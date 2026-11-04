# Capital UC3 Hold Clock — Temporal Handling of Late Cash in Disposable Shadow Replays

> **PROVISIONAL PRODUCT DECISION**
>
> **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**
>
> Date: **2026-11-04** · Capital main: **`9510843`** · kix-protocol: **`bbf55e5`**
>
> Simulation/product design only; no real money; production **`NOT_AUTHORIZED`**. No upstream contract, authentication mechanism or execution authority is adopted.
>
> Execution provenance: the attribution above is supervisor-prescribed. Claude CLI execution, three failed attempts and Fable takeover were not verified and are not claimed. Revision identifiers are supervisor-supplied bases, not independently verified checkouts.

Node: `uc3-hold-clock-decision`. Dependencies: `settlement-policy-decision`, `shadow-policy-decision`, `shadow-participation-slice-uc`, `sim-clock-ledger`.

This document authorizes a disposable, in-memory UC3 evaluation and explicit operator-disposition proposals. It changes neither the UC1–UC4 partition nor financial terms. `ADOPTED` means a provisional Capital product decision, not implementation or upstream adoption.

## 1. 결정 요약

| Item | Decision | CAP rows | Consumer |
|---|---|---|---|
| `hold_start_anchor` | Each arrival tranche starts its own existing 180-day hold on its synthetic arrival day | CAP-04 | Disposable UC3 evaluator |
| `arrival_tranche_identity` | One claim; scoped tranche identity with a unique synthetic source-fact reference | CAP-04, CAP-20 | Replay input validator |
| `eligibility_day_boundary` | Eligible at `arrival_sim_day + 180`, inclusive; cash remains held | CAP-04 | Logical-clock projection |
| `duplicate_and_conflicting_inputs` | Collapse exact duplicates; reject contradictory snapshots; canonical ordering | CAP-11, CAP-20 | Replay validator and fold |
| `operator_disposition_proposal` | Explicit operator request produces a snapshot-bound proposal with no financial effect | CAP-04, CAP-20 | Disposable proposal projector |
| `replay_capacity_bounds` | One claim, 64 unique tranches, 256 raw arrivals and 64 proposal requests | CAP-11, CAP-20 | Replay admission gate |

CAP associations describe intended product coverage, not completed capabilities. Consumer labels identify responsibilities rather than existing implementation names.

## 2. KIX 비전 연결

The read-only sources used are:

- `/workspace/capital-run/kixproto-ro/README.md`, §§1–4: protocol development and local simulation do not establish operational readiness or real payment authority.
- `/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md`, A-4: replay preserves historical meaning without granting fresh external execution; late facts must not disappear at a cutoff.
- `docs/decisions/CAPITAL_DEFAULT_RECOVERY.md`, §§4.6–4.8: late recovery does not reopen an advance, and time-based eligibility remains separate from operator action. Its recovery postings and financial terms are not imported into UC3.
- Supervisor excerpts of `docs/CAPITAL_REQUIREMENTS_KO.md` and `docs/SEAMS.md`: local simulated gates do not establish semantic conformance, production identity or upstream binding.
- Supervisor excerpt of `docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md`: accounting, tax, legal and retention positions remain working assumptions pending professional review.
- Supervisor excerpt of `docs/decisions/CAPITAL_AGENT_CASE_DISCLOSURE.md`: disclosure and local tools do not establish real authentication or execution authority.

The product ambition is reproducible handling of delayed evidence: the same scenario, cash facts and logical day produce the same eligibility and proposals, while preserving the authority boundary.

**Evidence limitation.** The supervisor names `CAPITAL_SETTLEMENT_POLICY.md` and `CAPITAL_SHADOW_POLICY.md` as binding predecessors, but excludes their paths from the explicit read allowlist and supplies no contents. They were not opened. The existing 180-day duration and unchanged UC partition are accepted from the supervisor’s instruction. Exact predecessor field paths, receipt digests and clock-adapter interfaces are **UNDETERMINED**, with `value: null`, because they are absent from the permitted evidence. This does not reopen their decided policy.

## 3. 항목별 결정

### 3.1 `hold_start_anchor` — ADOPTED

The hold starts separately for each tranche at its immutable `arrival_sim_day`: the logical day on which that synthetic cash arrival occurred in the scenario. It is not the day the evaluator first sees the record.

For tranche `t`:

`eligible_sim_day(t) = arrival_sim_day(t) + hold_days`

