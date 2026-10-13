"""Repayment allocation preview: read-only waterfall quote, pinned FSM untouched."""
import copy
import json
import re
import tempfile
import threading
import unittest
from fractions import Fraction
from http.client import HTTPConnection
from pathlib import Path

from capital.ports import TermsPolicyPort
from capital.server import make_server
from capital.service import ApiError, CapitalService
from capital.terms import DecisionNoteTermsPolicy

ROOT = Path(__file__).resolve().parents[1]
NOTE = ROOT / 'docs' / 'decisions' / 'CAPITAL_FINANCIAL_TERMS.md'
_FENCE = re.compile(r'```capital-decision-v1[ \t]*\n(.*?)```', re.DOTALL)
LABEL = 'simulated overlay — not vendor FSM arithmetic, not an offer'
ORDER_NEEDLE = '"repayment_allocation_order": ["DEFAULT_INTEREST", "INTEREST", "PRINCIPAL"]'


def note_block(text=None):
    raw = _FENCE.findall(NOTE.read_text(encoding='utf-8') if text is None else text)
    if len(raw) != 1:
        raise AssertionError('expected one block')
    return json.loads(raw[0])


def _value(name):
    return note_block()['entries'][name]['value']


def _day_count(token):
    match = re.fullmatch(r'ACT_(\d+)_FIXED', token)
    if match is None:
        raise AssertionError(token)
    return int(match.group(1))


def _clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value


def reference_term_days(draw_day, expected):
    term = _value('term')
    if expected is None:
        return term['standard_term_days']
    raw = expected - draw_day + term['settlement_slack_days']
    return _clamp(raw, term['min_term_days'], term['max_term_days'])


def reference_tier(gate, refund_face):
    for tier in _value('interest_rate')['tiers']:
        condition = tier['condition']
        if condition.get('settlement_gate') != gate:
            continue
        if 'refund_face' in condition and condition['refund_face'] != refund_face:
            continue
        return tier
    return None


def reference_interest(principal, draw_day, as_of_day, term_days, tier):
    """Independent recompute: exact contract and default buckets, each floored."""
    interest = _value('interest_rate')
    day_count = _day_count(interest['day_count'])
    elapsed = as_of_day - draw_day
    if elapsed < interest['min_interest_days']:
        elapsed = interest['min_interest_days']
    if elapsed <= term_days:
        contractual_days, default_days = elapsed, 0
    else:
        contractual_days, default_days = term_days, elapsed - term_days
    contract_bps = tier['all_in_bps_annual']
    default_bps = contract_bps + interest['default_interest_add_bps_annual']
    denominator = 10000 * day_count
    contract_exact = Fraction(principal * contractual_days * contract_bps, denominator)
    default_exact = Fraction(principal * default_days * default_bps, denominator)
    return {
        'contractual_days': contractual_days,
        'default_days': default_days,
        'contract_exact': contract_exact,
        'default_exact': default_exact,
        'exact': contract_exact + default_exact,
        'interest_due_krw': contract_exact.numerator // contract_exact.denominator,
        'default_interest_due_krw': default_exact.numerator // default_exact.denominator,
    }


def reference_split(order, dues, cash):
    applied = {token: 0 for token in dues}
    remaining = dict(dues)
    left = cash
    for token in order:
        pay = min(left, remaining[token])
        applied[token] += pay
        remaining[token] -= pay
        left -= pay
    return applied, remaining, left


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


