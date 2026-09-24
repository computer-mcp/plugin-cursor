"""Private stdio, process ownership and validation primitives for this plugin."""
from collections import deque
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import select
import selectors
import shutil
import signal
import subprocess
import sys
import threading
import time
import tomllib

MAX_FRAME = 1_048_576
MAX_RESULT = 196_608
SUPPORTED_MCP = ('2024-11-05', '2025-03-26', '2025-06-18')


class Failure(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')


def decoded(raw):
    def unique(pairs):
        value = {}
        for k, v in pairs:
            if k in value:
                raise ValueError('Duplicate JSON object key')
            value[k] = v
        return value
    def invalid_number(_):
        raise ValueError('Non-finite JSON number')
    def finite_float(text):
        value = float(text)
        if not math.isfinite(value):
            raise ValueError('JSON floating-point number is not finite')
        return value
    return json.loads(raw.decode('utf-8'), object_pairs_hook=unique, parse_constant=invalid_number, parse_float=finite_float)


def schema(properties, required=()):
    return {'type':'object', 'properties':properties, 'required':list(required), 'additionalProperties':False}


def text_schema(limit=131072, minimum=1):
    return {'type':'string', 'minLength':minimum, 'maxLength':limit}


def integer_schema(minimum, maximum, default=None):
    result = {'type':'integer', 'minimum':minimum, 'maximum':maximum}
    if default is not None:
        result['default'] = default
    return result


def validate(value, spec, location='arguments', depth=0):
    if depth > 20:
        raise Failure('invalid_arguments', 'Input exceeds the nesting limit')
    kind = spec.get('type')
    valid = {
        'object':lambda: isinstance(value, dict),
        'array':lambda: isinstance(value, list),
        'string':lambda: isinstance(value, str),
        'integer':lambda: type(value) is int,
        'number':lambda: type(value) is int or (type(value) is float and math.isfinite(value)),
        'boolean':lambda: type(value) is bool,
        'null':lambda: value is None,
    }
    if kind in valid and not valid[kind]():
        raise Failure('invalid_arguments', f'{location} must be {kind}')
    if 'enum' in spec and value not in spec['enum']:
        raise Failure('invalid_arguments', f'{location} is not an allowed value')
    if isinstance(value, str):
        if '\0' in value or len(value.encode('utf-8')) > MAX_FRAME:
            raise Failure('invalid_arguments', f'{location} contains NUL or exceeds its byte bound')
        if not spec.get('minLength', 0) <= len(value) <= spec.get('maxLength', MAX_FRAME):
            raise Failure('invalid_arguments', f'{location} exceeds its length bounds')
    if type(value) in (int, float):
        if (type(value) is float and not math.isfinite(value)) or value < spec.get('minimum', -math.inf) or value > spec.get('maximum', math.inf):
            raise Failure('invalid_arguments', f'{location} exceeds its numeric bounds')
    if isinstance(value, dict):
        props = spec.get('properties', {})
        missing = set(spec.get('required', ())) - value.keys()
        if missing:
            raise Failure('invalid_arguments', f'{location} is missing required fields: {", ".join(sorted(missing))}')
        if spec.get('additionalProperties') is False and set(value) - props.keys():
            raise Failure('invalid_arguments', f'{location} has unknown fields')
        for k, v in value.items():
            validate(v, props.get(k, {}), f'{location}.{k}', depth+1)
    if isinstance(value, list):
        if not spec.get('minItems', 0) <= len(value) <= spec.get('maxItems', 4096):
            raise Failure('invalid_arguments', f'{location} exceeds its item bound')
        for v in value:
            validate(v, spec.get('items', {}), location+'[]', depth+1)


class Job:
    def __init__(self):
        self.cancelled = threading.Event()
    def cancel(self):
        self.cancelled.set()
    def check(self):
        if self.cancelled.is_set():
            raise Failure('cancelled', 'Operation cancelled')


class LineReader:
    """Bound bytes before parsing, and bound queued frames before admitting more."""
    def __init__(self, stream, limit=MAX_FRAME):
        self.stream, self.limit = stream, limit
        self.queue = queue.Queue(maxsize=8)
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()
    def _put(self, item):
        while not self.stopped.is_set():
            try:
                self.queue.put(item, timeout=.05)
                return
            except queue.Full:
                pass
    def _read(self):
        buf = bytearray()
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(self.stream, selectors.EVENT_READ)
                while not self.stopped.is_set():
                    if not selector.select(.05):
                        continue
                    chunk = os.read(self.stream.fileno(), 16384)
                    if not chunk:
                        if buf:
                            self._put(bytes(buf))
                        break
                    buf.extend(chunk)
                    while True:
                        index = buf.find(b'\n')
                        if index < 0:
                            if len(buf) > self.limit:
                                raise Failure('frame_too_large', 'A protocol line exceeds its byte bound')
                            break
                        if index+1 > self.limit:
                            raise Failure('frame_too_large', 'A protocol line exceeds its byte bound')
                        self._put(bytes(buf[:index+1]))
                        del buf[:index+1]
        except Exception as error:
            self._put(error if isinstance(error, Failure) else Failure('stream_failed', 'Protocol stream capture failed'))
        finally:
            self._put(None)
    def next(self, deadline, job=None):
        while True:
            if job:
                job.check()
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise Failure('timeout', 'Operation exceeded its deadline')
            try:
                item = self.queue.get(timeout=min(.05, remaining))
            except queue.Empty:
                continue
            if isinstance(item, Exception):
                raise item
            return item
    def close(self):
        self.stopped.set()
        self.thread.join(timeout=.5)


def write_bytes(fd, data, deadline, cancelled=None):
    view = memoryview(data)
    with selectors.DefaultSelector() as selector:
        selector.register(fd, selectors.EVENT_WRITE)
        while view:
            if cancelled is not None and cancelled.is_set():
                raise Failure('cancelled', 'Operation cancelled')
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise Failure('timeout', 'Protocol writer exceeded its deadline')
            if not selector.select(min(.05, remaining)):
                continue
            try:
                count = os.write(fd, view)
            except BlockingIOError:
                continue
            except (BrokenPipeError, OSError) as error:
                raise Failure('connection_closed', 'Protocol peer closed its input') from error
            view = view[count:]


def vendor_environment():
    # Private host provenance and inherited callback authority do not belong to a vendor.
    return {k:v for k,v in os.environ.items() if not k.startswith('COMPUTER_MCP_')}


def supervise(read_fd, receipt_fd, command):
    """Pin the vendor group until retirement and report cleanup separately from exit."""
    stopped = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stopped.set())
    child = None
    exit_code = 70
    confirmed = False
    try:
        child = subprocess.Popen(command, close_fds=True, start_new_session=True)
        while not stopped.is_set():
            status = os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            if status is not None:
                break
            ready, _, _ = select.select([read_fd], [], [], .05)
            if ready and not os.read(read_fd, 1):
                break
    except Exception:
        os.write(2, b'Owned vendor process could not start or be supervised.\n')
    finally:
        try:
            if child is not None:
                # Do not reap the leader before signalling its group: its PID pins ownership.
                for sig, delay in ((signal.SIGTERM, .15), (signal.SIGKILL, 0)):
                    try:
                        os.killpg(child.pid, sig)
                    except ProcessLookupError:
                        pass
                    except PermissionError:
                        report = subprocess.run(
                            ['/bin/ps', '-g', str(child.pid), '-o', 'pid=,stat='],
                            capture_output=True, text=True, timeout=1)
                        rows = [line.split() for line in report.stdout.splitlines() if line.strip()]
                        if report.returncode not in (0, 1) or any(
                            len(row) != 2 or not row[1].startswith('Z') for row in rows
                        ):
                            raise Failure('cleanup_unconfirmed', 'Owned group could not be retired')
                    if delay:
                        time.sleep(delay)
                child.wait(timeout=2)
                exit_code = child.returncode if child.returncode >= 0 else 128-child.returncode
            confirmed = True
        except Exception:
            exit_code = 70
            os.write(2, b'Owned vendor process cleanup is unconfirmed.\n')
        finally:
            try:
                os.write(receipt_fd, encoded({'cleanup_confirmed': confirmed})+b'\n')
            except OSError:
                pass
            os.close(receipt_fd)
            os.close(read_fd)
    return exit_code


