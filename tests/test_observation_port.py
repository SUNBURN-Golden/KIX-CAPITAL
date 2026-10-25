"""Reusable fixture gate for ObservationPort factories; not SEMANTIC_CONFORMANCE."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from capital.observation import LocalFakeObservation
from capital.ports import ObservationPort
from capital.service import CapitalService

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / 'tests/vectors/provider_facts.json'
CORPUS_SHA256 = '2693540fc4e7572dc2a05c004af19c7dde272ad137d7c4801d765aaac0747b11'
CONTRACT_REVISION = 'e2a029d8ac3af7575888dac22fc4bf173ebec232'
CONTRACT_SHA256 = 'e640151bbdff15b67584337e6cdb6e95b2cc9c060f48dcc9de45df84f8de5345'
PROFILE = 'LOCAL_SYNTHETIC_JSON_SHA256_V1'
# Independent expectations: dropping a normalized field in the adapter must fail.
SCOPE = ('provider', 'account', 'environment', 'profile_version')
CONTENT = ('payment_key', 'order_id', 'operation', 'kind', 'amount', 'currency',
           'method', 'status', 'occurred_at', 'offset', 'api_version', 'product')


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def _safety(result):
    assert result['label'] == 'SIMULATED'
    assert result['applied'] is False
    assert result['funds_executed'] is False


def run_observation_vectors(factory, path=CORPUS):
    """Check complete pinned outputs, safety and isolation; raise on any drift."""
    table = json.loads(Path(path).read_text())
    assert table['format'] == 'KIX_CAPITAL_PROVIDER_FACTS_V1'
    assert table['label'] == 'SIMULATED' and table['semantic_conformance'] is False
    assert table['source_revision'] == CONTRACT_REVISION
    assert table['source_sha256'] == CONTRACT_SHA256
    assert table['identity_profile'] == PROFILE
    assert table['source_doc'] == 'docs/contracts/ADAPTER_EVENT_IDENTITY.md'
    assert table['cases'], 'empty corpus'
    assert len({case['name'] for case in table['cases']}) == len(table['cases'])
    for case in table['cases']:
        facts = [dict(copy.deepcopy(table['base_fact']), **copy.deepcopy(patch)) for patch in case['patches']]
        bindings = copy.deepcopy(case.get('bindings', table['bindings']))
        before = copy.deepcopy((facts, bindings))
        adapter = factory()
        assert isinstance(adapter, ObservationPort)
        output = adapter.fold(facts, bindings=bindings)
        assert _hash(output) == case['output_sha256'], case['name']
        _safety(output)
        assert output['binding_status'] == 'NOT_BOUND'
        assert output['semantic_conformance'] is False
        assert output['identity_profile'] == PROFILE
        assert output['applied_effects'] == []
        assert [item['status'] for item in output['event_items']] == case['statuses'], case['name']
        assert len(output['duplicates']) == case['duplicates'], case['name']
        assert len(output['conflicts']) == case['conflicts'], case['name']
        assert [item['delivery_index'] for item in output['duplicates']] == case['duplicate_deliveries']
        assert [item['delivery_index'] for item in output['conflicts']] == case['conflict_deliveries']
        assert len(output['deliveries']) == len(facts)
        first = {}
        for fact, delivery in zip(facts, output['deliveries']):
            key = {name: fact[name] for name in SCOPE + ('item_key',)}
            event_id = 'sim-event-' + _hash({'profile': PROFILE, 'key': key})
            assert delivery['event_item_id'] == event_id
            assert delivery['transmission'] == fact['transmission']
            first.setdefault(event_id, fact)
        for item in output['event_items']:
            fact = first[item['event_item_id']]
            assert item['scoped_key'] == {name: fact[name] for name in SCOPE + ('item_key',)}
            assert item['normalized_fact'] == {name: fact[name] for name in SCOPE + CONTENT}
            assert item['evidence_digest'] == _hash(item['normalized_fact'])
        for conflict in output['conflicts']:
            assert conflict['original'] == {name: first[conflict['event_item_id']][name]
                                            for name in SCOPE + CONTENT}
            incoming = facts[conflict['delivery_index']]
            assert conflict['incoming'] == {name: incoming[name] for name in SCOPE + CONTENT}
            assert conflict['evidence_digest'] == _hash(conflict['incoming'])
        for collection in ('event_items', 'duplicates', 'conflicts', 'deliveries'):
            for result in output[collection]:
                _safety(result)
        assert (facts, bindings) == before
        assert adapter.fold(facts, bindings=bindings) == output
        detached = copy.deepcopy(output)
        facts[0]['amount'] += 1
        bindings.clear()
        assert output == detached
        output['event_items'].clear()
        assert adapter.fold(before[0], bindings=before[1]) == detached
        empty = adapter.fold([], bindings=[])
        _safety(empty)
        assert all(empty[name] == [] for name in
                   ('event_items', 'deliveries', 'duplicates', 'conflicts', 'applied_effects'))


class ObservationTests(unittest.TestCase):
    def test_vectors(self):
        run_observation_vectors(LocalFakeObservation)

    def test_populated_state_unchanged_for_every_case(self):
        from test_overlay import draw_book, tick
        service = CapitalService()
        draw_book(service)
        tick(service, 'sim-observation-tick', 0, 1)
        def snapshot():
            return copy.deepcopy((service.machine.state_digest(), service.machine.canonical_state(),
                                  service.machine.export_journal(), service.receipts,
                                  service.overlay_state(), service.overlay_entries, len(service.receipts)))
        before = snapshot()
        self.assertTrue(service.machine.export_journal())
        self.assertTrue(service.overlay_entries)
        self.assertTrue(service.overlay_state()['overlay_state_digest'])
        class Checked(LocalFakeObservation):
            def fold(self, facts, *, bindings):
                result = super().fold(facts, bindings=bindings)
                self_test.assertEqual(snapshot(), before)
                return result
        self_test = self
        run_observation_vectors(Checked)
        self.assertEqual(snapshot(), before)

    def test_validation_and_collision(self):
        table = json.loads(CORPUS.read_text())
        fact = table['base_fact']
        for change in ({'amount': True}, {'amount': 1.5}, {'amount': -1}, {'currency': 'USD'},
                       {'item_key': ''}, {'provenance': 'WEBHOOK'}, {'offset': 9}, {'extra': 1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                LocalFakeObservation().fold([dict(fact, **change)], bindings=[])
        other = dict(fact, item_key='sim-other-item')
        with patch('capital.observation.digest', return_value='collision'), self.assertRaisesRegex(ValueError, 'collision'):
            LocalFakeObservation().fold([fact, other], bindings=[])
        bad = dict(table['bindings'][0], order_id='sim-other-order')
        with self.assertRaisesRegex(ValueError, 'inconsistent'):
            LocalFakeObservation().fold([fact], bindings=table['bindings'] + [bad])
        for facts, bindings in ((None, []), ({}, []), ([None], []), ([{}], []),
                                ([dict(fact, transmission={})], []),
                                ([dict(fact, transmission=dict(fact['transmission'], id=''))], []),
                                ([fact], None), ([fact], [{}]), ([fact], [None])):
            with self.subTest(facts=facts, bindings=bindings), self.assertRaises(ValueError):
                LocalFakeObservation().fold(facts, bindings=bindings)

    def test_key_order_and_empty_fold(self):
        fact = json.loads(CORPUS.read_text())['base_fact']
        output = LocalFakeObservation().fold([fact, dict(reversed(list(fact.items())))], bindings=[])
        self.assertEqual(len(output['event_items']), 1)
        self.assertEqual(len(output['duplicates']), 1)
        _safety(LocalFakeObservation().fold([], bindings=[]))

    def test_factory_gate_checks_complete_output(self):
        class DriftingObservation(LocalFakeObservation):
            def fold(self, facts, *, bindings):
                output = super().fold(facts, bindings=bindings)
                output['deliveries'][0]['transmission']['received_at'] = 'sim-wrong-receive'
                return output
        with self.assertRaises(AssertionError):
            run_observation_vectors(DriftingObservation)

    def test_checker_and_drift_controls(self):
        command = [sys.executable, str(ROOT / 'scripts/observation_vectors.py'), '--check']
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'drift.json'
            table = json.loads(CORPUS.read_text())
            for body in ('{', '{}', CORPUS.read_text().replace('1000', '1001'),
                         CORPUS.read_text().replace('MATCHED_FIXTURE', 'UNMATCHED')):
                path.write_text(body)
                self.assertEqual(subprocess.run(command + ['--file', str(path)], capture_output=True).returncode, 1)
            self.assertEqual(subprocess.run(command + ['--file', str(path.parent / 'missing')], capture_output=True).returncode, 1)
            table['cases'][0]['duplicates'] = 99
            path.write_text(json.dumps(table))
            with self.assertRaises(AssertionError):
                run_observation_vectors(LocalFakeObservation, path)


if __name__ == '__main__':
    unittest.main()
