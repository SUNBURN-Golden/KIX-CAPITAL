"""Synthetic recording isolation and deterministic source behavior."""

import json
import unittest

from fake_cancel_acceptance_source import FakeCancelAcceptanceSource, SyntheticCancelAcceptanceFault
from cancel_acceptance_source import InvalidCancelAcceptanceRecord, CancelAcceptanceSourceError


class CancelAcceptanceSourceTests(unittest.TestCase):
    def test_copied_recordings_fresh_documents_and_immutable_snapshots(self):
        identity = ("fixture-settlement", "fixture-source")
        document = dict(settlement_id=identity[0], source_id=identity[1], amount={"nested": [90]})
        text = json.dumps(document)
        recordings = {identity: text}
        source = FakeCancelAcceptanceSource(recordings=recordings)
        empty_calls = source.calls
        recordings[identity] = SyntheticCancelAcceptanceFault.ERROR
        recordings.clear()
        first = source.fetch(*identity)
        calls = source.calls
        first["amount"]["nested"].append(-100)
        first.pop("source_id")
        first["caller-only"] = []
        self.assertEqual(source.fetch(*identity), document)
        self.assertEqual(source.recordings, {identity: text})
        self.assertEqual(empty_calls, ())
        self.assertEqual(calls, (identity,))
        self.assertEqual(source.calls, (identity, identity))
        with self.assertRaises(TypeError):
            source.recordings[identity] = "{}"
        with self.assertRaises(AttributeError):
            source.recordings = {}
        with self.assertRaises(AttributeError):
            source.calls = ()

    def test_lookup_uses_both_identities_without_consuming_records(self):
        source = FakeCancelAcceptanceSource(recordings={
            ("s1", "m1"): '{"fixture":1}',
            ("s1", "m2"): '{"fixture":2}',
            ("s2", "m1"): '{"fixture":3}',
        })
        requests = (("s1", "m1"), ("s1", "m2"), ("s2", "m1"), ("s2", "m2"), ("s1", "m1"))
        self.assertEqual([source.fetch(*key) for key in requests],
                         [{"fixture": 1}, {"fixture": 2}, {"fixture": 3}, None, {"fixture": 1}])
        self.assertEqual(source.calls, requests)

    def test_fault_markers_raise_immediately_and_are_not_consumed(self):
        for fault in SyntheticCancelAcceptanceFault:
            with self.subTest(fault=fault):
                source = FakeCancelAcceptanceSource(recordings={("s", "m"): fault})
                for _ in range(2):
                    with self.assertRaises(CancelAcceptanceSourceError) as caught:
                        source.fetch("s", "m")
                    self.assertEqual(str(caught.exception), fault.value)
                self.assertEqual(source.calls, (("s", "m"), ("s", "m")))
                self.assertIs(source.recordings[("s", "m")], fault)

    def test_invalid_text_or_non_object_is_a_local_record_error(self):
        for text in ("{", "null", "[]", "1", '"acceptance"'):
            with self.subTest(text=text):
                source = FakeCancelAcceptanceSource(recordings={("s", "m"): text})
                with self.assertRaises(InvalidCancelAcceptanceRecord):
                    source.fetch("s", "m")
                self.assertEqual(source.calls, (("s", "m"),))

    def test_mutable_recordings_and_non_identity_keys_are_refused(self):
        for key, recording in (("s", "{}"), (("s",), "{}"), (("s", 1), "{}"),
                               (("s", "m"), {}), (("s", "m"), None)):
            with self.subTest(key=key, recording=recording):
                with self.assertRaises(TypeError):
                    FakeCancelAcceptanceSource(recordings={key: recording})
