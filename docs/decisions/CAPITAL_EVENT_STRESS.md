# CAPITAL_EVENT_STRESS — Correlated refund stress for one synthetic event

> **PROVISIONAL PRODUCT DECISION**
>
> Requested decision lane: **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**.
>
> Date: **2026-11-02** · Capital main: **`079dcca`** · kix-protocol: **`5f8e85c`**. These bases are supervisor-supplied, not independently verified.
>
> Simulation/product design only. **`SIMULATED` · `applied=false` · `funds_executed=false` · production `NOT_AUTHORIZED`.**

**Execution provenance.** Claude CLI attempts for Sonnet 5.5 failed three times; the subsequent Fable 5.1 attempt also failed. Each returned `Not logged in`. Codex authored and made the scope decisions below. The required `decided_by` and `provided_by` strings identify the requested delegation lane; they do **not** attest that those models authored, reviewed, or approved this document.

Decision node: `event-stress-scope-decision`. Dependencies: `risk-whatif-scenarios`, `portfolio-consistent-read`, `financial-terms-decision`. Consumer: **`event-stress-report`**.

The explicit reading allowlist controls. Financial-terms and implementation sources were outside it; truncated documents were used only through supplied excerpts. Existing decided terms remain authoritative. Their omitted contents are not reconstructed or reopened as undecided policy. Exact implementation bindings remain `UNDETERMINED` where identified below.

## 1. 결정 요약

`ADOPTED` here means a provisional local product decision, not upstream adoption or an adopted facade contract.

| Item | Decision | CAP rows | Consumer |
|---|---|---|---|
| `synthetic_event_membership` | Request-local explicit membership; exactly one selected event per scenario; reject duplicates within an event and unknown claims | CAP-04, CAP-08 | `event-stress-report` |
| `claim_shock_identity` | One common additional open-refund amount; transform each distinct member claim once per scenario | CAP-04, CAP-08 | `event-stress-report` |
| `shared_claim_counting` | Share the transformed claim view across advances; count claim collateral and advance exposure at their respective unique identities | CAP-04, CAP-08 | `event-stress-report` |
| `shock_application_order` | Freeze one consistent snapshot; transform claims; recompute existing risk; aggregate and compare | CAP-01, CAP-04 | `event-stress-report` |
| `unsupported_position_handling` | Reject invalid requests; retain unsupported positions with null affected metrics and explicit coverage | CAP-04, CAP-20 | `event-stress-report` |
| `scenario_capacity_bounds` | Fixed request and computation limits; atomic rejection above limits; no truncation | CAP-08, CAP-20 | `event-stress-report` |

## 2. KIX 비전 연결

The [Protocol README](/workspace/capital-run/kixproto-ro/README.md) connects ticket transactions, refunds, settlement, and financial evidence. Event-level scenarios provide a bounded way to inspect their common financial sensitivity: several claims can respond to one assumed disruption without introducing an event probability model.

The [authority decision](/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md) separates chain rights authority from offchain execution and financial obligations. Membership here is an operator-authored synthetic grouping. It proves neither ticket ownership nor contractual entitlement, event authenticity, performance, or collection rights.

[CAPITAL_DEMO_BOOK.md](CAPITAL_DEMO_BOOK.md) supplies the synthetic-fixture boundary and a secondary description of eligible face and open refunds. The supplied [claim-slice registry excerpt](CAPITAL_CLAIM_SLICE_REGISTRY.md) establishes the need to prevent double use of shared collateral. Neither source authorizes inventing allocation priorities.

The supplied [requirements](../CAPITAL_REQUIREMENTS_KO.md), [seams](../SEAMS.md), and [validation](../VALIDATION.md) excerpts preserve the distinction between local simulation, upstream binding, and demonstrated conformance. This decision adds a reporting scope, without claiming implementation or conformance.

## 3. 항목별 결정

### 3.1 `synthetic_event_membership`

**ADOPTED.** Introduce request format `CAPITAL_EVENT_STRESS_V1`. It contains event definitions and independently identified scenarios. Each event has `event_id` and a nonempty `claim_refs` list; each scenario names exactly one event.

