# CAPITAL_MULTIPAYEE_SHADOW — Bounded multi-payee inputs for class-priority allocation

> **PROVISIONAL PRODUCT DECISION**
>
> Requested attribution: **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**.
>
> Date: **2026-10-22** · Capital main: **`cde0bc7`** · kix-protocol: **`93cec6a`**. Bases are supervisor-supplied, not independently verified.
>
> Execution provenance: prepared by **Codex** from the supplied pack. Claude CLI was not executed; no Sonnet execution, failed attempts, or Fable fallback is claimed.
>
> Simulation/product design only; no real money. Production remains **`NOT_AUTHORIZED`**. All shadow effects remain **`SHADOW_NOT_APPLIED`**. No persistent settlement record, UC1–UC4 implementation, or upstream contract change is authorized.

Node: `multipayee-shadow-input-decision`. Dependencies: `settlement-policy-decision`, `shadow-policy-decision`, `shadow-refund-resale`.

The inherited policies remain authoritative. Their adoption and the shadow-envelope requirements are supplied by the supervisor and review. Their originals are outside the final exact-path reading scope and were not opened. Missing source detail does not reopen adopted financial decisions.

## 1. 결정 요약

All six entries are **ADOPTED as provisional Capital-local product decisions**, without implying upstream adoption.

| Item | Decision | CAP rows | Consumer |
|---|---|---|---|
| `synthetic_payee_identity` | Unique ASCII fixture labels; one row per payee per snapshot | CAP-02, CAP-05 | Multi-payee input adapter |
| `class_mapping_and_unknowns` | Explicit inherited class membership; reject unknown classes | CAP-02, CAP-05 | Policy loader and allocator |
| `single_cut_allocation_inputs` | One frozen cash amount and remaining-obligation vector | CAP-02, CAP-05 | `policy-simulator`, `shadow-refund-resale` |
| `within_class_caps_and_rounding` | Inherit priority, largest remainder and tie comparator; cap at remaining obligations | CAP-02, CAP-05 | Shadow allocator |
| `fixture_capacity_bounds` | Maximum 64 rows, 32,768 bytes, bounded integer amounts | CAP-08, CAP-20 | Input validation |
| `shadow_comparison_labels` | Preserve shadow envelope; separate adapter diagnostics; compare compatible snapshots | CAP-09, CAP-20 | Comparison presentation |

CAP mappings identify local coverage responsibilities, not completed implementation.

## 2. KIX 비전 연결

The supplied [Capital requirements](../CAPITAL_REQUIREMENTS_KO.md) distinguish local development authority from operational authorization. The [seams registry](../SEAMS.md) distinguishes local checks from upstream adoption and semantic conformance. This decision makes larger synthetic allocation experiments reproducible within those boundaries.

The [claim-slice registry excerpt](CAPITAL_CLAIM_SLICE_REGISTRY.md) retains responsibility for slice uniqueness, shared caps and borrowing-base protection. Synthetic payee rows neither create claim slices nor establish eligibility. The [accounts, tax and legal excerpt](CAPITAL_ACCOUNTS_TAX_LEGAL.md) keeps professional interpretations provisional; fixture identity does not establish legal payee identity.

Only supplied excerpts support these connections. No upstream receipt or additional source inspection is claimed.

## 3. 항목별 결정

### 3.1 `synthetic_payee_identity`

Adopt `CAPITAL-MULTIPAYEE-SHADOW-INPUT-V1`.

Each payee row contains exactly `payee_label`, `class_id`, and `shadow_remaining_obligation_krw`. Labels match `^fx-[a-z0-9][a-z0-9_-]{0,60}$`, giving 4–64 ASCII bytes. Equality is exact: no trimming, case folding, normalization or alias expansion.

Labels must be unique across the entire snapshot, including different classes and zero-obligation rows. Duplicates reject the whole input; they are never merged. Each label belongs to exactly one class.

Identity is `(fixture_id, snapshot_id, payee_label)`. Both enclosing identifiers use the same label grammar. Reusing a label in another snapshot establishes no continuing creditor or beneficiary identity.

Canonical presentation order is ascending ASCII label. Input order cannot influence allocation, and presentation order does not replace the inherited tie comparator. Real names, bank details and legal identifiers are outside this schema.

### 3.2 `class_mapping_and_unknowns`

Every row declares `class_id`. Load the vocabulary, class priority and tie comparator from adopted `CAPITAL-ALLOC-V1`; never infer membership from a payee label.

An unknown class rejects the whole input with adapter outcome `INVALID_INPUT` and reason `UNKNOWN_CLASS`. Missing, wrongly typed or syntactically invalid classes use reason `INVALID_CLASS`. Validation includes zero-obligation rows. There is no fallback class, ignored row or partial allocation.

