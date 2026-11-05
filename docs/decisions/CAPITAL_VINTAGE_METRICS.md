# CAPITAL_VINTAGE_METRICS — Draw-cohort metrics for simulated servicing

> **PROVISIONAL PRODUCT DECISION**
>
> Requested decision-maker attribution: **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**.
>
> Date: **2026-11-05** · Capital main: **`343f425`** · kix-protocol: **`7e75391`**.
>
> Simulation/product design only; no real money; production **`NOT_AUTHORIZED`**. No upstream adoption, authenticated observation, execution authority or SEMANTIC_CONFORMANCE is established.
>
> Execution provenance: the attribution and revision bases are supervisor-supplied. Claude CLI execution, three failed attempts and Fable takeover were not performed or verified. This document defines policy; implementation and repository-check results are not claimed.

Node: `vintage-metrics-decision`. Dependencies: `financial-terms-decision`, `overlay-repayment-posting`, `overlay-recovery-writeoff`, `residual-obligations-report`.

## 1. 결정 요약

`ADOPTED` denotes a provisional Capital product decision, not an implemented capability or upstream adoption.

| Item | Decision | CAP rows | Consumer |
|---|---|---|---|
| `cohort_membership_and_width` | Fixed 30-sim-day draw cohorts, anchored at day 0 | CAP-04, CAP-14 | Cohort projector |
| `draw_day_evidence` | Require draw-linked logical-day evidence; preserve an unassigned legacy population | CAP-04, CAP-20 | Evidence adapter |
| `metric_population_and_denominators` | Fixed originating population; explicit principal and count denominators | CAP-04, CAP-14 | Metrics calculator |
| `repayment_and_recovery_classification` | Separate F04, asserted payments, allocated recovery and unallocated late recovery | CAP-04, CAP-14 | Servicing classifier |
| `terminal_case_retention` | Retain closed, defaulted and written-off members | CAP-04, CAP-20 | Cohort projector |
| `unknown_evidence_treatment` | Null affected metrics; retain coverage counts and known subtotals | CAP-04, CAP-20 | Completeness evaluator |
| `report_bounds_and_labels` | One bounded, read-only snapshot; descriptive simulation labels | CAP-14, CAP-20 | Local report surface |

CAP associations describe intended consumers, not coverage completion.

## 2. KIX 비전 연결

The [Protocol README](/workspace/capital-run/kixproto-ro/README.md) distinguishes local verification from operational finance. [AUTHORITY_MODEL_1.md](/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md), A-4, requires preserving late facts and separates historical replay from fresh execution authority. Accordingly, cohort reporting retains terminal cases and late recoveries without issuing commands.

[CAPITAL_DEFAULT_RECOVERY.md](CAPITAL_DEFAULT_RECOVERY.md), §§4.3–4.6, supplies the controlling allocation boundary: pre-write-off recovery has default-interest, interest and principal components; post-write-off recovery has no such allocation. This report preserves that distinction without importing accounting recognition.

Supplied excerpts of [CAPITAL_REQUIREMENTS_KO.md](../CAPITAL_REQUIREMENTS_KO.md), [SEAMS.md](../SEAMS.md), [VALIDATION.md](../VALIDATION.md), and [CAPITAL_ACCOUNTS_TAX_LEGAL.md](CAPITAL_ACCOUNTS_TAX_LEGAL.md) establish simulation, binding and evidence limits. Their truncated remainder was not opened.

The financial-terms dependency was named but lies outside the explicit read allowlist. Its contents and implementation field bindings are **UNDETERMINED**, with `value: null`, because they were unavailable within scope. This does not reopen its adopted decisions. Consumers must load the adopted terms through the established mechanism; this report copies no rates, grace periods, write-off delays or reserve percentages.

The ambition is reproducible descriptive servicing evidence, with enough provenance to explain every inclusion and subtotal.

## 3. 항목별 결정

### 3.1 `cohort_membership_and_width` — ADOPTED

