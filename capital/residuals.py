"""Offline SIMULATED residual register over one audited workspace capture.

This reader composes existing folds; it never saves, releases cash, collects,
waives, reclassifies statements or establishes legal/accounting recognition.
Amounts are separate category metrics, with no grand total. See INTEGRATION.md
for coverage and the existing schemas retained verbatim in fold_values.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import sys
from pathlib import Path

from capital import audit, evidence, overlay, recovery, slices, store
from capital.verify import loads

FORMAT = 'KIX_CAPITAL_RESIDUAL_OBLIGATIONS_V1'
METRICS = {
    'closed_unpaid_interest': ('interest_due_krw', 'default_interest_due_krw'),
    'unapplied_cash': ('unapplied_cash_krw',),
    'defaulted_unwritten': ('principal_krw', 'interest_krw', 'default_interest_krw', 'claim_krw'),
    'post_writeoff_residual_claims': ('residual_claim_krw',),
    'impaired_slice_residuals': ('slice_face_krw', 'recourse_received_krw', 'served_krw',
                                'outstanding_krw', 'eligible_line_krw', 'shortfall_krw'),
}
POPULATIONS = {
    'closed_unpaid_interest': 'All CLOSED advances',
    'unapplied_cash': 'All advances with a recorded F04 draw',
    'defaulted_unwritten': 'DEFAULTED advances without a folded write-off',
    'post_writeoff_residual_claims': 'Advances with a folded write-off',
    'impaired_slice_residuals': 'IMPAIRED claim slice registry rows; last recorded observation only',
}
INTERPRETATION = (
    'SIMULATED recorded obligations only. Terminal FSM status does not establish '
    'extinguishment. COMPLETE means the declared recorded population was audited '
    'and reconciled, not complete settlement history or authenticity. Categories '
    'and metrics are independent: no grand total, F04 exposure addition, cash '
    'netting, or addition of slice shortfall to outstanding. Sub-won remainders '
    'are excluded from totals. Later settlement evidence, waiver, cash release, '
    'slice write-off, collection, legal collectability and accounting recognition '
    'are NOT_BOUND. No statement reclassification.'
)


def _unique(entries):
    """First occurrences, matching the audited overlay fold's deduplication."""
    seen = set()
    for index, entry in enumerate(entries):
        if entry['overlay_id'] not in seen:
            seen.add(entry['overlay_id'])
            yield index, entry


def _reference(journal, index, entry):
    return {'journal': journal, 'index': index,
            'entry_id': entry['idempotency_key'] if journal == 'F04' else entry['overlay_id'],
            'kind': entry['op'] if journal == 'F04' else entry['kind'],
            'after_journal_index': entry.get('after_journal_index'),
            'sim_day': entry.get('sim_day') if journal == 'OVERLAY' else None}


def _row(identity, status, category, *, basis='RECORDED_FOLD'):
    return {**{key: identity.get(key) for key in ('advance_id', 'slice_id', 'claim_id',
                                               'beneficiary_role', 'payee_label', 'holder_role')},
            'lifecycle_status': status, 'evidence_status': 'BOUND', 'reasons': [], 'basis': basis,
            'amounts': dict.fromkeys(METRICS[category]),
            'fold_values': dict.fromkeys(('accrual', 'repayment', 'recovery', 'position',
                                         'slice', 'derived', 'observation')),
            'remainders': {'contract_subwon': None, 'default_subwon': None}, 'references': []}


def _check(check_id, matched, reason=None):
    return {'id': check_id, 'status': ('NOT_CHECKED' if matched is None else
                                     'MATCHED' if matched else 'MISMATCH'), 'reason': reason}


