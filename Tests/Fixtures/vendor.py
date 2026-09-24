#!/usr/bin/env python3
"""Deterministic ACP peer; deliberately has no networking or model client."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

if sys.argv[1:]==['--version']:
    print('unsupported' if os.environ.get('FIXTURE_WRONG_VERSION') else '2026.05.04-08e5280')
    raise SystemExit
assert sys.argv[1:]==['acp']
session='fixture-session'
waiting={}
active=None

def emit(value):print(json.dumps(value),flush=True)
def reply(identifier,value):emit({'jsonrpc':'2.0','id':identifier,'result':value})
def update(text):emit({'jsonrpc':'2.0','method':'session/update','params':{'sessionId':session,'update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':text}}}})
def finish(identifier,reason='end_turn'):reply(identifier,{'stopReason':reason})

for line in sys.stdin:
    q=json.loads(line);method=q.get('method');identifier=q.get('id');params=q.get('params',{})
    if method=='initialize':
        reply(identifier,{'protocolVersion':1,'agentCapabilities':{'loadSession':True},'authMethods':[{'id':'cursor_login','name':'Existing CLI login'}]})
    elif method=='authenticate':reply(identifier,{})
    elif method in ('session/new','session/load'):
        session=params.get('sessionId','fixture-session')
        reply(identifier,{'sessionId':session,'modes':{'currentModeId':'agent','availableModes':[{'id':m,'name':m} for m in ['agent','ask','plan']]}})
    elif method=='session/set_mode':reply(identifier,{'observed_mode':params['modeId']})
    elif method=='session/prompt':
        prompt=params['prompt'][0]['text'];active=identifier
        if prompt in ('permission','question','plan'):
            if prompt=='permission':
                name='session/request_permission';value={'sessionId':session,'toolCall':{'toolCallId':'fixture-tool','title':'Fixture permission'},'options':[{'optionId':'opaque-yes','kind':'allow_once','name':'Allow once'},{'optionId':'opaque-no','kind':'reject_once','name':'Reject once'}]}
            elif prompt=='question':
                name='cursor/ask_question';value={'toolCallId':'fixture-question','questions':[{'id':'q1','prompt':'Choose','options':[{'id':'a','label':'A'},{'id':'b','label':'B'}],'allowMultiple':False}]}
            else:
                name='cursor/create_plan';value={'toolCallId':'fixture-plan','plan':'Fixture plan','todos':[]}
            waiting[900]=identifier
            emit({'jsonrpc':'2.0','id':900,'method':name,'params':value})
        elif prompt=='slow':update('started')
        elif prompt=='fork':
            child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)'])
            Path(os.environ['FIXTURE_MARKER']).write_text(json.dumps([os.getpid(),child.pid]))
            update('started')
        elif prompt=='huge':sys.stdout.write('x'*1048577);sys.stdout.flush()
        elif prompt=='malformed':sys.stdout.write('not-json\n');sys.stdout.flush()
        elif prompt=='flood':
            for i in range(600):update('x'*4096)
            finish(identifier)
        elif prompt=='exit-fast':finish(identifier);raise SystemExit
        elif prompt=='env':
            update(json.dumps([k for k in os.environ if k.startswith('COMPUTER_MCP_')]))
            finish(identifier)
        else:update('hello');finish(identifier)
    elif method=='session/cancel':
        if active is not None:finish(active,'cancelled');active=None
    elif method is None and identifier in waiting:
        update(json.dumps({'received_response':q.get('result')}))
        finish(waiting.pop(identifier))
    elif identifier is not None:
        emit({'jsonrpc':'2.0','id':identifier,'error':{'code':-32601,'message':'Unknown fixture method'}})
