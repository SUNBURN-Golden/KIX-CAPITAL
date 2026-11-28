# Offline settlement statement adapter

`StatementSource.fetch(settlement_id, movement_id)` is an internal Python
interface. A record has exactly `settlement_id`, `movement_id`, `gross`,
`amount`, `fee`, `tax`, `held`, `adjustment`, and `adjustment_reason` (explicitly
`None` when appropriate). These are existing FSM arguments, not a wire schema.

`StatementAdapter.apply(operation=..., settlement_id=..., movement_id=...,
idempotency_key=...)` fetches once per explicit request, including replay.
The caller selects `commit` or `observe_statement` and supplies the key.
Unsupported selectors fail before fetching. Missing records, invalid shape and
identity mismatch raise local source/record exceptions before any FSM call.
Components pass through unchanged; the FSM alone validates amounts, phases,
movement bindings and idempotency. Results and `SettlementError` propagate
unchanged. There is no retry, fallback, cached result or inferred fee.

`FakeStatementSource(recordings=...)` copies a mapping from identity pairs to
immutable JSON text or `SyntheticStatementFault.ERROR/TIMEOUT`. Its recordings
are read-only, fetched documents are freshly parsed, and `calls` is a tuple
snapshot. Faults raise `StatementSourceError` immediately; timeout is a synthetic
marker with no clock, waiting or statement-absence meaning.

Run from the repository root, with only Python's standard library:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 reference/settlement_f01_f03/example_statement_adapter.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s reference/settlement_f01_f03 -t reference/settlement_f01_f03
```

The callable `run_example(*, policy, order)` requires both fixture inputs.
Its script entry point supplies visibly synthetic values. It explicitly
initiates, authorizes, captures, commits the first statement, observes a later
statement, then separately distributes. Statements never distribute cash.
Receipts retain `MOCK_SETTLEMENT_ONLY` and all existing false flags;
`chain_finality=False` belongs only to the example report.

Existing coverage inventory (recorded before adding adapter tests):

| Requirement | Coverage before this change | Existing evidence / adapter gap |
|---|---|---|
| Coverage inventory and mock posture | Sufficiently covered | `docs/status/SETTLEMENT_CONTRACT_EVIDENCE_MAP.md`; `test_adopted_policy.py::AdoptedPolicyTests.test_adopted_policy_posture` and `test_t0_tax_and_held_stay_non_cash`. |
| Conservation and component rejection | Partially covered | `test_mock_settlement.py::SettlementMockTests.test_f02_statement_does_not_infer_fee_or_shrink_faces`; `test_settlement_properties.py::ConservationPropertyTests.test_b_c_seeded_sequences_conserve_and_rejections_change_nothing`; commit/observe matrices in `test_settlement_rejection_atomicity.py`. Adapter forwarding/parity absent. |
| Replay, conflicts and rejection keys | Partially covered | `test_settlement_fsm.py::SettlementFsmTests.test_same_key_replays_and_a_different_body_is_rejected`; `test_returned_data_isolation.py::ReturnedResultReplayTests.test_mutated_first_and_duplicate_results_preserve_original_replay`; rejection/restore probes in `test_settlement_rejection_atomicity.py`. Adapter replay and later key probes absent. |
| Duplicate movement and illegal phase | Partially covered | `test_settlement_properties.py::BindingPropertyTests.test_d_statement_binding`; `test_settlement_fsm.py::SettlementFsmTests.test_illegal_transitions_do_not_move_the_phase`; observe binding/phase tests in `test_settlement_rejection_atomicity.py`. Adapter path absent. |
| One fetch, exact forwarding, unchanged result/error object | Not covered | New `test_statement_adapter.py` wraps actual FSM methods and compares direct execution. |
| Immutable copied recordings and call snapshots | Not covered | New `test_statement_source.py` exercises constructor/output isolation and deterministic faults. |
| Missing/fault/mismatched/invalid source record leaves keys free | Not covered | New adapter tests verify zero FSM calls, unchanged state/journal and successful later use of the same key. |
| Runnable example and separate distribution | Not covered | New adapter example test checks intermediate cash, final conservation, caller policy/order and false flags. |
| CI discovery | Sufficiently covered for suite wiring | Existing `protocol.yml` discovers the entire settlement directory; run `check_ci_test_discovery.py` and its self-test with the new tests present. |

This addition follows settlement contract §§3 and 9 and adopted
`SET-POLICY-DRAFT-0.3`. It changes no FSM, arithmetic, contract, catalogue, SDK or
gate. New-key duplicate-movement journaling is an existing implementation
characterization, not a new contract. Product policy remains **UNDETERMINED**
with Astra/User and the existing I10 legal, tax and accounting owners. No
network, persistence, real services, credentials, funds, chain execution,
runtime activation, production durability or P04 closure is supplied.

## Offline cancellation-acceptance source

Existing coverage inventory for `plan-local-refund-acceptance-source`, recorded
before adding its tests (test paths below are relative to this directory):

| Requirement | Existing coverage | Gap / evidence |
|---|---|---|
| Partial acceptance, preserved cash and adjustment increase | Partially covered | `test_settlement_fsm.py::SettlementFsmTests.test_full_refund_acceptance_does_not_close_an_external_return`; `test_settlement_multi_payee_refund.py::RefundReplayTests.test_i_seeded_fsm_refund_command_sequences`. Adapter path absent. |
| Duplicate replay and conflicting source binding | Partially covered | `test_settlement_properties.py::BindingPropertyTests.test_d_acceptance_binding`; seeded refund replay corpus above. Adapter fetch/replay parity absent. |
| Missing obligation and excessive acceptance | Partially covered | `test_settlement_rejection_atomicity.py::SettlementRejectionAtomicityTests.test_acceptance_refund_obligation_required_leaves_no_trace` and `test_acceptance_exceeds_obligation_leaves_no_trace`. Source boundary and adapter rejection-key probes absent. |
| Missing, malformed, mismatched and fault records | Not covered for cancellation source | Statement-source tests provide a pattern; new adapter tests must prove no FSM call, mutation or key binding. |
| Immutable recordings, exactly one fetch, no retry/fallback | Not covered for cancellation source | New source isolation and adapter call-count tests. |
| Partial-refund distribution blocking | Sufficiently covered at FSM level | `test_settlement_fsm.py::SettlementFsmTests.test_refund_block_survives_replay_and_is_not_a_clawback`. Retain regression; exercise blocking in the new example. |
| Runnable journey and false flags | Not covered for this journey | New example tests verify arithmetic, explicit obligation/observation sequence and journal restoration. |
| CI discovery | Sufficiently covered for wiring | Existing `protocol.yml` discovers this directory; new `test_cancel_acceptance*.py` files need no workflow change. |

`CancelAcceptanceSource.fetch(settlement_id, source_id)` is an internal Python
interface. Records contain exactly `settlement_id`, `source_id` and `amount`.
`CancelAcceptanceAdapter.apply(settlement_id=..., source_id=...,
idempotency_key=...)` fetches once on every explicit invocation, including
replay. It rejects absence, invalid shape and non-string/mismatched identities
before calling the FSM. It forwards the amount and caller's key unchanged to
`SettlementMachine.observe_mock_cancel_acceptance`. Economic, identifier,
phase, binding and idempotency validation stay in that FSM; its result and
exceptions propagate unchanged. Source exceptions are local diagnostics,
not new protocol error codes. There is no cache, retry or fallback.

`FakeCancelAcceptanceSource(recordings=...)` copies an identity-pair mapping
of immutable JSON text or `SyntheticCancelAcceptanceFault.ERROR/TIMEOUT`.
Read-only recordings never get consumed; each fetch parses a fresh document,
and `calls` returns a tuple snapshot. Faults raise `CancelAcceptanceSourceError`
immediately with no clock/wait. Failures imply neither cancellation absence
nor refund completion.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 reference/settlement_f01_f03/example_cancel_acceptance_adapter.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s reference/settlement_f01_f03 -t reference/settlement_f01_f03 -p 'test_cancel_acceptance*.py'
```

