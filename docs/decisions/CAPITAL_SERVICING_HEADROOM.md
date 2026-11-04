# CAPITAL_SERVICING_HEADROOM — Bounded capacity for servicing existing cases

> **PROVISIONAL PRODUCT DECISION**
>
> Decision attribution: **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**.
>
> Date: **2026-11-04** · KIX-CAPITAL main **5cfb044** · kix-protocol **c641a74**; supervisor-supplied baselines.
>
> Simulation/product design only; no real money; production **NOT_AUTHORIZED**. Legal, tax and accounting statements are working assumptions pending professional review, not advice. No upstream adoption or production availability is claimed.
>
> Execution provenance: prepared by Codex. Requested attribution is retained; Claude CLI execution, Sonnet execution and fallback attempts are not evidenced.

Reserve **100 of 500 receipt slots** and **200 of 2,000 overlay-entry slots**. New admission must finish at or below **400 receipts and 1,800 overlay entries**. Servicing and clock maintenance share the remaining capacity, subject to every existing hard limit.

## 1. 결정 요약

| Item | Decision | CAP rows | Consumer |
|---|---|---|---|
| `command_budget_classes` | Effect-based classification specified; exhaustive identifier inventory UNDETERMINED | CAP-01, CAP-04 | Facade dispatch; overlay commands |
| `receipt_headroom` | ADOPTED: hard 500, reserve 100, admission 400 | CAP-01, CAP-04 | `capital/service.py`; facade-load-harness |
| `overlay_entry_headroom` | ADOPTED: hard 2,000, reserve 200, admission 1,800 | CAP-01, CAP-04 | `capital/overlay.py`; facade-load-harness |
| `compound_command_accounting` | ADOPTED: complete actual footprint; atomic preflight | CAP-01, CAP-04 | overlay-repayment-posting; overlay-recovery-writeoff |
| `existing_workspace_behavior` | ADOPTED: restore valid history above admission cutoffs | CAP-01, CAP-04 | `capital/store.py`; facade |
| `capacity_refusal_precedence` | ADOPTED: replay first; hard limits before admission limits | CAP-01, CAP-04 | Facade and overlay validation |
| `remaining_hard_limits` | Count ceilings fixed; byte/per-case inventory UNDETERMINED | CAP-01, CAP-04 | Workspace and overlay validation |

## 2. KIX 비전 연결

[Authority model A-4](/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md) separates stopping new commitments from preserving prior obligations, evidence and restoration. This local counting policy applies that distinction without importing chain authority or distributed execution. The [Protocol README](/workspace/capital-run/kixproto-ro/README.md) preserves the boundary between local verification and operational authorization. DEVELOPMENT_PLAN §10 is cited only through the supervisor's description; that file was not opened.

The supplied [SEAMS](../SEAMS.md) excerpt leaves durable storage and upstream contracts unbound. [CAPITAL_DEMO_BOOK](CAPITAL_DEMO_BOOK.md) supplies the historical 500-operation ceiling and a separate script target of at most 300 operations. The review now explicitly identifies the current 500-receipt and 2,000-overlay guards; those are accepted as supervisor evidence, without claiming source inspection.

The supplied [default/recovery](CAPITAL_DEFAULT_RECOVERY.md), [claim-slice](CAPITAL_CLAIM_SLICE_REGISTRY.md) and [accounts/tax/legal](CAPITAL_ACCOUNTS_TAX_LEGAL.md) excerpts preserve financial references and provisional labels. This decision changes no financial limit, recognition policy or legal authority.

## 3. 항목별 결정

### 3.1 `command_budget_classes`

Use the complete operation's effects, including generated writes. An existing case identifier alone does not establish servicing eligibility.

| Class | Behavior covered | Capacity treatment |
|---|---|---|
| ADMISSION | New case or claim (`recognize_claim` is evidenced); new offer, commitment, advance, draw or increased exposure | Both admission cutoffs and all hard limits |
| SERVICING | Existing-obligation repayment, settlement, refund resolution, cancellation/release, margin/default administration, recovery, write-off or closure, with no new exposure | Hard limits; reserve eligible |
| MAINTENANCE | Existing simulation-clock actions and generated accrual/status entries | Hard limits; same shared reserve |
| READ | Queries, previews and exports without persistent mutation | Zero record growth; existing byte/access limits |
| REPLAY | Exact recognized retry returning its stored outcome | Zero growth; no generated effects repeated |
| UNCLASSIFIED | Unknown identifier or insufficiently established effects | Refuse before mutation |

