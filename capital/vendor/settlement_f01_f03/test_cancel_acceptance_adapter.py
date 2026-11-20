"""Source-informed boundary and direct-FSM parity evidence; synthetic only."""

from copy import deepcopy
import json
import unittest
from unittest.mock import Mock

from cancel_acceptance_adapter import CancelAcceptanceAdapter
from cancel_acceptance_source import (
    CancelAcceptanceIdentityMismatch, CancelAcceptanceNotFound,
    CancelAcceptanceSourceError, InvalidCancelAcceptanceRecord,
)
from example_cancel_acceptance_adapter import run_example
from fake_cancel_acceptance_source import FakeCancelAcceptanceSource, SyntheticCancelAcceptanceFault
from settlement_fsm import SettlementError, SettlementMachine
from settlement_property_support import (
    ALWAYS_FALSE_FLAGS, check_claim_view, check_refund_view, policy, statement_kwargs,
)

SID = "fixture-settlement"
SOURCE = "fixture-acceptance"


def record(**changes):
    result = dict(settlement_id=SID, source_id=SOURCE, amount=10_000)
    result.update(changes)
    return result


def prepared(phase="COMMITTED", *, refund=True):
    machine = SettlementMachine()
    if phase == "ABSENT":
        return machine
    machine.initiate(SID, idempotency_key="init", trade_id="fixture-trade", gross=100_000,
                     debtor_role="fixture-merchant", policy=policy(500))
    if phase in ("FAILED", "CANCELLED"):
        method = machine.fail if phase == "FAILED" else machine.cancel
        method(SID, idempotency_key="terminal", reason="fixture-terminal")
        return machine
    if phase == "INITIATED":
        return machine
    machine.authorize(SID, idempotency_key="auth")
    if phase == "AUTHORIZED":
        return machine
    machine.capture(SID, idempotency_key="capture")
    if phase == "COMMITTED":
        machine.commit(SID, idempotency_key="commit", **statement_kwargs(
            "fixture-statement", (100_000, 97_000, 3_000, 0, 0, 0, None)))
    if refund:
        machine.bind_refund(SID, idempotency_key="refund", refund_id="fixture-refund",
                            amount=40_000, beneficiary_role="fixture-buyer", reason="fixture-reason")
    return machine


def observables(machine):
    return machine.canonical_state(), machine.state_digest(), machine.export_journal()


def direct(machine, document, key):
    return machine.observe_mock_cancel_acceptance(
        SID, source_id=document["source_id"], amount=document["amount"], idempotency_key=key)


def adapted_call(machine, document, key):
    source = FakeCancelAcceptanceSource(recordings={(SID, document["source_id"]): json.dumps(document)})
    try:
        return CancelAcceptanceAdapter(machine, source).apply(
            settlement_id=SID, source_id=document["source_id"], idempotency_key=key)
    finally:
        assert source.calls == ((SID, document["source_id"]),)


