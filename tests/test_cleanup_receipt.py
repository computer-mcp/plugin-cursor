"""A dead supervisor is not itself proof of completed process cleanup."""
import os
import sys
import unittest
from support import ROOT
sys.path.insert(0, str(ROOT / 'bin'))
from plugin_runtime import Failure, Process

class CleanupReceiptTests(unittest.TestCase):
    def check_receipt(self, data):
        read_fd, write_fd = os.pipe()
        try:
            os.write(write_fd, data)
            os.close(write_fd)
            write_fd = None
            Process.confirm_cleanup(read_fd)
        finally:
            os.close(read_fd)
            if write_fd is not None:
                os.close(write_fd)
    def test_positive_confirmation_is_required(self):
        self.check_receipt(b'{"cleanup_confirmed":true}')
    def test_eof_without_confirmation_is_unknown(self):
        with self.assertRaises(Failure) as result:
            self.check_receipt(b'')
        self.assertEqual(result.exception.code, 'cleanup_unconfirmed')
    def test_negative_or_malformed_confirmation_is_unknown(self):
        for data in (b'{"cleanup_confirmed":false}', b'not-json', b'{"cleanup_confirmed":1}'):
            with self.assertRaises(Failure):
                self.check_receipt(data)

if __name__ == '__main__':
    unittest.main()
