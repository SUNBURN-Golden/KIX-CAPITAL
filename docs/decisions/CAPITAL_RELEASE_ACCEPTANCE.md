# Capital 출시 수용 결정 — 점검표 판정, 시뮬레이션 산출물 수용, 운영 승인, 잔여 보류 목록

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
이 문서는 KIX-CAPITAL 저장소 안의 **시뮬레이션·제품 설계용** 결정이다. 청약이나 대출 제안이 아니고, 실자금이 움직이지 않으며, production은 계속 `NOT_AUTHORIZED`다. 돈을 쓰거나, 배포하거나, 비밀·과금을 건드리는 항목은 이 문서가 실행하지 않고 `PENDING_OWNER_ACTION`으로 JunTae에게 남긴다. 법률·세무·회계 관련 내용은 전문가 검토 전의 작업 가정이다. 어떤 upstream 노드도 완료로 표시하지 않는다. 이 문서는 읽기만으로 작성했다. `scripts/acceptance.py`를 실행하지 않았고 `build/acceptance-evidence.json`을 읽지 않았다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `release-acceptance-decision` (Decision: human product acceptance and release authorization) · kind `decision` · user_merge `False` |
| 결정자 | **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)** |
| 위임 원문 | 2026-10-08 JunTae: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." |
| 결정일 | 2026-10-17 |
| 기준 | KIX-CAPITAL main `4d04a5b` · kix-protocol `244595d` (읽기 전용) |
| 이 문서가 읽은 파일 | `docs/OPERATOR_HANDBOOK_KO.md`, `docs/ACCEPTANCE_KO.md`, `capital/readiness.py`, 선행 결정 노트 네 개(`CAPITAL_FINANCIAL_TERMS.md`, `CAPITAL_SETTLEMENT_POLICY.md`, `CAPITAL_UPSTREAM_BINDING.md`, `CAPITAL_ACCOUNTS_TAX_LEGAL.md`), kix-protocol `README.md`와 `AUTHORITY_MODEL_1.md`. 감독자 팩의 `RELEASES.md`와 `VALIDATION.md` 발췌도 참고했다 |
| 읽지 않은 것 | 증거 파일, 서비스 코드, 테스트, `CAP_COVERAGE.md`, 병합된 다섯 노트(`CAPITAL_OVERLAY_STATE`, `CAPITAL_SHADOW_POLICY`, `CAPITAL_DEMO_BOOK`, `CAPITAL_ARTIFACT_BUNDLING`, `CAPITAL_OVERLAY_DIGEST_EXPORT`). 이 범위는 감독자가 정했다. |

## 2. 결정 요약

| item | 결정 | CAP rows | consumer |
|---|---|---|---|
| `handbook_checklist_verdict` | 사람 점검표 다섯 칸 모두 **defer**(2026-10-17). 증거 파일을 보지 못해 pass를 줄 수 없고, 실패 증거도 없어 fail도 아니다. 칸은 비워 둔다 | CAP-20 | `docs/ACCEPTANCE_KO.md`, `scripts/acceptance.py` |
| `simulation_deliverable_acceptance` | 제품화된 **로컬 시뮬레이션**을 Capital 산출물로 **잠정 수용**한다. 다섯 칸이 사람 손으로 통과해야 유지된다. 사람 수용은 기록된 적 없다 | CAP-20 | 운영 핸드북, `GET /api/readiness`(`local-simulation`) |
| `production_authorization` | **NOT_AUTHORIZED: owner action pending.** 실자금·실서비스·배포는 승인하지 않는다. 해제 조건은 `PENDING_OWNER_ACTION` 아홉 개 | CAP-20 | `release` 그룹, `f04-real-funds-lift-criteria`(사용자 노드) |
| `remaining_holds_inventory` | 20개 CAP 행을 한 줄도 빼지 않고 결정 노트 상태와 함께 목록화한다(§4.4) | CAP-02, 03, 07, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20 | `GET /api/decisions`, `not_bound_checklist.py` |
| `readiness_production_authorized` | `production_authorized`는 false로 유지한다. 이 결정은 코드를 바꾸지 않는다 | CAP-20 | `GET /api/readiness` |

## 3. KIX 비전 연결

