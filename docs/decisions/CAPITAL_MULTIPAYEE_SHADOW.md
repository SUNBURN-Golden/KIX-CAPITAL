# CAPITAL_MULTIPAYEE_SHADOW — Bounded multi-payee inputs for class-priority allocation

> **PROVISIONAL PRODUCT DECISION**
>
> Requested decision attribution: **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**.
>
> Date: **2026-10-21** · Capital main: **`02bc3e5`** · kix-protocol: **`45ec626`**. These bases are supervisor-supplied, not independently verified.
>
> Execution provenance: this document was prepared by **Codex**. Claude CLI was not executed; no Sonnet execution, three failed attempts, or Fable fallback is claimed. The attribution fields below preserve the supervisor-requested designation.
>
> Simulation/product design only; no real money. Production remains **`NOT_AUTHORIZED`**. Every shadow effect remains **`SHADOW_NOT_APPLIED`**. This decision authorizes no upstream contract change, persistent settlement record, or UC1–UC4 implementation.

Node: `multipayee-shadow-input-decision`. Dependencies: `settlement-policy-decision`, `shadow-policy-decision`, `shadow-refund-resale`.

The exact-path restriction governs this review. The settlement and shadow policy originals are outside that list and were not opened. Their adoption is supplied by the supervisor; their complete class vocabulary and tie comparator are **UNDETERMINED from this pack**. This document inherits those rules by reference instead of reconstructing them. Missing source access is not a new `DECISION_REQUIRED` for policy already decided.

## 1. 결정 요약

All six entries are **ADOPTED as provisional Capital-local input decisions**. This does not mean upstream adoption.

| Item | Decision | CAP rows | Consumer |
|---|---|---|---|
| `synthetic_payee_identity` | Unique, bounded ASCII fixture labels; one row per payee per snapshot | CAP-02, CAP-05 | Multi-payee shadow input adapter |
| `class_mapping_and_unknowns` | Explicit class membership from `CAPITAL-ALLOC-V1`; reject unknown classes without fallback | CAP-02, CAP-05 | Policy loader and shadow allocator |
| `single_cut_allocation_inputs` | One frozen cash amount and remaining-obligation vector; no cumulative processing | CAP-02, CAP-05 | `policy-simulator`, `shadow-refund-resale` |
| `within_class_caps_and_rounding` | Preserve class priority, proportional largest remainder, inherited tie rule, and remaining-obligation caps | CAP-02, CAP-05 | Shadow allocator |
| `fixture_capacity_bounds` | At most 64 rows, 32,768 input bytes, and bounded integer amounts | CAP-08, CAP-20 | Input validation and fixtures |
| `shadow_comparison_labels` | Compare compatible snapshots only; otherwise `NOT_COMPARABLE`; all effects unapplied | CAP-09, CAP-20 | Shadow comparison presentation |

CAP mappings are local coverage assignments, not assertions that implementation or upstream qualification is complete.

## 2. KIX 비전 연결

[CAPITAL_DEMO_BOOK.md](CAPITAL_DEMO_BOOK.md) already places additional payee lines in shadow metadata while retaining the pinned two-payee FSM. This contract makes that multi-payee experiment reproducible without converting synthetic labels into legal parties or changing existing beneficiary mappings.

The supplied [requirements excerpt](../CAPITAL_REQUIREMENTS_KO.md) separates Capital-local development from operational authority. The [seams excerpt](../SEAMS.md) likewise distinguishes local gateways from upstream adoption and semantic conformance. Consequently, successfully calculating these vectors establishes local arithmetic coverage only.

The [Protocol README](/workspace/capital-run/kixproto-ro/README.md) connects settlement and financial evidence to the wider ticket lifecycle while retaining operational locks. [AUTHORITY_MODEL_1.md](/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md) separates recorded facts, authority, and external execution. A frozen shadow snapshot therefore carries reproducible inputs, not payment authority or finality.

The supplied [claim-slice registry excerpt](CAPITAL_CLAIM_SLICE_REGISTRY.md) retains ownership of slice uniqueness and shared caps. This contract does not create slices or borrowing-base eligibility.

## 3. 항목별 결정

### 3.1 `synthetic_payee_identity`

Adopt input version `CAPITAL-MULTIPAYEE-SHADOW-INPUT-V1`.

