"""Overlay ledger: sim_day clock, ACT/365 interest memo postings, envelope v2 restore.

Every number is SIMULATED. The expected values are recomputed here from the
CAPITAL-TERMS-V1 block, never read back from the code under test, except the one
golden literal (700 bps for tier T1) that pins the note itself.
"""
import ast
import copy
import hashlib
import importlib.util
import json
import re
import tempfile
import threading
import unittest
from fractions import Fraction
from http.client import HTTPConnection
from pathlib import Path

from capital import overlay
from capital.auth import ROLES
from capital.server import make_server
from capital.service import ApiError, CapitalService
from capital.store import FileWorkspace, WorkspaceError, canonical_bytes, envelope_kind, verify_document
from capital.terms import DecisionNoteTermsPolicy, read_decision_block

ROOT = Path(__file__).resolve().parents[1]
TERMS_NOTE = ROOT / 'docs' / 'decisions' / 'CAPITAL_FINANCIAL_TERMS.md'
GOLDEN_DIR = ROOT / 'tests' / 'golden'
OVERLAY_PY = ROOT / 'capital' / 'overlay.py'
ACTOR = 'LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED'


def _load_seed():
    spec = importlib.util.spec_from_file_location('seed_demo', ROOT / 'scripts' / 'seed_demo.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed = _load_seed()


def terms_value(name):
    return read_decision_block(TERMS_NOTE)['entries'][name]['value']


def tier(short):
    return next(row for row in terms_value('interest_rate')['tiers'] if row['id'].startswith(short + '_'))


def formula(person_days, bps):
    """floor(sum(outstanding*days) * bps / (10000 * 365)) from the note's ACT_365_FIXED."""
    day_count = int(re.fullmatch(r'ACT_(\d+)_FIXED', terms_value('interest_rate')['day_count']).group(1))
    return (person_days * bps) // (10000 * day_count)


def run(service, op, advance, key, **args):
    return service.execute({'instance_id': service.instance_id, 'operation_id': key, 'op': op,
                            'advance_id': advance, 'args': args})


def draw_book(service, advance='sim-a', fixture='sim-committed', amount=90000, prefix='a'):
    run(service, 'offer', advance, f'{prefix}-offer', fixture_id=fixture, amount=amount)
    run(service, 'approve', advance, f'{prefix}-approve')
    run(service, 'bind_settlement', advance, f'{prefix}-bind')
    receipt = run(service, 'draw', advance, f'{prefix}-draw')
    assert receipt['outcome'] == 'ACCEPTED', receipt
    return receipt


def tick(service, key, start, end, reason='test tick', role='organizer'):
    return service.overlay_command({
        'instance_id': service.instance_id, 'operation_id': key, 'op': 'advance_day',
        'from_sim_day': start, 'to_sim_day': end, 'reason': reason}, role=role)


def row(service, advance='sim-a'):
    return next(item for item in service.overlay_state()['advances'] if item['advance_id'] == advance)


def f04_view(service):
    return (service.machine.state_digest(), len(service.receipts), service.machine.export_journal(),
            service.machine.canonical_state())


class AccrualTests(unittest.TestCase):
    def setUp(self):
        self.service = CapitalService()
        draw_book(self.service)

    def test_note_golden_literals(self):
        # The one literal pinned from the note: T1 all-in 700 bps/yr, ACT/365, floor, carry.
        self.assertEqual(tier('T1')['all_in_bps_annual'], 700)
        self.assertEqual(terms_value('interest_rate')['day_count'], 'ACT_365_FIXED')
        self.assertEqual(terms_value('interest_rate')['default_interest_add_bps_annual'], 300)

    def test_t1_golden_vector_equals_the_decision_formula_and_the_remainder_carries(self):
        bps = tier('T1')['all_in_bps_annual']
        first = tick(self.service, 'c-1', 0, 3)
        second = tick(self.service, 'c-2', 3, 6)
        posted = [first['postings'][0]['posted_contract_krw'], second['postings'][0]['posted_contract_krw']]
        exact = Fraction(90000 * 6 * bps, 10000 * 365)
        # Independent floors of the two periods lose a KRW; the carried remainder gives it back.
        naive = formula(90000 * 3, bps) * 2
        self.assertEqual(posted, [51, 52])
        self.assertEqual(naive, 102)
        self.assertEqual(sum(posted), formula(90000 * 6, bps))
        self.assertEqual(sum(posted), exact.numerator // exact.denominator)
        self.assertEqual(sum(posted), 103)
        current = row(self.service)
        self.assertEqual(current['tier'], 'T1')
        self.assertEqual(current['interest_due_krw'], 103)
        self.assertEqual(current['default_interest_due_krw'], 0)
        self.assertEqual(current['cumulative_exact_contract'], f'{exact.numerator}/{exact.denominator}')
        remainder = exact - 103
        self.assertEqual(current['carried_remainder_contract'], f'{remainder.numerator}/{remainder.denominator}')
        self.assertEqual(current['accrued_through_sim_day'], 6)

    def test_matches_the_read_only_allocation_quote(self):
        tick(self.service, 'c-1', 0, 10)
        tick(self.service, 'c-2', 10, 75)
        quote = self.service.case_allocation('sim-a', self.service.instance_id, draw_day=0, as_of_day=75,
                                             cash=10 ** 6)
        current = row(self.service)
        self.assertEqual(current['interest_due_krw'], quote['interest']['interest_due_krw'])
        self.assertEqual(current['default_interest_due_krw'], quote['interest']['default_interest_due_krw'])
        self.assertEqual(current['maturity_day'], quote['interest']['maturity_day'])
        # Independent recompute: 60 contract days at 700 bps, the rest at 700 + 300.
        self.assertEqual(current['interest_due_krw'], formula(90000 * 60, 700))
        self.assertEqual(current['default_interest_due_krw'], formula(90000 * 15, 1000))
        self.assertEqual((current['contract_bps'], current['default_bps']), (700, 1000))

    def test_partial_repay_changes_the_principal_for_later_days_only(self):
        tick(self.service, 'c-1', 0, 10)
        run(self.service, 'repay', 'sim-a', 'a-repay', amount=20000, sequence=1)
        tick(self.service, 'c-2', 10, 20)
        expected = formula(90000 * 10 + 70000 * 10, 700)
        self.assertEqual(row(self.service)['interest_due_krw'], expected)
        self.assertEqual(row(self.service)['principal_outstanding_krw'], 70000)

    def test_accrual_stops_at_the_note_writeoff_day(self):
        tick(self.service, 'c-1', 0, 170)
        term = terms_value('term')
        loss = terms_value('default_loss_treatment')
        maturity = term['standard_term_days']
        writeoff = maturity + term['grace_days_after_maturity'] + 1 + loss['writeoff_days_after_default']
        current = row(self.service)
        self.assertEqual(current['writeoff_day'], writeoff)
        self.assertEqual(current['accrued_through_sim_day'], writeoff)
        self.assertEqual(current['interest_due_krw'], formula(90000 * maturity, 700))
        self.assertEqual(current['default_interest_due_krw'], formula(90000 * (writeoff - maturity), 1000))
        tick(self.service, 'c-2', 170, 200)
        self.assertEqual(row(self.service)['accrued_through_sim_day'], writeoff)

    def test_a_draw_then_one_tick_posts_exactly_one_day(self):
        receipt = tick(self.service, 'c-1', 0, 1)
        self.assertEqual(receipt['postings'][0]['posted_contract_krw'], formula(90000, 700))
        entry = self.service.overlay_entries[-1]
        self.assertEqual((entry['payload']['contractual_days'], entry['payload']['default_days']), (1, 0))

    def test_draw_day_follows_the_clock(self):
        service = CapitalService()
        tick(service, 'c-1', 0, 10)
        draw_book(service)
        tick(service, 'c-2', 10, 20)
        entry = service.overlay_entries[-1]
        self.assertEqual((entry['payload']['draw_day'], entry['payload']['contractual_days']), (10, 10))
        self.assertEqual(row(service)['interest_due_krw'], formula(90000 * 10, 700))
        self.assertEqual(row(service)['maturity_day'], 70)

    def test_tier_comes_from_the_draw_receipt_gate_and_defaulted_cases_keep_accruing(self):
        service = seed.build_service()
        tick(service, 'c-1', 0, 30)
        by_id = {item['advance_id']: item for item in service.overlay_state()['advances']}
        self.assertEqual(by_id['sim-unbound']['tier'], 'T2')
        self.assertEqual(by_id['sim-defaulted']['tier'], 'T1')
        self.assertEqual(by_id['sim-defaulted']['phase'], 'DEFAULTED')
        t2, t1 = tier('T2')['all_in_bps_annual'], tier('T1')['all_in_bps_annual']
        self.assertEqual(by_id['sim-unbound']['interest_due_krw'], formula(15000 * 30, t2))
        self.assertEqual(by_id['sim-defaulted']['interest_due_krw'], formula(30000 * 30, t1))
        self.assertEqual(by_id['sim-closed']['interest_due_krw'], 0)
        posted = {e['payload']['advance_id'] for e in service.overlay_entries if e['kind'] == 'interest_posting'}
        self.assertEqual(posted, {'sim-unbound', 'sim-defaulted'})

    def test_no_accrual_without_a_draw_but_the_clock_still_advances(self):
        service = CapitalService()
        run(service, 'offer', 'sim-b', 'b-offer', fixture_id='sim-committed', amount=1000)
        receipt = tick(service, 'c-1', 0, 5)
        self.assertEqual(receipt['postings'], [])
        self.assertEqual(service.overlay_state()['sim_day'], 5)
        self.assertEqual(service.overlay_state()['advances'], [])

    def test_allocation_proposal_uses_the_note_order_and_close_ready_is_read_only(self):
        tick(self.service, 'c-1', 0, 75)
        current = row(self.service)
        self.assertEqual(current['allocation']['order'], terms_value('interest_rate')['repayment_allocation_order'])
        self.assertEqual(current['allocation']['to_default_interest'], current['default_interest_due_krw'])
        self.assertEqual(current['allocation']['to_interest'], current['interest_due_krw'])
        self.assertEqual(current['allocation']['to_principal'], 90000)
        self.assertEqual(current['fsm_repay'], {'amount': 90000, 'sequence': 1, 'proposal_only': True})
        self.assertFalse(current['close_ready'])
        before = f04_view(self.service)
        self.service.overlay_state()
        self.assertEqual(f04_view(self.service), before)

    def test_close_ready_only_when_principal_and_dues_are_zero(self):
        service = CapitalService()
        draw_book(service)
        run(service, 'repay', 'sim-a', 'a-repay', amount=90000, sequence=1)
        self.assertTrue(row(service)['close_ready'])
        tick(service, 'c-1', 0, 5)
        self.assertEqual(row(service)['interest_due_krw'], 0)
        self.assertTrue(row(service)['close_ready'])
        service2 = CapitalService()
        draw_book(service2)
        tick(service2, 'c-1', 0, 5)
        run(service2, 'repay', 'sim-a', 'a-repay', amount=90000, sequence=1)
        self.assertGreater(row(service2)['interest_due_krw'], 0)
        self.assertFalse(row(service2)['close_ready'])
        self.assertEqual(run(service2, 'close', 'sim-a', 'a-close')['outcome'], 'ACCEPTED')  # the FSM is never gated


class ContractTests(unittest.TestCase):
    def test_live_bodies_validate_against_the_closed_facade_schema(self):
        spec = importlib.util.spec_from_file_location('facade_schema', ROOT / 'tests' / 'facade_schema.py')
        facade = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(facade)
        doc = facade.load_contract()
        routes = {(row['method'], row['path']): row for row in doc['routes']}
        quote_schema = routes[('GET', '/api/overlay')]['response']
        receipt_schema = routes[('POST', '/api/overlay/commands')]['response']
        service = seed.build_service()
        facade.validate(service.overlay_state(), quote_schema, doc)
        receipt = tick(service, 'c-1', 0, 75)
        facade.validate(receipt, receipt_schema, doc)
        facade.validate(tick(service, 'c-1', 0, 75), receipt_schema, doc)
        quote = service.overlay_state('c-1')
        self.assertTrue(any(item['phase'] == 'DEFAULTED' for item in quote['advances']))
        facade.validate(quote, quote_schema, doc)
        facade.validate(service.overlay_state('c-nope'), quote_schema, doc)
        quote['advances'][0]['surprise'] = 1
        with self.assertRaises(facade.SchemaError):
            facade.validate(quote, quote_schema, doc)
        with tempfile.TemporaryDirectory() as tmp:
            bare = CapitalService(terms=DecisionNoteTermsPolicy(Path(tmp) / 'absent.md'))
            facade.validate(bare.overlay_state(), quote_schema, doc)

    def test_no_name_collides_with_the_promoted_catalogue(self):
        text = (ROOT / 'capital' / 'contract' / 'facade-v1.json').read_text(encoding='utf-8')
        self.assertNotIn('advance_clock', text)


class ClockTests(unittest.TestCase):
    def setUp(self):
        self.service = CapitalService()

    def refuse(self, code, status, body_changes=None, key='c-x', start=0, end=5):
        body = {'instance_id': self.service.instance_id, 'operation_id': key, 'op': 'advance_day',
                'from_sim_day': start, 'to_sim_day': end, 'reason': 'r'}
        body.update(body_changes or {})
        before = (copy.deepcopy(self.service.overlay_entries), f04_view(self.service))
        with self.assertRaises(ApiError) as caught:
            self.service.overlay_command(body)
        self.assertEqual((caught.exception.code, caught.exception.status), (code, status))
        self.assertEqual((self.service.overlay_entries, f04_view(self.service)), before)
        return caught.exception

    def test_cas_monotone_and_step_vectors(self):
        tick(self.service, 'c-1', 0, 5)
        self.assertEqual(self.refuse('SIM_CLOCK_STALE', 409, start=0, end=9).detail, {'sim_day': 5})
        self.refuse('SIM_CLOCK_NOT_ADVANCING', 400, start=5, end=5)
        self.refuse('SIM_CLOCK_NOT_ADVANCING', 400, start=5, end=2)
        step = overlay.load_bounds()['max_step_days']
        self.refuse('SIM_CLOCK_STEP', 400, start=5, end=5 + step + 1)
        self.assertEqual(tick(self.service, 'c-2', 5, 5 + step)['sim_day'], 5 + step)

    def test_sim_day_max_is_a_capacity_refusal(self):
        bounds = overlay.load_bounds()
        day, index = 0, 0
        while day < bounds['SIM_DAY_MAX']:
            nxt = min(day + bounds['max_step_days'], bounds['SIM_DAY_MAX'])
            index += 1
            tick(self.service, f'c-{index}', day, nxt)
            day = nxt
        self.assertEqual(self.service.overlay_state()['sim_day'], bounds['SIM_DAY_MAX'])
        error = self.refuse('SIMULATION_CAPACITY', 409, key='c-over', start=day, end=day + 1)
        self.assertEqual(error.detail, {'bound': 'SIM_DAY_MAX'})

    def test_idempotent_replay_and_conflict(self):
        first = tick(self.service, 'c-1', 0, 5)
        self.assertFalse(first['transport_duplicate'])
        again = tick(self.service, 'c-1', 0, 5)
        self.assertTrue(again['transport_duplicate'])
        self.assertEqual(again['postings'], first['postings'])
        self.assertEqual(self.service.overlay_state()['sim_day'], 5)
        self.refuse('IDEMPOTENCY_CONFLICT', 409, key='c-1', start=0, end=6)
        self.refuse('IDEMPOTENCY_CONFLICT', 409, key='c-1', start=0, end=5, body_changes={'reason': 'other'})
        self.assertEqual(len(self.service.overlay_entries), 2)  # terms binding + clock

    def test_lost_response_lookup_by_operation_id(self):
        tick(self.service, 'c-1', 0, 5)
        known = self.service.overlay_state('c-1')['operation']
        self.assertEqual((known['outcome'], known['sim_day']), ('APPLIED', 5))
        unknown = self.service.overlay_state('c-never')['operation']
        self.assertEqual(unknown, {'outcome': 'UNKNOWN', 'operation_id': 'c-never', 'retry_authorized': False})

    def test_strict_input_and_volatile_keys_write_nothing(self):
        self.refuse('OVERLAY_VOLATILE_KEY', 400, body_changes={'created_at': 'x'})
        self.refuse('OVERLAY_VOLATILE_KEY', 400, body_changes={'timestamp': 1})
        self.refuse('OVERLAY_VOLATILE_KEY', 400, body_changes={'reason': {'saved_at': 'x'}})
        self.refuse('INVALID_COMMAND', 400, body_changes={'extra': 1})
        self.refuse('SESSION_CHANGED', 409, body_changes={'instance_id': 'someone-else'})
        self.refuse('UNSUPPORTED_OPERATION', 400, body_changes={'op': 'advance_clock'})
        self.refuse('INVALID_OPERATION_ID', 400, body_changes={'operation_id': 'bad id!'})
        self.refuse('INVALID_ARGUMENTS', 400, body_changes={'to_sim_day': True})
        self.refuse('INVALID_ARGUMENTS', 400, body_changes={'to_sim_day': -1})
        self.refuse('INVALID_ARGUMENTS', 400, body_changes={'to_sim_day': 1.5})
        self.refuse('INVALID_ARGUMENTS', 400, body_changes={'to_sim_day': 1234567})
        self.refuse('INVALID_ARGUMENTS', 400, body_changes={'reason': ''})
        self.refuse('INVALID_ARGUMENTS', 400, body_changes={'reason': 'x' * 121})
        self.refuse('INVALID_ARGUMENTS', 400, body_changes={'reason': 5})
        with self.assertRaises(ApiError) as caught:
            self.service.overlay_command(['not', 'an', 'object'])
        self.assertEqual(caught.exception.code, 'INVALID_COMMAND')
        self.assertEqual(self.service.overlay_entries, [])

    def test_non_active_workspace_refuses(self):
        self.service.workspace_status = 'WORKSPACE_UNREADABLE'
        self.refuse('WORKSPACE_UNREADABLE', 503)

    def test_role_check_runs_first(self):
        for role in ('auditor', 'observer', 'agent', 'nobody'):
            with self.assertRaises(ApiError) as caught:
                tick(self.service, 'c-1', 0, 5, role=role)
            self.assertEqual((caught.exception.code, caught.exception.status), ('ROLE_FORBIDDEN', 403))
        self.assertEqual(self.service.overlay_entries, [])

    def test_capacity_bounds_fail_closed_without_writing(self):
        bounds = overlay.load_bounds()
        tight = CapitalService(overlay_bounds={**bounds, 'OVERLAY_MAX_ENTRIES': 2})
        tick(tight, 'c-1', 0, 5)
        before = (copy.deepcopy(tight.overlay_entries), f04_view(tight))
        with self.assertRaises(ApiError) as caught:
            tick(tight, 'c-2', 5, 6)
        self.assertEqual((caught.exception.code, caught.exception.status, caught.exception.detail),
                         ('SIMULATION_CAPACITY', 409, {'bound': 'OVERLAY_MAX_ENTRIES'}))
        self.assertEqual((tight.overlay_entries, f04_view(tight)), before)
        small = CapitalService(overlay_bounds={**bounds, 'OVERLAY_ENTRY_MAX_BYTES': 40})
        with self.assertRaises(ApiError) as caught:
            tick(small, 'c-1', 0, 5)
        self.assertEqual(caught.exception.detail, {'bound': 'OVERLAY_ENTRY_MAX_BYTES'})
        self.assertEqual(small.overlay_entries, [])
        envelope_small = CapitalService(overlay_bounds={**bounds, 'ENVELOPE_MAX_BYTES': 100})
        with self.assertRaises(ApiError) as caught:
            tick(envelope_small, 'c-1', 0, 5)
        self.assertEqual(caught.exception.detail, {'bound': 'ENVELOPE_MAX_BYTES'})
        records = CapitalService(overlay_bounds={**bounds, 'DECISION_RECORDS_MAX': 1})
        tick(records, 'c-1', 0, 5)  # one binding fits; there is only ever one
        self.assertEqual(records.overlay_state()['capacity']['decision_records'], {'current': 1, 'max': 1})

    def test_bounds_come_from_the_adopted_notes(self):
        bounds = overlay.load_bounds()
        state = read_decision_block(ROOT / 'docs' / 'decisions' / 'CAPITAL_OVERLAY_STATE.md')
        export = read_decision_block(ROOT / 'docs' / 'decisions' / 'CAPITAL_OVERLAY_DIGEST_EXPORT.md')
        value = state['entries']['overlay_capacity_bounds']['value']
        for name in overlay.BOUND_NAMES:
            self.assertEqual(bounds[name], value[name])
        self.assertEqual(bounds['max_step_days'], export['entries']['clock_command_authority']['value']['max_step_days'])
        self.assertEqual((bounds['SIM_DAY_MAX'], bounds['max_step_days']), (3650, 366))
        self.assertIsNone(overlay.load_bounds(ROOT / 'no-such-note.md'))
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / 'state.md'
            broken.write_text((ROOT / 'docs' / 'decisions' / 'CAPITAL_OVERLAY_STATE.md').read_text(encoding='utf-8')
                              .replace('"status": "ADOPTED"', '"status": "UNDETERMINED"'), encoding='utf-8')
            self.assertIsNone(overlay.load_bounds(broken))

    def test_overlay_commands_leave_f04_and_the_demo_golden_untouched(self):
        service = seed.build_service()
        golden = json.loads((GOLDEN_DIR / 'demo.json').read_text(encoding='utf-8'))
        self.assertEqual(seed.capture(service), golden)
        before = f04_view(service)
        manifest_before = service.export_manifest()
        self.assertEqual(manifest_before['format'], 'KIX_CAPITAL_EXPORT_MANIFEST_V2')
        self.assertNotIn('overlay', manifest_before['sections'])
        tick(service, 'c-1', 0, 60)
        tick(service, 'c-2', 60, 75)
        self.assertEqual(f04_view(service), before)
        # The risk pin reads the sim_day clock and the manifest content_digest moves to V3 with a
        # non-empty overlay, so those two keys alone move with the tick; every other key is byte-equal.
        moved = seed.capture(service)
        clock_bound = {'risk', 'content_digest'}
        self.assertEqual({key: value for key, value in moved.items() if key not in clock_bound},
                         {key: value for key, value in golden.items() if key not in clock_bound})
        self.assertEqual(moved['risk']['sim_day'], 75)
        self.assertNotEqual(moved['risk']['risk_digest'], golden['risk']['risk_digest'])
        self.assertEqual(moved['risk']['outstanding_krw'], golden['risk']['outstanding_krw'])
        self.assertEqual(manifest_before['content_digest'], golden['content_digest'])
        # A non-empty overlay moves the manifest to V3 (CAPITAL_OVERLAY_DIGEST_EXPORT.md 3.2);
        # the F04 state digest and the V2 golden itself are untouched.
        manifest_after = service.export_manifest()
        self.assertEqual(manifest_after['format'], 'KIX_CAPITAL_EXPORT_MANIFEST_V3')
        self.assertIn('overlay', manifest_after['sections'])
        self.assertNotEqual(manifest_after['content_digest'], golden['content_digest'])
        self.assertEqual(moved['content_digest'], manifest_after['content_digest'])
        self.assertEqual(service.snapshot()['state_digest'], golden['state_digest'])
        self.assertNotIn('overlay', service.snapshot())


class NotBoundTests(unittest.TestCase):
    def check_refused(self, terms):
        service = CapitalService(terms=terms)
        draw_book(service)
        before = (service.overlay_entries, f04_view(service))
        with self.assertRaises(ApiError) as caught:
            tick(service, 'c-1', 0, 30)
        self.assertEqual((caught.exception.code, caught.exception.status, caught.exception.detail),
                         ('NOT_BOUND', 400, {'reason': 'terms not bound'}))
        self.assertEqual((service.overlay_entries, f04_view(service)), before)
        quote = service.overlay_state()
        self.assertEqual((quote['status'], quote['reason'], quote['advances'], quote['sim_day']),
                         ('NOT_BOUND', 'terms not bound', [], 0))
        self.assertEqual(service.overlay_entries, [])

    def test_missing_note(self):
        self.check_refused(DecisionNoteTermsPolicy(ROOT / 'docs' / 'decisions' / 'no-such-note.md'))

    def test_interest_rate_undetermined(self):
        text = TERMS_NOTE.read_text(encoding='utf-8')
        start = text.index('"interest_rate"')
        marked = text[:start] + text[start:].replace('"status": "ADOPTED"', '"status": "UNDETERMINED"', 1)
        self.assertNotEqual(marked, text)
        with tempfile.TemporaryDirectory() as tmp:
            note = Path(tmp) / 'terms.md'
            note.write_text(marked, encoding='utf-8')
            policy = DecisionNoteTermsPolicy(note)
            self.assertEqual(policy.status()['items']['interest_rate'], 'UNDETERMINED')
            self.check_refused(policy)

    def test_all_undetermined(self):
        with tempfile.TemporaryDirectory() as tmp:
            note = Path(tmp) / 'terms.md'
            note.write_text(TERMS_NOTE.read_text(encoding='utf-8').replace('"status": "ADOPTED"', '"status": "UNDETERMINED"'),
                            encoding='utf-8')
            self.check_refused(DecisionNoteTermsPolicy(note))

    def test_a_port_without_ledger_terms_is_not_bound(self):
        class Bare:
            def __init__(self, inner):
                self.inner = inner

            def status(self):
                return self.inner.status()

            def __getattr__(self, name):
                if name in ('ledger_terms', 'allocate'):
                    raise AttributeError(name)
                return getattr(self.inner, name)

        self.check_refused(Bare(DecisionNoteTermsPolicy()))

    def test_changed_terms_version_is_refused_after_binding(self):
        service = CapitalService()
        draw_book(service)
        tick(service, 'c-1', 0, 5)
        with tempfile.TemporaryDirectory() as tmp:
            note = Path(tmp) / 'terms.md'
            note.write_text(TERMS_NOTE.read_text(encoding='utf-8').replace('CAPITAL-TERMS-V1', 'CAPITAL-TERMS-V2'),
                            encoding='utf-8')
            service.terms = DecisionNoteTermsPolicy(note)
            self.assertEqual(service.terms.status()['terms_version'], 'CAPITAL-TERMS-V2')
            with self.assertRaises(ApiError) as caught:
                tick(service, 'c-2', 5, 9)
            self.assertEqual((caught.exception.code, caught.exception.detail), ('NOT_BOUND', {'reason': 'terms version mismatch'}))
            self.assertFalse(service.overlay_state()['terms_binding_matches'])
        self.assertEqual(service.overlay_state()['sim_day'], 5)


class FoldTests(unittest.TestCase):
    def entries(self):
        service = CapitalService()
        draw_book(service)
        tick(service, 'c-1', 0, 10)
        tick(service, 'c-2', 10, 20)
        return copy.deepcopy(service.overlay_entries), len(service.machine.export_journal())

    def test_fold_is_deterministic_and_digest_is_domain_tagged(self):
        entries, length = self.entries()
        state = overlay.fold(entries, length)
        self.assertEqual(state, overlay.fold(copy.deepcopy(entries), length))
        material = canonical_bytes({'domain': 'KIX_CAPITAL_OVERLAY_STATE_DIGEST_V1', 'overlay_schema': 1, 'state': state})
        self.assertEqual(overlay.state_digest(state), hashlib.sha256(material).hexdigest())
        self.assertEqual(sorted(state['sections']), sorted(
            ['clock', 'interest_ledger', 'recovery_ledger', 'decision_records', 'agent_proposals']))
        self.assertEqual(state['sections']['recovery_ledger'], [])
        self.assertEqual(state['entry_count'], len(entries))
        section = overlay.build_section(entries)
        self.assertEqual(overlay.restore(section, length), entries)

    def test_identical_duplicate_is_ignored_and_a_conflicting_one_fails_closed(self):
        entries, length = self.entries()
        self.assertEqual(overlay.fold(entries + [copy.deepcopy(entries[1])], length), overlay.fold(entries, length))
        conflicting = copy.deepcopy(entries[1])
        conflicting['payload']['reason'] = 'different'
        with self.assertRaises(overlay.OverlayError):
            overlay.fold(entries + [conflicting], length)

    def test_every_violation_raises(self):
        entries, length = self.entries()
        clock = next(i for i, e in enumerate(entries) if e['kind'] == 'clock' and e['overlay_id'] == 'c-2')
        posting = next(i for i, e in enumerate(entries) if e['kind'] == 'interest_posting' and e['overlay_id'].startswith('c-2'))

        def broken(index, path, value):
            copy_ = copy.deepcopy(entries)
            node = copy_[index]
            for part in path[:-1]:
                node = node[part]
            node[path[-1]] = value
            return copy_

        cases = {
            'clock from is not the folded day': broken(clock, ('payload', 'from_sim_day'), 11),
            'clock rewinds': broken(clock, ('payload', 'to_sim_day'), 5),
            'entry sim_day differs from the clock': broken(clock, ('sim_day',), 21),
            'dangling after_journal_index': broken(clock, ('after_journal_index',), length + 1),
            'unknown payload key': broken(clock, ('payload', 'extra'), 1),
            'bool day': broken(clock, ('payload', 'to_sim_day'), True),
            'wrong actor': broken(clock, ('payload', 'actor'), 'someone'),
            'posting not the cumulative floor': broken(posting, ('payload', 'posted_contract_krw'), 999),
            'unreduced fraction': broken(posting, ('payload', 'cumulative_contract_exact'), '2/4'),
            'accrual backwards': broken(posting, ('payload', 'cumulative_contract_exact'), '1/1'),
            'posting for another terms version': broken(posting, ('payload', 'terms_version'), 'OTHER'),
            'unknown kind': broken(clock, ('kind',), 'margin_call'),
            'empty id': broken(clock, ('overlay_id',), ''),
        }
        for name, bad in cases.items():
            with self.subTest(name), self.assertRaises(overlay.OverlayError):
                overlay.fold(bad, length)
        with self.assertRaises(overlay.OverlayError):
            overlay.fold(list(reversed(entries)), length)
        with self.assertRaises(overlay.OverlayError):
            overlay.fold(entries[1:], length)  # no terms binding before the clock/posting
        with self.assertRaises(overlay.OverlayError):
            overlay.fold('not a list')

    def test_overlay_module_integers_are_only_zero_one_and_two(self):
        found = []

        class Visitor(ast.NodeVisitor):
            def visit_Constant(self, node):
                if type(node.value) in (int, float):
                    found.append(node.value)

        Visitor().visit(ast.parse(OVERLAY_PY.read_text(encoding='utf-8')))
        self.assertTrue(set(found) <= {0, 1, 2}, sorted(set(found)))


class EnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.ports = []

    def tearDown(self):
        for port in self.ports:
            port.close()
        self.tmp.cleanup()

    def open(self):
        port = FileWorkspace.open(self.dir)
        self.ports.append(port)
        return CapitalService(port)

    def close_all(self):
        for port in self.ports:
            port.close()
        self.ports.clear()

    def document(self):
        return json.loads((self.dir / 'workspace.json').read_text(encoding='utf-8'))

    def write(self, document):
        (self.dir / 'workspace.json').write_bytes(canonical_bytes(document))

    def seeded(self):
        service = self.open()
        draw_book(service)
        tick(service, 'c-1', 0, 10)
        tick(service, 'c-2', 10, 75)
        result = (service.overlay_state()['sim_day'], row(service)['interest_due_krw'],
                  row(service)['default_interest_due_krw'], service.overlay_state()['overlay_state_digest'],
                  service.machine.state_digest())
        self.close_all()
        return result

    def test_restart_restores_the_overlay_and_the_same_interest_due(self):
        sim_day, interest, default, digest, state_digest = self.seeded()
        self.assertEqual((interest, default), (formula(90000 * 60, 700), formula(90000 * 15, 1000)))
        restored = self.open()
        self.assertEqual(restored.workspace_status, 'ACTIVE')
        quote = restored.overlay_state()
        self.assertEqual((quote['sim_day'], quote['overlay_state_digest']), (sim_day, digest))
        self.assertEqual((row(restored)['interest_due_krw'], row(restored)['default_interest_due_krw']), (interest, default))
        self.assertEqual(restored.machine.state_digest(), state_digest)
        # The restored overlay keeps accruing from where it stopped, exactly as one unbroken run would.
        tick(restored, 'c-3', 75, 80)
        fresh = CapitalService()
        draw_book(fresh)
        tick(fresh, 'c-1', 0, 10)
        tick(fresh, 'c-2', 10, 75)
        tick(fresh, 'c-3', 75, 80)
        self.assertEqual(row(restored), row(fresh))
        self.assertEqual(restored.overlay_state()['overlay_state_digest'], fresh.overlay_state()['overlay_state_digest'])
        replay = tick(restored, 'c-1', 0, 10)
        self.assertTrue(replay['transport_duplicate'])

    def test_the_file_is_envelope_v2_and_payload_checksum_is_unchanged(self):
        self.seeded()
        document = self.document()
        self.assertEqual(envelope_kind(document), 2)
        self.assertEqual(document['envelope_version'], 2)
        self.assertEqual(document['format'], 'KIX_CAPITAL_LOCAL_WORKSPACE_V1')
        self.assertEqual(document['payload_sha256'], hashlib.sha256(canonical_bytes(document['payload'])).hexdigest())
        self.assertEqual(set(document['payload']), {'receipts', 'journal', 'case_fixtures', 'state_digest'})
        self.assertEqual(document['overlay']['overlay_schema'], 1)
        self.assertEqual(verify_document(document), document)

    def test_command_only_workspace_carries_the_empty_overlay_section(self):
        service = self.open()
        draw_book(service)
        self.close_all()
        document = self.document()
        self.assertEqual(document['overlay'], overlay.empty_section())
        self.assertEqual(document['overlay']['journal'], [])

    def test_legacy_v1_loads_as_empty_overlay_and_promotes_on_the_next_save(self):
        service = self.open()
        draw_book(service)
        self.close_all()
        document = self.document()
        payload_bytes = canonical_bytes(document['payload'])
        legacy = {key: value for key, value in document.items() if key not in ('envelope_version', 'overlay')}
        self.write(legacy)
        self.assertEqual(envelope_kind(legacy), 1)
        restored = self.open()
        self.assertEqual(restored.workspace_status, 'ACTIVE')
        self.assertEqual((restored.overlay_state()['sim_day'], restored.overlay_state()['entry_count']), (0, 0))
        self.assertNotIn('envelope_version', json.loads((self.dir / 'workspace.json').read_text(encoding='utf-8')))
        tick(restored, 'c-1', 0, 5)
        self.close_all()
        promoted = self.document()
        self.assertEqual(promoted['envelope_version'], 2)
        self.assertEqual(canonical_bytes(promoted['payload']), payload_bytes)
        self.assertEqual(promoted['payload_sha256'], document['payload_sha256'])
        self.assertEqual([e['kind'] for e in promoted['overlay']['journal']], ['terms_binding', 'clock', 'interest_posting'])

    def assert_fail_closed(self, mutate, label):
        self.seeded()
        document = self.document()
        mutate(document)
        self.write(document)
        before = (self.dir / 'workspace.json').read_bytes()
        service = self.open()
        self.assertEqual(service.workspace_status, 'WORKSPACE_UNREADABLE', label)
        self.assertEqual(service.overlay_entries, [], label)
        with self.assertRaises(ApiError) as caught:
            tick(service, 'c-new', 0, 1)
        self.assertEqual((caught.exception.code, caught.exception.status), ('WORKSPACE_UNREADABLE', 503), label)
        with self.assertRaises(ApiError) as caught:
            run(service, 'offer', 'sim-z', 'z-offer', fixture_id='sim-committed', amount=100)
        self.assertEqual(caught.exception.status, 503, label)
        self.assertEqual(service.overlay_state()['workspace_status'], 'WORKSPACE_UNREADABLE', label)
        self.assertEqual((self.dir / 'workspace.json').read_bytes(), before, label)  # never replaced by an empty overlay
        self.close_all()

    def test_tampered_overlay_sections_are_refused_and_never_replaced(self):
        def edit_entry(document):
            document['overlay']['journal'][2]['payload']['posted_contract_krw'] += 1

        def edit_entry_and_resign(document):
            edit_entry(document)
            from capital.store import section_checksum
            document['overlay']['section_sha256'] = section_checksum(document['overlay'])

        def stale_state(document):
            from capital.store import section_checksum
            document['overlay']['overlay_state']['state']['sim_day'] += 1
            document['overlay']['section_sha256'] = section_checksum(document['overlay'])

        def stale_digest(document):
            from capital.store import section_checksum
            document['overlay']['overlay_state']['digest'] = '0' * 64
            document['overlay']['section_sha256'] = section_checksum(document['overlay'])

        def dangling(document):
            entries = copy.deepcopy(document['overlay']['journal'])
            for entry in entries:
                entry['after_journal_index'] = 99
            document['overlay'] = overlay.build_section(entries)

        def drop_entry(document):
            from capital.store import section_checksum
            document['overlay']['journal'].pop()
            document['overlay']['section_sha256'] = section_checksum(document['overlay'])

        def empty_replacement(document):
            document['overlay']['journal'] = []

        def bad_schema(document):
            from capital.store import section_checksum
            document['overlay']['overlay_schema'] = 2
            document['overlay']['section_sha256'] = section_checksum(document['overlay'])

        def extra_key(document):
            document['overlay']['extra'] = 1

        def missing_overlay(document):
            del document['overlay']

        def overlay_null(document):
            document['overlay'] = None

        def set_version(value):
            def mutate(document):
                document['envelope_version'] = value
            return mutate

        mutations = {
            'edited entry': edit_entry, 'edited entry, section re-signed': edit_entry_and_resign,
            'stale state, re-signed': stale_state, 'stale digest, re-signed': stale_digest,
            'dangling after_journal_index': dangling, 'dropped last entry': drop_entry,
            'journal emptied': empty_replacement, 'overlay_schema 2': bad_schema, 'extra section key': extra_key,
            'v2 without overlay': missing_overlay, 'overlay null': overlay_null,
            'envelope_version 1': set_version(1), 'envelope_version "2"': set_version('2'),
            'envelope_version true': set_version(True), 'envelope_version null': set_version(None),
            'envelope_version 3': set_version(3), 'envelope_version 2.0': set_version(2.0),
        }
        for label, mutate in mutations.items():
            with self.subTest(label):
                self.assert_fail_closed(mutate, label)
                for name in ('workspace.json', 'workspace.json.lock'):
                    (self.dir / name).unlink(missing_ok=True)

    def test_a_v1_record_with_an_overlay_key_is_not_legacy(self):
        self.seeded()
        document = self.document()
        del document['envelope_version']
        self.write(document)
        service = self.open()
        self.assertEqual(service.workspace_status, 'WORKSPACE_UNREADABLE')

    def test_offline_auditor_accepts_v2_and_fails_closed_on_a_tampered_overlay(self):
        from capital.audit import audit_workspace
        self.seeded()
        report = audit_workspace(self.dir)
        self.assertTrue(report['ok'], report)
        document = self.document()
        document['overlay']['journal'][2]['payload']['posted_contract_krw'] += 1
        self.write(document)
        report = audit_workspace(self.dir)
        self.assertFalse(report['ok'])
        self.assertEqual(report['reason'], 'WORKSPACE_UNREADABLE')


class LiveServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.port = cls.server.server_port
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        status, state = cls.call('GET', '/api/state')
        cls.instance = state['instance_id']
        cls.tokens = {'organizer': state['local_token']}
        for role in ROLES:
            if role != 'organizer':
                cls.tokens[role] = cls.call('POST', '/api/session', {'role': role}, cls.tokens['organizer'])[1]['local_token']

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=2)

    @classmethod
    def call(cls, method, path, body=None, token=None):
        headers = {}
        payload = None
        if body is not None:
            headers['Content-Type'] = 'application/json'
            payload = json.dumps(body).encode()
        if token is not None:
            headers['X-Capital-Token'] = token
        client = HTTPConnection('127.0.0.1', cls.port, timeout=5)
        try:
            client.request(method, path, body=payload, headers=headers)
            response = client.getresponse()
            return response.status, json.loads(response.read().decode('utf-8'))
        finally:
            client.close()

    def body(self, key, start, end):
        return {'instance_id': self.instance, 'operation_id': key, 'op': 'advance_day',
                'from_sim_day': start, 'to_sim_day': end, 'reason': 'live'}

    def test_advance_is_organizer_only_and_get_is_organizer_and_auditor(self):
        before = self.call('GET', '/api/state')[1]
        for role in ('auditor', 'observer', 'agent'):
            status, payload = self.call('POST', '/api/overlay/commands', self.body('live-denied', 0, 1), self.tokens[role])
            self.assertEqual((status, payload['error'], payload['permission']), (403, 'ROLE_FORBIDDEN', 'overlay:command'), role)
        status, payload = self.call('POST', '/api/overlay/commands', self.body('live-denied', 0, 1))
        self.assertEqual((status, payload['error']), (403, 'LOCAL_TOKEN_REQUIRED'))
        self.assertEqual(self.call('GET', '/api/overlay', token=self.tokens['organizer'])[0], 200)
        self.assertEqual(self.call('GET', '/api/overlay', token=self.tokens['auditor'])[0], 200)
        for role in ('observer', 'agent'):
            status, payload = self.call('GET', '/api/overlay', token=self.tokens[role])
            self.assertEqual((status, payload['error']), (403, 'ROLE_FORBIDDEN'), role)
        self.assertEqual(self.call('GET', '/api/overlay')[0], 200)  # no token is the default organizer
        self.assertEqual(self.call('GET', '/api/overlay?operation_id=live-denied', token=self.tokens['auditor'])[1]['operation']['outcome'], 'UNKNOWN')
        status, applied = self.call('POST', '/api/overlay/commands', self.body('live-ok', 0, 2), self.tokens['organizer'])
        self.assertEqual((status, applied['outcome'], applied['sim_day']), (200, 'APPLIED', 2))
        status, quote = self.call('GET', '/api/overlay?operation_id=live-ok', token=self.tokens['auditor'])
        self.assertEqual((quote['sim_day'], quote['operation']['outcome']), (2, 'APPLIED'))
        after = self.call('GET', '/api/state')[1]
        for key in ('state_digest', 'operation_count'):
            self.assertEqual(before[key], after[key])
        self.assertNotIn('overlay', after)

    def test_error_bodies_over_http(self):
        status, payload = self.call('POST', '/api/overlay/commands', self.body('live-stale', 99, 100), self.tokens['organizer'])
        self.assertEqual((status, payload['error']), (409, 'SIM_CLOCK_STALE'))
        status, payload = self.call('POST', '/api/overlay/commands', {**self.body('live-v', 0, 1), 'timestamp': 'x'}, self.tokens['organizer'])
        self.assertEqual((status, payload['error']), (400, 'OVERLAY_VOLATILE_KEY'))

    def test_not_bound_over_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = make_server(0, terms=DecisionNoteTermsPolicy(Path(tmp) / 'absent.md'))
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                def call(method, path, body=None, token=None):
                    headers = {'Content-Type': 'application/json'} if body is not None else {}
                    if token:
                        headers['X-Capital-Token'] = token
                    client = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                    try:
                        client.request(method, path, body=None if body is None else json.dumps(body).encode(), headers=headers)
                        response = client.getresponse()
                        return response.status, json.loads(response.read().decode('utf-8'))
                    finally:
                        client.close()

                state = call('GET', '/api/state')[1]
                status, payload = call('POST', '/api/overlay/commands', {
                    'instance_id': state['instance_id'], 'operation_id': 'nb-1', 'op': 'advance_day',
                    'from_sim_day': 0, 'to_sim_day': 1, 'reason': 'nb'}, state['local_token'])
                self.assertEqual((status, payload['error'], payload['reason']), (400, 'NOT_BOUND', 'terms not bound'))
                status, quote = call('GET', '/api/overlay')
                self.assertEqual((status, quote['status'], quote['reason'], quote['advances']), (200, 'NOT_BOUND', 'terms not bound', []))
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=2)


