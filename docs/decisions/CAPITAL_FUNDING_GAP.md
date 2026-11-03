# CAPITAL_FUNDING_GAP — 상환 재원과 계약상 현금 의무의 분리

> **PROVISIONAL PRODUCT DECISION**
>
> 요청된 위임 식별자: **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**
>
> 결정일: **2026-11-03** · KIX-CAPITAL main **079dcca** · kix-protocol **15ea27b** — supervisor 제공 기준이며 Git으로 재검증하지 않았다.
>
> 시뮬레이션·제품 설계 전용. 실자금 없음. production **NOT_AUTHORIZED**. 소비 노드: **`funding-gap-report`**.
>
> **작성 이력:** 지정 Sonnet CLI 호출 3회와 Fable 대체 호출 1회가 모두 `Not logged in`으로 실패했다. 실제 문서 작성·설계 판단은 Codex가 수행했다. 아래 `decided_by`·`provided_by`는 요청된 위임 식별자를 보존하며, 해당 모델의 실제 실행·서명·검토 완료를 증명하지 않는다.

`ADOPTED`는 이 문서의 잠정 제품 설계 선택이다. upstream 채택, 구현 완료 또는 운영 승인이 아니다. 회계·세무·법률에 닿는 해석은 전문가 검토 전 작업 가정이다.

읽기 범위는 supervisor pack과 허용 경로로 제한했다. 선행 정산·상환 결정은 supervisor가 병합 사실을 제공했으나, 두 원문은 명시적 허용 목록 밖이고 내용도 제공되지 않았다. 따라서 기존 정책을 재결정하지 않는다. 정확한 소비 필드·정책 연결은 `UNDETERMINED`, `value: null`이며, 후속 구현자가 원문을 읽고 ADOPTED 값을 적용한다. 기존 결정에 다시 `DECISION_REQUIRED`를 붙이지 않는다.

## 1. 결정 요약

CAP 행은 본 보고서의 설계 추적용 제안 매핑이며 커버리지 완료 판정이 아니다.

| item | 결정 | CAP rows | consumer |
|---|---|---|---|
| `cashflow_viewpoint` | 합성 수익자 `demo-org-alpha`의 선택된 기존 선지급 상환을 분석. 정산은 재원, 상환은 의무 | CAP-01, CAP-04 | `funding-gap-report` |
| `opening_cash_assumption` | 기본 0원. 명시적 합성 기초현금만 허용하고 정산 재원과 중복 금지 | CAP-01, CAP-20 | `funding-gap-report` |
| `source_identity_and_budget` | 정산 권리별 단일 잔여 예산. 선지급별 참조 복제로 예산 증가 금지 | CAP-04, CAP-08 | `funding-gap-report` |
| `due_day_ordering` | 논리 일별 정산 유입을 먼저 반영하고 같은 날 의무를 합산 차감 | CAP-01, CAP-04 | `funding-gap-report` |
| `shortfall_and_carry` | 정확한 정수 누적 순잔액, 양수 이월, 음수 부족. 최대 부족과 말일 부족 분리 | CAP-01, CAP-04 | `funding-gap-report` |
| `unsupported_case_policy` | 부도·가속·슬라이스 부담·불명 입력은 전체 선택 범위 `UNEVALUATED` | CAP-04, CAP-08, CAP-20 | `funding-gap-report` |
| `horizon_and_input_bounds` | 1명, 선지급 1–32건, 재원 0–64개, 사건 1,024개 이하, 기간 1–365일 | CAP-01, CAP-20 | `funding-gap-report` |

## 2. KIX 비전 연결

[KIX Protocol README](/workspace/capital-run/kixproto-ro/README.md)는 티켓 거래에서 환불·정산·금융 근거까지 연결하는 방향과 비운영 구현의 한계를 함께 명시한다. 이 보고서는 같은 사건에서 발생한 정산 유입과 상환 의무를 별도로 추적하여 그 연결을 설명 가능하게 한다.

