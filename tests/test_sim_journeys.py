"""Named SIMULATED journeys T03-sim through T06-sim: steps, pinned goldens, and the acceptance stage.

The journeys run a real loopback server (T04-sim and T06-sim on --workspace subprocesses,
T06-sim killed with SIGKILL). Nothing here claims T01-T06 qualification, integration, or
human acceptance.
"""
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from capital.service import CapitalService

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / 'tests' / 'golden'
ACCEPTANCE_DOC = ROOT / 'docs' / 'ACCEPTANCE_KO.md'


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


journeys = _load('sim_journeys')
acceptance = _load('acceptance')


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = journeys.main(argv)
    return code, out.getvalue(), err.getvalue()


def _step(result, fragment):
    matches = [step for step in result['steps'] if fragment in step['name']]
    assert len(matches) == 1, (fragment, [step['name'] for step in matches])
    return matches[0]


_RESULTS = {}


def _result(journey_id):
    """One cached run per journey; the golden-equality test reruns each itself."""
    if journey_id not in _RESULTS:
        _RESULTS[journey_id] = journeys.RUNNERS[journey_id]()
    return _RESULTS[journey_id]


class JourneyBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t03 = _result('T03-sim')
        cls.t04 = _result('T04-sim')
        cls.t05 = _result('T05-sim')
        cls.t06 = _result('T06-sim')
        cls.n1 = _result('N1-sim')
        cls.n2 = _result('N2-sim')
        cls.all = (cls.t03, cls.t04, cls.t05, cls.t06, cls.n1, cls.n2)


class CommonTests(JourneyBase):
    def test_labels_and_flags_on_all_journeys(self):
        for result in self.all:
            with self.subTest(result['journey']):
                self.assertEqual(result['label'], 'SIMULATED')
                self.assertIs(result['funds_executed'], False)
                self.assertIs(result['integrated'], False)
                self.assertIs(result['qualification_claimed'], False)
                self.assertEqual(result['seed'], 'CAPITAL-SIM-JOURNEYS-V1')
                self.assertEqual(result['step_count'], len(result['steps']))
                self.assertGreater(result['step_count'], 20 if result['journey'].startswith('T') else 14)
                self.assertEqual([step['n'] for step in result['steps']], list(range(1, result['step_count'] + 1)))
                for step in result['steps']:
                    self.assertEqual(step['status'], step['expect'])
                self.assertEqual(len(result['digest']), 64)

    def test_committed_goldens_equal_the_live_run(self):
        for result in self.all:
            path = GOLDEN / journeys.GOLDEN_FILES[result['journey']]
            self.assertEqual(path.read_text(encoding='utf-8'), journeys.render(result), path.name)

    def test_second_run_has_the_same_digests(self):
        for result in self.all:
            with self.subTest(result['journey']):
                self.assertEqual(journeys.RUNNERS[result['journey']]()['digest'], result['digest'])

    def test_goldens_carry_no_process_identity(self):
        for name in journeys.GOLDEN_FILES.values():
            data = json.loads((GOLDEN / name).read_text(encoding='utf-8'))
            journeys._reject_volatile(data)
            text = json.dumps(data)
            for needle in ('local_token', 'instance_id', '127.0.0.1', 'capital-sim-t06', 'X-Capital'):
                self.assertNotIn(needle, text, needle)

    def test_no_operation_id_is_posted_twice(self):
        for result in self.all:
            step = _step(result, 'no operation id was posted twice')
            self.assertIs(step['status'], True)
            if result['journey'] == 'N2-sim':
                self.assertEqual(step['facts']['posted'], 5)
            else:
                self.assertGreater(step['facts']['posted'], 5)