Each row contains exactly `payee_label`, `class_id`, and `remaining_obligation_krw`. Labels match `^fx-[a-z0-9][a-z0-9_-]{0,60}$`: 4–64 ASCII bytes. Equality is exact; there is no trimming, Unicode normalization, case folding, or alias expansion.

Labels must be unique across the entire snapshot, including different classes and zero-obligation rows. Duplicate labels reject the whole input; they are never merged or resolved by “last row wins.” One label belongs to exactly one class in that snapshot.

Identity is the tuple `(fixture_id, snapshot_id, payee_label)`. Both enclosing identifiers use the same bounded label grammar. Cross-snapshot label reuse does not establish a continuing creditor, account, or beneficiary identity.

Row order is not identity and cannot determine allocation. Canonical output order is ascending ASCII `payee_label`; this presentation order does **not** replace the inherited allocation tie rule. Real names, account numbers, and legal identifiers are outside this schema.

### 3.2 `class_mapping_and_unknowns`

Every row must state `class_id` explicitly. The consumer loads the allowed vocabulary, class priority, and tie semantics from the adopted `CAPITAL-ALLOC-V1` source. Labels such as “venue” or “organizer” do not independently confer a class.

Unknown, missing, wrongly typed, or differently cased class identifiers produce `INVALID_INPUT` with reason `UNKNOWN_CLASS` or `INVALID_CLASS`. Validation includes zero-obligation rows. There is no automatic residual class, ignored row, or partial result.

The demo-book source identifies `PROTECTED_THIRD_PARTY` and `ECOSYSTEM_ROYALTY`; it does not supply the complete authoritative vocabulary. This document neither completes that list by inference nor introduces new class names.

The consumer freezes the loaded allocation and shadow-policy source digests with each calculation. Missing, unreadable, or unresolved required policy produces `NOT_BOUND`, with allocations absent. An inherited `UNDETERMINED` or deferred policy branch follows its existing not-bound behavior. Valid adopted policy is applied without another decision request.

### 3.3 `single_cut_allocation_inputs`

The input object has exactly these fields:

- `schema`: `CAPITAL-MULTIPAYEE-SHADOW-INPUT-V1`;
- `fixture_id` and `snapshot_id`;
- `cash_krw`: available synthetic cash for this calculation;
- `payees`: the complete remaining-obligation vector.

Reject unknown fields and duplicate JSON object keys. Amounts are nonnegative JSON integers; booleans, strings, fractions, and exponent-form numeric encodings are rejected.

`remaining_obligation_krw` means the fixture author's obligation remaining immediately before this cut. It is an explicit synthetic assumption, not verified evidence of a debt. The allocator does not derive it from original face, prior payments, refunds, fees, percentages, or prior shadow outputs.

The consumer validates and freezes the complete payload and policy sources before calculation. It must not reread mutable workspace values between classes or between comparison runs. Input identifiers alone do not prove equality; comparisons inspect the frozen content.

Outputs contain each row's allocation and `remaining_after_krw`, plus total allocated and `unallocated_cash_krw`. Zero rows remain visible. An empty payee array is valid and leaves all cash unallocated.

There is no history lookup, deduplication ledger, settlement write, or automatic carry-forward. Recomputing a snapshot repeats a hypothetical calculation. Cumulative late cash, partial-payment histories, refund/resale lifecycle effects, participation, and claim slices remain with their existing nodes.

### 3.4 `within_class_caps_and_rounding`

`CAPITAL-ALLOC-V1` remains authoritative for financial priority and largest-remainder behavior. No percentage, fee, underwriting cap, or protected entitlement is created here.

For each class in inherited priority order, let remaining cash be `C`, row obligations be `r_i`, and class obligation be `R = Σr_i`. The class budget is `B = min(C, R)`. If `R = 0`, allocate zero without division. Otherwise the proportional calculation is:

- base allocation `q_i = floor(B × r_i / R)`;
- remainder numerator `m_i = (B × r_i) mod R`;
- distribute `B − Σq_i` single units in descending remainder order, resolving equal remainders with the existing policy comparator.

The unique synthetic label supplies the payee identity expected by that comparator. This note does not choose a new alphabetical, input-order, or random tie rule. If the inherited comparator requires unavailable information, that calculation is `NOT_BOUND`; implementation must not guess.

Use exact integer arithmetic, including intermediate products. Allocation cannot exceed a row's remaining obligation. A lower-priority class receives cash only after all higher-priority remaining obligations are satisfied. Cash exceeding all obligations stays explicitly unallocated; it is not assigned to a new residual beneficiary.

