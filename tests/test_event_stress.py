"""Local SIMULATED absolute event shocks; no financial execution or source writes."""
import copy
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from capital import event_stress as stress, margin, overlay, risk, risk_whatif
from capital.portfolio_snapshot import FrozenInputs
from capital.service import CapitalService
from capital.store import FILE_NAME, canonical_bytes
from tests.test_overlay import draw_book, tick

ROOT = Path(__file__).resolve().parents[1]


def ref(name='sim-committed'):
    return {'claim_id': name, 'trade_id': 'sim-trade-' + name, 'currency': 'KRW'}


def spec(names=('sim-committed',), amount=100):
    return {'format': 'CAPITAL_EVENT_STRESS_V1',
            'events': [{'event_id': 'E1', 'claim_refs': [ref(n) for n in names]}],
            'scenarios': [{'scenario_id': 'S1', 'event_id': 'E1', 'kind': 'ADDITIONAL_OPEN_REFUND_KRW',
                           'additional_open_refund_krw': amount}]}


def capture(service):
    with service.lock:
        return FrozenInputs.capture(service.producer.snapshot_inputs(), service.receipts,
            service.case_fixtures, service.overlay_entries, service.terms, service.overlay_bounds)


def rows(report):
    return {r['claim_ref']['claim_id']: r for r in report['claims']}