class Process:
    """A supervisor owns vendor descendants and watches an adapter-only lifeline."""
    def __init__(self, command, cwd):
        read_fd, self.life = os.pipe()
        self.receipt, receipt_write = os.pipe()
        try:
            self.child = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), '--supervise', str(read_fd), str(receipt_write), '--', *command],
                cwd=cwd, env=vendor_environment(), close_fds=True, pass_fds=(read_fd, receipt_write),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except BaseException:
            os.close(self.life)
            os.close(self.receipt)
            raise
        finally:
            os.close(read_fd)
            os.close(receipt_write)
        self.writer_lock = threading.Lock()
        self.close_lock = threading.Lock()
        self.closed = False
        self.cleanup_failure = None
        self.stderr = bytearray()
        self.stderr_truncated = False
        self.stop_stderr = threading.Event()
        os.set_blocking(self.child.stdin.fileno(), False)
        self.output = LineReader(self.child.stdout)
        self.stderr_thread = threading.Thread(target=self._stderr, daemon=True)
        self.stderr_thread.start()
    def _stderr(self):
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(self.child.stderr, selectors.EVENT_READ)
                while not self.stop_stderr.is_set():
                    if not selector.select(.05):
                        continue
                    raw = os.read(self.child.stderr.fileno(), 16384)
                    if not raw:
                        return
                    capacity = 65536-len(self.stderr)
                    self.stderr.extend(raw[:capacity])
                    self.stderr_truncated |= len(raw) > capacity
        except (ValueError, OSError):
            pass
    def send(self, message, deadline, job=None):
        data = encoded(message)+b'\n'
        if len(data) > MAX_FRAME:
            raise Failure('frame_too_large', 'Outbound protocol frame exceeds its byte bound')
        with self.writer_lock:
            if self.closed:
                raise Failure('connection_closed', 'Vendor process is closed')
            write_bytes(self.child.stdin.fileno(), data, deadline, job.cancelled if job else None)
    def end_input(self):
        with self.writer_lock:
            if not self.child.stdin.closed:
                self.child.stdin.close()
    def read(self, deadline, job=None):
        return self.output.next(deadline, job)
    def finish(self, deadline, job=None):
        while True:
            if job:
                job.check()
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise Failure('timeout', 'Vendor did not exit before its deadline')
            try:
                return self.child.wait(timeout=min(.05,remaining))
            except subprocess.TimeoutExpired:
                pass
    @staticmethod
    def confirm_cleanup(descriptor):
        try:
            raw = os.read(descriptor, 4096)
            value = decoded(raw)
            if not isinstance(value, dict) or value.get('cleanup_confirmed') is not True:
                raise ValueError('Cleanup not confirmed')
        except (ValueError, UnicodeError, OSError, RecursionError) as error:
            raise Failure('cleanup_unconfirmed', 'Supervisor did not confirm owned process cleanup') from error

    def close(self):
        with self.close_lock:
            if self.closed:
                if self.cleanup_failure:
                    raise self.cleanup_failure
                return
            self.closed = True
            os.close(self.life)
            try:
                try:
                    self.child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.child.terminate()
                    try:
                        self.child.wait(timeout=2)
                    except subprocess.TimeoutExpired as error:
                        self.child.kill()
                        self.child.wait(timeout=2)
                        raise Failure('cleanup_unconfirmed', 'Vendor supervisor did not confirm shutdown') from error
                self.confirm_cleanup(self.receipt)
            except Failure as error:
                self.cleanup_failure = error
                raise
            finally:
                os.close(self.receipt)
                self.output.close()
                self.stop_stderr.set()
                self.stderr_thread.join(timeout=.5)
                with self.writer_lock:
                    for stream in (self.child.stdin, self.child.stdout, self.child.stderr):
                        stream.close()


