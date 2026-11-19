# Local F04 credit desk

`CreditSession` exposes the existing in-memory `CreditMachine` in one fresh,
synthetic session. The JSONL CLI accepts explicit local requests and embeds the
FSM's receipts, views and domain error codes unchanged. Provenance is always
`MOCK_CREDIT_F04_ONLY`; the exposure ledger is `MOCK_EXPOSURE`.

This is the mock boundary in [CREDIT_ADVANCE_F04.md](../../docs/contracts/CREDIT_ADVANCE_F04.md).
Local method selectors are not additions to the protocol catalogue or OpenAPI.

## Importable session

Use the existing module-directory convention (put `reference/credit_advance_f04`
on your Python import path):

```python
from credit_session import CreditSession

# Caller-owned synthetic inputs; these numbers establish no product policy.
session = CreditSession()
print(session.view("adv-1"))
```

`CreditSession(settlement_source=None, ownership_source=None)` forwards the nine
mutating methods and three reads below with the existing FSM signatures and
errors. An optional `settlement_source` (for example a real local
`SettlementMachine` from `reference/settlement_f01_f03`) is read by the machine's
existing bound-draw `COMMITTED` gate; `ownership_source` is only compared through
`canonical_state`, exactly as the machine already does. The session supplies no
policy values, faces, approvals or automation. It has no journal export/import,
restoration, persistence or external-execution interface. Returned snapshots
retain the FSM's existing copy behavior.

## Schemas

The fixture has exactly these fields; `settlement_setup` is `null` (no source)
or an array replayed in order onto one fresh real `SettlementMachine`:

```json
{"fixture_version":1,"provenance":"MOCK_CREDIT_F04_ONLY","settlement_setup":null}
```

Each setup entry has exactly `operation`, `settlement_id`, `idempotency_key` and
`body`, whitelisted to `initiate` (`trade_id`, `gross`, `debtor_role`, `policy`,
optional `currency`), `authorize`/`capture` (`{}`), `commit` (`movement_id`,
`gross`, `amount`, `fee`, `tax`, `held`, `adjustment`, optional
`adjustment_reason`), `fail` (`reason`) and `cancel` (`reason`). Setup FSM
rejections propagate with their unchanged codes; no synthetic settlement source,
claim-snapshot adapter or repayment-note source is constructed.

Each JSONL line has exactly `operation` and `arguments`. Every mutating operation
requires `advance_id` and `idempotency_key`; the reads do not take idempotency
keys.

| Operation | Other required arguments | Optional arguments (existing default `None`) |
|---|---|---|
| `offer` | `face`, `amount`, `beneficiary_role` | `product` |
| `approve`, `close`, `reconcile` | none | none |
| `reject`, `cancel`, `default` | `reason` | none |
| `bind_settlement` | `settlement_id` | none |
| `draw` | `draw_id` | none |
| `repay` | `repay_id`, `sequence`, `amount` | none |
| `view` | `advance_id` only | none |
| `view_claim` | `claim_id` only | none |

`face` must be a JSON object; the FSM's existing `_parse_face` retains all face
predicates (mock provenance, KRW, obligation arithmetic, frozen flags, refund
bearer states). The desk never derives a face from the settlement source: callers
embed a snapshot themselves, for example `book.view(id)["claim"]` from the same
local book. `product` is forwarded unchanged; any non-null value is the FSM's
existing `CREDIT_PRODUCT_UNDEFINED` refusal. No amounts, identities, reasons,
sequences or terms are inferred or defaulted. `open_terms` stays `UNDETERMINED`
under adopted option A.

## Commands and journeys

Run from the repository root, using only the Python standard library:

```bash
python3 reference/credit_advance_f04/credit_cli.py --fixture reference/credit_advance_f04/fixtures/committed.json --requests reference/credit_advance_f04/fixtures/lifecycle.jsonl
python3 reference/credit_advance_f04/credit_cli.py --fixture reference/credit_advance_f04/fixtures/committed.json --requests reference/credit_advance_f04/fixtures/settlement_gates.jsonl
python3 reference/credit_advance_f04/credit_cli.py --fixture reference/credit_advance_f04/fixtures/captured.json --requests reference/credit_advance_f04/fixtures/gate.jsonl
python3 reference/credit_advance_f04/credit_cli.py --fixture reference/credit_advance_f04/fixtures/unbound.json --requests reference/credit_advance_f04/fixtures/decline.jsonl
python3 reference/credit_advance_f04/credit_cli.py --fixture reference/credit_advance_f04/fixtures/unbound.json --requests reference/credit_advance_f04/fixtures/boundaries.jsonl
```