ADMISSION wins every mixed operation. Generated F04 repayment is servicing only when the entire parent operation resolves existing obligations without increasing exposure. Clock classification grants no new posting or automatic write-off authority. A persisted rejection retains its attempted command's class; failed admission cannot spend the reserve.

These are exhaustive **effect classes**, not a verified enumeration of current command identifiers. The pack does not provide that enumeration. `command_budget_classes` remains UNDETERMINED for identifier binding; its target fixes the proposed classifier. The implementation must not enable an incomplete command map.

### 3.2 `receipt_headroom`

Let `R` count persisted facade receipts and `delta_R` count all receipts the complete attempt would append. The review identifies `MAX_OPERATIONS = 500` in `capital/service.py` as the current receipt gate. Preserve it. Admission requires `R + delta_R <= 400`; servicing/maintenance requires `R + delta_R <= 500`. Equality passes.

Count stored successes and stored business rejections. Preserve nonpersisted validation failures as nonpersisted. Capacity refusals append nothing, so repeated refusals cannot drain the reserve. Exact replay adds nothing. Do not charge a parent receipt merely because a user invoked a command: charge it only if that receipt is actually persisted.

**Admission boundary:** at `R=399`, an admission with one receipt reaches 400; at 400, the next such attempt refuses. An admission requiring two receipts at 399 also refuses atomically. Both post-count admission tests apply even if one dimension has zero growth, so a workspace already beyond either cutoff admits no new exposure.

### 3.3 `overlay_entry_headroom`

Let `O` count persisted overlay entries and `delta_O` their complete increment. Preserve the review-supplied `OVERLAY_MAX_ENTRIES = 2000`. Admission requires `O + delta_O <= 1800`; servicing/maintenance requires `O + delta_O <= 2000`.

Each clock-generated entry counts separately. At `O=1997`, a clock operation producing three entries fits exactly; four entries refuse entirely. Any receipts generated by that operation must independently fit. Admission producing two entries at `O=1799` refuses even with spare receipts.

The reserve is shared, with no per-case allocation or priority promise. Clock work can exhaust it. Spare receipts never compensate for overlays, bytes or per-case capacity. Existing representation supplies the counts; no new counter file, journal or storage format is authorized.

### 3.4 `compound_command_accounting`

Preflight the bounded complete effect set before mutation: actual parent receipts, generated F04 repayment receipts, overlay postings and clock fan-out. Count every persisted record once. Internal calls without persisted records add no charge.

Commit the complete operation or none through existing local mechanisms. If those mechanisms cannot prevent a partial compound write, refuse the compound operation; this policy does not authorize storage redesign. Determine rejected-outcome footprints separately from successful ones.

**Principal-coupled repayment:** for an operation whose established footprint is one generated F04 receipt and one overlay entry, `(R,O)=(499,1999)` reaches `(500,2000)`. If its existing path also persists a parent receipt, the footprint is `(2,1)` and the starting receipt count must instead be at most 498. At 499 that two-receipt variant refuses in full. These examples fix the accounting rule without asserting an unseen implementation's multiplicity. No overlay payment may survive without its required principal posting.

### 3.5 `existing_workspace_behavior`

Restore historical records using existing schema, integrity and absolute-limit validation. Do not reapply new admission cutoffs to historical events, rerun external effects, change operation identifiers, rewrite outcomes or reset counters.

**Restoration boundary:** a valid workspace with `(R,O)=(450,1850)` restores unchanged. New admission is blocked. Remaining count capacity is 50 receipts and 150 overlay entries for servicing/maintenance, subject to all other limits. Restoration creates no fresh reserve.

Above an absolute ceiling, preserve the source and retain existing invalid/oversized-workspace handling. No repair, bypass, eviction or cleanup is authorized.

### 3.6 `capacity_refusal_precedence`

Apply this exact order:

1. Existing envelope, access and identity checks, including existing early input-size checks.
2. Idempotency lookup: exact replay returns its stored result; conflicts retain existing handling.
3. Complete-operation classification; unmapped commands refuse.
4. Bounded dry run, preserving existing business-validation order and computing the actual success or rejected-outcome footprint.
5. Hard limits: per-case, bytes, receipts, overlays; preserve existing order within each category.
6. Admission limits: receipts, then overlays.
7. Existing local commit.

A historically persisted business rejection requires capacity for its own footprint. If that footprint cannot fit, return `SIMULATION_CAPACITY` without appending. Existing nonpersisted domain failures need no append capacity. Capacity diagnostics identify dimension and hard-versus-admission boundary. Early ingress checks remain earlier; this sequence does not bypass authentication or authorize resource-unbounded dry runs.

