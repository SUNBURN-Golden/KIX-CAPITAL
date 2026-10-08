"""Seeded demo portfolio and the instance-independent golden pin."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from capital.service import CapitalService
from capital.store import FileWorkspace

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / 'tests' / 'golden' / 'demo.json'
OPERATION_IDS = (
    'op-closed-offer', 'op-closed-approve', 'op-closed-bind', 'op-closed-draw',
    'op-closed-repay', 'op-closed-close',
    'op-defaulted-offer', 'op-defaulted-approve', 'op-defaulted-bind',
    'op-defaulted-draw', 'op-defaulted-default',
    'op-rejected-offer', 'op-rejected-reject',
    'op-cancelled-offer', 'op-cancelled-cancel',
    'op-unbound-offer', 'op-unbound-approve', 'op-unbound-draw',
    'op-pending-offer', 'op-pending-approve', 'op-pending-bind', 'op-pending-draw',
)


def _load():
    spec = importlib.util.spec_from_file_location('seed_demo', ROOT / 'scripts' / 'seed_demo.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed = _load()


class SeedDemoTests(unittest.TestCase):
    def test_fixed_operation_ids_cover_every_required_case(self):
        ids = [step[0] for step in seed.STEPS]
        self.assertEqual(ids, list(OPERATION_IDS))
        self.assertEqual([row[0] for row in seed.EXPECTED], [
            'sim-closed', 'sim-defaulted', 'sim-rejected', 'sim-cancelled',
            'sim-unbound', 'sim-pending-settlement',
        ])
        pending = [step for step in seed.STEPS if step[0] == 'op-pending-draw'][0]
        self.assertEqual(pending[4:], ('REJECTED', 'SETTLEMENT_NOT_COMMITTED'))

    def test_two_processes_share_digests_and_not_instance_id(self):
        left = seed.build_service()
        right = seed.build_service()
        self.assertNotEqual(left.instance_id, right.instance_id)
        body = seed.capture(left)
        self.assertEqual(body, seed.capture(right))
        self.assertEqual(body, json.loads(GOLDEN.read_text(encoding='utf-8')))
        self.assertNotIn('instance_id', GOLDEN.read_text(encoding='utf-8'))
        self.assertEqual(body['projection_totals']['debit'], body['projection_totals']['credit'])
        self.assertEqual(body['cases'][4]['settlement_gate'], 'UNBOUND')
        self.assertEqual(body['cases'][5]['phase'], 'APPROVED')

    def test_restored_workspace_keeps_the_golden_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(seed.main(['--workspace', tmp, '--golden', str(GOLDEN)]), 0)
            storage = FileWorkspace.open(tmp)
            try:
                restored = CapitalService(storage)
                self.assertEqual(seed.capture(restored), json.loads(GOLDEN.read_text(encoding='utf-8')))
            finally:
                storage.close()

    def test_drift_fails_without_rewriting_the_pin(self):
        original = GOLDEN.read_text(encoding='utf-8')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'demo.json'
            body = json.loads(original)
            body['state_digest'] = '0' * 64
            path.write_text(json.dumps(body), encoding='utf-8')
            before = path.read_bytes()
            code = seed.main(['--golden', str(path)])
            self.assertEqual(code, 1)
            self.assertEqual(path.read_bytes(), before)

    def test_update_golden_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'demo.json'
            self.assertEqual(seed.main(['--golden', str(path)]), 1)
            self.assertFalse(path.exists())
            self.assertEqual(seed.main(['--golden', str(path), '--update-golden']), 0)
            self.assertEqual(seed.main(['--golden', str(path)]), 0)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), json.loads(GOLDEN.read_text(encoding='utf-8')))


if __name__ == '__main__':
    unittest.main()
