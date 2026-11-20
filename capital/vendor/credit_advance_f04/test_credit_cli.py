"""Subprocess journeys and JSONL stream boundaries; no lifecycle reimplementation."""

from contextlib import redirect_stdout
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from credit_cli import dispatch_request, run_requests
from credit_fixture import FixtureError, decode_json, load_fixture
from credit_session import CreditSession
from mock_credit import PROVENANCE, _canonical
from test_credit_fsm import FALSE_FLAGS, assert_not_lending
from test_credit_session import JOURNEYS, FIXTURES, requests


CLI = Path(__file__).with_name("credit_cli.py")
TRANSCRIPTS = {"lifecycle": ("committed.json", 0), "settlement_gates": ("committed.json", 1),
               "gate": ("captured.json", 1), "decline": ("unbound.json", 1),
               "boundaries": ("unbound.json", 1)}


class CreditCliTests(unittest.TestCase):
    def invoke(self, text=None, path=None, fixture=None):
        return subprocess.run(
            [sys.executable, str(CLI), "--fixture", str(fixture or FIXTURES / "unbound.json"),
             "--requests", str(path) if path else "-"],
            input=text, capture_output=True, text=True, encoding="utf-8", timeout=20,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})

    def output(self, completed, status):
        self.assertEqual(completed.returncode, status, completed.stderr + completed.stdout)
        self.assertEqual(completed.stderr, "")
        result = [decode_json(line) for line in completed.stdout.splitlines()]
        for row in result:
            self.assertEqual(row["provenance"], PROVENANCE)
            self.assertEqual(set(row) - {"operation", "provenance"},
                             {next(k for k in row if k not in ("operation", "provenance"))})
            if "receipt" in row:
                assert_not_lending(self, row["receipt"])
            elif "view" in row:
                assert_not_lending(self, row["view"])
            elif "claim" in row:
                for flag in FALSE_FLAGS:
                    self.assertIs(row["claim"][flag], False)
        return result

    def test_every_fixture_file_stdin_and_repeat_transcripts_are_identical(self):
        for name, (fixture, status) in TRANSCRIPTS.items():
            with self.subTest(name=name):
                path = FIXTURES / (name + ".jsonl")
                first = self.invoke(path=path, fixture=FIXTURES / fixture)
                rows = self.output(first, status)
                self.assertEqual(len(rows), len(path.read_text().splitlines()))
                by_stdin = self.invoke(text=path.read_text(), fixture=FIXTURES / fixture)
                self.output(by_stdin, status)
                self.assertEqual(by_stdin.stdout, first.stdout)
                repeated = self.invoke(path=path, fixture=FIXTURES / fixture)
                self.output(repeated, status)
                self.assertEqual(repeated.stdout, first.stdout)
        self.assertEqual(self.output(self.invoke(text=""), 0), [])

    def test_lifecycle_historical_receipts_gate_views_and_reconcile(self):
        rows = self.output(self.invoke(path=FIXTURES / "lifecycle.jsonl",
                                       fixture=FIXTURES / "committed.json"), 0)
        receipts = [row["receipt"] for row in rows
                    if "receipt" in row and not row["receipt"]["duplicate"]]
        self.assertEqual([receipt["applied"] for receipt in receipts],
                         ["offer", "approve", "bind_settlement", "draw", "repay",
                          "repay", "close", "reconcile"])
        self.assertEqual([receipt["credit"]["phase"] for receipt in receipts],
                         ["OFFERED", "APPROVED", "APPROVED", "DRAWN", "DRAWN",
                          "DRAWN", "CLOSED", "CLOSED"])
        self.assertEqual(rows[2]["receipt"]["credit"]["settlement_id"], "claim-1")
        self.assertEqual(rows[3]["view"]["settlement_gate"], "BOUND")
        self.assertEqual(rows[4]["receipt"]["effect"]["outstanding_exposure"], 80_000)
        self.assertEqual(rows[4]["receipt"]["credit"]["settlement_gate"],
                         "MOCK_COMMIT_OBSERVED")
        for original, replay in ((6, 7), (4, 10)):
            expected = {**rows[original]["receipt"], "duplicate": True, "applied": None}
            self.assertEqual(rows[replay]["receipt"], expected)
        self.assertEqual(rows[9]["receipt"]["credit"]["note_status"], "RELEASED")
        self.assertEqual(rows[11]["view"]["phase"], "CLOSED")
        self.assertTrue(rows[11]["view"]["terminal"])
        claim = rows[12]["claim"]
        self.assertEqual(claim["claim_id"], "claim-1")
        self.assertEqual(claim["open_face"], 100_000)
        self.assertEqual(claim["reserved_open"], 0)
        reconcile = rows[13]["receipt"]
        self.assertIs(reconcile["matched"], True)
        self.assertEqual(reconcile["entry_count"], 7)
        self.assertEqual(len(reconcile["state_digest"]), 64)

    def test_settlement_gate_refusals_retain_machine_error_codes(self):
        rows = self.output(self.invoke(path=FIXTURES / "settlement_gates.jsonl",
                                       fixture=FIXTURES / "committed.json"), 1)
        self.assertEqual([row["error"]["code"] for row in rows if "error" in row],
                         ["SETTLEMENT_AMOUNT_MISMATCH", "UNKNOWN_SETTLEMENT",
                          "SETTLEMENT_BINDING_CONFLICT", "SETTLEMENT_BINDING_CONFLICT",
                          "ILLEGAL_TRANSITION"])
        view = rows[4]["view"]
        self.assertEqual(view["phase"], "APPROVED")
        self.assertEqual(view["settlement_gate"], "BOUND")
        self.assertIs(view["mock_settlement_commit_observed"], False)

    def test_captured_gate_blocks_bound_draw_but_not_unbound(self):
        rows = self.output(self.invoke(path=FIXTURES / "gate.jsonl",
                                       fixture=FIXTURES / "captured.json"), 1)
        self.assertEqual([row["error"]["code"] for row in rows if "error" in row],
                         ["SETTLEMENT_NOT_COMMITTED", "SETTLEMENT_NOT_COMMITTED",
                          "ILLEGAL_TRANSITION"])
        self.assertEqual(rows[8]["receipt"]["credit"]["settlement_gate"], "UNBOUND")
        self.assertIs(rows[8]["receipt"]["credit"]["mock_settlement_commit_observed"], False)
        self.assertEqual(rows[10]["view"]["phase"], "APPROVED")
        self.assertEqual(rows[11]["view"]["phase"], "DRAWN")
        self.assertEqual(rows[12]["claim"]["reserved_open"], 30_000)

    def test_decline_transcript_reaches_terminal_phases(self):
        rows = self.output(self.invoke(path=FIXTURES / "decline.jsonl",
                                       fixture=FIXTURES / "unbound.json"), 1)
        self.assertEqual([row["view"]["phase"] for row in rows if "view" in row],
                         ["REJECTED", "CANCELLED", "DEFAULTED"])
        self.assertEqual(rows[10]["receipt"]["credit"]["note_status"], "NOTED")
        self.assertEqual(rows[10]["receipt"]["effect"]["outstanding_exposure"], 60_000)
        self.assertEqual(rows[12]["error"]["code"], "TERMINAL_IMMUTABLE")
        self.assertEqual(rows[13]["claim"]["reserved_open"], 60_000)

    def test_semantic_refusals_retain_machine_error_codes(self):
        rows = self.output(self.invoke(path=FIXTURES / "boundaries.jsonl",
                                       fixture=FIXTURES / "unbound.json"), 1)
        self.assertEqual(
            [row["error"]["code"] for row in rows if "error" in row],
            ["UNKNOWN_ADVANCE", "UNKNOWN_CLAIM", "UNKNOWN_ADVANCE",
             "IDEMPOTENCY_CONFLICT", "ILLEGAL_TRANSITION", "ADVANCE_BINDING_CONFLICT",
             "ADVANCE_EXCEEDS_OPEN_FACE", "CREDIT_PRODUCT_UNDEFINED",
             "REFUND_OBLIGATION_OPEN", "SETTLEMENT_FACE_FIELDS", "CURRENCY_UNSUPPORTED",
             "SETTLEMENT_FACE_NOT_MOCK", "SETTLEMENT_FACE_NOT_MOCK", "INVALID_AMOUNT",
             "INVALID_ID", "ILLEGAL_TRANSITION", "DUPLICATE_DRAW", "ILLEGAL_TRANSITION",
             "REPAYMENT_ORDER", "REPAYMENT_ORDER", "REPAYMENT_EXCEEDS_OUTSTANDING",
             "OUTSTANDING_REMAINS", "REPAY_BINDING_CONFLICT", "DEFAULT_REQUIRES_EXPOSURE",
             "TERMINAL_IMMUTABLE", "TERMINAL_IMMUTABLE", "FACE_SNAPSHOT_FROZEN",
             "TERMINAL_IMMUTABLE", "SETTLEMENT_SOURCE_REQUIRED"])
        replayed = [row for row in rows
                    if "receipt" in row and row["receipt"]["duplicate"]]
        self.assertTrue(all(row["receipt"]["applied"] is None for row in replayed))
        self.assertEqual(rows[-3]["view"]["phase"], "CLOSED")
        self.assertEqual(rows[-2]["view"]["settlement_gate"], "BOUND")
        self.assertEqual(rows[-1]["claim"]["residual_unreserved"], 100_000)

    def test_malformed_stops_without_dispatch_or_idempotency_consumption(self):
        session = load_fixture(FIXTURES / "unbound.json")
        offer, reject = requests("decline")[0], requests("decline")[1]
        malformed = copy.deepcopy(reject)
        malformed["arguments"]["extra"] = "bad"
        with patch.object(session._machine, "reject",
                          wraps=session._machine.reject) as method:
            with redirect_stdout(io.StringIO()) as output:
                code = run_requests(
                    session, [_canonical(r) for r in (offer, malformed, reject)])
            self.assertEqual(code, 2)
            method.assert_not_called()
            rows = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[-1]["error"]["type"], "FixtureError")
            self.assertEqual(session.view("adv-r")["phase"], "OFFERED")
            receipt = dispatch_request(session, reject)["receipt"]
            self.assertFalse(receipt["duplicate"])
            method.assert_called_once()

    def test_bad_stream_setup_and_io_exit_two_without_tracebacks(self):
        for text in ('\n', '{bad}\n', '{"operation":"view","arguments":{},"arguments":{}}\n',
                     '{"operation":"offer","arguments":{"face":{"x":1e9999}}}\n'):
            rows = self.output(self.invoke(text=text + _canonical(requests("decline")[0])), 2)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["error"]["type"], "FixtureError")
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing"
            self.output(self.invoke(path=missing), 2)
            self.output(self.invoke(text="", fixture=missing), 2)
            invalid = Path(directory) / "bad.jsonl"
            invalid.write_bytes(b'\xff\n')
            self.output(self.invoke(path=invalid), 2)
            fixture = Path(directory) / "bad.json"
            fixture.write_text('{"fixture_version":true}')
            self.output(self.invoke(text="", fixture=fixture), 2)
            broken = json.loads((FIXTURES / "committed.json").read_text())
            broken["settlement_setup"][0]["operation"] = "observe_statement"
            fixture.write_text(json.dumps(broken))
            rows = self.output(self.invoke(text="", fixture=fixture), 2)
            self.assertEqual(rows[0]["error"]["type"], "FixtureError")
            out_of_order = json.loads((FIXTURES / "committed.json").read_text())
            out_of_order["settlement_setup"] = out_of_order["settlement_setup"][:2]
            out_of_order["settlement_setup"][0], out_of_order["settlement_setup"][1] = (
                out_of_order["settlement_setup"][1], out_of_order["settlement_setup"][0])
            fixture.write_text(json.dumps(out_of_order))
            rows = self.output(self.invoke(text="", fixture=fixture), 2)
            self.assertEqual(rows[0]["error"]["code"], "UNKNOWN_SETTLEMENT")

    def test_strict_decoder_rejects_duplicates_nonfinite_overflow_and_bad_json(self):
        for text in ('{"x":1,"x":2}', '{"nested":{"x":1,"x":2}}',
                     '[{"x":1,"x":2}]', 'NaN', 'Infinity', '-Infinity',
                     '{"x":1e9999}', '{"x":-1e9999}', '', '[] trailing',
                     '{"x":}', '"\\ud800"', '[' * 2000):
            with self.subTest(text=text[:50]), self.assertRaises(FixtureError):
                decode_json(text)

    def test_duplicate_surrogate_keys_emit_utf8_json_errors_in_subprocess(self):
        following = (_canonical(requests("decline")[0]) + "\n").encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "duplicate.json"
            for key in ("\udc80", "\ud800"):
                encoded_key = json.dumps(key, ensure_ascii=True)
                duplicate = f'{{{encoded_key}:1,{encoded_key}:2}}'
                for location in ("request", "nested_request", "fixture"):
                    payload = ('{"nested":' + duplicate + '}'
                               if location == "nested_request" else duplicate)
                    fixture.write_text(payload, encoding="utf-8")
                    for errors in ("surrogateescape", "strict"):
                        with self.subTest(key=encoded_key, location=location, errors=errors):
                            completed = subprocess.run(
                                [sys.executable, str(CLI), "--fixture",
                                 str(fixture if location == "fixture"
                                     else FIXTURES / "unbound.json"), "--requests", "-"],
                                input=(b"" if location == "fixture"
                                       else (payload + "\n").encode("utf-8")) + following,
                                capture_output=True, timeout=20,
                                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                                     "PYTHONUTF8": "1",
                                     "PYTHONIOENCODING": f"utf-8:{errors}"})
                            self.assertEqual(completed.returncode, 2)
                            self.assertEqual(completed.stderr, b"")
                            lines = completed.stdout.decode("utf-8", errors="strict").splitlines()
                            self.assertEqual(len(lines), 1)
                            self.assertEqual(decode_json(lines[0]), {
                                "operation": None, "provenance": PROVENANCE,
                                "error": {"type": "FixtureError",
                                          "message": f"duplicate JSON key: {encoded_key}"},
                            })

    def assert_not_dispatched(self, request):
        session = CreditSession()
        with patch.object(session, "_machine") as machine:
            with self.assertRaises(FixtureError):
                dispatch_request(session, request)
            self.assertEqual(machine.mock_calls, [])

    def test_all_operation_shapes_missing_extra_arguments_and_unsupported_selectors(self):
        examples = {}
        for name in JOURNEYS:
            for request in requests(name):
                examples.setdefault(request["operation"], request)
        optional = {"offer": {"product"}}
        self.assertEqual(set(examples),
                         {"offer", "approve", "reject", "cancel", "bind_settlement",
                          "draw", "repay", "close", "default", "reconcile", "view",
                          "view_claim"})
        for operation, request in examples.items():
            for field in set(request["arguments"]) - optional.get(operation, set()):
                bad = copy.deepcopy(request)
                del bad["arguments"][field]
                with self.subTest(operation=operation, missing=field):
                    self.assert_not_dispatched(bad)
            bad = copy.deepcopy(request)
            bad["arguments"]["unexpected"] = None
            self.assert_not_dispatched(bad)
            self.assert_not_dispatched({**request, "arguments": []})
        for request in (None, [], {}, {"operation": "view"},
                        {"operation": "view", "arguments": {}, "extra": 1}):
            self.assert_not_dispatched(request)
        for operation in (None, [], {}, 1, "restore", "export_journal", "canonical_state",
                          "state_digest", "reject_unsupported", "attempt_execution",
                          "transfer", "__init__", "_machine"):
            self.assert_not_dispatched({"operation": operation, "arguments": {}})

    def test_nested_structures_and_nonjson_python_data_never_dispatch(self):
        offer = next(r for r in requests("lifecycle") if r["operation"] == "offer")
        for face in (None, [], "x", 1):
            bad = copy.deepcopy(offer)
            bad["arguments"]["face"] = face
            with self.subTest(face=face):
                self.assert_not_dispatched(bad)
        for value in (float("nan"), float("inf"), float("-inf"), (1, 2),
                      {1: "value"}, b"x", "\ud800"):
            bad = copy.deepcopy(offer)
            bad["arguments"]["face"]["opaque"] = value
            self.assert_not_dispatched(bad)

    def test_payloads_survive_canonical_roundtrip_and_optionals_forward_none(self):
        session = load_fixture(FIXTURES / "unbound.json")
        request = next(r for r in requests("decline") if r["operation"] == "offer")
        original = copy.deepcopy(request)
        result = dispatch_request(session, decode_json(_canonical(request)))
        self.assertEqual(result["provenance"], PROVENANCE)
        self.assertEqual(result["receipt"]["credit"]["phase"], "OFFERED")
        self.assertEqual(decode_json(_canonical(result)), result)
        self.assertEqual(request, original)
        machine_session = CreditSession()
        with patch.object(machine_session, "_machine") as machine:
            dispatch_request(machine_session, request)
            self.assertIsNone(machine.offer.call_args.kwargs["product"])

    def test_setup_requires_version_provenance_and_whitelisted_replay(self):
        valid = json.loads((FIXTURES / "committed.json").read_text())
        malformed = [{}, {**valid, "fixture_version": True},
                     {**valid, "fixture_version": 2},
                     {**valid, "provenance": "MOCK_SETTLEMENT_ONLY"},
                     {**valid, "extra": 1},
                     {**valid, "settlement_setup": {}},
                     {**valid, "settlement_setup": "claim-1"},
                     {**valid, "settlement_setup": [1]},
                     {**valid, "settlement_setup": [
                         {**valid["settlement_setup"][0], "extra": 1}]},
                     {**valid, "settlement_setup": [
                         {**valid["settlement_setup"][0], "body": {}}]},
                     {**valid, "settlement_setup": [
                         {**valid["settlement_setup"][0],
                          "body": {**valid["settlement_setup"][0]["body"], "extra": 1}}]}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            for fixture in malformed:
                path.write_text(json.dumps(fixture))
                with patch("credit_fixture.CreditSession") as constructor:
                    with self.assertRaises(FixtureError):
                        load_fixture(path)
                    constructor.assert_not_called()
            session = load_fixture(FIXTURES / "unbound.json")
            self.assertIs(type(session), CreditSession)


if __name__ == "__main__":
    unittest.main()