- `/workspace/capital-run/kixproto-ro/README.md` §3·§4. 실자금, 실 PG·은행·KYC, 공개 운영 엔드포인트, mainnet은 계속 잠겨 있고 Track P 산출물은 모두 "mock·비운영 범위"다. 같은 잣대로 Capital의 수용 대상은 로컬 시뮬레이션이고 출시가 아니다. README는 "원본 증거를 현재 결과로 재라벨링하지 않습니다"라고도 한다. 그래서 읽지 못한 증거에 pass를 주지 않는다.
- `/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md`. "예약 확정 ≠ 결제 확인 ≠ 체인 권리 발행 완료"와 "과거 사실 재생은 새로운 외부 실행 허가가 아님"을 수용에 옮기면 이렇게 된다. 합성 여정이 통과해도 실자금 실행 권한이 되지 않고, 산출물 수용도 출시 허가가 되지 않는다. A-5의 "추정 승인은 착수 승인이 아니다"가 같은 구조다.
- 원대한 포부와의 관계. 시뮬레이션 수용은 천장이 아니라 바닥이다. 이 문서는 시뮬레이션의 경계를 확정하고 출시로 가는 문을 이름 붙여 남긴다(§4.3). 문을 여는 열쇠는 JunTae가 가진다.

## 4. 항목별 결정

### 4.1 handbook_checklist_verdict

`ACCEPTANCE_KO.md`의 사람 점검표는 다섯 칸이고 모두 `build/acceptance-evidence.json`을 읽어야 채워진다. 이 파일은 커밋되지 않고 실행마다 달라진다. 읽기 전용 작성자는 이 파일을 만들 수도, 읽을 수도 없다. 문서 정합성은 확인했다. Protocol pin `7481b0e1…`은 `RELEASES.md`와 결정 노트들에서 같고, 라벨은 `readiness.py`와 핸드북에서 일관된다. 다만 이것은 칸의 합격 기준(`evidence.*` 값)이 아니다.

| 점검 칸 | 합격 기준(원문 요지) | 판정 | 일자 | 이유 |
|---|---|---|---|---|
| 사다리 결과 | `evidence.ok == true`, 여덟 stage 모두 `passed` | **defer** | 2026-10-17 | 증거 파일 미열람 |
| 정직 라벨 | `label == SIMULATED`, `funds_executed == false` | **defer** | 2026-10-17 | 증거 파일 미열람. 문서상 라벨은 일관됨 |
| vendor 바이트 | `vendor_hashes.verified == true` | **defer** | 2026-10-17 | 해시를 직접 대조하지 않음 |
| golden digest | `golden_digests.status == "recorded"` | **defer** | 2026-10-17 | 증거 파일 미열람 |
| 추적 정보 | `head_sha` 존재, `tool_versions.*` 다섯 값 비지 않음 | **defer** | 2026-10-17 | 증거 파일 미열람 |

기준 HEAD는 main `4d04a5b`다. 사람이 증거를 읽을 때 `evidence.head_sha`를 수용하려는 커밋과 대조해 기록한다. 이 노트가 병합되면 HEAD는 `4d04a5b`와 달라진다. 이 문서는 `ACCEPTANCE_KO.md`의 체크박스를 채우지 않는다. 그 칸의 규칙이 "칸은 비워 둔다"이기 때문이다.

### 4.2 simulation_deliverable_acceptance

**결정: 제품화된 로컬 시뮬레이션을 Capital 산출물로 잠정 수용한다. 단 `PROVISIONAL_CONDITIONAL`이다.**

- **산출물.** 체크아웃 또는 `capital-0.1.0.pyz`(`LOCAL_SIMULATION_ARTIFACT`, `signed: false`, `published: false`)로 켜는 루프백 서버다. 합성 F04 여정, 역할 레인(organizer·auditor·observer·simulated agent), 읽기 전용 오버레이(조건·정책·그림자 산술·심사 기록·상계 견적·포트폴리오·시뮬레이션 시계·마진), 내용 주소 export manifest와 오프라인 검증기, 결정 색인, 로컬 관측이 들어 있다. 숫자는 모두 합성 fixture다.
- **수용 범위.** `readiness.py`의 `local-simulation` 그룹이 이미 말하는 범위(`AVAILABLE_LOCAL`, "로컬 합성 프로파일만 사용 가능; 전체 금융 완료 아님")와 같다. 그 밖은 수용하지 않는다.
- **조건.** 사람이 다섯 칸을 pass로 채워야 이 수용이 유지된다. 다음 중 하나라도 일어나면 수용이 자동으로 효력을 잃는다.
  - 점검표 한 칸이 fail이다.
  - `evidence.funds_executed`가 true다.
  - 라벨이 `SIMULATED`가 아니다.
  - vendor 바이트가 어긋난다.
  - `/api/readiness`의 `production_authorized`가 true다.
