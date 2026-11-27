"""Lifecycle checks for the in-memory F04 credit machine.

Draw and repayment races are ordered commands in one process. They are not
threads, not a bank debit, and not a lending decision.
"""

import sys
import unittest
from pathlib import Path

from credit_fsm import (
    APPROVED,
    CANCELLED,
    CLOSED,
    DEFAULTED,
    DRAWN,
    OFFERED,
    REJECTED,
    CreditError,
    CreditMachine,
)
from mock_credit import PROVENANCE, open_terms

_ROOT = Path(__file__).resolve().parents[1]
for _path in (_ROOT / "settlement_f01_f03", _ROOT / "booking_resale_admission"):
    if str(_path) not in sys.path:
        sys.path.insert(1, str(_path))

from mock_gates import OFFER_WINDOW_MS  # noqa: E402
from resale_fsm import ResaleMachine  # noqa: E402
from settlement_fsm import SettlementMachine  # noqa: E402

FALSE_FLAGS = (
    "funds_executed",
    "license_granted",
    "regulated_product",
    "collateral_perfected",
    "priority_bound",
    "disposal_controlled",
    "revenue_assigned",
    "admission_granted",
    "legal_debtor_bound",
    "bank_debit_observed",
    "external_pledge_complete",
    "durable",
    "repayment_observed",
    "interest_defined",
)

PAY = "ab" * 32
PRICE = 10_001
T0 = 1_000_000
EXPIRES = T0 + OFFER_WINDOW_MS


def codes(fn):
    try:
        fn()
    except CreditError as error:
        return error.code
    raise AssertionError("expected CreditError")


def policy():
    return {
        "kind": "PRIMARY_FEE_BPS",
        "fee_bps": 500,
        "residual_payee": "organizer",
        "fee_payee": "platform",
    }


def settlement_book(phase, gross=100_000, settlement_id="claim-1"):
    book = SettlementMachine()
    book.initiate(
        settlement_id,
        idempotency_key=f"init-{settlement_id}",
        trade_id=f"trade-{settlement_id}",
        gross=gross,
        debtor_role="fixture-merchant",
        policy=policy(),
    )
    if phase == "INITIATED":
        return book, None
    if phase == "FAILED":
        book.fail(settlement_id, idempotency_key=f"fail-{settlement_id}", reason="fixture-fail")
        return book, None
    book.authorize(settlement_id, idempotency_key=f"auth-{settlement_id}")
    book.capture(settlement_id, idempotency_key=f"cap-{settlement_id}")
    if phase == "CAPTURED":
        return book, book.view(settlement_id)["claim"]
    book.commit(
        settlement_id,
        idempotency_key=f"commit-{settlement_id}",
        movement_id=f"move-{settlement_id}",
        gross=gross,
        amount=gross - 3_000,
        fee=3_000,
        tax=0,
        held=0,
        adjustment=0,
    )
    return book, book.view(settlement_id)["claim"]


def assert_not_lending(test, body):
    test.assertEqual(body["provenance"], PROVENANCE)
    test.assertEqual(body["lifecycle_authority"], "IN_MEMORY_FSM")
    test.assertEqual(body["external_credit"], "UNSUPPORTED")
    test.assertIs(body["economic_finality_claimed"], False)
    test.assertIs(body["funds_executed"], False)
    test.assertIs(body["bank_debit_observed"], False)
    test.assertIs(body["repayment_observed"], False)
    test.assertIs(body["interest_defined"], False)
    test.assertIs(body["underwriting_executed"], False)
    test.assertIs(body["kyc_executed"], False)
    credit = body.get("credit", body)
    test.assertEqual(credit["exposure_ledger"], "MOCK_EXPOSURE")
    test.assertIs(credit["ownership_mutated"], False)
    test.assertIs(credit["ticket_ownership_authoritative"], False)
    for flag in FALSE_FLAGS:
        test.assertIs(credit[flag], False)


