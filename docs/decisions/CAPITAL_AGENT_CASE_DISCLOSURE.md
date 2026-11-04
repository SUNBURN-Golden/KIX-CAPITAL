# Capital agent case disclosure — minimum evidence for a scoped simulated agent

> **PROVISIONAL PRODUCT DECISION**
>
> Requested decision-maker attribution: **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**.
>
> Date: **2026-11-04** · Capital main: **`5cfb044`** · kix-protocol context: **`c641a74`**.
>
> Simulation/product design only; no real money; production **`NOT_AUTHORIZED`**. Real authentication and execution authority remain **`NOT_BOUND`**. No upstream contract is adopted.
>
> Execution provenance: the attribution is supervisor-prescribed. Sonnet CLI execution, three failed attempts and Fable takeover were not verified and are not claimed. Repository revisions are supervisor-supplied bases, not independently verified checkouts.

Node: `agent-case-disclosure-decision`. Dependencies: `agent-lane-tools`, `advance-case-dossier`, `auth-boundary`. This document decides disclosure policy; implementation remains separate.

## 1. 결정 요약

`ADOPTED` means a provisional Capital product choice, not upstream adoption or an implemented capability.

| Item | Decision | CAP rows | Consumer |
|---|---|---|---|
| `case_brief_field_allowlist` | Closed schema: one subject and three attributable financial facts | CAP-04, CAP-20 | Case-brief projector |
| `explicit_subject_scope` | Dedicated synthetic grant for one agent, case and beneficiary, pinning claim and advance | CAP-09, CAP-20 | Local grant registry |
| `grant_currentness_checks` | Check run, agent, generation, logical period, revocation and subject before access and release | CAP-09, CAP-20 | `query_case` gate |
| `denial_disclosure_policy` | Uniform unavailable response for absent, forbidden and unusable cases | CAP-09, CAP-20 | Agent tool response |
| `brief_provenance_scope` | Hash only disclosed content; exclude workspace revisions | CAP-20 | Brief provenance |
| `local_tool_extension_boundary` | Capital-local `query_case`, outside pinned five-tool coverage | CAP-09, CAP-20 | Agent dispatcher |
| `query_non_mutation` | No business, grant, clock, proposal or persistence mutation | CAP-09, CAP-20 | Query implementation |

CAP associations describe product impact, not requirement completion.

## 2. KIX 비전 연결

The product direction is useful financing evidence for scoped simulated reasoning, with authority kept explicit. Membership alone supplies insufficient evidence; a full dossier exceeds the necessary disclosure.

The supplied [requirements excerpt](../CAPITAL_REQUIREMENTS_KO.md) distinguishes the FSM pin from the AI delegation citation pin, `e2a029d8ac3af7575888dac22fc4bf173ebec232`. The research base `c641a74` repins neither. The supplied [seams excerpt](../SEAMS.md) states that local gates do not establish semantic conformance.

The supplied [accounts/tax/legal excerpt](CAPITAL_ACCOUNTS_TAX_LEGAL.md) preserves `WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW`. This disclosure decision establishes no legal entitlement, accounting treatment or retention period. Only supplied excerpts and the expressly permitted binding registry were used; linked sources were not followed.

## 3. 항목별 결정

### 3.1 `case_brief_field_allowlist`

Adopt `CAPITAL_CASE_BRIEF_V1`. Success contains exactly these fourteen leaves and their containing objects. Additional properties, optional expansion, free text, attachments and arrays are forbidden.

| Field | Exact meaning/type |
|---|---|
| `schema` | Constant `CAPITAL_CASE_BRIEF_V1` |
| `mode` | Constant `SIMULATED` |
| `subject.case_id` | Exact granted synthetic case ID |
| `subject.beneficiary_id` | Exact granted synthetic beneficiary ID |
| `subject.claim_id` | Claim ID pinned in the grant |
| `subject.advance_id` | Advance ID pinned in the grant |
| `facts.beneficiary_claim_outstanding_krw` | Outstanding claim face exclusively attributable to this beneficiary within this case |
| `facts.beneficiary_refund_exposure_krw` | Open refund exposure exclusively attributable to this beneficiary within this case |
| `facts.advance_principal_outstanding_krw` | Outstanding principal of the pinned advance, exclusively attributable to this beneficiary |
| `provenance.policy_id` | Constant `CAPITAL_AGENT_CASE_DISCLOSURE_V1` |
| `provenance.brief_sha256` | Digest defined in §3.5 |
| `authority.real_authentication` | Constant `NOT_BOUND` |
| `authority.execution_authority` | Constant `NOT_BOUND` |
| `authority.production` | Constant `NOT_AUTHORIZED` |

