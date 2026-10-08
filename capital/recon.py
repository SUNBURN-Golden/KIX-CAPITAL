"""Read-only reconciliation exception report. Local diagnostics only.

Compares receipts, the accepted journal, fixture rows, and the synthetic
projection. It does not observe a bank, a PG, or a provider, and it does not
repair, retry, or resolve an absent receipt.
"""
from __future__ import annotations

import copy
import hashlib
import json

from capital.projection import ProjectionError
from capital.protocol import CreditError, CreditMachine


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()

CHECK_IDS = (
    'receipts_vs_journal_keys',
    'rejected_receipts_absent_from_journal',
    'replay_digest_equals_state_digest',
    'case_fixture_map_vs_journal_offers',
    'projection_totals_vs_case_views',
    'fixtures_digest',
)

NOT_BOUND_GAPS = (
    ('bank_pg_provider_observations', '은행·PG·제공자 관측은 연결되지 않았습니다.'),
    ('source_cut', '인증된 source cut이 없습니다.'),
    ('completeness', '제공자 인증 완전성을 주장하지 않습니다.'),
)


def not_bound_gaps():
    return [{'id': gap_id, 'status': 'NOT_BOUND', 'meaning': meaning} for gap_id, meaning in NOT_BOUND_GAPS]


def _check(check_id, matched, detail=None):
    body = {'id': check_id, 'status': 'MATCHED' if matched else 'RECON_MISMATCH'}
    if detail and not matched:
        body['detail'] = detail
    return body


def _as_dict(value):
    return value if type(value) is dict else None


def _as_list(value):
    return value if type(value) is list else None


def _journal_entries(journal):
    if type(journal) is not list:
        return None
    entries = []
    for entry in journal:
        if type(entry) is not dict:
            return None
        entries.append(entry)
    return entries


def _outcome(stored):
    body = _as_dict(stored)
    if body is None:
        return None
    receipt = _as_dict(body.get('receipt'))
    if receipt is None:
        return None
    outcome = receipt.get('outcome')
    if outcome not in {'ACCEPTED', 'REJECTED'}:
        return None
    return outcome


def _credit(stored):
    body = _as_dict(stored)
    if body is None:
        return None
    receipt = _as_dict(body.get('receipt'))
    if receipt is None or receipt.get('outcome') != 'ACCEPTED':
        return None
    result = _as_dict(receipt.get('result'))
    if result is None:
        return None
    return _as_dict(result.get('credit'))


