"""Probe native ACP initialization only: no authentication, session or model call."""
import argparse
import datetime
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'bin'))
from plugin_runtime import Job, Process, decoded, load_package, resolve_executable, verify_version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    _, tree = load_package(ROOT / 'bin/cursor-mcp-adapter')
    executable = resolve_executable(args.executable, 'CURSOR_AGENT_EXECUTABLE', 'agent')
    verify_version(executable, tree, Job(), os.getcwd())
    process = Process([executable, 'acp'], os.getcwd())
    deadline = time.monotonic()+30
    response = None
    try:
        process.send({'jsonrpc':'2.0','id':1,'method':'initialize',
                      'params':{'protocolVersion':1,'clientCapabilities':{'fs':{'readTextFile':False,'writeTextFile':False},'terminal':False},
                                'clientInfo':{'name':'computer-mcp-plugin-contract-probe','version':'1'}}}, deadline)
        for _ in range(32):
            raw = process.read(deadline)
            if raw is None:
                raise RuntimeError('ACP closed before initialization')
            message = decoded(raw)
            if isinstance(message,dict) and message.get('id') == 1:
                response = message
                break
        if not response or response.get('result',{}).get('protocolVersion') != 1:
            raise RuntimeError('ACP protocol 1 was not negotiated')
    finally:
        process.close()
    report = {'status':'passed','observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'scope':'native ACP initialize only; no authenticate, session, prompt or model call',
              'response':response,'cleanup':'confirmed','stderr_bytes':len(process.stderr),
              'stderr_truncated':process.stderr_truncated}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,sort_keys=True))


if __name__ == '__main__':
    main()