IDs are synthetic ASCII strings matching `[A-Za-z0-9_-]{1,64}`. Amounts are nonnegative integers in synthetic KRW units, or `null` when that individual attributable amount is undetermined. Zero means known zero; null never implies zero, eligibility or permission.

These are new output names. Source-field mappings are `UNDETERMINED`: implementation sources are outside the pack. The implementation owner must establish exact mappings without substituting similarly named totals.

After authorization, project only bounded records for the granted subject. Never build a full dossier and then redact it. Ambiguous ownership, incompatible claim/advance bindings or inability to isolate the subject causes uniform denial. An isolated subject may have an individual amount returned as null.

Exclude workspace-wide receipts, other beneficiaries, sibling cases, portfolio totals, concentration/headroom calculations, aggregate underwriting results, raw journals, event lists, documents, names, bank details, credentials, signatures, grant records and authentication material. Include no dossier URL or indirect retrieval handle.

### 3.2 `explicit_subject_scope`

Adopt permission `CAPITAL_LOCAL_QUERY_CASE_V1`, explicitly issued by the local simulation host. QUERY/PROPOSE eligibility, `query_subject` membership, workspace membership, generic query grants and matching payee labels never imply this permission.

The in-memory grant contains exactly:

`grant_id`, `run_id`, `agent_id`, `permission`, `subject`, `claim_id`, `advance_id`, `generation`, `not_before_period`, `expires_before_period`, `revoked`.

`subject` contains exactly `case_id` and `beneficiary_id`. One grant permits one pair and pins one claim and advance. Wildcards, beneficiary-wide scope, lists, inherited scope, delegation and grant unions are forbidden.

The host issues a collision-checked, opaque 128-bit random handle and retains the record only in memory. This is a synthetic fixture handle, not a bearer authentication credential. The host supplies agent identity; callers cannot select it.

Issuance is explicit fixture setup outside `query_case`. No implicit issuance, persistence, renewal, restoration or agent-accessible grant management is permitted. Another case requires another grant.

### 3.3 `grant_currentness_checks`

Use a host-controlled monotonic integer `logical_period`, distinct from financial `sim_day`, wall time, business epochs and chain leases. Issuance at period `p` sets `not_before_period=p` and `expires_before_period=p+1`. Repeated reads during that single period are permitted.

Maintain a generation counter per `(agent_id, case_id, beneficiary_id)` slot. Initial issuance uses 1. Replacement issuance or revocation advances the counter; old generations never become current again. Revocation also marks the affected record revoked. Restart creates a fresh run identity and discards all grants.

Before protected case access:

1. Validate a closed request containing only `grant_id` and `subject`.
2. Resolve the grant from the host registry; reject caller-supplied grant contents.
3. Require a permitted simulated QUERY/PROPOSE lane, current run, exact host agent and dedicated permission.
4. Require exact request/grant subject equality, current slot generation and `revoked=false`.
5. Require `not_before_period <= logical_period < expires_before_period`.
6. Perform a bounded lookup and verify beneficiary, claim and advance against the grant.

Missing currentness data, clock rollback, generation overflow, ownership mismatch or changed binding fails closed.

Authorization, projection and response release share one serialized critical section with revocation and period changes. Release is the linearization point: prior revocation denies release; subsequent revocation cannot retract disclosed bytes. No partial streaming or lazy protected-state reads are allowed.

### 3.4 `denial_disclosure_policy`

Every unsuccessful call returns exactly `{"status":"UNAVAILABLE","code":"CASE_BRIEF_UNAVAILABLE"}`. An HTTP wrapper uses status 200 for this tool result, without case-dependent headers.

This includes malformed requests, unknown grants, wrong agents, stale generations, expired/revoked grants, subject mismatch, absent cases, ambiguous linkage and unsafe projection. Return no echoed identifier, membership flag, detailed reason, partial brief, retry hint, count or digest. A valid grant for an absent case receives the same result.

Existing `query_subject` membership semantics remain unchanged. This decision does not conceal facts already exposed there; membership confers no brief entitlement.

| Worked fixture | Result |
|---|---|
| A has a current dedicated C1/B1 grant pinning CL1/AD1; isolated amounts are 100,000 claim, 5,000 refund and 40,000 principal | Exactly the fourteen-leaf brief, scoped IDs, constants and digest; no receipts, other beneficiaries, portfolio data, journals or authentication material |
| A uses that grant for C2, also belonging to B1 | Uniform unavailable; no sibling-case evidence |
| A requests C1/B2, whose payee label also happens to be `organizer` | Uniform unavailable; no B2 evidence |
| `query_subject` reports membership, but A has only a generic QUERY grant | Uniform unavailable; membership behavior unchanged |
| Generation is stale, period advances, or revocation precedes release | Uniform unavailable, identical to an absent case |
| A adds `include_receipts`, `portfolio_total`, `raw_journal` or `credentials` | Reject the whole request uniformly; no expansion or partial response |

