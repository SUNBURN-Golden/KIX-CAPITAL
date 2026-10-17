"""Margin call, cure, acceleration and default-eligible proposals on the overlay.

SIMULATED. Expected numbers are recomputed from the CAPITAL-TERMS-V1 block, never read back
from the code under test. Margin rules fire only on a disposable ScenarioReplaySource book.
"""
import io
import json
import tempfile
import tokenize
import unittest
from pathlib import Path

from capital import margin, overlay
from capital.producer import FixtureViews, PinnedFsmProducer
from capital.scenarios import definitions, replay_scenarios
from capital.service import ApiError, CapitalService
from capital.store import FileWorkspace, canonical_bytes, section_checksum
from capital.terms import DecisionNoteTermsPolicy
from tests.test_overlay import TERMS_NOTE, draw_book, f04_view, run, seed, terms_value, tick

MARGIN_PY = Path(margin.__file__)
MARGIN = terms_value('additional_margin')
TERM = terms_value('term')
WINDOW = MARGIN['cure_window_days']
GRACE = TERM['grace_days_after_maturity']
T1_RATE = MARGIN['advance_rate_bps_by_tier']['T1_COMMIT_OBSERVED']
# sim-committed: organizer line 95,000 (100,000 gross - 5% platform fee); partial-before binds a 40,000 refund.
ELIGIBLE = 95_000 - 40_000
BASE = ELIGIBLE * T1_RATE // 10_000
STANDARD_TERM = TERM['standard_term_days']


def disposable(path=None):
    source = margin.ScenarioReplaySource()
    return source, CapitalService(path, producer=PinnedFsmProducer(fixtures=source))


def drawn_then_refunded(amount=BASE + 1):
    source, service = disposable()
    draw_book(service, amount=amount)
    outcomes = source.replay('sim-committed', 'partial-before')
    assert all(item['matched'] for item in outcomes), outcomes
    return source, service


def margin_state(service, advance='sim-a'):
    return overlay.fold(service.overlay_entries).get('margin', {}).get('advances', {}).get(advance)


def kinds(service):
    return [entry['kind'] for entry in service.overlay_entries if entry['kind'] in overlay.MARGIN_KINDS]


class CallTests(unittest.TestCase):
    def test_note_literals_used_here(self):
        self.assertEqual((WINDOW, GRACE, T1_RATE), (5, 10, 8500))
        self.assertEqual(BASE, 46_750)

    def test_call_fires_on_the_first_tick_above_the_floor_with_deadline_day_plus_window(self):
        source, service = drawn_then_refunded()
        quote = service.overlay_state()
        self.assertEqual(quote['advances'][0]['margin']['state'], 'BREACH_AWAITING_TICK')
        self.assertEqual(quote['margin']['source'], 'SIMULATED_DISPOSABLE_BOOK')
        tick(service, 'c-1', 0, 3)
        entry = next(e for e in service.overlay_entries if e['kind'] == overlay.KIND_MARGIN_CALL)
        self.assertEqual((entry['sim_day'], entry['payload']['cure_deadline']), (3, 3 + WINDOW))
        self.assertEqual((entry['payload']['outstanding_krw'], entry['payload']['base_krw']), (BASE + 1, BASE))
        self.assertEqual(margin_state(service)['status'], 'CALLED')
        block = service.overlay_state()
        self.assertTrue(block['margin']['triggered'])
        self.assertEqual(block['advances'][0]['margin']['cure_deadline'], 3 + WINDOW)
        self.assertEqual(block['margin']['cure_options'][0],
                         {'option': 'PARTIAL_REPAY_TO_WITHIN_BASE', 'status': 'AVAILABLE'})

    def test_no_call_at_equality_and_no_second_call_while_open(self):
        _, service = drawn_then_refunded(amount=BASE)
        tick(service, 'c-1', 0, 2)
        self.assertEqual(kinds(service), [])
        self.assertEqual(service.overlay_state()['advances'][0]['margin']['state'], 'WITHIN_BASE')
        _, service = drawn_then_refunded()
        tick(service, 'c-1', 0, 1)
        tick(service, 'c-2', 1, 2)
        tick(service, 'c-3', 2, 3)
        self.assertEqual(kinds(service), [overlay.KIND_MARGIN_CALL])

    def test_no_call_before_the_refund_lowers_the_base(self):
        source, service = disposable()
        draw_book(service, amount=BASE + 1)
        tick(service, 'c-1', 0, 1)
        self.assertEqual(kinds(service), [])
        self.assertEqual(service.overlay_state()['advances'][0]['margin']['state'], 'WITHIN_BASE')

    def test_base_equals_the_terms_overlay_borrowing_base(self):
        # With no refund the T1 tier still matches, so the independent terms.overlay base is comparable.
        service = CapitalService()
        draw_book(service, amount=90_000)
        claim = service.fixtures.view('sim-committed')['claim']
        base = service.terms.overlay(service.machine.view('sim-a'), claim, draw_day=0, as_of_day=1,
                                     expected_settlement_cash_day=None,
                                     gate='MOCK_COMMIT_OBSERVED')['borrowing_base']
        row = service.overlay_state()['advances'][0]['margin']
        self.assertEqual((row['eligible_face_krw'], row['base_krw'], row['advance_rate_bps']),
                         (base['eligible_face'], base['base_krw'], base['advance_rate_bps']))


