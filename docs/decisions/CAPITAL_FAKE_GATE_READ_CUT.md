# Capital fake-gate read cut — coherent local portfolio snapshots

> **PROVISIONAL PRODUCT DECISION**
>
> Requested decision-maker attribution: **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**.
>
> Date: **2026-11-04** · Capital main: **`9510843`** · kix-protocol context: **`ecefde2`**.
>
> Simulation/product design only; no real money; production **`NOT_AUTHORIZED`**. Authenticated upstream authority and the CAP-16 producer/SDK tuple remain **`NOT_BOUND`**. No upstream adoption or SEMANTIC_CONFORMANCE is claimed.
>
> Execution provenance: the attribution and revisions are supervisor-supplied. Claude CLI execution, three failed attempts, Fable takeover and checkout revisions were not independently verified. This document uses only the supplied excerpts; implementation and executable validation remain separate.

Node: `fake-gate-read-cut-decision`  
Dependencies: `gate-http-producer-fake`, `portfolio-consistent-read`, `read-model-claims-conformance`, `lifecycle-claims-conformance`.

## 1. 결정 요약

`ADOPTED` denotes a provisional Capital product choice, not upstream adoption or implementation completion. CAP associations below describe intended scope, not new coverage receipts.

| Item | Decision | CAP rows | Consumer |
|---|---|---|---|
| `snapshot_payload_scope` | One versioned envelope carries complete canonical producer state, journal and immutable fixture inputs | CAP-14, CAP-16, CAP-20 | ProducerPort snapshot capability |
| `atomic_capture_boundary` | Capture under the fake’s command lock; freeze before serialization | CAP-11, CAP-16 | Owned loopback fake |
| `producer_incarnation_binding` | Bind every cut to a fresh process incarnation, fixture digest and monotonic revision | CAP-16, CAP-20 | Adapter and portfolio coordinator |
| `local_journal_receipt_alignment` | Publish only after exact journal/receipt reconciliation against one Capital generation | CAP-11, CAP-16, CAP-20 | Portfolio snapshot coordinator |
| `response_validation_and_bounds` | Strict schema, full verification, bounded loopback transport and no truncation | CAP-16, CAP-20 | Gate adapter |
| `failure_and_retry_semantics` | Fail closed; one bounded read attempt; command UNKNOWN remains unresolved | CAP-11, CAP-16, CAP-20 | Command gateway and portfolio reader |
| `completeness_claim_limits` | Claim only a complete, aligned local simulation cut | CAP-14, CAP-16, CAP-20 | Portfolio response and evidence |

## 2. KIX 비전 연결

The ambition is a replaceable producer boundary whose financial readouts have reproducible evidence and explicit limits. [SEAMS.md](../SEAMS.md) establishes local ports, factory-based gateway checks and the distinction between stand-ins and adopted upstream contracts. This decision keeps capture behind `ProducerPort`; portfolio consumers receive detached data through that seam.

[CAPITAL_REQUIREMENTS_KO.md](../CAPITAL_REQUIREMENTS_KO.md) separates executable FSM, observation-identity and lifecycle references. This decision preserves those distinctions. It neither imports a new upstream snapshot contract nor turns a local revision into an authenticated source cut.

[CAPITAL_AGENT_CASE_DISCLOSURE.md](CAPITAL_AGENT_CASE_DISCLOSURE.md) requires query non-mutation and scoped disclosure. An internal full snapshot therefore grants no additional disclosure rights. [CAPITAL_ACCOUNTS_TAX_LEGAL.md](CAPITAL_ACCOUNTS_TAX_LEGAL.md) retains simulation-only accounting assumptions; a coherent snapshot does not validate accounting policy.

## 3. 항목별 결정

### `snapshot_payload_scope` — ADOPTED

Define Capital-local format `CAPITAL_LOCAL_FAKE_READ_CUT_V1`, obtained through a read-only snapshot capability on `ProducerPort`. Unsupported implementations explicitly report that capability as unavailable. Consumers must not inspect concrete producer classes or assemble a snapshot from separate live getters.

The envelope contains:

- `schema`, `incarnation_id`, `revision`, `fixture_digest`, `cut_id`;
- `state`: the complete canonical producer state used by supported portfolio projections;
- `journal`: the complete ordered command journal since this fixture incarnation’s baseline;
- `fixtures`: the actual immutable inputs needed to reproduce that baseline and interpret captured state, with named per-input SHA256 digests;
- `payload_digest`: a digest of the envelope excluding this field.

All values are detached, JSON-compatible data. No live object references, file paths requiring later reads, lazy iterators, pagination or omitted “unchanged” sections are permitted. Fixtures contain synthetic inputs only; credentials and DEV_ONLY key material are excluded.

