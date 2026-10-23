"""Completion semantics regressions without invoking a vendor or model."""
import importlib.machinery
import importlib.util
import sys
import unittest
from support import ROOT, VENDOR

sys.path.insert(0, str(ROOT / 'bin'))
from plugin_runtime import Failure, Job

loader = importlib.machinery.SourceFileLoader('completion_adapter', str(ROOT / f'bin/{VENDOR}-mcp-adapter'))
spec = importlib.util.spec_from_loader(loader.name, loader)
adapter = importlib.util.module_from_spec(spec)
loader.exec_module(adapter)


class CompletionTests(unittest.TestCase):
    def test_reserved_prompt_does_not_erase_a_pending_cancellation(self):
        session = adapter.Session('local-handle', '/unused', 'reject-once')
        session.vendor_id = 'native-session'
        session.busy = True
        session.cancelled.set()
        def request(*args):
            self.assertTrue(session.cancelled.is_set())
            return {'stopReason': 'cancelled', 'cancelled': True}
        session.request = request
        self.assertTrue(session.prompt({'prompt': 'not-executed'}, Job(), reserved=True)['is_error'])


    def test_missing_stop_reason_is_not_success(self):
        session = adapter.Session('local-handle', '/unused', 'reject-once')
        session.request = lambda *args: {}
        with self.assertRaises(Failure) as context:
            session.prompt({'prompt': 'not-executed'}, Job())
        self.assertEqual(context.exception.code, 'invalid_vendor_response')


    def test_native_cancelled_result_is_not_reported_successful(self):
        session = adapter.Session('local-handle', '/unused', 'reject-once')
        session.request = lambda *args: {'stopReason': 'cancelled', 'usage': {'tokens': 0}}
        value = session.prompt({'prompt': 'not-executed'}, Job())
        self.assertTrue(value['is_error'])
        self.assertEqual(value['native_result']['usage'], {'tokens': 0})



    def test_permission_id_cannot_override_its_declared_kind(self):
        request = {'options':[{'optionId':'reject-once','kind':'allow_always'}]}
        self.assertEqual(adapter.permission_choice(request,'reject-once'), {'outcome':{'outcome':'cancelled'}})

if __name__ == '__main__':
    unittest.main()
