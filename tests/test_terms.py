"""Simulated terms overlay: ADOPTED note values, and NOT_BOUND when none are usable."""
import ast
import copy
import json
import re
import tempfile
import threading
import unittest
from fractions import Fraction
from http.client import HTTPConnection
from pathlib import Path

import scripts.decision_ledger as ledger
from capital.ports import TermsPolicyPort
from capital.server import make_server
from capital.service import ApiError, CapitalService
from capital.terms import OVERLAY_LABEL, DecisionNoteTermsPolicy

ROOT = Path(__file__).resolve().parents[1]
NOTE = ROOT / 'docs' / 'decisions' / 'CAPITAL_FINANCIAL_TERMS.md'
TERMS_PY = ROOT / 'capital' / 'terms.py'
_FENCE = re.compile(r'```capital-decision-v1[ \t]*\n(.*?)```', re.DOTALL)
QUOTE = 'PROVISIONAL per docs/decisions/CAPITAL_FINANCIAL_TERMS.md (CAPITAL-TERMS-V1)'
LABEL = 'simulated overlay — not vendor FSM arithmetic, not an offer'


def note_block(text=None):
    raw = _FENCE.findall(NOTE.read_text(encoding='utf-8') if text is None else text)
    if len(raw) != 1:
        raise AssertionError('expected one block')
    return json.loads(raw[0])


def entries():
    return note_block()['entries']


def _value(name):
    return entries()[name]['value']


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
        return term['standard_term_days'], 'standard'
    raw = expected - draw_day + term['settlement_slack_days']
    return _clamp(raw, term['min_term_days'], term['max_term_days']), 'settlement_linked'


def reference_schedule(draw_day, expected):
    term_days, source = reference_term_days(draw_day, expected)
    term = _value('term')
    loss = _value('default_loss_treatment')
    maturity = draw_day + term_days
    grace = term['grace_days_after_maturity']
    default_eligible = maturity + grace + 1
    return {
        'term_days': term_days,
        'maturity_day': maturity,
        'grace_days': grace,
        'default_eligible_day': default_eligible,
        'writeoff_day': default_eligible + loss['writeoff_days_after_default'],
        'source': source,
    }


def reference_tier(gate, refund_face):
    for tier in _value('interest_rate')['tiers']:
        condition = tier['condition']
        if condition.get('settlement_gate') != gate:
            continue
        if 'refund_face' in condition and condition['refund_face'] != refund_face:
            continue
        return tier
    return None


def reference_accrual(principal, draw_day, as_of_day, tier, schedule):
    interest = _value('interest_rate')
    fees = _value('fees')
    day_count = _day_count(interest['day_count'])
    elapsed = as_of_day - draw_day
    if elapsed < interest['min_interest_days']:
        elapsed = interest['min_interest_days']
    if elapsed <= schedule['term_days']:
        contractual_days = elapsed
        default_days = 0
    else:
        contractual_days = schedule['term_days']
        default_days = elapsed - contractual_days
    contract_bps = tier['all_in_bps_annual']
    default_bps = contract_bps + interest['default_interest_add_bps_annual']
    numerator = principal * contractual_days * contract_bps + principal * default_days * default_bps
    denominator = 10000 * day_count
    exact = Fraction(numerator, denominator)
    annual = contract_bps + interest['default_interest_add_bps_annual']
    annual += fees['servicing_fee_bps_annual'] + fees['commitment_fee_bps_annual_on_undrawn']
    one_time = fees['origination_fee_bps'] + fees['extension_fee_bps'] + fees['prepayment_penalty_bps']
    cap = interest['all_in_cost_cap_bps_annual']
    return {
        'exact': f'{exact.numerator}/{exact.denominator}',
        'interest_krw': exact.numerator // exact.denominator,
        'all_in_bps_annual': contract_bps,
        'cap_ok': annual * schedule['term_days'] + one_time * day_count <= cap * schedule['term_days'],
        'contractual_days': contractual_days,
        'default_days': default_days,
        'fee_bps_charged': (
            fees['origination_fee_bps'] + fees['servicing_fee_bps_annual']
            + fees['commitment_fee_bps_annual_on_undrawn'] + fees['extension_fee_bps']
            + fees['prepayment_penalty_bps']
        ),
    }


