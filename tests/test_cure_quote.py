"""Minimum-cure quote: captured-input advisory with disposable-copy witnesses.

SIMULATED. Expected numbers are recomputed here from the CAPITAL-TERMS-V1 and
CAPITAL_MINIMUM_CURE_QUOTE blocks, never read back from the code under test.
Witnesses run `post_repayment` on disposable restored copies only; the source
journal, receipts, clock and workspace bytes must not move.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from capital import cure_quote, margin, overlay
from capital.producer import PinnedFsmProducer
from capital.service import CapitalService
from capital.store import canonical_bytes
from capital.terms import DecisionNoteTermsPolicy
from tests.test_margin import MARGIN, T1_RATE
from tests.test_overlay import ROOT, TERMS_NOTE, draw_book, run, terms_value, tick

NOTE = ROOT / 'docs' / 'decisions' / 'CAPITAL_MINIMUM_CURE_QUOTE.md'
CURE_WINDOW = MARGIN['cure_window_days']
# Fixture constants: 'sim-committed' organizer line is 95,000; 'partial-before'
# binds a 40,000 refund; 'sim-pending' starts with the same obligations.
ELIGIBLE_T1 = 95_000 - 40_000
BASE_T1 = ELIGIBLE_T1 * T1_RATE // 10_000
T2_RATE = MARGIN['advance_rate_bps_by_tier']['T2_UNBOUND']
ELIGIBLE_T2 = 95_000 - 60_000
BASE_T2 = ELIGIBLE_T2 * T2_RATE // 10_000
T1_BPS = next(row['all_in_bps_annual'] for row in terms_value('interest_rate')['tiers']
              if row['id'] == 'T1_COMMIT_OBSERVED')
T2_BPS = next(row['all_in_bps_annual'] for row in terms_value('interest_rate')['tiers']
              if row['id'] == 'T2_UNBOUND')


def due(person_days, bps):
    day_count = int(terms_value('interest_rate')['day_count'].split('_')[1])
    return (person_days * bps) // (10_000 * day_count)


def whole(service):
    """Everything a read-only quote must leave alone."""
    return (json.dumps(service.overlay_entries, sort_keys=True),
            json.dumps(service.receipts, sort_keys=True),
            service.machine.state_digest(),
            service.overlay_state()['overlay_state_digest'],
            json.dumps(service.machine.export_journal(), sort_keys=True),
            service.workspace_status,
            None if service.storage._document is None else canonical_bytes(service.storage._document))


def scenario(name):
    service, advance_id = cure_quote.SCENARIOS[name]()
    return service, advance_id


class NoteAndShapeTests(unittest.TestCase):
    def test_the_six_entries_are_adopted_and_bound(self):
        binding = cure_quote.note_binding()
        self.assertEqual(binding['decision_id'], 'cure-quote-scope-decision')
        self.assertIs(binding['bound'], True)
        self.assertEqual(binding['missing_entries'], [])
        self.assertIsNotNone(binding['note_sha256'])

    def test_labels_and_flags(self):
        service, advance = scenario('breach-tier1')
        report = cure_quote.quote(service, advance)
        self.assertEqual((report['label'], report['mode'], report['format']),
                         ('SIMULATED', 'READ_ONLY_CAPTURED_INPUT_ADVISORY', cure_quote.FORMAT))
        for key in ('provisional', 'advisory'):
            self.assertIs(report[key], True, key)
        for key in ('executionAuthorized', 'funds_executed'):
            self.assertIs(report[key], False, key)
        self.assertNotIn('instance_id', report)
        self.assertNotIn('_live', report)

    def test_missing_note_entry_is_not_bound_with_named_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            changed = NOTE.read_text(encoding='utf-8').replace(
                '"cure_target_predicate": {\n      "status": "ADOPTED"',
                '"cure_target_predicate": {\n      "status": "UNDETERMINED"')
            path = Path(tmp) / 'note.md'
            path.write_text(changed, encoding='utf-8')
            service, advance = scenario('breach-tier1')
            report = cure_quote.quote(service, advance, note=path)
        self.assertEqual(report['outcome'], 'NOT_BOUND')
        self.assertIn('decision_entry:cure_target_predicate', report['reasons'])
        self.assertIsNone(report['amounts'])

    def test_absent_note_is_not_bound(self):
        service, advance = scenario('breach-tier1')
        report = cure_quote.quote(service, advance,
                                  note=Path(tempfile.gettempdir()) / 'absent-note.md')
        self.assertEqual(report['outcome'], 'NOT_BOUND')
        self.assertEqual(report['reasons'], [f'decision_entry:{name}' for name in cure_quote.ENTRIES])


class QuoteArithmeticTests(unittest.TestCase):
    def test_tier1_quote_matches_an_independent_recompute(self):
        service, advance = scenario('breach-tier1')
        report = cure_quote.quote(service, advance)
        self.assertEqual(report['outcome'], 'QUOTED')
        self.assertEqual(report['tier'], 'T1')
        amounts = report['amounts']
        reduction = BASE_T1 + 1 - BASE_T1
        interest = due((BASE_T1 + 1) * 3, T1_BPS)
        self.assertEqual((amounts['outstanding_principal_krw'], amounts['base_krw']), (BASE_T1 + 1, BASE_T1))
        self.assertEqual(amounts['required_principal_reduction_krw'], reduction)
        self.assertEqual((amounts['posted_interest_due_krw'], amounts['interest_due_krw'],
                          amounts['default_interest_due_krw']), (interest, interest, 0))
        gross = interest + reduction
        self.assertEqual((amounts['gross_repayment_resources_krw'], amounts['eligible_held_cash_krw'],
                          amounts['held_cash_applied_krw'], amounts['minimum_new_cash_krw']),
                         (gross, 0, 0, gross))
        self.assertEqual((report['sim_day'], report['cure_deadline']), (3, 3 + CURE_WINDOW))
        self.assertIs(report['arithmetic_sufficient'], True)
        self.assertEqual(report['command_admissibility'], {'status': 'ADMISSIBLE_AT_SNAPSHOT', 'reason': None})
        self.assertEqual(report['recorded_cure'], 'CALLED')

    def test_tier2_unbound_quote_uses_the_t2_rate_and_base(self):
        service, advance = scenario('breach-tier2-unbound')
        report = cure_quote.quote(service, advance)
        self.assertEqual(report['outcome'], 'QUOTED')
        self.assertEqual(report['tier'], 'T2')
        amounts = report['amounts']
        interest = due((BASE_T2 + 1) * 3, T2_BPS)
        self.assertEqual((amounts['outstanding_principal_krw'], amounts['base_krw']), (BASE_T2 + 1, BASE_T2))
        self.assertEqual(amounts['required_principal_reduction_krw'], 1)
        self.assertEqual(amounts['posted_interest_due_krw'], interest)
        self.assertEqual(amounts['minimum_new_cash_krw'], interest + 1)
        self.assertIs(report['arithmetic_sufficient'], True)
        self.assertEqual(report['witnesses']['sufficiency']['result'], 'COVERAGE_SATISFIED')

    def test_fractional_interest_carry_stays_visible_in_the_witness(self):
        service, advance = scenario('fractional-carry')
        report = cure_quote.quote(service, advance)
        self.assertEqual(report['outcome'], 'QUOTED')
        witness = cure_quote.capture(service, advance)['dues']['witness']
        numerator = int(witness['accrued_interest_num'])
        self.assertGreater(numerator % witness['denominator'], 0)
        self.assertEqual(numerator // witness['denominator'], report['amounts']['posted_interest_due_krw'])
        # Two postings carry the sub-won remainder; the independent recompute agrees.
        self.assertEqual(report['amounts']['posted_interest_due_krw'], due((BASE_T1 + 1) * 3, T1_BPS))

    def test_held_cash_formula_matches_the_note_worked_examples(self):
        # §3.2 synthetic fixtures: R = 20,000, I = 3,000, G = 23,000.
        def cap(held):
            return {'measured': {'outstanding_krw': 100_000, 'base_krw': 80_000,
                                 'breach': True, 'eligible_face_krw': 94_000},
                    'dues': {'interest_due_krw': 3_000, 'default_interest_due_krw': 0,
                             'unapplied_cash_krw': held, 'witness': {}}}
        for held, applied, new_cash in ((0, 0, 23_000), (5_000, 5_000, 18_000), (25_000, 23_000, 0)):
            with self.subTest(held=held):
                amounts = cure_quote.evaluate(cap(held))['amounts']
                self.assertEqual((amounts['gross_repayment_resources_krw'],
                                  amounts['held_cash_applied_krw'],
                                  amounts['minimum_new_cash_krw']), (23_000, applied, new_cash))
        # R = 0: gross/applied/new are all zero while interest stays disclosed.
        zero = cure_quote.evaluate({'measured': {'outstanding_krw': 10, 'base_krw': 10, 'breach': False,
                                                 'eligible_face_krw': 12},
                                    'dues': {'interest_due_krw': 7, 'default_interest_due_krw': 3,
                                             'unapplied_cash_krw': 4, 'witness': {}}})['amounts']
        self.assertEqual((zero['required_principal_reduction_krw'],
                          zero['gross_repayment_resources_krw'], zero['held_cash_applied_krw'],
                          zero['minimum_new_cash_krw']), (0, 0, 0, 0))
        self.assertEqual(zero['posted_interest_due_krw'], 10)


class BoundaryOutcomeTests(unittest.TestCase):
    def test_at_deadline_is_eligible_and_labeled(self):
        service, advance = scenario('at-deadline')
        report = cure_quote.quote(service, advance)
        self.assertEqual(report['outcome'], 'AT_DEADLINE')
        self.assertEqual(report['sim_day'], report['cure_deadline'])
        self.assertIsNotNone(report['amounts'])
        self.assertEqual(report['witnesses']['sufficiency']['result'], 'COVERAGE_SATISFIED')
        self.assertIs(report['witnesses']['cure_would_record']['after_quote'], True)

    def test_window_expired_classification_is_defensive_on_the_capture(self):
        # The real fold accelerates inside the same tick, so a CALLED record
        # past its deadline is crafted here, labeled READ_ONLY_FIXTURE.
        cap = {'invalid': [], 'missing': [], 'terminal': False,
               'record': {'status': 'CALLED', 'cure_deadline': 8},
               'sim_day': 9,
               'measured': {'outstanding_krw': 1, 'base_krw': 0, 'breach': True}}
        self.assertEqual(cure_quote.classify(cap), 'WINDOW_EXPIRED')
        cap['record'] = {'status': 'ACCELERATED', 'cure_deadline': 8}
        self.assertEqual(cure_quote.classify(cap), 'ALREADY_ACCELERATED')
        cap['terminal'] = True
        self.assertEqual(cure_quote.classify(cap), 'TERMINAL_CASE')

    def test_already_accelerated_returns_null_amounts(self):
        service, advance = scenario('already-accelerated')
        report = cure_quote.quote(service, advance)
        self.assertEqual(report['outcome'], 'ALREADY_ACCELERATED')
        self.assertIsNone(report['amounts'])
        self.assertEqual(report['recorded_cure'], 'ACCELERATED')
        self.assertIsNone(report['witnesses'])

    def test_terminal_case_after_a_recorded_default(self):
        service, advance = scenario('breach-tier1')
        run(service, 'default', advance, 'cq-default-1')
        report = cure_quote.quote(service, advance)
        self.assertEqual(report['outcome'], 'TERMINAL_CASE')
        self.assertIsNone(report['amounts'])
        self.assertEqual(report['recorded_cure'], 'CALLED')

    def test_no_active_margin_call(self):
        service, advance = scenario('no-call')
        report = cure_quote.quote(service, advance)
        self.assertEqual(report['outcome'], 'NO_ACTIVE_MARGIN_CALL')
        self.assertIsNone(report['amounts'])
        self.assertIsNone(report['recorded_cure'])

    def test_zero_required_cash_keeps_amounts_disclosed_and_no_command(self):
        service, advance = scenario('zero-required-cash')
        report = cure_quote.quote(service, advance)
        self.assertEqual(report['outcome'], 'NO_REDUCTION_REQUIRED')
        amounts = report['amounts']
        self.assertEqual((amounts['required_principal_reduction_krw'],
                          amounts['gross_repayment_resources_krw'], amounts['held_cash_applied_krw'],
                          amounts['minimum_new_cash_krw']), (0, 0, 0, 0))
        self.assertEqual(report['recorded_cure'], 'CALLED')
        self.assertEqual(report['command_admissibility']['status'], 'UNKNOWN')
        self.assertIs(report['witnesses']['cure_would_record']['at_snapshot'], True)

    def test_missing_terms_is_not_bound(self):
        service, advance = scenario('missing-terms')
        report = cure_quote.quote(service, advance)
        self.assertEqual(report['outcome'], 'NOT_BOUND')
        self.assertIn('margin_terms', report['reasons'])
        self.assertIn('ledger_denominator', report['reasons'])
        self.assertIsNone(report['amounts'])

    def test_capacity_refusal_preserves_arithmetic_and_marks_the_command(self):
        service, advance = scenario('capacity-refusal')
        report = cure_quote.quote(service, advance)
        self.assertEqual(report['outcome'], 'QUOTED')
        self.assertIsNotNone(report['amounts'])
        self.assertIs(report['arithmetic_sufficient'], True)
        admissibility = report['command_admissibility']
        self.assertEqual((admissibility['status'], admissibility['reason']),
                         ('REFUSED', 'SIMULATION_CAPACITY'))
        self.assertEqual(report['witnesses']['sufficiency']['result'], 'COMMAND_REFUSED')

    def test_unsupported_producer_is_named_and_null(self):
        class Other(PinnedFsmProducer):
            """Not the in-process pinned producer."""

        source = margin.ScenarioReplaySource()
        service = CapitalService(producer=Other(fixtures=source))
        cure_quote._breach_draw(service, 'sim-committed', 'MOCK_COMMIT_OBSERVED', 40_000)
        source.replay('sim-committed', 'partial-before')
        tick(service, 'cq-tick-1', 0, 3)
        report = cure_quote.quote(service, 'sim-a')
        self.assertEqual(report['outcome'], 'UNSUPPORTED_PRODUCER')
        self.assertIsNone(report['amounts'])
        self.assertIsNone(report['witnesses'])

    def test_unknown_advance_is_invalid_input(self):
        service, _advance = scenario('breach-tier1')
        report = cure_quote.quote(service, 'sim-nope')
        self.assertEqual(report['outcome'], 'INVALID_INPUT')
        self.assertIn('ADVANCE_NOT_DRAWN', report['reasons'])


class WitnessTests(unittest.TestCase):
    def test_quoted_amount_satisfies_the_predicate_and_one_less_fails(self):
        service, advance = scenario('breach-tier1')
        report = cure_quote.quote(service, advance)
        witnesses = report['witnesses']
        self.assertEqual(witnesses['scope'], 'SIMULATED_DISPOSABLE_BOOK')
        sufficiency = witnesses['sufficiency']
        self.assertEqual(sufficiency['result'], 'COVERAGE_SATISFIED')
        self.assertIs(sufficiency['predicate']['breach'], False)
        self.assertEqual(sufficiency['predicate']['eligible_face_krw'],
                         report['amounts']['eligible_face_krw'])
        allocation = sufficiency['receipt']['allocation']
        self.assertEqual(allocation['principal_krw'], report['amounts']['required_principal_reduction_krw'])
        self.assertEqual(allocation['interest_krw'], report['amounts']['interest_due_krw'])
        minimality = witnesses['minimality']
        self.assertEqual((minimality['result'], minimality['minimum_confirmed']),
                         ('STILL_BREACHED', True))
        self.assertIs(minimality['predicate']['breach'], True)
        # The disposable copies never became the source: the book is still breached.
        self.assertIs(cure_quote._measure_on(service, advance)['breach'], True)

    def test_recorded_cure_requires_the_existing_tick_not_the_quote(self):
        service, advance = scenario('breach-tier1')
        report = cure_quote.quote(service, advance)
        self.assertEqual(report['recorded_cure'], 'CALLED')
        self.assertIs(report['witnesses']['cure_would_record']['at_snapshot'], False)
        self.assertIs(report['witnesses']['cure_would_record']['after_quote'], True)
        # A real posting plus a real tick records CURE through the existing path.
        run(service, 'repay', advance, 'cq-r-1', amount=report['amounts']['required_principal_reduction_krw'],
            sequence=1)
        tick(service, 'cq-tick-2', 3, 4)
        folded = overlay.fold(service.overlay_entries)
        self.assertEqual(folded['margin']['advances'][advance]['status'], 'CURED')
        refreshed = cure_quote.quote(service, advance)
        self.assertEqual(refreshed['recorded_cure'], 'CURED')
        self.assertEqual(refreshed['outcome'], 'NO_ACTIVE_MARGIN_CALL')

    def test_quote_changes_no_source_journal_receipt_clock_or_workspace_bytes(self):
        for name in ('breach-tier1', 'capacity-refusal', 'already-accelerated', 'missing-terms'):
            with self.subTest(name):
                service, advance = scenario(name)
                before = whole(service)
                report = cure_quote.quote(service, advance)
                self.assertEqual(whole(service), before)
                self.assertIsNotNone(report['input_digest'])


class BindingAndFreshnessTests(unittest.TestCase):
    def test_input_and_quote_digests_are_deterministic_and_bound(self):
        first_service, advance = scenario('breach-tier1')
        first = cure_quote.quote(first_service, advance)
        second_service, second_advance = scenario('breach-tier1')
        second = cure_quote.quote(second_service, second_advance)
        self.assertEqual(first['input_digest'], second['input_digest'])
        self.assertEqual(first['quote_digest'], second['quote_digest'])
        self.assertIs(cure_quote.is_stale(first_service, first), False)
        self.assertIs(cure_quote.is_stale(second_service, first), False)
        tick(first_service, 'cq-tick-2', 3, 4)
        self.assertIs(cure_quote.is_stale(first_service, first), True)
        # A foreign document is conservatively stale.
        self.assertIs(cure_quote.is_stale(first_service, {'format': 'other'}), True)

    def test_posted_interest_components_and_digests_in_every_supported_case(self):
        for name in cure_quote.SCENARIOS:
            with self.subTest(name):
                report = cure_quote.evaluate_scenario(name)
                self.assertIn(report['outcome'], cure_quote.OUTCOMES)
                self.assertEqual(len(report['input_digest']), 64)
                self.assertEqual(len(report['quote_digest']), 64)


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-m', 'capital.cure_quote', *args],
                              capture_output=True, text=True, timeout=60, cwd=ROOT)

    def test_list_and_single_scenario(self):
        listed = self.run_cli('--list')
        self.assertEqual(listed.returncode, 0, listed.stderr)
        body = json.loads(listed.stdout)
        self.assertEqual(body['scenarios'], sorted(cure_quote.SCENARIOS))
        single = self.run_cli('--scenario', 'breach-tier1')
        self.assertEqual(single.returncode, 0, single.stderr)
        report = json.loads(single.stdout)
        self.assertEqual((report['format'], report['outcome']), (cure_quote.FORMAT, 'QUOTED'))
        self.assertEqual(report['amounts']['minimum_new_cash_krw'],
                         report['amounts']['gross_repayment_resources_krw'])

    def test_all_scenarios_and_misuse(self):
        full = self.run_cli()
        self.assertEqual(full.returncode, 0, full.stderr)
        body = json.loads(full.stdout)
        self.assertEqual(sorted(body['scenarios']), sorted(cure_quote.SCENARIOS))
        self.assertEqual(body['scenarios']['capacity-refusal']['command_admissibility']['status'], 'REFUSED')
        bad = self.run_cli('--scenario', 'not-a-scenario')
        self.assertEqual(bad.returncode, 2)
        both = self.run_cli('--list', '--scenario', 'breach-tier1')
        self.assertEqual(both.returncode, 2)


if __name__ == '__main__':
    unittest.main()
