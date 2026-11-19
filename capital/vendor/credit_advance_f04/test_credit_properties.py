"""Seeded property suite for the F04 credit mock and its acceptance machine.

Author-side harness. The author is the builder, so a green run here is not an
independent PASS, not a regulated credit product, and not a loan or payment.
Fixtures are synthetic KRW integers, not policy values. No wall clock, no
os.urandom, no network, no files. Seeds are fixed in
credit_property_support.SEEDS.

Oracles are re-derived from docs/contracts/CREDIT_ADVANCE_F04.md sections 1-4
and 7 (option A adopted draft). Nothing is imported from the mock or the FSM
except the objects under test. The mapping to existing tests and the section 8
classes are in validation/2026-10-17-credit-f04-seeded-property-suite/README.md.

This suite does not implement or close the pending fin-credit-exposure-
reconciliation node or the F04 real-funds lock. It asserts no APR, rank, fee,
party, perfection or limit-recalculation formula (all UNDETERMINED).

Properties:
  (a) face, reserved_open, outstanding, repaid, recovery_due are bounded
      non-negative integers with the contract's relations
  (b) advances on one claim never reserve more than its unpaid face; cash and
      recovery_due never add capacity
  (c) a bound draw needs COMMITTED; the face snapshot stays frozen
  (d) an open refund blocks new draws; a release is not a repayment
  (e) close is rejected while exposure remains
  (f) a raising command leaves state_digest unchanged, keys replay first results
  (g) restore(export_journal()) reproduces the digest at every prefix
  (h) reject_unsupported and attempt_execution leave the journal unchanged
"""

import unittest
from unittest import mock

import credit_fsm
import mock_credit
from credit_fsm import CreditError, CreditMachine
from credit_property_support import (
    ALWAYS_FALSE_FLAGS,
    CONTRACT_MONEY_MAX,
    EXECUTION_TABLE,
    MACHINE_CODES,
    MOCK_CODES,
    NOT_KINDS,
    SEEDS,
    STUB_KINDS,
    UNSUPPORTED_TABLE,
    MachineDriver,
    MockDriver,
    StubSettlementSource,
    check_gate_matrix,
    code_of,
    gate_fixture,
    make_face,
    mock_code_of,
)
from mock_credit import MockCredit

MOCK_STEPS = 250
MACHINE_STEPS = 220
PREFIX_SEEDS = (1, 8, 21)

_RUNS = {}


def mock_runs():
    if "mock" not in _RUNS:
        _RUNS["mock"] = []
        for seed in SEEDS:
            driver = MockDriver(seed)
            driver.run(MOCK_STEPS)
            _RUNS["mock"].append(driver)
    return _RUNS["mock"]


def machine_runs():
    if "machine" not in _RUNS:
        _RUNS["machine"] = []
        for seed in SEEDS:
            driver = MachineDriver(seed)
            driver.run(MACHINE_STEPS, restore_every=25)
            if seed in PREFIX_SEEDS:
                driver.check_prefixes()
            _RUNS["machine"].append(driver)
    return _RUNS["machine"]


def total(drivers, name):
    return sum(driver.counters.get(name, 0) for driver in drivers)


def all_codes(drivers):
    out = set()
    for driver in drivers:
        out |= driver.codes
    return out


def plain(claim="claim-a", faces=(60_000, 30_000), dists=(10_000, 0), **kwargs):
    return make_face(claim, faces, dists, kwargs.pop("variant", "plain"), **kwargs)


def note(credit, advance_id, face, amount, role="role-0"):
    return credit.note_advance(advance_id, face=face, amount=amount, beneficiary_role=role)


class ContractConstantTests(unittest.TestCase):
    def test_typed_oracles_agree_with_the_modules(self):
        self.assertEqual(mock_credit.MONEY_MAX, CONTRACT_MONEY_MAX)
        self.assertEqual(tuple(sorted(mock_credit._flags())), tuple(sorted(ALWAYS_FALSE_FLAGS)))
        self.assertEqual(dict(mock_credit.EXECUTION_KINDS), EXECUTION_TABLE)
        table = {kind: "REAL_FUNDS_FORBIDDEN" for kind in credit_fsm._REAL_FUNDS}
        table.update({kind: "CREDIT_PRODUCT_UNDEFINED" for kind in credit_fsm._UNDEFINED_PRODUCT})
        self.assertEqual(table, UNSUPPORTED_TABLE)
        allowed = {op: tuple(sorted(phases)) for op, phases in credit_fsm._ALLOWED.items()}
        self.assertEqual(allowed["draw"], ("APPROVED",))
        self.assertEqual(allowed["repay"], ("DRAWN",))
        self.assertEqual(allowed["cancel"], ("APPROVED", "OFFERED"))
        self.assertEqual(allowed["bind_settlement"], ("APPROVED", "OFFERED"))
        self.assertEqual(sorted(credit_fsm.TERMINAL_PHASES), ["CANCELLED", "CLOSED", "DEFAULTED", "REJECTED"])
        self.assertTrue(MOCK_CODES < MACHINE_CODES)
        self.assertNotIn("MOCK_INVARIANT", MACHINE_CODES)