`hold_days` remains **180**, as already decided and explicitly preserved by this node. A downstream adapter must load that duration from the adopted predecessor policy through its actual schema. The number here documents the invariant and supports examples; it is not permission to create a competing runtime terms constant.

Claim creation, advance closure, first arrival, latest arrival, replay execution and proposal creation do not replace this anchor. A later tranche receives its own full hold. It neither inherits an older tranche’s eligibility nor extends an older tranche’s hold.

This prevents both premature eligibility for fresh cash and indefinite extensions of older holds. Arrival tranches represent cash facts only; they create no investment tranche, ownership priority or new participation right.

UC3 membership must come from the unchanged predecessor classification. This evaluator accepts only a scenario classified as UC3; it does not infer UC3 from age or redefine UC1, UC2 or UC4.

### 3.2 `arrival_tranche_identity` — ADOPTED

One replay contains one `scenario_id` and one synthetic `claim_id`. Its closed arrival record has:

- `tranche_id`
- `source_fact_id`
- `arrival_sim_day`
- `amount_krw`
- `currency`, exactly `KRW`

Scenario and claim identifiers are inherited from the replay envelope. Every identifier is case-sensitive ASCII matching `[A-Za-z0-9_-]{1,64}`; no trimming, case folding or alias expansion is permitted.

The full tranche key is `(scenario_id, claim_id, tranche_id)`. Within that scope, tranche IDs and source-fact IDs must have a one-to-one relationship. One source fact cannot be counted under two tranche IDs, and one tranche cannot name two source facts.

`source_fact_id` is fixture-local evidence identity, not a provider event ID, authenticated receipt or adopted wire identifier. Distinct tranches may legitimately share an amount and arrival day. They remain distinct only when their identities and source-fact references differ.

Amounts are positive integer synthetic KRW. Zero, negative, fractional, boolean and string amounts are rejected. Corrections do not overwrite accepted facts inside a replay. A corrected scenario is evaluated as a new disposable snapshot, with the original result distinguishable by its snapshot digest.

No rights allocation, recovery waterfall, interest calculation or financial cap is introduced.

### 3.3 `eligibility_day_boundary` — ADOPTED

The only time input is an explicit nonnegative integer `as_of_sim_day`. Wall-clock time, timezone, timestamps, business calendars and elapsed process time have no effect.

For each valid tranche:

- `as_of_sim_day < eligible_sim_day`: `HELD_INELIGIBLE`.
- `as_of_sim_day >= eligible_sim_day`: `HELD_ELIGIBLE_FOR_PROPOSAL`.

The arrival day has age zero. Thus a day-10 arrival reaches age 180 on day 190. The hold interval is `[10, 190)`; eligibility begins at day 190, inclusive.

Example: tranche A arrives on day 10 for 100 synthetic KRW; tranche B arrives on day 189 for 40. Their eligibility days are 190 and 369.

| Evaluation day | A | B | Total held | Eligible held |
|---:|---|---|---:|---:|
| 189 | Ineligible | Ineligible | 140 | 0 |
| 190 | Eligible for proposal | Ineligible | 140 | 100 |
| 191 | Eligible for proposal | Ineligible | 140 | 100 |
| 368 | Eligible for proposal | Ineligible | 140 | 100 |
| 369 | Eligible for proposal | Eligible for proposal | 140 | 140 |
| 370 | Eligible for proposal | Eligible for proposal | 140 | 140 |

If tranche C arrives on day 190, it is ineligible that day and becomes eligible on day 370. A’s eligibility remains unchanged.

Eligible cash is a subset of held cash, never an additional balance. The total held amount does not fall at eligibility. A direct evaluation at day 370 must match the result of evaluating successive days, absent input changes. Advancing time creates no release, payout, return, posting or reopened advance.

### 3.4 `duplicate_and_conflicting_inputs` — ADOPTED

Validate the complete bounded snapshot before producing totals or proposals.

Exact duplicates have the same scoped tranche key and all five validated record fields equal. They collapse to one economic fact. JSON property order is irrelevant; invalid types are rejected before comparison.

Any of the following rejects the **entire snapshot**, without a usable financial projection or proposals:

- Same tranche key with different amount, day, currency or source-fact ID.
- Same source-fact ID under different tranche IDs.
- Unknown fields, malformed identifiers or invalid numeric types.
- A second claim or an arrival after `as_of_sim_day`.
- Capacity or arithmetic limits exceeded.

There is no first-wins, last-wins or partial-success rule. Conflict diagnostics identify offending keys in lexical order without selecting a preferred record.

