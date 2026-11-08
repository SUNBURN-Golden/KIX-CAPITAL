"""Hand-calculated SIMULATED draw order consequences and offline boundaries."""
import hashlib
import itertools
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from capital import draw_order as dor
from capital.gate_producer import TransportLost
from capital.evidence import offline_service
from capital.service import ApiError, CapitalService
from capital.store import FILE_NAME, FileWorkspace, canonical_bytes, _checksum
from tests.test_overlay import run, draw_book, tick
from tests.test_claim_slices import seed

ROOT = Path(__file__).resolve().parents[1]


def approve(service, key, amount, fixture='sim-committed', bind=True):
    operations = [('offer', {'fixture_id': fixture, 'amount': amount}), ('approve', {})]
    if bind:
        operations.append(('bind_settlement', {}))
    for op, args in operations:
        receipt = run(service, op, key, key + '-' + op.replace('_', '-'), **args)
        assert receipt['outcome'] == 'ACCEPTED', receipt


def tree(directory):
    return {str(p.relative_to(directory)): (p.stat().st_mode, p.read_bytes() if p.is_file() else None)
            for p in [directory, *sorted(directory.rglob('*'))]}


class RehearsalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.service = CapitalService()
        self.addCleanup(self.service.observability.close)

    def save(self, legacy=False):
        self.service._persist()
        document = self.service.storage.load()
        if legacy:
            del document['envelope_version']
            del document['overlay']
        (self.directory / FILE_NAME).write_bytes(canonical_bytes(document))
        return document

    def shared(self):
        approve(self.service, 'sim-a', 60000)
        approve(self.service, 'sim-b', 50000)
        self.save()

    def report(self, ids=('sim-a', 'sim-b'), status='COMPLETE'):
        before = tree(self.directory)
        report = dor.rehearse_workspace(self.directory, list(ids))
        self.assertEqual(report['status'], status, report['reasons'])
        self.assertEqual(tree(self.directory), before)
        self.assertEqual(report['label'], 'SIMULATED')
        for field in ('funds_executed', 'workspace_mutated', 'lock_taken'):
            self.assertFalse(report[field])
        return report

    def test_shared_face_hand_calculation_and_preceding_record(self):
        self.shared()
        report = self.report()
        self.assertEqual(report['baseline']['risk']['totals']['outstanding_krw'], 0)
        for ordering, winning, reserve in zip(report['orderings'], (60000, 50000), (900, 750)):
            first, second = ordering['steps']
            self.assertEqual(first['observed_state_digest'], report['inputs']['state_digest'])
            self.assertEqual(first['command']['outcome'], 'ACCEPTED')
            self.assertEqual(second['command']['outcome'], 'REJECTED')
            self.assertEqual(second['command']['error'], 'ADVANCE_EXCEEDS_OPEN_FACE')
            self.assertEqual([r['id'][:2] for r in first['underwriting']['checks']],
                             ['U1', 'U2', 'U3', 'U4', 'U5', 'U6'])
            self.assertNotEqual(first['observed_state_digest'], second['observed_state_digest'])
            self.assertEqual(first['movements']['delta']['claim_reservations_krw'], {'sim-committed': winning})
            self.assertEqual(second['movements']['delta']['claim_reservations_krw'], {'sim-committed': 0})
            self.assertEqual(sum(first['movements']['delta']['advance_exposure_krw'].values()), winning)
            final = ordering['final']
            self.assertEqual(final['measures']['claim_reservations_krw'], {'sim-committed': winning})
            self.assertEqual(final['risk']['totals']['outstanding_krw'], winning)
            self.assertEqual(final['risk']['reserve']['requirement_krw'], reserve)
            self.assertEqual(final['risk']['concentration']['hhi_permille'], 1000)
        self.assertTrue(all(r['order_sensitive'] for r in report['comparison']['outcome_variants']))
        self.assertIn('reserve', [r['measure'] for r in report['comparison']['differing_financial_measures']])

    def test_advisory_failure_does_not_become_command_refusal(self):
        approve(self.service, 'sim-a', 90000)
        approve(self.service, 'sim-b', 5000)
        self.save()
        step = self.report()['orderings'][0]['steps'][0]
        checks = {r['id']: r for r in step['underwriting']['checks']}
        # T1 borrowing base is 85% of organizer's 95,000 line: 80,750.
        self.assertEqual(checks['U3_BORROWING_BASE']['outcome'], 'FAIL')
        self.assertEqual(step['command']['outcome'], 'ACCEPTED')

    def test_slice_encumbrance_uses_existing_guard_and_keeps_overlay(self):
        seed.register(self.service, 'slice-a', 10000000)
        seed.open_slice(self.service, 'slice-a')
        approve(self.service, 'sim-a', 20000000, 'demo-delta-small')
        approve(self.service, 'sim-b', 25000000, 'demo-delta-small')
        self.save()
        report = self.report()
        for ordering, winning, reserve in zip(report['orderings'], (20000000, 25000000), (300000, 375000)):
            first, second = ordering['steps']
            self.assertEqual(first['command']['outcome'], 'ACCEPTED')
            self.assertEqual(second['command']['kind'], 'API_ERROR')
            self.assertEqual(second['command']['code'], 'SLICE_DRAW_REFUSED')
            self.assertEqual(second['command']['status'], 409)
            self.assertEqual(second['movements']['before'], second['movements']['after'])
            self.assertEqual(ordering['final']['risk']['totals']['outstanding_krw'], winning)
            self.assertEqual(ordering['final']['risk']['reserve']['requirement_krw'], reserve)
            self.assertEqual(ordering['final']['overlay_state_digest'], report['inputs']['overlay_state_digest'])
            self.assertEqual(ordering['final']['measures']['slice_exposure_krw'], {'slice-a': 10000000})

    def test_two_beneficiaries_reserve_floors_per_advance(self):
        approve(self.service, 'sim-a', 101, 'demo-alpha-arena')
        approve(self.service, 'sim-b', 101, 'demo-beta-festival')
        self.save()
        report = self.report()
        for ordering in report['orderings']:
            risk = ordering['final']['risk']
            self.assertEqual(risk['totals']['outstanding_krw'], 202)
            self.assertEqual(risk['concentration']['hhi_permille'], 500)
            self.assertEqual(risk['reserve']['requirement_krw'], 2)  # floor(101*.015) twice
            self.assertEqual(len(risk['concentration']['beneficiaries']), 2)
        self.assertEqual(report['comparison']['differing_financial_measures'], [])
        self.assertFalse(any(r['order_sensitive'] for r in report['comparison']['outcome_variants']))

    def test_existing_partial_repayment_and_fixed_clock_full_portfolio(self):
        draw_book(self.service, 'sim-old', 'sim-committed', 10000, 'old')
        run(self.service, 'repay', 'sim-old', 'old-partial', amount=4000, sequence=1)
        tick(self.service, 'day61', 0, 61)
        approve(self.service, 'sim-a', 101, 'demo-alpha-arena')
        approve(self.service, 'sim-b', 101, 'demo-beta-festival')
        self.save()
        for ordering in self.report()['orderings']:
            risk = ordering['final']['risk']
            self.assertEqual(risk['sim_day'], 61)
            self.assertEqual(risk['totals']['outstanding_krw'], 6202)
            self.assertEqual(risk['reserve']['requirement_krw'], 1502)  # 6000*.25 + 1 + 1
            self.assertEqual({r['id']: r['outstanding_krw'] for r in risk['overdue_aging']['rows']}['1-30'], 6000)
            # F04 holds the original note face even after a partial repayment.
            self.assertEqual(ordering['final']['measures']['claim_reservations_krw']['sim-committed'], 10000)
            self.assertTrue(risk['reconciliation']['matched'])

    def test_all_two_three_four_permutations_are_isolated(self):
        for n in (2, 3, 4):
            service = CapitalService()
            self.addCleanup(service.observability.close)
            self.service = service
            ids = ['sim-' + str(i) for i in range(n)]
            for key in ids:
                approve(service, key, 100)
            self.save()
            report = self.report(ids)
            self.assertEqual([tuple(o['order']) for o in report['orderings']], list(itertools.permutations(ids)))
            for o in report['orderings']:
                self.assertEqual(o['steps'][0]['observed_state_digest'], report['inputs']['state_digest'])
                self.assertEqual(o['final']['risk']['totals']['outstanding_krw'], 100*n)
            self.assertEqual(service.risk()['totals']['outstanding_krw'], 0)

    def test_invalid_selection_fails_before_any_replay(self):
        self.shared()
        for ids, reason in (([], 'SELECTION_REQUIRES_TWO_TO_FOUR_IDS'),
                            (['sim-a'], 'SELECTION_REQUIRES_TWO_TO_FOUR_IDS'),
                            (['sim-a']*5, 'SELECTION_REQUIRES_TWO_TO_FOUR_IDS'),
                            (['sim-a', None], 'SELECTION_REQUIRES_TWO_TO_FOUR_IDS'),
                            (['sim-a', 'sim-a'], 'DUPLICATE_ADVANCE'),
                            (['sim-a', 'sim-missing'], 'UNKNOWN_ADVANCE:sim-missing')):
            with self.subTest(ids=ids), patch.object(CapitalService, 'execute', side_effect=AssertionError('no replay')):
                report = self.report(ids, 'INCOMPLETE')
                self.assertIn(reason, report['reasons'])
                self.assertEqual(report['orderings'], [])

    def test_nonapproved_and_successful_draw_are_ineligible(self):
        self.shared()
        for op in ('draw', 'cancel'):
            with self.subTest(op=op):
                if op == 'cancel':
                    # A different approved note, so this checks terminal eligibility too.
                    approve(self.service, 'sim-c', 1)
                key = 'sim-a' if op == 'draw' else 'sim-c'
                run(self.service, op, key, 'prior-' + op)
                self.save()
                with patch.object(CapitalService, 'execute', side_effect=AssertionError('no replay')):
                    self.assertIn('INELIGIBLE_ADVANCE:' + key, self.report([key, 'sim-b'], 'INCOMPLETE')['reasons'])

    def test_prior_rejected_draw_and_unpersisted_unknown_remain_eligible(self):
        approve(self.service, 'sim-a', 100, 'sim-pending')
        approve(self.service, 'sim-b', 100)
        receipt = run(self.service, 'draw', 'sim-a', 'prior-reject')
        self.assertEqual(receipt['outcome'], 'REJECTED')
        with patch.object(self.service.producer, 'apply', side_effect=TransportLost('lost-before-capture')):
            unknown = run(self.service, 'draw', 'sim-b', 'lost-before-capture')
        self.assertEqual(unknown['outcome'], 'UNKNOWN')
        self.assertNotIn('lost-before-capture', self.service.receipts)
        self.save()
        report = self.report()
        self.assertTrue(all(o['steps'][0 if o['order'][0] == 'sim-a' else 1]['command']['outcome'] == 'REJECTED'
                            for o in report['orderings']))
        self.assertIn('UNKNOWN', report['limitations'][0])
        # No persisted UNKNOWN record is invented or required in the captured book.
        self.assertNotIn('UNKNOWN', [s['receipt']['outcome'] for s in self.service.receipts.values()])

    def test_unbound_draw_uses_existing_t2_policy(self):
        approve(self.service, 'sim-a', 100, bind=False)
        approve(self.service, 'sim-b', 100)
        self.save()
        report = self.report()
        for ordering in report['orderings']:
            step = next(s for s in ordering['steps'] if s['advance_id'] == 'sim-a')
            self.assertEqual(step['command']['outcome'], 'ACCEPTED')
            self.assertEqual(step['command']['result']['credit']['settlement_gate'], 'UNBOUND')
            self.assertEqual(step['underwriting']['tier'], 'T2')
            self.assertEqual(ordering['final']['risk']['reserve']['requirement_krw'], 6)  # 5 + floor(100*.015)

    def test_legacy_maximum_id_and_sorted_input(self):
        key = 'sim-' + 'a'*60
        approve(self.service, key, 100)
        approve(self.service, 'sim-z', 100)
        self.save(legacy=True)
        left = self.report([key, 'sim-z'])
        self.assertEqual(left, self.report(['sim-z', key]))
        self.assertTrue(all(s['command']['outcome'] == 'ACCEPTED' for o in left['orderings'] for s in o['steps']))

    def test_operation_collision_and_per_clone_capacity_boundaries(self):
        self.shared()
        with patch.object(dor, 'MAX_OPERATIONS', 7), patch.object(CapitalService, 'execute', side_effect=AssertionError('no replay')):
            self.assertIn('SIMULATION_CAPACITY', self.report(status='INCOMPLETE')['reasons'])
        with patch.object(dor, 'MAX_OPERATIONS', 8):
            self.report()  # 6 receipts + 2 attempts, not 6 + 2*2
        run(self.service, 'draw', 'sim-a', 'dor-p01-s1')
        # Use an unrelated rejected command to occupy a generated ID without changing eligibility.
        approve(self.service, 'sim-c', 1)
        approve(self.service, 'sim-d', 1)
        self.save()
        with patch.object(CapitalService, 'execute', side_effect=AssertionError('no replay')):
            self.assertIn('OPERATION_ID_COLLISION', self.report(['sim-c', 'sim-d'], 'INCOMPLETE')['reasons'])

    def test_overlay_id_collision_fails_before_replay(self):
        self.shared()
        tick(self.service, 'dor-p00-s0', 0, 1)
        self.save()
        with patch.object(CapitalService, 'execute', side_effect=AssertionError('no replay')):
            self.assertIn('OPERATION_ID_COLLISION', self.report(status='INCOMPLETE')['reasons'])

    def test_missing_corrupt_and_strict_duplicate_capture(self):
        for raw in (None, b'{', b'{"format":1,"format":2}', b'{}'):
            path = self.directory / FILE_NAME
            if raw is not None:
                path.write_bytes(raw)
            report = self.report(status='INCOMPLETE')
            self.assertIn('WORKSPACE_AUDIT_FAILED', report['reasons'])
            self.assertEqual(report['orderings'], [])

    def test_persisted_inconsistency_fails_audit(self):
        self.shared()
        document = self.service.storage.load()
        document['payload']['case_fixtures']['sim-a'] = 'sim-pending'
        document['payload_sha256'] = _checksum(document['payload'])
        (self.directory / FILE_NAME).write_bytes(canonical_bytes(document))
        self.assertFalse(self.report(status='INCOMPLETE')['audit']['ok'])

    def test_repeated_api_and_cli_bytes_and_input_hashes(self):
        self.shared()
        report = self.report()
        self.assertEqual(report, self.report())
        cmd = [sys.executable, '-m', 'capital.draw_order', '--workspace', str(self.directory),
               '--advance', 'sim-b', '--advance', 'sim-a']
        one = subprocess.run(cmd, cwd=ROOT, capture_output=True)
        two = subprocess.run(cmd, cwd=ROOT, capture_output=True)
        self.assertEqual(one.returncode, 0, one.stderr)
        self.assertEqual(one.stdout, two.stdout)
        self.assertEqual(one.stdout, canonical_bytes(report)+b'\n')
        self.assertEqual(report['inputs']['workspace_sha256'], hashlib.sha256((self.directory / FILE_NAME).read_bytes()).hexdigest())
        self.assertEqual(report['inputs']['policy_inputs_digest'], dor.digest(report['inputs']['policy_inputs']))
        self.assertEqual(report['audit']['workspace'], 'CAPTURED_WORKSPACE')
        encoded = one.stdout.decode()
        self.assertNotIn('"instance_id"', encoded)
        self.assertEqual(encoded.count('"saved_at"'), 1)
        self.assertEqual(encoded.count('"saved_by_instance"'), 1)
        self.assertNotIn(str(self.directory), encoded)

    def test_cli_failure_and_argparse_exit_codes(self):
        cmd = [sys.executable, '-m', 'capital.draw_order']
        misuse = subprocess.run(cmd, cwd=ROOT, capture_output=True)
        self.assertEqual(misuse.returncode, 2)
        invalid = subprocess.run(cmd + ['--workspace', str(self.directory), '--advance', 'sim-a'], cwd=ROOT, capture_output=True)
        self.assertEqual(invalid.returncode, 1)
        self.assertEqual(json.loads(invalid.stdout)['status'], 'INCOMPLETE')

    def test_no_source_lock_network_signing_or_save(self):
        self.shared()
        with patch.object(FileWorkspace, 'open', side_effect=AssertionError('no lock')), \
             patch.object(socket.socket, 'connect', side_effect=AssertionError('no network')), \
             patch('capital.evidence._DocumentStorage.save', side_effect=AssertionError('no baseline save')), \
             patch('capital.keyset.load_dev_keyset', side_effect=AssertionError('no key')):
            self.report()

    def test_exactly_one_read_even_if_source_replaced_after_capture(self):
        self.shared()
        expected = self.report()
        real = dor.audit.audit_workspace_bytes
        reads = []
        original = Path.read_bytes
        def read(path):
            if path == self.directory / FILE_NAME:
                reads.append(path)
            return original(path)
        def replace(raw, **kwargs):
            (self.directory / FILE_NAME).write_bytes(b'replaced after capture')
            return real(raw, **kwargs)
        with patch.object(Path, 'read_bytes', read), patch.object(dor.audit, 'audit_workspace_bytes', replace):
            actual = dor.rehearse_workspace(self.directory, ['sim-a', 'sim-b'])
        self.assertEqual(actual, expected)
        self.assertEqual(len(reads), 1)

    def test_missing_policy_and_binding_failure_precede_replay(self):
        self.shared()
        for mutation in ('missing', 'bounds', 'binding'):
            def restore(document):
                service = offline_service(document)
                if mutation == 'missing':
                    del service.terms.items['reserve']
                elif mutation == 'bounds':
                    service.overlay_bounds = None
                else:
                    service.terms.version = 'incompatible'
                    # Establish an actual recorded binding first below.
                return service
            if mutation == 'binding':
                tick(self.service, 'bind-day', 0, 1)
                self.save()
            with self.subTest(mutation=mutation), patch.object(dor, 'offline_service', restore), \
                 patch.object(CapitalService, 'execute', side_effect=AssertionError('no replay')):
                self.assertEqual(self.report(status='INCOMPLETE')['orderings'], [])

    def test_policy_hash_tracks_expanded_inputs_without_forecast_gate(self):
        self.shared()
        base = self.report()['inputs']['policy_inputs_digest']
        for field in ('repayment_bounds', 'slice_policy', 'recovery_policy'):
            def restore(document):
                service = offline_service(document)
                getattr(service, field)['test_capture_marker'] = 'SIMULATED'
                return service
            with self.subTest(field=field), patch.object(dor, 'offline_service', restore):
                self.assertNotEqual(self.report()['inputs']['policy_inputs_digest'], base)
        def no_fees(document):
            service = offline_service(document)
            del service.terms.items['fees']
            return service
        with patch.object(dor, 'offline_service', no_fees):
            self.report()

    def test_policy_hash_preserves_nested_reserve_iteration_order(self):
        self.shared()
        baseline = self.report()
        def reorder(document):
            service = offline_service(document)
            value = service.terms.items['reserve']['value']
            value['provision_bps_of_outstanding'] = dict(reversed(list(value['provision_bps_of_outstanding'].items())))
            return service
        with patch.object(dor, 'offline_service', reorder):
            reordered = self.report()
        self.assertNotEqual(baseline['inputs']['policy_inputs_digest'], reordered['inputs']['policy_inputs_digest'])
        for report in (baseline, reordered):
            self.assertEqual(report, json.loads(canonical_bytes(report)))

    def test_clone_mismatch_precedes_all_commands(self):
        self.shared()
        original = dor._clone
        def mismatch(*args):
            clone = original(*args)
            clone.fixtures.profiles['sim-committed'] = 'changed'
            return clone
        with patch.object(dor, '_clone', mismatch), patch.object(CapitalService, 'execute', side_effect=AssertionError('no replay')):
            self.assertIn('CLONE_INPUTS_MISMATCH', self.report(status='INCOMPLETE')['reasons'])

    def test_selected_applicable_margin_inputs_are_required_before_replay(self):
        self.shared()
        for field in ('cure_window_days', 'advance_rate_bps_by_tier', 'beneficiary_payee_map'):
            def restore(document):
                service = offline_service(document)
                values = service.terms.items['additional_margin']['value']
                if field == 'advance_rate_bps_by_tier':
                    del values[field]['T1_COMMIT_OBSERVED']
                elif field == 'beneficiary_payee_map':
                    del values[field]['fixture-organizer']
                else:
                    del values[field]
                return service
            with self.subTest(field=field), patch.object(dor, 'offline_service', restore), \
                 patch.object(CapitalService, 'execute', side_effect=AssertionError('no replay')):
                report = self.report(status='INCOMPLETE')
                self.assertEqual(report['orderings'], [])
                self.assertIn('APPLICABLE_MARGIN_TERMS_UNUSABLE', [c['reason'] for c in report['readiness_checks']])

    def test_missing_recorded_draw_gate_is_not_fabricated(self):
        draw_book(self.service, 'sim-old', 'demo-alpha-arena', 100, 'old')
        self.shared()
        document = self.service.storage.load()
        del document['payload']['receipts']['old-draw']['receipt']['result']['credit']['settlement_gate']
        document['payload_sha256'] = _checksum(document['payload'])
        (self.directory / FILE_NAME).write_bytes(canonical_bytes(document))
        with patch.object(CapitalService, 'execute', side_effect=AssertionError('no replay')):
            report = self.report(status='INCOMPLETE')
            self.assertEqual(report['orderings'], [])
            self.assertIn('DRAW_RECEIPT_GATE_MISSING', [c['reason'] for c in report['readiness_checks']])

    def test_unknown_unexpected_and_server_error_stop_without_retry(self):
        self.shared()
        for fault in ('unknown', 'unexpected', 'server'):
            calls = []
            def execute(service, body, role):
                calls.append(body['operation_id'])
                if fault == 'unknown':
                    return {'outcome': 'UNKNOWN', 'retry_authorized': False}
                if fault == 'server':
                    raise ApiError('GATE_FAILED', 502, {'reason': 'SIMULATED'})
                raise RuntimeError('unexpected fault')
            with self.subTest(fault=fault), patch.object(CapitalService, 'execute', execute):
                report = self.report(status='INCOMPLETE')
                self.assertEqual(calls, ['dor-p00-s0', 'dor-p01-s0'])
                self.assertTrue(all(o['status'] == 'INCOMPLETE' and len(o['steps']) == 1 for o in report['orderings']))


if __name__ == '__main__':
    unittest.main()