class MockPropertyTests(unittest.TestCase):
    def test_seeded_sequences_keep_ceiling_inertness_and_first_results(self):
        drivers = mock_runs()
        for name in ("note_advance:ok", "note_advance:dup", "release_note:ok", "release_note:dup", "execute"):
            self.assertGreater(total(drivers, name), 0, name)
        seen = all_codes(drivers)
        for code in ("ADVANCE_EXCEEDS_OPEN_FACE", "FACE_SNAPSHOT_FROZEN", "REFUND_OBLIGATION_OPEN",
                     "ADVANCE_BINDING_CONFLICT", "CREDIT_PRODUCT_UNDEFINED", "INVALID_AMOUNT", "INVALID_ID",
                     "SETTLEMENT_FACE_MISMATCH", "SETTLEMENT_FACE_NOT_MOCK", "SETTLEMENT_FACE_FIELDS",
                     "SETTLEMENT_FACE_TYPE", "CURRENCY_UNSUPPORTED", "UNKNOWN_ADVANCE", "EXECUTION_KIND",
                     "REAL_FUNDS_FORBIDDEN"):
            self.assertIn(code, seen)
        self.assertLessEqual(seen, MOCK_CODES)

    def test_ceiling_boundary_is_exact_and_cash_never_adds_capacity(self):
        for faces, dists in (((60_000, 30_000), (10_000, 0)), ((4, 3), (0, 0)),
                             ((CONTRACT_MONEY_MAX - 7, 7), (0, 0))):
            face, open_face = plain("claim-x", faces, dists, cash=CONTRACT_MONEY_MAX, recovery=CONTRACT_MONEY_MAX)
            credit = MockCredit()
            self.assertEqual(mock_code_of(lambda: note(credit, "adv-0", face, min(open_face + 1, CONTRACT_MONEY_MAX)
                                                       if open_face < CONTRACT_MONEY_MAX else 0)),
                             "ADVANCE_EXCEEDS_OPEN_FACE" if open_face < CONTRACT_MONEY_MAX else "INVALID_AMOUNT")
            self.assertEqual(mock_code_of(lambda: credit.view_claim("claim-x")), "UNKNOWN_CLAIM")
            first = open_face - 1 if open_face > 1 else open_face
            note(credit, "adv-1", face, first)
            claim = credit.view_claim("claim-x")
            self.assertEqual((claim["open_face"], claim["reserved_open"]), (open_face, first))
            self.assertEqual(claim["confirmed_cash_on_face"], CONTRACT_MONEY_MAX)
            self.assertEqual(claim["recovery_due_on_face"], CONTRACT_MONEY_MAX)
            rest = open_face - first
            if rest:
                self.assertEqual(mock_code_of(lambda: note(credit, "adv-2", face, rest + 1)),
                                 "ADVANCE_EXCEEDS_OPEN_FACE")
                note(credit, "adv-2", face, rest)
            self.assertEqual(mock_code_of(lambda: note(credit, "adv-3", face, 1)), "ADVANCE_EXCEEDS_OPEN_FACE")
            claim = credit.view_claim("claim-x")
            self.assertEqual((claim["reserved_open"], claim["residual_unreserved"]), (open_face, 0))

    def test_release_returns_exactly_the_noted_amount_and_is_not_repayment(self):
        face, open_face = plain()
        credit = MockCredit()
        note(credit, "adv-1", face, 50_000)
        note(credit, "adv-2", face, 30_000)
        released = credit.release_note("adv-1")
        self.assertEqual((released["advance"]["reserved_open"], released["advance"]["status"]), (30_000, "RELEASED"))
        for flag in ("repayment_observed", "funds_executed", "bank_debit_observed"):
            self.assertIs(released["advance"][flag], False)
        again = note(credit, "adv-1", face, 50_000)
        self.assertIs(again["duplicate"], True)
        self.assertEqual(credit.view("adv-1")["status"], "RELEASED")
        self.assertEqual(credit.view_claim("claim-a")["reserved_open"], 30_000)
        self.assertEqual(mock_code_of(lambda: note(credit, "adv-3", face, open_face - 30_000 + 1)),
                         "ADVANCE_EXCEEDS_OPEN_FACE")
        note(credit, "adv-3", face, open_face - 30_000)
        self.assertEqual(credit.view_claim("claim-a")["residual_unreserved"], 0)

    def test_open_refund_blocks_a_note_and_a_later_settlement_face_is_frozen_out(self):
        credit = MockCredit()
        refund, _ignored = plain(variant="open-refund", refund=5)
        self.assertEqual(mock_code_of(lambda: note(credit, "adv-r", refund, 1)), "REFUND_OBLIGATION_OPEN")
        self.assertEqual(mock_code_of(lambda: credit.view("adv-r")), "UNKNOWN_ADVANCE")
        self.assertEqual(mock_code_of(lambda: credit.view_claim("claim-a")), "UNKNOWN_CLAIM")
        face, open_face = plain()
        note(credit, "adv-1", face, 1_000)
        later, later_open = plain(dists=(40_000, 10_000), cash=90_000, recovery=89_999, variant="later")
        self.assertLess(later_open, open_face)
        before = credit.view_claim("claim-a")
        self.assertEqual(mock_code_of(lambda: note(credit, "adv-2", later, 1)), "FACE_SNAPSHOT_FROZEN")
        self.assertEqual(credit.view_claim("claim-a"), before)
        self.assertEqual(before["open_face"], open_face)


