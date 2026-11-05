# Capital Recovery Competition — 공유 정산 재원에 대한 회수 순서 리허설

> **PROVISIONAL PRODUCT DECISION**
>
> **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**
>
> Date: **2026-11-05** · Capital main: **`13b8536`** · kix-protocol: **`121e0bd`**
>
> Simulation/product design only; no real money; production **`NOT_AUTHORIZED`**. No upstream adoption, legal priority determination, authenticated authority or production capability is established.
>
> Execution provenance: the attribution above is supervisor-prescribed. Sonnet CLI execution, three failed attempts and Fable takeover were not verified and are not claimed. Repository revisions are supervisor-supplied bases.

Node: `recovery-competition-decision`. Dependencies: `overlay-recovery-writeoff`, `claim-slice-registry`. Pending consumer: **`recovery-order-rehearsal`**.

This document specifies a disposable Capital-local comparison contract, `CAPITAL-RECOVERY-COMPETITION-V1`. `ADOPTED` means a provisional product choice, not implementation completion. Existing recovery and slice decisions remain authoritative; an unavailable rule produces an explicit unsupported result rather than a substitute policy.

## 1. 결정 요약

| Item | Decision | CAP rows | Consumer |
|---|---|---|---|
| `comparison_population` | Compare 2–4 selected `DEFAULTED` advances against one frozen local snapshot; retain deductions and holder obligations outside the selected population | CAP-04, CAP-11 | `recovery-order-rehearsal` — PENDING |
| `scenario_order_inputs` | Compare 2–4 caller-supplied complete permutations; vary only advance order | CAP-04, CAP-20 | `recovery-order-rehearsal` — PENDING |
| `per_step_amount_rule` | Apply the smallest of requested ceiling, remaining claim, current valid quote and available source; primary before secondary | CAP-04 | `recovery-order-rehearsal` — PENDING |
| `shared_source_accounting` | One scenario-local balance per economic source; deduct historical consumption and preserve holder priority before rehearsal consumption | CAP-04, CAP-11 | `recovery-order-rehearsal` — PENDING |
| `authority_and_refusal_behavior` | Preserve existing beneficiary, approval and authority checks; refusals consume nothing; missing semantics are unsupported | CAP-04, CAP-19 | `recovery-order-rehearsal` — PENDING |
| `comparison_bounds` | Fixed small limits, one logical day, deterministic traces and descriptive differences; no ranking or preferred order | CAP-04, CAP-20 | `recovery-order-rehearsal` — PENDING |

CAP references describe intended coverage, not completed capabilities.

## 2. KIX 비전 연결

The ambition is reproducible evidence about competition for finite distributions: show exactly whose simulated recovery changes when processing order changes, without creating collection authority.

Sources used are limited to the supplied pack:

- [`CAPITAL_DEFAULT_RECOVERY.md`](CAPITAL_DEFAULT_RECOVERY.md), especially §§4.3–4.8: observed beneficiary distributions, shared consumption limits, recovery allocation, residual claims and human approval requirements.
- [`CAPITAL_CLAIM_SLICE_REGISTRY.md`](CAPITAL_CLAIM_SLICE_REGISTRY.md), supplied excerpt only: slice uniqueness, shared limits, holder priority and the precedence of existing decisions.
- [`CAPITAL_ACCOUNTS_TAX_LEGAL.md`](CAPITAL_ACCOUNTS_TAX_LEGAL.md), supplied excerpt only: accounting and legal positions remain provisional working assumptions.
- [`CAPITAL_REQUIREMENTS_KO.md`](../CAPITAL_REQUIREMENTS_KO.md) and [`SEAMS.md`](../SEAMS.md), supplied excerpts only: fixture observations and local gates do not establish production bindings or semantic conformance.
- [`kix-protocol README`](/workspace/capital-run/kixproto-ro/README.md): mock and local development do not open real funds, providers or production.
- [`AUTHORITY_MODEL_1.md`](/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md), A-4: historical replay does not authorize a new external execution.

