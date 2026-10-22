# CAPITAL_MULTIPAYEE_SHADOW — Bounded multi-payee inputs for class-priority allocation

> **PROVISIONAL PRODUCT DECISION**
>
> Requested decision attribution: **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**.
>
> **Date: 2026-10-22 · Capital main: `cde0bc7` · kix-protocol: `9eb6b5f`** — supervisor-supplied bases.
>
> Execution provenance: revised by **Codex** using the supplied pack. No Claude CLI execution, Sonnet attempts or Fable fallback is claimed.
>
> Simulation/product design only; no real money. Production remains **`NOT_AUTHORIZED`** and every shadow effect remains **`SHADOW_NOT_APPLIED`**. No persistent settlement records, UC1–UC4 implementation or upstream contract changes are authorized.

Node: `multipayee-shadow-input-decision`. Dependencies: `settlement-policy-decision`, `shadow-policy-decision`, `shadow-refund-resale`.

The supervisor identifies the inherited allocation and shadow policies as adopted provisional policy. Their originals are outside the exact-path reading scope and were not opened. This note defines bounded local inputs without replacing their priorities, vocabulary or tie comparator.

## 1. 결정 요약

All six items are **ADOPTED as provisional Capital-local product decisions**. Adoption here establishes neither implementation completion nor upstream adoption.

| Item | Decision | CAP rows | Consumer |
|---|---|---|---|
| `synthetic_payee_identity` | Unique synthetic ASCII labels; one row per payee per snapshot | CAP-02, CAP-05 | Multi-payee input adapter |
| `class_mapping_and_unknowns` | Explicit inherited class membership; reject unknown classes | CAP-02, CAP-05 | Policy loader and allocator |
| `single_cut_allocation_inputs` | One frozen cash amount and remaining-obligation vector | CAP-02, CAP-05 | `policy-simulator`, `shadow-refund-resale` |
| `within_class_caps_and_rounding` | Inherited class priority and largest remainder; remaining-obligation caps | CAP-02, CAP-05 | Shadow allocator |
| `fixture_capacity_bounds` | Maximum 64 rows, 32,768 bytes and bounded integer amounts | CAP-08, CAP-20 | Input validation |
| `shadow_comparison_labels` | Unapplied shadow envelope; compatible-snapshot comparisons | CAP-09, CAP-20 | Comparison presentation |

## 2. KIX 비전 연결

The supplied [Capital requirements excerpt](../CAPITAL_REQUIREMENTS_KO.md) distinguishes local development authority from operational authorization. The [seams excerpt](../SEAMS.md) distinguishes local verification from upstream adoption and semantic conformance. This contract extends reproducible synthetic allocation experiments within those boundaries.

The [claim-slice registry excerpt](CAPITAL_CLAIM_SLICE_REGISTRY.md) assigns slice uniqueness, shared caps and borrowing-base protection to its existing decision. A payee row creates neither a claim slice nor participation eligibility. The [accounts, tax and legal excerpt](CAPITAL_ACCOUNTS_TAX_LEGAL.md) preserves professional-review boundaries; fixture identity establishes no legal payee identity.

These connections use supplied excerpts only. Historical validation in the [validation excerpt](../VALIDATION.md) is not evidence that this revision passed checks. No upstream receipt is asserted.

## 3. 항목별 결정

### 3.1 `synthetic_payee_identity`

Adopt input version `CAPITAL-MULTIPAYEE-SHADOW-INPUT-V1`.

Every row contains exactly `payee_label`, `class_id` and `shadow_remaining_obligation_krw`. Labels match `^fx-[a-z0-9][a-z0-9_-]{0,60}$`, giving 4–64 ASCII bytes. Equality is exact: no trimming, normalization, aliases or case folding.

Labels must be unique throughout a snapshot, including across classes and zero-obligation rows. Duplicate labels reject the whole input; never merge them. Each label belongs to exactly one class.

Identity is `(fixture_id, snapshot_id, payee_label)`. Both enclosing identifiers follow the same grammar. Reuse across snapshots establishes no continuing creditor identity.

Present rows in ascending ASCII label order. Presentation and input order never override the inherited allocation tie comparator. Real names, bank details and legal identifiers are outside this schema.

### 3.2 `class_mapping_and_unknowns`

Require explicit `class_id` for every row. Load class vocabulary, priority and tie comparator from adopted `CAPITAL-ALLOC-V1`; do not infer membership from labels or copy unavailable policy literals.

An otherwise valid but unknown class rejects the whole input with `adapter_outcome: INVALID_INPUT` and reason `UNKNOWN_CLASS`. Missing or wrongly typed classes use `INVALID_CLASS`; capacity violations follow §3.5. Validate zero-obligation rows too. No fallback class, silent omission or partial allocation is permitted.