class GoldenTests(unittest.TestCase):
    """Overlay goldens are pinned once from a verified run and never regenerated by a test."""

    @staticmethod
    def demo_scenario():
        service = seed.build_service()
        tick(service, 'demo-advance-1', 0, 60)
        run(service, 'repay', 'sim-unbound', 'demo-repay-1', amount=5000, sequence=1)
        tick(service, 'demo-advance-2', 60, 75)
        state = overlay.fold(service.overlay_entries, len(service.machine.export_journal()))
        manifest = service.export_manifest()
        return {
            'label': 'SIMULATED', 'overlay_schema': 1,
            'decision_note': 'docs/decisions/CAPITAL_OVERLAY_DIGEST_EXPORT.md 3.2, 3.4 (overlay-digest-export-decision), node audit60-fix2',
            'export_manifest_v3_format': manifest['format'],
            'export_manifest_v3_content_digest': manifest['content_digest'],
            'scenario': 'terms binding -> advance_day 0->60 -> repay sim-unbound 5000 -> advance_day 60->75',
            'sim_day': state['sim_day'], 'entry_count': state['entry_count'],
            'overlay_state_digest': overlay.state_digest(state),
            'interest_krw': {advance: {'contract': info['posted_contract_krw'], 'default': info['posted_default_krw']}
                             for advance, info in sorted(state['advances'].items())},
        }

    def test_empty_overlay_golden(self):
        golden = json.loads((GOLDEN_DIR / 'overlay_empty.json').read_text(encoding='utf-8'))
        demo = json.loads((GOLDEN_DIR / 'demo.json').read_text(encoding='utf-8'))
        self.assertEqual(golden['overlay_state_digest'], overlay.state_digest(overlay.empty_state()))
        self.assertEqual(golden['overlay_state_digest'], overlay.empty_section()['overlay_state']['digest'])
        self.assertEqual(golden['export_manifest_v2_content_digest'], demo['content_digest'])
        service = seed.build_service()
        self.assertEqual(service.export_manifest()['content_digest'], golden['export_manifest_v2_content_digest'])
        self.assertEqual(service.export_manifest()['format'], 'KIX_CAPITAL_EXPORT_MANIFEST_V2')
        self.assertEqual(golden['f04_state_digest'], demo['state_digest'])

    def test_demo_overlay_golden(self):
        golden = json.loads((GOLDEN_DIR / 'overlay_demo.json').read_text(encoding='utf-8'))
        self.assertEqual(self.demo_scenario(), golden)
        self.assertEqual(self.demo_scenario(), self.demo_scenario())

    def test_goldens_carry_no_volatile_keys(self):
        for name in ('overlay_empty.json', 'overlay_demo.json'):
            text = (GOLDEN_DIR / name).read_text(encoding='utf-8')
            for key in ('instance_id', 'created_at', 'saved_at', 'timestamp'):
                self.assertNotIn(key, text, name)


if __name__ == '__main__':
    unittest.main()
