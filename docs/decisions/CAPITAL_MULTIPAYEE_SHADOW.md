# CAPITAL_MULTIPAYEE_SHADOW — 결정된 클래스 우선 배정을 위한 한정 다중 수취인 입력

**PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**  
**결정자:** Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)  
**결정일:** 2026-10-30 · **기준:** KIX-CAPITAL main `95815c4` · kix-protocol `6dfb03a`

시뮬레이션·제품 설계 전용이다. 청약이 아니며 실자금은 움직이지 않는다. production은 `NOT_AUTHORIZED`, 모든 그림자 효과는 미적용이다. 법무·세무·회계 해석은 전문가 검토 전 작업 가정이다. upstream 계약 채택·영수증·SEMANTIC_CONFORMANCE를 주장하지 않는다.

결정 노드는 `multipayee-shadow-input-decision`, 의존 노드는 `settlement-policy-decision`, `shadow-policy-decision`, `shadow-refund-resale`, `decision-guard-additions`다. 이 문서는 금융 우선순위를 다시 결정하지 않고, 이미 결정된 배정을 실행할 **Capital 로컬 합성 입력 계약**만 정한다.

출처는 supervisor pack과 그 안의 현재 노트·검토 발췌다. 위 결정자 표기는 기존 위임 결정의 귀속이며, 이번 문서 개정은 Codex가 수행했다. 지정 Claude CLI 실행이나 모델 전환을 수행했다고 주장하지 않는다. 기준 커밋은 supervisor 제공값이다. 허용 목록 밖인 선행 정산·그림자 정책 원문은 직접 열지 않았으며, 상속 규칙은 제공된 검토 발췌를 근거로 유지한다.

## 1. 결정 요약

`ADOPTED`는 이 위임 범위 안의 잠정 제품 결정이며 upstream 채택이나 구현 완료를 뜻하지 않는다.

| item | 결정 | CAP rows | consumer |
|---|---|---|---|
| `synthetic_payee_identity` | 유일한 합성 ASCII 라벨; 스냅샷당 수취인 한 행; 법적 신원 아님 | CAP-02, CAP-05 | `multipayee-shadow-input` 입력 어댑터 |
| `class_mapping_and_unknowns` | 명시적 클래스; 어휘·우선순위·비교자는 `CAPITAL-ALLOC-V1`에서 로드; 미지 클래스 전체 거부 | CAP-02, CAP-05 | 정책 로더 |
| `single_cut_allocation_inputs` | 동결 현금 한 값과 잔여 의무 벡터 한 벌; 누적·이력 조회·영구 효과 없음 | CAP-02, CAP-05 | `policy-simulator`, `shadow-refund-resale` |
| `within_class_caps_and_rounding` | 상속 클래스 우선·최대 잉여·라벨 오름차순 동률; 잔여 의무 상한; 정확 정수 산술 | CAP-02, CAP-05 | 그림자 배정기 |
| `fixture_capacity_bounds` | 최대 64행, 32,768바이트, 금액별·의무 합 1조 합성 KRW | CAP-08, CAP-20 | 입력 검증 |
| `shadow_comparison_labels` | 고정 그림자 mode, 상속 status, 호환 스냅샷만 수치 비교; 실패 금액은 null | CAP-09, CAP-20 | 비교 표시 |

여섯 항목 모두 `ADOPTED`다. 소비 구현과 여섯 바인딩의 상태는 `PENDING_CONSUMER`로 유지한다.

## 2. KIX 비전 연결

[CAPITAL_REQUIREMENTS_KO.md](../CAPITAL_REQUIREMENTS_KO.md)의 제공 발췌는 실행·참조 핀과 역사적 결정 출처를 구별하고, 설계 후보를 구현 완료로 옮기지 않는다. 이 문서의 기준 커밋도 출처이며 실행 핀을 교체하지 않는다. [SEAMS.md](../SEAMS.md)의 로컬 게이트·upstream 채택 구분에 따라 합성 계산 성공은 생산 적합성이나 CAP-16 바인딩을 증명하지 않는다.