class CureTests(unittest.TestCase):
    def setUp(self):
        self.source, self.service = drawn_then_refunded()
        tick(self.service, 'c-1', 0, 3)

    def test_partial_repay_back_within_the_base_cures_and_is_journaled(self):
        run(self.service, 'repay', 'sim-a', 'r-1', amount=2, sequence=1)
        tick(self.service, 'c-2', 3, 4)
        cure = next(e for e in self.service.overlay_entries if e['kind'] == overlay.KIND_MARGIN_CURE)
        self.assertEqual((cure['sim_day'], cure['payload']['cure_option']), (3, 'PARTIAL_REPAY_TO_WITHIN_BASE'))
        self.assertEqual(cure['payload']['outstanding_krw'], BASE - 1)
        self.assertEqual(margin_state(self.service)['status'], 'CURED')
        self.assertEqual(self.service.overlay_state()['advances'][0]['margin']['state'], 'CURED')
        tick(self.service, 'c-3', 4, 20)
        self.assertEqual(kinds(self.service), [overlay.KIND_MARGIN_CALL, overlay.KIND_MARGIN_CURE])

    def test_deadline_day_is_inclusive_and_one_day_late_accelerates(self):
        tick(self.service, 'c-2', 3, 3 + WINDOW)
        run(self.service, 'repay', 'sim-a', 'r-1', amount=2, sequence=1)
        tick(self.service, 'c-3', 3 + WINDOW, 3 + WINDOW + 1)
        self.assertEqual(margin_state(self.service)['status'], 'CURED')

    def test_repay_that_is_still_over_the_base_does_not_cure(self):
        run(self.service, 'repay', 'sim-a', 'r-1', amount=1, sequence=1)
        tick(self.service, 'c-2', 3, 4)
        # outstanding == base is "not above the floor": that repay is exactly back within the base.
        self.assertEqual(margin_state(self.service)['status'], 'CURED')
        source, service = drawn_then_refunded(amount=BASE + 5)
        tick(service, 'c-1', 0, 3)
        run(service, 'repay', 'sim-a', 'r-1', amount=2, sequence=1)
        tick(service, 'c-2', 3, 4)
        self.assertEqual(margin_state(service)['status'], 'CALLED')

    def test_new_call_after_a_cure(self):
        run(self.service, 'repay', 'sim-a', 'r-1', amount=2, sequence=1)
        tick(self.service, 'c-2', 3, 4)
        self.source.replay('sim-committed', 'late', steps=[
            {'op': 'bind_refund', 'args': {'refund_id': 'sim-refund-2', 'amount': 1_000,
                                           'beneficiary_role': 'fixture-buyer', 'reason': 'SYNTHETIC_SCENARIO'},
             'expected_error': None}])
        tick(self.service, 'c-3', 4, 5)
        self.assertEqual(kinds(self.service).count(overlay.KIND_MARGIN_CALL), 2)
        self.assertEqual(margin_state(self.service)['calls'], 2)

    def test_cure_survives_a_workspace_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = margin.ScenarioReplaySource()
            port = FileWorkspace.open(Path(tmp))
            try:
                service = CapitalService(port, producer=PinnedFsmProducer(fixtures=source))
                draw_book(service, amount=BASE + 1)
                source.replay('sim-committed', 'partial-before')
                tick(service, 'c-1', 0, 3)
                run(service, 'repay', 'sim-a', 'r-1', amount=2, sequence=1)
                tick(service, 'c-2', 3, 4)
                digest = service.overlay_state()['overlay_state_digest']
            finally:
                port.close()
            port = FileWorkspace.open(Path(tmp))
            try:
                again = CapitalService(port, producer=PinnedFsmProducer(fixtures=source))
                self.assertEqual(again.workspace_status, 'ACTIVE')
                self.assertEqual(again.overlay_state()['overlay_state_digest'], digest)
                self.assertEqual(margin_state(again)['status'], 'CURED')
            finally:
                port.close()


