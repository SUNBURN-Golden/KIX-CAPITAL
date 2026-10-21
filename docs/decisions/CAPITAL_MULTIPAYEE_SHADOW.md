# CAPITAL_MULTIPAYEE_SHADOW — Bounded multi-payee inputs for class-priority allocation

> **PROVISIONAL PRODUCT DECISION**
>
> Requested decision attribution: **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**.
>
> Date: **2026-10-22** · Capital main: **`cde0bc7`** · kix-protocol: **`93cec6a`**. These bases are supervisor-supplied.
>
> Execution provenance: revised by **Codex** from the supplied pack. No Claude CLI execution, Sonnet attempts or Fable fallback is claimed.
>
> Simulation/product design only; no real money. Production remains **`NOT_AUTHORIZED`** and every shadow effect remains **`SHADOW_NOT_APPLIED`**. This decision authorizes no persistent settlement records, UC1–UC4 implementation or upstream contract changes.

Node: `multipayee-shadow-input-decision`. Dependencies: `settlement-policy-decision`, `shadow-policy-decision`, `shadow-refund-resale`.

The inherited allocation and shadow policies remain authoritative. Their adoption is supplied by the supervisor; their originals were not opened because they are outside the exact-path reading scope. This decision defines local inputs without reopening financial priorities.

## 1. 결정 요약

All six items are **ADOPTED as provisional Capital-local product decisions**. This does not imply upstream adoption or completed implementation.

| Item | Decision | CAP rows | Consumer |
|---|---|---|---|
| `synthetic_payee_identity` | Unique ASCII fixture labels; one row per payee per snapshot | CAP-02, CAP-05 | Multi-payee input adapter |
| `class_mapping_and_unknowns` | Explicit inherited membership; reject unknown classes | CAP-02, CAP-05 | Policy loader and allocator |
| `single_cut_allocation_inputs` | One frozen cash amount and remaining-obligation vector | CAP-02, CAP-05 | `policy-simulator`, `shadow-refund-resale` |
| `within_class_caps_and_rounding` | Preserve priority, largest remainder and inherited tie comparator; cap at remaining obligations | CAP-02, CAP-05 | Shadow allocator |
| `fixture_capacity_bounds` | At most 64 rows and 32,768 bytes; exact bounded integer amounts | CAP-08, CAP-20 | Input validation |
| `shadow_comparison_labels` | Preserve shadow envelope; separate diagnostics; compare compatible snapshots | CAP-09, CAP-20 | Comparison presentation |

## 2. KIX 비전 연결

The supplied [Capital requirements excerpt](../CAPITAL_REQUIREMENTS_KO.md) separates local development authority from operational authorization. The [seams excerpt](../SEAMS.md) separates local verification from upstream adoption and semantic conformance. Bounded multi-payee inputs extend reproducible synthetic experiments within these boundaries.

The [claim-slice registry excerpt](CAPITAL_CLAIM_SLICE_REGISTRY.md) leaves slice uniqueness, shared caps and borrowing-base protection with that decision. A synthetic payee row creates neither a claim slice nor participation eligibility. The [accounts, tax and legal excerpt](CAPITAL_ACCOUNTS_TAX_LEGAL.md) preserves professional-review boundaries: fixture identity establishes no legal payee identity.

These connections rely only on supplied excerpts. No upstream receipt or independent source verification is claimed.

## 3. 항목별 결정

### 3.1 `synthetic_payee_identity`

Adopt input version `CAPITAL-MULTIPAYEE-SHADOW-INPUT-V1`.

Each payee row contains exactly `payee_label`, `class_id` and `shadow_remaining_obligation_krw`. Labels match `^fx-[a-z0-9][a-z0-9_-]{0,60}$`: 4–64 ASCII bytes. Equality is exact, without trimming, normalization, case folding or aliases.

Labels must be unique across the whole snapshot, including different classes and zero-obligation rows. Duplicate labels reject the entire input; they are never merged. A label belongs to exactly one class.

Identity is `(fixture_id, snapshot_id, payee_label)`. Both enclosing identifiers use the same grammar. Reuse in another snapshot establishes no continuing creditor identity.

Canonical presentation order is ascending ASCII label. Neither presentation nor input order overrides the inherited allocation tie comparator. Real names, bank details and legal identifiers are outside this schema.

### 3.2 `class_mapping_and_unknowns`

Require explicit `class_id` on every row. Load class vocabulary, priority and the tie comparator from adopted `CAPITAL-ALLOC-V1`; never infer membership from labels.

Unknown classes reject the whole input with `adapter_outcome: INVALID_INPUT` and reason `UNKNOWN_CLASS`. Missing, wrongly typed or syntactically invalid classes use `INVALID_CLASS`. Validate zero-obligation rows too. There is no fallback class, silent omission or partial allocation.

