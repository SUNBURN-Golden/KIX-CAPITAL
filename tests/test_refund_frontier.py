"""Independent exhaustive integer allocations, route fences and read isolation."""
import copy
import hashlib
import itertools
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from capital import margin, overlay, refund_frontier as f, risk
from capital.service import ApiError, CapitalService
from capital.terms import DecisionNoteTermsPolicy
from capital.store import FileWorkspace
from scripts.refund_frontier_vectors import subject, inputs, build_artifact, FILE
from tests.facade_schema import load_contract, validate, SchemaError
from tests.test_margin import disposable, drawn_then_refunded
from tests.test_overlay import draw_book, tick
from tests import test_risk_whatif as server_harness


def build(rows, change=None):
    data = inputs(copy.deepcopy(rows))
    if change:
        change(data)
    return f.build(f.FrozenInputs.capture(data))


def exhaustive(rows):
    """Cartesian physical-line enumeration: no production search or inverse."""
    budgets = {}
    for s in rows:
        for line in s['claim']['obligations']:
            if line['payee'] in s['margin']['payees']:
                budgets[(s['case']['claim_id'], line['payee'])] = max(
                    0, line['outstanding'] - line.get('refund_open_krw', 0))
    keys = sorted(budgets)
    best = None
    for values in itertools.product(*(range(budgets[k] + 1) for k in keys)):
        allocation = dict(zip(keys, values))
        for s in rows:
            eligible = sum(line['outstanding'] for line in s['claim']['obligations']
                           if line['payee'] in s['margin']['payees']) - s['claim']['refund_face']
            delta = sum(allocation.get((s['case']['claim_id'], p), 0) for p in s['margin']['payees'])
            base = max(0, eligible - delta) * s['margin']['advance_rate_bps'] // 10000
            if s['principal'] > base:
                best = sum(values) if best is None else min(best, sum(values))
    return best


class ArithmeticTests(unittest.TestCase):
    def test_cartesian_enumeration_plateaus_equality_and_domain_endpoints(self):
        for amounts in ((0,), (1,), (2, 3), (6, 4)):
            for rate in (0, 1, 2500, 5000, 8500, 10000):
                for exposure in range(0, 8):
                    rows = [subject(amounts=amounts, rate=rate, exposure=exposure)]
                    result = build(rows)
                    self.assertEqual(result['portfolio']['frontier_krw'], exhaustive(rows), (amounts, rate, exposure))
                    self.check_witness(result['cases'][0]['witness'], rows)

    def check_witness(self, witness, rows):
        if witness is None:
            return
        for point, field in (('allocation', 'advance_evaluations_at_frontier'),
                             ('predecessor_allocation', 'advance_evaluations_at_predecessor')):
            allocation = witness[point]
            if allocation is None:
                self.assertEqual(witness['frontier_krw'], 0)
                continue
            amount = sum(v['refund_krw'] for v in allocation)
            self.assertEqual(amount, witness['frontier_krw'] - (point == 'predecessor_allocation'))
            values = {(v['claim_id'], v['payee_label']): v['refund_krw'] for v in allocation}
            for s, evaluation in zip(rows, witness[field]):
                shifted = copy.deepcopy(s)
                delta = sum(values.get((s['case']['claim_id'], p), 0) for p in s['margin']['payees'])
                shifted['claim']['refund_face'] += delta
                self.assertEqual(evaluation['evaluation'], margin.measure(shifted))
            flags = [v['evaluation']['breach'] for v in witness[field]]
            self.assertEqual(any(flags), point == 'allocation')

    def test_shared_lines_unequal_rates_and_utf8_tie(self):
        for rows in ([subject('a', amounts=(6, 4)), subject('b', amounts=(6, 4), exposure=1)],
                     [subject('a', 'c', amounts=(20,), exposure=15, rate=8500),
                      subject('b', 'd', amounts=(10,), exposure=3)],
                     [subject('é', amounts=(6, 4)), subject('z', amounts=(6, 4))]):
            result = build(rows)
            self.assertEqual(result['portfolio']['frontier_krw'], exhaustive(rows))
            self.check_witness(result['portfolio']['witness'], sorted(rows, key=lambda s:s['advance_id'].encode()))
        self.assertEqual(result['portfolio']['witness']['selected_advance_id'], 'z')
        self.assertEqual(result['coverage']['affected_ids'], ['z', 'é'])

    def test_existing_refund_sourced_once_and_frozen_rate(self):
        row = subject(amounts=(10,), exposure=3)
        row['claim']['refund_face'] = 2
        row['claim']['obligations'][0].update(refund_open_krw=2, refund_attribution_source='SYNTHETIC_TEST')
        result = build([row])
        self.assertEqual(result['portfolio']['frontier_krw'], exhaustive([row]))
        self.assertEqual(result['cases'][0]['domain_max_krw'], 8)
        self.check_witness(result['cases'][0]['witness'], [row])

    def test_margin_disagreement_suppresses_exact_output(self):
        original = margin.measure
        def incompatible(subject):
            measured = original(subject)
            measured['base_krw'] += 1
            return measured
        with patch.object(margin, 'measure', side_effect=incompatible):
            body = build([subject()])
        self.assertEqual(body['cases'][0]['status'], f.UNSUPPORTED)
        self.assertIsNone(body['cases'][0]['frontier_krw'])

    def test_fixed_bps_predicate_correspondence(self):
        rows = [subject(amounts=(6, 4), exposure=4)]
        stress = risk._stress(rows, 1)
        for shock, stressed in zip(risk.SHOCKS_BPS, stress['rows']):
            s = copy.deepcopy(rows[0])
            delta = 10 * shock // 10000
            s['claim']['refund_face'] += delta
            measured = margin.measure(s)
            self.assertEqual(measured['breach'], delta >= build(rows)['cases'][0]['frontier_krw'])
            self.assertEqual(stressed['margin_call_count'], int(measured['breach']))
            self.assertEqual(stressed['shocked_eligible_face_krw'], measured['eligible_face_krw'])

    def test_large_integer_domain_has_logarithmic_measure_bound(self):
        row = subject(amounts=(10**30,), exposure=10**20)
        with patch.object(margin, 'measure', wraps=margin.measure) as measured:
            result = build([row])
        self.assertEqual(result['cases'][0]['outcome'], 'FIRST_BREACH')
        self.assertLess(measured.call_count, 2 * (10**30).bit_length())


