# Capital 2인 승인 시뮬레이션 결정 — 승인자 identity 모델, capital-desk 역할 채택 여부, 임계값 출처, 동일 선지급 당일 합산, AI 제안 비승인, 증거 인용 형태, auth matrix·데스크 UI 영향

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
이 문서는 KIX-CAPITAL 저장소 안의 **시뮬레이션·제품 설계용** 결정이다. 2인 원칙은 **시뮬레이션 통제**이며 실제 sign-off 권한이 아니다. 청약이나 대출 제안이 아니고, 실자금이 움직이지 않으며, production은 계속 `NOT_AUTHORIZED`다. `approver_label`은 인증이 아니고 모든 승인 증거는 `LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED`를 단다. 어떤 upstream 계약(IdP, AgentGrant/ActionPermit, `ai-delegation-contract-mock` 등)의 채택도 주장하지 않는다. 이 결정 PR의 허용 diff는 `docs/decisions/CAPITAL_SECOND_APPROVER.md`, `tests/decision_bindings.json`, `tests/vectors/pack/`뿐이다. `tests/test_coa_candidate.py`(byte guard)를 포함한 그 밖의 테스트·CI 파일은 이 PR에서 바꾸지 않는다. guard 정책 수정은 별도로 승인된 선행 변경의 몫이다(§6·§7). 바인딩은 세 parked 소비 노드의 기존 Python 통합 지점을 `PENDING_CONSUMER`로 적을 뿐 구현 완료를 주장하지 않는다. pack은 바뀐 결정 목록과 문서 digest를 반영해 다시 만든 `SIMULATED` 진단 fixture다. `capital/`, vendor 바이트, 기타 골든, pinned auth matrix, 기존 결정 노트의 상태 토큰은 건드리지 않는다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `second-approver-decision` (Decision: two-person approval simulation — approver identity model, role choice and evidence shape) · deps `agent-proposal-lane`, `auth-matrix-freeze` · kind `decision` · user_merge `False` |
| 결정자 | **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)** |
| 위임 원문 | 2026-10-08 18:25 KST JunTae Park: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." |
| 결정일 | 2026-10-25 |
| 기준 | KIX-CAPITAL main `e56224a` · kix-protocol `53c16b2` (읽기 전용 `/workspace/capital-run/kixproto-ro`) · vendor pin `7481b0e16ce9b903abbffa62249bb91cd9e63cfe` 불변 |
| 임계값 출처 규칙 | 임계값 숫자를 복사하지 않는다. `CAPITAL-TERMS-V1` `underwriting_depth.two_person_threshold_krw` 필드명으로만 인용한다(설명용 현재 값 50,000,000). |
| 상태 어휘 | **ADOPTED** = 위임 범위 안의 잠정 값. **UNDETERMINED** = 값을 정할 수 없어 이유만 남긴 항목(`value: null`, 방향은 `target`). 여덟 항목 모두 ADOPTED다. |
| 개정 | 리뷰 라운드(2026-10-25): [blocking] `tests/test_coa_candidate.py` 변경은 허용 범위 밖이라는 지적을 수용했다. 이 노트는 그 파일의 변경을 요구하거나 포함하지 않는다. 브랜치에 남은 해당 diff는 이 결정 PR에서 빼고 origin/main 바이트로 되돌려야 한다. guard 정책 수정은 repository verification owner의 별도 선행 PR로 넘긴다. 결정 값은 바뀌지 않았다. |

## 1. 결정 요약

