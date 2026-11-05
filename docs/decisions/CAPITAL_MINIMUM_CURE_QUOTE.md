# Capital minimum cure quote — minimum repayment for a simulated margin breach

> **PROVISIONAL PRODUCT DECISION**
>
> **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**
>
> Date: **2026-11-05** · Capital main: **`343f425`** · kix-protocol: **`7e75391`**
>
> Simulation/product design only; no real money; production **`NOT_AUTHORIZED`**. No upstream adoption, payment authority, waiver or enforcement authority is granted.
>
> Execution provenance: the attribution and revisions above are supervisor-prescribed. Claude CLI execution, model identity, three failed attempts, fallback execution and checkout revisions were not independently verified.

Node: `cure-quote-scope-decision`. Dependencies: `financial-terms-decision`, `repayment-posting-decision`, `default-recovery-decision`.

`ADOPTED` below means a provisional Capital product decision, not implemented capability. The future consumer is **`minimum-cure-quote`**, registration state **`PENDING`**.

## 1. 결정 요약

| Item | Decision | CAP rows | Consumer |
|---|---|---|---|
| `cure_target_predicate` | Invert the existing margin predicate over integer principal reductions; prove sufficiency and minimality | CAP-01, CAP-04 | `minimum-cure-quote` |
| `new_cash_and_held_cash` | Separate principal reduction, gross repayment resources and additional cash; credit only eligible, unconsumed held cash | CAP-04 | `minimum-cure-quote` |
| `posted_interest_basis` | Use captured unpaid posted dues and the existing repayment waterfall; no hypothetical accrual or posting | CAP-01, CAP-04 | `minimum-cure-quote` |
| `deadline_and_acceleration_boundary` | Include the deadline in advisory eligibility, subject to unchanged command ordering; acceleration is irreversible | CAP-01, CAP-04 | `minimum-cure-quote` |
| `quote_snapshot_binding` | Bind deterministic advisory results to complete captured inputs; revalidate before any existing command | CAP-04, CAP-20 | `minimum-cure-quote` |
| `unsupported_case_handling` | Explicit unavailable, unsupported and refusal results; unknown amounts are null | CAP-04, CAP-20 | `minimum-cure-quote` |

CAP associations describe product scope, not coverage completion.

## 2. KIX 비전 연결

The permitted [Protocol README](/workspace/capital-run/kixproto-ro/README.md) distinguishes local research and mock capabilities from operational financial infrastructure. This decision makes a useful local calculation possible without claiming that its result moves money.

[AUTHORITY_MODEL_1.md](/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md), especially A-4, separates historical evidence from current execution permission. Accordingly, a reproducible quote is neither a payment instruction nor authority to replay a command.

[CAPITAL_DEFAULT_RECOVERY.md](CAPITAL_DEFAULT_RECOVERY.md) §4.1 makes acceleration irreversible; §4.3–4.4 separates post-default recovery from pre-default repayment. Those boundaries remain controlling.

The supplied excerpts of [CAPITAL_REQUIREMENTS_KO.md](../CAPITAL_REQUIREMENTS_KO.md), [SEAMS.md](../SEAMS.md) and [CAPITAL_AGENT_CASE_DISCLOSURE.md](CAPITAL_AGENT_CASE_DISCLOSURE.md) support separate binding states, local simulation labels and nonmutating queries.

**Evidence limit:** the financial-terms and repayment-posting dependency notes were named but excluded from the explicit read allowlist. Their contents were not opened. Exact field mappings, pre-default waterfall details and producer guards are therefore **UNDETERMINED**, with binding value `null`, pending implementation inspection by the supervisor-authorized consumer. This does not reopen their adopted policies: the consumer must load them and reuse their implementation, without substituting literals from this document.

## 3. 항목별 결정

### 3.1 `cure_target_predicate` — ADOPTED

Scope is one identified advance and its current simulated margin call. Let `S` be a consistent captured state, `P` its effective outstanding principal, and `C` the existing margin-sufficiency predicate.

Define `required_principal_reduction_krw`, or `R`, as the smallest integer reduction in `[0, P]` that makes `C` true under the existing repayment projection. Preserve all borrowing-base inputs, eligibility rules, haircuts, thresholds, rounding and treatment of equality. Do not replace the predicate with a newly chosen collateral ratio.

The projection must apply all effects that existing repayment has on the borrowing base. If repayment leaves the base unchanged, a principal-only inversion is sufficient. If it changes the base, use the existing complete projection; an unsupported dependency returns `UNSUPPORTED_CALCULATION`, not an approximation.

The result must demonstrate:

