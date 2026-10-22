# CAPITAL_MULTIPAYEE_SHADOW — 결정된 클래스 우선 배정을 위한 한정 다중 수취인 입력

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
이 문서는 KIX-CAPITAL 저장소 안의 **시뮬레이션·제품 설계용** 결정이다. 청약이 아니고 실자금이 움직이지 않으며 production은 계속 `NOT_AUTHORIZED`다. 모든 그림자 효과는 `SHADOW_NOT_APPLIED`로 남는다. 영구 정산 기록, UC1–UC4 구현, upstream 계약 변경은 승인하지 않는다. 법무·세무·회계에 닿는 언급은 전문가 검토 전 작업 가정이며 자문이 아니다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `multipayee-shadow-input-decision` (Decision: bounded multi-payee inputs for the decided class-priority allocation) · deps `settlement-policy-decision`, `shadow-policy-decision`, `shadow-refund-resale` · kind `decision` · user_merge `False` |
| 결정자 | **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)** |
| 위임 원문 | 2026-10-08 18:25 KST JunTae Park: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." |
| 결정일 | 2026-10-22 |
| 기준 | KIX-CAPITAL main `5c23989` · kix-protocol `1a69364` (읽기 전용 `/workspace/capital-run/kixproto-ro`) · vendor FSM pin `7481b0e16ce9b903abbffa62249bb91cd9e63cfe` |
| 실행 출처 | 개정 라운드 5는 Fable 5.1(claude-fable-5-1)이 supervisor pack과 검토자 발췌만으로 수행했다. 라운드 6(벡터 고정만, 결정 내용 변경 없음)은 Devin swe-2-high가 수행했다 |
| 읽기 범위 | supervisor pack이 허용한 경로만 읽었다. 선행 노트 `CAPITAL_SETTLEMENT_POLICY.md`(`CAPITAL-ALLOC-V1`)·`CAPITAL_SHADOW_POLICY.md`는 허용 경로 밖이라 **직접 열지 않았다.** 상속 규칙 두 가지는 검토 라운드의 검토자 발췌(2차 정보)로 확인했다: (a) `CAPITAL-ALLOC-V1`은 동률을 **`payee_label` 오름차순**으로 가르고 클래스 표(`PROTECTED_THIRD_PARTY`, `COUNTERPARTY_PROCEEDS`, `ECOSYSTEM_ROYALTY`, `PLATFORM_FEE`)를 구체적으로 정한다; (b) 클래스 내 비례 배분, 클래스당 수취인 복수, 보호 제3자 라인은 **upstream FSM 변경이 필요**하다. 이 노트는 그 값을 재정의하지 않고 로드해 쓴다. 충돌 시 선행 노트가 이기고, 입력 형태·용량·비교 규칙은 이 노트가 이긴다 |
| 상태 어휘 | **ADOPTED** = 위임 범위 안의 잠정 값. **UNDETERMINED** = 값을 정할 수 없어 이유만(`value: null`). 여섯 항목 모두 ADOPTED |
| 개정 | 라운드 5: (1) **동률 규칙 정정.** 이전 판은 "동률 정보가 없으면 `NOT_BOUND`이며 알파벳 순서를 대체로 쓰지 않는다"고 적어 상속 비교자(`payee_label` 오름차순)를 금지하는 모순을 냈다. §3.2·§3.4·§4 `equal_remainders`를 상속 비교자 그대로("ascending `payee_label`")로 고치고, `NOT_BOUND`는 정책을 로드할 수 없는 경우로만 한정했다. 작업 예시의 P1<P2<P3 순서를 그 비교자로 명시했다. (2) **FSM 표현 불가 표시 추가.** §3.4와 §4 `within_class_caps_and_rounding`에 `fsm_expressible: false`를 두고, 고정된 두 수취인 FSM 기준선과 "행 조작 금지" 규칙을 유지했다. (3) 기준을 supervisor 값 main `5c23989`·kix `1a69364`로 맞췄다. 라운드 4: `tests/decision_bindings.json`에 여섯 `PENDING_CONSUMER` 행 추가, 블록에 `status` 추가, 검사 실행. 라운드 6: **`tests/vectors/pack` 코퍼스 재고정(내용 결정 변경 없음).** 그림자 증거 팩의 `decisions` 섹션은 원장 인덱스 행을 바이트로 박제하는데, 커밋된 코퍼스는 이 노트의 원장 행이 생기기 전(main 머지 기점 `02bc3e5`, 15행)에 만들어져 `--check` 드리프트로 CI 단위 테스트 4개(`PackRegenerationTests`)가 실패했다. `scripts/pack_vectors.py --write`로 이 트리 기준 16행(기존 15 + 이 노트 1)을 재고정했다. 본문·블록은 바꾸지 않았고, 팩 행은 블록에서 파싱한 필드만 담으므로 산문 편집은 코퍼스를 오염시키지 않는다 |