class T03Tests(JourneyBase):
    def test_lifecycle_reaches_close_with_no_exceptions(self):
        for fragment in ('offer sim-t03-a', 'approve sim-t03-a', 'bind_settlement sim-t03-a',
                         'draw sim-t03-a', 'repay the outstanding principal', 'close sim-t03-a'):
            self.assertEqual(_step(self.t03, fragment)['status'], [200, 'ACCEPTED', None], fragment)
        self.assertEqual(_step(self.t03, 'the draw receipt is queryable')['status'],
                         [200, 'ACCEPTED', False])
        final = _step(self.t03, 'final phases and digests')
        self.assertEqual(final['status'], {'sim-t03-a': 'CLOSED'})
        facts = final['facts']
        self.assertEqual((facts['sim_day'], facts['interest_payments']), (45, 'NOT_RECORDED'))
        self.assertIs(facts['funds_executed'], False)
        for key in ('overlay_state_digest', 'risk_digest', 'state_digest'):
            self.assertRegex(facts[key], r'^[0-9a-f]{64}$', key)

    def test_act365_accrual_is_pinned_and_stops_at_close(self):
        day15 = _step(self.t03, 'through sim_day 15')
        day30 = _step(self.t03, 'through sim_day 30')
        self.assertEqual((day15['status'], day30['status'][0]),
                         (['DRAWN', 15, True, 0, False], 30))
        self.assertEqual((day15['facts']['interest_due_krw'], day30['facts']['interest_due_krw']),
                         (86, 172))
        self.assertEqual(day30['facts']['cumulative_exact_contract'], '12600/73')
        after = _step(self.t03, 'no interest accrues after close')
        self.assertEqual(after['status'], [[], 30, 'CLOSED'])
        self.assertEqual(after['facts']['interest_due_krw'], day30['facts']['interest_due_krw'])

    def test_full_repay_leaves_the_interest_memo_unpaid_and_close_still_works(self):
        self.assertEqual(_step(self.t03, 'not close-ready')['status'],
                         ['DRAWN', 0, False, 'NOT_RECORDED'])
        quote = _step(self.t03, 'full-repayment allocation quote')['facts']
        self.assertEqual(quote['order'], ['DEFAULT_INTEREST', 'INTEREST', 'PRINCIPAL'])
        self.assertEqual((quote['to_interest'], quote['to_principal']), (172, 30_000))
        self.assertEqual(quote['fsm_repay'], {'amount': 30_000, 'sequence': 1})
        recon = _step(self.t03, 'reconciliation is clean')
        self.assertEqual(recon['status'], [200, 'MATCHED', ['MATCHED']])
        self.assertIn('overlay_fold_digest_equals_persisted', recon['facts']['checks'])
        risk = _step(self.t03, 'risk rollup is bound')
        self.assertEqual(risk['status'], [200, 'BOUND', True, 30_000])
        self.assertRegex(risk['facts']['risk_digest'], r'^[0-9a-f]{64}$')


