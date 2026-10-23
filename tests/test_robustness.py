"""Executable regressions; fixtures never contact Cursor or a model."""
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parent.parent
FAKE = '''#!/usr/bin/env python3
import json, sys
if sys.argv[1:] == ["--version"]:
    print("2026.05.04-08e5280"); raise SystemExit
for line in sys.stdin:
    q = json.loads(line)
    method = q.get("method")
    if method == "initialize":
        value = {"protocolVersion":1,"agentCapabilities":{"loadSession":True},"authMethods":[{"id":"cursor_login","name":"Login"}]}
    elif method == "session/new":
        value = {"sessionId":"fixture-session"}
    elif method == "session/prompt":
        value = {"stopReason":"end_turn"}
    else:
        value = {}
    if "id" in q: print(json.dumps({"jsonrpc":"2.0","id":q["id"],"result":value}),flush=True)
'''

class RobustnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        fake = Path(self.temp.name) / "agent"
        fake.write_text(FAKE)
        fake.chmod(0o755)
        env = dict(os.environ, CURSOR_AGENT_EXECUTABLE=str(fake))
        self.p = subprocess.Popen([sys.executable,str(ROOT/'bin/cursor-mcp-adapter')],cwd=self.temp.name,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.addCleanup(self.stop)
        self.buffer = b''
        self.serial = 2
        self.request({'id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'fixture','version':'1'}}})
        self.send({'method':'notifications/initialized'})

    def stop(self):
        if not self.p.stdin.closed: self.p.stdin.close()
        try: self.p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.p.kill(); self.p.wait(timeout=3)
        self.p.stdout.close(); self.p.stderr.close()

    def send(self, q):
        self.p.stdin.write((json.dumps(dict(jsonrpc='2.0',**q))+'\n').encode()); self.p.stdin.flush()

    def receive(self, seconds=5):
        deadline=time.monotonic()+seconds
        with selectors.DefaultSelector() as selector:
            selector.register(self.p.stdout,selectors.EVENT_READ)
            while b'\n' not in self.buffer:
                remaining=deadline-time.monotonic()
                if remaining<=0 or not selector.select(remaining): self.fail('MCP response timeout')
                chunk=os.read(self.p.stdout.fileno(),65536)
                if not chunk: self.fail('MCP exited before a response')
                self.buffer+=chunk
        raw,self.buffer=self.buffer.split(b'\n',1)
        return json.loads(raw)

    def request(self,q): self.send(q); return self.receive()
    def call(self,args):
        self.serial+=1
        return self.request({'id':self.serial,'method':'tools/call','params':{'name':'cursor.acp.prompt','arguments':args}})

    def test_unknown_arguments_are_rejected(self):
        r=self.call({'prompt':'hello','arbitrary_cwd':'/outside'})
        self.assertTrue(r.get('error') or r['result']['isError'])

    def test_ping_is_supported(self):
        self.assertEqual(self.request({'id':10,'method':'ping'})['result'],{})

    def test_unimplemented_protocol_is_not_echoed(self):
        # A new server is needed because initialize is single-use.
        self.stop()
        self.setUp()
        self.p.stdin.close(); self.p.wait(timeout=3)
        self.p.stdout.close(); self.p.stderr.close()
        self.p=subprocess.Popen([sys.executable,str(ROOT/'bin/cursor-mcp-adapter')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.buffer=b''
        r=self.request({'id':11,'method':'initialize','params':{'protocolVersion':'9999-01-01','capabilities':{},'clientInfo':{'name':'fixture','version':'1'}}})
        self.assertEqual(r['result']['protocolVersion'],'2025-06-18')

    def test_non_object_request_has_protocol_error(self):
        self.p.stdin.write(b'[]\n');self.p.stdin.flush()
        self.assertEqual(self.receive()['error']['code'],-32600)

if __name__=='__main__': unittest.main()
