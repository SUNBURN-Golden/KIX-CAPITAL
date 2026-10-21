# Capital 2인 승인 시뮬레이션 결정 — 승인자 identity 모델, capital-desk 역할 채택 여부, 임계값 출처, 동일 선지급 당일 합산, AI 제안 비승인, 증거 인용 형태, auth matrix·데스크 UI 영향

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
이 문서는 KIX-CAPITAL 저장소 안의 **시뮬레이션·제품 설계용** 결정이다. 2인 원칙은 **시뮬레이션 통제**이며 실제 sign-off 권한이 아니다. 청약이나 대출 제안이 아니고, 실자금이 움직이지 않으며, production은 계속 `NOT_AUTHORIZED`다. `approver_label`은 인증이 아니고 모든 승인 증거는 `LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED`를 단다. 어떤 upstream 계약(IdP, AgentGrant/ActionPermit, `ai-delegation-contract-mock` 등)의 채택도 주장하지 않는다. diff는 `docs/decisions/CAPITAL_SECOND_APPROVER.md` 한 파일이며, `capital/`·`tests/`·vendor 바이트·골든·pinned auth matrix·기존 결정 노트의 상태 토큰은 건드리지 않는다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `second-approver-decision` (Decision: two-person approval simulation — approver identity model, role choice and evidence shape) · deps `agent-proposal-lane`, `auth-matrix-freeze` · kind `decision` · user_merge `False` |
| 결정자 | **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)** |
| 위임 원문 | 2026-10-08 18:25 KST JunTae Park: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." |
| 결정일 | 2026-10-21 |
| 기준 | KIX-CAPITAL main `4cf1de3` · kix-protocol `4e3ce63` (읽기 전용 `/workspace/capital-run/kixproto-ro`) · vendor pin `7481b0e16ce9b903abbffa62249bb91cd9e63cfe` 불변 |
| 임계값 출처 규칙 | 임계값 숫자를 복사하지 않는다. `CAPITAL-TERMS-V1` `underwriting_depth.two_person_threshold_krw` 필드명으로만 인용한다(설명용 현재 값 50,000,000). |
| 상태 어휘 | **ADOPTED** = 위임 범위 안의 잠정 값. **UNDETERMINED** = 값을 정할 수 없어 이유만(`value: null`, 방향은 `target`). 여덟 항목 모두 ADOPTED다. |

## 1. 결정 요약

