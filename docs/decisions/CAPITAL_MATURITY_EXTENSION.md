# Capital 일회성 만기 연장 결정 — 적격 창, 금리, 유예, 가속 거절과 승인 증거

**PROVISIONAL PRODUCT DECISION · 2026-11-20 · `maturity-extension-decision`**

| 항목 | 값 |
|---|---|
| 지정 결정자 | Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07) |
| 검토 기준 | KIX-CAPITAL main `b24f175` · kix-protocol `8341dd7` · supervisor 제공 |
| 선행 노드 | `financial-terms-decision`, `default-recovery-decision`, `margin-cure-default`, `decision-guard-additions` |
| 구현 소유자 | 일곱 항목 모두 `maturity-extension-command` |
| 적용 범위 | `SIMULATED` · 제품 설계 전용 · 실자금 없음 · production `NOT_AUTHORIZED` |

위임 원문은 “금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해.”이다. `decided_by`와 `provided_by`는 감독자가 지정한 위임 표기다. 이번 개정에서 Claude CLI는 Sonnet 세 차례와 후속 Fable 한 차례 모두 로그인 오류를 반환했다. 개정 판단은 제공된 결정문·리뷰와 허용된 자료에 근거한다.

## 1. 결정 요약

| Item | 결정 | CAP rows | Consumer |
|---|---|---|---|
| `extension_eligibility_window` | 인출일부터 마지막 유예일까지 양 끝을 포함한다. 미상환 원금이 있고 미해결 마진콜이 없는 선지급에 1회 허용한다. | CAP-01, CAP-04 | `maturity-extension-command` |
| `extension_during_grace_and_default_interest_kept` | 유예 중 승인하면 명령일분까지 연체이자를 보존한다. 새 만기에 전체 유예를 적용한다. | CAP-01, CAP-04 | `maturity-extension-command` |
| `extended_term_rate_and_tier` | 앞으로 남은 연장일에는 최초 인출 티어의 계약 금리를 적용한다. 연장 수수료는 0원이다. | CAP-01 | `maturity-extension-command` |
| `hard_cap_180_interaction_with_settlement_linked_term` | 정산 연동 원 만기에 최대 30일을 더하되 인출일부터 새 만기까지 180일을 넘길 수 없다. | CAP-01, CAP-04 | `maturity-extension-command` |
| `acceleration_and_default_eligible_refusal` | 가속 사실이 있거나 부도 적격일에 도달하면 거절한다. | CAP-01, CAP-04, CAP-19 | `maturity-extension-command` |
| `forecast_rollup_and_cap_check_treatment` | 롤업·예측·충당금 측정은 각 시점의 유효 만기를 쓴다. 연장 단독으로는 연환산 비용 상한의 `PASS`/`FAIL`이 바뀌지 않는다. | CAP-01, CAP-04 | `maturity-extension-command` |
| `extension_record_fields_and_operator_authority` | 사람 승인을 `MATURITY_EXTENSION` 한 건에 기록한다. 적용 약관의 버전·원문 해시·순서가 고정된 조항 경로를 함께 보존한다. | CAP-01, CAP-11, CAP-19 | `maturity-extension-command` |

## 2. KIX 비전 연결

- kix-protocol `CREDIT_ADVANCE_F04` §5는 이자·수수료·APR·기간·상환 일정·연체·손실 귀속·상각을 open items로 둔다. 이 결정은 그중 만기 연장을 Capital 오버레이에서 처리한다. §5와 재핀 정책 `CAPITAL_UPSTREAM_REPINS` §§3.3–3.4는 제공된 전판의 인용을 따른다. 전판의 `3c2cfaf`·`5efab69`와 이번 판의 `b24f175`·`8341dd7`은 각각의 검토 출처다. FSM 전달 핀 `8ba7f6c36373ac0ec49246f51f7471c164ac3a28`과 별도 계약 인용 핀의 적용 범위는 요구사항이 정한다. [Capital 요구사항](../CAPITAL_REQUIREMENTS_KO.md)
- 권위 모델 A-4에 따라 재생은 당시 명령과 최초 결과를 복원한다. 새 연장은 현재 권한으로 승인해야 한다. 가속·부도 적격일은 기존 회수 결정의 시계를 따르고, 로컬 승인 라벨의 효력은 시뮬레이션에 한정한다. [권위 모델 A-4](/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md) · [기본 회수 결정 §4.1](CAPITAL_DEFAULT_RECOVERY.md) · [로컬 포트 범위](../SEAMS.md)
- `ADOPTED`는 Capital의 잠정 제품 선택이다. 운영 계약 채택과 실제 대출 제안은 범위 밖이다. 법률·세무·회계 판단의 근거 상태는 `WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW`다. [회계·세무·법무 결정](CAPITAL_ACCOUNTS_TAX_LEGAL.md)