The new example also requires `run_example(*, policy, order)` fixture inputs.
It uses the statement adapter to commit synthetic gross 100,000, cash 97,000
and fee 3,000. It explicitly binds a 40,000 refund obligation, then separately
observes caller-selected synthetic acceptances of 10,000 and 5,000. Cash stays
97,000; adjustment outstanding rises 0 → 10,000 → 15,000; refund outstanding
ends at 25,000. A separate distribution then allocates the confirmed cash under
the caller order. Receipts retain `MOCK_SETTLEMENT_ONLY`, `REQUESTER` refund
burden after binding (B5, owner decision 2026-11-10, `SET-POLICY-DRAFT-0.4`), and
false execution, bank debit, external-return closure and durability flags.
No receipt fields are added. New source tests cover recording isolation;
adapter tests compare direct receipts/errors/state/journal, probe rejection
keys and source failures, and restore the example journal. New-key repeated
source journaling is an existing implementation characterization, not a new
contract rule.

This follows contract §§5 and 9 without changing contracts, FSM semantics,
arithmetic, catalogue, SDK or gate. It does not translate `provider_facts`
cancellation histories, derive event identities, initiate cancellation, infer
customer credit, choose refund burden or close external returns. Refund
liability remains **UNDETERMINED — User/legal through I10**; provider
authentication remains **UNDETERMINED — Toss/User**; event-identity policy
remains with **Astra**. All recordings and fixture values are synthetic.
No network, real service, real funds, persistence, production runtime or
chain execution is supplied or verified.
