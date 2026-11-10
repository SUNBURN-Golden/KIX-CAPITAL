"""SIMULATED offline observations between two explicitly supplied snapshots.

No collection, import, persistence, payment inference or ownership attestation.
Only captured workspace.json bytes are audited and restored; local policies and
fixtures describe comparison-time inputs, not authenticated historical policy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from capital import audit, covenants, margin, overlay, risk
from capital.evidence import offline_service
from capital.portfolio_snapshot import FrozenInputs, digest
from capital.producer import FixtureViews, PinnedFsmProducer
from capital.projection import SimulationProjection
from capital.protocol import CreditMachine
from capital.store import FILE_NAME, canonical_bytes
from capital.terms import BPS_SCALE, DecisionNoteTermsPolicy
from capital.verify import loads

FORMAT = 'KIX_CAPITAL_PORTFOLIO_COMPARISON_V1'
REQUIRED_TERMS = ('interest_rate', 'term', 'default_loss_treatment',
                  'reserve', 'additional_margin', 'underwriting_depth')
WATCH_STATUSES = ('CLEAR', 'WATCH', 'BREACH')


def _check(checks, name, side, ok, reason, entries=()):
    checks.append({'id': name, 'side': side,
                   'status': 'NOT_CHECKED' if ok is None else ('MATCHED' if ok else 'MISMATCH'),
                   'reason': reason if ok is False else None, 'entries': list(entries)})


def _capture(directory, side, checks):
    """Read once, then audit, hash and restore exactly the captured bytes."""
    try:
        path = Path(directory) / FILE_NAME
        if not path.is_file():
            raise OSError('workspace file absent or nonregular')
        raw = path.read_bytes()
    except (OSError, TypeError, ValueError):
        raw = None
    report = audit.audit_workspace_bytes(raw, workspace=str(directory))
    info = dict.fromkeys(('payload_sha256', 'state_digest', 'overlay_state_digest', 'sim_day',
                          'fixtures_digest', 'policy_inputs_digest', 'inputs_digest',
                          'risk_digest', 'covenant_digest'))
    info.update(workspace_sha256=None if raw is None else hashlib.sha256(raw).hexdigest(), audit=report)
    info['payload_sha256'] = report['payload_sha256']
    _check(checks, 'audit', side, report['ok'], 'WORKSPACE_AUDIT_FAILED')
    if not report['ok']:
        return info, None
    service = offline_service(loads(raw))
    try:
        frozen = FrozenInputs.capture(service.producer.snapshot_inputs(), service.receipts,
                                      service.case_fixtures, service.overlay_entries,
                                      service.terms, service.overlay_bounds)
    finally:
        service.observability.close()
    return info, frozen


def _prepare(frozen, info, side, checks):
    """Detach inputs before calculations; do not require forecast/fees readiness."""
    if frozen is None:
        for name in ('policy', 'draw_gates', 'terms_binding', 'margin_terms', 'views'):
            _check(checks, name, side, None, None)
        return None
    data = frozen.detached()
    captured, policy = data['producer'], data['policy']
    state = json.loads(captured['canonical_state'])
    journal, entries, fixtures = state['journal'], data['overlay_entries'], captured['fixtures']
    folded = overlay.fold(entries)
    terms = DecisionNoteTermsPolicy.__new__(DecisionNoteTermsPolicy)
    terms.items, terms.version = json.loads(data['policy_items_json']), policy['version']
    terms.top, terms.reason = policy['top'], policy['reason']
    info.update(state_digest=captured['state_digest'], overlay_state_digest=overlay.state_digest(folded),
                sim_day=folded['sim_day'], fixtures_digest=digest(fixtures['rows']),
                policy_inputs_digest=digest({'version': 1, **policy}))
    missing = [name for name in REQUIRED_TERMS if name not in terms.items]
    unusable = [name for name in REQUIRED_TERMS if name in terms.items and not terms._ready(name)]
    bounds = policy['bounds']
    bounds_ok = (type(bounds) is dict and all(type(bounds.get(key)) is int and bounds[key] > 0
                 for key in (*overlay.BOUND_NAMES, 'max_step_days')))
    policy_ok = not (missing or unusable) and bounds_ok and risk.usable(terms)
    # Separate ordered entries retain every missing/unusable policy name.
    problems = ([{'name': name, 'reason': 'REQUIRED_POLICY_ENTRY_MISSING'} for name in missing]
                + [{'name': name, 'reason': 'REQUIRED_POLICY_ENTRY_UNUSABLE'} for name in unusable])
    _check(checks, 'policy', side, policy_ok,
           problems[0]['reason'] if problems else 'POLICY_INPUTS_UNUSABLE', problems)
    gates = {}
    bad_gates = []
    for row in journal:
        if row['op'] != 'draw':
            continue
        receipt = data['receipts'].get(row['idempotency_key'], {}).get('receipt', {})
        # The offline audit validates receipt identity and amounts, but a draw's
        # nested result may still be absent or malformed. Treat that as missing
        # comparison evidence rather than raising while extracting the gate.
        result = receipt.get('result')
        credit = result.get('credit') if type(result) is dict else None
        gate = credit.get('settlement_gate') if type(credit) is dict else None
        if receipt.get('outcome') != 'ACCEPTED' or type(gate) is not str or not gate:
            bad_gates.append(row['advance_id'])
        else:
            gates[row['advance_id']] = gate
    _check(checks, 'draw_gates', side, not bad_gates, 'DRAW_RECEIPT_GATE_MISSING', bad_gates)
    cut = {key: info[key] for key in ('state_digest', 'overlay_state_digest', 'sim_day',
                                     'fixtures_digest', 'policy_inputs_digest')}
    # Same input digest recipe as portfolio_snapshot.compose.
    info['inputs_digest'] = digest({'version': 1, 'cut': {'kind': 'LOCAL_DIAGNOSTIC', **cut},
        'fixtures': fixtures, 'case_fixtures': data['case_fixtures'], 'draw_gates': gates,
        'overlay_entries': entries, 'policy_items_json': data['policy_items_json']})
    binding = folded['terms_binding']
    # Like the overlay service, both BOUND and PARTIAL allow usable ledger
    # terms. Unrelated entries (e.g. fees) must not become comparison gates.
    binding_ok = (binding is None or (binding['terms_version'] == terms.version
                                     and binding['status'] in ('BOUND', 'PARTIAL')
                                     and terms.top in ('BOUND', 'PARTIAL')))
    _check(checks, 'terms_binding', side, binding_ok, 'TERMS_BINDING_INCOMPATIBLE')
    prepared = {'journal': journal, 'entries': entries, 'fixtures': fixtures,
                'mapping': data['case_fixtures'], 'gates': gates, 'info': info}
    if not (policy_ok and not bad_gates and binding_ok):
        for name in ('margin_terms', 'views'):
            _check(checks, name, side, None, None)
        return prepared
    views = FixtureViews.__new__(FixtureViews)
    views.rows, views.profiles = fixtures['rows'], fixtures['profiles']
    views.beneficiaries, views.projection_ids = fixtures['beneficiaries'], frozenset(fixtures['projection_ids'])
    scratch = PinnedFsmProducer(views, CreditMachine.restore(journal, views))
    if scratch.canonical_state() != captured['canonical_state']:
        raise ValueError('CAPTURE_STATE_MISMATCH')
    drawn = []
    for index, row in enumerate(journal):
        if row['op'] == 'draw':
            key = row['advance_id']
            case = scratch.machine.view(key)
            drawn.append({'advance_id': key, 'case': case,
                          'claim': views.view(data['case_fixtures'][key])['claim'], 'gate': gates[key],
                          'draw_day': overlay.draw_day_for(entries, index), 'principal': case['outstanding_exposure']})
    drawn.sort(key=lambda row: row['advance_id'])
    margins, bad_margins = [], []
    for subject in drawn:
        args = (subject['case'], subject['claim'])
        kwargs = {'gate': subject['gate'], 'draw_day': subject['draw_day']}
        value = terms.margin_terms(*args, **kwargs, refund_after_draw=False)
        if value is not None:
            margins.append({**subject, 'margin': value})
        elif terms.ledger_terms(*args, **kwargs) is not None:
            bad_margins.append(subject['advance_id'])
    _check(checks, 'margin_terms', side, not bad_margins, 'APPLICABLE_MARGIN_TERMS_UNUSABLE', bad_margins)
    if bad_margins:
        _check(checks, 'views', side, None, None)
        return prepared
    projected = SimulationProjection().project(journal, [views.view(k) for k in sorted(views.projection_ids)])
    outstanding = sum(row['outstanding'] for row in projected['read_model']['advances'])
    risk_body = risk.build(drawn, margins, terms=terms, sim_day=folded['sim_day'],
                           projection_outstanding_krw=outstanding)
    margin_rows = margin.row_blocks(folded, margins, mutable=False)
    block = margin.status_block(folded, margin_rows, mutable=False, bound=True,
                                cure_terms=margins[0]['margin'] if margins else None)
    covenant_body = covenants.build(drawn, margin_rows, block, risk_body, terms=terms, sim_day=folded['sim_day'])
    ok = (risk_body['status'] == covenant_body['status'] == 'BOUND'
          and risk_body['reconciliation']['matched'] and covenant_body['reconciliation']['matched']
          and risk_body['reserve']['complete'])
    _check(checks, 'views', side, ok, 'VIEW_COVERAGE_OR_RECONCILIATION_FAILED')
    info.update(risk_digest=risk_body['risk_digest'], covenant_digest=covenant_body['covenant_digest'])
    weights = terms.items['reserve']['value']['provision_bps_of_outstanding']
    watches = {row['advance_id']: row for row in covenant_body['advances']}
    rows = {}
    for row in risk.advance_rows(drawn, terms, folded['sim_day']):
        watch = watches[row['advance_id']]
        weight = weights.get(row['reserve_class'])
        rows[row['advance_id']] = {**row,
            'reserve_requirement_krw': None if weight is None else row['outstanding_krw'] * weight // BPS_SCALE,
            'covenant_status': watch['status'], 'reasons': watch['reasons'], 'margin': watch['margin'],
            'days_to_maturity': watch['days_to_maturity'], 'days_past_maturity': watch['days_past_maturity']}
    prepared.update(rows=rows, risk=risk_body, covenants=covenant_body)
    return prepared


def _compatible(before, after, checks):
    ready = before is not None and after is not None
    comparisons = (
        ('fixtures', 'FIXTURE_INPUTS_MISMATCH', lambda a, b: a['fixtures'] == b['fixtures']),
        ('policy_inputs', 'POLICY_INPUTS_MISMATCH', lambda a, b:
            a['info']['policy_inputs_digest'] == b['info']['policy_inputs_digest']),
        ('sim_day', 'SIM_DAY_DECREASED', lambda a, b: a['info']['sim_day'] <= b['info']['sim_day']),
        ('f04_prefix', 'F04_JOURNAL_NOT_PREFIX', lambda a, b:
            canonical_bytes(a['journal']) == canonical_bytes(b['journal'][:len(a['journal'])])),
        ('overlay_prefix', 'OVERLAY_JOURNAL_NOT_PREFIX', lambda a, b:
            canonical_bytes(a['entries']) == canonical_bytes(b['entries'][:len(a['entries'])])),
        ('overlay_append_cut', 'RETROACTIVE_OVERLAY_ENTRY', lambda a, b: all(
            row['after_journal_index'] >= len(a['journal']) for row in b['entries'][len(a['entries']):])),
        ('advance_mappings', 'ADVANCE_MAPPING_CHANGED', lambda a, b: all(
            b['mapping'].get(key) == value for key, value in a['mapping'].items())),
        ('existing_draw_gates', 'DRAW_RECEIPT_GATE_CHANGED', lambda a, b: all(
            b['gates'].get(key) == value for key, value in a['gates'].items())),
    )
    results = {}
    for name, reason, predicate in comparisons:
        # A divergent overlay has no meaningful appended suffix to inspect.
        applicable = ready and (name != 'overlay_append_cut' or results.get('overlay_prefix') is True)
        ok = predicate(before, after) if applicable else None
        _check(checks, name, 'pair', ok, reason)
        results[name] = ok


def _metrics(rows):
    return {
        'outstanding_krw': sum(row['outstanding_krw'] for row in rows),
        'reserve_requirement_krw': sum(row['reserve_requirement_krw'] or 0 for row in rows),
        'maturity_bucket_exposure_krw': {key: sum(row['outstanding_krw'] for row in rows
            if row['maturity_bucket'] == key) for key in risk.MATURITY_IDS},
        'aging_exposure_krw': {key: sum(row['outstanding_krw'] for row in rows
            if row['aging'] == key) for key in risk.AGING_IDS},
        'watch_status_counts': {key: sum(row['covenant_status'] == key for row in rows) for key in WATCH_STATUSES},
    }


def _delta(before, after):
    return {key: _delta(value, after[key]) if type(value) is dict else after[key] - value
            for key, value in before.items()}


def _movement(before, after):
    return {'before': before, 'after': after, 'delta': _delta(before, after)}


def _watch_change(before, after):
    left = before is not None and before['covenant_status'] != 'CLEAR'
    right = after is not None and after['covenant_status'] != 'CLEAR'
    return {'entered': right and not left, 'exited': left and not right,
            'reasons_changed': (before or {}).get('reasons', []) != (after or {}).get('reasons', [])}


def _changes(before, after):
    a, b = before['rows'], after['rows']
    advances = []
    for key in sorted(a.keys() | b.keys()):
        left, right = a.get(key), b.get(key)
        advances.append({'advance_id': key, 'presence': 'BOTH' if left and right else ('AFTER_ONLY' if right else 'BEFORE_ONLY'),
                         'before': left, 'after': right, 'watch_change': _watch_change(left, right),
                         'delta': _delta(_metrics([left] if left else []), _metrics([right] if right else []))})
    roles = sorted({row['beneficiary_role'] for row in [*a.values(), *b.values()]})
    beneficiaries = []
    for role in roles:
        left = [row for row in a.values() if row['beneficiary_role'] == role]
        right = [row for row in b.values() if row['beneficiary_role'] == role]
        beneficiaries.append({'beneficiary_role': role, **_movement(_metrics(left), _metrics(right)),
                              'watch_changes': [{'advance_id': row['advance_id'], **row['watch_change']}
                                  for row in advances if (row['after'] or row['before'])['beneficiary_role'] == role]})
    totals = _movement(_metrics(list(a.values())), _metrics(list(b.values())))
    checks = []
    for side, endpoint in (('before', before), ('after', after)):
        metrics = totals[side]
        view = endpoint['risk']
        checks.extend((metrics['outstanding_krw'] == view['totals']['outstanding_krw'],
                       metrics['reserve_requirement_krw'] == view['reserve']['requirement_krw'],
                       metrics['maturity_bucket_exposure_krw'] == {r['id']: r['outstanding_krw'] for r in view['maturity_buckets']['rows']},
                       metrics['aging_exposure_krw'] == {r['id']: r['outstanding_krw'] for r in view['overdue_aging']['rows']},
                       metrics['watch_status_counts'] == {s: endpoint['covenants']['totals'][s.lower()] for s in WATCH_STATUSES}))
    def sums_match(rows, expected):
        return all(sums_match([row[key] for row in rows], value) if type(value) is dict
                   else sum(row[key] for row in rows) == value for key, value in expected.items())
    checks.extend(sums_match([row['delta'] for row in rows], totals['delta']) for rows in (advances, beneficiaries))
    for side in ('before', 'after'):
        checks.append(sums_match([row[side] for row in beneficiaries], totals[side]))
    return {'advances': advances, 'beneficiaries': beneficiaries, 'totals': totals,
            'reconciliation': {'matched': all(checks), 'endpoint_views_matched': all(checks[:10]),
                               'additive_deltas_matched': all(checks[10:12]),
                               'beneficiary_endpoints_matched': all(checks[12:])}}


def compare_workspaces(before_dir, after_dir):
    """Compare audited explicit snapshots. Both audits are attempted on failure."""
    checks = []
    before_info, before_frozen = _capture(before_dir, 'before', checks)
    after_info, after_frozen = _capture(after_dir, 'after', checks)
    before = _prepare(before_frozen, before_info, 'before', checks)
    after = _prepare(after_frozen, after_info, 'after', checks)
    _compatible(before, after, checks)
    comparable = all(row['status'] == 'MATCHED' for row in checks)
    changes = _changes(before, after) if comparable else None
    if changes is not None:
        _check(checks, 'additive_reconciliation', 'pair', changes['reconciliation']['matched'], 'ADDITIVE_RECONCILIATION_FAILED')
        comparable = changes['reconciliation']['matched']
    return {'format': FORMAT, 'label': 'SIMULATED', 'status': 'COMPARABLE' if comparable else 'NON_COMPARABLE',
            'inputs': {'before': before_info, 'after': after_info}, 'comparability': {'checks': checks},
            'changes': changes if comparable else None,
            'historical_policy_provenance': 'NOT_BOUND', 'authentication': 'NOT_BOUND',
            'common_ownership': 'NOT_BOUND', 'actual_payments': 'NOT_BOUND',
            'interpretation': 'Observed differences only; no payment, causation or authenticated common ownership inference.',
            'funds_executed': False, 'workspace_mutated': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', required=True, help='explicit directory containing workspace.json')
    parser.add_argument('--after', required=True, help='explicit directory containing workspace.json')
    args = parser.parse_args(argv)
    report = compare_workspaces(args.before, args.after)
    sys.stdout.buffer.write(canonical_bytes(report) + b'\n')
    return 0 if report['status'] == 'COMPARABLE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