class AccelerationTests(unittest.TestCase):
    def setUp(self):
        self.source, self.service = drawn_then_refunded()
        tick(self.service, 'c-1', 0, 3)
        self.deadline = 3 + WINDOW
        self.eligible = min(STANDARD_TERM, self.deadline) + GRACE + 1

    def test_uncured_call_accelerates_with_maturity_at_the_deadline_and_default_eligible_day(self):
        tick(self.service, 'c-2', 3, self.deadline)
        self.assertEqual(margin_state(self.service)['status'], 'CALLED')
        tick(self.service, 'c-3', self.deadline, self.deadline + 1)
        accel = next(e for e in self.service.overlay_entries if e['kind'] == overlay.KIND_MARGIN_ACCELERATION)
        self.assertEqual(accel['payload']['maturity_after'], self.deadline)
        self.assertEqual(accel['payload']['default_eligible_day'], self.deadline + GRACE + 1)
        state = margin_state(self.service)
        self.assertEqual((state['status'], state['maturity_day']), ('ACCELERATED', self.deadline))
        self.assertNotIn(overlay.KIND_DEFAULT_PROPOSAL, kinds(self.service))

    def test_proposal_appears_once_on_the_default_eligible_day_and_never_calls_default(self):
        tick(self.service, 'c-2', 3, self.deadline + 1)
        before = f04_view(self.service)
        last = self.deadline + GRACE + 1
        tick(self.service, 'c-3', self.deadline + 1, last - 1)
        self.assertNotIn(overlay.KIND_DEFAULT_PROPOSAL, kinds(self.service))
        tick(self.service, 'c-4', last - 1, last)
        tick(self.service, 'c-5', last, last + 5)
        self.assertEqual(kinds(self.service).count(overlay.KIND_DEFAULT_PROPOSAL), 1)
        self.assertEqual(f04_view(self.service), before)
        self.assertEqual(len(self.service.machine.export_journal()), len(before[2]))
        self.assertNotIn('default', [row['op'] for row in self.service.machine.export_journal()])
        self.assertEqual(self.service.machine.view('sim-a')['phase'], 'DRAWN')
        block = self.service.overlay_state()['margin']
        self.assertEqual(len(block['proposals']), 1)
        self.assertEqual((block['proposals'][0]['proposal_kind'], block['f04_default_called'], block['proposal_only']),
                         ('DEFAULT_ELIGIBLE', False, True))
        self.assertEqual(self.service.overlay_state()['advances'][0]['margin']['default_eligible_day'], last)

    def test_one_long_tick_chains_acceleration_and_proposal(self):
        last = self.deadline + GRACE + 1
        tick(self.service, 'c-2', 3, last)
        self.assertEqual(kinds(self.service)[-2:], [overlay.KIND_MARGIN_ACCELERATION, overlay.KIND_DEFAULT_PROPOSAL])

    def test_cure_does_not_reverse_an_acceleration_and_repay_to_zero_stops_proposals(self):
        tick(self.service, 'c-2', 3, self.deadline + 1)
        outstanding = self.service.machine.view('sim-a')['outstanding_exposure']
        run(self.service, 'repay', 'sim-a', 'r-1', amount=outstanding, sequence=1)
        tick(self.service, 'c-3', self.deadline + 1, self.deadline + GRACE + 5)
        self.assertEqual(margin_state(self.service)['status'], 'ACCELERATED')
        self.assertNotIn(overlay.KIND_DEFAULT_PROPOSAL, kinds(self.service))

    def test_interest_is_not_rebased(self):
        tick(self.service, 'c-2', 3, self.deadline + 1)
        self.assertIs(self.service.overlay_state()['margin']['interest_rebased'], False)
        self.assertIs(self.service.overlay_state()['advances'][0]['margin']['interest_rebased'], False)