- Sufficiency: the projected state after the quoted allocation satisfies `C`.
- Minimality: for positive `R`, one won less fails, with monotonicity established over the supported domain.
- Bounds: no principal reduction exceeds outstanding principal.

Binary search is permitted only when monotonicity is established. No feasible reduction returns `NO_FEASIBLE_CURE`. A predicate already satisfied returns `R = 0`, labeled `NO_REDUCTION_REQUIRED`; it does not establish that a margin call has been recorded as cured.

This is a margin-cure calculation, not a payoff quote. It introduces no safety buffer, new fee or negotiated reduction.

### 3.2 `new_cash_and_held_cash` — ADOPTED

Return separate quantities:

- `required_principal_reduction_krw`: `R`.
- `posted_interest_due_krw`: `I`, as defined below.
- `gross_repayment_resources_krw`: `G`.
- `held_cash_applied_krw`: `A`.
- `minimum_new_cash_krw`: `N`.

For the supported interest-before-principal waterfall, when `R > 0`:

`G = I + R`; `A = min(H, G)`; `N = G − A`.

Here `H` is eligible held cash at the same snapshot. When `R = 0`, `G = A = N = 0`; outstanding interest remains disclosed and payable under existing rules.

Held cash counts only when recorded evidence establishes that it is attributable to the same advance, remains unconsumed, and may already be applied through the existing repayment rules. Already-applied cash is reflected in principal or dues and cannot be deducted again. Unknown ownership, consumption or applicability makes `H` unknown, not zero.

Observed beneficiary distributions, proposed set-off, expected receipts, wallet balances, another advance’s funds, refund reserves and hypothetical collateral deposits do not qualify merely because they exist. This decision creates no transfer, set-off or cash-release mechanism.

The existing allocation projection must confirm the proposed use of `A`. If it cannot use held cash independently, partially or with zero additional cash, report that command limitation. Do not invent a zero-value payment command.

**Worked examples.** These are synthetic arithmetic fixtures, not term literals. Assume an existing evaluator returns a maximum sufficient principal of 80,000 KRW for these captured inputs, repayment leaves that base unchanged, outstanding principal is 100,000 KRW, and unpaid posted interest is 3,000 KRW. Thus `R = 20,000` and `G = 23,000`.

| Fixture | Eligible held cash `H` | Applied `A` | New cash `N` | Allocation |
|---|---:|---:|---:|---|
| No held cash | 0 | 0 | 23,000 | 3,000 interest; 20,000 principal |
| Partial held cash | 5,000 | 5,000 | 18,000 | Same total allocation |
| Sufficient held cash | 25,000 | 23,000 | 0 | Same allocation; remaining 2,000 follows existing rules |

In the second fixture, 17,999 new cash plus 5,000 held cash pays 3,000 interest and only 19,999 principal: remaining principal is 80,001, so it fails.

If a displayed historical receipt of 5,000 was already fully applied, its eligible remainder is zero. Given the stated current balances, the first fixture applies. The third fixture means no additional cash is arithmetically needed; an existing admissible application and subsequent cure recording may still be necessary.

### 3.3 `posted_interest_basis` — ADOPTED

Use unpaid posted contractual and default-interest dues that the existing pre-default repayment allocator consumes before principal. Preserve their existing priority, allocation and rounding; retain category-level amounts in the explanation.

Do not copy the post-default recovery waterfall into the pre-default repayment path. Do not calculate interest independently from rates, capitalize it, include already-paid dues, or count memo balances unless the existing repayment policy makes them payable here.

Capture fractional carries and posting cutoffs for reproducibility. Unposted accrual is not silently added to `I`, and quoting never posts it. If an existing command requires an intervening interest posting, the quote becomes stale: perform the established workflow separately and quote the resulting state again.

Unsupported senior charges or an unverified waterfall return `UNSUPPORTED_CALCULATION` or `NOT_BOUND`, respectively. A simplified formula must never bypass an inherited obligation.

### 3.4 `deadline_and_acceleration_boundary` — ADOPTED

Use captured integer `sim_day = t` and the margin call’s recorded deadline `D`. Never reconstruct `D` from a copied cure-window constant.

| Captured condition | Quote behavior |
|---|---|
| Active call, `t < D`, no acceleration | Calculate advisory amounts; evaluate existing command admissibility separately |
| Active call, `t = D`, no acceleration | Same arithmetic eligibility, labeled `AT_DEADLINE`; no extra grace or guaranteed execution |
| `t > D`, no acceleration marker yet | `WINDOW_EXPIRED`; cure amounts null; missing acceleration recording does not extend the window |
| Acceleration already recorded, at any day | `ALREADY_ACCELERATED`; cure amounts null |
| Defaulted, written off or otherwise terminal | `TERMINAL_CASE`; cure amounts null |
| No active margin call | `NO_ACTIVE_MARGIN_CALL`; cure amounts null |

