"""Own-process cleanup tests, including abrupt adapter loss and exited leaders."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest
from support import Client, ROOT, VENDOR, wait_file, wait_stopped

sys.path.insert(0,str(ROOT/'bin'))
from plugin_runtime import EventBuffer


class LifecycleTests(unittest.TestCase):
    def scenario(self,termination):
        with tempfile.TemporaryDirectory() as temp:
            marker=Path(temp)/'pids.json'
            client=Client(temp,{'FIXTURE_MARKER':str(marker)})
            try:
                name='cursor.acp.prompt' if VENDOR=='cursor' else 'claude.run'
                client.begin(name,{'prompt':'fork','timeout_seconds':30})
                pids=wait_file(marker)
                if termination=='eof':client.process.stdin.close()
                else:os.kill(client.process.pid,termination)
                client.process.wait(timeout=6)
                wait_stopped(pids)
            finally:client.close()
    def test_eof_retires_vendor_and_descendant(self):self.scenario('eof')
    def test_sigterm_retires_vendor_and_descendant(self):self.scenario(signal.SIGTERM)
    def test_sigkill_parent_loss_is_detected_by_supervisor(self):self.scenario(signal.SIGKILL)
    def test_host_context_is_not_forwarded_to_vendor(self):
        with tempfile.TemporaryDirectory() as temp:
            client=Client(temp,{'COMPUTER_MCP_TEST_PRIVATE':'must-not-inherit'})
            try:
                response=client.call('cursor.acp.prompt' if VENDOR=='cursor' else 'claude.run',{'prompt':'env'})
                value=Client.value(response)
                self.assertFalse(response['result']['isError'],value)
                self.assertEqual(value['text'] if VENDOR=='cursor' else value['result'],'[]')
            finally:client.close()
    def test_version_mismatch_prevents_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            client=Client(temp,{'FIXTURE_WRONG_VERSION':'1'})
            try:
                response=client.call('cursor.acp.prompt' if VENDOR=='cursor' else 'claude.run',{'prompt':'hello'})
                self.assertEqual(Client.value(response)['error']['code'],'incompatible_vendor')
            finally:client.close()
    def test_event_buffer_reports_exact_retention_and_small_pages(self):
        events=EventBuffer(max_events=3,max_bytes=1024)
        for i in range(3):events.append({'index':i})
        first=events.page()
        self.assertFalse(first['has_more']);self.assertFalse(first['missed_events'])
        events.append({'index':3})
        self.assertTrue(events.page()['missed_events'])
        events.append({'text':'x'*2048})
        last=events.page(4)
        self.assertTrue(last['events'][0]['event']['omitted'])
        self.assertLessEqual(events.bytes,1024)

if __name__=='__main__':unittest.main()