class T04Tests(JourneyBase):
    def test_seeded_book_matches_the_demo_pin_over_http(self):
        seeds = [step for step in self.t04['steps'] if step['name'].startswith('seed ')]
        self.assertEqual(len(seeds), len(journeys.seed_demo.STEPS))
        rejected = _step(self.t04, 'seed draw sim-pending-settlement')
        self.assertEqual(rejected['status'], [200, 'REJECTED', 'SETTLEMENT_NOT_COMMITTED'])
        pin = _step(self.t04, 'matches the seeded-demo state_digest pin')
        demo = json.loads((GOLDEN / 'demo.json').read_text(encoding='utf-8'))
        self.assertEqual(pin['status'], demo['state_digest'])
        self.assertEqual(pin['expect'], demo['state_digest'])
        self.assertEqual(pin['facts']['cases'], 6)

    def test_auditor_reads_and_offline_verification(self):
        bind = _step(self.t04, 'auditor role bound')
        self.assertEqual(bind['status'], [200, 'auditor', 'NOT_BOUND', 'NOT_BOUND', 'NOT_BOUND'])
        overlay = _step(self.t04, 'auditor reads the overlay')
        self.assertEqual(overlay['status'], [200, 10, 'BOUND', 'INCLUDED_IN_MANIFEST_V3'])
        self.assertRegex(overlay['facts']['overlay_state_digest'], r'^[0-9a-f]{64}$')
        self.assertEqual(_step(self.t04, 'auditor reads the risk rollup')['status'],
                         [200, 'BOUND', True])
        self.assertEqual(_step(self.t04, 'terms portfolio rollup')['status'], [200, 'BOUND'])
        recon = _step(self.t04, 'every check MATCHED')
        self.assertEqual(recon['status'], [200, 'MATCHED', ['MATCHED']])
        self.assertIn('overlay_fold_digest_equals_persisted', recon['facts']['checks'])
        exported = _step(self.t04, 'auditor exports the V3 manifest')
        self.assertEqual(exported['status'],
                         [200, 'KIX_CAPITAL_EXPORT_MANIFEST_V3', 'COMPLETE', 'UNSIGNED', 'NOT_BOUND'])
        self.assertIs(exported['facts']['stage7_authenticated_export'], False)
        verify = _step(self.t04, 'rechecks the exported manifest')
        self.assertEqual(verify['status'],
                         [0, True, 'KIX_CAPITAL_EXPORT_MANIFEST_V3', 'MATCHED', 'NOT_BOUND', False])
        self.assertEqual(set(verify['facts']['sections'].values()), {'MATCHED'})
        audit = _step(self.t04, 'audits the live file read-only')
        self.assertEqual(audit['status'],
                         [0, True, 'OFFLINE_WORKSPACE_AUDIT', 'MATCHED', False, False, False])
        self.assertEqual(set(audit['facts']['checks'].values()), {'MATCHED'})
        self.assertEqual(audit['facts']['stage5_durable_transactions'], 'NOT_BOUND')
        self.assertEqual(audit['facts']['durable'], 'LOCAL_FILE_WORKSPACE')
        final = _step(self.t04, 'final phases and digests')
        self.assertEqual(final['status'],
                         {row[0]: row[1] for row in journeys.seed_demo.EXPECTED})
        facts = final['facts']
        self.assertEqual((facts['sim_day'], facts['funds_executed']), (10, False))
        for key in ('overlay_state_digest', 'risk_digest', 'state_digest'):
            self.assertRegex(facts[key], r'^[0-9a-f]{64}$', key)

    def test_auditor_and_observer_tokens_cannot_write_or_export(self):
        for fragment in ('cannot advance the clock', 'cannot submit a command',
                         'cannot export the manifest'):
            self.assertEqual(_step(self.t04, fragment)['status'], [403, 'ROLE_FORBIDDEN'], fragment)


