# CAPITAL_EVENT_STRESS — Correlated refund stress for one synthetic event

> **PROVISIONAL PRODUCT DECISION**
>
> Requested decision lane: **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**.
>
> Date: **2026-11-03** · Capital main: **`079dcca`** · kix-protocol: **`15ea27b`**. These bases are supervisor-supplied, not independently verified.
>
> Simulation/product design only; no real money. **`SIMULATED` · `applied=false` · `funds_executed=false` · production `NOT_AUTHORIZED`.**

**Execution provenance.** The supplied prior revision records three failed Sonnet CLI attempts and one failed Fable attempt, each returning `Not logged in`. Those attempts were not repeated or independently verified in this revision. Codex authored this revision. The required `decided_by` and `provided_by` strings identify the requested delegation lane; they do **not** attest to those models’ authorship, review, or approval.

Decision node: `event-stress-scope-decision`. Dependencies: `risk-whatif-scenarios`, `portfolio-consistent-read`, `financial-terms-decision`. Consumer: **`event-stress-report`**.

The explicit reading allowlist controls. Financial-terms and implementation sources are outside it; truncated sources are used only through supplied excerpts. Existing decided terms remain authoritative. Omitted policy is not reconstructed or reopened. Exact implementation bindings remain `UNDETERMINED` where identified below.

## 1. 결정 요약

`ADOPTED` means a provisional local product decision, not upstream adoption or an adopted facade contract.

| Item | Decision | CAP rows | Consumer |
|---|---|---|---|
| `synthetic_event_membership` | Explicit request-local membership; one selected event per scenario; reject duplicates and unknown claims | CAP-04, CAP-08 | `event-stress-report` |
| `claim_shock_identity` | Common additional open-refund amount; transform each distinct member claim once | CAP-04, CAP-08 | `event-stress-report` |
| `shared_claim_counting` | Share transformed views; count collateral by claim and exposure by advance | CAP-04, CAP-08 | `event-stress-report` |
| `shock_application_order` | Capture one consistent snapshot, transform claims, recompute existing risk, aggregate and compare | CAP-01, CAP-04 | `event-stress-report` |
| `unsupported_position_handling` | Reject invalid requests; retain unsupported positions with null affected metrics and explicit coverage | CAP-04, CAP-20 | `event-stress-report` |
| `scenario_capacity_bounds` | Fixed computation limits; atomic rejection above limits; no truncation | CAP-08, CAP-20 | `event-stress-report` |

## 2. KIX 비전 연결

Event-level stress makes correlated refund sensitivity visible across claims and advances while keeping financial policy authoritative. It supports a broader financial reporting system through a bounded, buildable extension to existing scenarios.

The supplied [claim-slice registry excerpt](CAPITAL_CLAIM_SLICE_REGISTRY.md) identifies shared limits and prevention of borrowing-base double use as design concerns. This report preserves that boundary without inventing allocation priorities or asserting ticket ownership, contractual entitlement, event authenticity, performance, or collection rights.

The supplied [requirements](../CAPITAL_REQUIREMENTS_KO.md), [seams](../SEAMS.md), and [validation](../VALIDATION.md) excerpts distinguish local simulation from upstream binding and demonstrated conformance. Synthetic grouping adds reporting scope only. It creates no production identity adoption, upstream receipt, or conformance claim.

## 3. 항목별 결정

### 3.1 `synthetic_event_membership`

**ADOPTED.** Introduce request format `CAPITAL_EVENT_STRESS_V1`, containing event definitions and independently identified scenarios. Each event has `event_id` and a nonempty `claim_refs` list. Each scenario selects exactly one defined event.

A claim reference is its full existing identity within the captured workspace snapshot, preserving required scope components. Never resolve membership by display name, organizer, venue, date, ticket identifier, substring, or upstream alias.

Event and scenario identifiers are case-sensitive request-local ASCII identifiers, 1–128 bytes, using letters, digits, `.`, `_`, and `-`. Existing claim identities retain existing validation rules.

