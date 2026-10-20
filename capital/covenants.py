"""Read-only covenant watch folded from the F04 journal, overlay clock and terms note.

SIMULATED. This module reports desk watch flags only. It never enforces a covenant, blocks a
command, mutates the workspace, or applies a reserve or accounting policy.
"""
from __future__ import annotations

import hashlib
import json

from capital import margin, risk
from capital.terms import TERMS_NOT_BOUND

LABEL = 'SIMULATED covenant watch — read-only, not an enforcement gate'
MODE = 'SIMULATED_COVENANT_WATCH'
ACCOUNTING = 'SYNTHETIC_UNADOPTED'


def _digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def not_bound(terms_version, sim_day, reason=TERMS_NOT_BOUND):
    return {
        'label': LABEL, 'mode': MODE, 'provisional': True, 'status': 'NOT_BOUND', 'reason': reason,
        'sim_day': sim_day, 'terms_version': terms_version, 'policy_adopted': False,
        'accounting_policy': ACCOUNTING, 'enforced': False, 'covenant_digest': None,
    }


def _reason(code, severity, detail, **facts):
    return {'code': code, 'severity': severity, 'detail': detail, **facts}


def _cap_reasons(row, risk_body):
    if row['outstanding_krw'] <= 0:
        return []
    section = risk_body['concentration']['caps']
    if section['status'] != 'BOUND':
        return []
    holders = {item['role']: item for item in risk_body['concentration']['beneficiaries']}
    holder = holders.get(row['beneficiary_role'])
    reasons = []
    for cap in section['rows']:
        name = cap['cap'].removesuffix('_cap_krw')
        applies = (name == 'portfolio' or name == 'single_advance'
                   or (name == 'beneficiary_aggregate' and holder is not None))
        used = row['amount'] if name == 'single_advance' else (
            holder['outstanding_krw'] if name == 'beneficiary_aggregate' and holder is not None
            else cap['used_krw'])
        breached = applies and risk._nonneg_int(used) and used > cap['cap_krw']
        if breached:
            reasons.append(_reason(
                'U4_CAP_BREACHED', 'BREACH',
                f"U4 {name} cap breached: used_krw={used}, cap_krw={cap['cap_krw']}",
                cap=name, cap_krw=cap['cap_krw'], used_krw=used,
                utilization_permille=used * risk.PERMILLE // cap['cap_krw']))
    return reasons


def _margin_reasons(row, margin_row, proposals, sim_day):
    state = margin_row.get('state')
    if state == margin.CALLED:
        deadline = margin_row['cure_deadline']
        if sim_day > deadline:
            return [_reason('CURE_DEADLINE_PASSED', 'BREACH',
                            f'margin cure deadline passed: cure_deadline={deadline}', cure_deadline=deadline)]
        return [_reason('MARGIN_CALL_ACTIVE', 'WATCH',
                        f'active margin call: cure_deadline={deadline}', cure_deadline=deadline)]
    if state == 'BREACH_AWAITING_TICK':
        return [_reason('MARGIN_BREACH_PENDING', 'WATCH', 'margin breach awaits an overlay clock tick')]
    if state == margin.ACCELERATED:
        found = next((item for item in proposals if item.get('advance_id') == row['advance_id']), None)
        if found is not None:
            return [_reason('DEFAULT_ELIGIBLE', 'BREACH',
                            f"default-eligible proposal: default_eligible_day={found['default_eligible_day']}",
                            default_eligible_day=found['default_eligible_day'])]
        day = margin_row['default_eligible_day']
        return [_reason('MARGIN_ACCELERATED', 'BREACH',
                        f'margin acceleration recorded: default_eligible_day={day}', default_eligible_day=day)]
    return []


def build(drawn, margin_rows, margin_block, risk_body, *, terms, sim_day):
    """Build a deterministic watch projection without mutating any input."""
    rows = risk.advance_rows(drawn, terms, sim_day)
    reserve_bps = {item['bucket']: item['bps'] for item in risk_body['reserve'].get('rows', [])}
    advances = []
    for row in rows:
        reasons = []
        remaining = row['maturity_day'] - sim_day
        if row['outstanding_krw'] > 0 and remaining < 0:
            reasons.append(_reason('PAST_MATURITY', 'BREACH',
                                   f"advance is past maturity by {-remaining} days", days_past_maturity=-remaining))
        elif row['outstanding_krw'] > 0 and remaining <= risk.EDGES[0]:
            reasons.append(_reason('MATURITY_WINDOW', 'WATCH',
                                   f'advance matures in {remaining} days', days_to_maturity=remaining,
                                   window_days=risk.EDGES[0]))
        reasons.extend(_margin_reasons(row, margin_rows.get(row['advance_id'], {}),
                                       margin_block.get('proposals', []), sim_day))
        reasons.extend(_cap_reasons(row, risk_body))
        if row['reserve_class'] in ('PAST_DUE_ANY_TIER', 'DEFAULTED'):
            bps = reserve_bps.get(row['reserve_class'])
            reasons.append(_reason('RESERVE_CLASS_ESCALATED', 'BREACH',
                                   f"reserve class escalated: {row['reserve_class']}, provision_bps={bps}",
                                   reserve_class=row['reserve_class'], provision_bps=bps))
        if row['phase'] == 'DEFAULTED':
            reasons.append(_reason('DEFAULTED', 'BREACH', 'F04 advance phase is DEFAULTED'))
        status = 'BREACH' if any(item['severity'] == 'BREACH' for item in reasons) else (
            'WATCH' if reasons else 'CLEAR')
        mrow = margin_rows.get(row['advance_id']) or margin.unbound_row(row['advance_id'])
        advances.append({
            'advance_id': row['advance_id'], 'phase': row['phase'], 'status': status,
            'reasons': reasons, 'outstanding_krw': row['outstanding_krw'],
            'maturity_day': row['maturity_day'], 'days_to_maturity': max(0, remaining),
            'days_past_maturity': max(0, -remaining),
            'margin': {key: mrow.get(key) for key in ('state', 'cure_deadline', 'effective_maturity_day',
                                                      'default_eligible_day')},
            'reserve_class': row['reserve_class'], 'provision_bps': reserve_bps.get(row['reserve_class']),
            'applied': False, 'enforced': False,
        })
    total = sum(row['outstanding_krw'] for row in advances)
    flagged = sum(row['outstanding_krw'] for row in advances if row['status'] != 'CLEAR')
    caps = risk_body['concentration']['caps']
    reserve = risk_body['reserve']
    body = {
        'label': LABEL, 'mode': MODE, 'provisional': True,
        'status': 'BOUND' if caps['status'] == reserve['status'] == 'BOUND' else 'PARTIAL', 'reason': None,
        'sim_day': sim_day, 'terms_version': getattr(terms, 'version', None), 'policy_adopted': False,
        'accounting_policy': ACCOUNTING, 'watch_window_days': risk.EDGES[0],
        'advances': advances, 'watch_list': [row for row in advances if row['status'] != 'CLEAR'],
        'totals': {'advances': len(advances), 'clear': sum(row['status'] == 'CLEAR' for row in advances),
                   'watch': sum(row['status'] == 'WATCH' for row in advances),
                   'breach': sum(row['status'] == 'BREACH' for row in advances),
                   'outstanding_krw': total, 'flagged_outstanding_krw': flagged},
        'caps': caps,
        'reserve': {'status': reserve['status'], 'requirement_krw': reserve['requirement_krw'],
                    'funding_source': 'NOT_BOUND', 'coverage': 'NOT_BOUND',
                    'coverage_reason': 'RESERVE_POOL_NOT_BOUND', 'applied': False},
        'reconciliation': {'total_krw': total, 'risk_total_krw': risk_body['totals']['outstanding_krw'],
                           'matched': total == risk_body['totals']['outstanding_krw']},
        'enforced': False,
    }
    body['covenant_digest'] = _digest(body)
    return body
