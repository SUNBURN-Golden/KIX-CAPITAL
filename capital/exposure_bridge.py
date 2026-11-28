"""Explain recorded F04 and recovery balances from one audited SIMULATED workspace."""
from __future__ import annotations

import argparse
from collections import defaultdict
import copy
import hashlib
from pathlib import Path
import sys

from capital import audit, evidence, overlay, recovery, store
from capital.verify import loads

FORMAT = 'KIX_CAPITAL_EXPOSURE_BRIDGE_V1'
RECOVERY_AMOUNTS = (
    'default_anchor_principal_krw', 'principal_recovered_krw', 'written_off_principal_krw',
    'recovery_principal_krw', 'recovery_interest_krw', 'recovery_default_interest_krw',
    'recovery_claim_krw',
)
AMOUNTS = ('f04_exposure_krw', *RECOVERY_AMOUNTS, 'writeoff_opening_claim_krw',
           'post_writeoff_residual_claim_krw', 'closed_unpaid_interest_krw',
           'closed_unpaid_default_interest_krw')
INTERPRETATION = (
    'F04 exposure is drawn principal less accepted F04 repayments and is fixed at default. '
    'Overlay principal recovery and writeoff reduce recovery principal without changing F04. '
    'After writeoff, receipts reduce the undivided residual claim. The recorded interest '
    'buckets describe the writeoff basis and do not allocate that residual. CLOSED interest '
    'is a separate measure. The balances overlap and portfolio coverage contains counts only. '
    'All amounts are recorded integer KRW in simulation. Financial recognition is NOT_BOUND.'
)


def _reference(journal, index, entry):
    f04 = journal == 'F04'
    return {'journal': journal, 'index': index,
            'entry_id': entry['idempotency_key' if f04 else 'overlay_id'],
            'kind': entry['op' if f04 else 'kind'],
            'after_journal_index': entry.get('after_journal_index'), 'sim_day': entry.get('sim_day')}


def _check(row, field, expected, observed, references, *, missing=None):
    if missing is not None:
        status, reason = 'NOT_CHECKED', missing
    elif type(observed) is int and expected == observed:
        status, reason = 'MATCHED', None
    else:
        status, reason = 'MISMATCH', 'ENTRY_ARITHMETIC_DIFFERS'
    row['checks'].append({'id': field, 'status': status, 'reason': reason,
                          'expected_krw': expected, 'observed_krw': observed, 'references': references})
    if status == 'MATCHED' and field in row['amounts']:
        row['amounts'][field] = observed
    if reason is not None and reason not in row['reasons']:
        row['reasons'].append(reason)


def _f04_checks(row, entries, exposure):
    offered, outstanding = None, 0
    refs, defaults = [], {}
    for ref, body in entries:
        kind = ref['kind']
        if kind in ('offer', 'draw', 'repay'):
            refs.append(ref)
        if kind == 'offer':
            offered = body['amount']
        elif kind == 'draw':
            outstanding = offered
        elif kind == 'repay':
            outstanding -= body['amount']
        elif kind == 'default':
            defaults[ref['index']] = (ref, outstanding)
    _check(row, 'f04_exposure_krw', outstanding, exposure, refs)
    return refs, defaults


def _interest(entries):
    contract, default = 0, 0
    refs = []
    for ref, payload in entries:
        if ref['kind'] == overlay.KIND_INTEREST:
            contract += payload['posted_contract_krw']
            default += payload['posted_default_krw']
        elif ref['kind'] == overlay.KIND_REPAYMENT or (
                ref['kind'] == 'RECOVERY' and payload['phase'] == 'POST_DEFAULT'):
            contract -= payload['allocation']['interest_krw']
            default -= payload['allocation']['default_interest_krw']
        else:
            continue
        refs.append(ref)
    return contract, default, refs