def build_reconciliation(*, payload, unreadable, fixture_rows, fixtures_digest, settlement_source,
                         projection_port, probe_operation_id, instance_id, operation_capacity,
                         workspace_status):
    """Fold copies. `settlement_source.view` is read while replaying a scratch machine."""
    gaps = not_bound_gaps()
    if unreadable:
        report = _envelope(
            instance_id=instance_id, status=unreadable, replay_matched=False, entry_count=0, cut=None,
            fixtures_digest=fixtures_digest, operation_capacity=operation_capacity, checks=[], unknown=[],
            workspace_status=workspace_status, gaps=gaps,
        )
        if type(probe_operation_id) is str:
            report['unknown_unresolved'] = [_unknown(probe_operation_id)]
        return report
    if type(payload) is not dict:
        report = _envelope(
            instance_id=instance_id, status='RECON_MISMATCH', replay_matched=False, entry_count=0, cut=None,
            fixtures_digest=fixtures_digest, operation_capacity=operation_capacity,
            checks=[_check(check_id, False, 'payload_shape') for check_id in CHECK_IDS],
            unknown=[], workspace_status=workspace_status, gaps=gaps,
        )
        if type(probe_operation_id) is str:
            report['unknown_unresolved'] = [_unknown(probe_operation_id)]
        return report

    receipts = payload.get('receipts')
    journal = _journal_entries(payload.get('journal'))
    mapping = payload.get('case_fixtures')
    state_digest = payload.get('state_digest')
    shape_ok = (
        type(receipts) is dict and journal is not None and type(mapping) is dict
        and type(state_digest) is str and state_digest
    )
    if not shape_ok:
        report = _envelope(
            instance_id=instance_id, status='RECON_MISMATCH', replay_matched=False, entry_count=0,
            cut=state_digest if type(state_digest) is str else None, fixtures_digest=fixtures_digest,
            operation_capacity=operation_capacity,
            checks=[_check(check_id, False, 'payload_shape') for check_id in CHECK_IDS],
            unknown=[], workspace_status=workspace_status,
        )
        if type(probe_operation_id) is str and (type(receipts) is not dict or probe_operation_id not in receipts):
            report['unknown_unresolved'] = [_unknown(probe_operation_id)]
        return report

    journal = copy.deepcopy(journal)
    receipts = copy.deepcopy(receipts)
    mapping = copy.deepcopy(mapping)
    restored, restore_error = _restore(journal, settlement_source)
    keys_ok, key_detail = _keys_match(receipts, journal)
    rejected_ok = _rejected_absent(receipts, journal)
    replay_ok = restore_error is None and restored is not None and restored.state_digest() == state_digest
    map_ok = _map_matches(mapping, journal, restored)
    projection_ok = _projection_matches(
        journal, receipts, restored, fixture_rows, projection_port, restore_error,
    )
    fixtures_ok = _fixtures_match(journal, mapping, fixture_rows, fixtures_digest)
    checks = [
        _check('receipts_vs_journal_keys', keys_ok, key_detail),
        _check('rejected_receipts_absent_from_journal', rejected_ok, 'rejected_receipt_in_journal'),
        _check('replay_digest_equals_state_digest', replay_ok, restore_error or 'digest_differs'),
        _check('case_fixture_map_vs_journal_offers', map_ok, 'offer_map'),
        _check('projection_totals_vs_case_views', projection_ok, 'projection_or_receipt_amount'),
        _check('fixtures_digest', fixtures_ok, 'fixture_face'),
    ]
    unknown = _unknowns(receipts, journal, probe_operation_id)
    status = 'MATCHED' if all(row['status'] == 'MATCHED' for row in checks) else 'RECON_MISMATCH'
    return _envelope(
        instance_id=instance_id, status=status, replay_matched=replay_ok, entry_count=len(journal),
        cut=state_digest, fixtures_digest=fixtures_digest, operation_capacity=operation_capacity,
        checks=checks, unknown=unknown, workspace_status=workspace_status, gaps=gaps,
    )


def _envelope(*, instance_id, status, replay_matched, entry_count, cut, fixtures_digest,
              operation_capacity, checks, unknown, workspace_status, gaps=None):
    return {
        'mode': 'READ_ONLY_RECONCILIATION',
        'label': 'SIMULATED',
        'diagnostic': 'LOCAL_ONLY',
        'instance_id': instance_id,
        'status': status,
        'replay_matched': replay_matched,
        'entry_count': entry_count,
        'state_digest': cut,
        'cut': cut,
        'fixtures_digest': fixtures_digest,
        'operation_capacity': operation_capacity,
        'scope': {
            'cut': cut,
            'state_digest': cut,
            'fixtures_digest': fixtures_digest,
            'operation_capacity': operation_capacity,
            'capacity_bound': operation_capacity,
            'source_cut': 'NOT_BOUND',
            'completeness': 'NOT_BOUND',
        },
        'checks': checks,
        'not_bound': gaps if gaps is not None else not_bound_gaps(),
        'unknown_unresolved': unknown,
        'unknown_policy': {
            'absent_receipt': 'UNKNOWN_UNRESOLVED',
            'retry_authorized': False,
            'resolved_by_reconciliation': False,
        },
        'bank_reconciliation': 'NOT_BOUND',
        'provider_authenticated_completeness': 'NOT_BOUND',
        'source_cut': 'NOT_BOUND',
        'funds_executed': False,
        'durable': False,
        'workspace_mutated': False,
        'workspace_status': workspace_status,
    }


