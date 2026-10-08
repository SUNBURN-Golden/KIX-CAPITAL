"""Read-only replay of existing F01-F03 test policies in disposable books.

No input changes the workspace. These are comparison fixtures, not policy defaults.
"""
from __future__ import annotations

import copy

from capital.protocol import MockSettlement, SettlementError

POLICY = {'kind': 'PRIMARY_FEE_BPS', 'fee_bps': 500,
          'residual_payee': 'organizer', 'fee_payee': 'platform'}
STATEMENT = {'movement_id': 'sim-move-1', 'gross': 100_000, 'amount': 97_000,
             'fee': 3_000, 'tax': 0, 'held': 0, 'adjustment': 0}
ORDER = ['platform', 'organizer']


def public_invariants(view):
    """Independent read checks, not an economic writer or legal classification."""
    rows = view['obligations']
    checks = {
        'GROSS_EQUALS_OBLIGATION_FACES': sum(row['face'] for row in rows) == view['gross'],
        'OBLIGATION_CONSERVATION': all(row['face'] == row['distributed'] + row['cancelled_unpaid'] + row['outstanding'] for row in rows),
        'CASH_ALLOCATION_CONSERVATION': view['confirmed_cash'] == view['distributed_cash'] + view['undistributed_cash'],
        'REFUND_ACCEPTANCE_CONSERVATION': view['refund_face'] == view['refund_accepted'] + view['refund_outstanding'],
        'NO_REAL_EFFECT': all(view[key] is False for key in ('funds_executed', 'bank_debit_observed', 'right_cancelled', 'external_return_closed', 'legal_debtor_bound', 'admission_granted')),
    }
    return [{'predicate': key, 'matched': value} for key, value in checks.items()]


def step(op, label, args, error=None):
    return {'op': op, 'label': label, 'args': args, 'expected_error': error}


def refund(amount=40_000, refund_id='sim-refund-1'):
    return {'refund_id': refund_id, 'amount': amount, 'beneficiary_role': 'fixture-buyer', 'reason': 'SYNTHETIC_SCENARIO'}


