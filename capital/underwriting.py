"""Read-only simulated underwriting decision record.

Values come from the same capital-decision-v1 note the terms overlay parses
(underwriting_depth, additional_margin, interest_rate). This module does not
import the vendor FSM, does not write a receipt, and does not approve. The FSM
approve command stays a caller decision; the record is a proposal only. A
missing or unusable note entry is NOT_BOUND and carries no numbers.
"""
from __future__ import annotations

import hashlib
import json
from typing import Protocol, runtime_checkable

UNDERWRITE_LABEL = 'simulated underwriting record — rule checks only, not an approval'
UNDERWRITE_NOT_BOUND = 'terms not bound'
BPS_SCALE = 10000

_MODE = 'SIMULATED_UNDERWRITING_RECORD'
_COMMITTED = 'COMMITTED'
_GATE_OBSERVED = 'MOCK_COMMIT_OBSERVED'
_GATE_UNBOUND = 'UNBOUND'
_GATE_BOUND = 'BOUND'
_TIER_NONE = 'NOT_APPLICABLE'

_REFUND_OPEN = 'REFUND_OBLIGATION_OPEN'
_NOT_COMMITTED = 'SETTLEMENT_NOT_COMMITTED'
_NO_TIER = 'NO_TIER_FOR_GATE'
_NO_BASE = 'BORROWING_BASE_UNDETERMINED'
_OVER_BASE = 'BORROWING_BASE_EXCEEDED'
_OVER_FACE = 'OPEN_FACE_RESIDUAL_EXCEEDED'
_CAP_EXCEEDED = 'CAP_EXCEEDED'
_UNSUPPORTED_CHECK = 'UNSUPPORTED_CHECK'

_REQUIRED_ENTRIES = ('underwriting_depth', 'additional_margin', 'interest_rate')
_CAP_KEYS = ('single_advance_cap_krw', 'beneficiary_aggregate_cap_krw', 'portfolio_cap_krw')
_THRESHOLD_KEY = 'two_person_threshold_krw'

_U1 = 'U1_SETTLEMENT_EVIDENCE'
_U2 = 'U2_REFUND_EXPOSURE'
_U3 = 'U3_BORROWING_BASE'
_U4 = 'U4_CONCENTRATION'
_U5 = 'U5_DECISION_AUTHORITY'
_U6 = 'U6_KYC_AML_STATUS'


def _nonneg_int(value):
    return type(value) is int and value >= 0


def _digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()


@runtime_checkable
class UnderwritingPort(Protocol):
    """Evaluate decided underwriting rules into a read-only decision record."""

    def record(self, subject, *, decided_by_role, sim_day) -> dict:
        """Deterministic rule record. A proposal only; approve stays caller-decided."""


