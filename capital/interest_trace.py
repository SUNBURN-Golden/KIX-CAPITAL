"""Detached SIMULATED explanations of recorded accrual, never an interest engine.

Caller holds the service lock. The complete overlay fold validates the evidence;
only differences of recorded cumulative fractions are calculated here. Elapsed
boundaries and day splits are copied verbatim, including historical conventions.
"""
from __future__ import annotations

import copy
from fractions import Fraction

from capital import overlay, recovery
from capital.export import sha256_hex, strip_volatile

FORMAT = 'KIX_CAPITAL_INTEREST_TRACE_V1'


def digest(body):
    return sha256_hex(strip_volatile({k: v for k, v in body.items() if k != 'trace_digest'}))


def _component(payload, bucket, before):
    after = overlay.parse_exact(payload[f'cumulative_{bucket}_exact'])
    posted = payload[f'posted_{bucket}_krw']
    if posted != overlay.floor(after) - overlay.floor(before):
        raise overlay.OverlayError('trace cumulative floor mismatch')
    return {
        'days': payload['contractual_days' if bucket == 'contract' else 'default_days'],
        'rate_bps': payload[f'{bucket}_bps'],
        'cumulative_before': overlay.exact_text(before),
        'cumulative_after': overlay.exact_text(after),
        'exact_increment': overlay.exact_text(after - before), 'posted_krw': posted,
        'remainder_before': overlay.exact_text(before - overlay.floor(before)),
        'remainder_after': overlay.exact_text(after - overlay.floor(after)),
    }