def definitions():
    observe = step('observe_settlement_statement', '목 정산 명세서: 현금 97,000 · 비현금 3,000', STATEMENT)
    distribute = step('apply_distribution', '플랫폼 먼저 배정하는 시험 순서', {'order': ORDER})
    partial = step('bind_refund', '부분 환불 의무 40,000', refund())
    full = step('bind_refund', '한 번의 전액 환불 fixture 재분류', refund(100_000))
    return [
        ('shortfall-platform', '부족 현금 · 플랫폼 우선 fixture',
         '같은 97,000을 배정해도 시험 순서에 따라 미배정 의무의 주체가 달라집니다. 운영 우선순위는 미정입니다.',
         [observe, distribute, step('apply_distribution', '같은 순서 반복: 추가 배정 없음', {'order': ORDER}),
          step('apply_distribution', '이미 고정된 순서 변경 거절', {'order': list(reversed(ORDER))}, 'DISTRIBUTION_ORDER_FROZEN')]),
        ('shortfall-organizer', '부족 현금 · 주최자 우선 fixture',
         '반대 순서와 비교할 수 있는 독립 fixture입니다. 어느 순서도 제품 기본 정책으로 채택하지 않습니다.',
         [observe, step('apply_distribution', '주최자 먼저 배정하는 시험 순서', {'order': list(reversed(ORDER))})]),
        ('partial-before', '배정 전 부분 환불',
         '환불 부담자가 미정이면 추가 배정을 멈춥니다. 수취인 액면이나 회수 의무를 자동 변경하지 않습니다.',
         [observe, partial, step('apply_distribution', '부담 미정으로 배정 거절', {'order': ORDER}, 'DISTRIBUTION_BLOCKED_REFUND_BEARER_UNDEFINED')]),
        ('partial-after', '배정 후 부분 환불',
         '이미 배정된 97,000은 되돌리지 않습니다. 부분 환불이 자동 환수·상계 권한을 만들지 않습니다.',
         [observe, distribute, partial, step('apply_distribution', '추가 배정 거절', {'order': ORDER}, 'DISTRIBUTION_BLOCKED_REFUND_BEARER_UNDEFINED')]),
        ('full-after', '배정 후 전액 취소 · 회수 의무',
         '전액 fixture 재분류는 회수 의무만 표시합니다. 목 취소 수락으로 환불 미이행이 0이 되어도 은행 반환은 종결되지 않습니다.',
         [observe, distribute, full,
          step('observe_mock_cancel_acceptance', '목 취소 수락 40,000', {'source_id': 'sim-accept-1', 'amount': 40_000}),
          step('observe_mock_cancel_acceptance', '같은 수락 중복: 한 번만 반영', {'source_id': 'sim-accept-1', 'amount': 40_000}),
          step('observe_mock_cancel_acceptance', '나머지 목 취소 수락 60,000', {'source_id': 'sim-accept-2', 'amount': 60_000}),
          step('observe_mock_cancel_acceptance', '초과 수락 거절', {'source_id': 'sim-accept-3', 'amount': 1}, 'REFUND_ACCEPTANCE_EXCEEDS_OBLIGATION')]),
        ('split-refund', '부분 환불 합계가 전액이 된 경우',
         '40,000 + 60,000은 한 번의 전액 fixture와 다른 이력입니다. 자동으로 전액 재분류하지 않습니다.',
         [observe, partial, step('bind_refund', '나머지 환불 의무 60,000', refund(60_000, 'sim-refund-2')),
          step('apply_distribution', '부담 미정 유지 · 배정 거절', {'order': ORDER}, 'DISTRIBUTION_BLOCKED_REFUND_BEARER_UNDEFINED')]),
        ('duplicate-statement', '정산 관측 중복·상충',
         '동일 movement와 동일 내용은 한 번만 반영하고, 다른 구성 금액은 거절합니다. 차액을 임의의 수수료로 채우지 않습니다.',
         [observe, observe,
          step('observe_settlement_statement', '같은 movement의 다른 구성 거절', {**STATEMENT, 'amount': 96_000, 'fee': 4_000}, 'STATEMENT_BINDING_CONFLICT'),
          step('observe_settlement_statement', '구성 합계 불일치 거절', {**STATEMENT, 'movement_id': 'sim-bad', 'fee': 2_000}, 'SETTLEMENT_COMPONENT_MISMATCH')]),
        ('late-cash', '전액 재분류 뒤 늦은 현금',
         '취소된 의무를 늦은 현금으로 다시 배정하지 않습니다. 현금은 미배정으로 남고 자동 송금하지 않습니다.',
         [full, step('observe_settlement_statement', '늦게 도착한 합성 현금 100,000', {**STATEMENT, 'amount': 100_000, 'fee': 0}), distribute]),
        ('split-statement', '부분 정산 후 추가 현금',
         '목 명세서 두 건을 구분하고 첫 배정 순서를 유지합니다. 이전 배정에 같은 현금을 다시 더하지 않습니다.',
         [step('observe_settlement_statement', '첫 합성 명세서 50,000', {**STATEMENT, 'gross': 50_000, 'amount': 48_000, 'fee': 2_000}), distribute,
          step('observe_settlement_statement', '두 번째 합성 명세서 50,000', {**STATEMENT, 'movement_id': 'sim-move-2', 'gross': 50_000, 'amount': 49_000, 'fee': 1_000}), distribute]),
    ]


def replay_scenarios():
    results = {}
    for scenario_id, title, description, commands in definitions():
        book = MockSettlement()
        claim_id = 'sim-lab-' + scenario_id
        book.recognize_claim(claim_id, trade_id='sim-lab-trade', gross=100_000,
                             debtor_role='fixture-merchant', policy=POLICY)
        initial = book.view(claim_id)
        history = []
        for ordinal, command in enumerate(commands, 1):
            before = book.view(claim_id)
            error, output = None, None
            try:
                output = getattr(book, command['op'])(claim_id, **copy.deepcopy(command['args']))
            except SettlementError as exc:
                error = exc.code
            after = book.view(claim_id)
            checks = public_invariants(after)
            checks.append({'predicate': 'EXPECTED_CONTRACT_OUTCOME', 'matched': error == command['expected_error']})
            if error:
                checks.append({'predicate': 'REJECTION_PRESERVES_STATE', 'matched': before == after})
            history.append({'ordinal': ordinal, **copy.deepcopy(command),
                            'outcome': 'REJECTED' if error else 'ACCEPTED', 'error': error,
                            'duplicate': bool(output and output['duplicate']),
                            'view': after, 'checks': checks})
        results[scenario_id] = {'id': scenario_id, 'title': title, 'description': description,
                                'initial': initial, 'steps': history, 'final': book.view(claim_id),
                                'all_predicates_matched': all(c['matched'] for s in history for c in s['checks']),
                                'provenance': 'MOCK_SETTLEMENT_ONLY', 'scope': 'DISPOSABLE_READ_ONLY_SCENARIO',
                                'policy_adopted': False, 'funds_executed': False,
                                'workspace_mutated': False, 'external_return_closed': False}
    return results
