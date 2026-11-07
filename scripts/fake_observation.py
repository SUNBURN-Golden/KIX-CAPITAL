#!/usr/bin/env python3
"""Local fake observation endpoint. SIMULATED. Not provider evidence.

Stdlib HTTP server that delegates synthetic fact batches to
``LocalFakeObservation.fold`` and speaks the local
``OBSERVATION_HTTP_LOOPBACK`` envelope: ``POST /v1/fold`` with a body of
exactly ``{"facts": [...], "bindings": [...]}``. The label is
``LOCAL_FAKE_OBSERVATION``. There is no authentication, no durable inbox and
no recording: each POST is folded in memory and the detached SIMULATED
result is returned. ``GET /v1/counters`` reports the POST count so a caller
can prove one fold is at most one transport attempt.

This process binds ``127.0.0.1`` (or another loopback address) only. It is
not a provider contract, not fact authentication and not SEMANTIC_CONFORMANCE.
CAP-14 and CAP-16 stay NOT_BOUND. ``funds_executed`` stays false.

Fault hooks, armed in-process or with ``--fault KIND`` and consumed one per
POST in arming order:

- ``drop``: count the POST, close the connection with no response
- ``timeout``: fold, count the POST, delay the response
- ``malformed-json``: fold, count the POST, answer 200 truncated invalid JSON
- ``duplicate-key``: fold, count the POST, answer 200 with a repeated key
- ``oversized``: count the POST, answer 200 over the client read cap
- ``redirect``: count the POST, answer 302 with a loopback Location
- ``alter-identity``: fold, count the POST, rewrite result.identity_profile
- ``alter-execution``: fold, count the POST, claim executed effects

A lost response is the caller's explicit error. This server does not retry
and does not store anything.
"""
from __future__ import annotations

import argparse
import atexit
import ipaddress
import json
import socket
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital.observation import LocalFakeObservation

LABEL = 'LOCAL_FAKE_OBSERVATION'
LOOPBACK = '127.0.0.1'
MAX_BODY_BYTES = 1_048_576  # local read cap, not a financial limit
FAULTS = frozenset({
    'drop', 'timeout', 'malformed-json', 'duplicate-key', 'oversized',
    'redirect', 'alter-identity', 'alter-execution'})
REQUEST_KEYS = frozenset({'facts', 'bindings'})
_OPEN = set()


