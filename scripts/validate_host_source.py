"""Run the deterministic Cursor companion against explicit clean source commits.

The driver exports both commits into an ignored run directory. It never edits
input checkouts, contacts an installed App or launches the vendor's executable.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import time

FIXTURE = "CursorSourceIntegrationTests.swift"
CASES = {
    "package", "declarations", "dual-authority", "cli", "mcp", "skills",
    "worktree", "container", "boundaries", "continuation", "cancellation",
    "scoped-revocation", "host-removal", "cleanup",
}
VENDOR_CASES = {
    "dual-authority", "cold-warm-ownership", "seatbelt-boundaries", "ordinary-cancel",
    "native-result-races", "pending-answer-cancel", "forced-stop-isolation", "startup-cancellation",
    "lost-start-reply", "pending-start-closure", "cleanup",
}
SELECTORS = {
    "source": "CursorSourceIntegrationTests/sourceConsumer",
    "vendor-stop": "CursorSourceIntegrationTests/registeredVendorStop",
}
INPUTS = (
    "computer-mcp-plugin.toml", "tests/Fixtures/" + FIXTURE + ".txt",
    "tests/Fixtures/vendor.py", "tests/Fixtures/vendor_start_transport.py",
    "scripts/validate_host_source.py",
    "bin/cursor-mcp-adapter", "bin/plugin_runtime.py", "cli-tree.json",
    "bin/cursor_vendor_execution.py", "cursor-vendor-execution.json", "scripts/build_package.py",
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def revision(value):
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise argparse.ArgumentTypeError("Use a full lowercase 40-character commit SHA")
    return value


def absolute(value):
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("Use an absolute path")
    return path.resolve()


def git(root, *arguments):
    return subprocess.check_output(
        ["git", "-C", str(root), *arguments], text=True,
        stderr=subprocess.PIPE, timeout=15).strip()


def verify_source(root, sha):
    revision(sha)
    if not root.is_dir() or git(root, "rev-parse", "--show-toplevel") != str(root):
        raise ValueError("Source must be an existing repository root")
    if git(root, "rev-parse", "HEAD") != sha:
        raise ValueError("Source HEAD differs from its supplied commit")
    if git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("Source checkout must be clean, including untracked files")


def contains(parent, child):
    return child == parent or parent in child.parents


def validate_locations(host, plugin, output):
    if contains(host, plugin) or contains(plugin, host):
        raise ValueError("Host and plugin must be separate, non-nested source checkouts")
    owned = plugin / ".agent/host6"
    if not contains(owned, output) or output == owned:
        raise ValueError("Output must be a new run directory under plugin .agent/host6")
    if contains(host, output):
        raise ValueError("Output must be outside the host source")
    if not git(plugin, "check-ignore", str(output / "receipt.json")):
        raise ValueError("Run output must be ignored")
    if output.exists() or output.is_symlink():
        raise ValueError("Output must be a new directory")


def run_process(command, cwd, environment, log, timeout):
    """Bound execution/output and reap the driver-owned command group on every exit."""
    with log.open("wb") as stream:
        process = subprocess.Popen(
            command, cwd=cwd, env=environment, stdout=stream,
            stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic() + timeout
        failure = None
        try:
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Command exceeded its deadline")
                if log.stat().st_size > 32 * 1024 * 1024:
                    raise RuntimeError("Command exceeded its 32 MiB output bound")
                time.sleep(0.05)
            if process.returncode:
                raise RuntimeError(f"Command exited {process.returncode}; inspect {log}")
        except BaseException as error:
            failure = error
        finally:
            try:
                try:
                    os.killpg(process.pid, 0)
                except ProcessLookupError:
                    pass
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                    if failure is None:
                        failure = RuntimeError("Command left descendants; its group was terminated")
            finally:
                process.wait(timeout=5)
        if failure:
            raise failure
        if log.stat().st_size > 32 * 1024 * 1024:
            raise RuntimeError("Command exceeded its 32 MiB output bound")


def extract_source(archive, destination):
    """Export only bounded regular files and directories into a fresh directory."""
    if archive.stat().st_size > 128 * 1024 * 1024:
        raise ValueError("Source archive exceeds 128 MiB")
    destination.mkdir()
    total = 0
    with tarfile.open(archive, "r:") as source:
        for index, entry in enumerate(source):
            target = destination / entry.name
            if (index >= 20000 or entry.name.startswith("/")
                    or ".." in Path(entry.name).parts or not contains(destination, target)
                    or not (entry.isdir() or entry.isfile())):
                raise ValueError("Unsafe or oversized source archive")
            total += entry.size
            if total > 128 * 1024 * 1024:
                raise ValueError("Expanded source exceeds 128 MiB")
            if entry.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(entry) as incoming, target.open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing)
                target.chmod(0o755 if entry.mode & 0o111 else 0o644)


def export_source(root, sha, destination, environment, output):
    archive = output / (destination.name + ".tar")
    try:
        run_process(
            ["git", "-C", str(root), "archive", "--format=tar", "--output", str(archive), sha],
            output, environment, output / (destination.name + "-export.log"), 30)
        extract_source(archive, destination)
    finally:
        archive.unlink(missing_ok=True)


def validate_evidence(observed, run_id, expected_cases=CASES):
    cases = observed.get("cases")
    if (observed.get("kind") != "deterministic" or observed.get("run_id") != run_id
            or type(observed.get("tests_executed")) is not int or observed["tests_executed"] < 1
            or not isinstance(cases, list) or len(cases) != len(expected_cases)
            or any(not isinstance(case, str) for case in cases) or set(cases) != expected_cases):
        raise ValueError("Consumer case evidence is incomplete, duplicated or stale")


def validate_acquisitions(rows):
    if not isinstance(rows, list) or len(rows) != 2 or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Host did not record the cold and warm Cursor acquisitions")

    def root(row, phase):
        pid = row.get(f"{phase}_pid")
        identity = row.get(f"{phase}_identity")
        if (type(pid) is not int or pid <= 0 or not isinstance(identity, str)
                or not re.fullmatch(r"[1-9][0-9]{0,19}", identity)):
            raise ValueError("Cursor acquisition is missing a durable process identity")
        return pid, identity

    cold, warm = rows
    adapter = root(cold, "adapter")
    if root(warm, "adapter") != adapter or warm.get("adapter_child") != cold.get("adapter_child"):
        raise ValueError("Warm Cursor acquisition did not reuse the cold adapter")
    roots = [adapter]
    ids = [cold.get("adapter_child")]
    for row in rows:
        proofs = row.get("authorization_ids")
        if not isinstance(proofs, list) or len(proofs) != 2:
            raise ValueError("Cursor acquisition is missing caller or provider authority")
        ids.extend([row.get("execution"), *proofs])
        for phase in ("probe", "workload"):
            roots.append(root(row, phase))
            ids.append(row.get(f"{phase}_child"))
    if (len(set(roots)) != len(roots)
            or any(not isinstance(value, str) or not re.fullmatch(
                r"[0-9A-F]{8}-(?:[0-9A-F]{4}-){3}[0-9A-F]{12}", value) for value in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("Cursor acquisitions reused a launch, child, execution, or authorization")


def validate_startup_cancellation(evidence):
    if not isinstance(evidence, dict):
        raise ValueError("Host did not record startup cancellation")
    control = evidence.get("control")
    cancelled = evidence.get("cancelled")
    if not isinstance(control, dict) or not isinstance(cancelled, dict):
        raise ValueError("Host did not record both startup trials")
    phase_ids = [trial.get(key) for trial in (control, cancelled)
                 for key in ("acquisition", "execution", "probe", "workload")]
    if (any(not isinstance(value, str) or not re.fullmatch(
                r"[0-9A-F]{8}-(?:[0-9A-F]{4}-){3}[0-9A-F]{12}", value)
            for value in phase_ids) or len(set(phase_ids)) != len(phase_ids)):
        raise ValueError("Startup phase identities are missing or shared")
    pids = [evidence.get("adapter_pid"), evidence.get("sibling_pid"),
            control.get("probe_pid"), control.get("workload_pid"), cancelled.get("probe_pid")]
    if (any(type(pid) is not int or pid <= 0 for pid in pids) or len(set(pids)) != len(pids)
            or any(trial.get("probe_state") != "retired" for trial in (control, cancelled))
            or control.get("result") != "opened" or control.get("workload_starts") != 1
            or cancelled.get("result") != "cancelled" or cancelled.get("workload_starts") != 0
            or cancelled.get("workload_state") != "never_dispatched"):
        raise ValueError("Startup cancellation did not prove exact workload sealing")


def validate_start_recovery(lost, closure):
    phases = (("before_dispatch", "never_dispatched", 0), ("after_dispatch", "retired", 1))
    if not isinstance(closure, dict):
        raise ValueError("Host did not record pending connection closure")
    for record in (lost, *(closure.get(key) for key, _, _ in phases)):
        if not isinstance(record, dict):
            raise ValueError("Host did not record startup recovery")
        identities = [record.get(key) for key in ("acquisition", "execution", "probe", "workload")]
        if (any(not isinstance(value, str) or not re.fullmatch(
                    r"[0-9A-F]{8}-(?:[0-9A-F]{4}-){3}[0-9A-F]{12}", value)
                for value in identities) or len(set(identities)) != len(identities)
                or not all(isinstance(record.get(key), str) and record[key]
                           for key in ("request_id", "downstream_request_id"))):
            raise ValueError("Startup recovery identities are incomplete")
    pids = [lost.get("workload_pid"), lost.get("sibling_pid")]
    if (any(type(pid) is not int or pid <= 0 for pid in pids) or pids[0] == pids[1]
            or lost.get("retired_at_lookup") is not False
            or lost.get("retired_after_cleanup") is not True
            or type(lost.get("workload_starts")) is not int or lost["workload_starts"] != 1
            or lost.get("workload_state") != "retired" or lost.get("result") != "timeout"):
        raise ValueError("Lost start reply did not reconcile exactly one retired workload")
    for key, workload_state, workload_starts in phases:
        record = closure[key]
        if (type(record.get("workload_starts")) is not int or record["workload_starts"] != workload_starts
                or record.get("probe_state") != "retired" or record.get("workload_state") != workload_state
                or record.get("result") != "outcome_unknown" or record.get("cleanup") != "confirmed"):
            raise ValueError(f"Private channel closure did not confirm cleanup {key}")


def run(args):
    validate_locations(args.host_source, args.plugin_source, args.output)
    verify_source(args.host_source, args.host_sha)
    verify_source(args.plugin_source, args.plugin_sha)
    suite = args.suite
    before = {name: digest(args.plugin_source / name) for name in INPUTS}
    args.output.mkdir(parents=True)
    output = args.output
    host = output / "host-source"
    plugin = output / "plugin-source"
    evidence = output / "cases.json"
    run_id = os.urandom(16).hex()
    result = {
        "host_sha": args.host_sha, "plugin_sha": args.plugin_sha, "suite": suite,
        "inputs_sha256": before, "run_id": run_id, "kind": "deterministic",
        "native_verified": False, "python": sys.executable, "python_sha256": digest(Path(sys.executable)), "status": "failed", "cleanup": "pending",
    }
    environment = dict(os.environ)
    # No implicit Cursor source, target or evidence selection from the parent session.
    for key in list(environment):
        if key.startswith("COMPUTER_MCP_CURSOR_"):
            del environment[key]
    environment.update({
        "COMPUTER_MCP_CURSOR_PLUGIN": str(plugin),
        "COMPUTER_MCP_CURSOR_CASES": str(evidence),
        "COMPUTER_MCP_CURSOR_RUN_ID": run_id,
        "COMPUTER_MCP_CURSOR_PYTHON": sys.executable,
    })
    try:
        export_source(args.host_source, args.host_sha, host, environment, output)
        export_source(args.plugin_source, args.plugin_sha, plugin, environment, output)
        for name, expected in before.items():
            if digest(plugin / name) != expected:
                raise ValueError("Exported plugin differs from its source commit")
        target = host / "Tests/ComputerMCPMacOSTests" / FIXTURE
        if not target.parent.is_dir():
            raise ValueError("Host does not provide the required macOS test target")
        with target.open("xb") as destination:
            destination.write((plugin / INPUTS[1]).read_bytes())
        if suite == "vendor-stop":
            packages = output / "package"
            run_process(
                [sys.executable, "-B", str(plugin / "scripts/build_package.py"), str(packages)],
                plugin, environment, output / "package-build.log", 30)
            archive = packages / "cursor.zip"
            result["archive_sha256"] = digest(archive)
            environment["COMPUTER_MCP_CURSOR_ARCHIVE"] = str(archive)
            environment["COMPUTER_MCP_CURSOR_ARCHIVE_SHA256"] = result["archive_sha256"]
        run_process(
            ["/usr/bin/swift", "test", "--build-system", "native", "--scratch-path",
             str(output / "build"), "--no-parallel", "--filter", SELECTORS[suite]],
            host, environment, output / "swift-test.log", args.timeout)
        if evidence.stat().st_size > 65536:
            raise ValueError("Case evidence exceeds its bound")
        observed = json.loads(evidence.read_text())
        validate_evidence(observed, run_id, VENDOR_CASES if suite == "vendor-stop" else CASES)
        if suite == "vendor-stop":
            acquisitions = observed.get("acquisitions")
            validate_acquisitions(acquisitions)
            result["acquisitions"] = acquisitions
            result["startup_cancellation"] = observed.get("startup_cancellation")
            validate_startup_cancellation(result["startup_cancellation"])
            result["lost_start_reply"] = observed.get("lost_start_reply")
            result["pending_start_closure"] = observed.get("pending_start_closure")
            validate_start_recovery(result["lost_start_reply"], result["pending_start_closure"])
        if {name: digest(args.plugin_source / name) for name in INPUTS} != before:
            raise ValueError("Source input changed during verification")
        result["cases"] = sorted(observed["cases"])
        result["tests_executed"] = observed["tests_executed"]
        result["status"] = "passed"
    finally:
        # Logs/case evidence survive; all exported sources and build output are owned here.
        for path in (host, plugin, output / "build", output / "package"):
            if path.is_symlink():
                raise RuntimeError("Run-owned cleanup target was replaced by a symlink")
            if path.exists():
                shutil.rmtree(path)
        result["cleanup"] = ("confirmed" if result["status"] == "passed"
                             else "exports-removed; fixture-process-cleanup-unverified")
        try:
            verify_source(args.host_source, args.host_sha)
            verify_source(args.plugin_source, args.plugin_sha)
        except BaseException:
            result["status"] = "failed"
            raise
        finally:
            (output / "receipt.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"receipt": str(output / "receipt.json"), "status": "passed"}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-source", required=True, type=absolute)
    parser.add_argument("--host-sha", required=True, type=revision)
    parser.add_argument("--plugin-source", required=True, type=absolute)
    parser.add_argument("--plugin-sha", required=True, type=revision)
    parser.add_argument("--output", required=True, type=absolute)
    parser.add_argument("--suite", choices=SELECTORS, default="source")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 1800:
        parser.error("--timeout must be between 1 and 1800 seconds")
    try:
        run(args)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Source verification failed: {error}\n")


if __name__ == "__main__":
    main()
