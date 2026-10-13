"""Pinned finance input vectors: tests/vectors/finance_vectors.json.

The artifact is SIMULATED and supplies INPUT_VECTOR_CANDIDATE material for
FINANCE_PENDING_NODES candidates. It is not SEMANTIC_CONFORMANCE and it completes
no upstream node. Expected values below are written by hand from the scenario
and seed_demo stories, so the generator is not its own oracle.
"""
import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from capital import scenarios as scenario_module
from capital.protocol import CreditMachine
from capital.service import CapitalService, digest

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / 'tests' / 'vectors' / 'finance_vectors.json'
GOLDEN = ROOT / 'tests' / 'golden' / 'demo.json'
SCRIPT = ROOT / 'scripts' / 'finance_vectors.py'
NOTE = ROOT / 'docs' / 'decisions' / 'CAPITAL_UPSTREAM_BINDING.md'
VALIDATION = ROOT / 'docs' / 'VALIDATION.md'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = _load('finance_vectors', SCRIPT)
seed_demo = _load('seed_demo_for_finance_vectors', ROOT / 'scripts' / 'seed_demo.py')
decision_ledger = _load('decision_ledger_for_finance_vectors', ROOT / 'scripts' / 'decision_ledger.py')


def run_script(*argv):
    """Call script.main with its status lines swallowed; return (exit code, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = script.main(list(argv))
    return code, err.getvalue()


def load_artifact():
    return json.loads(ARTIFACT.read_text(encoding='ascii'))


def binding_candidate_ids():
    blocks = decision_ledger.extract_blocks(NOTE.read_text(encoding='utf-8'))
    assert len(blocks) == 1
    return blocks[0]['entries']['stage6_finance_candidates']['candidate_ids']


# Written by hand: which candidate each vector group supplies.
GROUP_CANDIDATE = {
    'scenario_obligations': 'fin-multi-payee-refund-proof',
    'f04_command_outcomes': 'fin-ledger-contract',
    'journal_projection_digests': 'fin-double-entry-projection',
}

# Per scenario, per step: (op, outcome, error, duplicate,
#   organizer (distributed, cancelled_unpaid, recovery_due, outstanding),
#   platform  (distributed, cancelled_unpaid, recovery_due, outstanding),
#   undistributed_cash, refund_face, refund_accepted).
# Organizer face is 95000 and platform face is 5000 in every scenario.
STATEMENT, DISTRIBUTE, REFUND, ACCEPT = (
    'observe_settlement_statement', 'apply_distribution', 'bind_refund', 'observe_mock_cancel_acceptance')
FRESH = ((0, 0, 0, 95000), (0, 0, 0, 5000))
PLATFORM_FIRST = ((92000, 0, 0, 3000), (5000, 0, 0, 0))
CANCELLED_AFTER_PAY = ((92000, 3000, 92000, 0), (5000, 0, 5000, 0))
FROZEN = 'DISTRIBUTION_ORDER_FROZEN'
BLOCKED = 'DISTRIBUTION_BLOCKED_REFUND_BEARER_UNDEFINED'
SCENARIO_STEPS = {
    'shortfall-platform': [
        (STATEMENT, 'ACCEPTED', None, False, *FRESH, 97000, 0, 0),
        (DISTRIBUTE, 'ACCEPTED', None, False, *PLATFORM_FIRST, 0, 0, 0),
        (DISTRIBUTE, 'ACCEPTED', None, False, *PLATFORM_FIRST, 0, 0, 0),
        (DISTRIBUTE, 'REJECTED', FROZEN, False, *PLATFORM_FIRST, 0, 0, 0),
    ],
    'shortfall-organizer': [
        (STATEMENT, 'ACCEPTED', None, False, *FRESH, 97000, 0, 0),
        (DISTRIBUTE, 'ACCEPTED', None, False, (95000, 0, 0, 0), (2000, 0, 0, 3000), 0, 0, 0),
    ],
    'partial-before': [
        (STATEMENT, 'ACCEPTED', None, False, *FRESH, 97000, 0, 0),
        (REFUND, 'ACCEPTED', None, False, *FRESH, 97000, 40000, 0),
        (DISTRIBUTE, 'REJECTED', BLOCKED, False, *FRESH, 97000, 40000, 0),
    ],
    'partial-after': [
        (STATEMENT, 'ACCEPTED', None, False, *FRESH, 97000, 0, 0),
        (DISTRIBUTE, 'ACCEPTED', None, False, *PLATFORM_FIRST, 0, 0, 0),
        (REFUND, 'ACCEPTED', None, False, *PLATFORM_FIRST, 0, 40000, 0),
        (DISTRIBUTE, 'REJECTED', BLOCKED, False, *PLATFORM_FIRST, 0, 40000, 0),
    ],
    'full-after': [
        (STATEMENT, 'ACCEPTED', None, False, *FRESH, 97000, 0, 0),
        (DISTRIBUTE, 'ACCEPTED', None, False, *PLATFORM_FIRST, 0, 0, 0),
        (REFUND, 'ACCEPTED', None, False, *CANCELLED_AFTER_PAY, 0, 100000, 0),
        (ACCEPT, 'ACCEPTED', None, False, *CANCELLED_AFTER_PAY, 0, 100000, 40000),
        (ACCEPT, 'ACCEPTED', None, True, *CANCELLED_AFTER_PAY, 0, 100000, 40000),
        (ACCEPT, 'ACCEPTED', None, False, *CANCELLED_AFTER_PAY, 0, 100000, 100000),
        (ACCEPT, 'REJECTED', 'REFUND_ACCEPTANCE_EXCEEDS_OBLIGATION', False, *CANCELLED_AFTER_PAY, 0, 100000, 100000),
    ],
    'split-refund': [
        (STATEMENT, 'ACCEPTED', None, False, *FRESH, 97000, 0, 0),
        (REFUND, 'ACCEPTED', None, False, *FRESH, 97000, 40000, 0),
        (REFUND, 'ACCEPTED', None, False, *FRESH, 97000, 100000, 0),
        (DISTRIBUTE, 'REJECTED', BLOCKED, False, *FRESH, 97000, 100000, 0),
    ],
    'duplicate-statement': [
        (STATEMENT, 'ACCEPTED', None, False, *FRESH, 97000, 0, 0),
        (STATEMENT, 'ACCEPTED', None, True, *FRESH, 97000, 0, 0),
        (STATEMENT, 'REJECTED', 'STATEMENT_BINDING_CONFLICT', False, *FRESH, 97000, 0, 0),
        (STATEMENT, 'REJECTED', 'SETTLEMENT_COMPONENT_MISMATCH', False, *FRESH, 97000, 0, 0),
    ],
    'late-cash': [
        (REFUND, 'ACCEPTED', None, False, (0, 95000, 0, 0), (0, 5000, 0, 0), 0, 100000, 0),
        (STATEMENT, 'ACCEPTED', None, False, (0, 95000, 0, 0), (0, 5000, 0, 0), 100000, 100000, 0),
        (DISTRIBUTE, 'ACCEPTED', None, False, (0, 95000, 0, 0), (0, 5000, 0, 0), 100000, 100000, 0),
    ],
    'split-statement': [
        (STATEMENT, 'ACCEPTED', None, False, *FRESH, 48000, 0, 0),
        (DISTRIBUTE, 'ACCEPTED', None, False, (43000, 0, 0, 52000), (5000, 0, 0, 0), 0, 0, 0),
        (STATEMENT, 'ACCEPTED', None, False, (43000, 0, 0, 52000), (5000, 0, 0, 0), 49000, 0, 0),
        (DISTRIBUTE, 'ACCEPTED', None, False, *PLATFORM_FIRST, 0, 0, 0),
    ],
}

# operation_id -> (outcome, error, journal entry, phase, drawn exposure, outstanding exposure)
F04_COMMANDS = [
    ('op-closed-offer', 'ACCEPTED', None, 0, 'OFFERED', 0, 0),
    ('op-closed-approve', 'ACCEPTED', None, 1, 'APPROVED', 0, 0),
    ('op-closed-bind', 'ACCEPTED', None, 2, 'APPROVED', 0, 0),
    ('op-closed-draw', 'ACCEPTED', None, 3, 'DRAWN', 20000, 20000),
    ('op-closed-repay', 'ACCEPTED', None, 4, 'DRAWN', 20000, 0),
    ('op-closed-close', 'ACCEPTED', None, 5, 'CLOSED', 20000, 0),
    ('op-defaulted-offer', 'ACCEPTED', None, 6, 'OFFERED', 0, 0),
    ('op-defaulted-approve', 'ACCEPTED', None, 7, 'APPROVED', 0, 0),
    ('op-defaulted-bind', 'ACCEPTED', None, 8, 'APPROVED', 0, 0),
    ('op-defaulted-draw', 'ACCEPTED', None, 9, 'DRAWN', 30000, 30000),
    ('op-defaulted-default', 'ACCEPTED', None, 10, 'DEFAULTED', 30000, 30000),
    ('op-rejected-offer', 'ACCEPTED', None, 11, 'OFFERED', 0, 0),
    ('op-rejected-reject', 'ACCEPTED', None, 12, 'REJECTED', 0, 0),
    ('op-cancelled-offer', 'ACCEPTED', None, 13, 'OFFERED', 0, 0),
    ('op-cancelled-cancel', 'ACCEPTED', None, 14, 'CANCELLED', 0, 0),
    ('op-unbound-offer', 'ACCEPTED', None, 15, 'OFFERED', 0, 0),
    ('op-unbound-approve', 'ACCEPTED', None, 16, 'APPROVED', 0, 0),
    ('op-unbound-draw', 'ACCEPTED', None, 17, 'DRAWN', 15000, 15000),
    ('op-pending-offer', 'ACCEPTED', None, 18, 'OFFERED', 0, 0),
    ('op-pending-approve', 'ACCEPTED', None, 19, 'APPROVED', 0, 0),
    ('op-pending-bind', 'ACCEPTED', None, 20, 'APPROVED', 0, 0),
    ('op-pending-draw', 'REJECTED', 'SETTLEMENT_NOT_COMMITTED', None, 'APPROVED', 0, 0),
]
# The first 21 rows above are the 21 accepted journal entries; the 22nd is the rejected draw.
# Debit total of every journal prefix, 0 through 21 entries. The three fixture claims
# post 300000 first; a draw adds its amount and a repay adds the repaid amount.
PREFIX_DEBIT = [300000] * 4 + [320000] + [340000] * 5 + [370000] * 8 + [385000] * 4
CONSERVATION = [
    'DEBITS_EQUAL_CREDITS_EVERY_STEP', 'CLAIM_FACE_EQUALS_PAYEE_FACES', 'ADVANCE_EXPOSURE_CONSERVATION',
    'REFUND_ACCEPTANCE_CONSERVATION', 'NO_REAL_EFFECT',
]
UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')


class ArtifactShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = ARTIFACT.read_bytes()
        cls.artifact = load_artifact()

    def test_top_level_labels_and_explicit_non_claims(self):
        a = self.artifact
        self.assertEqual(a['format'], 'KIX_CAPITAL_FINANCE_VECTORS_V1')
        self.assertEqual(a['label'], 'SIMULATED')
        self.assertIs(a['funds_executed'], False)
        self.assertEqual(a['vector_role'], 'INPUT_VECTOR_CANDIDATE')
        self.assertIs(a['semantic_conformance'], False)
        self.assertEqual(a['upstream_nodes_completed'], [])
        self.assertEqual(a['source_commit'], '7481b0e16ce9b903abbffa62249bb91cd9e63cfe')
        self.assertIn('not SEMANTIC_CONFORMANCE', a['note'])
        self.assertIn('completes no upstream node', a['note'])

    def test_candidate_index_is_the_eight_ids_of_the_binding_note(self):
        ids = binding_candidate_ids()
        self.assertEqual(len(ids), 8)
        self.assertEqual([row['id'] for row in self.artifact['candidates']], ids)

    def test_every_group_names_one_candidate_and_carries_the_label(self):
        groups = self.artifact['groups']
        self.assertEqual(sorted(groups), sorted(GROUP_CANDIDATE))
        ids = binding_candidate_ids()
        for name, group in groups.items():
            with self.subTest(group=name):
                self.assertEqual(group['candidate'], GROUP_CANDIDATE[name])
                self.assertIn(group['candidate'], ids)
                self.assertEqual(group['label'], 'INPUT_VECTOR_CANDIDATE')
                self.assertEqual(group['data_label'], 'SIMULATED')
        supplied = {row['id']: row['vectors'] for row in self.artifact['candidates']}
        for name, candidate in GROUP_CANDIDATE.items():
            self.assertEqual(supplied[candidate], name)
        self.assertEqual(sorted(key for key, value in supplied.items() if value is None), sorted(
            set(ids) - set(GROUP_CANDIDATE.values())))

    def test_bytes_are_canonical_ascii_with_no_volatile_or_host_text(self):
        self.assertTrue(self.raw.endswith(b'\n') and not self.raw.endswith(b'\n\n'))
        self.raw.decode('ascii')
        again = json.dumps(self.artifact, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n'
        self.assertEqual(again.encode('ascii'), self.raw)
        text = self.raw.decode('ascii')
        self.assertIsNone(UUID.search(text))
        for fragment in ('/workspace', '/tmp/', '/home/', 'instance_id', 'workspace.json'):
            self.assertNotIn(fragment, text)

    def test_docs_state_the_non_claim(self):
        text = VALIDATION.read_text(encoding='utf-8')
        self.assertIn('## finance-vector-pack', text)
        section = text.split('## finance-vector-pack', 1)[1].split('\n## ', 1)[0]
        for phrase in ('INPUT_VECTOR_CANDIDATE', 'not SEMANTIC_CONFORMANCE', 'completes no upstream node'):
            self.assertIn(phrase, section)
        self.assertIn('not SEMANTIC_CONFORMANCE', script.__doc__)
        self.assertIn('completes no upstream node', script.__doc__)


class ScenarioVectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.group = load_artifact()['groups']['scenario_obligations']
        cls.by_id = {row['id']: row for row in cls.group['scenarios']}

    def test_nine_scenarios_and_thirty_five_steps(self):
        self.assertEqual(
            [row['id'] for row in self.group['scenarios']],
            ['shortfall-platform', 'shortfall-organizer', 'partial-before', 'partial-after', 'full-after',
             'split-refund', 'duplicate-statement', 'late-cash', 'split-statement'])
        self.assertEqual(self.group['scenario_count'], 9)
        self.assertEqual(self.group['step_count'], 35)
        self.assertEqual(sum(len(rows) for rows in SCENARIO_STEPS.values()), 35)
        self.assertEqual(sum(len(row['steps']) for row in self.group['scenarios']), 35)
        self.assertIs(self.group['policy_chosen'], False)

    def test_per_step_obligation_values_match_the_hand_written_table(self):
        self.assertEqual(sorted(self.by_id), sorted(SCENARIO_STEPS))
        for scenario_id, want in SCENARIO_STEPS.items():
            got = self.by_id[scenario_id]
            self.assertEqual(got['step_count'], len(want))
            self.assertIs(got['all_predicates_matched'], True)
            for ordinal, (step, expected) in enumerate(zip(got['steps'], want), 1):
                with self.subTest(scenario=scenario_id, ordinal=ordinal):
                    op, outcome, error, duplicate, organizer, platform, undistributed, refund, accepted = expected
                    self.assertEqual(step['ordinal'], ordinal)
                    self.assertEqual((step['op'], step['outcome'], step['error'], step['duplicate']),
                                     (op, outcome, error, duplicate))
                    self.assertEqual(step['expected_error'], error)
                    rows = {row['payee']: row for row in step['obligations']}
                    self.assertEqual(sorted(rows), ['organizer', 'platform'])
                    for payee, face, values in (('organizer', 95000, organizer), ('platform', 5000, platform)):
                        row = rows[payee]
                        self.assertEqual(row['face'], face)
                        self.assertEqual(
                            (row['distributed'], row['cancelled_unpaid'], row['recovery_due'], row['outstanding']),
                            values)
                    self.assertEqual(step['totals']['undistributed_cash'], undistributed)
                    self.assertEqual(step['totals']['refund_face'], refund)
                    self.assertEqual(step['totals']['refund_accepted'], accepted)
                    self.assertEqual(step['totals']['refund_outstanding'], refund - accepted)

    def test_every_step_conserves_faces_and_cash(self):
        for scenario in self.group['scenarios']:
            self.assertEqual([row['face'] for row in scenario['initial']['obligations']], [95000, 5000])
            for step in scenario['steps']:
                with self.subTest(scenario=scenario['id'], ordinal=step['ordinal']):
                    rows = step['obligations']
                    self.assertEqual(sum(row['face'] for row in rows), 100000)
                    for row in rows:
                        self.assertEqual(row['face'], row['distributed'] + row['cancelled_unpaid'] + row['outstanding'])
                    totals = step['totals']
                    self.assertEqual(totals['confirmed_cash'], totals['distributed_cash'] + totals['undistributed_cash'])
                    self.assertEqual(totals['distributed_cash'], sum(row['distributed'] for row in rows))
                    self.assertTrue(all(step['checks'].values()))
                    self.assertEqual(len(step['checks']), 5 + 1 + (step['outcome'] == 'REJECTED'))

    def test_rejected_and_duplicate_steps_change_nothing(self):
        rejected = duplicates = 0
        for scenario in self.group['scenarios']:
            previous = scenario['initial']['view_digest']
            for step in scenario['steps']:
                if step['outcome'] == 'REJECTED':
                    rejected += 1
                    self.assertEqual(step['view_digest'], previous, (scenario['id'], step['ordinal']))
                    self.assertIn('REJECTION_PRESERVES_STATE', step['checks'])
                if step['duplicate']:
                    duplicates += 1
                    self.assertEqual(step['view_digest'], previous, (scenario['id'], step['ordinal']))
                previous = step['view_digest']
        self.assertEqual((rejected, duplicates), (7, 2))

    def test_view_digests_match_the_live_service_scenarios(self):
        service = CapitalService()
        for scenario_id, got in self.by_id.items():
            live = service.scenarios(scenario_id)['scenario']
            self.assertEqual(got['final_view_digest'], digest(live['final']))
            self.assertEqual(got['initial']['view_digest'], digest(live['initial']))
            self.assertEqual([step['view_digest'] for step in got['steps']],
                             [digest(step['view']) for step in live['steps']])


class F04VectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact = load_artifact()
        cls.group = cls.artifact['groups']['f04_command_outcomes']
        cls.projection = cls.artifact['groups']['journal_projection_digests']

    def test_twenty_two_commands_one_rejected(self):
        self.assertEqual((self.group['command_count'], self.group['accepted'], self.group['rejected']), (22, 21, 1))
        self.assertEqual(len(self.group['commands']), 22)
        for ordinal, (row, want) in enumerate(zip(self.group['commands'], F04_COMMANDS), 1):
            with self.subTest(operation_id=want[0]):
                self.assertEqual(row['ordinal'], ordinal)
                self.assertEqual(
                    (row['operation_id'], row['outcome'], row['error'], row['journal_entry'],
                     row['phase_after'], row['drawn_exposure_after'], row['outstanding_exposure_after']), want)
                accepted = sum(1 for earlier in F04_COMMANDS[:ordinal] if earlier[1] == 'ACCEPTED')
                self.assertEqual(row['journal_length_after'], accepted)

    def test_rejected_draw_leaves_the_book_where_it_was(self):
        rejected = self.group['commands'][-1]
        before = self.group['commands'][-2]
        self.assertEqual((rejected['op'], rejected['advance_id']), ('draw', 'sim-pending-settlement'))
        self.assertEqual(rejected['state_digest_after'], before['state_digest_after'])
        self.assertEqual(rejected['journal_length_after'], 21)

    def test_journal_rows_follow_the_accepted_commands(self):
        journal = self.group['journal']
        accepted = [row for row in self.group['commands'] if row['outcome'] == 'ACCEPTED']
        self.assertEqual(len(journal), 21)
        for index, (entry, command) in enumerate(zip(journal, accepted)):
            with self.subTest(index=index):
                self.assertEqual(entry['index'], index)
                self.assertEqual((entry['op'], entry['advance_id'], entry['idempotency_key']),
                                 (command['op'], command['advance_id'], command['operation_id']))
        self.assertEqual(journal[0]['body_scalars'], {'amount': 20000, 'beneficiary_role': 'fixture-organizer'})
        self.assertEqual(journal[2]['body_scalars'], {'settlement_id': 'sim-committed'})
        self.assertEqual(journal[3]['body_scalars'], {'draw_id': 'draw-op-closed-draw'})
        self.assertEqual(journal[4]['body_scalars'],
                         {'amount': 20000, 'repay_id': 'repay-op-closed-repay', 'sequence': 1})
        self.assertEqual(journal[20]['body_scalars'], {'settlement_id': 'sim-pending'})

    def test_final_digest_is_the_golden_state_digest(self):
        golden = json.loads(GOLDEN.read_text(encoding='utf-8'))
        self.assertEqual(self.group['state_digest'], golden['state_digest'])
        self.assertEqual(self.group['commands'][-1]['state_digest_after'], golden['state_digest'])

    def test_recorded_digests_match_a_live_replay(self):
        service = seed_demo.build_service()
        try:
            journal = service.machine.export_journal()
            self.assertEqual(self.group['journal_digest'], digest(journal))
            restored = CreditMachine.restore(journal, service.fixtures)
            self.assertEqual(restored.state_digest(), self.group['state_digest'])
            self.assertEqual(self.projection['journal_digest'], digest(journal))
            for entry, row in zip(journal, self.group['journal']):
                self.assertEqual(row['body_digest'], digest(entry['body']))
        finally:
            seed_demo._release(service.producer)

    def test_each_command_digest_is_the_restored_prefix_digest(self):
        prefixes = {row['journal_length']: row['state_digest'] for row in self.projection['prefixes']}
        for row in self.group['commands']:
            with self.subTest(operation_id=row['operation_id']):
                self.assertEqual(row['state_digest_after'], prefixes[row['journal_length_after']])


class ProjectionDigestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.group = load_artifact()['groups']['journal_projection_digests']

    def test_every_prefix_balances_and_totals_follow_the_story(self):
        prefixes = self.group['prefixes']
        self.assertEqual([row['journal_length'] for row in prefixes], list(range(22)))
        self.assertEqual(len(PREFIX_DEBIT), 22)
        for row, debit in zip(prefixes, PREFIX_DEBIT):
            with self.subTest(journal_length=row['journal_length']):
                self.assertEqual((row['debit'], row['credit']), (debit, debit))
                # Three evidence entries, then one entry per journal entry.
                self.assertEqual(row['entry_count'], 3 + row['journal_length'])
        # Every accepted journal entry moves the book and the projection.
        self.assertEqual(len({row['state_digest'] for row in prefixes}), 22)
        self.assertEqual(len({row['entries_digest'] for row in prefixes}), 22)

    def test_chart_policy_and_labels(self):
        self.assertEqual(self.group['chart'], 'SIMULATION_FIXED_V1')
        self.assertEqual(self.group['accounting_policy'], 'SYNTHETIC_UNADOPTED')

    def test_final_prefix_is_the_golden_pin(self):
        golden = json.loads(GOLDEN.read_text(encoding='utf-8'))
        last = self.group['prefixes'][-1]
        self.assertEqual(last['state_digest'], golden['state_digest'])
        self.assertEqual(last['debit'], golden['projection_totals']['debit'])
        self.assertEqual(last['credit'], golden['projection_totals']['credit'])
        self.assertEqual((last['debit'], last['credit']), (385000, 385000))

    def test_final_prefix_matches_the_live_projection(self):
        service = seed_demo.build_service()
        try:
            live = service.projection()
        finally:
            seed_demo._release(service.producer)
        last = self.group['prefixes'][-1]
        self.assertEqual(last['state_digest'], live['cut'])
        self.assertEqual(last['entries_digest'], digest(live['entries']))
        self.assertEqual(last['accounts_digest'], digest(live['accounts']))
        self.assertEqual(last['read_model_digest'], digest(live['read_model']))
        self.assertEqual(self.group['final']['conservation'], live['conservation'])

    def test_final_accounts_and_conservation(self):
        self.assertEqual([row['predicate'] for row in self.group['final']['conservation']], CONSERVATION)
        self.assertTrue(all(row['matched'] is True for row in self.group['final']['conservation']))
        accounts = {row['code']: row for row in self.group['final']['accounts']}
        self.assertEqual(len(accounts), 16)
        self.assertEqual(sum(row['debit_total'] for row in accounts.values()), 385000)
        self.assertEqual(sum(row['credit_total'] for row in accounts.values()), 385000)
        self.assertEqual(
            {key: accounts[key] for key in ('SIM_ADVANCE_OBLIGATION:sim-closed', 'SIM_ADVANCE_OBLIGATION:sim-defaulted')},
            {'SIM_ADVANCE_OBLIGATION:sim-closed': {
                'code': 'SIM_ADVANCE_OBLIGATION:sim-closed', 'debit_total': 20000, 'credit_total': 20000, 'balance': 0},
             'SIM_ADVANCE_OBLIGATION:sim-defaulted': {
                'code': 'SIM_ADVANCE_OBLIGATION:sim-defaulted', 'debit_total': 0, 'credit_total': 30000, 'balance': 30000}})
        self.assertEqual(accounts['SIM_REPAY_MEMO:sim-closed']['credit_total'], 20000)
        self.assertEqual(accounts['SIM_CLAIM_FACE:sim-committed']['debit_total'], 100000)
        self.assertNotIn('SIM_ADVANCE_EXPOSURE:sim-pending-settlement', accounts)


class RegenerationTests(unittest.TestCase):
    def test_regeneration_reproduces_the_committed_bytes(self):
        first = script.build_artifact()
        self.assertEqual(first, script.build_artifact())
        self.assertEqual(first, ARTIFACT.read_bytes())

    def test_regeneration_is_independent_of_hash_seed_and_working_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'out.json'
            env = {**os.environ, 'PYTHONHASHSEED': '12345'}
            proc = subprocess.run(
                [sys.executable, os.fspath(SCRIPT), '--write', '--file', os.fspath(target)],
                cwd=tmp, env=env, capture_output=True, text=True, timeout=120, check=False)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(target.read_bytes(), ARTIFACT.read_bytes())

    def test_check_passes_on_the_committed_artifact(self):
        proc = subprocess.run(
            [sys.executable, os.fspath(SCRIPT), '--check'],
            cwd=ROOT, capture_output=True, text=True, timeout=120, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, '')

    def test_a_mode_is_required_and_the_two_modes_exclude_each_other(self):
        for argv in ([], ['--check', '--write']):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    script.main(argv)
                self.assertEqual(caught.exception.code, 2)

    def test_write_into_another_file_matches_and_check_catches_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'nested' / 'finance_vectors.json'
            self.assertEqual(run_script('--write', '--file', os.fspath(target))[0], 0)
            self.assertEqual(target.read_bytes(), ARTIFACT.read_bytes())
            self.assertEqual(run_script('--check', '--file', os.fspath(target)), (0, ''))
            original = target.read_bytes()
            digest_at = original.index(b'"view_digest":"') + len(b'"view_digest":"')
            edits = {
                'a digest character': original[:digest_at] + (b'1' if original[digest_at:digest_at + 1] == b'0' else b'0')
                + original[digest_at + 1:],
                'a number': original.replace(b'"outstanding":3000', b'"outstanding":3001', 1),
                'a label': original.replace(b'"label":"INPUT_VECTOR_CANDIDATE"', b'"label":"ADOPTED"', 1),
                'a candidate id': original.replace(b'"candidate":"fin-ledger-contract"', b'"candidate":"fin-finance-closeout"', 1),
            }
            for what, changed in sorted(edits.items()):
                with self.subTest(drift=what):
                    self.assertNotEqual(changed, original)
                    target.write_bytes(changed)
                    code, err = run_script('--check', '--file', os.fspath(target))
                    self.assertEqual(code, 1)
                    self.assertIn('finance vectors drift: $', err)
                    self.assertIn('--write', err)
                    target.write_bytes(original)
                    self.assertEqual(run_script('--check', '--file', os.fspath(target))[0], 0)
            target.write_bytes(original[:len(original) // 2])
            self.assertEqual(run_script('--check', '--file', os.fspath(target))[0], 1)
            target.write_bytes(original.rstrip(b'\n'))
            self.assertEqual(run_script('--check', '--file', os.fspath(target))[0], 1)
            self.assertEqual(run_script('--write', '--file', os.fspath(target))[0], 0)
            self.assertEqual(target.read_bytes(), original)
            target.unlink()
            code, err = run_script('--check', '--file', os.fspath(target))
            self.assertEqual(code, 1)
            self.assertIn('missing', err)
            self.assertFalse(target.exists())

    def test_check_writes_nothing(self):
        before = (ARTIFACT.read_bytes(), ARTIFACT.stat().st_mtime_ns,
                  sorted(path.name for path in ARTIFACT.parent.iterdir()))
        self.assertEqual(run_script('--check'), (0, ''))
        after = (ARTIFACT.read_bytes(), ARTIFACT.stat().st_mtime_ns,
                 sorted(path.name for path in ARTIFACT.parent.iterdir()))
        self.assertEqual(after, before)

    def test_a_changed_source_value_changes_the_vectors(self):
        """The artifact is built from the live code, so a policy edit cannot pass --check unseen."""
        with mock.patch.dict(scenario_module.POLICY, {'fee_bps': 400}):
            changed = script.build_artifact()
        self.assertNotEqual(changed, ARTIFACT.read_bytes())
        self.assertEqual(script.build_artifact(), ARTIFACT.read_bytes())


if __name__ == '__main__':
    unittest.main()
