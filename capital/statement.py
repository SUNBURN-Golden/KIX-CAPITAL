"""Five-category local statement. Primary sales and resale sales are never summed.

Approved, exposure, and reserved figures come from F04 case views. Settlement
confirmed/distributed cash and refund figures come from the immutable fixture
views. Those fixture totals are not added to the case figures. primary_sales,
resale_sales, and actual_paid stay NOT_BOUND.
"""
from __future__ import annotations

APPROVED_PHASES = frozenset({'APPROVED', 'DRAWN', 'CLOSED', 'DEFAULTED'})

SALES_GAPS = (
    ('primary_sales', '최초 판매 매출은 연결되지 않았고 리셀과 합산하지 않습니다.'),
    ('resale_sales', '리셀 매출은 연결되지 않았고 최초 판매와 합산하지 않습니다.'),
    ('actual_paid', '실지급은 연결되지 않았습니다.'),
)


def build_statement(*, cases, fixture_views, fixtures_digest, state_digest, instance_id,
                    operation_capacity, workspace_status):
    ordered = sorted(cases, key=lambda row: row['advance_id'])
    approved_rows = [
        {'advance_id': row['advance_id'], 'phase': row['phase'], 'amount': row['amount']}
        for row in ordered if row['phase'] in APPROVED_PHASES
    ]
    exposure_rows = [
        {
            'advance_id': row['advance_id'],
            'phase': row['phase'],
            'drawn': row['drawn_exposure'],
            'repaid': row['repaid_exposure'],
            'outstanding': row['outstanding_exposure'],
            'confirmed_cash_on_face': row['confirmed_cash_on_face'],
        }
        for row in ordered
    ]
    reserved_rows = [
        {'advance_id': row['advance_id'], 'claim_id': row['claim_id'], 'reserved_open': row['reserved_open']}
        for row in ordered
    ]
    reserved_total, reserved_consistent = _reserved_total(reserved_rows)
    settlement_rows = [_settlement_row(row) for row in fixture_views]
    refund_rows = [_refund_row(row) for row in fixture_views]
    categories = [
        {
            'id': 'approved',
            'source': 'SIMULATED',
            'total': sum(row['amount'] for row in approved_rows),
            'rows': approved_rows,
        },
        {
            'id': 'exposure',
            'source': 'SIMULATED',
            'drawn': sum(row['drawn'] for row in exposure_rows),
            'repaid': sum(row['repaid'] for row in exposure_rows),
            'outstanding': sum(row['outstanding'] for row in exposure_rows),
            'rows': exposure_rows,
            'case_confirmed_cash_on_face_not_in_fixture_total': True,
        },
        {
            'id': 'reserved',
            'source': 'SIMULATED',
            'total': reserved_total,
            'consistent': reserved_consistent,
            'rows': reserved_rows,
        },
        {
            'id': 'settlement',
            'source': 'READ_ONLY_FIXTURE',
            'confirmed': sum(row['confirmed_cash'] for row in settlement_rows),
            'distributed': sum(row['distributed_cash'] for row in settlement_rows),
            'rows': settlement_rows,
        },
        {
            'id': 'refund',
            'source': 'READ_ONLY_FIXTURE',
            'refund_face': sum(row['refund_face'] for row in refund_rows),
            'refund_accepted': sum(row['refund_accepted'] for row in refund_rows),
            'refund_outstanding': sum(row['refund_outstanding'] for row in refund_rows),
            'rows': refund_rows,
        },
    ]
    return {
        'mode': 'READ_ONLY_STATEMENT',
        'label': 'SIMULATED',
        'diagnostic': 'LOCAL_ONLY',
        'instance_id': instance_id,
        'state_digest': state_digest,
        'cut': state_digest,
        'fixtures_digest': fixtures_digest,
        'operation_capacity': operation_capacity,
        'scope': {
            'cut': state_digest,
            'state_digest': state_digest,
            'fixtures_digest': fixtures_digest,
            'operation_capacity': operation_capacity,
            'capacity_bound': operation_capacity,
            'source_cut': 'NOT_BOUND',
            'completeness': 'NOT_BOUND',
        },
        'categories': categories,
        'not_bound': [
            {'id': gap_id, 'status': 'NOT_BOUND', 'meaning': meaning} for gap_id, meaning in SALES_GAPS
        ],
        'sales_combined': False,
        'primary_and_resale': 'NOT_SUMMED',
        'funds_executed': False,
        'durable': False,
        'workspace_mutated': False,
        'tax_reporting': 'NOT_BOUND',
        'bank_reconciliation': 'NOT_BOUND',
        'workspace_status': workspace_status,
    }


def _reserved_total(rows):
    by_claim = {}
    for row in rows:
        claim_id = row['claim_id']
        reserved = row['reserved_open']
        if claim_id in by_claim and by_claim[claim_id] != reserved:
            return None, False
        by_claim[claim_id] = reserved
    return sum(by_claim.values()), True


def _settlement_row(view):
    claim = view['claim']
    return {
        'claim_id': claim['claim_id'],
        'phase': view['phase'],
        'confirmed_cash': claim['confirmed_cash'],
        'distributed_cash': claim['distributed_cash'],
    }


def _refund_row(view):
    claim = view['claim']
    return {
        'claim_id': claim['claim_id'],
        'refund_face': claim['refund_face'],
        'refund_accepted': claim['refund_accepted'],
        'refund_outstanding': claim['refund_outstanding'],
    }