class T05Tests(JourneyBase):
    def test_partial_allocation_leaves_part_of_the_organizer_line_unreserved(self):
        step = _step(self.t05, 'partial allocation')
        facts = step['facts']
        self.assertEqual(step['status'], [200, ['sim-committed'], True])
        self.assertEqual(facts['advances'], {'sim-a': 48_000, 'sim-b': 20_000})
        self.assertEqual((facts['reserved_open_on_claim'], facts['organizer_line_face']), (68_000, 95_000))
        self.assertEqual(facts['unreserved_remainder'], 27_000)

    def test_refund_event_is_labelled_out_of_band_and_the_pinned_refusal_is_shown(self):
        event = _step(self.t05, 'partial refund before allocation')
        self.assertEqual(event['kind'], 'SETTLEMENT_EVENT')
        self.assertEqual(event['facts']['label'], 'SIMULATED_OUT_OF_BAND_SETTLEMENT_EVENT')
        self.assertEqual(event['facts']['scope'], 'DISPOSABLE_BOOK_ONLY')
        self.assertEqual(event['status'][-1],
                         ['apply_distribution', 'DISTRIBUTION_BLOCKED_REFUND_BEARER_UNDEFINED', True])
        refusal = _step(self.t05, 'pinned refusal while')
        self.assertEqual(refusal['status'], [200, 'REJECTED', 'REFUND_OBLIGATION_OPEN'])
        self.assertLess(refusal['n'], _step(self.t05, 'shadow refund split')['n'])

    def test_shadow_split_is_beside_the_pinned_refusal_and_not_applied(self):
        shadow = _step(self.t05, 'shadow refund split')
        self.assertEqual(shadow['status'], [200, 'UNSUPPORTED_BY_PINNED_FSM', 'SHADOW_COMPUTED', False])
        facts = shadow['facts']
        self.assertEqual(facts['label'], 'SHADOW_NOT_APPLIED')
        self.assertIs(facts['policy_adopted'], False)
        self.assertIn('frozen', facts['vector'])
        classes = {row['reason_class']: row for row in facts['per_class']}
        self.assertIn('RC1_BUYER_WITHIN_POLICY', classes)
        self.assertEqual(sorted(classes)[0], 'RC1_BUYER_WITHIN_POLICY')
        for row in facts['per_class']:
            self.assertIn(row['reconciliation'], ('DIVERGES_PINNED_FSM_BY_DESIGN', 'NOT_COMPARABLE'))
            self.assertEqual([line['payee'] for line in row['lines']], ['organizer', 'platform'])
        self.assertEqual(classes['RC1_BUYER_WITHIN_POLICY']['reconciliation'], 'DIVERGES_PINNED_FSM_BY_DESIGN')

    def test_margin_call_acceleration_and_late_cash_follow_the_note(self):
        called = _step(self.t05, 'sim-a is called')['facts']
        accelerated = _step(self.t05, 'sim-a accelerated')['facts']
        self.assertEqual(called['margin_state'], 'CALLED')
        self.assertEqual(called['default_eligible_day'], None)
        self.assertEqual(accelerated['margin_state'], 'ACCELERATED')
        self.assertIs(accelerated['interest_rebased'], False)
        self.assertEqual(accelerated['interest_basis'], 'NOT_REBASED')
        # Deadline 3 + window 5 = 8; acceleration on the next tick; eligible = 8 + grace 10 + 1.
        self.assertEqual((called['cure_deadline'], accelerated['default_eligible_day']), (8, 19))
        self.assertEqual(_step(self.t05, 'allocation quote')['status'], [200, 'NOT_APPLICABLE', 'NOT_APPLICABLE'])
        split = _step(self.t05, 'late cash splits')['facts']
        self.assertEqual(split['order'], ['DEFAULT_INTEREST', 'INTEREST', 'PRINCIPAL'])
        self.assertEqual(split['principal_share_krw'],
                         split['cash'] - split['interest_due_krw'] - split['default_interest_due_krw'])
        later = _step(self.t05, 'acceleration is not reversed')
        self.assertEqual(later['status'], 'ACCELERATED')
        self.assertEqual(later['facts']['principal_outstanding_krw'], 48_000 - split['principal_share_krw'])

    def test_close_and_human_default_with_the_proposal_only_f04(self):
        self.assertEqual(_step(self.t05, 'not close-ready')['status'], [False, 'NOT_RECORDED'])
        proposal = _step(self.t05, 'DEFAULT_ELIGIBLE proposal')
        self.assertEqual(proposal['status'], [1, 'DEFAULT_ELIGIBLE', False, True])
        self.assertEqual(_step(self.t05, 'still DRAWN')['status'], 'DRAWN')
        self.assertEqual(_step(self.t05, 'human default')['status'], [200, 'ACCEPTED', None])
        final = _step(self.t05, 'final phases')
        self.assertEqual(final['status'], {'sim-a': 'DEFAULTED', 'sim-b': 'CLOSED'})
        self.assertIs(final['facts']['funds_executed'], False)

    def test_t05_runs_on_a_disposable_book_not_the_workspace_fixtures(self):
        self.assertEqual(CapitalService().overlay_state()['margin']['source'], 'READ_ONLY_FIXTURE')