**Replay at full capacity:** at `(500,2000)`, an exact recognized retry returns its stored outcome without rerunning F04 or regenerating clock entries. A fresh identifier is a new attempt. Growth in any full dimension refuses; an operation with zero growth in that dimension still faces every other constraint.

### 3.7 `remaining_hard_limits`

| Absolute constraint | Binding and evidence |
|---|---|
| Receipts | 500; review cites `capital/service.py:52,1178`, `MAX_OPERATIONS` |
| Overlay entries | 2,000; review cites `capital/overlay.py:55`, `OVERLAY_MAX_ENTRIES` |
| Bytes | Every existing request, entry and workspace ceiling remains binding; exact values absent from allowed evidence |
| Per-case capacity | Every existing case ceiling remains binding; exact values absent from allowed evidence |

Never interpret missing values as unlimited. This item remains UNDETERMINED only for the complete byte/per-case inventory, not for the two established count ceilings.

The permitted `tests/decision_bindings.json` identifies affected earlier entries: `overlay-state-decision.overlay_capacity_bounds` and `repayment-posting-decision.capacity_and_envelope_effect`. Add lower admission gates to their count rules; preserve absolute limits, repayment coupling, replay, storage shape and envelope version. The earlier `overlay_replay_rule`, `workspace_envelope_version` and repayment `idempotency_and_lost_response` remain compatibility obligations. The demo's 300-operation script target also remains unchanged.

