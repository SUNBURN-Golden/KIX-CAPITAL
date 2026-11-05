# CAPITAL_VINTAGE_METRICS — Draw-cohort metrics for simulated servicing

> **PROVISIONAL PRODUCT DECISION**
>
> Requested decision-maker attribution: **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**.
>
> Date: **2026-11-05** · Capital main: **`343f425`** · kix-protocol context: **`7c43b79`**.
>
> Simulation/product design only; no real money or offer; production **`NOT_AUTHORIZED`**. No upstream adoption, authenticated observation, execution authority or SEMANTIC_CONFORMANCE is established.
>
> Execution provenance: attribution and revision bases are supervisor-supplied. Claude CLI execution, three failed attempts and Fable takeover were not performed or verified. Policy adoption and pending-consumer registration do not establish implementation.

Node: `vintage-metrics-decision`. Dependencies: `financial-terms-decision`, `overlay-repayment-posting`, `overlay-recovery-writeoff`, `residual-obligations-report`.

## 1. 결정 요약

`ADOPTED` means a provisional Capital product choice, not upstream adoption or implemented capability.

| Item | Decision | CAP rows | Consumer |
|---|---|---|---|
| `cohort_membership_and_width` | Fixed 30-sim-day draw cohorts anchored at day 0 | CAP-04, CAP-14 | Cohort projector |
| `draw_day_evidence` | Draw-linked logical-day evidence; unassigned legacy population | CAP-04, CAP-20 | Evidence adapter |
| `metric_population_and_denominators` | Originating population with explicit principal/count denominators | CAP-04, CAP-14 | Metrics calculator |
| `repayment_and_recovery_classification` | Separate F04, assertions, allocated recovery and unallocated late recovery | CAP-04, CAP-14 | Servicing classifier |
| `terminal_case_retention` | Retain closed, defaulted and written-off members | CAP-04, CAP-20 | Cohort projector |
| `unknown_evidence_treatment` | Null affected metrics; disclose coverage and known subtotals | CAP-04, CAP-20 | Completeness evaluator |
| `report_bounds_and_labels` | One bounded, read-only descriptive simulation snapshot | CAP-14, CAP-20 | Local report surface |

These roles belong to the designated future `vintage-metrics-report` consumer. CAP associations and module anchors do not establish coverage completion.

## 2. KIX 비전 연결

The supplied excerpts of [CAPITAL_REQUIREMENTS_KO.md](../CAPITAL_REQUIREMENTS_KO.md), [SEAMS.md](../SEAMS.md), [VALIDATION.md](../VALIDATION.md) and [CAPITAL_ACCOUNTS_TAX_LEGAL.md](CAPITAL_ACCOUNTS_TAX_LEGAL.md) establish simulation, evidence and binding limits. Their truncated remainders were not opened.

The supervisor’s review confirms that [CAPITAL_DEFAULT_RECOVERY.md](CAPITAL_DEFAULT_RECOVERY.md), §§4.3–4.6, controls recovery allocation: pre-write-off recovery preserves its components; post-write-off recovery remains unallocated and does not revive the case. This revision relies on that supplied review, without reopening the underlying implementation.

The financial-terms note lies outside the explicit read allowlist. Its contents and implementation mappings remain **UNDETERMINED**, `value: null`, within this review’s evidence. Its adopted policy is not reopened. Consumers must load applicable adopted terms through the established mechanism; this report copies no rates, grace periods, write-off delays or reserve percentages.

The objective is reproducible descriptive servicing evidence that explains every inclusion, exclusion and subtotal without claiming financial execution or accounting recognition.

## 3. 항목별 결정

### 3.1 `cohort_membership_and_width` — ADOPTED

One member is an accepted draw occurrence identified by workspace/run, advance identifier and accepted draw-operation identity. Exclude applications, commitments and rejected commands. Replayed copies of one operation count once; conflicting copies are evidence errors.

For evidenced draw day `d ≥ 0`, cohort index is `floor(d / 30)` and bounds are `[30k, 30(k+1))`. Day 29 belongs to `[0,30)`; day 30 belongs to `[30,60)`. These are logical simulation days, not calendar months.