## 1. 결정 요약

| item | 결정 (요지) | CAP rows | 소비 노드 / seam |
|---|---|---|---|
| `synthetic_payee_identity` | **ADOPTED.** 유일한 합성 ASCII 라벨, 스냅샷당 수취인 한 행, 법적 신원 아님 | CAP-02, CAP-05 | `multipayee-shadow-input` (입력 어댑터, 미구축) |
| `class_mapping_and_unknowns` | **ADOPTED.** 행마다 명시적 `class_id`; 어휘·우선순위·비교자는 `CAPITAL-ALLOC-V1`에서 로드; 미지 클래스는 전체 거부 | CAP-02, CAP-05 | 정책 로더 `capital/policy.py` 앵커 |
| `single_cut_allocation_inputs` | **ADOPTED.** 동결된 현금 한 값 + 잔여 의무 벡터 한 벌; 이력 조회·누적·영구 효과 없음 | CAP-02, CAP-05 | `policy-simulator`, `shadow-refund-resale` |
| `within_class_caps_and_rounding` | **ADOPTED.** 상속 클래스 우선·최대 잉여·`payee_label` 오름차순 동률 유지; 잔여 의무가 상한; 정확 정수 산술; `fsm_expressible: false` | CAP-02, CAP-05 | 그림자 배정기 `capital/shadow.py` 앵커 |
| `fixture_capacity_bounds` | **ADOPTED.** 최대 64행·32,768바이트·금액 1조 KRW; 위반은 `SIMULATION_CAPACITY` | CAP-08, CAP-20 | 입력 검증 `capital/strict_json.py` 앵커 |
| `shadow_comparison_labels` | **ADOPTED.** `SHADOW_NOT_APPLIED` 봉투 유지; `adapter_outcome` 진단; 호환 스냅샷만 비교 | CAP-09, CAP-20 | 비교 표시 |

## 2. KIX 비전 연결

[CAPITAL_REQUIREMENTS_KO.md](../CAPITAL_REQUIREMENTS_KO.md)는 로컬 개발 권한과 운영 승인을 구분하고 과거 CI·설계 후보를 현재 구현 완료로 옮기지 말라고 하며, vendor FSM 다섯 파일을 `7481b0e`에 바이트 핀한다. [SEAMS.md](../SEAMS.md)는 로컬 게이트 통과가 SEMANTIC_CONFORMANCE나 upstream 채택이 아님을 정한다. 이 입력 계약은 그 경계 안에서 재현 가능한 합성 배정 실험의 입력만 정의하며, 고정 FSM이 표현하지 못하는 부분은 표시만 하고 FSM을 바꾸지 않는다.

[CAPITAL_CLAIM_SLICE_REGISTRY.md](CAPITAL_CLAIM_SLICE_REGISTRY.md)는 슬라이스 유일성·공유 한도·차입기초 보호를 자기 노드에 둔다. 수취인 행은 클레임 슬라이스도 참여 자격도 만들지 않는다. [CAPITAL_ACCOUNTS_TAX_LEGAL.md](CAPITAL_ACCOUNTS_TAX_LEGAL.md)의 전문가 검토 경계를 유지하며 fixture 신원은 법적 수취인 신원이 아니다. [CAPITAL_DEFAULT_RECOVERY.md](CAPITAL_DEFAULT_RECOVERY.md)와 같이 숫자 한도를 선행 노트에서 복사하지 않고 필드명으로만 인용한다. [VALIDATION.md](../VALIDATION.md)의 과거 결과는 이 개정의 통과 증거가 아니며, §5의 결과만 이 개정의 실행 기록이다. upstream 영수증은 주장하지 않는다.

## 3. 항목별 결정

### 3.1 `synthetic_payee_identity`

입력 버전 `CAPITAL-MULTIPAYEE-SHADOW-INPUT-V1`. 행은 정확히 `payee_label`, `class_id`, `shadow_remaining_obligation_krw` 세 필드다. 라벨은 `^fx-[a-z0-9][a-z0-9_-]{0,60}$`(4–64 ASCII 바이트)이며 동일성은 바이트 일치다. 트리밍·정규화·별칭·대소문자 접기 없음.

