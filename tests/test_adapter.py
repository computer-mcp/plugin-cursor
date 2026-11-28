import json
from pathlib import Path
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
    def test_catalog_declares_execution_and_inspection_risk(self):
        expected = {'cursor.acp.prompt': 'full-shell', 'cursor.acp.session.open': 'full-shell', 'cursor.acp.session.prompt': 'full-shell', 'cursor.acp.session.prompt.start': 'full-shell', 'cursor.acp.session.prompt.result': 'read-only', 'cursor.acp.session.list': 'read-only', 'cursor.acp.session.mode': 'full-shell', 'cursor.acp.session.cancel': 'destructive', 'cursor.acp.session.close': 'destructive', 'cursor.acp.events.read': 'read-only', 'cursor.acp.requests.list': 'read-only', 'cursor.acp.requests.respond': 'full-shell'}
        tools = self.client.request('tools/list')['result']['tools']
        self.assertEqual({tool['name']:tool['_meta']['io.github.computer-mcp/risk'] for tool in tools},expected)
        for tool in tools:
            risk = expected[tool['name']]
            self.assertEqual(tool['annotations']['readOnlyHint'],risk=='read-only')
            self.assertEqual(tool['annotations']['destructiveHint'],risk in {'destructive','full-shell'})
    def test_acp_prompt_through_mcp(self):
        r=self.value(self.call('prompt',{'prompt':'hello'}))
        self.assertEqual(r['text'],'hello');self.assertEqual(r['stop_reason'],'end_turn')
        self.assertEqual(self.value(self.call('session.list'))['sessions'],[])
    def test_authentication_rejection_stops_before_native_session_setup(self):
        cases = [
            (-32000, 'fixture-sensitive-message', 'authentication_required'),
            (-32602, 'Failed to open browser for login. Please visit: https://example.test/fixture-sensitive-url',
             'vendor_error'),
            (-32603, 'fixture-sensitive-message', 'vendor_error'),
        ]
        for rpc_code, message, expected in cases:
            with self.subTest(rpc_code=rpc_code, expected=expected), tempfile.TemporaryDirectory() as directory:
                client = Client(directory, {
                    'HOME': directory, 'CURSOR_SOURCE_FIXTURE': '1',
                    'FIXTURE_AUTH_ERROR_CODE': str(rpc_code),
                    'FIXTURE_AUTH_ERROR_MESSAGE': message,
                })
                try:
                    response = client.call('cursor.acp.session.open')
                    self.assertTrue(response['result']['isError'])
                    error = Client.value(response)['error']
                    self.assertEqual(error['code'], expected)
                    self.assertIn(f'RPC code {rpc_code}', error['message'])
                    if rpc_code == -32000:
                        self.assertIn('Run `agent login` in the standalone Cursor Agent context.', error['message'])
                    else:
                        self.assertEqual(error['message'], f'Cursor rejected authenticate (RPC code {rpc_code}).')
                    self.assertNotIn('fixture-sensitive', json.dumps(response))
                    self.assertNotIn('https://example.test/', json.dumps(response))
                    self.assertEqual(self.value(client.call('cursor.acp.session.list'))['sessions'], [])
                finally:
                    client.close()
                effects = (Path(directory) / 'cursor-vendor-effects.jsonl').read_text().splitlines()
                self.assertEqual([json.loads(line)['phase'] for line in effects],
                                 ['probe', 'workload', 'rejected_authentication'])
                self.assertFalse((Path(directory) / 'cursor-native-starts.jsonl').exists())
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
    def begin_cancel_case(self, session, prompt):
        request = self.client.begin('cursor.acp.session.prompt', {
            'session': session, 'prompt': prompt, 'timeout_seconds': 10,
        })
        for _ in range(80):
            page = self.value(self.call('events.read', {'session': session}))
            if page['events']:
                return request
            time.sleep(.02)
        self.fail('Native prompt did not start')

    def cancel_and_wait(self, session, request):
        self.assertEqual(self.value(self.call('session.cancel', {'session': session})),
                         {'cancel_requested': True, 'session': session})
        return self.client.wait(request, timeout=5)

    def test_native_cancel_settles_prompt_and_session_can_be_reused(self):
        session = self.open(resume_session_id='cancel-target')
        request = self.begin_cancel_case(session, 'slow')
        response = self.cancel_and_wait(session, request)
        self.assertTrue(response['result']['isError'])
        result = Client.value(response)
        self.assertEqual(result['stop_reason'], 'cancelled')
        self.assertTrue(result['is_error'])
        self.assertEqual(result['native_result'], {
            'stopReason': 'cancelled', 'usage': {'tokens': 3}, '_meta': {'fixture': 'settled'},
        })
        reused = self.value(self.call('session.prompt', {'session': session, 'prompt': 'after-cancel'}))
        self.assertEqual(reused['session_id'], 'cancel-target')
        self.assertEqual(reused['stop_reason'], 'end_turn')

    def test_native_completion_can_win_cancellation_without_affecting_sibling(self):
        target = self.open(resume_session_id='cancel-target')
        sibling = self.open(resume_session_id='unrelated-sibling', permission_policy='manual')
        sibling_request = self.client.begin('cursor.acp.session.prompt', {
            'session': sibling, 'prompt': 'permission', 'timeout_seconds': 15,
        })
        pending = self.pending(sibling)
        target_request = self.begin_cancel_case(target, 'complete-on-cancel')
        result = self.value(self.cancel_and_wait(target, target_request))
        self.assertEqual(result['stop_reason'], 'end_turn')
        self.assertFalse(result['is_error'])
        self.assertEqual(result['native_result'], {
            'stopReason': 'end_turn', 'usage': {'tokens': 7}, '_meta': {'fixture': 'completed'},
        })
        self.assertEqual(self.value(self.call('requests.list', {'session': sibling}))['requests'],
                         [pending])
        self.value(self.call('requests.respond', {
            'session': sibling, 'request_id': pending['request_id'],
            'response': {'outcome': {'outcome': 'selected', 'optionId': 'opaque-yes'}},
        }))
        sibling_result = self.value(self.client.wait(sibling_request, timeout=5))
        self.assertEqual(sibling_result['session_id'], 'unrelated-sibling')
        self.assertEqual(sibling_result['stop_reason'], 'end_turn')
        self.assertIn('opaque-yes', sibling_result['text'])

    def test_cancel_preserves_native_error_and_result_validation(self):
        for prompt, code, detail in [
            ('error-on-cancel', 'vendor_error', '-32023'),
            ('invalid-result-on-cancel', 'invalid_vendor_response', 'must be an object'),
            ('missing-stop-on-cancel', 'invalid_vendor_response', 'lacks a stop reason'),
        ]:
            with self.subTest(prompt=prompt):
                session = self.open()
                request = self.begin_cancel_case(session, prompt)
                response = self.cancel_and_wait(session, request)
                self.assertTrue(response['result']['isError'])
                error = Client.value(response)['error']
                self.assertEqual(error['code'], code)
                self.assertIn(detail, error['message'])
                closed = self.call('session.prompt', {'session': session, 'prompt': 'after'})
                self.assertEqual(Client.value(closed)['error']['code'], 'session_closed')
    def test_unsettled_native_cancellation_retires_owned_session(self):
        session=self.open()
        request=self.client.begin('cursor.acp.session.prompt',{'session':session,'prompt':'ignore-cancel'})
        for _ in range(80):
            if self.value(self.call('events.read',{'session':session}))['events']:break
            time.sleep(.02)
        else:self.fail('Native prompt did not start')
        started=time.monotonic()
        self.value(self.call('session.cancel',{'session':session}))
        result=Client.value(self.client.wait(request))
        self.assertEqual(result['error']['code'],'cancelled')
        self.assertLess(time.monotonic()-started,5)
        self.assertTrue(self.call('session.prompt',{'session':session,'prompt':'after'})['result']['isError'])

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