`lifecycle` runs offer → approve → bind → draw → repay → repay → close on the
committed book, then replays historical requests. Replayed receipts retain their
historical snapshots with the FSM's `duplicate=true`, `applied=null`; reconcile
returns `matched=true`, `entry_count` and the deterministic `state_digest`.

`settlement_gates` exercises the committed book's binding predicates: mismatched
face gross (`SETTLEMENT_AMOUNT_MISMATCH`), a settlement id unknown to the source
(`UNKNOWN_SETTLEMENT`), a committed claim that is not the face's claim
(`SETTLEMENT_BINDING_CONFLICT`) and rebinding conflicts. `gate` shows a bound
draw on a merely captured claim rejected `SETTLEMENT_NOT_COMMITTED` while an
unbound draw succeeds with `settlement_gate:"UNBOUND"`. `decline` covers reject,
cancel and default terminal paths. `boundaries` is a code matrix over one
session, including `IDEMPOTENCY_CONFLICT`, `REPAYMENT_ORDER`,
`FACE_SNAPSHOT_FROZEN` and `SETTLEMENT_SOURCE_REQUIRED`. No request is retried,
repaired or reconciled automatically.

## Output and errors

Each output is deterministic sorted JSON containing `operation`, synthetic
`provenance`, and exactly one of `receipt`, `view`, `claim`, `error`. Domain
errors are `{"code":"<unchanged CreditError code>"}`; settlement setup
rejections keep their `SettlementError` code. Format/setup/I/O errors use a
distinct `type` and `message`. Command-line usage errors follow argparse on
stderr.

Exit codes: **0** all accepted; **1** at least one domain rejection; **2** malformed
input, setup or I/O failure. Domain rejection continues only to the next supplied
line. Malformed input stops immediately; earlier accepted requests remain applied.
Empty streams succeed; blank lines are malformed JSON.

Duplicate keys at every depth, non-finite constants and exponent overflow,
invalid JSON/Unicode, wrong object/array structures, missing/extra fields and
unsupported selectors are rejected before dispatch. The FSM retains all value,
lifecycle, idempotency and face predicates.

## Live local subprocess client

`CreditClient` uses only the Python standard library. Importing it launches
nothing. `CreditClient.launch(fixture, cleanup_timeout=...)` explicitly launches
one fresh `credit_cli.py` child using the current interpreter, an absolute local
fixture path, binary stdin/stdout pipes and inherited stderr. The CLI flushes
each JSONL reply, so sequential requests can depend on replies while stdin
remains open. The child alone loads the fixture and owns the business session.

```python
from credit_client import CreditClient

with CreditClient.launch("reference/credit_advance_f04/fixtures/committed.json",
                         cleanup_timeout=1) as client:
    # An explicit read, returning the existing UNKNOWN_ADVANCE domain error.
    reply = client.request({"operation": "view",
                            "arguments": {"advance_id": "caller-selected-id"}})
    print(reply)
```

`request(dict) -> dict` preserves the envelopes above, integer amounts and nested
business payloads. It validates finite JSON data before writing; the existing
CLI/FSM still decides operation, argument and value acceptance. Replies require
newline-terminated strict UTF-8 JSON, exact envelope fields, synthetic provenance,
matching operation and the corresponding object payload. Duplicate keys,
non-finite numbers, mismatches and incomplete output are transport failures.

Only one request or cleanup may run at a time. Concurrent/reentrant calls raise
`CreditClientStateError` before writing. Matching `error.code` domain rejections
permit another explicitly supplied request. Typed fatal errors and startup
errors (`operation:null`) make the client terminal. A startup broken-pipe race
is transport uncertainty, never an inferred domain rejection.

