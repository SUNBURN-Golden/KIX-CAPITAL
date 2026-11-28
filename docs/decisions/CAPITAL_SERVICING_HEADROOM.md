# CAPITAL_SERVICING_HEADROOM — Bounded capacity for servicing existing cases

> **PROVISIONAL PRODUCT DECISION**
>
> Decision attribution: **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**.
>
> Date: **2026-11-04** · Capital main **5cfb044** · kix-protocol **c641a74**.
>
> Simulation/product design only; no real money; production **NOT_AUTHORIZED**. Legal, tax and accounting statements remain working assumptions pending professional review. No upstream adoption, deployment authorization or production availability is claimed.
>
> Execution provenance: prepared by Codex; the requested attribution is retained. Claude CLI execution and fallback attempts are not evidenced.

Reserve **100 of 500 receipt slots** and **200 of 2,000 overlay slots**. New admission must finish at or below **400 receipts and 1,800 overlay entries**. Servicing and clock maintenance may use the shared reserve, subject to all existing absolute limits.

## 1. 결정 요약

| Item | Decision | CAP rows | Consumer |
|---|---|---|---|
| `command_budget_classes` | ADOPTED. Classify all 10 facade and 12 overlay commands and the auxiliary routes | CAP-01, CAP-04 | `capital/service.py`; facade contract |
| `receipt_headroom` | ADOPTED: hard 500; reserve 100; admission 400 | CAP-01, CAP-04 | Facade; facade-load-harness |
| `overlay_entry_headroom` | ADOPTED: hard 2,000; reserve 200; admission 1,800 | CAP-01, CAP-11 | Overlay; facade-load-harness |
| `compound_command_accounting` | ADOPTED: actual complete footprint; atomic preflight | CAP-01, CAP-11 | overlay-repayment-posting; overlay-recovery-writeoff |
| `existing_workspace_behavior` | ADOPTED: restore valid history above admission cutoffs unchanged | CAP-11 | Workspace restore; facade |
| `capacity_refusal_precedence` | ADOPTED: authorized replay before growth checks; hard ceilings before admission cutoffs | CAP-01, CAP-11 | Facade and overlay validation |
| `remaining_hard_limits` | ADOPTED: retain numeric overlay bounds and authoritative per-advance repayment bounds | CAP-04, CAP-11 | Overlay capacity and repayment validators |

## 2. KIX 비전 연결

[Authority model A-4](/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md) distinguishes stopping new commitments from preserving existing obligations, evidence and historical restoration. This decision applies that distinction to local capacity without importing chain authority.

The [SEAMS](../SEAMS.md) document keeps durable storage and upstream adoption unbound. [CAPITAL_DEMO_BOOK](CAPITAL_DEMO_BOOK.md) retains its separate script target of at most 300 operations. The [accounts/tax/legal](CAPITAL_ACCOUNTS_TAX_LEGAL.md) and [claim-slice registry](CAPITAL_CLAIM_SLICE_REGISTRY.md) decisions preserve provisional treatment and financial-policy references.

Protocol DEVELOPMENT_PLAN §10 separates budgets for new intake from budgets for completion, observation, cancellation and recovery. This decision applies that principle to counts in the local workspace. The adopted absolute overlay bounds come from [CAPITAL_OVERLAY_STATE](CAPITAL_OVERLAY_STATE.md). The command inventory follows [facade-v1](../../capital/contract/facade-v1.json), [server dispatch](../../capital/server.py) and [service dispatch](../../capital/service.py).

## 3. 항목별 결정

### 3.1 `command_budget_classes`

Apply the following budget classes to fresh commands.

| Surface | ADMISSION | SERVICING | MAINTENANCE |
|---|---|---|---|
| `/api/commands` | `offer`, `approve`, `bind_settlement`, `draw` | `reject`, `cancel`, `repay`, `close`, `default`, `reconcile` | None |
| `/api/overlay/commands` | `register_slice`, `open_slice`, `record_external_fact` | `post_repayment`, `post_recovery`, `post_writeoff`, `record_acceleration`, `impair_slice`, `post_slice_recourse`, `resolve_slice`, `void_slice` | `advance_day` |

ADMISSION covers creating a case, proposing a slice and preparing or activating new exposure, including `approve`, `bind_settlement`, `draw` and `open_slice` for existing identifiers. Apply the admission cutoffs to `record_external_fact` because organizers can append a simulated observation against a claim fixture before any advance or slice exists. Recording an unverified assertion creates no exposure and grants no settlement authority.