Reject duplicate event identifiers, duplicate scenario identifiers, and repeated claim references within one event. Reject unknown or ambiguous claims anywhere in submitted definitions, including unselected events. Never create placeholder claims.

A known claim may belong to multiple event definitions as alternative synthetic groupings. Every scenario starts independently from the same baseline. Overlap neither stacks shocks nor creates collateral. Multi-event unions and sequential composition are outside V1.

Membership is operator-authored and supplied with each request. No persistent event registry, real-event import, inferred relationship, ticket verification, or rights verification is introduced.

### 3.2 `claim_shock_identity`

**ADOPTED.** Support one shock: `ADDITIONAL_OPEN_REFUND_KRW`, parameterized by nonnegative integer `additional_open_refund_krw`. Reject booleans, fractional or negative values, and amounts outside existing monetary constraints.

For each distinct member claim, baseline open refund `R` becomes the requested hypothetical amount `R + additional_open_refund_krw`. Every member receives the same increment. This is deterministic sensitivity, not refund entitlement, probability, a new policy rate, or prediction.

The existing single-claim refund scenario evaluator determines validity and resulting risk. Preserve its caps, refund and payee treatment, rounding, eligibility, and borrowing-base rules. The wrapper must not implement a second refund waterfall or subtract the shock again from transformed results.

Transformation identity is `(baseline identity, scenario_id, full claim identity)`. Event labels and advance identifiers create no additional transformations. Zero shock preserves financial values and unsupported-state labels.

**Binding limitation:** the evaluator callable, argument mapping, and monetary domain were omitted from the authorized pack. Binding is `UNDETERMINED`, `value: null`, owned by `event-stress-report`. Establish an equivalent mapping before producing affected numeric results; do not approximate missing arithmetic.

### 3.3 `shared_claim_counting`

**ADOPTED.** Construct one transformed view per member claim. Every linked advance consumes that same view.

Count eligible face and collateral once per full claim identity. Count exposure once per distinct advance identity under existing exposure-inclusion rules. Reject repeated relationship edges. An advance legitimately linked to several claims contributes exposure only once.

Per-advance rows may repeat claim references and contextual values, explicitly marked non-additive. Never sum standalone advance borrowing bases that reuse the same claim.

Use existing allocation, reservation, slice, and shared-cap behavior where supported. This decision creates no equal split, pro rata allocation, priority waterfall, or borrowing permission. If existing arithmetic cannot reconcile shared collateral, affected borrowing-base and headroom totals are null with `UNSUPPORTED_SHARED_ALLOCATION`.

A standalone claim borrowing base is contextual information, not an amount separately available to every linked advance.

### 3.4 `shock_application_order`

**ADOPTED.** The consumer must:

1. Validate request structure and capacity without modifying state.
2. Capture claims, advances, relationships, terms, and logical-time inputs through the existing consistent-read mechanism; validate references against that snapshot.
3. Calculate baseline metrics through existing risk arithmetic.
4. Independently transform each scenario’s distinct member claims from the baseline; recompute affected advance and portfolio metrics.
5. Aggregate by unique claim and advance identities; emit baseline, stressed values, deltas, reasons, and coverage.

Sort output by canonical event, scenario, claim, and advance identifiers. Input array order must not affect financial results; preserve evaluator-required internal ordering.

Outside claims retain baseline views and remain in portfolio comparisons. An advance linked to both inside and outside claims consumes changed and unchanged views together, so its result may change.

Baseline and stress use the same existing terms snapshot. Read rates, caps, thresholds, and policy values from their authoritative sources. Preserve `CAPITAL-TERMS-V1` references, including `underwriting_depth.single_advance_cap_krw`, `beneficiary_aggregate_cap_krw`, `portfolio_cap_krw`, and `two_person_threshold_krw`; copy no policy literals.

Stress changes no principal, repayment, settlement, maturity, default, write-off, ledger, or clock state and emits no commands. Report eligibility and margin consequences only under existing rules.