class FakeObservationError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def require_loopback(host):
    """Refuse any bind that is not an IP loopback address. No DNS lookup."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise FakeObservationError('NON_LOOPBACK_BIND') from exc
    if not address.is_loopback:
        raise FakeObservationError('NON_LOOPBACK_BIND')


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def _stamp(**fields):
    body = {
        'label': LABEL,
        'mode': 'SIMULATED',
        'binding': 'NOT_BOUND',
        'semantic_conformance': False,
        'funds_executed': False,
    }
    body.update(fields)
    return body


def _close_open_fakes():
    for fake in list(_OPEN):
        fake.close()


atexit.register(_close_open_fakes)


class FakeObservation:
    """One LocalFakeObservation behind a loopback socket. Results are SIMULATED."""

    def __init__(self, fault_delay=1.0):
        self.fault_delay = fault_delay
        self.observation = LocalFakeObservation()
        self.lock = threading.Lock()
        self.httpd = None
        self.thread = None
        self.host = None
        self.port = None
        self.url = None
        self.faults = deque()
        self.posts = 0
        self.last_request = None
        self._closed = False
        self._close_lock = threading.Lock()

    def arm(self, fault):
        if fault not in FAULTS:
            raise FakeObservationError('UNKNOWN_FAULT')
        with self.lock:
            self.faults.append(fault)

    def take_fault(self):
        with self.lock:
            return self.faults.popleft() if self.faults else None

    def note_post(self, payload):
        with self.lock:
            self.posts += 1
            self.last_request = payload

    def counters(self):
        with self.lock:
            return _stamp(posts=self.posts)

    def fold(self, payload):
        with self.lock:
            try:
                result = self.observation.fold(
                    payload['facts'], bindings=payload['bindings'])
            except ValueError:
                return None, 'FOLD_INVALID'
            return result, None

    def wait_ready(self):
        deadline = time.monotonic() + 2
        last = None
        while time.monotonic() < deadline:
            try:
                with socket.create_connection((self.host, self.port), timeout=0.2):
                    return
            except OSError as exc:
                last = exc
                time.sleep(0.01)
        raise FakeObservationError('FAKE_NOT_READY') from last

    def close(self):
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        httpd = self.httpd
        thread = self.thread
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=3)
        _OPEN.discard(self)


class ObservationHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True
    request_queue_size = 16


def _http_url(host, port):
    if ':' in host:
        return f'http://[{host}]:{port}'
    return f'http://{host}:{port}'


def start(host=LOOPBACK, port=0, fault_delay=1.0):
    """Bind a loopback socket and serve until ``close``. Refuse any other host."""
    require_loopback(host)
    fake = FakeObservation(fault_delay=fault_delay)
    try:
        httpd = ObservationHTTPServer((host, port), Handler)
    except OSError as exc:
        raise FakeObservationError('FAKE_NOT_READY') from exc
    bound_host, bound_port = httpd.server_address[:2]
    try:
        require_loopback(bound_host)
    except FakeObservationError:
        httpd.server_close()
        raise
    httpd.fake = fake
    fake.httpd = httpd
    fake.host = bound_host
    fake.port = bound_port
    fake.url = _http_url(bound_host, bound_port)
    fake.thread = threading.Thread(
        target=httpd.serve_forever, name='local-fake-observation', daemon=True)
    fake.thread.start()
    try:
        fake.wait_ready()
    except Exception:
        fake.close()
        raise
    _OPEN.add(fake)
    return fake


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = LABEL
    sys_version = ''

    def log_message(self, *_args):
        return

    def do_GET(self):
        self._route(False)

    def do_POST(self):
        self._route(True)

    def do_PUT(self):
        self._error(405, 'METHOD_NOT_ALLOWED')

    def do_DELETE(self):
        self._error(405, 'METHOD_NOT_ALLOWED')

    def _route(self, mutate):
        if not self._loopback_host():
            return
        parts = urlsplit(self.path)
        path = parts.path
        fake = self.server.fake
        try:
            if not mutate and path == '/v1/counters' and not parts.query:
                self._json(200, fake.counters())
            elif mutate and path == '/v1/fold' and not parts.query:
                self._fold()
            else:
                self._error(404, 'NOT_FOUND')
        except Exception:
            self._error(500, 'OBSERVATION_FAILED')

    def _loopback_host(self):
        expected = f'{self.server.fake.host}:{self.server.fake.port}'
        # IPv6 literal hosts are bracketed on the wire.
        if ':' in self.server.fake.host:
            expected = f'[{self.server.fake.host}]:{self.server.fake.port}'
        hosts = self.headers.get_all('Host')
        if hosts != [expected]:
            self._error(403, 'LOOPBACK_HOST_REQUIRED')
            return False
        return True

    def _fold(self):
        payload, code = self._read_json()
        if code is not None:
            self._error(400, code)
            return
        if type(payload) is not dict or set(payload) != REQUEST_KEYS \
                or type(payload['facts']) is not list \
                or type(payload['bindings']) is not list:
            self._error(400, 'ENVELOPE_INVALID')
            return
        fake = self.server.fake
        fake.note_post(payload)
        fault = fake.take_fault()
        if fault == 'drop':
            self._drop()
            return
        if fault == 'redirect':
            self._redirect()
            return
        if fault == 'oversized':
            self._json(200, _stamp(padding='x' * MAX_BODY_BYTES))
            return
        result, error = fake.fold(payload)
        if error is not None:
            self._error(400, error)
            return
        reply = _stamp(result=result)
        if fault == 'timeout':
            time.sleep(fake.fault_delay)
        elif fault == 'malformed-json':
            self._malformed(reply)
            return
        if fault == 'duplicate-key':
            self._duplicate_key(reply)
            return
        if fault == 'alter-identity':
            reply['result']['identity_profile'] = 'KERNEL_BCS_IDENTITY_V1'
        elif fault == 'alter-execution':
            reply['result']['applied'] = True
            reply['result']['funds_executed'] = True
            reply['result']['applied_effects'] = [
                _stamp(effect='RECORDED_EXTERNAL_FACT')]
        self._json(200, reply)

    def _read_json(self):
        if self.headers.get('Content-Type') != 'application/json':
            return None, 'JSON_REQUIRED'
        lengths = self.headers.get_all('Content-Length', [])
        if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit() or self.headers.get('Transfer-Encoding'):
            return None, 'INVALID_LENGTH'
        length = int(lengths[0])
        if not 0 < length <= MAX_BODY_BYTES:
            return None, 'BODY_TOO_LARGE'
        self.connection.settimeout(3)
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                return None, 'INVALID_LENGTH'
            payload = json.loads(
                raw.decode('utf-8'), object_pairs_hook=strict_object,
                parse_constant=lambda _value: (_ for _ in ()).throw(ValueError('constant')))
        except (ValueError, UnicodeError, TimeoutError, RecursionError):
            return None, 'INVALID_JSON'
        return payload, None

    def _json(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode('ascii')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(raw)

    def _error(self, status, code):
        try:
            self._json(status, _stamp(error=code))
        except OSError:
            return

    def _malformed(self, reply):
        """200 with a truncated body. Nothing is stored to retry against."""
        raw = json.dumps(
            reply, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode('ascii')
        raw = raw[: max(1, len(raw) // 2)]
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(raw)

    def _duplicate_key(self, reply):
        """200 whose body repeats one envelope key. The strict parser must fail."""
        raw = json.dumps(
            reply, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode('ascii')
        needle = b'"funds_executed":false'
        if needle not in raw:
            self._error(500, 'OBSERVATION_FAILED')
            return
        raw = raw.replace(needle, needle + b',"funds_executed":true', 1)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(raw)

    def _redirect(self):
        """302 to a loopback Location. The client must refuse, not follow."""
        self.send_response(302)
        self.send_header('Location', self.server.fake.url + '/v1/fold')
        self.send_header('Content-Length', '0')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()

    def _drop(self):
        """Close with no status line. The client must report unavailable."""
        self.close_connection = True
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            return


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default=LOOPBACK, help='Loopback address only. Any other host is NON_LOOPBACK_BIND.')
    parser.add_argument('--port', type=int, default=8792)
    parser.add_argument('--fault', action='append', default=[],
                        help='Opt-in fault, one per POST in order: ' + '|'.join(sorted(FAULTS)) + '. Not a production control.')
    parser.add_argument('--fault-delay', type=float, default=1.0, help='Seconds a timeout fault waits before answering.')
    args = parser.parse_args(argv)
    try:
        fake = start(args.host, args.port, fault_delay=args.fault_delay)
    except FakeObservationError as exc:
        print(f'fake observation refused: {exc.code}', file=sys.stderr)
        return 2
    try:
        for fault in args.fault:
            fake.arm(fault)
    except FakeObservationError as exc:
        print(f'fake observation refused: {exc.code}', file=sys.stderr)
        fake.close()
        return 2
    print(
        f'{LABEL} {fake.url} mode=SIMULATED binding=NOT_BOUND semantic_conformance=false',
        flush=True)
    try:
        fake.thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        fake.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
