"""Offline auditor for an opt-in LOCAL_FILE_WORKSPACE directory.

`python3 -m capital.verify --workspace DIR` reads DIR/workspace.json bytes
directly: no flock, no mkdir, no write, no repair. The staged checks recompute
the envelope checksum, replay the journal into a scratch machine, run the
service's own restore validation over an in-memory document port, recompute
receipt fingerprints, and embed the same six build_reconciliation checks as
GET /api/reconciliation. The first failing check supplies the reason and the
command exits non-zero. This is a local diagnostic, not stage5 durable
transaction evidence and not an import or resume route.
"""
from __future__ import annotations

import copy
import hmac
import json
from pathlib import Path

from capital import store
from capital.producer import FixtureViews
from capital.projection import SimulationProjection
from capital.protocol import CreditMachine
from capital.recon import build_reconciliation
from capital.service import MAX_OPERATIONS, CapitalService, digest
from capital.store import FILE_NAME, StoragePort, verify_document
from capital.verify import loads

CHECK_ORDER = (
    'workspace_file',
    'strict_json',
    'envelope_shape',
    'payload_sha256',
    'payload_shape',
    'journal_replay',
    'state_digest',
    'service_restore',
    'receipt_journal_fingerprints',
    'recon',
)

_AUDIT_INSTANCE = 'workspace-offline-audit'
_WORKSPACE_STATUS = 'OFFLINE_AUDIT'
_HEX = frozenset('0123456789abcdef')


class _DocumentStorage(StoragePort):
    """In-memory port over the audited envelope. save() must never run."""

    def __init__(self, document):
        self._document = copy.deepcopy(document)

    def load(self):
        return verify_document(copy.deepcopy(self._document))

    def save(self, document):
        raise AssertionError('offline audit does not write')


def _marks(stop=None):
    """MATCHED for checks before `stop`, MISMATCH at `stop`, NOT_CHECKED after."""
    marks = {}
    for name in CHECK_ORDER:
        if name == stop:
            marks[name] = 'MISMATCH'
            stop = 'done'
        else:
            marks[name] = 'NOT_CHECKED' if stop == 'done' else 'MATCHED'
    return marks


def _report(workspace, marks, *, reason, failed_check, detail, recon=None):
    return {
        'ok': reason is None,
        'reason': reason,
        'failed_check': failed_check,
        'mode': 'OFFLINE_WORKSPACE_AUDIT',
        'label': 'SIMULATED',
        'diagnostic': 'LOCAL_ONLY',
        'format': store.FORMAT,
        'file': FILE_NAME,
        'workspace': workspace,
        'checks': marks,
        'saved_by_instance': detail.get('saved_by_instance'),
        'saved_at': detail.get('saved_at'),
        'payload_sha256': detail.get('payload_sha256'),
        'state_digest': detail.get('state_digest'),
        'entry_count': detail.get('entry_count'),
        'receipt_count': detail.get('receipt_count'),
        'recon_status': 'NOT_CHECKED' if recon is None else recon['status'],
        'recon': recon,
        'lock_taken': False,
        'writes': False,
        'workspace_mutated': False,
        'repair': 'NOT_IMPLEMENTED',
        'funds_executed': False,
        'durable': 'LOCAL_FILE_WORKSPACE',
        'stage5_durable_transactions': 'NOT_BOUND',
    }


def _is_hex64(value):
    return (type(value) is str and len(value) == 64
            and all(char in _HEX for char in value))


def _envelope_ok(document):
    """Same shape predicates as store.verify_document, without the checksum."""
    if type(document) is not dict or set(document) != store.ENVELOPE_KEYS:
        return False
    if document['format'] != store.FORMAT or type(document['payload']) is not dict:
        return False
    writer, saved_at = document['saved_by_instance'], document['saved_at']
    if not _is_hex64(document['payload_sha256']):
        return False
    return (type(writer) is str and bool(writer) and len(writer) <= 80
            and type(saved_at) is str and bool(saved_at))


def _payload_ok(payload):
    """Same payload predicates as CapitalService._validated_restore."""
    if set(payload) != {'receipts', 'journal', 'case_fixtures', 'state_digest'}:
        return False
    return (type(payload['receipts']) is dict and type(payload['journal']) is list
            and type(payload['case_fixtures']) is dict and type(payload['state_digest']) is str)