def _interest_evidence(row, entries, f04_refs, clocks, terms, *, stop, anchor=None):
    draw = next(ref for ref in f04_refs if ref['kind'] == 'draw')
    anchor_ref, anchor_payload = anchor if anchor is not None else (None, None)
    start, draw_clock = 0, None
    expected, clock_refs = [], []
    for clock in clocks:
        # A tick at journal length N sees F04 entries with indexes below N.
        length = clock['after_journal_index']
        if length <= draw['index']:
            start, draw_clock = clock['sim_day'], clock
            continue
        if stop is not None:
            if stop['journal'] == 'F04' and length > stop['index']:
                break
            if stop['journal'] == 'OVERLAY' and clock['index'] > stop['index']:
                break
        day = end = clock['sim_day']
        if anchor_ref is not None and clock['index'] > anchor_ref['index']:
            end = min(day, anchor_payload['writeoff_eligible_sim_day'])
        if end <= start:
            break  # Already at the recorded accrual cutoff.
        expected.append((length, day, start, end))
        clock_refs.append(clock)
        start = end
    posted = [(ref['after_journal_index'], ref['sim_day'], p['from_day'], p['to_day'])
              for ref, p in entries if ref['kind'] == overlay.KIND_INTEREST]

    if draw_clock is not None:
        clock_refs.insert(0, draw_clock)
    row['references'].extend(clock_refs)
    refs = [ref for ref in (draw, stop, anchor_ref, terms) if ref is not None] + clock_refs
    if terms is None:
        row['reasons'].append('TERMS_BINDING_NOT_BOUND')
    if not posted or posted != expected:
        return 'ACCRUAL_NOT_BOUND', refs
    return ('TERMS_BINDING_NOT_BOUND' if terms is None else None), refs


def _closed_checks(row, gate, entries, terms, f04_refs, clocks):
    contract, default, refs = _interest(entries)
    # An accepted close requires zero F04 principal. The final repay stopped accrual.
    missing, coverage_refs = _interest_evidence(row, entries, f04_refs, clocks, terms, stop=f04_refs[-1])
    refs = coverage_refs + refs
    _check(row, 'closed_unpaid_interest_krw', None if missing else contract,
           gate['interest_due_krw'], refs, missing=missing)
    _check(row, 'closed_unpaid_default_interest_krw', None if missing else default,
           gate['default_interest_due_krw'], refs, missing=missing)


def _writeoff_checks(row, writeoff, late_entries, opening, missing, opening_refs, rec, pos):
    writeoff_ref, payload = writeoff
    _check(row, 'writeoff_opening_claim_krw', opening, payload['residual_claim_krw'],
           opening_refs, missing=missing)
    running = opening
    previous = writeoff_ref
    late_refs = []
    for ref, receipt in late_entries:
        if ref['kind'] != 'RECOVERY' or receipt['phase'] != 'POST_WRITEOFF':
            continue
        late_refs.append(ref)
        if running is not None:
            running -= receipt['amount_krw']
        _check(row, f'running_residual_claim_krw:{ref["index"]}', running,
               receipt['residual_claim_krw'], [previous, ref], missing=missing)
        previous = ref
    refs = opening_refs + late_refs
    _check(row, 'post_writeoff_residual_claim_krw', running, rec['residual_claim_krw'], refs,
           missing=missing)
    _check(row, 'recovery_claim_krw', running, pos['claim_krw'], refs, missing=missing)