def _section(category, rows, expected):
    """Reconcile each metric to independent entry arithmetic, including zeros."""
    rows.sort(key=lambda r: (r['advance_id'] or '', r['slice_id'] or '', r['claim_id'] or '',
                             r['payee_label'] or ''))
    checks, totals = [], {}
    for metric in METRICS[category]:
        values = [r['amounts'][metric] for r in rows]
        unknown = sum(v is None for v in values)
        known = sum(v for v in values if v is not None)
        totals[metric] = {'known_subtotal_krw': known,
                          'total_krw': None if unknown else known, 'unknown_rows': unknown}
        # Check known rows even when other rows lack evidence.
        for row in rows:
            ident = row['advance_id'] or row['slice_id']
            value, independent = row['amounts'][metric], expected[ident].get(metric)
            matched = None if value is None or independent is None else value == independent
            checks.append(_check(f'{ident}:{metric}', matched,
                                 'MISSING_MONETARY_EVIDENCE' if matched is None else
                                 'ENTRY_ARITHMETIC_DIFFERS' if not matched else None))
        checks.append(_check(f'total:{metric}', None if unknown else
                             known == sum(e[metric] for e in expected.values()),
                             'MISSING_MONETARY_EVIDENCE' if unknown else None))
    statuses = {c['status'] for c in checks}
    matched = False if 'MISMATCH' in statuses else None if 'NOT_CHECKED' in statuses else True
    bound = sum(r['evidence_status'] == 'BOUND' for r in rows)
    return {'rows': rows, 'coverage': {'population': POPULATIONS[category], 'candidates': len(rows),
                                     'bound': bound, 'not_bound': len(rows) - bound},
            'totals': totals, 'reconciliation': {'matched': matched, 'checks': checks}}


def _unbound(row, *reasons):
    row['evidence_status'] = 'NOT_BOUND'
    row['reasons'].extend(reasons)


def _advance_rows(service, state, journal, entries, rows, expected, advance_ids=None):
    drawn = {e['advance_id'] for e in journal if e['op'] == 'draw'}
    ids = {e['advance_id'] for e in journal}
    ids.update(state.get('recovery', {}).get('advances', {}))
    if advance_ids is not None:
        ids.intersection_update(advance_ids)
    for ref in sorted(ids):
        case = service.machine.view(ref)
        phase = case['phase']
        rec = recovery.recovered(state, ref)
        written = rec['writeoff_sim_day'] is not None
        categories = []
        if phase == 'CLOSED': categories.append('closed_unpaid_interest')
        if ref in drawn: categories.append('unapplied_cash')
        if written: categories.append('post_writeoff_residual_claims')
        elif phase == 'DEFAULTED': categories.append('defaulted_unwritten')
        accrued = state['advances'].get(ref)
        paid = state.get('repayment', {}).get('advances', {}).get(ref)
        anchor = recovery.anchor(state, ref)
        pos = recovery.position(state, ref) if anchor is not None else None
        relevant = [(i, e) for i, e in entries
                    if e['payload'].get('advance_id', e['payload'].get('advance_ref')) == ref]
        relevant_indices = {i for i, _ in relevant}
        interest = [e['payload'] for _, e in relevant if e['kind'] == overlay.KIND_INTEREST]
        payments = [e['payload'] for _, e in relevant if e['kind'] == overlay.KIND_REPAYMENT]
        recoveries = [e['payload'] for _, e in relevant if e['kind'] == 'RECOVERY']
        before = [p for p in recoveries if p['phase'] == 'POST_DEFAULT']
        independent_interest = sum(p['posted_contract_krw'] for p in interest) - sum(
            p['allocation']['interest_krw'] for p in payments)
        independent_default = sum(p['posted_default_krw'] for p in interest) - sum(
            p['allocation']['default_interest_krw'] for p in payments)
        for category in categories:
            row = _row({**case, 'advance_id': ref}, phase, category)
            row['fold_values'].update(accrual=copy.deepcopy(accrued), repayment=copy.deepcopy(paid),
                                      recovery=copy.deepcopy(rec) if anchor is not None else None,
                                      position=copy.deepcopy(pos))
            if accrued is not None:
                for field, cumulative, posted in (
                    ('contract_subwon', 'cumulative_contract_exact', 'posted_contract_krw'),
                    ('default_subwon', 'cumulative_default_exact', 'posted_default_krw')):
                    row['remainders'][field] = overlay.exact_text(
                        overlay.parse_exact(accrued[cumulative]) - accrued[posted])
            row['references'] = [_reference('F04', i, e) for i, e in enumerate(journal)
                                 if e['advance_id'] == ref]
            row['references'] += [_reference('OVERLAY', i, e) for i, e in entries
                                  if i in relevant_indices or e['kind'] in (overlay.KIND_TERMS, overlay.KIND_CLOCK)]
            independent = dict.fromkeys(METRICS[category])
            if state['terms_binding'] is None:
                _unbound(row, 'TERMS_BINDING_NOT_BOUND')
            if category == 'unapplied_cash':
                if accrued is None and paid is None:
                    _unbound(row, 'CASH_COVERAGE_NOT_BOUND')
                if row['evidence_status'] == 'BOUND':
                    row['amounts']['unapplied_cash_krw'] = overlay._payments(state, ref)['unapplied_cash_krw']
                    independent['unapplied_cash_krw'] = sum(p['amount_krw'] - sum(
                        p['allocation'][k] for k in ('default_interest_krw', 'interest_krw', 'principal_krw'))
                        for p in payments)
            else:
                if accrued is None:
                    _unbound(row, 'ACCRUAL_NOT_BOUND')
                if category != 'closed_unpaid_interest' and anchor is None:
                    _unbound(row, 'DEFAULT_ANCHOR_NOT_BOUND')
                if row['evidence_status'] == 'BOUND':
                    if category == 'closed_unpaid_interest':
                        gate = overlay.advance_gate(state, ref)
                        row['amounts'] = {m: gate[m] for m in METRICS[category]}
                        independent = dict(zip(METRICS[category], (independent_interest, independent_default)))
                    elif category == 'defaulted_unwritten':
                        row['amounts'] = copy.deepcopy(pos)
                        independent = {
                            'principal_krw': anchor['principal_krw'] - sum(p['allocation']['principal_krw'] for p in before),
                            'interest_krw': independent_interest - sum(p['allocation']['interest_krw'] for p in before),
                            'default_interest_krw': independent_default - sum(p['allocation']['default_interest_krw'] for p in before)}
                        independent['claim_krw'] = sum(independent.values())
                    else:
                        row['amounts']['residual_claim_krw'] = rec['residual_claim_krw']
                        writeoff = next(e['payload'] for _, e in relevant if e['kind'] == 'WRITEOFF')
                        independent['residual_claim_krw'] = writeoff['residual_claim_krw'] - sum(
                            p['amount_krw'] for p in recoveries if p['phase'] == 'POST_WRITEOFF')
            rows[category].append(row)
            expected[category][ref] = independent