| item | 결정 (요지) | CAP rows | 소비 노드 / seam |
|---|---|---|---|
| `approver_identity_model` | **ADOPTED.** 승인자 = 명령 본문의 합성 `approver_label` 문자열 쌍. 서버는 **개수·구별·형식**만 검사하고 정체성·자격은 검사하지 않는다. 계정·비밀번호·개인정보 없음. 모든 표면에 `LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED` | CAP-19, CAP-01 | `overlay-recovery-writeoff`, `claim-slice-registry`, `waiver-writeoff-decision` 세 build 노드 공통 |
| `capital_desk_role_adoption` | **ADOPTED (비채택으로 채택).** deferred `capital-desk` 역할(`roles_v2` 다섯 번째 값)을 지금 auth matrix·`LocalRoleAuthorizer`에 넣지 않는다. 두 번째 승인자는 `approver_label`로만 표현하고, `capital-desk`는 OIDC `kix_role` 목표로만 인용 (`ROLE_TARGET_NOT_ADOPTED`) | CAP-19 | `docs/SEAMS.md` AuthorizerPort 행(문서 갱신만), 세 build 노드 |
| `threshold_value_source` | **ADOPTED.** 임계값의 유일한 출처는 `CAPITAL-TERMS-V1.underwriting_depth.two_person_threshold_krw`. 노트·코드·응답에는 `threshold_ref` 필드명 인용만 두고 숫자 리터럴을 새 상수로 복사하지 않는다 | CAP-01, CAP-04 | `TermsPolicyPort`(`capital/terms.py`) 경유 조회, 세 build 노드 |
| `same_advance_aggregation` | **ADOPTED.** 쪼개기 회피 차단: 같은 명령 계열의 **대상 키 × `sim_day`** 버킷으로 운영자가 제출한 금액을 누적해 임계값과 비교한다. 대상 키 = 회수·상각·가속은 `advance_id`, 슬라이스는 `slice_key`, 면제·상각 결정은 `waiver_id`/`advance_id` | CAP-04, CAP-03, CAP-08 | 세 build 노드 공통 규칙 |
| `agent_proposal_not_approval` | **ADOPTED.** agent lane 제안은 `approvals[]`에 들어가지 않고 승인 수에 세지 않는다. agent의 사람 전용 명령 POST는 403 `*_AGENT_FORBIDDEN`. 운영자 채택은 사람 명령이 `proposal_id`를 인용하고 자체 `approvals[]`를 갖는다 | CAP-19 | agent lane(`tests/agent_claims.json` 인용), 세 build 노드 |
| `evidence_citation_shape` | **ADOPTED.** 오버레이 엔트리 `payload.authority` 블록: `{mode: LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED, approvals: [{approver_label, sim_day}], proposal_refs: [], threshold_ref}` + receipt에 `two_person: {required, satisfied, distinct_approver_labels}`를 echo. 영수증 인용 키는 `overlay_id` | CAP-14, CAP-15, CAP-19 | 세 build 노드, `GET /api/overlay`, V3 `overlay` export 섹션 |
| `auth_matrix_effect` | **ADOPTED.** `KIX_CAPITAL_AUTH_MATRIX_V1`의 역할·호출자 축은 **불변**: 새 역할·새 호출자 열 없음. 2인 검사는 역할 검사 **통과 뒤** 핸들러 내부 정책이다. parked 노드가 새 라우트·명령을 추가하면 기존 `--write`/`--check` 재생성 절차로 셀만 추가한다 | CAP-19, CAP-20 | `tests/auth_matrix.json`, `scripts/auth_matrix.py`, 세 build 노드 |
| `desk_ui_flow` | **ADOPTED.** `#desk`는 단일 명령 제출 흐름을 유지: 금액 > 임계값이면 두 개의 `approver_label` 입력 칸(approver 1 / approver 2, 합성 표기)을 렌더하고 동일 라벨은 클라이언트에서도 거절. 별도 로그인·세션 분리·보류 큐 없음. 라벨 `SIMULATED` + `LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED` | CAP-20, CAP-19 | `capital/static/app.js` `#desk`, `tests/browser/operator-desk.spec.cjs` |

## 2. KIX 비전 연결 — 읽은 pack 경로

- `/workspace/capital-run/kixproto-ro/README.md` §1·§3·§4: 현재 범위는 mock·비운영이고 IdP·실인증·실자금은 잠겨 있다. 그래서 승인자 모델은 인증 없는 합성 라벨로 닫고, `capital-desk`는 "목표 역할"로만 둔다.
- `/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md` A-4: 기록과 재생, 권한과 커밋을 합치지 않는다. `approvals[]`는 기록이며 실행 허가가 아니고, 과거 승인 기록의 재생은 새 승인이 아니다.
- `docs/CAPITAL_REQUIREMENTS_KO.md`: CAP-19(로컬 합성 역할 organizer/auditor/observer/agent, `agent` 제안은 `HUMAN_PENDING`·`effects_executed=false`, IdP·KYC `NOT_BOUND`)와 CAP-01/04(사람 운영자 전용 오버레이 명령, U1–U6)가 이 노트의 표면이다.
- `docs/SEAMS.md` AuthorizerPort 행: `LocalRoleAuthorizer`·합성 loopback 역할은 인증이 아니며 upstream은 IdP+AgentGrant/ActionPermit이다. `capital-desk` 채택은 이 seam의 `NOT_BOUND`를 건드리지 않는 범위 밖이다.
- `docs/VALIDATION.md` `auth-matrix-freeze`: `tests/auth_matrix.json`은 25 라우트 × 5 호출자(organizer/auditor/observer/agent/무토큰) 125셀 + 명령 셀을 고정한 합성 표이며 자격정책이 아니다. 이 결정은 그 축을 바꾸지 않는다.
- `docs/decisions/CAPITAL_DEFAULT_RECOVERY.md` §권한: 이미 채택된 "금액 ≤ `two_person_threshold_krw` → 1인, 초과 → 서로 다른 `approver_label` 2개 이상, 409 `TWO_PERSON_REQUIRED`, 같은 `advance_id` 같은 `sim_day` 합산, `approver_label`은 인증 아님" 규칙을 이 노트가 정본 패턴으로 채택한다.
- `docs/decisions/CAPITAL_CLAIM_SLICE_REGISTRY.md` §3.8: 슬라이스 명령에 동일 규칙(`slice_key` × `sim_day` 합산, `SLICE_AGENT_FORBIDDEN`, AI 제안은 `PROPOSED`가 아니며 승인으로 세지 않음)을 이미 적용했다. 이 노트는 그 두 노트의 공통분모를 명명해 세 번째 소비자(`waiver-writeoff-decision`)가 같은 모양을 쓰게 한다.
- `docs/decisions/CAPITAL_DEMO_BOOK.md`·`docs/decisions/CAPITAL_ARTIFACT_BUNDLING.md`·`docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md`(인용만): 한도 인용 규칙, `auth matrix` 불변 조건, IdP/KYC 비채택과 `capital-desk`의 deferred 위치(`roles_v2`)를 따른다.
- 「포부」의 번역: 지금 2인 규칙을 **하나의 명명된 패턴**으로 고정해 두면, IdP/`capital-desk`가 실제로 열릴 때 `approver_label` → `kix_role` 매핑 자리가 이미 있다. 실제 승인 권한은 지금 아무에게도 없다.

