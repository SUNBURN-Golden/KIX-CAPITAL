"""Read-only named what-if scenarios over the risk and covenant folds.

SIMULATED_WHATIF. A fixed catalog re-folds the same integer inputs GET /api/risk and
GET /api/risk/covenants consume under one stated assumption per scenario: an advance
default at the recorded sim_day, a fixed refund shock, a covenant breach projection
past the last recorded maturity, or one hypothetical draw over the tightest bound U4
concentration cap. Nothing here is a credit decision, a booked reserve, a margin
call, an enforcement gate or a journal entry. Every transform runs on deep copies
and nothing is planned, accrued or written.

All arithmetic is integer floor division. No float, no probability model, no
external data. The refund shock reuses the spec-pinned SHOCKS_BPS set; every rate,
cap, tier and reserve weight reaches the fold through the same decision-note reads
the live endpoints use.
"""
from __future__ import annotations

import copy
import hashlib
import json

from capital import covenants, margin, risk
from capital.terms import BPS_SCALE, TERMS_NOT_BOUND

LABEL = ('SIMULATED what-if scenario — read-only hypothetical re-fold of the risk and '
         'covenant folds, not a credit decision, not an enforcement, nothing is applied')
MODE = 'SIMULATED_WHATIF'
ACCOUNTING = 'SYNTHETIC_UNADOPTED'
INJECTED_ADVANCE = 'sim-whatif-cap'
_DEFAULTED = 'DEFAULTED'
_DRAWN = 'DRAWN'
_LIVE_MARGIN = (margin.CALLED, margin.ACCELERATED)

CATALOG = {
    'largest-advance-default': {
        'title': 'Largest open advance defaults at the recorded sim_day',
        'assumption': 'TARGET_PHASE_SET_TO_DEFAULTED',
    },
    'refund-shock': {
        'title': 'The largest pinned refund shock raises refund_face on every assessed DRAWN advance',
        'assumption': 'REFUND_FACE_RAISES_BY_MAX_PINNED_SHOCK_BPS_OF_ELIGIBLE',
    },
    'all-watch-breach': {
        'title': 'Every open advance ages one day past the last recorded maturity',
        'assumption': 'SIM_DAY_PROJECTED_PAST_LAST_MATURITY',
    },
    'concentration-cap-hit': {
        'title': 'One hypothetical draw pushes the tightest bound U4 cap over its bound',
        'assumption': 'HYPOTHETICAL_DRAW_OVER_TIGHTEST_CAP',
    },
}


def _digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def catalog():
    """The fixed named set. Static text only — no computed numbers."""
    return [{'scenario_id': name, 'title': row['title'], 'assumption': row['assumption'],
             'applied': False, 'enforced': False} for name, row in CATALOG.items()]


def _envelope(scenario_id, status, reason, sim_day, terms_version):
    body = {
        'label': LABEL, 'mode': MODE, 'provisional': True, 'status': status, 'reason': reason,
        'sim_day': sim_day, 'terms_version': terms_version, 'policy_adopted': False,
        'accounting_policy': ACCOUNTING, 'applied': False, 'enforced': False,
    }
    if scenario_id is not None:
        meta = CATALOG[scenario_id]
        body['scenario'] = {'scenario_id': scenario_id, 'title': meta['title'],
                            'assumption': meta['assumption']}
    return body


def index(usable, sim_day, terms_version):
    """The scenario catalog. Binding state is reported; the names are always served."""
    body = _envelope(None, 'BOUND' if usable else 'NOT_BOUND',
                     None if usable else TERMS_NOT_BOUND, sim_day, terms_version)
    body['scenarios'] = catalog()
    return body


def not_bound(scenario_id, terms_version, sim_day, reason=TERMS_NOT_BOUND):
    """A scenario id under a missing or unusable terms note: no numbers at all."""
    body = _envelope(scenario_id, 'NOT_BOUND', reason, sim_day, terms_version)
    body['evaluated'] = False
    body['whatif_digest'] = None
    return body


