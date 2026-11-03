# CAPITAL_SERVICING_HEADROOM — Bounded capacity for servicing existing cases

> **PROVISIONAL PRODUCT DECISION**
>
> Requested decision attribution: **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**.
>
> Date: **2026-11-04** · KIX-CAPITAL baseline: **8ab3d95** · kix-protocol context baseline: **c641a74**; both supplied by the supervisor.
>
> Simulation/product design only; no real money; production remains **NOT_AUTHORIZED**. No upstream adoption, backend adoption or production availability claim.
>
> Execution provenance: Codex prepared this document. The requested attribution is retained in the decision metadata; Claude CLI execution, Sonnet execution and fallback attempts were not performed or evidenced.

The decision reserves **100 receipt slots and 200 overlay-entry slots**, each within the corresponding existing absolute ceiling, for servicing and clock maintenance. These are shared reserves, not allocations to individual cases.

Five policy items are **ADOPTED** provisionally. Exact current-command binding and the complete hard-limit inventory are **UNDETERMINED** because the permitted evidence does not contain them. These gaps prevent implementation acceptance, but do not reopen the five adopted policy choices.

## 1. 결정 요약

| Item | Decision | CAP rows | Consumer |
|---|---|---|---|
| `command_budget_classes` | Classification policy fixed below; exhaustive current-command binding **UNDETERMINED** | CAP-01, CAP-04 | Facade command dispatch; overlay consumers |
| `receipt_headroom` | Reserve 100 existing receipt slots; admission stops before that reserve | CAP-01, CAP-04 | Facade receipt accounting; load harness |
| `overlay_entry_headroom` | Reserve 200 existing overlay-entry slots; clock-generated entries count | CAP-01, CAP-04 | Overlay append planning; load harness |
| `compound_command_accounting` | Count all actual records, including generated F04 commands; preflight the whole operation | CAP-01, CAP-04 | `overlay-repayment-posting`; `overlay-recovery-writeoff` |
| `existing_workspace_behavior` | Restore valid workspaces above the admission cutoff; preserve history and remaining servicing capacity | CAP-01, CAP-04 | Local workspace restoration; facade |
| `capacity_refusal_precedence` | Replay precedes growth checks; hard limits precede admission cutoffs | CAP-01, CAP-04 | Command validation and capacity errors |
| `remaining_hard_limits` | Preserve every ceiling; missing current values and bindings **UNDETERMINED** | CAP-01, CAP-04 | Workspace validation; capacity guards |

Consumer names identify intended bindings, not verified code locations or completed implementations.

## 2. KIX 비전 연결

The supplied node description attributes admission/completion budget separation to DEVELOPMENT_PLAN §10. That file was outside the permitted paths and was not opened; this attribution is supervisor context.

The permitted [authority decision](/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md) separates stopping new commitments from preserving existing obligations and their evidence. This decision applies that distinction to local simulation capacity. It does not import chain authority, grant semantics or distributed execution.

The permitted [Protocol README](/workspace/capital-run/kixproto-ro/README.md) distinguishes local mock evidence from operational authorization. The supplied `docs/SEAMS.md` excerpt likewise leaves local stand-ins and durable-transaction binding unadopted. Headroom therefore establishes a finite local counting rule, not durable backend or production service guarantees.

[CAPITAL_DEMO_BOOK.md](CAPITAL_DEMO_BOOK.md) records a historical `MAX_OPERATIONS = 500` and a demonstration script budget of at most 300 operations. Its historical operation count is not sufficient evidence that the current receipt ceiling is 500 or that operations and receipts are identical.

The supplied `CAPITAL_DEFAULT_RECOVERY.md` and `CAPITAL_CLAIM_SLICE_REGISTRY.md` excerpts retain financial-policy references and distinguish simulation policy from upstream adoption. Headroom changes no monetary amount, rate, maturity, loss rule or shared financial cap.

## 3. 항목별 결정

### 3.1 `command_budget_classes`

Classification follows effects, including generated effects, rather than endpoint names. An existing case ID does not make an exposure-increasing command servicing.

| Class | Included behavior | Budget |
|---|---|---|
| `ADMISSION` | New case/claim creation; new offer, commitment, advance or draw; exposure increases on existing cases; batches containing any such effect | Both admission cutoffs and all hard limits |
| `SERVICING` | Existing-obligation repayment, settlement, refund resolution, cancellation/release, margin/default administration, recovery, write-off and closure, only where the current command creates no new exposure | Absolute limits; may consume reserve |
| `MAINTENANCE` | Existing simulation-clock commands and their generated accrual, status or other entries | Absolute limits; shares servicing reserve |
| `READ` | Queries, previews and exports that do not persist workspace changes | Zero receipt/overlay growth; existing access and byte restrictions remain |
| `REPLAY` | Exact recognized retry returning its already stored result | Zero new records |
| `UNCLASSIFIED` | Unknown command or effects that cannot be classified from verified behavior | Refuse before mutation |

