"""Set-off proposal quote: read-only min(exposure, counted beneficiary cash) on the bound view.

The pinned per-step table below is hand-written. It replays the nine F01-F03
scenario fixtures in disposable books and reads the quote on each resulting
claim view; numbers come from the fixture arithmetic, not copied into the
proposal code. Nothing here is an execution: the pinned FSM is never invoked,
no receipt or journal entry is written, and cash under recovery_due is never
counted.
"""
import copy
import json
import re
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from capital.policy import DecisionNoteSettlementPolicy
from capital.ports import SetoffQuotePort
from capital.scenarios import replay_scenarios
from capital.server import make_server
from capital.service import ApiError, CapitalService
from capital.setoff import DecisionNoteSetoff
from capital.terms import DecisionNoteTermsPolicy

ROOT = Path(__file__).resolve().parents[1]
NOTE = ROOT / 'docs' / 'decisions' / 'CAPITAL_FINANCIAL_TERMS.md'
_FENCE = re.compile(r'```capital-decision-v1[ \t]*\n(.*?)```', re.DOTALL)
LABEL = 'simulated overlay — not vendor FSM arithmetic, not an offer'
ORDER = ['DEFAULT_INTEREST', 'INTEREST', 'PRINCIPAL']
BENEFICIARY = 'fixture-organizer'
SCENARIO_OUTSTANDING = 60_000


def note_block(text=None):
    raw = _FENCE.findall(NOTE.read_text(encoding='utf-8') if text is None else text)
    if len(raw) != 1:
        raise AssertionError('expected one block')
    return json.loads(raw[0])


def _value(name):
    return note_block()['entries'][name]['value']


def _has_number(value):
    if type(value) is bool:
        return False
    if type(value) is int or type(value) is float:
        return True
    if type(value) is dict:
        return any(_has_number(item) for item in value.values())
    if type(value) is list:
        return any(_has_number(item) for item in value)
    return False


def rewritten_note(**changes):
    """A fresh note text with per-entry status overrides, re-serialized once."""
    block = note_block()
    for name, status in changes.items():
        block['entries'][name]['status'] = status
    return '```capital-decision-v1\n' + json.dumps(block, ensure_ascii=True, indent=2) + '\n```\n'


# Per-step pins of (allocated_krw, recovery_due_krw, base_krw, setoff_amount,
# capped_by, base_reason) for a synthetic DRAWN case with outstanding_exposure
# 60000 bound to each replayed claim. The counted lines are the beneficiary-
# mapped class-2 (COUNTERPARTY_PROCEEDS) payee lines of the claim view; the base
# is max(0, distributed - recovery_due) summed over those lines.
ZERO = (0, 0, 0, 0, 'ALLOCATED_CASH', 'ALLOCATION_NOT_OBSERVED')
CAPPED = (92000, 0, 92000, 60000, 'EXPOSURE', 'ALLOCATION_OBSERVED')
ORGANIZER_FIRST = (95000, 0, 95000, 60000, 'EXPOSURE', 'ALLOCATION_OBSERVED')
UNDER_RECOVERY = (92000, 92000, 0, 0, 'ALLOCATED_CASH', 'ALLOCATED_CASH_UNDER_RECOVERY')
HALF_DISTRIBUTED = (43000, 0, 43000, 43000, 'ALLOCATED_CASH', 'ALLOCATION_OBSERVED')
PINNED_STEPS = {
    'shortfall-platform': {1: ZERO, 2: CAPPED, 3: CAPPED, 4: CAPPED},
    'shortfall-organizer': {1: ZERO, 2: ORGANIZER_FIRST},
    'partial-before': {1: ZERO, 2: ZERO, 3: ZERO},
    'partial-after': {1: ZERO, 2: CAPPED, 3: CAPPED, 4: CAPPED},
    'full-after': {
        1: ZERO, 2: CAPPED, 3: UNDER_RECOVERY, 4: UNDER_RECOVERY,
        5: UNDER_RECOVERY, 6: UNDER_RECOVERY, 7: UNDER_RECOVERY,
    },
    'split-refund': {1: ZERO, 2: ZERO, 3: ZERO, 4: ZERO},
    'duplicate-statement': {1: ZERO, 2: ZERO, 3: ZERO, 4: ZERO},
    'late-cash': {1: ZERO, 2: ZERO, 3: ZERO},
    'split-statement': {1: ZERO, 2: HALF_DISTRIBUTED, 3: HALF_DISTRIBUTED, 4: CAPPED},
}
# Steps whose claim carries refund_face > 0, so no interest tier applies and the
# repayment split is NOT_APPLICABLE even though the setoff section still prices.
NO_TIER_STEPS = {
    ('partial-before', 2), ('partial-before', 3),
    ('partial-after', 3), ('partial-after', 4),
    ('full-after', 3), ('full-after', 4), ('full-after', 5), ('full-after', 6), ('full-after', 7),
    ('split-refund', 2), ('split-refund', 3), ('split-refund', 4),
    ('late-cash', 1), ('late-cash', 2), ('late-cash', 3),
}


