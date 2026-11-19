"""Source-informed adapter evidence over the actual unchanged local FSM."""

from copy import deepcopy
import json
import unittest
from unittest.mock import Mock

from example_statement_adapter import run_example
from fake_statement_source import FakeStatementSource, SyntheticStatementFault
from settlement_fsm import SettlementError, SettlementMachine
from settlement_property_support import ALWAYS_FALSE_FLAGS, check_claim_view, policy, statement_kwargs
from statement_adapter import StatementAdapter
from statement_source import (
    InvalidStatementRecord, StatementIdentityMismatch, StatementNotFound, StatementSourceError,
)


SID = "fixture-settlement"
MID = "fixture-movement"


def record(**changes):
    result = dict(settlement_id=SID, **statement_kwargs(
        MID, (60_000, 55_000, 2_000, 1_000, 1_000, 1_000, "fixture-adjustment"),
    ))
    result.update(changes)
    return result


def prepared(phase="CAPTURED"):
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
        machine.commit(SID, idempotency_key="seed", **statement_kwargs(
            "fixture-seed", (20_000, 20_000, 0, 0, 0, 0, None),
        ))
    return machine


def observables(machine):
    return machine.canonical_state(), machine.state_digest(), machine.export_journal()


def apply(machine, document, *, operation="commit", key="request"):
    source = FakeStatementSource(recordings={(SID, document["movement_id"]): json.dumps(document)})
    result = StatementAdapter(machine, source).apply(
        operation=operation, settlement_id=SID, movement_id=document["movement_id"],
        idempotency_key=key,
    )
    return result, source


def direct(machine, document, *, operation="commit", key="request"):
    body = {k: v for k, v in document.items() if k != "settlement_id"}
    return getattr(machine, operation)(SID, idempotency_key=key, **body)