A claim reference is the full existing identity within the captured workspace snapshot. Preserve any scope components required by that identity. Do not resolve claims by display name, organizer, venue, date, ticket identifier, substring, or upstream alias.

Event and scenario identifiers are case-sensitive request-local ASCII identifiers, 1–128 bytes, using letters, digits, `.`, `_`, and `-`. Existing claim identities retain their existing validation rules.

Reject duplicate event identifiers, duplicate scenario identifiers, and repeated claim references within one event. Reject unknown or ambiguous claims anywhere in the submitted definitions, including unselected events. Never create placeholder claims.

A known claim may belong to multiple event definitions. This expresses alternative synthetic groupings. Each scenario selects one definition, and scenarios always start from the same baseline. Overlaps therefore neither stack shocks nor establish additional collateral. Multi-event unions and sequential scenario composition are outside V1.

Membership is supplied explicitly with each request. No persistent event registry, real-event import, inferred relationship, ticket verification, or rights verification is introduced.

### 3.2 `claim_shock_identity`

**ADOPTED.** V1 supports one shock: `ADDITIONAL_OPEN_REFUND_KRW`, parameterized by nonnegative integer `additional_open_refund_krw`. Booleans, fractional values, negative amounts, and values outside existing monetary constraints are invalid.

For every distinct member claim, let `R` be its baseline open-refund amount. The scenario requests a hypothetical open-refund amount of `R + additional_open_refund_krw`. All members receive the same increment. This is a deterministic sensitivity input, not a refund entitlement, probability, new policy rate, or prediction.

The existing single-claim refund scenario evaluator must determine validity and resulting risk. Its existing caps, refund treatment, payee treatment, rounding, eligibility, and borrowing-base rules remain authoritative. The wrapper must not implement a second refund waterfall or subtract the shock again from an already transformed result.

Transformation identity is `(baseline identity, scenario_id, full claim identity)`. Event labels and advance identifiers do not create additional transformations. Zero shock is an identity operation for financial values, while still preserving unsupported-state labels.

**Binding limitation:** the existing evaluator’s callable, parameter mapping, and monetary domain were not in the pack. Their binding is `UNDETERMINED`, `value: null`, owned by `event-stress-report`. The implementation must establish an equivalent mapping to the existing evaluator before producing affected numeric results. It must not fabricate an approximation.

### 3.3 `shared_claim_counting`

**ADOPTED.** Construct one transformed view for each member claim and let every linked advance consume that same view.

Count claim-level eligible face and collateral once per full claim identity. Count exposure once per distinct advance identity, subject to the existing exposure-inclusion rules. A repeated relationship edge is invalid; one advance legitimately linked to several claims still contributes its exposure only once.

Per-advance rows may show a shared claim reference and contextual claim values, but those contextual values are explicitly non-additive. Do not sum standalone advance borrowing bases when they reuse the same claim.

Use existing allocation, reservation, slice, and shared-cap behavior if the current risk evaluator supports the position. This decision creates no equal split, pro rata allocation, priority waterfall, or new borrowing permission. If the evaluator cannot reconcile shared collateral, affected borrowing-base and headroom totals are null, with `UNSUPPORTED_SHARED_ALLOCATION`.

A standalone claim borrowing base is contextual information, not an amount available separately to every linked advance.

### 3.4 `shock_application_order`

**ADOPTED.** The consumer follows this sequence:

1. Validate request structure and capacity without modifying state.
2. Capture claims, advances, relationships, terms, and logical-time inputs through the existing consistent-read mechanism. Validate all references against that snapshot.
3. Calculate the baseline through existing risk arithmetic.
4. For each scenario, independently transform each distinct member claim from the baseline, then recompute affected advance and portfolio metrics.
5. Aggregate with unique claim and advance identities; emit baseline, stressed values, deltas, reasons, and coverage.

Sort event, scenario, claim, and advance output by their canonical identifiers. Array order must not affect financial results. Preserve evaluator-required internal ordering.