def build(service, instance_id, advance_id):
    from capital.service import ApiError

    journal = service.machine.export_journal()
    state = overlay.fold(service.overlay_entries, len(journal))
    # Link readers must see the same effective journal as the fold, including
    # when an old identical clock entry is repeated after a later default.
    effective, seen = [], set()
    for index, entry in enumerate(service.overlay_entries):
        if entry['overlay_id'] not in seen:
            seen.add(entry['overlay_id'])
            effective.append((index, entry))
    recovery.validate_links([entry for _, entry in effective], journal)
    case = service.machine.view(advance_id)
    drawn = any(r['op'] == 'draw' and r['advance_id'] == advance_id for r in journal)
    diagnostics = []
    unavailable = None

    def blocked(reason, status='NOT_BOUND'):
        return {'status': status, 'reason': reason}

    # Binding checks use the existing readers. They never generate accrual.
    status = service._overlay_terms()
    if status is None:
        unavailable = blocked('terms not bound')
    elif state['terms_binding'] is not None and state['terms_binding']['terms_version'] != status['terms_version']:
        unavailable = blocked('terms version mismatch')
    elif not drawn:
        unavailable = blocked('NOT_DRAWN', 'NOT_APPLICABLE')
    elif case['phase'] == 'DEFAULTED' and recovery.anchor(state, advance_id) is None:
        unavailable = blocked('DEFAULT_DAY_UNKNOWN')
    due_reader = None
    if unavailable is None:
        try:
            sibling = service.overlay_state()
            row = next(r for r in sibling['advances'] if r['advance_id'] == advance_id)
            subject = next(r for r in service._overlay_subjects(service.overlay_entries)
                           if r['advance_id'] == advance_id)
            if service._ledger_terms(subject) is None:
                unavailable = blocked('draw terms not bound')
            else:
                due_reader = {k: row[k] for k in ('interest_due_krw', 'default_interest_due_krw')}
                due_reader['recovery_position'] = (recovery.position(state, advance_id)
                                                   if recovery.anchor(state, advance_id) else None)
        except ApiError as exc:
            if exc.code != 'NOT_BOUND':
                raise
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            unavailable = blocked(detail.get('reason') or 'NOT_BOUND')
    if unavailable:
        diagnostics.append({'scope': 'computed', **unavailable})

    segments, payments, events = [], [], []
    previous = {k: Fraction(0) for k in ('contract', 'default')}
    for index, entry in effective:
        p, kind = entry['payload'], entry['kind']
        if p.get('advance_id', p.get('advance_ref')) != advance_id:
            continue
        ref = {k: entry[k] for k in ('overlay_id', 'after_journal_index', 'sim_day')}
        ref.update(overlay_index=index, recorded_payload=p)
        if kind == overlay.KIND_INTEREST:
            components = {k: _component(p, k, previous[k]) for k in previous}
            previous = {k: overlay.parse_exact(p[f'cumulative_{k}_exact']) for k in previous}
            segments.append({**ref, 'components': unavailable or {'status': 'COMPUTED', **components}})
        elif kind in (overlay.KIND_REPAYMENT, 'RECOVERY'):
            receipt = service.receipts.get(p.get('f04_operation_id'), {}).get('receipt')
            linked = next(({'journal_index': i, 'entry': r} for i, r in enumerate(journal)
                           if r['idempotency_key'] == p.get('f04_operation_id')), None)
            payments.append({**ref, 'kind': kind, 'payment_basis': 'UNVERIFIED_ASSERTED',
                             'f04_receipt': receipt, 'f04_journal_row': linked})
        elif kind in (*overlay.MARGIN_KINDS, *recovery.KINDS):
            events.append({**ref, 'kind': kind})

    if not segments and unavailable is None:
        diagnostics.append({'scope': 'segments', 'status': 'NOT_APPLICABLE', 'reason': 'NO_POSTINGS_YET'})
    linked_ops = {p['recorded_payload'].get('f04_operation_id') for p in payments}
    if any(r['op'] == 'repay' and r['advance_id'] == advance_id and r['idempotency_key'] not in linked_ops
           for r in journal):
        diagnostics.append({'scope': 'payments', 'status': 'NOT_BOUND',
                            'reason': 'DIRECT_F04_REPAYMENTS_NOT_INTEREST_WITNESSES'})

    totals = unavailable
    if totals is None:
        posted = {k: sum(s['recorded_payload'][f'posted_{k}_krw'] for s in segments) for k in previous}
        record = state['advances'].get(advance_id, {})
        for k in posted:
            if posted[k] != record.get(f'posted_{k}_krw', 0):
                raise overlay.OverlayError('trace posted total mismatch')
        repayment = {k: 0 for k in ('paid_default_krw', 'paid_interest_krw', 'principal_krw',
                                    'unapplied_cash_krw', 'postings')}
        recovered = recovery.recovered(state, advance_id)
        recovery_paid = {k: 0 for k in ('paid_default_krw', 'paid_interest_krw', 'principal_recovered_krw')}
        residual_recovery = 0
        for payment in payments:
            p = payment['recorded_payload']
            if payment['kind'] == overlay.KIND_REPAYMENT:
                for target, source in (('paid_default_krw', 'default_interest_krw'),
                                       ('paid_interest_krw', 'interest_krw'), ('principal_krw', 'principal_krw')):
                    repayment[target] += p['allocation'][source]
                repayment['unapplied_cash_krw'] = p['allocation']['unapplied_after_krw']
                repayment['postings'] += 1
            elif p['phase'] == 'POST_WRITEOFF':
                residual_recovery += p['amount_krw']
            else:
                for target, source in (('paid_default_krw', 'default_interest_krw'),
                                       ('paid_interest_krw', 'interest_krw'),
                                       ('principal_recovered_krw', 'principal_krw')):
                    recovery_paid[target] += p['allocation'][source]
        if repayment != overlay._payments(state, advance_id):
            raise overlay.OverlayError('trace repayment total mismatch')
        if any(recovery_paid[k] != recovered[k] for k in recovery_paid):
            raise overlay.OverlayError('trace recovery total mismatch')
        writeoffs = [e['recorded_payload'] for e in events if e['kind'] == 'WRITEOFF']
        adjustments = {k: sum(p[k] for p in writeoffs) for k in (
            'writeoff_principal_krw', 'accrued_interest_reversed_krw', 'suspended_interest_released_krw')}
        if adjustments['writeoff_principal_krw'] != recovered['written_off_krw']:
            raise overlay.OverlayError('trace writeoff total mismatch')
        if writeoffs and writeoffs[-1]['residual_claim_krw'] - residual_recovery != recovered['residual_claim_krw']:
            raise overlay.OverlayError('trace residual recovery mismatch')
        totals = {'status': 'COMPUTED', 'reconciled': True, 'posted_krw': posted,
                  'cumulative_exact': {k: overlay.exact_text(v) for k, v in previous.items()},
                  'repayment': repayment, 'recovery_paid': recovery_paid,
                  'writeoff_adjustments': adjustments, 'residual_recovery_krw': residual_recovery,
                  'recovery_fold': recovered, 'due_reader': due_reader}
    body = service._terms_envelope({
        'format': FORMAT, 'label': 'SIMULATED', 'mode': 'READ_ONLY_INTEREST_TRACE',
        'advance_id': advance_id, 'drawn': drawn, 'sim_day': state['sim_day'],
        'clock_source': overlay.CLOCK_SOURCE,
        'cut': {'state_digest': service.machine.state_digest(),
                'overlay_state_digest': overlay.state_digest(state),
                'journal_length': len(journal), 'overlay_journal_length': len(service.overlay_entries),
                'terms_binding': state['terms_binding']},
        'segments': segments, 'payments': payments, 'events': events,
        'totals': totals, 'diagnostics': diagnostics,
    })
    body['trace_digest'] = digest(body)
    return copy.deepcopy(body)
