# Capital servicing calendar — logical-day deadlines and eligibility boundaries

> **PROVISIONAL PRODUCT DECISION** · `servicing-calendar-decision` · **2026-11-27**
>
> **Prescribed decision attribution** — Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07).
>
> **Execution provenance** — Three noninteractive Sonnet CLI attempts and the Fable fallback each returned `Not logged in`. Codex completed this decision from the permitted evidence. The attribution fields below reproduce the supervisor’s mandate.
>
> **Supervisor-supplied bases** — KIX-CAPITAL main `bfd5e69` · kix-protocol `212d4c0`. Local simulation and product design only. No real money. Production `NOT_AUTHORIZED`. Accounting, tax and legal assumptions remain pending professional review.

## 1. 결정 요약

Adopt a read-only agenda evaluated at the recorded simulation day. It may tell an operator, “The default eligibility boundary was day 36.” Only an accepted, dated default record can establish, “Default was recorded on day 42.” That distinction determines both the writeoff boundary and the interest-stop day.

| Item | Decision | CAP rows | Pending consumer |
|---|---|---|---|
| `agenda_event_catalog` | Admit six boundary kinds. Attach command dates only as supporting evidence. | CAP-01, CAP-04, CAP-13 | `servicing-deadline-agenda` |
| `recorded_anchor_precedence` | Use same-advance records at one replay cut, then apply existing policy to those records. | CAP-01, CAP-04, CAP-20 | `servicing-deadline-agenda` |
| `boundary_and_same_day_order` | Include the last cure day and first eligible day. Exclude the interest-stop day. Preserve journal order. | CAP-01, CAP-04, CAP-13 | `servicing-deadline-agenda` |
| `conditional_event_labels` | Show how the date is known and what becomes true on that date. | CAP-04, CAP-20 | `servicing-deadline-agenda` |
| `missing_evidence_behavior` | Return a null date with a reason for an applicable boundary lacking evidence. | CAP-04, CAP-20 | `servicing-deadline-agenda` |
| `agenda_horizon_bounds` | Default to 30 days ahead, allow up to 366, and return at most 128 rows in total. | CAP-04, CAP-20 | `servicing-deadline-agenda` |

## 2. KIX 비전 연결

KIX authority model A-4 preserves the source position of an accepted fact and requires separate authority for execution. The agenda applies that principle to servicing. Replaying an advance can explain when an operator could have acted. Only the command record establishes when the operator acted. Protocol’s local mock scope applies throughout. [Authority model A-4](/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md) · [KIX Protocol README, §3](/workspace/capital-run/kixproto-ro/README.md)

Capital’s recovery decision supplies the maturity rebase, default-command anchor and exclusive accrual cutoff. It also identifies an assumption-based pre-default writeoff rollup. The agenda consumes those distinctions within the local simulation seam. `CAPITAL-TERMS-V1` field references below come through the recovery decision. The financial-terms note itself was outside the permitted read list. [Capital default recovery, §§2, 4.1–4.2 and 4.7](CAPITAL_DEFAULT_RECOVERY.md) · [Capital seams](../SEAMS.md)

## 3. 항목별 결정

### `agenda_event_catalog`

Use integer `sim_day` throughout. Let `M` be effective maturity, `C` the cure deadline, `G` the adopted `term.grace_days_after_maturity`, `D` the recorded default-command day and `L` the adopted `default_loss_treatment.writeoff_days_after_default`. Resolve terms applicable to the advance. The example numbers below are fixture inputs.

| Agenda kind | Authoritative date | Meaning |
|---|---|---|
| `CURE_DEADLINE` | The recorded call’s `cure_deadline_sim_day`, or its recorded `margin_call_sim_day` plus the applicable `additional_margin.cure_window_days` | Last day on which the existing cure rule can be satisfied for that call. |
| `MATURITY` | Current contractual maturity supported by the advance’s records, or recorded draw day plus its applicable tenor. Apply any established acceleration rebase. | Effective maturity day, inclusive of the ordinary-rate period while accrual continues. |
| `DEFAULT_INTEREST_FROM` | `M + 1` | First day the existing late-interest rule can apply to outstanding principal. |
| `DEFAULT_ELIGIBLE` | `E = M + G + 1` | First day the time condition for default is met if an eligible exposure remains. |
| `INTEREST_STOP` | Earlier of an applicable recorded full-close day and `W = D + L`. Either established endpoint suffices when the other does not apply. | First day excluded from accrual. A writeoff posted later cannot extend accrual. |
| `WRITEOFF_ELIGIBLE` | `W = D + L`, using the overlay day attached to the accepted FSM default for this advance | First day the writeoff time condition is met. Posting still requires the existing state, balance, waterfall evidence and operator authority. |

Draw, cure satisfaction, acceleration, default, close and writeoff posting may appear as cited facts on a row. The catalog has no scheduled-command event. An agenda read grants no authority for repayment, default, recovery or writeoff.

### `recorded_anchor_precedence`

Evaluate the current recorded clock, FSM state and overlay at one consistent journal cut. Identify the advance and the source entry or replay position for each anchor. A derived date also carries its rule and applicable terms reference. A recorded day zero is valid. A missing draw day has no numeric value.

