"""Test interpreter for the registered adapter's inherited vendor channel.

Relay the production frames unchanged. A fixture may hold one launch request
before delivery, or drop one real launch reply and hold its recovery replies
long enough for the test to read the Host's durable state.
"""

import json
import os
from pathlib import Path
import runpy
import socket
import sys
import threading
import time


MAX_FRAME = 1_048_576


def relay(upstream, downstream, control):
    lock = threading.Lock()
    pending = {}
    deferred = []
    writers = {upstream: threading.Lock(), downstream: threading.Lock()}
    target = None
    fault = None
    launch_seen = False
    ended = threading.Event()

    def stage(name, request, reply=None):
        value = {'adapter_pid': os.getpid(), 'request': request}
        if reply is not None:
            value['reply'] = reply
        path = control / (name + '.json')
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value))
        temporary.replace(path)

    def send(destination, line):
        with writers[destination]:
            if not ended.is_set():
                destination.sendall(line)

    def hold(name, destination, line):
        def forward():
            deadline = time.monotonic() + 18
            try:
                while not ended.is_set():
                    if (control / (name + '.release')).is_file():
                        send(destination, line)
                        return
                    if time.monotonic() >= deadline:
                        raise TimeoutError(name)
                    ended.wait(.02)
            except OSError as error:
                if not ended.is_set():
                    print(f'Cursor fixture relay: {type(error).__name__}: {error}', file=sys.stderr)
                    try:
                        destination.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass

        thread = threading.Thread(target=forward, daemon=True)
        with lock:
            if len(deferred) >= 3:
                raise ValueError("Unexpected duplicate held vendor frames")
            deferred.append(thread)
            thread.start()

    def transfer(source, destination, to_host):
        nonlocal target, fault, launch_seen
        try:
            with source.makefile('rb') as stream:
                while not ended.is_set():
                    line = stream.readline(MAX_FRAME + 1)
                    if not line:
                        break
                    if len(line) > MAX_FRAME or not line.endswith(b'\n'):
                        raise ValueError("Unbounded vendor channel frame")
                    frame = json.loads(line)
                    if to_host:
                        with lock:
                            if len(pending) >= 32 or frame['id'] in pending:
                                raise ValueError("Invalid pending vendor channel frame")
                            pending[frame['id']] = frame
                            choice = control / 'fault'
                            if target is None and frame['op'] == 'bind' and choice.is_file():
                                fault = choice.read_text()
                                target = frame['acquisition']
                            selected = frame.get('acquisition') == target and target is not None
                        if selected and frame['op'] == 'launch':
                            if launch_seen:
                                stage('launch-replayed', frame)
                            launch_seen = True
                            if fault == 'hold-launch':
                                stage('launch-held', frame)
                                hold('launch-held', destination, line)
                                continue
                    else:
                        with lock:
                            request = pending.pop(frame['id'])
                            selected = request.get('acquisition') == target and target is not None
                        if selected and request['op'] in ('bind', 'probe'):
                            stage(request['op'], request, frame)
                        elif selected and fault == 'lose-reply':
                            if request['op'] == 'launch' and 'result' in frame:
                                stage('launch-dropped', request, frame)
                                continue
                            if request['op'] in ('receipt', 'retire'):
                                stage(request['op'], request, frame)
                                hold(request['op'], destination, line)
                                continue
                        elif selected and fault == 'hold-launch-reply' and request['op'] == 'launch':
                            stage('launch-reply-held', request, frame)
                            hold('launch-reply-held', destination, line)
                            continue
                        elif selected and fault == 'hold-launch' and request['op'] == 'launch':
                            stage('launch-delivered', request, frame)
                    send(destination, line)
        except (OSError, ValueError, KeyError) as error:
            if not ended.is_set():
                print(f'Cursor fixture relay: {type(error).__name__}: {error}', file=sys.stderr)
        finally:
            ended.set()
            for endpoint in (source, destination):
                try:
                    endpoint.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    threads = [
        threading.Thread(target=transfer, args=(downstream, upstream, True), daemon=True),
        threading.Thread(target=transfer, args=(upstream, downstream, False), daemon=True),
    ]
    for thread in threads:
        thread.start()
    return ended, threads, deferred


def main():
    adapter = sys.argv[1]
    if sys.argv[2:] != ['--host-vendor-execution']:
        raise ValueError("Expected the registered managed Cursor adapter")
    control = Path(os.environ['HOME']) / 'cursor-start-transport'
    control.mkdir(exist_ok=True)
    # Only the real adapter consumes fd 3. The test owns the other socket ends.
    upstream = socket.socket(fileno=os.dup(3))
    upstream.setblocking(True)
    adapter_end, downstream = socket.socketpair()
    os.dup2(adapter_end.fileno(), 3, inheritable=False)
    adapter_end.close()
    ended, threads, deferred = relay(upstream, downstream, control)
    try:
        sys.argv = sys.argv[1:]
        sys.path.insert(0, str(Path(adapter).parent))
        runpy.run_path(adapter, run_name='__main__')
    finally:
        ended.set()
        for endpoint in (upstream, downstream):
            try:
                endpoint.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        for thread in threads + deferred:
            thread.join(timeout=1)
        upstream.close()
        downstream.close()


if __name__ == '__main__':
    main()
