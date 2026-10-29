"""One deterministic SIMULATED evidence document, composed from existing readers.

Caller holds service.lock. No policy inputs or financial arithmetic live here.
"""
from __future__ import annotations

import copy

from capital import overlay
from capital.export import sha256_hex, strip_volatile

FORMAT = 'KIX_CAPITAL_CASE_DOSSIER_V1'
LABEL = 'SIMULATED'
TERMS_BLOCKS = ('ledger_row', 'allocation_quote', 'margin_status', 'covenant_status', 'terms_line')


def not_bound_block(reason):
    return {'status': 'NOT_BOUND', 'reason': reason}


def not_applicable_block(reason):
    return {'status': 'NOT_APPLICABLE', 'reason': reason}


def digest(body):
    return sha256_hex(strip_volatile({key: value for key, value in body.items() if key != 'dossier_digest'}))


def build(service, instance_id, advance_id):
    # Import here to avoid a cycle with the facade that owns ApiError.
    from capital.service import ApiError, digest as state_digest

    def bound_read(reader):
        try:
            return reader()
        except ApiError as exc:
            if exc.code != 'NOT_BOUND':
                raise
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            return not_bound_block(detail.get('reason') or 'NOT_BOUND')

    state = overlay.fold(service.overlay_entries)
    sim_day = state['sim_day']
    case = service.machine.view(advance_id)
    journal = service.machine.export_journal()
    terms = service.terms.status()
    drawn = any(row['op'] == 'draw' and row['advance_id'] == advance_id for row in journal)
    body = {
        'format': FORMAT, 'label': LABEL, 'mode': 'READ_ONLY_CASE_DOSSIER',
        'advance_id': advance_id, 'sim_day': sim_day, 'clock_source': overlay.CLOCK_SOURCE,
        'cut': {'state_digest': service.machine.state_digest(),
                'overlay_state_digest': overlay.state_digest(state),
                'fixtures_digest': state_digest(service.fixtures.rows),
                'terms_version': terms['terms_version']},
        'terms_status': terms['status'], 'terms_reason': terms['reason'], 'drawn': drawn,
        'case': case,
        'receipt_chain': {'journal': [
            {'journal_index': index, 'entry': row,
             'receipt': service.receipts.get(row['idempotency_key'], {}).get('receipt')}
            for index, row in enumerate(journal) if row['advance_id'] == advance_id]},
        'workspace_receipts_without_journal_rows': {
            'scope': 'WORKSPACE_WIDE', 'case_association': 'NOT_INFERRED',
            'rows': [{'idempotency_key': key, 'receipt': service.receipts[key]['receipt']}
                     for key in sorted(service.receipts)
                     if key not in {row['idempotency_key'] for row in journal}]},
        'overlay_rows': {'entries': [
            {'overlay_index': index, 'entry': row}
            for index, row in enumerate(service.overlay_entries)
            if row['payload'].get('advance_id') == advance_id
            or row['kind'] in (overlay.KIND_CLOCK, overlay.KIND_TERMS)]},
        'underwriting_note': 'rule evaluation copied for audit; not a decision by the reader',
        'settlement_evidence': {
            'label': 'READ_ONLY_FIXTURE',
            'rows': [row for row in service.evidence()['rows']
                     if row['claim_id'] in (case['claim_id'], case['settlement_id'])]},
        'not_bound': [
            {'id': key, 'status': 'NOT_BOUND', 'meaning': meaning}
            for key, meaning in (
                ('authentication', 'local synthetic roles are not authentication'),
                ('identity', 'no real identity or KYC'),
                ('remote_attestation', 'local content digest is not remote attestation'),
                ('pdf_rendering', 'JSON only; PDF rendering is not bound'))],
    }
    if terms['status'] == 'NOT_BOUND':
        body.update({name: not_bound_block(terms['reason'] or 'terms not bound')
                     for name in (*TERMS_BLOCKS, 'underwriting')})
    else:
        body['underwriting'] = bound_read(lambda: service.underwrite(
            advance_id, instance_id, 'DOSSIER_READ_ONLY', sim_day=sim_day))
        if not drawn:
            body.update({name: not_applicable_block('NOT_DRAWN') for name in TERMS_BLOCKS})
        else:
            def read_blocks():
                ledger = service.overlay_state()
                if ledger['status'] == 'NOT_BOUND':
                    return {name: not_bound_block(ledger['reason']) for name in TERMS_BLOCKS}
                row = next(row for row in ledger['advances'] if row['advance_id'] == advance_id)
                covenant = service.covenants()
                covenant_row = next((row for row in covenant.get('advances', [])
                                     if row['advance_id'] == advance_id), None)
                subject = next(row for row in service._overlay_subjects(service.overlay_entries)
                               if row['advance_id'] == advance_id)
                line = service.terms.overlay(case, subject['claim'], draw_day=subject['draw_day'],
                                            as_of_day=sim_day, expected_settlement_cash_day=None,
                                            gate=subject['gate'])
                return {
                    'ledger_row': row,
                    'allocation_quote': {key: row[key] for key in ('allocation', 'fsm_repay', 'close_ready')},
                    'margin_status': row['margin'],
                    'covenant_status': covenant_row if covenant_row is not None else not_bound_block(
                        covenant.get('reason') or 'covenant row not bound'),
                    'terms_line': line,
                }
            blocks = bound_read(read_blocks)
            if blocks.get('status') == 'NOT_BOUND':
                body.update({name: dict(blocks) for name in TERMS_BLOCKS})
            else:
                body.update(blocks)
    body = service._terms_envelope(body)
    body['dossier_digest'] = digest(body)
    # Readers may return references to receipts or overlay payloads. Detach the
    # result so a caller cannot mutate the live book through this document.
    return copy.deepcopy(body)