def _unevaluated(inputs, reason, detail=None):
    return {'evaluated': False, 'target': None, 'detail': detail or {},
            'delta': 0, 'fold_day': inputs['sim_day'], 'unevaluated_reason': reason}


def _largest_advance_default(inputs, _terms):
    candidates = [row for row in inputs['drawn']
                  if row['principal'] > 0 and row['case'].get('phase') != _DEFAULTED]
    if not candidates:
        return _unevaluated(inputs, 'NO_OPEN_NON_DEFAULTED_ADVANCE')
    chosen = min(candidates, key=lambda row: (-row['principal'], row['advance_id']))
    chosen['case']['phase'] = _DEFAULTED
    return {'evaluated': True, 'unevaluated_reason': None,
            'target': {'advance_id': chosen['advance_id'], 'outstanding_krw': chosen['principal']},
            'detail': {'rule': 'MAX_OPEN_OUTSTANDING_THEN_SMALLEST_ADVANCE_ID'},
            'delta': 0, 'fold_day': inputs['sim_day']}


def _refund_shock(inputs, _terms):
    """The largest spec-pinned shock of eligible face lands as refund_face on each subject."""
    shock = risk.SHOCKS_BPS[-1]
    shifted = []
    for subject in inputs['margin_subjects']:
        if subject['case'].get('phase') != _DRAWN or subject['principal'] <= 0:
            continue
        eligible = margin.eligible_face(subject['claim'], subject['margin']['payees'])
        if eligible is None:
            continue
        subject['claim']['refund_face'] += eligible * shock // BPS_SCALE
        shifted.append(subject)
    if not shifted:
        return _unevaluated(inputs, 'NO_ASSESSED_DRAWN_ADVANCE',
                            {'shock_bps': shock, 'shock_set': risk.SHOCK_SET})
    calls = 0
    for subject in shifted:
        measured = margin.measure(subject)
        if measured is None or not measured['breach']:
            continue
        row = inputs['margin_rows'].setdefault(
            subject['advance_id'], margin.unbound_row(subject['advance_id']))
        if row.get('state') in _LIVE_MARGIN:
            continue
        row.update(
            {key: measured[key] for key in ('eligible_face_krw', 'advance_rate_bps', 'base_krw',
                                            'outstanding_krw', 'headroom_krw')},
            checked=True, triggered=False, hypothetical=True, state=margin.CALLED,
            cure_deadline=inputs['sim_day'] + subject['margin']['cure_window_days'],
            effective_maturity_day=subject['margin']['maturity_day'],
            default_eligible_day=None)
        calls += 1
    return {'evaluated': True, 'unevaluated_reason': None,
            'target': {'scope': 'ASSESSED_DRAWN_ADVANCES', 'advances': len(shifted)},
            'detail': {'shock_bps': shock, 'shock_set': risk.SHOCK_SET,
                       'shifted_advances': len(shifted), 'hypothetical_calls': calls},
            'delta': 0, 'fold_day': inputs['sim_day']}


def _all_watch_breach(inputs, terms):
    rows = risk.advance_rows(inputs['drawn'], terms, inputs['sim_day'])
    maturities = [row['maturity_day'] for row in rows if row['outstanding_krw'] > 0]
    if not maturities:
        return _unevaluated(inputs, 'NO_OPEN_ADVANCE')
    projected = max(inputs['sim_day'], max(maturities) + 1)
    return {'evaluated': True, 'unevaluated_reason': None,
            'target': {'scope': 'ALL_OPEN_ADVANCES', 'advances': len(maturities)},
            'detail': {'projected_sim_day': projected},
            'delta': 0, 'fold_day': projected}


