"""Connection-owned Cursor sessions outlive their MCP creation responses."""
import json
import os
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import Mock, patch
from support import Client
from test_completion import adapter
from plugin_runtime import CONTINUATION_METADATA, Failure, Job, MCPServer, Process, WORK_INVOCATION, WORK_METADATA, WORK_URI


class WorkResourceTests(unittest.TestCase):
    def call(self, client, name, arguments=None, origin=None):
        params = {'name':name,'arguments':arguments or {}}
        if origin is not None: params['_meta'] = {WORK_INVOCATION:origin}
        return client.request('tools/call',params)

    def snapshot(self, client):
        response = client.request('resources/read',{'uri':WORK_URI})
        self.assertNotIn('error',response,response)
        contents = response['result']['contents']
        self.assertEqual(len(contents),1)
        self.assertEqual(contents[0]['uri'],WORK_URI)
        self.assertEqual(contents[0]['mimeType'],'application/json')
        return json.loads(contents[0]['text'])

    def test_native_session_report_spans_background_prompt_and_interactive_work(self):
        with tempfile.TemporaryDirectory() as root:
            client = Client(root)
            try:
                definitions = client.request('tools/list')['result']['tools']
                self.assertEqual(len(definitions),12)
                for definition in definitions:
                    self.assertEqual(definition['_meta'][WORK_METADATA],{'format_version':1,'uri':WORK_URI})
                    self.assertIn('io.github.computer-mcp/risk',definition['_meta'])
                continuations = {
                    'cursor.acp.session.prompt','cursor.acp.session.prompt.start',
                    'cursor.acp.session.prompt.result','cursor.acp.session.mode',
                    'cursor.acp.session.cancel','cursor.acp.session.close',
                    'cursor.acp.events.read','cursor.acp.requests.list','cursor.acp.requests.respond',
                }
                declared = {tool['name']:tool['_meta'][CONTINUATION_METADATA]
                            for tool in definitions if CONTINUATION_METADATA in tool['_meta']}
                self.assertEqual(set(declared),continuations)
                for selector in declared.values():
                    self.assertEqual(selector,{'format_version':1,'selectors':[
                        {'kind':'cursor.session','handles':{'id':'/session'}}]})
                self.assertEqual(client.request('resources/list')['result']['resources'][0]['uri'],WORK_URI)
                initial = self.snapshot(client)
                self.assertEqual(initial['resources'],[])
                origin = str(uuid.uuid4())
                opened = self.call(client,'cursor.acp.session.open',{'permission_policy':'manual'},origin)
                self.assertFalse(opened['result']['isError'],opened)
                session = Client.value(opened)['session']
                report = self.snapshot(client)
                self.assertEqual(report['instance_id'],initial['instance_id'])
                self.assertGreater(report['revision'],initial['revision'])
                self.assertEqual(report['resources'],[{'kind':'cursor.session','id':session,'acquired_by':origin,'state':'active'}])
                self.assertEqual(self.snapshot(client),report)
                started = self.call(client,'cursor.acp.session.prompt.start',{'session':session,'prompt':'permission'},str(uuid.uuid4()))
                prompt = Client.value(started)['prompt_id']
                for _ in range(100):
                    pending = Client.value(client.call('cursor.acp.requests.list',{'session':session}))['requests']
                    if pending: break
                    time.sleep(.02)
                else: self.fail('Native permission request did not become pending')
                self.assertEqual(self.snapshot(client),report)
                response = client.call('cursor.acp.requests.respond',{'session':session,'request_id':pending[0]['request_id'],'response':{'outcome':{'outcome':'selected','optionId':'opaque-no'}}})
                self.assertFalse(response['result']['isError'],response)
                for _ in range(100):
                    result = Client.value(client.call('cursor.acp.session.prompt.result',{'session':session,'prompt_id':prompt}))
                    if result.get('completed'): break
                    time.sleep(.02)
                else: self.fail('Native prompt did not complete')
                self.assertEqual(self.snapshot(client),report)
                closed = client.call('cursor.acp.session.close',{'session':session})
                self.assertFalse(closed['result']['isError'],closed)
                released = self.snapshot(client)
                self.assertEqual(released['resources'],[])
                self.assertGreater(released['revision'],report['revision'])
            finally: client.close()

    def test_unbound_live_sessions_fail_observation_without_breaking_ordinary_calls(self):
        with tempfile.TemporaryDirectory() as root:
            client = Client(root)
            try:
                self.assertEqual(self.snapshot(client)['resources'],[])
                opened = client.call('cursor.acp.session.open')
                self.assertFalse(opened['result']['isError'],opened)
                session = Client.value(opened)['session']
                missing = client.request('resources/read',{'uri':WORK_URI})
                self.assertIn('error',missing)
                self.assertIn('no bound host acquisition',missing['error']['message'])
                prompted = client.call('cursor.acp.session.prompt',{'session':session,'prompt':'hello'})
                self.assertFalse(prompted['result']['isError'],prompted)
                self.assertFalse(client.call('cursor.acp.session.close',{'session':session})['result']['isError'])
                self.assertEqual(self.snapshot(client)['resources'],[])
            finally: client.close()

    def test_concurrent_identical_open_calls_keep_distinct_acquisitions(self):
        with tempfile.TemporaryDirectory() as root:
            client = Client(root)
            try:
                requests = []
                for _ in range(2):
                    origin = str(uuid.uuid4())
                    client.serial += 1
                    requests.append((client.serial,origin))
                    client.send({'jsonrpc':'2.0','id':client.serial,'method':'tools/call',
                                 'params':{'name':'cursor.acp.session.open','arguments':{},
                                           '_meta':{WORK_INVOCATION:origin}}})
                expected = {}
                for request, origin in requests:
                    opened = client.wait(request)
                    self.assertFalse(opened['result']['isError'],opened)
                    expected[Client.value(opened)['session']] = origin
                self.assertEqual(len(expected),2)
                report = self.snapshot(client)
                self.assertEqual({row['id']:row['acquired_by'] for row in report['resources']},expected)
                for session in expected:
                    self.assertFalse(client.call('cursor.acp.session.close',{'session':session})['result']['isError'])
                self.assertEqual(self.snapshot(client)['resources'],[])
            finally: client.close()

    def test_invalid_metadata_and_resource_uris_do_not_start_work(self):
        with tempfile.TemporaryDirectory() as root:
            client = Client(root)
            try:
                for value in (None,True,7,{},[], 'bad-reference'):
                    response = client.request('tools/call',{'name':'cursor.acp.session.open','_meta':{WORK_INVOCATION:value}})
                    self.assertEqual(response['error']['code'],-32602)
                forged = self.call(client,'cursor.acp.session.open',{'acquired_by':str(uuid.uuid4())},str(uuid.uuid4()))
                self.assertTrue(forged['result']['isError'])
                self.assertEqual(self.snapshot(client)['resources'],[])
                self.assertIn('error',client.request('resources/read',{'uri':'https://unrelated.invalid'}))
                self.assertEqual(client.request('ping')['result'],{})
            finally: client.close()

    def test_unknown_cleanup_is_retained_through_close_and_shutdown(self):
        origin = str(uuid.uuid4())
        cursor = adapter.Cursor('/unused')
        session = adapter.Session('owned','/unused','manual',origin)
        session.process = Mock()
        session.process.close.side_effect = Failure('cleanup_unconfirmed','Fixture has no cleanup acknowledgement')
        cursor.sessions[session.handle] = session
        for close in (lambda:cursor.close({'session':'owned'},Job()),cursor.shutdown):
            with self.assertRaises(Failure): close()
            self.assertIn('owned',cursor.sessions)
            self.assertEqual(cursor.work_resources(),[{'kind':'cursor.session','id':'owned','acquired_by':origin,'state':'uncertain'}])

    def test_background_thread_must_drain_before_session_release(self):
        session = adapter.Session('owned','/unused','manual',str(uuid.uuid4()))
        session.process = Mock()
        session.prompt_thread = Mock()
        session.prompt_thread.is_alive.return_value = True
        with self.assertRaises(Failure): session.close()
        self.assertFalse(session.released())
        self.assertEqual(session.work_resource()['state'],'uncertain')
        session.prompt_thread.is_alive.return_value = False
        session.close()
        self.assertTrue(session.released())
        self.assertIsNone(session.work_resource())

    def test_self_closing_background_work_is_retained_until_its_thread_finishes(self):
        entered, release = threading.Event(), threading.Event()
        session = adapter.Session('owned','/unused','manual',str(uuid.uuid4()))
        def close_then_finish():
            session.close()
            entered.set()
            release.wait(2)
        session.prompt_thread = threading.Thread(target=close_then_finish)
        session.prompt_thread.start()
        try:
            self.assertTrue(entered.wait(1))
            self.assertTrue(session.cleanup_confirmed)
            self.assertFalse(session.released())
            self.assertIsNotNone(session.work_resource())
        finally:
            release.set()
            session.prompt_thread.join(2)
        self.assertTrue(session.released())

    def test_pending_startup_is_owned_before_native_execution(self):
        origin = str(uuid.uuid4())
        cursor = adapter.Cursor('/unused')
        entered, release = threading.Event(), threading.Event()
        errors = []
        def verify(*_):
            entered.set()
            if not release.wait(2): raise AssertionError('Probe not released')
            raise Failure('incompatible_vendor','No native session was launched')
        def run():
            try: cursor.open({},Job(work_invocation=origin))
            except Exception as error: errors.append(error)
        with patch.object(adapter,'resolve_executable',return_value='/unused'),patch.object(adapter,'verify_version',side_effect=verify),patch.object(adapter,'Process') as process:
            thread = threading.Thread(target=run)
            thread.start()
            try:
                self.assertTrue(entered.wait(1))
                rows = cursor.work_resources()
                self.assertEqual(len(rows),1)
                self.assertEqual(rows[0]['acquired_by'],origin)
                self.assertEqual(rows[0]['state'],'active')
            finally:
                release.set()
                thread.join(3)
            self.assertFalse(thread.is_alive())
            process.assert_not_called()
            self.assertEqual(len(errors),1)
            self.assertEqual(cursor.work_resources(),[])

    def test_version_probe_cleanup_uncertainty_retains_its_session(self):
        origin = str(uuid.uuid4())
        cursor = adapter.Cursor('/unused')
        probe = Mock()
        expected = next(row['stdout'] for row in adapter.TREE['executable_checks'] if row['args']==['--version'])
        probe.read.side_effect = [expected.encode(),None]
        probe.finish.return_value = 0
        probe.close.side_effect = Failure('cleanup_unconfirmed','Probe supervisor supplied no acknowledgement')
        with patch.object(adapter,'resolve_executable',return_value='/unused'),patch('plugin_runtime.Process',return_value=probe),patch.object(adapter,'Process') as native:
            with self.assertRaises(Failure): cursor.open({},Job(work_invocation=origin))
            native.assert_not_called()
        self.assertEqual(len(cursor.sessions),1)
        self.assertEqual(cursor.work_resources()[0]['state'],'uncertain')
        self.assertEqual(cursor.work_resources()[0]['acquired_by'],origin)
        with self.assertRaises(Failure): cursor.shutdown()
        self.assertEqual(len(cursor.sessions),1)

    def test_cleanup_io_failure_cannot_become_success_on_repeated_close(self):
        process = Process.__new__(Process)
        process.close_lock, process.writer_lock = threading.Lock(), threading.Lock()
        process.closed, process.cleanup_failure = False, None
        process.life, process.receipt = 100, 101
        process.child, process.output, process.stderr_thread = Mock(), Mock(), Mock()
        process.stop_stderr = threading.Event()
        def close(fd):
            if fd==process.life: raise OSError('Fixture lifeline close failed')
        with patch('plugin_runtime.os.close',side_effect=close),patch.object(process,'confirm_cleanup') as confirmed:
            for _ in range(2):
                with self.assertRaises(Failure) as error: process.close()
                self.assertEqual(error.exception.code,'cleanup_unconfirmed')
            confirmed.assert_not_called()

    def test_partial_process_initialization_retains_unknown_cleanup(self):
        for confirmed in (True,False):
            with self.subTest(confirmed=confirmed):
                cursor = adapter.Cursor('/unused')
                owners = []
                def close(process):
                    owners.append(process)
                    if not confirmed: raise Failure('cleanup_unconfirmed','Partial startup cleanup unavailable')
                try:
                    with patch.object(adapter,'resolve_executable',return_value='/unused'),patch('plugin_runtime.subprocess.Popen',return_value=Mock()),patch('plugin_runtime.os.set_blocking',side_effect=OSError('Fixture pipe setup failed')),patch.object(Process,'close',autospec=True,side_effect=close):
                        with self.assertRaises(OSError if confirmed else Failure):
                            cursor.open({},Job(work_invocation=str(uuid.uuid4())))
                    self.assertEqual(len(owners),1)
                    if confirmed:
                        self.assertEqual(cursor.work_resources(),[])
                    else:
                        self.assertEqual(len(cursor.sessions),1)
                        self.assertEqual(cursor.work_resources()[0]['state'],'uncertain')
                        with self.assertRaises(Failure): cursor.shutdown()
                finally:
                    # These descriptors belong to the inert, mocked process owner.
                    for owner in owners:
                        os.close(owner.life)
                        os.close(owner.receipt)

    def test_failed_snapshot_never_advances_revision_or_discards_valid_state(self):
        origin = str(uuid.uuid4())
        row = {'kind':'session','id':1,'acquired_by':origin,'state':'active'}
        rows = [row]
        server = MCPServer('fixture','1',[],lambda:None,work=lambda:rows)
        def snapshot(): return json.loads(server.work_resource()['contents'][0]['text'])
        first = snapshot()
        rows.append(dict(row))
        with self.assertRaises(Failure): snapshot()
        rows.pop()
        self.assertEqual(snapshot(),first)
        rows.append(dict(row,id='1'))
        second = snapshot()
        self.assertGreater(second['revision'],first['revision'])
        self.assertEqual(len(second['resources']),2)
        rows.reverse()
        self.assertEqual(snapshot(),second)
        rows[0]['state']='uncertain'
        self.assertGreater(snapshot()['revision'],second['revision'])


if __name__=='__main__': unittest.main()