def resolve_executable(explicit, environment_key, default):
    candidate = explicit or os.environ.get(environment_key)
    if candidate:
        if not os.path.isabs(candidate):
            raise Failure('invalid_configuration', 'The configured vendor executable must be absolute')
    else:
        candidate = shutil.which(default)
    if not candidate or not os.path.isfile(candidate) or not os.access(candidate, os.X_OK):
        raise Failure('dependency_unavailable', f'Install {default} separately or configure --executable')
    return candidate


def load_package(entry):
    root = Path(entry).resolve().parent.parent
    manifest = tomllib.loads((root/'computer-mcp-plugin.toml').read_text())
    tree = json.loads((root/'cli-tree.json').read_text())
    return manifest, tree


def verify_version(executable, tree, job, cwd):
    expected = next((x.get('stdout') for x in tree.get('executable_checks', []) if x.get('args') == ['--version']), None)
    if expected is None:
        raise Failure('invalid_configuration', 'Package lacks its native version assertion')
    process = Process([executable, '--version'], cwd)
    deadline = time.monotonic()+5
    output = bytearray()
    try:
        process.end_input()
        while True:
            raw = process.read(deadline, job)
            if raw is None:
                break
            output.extend(raw)
            if len(output) > 65536:
                raise Failure('incompatible_vendor', 'Native version output exceeded its bound')
        if process.finish(deadline, job) != 0 or bytes(output) != expected.encode():
            raise Failure('incompatible_vendor', 'Vendor version differs from the verified plugin baseline')
    finally:
        process.close()