The unit is one accepted draw occurrence, identified by workspace/run scope, advance identifier and accepted draw-operation identity. Applications, commitments and rejected commands are excluded. Replayed copies of the same operation are one draw; conflicting copies are evidence errors.

For evidenced draw day `d ≥ 0`, cohort index is `floor(d / 30)`, with half-open bounds `[30k, 30(k+1))`. Day 29 belongs to `[0,30)`; day 30 belongs to `[30,60)`. Boundaries are logical simulation days, not calendar months.

Each cohort retains original drawn principal `P_i` and original membership. Later status, repayment, recovery or write-off cannot move its members. Independent runs are never pooled. Multiple accepted draw operations require individually attributable amounts and servicing; ambiguous attribution produces unknown metrics rather than invented splits.

The current cohort is marked `OPEN_COHORT` when the observation day precedes its ending boundary. Its population is “originated through this cut,” not a completed vintage.

### 3.2 `draw_day_evidence` — ADOPTED

Accept a nonnegative integer `sim_day` only when evidence explicitly links it to the accepted draw operation and agrees with source ordering. Retain the evidence reference and provenance label. A local recorded day remains simulated evidence, not authenticated time.

Do not infer draw day from maturity minus term, journal position, creation timestamps, first repayment, default, file modification time or report generation time.

Accepted legacy draws lacking sufficient timing evidence go to `UNASSIGNED_DRAW_DAY`, with draw count, known original-principal subtotal and missing/conflicting-evidence counts. Their attributable servicing amounts remain visible there, but they contribute to no dated cohort. Report-level disclosure must say that dated cohorts do not represent the full inventory when this group is nonempty.

An evidenced draw after the snapshot clock is inconsistent, not an ordinary unassigned legacy draw. Reject that snapshot. Newly supplied timing evidence may assign a draw in a later report; retain the changed evidence reference and never rewrite an earlier report.

### 3.3 `metric_population_and_denominators` — ADOPTED

For each cohort at cut `C`, define:

- `N`: accepted draw count.
- `P`: sum of original drawn principal.
- `F`: cumulative accepted F04 principal repayments.
- `R_p`, `R_i`, `R_d`: recorded pre-write-off recovery principal, contractual-interest and default-interest components.
- `W`: recorded written-off principal.
- `B_i = P_i − F_i − R_p,i − W_i`: remaining principal for servicing classification.
- `D`: number of members with an accepted default command by `C`, retained thereafter.

`B` is a descriptive servicing quantity. It excludes post-write-off residual claims and is not an accounting carrying amount. Validate each draw’s conservation before aggregation; negative balances or unsupported reductions produce null affected metrics, never clamping.

Use the recorded effective maturity at `C`, including evidenced acceleration or extension under existing policy. For `B_i > 0`, `DPD_i = max(0, C.sim_day − effective_maturity_i)`. For proven `B_i = 0`, overdue principal is zero without requiring maturity evidence. DPD starts the day after maturity and does not itself declare default.

Report disjoint principal buckets: current, 1–29 DPD, 30–59 DPD, 60–89 DPD, and 90+ DPD. These are display bands, not policy thresholds. Defaulted balances before write-off remain eligible for these buckets. Written-off residual claims are separate.

Every permitted ratio uses the same snapshot cut:

| Ratio | Numerator through/at `C` | Denominator at `C` |
|---|---|---|
| `f04_principal_repaid_share` | `F` | Original cohort principal `P` |
| `allocated_recovery_principal_share` | `R_p` | `P` |
| `recorded_principal_serviced_share` | `F + R_p` | `P` |
| `recorded_writeoff_principal_share` | `W` | `P` |
| `remaining_principal_share` | `Σ B_i` | `P` |
| `overdue_principal_share` | `Σ B_i` where `DPD_i ≥ 1` | `P` |
| `dpd_30_plus_principal_share` | `Σ B_i` where `DPD_i ≥ 30` | `P` |
| `recorded_default_incidence` | `D` | Original cohort count `N` |