### 3.5 `brief_provenance_scope`

Compute `brief_sha256` over the entire successful response except the `provenance.brief_sha256` member.

Canonical bytes are UTF-8 JSON with recursively lexicographically sorted object keys, no whitespace or final newline, decimal integers, JSON nulls and no floats. The closed ASCII schema avoids Unicode normalization ambiguity. Encode SHA256 as 64 lowercase hexadecimal characters.

Exclude workspace digest, HEAD, global revision, journal position, receipt root, global counter, timestamp, logical period, grant ID and hidden-field hashes.

While authorization remains valid, unrelated workspace changes and changes confined to excluded fields must leave complete brief bytes unchanged. A disclosed fact change changes the digest. Authorization changes may stop access but never become provenance fields.

The digest proves deterministic local content identity only; it proves neither authentication, completeness, freshness nor upstream adoption.

### 3.6 `local_tool_extension_boundary`

Adopt proposed tool `query_case`, classified `CAPITAL_LOCAL_EXTENSION`, explicitly outside pinned five-tool upstream claim coverage. It is not a sixth covered upstream tool. Preserve upstream delegation contracts and existing claims.

Expose it only through the specified gate. Existing dossier routes cannot become fallback agent tools. PROPOSE consumers may reason within their existing scope; this grant creates no proposal and changes no proposal validation.

Real identity, production authorization, model calls, proposal execution and persistent grants are excluded. Execution authority and real authentication remain `NOT_BOUND`; production remains `NOT_AUTHORIZED`. No upstream receipt is available or invented.

### 3.7 `query_non_mutation`

A query changes no financial state, ownership, journal, proposal, grant, revocation flag, generation or logical period. It writes no read receipt, file, cache, session history or durable audit event. No “last used” mutation or quota consumption is permitted.

Transient parsing, locking and projection buffers are permitted. Process and intermediary logging must not capture handles or response facts. Identical requests against unchanged authorized inputs return identical bytes.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "agent-case-disclosure-decision",
  "status": "PROVISIONAL_PRODUCT_DECISION",
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
      "rationale": "Membership and lane eligibility do not grant case access.",
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
      "rationale": "A grant must remain current at response release.",
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

| Acceptance | Evidence and verification |
|---|---|
| Valid provisional block and exact allowlist | §3.1/§4; in-memory JSON round-trip, top-level status, seven required-field entries and fourteen leaves checked |
| Dedicated scope and currentness | §3.2–3.3; implementation tests must cover wrong agent/run, replacement, period boundaries, revocation and binding changes |
| Allowed/denied examples | §3.4; reject every excluded category and expansion request |
| Existence behavior and scoped provenance | §3.4–3.5; compare denial bytes and unrelated-change invariance |
| Local-only extension and non-mutation | §3.6–3.7; preserve membership, upstream coverage and state |

Both blocking findings are addressed: §4 adds top-level `status`; seven rows were added to `tests/decision_bindings.json`, one for each entry. Every row uses `kind=module`, `path=capital/agent_lane.py`, `status=PENDING_CONSUMER`, `consumer_node=agent-lane-tools`, this note’s path and an entry-specific implementation reason. These are integration anchors, not implementation claims.

Registry JSON parsing, seven-row coverage, uniqueness and preservation of existing rows passed. Local decision, documentation and pack-vector checks were run in this revision: `tests.test_decision_bindings`, `tests.test_decisions` and `tests.test_decisions_surface` (55 tests, OK), `scripts/docs_surface.py --check` (OK) and `scripts/pack_vectors.py --check` (OK after regenerating the affected committed pack fixtures). Full repository acceptance remains unverified; historical validation results are not evidence for this revision.

## 6. Open risks

- Source mappings and ownership isolation remain unverified; ambiguous attribution must deny access.
- Uniform responses do not establish timing-side-channel resistance or production confidentiality.
- Recipients can retain disclosed facts; revocation prevents subsequent release.
- Null facts limit reasoning and must never trigger broader reads or optimistic approval.

## 7. 후속 작업

The supervisor writes this complete note to `docs/decisions/CAPITAL_AGENT_CASE_DISCLOSURE.md` and retains the seven binding additions. The implementation owner builds the isolated projector and ephemeral grant gate, then verifies denial equality, revocation races, non-mutation and unrelated-change invariance.

In an authorized repository-validation environment, run decision binding and decision surface checks, `python3 scripts/docs_surface.py --check`, and applicable pack-vector checks. Regenerate affected pack fixtures if required. New vector files require surface entries and matching README needles. Record actual results before claiming acceptance. Preserve upstream pins, legacy export construction and existing claim coverage.
