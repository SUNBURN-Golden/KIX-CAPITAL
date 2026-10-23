"""HTTP client for the local fake integration gate.

``GateHttpProducer`` is a ``ProducerPort``. It posts
``{operationId, actor, action, body}`` to ``scripts/fake_gate.py`` on
``127.0.0.1``. The label is ``LOCAL_FAKE_GATE``. ``actor`` is not
authentication. ``operationId`` is the Capital ``operation_id`` and, on this
facade, the pinned FSM idempotency key.

A response that does not arrive is ``UNKNOWN``. This client posts that
command once and does not retry. CAP-16 stays NOT_BOUND. Passing producer
vectors is not SEMANTIC_CONFORMANCE. No real money moves.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import urllib.error
import urllib.request
from http.client import HTTPException
from pathlib import Path

from capital.ports import ProducerPort
from capital.producer import CreditError, FixtureViews
from capital.resources import ROOT

LABEL = 'LOCAL_FAKE_GATE'
_FAKE_GATE_MODULE = 'kix_capital_fake_gate'


class GateUnavailable(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class GateProtocolError(Exception):
    """The gate answered, and the answer is not a simulated command result."""

    def __init__(self, code, status=None):
        super().__init__(code)
        self.code = code
        self.status = status


class GateConflict(CreditError):
    """A replayed ``operationId`` whose body conflicts with the first."""


class TransportLost(Exception):
    def __init__(self, operation_id):
        super().__init__('UNKNOWN')
        self.code = 'UNKNOWN'
        self.operation_id = operation_id


class ProducerUnknown(TransportLost):
    """The command POST did not complete. Do not send it again."""

    def __init__(self, operation_id):
        super().__init__(operation_id)
        self.outcome = 'UNKNOWN'
        self.retry_authorized = False


def load_fake_gate():
    """Load ``scripts/fake_gate.py`` from a source checkout.

    The zipapp does not bundle ``scripts/``. A packaged process fails closed
    with ``FAKE_GATE_UNAVAILABLE`` instead of binding anything.
    """
    cached = sys.modules.get(_FAKE_GATE_MODULE)
    if cached is not None:
        return cached
    path = Path(str(ROOT)).parent / 'scripts' / 'fake_gate.py'
    if not path.is_file():
        raise GateUnavailable('FAKE_GATE_UNAVAILABLE')
    spec = importlib.util.spec_from_file_location(_FAKE_GATE_MODULE, path)
    if spec is None or spec.loader is None:
        raise GateUnavailable('FAKE_GATE_UNAVAILABLE')
    module = importlib.util.module_from_spec(spec)
    sys.modules[_FAKE_GATE_MODULE] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(_FAKE_GATE_MODULE, None)
        raise
    return module


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def _honest(payload):
    if type(payload) is not dict:
        raise GateProtocolError('ENVELOPE_INVALID')
    if payload.get('label') != LABEL:
        raise GateProtocolError('LABEL_MISMATCH')
    if payload.get('mode') != 'SIMULATED':
        raise GateProtocolError('LABEL_MISMATCH')
    if payload.get('binding') != 'NOT_BOUND':
        raise GateProtocolError('LABEL_MISMATCH')
    if payload.get('semantic_conformance') is not False:
        raise GateProtocolError('CONFORMANCE_CLAIM_REFUSED')
    if payload.get('funds_executed') is not False:
        raise GateProtocolError('FUNDS_EXECUTED')
    return payload


class RemoteBook:
    """Read side of the live gate. Not a ``CreditMachine`` and not a database."""

    def __init__(self, producer):
        self._producer = producer

    def view(self, advance_id):
        return self._producer._view(advance_id)

    def export_journal(self):
        return self._producer._journal()

    def state_digest(self) -> str:
        return self._producer._state()['state_digest']

    def canonical_state(self) -> str:
        return self._producer._state()['canonical_state']


class GateHttpProducer:
    """Opt-in ``ProducerPort`` over ``LOCAL_FAKE_GATE``. Not SEMANTIC_CONFORMANCE."""

    label = LABEL
    semantic_conformance = False

    def __init__(self, base_url=None, timeout=5.0, actor='SIMULATED', gate=None):
        if type(actor) is not str or not actor:
            raise GateProtocolError('ENVELOPE_INVALID')
        self.actor = actor
        self.timeout = timeout
        self._owned = False
        self._closed = False
        if gate is not None:
            self.gate = gate
            self.base_url = gate.url
        elif base_url is None:
            module = load_fake_gate()
            self.gate = module.start()
            self.base_url = self.gate.url
            self._owned = True
        else:
            if not (base_url.startswith('http://127.0.0.1:') or base_url.startswith('http://[::1]:')):
                raise GateProtocolError('NON_LOOPBACK')
            self.gate = None
            self.base_url = base_url
        self.machine = RemoteBook(self)
        # Settlement fixtures are immutable and constructed the same way on both
        # sides. The credit book itself is only on the gate.
        self.fixtures = FixtureViews()
        if not isinstance(self, ProducerPort):
            self.close()
            raise GateProtocolError('NOT_A_PRODUCER')

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._owned and self.gate is not None:
            self.gate.close()

    def apply(self, op, advance_id, *, idempotency_key, args, bound_settlement_id):
        """POST once. A lost response raises ``ProducerUnknown`` and is not retried."""
        operation_id = idempotency_key
        envelope = {
            'operationId': operation_id,
            'actor': self.actor,
            'action': op,
            'body': {
                'operation_id': operation_id,
                'advance_id': advance_id,
                'args': args,
                'bound_settlement_id': bound_settlement_id,
            },
        }
        try:
            status, payload = self._request('POST', '/v1/commands', envelope, operation_id)
        except TransportLost as exc:
            raise ProducerUnknown(operation_id) from exc
        if status == 409:
            raise GateConflict(
                payload.get('error') if type(payload) is dict else 'IDEMPOTENCY_CONFLICT')
        if status != 200:
            raise GateProtocolError(
                payload.get('error') if type(payload) is dict else 'GATE_FAILED', status)
        payload = _honest(payload)
        if payload.get('outcome') == 'REJECTED':
            raise CreditError(payload.get('error'))
        if payload.get('outcome') != 'ACCEPTED' or type(payload.get('result')) is not dict:
            raise GateProtocolError('ENVELOPE_INVALID')
        return payload['result']

    def view(self, advance_id):
        return self._view(advance_id)

    def export_journal(self):
        return self._journal()

    def state_digest(self) -> str:
        return self._state()['state_digest']

    def canonical_state(self) -> str:
        return self._state()['canonical_state']

    def restored(self, journal):
        """New gate, same fixtures, book restored from ``journal``. Does not mutate self."""
        fresh = GateHttpProducer(timeout=self.timeout, actor=self.actor)
        try:
            fresh._restore(journal)
        except Exception:
            fresh.close()
            raise
        return fresh

    def reset(self) -> None:
        status, payload = self._request('POST', '/v1/reset', {})
        if status != 200:
            raise GateProtocolError(payload.get('error') if type(payload) is dict else 'GATE_FAILED')
        _honest(payload)

    def preview_draw(self, advance_id):
        status, payload = self._request('POST', '/v1/preview', {'advance_id': advance_id})
        if status != 200:
            raise GateProtocolError(payload.get('error') if type(payload) is dict else 'GATE_FAILED')
        payload = _honest(payload)
        if payload.get('outcome') == 'REJECTED':
            raise CreditError(payload.get('error'))
        if payload.get('outcome') != 'ACCEPTED':
            raise GateProtocolError('ENVELOPE_INVALID')
        return payload['result']

    def lookup(self, operation_id):
        """GET the original receipt. ``None`` when the gate has not stored one."""
        status, payload = self._request('GET', '/v1/receipts/' + operation_id)
        if status == 404:
            return None
        if status != 200:
            raise GateProtocolError(payload.get('error') if type(payload) is dict else 'LOOKUP_FAILED')
        return _honest(payload)

    def post_count(self, operation_id):
        """POST counter observed over HTTP. This client does not add a retry."""
        status, payload = self._request('GET', '/v1/counters')
        if status != 200:
            raise GateProtocolError(payload.get('error') if type(payload) is dict else 'LOOKUP_FAILED')
        payload = _honest(payload)
        counts = payload.get('post_counts')
        if type(counts) is not dict:
            raise GateProtocolError('ENVELOPE_INVALID')
        return counts.get(operation_id, 0)

    def _view(self, advance_id):
        status, payload = self._request('GET', '/v1/view?advance_id=' + advance_id)
        if status == 404 and type(payload) is dict and payload.get('error'):
            _honest(payload)
            raise CreditError(payload['error'])
        if status != 200:
            raise GateProtocolError(payload.get('error') if type(payload) is dict else 'GATE_FAILED')
        payload = _honest(payload)
        if type(payload.get('view')) is not dict:
            raise GateProtocolError('ENVELOPE_INVALID')
        return payload['view']

    def _journal(self):
        status, payload = self._request('GET', '/v1/journal')
        if status != 200:
            raise GateProtocolError(payload.get('error') if type(payload) is dict else 'GATE_FAILED')
        payload = _honest(payload)
        journal = payload.get('journal')
        if type(journal) is not list:
            raise GateProtocolError('ENVELOPE_INVALID')
        return journal

    def _state(self):
        status, payload = self._request('GET', '/v1/state')
        if status != 200:
            raise GateProtocolError(payload.get('error') if type(payload) is dict else 'GATE_FAILED')
        payload = _honest(payload)
        if type(payload.get('state_digest')) is not str or type(payload.get('canonical_state')) is not str:
            raise GateProtocolError('ENVELOPE_INVALID')
        return payload

    def _restore(self, journal):
        status, payload = self._request('POST', '/v1/restore', {'journal': journal})
        if status != 200:
            code = payload.get('error') if type(payload) is dict else 'GATE_FAILED'
            if status == 400 and type(code) is str and code not in {
                'UNKNOWN_FIELDS', 'ENVELOPE_INVALID', 'INVALID_JSON', 'JSON_REQUIRED',
                'INVALID_LENGTH', 'BODY_TOO_LARGE',
            }:
                raise CreditError(code)
            raise GateProtocolError(code)
        _honest(payload)

    def _request(self, method, path, payload=None, operation_id=None):
        data = None
        headers = {'Accept': 'application/json', 'Host': self._host_header()}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode('ascii')
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read()
                status = exc.code
            finally:
                exc.close()
        except (OSError, HTTPException) as exc:
            raise TransportLost(operation_id) from exc
        if not raw:
            raise TransportLost(operation_id)
        try:
            parsed = json.loads(raw.decode('utf-8'), object_pairs_hook=_strict_object)
        except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise GateProtocolError('INVALID_JSON') from exc
        return status, parsed

    def _host_header(self):
        rest = self.base_url.split('://', 1)[1]
        return rest


# Structural check at import. A missing method fails here, not at a call site.
_ = ProducerPort
