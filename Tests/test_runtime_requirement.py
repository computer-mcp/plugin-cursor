"""The public entrypoint must reject old runtimes before loading the adapter."""
from pathlib import Path
import subprocess
import sys
import unittest


class RuntimeRequirementTests(unittest.TestCase):
    def test_unsupported_interpreter_exits_with_actionable_diagnostic(self):
        entry = next((Path(__file__).resolve().parent.parent / 'bin').glob('*-mcp-adapter'))
        script = "import sys,runpy;sys.version_info=(3,12,99);runpy.run_path(sys.argv[1],run_name='__main__')"
        result = subprocess.run([sys.executable, '-c', script, str(entry)],
                                capture_output=True, input=b'', timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'Python 3.13+', result.stderr)
        self.assertEqual(result.stdout, b'')


if __name__ == '__main__':
    unittest.main()
