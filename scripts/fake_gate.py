#!/usr/bin/env python3
"""Local fake integration gate. SIMULATED. Not a promoted catalogue.

Stdlib HTTP server that wraps ``PinnedFsmProducer`` and speaks the
``GATE_HTTP_LOOPBACK`` envelope ``{operationId, actor, action, body}`` from
``docs/decisions/CAPITAL_UPSTREAM_BINDING.md`` section 3.1. The label is
``LOCAL_FAKE_GATE``. ``actor`` is not authentication. Unknown fields are
rejected. ``operationId`` must equal ``operation_id``.

This process binds ``127.0.0.1`` (or another loopback address) only. It does
not pin OpenAPI, ship a TypeScript SDK, or claim SEMANTIC_CONFORMANCE.
CAP-16 stays NOT_BOUND. No real money moves. ``funds_executed`` stays false.

Fault hooks, armed in-process or with ``--fault OPERATION_ID:KIND``:

- ``drop-before``: count the POST, do not apply, close with no response
- ``drop-after``: apply, store the original receipt, count the POST, close
- ``timeout``: apply and store, count the POST, then delay the response

A lost response is the caller's UNKNOWN. This server does not retry.
"""
from __future__ import annotations

import argparse
import atexit
import copy
import ipaddress
import json
import re
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital.producer import CreditError, PinnedFsmProducer

LABEL = 'LOCAL_FAKE_GATE'
LOOPBACK = '127.0.0.1'
MAX_BODY_BYTES = 1_048_576  # local read cap, not a financial limit
FAULTS = frozenset({'drop-before', 'drop-after', 'timeout'})
ENVELOPE_KEYS = frozenset({'operationId', 'actor', 'action', 'body'})
BODY_KEYS = frozenset({'operation_id', 'advance_id', 'args', 'bound_settlement_id'})
COMMANDS = {
    'offer': frozenset({'fixture_id', 'amount'}),
    'approve': frozenset(),
    'reject': frozenset(),
    'cancel': frozenset(),
    'bind_settlement': frozenset(),
    'draw': frozenset(),
    'repay': frozenset({'amount', 'sequence'}),
    'close': frozenset(),
    'default': frozenset(),
    'reconcile': frozenset(),
}
_ID = re.compile(r'[A-Za-z0-9-]{1,80}\Z')
_ACTOR = re.compile(r'[A-Za-z0-9._:-]{1,80}\Z')
_OPEN = set()