class MachinePropertyTests(unittest.TestCase):
    def test_seeded_machine_runs_hold_every_relation(self):
        drivers = machine_runs()
        for name in ("offer:ok", "approve:ok", "bind_settlement:ok", "draw:ok", "draw:dup", "repay:ok",
                     "repay:dup", "close:ok", "default:ok", "cancel:ok", "reject:ok", "reconcile:ok",
                     "replay:ok", "conflict", "unsupported", "execution", "tick"):
            self.assertGreater(total(drivers, name), 0, name)
        seen = all_codes(drivers)
        for code in ("ADVANCE_EXCEEDS_OPEN_FACE", "FACE_SNAPSHOT_FROZEN", "OUTSTANDING_REMAINS",
                     "REPAYMENT_EXCEEDS_OUTSTANDING", "REPAYMENT_ORDER", "REPAY_BINDING_CONFLICT",
                     "DEFAULT_REQUIRES_EXPOSURE", "TERMINAL_IMMUTABLE", "ILLEGAL_TRANSITION",
                     "IDEMPOTENCY_CONFLICT", "DUPLICATE_DRAW", "SETTLEMENT_NOT_COMMITTED",
                     "SETTLEMENT_BINDING_CONFLICT", "UNKNOWN_ADVANCE",
                     "REFUND_OBLIGATION_OPEN", "INVALID_ID"):
            self.assertIn(code, seen, code)
        self.assertLessEqual(seen, MACHINE_CODES)

    def test_restore_reproduces_the_digest_at_every_prefix(self):
        drivers = [d for d in machine_runs() if d.counters.get("prefixes")]
        self.assertEqual(len(drivers), len(PREFIX_SEEDS))
        self.assertGreater(sum(len(d.m.export_journal()) for d in drivers), 20)

    def test_a_bound_draw_needs_a_committed_settlement(self):
        check_gate_matrix()

    def test_a_gate_rejected_key_stays_rejected_after_commit_and_a_new_key_succeeds(self):
        machine, stub, _face, open_face = gate_fixture("ok", 2)
        first = code_of(lambda: machine.draw("adv-1", idempotency_key="d-1", draw_id="dr-1"))
        self.assertEqual(first, "SETTLEMENT_NOT_COMMITTED")
        stub.tick("st-1")
        before = machine.state_digest()
        self.assertEqual(code_of(lambda: machine.draw("adv-1", idempotency_key="d-1", draw_id="dr-1")), first)
        self.assertEqual(machine.state_digest(), before)
        drawn = machine.draw("adv-1", idempotency_key="d-2", draw_id="dr-1")
        self.assertEqual(drawn["credit"]["outstanding_exposure"], open_face)
        self.assertEqual(len([e for e in machine.export_journal() if e["op"] == "draw"]), 1)
        again = machine.draw("adv-1", idempotency_key="d-3", draw_id="dr-1")
        self.assertIs(again["duplicate"], True)
        self.assertEqual(machine.view("adv-1")["outstanding_exposure"], open_face)

    def test_the_face_snapshot_stays_frozen_after_later_settlement_changes(self):
        machine, stub, face, open_face = gate_fixture("ok", 3)
        machine.draw("adv-1", idempotency_key="d-1", draw_id="dr-1")
        claim = machine.view_claim("claim-a")
        later, later_open = plain(dists=(60_000, 30_000), cash=90_000, recovery=0, variant="later")
        self.assertEqual(later_open, 0)
        machine.offer("adv-2", idempotency_key="o2", face=later, amount=1, beneficiary_role="role-0")
        machine.approve("adv-2", idempotency_key="a2")
        stub.tick("st-1")
        self.assertEqual(code_of(lambda: machine.draw("adv-2", idempotency_key="d2", draw_id="dr-2")),
                         "FACE_SNAPSHOT_FROZEN")
        self.assertEqual(machine.view_claim("claim-a"), claim)
        self.assertEqual(claim["open_face"], open_face)
        self.assertEqual(machine.view("adv-1")["open_face"], open_face)

    def test_an_open_refund_blocks_a_draw_and_a_release_is_not_a_repayment(self):
        machine, _stub, face, open_face = gate_fixture("ok", 3)
        refund, _ignored = plain(variant="open-refund", refund=7)
        self.assertEqual(code_of(lambda: machine.offer("adv-r", idempotency_key="or", face=refund, amount=1,
                                                       beneficiary_role="role-0")), "REFUND_OBLIGATION_OPEN")
        self.assertEqual(code_of(lambda: machine.view("adv-r")), "UNKNOWN_ADVANCE")
        machine.draw("adv-1", idempotency_key="d-1", draw_id="dr-1")
        machine.repay("adv-1", idempotency_key="r1", repay_id="rp-1", sequence=1, amount=open_face - 1)
        self.assertEqual(code_of(lambda: machine.close("adv-1", idempotency_key="c0")), "OUTSTANDING_REMAINS")
        machine.repay("adv-1", idempotency_key="r2", repay_id="rp-2", sequence=2, amount=1)
        self.assertEqual(machine.view_claim("claim-a")["reserved_open"], open_face)
        closed = machine.close("adv-1", idempotency_key="c1")["credit"]
        self.assertEqual((closed["phase"], closed["note_status"], closed["reserved_open"]), ("CLOSED", "RELEASED", 0))
        self.assertEqual((closed["repaid_exposure"], closed["outstanding_exposure"]), (open_face, 0))
        self.assertEqual(sum(item["amount"] for item in closed["repayments"]), closed["repaid_exposure"])
        self.assertIs(closed["repayment_observed"], False)

    def test_default_keeps_the_ceiling_closed_and_a_release_without_repayment_is_refused(self):
        machine, _stub, face, open_face = gate_fixture("ok", 3)
        machine.draw("adv-1", idempotency_key="d-1", draw_id="dr-1")
        machine.default("adv-1", idempotency_key="df", reason="why")
        self.assertEqual(code_of(lambda: machine.close("adv-1", idempotency_key="c1")), "TERMINAL_IMMUTABLE")
        view = machine.view("adv-1")
        self.assertEqual((view["note_status"], view["reserved_open"], view["repaid_exposure"]),
                         ("NOTED", open_face, 0))

    def test_unsupported_and_execution_refusals_are_inert_in_every_phase(self):
        machine, stub, face, open_face = gate_fixture("ok", 3)
        for suffix, build in (("off", None), ("app", "approve"), ("rej", "reject"), ("can", "cancel"),
                              ("drw", "draw"), ("def", "default"), ("cls", "close")):
            name = "x-" + suffix
            machine.offer(name, idempotency_key="o-" + suffix, face=face, amount=1, beneficiary_role="role-0")
            if build == "reject":
                machine.reject(name, idempotency_key="p-" + suffix, reason="why")
                continue
            if build:
                machine.approve(name, idempotency_key="p-" + suffix)
            if build == "cancel":
                machine.cancel(name, idempotency_key="q-" + suffix, reason="why")
            if build in ("draw", "default", "close"):
                machine.draw(name, idempotency_key="q-" + suffix, draw_id="dr-" + suffix)
            if build == "default":
                machine.default(name, idempotency_key="r-" + suffix, reason="why")
            if build == "close":
                machine.repay(name, idempotency_key="r-" + suffix, repay_id="rp-" + suffix, sequence=1, amount=1)
                machine.close(name, idempotency_key="s-" + suffix)
        phases = {machine.view(name)["phase"] for name in sorted(n for n in ("x-" + s for s in
                  ("off", "app", "rej", "can", "drw", "def", "cls")))}
        self.assertEqual(phases, {"OFFERED", "APPROVED", "REJECTED", "CANCELLED", "DRAWN", "DEFAULTED", "CLOSED"})
        noted = {"DRAWN", "DEFAULTED", "CLOSED"}
        for name in ["x-%s" % s for s in ("off", "app", "rej", "can", "drw", "def", "cls")] + ["nobody"]:
            for kind in sorted(UNSUPPORTED_TABLE) + list(NOT_KINDS):
                before = (machine.state_digest(), machine.export_journal(), stub.snapshot())
                self.assertEqual(code_of(lambda: machine.reject_unsupported(kind)),
                                 UNSUPPORTED_TABLE.get(kind, "EXECUTION_KIND"))
                self.assertEqual((machine.state_digest(), machine.export_journal(), stub.snapshot()), before)
            for kind in sorted(EXECUTION_TABLE) + list(NOT_KINDS):
                has_note = name != "nobody" and machine.view(name)["phase"] in noted
                if kind not in EXECUTION_TABLE:
                    want = "EXECUTION_KIND"
                else:
                    want = EXECUTION_TABLE[kind] if has_note else "UNKNOWN_ADVANCE"
                before = (machine.state_digest(), machine.export_journal())
                self.assertEqual(code_of(lambda: machine.attempt_execution(name, kind=kind)), want)
                self.assertEqual((machine.state_digest(), machine.export_journal()), before)