[AUTHORITY_MODEL_1.md](/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md)는 예약, 지급 확인, 권리 발행을 구별하고 체인이 실제 은행 자금이나 계약상 의무를 보증하지 않는다고 명시한다. 따라서 보고서의 계산 결과는 현금 보유 증명이나 지급 권한이 아니다.

[CAPITAL_DEMO_BOOK.md](CAPITAL_DEMO_BOOK.md)의 `demo-org-alpha`를 합성 관점으로 사용한다. 여러 수익자가 `organizer` 역할 라벨을 공유하므로 역할명만으로 재원 소유자를 식별하지 않는다. 기존 북의 금액·fixture·golden을 변경하지 않는다.

제공된 [SEAMS.md](../SEAMS.md) 발췌의 `NOT_BOUND` 경계, [CAPITAL_CLAIM_SLICE_REGISTRY.md](CAPITAL_CLAIM_SLICE_REGISTRY.md)의 중복 사용 방지 방향, [CAPITAL_DEFAULT_RECOVERY.md](CAPITAL_DEFAULT_RECOVERY.md)의 별도 가속·회수 정책을 유지한다. [CAPITAL_ACCOUNTS_TAX_LEGAL.md](CAPITAL_ACCOUNTS_TAX_LEGAL.md)의 합성 회계 투영을 현금 근거로 전환하지 않는다.

## 3. 항목별 결정

### 3.1 `cashflow_viewpoint`

모델 버전은 `CAPITAL-FUNDING-GAP-V1`이다. 보고서 하나는 하나의 고정 snapshot, 하나의 시나리오, 합성 수익자 `demo-org-alpha`, 명시적으로 선택한 기존 선지급 집합을 다룬다.

정산 leg는 그 수익자에게 가용하다고 **가정한 재원 후보**다. 상환 leg는 수익자가 부담하는 **현금 의무**다. 두 leg를 각각 독립적인 가용 현금으로 더하는 것을 금지한다. 대주 관점의 상환 수취액도 이 수익자의 유입이 아니다.

재원은 기존 정산 정책에 따른 제3자 몫·공제 등을 반영한 수익자 귀속액이어야 하며, 본 보고서가 차감할 선택 선지급 상환액을 이미 차감한 값이어서는 안 된다. 이미 상환 차감된 순액만 제공되면 임의로 gross-up하지 않고 `UNEVALUATED`로 둔다.

의무는 선행 상환 정책이 산출한 미지급 금액·기일을 소비한다. 원금·이자·수수료를 새로 배분하거나 계산하지 않는다. 이미 반영된 상환을 다시 차감하지 않는다. 공통 재원의 충족 가능성만 계산하며 특정 선지급이 지급됐다고 판정하지 않는다.

출력에는 `SIMULATED`, `HYPOTHETICAL_FUNDING_GAP`, `non_posting: true`, `funds_executed: false`, `production: NOT_AUTHORIZED`를 고정한다. 결과는 선택 집합에 한정되며 수익자의 전체 채무, 지급능력 또는 실제 유동성 평가가 아니다.

### 3.2 `opening_cash_assumption`

기초현금 `O`는 시작일 직전의 합성 가용 잔액이다. 생략하면 정확히 0원이며 `opening_cash_origin: DEFAULT_ZERO`를 표시한다. 명시 입력은 `EXPLICIT_SYNTHETIC_ASSUMPTION`과 입력값을 보존한다.

선지급 실행액, 담보 액면, 회계 잔액 또는 과거 정산 총액에서 기초현금을 자동 추론하지 않는다. 0원은 실제 잔액이 없다는 뜻이 아니다.

기초현금과 향후 재원 예산은 서로 겹치지 않아야 한다. 이미 기초현금에 포함된 수령액은 재원 잔여액에서 제외한다. 그 구분을 입증할 합성 입력이 없으면 `UNEVALUATED`다.