Retain each member’s original drawn principal `P_i` and originating cohort regardless of subsequent status or servicing. Never pool independent runs. Multiple accepted draws require individually attributable principal and servicing; ambiguous attribution yields unknown affected metrics, never invented splits.

Mark a cohort `OPEN_COHORT` when the observation day precedes its ending boundary. Its population is originated through the cut, not a completed vintage.

### 3.2 `draw_day_evidence` — ADOPTED

Accept only a nonnegative integer `sim_day` explicitly linked to the accepted draw operation and consistent with source ordering. Retain its evidence reference and provenance. Local recorded time remains simulated evidence.

Never infer draw day from maturity minus term, journal position, creation timestamps, first repayment, default, file modification time or report generation time.

Legacy draws lacking sufficient timing evidence enter `UNASSIGNED_DRAW_DAY`. Disclose draw count, known original-principal subtotal and missing/conflicting-evidence counts. Retain attributable servicing there, but include these draws in no dated cohort. Explicitly disclose that dated cohorts omit part of the inventory whenever this group is nonempty.

A proven draw day after the snapshot clock is inconsistent: reject the snapshot. Later timing evidence may assign a legacy draw in a later report; preserve the new evidence reference and do not rewrite earlier reports.

### 3.3 `metric_population_and_denominators` — ADOPTED

At the single observation cut `C`, define:

- `N`: originating accepted draw count.
- `P`: original drawn principal summed over those members.
- `F`: cumulative accepted F04 principal repayments.
- `R_p`, `R_i`, `R_d`: recorded pre-write-off recovery principal, contractual interest and default interest.
- `W`: recorded written-off principal.
- `B_i = P_i − F_i − R_p,i − W_i`: remaining principal for servicing classification.
- `D`: members with an accepted default command by `C`, retained thereafter.

Validate conservation per draw before aggregation. Negative balances or unsupported reductions invalidate affected metrics; never clamp them. `B` excludes post-write-off residual claims and is not an accounting carrying amount.

Use recorded effective maturity at `C`, including evidenced acceleration or extension under existing policy. For `B_i > 0`, `DPD_i = max(0, C.sim_day − effective_maturity_i)`. Proven zero balances contribute zero overdue principal without maturity evidence. DPD begins the day after maturity; it does not declare default.

Disclose disjoint remaining-principal buckets: current, 1–29, 30–59, 60–89 and 90+ DPD. These are display bands, not policy thresholds. Defaulted balances remain eligible before write-off; written-off residual claims remain separate.

All ratios use the same `C`:

| Ratio | Numerator through/at `C` | Denominator |
|---|---|---|
| `f04_principal_repaid_share` | `F` | Original cohort principal `P` |
| `allocated_recovery_principal_share` | `R_p` | `P` |
| `recorded_principal_serviced_share` | `F + R_p` | `P` |
| `recorded_writeoff_principal_share` | `W` | `P` |
| `remaining_principal_share` | `Σ B_i` | `P` |
| `overdue_principal_share` | `Σ B_i` with `DPD_i ≥ 1` | `P` |
| `dpd_30_plus_principal_share` | `Σ B_i` with `DPD_i ≥ 30` | `P` |
| `recorded_default_incidence` | `D` | Original cohort count `N` |

Every zero denominator yields `null`, reason `ZERO_DENOMINATOR`, including empty cohorts. Missing required evidence yields `null`, reason `INCOMPLETE_EVIDENCE`; preserve all applicable reasons. Keep exact integer numerator/denominator pairs when known. Optional percentages round half-up to two decimals.

Never replace originating denominators with surviving, active, defaulted or known-only populations. Default incidence is descriptive command frequency, never estimated probability of default.

### 3.4 `repayment_and_recovery_classification` — ADOPTED

Keep four independently identifiable streams:

| Stream | Treatment |
|---|---|
| Accepted F04 principal repayments | Count principal in `F`; retain operation references |
| Asserted overlay payments | Disclose asserted gross and recorded allocation components separately |
| Pre-write-off recoveries | Preserve gross and `R_d`, `R_i`, `R_p`; components must sum to gross |
| Post-write-off recoveries | Disclose unallocated total `L`; allocation is `null`, reason `UNALLOCATED_BY_POLICY` |