def _recovery_checks(row, entries, f04_refs, defaults, terms, clocks):
    values = row['fold_values']
    anchor = values['anchor']
    stamped_anchor = next((item for item in entries if item[0]['kind'] == 'default_anchor'), None)
    if anchor is None or stamped_anchor is None:
        row['recovery_basis'] = 'NOT_BOUND'
        for field in RECOVERY_AMOUNTS:
            _check(row, field, None, None, [ref for ref, _ in defaults.values()],
                   missing='DEFAULT_ANCHOR_NOT_BOUND')
        return

    anchor_ref, anchor_payload = stamped_anchor
    link = defaults.get(anchor_ref['after_journal_index'] - 1)
    anchor_refs = [*f04_refs, anchor_ref]
    expected_anchor = None
    if link is not None:
        default_ref, default_exposure = link
        anchor_refs = [*f04_refs, default_ref, anchor_ref]
        if default_ref['entry_id'] == anchor_payload['f04_operation_id'] == anchor['f04_operation_id']:
            expected_anchor = default_exposure
    _check(row, 'default_anchor_principal_krw', expected_anchor, anchor['principal_krw'], anchor_refs)

    rec, pos = values['recovered'], values['position']
    writeoff = next((item for item in entries if item[0]['kind'] == 'WRITEOFF'), None)
    row['recovery_basis'] = 'POST_DEFAULT' if writeoff is None else 'POST_WRITEOFF'
    before = entries
    after, writeoff_refs = [], []
    written_off = 0
    if writeoff is not None:
        writeoff_ref, payload = writeoff
        cut = writeoff_ref['index']
        before = [item for item in entries if item[0]['index'] < cut]
        after = [item for item in entries if item[0]['index'] > cut]
        writeoff_refs = [writeoff_ref]
        written_off = payload['writeoff_principal_krw']

    early = [(ref, payload) for ref, payload in before if ref['kind'] == 'RECOVERY'
             and payload['phase'] == 'POST_DEFAULT']
    recovered_principal = sum(p['allocation']['principal_krw'] for _, p in early)
    early_refs = [ref for ref, _ in early]
    principal_refs = [anchor_ref, *early_refs, *writeoff_refs]
    principal_before_writeoff = anchor_payload['principal_krw'] - recovered_principal
    remaining_principal = principal_before_writeoff - written_off
    _check(row, 'principal_recovered_krw', recovered_principal, rec['principal_recovered_krw'],
           [anchor_ref, *early_refs])
    _check(row, 'written_off_principal_krw', written_off, rec['written_off_krw'], principal_refs)
    _check(row, 'recovery_principal_krw', remaining_principal, pos['principal_krw'], principal_refs)
    displayed = (pos['principal_krw'], rec['principal_recovered_krw'], rec['written_off_krw'])
    _check(row, 'f04_principal_bridge', sum(displayed), values['f04_exposure_krw'],
           anchor_refs + early_refs + writeoff_refs)

    stop = writeoff[0] if writeoff is not None else None
    if stop is None and remaining_principal == 0:
        stop = early[-1][0]  # The final allocated recovery cleared principal.
    missing, coverage_refs = _interest_evidence(row, before, f04_refs, clocks, terms,
                                                stop=stop, anchor=stamped_anchor)
    contract, default, interest_refs = _interest(before)
    interest_refs = coverage_refs + [ref for ref in interest_refs if ref != stop]
    _check(row, 'recovery_interest_krw', None if missing else contract, pos['interest_krw'],
           interest_refs, missing=missing)
    _check(row, 'recovery_default_interest_krw', None if missing else default, pos['default_interest_krw'],
           interest_refs, missing=missing)
    claim = None if missing else principal_before_writeoff + contract + default
    if writeoff is None:
        _check(row, 'recovery_claim_krw', claim, pos['claim_krw'], interest_refs, missing=missing)
    else:
        _check(row, 'writeoff_cutoff_principal_krw', principal_before_writeoff, written_off, principal_refs)
        _writeoff_checks(row, writeoff, after, claim, missing, interest_refs, rec, pos)