class ClassBCharacterizationTests(unittest.TestCase):
    """Behaviour the contract leaves open. Recorded, never pinned beyond this."""

    def test_b_the_frozen_face_is_not_cleared_when_every_note_is_released(self):
        machine, _stub, face, open_face = gate_fixture("ok", 3)
        machine.draw("adv-1", idempotency_key="d-1", draw_id="dr-1")
        machine.repay("adv-1", idempotency_key="r1", repay_id="rp-1", sequence=1, amount=open_face)
        machine.close("adv-1", idempotency_key="c1")
        self.assertEqual(machine.view_claim("claim-a")["reserved_open"], 0)
        other, _o = plain(dists=(0, 0), cash=1, recovery=1, variant="later")
        machine.offer("adv-2", idempotency_key="o2", face=other, amount=1, beneficiary_role="role-0")
        machine.approve("adv-2", idempotency_key="a2")
        self.assertEqual(code_of(lambda: machine.draw("adv-2", idempotency_key="d2", draw_id="dr-2")),
                         "FACE_SNAPSHOT_FROZEN")

    def test_b_a_terminal_case_still_answers_a_resent_draw_and_repay_as_duplicates(self):
        machine, _stub, face, open_face = gate_fixture("ok", 3)
        machine.draw("adv-1", idempotency_key="d-1", draw_id="dr-1")
        machine.repay("adv-1", idempotency_key="r1", repay_id="rp-1", sequence=1, amount=open_face)
        machine.close("adv-1", idempotency_key="c1")
        journal = machine.export_journal()
        self.assertIs(machine.draw("adv-1", idempotency_key="d-9", draw_id="dr-1")["duplicate"], True)
        self.assertIs(machine.repay("adv-1", idempotency_key="r9", repay_id="rp-1", sequence=1,
                                    amount=open_face)["duplicate"], True)
        self.assertEqual(machine.export_journal(), journal)
        self.assertEqual(code_of(lambda: machine.draw("adv-1", idempotency_key="d-8", draw_id="dr-2")),
                         "TERMINAL_IMMUTABLE")

    def test_b_the_gate_does_not_read_refund_fields_of_the_settlement_view(self):
        class RefundStub(StubSettlementSource):
            def peek(self, settlement_id):
                view = super().peek(settlement_id)
                view["refund_face"], view["fixture_reclassified"] = 5, False
                return view

        stub = RefundStub()
        stub.register("st-1", "ok", "claim-a", 90_000)
        for _ in range(3):
            stub.tick("st-1")
        face, open_face = plain()
        machine = CreditMachine(stub)
        machine.offer("adv-1", idempotency_key="o", face=face, amount=1, beneficiary_role="role-0")
        machine.approve("adv-1", idempotency_key="a")
        machine.bind_settlement("adv-1", idempotency_key="b", settlement_id="st-1")
        self.assertEqual(machine.draw("adv-1", idempotency_key="d", draw_id="dr-1")["credit"]["phase"], "DRAWN")