For an established uncured margin call, the acceleration anchor is `C`. For an established insolvency notice or evidence-fraud finding, it is the operator-recorded event day. Fold established anchors as `min(current maturity, anchor)`. A still-open cure window may carry an *if uncured* explanation. Its deadline alone cannot replace current maturity. An assumption-based rollup loses to supported overlay dates even when both produce the same number.

In particular, the recovery rollup may show `earliest_writeoff_sim_day = E + L` before default. The agenda excludes that estimate from its dated rows. A `DEFAULTED` state, a clock reading, a journal ordinal and the passage of `E` are each insufficient to establish `D`. A dated entry for the accepted default is the authority.

### `boundary_and_same_day_order`

Fold accepted records in their existing order before evaluating any boundary. Day `C` remains available for a qualifying cure. On a recorded day strictly after `C`, an unresolved call can establish uncured acceleration under the existing fold, with maturity anchored at `C`. A clock jump across the deadline creates no intervening repayment, cure or command. An accepted late partial repayment can reduce the balance while accelerated maturity stays fixed.

Day `M` is the last ordinary-rate day if accrual is still open. Grace runs through `M + G` inclusive. Day `E` opens the default time gate. Existing repayment and default rules govern which commands may succeed that day. If a full repayment has already closed the advance at the selected cut, suppress the default opportunity. Preserve the recorded order when two commands share a day.

Accrual includes the draw day and excludes its endpoint. Following a recorded default, the existing memo-accrual period includes `D` and excludes `W`, subject to earlier closure. At `W`, the interest stop takes effect even if the operator posts the writeoff later. For display ties, use the catalog order above. This places `INTEREST_STOP` before `WRITEOFF_ELIGIBLE` on their shared day. Display rank has no role in replay.

### `conditional_event_labels`

Give every row a `date_basis` and a `meaning`. `RECORDED` identifies a day carried by the cited record. `POLICY_FROM_RECORDS` identifies arithmetic on cited anchors. `UNAVAILABLE` carries a null day and a reason. A stored cure deadline, for example, proves the date assigned to that call. It says nothing about whether a cure will occur.

Use `RECORDED_BOUNDARY` for a boundary expressly recorded as such, `CONDITIONAL_BOUNDARY` for an outstanding or future threshold whose consequence depends on the case, and `EFFECTIVE_BOUNDARY` when the current fold establishes the consequence. A reached default gate can still be conditional. A reached interest cutoff with recorded `D` takes effect regardless of posting delay. Each conditional row states its predicate. Each result carries `SIMULATED`, `provisional=true` and `execution_authorized=false`.

### `missing_evidence_behavior`

When an applicable date cannot be supported, return `sim_day=null` and a specific reason such as `DRAW_DAY_UNKNOWN`, `TERMS_UNAVAILABLE`, `ANCHOR_CONFLICT` or `DEFAULT_DAY_UNKNOWN`. Before default, the writeoff-based dates are unavailable because `DEFAULT_NOT_RECORDED`. After an evidenced but undated default, use `DEFAULT_DAY_UNKNOWN`. Keep independently supported rows. A disagreement between two authoritative records for the same fact affects its dependants. A difference from an assumption-based rollup does not invalidate a recorded anchor.

Omit extinguished obligations. A fully repaid advance has no prospective cure or default opportunity. A defaulted advance can still have interest-stop and writeoff boundaries. A recorded writeoff retires the writeoff opportunity. Later residual recovery creates no new accrual or servicing deadline.

| Worked case | Expected agenda result |
|---|---|
| Normal maturity | A recorded draw on day 12 with a 60-day tenor gives `M=72`. With 10 grace days, late interest can start on 73, grace includes 82, and `E=83`. A day-zero rollup giving maturity 60 supplies no agenda date. |
| Timely cure | Draw on 0, maturity 60, call on 20, deadline 25. A qualifying repayment recorded on 25 satisfies the call under the existing cure rule. Retire its deadline and retain maturity 60. |
| Irreversible acceleration | With the same call unresolved on day 26, effective maturity becomes 25. Late interest starts on 26 and `E=36`. A partial repayment on 27 does not restore maturity 60. |
| Delayed default recording | `E=36` passes with no command. `D` and `W` are unavailable. An accepted default on 42 establishes `D=42`. With a 90-day wait, `W=132`. Memo accrual includes 131 and excludes 132. The rollup’s 126 never becomes the stop day. |
| Terminal cases | Full repayment on day 55 establishes an exclusive stop at 55 and retires prospective servicing rows. In the delayed-default case, a writeoff posted on 140 retains effective day 132. Later residual recovery does not reopen the case. |

### `agenda_horizon_bounds`

Start at recorded day `S`. Accept an integer lookahead `H` from 0 through 366, default 30. Include both ends of `[S, S+H]`. Zero requests today only. Reject invalid lookaheads. If `S` is unavailable, return an unavailable agenda with `CLOCK_DAY_UNKNOWN`.