def reference_eligible(claim):
    margin = _value('additional_margin')
    payees = margin['beneficiary_payee_map']['fixture-organizer']
    total = sum(line['outstanding'] for line in claim['obligations'] if line['payee'] in payees)
    return total - claim['refund_face']


def reference_base(claim, tier):
    rate = _value('additional_margin')['advance_rate_bps_by_tier'][tier['id']]
    eligible = reference_eligible(claim)
    return eligible, rate, eligible * rate // 10000


def reference_reserve(exposure, phase, as_of_day, tier, schedule):
    weights = _value('reserve')['provision_bps_of_outstanding']
    if phase == 'DEFAULTED':
        bucket = 'DEFAULTED'
    elif exposure > 0 and as_of_day > schedule['maturity_day']:
        bucket = 'PAST_DUE_ANY_TIER'
    else:
        bucket = tier['id']
    bps = weights[bucket]
    return bucket, bps, exposure * bps // 10000


def _numbers(value, found):
    if type(value) is bool:
        return
    if type(value) is int:
        found.add(value)
        return
    if type(value) is dict:
        for item in value.values():
            _numbers(item, found)
    elif type(value) is list:
        for item in value:
            _numbers(item, found)


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


class TermsOverlayTests(unittest.TestCase):
    def setUp(self):
        self.service = CapitalService()
        self.counter = 0

    def command(self, op, case='sim-a', **args):
        self.counter += 1
        return self.service.execute({
            'instance_id': self.service.instance_id,
            'operation_id': f'terms-{self.counter}',
            'op': op,
            'advance_id': case,
            'args': args,
        })

    def ready(self, case='sim-a', amount=60000, fixture='sim-committed', bound=True):
        self.assertEqual(self.command('offer', case, fixture_id=fixture, amount=amount)['outcome'], 'ACCEPTED')
        self.assertEqual(self.command('approve', case)['outcome'], 'ACCEPTED')
        if bound:
            self.assertEqual(self.command('bind_settlement', case)['outcome'], 'ACCEPTED')

    def overlay(self, case='sim-a', draw_day=0, as_of_day=0, expected=None):
        return self.service.case_terms(
            case, self.service.instance_id, draw_day, as_of_day, expected)

    def claim(self, case='sim-a'):
        return self.service.fixtures.view(self.service.case_fixtures[case])['claim']

    def test_port_loads_only_adopted_entries_from_the_real_note(self):
        errors, summary = ledger.validate_note(NOTE)
        self.assertEqual(errors, [])
        policy = self.service.terms
        self.assertIsInstance(policy, TermsPolicyPort)
        status = policy.status()
        self.assertEqual(status['label'], LABEL)
        self.assertEqual(OVERLAY_LABEL, LABEL)
        self.assertEqual(status['status'], 'BOUND')
        self.assertIsNone(status['reason'])
        self.assertEqual(status['terms_version'], note_block()['terms_version'])
        self.assertEqual(status['items'], summary['entries'])
        self.assertTrue(all(mark == 'ADOPTED' for mark in status['items'].values()))
        self.assertTrue(all(flag == 'BOUND' for flag in status['sections'].values()))

    def test_removed_and_undetermined_notes_are_not_bound(self):
        text = NOTE.read_text(encoding='utf-8')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = DecisionNoteTermsPolicy(root / 'absent.md')
            self.assertEqual(missing.status()['status'], 'NOT_BOUND')
            self.assertEqual(missing.status()['reason'], 'terms not bound')
            two = root / 'two.md'
            two.write_text(text + '\n```capital-decision-v1\n{"schema":"capital-decision-v1"}\n```\n', encoding='utf-8')
            bad = root / 'bad.md'
            bad.write_text(text.replace('```capital-decision-v1\n{', '```capital-decision-v1\n{,', 1), encoding='utf-8')
            duplicate = root / 'dup.md'
            duplicate.write_text('```capital-decision-v1\n{"schema":"capital-decision-v1","schema":"other"}\n```\n', encoding='utf-8')
            undetermined = root / 'none.md'
            undetermined.write_text(text.replace('"status": "ADOPTED"', '"status": "UNDETERMINED"'), encoding='utf-8')
            for path in (two, bad, duplicate, undetermined):
                policy = DecisionNoteTermsPolicy(path)
                self.assertEqual(policy.status()['status'], 'NOT_BOUND', path.name)
                self.assertEqual(policy.status()['reason'], 'terms not bound', path.name)
            partial = root / 'partial.md'
            partial.write_text(text.replace('"status": "ADOPTED"', '"status": "UNDETERMINED"', 1), encoding='utf-8')
            partial_policy = DecisionNoteTermsPolicy(partial)
            self.assertEqual(partial_policy.status()['status'], 'PARTIAL')
            self.assertEqual(partial_policy.status()['items']['interest_rate'], 'UNDETERMINED')
            dropped = root / 'dropped.md'
            needle = '"provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",\n'
            self.assertIn(needle, text)
            dropped.write_text(text.replace(needle, '', 1), encoding='utf-8')
            dropped_policy = DecisionNoteTermsPolicy(dropped)
            self.assertEqual(dropped_policy.status()['status'], 'PARTIAL')
            self.assertEqual(dropped_policy.status()['items']['interest_rate'], 'UNDETERMINED')
            unsupported = root / 'token.md'
            unsupported.write_text(text.replace('"day_count": "ACT_365_FIXED"', '"day_count": "ACT_365_ACTUAL"', 1), encoding='utf-8')
            token_policy = DecisionNoteTermsPolicy(unsupported)
            self.assertEqual(token_policy.status()['items']['interest_rate'], 'NOT_BOUND')
            self.assertEqual(token_policy.status()['status'], 'PARTIAL')
            self.assertEqual(token_policy.status()['sections']['accrual'], 'NOT_BOUND')

    def test_unbound_endpoints_and_snapshot_have_no_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'note.md'
            path.write_text(NOTE.read_text(encoding='utf-8').replace('"status": "ADOPTED"', '"status": "UNDETERMINED"'), encoding='utf-8')
            service = CapitalService(terms=DecisionNoteTermsPolicy(path))
            missing = CapitalService(terms=DecisionNoteTermsPolicy(Path(tmp) / 'missing.md'))
        for current in (service, missing):
            status = current.terms_status()
            snap = current.snapshot()
            self.assertEqual(status['reason'], 'terms not bound')
            self.assertEqual(snap['terms']['status'], 'NOT_BOUND')
            self.assertEqual(snap['terms']['reason'], 'terms not bound')
            self.assertEqual(status['label'], LABEL)
            self.assertFalse(_has_number(status))
            self.assertFalse(_has_number(snap['terms']))
            self.assertEqual(current.readiness()['requirement_notes']['CAP-01'], 'terms not bound')
            self.assertEqual(current.readiness()['requirement_notes']['CAP-04'], 'terms not bound')
            self.assertIn('terms not bound', current.snapshot()['decisions'][0])

    def test_bound_case_matches_an_independent_reference(self):
        interest = _value('interest_rate')
        day_count = _day_count(interest['day_count'])
        t1 = reference_tier('MOCK_COMMIT_OBSERVED', 0)
        if t1['all_in_bps_annual'] == 700 and day_count == 365:
            hand = reference_accrual(60000, 0, 1, t1, {'term_days': _value('term')['standard_term_days']})
            self.assertEqual(hand['interest_krw'], 11)
            self.assertEqual(hand['exact'], '840/73')
        self.ready(amount=60000)
        approved = self.overlay(as_of_day=1)
        claim = self.claim()
        schedule = reference_schedule(0, None)
        accrual = reference_accrual(60000, 0, 1, t1, schedule)
        self.assertEqual(approved['tier'], 'T1')
        self.assertEqual(approved['principal'], 60000)
        self.assertEqual(approved['schedule']['term_days'], schedule['term_days'])
        self.assertEqual(approved['schedule']['maturity_day'], schedule['maturity_day'])
        self.assertEqual(approved['schedule']['grace_days'], schedule['grace_days'])
        self.assertEqual(approved['schedule']['default_eligible_day'], schedule['default_eligible_day'])
        self.assertEqual(approved['schedule']['writeoff_day'], schedule['writeoff_day'])
        self.assertEqual(approved['accrual']['exact'], accrual['exact'])
        self.assertEqual(approved['accrual']['interest_krw'], accrual['interest_krw'])
        self.assertEqual(approved['accrual']['all_in_bps_annual'], accrual['all_in_bps_annual'])
        self.assertEqual(approved['accrual']['cap_ok'], accrual['cap_ok'])
        self.assertEqual(approved['accrual']['fee_bps_charged'], 0)
        self.assertTrue(approved['accrual']['cap_ok'])
        self.assertIn('principal is constant', approved['accrual']['assumption'])
        eligible, rate, base = reference_base(claim, t1)
        self.assertEqual(approved['borrowing_base']['eligible_face'], eligible)
        self.assertEqual(approved['borrowing_base']['advance_rate_bps'], rate)
        self.assertEqual(approved['borrowing_base']['base_krw'], base)
        self.assertIs(approved['borrowing_base']['margin_call'], 0 > base)
        rung = _value('external_collateral_completeness')['required_by_tier'][t1['id']]
        self.assertEqual(approved['collateral']['rung'], rung['simulation'])
        self.assertEqual(approved['collateral']['real_funds_minimum'], rung['real_funds_minimum'])
        self.assertIs(approved['collateral']['synthetic'], True)
        flags = approved['collateral']['flags']
        view = self.service.machine.view('sim-a')
        self.assertEqual(flags['collateral_perfected'], view['collateral_perfected'])
        self.assertEqual(flags['priority_bound'], view['priority_bound'])
        self.assertIs(flags['external_pledge_complete'], False)
        underwriting = _value('underwriting_depth')
        execution = _value('collateral_execution')
        self.assertIs(approved['not_applied']['underwriting_depth']['applied'], False)
        self.assertEqual(approved['not_applied']['underwriting_depth']['depth'], underwriting['depth'])
        self.assertEqual(
            approved['not_applied']['underwriting_depth']['check_ids'],
            [item['id'] for item in underwriting['checks_ordered']])
        self.assertIs(approved['not_applied']['collateral_execution']['applied'], False)
        self.assertEqual(approved['not_applied']['collateral_execution']['primary'], execution['primary'])
        self.assertEqual(approved['not_applied']['collateral_execution']['never'], execution['never'])
        self.assertEqual(approved['label'], LABEL)
        self.assertIs(approved['funds_executed'], False)
        self.assertIs(approved['workspace_mutated'], False)
        self.assertIs(approved['write_authorized'], False)

        self.assertEqual(self.command('draw')['outcome'], 'ACCEPTED')
        drawn = self.overlay(as_of_day=1)
        drawn_accrual = reference_accrual(60000, 0, 1, t1, schedule)
        self.assertEqual(drawn['principal'], 60000)
        self.assertEqual(drawn['accrual']['exact'], drawn_accrual['exact'])
        self.assertEqual(drawn['borrowing_base']['base_krw'], base)
        self.assertIs(drawn['borrowing_base']['margin_call'], False)
        self.assertEqual(self.command('repay', amount=20000, sequence=1)['outcome'], 'ACCEPTED')
        partial = self.overlay(as_of_day=1)
        partial_accrual = reference_accrual(40000, 0, 1, t1, schedule)
        self.assertEqual(partial['principal'], 40000)
        self.assertEqual(partial['accrual']['exact'], partial_accrual['exact'])
        self.assertEqual(partial['accrual']['interest_krw'], partial_accrual['interest_krw'])
        minimum = self.overlay(draw_day=10, as_of_day=10)
        minimum_accrual = reference_accrual(40000, 10, 10, t1, reference_schedule(10, None))
        self.assertEqual(minimum['accrual']['contractual_days'], interest['min_interest_days'])
        self.assertEqual(minimum['accrual']['interest_krw'], minimum_accrual['interest_krw'])
        past_schedule = reference_schedule(0, None)
        past_as_of = past_schedule['maturity_day'] + 5
        past = self.overlay(as_of_day=past_as_of)
        past_accrual = reference_accrual(40000, 0, past_as_of, t1, past_schedule)
        self.assertGreater(past['accrual']['default_days'], 0)
        self.assertEqual(past['accrual']['exact'], past_accrual['exact'])
        self.assertEqual(past['accrual']['interest_krw'], past_accrual['interest_krw'])
        bucket, bps, provision = reference_reserve(40000, 'DRAWN', past_as_of, t1, past_schedule)
        self.assertEqual(past['reserve_provision']['bucket'], bucket)
        self.assertEqual(past['reserve_provision']['provision_bps'], bps)
        self.assertEqual(past['reserve_provision']['provision_krw'], provision)
        self.assertEqual(bucket, 'PAST_DUE_ANY_TIER')

        low = self.overlay(draw_day=100, expected=0)
        low_days, low_source = reference_term_days(100, 0)
        self.assertEqual(low_days, _value('term')['min_term_days'])
        self.assertEqual(low['schedule']['term_days'], low_days)
        self.assertEqual(low['schedule']['source'], low_source)
        high = self.overlay(expected=999999)
        high_days, _high_source = reference_term_days(0, 999999)
        self.assertEqual(high_days, _value('term')['max_term_days'])
        self.assertEqual(high['schedule']['term_days'], high_days)

        self.assertEqual(self.command('repay', amount=40000, sequence=2)['outcome'], 'ACCEPTED')
        self.assertEqual(self.command('close')['outcome'], 'ACCEPTED')
        closed = self.overlay()
        self.assertEqual(closed['principal'], 0)
        self.assertEqual(closed['accrual']['interest_krw'], 0)
        closed_bucket, closed_bps, closed_provision = reference_reserve(0, 'CLOSED', 0, t1, schedule)
        self.assertEqual(closed['reserve_provision']['bucket'], closed_bucket)
        self.assertEqual(closed['reserve_provision']['provision_krw'], closed_provision)
        self.assertEqual(closed_bps, _value('reserve')['provision_bps_of_outstanding'][t1['id']])

        self.ready('sim-default', amount=60000)
        self.assertEqual(self.command('draw', 'sim-default')['outcome'], 'ACCEPTED')
        self.assertEqual(self.command('default', 'sim-default')['outcome'], 'ACCEPTED')
        defaulted = self.overlay('sim-default', as_of_day=past_as_of)
        def_bucket, def_bps, def_provision = reference_reserve(60000, 'DEFAULTED', past_as_of, t1, schedule)
        self.assertEqual(def_bucket, 'DEFAULTED')
        self.assertEqual(defaulted['reserve_provision']['bucket'], def_bucket)
        self.assertEqual(defaulted['reserve_provision']['provision_bps'], def_bps)
        self.assertEqual(defaulted['reserve_provision']['provision_krw'], def_provision)
        self.assertEqual(
            defaulted['not_applied']['loss_waterfall']['recovery_waterfall'],
            _value('default_loss_treatment')['recovery_waterfall'])
        self.assertIs(defaulted['not_applied']['loss_waterfall']['applied'], False)

        self.ready('sim-unbound', fixture='sim-pending', bound=False)
        self.assertEqual(self.command('draw', 'sim-unbound')['outcome'], 'ACCEPTED')
        unbound = self.overlay('sim-unbound', as_of_day=1)
        t2 = reference_tier('UNBOUND', self.claim('sim-unbound')['refund_face'])
        self.assertEqual(unbound['tier'], 'T2')
        t2_accrual = reference_accrual(60000, 0, 1, t2, schedule)
        self.assertEqual(unbound['accrual']['all_in_bps_annual'], t2['all_in_bps_annual'])
        self.assertEqual(unbound['accrual']['exact'], t2_accrual['exact'])
        self.assertEqual(unbound['accrual']['interest_krw'], t2_accrual['interest_krw'])
        t2_rung = _value('external_collateral_completeness')['required_by_tier'][t2['id']]
        self.assertEqual(unbound['collateral']['rung'], t2_rung['simulation'])
        _eligible, t2_rate, t2_base = reference_base(self.claim('sim-unbound'), t2)
        self.assertEqual(unbound['borrowing_base']['advance_rate_bps'], t2_rate)
        self.assertEqual(unbound['borrowing_base']['base_krw'], t2_base)
        t2_bucket, t2_bps, t2_provision = reference_reserve(60000, 'DRAWN', 1, t2, schedule)
        self.assertEqual(unbound['reserve_provision']['provision_bps'], t2_bps)
        self.assertEqual(unbound['reserve_provision']['provision_krw'], t2_provision)
        self.assertEqual(t2_bucket, t2['id'])

        wide_service = CapitalService()
        wide_id = wide_service.instance_id
        for index, (op, args) in enumerate((
            ('offer', {'fixture_id': 'sim-committed', 'amount': 90000}),
            ('approve', {}),
            ('bind_settlement', {}),
            ('draw', {}),
        ), start=1):
            outcome = wide_service.execute({
                'instance_id': wide_id, 'operation_id': f'wide-{index}', 'op': op,
                'advance_id': 'sim-wide', 'args': args,
            })['outcome']
            self.assertEqual(outcome, 'ACCEPTED')
        wide = wide_service.case_terms('sim-wide', wide_id, 0, 0)
        wide_claim = wide_service.fixtures.view('sim-committed')['claim']
        _face, _wide_rate, wide_base = reference_base(wide_claim, t1)
        self.assertGreater(90000, wide_base)
        self.assertIs(wide['borrowing_base']['margin_call'], True)
        self.assertEqual(wide['borrowing_base']['base_krw'], wide_base)

        refund_claim = self.service.fixtures.view('sim-refund')['claim']
        refund_case = {
            'phase': 'DRAWN', 'amount': 1000, 'outstanding_exposure': 1000,
            'drawn_exposure': 1000, 'draw_id': 'draw-refund',
            'beneficiary_role': 'fixture-organizer', 'settlement_gate': 'MOCK_COMMIT_OBSERVED',
            'collateral_perfected': False, 'priority_bound': False, 'external_pledge_complete': False,
        }
        refund = self.service.terms.overlay(
            refund_case, refund_claim, draw_day=0, as_of_day=1,
            expected_settlement_cash_day=None, gate='MOCK_COMMIT_OBSERVED')
        self.assertEqual(refund['tier'], 'NOT_APPLICABLE')
        self.assertEqual(refund['accrual']['status'], 'NOT_APPLICABLE')
        self.assertNotIn('all_in_bps_annual', refund['accrual'])
        offered = {
            'phase': 'OFFERED', 'amount': 1000, 'outstanding_exposure': 0,
            'beneficiary_role': 'fixture-organizer', 'settlement_gate': 'UNBOUND',
            'collateral_perfected': False, 'priority_bound': False,
        }
        offered_view = self.service.terms.overlay(
            offered, claim, draw_day=0, as_of_day=0,
            expected_settlement_cash_day=None, gate='UNBOUND')
        self.assertEqual(offered_view['tier'], 'NOT_APPLICABLE')

    def test_reads_do_not_change_receipts_or_the_journal(self):
        self.ready()
        self.assertEqual(self.command('draw')['outcome'], 'ACCEPTED')
        before = self._frozen_view()
        status = self.service.terms_status()
        case = self.overlay(as_of_day=1)
        self.assertEqual(status['observed_state_digest'], before['digest'])
        self.assertEqual(case['observed_state_digest'], before['digest'])
        self.assertEqual(self._frozen_view(), before)
        with tempfile.TemporaryDirectory() as tmp:
            empty = CapitalService(terms=DecisionNoteTermsPolicy(Path(tmp) / 'missing.md'))
            empty_before = (
                copy.deepcopy(empty.receipts), empty.machine.state_digest(), len(empty.receipts))
            unbound = empty.terms_status()
            self.assertEqual(unbound['reason'], 'terms not bound')
            self.assertEqual(
                (empty.receipts, empty.machine.state_digest(), len(empty.receipts)), empty_before)

    def _frozen_view(self):
        view = self.service.machine.view('sim-a')
        return {
            'receipts': copy.deepcopy(self.service.receipts),
            'digest': self.service.machine.state_digest(),
            'count': len(self.service.receipts),
            'reserved': view['reserved_open'],
        }

    def test_http_is_read_only_for_auditor_and_forbidden_for_observer(self):
        server = make_server(0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            service = server.service
            authorizer = server.authorizer
            auditor = authorizer.bind_role('auditor')
            observer = authorizer.bind_role('observer')

            def run(op, args):
                self.counter += 1
                return service.execute({
                    'instance_id': service.instance_id, 'operation_id': f'http-{self.counter}',
                    'op': op, 'advance_id': 'sim-a', 'args': args,
                })

            self.assertEqual(run('offer', {'fixture_id': 'sim-committed', 'amount': 60000})['outcome'], 'ACCEPTED')
            self.assertEqual(run('approve', {})['outcome'], 'ACCEPTED')
            self.assertEqual(run('bind_settlement', {})['outcome'], 'ACCEPTED')
            self.assertEqual(run('draw', {})['outcome'], 'ACCEPTED')
            before = (
                copy.deepcopy(service.receipts), service.machine.state_digest(), len(service.receipts),
                service.machine.view('sim-a')['reserved_open'],
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

            code, body = get('/api/terms', auditor)
            self.assertEqual(code, 200)
            self.assertEqual(body['label'], LABEL)
            self.assertEqual(body['status'], 'BOUND')
            case_path = f'/api/terms/sim-a?instance_id={instance}&draw_day=0&as_of_day=1'
            code, case = get(case_path, auditor)
            self.assertEqual(code, 200, case)
            self.assertEqual(case['label'], LABEL)
            after = (
                service.receipts, service.machine.state_digest(), len(service.receipts),
                service.machine.view('sim-a')['reserved_open'],
            )
            self.assertEqual(after, before)
            code, denied = get('/api/terms', observer)
            self.assertEqual(code, 403)
            self.assertEqual(denied['error'], 'ROLE_FORBIDDEN')
            self.assertEqual(denied['role'], 'observer')
            self.assertEqual(denied['permission'], 'projection:read')
            self.assertIn('observer', denied['reason'])
            code, _denied_case = get(case_path, observer)
            self.assertEqual(code, 403)
            self.assertEqual(
                (service.receipts, service.machine.state_digest(), len(service.receipts),
                 service.machine.view('sim-a')['reserved_open']),
                before)
            code, missing = get(f'/api/terms/sim-missing?instance_id={instance}&draw_day=0&as_of_day=0', auditor)
            self.assertEqual(code, 404)
            self.assertEqual(missing['error'], 'UNKNOWN_ADVANCE')
            code, changed = get('/api/terms/sim-a?instance_id=other&draw_day=0&as_of_day=0', auditor)
            self.assertEqual(code, 409)
            self.assertEqual(changed['error'], 'SESSION_CHANGED')
            code, bad_day = get(f'/api/terms/sim-a?instance_id={instance}&draw_day=01&as_of_day=0', auditor)
            self.assertEqual(code, 400)
            self.assertEqual(bad_day['error'], 'INVALID_ARGUMENTS')
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

    def test_module_constants_are_only_the_scale_and_zero_and_one(self):
        tree = ast.parse(TERMS_PY.read_text(encoding='utf-8'))
        found = []

        class Visitor(ast.NodeVisitor):
            def visit_Constant(self, node):
                if type(node.value) is int or type(node.value) is float:
                    found.append(node.value)

        Visitor().visit(tree)
        self.assertTrue(set(found) <= {0, 1, 10000}, found)
        note_ints = set()
        _numbers(entries(), note_ints)
        forbidden = note_ints - {0, 1, 10000}
        self.assertTrue(set(found).isdisjoint(forbidden), set(found) & forbidden)

    def test_readiness_and_docs_quote_the_decision_note(self):
        ready = self.service.readiness()
        self.assertEqual(ready['requirement_notes']['CAP-01'], QUOTE)
        self.assertEqual(ready['requirement_notes']['CAP-04'], QUOTE)
        self.assertEqual(self.service.snapshot()['terms']['status'], 'BOUND')
        self.assertEqual(self.service.snapshot()['terms']['terms_version'], 'CAPITAL-TERMS-V1')
        self.assertIn(QUOTE, self.service.snapshot()['decisions'][0])
        group = next(row for row in ready['groups'] if row['id'] == 'financial-contracts')
        self.assertEqual(group['status'], 'DECISION_REQUIRED')
        self.assertTrue(any('PROVISIONAL per docs/decisions/CAPITAL_FINANCIAL_TERMS.md' in item for item in group['blockers']))
        handbook = (ROOT / 'docs' / 'OPERATOR_HANDBOOK_KO.md').read_text(encoding='utf-8')
        coverage = (ROOT / 'docs' / 'CAP_COVERAGE.md').read_text(encoding='utf-8')
        self.assertIn('<!-- handbook-section:terms-overlay -->', handbook)
        self.assertIn('상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).', handbook)
        self.assertIn(LABEL, handbook)
        self.assertIn('상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).', coverage)
        self.assertIn('CAPITAL-TERMS-V1', coverage)


class TermsHttpUnboundTests(unittest.TestCase):
    def test_case_view_on_an_unbound_policy_has_no_numbers(self):
        text = NOTE.read_text(encoding='utf-8').replace('"status": "ADOPTED"', '"status": "UNDETERMINED"')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'note.md'
            path.write_text(text, encoding='utf-8')
            service = CapitalService(terms=DecisionNoteTermsPolicy(path))
            service.execute({
                'instance_id': service.instance_id, 'operation_id': 'offer', 'op': 'offer',
                'advance_id': 'sim-a', 'args': {'fixture_id': 'sim-committed', 'amount': 1000},
            })
            before = (copy.deepcopy(service.receipts), service.machine.state_digest(), len(service.receipts),
                      service.machine.view('sim-a')['reserved_open'])
            body = service.case_terms('sim-a', service.instance_id, 0, 1)
            self.assertEqual(body['status'], 'NOT_BOUND')
            self.assertEqual(body['reason'], 'terms not bound')
            self.assertEqual(body['label'], LABEL)
            self.assertFalse(_has_number(body))
            self.assertNotIn('principal', body)
            self.assertNotIn('tier', body)
            after = (service.receipts, service.machine.state_digest(), len(service.receipts),
                     service.machine.view('sim-a')['reserved_open'])
            self.assertEqual(after[1:], before[1:])
            self.assertEqual(after[0], before[0])
            with self.assertRaises(ApiError) as caught:
                service.case_terms('sim-missing', service.instance_id, 0, 0)
            self.assertEqual(caught.exception.status, 404)


if __name__ == '__main__':
    unittest.main()
