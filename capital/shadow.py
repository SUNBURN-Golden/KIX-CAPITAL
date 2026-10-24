"""Pure-integer shadow arithmetic for the items the pinned FSM cannot express.

`docs/decisions/CAPITAL_SHADOW_POLICY.md` (CAPITAL-SHADOW-V1) splits every
`fsm_expressible: false` settlement entry into two verdicts that never merge:
the pinned-path `UNSUPPORTED_BY_PINNED_FSM` row (kept by `capital/policy.py`,
which computes nothing) and a shadow-path `SHADOW_*` verdict under mode
`SHADOW_NOT_APPLIED` owned by this module.

This module imports only the standard library plus the same decision-note
loader shape as `capital/policy.py`. It never imports `capital.vendor` or
`capital.protocol`, never touches a `SettlementMachine`/`MockSettlement`
instance, never writes the workspace and never issues an FSM command. Inputs
are frozen input-vector dicts built by the facade from a pinned `view()`
snapshot or from synthetic literals in the decision note; policy values (the
reason-class table, bearer rules, resale triggers and the worked resale
example) are read from the note at runtime, never copied into code.

A missing or malformed note reports `SHADOW_NOT_BOUND` — the zipapp does not
bundle `docs/`, so that run stays NOT_BOUND. Every result carries the nine
constant false flags; no result is an executed distribution, a recovery, a
payout or a bank movement.

Single-claim revenue participation posting, claim-slice sizing and price, and
the ordered UC1-UC4 partition of `undistributed_cash` are pure integer-floor
functions here (CAPITAL_SHADOW_POLICY section 3.7). Their ratio, cap, advance
rate and tier rate are read from the settlement and financial-terms notes at
runtime; only the CAPITAL-SHADOW-V1 rule constants (10000 bps, 365 days) live in
code. The multi-claim base, 90-day window, upward late cash, term end, slice
registry, holder priority, impairment, aggregate caps, 180-day timer, D+1 batch
and provider return stay `SHADOW_DEFERRED` with the unblock seam from the note.
"""
from __future__ import annotations

import hashlib
import importlib.resources
import json
import re
from pathlib import Path
from typing import Protocol, runtime_checkable

SHADOW_LABEL = 'shadow arithmetic — not applied to the pinned FSM, not an executed distribution, not a bank movement'
SHADOW_MODE = 'SHADOW_NOT_APPLIED'
SHADOW_PROVENANCE = 'SHADOW_ARITHMETIC_ONLY'
RULES_VERSION = 'CAPITAL-SHADOW-V1'
MONEY_MAX = 10**12  # pinned FSM MONEY_MAX fixture bound
SHADOW_NOT_BOUND_REASON = 'shadow note not bound'
SHADOW_ENTRY_NOT_BOUND = 'decided entry not bound in the note'

COMPUTED = 'SHADOW_COMPUTED'
DEFERRED = 'SHADOW_DEFERRED'
NOT_BOUND = 'SHADOW_NOT_BOUND'
INPUT_UNKNOWN = 'SHADOW_INPUT_UNKNOWN'
INCONSISTENT = 'SHADOW_INCONSISTENT'
SHADOW_STATUSES = frozenset((COMPUTED, DEFERRED, NOT_BOUND, INPUT_UNKNOWN, INCONSISTENT))

MATCHES = 'MATCHES_PINNED_FSM'
DIVERGES = 'DIVERGES_PINNED_FSM_BY_DESIGN'
NOT_COMPARABLE = 'NOT_COMPARABLE'
RECONCILIATIONS = frozenset((MATCHES, DIVERGES, NOT_COMPARABLE))

FALSE_FLAGS = (
    'applied_to_fsm', 'funds_executed', 'policy_adopted', 'bank_debit_observed',
    'right_cancelled', 'external_return_closed', 'legal_debtor_bound',
    'admission_granted', 'workspace_mutated',
)

_BPS = 10_000  # CAPITAL-SHADOW-V1: bps = floor(amount * bps / 10000)
_YEAR_DAYS = 365  # CAPITAL-SHADOW-V1 / ACT_365_FIXED day-count divisor
_ACT_365 = 'ACT_365_FIXED'
_UC_IDS = ('UC1', 'UC2', 'UC3', 'UC4')
_FENCE = re.compile(r'```capital-decision-v1[ \t]*\n(.*?)```', re.DOTALL)
# Bearer mechanics vocabulary of the settlement note's reason_classes_ordered.
_PRO_RATA_ALL = 'PRO_RATA_ALL_LINES'
_RESIDUAL_THEN_FEE = 'ORGANIZER_FIRST_THEN_PLATFORM'
_RESIDUAL_THEN_FEE_WA = 'ORGANIZER_FIRST_THEN_PLATFORM_WORKING_ASSUMPTION'
_FEE_THEN_POOL = 'PLATFORM_100'
_RESALE_ROUTED = 'resale_prior_contract_cancel_burden'
_SELLER = 'seller_due'
_ORGANIZER_DUE = 'organizer_due'
_PLATFORM_DUE = 'platform_due'


class _UnknownInput(Exception):
    def __init__(self, key, detail):
        self.key = key
        self.detail = detail
        super().__init__(detail)


class ShadowInconsistent(Exception):
    """An input violates the CAPITAL-SHADOW-V1 domain or an invariant."""

    def __init__(self, detail):
        self.detail = detail
        super().__init__(detail)


def default_note_path():
    """Checkout path of the settlement-policy note. Absent inside the zipapp."""
    package = importlib.resources.files('capital')
    return Path(str(package)).parent / 'docs' / 'decisions' / 'CAPITAL_SETTLEMENT_POLICY.md'


def default_terms_path():
    """Checkout path of the financial-terms note. Absent inside the zipapp."""
    package = importlib.resources.files('capital')
    return Path(str(package)).parent / 'docs' / 'decisions' / 'CAPITAL_FINANCIAL_TERMS.md'


def default_shadow_note_path():
    """Checkout path of the shadow-policy note. Absent inside the zipapp."""
    package = importlib.resources.files('capital')
    return Path(str(package)).parent / 'docs' / 'decisions' / 'CAPITAL_SHADOW_POLICY.md'