Required invariants are `0 ≤ allocation_i ≤ r_i`, `remaining_after_i = r_i − allocation_i`, and `Σallocation_i + unallocated_cash = input_cash`.

**Worked examples.** Amounts are synthetic KRW integers. `P` denotes `PROTECTED_THIRD_PARTY`; `L` denotes an actual lower-priority class resolved from the policy. In the tie example, P1–P3 denote distinct valid labels **in inherited tie-comparator order**, not an assumed alphabetical order.

| Case | Frozen obligations | Cash | Expected allocation | Unallocated |
|---|---|---:|---|---:|
| Cash exhausted inside protected class | P1=5, P2=3; L1=9 | 5 | P1=3, P2=2, L1=0 | 0 |
| Equal remainders | P1=1, P2=1, P3=1 | 2 | P1=1, P2=1, P3=0 | 0 |
| Zero cash | P1=5, P2=3 | 0 | P1=0, P2=0 | 0 |
| Fully satisfied obligations | P1=0, P2=0 | 7 | P1=0, P2=0 | 7 |
| Cash exceeds remaining obligations | P1=2, P2=1; L1=4 | 10 | P1=2, P2=1, L1=4 | 3 |

In the first example, base allocations are 3 and 1; remainder numerators are 1 and 7. The additional unit therefore goes to P2. In the tie example, each base is zero and each remainder numerator is 2; the first two inherited tie ranks receive one unit.

These calculations were checked in memory. Concrete label-to-tie-rank binding remains unverified because the authoritative comparator was not in the readable pack.

### 3.5 `fixture_capacity_bounds`

Adopt these local computational limits:

| Dimension | Inclusive bound |
|---|---:|
| UTF-8 input payload | 32,768 bytes |
| Payee rows | 0–64 |
| Each label or fixture/snapshot identifier | 4–64 ASCII bytes |
| Each class identifier | 1–64 ASCII bytes, also requiring policy membership |
| Cash and each remaining obligation | 0–1,000,000,000,000 |
| Sum of remaining obligations | 0–1,000,000,000,000 |

These are fixture capacity limits, not lending limits, entitlements, or copied financial terms. An otherwise valid payload exceeding them returns `SIMULATION_CAPACITY`, identifies the exceeded dimension, and produces no allocation. No truncation or batching is permitted.

Check payload size before parsing, then schema and bounds before allocation. Integer products may reach `10^24`; use arbitrary-precision integers or an equivalently exact method. Floating-point rounding is unacceptable even when the final amount fits the bound.

### 3.6 `shadow_comparison_labels`

Every result carries `SIMULATED`, `SYNTHETIC_FIXTURE_PROFILE`, `PROVISIONAL_PRODUCT_DECISION`, `SHADOW_NOT_APPLIED`, `funds_executed:false`, `effects_applied:false`, and `production:NOT_AUTHORIZED`.

Execution status is separate from those labels: `COMPUTED`, `INVALID_INPUT`, `SIMULATION_CAPACITY`, or `NOT_BOUND`. Failed calculations have absent/null allocations, never plausible zero allocations.

A numeric comparison requires identical frozen fixture/snapshot content: cash, payee-label set, class membership, remaining obligations, and unit. Each side must identify its algorithm/policy and source digest. Different policies may be compared when explicitly named; their difference is not evidence of error or financial superiority.

Return `COMPARABLE` only when both sides meet that contract. Report `candidate − baseline` per label and for unallocated cash. All-zero deltas mean numerical equality for this snapshot only.