새 차입, 자본 투입, 자동 부족액 보충, 준비금 인출 및 기간 중 외부현금 추가는 지원하지 않는다.

### 3.3 `source_identity_and_budget`

재원 식별자는 보고서 내부의 다음 완전한 튜플이다.

`(workspace_id, beneficiary_id, claim_id, settlement_entitlement_id, currency)`

`settlement_entitlement_id`는 동일 정산 권리를 가리키는 안정된 로컬 식별자다. upstream 필드나 인증된 소유권 식별자를 새로 채택한다는 뜻은 아니다. `advance_id`나 forecast 행 번호를 재원 식별자로 쓰지 않는다.

동일 권리를 가리키는 여러 참조는 한 예산에 결합한다. 별칭을 유일한 원천 권리로 해소할 수 없으면 미평가한다. 별도 시나리오는 독립 보고서이며 서로의 예산을 합치지 않는다.

각 재원은 다음을 갖는다.

- `budget_krw`: 기준 snapshot의 미수령·미사용 수익자 귀속 잔여 예산.
- `release_id`, `available_sim_day`, `amount_krw`: 예산 중 언제 얼마가 가용하다고 가정하는지 나타내는 일정.
- 원천 참조, snapshot 식별자, 수익자 연결 및 기존 정산 정책의 출처.

모든 release 합계는 해당 예산 이하이고 예산은 근거가 있는 잔여 귀속액 이하다. 미배치 예산은 자동 유입되지 않으며 `unscheduled_budget_krw`로 별도 표시한다. 같은 날의 복수 release는 허용하되 서로 다른 부분이어야 한다.

완전히 같은 식별자·내용의 반복은 한 번만 센다. 같은 식별자의 금액·날짜 충돌은 `INVALID_INPUT`이다. 같은 권리에 서로 다른 식별자를 부여한 중복을 해소할 수 없으면 `UNEVALUATED`다. 예산 초과는 자르지 않고 거절한다.

상환 의무도 `(advance_id, obligation_id)`별 한 번만 센다. 원천 일정의 같은 의무를 여러 forecast 행이 참조해도 금액을 늘리지 않는다. 원금 총액과 원리금 합계를 중복 차감하지 않도록 기존 정책에서 배타적인 의무 행을 제공해야 한다.

선택된 재원은 선택 의무 집합에 공통으로 사용 가능한 합성 재원이어야 한다. 특정 선지급에만 사용 가능한 법적·계약상 제한은 V1에서 지원하지 않는다. 이는 실제 상환 배분 정책이 아니다.

### 3.4 `due_day_ordering`

기준일 `as_of_sim_day`는 해당 일 종료 시점 snapshot이다. 시작일은 `as_of_sim_day + 1`이며, 날짜는 시간대 없는 정수 논리 일이다.

매일 다음 순서로 계산한다.

1. 전날 누적 순잔액을 가져온다.
2. 그날 가용해지는 고유 release를 모두 더한다.
3. 그날 도래한 고유 상환 의무를 모두 합산하여 뺀다.
4. 순잔액·이월·부족액을 기록한다.

같은 날 유입 우선은 명시적 일 단위 가정이다. 장중 지급 시각, 은행 처리 순서 또는 계약상 우선순위를 보장하지 않는다. 선지급 ID 정렬은 표시 순서에만 사용한다.

지연 시나리오는 재원별 0 이상의 정수 `delay_days`를 별도 입력하여 `available_sim_day = base_available_sim_day + delay_days`로 계산한다. 금액과 의무 기일은 이동시키지 않는다. 조기 정산 시나리오는 지원하지 않는다.

기준일 이전의 미해결 의무를 시작일로 옮기거나 0원 처리하지 않는다. 존재하면 본 모델의 시작 조건 밖이므로 미평가한다.

### 3.5 `shortfall_and_carry`