[CAPITAL_CLAIM_SLICE_REGISTRY.md](CAPITAL_CLAIM_SLICE_REGISTRY.md)의 슬라이스 유일성·공유 한도·차입기초 보호는 해당 노드에 남긴다. 합성 수취인 행은 참여 자격이나 클레임 슬라이스를 만들지 않는다. [CAPITAL_ACCOUNTS_TAX_LEGAL.md](CAPITAL_ACCOUNTS_TAX_LEGAL.md)의 전문가 검토 경계를 유지하며, 계산 금액으로 법적 채무·수익 인식·세무 처리를 추론하지 않는다.

[VALIDATION.md](../VALIDATION.md)의 합성 검증 경계처럼 결과는 미적용 진단이다. 재현 가능한 다중 수취인 입력은 향후 어댑터 검증을 가능하게 하지만, 기존 FSM·정산 원장·운영 권한을 확장하지 않는다. 위 문서들은 모두 pack에 실린 발췌 범위에서만 사용했다.

## 3. 항목별 결정

### 3.1 `synthetic_payee_identity`

입력 버전은 `CAPITAL-MULTIPAYEE-SHADOW-INPUT-V1`이다. 각 수취인 행은 정확히 `payee_label`, `class_id`, `shadow_remaining_obligation_krw` 세 필드를 가진다.

`payee_label`은 `^fx-[a-z0-9][a-z0-9_-]{0,60}$`에 맞는 4–64 ASCII 바이트다. 동일성은 바이트 일치이며 트리밍·정규화·별칭·대소문자 접기는 없다. `fixture_id`와 `snapshot_id`에도 같은 문법을 적용한다.

신원 범위는 `(fixture_id, snapshot_id, payee_label)`이다. 라벨은 클래스 간과 의무 0 행을 포함하여 스냅샷 전체에서 유일해야 한다. 중복은 전체 입력 거부이며 병합하지 않는다. 한 라벨은 정확히 한 클래스에 속한다. 스냅샷 간 라벨 재사용은 지속되는 채권자 신원을 뜻하지 않는다.

표시 순서는 `payee_label` ASCII 바이트 오름차순이다. 상속 동률 비교자도 같은 순서이며 입력 배열 순서는 배정에 영향을 주지 않는다. 실명·계좌·법적 식별자 필드는 허용하지 않는다.

### 3.2 `class_mapping_and_unknowns`

각 행은 `class_id`를 명시해야 한다. 클래스 어휘·우선순위·동률 비교자는 채택된 `CAPITAL-ALLOC-V1`에서 로드한다. 제공 발췌가 확인한 클래스는 다음 순서다.

1. `PROTECTED_THIRD_PARTY`
2. `COUNTERPARTY_PROCEEDS`
3. `ECOSYSTEM_ROYALTY`
4. `PLATFORM_FEE`

이 목록은 상속 정책 설명이며 독립된 정책 정의가 아니다. 구현은 원문에서 로드한 표를 사용하고 금융 우선순위를 코드 리터럴로 복제하지 않는다. 라벨로 클래스를 추론하지 않는다.

문법상 유효하지만 어휘에 없는 클래스는 `INVALID_INPUT/UNKNOWN_CLASS`, 누락된 필드는 `INVALID_INPUT/MISSING_FIELD`, 클래스 형식 오류는 `INVALID_INPUT/INVALID_CLASS`다. 모두 전체 입력 거부이며 대체 클래스·조용한 생략·부분 배정은 없다. 의무 0 행도 검증한다.

