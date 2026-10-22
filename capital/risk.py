"""Read-only portfolio risk analytics over the journal, the overlay clock and the terms note.

SIMULATED. Every figure is a deterministic integer fold of drawn advances: exposure by tier,
maturity buckets, overdue aging, beneficiary concentration with U4 cap utilization, the loss
reserve requirement from the note's provision table, and a refund-shock stress. Nothing here
is a credit decision, a booked reserve, a margin call, an accounting policy or a journal
entry. The stress is hypothetical: it never writes a margin call to the overlay.

All arithmetic is integer floor division. No float, no probability model, no external data.
Rates, caps, tier ids and the provision table come from the decision note; only the maturity
bucket edges and the stress shocks below are fixed by the node spec.
"""
from __future__ import annotations

import hashlib
import json

from capital import margin
from capital.terms import BPS_SCALE, TERMS_NOT_BOUND

RISK_LABEL = 'SIMULATED portfolio risk analytics — read-only, not a credit decision, not an accounting policy'
RESERVE_LABEL = ('SIMULATED reserve requirement from the CAPITAL-TERMS-V1 provision table — '
                 'not an accounting policy, no reserve is booked')
STRESS_LABEL = 'SIMULATED refund-shock stress — hypothetical, no margin call is recorded'
MODE = 'SIMULATED_RISK_ANALYTICS'
ACCOUNTING = 'SYNTHETIC_UNADOPTED'

SHOCK_SET = 'FIXED_REFUND_SHOCK_BPS_OF_ELIGIBLE_FACE_V1'
SHOCKS_BPS = (500, 1000, 2500, 5000)
# Bucket edges in days. Maturity buckets and overdue aging use the same edges.
EDGES = (30, 60, 90)
MATURITY_IDS = ('0-30', '31-60', '61-90', '>90')
AGING_IDS = ('NOT_DUE', '1-30', '31-60', '61-90', '>90', 'DEFAULTED')
PERMILLE = 1000

TIER_NONE = 'NOT_APPLICABLE'
CAP_KEYS = (
    ('single_advance', 'single_advance_cap_krw'),
    ('beneficiary_aggregate', 'beneficiary_aggregate_cap_krw'),
    ('portfolio', 'portfolio_cap_krw'),
)
_DEFAULTED = 'DEFAULTED'
_PAST_DUE = 'PAST_DUE_ANY_TIER'
_DRAWN = 'DRAWN'
_NEEDED = ('interest_rate', 'term', 'default_loss_treatment')


def _digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def _nonneg_int(value):
    return type(value) is int and value >= 0


def _value(terms, name):
    items = getattr(terms, 'items', None)
    item = items.get(name) if type(items) is dict else None
    if type(item) is not dict or item.get('mark') != 'ADOPTED':
        return None
    return item['value']


def usable(terms):
    """True when the standard term, the tiers and the default treatment are all ADOPTED."""
    return (callable(getattr(terms, 'ledger_terms', None))
            and all(_value(terms, name) is not None for name in _NEEDED))


def not_bound(terms_version, sim_day, reason=TERMS_NOT_BOUND):
    return {
        'label': RISK_LABEL, 'mode': MODE, 'provisional': True, 'status': 'NOT_BOUND', 'reason': reason,
        'sim_day': sim_day, 'terms_version': terms_version, 'policy_adopted': False,
        'accounting_policy': ACCOUNTING, 'risk_digest': None,
    }


def maturity_bucket(remaining_days):
    """Bucket id for days left to maturity. Due-today and overdue exposure count as 0-30."""
    for edge, bucket in zip(EDGES, MATURITY_IDS):
        if remaining_days <= edge:
            return bucket
    return MATURITY_IDS[-1]


def aging_class(sim_day, maturity_day, phase):
    if phase == _DEFAULTED:
        return _DEFAULTED
    if sim_day <= maturity_day:
        return AGING_IDS[0]
    late = sim_day - maturity_day
    for edge, bucket in zip(EDGES, AGING_IDS[1:]):
        if late <= edge:
            return bucket
    return AGING_IDS[-2]