- **이것이 아닌 것.** 사람 수용이 아니다. 핸드북은 "사람 수용은 아직 없다. 자동 검사가 통과해도 사람이 수용한 것이 아니다"라고 하고, 이 결정은 그 문장을 바꾸지 않는다. 위임된 결정자의 산출물 범위 수용이고, 사람 서명은 `PENDING_OWNER_ACTION`(POA-1)이다. 출시 허가도, 독립 감사 대체도 아니다.

`readiness.py`에서 CAP-20은 `local-simulation`(AVAILABLE_LOCAL)과 `release`(NOT_AUTHORIZED)에 모두 나온다. 이 결정은 그것을 이렇게 읽는다. 앞쪽은 위 조건으로 잠정 수용하고, 뒤쪽은 계속 막힌다. 두 그룹의 데이터는 바꾸지 않는다.

### 4.3 production_authorization

**결정: NOT_AUTHORIZED: owner action pending.** 실대출, PG·은행 연동, KYC, 공개 배포, 키·비밀 취급은 이 루프가 실행하지 않는다. 아래 아홉 개는 JunTae의 `PENDING_OWNER_ACTION`이다.

| id | 항목 | 근거 |
|---|---|---|
| POA-1 | 점검표 실행·증거 열람·다섯 칸 서명(사람 수용) | `ACCEPTANCE_KO.md` |
| POA-2 | 실자금 해제 결정(`f04-real-funds-lift-criteria`, 사용자 노드) | `CAPITAL_ACCOUNTS_TAX_LEGAL.md` licence gate |
| POA-3 | 대부 주체와 등록·인허가 판단(`CAPITAL-LICENCE-ROUTE-V1`은 `PENDING_PROFESSIONAL_REVIEW`, 법률 자문 지명) | 같은 노트 |
| POA-4 | PG·은행·KYC 벤더 계약, 자격증명·비밀 취급(Toss는 잠정 선택이고 최종 가맹은 미확인, IdP/KYC 벤더는 UNDETERMINED) | kix-protocol `README.md` §4, 상위 연동 노트 |
| POA-5 | 공개 엔드포인트·TLS·DNS·ingress 운영자 지정(지금은 루프백 전용, Capital은 TLS를 종단하지 않음) | `deployment_tls_retention` |
| POA-6 | zipapp 서명·게시·호스팅 채널 선택 | `RELEASES.md` |
| POA-7 | 보존 기간 다섯 칸의 값(법무·Toss·Astra·회계사 답변) | `data_retention_privacy` |
| POA-8 | 호스팅·CI·벤더 과금·쿼터 승인(승인 전 지출 없음) | 위임 범위 밖 |
| POA-9 | 회계·세무 전문가 검토와, 해당될 때 독립 감사(`release` 차단 사유 첫 줄) | `readiness.py` |

### 4.4 remaining_holds_inventory

CAP 20개 중 `AVAILABLE_LOCAL`은 CAP-01, 04, 05, 06, 08, 09, 10, 14, 20이다. 이 중 CAP-04와 CAP-14는 아래 보류에도 걸쳐 있어 두 번 센다. 아래 표가 나머지 행과 결정 노트 상태를 모두 담는다. 빠진 행은 0이다.