def _compose(service, state, journal, entries):
    f04, by_advance = defaultdict(list), defaultdict(list)
    for index, entry in enumerate(journal):
        f04[entry['advance_id']].append((_reference('F04', index, entry), entry['body']))
    seen = set()
    terms = None
    clocks = []
    for index, entry in enumerate(entries):
        if entry['overlay_id'] in seen:
            continue
        seen.add(entry['overlay_id'])
        ref, payload = _reference('OVERLAY', index, entry), entry['payload']
        if entry['kind'] == overlay.KIND_TERMS:
            terms = ref
        elif entry['kind'] == overlay.KIND_CLOCK:
            clocks.append(ref)
        elif entry['kind'] == overlay.KIND_REPAYMENT:
            by_advance[payload['advance_ref']].append((ref, payload))
        elif entry['kind'] in (overlay.KIND_INTEREST, 'default_anchor', 'RECOVERY', 'WRITEOFF'):
            by_advance[payload['advance_id']].append((ref, payload))

    rows = []
    for advance in sorted(f04):
        case = service.machine.view(advance)
        exposure, phase = case['outstanding_exposure'], case['phase']
        anchor = recovery.anchor(state, advance)
        gate = overlay.advance_gate(state, advance) if phase == 'CLOSED' else None
        values = {'f04_exposure_krw': exposure, 'anchor': anchor, 'closed_interest_gate': gate,
                  'recovered': recovery.recovered(state, advance) if anchor is not None else None,
                  'position': recovery.position(state, advance) if anchor is not None else None}
        advance_entries = by_advance[advance]
        overlay_refs = [ref for ref, _ in advance_entries]
        if terms is not None:
            overlay_refs.append(terms)
        row = {'advance_id': advance, 'phase': phase, 'recovery_basis': 'NOT_APPLICABLE',
               'fold_values': values, 'amounts': dict.fromkeys(AMOUNTS), 'checks': [], 'reasons': [],
               'references': [ref for ref, _ in f04[advance]] + overlay_refs}
        f04_refs, defaults = _f04_checks(row, f04[advance], exposure)
        if phase == 'DEFAULTED':
            _recovery_checks(row, advance_entries, f04_refs, defaults, terms, clocks)
        elif phase == 'CLOSED':
            _closed_checks(row, gate, advance_entries, terms, f04_refs, clocks)
        row['references'].sort(key=lambda ref: (ref['journal'], ref['index']))
        row['status'] = 'INCOMPLETE' if row['reasons'] else 'COMPLETE'
        rows.append(row)
    return rows


def report_workspace(directory) -> dict:
    """Capture the workspace once, audit and restore that capture, and reconcile its balances."""
    try:
        path = Path(directory) / store.FILE_NAME
        raw = path.read_bytes() if path.is_file() else None
    except (OSError, TypeError, ValueError):
        raw = None
    audited = audit.audit_workspace_bytes(raw, workspace=str(directory))
    report = {'format': FORMAT, 'label': 'SIMULATED', 'mode': 'READ_ONLY_EXPOSURE_BRIDGE',
              'status': 'AUDIT_FAILED', 'reasons': [], 'rows': None, 'coverage': None,
              'source': {'workspace_sha256': None if raw is None else hashlib.sha256(raw).hexdigest(),
                         'payload_sha256': audited['payload_sha256'], 'state_digest': audited['state_digest'],
                         'overlay_state_digest': None, 'sim_day': None, 'audit': audited},
              'interpretation': INTERPRETATION, 'authentication': 'NOT_BOUND', 'actual_payments': 'NOT_BOUND',
              'funds_executed': False, 'workspace_mutated': False}
    if not audited['ok']:
        report['reasons'].append(audited['reason'])
        return report

    service = None
    try:
        service = evidence.offline_service(loads(raw))
        if service.workspace_status != 'ACTIVE':
            report['reasons'].append('RESTORE_NOT_ACTIVE')
            return report
        journal = service.machine.export_journal()
        entries = copy.deepcopy(service.overlay_entries)
        state = overlay.fold(entries, len(journal))
        report['source'].update(overlay_state_digest=overlay.state_digest(state), sim_day=state['sim_day'])
        rows = _compose(service, state, journal, entries)
    except (ValueError, KeyError, TypeError, ArithmeticError):
        report['reasons'].append('RESTORE_OR_COMPOSITION_FAILED')
        return report
    finally:
        if service is not None:
            service.observability.close()

    statuses = {check['status'] for row in rows for check in row['checks']}
    if 'NOT_CHECKED' in statuses:
        report['reasons'].append('MONETARY_EVIDENCE_NOT_BOUND')
    if 'MISMATCH' in statuses:
        report['reasons'].append('RECONCILIATION_FAILED')
    incomplete = sum(row['status'] == 'INCOMPLETE' for row in rows)
    report.update(rows=rows, status='INCOMPLETE' if incomplete else 'COMPLETE',
                  coverage={'advances': len(rows), 'complete': len(rows) - incomplete,
                            'incomplete': incomplete})
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
    args = parser.parse_args(argv)
    report = report_workspace(args.workspace)
    sys.stdout.buffer.write(store.canonical_bytes(report) + b'\n')
    return 0 if report['status'] == 'COMPLETE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
