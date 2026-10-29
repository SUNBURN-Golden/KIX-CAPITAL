"""Opt-in fake byte preflight; LOCAL_FAKE_GATE, semantic HOLD, CAP-16 NOT_BOUND."""
from dataclasses import FrozenInstanceError
import json
import tempfile
import unittest
from unittest.mock import patch

from capital.gate_producer import (
    GateHttpProducer, PreflightRejected, load_fake_gate, make_preflighted_fake_producer,
)
from capital.compat_preflight import canonical_bytes, git_blob, sha256
from test_compat_preflight import BundleCopy
from scripts.compat_preflight import CORPUS, MANIFEST
from test_producer_port import run_producer_vectors


def make(bundle):
    return make_preflighted_fake_producer(root=bundle.root, manifest_path=MANIFEST,
                                         expected_path=bundle.expected_path)


class GatePreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bundle = BundleCopy(self.temp.name)

    def test_mismatch_prevents_constructor_start_and_first_command_post(self):
        gate = load_fake_gate().start()
        self.addCleanup(gate.close)
        expected = json.loads(self.bundle.expected_path.read_bytes())
        expected['tuple']['producer']['source_tree'] = '0' * 40
        self.bundle.expected_path.write_bytes(canonical_bytes(expected))
        # A running fake's counter stays zero even if a constructor could have used it.
        with patch('capital.gate_producer.GateHttpProducer', return_value=GateHttpProducer(gate=gate)) as constructor:
            with self.assertRaises(PreflightRejected):
                make(self.bundle)
            constructor.assert_not_called()
        self.assertEqual(gate.post_count('preflight-offer'), 0)
        with patch.object(load_fake_gate(), 'start') as start:
            with self.assertRaises(PreflightRejected):
                make(self.bundle)
            start.assert_not_called()

    def test_successful_local_vectors_keep_honest_labels(self):
        opened = []

        def factory():
            producer = make_preflighted_fake_producer(root=CORPUS / 'bundle', manifest_path=MANIFEST,
                                                     expected_path=CORPUS / 'expected.json')
            opened.append(producer)
            self.assertEqual(producer.label, 'LOCAL_FAKE_GATE')
            self.assertIs(producer.semantic_conformance, False)
            self.assertEqual(producer.preflight_report.as_dict()['adoption'], 'NOT_BOUND')
            self.assertEqual(producer.preflight_report.as_dict()['semantic_consumption'], 'HOLD')
            return producer

        try:
            run_producer_vectors(factory)
        finally:
            for producer in opened:
                producer.close()

    def test_duplicate_extension_keys_with_refreshed_hashes_prevent_construction(self):
        ref = self.bundle.manifest['source_references']['extension_profile']
        duplicate = b'{"a":1,"a":2}'
        (self.bundle.root / ref['path']).write_bytes(duplicate)
        ref.update(sha256=sha256(duplicate), gitBlob=git_blob(duplicate))
        self.bundle.save()
        # Matching file hashes, tuple, manifest digest and sidecar cannot hide duplicates.
        self.assertEqual(self.bundle.check().errors, ({'code': 'duplicate-key', 'location': 'json'},))
        with patch('capital.gate_producer.GateHttpProducer') as constructor:
            with patch.object(load_fake_gate(), 'start') as start:
                with self.assertRaises(PreflightRejected):
                    make(self.bundle)
                constructor.assert_not_called()
                start.assert_not_called()

    def test_restore_retains_inputs_and_rechecks_before_start(self):
        original = make(self.bundle)
        self.addCleanup(original.close)
        original.actor = 'SIMULATED_RESTORE'
        original.timeout = 2.0
        original.apply('offer', 'sim-a', idempotency_key='preflight-offer',
                       args={'fixture_id': 'sim-committed', 'amount': 1000}, bound_settlement_id=None)
        receipt = original.lookup('preflight-offer')
        self.assertEqual(receipt['label'], 'LOCAL_FAKE_GATE')
        self.assertEqual(receipt['binding'], 'NOT_BOUND')
        self.assertIs(receipt['semantic_conformance'], False)
        journal = original.export_journal()
        restored = original.restored(journal)
        self.addCleanup(restored.close)
        self.assertEqual(original.state_digest(), restored.state_digest())
        self.assertEqual(restored.actor, original.actor)
        self.assertEqual(restored.timeout, original.timeout)
        self.assertIs(restored._preflight_inputs, original._preflight_inputs)
        with self.assertRaises(FrozenInstanceError):
            restored._preflight_inputs.manifest_path = 'other'
        (self.bundle.root / self.bundle.manifest['sdk_output']['path']).write_bytes(b'drift')
        for producer in (original, restored):
            with patch('capital.gate_producer.GateHttpProducer') as constructor:
                with self.assertRaises(PreflightRejected):
                    producer.restored(journal)
                constructor.assert_not_called()
        self.assertEqual(original.post_count('preflight-offer'), 1)

    def test_byte_consistent_self_declared_semantics_cannot_construct_adapter(self):
        self.bundle.manifest['profile_kind'] = 'SEMANTIC_CONFORMANCE'
        self.bundle.profile['profile_kind'] = 'SEMANTIC_CONFORMANCE'
        self.bundle.profile['grants'] = 'self-declared semantic conformance'
        self.bundle.save_profile()
        report = self.bundle.check()
        self.assertTrue(report.matched, report.errors)
        self.assertEqual(report.as_dict()['semantic_consumption'], 'HOLD')
        self.assertIs(report.as_dict()['semantic_conformance'], False)
        with patch('capital.gate_producer.GateHttpProducer') as constructor:
            with self.assertRaises(PreflightRejected) as caught:
                make(self.bundle)
            self.assertEqual(caught.exception.code, 'BOOTSTRAP_REHEARSAL_ONLY')
            constructor.assert_not_called()

    def test_failed_restore_closes_its_new_owned_gate(self):
        fake = load_fake_gate()
        original = make(self.bundle)
        self.addCleanup(original.close)
        before = set(fake._OPEN)
        with self.assertRaises(Exception):
            original.restored([{'not_a_journal_record': True}])
        self.assertEqual(fake._OPEN, before)


if __name__ == '__main__':
    unittest.main()