`ADMISSION` wins for mixed operations. A generated repayment inherits its parent servicing classification only when the complete operation resolves existing obligations without admitting exposure. Clock advancement cannot authorize an otherwise absent posting or automatic write-off.

This table is exhaustive over policy classes, **not a verified enumeration of current command identifiers**. The pack names `recognize_claim` in the demo note; creating a claim through it is admission. It describes repayment, recovery and clock behavior without supplying complete current command names or dispatch branches.

`CAPITAL_OVERLAY_STATE.md` was requested as a prerequisite but is outside the exact allowed paths. Its ADOPTED entries, current command inventory and capacity rules could not be inspected. Consequently this item's machine status is `UNDETERMINED`; its `target` records the decided classification policy. No fabricated command list is substituted.

### 3.2 `receipt_headroom`

Let `R` be the existing persisted receipt count, `R_max` its unchanged absolute ceiling, and `delta_R` the receipts the complete operation would append.

- Effective reserve: `min(100, R_max)`.
- Admission cutoff: `A_R = max(0, R_max - 100)`.
- Admission requires `R + delta_R <= A_R`.
- Servicing and maintenance require `R + delta_R <= R_max`.

Equality is allowed. All persisted receipt outcomes count, including stored business rejections. A rejection keeps its originating command's class: rejected admission cannot spend servicing reserve.

Existing nonpersisted validation errors remain nonpersisted. Capacity refusals append no receipt; repeatedly refusing an operation must not itself exhaust the reserve. Exact retries add no count.

The historical 500-operation ceiling must be reconciled with current receipt accounting before activation. If the verified receipt ceiling is 500, admission ends at 400 receipts. This conditional example does not redefine the historical operation measure.

### 3.3 `overlay_entry_headroom`

Let `O`, `O_max` and `delta_O` be the corresponding overlay-entry quantities.

- Effective reserve: `min(200, O_max)`.
- Admission cutoff: `A_O = max(0, O_max - 200)`.
- Admission requires `O + delta_O <= A_O`.
- Servicing and maintenance require `O + delta_O <= O_max`.

Every persisted generated entry counts individually. A clock command producing `k` entries consumes `k` overlay slots, plus whatever receipts it actually persists. A servicing operation that produces no overlay entry consumes zero overlay slots.

Receipts and overlays are independent constraints. Spare receipts cannot compensate for exhausted overlays, bytes or per-case capacity. Maintenance receives no separate quota and can exhaust the shared reserve. No new journal, counter file or storage format is authorized.

### 3.4 `compound_command_accounting`

Budget the complete persisted effect set before mutation: parent receipts, generated F04 repayment receipts, overlay postings and clock fan-out. Count each actual persisted record once; internal calls without records do not create artificial count charges.

Use a bounded dry run under the existing local mutation discipline. Publish the complete operation or none of it. Existing rejection-record behavior remains subject to capacity checks. If the existing workspace mechanism cannot prevent a partial compound write, refuse that compound mutation; this decision does not authorize a storage redesign.

**Principal-coupled repayment example.** Assume a verified operation produces one parent receipt, one generated F04 receipt and one overlay entry: `(delta_R, delta_O) = (2, 1)`. With `R_max = 500`, `R = 498` and one overlay slot remaining, it may finish exactly at both hard ceilings if all other checks pass. At `R = 499`, refuse the entire operation. Do not post the overlay portion while losing the generated principal repayment. These record multiplicities are illustrative until implementation binding verifies them.

### 3.5 `existing_workspace_behavior`

Admission cutoffs constrain new admission, not restoration of historical records. Restore any workspace accepted by existing schema, integrity and hard-limit checks even when its counts exceed either new admission cutoff.

Do not replay historical records through the new admission gate, delete receipts, rewrite outcomes, reset counters or create replacement IDs. Counts derive from the existing stored representation.

**Restoration example.** If the verified receipt ceiling is 500, a valid workspace containing 450 receipts restores unchanged. Admission is blocked at the proposed 400 cutoff. At most 50 further receipt slots remain for servicing/maintenance, subject to every other ceiling. Restoration does not recreate a 100-slot reserve.