class T06Tests(JourneyBase):
    def test_agent_execute_is_refused_and_changes_nothing(self):
        for fragment in ('agent EXECUTE is refused', 'kind EXECUTE is refused'):
            self.assertEqual(_step(self.t06, fragment)['status'], [403, 'EXECUTE_AUTHORITY_DISABLED'])
        self.assertEqual(_step(self.t06, 'agent token cannot submit')['status'], [403, 'ROLE_FORBIDDEN'])
        self.assertEqual(_step(self.t06, 'changed nothing')['facts']['operation_count'], 4)

    def test_a_human_executes_the_proposal_with_proposal_id_on_the_receipt(self):
        step = _step(self.t06, 'human executes the proposal')
        self.assertEqual(step['status'], [200, 'ACCEPTED', 'sim-t06-proposal', 'organizer', False])
        memo = _step(self.t06, 'still a pending memo')
        self.assertEqual(memo['status'], [200, True, 'HUMAN_PENDING', False])
        self.assertLess(_step(self.t06, 'agent EXECUTE is refused')['n'], step['n'])

    def test_unknown_is_fenced_and_never_retried(self):
        self.assertEqual(_step(self.t06, 'never leaves the process')['status'], 'FENCED_NO_NETWORK_CALL')
        self.assertEqual(_step(self.t06, 'never leaves the process')['facts']['held'], ['h-repay-lost'])
        self.assertEqual(_step(self.t06, 'finds the lost response')['status'], [200, 'ACCEPTED', False])
        self.assertEqual(_step(self.t06, 'never-sent')['status'], [200, 'UNKNOWN', False])

    def test_kill_restart_gives_session_changed_restores_receipts_and_replays_nothing(self):
        self.assertEqual(_step(self.t06, 'killed with SIGKILL')['status'], -9)
        self.assertEqual(_step(self.t06, 'restarted')['status'], ['ACTIVE', True])
        self.assertEqual(_step(self.t06, 'stale token')['status'], [403, 'LOCAL_TOKEN_REQUIRED'])
        self.assertEqual(_step(self.t06, 'stale instance')['status'], [409, 'SESSION_CHANGED'])
        self.assertEqual(_step(self.t06, 'lookup under the old instance')['status'], [409, 'SESSION_CHANGED'])
        before = _step(self.t06, 'state recorded before the kill')['facts']
        after = _step(self.t06, 'survive the restart')['facts']
        self.assertEqual((after['state_digest'], after['operation_count']),
                         (before['state_digest'], before['operation_count']))
        restored = _step(self.t06, 'receipts are restored')
        self.assertEqual(restored['status'], [True, True])
        self.assertEqual(restored['facts']['proposal_id'], 'sim-t06-proposal')
        self.assertEqual(restored['facts']['operations'], ['h-repay-lost', 'h-repay-proposal', 'o-draw', 'o-offer'])
        self.assertEqual(_step(self.t06, 'no command at startup')['status'], [200, 0])
        self.assertEqual(_step(self.t06, 'old citation')['status'], [404, 'UNKNOWN_PROPOSAL'])
        self.assertEqual(_step(self.t06, 'reconciliation checks')['status'], [200, ['MATCHED']])
        self.assertEqual(_step(self.t06, 'final phase')['status'], {'sim-t06-a': 'CLOSED'})

    def test_the_server_process_is_gone_after_the_journey(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = journeys.ServerProcess(Path(tmp))
            port = server.start()
            self.assertGreater(port, 0)
            process = server.process
            self.assertEqual(server.kill(), -9)
            self.assertIsNone(server.process)
            self.assertIsNotNone(process.poll())
            self.assertIsNone(server.kill())

    def test_the_fence_blocks_a_write_without_a_network_call(self):
        client = journeys.Client(1)  # nothing listens on port 1; a call would raise OSError, not FenceError
        client.fence.hold('op-1')
        with self.assertRaises(journeys.FenceError):
            client.request('POST', '/api/commands', {'operation_id': 'op-2'}, 'token')
        with self.assertRaises(journeys.FenceError):
            client.send_lost('/api/commands', {'operation_id': 'op-2'}, 'token')
        self.assertEqual(client.log, [])
        client.fence.resolve('op-1')
        client.fence.guard()


class NamedJourneyTests(JourneyBase):
    def test_n1_never_invokes_default_and_pins_margin_order(self):
        original = journeys.PinnedFsmProducer.apply
        operations = []

        def tracked(producer, op, *args, **kwargs):
            operations.append(op)
            self.assertNotEqual(op, 'default')
            return original(producer, op, *args, **kwargs)

        with patch.object(journeys.PinnedFsmProducer, 'apply', tracked):
            result = journeys.run_n1()
        self.assertEqual(operations, ['offer', 'approve', 'bind_settlement', 'draw'])
        self.assertEqual(result, self.n1)
        events = _step(result, 'margin journal sequence')['facts']['events']
        self.assertEqual([event['record'] for event in events],
                         ['MARGIN_CALL', 'MARGIN_ACCELERATION', 'DEFAULT_ELIGIBLE_PROPOSAL'])
        self.assertEqual(_step(result, 'inclusive cure deadline')['status'], 'CALLED')
        self.assertEqual(_step(result, 'uncured expiry')['status'], 'ACCELERATED')
        self.assertEqual(_step(result, 'case remains DRAWN')['status'], ['DRAWN', 4])
        self.assertEqual(_step(result, 'human-facing')['status'],
                         [1, 'DEFAULT_ELIGIBLE', 'HUMAN_OPERATOR_DECISION', False, True])

    def test_n2_citation_and_offline_evidence_chain(self):
        self.assertEqual(_step(self.n2, 'organizer command cites')['status'],
                         [200, 'ACCEPTED', 'organizer', 'sim-n2-proposal', False, False])
        self.assertEqual(_step(self.n2, 'memo stays')['status'], [200, True, 'HUMAN_PENDING', False])
        self.assertEqual(_step(self.n2, 'simulated repayment')['status'], 10_000)
        self.assertEqual(_step(self.n2, 'correlates receipt')['status'], [200, True, True])
        self.assertEqual(_step(self.n2, 'offline manifest')['status'], [0, True, 'MATCHED', 'NOT_BOUND'])
        self.assertEqual(_step(self.n2, 'offline workspace')['status'], [0, True, 'MATCHED', False, False])
        self.assertEqual(_step(self.n2, 'tampered citation')['status'], [True, False])

    def test_new_pins_missing_and_tampered_fail_without_writing(self):
        for result in (self.n1, self.n2):
            with tempfile.TemporaryDirectory() as tmp:
                path = journeys.golden_path(tmp, result['journey'])
                with self.assertRaises(journeys.JourneyError):
                    journeys.check_or_update(result, path, False)
                self.assertFalse(path.exists())
                journeys.check_or_update(result, path, True)
                data = json.loads(path.read_text())
                data['steps'][0]['status'] = 'TAMPERED'
                path.write_text(json.dumps(data))
                before = path.read_bytes()
                self.assertTrue(journeys.check_or_update(result, path, False))
                self.assertEqual(path.read_bytes(), before)

    def test_check_and_update_are_mutually_exclusive(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            journeys.main(['--check', '--update-golden'])
        self.assertEqual(raised.exception.code, 2)


class GoldenTests(JourneyBase):
    def test_check_update_and_tamper_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = _run(['--journey', 'T05-sim', '--golden-dir', tmp])
            self.assertEqual(code, 1)
            self.assertIn('--update-golden', err)
            self.assertNotIn('sim journeys ok', out)
            self.assertEqual(list(Path(tmp).iterdir()), [])
            code, out, err = _run(['--journey', 'T05-sim', '--golden-dir', tmp, '--update-golden'])
            self.assertEqual(code, 0, err)
            self.assertIn('sim journeys updated SIMULATED T05-sim steps=', out)
            path = Path(tmp) / 'journey_t05_sim.json'
            self.assertEqual(path.read_text(encoding='utf-8'), (GOLDEN / 'journey_t05_sim.json').read_text(encoding='utf-8'))
            code, out, err = _run(['--journey', 'T05-sim', '--golden-dir', tmp])
            self.assertEqual(code, 0, err)
            self.assertIn('sim journeys ok SIMULATED T05-sim steps=', out)
            tampered = path.read_text(encoding='utf-8').replace('"CALLED"', '"CURED"', 1)
            self.assertNotEqual(tampered, path.read_text(encoding='utf-8'))
            path.write_text(tampered, encoding='utf-8')
            code, out, err = _run(['--journey', 'T05-sim', '--golden-dir', tmp])
            self.assertEqual(code, 1)
            self.assertIn('golden drift:', err)
            self.assertIn('--update-golden', err)
            self.assertNotIn('sim journeys ok', out)
            self.assertEqual(path.read_text(encoding='utf-8'), tampered)

    def test_digest_tamper_in_a_golden_fails(self):
        for journey_id, name in (('T03-sim', 'journey_t03_sim.json'), ('T06-sim', 'journey_t06_sim.json')):
            with self.subTest(journey_id), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / name
                data = json.loads((GOLDEN / name).read_text(encoding='utf-8'))
                data['digest'] = '0' * 64
                path.write_text(journeys.render(data), encoding='utf-8')
                code, _out, err = _run(['--journey', journey_id, '--golden-dir', tmp])
                self.assertEqual(code, 1)
                self.assertIn(f'{journey_id}.digest', err)

    def test_a_golden_with_a_volatile_key_is_rejected(self):
        for journey_id in ('T04-sim', 'T05-sim'):
            with self.subTest(journey_id), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / journeys.GOLDEN_FILES[journey_id]
                data = json.loads((GOLDEN / journeys.GOLDEN_FILES[journey_id]).read_text(encoding='utf-8'))
                data['instance_id'] = 'x'
                path.write_text(journeys.render(data), encoding='utf-8')
                code, _out, err = _run(['--journey', journey_id, '--golden-dir', tmp])
                self.assertEqual(code, 1)
                self.assertIn('volatile key', err)


def _stage(script, kind='integrated-journeys'):
    return {'id': 'integrated-journeys', 'kind': kind, 'timeout': 30, 'commands': [[sys.executable, '-c', script]]}


def _summary_script(mutate=None, exit_code=0):
    summary = {
        'label': 'SIMULATED', 'seed': 'x', 'funds_executed': False, 'integrated': False,
        'journeys': [
            {'id': 'T03-sim', 'label': 'SIMULATED', 'steps': 3, 'digest': 'a' * 64,
             'funds_executed': False, 'integrated': False},
            {'id': 'T04-sim', 'label': 'SIMULATED', 'steps': 3, 'digest': 'b' * 64,
             'funds_executed': False, 'integrated': False},
            {'id': 'T05-sim', 'label': 'SIMULATED', 'steps': 3, 'digest': 'c' * 64,
             'funds_executed': False, 'integrated': False},
            {'id': 'T06-sim', 'label': 'SIMULATED', 'steps': 4, 'digest': 'd' * 64,
             'funds_executed': False, 'integrated': False},
        ],
    }
    summary['journeys'].extend(
        {'id': name, 'label': 'SIMULATED', 'steps': 16, 'digest': 'e' * 64,
         'funds_executed': False, 'integrated': False} for name in ('N1-sim', 'N2-sim'))
    if mutate:
        mutate(summary)
    return ('import sys\nprint("SIM_JOURNEYS " + ' + repr(json.dumps(summary)) + ')\n'
            'print("sim journeys ok SIMULATED T03-sim steps=3 T04-sim steps=3 '
            'T05-sim steps=3 T06-sim steps=4")\n'
            f'sys.exit({exit_code})')


def _ok_stub(stage_id):
    return {'id': stage_id, 'timeout': 20,
            'commands': [[sys.executable, '-c', 'print("Ran 2 tests in 0.001s\\n\\nOK")']]}


class EvidenceTests(unittest.TestCase):
    def evidence_for(self, stage):
        plan = [_ok_stub(sid) for sid in acceptance.REQUIRED_STAGES if sid != 'integrated-journeys'] + [stage]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'acceptance-evidence.json'
            code = acceptance.execute_plan(plan, root=ROOT, evidence_path=path, required=acceptance.REQUIRED_STAGES)
            return code, json.loads(path.read_text(encoding='utf-8'))

    def test_real_stage_lists_all_journeys_with_steps_and_label(self):
        doc_before = ACCEPTANCE_DOC.read_bytes()
        stage = next(item for item in acceptance.build_plan(ROOT) if item['id'] == 'integrated-journeys')
        code, evidence = self.evidence_for(stage)
        self.assertEqual(code, 0, evidence['stages'][-1])
        body = next(item for item in evidence['stages'] if item['id'] == 'integrated-journeys')
        self.assertEqual(body['status'], 'passed')
        self.assertEqual(body['test_count'], {'ran': 6, 'passed': 6, 'failed': 0})
        items = {item['id']: item for item in body['journeys']['items']}
        self.assertEqual(sorted(items), sorted(journeys.JOURNEY_IDS))
        for journey_id, item in items.items():
            golden = json.loads((GOLDEN / journeys.GOLDEN_FILES[journey_id]).read_text(encoding='utf-8'))
            self.assertEqual(item['label'], 'SIMULATED')
            self.assertEqual((item['steps'], item['digest']), (golden['step_count'], golden['digest']))
        self.assertEqual(body['journeys']['label'], 'SIMULATED')
        self.assertIs(body['journeys']['integrated'], False)
        self.assertIs(body['journeys']['qualification_claimed'], False)
        self.assertIs(evidence['funds_executed'], False)
        self.assertIs(evidence['integrated'], False)
        self.assertIs(evidence['qualification']['claimed'], False)
        text = json.dumps(evidence)
        for needle in ('SEMANTIC_CONFORMANCE', 'qualified', 'T01-T06 pass'):
            self.assertNotIn(needle, text.replace('no T01-T06 qualification is claimed', ''), needle)
        self.assertEqual(ACCEPTANCE_DOC.read_bytes(), doc_before)

    def test_human_checkboxes_stay_unchecked(self):
        text = ACCEPTANCE_DOC.read_text(encoding='utf-8')
        self.assertNotIn('- [x]', text.lower())
        self.assertGreaterEqual(text.count('- [ ]'), 5)
        self.assertIn('`integrated-journeys`', text)

    def test_well_formed_summary_passes(self):
        code, evidence = self.evidence_for(_stage(_summary_script()))
        self.assertEqual(code, 0)
        self.assertEqual(evidence['stages'][-1]['journeys']['items'][0]['steps'], 3)

    def test_malformed_or_overclaiming_summaries_fail_the_stage(self):
        cases = {
            'integrated true': lambda s: s['journeys'][0].update(integrated=True),
            'funds executed true': lambda s: s['journeys'][1].update(funds_executed=True),
            'top level integrated': lambda s: s.update(integrated=True),
            'label not simulated': lambda s: s['journeys'][0].update(label='REAL'),
            'missing journey': lambda s: s['journeys'].pop(),
            'extra journey': lambda s: s['journeys'].append(dict(s['journeys'][0], id='T07-sim')),
            'zero steps': lambda s: s['journeys'][0].update(steps=0),
            'bool steps': lambda s: s['journeys'][0].update(steps=True),
            'short digest': lambda s: s['journeys'][0].update(digest='abc'),
            'nonhex digest': lambda s: s['journeys'][0].update(digest='z' * 64),
            'duplicate journey': lambda s: s['journeys'].__setitem__(-1, dict(s['journeys'][0])),
            'malformed journeys': lambda s: s.update(journeys=42),
            'malformed item': lambda s: s['journeys'].__setitem__(0, None),
            'missing id': lambda s: s['journeys'][0].pop('id'),
        }
        for name, mutate in cases.items():
            with self.subTest(name):
                code, evidence = self.evidence_for(_stage(_summary_script(mutate)))
                self.assertEqual(code, 1)
                self.assertEqual(evidence['stages'][-1]['status'], 'failed')
                self.assertFalse(evidence['ok'])

    def test_nonzero_exit_or_no_summary_fails_the_stage(self):
        code, evidence = self.evidence_for(_stage(_summary_script(exit_code=1)))
        self.assertEqual((code, evidence['stages'][-1]['status']), (1, 'failed'))
        code, evidence = self.evidence_for(_stage(
            'print("sim journeys ok SIMULATED T03-sim steps=3 T04-sim steps=3 '
            'T05-sim steps=3 T06-sim steps=4")'))
        self.assertEqual((code, evidence['stages'][-1]['status']), (1, 'failed'))
        self.assertEqual(evidence['stages'][-1]['journeys']['items'], [])

    def test_missing_stage_and_injected_failure_fail_the_ladder(self):
        plan = [_ok_stub(sid) for sid in acceptance.REQUIRED_STAGES if sid != 'integrated-journeys']
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'acceptance-evidence.json'
            self.assertEqual(acceptance.execute_plan(
                plan, root=ROOT, evidence_path=path, required=acceptance.REQUIRED_STAGES), 1)
            data = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(next(s for s in data['stages'] if s['id'] == 'integrated-journeys')['status'], 'unrun')
            injected = acceptance.inject_failure(
                [_ok_stub(sid) for sid in acceptance.REQUIRED_STAGES], 'integrated-journeys')
            self.assertEqual(acceptance.execute_plan(
                injected, root=ROOT, evidence_path=path, required=acceptance.REQUIRED_STAGES), 1)
            data = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(next(s for s in data['stages'] if s['id'] == 'integrated-journeys')['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