After validation and deduplication, fold arrivals by `(arrival_sim_day, tranche_id)`, ascending, using ASCII lexical order for ties. Evaluate eligibility after incorporating every arrival in the snapshot, then evaluate operator requests. Input delivery order cannot change results.

Boundary examples:

| Input | Result |
|---|---|
| A duplicated exactly at day 189 | Count 100 once; ineligible |
| A duplicated exactly at day 190 | Count 100 once; eligible |
| A duplicated exactly at day 191 | Count 100 once; eligible |
| A repeated with amount 101 at any of those days | Reject entire snapshot |
| Day-10 A first supplied in a day-191 replay | Eligible using day 10; retain its original anchor |
| A and B supplied in reverse order | Same normalized facts and result |
| Day-190 C supplied to a day-189 replay | Reject future arrival |

Late delivery is handled by constructing a new complete disposable snapshot. It does not mutate an earlier result or backdate an executed instruction. Within an interactive replay, logical time may only advance; an earlier-day comparison requires a separate disposable evaluation.

### 3.5 `operator_disposition_proposal` — ADOPTED

Eligibility alone creates no proposal. An explicit synthetic operator request may select whole tranches and one of two actions:

- `CONTINUE_HOLD`: record an operator’s proposed continued hold; does not reset the anchor.
- `REVIEW_ELIGIBLE_HELD_CASH`: request disposition review; every selected tranche must be eligible at that snapshot.

Each request contains `proposal_id`, `operator_label`, `action` and a nonempty selection of distinct tranche IDs. Identifiers follow §3.2. Selections are sorted canonically. Exact repeated requests collapse; a reused proposal ID with different content rejects the snapshot. Invalid selections or premature review requests also reject it.

The output includes selected identities, their full amounts and eligibility days, the as-of day, policy references, snapshot digest, `status: PROPOSED_ONLY`, `label: SIMULATED` and `executionAuthorized: false`. `operator_label` is attribution within a fixture, not authenticated identity.

The snapshot digest covers the normalized scenario, source facts, as-of day and policy identifiers/digests; it excludes proposals to avoid circularity. Use full SHA256 over UTF-8 JSON with sorted object keys, compact separators, ASCII strings, integer values and the canonical array order specified here. Any changed input invalidates the old proposal’s applicability.

Multiple proposals are independent alternatives. Their amounts must not be summed as reservations or disbursements. No proposal consumes a tranche or changes held totals. On day 189, review of A fails; at days 190 and 191 it may produce a proposal, while A remains held.

Neither an operator label nor a later approval field can convert this artifact into execution. Actual disposition and its authority require a separate binding outside this decision.

### 3.6 `replay_capacity_bounds` — ADOPTED

V1 admission limits are:

| Dimension | Bound |
|---|---:|
| Synthetic claims | Exactly 1 |
| Raw arrival records, including duplicates | 256 |
| Unique arrival tranches | 64 |
| Raw operator proposal requests, including duplicates | 64 |
| Logical day range | 0–1,000,000 inclusive |
| Identifier length | 1–64 ASCII bytes |
| Each amount and aggregate held amount | At most 9,007,199,254,740,991 synthetic KRW |

Derived eligibility days must also fit the day range. Arithmetic uses exact integers, with bounds checked before emitting results. The amount ceiling is a representation limit, not a lending, settlement or participation cap.

Exceeding any bound rejects the whole snapshot. There is no eviction of older facts, truncation, rolling window or automatic splitting to make a scenario fit. Capacity rejection does not declare omitted cash absent or extinguish any obligation.

These bounds authorize finite disposable evaluation independently of provider-capture recording and participation-window implementation. They define no durable retention period or workspace storage contract.