| item | 결정 (요지) | CAP rows | 소비 노드 / seam |
|---|---|---|---|
| `approver_identity_model` | **ADOPTED.** 승인자는 명령 본문에 담긴 합성 `approver_label` 문자열 쌍이다. 서버는 **개수·구별·형식**만 검사하고 정체성·자격은 검사하지 않는다. 계정·비밀번호·개인정보 없음. 모든 표면에 `LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED`를 단다 | CAP-19, CAP-01 | `overlay-recovery-writeoff`, `claim-slice-registry`, `waiver-writeoff-decision` 세 노드 공통 |
| `capital_desk_role_adoption` | **ADOPTED (비채택으로 채택).** deferred `capital-desk` 역할을 지금 auth matrix나 `LocalRoleAuthorizer`에 넣지 않는다. 두 번째 승인자는 `approver_label`로만 표현한다. `capital-desk`는 OIDC `kix_role` 목표로만 인용한다(`ROLE_TARGET_NOT_ADOPTED`) | CAP-19 | `docs/SEAMS.md` AuthorizerPort 행(문서 갱신만), 세 노드 |
| `threshold_value_source` | **ADOPTED.** 유일한 출처는 `CAPITAL-TERMS-V1.underwriting_depth.two_person_threshold_krw`다. 노트·코드·응답은 `threshold_ref` 필드명만 인용하고 숫자를 새 상수로 복사하지 않는다 | CAP-01, CAP-04 | `TermsPolicyPort`(`capital/terms.py`) 경유, 세 노드 |
| `same_advance_aggregation` | **ADOPTED.** 쪼개기 회피를 막기 위해 `(command_family, target_key, sim_day)` 버킷별로 금액을 누적해 임계값과 비교한다 | CAP-04, CAP-03, CAP-08 | 세 노드 공통 규칙 |
| `agent_proposal_not_approval` | **ADOPTED.** agent 제안은 `approvals[]`에 들어가지 않고 승인 수에 세지 않는다. agent가 사람 전용 명령을 POST하면 403 `*_AGENT_FORBIDDEN`이다. 운영자가 채택하면 사람 명령이 `proposal_id`를 인용하고 자체 `approvals[]`를 갖는다 | CAP-19 | agent lane(`tests/agent_claims.json`), 세 노드 |
| `evidence_citation_shape` | **ADOPTED.** 엔트리 `payload.authority`에 {mode, approvals[{approver_label, sim_day}], proposal_refs, threshold_ref}를 둔다. receipt는 `two_person` 결과를 echo한다. 인용 키는 `overlay_id`다 | CAP-14, CAP-15, CAP-19 | 세 노드, `GET /api/overlay`, V3 `overlay` export 섹션 |
| `auth_matrix_effect` | **ADOPTED.** `KIX_CAPITAL_AUTH_MATRIX_V1`의 역할·호출자 축은 불변이며 바뀌는 셀은 0개다. 2인 검사는 역할 검사를 통과한 뒤 핸들러 안에서 하는 정책이다(409). 새 라우트는 기존 `--write`/`--check` 절차로 셀만 추가한다 | CAP-19, CAP-20 | `tests/auth_matrix.json`, `scripts/auth_matrix.py`, 세 노드 |
| `desk_ui_flow` | **ADOPTED.** `#desk`는 단일 제출 흐름을 유지한다. 금액이 임계값을 넘으면 `approver_label` 입력 칸 두 개를 보이고, 같은 라벨은 클라이언트에서도 거절한다. 로그인·보류 큐는 없다 | CAP-20, CAP-19 | `capital/static/app.js` `#desk`, `tests/browser/operator-desk.spec.cjs` |

## 2. KIX 비전 연결 — 사용한 pack 경로