모든 금액은 KRW 정수다. 부동소수점·확률 가중치·모델 내부 반올림을 사용하지 않는다. 원천 계산이 분수 금액을 반환하면 기존 정책에 따른 정수 확정값이 필요하다. 이 보고서는 그 반올림 규칙을 새로 정하지 않는다.

일 `d`의 재원 유입을 `F_d`, 신규 도래 의무를 `D_d`라 하면:

- `N_0 = O`
- `N_d = N_(d-1) + F_d - D_d`
- `carry_d = max(N_d, 0)`
- `shortfall_d = max(-N_d, 0)`
- `peak_shortfall = max(shortfall_d)`
- `terminal_shortfall = shortfall_end`

음수 `N_d`는 분석상의 미충족 누계이며 실제 음수 은행 잔액이나 신규 대출이 아니다. 양수 부분만 다음 날로 넘기고 음수 부족을 버리는 계산은 금지한다.

일별 부족액을 더하지 않는다. 동일한 100원 부족이 이틀 지속되어도 필요 재원을 200원으로 표시하지 않는다. `peak_shortfall`은 정해진 시나리오에서 모든 일말 부족을 없애는 추가 기초현금의 수학적 크기이며 조달 제안이 아니다. 이를 실제 입력 현금으로 자동 주입하지 않는다.

늦은 유입은 분석상 미충족 누계를 줄일 수 있지만 과거 부족일, 최초 부족일 및 최대 부족액을 지우지 않는다. 부족 결과로 연체이자·가속·부도를 새로 발생시키지 않는다. 따라서 결과는 고정된 계약 일정과 가정 재원의 비교다.

**작동 예시 — 모두 별도 합성 시나리오이며 금액은 원:**

| 사례 | 기초현금·유입 | 의무 | 일말 `N` | 최대 / 말일 부족 |
|---|---|---|---|---|
| 지연 정산 | `O=0`, 재원 S 예산 100, 3일 유입 100 | 1일 100 | 1일 −100, 2일 −100, 3일 0 | 100 / 0 |
| 두 선지급의 재원 공유 | `O=0`, S 예산 100, 1일 유입 100 | 1일 A 60, B 50 | −10 | 10 / 10 |
| 정확 충족 | `O=0`, S 예산·1일 유입 100 | 1일 100 | 0 | 0 / 0 |
| 1원 부족 | `O=0`, S 예산·1일 유입 99 | 1일 100 | −1 | 1 / 1 |
| 양수 이월 | `O=20`, S 예산·1일 유입 100 | 1일 70, 2일 50 | 1일 50, 2일 0 | 0 / 0 |

공유 사례에서 A와 B가 각각 S를 참조해도 유입은 100원이다. A와 B 중 누가 얼마를 받는지는 결정하지 않는다. 정확 충족 사례도 실제 지급 성공을 뜻하지 않는다.

### 3.6 `unsupported_case_policy`

다음은 관련 행에 이유를 표시하고 **전체 선택 범위**를 `UNEVALUATED`로 둔다.

- 부도, 상각, 회수 단계인 선지급.
- 이미 가속됐거나 입력 기간 중 가속 사건이 예정된 선지급.
- 선택 선지급 또는 재원에 슬라이스 부담·제3자 홀더 권리·상계·용도 제한이 있는 경우.
- 상태·부담 유무·수익자 연결·원천 예산·기일·금액이 불명인 경우.
- 미확정 환불·분쟁 등으로 수익자 순귀속 재원을 확정할 수 없는 경우.
- 정산 순액에 선택 상환액이 이미 반영됐거나, 중복 차감 여부를 판별할 수 없는 경우.
- 기준일 이전 미해결 의무 또는 기초현금과 재원의 중복 가능성이 있는 경우.

가속 만기를 기존 결정에서 읽을 수 있다는 사실만으로 V1이 가속 후 이자·회수까지 지원한다고 주장하지 않는다. 부도·상각도 의무를 0원으로 만들지 않는다.

