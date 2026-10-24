"""Pinned fault corpus for LOCAL_FAKE_GATE. Not SEMANTIC_CONFORMANCE. CAP-16 stays NOT_BOUND."""
import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.gate_faults as gate_faults
from capital.gate_producer import load_fake_gate

CORPUS = ROOT / 'tests' / 'vectors' / 'gate_faults.json'
SEAMS = ROOT / 'docs' / 'SEAMS.md'
fake_gate = load_fake_gate()


class GateFaultCorpusTests(unittest.TestCase):
    def test_corpus_matches_the_pinned_vectors(self):
        report = gate_faults.run_corpus(CORPUS)
        self.assertEqual(report['findings'], [])
        self.assertIs(report['ok'], True)
        self.assertEqual(
            set(report['cases']),
            {'accept', 'gate-5xx', 'malformed-json', 'drop-before',
             'drop-after', 'delayed-then-lost', 'idempotency-conflict'})
        self.assertEqual(fake_gate._OPEN, set())

    def test_corpus_pins_every_fault_kind_and_conflict(self):
        doc = gate_faults.load_corpus(CORPUS)
        self.assertEqual(doc['format'], 'KIX_CAPITAL_GATE_FAULTS_V1')
        self.assertEqual(doc['label'], 'LOCAL_FAKE_GATE')
        self.assertEqual(doc['mode'], 'SIMULATED')
        self.assertEqual(doc['binding'], 'NOT_BOUND')
        self.assertIs(doc['semantic_conformance'], False)
        self.assertIs(doc['funds_executed'], False)
        faults = {step['fault'] for case in doc['cases'] for step in case['steps']}
        self.assertEqual(
            faults - {None},
            {'drop-before', 'drop-after', 'timeout', 'error-5xx', 'malformed-json'})
        # accept, dropped connection, delayed-then-lost and the conflict replay
        # are all pinned with explicit expectations.
        self.assertTrue(any(
            step['expect'].get('http') == 200 and step['expect'].get('outcome') == 'ACCEPTED'
            for case in doc['cases'] for step in case['steps']))
        self.assertTrue(any(
            step['expect'].get('outcome') == 'UNKNOWN'
            and step['expect'].get('retry_authorized') is False
            for case in doc['cases'] for step in case['steps']))
        conflicts = [
            step for case in doc['cases'] for step in case['steps']
            if step['expect'].get('error') == 'IDEMPOTENCY_CONFLICT']
        self.assertTrue(conflicts)
        self.assertTrue(all(step['expect']['http'] == 409 for step in conflicts))
        self.assertTrue(any(step['post'] == 'gate' for step in conflicts))

    def test_check_exits_zero_on_match(self):
        proc = subprocess.run(
            [sys.executable, 'scripts/gate_faults.py', '--check'],
            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn('LOCAL_FAKE_GATE', proc.stdout)

    def test_check_exits_nonzero_on_drift(self):
        doc = gate_faults.load_corpus(CORPUS)
        for mutate in (
                lambda case: case['steps'][-1]['expect'].update(post_count=99),
                lambda case: case['steps'][-1]['expect'].update(lookup='REJECTED'),
                lambda case: case.update(journal_length=99)):
            changed = copy.deepcopy(doc)
            mutate(changed['cases'][-1])
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'gate_faults.json'
                path.write_text(json.dumps(changed), encoding='utf-8')
                out = io.StringIO()
                self.assertEqual(gate_faults.check(path, out=out), 1)
                self.assertIn('DRIFT', out.getvalue())

    def test_check_exits_nonzero_on_missing_or_malformed_corpus(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / 'missing.json'
            self.assertEqual(gate_faults.check(missing, out=io.StringIO()), 1)
            broken = Path(tmp) / 'broken.json'
            broken.write_text('{not json', encoding='utf-8')
            self.assertEqual(gate_faults.check(broken, out=io.StringIO()), 1)
            wrong = Path(tmp) / 'wrong.json'
            wrong.write_text(json.dumps({'format': 'OTHER'}), encoding='utf-8')
            self.assertEqual(gate_faults.check(wrong, out=io.StringIO()), 1)

    def test_lost_responses_stay_unknown_without_retry(self):
        doc = gate_faults.load_corpus(CORPUS)
        lost = [
            step for case in doc['cases'] for step in case['steps']
            if step['fault'] in {'drop-before', 'drop-after', 'timeout'}]
        self.assertEqual(len(lost), 3)
        for step in lost:
            expect = step['expect']
            # One POST, never resent: post_count stays 1 while the facade
            # reports UNKNOWN and refuses to authorize a retry.
            self.assertEqual(expect['post_count'], 1)
            self.assertEqual(expect['outcome'], 'UNKNOWN')
            self.assertIs(expect['retry_authorized'], False)
            self.assertEqual(expect['lookup'], 'UNKNOWN')

    def test_seams_keep_producer_port_not_bound(self):
        text = SEAMS.read_text(encoding='utf-8')
        row = next(line for line in text.splitlines() if line.startswith('| ProducerPort |'))
        cells = [cell.strip() for cell in row.strip().strip('|').split('|')]
        self.assertEqual(cells[4], 'NOT_BOUND')
        self.assertEqual(cells[5], 'NONE')
        source = (ROOT / 'scripts' / 'gate_faults.py').read_text(encoding='utf-8')
        self.assertIn('LOCAL_FAKE_GATE', source)
        self.assertIn('NOT_BOUND', source)
        for line in source.splitlines():
            if 'SEMANTIC_CONFORMANCE' in line:
                self.assertIn('not ', line.lower(), line)


if __name__ == '__main__':
    unittest.main()