- `/workspace/capital-run/kixproto-ro/README.md`: 현재 범위는 mock·비운영이고 IdP·실인증·실자금은 잠겨 있다. 그래서 승인자 모델은 인증 없는 합성 라벨로 닫고 `capital-desk`는 목표 역할로만 둔다.
- `/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md`: 기록과 재생, 권한과 커밋을 합치지 않는다. `approvals[]`는 기록일 뿐 실행 허가가 아니다. 과거 승인 기록을 재생해도 새 승인이 되지 않는다.
- `docs/CAPITAL_REQUIREMENTS_KO.md`: 범위는 DEV_ONLY 로컬 시뮬레이션이고 authentication은 `NOT_BOUND`다. CAP-19(로컬 합성 역할, agent 제안은 `HUMAN_PENDING`)와 CAP-01/04(사람 운영자 전용 오버레이 명령)가 이 노트의 표면이다.
- `docs/SEAMS.md`: "`actor` is not authentication" 원칙과 AuthorizerPort `NOT_BOUND`를 따른다. `approver_label`도 같은 규칙을 적용받는다.
- `docs/VALIDATION.md`: 로컬 검증 범위는 SIMULATED fixture뿐이다. auth matrix 고정은 관측 동작의 드리프트 감지 장치다.
- `docs/decisions/CAPITAL_DEFAULT_RECOVERY.md`: 2인 임계값은 `CAPITAL-TERMS-V1` 필드를 참조하고, 같은 `advance_id`·같은 `sim_day` 합산을 쓴다. 이 노트는 그 규칙을 정본 패턴으로 채택한다.
- `docs/decisions/CAPITAL_CLAIM_SLICE_REGISTRY.md`: 한도는 `underwriting_depth` 필드명으로만 인용하고, 엔트리는 `overlay_id`/`kind`/`payload` 형태다. 슬라이스 명령에는 `slice_key` × `sim_day` 합산을 적용한다.
- `docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md`: IdP와 KYC는 채택하지 않는다.
- `docs/decisions/CAPITAL_ARTIFACT_BUNDLING.md`: 라벨 정직성(`NOT_BOUND`, `LOCAL_SIMULATION_ARTIFACT`)을 유지한다.
- `docs/decisions/CAPITAL_CLOSEOUT_ARTIFACT.md`: 골든·`test_count`가 바뀌면 재생성 절차를 따른다.
- 「포부」의 번역: 2인 규칙을 지금 **하나의 명명된 패턴**으로 고정해 둔다. 그러면 IdP나 `capital-desk`가 실제로 열릴 때 `approver_label` → `kix_role` 매핑 자리가 이미 마련돼 있다. 지금은 누구에게도 실제 승인 권한이 없다.

## 3. 항목별 결정

### 3.1 approver_identity_model (CAP-19, CAP-01) — ADOPTED

- **값.** 승인자는 사람 운영자 명령 본문 `approvals[]` 안의 합성 `approver_label` 문자열이다. 형식은 `^[a-z][a-z0-9-]{0,31}$`이고 명령당 최대 4개다. 서버는 다음 세 가지만 검사한다.
  - 라벨 형식
  - `approvals` 길이
  - 서로 다른 라벨 수

  라벨이 실제 사람·계정·자격과 대응하는지는 검사하지 않으며, 검사할 수단도 없다.
- **라벨.** 응답·엔트리·조회·export 모두에 상수 `authority: LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED`를 단다.
- **근거.** CAP-19는 계정·비밀번호·개인정보를 금지하고, AuthorizerPort는 `NOT_BOUND`다. 선행 두 노트가 이미 같은 모양을 쓴다.
- **대안.** 고정 로스터 강제는 진짜 계정처럼 오독될 수 있어 기각한다. 단일 서명 필드는 두 사람을 구별할 수 없어 기각한다.

### 3.2 capital_desk_role_adoption (CAP-19) — ADOPTED (값: 비채택)

- **값.** `capital-desk`(바인딩 노트 `roles_v2`의 목표 역할, OIDC `kix_role` 매핑값)를 지금은 `LocalRoleAuthorizer`·auth matrix·라우트 권한에 추가하지 않는다. 상태 라벨은 `ROLE_TARGET_NOT_ADOPTED`다.
- **근거.** 역할을 채택하려면 IdP·KYC 제공자 결정(`UNDETERMINED`)과 matrix 호출자 축 변경이 필요하다. 둘 다 이 노드의 시뮬레이션 범위를 넘는다.
- **대안.** 다섯 번째 역할을 지금 추가하면 pinned 축이 깨진다. 또 인증 없는 역할이 인증처럼 보이게 되므로 기각한다.

