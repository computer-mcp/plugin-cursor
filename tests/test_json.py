"""Bounded numeric validation must not silently admit nonfinite values."""
import sys
import unittest
from support import ROOT
sys.path.insert(0, str(ROOT / 'bin'))
from plugin_runtime import Failure, decoded, validate

class JSONTests(unittest.TestCase):
    def test_exponent_overflow_is_invalid_json(self):
        with self.assertRaises(ValueError):
            decoded(b'{"value":1e999}')
    def test_large_integer_reports_argument_bounds(self):
        with self.assertRaises(Failure) as result:
            validate(10**1000, {'type':'integer','maximum':100})
        self.assertEqual(result.exception.code,'invalid_arguments')

if __name__ == '__main__':
    unittest.main()