## 3. 항목별 결정

`d0`는 인출일, `M`은 연장 직전 예정 만기, `E`는 명령일, `k`는 요청 연장일, `M' = M + k`는 새 만기, `G`는 약관상 유예일이다. 모두 정수 논리 일이다. 아래의 **선지급당 1회, 최대 30일, 총기간 180일, 사람 승인, 연장 수수료 0, 유예 10일**은 `CAPITAL-TERMS-V1`의 채택값이다. 소비자는 §4의 `clause_paths`가 가리키는 약관에서 값을 읽는다.

### 3.1 `extension_eligibility_window` — ADOPTED

주최자는 `d0 ≤ E ≤ M + G`에 해당 선지급의 연장을 요청할 수 있다. 사람 운영자는 명령 직전 기록에서 인출 완료, 생존 상태, 양수인 실효 미상환 원금, 연장 미사용, 가속·미해결 마진콜 부재를 확인한다. 만기 당일과 마지막 유예일도 포함한다. 치유 마감 경과만으로 마진콜을 닫지 않는다. 먼저 유효한 치유가 기록되어 종료된 경우에는 나머지 조건으로 판단한다.

명령은 시계를 진행시키지 않는다. 적격 확인과 성공 사실 추가를 한 번에 처리하여 같은 선지급에 경합하는 두 요청 중 하나만 연장 횟수를 사용한다.

### 3.2 `extension_during_grace_and_default_interest_kept` — ADOPTED

`M < E ≤ M + G`이면 `M + 1`일부터 `E`일분까지 기존 원금 이력으로 발생한 연체이자를 보존한다. `accrued_default_interest_kept_krw`는 그 발생액의 증거다. 지급 이력은 채무 잔액에 그대로 반영한다. 이 증거 금액을 다시 청구하거나 원금에 편입하지 않는다.

`M' ≥ E`여야 한다. `M' = E`이면 앞으로 남은 계약 금리 적용일은 0일이다. 후속 가속이 없을 때 새 연체 시작일은 `M' + 1`, 부도 적격일은 `M' + G + 1`이다. 180일 한도에 도달한 만기도 전체 유예를 갖는다.

### 3.3 `extended_term_rate_and_tier` — ADOPTED

| 발생일 `t` | 적용 금리 |
|---|---|
| `E ≤ M`일 때 `M < t ≤ M'` | 최초 인출 시 확정한 티어의 all-in 계약 금리 |
| `E > M`일 때 `M < t ≤ E` | 기존 연체 금리. 명령일분을 포함한다. |
| `E > M`일 때 `E < t ≤ M'` | 최초 티어의 all-in 계약 금리 |
| `t > M'` | 새 만기를 기준으로 기존 연체 정책 적용 |

원금 변동, ACT/365 단리, 기존 반올림 및 상환 종료일 제외 규칙을 따른다. 각 발생일에는 한 구간의 금리만 적용한다. 재심사에 의한 티어 변경, 연장 가산금리, 복리는 없다. 연장 후 가속이 기록되면 기존 가속 규칙에 따라 `M* = min(M', 앵커일)`을 사용하고 이전 기록 시점의 발생액은 보존한다.

### 3.4 `hard_cap_180_interaction_with_settlement_linked_term` — ADOPTED

정산 연동 산식은 인출 시 원 만기 `M`을 정한다. 연장 때는 기록된 `M`에서 다음 범위를 계산한다. 정산 예정일이 바뀌어도 산식을 다시 실행하지 않는다.