Explicit operation evidence links mirrored overlay/F04 records. Count F04 principal once while retaining the assertion. Never deduplicate by matching amount or day. Unlinked assertions do not reduce principal; unresolved relationships that prevent reconciliation invalidate affected combined metrics.

Consume recorded recovery allocations without replaying a new waterfall. Do not infer allocation from balances or apportion `L`. Missing pre-write-off allocation is incomplete evidence; missing post-write-off allocation is intentional policy.

`W` is not servicing received. `L` neither reduces `W` nor increases `F + R_p`. Disclose recorded residual claims separately where available. Introduce no combined cash, yield or loss ratio.

### 3.5 `terminal_case_retention` — ADOPTED

Closed, defaulted and written-off members remain in `N` and `P`. Zero principal alone does not establish closure; other obligations may remain. Preserve terminal status and residual-obligation evidence separately.

Attach late recoveries to the originating draw without reopening the case or issuing F04 repayment. Retain default incidence after recovery. Missing archived history reduces coverage, never population membership.

This prevents survivor bias but does not make cohorts of different ages or evidence completeness directly comparable.

### 3.6 `unknown_evidence_treatment` — ADOPTED

Every monetary metric exposes `value`, `known_subtotal_krw`, `eligible_draw_count`, `complete_draw_count`, `incomplete_draw_count` and reason codes. Event-derived metrics also expose known/incomplete event counts where determinable; unknown counts remain null.

Completeness requires source-completeness evidence through `C`. An empty complete stream proves zero; an unavailable stream does not. Apply completeness per metric: missing maturity can invalidate delinquency while leaving F04 repayment totals known. Missing principal invalidates principal-weighted ratios without necessarily invalidating draw/default counts. No imputation or known-only replacement ratios are permitted.

Hand-calculated examples use synthetic KRW and `C.sim_day = 180`. Maturity and write-off facts are assumed evidenced inputs, not newly selected terms.

| Draw in `[0,30)` | Day | `P_i` | `F_i` | Recovery `(R_d,R_i,R_p)` | `W_i` | `L_i` | At cut |
|---|---:|---:|---:|---|---:|---:|---|
| A | 0 | 100 | 100 | `(0,0,0)` | 0 | 0 | Closed |
| B | 10 | 200 | 20 | `(5,5,40)` | 140 | 25 | Defaulted, written off |
| C | 29 | 100 | 20 | `(0,0,0)` | 0 | 0 | Maturity day 150 |

Complete evidence gives `N=3`, `P=400`, `F=140`, `R_p=40`, `W=140`, `B=80`. Recovery gross is `5+5+40=50`; unallocated late recovery is 25. Separately linked asserted payments of 150 remain separate, not additional principal servicing.

The eight ratios are respectively `35%`, `10%`, `45%`, `35%`, `20%`, `20%`, `20%` and `1/3 = 33.33%`. C has 30 DPD. Closed A and defaulted B remain in every originating denominator. Adding late recovery would incorrectly produce `(140+40+25)/400=205/400`; this is forbidden.

Remove C’s maturity evidence: overdue and 30+ metrics become null, with two complete draws, one incomplete draw and known overdue subtotal zero. Other evidenced amounts remain unchanged.

Instead remove B’s recovery allocation but retain gross 50: `R_p`, combined servicing and dependent remaining-principal metrics become null. Known recovery-principal subtotal is zero from A/C, with two complete draws and one incomplete draw; `F=140` and gross recovery 50 remain known.

Add legacy U with principal 60 and no draw day: inventory count becomes four, dated `N` remains three, and `UNASSIGNED_DRAW_DAY` contains one draw with known principal 60. An empty requested cohort has `N=P=0`; its ratios are null with `ZERO_DENOMINATOR`.

### 3.7 `report_bounds_and_labels` — ADOPTED