def _derived_args(entry, mapping):
    """Service-level args for one journal entry, for the fingerprint recompute.

    REJECTED and reconcile receipts have no journal row and their args are not
    persisted, so they keep the shape and uniqueness checks only.
    """
    try:
        op, body, advance_id = entry['op'], entry['body'], entry['advance_id']
        if op == 'offer':
            return {'fixture_id': mapping[advance_id], 'amount': body['amount']}
        if op == 'repay':
            return {'amount': body['amount'], 'sequence': body['sequence']}
        return {}
    except (KeyError, TypeError):
        return None


def _fingerprints_match(receipts, journal, mapping):
    fingerprints = []
    for key, stored in receipts.items():
        if type(key) is not str or type(stored) is not dict or set(stored) != {'fingerprint', 'receipt'}:
            return False
        fingerprint = stored['fingerprint']
        if not _is_hex64(fingerprint):
            return False
        fingerprints.append(fingerprint)
    if len(set(fingerprints)) != len(fingerprints):
        return False
    for entry in journal:
        args = _derived_args(entry, mapping)
        if args is None:
            return False
        try:
            stored = receipts.get(entry['idempotency_key'])
        except TypeError:
            return False
        if stored is None:
            return False
        expected = digest({'operation_id': entry['idempotency_key'], 'op': entry['op'],
                           'advance_id': entry['advance_id'], 'args': args})
        if not hmac.compare_digest(expected, stored['fingerprint']):
            return False
    return True


def audit_workspace(directory):
    """Audit DIR/workspace.json read-only. Returns the JSON report dict."""
    detail = {}
    workspace = str(directory)

    def fail(reason, check, recon=None):
        return _report(workspace, _marks(check), reason=reason, failed_check=check,
                       detail=detail, recon=recon)

    def unreadable(check):
        return fail('WORKSPACE_UNREADABLE', check)

    try:
        path = Path(directory) / FILE_NAME
        if not path.is_file():
            raise OSError('workspace file absent')
        raw = path.read_bytes()
    except (OSError, TypeError, ValueError):
        return unreadable('workspace_file')

    try:
        document = loads(raw)
    except (UnicodeError, ValueError, json.JSONDecodeError, RecursionError):
        return unreadable('strict_json')

    if not _envelope_ok(document):
        return unreadable('envelope_shape')
    detail['saved_by_instance'] = document['saved_by_instance']
    detail['saved_at'] = document['saved_at']
    detail['payload_sha256'] = document['payload_sha256']
    payload = document['payload']

    if not hmac.compare_digest(store._checksum(payload), document['payload_sha256']):
        return unreadable('payload_sha256')

    if not _payload_ok(payload):
        return unreadable('payload_shape')
    receipts, journal, mapping = payload['receipts'], payload['journal'], payload['case_fixtures']
    detail['state_digest'] = payload['state_digest']
    detail['entry_count'] = len(journal)
    detail['receipt_count'] = len(receipts)

    fixtures = FixtureViews()
    try:
        restored = CreditMachine.restore(copy.deepcopy(journal), fixtures)
    except Exception:
        return unreadable('journal_replay')

    if restored.state_digest() != payload['state_digest']:
        return unreadable('state_digest')

    try:
        service = CapitalService(_DocumentStorage(document))
        active = service.workspace_status == 'ACTIVE'
    except Exception:
        active = False
    if not active:
        return unreadable('service_restore')

    if not _fingerprints_match(receipts, journal, mapping):
        return unreadable('receipt_journal_fingerprints')

    try:
        recon = build_reconciliation(
            payload=copy.deepcopy(payload), unreadable=None,
            fixture_rows=copy.deepcopy(fixtures.rows), fixtures_digest=digest(fixtures.rows),
            settlement_source=fixtures, projection_port=SimulationProjection(),
            probe_operation_id=None, instance_id=_AUDIT_INSTANCE,
            operation_capacity=MAX_OPERATIONS, workspace_status=_WORKSPACE_STATUS)
    except Exception:
        return fail('RECON_MISMATCH', 'recon')
    if recon['status'] != 'MATCHED':
        return fail('RECON_MISMATCH', 'recon', recon=recon)
    return _report(workspace, _marks(), reason=None, failed_check=None,
                   detail=detail, recon=recon)
