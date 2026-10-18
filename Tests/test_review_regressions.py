"""ACP request identity, operation ownership and terminal-state regressions."""
import queue
import threading
import time
import unittest
from unittest.mock import patch
from test_completion import adapter
from plugin_runtime import Failure, Job, encoded

PERMISSION = {'jsonrpc':'2.0','id':900,'method':'session/request_permission',
              'params':{'sessionId':'native-session','options':[{'optionId':'yes','kind':'allow_once'}]}}
ALLOW = {'outcome':{'outcome':'selected','optionId':'yes'}}

class Peer:
    def __init__(self):
        self.frames=queue.Queue()
        self.sent=[]
        self.requested=threading.Event()
        self.closed=False
        self.on_send=lambda _:None
    def send(self,message,*_):
        self.on_send(message)
        self.sent.append(message)
        if 'method' in message and 'id' in message:self.requested.set()
    def read(self,deadline,*_):
        try:return encoded(self.frames.get(timeout=max(0,deadline-time.monotonic())))
        except queue.Empty:raise Failure('timeout','fixture read deadline')
    def close(self):self.closed=True

class ReviewRegressions(unittest.TestCase):
    def begin(self,policy='manual',method='session/prompt'):
        session=adapter.Session('handle','/unused',policy)
        session.vendor_id='native-session'
        peer=Peer();session.process=peer
        result=[]
        def execute():
            try:result.append(session.request(method,{},time.monotonic()+3,Job()))
            except Exception as error:result.append(error)
        thread=threading.Thread(target=execute)
        thread.start()
        self.assertTrue(peer.requested.wait(1))
        def cleanup():
            peer.frames.put({'jsonrpc':'2.0','id':session.sequence,'result':{'stopReason':'end_turn'}})
            thread.join(4)
            self.assertFalse(thread.is_alive())
        self.addCleanup(cleanup)
        return session,peer,thread,result
    def pending(self,session):
        deadline=time.monotonic()+1
        while time.monotonic()<deadline:
            with session.lock:
                if session.pending:return next(iter(session.pending))
            time.sleep(.001)
        self.fail('Native request did not become pending')
    def test_close_during_version_probe_prevents_later_native_launch(self):
        session=adapter.Session('handle','/unused','manual');job=Job()
        def verify(*_):session.close()
        with patch.object(adapter,'verify_version',side_effect=verify),patch.object(adapter,'Process') as process:
            with self.assertRaises(Failure) as error:session.open({},job)
            self.assertEqual(error.exception.code,'cancelled')
            process.assert_not_called()

    def test_duplicate_and_invalid_native_request_ids_fail_closed(self):
        for identifier in (900,True,None,[],{}):
            with self.subTest(identifier=identifier):
                session,peer,thread,result=self.begin()
                peer.frames.put(PERMISSION);self.pending(session)
                peer.frames.put(dict(PERMISSION,id=identifier))
                thread.join(.5)
                self.assertFalse(thread.is_alive())
                self.assertIsInstance(result[0],Failure)
                self.assertTrue(peer.closed)
    def test_integer_and_string_request_ids_are_distinct(self):
        session,peer,_,_=self.begin()
        peer.frames.put(PERMISSION);first=self.pending(session)
        session.vendor_request(dict(PERMISSION,id='900'),time.monotonic()+2)
        with session.lock:tokens=list(session.pending)
        self.assertEqual(len(tokens),2)
        for token in tokens:session.answer(token,ALLOW)
        self.assertEqual([m['id'] for m in peer.sent if 'result' in m],[900,'900'])
    def test_cancelled_operation_cannot_send_allow(self):
        session,peer,_,_=self.begin()
        peer.frames.put(PERMISSION);token=self.pending(session)
        session.cancelled.set()
        with self.assertRaises(Failure) as error:session.answer(token,ALLOW)
        self.assertEqual(error.exception.code,'stale_request')
        self.assertFalse(any(m.get('result')==ALLOW for m in peer.sent))

    def test_settled_native_id_can_be_reused_with_a_fresh_token(self):
        session,peer,_,_=self.begin()
        peer.frames.put(PERMISSION);first=self.pending(session)
        session.answer(first,ALLOW)
        peer.frames.put(PERMISSION);second=self.pending(session)
        self.assertNotEqual(first,second)
        with self.assertRaises(Failure):session.answer(first,ALLOW)
        session.answer(second,ALLOW)
        self.assertEqual(sum(m.get('result')==ALLOW for m in peer.sent),2)

    def test_protocol_version_must_be_an_exact_integer(self):
        for version in (True,1.0,'1'):
            session=adapter.Session('handle','/unused','manual')
            with patch.object(adapter,'verify_version'),patch.object(adapter,'Process',return_value=Peer()),patch.object(session,'request',return_value={'protocolVersion':version}):
                with self.assertRaises(Failure) as error:session.open({},Job())
                self.assertEqual(error.exception.code,'unsupported_protocol')

    def test_foreign_session_never_receives_permission_or_output(self):
        for policy in ('allow-once','manual'):
            session,peer,thread,result=self.begin(policy)
            peer.frames.put(dict(PERMISSION,params=dict(PERMISSION['params'],sessionId='foreign')))
            thread.join(.5)
            self.assertFalse(thread.is_alive())
            self.assertIsInstance(result[0],Failure)
            self.assertFalse(any(m.get('result')==ALLOW for m in peer.sent))
        session,peer,thread,result=self.begin()
        peer.frames.put({'jsonrpc':'2.0','method':'session/update','params':{'sessionId':'foreign','update':{'sessionUpdate':'agent_message_chunk','content':{'text':'foreign'}}}})
        thread.join(.5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(session.text,b'')
    def test_response_delivery_finishes_before_operation_retirement(self):
        session,peer,_,_=self.begin()
        peer.frames.put(PERMISSION);token=self.pending(session)
        entered,release,retired=threading.Event(),threading.Event(),threading.Event()
        failures=[]
        def pause(message):
            if message.get('result')==ALLOW:
                entered.set()
                if not release.wait(2):raise AssertionError('fixture response not released')
        peer.on_send=pause
        def answer():
            try:session.answer(token,ALLOW)
            except Exception as error:failures.append(error)
        writer=threading.Thread(target=answer);writer.start()
        self.assertTrue(entered.wait(1))
        retire=threading.Thread(target=lambda:(session.cancel_pending(),retired.set()))
        retire.start()
        try:self.assertFalse(retired.wait(.05),'Retirement overtook an owned response write')
        finally:
            release.set();writer.join(2);retire.join(2)
        self.assertEqual(failures,[])
        self.assertTrue(retired.is_set())
    def test_busy_prompt_does_not_retire_control_request(self):
        session,peer,_,_=self.begin(method='session/set_mode')
        peer.frames.put(PERMISSION);token=self.pending(session)
        with self.assertRaises(Failure):session.prompt({'prompt':'rejected'},Job())
        self.assertIn(token,session.pending)
        session.answer(token,ALLOW)
    def test_completed_operation_expires_pending_and_reused_id_is_safe(self):
        session,peer,thread,_=self.begin()
        peer.frames.put(PERMISSION);token=self.pending(session)
        peer.frames.put({'jsonrpc':'2.0','id':session.sequence,'result':{}})
        thread.join(1)
        with self.assertRaises(Failure) as error:session.answer(token,ALLOW)
        self.assertEqual(error.exception.code,'stale_request')
        self.assertEqual(session.pending,{})
    def test_unknown_cleanup_is_retained_across_close_and_admission(self):
        cursor=adapter.Cursor('/unused')
        session=adapter.Session('uncertain','/unused','manual')
        session.process=Peer()
        session.process.close=lambda:(_ for _ in ()).throw(Failure('cleanup_unconfirmed','fixture'))
        cursor.sessions[session.handle]=session
        for _ in range(2):
            with self.assertRaises(Failure) as error:cursor.close({'session':session.handle},Job())
            self.assertEqual(error.exception.code,'cleanup_unconfirmed')
        with patch.object(adapter,'resolve_executable',return_value='/unused'),patch.object(adapter.Session,'open',return_value={}):
            cursor.open({},Job())
        self.assertIn(session.handle,cursor.sessions)
    def test_serialized_text_and_events_fit_result_without_losing_completion(self):
        session=adapter.Session('handle','/unused','manual')
        def request(*_):
            session.text=bytearray(b'\x01'*131072)
            for _ in range(10):session.events.append({'text':'x'*60000})
            return {'stopReason':'end_turn','metadata':'x'*120000}
        session.request=request
        result=session.prompt({'prompt':'fixture'},Job())
        self.assertLessEqual(len(encoded(result)),524288)
        self.assertTrue(result['text_truncated'])
        self.assertEqual(result['stop_reason'],'end_turn')
        self.assertEqual(len(result['native_result']['metadata']),120000)
    def test_ambiguous_response_cannot_settle_operation(self):
        session,peer,thread,result=self.begin()
        peer.frames.put({'jsonrpc':'2.0','id':session.sequence,'result':{},'error':{'code':-1,'message':'ambiguous'}})
        thread.join(1)
        self.assertIsInstance(result[0],Failure)
        self.assertEqual(result[0].code,'invalid_vendor_response')

if __name__=='__main__':unittest.main()