After submission begins, a short write, broken pipe, malformed reply, EOF or
interruption raises `CreditTransportUncertainty` and permanently fences that
instance. `client.uncertainty` retains the submitted `request` snapshot,
`request_bytes` and observed `reply_bytes`. No retry, restart, replay,
compensation or automatic reconciliation occurs. Uncertainty proves neither
rejection nor rollback; earlier work may already have applied.

Reads block without a product response deadline. The caller must supply a finite
positive `cleanup_timeout` (booleans are rejected); it applies only to process
cleanup. `close() -> int` closes stdin, waits, then terminates/kills and reaps
only the owned child if needed. Repeated close returns the same exit code and
preserves uncertainty. A `with` block always calls close, including on caller
exceptions. `client.close()` is process cleanup; a request with
`operation:"close"` is the existing credit-domain transition.

Run the caller-configured example from the repository root:

```bash
python3 reference/credit_advance_f04/example_credit_client.py --fixture reference/credit_advance_f04/fixtures/committed.json --requests reference/credit_advance_f04/fixtures/lifecycle.jsonl --cleanup-timeout 1
```

The example submits the supplied transcript and prints replies plus additional
reads using returned `receipt.credit.advance_id` and `claim_id`. A claim read
starts once `snapshot_frozen` reports a noted claim; before the first draw the
existing machine has no claim to read. The example stops at the first error and
always cleans up. It invents no approval, amount, identifier or policy value.
This is a runnable local example, with no credit console, new adapter,
persistence, sockets, protocol command, SDK/catalogue change or real lending.
Product policy remains **UNDETERMINED — Astra/User**; legal terms remain
**UNDETERMINED — User/legal**.

## Synthetic limitations and Class B

Draw and repay are in-memory mock exposure-ledger transitions. All flags remain
false: `funds_executed`, `bank_debit_observed`, `repayment_observed`,
`economic_finality_claimed`, `interest_defined`, `underwriting_executed`,
`kyc_executed`, `legal_debtor_bound`, `collateral_perfected`, `priority_bound`
and the remaining mock flags. `external_credit` stays `UNSUPPORTED`, ownership
is never mutated and ticket ownership is never authoritative. `default` is a
recorded reason, not a workout; there is no interest, APR, rank, perfection or
recalculation. There are no external calls, funds, credentials, persistence,
production runtime, bank/PG/KYC connections or Wave7 work. Process exit loses
the session.

Existing behavior is preserved, including these contract-undefined
characterizations:

- Stored rejections are not journaled; a later `reconcile` still matches
  journal and views. `MOCK_INVARIANT`, `IDEMPOTENCY_CONFLICT` and
  `INVALID_JOURNAL` rejections are never stored and cannot be replayed as
  first results. See the existing [rejection-atomicity coverage](test_credit_rejection_atomicity.py)
  and the [F04 contract evidence map](../../docs/status/CREDIT_F04_CONTRACT_EVIDENCE_MAP.md).
- `reconcile` restores into a second machine that shares the same injected
  sources; it is a determinism witness, not durable recovery.
- `draw` reads the bound settlement view at call time only; no settlement
  commands are issued and later settlement movement does not rewrite the
  stored `mock_settlement_commit_observed` observation.
- The desk does not expose `export_journal`, `restore`, `canonical_state`,
  `state_digest`, `reject_unsupported` or `attempt_execution`; those remain
  machine-level surfaces covered by their existing tests.

## Cross-boundary settlement-to-credit vector pack

The synthetic pack in
[`fixtures/settlement_credit_boundary_v1.json`](fixtures/settlement_credit_boundary_v1.json)
and
[`fixtures/settlement_credit_boundary_vectors_v1.json`](fixtures/settlement_credit_boundary_vectors_v1.json)
crosses exactly one boundary: a caller copies the F01-F03 settlement view's
`claim` object literally into `CreditMachine.offer(face=...)`. No adapter,
console, subprocess client, protocol command, derivation function or product
policy is involved. Settlement provenance is `MOCK_SETTLEMENT_ONLY`; credit
provenance is `MOCK_CREDIT_F04_ONLY`. Every number and identifier is a
caller-owned fixture literal.