배정·그림자 정책의 출처 digest를 계산 전에 동결한다. 필수 정책이 없거나 읽기·파싱에 실패하면 `adapter_outcome: NOT_BOUND`와 null 금액을 반환한다. `NOT_BOUND`는 정책 로드 실패에 한정한다. 이미 채택된 우선순위나 동률 규칙을 다시 `DECISION_REQUIRED`로 돌리지 않는다. 원문과 발췌가 충돌하면 선행 정책 원문이 우선한다.

### 3.3 `single_cut_allocation_inputs`

최상위 객체는 정확히 `schema`, `fixture_id`, `snapshot_id`, `shadow_cash_krw`, `payees`를 가진다. `schema` 값은 입력 버전과 같다. 미지 필드와 중복 JSON 키를 거부하며 `payees`는 행 객체의 배열이어야 한다.

금액은 음이 아닌 JSON 정수다. 불리언·문자열·분수·지수 표기는 거부한다. 입력 에코·결과·비교 델타를 포함한 금액 키는 모두 `shadow_`로 시작한다. 잔여 의무는 계산 직전 fixture 작성자의 합성 가정이다. 액면·과거 지급·이전 그림자 결과·수수료·환불에서 자동 유도하지 않는다.

한 번 동결한 페이로드와 정책 집합으로 전체 계산과 비교를 수행한다. 클래스 사이 또는 비교 실행 사이에 가변 상태를 다시 읽지 않는다. 식별자 일치만으로 입력 동등성을 판단하지 않는다.

성공 결과는 각 행의 `payee_label`, `class_id`, `shadow_allocation_krw`, `shadow_remaining_after_krw`와 합계 `shadow_total_allocated_krw`, `shadow_unallocated_cash_krw`다. 의무 0 행도 출력한다. 빈 배열은 유효하며 현금 전액이 미배정이다.

이력 조회·정산 쓰기·재생 원장·자동 이월은 없다. 같은 입력의 재계산은 가설 계산의 반복이다. **누적 늦은 현금, 참여, 클레임 슬라이스, 환불·리셀 수명주기와 UC1–UC4는 기존 노드에 남긴다.**

### 3.4 `within_class_caps_and_rounding`

`CAPITAL-ALLOC-V1`의 클래스 우선순위·클래스 내 비례 배분·최대 잉여·라벨 오름차순 동률 규칙을 그대로 적용한다. 새로운 금융 비율·수수료·권리·인수 한도는 없다.

클래스를 상속 우선순위로 처리한다. 남은 현금을 `C`, 행별 잔여 의무를 `r_i`, 클래스 의무 합을 `R`이라 하면 예산은 `B = min(C, R)`다. `R = 0`이면 나눗셈 없이 전 행에 0을 배정한다. 그 외에는 다음을 적용한다.

- 기본 배정: `q_i = floor(B × r_i / R)`.
- 잉여 분자: `m_i = (B × r_i) mod R`.
- 남은 `B − Σq_i` 단위를 `m_i` 내림차순으로 한 단위씩 배정한다.
- 같은 잉여는 **`payee_label` ASCII 바이트 오름차순**으로 가른다.

라벨 유일성이 동률의 전순서를 보장한다. 클래스 처리 후 현금에서 `B`를 차감한다. 하위 클래스는 상위 클래스의 잔여 의무가 충족된 뒤에만 받으며, 전 클래스 처리 후 현금은 미배정으로 남는다. 전 과정에 정확 정수 산술을 사용한다.

불변식은 `0 ≤ a_i ≤ r_i`, `remaining_after_i = r_i − a_i`, `Σa_i + unallocated = cash`다. 이는 수학 표기이며 출력 키가 아니다.

**`fsm_expressible: false`.** 제공 발췌에 따르면 고정 vendor FSM `7481b0e`의 두 수취인 기준선은 클래스당 복수 수취인·클래스 내 비례 배분·보호 제3자 라인을 표현하지 못한다. 이 계산은 FSM 명령·전이·행을 만들지 않는다. 기준선을 늘리기 위한 fabricated row나 행 조작은 금지한다. FSM 반영은 upstream 변경 이후 별도 노드의 일이다.