Freeze allocation-policy and shadow-policy source digests before computation. Missing, unreadable or unresolved required policy yields `adapter_outcome: NOT_BOUND` and null monetary results. Adopted branches require no further policy decision; inherited undecided or deferred branches retain their existing not-bound behavior.

The pack does not establish the complete class vocabulary or concrete tie comparator. Those remain inherited dependencies, not replacement values invented here.

### 3.3 `single_cut_allocation_inputs`

The input object contains exactly:

- `schema`: `CAPITAL-MULTIPAYEE-SHADOW-INPUT-V1`;
- `fixture_id` and `snapshot_id`;
- `shadow_cash_krw`: available synthetic cash;
- `payees`: the complete remaining-obligation vector.

All monetary keys use `shadow_`, including inputs, echoed values, outputs and comparison deltas. Reject unknown fields and duplicate JSON object keys.

Amounts are nonnegative JSON integers. Reject booleans, strings, fractions and exponent-form numeric encodings. Remaining obligations are fixture-author assumptions immediately before this calculation, not verified debt evidence. Do not derive them from face amounts, historical payments, fees, refunds or prior shadow results.

Freeze the complete payload and policy sources once. Do not reread mutable state between classes or comparison runs. Identifiers alone do not establish input equivalence.

Successful results contain per-row `payee_label`, `class_id`, `shadow_allocation_krw` and `shadow_remaining_after_krw`, plus `shadow_total_allocated_krw` and `shadow_unallocated_cash_krw`.

Keep zero-obligation rows visible. An empty payee array is valid and leaves all cash unallocated.

There is no history lookup, settlement write, replay ledger or automatic carry-forward. Recomputing repeats a hypothetical calculation. Cumulative late-cash handling, participation, claim slices and refund/resale lifecycle effects remain with their existing nodes.

### 3.4 `within_class_caps_and_rounding`

Preserve `CAPITAL-ALLOC-V1` class priority and largest-remainder rules. Introduce no financial percentage, fee, entitlement or underwriting limit.

Process classes in inherited priority order. For a class, let remaining cash be `C`, obligations be `r_i`, and their sum be `R`. Set class budget `B = min(C, R)`.

If `R = 0`, allocate zero without division. Otherwise compute:

- Base allocation `q_i = floor(B × r_i / R)`.
- Remainder numerator `m_i = (B × r_i) mod R`.
- Distribute the remaining `B − Σq_i` units by descending `m_i`, resolving equal remainders with the inherited comparator.

Synthetic labels supply identity only where that comparator accepts it. If information needed to resolve a tie is unavailable, return `NOT_BOUND`; never substitute alphabetical or input order.

Use exact integer arithmetic, including intermediate products. No payee receives more than its remaining obligation. Lower-priority classes receive cash only after higher-priority remaining obligations are satisfied. Surplus stays unallocated.

For allocations `a_i`, preserve:

`0 ≤ a_i ≤ r_i`

`remaining_after_i = r_i − a_i`

`Σa_i + unallocated = cash`

These are mathematical symbols, not additional output keys.

**Worked examples.** Amounts are synthetic KRW integers. `P` represents the inherited protected class; `L` represents an inherited lower-priority class. P1–P3 and L1 are table aliases for valid fixture labels. In the tie example, P1–P3 are ordered by the inherited comparator.

| Case | Remaining obligations | Cash | Allocations | Remaining after | Unallocated |
|---|---|---:|---|---|---:|
| Cash exhausted inside protected class | P1=5, P2=3; L1=9 | 5 | P1=3, P2=2, L1=0 | P1=2, P2=1, L1=9 | 0 |
| Equal remainders | P1=1, P2=1, P3=1 | 2 | P1=1, P2=1, P3=0 | P1=0, P2=0, P3=1 | 0 |
| Zero cash | P1=5, P2=3 | 0 | P1=0, P2=0 | P1=5, P2=3 | 0 |
| Fully satisfied obligations | P1=0, P2=0 | 7 | P1=0, P2=0 | P1=0, P2=0 | 7 |
| Cash exceeds obligations | P1=2, P2=1; L1=4 | 10 | P1=2, P2=1, L1=4 | P1=0, P2=0, L1=0 | 3 |

In the first example, bases are 3 and 1 and remainder numerators are 1 and 7; P2 receives the extra unit. In the tie example, all bases are zero and all remainder numerators are 2; the first two inherited ranks receive one unit.

These examples specify arithmetic. They are not executed fixtures or evidence of validated concrete policy bindings.

### 3.5 `fixture_capacity_bounds`

Adopt inclusive local bounds:

| Dimension | Bound |
|---|---:|
| UTF-8 payload | 32,768 bytes |
| Payee rows | 0–64 |
| Fixture, snapshot and payee identifiers | 4–64 ASCII bytes |
| Class identifier | 1–64 ASCII bytes and inherited membership |
| Cash, each obligation and total obligations | Each 0–1,000,000,000,000 KRW |

These limits bound synthetic inputs and computation, not lending or economic rights.

Check payload size before parsing. Validate the entire schema and all bounds before allocating. A capacity violation yields `adapter_outcome: SIMULATION_CAPACITY`, identifies the exceeded dimension and returns null monetary results. Never truncate or divide an oversized snapshot into separately allocated batches.

Intermediate products can reach `10^24`. Use arbitrary-precision integers or an equally exact method.

### 3.6 `shadow_comparison_labels`

Every adapter outcome preserves `status: SHADOW_NOT_APPLIED`. Successful arithmetic applies no effect. Preserve labels `SIMULATED`, `SYNTHETIC_FIXTURE_PROFILE` and `PROVISIONAL_PRODUCT_DECISION`, with `funds_executed:false`, `effects_applied:false` and `production:NOT_AUTHORIZED`.

Diagnostics belong exclusively to `adapter_outcome`:

| `adapter_outcome` | Shadow `status` | Monetary payload |
|---|---|---|
| `COMPUTED` | `SHADOW_NOT_APPLIED` | Computed amounts |
| `INVALID_INPUT` | `SHADOW_NOT_APPLIED` | Null; validation reason |
| `SIMULATION_CAPACITY` | `SHADOW_NOT_APPLIED` | Null; exceeded dimension |
| `NOT_BOUND` | `SHADOW_NOT_APPLIED` | Null; unresolved policy dependency |

No diagnostic extends the inherited shadow status set. Failed calculations never appear as successful zero allocations.

Use separate comparison metadata `comparison_state: COMPARABLE` or `NOT_COMPARABLE`.

Numeric comparison requires two `COMPUTED` results with identical frozen cash, label set, class membership, remaining obligations and KRW unit. Record each side’s explicit algorithm/policy identity and source digest. Deliberately different policies may be compared; differences do not establish error or financial superiority.

Report candidate minus baseline with `shadow_allocation_delta_krw`, `shadow_remaining_after_delta_krw`, `shadow_total_allocated_delta_krw` and `shadow_unallocated_cash_delta_krw`. Equality applies only to this snapshot.

