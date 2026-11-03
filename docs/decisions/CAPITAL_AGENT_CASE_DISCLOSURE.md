# Capital agent case disclosure — minimum evidence for a scoped simulated agent

> **PROVISIONAL PRODUCT DECISION**
>
> Requested decision-maker attribution: **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**.
>
> Date: **2026-11-04** · Capital main: **`8ab3d95`** · kix-protocol context: **`c641a74`**.
>
> Simulation/product design only; no real money; production **`NOT_AUTHORIZED`**. Real authentication and execution authority remain **`NOT_BOUND`**. This decision does not adopt an upstream contract.
>
> Execution provenance: the attribution above is the supervisor-prescribed designation. A Sonnet CLI execution, three failed attempts, or Fable takeover was not verified and is not claimed. Repository revisions are supervisor-supplied bases, not independently verified checkouts.

Node: `agent-case-disclosure-decision`. Dependencies: `agent-lane-tools`, `advance-case-dossier`, `auth-boundary`. This document decides the local disclosure contract; implementation and repository acceptance remain separate.

## 1. 결정 요약

`ADOPTED` below means a provisional Capital product choice, not an upstream adoption or implemented capability.

| Item | Decision | CAP rows | Consumer |
|---|---|---|---|
| `case_brief_field_allowlist` | Closed, fixed schema containing one subject and three attributable financial facts | CAP-04, CAP-20 | Proposed case-brief projector |
| `explicit_subject_scope` | Dedicated synthetic grant for exactly one agent, case and beneficiary; pin its claim and advance | CAP-09, CAP-20 | Local grant registry; auth boundary |
| `grant_currentness_checks` | Check run, agent, generation, logical period, revocation and subject before access and response release | CAP-09, CAP-20 | `query_case` gate |
| `denial_disclosure_policy` | Uniform unavailable response for absent, forbidden and unusable cases | CAP-09, CAP-20 | Agent tool response |
| `brief_provenance_scope` | Hash only the disclosed brief; exclude workspace history and revisions | CAP-20 | Brief provenance |
| `local_tool_extension_boundary` | Capital-local `query_case`, outside pinned five-tool coverage | CAP-09, CAP-20 | Agent tool dispatcher |
| `query_non_mutation` | No business, grant, clock, proposal or persistence mutation | CAP-09, CAP-20 | Query implementation and regression checks |

CAP associations describe product impact; they do not declare those requirements complete.

## 2. KIX 비전 연결

The [Protocol README](/workspace/capital-run/kixproto-ro/README.md) connects ticket rights, settlement and financing while distinguishing local reference machinery from production authority. A useful agent therefore needs bounded financing evidence without inheriting the workspace or acquiring execution authority.

[AUTHORITY_MODEL_1.md](/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md) separates grants, generations, currentness, revocation and replay. This decision applies those distinctions to a **synthetic local** gate. Its generation is not a chain lease generation; its revocation is not chain-confirmed revocation.

The supplied [requirements excerpt](../CAPITAL_REQUIREMENTS_KO.md) distinguishes the FSM pin from the AI delegation citation pin, `e2a029d8ac3af7575888dac22fc4bf173ebec232`. The research base `c641a74` does not repin either. The supplied [seams excerpt](../SEAMS.md) also states that local gates do not establish semantic conformance.

[CAPITAL_DEMO_BOOK.md](CAPITAL_DEMO_BOOK.md) describes several synthetic beneficiaries sharing the `organizer` payee label. Consequently, that label cannot establish ownership or disclosure scope. The supplied [accounts/tax/legal excerpt](CAPITAL_ACCOUNTS_TAX_LEGAL.md) preserves the working-assumption boundary; this note establishes no legal entitlement or retention period. No references linked within these sources were followed.

## 3. 항목별 결정

### 3.1 `case_brief_field_allowlist`

Adopt `CAPITAL_CASE_BRIEF_V1`. A successful response has exactly the following leaves and their containing objects. Additional properties, optional expansion, free text, attachments and arrays are forbidden.