No truncated file remainder or linked document outside the allowed pack was consulted. In particular, the slice excerpt does not expose its complete calculation rules. This contract requires the consumer to preserve those rules through existing validation; it does not reconstruct them.

## 3. 항목별 결정

### 3.1 `comparison_population` — ADOPTED

A comparison uses one immutable, already-loaded **local synthetic snapshot** at one `sim_day`. It includes:

- Selected advance IDs, bound claim IDs, beneficiary mappings, `DEFAULTED` status, recovery phase, outstanding components or post-writeoff residual claims.
- Existing slice assignments, holder entitlements, source observations and observation cuts.
- Historical consumption by **all** advances and other existing consumers, including advances omitted from the comparison.
- Existing recovery approval context, same-day recovery totals and applicable policy references.

Both `POST_DEFAULT` and `POST_WRITEOFF` advances are eligible when their existing recovery calculation is available. Each selected advance must have a positive recoverable claim at the snapshot. The rehearsal does not default an advance, write it off, accrue new interest or advance the clock.

Sources are observed local fixture distributions, not caller-created liquidity. Inputs select existing source references; they cannot override observed amounts, beneficiaries, holder entitlements or historical deductions. A hypothetical change to a source balance requires a separate fixture and comparison.

A valid population contains 2–4 advances and 1–8 sources, with at least one source eligible, apart from exhaustion, for at least two selected advances. This establishes actual competition potential. Other-beneficiary sources may be selected to exercise refusals.

A missing beneficiary mapping, incomplete consumption history, unavailable holder calculation or unresolved source identity makes the comparison `UNSUPPORTED`. Missing data never means zero.

### 3.2 `scenario_order_inputs` — ADOPTED

The request supplies:

- A frozen snapshot reference and `sim_day`.
- Selected advances and source references.
- One fixed ordered source list and positive integer `requested_ceiling_krw` per advance/source pair.
- 2–4 scenarios, each with a unique `scenario_id` and an `advance_order` containing every selected advance exactly once.

All scenarios share the same sources, ceilings, policy basis and approval context. Only advance order varies. Duplicate permutations, omitted advances, repeated sources within an advance, unknown references and scenario-specific financial overrides are refused.

For each advance, all selected bound-claim sources form the primary phase. Other-claim sources form the secondary phase and retain their supplied relative order. A secondary source cannot be used while an eligible primary balance remains available to that advance. An omitted primary source with available funds therefore blocks secondary recovery.

A caller ceiling is an experimental request limit, not permission to bypass primary recovery. If it leaves usable primary funds, secondary attempts return `PRIMARY_REMAINS_AVAILABLE`. A failed or indeterminate primary eligibility check also blocks that advance’s secondary phase.

Each scenario starts from a fresh copy of the same snapshot. Its result never initializes another scenario. Scenario order represents processing order only: it establishes no contractual creditor seniority, lien, pari passu rule or insolvency priority.

### 3.3 `per_step_amount_rule` — ADOPTED

For each scheduled advance/source pair, the consumer records an attempt after checking phase, beneficiary, holder and primary-order eligibility.

For a supported, eligible pair:

`candidate_krw = min(requested_ceiling_krw, remaining_claim_krw, quote_limit_krw, source_available_krw)`

All amounts are integer KRW. `quote_limit_krw` comes from the existing recovery quotation logic evaluated against the current disposable state. An initial quote cannot override later source depletion. The implementation must use existing arithmetic and rounding; it must not introduce a new interest formula.

The existing approval gate checks the candidate amount and cumulative same-day recovery. If that gate refuses, the entire step consumes zero. The consumer must not reduce the candidate merely to fit an approval threshold.