def scenario_case(claim):
    """Synthetic DRAWN case bound to one replayed claim view."""
    return {
        'advance_id': 'sim-pin',
        'phase': 'DRAWN',
        'amount': SCENARIO_OUTSTANDING,
        'outstanding_exposure': SCENARIO_OUTSTANDING,
        'next_repayment_sequence': 1,
        'beneficiary_role': BENEFICIARY,
        'settlement_id': claim['claim_id'],
    }


class SetoffQuoteTests(unittest.TestCase):
    def setUp(self):
        self.service = CapitalService()
        self.counter = 0

    def command(self, op, case='sim-a', **args):
        self.counter += 1
        return self.service.execute({
            'instance_id': self.service.instance_id,
            'operation_id': f'setoff-{self.counter}',
            'op': op,
            'advance_id': case,
            'args': args,
        })

    def ready(self, case='sim-a', amount=60000, fixture='sim-committed', bound=True, draw=False):
        self.assertEqual(self.command('offer', case, fixture_id=fixture, amount=amount)['outcome'], 'ACCEPTED')
        self.assertEqual(self.command('approve', case)['outcome'], 'ACCEPTED')
        if bound:
            self.assertEqual(self.command('bind_settlement', case)['outcome'], 'ACCEPTED')
        if draw:
            self.assertEqual(self.command('draw', case)['outcome'], 'ACCEPTED')

    def setoff(self, case='sim-a', draw_day=0, as_of_day=0, expected=None):
        return self.service.case_setoff(
            case, self.service.instance_id, draw_day=draw_day, as_of_day=as_of_day,
            expected_settlement_cash_day=expected)

    def frozen_view(self, case='sim-a'):
        view = self.service.machine.view(case)
        return {
            'receipts': copy.deepcopy(self.service.receipts),
            'digest': self.service.machine.state_digest(),
            'count': len(self.service.receipts),
            'journal': self.service.machine.export_journal(),
            'reserved': view['reserved_open'],
        }

    def test_label_authority_and_proposal_flags_echo_the_note(self):
        self.ready(draw=True)
        body = self.setoff(as_of_day=1)
        self.assertEqual(body['label'], LABEL)
        self.assertEqual(body['mode'], 'SIMULATED_OVERLAY')
        self.assertEqual(body['terms_version'], _value('interest_rate') and note_block()['terms_version'])
        self.assertIs(body['provisional'], True)
        self.assertEqual(body['status'], 'BOUND')
        self.assertIs(body['proposal_only'], True)
        self.assertIs(body['applied'], False)
        authority = _value('collateral_execution')['execution_authority']
        self.assertEqual(body['execution_authority'], authority)
        self.assertTrue(authority.startswith('HUMAN_OPERATOR'))
        echo = body['collateral_execution']
        self.assertIs(echo['applied'], False)
        self.assertEqual(echo['primary'], 'SETOFF_AGAINST_BENEFICIARY_SETTLEMENT_DISTRIBUTION')
        self.assertEqual(echo['never'], _value('collateral_execution')['never'])
        self.assertEqual(
            body['recovery_waterfall']['steps'], _value('default_loss_treatment')['recovery_waterfall'])
        self.assertIs(body['recovery_waterfall']['applied'], False)
        self.assertEqual(body['post_default'], 'OVERLAY_RECOVERY_LEDGER_NOT_IN_SCOPE')
        self.assertIs(body['funds_executed'], False)
        self.assertIs(body['workspace_mutated'], False)
        self.assertIs(body['write_authorized'], False)
        self.assertEqual(body['observed_state_digest'], self.service.machine.state_digest())

    def test_zero_allocation_view_returns_zero_and_no_invented_cash(self):
        self.ready(draw=True)
        body = self.setoff(as_of_day=1)
        setoff = body['setoff']
        view = body['settlement_view']
        self.assertEqual(setoff['status'], 'BOUND')
        self.assertEqual(view['status'], 'BOUND')
        self.assertEqual(setoff['outstanding_exposure'], 60000)
        self.assertEqual(setoff['allocated_krw'], 0)
        self.assertEqual(setoff['recovery_due_krw'], 0)
        self.assertEqual(setoff['base_krw'], 0)
        self.assertEqual(setoff['setoff_amount'], 0)
        self.assertEqual(setoff['base_reason'], 'ALLOCATION_NOT_OBSERVED')
        self.assertIs(view['recovery_due_excluded'], True)
        by_payee = {line['payee']: line for line in view['lines']}
        self.assertIs(by_payee['organizer']['counted'], True)
        self.assertIs(by_payee['organizer']['beneficiary_mapped'], True)
        self.assertEqual(by_payee['organizer']['class'], 2)
        self.assertIs(by_payee['platform']['counted'], False)
        for line in view['lines']:
            self.assertEqual(line['eligible_krw'], 0)
        # cash=0 splits to nothing and carries no fsm_repay
        self.assertEqual(body['allocation']['order'], ORDER)
        self.assertEqual(body['allocation']['to_principal'], 0)
        self.assertIsNone(body['fsm_repay'])
        self.assertIs(body['close_ready'], False)

    def test_unbound_and_captured_claims_carry_no_numeric_quote(self):
        self.ready(bound=False, draw=True)
        body = self.setoff(as_of_day=1)
        self.assertEqual(body['settlement_view'], {'status': 'NOT_APPLICABLE', 'reason': 'settlement not bound'})
        self.assertEqual(body['setoff'], {'status': 'NOT_APPLICABLE', 'reason': 'settlement not bound'})
        self.assertIsNone(body['fsm_repay'])
        self.assertIs(body['close_ready'], False)

        self.ready(case='sim-b', fixture='sim-pending')
        pending = self.setoff(case='sim-b', as_of_day=1)
        self.assertEqual(pending['settlement_view']['status'], 'BOUND')
        self.assertEqual(pending['settlement_view']['claim_id'], 'sim-pending')
        self.assertEqual(pending['settlement_view']['confirmed_cash'], 0)
        self.assertEqual(pending['setoff']['allocated_krw'], 0)
        self.assertEqual(pending['setoff']['setoff_amount'], 0)
        self.assertEqual(pending['setoff']['base_reason'], 'ALLOCATION_NOT_OBSERVED')
        self.assertIsNone(pending['fsm_repay'])

    def test_replayed_scenario_steps_match_hand_written_pins(self):
        setoff = DecisionNoteSetoff(DecisionNoteTermsPolicy(), DecisionNoteSettlementPolicy())
        results = replay_scenarios()
        self.assertEqual(sorted(results), sorted(PINNED_STEPS))
        for scenario_id, scenario in results.items():
            pins = PINNED_STEPS[scenario_id]
            self.assertEqual(
                [step['ordinal'] for step in scenario['steps']], sorted(pins), scenario_id)
            for step in scenario['steps']:
                claim = step['view']
                body = setoff.proposal(
                    scenario_case(claim), claim, draw_day=0, as_of_day=1,
                    expected_settlement_cash_day=None, gate='MOCK_COMMIT_OBSERVED')
                where = f'{scenario_id} step {step["ordinal"]}'
                self.assertEqual(body['label'], LABEL, where)
                self.assertEqual(body['mode'], 'SIMULATED_OVERLAY', where)
                self.assertIs(body['proposal_only'], True, where)
                self.assertIs(body['applied'], False, where)
                self.assertEqual(body['settlement_view']['status'], 'BOUND', where)
                self.assertEqual(body['settlement_view']['claim_id'], claim['claim_id'], where)
                section = body['setoff']
                self.assertEqual(section['status'], 'BOUND', where)
                allocated, recovery, base, amount, capped_by, reason = pins[step['ordinal']]
                self.assertEqual(section['allocated_krw'], allocated, where)
                self.assertEqual(section['recovery_due_krw'], recovery, where)
                self.assertEqual(section['base_krw'], base, where)
                self.assertEqual(section['setoff_amount'], amount, where)
                self.assertEqual(section['capped_by'], capped_by, where)
                self.assertEqual(section['base_reason'], reason, where)
                self.assertEqual(section['setoff_amount'], min(SCENARIO_OUTSTANDING, base), where)
                self.assertEqual(section['route'], 'FSM_REPAY', where)
                counted = [line for line in body['settlement_view']['lines'] if line['counted']]
                self.assertEqual(allocated, sum(line['distributed'] for line in counted), where)
                self.assertEqual(recovery, sum(line['recovery_due'] for line in counted), where)
                self.assertEqual(base, sum(line['eligible_krw'] for line in counted), where)
                for line in body['settlement_view']['lines']:
                    if line['beneficiary_mapped'] and line['class'] == 2:
                        self.assertIs(line['counted'], True, where)
                    else:
                        self.assertIs(line['counted'], False, where)
                        self.assertEqual(line['eligible_krw'], 0, where)
                split = body['allocation']
                if (scenario_id, step['ordinal']) in NO_TIER_STEPS:
                    self.assertEqual(body['tier'], 'NOT_APPLICABLE', where)
                    self.assertEqual(split['status'], 'NOT_APPLICABLE', where)
                    self.assertIsNone(body['fsm_repay'], where)
                    continue
                self.assertEqual(split['order'], ORDER, where)
                due = split['to_default_interest'] + split['to_interest'] + split['to_principal']
                self.assertLessEqual(due, amount, where)
                if split['to_principal'] > 0:
                    # fsm_repay carries the principal portion only, never the dues.
                    self.assertEqual(
                        body['fsm_repay'], {'amount': split['to_principal'], 'sequence': 1}, where)
                    self.assertLess(
                        body['fsm_repay']['amount'] + split['to_interest']
                        + split['to_default_interest'], amount + 1, where)
                else:
                    self.assertIsNone(body['fsm_repay'], where)
        # A positive set-off is quoted only where the replay actually distributed cash.
        self.assertTrue(any(pins[o][0] > 0 for pins in PINNED_STEPS.values() for o in pins))
        self.assertTrue(any(pins[o][1] > 0 for pins in PINNED_STEPS.values() for o in pins))

    def test_quote_leaves_receipts_journal_digest_and_reservation_unchanged(self):
        self.ready(draw=True)
        before = self.frozen_view()
        for as_of_day in (0, 1, 30, 999):
            body = self.setoff(as_of_day=as_of_day)
            self.assertEqual(body['observed_state_digest'], before['digest'])
        self.assertEqual(self.frozen_view(), before)
        self.assertEqual(self.service.machine.view('sim-a')['repayments'], [])

    def test_missing_note_is_not_bound_with_no_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = CapitalService(terms=DecisionNoteTermsPolicy(Path(tmp) / 'missing.md'))
            service.execute({
                'instance_id': service.instance_id, 'operation_id': 'offer', 'op': 'offer',
                'advance_id': 'sim-a', 'args': {'fixture_id': 'sim-committed', 'amount': 1000},
            })
            before = (copy.deepcopy(service.receipts), service.machine.state_digest(), len(service.receipts))
            body = service.case_setoff('sim-a', service.instance_id, draw_day=0, as_of_day=1)
            self.assertEqual(body['status'], 'NOT_BOUND')
            self.assertEqual(body['reason'], 'terms not bound')
            self.assertEqual(body['label'], LABEL)
            self.assertEqual(body['setoff']['status'], 'NOT_BOUND')
            self.assertEqual(body['settlement_view']['status'], 'NOT_BOUND')
            self.assertEqual(body['allocation']['status'], 'NOT_BOUND')
            self.assertIsNone(body['fsm_repay'])
            self.assertIsNone(body['execution_authority'])
            self.assertIs(body['proposal_only'], True)
            self.assertIs(body['close_ready'], False)
            self.assertNotIn('principal', body)
            self.assertNotIn('tier', body)
            self.assertFalse(_has_number(body))
            self.assertEqual(
                (service.receipts, service.machine.state_digest(), len(service.receipts)), before)
            with self.assertRaises(ApiError) as caught:
                service.case_setoff('sim-missing', service.instance_id, draw_day=0, as_of_day=0)
            self.assertEqual(caught.exception.status, 404)

    def test_partial_and_dropped_entries_fail_closed(self):
        text = NOTE.read_text(encoding='utf-8')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # First ADOPTED entry is interest_rate: the overlay is PARTIAL and the
            # split cannot price while the setoff section still reads the view.
            partial = root / 'partial.md'
            partial.write_text(text.replace('"status": "ADOPTED"', '"status": "UNDETERMINED"', 1), encoding='utf-8')
            # Without the ADOPTED collateral_execution entry there is no decided
            # primary step, so the quote refuses to price at all.
            no_step = root / 'no-step.md'
            no_step.write_text(rewritten_note(collateral_execution='UNDETERMINED'), encoding='utf-8')
            # Without the ADOPTED margin entry there is no beneficiary payee map.
            no_margin = root / 'no-margin.md'
            no_margin.write_text(rewritten_note(additional_margin='UNDETERMINED'), encoding='utf-8')
            for name, (path, top) in {
                'partial': (partial, 'PARTIAL'),
                'no-step': (no_step, 'PARTIAL'),
                'no-margin': (no_margin, 'PARTIAL'),
            }.items():
                service = CapitalService(terms=DecisionNoteTermsPolicy(path))
                for op, args in (
                    ('offer', {'fixture_id': 'sim-committed', 'amount': 60000}),
                    ('approve', {}), ('bind_settlement', {}), ('draw', {}),
                ):
                    self.assertEqual(service.execute({
                        'instance_id': service.instance_id, 'operation_id': f'sim-{name}-{op.replace("_", "-")}',
                        'op': op, 'advance_id': 'sim-a', 'args': args,
                    })['outcome'], 'ACCEPTED', name)
                body = service.case_setoff('sim-a', service.instance_id, draw_day=0, as_of_day=1)
                self.assertEqual(body['status'], top, name)
                self.assertIs(body['proposal_only'], True, name)
                if name == 'partial':
                    self.assertEqual(body['setoff']['status'], 'BOUND', name)
                    self.assertEqual(body['setoff']['setoff_amount'], 0, name)
                    self.assertEqual(body['allocation']['status'], 'NOT_BOUND', name)
                else:
                    self.assertEqual(body['setoff']['status'], 'NOT_BOUND', name)
                    self.assertEqual(body['setoff']['reason'], 'terms not bound', name)
                    self.assertEqual(body['settlement_view']['status'], 'NOT_BOUND', name)
                    if name == 'no-step':
                        self.assertIsNone(body['execution_authority'], name)
                    else:
                        self.assertEqual(
                            body['execution_authority'],
                            _value('collateral_execution')['execution_authority'], name)
                self.assertIsNone(body['fsm_repay'], name)
                self.assertIs(body['close_ready'], False, name)

    def test_missing_policy_note_stays_not_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = CapitalService(policy=DecisionNoteSettlementPolicy(Path(tmp) / 'missing.md'))
            for op, args in (
                ('offer', {'fixture_id': 'sim-committed', 'amount': 60000}),
                ('approve', {}), ('bind_settlement', {}), ('draw', {}),
            ):
                self.assertEqual(service.execute({
                    'instance_id': service.instance_id, 'operation_id': f'sim-np-{op.replace("_", "-")}',
                    'op': op, 'advance_id': 'sim-a', 'args': args,
                })['outcome'], 'ACCEPTED')
            body = service.case_setoff('sim-a', service.instance_id, draw_day=0, as_of_day=1)
            self.assertEqual(body['status'], 'BOUND')
            self.assertEqual(body['settlement_view'], {'status': 'NOT_BOUND', 'reason': 'policy not bound'})
            self.assertEqual(body['setoff'], {'status': 'NOT_BOUND', 'reason': 'policy not bound'})
            self.assertIsNone(body['fsm_repay'])

    def test_service_argument_guards(self):
        self.ready(draw=True)
        instance = self.service.instance_id
        for kwargs, code in (
            ({'draw_day': -1}, 'INVALID_ARGUMENTS'),
            ({'as_of_day': 1000000}, 'INVALID_ARGUMENTS'),
            ({'expected': 9999999}, 'INVALID_ARGUMENTS'),
        ):
            with self.assertRaises(ApiError) as caught:
                self.service.case_setoff(
                    'sim-a', instance, draw_day=kwargs.get('draw_day', 0),
                    as_of_day=kwargs.get('as_of_day', 1),
                    expected_settlement_cash_day=kwargs.get('expected'))
            self.assertEqual(caught.exception.code, code, kwargs)
        with self.assertRaises(ApiError) as caught:
            self.service.case_setoff('sim-a', 'other', draw_day=0, as_of_day=1)
        self.assertEqual(caught.exception.code, 'SESSION_CHANGED')
        self.assertEqual(caught.exception.status, 409)
        with self.assertRaises(ApiError) as caught:
            self.service.case_setoff('sim-missing', instance, draw_day=0, as_of_day=1)
        self.assertEqual(caught.exception.code, 'UNKNOWN_ADVANCE')