아래는 실행 fixture가 아닌 산술 기대치다. `P`는 보호 클래스, `L`은 그보다 낮은 상속 클래스다. P1–P3과 L1은 각각 `fx-p1`–`fx-p3`, `fx-l1`의 표 별칭이다.

| 사례 | 잔여 의무 | 현금 | 배정 | 배정 후 잔여 | 미배정 |
|---|---|---:|---|---|---:|
| 보호 클래스 내부 소진 | P1=5, P2=3; L1=9 | 5 | P1=3, P2=2, L1=0 | P1=2, P2=1, L1=9 | 0 |
| 같은 잉여 동률 | P1=1, P2=1, P3=1 | 2 | P1=1, P2=1, P3=0 | P1=0, P2=0, P3=1 | 0 |
| 현금 0 | P1=5, P2=3 | 0 | P1=0, P2=0 | P1=5, P2=3 | 0 |
| 이미 전부 충족된 의무 | P1=0, P2=0 | 7 | P1=0, P2=0 | P1=0, P2=0 | 7 |
| 현금이 잔여 의무 초과 | P1=2, P2=1; L1=4 | 10 | P1=2, P2=1, L1=4 | P1=0, P2=0, L1=0 | 3 |

첫 사례의 기본 배정은 3과 1, 잉여 분자는 1과 7이므로 P2가 추가 단위를 받는다. 동률 사례는 기본 배정이 모두 0, 잉여 분자가 모두 2이므로 `fx-p1`, `fx-p2`가 먼저 받는다.

### 3.5 `fixture_capacity_bounds`

다음 한도는 포함 경계이며 합성 계산 용량이다. 금융 조건이나 실제 취급 한도가 아니다.

| 차원 | 한도 |
|---|---:|
| UTF-8 입력 페이로드 | 32,768바이트 |
| 수취인 행 수 | 0–64 |
| fixture·snapshot·payee 식별자 | 4–64 ASCII 바이트 |
| 클래스 식별자 | 1–64 ASCII 바이트, 상속 어휘 멤버십 필수 |
| 현금, 각 잔여 의무, 잔여 의무 합 | 각각 0–1,000,000,000,000 KRW |

원본 페이로드 크기를 파싱 전에 검사하고 모든 검증을 배정 전에 끝낸다. 용량 초과는 `adapter_outcome: SIMULATION_CAPACITY`, 초과 차원과 null 금액을 반환한다. 잘라내기·부분 계산·자동 배치 분할은 없다.

상한 초과는 용량 오류이며 음수·잘못된 금액 형식은 입력 오류다. 클래스 길이 상한 초과도 용량 오류이고, 한도 안의 미지 클래스는 `UNKNOWN_CLASS`다. 중간 곱은 `10^24`에 이를 수 있으므로 임의 정밀도 정수를 요구한다.

### 3.6 `shadow_comparison_labels`

모든 결과는 `mode: SHADOW_NOT_APPLIED`, 라벨 `SIMULATED`, `SYNTHETIC_FIXTURE_PROFILE`, `PROVISIONAL_PRODUCT_DECISION`과 `funds_executed:false`, `effects_applied:false`, `production:NOT_AUTHORIZED`를 유지한다. mode는 성공 여부와 무관하다.

결과의 `shadow_status`는 상속 그림자 정책의 닫힌 어휘만 사용한다. 어댑터 진단은 별도 `adapter_outcome`과 `reason`이다.

