"""SIMULATED V2 allowance: independent integer vectors and recorded lifecycle replay."""
import copy
import unittest
from unittest.mock import patch

from capital import coa, margin, overlay, recon
from capital.projection import ProjectionError
from capital.service import CapitalService
from capital.store import canonical_bytes
from test_coa_payment_writeoff import combined, selected
from test_margin import drawn_then_refunded
from test_overlay import draw_book, run, seed, tick
from test_recovery import book, cmd, recover, seed as recovery_seed


def candidate(s):
    return s.projection('coa-candidate')


def allowance_entries(body):
    return selected(body, 'ALLOWANCE')


def changes(body):
    return [(e['dimensions']['advance_id'], e['dimensions']['sim_day'],
             e['evidence']['operation_id'],
             sum((1 if line['side'] == 'debit' else -1) * line['amount']
                 for line in e['lines'] if line['account'] == '5100')) for e in allowance_entries(body)]


def check(s):
    return s.reconciliation(None, 'coa-candidate')['checks'][-1]


class AllowanceTests(unittest.TestCase):
    def assert_conserved(self, body):
        carried = {}
        for entry in allowance_entries(body):
            ref = entry['dimensions']['advance_id']
            for line in entry['lines']:
                self.assertIn(line['account'], ('1190', '5100'))
                self.assertTrue(line['leg'].startswith(entry['txn_id']))
                if line['account'] == '1190':
                    carried[ref] = carried.get(ref, 0) + (1 if line['side'] == 'credit' else -1) * line['amount']
                    self.assertGreaterEqual(carried[ref], 0)
            self.assertEqual(sum(l['amount'] for l in entry['lines'] if l['side'] == 'debit'),
                             sum(l['amount'] for l in entry['lines'] if l['side'] == 'credit'))
        for row in body['allowance']['rows']:
            self.assertEqual(carried.get(row['advance_id'], 0), row['allowance_krw'])
            self.assertLessEqual(row['allowance_krw'], row['effective_principal_krw'])
        self.assertTrue(all(g['debit'] == g['credit'] for g in body['balance_groups']))
        self.assertTrue(all(c['matched'] for c in body['conservation']))
        self.assertFalse(any(l['account'] in ('3100', '3200') for e in body['entries'] for l in e['lines']))

    def test_empty_overlay_is_valid_with_recorded_draw_receipts(self):
        s = CapitalService()
        draw_book(s)
        self.assertEqual(s.overlay_entries, [])
        frozen = s._frozen()
        body = candidate(s)
        self.assertEqual(changes(body), [('sim-a', 0, 'a-draw', 1350)])
        self.assertEqual(body['reserve_pool']['portfolio_floor_krw'], 900)
        self.assertEqual(check(s)['allowance']['outcome'], 'MATCH')
        self.assertEqual(s._frozen(), frozen)
        self.assert_conserved(body)

    def test_complete_population_keeps_unfunded_and_closed_zero_rows(self):
        s = CapitalService()
        draw_book(s)
        run(s, 'offer', 'sim-idle', 'idle', fixture_id='sim-pending', amount=100)
        run(s, 'repay', 'sim-a', 'pay', amount=90000, sequence=1)
        run(s, 'close', 'sim-a', 'close')
        body = candidate(s)
        self.assertEqual(body['allowance']['population']['advance_ids'], ['sim-a', 'sim-idle'])
        self.assertEqual([r['allowance_krw'] for r in body['allowance']['rows']], [0, 0])
        self.assertEqual([r[-1] for r in changes(body)], [1350, -1350])
        self.assert_conserved(body)

    def test_t1_t2_amounts_and_rejected_rebinding_preserve_draw_tier(self):
        s = CapitalService()
        draw_book(s)
        run(s, 'offer', 'sim-b', 'b-offer', fixture_id='sim-pending', amount=50000)
        run(s, 'approve', 'sim-b', 'b-approve')
        self.assertEqual(run(s, 'draw', 'sim-b', 'b-draw')['outcome'], 'ACCEPTED')
        tick(s, 'ten', 0, 10)
        rebound = run(s, 'bind_settlement', 'sim-b', 'late-bind')
        self.assertEqual((rebound['outcome'], rebound['error']), ('REJECTED', 'ILLEGAL_TRANSITION'))
        body = candidate(s)
        self.assertEqual([(r['tier'], r['allowance_krw']) for r in body['allowance']['rows']],
                         [('T1', 1350), ('T2', 2500)])
        self.assert_conserved(body)

    def test_same_day_events_keep_each_delta_in_economic_order(self):
        s = CapitalService()
        draw_book(s)
        run(s, 'repay', 'sim-a', 'p1', amount=30000, sequence=1)
        run(s, 'repay', 'sim-a', 'p2', amount=20000, sequence=2)
        body = candidate(s)
        self.assertEqual(changes(body), [('sim-a', 0, 'a-draw', 1350),
                                        ('sim-a', 0, 'p1', -450), ('sim-a', 0, 'p2', -300)])
        self.assertEqual([e['txn_id'] for e in body['entries'] if e['source'] != 'EVIDENCE'],
                         ['a-draw', allowance_entries(body)[0]['txn_id'], 'p1',
                          allowance_entries(body)[1]['txn_id'], 'p2', allowance_entries(body)[2]['txn_id']])
        self.assert_conserved(body)

    def test_crossed_stage_replays_identically_for_split_and_jump_ticks(self):
        books = []
        for split in (False, True):
            s = CapitalService()
            draw_book(s)
            if split:
                tick(s, 'sixty', 0, 60)
                tick(s, 'sixtyone', 60, 61)
                tick(s, 'hundred', 61, 100)
            else:
                tick(s, 'hundred', 0, 100)
            books.append(candidate(s))
        self.assertEqual(changes(books[0]), changes(books[1]))
        self.assertEqual(changes(books[0])[-1], ('sim-a', 61, 'STAGE_TRANSITION:sim-a:61', 21150))
        self.assertEqual(books[0]['allowance']['rows'][0]['bucket'], 'PAST_DUE_ANY_TIER')
        for body in books:
            self.assert_conserved(body)

    def test_opening_day_transition_precedes_same_day_repayment(self):
        s = CapitalService()
        draw_book(s)
        tick(s, 'sixtyone', 0, 61)
        run(s, 'repay', 'sim-a', 'p', amount=10000, sequence=1)
        self.assertEqual([r[-1] for r in changes(candidate(s))], [1350, 21150, -2500])

    def test_default_eligibility_does_not_post_default_until_command_day(self):
        s = CapitalService()
        draw_book(s)
        tick(s, 'ninety', 0, 90)
        self.assertEqual(candidate(s)['allowance']['rows'][0]['allowance_krw'], 22500)
        run(s, 'default', 'sim-a', 'default90')
        body = candidate(s)
        self.assertEqual(changes(body)[-1], ('sim-a', 90, 'default90', 67500))
        self.assert_conserved(body)

    def test_margin_acceleration_uses_recorded_day_and_preserves_draw_tier(self):
        _, s = drawn_then_refunded()
        tick(s, 'call', 0, 3)
        tick(s, 'accel', 3, 9)
        body = candidate(s)
        self.assertEqual(changes(body)[0][-1], 701)  # floor(46,751 * 150 / 10,000)
        self.assertEqual(changes(body)[-1][1], 9)
        self.assertEqual(body['allowance']['rows'][0]['allowance_krw'], 11687)
        self.assertEqual(body['allowance']['rows'][0]['tier'], 'T1')
        # The legacy risk path cannot rate the post-draw refund and reports incomplete evidence.
        self.assertEqual(check(s)['allowance']['outcome'], 'NOT_BOUND')
        self.assert_conserved(body)

    def test_operator_acceleration_is_also_a_measurement_event(self):
        _, s = book()
        s.overlay_command(cmd(s, 'record_acceleration', 'acc', event='BENEFICIARY_INSOLVENCY_NOTICE'))
        self.assertEqual(changes(candidate(s))[-1], ('sim-a', 10, 'acc', 21150))

    def test_recovery_deducts_allocated_principal_once_and_writeoff_releases_once(self):
        source, s = book()
        run(s, 'default', 'sim-a', 'default')
        recovery_seed.distribute(source, 'sim-committed')
        tick(s, 'twenty', 10, 20)
        s.overlay_command(recover(s, 10000))
        body = candidate(s)
        # 172 contract + 246 default interest; only 9,582 principal reduces allowance.
        self.assertEqual(body['allowance']['rows'][0]['effective_principal_krw'], 80418)
        self.assertEqual(changes(body)[-1][-1], -9582)
        tick(s, 'late', 20, 110)
        s.overlay_command(cmd(s, 'post_writeoff', 'wo', setoff_declined_reason='SIMULATED_DECLINED'))
        before_late = candidate(s)
        s.overlay_command(recover(s, 100, key='late-recovery'))
        body = candidate(s)
        self.assertEqual(changes(body), changes(before_late))
        wo = next(i for i,e in enumerate(body['entries']) if e['source'] == 'OVERLAY_WRITEOFF')
        release = body['entries'][wo - 1]
        self.assertEqual(release['source'], 'ALLOWANCE')
        self.assertEqual(release['evidence']['source_reserve_step_version'], 'UNBUILT_V1')
        self.assertEqual(release['evidence']['effective_sim_day'], 100)
        self.assertEqual(release['dimensions']['sim_day'], 110)
        self.assertEqual(release['lines'][0]['amount'], 80418)
        self.assertEqual(body['allowance']['rows'][0]['allowance_krw'], 0)
        self.assert_conserved(body)

    def test_seed_demo_is_exactly_30750_and_read_only_repeatable(self):
        s = seed.build_service()
        before = s._frozen()
        body = candidate(s)
        self.assertEqual(body['allowance']['allowance_component_krw'], 30750)
        self.assertEqual(check(s)['allowance']['requirement_krw'], 30750)
        self.assertEqual(check(s)['status'], 'MATCHED')
        self.assertEqual(canonical_bytes(candidate(s)), canonical_bytes(body))
        self.assertEqual(before, s._frozen())
        self.assert_conserved(body)

    def test_floor_is_portfolio_rounded_once_and_not_posted_to_1190(self):
        s = CapitalService()
        draw_book(s, amount=66)
        draw_book(s, advance='sim-b', amount=66, prefix='b')
        body = candidate(s)
        self.assertEqual(allowance_entries(body), [])
        self.assertEqual(body['reserve_pool']['portfolio_floor_krw'], 1)
        self.assertEqual(body['reserve_pool']['binding_component'], 'PORTFOLIO_FLOOR')
        self.assertEqual(check(s)['allowance']['delta_krw'], 1)
        self.assertEqual(check(s)['allowance']['outcome'], 'MISMATCH')
        self.assert_conserved(body)

    def test_deduplicated_overlay_transport_does_not_duplicate_postings(self):
        s = combined()
        context = s._allowance_context()
        entries = s.overlay_entries
        duplicate = [copy.deepcopy(e) for e in entries for _ in range(2)]
        # Fold ignores identical IDs, so the same cut yields the same candidate.
        evidence = [s.fixtures.view(key) for key in sorted(s.fixtures.projection_ids)]
        body = coa.CoaCandidateProjection().project(s.machine.export_journal(), evidence,
                                                    overlay_entries=duplicate, allowance_context=context)
        self.assertEqual(body['entries'], candidate(s)['entries'])


class AllowanceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.s = CapitalService()
        draw_book(self.s)
        self.context = self.s._allowance_context()

    def project(self, context):
        return coa.CoaCandidateProjection().project(self.s.machine.export_journal(), [],
                    overlay_entries=self.s.overlay_entries, allowance_context=context)

    def test_missing_context_does_not_guess_zero(self):
        body = self.project(None)
        self.assertEqual(body['allowance']['status'], 'NOT_BOUND')
        self.assertIsNone(body['allowance']['allowance_component_krw'])
        self.assertEqual(recon.allowance_check(body, None)['allowance']['outcome'], 'NOT_BOUND')

    def test_missing_terms_mapping_or_tier_is_not_bound(self):
        for field in ('reserve_terms', 'terms_version', 'advances'):
            context = copy.deepcopy(self.context)
            context.pop(field)
            self.assertEqual(self.project(context)['allowance']['status'], 'NOT_BOUND')
        context = copy.deepcopy(self.context)
        context['advances'][0]['ledger_terms']['tier'] = 'UNKNOWN'
        self.assertEqual(self.project(context)['allowance']['status'], 'NOT_BOUND')

    def test_missing_floor_never_falls_back_to_allowance_or_100_bps(self):
        context = copy.deepcopy(self.context)
        context['reserve_terms']['pool_target'] = 'unverified formula'
        body = self.project(context)
        self.assertEqual(body['allowance']['status'], 'BOUND')
        self.assertIsNone(body['reserve_pool']['pool_target_krw'])
        self.assertIsNone(body['reserve_pool']['floor_bps'])
        self.assertEqual(recon.allowance_check(body, context)['allowance']['outcome'], 'NOT_BOUND')

    def test_missing_policy_fails_closed(self):
        with patch('capital.coa.read_note', return_value={'block': None}):
            self.assertEqual(self.project(self.context)['allowance']['status'], 'NOT_BOUND')

    def test_cut_population_and_policy_mismatch_never_pass_on_equal_amounts(self):
        body = self.project(self.context)
        for key in ('source_cut', 'population', 'policy_context'):
            context = copy.deepcopy(self.context)
            context['risk'][key] = {}
            detail = recon.allowance_check(body, context)['allowance']
            self.assertEqual(detail['outcome'], 'CUT_MISMATCH')
            self.assertIsNone(detail['delta_krw'])
        for key in ('source_cut', 'population', 'policy_context'):
            context = copy.deepcopy(self.context)
            context[key] = {}
            self.assertEqual(self.project(context)['allowance']['status'], 'NOT_BOUND')

    def test_planted_posting_or_aggregate_drift_mismatches(self):
        good = self.project(self.context)
        for kind in ('posting', 'aggregate', 'risk', 'expense'):
            body, context = copy.deepcopy(good), copy.deepcopy(self.context)
            if kind == 'posting':
                allowance_entries(body)[0]['lines'][0]['amount'] += 1
                allowance_entries(body)[0]['lines'][1]['amount'] += 1
            elif kind == 'expense':
                allowance_entries(body)[0]['lines'][0]['amount'] += 1
            elif kind == 'aggregate':
                next(r for r in body['accounts'] if r['code'] == '1190')['balance'] += 1
            else:
                context['risk']['requirement_krw'] += 1
            self.assertEqual(recon.allowance_check(body, context)['allowance']['outcome'], 'MISMATCH')

    def test_negative_principal_and_contradictory_terminal_evidence_fail(self):
        for amount in (-1, 1):
            context = copy.deepcopy(self.context)
            context['advances'][0]['case']['outstanding_exposure'] = amount
            with self.assertRaises(ProjectionError):
                self.project(context)

    def test_missing_maturity_and_risk_cut_are_not_bound(self):
        context = copy.deepcopy(self.context)
        context['advances'][0]['ledger_terms'].pop('maturity_day')
        self.assertEqual(self.project(context)['allowance']['status'], 'NOT_BOUND')
        context = copy.deepcopy(self.context)
        context['risk'].pop('source_cut')
        self.assertEqual(recon.allowance_check(self.project(context), context)['allowance']['outcome'], 'NOT_BOUND')

    def test_terminal_source_cannot_hide_outstanding_principal(self):
        context = copy.deepcopy(self.context)
        context['advances'][0]['case']['phase'] = 'CLOSED'
        with self.assertRaises(ProjectionError):
            self.project(context)