class EventBuffer:
    def __init__(self, max_events=256, max_bytes=262144):
        self.lock = threading.Lock()
        self.items = deque()
        self.max_events, self.max_bytes = max_events, max_bytes
        self.bytes, self.cursor, self.omitted = 0, 0, 0
    def append(self, value):
        data = encoded(value)
        with self.lock:
            self.cursor += 1
            if len(data) > self.max_bytes//2:
                value = {'omitted':True, 'reason':'event_byte_bound', 'bytes':len(data), 'sha256':hashlib.sha256(data).hexdigest()}
                data = encoded(value)
                self.omitted += 1
            self.items.append((self.cursor, value, len(data)))
            self.bytes += len(data)
            while len(self.items) > self.max_events or self.bytes > self.max_bytes:
                self.bytes -= self.items.popleft()[2]
    def page(self, after=0, limit=128, max_bytes=196608):
        with self.lock:
            if after > self.cursor:
                raise Failure('invalid_cursor', 'Cursor is newer than this event stream')
            oldest = self.items[0][0] if self.items else self.cursor+1
            rows, total, next_cursor = [], 0, after
            for cursor, value, size in self.items:
                if cursor <= after:
                    continue
                row = {'cursor':cursor,'event':value}
                row_size = len(encoded(row))
                if not rows and row_size > max_bytes:
                    row = {'cursor':cursor,'event':{'omitted':True,'reason':'page_byte_bound','bytes':size}}
                    row_size = len(encoded(row))
                if len(rows) >= limit or total+row_size > max_bytes:
                    break
                rows.append(row)
                total += row_size
                next_cursor = cursor
            return {'events':rows,'next_cursor':next_cursor,'oldest_cursor':oldest,'has_more':next_cursor<self.cursor,'missed_events':after<oldest-1,'observed_events':self.cursor,'omitted_events':self.omitted}


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    handler: object
    def definition(self):
        return {'name':self.name,'description':self.description,'inputSchema':self.input_schema}