| id | 보류 | CAP | 결정 노트 상태 | 보류 내용 / 다음 |
|---|---|---|---|---|
| H1 | 금융 조건 | 01, 04 (02·03 연결) | `CAPITAL_FINANCIAL_TERMS.md`: 9개 모두 ADOPTED(잠정, `CAPITAL-TERMS-V1`) | 읽기 전용 오버레이만. 청약 아님. 대부 주체는 H4 |
| H2 | 정산 정책 | 02, 03, 04 | `CAPITAL_SETTLEMENT_POLICY.md`: 6개 모두 ADOPTED(잠정) | 고정 FSM이 대부분 표현하지 못한다. readiness는 `DECISION_REQUIRED`다. CAP-03은 V1 `NOT_OFFERED`다. 그림자 산술만 있고 수익 참여·채권 매입·잔여·늦은 현금은 `SHADOW_DEFERRED`다 |
| H3a | producer 연결 | 07, 16 | `CAPITAL_UPSTREAM_BINDING.md`: `producer_sdk_tuple`, `t01_t06_qualification` DEFERRED | `UPSTREAM_REQUIRED`. SEMANTIC_CONFORMANCE tuple 없음 |
| H3b | 내구 원장·투영·export | 11, 13, 14, 15 | 같은 노트: `stage5_durable_backend`, `stage6_finance_candidates`, `stage7_authenticated_export` DEFERRED | `UPSTREAM_REQUIRED`. `LOCAL_FILE_WORKSPACE`와 DEV HMAC은 stage5·7이 아니다 |
| H3c | 자산·권리 규모·AI | 12, 17, 18, 19 | 같은 노트: `asset_registry_fx`, `rights_scale_privacy`, `token_layer_coin_lock` DEFERRED. `ai_agent_grant_action_permit` ADOPTED | `UPSTREAM_REQUIRED`. KRW AssetSpec은 PROVISIONAL이고, agent 레인은 propose-only 시뮬레이션이다 |
| H3d | 신원·배포 | 15, 20 | 같은 노트: `identity_provider_kyc` NOT_ADOPTED, `deployment_tls_retention` DEFERRED | IdP·KYC·TLS·공개 배포 없음 |
| H4 | 회계·세무·법무·보존 | 13, 15 (03·20 연결) | `CAPITAL_ACCOUNTS_TAX_LEGAL.md`: 5개 모두 ADOPTED이며 basis `WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW` | 인허가 적용 여부는 `PENDING_PROFESSIONAL_REVIEW`. 보존 칸 다섯은 기간 미설정 |
| H5 | 오버레이 상태 | 01 | `CAPITAL_OVERLAY_STATE.md`: 루프 상태 MERGED. 항목 상태는 이 노드에서 다시 읽지 않음 | 항목 상태는 `GET /api/decisions` |
| H6 | 그림자 정책 | 02, 03 | `CAPITAL_SHADOW_POLICY.md`: MERGED. 항목 미열람 | `SHADOW_NOT_APPLIED`. FSM·자금 집행 아님 |
| H7 | 데모 장부 | 04, 06 | `CAPITAL_DEMO_BOOK.md`: MERGED. 항목 미열람 | `SYNTHETIC_FIXTURE_PROFILE`일 뿐 실제 익스포저가 아니다 |
| H8 | 산출물 문서 번들링 | 20 | `CAPITAL_ARTIFACT_BUNDLING.md`: MERGED. 항목 미열람 | 4d04a5b의 핸드북은 `.pyz`에 `docs/`가 없어 조건·정책·결정 색인이 `NOT_BOUND`라고 쓴다. 노트와 대조가 필요하다(§7, §8) |
| H9 | 오버레이 digest export | 11, 15 | `CAPITAL_OVERLAY_DIGEST_EXPORT.md`: MERGED. 항목 미열람 | DEV HMAC은 무결성만이다. stage7 인증 export가 아니다 |
| H10 | 출시 | 20 | 이 노트: 아래 §5의 두 항목 | `NOT_AUTHORIZED`, POA-1~9 |

`external-gate-decision`은 같은 위임으로 따로 결정한다. 이 문서는 `real_funds_pilot`, `public_endpoint_tls`, `idp_kyc_vendor`, `licensed_lender_entity` 항목을 만들지 않고, 위 POA와 H3d·H4에서 이름만 가리킨다.

### 4.5 readiness_production_authorized