class StatementAdapterTests(unittest.TestCase):
    def assert_parity(self, adapted, control, document, operation, key, code=None):
        if code is None:
            result, source = apply(adapted, document, operation=operation, key=key)
            self.assertEqual(result, direct(control, document, operation=operation, key=key))
            self.assertEqual(source.calls, ((SID, document["movement_id"]),))
        else:
            for invoke in (
                lambda: apply(adapted, document, operation=operation, key=key),
                lambda: direct(control, document, operation=operation, key=key),
            ):
                with self.assertRaises(SettlementError) as caught:
                    invoke()
                self.assertEqual(caught.exception.code, code)
            result = None
        self.assertEqual(observables(adapted), observables(control))
        return result

    def test_one_fetch_exact_forwarding_and_same_response_or_error_object(self):
        for operation in ("commit", "observe_statement"):
            for malformed in (False, True):
                with self.subTest(operation=operation, malformed=malformed):
                    machine = prepared("CAPTURED" if operation == "commit" else "COMMITTED")
                    document = record(amount=True) if malformed else record()
                    source = Mock()
                    source.fetch.return_value = document
                    spy = Mock(wraps=machine, spec_set=SettlementMachine)
                    retained = []

                    def invoke(*args, **kwargs):
                        try:
                            result = getattr(machine, operation)(*args, **kwargs)
                        except SettlementError as error:
                            retained.append(error)
                            raise
                        retained.append(result)
                        return result

                    getattr(spy, operation).side_effect = invoke
                    adapter = StatementAdapter(spy, source)
                    if malformed:
                        with self.assertRaises(SettlementError) as caught:
                            adapter.apply(operation=operation, settlement_id=SID,
                                          movement_id=MID, idempotency_key="caller-key")
                        self.assertIs(caught.exception, retained[0])
                        self.assertEqual(caught.exception.code, "INVALID_NONNEGATIVE")
                    else:
                        result = adapter.apply(operation=operation, settlement_id=SID,
                                               movement_id=MID, idempotency_key="caller-key")
                        self.assertIs(result, retained[0])
                        check_claim_view(result["settlement"]["claim"])
                        self.assertEqual(result["settlement"]["claim"]["distributed_cash"], 0)
                    source.fetch.assert_called_once_with(SID, MID)
                    self.assertEqual(len(spy.mock_calls), 1)
                    method = getattr(spy, operation)
                    expected = {k: v for k, v in document.items() if k != "settlement_id"}
                    method.assert_called_once_with(SID, idempotency_key="caller-key", **expected)
                    for field, value in expected.items():
                        self.assertIs(method.call_args.kwargs[field], value)
                    self.assertEqual(document, record(amount=True) if malformed else record())

    def test_local_source_rejections_do_not_call_fsm_or_bind_key(self):
        missing_field = record()
        missing_field.pop("adjustment_reason")
        cases = [
            (None, StatementNotFound),
            (SyntheticStatementFault.ERROR, StatementSourceError),
            (SyntheticStatementFault.TIMEOUT, StatementSourceError),
            ("{", InvalidStatementRecord),
            (json.dumps([]), InvalidStatementRecord),
            (json.dumps(missing_field), InvalidStatementRecord),
            (json.dumps(record(extra="unexpected")), InvalidStatementRecord),
            (json.dumps(record(settlement_id="another-settlement")), StatementIdentityMismatch),
            (json.dumps(record(movement_id="another-movement")), StatementIdentityMismatch),
            (json.dumps(record(settlement_id=1)), StatementIdentityMismatch),
        ]
        for operation in ("commit", "observe_statement"):
            for recording, error_type in cases:
                with self.subTest(operation=operation, recording=recording):
                    machine = prepared("CAPTURED" if operation == "commit" else "COMMITTED")
                    before = observables(machine)
                    source = FakeStatementSource(recordings={} if recording is None else {(SID, MID): recording})
                    spy = Mock(wraps=machine, spec_set=SettlementMachine)
                    with self.assertRaises(error_type):
                        StatementAdapter(spy, source).apply(
                            operation=operation, settlement_id=SID, movement_id=MID,
                            idempotency_key="still-free",
                        )
                    self.assertEqual(source.calls, ((SID, MID),))
                    self.assertEqual(spy.mock_calls, [])
                    self.assertEqual(observables(machine), before)
                    accepted, _ = apply(machine, record(), operation=operation, key="still-free")
                    self.assertFalse(accepted["duplicate"])

    def test_custom_source_shape_errors_and_failure_propagate_without_retry(self):
        for value in ([], "text", 42, {}):
            with self.subTest(value=value):
                source, machine = Mock(), Mock(spec_set=SettlementMachine)
                source.fetch.return_value = value
                with self.assertRaises(InvalidStatementRecord):
                    StatementAdapter(machine, source).apply(
                        operation="commit", settlement_id=SID, movement_id=MID, idempotency_key="key")
                source.fetch.assert_called_once_with(SID, MID)
                self.assertEqual(machine.mock_calls, [])
        source, machine = Mock(), Mock(spec_set=SettlementMachine)
        failure = StatementSourceError("fixture failure")
        source.fetch.side_effect = failure
        with self.assertRaises(StatementSourceError) as caught:
            StatementAdapter(machine, source).apply(
                operation="commit", settlement_id=SID, movement_id=MID, idempotency_key="key")
        self.assertIs(caught.exception, failure)
        source.fetch.assert_called_once_with(SID, MID)
        self.assertEqual(machine.mock_calls, [])

    def test_unsupported_selectors_never_fetch_or_call_fsm(self):
        for operation in ("distribute", "capture", "COMMIT", "", None):
            with self.subTest(operation=operation):
                source, machine = Mock(), Mock(spec_set=SettlementMachine)
                with self.assertRaises(ValueError):
                    StatementAdapter(machine, source).apply(
                        operation=operation, settlement_id=SID, movement_id=MID, idempotency_key="key")
                self.assertEqual(source.mock_calls, [])
                self.assertEqual(machine.mock_calls, [])

    def test_malformed_components_preserve_direct_errors_and_rejection_keys(self):
        cases = (
            ({"amount": 54_999}, "SETTLEMENT_COMPONENT_MISMATCH"),
            ({"amount": True}, "INVALID_NONNEGATIVE"),
            ({"gross": True}, "INVALID_AMOUNT"),
            ({"fee": -1}, "INVALID_NONNEGATIVE"),
            ({"tax": "1000"}, "INVALID_NONNEGATIVE"),
            ({"adjustment_reason": None}, "ADJUSTMENT_REASON_REQUIRED"),
            ({"adjustment": 0, "amount": 56_000}, "ADJUSTMENT_REASON_UNEXPECTED"),
        )
        for operation in ("commit", "observe_statement"):
            for changes, code in cases:
                with self.subTest(operation=operation, changes=changes):
                    phase = "CAPTURED" if operation == "commit" else "COMMITTED"
                    adapted, control = prepared(phase), prepared(phase)
                    before = observables(adapted)
                    for _ in range(2):
                        self.assert_parity(adapted, control, record(**changes), operation, "rejected", code)
                        self.assertEqual(observables(adapted), before)
                    self.assert_parity(adapted, control, record(), operation, "rejected", "IDEMPOTENCY_CONFLICT")
                    self.assert_parity(adapted, control, record(), operation, "fresh")
                    # A stored rejection survives a later accepted state change.
                    self.assert_parity(adapted, control, record(**changes), operation, "rejected", code)

    def test_replay_fetches_each_time_returns_first_snapshot_after_later_changes(self):
        for operation in ("commit", "observe_statement"):
            with self.subTest(operation=operation):
                phase = "CAPTURED" if operation == "commit" else "COMMITTED"
                adapted, control = prepared(phase), prepared(phase)
                source = FakeStatementSource(recordings={(SID, MID): json.dumps(record())})
                adapter = StatementAdapter(adapted, source)
                request = dict(operation=operation, settlement_id=SID, movement_id=MID, idempotency_key="first")
                first = adapter.apply(**request)
                self.assertEqual(first, direct(control, record(), operation=operation, key="first"))
                expected = deepcopy(first)
                expected.update(duplicate=True, applied=None)
                first["settlement"]["claim"]["confirmed_cash"] = -1
                for machine in (adapted, control):
                    machine.distribute(SID, idempotency_key="dist", order=["fixture-fee", "fixture-residual"])
                before = observables(adapted)
                self.assertEqual(adapter.apply(**request), expected)
                self.assertEqual(adapter.apply(**request), expected)
                self.assertEqual(source.calls, ((SID, MID),) * 3)
                self.assertEqual(observables(adapted), before)
                self.assertEqual(observables(adapted), observables(control))
                self.assert_parity(adapted, control, record(amount=54_999, fee=2_001),
                                   operation, "first", "IDEMPOTENCY_CONFLICT")
                other = "observe_statement" if operation == "commit" else "commit"
                self.assert_parity(adapted, control, record(), other, "first", "IDEMPOTENCY_CONFLICT")

    def test_duplicate_movement_and_conflicting_binding_match_direct_fsm(self):
        adapted, control = prepared(), prepared()
        self.assert_parity(adapted, control, record(), "commit", "first")
        before_claim = adapted.view(SID)["claim"]
        before_journal = adapted.export_journal()
        duplicate = self.assert_parity(adapted, control, record(), "observe_statement", "another-key")
        self.assertFalse(duplicate["duplicate"])
        self.assertEqual(adapted.view(SID)["claim"], before_claim)
        # Existing characterization: a new-key movement repeat is journaled,
        # although it is economically inert. No new contract is defined here.
        self.assertEqual(len(adapted.export_journal()), len(before_journal) + 1)
        before = observables(adapted)
        self.assert_parity(adapted, control, record(amount=54_999, fee=2_001),
                           "observe_statement", "conflict", "STATEMENT_BINDING_CONFLICT")
        self.assertEqual(observables(adapted), before)

    def test_illegal_unknown_and_terminal_phase_errors_are_unchanged(self):
        for operation in ("commit", "observe_statement"):
            phases = ("ABSENT", "INITIATED", "AUTHORIZED", "FAILED", "CANCELLED",
                      "COMMITTED" if operation == "commit" else "CAPTURED")
            for phase in phases:
                with self.subTest(operation=operation, phase=phase):
                    adapted, control = prepared(phase), prepared(phase)
                    code = ("UNKNOWN_SETTLEMENT" if phase == "ABSENT" else
                            "TERMINAL_IMMUTABLE" if phase in ("FAILED", "CANCELLED") else
                            "ILLEGAL_TRANSITION")
                    before = observables(adapted)
                    self.assert_parity(adapted, control, record(), operation, "phase-key", code)
                    self.assertEqual(observables(adapted), before)

    def test_invalid_caller_key_remains_the_fsm_error_and_does_not_bind(self):
        adapted, control = prepared(), prepared()
        self.assert_parity(adapted, control, record(), "commit", "", "INVALID_ID")
        self.assert_parity(adapted, control, record(), "commit", "fresh")