class DecisionNoteUnderwriting:
    """EVIDENCE_RULES_V1 checks read from a parsed terms note. No invented values."""

    def __init__(self, terms):
        self.terms = terms

    def _value(self, name):
        items = getattr(self.terms, 'items', None)
        item = items.get(name) if type(items) is dict else None
        if type(item) is not dict or item.get('mark') != 'ADOPTED':
            return None
        return item['value']

    def _unbound(self, subject, decided_by_role):
        return {
            'label': UNDERWRITE_LABEL,
            'mode': _MODE,
            'provisional': True,
            'status': 'NOT_BOUND',
            'reason': UNDERWRITE_NOT_BOUND,
            'terms_version': getattr(self.terms, 'version', None),
            **{key: self.terms.status().get(key, 'NONE' if key == 'notes_source' else None)
               for key in ('notes_source', 'note_sha256')},
            'rules_version': None,
            'advance_id': subject['advance_id'],
            'candidate': subject['candidate'],
            'decided_by_role': decided_by_role,
            'kyc_executed': False,
            'underwriting_executed': False,
        }

    def _rules(self, depth):
        if not _nonneg_int(depth.get(_THRESHOLD_KEY)):
            return None
        caps = {}
        for key in _CAP_KEYS:
            if not _nonneg_int(depth.get(key)):
                return None
            caps[key] = depth[key]
        checks = depth.get('checks_ordered')
        if type(checks) is not list or not checks:
            return None
        ordered = []
        for item in checks:
            if type(item) is not dict or type(item.get('id')) is not str:
                return None
            ordered.append({'id': item['id'], 'rule': item.get('rule')})
        return {
            'caps': caps,
            'threshold': depth[_THRESHOLD_KEY],
            'checks': ordered,
            'version': depth['depth'],
        }

    def _gate(self, subject):
        if subject['commit_observed']:
            return _GATE_OBSERVED
        if subject['settlement_id'] is None:
            return _GATE_UNBOUND
        if subject['settlement_phase'] == _COMMITTED:
            return _GATE_OBSERVED
        return _GATE_BOUND

    def _tier(self, interest, gate):
        # U1 resolves the evidence tier from the settlement gate only (the note's
        # U1 rule); pricing conditions such as refund_face are U2's concern.
        for tier in interest['tiers']:
            if tier['condition'].get('settlement_gate') == gate:
                return tier
        return None

    def _u1(self, tier, gate):
        if tier is not None:
            return 'PASS', {'gate': gate, 'tier': tier['id']}
        reason = _NOT_COMMITTED if gate == _GATE_BOUND else _NO_TIER
        return 'FAIL', {'gate': gate, 'reason': reason}

    def _u2(self, claim):
        refund = claim['refund_face']
        if refund == 0 or claim['fixture_reclassified'] is True:
            return 'PASS', {'refund_face': refund}
        return 'FAIL', {
            'reason': _REFUND_OPEN,
            'refund_face': refund,
            'refund_outstanding': claim['refund_outstanding'],
        }

    def _u3(self, subject, base):
        amount = subject['amount']
        residual = subject['open_face'] - subject['other_reserved']
        detail = {
            'amount': amount,
            'base_krw': base,
            'open_face_residual_krw': residual,
        }
        if base is None:
            detail['reason'] = _NO_BASE
            return 'FAIL', detail
        if amount > base:
            detail['reason'] = _OVER_BASE
            return 'FAIL', detail
        if amount > residual:
            detail['reason'] = _OVER_FACE
            return 'FAIL', detail
        return 'PASS', detail

    def _u4(self, subject, caps):
        amount = subject['amount']
        incremental = subject['incremental']
        beneficiary = subject['beneficiary_outstanding'] + incremental
        portfolio = subject['portfolio_outstanding'] + incremental
        remaining = {
            'single_advance_krw': caps['single_advance_cap_krw'] - amount,
            'beneficiary_aggregate_krw': caps['beneficiary_aggregate_cap_krw'] - beneficiary,
            'portfolio_krw': caps['portfolio_cap_krw'] - portfolio,
        }
        checks = (
            ('single_advance_cap_krw', amount),
            ('beneficiary_aggregate_cap_krw', beneficiary),
            ('portfolio_cap_krw', portfolio),
        )
        for key, required in checks:
            if required > caps[key]:
                return 'FAIL', {
                    'reason': _CAP_EXCEEDED,
                    'cap': key,
                    'cap_krw': caps[key],
                    'required_krw': required,
                    'remaining_krw': caps[key] - required,
                }, remaining
        return 'PASS', dict(remaining), remaining

    def _u5(self, subject, threshold, decided_by_role):
        return 'PASS', {
            'two_person_required': subject['amount'] > threshold,
            'decided_by_role': decided_by_role,
            'approve_authority': 'CALLER_DECIDED',
        }

    def _u6(self):
        return 'PASS', {'kyc_executed': False}

    def record(self, subject, *, decided_by_role, sim_day):
        values = {name: self._value(name) for name in _REQUIRED_ENTRIES}
        if any(item is None for item in values.values()):
            return self._unbound(subject, decided_by_role)
        depth, margin, interest = (
            values['underwriting_depth'], values['additional_margin'], values['interest_rate'])
        rules = self._rules(depth)
        if rules is None:
            return self._unbound(subject, decided_by_role)
        claim = subject['claim']
        gate = self._gate(subject)
        tier = self._tier(interest, gate)
        payees = margin['beneficiary_payee_map'].get(subject['beneficiary_role'])
        rate = None if tier is None else margin['advance_rate_bps_by_tier'].get(tier['id'])
        eligible = None
        if payees is not None:
            eligible = sum(
                line['outstanding'] for line in claim['obligations']
                if line['payee'] in payees) - claim['refund_face']
        base = None
        if eligible is not None and _nonneg_int(rate):
            base = eligible * rate // BPS_SCALE
        u1_outcome, u1_detail = self._u1(tier, gate)
        u2_outcome, u2_detail = self._u2(claim)
        u3_outcome, u3_detail = self._u3(subject, base)
        u4_outcome, u4_detail, caps_remaining = self._u4(subject, rules['caps'])
        u5_outcome, u5_detail = self._u5(subject, rules['threshold'], decided_by_role)
        u6_outcome, u6_detail = self._u6()
        outcomes = {
            _U1: (u1_outcome, u1_detail),
            _U2: (u2_outcome, u2_detail),
            _U3: (u3_outcome, u3_detail),
            _U4: (u4_outcome, u4_detail),
            _U5: (u5_outcome, u5_detail),
            _U6: (u6_outcome, u6_detail),
        }
        checks = []
        failed = None
        for item in rules['checks']:
            outcome = outcomes.get(item['id'])
            if outcome is None:
                outcome = ('FAIL', {'reason': _UNSUPPORTED_CHECK})
            checks.append({'id': item['id'], 'rule': item['rule'],
                           'outcome': outcome[0], 'detail': outcome[1]})
            if failed is None and outcome[0] == 'FAIL':
                failed = item['id']
        inputs = {
            'rules_version': rules['version'],
            'terms_version': getattr(self.terms, 'version', None),
            'advance_id': subject['advance_id'],
            'candidate': subject['candidate'],
            'phase': subject['phase'],
            'amount': subject['amount'],
            'beneficiary_role': subject['beneficiary_role'],
            'settlement_id': subject['settlement_id'],
            'gate': gate,
            'tier': None if tier is None else tier['id'],
            'refund_face': claim['refund_face'],
            'refund_outstanding': claim['refund_outstanding'],
            'fixture_reclassified': claim['fixture_reclassified'],
            'eligible_face': eligible,
            'advance_rate_bps': rate,
            'base_krw': base,
            'open_face': subject['open_face'],
            'other_reserved': subject['other_reserved'],
            'beneficiary_outstanding': subject['beneficiary_outstanding'],
            'portfolio_outstanding': subject['portfolio_outstanding'],
            'incremental': subject['incremental'],
            'caps': rules['caps'],
            'two_person_threshold_krw': rules['threshold'],
            'decided_by_role': decided_by_role,
            'sim_day': sim_day,
        }
        return {
            'label': UNDERWRITE_LABEL,
            'mode': _MODE,
            'provisional': True,
            'status': 'BOUND',
            'reason': None,
            'terms_version': getattr(self.terms, 'version', None),
            **{key: self.terms.status().get(key, 'NONE' if key == 'notes_source' else None)
               for key in ('notes_source', 'note_sha256')},
            'rules_version': rules['version'],
            'advance_id': subject['advance_id'],
            'candidate': subject['candidate'],
            'phase': subject['phase'],
            'gate': gate,
            'tier': _TIER_NONE if tier is None else tier['id'].split('_', 1)[0],
            'amount': subject['amount'],
            'beneficiary_role': subject['beneficiary_role'],
            'borrowing_base': None if base is None else {
                'eligible_face': eligible,
                'advance_rate_bps': rate,
                'base_krw': base,
            },
            'caps_remaining': caps_remaining,
            'decided_by_role': decided_by_role,
            'two_person_required': u5_detail['two_person_required'],
            'kyc_executed': False,
            'underwriting_executed': False,
            'checks': checks,
            'failed_check': failed,
            'proposal': 'DECLINE' if failed is not None else 'APPROVE',
            'inputs_digest': _digest(inputs),
            'sim_day': sim_day,
        }