Freeze the loaded allocation and shadow-policy digests before computation. Missing, unreadable or unresolved required policy produces adapter outcome `NOT_BOUND`, with monetary results null. An inherited undecided or deferred branch retains its existing not-bound behavior; adopted branches are applied without another decision request.

The pack does not establish the complete class vocabulary or concrete tie comparator. Those are inherited dependencies, not new values for this node to invent.

### 3.3 `single_cut_allocation_inputs`

The input object has exactly:

- `schema`: `CAPITAL-MULTIPAYEE-SHADOW-INPUT-V1`;
- `fixture_id` and `snapshot_id`;
- `shadow_cash_krw`: available synthetic cash;
- `payees`: the complete remaining-obligation vector.

All monetary keys use the `shadow_` prefix, including inputs, echoed amounts, outputs and comparison deltas. This replaces the earlier draft’s unprefixed amount fields.

Reject unknown fields and duplicate JSON object keys. Amounts are nonnegative JSON integers; booleans, strings, fractions and exponent-form numeric encodings are rejected.

`shadow_remaining_obligation_krw` is the fixture author’s assumption immediately before this calculation. It is not verified debt evidence. The allocator does not derive it from face value, historical payments, refund events, fees or earlier shadow results.

Freeze the complete payload and policy sources once. Never reread mutable state between classes or comparison runs. Identifiers alone do not establish equivalent inputs.

Successful results contain:

- per row: `payee_label`, `class_id`, `shadow_allocation_krw`, `shadow_remaining_after_krw`;
- totals: `shadow_total_allocated_krw`, `shadow_unallocated_cash_krw`.

Zero-obligation rows remain visible. An empty array is valid and leaves all cash unallocated.

There is no history lookup, settlement write, replay ledger or automatic carry-forward. Recomputing repeats a hypothetical calculation. Cumulative late cash, participation, claim slices and refund/resale lifecycle effects remain with their existing nodes.

### 3.4 `within_class_caps_and_rounding`

Preserve `CAPITAL-ALLOC-V1` financial priority and largest-remainder rules. No new fee, percentage, entitlement or underwriting limit is introduced.

For each inherited class, let remaining cash be `C`, obligations be `r_i`, and their sum be `R`. The class budget is `B = min(C, R)`. If `R = 0`, allocate zero without division. Otherwise:

- `q_i = floor(B × r_i / R)`;
- `m_i = (B × r_i) mod R`;
- distribute `B − Σq_i` single units by descending `m_i`, resolving ties with the inherited comparator.

Synthetic labels supply payee identity only where that comparator accepts it. If required comparator information is unavailable, return adapter outcome `NOT_BOUND`; do not substitute alphabetical or input order.

Use exact integers, including intermediate products. No allocation exceeds its remaining obligation. Lower-priority classes receive cash only after higher-priority remaining obligations are satisfied. Surplus remains unallocated.

The mathematical invariants are:

`0 ≤ a_i ≤ r_i`; `remaining_after_i = r_i − a_i`; `Σa_i + unallocated = cash`.

These are mathematical symbols, not additional output keys.

**Worked examples.** Amounts are synthetic KRW integers. `P` denotes the inherited protected class and `L` an inherited lower-priority class. P1–P3 and L1 are table aliases for valid fixture labels. In the tie case, P1–P3 are already ordered by the inherited comparator.

| Case | Remaining obligations | Cash | Allocations | Remaining after | Unallocated |
|---|---|---:|---|---|---:|
| Cash exhausted inside protected class | P1=5, P2=3; L1=9 | 5 | P1=3, P2=2, L1=0 | P1=2, P2=1, L1=9 | 0 |
| Equal remainders | P1=1, P2=1, P3=1 | 2 | P1=1, P2=1, P3=0 | P1=0, P2=0, P3=1 | 0 |
| Zero cash | P1=5, P2=3 | 0 | P1=0, P2=0 | P1=5, P2=3 | 0 |
| Fully satisfied obligations | P1=0, P2=0 | 7 | P1=0, P2=0 | P1=0, P2=0 | 7 |
| Cash exceeds obligations | P1=2, P2=1; L1=4 | 10 | P1=2, P2=1, L1=4 | P1=0, P2=0, L1=0 | 3 |

For the first case, bases are 3 and 1; remainder numerators are 1 and 7, so P2 receives the extra unit. For the tie case, bases are zero and all remainder numerators are 2; the first two inherited ranks receive one unit.

These are arithmetic specifications, not executed fixtures or evidence that concrete comparator bindings were validated.

### 3.5 `fixture_capacity_bounds`

Adopt inclusive local bounds:

| Dimension | Bound |
|---|---:|
| UTF-8 payload | 32,768 bytes |
| Payee rows | 0–64 |
| Fixture, snapshot and payee identifiers | 4–64 ASCII bytes |
| Class identifier | 1–64 ASCII bytes and inherited membership |
| Cash, each obligation, total obligations | Each 0–1,000,000,000,000 KRW |

These limits bound fixtures and computation, not lending or economic rights.

Check payload size before parsing; validate the full schema and bounds before allocation. Exceeding a bound produces adapter outcome `SIMULATION_CAPACITY`, names the dimension, and returns no monetary result. Never truncate or batch an oversized snapshot.

Intermediate products can reach `10^24`. Use arbitrary-precision integers or an equally exact method, never floating-point approximation.

### 3.6 `shadow_comparison_labels`

Preserve the inherited shadow envelope. The adapter emits `status: SHADOW_NOT_APPLIED` for every outcome: successful arithmetic does not apply an effect. It also carries `SIMULATED`, `SYNTHETIC_FIXTURE_PROFILE`, `PROVISIONAL_PRODUCT_DECISION`, `funds_executed:false`, `effects_applied:false`, and `production:NOT_AUTHORIZED`.

The following values belong only to `adapter_outcome`. They are diagnostic metadata, never values of the inherited shadow `status` field:

| `adapter_outcome` | Shadow `status` | Monetary payload |
|---|---|---|
| `COMPUTED` | `SHADOW_NOT_APPLIED` | Computed amounts |
| `INVALID_INPUT` | `SHADOW_NOT_APPLIED` | Null; validation reason |
| `SIMULATION_CAPACITY` | `SHADOW_NOT_APPLIED` | Null; exceeded dimension |
| `NOT_BOUND` | `SHADOW_NOT_APPLIED` | Null; missing policy dependency |

Thus no new execution status enters the inherited closed set. Failed calculations never masquerade as successful zero allocations.

Comparison metadata uses a separate `comparison_state`: `COMPARABLE` or `NOT_COMPARABLE`. Neither is a shadow execution status.

Numeric comparison requires two `COMPUTED` results with identical frozen cash, label set, class membership, remaining obligations and KRW unit. Each side records its explicit algorithm/policy identity and source digest. Different policies may be compared deliberately; differing results do not establish error or financial superiority.

Report candidate minus baseline using `shadow_allocation_delta_krw`, `shadow_remaining_after_delta_krw`, `shadow_total_allocated_delta_krw`, and `shadow_unallocated_cash_delta_krw`. Equality applies only to this snapshot.

Otherwise use `NOT_COMPARABLE`, a reason and null deltas. Never pad a pinned two-payee baseline with fabricated rows. No comparison establishes executed settlement, upstream adoption or semantic conformance.

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
      "rationale": "Keep adapter diagnostics outside the inherited status set and reject fabricated comparison compatibility.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| Acceptance | Evidence / status |
|---|---|
| Exactly one block; six decisions | §4 |
| Unique labels, classes and bounded sizes | §§3.1–3.2, 3.5 |
| Inherited priority and five examples | §3.4 |
| Frozen snapshot and existing-node boundaries | §3.3 |
| Shadow amount prefix and status envelope | §§3.3, 3.6; first review blocker addressed |
| Production unauthorized; effects unapplied | Banner and §3.6 |
| Decision ledger validates note | **UNDETERMINED:** validator not executed under this document-only scope |
| Documentation-index reference | **NOT COMPLETED:** required location is `docs/CAP_COVERAGE.md`; final revision scope excludes editing it |

The index finding is valid. It cannot be resolved by a link inside this note. The final instruction permits only this document as the deliverable and excludes the index from editable paths, so repository-level acceptance remains incomplete until the supervisor applies that separate edit.

## 6. Open risks

Concrete class vocabulary and label-to-tie-rank bindings remain unverified from this pack. Consumers must resolve adopted sources before affected calculations; this note does not authorize substitutes.

Remaining obligations are synthetic assertions, not proof of completeness or legal validity. Legal, tax and accounting interpretations remain working assumptions pending professional review.

## 7. 후속 작업

The supervisor writes this note and adds the following actual index entry to `docs/CAP_COVERAGE.md`:

`[CAPITAL_MULTIPAYEE_SHADOW — bounded multi-payee shadow inputs](decisions/CAPITAL_MULTIPAYEE_SHADOW.md)`

Then run the existing decision-ledger validator and `python3 scripts/docs_surface.py --check`. No execution or passing result is claimed here.

The implementation consumer binds inherited policy sources and checks permutation independence, ties, duplicates, unknown classes, numeric rejection, capacity boundaries, conservation, shadow-envelope mapping and incompatible comparisons. New vectors require maintained surface registrations and README needles. Cumulative late cash, participation, claim slices, UC1–UC4 and upstream changes stay with their existing nodes.