class SetoffHttpTests(unittest.TestCase):
    def test_route_permission_and_invariants(self):
        server = make_server(0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            service = server.service
            authorizer = server.authorizer
            auditor = authorizer.bind_role('auditor')
            observer = authorizer.bind_role('observer')

            counter = [0]

            def run(op, args):
                counter[0] += 1
                return service.execute({
                    'instance_id': service.instance_id, 'operation_id': f'setoff-http-{counter[0]}',
                    'op': op, 'advance_id': 'sim-a', 'args': args,
                })

            self.assertEqual(run('offer', {'fixture_id': 'sim-committed', 'amount': 60000})['outcome'], 'ACCEPTED')
            self.assertEqual(run('approve', {})['outcome'], 'ACCEPTED')
            self.assertEqual(run('bind_settlement', {})['outcome'], 'ACCEPTED')
            self.assertEqual(run('draw', {})['outcome'], 'ACCEPTED')
            before = (
                copy.deepcopy(service.receipts), service.machine.state_digest(), len(service.receipts),
                service.machine.view('sim-a')['reserved_open'], len(service.machine.export_journal()),
            )
            instance = service.instance_id

            def get(path, token):
                client = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                client.request('GET', path, headers={'X-Capital-Token': token})
                response = client.getresponse()
                payload = json.loads(response.read().decode())
                status = response.status
                client.close()
                return status, payload

            code, body = get(
                f'/api/terms/sim-a/setoff?instance_id={instance}&as_of_day=30', auditor)
            self.assertEqual(code, 200, body)
            self.assertEqual(body['label'], LABEL)
            self.assertEqual(body['mode'], 'SIMULATED_OVERLAY')
            self.assertEqual(body['advance_id'], 'sim-a')
            self.assertIs(body['proposal_only'], True)
            self.assertIs(body['applied'], False)
            self.assertIs(body['funds_executed'], False)
            self.assertIs(body['workspace_mutated'], False)
            self.assertIs(body['write_authorized'], False)
            self.assertEqual(body['observed_state_digest'], service.machine.state_digest())
            after = (
                service.receipts, service.machine.state_digest(), len(service.receipts),
                service.machine.view('sim-a')['reserved_open'], len(service.machine.export_journal()),
            )
            self.assertEqual(after, before)

            code, denied = get(
                f'/api/terms/sim-a/setoff?instance_id={instance}&as_of_day=30', observer)
            self.assertEqual(code, 403)
            self.assertEqual(denied['error'], 'ROLE_FORBIDDEN')
            self.assertEqual(denied['role'], 'observer')
            self.assertEqual(denied['permission'], 'projection:read')
            self.assertEqual(
                (service.receipts, service.machine.state_digest(), len(service.receipts),
                 service.machine.view('sim-a')['reserved_open'], len(service.machine.export_journal())),
                before)

            code, missing = get(
                f'/api/terms/sim-missing/setoff?instance_id={instance}&as_of_day=0', auditor)
            self.assertEqual(code, 404)
            self.assertEqual(missing['error'], 'UNKNOWN_ADVANCE')
            code, changed = get(
                '/api/terms/sim-a/setoff?instance_id=other&as_of_day=0', auditor)
            self.assertEqual(code, 409)
            self.assertEqual(changed['error'], 'SESSION_CHANGED')
            for path in (
                f'/api/terms/sim-a/setoff?instance_id={instance}',
                f'/api/terms/sim-a/setoff?instance_id={instance}&as_of_day=-1',
                f'/api/terms/sim-a/setoff?instance_id={instance}&as_of_day=01',
                f'/api/terms/sim-a/setoff?instance_id={instance}&as_of_day=abc',
                f'/api/terms/sim-a/setoff?instance_id={instance}&as_of_day=1&as_of_day=2',
                f'/api/terms/sim-a/setoff?instance_id={instance}&as_of_day=1&draw_day=01',
            ):
                code, bad = get(path, auditor)
                self.assertEqual(code, 400, path)
                self.assertEqual(bad['error'], 'INVALID_ARGUMENTS', path)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

    def test_port_exposes_the_proposal_method(self):
        self.assertIsInstance(CapitalService().setoff, SetoffQuotePort)


if __name__ == '__main__':
    unittest.main()
