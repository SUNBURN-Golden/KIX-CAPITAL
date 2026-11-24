"""HTTP client for the local fake observation endpoint.

``ObservationHttpAdapter`` is an ``ObservationPort``. It POSTs one synthetic
batch ``{"facts": [...], "bindings": [...]}`` per ``fold`` call to
``scripts/fake_observation.py`` on ``127.0.0.1`` and returns the fake's
SIMULATED result verbatim. The label is ``LOCAL_FAKE_OBSERVATION``. There is
no authentication, recording, durable inbox or webhook: the transport only
exercises the unchanged port contract over a bounded loopback.

One ``fold`` call makes at most one transport attempt and never retries. A
lost connection, timeout or empty reply raises ``ObservationUnavailable``; a
redirected, oversized, malformed or dishonestly stamped reply raises
``ObservationProtocolError``. Neither is ever an empty successful fold. This
is not SEMANTIC_CONFORMANCE. CAP-14 and CAP-16 stay NOT_BOUND. No real money
moves.
"""
from __future__ import annotations

import http.client
import importlib.util
import ipaddress
import json
import socket
import sys
import time
from contextlib import suppress
from http.client import HTTPException
from pathlib import Path
from threading import Timer
from urllib.parse import urlsplit

from capital import observation
from capital.resources import ROOT
from capital.strict_json import loads as strict_loads

LABEL = 'LOCAL_FAKE_OBSERVATION'
# Transport limits for synthetic fixture data.
MAX_REQUEST_BYTES = MAX_REPLY_BYTES = 1_048_576
MAX_TIMEOUT_SECONDS = 30
_FAKE_MODULE = 'kix_capital_fake_observation'
STAMP_KEYS = frozenset({'label', 'mode', 'binding', 'semantic_conformance', 'funds_executed'})
ROW_STAMPS = frozenset({'label', 'applied', 'funds_executed'})
RESULT_KEYS = frozenset({
    'label', 'applied', 'funds_executed', 'identity_profile', 'binding_status',
    'semantic_conformance', 'event_items', 'deliveries', 'duplicates',
    'conflicts', 'applied_effects'})
ROW_FIELDS = {
    'event_items': {'event_item_id': str, 'scoped_key': dict, 'normalized_fact': dict,
                    'evidence_digest': str, 'status': str, 'binding_status': str},
    'deliveries': {'event_item_id': str, 'transmission': dict},
    'duplicates': {'event_item_id': str, 'delivery_index': int},
    'conflicts': {'event_item_id': str, 'original': dict, 'incoming': dict,
                  'evidence_digest': str, 'delivery_index': int},
}


class ObservationUnavailable(Exception):
    """The transport lost the single attempt. Never an empty successful fold."""

    def __init__(self, code='OBSERVATION_UNAVAILABLE'):
        super().__init__(code)
        self.code = code


class ObservationProtocolError(Exception):
    """The endpoint answered, and the answer is not a simulated fold result."""

    def __init__(self, code, status=None):
        super().__init__(code)
        self.code = code
        self.status = status


def load_fake_observation():
    """Load ``scripts/fake_observation.py`` from a source checkout.

    The zipapp does not bundle ``scripts/``. A packaged process fails closed
    with ``FAKE_OBSERVATION_UNAVAILABLE`` instead of binding anything.
    """
    cached = sys.modules.get(_FAKE_MODULE)
    if cached is not None:
        return cached
    path = Path(str(ROOT)).parent / 'scripts' / 'fake_observation.py'
    if not path.is_file():
        raise ObservationUnavailable('FAKE_OBSERVATION_UNAVAILABLE')
    spec = importlib.util.spec_from_file_location(_FAKE_MODULE, path)
    if spec is None or spec.loader is None:
        raise ObservationUnavailable('FAKE_OBSERVATION_UNAVAILABLE')
    module = importlib.util.module_from_spec(spec)
    sys.modules[_FAKE_MODULE] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(_FAKE_MODULE, None)
        raise
    return module


