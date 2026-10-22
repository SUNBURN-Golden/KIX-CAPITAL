# CAPITAL_MULTIPAYEE_SHADOW — 결정된 클래스 우선 배정을 위한 한정 다중 수취인 입력

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
이 문서는 KIX-CAPITAL 저장소 안의 **시뮬레이션·제품 설계용** 결정이다. 청약이 아니고 실자금이 움직이지 않으며 production은 계속 `NOT_AUTHORIZED`다. 모든 그림자 효과는 `SHADOW_NOT_APPLIED`로 남는다. 영구 정산 기록, UC1–UC4 구현, upstream 계약 변경은 승인하지 않는다. 법무·세무·회계에 닿는 언급은 전문가 검토 전 작업 가정이며 자문이 아니다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `multipayee-shadow-input-decision` (Decision: bounded multi-payee inputs for the decided class-priority allocation) · deps `settlement-policy-decision`, `shadow-policy-decision`, `shadow-refund-resale` · kind `decision` · user_merge `False` |
| 결정자 | **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)** |
| 위임 원문 | 2026-10-08 18:25 KST JunTae Park: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." |
| 결정일 | 2026-10-22 |
| 기준 | KIX-CAPITAL main `cde0bc7` · kix-protocol `8e85ef4` (읽기 전용 `/workspace/capital-run/kixproto-ro`) |
| 실행 출처 | 개정 라운드 4는 Fable 5.1(claude-fable-5-1)이 세 차례 실패한 시도 뒤에 supervisor pack만으로 수행했다 |
| 읽기 범위 | supervisor pack이 허용한 경로만 읽었다. 선행 노트 `CAPITAL_SETTLEMENT_POLICY.md`(`CAPITAL-ALLOC-V1`)·`CAPITAL_SHADOW_POLICY.md`는 허용 경로 밖이라 **직접 열지 않았다.** 클래스 어휘·우선순위·동률 비교자는 그 노트에서 로드하는 상속 의존이며 이 노트는 그 값을 복사하거나 재정의하지 않는다. 충돌 시 선행 노트가 이기고, 입력 형태·용량·비교 규칙은 이 노트가 이긴다 |
| 상태 어휘 | **ADOPTED** = 위임 범위 안의 잠정 값. **UNDETERMINED** = 값을 정할 수 없어 이유만(`value: null`). 여섯 항목 모두 ADOPTED |
| 개정 | 라운드 4: (1) 문서 색인 참조를 **개정 범위 안에서 실제로 수행**했다. `tests/decision_bindings.json`에 여섯 ADOPTED 항목의 `PENDING_CONSUMER` 바인딩 행(consumer_node `multipayee-shadow-input`, 기존 모듈 앵커 `capital/shadow.py`·`capital/policy.py`·`capital/strict_json.py`)을 정렬 순서대로 추가했다. (2) 블록에 `status: PROVISIONAL_PRODUCT_DECISION`을 추가해 선행 노트들과 원장 표기를 맞췄다. (3) kix-protocol 기준을 supervisor 값 `8e85ef4`로 바로잡았다. (4) 원장·바인딩 검사를 실제로 실행해 §5에 결과를 적었다 |

## 1. 결정 요약

| item | 결정 (요지) | CAP rows | 소비 노드 / seam |
|---|---|---|---|
| `synthetic_payee_identity` | **ADOPTED.** 유일한 합성 ASCII 라벨, 스냅샷당 수취인 한 행, 법적 신원 아님 | CAP-02, CAP-05 | `multipayee-shadow-input` (입력 어댑터, 미구축) |
| `class_mapping_and_unknowns` | **ADOPTED.** 행마다 명시적 `class_id`; 어휘·우선순위·비교자는 `CAPITAL-ALLOC-V1`에서 로드; 미지 클래스는 전체 거부 | CAP-02, CAP-05 | 정책 로더 `capital/policy.py` 앵커 |
| `single_cut_allocation_inputs` | **ADOPTED.** 동결된 현금 한 값 + 잔여 의무 벡터 한 벌; 이력 조회·누적·영구 효과 없음 | CAP-02, CAP-05 | `policy-simulator`, `shadow-refund-resale` |
| `within_class_caps_and_rounding` | **ADOPTED.** 상속 클래스 우선·최대 잉여 반올림 유지; 잔여 의무가 상한; 정확 정수 산술 | CAP-02, CAP-05 | 그림자 배정기 `capital/shadow.py` 앵커 |
| `fixture_capacity_bounds` | **ADOPTED.** 최대 64행·32,768바이트·금액 1조 KRW; 위반은 `SIMULATION_CAPACITY` | CAP-08, CAP-20 | 입력 검증 `capital/strict_json.py` 앵커 |
| `shadow_comparison_labels` | **ADOPTED.** `SHADOW_NOT_APPLIED` 봉투 유지; `adapter_outcome` 진단; 호환 스냅샷만 비교 | CAP-09, CAP-20 | 비교 표시 |