라벨은 스냅샷 전체(클래스 간, 의무 0 행 포함)에서 유일하다. 중복은 전체 입력을 거부하며 병합하지 않는다. 각 라벨은 정확히 한 클래스에 속한다. 신원은 `(fixture_id, snapshot_id, payee_label)`이고 두 상위 식별자도 같은 문법을 따른다. 스냅샷 간 재사용은 계속되는 채권자 신원을 만들지 않는다.

표시 순서와 상속 동률 비교자는 둘 다 `payee_label` ASCII 바이트 오름차순이다. 라벨이 유일하므로 모든 동률이 결정적으로 풀린다. 입력 배열 순서는 결과에 영향이 없다(순열 독립). 실명·계좌·법적 식별자는 스키마 밖이다.

### 3.2 `class_mapping_and_unknowns`

모든 행에 `class_id`를 요구한다. 클래스 어휘·우선순위·동률 비교자는 채택된 `CAPITAL-ALLOC-V1`에서 로드하며 라벨에서 추론하지 않는다. 상속 어휘는 네 클래스(`PROTECTED_THIRD_PARTY`, `COUNTERPARTY_PROCEEDS`, `ECOSYSTEM_ROYALTY`, `PLATFORM_FEE`)이고 우선순위도 그 노트가 정한다. 이 노트는 그 표를 참조 대상으로만 인용하며 재정의·확장하지 않는다. 구현은 노트에서 로드한 표를 쓰고 리터럴을 코드에 복사하지 않는다.

문법상 유효하지만 미지인 클래스는 전체 입력을 `adapter_outcome: INVALID_INPUT`, 이유 `UNKNOWN_CLASS`로 거부한다. 누락·형식 오류는 `INVALID_CLASS`. 용량 위반은 §3.5. 의무 0 행도 검증한다. 대체 클래스·조용한 생략·부분 배정은 없다.

계산 전 배정 정책·그림자 정책 출처 digest를 동결한다. 필수 정책 노트가 없거나 읽을 수 없거나 블록이 파싱되지 않으면 `adapter_outcome: NOT_BOUND`와 null 금액이다. 로드가 성공하면 어휘·우선순위·비교자는 모두 채택된 값이므로 추가 결정이 필요 없다. `NOT_BOUND`는 로드 실패에만 쓰며, 동률 해소 실패의 결과가 아니다.

### 3.3 `single_cut_allocation_inputs`

입력 객체는 정확히 `schema`(`CAPITAL-MULTIPAYEE-SHADOW-INPUT-V1`), `fixture_id`, `snapshot_id`, `shadow_cash_krw`, `payees`다. 미지 필드와 중복 JSON 키는 거부한다. 입력 에코·결과·비교 델타를 포함한 모든 금액 키는 `shadow_`로 시작한다.

금액은 음이 아닌 JSON 정수다. 불리언·문자열·분수·지수 표기는 거부한다. 잔여 의무는 이 계산 직전의 fixture 작성자 가정이며 검증된 채무 증거가 아니다. 액면·과거 지급·수수료·환불·이전 그림자 결과에서 유도하지 않는다.

페이로드와 정책 출처를 한 번 동결한다. 클래스 사이나 비교 실행 사이에 가변 상태를 다시 읽지 않는다. 식별자만으로 입력 동등성을 주장하지 않는다.

성공 결과는 행별 `payee_label`, `class_id`, `shadow_allocation_krw`, `shadow_remaining_after_krw`와 합계 `shadow_total_allocated_krw`, `shadow_unallocated_cash_krw`다. 의무 0 행도 보인다. 빈 배열은 유효하며 전액 미배정이다.

이력 조회·정산 쓰기·재생 원장·자동 이월은 없다. 재계산은 가설 계산의 반복이다. 누적 늦은 현금, 참여, 클레임 슬라이스, 환불·리셀 수명주기 효과는 기존 노드에 남는다.

### 3.4 `within_class_caps_and_rounding`

`CAPITAL-ALLOC-V1`의 클래스 우선순위, 최대 잉여 규칙, 동률 비교자를 유지한다. 금융 비율·수수료·권리·인수 한도는 새로 두지 않는다.

상속 우선순위 순서로 클래스를 처리한다. 클래스마다 남은 현금 `C`, 의무 `r_i`, 합 `R`, 클래스 예산 `B = min(C, R)`. `R = 0`이면 나눗셈 없이 0 배정. 그 외:

- 기본: `q_i = floor(B × r_i / R)`
- 잉여 분자: `m_i = (B × r_i) mod R`
- `B − Σq_i` 단위를 `m_i` 내림차순으로 배분하고, 같은 잉여는 상속 비교자 **`payee_label` 오름차순(ASCII 바이트)** 으로 가른다.

라벨은 유일하므로(§3.1) 비교자는 항상 전순서를 주고 동률은 남지 않는다. 입력 배열 순서는 어떤 단계에서도 쓰지 않는다.

**FSM 표현 가능성: `fsm_expressible: false`.** 고정 vendor FSM(`7481b0e`)은 두 수취인 기준선만 표현한다. 선행 정산 노트가 정한 대로 클래스 내 비례 배분, 클래스당 수취인 복수, 보호 제3자 라인은 upstream FSM 변경이 필요하다. 이 노트의 계산은 그 변경을 요청하거나 대신하지 않는다. 결과는 FSM 명령·전이·행을 만들지 않는 그림자 산술이며, 고정 두 수취인 기준선을 늘리려고 행을 조작하거나 fabricated row를 만드는 것은 금지한다. 다중 수취인 결과를 FSM 행으로 번역하는 일은 upstream 수용 후의 별도 노드다.

전 과정 정확 정수 산술. 배정은 잔여 의무를 넘지 않는다. 하위 클래스는 상위 잔여 의무가 충족된 뒤에만 현금을 받는다. 잉여는 미배정으로 남는다. 불변식: `0 ≤ a_i ≤ r_i`, `remaining_after_i = r_i − a_i`, `Σa_i + unallocated = cash` (수학 기호이며 출력 키가 아니다).

**작업 예시.** 합성 KRW 정수. `P`는 상속 보호 클래스(`PROTECTED_THIRD_PARTY`), `L`은 그 아래 상속 클래스. P1–P3, L1은 라벨 `fx-p1`, `fx-p2`, `fx-p3`, `fx-l1`의 표 별칭이며, 동률은 상속 비교자대로 `fx-p1 < fx-p2 < fx-p3` 순이다.

| 사례 | 잔여 의무 | 현금 | 배정 | 배정 후 잔여 | 미배정 |
|---|---|---:|---|---|---:|
| 보호 클래스 안에서 현금 소진 | P1=5, P2=3; L1=9 | 5 | P1=3, P2=2, L1=0 | P1=2, P2=1, L1=9 | 0 |
| 같은 잉여 동률 | P1=1, P2=1, P3=1 | 2 | P1=1, P2=1, P3=0 | P1=0, P2=0, P3=1 | 0 |
| 현금 0 | P1=5, P2=3 | 0 | P1=0, P2=0 | P1=5, P2=3 | 0 |
| 의무 전부 충족 | P1=0, P2=0 | 7 | P1=0, P2=0 | P1=0, P2=0 | 7 |
| 현금이 의무 초과 | P1=2, P2=1; L1=4 | 10 | P1=2, P2=1, L1=4 | P1=0, P2=0, L1=0 | 3 |

첫 사례: 기본 3과 1, 잉여 분자 1과 7이므로 P2가 추가 단위를 받는다. 동률 사례: 기본 모두 0, 잉여 분자 모두 2이므로 `payee_label` 오름차순 상위 둘(`fx-p1`, `fx-p2`)이 1씩 받는다. 예시는 산술 기대치이며 실행된 fixture가 아니다.

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
| `NOT_BOUND` | `SHADOW_NOT_APPLIED` | null; 정책 로드 실패 |

실패한 계산은 결코 0 배정 성공으로 보이지 않는다.