def _honest(payload):
    """Envelope stamps every reply must keep, success or error."""
    if type(payload) is not dict:
        raise ObservationProtocolError('ENVELOPE_INVALID')
    if payload.get('label') != LABEL or payload.get('mode') != 'SIMULATED' \
            or payload.get('binding') != 'NOT_BOUND':
        raise ObservationProtocolError('LABEL_MISMATCH')
    if payload.get('semantic_conformance') is not False:
        raise ObservationProtocolError('CONFORMANCE_CLAIM_REFUSED')
    if payload.get('funds_executed') is not False:
        raise ObservationProtocolError('FUNDS_EXECUTED')
    return payload


def _check_safe(entry):
    if type(entry) is not dict:
        raise ObservationProtocolError('ENVELOPE_INVALID')
    if entry.get('label') != 'SIMULATED':
        raise ObservationProtocolError('LABEL_MISMATCH')
    if entry.get('funds_executed') is not False:
        raise ObservationProtocolError('FUNDS_EXECUTED')
    if entry.get('applied') is not False:
        raise ObservationProtocolError('EFFECTS_CLAIMED')


def _validated_result(payload):
    """The reply's ``result`` must be the honest detached fold contract."""
    if payload.keys() != STAMP_KEYS | {'result'}:
        raise ObservationProtocolError('ENVELOPE_INVALID')
    result = payload['result']
    if type(result) is not dict or set(result) != RESULT_KEYS:
        raise ObservationProtocolError('ENVELOPE_INVALID')
    _check_safe(result)
    if result['semantic_conformance'] is not False:
        raise ObservationProtocolError('CONFORMANCE_CLAIM_REFUSED')
    if result['binding_status'] != 'NOT_BOUND':
        raise ObservationProtocolError('LABEL_MISMATCH')
    if result['identity_profile'] != observation.PROFILE:
        raise ObservationProtocolError('IDENTITY_MISMATCH')
    if result['applied_effects'] != []:
        raise ObservationProtocolError('EFFECTS_CLAIMED')
    for name, fields in ROW_FIELDS.items():
        entries = result[name]
        if type(entries) is not list:
            raise ObservationProtocolError('ENVELOPE_INVALID')
        for entry in entries:
            _check_safe(entry)
            if entry.keys() != ROW_STAMPS | fields.keys() or any(
                    type(entry[field]) is not kind for field, kind in fields.items()):
                raise ObservationProtocolError('ENVELOPE_INVALID')
    return result


def _loopback_endpoint(base_url):
    """Refuse anything but a literal loopback IP URL. No DNS lookup."""
    if type(base_url) is not str:
        raise ObservationProtocolError('NON_LOOPBACK')
    try:
        parts = urlsplit(base_url)
        port = parts.port
    except ValueError as exc:
        raise ObservationProtocolError('NON_LOOPBACK') from exc
    if parts.scheme != 'http' or not port \
            or parts.path not in ('', '/') or parts.query or parts.fragment \
            or parts.username is not None or parts.password is not None:
        raise ObservationProtocolError('NON_LOOPBACK')
    try:
        address = ipaddress.ip_address(parts.hostname or '')
    except ValueError as exc:
        raise ObservationProtocolError('NON_LOOPBACK') from exc
    if not address.is_loopback or '%' in str(address):
        raise ObservationProtocolError('NON_LOOPBACK')
    return str(address), port


def _interrupt(connection_socket):
    # Interrupt a buffered header or body read when the whole attempt expires.
    with suppress(OSError):
        connection_socket.shutdown(socket.SHUT_RDWR)