A workspace already above an absolute hard limit receives existing invalid/oversized-workspace handling. Preserve its source; this decision supplies no repair, bypass or cleanup authority.

### 3.6 `capacity_refusal_precedence`

Apply this order:

1. Existing envelope, access and identity checks.
2. Existing idempotency lookup: return an exact stored result; reject identity/content conflicts under existing rules.
3. Classify the complete requested operation.
4. Bounded dry run using existing business-validation precedence; determine success or the existing rejection outcome and its exact persistence footprint.
5. Check hard limits: per-case, then bytes, then receipts, then overlays. Within a category, preserve existing error precedence.
6. For admission, check receipt cutoff, then overlay cutoff.
7. Commit through the existing local workspace mechanism.

Existing input-size checks remain at their current earlier ingress position. If a dry run cannot safely establish a bounded footprint, refuse before mutation.

For a business rejection that historically requires persistence, return and persist that outcome only when its receipt fits the applicable budgets. Otherwise return `SIMULATION_CAPACITY` without appending. Nonpersisted business errors need no append capacity. Capacity diagnostics should identify the failed dimension and admission-versus-hard boundary without changing financial rejection meanings.

**Admission boundary.** With verified `R_max = 500`, an admission adding one receipt can move `399 → 400`; the next cannot move `400 → 401`. Separately, an admission needing two overlay entries fails at `O = A_O - 1`, even with spare receipts.

**Replay at full capacity.** At `R = R_max` and `O = O_max`, an exact recognized retry returns the original stored outcome without appending. It does not rerun F04 or regenerate clock entries. A fresh operation ID is a new attempt and receives ordinary capacity checks.

### 3.7 `remaining_hard_limits`

All absolute constraints remain conjunctive and unchanged:

| Constraint | Evidence and binding |
|---|---|
| Receipt ceiling `R_max` | Current value and operation-to-receipt mapping **UNDETERMINED**; historical operation ceiling 500 is documented |
| Overlay ceiling `O_max` | Current absolute value **UNDETERMINED** |
| Byte ceilings | Every existing request, record and workspace limit remains binding; exact values **UNDETERMINED** |
| Per-case ceilings | Every existing per-case limit remains binding; exact values **UNDETERMINED** |

Resolve these from their existing authoritative consumers during implementation; do not supply guessed constants or default to unlimited capacity.

This decision supersedes only a uniform admission/servicing count gate, wherever verified, by adding lower admission cutoffs. It does not supersede the underlying hard ceilings. Exact affected entries in the unread overlay-state note remain unbound. The demo's ≤300-operation script target remains unchanged.

