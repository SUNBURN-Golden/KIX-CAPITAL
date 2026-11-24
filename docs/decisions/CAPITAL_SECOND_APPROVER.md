# Capital two-person approval simulation — identity, role, threshold and evidence

> **PROVISIONAL PRODUCT DECISION**
>
> Decision-maker attribution: **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**.
>
> Date: **2026-11-10** · Capital main: **`a791651`** · kix-protocol: **`61e581a`**.
>
> Revised 2026-11-19 to specify how advance-linked commands share a daily total and how receipts cite each applicable total.
>
> Simulation/product design only; no real money, offer or real sign-off authority. Production remains **`NOT_AUTHORIZED`**. Approver labels are synthetic and carry **`LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED`**. Authentication remains **`NOT_BOUND`**. No upstream adoption is claimed.
>
> Provenance: model attribution and revisions are supervisor-prescribed. This revision does not claim verified Claude CLI execution, three failures, Fable takeover or independently verified checkouts.

Node: `second-approver-decision`. Dependencies: `agent-proposal-lane`, `auth-matrix-freeze`, `decision-guard-additions`. `user_merge: false`.

## 1. 결정 요약

`ADOPTED` means a provisional local product choice. It does not mean implementation completion or upstream adoption. “Three consumers” below means `overlay-recovery-writeoff`, `claim-slice-registry` and `waiver-writeoff-decision`; their implementation bindings remain `PENDING_CONSUMER`.

| Item | Decision | CAP rows | Consumer |
|---|---|---|---|
| `approver_identity_model` | Distinct synthetic labels supplied together by a local operator; no identity verification | CAP-19, CAP-01 | Three consumers |
| `capital_desk_role_adoption` | Do not adopt `capital-desk`; retain `ROLE_TARGET_NOT_ADOPTED` | CAP-19 | Three consumers; future authorizer integration |
| `threshold_value_source` | Resolve only `CAPITAL-TERMS-V1.underwriting_depth.two_person_threshold_krw` through `TermsPolicyPort` | CAP-01, CAP-04 | Three consumers |
| `same_advance_aggregation` | Compare accepted same-day bucket total plus candidate amount; crossing command needs two labels | CAP-04, CAP-03, CAP-08 | Three consumers |
| `agent_proposal_not_approval` | Proposals contribute zero approvals; human commands provide their own labels | CAP-19 | Three consumers; agent proposal lane |
| `evidence_citation_shape` | Authority evidence inside overlay payload; receipt cites `overlay_id` and evaluation | CAP-14, CAP-15, CAP-19 | Three consumers; overlay queries/export |
| `auth_matrix_effect` | Preserve existing caller axis and cells; apply policy after role admission | CAP-19, CAP-20 | Three consumers; auth matrix gate |
| `desk_ui_flow` | One submission with synthetic label fields; server decides whether two are required | CAP-20, CAP-19 | Future desk implementation |

## 2. KIX 비전 연결

Underwriting rule U5 reserves approval for a human operator and assigns proposals to the agent lane. The recovery and slice decisions already define the amount basis and simulated authority for their respective commands. This note gives those consumers a common way to count labels, apply the threshold and cite the result. [Financial terms](CAPITAL_FINANCIAL_TERMS.md) · [Default and recovery](CAPITAL_DEFAULT_RECOVERY.md) · [Claim slice registry](CAPITAL_CLAIM_SLICE_REGISTRY.md)

## 3. 항목별 결정

### 3.1 `approver_identity_model` — ADOPTED

A human operator command supplies `approvals[]`, containing synthetic `approver_label` values matching `^[a-z][a-z0-9-]{0,31}$`. Accept one to four labels; reject malformed or duplicate labels. A command requiring two-person simulation needs at least two distinct labels.

Labels identify fixture participants only. The server verifies syntax, count and distinctness; it does not verify identity, employment, credentials, independent sessions or actual human participation. One operator can enter both labels. All evidence and desk surfaces must therefore display `LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED`.

