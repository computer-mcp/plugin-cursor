"""Validate an exact plugin archive against an unchanged, isolated host binary.

Uses the host's bounded archive worker and standalone MCP runtime. It never
connects to production control sockets, registers a production plugin, loads
production credentials, or invokes a real model. Runtime calls use fixtures.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'Tests'))
from support import Client


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


def checked(client, name, arguments=None):
    response = client.call(name, arguments or {}, timeout=20)
    require('error' not in response and not response['result'].get('isError'),
            'Tool failed: ' + name + '\n' + json.dumps(response)[:8192])
    return Client.value(response)


def wait_for(callback, predicate, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = callback()
        if predicate(value):
            return value
        time.sleep(.03)
    raise AssertionError('Isolated execution did not reach its postcondition')


def configuration(package, workspace, cli_fixture, acp_fixture, vendor, readonly=False):
    quote = json.dumps
    return f'''schema_version = 1
[server]
name = "plugin-contract-validation"
[runtime]
caller = "local-mcp"
profile = "validation"
workspace_id = "primary"
[policy]
default_timeout_ms = 15000
max_output_bytes = 1048576
shell_enabled = true
[[profiles]]
id = "validation"
mode = "{'read-only' if readonly else 'local-full-access'}"
confirmation_policy = "never"
capabilities = ["*"]
workspaces = ["primary"]
allowed_callers = ["local-mcp"]
full_shell_enabled = {'false' if readonly else 'true'}
[[workspaces]]
id = "primary"
display_name = "Isolated fixture workspace"
path = {quote(str(workspace))}
[[cli.commands]]
id = "fixture-cli"
executable = {quote(str(cli_fixture))}
allow_any_args = false
tree = {{ kind = "file", path = {quote(str(package / 'cli-tree.json'))} }}
[[mcp.servers]]
id = "fixture-adapter"
transport = "stdio"
command = {quote(str(package / f'bin/{vendor}-mcp-adapter'))}
args = ["--executable", {quote(str(acp_fixture))}]
exposure = "reexport"
prefix = ""
allow_any_tool = true
capabilities = ["tools"]
startup_timeout_ms = 10000
request_timeout_ms = 20000
[skills]
enabled = true
[[skills.roots]]
id = "fixture-skills"
path = {quote(str(package / 'skills'))}
[builtin]
enabled = []
'''


def validate(host, archive, output):
    host = host.resolve(strict=True)
    archive = archive.resolve(strict=True)
    output.mkdir(parents=True, exist_ok=False)
    manifest = tomllib.loads((ROOT / 'computer-mcp-plugin.toml').read_text())
    vendor = manifest['id']
    tree = json.loads((ROOT / 'cli-tree.json').read_text())
    expected_version = next(c['stdout'] for c in tree['executable_checks'] if c['args'] == ['--version'])
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
        require(version.startswith('1.2.2 '), 'This validator targets Computer MCP 1.2.2; review another host before use')
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
        require(os.access(package / f'bin/{vendor}-mcp-adapter', os.X_OK), 'Host extraction lost executable mode')
        checks['archive_and_manifest'] = 'passed'
        require(not list(package.rglob('*.pyc')) and not list(package.rglob('__pycache__')), 'Archive contains Python cache')

        workspace = work / 'workspace'
        workspace.mkdir()
        version_file = work / 'version.txt'
        version_file.write_text(expected_version)
        cli_fixture = work / 'native-cli-fixture'
        cli_fixture.write_text('#!' + sys.executable + '\nimport json,sys\nfrom pathlib import Path\n'
                               + 'if sys.argv[1:]==["--version"]:\n    print(Path(' + repr(str(version_file)) + ').read_text(),end="")\n'
                               + 'else:\n    print(json.dumps({"argv":sys.argv[1:],"stdin":sys.stdin.read()}))\n')
        cli_fixture.chmod(0o755)
        config = work / 'gateway.toml'
        config.write_text(configuration(package, workspace, cli_fixture, ROOT / 'Tests/Fixtures/vendor.py', vendor))
        checked_config = capture([str(host), 'config', 'validate', '--config', str(config)], work, environment)
        (output / 'configuration-validation.txt').write_bytes(checked_config)
        client = Client(str(workspace), environment, [str(host), 'serve', 'stdio', '--config', str(config)])
        try:
            catalog = client.request('tools/list')['result']['tools']
            (output / 'catalog.json').write_text(json.dumps(catalog, indent=2)+'\n')
            projected = [tool for tool in catalog if tool.get('_meta', {}).get('cli', {}).get('command') == 'print']
            require(len(projected) == 1, 'Expected one real host-projected print tool')
            native_names = [tool['name'] for tool in catalog if tool['name'].startswith(vendor + '.')]
            require(len(native_names) == (12 if vendor == 'cursor' else 6), 'Adapter catalog missing required tools')
            checks['catalog'] = {'status':'passed', 'cli_tools':len(projected), 'mcp_tools':len(native_names)}
            prompt = "--leading 'quotes' 中文\nnot-a-shell-command"
            arguments = {'prompt': prompt}
            if vendor == 'claude':
                arguments['permission_mode'] = 'plan'
            result = checked(client, projected[0]['name'], arguments)
            argv = result['data']['argv']
            require(argv[-2:] == ['--', prompt], 'Host did not preserve exact argv argument boundaries')
            require(result['exit_code'] == 0, 'CLI result did not capture exit status')
            checks['cli_argv_and_json'] = 'passed'
            invalid = client.call(projected[0]['name'], dict(arguments, unknown_argument=True))
            require('error' in invalid or invalid['result'].get('isError'), 'Unknown CLI arguments were accepted')
            version_file.write_text('incompatible-fixture-version\n')
            mismatch = client.call(projected[0]['name'], arguments)
            require('error' in mismatch or mismatch['result'].get('isError'), 'Incompatible CLI version was executed')
            version_file.write_text(expected_version)
            bypass = client.call('cli.exec', {'id':'fixture-cli', 'argv':['--help']})
            require('error' in bypass or bypass['result'].get('isError'), 'Raw execution bypassed the CLI tree')
            checks['cli_negative_contracts'] = 'passed'

            if vendor == 'cursor':
                session = checked(client, 'cursor.acp.session.open', {'permission_policy':'manual'})['session']
                run = checked(client, 'cursor.acp.session.prompt.start', {'session':session,'prompt':'permission'})['prompt_id']
                pending = wait_for(lambda: checked(client, 'cursor.acp.requests.list', {'session':session}), lambda v: bool(v['requests']))['requests'][0]
                checked(client, 'cursor.acp.requests.respond', {'session':session,'request_id':pending['request_id'],
                                                              'response':{'outcome':{'outcome':'selected','optionId':'opaque-no'}}})
                completed = wait_for(lambda: checked(client, 'cursor.acp.session.prompt.result', {'session':session,'prompt_id':run}), lambda v:v.get('completed'))
                require(not completed.get('is_error'), 'Background ACP fixture failed')
                checked(client, 'cursor.acp.events.read', {'session':session,'max_bytes':2048})
                checked(client, 'cursor.acp.session.close', {'session':session})
                require(not checked(client, 'cursor.acp.session.list')['sessions'], 'Closed ACP session remains live')
            else:
                run = checked(client, 'claude.run.start', {'prompt':'hello','permission_mode':'plan'})['run_id']
                completed = wait_for(lambda: checked(client, 'claude.run.result', {'run_id':run}), lambda v:v.get('completed'))
                require(completed['result'] == 'hello', 'Native final result was not preserved')
                checked(client, 'claude.run.events', {'run_id':run,'max_bytes':2048})
                invalid = client.call('claude.run', {'prompt':'not-executed','permission_mode':'bypassPermissions'})
                require(invalid['result'].get('isError'), 'Bypass mode was admitted')
            checks['mcp_execution_and_events'] = 'passed'
        finally:
            client.close()
        checks['standalone_shutdown'] = 'passed'
        config.write_text(configuration(package, workspace, cli_fixture, ROOT / 'Tests/Fixtures/vendor.py', vendor, readonly=True))
        client = Client(str(workspace), environment, [str(host), 'serve', 'stdio', '--config', str(config)])
        try:
            readonly_tools = client.request('tools/list')['result']['tools']
            require(not any(tool.get('_meta',{}).get('cli') for tool in readonly_tools), 'Read-only profile exposed arbitrary CLI execution')
            require(not any(tool['name'].startswith(vendor+'.') for tool in readonly_tools), 'Read-only profile exposed vendor execution')
        finally:
            client.close()
        checks['read_only_profile'] = 'passed'
    require(digest(host) == host_hash and digest(archive) == archive_hash, 'Host or archive changed during acceptance')
    report = {'status':'passed', 'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'plugin_id':vendor, 'plugin_version':manifest['version'], 'host_version':version,
              'host_sha256':host_hash, 'archive_sha256':archive_hash, 'checks':checks,
              'scope':'host archive validation and ordinary standalone registrations with inert vendor fixtures',
              'production_installation':False, 'authenticated_model_execution':False,
              'host_database_or_control_socket_used':False}
    (output / 'acceptance.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True, type=Path)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    validate(args.host, args.archive, args.output)


if __name__ == '__main__':
    main()