SERVICING applies to an advance or slice already present in the workspace before the attempt. If a command in that column targets no persisted advance or slice and would store a rejection, apply the admission cutoffs to the rejected receipt. This keeps requests for unknown cases from consuming the reserve. `reconcile` in the table is the mutating facade command. The GET reconciliation route is a read.

Auxiliary surfaces are classified exhaustively by current route:

- Every current GET route, including previews, underwriting, scenarios, exports, operation lookup and static assets: **READ**, zero receipt/overlay growth.
- `/api/agent/query_grant` and `/api/agent/query_subject`: **READ**.
- `/api/agent/propose_action`, `/api/agent/withdraw_proposal` and `/api/agent/propose_grant_change` are **AUXILIARY**. The existing in-memory agent lane handles them outside the workspace counts.
- `/api/session`: **AUXILIARY** session handling; it neither resets workspace counts nor grants capacity.
- `/api/agent/execute`: **DISABLED**; preserve existing refusal and zero writes.

An authorized exact retry is **REPLAY**, regardless of its original class. Unknown commands refuse before mutation. `recognize_claim` is not a current facade command and gains no authorization here.

ADMISSION wins any mixed operation. Generated effects inherit the complete operation’s class. A clock command with its existing explicit write-off directive remains reserve-eligible, but this classification grants no automatic write-off authority. Adding identifiers, aliases or persistent effects requires updating the map before activation.

### 3.2 `receipt_headroom`

Let `R` be persisted facade receipts, including accepted and persisted rejected outcomes. Let `ΔR` include every receipt the complete attempt would append.

Admission requires `R + ΔR ≤ 400`. Servicing and maintenance require `R + ΔR ≤ 500`. Both admission dimensions must pass even when one has zero growth.

Persisted business rejections consume their originating command’s budget after the existing-case check in §3.1. Validation failures that currently append nothing keep that behavior. Capacity refusals append nothing. An overlay response reconstructed from an overlay entry adds zero facade receipts.

**Admission boundary:** with `R=399` and sufficient overlay capacity, a one-receipt admission reaches 400. Another one-receipt admission refuses. A two-receipt admission starting at 399 also refuses completely.

### 3.3 `overlay_entry_headroom`

Let `O` count persisted overlay entries, across all sections, and `ΔO` count every generated entry.

Admission requires `O + ΔO ≤ 1800`. Servicing and maintenance require `O + ΔO ≤ 2000`. Terms bindings, clock ticks, interest entries, margin events and explicit write-off entries each count individually when persisted.

**Clock boundary:** at `O=1997`, a complete three-entry clock result fits; four entries refuse entirely. Every accompanying receipt and byte constraint must also pass.

The reserve is shared, with no per-case allocation, scheduler priority or fairness guarantee. Clock traffic can exhaust it. Spare receipt slots cannot compensate for exhausted overlay, byte or per-case capacity.

A fresh `record_external_fact` appends one overlay entry and zero facade receipts. Keep its existing additional gate, `R + F ≤ 500`, where `F` is the projected count of persisted `EXTERNAL_FACT` entries, including superseded entries. Apply this combined gate on fact recording only. Restoring a workspace or servicing an existing advance does not spend a receipt slot for a previously recorded fact.

### 3.4 `compound_command_accounting`

Plan the complete outcome on bounded disposable state, then validate its projected receipts, journals, overlay entries and serialized size before publication. Use the same locked workspace state for preflight and atomic publication. Commit all effects or none through existing local mechanisms. Refuse a compound operation when those mechanisms cannot provide that behavior.

The `post_repayment` path appends one overlay entry. When principal is positive, it also generates one F04 `repay` receipt. The parent response is reconstructed from the overlay entry.

Consequently, a valid principal-coupled posting at `(R,O)=(499,1999)` reaches `(500,2000)`, provided per-advance, byte and other bounds pass. At `R=500`, the same posting refuses without an overlay-only payment. A posting with zero principal has footprint `(0,1)` and may fit at `R=500`.

Generated F04 receipts consume reserved receipt capacity. Generated clock entries consume reserved overlay capacity. A rejected compound preflight leaves neither behind. Do not invent extra parent charges or omit generated records.

### 3.5 `existing_workspace_behavior`

Restore historical records under existing schema, checksum, link, digest and absolute-limit rules. Admission cutoffs apply to new attempts, not historical replay. Preserve operation identifiers, recorded outcomes, journal ordering and financial bindings.