class EventStressTests(unittest.TestCase):
    def setUp(self):
        self.service = CapitalService()
        self.addCleanup(self.service.observability.close)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def evaluate(self, request=None, frozen=None, status='COMPLETE'):
        before = self.service._frozen()
        fixtures = copy.deepcopy(self.service.fixtures.rows)
        frozen = frozen or capture(self.service)
        raw = frozen.raw
        result = stress.evaluate_detached(frozen, canonical_bytes(request or spec()))
        self.assertEqual(result['status'], status, result.get('diagnostics'))
        self.assertEqual(self.service._frozen(), before)
        self.assertEqual(self.service.fixtures.rows, fixtures)
        self.assertEqual(frozen.raw, raw)
        return result

    def save(self):
        self.service._persist()
        path = self.root / FILE_NAME
        path.write_bytes(canonical_bytes(self.service.storage.load()))
        path.chmod(0o600)
        return path

    def rejected(self, result, code):
        self.assertEqual(result['status'], 'REJECTED', result)
        self.assertEqual(result['diagnostics'][0]['code'], code)
        for key in ('baseline', 'scenarios', 'scenario_digest', 'delta', 'unchanged_risk_folds'):
            self.assertNotIn(key, result)

    def test_single_and_outside_unchanged_margin_equivalence(self):
        draw_book(self.service, amount=10001)
        report = self.evaluate()
        after = report['scenarios'][0]['stressed']
        left, right = rows(report['baseline']), rows(after)
        for key in left:
            if key != 'sim-committed':
                self.assertEqual(left[key], right[key])
        claim = right['sim-committed']
        self.assertEqual(claim['eligible_face_krw'], 95000 - 100)
        self.assertEqual(claim['witness']['applications'], 1)
        subject = stress.prepare(capture(self.service), stress.load_policy())['drawn'][0]
        projection = {**subject['claim'], 'refund_face': 100}
        measurement = margin.measure({**subject, 'claim': projection})
        row = after['advances'][0]
        self.assertEqual(row['borrowing_base_krw'], measurement['base_krw'])
        self.assertEqual(row['headroom_krw'], measurement['base_krw'] - 10001)
        tier = self.service.terms._tier(subject['case'], subject['claim'], subject['gate'])
        existing = self.service.terms._borrowing_base(subject['case'], projection, tier)
        self.assertEqual(existing['base_krw'], row['borrowing_base_krw'])
        self.assertEqual(report['scenarios'][0]['delta']['portfolio']['eligible_face_krw'], -100)

    def test_pinned_corpus_inputs_recompute_expected_reports(self):
        corpus = json.loads((ROOT / 'tests/vectors/event_stress.json').read_bytes())
        frozen = FrozenInputs(canonical_bytes(corpus['inputs']))
        for case in corpus['cases']:
            self.assertEqual(stress.evaluate_detached(frozen, canonical_bytes(case['request'])), case['expected'])
        checked = subprocess.run([sys.executable, 'scripts/event_stress_vectors.py', '--check'],
                                 cwd=ROOT, capture_output=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_shared_decision_example_800_once_exposure_500(self):
        draw_book(self.service, 'sim-A1', amount=300, prefix='a1')
        draw_book(self.service, 'sim-A2', amount=200, prefix='a2')
        prepared = stress.prepare(capture(self.service), stress.load_policy())
        identity = stress._identity(ref())
        claim = prepared['claims'][identity]
        claim.update(gross=1000, refund_face=100, refund_outstanding=100,
                     confirmed_cash=0, non_cash_accounted=0, undistributed_cash=0, receivable_open=1000)
        claim['obligations'] = [dict(payee='organizer',face=1000,distributed=0,
                                    cancelled_unpaid=0,recovery_due=0,outstanding=1000)]
        measured = stress.measure_portfolio(prepared, [identity], 100)
        self.assertEqual(measured['event']['eligible_face_krw'], 800)
        self.assertEqual(measured['event']['open_refund_krw'], 200)
        self.assertEqual(measured['event']['exposure_krw'], 500)
        self.assertIsNone(measured['event']['headroom_krw'])

    def test_payee_conflict_and_holder_semantics_are_null(self):
        draw_book(self.service, 'sim-A1', amount=300, prefix='a1')
        draw_book(self.service, 'sim-A2', amount=200, prefix='a2')
        prepared = stress.prepare(capture(self.service), stress.load_policy())
        prepared['drawn'][1]['margin']['payees'] = ['platform']
        measured = stress.measure_portfolio(prepared)
        self.assertIsNone(rows(measured)['sim-committed']['eligible_face_krw'])
        self.assertIsNone(measured['portfolio']['borrowing_base_krw'])
        prepared = stress.prepare(capture(self.service), stress.load_policy())
        prepared['claims'][stress._identity(ref())]['holder_role'] = 'unresolved'
        measured = stress.measure_portfolio(prepared)
        self.assertIn('REFUND_MAPPING_NOT_BOUND', rows(measured)['sim-committed']['reasons'])

    def test_real_captured_slice_entries_are_unsupported(self):
        from scripts.seed_overlay_slices import register
        register(self.service, 'sim-slice', 1000)
        self.save()
        report = stress.report_workspace(self.root, canonical_bytes(spec()))
        self.assertEqual(report['status'], 'PARTIAL', report['diagnostics'])
        self.assertIn('REFUND_MAPPING_NOT_BOUND', rows(report['baseline'])['demo-delta-small']['reasons'])

    def test_undrawn_relationship_retained_without_inventing_exposure(self):
        from tests.test_overlay import run
        draw_book(self.service, amount=300)
        run(self.service, 'offer', 'sim-reserved', 'reservation', fixture_id='sim-committed', amount=200)
        run(self.service, 'approve', 'sim-reserved', 'reservation-approved')
        report = self.evaluate()
        self.assertEqual(report['baseline']['portfolio']['exposure_krw'], 300)
        self.assertIsNotNone(report['baseline']['portfolio']['borrowing_base_krw'])
        self.assertEqual(rows(report['baseline'])['sim-committed']['linked_advance_ids'], ['sim-a','sim-reserved'])

    def test_missing_mapping_note_is_unavailable(self):
        original = stress.resources.read_note
        def missing(path):
            note = original(path)
            if str(path).endswith('CAPITAL_EVENT_STRESS_BINDING.md'):
                note['block'] = None
            return note
        with patch.object(stress.resources, 'read_note', side_effect=missing):
            report = self.evaluate(status='UNAVAILABLE')
        self.assertEqual(report['diagnostics'][0]['code'], 'EVENT_MEASUREMENT_NOT_BOUND')

    def test_shared_claim_once_no_allocated_base(self):
        draw_book(self.service, 'sim-A1', amount=300, prefix='a1')
        draw_book(self.service, 'sim-A2', amount=200, prefix='a2')
        report = self.evaluate(status='PARTIAL')
        after = report['scenarios'][0]['stressed']
        claim = rows(after)['sim-committed']
        self.assertEqual(claim['witness']['hypothetical_open_refund_krw'], 100)
        self.assertEqual(claim['eligible_face_krw'], 94900)
        self.assertEqual(after['portfolio']['exposure_krw'], 500)
        self.assertEqual(report['scenarios'][0]['delta']['portfolio']['open_refund_krw'], 100)
        for row in after['advances']:
            self.assertIn('UNSUPPORTED_SHARED_ALLOCATION', row['reasons'])
            self.assertIsNone(row['borrowing_base_krw'])
            self.assertIsNone(row['headroom_krw'])
            self.assertEqual(row['claim_context'], 'NON_ADDITIVE')
        self.assertIsNone(after['portfolio']['headroom_krw'])
        self.assertIsNone(report['scenarios'][0]['delta']['portfolio']['borrowing_base_krw'])

    def test_closed_and_current_draw_cannot_duplicate_claim_base(self):
        from tests.test_overlay import run
        draw_book(self.service, 'sim-old', amount=300, prefix='old')
        run(self.service, 'repay', 'sim-old', 'old-repay', amount=300, sequence=1)
        run(self.service, 'close', 'sim-old', 'old-close')
        draw_book(self.service, 'sim-new', amount=200, prefix='new')
        report = self.evaluate(status='PARTIAL')
        self.assertEqual(report['baseline']['portfolio']['exposure_krw'], 200)
        self.assertIsNone(report['baseline']['portfolio']['borrowing_base_krw'])
        self.assertEqual([r['exposure_krw'] for r in report['baseline']['advances']], [200, 0])

    def test_decision_examples_two_claims_and_overlap(self):
        # Build internally consistent disposable source claims for the decision's
        # illustrative numbers; no settlement history or real event is asserted.
        frozen = capture(self.service).detached()
        names = ('sim-committed', 'sim-pending', 'sim-refund')
        amounts = ((1000, 100), (2000, 200), (500, 50))
        for name, (gross, refund) in zip(names, amounts):
            c = frozen['producer']['fixtures']['rows'][name]['claim']
            c.update(gross=gross, confirmed_cash=0, non_cash_accounted=0, receivable_open=gross,
                     undistributed_cash=0, refund_face=refund, refund_outstanding=refund)
            c['obligations'] = [dict(payee='organizer', face=gross, distributed=0,
                                    cancelled_unpaid=0, recovery_due=0, outstanding=gross)]
        # Empty F04 journal: capture reconciliation never invents advances.
        request = spec(names[:2])
        request['events'].append({'event_id': 'E2', 'claim_refs': [ref(names[0]), ref(names[2])]})
        request['scenarios'].append({**request['scenarios'][0], 'scenario_id': 'S2', 'event_id': 'E2'})
        report = self.evaluate(request, FrozenInputs(canonical_bytes(frozen)))
        first, second = report['scenarios']
        self.assertEqual(first['baseline_event']['eligible_face_krw'], 2700)
        self.assertEqual(first['stressed']['event']['eligible_face_krw'], 2500)
        self.assertEqual(rows(first['stressed'])[names[2]]['eligible_face_krw'], 450)
        self.assertEqual(rows(second['stressed'])[names[0]]['open_refund_krw'], 200)
        self.assertEqual(rows(second['stressed'])[names[1]]['open_refund_krw'], 200)
        self.assertEqual(first['delta']['portfolio']['open_refund_krw'], 200)

    def test_permutations_have_identical_calculation_digests(self):
        draw_book(self.service, amount=10000)
        request = spec(('sim-committed', 'sim-refund'))
        request['events'].append({'event_id': 'E2', 'claim_refs': [ref('sim-pending')]})
        request['scenarios'].append({**request['scenarios'][0], 'scenario_id': 'S2', 'event_id': 'E2'})
        expected = self.evaluate(request)
        for events, scenarios, members in itertools.product((False, True), repeat=3):
            variant = copy.deepcopy(request)
            if events:
                variant['events'].reverse()
            if scenarios:
                variant['scenarios'].reverse()
            if members:
                for event in variant['events']:
                    event['claim_refs'].reverse()
            actual = self.evaluate(variant)
            self.assertEqual(actual['scenarios'], expected['scenarios'])
            self.assertEqual(actual['normalized_request_digest'], expected['normalized_request_digest'])

    def test_zero_shock_identity_and_tier_is_frozen(self):
        draw_book(self.service, amount=10000)
        report = self.evaluate(spec(amount=0))
        after = report['scenarios'][0]['stressed']
        self.assertEqual(report['baseline']['portfolio'], after['portfolio'])
        report = self.evaluate(spec(amount=1))
        before = report['baseline']['advances'][0]['witness']
        after = report['scenarios'][0]['stressed']['advances'][0]['witness']
        self.assertEqual(before['frozen_margin_terms'], after['frozen_margin_terms'])
        self.assertEqual(before['frozen_ledger_terms'], after['frozen_ledger_terms'])
        self.assertEqual(before['frozen_ledger_terms']['tier'], 'T1')
        self.assertNotIn('stress', report['unchanged_risk_folds'])
        self.assertEqual(report['unchanged_risk_folds']['reserve']['requirement_krw'], 150)

    def test_relative_refund_evaluator_equivalence_with_matching_increment(self):
        draw_book(self.service, amount=10000)
        prepared = stress.prepare(capture(self.service), stress.load_policy())
        s = prepared['drawn'][0]
        amount = margin.eligible_face(s['claim'], s['margin']['payees']) * risk.SHOCKS_BPS[-1] // stress.BPS_SCALE
        inputs = {'margin_subjects': [copy.deepcopy(s)], 'sim_day': 0, 'margin_rows': []}
        risk_whatif._refund_shock(inputs, self.service.terms)
        report = self.evaluate(spec(amount=amount))
        after = report['scenarios'][0]['stressed']['advances'][0]['witness']['measurement']
        self.assertEqual(after, margin.measure(inputs['margin_subjects'][0]))

    def test_rounding_and_hypothetical_breach(self):
        draw_book(self.service, amount=80000)
        report = self.evaluate(spec(amount=101))
        row = report['scenarios'][0]['stressed']['advances'][0]
        rate = row['witness']['frozen_margin_terms']['advance_rate_bps']
        self.assertEqual(row['borrowing_base_krw'], (95000 - 101) * rate // stress.BPS_SCALE)
        report = self.evaluate(spec(amount=10000))
        self.assertEqual(report['scenarios'][0]['stressed']['portfolio']['hypothetical_margin_breaches'], 1)

    def test_mapped_boundary_gross_boundary_and_atomic_late_rejection(self):
        draw_book(self.service, amount=10000)
        report = self.evaluate(spec(amount=95000))
        self.assertEqual(rows(report['scenarios'][0]['stressed'])['sim-committed']['eligible_face_krw'], 0)
        for amount in (95001, 100000):
            report = self.evaluate(spec(amount=amount), status='PARTIAL')
            after = report['scenarios'][0]['stressed']
            self.assertIsNone(after['portfolio']['eligible_face_krw'])
            self.assertIsNone(after['portfolio']['borrowing_base_krw'])
            self.assertIn('REFUND_MAPPING_NOT_BOUND', rows(after)['sim-committed']['reasons'])
        request = spec()
        request['scenarios'].append({**request['scenarios'][0], 'scenario_id': 'S2', 'additional_open_refund_krw': 100001})
        self.rejected(self.evaluate(request, status='REJECTED'), 'REFUND_EXCEEDS_MONETARY_DOMAIN')

    def test_unsupported_outside_claim_and_zero_shock_preserve_labels(self):
        draw_book(self.service, amount=10000)
        data = capture(self.service).detached()
        c = data['producer']['fixtures']['rows']['sim-refund']['claim']
        c.update(refund_accepted=1, refund_outstanding=c['refund_face'] - 1, pg_adjustment_outstanding=1)
        report = self.evaluate(spec(amount=0), FrozenInputs(canonical_bytes(data)), 'PARTIAL')
        left, right = rows(report['baseline'])['sim-refund'], rows(report['scenarios'][0]['stressed'])['sim-refund']
        self.assertEqual(left, right)
        self.assertIn('REFUND_MAPPING_NOT_BOUND', left['reasons'])
        self.assertIsNone(report['baseline']['portfolio']['eligible_face_krw'])
        self.assertFalse(report['baseline']['coverage']['complete'])
        self.assertEqual(report['baseline']['coverage']['unsupported_claim_count'], 1)
        self.assertEqual(report['baseline']['coverage']['portfolio_safety_conclusion'], 'NOT_ASSERTED')

    def test_invalid_source_equations_are_noncomputed(self):
        for field in ('gross', 'refund_outstanding', 'confirmed_cash', 'undistributed_cash', 'recovery_due'):
            data = capture(self.service).detached()
            data['producer']['fixtures']['rows']['sim-refund']['claim'][field] += 1
            report = self.evaluate(frozen=FrozenInputs(canonical_bytes(data)), status='PARTIAL')
            row = rows(report['baseline'])['sim-refund']
            self.assertIn('CLAIM_INVARIANTS_NOT_BOUND', row['reasons'])
            self.assertIsNone(row['eligible_face_krw'])
            self.assertIsNone(report['baseline']['portfolio']['open_refund_krw'])

    def test_missing_terms_even_empty_and_unrelated_fees(self):
        for name in stress.REQUIRED_TERMS:
            data = capture(self.service).detached()
            items = json.loads(data['policy_items_json'])
            del items[name]
            data['policy_items_json'] = json.dumps(items)
            report = self.evaluate(frozen=FrozenInputs(canonical_bytes(data)), status='UNAVAILABLE')
            self.assertEqual(report['diagnostics'][0]['code'], 'TERMS_NOT_BOUND')
            self.assertNotIn('baseline', report)
        data = capture(self.service).detached()
        items = json.loads(data['policy_items_json'])
        del items['fees']
        data['policy_items_json'] = json.dumps(items)
        self.evaluate(frozen=FrozenInputs(canonical_bytes(data)))

    def test_all_six_policy_entries_must_be_adopted_and_semantics_usable(self):
        original = stress.resources.read_note
        for name in stress.POLICY_ENTRIES:
            def altered(path, name=name):
                note = copy.deepcopy(original(path))
                if str(path).endswith('CAPITAL_EVENT_STRESS.md'):
                    note['block']['entries'][name]['status'] = 'UNDETERMINED'
                return note
            with patch.object(stress.resources, 'read_note', side_effect=altered):
                report = self.evaluate(status='UNAVAILABLE')
                self.assertEqual(report['diagnostics'][0]['code'], 'EVENT_POLICY_NOT_BOUND')
        def altered(path):
            note = copy.deepcopy(original(path))
            if str(path).endswith('CAPITAL_EVENT_STRESS.md'):
                note['block']['entries']['claim_shock_identity']['value']['applications_per_member_claim'] = 2
            return note
        with patch.object(stress.resources, 'read_note', side_effect=altered):
            self.evaluate(status='UNAVAILABLE')

    def test_request_rejections(self):
        mutations = [
            ('DUPLICATE_EVENT_ID', lambda r: r['events'].append(copy.deepcopy(r['events'][0]))),
            ('DUPLICATE_SCENARIO_ID', lambda r: r['scenarios'].append(copy.deepcopy(r['scenarios'][0]))),
            ('DUPLICATE_MEMBERSHIP', lambda r: r['events'][0]['claim_refs'].append(ref())),
            ('INVALID_MEMBERSHIP', lambda r: r['events'][0].update(claim_refs=[])),
            ('UNKNOWN_EVENT', lambda r: r['scenarios'][0].update(event_id='missing')),
            ('UNSUPPORTED_SHOCK_KIND', lambda r: r['scenarios'][0].update(kind='OPTIMIZE')),
            ('INVALID_REQUEST_ID', lambda r: r['events'][0].update(event_id='한글')),
            ('INVALID_REQUEST_ID', lambda r: r['events'][0].update(event_id='x' * 129)),
            ('INVALID_REQUEST_SHAPE', lambda r: r.update(unknown=True)),
            ('INVALID_REQUEST_SHAPE', lambda r: r['scenarios'][0].update(unknown=True)),
            ('INVALID_REQUEST_FORMAT', lambda r: r.update(format='bad')),
            ('INVALID_CLAIM_IDENTITY', lambda r: r['events'][0]['claim_refs'][0].update(currency='USD')),
            ('INVALID_CLAIM_IDENTITY', lambda r: r['events'][0]['claim_refs'][0].update(claim_id=' x')),
            ('UNKNOWN_CLAIM_REFERENCE', lambda r: r['events'].append({'event_id':'unselected', 'claim_refs':[ref('unknown')]})),
        ]
        for code, change in mutations:
            with self.subTest(code=code):
                request = spec()
                change(request)
                self.rejected(self.evaluate(request, status='REJECTED'), code)
        for amount in (-1, True, 1.0, stress.assets.KRW['max_atoms'] + 1, '1', None):
            self.rejected(self.evaluate(spec(amount=amount), status='REJECTED'), 'INVALID_SHOCK_AMOUNT')

    def test_strict_json_and_raw_byte_limit(self):
        for raw in (b'{"x":1,"x":2}', b'\xef\xbb\xbf{}', b'{}\x00', b'\xff', b'NaN',
                    b'Infinity', b'-Infinity', b'[]', b'{}{}', b'[' * 2000):
            report = stress.evaluate_detached(capture(self.service), raw)
            self.assertEqual(report['status'], 'REJECTED', raw[:20])
        self.rejected(stress.evaluate_detached(capture(self.service), b' ' * 8193), 'SCENARIO_CAPACITY_EXCEEDED')
        raw = canonical_bytes(spec())
        self.assertEqual(stress.evaluate_detached(capture(self.service), raw + b' ' * (8192-len(raw)))['status'], 'COMPLETE')
        for payload in ('NaN', 'Infinity', '-Infinity'):
            raw = canonical_bytes(spec()).replace(b'100,', payload.encode() + b',')
            self.rejected(stress.evaluate_detached(capture(self.service), raw), 'INVALID_REQUEST_JSON')

    def test_request_capacity_boundaries(self):
        policy = stress.load_policy()
        for dimension, count in (('max_events', 2), ('max_scenarios', 2), ('max_claims_per_event', 2), ('max_membership_edges', 2)):
            request = spec(('sim-committed', 'sim-refund')) if dimension in ('max_claims_per_event','max_membership_edges') else spec()
            if dimension == 'max_events':
                request['events'].append({'event_id': 'E2', 'claim_refs': [ref()]})
            if dimension == 'max_scenarios':
                request['scenarios'].append({**request['scenarios'][0], 'scenario_id':'S2'})
            lowered = copy.deepcopy(policy)
            lowered['values']['scenario_capacity_bounds'][dimension] = count
            stress.validate_request(canonical_bytes(request), lowered)
            lowered['values']['scenario_capacity_bounds'][dimension] = count-1
            with self.assertRaises(stress.StressError) as caught:
                stress.validate_request(canonical_bytes(request), lowered)
            self.assertEqual(caught.exception.code, 'SCENARIO_CAPACITY_EXCEEDED')
        lowered = copy.deepcopy(policy)
        lowered['values']['scenario_capacity_bounds']['max_request_bytes'] = len(canonical_bytes(spec())) - 1
        with self.assertRaises(stress.StressError):
            stress.validate_request(canonical_bytes(spec()), lowered)

    def test_snapshot_capacity_boundaries_and_operation_intersection(self):
        draw_book(self.service, amount=10000)
        tick(self.service, 'capacity-tick', 0, 1)
        frozen = capture(self.service)
        data = frozen.detached()
        policy = stress.load_policy()
        for dimension, actual in (('max_snapshot_claims',len(self.service.fixtures.rows)),
                                  ('max_snapshot_advances',1), ('max_advance_claim_edges',1)):
            modified = copy.deepcopy(policy)
            modified['values']['scenario_capacity_bounds'][dimension] = actual
            stress._capacity(data, modified['values']['scenario_capacity_bounds'])
            modified['values']['scenario_capacity_bounds'][dimension] = actual-1
            with self.assertRaises(stress.StressError) as caught:
                stress._capacity(data, modified['values']['scenario_capacity_bounds'])
            self.assertEqual(caught.exception.code, 'SCENARIO_CAPACITY_EXCEEDED')
        with patch.object(stress, 'MAX_OPERATIONS', 3):
            self.evaluate(frozen=frozen, status='REJECTED')  # four receipts, one advance
        with patch.object(stress, 'MAX_OPERATIONS', 4):
            self.evaluate(frozen=frozen)
        for dimension, current in (
            ('OVERLAY_MAX_ENTRIES', len(data['overlay_entries'])),
            ('OVERLAY_ENTRY_MAX_BYTES', max(map(overlay.entry_size,data['overlay_entries']))),
            ('DECISION_RECORDS_MAX',1),
            ('ENVELOPE_MAX_BYTES', overlay.section_size(self.service.storage.load()['payload'],data['overlay_entries']))):
            changed = copy.deepcopy(data)
            changed['policy']['bounds'][dimension] = current
            self.evaluate(frozen=FrozenInputs(canonical_bytes(changed)))
            changed['policy']['bounds'][dimension] = current - 1
            self.evaluate(frozen=FrozenInputs(canonical_bytes(changed)), status='REJECTED' if current>1 else 'UNAVAILABLE')
        tick(self.service, 'tick', 1, 2)
        changed = capture(self.service).detached()
        changed['policy']['bounds']['SIM_DAY_MAX'] = 2
        self.evaluate(frozen=FrozenInputs(canonical_bytes(changed)))
        changed['policy']['bounds']['SIM_DAY_MAX'] = 1
        self.evaluate(frozen=FrozenInputs(canonical_bytes(changed)), status='REJECTED')

    def test_invalid_mapping_and_ambiguous_identity(self):
        draw_book(self.service, amount=10000)
        data = capture(self.service).detached()
        data['case_fixtures']['sim-a'] = 'sim-refund'
        self.rejected(self.evaluate(frozen=FrozenInputs(canonical_bytes(data)), status='REJECTED'), 'INVALID_RELATIONSHIPS')
        data = capture(self.service).detached()
        data['producer']['fixtures']['rows']['duplicate'] = copy.deepcopy(data['producer']['fixtures']['rows']['sim-refund'])
        self.rejected(self.evaluate(frozen=FrozenInputs(canonical_bytes(data)), status='REJECTED'), 'AMBIGUOUS_CLAIM_IDENTITY')

    def test_missing_draw_gate_and_snapshot_failures(self):
        draw_book(self.service, amount=10000)
        data = capture(self.service).detached()
        data['receipts']['a-draw']['receipt']['result'] = None
        self.evaluate(frozen=FrozenInputs(canonical_bytes(data)), status='UNAVAILABLE')
        self.save()
        for code in ('COHERENT_SNAPSHOT_UNSUPPORTED', 'IMMUTABLE_FIXTURES_REQUIRED'):
            with patch.object(stress.PinnedFsmProducer, 'snapshot_inputs', side_effect=ValueError(code)):
                report = stress.report_workspace(self.root, canonical_bytes(spec()))
            self.assertEqual(report['diagnostics'][0]['code'], code)

    def test_audited_capture_preserves_tree_and_never_writes_or_uses_live_views(self):
        draw_book(self.service, amount=10000)
        path = self.save()
        def tree():
            return {p.name:(p.stat().st_mode,p.read_bytes()) for p in self.root.iterdir()}
        before = tree()
        with (patch.object(CapitalService, '_persist', side_effect=AssertionError('write')),
             patch.object(CapitalService, '_watch_inputs', side_effect=AssertionError('live views')),
             patch.object(CapitalService, 'execute', side_effect=AssertionError('command'))):
            report = stress.report_workspace(self.root, canonical_bytes(spec()))
        self.assertEqual(report['status'], 'COMPLETE', report)
        self.assertEqual(tree(), before)
        self.assertEqual(report['inputs']['workspace_sha256'], stress._sha(path.read_bytes()))
        self.assertTrue(report['capture_audit']['ok'])
        for key in ('inputs_digest','policy_inputs_digest','fixtures_digest','terms_provenance'):
            self.assertIn(key, report['inputs'])
        for key in ('funds_executed','workspace_mutated','applied'):
            self.assertIs(report[key], False)
        self.assertEqual(report['label'], 'SIMULATED')

    def test_replacement_after_capture_uses_audited_bytes(self):
        draw_book(self.service, amount=10000)
        path = self.save()
        real = stress.audit.audit_workspace_bytes
        def audit_then_replace(raw, **kwargs):
            result = real(raw, **kwargs)
            path.write_bytes(b'corrupt replacement')
            return result
        with patch.object(stress.audit, 'audit_workspace_bytes', side_effect=audit_then_replace):
            report = stress.report_workspace(self.root, canonical_bytes(spec()))
        self.assertEqual(report['status'], 'COMPLETE', report)
        self.assertEqual(report['baseline']['portfolio']['exposure_krw'], 10000)
        with patch.object(stress, 'offline_service', side_effect=AssertionError('must short circuit')):
            report = stress.report_workspace(self.root, canonical_bytes(spec()))
        self.assertEqual(report['status'], 'UNAVAILABLE')
        self.assertNotIn('baseline', report)

    def test_cli_determinism_and_exit_codes(self):
        draw_book(self.service, amount=80000)
        self.save()
        path = self.root / 'events.json'
        path.write_bytes(canonical_bytes(spec(amount=10000)))
        command = [sys.executable, 'scripts/event_stress.py', '--workspace', str(self.root), '--spec', str(path)]
        left = subprocess.run(command, cwd=ROOT, capture_output=True)
        right = subprocess.run(command, cwd=ROOT, capture_output=True)
        self.assertEqual(left.returncode, 0, left.stderr)
        self.assertEqual(left.stdout, right.stdout)
        self.assertEqual(json.loads(left.stdout)['status'], 'COMPLETE')
        path.write_bytes(canonical_bytes(spec(amount=95001)))
        self.assertEqual(subprocess.run(command, cwd=ROOT, capture_output=True).returncode, 1)
        path.unlink()
        self.assertEqual(subprocess.run(command, cwd=ROOT, capture_output=True).returncode, 1)
        self.assertEqual(subprocess.run(command[:2], cwd=ROOT, capture_output=True).returncode, 2)


if __name__ == '__main__':
    unittest.main()