Replay the pack with the standard library only:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B reference/credit_advance_f04/settlement_credit_boundary_vectors.py
```

The driver prints the canonical actual vectors and exits 0 on exact match, 1 on
the first mismatch (naming the scenario and step), and 2 on invalid input. It
dispatches only an explicit allowlist of existing public machine methods; a step
is `{"step_id", "target", "operation", "arguments"}` where `arguments` is the
full keyword call including the identifier parameter (`settlement_id`,
`advance_id` or `claim_id`). A step result is `{"ok": value}` or
`{"error": {"type": "SettlementError"|"CreditError", "code": ...}}`. Both files
are canonical JSON (sorted keys, compact separators, UTF-8, one trailing
newline); the vector file pins the fixture bytes with `fixture_sha256`.

The six scenarios and their acceptance tags:

| Scenario | Covers |
| --- | --- |
| `S1_captured_face_no_derivation` | captured claim snapshot embedded as the face; early draw refuses with `SETTLEMENT_NOT_COMMITTED`; the frozen face keeps `confirmed_cash_on_face: 0` after the settlement later commits |
| `S2_committed_face_no_derivation` | committed claim snapshot embedded as the face; draw observes the mock commit and claims no finality |
| `S3_face_snapshot_frozen_and_stable_view_claim` | first note freezes the face; a modified later face fails `FACE_SNAPSHOT_FROZEN`; `view_claim` is byte-equal before and after a settlement refund and partial acceptance |
| `S4_refund_obligation_partial_acceptance` | refund obligation and partial acceptance are visible on the settlement claim; the credit face has no refund fields; `funds_executed` stays false |
| `S5_shared_exposure_two_advances` | two advances share one exposure ledger; only the caller-supplied amounts set the limit; an over-ceiling draw fails `ADVANCE_EXCEEDS_OPEN_FACE` without changing the offer; the residual reserves exactly |
| `S6_reconciliation_gap_reported_no_repair` | a settlement refund is absent from the frozen credit face and a second advance still draws; both reconciles report `matched: true` and neither repairs the gap |

Existing coverage is cited, not duplicated:

- Captured-versus-committed gate and the no-finality draw:
  [`fixtures/settlement_gates.jsonl`](fixtures/settlement_gates.jsonl) and
  `test_credit_fsm.py::CreditFsmTests.test_bound_draw_waits_for_mock_commit_and_does_not_claim_finality`.
- The credit gate does not read the settlement view's refund fields:
  `test_credit_properties.py::ClassBCharacterizationTests.test_b_the_gate_does_not_read_refund_fields_of_the_settlement_view`.

The reconciliation gap is a **contract-undefined Class B characterization**. The
pack reports it as `{"code": "SETTLEMENT_REFUND_NOT_REFLECTED_IN_CREDIT_FACE",
"contract_status": "UNDEFINED", "repair": "NONE"}`; it implements no repair and
adopts no pending Finance design or product term. Tests are run by the existing
suite discovery (`test_settlement_credit_boundary.py`), so no CI file changes.
No claim of durability, finality, bank exactly-once, live funds, production
readiness or product-policy adoption is made.

## Settlement variance observation (CR-CAPITAL-1110 #1)

[`settlement_variance.py`](settlement_variance.py) defines the F04 §7.11
settlement-variance observation between the F01–F03 settlement and F04 credit
mock views:

```text
variance = sum(settlement_view["obligations"][i]["outstanding"])
           - credit_view["open_face"]