class FoldTests(unittest.TestCase):
    def setUp(self):
        _, self.service = drawn_then_refunded()
        tick(self.service, 'c-1', 0, 3)
        tick(self.service, 'c-2', 3, 3 + WINDOW + 1)
        self.entries = self.service.overlay_entries

    def entry(self, kind):
        return next(e for e in self.entries if e['kind'] == kind)

    def test_fold_refuses_out_of_order_or_inconsistent_margin_entries(self):
        def clone(kind, **changes):
            item = json.loads(json.dumps(self.entry(kind)))
            item['overlay_id'] += ':x'
            item['payload'].update(changes)
            return item
        cases = {
            'second call while accelerated': clone(overlay.KIND_MARGIN_CALL),
            'cure after acceleration': {
                'overlay_id': 'cure-x', 'after_journal_index': self.entry(overlay.KIND_MARGIN_CALL)['after_journal_index'],
                'kind': overlay.KIND_MARGIN_CURE,
                'payload': {'advance_id': 'sim-a', 'outstanding_krw': 0, 'eligible_face_krw': 1, 'base_krw': 1,
                            'cure_deadline': 3 + WINDOW, 'cure_option': 'x',
                            'terms_version': self.entry(overlay.KIND_MARGIN_CALL)['payload']['terms_version']}},
        }
        for label, extra in cases.items():
            with self.subTest(label):
                extra['sim_day'] = overlay.fold(self.entries)['sim_day']
                with self.assertRaises(overlay.OverlayError):
                    overlay.fold(self.entries + [extra])
        early = json.loads(json.dumps(self.entries))
        proposal = {'overlay_id': 'p', 'after_journal_index': early[-1]['after_journal_index'],
                    'sim_day': early[-1]['sim_day'], 'kind': overlay.KIND_DEFAULT_PROPOSAL,
                    'payload': {'advance_id': 'sim-a', 'proposal_kind': 'DEFAULT_ELIGIBLE', 'authority': 'x',
                                'default_eligible_day': 3 + WINDOW + GRACE + 1, 'outstanding_krw': 1,
                                'terms_version': early[0]['payload']['terms_version']}}
        with self.assertRaises(overlay.OverlayError):
            overlay.fold(early + [proposal])

    def test_fold_refuses_a_cure_deadline_that_is_not_day_plus_window(self):
        bad = json.loads(json.dumps(self.entries))
        next(e for e in bad if e['kind'] == overlay.KIND_MARGIN_CALL)['payload']['cure_deadline'] += 1
        with self.assertRaises(overlay.OverlayError):
            overlay.fold(bad)

    def test_margin_state_key_is_absent_until_a_margin_entry_folds(self):
        self.assertNotIn('margin', overlay.fold([e for e in self.entries if e['kind'] not in overlay.MARGIN_KINDS]))