- `k_min = max(1, E − M)`
- `k_max = max(0, min(days_max, hard_cap_total_days − (M − d0)))`
- 정수 `k`가 `k_min ≤ k ≤ k_max`일 때만 `M' = M + k`를 승인한다.

예를 들어 `d0 = 0`, `M = 170`, `E = 175`이면 5일부터 10일까지 요청할 수 있다. 11일 요청은 거절하고 `min_admissible_extension_days = 5`, `max_admissible_extension_days = 10`을 반환한다. 요청을 자동 절사하지 않는다. 최솟값이 최댓값보다 크면 허용할 연장일이 없다.

### 3.5 `acceleration_and_default_eligible_refusal` — ADOPTED

권한과 입력 형식을 먼저 확인한다. agent의 게시 시도는 `403 EXTENSION_AGENT_FORBIDDEN`이다. 권한 있는 동일 `overlay_id`·동일 요청 재생에는 최초 결과를 반환하고, 같은 ID의 다른 요청에는 `409`를 반환한다. 응답이 유실되면 원 ID로 조회한다.

신규 요청은 아래 순서에서 처음 해당하는 사유로 `409`를 반환한다. 거절 시 상태·저널·사용 횟수는 그대로다.

| 순서 | 명령 직전 조건 | 코드 |
|---|---|---|
| 1 | `ACCELERATED` 사실 존재 | `EXTENSION_AFTER_ACCELERATION` |
| 2 | FSM `DEFAULTED` 또는 `E ≥ 현재 default_eligible_sim_day` | `EXTENSION_DEFAULT_ELIGIBLE` |
| 3 | 미인출·종료·실효 원금 0 | `EXTENSION_NOT_LIVE` |
| 4 | 미해결 마진콜 | `EXTENSION_MARGIN_CALL_OPEN` |
| 5 | 이미 성공한 연장 존재 | `EXTENSION_ALREADY_USED` |
| 6 | `E < d0` | `EXTENSION_OUTSIDE_WINDOW` |
| 7 | 요청일이 §3.4 범위 밖 | `EXTENSION_CAP_EXCEEDED` |
| 8 | 필요한 두 번째 승인 부재 | `TWO_PERSON_REQUIRED` |

가속 후에는 부분 상환이 있어도 연장을 거절한다. 부도 명령이 아직 없어도 `DEFAULT_ELIGIBLE` 첫날부터 거절한다.

### 3.6 `forecast_rollup_and_cap_check_treatment` — ADOPTED

롤업과 예측은 연장 사실을 포함한 첫 기록 시점부터 `M'`을 표시한다. 그보다 이른 스냅샷에는 `M`이 남는다. 예정 상환 흐름은 `M'`으로 한 번만 이동한다. 연장된 행에만 `original_maturity_sim_day`와 `extension_days`를 덧붙인다. 예측 이자는 §3.3의 구간과 실제 지급 이력을 사용한다. 원 심사 U1–U6 기록은 보존한다.

포트폴리오 `cap_check`는 **연환산 비용 상한에 대한 `PASS` 또는 `FAIL`**이다. 최초 티어가 고정되고 수수료가 0이므로 다른 입력이 같은 경우 연장 전후 판정은 같다. 예측 총이자는 적용 일수에 따라 달라질 수 있다. 연장 자체로 원금을 감액하거나 차입 한도를 복원하지 않는다.

**충당금은 각 측정 시점까지 기록된 사실로 재계산한다.** 연장 전 측정은 `M`을, 연장 사실을 포함한 측정은 `M'`을 사용한다. 동일 `sim_day` 안에서도 저널 순서로 두 시점을 구별한다. 예를 들어 T1 미상환 원금이 1,000,000원이고 이미 측정된 연체 충당금이 250,000원이라고 하자. `M = 60`, `E = 65`, `k = 20`이면 `M' = 80`이다. 다른 변동 없이 66일에 측정하면 정상 상태 목표액은 15,000원이다. 기존 충당금 측정 절차가 차액 **235,000원을 환입**한다. 이전 측정액과 65일까지 발생한 연체이자는 보존한다. 같은 시점을 재생해도 환입을 중복 게시하지 않는다.

