"""Portfolio terms rollup: one simulated row per advance, exact totals, cap read from the note."""
import copy
import json
import re
import tempfile
import threading
import unittest
from fractions import Fraction
from http.client import HTTPConnection
from pathlib import Path

from capital.auth import route_permission
from capital.server import make_server, route_label
from capital.service import ApiError, CapitalService
from capital.terms import DecisionNoteTermsPolicy

ROOT = Path(__file__).resolve().parents[1]
NOTE = ROOT / 'docs' / 'decisions' / 'CAPITAL_FINANCIAL_TERMS.md'
_FENCE = re.compile(r'```capital-decision-v1[ \t]*\n(.*?)```', re.DOTALL)
LABEL = 'simulated overlay — not vendor FSM arithmetic, not an offer'


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


def reference_tier(gate, refund_face):
    for tier in _value('interest_rate')['tiers']:
        condition = tier['condition']
        if condition.get('settlement_gate') != gate:
            continue
        if 'refund_face' in condition and condition['refund_face'] != refund_face:
            continue
        return tier
    return None


def reference_row(principal, draw_day, as_of_day, tier, expected):
    interest = _value('interest_rate')
    fees = _value('fees')
    term = _value('term')
    day_count = _day_count(interest['day_count'])
    if expected is None:
        term_days, source = term['standard_term_days'], 'standard'
    else:
        raw = expected - draw_day + term['settlement_slack_days']
        term_days = _clamp(raw, term['min_term_days'], term['max_term_days'])
        source = 'settlement_linked'
    maturity = draw_day + term_days
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
    exact = contract_exact + default_exact
    annual = contract_bps + interest['default_interest_add_bps_annual']
    annual += fees['servicing_fee_bps_annual'] + fees['commitment_fee_bps_annual_on_undrawn']
    one_time = fees['origination_fee_bps'] + fees['extension_fee_bps'] + fees['prepayment_penalty_bps']
    if type(fees.get('late_fee')) is int:
        one_time += fees['late_fee']
    annualized = annual + Fraction(one_time * day_count, term_days)
    cap = interest['all_in_cost_cap_bps_annual']
    cap_ok = annual * term_days + one_time * day_count <= cap * term_days
    return {
        'term_days': term_days,
        'term_source': source,
        'maturity_day': maturity,
        'days_past_maturity': max(0, as_of_day - maturity),
        'contractual_days': contractual_days,
        'default_days': default_days,
        'contract_exact': f'{contract_exact.numerator}/{contract_exact.denominator}',
        'contract_interest_krw': contract_exact.numerator // contract_exact.denominator,
        'default_exact': f'{default_exact.numerator}/{default_exact.denominator}',
        'default_interest_krw': default_exact.numerator // default_exact.denominator,
        'exact': f'{exact.numerator}/{exact.denominator}',
        'interest_krw': exact.numerator // exact.denominator,
        'annualized_all_in_bps': f'{annualized.numerator}/{annualized.denominator}',
        'cap_check': 'PASS' if cap_ok else 'FAIL',
    }