Use local canonical JSON: UTF-8, sorted object keys, compact separators, unescaped Unicode, preserved array order, no duplicate keys, no floats or non-finite values, and signed 64-bit integers. Reject invalid Unicode. These are local diagnostic encoding rules, not KIX-BCS or upstream event identity rules.

`fixture_digest` hashes the canonical named fixture bundle. `cut_id` hashes the canonical object containing schema, incarnation, revision, fixture digest, state digest and journal digest. Hashes detect content inconsistency; they provide no authentication.

### `atomic_capture_boundary` — ADOPTED

The fake owns one lock covering every command mutation, journal append and snapshot capture. A command’s state transition, terminal journal entry and revision increment become visible together. Capture copies or freezes state, journal, fixtures and metadata while holding that same lock; serialization may occur after release.

There is no observable cut between state mutation and its journal entry. Revision starts at zero for the fixture baseline and advances once per journaled terminal command, including deterministic rejection. A rejection before command admission changes neither state nor journal. A snapshot request changes neither revision nor business data.

If copying fails, return an error without a partial envelope. Fixture replacement requires a new incarnation. Future caches and indexes influencing producer results must join this boundary; omission makes capture unsupported.

### `producer_incarnation_binding` — ADOPTED

Generate a fresh 256-bit random `incarnation_id` at fake startup, never restored from fixture files. Revision cannot wrap or reset within an incarnation. The owned launcher supplies the expected incarnation and fixture digest to the adapter before reads are enabled.

The adapter accepts only that configured incarnation. A matching port, identical state, or revision zero cannot establish continuity after restart. Restart invalidates all previous cuts and Capital alignment anchors.

Re-enabling requires explicit local initialization that verifies the fixture baseline and establishes a corresponding Capital baseline. Existing receipts and overlays cannot silently attach to a new incarnation. This initialization is a simulator lifecycle operation, not a query side effect.

The launcher association establishes local ownership assumptions only. It is not authenticated service identity or protection against a hostile local process.

### `local_journal_receipt_alignment` — ADOPTED

Atomic producer capture alone is insufficient. Capital must align it with receipts, producer-to-Capital mappings, overlays and the exact policy inputs used for the portfolio.

Adopt one Capital coordination lock and a monotonic `capital_generation`. All relevant command lifecycles, mapping changes, overlay changes, policy replacement and baseline initialization participate. A command holds the coordination lock through its bounded remote attempt and local receipt handling. A snapshot holds it while freezing Capital inputs, obtaining the producer cut and validating alignment. Always acquire Capital coordination before requesting the fake lock; the fake never calls back into Capital.

At initialization, record a verified baseline: incarnation, fixture digest, baseline producer state/journal digests and the corresponding Capital generation. Initialization requires a known fixture baseline with no unexplained prior commands.

For each terminal command, retain a local reconciliation record binding incarnation, journal position, revision, operation ID, actor, action, canonical request-body digest, terminal outcome and result digest to its Capital receipt. This is a proposed local contract; existing receipt fields are not asserted to contain it already.

A publishable read requires:

1. Matching incarnation and fixture baseline, with contiguous journal positions and revisions.
2. Exactly one attributable Capital terminal receipt for each post-baseline journal entry, and no unmatched producer-affecting terminal receipt.
3. Matching request and outcome fingerprints; duplicate operation IDs, changed historical entries and unexplained producer commands are rejected.
4. Mappings and overlays valid against the captured state and frozen Capital inputs. An overlay may legitimately change without a producer revision, but its generation and references must remain coherent.
5. Available, applicable policy inputs and no unresolved command UNKNOWN.

Validate state by replaying the complete fixture baseline and journal through the supported local deterministic transition model. Recorded outcomes and resulting state must match the envelope. If that adapter cannot perform the required verification, it cannot claim alignment.

This catches direct producer-side mutation even when the journal was left unchanged. A producer revision change is acceptable only when fully explained by the reconciled journal.

The resulting portfolio includes a local read identifier binding `cut_id`, `capital_generation` and digests of the frozen mappings, overlays, receipts and policy. It describes one historical cut, not guaranteed freshness at response delivery.

### `response_validation_and_bounds` — ADOPTED

Use a single read-only request to a configured numeric loopback address: `127.0.0.1` or `::1`. Disable redirects, environment proxies, DNS resolution, compression and connection-level automatic retries. Do not fall back to a different producer.

Adopt these finite limits:

| Limit | Value |
|---|---:|
| End-to-end portfolio read deadline, including coordination wait and validation | 2,000 ms |
| Connection establishment | 250 ms |
| Fake capture-lock wait | 250 ms |
| Response-body read | 1,000 ms |
| Response headers | 16 KiB |
| Encoded response body | 8 MiB |
| Journal entries | 10,000 |
| Fixture inputs | 256 |
| Individual / aggregate encoded fixture inputs | 1 MiB / 4 MiB |
| JSON nesting / total parsed values | 64 / 200,000 |

Each phase uses the smaller of its limit and the remaining total budget. Parsing and replay must also respect the total budget. Enforce streaming byte limits even without `Content-Length`.

Require the exact supported schema, required fields, field types, bounded nonempty identifiers, digest syntax and digest equality. Reject unknown fields in this version, duplicate object keys, revision gaps, inconsistent counts, incomplete bodies and non-success responses.

Limits are rejection thresholds. No truncation, partial success or “best effort” portfolio is permitted. Larger fixtures require a reviewed future local contract version.

### `failure_and_retry_semantics` — ADOPTED

Each query makes at most one remote capture attempt. A later caller-initiated query is a new read with a new deadline; it never resends a command.

| Condition | Expected outcome |
|---|---|
| Concurrent ordinary command or overlay update | Coordination yields a complete before-or-after cut; contention exceeding the deadline returns unavailable |
| Producer mutation after completed capture | The frozen cut remains valid historically; a subsequent read must reconcile the later mutation |
| Direct, unexplained producer change | Reject with internal `UNEXPLAINED_PRODUCER_CHANGE`; quarantine alignment until diagnosed |
| Restart or incarnation mismatch | `INCARNATION_MISMATCH`; require explicit baseline initialization |
| Malformed, oversized or digest-inconsistent response | `INVALID_SNAPSHOT`; discard the envelope |
| Transport timeout, disconnect or exhausted validation budget | `READ_UNAVAILABLE`; publish no portfolio |
| Unsupported producer capability | `SNAPSHOT_UNSUPPORTED`; no multi-call substitute |
| Missing or unavailable policy | `POLICY_UNAVAILABLE`; no financial portfolio projection |
| Unresolved command outcome | `COMMAND_UNKNOWN`; no aligned portfolio |

A command timeout can mean execution occurred remotely. Preserve the existing command UNKNOWN and no-retransmission behavior. Neither matching snapshot state nor a matching journal entry automatically upgrades UNKNOWN to success or authorizes retransmission. Resolution requires a separately supported explicit reconciliation procedure; none is claimed here. Without it, aligned reads remain unavailable for that affected workspace.

Keep failure details internal where disclosure policy requires a uniform unavailable response. A diagnostic capture is never relabeled as a successful portfolio. Failures must not alter receipts, mappings, overlays, grants or logical clocks; separate operational diagnostics may record the error.

### `completeness_claim_limits` — ADOPTED

A successful result may state:

`SIMULATED`, `LOCAL_FAKE`, `snapshot_complete: true`, `capital_aligned: true`, `authenticated_source_cut: false`, `upstream_adopted: false`.

Completeness means all required local inputs passed this contract within one producer cut and one Capital generation. It does not imply distributed serializability, durable recovery, authenticated provenance, current authorization, settlement finality or real-money readiness.

The supplied [requirements excerpt](../CAPITAL_REQUIREMENTS_KO.md) identifies `tests/read_model_claims.json` as an FSM/read-model citation consumer of `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`, and `tests/lifecycle_claims.json` as the LC-TERM/LC-FACT/LC-CUT citation consumer of `e2313ab473ea1b5a7b5b9246a564749188c1c2c8`. Preserve both executable/reference pins. The separate observation-identity reference remains `e2a029d8ac3af7575888dac22fc4bf173ebec232`.

Exact individual claim IDs and current adapter behavior are **UNDETERMINED from the supplied excerpts**. Implementation must reuse verified existing mappings; this decision invents no claim receipt or upstream LC-CUT satisfaction.