## 2. KIX 비전 연결

[CAPITAL_REQUIREMENTS_KO.md](../CAPITAL_REQUIREMENTS_KO.md)는 로컬 개발 권한과 운영 승인을 구분하고 과거 CI·설계 후보를 현재 구현 완료로 옮기지 말라고 한다. [SEAMS.md](../SEAMS.md)는 로컬 게이트 통과가 SEMANTIC_CONFORMANCE나 upstream 채택이 아님을 정한다. 이 입력 계약은 그 경계 안에서 재현 가능한 합성 배정 실험의 입력만 정의한다.

[CAPITAL_CLAIM_SLICE_REGISTRY.md](CAPITAL_CLAIM_SLICE_REGISTRY.md)는 슬라이스 유일성·공유 한도·차입기초 보호를 자기 노드에 둔다. 수취인 행은 클레임 슬라이스도 참여 자격도 만들지 않는다. [CAPITAL_ACCOUNTS_TAX_LEGAL.md](CAPITAL_ACCOUNTS_TAX_LEGAL.md)의 전문가 검토 경계를 유지하며 fixture 신원은 법적 수취인 신원이 아니다. [CAPITAL_DEFAULT_RECOVERY.md](CAPITAL_DEFAULT_RECOVERY.md)와 같이 숫자 한도를 선행 노트에서 복사하지 않고 필드명으로만 인용한다. [VALIDATION.md](../VALIDATION.md)의 과거 결과는 이 개정의 통과 증거가 아니며, §5의 결과만 이 개정의 실행 기록이다. upstream 영수증은 주장하지 않는다.

## 3. 항목별 결정

### 3.1 `synthetic_payee_identity`

입력 버전 `CAPITAL-MULTIPAYEE-SHADOW-INPUT-V1`. 행은 정확히 `payee_label`, `class_id`, `shadow_remaining_obligation_krw` 세 필드다. 라벨은 `^fx-[a-z0-9][a-z0-9_-]{0,60}$`(4–64 ASCII 바이트)이며 동일성은 바이트 일치다. 트리밍·정규화·별칭·대소문자 접기 없음.

라벨은 스냅샷 전체(클래스 간, 의무 0 행 포함)에서 유일하다. 중복은 전체 입력을 거부하며 병합하지 않는다. 각 라벨은 정확히 한 클래스에 속한다. 신원은 `(fixture_id, snapshot_id, payee_label)`이고 두 상위 식별자도 같은 문법을 따른다. 스냅샷 간 재사용은 계속되는 채권자 신원을 만들지 않는다.

표시는 라벨 ASCII 오름차순이다. 표시·입력 순서는 상속 동률 비교자를 절대 대체하지 않는다. 실명·계좌·법적 식별자는 스키마 밖이다.

### 3.2 `class_mapping_and_unknowns`

모든 행에 `class_id`를 요구한다. 클래스 어휘·우선순위·동률 비교자는 채택된 `CAPITAL-ALLOC-V1`에서 로드하며 라벨에서 추론하거나 정책 리터럴을 복사하지 않는다.

문법상 유효하지만 미지인 클래스는 전체 입력을 `adapter_outcome: INVALID_INPUT`, 이유 `UNKNOWN_CLASS`로 거부한다. 누락·형식 오류는 `INVALID_CLASS`. 용량 위반은 §3.5. 의무 0 행도 검증한다. 대체 클래스·조용한 생략·부분 배정은 없다.

계산 전 배정 정책·그림자 정책 출처 digest를 동결한다. 필수 정책이 없거나 읽을 수 없거나 미해결이면 `adapter_outcome: NOT_BOUND`와 null 금액이다. 채택된 분기는 추가 결정이 필요 없고, 상속된 미정·연기 분기는 그 노트가 정한 not-bound 경로를 따른다. pack은 구체 클래스 어휘와 비교자를 담지 않으므로 그것은 상속 의존이며 새로 미정인 금융 우선순위가 아니다.

### 3.3 `single_cut_allocation_inputs`

