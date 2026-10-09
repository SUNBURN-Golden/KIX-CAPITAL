"""Read-only simulated application of a decided distribution order.

The pinned SettlementMachine accepts only an explicit order list as a policy
input. This module derives that list from the capital-decision-v1 note and
runs it on a disposable book. Entries the note marks fsm_expressible false
are listed and never computed. The note asks for shadow math on those
entries; this node does not calculate them.

A missing or malformed note is NOT_BOUND. The zipapp does not bundle docs/,
so that run stays NOT_BOUND. Nothing here is an executed distribution or a
bank movement.
"""
from __future__ import annotations

import datetime
import hashlib
import importlib.resources
import json
import re
from pathlib import Path
from typing import Protocol, runtime_checkable

from capital.protocol import SettlementError, SettlementMachine
from capital.scenarios import public_invariants

POLICY_LABEL = 'simulated policy application — not executed distribution, not bank movement'
POLICY_NOT_BOUND = 'policy not bound'
POLICY_INCONSISTENT = 'POLICY_INCONSISTENT'
WITHIN_CLASS = 'within-class pro-rata requires upstream FSM change'
UPSTREAM_FSM = 'upstream FSM change'
UNSUPPORTED = 'UNSUPPORTED_BY_PINNED_FSM'
SCENARIO_ID = 'derived-order-v1'

_FENCE = re.compile(r'```capital-decision-v1[ \t]*\n(.*?)```', re.DOTALL)
_ISO_DATE = re.compile(r'\d{4}-\d{2}-\d{2}\Z')
_RESIDUAL_KIND_PREFIX = 'primary residual_payee'
_FEE_KIND_PREFIX = 'primary fee_payee'
_UNDECIDED = frozenset(('UNDETERMINED', 'DEFERRED', 'NOT_ADOPTED'))
_BOOK = 'sim-policy-disposable'
_TRADE = 'sim-policy-trade'
_DEBTOR = 'fixture-merchant'


def default_note_path():
    """Checkout path of the settlement-policy note. Absent inside the zipapp."""
    package = importlib.resources.files('capital')
    return Path(str(package)).parent / 'docs' / 'decisions' / 'CAPITAL_SETTLEMENT_POLICY.md'