| Field | Exact meaning/type |
|---|---|
| `schema` | Constant `CAPITAL_CASE_BRIEF_V1` |
| `mode` | Constant `SIMULATED` |
| `subject.case_id` | Exact granted synthetic case ID |
| `subject.beneficiary_id` | Exact granted synthetic beneficiary ID |
| `subject.claim_id` | Claim ID pinned in the grant |
| `subject.advance_id` | Advance ID pinned in the grant |
| `facts.beneficiary_claim_outstanding_krw` | Outstanding claim face attributable exclusively to this beneficiary within this case |
| `facts.beneficiary_refund_exposure_krw` | Open refund exposure attributable exclusively to this beneficiary within this case |
| `facts.advance_principal_outstanding_krw` | Outstanding principal of this case’s pinned advance, exclusively attributable to this beneficiary |
| `provenance.policy_id` | Constant `CAPITAL_AGENT_CASE_DISCLOSURE_V1` |
| `provenance.brief_sha256` | Digest defined in §3.5 |
| `authority.real_authentication` | Constant `NOT_BOUND` |
| `authority.execution_authority` | Constant `NOT_BOUND` |
| `authority.production` | Constant `NOT_AUTHORIZED` |

IDs are synthetic ASCII strings matching `[A-Za-z0-9_-]{1,64}`. Amounts are nonnegative integers in synthetic KRW units, or `null` when that particular attributable amount is undetermined. Zero means known zero. Null must never become zero, eligibility, or permission.

These are **new output names**, not claims about existing dossier fields. Source-field mappings are `UNDETERMINED` because implementation sources are outside the pack. The implementation owner must establish exact mappings; it may not substitute similarly named totals.

The projector reads only the authorized case’s bounded records after authorization. It must not build a full dossier and then redact it. Ambiguous case ownership, multiple incompatible claim/advance bindings, or inability to isolate the subject causes uniform denial. An isolated subject with an unavailable individual amount may receive that amount as null.

Exclude workspace-wide receipts, other beneficiaries, other cases of the same beneficiary, portfolio totals, concentration/headroom calculations, aggregate underwriting results, raw journals, event lists, documents, names, bank details, credentials, signatures, grant records and authentication material. Do not include a dossier URL or indirect retrieval handle.

### 3.2 `explicit_subject_scope`

Adopt a separate permission, `CAPITAL_LOCAL_QUERY_CASE_V1`, issued explicitly by the local simulation host. Neither QUERY nor PROPOSE lane eligibility, `query_subject` membership, workspace membership, a generic query grant, nor a matching payee label implies this permission.

The grant is an in-memory record containing exactly:

`grant_id`, `run_id`, `agent_id`, `permission`, `subject`, `claim_id`, `advance_id`, `generation`, `not_before_period`, `expires_before_period`, `revoked`.

`subject` contains exactly `case_id` and `beneficiary_id`. One grant permits one such pair and pins one claim and one advance. Wildcards, beneficiary-wide grants, lists, inherited scope, delegation and grant unions are forbidden.

The host creates a unique opaque 128-bit random grant handle, collision-checks it, and retains the record only in memory. It is a synthetic fixture handle, not a bearer authentication credential. The host supplies the simulated agent context; a request cannot select its own agent identity.

Issuance is explicit fixture setup, outside `query_case`. There is no implicit issuance, persistence, renewal, restoration or agent-accessible grant-management tool. A second case needs its own grant.

### 3.3 `grant_currentness_checks`

Use a host-controlled monotonic integer `logical_period`, distinct from financial `sim_day`, wall time, business epochs and chain leases. Issuance at period `p` sets `not_before_period=p` and `expires_before_period=p+1`. Thus a grant lasts exactly the current logical period; repeated reads during that period are permitted.

Maintain a generation counter for each `(agent_id, case_id, beneficiary_id)` slot. Initial issuance uses generation 1. Replacement issuance or revocation advances the counter; old generations never become current again. Revocation also marks the affected record revoked. Restart creates a fresh run identity and discards all grants.

For every request, before protected case access:

1. Validate the closed request shape: `grant_id` and `subject` only.
2. Resolve the grant from the host’s in-memory registry; reject caller-supplied grant contents.
3. Require a permitted simulated QUERY/PROPOSE lane, exact current run and host agent, and the dedicated permission.
4. Require an exact request/grant subject match, current slot generation and `revoked=false`.
5. Require `not_before_period <= logical_period < expires_before_period`.
6. Perform a bounded lookup and verify the case’s beneficiary, claim and advance against the grant.

Missing or inconsistent currentness data, clock rollback, generation overflow, mismatched ownership or changed binding fails closed.

Authorization, bounded projection and response release share one serialized critical section with revocation and period changes. The response linearizes at release: revocation before release denies it; revocation afterward cannot retract already disclosed bytes. Do not stream partial fields or return lazy objects that read protected state later.

### 3.4 `denial_disclosure_policy`

All unsuccessful calls return exactly `{"status":"UNAVAILABLE","code":"CASE_BRIEF_UNAVAILABLE"}`. Any HTTP wrapper uses status 200 for this tool result, without case-dependent headers.

