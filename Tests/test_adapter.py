import json
import tempfile
import time
import unittest
from support import Client


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.client=Client(self.temp.name);self.addCleanup(self.client.close)
    def call(self,name,args=None):return self.client.call('cursor.acp.'+name,args)
    def value(self,response):
        self.assertFalse(response['result']['isError'],response)
        return Client.value(response)
    def open(self,**args):return self.value(self.call('session.open',args))['session']
    def test_acp_prompt_through_mcp(self):
        r=self.value(self.call('prompt',{'prompt':'hello'}))
        self.assertEqual(r['text'],'hello');self.assertEqual(r['stop_reason'],'end_turn')
        self.assertEqual(self.value(self.call('session.list'))['sessions'],[])
    def test_reuse_session_and_explicit_native_resume(self):
        session=self.open(resume_session_id='saved-conversation',mode='plan')
        for prompt in ['first','second']:
            r=self.value(self.call('session.prompt',{'session':session,'prompt':prompt}))
            self.assertEqual(r['session_id'],'saved-conversation')
        self.value(self.call('session.close',{'session':session}))
        self.assertTrue(self.call('session.prompt',{'session':session,'prompt':'late'})['result']['isError'])
    def test_opaque_permission_ids_follow_offered_kind(self):
        r=self.value(self.call('prompt',{'prompt':'permission','permission_policy':'allow-once'}))
        self.assertIn('opaque-yes',r['text'])
    def test_unoffered_allow_falls_back_to_reject(self):
        r=self.value(self.call('prompt',{'prompt':'permission','permission_policy':'allow-always'}))
        self.assertIn('opaque-no',r['text'])
    def pending(self,session):
        for _ in range(80):
            pending=self.value(self.call('requests.list',{'session':session}))['requests']
            if pending:return pending[0]
            time.sleep(.02)
        self.fail('No pending request')
    def interactive(self,prompt,response):
        session=self.open(permission_policy='manual')
        request=self.client.begin('cursor.acp.session.prompt',{'session':session,'prompt':prompt})
        pending=self.pending(session)
        bad=self.call('requests.respond',{'session':session,'request_id':pending['request_id'],'response':{'outcome':{'outcome':'selected','optionId':'not-offered'}}})
        self.assertTrue(bad['result']['isError'])
        self.value(self.call('requests.respond',{'session':session,'request_id':pending['request_id'],'response':response}))
        self.value(self.client.wait(request))
        stale=self.call('requests.respond',{'session':session,'request_id':pending['request_id'],'response':response})
        self.assertTrue(stale['result']['isError'])
        self.value(self.call('session.close',{'session':session}))
    def test_manual_permission_response(self):
        self.interactive('permission',{'outcome':{'outcome':'selected','optionId':'opaque-yes'}})
    def test_question_response(self):
        self.interactive('question',{'outcome':{'outcome':'answered','answers':[{'questionId':'q1','selectedOptionIds':['a']}]}})
    def test_plan_response(self):
        self.interactive('plan',{'outcome':{'outcome':'accepted'}})
    def test_native_cancel_settles_prompt_and_session_can_be_reused(self):
        session=self.open()
        request=self.client.begin('cursor.acp.session.prompt',{'session':session,'prompt':'slow'})
        for _ in range(80):
            page=self.value(self.call('events.read',{'session':session}))
            if page['events']:break
            time.sleep(.02)
        self.value(self.call('session.cancel',{'session':session}))
        self.assertEqual(Client.value(self.client.wait(request))['stop_reason'],'cancelled')
        self.value(self.call('session.prompt',{'session':session,'prompt':'after-cancel'}))
    def test_early_exit_does_not_drop_buffered_result(self):
        self.assertEqual(self.value(self.call('prompt',{'prompt':'exit-fast'}))['stop_reason'],'end_turn')
    def test_aggregate_events_are_bounded_and_cursor_progresses(self):
        session=self.open()
        r=self.value(self.call('session.prompt',{'session':session,'prompt':'flood'}))
        self.assertTrue(r['events_truncated']);self.assertTrue(r['text_truncated'])
        page=self.value(self.call('events.read',{'session':session,'max_bytes':1024}))
        self.assertTrue(page['missed_events']);self.assertGreater(page['next_cursor'],0)
        self.assertLess(len(json.dumps(page)),8192)
    def test_oversized_unterminated_line_fails_without_waiting_for_newline(self):
        started=time.monotonic()
        r=self.call('prompt',{'prompt':'huge','timeout_seconds':5})
        self.assertEqual(Client.value(r)['error']['code'],'frame_too_large')
        self.assertLess(time.monotonic()-started,4)
    def test_malformed_vendor_does_not_crash_mcp(self):
        self.assertTrue(self.call('prompt',{'prompt':'malformed'})['result']['isError'])
        self.assertIn('result',self.client.request('ping'))

if __name__=='__main__':unittest.main()