class DiagnosticsTests(unittest.TestCase):
    def status(self, row, expected, change=None):
        result = build([row], change)
        case = result['cases'][0]
        self.assertEqual(case['status'], expected, case)
        if expected not in (f.FIRST, f.ALREADY):
            self.assertIsNone(case['frontier_krw'])
        return result

    def test_missing_is_never_zero_and_terminal_precedes_missing(self):
        for principal in (None, -1, True):
            row = subject(); row['principal'] = principal
            self.status(row, f.MISSING)
        row = subject(); row['case']['phase'] = 'DEFAULTED'; row['margin'] = None
        self.status(row, f.TERMINAL)
        for change in (lambda r:r.update(margin=None), lambda r:r.update(gate=None),
                       lambda r:r['margin'].update(payees=[]), lambda r:r['claim'].update(obligations=[]),
                       lambda r:r['claim'].update(refund_face=None)):
            row = subject(exposure=0); change(row); self.status(row, f.MISSING)
        row = subject(); row['claim']['refund_face'] = 1
        self.status(row, f.MISSING)
        row['claim']['obligations'][0].update(refund_open_krw=0, refund_attribution_source='TEST')
        row['claim']['obligations'][1].update(refund_open_krw=0, refund_attribution_source='TEST')
        self.status(row, f.UNSUPPORTED)
        self.status(subject(rate=0), f.ALREADY)
        self.status(subject(amounts=(0,)), f.ALREADY)
        self.status(subject(exposure=0), f.ZERO)

    def test_registry_requires_full_evidence_and_positive_terminal_residual_excludes(self):
        self.status(subject(), f.MISSING, lambda d:d.update(registry={}))
        self.status(subject(), f.MISSING, lambda d:d['registry'].update(fold_success=False))
        self.status(subject(), f.MISSING, lambda d:d['registry'].update(lookups={}))
        for status in ('OPEN', 'IMPAIRED', 'VOID', 'RESOLVED', 'PROPOSED'):
            entry = {'claim_id': 'c', 'payee_label': 'payee-0', 'status': status,
                     'slice_face_krw': 10, 'baseline_distributed_krw': 0,
                     'recourse_received_krw': 0, 'served_krw': 0}
            self.status(subject(amounts=(0,), exposure=1), (f.ALREADY if status == 'PROPOSED' else f.SLICE),
                        lambda d:d['registry']['lookups'].update(c=[entry]))
            entry['recourse_received_krw'] = 10
            self.status(subject(), f.FIRST, lambda d:d['registry']['lookups'].update(c=[entry]))

    def test_zero_exposure_precedes_positive_exposure_support_guards(self):
        row = subject(exposure=0)
        self.status(row, f.ZERO, lambda d:d.update(registry={}))
        row['claim']['refund_face'] = 2
        self.status(row, f.ZERO)  # Attribution is unnecessary to prove zero debt cannot breach.
        a, b = subject('a'), subject('b', exposure=0)
        result = build([a,b])
        witness = result['portfolio']['witness']
        self.assertFalse(witness['advance_evaluations_at_frontier'][1]['evaluation']['breach'])
        self.assertEqual(witness['advance_evaluations_at_frontier'][1]['evaluation']['base_krw'], 3)
        self.assertEqual(result['cases'][1]['outcome'], 'NO_BREACH_IN_DOMAIN')
        b['case']['beneficiary_role'] = 'different-zero-holder'
        self.assertEqual(build([a,b])['cases'][0]['status'], f.FIRST)

    def test_overlap_conflict_disjoint_beneficiaries_and_incomplete_minimum(self):
        a, b = subject('a'), subject('b', beneficiary='C')
        self.assertTrue(all(r['status'] == f.AMBIGUOUS for r in build([a,b])['cases']))
        b['principal'] = None
        self.assertEqual([r['status'] for r in build([a,b])['cases']], [f.AMBIGUOUS, f.MISSING])
        b['principal'] = 4
        b['claim']['obligations'][0]['outstanding'] += 1
        self.assertTrue(all(r['status'] == f.UNSUPPORTED for r in build([a,b])['cases']))
        b = subject('b', 'd'); b['margin'] = None
        result = build([a,b])
        self.assertIsNone(result['beneficiaries'][0]['frontier_krw'])
        self.assertEqual(result['portfolio']['scope'], 'ASSESSED_CASES_ONLY')
        a['principal'] = 100
        result = build([a,b]); self.assertEqual(result['beneficiaries'][0]['frontier_krw'], 0)
        self.assertFalse(result['beneficiaries'][0]['evaluation_complete'])
        a,b = subject('a'),subject('b', beneficiary='C')
        a['margin']['payees'] = ['payee-0']; b['margin']['payees'] = ['payee-1']; a['principal'] = 3
        self.assertEqual([r['outcome'] for r in build([a,b])['cases']], ['FIRST_BREACH','ALREADY_BREACHED'])

    def test_policy_is_loaded_and_missing_deferred_or_changed_fail_closed(self):
        self.assertEqual(f.load_policy()['status'], 'BOUND')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'note.md'
            self.assertEqual(f.load_policy(path)['status'], 'NOT_BOUND')
            block = copy.deepcopy(f.load_policy()['block'])
            name = next(iter(block['entries']))
            for status, expected in (('DEFERRED','NOT_BOUND'), ('ADOPTED','UNSUPPORTED')):
                block['entries'][name]['status'] = status
                block['entries'][name]['value']['domain'] = 'changed'
                path.write_text('```capital-decision-v1\n'+json.dumps(block)+'\n```\n')
                policy = f.load_policy(path)
                self.assertEqual(policy['status'], expected)
                result = build([subject()], lambda d:d.update(policy=policy))
                self.assertIsNone(result['cases'][0]['frontier_krw'])

    def test_digests_are_independently_reproducible_and_detached(self):
        data = inputs([subject()]); frozen = f.FrozenInputs.capture(data)
        result = f.build(frozen); data['subjects'][0]['principal'] = 1000
        self.assertEqual(f.build(frozen), result)
        encode = lambda v:json.dumps(v,sort_keys=True,separators=(',', ':'),ensure_ascii=True).encode()
        self.assertEqual(result['inputs_digest'], hashlib.sha256(frozen.raw).hexdigest())
        expected = result.pop('result_digest')
        self.assertEqual(expected, hashlib.sha256(encode(result)).hexdigest())


