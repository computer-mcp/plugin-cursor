"""Validate an exact plugin archive against an unchanged, isolated host binary.

Uses only the host's bounded archive worker. It never
connects to production control sockets, registers a production plugin, loads
production credentials, or invokes a vendor.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parent.parent


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def capture(arguments, cwd, environment, timeout=30):
    result = subprocess.run(arguments, cwd=cwd, env=environment,
                            capture_output=True, timeout=timeout)
    require(result.returncode == 0,
            'Command failed: ' + repr(arguments[:3]) + '\n' + result.stderr.decode(errors='replace')[:4096]
            + '\n' + result.stdout.decode(errors='replace')[:4096])
    return result.stdout


def validate(host, archive, output, expected_host_version):
    host = host.resolve(strict=True)
    archive = archive.resolve(strict=True)
    output.mkdir(parents=True, exist_ok=False)
    manifest = tomllib.loads((ROOT / 'computer-mcp-plugin.toml').read_text())
    vendor = manifest['id']
    host_hash = digest(host)
    archive_hash = digest(archive)
    checks = {}
    with tempfile.TemporaryDirectory(prefix='computer-mcp-plugin-acceptance-') as directory:
        work = Path(directory)
        home = work / 'home'
        home.mkdir()
        environment = {'PATH': os.pathsep.join([str(Path(sys.executable).parent), '/usr/bin', '/bin', '/usr/sbin', '/sbin']),
                       'HOME': str(home), 'TMPDIR': str(work), 'PYTHONDONTWRITEBYTECODE': '1', 'LANG': 'en_US.UTF-8'}
        version = capture([str(host), '--version'], work, environment).decode().strip()
        require(bool(expected_host_version) and version.startswith(expected_host_version + ' '),
                'Host version differs from the explicitly selected acceptance version')
        inputs = work / 'inputs'
        inputs.mkdir()
        (inputs / f'{vendor}.zip').write_bytes(archive.read_bytes())
        index = [{'id': vendor, 'version': manifest['version'], 'archive': f'{vendor}.zip', 'sha256': archive_hash}]
        (inputs / 'index.json').write_text(json.dumps(index))
        receipt = capture([str(host), '_bundle-plugins', '--index', str(inputs / 'index.json'),
                           '--output', str(work / 'packages'), '--architectures', 'arm64'], work, environment, 90)
        (output / 'archive-validation.json').write_bytes(receipt)
        package = work / 'packages' / vendor
        require((package / 'computer-mcp-plugin.toml').read_bytes() == (ROOT / 'computer-mcp-plugin.toml').read_bytes(),
                'Extracted manifest differs from source')
        require((package / 'cli-tree.json').read_bytes() == (ROOT / 'cli-tree.json').read_bytes(),
                'Extracted CLI contract differs from source')
        for path in ('cursor-vendor-execution.json', 'bin/cursor_vendor_execution.py',
                     'bin/plugin_runtime.py', 'bin/cursor-mcp-adapter'):
            require((package / path).read_bytes() == (ROOT / path).read_bytes(),
                    f'Extracted managed execution file differs from source: {path}')
        require(os.access(package / f'bin/{vendor}-mcp-adapter', os.X_OK), 'Host extraction lost executable mode')
        checks['archive_and_manifest'] = 'passed'
        require(not list(package.rglob('*.pyc')) and not list(package.rglob('__pycache__')), 'Archive contains Python cache')

    require(digest(host) == host_hash and digest(archive) == archive_hash, 'Host or archive changed during acceptance')
    report = {'status':'passed', 'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'plugin_id':vendor, 'plugin_version':manifest['version'], 'host_version':version,
              'expected_host_version':expected_host_version,
              'host_sha256':host_hash, 'archive_sha256':archive_hash, 'checks':checks,
              'scope':'host archive worker and package identity only; runtime acceptance uses validate_host_source.py',
              'production_installation':False, 'authenticated_model_execution':False,
              'host_database_or_control_socket_used':False}
    (output / 'acceptance.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True, type=Path)
    parser.add_argument('--expected-host-version', required=True,
                        help='Exact reviewed host release version, for example 1.3.0')
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    validate(args.host, args.archive, args.output, args.expected_host_version)


if __name__ == '__main__':
    main()