입력 객체는 정확히 `schema`(`CAPITAL-MULTIPAYEE-SHADOW-INPUT-V1`), `fixture_id`, `snapshot_id`, `shadow_cash_krw`, `payees`다. 미지 필드와 중복 JSON 키는 거부한다. 입력 에코·결과·비교 델타를 포함한 모든 금액 키는 `shadow_`로 시작한다.

금액은 음이 아닌 JSON 정수다. 불리언·문자열·분수·지수 표기는 거부한다. 잔여 의무는 이 계산 직전의 fixture 작성자 가정이며 검증된 채무 증거가 아니다. 액면·과거 지급·수수료·환불·이전 그림자 결과에서 유도하지 않는다.

페이로드와 정책 출처를 한 번 동결한다. 클래스 사이나 비교 실행 사이에 가변 상태를 다시 읽지 않는다. 식별자만으로 입력 동등성을 주장하지 않는다.

성공 결과는 행별 `payee_label`, `class_id`, `shadow_allocation_krw`, `shadow_remaining_after_krw`와 합계 `shadow_total_allocated_krw`, `shadow_unallocated_cash_krw`다. 의무 0 행도 보인다. 빈 배열은 유효하며 전액 미배정이다.

이력 조회·정산 쓰기·재생 원장·자동 이월은 없다. 재계산은 가설 계산의 반복이다. 누적 늦은 현금, 참여, 클레임 슬라이스, 환불·리셀 수명주기 효과는 기존 노드에 남는다.

### 3.4 `within_class_caps_and_rounding`

`CAPITAL-ALLOC-V1`의 클래스 우선순위와 최대 잉여 규칙을 유지한다. 금융 비율·수수료·권리·인수 한도는 새로 두지 않는다.

상속 우선순위 순서로 클래스를 처리한다. 클래스마다 남은 현금 `C`, 의무 `r_i`, 합 `R`, 클래스 예산 `B = min(C, R)`. `R = 0`이면 나눗셈 없이 0 배정. 그 외:

- 기본: `q_i = floor(B × r_i / R)`
- 잉여 분자: `m_i = (B × r_i) mod R`
- `B − Σq_i` 단위를 `m_i` 내림차순으로 배분하고, 같은 잉여는 상속 비교자로 가른다.

합성 라벨은 비교자가 허용하는 곳에서만 신원을 제공한다. 실제 동률을 풀 정보가 없으면 `NOT_BOUND`를 반환하며 알파벳·입력 순서를 대체로 쓰지 않는다.

전 과정 정확 정수 산술. 배정은 잔여 의무를 넘지 않는다. 하위 클래스는 상위 잔여 의무가 충족된 뒤에만 현금을 받는다. 잉여는 미배정으로 남는다. 불변식: `0 ≤ a_i ≤ r_i`, `remaining_after_i = r_i − a_i`, `Σa_i + unallocated = cash` (수학 기호이며 출력 키가 아니다).

**작업 예시.** 합성 KRW 정수. `P`는 상속 보호 클래스, `L`은 상속 하위 클래스. P1–P3, L1은 유효 라벨의 표 별칭이며 같은 잉여에서 상속 비교자가 P1, P2, P3 순으로 매긴다고 가정한다.

| 사례 | 잔여 의무 | 현금 | 배정 | 배정 후 잔여 | 미배정 |
|---|---|---:|---|---|---:|
| 보호 클래스 안에서 현금 소진 | P1=5, P2=3; L1=9 | 5 | P1=3, P2=2, L1=0 | P1=2, P2=1, L1=9 | 0 |
| 같은 잉여 동률 | P1=1, P2=1, P3=1 | 2 | P1=1, P2=1, P3=0 | P1=0, P2=0, P3=1 | 0 |
| 현금 0 | P1=5, P2=3 | 0 | P1=0, P2=0 | P1=5, P2=3 | 0 |
| 의무 전부 충족 | P1=0, P2=0 | 7 | P1=0, P2=0 | P1=0, P2=0 | 7 |
| 현금이 의무 초과 | P1=2, P2=1; L1=4 | 10 | P1=2, P2=1, L1=4 | P1=0, P2=0, L1=0 | 3 |

첫 사례: 기본 3과 1, 잉여 분자 1과 7이므로 P2가 추가 단위를 받는다. 동률 사례: 기본 모두 0, 잉여 분자 모두 2이므로 상속 순위 상위 둘이 1씩 받는다. 예시는 산술 기대치이며 실행된 fixture나 검증된 구체 정책 바인딩이 아니다.