## 3. 항목별 결정

### 3.1 approver_identity_model (CAP-19, CAP-01) — ADOPTED

- **값.** 승인자는 사람 운영자 명령 본문의 `approvals[]` 안 **합성 `approver_label` 문자열**이다. 형식: `^[a-z][a-z0-9-]{0,31}$`, 엔트리당 최대 4개. 서버는 (a) `approver_label` 형식, (b) `approvals` 길이, (c) 서로 다른 라벨 수만 검사한다. 라벨이 실제 사람·계정·좌석·자격과 대응하는지는 검사하지 않고 검사할 수단도 없다.
- **라벨.** 명령 응답·오버레이 엔트리·조회·export에 상수 `authority: LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED`를 단다. `actor`가 인증이 아니듯 `approver_label`도 인증이 아니다(SEAMS `GateHttpProducer`의 "actor is not authentication"과 같은 문구).
- **근거.** CAP-19는 계정·비밀번호·개인정보 없음을 못 박았고 AuthorizerPort는 `NOT_BOUND`다. 두 선행 노트가 이미 이 모양으로 채택됐으므로 세 build 노드가 다른 identity 모델을 만들 이유가 없다.
- **대안.** 고정 로스터(`sim-desk-a`/`sim-desk-b`) 강제: 구별 규칙만으로 시연이 되고 로스터는 진짜 계정처럼 오독될 수 있어 기각. 단일 서명 필드: 2인 구별을 표현 못 해 기각.

### 3.2 capital_desk_role_adoption (CAP-19) — ADOPTED (값: 비채택)

- **값.** `capital-desk`(바인딩 노트 `roles_v2`의 두 번째 승인자 목표 역할, OIDC bearer `kix_role`로 매핑될 값)를 지금의 `LocalRoleAuthorizer`·auth matrix·라우트 권한에 **추가하지 않는다.** 상태 라벨 `ROLE_TARGET_NOT_ADOPTED`. 두 번째 승인자는 §3.1의 `approver_label`로만 존재한다.
- **근거.** 역할 채택은 IdP·KYC 제공자 결정(현재 `UNDETERMINED — 법무·인허가·JunTae 지정`)과 auth matrix 축 변경을 수반하며 이 노드의 시뮬레이션 범위를 넘는다. 외부 게이트 노트의 파일럿 형태("운영자 데스크 `capital-desk` 전용과 2인 원칙")는 실자금 해제 시점의 목표이지 현재 구현 지시가 아니다.
- **대안.** 지금 `capital-desk`를 다섯 번째 역할로 추가: pinned matrix의 호출자 축을 깨고 인증 없는 역할이 인증처럼 보이게 해 기각. 대신 `approver_label` 값이 나중에 `kix_role=capital-desk` principal로 대체될 자리를 `payload.authority`에 남긴다.

