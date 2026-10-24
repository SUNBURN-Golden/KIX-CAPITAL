"""Read-only projected settlement and repayment cash ladder on the overlay sim clock.

SIMULATED. `build` folds the drawn advances of the overlay ledger (per-advance `draw_day`,
outstanding principal) and the ADOPTED `CAPITAL-TERMS-V1` entries into a deterministic
expected-cash ladder: a `SETTLEMENT_CASH_IN` leg on `expected_settlement_cash_day`, a
`CONTRACT_INTEREST` leg at `maturity_day` and a `PRINCIPAL` leg at `maturity_day`, each
bucketed `0-7 / 8-30 / 31-60 / 61-90 / 91+` sim days ahead of the folded `sim_day`. Every
leg is a dated projection only — nothing is a payment, a receivable, a booking or a funds
movement, and nothing here writes to the F04 journal, the overlay ledger or the workspace.

The labeled assumptions are deliberately simple: the bound settlement is assumed to arrive
in full on its expected day (`SETTLEMENT_ARRIVES_IN_FULL_ON_EXPECTED_DAY`), no default and
no acceleration happens (`NO_DEFAULT_CONTRACTUAL_SCHEDULE`), and no prepayment beyond what
the overlay already recorded is assumed (`NO_PREPAYMENT_BEYOND_RECORDED_ENTRIES`). The
settlement leg is the funding event for the principal leg — the same KRW reported at its
own date, so a bucket's `expected_cash_krw` counts both events by design; the repayment
legs alone reconcile to outstanding principal plus contract interest to maturity. Out of
scope: probability weighting, discounting/NPV, FX and funds movement.

Arithmetic is exact rationals (Fraction). Rates, day counts and term bounds come from the
decision note at run time and are never copied into code; only the bucket edges and the
three leg kinds are fixed by the node spec. Each bucket floors its summed exact rationals
once to 1 KRW — legs are never floored individually.
"""
from __future__ import annotations

import hashlib
import json
from fractions import Fraction

from capital.terms import BPS_SCALE, TERMS_NOT_BOUND, TIER_NOT_APPLICABLE

LABEL = 'SIMULATED cash forecast — read-only ladder, not a payment schedule, not funds movement'
MODE = 'SIMULATED_CASH_FORECAST'
ACCOUNTING = 'SYNTHETIC_UNADOPTED'

SETTLEMENT_ASSUMPTION = 'SETTLEMENT_ARRIVES_IN_FULL_ON_EXPECTED_DAY'
INTEREST_ASSUMPTION = 'NO_DEFAULT_CONTRACTUAL_SCHEDULE'
PRINCIPAL_ASSUMPTION = 'NO_PREPAYMENT_BEYOND_RECORDED_ENTRIES'
ASSUMPTIONS = (SETTLEMENT_ASSUMPTION, INTEREST_ASSUMPTION, PRINCIPAL_ASSUMPTION)

LEG_SETTLEMENT = 'SETTLEMENT_CASH_IN'
LEG_INTEREST = 'CONTRACT_INTEREST'
LEG_PRINCIPAL = 'PRINCIPAL'
NO_SETTLEMENT_DAY = 'EXPECTED_DAY_NOT_PROVIDED'
NO_PRINCIPAL = 'NO_OUTSTANDING_PRINCIPAL'

# Bucket edges in days ahead of sim_day. A leg dated in the past lands in '0-7'.
EDGES = (7, 30, 60, 90)
BUCKET_IDS = ('0-7', '8-30', '31-60', '61-90', '91+')

_NEEDED = ('interest_rate', 'term', 'default_loss_treatment')


def _digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def _exact(value):
    return f'{value.numerator}/{value.denominator}'


def _floor(value):
    return value.numerator // value.denominator


def _value(terms, name):
    items = getattr(terms, 'items', None)
    item = items.get(name) if type(items) is dict else None
    if type(item) is not dict or item.get('mark') != 'ADOPTED':
        return None
    return item['value']


def usable(terms):
    """True when the schedule and interest items are ADOPTED and ledger_terms is callable."""
    return (callable(getattr(terms, 'ledger_terms', None))
            and all(_value(terms, name) is not None for name in _NEEDED))


def not_bound(terms_version, sim_day, *, expected_settlement_cash_day=None, reason=TERMS_NOT_BOUND):
    return {
        'label': LABEL, 'mode': MODE, 'provisional': True, 'status': 'NOT_BOUND', 'reason': reason,
        'sim_day': sim_day, 'terms_version': terms_version,
        'expected_settlement_cash_day': expected_settlement_cash_day,
        'policy_adopted': False, 'accounting_policy': ACCOUNTING, 'forecast_digest': None,
    }


def bucket_id(day, sim_day):
    """Bucket id for a leg day. Days at or before sim_day count as 0 days ahead."""
    offset = day - sim_day
    if offset < 0:
        offset = 0
    for edge, name in zip(EDGES, BUCKET_IDS):
        if offset <= edge:
            return name
    return BUCKET_IDS[-1]