Freeze allocation-policy and shadow-policy source digests before calculation. Missing, unreadable or unresolved required policy produces `adapter_outcome: NOT_BOUND` and null monetary results. An adopted branch needs no further policy decision. Inherited undecided or deferred branches retain their prescribed not-bound behavior.

The pack does not establish concrete class vocabulary or the tie comparator. Those remain inherited dependencies, not newly undecided financial priorities.

### 3.3 `single_cut_allocation_inputs`

The input object contains exactly:

- `schema`: `CAPITAL-MULTIPAYEE-SHADOW-INPUT-V1`;
- `fixture_id` and `snapshot_id`;
- `shadow_cash_krw`: available synthetic cash;
- `payees`: the complete remaining-obligation vector.

Reject unknown fields and duplicate JSON object keys. All monetary keys, including echoed inputs, results and comparison deltas, begin with `shadow_`.

Amounts are nonnegative JSON integers. Reject booleans, strings, fractions and exponent-form numeric encodings. Remaining obligations are fixture-author assumptions immediately before this calculation, not verified debt evidence. Do not derive them from face amounts, historical payments, fees, refunds or earlier shadow results.

Freeze the complete payload and policy sources once. Do not reread mutable state between classes or comparison runs. Identifiers alone do not establish input equivalence.

Successful results contain per-row `payee_label`, `class_id`, `shadow_allocation_krw` and `shadow_remaining_after_krw`, plus `shadow_total_allocated_krw` and `shadow_unallocated_cash_krw`. Keep zero-obligation rows visible. An empty array is valid and leaves all cash unallocated.

There is no history lookup, settlement write, replay ledger or automatic carry-forward. Recalculation repeats a hypothetical computation. Cumulative late-cash handling, participation, claim slices and refund/resale lifecycle effects remain with their existing nodes.

### 3.4 `within_class_caps_and_rounding`

Preserve `CAPITAL-ALLOC-V1` class priority and largest-remainder rules. Introduce no financial percentage, fee, entitlement or underwriting limit.

Process classes in inherited priority order. For each class, let remaining cash be `C`, obligations be `r_i`, their sum be `R`, and class budget be `B = min(C, R)`.

When `R = 0`, allocate zero without division. Otherwise:

- Base allocation: `q_i = floor(B × r_i / R)`.
- Remainder numerator: `m_i = (B × r_i) mod R`.
- Distribute `B − Σq_i` additional units by descending `m_i`, breaking equal remainders with the inherited comparator.

Synthetic labels provide identity only where that comparator accepts it. If information needed to resolve an actual tie is unavailable, return `NOT_BOUND`; never substitute alphabetical or input order.

Use exact integer arithmetic throughout. No allocation exceeds its remaining obligation. Lower-priority classes receive cash only after higher-priority remaining obligations are satisfied. Surplus remains unallocated.

For allocations `a_i`, preserve:

`0 ≤ a_i ≤ r_i`

`remaining_after_i = r_i − a_i`

`Σa_i + unallocated = cash`

These are mathematical symbols, not additional output keys.

**Worked examples.** Amounts are synthetic KRW integers. `P` denotes an inherited protected class and `L` an inherited lower-priority class. P1–P3 and L1 are table aliases for valid fixture labels. For equal remainders, assume the inherited comparator ranks P1 before P2 before P3.

| Case | Remaining obligations | Cash | Allocations | Remaining after | Unallocated |
|---|---|---:|---|---|---:|
| Cash exhausted inside protected class | P1=5, P2=3; L1=9 | 5 | P1=3, P2=2, L1=0 | P1=2, P2=1, L1=9 | 0 |
| Equal remainders | P1=1, P2=1, P3=1 | 2 | P1=1, P2=1, P3=0 | P1=0, P2=0, P3=1 | 0 |
| Zero cash | P1=5, P2=3 | 0 | P1=0, P2=0 | P1=5, P2=3 | 0 |
| Fully satisfied obligations | P1=0, P2=0 | 7 | P1=0, P2=0 | P1=0, P2=0 | 7 |
| Cash exceeds obligations | P1=2, P2=1; L1=4 | 10 | P1=2, P2=1, L1=4 | P1=0, P2=0, L1=0 | 3 |

In the first example, bases are 3 and 1, with remainder numerators 1 and 7; P2 receives the extra unit. In the tie example, all bases are zero and remainder numerators are 2; the first two inherited ranks receive one unit.

These examples establish arithmetic expectations, not executed fixtures or verified concrete policy bindings.

### 3.5 `fixture_capacity_bounds`

Adopt inclusive local limits:

| Dimension | Bound |
|---|---:|
| UTF-8 payload | 32,768 bytes |
| Payee rows | 0–64 |
| Fixture, snapshot and payee identifiers | 4–64 ASCII bytes |
| Class identifier | 1–64 ASCII bytes, with inherited membership |
| Cash, each obligation and total obligations | Each 0–1,000,000,000,000 KRW |

These are synthetic computation limits, not financial terms.

