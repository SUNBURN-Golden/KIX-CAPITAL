"""Contract oracle sensitivity corrupts copies of observed facade traces only."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from capital import contract_invariants as inv

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/contract_invariants_check.py'


class ContractInvariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        start = time.monotonic()
        cls.table = inv.load_table()
        cls.corpus = inv.run_corpus()
        cls.trace = cls.corpus['traces'][str(inv.BASE_SEED)]
        cls.elapsed = time.monotonic() - start

    def test_table_fields_and_every_claim_passes(self):
        result = inv.run_claims(self.table, self.corpus)
        self.assertTrue(result['ok'], result)
        self.assertEqual((result['passed'], result['total']), (6, 6))
        for key, check in inv.CHECKS.items():
            for name, trace in self.corpus['traces'].items():
                with self.subTest(predicate=key, trace=name):
                    self.assertTrue(check(trace)['ok'], check(trace))

    def test_pin_consumer_block_complete(self):
        pin = self.table['pin_consumer']
        self.assertEqual(pin['note_registration'], 'PENDING_NOTE_REGISTRATION')
        self.assertEqual(pin['full_sha'], inv.PINNED_SHA)
        self.assertEqual(pin['follow_up'], 'upstream-repin-inventory-contract-invariants')
        for field in ('full_sha', 'target_path', 'consumer', 'verification', 'pin_class'):
            changed = copy.deepcopy(self.table)
            del changed['pin_consumer'][field]
            with self.subTest(field=field), self.assertRaises(inv.ClaimTableError):
                inv.validate_table(changed)

    def test_false_predicate_cannot_be_accepted_by_table_expectation(self):
        changed = copy.deepcopy(self.table)
        changed['claims'][0]['expected'] = False
        with self.assertRaises(inv.ClaimTableError):
            inv.validate_table(changed)

    def test_no_profile_or_kernel_claim(self):
        for field in ('semantic_conformance', 'upstream_kernel_executed', 'vendored'):
            self.assertIs(self.table[field], False)
        self.assertTrue(all(r['source_doc'] == inv.SOURCE_DOC for r in self.table['claims']))
        self.assertEqual(self.table['claims'][-1]['disposition'], 'DOCUMENTED_DIVERGENCE')
        self.assertIn('overlay_state_digest', self.table['claims'][-1]['divergence'])

    def test_generator_is_seeded_and_covers_required_actions(self):
        self.assertEqual(inv.generate_sequence(1), inv.generate_sequence(1))
        self.assertNotEqual(inv.generate_sequence(1), inv.generate_sequence(2))
        ops = {b['op'] for c in inv.generate_sequence(inv.BASE_SEED) for b in c['commands']}
        self.assertTrue({'offer', 'approve', 'bind_settlement', 'draw', 'repay', 'cancel', 'advance_day'} <= ops)
        self.assertTrue(any(c.get('kind') == 'concurrent' for c in self.trace['steps']))
        self.assertGreater(len(set(self.trace['instances'])), 1)
        self.assertEqual(self.trace['session_probes'], ['SESSION_CHANGED'])
        drawn = [r for s in self.trace['snapshots'] for r in s['cases'] if r['draw_id']]
        self.assertTrue(drawn)
        self.assertTrue(any(r['outstanding_exposure'] == 0 for r in drawn))

    def test_inv1_concurrent_large_fixtures(self):
        for fixture in ('sim-committed', 'demo-beta-festival', 'demo-gamma-tour'):
            trace = self.corpus['traces'][fixture]
            cell = next(c for c in trace['steps'] if c.get('kind') == 'concurrent')
            self.assertEqual(sorted(r['outcome'] for r in cell['results']), ['ACCEPTED', 'REJECTED'])
            self.assertEqual([r['error'] for r in cell['results'] if r['outcome'] == 'REJECTED'],
                             ['ADVANCE_EXCEEDS_OPEN_FACE'])
            self.assertTrue(inv.inv1_shared_face(trace)['ok'])
            if fixture.startswith('demo-'):
                self.assertGreater(trace['snapshots'][-1]['cases'][0]['amount'], 1_000_000_000)

    def test_inv1_detects_overlap(self):
        trace = copy.deepcopy(self.trace)
        trace['snapshots'][-1]['cases'][0]['reserved_open'] += 1
        self.assertFalse(inv.inv1_shared_face(trace)['ok'])
        trace['snapshots'][-1]['cases'][0]['reserved_open'] = trace['snapshots'][-1]['cases'][0]['open_face'] + 1
        self.assertFalse(inv.inv1_shared_face(trace)['ok'])

    def test_inv2_refusals_not_eviction_and_replays_still_ok(self):
        trace = self.corpus['traces']['capacity']
        probes = [c for c in trace['steps'] if c.get('capacity_probe')]
        self.assertEqual(len(probes), 6)
        self.assertTrue(all(r['error'] == 'SIMULATION_CAPACITY' and r['status'] == 409
                            for c in probes for r in c['results']))
        self.assertEqual(len(trace['snapshots'][-1]['receipt_ids']), inv.RECEIPT_BOUND)
        self.assertEqual(len(trace['snapshots'][-1]['overlay_ids']), inv.OVERLAY_BOUND)
        self.assertTrue(all(r['transport_duplicate'] for c in trace['steps'] if c.get('replay') for r in c['results']))
        self.assertEqual(len(trace['instances']), 3)

    def test_inv2_detects_eviction(self):
        trace = copy.deepcopy(self.corpus['traces']['capacity'])
        trace['snapshots'][-1]['receipt_ids'].pop()
        self.assertFalse(inv.inv2_capacity(trace)['ok'])

    def test_inv2_detects_over_bound_and_admission(self):
        trace = copy.deepcopy(self.corpus['traces']['capacity'])
        trace['snapshots'][-1]['overlay_ids'].add('extra')
        self.assertFalse(inv.inv2_capacity(trace)['ok'])
        trace = copy.deepcopy(self.corpus['traces']['capacity'])
        next(c for c in trace['steps'] if c.get('capacity_probe'))['results'][0]['status'] = 200
        self.assertFalse(inv.inv2_capacity(trace)['ok'])

    def test_inv3_detects_changed_receipt(self):
        trace = copy.deepcopy(self.trace)
        trace['reads'][-1]['bytes'] += b'changed'
        self.assertFalse(inv.inv3_first_result(trace)['ok'])

    def test_inv3_detects_changed_overlay_day(self):
        trace = copy.deepcopy(self.trace)
        read = next(r for r in reversed(trace['reads']) if r['id'] == 'tick')
        document = json.loads(read['bytes'])
        document['to_sim_day'] += 1
        read['bytes'] = inv.canonical_bytes(document)
        self.assertFalse(inv.inv3_first_result(trace)['ok'])
        trace = copy.deepcopy(self.trace)
        trace['overlay_digests'][0]['receipt'] = 'wrong'
        self.assertFalse(inv.inv3_first_result(trace)['ok'])

    def test_inv3_probes_cover_each_later_step_and_keep_original_instance(self):
        known = set()
        for cell in self.trace['steps']:
            known.update(r['id'] for r in cell['results'] if r['status'] == 200)
            for key in known:
                self.assertTrue(any(r['n'] == cell['n'] + 1 and r['id'] == key for r in self.trace['reads']))
        receipt = json.loads(self.trace['first']['draw'])
        self.assertEqual(receipt['instance_id'], self.trace['instances'][0])
        self.assertTrue(all(r['bytes'] == self.trace['first'][r['id']] for r in self.trace['reads']))

    def test_inv3_detects_missing_later_read_or_first_result(self):
        trace = copy.deepcopy(self.trace)
        trace['reads'] = [r for r in trace['reads']
                          if not (r['n'] == len(trace['steps']) and r['id'] == 'offer')]
        self.assertFalse(inv.inv3_first_result(trace)['ok'])
        trace = copy.deepcopy(self.trace)
        del trace['first']['offer']
        self.assertFalse(inv.inv3_first_result(trace)['ok'])

    def test_inv3_detects_unmarked_replay(self):
        trace = copy.deepcopy(self.trace)
        next(c for c in trace['steps'] if c.get('replay'))['results'][0]['transport_duplicate'] = False
        self.assertFalse(inv.inv3_first_result(trace)['ok'])

    def test_inv4_detects_double_capture(self):
        trace = copy.deepcopy(self.trace)
        self.assertEqual(trace['snapshots'][-1]['cases'][0]['outstanding_exposure'], 0)
        trace['snapshots'][-1]['cases'][0]['outstanding_exposure'] = 1
        self.assertFalse(inv.inv4_single_effect(trace)['ok'])

    def test_inv4_detects_replay_increase_after_partial_repayment(self):
        draw = inv.command('draw', 'partial-draw')
        trace = inv._run([
            {'commands': [inv.command('offer', 'partial-offer',
                                      fixture_id='sim-committed', amount=5000)]},
            {'commands': [inv.command('approve', 'partial-approve')]},
            {'commands': [draw]},
            {'commands': [inv.command('repay', 'partial-repay', amount=2000, sequence=1)]},
            {'kind': 'restart', 'commands': []},
            {'commands': [draw, copy.deepcopy(draw)], 'kind': 'concurrent', 'replay': True},
        ])
        balances = [s['cases'][0]['outstanding_exposure'] for s in trace['snapshots'][3:]]
        self.assertEqual(balances, [5000, 3000, 3000, 3000])
        self.assertTrue(inv.inv4_single_effect(trace)['ok'])
        self.assertTrue(all(r['transport_duplicate'] for r in trace['steps'][-1]['results']))
        trace['snapshots'][-1]['cases'][0]['outstanding_exposure'] = 5000
        result = inv.inv4_single_effect(trace)
        self.assertFalse(result['ok'])
        self.assertIn('exposure increased after draw', [v[-1] for v in result['violations']])

    def test_inv4_detects_missing_or_incomplete_initial_draw_increase(self):
        first_draw = next(i for i, snap in enumerate(self.trace['snapshots'])
                          if any(r['draw_id'] for r in snap['cases']))
        for exposure in (0, self.trace['snapshots'][first_draw]['cases'][0]['amount'] - 1):
            with self.subTest(exposure=exposure):
                trace = copy.deepcopy(self.trace)
                trace['snapshots'] = trace['snapshots'][:first_draw + 1]
                trace['snapshots'][-1]['cases'][0]['outstanding_exposure'] = exposure
                result = inv.inv4_single_effect(trace)
                self.assertFalse(result['ok'])
                self.assertIn('initial draw increase missing or incorrect',
                              [v[-1] for v in result['violations']])

    def test_inv4_detects_exposure_without_draw(self):
        trace = copy.deepcopy(self.trace)
        row = trace['snapshots'][1]['cases'][0]
        self.assertIsNone(row['draw_id'])
        row['outstanding_exposure'] = row['drawn_exposure'] = row['amount']
        self.assertFalse(inv.inv4_single_effect(trace)['ok'])

    def test_inv4_detects_concurrent_double_amount_in_first_draw(self):
        trace = copy.deepcopy(self.trace)
        row = next(r for snap in trace['snapshots'] for r in snap['cases'] if r['draw_id'])
        row['drawn_exposure'] *= 2
        row['outstanding_exposure'] *= 2
        self.assertFalse(inv.inv4_single_effect(trace)['ok'])

    def test_inv4_new_operation_after_draw_is_rejected(self):
        cell = next(c for c in self.trace['steps'] if c.get('duplicate_draw_probe'))
        self.assertEqual(cell['results'][0]['error'], 'DUPLICATE_DRAW')
        trace = copy.deepcopy(self.trace)
        next(c for c in trace['steps'] if c.get('duplicate_draw_probe'))['results'][0]['outcome'] = 'ACCEPTED'
        self.assertFalse(inv.inv4_single_effect(trace)['ok'])

    def test_inv5_detects_vanished_entry(self):
        for key in ('journal', 'overlay_ids'):
            trace = copy.deepcopy(self.trace)
            trace['snapshots'][-1][key].pop()
            self.assertFalse(inv.inv5_retained_facts(trace)['ok'], key)

    def test_inv5_detects_changed_drawn_amount_or_binding_or_case_loss(self):
        for field in ('claim_id', 'trade_id', 'currency', 'amount', 'drawn_exposure',
                      'draw_id', 'draw_indices', 'cases', 'note_status'):
            trace = copy.deepcopy(self.trace)
            snap = trace['snapshots'][-1]
            if field == 'cases':
                snap['cases'] = []
            elif field == 'draw_indices':
                snap[field].clear()
            else:
                snap['cases'][0][field] = 123
            self.assertFalse(inv.inv5_retained_facts(trace)['ok'], field)

    def test_sigkill_and_loopback_cells(self):
        if self.corpus['loopback'] != 'EXECUTED':
            self.skipTest('loopback bind unavailable: HTTP and SIGKILL not executed')
        for name in ('loopback', 'sigkill'):
            self.assertIn(name, self.corpus['traces'])
            self.assertTrue(all(fn(self.corpus['traces'][name])['ok'] for fn in inv.CHECKS.values()))
        self.assertTrue(any(c['kind'] == 'sigkill' for c in self.corpus['traces']['sigkill']['steps'] if 'kind' in c))
        self.assertIn('cr-tick-2', self.corpus['traces']['sigkill']['first'])
        self.assertEqual(self.corpus['traces']['sigkill']['snapshots'][-1]['cases'][0]['outstanding_exposure'], 30000)

    def test_check_mode_is_stable_across_runs(self):
        second = inv.run_corpus(fresh=True)
        self.assertEqual(inv.seed_digests(self.corpus), inv.seed_digests(second))
        self.assertEqual(self.table['pinned_seeds']['digests'], inv.seed_digests(second))

    def test_check_is_order_insensitive(self):
        trace = copy.deepcopy(self.trace)
        for cell in trace['steps']:
            if cell.get('kind') == 'concurrent':
                cell['results'].reverse()
        self.assertEqual(inv.trace_digest(self.trace), inv.trace_digest(trace))
        trace['steps'][0]['results'][0]['outcome'] = 'REJECTED'
        self.assertNotEqual(inv.trace_digest(self.trace), inv.trace_digest(trace))

    def test_check_detects_drift_and_writes_nothing(self):
        spec = inv._module('inv_script', SCRIPT)
        table = copy.deepcopy(self.table)
        table['pinned_seeds']['digests'][str(inv.BASE_SEED)] = 'wrong'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'table.json'
            path.write_text(json.dumps(table))
            before = path.read_bytes()
            self.assertEqual(spec.main(['--check', '--table', str(path)]), 1)
            self.assertEqual(path.read_bytes(), before)

    def test_execute_and_check_subprocesses(self):
        if not inv.loopback_available():
            self.skipTest('loopback bind unavailable')
        before = inv.TABLE.read_bytes()
        for option in ('--execute', '--check'):
            result = subprocess.run([sys.executable, str(SCRIPT), option], cwd=ROOT,
                                    text=True, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('passed=6 total=6 loopback=EXECUTED', result.stdout)
        self.assertEqual(inv.TABLE.read_bytes(), before)

    def test_script_no_mode_skips_and_seed_override_does_not_write(self):
        spec = inv._module('inv_script_skip', SCRIPT)
        self.assertEqual(spec.main([]), 0)
        before = inv.TABLE.read_bytes()
        self.assertEqual(spec.main(['--seed', '42']), 0)
        self.assertEqual(inv.TABLE.read_bytes(), before)

    def test_protocol_dir_verifies_without_writing_and_missing_needle_is_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / inv.SOURCE_DOC
            path.parent.mkdir(parents=True)
            heading = self.table['claims'][0]['section']
            text = heading + '\n' + '\n'.join(r['needle'] for r in self.table['claims'])
            path.write_text(text)
            before = path.read_bytes()
            self.assertEqual(inv.check_protocol(tmp, self.table)['status'], 'verified')
            self.assertEqual(path.read_bytes(), before)
            changed = copy.deepcopy(self.table)
            changed['claims'][0]['needle'] = 'missing needle'
            self.assertEqual(inv.check_protocol(tmp, changed)['status'], 'failed')
            path.write_text(text.replace(heading, '## wrong') + '\n' + heading)
            self.assertEqual(inv.check_protocol(tmp, self.table)['status'], 'failed')
        self.assertEqual(inv.check_protocol('/absent-invariants-checkout')['status'], 'failed')

    def test_vendor_hashes_unchanged(self):
        vendor = ROOT / 'capital/vendor'
        manifest = json.loads((vendor / 'manifest.json').read_text())
        self.assertEqual(manifest['commit'], inv.PINNED_SHA)
        self.assertEqual(len(manifest['files']), 5)
        for path, wanted in manifest['files'].items():
            self.assertEqual(hashlib.sha256((vendor / path).read_bytes()).hexdigest(), wanted)