class CancelAcceptanceAdapterTests(unittest.TestCase):
    def assert_parity(self, adapted, control, document, key, code=None):
        if code is None:
            result = adapted_call(adapted, document, key)
            self.assertEqual(result, direct(control, document, key))
        else:
            for invoke in (lambda: adapted_call(adapted, document, key),
                           lambda: direct(control, document, key)):
                with self.assertRaises(SettlementError) as caught:
                    invoke()
                self.assertEqual(caught.exception.code, code)
            result = None
        self.assertEqual(observables(adapted), observables(control))
        return result

    def test_one_fetch_exact_forwarding_and_same_result_or_error_object(self):
        for amount in (10_000, True):
            with self.subTest(amount=amount):
                machine = prepared()
                document = record(amount=amount)
                source = Mock()
                source.fetch.return_value = document
                spy = Mock(wraps=machine, spec_set=SettlementMachine)
                retained = []

                def invoke(*args, **kwargs):
                    try:
                        result = machine.observe_mock_cancel_acceptance(*args, **kwargs)
                    except SettlementError as error:
                        retained.append(error)
                        raise
                    retained.append(result)
                    return result

                spy.observe_mock_cancel_acceptance.side_effect = invoke
                key = "caller-key"
                adapter = CancelAcceptanceAdapter(spy, source)
                if amount is True:
                    with self.assertRaises(SettlementError) as caught:
                        adapter.apply(settlement_id=SID, source_id=SOURCE, idempotency_key=key)
                    self.assertIs(caught.exception, retained[0])
                    self.assertEqual(caught.exception.code, "INVALID_AMOUNT")
                else:
                    self.assertIs(adapter.apply(settlement_id=SID, source_id=SOURCE,
                                                idempotency_key=key), retained[0])
                source.fetch.assert_called_once_with(SID, SOURCE)
                self.assertEqual(len(spy.mock_calls), 1)
                spy.observe_mock_cancel_acceptance.assert_called_once_with(
                    SID, source_id=SOURCE, amount=amount, idempotency_key=key)
                self.assertIs(spy.observe_mock_cancel_acceptance.call_args.kwargs["amount"], amount)
                self.assertIs(spy.observe_mock_cancel_acceptance.call_args.kwargs["idempotency_key"], key)
                self.assertEqual(document, record(amount=amount))

    def test_partial_acceptance_and_replay_after_later_changes_match_direct(self):
        for phase in ("CAPTURED", "COMMITTED"):
            with self.subTest(phase=phase):
                adapted, control = prepared(phase), prepared(phase)
                source = FakeCancelAcceptanceSource(recordings={(SID, SOURCE): json.dumps(record())})
                adapter = CancelAcceptanceAdapter(adapted, source)
                request = dict(settlement_id=SID, source_id=SOURCE, idempotency_key="first")
                first = adapter.apply(**request)
                self.assertEqual(first, direct(control, record(), "first"))
                expected = deepcopy(first)
                expected.update(duplicate=True, applied=None)
                first["settlement"]["claim"]["refund_accepted"] = -1
                later = self.assert_parity(adapted, control, record(source_id="fixture-later", amount=5_000), "later")
                view = later["settlement"]
                check_claim_view(view["claim"])
                check_refund_view(view["claim"])
                self.assertEqual(view["claim"]["confirmed_cash"], 97_000 if phase == "COMMITTED" else 0)
                self.assertEqual(view["claim"]["pg_adjustment_outstanding"], 15_000)
                self.assertEqual(view["claim"]["refund_outstanding"], 25_000)
                self.assertEqual(view["phase"], phase)
                before = observables(adapted)
                for _ in range(2):
                    self.assertEqual(adapter.apply(**request), expected)
                    self.assertEqual(direct(control, record(), "first"), expected)
                self.assertEqual(source.calls, ((SID, SOURCE),) * 3)
                self.assertEqual(observables(adapted), before)
                self.assertEqual(observables(adapted), observables(control))
                self.assert_parity(adapted, control, record(amount=9_999), "first", "IDEMPOTENCY_CONFLICT")
                self.assert_parity(adapted, control, record(source_id="other"), "first", "IDEMPOTENCY_CONFLICT")

    def test_source_binding_repeat_and_conflict_match_direct(self):
        for phase in ("CAPTURED", "COMMITTED"):
            with self.subTest(phase=phase):
                adapted, control = prepared(phase), prepared(phase)
                self.assert_parity(adapted, control, record(), "first")
                before_claim, before_journal = adapted.view(SID)["claim"], adapted.export_journal()
                repeated = self.assert_parity(adapted, control, record(), "another-key")
                self.assertFalse(repeated["duplicate"])
                self.assertEqual(adapted.view(SID)["claim"], before_claim)
                # Existing characterization: new-key source repeats are journaled
                # despite being economically inert; this defines no new contract.
                self.assertEqual(len(adapted.export_journal()), len(before_journal) + 1)
                before = observables(adapted)
                self.assert_parity(adapted, control, record(amount=9_999), "conflict", "ACCEPTANCE_BINDING_CONFLICT")
                self.assertEqual(observables(adapted), before)
                self.assert_parity(adapted, control, record(), "conflict", "IDEMPOTENCY_CONFLICT")

    def test_economic_rejections_and_retained_keys_remain_in_fsm(self):
        for phase in ("CAPTURED", "COMMITTED"):
            for amount, refund, code in (
                (10_000, False, "REFUND_OBLIGATION_REQUIRED"),
                (40_001, True, "REFUND_ACCEPTANCE_EXCEEDS_OBLIGATION"),
                (True, True, "INVALID_AMOUNT"), (0, True, "INVALID_AMOUNT"),
                (-1, True, "INVALID_AMOUNT"), ("10000", True, "INVALID_AMOUNT"),
                (None, True, "INVALID_AMOUNT"), (10**12 + 1, True, "INVALID_AMOUNT"),
            ):
                with self.subTest(phase=phase, amount=amount, refund=refund):
                    adapted, control = prepared(phase, refund=refund), prepared(phase, refund=refund)
                    document = record(amount=amount)
                    before = observables(adapted)
                    for _ in range(2):
                        self.assert_parity(adapted, control, document, "rejected", code)
                        self.assertEqual(observables(adapted), before)
                    # Same key, changed body probes the rejection table omitted
                    # from canonical_state; no source-side validation consumed it.
                    self.assert_parity(adapted, control, record(source_id="fresh-source"),
                                       "rejected", "IDEMPOTENCY_CONFLICT")
                    if not refund:
                        for machine in (adapted, control):
                            machine.bind_refund(SID, idempotency_key="later-refund", refund_id="later-refund",
                                                amount=40_000, beneficiary_role="fixture-buyer", reason="fixture")
                    self.assert_parity(adapted, control, record(), "fresh")
                    self.assert_parity(adapted, control, document, "rejected", code)

    def test_local_failures_never_call_fsm_mutate_state_or_consume_key(self):
        cases = [(None, CancelAcceptanceNotFound),
                 (SyntheticCancelAcceptanceFault.ERROR, CancelAcceptanceSourceError),
                 (SyntheticCancelAcceptanceFault.TIMEOUT, CancelAcceptanceSourceError),
                 ("{", InvalidCancelAcceptanceRecord), ("[]", InvalidCancelAcceptanceRecord)]
        for field in record():
            missing = record()
            missing.pop(field)
            cases.append((json.dumps(missing), InvalidCancelAcceptanceRecord))
        cases.append((json.dumps(record(extra=True)), InvalidCancelAcceptanceRecord))
        for field in ("settlement_id", "source_id"):
            for value in ("other", 1, None, True):
                cases.append((json.dumps(record(**{field: value})), CancelAcceptanceIdentityMismatch))
        for phase in ("CAPTURED", "COMMITTED"):
            for recording, error_type in cases:
                with self.subTest(phase=phase, recording=recording):
                    machine = prepared(phase)
                    before = observables(machine)
                    source = FakeCancelAcceptanceSource(
                        recordings={} if recording is None else {(SID, SOURCE): recording})
                    spy = Mock(wraps=machine, spec_set=SettlementMachine)
                    for count in (1, 2):
                        with self.assertRaises(error_type):
                            CancelAcceptanceAdapter(spy, source).apply(
                                settlement_id=SID, source_id=SOURCE, idempotency_key="still-free")
                        self.assertEqual(source.calls, ((SID, SOURCE),) * count)
                        self.assertEqual(spy.mock_calls, [])
                        self.assertEqual(observables(machine), before)
                    self.assertFalse(adapted_call(machine, record(), "still-free")["duplicate"])

    def test_custom_source_bad_shapes_and_failure_objects_propagate_without_retry(self):
        for value in ([], "text", 42, {}):
            with self.subTest(value=value):
                machine, source = prepared(), Mock()
                source.fetch.return_value = value
                before = observables(machine)
                spy = Mock(wraps=machine, spec_set=SettlementMachine)
                with self.assertRaises(InvalidCancelAcceptanceRecord):
                    CancelAcceptanceAdapter(spy, source).apply(
                        settlement_id=SID, source_id=SOURCE, idempotency_key="still-free")
                source.fetch.assert_called_once_with(SID, SOURCE)
                self.assertEqual(spy.mock_calls, [])
                self.assertEqual(observables(machine), before)
                self.assertFalse(adapted_call(machine, record(), "still-free")["duplicate"])
        machine, source = prepared(), Mock()
        failure = CancelAcceptanceSourceError("synthetic failure")
        source.fetch.side_effect = failure
        spy = Mock(wraps=machine, spec_set=SettlementMachine)
        before = observables(machine)
        with self.assertRaises(CancelAcceptanceSourceError) as caught:
            CancelAcceptanceAdapter(spy, source).apply(
                settlement_id=SID, source_id=SOURCE, idempotency_key="still-free")
        self.assertIs(caught.exception, failure)
        source.fetch.assert_called_once_with(SID, SOURCE)
        self.assertEqual(spy.mock_calls, [])
        self.assertEqual(observables(machine), before)
        self.assertFalse(adapted_call(machine, record(), "still-free")["duplicate"])

    def test_phase_and_identifier_errors_match_direct(self):
        for phase in ("ABSENT", "INITIATED", "AUTHORIZED", "FAILED", "CANCELLED"):
            with self.subTest(phase=phase):
                adapted, control = prepared(phase), prepared(phase)
                before = observables(adapted)
                code = ("UNKNOWN_SETTLEMENT" if phase == "ABSENT" else
                        "TERMINAL_IMMUTABLE" if phase in ("FAILED", "CANCELLED") else "ILLEGAL_TRANSITION")
                self.assert_parity(adapted, control, record(), "phase-key", code)
                self.assertEqual(observables(adapted), before)
        for document, key in ((record(), ""), (record(source_id=" invalid "), "caller-key")):
            adapted, control = prepared(), prepared()
            self.assert_parity(adapted, control, document, key, "INVALID_ID")
            self.assert_parity(adapted, control, record(), "fresh")