### 3.7 `extension_record_fields_and_operator_authority` — ADOPTED

성공 시 `kind = MATURITY_EXTENSION`인 사실 한 건을 기록한다. §4의 `entry_fields`와 `payload_fields`가 필수 필드 전체다. `sim_day`에는 `E`, `after_journal_index`에는 명령이 관측한 FSM 저널 위치를 기록한다. 같은 위치의 사실은 기존 오버레이 저널 순서로 재생한다. 서버는 결합된 선지급에서 식별자·수익자·티어를 가져오고 명령 직전 원금과 보존 이자를 산출한다. 날짜·일수와 KRW 금액은 정수다.

`payload.terms_refs`는 §4의 `terms_refs_schema`를 만족하는 객체다. `terms_version`은 문자열 `CAPITAL-TERMS-V1`이다. `note_sha256`은 승인에 실제 사용한 `CAPITAL_FINANCIAL_TERMS.md` **파일 전체의 원본 바이트**를 SHA-256으로 해시한 소문자 16진수 64자다. 줄바꿈도 원본 그대로 포함한다. `clause_paths`는 해당 노트의 결정 JSON 루트를 기준으로 한 점 표기 문자열 배열이다. 모든 승인에 §4의 13개 값을 표시된 순서대로 기록한다. 추가 키·생략·중복·재정렬은 허용하지 않는다. 객체 직렬화에는 기존 오버레이의 정본 인코딩을 적용한다.

`authority`의 필수 키는 `role`과 `approvals`다. `role`은 `HUMAN_OPERATOR`이고, `approvals`의 각 원소는 문자열 `approver_label` 키 하나를 갖는다. 라벨을 중복 제거한 뒤 UTF-8 바이트 오름차순으로 기록한다. 명령 시 실효 미상환 원금이 TERMS의 2인 임계 **이하**이면 사람 한 명, **초과**이면 서로 다른 사람 두 명 이상이 필요하다. AI는 `MATURITY_EXTENSION_CANDIDATE`를 `executionAuthorized=false`로 제안할 수 있다. 운영자가 제안을 채택할 때만 `authority.proposal_id`를 포함한다. 제안은 승인 횟수에 포함하지 않는다.