Check payload size before parsing. Validate the entire schema and all bounds before allocating. A capacity violation returns `adapter_outcome: SIMULATION_CAPACITY`, the exceeded dimension and null monetary results. Never truncate or split an oversized snapshot into separately allocated batches.

Intermediate products can reach `10^24`; use arbitrary-precision integers or an equally exact method. Floating-point arithmetic is insufficient.

### 3.6 `shadow_comparison_labels`

Every outcome preserves `status: SHADOW_NOT_APPLIED`. Preserve `SIMULATED`, `SYNTHETIC_FIXTURE_PROFILE` and `PROVISIONAL_PRODUCT_DECISION`, with `funds_executed:false`, `effects_applied:false` and `production:NOT_AUTHORIZED`.

Diagnostics belong to `adapter_outcome`, without extending inherited shadow statuses:

| `adapter_outcome` | Shadow `status` | Monetary payload |
|---|---|---|
| `COMPUTED` | `SHADOW_NOT_APPLIED` | Computed amounts |
| `INVALID_INPUT` | `SHADOW_NOT_APPLIED` | Null; validation reason |
| `SIMULATION_CAPACITY` | `SHADOW_NOT_APPLIED` | Null; exceeded dimension |
| `NOT_BOUND` | `SHADOW_NOT_APPLIED` | Null; unresolved dependency |

Failed calculations never appear as successful zero allocations.

Separate comparison metadata uses `comparison_state: COMPARABLE` or `NOT_COMPARABLE`. Numeric comparison requires two `COMPUTED` results with identical frozen cash, label set, class membership, remaining obligations and KRW unit. Record each side’s explicit algorithm/policy identity and source digest.

Deliberately different policies may be compared; their differences establish neither error nor financial superiority. Report candidate minus baseline using `shadow_allocation_delta_krw`, `shadow_remaining_after_delta_krw`, `shadow_total_allocated_delta_krw` and `shadow_unallocated_cash_delta_krw`.

Otherwise return `NOT_COMPARABLE`, a reason and null deltas. Never fabricate rows to extend a pinned two-payee baseline. Equality applies only to this snapshot and proves neither executed settlement nor upstream conformance.

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
      "rationale": "Bound synthetic identity and reject duplicate obligations without asserting legal identity.",
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
      "rationale": "Apply inherited adopted classes without fallback or invented financial priorities.",
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
      "rationale": "Define one frozen calculation without cumulative or persistent settlement effects.",
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
      "rationale": "Preserve class priority and rounding while preventing overpayment.",
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
      "rationale": "Bound parsing and exact computation without changing economic terms.",
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
      "rationale": "Preserve unapplied status and reject fabricated comparison compatibility.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| Acceptance | Evidence / status |
|---|---|
| One decision block resolving six items | §4: six ADOPTED entries |
| Unique labels, unknown-class rejection, bounded inputs | §§3.1–3.2, 3.5 |
| Inherited priority and largest remainder; five examples | §3.4 |
| One frozen snapshot and existing-node boundaries | §3.3 |
| Production unauthorized; shadow effects unapplied | Banner and §3.6 |
| Decision-ledger validation | **UNVERIFIED:** no execution or validation receipt supplied |
| Actual documentation-index reference | **PENDING:** required index file is outside permitted revision scope |

**Blocking finding disposition:** The missing index reference is valid and remains unresolved. The final revision instruction permits editing only this note, `tests/decision_bindings.json` and `tests/vectors/pack/`; it excludes `docs/CAP_COVERAGE.md`. This document cannot truthfully claim that the index was changed. No link inside this note substitutes for that change, and repository acceptance is not claimed.

## 6. Open risks

Concrete inherited class vocabulary and tie-comparator bindings require verification by the implementation consumer. Missing required bindings must produce `NOT_BOUND`.

Remaining obligations are synthetic assertions, not evidence of legal validity or completeness. Legal, tax and accounting interpretations remain working assumptions pending professional review.

The six product decisions are resolved; index integration and decision-ledger validation remain outstanding.

## 7. 후속 작업

The supervisor’s repository integration must add this actual entry to the documentation index at `docs/CAP_COVERAGE.md`:

`[Bounded multi-payee shadow inputs](decisions/CAPITAL_MULTIPAYEE_SHADOW.md) — provisional CAPITAL-ALLOC-V1 input contract; one frozen snapshot; SHADOW_NOT_APPLIED.`

Then run the existing decision-ledger validator and `python3 scripts/docs_surface.py --check`, recording actual results. These are integration requirements, not claimed completed actions.

The implementation consumer must verify policy binding, permutation independence, ties, duplicate and unknown-class rejection, numeric and capacity boundaries, conservation, shadow-envelope preservation and incompatible comparisons. New vectors require maintained surface registrations and README needles.

Cumulative late cash, participation, claim slices, UC1–UC4 and upstream changes remain with their existing nodes.