### 3.3 threshold_value_source (CAP-01, CAP-04) — ADOPTED

- **값.** 코드는 `TermsPolicyPort`에서 값을 읽는다. 엔트리·응답은 `threshold_ref: "CAPITAL-TERMS-V1.underwriting_depth.two_person_threshold_krw"`로 인용한다. TERMS가 개정되면 이후 검사는 새 값을 따른다. 이미 기록된 엔트리는 기록 당시의 평가를 유지한다.
- **근거.** 숫자 복사 금지 규칙은 claim-slice·default-recovery 노트에서 이미 채택됐다.
- **대안.** 승인 전용 임계값을 따로 두면 같은 금액 scope에 숫자가 두 개 생겨 드리프트하므로 기각한다.

### 3.4 same_advance_aggregation (CAP-04, CAP-03, CAP-08) — ADOPTED

- **값.** 버킷은 `amount_bucket = (command_family, target_key, sim_day)`다. `target_key`는 계열별로 다음과 같다.
  - 회수·상각·가속·부도: `advance_id`
  - 슬라이스: `slice_key`
  - waiver/writeoff: `waiver_id`, 없으면 `advance_id`

  같은 버킷에서 누적 금액이 임계값을 넘는 순간부터, 그 버킷의 이후 모든 명령에 2인 승인이 필요하다. 미충족이면 409 `TWO_PERSON_REQUIRED`다.
- **근거.** 선행 두 노트의 당일·대상별 합산 규칙을 일반화했다. `sim_day`가 버킷 경계를 결정론적으로 만든다.
- **대안.** 명령당 평가만 하면 40+40 쪼개기를 허용하므로 기각한다. 여러 날에 걸친 영구 합산은 실자금 정책의 몫이며 `target`으로만 남긴다.

### 3.5 agent_proposal_not_approval (CAP-19) — ADOPTED

- **값.**
  1. agent는 `QUERY`·`PROPOSE`만 할 수 있다. 제안은 `HUMAN_PENDING` 상태이고 `effects_executed=false`다.
  2. agent가 사람 전용 명령을 보내면 `approvals[]` 검사 전에 403 `*_AGENT_FORBIDDEN`으로 거절된다.
  3. 운영자가 제안을 채택하면 `payload.authority.proposal_refs`에 `proposal_id`를 인용한다. 인용은 승인 수에 더해지지 않는다. 임계값을 넘으면 사람 라벨 두 개가 여전히 필요하다.
- **근거.** U5("AI proposes only")와 `tests/agent_claims.json`의 `executionAuthorized=false` 고정에 따른다.
- **대안.** AI 제안을 첫 승인으로 세는 안은 U5 위반이므로 기각한다.

### 3.6 evidence_citation_shape (CAP-14, CAP-15, CAP-19) — ADOPTED

- **값.** 엔트리 `payload.authority`는 다음과 같다.
  `{"mode":"LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED","approvals":[{"approver_label":"...","sim_day":n}],"proposal_refs":[...],"threshold_ref":"CAPITAL-TERMS-V1.underwriting_depth.two_person_threshold_krw"}`.
  receipt는 `two_person: {required, satisfied, distinct_approver_labels, amount_bucket}`를 echo한다. 인용 키는 `overlay_id`다. 실시간 시각·세션 id·토큰은 기록하지 않는다.
- **근거.** 채택된 `overlay_id`/`kind`/`payload` 형태를 재사용해 digest 안정성을 지킨다. 토큰 같은 필드를 두면 인증이 있는 것처럼 보인다.
- **대안.** 별도 approval receipt 객체는 새 저장 경계와 새 digest를 만들므로 기각한다.

### 3.7 auth_matrix_effect (CAP-19, CAP-20) — ADOPTED