A fixed personnel roster, account creation and signature collection are excluded. They would introduce unsupported identity implications and unnecessary personal data.

### 3.2 `capital_desk_role_adoption` — ADOPTED

Do not add deferred `capital-desk` to the authorizer, caller axis or route permissions. Its status is `ROLE_TARGET_NOT_ADOPTED`. The second simulated approver is another label in the same command, not another admitted role or session.

Future authenticated role adoption requires its own authority contract and acceptance evidence. This note supplies neither. Historical synthetic labels must never become authenticated approvals through an automatic migration or reinterpretation.

### 3.3 `threshold_value_source` — ADOPTED

The sole source is `CAPITAL-TERMS-V1.underwriting_depth.two_person_threshold_krw`, resolved through `TermsPolicyPort`. Do not introduce an approval-specific numeric constant. This note intentionally repeats no threshold amount.

“Exceeds” means strictly greater than the resolved threshold; equality does not trigger the two-label requirement. Read one terms snapshot for an evaluation. Missing, invalid or unavailable terms block the command without an overlay write; they must not default to zero or unlimited authority.

Evidence retains the reference, terms evidence digest and evaluated threshold amount. That amount is an observation from the source, not a replacement configuration. Future commands use current terms; historical receipts retain their original evaluation.

### 3.4 `same_advance_aggregation` — ADOPTED

For every covered command against an advance, resolve its canonical `advance_id` from workspace state and use the bucket `(advance_id, sim_day)`. Default, recovery, acceleration and writeoff share that bucket with any waiver or slice command targeting the same advance. A new verb, waiver ID or slice ID cannot restart the total. Every slice command also uses the registry’s own `(slice_key, sim_day)` bucket, where `slice_key = (claim_id, payee_label)`. A standalone slice has only that bucket.

In each applicable bucket, add the candidate amount once to the previously accepted total. If **any** resulting total exceeds the threshold, the crossing command itself needs two labels. Compare each bucket separately. Reject an insufficient submission with `409 TWO_PERSON_REQUIRED`.

An agent proposal or a rejected submission contributes zero. An accepted human `SLICE_PROPOSE` command counts at its decided slice amount. Idempotent replay returns the recorded evaluation and adds zero. Reversals preserve the amount already counted. Evaluate and append atomically so that a concurrent command sees the first accepted amount.

Consumers use the amount basis from their adopted command decision. A missing amount basis or an unresolved required target blocks the command before append. Each new simulation day starts a fresh total.

### 3.5 `agent_proposal_not_approval` — ADOPTED

Agent proposals always contribute zero approvals and zero accepted bucket amount. They remain `HUMAN_PENDING` with `effects_executed: false`.

An agent attempting a human-only command is rejected with the route’s `403 *_AGENT_FORBIDDEN` outcome before inspecting its proposed approvals. Supplying human-looking labels does not bypass caller admission.

An admitted human operator may cite a proposal in `proposal_refs`, but must supply the command’s own labels. Proposal authors, agent identifiers and proposal references never become approvers. Proposal adoption is a new human-command evaluation using current terms and current bucket state.

### 3.6 `evidence_citation_shape` — ADOPTED

Retain the overlay envelope `overlay_id`/`kind`/`payload`. Place synthetic approval evidence in `payload.authority`, including `mode`, `approvals`, `proposal_refs`, `threshold_ref` and `evaluation`.

The server supplies approval `sim_day` from the workspace simulation clock. For each applicable bucket, `evaluation.buckets[]` records its key, previously accepted amount and evaluated total. The evaluation also records the candidate amount, observed threshold, terms evidence digest, requirement result and distinct-label count. The accepted entry retains that evaluation. Its receipt echoes the evaluation under `two_person` and cites the entry by `overlay_id`.

A rejection creates no accepted entry and no success citation. Its diagnostic response may explain the policy requirement without representing a successful approval. Replay returns the original accepted evidence; it does not create fresh approval.

No wall-clock identity claims, session identifiers, credentials or token material belong in this evidence. The terms digest is a local provenance reference, not a signature or upstream receipt.