A zero denominator yields `null`, reason `ZERO_DENOMINATOR`, including empty cohorts. Missing required evidence yields `null`, reason `INCOMPLETE_EVIDENCE`, even if a subtotal is known. Preserve exact integer numerator/denominator pairs; optional displayed percentages round half-up to two decimal places.

No denominator shrinks to surviving, active, known-only or defaulted members. Default incidence is an observed command frequency, never a probability-of-default estimate.

### 3.4 `repayment_and_recovery_classification` — ADOPTED

Preserve four independently identifiable streams:

| Stream | Treatment |
|---|---|
| Accepted F04 principal repayments | Count principal in `F`; retain operation references |
| Asserted overlay payments | Show asserted gross amount and recorded allocation components separately |
| Pre-write-off recoveries | Preserve gross amount and `R_d`, `R_i`, `R_p`; require component sum to equal gross |
| Post-write-off recoveries | Show `L`, the unallocated late-recovery total; principal/interest allocation is `null`, reason `UNALLOCATED_BY_POLICY` |

An overlay assertion is not an additional principal payment merely because its amount resembles an F04 repayment. Link mirrored records by explicit operation evidence, count F04 principal once, and retain the assertion separately. Never deduplicate by equal amount or day. An assertion lacking a proven posting relationship does not reduce principal; if its unresolved relationship prevents complete reconciliation, affected combined metrics are null.

Consume existing recorded recovery allocations. Do not replay a new waterfall, assign all recovery to principal, infer allocation from balances, or allocate `L` proportionally. Missing allocation on a pre-write-off recovery is missing evidence; absent allocation on a post-write-off recovery is intentional policy.

`W` is not servicing received. `L` neither reduces `W` nor increases `F + R_p`. Show recorded residual claim separately where available. No combined cash, yield or loss ratio is introduced.

### 3.5 `terminal_case_retention` — ADOPTED

Closed, defaulted and written-off draws remain in `N` and `P`. Closure is not inferred from zero principal alone: other obligations may remain. Preserve source terminal status and residual-obligation evidence separately.

Late recovery stays attached to the originating draw, including after write-off, without reopening the case or issuing FSM repayment. Retain recorded default incidence after recovery. Missing archived history reduces evidence coverage; it never removes a terminal member.

This retention rule prevents survivor bias. It does not make cohorts with different ages or incomplete histories directly comparable.

### 3.6 `unknown_evidence_treatment` — ADOPTED

Each monetary metric returns `value`, `known_subtotal_krw`, `eligible_draw_count`, `complete_draw_count`, `incomplete_draw_count`, and reason codes. Event-derived metrics additionally expose known and incomplete event counts where determinable; unknown counts remain null.

“Complete” requires evidence of source completeness through `C`, not merely a nonempty list. An empty, complete event stream proves zero; an unavailable stream does not.

Completeness is metric-specific. Missing maturity can invalidate delinquency without invalidating fully evidenced F04 repayments. Missing principal invalidates principal-weighted ratios but need not invalidate an evidenced draw count or default count. No imputation, known-only replacement ratio or synthetic backfill is permitted.

Hand-calculated examples use synthetic KRW and an illustrative `C.sim_day = 180`; maturity and write-off facts are assumed evidenced inputs, not newly selected financial terms.

| Draw in `[0,30)` | Day | `P_i` | `F_i` | Pre-write-off recovery `(R_d,R_i,R_p)` | `W_i` | `L_i` | At cut |
|---|---:|---:|---:|---|---:|---:|---|
| A | 0 | 100 | 100 | `(0,0,0)` | 0 | 0 | Closed |
| B | 10 | 200 | 20 | `(5,5,40)` | 140 | 25 | Defaulted, written off |
| C | 29 | 100 | 20 | `(0,0,0)` | 0 | 0 | Maturity day 150 |