class TermsPortfolioTests(unittest.TestCase):
    def setUp(self):
        self.service = CapitalService()
        self.counter = 0

    def command(self, op, case='sim-a', **args):
        self.counter += 1
        return self.service.execute({
            'instance_id': self.service.instance_id,
            'operation_id': f'pf-{self.counter}',
            'op': op,
            'advance_id': case,
            'args': args,
        })

    def portfolio(self, service=None, draw_day=None, as_of_day=0, expected=None):
        service = service or self.service
        return service.terms_portfolio(
            service.instance_id, draw_day=draw_day, as_of_day=as_of_day,
            expected_settlement_cash_day=expected)

    def claim(self, case, service=None):
        service = service or self.service
        return service.fixtures.view(service.case_fixtures[case])['claim']

    def test_empty_portfolio_is_not_applicable_not_unbound(self):
        body = self.portfolio(as_of_day=1)
        self.assertEqual(body['label'], LABEL)
        self.assertEqual(body['mode'], 'SIMULATED_OVERLAY')
        self.assertEqual(body['status'], 'BOUND')
        self.assertEqual(body['rows'], [])
        totals = body['totals']
        self.assertEqual(totals['advances'], 0)
        self.assertEqual(totals['evaluated'], 0)
        self.assertEqual(totals['cap_check'], 'NOT_APPLICABLE')
        self.assertEqual(totals['exact'], '0/1')
        self.assertEqual(totals['interest_krw'], 0)
        self.assertEqual(body['cap']['status'], 'BOUND')
        self.assertEqual(
            body['cap']['all_in_cost_cap_bps_annual'],
            _value('interest_rate')['all_in_cost_cap_bps_annual'])
        self.assertEqual(body['cap']['fees_policy'], _value('fees')['policy'])
        self.assertEqual(body['cap']['fee_schedule_version'], _value('fees')['fee_schedule_version'])
        self.assertIs(body['funds_executed'], False)
        self.assertIs(body['workspace_mutated'], False)
        self.assertIs(body['write_authorized'], False)
        self.assertEqual(body['instance_id'], self.service.instance_id)
        self.assertEqual(body['observed_state_digest'], self.service.machine.state_digest())

    def test_rows_match_an_independent_reference(self):
        for op in ('offer', 'approve', 'bind_settlement', 'draw'):
            args = {'fixture_id': 'sim-committed', 'amount': 60000} if op == 'offer' else {}
            self.assertEqual(self.command(op, **args)['outcome'], 'ACCEPTED')
        for op in ('offer', 'approve', 'draw'):
            args = {'fixture_id': 'sim-pending', 'amount': 25000} if op == 'offer' else {}
            self.assertEqual(self.command(op, 'sim-b', **args)['outcome'], 'ACCEPTED')
        self.assertEqual(
            self.command('offer', 'sim-open', fixture_id='sim-committed', amount=1)['outcome'],
            'ACCEPTED')
        body = self.portfolio(as_of_day=80)
        self.assertEqual([row['advance_id'] for row in body['rows']], ['sim-a', 'sim-b', 'sim-open'])
        rows = {row['advance_id']: row for row in body['rows']}
        open_row = rows['sim-open']
        self.assertEqual(open_row['status'], 'NOT_APPLICABLE')
        self.assertFalse(_has_number(open_row))

        expected = {
            'sim-a': ('T1', 60000, 'MOCK_COMMIT_OBSERVED', 'DRAWN'),
            'sim-b': ('T2', 25000, 'UNBOUND', 'DRAWN'),
        }
        for advance_id, (tier_id, principal, gate, phase) in expected.items():
            row = rows[advance_id]
            self.assertEqual(row['status'], 'BOUND')
            self.assertEqual(row['phase'], phase)
            self.assertEqual(row['tier'], tier_id)
            self.assertEqual(row['principal'], principal)
            self.assertEqual(row['draw_day'], 0)
            self.assertEqual(row['draw_day_source'], 'DEFAULT')
            claim = self.claim(advance_id)
            tier = reference_tier(gate, claim['refund_face'])
            self.assertIsNotNone(tier)
            reference = reference_row(principal, 0, 80, tier, None)
            for key, value in reference.items():
                self.assertEqual(row[key], value, f'{advance_id}.{key}')

        totals = body['totals']
        self.assertEqual(totals['advances'], 3)
        self.assertEqual(totals['evaluated'], 2)
        self.assertEqual(totals['cap_check'], 'PASS')
        contract = sum(Fraction(row['contract_exact']) for row in rows.values()
                       if row['status'] == 'BOUND')
        default = sum(Fraction(row['default_exact']) for row in rows.values()
                      if row['status'] == 'BOUND')
        exact = contract + default
        self.assertEqual(Fraction(totals['contract_exact']), contract)
        self.assertEqual(Fraction(totals['default_exact']), default)
        self.assertEqual(Fraction(totals['exact']), exact)
        self.assertEqual(totals['contract_interest_krw'], contract.numerator // contract.denominator)
        self.assertEqual(totals['default_interest_krw'], default.numerator // default.denominator)
        self.assertEqual(totals['interest_krw'], exact.numerator // exact.denominator)

        queried = self.portfolio(draw_day=10, as_of_day=80)
        for row in queried['rows']:
            if row['status'] == 'BOUND':
                self.assertEqual(row['draw_day'], 10)
                self.assertEqual(row['draw_day_source'], 'QUERY_PARAMETER')
        linked = self.portfolio(draw_day=0, as_of_day=80, expected=100)
        t1 = rows['sim-a']
        for row in linked['rows']:
            if row['status'] == 'BOUND':
                self.assertEqual(row['term_source'], 'settlement_linked')
        self.assertNotEqual(linked['rows'][0]['term_days'], t1['term_days'])

    def test_cap_fail_only_with_a_lowered_synthetic_note(self):
        text = NOTE.read_text(encoding='utf-8')
        cap = _value('interest_rate')['all_in_cost_cap_bps_annual']
        needle = f'"all_in_cost_cap_bps_annual": {cap}'
        self.assertIn(needle, text)
        lowered = text.replace(needle, '"all_in_cost_cap_bps_annual": 1100', 1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'note.md'
            path.write_text(lowered, encoding='utf-8')
            low = CapitalService(terms=DecisionNoteTermsPolicy(path))
        for op in ('offer', 'approve', 'draw'):
            args = {'fixture_id': 'sim-pending', 'amount': 25000} if op == 'offer' else {}
            outcome = low.execute({
                'instance_id': low.instance_id, 'operation_id': f'low-{op}',
                'op': op, 'advance_id': 'sim-low', 'args': args,
            })['outcome']
            self.assertEqual(outcome, 'ACCEPTED')
        body = self.portfolio(low, as_of_day=10)
        self.assertEqual(body['cap']['all_in_cost_cap_bps_annual'], 1100)
        row = body['rows'][0]
        self.assertEqual(row['tier'], 'T2')
        self.assertEqual(row['cap_check'], 'FAIL')
        self.assertEqual(body['totals']['cap_check'], 'FAIL')
        self.assertEqual(NOTE.read_text(encoding='utf-8'), text)
        committed = self.portfolio(self.service, as_of_day=10)
        self.assertNotIn('FAIL', {row['cap_check'] for row in committed['rows']
                                 if row['status'] == 'BOUND'})

    def test_unbound_note_has_no_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = CapitalService(terms=DecisionNoteTermsPolicy(Path(tmp) / 'missing.md'))
            undetermined = Path(tmp) / 'none.md'
            undetermined.write_text(
                NOTE.read_text(encoding='utf-8').replace('"status": "ADOPTED"', '"status": "UNDETERMINED"'),
                encoding='utf-8')
            undecided = CapitalService(terms=DecisionNoteTermsPolicy(undetermined))
        undecided.execute({
            'instance_id': undecided.instance_id, 'operation_id': 'u-offer', 'op': 'offer',
            'advance_id': 'sim-a', 'args': {'fixture_id': 'sim-committed', 'amount': 1000},
        })
        for service in (missing, undecided):
            before = (copy.deepcopy(service.receipts), service.machine.state_digest())
            body = self.portfolio(service, as_of_day=1)
            self.assertEqual(body['status'], 'NOT_BOUND')
            self.assertEqual(body['reason'], 'terms not bound')
            self.assertEqual(body['label'], LABEL)
            self.assertFalse(_has_number(body))
            self.assertNotIn('rows', body)
            self.assertNotIn('totals', body)
            self.assertEqual((service.receipts, service.machine.state_digest()), before)

    def test_guards_and_read_only_invariant(self):
        self.assertEqual(self.command('offer', fixture_id='sim-committed', amount=1000)['outcome'], 'ACCEPTED')
        before = (copy.deepcopy(self.service.receipts), self.service.machine.state_digest())
        body = self.portfolio(as_of_day=1)
        self.assertEqual(body['observed_state_digest'], before[1])
        self.assertEqual((self.service.receipts, self.service.machine.state_digest()), before)
        with self.assertRaises(ApiError) as caught:
            self.service.terms_portfolio('other', as_of_day=1)
        self.assertEqual(caught.exception.args[0], 'SESSION_CHANGED')
        for bad in (-1, 'x', 1.5, True):
            with self.assertRaises(ApiError):
                self.portfolio(as_of_day=bad)
            with self.assertRaises(ApiError):
                self.portfolio(draw_day=bad, as_of_day=1)
            with self.assertRaises(ApiError):
                self.portfolio(as_of_day=1, expected=bad)


class TermsPortfolioHttpTests(unittest.TestCase):
    def test_literal_route_wins_over_advance_id_and_observer_is_denied(self):
        server = make_server(0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            service = server.service
            authorizer = server.authorizer
            auditor = authorizer.bind_role('auditor')
            observer = authorizer.bind_role('observer')
            for index, op in enumerate(('offer', 'approve', 'bind_settlement', 'draw'), start=1):
                args = {'fixture_id': 'sim-committed', 'amount': 60000} if op == 'offer' else {}
                outcome = service.execute({
                    'instance_id': service.instance_id, 'operation_id': f'pf-http-{index}',
                    'op': op, 'advance_id': 'sim-a', 'args': args,
                })['outcome']
                self.assertEqual(outcome, 'ACCEPTED')
            before = (copy.deepcopy(service.receipts), service.machine.state_digest())
            instance = service.instance_id

            def get(path, token):
                client = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                client.request('GET', path, headers={'X-Capital-Token': token})
                response = client.getresponse()
                payload = json.loads(response.read().decode())
                status = response.status
                client.close()
                return status, payload

            code, body = get(f'/api/terms/portfolio?instance_id={instance}&as_of_day=1', auditor)
            self.assertEqual(code, 200, body)
            self.assertEqual(body['label'], LABEL)
            self.assertIn('rows', body)
            self.assertIn('totals', body)
            self.assertNotEqual(body.get('error'), 'UNKNOWN_ADVANCE')
            self.assertEqual(route_label('/api/terms/portfolio'), '/api/terms')
            self.assertEqual(route_permission('/api/terms/portfolio'), 'projection:read')
            self.assertEqual((service.receipts, service.machine.state_digest()), before)

            code, denied = get(f'/api/terms/portfolio?instance_id={instance}&as_of_day=1', observer)
            self.assertEqual(code, 403)
            self.assertEqual(denied['error'], 'ROLE_FORBIDDEN')
            self.assertEqual(denied['permission'], 'projection:read')
            code, missing = get(
                f'/api/terms/sim-missing?instance_id={instance}&draw_day=0&as_of_day=0', auditor)
            self.assertEqual(code, 404)
            self.assertEqual(missing['error'], 'UNKNOWN_ADVANCE')
            code, changed = get('/api/terms/portfolio?instance_id=other&as_of_day=1', auditor)
            self.assertEqual(code, 409)
            self.assertEqual(changed['error'], 'SESSION_CHANGED')
            code, bad = get(f'/api/terms/portfolio?instance_id={instance}', auditor)
            self.assertEqual(code, 400)
            self.assertEqual(bad['error'], 'INVALID_ARGUMENTS')
            self.assertEqual((service.receipts, service.machine.state_digest()), before)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
