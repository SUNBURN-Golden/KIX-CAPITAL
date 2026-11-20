"""Lifecycle checks for the in-memory F01–F03 settlement machine."""

import json
import unittest

from settlement_fsm import (
    CANCELLED,
    COMMITTED,
    FAILED,
    SettlementError,
    SettlementMachine,
)


def policy(**changes):
    base = {
        "kind": "PRIMARY_FEE_BPS",
        "fee_bps": 500,
        "residual_payee": "organizer",
        "fee_payee": "platform",
    }
    base.update(changes)
    return base


def line(view, payee):
    return next(item for item in view["obligations"] if item["payee"] == payee)


def codes(fn):
    try:
        fn()
    except SettlementError as error:
        return error.code
    raise AssertionError("expected SettlementError")


class SettlementFsmTests(unittest.TestCase):
    def setUp(self):
        self.machine = SettlementMachine()

    def initiate(self, **changes):
        body = dict(
            trade_id="trade-1",
            gross=100_000,
            debtor_role="fixture-merchant",
            policy=policy(),
            idempotency_key="init-1",
        )
        body.update(changes)
        key = body.pop("idempotency_key")
        return self.machine.initiate("claim-1", idempotency_key=key, **body)

    def authorize(self):
        self.initiate()
        return self.machine.authorize("claim-1", idempotency_key="auth-1")

    def capture(self):
        self.authorize()
        return self.machine.capture("claim-1", idempotency_key="cap-1")

    def commit(self, **changes):
        self.capture()
        body = dict(
            movement_id="move-1",
            gross=100_000,
            amount=97_000,
            fee=3_000,
            tax=0,
            held=0,
            adjustment=0,
            idempotency_key="commit-1",
        )
        body.update(changes)
        key = body.pop("idempotency_key")
        return self.machine.commit("claim-1", idempotency_key=key, **body)

    def test_happy_path_posts_mock_economics_without_external_execution(self):
        opened = self.initiate()
        self.assertEqual(opened["applied"], "initiate")
        self.assertFalse(opened["duplicate"])
        self.assertEqual(opened["provenance"], "MOCK_SETTLEMENT_ONLY")
        self.assertEqual(opened["external_payment"], "UNSUPPORTED")
        self.assertIs(opened["funds_executed"], False)
        self.assertEqual(opened["settlement"]["phase"], "INITIATED")
        self.assertIsNone(opened["settlement"]["claim"])
        self.assertIs(opened["settlement"]["provider_authorization_executed"], False)
        self.assertIs(opened["settlement"]["durable"], False)

        authorized = self.machine.authorize("claim-1", idempotency_key="auth-1")
        self.assertEqual(authorized["settlement"]["phase"], "AUTHORIZED")
        self.assertIs(authorized["settlement"]["mock_authorized"], True)
        self.assertIs(authorized["settlement"]["provider_authorization_executed"], False)
        self.assertIsNone(authorized["settlement"]["claim"])

        captured = self.machine.capture("claim-1", idempotency_key="cap-1")
        claim = captured["settlement"]["claim"]
        self.assertEqual(captured["settlement"]["phase"], "CAPTURED")
        self.assertEqual(claim["provenance"], "MOCK_SETTLEMENT_ONLY")
        self.assertEqual(line(claim, "organizer")["face"], 95_000)
        self.assertEqual(line(claim, "platform")["face"], 5_000)
        self.assertEqual(claim["confirmed_cash"], 0)
        for flag in (
            "legal_debtor_bound",
            "admission_granted",
            "right_cancelled",
            "bank_debit_observed",
            "external_return_closed",
            "funds_executed",
        ):
            self.assertIs(claim[flag], False)
            self.assertIs(captured["settlement"][flag], False)

        committed = self.machine.commit(
            "claim-1",
            idempotency_key="commit-1",
            movement_id="move-1",
            gross=100_000,
            amount=97_000,
            fee=3_000,
            tax=0,
            held=0,
            adjustment=0,
        )
        posted = committed["settlement"]
        self.assertEqual(posted["phase"], COMMITTED)
        self.assertEqual(posted["commit_movement_id"], "move-1")
        self.assertEqual(posted["claim"]["confirmed_cash"], 97_000)
        self.assertEqual(posted["claim"]["non_cash_accounted"], 3_000)
        self.assertEqual(line(posted["claim"], "organizer")["face"], 95_000)
        self.assertEqual(posted["claim"]["distributed_cash"], 0)

        distributed = self.machine.distribute(
            "claim-1",
            idempotency_key="dist-1",
            order=["platform", "organizer"],
        )
        self.assertEqual(distributed["effect"], {"platform": 5_000, "organizer": 92_000})
        self.assertEqual(distributed["settlement"]["phase"], COMMITTED)
        self.assertEqual(line(distributed["settlement"]["claim"], "organizer")["outstanding"], 3_000)
        self.assertIs(distributed["settlement"]["funds_executed"], False)
        self.assertIs(distributed["settlement"]["terminal"], False)

    def test_same_key_replays_and_a_different_body_is_rejected(self):
        first = self.initiate()
        again = self.initiate()
        self.assertTrue(again["duplicate"])
        self.assertIsNone(again["applied"])
        self.assertEqual(again["settlement"], first["settlement"])
        self.assertEqual(self.machine.view("claim-1")["accepted_entries"], 1)
        self.assertEqual(
            codes(lambda: self.initiate(gross=90_000)),
            "IDEMPOTENCY_CONFLICT",
        )
        self.assertEqual(self.machine.view("claim-1")["gross"], 100_000)
        self.assertEqual(
            codes(lambda: self.machine.initiate(
                "claim-1",
                idempotency_key="init-2",
                trade_id="trade-1",
                gross=100_000,
                debtor_role="fixture-merchant",
                policy=policy(),
            )),
            "ILLEGAL_TRANSITION",
        )
        self.assertEqual(self.machine.view("claim-1")["phase"], "INITIATED")

        self.machine.authorize("claim-1", idempotency_key="auth-1")
        lost = self.machine.authorize("claim-1", idempotency_key="auth-1")
        self.assertTrue(lost["duplicate"])
        self.assertEqual(lost["settlement"]["phase"], "AUTHORIZED")
        self.assertEqual(
            codes(lambda: self.machine.authorize("claim-1", idempotency_key="auth-2")),
            "ILLEGAL_TRANSITION",
        )

    def test_illegal_transitions_do_not_move_the_phase(self):
        self.initiate()
        before = self.machine.canonical_state()
        self.assertEqual(
            codes(lambda: self.machine.capture("claim-1", idempotency_key="cap-early")),
            "ILLEGAL_TRANSITION",
        )
        self.assertEqual(
            codes(lambda: self.machine.commit(
                "claim-1",
                idempotency_key="commit-early",
                movement_id="move-1",
                gross=100_000,
                amount=97_000,
                fee=3_000,
                tax=0,
                held=0,
                adjustment=0,
            )),
            "ILLEGAL_TRANSITION",
        )
        self.assertEqual(self.machine.canonical_state(), before)
        self.assertEqual(
            codes(lambda: self.machine.capture("claim-1", idempotency_key="cap-early")),
            "ILLEGAL_TRANSITION",
        )

        self.machine.authorize("claim-1", idempotency_key="auth-1")
        self.machine.capture("claim-1", idempotency_key="cap-1")
        self.assertEqual(
            codes(lambda: self.machine.cancel("claim-1", idempotency_key="cancel-late", reason="LATE")),
            "ILLEGAL_TRANSITION",
        )
        self.assertEqual(
            codes(lambda: self.machine.fail("claim-1", idempotency_key="fail-late", reason="LATE")),
            "ILLEGAL_TRANSITION",
        )
        self.assertEqual(
            codes(lambda: self.machine.distribute(
                "claim-1",
                idempotency_key="dist-early",
                order=["platform", "organizer"],
            )),
            "ILLEGAL_TRANSITION",
        )
        self.assertEqual(self.machine.view("claim-1")["phase"], "CAPTURED")
        self.assertIsNone(self.machine.view("claim-1")["claim"]["distribution_order"])
        self.assertEqual(self.machine.view("claim-1")["claim"]["confirmed_cash"], 0)

        self.assertEqual(codes(lambda: self.machine.view("missing")), "UNKNOWN_SETTLEMENT")
        self.assertEqual(
            codes(lambda: self.machine.authorize("missing", idempotency_key="auth-missing")),
            "UNKNOWN_SETTLEMENT",
        )

    def test_terminal_fail_and_cancel_are_immutable(self):
        self.authorize()
        failed = self.machine.fail("claim-1", idempotency_key="fail-1", reason="FIXTURE_DECLINE")
        self.assertEqual(failed["settlement"]["phase"], FAILED)
        self.assertIs(failed["settlement"]["terminal"], True)
        self.assertEqual(failed["settlement"]["failure_reason"], "FIXTURE_DECLINE")
        self.assertIs(failed["settlement"]["mock_authorized"], True)
        self.assertIsNone(failed["settlement"]["claim"])
        self.assertIs(failed["settlement"]["provider_authorization_executed"], False)
        digest = self.machine.state_digest()
        for call in (
            lambda: self.machine.initiate(
                "claim-1",
                idempotency_key="init-again",
                trade_id="trade-1",
                gross=100_000,
                debtor_role="fixture-merchant",
                policy=policy(),
            ),
            lambda: self.machine.authorize("claim-1", idempotency_key="auth-again"),
            lambda: self.machine.capture("claim-1", idempotency_key="cap-again"),
            lambda: self.machine.commit(
                "claim-1",
                idempotency_key="commit-again",
                movement_id="move-1",
                gross=100_000,
                amount=100_000,
                fee=0,
                tax=0,
                held=0,
                adjustment=0,
            ),
            lambda: self.machine.cancel("claim-1", idempotency_key="cancel-again", reason="NO"),
            lambda: self.machine.fail("claim-1", idempotency_key="fail-again", reason="NO"),
            lambda: self.machine.bind_refund(
                "claim-1",
                idempotency_key="refund-again",
                refund_id="refund-1",
                amount=1,
                beneficiary_role="buyer",
                reason="NO",
            ),
        ):
            self.assertEqual(codes(call), "TERMINAL_IMMUTABLE")
        self.assertEqual(self.machine.state_digest(), digest)
        replayed = self.machine.fail("claim-1", idempotency_key="fail-1", reason="FIXTURE_DECLINE")
        self.assertTrue(replayed["duplicate"])
        self.assertEqual(replayed["settlement"]["phase"], FAILED)

        other = SettlementMachine()
        other.initiate(
            "claim-9",
            idempotency_key="init-9",
            trade_id="trade-9",
            gross=10_000,
            debtor_role="fixture-merchant",
            policy=policy(fee_bps=0),
        )
        cancelled = other.cancel("claim-9", idempotency_key="cancel-9", reason="BUYER_LEFT")
        self.assertEqual(cancelled["settlement"]["phase"], CANCELLED)
        self.assertEqual(cancelled["settlement"]["cancel_reason"], "BUYER_LEFT")
        self.assertIs(cancelled["settlement"]["mock_authorized"], False)
        self.assertIsNone(cancelled["settlement"]["claim"])
        self.assertEqual(
            codes(lambda: other.authorize("claim-9", idempotency_key="auth-9")),
            "TERMINAL_IMMUTABLE",
        )
        report = other.reconcile("claim-9", idempotency_key="recon-9")
        self.assertTrue(report["matched"])
        self.assertEqual(report["settlement"]["phase"], CANCELLED)
        self.assertIs(report["funds_executed"], False)

    def test_commit_fault_is_outside_the_journal_and_replay_stays_captured(self):
        self.capture()
        journal = json.loads(json.dumps(self.machine.export_journal()))
        before = self.machine.canonical_state()
        self.assertEqual(
            codes(lambda: self.machine.commit(
                "claim-1",
                idempotency_key="commit-bad",
                movement_id="move-bad",
                gross=100_000,
                amount=1,
                fee=0,
                tax=0,
                held=0,
                adjustment=0,
            )),
            "SETTLEMENT_COMPONENT_MISMATCH",
        )
        self.assertEqual(
            codes(lambda: self.machine.commit(
                "claim-1",
                idempotency_key="commit-bad",
                movement_id="move-bad",
                gross=100_000,
                amount=1,
                fee=0,
                tax=0,
                held=0,
                adjustment=0,
            )),
            "SETTLEMENT_COMPONENT_MISMATCH",
        )
        self.assertEqual(
            codes(lambda: self.machine.commit(
                "claim-1",
                idempotency_key="commit-bad",
                movement_id="move-bad",
                gross=100_000,
                amount=97_000,
                fee=3_000,
                tax=0,
                held=0,
                adjustment=0,
            )),
            "IDEMPOTENCY_CONFLICT",
        )
        self.assertEqual(self.machine.export_journal(), journal)
        self.assertEqual(self.machine.canonical_state(), before)
        self.assertEqual(self.machine.view("claim-1")["phase"], "CAPTURED")

        restored = SettlementMachine.restore(journal)
        self.assertEqual(restored.canonical_state(), before)
        self.assertEqual(restored.view("claim-1")["phase"], "CAPTURED")
        self.assertIsNone(restored.view("claim-1")["claim"]["distribution_order"])
        posted = restored.commit(
            "claim-1",
            idempotency_key="commit-bad",
            movement_id="move-1",
            gross=100_000,
            amount=97_000,
            fee=3_000,
            tax=0,
            held=0,
            adjustment=0,
        )
        self.assertFalse(posted["duplicate"])
        self.assertEqual(posted["settlement"]["claim"]["confirmed_cash"], 97_000)
        retry = restored.commit(
            "claim-1",
            idempotency_key="commit-bad",
            movement_id="move-1",
            gross=100_000,
            amount=97_000,
            fee=3_000,
            tax=0,
            held=0,
            adjustment=0,
        )
        self.assertTrue(retry["duplicate"])
        self.assertEqual(restored.view("claim-1")["claim"]["confirmed_cash"], 97_000)
        self.assertEqual(retry["settlement"], posted["settlement"])

        crashed = json.loads(json.dumps(restored.export_journal()))
        crashed.append({"op": "tamper"})
        self.assertEqual(codes(lambda: SettlementMachine.restore(crashed)), "INVALID_JOURNAL")
        self.assertEqual(codes(lambda: SettlementMachine.restore({"op": "initiate"})), "INVALID_JOURNAL")
        revived = SettlementMachine.restore(json.loads(json.dumps(restored.export_journal())))
        self.assertEqual(revived.canonical_state(), restored.canonical_state())
        self.assertEqual(revived.state_digest(), restored.state_digest())
        lost_response = revived.commit(
            "claim-1",
            idempotency_key="commit-bad",
            movement_id="move-1",
            gross=100_000,
            amount=97_000,
            fee=3_000,
            tax=0,
            held=0,
            adjustment=0,
        )
        self.assertTrue(lost_response["duplicate"])
        self.assertEqual(revived.view("claim-1")["claim"]["confirmed_cash"], 97_000)

    def test_partial_refund_distribution_survives_replay_and_is_not_a_clawback(self):
        self.commit()
        self.machine.distribute(
            "claim-1",
            idempotency_key="dist-1",
            order=["platform", "organizer"],
        )
        distributed_at = self.machine.export_journal()
        refunded = self.machine.bind_refund(
            "claim-1",
            idempotency_key="refund-1",
            refund_id="refund-1",
            amount=40_000,
            beneficiary_role="buyer",
            reason="PARTIAL",
        )
        self.assertEqual(refunded["settlement"]["phase"], COMMITTED)
        self.assertEqual(refunded["settlement"]["claim"]["refund_bearer_policy"], "REQUESTER")
        self.assertFalse(refunded["settlement"]["claim"]["distribution_blocked"])
        self.assertEqual(refunded["settlement"]["claim"]["distributed_cash"], 97_000)
        self.assertEqual(line(refunded["settlement"]["claim"], "organizer")["cancelled_unpaid"], 0)
        # B5: distribution after the partial refund is accepted. No cash
        # remains, so it applies zero and claws nothing back.
        again = self.machine.distribute(
            "claim-1",
            idempotency_key="dist-2",
            order=["platform", "organizer"],
        )
        self.assertEqual(again["effect"], {"platform": 0, "organizer": 0})
        journal = self.machine.export_journal()
        self.assertEqual(len(journal), len(distributed_at) + 2)
        replayed = self.machine.distribute(
            "claim-1",
            idempotency_key="dist-2",
            order=["platform", "organizer"],
        )
        self.assertTrue(replayed["duplicate"])
        self.assertIsNone(replayed["applied"])
        self.assertEqual(self.machine.export_journal(), journal)
        restored = SettlementMachine.restore(json.loads(json.dumps(journal)))
        self.assertEqual(restored.canonical_state(), self.machine.canonical_state())
        self.assertFalse(restored.view("claim-1")["claim"]["distribution_blocked"])
        self.assertEqual(restored.view("claim-1")["claim"]["distributed_cash"], 97_000)
        report = restored.reconcile("claim-1", idempotency_key="recon-partial")
        self.assertTrue(report["matched"])
        self.assertEqual(report["entry_count"], len(journal))
        self.assertEqual(len(report["state_digest"]), 64)
        self.assertNotEqual(restored.export_journal(), distributed_at)

    def test_full_refund_acceptance_does_not_close_an_external_return(self):
        self.commit()
        self.machine.distribute(
            "claim-1",
            idempotency_key="dist-1",
            order=["platform", "organizer"],
        )
        refunded = self.machine.bind_refund(
            "claim-1",
            idempotency_key="refund-full",
            refund_id="refund-full",
            amount=100_000,
            beneficiary_role="buyer",
            reason="FULL",
        )["settlement"]["claim"]
        self.assertTrue(refunded["fixture_reclassified"])
        self.assertEqual(refunded["refund_bearer_policy"], "FIXTURE_FULL_GROSS_RECLASS")
        self.assertEqual(line(refunded, "platform")["recovery_due"], 5_000)
        self.assertEqual(line(refunded, "organizer")["recovery_due"], 92_000)
        self.assertIs(refunded["right_cancelled"], False)
        accepted = self.machine.observe_mock_cancel_acceptance(
            "claim-1",
            idempotency_key="accept-1",
            source_id="accept-1",
            amount=100_000,
        )["settlement"]
        self.assertEqual(accepted["phase"], COMMITTED)
        self.assertEqual(accepted["claim"]["refund_outstanding"], 0)
        self.assertEqual(accepted["claim"]["pg_adjustment_outstanding"], 100_000)
        self.assertEqual(accepted["claim"]["confirmed_cash"], 97_000)
        self.assertIs(accepted["claim"]["external_return_closed"], False)
        self.assertIs(accepted["bank_debit_observed"], False)
        self.assertIs(accepted["external_return_closed"], False)
        duplicate = self.machine.observe_mock_cancel_acceptance(
            "claim-1",
            idempotency_key="accept-1",
            source_id="accept-1",
            amount=100_000,
        )
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(self.machine.view("claim-1")["claim"]["pg_adjustment_outstanding"], 100_000)
        revived = SettlementMachine.restore(self.machine.export_journal())
        self.assertEqual(revived.view("claim-1")["claim"]["external_return_closed"], False)
        self.assertEqual(revived.canonical_state(), self.machine.canonical_state())

    def test_external_payment_attempts_leave_the_journal_unchanged(self):
        self.commit()
        before = self.machine.canonical_state()
        journal = self.machine.export_journal()
        for kind in ("PG_CHARGE", "PG_AUTHORIZE", "PG_CAPTURE", "PG_CANCEL", "BANK_DEBIT", "PAYOUT"):
            self.assertEqual(codes(lambda kind=kind: self.machine.reject_external(kind)), "EXTERNAL_PAYMENT_UNSUPPORTED")
        self.assertEqual(codes(lambda: self.machine.reject_external(" ")), "INVALID_ID")
        self.assertEqual(self.machine.canonical_state(), before)
        self.assertEqual(self.machine.export_journal(), journal)
        self.assertIs(self.machine.view("claim-1")["funds_executed"], False)
        self.assertEqual(self.machine.view("claim-1")["external_payment"], "UNSUPPORTED")
        detached = self.machine.export_journal()
        detached.clear()
        self.assertEqual(len(self.machine.export_journal()), len(journal))

    def test_later_statement_stays_on_commit_and_cases_do_not_share_cash(self):
        self.machine.initiate(
            "claim-1",
            idempotency_key="init-1",
            trade_id="trade-1",
            gross=100_000,
            debtor_role="fixture-merchant",
            policy=policy(),
        )
        self.machine.authorize("claim-1", idempotency_key="auth-1")
        self.machine.capture("claim-1", idempotency_key="cap-1")
        self.machine.commit(
            "claim-1",
            idempotency_key="commit-1",
            movement_id="part-1",
            gross=60_000,
            amount=60_000,
            fee=0,
            tax=0,
            held=0,
            adjustment=0,
        )
        self.assertEqual(
            codes(lambda: self.machine.commit(
                "claim-1",
                idempotency_key="commit-2",
                movement_id="part-2",
                gross=40_000,
                amount=37_000,
                fee=3_000,
                tax=0,
                held=0,
                adjustment=0,
            )),
            "ILLEGAL_TRANSITION",
        )
        second = self.machine.observe_statement(
            "claim-1",
            idempotency_key="stmt-2",
            movement_id="part-2",
            gross=40_000,
            amount=37_000,
            fee=3_000,
            tax=0,
            held=0,
            adjustment=0,
        )
        self.assertEqual(second["settlement"]["phase"], COMMITTED)
        self.assertEqual(second["settlement"]["commit_movement_id"], "part-1")
        self.assertEqual(second["settlement"]["claim"]["confirmed_cash"], 97_000)
        self.assertEqual(second["settlement"]["claim"]["receivable_open"], 0)
        self.machine.initiate(
            "claim-2",
            idempotency_key="init-2",
            trade_id="trade-2",
            gross=10_000,
            debtor_role="fixture-merchant",
            policy=policy(fee_bps=0),
        )
        self.assertEqual(self.machine.view("claim-2")["phase"], "INITIATED")
        self.assertIsNone(self.machine.view("claim-2")["claim"])
        self.assertEqual(self.machine.view("claim-1")["claim"]["confirmed_cash"], 97_000)

    def test_reconcile_matches_restore_and_does_not_enter_the_economic_journal(self):
        self.commit()
        journal = self.machine.export_journal()
        first = self.machine.reconcile("claim-1", idempotency_key="recon-1")
        self.assertTrue(first["matched"])
        self.assertEqual(first["entry_count"], len(journal))
        self.assertEqual(self.machine.export_journal(), journal)
        second = self.machine.reconcile("claim-1", idempotency_key="recon-1")
        self.assertTrue(second["duplicate"])
        self.assertEqual(second["state_digest"], first["state_digest"])
        self.assertEqual(
            codes(lambda: self.machine.reconcile("claim-2", idempotency_key="recon-1")),
            "IDEMPOTENCY_CONFLICT",
        )
        restored = SettlementMachine.restore(journal)
        self.assertEqual(restored.canonical_state(), self.machine.canonical_state())
        again = restored.reconcile("claim-1", idempotency_key="recon-1")
        self.assertFalse(again["duplicate"])
        self.assertTrue(again["matched"])
        self.assertEqual(again["state_digest"], first["state_digest"])
        self.assertEqual(restored.export_journal(), journal)


if __name__ == "__main__":
    unittest.main()