class ObservationHttpAdapter:
    """Opt-in ``ObservationPort`` over ``LOCAL_FAKE_OBSERVATION``. Not SEMANTIC_CONFORMANCE."""

    label = LABEL
    semantic_conformance = False

    def __init__(self, base_url=None, timeout=5.0, fake=None):
        if type(timeout) not in (int, float) or not 0 < timeout <= MAX_TIMEOUT_SECONDS:
            raise ObservationProtocolError('ENVELOPE_INVALID')
        self.timeout = timeout
        self._owned = False
        self._closed = False
        if fake is not None:
            self.fake = fake
            base_url = fake.url
        elif base_url is None:
            module = load_fake_observation()
            self.fake = module.start()
            base_url = self.fake.url
            self._owned = True
        else:
            self.fake = None
        try:
            self._host, self._port = _loopback_endpoint(base_url)
        except ObservationProtocolError:
            self.close()
            raise
        self.base_url = base_url.rstrip('/')
        host = f'[{self._host}]' if ':' in self._host else self._host
        self._authority = f'{host}:{self._port}'

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._owned and self.fake is not None:
            self.fake.close()

    def fold(self, facts, *, bindings) -> dict:
        """POST once. A lost or dishonest response raises; nothing is retried."""
        if not isinstance(facts, list):
            raise ValueError('facts must be a list')
        if not isinstance(bindings, list):
            raise ValueError('bindings must be a synthetic list')
        status, payload = self._request(
            'POST', '/v1/fold', {'facts': facts, 'bindings': bindings})
        _honest(payload)
        if status != 200:
            code = self._error_code(payload, status)
            if status == 400:
                raise ValueError(code)
            raise ObservationProtocolError(code, status)
        result = _validated_result(payload)
        if len(result['deliveries']) != len(facts):
            raise ObservationProtocolError('ENVELOPE_INVALID', status)
        return result

    def post_count(self):
        """POST counter observed over HTTP. This client does not add a retry."""
        status, payload = self._request('GET', '/v1/counters')
        _honest(payload)
        if status != 200:
            raise ObservationProtocolError(self._error_code(payload, status), status)
        posts = payload.get('posts')
        if payload.keys() != STAMP_KEYS | {'posts'} or type(posts) is not int or posts < 0:
            raise ObservationProtocolError('ENVELOPE_INVALID')
        return posts

    @staticmethod
    def _error_code(payload, status):
        if payload.keys() != STAMP_KEYS | {'error'} or type(payload['error']) is not str:
            raise ObservationProtocolError('ENVELOPE_INVALID', status)
        return payload['error']

    def _request(self, method, path, payload=None):
        """One attempt, explicit bounds; transport loss is ``ObservationUnavailable``."""
        if self._closed:
            raise ObservationUnavailable()
        data = None
        headers = {'Accept': 'application/json', 'Connection': 'close',
                   'Host': self._authority}
        if payload is not None:
            try:
                data = json.dumps(payload, ensure_ascii=True, allow_nan=False,
                                  separators=(',', ':')).encode('ascii')
            except (TypeError, ValueError, RecursionError) as exc:
                raise ValueError('INVALID_JSON') from exc
            if len(data) > MAX_REQUEST_BYTES:
                raise ValueError('BODY_TOO_LARGE')
            headers['Content-Type'] = 'application/json'
        connection = http.client.HTTPConnection(self._host, self._port, timeout=self.timeout)
        deadline = time.monotonic() + self.timeout
        timer = None
        try:
            connection.connect()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ObservationUnavailable()
            timer = Timer(remaining, _interrupt, args=(connection.sock,))
            timer.daemon = True
            timer.start()
            connection.request(method, path, body=data, headers=headers)
            with connection.getresponse() as response:
                status = response.status
                if 300 <= status < 400:
                    raise ObservationProtocolError('REDIRECT_REFUSED', status)
                length = response.length
                lengths = response.headers.get_all('Content-Length', [])
                if lengths and (len(lengths) != 1 or not lengths[0].isascii()
                                or not lengths[0].isdigit() or length is None):
                    raise ObservationProtocolError('ENVELOPE_INVALID', status)
                if length is not None and length > MAX_REPLY_BYTES:
                    raise ObservationProtocolError('REPLY_TOO_LARGE', status)
                raw = response.read(MAX_REPLY_BYTES + 1)
                if length is not None and len(raw) < length:
                    raise ObservationUnavailable()
        except (OSError, HTTPException) as exc:
            raise ObservationUnavailable() from exc
        finally:
            if timer is not None:
                timer.cancel()
            connection.close()
        if not raw or time.monotonic() >= deadline:
            raise ObservationUnavailable()
        if len(raw) > MAX_REPLY_BYTES:
            raise ObservationProtocolError('REPLY_TOO_LARGE', status)
        try:
            parsed = strict_loads(raw)
        except (ValueError, RecursionError) as exc:
            raise ObservationProtocolError('INVALID_JSON', status) from exc
        return status, parsed
