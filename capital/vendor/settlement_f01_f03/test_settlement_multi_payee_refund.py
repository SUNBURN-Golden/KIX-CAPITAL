"""Seeded multi-payee refund corpus for the F01-F03 settlement mock and FSM.

Builder-authored harness (the author is the builder): a green run is not an
independent PASS, not an accounting or legal treatment, and not a payment.
Fixtures are synthetic KRW integers, not policy values. No wall clock, no
os.urandom, no network, no files. Seeds are fixed in
settlement_property_support.SEEDS.

Oracles are re-derived from docs/contracts/SETTLEMENT_DISTRIBUTION_F01_F03.md
sections 1-6 and 9 under the adopted section-7 postures (L0, W0, R0, S0, T0,
B5, P0 of SET-POLICY-DRAFT-0.4). The coverage mapping and the section-8 class
table are in validation/2026-10-21-settlement-multi-payee-refund-corpus/README.md.

This module narrows the fin-multi-payee-refund-proof register gap inside the
MOCK bound; it does not implement or close that pending node. It asserts no
waterfall numbers, no remainder-unit payee, no resale bps, no tax or reserve
rate and no legal debtor (all UNDETERMINED). The mock partial-refund bearer
is the adopted B5 REQUESTER; the legal refund debtor stays UNDETERMINED. It
asserts no external return closure.

Properties:
  (f) original waterfall split conservation: per payee
      face = distributed + cancelled_unpaid + outstanding, faces sum to gross,
      held across every seeded refund sequence including rejected and
      replayed commands
  (g) refund reservation per payee: the first full-gross refund maps each
      payee's unpaid face to cancelled_unpaid and its paid cash to
      recovery_due; partial sums never reclassify
  (h) rejection atomicity: a rejected refund-family call leaves every claim
      view byte-identical, and a rejected FSM command leaves state_digest and
      the journal byte-identical
  (i) replay of refund commands: identical re-issue is a duplicate with no
      second effect; changed binding conflicts; same key with a different
      body is IDEMPOTENCY_CONFLICT; a rejected key is forgotten by restore
"""

import unittest
from unittest import mock

import mock_settlement
from mock_settlement import MockSettlement, SettlementError
from settlement_fsm import SettlementMachine
from settlement_property_support import (
    CONTRACT_MONEY_MAX,
    SEEDS,
    Mirror,
    RefundCorpusDriver,
    RefundMachineDriver,
    canon,
    check_claim_view,
    check_refund_view,
    policy,
    rng,
    statement_kwargs,
)


def code_of(fn):
    try:
        fn()
    except SettlementError as error:
        return error.code
    raise AssertionError("expected SettlementError")


def two_payee_book(gross, bps, residual="res-c", fee="fee-c"):
    book = MockSettlement()
    book.recognize_claim(
        "c", trade_id="t", gross=gross, debtor_role="d", policy=policy(bps, residual, fee)
    )
    return book


def two_payee_mirror(gross, bps, residual="res-c", fee="fee-c"):
    return Mirror("c", "t", gross, "d", bps, residual, fee)


def line(view, payee):
    return next(item for item in view["obligations"] if item["payee"] == payee)


def committed_machine(gross=10_000, bps=500, amount=None):
    """INITIATED -> AUTHORIZED -> CAPTURED -> COMMITTED with one statement."""

    if amount is None:
        amount = gross
    machine = SettlementMachine()
    machine.initiate(
        "s",
        idempotency_key="k-init",
        trade_id="t",
        gross=gross,
        debtor_role="d",
        policy=policy(bps, "res-s", "fee-s"),
    )
    machine.authorize("s", idempotency_key="k-auth")
    machine.capture("s", idempotency_key="k-cap")
    machine.commit(
        "s",
        idempotency_key="k-commit",
        **statement_kwargs("mv-1", (gross, amount, gross - amount, 0, 0, 0, None)),
    )
    return machine