### 3.7 `auth_matrix_effect` — ADOPTED

This decision changes zero existing auth-matrix cells and no caller roles. Apply existing role admission first, then the amount/approval policy within the human command handler. Insufficient approvals produce `409 TWO_PERSON_REQUIRED`; forbidden callers retain their existing authorization denial.

Parked implementations may add route coverage using the existing matrix generation/check procedure on the unchanged caller axis. They must review those additions as implementation changes. This document does not regenerate the matrix or assert knowledge of unavailable implementation details.

### 3.8 `desk_ui_flow` — ADOPTED

Keep a single operator submission. The ordinary path accepts one synthetic label; when the server reports that two are required, show two required label fields and preserve the pending command for resubmission. Display “SIMULATED — synthetic labels, not authenticated” with the exact authority label.

The server’s cumulative bucket evaluation governs the UI, including when the individual command amount is below the threshold. Client checks may detect duplicate or malformed labels, but cannot authorize a command. Any preview is advisory; submission rechecks current terms and bucket state.

Do not add a second login, signature widget or pending-approval queue. Browser acceptance must cover a crossing command, equal labels, successful resubmission and an agent-originated denial.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "second-approver-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-11-10",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "consumers": [
    "overlay-recovery-writeoff",
    "claim-slice-registry",
    "waiver-writeoff-decision"
  ],
  "entries": {
    "approver_identity_model": {
      "status": "ADOPTED",
      "value": {
        "model": "SYNTHETIC_APPROVER_LABELS",
        "mode": "LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED",
        "pattern": "^[a-z][a-z0-9-]{0,31}$",
        "min_labels": 1,
        "max_labels": 4,
        "required_when_triggered": 2,
        "duplicates": "REJECT",
        "identity_verified": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-10",
      "cap_rows": ["CAP-19", "CAP-01"],
      "rationale": "Distinct fixture labels simulate participation without claiming authentication.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "capital_desk_role_adoption": {
      "status": "ADOPTED",
      "value": {
        "adopted_as_role": false,
        "role_state": "ROLE_TARGET_NOT_ADOPTED",
        "historical_labels_become_authenticated": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-10",
      "cap_rows": ["CAP-19"],
      "rationale": "The simulation needs no new role or unsupported authority contract.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "threshold_value_source": {
      "status": "ADOPTED",
      "value": {
        "threshold_ref": "CAPITAL-TERMS-V1.underwriting_depth.two_person_threshold_krw",
        "read_via": "TermsPolicyPort",
        "comparison": "any applicable bucket's evaluated_total > threshold",
        "independent_numeric_constant": false,
        "unavailable_terms": "BLOCK_WITHOUT_WRITE",
        "evidence": "Persist observed threshold and terms evidence digest; retain historical evaluation"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-10",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "One terms source prevents configuration drift while preserving historical evidence.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "same_advance_aggregation": {
      "status": "ADOPTED",
      "value": {
        "advance_bucket": ["advance_id", "sim_day"],
        "advance_scope": "All covered commands targeting the same advance, across command families",
        "slice_bucket": ["slice_key", "sim_day"],
        "slice_scope": "Every slice command uses (claim_id, payee_label) as slice_key, including when an advance bucket also applies",
        "evaluation": "For each applicable bucket, compare its accepted total plus the candidate amount to the terms threshold",
        "crossing_command_requires_two": true,
        "denials_agent_proposals_replays_count": false,
        "reversals_reduce_aggregate": false,
        "atomic_evaluation_and_append": true,
        "target_alias_reset": "FORBIDDEN",
        "unmapped_command": "BLOCK_PENDING_CONSUMER_DECISION",
        "insufficient_approvals": "409 TWO_PERSON_REQUIRED",
        "cross_day_policy": {
          "status": "UNDETERMINED",
          "value": null,
          "target": "Separate cumulative policy; this decision covers same-day buckets only",
          "reason": "The supplied scope does not establish a cross-day aggregation policy"
        }
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-10",
      "cap_rows": ["CAP-04", "CAP-03", "CAP-08"],
      "rationale": "Candidate-inclusive, serialized aggregation blocks same-bucket splitting without counting unsuccessful actions.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "agent_proposal_not_approval": {
      "status": "ADOPTED",
      "value": {
        "counts_as_approval": false,
        "counts_as_bucket_amount": false,
        "proposal_state": "HUMAN_PENDING",
        "effects_executed": false,
        "agent_command": "403 *_AGENT_FORBIDDEN before approval inspection",
        "human_adoption": "Cite proposal_refs and supply independent command approvals"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-10",
      "cap_rows": ["CAP-19"],
      "rationale": "Proposal provenance cannot grant approval or execution authority.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "evidence_citation_shape": {
      "status": "ADOPTED",
      "value": {
        "location": "payload.authority",
        "mode": "LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED",
        "approvals": [
          {"approver_label": "synthetic string", "sim_day": "server simulation day"}
        ],
        "proposal_refs": ["proposal_id"],
        "threshold_ref": "CAPITAL-TERMS-V1.underwriting_depth.two_person_threshold_krw",
        "evaluation_fields": [
          "buckets",
          "candidate_amount",
          "threshold_observed_krw",
          "terms_evidence_sha256",
          "required",
          "satisfied",
          "distinct_approver_labels"
        ],
        "bucket_fields": ["amount_bucket", "prior_accepted_amount", "evaluated_total"],
        "receipt_echo": "two_person",
        "citation_key": "overlay_id",
        "rejection_creates_entry": false,
        "replay": "Original accepted evidence",
        "excluded": ["wall-clock identity claims", "session identifiers", "credentials", "tokens"]
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-10",
      "cap_rows": ["CAP-14", "CAP-15", "CAP-19"],
      "rationale": "Overlay evidence preserves the evaluated policy without pretending to be a signed authorization.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "auth_matrix_effect": {
      "status": "ADOPTED",
      "value": {
        "caller_axis_changed": false,
        "existing_cells_changed": 0,
        "check_layer": "Human handler after existing role admission",
        "policy_failure": "409 TWO_PERSON_REQUIRED",
        "new_routes": "Future consumers add reviewed coverage on the existing caller axis"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-10",
      "cap_rows": ["CAP-19", "CAP-20"],
      "rationale": "Approval simulation is a policy check within existing authorization boundaries.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "desk_ui_flow": {
      "status": "ADOPTED",
      "value": {
        "flow": "Single operator submission with approvals",
        "ordinary_labels": 1,
        "triggered_labels": 2,
        "requirement_source": "Server cumulative evaluation",
        "resubmission": "Preserve command and re-evaluate current state",
        "client_checks": ["format", "duplicate labels"],
        "labels": ["SIMULATED", "LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED"],
        "excluded": ["second login", "signature widget", "pending-approval queue"]
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-10",
      "cap_rows": ["CAP-20", "CAP-19"],
      "rationale": "One submission demonstrates the control while keeping server evaluation authoritative.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

- Exactly one decision block contains all eight required items, each with status, attribution, date, rationale and provisional product basis.
- Synthetic identity and `LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED` are explicit in identity, evidence and UI decisions.
- Agent proposals contribute no approval or bucket amount.
- All three parked consumers are named; their bindings remain `PENDING_CONSUMER`.

## 6. Open risks

One operator can supply both labels in this simulation. Production authentication and real sign-off remain `NOT_BOUND`. The daily aggregation window permits a new total on the next simulation day.

## 7. 후속 작업

Consumer acceptance includes an advance whose accepted recovery reaches the threshold exactly. A positive waiver against that advance on the same day must then require two distinct labels, even with a fresh waiver ID. A rejected attempt leaves the prior total intact. Replay of the accepted retry returns its original receipt and counts once. Other cases cover concurrent submissions, independent advances and days, the slice bucket, duplicate labels, agent rejection and unavailable terms.