This covers malformed requests, unknown grants, wrong agents, stale generations, expired or revoked grants, subject mismatch, absent cases, ambiguous linkage and unavailable safe projection. Return no echoed identifier, membership flag, reason detail, partial brief, retry hint, count or digest. A valid grant for an absent case receives the same result.

Existing `query_subject` membership semantics remain unchanged. This decision does not conceal facts already exposed by that tool; it prevents membership from becoming a brief entitlement or `query_case` from becoming an additional unrestricted existence oracle.

Worked examples:

| Fixture situation | Result |
|---|---|
| Agent A has a current dedicated grant for case C1 / beneficiary B1, pinned to claim CL1 / advance AD1. The isolated facts are 100,000 claim outstanding, 5,000 refund exposure and 40,000 principal outstanding. | Allow exactly the listed brief, constants and scoped digest. No receipt or ledger accompanies it. |
| A uses that grant for C2, even where C2 also belongs to B1. | Uniform unavailable. No sibling-case evidence. |
| A requests C1 / B2; B2 shares the `organizer` label. | Uniform unavailable. No other-beneficiary identity or amount. |
| `query_subject` reports membership, but A has only a generic QUERY grant. | Uniform unavailable. Membership remains unchanged. |
| The generation is stale, the period has advanced, or revocation occurred before release. | Uniform unavailable, identical to an unknown case. |
| A adds `include_receipts`, `portfolio_total`, `raw_journal` or `credentials` to a valid request. | Reject the whole request uniformly; no expanded or partial response. |

### 3.5 `brief_provenance_scope`

Compute `brief_sha256` over the entire successful allowlisted response **except** the `provenance.brief_sha256` member.

Canonical serialization is UTF-8 JSON with recursively lexicographically sorted object keys, no whitespace, no final newline, decimal integers, JSON nulls and no floats. The closed ASCII schema avoids Unicode normalization ambiguity. Hash those bytes with SHA256 and encode 64 lowercase hexadecimal characters.

Include no workspace digest, HEAD, global revision, journal position, receipt root, global counter, timestamp, current logical period, grant ID or hidden-field hash. Do not hash excluded material as a substitute for withholding it.

While a grant remains valid, an unrelated workspace change must leave the complete brief bytes unchanged. A change confined to excluded fields also leaves the digest unchanged. A disclosed fact change changes the digest. Authorization changes may stop access, but do not become provenance fields.

This is deterministic local content identity, not authentication, completeness, freshness or an upstream receipt. Even authorized recipients cannot infer that the brief is a full dossier.

### 3.6 `local_tool_extension_boundary`

Adopt the proposed tool name `query_case`, classified `CAPITAL_LOCAL_EXTENSION`. It is explicitly outside the pinned five-tool upstream claim coverage. Do not count it as a sixth covered upstream tool, modify upstream delegation contracts, or relabel existing claims.

The local dispatcher must expose it only through the gate above. Existing dossier routes must not become fallback agent tools. PROPOSE consumers may reason from the returned facts within their existing scope; this grant neither creates proposals nor changes proposal validation.

Real identity, production authorization, model calls, proposal execution and persistent grants are excluded. Execution authority and real authentication remain `NOT_BOUND`; production remains `NOT_AUTHORIZED`. No upstream adoption receipt is available or invented.

### 3.7 `query_non_mutation`

A query changes no financial state, ownership, journal, proposal, grant, revocation flag, generation or logical period. It writes no read receipt, file, cache, session history or durable audit event. It has no “last used” mutation and consumes no grant quota.

