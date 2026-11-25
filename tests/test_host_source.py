"""Source driver checks do not build a host or execute a native vendor."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('host_source', ROOT / 'scripts/validate_host_source.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


class HostSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / '.agent/host6').mkdir(parents=True, exist_ok=True)

    def test_cli_requires_explicit_sources_and_commits(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/validate_host_source.py'), '--help'], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0)
        for name in ('--host-source', '--plugin-source', '--host-sha', '--plugin-sha', '--output'):
            self.assertIn(name, result.stdout)
        for value in ('master', 'a' * 39, 'A' * 40):
            with self.assertRaises(argparse.ArgumentTypeError): driver.revision(value)

    def test_evidence_must_be_fresh_complete_and_nonzero(self):
        good = {'kind': 'deterministic', 'run_id': 'fresh', 'tests_executed': 1, 'cases': sorted(driver.CASES)}
        driver.validate_evidence(good, 'fresh')
        for patch in ({'tests_executed': 0}, {'tests_executed': True}, {'run_id': 'stale'}, {'cases': []}, {'cases': good['cases'] + good['cases'][:1]}):
            with self.assertRaises(ValueError): driver.validate_evidence(dict(good, **patch), 'fresh')

    def test_source_identity_and_dirt_are_rejected(self):
        sha = 'a' * 40
        with patch.object(driver, 'git', side_effect=[str(ROOT), sha, '']):
            driver.verify_source(ROOT, sha)
        with patch.object(driver, 'git', side_effect=[str(ROOT), 'b' * 40]):
            with self.assertRaises(ValueError): driver.verify_source(ROOT, sha)
        with patch.object(driver, 'git', side_effect=[str(ROOT), sha, '?? untracked']):
            with self.assertRaises(ValueError): driver.verify_source(ROOT, sha)

    def test_only_ignored_run_outputs(self):
        host = Path('/separate/host')
        with self.assertRaises(ValueError): driver.validate_locations(host, ROOT, ROOT / 'output')
        with self.assertRaises(ValueError): driver.validate_locations(ROOT, ROOT, ROOT / '.agent/host6/run')
        driver.validate_locations(host, ROOT, ROOT / '.agent/host6/not-created')

    def test_snapshot_rejects_links_and_path_escape(self):
        for name, kind in (('../escape', tarfile.REGTYPE), ('link', tarfile.SYMTYPE)):
            with tempfile.TemporaryDirectory(dir=ROOT / '.agent/host6') as temp:
                root = Path(temp); archive = root / 'source.tar'
                with tarfile.open(archive, 'w') as tar:
                    item = tarfile.TarInfo(name); item.type = kind; item.linkname = '/tmp/target'; tar.addfile(item)
                with self.assertRaises(ValueError): driver.extract_source(archive, root / 'export')
                self.assertFalse((root / 'escape').exists())

    def test_staged_run_records_pair_and_removes_owned_snapshots(self):
        import shutil
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory(dir=ROOT / '.agent/host6') as temp:
            output = Path(temp) / 'run'
            args = SimpleNamespace(host_source=Path('/separate/host'), plugin_source=ROOT, suite='source',
                                   host_sha='a' * 40, plugin_sha='b' * 40, output=output, timeout=3)
            def export(root, sha, destination, environment, work):
                destination.mkdir()
                if root == args.host_source:
                    (destination / 'Tests/ComputerMCPMacOSTests').mkdir(parents=True)
                else:
                    for name in driver.INPUTS:
                        target = destination / name; target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(ROOT / name, target)
            def execute(command, cwd, environment, log, timeout):
                self.assertEqual(cwd, output / 'host-source')
                self.assertEqual(command[-1], 'CursorSourceIntegrationTests/sourceConsumer')
                self.assertTrue((cwd / 'Tests/ComputerMCPMacOSTests' / driver.FIXTURE).is_file())
                self.assertEqual(environment['COMPUTER_MCP_CURSOR_PLUGIN'], str(output / 'plugin-source'))
                (output / 'build').mkdir()
                Path(environment['COMPUTER_MCP_CURSOR_CASES']).write_text(json.dumps({
                    'kind': 'deterministic', 'run_id': environment['COMPUTER_MCP_CURSOR_RUN_ID'],
                    'tests_executed': 1, 'cases': sorted(driver.CASES)}))
            with patch.object(driver, 'verify_source'), patch.object(driver, 'export_source', side_effect=export), patch.object(driver, 'run_process', side_effect=execute):
                driver.run(args)
            receipt = json.loads((output / 'receipt.json').read_text())
            self.assertEqual(receipt['host_sha'], args.host_sha)
            self.assertEqual(receipt['plugin_sha'], args.plugin_sha)
            self.assertEqual(receipt['status'], 'passed')
            self.assertEqual(receipt['tests_executed'], 1)
            self.assertEqual(receipt['cleanup'], 'confirmed')
            self.assertFalse(receipt['native_verified'])
            for name in ('host-source', 'plugin-source', 'build'): self.assertFalse((output / name).exists())

    def test_bounded_command_failure_and_timeout(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.agent/host6') as temp:
            root = Path(temp); log = root / 'process.log'
            driver.run_process([sys.executable, '-c', 'print("ok")'], root, dict(os.environ), log, 3)
            self.assertEqual(log.read_text(), 'ok\n')
            with self.assertRaises(RuntimeError): driver.run_process([sys.executable, '-c', 'raise SystemExit(7)'], root, dict(os.environ), log, 3)
            with self.assertRaises(TimeoutError): driver.run_process([sys.executable, '-c', 'import time; time.sleep(30)'], root, dict(os.environ), log, .1)

if __name__ == '__main__': unittest.main()