def _restore(journal, settlement_source):
    try:
        restored = CreditMachine.restore(copy.deepcopy(journal), settlement_source)
    except CreditError as exc:
        return None, exc.code
    return restored, None


def _keys_match(receipts, journal):
    journal_keys = []
    for entry in journal:
        key = entry.get('idempotency_key')
        if type(key) is not str:
            return False, 'journal_key'
        journal_keys.append(key)
    if len(journal_keys) != len(set(journal_keys)):
        return False, 'duplicate_journal_key'
    accepted = set()
    reconcile_only = set()
    for key, stored in receipts.items():
        if type(key) is not str:
            return False, 'receipt_key'
        outcome = _outcome(stored)
        if outcome is None:
            return False, 'receipt_shape'
        receipt = stored['receipt']
        if receipt.get('operation_id') != key:
            return False, 'operation_id'
        if outcome != 'ACCEPTED':
            continue
        # The pinned F04 reconcile command stores an ACCEPTED receipt and does not append a journal row.
        if _reconcile_receipt(stored):
            reconcile_only.add(key)
        else:
            accepted.add(key)
    journal_set = set(journal_keys)
    if reconcile_only & journal_set:
        return False, 'reconcile_in_journal'
    if journal_set != accepted:
        return False, 'key_set'
    return True, None


def _reconcile_receipt(stored):
    receipt = stored['receipt']
    result = receipt.get('result')
    return type(result) is dict and result.get('applied') == 'reconcile' and result.get('matched') is True


def _rejected_absent(receipts, journal):
    journal_keys = {entry.get('idempotency_key') for entry in journal}
    for key, stored in receipts.items():
        if _outcome(stored) == 'REJECTED' and key in journal_keys:
            return False
    return True


def _map_matches(mapping, journal, restored):
    offers = []
    for entry in journal:
        if entry.get('op') != 'offer':
            continue
        body = _as_dict(entry.get('body'))
        face = _as_dict(body.get('face')) if body else None
        advance_id = entry.get('advance_id')
        if type(advance_id) is not str or face is None or type(face.get('claim_id')) is not str:
            return False
        if mapping.get(advance_id) != face['claim_id']:
            return False
        offers.append(advance_id)
    if len(offers) != len(set(offers)) or set(mapping) != set(offers):
        return False
    if restored is None:
        return True
    expected = {}
    seen = []
    for entry in journal:
        advance_id = entry.get('advance_id')
        if advance_id not in seen:
            seen.append(advance_id)
            try:
                expected[advance_id] = restored.view(advance_id)['claim_id']
            except CreditError:
                return False
    return mapping == expected


def _projection_matches(journal, receipts, restored, fixture_rows, projection_port, restore_error):
    if restore_error is not None or restored is None:
        return False
    evidence = [copy.deepcopy(fixture_rows[key]) for key in sorted(fixture_rows)]
    try:
        projected = projection_port.project(copy.deepcopy(journal), evidence)
    except ProjectionError:
        return False
    views = {}
    try:
        for advance_id in _advance_ids(journal):
            views[advance_id] = restored.view(advance_id)
    except CreditError:
        return False
    advances = projected.get('read_model', {}).get('advances')
    claims = projected.get('read_model', {}).get('claims')
    if type(advances) is not list or type(claims) is not list:
        return False
    by_advance = {row.get('advance_id'): row for row in advances}
    if set(by_advance) != set(views):
        return False
    drawn_sum = repaid_sum = outstanding_sum = 0
    for advance_id, view in views.items():
        row = by_advance[advance_id]
        if row.get('amount') != view.get('amount') or row.get('drawn') != view.get('drawn_exposure'):
            return False
        if row.get('repaid') != view.get('repaid_exposure') or row.get('outstanding') != view.get('outstanding_exposure'):
            return False
        drawn_sum += view['drawn_exposure']
        repaid_sum += view['repaid_exposure']
        outstanding_sum += view['outstanding_exposure']
    accounts = projected.get('accounts')
    if type(accounts) is not list:
        return False
    exposure = sum(row.get('debit_total', 0) for row in accounts if str(row.get('code', '')).startswith('SIM_ADVANCE_EXPOSURE:'))
    memo = sum(row.get('credit_total', 0) for row in accounts if str(row.get('code', '')).startswith('SIM_REPAY_MEMO:'))
    obligation = sum(row.get('balance', 0) for row in accounts if str(row.get('code', '')).startswith('SIM_ADVANCE_OBLIGATION:'))
    if exposure != drawn_sum or memo != repaid_sum or obligation != outstanding_sum:
        return False
    by_claim = {row.get('claim_id'): row for row in claims}
    if set(by_claim) != set(fixture_rows):
        return False
    for claim_id, source in fixture_rows.items():
        claim = source.get('claim') if type(source) is dict else None
        row = by_claim[claim_id]
        if type(claim) is not dict:
            return False
        if row.get('gross') != claim.get('gross') or row.get('confirmed_cash') != claim.get('confirmed_cash'):
            return False
        if row.get('refund_face') != claim.get('refund_face') or row.get('refund_outstanding') != claim.get('refund_outstanding'):
            return False
    return _receipt_amounts(journal, receipts, views)