There is no eviction, automatic cleanup, retention deletion, financial-cap change or unlimited completion guarantee. The finite guarantee is exclusion of admission from the last 100 receipt slots and 200 overlay slots under the new policy. Prior history, servicing, maintenance, bytes and per-case exhaustion can reduce usable capacity to zero. No number of completed cases, latency or production availability is promised.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "servicing-headroom-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-11-04",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "scope": "Local simulation and product design only; no real money; production NOT_AUTHORIZED; legal, tax and accounting statements are working assumptions pending professional review, not advice.",
  "bases": {
    "capital_main": "5cfb044",
    "kix_protocol_main": "c641a74"
  },
  "execution_provenance": "Prepared by Codex; requested decision attribution retained; Claude CLI execution and fallback attempts not evidenced.",
  "upstream_adoption_claimed": false,
  "entries": {
    "command_budget_classes": {
      "status": "UNDETERMINED",
      "target": {
        "policy": "Section 3.1; admission wins mixed effects; unmapped commands refuse before mutation",
        "current_command_inventory": null
      },
      "cap_rows": [
        "CAP-01",
        "CAP-04"
      ],
      "rationale": "The permitted pack does not enumerate current dispatch identifiers. Source presence reported by review does not authorize reading excluded paths.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "receipt_headroom": {
      "status": "ADOPTED",
      "value": {
        "hard_max": 500,
        "hard_max_source": "Review: capital/service.py MAX_OPERATIONS",
        "reserve_count": 100,
        "admission_max": 400,
        "admission_postcondition": "R + delta_R <= 400",
        "servicing_maintenance_postcondition": "R + delta_R <= 500",
        "persisted_rejections": "Count against originating command class",
        "capacity_refusal_appends": 0
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": [
        "CAP-01",
        "CAP-04"
      ],
      "rationale": "Reserve 20 percent of the existing receipt ceiling without increasing it.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "overlay_entry_headroom": {
      "status": "ADOPTED",
      "value": {
        "hard_max": 2000,
        "hard_max_source": "Review: capital/overlay.py OVERLAY_MAX_ENTRIES",
        "reserve_count": 200,
        "admission_max": 1800,
        "admission_postcondition": "O + delta_O <= 1800",
        "servicing_maintenance_postcondition": "O + delta_O <= 2000",
        "clock_generated_entries": "Count every persisted entry"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": [
        "CAP-01",
        "CAP-04"
      ],
      "rationale": "Reserve 10 percent of the existing overlay ceiling; clock and servicing share it.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "compound_command_accounting": {
      "status": "ADOPTED",
      "value": {
        "count": "Every actual persisted record once across the complete operation",
        "generated_f04_receipts": "Included; no synthetic parent receipt charge",
        "clock_generated_entries": "Included",
        "preflight": "Bounded complete effect set before mutation",
        "commit": "All or none through existing local mechanisms",
        "unsupported_atomicity": "Refuse compound mutation"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": [
        "CAP-01",
        "CAP-04"
      ],
      "rationale": "Prevent generated repayment bypasses and partial principal postings.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "existing_workspace_behavior": {
      "status": "ADOPTED",
      "value": {
        "above_admission_cutoff": "Restore valid history unchanged; block new admission",
        "at_hard_limit": "Reads and exact replay remain; only zero-growth effects in the full dimension can fit",
        "above_hard_limit": "Preserve source; existing invalid-workspace handling",
        "counter_basis": "Existing persisted records",
        "reset_eviction_cleanup": false,
        "new_storage_format": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": [
        "CAP-01",
        "CAP-04"
      ],
      "rationale": "Admission limits do not invalidate historical workspaces or replenish reserves.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "capacity_refusal_precedence": {
      "status": "ADOPTED",
      "value": {
        "order": [
          "EXISTING_ENVELOPE_ACCESS_IDENTITY",
          "EXACT_REPLAY_OR_IDEMPOTENCY_CONFLICT",
          "COMMAND_CLASSIFICATION",
          "BOUNDED_DRY_RUN_EXISTING_DOMAIN_ORDER",
          "HARD_PER_CASE_BYTES_RECEIPTS_OVERLAY",
          "ADMISSION_RECEIPTS_OVERLAY",
          "EXISTING_LOCAL_COMMIT"
        ],
        "ingress_size_checks": "Remain earlier",
        "persisted_domain_rejection": "Requires applicable capacity",
        "capacity_code": "SIMULATION_CAPACITY",
        "capacity_refusal_appends": 0
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": [
        "CAP-01",
        "CAP-04"
      ],
      "rationale": "Preserve replay while making capacity refusals deterministic and nonpersisting.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "remaining_hard_limits": {
      "status": "UNDETERMINED",
      "target": {
        "receipt_hard_max": 500,
        "overlay_hard_max": 2000,
        "byte_hard_max": null,
        "per_case_hard_max": null,
        "missing_limit_behavior": "Preserve authoritative existing ceilings; never default to unlimited",
        "financial_limits": "Unchanged original policy references",
        "raise_limits": false,
        "eviction": false,
        "automatic_cleanup": false,
        "unlimited_completion": false
      },
      "cap_rows": [
        "CAP-01",
        "CAP-04"
      ],
      "rationale": "Review supplies receipt and overlay ceilings but no byte/per-case values; prerequisite overlay-state text is outside the explicit allowlist.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| Requirement / review finding | Disposition |
|---|---|
| Machine schema and provisional labeling | Top-level status added. UNDETERMINED entries omit `value`, `provided_by` and `date`, as required by the reviewed validator. Five ADOPTED entries retain complete metadata. |
| Missing bindings | Five ADOPTED entries registered in `tests/decision_bindings.json` as PENDING_CONSUMER; never CONSUMED. |
| Concrete count limits and examples | 500/2,000 hard limits, 400/1,800 admission limits, rejected attempts, clock fan-out, generated F04, replay and restoration specified above. |
| Exhaustive command identifiers; exact byte/per-case ceilings | Unresolved evidence gap; partial rebuttal below. |
| Repository checks | PASS (exit 0): `python3 scripts/decision_ledger.py`, `python3 scripts/decision_bindings.py --check`, `python3 scripts/docs_surface.py --check`. Decision/surface tests passed; all 25 binding tests passed after correcting registration order. These checks validate documentation/registration, not implementation completeness. |

**Scope rebuttal:** the review establishes that excluded prerequisite/code files exist; it supplies two count constants, which this revision accepts. It supplies neither the full dispatch inventory nor byte/per-case constants. The explicit exact-path allowlist excludes `CAPITAL_OVERLAY_STATE.md`, `capital/service.py` and `capital/overlay.py`; its prohibition on exploration remains in force. Presence is therefore not evidence of contents. The instruction to use UNDETERMINED for missing evidence applies to those remaining fields. Full acceptance is not claimed.

## 6. Open risks

An unverified alias or generated effect can change classification or footprint. Shared clock traffic can consume all reserve. Existing compound persistence may not provide all-or-none publication. The two unresolved inventories prevent safe activation; successful documentation checks would not resolve them.

## 7. 후속 작업

The supervisor publishes the complete note. The implementation consumer binds every current command identifier and existing byte/per-case constant from authorized source evidence, retaining decided financial policy by reference. No renewed decision is required for the five ADOPTED choices. Verify exact-cutoff admission, stored rejection accounting, generated principal repayment, clock fan-out, full-capacity replay, restoration and unchanged absolute-limit refusal before activation. Keep backend adoption, distributed scheduling, new storage formats and production authorization outside this node.
