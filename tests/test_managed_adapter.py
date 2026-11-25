"""Exercise the packaged Cursor adapter on its private carrier and ordinary MCP."""

import base64
import io
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
import zipfile

from support import Client, ROOT
from test_package import builder

CAPABILITY = 'io.github.computer-mcp/vendor-execution-v1'
METADATA = 'io.github.computer-mcp/work-invocation'
PEER = ROOT / 'tests/Fixtures/vendor.py'
REFUSAL = 'vendor_effect_denied'


class VendorFixture:
    """Drive the adapter contract with a local socket and a deterministic ACP peer."""

    def __init__(self, home, answer_error):
        self.socket, self.adapter_socket = socket.socketpair()
        self.home = home
        self.answer_error = answer_error
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.vendor = None
        self.turn = None
        self.answers = []
        self.retirements = 0
        self.error = None
        self.thread.start()

    def serve(self):
        try:
            with self.socket.makefile('rb') as incoming:
                for line in incoming:
                    request = json.loads(line)
                    result = self.respond(request)
                    self.socket.sendall(json.dumps({'id': request['id'], **result}).encode() + b'\n')
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as error:
            self.error = error
            self.socket.shutdown(socket.SHUT_RDWR)
        finally:
            self.retire()
            self.socket.close()

    def respond(self, request):
        op = request['op']
        result = {}
        if op == 'initialize':
            result = {'capability': request['capability']}
        elif op == 'bind':
            result = {'probe': 'probe', 'workload': 'workload'}
        elif op == 'probe':
            completed = subprocess.run(
                [sys.executable, str(PEER), '--version'], capture_output=True, timeout=3, check=True)
            assert completed.stdout == b'2026.05.04-08e5280\n', completed
        elif op == 'launch':
            assert self.vendor is None
            self.vendor = subprocess.Popen(
                [sys.executable, str(PEER), 'acp'], cwd=self.home,
                env={'HOME': str(self.home), 'CURSOR_SOURCE_FIXTURE': '1'},
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        elif op == 'read':
            if self.vendor is None:
                return {'error': 'vendor_effect_stale'}
            if select.select([self.vendor.stdout], [], [], .02)[0]:
                data = os.read(self.vendor.stdout.fileno(), 65536)
                result = ({'data': base64.b64encode(data).decode(), 'cursor': request['after'] + 1}
                          if data else {'eof': True})
            else:
                result = {'eof': False}
        elif op == 'write':
            message = json.loads(request['data'])
            kind = request['kind']
            if kind == 'prompt':
                self.turn = request['call']
            if kind == 'answer' and self.answer_error == REFUSAL:
                return {'error': REFUSAL}
            if kind in ('answer', 'housekeeping'):
                self.answers.append(message)
            self.vendor.stdin.write(request['data'].encode() + b'\n')
            self.vendor.stdin.flush()
            if kind == 'answer' and self.answer_error:
                return {'error': self.answer_error}
        elif op == 'stop':
            result = {'turn': self.turn, 'dispatched': True, 'sent': False}
        elif op == 'retire':
            self.retire()
            self.retirements += 1
            result = {'retired': True, 'probe_settled': True, 'workload_settled': True}
        else:
            assert op in ('ready', 'pending', 'finish', 'detach'), request
        return {'result': result}

    def retire(self):
        if self.vendor is not None:
            process, self.vendor = self.vendor, None
            try:
                process.stdin.close()
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
                raise
            finally:
                process.stdout.close()
                process.stderr.close()

    def close(self):
        self.adapter_socket.close()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            self.socket.shutdown(socket.SHUT_RDWR)
            self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise AssertionError('Fixture carrier did not finish')
        if self.error:
            raise self.error


class ManagedAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stage = tempfile.TemporaryDirectory()
        cls.addClassCleanup(stage.cleanup)
        cls.root = Path(stage.name)
        with zipfile.ZipFile(io.BytesIO(builder.package_bytes(ROOT)[0])) as archive:
            archive.extractall(cls.root)
        cls.adapter = cls.root / 'bin/cursor-mcp-adapter'

    def setUp(self):
        self.home = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def managed(self, answer_error):
        host = VendorFixture(self.home, answer_error)
        self.addCleanup(host.close)
        fd = host.adapter_socket.fileno()
        bootstrap = (
            'import os,sys; fd=int(sys.argv[1]); '
            'os.dup2(fd,3); os.set_inheritable(3,True); '
            'os.close(fd) if fd!=3 else None; os.execv(sys.executable,[sys.executable,*sys.argv[2:]])'
        )
        client = Client(self.home, {
            'COMPUTER_MCP_HOST_CONTEXT': CAPABILITY, 'COMPUTER_MCP_HOST_FD': '3',
        }, [sys.executable, '-B', '-c', bootstrap, str(fd), str(self.adapter),
            '--host-vendor-execution'], pass_fds=(fd,))
        self.addCleanup(client.close)
        host.adapter_socket.close()
        self.assertIs(client.initialization['result']['capabilities']['experimental'][CAPABILITY], True)
        return client, host

    def raw_call(self, client, name, arguments=None, *, wait=True):
        client.serial += 1
        identifier = client.serial
        client.send({
            'jsonrpc': '2.0', 'id': identifier, 'method': 'tools/call',
            'params': {'name': 'cursor.acp.' + name, 'arguments': arguments or {},
                       '_meta': {METADATA: str(uuid.uuid4())}},
        })
        return client.wait(identifier, timeout=10) if wait else identifier

    def value(self, response):
        self.assertFalse(response['result']['isError'], response)
        return Client.value(response)

    def pending(self, client, session):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            requests = self.value(self.raw_call(client, 'requests.list', {'session': session}))['requests']
            if requests:
                return requests[0]
            time.sleep(.01)
        self.fail('Peer did not request a manual answer')

    def interactive(self, client):
        session = self.value(self.raw_call(client, 'session.open', {'permission_policy': 'manual'}))['session']
        prompt = self.raw_call(client, 'session.prompt', {
            'session': session, 'prompt': 'permission-on-cancel', 'timeout_seconds': 10,
        }, wait=False)
        token = self.pending(client, session)['request_id']
        answer = {'outcome': {'outcome': 'selected', 'optionId': 'opaque-yes'}}
        response = self.raw_call(client, 'requests.respond', {
            'session': session, 'request_id': token, 'response': answer,
        })
        self.assertTrue(response['result']['isError'])
        return session, prompt, token, Client.value(response)['error']['code']

    def test_definitive_answer_refusal_leaves_turn_to_settle_pending_and_reuse_session(self):
        client, host = self.managed(REFUSAL)
        session, prompt, token, code = self.interactive(client)
        self.assertEqual(code, 'response_refused')
        self.assertEqual(self.pending(client, session)['request_id'], token)
        self.assertTrue(self.value(self.raw_call(client, 'session.cancel', {'session': session}))['cancel_requested'])
        stopped = client.wait(prompt, timeout=5)
        self.assertTrue(stopped['result']['isError'])
        self.assertEqual(Client.value(stopped)['native_result'], {'stopReason': 'cancelled'})
        self.assertEqual(host.answers, [
            {'jsonrpc': '2.0', 'id': 900, 'result': {'outcome': {'outcome': 'cancelled'}}},
        ])
        self.assertEqual(host.retirements, 0)
        self.assertEqual(self.value(self.raw_call(client, 'requests.list', {'session': session}))['requests'], [])
        reused = self.value(self.raw_call(client, 'session.prompt', {'session': session, 'prompt': 'hello'}))
        self.assertEqual(reused['text'], 'hello')
        self.assertEqual((self.home / 'cursor-native-starts.jsonl').read_text().count('\n'), 1)
        self.value(self.raw_call(client, 'session.close', {'session': session}))
        self.assertEqual(host.retirements, 1)

    def test_unknown_answer_delivery_retires_without_replaying_answer(self):
        client, host = self.managed('cleanup_unconfirmed')
        session, prompt, _, code = self.interactive(client)
        self.assertEqual(code, 'response_unknown')
        client.wait(prompt, timeout=5)
        self.assertEqual(host.answers, [
            {'jsonrpc': '2.0', 'id': 900,
             'result': {'outcome': {'outcome': 'selected', 'optionId': 'opaque-yes'}}},
        ])
        self.assertGreaterEqual(host.retirements, 1)
        result = self.raw_call(client, 'session.prompt', {'session': session, 'prompt': 'hello'})
        self.assertTrue(result['result']['isError'])

    def test_packaged_standalone_and_missing_managed_negotiation(self):
        environment = {'HOME': str(self.home), 'PATH': os.environ['PATH'], 'CURSOR_SOURCE_FIXTURE': '1'}
        missing = subprocess.run(
            [sys.executable, '-B', str(self.adapter), '--host-vendor-execution', '--executable', str(PEER)],
            env=environment, capture_output=True, timeout=5)
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn(b'Managed Cursor requires the Host vendor channel', missing.stderr)
        self.assertFalse((self.home / 'cursor-vendor-effects.jsonl').exists())
        client = Client(self.home, environment, [sys.executable, '-B', str(self.adapter)])
        self.addCleanup(client.close)
        self.assertNotIn('experimental', client.initialization['result']['capabilities'])
        result = self.value(client.call('cursor.acp.prompt', {'prompt': 'hello'}))
        self.assertEqual(result['stop_reason'], 'end_turn')
        self.assertEqual(result['text'], 'hello')
        self.assertTrue(result['closed'])