Missing consistent snapshots or required terms bindings make dependent computations unavailable. Independently timed reads are not a substitute.

#### Worked examples

These illustrative synthetic integer fixtures are not executed tests. For these fixtures, assume the existing evaluator supports eligible face equal to mapped outstanding less open refunds. This assumption defines no general payee allocation or borrowing-base formula.

**Two claims in one event and an outside claim.** `E1` contains `C1` and `C2`; `S1` adds 100 synthetic KRW of open refund per member.

| Claim | Membership | Mapped outstanding | Baseline refund | Stressed refund | Baseline eligible face | Stressed eligible face |
|---|---|---:|---:|---:|---:|---:|
| `C1` | `E1` | 1,000 | 100 | 200 | 900 | 800 |
| `C2` | `E1` | 2,000 | 200 | 300 | 1,800 | 1,700 |
| `C3` | Outside `E1` | 500 | 50 | 50 | 450 | 450 |

Event eligible face moves from 2,700 to 2,500; portfolio eligible face moves from 3,150 to 2,950. Total hypothetical refunds increase by 200. `C3` remains unchanged and included.

Recalculate borrowing base through the existing evaluator and unchanged terms. Infer no advance rate or eligibility exception from these figures.

**Two advances sharing one claim.** Distinct advances `A1` and `A2` reference `C1`, with included exposures of 300 and 200: combined exposure 500. Both consume the same stressed view, refund 200 and eligible face 800.

Claim eligible face contributes **800 once**, not 1,600. Refund increases **100 once**, not 200. Existing supported rules govern allocation. If allocation is unsupported, allocated bases and dependent headroom are null; neither advance receives a separate full claim base.

**Overlapping alternative.** If `E2` contains `C1` and `C3`, its scenario restarts from baseline. It inherits no `E1` increase, and its portfolio outcome cannot be added to `S1`.

### 3.5 `unsupported_position_handling`

**ADOPTED.** Distinguish invalid requests from known unsupported positions.

Invalid identifiers, duplicates, unknown references, negative shocks, monetary-domain violations, and exceeded bounds reject the entire request with reasons and no financial result.

For known positions, preserve existing unsupported reasons, including missing refund detail, unresolved payee mapping, unsupported shared allocation, or unsupported holder/slice semantics. Never substitute zero exposure, zero refund, or full eligibility.

Emit supported and unsupported rows explicitly. Any aggregate depending on an unsupported value, and its delta, is null. Supported subtotals require explicit scope and excluded identifiers; never label them complete event or portfolio totals. Independent known metrics may remain numeric.

Unsupported outside positions also reduce portfolio coverage when aggregates depend on them. Include unsupported identifiers, reasons, and counts. `PARTIAL` or `UNAVAILABLE` reports cannot carry a complete-portfolio pass or safety conclusion.

### 3.6 `scenario_capacity_bounds`

**ADOPTED.** V1 limits are:

| Dimension | Maximum |
|---|---:|
| UTF-8 request payload before JSON parsing | 1,048,576 bytes |
| Event definitions | 20 |
| Claims per event | 100 |
| Membership edges across definitions | 1,000 |
| Independent scenarios | 20 |
| Captured portfolio claims | 1,000 |
| Captured portfolio advances | 1,000 |
| Advance-to-claim relationship edges | 5,000 |

Require at least one event and scenario. Count overlap once per event membership edge. Existing lower limits prevail. Reject excess atomically with `SCENARIO_CAPACITY_EXCEEDED`; never sample, truncate, split silently, or evaluate a convenient portfolio subset.