```

It reads only caller-supplied literal snapshots; it does not call either
machine, derive a face, repair a gap or authorize exposure. `tolerance` is a
required keyword with no default: omission is `TOLERANCE_REQUIRED`, and a
non-`int` (including `bool`) or negative value is `TOLERANCE_INVALID`.
`within_tolerance` is `abs(variance) <= tolerance` and is never an acceptance.
Every record is `fail_closed: true`, `authorizes_exposure: false`,
`mutates_state: false`, and maps to `NOT_BOUND` with repair `NONE`.
`cash_delta` and `recovery_delta` are diagnostic companions excluded from the
formula and the tolerance gate; the refund component is `NOT_BOUND` because the
F04 view has no refund field. Signs are `POSITIVE` (settlement outstanding
exceeds the frozen credit face), `NEGATIVE` (the frozen face exceeds settlement
outstanding) and `ZERO` (equal at the observed values only).

The canonical fixture
[`fixtures/settlement_variance_v1.json`](fixtures/settlement_variance_v1.json)
is pinned by `FIXTURE_SHA256`; its six scenarios are literal snapshots captured
from `MockSettlement.view` and `MockCredit.view_claim`, including a later
partial distribution, a full refund reclassification, a positive observation,
and the exact/one-past tolerance boundary.

Vendoring: `settlement_variance.py` and the fixture may be copied
byte-for-byte. The module imports only the Python standard library and reads no
other reference module. Replay with:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B reference/credit_advance_f04/settlement_variance.py --check
```

No protocol command, FSM state, error-table entry, OpenAPI byte or product
policy value is added. Tolerance values stay caller-supplied; a future binding's
owner is the User. Tests are reached by the existing credit-suite discovery
(`test_settlement_variance_contract.py`), so no CI workflow change is needed.

## Shared exposure observation (CR-CAPITAL-1110 #2)

[`shared_exposure.py`](shared_exposure.py) defines the F04 §7.12 shared-exposure
observation across claims or advances that the caller groups under one debtor
or pool label:

```text
group_outstanding_exposure = sum(view["outstanding_exposure"])
group_drawn_exposure       = sum(view["drawn_exposure"])
group_repaid_exposure      = sum(view["repaid_exposure"])
group_open_face            = sum(claim["open_face"])      # once per distinct claim_id
group_reserved_open        = sum(claim["reserved_open"])  # once per distinct claim_id
group_residual_unreserved  = group_open_face - group_reserved_open
```

It reads only a non-empty list of caller-supplied literal `CreditMachine.view`
snapshots; it does not call any machine, recompute a frozen face, repair a gap
or authorize exposure. Advance-level sums are per view; claim-level capacity is
counted once per distinct `claim_id`, and views sharing a claim must agree on
`trade_id`, `open_face`, `reserved_open` and `residual_unreserved`
(`VIEW_BINDING_CONFLICT` otherwise). Views must be frozen
(`snapshot_frozen: true`, phase `DRAWN`/`CLOSED`/`DEFAULTED`); pre-draw grouping
is undefined in this revision and fails as `VIEW_NOT_FROZEN`. `group_id` is a
caller label, not a legal party: `legal_debtor_bound` stays false.

`limit` is a required keyword with no default: omission is `LIMIT_REQUIRED`,
and a non-`int` (including `bool`) or negative value is `LIMIT_INVALID`.
`within_limit` is `group_outstanding_exposure <= limit`, inclusive at the
boundary, and is never an acceptance. The machine enforces only per-claim
ceilings (`ADVANCE_EXCEEDS_OPEN_FACE`); it never enforces the caller's group
limit. Product limit numbers stay `UNDETERMINED` with owner Astra; legal debtor
identity stays `UNDETERMINED` with owner the User (roadmap D-E, I10).

Frozen faces are not recomputed. After the face snapshot freezes, exposure
moves only through the existing observable transitions: `draw` adds once,
`repay` reduces outstanding but keeps the reservation, `close` releases the
reservation only at zero exposure, and `default` retains both; a `DEFAULTED`
advance still aggregates. Later settlement refunds or cancellations affect the
observation only through those transitions; the refund component is
`NOT_BOUND` and the per-claim settlement gap stays §7.11 territory. Every
record is `fail_closed: true`, `authorizes_exposure: false`,
`mutates_state: false`, and maps to `NOT_BOUND` with repair `NONE`
(`SHARED_EXPOSURE_NOT_BOUND` is a reference-only label, not a protocol code).

The canonical fixture
[`fixtures/shared_exposure_v1.json`](fixtures/shared_exposure_v1.json)
is pinned by `FIXTURE_SHA256`; its six scenarios are literal snapshots captured
from `MockSettlement` recognition plus unbound `CreditMachine` draws:

| Scenario | Covers |
| --- | --- |
| `E1_two_advances_one_claim_exact_limit` | two advances on one claim; claim capacity counted once; outstanding exactly at the caller limit |
| `E2_two_claims_one_debtor_label_over_limit` | two claims under one caller debtor label; the sum exceeds the limit and is reported fail-closed, not rejected by the machine |
| `E3_pool_three_claims_default_still_aggregates` | three claims under one pool label; a `DEFAULTED` advance keeps its reservation and still aggregates |
| `E4_refund_after_freeze_face_unchanged` | a full settlement refund reclassification leaves the frozen face and exposure byte-equal; the §7.11 variance observes the gap separately |
| `E5_exact_limit_boundary_within` | the same views as E2 at the exact sum boundary: `within_limit` is inclusive |
| `E6_repay_then_close_reservation_released` | partial repay keeps the reservation; full repay then close releases it; exposure moves only via transitions |

Existing coverage is cited, not duplicated:

- Per-claim ceilings and the frozen snapshot:
  `test_mock_credit.py::CreditAdvanceMockTests.test_claims_do_not_share_a_ceiling_and_the_snapshot_stays_frozen`.
- Face stability across later settlement changes:
  `test_credit_properties.py::MachinePropertyTests.test_the_face_snapshot_stays_frozen_after_later_settlement_changes`.
- The boundary pack's `S5_shared_exposure_two_advances` and
  `S6_reconciliation_gap_reported_no_repair` scenarios in
  [`fixtures/settlement_credit_boundary_v1.json`](fixtures/settlement_credit_boundary_v1.json)
  remain the per-claim ceiling and gap evidence; this module extends them with
  the cross-claim group observation instead of re-testing them.

Vendoring: `shared_exposure.py` and the fixture may be copied byte-for-byte.
The module imports only the Python standard library and reads no other
reference module. Replay with:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B reference/credit_advance_f04/shared_exposure.py --check
```

No protocol command, FSM state, error-table entry, OpenAPI byte or product
policy value is added. Limit values stay caller-supplied. Tests are reached by
the existing credit-suite discovery (`test_shared_exposure_contract.py`), so no
CI workflow change is needed. No claim of durability, finality, bank
exactly-once, live funds, production readiness or product-policy adoption is
made.

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s reference/credit_advance_f04 -t reference/credit_advance_f04
```

The [local evidence record](../../validation/2026-11-05-plan-local-credit-desk/README.md)
maps reused lifecycle coverage and new session/fixture/CLI tests, records
actual checks and transcripts, and states remaining gates. Builder checks do not
replace A2 non-author exact-final-head review or completed/success KTX and KIX
exact-final-head CI. No merge authorization is implied.

The [client evidence record](../../validation/2026-11-06-plan-local-credit-stdio-client/README.md)
adds live-child parity, transport failure/fencing, import and cleanup coverage.

## Economics refund consumer vectors

The [economics consumer field guide](../../docs/status/ECONOMICS_CREDIT_CONSUMER_FIELD_GUIDE.md)
connects public `EconomicsSession` snapshots to the unchanged F04 machine and
variance/shared-exposure observers. The canonical
[input histories](fixtures/economics_credit_consumer_v1.json) and
[public result vectors](fixtures/economics_credit_consumer_vectors_v1.json)
cover separate partial REQUESTER, full-before-distribution and
full-after-distribution refunds after two draws freeze the original face.
Explicit distribution and mock cancellation acceptance leave the complete
credit views, claim, journal and digest unchanged. Arithmetic expectations are
separate literals; input/vector/source bytes are pinned. The captured snapshot
reader and replay code exist only in the test module.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s reference/credit_advance_f04 -t reference/credit_advance_f04 -p test_economics_credit_consumer_vectors.py
```

This is offline synthetic evidence for kix-capital, with no external consumer
acceptance or published reads. Observations remain `NOT_BOUND`, repair `NONE`,
without exposure authority. Product values stay `UNDETERMINED` under existing
owners. See the [builder validation record](../../validation/2026-11-13-plan-economics-credit-consumer-vectors/README.md)
for actual checks and remaining review/CI gates.