### 3.3 threshold_value_source (CAP-01, CAP-04) — ADOPTED

- **값.** 임계값의 유일 출처는 `CAPITAL-TERMS-V1` `underwriting_depth.two_person_threshold_krw`다. 코드는 `TermsPolicyPort`에서 읽고, 노트·엔트리·응답은 `threshold_ref: "CAPITAL-TERMS-V1.underwriting_depth.two_person_threshold_krw"`로 인용한다. 이 문서의 50,000,000은 설명용 현재 값이며 새 상수 선언이 아니다. TERMS 개정으로 값이 바뀌면 폴드·검사는 재기동 없이 새 값을 따르고, 이미 기록된 엔트리는 기록 당시 평가를 유지한다.
- **근거.** 한도 출처 규칙(숫자 복사 금지)은 claim-slice·demo-book 두 노트가 이미 지킨 규칙이며, `ai-delegation-contract-mock`이 AgentGrant/ActionPermit을 정하면 같은 금액 scope로 결합된다는 TERMS의 표기와 일치한다.
- **대안.** 승인 전용 별도 임계값: 같은 U5 금액 scope를 두 숫자로 나눠 드리프트를 만들어 기각.

### 3.4 same_advance_aggregation (CAP-04, CAP-03, CAP-08) — ADOPTED

- **값.** `amount_bucket = (command_family, target_key, sim_day)`. `target_key`: 회수·상각·가속·부도 계열은 `advance_id`, 슬라이스 계열은 `slice_key`, waiver/writeoff 계열은 그 노드가 정한 대상 id(`waiver_id` 없으면 `advance_id`). 같은 버킷에서 **운영자가 같은 `sim_day`에 제출·적용한 금액 합**을 누적해 그 누적치가 임계값을 넘는 순간부터 해당 버킷의 모든 명령에 2인을 요구한다. 임계값 이하로 쪼개 연속 게시하면 누적 합으로 재평가되어 막힌다(`TWO_PERSON_REQUIRED`).
- **근거.** DEFAULT_RECOVERY("같은 `advance_id`·같은 `sim_day` 회수 합계 누적")와 CLAIM_SLICE("같은 `slice_key`·같은 `sim_day` 금액 누적")가 이미 같은 규칙을 채택했다. `sim_day`는 오버레이 시계의 유일한 날짜 단위이므로 버킷 경계가 결정론적이다.
- **대안.** 명령당 평가만: 같은 날 40+40으로 80을 나눠 쓰는 회피를 허용해 기각. 영구 누적(`sim_day` 무시): 날이 지나면 새 평가가 합리적인 단기 통제의 본래 의미와 어긋나 기각하되, cross-day 영구 합산은 실자금 정책의 몫으로 `target`만 남긴다.

### 3.5 agent_proposal_not_approval (CAP-19) — ADOPTED

- **값.** (1) agent lane은 `QUERY`·`PROPOSE`만 호출하고 제안은 `HUMAN_PENDING`·`effects_executed=false`다. (2) `approvals[]` 안의 `approver_label`은 사람 명령 본문 필드이며, agent가 보낸 사람 전용 명령은 역할 검사에서 403 `*_AGENT_FORBIDDEN`으로 거절된다(agent의 `approver_label`은 검사 전에 배제된다). (3) 운영자가 제안을 채택하면 사람 명령의 `payload.authority.proposal_refs`에 `proposal_id`를 인용하고 자체 `approvals[]`를 채운다. 인용은 근거 표시일 뿐 승인 수에 더하지 않는다 — proposal을 넣은 사람 명령도 임계 초과 시 두 `approver_label`이 필요하다.
- **근거.** U5(`HUMAN_OPERATOR_TWO_PERSON; AI proposes only`)와 두 선행 노트, `tests/agent_claims.json`의 `executionAuthorized=false` 고정과 일치한다. AI가 `approver_label`을 하나라도 채울 수 있으면 2인 원칙의 의미가 사라진다.
- **대안.** AI 제안을 첫 승인으로 카운트: 위임 초안·U5 정면 위반이라 기각.

### 3.6 evidence_citation_shape (CAP-14, CAP-15, CAP-19) — ADOPTED

