"""Verify the installed CLI baseline without login, model calls or updates."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import datetime
import tomllib
import re

ROOT=Path(__file__).resolve().parent.parent

def main():
    manifest=tomllib.loads((ROOT/'computer-mcp-plugin.toml').read_text())
    tree=json.loads((ROOT/'cli-tree.json').read_text())
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    vendor='agent' if manifest['id']=='cursor' else 'claude'
    executable=args.executable or shutil.which(vendor)
    if not executable:raise SystemExit(f'Install {vendor} separately or supply --executable')
    expected=next(x['stdout'] for x in tree['executable_checks'] if x['args']==['--version'])
    version=subprocess.run([executable,'--version'],capture_output=True,timeout=10,check=True).stdout
    if version!=expected.encode():raise SystemExit('Installed vendor version differs from the declared baseline')
    help_bytes=subprocess.run([executable,'--help'],capture_output=True,timeout=10,check=True).stdout
    help_text=help_bytes.decode()
    flags=set()
    for command in tree['commands']:
        for token in command.get('argv',[]):
            if 'flag' in token:
                flags.add(token['flag'])
            if token.get('kind') == 'literal':
                value = token.get('value', '')
                if value.startswith('-') and value != '--':
                    flags.add(value.split('=', 1)[0])
    if vendor == 'claude':
        flags.update(['--verbose', '--include-partial-messages'])
    flags=sorted(flags)
    missing=[flag for flag in flags if re.search(r'(?<![-\w])'+re.escape(flag)+r'(?![-\w])',help_text) is None]
    if missing:raise SystemExit('Native help lacks declared flags: '+', '.join(missing))
    extra={}
    if vendor=='agent':
        acp=subprocess.run([executable,'acp','--help'],capture_output=True,timeout=10,check=True).stdout
        if b'Agent Client Protocol' not in acp:raise SystemExit('Native ACP entrypoint is unavailable')
        extra['acp_help_sha256']=hashlib.sha256(acp).hexdigest()
    report={'status':'passed','scope':'native version/help only; no model or login','plugin_id':manifest['id'],'plugin_version':manifest['version'],'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'vendor_version':version.decode().strip(),'help_sha256':hashlib.sha256(help_bytes).hexdigest(),'tree_sha256':hashlib.sha256((ROOT/'cli-tree.json').read_bytes()).hexdigest(),'checked_flags':flags,**extra}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,sort_keys=True))

if __name__=='__main__':main()