def _advance_ids(journal):
    seen = []
    for entry in journal:
        advance_id = entry.get('advance_id')
        if advance_id not in seen:
            seen.append(advance_id)
    return seen


def _receipt_amounts(journal, receipts, views):
    for entry in journal:
        if entry.get('op') != 'offer':
            continue
        if entry.get('idempotency_key') not in receipts:
            continue
        credit = _credit(receipts.get(entry.get('idempotency_key')))
        body = _as_dict(entry.get('body')) or {}
        view = views.get(entry.get('advance_id'))
        if credit is None or view is None:
            return False
        if credit.get('amount') != body.get('amount') or credit.get('amount') != view.get('amount'):
            return False
    for entry in journal:
        if entry.get('op') != 'repay':
            continue
        if entry.get('idempotency_key') not in receipts:
            continue
        credit = _credit(receipts.get(entry.get('idempotency_key')))
        body = _as_dict(entry.get('body')) or {}
        if credit is None or type(body.get('amount')) is not int:
            return False
        repayments = credit.get('repayments')
        if type(repayments) is not list:
            return False
        matched = [row for row in repayments if type(row) is dict and row.get('amount') == body.get('amount')
                   and row.get('sequence') == body.get('sequence')]
        if len(matched) != 1:
            return False
    return True


def _fixtures_match(journal, mapping, fixture_rows, fixtures_digest):
    if _digest(fixture_rows) != fixtures_digest:
        return False
    for entry in journal:
        if entry.get('op') != 'offer':
            continue
        body = _as_dict(entry.get('body'))
        face = _as_dict(body.get('face')) if body else None
        if face is None:
            return False
        claim_id = face.get('claim_id')
        if mapping.get(entry.get('advance_id')) != claim_id or claim_id not in fixture_rows:
            return False
        claim = fixture_rows[claim_id].get('claim') if type(fixture_rows[claim_id]) is dict else None
        if type(claim) is not dict:
            return False
        if claim.get('gross') != face.get('gross') or claim.get('confirmed_cash') != face.get('confirmed_cash'):
            return False
        if claim.get('refund_face') != face.get('refund_face'):
            return False
    return True


def _unknown(operation_id):
    return {
        'operation_id': operation_id,
        'outcome': 'UNKNOWN_UNRESOLVED',
        'retry_authorized': False,
        'resolved': False,
    }


def _unknowns(receipts, journal, probe_operation_id):
    missing = []
    for entry in journal:
        key = entry.get('idempotency_key')
        if type(key) is str and key not in receipts:
            missing.append(key)
    if type(probe_operation_id) is str and probe_operation_id not in receipts and probe_operation_id not in missing:
        missing.append(probe_operation_id)
    return [_unknown(key) for key in missing]