class MCPServer:
    def __init__(self, name, version, tools, shutdown):
        self.name, self.version = name, version
        self.tools = {t.name:t for t in tools}
        self.shutdown = shutdown
        self.stop = threading.Event()
        self.jobs, self.threads = {}, set()
        self.lock, self.write_lock = threading.Lock(), threading.Lock()
        self.initialized = False
    def emit(self, message):
        raw = encoded(message)+b'\n'
        if len(raw) > MAX_FRAME:
            raw = encoded({'jsonrpc':'2.0','id':message.get('id'),'error':{'code':-32603,'message':'Response exceeds the protocol bound'}})+b'\n'
        try:
            with self.write_lock:
                write_bytes(1, raw, time.monotonic()+5, self.stop)
        except (Failure, OSError):
            self.stop.set()
    def rpc_error(self, request_id, code, message):
        self.emit({'jsonrpc':'2.0','id':request_id,'error':{'code':code,'message':message}})
    def call(self, request_id, key, tool, arguments, job):
        try:
            validate(arguments, tool.input_schema)
            job.check()
            value = tool.handler(arguments, job)
            body = encoded(value)
            if len(body) > 524288:
                raise Failure('result_too_large', 'Result exceeds its structured byte bound; use event pagination')
            is_error = bool(value.get('is_error', False)) if isinstance(value, dict) else False
        except Failure as error:
            value, is_error = {'error':{'code':error.code,'message':str(error)[:1024]}}, True
        except Exception:
            value, is_error = {'error':{'code':'internal_error','message':'Adapter operation failed; no automatic replay was attempted'}}, True
        summary = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',',':'))
        if len(summary.encode()) > 8192:
            summary = 'Structured result available in structuredContent.result; events are separately paginated.'
        self.emit({'jsonrpc':'2.0','id':request_id,'result':{'content':[{'type':'text','text':summary}],'structuredContent':{'result':value},'isError':is_error}})
        with self.lock:
            self.jobs.pop(key, None)
            self.threads.discard(threading.current_thread())
    @staticmethod
    def id_key(value):
        if type(value) not in (int,str) or (isinstance(value,str) and (not value or len(value)>256)):
            raise ValueError('Invalid request ID')
        return type(value).__name__, value
    def dispatch(self, message):
        if not isinstance(message, dict) or message.get('jsonrpc') != '2.0' or not isinstance(message.get('method'),str):
            self.rpc_error(None,-32600,'Invalid JSON-RPC request')
            return
        method, params = message['method'], message.get('params', {})
        if 'id' not in message:
            if method == 'notifications/cancelled' and isinstance(params,dict):
                try: key = self.id_key(params.get('requestId'))
                except ValueError: return
                with self.lock: job = self.jobs.get(key)
                if job: job.cancel()
            return
        request_id = message['id']
        try: key = self.id_key(request_id)
        except ValueError:
            self.rpc_error(None,-32600,'Invalid request ID'); return
        if not isinstance(params,dict):
            self.rpc_error(request_id,-32602,'Parameters must be an object'); return
        if method == 'initialize':
            if self.initialized:
                self.rpc_error(request_id,-32600,'Connection is already initialized'); return
            requested = params.get('protocolVersion')
            if not isinstance(requested,str):
                self.rpc_error(request_id,-32602,'protocolVersion is required'); return
            self.initialized = True
            self.emit({'jsonrpc':'2.0','id':request_id,'result':{'protocolVersion':requested if requested in SUPPORTED_MCP else SUPPORTED_MCP[-1],'capabilities':{'tools':{'listChanged':False}},'serverInfo':{'name':self.name,'version':self.version}}})
        elif method == 'ping':
            self.emit({'jsonrpc':'2.0','id':request_id,'result':{}})
        elif not self.initialized:
            self.rpc_error(request_id,-32002,'Initialize the MCP connection first')
        elif method == 'tools/list':
            if params.get('cursor'):
                self.rpc_error(request_id,-32602,'This finite catalog has no continuation cursor'); return
            self.emit({'jsonrpc':'2.0','id':request_id,'result':{'tools':[t.definition() for t in self.tools.values()]}})
        elif method == 'tools/call':
            name = params.get('name')
            if not isinstance(name,str) or name not in self.tools:
                self.rpc_error(request_id,-32602,'Unknown tool'); return
            args = params.get('arguments', {})
            with self.lock:
                if key in self.jobs:
                    self.rpc_error(request_id,-32600,'Request ID is already active'); return
                if len(self.jobs)>=16:
                    self.rpc_error(request_id,-32000,'Concurrent request capacity reached'); return
                job = Job()
                thread = threading.Thread(target=self.call,args=(request_id,key,self.tools[name],args,job))
                self.jobs[key] = job
                self.threads.add(thread)
                thread.start()
        else:
            self.rpc_error(request_id,-32601,'Method not found')
    def serve(self):
        os.set_blocking(1,False)
        for sig in (signal.SIGTERM,signal.SIGINT):
            signal.signal(sig,lambda *_:self.stop.set())
        reader = LineReader(sys.stdin.buffer)
        try:
            while not self.stop.is_set():
                try: raw = reader.next(time.monotonic()+.1)
                except Failure as error:
                    if error.code=='timeout': continue
                    self.rpc_error(None,-32600,str(error)); break
                if raw is None: break
                try: message = decoded(raw)
                except (ValueError,UnicodeError,RecursionError):
                    self.rpc_error(None,-32700,'Invalid JSON'); continue
                self.dispatch(message)
        finally:
            self.stop.set()
            reader.close()
            with self.lock:
                jobs, threads = list(self.jobs.values()), list(self.threads)
            for job in jobs: job.cancel()
            self.shutdown()
            for thread in threads: thread.join(timeout=5)


if __name__ == '__main__':
    if len(sys.argv) < 6 or sys.argv[1] != '--supervise' or sys.argv[4] != '--':
        raise SystemExit('Private process supervisor requires an inherited lifeline')
    raise SystemExit(supervise(int(sys.argv[2]), int(sys.argv[3]), sys.argv[5:]))
