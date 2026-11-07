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
import sys
from http.client import HTTPException
from pathlib import Path
from urllib.parse import urlsplit

from capital import observation
from capital.ports import ObservationPort
from capital.resources import ROOT
from capital.strict_json import loads as strict_loads

LABEL = 'LOCAL_FAKE_OBSERVATION'
MAX_REPLY_BYTES = 1_048_576  # local read cap, not a financial limit
_FAKE_MODULE = 'kix_capital_fake_observation'
ENVELOPE_KEYS = frozenset({
    'label', 'mode', 'binding', 'semantic_conformance', 'funds_executed', 'result'})
ERROR_KEYS = frozenset({
    'label', 'mode', 'binding', 'semantic_conformance', 'funds_executed', 'error'})
RESULT_KEYS = frozenset({
    'label', 'applied', 'funds_executed', 'identity_profile', 'binding_status',
    'semantic_conformance', 'event_items', 'deliveries', 'duplicates',
    'conflicts', 'applied_effects'})
RESULT_LISTS = ('event_items', 'deliveries', 'duplicates', 'conflicts')
REDIRECTS = frozenset({301, 302, 303, 307, 308})


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
    if set(payload) != ENVELOPE_KEYS:
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
    for name in RESULT_LISTS:
        entries = result[name]
        if type(entries) is not list:
            raise ObservationProtocolError('ENVELOPE_INVALID')
        for entry in entries:
            _check_safe(entry)
    return result


def _loopback_base_url(base_url):
    """Refuse anything but a literal loopback IP URL. No DNS lookup."""
    if type(base_url) is not str:
        raise ObservationProtocolError('NON_LOOPBACK')
    try:
        parts = urlsplit(base_url)
        port = parts.port
    except ValueError as exc:
        raise ObservationProtocolError('NON_LOOPBACK') from exc
    if parts.scheme != 'http' or port is None \
            or parts.path not in ('', '/') or parts.query or parts.fragment \
            or parts.username is not None or parts.password is not None:
        raise ObservationProtocolError('NON_LOOPBACK')
    try:
        address = ipaddress.ip_address(parts.hostname or '')
    except ValueError as exc:
        raise ObservationProtocolError('NON_LOOPBACK') from exc
    if not address.is_loopback:
        raise ObservationProtocolError('NON_LOOPBACK')
    return base_url.rstrip('/')


class ObservationHttpAdapter:
    """Opt-in ``ObservationPort`` over ``LOCAL_FAKE_OBSERVATION``. Not SEMANTIC_CONFORMANCE."""

    label = LABEL
    semantic_conformance = False

    def __init__(self, base_url=None, timeout=5.0, fake=None):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not timeout > 0:
            raise ObservationProtocolError('ENVELOPE_INVALID')
        self.timeout = timeout
        self._owned = False
        self._closed = False
        if fake is not None:
            self.fake = fake
            self.base_url = fake.url
        elif base_url is None:
            module = load_fake_observation()
            self.fake = module.start()
            self.base_url = self.fake.url
            self._owned = True
        else:
            self.fake = None
            self.base_url = _loopback_base_url(base_url)
        if not isinstance(self, ObservationPort):
            self.close()
            raise ObservationProtocolError('NOT_AN_OBSERVATION')

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._owned and self.fake is not None:
            self.fake.close()

    def fold(self, facts, *, bindings):
        """POST once. A lost or dishonest response raises; nothing is retried."""
        if not isinstance(facts, list):
            raise ValueError('facts must be a list')
        if not isinstance(bindings, list):
            raise ValueError('bindings must be a synthetic list')
        status, payload = self._request(
            'POST', '/v1/fold', {'facts': facts, 'bindings': bindings})
        if status == 400:
            _honest(payload)
            code = payload.get('error')
            if set(payload) != ERROR_KEYS or type(code) is not str:
                raise ObservationProtocolError('ENVELOPE_INVALID', status)
            raise ValueError(code)
        if status != 200:
            raise ObservationProtocolError(
                payload.get('error') if type(payload) is dict else 'OBSERVATION_FAILED',
                status)
        _honest(payload)
        return _validated_result(payload)

    def post_count(self):
        """POST counter observed over HTTP. This client does not add a retry."""
        status, payload = self._request('GET', '/v1/counters')
        if status != 200:
            raise ObservationProtocolError(
                payload.get('error') if type(payload) is dict else 'LOOKUP_FAILED')
        _honest(payload)
        posts = payload.get('posts')
        if type(posts) is not int:
            raise ObservationProtocolError('ENVELOPE_INVALID')
        return posts

    def _request(self, method, path, payload=None):
        """One attempt, explicit bounds; transport loss is ``ObservationUnavailable``."""
        data = None
        headers = {'Accept': 'application/json', 'Host': self._host_header()}
        if payload is not None:
            data = json.dumps(
                payload, ensure_ascii=True, sort_keys=True,
                separators=(',', ':')).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        connection = http.client.HTTPConnection(
            self._host(), self._port(), timeout=self.timeout)
        try:
            connection.request(method, path, body=data, headers=headers)
            response = connection.getresponse()
            status = response.status
            raw = response.read(MAX_REPLY_BYTES + 1)
        except (OSError, HTTPException) as exc:
            raise ObservationUnavailable('OBSERVATION_UNAVAILABLE') from exc
        finally:
            connection.close()
        if status in REDIRECTS:
            raise ObservationProtocolError('REDIRECT_REFUSED', status)
        if len(raw) > MAX_REPLY_BYTES:
            raise ObservationProtocolError('REPLY_TOO_LARGE', status)
        if not raw:
            raise ObservationUnavailable('OBSERVATION_UNAVAILABLE')
        try:
            parsed = strict_loads(raw)
        except (ValueError, RecursionError) as exc:
            raise ObservationProtocolError('INVALID_JSON', status) from exc
        return status, parsed

    def _host(self):
        return urlsplit(self.base_url).hostname

    def _port(self):
        return urlsplit(self.base_url).port

    def _host_header(self):
        return self.base_url.split('://', 1)[1]


# Structural check at import. A missing method fails here, not at a call site.
_ = ObservationPort