- **값.** 이 결정으로 `tests/auth_matrix.json`에서 바뀌는 셀은 0개다. 2인 검사는 organizer 역할 검사를 통과한 뒤에 하며, 실패하면 409 `TWO_PERSON_REQUIRED`다. 라벨 부족은 권한 부족이 아니라 정책 미충족이므로 403이 아니다. parked 노드가 라우트를 추가하면 `scripts/auth_matrix.py --write` + `--check`로 같은 다섯 호출자 축에 셀만 추가한다.
- **근거.** freeze의 목적은 드리프트 감지이며 확장 금지가 아니다.
- **대안.** 실패를 403으로 처리하면 의미가 틀리므로 기각한다.

### 3.8 desk_ui_flow (CAP-20, CAP-19) — ADOPTED

- **값.** `#desk`는 단일 제출 흐름을 유지한다. 금액이 임계값을 넘으면 `approver 1`·`approver 2` 칸과 "합성 라벨 — 인증 아님(`LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED`)" 표기를 보인다. 임계값은 서버 응답에서 받아 표시만 하고, 클라이언트가 직접 계산해 판정하지 않는다. 두 라벨이 같으면 클라이언트에서도 거절하지만 정본은 서버의 409다. 로그인·제2 세션·보류 큐·서명 위젯은 두지 않는다. 브라우저 테스트는 임계 초과(두 라벨) 경로와 임계 이하(단일 라벨) 경로를 모두 고정한다.
- **근거.** 명령 형태가 `approvals[]`를 한 번에 받으므로 이것이 가장 작으면서 정직한 시연이다.
- **대안.** PENDING_SECOND_APPROVAL 큐는 명령 수명과 dedup을 다시 설계해야 하므로 기각한다. 실자금 결정의 `target`으로 남긴다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "second-approver-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-10-25",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "scope": "KIX-CAPITAL simulation and product design only; the two-person rule is a SIMULATED control, not sign-off authority; no real money; production NOT_AUTHORIZED; approver_label is not authentication; no upstream contract claimed adopted",
  "delegation": "2026-10-08 18:25 KST JunTae Park delegated financial terms, settlement policy, upstream binding and accounts/tax/legal; this node decided by Sonnet 5.5 xhigh under the same delegation (lanes 10-16 09:07)",
  "bases": {"capital_main": "e56224a", "kix_protocol": "53c16b2", "vendor_pin_commit": "7481b0e16ce9b903abbffa62249bb91cd9e63cfe", "terms_version": "CAPITAL-TERMS-V1", "auth_matrix_version": "KIX_CAPITAL_AUTH_MATRIX_V1"},
  "upstream_adoption_claimed": false,
  "pr_file_scope": ["docs/decisions/CAPITAL_SECOND_APPROVER.md", "tests/decision_bindings.json", "tests/vectors/pack/"],
  "consumers": ["overlay-recovery-writeoff", "claim-slice-registry", "waiver-writeoff-decision"],
  "entries": {
    "approver_identity_model": {
      "status": "ADOPTED",
      "value": {"model": "SYNTHETIC_APPROVER_LABELS", "location": "command body approvals[].approver_label", "pattern": "^[a-z][a-z0-9-]{0,31}$", "max_approvals_per_command": 4, "server_checks": ["label format", "approvals count", "distinct label count"], "not_checked": ["real identity", "accounts", "credentials", "seats"], "label": "LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED"},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-25",
      "cap_rows": ["CAP-19", "CAP-01"],
      "rationale": "CAP-19 forbids accounts/passwords/PII and AuthorizerPort is NOT_BOUND; distinct synthetic labels are the only honest way to simulate two persons and match both prior notes.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "capital_desk_role_adoption": {
      "status": "ADOPTED",
      "value": {"adopted_as_role": false, "role_state": "ROLE_TARGET_NOT_ADOPTED", "target": "capital-desk stays the deferred upstream role (binding note roles_v2, mapped from OIDC kix_role claim); second approver is expressed only as a distinct approver_label; adoption waits on IdP vendor + KYC provider (UNDETERMINED, JunTae/legal designate)"},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-25",
      "cap_rows": ["CAP-19"],
      "rationale": "Adding capital-desk now would mutate the pinned caller axis and make an unauthenticated role look like authentication; it remains the target shape for real-funds lift.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "threshold_value_source": {
      "status": "ADOPTED",
      "value": {"threshold_ref": "CAPITAL-TERMS-V1.underwriting_depth.two_person_threshold_krw", "read_via": "TermsPolicyPort", "literal_copied": false, "recompute_on_terms_revision": true, "recorded_entries_keep_evaluation_at_write": true},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-25",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Single source avoids a second drift-prone number and matches the citation-only cap rule already used by claim-slice-registry and default-recovery.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "same_advance_aggregation": {
      "status": "ADOPTED",
      "value": {"bucket": "(command_family, target_key, sim_day)", "target_keys": {"recovery_writeoff_acceleration_default": "advance_id", "claim_slice": "slice_key", "waiver_writeoff": "waiver_id_or_advance_id"}, "rule": "cumulative operator-submitted amount in the bucket is compared to the threshold; crossing mid-day makes every further command in the bucket two-person", "reject": "409 TWO_PERSON_REQUIRED", "cross_day_cumulative": {"value": null, "target": "permanent cumulative aggregation across sim_days is a real-funds policy choice, deferred to f04-real-funds-lift-criteria"}},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-25",
      "cap_rows": ["CAP-04", "CAP-03", "CAP-08"],
      "rationale": "Same-day per-target summation is the already-adopted split-evasion guard in default-recovery and claim-slice; generalizing it names one pattern for all three consumers.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "agent_proposal_not_approval": {
      "status": "ADOPTED",
      "value": {"agent_may": ["QUERY", "PROPOSE"], "proposal_state": "HUMAN_PENDING", "effects_executed": false, "counts_as_approval": false, "agent_command_post": "403 *_AGENT_FORBIDDEN before approvals inspection", "human_adoption": "human command cites proposal_id in authority.proposal_refs and supplies its own approvals[]"},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-25",
      "cap_rows": ["CAP-19"],
      "rationale": "U5 and the agent lane fix AI to proposal-only; counting a proposal as an approval would dissolve the two-person control.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "evidence_citation_shape": {
      "status": "ADOPTED",
      "value": {"entry_payload_authority": {"mode": "LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED", "approvals": [{"approver_label": "string", "sim_day": "integer"}], "proposal_refs": ["proposal_id"], "threshold_ref": "CAPITAL-TERMS-V1.underwriting_depth.two_person_threshold_krw"}, "receipt_echo": {"two_person": {"required": "bool", "satisfied": "bool", "distinct_approver_labels": "int", "amount_bucket": "family/target/sim_day"}}, "citation_key": "overlay_id", "not_recorded": ["wall-clock time", "session id", "token material"]},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-25",
      "cap_rows": ["CAP-14", "CAP-15", "CAP-19"],
      "rationale": "Reuses the adopted overlay_id/kind/payload shape and digest-stable sim_day; recording token-like fields would pretend authentication exists.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "auth_matrix_effect": {
      "status": "ADOPTED",
      "value": {"caller_axis_changed": false, "cells_changed_by_this_decision": 0, "check_layer": "post-role handler policy", "failure_code": "409 TWO_PERSON_REQUIRED (not 403)", "extension_procedure": "new routes/commands from parked nodes add cells on the same five-caller axis via scripts/auth_matrix.py --write + --check"},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-25",
      "cap_rows": ["CAP-19", "CAP-20"],
      "rationale": "auth-matrix-freeze pins the observed role axis; the two-person rule is a policy check after role admission, so no axis or cell changes.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "desk_ui_flow": {
      "status": "ADOPTED",
      "value": {"flow": "single command submit carrying approvals[]", "above_threshold_ui": "two approver_label fields labelled synthetic; equal labels rejected client-side; server 409 is authoritative; threshold displayed from server response, no client arithmetic", "absent": ["separate login", "second session", "pending-approval queue", "signature widget"], "labels": ["SIMULATED", "LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED"], "target": "a real pending-second-approval workflow remains for the real-funds decision"},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-25",
      "cap_rows": ["CAP-20", "CAP-19"],
      "rationale": "The adopted command shape takes both labels at once; a queue would reopen command lifecycle and dedup semantics for no simulation gain.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

- `capital-decision-v1` 블록 하나에 여덟 항목과 각 `status`가 있다 → §4(모두 ADOPTED).
- 승인자 라벨은 합성이고 `LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED`를 단다 → §3.1, §3.6.
- agent 제안은 승인 수에 들어가지 않는다 → §3.5(`counts_as_approval: false`, 403 경로).
- 이 노트를 소비하는 parked 노드: `overlay-recovery-writeoff`, `claim-slice-registry`, `waiver-writeoff-decision` → §1, §4 `consumers`.

## 6. Open risks

- **CI baseline guard 충돌(blocking 리뷰 대응).** `tests/test_coa_candidate.py::V1UnchangedTests`는 `docs/decisions/` 전체를 origin/main과 비교하므로, 새 노트를 추가하면 실패한다. 이 PR은 그 테스트를 바꾸지 않는다. 브랜치에 있는 해당 파일 diff는 결정 PR에서 제외해 main 바이트로 되돌려야 한다. 해결 주체는 repository verification owner다. 추가형 결정 노트는 허용하면서 기존 노트·legacy 코드·vendor·골든의 byte guard는 유지하는 별도 선행 PR이 필요하다. 그 PR이 병합된 뒤 exact-head CI를 다시 돌린다. 그 전까지 이 노드의 CI는 그 한 검사에서 실패할 수 있다.
- `waiver-writeoff-decision`이 아직 결정되지 않아, 대상 키(`waiver_id` vs `advance_id`)는 그 노드가 이 규칙 안에서 확정한다.
- 여러 날에 걸친 합산은 `null`이다. 날을 넘겨 쪼개는 회피는 현재 시뮬레이션에서 잡히지 않는다.
- `capital-desk`가 실제 역할로 열리면 `approver_label` → `kix_role` 매핑과 기존 `authority` 블록의 재해석이 필요하다.
- 합성 라벨만 보고 "실제로 두 사람이 승인했다"고 읽힐 위험이 있다. 라벨 상수와 UI 표기로 완화되지만 없어지지는 않는다.

## 7. 후속 작업

- **선행(별도 승인 필요):** repository verification owner가 `tests/test_coa_candidate.py` guard 정책 수정 PR을 낸다. 그 PR이 병합된 뒤 이 결정 PR의 exact-head CI를 다시 실행한다.
- 세 build 노드:
  - 다음을 구현한다: `approvals[]`, `authority` 블록, `TWO_PERSON_REQUIRED`, `*_AGENT_FORBIDDEN`, 버킷 합산.
  - `GET /api/overlay`와 V3 export `overlay` 섹션에 반영한다.
  - 골든·`test_count`가 바뀌면 `CAPITAL-CLOSEOUT-REGEN-V1` 절차를 따른다.
- auth matrix와 문서:
  - `scripts/auth_matrix.py --write`/`--check`로 새 셀을 추가한다(호출자 축 불변).
  - 운영자 문서 라벨 표에 `LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED`·`TWO_PERSON_REQUIRED`를 넣은 뒤 `scripts/docs_surface.py --check`를 돌린다.
  - `docs/SEAMS.md` AuthorizerPort 행에 "두 번째 승인자: `capital-desk` 목표, 현재 `approver_label` 합성"을 한 줄 추가한다.