class WaterfallConservationCorpusTests(unittest.TestCase):
    """(f) split conservation held through refund-dense seeded sequences."""

    REQUIRED = (
        "ok:observe_settlement_statement",
        "ok:apply_distribution",
        "ok:bind_refund",
        "ok:observe_mock_cancel_acceptance",
        "lines:1",
        "lines:2",
        "replay:statement",
        "replay:refund",
        "replay:accept",
        "reclass@0",
        "reclass@partial",
        "reclass@full",
        "partial-sum-to-gross",
        "INVALID_AMOUNT",
        "CURRENCY_UNSUPPORTED",
        "CLAIM_BINDING_CONFLICT",
        "UNKNOWN_CLAIM",
        "REFUND_CEILING",
        "REFUND_BINDING_CONFLICT",
        "REFUND_BENEFICIARY_CONFLICT",
        "REFUND_OBLIGATION_REQUIRED",
        "REFUND_ACCEPTANCE_EXCEEDS_OBLIGATION",
        "ACCEPTANCE_BINDING_CONFLICT",
        "DISTRIBUTION_ORDER_MISMATCH",
        "DISTRIBUTION_ORDER_FROZEN",
    )

    def test_f_seeded_multi_payee_sequences_conserve_through_refunds(self):
        total = {}
        for seed in SEEDS:
            driver = RefundCorpusDriver(seed)
            with self.subTest(seed=seed):
                driver.run()
            for name, count in driver.counts.items():
                total[name] = total.get(name, 0) + count
        # Guard against a vacuous run: the corpus must reach each family.
        for name in self.REQUIRED:
            self.assertGreater(total.get(name, 0), 0, name)

    def test_f_directed_two_payee_sequence_conserves_through_refunds(self):
        for seed in SEEDS:
            r = rng(seed)
            gross = r.choice((3, 10_000, 99_999, CONTRACT_MONEY_MAX))
            bps = r.choice((1, 5000, 9999, r.randint(1, 9999)))
            with self.subTest(seed=seed, gross=gross, bps=bps):
                book = two_payee_book(gross, bps)
                mirror = two_payee_mirror(gross, bps)
                half = gross // 2 or 1
                vals = (half, half, 0, 0, 0, 0, None)
                book.observe_settlement_statement("c", **statement_kwargs("m-1", vals))
                mirror.apply_statement("m-1", vals)
                order = sorted(mirror.faces)
                applied = book.apply_distribution("c", order=order)["applied"]
                self.assertEqual(applied, mirror.apply_distribution(order))
                part = max(1, gross // 3)
                book.bind_refund(
                    "c", refund_id="r-1", amount=part, beneficiary_role="buyer", reason="why"
                )
                mirror.apply_refund("r-1", (part, "buyer", "why"))
                view = book.view("c")
                check_claim_view(view, mirror)
                check_refund_view(view)
                self.assertEqual(view["refund_bearer_policy"], "REQUESTER")
                self.assertIs(view["distribution_blocked"], False)
                # A second partial refund completes the gross sum without a reclass.
                book.bind_refund(
                    "c",
                    refund_id="r-2",
                    amount=gross - part,
                    beneficiary_role="buyer",
                    reason="why",
                )
                mirror.apply_refund("r-2", (gross - part, "buyer", "why"))
                view = book.view("c")
                check_claim_view(view, mirror)
                check_refund_view(view)
                self.assertEqual(view["refund_face"], gross)
                self.assertIs(view["fixture_reclassified"], False)
                book.observe_mock_cancel_acceptance("c", source_id="a-1", amount=part)
                mirror.apply_acceptance("a-1", part)
                view = book.view("c")
                check_claim_view(view, mirror)
                check_refund_view(view)
                self.assertEqual(view["refund_outstanding"], gross - part)
                self.assertIs(view["external_return_closed"], False)

    def test_f_distinct_payee_labels_per_claim_do_not_share_lines(self):
        for seed in SEEDS[:4]:
            r = rng(seed)
            book = MockSettlement()
            mirrors = {}
            cash = {}
            for cid, residual, fee in (("c1", "res-1", "fee-1"), ("c2", "res-2", "fee-2")):
                bps = r.randint(1, 9999)
                book.recognize_claim(
                    cid,
                    trade_id=f"t-{cid}",
                    gross=10_000,
                    debtor_role="d",
                    policy=policy(bps, residual, fee),
                )
                mirrors[cid] = Mirror(cid, f"t-{cid}", 10_000, "d", bps, residual, fee)
                cash[cid] = 0
            for index in range(6):
                cid = r.choice(sorted(mirrors))
                amount = r.randint(1, 500)
                vals = (amount, amount, 0, 0, 0, 0, None)
                book.observe_settlement_statement(cid, **statement_kwargs(f"m-{cid}-{index}", vals))
                mirrors[cid].apply_statement(f"m-{cid}-{index}", vals)
                cash[cid] += amount
                for key, mirror in mirrors.items():
                    view = book.view(key)
                    check_claim_view(view, mirror)
                    check_refund_view(view)
                    self.assertEqual(view["confirmed_cash"], cash[key], (seed, key))
                    self.assertEqual(
                        sorted(item["payee"] for item in view["obligations"]),
                        sorted(mirror.faces),
                    )


class RefundReservationPerPayeeTests(unittest.TestCase):
    """(g) the first full-gross refund reserves each payee's share."""

    def test_g_reservation_at_zero_distribution_reserves_full_faces(self):
        book = two_payee_book(10_000, 2500)
        refunded = book.bind_refund(
            "c", refund_id="r", amount=10_000, beneficiary_role="buyer", reason="why"
        )["claim"]
        self.assertEqual(refunded["refund_bearer_policy"], "FIXTURE_FULL_GROSS_RECLASS")
        for item in refunded["obligations"]:
            self.assertEqual(item["distributed"], 0)
            self.assertEqual(item["cancelled_unpaid"], item["face"])
            self.assertEqual(item["recovery_due"], 0)
            self.assertEqual(item["outstanding"], 0)
        self.assertEqual(refunded["recovery_due"], 0)
        check_refund_view(refunded)

    def test_g_reservation_at_partial_distribution_is_per_payee(self):
        book = two_payee_book(100_000, 500)
        book.observe_settlement_statement(
            "c", **statement_kwargs("m-1", (100_000, 10_000, 90_000, 0, 0, 0, None))
        )
        # Caller order puts the fee payee first: it is paid in full, the
        # residual payee takes the rest of the confirmed cash.
        book.apply_distribution("c", order=["fee-c", "res-c"])
        refunded = book.bind_refund(
            "c", refund_id="r", amount=100_000, beneficiary_role="buyer", reason="why"
        )["claim"]
        fee_line = line(refunded, "fee-c")
        res_line = line(refunded, "res-c")
        self.assertEqual(
            (fee_line["distributed"], fee_line["cancelled_unpaid"], fee_line["recovery_due"]),
            (5_000, 0, 5_000),
        )
        self.assertEqual(
            (res_line["distributed"], res_line["cancelled_unpaid"], res_line["recovery_due"]),
            (5_000, 90_000, 5_000),
        )
        self.assertEqual(refunded["recovery_due"], refunded["distributed_cash"])
        self.assertEqual(
            sum(item["cancelled_unpaid"] for item in refunded["obligations"]),
            refunded["gross"] - refunded["distributed_cash"],
        )
        check_refund_view(refunded)

    def test_g_reservation_at_full_distribution_is_all_recovery(self):
        book = two_payee_book(10_000, 2500)
        book.observe_settlement_statement(
            "c", **statement_kwargs("m-1", (10_000, 10_000, 0, 0, 0, 0, None))
        )
        book.apply_distribution("c", order=["res-c", "fee-c"])
        refunded = book.bind_refund(
            "c", refund_id="r", amount=10_000, beneficiary_role="buyer", reason="why"
        )["claim"]
        for item in refunded["obligations"]:
            self.assertEqual(item["recovery_due"], item["face"])
            self.assertEqual(item["cancelled_unpaid"], 0)
        self.assertEqual(refunded["recovery_due"], 10_000)
        check_refund_view(refunded)

    def test_g_characterization_post_reclass_distribution_applies_zero(self):
        # Section 8 class B: sections 4-5 do not name "distribute after a
        # reclass freezes the order". Only the zero applied map and
        # conservation are asserted; the freeze itself is not pinned.
        book = two_payee_book(10_000, 2500)
        book.bind_refund("c", refund_id="r", amount=10_000, beneficiary_role="buyer", reason="why")
        book.observe_settlement_statement(
            "c", **statement_kwargs("m-1", (10_000, 10_000, 0, 0, 0, 0, None))
        )
        result = book.apply_distribution("c", order=["res-c", "fee-c"])
        self.assertEqual(result["applied"], {"res-c": 0, "fee-c": 0})
        view = book.view("c")
        self.assertEqual(view["distributed_cash"], 0)
        self.assertEqual(view["undistributed_cash"], 10_000)
        self.assertEqual(
            code_of(lambda: book.observe_mock_cancel_acceptance("c", source_id="a-x", amount=10_001)),
            "REFUND_ACCEPTANCE_EXCEEDS_OBLIGATION",
        )
        check_claim_view(view)
        check_refund_view(view)

    def test_g_partial_refunds_summing_to_gross_never_reclassify(self):
        book = two_payee_book(100_000, 500)
        book.observe_settlement_statement(
            "c", **statement_kwargs("m-1", (100_000, 60_000, 40_000, 0, 0, 0, None))
        )
        book.apply_distribution("c", order=["res-c", "fee-c"])
        book.bind_refund("c", refund_id="r-1", amount=30_000, beneficiary_role="buyer", reason="why")
        view = book.bind_refund(
            "c", refund_id="r-2", amount=70_000, beneficiary_role="buyer", reason="why"
        )["claim"]
        self.assertEqual(view["refund_face"], 100_000)
        self.assertIs(view["fixture_reclassified"], False)
        self.assertEqual(view["refund_bearer_policy"], "REQUESTER")
        self.assertIs(view["distribution_blocked"], False)
        for item in view["obligations"]:
            self.assertEqual(item["cancelled_unpaid"], 0)
            self.assertEqual(item["recovery_due"], 0)
        self.assertEqual(view["distributed_cash"], 60_000)
        # B5: distribution continues; the cash is already allocated, so the
        # frozen order applies zero without touching faces.
        again = book.apply_distribution("c", order=["res-c", "fee-c"])
        self.assertEqual(again["applied"], {"res-c": 0, "fee-c": 0})
        self.assertEqual(
            code_of(
                lambda: book.bind_refund(
                    "c", refund_id="r-3", amount=1, beneficiary_role="buyer", reason="why"
                )
            ),
            "REFUND_CEILING",
        )
        check_refund_view(book.view("c"))


class RefundRejectionAtomicityTests(unittest.TestCase):
    """(h) rejected refund-family calls are atomic."""

    def test_h_rejected_mock_refund_calls_leave_every_view_byte_identical(self):
        book = two_payee_book(10_000, 2500)
        book.recognize_claim(
            "d", trade_id="t-2", gross=50_000, debtor_role="d", policy=policy(7000, "res-d", "fee-d")
        )

        def views():
            return {cid: canon(book.view(cid)) for cid in ("c", "d")}

        rejected = [
            lambda: book.bind_refund(
                "c", refund_id="r-x", amount=0, beneficiary_role="b", reason="w"
            ),
            lambda: book.observe_mock_cancel_acceptance("c", source_id="a-x", amount=1),
            lambda: book.bind_refund(
                "missing", refund_id="r-x", amount=1, beneficiary_role="b", reason="w"
            ),
        ]
        expected = ["INVALID_AMOUNT", "REFUND_OBLIGATION_REQUIRED", "UNKNOWN_CLAIM"]
        for call, code in zip(rejected, expected):
            before = views()
            with self.subTest(code=code):
                self.assertEqual(code_of(call), code)
                self.assertEqual(views(), before)
        book.bind_refund("c", refund_id="r-1", amount=4_000, beneficiary_role="b", reason="w")
        book.observe_mock_cancel_acceptance("c", source_id="a-1", amount=1_000)
        rejected = [
            (
                lambda: book.bind_refund(
                    "c", refund_id="r-2", amount=7_000, beneficiary_role="b", reason="w"
                ),
                "REFUND_CEILING",
            ),
            (
                lambda: book.bind_refund(
                    "c", refund_id="r-1", amount=4_001, beneficiary_role="b", reason="w"
                ),
                "REFUND_BINDING_CONFLICT",
            ),
            (
                lambda: book.bind_refund(
                    "c", refund_id="r-4", amount=1, beneficiary_role="other", reason="w"
                ),
                "REFUND_BENEFICIARY_CONFLICT",
            ),
            (
                lambda: book.observe_mock_cancel_acceptance("c", source_id="a-2", amount=3_001),
                "REFUND_ACCEPTANCE_EXCEEDS_OBLIGATION",
            ),
            (
                lambda: book.observe_mock_cancel_acceptance("c", source_id="a-1", amount=999),
                "ACCEPTANCE_BINDING_CONFLICT",
            ),
            (
                lambda: book.apply_distribution("c", order=["res-c"]),
                "DISTRIBUTION_ORDER_MISMATCH",
            ),
            (
                lambda: book.observe_mock_cancel_acceptance("c", source_id="a-3", amount=True),
                "INVALID_AMOUNT",
            ),
        ]
        for call, code in rejected:
            before = views()
            with self.subTest(code=code):
                self.assertEqual(code_of(call), code)
                self.assertEqual(views(), before)
        for cid in ("c", "d"):
            check_claim_view(book.view(cid))
            check_refund_view(book.view(cid))

    def test_h_rejected_fsm_refund_commands_leave_digest_and_journal_identical(self):
        machine = committed_machine(gross=10_000, amount=6_000)
        calls = [
            (
                lambda key: machine.observe_mock_cancel_acceptance(
                    "s", idempotency_key=key, source_id="a-0", amount=1
                ),
                "REFUND_OBLIGATION_REQUIRED",
            ),
            (
                lambda key: machine.bind_refund(
                    "s", idempotency_key=key, refund_id="rf-0", amount=10_001,
                    beneficiary_role="b", reason="w",
                ),
                "REFUND_CEILING",
            ),
            (
                lambda key: machine.bind_refund(
                    "s", idempotency_key=key, refund_id="rf-0", amount=0,
                    beneficiary_role="b", reason="w",
                ),
                "INVALID_AMOUNT",
            ),
        ]
        serial = 0
        for call, code in calls:
            digest, journal = machine.state_digest(), machine.export_journal()
            serial += 1
            with self.subTest(code=code):
                self.assertEqual(code_of(lambda: call(f"k-bad-{serial}")), code)
                self.assertEqual(machine.state_digest(), digest)
                self.assertEqual(machine.export_journal(), journal)
        machine.bind_refund(
            "s", idempotency_key="k-rf-1", refund_id="rf-1", amount=4_000,
            beneficiary_role="b", reason="w",
        )
        machine.observe_mock_cancel_acceptance(
            "s", idempotency_key="k-ac-1", source_id="a-1", amount=1_000
        )
        calls = [
            (
                lambda key: machine.bind_refund(
                    "s", idempotency_key=key, refund_id="rf-1", amount=4_001,
                    beneficiary_role="b", reason="w",
                ),
                "REFUND_BINDING_CONFLICT",
            ),
            (
                lambda key: machine.bind_refund(
                    "s", idempotency_key=key, refund_id="rf-9", amount=1,
                    beneficiary_role="other", reason="w",
                ),
                "REFUND_BENEFICIARY_CONFLICT",
            ),
            (
                lambda key: machine.observe_mock_cancel_acceptance(
                    "s", idempotency_key=key, source_id="a-2", amount=3_001
                ),
                "REFUND_ACCEPTANCE_EXCEEDS_OBLIGATION",
            ),
            (
                lambda key: machine.observe_mock_cancel_acceptance(
                    "s", idempotency_key=key, source_id="a-1", amount=999
                ),
                "ACCEPTANCE_BINDING_CONFLICT",
            ),
            (
                lambda key: machine.distribute("s", idempotency_key=key, order=["res-s"]),
                "DISTRIBUTION_ORDER_MISMATCH",
            ),
            (
                lambda key: machine.bind_refund(
                    "s", idempotency_key=key, refund_id="rf-2", amount=6_001,
                    beneficiary_role="b", reason="w",
                ),
                "REFUND_CEILING",
            ),
        ]
        for call, code in calls:
            digest, journal = machine.state_digest(), machine.export_journal()
            serial += 1
            with self.subTest(code=code):
                self.assertEqual(code_of(lambda: call(f"k-bad-{serial}")), code)
                self.assertEqual(machine.state_digest(), digest)
                self.assertEqual(machine.export_journal(), journal)
        view = machine.view("s")
        self.assertEqual(view["claim"]["refund_face"], 4_000)
        check_refund_view(view["claim"])


class RefundReplayTests(unittest.TestCase):
    """(i) refund commands replay as duplicates and rejected keys re-raise."""

    REQUIRED = (
        "ok:initiate",
        "ok:capture",
        "ok:commit",
        "ok:bind_refund",
        "ok:bind_refund@CAPTURED",
        "ok:bind_refund@COMMITTED",
        "ok:observe_mock_cancel_acceptance",
        "ok:distribute",
        "replay:bind_refund",
        "replay:observe_mock_cancel_acceptance",
        "restored-replay:bind_refund",
        "restored-replay:observe_mock_cancel_acceptance",
        "reject:IDEMPOTENCY_CONFLICT",
        "reject:TERMINAL_IMMUTABLE",
        "reject:REFUND_CEILING",
        "reject:REFUND_ACCEPTANCE_EXCEEDS_OBLIGATION",
        "restore-check",
    )

    def test_i_seeded_fsm_refund_command_sequences(self):
        total = {}
        for seed in SEEDS:
            driver = RefundMachineDriver(seed)
            with self.subTest(seed=seed):
                driver.run()
            for name, count in driver.counts.items():
                total[name] = total.get(name, 0) + count
        for name in self.REQUIRED:
            self.assertGreater(total.get(name, 0), 0, name)

    def test_i_mock_refund_replays_are_duplicates_after_later_changes(self):
        book = two_payee_book(10_000, 2500)
        first = book.bind_refund(
            "c", refund_id="r-1", amount=4_000, beneficiary_role="b", reason="w"
        )
        self.assertFalse(first["duplicate"])
        # Later state changes: a statement and an acceptance on the same claim.
        book.observe_settlement_statement(
            "c", **statement_kwargs("m-1", (10_000, 9_000, 1_000, 0, 0, 0, None))
        )
        book.observe_mock_cancel_acceptance("c", source_id="a-1", amount=500)
        before = canon(book.view("c"))
        again = book.bind_refund(
            "c", refund_id="r-1", amount=4_000, beneficiary_role="b", reason="w"
        )
        self.assertEqual((again["duplicate"], again["applied"]), (True, None))
        self.assertEqual(canon(book.view("c")), before)
        changed = dict(refund_id="r-1", amount=4_001, beneficiary_role="b", reason="w")
        self.assertEqual(
            code_of(lambda: book.bind_refund("c", **changed)), "REFUND_BINDING_CONFLICT"
        )
        self.assertEqual(canon(book.view("c")), before)
        dup = book.observe_mock_cancel_acceptance("c", source_id="a-1", amount=500)
        self.assertEqual((dup["duplicate"], dup["applied"]), (True, None))
        self.assertEqual(canon(book.view("c")), before)
        self.assertEqual(
            code_of(lambda: book.observe_mock_cancel_acceptance("c", source_id="a-1", amount=501)),
            "ACCEPTANCE_BINDING_CONFLICT",
        )
        self.assertEqual(canon(book.view("c")), before)
        check_refund_view(book.view("c"))

    def test_i_fsm_refund_key_replay_returns_the_first_result_verbatim(self):
        machine = committed_machine(gross=10_000, amount=6_000)
        first = machine.bind_refund(
            "s", idempotency_key="k-rf", refund_id="rf-1", amount=4_000,
            beneficiary_role="b", reason="w",
        )
        # Later accepted command moves the view.
        machine.observe_mock_cancel_acceptance(
            "s", idempotency_key="k-ac", source_id="a-1", amount=1_000
        )
        digest, journal = machine.state_digest(), machine.export_journal()
        again = machine.bind_refund(
            "s", idempotency_key="k-rf", refund_id="rf-1", amount=4_000,
            beneficiary_role="b", reason="w",
        )
        self.assertEqual(canon(again), canon(dict(first, duplicate=True, applied=None)))
        self.assertEqual(machine.state_digest(), digest)
        self.assertEqual(machine.export_journal(), journal)
        self.assertEqual(
            code_of(
                lambda: machine.bind_refund(
                    "s", idempotency_key="k-rf", refund_id="rf-1", amount=4_001,
                    beneficiary_role="b", reason="w",
                )
            ),
            "IDEMPOTENCY_CONFLICT",
        )
        self.assertEqual(machine.state_digest(), digest)
        self.assertEqual(machine.export_journal(), journal)

    def test_i_fsm_rejected_refund_key_replays_live_and_is_forgotten_by_restore(self):
        machine = SettlementMachine()
        machine.initiate(
            "s", idempotency_key="k-init", trade_id="t", gross=10_000,
            debtor_role="d", policy=policy(500, "res-s", "fee-s"),
        )
        machine.authorize("s", idempotency_key="k-auth")
        machine.capture("s", idempotency_key="k-cap")
        bad = dict(refund_id="rf", amount=0, beneficiary_role="b", reason="w")
        self.assertEqual(
            code_of(lambda: machine.bind_refund("s", idempotency_key="k-rf", **bad)),
            "INVALID_AMOUNT",
        )
        self.assertEqual(
            code_of(lambda: machine.bind_refund("s", idempotency_key="k-rf", **bad)),
            "INVALID_AMOUNT",
        )
        fixed = dict(bad, amount=10)
        self.assertEqual(
            code_of(lambda: machine.bind_refund("s", idempotency_key="k-rf", **fixed)),
            "IDEMPOTENCY_CONFLICT",
        )
        restored = SettlementMachine.restore(machine.export_journal())
        accepted = restored.bind_refund("s", idempotency_key="k-rf", **fixed)
        self.assertEqual(accepted["duplicate"], False)
        self.assertEqual(accepted["applied"], "bind_refund")
        # The live machine still holds the rejected key; the restored one does not.
        self.assertEqual(
            code_of(lambda: machine.bind_refund("s", idempotency_key="k-rf", **fixed)),
            "IDEMPOTENCY_CONFLICT",
        )

    def test_i_restored_machine_replays_every_refund_key(self):
        machine = committed_machine(gross=10_000, amount=6_000)
        journal_keys = [
            ("bind_refund", "k-rf-1", dict(refund_id="rf-1", amount=4_000, beneficiary_role="b", reason="w")),
            ("observe_mock_cancel_acceptance", "k-ac-1", dict(source_id="a-1", amount=1_000)),
            ("bind_refund", "k-rf-2", dict(refund_id="rf-2", amount=5_000, beneficiary_role="b", reason="w")),
        ]
        firsts = {}
        for op, key, kwargs in journal_keys:
            firsts[key] = getattr(machine, op)("s", idempotency_key=key, **kwargs)["settlement"]
        restored = SettlementMachine.restore(machine.export_journal())
        self.assertEqual(restored.state_digest(), machine.state_digest())
        digest = restored.state_digest()
        for op, key, kwargs in journal_keys:
            result = getattr(restored, op)("s", idempotency_key=key, **kwargs)
            self.assertTrue(result["duplicate"])
            self.assertEqual(result["settlement"], firsts[key])
        self.assertEqual(restored.state_digest(), digest)


class MultiPayeeControlTests(unittest.TestCase):
    """The refund oracles must fail on deliberately broken in-memory copies.

    Each control patches an attribute in memory with unittest.mock and never
    touches a source file. AssertionError is required: a SettlementError from
    the mock's own guard would mean the oracle did not see the fault.
    MockSettlement._invariant is silenced where the mock's guard would mask
    the oracle.
    """

    def test_control_reclass_that_inflates_recovery_due_is_caught(self):
        real = MockSettlement.bind_refund

        def inflate(self, claim_id, **kwargs):
            out = real(self, claim_id, **kwargs)
            claim = self._claims.get(claim_id)
            if claim is not None and claim["fixture_reclassified"]:
                name = sorted(claim["obligations"])[0]
                claim["obligations"][name]["recovery_due"] += 1
            return out

        with mock.patch.object(MockSettlement, "bind_refund", inflate), mock.patch.object(
            MockSettlement, "_invariant", lambda self, claim: None
        ):
            with self.assertRaises(AssertionError):
                for seed in SEEDS:
                    RefundCorpusDriver(seed).run()
        self.assertIs(MockSettlement.bind_refund, real)

    def test_control_full_refund_that_does_not_reclassify_is_caught(self):
        real = MockSettlement.bind_refund

        def no_flag(self, claim_id, **kwargs):
            out = real(self, claim_id, **kwargs)
            claim = self._claims.get(claim_id)
            if claim is not None and claim["refund_face"] == claim["gross"]:
                claim["fixture_reclassified"] = False
            return out

        with mock.patch.object(MockSettlement, "bind_refund", no_flag), mock.patch.object(
            MockSettlement, "_invariant", lambda self, claim: None
        ):
            with self.assertRaises(AssertionError):
                for seed in SEEDS:
                    RefundCorpusDriver(seed).run()
        self.assertIs(MockSettlement.bind_refund, real)

    def test_control_rejected_refund_that_mutates_state_is_caught(self):
        real = MockSettlement.bind_refund

        def mutate_then_raise(self, claim_id, **kwargs):
            try:
                return real(self, claim_id, **kwargs)
            except SettlementError:
                claim = self._claims.get(claim_id)
                if claim is not None:
                    claim["refund_face"] += 1
                raise

        with mock.patch.object(MockSettlement, "bind_refund", mutate_then_raise):
            with self.assertRaisesRegex(AssertionError, "view changed after a rejected call"):
                for seed in SEEDS:
                    RefundCorpusDriver(seed).run()
        self.assertIs(MockSettlement.bind_refund, real)

    def test_control_replay_that_returns_a_mutated_first_result_is_caught(self):
        real = SettlementMachine._replay_if_known

        def skewed(self, key, request):
            out = real(self, key, request)
            if out is not None and out.get("settlement") is not None:
                out["settlement"] = dict(out["settlement"], gross=out["settlement"]["gross"] + 1)
            return out

        with mock.patch.object(SettlementMachine, "_replay_if_known", skewed):
            with self.assertRaises(AssertionError):
                for seed in SEEDS:
                    RefundMachineDriver(seed).run()
        self.assertIs(SettlementMachine._replay_if_known, real)


if __name__ == "__main__":
    unittest.main()
