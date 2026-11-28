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

    def test_acquisition_receipt_requires_durable_distinct_launches(self):
        def identifier(number):
            return f"00000000-0000-0000-0000-{number:012X}"

        def acquisition(offset):
            return {
                "execution": identifier(offset),
                "authorization_ids": [identifier(offset + 1), identifier(offset + 2)],
                "adapter_child": identifier(1), "adapter_pid": 11, "adapter_identity": "101",
                "probe_child": identifier(offset + 3), "probe_pid": 12,
                "probe_identity": str(offset + 100),
                "workload_child": identifier(offset + 4), "workload_pid": offset + 100,
                "workload_identity": str(offset + 200),
            }

        cold, warm = acquisition(10), acquisition(20)
        driver.validate_acquisitions([cold, warm])
        for field, value in (("workload_identity", None), ("adapter_identity", "102"),
                             ("probe_child", cold["probe_child"]),
                             ("probe_identity", cold["probe_identity"])):
            with self.subTest(field=field), self.assertRaises(ValueError):
                driver.validate_acquisitions([cold, dict(warm, **{field: value})])

    def test_native_stops_require_one_turn_per_addressed_request(self):
        owners = [{"workload_pid": 10, "workload_identity": "11"},
                  {"workload_pid": 20, "workload_identity": "21"}]
        stops = [
            {"prompt": label, "peer_pid": 10 if index < 4 else 20,
             "peer_identity": "11" if index < 4 else "21", "acp_id": 10 + index,
             "stop_request_id": f"stop-{index}", "prompt_request_id": f"prompt-{index}"}
            for index, label in enumerate(("slow", "permission-on-cancel", "error-on-cancel",
                                           "ignore-cancel", "complete-on-cancel"))
        ]
        stops[-1]["downstream_request_id"] = "retained-invocation"
        driver.validate_native_stops(stops, owners)
        for changes in ({"acp_id": 10}, {"stop_request_id": "stop-0"}, {"peer_pid": 20}):
            with self.assertRaises(ValueError):
                driver.validate_native_stops([stops[0], dict(stops[1], **changes), *stops[2:]], owners)
        for invalid in ([stops[0], *stops], [stops[0], *stops[2:]]):
            with self.assertRaises(ValueError):
                driver.validate_native_stops(invalid, owners)

    def test_source_identity_and_dirt_are_rejected(self):
        sha = 'a' * 40
        with patch.object(driver, 'git', side_effect=[str(ROOT), sha, '']):
            driver.verify_source(ROOT, sha)
        with patch.object(driver, 'git', side_effect=[str(ROOT), 'b' * 40]):
            with self.assertRaises(ValueError): driver.verify_source(ROOT, sha)
        with patch.object(driver, 'git', side_effect=[str(ROOT), sha, '?? untracked']):
            with self.assertRaises(ValueError): driver.verify_source(ROOT, sha)

    def test_only_fresh_external_run_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            host = root / 'sources' / 'host'
            plugin = root / 'sources' / 'plugin'
            host.mkdir(parents=True)
            plugin.mkdir()
            output = root / 'evidence' / 'run'
            self.assertEqual(driver.validate_locations(host, plugin, output), output)
            self.assertFalse(output.parent.exists())

            existing = root / 'existing'
            existing.mkdir()
            file = root / 'file'
            file.touch()
            host_alias = root / 'host-alias'
            host_alias.symlink_to(host, target_is_directory=True)
            dangling = root / 'dangling'
            dangling.symlink_to(output)
            for invalid in (Path('relative'), host, plugin, host / 'run', plugin / 'run',
                            host.parent, root, existing, file, host_alias / 'run', dangling):
                with self.subTest(output=invalid), self.assertRaises(ValueError):
                    driver.validate_locations(host, plugin, invalid)
            for first, second in ((host, host), (host, host / 'nested'), (plugin / 'nested', plugin)):
                with self.subTest(host=first, plugin=second), self.assertRaises(ValueError):
                    driver.validate_locations(first, second, output)

    def test_case_aliases_follow_filesystem_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            sources = root / 'sources'
            host = sources / 'host'
            plugin = sources / 'plugin'
            host.mkdir(parents=True)
            plugin.mkdir()
            host_alias = sources / 'HOST'
            plugin_alias = sources / 'PLUGIN'
            candidates = (host_alias / 'fresh' / 'run', plugin_alias / 'fresh' / 'run')

            if host_alias.exists():
                self.assertTrue(host_alias.samefile(host))
                self.assertTrue(plugin_alias.samefile(plugin))
                for output in (*candidates, root / 'SOURCES'):
                    with self.subTest(output=output), self.assertRaisesRegex(ValueError, 'outside both'):
                        driver.validate_locations(host, plugin, output)
                with self.assertRaisesRegex(ValueError, 'separate, non-nested'):
                    driver.validate_locations(host, host_alias, root / 'evidence')
                result = subprocess.run(
                    [sys.executable, str(ROOT / 'scripts/validate_host_source.py'),
                     '--host-source', str(host), '--host-sha', 'a' * 40,
                     '--plugin-source', str(plugin), '--plugin-sha', 'b' * 40,
                     '--output', str(candidates[0])],
                    capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn('Source verification failed: Output must be outside both', result.stderr)
            else:
                for output in candidates:
                    with self.subTest(output=output):
                        self.assertEqual(driver.validate_locations(host, plugin, output), output)

            for output in candidates:
                self.assertFalse(output.parent.exists())

    def test_snapshot_rejects_links_and_path_escape(self):
        for name, kind in (('../escape', tarfile.REGTYPE), ('link', tarfile.SYMTYPE)):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp); archive = root / 'source.tar'
                with tarfile.open(archive, 'w') as tar:
                    item = tarfile.TarInfo(name); item.type = kind; item.linkname = '/tmp/target'; tar.addfile(item)
                with self.assertRaises(ValueError): driver.extract_source(archive, root / 'export')
                self.assertFalse((root / 'escape').exists())

    def test_staged_run_records_pair_and_removes_owned_snapshots(self):
        import shutil
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            output = root / 'run'
            args = SimpleNamespace(host_source=root / 'host', plugin_source=ROOT, suite='source',
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
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); log = root / 'process.log'
            driver.run_process([sys.executable, '-c', 'print("ok")'], root, dict(os.environ), log, 3)
            self.assertEqual(log.read_text(), 'ok\n')
            with self.assertRaises(RuntimeError): driver.run_process([sys.executable, '-c', 'raise SystemExit(7)'], root, dict(os.environ), log, 3)
            with self.assertRaises(TimeoutError): driver.run_process([sys.executable, '-c', 'import time; time.sleep(30)'], root, dict(os.environ), log, .1)

if __name__ == '__main__': unittest.main()