Inclusive deadline eligibility does not reorder commands. Any existing tick, posting, repayment or margin-evaluation ordering remains authoritative. If that ordering accelerates or refuses the proposed repayment before it could cure, report the refusal; do not backdate repayment, suppress the tick or defer acceleration.

For a synthetic deadline of day 25, day 24 is before-deadline, day 25 is the inclusive boundary, and day 26 is expired. An acceleration marker on any of those snapshots takes precedence.

Existing accelerated maturity, interest rebase and default eligibility remain unchanged. Late repayment may reduce debt under an existing path, but this quote cannot reverse acceleration or reopen a terminal case.

### 3.5 `quote_snapshot_binding` — ADOPTED

The response is a pure read. It creates no journal entry, reservation, proposal, posting, grant, clock change or persisted cure marker.

Capture the subject identifiers; principal; full borrowing-base inputs; margin-call identity, state and deadline; logical day; acceleration and terminal markers; posted dues and carry state; held-cash source and consumption references; relevant journal cuts; policy-note digests; evaluator version; and producer identity and capabilities.

Use a deterministic, versioned local SHA256 digest of these canonical inputs and the result. It is a diagnostic identifier, not a signature, receipt, authenticated identity or upstream wire contract.

Expose three independent conclusions:

1. `arithmetic_sufficient`: whether the projected allocation satisfies the margin predicate.
2. `command_admissibility`: `ADMISSIBLE_AT_SNAPSHOT`, `REFUSED` or `UNKNOWN`, with reasons.
3. `recorded_cure`: the existing recorded state, never synthesized from the quote.

Every response carries `SIMULATED`, `provisional: true`, `advisory: true` and `executionAuthorized: false`.

Before an existing command, recapture and compare all relevant inputs and re-run its normal validation. Changed cash, dues, collateral, time, policy, producer or capacity invalidates the old quote. There is no wall-clock validity promise or liquidity reservation. A successful command still requires the existing cure-recording rules to establish cure.

### 3.6 `unsupported_case_handling` — ADOPTED

| Condition | Required outcome |
|---|---|
| Missing required evidence or policy binding | `NOT_BOUND`, missing-field reasons, affected amounts null |
| Conflicting balances, invalid monetary types or inconsistent cuts | `INVALID_INPUT`, no cure quote |
| Unsupported producer or unavailable reliable repayment projection | `UNSUPPORTED_PRODUCER`, cure amounts null |
| Unsupported arithmetic coupling or waterfall | `UNSUPPORTED_CALCULATION`, cure amounts null |
| Command-capacity limit or ordinary command guard refuses | Preserve independently established arithmetic; `command_admissibility: REFUSED` with original reason |
| Admissibility cannot be evaluated without mutation | `command_admissibility: UNKNOWN`; never label executable |
| No sufficient amount within existing repayment bounds | `NO_FEASIBLE_CURE`, cure amounts null |
| Snapshot changed | `STALE_QUOTE`; obtain a fresh quote |

Unknown values must never become zero. Refusals must not trigger retries, command splitting, alternative producers or hidden state changes.

Collateral substitution, cash-margin deposits, collateral top-ups, new repayment commands, waivers, deadline extensions, accelerated payoff advice and real collection are excluded. Existing recovery authority is untouched.