def advance_rows(drawn, terms, sim_day):
    """One fact row per drawn advance. Tier follows the draw receipt gate through the terms."""
    standard = _value(terms, 'term')['standard_term_days']
    weights = (_value(terms, 'reserve') or {}).get('provision_bps_of_outstanding')
    rows = []
    for subject in drawn:
        case, outstanding = subject['case'], subject['principal']
        ledger = terms.ledger_terms(case, subject['claim'], gate=subject['gate'], draw_day=subject['draw_day'])
        tier = TIER_NONE if ledger is None else ledger['tier']
        maturity = subject['draw_day'] + standard
        phase = case['phase']
        past_due = outstanding > 0 and phase != _DEFAULTED and sim_day > maturity
        reserve_class = None
        if type(weights) is dict:
            if phase == _DEFAULTED:
                reserve_class = _DEFAULTED
            elif past_due:
                reserve_class = _PAST_DUE
            else:
                reserve_class = next((key for key in weights if key.split('_', 1)[0] == tier), None)
        rows.append({
            'advance_id': subject['advance_id'], 'phase': phase, 'tier': tier,
            'outstanding_krw': outstanding, 'amount': case.get('amount'),
            'beneficiary_role': case.get('beneficiary_role'), 'draw_day': subject['draw_day'],
            'maturity_day': maturity, 'reserve_class': reserve_class,
            'maturity_bucket': maturity_bucket(max(0, maturity - sim_day)),
            'aging': aging_class(sim_day, maturity, phase),
        })
    return rows


def _tally(rows, key, ids):
    out = {name: {'advances': 0, 'outstanding_krw': 0} for name in ids}
    for row in rows:
        if row['outstanding_krw'] > 0:
            out[row[key]]['advances'] += 1
        out[row[key]]['outstanding_krw'] += row['outstanding_krw']
    return out


def _share(part, total):
    return None if total == 0 else part * PERMILLE // total


def _tiers(terms, rows, total):
    interest = _value(terms, 'interest_rate')
    ids = sorted({tier['id'].split('_', 1)[0] for tier in interest['tiers']}) + [TIER_NONE]
    tally = _tally(rows, 'tier', ids)
    return [{'tier': name, 'advances': tally[name]['advances'], 'outstanding_krw': tally[name]['outstanding_krw'],
             'share_permille': _share(tally[name]['outstanding_krw'], total)} for name in ids]


def _concentration(terms, rows, total):
    groups = {}
    for row in rows:
        if row['outstanding_krw'] > 0:
            role = row['beneficiary_role']
            groups[role] = groups.get(role, 0) + row['outstanding_krw']
    hhi = None if total == 0 else sum(value * value for value in groups.values()) * PERMILLE // (total * total)
    holders = [{'role': role, 'outstanding_krw': groups[role], 'share_permille': _share(groups[role], total)}
               for role in sorted(groups)]
    depth = _value(terms, 'underwriting_depth')
    caps = None if depth is None else {name: depth.get(key) for name, key in CAP_KEYS}
    section = {'hhi_permille': hhi, 'beneficiaries': holders}
    if caps is None or any(type(cap) is not int or cap < 1 for cap in caps.values()):
        section['caps'] = {'status': 'NOT_BOUND', 'reason': TERMS_NOT_BOUND, 'rows': []}
        return section
    amounts = [row['amount'] for row in rows if row['outstanding_krw'] > 0 and _nonneg_int(row['amount'])]
    used = {'single_advance': max(amounts, default=0), 'beneficiary_aggregate': max(groups.values(), default=0),
            'portfolio': total}
    section['caps'] = {'status': 'BOUND', 'reason': None, 'rows': [
        {'cap': key, 'cap_krw': caps[name], 'used_krw': used[name],
         'utilization_permille': used[name] * PERMILLE // caps[name],
         'remaining_krw': caps[name] - used[name], 'breached': used[name] > caps[name]}
        for name, key in CAP_KEYS]}
    return section


def _reserve(terms, rows):
    value = _value(terms, 'reserve')
    weights = None if value is None else value.get('provision_bps_of_outstanding')
    if type(weights) is not dict:
        return {'status': 'NOT_BOUND', 'reason': TERMS_NOT_BOUND, 'label': RESERVE_LABEL, 'rows': [],
                'requirement_krw': None, 'unrated_outstanding_krw': None, 'complete': False, 'applied': False}
    classes = {name: {'outstanding_krw': 0, 'provision_krw': 0} for name in weights}
    unrated = 0
    for row in rows:
        name = row['reserve_class']
        if name is None or not _nonneg_int(weights.get(name)):
            unrated += row['outstanding_krw']
            continue
        classes[name]['outstanding_krw'] += row['outstanding_krw']
        classes[name]['provision_krw'] += row['outstanding_krw'] * weights[name] // BPS_SCALE
    return {
        'status': 'BOUND', 'reason': None, 'label': RESERVE_LABEL,
        'rows': [{'bucket': name, 'bps': weights[name], **classes[name]} for name in weights],
        'requirement_krw': sum(item['provision_krw'] for item in classes.values()),
        'unrated_outstanding_krw': unrated, 'complete': unrated == 0, 'applied': False,
    }


