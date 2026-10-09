"""Read-only simulated overlay of the decided credit terms.

Values come from the capital-decision-v1 block in the financial-terms note.
This module does not import the vendor FSM, does not post a journal, and does
not make an offer. A missing note, a bad block, or no usable ADOPTED entry is
NOT_BOUND. The zipapp does not bundle docs/, so that run stays NOT_BOUND.
"""
from __future__ import annotations

import datetime
import importlib.resources
import json
import re
from fractions import Fraction
from pathlib import Path
from typing import Protocol, runtime_checkable

OVERLAY_LABEL = 'simulated overlay — not vendor FSM arithmetic, not an offer'
TERMS_NOT_BOUND = 'terms not bound'
TIER_NOT_APPLICABLE = 'tier not applicable'
BPS_SCALE = 10000

_FENCE = re.compile(r'```capital-decision-v1[ \t]*\n(.*?)```', re.DOTALL)
_ISO_DATE = re.compile(r'\d{4}-\d{2}-\d{2}\Z')
_DAY_COUNT = re.compile(r'\AACT_(\d+)_FIXED\Z')
_METHOD = 'SIMPLE_INTEREST_ON_OUTSTANDING_PRINCIPAL'
_COMPOUNDING = 'NONE'
_ACCRUAL_START = 'DRAW_DAY_INCLUSIVE'
_ACCRUAL_END = 'REPAYMENT_DAY_EXCLUSIVE'
_ROUNDING = 'EXACT_RATIONAL_ACCRUAL_FLOOR_TO_1_KRW_AT_POSTING_CARRY_REMAINDER'
_DEFAULT_FROM = 'MATURITY_DAY_PLUS_1'
_LATE_FEE_NONE = 'NONE_DEFAULT_INTEREST_ONLY'
_SETTLEMENT_RULE = (
    'term_days = clamp(expected_settlement_cash_day - draw_day + settlement_slack_days, '
    'min_term_days, max_term_days) when an expected settlement cash day is known; '
    'otherwise standard_term_days'
)
_FEE_KEYS = (
    'origination_fee_bps',
    'servicing_fee_bps_annual',
    'commitment_fee_bps_annual_on_undrawn',
    'extension_fee_bps',
    'prepayment_penalty_bps',
)
_ANNUAL_FEE_KEYS = (
    'servicing_fee_bps_annual',
    'commitment_fee_bps_annual_on_undrawn',
)
_ONE_TIME_FEE_KEYS = (
    'origination_fee_bps',
    'extension_fee_bps',
    'prepayment_penalty_bps',
)
_NO_DRAW_PHASES = frozenset(('OFFERED', 'REJECTED', 'CANCELLED'))
_PRINCIPAL_CONSTANT = 'principal is constant; the pinned journal has no repayment days'
_PAST_DUE = 'PAST_DUE_ANY_TIER'
_DEFAULTED_BUCKET = 'DEFAULTED'
_STANDARD = 'standard'
_LINKED = 'settlement_linked'


def default_note_path():
    """Checkout path of the financial-terms note. Absent inside the zipapp."""
    package = importlib.resources.files('capital')
    return Path(str(package)).parent / 'docs' / 'decisions' / 'CAPITAL_FINANCIAL_TERMS.md'