| `adapter_outcome` | `reason` | `shadow_status` | 금액 |
|---|---|---|---|
| `COMPUTED` | 없음 | `SHADOW_COMPUTED` | 계산값 |
| `INVALID_INPUT` | `UNKNOWN_CLASS`, `INVALID_CLASS`, `MISSING_FIELD` | `SHADOW_INPUT_UNKNOWN` | null |
| `INVALID_INPUT` | `INVALID_JSON`, `DUPLICATE_LABEL`, `DUPLICATE_KEY`, `UNKNOWN_FIELD`, `INVALID_IDENTIFIER`, `INVALID_AMOUNT`, `SCHEMA_MISMATCH` | `SHADOW_INCONSISTENT` | null |
| `SIMULATION_CAPACITY` | 초과 차원 | `SHADOW_DEFERRED` | null |
| `NOT_BOUND` | 정책 로드 실패 | `SHADOW_NOT_BOUND` | null |

잘못된 JSON·UTF-8는 `INVALID_JSON`, 객체·배열 타입 또는 버전 불일치는 `SCHEMA_MISMATCH`로 처리한다. 정책 로드 실패 시 계산하지 않는다. 로드 성공 후 입력 검증 순서는 크기→파싱→스키마→한도→클래스이며 첫 위반을 보고한다. 실패 시 부분 배정 행을 내보내지 않고 금액 페이로드를 null로 둔다. 실패를 0 배정 성공으로 표시하지 않는다.

이 표는 상속 status를 확장하지 않는다. 원문 의미와 차이가 확인되면 선행 그림자 정책이 우선하며 소비 구현에서 사상을 검증한다.

수치 비교는 두 `COMPUTED` 결과의 동결 현금·라벨 집합·클래스 멤버십·잔여 의무·KRW 단위가 같을 때만 `COMPARABLE`이다. 배열 순서는 동등성에 영향을 주지 않는다. 양쪽 알고리즘·정책 신원과 출처 digest를 기록하며 서로 다른 정책의 의도적 비교는 허용한다.