def _stress_row(shock, margin_subjects):
    called = shortfall = called_outstanding = 0
    shocked_total = 0
    for subject in margin_subjects:
        eligible = subject['eligible']
        shocked = eligible - eligible * shock // BPS_SCALE
        base = shocked * subject['rate'] // BPS_SCALE
        shocked_total += shocked
        if subject['outstanding'] > base:
            called += 1
            called_outstanding += subject['outstanding']
            shortfall += subject['outstanding'] - base
    return {'shock_bps': shock, 'shocked_eligible_face_krw': shocked_total, 'margin_call_count': called,
            'called_outstanding_krw': called_outstanding, 'shortfall_krw': shortfall}


def _stress(margin_subjects, drawn_open):
    """Hypothetical shocks over DRAWN advances that carry margin terms; the rest are counted, not guessed."""
    usable_subjects = []
    for subject in margin_subjects:
        if subject['case']['phase'] != _DRAWN or subject['principal'] <= 0:
            continue
        eligible = margin.eligible_face(subject['claim'], subject['margin']['payees'])
        if eligible is not None:
            usable_subjects.append({'eligible': eligible, 'rate': subject['margin']['advance_rate_bps'],
                                    'outstanding': subject['principal']})
    baseline = _stress_row(0, usable_subjects)
    rows = [_stress_row(shock, usable_subjects) for shock in SHOCKS_BPS]
    counts = [row['margin_call_count'] for row in rows]
    return {
        'status': 'BOUND', 'reason': None, 'label': STRESS_LABEL, 'shock_set': SHOCK_SET,
        'shocks_bps': list(SHOCKS_BPS), 'baseline': baseline, 'rows': rows,
        'coverage': {'drawn_open_advances': drawn_open, 'assessed': len(usable_subjects),
                     'unassessed': drawn_open - len(usable_subjects)},
        'monotone': all(left <= right for left, right in zip([baseline['margin_call_count']] + counts, counts)),
        'applied': False,
    }


def build(drawn, margin_subjects, *, terms, sim_day, projection_outstanding_krw):
    """The risk body. `drawn` and `margin_subjects` are the overlay's subjects; nothing is mutated."""
    rows = advance_rows(drawn, terms, sim_day)
    total = sum(row['outstanding_krw'] for row in rows)
    open_rows = [row for row in rows if row['outstanding_krw'] > 0]
    tiers = _tiers(terms, rows, total)
    maturity = _tally(rows, 'maturity_bucket', MATURITY_IDS)
    aging = _tally(rows, 'aging', AGING_IDS)
    concentration = _concentration(terms, rows, total)
    reserve = _reserve(terms, rows)
    drawn_open = sum(1 for row in open_rows if row['phase'] == _DRAWN)
    stress = _stress(margin_subjects, drawn_open)
    sums = {
        'tier_sum': sum(item['outstanding_krw'] for item in tiers),
        'bucket_sum': sum(item['outstanding_krw'] for item in maturity.values()),
        'aging_sum': sum(item['outstanding_krw'] for item in aging.values()),
    }
    sections = (concentration['caps']['status'], reserve['status'], stress['status'])
    body = {
        'label': RISK_LABEL, 'mode': MODE, 'provisional': True,
        'status': 'BOUND' if all(item == 'BOUND' for item in sections) else 'PARTIAL', 'reason': None,
        'sim_day': sim_day, 'terms_version': getattr(terms, 'version', None),
        'policy_adopted': False, 'accounting_policy': ACCOUNTING,
        'totals': {'advances_drawn': len(rows), 'advances_open': len(open_rows), 'outstanding_krw': total},
        'by_tier': tiers,
        'maturity_buckets': {'edges_days': list(EDGES), 'rows': [
            {'id': name, **maturity[name]} for name in MATURITY_IDS]},
        'overdue_aging': {'edges_days': list(EDGES), 'rows': [{'id': name, **aging[name]} for name in AGING_IDS]},
        'concentration': concentration,
        'reserve': reserve,
        'stress': stress,
        'reconciliation': {
            'total_krw': total, **sums, 'projection_outstanding_krw': projection_outstanding_krw,
            'matched': all(value == total for value in sums.values()) and total == projection_outstanding_krw,
        },
    }
    body['risk_digest'] = _digest(body)
    return body


def pin(body):
    """The instance-independent slice the seeded demo pins in tests/golden/demo.json."""
    return {
        'label': 'SIMULATED', 'sim_day': body['sim_day'], 'outstanding_krw': body['totals']['outstanding_krw'],
        'reserve_requirement_krw': body['reserve']['requirement_krw'],
        'hhi_permille': body['concentration']['hhi_permille'], 'risk_digest': body['risk_digest'],
    }
