"""Cursor's private channel to the Host-owned version and ACP children."""

import base64
import os
import queue
import socket
import threading
import time

from plugin_runtime import Failure, LineReader, MAX_FRAME, decoded, encoded, write_bytes


CAPABILITY = 'io.github.computer-mcp/vendor-execution-v1'


class HostVendorRefusal(Failure):
    """A definitive Host reply that the operation failed before delivery."""


class VendorChannel:
    def __init__(self):
        if (os.environ.get('COMPUTER_MCP_HOST_CONTEXT') != CAPABILITY
                or os.environ.get('COMPUTER_MCP_HOST_FD') != '3'):
            raise Failure('host_execution_required', 'Managed Cursor requires the Host vendor channel')
        self.socket = socket.socket(fileno=3)
        os.set_inheritable(3, False)
        self.socket.setblocking(False)
        self.reader = LineReader(self.socket)
        self.lock, self.writer = threading.Lock(), threading.Lock()
        self.pending = {}
        self.sequence = 0
        self.closed = threading.Event()
        threading.Thread(target=self._receive, daemon=True).start()
        try:
            if self.call('initialize', capability=CAPABILITY).get('capability') != CAPABILITY:
                raise Failure('host_execution_required', 'Host did not negotiate Cursor vendor execution')
        except BaseException:
            self.close()
            raise

    def _receive(self):
        try:
            while not self.closed.is_set():
                try:
                    raw = self.reader.next(time.monotonic() + .1)
                except Failure as error:
                    if error.code == 'timeout':
                        continue
                    raise
                if raw is None:
                    break
                result = decoded(raw)
                with self.lock:
                    pending = self.pending.get(result['id'])
                    if pending is not None:
                        pending.put_nowait(result)
        except (Failure, ValueError, KeyError, TypeError, queue.Full):
            pass
        finally:
            self.closed.set()

    def begin(self, op, deadline, **fields):
        pending = queue.Queue(maxsize=1)
        with self.lock:
            if self.closed.is_set() or len(self.pending) >= 16:
                raise Failure('host_execution_closed', 'Cursor vendor channel is unavailable')
            self.sequence += 1
            request = self.sequence
            self.pending[request] = pending
        try:
            data = encoded({'id': request, 'op': op, **fields}) + b'\n'
            if len(data) > MAX_FRAME:
                raise Failure('frame_too_large', 'Cursor vendor channel frame exceeds its bound')
            with self.writer:
                try:
                    write_bytes(self.socket.fileno(), data, deadline, self.closed)
                except Failure:
                    self.close()
                    raise
            return request, pending
        except BaseException:
            self.discard(request)
            raise

    def discard(self, request):
        with self.lock:
            self.pending.pop(request, None)

    def wait(self, handle, deadline, *, keep_pending=False):
        request, pending = handle
        while not self.closed.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if not keep_pending:
                    self.discard(request)
                raise Failure('timeout', 'Host vendor operation did not confirm its result')
            try:
                reply = pending.get(timeout=min(.05, remaining))
            except queue.Empty:
                continue
            self.discard(request)
            if 'error' in reply:
                code = reply['error']
                if 'result' not in reply and code in ('vendor_effect_denied', 'vendor_effect_stale'):
                    raise HostVendorRefusal(code, 'Host did not dispatch the Cursor vendor effect')
                if 'result' not in reply and isinstance(code, str):
                    raise Failure(code, 'Host could not settle the Cursor vendor effect')
                raise Failure('invalid_host_reply', 'Host returned an invalid Cursor vendor reply')
            if not isinstance(reply.get('result'), dict):
                raise Failure('invalid_host_reply', 'Host returned an invalid Cursor vendor result')
            return reply['result']
        self.discard(request)
        raise Failure('host_execution_closed', 'Cursor vendor channel closed')

    def call(self, op, *, timeout=10, **fields):
        deadline = time.monotonic() + timeout
        return self.wait(self.begin(op, deadline, **fields), deadline)

    def close(self):
        self.closed.set()
        self.reader.close()
        self.socket.close()


class ManagedCursorProcess:
    """Owns adapter-side correlation only. The Host owns both child generations."""

    def __init__(self, channel, session, job):
        if job.work_invocation is None:
            raise Failure('host_execution_required', 'Host did not correlate the Cursor acquisition')
        self.channel = channel
        self.session = session
        self.acquisition = job.work_invocation
        self.probe = None
        self.workload = None
        self.output = bytearray()
        self.output_cursor = 0
        self.read_handle = None

    def _call(self, op, job, *, child=None, **fields):
        if job is None or job.work_invocation is None:
            raise Failure('host_execution_required', 'Host did not correlate the Cursor effect')
        return self.channel.call(op, call=job.work_invocation, acquisition=self.acquisition,
                                 child=child or self.workload, **fields)

    def launch(self, job):
        bound = self._call('bind', job, session=self.session)
        self.probe, self.workload = bound['probe'], bound['workload']
        job.check()
        self._call('probe', job, child=self.probe)
        job.check()
        try:
            self._call('launch', job)
        except Failure as error:
            if error.code == 'timeout':
                # A lost reply can establish ownership through the receipt, never by replay.
                self._call('receipt', job)
            raise

    def ready(self, job):
        self._call('ready', job)

    def send(self, value, deadline, job, kind, token=None):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise Failure('timeout', 'Cursor operation exceeded its deadline')
        self._call('write', job, kind=kind, data=encoded(value).decode('utf-8'),
                   token=token, timeout=min(10, remaining))

    def read(self, deadline, job):
        while time.monotonic() < deadline:
            newline = self.output.find(b'\n')
            if newline >= 0:
                line = bytes(self.output[:newline+1])
                del self.output[:newline+1]
                return line
            # A short local wait leaves at most one Host read in flight for this child.
            handle = self.read_handle
            if handle is None:
                handle = self.channel.begin(
                    'read', time.monotonic() + 1, call=job.work_invocation,
                    acquisition=self.acquisition, child=self.workload, after=self.output_cursor)
                self.read_handle = handle
            try:
                reply = self.channel.wait(handle, deadline, keep_pending=True)
            except Failure as error:
                if error.code != 'timeout':
                    self.read_handle = None
                raise
            self.read_handle = None
            if 'data' in reply:
                cursor = reply.get('cursor')
                if type(cursor) is not int or cursor != self.output_cursor + 1:
                    raise Failure('invalid_vendor_response', 'Host returned an unexpected Cursor output cursor')
                self.output.extend(base64.b64decode(reply['data'], validate=True))
                if len(self.output) > MAX_FRAME:
                    raise Failure('frame_too_large', 'Cursor emitted an oversized frame')
                self.output_cursor = cursor
            elif reply.get('eof'):
                return None
            else:
                time.sleep(.01)
        raise Failure('timeout', 'Cursor operation exceeded its deadline')

    def pending(self, job, token):
        self._call('pending', job, token=token)

    def stop(self, job):
        return self._call('stop', job)

    def detach(self, job):
        self._call('detach', job)

    def finish(self, job):
        self._call('finish', job)

    def close(self, job):
        if self.read_handle is not None:
            self.channel.discard(self.read_handle[0])
            self.read_handle = None
        try:
            receipt = self._call('retire', job)
        except Failure as error:
            if error.code not in ('timeout', 'vendor_effect_stale'):
                raise
            receipt = self._call('receipt', job)
        if not all(receipt.get(flag) is True for flag in ('retired', 'probe_settled', 'workload_settled')):
            raise Failure('cleanup_unconfirmed', 'Host could not confirm both Cursor child receipts')