## 4. Machine-readable decision

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "uc3-hold-clock-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-11-04",
  "provisional": true,
  "entries": {
    "hold_start_anchor": {
      "status": "ADOPTED",
      "value": {
        "anchor": "EACH_TRANCHE_ARRIVAL_SIM_DAY",
        "hold_days": 180,
        "duration_authority": "SUPERVISOR_STATED_EXISTING_SHADOW_POLICY",
        "later_arrivals": "INDEPENDENT_ANCHOR",
        "reset_existing_anchor": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-04"],
      "rationale": "Each later arrival receives the existing full hold without extending earlier tranches.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "arrival_tranche_identity": {
      "status": "ADOPTED",
      "value": {
        "scope": ["scenario_id", "claim_id"],
        "key": "tranche_id",
        "source_identity": "source_fact_id",
        "identity_relation": "BIJECTION",
        "currency": "KRW",
        "amount": "POSITIVE_INTEGER",
        "provider_identity_adopted": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-04", "CAP-20"],
      "rationale": "Scoped synthetic identities prevent duplicate counting without adopting provider identity.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "eligibility_day_boundary": {
      "status": "ADOPTED",
      "value": {
        "clock": "EXPLICIT_INTEGER_SIM_DAY",
        "eligible_when": "as_of_sim_day >= arrival_sim_day + hold_days",
        "before": "HELD_INELIGIBLE",
        "at_or_after": "HELD_ELIGIBLE_FOR_PROPOSAL",
        "automatic_release": false,
        "advance_reopen": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-04"],
      "rationale": "An inclusive logical-day boundary changes review eligibility only.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "duplicate_and_conflicting_inputs": {
      "status": "ADOPTED",
      "value": {
        "exact_duplicate": "COLLAPSE",
        "conflict": "REJECT_ENTIRE_SNAPSHOT",
        "arrival_order": ["arrival_sim_day", "tranche_id"],
        "late_input": "NEW_DISPOSABLE_SNAPSHOT",
        "future_arrival": "REJECT",
        "wall_clock": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-11", "CAP-20"],
      "rationale": "Canonical folding cannot depend on delivery order or select a winner for contradictory evidence.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "operator_disposition_proposal": {
      "status": "ADOPTED",
      "value": {
        "trigger": "EXPLICIT_OPERATOR_REQUEST",
        "actions": ["CONTINUE_HOLD", "REVIEW_ELIGIBLE_HELD_CASH"],
        "scope": "WHOLE_SELECTED_TRANCHES",
        "binding": "EXACT_SNAPSHOT_DIGEST",
        "status": "PROPOSED_ONLY",
        "executionAuthorized": false,
        "cash_effect": "NONE",
        "persist": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-04", "CAP-20"],
      "rationale": "Human intent creates a review artifact without cash movement, recording or execution authority.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "replay_capacity_bounds": {
      "status": "ADOPTED",
      "value": {
        "claims": 1,
        "raw_arrival_records": 256,
        "unique_arrival_tranches": 64,
        "raw_proposal_requests": 64,
        "sim_day_min": 0,
        "sim_day_max": 1000000,
        "max_integer_krw": 9007199254740991,
        "identifier_max_ascii_bytes": 64,
        "overflow": "REJECT_ENTIRE_SNAPSHOT",
        "eviction": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-11", "CAP-20"],
      "rationale": "Finite local workloads fail explicitly without discarding late facts or changing financial caps.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| Acceptance | Coverage |
|---|---|
| One decision block covering all items | §4; six `ADOPTED` entries |
| Existing 180-day duration, anchor and inclusive boundary | §§3.1–3.3 |
| Later arrivals, duplicates, conflicts and ordering | §§3.2–3.4; boundary examples |
| Disposable evaluation and explicit proposals only | §§3.5–3.6 |
| No automatic release or advance reopening | §§3.3–3.5 |
| Excluded execution and recording domains | §7 |

The JSON was constructed and round-trip checked in memory with six populated entries and required common fields. **`python3 scripts/decision_ledger.py` was not run**: the script is outside the explicit read allowlist, and the delivered document has not been written into the repository. Repository validation remains a supervisor integration requirement; no passing result is claimed.

## 6. Open risks

The permitted pack does not establish the predecessor schema or actual clock interface. Their binding remains `NOT_BOUND` until verified; implementations must not guess field names, classification rules or receipt hashes.

Synthetic arrival evidence is operator-controlled and unauthenticated. Determinism does not establish that cash exists. The 180-day interval is product policy for this simulation, not a statutory deadline, legal entitlement or retention period.

## 7. 후속 작업

The supervisor writes this document and runs `python3 scripts/decision_ledger.py`. A downstream implementation must load the adopted predecessor terms, pin their provenance, verify the unchanged UC partition, and bind explicit logical-day inputs. Missing dependencies follow their existing not-bound path; a conflicting duration must fail binding rather than silently override either policy.

Implement the evaluator separately, with regression vectors for boundary days, independent later arrivals, input permutations, aliases, conflicts, stale proposals, capacity rejection and time jumps. Verify unchanged financial terms, terminal advance state and held totals. New vector files require corresponding documentation-surface entries, README needles and `python3 scripts/docs_surface.py --check`.

Provider returns, payout batches, provider-capture recording, workspace recording, participation-window implementation, statutory retention, accounting postings and real execution remain outside this decision. This document makes no runtime changes, upstream edits or vendor changes, and grants no production authority.