Format is `CAPITAL-VINTAGE-METRICS-V1`. Permit only one local workspace/run `snapshot_ref`, nonnegative `cohort_start_sim_day` divisible by 30, and integer `cohort_count` from 1–12. Width remains 30.

Allow no borrower, status, delinquency or outcome filters. Include empty requested buckets, unassigned-inventory coverage and counts/known principal outside the selected range.

`C` records the snapshot’s current `sim_day`, F04/overlay end positions and available source digests. Sources must describe the same consistent cut. Include accepted records within those positions; later-recorded facts cannot enter an earlier snapshot through backdated effective days. No arbitrary historical cutoff or multi-snapshot migration matrix is offered.

Limit processing to 10,000 accepted draws and 100,000 relevant records across the snapshot. Exceeding either returns `REPORT_LIMIT_EXCEEDED` without truncation. These are resource limits, not lending limits.

Labels: `SIMULATED`, `DESCRIPTIVE_ONLY`, `PROVISIONAL_PRODUCT_DECISION`, `production: NOT_AUTHORIZED`. Queries mutate no clock, journal, case, grant, accounting entry or business digest.

Exclude predictive models, PD/LGD estimates, annualized returns, actual yield, bank-cash claims, booked-loss claims, underwriting calibration, policy recalibration, reserve funding and accounting recognition.

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
      "rationale": "Missing timing remains visible without fabricated membership.",
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
      "rationale": "Preserves allocations and prevents mirrored-payment double counting.",
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
      "rationale": "Terminal status cannot erase servicing history or late facts.",
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
      "rationale": "Known subtotals remain useful without overstating completeness.",
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
      "rationale": "Bounds descriptive reporting without financial execution or prediction.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| Acceptance | Resolution |
|---|---|
| Seven decision items | Exactly seven ADOPTED entries in §4 |
| Cohorts, parameters, legacy timing | §§3.1–3.2, 3.7 |
| Ratios, cuts, zero denominators, terminal examples | §§3.3, 3.5–3.6 |
| Four servicing streams and late allocation | §3.4 |
| Nulls, coverage and known subtotals | §3.6 |
| Ledger and binding checks | Registration omission repaired below; full gate execution remains unverified |

**Revision fix:** seven rows were added to `tests/decision_bindings.json`, each with this decision ID, its exact entry key, this note’s path, `kind: module`, `status: PENDING_CONSUMER`, `consumer_node: vintage-metrics-report` and an explicit implementation-pending reason.

| Entry | Existing module anchor |
|---|---|
| `cohort_membership_and_width` | `capital/portfolio_snapshot.py` |
| `draw_day_evidence` | `capital/portfolio_snapshot.py` |
| `metric_population_and_denominators` | `capital/residuals.py` |
| `repayment_and_recovery_classification` | `capital/residuals.py` |
| `terminal_case_retention` | `capital/residuals.py` |
| `unknown_evidence_treatment` | `capital/residuals.py` |
| `report_bounds_and_labels` | `capital/portfolio_snapshot.py` |

Local validation **passed**: valid JSON, seven unique registrations, no duplicate decision/entry keys, and preservation of all preceding entries. Anchors identify future integration locations, not implemented consumers.

Full decision-ledger and binding checks were **NOT_RUN** because their repository traversal exceeds the explicit read allowlist. Their result remains **UNDETERMINED**; this is not a gate waiver. The blocking registration omission is repaired rather than deferred. No accounting, allowance or release decision was modified.

## 6. Open risks

Implementation mappings, source completeness and F04/overlay linkage remain unverified. Unsupported mappings invalidate dependent metrics. Legacy timing limits dated coverage; cohort ages and selective simulation scenarios prevent statistical or underwriting interpretation. Full integration-check results remain outstanding.

## 7. 후속 작업

The supervisor writes this revised note and carries the seven registry additions into integration, then runs decision-ledger and binding checks. The implementation consumer must reproduce the examples and verify boundaries, duplicates, terminal retention, incomplete evidence, zero denominators and limits before changing binding status to `CONSUMED`.

No vector files were added. Future vectors require documentation registrations and `python3 scripts/docs_surface.py --check`. Preserve existing accounting, allowance, release and upstream-binding decisions.