Transient parsing, locking and projection buffers are permitted. Process and intermediary logging must not capture request handles or response facts. Repeating the same request against unchanged authorized inputs returns identical bytes.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "agent-case-disclosure-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-11-04",
  "provisional": true,
  "entries": {
    "case_brief_field_allowlist": {
      "status": "ADOPTED",
      "value": {
        "schema": "CAPITAL_CASE_BRIEF_V1",
        "additional_properties": false,
        "leaf_fields": [
          "schema",
          "mode",
          "subject.case_id",
          "subject.beneficiary_id",
          "subject.claim_id",
          "subject.advance_id",
          "facts.beneficiary_claim_outstanding_krw",
          "facts.beneficiary_refund_exposure_krw",
          "facts.advance_principal_outstanding_krw",
          "provenance.policy_id",
          "provenance.brief_sha256",
          "authority.real_authentication",
          "authority.execution_authority",
          "authority.production"
        ],
        "unknown_amount": null
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-04", "CAP-20"],
      "rationale": "Only one beneficiary's evidence within one case is necessary.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "explicit_subject_scope": {
      "status": "ADOPTED",
      "value": {
        "permission": "CAPITAL_LOCAL_QUERY_CASE_V1",
        "subject_cardinality": 1,
        "subject_keys": ["case_id", "beneficiary_id"],
        "pin_keys": ["claim_id", "advance_id"],
        "implicit_inheritance": false,
        "persistent": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-09", "CAP-20"],
      "rationale": "Membership and QUERY/PROPOSE lane eligibility do not grant case access.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "grant_currentness_checks": {
      "status": "ADOPTED",
      "value": {
        "run": "exact_current",
        "agent": "host_context_exact",
        "generation": "exact_current_per_agent_subject_slot",
        "period": "not_before <= current < expires",
        "issuance": "not_before=current; expires=current+1",
        "revoked": "deny",
        "release": "atomic_with_checks_and_projection",
        "restart": "invalidate_all"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-09", "CAP-20"],
      "rationale": "An issued grant must remain current at response release.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "denial_disclosure_policy": {
      "status": "ADOPTED",
      "value": {
        "failure_response": {
          "status": "UNAVAILABLE",
          "code": "CASE_BRIEF_UNAVAILABLE"
        },
        "transport_status": 200,
        "existence_oracle": false,
        "query_subject": "UNCHANGED"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-09", "CAP-20"],
      "rationale": "Absence and denied access have the same public result.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "brief_provenance_scope": {
      "status": "ADOPTED",
      "value": {
        "policy_id": "CAPITAL_AGENT_CASE_DISCLOSURE_V1",
        "digest": "SHA256 of canonical allowed response excluding provenance.brief_sha256",
        "workspace_provenance": false,
        "authentication_proof": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-20"],
      "rationale": "Unrelated workspace mutations must not change response bytes.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "local_tool_extension_boundary": {
      "status": "ADOPTED",
      "value": {
        "tool": "query_case",
        "coverage": "CAPITAL_LOCAL_EXTENSION",
        "pinned_five_tool_coverage": false,
        "upstream_contract_change": false,
        "real_authentication": "NOT_BOUND",
        "execution_authority": "NOT_BOUND",
        "production": "NOT_AUTHORIZED",
        "model_calls": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-09", "CAP-20"],
      "rationale": "Local disclosure does not expand upstream authority or claim coverage.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "query_non_mutation": {
      "status": "ADOPTED",
      "value": {
        "business_state": "UNCHANGED",
        "grant_state": "UNCHANGED",
        "logical_period": "UNCHANGED",
        "persistence": false,
        "proposal_creation": false,
        "proposal_execution": false,
        "read_receipts": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-04",
      "cap_rows": ["CAP-09", "CAP-20"],
      "rationale": "Reading evidence has no business or authority side effects.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| Acceptance | Evidence and required verification |
|---|---|
| Provisional block and exact allowlist | §3.1 and §4; JSON round-trip and seven-entry required-field checks passed in memory |
| Dedicated scope and currentness | §3.2–3.3; test wrong agent/run, replacement, period boundaries, revocation and binding changes |
| Allowed and denied examples | §3.4; test every excluded category and reject expansion requests |
| Existence and scoped provenance | §3.4–3.5; compare denial bytes and mutate unrelated workspace data without changing successful response bytes |
| Local-only extension and non-mutation | §3.6–3.7; preserve upstream coverage and membership behavior; compare state before/after queries |

Repository decision checks were **NOT_RUN**: their scripts are outside the permitted read scope, and this document was not written to disk. The historical validation excerpt does not prove this note passes. Repository acceptance is therefore pending, not falsely reported as successful.

## 6. Open risks

- Exact source mappings and ownership isolation remain unverified; fail closed where attribution cannot be established.
- Uniform bodies do not prove timing-side-channel resistance. No production confidentiality or authentication guarantee is claimed.
- Authorized recipients can retain previously disclosed facts; revocation prevents subsequent release.
- Null facts limit proposal reasoning. They must never trigger broader reads or optimistic approval.

## 7. 후속 작업

The supervisor writes this note to `docs/decisions/CAPITAL_AGENT_CASE_DISCLOSURE.md`. The implementation owner adds the isolated projector, ephemeral grant gate and focused positive/negative vectors, including revocation races and unrelated-change invariance.

After writing, run the repository decision checks and `python3 scripts/docs_surface.py --check` in an authorized environment. Any new vector files require the hand-maintained surface entries and matching README needles specified by repository instructions. Record actual results before claiming acceptance; preserve upstream pins, legacy export construction and existing claim coverage.