class ServiceTests(unittest.TestCase):
    def test_local_cut_preserves_legacy_risk_and_all_state(self):
        source, service = disposable(); draw_book(service, amount=50000)
        before = (service.machine.canonical_state(), copy.deepcopy(service.overlay_entries),
                  copy.deepcopy(service.receipts), copy.deepcopy(source.rows), service.risk())
        with patch.object(service, '_watch_bound', side_effect=AssertionError('legacy capture')):
            body = service.risk_refund_frontier(service.instance_id)
        result = body.pop('refund_frontier')
        self.assertEqual(body, before[-1]); self.assertEqual(result['cases'][0]['outcome'], 'FIRST_BREACH')
        self.assertEqual(before[:4], (service.machine.canonical_state(), service.overlay_entries, service.receipts, source.rows))
        self.assertEqual(service.risk_refund_frontier(service.instance_id)['refund_frontier'], result)
        other_source, other = disposable(); draw_book(other, amount=50000)
        self.assertEqual(other.risk_refund_frontier(other.instance_id)['refund_frontier'], result)

    def test_attribution_missing_and_receipt_missing_remain_visible(self):
        _, service = drawn_then_refunded()
        result = service.risk_refund_frontier(service.instance_id)['refund_frontier']
        self.assertEqual(result['cases'][0]['reason'], 'REFUND_LINE_ATTRIBUTION_MISSING')
        service.receipts.clear()
        body = service.risk_refund_frontier(service.instance_id)
        self.assertEqual(body['status'], 'NOT_BOUND'); self.assertIsNone(body['risk_digest'])
        self.assertEqual(len(body['refund_frontier']['cases']), 1)

    def test_immutable_and_missing_terms_have_blocks_and_no_frontier(self):
        service = CapitalService(); draw_book(service)
        self.assertEqual(service.risk_refund_frontier(service.instance_id)['refund_frontier']['cases'][0]['status'], f.WORKSPACE)
        service.terms = DecisionNoteTermsPolicy(Path('/no/such/terms'))
        body = service.risk_refund_frontier(service.instance_id)
        self.assertIn('refund_frontier', body); self.assertIsNone(body['risk_digest'])
        validate(body, {'$ref':'#/definitions/risk_state'}, load_contract())

    def test_receipt_transport_identity_is_not_financial_provenance(self):
        _, service = disposable(); draw_book(service, amount=50000)
        before = service.risk_refund_frontier(service.instance_id)['refund_frontier']
        service.receipts['a-draw']['receipt']['instance_id'] = 'transport-only-change'
        service.receipts['a-draw']['receipt']['timestamp'] = 'transport-only-time'
        self.assertEqual(before, service.risk_refund_frontier(service.instance_id)['refund_frontier'])
        service.receipts['a-draw']['receipt']['result']['credit']['settlement_gate'] = 'UNKNOWN_GATE'
        self.assertNotEqual(before['inputs_digest'], service.risk_refund_frontier(service.instance_id)['refund_frontier']['inputs_digest'])

    def test_unsupported_adapter_not_invoked(self):
        service = CapitalService()
        class Adapter:
            def __getattr__(self, key):
                raise AssertionError('adapter touched')
        service.producer = Adapter()
        with self.assertRaises(ApiError) as caught:
            service.risk_refund_frontier(service.instance_id)
        self.assertEqual((caught.exception.status,caught.exception.detail['reason']), (400,'COHERENT_SNAPSHOT_UNSUPPORTED'))

    def test_real_registry_fold_proposed_open_and_void(self):
        from tests.test_claim_slices import advance, seed
        source, service = seed.book()
        advance(service, 1000)
        seed.register(service, 'frontier-slice', 1000)
        before = copy.deepcopy(service.overlay_entries)
        body = service.risk_refund_frontier(service.instance_id)['refund_frontier']
        self.assertEqual(body['cases'][0]['outcome'], 'FIRST_BREACH')
        self.assertTrue(body['source']['registry']['section_present'])
        self.assertEqual(service.overlay_entries, before)
        seed.open_slice(service, 'frontier-slice')
        body = service.risk_refund_frontier(service.instance_id)['refund_frontier']
        self.assertEqual(body['cases'][0]['status'], f.SLICE)
        validate(body, {'$ref':'#/definitions/refund_frontier'}, load_contract())
        evidence = body['source']['registry']['lookups']['demo-delta-small'][0]
        self.assertEqual(f.digest(json.loads(evidence['canonical_row_json'])), evidence['row_digest'])
        seed.post(service, 'void_slice', 'frontier-void', slice_id='frontier-slice', reason='OPERATOR_WITHDRAWN')
        body = service.risk_refund_frontier(service.instance_id)['refund_frontier']
        self.assertEqual(body['cases'][0]['status'], f.SLICE)

    def test_missing_mapping_and_malformed_gate_are_diagnostics(self):
        for defect in ('mapping', 'gate', 'receipt-shape', 'mapping-shape', 'claim-shape'):
            _, service = disposable(); draw_book(service, amount=50000)
            if defect == 'mapping':
                service.case_fixtures.clear()
            elif defect == 'gate':
                service.receipts['a-draw']['receipt']['result']['credit']['settlement_gate'] = []
            elif defect == 'receipt-shape':
                service.receipts['a-draw'] = None
            elif defect == 'mapping-shape':
                service.case_fixtures['sim-a'] = []
            else:
                service.fixtures.rows['sim-committed']['claim']['refund_face'] = None
            body = service.risk_refund_frontier(service.instance_id)
            self.assertEqual(body['refund_frontier']['cases'][0]['status'], f.MISSING)
            self.assertEqual(body['status'], 'NOT_BOUND')
            validate(body, {'$ref':'#/definitions/risk_state'}, load_contract())

    def test_capture_lock_and_workspace_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = FileWorkspace.open(tmp)
            try:
                _, service = disposable(storage); draw_book(service, amount=50000)
                files = {str(p):p.read_bytes() for p in Path(tmp).iterdir() if p.is_file()}
                service.risk_refund_frontier(service.instance_id)
                self.assertEqual(files,{str(p):p.read_bytes() for p in Path(tmp).iterdir() if p.is_file()})
            finally:
                storage.close()
        _, service = disposable(); draw_book(service, amount=50000)
        captured = threading.Event(); release = threading.Event(); ticked = threading.Event()
        original = service._refund_frontier_inputs
        def capture():
            value = original(); captured.set(); release.wait(5); return value
        results = []
        with patch.object(service, '_refund_frontier_inputs', side_effect=capture):
            read = threading.Thread(target=lambda:results.append(service.risk_refund_frontier(service.instance_id)))
            mutation = threading.Thread(target=lambda:(tick(service,'concurrent',0,1),ticked.set()))
            read.start(); self.assertTrue(captured.wait(5)); mutation.start()
            self.assertFalse(ticked.wait(.05)); release.set()
            read.join(5); mutation.join(5)
        self.assertFalse(read.is_alive()); self.assertFalse(mutation.is_alive())
        self.assertEqual(results[0]['sim_day'],0); self.assertTrue(ticked.is_set())