def _no_op_for(module, code):
    original = module._require

    def patched(ok, name):
        if name == code:
            return
        original(ok, name)

    return patched


class NegativeControlTests(unittest.TestCase):
    """Each control patches an in-memory attribute and must trip an oracle.

    AssertionError is required, not CreditError: the oracle fails, not the
    guard under test. Source files are never edited.
    """

    def run_seeds(self, make, steps):
        for seed in SEEDS:
            make(seed).run(steps)

    def test_removing_the_shared_ceiling_trips_the_mock_oracle(self):
        original = mock_credit._require
        with mock.patch.object(mock_credit, "_require", _no_op_for(mock_credit, "ADVANCE_EXCEEDS_OPEN_FACE")):
            with mock.patch.object(MockCredit, "_invariant", lambda self: None):
                with self.assertRaises(AssertionError):
                    self.run_seeds(MockDriver, MOCK_STEPS)
        self.assertIs(mock_credit._require, original)

    def test_removing_the_shared_ceiling_trips_the_machine_oracle(self):
        original = mock_credit._require
        with mock.patch.object(mock_credit, "_require", _no_op_for(mock_credit, "ADVANCE_EXCEEDS_OPEN_FACE")):
            with mock.patch.object(MockCredit, "_invariant", lambda self: None):
                with mock.patch.object(CreditMachine, "_invariant", lambda self: None):
                    with self.assertRaises(AssertionError):
                        self.run_seeds(MachineDriver, MACHINE_STEPS)
        self.assertIs(mock_credit._require, original)

    def test_removing_the_committed_gate_trips_the_gate_matrix_and_the_seeded_run(self):
        original = credit_fsm._require
        with mock.patch.object(credit_fsm, "_require", _no_op_for(credit_fsm, "SETTLEMENT_NOT_COMMITTED")):
            with self.assertRaises(AssertionError):
                check_gate_matrix()
            with self.assertRaises(AssertionError):
                self.run_seeds(MachineDriver, MACHINE_STEPS)
        self.assertIs(credit_fsm._require, original)
        check_gate_matrix()

    def test_a_rejected_repay_that_mutates_a_label_trips_the_inertness_oracle(self):
        original = CreditMachine.repay

        def leaky(self, advance_id, **kwargs):
            try:
                return original(self, advance_id, **kwargs)
            except CreditError:
                if advance_id in self._cases:
                    self._cases[advance_id]["reject_reason"] = "leak"
                raise

        with mock.patch.object(CreditMachine, "repay", leaky):
            with self.assertRaises(AssertionError):
                self.run_seeds(MachineDriver, MACHINE_STEPS)
        self.assertIs(CreditMachine.repay, original)

    def test_an_export_journal_that_drops_its_last_entry_trips_the_journal_oracle(self):
        original = CreditMachine.export_journal
        with mock.patch.object(CreditMachine, "export_journal", lambda self: original(self)[:-1]):
            with self.assertRaises(AssertionError):
                MachineDriver(SEEDS[0]).run(MACHINE_STEPS)
        self.assertIs(CreditMachine.export_journal, original)

    def test_a_restore_that_skips_repay_entries_trips_the_restore_oracle(self):
        original = CreditMachine.restore.__func__

        def skipping(cls, journal, settlement_source=None, ownership_source=None):
            kept = [e for e in journal if e["op"] != "repay"] if type(journal) is list else journal
            return original(cls, kept, settlement_source, ownership_source)

        with mock.patch.object(CreditMachine, "restore", classmethod(skipping)):
            with self.assertRaises(AssertionError):
                self.run_seeds(MachineDriver, MACHINE_STEPS)
        self.assertIs(CreditMachine.restore.__func__, original)


if __name__ == "__main__":
    unittest.main()