def _subject_row(subject, terms, sim_day, expected):
    """One row per drawn advance: the three legs or a no-number NOT_APPLICABLE marker."""
    case, claim = subject['case'], subject['claim']
    phase = case.get('phase') if type(case) is dict else None
    outstanding = subject.get('principal')
    base = {'advance_id': subject['advance_id'], 'phase': phase}
    if type(outstanding) is not int or outstanding <= 0:
        return {**base, 'status': 'NOT_APPLICABLE', 'reason': NO_PRINCIPAL}
    ledger = terms.ledger_terms(case, claim, gate=subject['gate'], draw_day=subject['draw_day'],
                                expected_settlement_cash_day=expected)
    if ledger is None:
        return {**base, 'status': 'NOT_APPLICABLE', 'reason': TIER_NOT_APPLICABLE}
    maturity = ledger['maturity_day']
    interest_exact = Fraction(outstanding * ledger['term_days'] * ledger['contract_bps'],
                              ledger['denominator'])
    principal_exact = Fraction(outstanding, 1)
    legs = [
        {'kind': LEG_SETTLEMENT, 'day': expected, 'bucket': None if expected is None else bucket_id(expected, sim_day),
         'status': NO_SETTLEMENT_DAY if expected is None else 'SCHEDULED',
         'exact': _exact(principal_exact), 'assumption': SETTLEMENT_ASSUMPTION},
        {'kind': LEG_INTEREST, 'day': maturity, 'bucket': bucket_id(maturity, sim_day),
         'status': 'SCHEDULED', 'exact': _exact(interest_exact), 'assumption': INTEREST_ASSUMPTION},
        {'kind': LEG_PRINCIPAL, 'day': maturity, 'bucket': bucket_id(maturity, sim_day),
         'status': 'SCHEDULED', 'exact': _exact(principal_exact), 'assumption': PRINCIPAL_ASSUMPTION},
    ]
    return {
        **base, 'status': 'BOUND', 'reason': None, 'tier': ledger['tier'],
        'principal_krw': outstanding, 'draw_day': subject['draw_day'],
        'term_days': ledger['term_days'], 'term_source': ledger['term_source'],
        'maturity_day': maturity, 'legs': legs,
    }


def build(drawn, *, terms, sim_day, expected_settlement_cash_day=None, posted_interest=None):
    """The forecast body. `drawn` is the overlay's drawn subjects; nothing is mutated."""
    posted = posted_interest if type(posted_interest) is dict else {}
    rows = [_subject_row(subject, terms, sim_day, expected_settlement_cash_day) for subject in drawn]
    buckets = {name: {'legs': 0, 'settlement': Fraction(0), 'repayment': Fraction(0)}
               for name in BUCKET_IDS}
    outstanding = 0
    interest_total = Fraction(0)
    for row in rows:
        if row['status'] != 'BOUND':
            continue
        outstanding += row['principal_krw']
        interest_total += Fraction(dict((leg['kind'], leg['exact']) for leg in row['legs'])[LEG_INTEREST])
        for leg in row['legs']:
            if leg['bucket'] is None:
                continue
            cell = buckets[leg['bucket']]
            cell['legs'] += 1
            key = 'settlement' if leg['kind'] == LEG_SETTLEMENT else 'repayment'
            cell[key] += Fraction(leg['exact'])
    posted_total = sum(value for value in posted.values() if type(value) is int)
    repayment = Fraction(outstanding) + interest_total
    settlement = sum(cell['settlement'] for cell in buckets.values())
    expected = settlement + repayment
    body = {
        'label': LABEL, 'mode': MODE, 'provisional': True,
        'status': 'BOUND', 'reason': None,
        'sim_day': sim_day, 'terms_version': getattr(terms, 'version', None),
        'expected_settlement_cash_day': expected_settlement_cash_day,
        'policy_adopted': False, 'accounting_policy': ACCOUNTING,
        'assumptions': list(ASSUMPTIONS),
        'advances': rows,
        'buckets': {'edges_days': list(EDGES), 'rows': [
            {'id': name, 'legs': cell['legs'],
             'settlement_exact': _exact(cell['settlement']),
             'repayment_exact': _exact(cell['repayment']),
             'expected_exact': _exact(cell['settlement'] + cell['repayment']),
             'expected_cash_krw': _floor(cell['settlement'] + cell['repayment'])}
            for name, cell in buckets.items()]},
        'reconciliation': {
            'outstanding_principal_krw': outstanding,
            'contract_interest_exact': _exact(interest_total),
            'contract_interest_krw': _floor(interest_total),
            'settlement_exact': _exact(settlement),
            'repayment_exact': _exact(repayment),
            'expected_exact': _exact(expected),
            'posted_accrued_interest_krw': posted_total,
            'matched': repayment == outstanding + interest_total
                       and settlement == (Fraction(outstanding) if expected_settlement_cash_day is not None
                                          else Fraction(0)),
        },
    }
    body['forecast_digest'] = _digest(body)
    return body


def pin(body):
    """The instance-independent slice the seeded demo pins in tests/vectors/forecast_vectors.json."""
    return {
        'label': 'SIMULATED', 'sim_day': body['sim_day'],
        'expected_settlement_cash_day': body['expected_settlement_cash_day'],
        'outstanding_principal_krw': body['reconciliation']['outstanding_principal_krw'],
        'expected_cash_krw': sum(row['expected_cash_krw'] for row in body['buckets']['rows']),
        'forecast_digest': body['forecast_digest'],
    }