**Restoration boundary:** a valid workspace at `(450,1850)` restores unchanged. New admission is blocked. Remaining count capacity is at most 50 receipts and 150 overlay entries, subject to every other ceiling.

Restoration preserves already-spent capacity and recorded effects. If the persisted workspace exceeds an applicable absolute limit, use the existing invalid or oversized workspace path and preserve the source. The admission cutoffs and the fact-recording-only combined gate apply to fresh writes. No trimming, migration bypass, counter reset or automatic repair is authorized.

### 3.6 `capacity_refusal_precedence`

Apply this order:

1. Existing envelope, access, identity and early input-size validation.
2. Existing idempotency lookup: return an authorized exact replay; preserve conflict handling.
3. Command classification; refuse unmapped identifiers.
4. Bounded outcome planning, preserving existing domain-validation order.
5. Absolute checks in this order apply to the planned outcome. Check per-case constraints, byte limits, scalar and subsection limits (including the combined fact-recording gate), receipt count, then overlay count. Preserve existing order within each category.
6. Admission checks: receipt cutoff, then overlay cutoff.
7. Existing local atomic publication.

A nonpersisted domain failure retains its existing error. A business rejection that would persist needs capacity for that rejected outcome. For receipt, overlay and admission count refusals, return `SIMULATION_CAPACITY` with no append. Identify the limiting dimension and whether the boundary is absolute or admission-only. Keep the earlier policy’s error for a bound with its own refusal code, such as `FACT_SUPERSEDE_DEPTH`.

**Replay at full capacity:** at `(500,2000)`, an authorized exact retry returns its original outcome without regenerating F04 or clock effects. A fresh identifier is a new attempt. Any positive growth in a full dimension refuses; zero growth in that dimension does not waive other constraints.

### 3.7 `remaining_hard_limits`

| Absolute constraint | Ceiling and authoritative binding |
|---|---|
| Facade receipts | `MAX_OPERATIONS = 500` |
| Overlay entries | `OVERLAY_MAX_ENTRIES = 2000` |
| Each overlay entry | `OVERLAY_ENTRY_MAX_BYTES = 4096`, using existing canonical byte measurement |
| Workspace envelope | `ENVELOPE_MAX_BYTES = 4194304`, using existing envelope measurement |
| Logical simulation day | `SIM_DAY_MAX = 3650` |
| Agent proposals | `AGENT_PROPOSALS_MAX = 500`; preserve existing counting semantics |
| Decision records | `DECISION_RECORDS_MAX = 64`; preserve existing counted kinds |
| Repayment entries per advance | Exact adopted `repayment-posting-decision.capacity_and_envelope_effect.entries_per_advance_max` |
| Each repayment entry | Both 4,096 bytes and adopted `capacity_and_envelope_effect.entry_canonical_bytes_max`; the stricter bound wins |
| Recorded fact entries, entries per claim, supersession depth and string bytes | Exact adopted `observation-record-decision.capacity_bounds` fields `max_fact_entries`, `max_facts_per_claim`, `max_supersede_chain_depth` and `string_field_bytes` |
| Receipts plus recorded fact entries on a fresh fact write | `MAX_OPERATIONS = 500` (see §3.3) |

Load the six overlay bounds from `overlay-state-decision.overlay_capacity_bounds`. The [repayment decision](CAPITAL_REPAYMENT_POSTING.md) specifies 600 postings per advance and 1,024 canonical bytes per entry. The [observation decision](CAPITAL_OBSERVATION_RECORD.md) specifies 128 entries overall, 16 per claim, supersession depth 4 and 64 bytes per string. Consumers resolve these fields from the adopted notes. Missing or invalid bounds take the existing `NOT_BOUND` refusal path.

Preserve the existing clock-step bound, repayment amount bound, unapplied-cash bound, slice constraints and all financial limits. Headroom never overrides them.

This decision narrows new admission under `overlay-state-decision.overlay_capacity_bounds` and `observation-record-decision.capacity_bounds`. The projected footprint for servicing uses `repayment-posting-decision.capacity_and_envelope_effect` and the existing recovery rules. Restoration and replay follow `overlay_replay_rule` and `workspace_envelope_version`. The repayment decision remains authoritative for idempotency and principal coupling. The demo’s 300-operation script target still applies.

