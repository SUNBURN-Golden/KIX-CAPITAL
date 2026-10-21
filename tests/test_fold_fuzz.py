"""SIMULATED sequence determinism; no crash, durability or performance claim."""
import contextlib
import copy
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from capital import overlay, store
from capital.export import VOLATILE_KEYS
from capital.producer import PinnedFsmProducer
from capital.service import CapitalService, MAX_OPERATIONS

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/fold_fuzz.py'
spec = importlib.util.spec_from_file_location('fold_fuzz', SCRIPT)
fuzz = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fuzz)


def run_main(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = fuzz.main(list(args))
    return code, out.getvalue(), err.getvalue()


class FoldFuzzTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = fuzz.VECTOR.read_bytes()
        cls.corpus = json.loads(cls.raw)

    def test_fixed_prng_arithmetic_and_generator_pins(self):
        rng = fuzz.Lcg32(74810048)
        self.assertEqual([rng.next() for _ in range(6)],
                         [222238495, 1306556914, 2316144809, 3343098356, 507077827, 2055848774])
        # Independent pins fence changes to both the generator and corpus at once.
        self.assertEqual(fuzz.sha(fuzz.generate_commands(74810048)),
                         '9d87577f1fc7cf5f51d641eeeb6213af02d4260c896e156eb64e2fae45bf02eb')
        self.assertEqual(fuzz.sha(fuzz.generate_commands(74810063)),
                         '0549abc99ab8a53384790619445498bedc4fd13139da0358385f21a88bba03cd')
        for seed in (-1, True, '74810048', 2**32):
            with self.subTest(seed=seed), self.assertRaises(fuzz.FuzzError):
                fuzz.generate_commands(seed)

    def test_corpus_schema_privacy_and_workload_bounds(self):
        self.assertEqual(set(self.corpus), {'format', 'label', 'generator', 'cases'})
        self.assertEqual(self.corpus['format'], 'KIX_CAPITAL_FOLD_FUZZ_V1')
        self.assertEqual(self.corpus['label'], 'SIMULATED')
        self.assertEqual(self.corpus['generator'], {
            'version': 'LCG32-LIFECYCLE-1', 'seeds': list(range(74810048, 74810064)),
            'max_commands': 64, 'max_advances': 6})
        self.assertEqual([c['seed'] for c in self.corpus['cases']], list(range(74810048, 74810064)))

        def no_volatile(value):
            if isinstance(value, dict):
                self.assertFalse(set(value) & VOLATILE_KEYS)
                for item in value.values():
                    no_volatile(item)
            elif isinstance(value, list):
                for item in value:
                    no_volatile(item)
        no_volatile(self.corpus)
        self.assertNotIn(b'2000-01-01', self.raw)
        bounds = overlay.load_bounds()
        self.assertIsNotNone(bounds)
        for case in self.corpus['cases']:
            commands = case['commands']
            self.assertEqual(commands, fuzz.generate_commands(case['seed']))
            self.assertLessEqual(len(commands), 64)
            ids = [c['operation_id'] for c in commands]
            self.assertEqual(len(set(ids)), len(ids))
            self.assertLessEqual(sum(c['op'] != 'advance_day' for c in commands), MAX_OPERATIONS)
            advances, day = set(), 0
            for step, command in enumerate(commands, 1):
                self.assertEqual(command['operation_id'], f'ff-{case["seed"]}-{step}')
                if command['op'] == 'advance_day':
                    self.assertEqual(set(command), {'operation_id', 'op', 'from_sim_day', 'to_sim_day', 'reason'})
                    self.assertEqual(command['reason'], 'FOLD_FUZZ')
                    self.assertEqual(command['from_sim_day'], day)
                    self.assertGreater(command['to_sim_day'], day)
                    self.assertLessEqual(command['to_sim_day'] - day, bounds['max_step_days'])
                    day = command['to_sim_day']
                    self.assertLessEqual(day, bounds['SIM_DAY_MAX'])
                else:
                    self.assertEqual(set(command), {'operation_id', 'op', 'advance_id', 'args'})
                    self.assertRegex(command['advance_id'], rf'^sim-ff-{case["seed"]}-[0-5]$')
                    advances.add(command['advance_id'])
                    if command['op'] == 'offer':
                        self.assertEqual(command['args']['fixture_id'], 'sim-committed')
                        self.assertIn(command['args']['amount'], (10000, 20000, 30000))
                    elif command['op'] == 'repay':
                        self.assertEqual(command['args']['amount'], 10000)
                        self.assertIn(command['args']['sequence'], (1, 2))
                    else:
                        self.assertEqual(command['args'], {})
            self.assertEqual(len(advances), 6)
            self.assertEqual(len(case['checkpoints']), len(commands))
            for step, checkpoint in enumerate(case['checkpoints'], 1):
                self.assertEqual(set(checkpoint), {'step', 'state_digest', 'overlay_state_digest',
                                                  'envelope_sha256', 'receipts_sha256', 'overlay_receipts_sha256'})
                self.assertEqual(checkpoint['step'], step)
                for key, value in checkpoint.items():
                    if key != 'step':
                        self.assertRegex(value, r'^[a-f0-9]{64}$')

    def test_each_seed_covers_legal_f04_paths_and_interleaving(self):
        for case in self.corpus['cases']:
            producer = PinnedFsmProducer()
            covered, gates, repayments, offered = set(), set(), set(), set()
            interleaved = False
            commands = case['commands']
            self.assertEqual(commands[0]['op'], 'advance_day')
            self.assertEqual(commands[-1]['op'], 'advance_day')
            for index, command in enumerate(commands):
                op = command['op']
                if op == 'advance_day':
                    continue
                advance_id = command['advance_id']
                covered.add(op)
                if op == 'offer':
                    offered.add(advance_id)
                else:
                    view = producer.view(advance_id)
                    if op == 'draw':
                        self.assertEqual(view['phase'], 'APPROVED')
                        self.assertLessEqual(view['amount'], view['residual_unreserved'])
                    if op == 'repay':
                        self.assertEqual(view['phase'], 'DRAWN')
                        self.assertEqual(command['args']['sequence'], view['next_repayment_sequence'])
                        self.assertLessEqual(command['args']['amount'], view['outstanding_exposure'])
                        repayments.add('full' if command['args']['amount'] == view['outstanding_exposure'] else 'partial')
                producer.apply(op, advance_id, idempotency_key=command['operation_id'],
                               args=command['args'], bound_settlement_id='sim-committed')
                if op == 'draw':
                    gates.add(producer.view(advance_id)['settlement_gate'])
                if op in ('draw', 'repay'):
                    self.assertEqual(commands[index + 1]['op'], 'advance_day')
                active = [a for a in offered if not producer.view(a)['terminal']]
                interleaved |= len(active) > 1
            self.assertEqual(covered, {'offer', 'approve', 'bind_settlement', 'draw', 'repay',
                                       'close', 'default', 'reject', 'cancel', 'reconcile'})
            self.assertEqual(gates, {'UNBOUND', 'MOCK_COMMIT_OBSERVED'})
            self.assertEqual(repayments, {'partial', 'full'})
            self.assertTrue(interleaved)

    def test_checker_independent_replays_reload_all_seeds_across_hash_seeds(self):
        # Both processes run every prefix in independent FileWorkspaces, fold the
        # journals, compare raw bytes and reopen with fresh session identities.
        for hash_seed in ('1', '987654321'):
            before = {p: p.read_bytes() for base in ('capital', 'scripts', 'tests')
                      for p in (ROOT / base).rglob('*') if p.is_file()}
            process = subprocess.run([sys.executable, str(SCRIPT), '--check'], cwd=ROOT,
                                     env=dict(os.environ, PYTHONHASHSEED=hash_seed),
                                     capture_output=True, text=True, timeout=120)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertIn('ok SIMULATED: 16 seeds, 736 commands', process.stdout)
            after = {p: p.read_bytes() for base in ('capital', 'scripts', 'tests')
                     for p in (ROOT / base).rglob('*') if p.is_file()}
            self.assertEqual([str(p.relative_to(ROOT)) for p in before.keys() | after.keys()
                              if before.get(p) != after.get(p)], [],
                             'checker changed project files or import caches')

    def test_saved_receipts_accrual_and_clock_scope(self):
        commands = self.corpus['cases'][0]['commands']
        original_clock = store.datetime
        with tempfile.TemporaryDirectory() as tmp:
            checkpoints, envelopes = fuzz.replay(commands, tmp)
        self.assertIs(store.datetime, original_clock)
        self.assertEqual(checkpoints, self.corpus['cases'][0]['checkpoints'])
        document = json.loads(envelopes[-1])
        self.assertEqual(document['saved_at'], '2000-01-01T00:00:00.000000Z')
        self.assertEqual(document['saved_by_instance'], fuzz.WRITER)
        receipts = document['payload']['receipts']
        journal = document['payload']['journal']
        entries = document['overlay']['journal']
        self.assertTrue(any(e['kind'] == overlay.KIND_INTEREST and
                            e['payload']['posted_contract_krw'] > 0 for e in entries))
        for command in commands:
            if command['op'] == 'advance_day':
                self.assertNotIn(command['operation_id'], receipts)
            else:
                self.assertEqual(receipts[command['operation_id']]['receipt']['instance_id'], fuzz.WRITER)
                self.assertEqual(receipts[command['operation_id']]['fingerprint'], fuzz.sha(command))
                self.assertEqual(sum(e['idempotency_key'] == command['operation_id'] for e in journal),
                                 0 if command['op'] == 'reconcile' else 1)

    def assert_check_fails_unchanged(self, raw, detail):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'corpus.json'
            if raw is not None:
                target.write_bytes(raw)
            code, _out, error = run_main('--check', '--file', str(target))
            self.assertEqual(code, 1, error)
            self.assertIn(detail, error)
            self.assertEqual(target.read_bytes() if target.exists() else None, raw)
            self.assertEqual(list(Path(tmp).iterdir()), [] if raw is None else [target])
        self.assertEqual(fuzz.VECTOR.read_bytes(), self.raw)

    def test_each_pinned_digest_and_envelope_hash_drift_is_fatal_without_rewrite(self):
        for field in ('state_digest', 'overlay_state_digest', 'envelope_sha256',
                      'receipts_sha256', 'overlay_receipts_sha256'):
            with self.subTest(field=field):
                corpus = copy.deepcopy(self.corpus)
                corpus['cases'][0]['checkpoints'][0][field] = '0' * 64
                self.assert_check_fails_unchanged(fuzz.serialize(corpus), f'seed 74810048 checkpoints step 1.{field}')

    def test_command_order_args_schema_and_seed_drift_fail_without_rewrite(self):
        for kind in ('order', 'args', 'seed', 'private', 'generator', 'extra'):
            corpus = copy.deepcopy(self.corpus)
            case = corpus['cases'][0]
            if kind == 'order':
                case['commands'][0], case['commands'][1] = case['commands'][1], case['commands'][0]
            elif kind == 'args':
                case['commands'][1]['args']['amount'] = 1
            elif kind == 'seed':
                case['seed'] += 1
            elif kind == 'private':
                case['commands'][0]['instance_id'] = 'forbidden-session'
            elif kind == 'generator':
                corpus['generator']['version'] = 'unfixed'
            else:
                corpus['extra'] = 'unexpected'
            with self.subTest(kind=kind):
                self.assert_check_fails_unchanged(fuzz.serialize(corpus), 'drift')

    def test_missing_malformed_duplicate_and_formatting_inputs_fail_without_rewrite(self):
        for raw, detail in ((None, 'No such file'), (self.raw[:100], 'fold fuzz failed'),
                            (b'{"label":1,"label":2}', 'duplicate key'),
                            (b'{"x":NaN}', 'fold fuzz failed'), (b'[]\n', 'corpus shape'),
                            (b'\n' + self.raw, 'formatting drift')):
            with self.subTest(raw=repr(raw)[:80]):
                self.assert_check_fails_unchanged(raw, detail)

    def test_cli_misuse_exits_two(self):
        for args in ([], ['--check', '--write'], ['--unknown']):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
                fuzz.main(args)
            self.assertEqual(exc.exception.code, 2)

    def test_missing_adopted_bounds_fail_visibly(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(overlay, 'load_bounds', return_value=None):
            with self.assertRaisesRegex(fuzz.FuzzError, 'capacity NOT_BOUND'):
                fuzz.replay(self.corpus['cases'][0]['commands'], tmp)

    def test_unexpected_rejection_and_reload_receipt_drift_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            invalid = copy.deepcopy(self.corpus['cases'][0]['commands'][:2])
            invalid[1]['op'], invalid[1]['args'] = 'close', {}
            with self.assertRaisesRegex(fuzz.FuzzError, 'step 2 close: unexpected rejection'):
                fuzz.replay(invalid, tmp)
        with tempfile.TemporaryDirectory() as tmp, patch.object(CapitalService, 'operation', return_value={}):
            with self.assertRaisesRegex(fuzz.FuzzError, 'reload receipt lookup'):
                fuzz.replay(self.corpus['cases'][0]['commands'], tmp)
        self.assertIs(store.datetime.datetime, __import__('datetime').datetime)

    def test_independent_raw_byte_mismatch_is_detected(self):
        original = fuzz.replay
        calls = 0

        def altered(commands, directory):
            nonlocal calls
            checkpoints, raw = original(commands, directory)
            calls += 1
            if calls == 2:
                raw[0] += b' '
            return checkpoints, raw

        with patch.object(fuzz, 'replay', side_effect=altered):
            with self.assertRaisesRegex(fuzz.FuzzError, 'seed 74810048 envelope bytes step 1: drift'):
                fuzz.build_corpus(self.corpus)


if __name__ == '__main__':
    unittest.main()