- **값.** 오버레이 엔트리 `payload.authority`:
  `{"mode":"LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED","approvals":[{"approver_label":"...","sim_day":n},...],"proposal_refs":["..."],"threshold_ref":"CAPITAL-TERMS-V1.underwriting_depth.two_person_threshold_krw"}`.
  명령 receipt는 `two_person: {"required":bool,"satisfied":bool,"distinct_approver_labels":n,"amount_bucket":"<family>/<target>/<sim_day>"}`를 echo하고, 영수증·조회의 인용 키는 채택된 `overlay_id`다. `sim_day` 외 시각·세션 id·토큰은 기록하지 않는다(기록할 인증이 없고 digest 안정성을 해친다).
- **근거.** `overlay_id`/`kind`/`payload` 엔트리 형태와 dedup은 이미 채택됐고, receipt echo는 `test_producer_port` 계열의 증거 관행과 같다. 인증 없는 세션을 인증으로 보이게 하는 필드(토큰 해시·세션 id)를 두지 않는다.
- **대안.** 별도 "approval receipt" 오브젝트: 새 저장 경계·새 digest라 기각(자체 저장엔진 금지와 동일 이유).

### 3.7 auth_matrix_effect (CAP-19, CAP-20) — ADOPTED

- **값.** `tests/auth_matrix.json`(`KIX_CAPITAL_AUTH_MATRIX_V1`)의 역할·호출자·권한 표는 이 결정으로 **0셀** 바뀐다. 2인 검사는 라우트·명령의 역할 검사(organizer 전용) **통과 뒤** 핸들러에서 일어나며, 실패 시 409 `TWO_PERSON_REQUIRED`(인가 실패 403이 아님)다 — 라벨 부족은 권한 부족이 아니라 정책 미충족이다. parked 노드가 새 라우트·명령을 추가하면 `scripts/auth_matrix.py --write` 재생성 + `--check` 절차로 **같은 다섯 호출자 축**의 새 셀만 추가한다.
- **근거.** `auth-matrix-freeze` 선행이 표를 고정한 목적은 관측 동작의 드리프트 감지이지 확장 금지가 아니다. 역할 축을 건드리는 것만이 이 선행과 충돌한다.
- **대안.** 2인 실패를 403으로: 역할은 통과했으므로 의미가 틀리고 matrix의 거절 코드 표기와 충돌해 기각.

### 3.8 desk_ui_flow (CAP-20, CAP-19) — ADOPTED