class CreditFsmTests(unittest.TestCase):
    def setUp(self):
        self.book, self.face = settlement_book("COMMITTED")
        self.machine = CreditMachine(self.book)

    def offer(self, advance="adv-1", amount=100_000, face=None, key="offer-1", **changes):
        body = dict(
            face=self.face if face is None else face,
            amount=amount,
            beneficiary_role="fixture-label",
            idempotency_key=key,
        )
        body.update(changes)
        idempotency_key = body.pop("idempotency_key")
        return self.machine.offer(advance, idempotency_key=idempotency_key, **body)

    def approve(self, advance="adv-1", key="approve-1", **changes):
        self.offer(advance, **changes)
        return self.machine.approve(advance, idempotency_key=key)

    def test_offer_approve_draw_repay_and_close_are_mock_ledger_only(self):
        offered = self.offer(amount=80_000)
        assert_not_lending(self, offered)
        self.assertEqual(offered["applied"], "offer")
        self.assertFalse(offered["duplicate"])
        self.assertEqual(offered["credit"]["phase"], OFFERED)
        self.assertEqual(offered["credit"]["outstanding_exposure"], 0)
        self.assertIsNone(offered["credit"]["note_status"])
        self.assertEqual(offered["credit"]["settlement_gate"], "UNBOUND")
        self.assertEqual(offered["credit"]["confirmed_cash_on_face"], 97_000)
        self.assertEqual(offered["credit"]["open_face"], 100_000)
        self.assertEqual(offered["credit"]["recovery_due_on_face"], 0)

        approved = self.machine.approve("adv-1", idempotency_key="approve-1")
        self.assertEqual(approved["credit"]["phase"], APPROVED)
        self.assertIs(approved["credit"]["underwriting_executed"], False)
        self.assertEqual(approved["credit"]["reserved_open"], 0)

        drawn = self.machine.draw("adv-1", idempotency_key="draw-1", draw_id="draw-1")
        self.assertEqual(drawn["applied"], "draw")
        self.assertEqual(drawn["effect"]["outstanding_exposure"], 80_000)
        view = drawn["credit"]
        self.assertEqual(view["phase"], DRAWN)
        self.assertEqual(view["note_status"], "NOTED")
        self.assertEqual(view["reserved_open"], 80_000)
        self.assertEqual(view["residual_unreserved"], 20_000)
        self.assertEqual(view["outstanding_exposure"], 80_000)
        self.assertEqual(view["settlement_gate"], "UNBOUND")
        self.assertIs(view["mock_settlement_commit_observed"], False)
        assert_not_lending(self, drawn)

        partial = self.machine.repay(
            "adv-1",
            idempotency_key="repay-1",
            repay_id="repay-1",
            sequence=1,
            amount=30_000,
        )
        self.assertEqual(partial["credit"]["phase"], DRAWN)
        self.assertEqual(partial["credit"]["outstanding_exposure"], 50_000)
        self.assertEqual(partial["credit"]["repaid_exposure"], 30_000)
        self.assertEqual(partial["credit"]["reserved_open"], 80_000)
        self.assertEqual(partial["credit"]["next_repayment_sequence"], 2)
        self.assertIs(partial["credit"]["repayment_observed"], False)
        self.assertEqual(partial["credit"]["note_status"], "NOTED")

        rest = self.machine.repay(
            "adv-1",
            idempotency_key="repay-2",
            repay_id="repay-2",
            sequence=2,
            amount=50_000,
        )
        self.assertEqual(rest["credit"]["outstanding_exposure"], 0)
        self.assertEqual(rest["credit"]["phase"], DRAWN)
        self.assertIsNone(rest["credit"]["next_repayment_sequence"])

        closed = self.machine.close("adv-1", idempotency_key="close-1")
        self.assertEqual(closed["credit"]["phase"], CLOSED)
        self.assertTrue(closed["credit"]["terminal"])
        self.assertEqual(closed["credit"]["note_status"], "RELEASED")
        self.assertEqual(closed["credit"]["reserved_open"], 0)
        self.assertEqual(closed["credit"]["residual_unreserved"], 100_000)
        self.assertIs(closed["credit"]["repayment_observed"], False)
        self.assertIs(closed["credit"]["funds_executed"], False)
        ceiling = self.machine.view_claim("claim-1")
        self.assertEqual(ceiling["reserved_open"], 0)
        self.assertEqual(ceiling["residual_unreserved"], 100_000)
        self.assertEqual(ceiling["provenance"], PROVENANCE)
        self.assertIs(ceiling["repayment_observed"], False)

    def test_same_draw_and_repay_notes_do_not_apply_twice(self):
        self.approve(amount=40_000)
        first = self.machine.draw("adv-1", idempotency_key="draw-1", draw_id="draw-1")
        again = self.machine.draw("adv-1", idempotency_key="draw-1", draw_id="draw-1")
        self.assertTrue(again["duplicate"])
        self.assertIsNone(again["applied"])
        self.assertEqual(again["credit"], first["credit"])
        self.assertEqual(self.machine.view("adv-1")["accepted_entries"], 3)
        self.assertEqual(
            codes(lambda: self.machine.draw("adv-1", idempotency_key="draw-1", draw_id="other-draw")),
            "IDEMPOTENCY_CONFLICT",
        )
        other_key = self.machine.draw("adv-1", idempotency_key="draw-2", draw_id="draw-1")
        self.assertTrue(other_key["duplicate"])
        self.assertEqual(self.machine.view("adv-1")["outstanding_exposure"], 40_000)
        self.assertEqual(self.machine.view("adv-1")["accepted_entries"], 3)
        self.assertEqual(
            codes(lambda: self.machine.draw("adv-1", idempotency_key="draw-3", draw_id="draw-9")),
            "DUPLICATE_DRAW",
        )
        self.assertEqual(self.machine.view("adv-1")["phase"], DRAWN)
        self.assertEqual(self.machine.view("adv-1")["outstanding_exposure"], 40_000)

        paid = self.machine.repay(
            "adv-1",
            idempotency_key="repay-1",
            repay_id="repay-1",
            sequence=1,
            amount=10_000,
        )
        replay = self.machine.repay(
            "adv-1",
            idempotency_key="repay-1",
            repay_id="repay-1",
            sequence=1,
            amount=10_000,
        )
        self.assertTrue(replay["duplicate"])
        self.assertEqual(replay["credit"]["outstanding_exposure"], paid["credit"]["outstanding_exposure"])
        echoed = self.machine.repay(
            "adv-1",
            idempotency_key="repay-1b",
            repay_id="repay-1",
            sequence=1,
            amount=10_000,
        )
        self.assertTrue(echoed["duplicate"])
        self.assertEqual(self.machine.view("adv-1")["outstanding_exposure"], 30_000)
        self.assertEqual(self.machine.view("adv-1")["repaid_exposure"], 10_000)
        self.assertEqual(
            codes(lambda: self.machine.repay(
                "adv-1",
                idempotency_key="repay-1c",
                repay_id="repay-1",
                sequence=1,
                amount=11_000,
            )),
            "REPAY_BINDING_CONFLICT",
        )
        self.assertEqual(self.machine.view("adv-1")["outstanding_exposure"], 30_000)

    def test_repayment_order_partial_and_double_application(self):
        self.approve(amount=50_000)
        self.machine.draw("adv-1", idempotency_key="draw-1", draw_id="draw-1")
        self.assertEqual(
            codes(lambda: self.machine.repay(
                "adv-1",
                idempotency_key="skip",
                repay_id="repay-2",
                sequence=2,
                amount=1,
            )),
            "REPAYMENT_ORDER",
        )
        self.assertEqual(
            codes(lambda: self.machine.repay(
                "adv-1",
                idempotency_key="zero-seq",
                repay_id="repay-0",
                sequence=0,
                amount=1,
            )),
            "REPAYMENT_ORDER",
        )
        self.assertEqual(
            codes(lambda: self.machine.repay(
                "adv-1",
                idempotency_key="bool-seq",
                repay_id="repay-b",
                sequence=True,
                amount=1,
            )),
            "REPAYMENT_ORDER",
        )
        self.machine.repay(
            "adv-1",
            idempotency_key="repay-1",
            repay_id="repay-1",
            sequence=1,
            amount=20_000,
        )
        self.assertEqual(
            codes(lambda: self.machine.repay(
                "adv-1",
                idempotency_key="repay-again",
                repay_id="repay-9",
                sequence=1,
                amount=1,
            )),
            "REPAYMENT_ORDER",
        )
        self.assertEqual(
            codes(lambda: self.machine.repay(
                "adv-1",
                idempotency_key="too-much",
                repay_id="repay-2",
                sequence=2,
                amount=30_001,
            )),
            "REPAYMENT_EXCEEDS_OUTSTANDING",
        )
        self.assertEqual(self.machine.view("adv-1")["outstanding_exposure"], 30_000)
        self.assertEqual(self.machine.view("adv-1")["reserved_open"], 50_000)
        self.machine.repay(
            "adv-1",
            idempotency_key="repay-2",
            repay_id="repay-2",
            sequence=2,
            amount=30_000,
        )
        self.assertEqual(
            codes(lambda: self.machine.repay(
                "adv-1",
                idempotency_key="repay-3",
                repay_id="repay-3",
                sequence=3,
                amount=1,
            )),
            "REPAYMENT_EXCEEDS_OUTSTANDING",
        )
        self.machine.repay(
            "adv-1",
            idempotency_key="repay-2",
            repay_id="repay-2",
            sequence=2,
            amount=30_000,
        )
        self.assertEqual(
            codes(lambda: self.machine.default("adv-1", idempotency_key="default-0", reason="fixture-default")),
            "DEFAULT_REQUIRES_EXPOSURE",
        )
        closed = self.machine.close("adv-1", idempotency_key="close-1")
        self.assertEqual(closed["credit"]["phase"], CLOSED)
        self.assertEqual(
            codes(lambda: self.machine.repay(
                "adv-1",
                idempotency_key="repay-after",
                repay_id="repay-4",
                sequence=3,
                amount=1,
            )),
            "TERMINAL_IMMUTABLE",
        )

    def test_close_rejects_remaining_exposure_before_release(self):
        self.approve(amount=25_000)
        self.machine.draw("adv-1", idempotency_key="draw-1", draw_id="draw-1")
        self.machine.repay(
            "adv-1",
            idempotency_key="repay-1",
            repay_id="repay-1",
            sequence=1,
            amount=24_000,
        )
        self.assertEqual(
            codes(lambda: self.machine.close("adv-1", idempotency_key="close-early")),
            "OUTSTANDING_REMAINS",
        )
        self.assertEqual(self.machine.view("adv-1")["phase"], DRAWN)
        self.assertEqual(self.machine.view("adv-1")["note_status"], "NOTED")
        self.assertEqual(self.machine.view("adv-1")["reserved_open"], 25_000)
        self.assertEqual(
            codes(lambda: self.machine.close("adv-1", idempotency_key="close-early")),
            "OUTSTANDING_REMAINS",
        )

    def test_bound_draw_waits_for_mock_commit_and_does_not_claim_finality(self):
        captured, face = settlement_book("CAPTURED")
        settlement_before = captured.canonical_state()
        machine = CreditMachine(captured)
        machine.offer(
            "adv-1",
            idempotency_key="offer-1",
            face=face,
            amount=10_000,
            beneficiary_role="fixture-label",
        )
        machine.approve("adv-1", idempotency_key="approve-1")
        machine.bind_settlement("adv-1", idempotency_key="bind-1", settlement_id="claim-1")
        self.assertEqual(machine.view("adv-1")["settlement_gate"], "BOUND")
        self.assertEqual(
            codes(lambda: machine.bind_settlement("adv-1", idempotency_key="bind-2", settlement_id="claim-1")),
            "ILLEGAL_TRANSITION",
        )
        self.assertEqual(
            codes(lambda: machine.bind_settlement("adv-1", idempotency_key="bind-3", settlement_id="other-claim")),
            "SETTLEMENT_BINDING_CONFLICT",
        )
        self.assertEqual(
            codes(lambda: machine.draw("adv-1", idempotency_key="draw-early", draw_id="draw-1")),
            "SETTLEMENT_NOT_COMMITTED",
        )
        self.assertEqual(machine.view("adv-1")["phase"], APPROVED)
        self.assertEqual(machine.view("adv-1")["outstanding_exposure"], 0)
        self.assertIsNone(machine.view("adv-1")["note_status"])
        self.assertEqual(captured.canonical_state(), settlement_before)
        self.assertEqual(
            codes(lambda: machine.draw("adv-1", idempotency_key="draw-early", draw_id="draw-1")),
            "SETTLEMENT_NOT_COMMITTED",
        )

        captured.commit(
            "claim-1",
            idempotency_key="commit-claim-1",
            movement_id="move-claim-1",
            gross=100_000,
            amount=97_000,
            fee=3_000,
            tax=0,
            held=0,
            adjustment=0,
        )
        settlement_after_commit = captured.canonical_state()
        drawn = machine.draw("adv-1", idempotency_key="draw-1", draw_id="draw-1")
        assert_not_lending(self, drawn)
        self.assertEqual(drawn["credit"]["phase"], DRAWN)
        self.assertTrue(drawn["credit"]["mock_settlement_commit_observed"])
        self.assertEqual(drawn["credit"]["settlement_gate"], "MOCK_COMMIT_OBSERVED")
        self.assertEqual(drawn["credit"]["open_face"], 100_000)
        self.assertEqual(drawn["credit"]["confirmed_cash_on_face"], 0)
        self.assertEqual(captured.canonical_state(), settlement_after_commit)
        self.assertIs(captured.view("claim-1")["funds_executed"], False)
        self.assertIs(captured.view("claim-1")["bank_debit_observed"], False)

        failed, _ignored = settlement_book("FAILED")
        rejected = CreditMachine(failed)
        rejected.offer(
            "adv-f",
            idempotency_key="offer-f",
            face=face,
            amount=1,
            beneficiary_role="fixture-label",
        )
        rejected.approve("adv-f", idempotency_key="approve-f")
        rejected.bind_settlement("adv-f", idempotency_key="bind-f", settlement_id="claim-1")
        self.assertEqual(
            codes(lambda: rejected.draw("adv-f", idempotency_key="draw-f", draw_id="draw-f")),
            "SETTLEMENT_NOT_COMMITTED",
        )

        forged = dict(self.book.view("claim-1"))
        forged["economic_finality_claimed"] = True

        class Flagged:
            def view(self, _settlement_id):
                return forged

        flagged = CreditMachine(Flagged())
        flagged.offer(
            "adv-flag",
            idempotency_key="offer-flag",
            face=self.face,
            amount=1,
            beneficiary_role="fixture-label",
        )
        flagged.approve("adv-flag", idempotency_key="approve-flag")
        flagged.bind_settlement("adv-flag", idempotency_key="bind-flag", settlement_id="claim-1")
        self.assertEqual(
            codes(lambda: flagged.draw("adv-flag", idempotency_key="draw-flag", draw_id="draw-flag")),
            "SETTLEMENT_VIEW_REJECTED",
        )
        self.assertEqual(flagged.view("adv-flag")["outstanding_exposure"], 0)

        debited = dict(self.book.view("claim-1"))
        debited["bank_debit_observed"] = True

        class Debited:
            def view(self, _settlement_id):
                return debited

        debit_machine = CreditMachine(Debited())
        debit_machine.offer(
            "adv-debit",
            idempotency_key="offer-debit",
            face=self.face,
            amount=1,
            beneficiary_role="fixture-label",
        )
        debit_machine.approve("adv-debit", idempotency_key="approve-debit")
        debit_machine.bind_settlement("adv-debit", idempotency_key="bind-debit", settlement_id="claim-1")
        self.assertEqual(
            codes(lambda: debit_machine.draw("adv-debit", idempotency_key="draw-debit", draw_id="draw-debit")),
            "SETTLEMENT_VIEW_REJECTED",
        )

        mismatched = dict(self.book.view("claim-1"))
        mismatched["gross"] = 1

        class Mismatched:
            def view(self, _settlement_id):
                return mismatched

        mismatch_machine = CreditMachine(Mismatched())
        mismatch_machine.offer(
            "adv-mismatch",
            idempotency_key="offer-mismatch",
            face=self.face,
            amount=1,
            beneficiary_role="fixture-label",
        )
        mismatch_machine.approve("adv-mismatch", idempotency_key="approve-mismatch")
        mismatch_machine.bind_settlement(
            "adv-mismatch",
            idempotency_key="bind-mismatch",
            settlement_id="claim-1",
        )
        self.assertEqual(
            codes(lambda: mismatch_machine.draw(
                "adv-mismatch",
                idempotency_key="draw-mismatch",
                draw_id="draw-mismatch",
            )),
            "SETTLEMENT_AMOUNT_MISMATCH",
        )
        self.assertEqual(mismatch_machine.view("adv-mismatch")["outstanding_exposure"], 0)

    def test_reconcile_replays_the_journal_without_a_second_draw(self):
        self.approve(amount=15_000)
        self.machine.bind_settlement("adv-1", idempotency_key="bind-1", settlement_id="claim-1")
        self.machine.draw("adv-1", idempotency_key="draw-1", draw_id="draw-1")
        self.machine.repay(
            "adv-1",
            idempotency_key="repay-1",
            repay_id="repay-1",
            sequence=1,
            amount=5_000,
        )
        digest = self.machine.state_digest()
        journal = self.machine.export_journal()
        reconciled = self.machine.reconcile("adv-1", idempotency_key="recon-1")
        self.assertTrue(reconciled["matched"])
        self.assertEqual(reconciled["state_digest"], digest)
        self.assertIs(reconciled["economic_finality_claimed"], False)
        self.assertEqual(self.machine.state_digest(), digest)
        self.assertEqual(len(self.machine.export_journal()), len(journal))
        again = self.machine.reconcile("adv-1", idempotency_key="recon-1")
        self.assertTrue(again["duplicate"])
        self.assertEqual(self.machine.state_digest(), digest)

        restored = CreditMachine.restore(journal, settlement_source=self.book)
        self.assertEqual(restored.canonical_state(), self.machine.canonical_state())
        self.assertEqual(restored.state_digest(), digest)
        replay = restored.draw("adv-1", idempotency_key="draw-1", draw_id="draw-1")
        self.assertTrue(replay["duplicate"])
        self.assertEqual(restored.view("adv-1")["outstanding_exposure"], 10_000)
        self.assertEqual(restored.view("adv-1")["repaid_exposure"], 5_000)
        self.assertEqual(
            codes(lambda: CreditMachine.restore(journal)),
            "SETTLEMENT_SOURCE_REQUIRED",
        )
        self.assertEqual(codes(lambda: CreditMachine.restore("nope")), "INVALID_JOURNAL")
        self.assertEqual(codes(lambda: CreditMachine.restore([{"op": "draw"}])), "INVALID_JOURNAL")

    def test_limit_race_is_ordered_and_cash_is_not_capacity(self):
        self.offer("held", amount=70_000, key="offer-held")
        self.offer("late", amount=40_000, key="offer-late")
        self.machine.approve("held", idempotency_key="approve-held")
        self.machine.approve("late", idempotency_key="approve-late")
        first = self.machine.draw("held", idempotency_key="draw-held", draw_id="draw-held")
        self.assertEqual(first["credit"]["reserved_open"], 70_000)
        self.assertEqual(first["credit"]["confirmed_cash_on_face"], 97_000)
        self.assertEqual(first["credit"]["open_face"], 100_000)
        self.assertEqual(
            codes(lambda: self.machine.draw("late", idempotency_key="draw-late", draw_id="draw-late")),
            "ADVANCE_EXCEEDS_OPEN_FACE",
        )
        self.assertEqual(self.machine.view("late")["phase"], APPROVED)
        self.assertEqual(self.machine.view("late")["outstanding_exposure"], 0)

        self.offer("fit", amount=30_000, key="offer-fit")
        self.machine.approve("fit", idempotency_key="approve-fit")
        fitted = self.machine.draw("fit", idempotency_key="draw-fit", draw_id="draw-fit")
        self.assertEqual(fitted["credit"]["reserved_open"], 100_000)
        self.assertEqual(fitted["credit"]["residual_unreserved"], 0)
        self.machine.repay(
            "fit",
            idempotency_key="repay-fit",
            repay_id="repay-fit",
            sequence=1,
            amount=10_000,
        )
        self.assertEqual(self.machine.view("late")["reserved_open"], 100_000)
        self.assertEqual(
            codes(lambda: self.machine.draw("late", idempotency_key="draw-late-2", draw_id="draw-late")),
            "ADVANCE_EXCEEDS_OPEN_FACE",
        )
        self.machine.repay(
            "fit",
            idempotency_key="repay-fit-2",
            repay_id="repay-fit-2",
            sequence=2,
            amount=20_000,
        )
        self.machine.close("fit", idempotency_key="close-fit")
        self.assertEqual(self.machine.view("held")["reserved_open"], 70_000)
        self.assertEqual(
            codes(lambda: self.machine.draw("late", idempotency_key="draw-late-3", draw_id="draw-late")),
            "ADVANCE_EXCEEDS_OPEN_FACE",
        )
        self.machine.repay(
            "held",
            idempotency_key="repay-held",
            repay_id="repay-held",
            sequence=1,
            amount=70_000,
        )
        self.machine.close("held", idempotency_key="close-held")
        drawn_late = self.machine.draw("late", idempotency_key="draw-late-4", draw_id="draw-late")
        self.assertEqual(drawn_late["credit"]["phase"], DRAWN)
        self.assertEqual(drawn_late["credit"]["reserved_open"], 40_000)
        self.assertEqual(drawn_late["credit"]["outstanding_exposure"], 40_000)
        self.offer("overflow", amount=70_000, key="offer-overflow")
        self.machine.approve("overflow", idempotency_key="approve-overflow")
        self.assertEqual(
            codes(lambda: self.machine.draw("overflow", idempotency_key="draw-overflow", draw_id="draw-overflow")),
            "ADVANCE_EXCEEDS_OPEN_FACE",
        )

    def test_default_keeps_the_reservation_and_does_not_foreclose(self):
        self.approve(amount=70_000)
        self.machine.draw("adv-1", idempotency_key="draw-1", draw_id="draw-1")
        self.machine.repay(
            "adv-1",
            idempotency_key="repay-1",
            repay_id="repay-1",
            sequence=1,
            amount=20_000,
        )
        defaulted = self.machine.default("adv-1", idempotency_key="default-1", reason="fixture-unpaid")
        self.assertEqual(defaulted["credit"]["phase"], DEFAULTED)
        self.assertTrue(defaulted["credit"]["terminal"])
        self.assertEqual(defaulted["credit"]["outstanding_exposure"], 50_000)
        self.assertEqual(defaulted["credit"]["note_status"], "NOTED")
        self.assertEqual(defaulted["credit"]["reserved_open"], 70_000)
        self.assertEqual(defaulted["credit"]["default_reason"], "fixture-unpaid")
        self.assertIs(defaulted["credit"]["repayment_observed"], False)
        self.assertIs(defaulted["credit"]["collateral_perfected"], False)
        self.assertIs(defaulted["credit"]["priority_bound"], False)
        self.assertEqual(
            codes(lambda: self.machine.close("adv-1", idempotency_key="close-1")),
            "TERMINAL_IMMUTABLE",
        )
        self.assertEqual(
            codes(lambda: self.machine.repay(
                "adv-1",
                idempotency_key="repay-2",
                repay_id="repay-2",
                sequence=2,
                amount=1,
            )),
            "TERMINAL_IMMUTABLE",
        )
        self.offer("other", amount=40_000, key="offer-other")
        self.machine.approve("other", idempotency_key="approve-other")
        self.assertEqual(
            codes(lambda: self.machine.draw("other", idempotency_key="draw-other", draw_id="draw-other")),
            "ADVANCE_EXCEEDS_OPEN_FACE",
        )
        digest = self.machine.state_digest()
        self.assertEqual(codes(lambda: self.machine.reject_unsupported("FORECLOSE")), "CREDIT_PRODUCT_UNDEFINED")
        self.assertEqual(self.machine.state_digest(), digest)
        self.assertEqual(self.machine.view("adv-1")["phase"], DEFAULTED)

    def test_cancel_and_reject_are_terminal_before_exposure(self):
        self.offer()
        rejected = self.machine.reject("adv-1", idempotency_key="reject-1", reason="fixture-reject")
        self.assertEqual(rejected["credit"]["phase"], REJECTED)
        self.assertIs(rejected["credit"]["underwriting_executed"], False)
        self.assertEqual(
            codes(lambda: self.machine.approve("adv-1", idempotency_key="approve-late")),
            "TERMINAL_IMMUTABLE",
        )
        self.assertEqual(codes(lambda: self.machine.view_claim("claim-1")), "UNKNOWN_CLAIM")

        self.offer("adv-2", key="offer-2")
        self.machine.approve("adv-2", idempotency_key="approve-2")
        cancelled = self.machine.cancel("adv-2", idempotency_key="cancel-2", reason="fixture-cancel")
        self.assertEqual(cancelled["credit"]["phase"], CANCELLED)
        self.assertIsNone(cancelled["credit"]["note_status"])
        self.assertEqual(
            codes(lambda: self.machine.draw("adv-2", idempotency_key="draw-2", draw_id="draw-2")),
            "TERMINAL_IMMUTABLE",
        )
        self.offer("adv-3", amount=100_000, key="offer-3")
        self.machine.approve("adv-3", idempotency_key="approve-3")
        drawn = self.machine.draw("adv-3", idempotency_key="draw-3", draw_id="draw-3")
        self.assertEqual(drawn["credit"]["reserved_open"], 100_000)
        self.assertEqual(
            codes(lambda: self.machine.cancel("adv-3", idempotency_key="cancel-3", reason="too-late")),
            "ILLEGAL_TRANSITION",
        )
        self.assertEqual(self.machine.view("adv-3")["phase"], DRAWN)

    def test_unsupported_product_and_real_funds_do_not_change_state(self):
        face = self.face
        self.assertEqual(
            codes(lambda: self.machine.offer(
                "adv-1",
                idempotency_key="offer-product",
                face=face,
                amount=1,
                beneficiary_role="fixture-label",
                product={},
            )),
            "CREDIT_PRODUCT_UNDEFINED",
        )
        self.assertEqual(
            codes(lambda: self.machine.offer(
                "adv-1",
                idempotency_key="offer-product",
                face=face,
                amount=1,
                beneficiary_role="fixture-label",
                product={"apr_bps": 1},
            )),
            "IDEMPOTENCY_CONFLICT",
        )
        self.assertEqual(codes(lambda: self.machine.view("adv-1")), "UNKNOWN_ADVANCE")

        self.approve(amount=10)
        digest = self.machine.state_digest()
        for kind in (
            "DISBURSE",
            "REPAY",
            "DEBIT",
            "DISBURSE_TO_BANK",
        ):
            self.assertEqual(codes(lambda kind=kind: self.machine.reject_unsupported(kind)), "REAL_FUNDS_FORBIDDEN")
        for kind in (
            "ACCRUE",
            "LICENSE",
            "FORECLOSE",
            "PRIORITY",
            "PERFECT",
            "INTEREST",
            "FEE",
            "KYC",
            "AML",
            "KYC_AML",
            "RISK_SCORE",
            "UNDERWRITE",
        ):
            self.assertEqual(
                codes(lambda kind=kind: self.machine.reject_unsupported(kind)),
                "CREDIT_PRODUCT_UNDEFINED",
            )
        self.assertEqual(codes(lambda: self.machine.reject_unsupported("draw")), "EXECUTION_KIND")
        self.assertEqual(codes(lambda: self.machine.reject_unsupported(1)), "EXECUTION_KIND")
        self.assertEqual(self.machine.state_digest(), digest)

        self.machine.draw("adv-1", idempotency_key="draw-1", draw_id="draw-1")
        before = self.machine.view("adv-1")
        self.assertEqual(
            codes(lambda: self.machine.attempt_execution("adv-1", kind="DISBURSE")),
            "REAL_FUNDS_FORBIDDEN",
        )
        self.assertEqual(
            codes(lambda: self.machine.attempt_execution("adv-1", kind="REPAY")),
            "REAL_FUNDS_FORBIDDEN",
        )
        self.assertEqual(
            codes(lambda: self.machine.attempt_execution("adv-1", kind="ACCRUE")),
            "CREDIT_PRODUCT_UNDEFINED",
        )
        self.assertEqual(self.machine.view("adv-1"), before)
        self.assertEqual(before["outstanding_exposure"], 10)
        self.assertEqual(before["open_terms"], open_terms())
        self.assertEqual(
            codes(lambda: self.machine.attempt_execution("missing", kind="draw")),
            "EXECUTION_KIND",
        )

    def test_refund_freeze_and_bad_inputs_follow_the_wave5_predicate(self):
        open_book, _face = settlement_book("CAPTURED")
        open_book.bind_refund(
            "claim-1",
            idempotency_key="refund-1",
            refund_id="refund-1",
            amount=1,
            beneficiary_role="buyer",
            reason="fixture",
        )
        refund_face = open_book.view("claim-1")["claim"]
        self.assertEqual(
            codes(lambda: self.machine.offer(
                "adv-r",
                idempotency_key="offer-r",
                face=refund_face,
                amount=1,
                beneficiary_role="fixture-label",
            )),
            "REFUND_OBLIGATION_OPEN",
        )
        self.assertEqual(codes(lambda: self.machine.view("adv-r")), "UNKNOWN_ADVANCE")

        self.offer("first", amount=10, key="offer-first")
        self.machine.approve("first", idempotency_key="approve-first")
        self.machine.draw("first", idempotency_key="draw-first", draw_id="draw-first")
        marked = dict(self.face)
        marked["caller_mark"] = "later"
        self.offer("second", amount=10, face=marked, key="offer-second")
        self.machine.approve("second", idempotency_key="approve-second")
        self.assertEqual(
            codes(lambda: self.machine.draw("second", idempotency_key="draw-second", draw_id="draw-second")),
            "FACE_SNAPSHOT_FROZEN",
        )
        self.assertEqual(self.machine.view("second")["phase"], APPROVED)
        self.assertEqual(self.machine.view("first")["open_face"], 100_000)

        self.assertEqual(
            codes(lambda: self.machine.offer(
                "first",
                idempotency_key="offer-conflict",
                face=self.face,
                amount=11,
                beneficiary_role="fixture-label",
            )),
            "ADVANCE_BINDING_CONFLICT",
        )
        self.assertEqual(
            codes(lambda: self.machine.offer(
                " spaced",
                idempotency_key="bad-id",
                face=self.face,
                amount=1,
                beneficiary_role="fixture-label",
            )),
            "INVALID_ID",
        )
        self.assertEqual(
            codes(lambda: self.machine.offer(
                "bool-amount",
                idempotency_key="bad-amount",
                face=self.face,
                amount=True,
                beneficiary_role="fixture-label",
            )),
            "INVALID_AMOUNT",
        )

    def test_credit_commands_do_not_mutate_resale_ownership(self):
        tickets = ResaleMachine()
        tickets.set_clock("clock", idempotency_key="clock-1", now_ms=T0)
        tickets.adopt_issued(
            "issue-1",
            idempotency_key="adopt-1",
            show_id="show-1",
            organizer_role="organizer",
            capacity=2,
            gate_roles=["gate-a", "gate-b"],
            primary_price=PRICE,
            resale_cap=20_000,
            resale_allowed=True,
            organizer_bps=1,
            platform_bps=1,
            slot=0,
            buyer_role="buyer-1",
            expires_ms=EXPIRES,
            order_id="order-1",
            amount=PRICE,
            payment_ref=PAY,
        )
        tickets.list_resale(
            "list-1",
            idempotency_key="list-1",
            right_id="issue-1",
            version=1,
            seller_role="buyer-1",
            recipient_role="buyer-2",
            amount=PRICE,
            expires_ms=EXPIRES,
        )
        before = tickets.canonical_state()
        holder = tickets.view_right("issue-1")["right"]
        listing = tickets.view("list-1")
        machine = CreditMachine(self.book, tickets)
        machine.offer(
            "adv-1",
            idempotency_key="offer-1",
            face=self.face,
            amount=12_000,
            beneficiary_role="fixture-label",
        )
        machine.approve("adv-1", idempotency_key="approve-1")
        machine.bind_settlement("adv-1", idempotency_key="bind-1", settlement_id="claim-1")
        machine.draw("adv-1", idempotency_key="draw-1", draw_id="draw-1")
        machine.repay(
            "adv-1",
            idempotency_key="repay-1",
            repay_id="repay-1",
            sequence=1,
            amount=4_000,
        )
        machine.default("adv-1", idempotency_key="default-1", reason="fixture-unpaid")
        self.assertEqual(tickets.canonical_state(), before)
        self.assertEqual(tickets.view_right("issue-1")["right"], holder)
        self.assertEqual(tickets.view("list-1"), listing)
        self.assertEqual(holder["holder_role"], "buyer-1")
        self.assertEqual(holder["version"], 1)
        self.assertEqual(listing["phase"], "LISTED")
        self.assertIs(machine.view("adv-1")["ownership_mutated"], False)
        self.assertIs(machine.view("adv-1")["ticket_ownership_authoritative"], False)
        restored = CreditMachine.restore(
            machine.export_journal(),
            settlement_source=self.book,
            ownership_source=tickets,
        )
        self.assertEqual(restored.canonical_state(), machine.canonical_state())
        self.assertEqual(tickets.canonical_state(), before)

    def test_direct_mock_credit_note_still_reserves_without_the_machine(self):
        from mock_credit import MockCredit

        book = MockCredit()
        noted = book.note_advance(
            "adv-1",
            face=self.face,
            amount=100_000,
            beneficiary_role="fixture-label",
        )
        self.assertEqual(noted["advance"]["status"], "NOTED")
        self.assertEqual(noted["advance"]["provenance"], PROVENANCE)
        self.assertIs(noted["advance"]["funds_executed"], False)
        self.assertEqual(noted["advance"]["open_terms"], open_terms())
        self.assertEqual(codes(lambda: self.machine.view("adv-1")), "UNKNOWN_ADVANCE")

    def test_adopted_boundary_does_not_price_rank_or_recalculate(self):
        face = self.face
        self.assertEqual(
            codes(lambda: self.machine.offer(
                "priced",
                idempotency_key="offer-schedule",
                face=face,
                amount=1,
                beneficiary_role="fixture-label",
                product={"apr_bps": 1200, "schedule": [{"day": 30, "amount": 1}]},
            )),
            "CREDIT_PRODUCT_UNDEFINED",
        )
        self.assertEqual(codes(lambda: self.machine.view("priced")), "UNKNOWN_ADVANCE")

        first = self.offer("senior-a", amount=60_000, key="offer-senior-a", beneficiary_role="lender")
        self.assertEqual(first["credit"]["open_terms"], open_terms())
        self.assertIs(first["credit"]["legal_debtor_bound"], False)
        self.assertIs(first["interest_defined"], False)
        self.machine.approve("senior-a", idempotency_key="approve-senior-a")
        self.machine.draw("senior-a", idempotency_key="draw-senior-a", draw_id="draw-senior-a")
        self.offer("senior-b", amount=40_000, key="offer-senior-b", beneficiary_role="borrower")
        self.machine.approve("senior-b", idempotency_key="approve-senior-b")
        second = self.machine.draw("senior-b", idempotency_key="draw-senior-b", draw_id="draw-senior-b")
        self.assertEqual(second["credit"]["phase"], DRAWN)
        self.assertEqual(second["credit"]["reserved_open"], 100_000)
        self.assertEqual(second["credit"]["open_face"], 100_000)
        self.assertEqual(second["credit"]["confirmed_cash_on_face"], 97_000)
        for advance_id in ("senior-a", "senior-b"):
            view = self.machine.view(advance_id)
            self.assertIs(view["priority_bound"], False)
            self.assertIs(view["collateral_perfected"], False)
            self.assertIs(view["interest_defined"], False)
            self.assertNotIn("seniority_rank", view)
            self.assertNotIn("apr_bps", view)
            self.assertEqual(view["open_terms"], open_terms())
        self.offer("senior-c", amount=1, key="offer-senior-c")
        self.machine.approve("senior-c", idempotency_key="approve-senior-c")
        self.assertEqual(
            codes(lambda: self.machine.draw(
                "senior-c",
                idempotency_key="draw-senior-c",
                draw_id="draw-senior-c",
            )),
            "ADVANCE_EXCEEDS_OPEN_FACE",
        )

        self.book.distribute(
            "claim-1",
            idempotency_key="dist-terms",
            order=["organizer", "platform"],
        )
        moved = self.book.view("claim-1")["claim"]
        self.assertLess(sum(line["outstanding"] for line in moved["obligations"]), 100_000)
        self.assertEqual(self.machine.view("senior-a")["open_face"], 100_000)
        self.offer("revalued", amount=1, key="offer-revalued", face=moved)
        self.machine.approve("revalued", idempotency_key="approve-revalued")
        self.assertEqual(
            codes(lambda: self.machine.draw(
                "revalued",
                idempotency_key="draw-revalued",
                draw_id="draw-revalued",
            )),
            "FACE_SNAPSHOT_FROZEN",
        )
        self.assertEqual(self.machine.view("revalued")["phase"], APPROVED)
        self.assertEqual(self.machine.view("senior-a")["open_face"], 100_000)
        digest = self.machine.state_digest()
        self.assertEqual(codes(lambda: self.machine.reject_unsupported("INTEREST")), "CREDIT_PRODUCT_UNDEFINED")
        self.assertEqual(codes(lambda: self.machine.reject_unsupported("PRIORITY")), "CREDIT_PRODUCT_UNDEFINED")
        self.assertEqual(codes(lambda: self.machine.reject_unsupported("PERFECT")), "CREDIT_PRODUCT_UNDEFINED")
        self.assertEqual(self.machine.state_digest(), digest)
        self.assertIs(self.machine.view("senior-a")["interest_defined"], False)
        self.assertIs(self.machine.view("senior-a")["collateral_perfected"], False)