폴드는 `state.maturity_extension[advance_id]`에 성공 사실 하나를 둔다. 연장 기록이 없으면 빈 키를 만들지 않는다. **`coa_posting: false`는 연장 명령의 직접 분개에만 적용한다.** 이후 충당금 측정의 분개는 §3.6을 따른다. 연장은 F04 전이 없이 오버레이에 기록하며, 연장 사실을 담은 오버레이 digest와 이를 포함한 export `content_digest`를 재계산한다. 기존 export 구조와 recon 식별자를 사용한다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "maturity-extension-decision",
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-11-20",
  "provisional": true,
  "scope": "Local simulation and product design only",
  "bases": {
    "capital_main": "b24f175",
    "kix_protocol": "8341dd7",
    "basis_kind": "SUPERVISOR_SUPPLIED_HISTORICAL_PROVENANCE",
    "terms_version": "CAPITAL-TERMS-V1"
  },
  "consumer_node": "maturity-extension-command",
  "label": "SIMULATED",
  "production": "NOT_AUTHORIZED",
  "upstream_adoption_claimed": false,
  "entries": {
    "extension_eligibility_window": {
      "status": "ADOPTED",
      "value": {
        "window": "d0 <= E <= M + G",
        "conditions": ["drawn and live", "positive effective outstanding principal", "unused extension", "no acceleration", "no unresolved margin call", "human operator command"],
        "count_max_ref": "entries.term.value.extension.count_max",
        "atomicity": "Evaluate at the pre-command cut and append at most one success per advance",
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-20",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Keep the last grace day available while enforcing open cure obligations.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "extension_during_grace_and_default_interest_kept": {
      "status": "ADOPTED",
      "value": {
        "grace_extension": "ALLOWED",
        "minimum_days": "max(1, E - M)",
        "kept": "Preserve default interest accrued through E under the original schedule and credit all payments",
        "kept_amount_use": "Observational snapshot only",
        "new_default_interest_from": "M_prime + 1",
        "new_default_eligible_day": "M_prime + G + 1",
        "professional_review": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-20",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Carry forward earned interest and start a full grace period at the revised maturity.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "extended_term_rate_and_tier": {
      "status": "ADOPTED",
      "value": {
        "tier": "Fixed at original draw",
        "segments": {
          "M < t <= E": "Original overdue rate if E > M",
          "max(M, E) < t <= M_prime": "Original tier all-in contract rate",
          "t > M_prime": "Existing overdue policy, subject to later acceleration and accrual stop rules"
        },
        "conventions": "Apply existing ACT/365 simple interest to principal history with existing rounding and stop days",
        "extension_premium": false,
        "fee_ref": "entries.fees.value.extension_fee_bps",
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-20",
      "cap_rows": ["CAP-01"],
      "rationale": "Price each accruing day once at the rate in force for that segment.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "hard_cap_180_interaction_with_settlement_linked_term": {
      "status": "ADOPTED",
      "value": {
        "settlement_formula": "Applied at origination only",
        "new_maturity": "M_prime = M + k",
        "minimum_days": "max(1, E - M)",
        "maximum_days": "max(0, min(days_max, hard_cap_total_days - (M - d0)))",
        "invalid_request": "409 EXTENSION_CAP_EXCEEDED with min_admissible_extension_days and max_admissible_extension_days",
        "hard_cap_scope": "Draw through scheduled maturity, excluding grace",
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-20",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Retain the settlement-linked base date and reject requests beyond either term limit.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "acceleration_and_default_eligible_refusal": {
      "status": "ADOPTED",
      "value": {
        "agent_post": "403 EXTENSION_AGENT_FORBIDDEN",
        "idempotency": "After authority and format checks, return the recorded result for an identical request with the same overlay_id. Conflicting reuse returns 409.",
        "business_refusal_order_409": [
          "EXTENSION_AFTER_ACCELERATION", "EXTENSION_DEFAULT_ELIGIBLE", "EXTENSION_NOT_LIVE",
          "EXTENSION_MARGIN_CALL_OPEN", "EXTENSION_ALREADY_USED", "EXTENSION_OUTSIDE_WINDOW",
          "EXTENSION_CAP_EXCEEDED", "TWO_PERSON_REQUIRED"
        ],
        "default_boundary": "FSM DEFAULTED or E >= current default_eligible_sim_day",
        "refusal_writes": false,
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-20",
      "cap_rows": ["CAP-01", "CAP-04", "CAP-19"],
      "rationale": "Acceleration is irreversible and default eligibility follows the clock independently of default posting.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "forecast_rollup_and_cap_check_treatment": {
      "status": "ADOPTED",
      "value": {
        "rollup_forecast": "Use M_prime from the first cut containing the extension. Move the scheduled repayment once and credit prior payments.",
        "additive_fields_on_extended_advances": ["original_maturity_sim_day", "extension_days"],
        "underwriting": "Preserve the original U1-U6 record",
        "cap_check": "PASS or FAIL against the existing annualized cost cap. Fixed tier and zero fees preserve the result for extension alone.",
        "allowance_replay": "Classify using the effective maturity at each measurement cut. Post target less carrying allowance under the existing measurement policy. Preserve earlier cuts.",
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-20",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Due dates and loss allowance can change even when principal and annualized pricing stay fixed.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "extension_record_fields_and_operator_authority": {
      "status": "ADOPTED",
      "value": {
        "entry_kind": "MATURITY_EXTENSION",
        "entry_fields": ["overlay_id", "kind", "sim_day", "after_journal_index", "payload"],
        "payload_fields": [
          "advance_id", "claim_id", "beneficiary_role", "draw_sim_day", "original_maturity_sim_day",
          "extension_days", "new_maturity_sim_day", "tier", "outstanding_principal_krw_at_command",
          "accrued_default_interest_kept_krw", "fee_krw", "terms_refs", "authority", "label"
        ],
        "constants": {"fee_krw": 0, "label": "SIMULATED"},
        "terms_refs_schema": {
          "type": "object",
          "additionalProperties": false,
          "required": ["terms_version", "note_sha256", "clause_paths"],
          "properties": {
            "terms_version": {"const": "CAPITAL-TERMS-V1"},
            "note_sha256": {"type": "string", "minLength": 64, "maxLength": 64, "pattern": "^[0-9a-f]{64}$"},
            "clause_paths": {
              "const": [
                "entries.fees.value.extension_fee_bps",
                "entries.interest_rate.value",
                "entries.term.value.extension.approval",
                "entries.term.value.extension.count_max",
                "entries.term.value.extension.days_max",
                "entries.term.value.extension.hard_cap_total_days",
                "entries.term.value.grace_days_after_maturity",
                "entries.term.value.max_term_days",
                "entries.term.value.min_term_days",
                "entries.term.value.settlement_linked_rule",
                "entries.term.value.settlement_slack_days",
                "entries.term.value.standard_term_days",
                "entries.underwriting_depth.value.two_person_threshold_krw"
              ]
            }
          }
        },
        "note_sha256_input": "Exact bytes of the full financial terms Markdown note used to approve the command",
        "authority": {
          "role": "HUMAN_OPERATOR",
          "approvals": "Unique objects with sole key approver_label, sorted by label in UTF-8 byte order",
          "threshold": "Require one distinct human up to the TERMS threshold and at least two above it, measured on effective outstanding principal at the command cut",
          "proposal_id": "Present only when adopting a proposal",
          "authentication_claimed": false
        },
        "ai": {"kind": "MATURITY_EXTENSION_CANDIDATE", "executionAuthorized": false},
        "fold": "One fact in state.maturity_extension[advance_id]. Omit the key when empty.",
        "ordering": "after_journal_index followed by existing overlay journal order",
        "direct_extension_command": {"coa_posting": false},
        "digests": "Recompute the affected overlay and containing export content_digest under existing canonical encoding",
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-20",
      "cap_rows": ["CAP-01", "CAP-11", "CAP-19"],
      "rationale": "Bind the approved dates, price, humans and source bytes to one replayable fact.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| 기준 | 확인 결과 |
|---|---|
| 단일 결정 블록과 소비자 | 제출 JSON을 파싱해 일곱 항목의 `ADOPTED`, 귀속, 날짜, CAP 행, 근거, 잠정 표시, 소비 노드를 확인했다. |
| Pending 앵커 | 일곱 항목명이 `tests/decision_bindings.json`의 `PENDING_CONSUMER` 등록과 일치하며 모두 `maturity-extension-command`를 가리킨다. |
| 조건과 증거 | §3.1–3.5가 TERMS 한도와 거절 순서를 정한다. §3.6은 충당금 환입 예를, §3.7과 §4는 승인 증거의 필드·타입·배열 순서를 고정한다. |
| 저장 후 통합 확인 | 감독자가 `docs/decisions/CAPITAL_MATURITY_EXTENSION.md`를 저장한 뒤 `scripts/decision_ledger.py` 파싱, `GET /api/decisions`의 일곱 항목 노출, `python3 scripts/decision_bindings.py --check`, `python3 scripts/docs_surface.py --check`를 확인한다. 이번 제출의 검증 범위는 저장 전 JSON과 기존 바인딩 대조까지다. |

## 6. Open risks

- 연체이자 보존의 대외 효력과 충당금 환입의 회계·세무 인식은 전문가 검토 전 작업 가정이다. 검토 소유자는 `accounts-tax-legal-decision` 후속 담당이다.
- 승인 라벨과 문서 해시는 시뮬레이션 재생용 증거다. 실제 신원·서명·채무 변경 권한은 `NOT_BOUND`다.

## 7. 후속 작업

`maturity-extension-command`는 마지막 유예일과 첫 부도 적격일, `M' = E`, 180일 경계, 가속·치유 순서, 승인 임계, 부분 상환, 경합·재생을 검증한다. 같은 날 연장 전후의 충당금 측정, 235,000원 환입의 단일 반영, `cap_check` 판정 보존, `clause_paths` 순열 거절을 소비자 수용 사례에 포함한다.