def _slice_rows(state, entries, rows, expected):
    category = 'impaired_slice_residuals'
    for sid, record in sorted(slices.registry(state).items()):
        if record['status'] != 'IMPAIRED': continue
        row = _row(record, record['status'], category, basis='LAST_RECORDED_OBSERVATION')
        row['fold_values']['slice'] = copy.deepcopy(record)
        row['amounts'].update(slice_face_krw=record['slice_face_krw'],
                              recourse_received_krw=record['recourse_received_krw'])
        relevant = [(i, e) for i, e in entries if e['kind'] in slices.KINDS
                    and e['payload']['slice_id'] == sid]
        witness = next(((i, e) for i, e in reversed(entries) if e['kind'] in slices.KINDS
                        and record['claim_id'] in e['payload']['witness']['observations']), None)
        obs = None if witness is None else witness[1]['payload']['witness']['observations'][record['claim_id']]
        row['fold_values']['observation'] = copy.deepcopy(obs)
        independent = dict.fromkeys(METRICS[category])
        independent.update(slice_face_krw=record['slice_face_krw'], recourse_received_krw=sum(
            e['payload']['amount_krw'] for _, e in relevant if e['kind'] == 'SLICE_RECOURSE'))
        if obs is None: _unbound(row, 'SLICE_OBSERVATION_NOT_BOUND')
        elif record['payee_label'] not in obs['lines']: _unbound(row, 'SLICE_PAYEE_NOT_BOUND')
        if 'baseline_distributed_krw' not in record: _unbound(row, 'SLICE_BASELINE_NOT_BOUND')
        if row['evidence_status'] == 'BOUND':
            d = slices.derived(record, obs)
            row['fold_values']['derived'] = copy.deepcopy(d)
            row['amounts'].update({k: d[k] for k in METRICS[category][2:]})
            line = obs['lines'][record['payee_label']]
            served = min(record['slice_face_krw'], max(0, line['distributed'] - record['baseline_distributed_krw']))
            outstanding = max(0, record['slice_face_krw'] - served - independent['recourse_received_krw'])
            total = sum(v['outstanding'] for v in obs['lines'].values())
            refund = (obs['refund_face_krw'] * line['outstanding'] + total - 1) // total if total else 0
            eligible = max(0, line['outstanding'] - refund)
            independent.update(served_krw=served, outstanding_krw=outstanding,
                               eligible_line_krw=eligible, shortfall_krw=max(0, outstanding - eligible))
        indices = {i for i, _ in relevant}
        if witness is not None: indices.add(witness[0])
        row['references'] = [_reference('OVERLAY', i, e) for i, e in entries if i in indices]
        rows[category].append(row)
        expected[category][sid] = independent