A successful `POST_DEFAULT` step allocates recovery to default interest, contractual interest and principal in the existing order. A `POST_WRITEOFF` step reduces the existing residual claim, without new interest or reopening the case. These are ephemeral calculations, never accounting postings.

Every trace row contains scenario, ordinal, advance, source, phase, requested ceiling, pre-step claim, quote limit, available source, candidate, simulated recovery, allocation, post-step balances and status/reasons.

Zero claim or zero available source is an explicit `NO_EFFECT` result, respectively `CLAIM_SATISFIED` or `SOURCE_EXHAUSTED`. Zero is never represented as a successful `RECOVERY` entry.

### 3.4 `shared_source_accounting` — ADOPTED

A source uses the existing canonical claim/payee-line identity. An observation cut is provenance, not a new balance. Two cuts or aliases for the same distribution cannot create two pools; unresolved equivalence is unsupported.

For a supported source, let:

- `O` = observed distribution.
- `C` = total historical consumption.
- `H` = still-unconsumed entitlement withheld for holders under the existing slice rules.
- `R` = successful rehearsal consumption within this scenario.

Then `available = O − C − H − R`.

`C` and `H` must be disjoint and established by the existing source/slice accounting. If they cannot be separated, or the result is negative, the consumer stops with an explicit error; it does not clamp the balance or invent holder allocations. Holders are not competing recovery advances, and their entitlements cannot be consumed by changing scenario order.

This expression is a reconciliation invariant, not a replacement for slice-specific eligibility limits. Existing validated quotes and holder rules can impose stricter limits.

A successful step atomically reduces both its advance’s claim and the one shared source balance. Refusals change neither. For each scenario:

- Source consumption never exceeds the holder-adjusted remaining distribution.
- Advance recovery never exceeds its recoverable claim.
- Total advance recovery equals total rehearsal source consumption.

**Worked reversal example.** Amounts below are KRW. A and B belong to beneficiary P, are `DEFAULTED`, and each has an 80,000 principal-only recoverable claim. Their distinct bound claims have observed primary availability of zero. Shared secondary source S belongs to P: `O=150,000`, `C=30,000`, `H=20,000`, hence available 100,000. Existing quotes and approvals permit the amounts; both ceilings are 80,000.

| Scenario | Step | Recovery | S remaining | Advance claim remaining |
|---|---|---:|---:|---:|
| A then B | A → S | 80,000 | 20,000 | A: 0 |
| A then B | B → S | 20,000 | 0 | B: 60,000 |
| B then A | B → S | 80,000 | 20,000 | B: 0 |
| B then A | A → S | 20,000 | 0 | A: 60,000 |

Total recovery is 100,000 in both scenarios. Reversal changes each advance’s recovery by 60,000; the contract expresses no preference.

**Exhaustion and beneficiary refusal example.** In a separate fixture, S has `O=130,000`, with unchanged `C=30,000` and `H=20,000`, leaving 80,000. A consumes 80,000 first. B’s S attempt returns `NO_EFFECT / SOURCE_EXHAUSTED`, recovery zero.

B next attempts T, whose 40,000 distribution belongs to beneficiary Q. It returns `REFUSED / BENEFICIARY_MISMATCH`, recovery zero; T remains 40,000 and B remains owed 80,000. Neither common platform ownership nor insufficient P funds authorizes using Q’s distribution.

### 3.5 `authority_and_refusal_behavior` — ADOPTED

Running a read-only comparison grants no recovery authority. AI may request or describe a rehearsal; `executionAuthorized` remains false.

Successful simulated steps must satisfy existing recovery gates using approval context already present in the frozen local fixture. The request cannot create approvers, elevate roles, treat proposals as approvals or replace human identities. Labels retain their existing unauthenticated simulation meaning.

The existing `underwriting_depth.two_person_threshold_krw` remains authoritative. Its check includes prior same-day recoveries plus successful earlier rehearsal steps for that advance. Splitting requests or changing order cannot reset this total.

Results distinguish:

| Status | Meaning |
|---|---|
| `SIMULATED` | All existing gates passed; disposable balances changed |
| `NO_EFFECT` | Supported calculation with nothing recoverable from this attempt |
| `REFUSED` | Known rule prohibits the attempt; zero consumption |
| `UNSUPPORTED` | Required evidence or semantics cannot be evaluated; no successful comparison |

Known refusals include beneficiary mismatch, unavailable primary precedence, invalid state and insufficient existing approvals. The trace retains existing refusal codes where available. Later independent attempts may continue after a known refusal, but primary failures block that advance’s secondary phase.

If missing semantics could affect balances or eligibility, the **whole comparison** is unsupported. Diagnostic traces may remain, but completed totals and comparative deltas are null; partial results cannot masquerade as complete scenarios.

Execution uses disposable in-memory state only. It performs no durable journal append, FSM transition, workspace update, live posting, provider query, reserve funding, signature, approval creation or upstream call. Returned output is labelled `SIMULATED_DISPOSABLE_COMPARISON`, with `persisted:false` and `executionAuthorized:false`.

### 3.6 `comparison_bounds` — ADOPTED

V1 bounds are fixed:

- 2–4 advances; 1–8 unique sources.
- 2–4 distinct caller-supplied complete orders.
- At most one attempt per advance/source pair: 32 attempts per scenario, 128 per comparison.
- One frozen logical day; no retries, source replenishment, automatic permutations or optimization.

Exceeding a bound returns `REFUSED / BOUNDS_EXCEEDED` before simulation. No input is truncated. Amounts use exact integer arithmetic; overflow or unsupported numeric representation is rejected.

Reports preserve caller scenario order and show per-advance recovery, allocation and residual claim; per-source consumption and remainder; total recovery; exhausted sources; refusal counts; and directional pairwise KRW differences. Differences are emitted only for complete comparisons. A pairwise difference is explicitly “scenario X minus scenario Y,” not a score.

There is no winner, fairness score, preferred-order recommendation, profitability objective or automatic operating-policy update. Rates, reserves, writeoff timing, holder rights and human gates remain unchanged.