def _reject_duplicate_keys(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate key')
        obj[key] = value
    return obj


def canonical(value):
    """CAPITAL-SHADOW-V1 canonical JSON: sort_keys, ensure_ascii, compact."""
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def _sha256(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _nonempty_str(value):
    return type(value) is str and bool(value.strip())


def _ascii_label(value):
    return _nonempty_str(value) and value.isascii()


def _amount(value):
    """CAPITAL-SHADOW-V1 domain: non-negative int at or under MONEY_MAX."""
    return type(value) is int and 0 <= value <= MONEY_MAX


def _check_amount(value, name):
    if not _amount(value):
        raise ShadowInconsistent(f'{name} outside the non-negative int domain')
    return value


def fill_sequential(total, lines):
    """Fill ordered (label, cap) lines from `total` until exhausted."""
    _check_amount(total, 'total')
    out = []
    remaining = total
    seen = set()
    for label, cap in lines:
        if not _ascii_label(label) or label in seen:
            raise ShadowInconsistent('labels must be unique ASCII')
        _check_amount(cap, 'cap')
        seen.add(label)
        take = min(cap, remaining)
        out.append((label, take))
        remaining -= take
    return out, remaining


def allocate_largest_remainder(total, weighted):
    """q_i = floor(T*w_i/W); the remainder goes one unit each to the largest
    (T*w_i) mod W, ties by ascending label in code-point order."""
    _check_amount(total, 'total')
    seen = set()
    rows = []
    for label, weight in weighted:
        if not _ascii_label(label) or label in seen:
            raise ShadowInconsistent('labels must be unique ASCII')
        _check_amount(weight, 'weight')
        seen.add(label)
        rows.append((label, weight))
    weight_sum = sum(weight for _label, weight in rows)
    if weight_sum == 0:
        raise ShadowInconsistent('total weight is zero')
    quota = {label: (total * weight) // weight_sum for label, weight in rows}
    remainder = total - sum(quota.values())
    ranked = sorted(rows, key=lambda row: (-((total * row[1]) % weight_sum), row[0]))
    for index in range(remainder):
        quota[ranked[index][0]] += 1
    return [(label, quota[label]) for label, _weight in rows]


def capped_pro_rata(total, lines):
    """Largest remainder over (label, weight, cap); lines over cap are fixed at
    cap and the excess is re-allocated among uncapped lines until stable."""
    _check_amount(total, 'total')
    seen = set()
    active = []
    for label, weight, cap in lines:
        if not _ascii_label(label) or label in seen:
            raise ShadowInconsistent('labels must be unique ASCII')
        _check_amount(weight, 'weight')
        _check_amount(cap, 'cap')
        seen.add(label)
        active.append((label, weight, cap))
    fixed = {}
    pool = total
    while active:
        if sum(weight for _l, weight, _c in active) == 0:
            for label, _weight, _cap in active:
                fixed[label] = 0
            break
        alloc = dict(allocate_largest_remainder(pool, [(label, w) for label, w, _c in active]))
        over = [(label, cap) for label, _w, cap in active if alloc[label] > cap]
        if not over:
            fixed.update(alloc)
            pool = 0
            break
        capped = {label for label, _cap in over}
        for label, cap in over:
            fixed[label] = cap
            pool -= cap
        active = [(label, w, cap) for label, w, cap in active if label not in capped]
    return [(label, fixed[label]) for label, _w, _c in lines], pool


def _bps_floor(amount, bps):
    return amount * bps // _BPS


def participation_posting(class2_allocated, organizer_borne_refunds, funded, paid_to_date,
                          ratio_bps, cap_bps):
    """Single-claim participation posting. B = class-2 cash - organizer-borne
    refunds; participation = floor(B*ratio); cap = floor(F*cap);
    payable = min(participation, cap - paid_to_date)."""
    _check_amount(class2_allocated, 'class2_allocated')
    _check_amount(organizer_borne_refunds, 'organizer_borne_refunds')
    _check_amount(funded, 'F')
    _check_amount(paid_to_date, 'paid_to_date')
    _check_amount(ratio_bps, 'ratio_bps')
    _check_amount(cap_bps, 'cap_bps')
    if organizer_borne_refunds > class2_allocated:
        raise ShadowInconsistent('organizer-borne refunds exceed the class-2 allocated cash')
    base = class2_allocated - organizer_borne_refunds
    participation = _bps_floor(base, ratio_bps)
    cap = _bps_floor(funded, cap_bps)
    if paid_to_date > cap:
        raise ShadowInconsistent('paid_to_date exceeds the cap')
    return {'base': base, 'participation': participation, 'cap': cap,
            'payable': min(participation, cap - paid_to_date)}


def slice_sizing(outstanding, open_refund_face, advance_bps, all_in_bps, expected_days):
    """Claim-slice size and price. max = floor((outstanding - open refund) *
    advance/10000); discount = floor(max*all_in*days/(10000*365)) (one last
    floor); price = max - discount."""
    _check_amount(outstanding, 'outstanding')
    _check_amount(open_refund_face, 'open_refund_face')
    _check_amount(advance_bps, 'advance_bps')
    _check_amount(all_in_bps, 'all_in_bps')
    _check_amount(expected_days, 'expected_days')
    if open_refund_face > outstanding:
        raise ShadowInconsistent('open refund face exceeds the line outstanding')
    face_max = _bps_floor(outstanding - open_refund_face, advance_bps)
    return {'slice_face_max': face_max, **slice_price(face_max, all_in_bps, expected_days)}


def slice_price(face, all_in_bps, expected_days):
    """The same one-floor price for an admitted face below the quoted maximum."""
    for name, value in (('face', face), ('all_in_bps', all_in_bps), ('expected_days', expected_days)):
        _check_amount(value, name)
    discount = face * all_in_bps * expected_days // (_BPS * _YEAR_DAYS)
    return {'discount': discount, 'price': face - discount}


def uc_partition(confirmed_cash, undistributed_cash, refund_outstanding, reclassified, rows):
    """Ordered UC1-UC4 split of undistributed cash; the parts sum to the cash."""
    _check_amount(confirmed_cash, 'confirmed_cash')
    _check_amount(undistributed_cash, 'undistributed_cash')
    _check_amount(refund_outstanding, 'refund_outstanding')
    if type(reclassified) is not bool:
        raise ShadowInconsistent('reclassified must be a bool')
    if type(rows) is not list or not rows:
        raise ShadowInconsistent('obligations missing')
    outstanding = faces = distributed = 0
    for row in rows:
        if type(row) is not dict:
            raise ShadowInconsistent('obligation row must be an object')
        face = _check_amount(row.get('face'), 'face')
        paid = _check_amount(row.get('distributed'), 'distributed')
        cancelled = _check_amount(row.get('cancelled_unpaid'), 'cancelled_unpaid')
        open_ = _check_amount(row.get('outstanding'), 'outstanding')
        if face != paid + cancelled + open_:
            raise ShadowInconsistent('face != distributed + cancelled_unpaid + outstanding')
        faces += face
        distributed += paid
        outstanding += open_
    if confirmed_cash < distributed or undistributed_cash != confirmed_cash - distributed:
        raise ShadowInconsistent('undistributed_cash != confirmed_cash - sum distributed')
    rest = undistributed_cash
    uc1 = min(rest, outstanding)
    rest -= uc1
    uc2 = min(rest, refund_outstanding)
    rest -= uc2
    uc3 = rest if reclassified else 0
    rest -= uc3
    uc4 = rest if confirmed_cash > faces else 0
    rest -= uc4
    if rest:
        raise ShadowInconsistent('undistributed cash fits no UC state')
    return {'uc1': uc1, 'uc2': uc2, 'uc3': uc3, 'uc4': uc4}


def _false_flags():
    return {name: False for name in FALSE_FLAGS}


def _parse_obligations(vector):
    """Validate the frozen claim half of an input vector. Returns (gross,
    policy roles, per-payee state). Raises ShadowInconsistent on any breach."""
    if type(vector) is not dict:
        raise ShadowInconsistent('input vector must be an object')
    gross = _check_amount(vector.get('gross'), 'gross')
    policy = vector.get('policy')
    if type(policy) is not dict:
        raise ShadowInconsistent('policy roles missing')
    residual_payee = policy.get('residual_payee')
    fee_payee = policy.get('fee_payee')
    if not _ascii_label(residual_payee) or not _ascii_label(fee_payee) or residual_payee == fee_payee:
        raise ShadowInconsistent('policy roles missing or equal')
    obligations = vector.get('obligations')
    if type(obligations) is not list or not obligations:
        raise ShadowInconsistent('obligations missing')
    lines = {}
    order = []
    for row in obligations:
        if type(row) is not dict:
            raise ShadowInconsistent('obligation row must be an object')
        payee = row.get('payee')
        if not _ascii_label(payee) or payee in lines:
            raise ShadowInconsistent('labels must be unique ASCII')
        face = _check_amount(row.get('face'), 'face')
        distributed = _check_amount(row.get('distributed'), 'distributed')
        cancelled = _check_amount(row.get('cancelled_unpaid'), 'cancelled_unpaid')
        outstanding = _check_amount(row.get('outstanding'), 'outstanding')
        recovery = row.get('recovery_due', 0)
        _check_amount(recovery, 'recovery_due')
        if face != distributed + cancelled + outstanding:
            raise ShadowInconsistent('face != distributed + cancelled_unpaid + outstanding')
        lines[payee] = {
            'payee': payee, 'face': face, 'distributed': distributed,
            'cancelled_unpaid': cancelled, 'outstanding': outstanding,
            'prior_recovery': recovery,
            'reversal': 0, 'cancelled': 0, 'recovery': 0,
        }
        order.append(payee)
    if residual_payee not in lines or fee_payee not in lines:
        raise ShadowInconsistent('policy payees must be obligation payees')
    if any(payee not in (residual_payee, fee_payee) for payee in order):
        raise ShadowInconsistent('a payee cannot be classified by the pinned two-payee roles')
    if sum(lines[payee]['face'] for payee in order) != gross:
        raise ShadowInconsistent('obligation faces do not sum to gross')
    return gross, residual_payee, fee_payee, lines, order


def _remaining_face(line):
    return line['face'] - line['cancelled_unpaid'] - line['reversal']


def _open_outstanding(line):
    return line['outstanding'] - line['cancelled']


def _recovery_room(line):
    return line['distributed'] - line['prior_recovery'] - line['recovery']


def _parse_refund_entry(refund):
    if type(refund) is not dict:
        raise ShadowInconsistent('refund entry must be an object')
    refund_id = refund.get('refund_id')
    if not _ascii_label(refund_id):
        raise ShadowInconsistent('refund_id missing')
    amount = _check_amount(refund.get('amount'), 'amount')
    reason_class = refund.get('reason_class')
    if not _nonempty_str(reason_class):
        raise ShadowInconsistent('reason_class missing')
    evidence_ref = refund.get('evidence_ref')
    if not _nonempty_str(evidence_ref):
        raise ShadowInconsistent('evidence_ref missing')
    adjudicated = refund.get('adjudicated_platform_fault', False)
    if type(adjudicated) is not bool:
        raise ShadowInconsistent('adjudicated_platform_fault must be a bool')
    return refund_id, amount, reason_class, evidence_ref, adjudicated


def _read_block(path):
    """The single capital-decision-v1 block of a note as a dict, else None."""
    try:
        path = Path(path)
        if not path.is_file():
            return None
        text = path.read_text(encoding='utf-8')
        blocks = [json.loads(raw, object_pairs_hook=_reject_duplicate_keys) for raw in _FENCE.findall(text)]
    except (OSError, UnicodeError, ValueError, RecursionError):
        return None
    if len(blocks) != 1 or type(blocks[0]) is not dict:
        return None
    return blocks[0]


def _adopted_value(entries, key):
    entry = entries.get(key)
    if type(entry) is dict and entry.get('status') == 'ADOPTED' and type(entry.get('value')) is dict:
        return entry['value']
    return None


class DecisionNoteShadow:
    """Load one capital-decision-v1 settlement note and evaluate shadow vectors.

    Reads the decided refund-bearer reason classes, bearer rules and resale
    triggers plus the note's own synthetic worked resale example. No numeric
    policy value is copied into this module.
    """

    def __init__(self, path=None, *, terms_path=None, shadow_path=None):
        self.path = default_note_path() if path is None else Path(path)
        self.terms_path = default_terms_path() if terms_path is None else Path(terms_path)
        self.shadow_path = default_shadow_note_path() if shadow_path is None else Path(shadow_path)
        self.terms_note_digest = None
        self.shadow_note_digest = None
        self._participation_rates = None
        self._advance_rates = None
        self._tier_rates = None
        self._uc_ids = None
        self._deferral = None
        self.outcome = 'NOT_BOUND'
        self.reason = SHADOW_NOT_BOUND_REASON
        self.policy_version = None
        self.note_digest = None
        self._reason_classes = []
        self._resale_entry = None
        self._load()

    def _load(self):
        block = _read_block(self.path)
        if block is None or block.get('schema') != 'capital-decision-v1':
            return
        entries = block.get('entries')
        if type(entries) is not dict:
            return
        self.note_digest = _sha256(block)
        version = block.get('policy_version')
        self.policy_version = version if _nonempty_str(version) else None
        bearer = entries.get('refund_bearer')
        resale = entries.get('resale_prior_contract_cancel_burden')
        if type(bearer) is dict and bearer.get('status') == 'ADOPTED':
            value = bearer.get('value')
            classes = value.get('reason_classes_ordered') if type(value) is dict else None
            if type(classes) is list and classes:
                parsed = []
                ok = True
                for row in classes:
                    if type(row) is not dict or not _nonempty_str(row.get('id')) or not _nonempty_str(row.get('bearer')):
                        ok = False
                        break
                    parsed.append({'id': row['id'], 'bearer': row['bearer']})
                if ok and len(parsed) == len({row['id'] for row in parsed}):
                    self._reason_classes = parsed
        if type(resale) is dict and resale.get('status') == 'ADOPTED' and type(resale.get('value')) is dict:
            triggers = resale['value'].get('triggers')
            if type(triggers) is list and all(
                    type(row) is dict and _nonempty_str(row.get('id')) for row in triggers):
                self._resale_entry = resale['value']
        self._load_slice_policy(entries)
        self.outcome = 'BOUND'
        self.reason = None

    def _load_slice_policy(self, entries):
        """Participation ratio/cap, advance rates, UC ids (settlement note), the
        tier rates (terms note) and the deferral text and vectors (shadow note)."""
        participation = _adopted_value(entries, 'revenue_participation')
        if participation is not None and _amount(participation.get('ratio_bps_of_base')) and _amount(
                participation.get('cap_bps_of_funded_amount')):
            self._participation_rates = (
                participation['ratio_bps_of_base'], participation['cap_bps_of_funded_amount'])
        purchase = _adopted_value(entries, 'claim_purchase')
        volume = purchase.get('volume') if purchase is not None else None
        advance = volume.get('advance_rate_bps_by_tier') if type(volume) is dict else None
        if type(advance) is dict and advance and all(
                _nonempty_str(tier) and _amount(bps) for tier, bps in advance.items()):
            self._advance_rates = dict(advance)
        residual = _adopted_value(entries, 'residual_and_late_cash')
        states = residual.get('undistributed_cash_states_ordered') if residual is not None else None
        if type(states) is list and all(type(row) is dict and _nonempty_str(row.get('id')) for row in states):
            ids = tuple(row['id'].split('_', 1)[0] for row in states)
            if ids == _UC_IDS:
                self._uc_ids = [row['id'] for row in states]
        terms = _read_block(self.terms_path)
        terms_entries = terms.get('entries') if terms is not None and terms.get('schema') == 'capital-decision-v1' else None
        interest = _adopted_value(terms_entries, 'interest_rate') if type(terms_entries) is dict else None
        tiers = interest.get('tiers') if interest is not None else None
        if interest is not None and interest.get('day_count') == _ACT_365 and type(tiers) is list:
            rates = {row['id']: row['all_in_bps_annual'] for row in tiers
                     if type(row) is dict and _nonempty_str(row.get('id'))
                     and _amount(row.get('all_in_bps_annual'))}
            if rates:
                self._tier_rates = rates
                self.terms_note_digest = _sha256(terms)
        shadow = _read_block(self.shadow_path)
        shadow_entries = shadow.get('entries') if shadow is not None and shadow.get('schema') == 'capital-decision-v1' else None
        deferral = _adopted_value(shadow_entries, 'revshare_claim_purchase_deferral') if type(shadow_entries) is dict else None
        if deferral is not None:
            self._deferral = deferral
            self.shadow_note_digest = _sha256(shadow)

    # -- module surface ----------------------------------------------------

    def status(self) -> dict:
        return {
            'label': SHADOW_LABEL,
            'mode': SHADOW_MODE,
            'provenance': SHADOW_PROVENANCE,
            'provisional': True,
            'shadow_rules_version': RULES_VERSION,
            'policy_version': self.policy_version,
            'note_digest': self.note_digest,
            'outcome': self.outcome,
            'reason': self.reason,
            **_false_flags(),
        }

    def refund_classes(self) -> list:
        """Ordered decided reason classes: [{id, bearer, working_assumption}]."""
        return [
            {**row, 'working_assumption': row['bearer'] == _RESIDUAL_THEN_FEE_WA}
            for row in self._reason_classes
        ]

    def resale_triggers(self) -> list:
        if self._resale_entry is None:
            return []
        return [row['id'] for row in self._resale_entry['triggers']]

    def worked_resale_vectors(self) -> list:
        """Synthetic input vectors read from the note's worked example values.

        The resale three lines are Move u128 floor inputs; the note states them
        verbatim, so they are read, never recomputed. The primary claim half is
        supplied by the caller as a pinned view snapshot.
        """
        if self._resale_entry is None:
            return []
        example = self._resale_entry.get('worked_example_synthetic')
        discount = self._resale_entry.get('worked_example_discount')
        if type(example) is not dict or type(discount) is not dict:
            return []
        sources = example.get('RU1_sources')
        if type(sources) is not dict:
            return []
        required = ('P_p', 'P_r', 'seller_due')
        dues = (sources.get('resale_organizer_due'), sources.get('resale_platform_due'))
        if any(not _amount(example.get(key)) for key in required) or any(
                not _amount(value) for value in dues):
            return []
        if any(not _amount(discount.get(key)) for key in ('P_p', 'P_r')):
            return []
        triggers = {row['id'].split('_', 1)[0]: row['id'] for row in self._resale_entry['triggers']}
        if sorted(triggers) != ['RU1', 'RU2', 'RU3']:
            return []
        premium = {
            'P_p': example['P_p'], 'P_r': example['P_r'],
            'seller_due': example['seller_due'],
            'organizer_due': dues[0], 'platform_due': dues[1],
            'trigger': triggers['RU1'],
        }
        vectors = [
            {'id': 'worked-ru1-premium', 'vector': dict(premium)},
            {'id': 'worked-ru1-discount', 'vector': {
                'P_p': discount['P_p'], 'P_r': discount['P_r'], 'trigger': triggers['RU1']}},
            {'id': 'worked-ru2', 'vector': {**premium, 'trigger': triggers['RU2']}},
            {'id': 'worked-ru3-full', 'vector': {
                **premium, 'trigger': triggers['RU3'], 'chargeback_amount': example['P_r']}},
            {'id': 'worked-ru3-partial-seller', 'vector': {
                **premium, 'trigger': triggers['RU3'], 'chargeback_amount': example['seller_due']}},
        ]
        return vectors

    def _envelope(self, status, detail=None):
        return {
            'status': status, 'detail': detail,
            'mode': SHADOW_MODE, 'label': SHADOW_LABEL,
            'provenance': SHADOW_PROVENANCE,
            'shadow_rules_version': RULES_VERSION if self.outcome == 'BOUND' else None,
            'note_digest': self.note_digest,
            **_false_flags(),
        }

    def _finish(self, result, vector):
        result['input_digest'] = _sha256(vector)
        result['result_digest'] = _sha256(result)
        return result

    def _not_bound_result(self, vector, detail=None):
        result = self._envelope(NOT_BOUND, detail or self.reason)
        result['input_digest'] = _sha256(vector)
        result['result_digest'] = _sha256(result)
        return result

    def deferred(self, item, detail):
        """Verdict for an adopted item this node does not compute."""
        if self.outcome != 'BOUND':
            return self._envelope(NOT_BOUND, self.reason)
        return self._envelope(DEFERRED, detail)

    # -- refund bearer (RC1-RC4; RC5 routes to resale) ----------------------

    def refund(self, vector) -> dict:
        """Shadow reversal split for the refund list of one claim vector."""
        if self.outcome != 'BOUND':
            return self._not_bound_result(vector)
        try:
            gross, residual_payee, fee_payee, lines, order = _parse_obligations(vector)
            refunds = vector.get('refunds')
            if type(refunds) is not list:
                raise ShadowInconsistent('refunds must be a list')
            seen = set()
            parsed = []
            for refund in refunds:
                refund_id, amount, reason_class, evidence_ref, adjudicated = _parse_refund_entry(refund)
                if refund_id in seen:
                    raise ShadowInconsistent('duplicate refund_id')
                seen.add(refund_id)
                parsed.append({
                    'refund_id': refund_id, 'amount': amount, 'reason_class': reason_class,
                    'evidence_ref': evidence_ref, 'adjudicated': adjudicated})
            if sum(row['amount'] for row in parsed) > gross:
                raise ShadowInconsistent('cumulative refund exceeds gross (REFUND_CEILING)')
        except ShadowInconsistent as exc:
            result = self._envelope(INCONSISTENT, exc.detail)
            result['refunds'] = None
            result['cumulative'] = None
            return self._finish(result, vector)

        bearers = {row['id']: row['bearer'] for row in self._reason_classes}
        clean_input = all(
            line['cancelled_unpaid'] == 0 and line['prior_recovery'] == 0
            for line in lines.values())
        entries = []
        pool_total = 0
        ok = True
        for row in parsed:
            pristine = clean_input and all(
                line['reversal'] == 0 and line['cancelled'] == 0 and line['recovery'] == 0
                for line in lines.values())
            entry = self._apply_refund(
                row, bearers, residual_payee, fee_payee, lines, order, gross, pristine)
            if entry['status'] == INCONSISTENT:
                ok = False
            pool_total += entry['shadow_platform_pool_obligation'] or 0
            entries.append(entry)
        cumulative = {
            'shadow_cumulative_refund': sum(
                entry['shadow_refund_amount'] for entry in entries
                if entry['status'] == COMPUTED),
            'shadow_platform_pool_obligation': pool_total,
            'auto_reclassified': False,
            'lines': [
                {'payee': payee,
                 'shadow_reversal': lines[payee]['reversal'],
                 'shadow_cancelled_unpaid': lines[payee]['cancelled'],
                 'shadow_recovery_due': lines[payee]['recovery']}
                for payee in order],
            'reconciliation': self._claim_reconciliation(gross, lines, order, parsed, clean_input),
        }
        result = self._envelope(COMPUTED if ok else INCONSISTENT,
                                None if ok else 'at least one refund entry is inconsistent')
        result['refunds'] = entries
        result['cumulative'] = cumulative
        return self._finish(result, vector)

    def _claim_reconciliation(self, gross, lines, order, refunds, clean_input):
        """MATCHES only for the pinned reclass shape: one refund of the full
        gross on a claim with no prior refunds, reproducing per-line
        cancelled_unpaid and recovery_due. Split refunds never match — the
        pinned FSM does not auto-reclassify them."""
        routed = any(
            row['reason_class'] in self._routed_classes() for row in refunds)
        if routed or not refunds:
            return NOT_COMPARABLE
        if len(refunds) != 1 or refunds[0]['amount'] != gross or not clean_input:
            return DIVERGES
        for payee in order:
            line = lines[payee]
            if line['cancelled'] != line['outstanding']:
                return DIVERGES
            if line['recovery'] != line['distributed'] - line['prior_recovery']:
                return DIVERGES
        return MATCHES

    def _routed_classes(self):
        return {row['id'] for row in self._reason_classes if _RESALE_ROUTED in row['bearer']}

    def _apply_refund(self, refund, bearers, residual_payee, fee_payee, lines, order, gross, pristine):
        entry = {
            'refund_id': refund['refund_id'],
            'reason_class': refund['reason_class'],
            'adjudicated_platform_fault': refund['adjudicated'],
            'status': None, 'detail': None, 'routed_to': None,
            'shadow_refund_amount': refund['amount'],
            'lines': None, 'shadow_platform_pool_obligation': None,
            'shadow_carry': None, 'working_assumption': False,
            'auto_reclassified': False, 'reconciliation': None,
        }
        bearer = bearers.get(refund['reason_class'])
        if bearer is None:
            entry['status'] = INCONSISTENT
            entry['detail'] = 'reason_class is not in the decided reason-class table'
            return entry
        if _RESALE_ROUTED in bearer:
            entry['status'] = INPUT_UNKNOWN
            entry['detail'] = 'resale unwind needs the resale input vector, not a refund vector'
            entry['routed_to'] = _RESALE_ROUTED
            entry['reconciliation'] = NOT_COMPARABLE
            return entry
        amount = refund['amount']
        reversal = {payee: 0 for payee in order}
        pool = 0
        working = bearer == _RESIDUAL_THEN_FEE_WA
        try:
            if bearer == _PRO_RATA_ALL:
                alloc, leftover = capped_pro_rata(
                    amount, [(payee, lines[payee]['face'], _remaining_face(lines[payee]))
                             for payee in order])
                if leftover:
                    raise ShadowInconsistent('refund exceeds the remaining faces')
                reversal.update(alloc)
            elif bearer in (_RESIDUAL_THEN_FEE, _RESIDUAL_THEN_FEE_WA) and not (
                    working and refund['adjudicated']):
                alloc, leftover = fill_sequential(
                    amount, [(residual_payee, _remaining_face(lines[residual_payee])),
                             (fee_payee, _remaining_face(lines[fee_payee]))])
                if leftover:
                    raise ShadowInconsistent('refund exceeds the remaining faces')
                reversal.update(alloc)
            elif bearer == _FEE_THEN_POOL or (working and refund['adjudicated']):
                alloc, pool = fill_sequential(
                    amount, [(fee_payee, _remaining_face(lines[fee_payee]))])
                reversal.update(alloc)
            else:
                raise ShadowInconsistent('bearer rule is outside the decided mechanics')
        except ShadowInconsistent as exc:
            entry['status'] = INCONSISTENT
            entry['detail'] = exc.detail
            return entry
        rows = []
        for payee in order:
            line = lines[payee]
            take = reversal[payee]
            cancelled = min(take, _open_outstanding(line))
            recovery = take - cancelled
            if recovery > _recovery_room(line):
                entry['status'] = INCONSISTENT
                entry['detail'] = 'recovery_due would exceed distributed minus prior recovery'
                return entry
            line['reversal'] += take
            line['cancelled'] += cancelled
            line['recovery'] += recovery
            rows.append({'payee': payee, 'shadow_reversal': take,
                         'shadow_cancelled_unpaid': cancelled,
                         'shadow_recovery_due': recovery})
        entry['status'] = COMPUTED
        entry['lines'] = rows
        entry['shadow_platform_pool_obligation'] = pool
        entry['shadow_carry'] = 0
        entry['working_assumption'] = working
        entry['reconciliation'] = DIVERGES
        if bearer in (_RESIDUAL_THEN_FEE, _RESIDUAL_THEN_FEE_WA):
            entry['reconciliation'] = self._refund_reconciliation(
                lines, order, refund['amount'], gross, pristine)
        return entry

    def _refund_reconciliation(self, lines, order, amount, gross, pristine):
        # MATCHES only in the pinned reclass shape: a lone full-gross refund on
        # a pristine claim reproducing every line's cancelled_unpaid/recovery.
        if amount != gross or not pristine:
            return DIVERGES
        for payee in order:
            line = lines[payee]
            if line['cancelled'] != line['outstanding']:
                return DIVERGES
            if line['recovery'] != line['distributed'] - line['prior_recovery']:
                return DIVERGES
        return MATCHES

    # -- participation, claim slice, residual partition -----------------------

    def item_binding(self, item):
        """None when the item's policy values are bound, else the reason."""
        if self.outcome != 'BOUND':
            return self.reason
        if item == 'revenue_participation':
            ready = self._participation_rates is not None
        elif item == 'claim_purchase':
            ready = self._advance_rates is not None and self._tier_rates is not None
        elif item == 'residual_and_late_cash':
            ready = self._uc_ids is not None
        else:
            return SHADOW_ENTRY_NOT_BOUND
        if not ready or self._item_note(item) is None:
            return SHADOW_ENTRY_NOT_BOUND
        return None

    def _item_note(self, item):
        entry = self._deferral.get(item) if self._deferral is not None else None
        return entry if type(entry) is dict else None

    def not_bound(self, detail=None):
        """Item verdict carrying no number when a note or entry is unbound."""
        return self._envelope(NOT_BOUND, detail or self.reason or SHADOW_ENTRY_NOT_BOUND)

    def note_vectors(self, item):
        """[{id, inputs, expected}] the shadow note states for the item."""
        entry = self._item_note(item)
        if entry is None:
            return []
        rows = [entry['vector']] if type(entry.get('vector')) is dict else entry.get('vectors')
        if type(rows) is not list:
            return []
        return [{'id': row['id'], 'inputs': row.get('inputs'), 'expected': row.get('expected')}
                for row in rows if type(row) is dict and _nonempty_str(row.get('id'))]

    def deferred_rows(self, item):
        """One SHADOW_DEFERRED row per deferred sub-item with its unblock seam."""
        entry = self._item_note(item)
        if self.item_binding(item) is not None or entry is None:
            return []
        names = entry.get('deferred_SHADOW_DEFERRED')
        unblock = entry.get('unblock')
        if type(names) is not list or not _nonempty_str(unblock):
            return []
        return [{'deferred_item': name, 'unblock': unblock, **self._envelope(DEFERRED, name)}
                for name in names if _nonempty_str(name)]

    def divide(self, total, weighted) -> list:
        """N-payee largest-remainder split; ties by ascending label."""
        return allocate_largest_remainder(total, weighted)

    def _slice_result(self, item, vector, required, compute, extra=None):
        """Shared INPUT_UNKNOWN / INCONSISTENT / COMPUTED shell for the three items."""
        reason = self.item_binding(item)
        if reason is not None:
            return self._not_bound_result(vector, reason)
        missing = [key for key in required if type(vector) is not dict or vector.get(key) is None]
        label = {'vector_id': None, 'input_source': None}
        if type(vector) is dict:
            label = {key: vector.get(key) if _nonempty_str(vector.get(key)) else None for key in label}
        if missing:
            result = self._envelope(INPUT_UNKNOWN, 'required inputs are absent')
            result['missing_inputs'] = missing
        else:
            try:
                body = compute(vector)
            except ShadowInconsistent as exc:
                result = self._envelope(INCONSISTENT, exc.detail)
                result['missing_inputs'] = []
            except _UnknownInput as exc:
                result = self._envelope(INPUT_UNKNOWN, exc.detail)
                result['missing_inputs'] = [exc.key]
            else:
                result = self._envelope(COMPUTED)
                result.update({f'shadow_{key}': value for key, value in body.items() if type(value) is int})
                result.update({key: value for key, value in body.items() if type(value) is not int})
                result['missing_inputs'] = []
        result['reconciliation'] = NOT_COMPARABLE
        result.update(label)
        if extra:
            result.update(extra)
        return self._finish(result, vector)

    def participation(self, vector) -> dict:
        """Single-claim participation posting (ratio and cap read from the note)."""
        def compute(v):
            ratio, cap = self._participation_rates
            return participation_posting(
                v['class2_allocated'], v['organizer_borne_refunds'], v['F'], v['paid_to_date'],
                ratio, cap)
        return self._slice_result(
            'revenue_participation', vector,
            ('class2_allocated', 'organizer_borne_refunds', 'F', 'paid_to_date'), compute)

    def claim_purchase(self, vector) -> dict:
        """Claim-slice maximum, discount and price (rates read from the notes)."""
        def compute(v):
            tier = v['tier']
            if not _nonempty_str(tier) or tier not in self._advance_rates or tier not in self._tier_rates:
                raise _UnknownInput('tier', 'tier is outside the decided tier table')
            body = slice_sizing(v['outstanding'], v['open_refund_face'], self._advance_rates[tier],
                                self._tier_rates[tier], v['expected_days'])
            body['tier'] = tier
            if 'registry' in v:
                from capital.slices import registry_check
                body['registry_check'] = registry_check(v['registry'], body['slice_face_max'])
            return body
        return self._slice_result(
            'claim_purchase', vector, ('outstanding', 'open_refund_face', 'tier', 'expected_days'),
            compute, {'terms_note_digest': self.terms_note_digest})

    def residual_partition(self, vector) -> dict:
        """Ordered UC1-UC4 split of undistributed cash. `pg_adjustment_outstanding`
        is required and validated but is not a partition input: the shadow note's
        UC2 formula uses `refund_outstanding` only."""
        def compute(v):
            _check_amount(v['pg_adjustment_outstanding'], 'pg_adjustment_outstanding')
            return uc_partition(v['confirmed_cash'], v['undistributed_cash'],
                                v['refund_outstanding'], v['reclassified'], v['obligations'])
        return self._slice_result(
            'residual_and_late_cash', vector,
            ('confirmed_cash', 'undistributed_cash', 'refund_outstanding', 'reclassified',
             'pg_adjustment_outstanding', 'obligations'), compute)

    # -- resale unwind (RU1-RU3) --------------------------------------------

    def resale(self, vector) -> dict:
        """Shadow unwind of one latest-trade resale vector. Never a chain walk."""
        if self.outcome != 'BOUND':
            return self._not_bound_result(vector)
        if self._resale_entry is None:
            result = self._envelope(NOT_BOUND, SHADOW_ENTRY_NOT_BOUND)
            result['input_digest'] = _sha256(vector)
            result['result_digest'] = _sha256(result)
            return result
        trigger = vector.get('trigger') if type(vector) is dict else None
        known = {row['id'].split('_', 1)[0]: row['id'] for row in self._resale_entry['triggers']}
        if not _nonempty_str(trigger) or trigger.split('_', 1)[0] not in known or trigger not in known.values():
            result = self._envelope(INPUT_UNKNOWN, 'trigger is missing or outside the decided set')
            result['missing_inputs'] = ['trigger']
            result['trigger'] = trigger if _nonempty_str(trigger) else None
            return self._finish(result, vector)
        prefix = trigger.split('_', 1)[0]
        required = ['P_p', 'P_r']
        if prefix == 'RU1':
            if _amount(vector.get('P_r')) and _amount(vector.get('P_p')) and vector['P_r'] >= vector['P_p']:
                required += [_SELLER, _ORGANIZER_DUE, _PLATFORM_DUE]
        elif prefix == 'RU2':
            required += [_SELLER, _ORGANIZER_DUE, _PLATFORM_DUE]
        elif prefix == 'RU3':
            required += [_SELLER, _ORGANIZER_DUE, _PLATFORM_DUE, 'chargeback_amount']
        missing = [key for key in required if not _amount(vector.get(key))]
        primary = vector.get('primary')
        if prefix == 'RU1' and type(primary) is not dict:
            missing.append('primary')
        if missing:
            result = self._envelope(INPUT_UNKNOWN, 'required resale inputs are absent')
            result['missing_inputs'] = missing
            result['trigger'] = trigger
            return self._finish(result, vector)
        try:
            if prefix == 'RU1':
                body = self._resale_ru1(vector)
            elif prefix == 'RU2':
                body = self._resale_ru2(vector)
            else:
                body = self._resale_ru3(vector)
        except ShadowInconsistent as exc:
            result = self._envelope(INCONSISTENT, exc.detail)
            result['trigger'] = trigger
            result['missing_inputs'] = []
            return self._finish(result, vector)
        result = self._envelope(COMPUTED)
        result.update(body)
        result['trigger'] = trigger
        result['missing_inputs'] = []
        return self._finish(result, vector)

    def _primary_reversal(self, vector):
        """The RU1 primary refund reuses the RC2 shadow for amount P_p."""
        primary = vector['primary']
        gross, residual_payee, fee_payee, lines, order = _parse_obligations(primary)
        if vector['P_p'] != gross:
            raise ShadowInconsistent('P_p differs from the primary claim gross')
        alloc, leftover = fill_sequential(
            vector['P_p'], [(residual_payee, _remaining_face(lines[residual_payee])),
                            (fee_payee, _remaining_face(lines[fee_payee]))])
        if leftover:
            raise ShadowInconsistent('the primary claim cannot fund a P_p refund')
        by_line = []
        for payee, take in alloc:
            line = lines[payee]
            cancelled = min(take, _open_outstanding(line))
            by_line.append({'payee': payee, 'shadow_reversal': take,
                            'shadow_cancelled_unpaid': cancelled,
                            'shadow_recovery_due': take - cancelled})
        reconciliation = MATCHES
        for payee in order:
            line = lines[payee]
            applied = dict(alloc)[payee]
            if min(applied, _open_outstanding(line)) != line['outstanding'] or (
                    applied - min(applied, _open_outstanding(line))) != line['distributed'] - line['prior_recovery']:
                reconciliation = DIVERGES
        return by_line, reconciliation

    def _resale_ru1(self, vector):
        p_p, p_r = vector['P_p'], vector['P_r']
        by_line, primary_recon = self._primary_reversal(vector)
        if p_r < p_p:
            return {
                'shadow_holder_entitlement': p_r,
                'shadow_holder_market_risk': 0,
                'shadow_seller_receives': p_p - p_r,
                'shadow_seller_kept': vector.get(_SELLER) if _amount(vector.get(_SELLER)) else None,
                'shadow_primary_refund_by_line': by_line,
                'shadow_resale_line_reversal': [
                    {'line': name, 'shadow_reversal': 0}
                    for name in (_SELLER, _ORGANIZER_DUE, _PLATFORM_DUE)],
                'shadow_recovery_due': [],
                'reconciliation': NOT_COMPARABLE,
                'primary_refund_reconciliation': primary_recon,
            }
        entitlement = min(p_r, p_p + vector[_ORGANIZER_DUE] + vector[_PLATFORM_DUE])
        fills, leftover = fill_sequential(
            entitlement - p_p, [(_ORGANIZER_DUE, vector[_ORGANIZER_DUE]),
                                (_PLATFORM_DUE, vector[_PLATFORM_DUE])])
        if leftover:
            raise ShadowInconsistent('resale reversals cannot fund the entitlement')
        reversal = dict(fills)
        return {
            'shadow_holder_entitlement': entitlement,
            'shadow_holder_market_risk': p_r - entitlement,
            'shadow_seller_receives': 0,
            'shadow_seller_kept': vector[_SELLER],
            'shadow_primary_refund_by_line': by_line,
            'shadow_resale_line_reversal': [
                {'line': _SELLER, 'shadow_reversal': 0},
                {'line': _ORGANIZER_DUE, 'shadow_reversal': reversal[_ORGANIZER_DUE]},
                {'line': _PLATFORM_DUE, 'shadow_reversal': reversal[_PLATFORM_DUE]}],
            'shadow_recovery_due': [],
            'reconciliation': NOT_COMPARABLE,
            'primary_refund_reconciliation': primary_recon,
        }

    def _resale_ru2(self, vector):
        p_r = vector['P_r']
        dues = (vector[_SELLER], vector[_ORGANIZER_DUE], vector[_PLATFORM_DUE])
        if sum(dues) != p_r:
            raise ShadowInconsistent('the three resale lines do not sum to P_r')
        return {
            'shadow_holder_entitlement': p_r,
            'shadow_holder_market_risk': 0,
            'shadow_seller_receives': 0,
            'shadow_seller_kept': 0,
            'shadow_primary_refund_by_line': None,
            'shadow_resale_line_reversal': [
                {'line': name, 'shadow_reversal': amount}
                for name, amount in zip((_SELLER, _ORGANIZER_DUE, _PLATFORM_DUE), dues)],
            'shadow_recovery_due': [],
            'reconciliation': NOT_COMPARABLE,
            'primary_refund_reconciliation': None,
        }

    def _resale_ru3(self, vector):
        p_r = vector['P_r']
        chargeback = vector['chargeback_amount']
        if chargeback > p_r:
            raise ShadowInconsistent('chargeback_amount exceeds P_r')
        fills, leftover = fill_sequential(
            chargeback, [(name, vector[name]) for name in (_SELLER, _ORGANIZER_DUE, _PLATFORM_DUE)])
        if leftover:
            raise ShadowInconsistent('chargeback exceeds the three resale lines')
        taken = dict(fills)
        return {
            'shadow_holder_entitlement': 0,
            'shadow_holder_market_risk': 0,
            'shadow_seller_receives': 0,
            'shadow_seller_kept': vector[_SELLER] - taken[_SELLER],
            'shadow_primary_refund_by_line': None,
            'shadow_resale_line_reversal': [
                {'line': _ORGANIZER_DUE, 'shadow_reversal': taken[_ORGANIZER_DUE]},
                {'line': _PLATFORM_DUE, 'shadow_reversal': taken[_PLATFORM_DUE]}],
            'shadow_recovery_due': [
                {'line': _SELLER, 'shadow_recovery_due': taken[_SELLER]}],
            'reconciliation': NOT_COMPARABLE,
            'primary_refund_reconciliation': None,
        }


@runtime_checkable
class ShadowPolicyPort(Protocol):
    """Shadow arithmetic for entries the pinned FSM cannot express.

    Pure functions over frozen input vectors only. No vendor import, no FSM
    command, no workspace write; every result is mode SHADOW_NOT_APPLIED and
    carries the constant false flags. Passing these vectors is not an upstream
    adoption and not SEMANTIC_CONFORMANCE.
    """

    def status(self) -> dict:
        """Module bind state. Does not compute a shadow result."""

    def refund(self, vector) -> dict:
        """Refund-bearer shadow for one claim vector (RC1-RC4; RC5 routes)."""

    def resale(self, vector) -> dict:
        """Latest-trade resale unwind shadow (RU1-RU3). Inputs are explicit."""

    def participation(self, vector) -> dict:
        """Single-claim revenue participation posting shadow."""

    def claim_purchase(self, vector) -> dict:
        """Claim-slice size, discount and price shadow."""

    def residual_partition(self, vector) -> dict:
        """Ordered UC1-UC4 partition of undistributed cash."""

    def divide(self, total, weighted) -> list:
        """N-payee largest-remainder split."""