## 4. Machine-readable decision

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "fake-gate-read-cut-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-11-04",
  "provisional": true,
  "entries": {
    "snapshot_payload_scope": {
      "status": "ADOPTED",
      "value": {
        "schema": "CAPITAL_LOCAL_FAKE_READ_CUT_V1",
        "contents": ["canonical_state", "complete_journal", "immutable_fixture_inputs"],
        "partial_snapshots": false,
        "encoding": "LOCAL_CANONICAL_JSON",
        "digests": "SHA256"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-14", "CAP-16", "CAP-20"],
      "rationale": "Capture all local projection inputs through ProducerPort without later live reads.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "atomic_capture_boundary": {
      "status": "ADOPTED",
      "value": {
        "mechanism": "SHARED_FAKE_COMMAND_CAPTURE_LOCK",
        "freeze_before_serialization": true,
        "state_journal_revision_atomic": true,
        "capture_mutates_business_state": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-11", "CAP-16"],
      "rationale": "Prevent mixed state and journal observations during concurrent commands.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "producer_incarnation_binding": {
      "status": "ADOPTED",
      "value": {
        "incarnation_random_bits": 256,
        "revision": "MONOTONIC_PER_TERMINAL_JOURNAL_ENTRY",
        "fixture_digest_required": true,
        "restart_action": "INVALIDATE_AND_EXPLICITLY_INITIALIZE",
        "automatic_rebaseline": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-16", "CAP-20"],
      "rationale": "Prevent restart and fixture replacement from masquerading as cut continuity.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "local_journal_receipt_alignment": {
      "status": "ADOPTED",
      "value": {
        "capital_boundary": "COORDINATION_LOCK_AND_GENERATION",
        "journal_receipts": "EXACT_ONE_TO_ONE_POST_BASELINE",
        "state_verification": "DETERMINISTIC_REPLAY",
        "freeze": ["receipts", "mappings", "overlays", "policy"],
        "unexplained_changes": "REJECT",
        "unresolved_command_unknown": "BLOCK"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-11", "CAP-16", "CAP-20"],
      "rationale": "Producer atomicity alone cannot establish a coherent Capital portfolio.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "response_validation_and_bounds": {
      "status": "ADOPTED",
      "value": {
        "network": "OWNED_NUMERIC_LOOPBACK_ONLY",
        "total_deadline_ms": 2000,
        "connect_ms": 250,
        "capture_lock_ms": 250,
        "body_read_ms": 1000,
        "max_header_bytes": 16384,
        "max_body_bytes": 8388608,
        "max_journal_entries": 10000,
        "max_fixture_inputs": 256,
        "max_fixture_bytes_each": 1048576,
        "max_fixture_bytes_total": 4194304,
        "max_json_depth": 64,
        "max_json_values": 200000,
        "strict_schema_and_digest_validation": true
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-16", "CAP-20"],
      "rationale": "Bound resource use and reject incomplete or inconsistent captures.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "failure_and_retry_semantics": {
      "status": "ADOPTED",
      "value": {
        "capture_attempts_per_query": 1,
        "automatic_retries": 0,
        "failures": "UNAVAILABLE_WITH_NO_PORTFOLIO",
        "policy_unavailable": "BLOCK",
        "command_unknown": "PRESERVE",
        "command_retransmission": false,
        "snapshot_resolves_command_unknown": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-11", "CAP-16", "CAP-20"],
      "rationale": "A read failure or successful capture must not change command execution semantics.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "completeness_claim_limits": {
      "status": "ADOPTED",
      "value": {
        "scope": "SIMULATED_LOCAL_FAKE",
        "authenticated_source_cut": false,
        "upstream_adopted": false,
        "semantic_conformance_claimed": false,
        "production": "NOT_AUTHORIZED",
        "cap16": "NOT_BOUND",
        "executable_pins": "UNCHANGED"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-14", "CAP-16", "CAP-20"],
      "rationale": "Local completeness supplies reproducible simulation evidence without authenticated upstream authority.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

The seven entries cover atomic payload capture, incarnation binding, Capital alignment, bounded validation, required failure outcomes and completeness limits.

Implementation acceptance requires deterministic barrier tests for before/after concurrency; restart rejection; direct state and journal tampering; malformed and oversized responses; timeout; unsupported capability; unavailable policy; and command UNKNOWN with zero retransmissions. Successful replay must reproduce the captured state and frozen portfolio inputs.

Claim-file associations and pins are cited above without new mappings. The document contains exactly one decision block. `python3 scripts/decision_ledger.py` was **not run**: its path is outside the authorized read scope. Passing that check remains an integration acceptance requirement, not a claimed result.

## 6. Open risks

Every relevant Capital mutation must participate in coordination; an omitted mutation path defeats alignment. Replay may exceed the deadline for large fixtures, which must fail unavailable. Loopback ownership and hashes provide no defense against a compromised local host. Current receipt-schema compatibility and exact claim IDs remain unverified.

## 7. 후속 작업

Implement the optional ProducerPort capability, fake atomic capture and Capital alignment coordinator; then add the acceptance vectors and verify existing claim mappings. Preserve vendor bytes, executable pins and legacy export construction. If new vector files are introduced, update the hand-maintained documentation surface and run its check.

The supervisor writes this note and runs the decision ledger. No filesystem changes, upstream changes, new storage engine, distributed snapshot protocol, SDK promotion, real producer binding or production authentication are part of this decision.
