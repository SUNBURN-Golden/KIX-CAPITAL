"""Session and fixture-forwarding coverage; lifecycle predicates have existing tests."""

import inspect
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from credit_fsm import CreditError, CreditMachine
from credit_fixture import decode_json, load_fixture
from credit_session import CreditSession
from mock_credit import PROVENANCE
from test_credit_fsm import assert_not_lending

_ROOT = Path(__file__).resolve().parents[1]
_SETTLEMENT_DIR = _ROOT / "settlement_f01_f03"
if str(_SETTLEMENT_DIR) not in sys.path:
    sys.path.insert(1, str(_SETTLEMENT_DIR))

from settlement_fsm import SettlementMachine  # noqa: E402


FIXTURES = Path(__file__).with_name("fixtures")
OPERATIONS = ("offer", "approve", "reject", "cancel", "bind_settlement", "draw",
              "repay", "close", "default", "reconcile", "view", "view_claim")
# Transcript -> (session fixture, transcript face source fixture).
JOURNEYS = {
    "lifecycle": ("committed.json", "committed.json"),
    "settlement_gates": ("committed.json", None),
    "gate": ("captured.json", "captured.json"),
    "decline": ("unbound.json", "committed.json"),
    "boundaries": ("unbound.json", "committed.json"),
}


def requests(name):
    return [json.loads(line)
            for line in (FIXTURES / (name + ".jsonl")).read_text().splitlines()]


def fixture_book(fixture_name):
    """Replay the fixture's declared setup on a fresh real SettlementMachine."""
    fixture = decode_json((FIXTURES / fixture_name).read_text())
    setup = fixture.get("settlement_setup")
    if setup is None:
        return None
    book = SettlementMachine()
    for entry in setup:
        getattr(book, entry["operation"])(
            entry["settlement_id"],
            idempotency_key=entry["idempotency_key"],
            **entry["body"])
    return book


def fixture_session(fixture_name):
    book = fixture_book(fixture_name)
    return CreditSession() if book is None else CreditSession(book)


def _view(target, name, subject):
    try:
        return getattr(target, name)(subject)
    except CreditError as error:
        return {"error": error.code}


class CreditSessionTests(unittest.TestCase):
    def test_explicit_public_signatures_match_machine_including_optional_none(self):
        for operation in OPERATIONS:
            with self.subTest(operation=operation):
                self.assertEqual(inspect.signature(getattr(CreditSession, operation)),
                                 inspect.signature(getattr(CreditMachine, operation)))
        self.assertEqual({name for name in dir(CreditSession) if not name.startswith("_")},
                         set(OPERATIONS))

    def test_each_journey_matches_direct_machine_receipts_errors_and_reads(self):
        for journey, (fixture_name, _face_source) in JOURNEYS.items():
            session = fixture_session(fixture_name)
            machine = CreditMachine(fixture_book(fixture_name))
            advances, claims = set(), set()
            for request in requests(journey):
                operation, arguments = request["operation"], request["arguments"]
                advances.add(arguments.get("advance_id"))
                claims.add(arguments.get("claim_id"))
                with self.subTest(journey=journey, operation=operation, arguments=arguments):
                    try:
                        expected = getattr(machine, operation)(**arguments)
                    except CreditError as error:
                        with self.assertRaises(CreditError) as caught:
                            getattr(session, operation)(**arguments)
                        self.assertEqual(caught.exception.code, error.code)
                    else:
                        self.assertEqual(getattr(session, operation)(**arguments), expected)
                    for advance_id in advances:
                        if advance_id is not None:
                            self.assertEqual(_view(session, "view", advance_id),
                                             _view(machine, "view", advance_id))
                    for claim_id in claims:
                        if claim_id is not None:
                            self.assertEqual(_view(session, "view_claim", claim_id),
                                             _view(machine, "view_claim", claim_id))

    def test_optional_values_and_sources_are_forwarded_without_rewriting(self):
        book = fixture_book("committed.json")
        ownership = object()
        with patch("credit_session.CreditMachine") as constructor:
            CreditSession(book, ownership)
            self.assertEqual(constructor.call_args.args, (book, ownership))
        session = CreditSession()
        face = {"synthetic": "caller-object"}
        with patch.object(session, "_machine") as machine:
            session.offer("a", idempotency_key="o", face=face, amount=10,
                          beneficiary_role="b")
            forwarded = machine.offer.call_args
            self.assertEqual(forwarded.args, ("a",))
            self.assertIsNone(forwarded.kwargs["product"])
            self.assertIs(forwarded.kwargs["face"], face)
            session.offer("a", idempotency_key="o2", face={"f": 1}, amount=10,
                          beneficiary_role="b", product="caller-value")
            self.assertEqual(machine.offer.call_args.kwargs["product"], "caller-value")
            session.repay("a", idempotency_key="r", repay_id="n", sequence=1, amount=5)
            self.assertEqual(set(machine.repay.call_args.kwargs),
                             {"idempotency_key", "repay_id", "sequence", "amount"})
            self.assertEqual(len(machine.mock_calls), 3)

    def test_transcript_faces_match_their_declared_settlement_claims(self):
        for journey, (_fixture_name, face_source) in JOURNEYS.items():
            if face_source is None:
                continue
            claim = fixture_book(face_source).view("claim-1")["claim"]
            face = next(r["arguments"]["face"] for r in requests(journey)
                        if r["operation"] == "offer")
            with self.subTest(journey=journey):
                self.assertEqual(face, claim)

    def test_no_implicit_sources_and_sessions_are_isolated(self):
        session = CreditSession()
        face = next(r["arguments"]["face"] for r in requests("lifecycle")
                    if r["operation"] == "offer")
        session.offer("adv-1", idempotency_key="o", face=face, amount=10_000,
                      beneficiary_role="b")
        session.approve("adv-1", idempotency_key="a")
        session.bind_settlement("adv-1", idempotency_key="b", settlement_id="claim-1")
        with self.assertRaises(CreditError) as caught:
            session.draw("adv-1", idempotency_key="d", draw_id="draw-1")
        self.assertEqual(caught.exception.code, "SETTLEMENT_SOURCE_REQUIRED")
        second = CreditSession()
        with self.assertRaises(CreditError) as caught:
            second.view("adv-1")
        self.assertEqual(caught.exception.code, "UNKNOWN_ADVANCE")

    def test_bound_draw_on_committed_fixture_reports_mock_gate_and_receipts(self):
        session = load_fixture(FIXTURES / "committed.json")
        face = fixture_book("committed.json").view("claim-1")["claim"]
        offered = session.offer("adv-1", idempotency_key="o", face=face, amount=80_000,
                                beneficiary_role="fixture-label")
        self.assertEqual(offered["provenance"], PROVENANCE)
        assert_not_lending(self, offered)
        self.assertEqual(session.view("adv-1")["settlement_gate"], "UNBOUND")
        session.approve("adv-1", idempotency_key="a")
        session.bind_settlement("adv-1", idempotency_key="b", settlement_id="claim-1")
        self.assertEqual(session.view("adv-1")["settlement_gate"], "BOUND")
        drawn = session.draw("adv-1", idempotency_key="d", draw_id="draw-1")
        assert_not_lending(self, drawn)
        self.assertEqual(drawn["credit"]["settlement_gate"], "MOCK_COMMIT_OBSERVED")
        self.assertIs(drawn["credit"]["mock_settlement_commit_observed"], True)
        self.assertEqual(drawn["effect"]["outstanding_exposure"], 80_000)


if __name__ == "__main__":
    unittest.main()