Claims outside the event retain their baseline claim views and remain in the portfolio comparison. An advance linked to both inside and outside claims consumes the changed and unchanged views together; its result can therefore change.

Use the same terms snapshot for baseline and stress. Read rates, caps, thresholds, and policy values from their existing sources. In particular, preserve `CAPITAL-TERMS-V1` references such as `underwriting_depth.single_advance_cap_krw`, `beneficiary_aggregate_cap_krw`, `portfolio_cap_krw`, and `two_person_threshold_krw`; copy no policy literals into this decision.

Stress changes no principal, repayment, settlement, maturity, default, write-off, ledger, or clock state. It produces no commands. An eligibility or margin consequence is reported under existing rules.

If a consistent snapshot or required terms binding is unavailable, affected computations are unavailable. Do not substitute several independently timed reads.

#### Worked examples

The following are illustrative synthetic integer fixtures, not executed tests. They use the eligible-face relationship quoted by `CAPITAL_DEMO_BOOK.md`: mapped outstanding less open refunds. They do not define general payee allocation or borrowing-base arithmetic.

**Two claims in one event, with an outside claim.** Event `E1` contains `C1` and `C2`. Scenario `S1` adds 100 synthetic KRW of open refund to each member. Assume each position is supported by the existing evaluator.

| Claim | Event membership | Mapped outstanding | Baseline open refund | Stressed open refund | Baseline eligible face | Stressed eligible face |
|---|---|---:|---:|---:|---:|---:|
| `C1` | `E1` | 1,000 | 100 | 200 | 900 | 800 |
| `C2` | `E1` | 2,000 | 200 | 300 | 1,800 | 1,700 |
| `C3` | Outside `E1` | 500 | 50 | 50 | 450 | 450 |

Event eligible face changes from 2,700 to 2,500. Portfolio eligible face changes from 3,150 to 2,950. The common increment is applied once to each of two members, giving a total hypothetical refund increase of 200. `C3` is retained unchanged.

Borrowing base is recalculated by the existing evaluator using these views and the same terms snapshot. No advance rate or refund eligibility exception is inferred from the example.

**Two advances sharing one claim.** Let distinct advances `A1` and `A2` reference `C1`, with included exposures of 300 and 200. Their combined exposure is 500. Both consume the same stressed `C1` view: open refund 200 and eligible face 800.

Claim eligible face contributes **800 once**, not 1,600. The shock adds **100 once**, not 200. Any allocation of supported borrowing base between `A1` and `A2` follows existing rules. If that allocation is unsupported, allocated bases and dependent headroom remain null; the consumer does not grant each advance the full claim base.

**Overlapping alternative.** If `E2` contains `C1` and `C3`, an `E2` scenario starts again from the baseline. It does not inherit the `E1` refund increase. Its portfolio result is an alternative outcome and must not be added to `S1`.

### 3.5 `unsupported_position_handling`

**ADOPTED.** Distinguish malformed input from a valid request containing unsupported positions.

Invalid identifiers, duplicates, unknown references, negative shocks, monetary-domain violations, and exceeded bounds reject the whole request before scenario evaluation. Return reasons and no financial result.

For known positions, preserve existing unsupported reasons. Examples include unavailable refund detail, unresolved payee mapping, unsupported shared allocation, and positions whose holder or slice semantics are not supported. Do not convert these into zero exposure, zero refund, or full eligibility.

Emit supported rows and explicit unsupported rows. An aggregate depending on an unsupported value is null; its delta is also null. Supported subtotals may be displayed only with their scope and excluded identifiers, never labeled a complete event or portfolio total. Known independent metrics may remain numeric.

Unsupported positions outside the event also affect portfolio coverage when the aggregate depends on them. Reports include unsupported identifiers, reason codes, and counts. `PARTIAL` or `UNAVAILABLE` results cannot carry a complete-portfolio pass or safety conclusion.

### 3.6 `scenario_capacity_bounds`

**ADOPTED.** V1 limits are:

| Dimension | Maximum |
|---|---:|
| UTF-8 request payload, before JSON parsing | 1,048,576 bytes |
| Event definitions per request | 20 |
| Claims per event | 100 |
| Membership edges across definitions | 1,000 |
| Independent scenarios per request | 20 |
| Claims in captured portfolio | 1,000 |
| Advances in captured portfolio | 1,000 |
| Advance-to-claim relationship edges | 5,000 |

Require at least one event and one scenario. Count overlapping membership once per event edge when enforcing capacity. Existing lower limits prevail. Reject excess atomically with `SCENARIO_CAPACITY_EXCEEDED`; do not sample, truncate, split silently, or evaluate only a convenient portfolio subset.

These bounds control local computation, not credit availability. No probability distribution, correlation coefficient, Monte Carlo engine, likelihood ranking, optimization, or new credit policy is introduced.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "event-stress-scope-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-11-02",
  "provisional": true,
  "execution_provenance": {
    "actual_author": "Codex",
    "requested_lane_executed": false,
    "sonnet_failed_attempts": 3,
    "fable_failed_attempts": 1,
    "failure": "Not logged in",
    "attribution_semantics": "Requested delegation lane only; not model authorship or approval evidence"
  },
  "bases": {
    "capital_main": "079dcca",
    "kix_protocol": "5f8e85c",
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
      "date": "2026-11-02",
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
      "date": "2026-11-02",
      "cap_rows": ["CAP-04", "CAP-08"],
      "rationale": "One deterministic increment per claim avoids duplicate refunds while preserving existing financial arithmetic.",
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
      "date": "2026-11-02",
      "cap_rows": ["CAP-04", "CAP-08"],
      "rationale": "Shared collateral must not multiply with the number of linked advances.",
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
      "date": "2026-11-02",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "A consistent baseline isolates the scenario effect without changing state or policy.",
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
      "date": "2026-11-02",
      "cap_rows": ["CAP-04", "CAP-20"],
      "rationale": "Unsupported positions remain visible and cannot silently improve reported coverage or headroom.",
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
      "date": "2026-11-02",
      "cap_rows": ["CAP-08", "CAP-20"],
      "rationale": "Explicit computational limits keep cohort stress buildable without introducing financial limits.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| Acceptance | Specification / implementation evidence required |
|---|---|
| Six decisions | Exactly six entries in §4 |
| Membership and identity | §3.1; duplicate, overlap, ambiguous-reference and unknown-claim cases |
| Once-per-claim shock | §3.2–3.3; shared-advance and duplicate-edge cases |
| Existing arithmetic | §3.4; one-member equivalence to existing scenarios, zero-shock identity, unchanged terms |
| Worked examples | §3.4 covers two members, shared advances, an outside claim, and alternative overlap |
| Bounded honest reporting | §3.5–3.6; unsupported propagation, limit boundaries, immutable inputs, deterministic output |

These are acceptance requirements, not claims that tests ran.

## 6. Open risks

Evaluator and snapshot bindings remain unverified. Their absence blocks dependent numeric output, not these six scope decisions. Existing `ADOPTED` policy must be consumed as decided; existing `UNDETERMINED` or deferred inputs retain their not-bound behavior.

Common absolute refund increments demonstrate sensitivity but do not estimate event cancellation losses or likelihood. Shared-position support may remain partial. Any legal, tax, accounting, priority, or recourse interpretation remains a working assumption pending professional review.

All upstream pins remain unchanged: FSM `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`; observation/AI references `e2a029d8ac3af7575888dac22fc4bf173ebec232`; lifecycle `e2313ab473ea1b5a7b5b9246a564749188c1c2c8`. No upstream receipt, production authorization, or semantic conformance is asserted.

## 7. 후속 작업

`event-stress-report` implements this bounded report, resolves the named bindings from its authorized sources, and verifies the acceptance cases. Preserve existing decisions, financial rates, production gates, export construction, vendor bytes, and golden artifacts.

If implementation adds vector files, maintain the required documentation inventory and README entries and run `python3 scripts/docs_surface.py --check`. This decision deliverable writes no files and performs no implementation or repository validation.