Otherwise return `NOT_COMPARABLE`, a reason, and null deltas. In particular, the pinned two-payee result cannot be padded with zero-valued rows to masquerade as a multi-payee baseline. Never label shadow output as executed settlement, upstream adoption, or semantic conformance.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "multipayee-shadow-input-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-10-21",
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
      "date": "2026-10-21",
      "cap_rows": ["CAP-02", "CAP-05"],
      "rationale": "Provide stable synthetic identity without aliasing, duplicate obligations, or legal-party claims.",
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
        "missing_required_policy": "NOT_BOUND",
        "source_binding": "FREEZE_LOADED_POLICY_DIGESTS"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-21",
      "cap_rows": ["CAP-02", "CAP-05"],
      "rationale": "Exercise adopted classes without inventing priorities or silently reclassifying unknown inputs.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "single_cut_allocation_inputs": {
      "status": "ADOPTED",
      "value": {
        "fields": ["schema", "fixture_id", "snapshot_id", "cash_krw", "payees"],
        "row_fields": ["payee_label", "class_id", "remaining_obligation_krw"],
        "amount_type": "NONNEGATIVE_JSON_INTEGER",
        "snapshot": "ONE_FROZEN_PAYLOAD_AND_POLICY_SET",
        "unknown_fields_and_duplicate_keys": "REJECT",
        "empty_payees": "VALID_ALL_CASH_UNALLOCATED",
        "history_lookup": false,
        "persistent_effects": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-21",
      "cap_rows": ["CAP-02", "CAP-05"],
      "rationale": "Make remaining obligations explicit and prevent a one-cut simulation from implying cumulative settlement.",
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
        "surplus": "UNALLOCATED_CASH"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-21",
      "cap_rows": ["CAP-02", "CAP-05"],
      "rationale": "Preserve decided priority and rounding while preventing overpayment and invented residual entitlement.",
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
        "max_cash_krw": 1000000000000,
        "max_row_obligation_krw": 1000000000000,
        "max_total_obligation_krw": 1000000000000,
        "overflow_result": "SIMULATION_CAPACITY",
        "financial_limit": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-21",
      "cap_rows": ["CAP-08", "CAP-20"],
      "rationale": "Bound parsing and computation without changing economic terms or truncating fixtures.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "shadow_comparison_labels": {
      "status": "ADOPTED",
      "value": {
        "labels": ["SIMULATED", "SYNTHETIC_FIXTURE_PROFILE", "PROVISIONAL_PRODUCT_DECISION", "SHADOW_NOT_APPLIED"],
        "comparison_requires": "IDENTICAL_FROZEN_INPUTS_AND_EXPLICIT_POLICY_IDENTITIES",
        "delta_direction": "CANDIDATE_MINUS_BASELINE",
        "incompatible_inputs": "NOT_COMPARABLE",
        "incompatible_deltas": null,
        "funds_executed": false,
        "effects_applied": false,
        "production": "NOT_AUTHORIZED"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-21",
      "cap_rows": ["CAP-09", "CAP-20"],
      "rationale": "Distinguish numerical comparison from applied settlement and refuse fabricated compatibility.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| Acceptance | Evidence or remaining verification |
|---|---|
| One block; six decisions | §4 contains exactly one block with six adopted entries |
| Identity, classes, bounds | §§3.1–3.2 and §3.5 |
| Priority, rounding, five examples | §3.4; arithmetic checked independently in memory |
| One frozen snapshot; existing-node boundaries | §3.3 |
| Production unauthorized; shadow unapplied | Banner and §3.6 |
| Decision ledger validation | **UNDETERMINED:** validator is outside the permitted read set; no ledger pass is claimed |
| Documentation index reference | Exact reference supplied below; insertion not performed under read-only instructions |

## 6. Open risks

The full inherited class vocabulary and tie comparator remain unverified from this restricted pack. Consumers must bind their adopted sources before producing affected results. A discovered conflict is resolved in favor of the prior financial policy, not by silently changing its priorities.

Synthetic remaining obligations are assertions supplied by fixture authors. This contract establishes neither their legal validity nor completeness. Any legal, tax, or accounting interpretation remains a working assumption pending professional review.

## 7. 후속 작업

The supervisor writes this document and inserts this reference into the repository's existing documentation index:

`[CAPITAL_MULTIPAYEE_SHADOW — bounded multi-payee shadow inputs](decisions/CAPITAL_MULTIPAYEE_SHADOW.md)`

That relative target assumes an index under `docs/`; adjust only the relative prefix for another location. The actual index path is **UNDETERMINED**, because none was supplied within the allowed set.

The implementation consumer binds the adopted policy sources, materializes tie-ranked fixtures, and tests row permutation, duplicate labels, unknown classes, numeric rejection, capacity boundaries, conservation, and incompatible comparisons. New vector files require the repository's maintained surface registrations and README needles.

After writing, run the existing decision-ledger validator and `python3 scripts/docs_surface.py --check` in an authorized execution context. Neither was run here. Keep cumulative late-cash handling, participation, claim slices, UC1–UC4, and upstream contracts with their existing nodes.