Include an earlier, still-outstanding maturity or open eligibility gate once as `OPEN_AT_START`, preserving its original day. Sort dated rows by day, catalog rank, advance ID and source identity. Put unavailable rows last in the same deterministic rank and identity order. Cap the combined result at 128 rows, including carry-ins and unavailable rows. Report `truncated` and the exact `omitted_count` after filtering and ordering. These limits govern display only. The read never advances a clock, schedules work or maps logical days to wall-clock deadlines.

## 4. 결정 레코드

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "servicing-calendar-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-11-27",
  "provisional": true,
  "pending_consumer": "servicing-deadline-agenda",
  "entries": {
    "agenda_event_catalog": {
      "status": "ADOPTED",
      "value": {"kinds": ["CURE_DEADLINE", "MATURITY", "DEFAULT_INTEREST_FROM", "DEFAULT_ELIGIBLE", "INTEREST_STOP", "WRITEOFF_ELIGIBLE"], "default_command_day": "recorded anchor only"},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-27", "cap_rows": ["CAP-01", "CAP-04", "CAP-13"],
      "rationale": "Each admitted boundary has an identifiable servicing rule and date source.",
      "provisional": true, "basis": "PRODUCT_DECISION"
    },
    "recorded_anchor_precedence": {
      "status": "ADOPTED",
      "value": {"cut": "same advance, consistent FSM and overlay cut", "sources": ["accepted dated records", "policy derivation from those records"], "rollup_fallback": false, "default_day_source": "overlay day of accepted default command"},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-27", "cap_rows": ["CAP-01", "CAP-04", "CAP-20"],
      "rationale": "Only the accepted command record can date an operator's default action.",
      "provisional": true, "basis": "PRODUCT_DECISION"
    },
    "boundary_and_same_day_order": {
      "status": "ADOPTED",
      "value": {"cure": "through C inclusive", "late_interest": "M+1", "default_eligible": "M+G+1 inclusive", "writeoff_eligible": "D+L inclusive", "accrual_end": "earliest applicable close or W, exclusive", "state_order": "existing journal replay", "display_rank": ["CURE_DEADLINE", "MATURITY", "DEFAULT_INTEREST_FROM", "DEFAULT_ELIGIBLE", "INTEREST_STOP", "WRITEOFF_ELIGIBLE"]},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-27", "cap_rows": ["CAP-01", "CAP-04", "CAP-13"],
      "rationale": "Replay resolves same-day commands. Display order makes the exclusive stop visible on the first writeoff-eligible day.",
      "provisional": true, "basis": "PRODUCT_DECISION"
    },
    "conditional_event_labels": {
      "status": "ADOPTED",
      "value": {"date_basis": ["RECORDED", "POLICY_FROM_RECORDS", "UNAVAILABLE"], "meaning": ["RECORDED_BOUNDARY", "CONDITIONAL_BOUNDARY", "EFFECTIVE_BOUNDARY", "UNAVAILABLE"], "execution_authorized": false},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-27", "cap_rows": ["CAP-04", "CAP-20"],
      "rationale": "A threshold can have an exact date while its business outcome remains conditional.",
      "provisional": true, "basis": "PRODUCT_DECISION"
    },
    "missing_evidence_behavior": {
      "status": "ADOPTED",
      "value": {"unavailable_day": null, "require_reason": true, "default_day_fallback": "NONE", "known_inapplicable": "omit", "terminal": "suppress extinguished obligations"},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-27", "cap_rows": ["CAP-04", "CAP-20"],
      "rationale": "A missing anchor invalidates the dates that depend on it while preserving independent evidence.",
      "provisional": true, "basis": "PRODUCT_DECISION"
    },
    "agenda_horizon_bounds": {
      "status": "ADOPTED",
      "value": {"start": "recorded S", "end_inclusive": "S+H", "default_horizon_days": 30, "min_horizon_days": 0, "max_horizon_days": 366, "max_rows_total": 128, "include_open_carry_ins": true, "overflow": ["truncated", "omitted_count"]},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-27", "cap_rows": ["CAP-04", "CAP-20"],
      "rationale": "A bounded view can retain outstanding gates and disclose exactly how many rows were omitted.",
      "provisional": true, "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

The catalog identifies the source of every dated row. The ordering rule fixes endpoint inclusivity and delegates same-day command outcomes to replay. The five worked cases cover ordinary maturity, cure on the deadline, irreversible acceleration, delayed default and terminal handling. The machine record assigns all six decisions to one pending consumer.

## 6. Open risks

Historical advances may have a terminal FSM state without a dated overlay anchor. For those advances the affected dates remain `UNAVAILABLE`. A rollup displayed alongside the agenda must retain its assumption label, particularly where it gives an earlier interest-stop day.

## 7. 후속 작업

`servicing-deadline-agenda` owns the pending read-only implementation. Verify the five cases against existing replay, including a jump over the cure deadline, an undated legacy default, a zero-day horizon and a 129-row result with exactly one omission. Repeated reads at the same cut must return identical rows and preserve clock and journal state. New financial terms, extensions, waivers, scheduling commands and calendar integrations are outside this decision.