The finite guarantee is exclusion of new admission from the final 100 receipt slots and 200 overlay slots. Historical usage, servicing, maintenance and other ceilings can reduce usable capacity to zero. No eviction, automatic cleanup, retention deletion, unlimited completion, backend adoption, distributed scheduling or new storage format is authorized.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "servicing-headroom-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-11-04",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "bases": {
    "capital_main": "5cfb044",
    "kix_protocol_main": "c641a74"
  },
  "scope": "Local simulation/product design; no real money; production NOT_AUTHORIZED; legal/tax/accounting working assumptions pending professional review.",
  "execution_provenance": "Prepared by Codex; Claude CLI execution and fallback attempts not evidenced.",
  "upstream_adoption_claimed": false,
  "entries": {
    "command_budget_classes": {
      "status": "ADOPTED",
      "value": {
        "facade_admission": ["offer", "approve", "bind_settlement", "draw"],
        "facade_servicing": ["reject", "cancel", "repay", "close", "default", "reconcile"],
        "overlay_admission": ["register_slice", "open_slice", "record_external_fact"],
        "overlay_servicing": ["post_repayment", "post_recovery", "post_writeoff", "record_acceleration", "impair_slice", "post_slice_recourse", "resolve_slice", "void_slice"],
        "overlay_maintenance": ["advance_day"],
        "read": ["ALL_CURRENT_GET_ROUTES", "/api/agent/query_grant", "/api/agent/query_subject"],
        "auxiliary": ["/api/session", "/api/agent/propose_action", "/api/agent/withdraw_proposal", "/api/agent/propose_grant_change"],
        "disabled": ["/api/agent/execute"],
        "servicing_requires_persisted_target": true,
        "stored_rejection_without_servicing_target": "ADMISSION_BUDGET",
        "mixed_effects": "ADMISSION_WINS",
        "unmapped": "REFUSE_BEFORE_MUTATION",
        "exact_replay": "ZERO_GROWTH"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Separate new exposure preparation from servicing; classify every current command and auxiliary surface.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "receipt_headroom": {
      "status": "ADOPTED",
      "value": {
        "hard_max": 500,
        "reserve_count": 100,
        "admission_max": 400,
        "count": "All actual persisted receipts, including generated F04 and stored rejections",
        "rejection_class": "ORIGINATING_COMMAND_WITH_EXISTING_TARGET_RULE",
        "capacity_refusal_appends": 0
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Reserve 20 percent without increasing the absolute receipt ceiling.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "overlay_entry_headroom": {
      "status": "ADOPTED",
      "value": {
        "hard_max": 2000,
        "reserve_count": 200,
        "admission_max": 1800,
        "generated_entries": "COUNT_EACH_PERSISTED_ENTRY",
        "reserve": "SHARED_SERVICING_AND_MAINTENANCE",
        "admission_requires_both_postcounts": true,
        "record_external_fact_delta": {"receipts": 0, "overlay_entries": 1}
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-01", "CAP-11"],
      "rationale": "Reserve 10 percent while counting clock fan-out and bindings.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "compound_command_accounting": {
      "status": "ADOPTED",
      "value": {
        "preflight": "BOUNDED_COMPLETE_PROJECTED_OUTCOME",
        "commit": "ALL_OR_NONE",
        "preflight_and_commit_use_same_locked_workspace_state": true,
        "principal_repayment_delta": {"receipts": 1, "overlay_entries": 1},
        "zero_principal_repayment_delta": {"receipts": 0, "overlay_entries": 1},
        "extra_parent_receipt_charge": 0,
        "unsupported_atomicity": "REFUSE"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-01", "CAP-11"],
      "rationale": "Count generated principal receipts exactly once and prohibit partial postings.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "existing_workspace_behavior": {
      "status": "ADOPTED",
      "value": {
        "above_admission": "RESTORE_VALID_HISTORY_BLOCK_NEW_ADMISSION",
        "at_hard_limit": "AUTHORIZED_READ_REPLAY_AND_OTHER_DIMENSION_ZERO_GROWTH_ONLY",
        "above_hard_limit": "EXISTING_INVALID_WORKSPACE_HANDLING_PRESERVE_SOURCE",
        "replenish_on_restore": false,
        "rewrite_history": false,
        "new_storage_format": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-11"],
      "rationale": "Admission cutoffs do not invalidate historical records or create fresh capacity.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "capacity_refusal_precedence": {
      "status": "ADOPTED",
      "value": {
        "order": [
          "EXISTING_INGRESS_ACCESS_IDENTITY",
          "EXACT_REPLAY_OR_CONFLICT",
          "COMMAND_CLASSIFICATION",
          "BOUNDED_OUTCOME_PLANNING",
          "HARD_PER_CASE_BYTES_OTHER_RECEIPTS_OVERLAY",
          "ADMISSION_RECEIPTS_OVERLAY",
          "ATOMIC_PUBLICATION"
        ],
        "capacity_code": "SIMULATION_CAPACITY",
        "capacity_status": 409,
        "capacity_refusal_appends": 0,
        "nonpersisted_domain_failures": "PRESERVE_EXISTING_ERRORS"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-01", "CAP-11"],
      "rationale": "Preserve authorized replay and deterministic nonpersisting capacity refusal.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "remaining_hard_limits": {
      "status": "ADOPTED",
      "value": {
        "MAX_OPERATIONS": 500,
        "overlay_bounds_source": "overlay-state-decision.overlay_capacity_bounds",
        "OVERLAY_MAX_ENTRIES": 2000,
        "OVERLAY_ENTRY_MAX_BYTES": 4096,
        "ENVELOPE_MAX_BYTES": 4194304,
        "SIM_DAY_MAX": 3650,
        "AGENT_PROPOSALS_MAX": 500,
        "DECISION_RECORDS_MAX": 64,
        "per_case_hard_max": {
          "source": "repayment-posting-decision.capacity_and_envelope_effect",
          "field": "entries_per_advance_max",
          "resolution": "EXACT_ADOPTED_VALUE_NO_OVERRIDE"
        },
        "repayment_entry_byte_max": {
          "source": "repayment-posting-decision.capacity_and_envelope_effect",
          "field": "entry_canonical_bytes_max",
          "combine": "MIN_WITH_OVERLAY_ENTRY_MAX_BYTES"
        },
        "observation_bounds": {
          "source": "observation-record-decision.capacity_bounds",
          "fields": ["max_fact_entries", "max_facts_per_claim", "max_supersede_chain_depth", "string_field_bytes"],
          "resolution": "EXACT_ADOPTED_VALUES_NO_OVERRIDE"
        },
        "fact_recording_combined_count": {
          "applies_to": "FRESH_RECORD_EXTERNAL_FACT_ONLY",
          "count": "PROJECTED_FACADE_RECEIPTS_PLUS_ALL_PERSISTED_EXTERNAL_FACT_ENTRIES",
          "hard_max_source": "MAX_OPERATIONS"
        },
        "missing_bound": "EXISTING_NOT_BOUND_REFUSAL",
        "financial_limits": "UNCHANGED_AUTHORITATIVE_REFERENCES",
        "raise_limits": false,
        "eviction": false,
        "automatic_cleanup": false,
        "unlimited_completion": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-04", "CAP-11"],
      "rationale": "Preserve existing absolute overlay, repayment and observation limits.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| Requirement | Disposition |
|---|---|
| Exhaustive command classification | §3.1 enumerates 22 commands and all auxiliary route categories |
| Rejections, generated F04 and clock entries | §§3.2–3.4 specify actual persisted footprints |
| Four boundary examples | Admission §3.2; principal repayment §3.4; restoration §3.5; full replay §3.6 |
| Explicit absolute ceilings | §3.7 gives numeric overlay bounds and exact repayment-bound references |
| Earlier-policy compatibility | §3.7 identifies affected entries and preserved obligations |
| Consumer registration | All seven entries registered as `PENDING_CONSUMER` in `tests/decision_bindings.json`; none is implemented by this note |

Verify the note and binding registry with `python3 scripts/decision_ledger.py`, `python3 scripts/decision_bindings.py --check` and `python3 scripts/docs_surface.py --check`. The evidence-pack corpus is regenerated with `python3 scripts/pack_vectors.py --write` and verified with `--check`.

## 6. Open risks

Shared clock traffic, envelope bytes or per-case limits can exhaust capacity before counts do. Future command effects can invalidate footprint assumptions. Atomic refusal must be verified across compound paths. Source-bound repayment ceilings must resolve successfully; this note supplies no substitute numeric defaults.

## 7. 후속 작업

The `servicing-headroom` implementation consumer loads the adopted policies and verifies admission boundaries, stored rejections, principal coupling, clock fan-out, fact recording, replay, restoration and every absolute bound. The facade and load harness use these same count definitions when reporting capacity. Preserve simulation labels and existing financial-policy references.