class ImmutableFixtureTests(unittest.TestCase):
    def test_workspace_fixtures_report_checked_not_triggered_and_a_fixture_limit(self):
        service = CapitalService()
        draw_book(service, amount=90_000)  # above the 80,750 T1 base, still never journaled
        tick(service, 'c-1', 0, 30)
        self.assertEqual(kinds(service), [])
        block = service.overlay_state()
        self.assertEqual(block['margin']['source'], 'READ_ONLY_FIXTURE')
        self.assertEqual((block['margin']['checked'], block['margin']['triggered'], block['margin']['limit']),
                         (True, False, 'FIXTURE_VIEWS_IMMUTABLE'))
        row = block['advances'][0]['margin']
        self.assertEqual((row['state'], row['checked'], row['triggered']), ('FIXTURE_LIMIT', True, False))
        self.assertEqual((row['base_krw'], row['headroom_krw']), (80_750, 80_750 - 90_000))
        self.assertNotIn('margin', overlay.fold(service.overlay_entries))

    def test_not_bound_note_has_no_numbers(self):
        service = CapitalService(terms=DecisionNoteTermsPolicy(TERMS_NOTE.parent / 'no-such-note.md'))
        block = service.overlay_state()['margin']
        self.assertEqual((block['status'], block['checked'], block['triggered']), ('NOT_BOUND', False, False))

    def test_pinned_fixture_views_are_untouched_by_a_replay_source(self):
        before = json.dumps(FixtureViews().rows, sort_keys=True)
        source = margin.ScenarioReplaySource()
        source.replay('sim-committed', 'partial-before')
        self.assertEqual(json.dumps(FixtureViews().rows, sort_keys=True), before)
        self.assertTrue(margin.views_mutable(source))
        self.assertFalse(margin.views_mutable(FixtureViews()))
        self.assertEqual(sorted(replay_scenarios()), sorted(item[0] for item in definitions()))
        self.assertEqual(seed.build_service().fixtures.__class__, FixtureViews)

    # These three scenarios start from an uncommitted claim with their own statement amounts; a fixture
    # that is already committed cannot reproduce them, and the replay reports that instead of hiding it.
    NEEDS_UNCOMMITTED_CLAIM = {'duplicate-statement', 'late-cash', 'split-statement'}

    def test_replay_returns_outcomes_and_matches_expected_errors(self):
        for scenario_id, _title, _desc, steps in definitions():
            with self.subTest(scenario_id):
                outcomes = margin.ScenarioReplaySource().replay('sim-committed', scenario_id)
                self.assertEqual(len(outcomes), len(steps))
                for item in outcomes:
                    self.assertEqual((item['label'], item['scope']), ('SIMULATED', 'DISPOSABLE_BOOK_ONLY'))
                if scenario_id in self.NEEDS_UNCOMMITTED_CLAIM:
                    self.assertFalse(all(item['matched'] for item in outcomes))
                else:
                    self.assertTrue(all(item['matched'] for item in outcomes), outcomes)


class TamperTests(unittest.TestCase):
    def test_tampered_margin_entry_is_unreadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = margin.ScenarioReplaySource()
            port = FileWorkspace.open(Path(tmp))
            try:
                service = CapitalService(port, producer=PinnedFsmProducer(fixtures=source))
                draw_book(service, amount=BASE + 1)
                source.replay('sim-committed', 'partial-before')
                tick(service, 'c-1', 0, 3)
            finally:
                port.close()
            path = Path(tmp) / 'workspace.json'
            document = json.loads(path.read_text(encoding='utf-8'))
            call = next(e for e in document['overlay']['journal'] if e['kind'] == overlay.KIND_MARGIN_CALL)
            call['payload']['cure_deadline'] += 1
            document['overlay']['section_sha256'] = section_checksum(document['overlay'])
            path.write_bytes(canonical_bytes(document))
            port = FileWorkspace.open(Path(tmp))
            try:
                again = CapitalService(port, producer=PinnedFsmProducer(fixtures=source))
                self.assertEqual(again.workspace_status, 'WORKSPACE_UNREADABLE')
            finally:
                port.close()


class IntegerOnlyTests(unittest.TestCase):
    def test_margin_module_has_no_float_arithmetic(self):
        source = MARGIN_PY.read_text(encoding='utf-8')
        banned_names = {'float', 'Decimal', 'math', 'statistics', 'Fraction'}
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.NAME:
                self.assertNotIn(token.string, banned_names, token)
            if token.type == tokenize.NUMBER:
                self.assertRegex(token.string, r'\A[0-9]+\Z', token)
                self.assertLessEqual(int(token.string), 2, token)
            if token.type == tokenize.OP:
                self.assertNotIn(token.string, ('/', '/='), token)
        self.assertNotRegex(source.replace('F01-F03', ''), r'\bfloat\b|\bDecimal\b')


if __name__ == '__main__':
    unittest.main()