### 3.5 `fixture_capacity_bounds`

포함 한도(합성 계산 한도이며 금융 조건이 아니다):

| 차원 | 한도 |
|---|---:|
| UTF-8 페이로드 | 32,768 바이트 |
| 수취인 행 | 0–64 |
| fixture·snapshot·payee 식별자 | 4–64 ASCII 바이트 |
| 클래스 식별자 | 1–64 ASCII 바이트 + 상속 멤버십 |
| 현금, 각 의무, 의무 합 | 각 0–1,000,000,000,000 KRW |

파싱 전 페이로드 크기를 검사하고, 배정 전 스키마와 한도 전체를 검증한다. 용량 위반은 `adapter_outcome: SIMULATION_CAPACITY`, 초과 차원, null 금액이다. 잘라내기나 배치 분할은 없다. 중간 곱은 `10^24`에 이를 수 있으므로 임의 정밀도 정수를 쓴다. 부동소수점은 불충분하다.

### 3.6 `shadow_comparison_labels`

모든 결과는 `status: SHADOW_NOT_APPLIED`, 라벨 `SIMULATED`·`SYNTHETIC_FIXTURE_PROFILE`·`PROVISIONAL_PRODUCT_DECISION`, `funds_executed:false`, `effects_applied:false`, `production:NOT_AUTHORIZED`를 유지한다. 진단은 상속 그림자 상태 어휘를 확장하지 않고 `adapter_outcome`에 둔다:

| `adapter_outcome` | 그림자 `status` | 금액 페이로드 |
|---|---|---|
| `COMPUTED` | `SHADOW_NOT_APPLIED` | 계산 금액 |
| `INVALID_INPUT` | `SHADOW_NOT_APPLIED` | null; 검증 이유 |
| `SIMULATION_CAPACITY` | `SHADOW_NOT_APPLIED` | null; 초과 차원 |
| `NOT_BOUND` | `SHADOW_NOT_APPLIED` | null; 미해결 의존 |

실패한 계산은 결코 0 배정 성공으로 보이지 않는다.

