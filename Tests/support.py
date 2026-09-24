"""Bounded MCP fixture client. No vendor account or model is used."""
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time
import tomllib

ROOT = Path(__file__).resolve().parent.parent
VENDOR = tomllib.loads((ROOT / 'computer-mcp-plugin.toml').read_text())['id']

class Client:
    def __init__(self, directory, environment=None, command=None):
        env = dict(os.environ) if command is None else {}
        env.update(environment or {})
        env['CURSOR_AGENT_EXECUTABLE' if VENDOR=='cursor' else 'CLAUDE_CODE_EXECUTABLE'] = str(ROOT/'Tests/Fixtures/vendor.py')
        self.process = subprocess.Popen(command or [sys.executable,str(ROOT/f'bin/{VENDOR}-mcp-adapter')],cwd=directory,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.buffer = bytearray()
        self.serial = 1
        self.saved = {}
        self.request('initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'fixture','version':'1'}})
        self.send({'jsonrpc':'2.0','method':'notifications/initialized'})
    def send(self, value):
        self.process.stdin.write(json.dumps(value).encode()+b'\n');self.process.stdin.flush()
    def receive(self, timeout=10):
        deadline = time.monotonic()+timeout
        with selectors.DefaultSelector() as s:
            s.register(self.process.stdout,selectors.EVENT_READ)
            while b'\n' not in self.buffer:
                remaining = deadline-time.monotonic()
                if remaining<=0 or not s.select(remaining):raise AssertionError('MCP response deadline exceeded')
                part = os.read(self.process.stdout.fileno(),65536)
                if not part:raise AssertionError('MCP closed without a response')
                self.buffer.extend(part)
                if len(self.buffer)>2*1048576:raise AssertionError('MCP response exceeds test bound')
        line,rest = self.buffer.split(b'\n',1);self.buffer=bytearray(rest)
        return json.loads(line)
    def begin(self, name, arguments):
        self.serial += 1
        self.send({'jsonrpc':'2.0','id':self.serial,'method':'tools/call','params':{'name':name,'arguments':arguments}})
        return self.serial
    def wait(self, identifier, timeout=10):
        if identifier in self.saved:return self.saved.pop(identifier)
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            response = self.receive(max(.001,deadline-time.monotonic()))
            if response.get('id')==identifier:return response
            self.saved[response.get('id')] = response
        raise AssertionError('MCP request deadline exceeded')
    def call(self,name,arguments=None,timeout=10):return self.wait(self.begin(name,arguments or {}),timeout)
    def request(self,method,params=None):
        self.serial+=1
        self.send({'jsonrpc':'2.0','id':self.serial,'method':method,'params':params or {}})
        return self.wait(self.serial)
    @staticmethod
    def value(response):return response['result']['structuredContent']['result']
    def close(self):
        if not self.process.stdin.closed:self.process.stdin.close()
        try:
            try:
                self.process.wait(timeout=6)
            except subprocess.TimeoutExpired as error:
                self.process.kill()
                self.process.wait(timeout=2)
                raise AssertionError('MCP peer required forced shutdown') from error
        finally:
            for stream in (self.process.stdout,self.process.stderr):
                stream.close()


def wait_file(path, seconds=8):
    end = time.monotonic()+seconds
    while time.monotonic()<end:
        if Path(path).exists():
            try:return json.loads(Path(path).read_text())
            except (ValueError,OSError):pass
        time.sleep(.02)
    raise AssertionError('Fixture did not reach its execution checkpoint')


def process_alive(pid):
    r=subprocess.run(['/bin/ps','-p',str(pid),'-o','stat='],capture_output=True,text=True,timeout=1)
    return bool(r.stdout.strip()) and not r.stdout.strip().startswith('Z')


def wait_stopped(pids, seconds=6):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if not any(process_alive(pid) for pid in pids):return
        time.sleep(.05)
    raise AssertionError('Owned fixture processes survived cleanup')