비교 메타데이터는 `comparison_state: COMPARABLE | NOT_COMPARABLE`다. 수치 비교는 동일한 동결 현금·라벨 집합·클래스 멤버십·잔여 의무·KRW 단위를 가진 두 `COMPUTED` 결과를 요구하며 양쪽의 알고리즘/정책 신원과 출처 digest를 기록한다. 의도적으로 다른 정책의 비교는 허용되고 차이는 오류도 금융적 우월도 아니다. 후보 − 기준선을 `shadow_allocation_delta_krw`, `shadow_remaining_after_delta_krw`, `shadow_total_allocated_delta_krw`, `shadow_unallocated_cash_delta_krw`로 보고한다. 그 외는 `NOT_COMPARABLE`, 이유, null 델타다. 고정된 두 수취인 FSM 기준선을 늘리기 위한 행 조작은 금지한다. 동등성은 이 스냅샷에만 적용되며 집행된 정산이나 upstream 적합성을 증명하지 않는다.

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
        "input_order_significant": false,
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
        "comparator_source": "CAPITAL-ALLOC-V1",
        "unknown_class": "REJECT_WHOLE_INPUT",
        "default_class": null,
        "missing_policy_adapter_outcome": "NOT_BOUND",
        "not_bound_scope": "POLICY_LOAD_FAILURE_ONLY",
        "source_binding": "FREEZE_LOADED_POLICY_DIGESTS"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-02", "CAP-05"],
      "rationale": "Apply inherited adopted classes and comparator without fallback or invented financial priorities.",
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
        "equal_remainders": "INHERIT_ASCENDING_PAYEE_LABEL",
        "payee_cap": "REMAINING_OBLIGATION",
        "arithmetic": "EXACT_INTEGER",
        "surplus_output": "shadow_unallocated_cash_krw",
        "fsm_expressible": false,
        "fsm_baseline": "PINNED_TWO_PAYEE_7481b0e",
        "fabricated_fsm_rows": "FORBIDDEN"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-02", "CAP-05"],
      "rationale": "Preserve class priority, rounding and the inherited label comparator while preventing overpayment; the pinned FSM cannot express multi-payee classes.",
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
| 상속 우선순위·최대 잉여·동률 비교자 유지, 다섯 예시 | §3.4 (동률 예시는 `payee_label` 오름차순으로 명시) |
| 동결 스냅샷 하나, 기존 노드 경계 | §3.3 |
| production NOT_AUTHORIZED, 그림자 효과 미적용 | 배너, §3.6 |
| 문서 색인 참조 | `tests/decision_bindings.json`에 여섯 항목의 `PENDING_CONSUMER` 행(라운드 4, 이 라운드에서 변경 없음). `docs/CAP_COVERAGE.md` 한 줄은 개정 범위 밖이라 §7로 넘긴다 |
| 결정 원장 검증 | 라운드 6에서 이 워크트리에서 실행: `python3 scripts/decision_ledger.py`, `python3 scripts/decision_bindings.py --check`, `python3 scripts/pack_vectors.py --check`, `python3 -m unittest tests/test_decision_bindings.py tests/test_evidence_pack.py`. 결과는 최종 메시지에 기록 |

**차단 소견 처리:** (1) 동률 규칙: 수용. 상속 비교자를 금지하던 문장을 제거하고 `payee_label` 오름차순을 상속 규칙으로 명시했다. (2) FSM 표현 불가: 수용. `fsm_expressible: false`, 고정 두 수취인 기준선, fabricated row 금지를 §3.4와 §4에 추가했다.

## 6. Open risks

선행 노트의 비교자·클래스 표는 검토자 발췌(2차 정보)로 확인했고 이 결정자가 원문을 열지 않았다. 구현 소비자는 선행 노트에서 직접 로드해 검증해야 하며, 발췌와 원문이 다르면 원문이 이긴다. 잔여 의무는 합성 주장이며 법적 유효성·완전성 증거가 아니다. 법무·세무·회계 해석은 전문가 검토 전 작업 가정이다. 바인딩 행은 `PENDING_CONSUMER`이며 구현 주장이 아니다. 다중 수취인 결과의 FSM 반영은 upstream 변경 전까지 불가능하다.

## 7. 후속 작업

| 작업 | 담당 | 상태 |
|---|---|---|
| `docs/CAP_COVERAGE.md` 9행의 잠정 결정 목록 끝에 `, [docs/decisions/CAPITAL_MULTIPAYEE_SHADOW.md](decisions/CAPITAL_MULTIPAYEE_SHADOW.md)(multipayee-shadow-input-decision)` 추가 | supervisor 통합(개정 범위 밖) | 미완 |
| `multipayee-shadow-input` 구현: 정책 로드·digest 동결, 순열 독립성, `payee_label` 오름차순 동률, 중복·미지 클래스 거부, 수치·용량 경계, 보존 불변식, 그림자 봉투 유지, 비호환 비교 검증. 새 벡터는 `scripts/docs_surface.py` 등록과 README needle 필요 | 구현 노드 | 미구축 |
| 다중 수취인 결과의 FSM 행 번역 | upstream FSM 변경 후 별도 노드 | 이 노트 밖 |
| 누적 늦은 현금, 참여, 클레임 슬라이스, UC1–UC4, upstream 변경 | 기존 노드 | 이 노트 밖 |