class RouteTests(server_harness.LiveServerTests):
    def test_frontier_authorization_arguments_and_session(self):
        _, state = self.call('/api/state')
        suffix = '&instance_id='+state['instance_id']
        for role in ('organizer','auditor'):
            status, body = self.call('/api/risk?refund_frontier=1'+suffix,self.tokens[role])
            self.assertEqual(status,200); self.assertIn('refund_frontier', body)
            validate(body, self.route('/api/risk')['response'], self.contract)
        for role in ('observer','agent'):
            status,body = self.call('/api/risk?refund_frontier=bad',self.tokens[role])
            self.assertEqual((status,body['error']),(403,'ROLE_FORBIDDEN'))
        for query in ('refund_frontier=2','refund_frontier=1&refund_frontier=1',
                      'refund_frontier=1&extra=1', 'refund_frontier=1&instance_id=x&instance_id=x'):
            status,body = self.call('/api/risk?'+query,self.tokens['organizer'])
            self.assertEqual((status,body['error']),(400,'INVALID_ARGUMENTS'))
        for query in ('refund_frontier=1','refund_frontier=1&instance_id=', 'refund_frontier=1&instance_id=stale'):
            status,body = self.call('/api/risk?'+query,self.tokens['organizer'])
            self.assertEqual((status,body['error']),(409,'SESSION_CHANGED'))
        _,ordinary = self.call('/api/risk?unrecognized=ignored',self.tokens['organizer'])
        self.assertNotIn('refund_frontier',ordinary)


class SchemaVectorTests(unittest.TestCase):
    def test_vectors_and_closed_nested_contract(self):
        self.assertEqual(FILE.read_bytes(),build_artifact())
        contract = load_contract()
        body = build([subject()])
        validate(body, {'$ref':'#/definitions/refund_frontier'}, contract)
        for path in ('cases','beneficiaries'):
            broken = copy.deepcopy(body); broken[path][0]['unexpected'] = 1
            with self.assertRaises(SchemaError):
                validate(broken, {'$ref':'#/definitions/refund_frontier'}, contract)