With complete evidence, `N=3`, `P=400`, `F=140`, `R_p=40`, `W=140`, and `B=80`. Pre-write-off gross recovery is 50; late unallocated recovery is 25. Suppose the separately linked asserted payments total 150: they remain a separate disclosure, not an additional 150 of principal.

The ratio table yields, in order: `35%`, `10%`, `45%`, `35%`, `20%`, `20%`, `20%`, and `1/3 = 33.33%`. C has 30 DPD. A and B remain in every originating denominator. Adding late recovery to principal would incorrectly produce `205/400`; that calculation is forbidden.

Now remove C’s maturity evidence. Overdue and 30+ metrics become null, with two complete draws, one incomplete draw, and known overdue-principal subtotal zero. Other evidenced amounts remain unchanged.

Alternatively, remove B’s recovery allocation while retaining its gross 50. `R_p`, combined servicing and dependent remaining-principal metrics become null; known `F=140` remains reportable. The separate gross recovery 50 remains known.

Add legacy draw U with original principal 60 and no draw-day evidence. The inventory count becomes four, but dated `N` stays three; `UNASSIGNED_DRAW_DAY` reports one draw and known principal 60. No date is fabricated.

### 3.7 `report_bounds_and_labels` — ADOPTED

Format: `CAPITAL-VINTAGE-METRICS-V1`. Permit only:

- One local workspace/run snapshot reference.
- `cohort_start_sim_day`, nonnegative and divisible by 30.
- `cohort_count`, integer 1–12.

Width is fixed at 30. No borrower, status, delinquency or outcome filters are allowed. Include empty requested buckets, unassigned-inventory coverage, and counts/principal subtotals for evidenced draws outside the selected range.

`C` contains the snapshot’s current `sim_day`, F04 and overlay end positions, and available source digests. Every source must describe that same consistent cut. Include only accepted records within those positions; later-recorded facts do not enter an earlier snapshot merely because their effective day is earlier. No arbitrary historical cutoff or multi-snapshot migration matrix is offered.

Bound V1 processing to 10,000 accepted draws and 100,000 relevant source records across the snapshot. Exceeding either limit returns `REPORT_LIMIT_EXCEEDED`, with no truncated result. These are report resource limits, not lending limits.

Labels are `SIMULATED`, `DESCRIPTIVE_ONLY`, `PROVISIONAL_PRODUCT_DECISION`, and `production: NOT_AUTHORIZED`. Queries change no clock, journal, case, grant, accounting entry or business digest.