`UNEVALUATED`에서는 일별 계산 결과와 전체 부족 지표를 `null`로 둔다. 알려진 원천 행은 진단 목적으로 보존할 수 있지만 부분 합계를 전체 결과처럼 표시하지 않는다. 지원 불가 행을 조용히 제외하지 않는다.

구문 오류·음수 금액·예산 초과·중복 내용 충돌·입력 한도 초과는 `INVALID_INPUT`으로 구별하고 역시 수치 결과를 반환하지 않는다. 정상 평가 상태는 `EVALUATED_HYPOTHETICAL`이다. 빈 재원 목록은 명시적 재원 없음이며, 재원 필드 누락과 구별한다.

### 3.7 `horizon_and_input_bounds`

보고서 한 건의 한도는 다음과 같다.

- 합성 수익자 정확히 1명, 고유 기존 선지급 1–32건.
- 고유 정산 재원 0–64개.
- 제출된 release와 obligation 행 합계 1,024개 이하. 중복 제거·기간 필터 **전** 적용한다.
- 기간 `horizon_days` 기본 30, 허용 1–365. 종료일은 `as_of_sim_day + horizon_days`이며 양 끝을 포함한다.
- 개별 금액은 0–1,000,000,000,000원 정수. 이는 보고서 표현 한도이며 금융 한도가 아니다.
- 논리 일은 0–2,147,483,647 정수. 기간·지연 계산 결과도 이 범위를 만족해야 한다.
- 합계·순잔액은 정확한 임의 정밀도 정수로 계산한다. 개별 금액 상한으로 합계를 잘라내지 않는다.

기간 뒤의 알려진 의무·유입은 계산에서 제외하되 건수·금액·최초 날짜를 `outside_horizon`에 표시한다. 기간 밖 값도 입력 검증과 전체 행 한도에 포함한다. 미배치 재원 예산은 기간 뒤 유입으로 간주하지 않는다.