차이는 후보 − 기준선으로 계산하고 `shadow_allocation_delta_krw`, `shadow_remaining_after_delta_krw`, `shadow_total_allocated_delta_krw`, `shadow_unallocated_cash_delta_krw`로 표시한다. 차이는 금융적 우월이나 오류를 자동 의미하지 않는다. 조건을 충족하지 못하면 `NOT_COMPARABLE`, 이유와 null 델타를 반환한다. 고정 두 수취인 FSM 결과를 맞추기 위한 행 조작은 금지한다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "multipayee-shadow-input-decision",
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-10-30",
  "provisional": true,
  "entries": {
    "synthetic_payee_identity": {
      "status": "ADOPTED",
      "value": {
        "input_version": "CAPITAL-MULTIPAYEE-SHADOW-INPUT-V1",
        "label_pattern": "^fx-[a-z0-9][a-z0-9_-]{0,60}$",
        "identity_scope": ["fixture_id", "snapshot_id", "payee_label"],
        "duplicate_labels": "REJECT_WHOLE_INPUT",
        "rows_per_payee": 1,
        "input_order_significant": false,
        "legal_identity": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-30",
      "cap_rows": ["CAP-02", "CAP-05"],
      "rationale": "Use unique snapshot-scoped synthetic labels without asserting legal identity.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "class_mapping_and_unknowns": {
      "status": "ADOPTED",
      "value": {
        "membership": "EXPLICIT_PER_ROW",
        "vocabulary_and_priority_source": "CAPITAL-ALLOC-V1",
        "comparator_source": "CAPITAL-ALLOC-V1",
        "unknown_class": "REJECT_WHOLE_INPUT",
        "default_class": null,
        "missing_policy_adapter_outcome": "NOT_BOUND",
        "not_bound_scope": "POLICY_LOAD_FAILURE_ONLY",
        "source_binding": "FREEZE_LOADED_POLICY_DIGESTS"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-30",
      "cap_rows": ["CAP-02", "CAP-05"],
      "rationale": "Load adopted classes and priorities without fallback or new economic terms.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "single_cut_allocation_inputs": {
      "status": "ADOPTED",
      "value": {
        "fields": ["schema", "fixture_id", "snapshot_id", "shadow_cash_krw", "payees"],
        "row_fields": ["payee_label", "class_id", "shadow_remaining_obligation_krw"],
        "amount_type": "NONNEGATIVE_JSON_INTEGER",
        "amount_key_prefix": "shadow_",
        "snapshot": "ONE_FROZEN_PAYLOAD_AND_POLICY_SET",
        "unknown_fields_and_duplicate_keys": "REJECT",
        "empty_payees": "VALID_ALL_CASH_UNALLOCATED",
        "history_lookup": false,
        "persistent_effects": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-30",
      "cap_rows": ["CAP-02", "CAP-05"],
      "rationale": "Compute one frozen hypothetical snapshot without cumulative settlement effects.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "within_class_caps_and_rounding": {
      "status": "ADOPTED",
      "value": {
        "policy": "CAPITAL-ALLOC-V1",
        "class_budget": "MIN_REMAINING_CASH_AND_CLASS_OBLIGATION",
        "weight": "REMAINING_OBLIGATION",
        "rounding": "INHERIT_LARGEST_REMAINDER",
        "equal_remainders": "INHERIT_ASCENDING_PAYEE_LABEL",
        "payee_cap": "REMAINING_OBLIGATION",
        "arithmetic": "EXACT_INTEGER",
        "surplus_output": "shadow_unallocated_cash_krw",
        "fsm_expressible": false,
        "fsm_baseline": "PINNED_TWO_PAYEE_7481b0e",
        "fabricated_fsm_rows": "FORBIDDEN"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-30",
      "cap_rows": ["CAP-02", "CAP-05"],
      "rationale": "Preserve inherited allocation and rounding while bounding every payment by remaining obligation.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "fixture_capacity_bounds": {
      "status": "ADOPTED",
      "value": {
        "max_payload_bytes": 32768,
        "max_payee_rows": 64,
        "max_identifier_bytes": 64,
        "max_class_identifier_bytes": 64,
        "shadow_cash_limit_krw": 1000000000000,
        "shadow_row_obligation_limit_krw": 1000000000000,
        "shadow_total_obligation_limit_krw": 1000000000000,
        "overflow_adapter_outcome": "SIMULATION_CAPACITY",
        "financial_limit": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-30",
      "cap_rows": ["CAP-08", "CAP-20"],
      "rationale": "Bound parsing and exact computation independently of financial limits.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "shadow_comparison_labels": {
      "status": "ADOPTED",
      "value": {
        "shadow_mode": "SHADOW_NOT_APPLIED",
        "shadow_status_vocabulary_source": "CAPITAL_SHADOW_POLICY",
        "shadow_status_vocabulary_extended": false,
        "adapter_outcome_to_shadow_status": {
          "COMPUTED": "SHADOW_COMPUTED",
          "INVALID_INPUT/UNKNOWN_CLASS|INVALID_CLASS|MISSING_FIELD": "SHADOW_INPUT_UNKNOWN",
          "INVALID_INPUT/INVALID_JSON|DUPLICATE_LABEL|DUPLICATE_KEY|UNKNOWN_FIELD|INVALID_IDENTIFIER|INVALID_AMOUNT|SCHEMA_MISMATCH": "SHADOW_INCONSISTENT",
          "SIMULATION_CAPACITY": "SHADOW_DEFERRED",
          "NOT_BOUND": "SHADOW_NOT_BOUND"
        },
        "validation_order": ["PAYLOAD_SIZE", "PARSE", "SCHEMA", "BOUNDS", "CLASS"],
        "labels": ["SIMULATED", "SYNTHETIC_FIXTURE_PROFILE", "PROVISIONAL_PRODUCT_DECISION"],
        "comparison_requires": "TWO_COMPUTED_RESULTS_WITH_IDENTICAL_FROZEN_INPUTS_AND_EXPLICIT_POLICY_IDENTITIES",
        "comparison_states": ["COMPARABLE", "NOT_COMPARABLE"],
        "delta_direction": "CANDIDATE_MINUS_BASELINE",
        "amount_key_prefix": "shadow_",
        "failed_amounts_and_incompatible_deltas": null,
        "funds_executed": false,
        "effects_applied": false,
        "production": "NOT_AUTHORIZED"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-30",
      "cap_rows": ["CAP-09", "CAP-20"],
      "rationale": "Keep inherited mode and statuses, explicit failure amounts and compatible snapshot comparisons.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| 수용 기준 | 근거 / 검증 상태 |
|---|---|
| 결정 블록 하나와 여섯 항목 | §4에 한 블록, 여섯 `ADOPTED` 항목 |
| 유일 신원·미지 클래스·입력 한도 | §§3.1–3.2, 3.5 |
| 상속 우선순위·최대 잉여·다섯 작업 예시 | §3.4 |
| 동결 스냅샷과 기존 노드 경계 | §3.3 |
| 운영 금지·그림자 미적용 | 배너, §3.6, §4 |
| 문서 색인·바인딩 | 제공 검토는 `docs/CAP_COVERAGE.md` 참조와 여섯 `PENDING_CONSUMER` 바인딩을 확인했다. 이번 실행에서 재검증하지 않았다 |
| 결정 원장 검증 | 제공된 이전 검증은 이전 트리의 증거다. **2026-10-30 수정본의 원장·바인딩·팩 검사 실행 결과는 UNDETERMINED**: 이번 산출물은 문서 본문이며 저장·명령 실행을 수행하지 않았다 |

**차단 소견 처리:** `DECISION_REQUIRED.md`의 무관한 `advance-case-dossier` 에스컬레이션 추가는 범위 위반이라는 소견을 수용한다. 해당 추가는 최종 PR에서 제외하며 이 결정의 근거·승인 조건·산출물로 사용하지 않는다. 최신 지시는 파일 수정 없이 이 문서만 반환하도록 하므로, 실제 삭제나 PR diff 정리가 완료됐다고 주장하지 않는다. supervisor의 적용 단계에서 그 추가를 제거한다. 수용 기준에 명시된 문서 색인 참조는 유지한다.

## 6. Open risks

선행 정책 규칙은 제공된 검토 발췌에 근거한다. 소비 구현은 원문을 직접 로드하고 클래스 표·동률 비교자·status 의미를 검증해야 한다. 합성 잔여 의무는 법적 유효성이나 완전성의 증거가 아니다. 다중 수취인 FSM 반영과 누적 현금 처리는 이 결정으로 해결되지 않는다.

이전 COA 가드 실패는 제공된 역사적 실행 보고다. 이 개정의 실패나 통과로 전환하지 않으며, 가드 완화·기준선 변경·관련 없는 에스컬레이션 추가를 승인하지 않는다.

## 7. 후속 작업

- supervisor는 이 문서를 저장하고 무관한 `DECISION_REQUIRED.md` 추가를 PR에서 제외한다. 기존 색인 참조와 여섯 `PENDING_CONSUMER` 바인딩을 유지한다.
- 통합 시 결정 원장, 바인딩, 문서 표면, 팩 검사를 실행한다. 문서 변경으로 팩이 달라지면 허용된 팩 벡터만 재고정하고 다시 확인한다. 새 벡터 파일은 문서 표면 등록과 README needle 규칙을 따른다.
- `multipayee-shadow-input` 구현 노드는 정책 로드·digest 동결, 순열 독립성, 상속 동률, 중복·미지 클래스 거부, 용량 경계, 보존 불변식, null 실패와 비교 호환성을 검증한다.
- 누적 늦은 현금·참여·클레임 슬라이스·UC1–UC4·upstream FSM 변경은 기존 또는 별도 노드에 남긴다. production은 계속 `NOT_AUTHORIZED`이며 그림자 효과는 미적용이다.