class StatementExampleTests(unittest.TestCase):
    def test_example_uses_actual_fsm_and_requires_explicit_fixture_policy_order(self):
        with self.assertRaises(TypeError):
            run_example()
        fixture_policy = policy(500, residual="fixture-host", fee="fixture-operator")
        order = ["fixture-host", "fixture-operator"]
        originals = deepcopy((fixture_policy, order))
        report = run_example(policy=fixture_policy, order=order)
        self.assertEqual((fixture_policy, order), originals)
        self.assertEqual(report["source_calls"], ((SID, "fixture-initial"), (SID, "fixture-later")))
        self.assertEqual([entry["op"] for entry in report["journal"]],
                         ["initiate", "authorize", "capture", "commit", "observe_statement", "distribute"])
        for stage, cash in (("initial", 55_000), ("later", 93_000), ("distributed", 93_000)):
            view = report[stage]["settlement"]
            check_claim_view(view["claim"])
            self.assertEqual(view["provenance"], "MOCK_SETTLEMENT_ONLY")
            self.assertEqual(view["claim"]["confirmed_cash"], cash)
            self.assertEqual(view["policy"], fixture_policy)
            for flag in ALWAYS_FALSE_FLAGS + ("durable", "provider_authorization_executed"):
                self.assertIs(view[flag], False)
            self.assertNotIn("chain_finality", report[stage])
            self.assertNotIn("chain_finality", view)
            if stage != "distributed":
                self.assertEqual(view["claim"]["undistributed_cash"], cash)
                self.assertEqual(view["claim"]["distributed_cash"], 0)
                self.assertIsNone(view["claim"]["distribution_order"])
        final = report["distributed"]["settlement"]["claim"]
        self.assertEqual(final["non_cash_accounted"], 7_000)
        self.assertEqual(final["receivable_open"], 0)
        self.assertEqual(final["distribution_order"], order)
        self.assertEqual(report["distributed"]["effect"], {"fixture-host": 93_000, "fixture-operator": 0})
        self.assertEqual(sum(line["outstanding"] for line in final["obligations"]), 7_000)
        self.assertEqual(report["provenance"], "MOCK_SETTLEMENT_ONLY")
        for flag in ("durable", "funds_executed", "chain_finality"):
            self.assertIs(report[flag], False)
        restored = SettlementMachine.restore(report["journal"])
        self.assertEqual(restored.view(SID), report["distributed"]["settlement"])