Exclude predictions, PD/LGD models, annualized returns, actual yield, bank-cash claims, booked-loss claims, underwriting calibration, policy recalibration, reserve funding and accounting recognition.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "vintage-metrics-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-11-05",
  "provisional": true,
  "entries": {
    "cohort_membership_and_width": {
      "status": "ADOPTED",
      "value": {
        "unit": "accepted draw operation within one workspace/run",
        "width_sim_days": 30,
        "origin_sim_day": 0,
        "interval": "half-open",
        "membership": "immutable originating cohort; section 3.1"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-05",
      "cap_rows": ["CAP-04", "CAP-14"],
      "rationale": "Stable logical-day cohorts preserve originating populations.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "draw_day_evidence": {
      "status": "ADOPTED",
      "value": {
        "required": "explicit accepted-draw-linked nonnegative integer sim_day",
        "inference": "FORBIDDEN",
        "legacy_population": "UNASSIGNED_DRAW_DAY",
        "rules": "section 3.2"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-05",
      "cap_rows": ["CAP-04", "CAP-20"],
      "rationale": "Missing timing must remain visible without fabricated cohort membership.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "metric_population_and_denominators": {
      "status": "ADOPTED",
      "value": {
        "principal_denominator": "original cohort principal P",
        "count_denominator": "original cohort draw count N",
        "observation": "one consistent snapshot cut C",
        "zero_denominator": null,
        "zero_reason": "ZERO_DENOMINATOR",
        "metric_contract": "section 3.3"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-05",
      "cap_rows": ["CAP-04", "CAP-14"],
      "rationale": "Fixed denominators prevent survivor and known-only selection bias.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "repayment_and_recovery_classification": {
      "status": "ADOPTED",
      "value": {
        "streams": ["F04_PRINCIPAL", "ASSERTED_OVERLAY_PAYMENT", "ALLOCATED_PRE_WRITEOFF_RECOVERY", "UNALLOCATED_POST_WRITEOFF_RECOVERY"],
        "principal_serviced": "F + R_p",
        "late_recovery_allocation": null,
        "allocation_reason": "UNALLOCATED_BY_POLICY",
        "rules": "section 3.4"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-05",
      "cap_rows": ["CAP-04", "CAP-14"],
      "rationale": "Preserves existing allocations and prevents mirrored-payment double counting.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "terminal_case_retention": {
      "status": "ADOPTED",
      "value": {
        "retain": ["CLOSED", "DEFAULTED", "WRITTEN_OFF"],
        "late_recovery": "original cohort; no reopening",
        "default_incidence": "retained once evidenced",
        "rules": "section 3.5"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-05",
      "cap_rows": ["CAP-04", "CAP-20"],
      "rationale": "Terminal status must not erase servicing history or late facts.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "unknown_evidence_treatment": {
      "status": "ADOPTED",
      "value": {
        "affected_metric": null,
        "reason": "INCOMPLETE_EVIDENCE",
        "required_disclosures": ["known_subtotal_krw", "eligible_draw_count", "complete_draw_count", "incomplete_draw_count", "reason_codes"],
        "imputation": "FORBIDDEN",
        "rules_and_examples": "section 3.6"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-05",
      "cap_rows": ["CAP-04", "CAP-20"],
      "rationale": "Known subtotals remain useful without presenting incomplete evidence as complete.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "report_bounds_and_labels": {
      "status": "ADOPTED",
      "value": {
        "format": "CAPITAL-VINTAGE-METRICS-V1",
        "parameters": ["snapshot_ref", "cohort_start_sim_day", "cohort_count"],
        "max_cohorts": 12,
        "max_draws": 10000,
        "max_source_records": 100000,
        "snapshot_count": 1,
        "read_only": true,
        "labels": ["SIMULATED", "DESCRIPTIVE_ONLY", "PROVISIONAL_PRODUCT_DECISION"],
        "production": "NOT_AUTHORIZED",
        "rules_and_exclusions": "section 3.7"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-05",
      "cap_rows": ["CAP-14", "CAP-20"],
      "rationale": "A bounded snapshot report is buildable without financial execution or predictive claims.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| Acceptance | Resolution |
|---|---|
| Seven registered items | Exactly seven ADOPTED entries in §4 |
| Cohorts, parameters, legacy timing | §§3.1–3.2, 3.7 |
| Ratios, cuts, zero denominators, terminal examples | §§3.3, 3.5–3.6 |
| Four servicing streams and late allocation | §3.4 |
| Nulls, coverage and subtotals | §3.6 |
| Ledger and binding checks | Required integration gate; **NOT_RUN** in this read-only decision pass |

Check executables and implementation sources were outside the allowlist. Their passing status is **UNDETERMINED**, not claimed. No accounting, allowance or release decision is modified.

## 6. Open risks

Implementation field mappings, overlay/F04 linkage and source-completeness evidence remain unverified. Unsupported mappings yield null dependent metrics. Legacy timing may materially limit dated-cohort coverage. Different cohort ages and selective simulation scenarios prevent statistical or underwriting interpretation.

## 7. 후속 작업

The implementation consumer must bind recorded sources, reproduce the examples, and test boundary days, duplicate operations, terminal retention, missing evidence, zero denominators and resource limits. The supervisor writes this note and runs decision-ledger and binding checks before integration. If later implementation adds vector files, maintain documentation registrations and run the required documentation-surface check. Preserve existing accounting, allowance, release and upstream-binding decisions.