## 4. Machine-readable decision

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "cure-quote-scope-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-11-05",
  "provisional": true,
  "entries": {
    "cure_target_predicate": {
      "status": "ADOPTED",
      "value": {
        "mode": "MINIMUM_INTEGER_REDUCTION_USING_EXISTING_MARGIN_PREDICATE",
        "preserve": ["borrowing_base", "thresholds", "rounding", "repayment_effects"],
        "proof": ["sufficiency", "minimality", "principal_bounds"],
        "consumer": "minimum-cure-quote",
        "consumer_state": "PENDING"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-05",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Invert established rules without introducing financial terms.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "new_cash_and_held_cash": {
      "status": "ADOPTED",
      "value": {
        "held_cash": "PROVEN_ELIGIBLE_UNCONSUMED_SAME_ADVANCE_ONLY",
        "positive_reduction": "G=I+R; A=min(H,G); N=G-A",
        "zero_reduction": "G=A=N=0",
        "allocation_validation": "EXISTING_REPAYMENT_PROJECTION_REQUIRED",
        "unknown_held_cash": "NULL_NOT_ZERO",
        "new_cash_zero": "NO_NEW_COMMAND_OR_CURE_IMPLIED"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-05",
      "cap_rows": ["CAP-04"],
      "rationale": "Distinguish principal reduction from additional cash without double counting receipts.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "posted_interest_basis": {
      "status": "ADOPTED",
      "value": {
        "source": "CAPTURED_UNPAID_POSTED_DUES",
        "waterfall": "EXISTING_PRE_DEFAULT_REPAYMENT_RULES",
        "quote_posts_interest": false,
        "unposted_accrual": "EXCLUDED_FROM_POSTED_DUES",
        "required_intervening_posting": "INVALIDATE_AND_REQUOTE",
        "unverified_mapping": "NOT_BOUND"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-05",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Use established posted obligations without inventing accrual or allocation behavior.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "deadline_and_acceleration_boundary": {
      "status": "ADOPTED",
      "value": {
        "before_deadline": "ADVISORY_ELIGIBLE_SUBJECT_TO_EXISTING_GUARDS",
        "inclusive_deadline": "AT_DEADLINE_EXISTING_COMMAND_ORDER_CONTROLS",
        "after_deadline": "WINDOW_EXPIRED_NULL_CURE_AMOUNTS",
        "accelerated": "ALREADY_ACCELERATED_NULL_CURE_AMOUNTS",
        "terminal": "TERMINAL_CASE_NULL_CURE_AMOUNTS",
        "acceleration_reversal": false,
        "deadline_extension": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-05",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Explain deadline arithmetic while preserving command ordering and irreversible acceleration.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "quote_snapshot_binding": {
      "status": "ADOPTED",
      "value": {
        "mode": "READ_ONLY_CAPTURED_INPUT_ADVISORY",
        "identity": "VERSIONED_LOCAL_CANONICAL_SHA256",
        "separate": ["arithmetic_sufficient", "command_admissibility", "recorded_cure"],
        "revalidation": "RECAPTURE_COMPARE_AND_RUN_EXISTING_GUARDS",
        "mutation": false,
        "executionAuthorized": false,
        "reservation": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-05",
      "cap_rows": ["CAP-04", "CAP-20"],
      "rationale": "Make calculations reproducible without presenting evidence as execution authority.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "unsupported_case_handling": {
      "status": "ADOPTED",
      "value": {
        "missing_evidence": "NOT_BOUND",
        "invalid_evidence": "INVALID_INPUT",
        "unsupported_producer": "UNSUPPORTED_PRODUCER",
        "unsupported_calculation": "UNSUPPORTED_CALCULATION",
        "capacity_refusal": "RETAIN_VALID_ARITHMETIC_MARK_COMMAND_REFUSED",
        "unknown_admissibility": "UNKNOWN",
        "infeasible": "NO_FEASIBLE_CURE",
        "changed_snapshot": "STALE_QUOTE",
        "unavailable_amount": null,
        "automatic_workarounds": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-05",
      "cap_rows": ["CAP-04", "CAP-20"],
      "rationale": "Expose evidence and command limitations without fabricating cash, authority or successful cure.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| Acceptance | Decision / required verification |
|---|---|
| Six decided items | Six `ADOPTED` entries above |
| Principal versus new cash | §3.2 examples, interest allocation and one-won failure |
| Deadline boundaries | §3.4; test before, equal, after and already accelerated |
| Advisory versus execution and cure | §3.5; verify query nonmutation and stale-input rejection |
| Missing evidence and refusals | §3.6; test null amounts, producer rejection and capacity refusal |
| Ledger and binding integration | Register all six entries to the pending consumer; execute repository checks after integration |

## 6. Open risks

Exact dependency field mappings and producer ordering remain unverified because the allowed pack omits their authoritative contents. The future consumer must resolve these bindings from existing policy, not invent replacements. Legal effect of held-cash application remains a working assumption pending professional review.

No files were changed and no repository validation was executed. Decision-ledger, binding and documentation-surface checks are **NOT_RUN**, not passed.

## 7. 후속 작업

The supervisor writes this note and registers `cure-quote-scope-decision`, its six item identifiers, CAP associations and consumer `minimum-cure-quote` in the existing decision index and binding registry. The consumer remains **`PENDING`**; implementation and upstream adoption remain false.

The consumer then binds inherited policies, implements the pure calculation and existing-command preflight, and verifies minimality, held-cash conservation, deadline ordering, acceleration precedence and nonmutation. Run the repository’s decision-ledger and binding checks. If vectors are added, update their hand-maintained documentation registrations and run `python3 scripts/docs_surface.py --check`.

Integration checks and implementation evidence are separate deliverables; this decision does not claim their completion.