class FakeGateError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class SchemaError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def require_loopback(host):
    """Refuse any bind that is not an IP loopback address. No DNS lookup."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise FakeGateError('NON_LOOPBACK_BIND') from exc
    if not address.is_loopback:
        raise FakeGateError('NON_LOOPBACK_BIND')


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
        'profile_kind': 'NOT_BOUND',
        'catalogue': 'NOT_BOUND',
        'semantic_conformance': False,
        'funds_executed': False,
    }
    body.update(fields)
    return body


def parse_command(payload):
    """Reject unknown fields. ``operationId`` must equal body ``operation_id``."""
    if type(payload) is not dict:
        raise SchemaError('ENVELOPE_INVALID')
    if set(payload) - ENVELOPE_KEYS:
        raise SchemaError('UNKNOWN_FIELDS')
    if set(payload) != ENVELOPE_KEYS:
        raise SchemaError('ENVELOPE_INVALID')
    operation_id = payload['operationId']
    actor = payload['actor']
    action = payload['action']
    body = payload['body']
    if type(operation_id) is not str or _ID.fullmatch(operation_id) is None:
        raise SchemaError('ENVELOPE_INVALID')
    if type(actor) is not str or _ACTOR.fullmatch(actor) is None:
        raise SchemaError('ENVELOPE_INVALID')
    if type(action) is not str or action not in COMMANDS:
        raise SchemaError('UNKNOWN_ACTION')
    if type(body) is not dict:
        raise SchemaError('ENVELOPE_INVALID')
    if set(body) - BODY_KEYS:
        raise SchemaError('UNKNOWN_FIELDS')
    if set(body) != BODY_KEYS:
        raise SchemaError('ENVELOPE_INVALID')
    if body['operation_id'] != operation_id:
        if type(body['operation_id']) is str:
            raise SchemaError('OPERATION_ID_MISMATCH')
        raise SchemaError('ENVELOPE_INVALID')
    advance_id = body['advance_id']
    if type(advance_id) is not str or _ID.fullmatch(advance_id) is None:
        raise SchemaError('ENVELOPE_INVALID')
    args = body['args']
    if type(args) is not dict:
        raise SchemaError('ENVELOPE_INVALID')
    allowed = COMMANDS[action]
    if set(args) - allowed:
        raise SchemaError('UNKNOWN_FIELDS')
    if set(args) != allowed:
        raise SchemaError('ENVELOPE_INVALID')
    for key, value in args.items():
        if key == 'fixture_id':
            if type(value) is not str or not 1 <= len(value) <= 80:
                raise SchemaError('INVALID_TYPE')
        elif type(value) is not int or abs(value) > 10**18:
            raise SchemaError('INVALID_TYPE')
    bound = body['bound_settlement_id']
    if bound is not None and (type(bound) is not str or _ID.fullmatch(bound) is None):
        raise SchemaError('INVALID_TYPE' if type(bound) is not str else 'ENVELOPE_INVALID')
    return payload


def _close_open_gates():
    for gate in list(_OPEN):
        gate.close()


atexit.register(_close_open_gates)


class FakeGate:
    """One pinned producer behind a loopback socket. Receipts are SIMULATED."""

    def __init__(self, fault_delay=1.0):
        self.fault_delay = fault_delay
        self.producer = PinnedFsmProducer()
        self.lock = threading.Lock()
        self.httpd = None
        self.thread = None
        self.host = None
        self.port = None
        self.url = None
        self.faults = {}
        self.post_counts = {}
        self.post_log = []
        self.original_receipts = {}
        self.last_request = None
        self._closed = False
        self._close_lock = threading.Lock()

    def arm(self, operation_id, fault):
        if fault not in FAULTS:
            raise FakeGateError('UNKNOWN_FAULT')
        if type(operation_id) is not str or _ID.fullmatch(operation_id) is None:
            raise FakeGateError('INVALID_OPERATION_ID')
        with self.lock:
            self.faults[operation_id] = fault

    def take_fault(self, operation_id):
        with self.lock:
            return self.faults.pop(operation_id, None)

    def note_post(self, operation_id):
        with self.lock:
            self.post_counts[operation_id] = self.post_counts.get(operation_id, 0) + 1
            self.post_log.append(operation_id)

    def post_count(self, operation_id):
        with self.lock:
            return self.post_counts.get(operation_id, 0)

    def counters(self):
        with self.lock:
            return dict(self.post_counts)

    def receipt(self, operation_id):
        with self.lock:
            stored = self.original_receipts.get(operation_id)
            return None if stored is None else copy.deepcopy(stored)

    def apply_command(self, envelope):
        operation_id = envelope['operationId']
        action = envelope['action']
        actor = envelope['actor']
        body = envelope['body']
        with self.lock:
            try:
                result = self.producer.apply(
                    action, body['advance_id'], idempotency_key=body['operation_id'],
                    args=body['args'], bound_settlement_id=body['bound_settlement_id'])
            except CreditError as exc:
                receipt = _stamp(
                    operationId=operation_id, action=action, actor=actor,
                    actor_is_authentication=False, outcome='REJECTED', error=exc.code, result=None)
            else:
                receipt = _stamp(
                    operationId=operation_id, action=action, actor=actor,
                    actor_is_authentication=False, outcome='ACCEPTED', error=None, result=result)
            # The first response is the original receipt. A later POST may be a
            # duplicate replay; GET keeps the first one. This server does not retry.
            self.original_receipts.setdefault(operation_id, copy.deepcopy(receipt))
            self.last_request = copy.deepcopy(envelope)
            return copy.deepcopy(receipt)

    def read_state(self):
        with self.lock:
            return _stamp(
                state_digest=self.producer.state_digest(),
                canonical_state=self.producer.canonical_state())

    def read_journal(self):
        with self.lock:
            return _stamp(journal=self.producer.export_journal())

    def read_view(self, advance_id):
        with self.lock:
            try:
                view = self.producer.view(advance_id)
            except CreditError as exc:
                return None, exc.code
            return _stamp(advance_id=advance_id, view=view), None

    def preview(self, advance_id):
        with self.lock:
            try:
                result = self.producer.preview_draw(advance_id)
            except CreditError as exc:
                return _stamp(outcome='REJECTED', error=exc.code, result=None)
            return _stamp(outcome='ACCEPTED', error=None, result=result)

    def reset_book(self):
        with self.lock:
            self.producer.reset()
            self.original_receipts.clear()
            self.post_counts.clear()
            self.post_log.clear()
            self.last_request = None
            return _stamp(reset=True)

    def restore_journal(self, journal):
        with self.lock:
            try:
                self.producer = self.producer.restored(journal)
            except CreditError as exc:
                return None, exc.code
            self.original_receipts.clear()
            self.post_counts.clear()
            self.post_log.clear()
            self.last_request = None
            return _stamp(state_digest=self.producer.state_digest()), None

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
        raise FakeGateError('GATE_NOT_READY') from last

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


class GateHTTPServer(ThreadingHTTPServer):
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
    gate = FakeGate(fault_delay=fault_delay)
    try:
        httpd = GateHTTPServer((host, port), Handler)
    except OSError as exc:
        raise FakeGateError('GATE_NOT_READY') from exc
    bound_host, bound_port = httpd.server_address[:2]
    try:
        require_loopback(bound_host)
    except FakeGateError:
        httpd.server_close()
        raise
    httpd.gate = gate
    gate.httpd = httpd
    gate.host = bound_host
    gate.port = bound_port
    gate.url = _http_url(bound_host, bound_port)
    gate.thread = threading.Thread(target=httpd.serve_forever, name='local-fake-gate', daemon=True)
    gate.thread.start()
    try:
        gate.wait_ready()
    except Exception:
        gate.close()
        raise
    _OPEN.add(gate)
    return gate


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
        gate = self.server.gate
        try:
            if not mutate and path == '/v1/state' and not parts.query:
                self._json(200, gate.read_state())
            elif not mutate and path == '/v1/journal' and not parts.query:
                self._json(200, gate.read_journal())
            elif not mutate and path == '/v1/counters' and not parts.query:
                self._json(200, _stamp(post_counts=gate.counters()))
            elif not mutate and path == '/v1/view':
                self._view(parts.query)
            elif not mutate and path.startswith('/v1/receipts/'):
                self._receipt(path[len('/v1/receipts/'):], parts.query)
            elif mutate and path == '/v1/commands':
                self._command()
            elif mutate and path == '/v1/preview':
                self._preview()
            elif mutate and path == '/v1/reset':
                self._reset()
            elif mutate and path == '/v1/restore':
                self._restore()
            else:
                self._error(404, 'NOT_FOUND')
        except Exception:
            self._error(500, 'GATE_FAILED')

    def _loopback_host(self):
        expected = f'{self.server.gate.host}:{self.server.gate.port}'
        # IPv6 literal hosts are bracketed on the wire.
        if ':' in self.server.gate.host:
            expected = f'[{self.server.gate.host}]:{self.server.gate.port}'
        hosts = self.headers.get_all('Host')
        if hosts != [expected]:
            self._error(403, 'LOOPBACK_HOST_REQUIRED')
            return False
        return True

    def _view(self, query):
        parsed = parse_qs(query, keep_blank_values=True)
        if set(parsed) - {'advance_id'}:
            self._error(400, 'UNKNOWN_FIELDS')
            return
        values = parsed.get('advance_id')
        if values is None or len(values) != 1 or _ID.fullmatch(values[0]) is None:
            self._error(400, 'ENVELOPE_INVALID')
            return
        body, code = self.server.gate.read_view(values[0])
        if code is not None:
            self._error(404, code)
            return
        self._json(200, body)

    def _receipt(self, operation_id, query):
        if query or _ID.fullmatch(operation_id) is None:
            self._error(404, 'NOT_FOUND')
            return
        stored = self.server.gate.receipt(operation_id)
        if stored is None:
            self._error(404, 'NOT_FOUND')
            return
        self._json(200, stored)

    def _command(self):
        payload, code = self._read_json()
        if code is not None:
            self._error(400, code)
            return
        try:
            envelope = parse_command(payload)
        except SchemaError as exc:
            self._error(400, exc.code)
            return
        gate = self.server.gate
        operation_id = envelope['operationId']
        fault = gate.take_fault(operation_id)
        if fault == 'drop-before':
            gate.note_post(operation_id)
            self._drop()
            return
        receipt = gate.apply_command(envelope)
        gate.note_post(operation_id)
        if fault == 'drop-after':
            self._drop()
            return
        if fault == 'timeout':
            time.sleep(gate.fault_delay)
        self._json(200, receipt)

    def _preview(self):
        payload, code = self._read_json()
        if code is not None:
            self._error(400, code)
            return
        if type(payload) is not dict:
            self._error(400, 'ENVELOPE_INVALID')
            return
        if set(payload) - {'advance_id'}:
            self._error(400, 'UNKNOWN_FIELDS')
            return
        if set(payload) != {'advance_id'}:
            self._error(400, 'ENVELOPE_INVALID')
            return
        advance_id = payload['advance_id']
        if type(advance_id) is not str or _ID.fullmatch(advance_id) is None:
            self._error(400, 'ENVELOPE_INVALID')
            return
        self._json(200, self.server.gate.preview(advance_id))

    def _reset(self):
        payload, code = self._read_json()
        if code is not None:
            self._error(400, code)
            return
        if type(payload) is not dict:
            self._error(400, 'ENVELOPE_INVALID')
            return
        if set(payload):
            self._error(400, 'UNKNOWN_FIELDS')
            return
        self._json(200, self.server.gate.reset_book())

    def _restore(self):
        payload, code = self._read_json()
        if code is not None:
            self._error(400, code)
            return
        if type(payload) is not dict:
            self._error(400, 'ENVELOPE_INVALID')
            return
        if set(payload) - {'journal'}:
            self._error(400, 'UNKNOWN_FIELDS')
            return
        if set(payload) != {'journal'} or type(payload['journal']) is not list:
            self._error(400, 'ENVELOPE_INVALID')
            return
        body, error = self.server.gate.restore_journal(payload['journal'])
        if error is not None:
            self._error(400, error)
            return
        self._json(200, body)

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

    def _drop(self):
        """Close with no status line. The client must treat that as UNKNOWN."""
        self.close_connection = True
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            return


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default=LOOPBACK, help='Loopback address only. Any other host is NON_LOOPBACK_BIND.')
    parser.add_argument('--port', type=int, default=8791)
    parser.add_argument('--fault', action='append', default=[],
                        help='Opt-in fault OPERATION_ID:drop-before|drop-after|timeout. Not a production control.')
    parser.add_argument('--fault-delay', type=float, default=1.0, help='Seconds a timeout fault waits after apply.')
    args = parser.parse_args(argv)
    try:
        gate = start(args.host, args.port, fault_delay=args.fault_delay)
    except FakeGateError as exc:
        print(f'fake gate refused: {exc.code}', file=sys.stderr)
        return 2
    try:
        for item in args.fault:
            operation_id, separator, fault = item.partition(':')
            if not separator:
                raise FakeGateError('UNKNOWN_FAULT')
            gate.arm(operation_id, fault)
    except FakeGateError as exc:
        print(f'fake gate refused: {exc.code}', file=sys.stderr)
        gate.close()
        return 2
    print(
        f'{LABEL} {gate.url} mode=SIMULATED binding=NOT_BOUND semantic_conformance=false',
        flush=True)
    try:
        gate.thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        gate.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