**결정: `GET /api/readiness`의 `production_authorized`는 false로 유지한다.** `capital/readiness.py`의 `release` 그룹은 `NOT_AUTHORIZED`이고 claim은 "개발 CI는 실거래 또는 배포 승인이 아님"이다. 핸드북도 `production_authorized`와 `policy_adopted`가 false라고 쓴다. 이 노드는 문서만 더하고 코드를 바꾸지 않으므로 값이 뒤집힐 길이 없다. 단 `production_authorized` 키 자체는 서비스의 `readiness()`가 만들고, 이 노드는 그 코드를 읽지 않았다. 이 값이 true가 되려면 POA-1~9가 JunTae의 명시 승인으로 해소된 뒤 별도 노드가 필요하다.

## 5. capital-decision-v1

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "release-acceptance-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-10-17",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "entries": {
    "handbook_checklist_verdict": {
      "status": "ADOPTED",
      "value": {
        "evidence_file": "build/acceptance-evidence.json",
        "evidence_read": false,
        "head_sha": "4d04a5b",
        "verdict_date": "2026-10-17",
        "items": {
          "ladder_result": "defer",
          "honest_label": "defer",
          "vendor_bytes": "defer",
          "golden_digest": "defer",
          "traceability": "defer"
        },
        "checkboxes_ticked": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-20"],
      "rationale": "All five human checklist items depend on build/acceptance-evidence.json, which is uncommitted and was not read or generated by this read-only docs decision. Without observation there is no honest pass, and no failing evidence exists, so each item is deferred to the human who runs scripts/acceptance.py and fills ACCEPTANCE_KO.md. The checkboxes stay blank per that file.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "simulation_deliverable_acceptance": {
      "status": "ADOPTED",
      "value": {
        "verdict": "ACCEPTED_PROVISIONAL_AS_LOCAL_SIMULATION_DELIVERABLE",
        "mode": "LOCAL_SIMULATION_ARTIFACT",
        "conditional_on": "all five human checklist items pass at the accepted head",
        "lapses_if": [
          "any checklist item fails",
          "evidence.funds_executed is true",
          "evidence.label is not SIMULATED",
          "vendor hashes mismatch",
          "readiness production_authorized is true"
        ],
        "human_acceptance_recorded": false,
        "production_authorized": false,
        "real_money": "NOT_AUTHORIZED"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-20"],
      "rationale": "The delegated decider fixes what the Capital deliverable is: the productized local simulation exactly as bounded by readiness local-simulation (AVAILABLE_LOCAL, synthetic profile only, not full finance). This is scope acceptance, not human acceptance and not a release permit; it lapses automatically on any failing condition and the human sign-off remains PENDING_OWNER_ACTION.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "production_authorization": {
      "status": "ADOPTED",
      "value": "NOT_AUTHORIZED: owner action pending (POA-1 human acceptance sign-off, POA-2 real-funds lift decision, POA-3 lender entity and licence determination, POA-4 PG/bank/KYC vendor contracts and credentials, POA-5 public endpoint/TLS/DNS/ingress and secrets, POA-6 zipapp signing/publishing/hosting, POA-7 retention durations, POA-8 billing and quota approval, POA-9 professional tax/accounting review and applicable independent audit)",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-20"],
      "rationale": "Real lending, PG/bank/KYC, deployment, secrets and billing are money, deploy and secrets items that this docs-only loop never executes or authorizes. The release readiness group stays NOT_AUTHORIZED and every unlock step is named for JunTae.",
      "provisional": true,
      "basis": "PENDING_OWNER_ACTION"
    },
    "remaining_holds_inventory": {
      "status": "ADOPTED",
      "value": {
        "rows_total": 20,
        "rows_dropped": 0,
        "available_local": ["CAP-01", "CAP-04", "CAP-05", "CAP-06", "CAP-08", "CAP-09", "CAP-10", "CAP-14", "CAP-20"],
        "holds": [
          {"id": "H1", "hold": "financial terms", "caps": ["CAP-01", "CAP-04"], "note": "CAPITAL_FINANCIAL_TERMS.md", "note_status": "9 of 9 ADOPTED provisional", "state": "read-only overlay, not an offer"},
          {"id": "H2", "hold": "settlement policy", "caps": ["CAP-02", "CAP-03", "CAP-04"], "note": "CAPITAL_SETTLEMENT_POLICY.md", "note_status": "6 of 6 ADOPTED provisional", "state": "DECISION_REQUIRED in readiness, unsupported by pinned FSM, CAP-03 V1 NOT_OFFERED"},
          {"id": "H3a", "hold": "producer binding", "caps": ["CAP-07", "CAP-16"], "note": "CAPITAL_UPSTREAM_BINDING.md", "note_status": "producer_sdk_tuple and t01_t06_qualification DEFERRED", "state": "UPSTREAM_REQUIRED"},
          {"id": "H3b", "hold": "durable finance", "caps": ["CAP-11", "CAP-13", "CAP-14", "CAP-15"], "note": "CAPITAL_UPSTREAM_BINDING.md", "note_status": "stage5_durable_backend, stage6_finance_candidates, stage7_authenticated_export DEFERRED", "state": "UPSTREAM_REQUIRED"},
          {"id": "H3c", "hold": "assets rights AI", "caps": ["CAP-12", "CAP-17", "CAP-18", "CAP-19"], "note": "CAPITAL_UPSTREAM_BINDING.md", "note_status": "asset_registry_fx, rights_scale_privacy, token_layer_coin_lock DEFERRED; ai_agent_grant_action_permit ADOPTED", "state": "UPSTREAM_REQUIRED"},
          {"id": "H3d", "hold": "identity and deployment", "caps": ["CAP-15", "CAP-20"], "note": "CAPITAL_UPSTREAM_BINDING.md", "note_status": "identity_provider_kyc NOT_ADOPTED; deployment_tls_retention DEFERRED", "state": "no IdP, KYC, TLS or public deployment"},
          {"id": "H4", "hold": "accounts tax legal retention", "caps": ["CAP-13", "CAP-15"], "note": "CAPITAL_ACCOUNTS_TAX_LEGAL.md", "note_status": "5 of 5 ADOPTED as WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW", "state": "licence applicability PENDING_PROFESSIONAL_REVIEW, retention durations unset"},
          {"id": "H5", "hold": "overlay state", "caps": ["CAP-01"], "note": "CAPITAL_OVERLAY_STATE.md", "note_status": "loop state MERGED, entries not re-read", "state": "see GET /api/decisions"},
          {"id": "H6", "hold": "shadow policy", "caps": ["CAP-02", "CAP-03"], "note": "CAPITAL_SHADOW_POLICY.md", "note_status": "loop state MERGED, entries not re-read", "state": "SHADOW_NOT_APPLIED"},
          {"id": "H7", "hold": "demo book", "caps": ["CAP-04", "CAP-06"], "note": "CAPITAL_DEMO_BOOK.md", "note_status": "loop state MERGED, entries not re-read", "state": "SYNTHETIC_FIXTURE_PROFILE"},
          {"id": "H8", "hold": "artifact docs bundling", "caps": ["CAP-20"], "note": "CAPITAL_ARTIFACT_BUNDLING.md", "note_status": "loop state MERGED, entries not re-read", "state": "handbook at 4d04a5b says pyz carries no docs so notes are NOT_BOUND there; reconcile"},
          {"id": "H9", "hold": "overlay digest export", "caps": ["CAP-11", "CAP-15"], "note": "CAPITAL_OVERLAY_DIGEST_EXPORT.md", "note_status": "loop state MERGED, entries not re-read", "state": "DEV HMAC integrity only"},
          {"id": "H10", "hold": "release", "caps": ["CAP-20"], "note": "CAPITAL_RELEASE_ACCEPTANCE.md", "note_status": "this note", "state": "NOT_AUTHORIZED, POA-1 to POA-9"}
        ]
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-02", "CAP-03", "CAP-07", "CAP-11", "CAP-12", "CAP-13", "CAP-14", "CAP-15", "CAP-16", "CAP-17", "CAP-18", "CAP-19", "CAP-20"],
      "rationale": "Every readiness group and every CAP row stays in the denominator. Statuses for the four notes read in this node are quoted from the notes; the five sibling notes are cited by merged loop state only because they were outside this node's read scope. CAP-13, CAP-15 and CAP-16 are listed in addition to the rows named in the node text because readiness carries them.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "readiness_production_authorized": {
      "status": "ADOPTED",
      "value": "production_authorized=false (NOT_AUTHORIZED: owner action pending); no code change in this node",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-20"],
      "rationale": "readiness.py keeps the release group NOT_AUTHORIZED and the handbook documents production_authorized and policy_adopted as false. This docs-only node cannot flip them, and flipping requires explicit owner action outside the loop.",
      "provisional": true,
      "basis": "PENDING_OWNER_ACTION"
    }
  }
}
```

## 6. 수용 기준 매핑

- 항목별 판정과 증거 파일·HEAD SHA를 가진 `capital-decision-v1` 블록 → §5의 `handbook_checklist_verdict`.
- 산출물 수용 여부, production·실자금 `NOT_AUTHORIZED`, 돈·배포·비밀·과금 항목의 `PENDING_OWNER_ACTION` → `simulation_deliverable_acceptance`, `production_authorization`, §4.3.
- 잔여 보류 전수와 노트 상태 → `remaining_holds_inventory`, §4.4.
- `production_authorized` false, docs-only → `readiness_production_authorized`. 이 문서는 한 파일(`docs/decisions/CAPITAL_RELEASE_ACCEPTANCE.md`)만 더한다. `tests/test_coverage.py`와 `scripts/decision_ledger.py`는 이 환경에서 실행하지 않았으므로 감독자와 CI가 최종 노트에 대해 돌려야 한다.

## 7. Open risks

1. **증거 미열람.** 점검표 다섯 칸이 모두 defer라서, 증거가 fail이면 §4.2 수용이 즉시 효력을 잃는다.
2. **"수용"이라는 말이 오해될 수 있다.** 이 노트는 "잠정 수용"이라 쓰는데 readiness `release` 차단 사유에는 여전히 "사용자 제품 수용"이 남아 있다. 의도한 상태다. 사람 수용은 POA-1이고 차단 사유는 바꾸지 않는다.
3. **번들링 불일치 가능성.** 4d04a5b의 핸드북은 `.pyz`에 `docs/`가 없다고 쓰는데 `CAPITAL_ARTIFACT_BUNDLING.md`는 병합됐고 읽지 못했다. 번들링이 바뀌었다면 핸드북 문장이 낡았을 수 있다.
4. **CAP-20이 두 그룹에 걸친다.** 이름 때문에 "AVAILABLE_LOCAL"과 "NOT_AUTHORIZED"가 모순처럼 읽힌다. 코드는 바꾸지 않고 §4.2에서 읽는 방법만 고정했다.
5. **ADOPTED 노트와 DECISION_REQUIRED의 공존.** 정산 정책 노트는 6개 모두 ADOPTED인데 readiness의 CAP-02·03은 `DECISION_REQUIRED`다. 고정 FSM이 표현하지 못해 적용되지 않았기 때문이다.
6. **법무·세무·인허가는 위임으로 닫히지 않는다.** 작업 가정이고 대부 주체 판단과 보존 기간이 비어 있다.
7. **HEAD 드리프트.** 노트 병합 뒤 HEAD는 `4d04a5b`와 다르다. 수용 시점의 `evidence.head_sha`를 사람이 기록해야 한다.
8. **service 코드 미열람.** `production_authorized` 키가 실제로 false를 내는지는 이 노드가 코드로 확인하지 않았다. 핸드북 서술에 의존한다.

## 8. 후속 작업

1. 병합 후 JunTae 또는 지명자가 병합 커밋에서 `python3 scripts/acceptance.py`를 돌리고 `build/acceptance-evidence.json`을 읽어 `ACCEPTANCE_KO.md`의 다섯 칸을 채운다(POA-1). 다섯 칸이 모두 pass이면 날짜와 `head_sha`를 별도 문서 개정으로 남긴다. fail이면 §4.2 수용을 철회한다.
2. `CAPITAL_ARTIFACT_BUNDLING.md`와 핸드북의 `.pyz` 서술을 대조한다. 어긋나면 핸드북에 노드 절을 더한다(기존 문장은 고치지 않는다).
3. POA-2~9는 JunTae의 명시 승인이 있을 때만 별도 노드로 연다. 이 루프는 그 사이에 실행하지 않는다.
4. `external-gate-decision`이 `real_funds_pilot`, `public_endpoint_tls`, `idp_kyc_vendor`, `licensed_lender_entity`를 따로 결정한다. 이 노트와 값이 충돌하면 더 엄격한 쪽(NOT_AUTHORIZED)을 따른다.