There is **no eviction, automatic cleanup, retention deletion, financial-cap change or unlimited completion guarantee**. The reserve guarantees only exclusion of new admission from a bounded count band once properly bound. Bytes, per-case limits, prior servicing and clock work can exhaust capacity earlier. No minimum number of completed cases is promised.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "servicing-headroom-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-11-04",
  "provisional": true,
  "entries": {
    "command_budget_classes": {
      "status": "UNDETERMINED",
      "value": null,
      "target": {
        "classes": ["ADMISSION", "SERVICING", "MAINTENANCE", "READ", "REPLAY", "UNCLASSIFIED"],
        "admission": "Any new case, commitment or exposure increase",
        "servicing": "Resolve existing obligations without new exposure",
        "maintenance": "Existing clock actions and generated entries",
        "read_and_exact_replay": "Zero new persistent records",
        "mixed": "ADMISSION wins",
        "unclassified": "Refuse before mutation",
        "current_command_inventory": null
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Current command inventory and prerequisite overlay-state entries are absent from permitted evidence.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "receipt_headroom": {
      "status": "ADOPTED",
      "value": {
        "reserve_count": 100,
        "effective_reserve": "min(R_max,100)",
        "admission_postcondition": "R + delta_R <= max(0,R_max-100)",
        "servicing_and_maintenance_postcondition": "R + delta_R <= R_max",
        "unit": "Every newly persisted receipt, including stored rejections",
        "historical_operation_ceiling": 500,
        "current_receipt_ceiling_binding": "UNDETERMINED"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Protect 100 receipt slots within the unchanged absolute ceiling.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "overlay_entry_headroom": {
      "status": "ADOPTED",
      "value": {
        "reserve_count": 200,
        "effective_reserve": "min(O_max,200)",
        "admission_postcondition": "O + delta_O <= max(0,O_max-200)",
        "servicing_and_maintenance_postcondition": "O + delta_O <= O_max",
        "clock_generated_entries": "Count each persisted entry",
        "current_overlay_ceiling_binding": "UNDETERMINED"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Protect 200 overlay slots without raising absolute or per-case limits.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "compound_command_accounting": {
      "status": "ADOPTED",
      "value": {
        "accounting": "Count every actual persisted record across the complete operation once",
        "generated_f04_receipts": "Included",
        "clock_generated_entries": "Included",
        "persisted_rejections": "Consume originating class budget",
        "capacity_refusals": "Append nothing",
        "preflight": "Bounded complete effect set before mutation",
        "commit": "All or none using existing local mechanisms",
        "unsupported_atomicity": "Refuse compound mutation"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Generated writes cannot bypass capacity or leave partial principal postings.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "existing_workspace_behavior": {
      "status": "ADOPTED",
      "value": {
        "above_admission_cutoff": "Restore under existing validity and hard limits; block admission",
        "at_hard_count_limit": "Allow existing reads and exact replay; refuse growth",
        "above_hard_limit": "Preserve source and existing refusal behavior",
        "counter_basis": "Existing persisted records",
        "reset_eviction_cleanup": false,
        "new_storage_format": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Admission cutoffs do not invalidate historical workspaces or replenish consumed capacity.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "capacity_refusal_precedence": {
      "status": "ADOPTED",
      "value": {
        "order": [
          "EXISTING_ENVELOPE_ACCESS_AND_IDENTITY",
          "EXACT_REPLAY_OR_IDEMPOTENCY_CONFLICT",
          "COMMAND_CLASSIFICATION",
          "BOUNDED_DRY_RUN_WITH_EXISTING_DOMAIN_PRECEDENCE",
          "HARD_PER_CASE_THEN_BYTES_THEN_RECEIPTS_THEN_OVERLAY",
          "ADMISSION_RECEIPTS_THEN_OVERLAY",
          "EXISTING_LOCAL_COMMIT"
        ],
        "existing_ingress_size_checks": "Remain earlier",
        "persisted_domain_rejection": "Requires applicable append capacity",
        "capacity_code": "SIMULATION_CAPACITY",
        "capacity_refusal_appends": 0
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Preserve idempotency and domain semantics while making capacity precedence deterministic.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "remaining_hard_limits": {
      "status": "UNDETERMINED",
      "value": null,
      "target": {
        "receipt_hard_max": "Existing R_max; current mapping unverified",
        "overlay_hard_max": "Existing O_max",
        "byte_hard_max": "Every existing request, record and workspace ceiling",
        "per_case_hard_max": "Every existing per-case ceiling",
        "financial_limits": "Unchanged original policy references",
        "raise_limits": false,
        "eviction": false,
        "automatic_cleanup": false,
        "unlimited_completion": false,
        "production": "NOT_AUTHORIZED"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "The permitted pack omits current absolute overlay, byte and per-case values and receipt-count binding.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| Requirement | Result |
|---|---|
| Seven decision entries and concrete reserve policy | Present; five ADOPTED, two explicitly UNDETERMINED |
| Exhaustive current-command classification | **Unmet:** inventory omitted from permitted evidence |
| Rejections, generated F04 commands and clock accounting | Specified in §3.1–3.4 |
| Four requested boundary examples | Specified in §3.4–3.6; numeric receipt examples conditional |
| Absolute ceilings and finite guarantees | Preservation explicit; missing exact values remain UNDETERMINED |
| Earlier rules and consumer bindings | Policy impact identified; exact overlay-state binding unresolved |
| Decision-ledger, decision-binding and documentation checks | **NOT RUN:** checker paths outside permitted read scope; output file not written |

Acceptance is therefore **incomplete**, not falsely reported as passing.

## 6. Open risks

Command aliases or generated effects may change classification and record multiplicity. The historical operation ceiling may use a different measure from receipts. Byte/per-case exhaustion and clock fan-out may prevent completion despite remaining reserved counts. Existing compound persistence may lack the required all-or-none behavior.

## 7. 후속 작업

The supervisor writes this document. The implementation consumer must bind the omitted command inventory, prerequisite overlay-state entries and exact hard ceilings before enabling the policy. Adopted reserve values require no renewed product decision.

Then verify admission boundaries, stored rejections, generated repayments, clock fan-out, full-capacity replay, restoration and unchanged hard-limit refusal. Run the repository's decision-ledger validation, `python3 scripts/decision_bindings.py --check` and `python3 scripts/docs_surface.py --check`. No repository checks, upstream receipts or implementation completion are claimed by this document.