비교 메타데이터는 `comparison_state: COMPARABLE | NOT_COMPARABLE`다. 수치 비교는 동일한 동결 현금·라벨 집합·클래스 멤버십·잔여 의무·KRW 단위를 가진 두 `COMPUTED` 결과를 요구하며 양쪽의 알고리즘/정책 신원과 출처 digest를 기록한다. 의도적으로 다른 정책의 비교는 허용되고 차이는 오류도 금융적 우월도 아니다. 후보 − 기준선을 `shadow_allocation_delta_krw`, `shadow_remaining_after_delta_krw`, `shadow_total_allocated_delta_krw`, `shadow_unallocated_cash_delta_krw`로 보고한다. 그 외는 `NOT_COMPARABLE`, 이유, null 델타다. 고정된 두 수취인 기준선을 늘리기 위한 행 조작은 금지한다. 동등성은 이 스냅샷에만 적용되며 집행된 정산이나 upstream 적합성을 증명하지 않는다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "multipayee-shadow-input-decision",
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-10-22",
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
        "legal_identity": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-02", "CAP-05"],
      "rationale": "Bound synthetic identity and reject duplicate obligations without asserting legal identity.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "class_mapping_and_unknowns": {
      "status": "ADOPTED",
      "value": {
        "membership": "EXPLICIT_PER_ROW",
        "vocabulary_and_priority_source": "CAPITAL-ALLOC-V1",
        "unknown_class": "REJECT_WHOLE_INPUT",
        "default_class": null,
        "missing_policy_adapter_outcome": "NOT_BOUND",
        "source_binding": "FREEZE_LOADED_POLICY_DIGESTS"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-02", "CAP-05"],
      "rationale": "Apply inherited adopted classes without fallback or invented financial priorities.",
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
      "date": "2026-10-22",
      "cap_rows": ["CAP-02", "CAP-05"],
      "rationale": "Define one frozen calculation without cumulative or persistent settlement effects.",
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
        "equal_remainders": "INHERIT_POLICY_COMPARATOR",
        "payee_cap": "REMAINING_OBLIGATION",
        "arithmetic": "EXACT_INTEGER",
        "surplus_output": "shadow_unallocated_cash_krw"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-02", "CAP-05"],
      "rationale": "Preserve class priority and rounding while preventing overpayment.",
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
      "date": "2026-10-22",
      "cap_rows": ["CAP-08", "CAP-20"],
      "rationale": "Bound parsing and exact computation without changing economic terms.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "shadow_comparison_labels": {
      "status": "ADOPTED",
      "value": {
        "shadow_result_status": "SHADOW_NOT_APPLIED",
        "adapter_outcome_to_shadow_status": {
          "COMPUTED": "SHADOW_NOT_APPLIED",
          "INVALID_INPUT": "SHADOW_NOT_APPLIED",
          "SIMULATION_CAPACITY": "SHADOW_NOT_APPLIED",
          "NOT_BOUND": "SHADOW_NOT_APPLIED"
        },
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
      "date": "2026-10-22",
      "cap_rows": ["CAP-09", "CAP-20"],
      "rationale": "Preserve unapplied status and reject fabricated comparison compatibility.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| 수용 기준 | 증거 / 상태 |
|---|---|
| 여섯 항목을 해결하는 결정 블록 하나 | §4: ADOPTED 여섯 |
| 유일 라벨, 미지 클래스 거부, 한정 입력 크기 | §§3.1–3.2, 3.5 |
| 상속 우선순위·최대 잉여 유지, 다섯 예시 | §3.4 |
| 동결 스냅샷 하나, 기존 노드 경계 | §3.3 |
| production NOT_AUTHORIZED, 그림자 효과 미적용 | 배너, §3.6 |
| 문서 색인 참조 | **완료(개정 범위 안):** `tests/decision_bindings.json`에 이 노트의 여섯 항목을 등록했다(`PENDING_CONSUMER`, consumer_node `multipayee-shadow-input`, 기존 모듈 앵커). `python3 scripts/decision_bindings.py --check`가 이 노트 없이 보고하던 "ADOPTED entry lacks binding" 여섯 건이 사라졌다. `docs/CAP_COVERAGE.md`의 산문 목록 한 줄은 개정 범위(노트·bindings·vectors/pack)에 없어 §7의 정확한 문구로 supervisor 통합에 넘긴다. 원장은 `docs/decisions/*.md`를 직접 열거하므로 그 줄 없이도 이 노트를 검증한다 |
| 결정 원장 검증 | **실행함(2026-10-22, 이 워크트리):** `python3 scripts/decision_ledger.py`가 이 노트를 `multipayee-shadow-input-decision · PROVISIONAL_PRODUCT_DECISION · ADOPTED 여섯`으로 색인했고 오류 없음. `python3 scripts/decision_bindings.py --check` 통과. `python3 -m unittest tests/test_decision_bindings.py tests/test_coverage.py` 통과. `python3 scripts/docs_surface.py --check` 통과. 결과는 §7 표 참조 |

**차단 소견 처리:** "문서 색인 참조가 PENDING"이라는 소견은 타당했다. 이번 라운드는 개정 범위 안의 색인인 `tests/decision_bindings.json`을 실제로 편집했고 검사기로 확인했다. 범위 밖 파일(`docs/CAP_COVERAGE.md`)은 편집하지 않았으며 편집했다고 주장하지도 않는다.

## 6. Open risks

구체 클래스 어휘와 동률 비교자 바인딩은 구현 소비자가 선행 노트에서 검증해야 하며, 없으면 `NOT_BOUND`다. 잔여 의무는 합성 주장이며 법적 유효성·완전성 증거가 아니다. 법무·세무·회계 해석은 전문가 검토 전 작업 가정이다. 바인딩 행은 `PENDING_CONSUMER`이며 기존 앵커를 가리킬 뿐 구현 주장이 아니다.

## 7. 후속 작업

| 작업 | 담당 | 상태 |
|---|---|---|
| `docs/CAP_COVERAGE.md` 9행의 잠정 결정 목록 끝에 `, [docs/decisions/CAPITAL_MULTIPAYEE_SHADOW.md](decisions/CAPITAL_MULTIPAYEE_SHADOW.md)(multipayee-shadow-input-decision)` 추가 | supervisor 통합(개정 범위 밖) | 미완 |
| `multipayee-shadow-input` 구현: 정책 바인딩, 순열 독립성, 동률, 중복·미지 클래스 거부, 수치·용량 경계, 보존 불변식, 그림자 봉투 유지, 비호환 비교 검증. 새 벡터는 `scripts/docs_surface.py` 등록과 README needle 필요 | 구현 노드 | 미구축 |
| 누적 늦은 현금, 참여, 클레임 슬라이스, UC1–UC4, upstream 변경 | 기존 노드 | 이 노트 밖 |
