"""Discovered runners for the StoragePort conformance suite.

The helper module is not named test*.py, matching tests/facade_schema.py.
Passing these vectors is a local gate. It is not SEMANTIC_CONFORMANCE.
CAP-11 stays NOT_BOUND.
"""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from capital.store import FileWorkspace, InMemoryStorage

_SPEC = importlib.util.spec_from_file_location(
    'storage_conformance', Path(__file__).resolve().with_name('storage_conformance.py'))
conformance = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(conformance)


class StorageVectorTests(unittest.TestCase):
    def test_memory_factory_passes(self):
        conformance.run_storage_vectors(InMemoryStorage)

    def test_file_factory_passes(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)

        def factory():
            return FileWorkspace.open(tmp.name)

        conformance.run_storage_vectors(factory)

    def test_vectors_do_not_claim_semantic_conformance(self):
        text = Path(conformance.__file__).read_text(encoding='utf-8')
        self.assertIn('not SEMANTIC_CONFORMANCE', text)
        self.assertIn('NOT_BOUND', text)
        self.assertIn('GET and POST', text)


class CrashVectorTests(unittest.TestCase):
    def test_injected_failure_at_each_step_keeps_last_complete_file(self):
        def directory_factory():
            tmp = tempfile.TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            return tmp.name

        self.assertEqual(
            conformance.run_crash_vectors(directory_factory), conformance.CRASH_STEPS)


class ChaosSequenceTests(unittest.TestCase):
    def test_200_seeded_sequences_replay_reconcile_and_verify(self):
        directories = []

        def file_factory():
            tmp = tempfile.TemporaryDirectory()
            directories.append(tmp)
            self.addCleanup(tmp.cleanup)
            return FileWorkspace.open(tmp.name)

        seeds = conformance.run_command_sequences([InMemoryStorage, file_factory])
        if conformance.env_seed() is None:
            self.assertEqual(len(seeds), conformance.SEQUENCE_COUNT)
            self.assertEqual(seeds[0], conformance.BASE_SEED)
            self.assertEqual(seeds[-1], conformance.BASE_SEED + conformance.SEQUENCE_COUNT - 1)

    def test_env_seed_reproduces_a_single_sequence(self):
        self.assertIsNone(conformance.env_seed())
        self.assertEqual(
            conformance.sequence_seeds(),
            [conformance.BASE_SEED + i for i in range(conformance.SEQUENCE_COUNT)])
        with mock.patch.dict(os.environ, {conformance.SEED_ENV: 'nope'}):
            with self.assertRaises(ValueError) as caught:
                conformance.sequence_seeds()
            self.assertIn(conformance.SEED_ENV, str(caught.exception))
        with mock.patch.dict(os.environ, {conformance.SEED_ENV: ''}):
            with self.assertRaises(ValueError):
                conformance.env_seed()
        calls = []

        def factory():
            calls.append('new')
            return InMemoryStorage()

        with mock.patch.dict(os.environ, {conformance.SEED_ENV: '424242'}):
            self.assertEqual(conformance.env_seed(), 424242)
            self.assertEqual(conformance.sequence_seeds(), [424242])
            self.assertEqual(conformance.fuzz_stream_seed(), 424242)
            seeds = conformance.run_command_sequences([factory])
        self.assertEqual(seeds, (424242,))
        self.assertEqual(calls, ['new'])
        with self.assertRaises(AssertionError) as caught:
            conformance.fail_seed(424242, 'digest drift')
        self.assertTrue(str(caught.exception).endswith(
            'seed=424242; reproduce: CAPITAL_CHAOS_SEED=424242'))


class HttpFuzzTests(unittest.TestCase):
    def test_500_seeded_malformed_requests_never_5xx_and_server_survives(self):
        seed, count = conformance.run_http_fuzz()
        self.assertEqual(count, conformance.FUZZ_COUNT)
        if conformance.env_seed() is None:
            self.assertEqual(seed, conformance.BASE_SEED)


if __name__ == '__main__':
    unittest.main()