class CancelAcceptanceExampleTests(unittest.TestCase):
    def test_explicit_obligation_then_observations_preserve_mock_posture_and_replay(self):
        with self.assertRaises(TypeError):
            run_example()
        fixture_policy = policy(500, residual="fixture-host", fee="fixture-operator")
        order = ["fixture-host", "fixture-operator"]
        before = deepcopy((fixture_policy, order))
        report = run_example(policy=fixture_policy, order=order)
        self.assertEqual((fixture_policy, order), before)
        self.assertEqual(report["source_calls"], ((SID, "fixture-acceptance-1"), (SID, "fixture-acceptance-2")))
        self.assertEqual(report["statement_calls"], ((SID, "fixture-statement"),))
        self.assertEqual([entry["op"] for entry in report["journal"]], [
            "initiate", "authorize", "capture", "commit", "bind_refund",
            "observe_mock_cancel_acceptance", "observe_mock_cancel_acceptance",
            "distribute"])
        # B5: the open partial refund no longer blocks distribution; the
        # caller order allocates the confirmed cash and then freezes.
        self.assertFalse(report["distribution"]["duplicate"])
        self.assertEqual(report["distribution"]["effect"],
                         {"fixture-host": 95_000, "fixture-operator": 2_000})
        for stage, accepted in (("initial", 0), ("refund", 0), ("first", 10_000), ("later", 15_000)):
            view = report[stage]["settlement"]
            claim = view["claim"]
            check_claim_view(claim)
            check_refund_view(claim)
            self.assertEqual(view["provenance"], "MOCK_SETTLEMENT_ONLY")
            self.assertEqual(view["policy"], fixture_policy)
            self.assertEqual(claim["confirmed_cash"], 97_000)
            self.assertEqual(claim["pg_adjustment_outstanding"], accepted)
            self.assertEqual(claim["refund_accepted"], accepted)
            self.assertEqual(claim["refund_face"], 0 if stage == "initial" else 40_000)
            self.assertEqual(claim["refund_outstanding"], 0 if stage == "initial" else 40_000 - accepted)
            self.assertEqual(claim["distributed_cash"], 0)
            self.assertIsNone(claim["distribution_order"])
            self.assertFalse(claim["fixture_reclassified"])
            self.assertEqual(claim["refund_bearer_policy"], "NONE" if stage == "initial" else "REQUESTER")
            self.assertEqual(sum(line["outstanding"] for line in claim["obligations"]), 100_000)
            self.assertTrue(all(line["cancelled_unpaid"] == line["recovery_due"] == 0
                                for line in claim["obligations"]))
            for flag in ALWAYS_FALSE_FLAGS + ("durable", "provider_authorization_executed"):
                self.assertIs(view[flag], False)
        self.assertEqual(report["provenance"], "MOCK_SETTLEMENT_ONLY")
        for flag in ("funds_executed", "bank_debit_observed", "external_return_closed", "durable"):
            self.assertIs(report[flag], False)
        restored = SettlementMachine.restore(report["journal"])
        self.assertEqual(restored.view(SID), report["distribution"]["settlement"])
        # A further distribute under a fresh key still succeeds under B5;
        # no cash remains, so it applies zero and claws nothing back.
        again = restored.distribute(SID, idempotency_key="after-restore", order=order)
        self.assertEqual(again["effect"], {"fixture-host": 0, "fixture-operator": 0})