These are computation bounds, not credit limits. Exclude probability distributions, correlation coefficients, Monte Carlo models, likelihood rankings, optimization, and new credit policy.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "event-stress-scope-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-11-03",
  "provisional": true,
  "execution_provenance": {
    "revision_author": "Codex",
    "requested_lane_executed_this_revision": false,
    "prior_attempts_source": "SUPPLIED_PRIOR_REVISION_NOT_INDEPENDENTLY_VERIFIED",
    "attribution_semantics": "Requested delegation lane only; not model authorship or approval evidence"
  },
  "bases": {
    "capital_main": "079dcca",
    "kix_protocol": "15ea27b",
    "source": "SUPERVISOR_SUPPLIED"
  },
  "consumer": "event-stress-report",
  "mode": "SIMULATED",
  "applied": false,
  "funds_executed": false,
  "production": "NOT_AUTHORIZED",
  "entries": {
    "synthetic_event_membership": {
      "status": "ADOPTED",
      "value": {
        "format": "CAPITAL_EVENT_STRESS_V1",
        "membership": "EXPLICIT_REQUEST_LOCAL_FULL_CLAIM_IDENTITIES",
        "events_per_scenario": 1,
        "empty_event": "REJECT",
        "duplicate_ids_or_members": "REJECT_REQUEST",
        "unknown_or_ambiguous_claims": "REJECT_REQUEST",
        "overlap_between_events": "ALLOW_INDEPENDENT_SCENARIOS",
        "rights_authority_asserted": false,
        "real_event_imports": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-03",
      "cap_rows": ["CAP-04", "CAP-08"],
      "rationale": "Explicit bounded groupings support common-event sensitivity without inventing event or ticket authority.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "claim_shock_identity": {
      "status": "ADOPTED",
      "value": {
        "kind": "ADDITIONAL_OPEN_REFUND_KRW",
        "parameter": "additional_open_refund_krw",
        "domain": "NONNEGATIVE_INTEGER_WITHIN_EXISTING_MONETARY_CONSTRAINTS",
        "target": "baseline_open_refund_krw + additional_open_refund_krw",
        "identity": ["baseline_identity", "scenario_id", "full_claim_identity"],
        "applications_per_member_claim": 1,
        "zero_shock": "FINANCIAL_IDENTITY",
        "arithmetic": "EXISTING_SINGLE_CLAIM_REFUND_SCENARIO_EVALUATOR",
        "binding": {
          "status": "UNDETERMINED",
          "value": null,
          "target": "Equivalent existing evaluator mapping",
          "owner": "event-stress-report",
          "reason": "Callable, argument semantics and monetary domain omitted from authorized pack"
        }
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-03",
      "cap_rows": ["CAP-04", "CAP-08"],
      "rationale": "One increment per claim avoids duplicate refunds and preserves existing arithmetic.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "shared_claim_counting": {
      "status": "ADOPTED",
      "value": {
        "claim_view": "ONE_SHARED_TRANSFORMED_VIEW",
        "collateral_counting": "UNIQUE_FULL_CLAIM_IDENTITY",
        "exposure_counting": "UNIQUE_ADVANCE_IDENTITY_WITH_EXISTING_INCLUSION_RULES",
        "duplicate_relationship_edges": "REJECT_REQUEST",
        "allocation": "EXISTING_SUPPORTED_RULES_ONLY",
        "unsupported_allocation": "NULL_DEPENDENT_METRICS",
        "per_advance_claim_context": "NON_ADDITIVE"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-03",
      "cap_rows": ["CAP-04", "CAP-08"],
      "rationale": "Shared collateral must not multiply with linked advances.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "shock_application_order": {
      "status": "ADOPTED",
      "value": {
        "order": [
          "VALIDATE",
          "CAPTURE_CONSISTENT_SNAPSHOT",
          "EVALUATE_BASELINE",
          "TRANSFORM_UNIQUE_MEMBER_CLAIMS",
          "RECOMPUTE_EXISTING_RISK",
          "AGGREGATE_AND_COMPARE"
        ],
        "scenario_baseline": "SAME_IMMUTABLE_SNAPSHOT",
        "outside_claims": "UNCHANGED_AND_RETAINED",
        "terms": "SAME_EXISTING_TERMS_SNAPSHOT",
        "ordering": "CANONICAL_IDENTIFIERS",
        "commands_emitted": false,
        "missing_snapshot_or_terms": "UNAVAILABLE_DEPENDENT_METRICS"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-03",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "A consistent baseline isolates scenario effects without changing state or policy.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "unsupported_position_handling": {
      "status": "ADOPTED",
      "value": {
        "invalid_request": "REJECT_ATOMICALLY",
        "known_unsupported_position": "RETAIN_WITH_REASON_AND_NULL_AFFECTED_METRICS",
        "dependent_aggregates_and_deltas": "NULL",
        "supported_subtotals": "EXPLICIT_SCOPE_AND_EXCLUSIONS",
        "coverage": "INCLUDE_UNSUPPORTED_IDENTITIES_REASONS_AND_COUNTS",
        "partial_portfolio_pass": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-03",
      "cap_rows": ["CAP-04", "CAP-20"],
      "rationale": "Unsupported positions cannot silently improve coverage or headroom.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "scenario_capacity_bounds": {
      "status": "ADOPTED",
      "value": {
        "max_request_bytes": 1048576,
        "max_events": 20,
        "max_claims_per_event": 100,
        "max_membership_edges": 1000,
        "max_scenarios": 20,
        "max_snapshot_claims": 1000,
        "max_snapshot_advances": 1000,
        "max_advance_claim_edges": 5000,
        "max_event_or_scenario_id_ascii_bytes": 128,
        "existing_lower_limits": "PREVAIL",
        "overflow": "REJECT_ATOMICALLY",
        "truncation": false,
        "probability_models": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-03",
      "cap_rows": ["CAP-08", "CAP-20"],
      "rationale": "Explicit computation bounds keep cohort stress buildable without introducing credit limits.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| Acceptance | Specification / implementation evidence required |
|---|---|
| Valid decision block covering all six items | Exactly one `capital-decision-v1` block with six entries in §4 |
| Bounded membership, duplicates, overlap, unknown claims, no rights authority | §3.1 and §3.6; rejection and alternative-grouping cases |
| Once-per-claim shock, multiple advances, existing refund and borrowing-base rules | §3.2–3.4; shared-advance, duplicate-edge, single-member equivalence, and zero-shock cases |
| Worked examples: two event claims, two advances sharing one claim, outside claim | §3.4 worked examples |
| `SIMULATED`, `applied=false`, `funds_executed=false`; preserve financial rates, production gates, upstream pins | Opening banner and §4 declare labels; §3.4 preserves terms and state; §6–7 preserve production gates and upstream pins |
| Unsupported coverage and computation limits | §3.5–3.6; null propagation, limit boundaries, immutable inputs, deterministic output |

These map acceptance requirements; they do not claim tests ran.

## 6. Open risks

Evaluator and snapshot bindings remain unverified. Missing bindings block dependent numeric output, not the six scope decisions. Consume existing `ADOPTED` policy as decided; unresolved or deferred inputs retain their not-bound behavior.

Absolute refund increments demonstrate sensitivity, not cancellation losses or likelihood. Shared-position support may remain partial. Legal, tax, accounting, priority, and recourse interpretations remain working assumptions pending professional review.

Execution/reference pins remain unchanged: FSM `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`; observation/AI references `e2a029d8ac3af7575888dac22fc4bf173ebec232`; lifecycle `e2313ab473ea1b5a7b5b9246a564749188c1c2c8`. The supervisor’s research base `15ea27b` does not repin those consumers. No upstream adoption, receipt, semantic conformance, or production authorization is asserted.

## 7. 후속 작업

`event-stress-report` implements the report, resolves bindings from its authorized sources, and verifies mapped cases. Preserve existing decisions, financial rates, production gates, upstream pins, export construction, vendor bytes, and golden artifacts.

If implementation adds vector files, maintain documentation inventory and README entries and run `python3 scripts/docs_surface.py --check`. This revision supplies only the decision document for the supervisor to write; no repository files were modified and no implementation checks were run.
