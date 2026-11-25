#!/usr/bin/env python3
"""Deterministic ACP peer; deliberately has no networking or model client."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

def observe(phase, **fields):
    if os.environ.get('CURSOR_SOURCE_FIXTURE') == '1':
        with (Path(os.environ['HOME']) / 'cursor-vendor-effects.jsonl').open('a') as stream:
            stream.write(json.dumps({'pid': os.getpid(), 'phase': phase,
                                     'time_ms': time.time_ns() // 1000000, **fields}) + '\n')


if sys.argv[1:]==['--version']:
    observe('probe')
    print('unsupported' if os.environ.get('FIXTURE_WRONG_VERSION') else '2026.05.04-08e5280')
    raise SystemExit
def boundaries(paths):
    record = {'cwd': os.getcwd(), 'paths': {}, 'denied': []}
    Path('cursor-selected-write').write_text('written')
    for key in ('HOME', 'XDG_CACHE_HOME', 'XDG_CONFIG_HOME', 'XDG_STATE_HOME'):
        directory = Path(os.environ[key])
        directory.mkdir(parents=True, exist_ok=True)
        marker = directory / 'cursor-container-marker'
        previous = marker.read_text() if marker.exists() else ''
        marker.write_text(previous + 'x')
        record['paths'][key] = str(directory)
    for path in paths:
        denied = []
        for mode in ('r', 'a'):
            try:
                with open(path, mode) as stream:
                    if mode == 'r': stream.read(1)
                    else: stream.write('escaped')
            except PermissionError:
                denied.append(mode)
        record['denied'].append(denied)
    return record

if sys.argv[1:] != ['acp']:
    assert '--' in sys.argv[1:]
    print(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd()}))
    Path('cursor-cli-write').write_text('written')
    raise SystemExit

observe('workload')
session='fixture-session'
waiting={}
active=None
cancel_replies = {
    'slow': {'result': {'stopReason': 'cancelled', 'usage': {'tokens': 3}, '_meta': {'fixture': 'settled'}}},
    'complete-on-cancel': {'result': {'stopReason': 'end_turn', 'usage': {'tokens': 7}, '_meta': {'fixture': 'completed'}}},
    'error-on-cancel': {'error': {'code': -32023, 'message': 'Fixture prompt error'}},
    'invalid-result-on-cancel': {'result': []},
    'missing-stop-on-cancel': {'result': {'usage': {'tokens': 1}}},
}

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
        if os.environ.get('CURSOR_SOURCE_FIXTURE') == '1':
            with (Path(os.environ['HOME']) / 'cursor-native-starts.jsonl').open('a') as stream:
                stream.write(json.dumps({'pid': os.getpid(), 'cwd': os.getcwd()}) + '\n')
        session=params.get('sessionId','fixture-session')
        reply(identifier,{'sessionId':session,'modes':{'currentModeId':'agent','availableModes':[{'id':m,'name':m} for m in ['agent','ask','plan']]}})
    elif method=='session/set_mode':reply(identifier,{'observed_mode':params['modeId']})
    elif method=='session/prompt':
        prompt=params['prompt'][0]['text'];active=identifier
        observe('prompt', prompt=prompt, acp_id=identifier, native_session=session)
        if prompt in ('permission','permission-on-cancel','question','plan'):
            if prompt in ('permission','permission-on-cancel'):
                name='session/request_permission';value={'sessionId':session,'toolCall':{'toolCallId':'fixture-tool','title':'Fixture permission'},'options':[{'optionId':'opaque-yes','kind':'allow_once','name':'Allow once'},{'optionId':'opaque-no','kind':'reject_once','name':'Reject once'}]}
            elif prompt=='question':
                name='cursor/ask_question';value={'toolCallId':'fixture-question','questions':[{'id':'q1','prompt':'Choose','options':[{'id':'a','label':'A'},{'id':'b','label':'B'}],'allowMultiple':False}]}
            else:
                name='cursor/create_plan';value={'toolCallId':'fixture-plan','plan':'Fixture plan','todos':[]}
            waiting[900]=identifier
            emit({'jsonrpc':'2.0','id':900,'method':name,'params':value})
        elif prompt in cancel_replies or prompt=='ignore-cancel':update('started')
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
        elif prompt.startswith('boundaries:'):
            update(json.dumps(boundaries(json.loads(prompt[len('boundaries:'):]))))
            finish(identifier)
        elif prompt=='env':
            update(json.dumps([k for k in os.environ if k.startswith('COMPUTER_MCP_')]))
            finish(identifier)
        else:update('hello');finish(identifier)
    elif method=='session/cancel':
        assert q == {'jsonrpc': '2.0', 'method': 'session/cancel', 'params': {'sessionId': session}}
        observe('cancel', acp_id=active, native_session=session)
        if active is not None and prompt == 'permission-on-cancel' and 900 in waiting:
            continue
        if active is not None and prompt != 'ignore-cancel':
            terminal = cancel_replies.get(prompt, {'result': {'stopReason': 'cancelled'}})
            emit({'jsonrpc': '2.0', 'id': active, **terminal})
            observe('terminal', acp_id=active, native_session=session, outcome=terminal)
            active = None
    elif method is None and identifier in waiting:
        response = q.get('result')
        observe('answer', acp_id=identifier, native_session=session, response=response)
        update(json.dumps({'received_response':response}))
        cancelled = prompt == 'permission-on-cancel' and response == {'outcome': {'outcome': 'cancelled'}}
        finish(waiting.pop(identifier), 'cancelled' if cancelled else 'end_turn')
        active = None
    elif identifier is not None:
        emit({'jsonrpc':'2.0','id':identifier,'error':{'code':-32601,'message':'Unknown fixture method'}})