def compose_sections(service, state, journal, entries, *, advance_ids=None):
    """Compose detached folds, selecting advances before reconciliation.

    Selection covers advance categories only; claim slices are outside that
    scope and their section is omitted. The default retains all five sections.
    Inputs are read without saving or issuing service commands.
    """
    rows = {c: [] for c in METRICS}
    expected = {c: {} for c in METRICS}
    entries = list(_unique(entries))
    _advance_rows(service, state, journal, entries, rows, expected, advance_ids)
    if advance_ids is None:
        _slice_rows(state, entries, rows, expected)
    return {c: _section(c, rows[c], expected[c]) for c in METRICS
            if advance_ids is None or c != 'impaired_slice_residuals'}


def _compose(service, state, journal, entries):
    return compose_sections(service, state, journal, entries)


def report_workspace(directory):
    """Capture once, audit those bytes, restore in memory, and describe the folds."""
    try:
        raw = (Path(directory) / store.FILE_NAME).read_bytes()
    except (OSError, TypeError, ValueError):
        raw = None
    audited = audit.audit_workspace_bytes(raw, workspace=str(directory))
    report = {'format': FORMAT, 'label': 'SIMULATED', 'mode': 'READ_ONLY_RESIDUAL_REGISTER',
              'status': 'AUDIT_FAILED', 'reasons': [],
              'source': {'workspace_sha256': None if raw is None else hashlib.sha256(raw).hexdigest(),
                         'payload_sha256': audited['payload_sha256'], 'state_digest': audited['state_digest'],
                         'overlay_state_digest': None, 'sim_day': None, 'audit': audited},
              'sections': None, 'interpretation': INTERPRETATION,
              'authentication': 'NOT_BOUND', 'actual_payments': 'NOT_BOUND',
              'legal_collectability': 'NOT_BOUND', 'funds_executed': False, 'workspace_mutated': False}
    if not audited['ok']:
        report['reasons'] = [audited['reason']]
        return report
    service = None
    try:
        service = evidence.offline_service(loads(raw))
        if service.workspace_status != 'ACTIVE':
            report['reasons'] = ['RESTORE_NOT_ACTIVE']
            return report
        journal = copy.deepcopy(service.machine.export_journal())
        entries = copy.deepcopy(service.overlay_entries)
        state = overlay.fold(entries, len(journal))
        report['source'].update(overlay_state_digest=overlay.state_digest(state), sim_day=state['sim_day'])
        report['sections'] = _compose(service, state, journal, entries)
    except (ValueError, KeyError, TypeError, ArithmeticError):
        report['reasons'] = ['RESTORE_OR_COMPOSITION_FAILED']
        return report
    finally:
        if service is not None:
            service.observability.close()
    if any(s['coverage']['not_bound'] for s in report['sections'].values()):
        report['reasons'].append('MONETARY_EVIDENCE_NOT_BOUND')
    if any(s['reconciliation']['matched'] is False for s in report['sections'].values()):
        report['reasons'].append('RECONCILIATION_FAILED')
    report['status'] = 'INCOMPLETE' if report['reasons'] else 'COMPLETE'
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
    args = parser.parse_args(argv)
    report = report_workspace(args.workspace)
    sys.stdout.buffer.write(store.canonical_bytes(report) + b'\n')
    return 0 if report['status'] == 'COMPLETE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