- **값.** `#desk`는 단일 명령 제출을 유지한다. 금액 입력이 임계값을 넘으면(클라이언트는 `threshold_ref` 값을 서버 응답으로만 표시하고 자체 산술로 판정하지 않는다 — 서버 거절이 정본) 폼에 `approver 1`·`approver 2` 두 입력 칸과 "합성 라벨 — 인증 아님(`LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED`)" 표기를 렌더한다. 두 칸이 같으면 클라이언트에서도 제출 전 거절하되 서버 409가 정본이다. 별도 로그인·제2 세션·보류 큐·서명 위젯 없음. 브라우저 테스트는 임계 초과 정상 경로(두 라벨)와 임계 이하 단일 라벨 경로를 둘 다 고정한다.
- **근거.** 채택된 명령 형태가 `approvals[]`를 한 번에 받으므로, 보류 큐는 명령 형태를 다시 열어야 하고 상태·재시도 의미를 새로 만들어야 한다. 단일 제출 + 두 라벨이 가장 작은 정직한 시연이다.
- **대안.** PENDING_SECOND_APPROVAL 큐: 더 진짜 같지만 명령 수명·dedup·재평가 규칙을 새로 요구해 기각(향후 실제 2인 워크플로 결정의 `target`으로 남김).

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "second-approver-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-10-21",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "scope": "KIX-CAPITAL simulation and product design only; the two-person rule is a SIMULATED control, not sign-off authority; no real money; production NOT_AUTHORIZED; approver_label is not authentication; no upstream contract claimed adopted",
  "delegation": "2026-10-08 18:25 KST JunTae Park delegated financial terms, settlement policy, upstream binding and accounts/tax/legal; this node decided by Sonnet 5.5 xhigh under the same delegation (lanes 10-16 09:07)",
  "bases": {"capital_main": "4cf1de3", "kix_protocol": "4e3ce63", "vendor_pin_commit": "7481b0e16ce9b903abbffa62249bb91cd9e63cfe", "terms_version": "CAPITAL-TERMS-V1", "auth_matrix_version": "KIX_CAPITAL_AUTH_MATRIX_V1"},
  "upstream_adoption_claimed": false,
  "consumers": ["overlay-recovery-writeoff", "claim-slice-registry", "waiver-writeoff-decision"],
  "entries": {
    "approver_identity_model": {
      "status": "ADOPTED",
      "value": {"model": "SYNTHETIC_APPROVER_LABELS", "location": "command body approvals[].approver_label", "pattern": "^[a-z][a-z0-9-]{0,31}$", "max_approvals_per_command": 4, "server_checks": ["label format", "approvals count", "distinct label count"], "not_checked": ["real identity", "accounts", "credentials", "seats"], "label": "LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED"},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-21",
      "cap_rows": ["CAP-19", "CAP-01"],
      "rationale": "CAP-19 forbids accounts/passwords/PII and AuthorizerPort is NOT_BOUND; distinct synthetic labels are the only honest way to simulate two persons and match both prior notes.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "capital_desk_role_adoption": {
      "status": "ADOPTED",
      "value": {"adopted_as_role": false, "role_state": "ROLE_TARGET_NOT_ADOPTED", "target": "capital-desk stays the deferred upstream role (binding note roles_v2 fifth value, mapped from OIDC kix_role claim); second approver is expressed only as a distinct approver_label; adoption waits on IdP vendor + KYC provider (UNDETERMINED, JunTae/legal designate)"},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-21",
      "cap_rows": ["CAP-19"],
      "rationale": "Adding capital-desk now would mutate the pinned caller axis and make an unauthenticated role look like authentication; it remains the target shape for real-funds lift.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "threshold_value_source": {
      "status": "ADOPTED",
      "value": {"threshold_ref": "CAPITAL-TERMS-V1.underwriting_depth.two_person_threshold_krw", "read_via": "TermsPolicyPort", "literal_copied": false, "recompute_on_terms_revision": true, "recorded_entries_keep_evaluation_at_write": true},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-21",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Single source avoids a second drift-prone number and matches the citation-only cap rule already used by claim-slice-registry and demo-book.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "same_advance_aggregation": {
      "status": "ADOPTED",
      "value": {"bucket": "(command_family, target_key, sim_day)", "target_keys": {"recovery_writeoff_acceleration_default": "advance_id", "claim_slice": "slice_key", "waiver_writeoff": "waiver_id_or_advance_id"}, "rule": "cumulative operator-submitted amount in the bucket is compared to the threshold; crossing mid-day makes every further command in the bucket two-person", "reject": "409 TWO_PERSON_REQUIRED", "cross_day_cumulative": {"value": null, "target": "permanent cumulative aggregation across sim_days is a real-funds policy choice, deferred to f04-real-funds-lift-criteria"}},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-21",
      "cap_rows": ["CAP-04", "CAP-03", "CAP-08"],
      "rationale": "Same-day per-target summation is the already-adopted split-evasion guard in default-recovery and claim-slice; generalizing it names one pattern for all three consumers.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "agent_proposal_not_approval": {
      "status": "ADOPTED",
      "value": {"agent_may": ["QUERY", "PROPOSE"], "proposal_state": "HUMAN_PENDING", "effects_executed": false, "counts_as_approval": false, "agent_command_post": "403 *_AGENT_FORBIDDEN before approvals inspection", "human_adoption": "human command cites proposal_id in authority.proposal_refs and supplies its own approvals[]"},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-21",
      "cap_rows": ["CAP-19"],
      "rationale": "U5 and the agent lane fix AI to proposal-only; counting a proposal as an approval would dissolve the two-person control.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "evidence_citation_shape": {
      "status": "ADOPTED",
      "value": {"entry_payload_authority": {"mode": "LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED", "approvals": [{"approver_label": "string", "sim_day": "integer"}], "proposal_refs": ["proposal_id"], "threshold_ref": "CAPITAL-TERMS-V1.underwriting_depth.two_person_threshold_krw"}, "receipt_echo": {"two_person": {"required": "bool", "satisfied": "bool", "distinct_approver_labels": "int", "amount_bucket": "family/target/sim_day"}}, "citation_key": "overlay_id", "not_recorded": ["wall-clock time", "session id", "token material"]},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-21",
      "cap_rows": ["CAP-14", "CAP-15", "CAP-19"],
      "rationale": "Reuses the adopted overlay_id/kind/payload shape and digest-stable sim_day; recording token-like fields would pretend authentication exists.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "auth_matrix_effect": {
      "status": "ADOPTED",
      "value": {"caller_axis_changed": false, "cells_changed_by_this_decision": 0, "check_layer": "post-role handler policy", "failure_code": "409 TWO_PERSON_REQUIRED (not 403)", "extension_procedure": "new routes/commands from parked nodes add cells on the same five-caller axis via scripts/auth_matrix.py --write + --check"},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-21",
      "cap_rows": ["CAP-19", "CAP-20"],
      "rationale": "auth-matrix-freeze pins the observed role axis; the two-person rule is a policy check after role admission, so no axis or cell changes.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "desk_ui_flow": {
      "status": "ADOPTED",
      "value": {"flow": "single command submit carrying approvals[]", "above_threshold_ui": "two approver_label fields labelled synthetic; equal labels rejected client-side; server 409 is authoritative; threshold displayed from server response, no client arithmetic", "absent": ["separate login", "second session", "pending-approval queue", "signature widget"], "labels": ["SIMULATED", "LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED"], "target": "a real pending-second-approval workflow remains for the real-funds decision"},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-21",
      "cap_rows": ["CAP-20", "CAP-19"],
      "rationale": "The adopted command shape takes both labels at once; a queue would reopen command lifecycle and dedup semantics for no simulation gain.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

- `docs/decisions/CAPITAL_SECOND_APPROVER.md`가 `capital-decision-v1` 블록 하나로 여덟 항목 전부의 `status`를 담는다 → §4(모두 ADOPTED).
- approver 라벨을 합성으로 유지하고 `LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED`를 단다 → §3.1·§3.6.
- agent 제안이 승인 수에 들어가지 않는다 → §3.5(`counts_as_approval: false`, 403 경로).
- 이 노트를 소비하는 parked build 노드 명명 → §1 표와 §4 `consumers`: `overlay-recovery-writeoff`, `claim-slice-registry`, `waiver-writeoff-decision`.

## 6. Open risks

- `waiver-writeoff-decision`이 아직 결정 전이라 대상 키(`waiver_id` vs `advance_id`)는 그 노드가 이 규칙 안에서 확정한다.
- cross-day 영구 합산은 실자금 정책의 몫으로 `null`이다 — 임계값 회피가 날을 넘으면 현재 시뮬레이션은 잡지 않는다.
- `capital-desk`가 실제 역할로 열릴 때 `approver_label` → `kix_role` 매핑과 기존 `authority` 블록의 재해석이 필요하다.
- 합성 라벨이 익명이므로 데모 관찰자가 "두 명이 실제로 승인했다"로 읽을 위험 — 라벨 상수와 UI 표기로 완화하되 제거되지 않는다.

## 7. 후속 작업

- 세 build 노드: 명령에 `approvals[]`·`authority` 블록·`TWO_PERSON_REQUIRED`·`*_AGENT_FORBIDDEN`·버킷 합산 구현, `GET /api/overlay` 조회와 V3 export `overlay` 섹션 반영, 골든·`test_count` 변화 시 `CAPITAL-CLOSEOUT-REGEN-V1` 절차.
- `scripts/auth_matrix.py --write`/`--check`로 새 라우트·명령 셀 추가(호출자 축 불변), `docs/OPERATOR_HANDBOOK_KO.md` 라벨 표에 `LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED`·`TWO_PERSON_REQUIRED` 문구 추가 후 `scripts/docs_surface.py --check`.
- `docs/SEAMS.md` AuthorizerPort 행 설명에 "두 번째 승인자는 `capital-desk` 목표 역할, 현재 `approver_label` 합성"을 한 줄 반영.