def _reject_duplicate_keys(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate key')
        obj[key] = value
    return obj


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def _sha256(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _iso_date(value):
    if type(value) is not str or _ISO_DATE.fullmatch(value) is None:
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _nonempty_str(value):
    return type(value) is str and bool(value.strip())


def _classes_for_prefix(table, prefix):
    found = []
    for row in table:
        for kind in row['payee_kinds']:
            if kind.startswith(prefix):
                found.append(row['class'])
    return found


def _table_ok(table):
    if type(table) is not list or not table:
        return False
    seen = []
    for row in table:
        if type(row) is not dict:
            return False
        cls = row.get('class')
        kinds = row.get('payee_kinds')
        if type(cls) is not int or type(kinds) is not list or not kinds:
            return False
        if any(not _nonempty_str(kind) for kind in kinds):
            return False
        seen.append(cls)
    return len(seen) == len(set(seen))


def _order_ok(order):
    if type(order) is not list or not order:
        return False
    if any(not _nonempty_str(item) for item in order):
        return False
    return len(order) == len(set(order))


def _unsupported_row(name, entry):
    note_status = entry.get('status')
    consumer = entry.get('consumer')
    return {
        'item': name,
        'status': UNSUPPORTED,
        'computed': False,
        'requires': UPSTREAM_FSM,
        'note_status': note_status if type(note_status) is str else None,
        'consumer': consumer if type(consumer) is str else None,
        'label': POLICY_LABEL,
    }


def apply_order(gross, policy, statement, order):
    """Run initiate through distribute on a fresh pinned book. Does not touch a workspace."""
    machine = SettlementMachine()
    machine.initiate(
        _BOOK, idempotency_key='policy-initiate', trade_id=_TRADE, gross=gross,
        debtor_role=_DEBTOR, policy=policy,
    )
    machine.authorize(_BOOK, idempotency_key='policy-authorize')
    machine.capture(_BOOK, idempotency_key='policy-capture')
    machine.commit(
        _BOOK, idempotency_key='policy-commit',
        movement_id=statement['movement_id'], gross=statement['gross'],
        amount=statement['amount'], fee=statement['fee'], tax=statement['tax'],
        held=statement['held'], adjustment=statement['adjustment'],
    )
    machine.distribute(_BOOK, idempotency_key='policy-distribute', order=list(order))
    claim = machine.view(_BOOK)['claim']
    by_payee = {row['payee']: row for row in claim['obligations']}
    per_payee = []
    for payee in order:
        row = by_payee[payee]
        per_payee.append({
            'payee': payee,
            'face': row['face'],
            'distributed': row['distributed'],
            'outstanding': row['outstanding'],
        })
    return {
        'claim': claim,
        'per_payee': per_payee,
        'invariants': public_invariants(claim),
        'distributed_cash': claim['distributed_cash'],
        'undistributed_cash': claim['undistributed_cash'],
        'order': list(claim['distribution_order']),
        'label': POLICY_LABEL,
    }


def probe_order_freeze(gross, policy, statement, first_order, attempted_order):
    """Distribute once, then show the pinned machine refuses a different order."""
    machine = SettlementMachine()
    machine.initiate(
        _BOOK, idempotency_key='policy-initiate', trade_id=_TRADE, gross=gross,
        debtor_role=_DEBTOR, policy=policy,
    )
    machine.authorize(_BOOK, idempotency_key='policy-authorize')
    machine.capture(_BOOK, idempotency_key='policy-capture')
    machine.commit(
        _BOOK, idempotency_key='policy-commit',
        movement_id=statement['movement_id'], gross=statement['gross'],
        amount=statement['amount'], fee=statement['fee'], tax=statement['tax'],
        held=statement['held'], adjustment=statement['adjustment'],
    )
    machine.distribute(_BOOK, idempotency_key='policy-distribute', order=list(first_order))
    before = machine.view(_BOOK)['claim']
    same = machine.distribute(_BOOK, idempotency_key='policy-distribute-same', order=list(first_order))
    after_same = machine.view(_BOOK)['claim']
    refused = False
    code = None
    try:
        machine.distribute(_BOOK, idempotency_key='policy-distribute-other', order=list(attempted_order))
    except SettlementError as exc:
        refused = True
        code = exc.code
    after = machine.view(_BOOK)['claim']
    added = sum(same['effect'].values()) if type(same.get('effect')) is dict else None
    return {
        'attempted_order': list(attempted_order),
        'refused': refused,
        'code': code,
        'unchanged': before == after,
        'same_order_added': added,
        'distributed_after_same': after_same['distributed_cash'],
        'distributed_before_repeat': before['distributed_cash'],
        'label': POLICY_LABEL,
    }


@runtime_checkable
class SettlementPolicyPort(Protocol):
    """Read the decided allocation order. Not an upstream adoption."""

    def status(self) -> dict:
        """Note-level mark. Does not apply an order."""

    def allocation(self, claim_policy) -> dict:
        """Derive an explicit order for one claim policy, or refuse."""

    def unsupported(self) -> list:
        """fsm_expressible false entries. No amounts."""


class DecisionNoteSettlementPolicy:
    """Load one capital-decision-v1 settlement note. No copied order literals."""

    def __init__(self, path=None):
        self.path = default_note_path() if path is None else Path(path)
        self.policy_version = None
        self.alloc_version = None
        self.policy_digest = None
        self.outcome = 'NOT_BOUND'
        self.reason = POLICY_NOT_BOUND
        self._table = None
        self._expected = None
        self._unsupported = []
        self._upstream = []
        self._load()

    def _load(self):
        path = self.path
        try:
            if not path.is_file():
                return
            text = path.read_text(encoding='utf-8')
            blocks = [json.loads(raw, object_pairs_hook=_reject_duplicate_keys) for raw in _FENCE.findall(text)]
        except (OSError, UnicodeError, ValueError, RecursionError):
            return
        if len(blocks) != 1 or type(blocks[0]) is not dict:
            return
        block = blocks[0]
        if block.get('schema') != 'capital-decision-v1':
            return
        version = block.get('policy_version')
        if not _nonempty_str(version):
            return
        entries = block.get('entries')
        if type(entries) is not dict:
            return
        self.policy_version = version
        self._collect(block, entries)
        entry = entries.get('allocation_order')
        if type(entry) is not dict:
            return
        self._classify(entry)

    def _collect(self, block, entries):
        rows = []
        for name, entry in entries.items():
            if type(entry) is not dict or entry.get('fsm_expressible') is not False:
                continue
            rows.append(_unsupported_row(name, entry))
        self._unsupported = rows
        upstream = block.get('upstream_fsm_change_requests_decision_required_astra')
        if type(upstream) is list and all(_nonempty_str(item) for item in upstream):
            self._upstream = list(upstream)

    def _classify(self, entry):
        status = entry.get('status')
        if status in _UNDECIDED:
            self.outcome = 'POLICY_UNDECIDED'
            self.reason = None
            return
        if status != 'ADOPTED':
            return
        if not _nonempty_str(entry.get('provided_by')) or not _iso_date(entry.get('date')):
            return
        if entry.get('provisional') is not True:
            return
        expressible = entry.get('fsm_expressible')
        if expressible is False:
            self.outcome = UNSUPPORTED
            self.reason = UPSTREAM_FSM
            return
        if expressible is not True:
            return
        value = entry.get('value')
        if type(value) is not dict or not _nonempty_str(value.get('policy_version')):
            return
        if not _nonempty_str(value.get('within_class')):
            return
        table = value.get('class_table_ordered')
        expected = value.get('derived_order_for_pinned_two_payee_policy')
        if not _table_ok(table) or not _order_ok(expected):
            return
        residual = _classes_for_prefix(table, _RESIDUAL_KIND_PREFIX)
        fee = _classes_for_prefix(table, _FEE_KIND_PREFIX)
        if len(residual) != 1 or len(fee) != 1:
            self.outcome = 'NOT_BOUND'
            self.reason = POLICY_INCONSISTENT
            return
        self._table = table
        self._expected = list(expected)
        self.alloc_version = value['policy_version']
        self.policy_digest = _sha256(table)
        if residual[0] == fee[0]:
            self.outcome = UNSUPPORTED
            self.reason = WITHIN_CLASS
            return
        self.outcome = 'DECIDED'
        self.reason = None

    def _base(self):
        return {
            'label': POLICY_LABEL,
            'policy_version': self.policy_version,
            'alloc_version': self.alloc_version,
            'policy_digest': self.policy_digest,
            'outcome': self.outcome,
            'reason': self.reason,
            'order': None,
        }

    def status(self) -> dict:
        return {
            'label': POLICY_LABEL,
            'mode': 'SIMULATED_POLICY_APPLICATION',
            'provisional': True,
            'policy_version': self.policy_version,
            'policy_digest': self.policy_digest,
            'outcome': self.outcome,
            'reason': self.reason,
        }

    def allocation(self, claim_policy) -> dict:
        base = self._base()
        if self.outcome != 'DECIDED':
            return base
        if type(claim_policy) is not dict:
            return {**base, 'outcome': 'NOT_BOUND', 'reason': POLICY_INCONSISTENT, 'order': None}
        residual_name = claim_policy.get('residual_payee')
        fee_name = claim_policy.get('fee_payee')
        if not _nonempty_str(residual_name) or not _nonempty_str(fee_name) or residual_name == fee_name:
            return {**base, 'outcome': 'NOT_BOUND', 'reason': POLICY_INCONSISTENT, 'order': None}
        residual = _classes_for_prefix(self._table, _RESIDUAL_KIND_PREFIX)
        fee = _classes_for_prefix(self._table, _FEE_KIND_PREFIX)
        if len(residual) != 1 or len(fee) != 1:
            return {**base, 'outcome': 'NOT_BOUND', 'reason': POLICY_INCONSISTENT, 'order': None}
        if residual[0] == fee[0]:
            return {**base, 'outcome': UNSUPPORTED, 'reason': WITHIN_CLASS, 'order': None}
        pairs = [(residual[0], residual_name), (fee[0], fee_name)]
        pairs.sort()
        order = [label for _cls, label in pairs]
        if order != self._expected:
            return {**base, 'outcome': 'NOT_BOUND', 'reason': POLICY_INCONSISTENT, 'order': None}
        return {**base, 'outcome': 'DECIDED', 'reason': None, 'order': order}

    def unsupported(self) -> list:
        return [dict(row) for row in self._unsupported]

    def upstream_requests(self) -> list:
        return list(self._upstream)