말일 부족 0은 기간 이후 부족 없음이나 완제 판정이 아니다. 선택 집합의 기간 내 일정 완전성을 확인할 수 없으면 `UNEVALUATED`다. 한도 초과 시 자동 샘플링·기간 축소·앞부분 잘라내기를 하지 않는다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "funding-gap-model-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-11-03",
  "provisional": true,
  "attribution_kind": "REQUESTED_DELEGATION_IDENTIFIER_NOT_EXECUTION_ATTESTATION",
  "actual_document_author": "Codex",
  "designated_model_execution": {
    "sonnet_failed_attempts": 3,
    "fable_failed_attempts": 1,
    "reason": "Not logged in",
    "model_review_completed": false
  },
  "model_version": "CAPITAL-FUNDING-GAP-V1",
  "consumer": "funding-gap-report",
  "bases": {
    "capital_main": "079dcca",
    "kix_protocol": "15ea27b",
    "origin": "SUPERVISOR_PROVIDED"
  },
  "dependency_field_binding": {
    "status": "UNDETERMINED",
    "value": null,
    "reason": "Settlement and repayment note contents are absent from the permitted pack.",
    "target": "Consumer reads and applies existing ADOPTED policies without copying forbidden literals or reopening decided policy."
  },
  "entries": {
    "cashflow_viewpoint": {
      "status": "ADOPTED",
      "value": {
        "beneficiary_id": "demo-org-alpha",
        "scope": "SELECTED_EXISTING_ADVANCES",
        "settlement_role": "FUNDING_SOURCE",
        "repayment_role": "CASH_OBLIGATION",
        "repayment_as_available_cash": false,
        "source_basis": "BENEFICIARY_NET_BEFORE_SELECTED_REPAYMENTS",
        "forecast_contract": "UNCHANGED",
        "non_posting": true,
        "funds_executed": false,
        "production": "NOT_AUTHORIZED",
        "labels": ["SIMULATED", "HYPOTHETICAL_FUNDING_GAP"],
        "repayment_allocation_policy_created": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-03",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "One beneficiary perspective separates available settlement assumptions from contractual repayment obligations.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "opening_cash_assumption": {
      "status": "ADOPTED",
      "value": {
        "default_krw": 0,
        "explicit_override": "NONNEGATIVE_SYNTHETIC_INTEGER",
        "origin_required": true,
        "disjoint_from_source_budgets": true,
        "infer_from_advance_or_ledger": false,
        "automatic_topup": false,
        "external_in_period_funding": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-03",
      "cap_rows": ["CAP-01", "CAP-20"],
      "rationale": "An explicit assumption avoids inventing liquidity from exposure, prior disbursement or accounting projections.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "source_identity_and_budget": {
      "status": "ADOPTED",
      "value": {
        "source_key": [
          "workspace_id",
          "beneficiary_id",
          "claim_id",
          "settlement_entitlement_id",
          "currency"
        ],
        "currency": "KRW",
        "budget_basis": "REMAINING_UNRECEIVED_UNUSED_BENEFICIARY_ENTITLEMENT",
        "release_identity": ["source_key", "release_id"],
        "release_sum_lte_budget": true,
        "unreleased_budget_is_cash": false,
        "advance_references_multiply_budget": false,
        "identical_repeats": "COUNT_ONCE",
        "conflicting_repeats": "INVALID_INPUT",
        "unresolved_aliases": "UNEVALUATED",
        "obligation_identity": ["advance_id", "obligation_id"],
        "already_netted_selected_repayment": "UNEVALUATED"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-03",
      "cap_rows": ["CAP-04", "CAP-08"],
      "rationale": "Each underlying settlement entitlement supplies one budget even when several advances reference it.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "due_day_ordering": {
      "status": "ADOPTED",
      "value": {
        "snapshot_cut": "END_OF_AS_OF_SIM_DAY",
        "start": "as_of_sim_day + 1",
        "same_day_order": ["SOURCE_RELEASES", "AGGREGATE_DUE_OBLIGATIONS"],
        "advance_priority": null,
        "delay_days_min": 0,
        "availability": "base_available_sim_day + delay_days",
        "delay_changes_obligation_due_day": false,
        "pre_start_unresolved_obligations": "UNEVALUATED"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-03",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Explicit daily ordering makes chronology reproducible without introducing repayment priorities.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "shortfall_and_carry": {
      "status": "ADOPTED",
      "value": {
        "arithmetic": "EXACT_INTEGER_KRW",
        "initial_net": "opening_cash",
        "daily_net": "previous_net + released_sources - newly_due_obligations",
        "carry": "max(daily_net, 0)",
        "shortfall": "max(-daily_net, 0)",
        "peak_shortfall": "max(daily_shortfall)",
        "terminal_shortfall": "shortfall_at_horizon_end",
        "sum_daily_shortfalls": false,
        "retain_negative_net": true,
        "preserve_historical_shortages": true,
        "derive_interest_or_default": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-03",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Signed cumulative balance preserves shortages without repeatedly counting the same uncovered obligation.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "unsupported_case_policy": {
      "status": "ADOPTED",
      "value": {
        "defaulted_writeoff_recovery": "UNEVALUATED",
        "accelerated_or_scheduled_acceleration": "UNEVALUATED",
        "slice_encumbered_or_restricted_source": "UNEVALUATED",
        "unknown_state_identity_budget_amount_or_day": "UNEVALUATED",
        "unresolved_refund_or_dispute": "UNEVALUATED",
        "incomplete_or_ambiguous_policy_binding": "UNEVALUATED",
        "scope": "ENTIRE_SELECTED_REPORT",
        "unevaluated_numeric_results": null,
        "silent_exclusion": false,
        "partial_success_total": false,
        "malformed_or_conflicting_input": "INVALID_INPUT",
        "supported_status": "EVALUATED_HYPOTHETICAL"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-03",
      "cap_rows": ["CAP-04", "CAP-08", "CAP-20"],
      "rationale": "Unsupported lifecycle and entitlement cases remain visible instead of producing misleading zero amounts or partial coverage.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "horizon_and_input_bounds": {
      "status": "ADOPTED",
      "value": {
        "beneficiaries": 1,
        "advances_min": 1,
        "advances_max": 32,
        "sources_min": 0,
        "sources_max": 64,
        "raw_event_rows_max": 1024,
        "horizon_days_default": 30,
        "horizon_days_min": 1,
        "horizon_days_max": 365,
        "end": "as_of_sim_day + horizon_days",
        "individual_amount_min_krw": 0,
        "individual_amount_max_krw": 1000000000000,
        "sim_day_min": 0,
        "sim_day_max": 2147483647,
        "aggregate_integer_precision": "ARBITRARY",
        "outside_horizon": "DISCLOSE_COUNT_AMOUNT_AND_FIRST_DAY",
        "truncation": false,
        "limit_kind": "REPORT_CAPACITY_NOT_FINANCIAL_TERMS"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-03",
      "cap_rows": ["CAP-01", "CAP-20"],
      "rationale": "Bounded complete inputs support deterministic reporting without implying lending limits or silently hiding later obligations.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| 수용 기준 | 충족 위치 |
|---|---|
| 일곱 결정 항목과 단일 기계 판독 블록 | §1, §3, §4 |
| 단일 수익자 관점·재원과 의무 중복 합산 금지 | §3.1–3.3 |
| 고유 예산·기초현금·당일 순서·정수 이월·부족 | §3.2–3.5 |
| 지연·공유 재원·정확 충족·1원 부족 예시 | §3.5 |
| 부도·가속·슬라이스 부담 미평가 | §3.6 |
| forecast 불변·가상·비게시·준비금 및 여신 승인과 무관 | §3.1, §3.2, §6–7 |

다섯 예시의 순잔액·최대 부족 산술을 메모리 내 계산으로 확인했다. 저장소 파일 변경, 구현 시험 또는 적합성 검증을 수행했다는 주장은 하지 않는다.

## 6. Open risks

일 단위 유입 우선 가정은 장중 부족을 포착하지 못한다. 선택하지 않은 의무와 모델에 없는 비용도 결과에 포함되지 않는다.

정산 권리의 고유성, 잔여 순액 및 기존 상환 차감 여부를 원천에서 확인할 수 있어야 한다. 해당 근거가 없으면 계산식을 적용할 수 있어도 보고서는 미평가다.

지정 모델의 실행 검토와 선행 정책의 정확한 필드 연결은 완료되지 않았다. upstream receipt, 실제 유동성, 회계 인식 또는 법적 상계 가능성을 이 문서로 증명하지 않는다.

## 7. 후속 작업

`funding-gap-report`는 선행 정산·상환 결정의 ADOPTED 값을 원문에서 읽어 정책 출처와 snapshot을 기록하고, 기존 forecast를 변경하지 않는 별도 읽기 전용 보고서로 구현한다. 기존 계약의 경로·필드 이름은 이 문서가 추정하여 지정하지 않는다.

검증에는 위 예시, 반복 참조 불변성, 예산 초과 거절, 원천 순액의 중복 차감 방지, 지원 불가 행의 전체 미평가, 기간 경계 및 정수 정확성을 포함한다. 게시·지급·상환 명령을 호출하지 않아야 한다.

새 vector 파일을 추가할 때는 저장소 지침에 따라 문서 표면 목록과 README를 함께 갱신하고 `python3 scripts/docs_surface.py --check`를 실행한다. 본 결정은 treasury 운영, 준비금 조성·해제, 신규 여신 승인 또는 실제 자금 실행을 열지 않는다.