class RepayAllocationTests(unittest.TestCase):
    def setUp(self):
        self.service = CapitalService()
        self.counter = 0

    def command(self, op, case='sim-a', **args):
        self.counter += 1
        return self.service.execute({
            'instance_id': self.service.instance_id,
            'operation_id': f'alloc-{self.counter}',
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

    def allocation(self, case='sim-a', draw_day=0, as_of_day=0, cash=0, expected=None):
        return self.service.case_allocation(
            case, self.service.instance_id, draw_day=draw_day, as_of_day=as_of_day,
            cash=cash, expected_settlement_cash_day=expected)

    def frozen_view(self, case='sim-a'):
        view = self.service.machine.view(case)
        return {
            'receipts': copy.deepcopy(self.service.receipts),
            'digest': self.service.machine.state_digest(),
            'count': len(self.service.receipts),
            'journal': self.service.machine.export_journal(),
            'reserved': view['reserved_open'],
        }

    def test_golden_vector_contract_interest_floor_and_carried_remainder(self):
        interest = _value('interest_rate')
        day_count = _day_count(interest['day_count'])
        t1 = reference_tier('MOCK_COMMIT_OBSERVED', 0)
        term_days = reference_term_days(0, None)
        self.ready(draw=True)
        one_day = self.allocation(as_of_day=1, cash=0)
        ref1 = reference_interest(60000, 0, 1, term_days, t1)
        self.assertEqual(one_day['interest']['contract_exact'], f'{ref1["contract_exact"].numerator}/{ref1["contract_exact"].denominator}')
        self.assertEqual(one_day['interest']['interest_due_krw'], ref1['interest_due_krw'])
        self.assertEqual(one_day['interest']['default_interest_due_krw'], 0)
        if t1['all_in_bps_annual'] == 700 and day_count == 365:
            self.assertEqual(one_day['interest']['contract_exact'], '840/73')
            self.assertEqual(one_day['interest']['interest_due_krw'], 11)
        two_day = self.allocation(as_of_day=2, cash=0)
        ref2 = reference_interest(60000, 0, 2, term_days, t1)
        self.assertEqual(two_day['interest']['exact'], f'{ref2["exact"].numerator}/{ref2["exact"].denominator}')
        self.assertEqual(two_day['interest']['interest_due_krw'], ref2['interest_due_krw'])
        # The unposted remainder is carried: the later quote is the floor of the
        # full-window rational, not the sum of two floored one-day postings.
        self.assertEqual(
            two_day['interest']['interest_due_krw'],
            (ref1['contract_exact'] * 2).numerator // (ref1['contract_exact'] * 2).denominator)
        self.assertGreater(two_day['interest']['interest_due_krw'], 2 * one_day['interest']['interest_due_krw'])

    def test_cash_splits_in_the_decided_order_and_fsm_repay_is_principal_only(self):
        t1 = reference_tier('MOCK_COMMIT_OBSERVED', 0)
        term_days = reference_term_days(0, None)
        dues = reference_interest(60000, 0, 1, term_days, t1)
        due = dues['interest_due_krw']
        self.assertGreater(due, 0)
        order = _value('interest_rate')['repayment_allocation_order']
        self.assertEqual(order, ['DEFAULT_INTEREST', 'INTEREST', 'PRINCIPAL'])
        self.ready(draw=True)
        view = self.service.machine.view('sim-a')
        self.assertEqual(view['phase'], 'DRAWN')

        zero = self.allocation(as_of_day=1, cash=0)
        self.assertEqual(zero['allocation']['order'], order)
        self.assertEqual(zero['allocation']['to_default_interest'], 0)
        self.assertEqual(zero['allocation']['to_interest'], 0)
        self.assertEqual(zero['allocation']['to_principal'], 0)
        self.assertEqual(zero['allocation']['unapplied_cash'], 0)
        self.assertIsNone(zero['fsm_repay'])
        self.assertIs(zero['close_ready'], False)

        partial = self.allocation(as_of_day=1, cash=due - 1)
        self.assertEqual(partial['allocation']['to_interest'], due - 1)
        self.assertEqual(partial['allocation']['to_principal'], 0)
        self.assertEqual(partial['allocation']['remaining']['interest_due'], 1)
        self.assertIsNone(partial['fsm_repay'])
        self.assertIs(partial['close_ready'], False)

        exact_interest = self.allocation(as_of_day=1, cash=due)
        self.assertEqual(exact_interest['allocation']['to_interest'], due)
        self.assertEqual(exact_interest['allocation']['to_principal'], 0)
        self.assertIsNone(exact_interest['fsm_repay'])
        self.assertIs(exact_interest['close_ready'], False)

        with_principal = self.allocation(as_of_day=1, cash=due + 20000)
        self.assertEqual(with_principal['allocation']['to_interest'], due)
        self.assertEqual(with_principal['allocation']['to_principal'], 20000)
        self.assertEqual(with_principal['allocation']['remaining']['principal_outstanding'], 40000)
        self.assertEqual(
            with_principal['fsm_repay'],
            {'amount': 20000, 'sequence': view['next_repayment_sequence']})
        self.assertIs(with_principal['close_ready'], False)

        overflow = self.allocation(as_of_day=1, cash=due + 60000 + 7)
        self.assertEqual(overflow['allocation']['to_default_interest'], 0)
        self.assertEqual(overflow['allocation']['to_interest'], due)
        self.assertEqual(overflow['allocation']['to_principal'], 60000)
        self.assertEqual(overflow['allocation']['unapplied_cash'], 7)
        self.assertEqual(overflow['fsm_repay']['amount'], 60000)
        self.assertIs(overflow['close_ready'], True)

    def test_past_maturity_accrues_default_interest_and_close_readiness(self):
        interest = _value('interest_rate')
        t1 = reference_tier('MOCK_COMMIT_OBSERVED', 0)
        term_days = reference_term_days(0, None)
        maturity = term_days
        as_of = maturity + 5
        dues = reference_interest(60000, 0, as_of, term_days, t1)
        self.assertEqual(dues['default_days'], 5)
        default_bps = t1['all_in_bps_annual'] + interest['default_interest_add_bps_annual']
        self.assertEqual(default_bps, t1['all_in_bps_annual'] + 300)
        self.ready(draw=True)

        body = self.allocation(as_of_day=as_of, cash=0)
        self.assertEqual(body['interest']['maturity_day'], maturity)
        self.assertEqual(body['interest']['contractual_days'], dues['contractual_days'])
        self.assertEqual(body['interest']['default_days'], dues['default_days'])
        self.assertEqual(body['interest']['default_exact'], f'{dues["default_exact"].numerator}/{dues["default_exact"].denominator}')
        self.assertEqual(body['interest']['default_interest_due_krw'], dues['default_interest_due_krw'])
        self.assertEqual(body['interest']['interest_due_krw'], dues['interest_due_krw'])
        total_due = dues['interest_due_krw'] + dues['default_interest_due_krw'] + 60000

        # The waterfall pays default interest before contract interest.
        short = self.allocation(as_of_day=as_of, cash=dues['default_interest_due_krw'])
        self.assertEqual(short['allocation']['to_default_interest'], dues['default_interest_due_krw'])
        self.assertEqual(short['allocation']['to_interest'], 0)
        self.assertIsNone(short['fsm_repay'])
        self.assertIs(short['close_ready'], False)

        dues_only = self.allocation(as_of_day=as_of, cash=dues['default_interest_due_krw'] + dues['interest_due_krw'])
        self.assertEqual(dues_only['allocation']['to_principal'], 0)
        self.assertIsNone(dues_only['fsm_repay'])
        self.assertIs(dues_only['close_ready'], False)
        self.assertEqual(dues_only['allocation']['remaining']['principal_outstanding'], 60000)

        full = self.allocation(as_of_day=as_of, cash=total_due)
        applied = full['allocation']
        self.assertEqual(applied['to_default_interest'], dues['default_interest_due_krw'])
        self.assertEqual(applied['to_interest'], dues['interest_due_krw'])
        self.assertEqual(applied['to_principal'], 60000)
        self.assertEqual(applied['unapplied_cash'], 0)
        self.assertEqual(
            applied['remaining'],
            {'default_interest_due': 0, 'interest_due': 0, 'principal_outstanding': 0})
        self.assertEqual(full['fsm_repay'], {'amount': 60000, 'sequence': 1})
        self.assertIs(full['close_ready'], True)

        # A settlement-linked term shifts maturity and therefore the split.
        linked_days = reference_term_days(0, 30)
        linked_as_of = linked_days + 3
        linked = self.allocation(as_of_day=linked_as_of, cash=0, expected=30)
        linked_dues = reference_interest(60000, 0, linked_as_of, linked_days, t1)
        self.assertEqual(linked['interest']['term_days'], linked_days)
        self.assertEqual(linked['interest']['default_days'], linked_dues['default_days'])
        self.assertEqual(linked['interest']['default_interest_due_krw'], linked_dues['default_interest_due_krw'])

    def test_non_drawn_phases_and_unmatched_tier_stay_applicable_or_unbound(self):
        self.ready(draw=False)
        approved = self.allocation(as_of_day=10, cash=5000)
        self.assertEqual(approved['status'], 'BOUND')
        self.assertEqual(approved['interest']['status'], 'BOUND')
        self.assertIs(approved['close_ready'], False)
        self.assertIsNone(approved['fsm_repay'])
        self.assertEqual(self.command('draw')['outcome'], 'ACCEPTED')
        self.assertEqual(self.command('repay', amount=60000, sequence=1)['outcome'], 'ACCEPTED')
        zero_outstanding = self.allocation(as_of_day=10, cash=5000)
        self.assertIsNone(zero_outstanding['fsm_repay'])

        refund_case = {
            'phase': 'DRAWN', 'amount': 1000, 'outstanding_exposure': 1000,
            'next_repayment_sequence': 1, 'settlement_gate': 'MOCK_COMMIT_OBSERVED',
        }
        refund_claim = self.service.fixtures.view('sim-refund')['claim']
        no_tier = self.service.terms.allocation(
            refund_case, refund_claim, draw_day=0, as_of_day=1,
            expected_settlement_cash_day=None, gate='MOCK_COMMIT_OBSERVED', cash=100)
        self.assertEqual(no_tier['tier'], 'NOT_APPLICABLE')
        self.assertEqual(no_tier['interest']['status'], 'NOT_APPLICABLE')
        self.assertEqual(no_tier['allocation']['status'], 'NOT_APPLICABLE')
        self.assertIsNone(no_tier['fsm_repay'])
        self.assertIs(no_tier['close_ready'], False)

    def test_missing_note_is_not_bound_with_no_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = CapitalService(terms=DecisionNoteTermsPolicy(Path(tmp) / 'missing.md'))
            service.execute({
                'instance_id': service.instance_id, 'operation_id': 'offer', 'op': 'offer',
                'advance_id': 'sim-a', 'args': {'fixture_id': 'sim-committed', 'amount': 1000},
            })
            before = (copy.deepcopy(service.receipts), service.machine.state_digest(), len(service.receipts))
            body = service.case_allocation(
                'sim-a', service.instance_id, draw_day=0, as_of_day=1, cash=100)
            self.assertEqual(body['status'], 'NOT_BOUND')
            self.assertEqual(body['reason'], 'terms not bound')
            self.assertEqual(body['label'], LABEL)
            self.assertEqual(body['interest']['status'], 'NOT_BOUND')
            self.assertEqual(body['allocation']['status'], 'NOT_BOUND')
            self.assertIsNone(body['fsm_repay'])
            self.assertIs(body['close_ready'], False)
            self.assertNotIn('principal', body)
            self.assertNotIn('tier', body)
            self.assertFalse(_has_number(body))
            self.assertEqual(
                (service.receipts, service.machine.state_digest(), len(service.receipts)), before)
            with self.assertRaises(ApiError) as caught:
                service.case_allocation('sim-missing', service.instance_id, draw_day=0, as_of_day=0, cash=0)
            self.assertEqual(caught.exception.status, 404)

    def test_partial_note_and_bad_order_fail_closed(self):
        text = NOTE.read_text(encoding='utf-8')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            partial = root / 'partial.md'
            partial.write_text(text.replace('"status": "ADOPTED"', '"status": "UNDETERMINED"', 1), encoding='utf-8')
            dropped = root / 'dropped.md'
            self.assertIn(ORDER_NEEDLE, text)
            dropped.write_text(text.replace(',\n        ' + ORDER_NEEDLE, '', 1), encoding='utf-8')
            bad = root / 'bad-order.md'
            bad.write_text(text.replace(ORDER_NEEDLE, '"repayment_allocation_order": ["FEES", "PRINCIPAL"]', 1), encoding='utf-8')
            policies = {
                'partial': (DecisionNoteTermsPolicy(partial), 'PARTIAL', 'NOT_BOUND'),
                'dropped': (DecisionNoteTermsPolicy(dropped), 'BOUND', 'BOUND'),
                'bad': (DecisionNoteTermsPolicy(bad), 'BOUND', 'BOUND'),
            }
            for name, (policy, top, interest_status) in policies.items():
                service = CapitalService(terms=policy)
                service.execute({
                    'instance_id': service.instance_id, 'operation_id': 'offer', 'op': 'offer',
                    'advance_id': 'sim-a', 'args': {'fixture_id': 'sim-committed', 'amount': 60000},
                })
                service.execute({
                    'instance_id': service.instance_id, 'operation_id': 'approve', 'op': 'approve',
                    'advance_id': 'sim-a', 'args': {},
                })
                service.execute({
                    'instance_id': service.instance_id, 'operation_id': 'bind', 'op': 'bind_settlement',
                    'advance_id': 'sim-a', 'args': {},
                })
                service.execute({
                    'instance_id': service.instance_id, 'operation_id': 'draw', 'op': 'draw',
                    'advance_id': 'sim-a', 'args': {},
                })
                body = service.case_allocation(
                    'sim-a', service.instance_id, draw_day=0, as_of_day=1, cash=100)
                self.assertEqual(body['status'], top, name)
                self.assertEqual(body['interest']['status'], interest_status, name)
                self.assertEqual(body['allocation']['status'], 'NOT_BOUND', name)
                self.assertIsNone(body['fsm_repay'], name)
                self.assertIs(body['close_ready'], False, name)

    def test_service_argument_guards(self):
        self.ready(draw=True)
        instance = self.service.instance_id
        for kwargs, code in (
            ({'draw_day': -1}, 'INVALID_ARGUMENTS'),
            ({'as_of_day': 1000000}, 'INVALID_ARGUMENTS'),
            ({'cash': -1}, 'INVALID_ARGUMENTS'),
            ({'cash': 10000000000000}, 'INVALID_ARGUMENTS'),
            ({'expected': 9999999}, 'INVALID_ARGUMENTS'),
        ):
            with self.assertRaises(ApiError) as caught:
                self.service.case_allocation(
                    'sim-a', instance, draw_day=kwargs.get('draw_day', 0),
                    as_of_day=kwargs.get('as_of_day', 1),
                    cash=kwargs.get('cash', 0),
                    expected_settlement_cash_day=kwargs.get('expected'))
            self.assertEqual(caught.exception.code, code, kwargs)
        with self.assertRaises(ApiError) as caught:
            self.service.case_allocation('sim-a', 'other', draw_day=0, as_of_day=1, cash=0)
        self.assertEqual(caught.exception.code, 'SESSION_CHANGED')
        self.assertEqual(caught.exception.status, 409)
        with self.assertRaises(ApiError) as caught:
            self.service.case_allocation('sim-missing', instance, draw_day=0, as_of_day=1, cash=0)
        self.assertEqual(caught.exception.code, 'UNKNOWN_ADVANCE')

    def test_quote_leaves_receipts_journal_digest_and_reservation_unchanged(self):
        self.ready(draw=True)
        before = self.frozen_view()
        for cash in (0, 5, 11, 60011, 9999999999999):
            body = self.allocation(as_of_day=30, cash=cash)
            self.assertEqual(body['observed_state_digest'], before['digest'])
        self.assertEqual(self.frozen_view(), before)
        self.assertEqual(self.service.machine.view('sim-a')['repayments'], [])


class RepayAllocationHttpTests(unittest.TestCase):
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
                    'instance_id': service.instance_id, 'operation_id': f'alloc-http-{counter[0]}',
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
                f'/api/terms/sim-a/allocation?instance_id={instance}&as_of_day=30&cash=50000', auditor)
            self.assertEqual(code, 200, body)
            self.assertEqual(body['label'], LABEL)
            self.assertEqual(body['mode'], 'SIMULATED_OVERLAY')
            self.assertEqual(body['advance_id'], 'sim-a')
            self.assertIs(body['funds_executed'], False)
            self.assertIs(body['workspace_mutated'], False)
            self.assertIs(body['write_authorized'], False)
            after = (
                service.receipts, service.machine.state_digest(), len(service.receipts),
                service.machine.view('sim-a')['reserved_open'], len(service.machine.export_journal()),
            )
            self.assertEqual(after, before)

            code, denied = get(
                f'/api/terms/sim-a/allocation?instance_id={instance}&as_of_day=30&cash=50000', observer)
            self.assertEqual(code, 403)
            self.assertEqual(denied['error'], 'ROLE_FORBIDDEN')
            self.assertEqual(denied['role'], 'observer')
            self.assertEqual(denied['permission'], 'projection:read')
            self.assertEqual(
                (service.receipts, service.machine.state_digest(), len(service.receipts),
                 service.machine.view('sim-a')['reserved_open'], len(service.machine.export_journal())),
                before)

            code, missing = get(
                f'/api/terms/sim-missing/allocation?instance_id={instance}&as_of_day=0&cash=0', auditor)
            self.assertEqual(code, 404)
            self.assertEqual(missing['error'], 'UNKNOWN_ADVANCE')
            code, changed = get(
                '/api/terms/sim-a/allocation?instance_id=other&as_of_day=0&cash=0', auditor)
            self.assertEqual(code, 409)
            self.assertEqual(changed['error'], 'SESSION_CHANGED')
            for path in (
                f'/api/terms/sim-a/allocation?instance_id={instance}&as_of_day=0',
                f'/api/terms/sim-a/allocation?instance_id={instance}&cash=10',
                f'/api/terms/sim-a/allocation?instance_id={instance}&as_of_day=0&cash=-5',
                f'/api/terms/sim-a/allocation?instance_id={instance}&as_of_day=0&cash=01',
                f'/api/terms/sim-a/allocation?instance_id={instance}&as_of_day=0&cash=abc',
                f'/api/terms/sim-a/allocation?instance_id={instance}&as_of_day=0&cash=1&cash=2',
                f'/api/terms/sim-a/allocation?instance_id={instance}&as_of_day=0&cash=1&draw_day=01',
            ):
                code, bad = get(path, auditor)
                self.assertEqual(code, 400, path)
                self.assertEqual(bad['error'], 'INVALID_ARGUMENTS', path)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

    def test_port_exposes_the_allocation_method(self):
        self.assertIsInstance(CapitalService().terms, TermsPolicyPort)


if __name__ == '__main__':
    unittest.main()