def _concentration_cap_hit(inputs, _terms):
    caps = inputs['baseline_risk']['concentration']['caps']
    if caps['status'] != 'BOUND':
        return _unevaluated(inputs, 'CAPS_NOT_BOUND')
    tightest = min(caps['rows'], key=lambda row: row['remaining_krw'])
    donors = [row for row in inputs['drawn'] if row['principal'] > 0]
    if not donors:
        return _unevaluated(inputs, 'NO_OPEN_ADVANCE')
    cap_name = tightest['cap'].removesuffix('_cap_krw')
    injection = (tightest['cap_krw'] + 1 if cap_name == 'single_advance'
                 else max(1, tightest['remaining_krw'] + 1))
    if cap_name == 'beneficiary_aggregate':
        holders = inputs['baseline_risk']['concentration']['beneficiaries']
        role = min(row['role'] for row in holders
                   if row['outstanding_krw'] == tightest['used_krw'])
        pool = [row for row in donors if row['case'].get('beneficiary_role') == role]
    else:
        pool = donors
    donor = min(pool, key=lambda row: (-row['principal'], row['advance_id']))
    inputs['drawn'].append({
        'advance_id': INJECTED_ADVANCE, 'gate': donor['gate'], 'draw_day': donor['draw_day'],
        'principal': injection,
        'case': {**donor['case'], 'phase': _DRAWN, 'amount': injection,
                 'outstanding_exposure': injection},
        'claim': copy.deepcopy(donor['claim']),
    })
    return {'evaluated': True, 'unevaluated_reason': None,
            'target': {'advance_id': INJECTED_ADVANCE, 'cap': cap_name,
                       'cap_krw': tightest['cap_krw'],
                       'injected_outstanding_krw': injection,
                       'beneficiary_role': donor['case'].get('beneficiary_role')},
            'detail': {'cap': cap_name, 'cap_krw': tightest['cap_krw'],
                       'injected_outstanding_krw': injection,
                       'donor_advance_id': donor['advance_id']},
            'delta': injection, 'fold_day': inputs['sim_day']}


_TRANSFORMS = {
    'largest-advance-default': _largest_advance_default,
    'refund-shock': _refund_shock,
    'all-watch-breach': _all_watch_breach,
    'concentration-cap-hit': _concentration_cap_hit,
}


def build(scenario_id, inputs, *, terms):
    """Re-fold the shared inputs under the scenario's stated assumption.

    `inputs` is the service's _watch_inputs snapshot plus `baseline_risk` and
    `baseline_cov`. Everything is deep-copied before a transform touches it, so the
    live book and the recorded margin rows are never mutated.
    """
    copied = copy.deepcopy(inputs)
    outcome = _TRANSFORMS[scenario_id](copied, terms)
    delta, fold_day = outcome['delta'], outcome['fold_day']
    risk_body = risk.build(
        copied['drawn'], copied['margin_subjects'], terms=terms, sim_day=fold_day,
        projection_outstanding_krw=copied['projection_outstanding_krw'] + delta)
    covenant_body = covenants.build(
        copied['drawn'], copied['margin_rows'], copied['margin_block'], risk_body,
        terms=terms, sim_day=fold_day)
    baseline_outstanding = copied['baseline_risk']['totals']['outstanding_krw']
    scenario_outstanding = risk_body['totals']['outstanding_krw']
    body = _envelope(scenario_id, risk_body['status'], None, copied['sim_day'],
                     risk_body['terms_version'])
    body.update({
        'evaluated': outcome['evaluated'],
        'unevaluated_reason': outcome['unevaluated_reason'],
        'target': outcome['target'],
        'assumption_detail': outcome['detail'],
        'risk': risk_body,
        'covenants': covenant_body,
        'reconciliation': {
            'baseline_risk_digest': copied['baseline_risk']['risk_digest'],
            'baseline_covenant_digest': copied['baseline_cov']['covenant_digest'],
            'baseline_outstanding_krw': baseline_outstanding,
            'assumption_delta_krw': delta,
            'scenario_outstanding_krw': scenario_outstanding,
            'matched': scenario_outstanding == baseline_outstanding + delta,
        },
    })
    body['whatif_digest'] = _digest(body)
    return body