def _reject_duplicate_keys(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate key')
        obj[key] = value
    return obj


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


def _nonneg_int(value):
    return type(value) is int and value >= 0


def _day_count(value):
    if type(value) is not str:
        return None
    match = _DAY_COUNT.fullmatch(value)
    if match is None:
        return None
    count = int(match.group(1))
    if count <= 0:
        return None
    return count


def _unbound_section():
    return {'status': 'NOT_BOUND', 'reason': TERMS_NOT_BOUND}


def _not_applicable_section():
    return {'status': 'NOT_APPLICABLE', 'reason': TIER_NOT_APPLICABLE}


def _clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value


def _fee_bps(value):
    total = 0
    for key in _FEE_KEYS:
        total += value[key]
    late = value.get('late_fee')
    if type(late) is int:
        total += late
    return total


def _interest_usable(value):
    if type(value) is not dict:
        return False
    if value.get('method') != _METHOD or value.get('compounding') != _COMPOUNDING:
        return False
    if value.get('accrual_start') != _ACCRUAL_START or value.get('accrual_end') != _ACCRUAL_END:
        return False
    if value.get('rounding') != _ROUNDING or value.get('default_interest_from') != _DEFAULT_FROM:
        return False
    if _day_count(value.get('day_count')) is None:
        return False
    if not _nonneg_int(value.get('min_interest_days')):
        return False
    if not _nonneg_int(value.get('base_rate_bps_annual')):
        return False
    if not _nonneg_int(value.get('default_interest_add_bps_annual')):
        return False
    if not _nonneg_int(value.get('all_in_cost_cap_bps_annual')):
        return False
    tiers = value.get('tiers')
    if type(tiers) is not list or not tiers:
        return False
    base = value['base_rate_bps_annual']
    for tier in tiers:
        if type(tier) is not dict or not _nonempty_str(tier.get('id')):
            return False
        if not _nonneg_int(tier.get('spread_bps_annual')) or not _nonneg_int(tier.get('all_in_bps_annual')):
            return False
        if tier['all_in_bps_annual'] != base + tier['spread_bps_annual']:
            return False
        condition = tier.get('condition')
        if type(condition) is not dict or not _nonempty_str(condition.get('settlement_gate')):
            return False
        if 'refund_face' in condition and not _nonneg_int(condition.get('refund_face')):
            return False
    return True


def _fees_usable(value):
    if type(value) is not dict or not _nonempty_str(value.get('policy')):
        return False
    for key in _FEE_KEYS:
        if not _nonneg_int(value.get(key)):
            return False
    late = value.get('late_fee')
    if late != _LATE_FEE_NONE and not _nonneg_int(late):
        return False
    return True


def _term_usable(value):
    if type(value) is not dict:
        return False
    if value.get('settlement_linked_rule') != _SETTLEMENT_RULE:
        return False
    keys = (
        'standard_term_days', 'min_term_days', 'max_term_days',
        'settlement_slack_days', 'grace_days_after_maturity',
    )
    for key in keys:
        if not _nonneg_int(value.get(key)):
            return False
    low, high = value['min_term_days'], value['max_term_days']
    standard = value['standard_term_days']
    if low > high or standard < low or standard > high:
        return False
    return True


def _loss_usable(value):
    if type(value) is not dict:
        return False
    if not _nonneg_int(value.get('writeoff_days_after_default')):
        return False
    waterfall = value.get('recovery_waterfall')
    if type(waterfall) is not list or not waterfall or any(not _nonempty_str(item) for item in waterfall):
        return False
    if not _nonempty_str(value.get('loss_bearer_v1')):
        return False
    return True


def _underwriting_usable(value):
    if type(value) is not dict:
        return False
    if not _nonempty_str(value.get('depth')) or not _nonempty_str(value.get('personal_credit_data')):
        return False
    if not _nonempty_str(value.get('ai_role')):
        return False
    checks = value.get('checks_ordered')
    if type(checks) is not list or not checks:
        return False
    for item in checks:
        if type(item) is not dict or not _nonempty_str(item.get('id')):
            return False
    return True


def _collateral_usable(value):
    if type(value) is not dict:
        return False
    ladder = value.get('ladder_ordered')
    if type(ladder) is not list or not ladder or any(not _nonempty_str(item) for item in ladder):
        return False
    required = value.get('required_by_tier')
    if type(required) is not dict or not required:
        return False
    for spec in required.values():
        if type(spec) is not dict:
            return False
        if not _nonempty_str(spec.get('simulation')) or not _nonempty_str(spec.get('real_funds_minimum')):
            return False
    if not _nonempty_str(value.get('chain_evidence_role')):
        return False
    return True


def _margin_usable(value):
    if type(value) is not dict:
        return False
    rates = value.get('advance_rate_bps_by_tier')
    if type(rates) is not dict or not rates or any(not _nonneg_int(item) for item in rates.values()):
        return False
    mapping = value.get('beneficiary_payee_map')
    if type(mapping) is not dict or not mapping:
        return False
    for payees in mapping.values():
        if type(payees) is not list or not payees or any(not _nonempty_str(item) for item in payees):
            return False
    return True


def _execution_usable(value):
    if type(value) is not dict:
        return False
    for key in ('primary', 'secondary', 'tertiary', 'execution_authority'):
        if not _nonempty_str(value.get(key)):
            return False
    never = value.get('never')
    if type(never) is not list or any(not _nonempty_str(item) for item in never):
        return False
    return True


def _reserve_usable(value):
    if type(value) is not dict:
        return False
    weights = value.get('provision_bps_of_outstanding')
    if type(weights) is not dict:
        return False
    for key in (_PAST_DUE, _DEFAULTED_BUCKET):
        if not _nonneg_int(weights.get(key)):
            return False
    if any(not _nonneg_int(item) for item in weights.values()):
        return False
    if not _nonempty_str(value.get('funding_source')):
        return False
    forbidden = value.get('forbidden_sources')
    if type(forbidden) is not list or any(not _nonempty_str(item) for item in forbidden):
        return False
    return True


_USABLE = {
    'interest_rate': _interest_usable,
    'fees': _fees_usable,
    'term': _term_usable,
    'default_loss_treatment': _loss_usable,
    'underwriting_depth': _underwriting_usable,
    'external_collateral_completeness': _collateral_usable,
    'additional_margin': _margin_usable,
    'collateral_execution': _execution_usable,
    'reserve': _reserve_usable,
}


def _entry_mark(entry):
    """Return (mark, value). ADOPTED only when the note entry is fully usable."""
    if type(entry) is not dict or entry.get('status') != 'ADOPTED':
        return 'UNDETERMINED', None
    if type(entry.get('value')) is not dict:
        return 'UNDETERMINED', None
    if not _nonempty_str(entry.get('provided_by')) or not _iso_date(entry.get('date')):
        return 'UNDETERMINED', None
    if entry.get('provisional') is not True:
        return 'UNDETERMINED', None
    return 'ADOPTED', entry['value']


@runtime_checkable
class TermsPolicyPort(Protocol):
    """Read decided terms and render one simulated case overlay. Not an offer."""

    def status(self) -> dict:
        """Policy status without case data."""

    def overlay(self, case, claim, *, draw_day, as_of_day, expected_settlement_cash_day, gate) -> dict:
        """Simulated schedule, accrual preview, and indicators for one case."""


class DecisionNoteTermsPolicy:
    """Load one capital-decision-v1 note. Unsupported tokens stay NOT_BOUND."""

    def __init__(self, path=None):
        self.path = default_note_path() if path is None else Path(path)
        self.version = None
        self.top = 'NOT_BOUND'
        self.reason = TERMS_NOT_BOUND
        self.items = {}
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
        if block.get('schema') != 'capital-decision-v1' or block.get('currency') != 'KRW':
            return
        version = block.get('terms_version')
        if not _nonempty_str(version):
            return
        entries = block.get('entries')
        if type(entries) is not dict:
            return
        items = {}
        for name, entry in entries.items():
            mark, value = _entry_mark(entry)
            if mark == 'ADOPTED':
                check = _USABLE.get(name)
                if check is None or not check(value):
                    mark, value = 'NOT_BOUND', None
            items[name] = {'mark': mark, 'value': value}
        self.items = items
        self.version = version
        marks = [item['mark'] for item in items.values()]
        if marks and all(mark == 'ADOPTED' for mark in marks):
            self.top = 'BOUND'
            self.reason = None
        elif any(mark == 'ADOPTED' for mark in marks):
            self.top = 'PARTIAL'
            self.reason = None
        else:
            self.top = 'NOT_BOUND'
            self.reason = TERMS_NOT_BOUND

    def _ready(self, *names):
        return all(self.items.get(name, {}).get('mark') == 'ADOPTED' for name in names)

    def _value(self, name):
        item = self.items.get(name)
        if item is None or item['mark'] != 'ADOPTED':
            return None
        return item['value']

    def _section_flags(self):
        return {
            'schedule': 'BOUND' if self._ready('term', 'default_loss_treatment') else 'NOT_BOUND',
            'accrual': 'BOUND' if self._ready('interest_rate', 'fees', 'term') else 'NOT_BOUND',
            'collateral': 'BOUND' if self._ready('external_collateral_completeness') else 'NOT_BOUND',
            'borrowing_base': 'BOUND' if self._ready('additional_margin') else 'NOT_BOUND',
            'reserve_provision': 'BOUND' if self._ready('reserve') else 'NOT_BOUND',
        }

    def status(self) -> dict:
        return {
            'label': OVERLAY_LABEL,
            'mode': 'SIMULATED_OVERLAY',
            'terms_version': self.version,
            'provisional': True,
            'status': self.top,
            'reason': self.reason,
            'items': {name: item['mark'] for name, item in self.items.items()},
            'sections': self._section_flags(),
        }

    def _tier(self, case, claim, gate):
        phase = case.get('phase')
        if phase in _NO_DRAW_PHASES:
            return None
        interest = self._value('interest_rate')
        if interest is None:
            return None
        refund = claim.get('refund_face')
        if not _nonneg_int(refund):
            return None
        for tier in interest['tiers']:
            condition = tier['condition']
            if condition.get('settlement_gate') != gate:
                continue
            if 'refund_face' in condition and condition['refund_face'] != refund:
                continue
            return tier
        return None

    def _principal(self, case):
        key = 'amount' if case.get('phase') == 'APPROVED' else 'outstanding_exposure'
        value = case.get(key)
        if type(value) is not int:
            return None
        return value

    def _term_days(self, draw_day, expected_settlement_cash_day):
        term = self._value('term')
        if expected_settlement_cash_day is None:
            return term['standard_term_days'], _STANDARD
        raw = expected_settlement_cash_day - draw_day + term['settlement_slack_days']
        return _clamp(raw, term['min_term_days'], term['max_term_days']), _LINKED

    def _schedule(self, draw_day, expected_settlement_cash_day):
        if not self._ready('term', 'default_loss_treatment'):
            return _unbound_section()
        term_days, source = self._term_days(draw_day, expected_settlement_cash_day)
        term = self._value('term')
        loss = self._value('default_loss_treatment')
        maturity = draw_day + term_days
        grace = term['grace_days_after_maturity']
        default_eligible = maturity + grace + 1
        return {
            'status': 'BOUND',
            'term_days': term_days,
            'maturity_day': maturity,
            'grace_days': grace,
            'default_eligible_day': default_eligible,
            'writeoff_day': default_eligible + loss['writeoff_days_after_default'],
            'source': source,
        }

    def _accrual(self, principal, draw_day, as_of_day, tier, schedule):
        if not self._ready('interest_rate', 'fees', 'term'):
            return _unbound_section()
        if tier is None or schedule.get('status') != 'BOUND' or principal is None:
            return _not_applicable_section()
        interest = self._value('interest_rate')
        fees = self._value('fees')
        day_count = _day_count(interest['day_count'])
        minimum = interest['min_interest_days']
        elapsed = as_of_day - draw_day
        if elapsed < minimum:
            elapsed = minimum
        contractual_limit = schedule['term_days']
        if elapsed <= contractual_limit:
            contractual_days = elapsed
            default_days = 0
        else:
            contractual_days = contractual_limit
            default_days = elapsed - contractual_limit
        contract_bps = tier['all_in_bps_annual']
        default_bps = contract_bps + interest['default_interest_add_bps_annual']
        numerator = principal * contractual_days * contract_bps + principal * default_days * default_bps
        denominator = BPS_SCALE * day_count
        exact = Fraction(numerator, denominator)
        annual = contract_bps + interest['default_interest_add_bps_annual']
        for key in _ANNUAL_FEE_KEYS:
            annual += fees[key]
        one_time = 0
        for key in _ONE_TIME_FEE_KEYS:
            one_time += fees[key]
        if type(fees.get('late_fee')) is int:
            one_time += fees['late_fee']
        term_days = schedule['term_days']
        cap = interest['all_in_cost_cap_bps_annual']
        cap_ok = annual * term_days + one_time * day_count <= cap * term_days
        return {
            'status': 'BOUND',
            'exact': f'{exact.numerator}/{exact.denominator}',
            'interest_krw': exact.numerator // exact.denominator,
            'assumption': _PRINCIPAL_CONSTANT,
            'all_in_bps_annual': contract_bps,
            'cap_ok': cap_ok,
            'contractual_days': contractual_days,
            'default_days': default_days,
            'fee_bps_charged': _fee_bps(fees),
        }

    def _flag(self, case, name):
        value = case.get(name, False)
        if type(value) is not bool:
            return False
        return value

    def _collateral(self, case, tier):
        if not self._ready('external_collateral_completeness'):
            return _unbound_section()
        if tier is None:
            return _not_applicable_section()
        value = self._value('external_collateral_completeness')
        spec = value['required_by_tier'].get(tier['id'])
        if type(spec) is not dict:
            return _unbound_section()
        return {
            'status': 'BOUND',
            'rung': spec['simulation'],
            'synthetic': True,
            'real_funds_minimum': spec['real_funds_minimum'],
            'chain_evidence_role': value['chain_evidence_role'],
            'flags': {
                'collateral_perfected': self._flag(case, 'collateral_perfected'),
                'external_pledge_complete': self._flag(case, 'external_pledge_complete'),
                'priority_bound': self._flag(case, 'priority_bound'),
            },
        }

    def _borrowing_base(self, case, claim, tier):
        if not self._ready('additional_margin'):
            return _unbound_section()
        if tier is None:
            return _not_applicable_section()
        value = self._value('additional_margin')
        role = case.get('beneficiary_role')
        payees = value['beneficiary_payee_map'].get(role)
        rate = value['advance_rate_bps_by_tier'].get(tier['id'])
        obligations = claim.get('obligations')
        refund = claim.get('refund_face')
        if payees is None or not _nonneg_int(rate) or type(obligations) is not list or not _nonneg_int(refund):
            return _unbound_section()
        eligible = 0
        for line in obligations:
            if type(line) is not dict or line.get('payee') not in payees:
                continue
            outstanding = line.get('outstanding')
            if not _nonneg_int(outstanding):
                return _unbound_section()
            eligible += outstanding
        eligible -= refund
        base = eligible * rate // BPS_SCALE
        exposure = case.get('outstanding_exposure')
        if type(exposure) is not int:
            return _unbound_section()
        return {
            'status': 'BOUND',
            'eligible_face': eligible,
            'advance_rate_bps': rate,
            'base_krw': base,
            'margin_call': exposure > base,
        }

    def _reserve(self, case, as_of_day, tier, schedule):
        if not self._ready('reserve'):
            return _unbound_section()
        value = self._value('reserve')
        weights = value['provision_bps_of_outstanding']
        exposure = case.get('outstanding_exposure')
        if type(exposure) is not int:
            return _unbound_section()
        phase = case.get('phase')
        past_due = (
            schedule.get('status') == 'BOUND'
            and exposure > 0
            and phase != 'DEFAULTED'
            and as_of_day > schedule['maturity_day']
        )
        if phase == 'DEFAULTED':
            bucket = _DEFAULTED_BUCKET
        elif past_due:
            bucket = _PAST_DUE
        elif tier is None:
            return _not_applicable_section()
        else:
            bucket = tier['id']
        bps = weights.get(bucket)
        if not _nonneg_int(bps):
            return _unbound_section()
        return {
            'status': 'BOUND',
            'bucket': bucket,
            'provision_bps': bps,
            'provision_krw': exposure * bps // BPS_SCALE,
            'funding_source': value['funding_source'],
            'applied': False,
        }

    def _echo(self):
        underwriting = self._value('underwriting_depth')
        execution = self._value('collateral_execution')
        loss = self._value('default_loss_treatment')
        if underwriting is None:
            underwriting_echo = _unbound_section()
        else:
            underwriting_echo = {
                'applied': False,
                'depth': underwriting['depth'],
                'personal_credit_data': underwriting['personal_credit_data'],
                'ai_role': underwriting['ai_role'],
                'check_ids': [item['id'] for item in underwriting['checks_ordered']],
            }
        if execution is None:
            execution_echo = _unbound_section()
        else:
            execution_echo = {
                'applied': False,
                'primary': execution['primary'],
                'secondary': execution['secondary'],
                'tertiary': execution['tertiary'],
                'never': list(execution['never']),
                'execution_authority': execution['execution_authority'],
            }
        if loss is None:
            loss_echo = _unbound_section()
        else:
            loss_echo = {
                'applied': False,
                'recovery_waterfall': list(loss['recovery_waterfall']),
                'loss_bearer_v1': loss['loss_bearer_v1'],
            }
        return {
            'underwriting_depth': underwriting_echo,
            'collateral_execution': execution_echo,
            'loss_waterfall': loss_echo,
        }

    def _unbound_overlay(self):
        return {
            'label': OVERLAY_LABEL,
            'mode': 'SIMULATED_OVERLAY',
            'terms_version': self.version,
            'provisional': True,
            'status': 'NOT_BOUND',
            'reason': TERMS_NOT_BOUND,
            'schedule': _unbound_section(),
            'accrual': _unbound_section(),
            'collateral': _unbound_section(),
            'borrowing_base': _unbound_section(),
            'reserve_provision': _unbound_section(),
            'not_applied': _unbound_section(),
        }

    def overlay(self, case, claim, *, draw_day, as_of_day, expected_settlement_cash_day, gate) -> dict:
        if self.top == 'NOT_BOUND':
            return self._unbound_overlay()
        if type(case) is not dict or type(claim) is not dict:
            return self._unbound_overlay()
        tier = self._tier(case, claim, gate)
        short = None if tier is None else tier['id'].split('_', 1)[0]
        principal = self._principal(case)
        schedule = self._schedule(draw_day, expected_settlement_cash_day)
        return {
            'label': OVERLAY_LABEL,
            'mode': 'SIMULATED_OVERLAY',
            'terms_version': self.version,
            'provisional': True,
            'status': self.top,
            'reason': self.reason,
            'tier': 'NOT_APPLICABLE' if short is None else short,
            'principal': principal,
            'schedule': schedule,
            'accrual': self._accrual(principal, draw_day, as_of_day, tier, schedule),
            'collateral': self._collateral(case, tier),
            'borrowing_base': self._borrowing_base(case, claim, tier),
            'reserve_provision': self._reserve(case, as_of_day, tier, schedule),
            'not_applied': self._echo(),
        }
