"""Malformed peer input must not terminate unrelated MCP work."""
import json
import sys
import threading
import unittest
from unittest.mock import patch
from support import ROOT
sys.path.insert(0,str(ROOT/'bin'))
import plugin_runtime as runtime

class ProtocolAdmissionTests(unittest.TestCase):
    def test_invalid_unicode_is_rejected_in_all_json_string_positions(self):
        for raw in (b'{"id":"\\ud800"}',b'{"\\udfff":1}',b'["\\ud800"]'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):
                runtime.decoded(raw)
        self.assertEqual(runtime.decoded(b'"\\ud83d\\ude00"'),'\U0001f600')
    def test_bad_id_does_not_end_active_tool_or_connection(self):
        entered,release=threading.Event(),threading.Event()
        def handler(_args,job):
            entered.set()
            if not release.wait(2): raise AssertionError('fixture not released')
            job.check()
            return {'finished':True}
        server=runtime.MCPServer('fixture','1',[runtime.Tool('hold','fixture',runtime.schema({}),handler,risk='read-only')],lambda:None)
        server.initialized=True
        messages=[]
        def write(_fd,data,*_): messages.append(json.loads(data))
        with patch.object(runtime,'write_bytes',side_effect=write):
            server.dispatch({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'hold'}})
            try:
                self.assertTrue(entered.wait(1))
                server.dispatch({'jsonrpc':'2.0','id':'\ud800','method':'ping'})
                self.assertEqual(messages[-1]['error']['code'],-32600)
                self.assertIsNone(messages[-1]['id'])
                server.dispatch({'jsonrpc':'2.0','id':2,'method':'ping'})
                self.assertEqual(messages[-1]['result'],{})
                self.assertFalse(server.stop.is_set())
            finally:
                with server.lock: threads=list(server.threads)
                release.set()
                for thread in threads: thread.join(2)
            completion=next(m for m in messages if m['id']==1)
            self.assertFalse(completion['result']['isError'])
    def test_active_request_id_cannot_be_reused_by_ping(self):
        server=runtime.MCPServer('fixture','1',[],lambda:None)
        server.jobs[server.id_key(5)]=runtime.Job()
        with patch.object(server,'emit') as emit:
            server.dispatch({'jsonrpc':'2.0','id':5,'method':'ping'})
            self.assertIn('error',emit.call_args.args[0])
            self.assertIn(server.id_key(5),server.jobs)

    def test_denied_process_inspection_cannot_confirm_cleanup(self):
        child=unittest.mock.Mock(pid=42,returncode=0)
        writes=[]
        report=unittest.mock.Mock(returncode=1,stdout='',stderr='permission denied')
        with patch.object(runtime.subprocess,'Popen',return_value=child), patch.object(runtime.os,'waitid',return_value=object()), patch.object(runtime.os,'killpg',side_effect=PermissionError()), patch.object(runtime.subprocess,'run',return_value=report), patch.object(runtime.os,'write',side_effect=lambda fd,data:writes.append((fd,data))), patch.object(runtime.os,'close'), patch.object(runtime.signal,'signal'):
            result=runtime.supervise(10,11,['/unused'])
        self.assertEqual(result,70)
        receipt=runtime.decoded(next(data for fd,data in writes if fd==11))
        self.assertFalse(receipt['cleanup_confirmed'])

    def test_protocol_negotiation_uses_supported_dates_and_typed_fields(self):
        for date in (*runtime.SUPPORTED_MCP,'unsupported'):
            server=runtime.MCPServer('fixture','1',[],lambda:None)
            with patch.object(server,'emit') as emit:
                server.dispatch({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':date,'capabilities':{},'clientInfo':{'name':'test','version':'1'}}})
                self.assertIn(emit.call_args.args[0]['result']['protocolVersion'],runtime.SUPPORTED_MCP)
        for fields in ({'protocolVersion':True},{'protocolVersion':'2025-06-18','capabilities':[]},
                       {'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':4,'version':'1'}}):
            server=runtime.MCPServer('fixture','1',[],lambda:None)
            with patch.object(server,'emit') as emit:
                server.dispatch({'jsonrpc':'2.0','id':1,'method':'initialize','params':fields})
                self.assertIn('error',emit.call_args.args[0])
                self.assertFalse(server.initialized)

if __name__=='__main__': unittest.main()