Otherwise return `NOT_COMPARABLE`, a reason and null deltas. Never fabricate rows to extend a pinned two-payee baseline. Comparison establishes neither executed settlement nor upstream adoption or semantic conformance.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "multipayee-shadow-input-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-10-22",
  "provisional": true,
  "entries": {
    "synthetic_payee_identity": {
      "status": "ADOPTED",
      "value": {
        "input_version": "CAPITAL-MULTIPAYEE-SHADOW-INPUT-V1",
        "label_pattern": "^fx-[a-z0-9][a-z0-9_-]{0,60}$",
        "identity_scope": ["fixture_id", "snapshot_id", "payee_label"],
        "duplicate_labels": "REJECT_WHOLE_INPUT",
        "rows_per_payee": 1,
        "legal_identity": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-02", "CAP-05"],
      "rationale": "Bound synthetic identity and prevent duplicate obligations without asserting legal identity.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "class_mapping_and_unknowns": {
      "status": "ADOPTED",
      "value": {
        "membership": "EXPLICIT_PER_ROW",
        "vocabulary_and_priority_source": "CAPITAL-ALLOC-V1",
        "unknown_class": "REJECT_WHOLE_INPUT",
        "default_class": null,
        "missing_policy_adapter_outcome": "NOT_BOUND",
        "source_binding": "FREEZE_LOADED_POLICY_DIGESTS"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-02", "CAP-05"],
      "rationale": "Apply adopted classes without fallback or invented financial priorities.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "single_cut_allocation_inputs": {
      "status": "ADOPTED",
      "value": {
        "fields": ["schema", "fixture_id", "snapshot_id", "shadow_cash_krw", "payees"],
        "row_fields": ["payee_label", "class_id", "shadow_remaining_obligation_krw"],
        "amount_type": "NONNEGATIVE_JSON_INTEGER",
        "amount_key_prefix": "shadow_",
        "snapshot": "ONE_FROZEN_PAYLOAD_AND_POLICY_SET",
        "unknown_fields_and_duplicate_keys": "REJECT",
        "empty_payees": "VALID_ALL_CASH_UNALLOCATED",
        "history_lookup": false,
        "persistent_effects": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-02", "CAP-05"],
      "rationale": "Make one frozen calculation explicit and preserve shadow monetary naming.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "within_class_caps_and_rounding": {
      "status": "ADOPTED",
      "value": {
        "policy": "CAPITAL-ALLOC-V1",
        "class_budget": "MIN_REMAINING_CASH_AND_CLASS_OBLIGATION",
        "weight": "REMAINING_OBLIGATION",
        "rounding": "INHERIT_LARGEST_REMAINDER",
        "equal_remainders": "INHERIT_POLICY_COMPARATOR",
        "payee_cap": "REMAINING_OBLIGATION",
        "arithmetic": "EXACT_INTEGER",
        "surplus_output": "shadow_unallocated_cash_krw"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-02", "CAP-05"],
      "rationale": "Preserve priority and rounding while preventing overpayment and invented residual entitlements.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "fixture_capacity_bounds": {
      "status": "ADOPTED",
      "value": {
        "max_payload_bytes": 32768,
        "max_payee_rows": 64,
        "max_identifier_bytes": 64,
        "max_class_identifier_bytes": 64,
        "shadow_cash_limit_krw": 1000000000000,
        "shadow_row_obligation_limit_krw": 1000000000000,
        "shadow_total_obligation_limit_krw": 1000000000000,
        "overflow_adapter_outcome": "SIMULATION_CAPACITY",
        "financial_limit": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-08", "CAP-20"],
      "rationale": "Bound parsing and exact computation without changing financial terms.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "shadow_comparison_labels": {
      "status": "ADOPTED",
      "value": {
        "shadow_result_status": "SHADOW_NOT_APPLIED",
        "adapter_outcome_to_shadow_status": {
          "COMPUTED": "SHADOW_NOT_APPLIED",
          "INVALID_INPUT": "SHADOW_NOT_APPLIED",
          "SIMULATION_CAPACITY": "SHADOW_NOT_APPLIED",
          "NOT_BOUND": "SHADOW_NOT_APPLIED"
        },
        "labels": ["SIMULATED", "SYNTHETIC_FIXTURE_PROFILE", "PROVISIONAL_PRODUCT_DECISION"],
        "comparison_requires": "TWO_COMPUTED_RESULTS_WITH_IDENTICAL_FROZEN_INPUTS_AND_EXPLICIT_POLICY_IDENTITIES",
        "comparison_states": ["COMPARABLE", "NOT_COMPARABLE"],
        "delta_direction": "CANDIDATE_MINUS_BASELINE",
        "amount_key_prefix": "shadow_",
        "failed_amounts_and_incompatible_deltas": null,
        "funds_executed": false,
        "effects_applied": false,
        "production": "NOT_AUTHORIZED"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-09", "CAP-20"],
      "rationale": "Keep diagnostics outside inherited statuses and reject fabricated comparison compatibility.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| Acceptance | Evidence / status |
|---|---|
| Exactly one decision block with six items | §4 |
| Unique labels, explicit classes and bounded sizes | §§3.1–3.2, 3.5 |
| Preserve priority and largest remainder; five examples | §3.4 |
| One frozen snapshot; existing-node boundaries | §3.3 |
| Shadow monetary keys and inherited status envelope | §§3.3, 3.6 |
| Production unauthorized; effects unapplied | Banner and §3.6 |
| Decision-ledger validation | **UNDETERMINED:** no validator execution or independent validation receipt available |
| Actual documentation-index reference | **UNSATISFIED:** no authorized index modification is included |

**Blocking review disposition:** The index finding is valid. The final revision scope permits edits only to this note, `tests/decision_bindings.json` and `tests/vectors/pack/`, and requires the decision document as the sole deliverable. It excludes `docs/CAP_COVERAGE.md`. Consequently, this response cannot make the required actual index edit. A link or insertion instruction inside this note cannot satisfy that acceptance criterion. Repository acceptance remains blocked; this document does not claim otherwise.

## 6. Open risks

Concrete inherited class vocabulary and label-to-tie-rank bindings remain unverified from the pack. Consumers must resolve adopted sources before affected calculations.

Remaining obligations are synthetic assertions, not evidence of completeness or legal validity. Legal, tax and accounting interpretations remain working assumptions pending professional review. The documentation-index and validator requirements remain outstanding independently of the six product decisions.

## 7. 후속 작업

Repository integration requires an actual reference from `docs/CAP_COVERAGE.md` to `decisions/CAPITAL_MULTIPAYEE_SHADOW.md`, followed by the existing decision-ledger validator and `python3 scripts/docs_surface.py --check`. These are outstanding integration requirements, not completed actions or substitutes for the blocking index edit.

The implementation consumer must bind inherited policies and verify permutation independence, equal-remainder ties, duplicate and unknown-class rejection, numeric and capacity boundaries, conservation, shadow-envelope preservation and incompatible comparisons. New vectors require maintained surface registrations and README needles.

Cumulative late cash, participation, claim slices, UC1–UC4 and upstream changes remain with their existing nodes.