## 4. 기계 판독 결정

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "recovery-competition-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-11-05",
  "provisional": true,
  "entries": {
    "comparison_population": {
      "status": "ADOPTED",
      "value": {
        "contract": "CAPITAL-RECOVERY-COMPETITION-V1",
        "state": "DEFAULTED",
        "phases": ["POST_DEFAULT", "POST_WRITEOFF"],
        "snapshot": "FROZEN_LOCAL_SYNTHETIC",
        "historical_consumption_scope": "ALL_CONSUMERS",
        "consumer": "recovery-order-rehearsal",
        "consumer_status": "PENDING"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-05",
      "cap_rows": ["CAP-04", "CAP-11"],
      "rationale": "Compare shared-source competition without discarding outside consumption or holder rights.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "scenario_order_inputs": {
      "status": "ADOPTED",
      "value": {
        "orders": "CALLER_SUPPLIED_COMPLETE_PERMUTATIONS",
        "variable": "ADVANCE_ORDER_ONLY",
        "source_lists_and_ceilings": "FIXED_ACROSS_SCENARIOS",
        "primary_before_secondary": true,
        "contractual_seniority": false,
        "consumer": "recovery-order-rehearsal",
        "consumer_status": "PENDING"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-05",
      "cap_rows": ["CAP-04", "CAP-20"],
      "rationale": "Isolate processing-order effects without introducing a priority policy.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "per_step_amount_rule": {
      "status": "ADOPTED",
      "value": {
        "candidate": "MIN_REQUEST_CLAIM_QUOTE_SOURCE",
        "amount_unit": "INTEGER_KRW",
        "allocation": "EXISTING_RECOVERY_RULES",
        "approval_failure": "ZERO_NO_THRESHOLD_CLIPPING",
        "zero_amount": "NO_EFFECT",
        "consumer": "recovery-order-rehearsal",
        "consumer_status": "PENDING"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-05",
      "cap_rows": ["CAP-04"],
      "rationale": "Make amounts deterministic while preserving existing quotation and approval constraints.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "shared_source_accounting": {
      "status": "ADOPTED",
      "value": {
        "identity": "EXISTING_CANONICAL_CLAIM_PAYEE_LINE",
        "available": "OBSERVED_MINUS_HISTORICAL_CONSUMPTION_MINUS_UNCONSUMED_HOLDER_ENTITLEMENT_MINUS_SCENARIO_CONSUMPTION",
        "holder_rule": "EXISTING_SLICE_RULES_AUTHORITATIVE",
        "scenario_reset": "FRESH_SNAPSHOT_COPY",
        "consumer": "recovery-order-rehearsal",
        "consumer_status": "PENDING"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-05",
      "cap_rows": ["CAP-04", "CAP-11"],
      "rationale": "Prevent double consumption and preserve holder priority across competing advances.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "authority_and_refusal_behavior": {
      "status": "ADOPTED",
      "value": {
        "execution": "DISPOSABLE_IN_MEMORY_ONLY",
        "approvals": "EXISTING_CONTEXT_AND_CUMULATIVE_SAME_DAY_GATES",
        "new_approval_identities": false,
        "executionAuthorized": false,
        "persisted": false,
        "missing_semantics": "UNSUPPORTED_COMPARISON_WITH_NULL_TOTALS",
        "refusal_consumption_krw": 0,
        "consumer": "recovery-order-rehearsal",
        "consumer_status": "PENDING"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-05",
      "cap_rows": ["CAP-04", "CAP-19"],
      "rationale": "A comparison must neither manufacture authority nor conceal unsupported recovery semantics.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "comparison_bounds": {
      "status": "ADOPTED",
      "value": {
        "advances": {"min": 2, "max": 4},
        "sources": {"min": 1, "max": 8},
        "scenarios": {"min": 2, "max": 4},
        "max_attempts_per_scenario": 32,
        "max_attempts_total": 128,
        "logical_days": 1,
        "measures": ["RECOVERY", "RESIDUAL_CLAIM", "SOURCE_REMAINDER", "REFUSALS", "PAIRWISE_KRW_DIFFERENCES"],
        "recommendation": "NONE",
        "optimization": false,
        "consumer": "recovery-order-rehearsal",
        "consumer_status": "PENDING"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-05",
      "cap_rows": ["CAP-04", "CAP-20"],
      "rationale": "Keep exhaustive trace inspection practical without selecting an operating order.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| Acceptance | Contract location |
|---|---|
| Six decisions and pending consumer | §§1, 4 |
| Bounded caller orders for multiple defaulted advances | §§3.1–3.2, 3.6 |
| Primary, beneficiary, holder, consumption and approval preservation | §§3.2–3.5 |
| Reversal, exhaustion and foreign-beneficiary examples | §3.4 |
| Disposable execution, explicit unsupported results, no recommendation or policy changes | §§3.5–3.6 |

## 6. Open risks

The pack does not establish current implementation APIs or complete slice formulas. Their binding remains unverified; the pending consumer must return unsupported wherever existing semantics cannot be preserved. Local approval labels are not authentication. Legal enforceability and creditor priority remain outside this comparison.

## 7. 후속 작업

`recovery-order-rehearsal` implements this contract and verifies reversal, exhaustion, beneficiary refusal, holder protection, historical deductions, cumulative approvals, primary bypass refusal, unsupported semantics and scenario isolation. Verification must also demonstrate unchanged input state and absence of durable writes or external calls.

Future vector files require the repository’s documentation-surface entries, matching README needles and `python3 scripts/docs_surface.py --check`. This decision delivers no implementation, test execution, upstream receipt or production authorization.
