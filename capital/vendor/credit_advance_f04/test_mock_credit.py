"""Deterministic checks for the F04 offline credit-advance mock."""

import importlib.util
import unittest
from pathlib import Path

from mock_credit import PROVENANCE, CreditMockError, MockCredit, open_terms

_SETTLEMENT_PATH = Path(__file__).resolve().parents[1] / "settlement_f01_f03" / "mock_settlement.py"
_SPEC = importlib.util.spec_from_file_location("wave3_mock_settlement", _SETTLEMENT_PATH)
_SETTLEMENT = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_SETTLEMENT)
MockSettlement = _SETTLEMENT.MockSettlement

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


def policy():
    return {
        "kind": "PRIMARY_FEE_BPS",
        "fee_bps": 500,
        "residual_payee": "organizer",
        "fee_payee": "platform",
    }


def settlement(claim_id="claim-1"):
    book = MockSettlement()
    book.recognize_claim(
        claim_id,
        trade_id="trade-1",
        gross=100_000,
        debtor_role="fixture-merchant",
        policy=policy(),
    )
    return book


def codes(fn):
    try:
        fn()
    except CreditMockError as error:
        return error.code
    raise AssertionError("expected CreditMockError")


class CreditAdvanceMockTests(unittest.TestCase):
    def setUp(self):
        self.credit = MockCredit()

    def test_note_reserves_unpaid_face_without_funds_or_license(self):
        book = settlement()
        before = book.view("claim-1")
        noted = self.credit.note_advance(
            "adv-1",
            face=before,
            amount=100_000,
            beneficiary_role="fixture-label",
        )
        advance = noted["advance"]
        self.assertFalse(noted["duplicate"])
        self.assertIsNone(noted["applied"])
        self.assertEqual(advance["provenance"], PROVENANCE)
        self.assertEqual(advance["status"], "NOTED")
        self.assertEqual(advance["open_face"], 100_000)
        self.assertEqual(advance["reserved_open"], 100_000)
        self.assertEqual(advance["residual_unreserved"], 0)
        self.assertEqual(advance["confirmed_cash_on_face"], 0)
        self.assertEqual(advance["currency"], "KRW")
        self.assertTrue(advance["snapshot_frozen"])
        for flag in FALSE_FLAGS:
            self.assertIs(advance[flag], False)
        self.assertEqual(book.view("claim-1"), before)
        again = self.credit.note_advance(
            "adv-1",
            face=before,
            amount=100_000,
            beneficiary_role="fixture-label",
        )
        self.assertTrue(again["duplicate"])
        self.assertEqual(again["advance"]["reserved_open"], 100_000)
        self.assertEqual(
            codes(lambda: self.credit.note_advance(
                "adv-1",
                face=before,
                amount=1,
                beneficiary_role="fixture-label",
            )),
            "ADVANCE_BINDING_CONFLICT",
        )
        self.assertEqual(
            codes(lambda: self.credit.note_advance(
                "adv-2",
                face=before,
                amount=1,
                beneficiary_role="fixture-label",
            )),
            "ADVANCE_EXCEEDS_OPEN_FACE",
        )

    def test_product_terms_are_rejected_before_a_note_exists(self):
        face = settlement().view("claim-1")
        self.assertEqual(
            codes(lambda: self.credit.note_advance(
                "adv-1",
                face=face,
                amount=1,
                beneficiary_role="fixture-label",
                product={},
            )),
            "CREDIT_PRODUCT_UNDEFINED",
        )
        self.assertEqual(
            codes(lambda: self.credit.note_advance(
                "adv-1",
                face=face,
                amount=1,
                beneficiary_role="fixture-label",
                product={"apr_bps": 0},
            )),
            "CREDIT_PRODUCT_UNDEFINED",
        )
        self.assertEqual(codes(lambda: self.credit.view_claim("claim-1")), "UNKNOWN_CLAIM")
        self.assertEqual(codes(lambda: self.credit.view("adv-1")), "UNKNOWN_ADVANCE")

    def test_confirmed_cash_and_recovery_are_not_capacity(self):
        book = settlement()
        book.observe_settlement_statement(
            "claim-1",
            movement_id="move-1",
            gross=100_000,
            amount=97_000,
            fee=3_000,
            tax=0,
            held=0,
            adjustment=0,
        )
        distributed = book.apply_distribution("claim-1", order=["organizer", "platform"])["claim"]
        noted = self.credit.note_advance(
            "adv-cash",
            face=distributed,
            amount=3_000,
            beneficiary_role="fixture-label",
        )["advance"]
        self.assertEqual(noted["open_face"], 3_000)
        self.assertEqual(noted["confirmed_cash_on_face"], 97_000)
        self.assertEqual(noted["recovery_due_on_face"], 0)
        self.assertEqual(noted["residual_unreserved"], 0)
        self.assertIs(noted["funds_executed"], False)
        self.assertEqual(
            codes(lambda: self.credit.note_advance(
                "adv-cash-2",
                face=distributed,
                amount=97_000,
                beneficiary_role="fixture-label",
            )),
            "ADVANCE_EXCEEDS_OPEN_FACE",
        )

        repaid = settlement()
        repaid.observe_settlement_statement(
            "claim-1",
            movement_id="move-1",
            gross=100_000,
            amount=97_000,
            fee=3_000,
            tax=0,
            held=0,
            adjustment=0,
        )
        repaid.apply_distribution("claim-1", order=["organizer", "platform"])
        repaid.bind_refund(
            "claim-1",
            refund_id="refund-1",
            amount=100_000,
            beneficiary_role="buyer",
            reason="fixture",
        )
        closed = repaid.view("claim-1")
        self.assertEqual(closed["recovery_due"], 97_000)
        other = MockCredit()
        self.assertEqual(
            codes(lambda: other.note_advance(
                "adv-recovery",
                face=closed,
                amount=1,
                beneficiary_role="fixture-label",
            )),
            "ADVANCE_EXCEEDS_OPEN_FACE",
        )
        self.assertEqual(codes(lambda: other.view_claim("claim-1")), "UNKNOWN_CLAIM")

    def test_claims_do_not_share_a_ceiling_and_the_snapshot_stays_frozen(self):
        book = settlement()
        book.recognize_claim(
            "claim-2",
            trade_id="trade-2",
            gross=100_000,
            debtor_role="fixture-merchant",
            policy=policy(),
        )
        first = book.view("claim-1")
        second = book.view("claim-2")
        self.credit.note_advance("a1", face=first, amount=60_000, beneficiary_role="label-a")
        self.credit.note_advance("a2", face=second, amount=100_000, beneficiary_role="label-b")
        self.assertEqual(self.credit.view_claim("claim-1")["reserved_open"], 60_000)
        self.assertEqual(self.credit.view_claim("claim-2")["residual_unreserved"], 0)
        self.assertIs(self.credit.view("a1")["priority_bound"], False)
        self.assertIs(self.credit.view("a2")["priority_bound"], False)
        self.assertEqual(
            codes(lambda: self.credit.note_advance(
                "a3",
                face=first,
                amount=50_000,
                beneficiary_role="label-c",
            )),
            "ADVANCE_EXCEEDS_OPEN_FACE",
        )

        moved = settlement()
        moved.observe_settlement_statement(
            "claim-1",
            movement_id="move-1",
            gross=100_000,
            amount=97_000,
            fee=3_000,
            tax=0,
            held=0,
            adjustment=0,
        )
        moved.apply_distribution("claim-1", order=["organizer", "platform"])
        later = moved.view("claim-1")
        self.assertEqual(
            codes(lambda: self.credit.note_advance(
                "a4",
                face=later,
                amount=1,
                beneficiary_role="label-a",
            )),
            "FACE_SNAPSHOT_FROZEN",
        )
        self.assertEqual(self.credit.view_claim("claim-1")["open_face"], 100_000)
        marked = dict(first)
        marked["caller_mark"] = "later"
        self.assertEqual(
            codes(lambda: self.credit.note_advance(
                "a5",
                face=marked,
                amount=1,
                beneficiary_role="label-a",
            )),
            "FACE_SNAPSHOT_FROZEN",
        )
        self.assertEqual(self.credit.view_claim("claim-1")["open_face"], 100_000)

    def test_open_refund_blocks_and_release_is_not_repayment(self):
        book = settlement()
        book.bind_refund(
            "claim-1",
            refund_id="refund-1",
            amount=1,
            beneficiary_role="buyer",
            reason="fixture",
        )
        open_refund = book.view("claim-1")
        self.assertEqual(open_refund["refund_bearer_policy"], "REQUESTER")
        self.assertEqual(
            codes(lambda: self.credit.note_advance(
                "adv-1",
                face=open_refund,
                amount=1,
                beneficiary_role="fixture-label",
            )),
            "REFUND_OBLIGATION_OPEN",
        )
        self.assertEqual(codes(lambda: self.credit.view_claim("claim-1")), "UNKNOWN_CLAIM")

        fresh = settlement().view("claim-1")
        self.credit.note_advance("keep", face=fresh, amount=40_000, beneficiary_role="fixture-label")
        self.credit.note_advance("drop", face=fresh, amount=60_000, beneficiary_role="other-label")
        released = self.credit.release_note("drop")
        self.assertFalse(released["duplicate"])
        self.assertEqual(released["advance"]["status"], "RELEASED")
        self.assertIs(released["advance"]["repayment_observed"], False)
        self.assertIs(released["advance"]["funds_executed"], False)
        self.assertEqual(released["advance"]["reserved_open"], 40_000)
        self.assertTrue(self.credit.release_note("drop")["duplicate"])
        self.assertEqual(self.credit.view("drop")["status"], "RELEASED")
        replay = self.credit.note_advance("drop", face=fresh, amount=60_000, beneficiary_role="other-label")
        self.assertTrue(replay["duplicate"])
        self.assertEqual(replay["advance"]["status"], "RELEASED")
        self.assertEqual(replay["advance"]["reserved_open"], 40_000)
        replacement = self.credit.note_advance(
            "drop-2",
            face=fresh,
            amount=60_000,
            beneficiary_role="other-label",
        )
        self.assertEqual(replacement["advance"]["status"], "NOTED")
        self.assertEqual(replacement["advance"]["reserved_open"], 100_000)
        self.assertEqual(codes(lambda: self.credit.release_note("missing")), "UNKNOWN_ADVANCE")

    def test_execution_attempts_do_not_change_the_note(self):
        face = settlement().view("claim-1")
        self.credit.note_advance("adv-1", face=face, amount=10, beneficiary_role="fixture-label")
        before = self.credit.view("adv-1")
        for kind, code in (
            ("DISBURSE", "REAL_FUNDS_FORBIDDEN"),
            ("REPAY", "REAL_FUNDS_FORBIDDEN"),
            ("DEBIT", "REAL_FUNDS_FORBIDDEN"),
            ("ACCRUE", "CREDIT_PRODUCT_UNDEFINED"),
            ("LICENSE", "CREDIT_PRODUCT_UNDEFINED"),
            ("FORECLOSE", "CREDIT_PRODUCT_UNDEFINED"),
            ("PRIORITY", "CREDIT_PRODUCT_UNDEFINED"),
            ("PERFECT", "CREDIT_PRODUCT_UNDEFINED"),
        ):
            self.assertEqual(
                codes(lambda kind=kind: self.credit.attempt_execution("adv-1", kind=kind)),
                code,
            )
            self.assertEqual(self.credit.view("adv-1"), before)
        self.assertEqual(codes(lambda: self.credit.attempt_execution("adv-1", kind="draw")), "EXECUTION_KIND")
        self.assertEqual(self.credit.view("adv-1"), before)
        self.credit.release_note("adv-1")
        released = self.credit.view("adv-1")
        self.assertEqual(
            codes(lambda: self.credit.attempt_execution("adv-1", kind="DISBURSE")),
            "REAL_FUNDS_FORBIDDEN",
        )
        self.assertEqual(self.credit.view("adv-1"), released)
        self.assertEqual(codes(lambda: self.credit.attempt_execution("missing", kind="DISBURSE")), "UNKNOWN_ADVANCE")
        self.assertEqual(codes(lambda: self.credit.attempt_execution("missing", kind="draw")), "EXECUTION_KIND")

    def test_forged_faces_and_bad_inputs_are_rejected(self):
        face = settlement().view("claim-1")
        funded = dict(face)
        funded["funds_executed"] = True
        self.assertEqual(
            codes(lambda: self.credit.note_advance(
                "adv-1",
                face=funded,
                amount=1,
                beneficiary_role="fixture-label",
            )),
            "SETTLEMENT_FACE_NOT_MOCK",
        )
        admitted = dict(face)
        admitted["admission_granted"] = True
        self.assertEqual(
            codes(lambda: self.credit.note_advance(
                "adv-1",
                face=admitted,
                amount=1,
                beneficiary_role="fixture-label",
            )),
            "SETTLEMENT_FACE_NOT_MOCK",
        )
        lied = dict(face)
        lied["obligations"] = [dict(item) for item in face["obligations"]]
        lied["obligations"][0] = dict(lied["obligations"][0])
        lied["obligations"][0]["outstanding"] = lied["obligations"][0]["outstanding"] + 1
        self.assertEqual(
            codes(lambda: self.credit.note_advance(
                "adv-1",
                face=lied,
                amount=1,
                beneficiary_role="fixture-label",
            )),
            "SETTLEMENT_FACE_MISMATCH",
        )
        foreign = dict(face)
        foreign["provenance"] = "LIVE_LEDGER"
        self.assertEqual(
            codes(lambda: self.credit.note_advance(
                "adv-1",
                face=foreign,
                amount=1,
                beneficiary_role="fixture-label",
            )),
            "SETTLEMENT_FACE_NOT_MOCK",
        )
        usd = dict(face)
        usd["currency"] = "USD"
        self.assertEqual(
            codes(lambda: self.credit.note_advance(
                "adv-1",
                face=usd,
                amount=1,
                beneficiary_role="fixture-label",
            )),
            "CURRENCY_UNSUPPORTED",
        )
        self.assertEqual(
            codes(lambda: self.credit.note_advance(
                "adv-1",
                face=[],
                amount=1,
                beneficiary_role="fixture-label",
            )),
            "SETTLEMENT_FACE_TYPE",
        )
        self.assertEqual(
            codes(lambda: self.credit.note_advance(
                "adv-1",
                face=face,
                amount=True,
                beneficiary_role="fixture-label",
            )),
            "INVALID_AMOUNT",
        )
        self.assertEqual(
            codes(lambda: self.credit.note_advance(
                "adv-1",
                face=face,
                amount=0,
                beneficiary_role="fixture-label",
            )),
            "INVALID_AMOUNT",
        )
        self.assertEqual(
            codes(lambda: self.credit.note_advance(
                " adv",
                face=face,
                amount=1,
                beneficiary_role="fixture-label",
            )),
            "INVALID_ID",
        )
        self.assertEqual(codes(lambda: self.credit.view_claim("claim-1")), "UNKNOWN_CLAIM")

    def test_adopted_boundary_stays_unfilled_on_the_mock(self):
        face = settlement().view("claim-1")
        schedule = {"apr_bps": 1200, "tenor_days": 30, "schedule": [{"day": 30, "amount": 1}]}
        self.assertEqual(
            codes(lambda: self.credit.note_advance(
                "priced",
                face=face,
                amount=1,
                beneficiary_role="fixture-label",
                product=schedule,
            )),
            "CREDIT_PRODUCT_UNDEFINED",
        )
        self.assertEqual(
            codes(lambda: self.credit.note_advance(
                "fee",
                face=face,
                amount=1,
                beneficiary_role="fixture-label",
                product={"fee": 1},
            )),
            "CREDIT_PRODUCT_UNDEFINED",
        )
        self.assertEqual(codes(lambda: self.credit.view_claim("claim-1")), "UNKNOWN_CLAIM")

        roles = ("lender", "borrower", "secured-party", "refund-debtor")
        amounts = (10_000, 20_000, 30_000, 40_000)
        for index, (role, amount) in enumerate(zip(roles, amounts), start=1):
            noted = self.credit.note_advance(
                f"party-{index}",
                face=face,
                amount=amount,
                beneficiary_role=role,
            )["advance"]
            self.assertEqual(noted["beneficiary_role"], role)
            self.assertEqual(noted["open_terms"], open_terms())
            self.assertIs(noted["legal_debtor_bound"], False)
            self.assertIs(noted["interest_defined"], False)
            self.assertIs(noted["priority_bound"], False)
            self.assertIs(noted["collateral_perfected"], False)
            self.assertIs(noted["external_pledge_complete"], False)
            self.assertTrue(noted["snapshot_frozen"])
            self.assertNotIn("apr_bps", noted)
            self.assertNotIn("schedule", noted)
            self.assertNotIn("seniority_rank", noted)
            self.assertNotIn("legal_party", noted)
        claim = self.credit.view_claim("claim-1")
        self.assertEqual(claim["open_terms"], open_terms())
        self.assertEqual(claim["reserved_open"], 100_000)
        self.assertEqual(claim["residual_unreserved"], 0)
        self.assertEqual(claim["open_face"], 100_000)

        before = self.credit.view("party-1")
        self.assertEqual(
            codes(lambda: self.credit.attempt_execution("party-1", kind="PERFECT")),
            "CREDIT_PRODUCT_UNDEFINED",
        )
        self.assertEqual(
            codes(lambda: self.credit.attempt_execution("party-1", kind="PRIORITY")),
            "CREDIT_PRODUCT_UNDEFINED",
        )
        self.assertEqual(
            codes(lambda: self.credit.attempt_execution("party-1", kind="ACCRUE")),
            "CREDIT_PRODUCT_UNDEFINED",
        )
        self.assertEqual(self.credit.view("party-1"), before)

        book = settlement()
        later_credit = MockCredit()
        original = book.view("claim-1")
        later_credit.note_advance(
            "frozen",
            face=original,
            amount=100_000,
            beneficiary_role="fixture-label",
        )
        book.observe_settlement_statement(
            "claim-1",
            movement_id="move-1",
            gross=100_000,
            amount=97_000,
            fee=3_000,
            tax=0,
            held=0,
            adjustment=0,
        )
        distributed = book.apply_distribution("claim-1", order=["organizer", "platform"])["claim"]
        self.assertEqual(distributed["confirmed_cash"], 97_000)
        self.assertLess(sum(line["outstanding"] for line in distributed["obligations"]), 100_000)
        self.assertEqual(
            codes(lambda: later_credit.note_advance(
                "revalued",
                face=distributed,
                amount=1,
                beneficiary_role="fixture-label",
            )),
            "FACE_SNAPSHOT_FROZEN",
        )
        frozen = later_credit.view("frozen")
        self.assertEqual(frozen["open_face"], 100_000)
        self.assertEqual(frozen["confirmed_cash_on_face"], 0)
        record = frozen["open_terms"]
        self.assertIsNone(record["decided_value"])
        self.assertEqual(record["adopted_option"], "A")
        self.assertEqual(record["policy_number_status"], "UNDETERMINED")
        self.assertEqual(record["adoption_decider"], "JunTae")
        self.assertEqual(record["adoption_date"], "2026-10-09")
        terms = record["terms"]
        self.assertEqual(terms["limit-recalculation"]["mock_effect"], "SNAPSHOT_FROZEN")
        self.assertEqual(terms["legal-parties"]["mock_effect"], "ROLE_LABEL_ONLY")
        self.assertEqual(terms["perfection"]["mock_effect"], "NOT_PERFECTED")
        self.assertEqual(terms["interest-apr-schedule"]["mock_effect"], "INTEREST_UNDEFINED")
        self.assertEqual(terms["seniority"]["mock_effect"], "UNORDERED_RESERVATION")
        for row in terms.values():
            self.assertIsNone(row["decided_value"])
            self.assertEqual(row["policy_number_status"], "UNDETERMINED")
            self.assertEqual(row["adopted_option"], "A")
