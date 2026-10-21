# Capital 이자 면제·미적용 현금 해제·종결 게이트 재검토 결정

> **PROVISIONAL PRODUCT DECISION**
>
> 결정자 표기(위임 메타데이터): **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**
>
> 결정일: **2026-10-22** · KIX-CAPITAL main **`cde0bc7`** · kix-protocol **`93cec6a`**. Supervisor 제공 기준이며 Git 재검증이나 지정 모델 실행을 주장하지 않는다.
>
> **시뮬레이션·제품 설계 전용**이다. 실자금·청약·외부 지급·법적 채무 소멸을 승인하지 않는다. **`funds_executed:false`**, production **`NOT_AUTHORIZED`**를 유지한다. 회계·세무·법무는 **`WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW`**다. 소비 구현은 별도 노드이며 upstream 채택·완료·SEMANTIC_CONFORMANCE를 주장하지 않는다.

## 1. 결정 요약

| item | 결정 | CAP rows | consumer |
|---|---|---|---|
| `waiver_command_existence` | ADOPTED — 명시적 `waive_interest`; 상각 후에도 가능 | CAP-01, CAP-04 | waiver overlay |
| `waiver_scope_interest_only_vs_principal` | ADOPTED — 미납 약정·연체이자만 면제. 상각 후 보조 귀속과 잔여 회수 한도 동시 차감 | CAP-01, CAP-04 | 이자·회수 투영 |
| `waiver_authority_and_two_person_threshold` | ADOPTED — 운영자·별도 검토자, 임계 초과 시 별도 금융책임자 추가 | CAP-04, CAP-09 | 승인 검증 |
| `waiver_caps_and_sim_day_recording` | ADOPTED — 적격 이자 100% 이내, 누적 예산, 현재 논리 일 | CAP-01, CAP-04 | cap·재생 |
| `unapplied_cash_release_or_refund` | ADOPTED — 대사된 원천 lot의 시뮬레이션 반환 | CAP-02, CAP-05 | 보관액 해제 |
| `close_gate_reconsideration` | ADOPTED — 유효 면제로 순이자 0 가능. 다른 차단 유지 | CAP-01, CAP-04, CAP-20 | advisory close |
| `overlay_entry_schema_and_digest_effect` | ADOPTED — append-only·원자성·멱등성, 보조 귀속도 digest에 결속 | CAP-13, CAP-14, CAP-15 | 저장·export |
| `tax_and_accounting_working_assumption` | ADOPTED — 면제·회수·상각 분리. 전문 판단은 미정 | CAP-04, CAP-20 | 회계 설명·투영 |
| `agent_lane_proposal_kinds` | ADOPTED — 세 종류 제안만 허용. 승인·게시·지급 금지 | CAP-09, CAP-20 | agent proposal lane |

CAP 매핑은 제공된 선행 노트의 사용례를 따른다. CAP 정본 전체를 확인했다는 뜻은 아니다.

## 2. KIX 비전 연결

- `docs/CAPITAL_REQUIREMENTS_KO.md`: 원 요청·관측·금전 의무·실행을 분리한다. 면제는 현금 회수가 아닌 독립된 오버레이 사건이다.
- `docs/SEAMS.md`: 로컬 정책 채택은 upstream 계약 채택이 아니다. 포트의 `NOT_BOUND`를 해제하지 않는다.
- `docs/VALIDATION.md`: 로컬 검증에서 은행 exactly-once·분산 내구성·법적 적합성을 추론하지 않는다.
- `docs/decisions/CAPITAL_DEFAULT_RECOVERY.md`: 가속 재기준·부도 명령일 기준 상각을 유지한다. 리뷰에 제공된 §98 및 JSON §260–261의 **상각 후 단일 잔여채권 회수·무배분** 규칙을 유지하면서, 면제 적격성에만 사용하는 보조 귀속을 추가한다.
- `docs/decisions/CAPITAL_CLAIM_SLICE_REGISTRY.md`: 한도 숫자를 복사하지 않고 `CAPITAL-TERMS-V1` 필드를 참조한다. 면제로 원금 한도나 차입기초를 복원하지 않는다.
- `docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md`: 합성 차트에서 회계·세무 입장을 추론하지 않는다.

근거는 supervisor pack과 리뷰 발췌뿐이다. `CAPITAL_REPAYMENT_POSTING.md`, `CAPITAL_FINANCIAL_TERMS.md`는 선행 정본이지만 허용된 본문이 없어 직접 읽지 않았다. 기존 숫자·정확한 바인딩은 해당 정본이 우선하고, 이번 면제 적격성·잔여 회수 한도 조정은 본 결정의 명시적 추가 정책이다. 바인딩 부족은 해당 소비 경로를 `NOT_BOUND`로 만들며 채택된 정책 자체를 `DECISION_REQUIRED`로 되돌리지 않는다.

## 3. 항목별 결정

### 3.1 `waiver_command_existence`

**`waive_interest`를 신설한다.** 정상·연체·부도·회계상 상각 이후의 열린 선지급에 적용한다. 약정이자·연체이자 금액을 각각 지정하고 합계는 양의 KRW 정수여야 한다. 각 금액은 0 이상이며 잔액 초과·소수·음수는 거절한다.

명시적 사유·기준 digest·승인 증거가 필수다. 자동 면제, 과거 영수증 수정, 종결 기록에 대한 게시, V1 면제 취소는 금지한다. 성공은 시뮬레이션 이자청구 감소만 의미한다.

### 3.2 `waiver_scope_interest_only_vs_principal`

대상은 현재 `sim_day`까지 발생·확정된 미납 약정이자와 연체이자다. 원금·수수료·미래이자·제3자 보호채무·반환 의무는 제외한다.

**상각 전:** 버킷별 적격 잔액은 확정 발생액에서 해당 버킷에 실제 확정 배분된 상환·회수액과 이전 유효 면제를 한 번씩 차감한다. 상각 자체는 면제가 아니다.

**상각 후:** 실제 회수는 선행 결정대로 **단일 잔여채권에 무배분**으로 기록한다. 그 기록과 별도로 `POST_WRITEOFF_WAIVER_ATTRIBUTION_V1` 보조 계산을 채택한다. 이것은 면제 적격성·잔여청구 대사용이며 실제 상환 배분, 회계 계정 배분 또는 원금 상환 증거가 아니다.

상각 사건 직후의 정본 잔여채권을 다음과 같이 초기화한다.

- `C`: 잔여채권에 포함된 미납 약정이자. 상각 전 유효 면제·확정 배분을 이미 차감한다.
- `D`: 같은 방식으로 산정한 미납 연체이자.
- `O`: 원금 등 나머지 잔여채권으로 `R − C − D`.
- `R`: 단일 잔여 회수 한도. 항상 `R = C + D + O`, 모든 값은 0 이상이다.

회계상 장부가액 0을 `R=0`으로 읽지 않는다. 원본 상각 시점의 구성과 정본 잔여채권이 대사되지 않으면 추측하거나 음수를 0으로 보정하지 않고 해당 경로를 `NOT_BOUND`로 거절한다.

확정된 상각 후 회수액 `x`마다 **연체이자 → 약정이자 → 기타 잔여채권** 순서로 보조 귀속한다.

`aD = min(x, D)`  
`aC = min(x − aD, C)`  
`aO = x − aD − aC`

`0 < x ≤ R`를 먼저 검증한 뒤 `(D,C,O,R)`를 각각 `(D−aD,C−aC,O−aO,R−x)`로 갱신한다. 실제 회수 엔트리는 여전히 단일 금액이다. 보조 귀속을 다시 실제 배분액으로 차감하면 안 된다.

면제액 `(wC,wD)`는 `0≤wC≤C`, `0≤wD≤D`, 합계 양수를 만족해야 한다. 성공 시 **같은 원자 단위에서** `C-=wC`, `D-=wD`, `R-=wC+wD`; `O`는 유지한다. 이후 모든 회수 제안·게시·예약은 감소한 `R`을 사용한다. 기존 승인·견적은 상태 변경으로 무효화한다. 그 결과 이미 회수에 귀속된 이자는 면제할 수 없고, 면제된 이자는 다시 회수할 수 없다.

이 계산은 최초 상각 snapshot부터 확정 append 순서로 재생한다. 같은 날도 커밋 순서를 따르며 날짜·operation ID로 재정렬하지 않는다. 과거 무배분 회수도 원본 영수증을 수정하지 않고 같은 규칙으로 재생한다. 유효 면제는 해당 위치에서 정확히 한 번 반영한다. 순서·구성 누락, 초과 회수 또는 불변식 위반은 `NOT_BOUND`와 대사 차단 사유다.

기존 정책이 상각 후 추가 발생을 허용하고 정본 잔여채권에 포함하는 경우에만 확정 증가분을 해당 버킷과 `R`에 함께 더한다. 본 결정은 새로운 발생 권한을 만들지 않는다.

예: `C=80,D=20,O=1000,R=1100`에서 회수 50은 보조적으로 `D=20,C=30`에 귀속되어 `C=50,D=0,R=1050`이다. 약정이자 60 면제는 거절한다. 40 면제는 `C=10,R=1010`을 만든다. 이후 회수 1015는 한도 초과로 거절한다. 이 숫자는 검증 예시이며 금융 조건이 아니다.

### 3.3 `waiver_authority_and_two_person_threshold`

모든 면제는 `SIM_OPERATOR` 제안과 별도 주체 `SIM_FINANCE_REVIEWER` 승인을 요구한다. 동일 주체의 역할 변경은 분리 승인으로 인정하지 않는다.

동일 수익자의 당일 누적 면제액에 제안액을 더한 값이 `CAPITAL-TERMS-V1.underwriting_depth.two_person_threshold_krw`를 **초과**하면 두 주체와 다른 `SIM_FINANCE_OWNER`를 추가한다. 분할해도 누적 계산한다.

승인은 대상·버킷별 금액·사유·현재 일·상태 및 정책 digest에 결속한다. 회수·발생·면제로 상태가 바뀌면 재승인한다. 합성 역할은 실제 인증이나 은행 권한이 아니다.

### 3.4 `waiver_caps_and_sim_day_recording`

버킷별 적격 잔액의 100%까지 허용하되 별도 누적 면제 예산을 적용한다. 선지급·수익자·포트폴리오 예산은 각각 `underwriting_depth.single_advance_cap_krw`, `beneficiary_aggregate_cap_krw`, `portfolio_cap_krw`를 참조한다.

기존 인출 cap의 의미는 바꾸지 않는다. 누적 면제액은 전체 보존 이력 기준이며 종결·일자 변경·상각·회수로 리셋하지 않는다. 수익자 귀속은 선지급 발생 당시 바인딩을 유지한다.

`effective_sim_day`는 게시 시점의 현재 논리 일이다. 소급·미래일·이율·가속일 재작성은 거절한다. 참조값·발생액·상각 후 대사가 불명확하면 `NOT_BOUND`다.

### 3.5 `unapplied_cash_release_or_refund`

**`release_unapplied_cash`를 신설한다.** 확정 원천 영수증과 연결되어 대사된 보관 lot의 가용 잔액에 대해 부분 시뮬레이션 반환을 허용한다. 수취 귀속은 동일 합성 원송금자로 제한한다.

귀속 불명·분쟁·반환 제한·보호채무·UNKNOWN·진행 중 예약이 있으면 해제하지 않는다. 같은 범위에서 확정 상환 배분이 가능하면 기존 repayment-posting 대사를 먼저 수행한다. 면제로 반환액을 자동 생성하지 않는다.

운영자와 별도 검토자가 승인한다. 원송금자의 당일 누적 해제액이 기존 2인 임계값을 초과하면 별도 금융책임자를 추가한다. 보관액 감소와 `SIMULATED_RELEASE`를 원자적으로 기록하며 `funds_executed=false`다. 실제 환불 API·은행 연결·지급 완료 표시는 허용하지 않는다.

### 3.6 `close_gate_reconsideration`

**`CAPITAL_REPAYMENT_POSTING`의 close-gate 규칙은 이 결정을 통해서만 재검토할 수 있다.** 이번 변경은 이자 조건에 한정한다. 상각 전에는 발생액에서 확정 배분·유효 면제를 차감하고, 상각 후에는 §3.2의 재생된 `C+D=0`을 사용한다. 보조 귀속을 실제 배분과 중복 차감하지 않는다.

원금 잔액·기타 채무·열린 환불 및 분쟁·보관액·UNKNOWN·미완료 승인과 예약 등 기존 차단을 모두 유지한다. 상각 후 대사 실패도 통과를 차단한다. `R=0`이나 보조 `O` 감소만으로 원금 상환·종결을 추론하지 않는다.

해제로 보관액이 0이면 그 조건만 충족한다. 결과는 `ADVISORY_ONLY`이며 pinned FSM 종결이나 실제 채무 소멸을 실행하지 않는다. 상태가 바뀌면 이전 평가를 무효화한다.

### 3.7 `overlay_entry_schema_and_digest_effect`

엔트리는 `overlay_id/kind/payload`이며 새 kind는 `INTEREST_WAIVER`, `UNAPPLIED_CASH_RELEASE`다. payload에는 operation·현재 일·대상·금액·사유·근거·승인·기준 상태 digest·정책 참조와 digest·`funds_executed:false`를 포함한다.

상각 후 면제는 상각 snapshot 참조, 보조 규칙 버전, 사건 순서 기준, `C/D/O/R` 전후값을 결속한다. 회수 원본과 보조 귀속은 구별하며 보조 이력을 별도 현금 사건으로 합산하지 않는다.

검증·승인·누적 cap·잔여 한도·예약 충돌 확인과 게시를 원자적으로 처리한다. 동시 회수·면제는 하나만 같은 기준 digest에서 성공한다. 동일 operation·내용은 최초 결과, 다른 내용은 충돌이다. 응답 유실은 조회로 복구한다.

효과 엔트리·정책 digest·재생 가능한 보조 근거는 overlay digest와 export에 포함한다. 벽시계·프로세스 ID는 제외한다. pinned FSM digest·기존 golden은 변경하지 않는다.

### 3.8 `tax_and_accounting_working_assumption`

면제는 비현금 이자청구 감소이며 회수·회계상 상각과 분리한다. 총발생·실제 배분·면제·상각 후 보조 귀속·순잔액을 구별하고 상각 후 면제로 손실을 이중 인식하지 않는다. 보조 귀속 순서를 수익 인식 순서로 사용하지 않는다.

보관액은 보관 의무이며 해제는 수익이나 회수가 아니다. 계정 코드·분개·세무 처리와 인정일·법적 면제 효력은 `UNDETERMINED`, `value:null`이며 회계·세무·법무 전문 검토를 각각 target으로 둔다. 합성 차트와 기존 합계는 유지한다.

### 3.9 `agent_lane_proposal_kinds`

`PROPOSE_INTEREST_WAIVER`, `PROPOSE_UNAPPLIED_CASH_RELEASE`, `REQUEST_ADVISORY_CLOSE_REVIEW`를 채택한다. 에이전트는 제한된 대상과 상태·정책 digest에 결속된 초안·계산 근거만 제출한다.

승인자 수에 포함되지 않으며 게시·지급·자동 종결 권한이 없다. stale 제안은 재계산한다. upstream AI 위임 계약의 채택을 주장하지 않는다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "waiver-writeoff-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-10-22",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "scope": "SIMULATION_PRODUCT_POLICY_ONLY",
  "funds_executed": false,
  "production": "NOT_AUTHORIZED",
  "entries": {
    "waiver_command_existence": {
      "status": "ADOPTED",
      "value": {
        "command": "waive_interest",
        "post_writeoff_allowed": true,
        "closed_record_posting": false,
        "automatic_waiver": false,
        "historical_receipt_mutation": false,
        "amounts": "NONNEGATIVE_INTEGER_KRW_BUCKETS_WITH_POSITIVE_SUM"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Explicit noncash relief with immutable evidence.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "waiver_scope_interest_only_vs_principal": {
      "status": "ADOPTED",
      "value": {
        "included": ["ACCRUED_UNPAID_CONTRACT_INTEREST", "ACCRUED_UNPAID_OVERDUE_INTEREST"],
        "excluded": ["PRINCIPAL", "FEES", "FUTURE_INTEREST", "THIRD_PARTY_OBLIGATIONS", "RETURN_OBLIGATIONS"],
        "explicit_bucket_amounts": true,
        "pre_writeoff_balance": "ACCRUAL_MINUS_ACTUAL_CONFIRMED_BUCKET_ALLOCATIONS_MINUS_VALID_WAIVERS",
        "post_writeoff": {
          "rule": "POST_WRITEOFF_WAIVER_ATTRIBUTION_V1",
          "actual_recovery": "SINGLE_RESIDUAL_CLAIM_WITHOUT_ALLOCATION",
          "purpose": "WAIVER_ELIGIBILITY_AND_RESIDUAL_RECONCILIATION_ONLY",
          "initialization": {
            "C": "UNPAID_CONTRACT_INTEREST_INCLUDED_IN_WRITEOFF_RESIDUAL_NET_OF_PRIOR_ALLOCATIONS_AND_WAIVERS",
            "D": "UNPAID_OVERDUE_INTEREST_INCLUDED_IN_WRITEOFF_RESIDUAL_NET_OF_PRIOR_ALLOCATIONS_AND_WAIVERS",
            "R": "AUTHORITATIVE_RESIDUAL_RECOVERY_CAP_NOT_BOOK_VALUE",
            "O": "R-C-D"
          },
          "invariant": "R=C+D+O; ALL_NONNEGATIVE",
          "replay": "FROM_ORIGINAL_WRITEOFF_SNAPSHOT_IN_CONFIRMED_APPEND_ORDER_INCLUDING_SAME_DAY_EVENTS",
          "historical_recoveries": "REPLAY_WITHOUT_MUTATING_ORIGINAL_RECEIPTS",
          "recovery_precondition": "0<x<=R",
          "memo_order": ["OVERDUE_INTEREST", "CONTRACT_INTEREST", "OTHER_RESIDUAL"],
          "recovery_formula": ["aD=min(x,D)", "aC=min(x-aD,C)", "aO=x-aD-aC"],
          "recovery_effect": ["D'=D-aD", "C'=C-aC", "O'=O-aO", "R'=R-x"],
          "waiver_precondition": "0<=wC<=C; 0<=wD<=D; wC+wD>0",
          "waiver_atomic_effect": ["C'=C-wC", "D'=D-wD", "O'=O", "R'=R-wC-wD"],
          "all_future_recovery_paths": "USE_WAIVER_ADJUSTED_R_IN_QUOTES_RESERVATIONS_AND_POSTING",
          "new_accrual": "ONLY_IF_EXISTING_POLICY_AUTHORIZES_AND_INCLUDES_IT_IN_RESIDUAL; INCREASE_MATCHING_BUCKET_AND_R_ATOMICALLY",
          "missing_or_inconsistent_history": "NOT_BOUND_REJECT_AND_BLOCK_CLOSE",
          "memo_is_actual_payment_allocation": false,
          "memo_is_accounting_allocation": false,
          "memo_proves_principal_payment": false,
          "duplicate_subtraction": false
        },
        "future_accrual": "UNCHANGED_EXISTING_TERMS",
        "writeoff_is_waiver": false,
        "principal_capacity_release": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Deterministic memo attribution prevents waiving recovered interest; atomic residual reduction prevents collecting waived interest.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "waiver_authority_and_two_person_threshold": {
      "status": "ADOPTED",
      "value": {
        "proposer": "SIM_OPERATOR",
        "reviewer": "DISTINCT_SIM_FINANCE_REVIEWER",
        "threshold_ref": "CAPITAL-TERMS-V1.underwriting_depth.two_person_threshold_krw",
        "threshold_basis": "BENEFICIARY_SIM_DAY_WAIVERS_INCLUDING_PROPOSAL",
        "threshold_comparison": "GREATER_THAN",
        "above_threshold": "ADDITIONAL_DISTINCT_SIM_FINANCE_OWNER",
        "approval_binding": ["TARGET", "BUCKET_AMOUNTS", "REASON", "STATE_DIGEST", "POLICY_DIGEST", "SIM_DAY"],
        "state_change": "REAPPROVE",
        "agent_approval": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-04", "CAP-09"],
      "rationale": "Distinct actors and cumulative thresholds prevent self-approval and splitting.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "waiver_caps_and_sim_day_recording": {
      "status": "ADOPTED",
      "value": {
        "eligible_interest_cap_bps": 10000,
        "advance_lifetime_cap_ref": "CAPITAL-TERMS-V1.underwriting_depth.single_advance_cap_krw",
        "beneficiary_lifetime_cap_ref": "CAPITAL-TERMS-V1.underwriting_depth.beneficiary_aggregate_cap_krw",
        "portfolio_lifetime_cap_ref": "CAPITAL-TERMS-V1.underwriting_depth.portfolio_cap_krw",
        "budget": "SEPARATE_CUMULATIVE_WAIVER_BUDGET_NO_RESET",
        "beneficiary_binding": "AT_ADVANCE_ORIGINATION",
        "effective_day": "CURRENT_SIM_DAY_ONLY",
        "missing_reference": "NOT_BOUND_REJECT"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Bound cumulative relief without copying financial cap literals.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "unapplied_cash_release_or_refund": {
      "status": "ADOPTED",
      "value": {
        "command": "release_unapplied_cash",
        "result": "SIMULATED_RELEASE",
        "recipient": "ORIGINAL_SYNTHETIC_REMITTER_ONLY",
        "partial_release": true,
        "cap": "SOURCE_LOT_AVAILABLE_RECONCILED_BALANCE",
        "priority": "EXISTING_CONFIRMED_REPAYMENT_ALLOCATION_FIRST",
        "blockers": ["UNKNOWN", "DISPUTE", "UNRESOLVED_OWNERSHIP", "PROTECTED_OBLIGATION", "RETURN_RESTRICTION", "PENDING_RESERVATION"],
        "approval": "DISTINCT_OPERATOR_AND_REVIEWER",
        "additional_owner_threshold_ref": "CAPITAL-TERMS-V1.underwriting_depth.two_person_threshold_krw",
        "threshold_basis": "ORIGINAL_REMITTER_SIM_DAY_RELEASES_INCLUDING_PROPOSAL",
        "threshold_comparison": "GREATER_THAN",
        "above_threshold": "ADDITIONAL_DISTINCT_SIM_FINANCE_OWNER",
        "waiver_automatically_creates_refund": false,
        "funds_executed": false,
        "external_refund": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-02", "CAP-05"],
      "rationale": "Release reconciled custody balances through an auditable simulation.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "close_gate_reconsideration": {
      "status": "ADOPTED",
      "value": {
        "repayment_posting_reconsideration_route": "THIS_DECISION_ONLY",
        "pre_writeoff_interest_condition": "ACCRUAL_MINUS_ACTUAL_CONFIRMED_ALLOCATIONS_MINUS_VALID_WAIVERS_EQUALS_ZERO",
        "post_writeoff_interest_condition": "REPLAYED_C_PLUS_D_EQUALS_ZERO_UNDER_POST_WRITEOFF_WAIVER_ATTRIBUTION_V1",
        "other_existing_blockers": "PRESERVE_ALL",
        "minimum_blockers": ["PRINCIPAL_OUTSTANDING", "OTHER_OBLIGATIONS", "OPEN_REFUND_OR_DISPUTE", "HELD_UNAPPLIED_CASH", "UNKNOWN", "PENDING_APPROVAL_OR_RESERVATION", "RESIDUAL_RECONCILIATION_FAILURE"],
        "writeoff_counts_as_principal_payment": false,
        "zero_residual_or_memo_other_reduction_proves_principal_payment": false,
        "scope": "ADVISORY_ONLY",
        "automatic_close": false,
        "state_change": "INVALIDATE_PRIOR_EVALUATION"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-01", "CAP-04", "CAP-20"],
      "rationale": "Net interest can be resolved by valid waivers while preserving all other close requirements.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "overlay_entry_schema_and_digest_effect": {
      "status": "ADOPTED",
      "value": {
        "envelope": ["overlay_id", "kind", "payload"],
        "kinds": ["INTEREST_WAIVER", "UNAPPLIED_CASH_RELEASE"],
        "common_payload": ["schema_version", "operation_id", "effective_sim_day", "expected_overlay_digest", "target_ids", "amounts_krw", "reason_code", "evidence_refs", "proposer_id", "approver_ids", "approval_binding", "policy_refs", "policy_digest", "funds_executed"],
        "post_writeoff_evidence": ["writeoff_snapshot_ref", "attribution_rule_version", "confirmed_event_order_ref", "balances_C_D_O_R_before", "balances_C_D_O_R_after"],
        "posting": "ATOMIC_BALANCE_CAP_APPROVAL_DIGEST_RESERVATION_VALIDATION_AND_APPEND",
        "concurrent_recovery_and_waiver": "SERIALIZE_WITH_EXPECTED_DIGEST_AND_RECHECK_ADJUSTED_RESIDUAL",
        "same_operation_same_content": "IMMUTABLE_FIRST_RESULT",
        "same_operation_different_content": "CONFLICT",
        "lost_response": "LOOKUP_ONLY_UNTIL_RESOLVED",
        "digest_effect": "INCLUDE_EFFECT_ENTRIES_POLICY_DIGEST_AND_REPLAYABLE_ATTRIBUTION_EVIDENCE_IN_OVERLAY_AND_EXPORT",
        "exclude_from_digest": ["WALL_CLOCK", "PROCESS_ID"],
        "pinned_fsm_digest": "UNCHANGED",
        "existing_goldens": "UNCHANGED",
        "reversal_command_v1": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-13", "CAP-14", "CAP-15"],
      "rationale": "Atomic replayable effects prevent duplicate relief and competing recovery against stale balances.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "tax_and_accounting_working_assumption": {
      "status": "ADOPTED",
      "value": {
        "professional_basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
        "waiver": "SEPARATE_NONCASH_INTEREST_CLAIM_REDUCTION",
        "projection": "SEPARATE_ACCRUAL_ACTUAL_ALLOCATION_WAIVER_MEMO_ATTRIBUTION_AND_NET",
        "memo_order_determines_revenue_recognition": false,
        "writeoff_double_loss": "PROHIBITED",
        "held_cash": "CUSTODIAL_OBLIGATION_NOT_REVENUE",
        "release": "NOT_REVENUE_OR_RECOVERY",
        "existing_synthetic_chart": "UNCHANGED",
        "professional_determinations": {
          "account_codes_and_posting": {
            "status": "UNDETERMINED",
            "value": null,
            "target": "ACCOUNTS_PROFESSIONAL_REVIEW",
            "reason": "Reviewed waiver and post-writeoff account mappings are not supplied."
          },
          "tax_treatment_and_dates": {
            "status": "UNDETERMINED",
            "value": null,
            "target": "TAX_PROFESSIONAL_REVIEW",
            "reason": "Reviewed deductibility, VAT, withholding and recognition dates are not supplied."
          },
          "legal_discharge_effect": {
            "status": "UNDETERMINED",
            "value": null,
            "target": "LEGAL_PROFESSIONAL_REVIEW",
            "reason": "Simulation policy does not establish enforceable discharge."
          }
        }
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-04", "CAP-20"],
      "rationale": "Separate product events without adopting unresolved professional judgments.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "agent_lane_proposal_kinds": {
      "status": "ADOPTED",
      "value": {
        "local_proposal_kinds": ["PROPOSE_INTEREST_WAIVER", "PROPOSE_UNAPPLIED_CASH_RELEASE", "REQUEST_ADVISORY_CLOSE_REVIEW"],
        "required_binding": ["TARGET_SCOPE", "STATE_DIGEST", "POLICY_DIGEST"],
        "stale_proposal": "RECOMPUTE",
        "agent_can_approve": false,
        "agent_can_post": false,
        "agent_can_execute_funds": false,
        "agent_can_auto_close": false,
        "upstream_adoption_claimed": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-09", "CAP-20"],
      "rationale": "Bounded proposals do not grant financial execution authority.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

- 저장 대상은 `docs/decisions/CAPITAL_WAIVER_WRITEOFF.md`다. 단일 결정 블록에 아홉 항목과 ADOPTED 메타데이터를 포함했다. 전문 판단의 미정값은 null·target·이유를 명시했다.
- blocking finding은 §3.2의 초기화·귀속 순서·회수 및 면제 공식·잔여 한도 조정과 JSON으로 해결한다. 실제 무배분 회수 정책은 유지한다.
- close-gate 재검토 경로, `funds_executed:false`, production `NOT_AUTHORIZED`를 기록했다.
- 이번 응답에서는 파일 저장·명령 실행을 하지 않았다. 저장 후 `python3 scripts/decision_ledger.py`의 해당 노드 상태와 종료 코드 0, `python3 -m unittest tests.test_decisions tests.test_decisions_surface`의 종료 코드 0을 확인해야 한다. 과거 실행 결과를 이번 문서의 통과 증거로 주장하지 않는다.

## 6. Open risks

- 상각 시점 구성·사건 순서가 없는 이력은 안전한 보조 재생이 불가능하다. 해당 경로는 대사 전 `NOT_BOUND`다.
- 기존 회수 소비자가 조정된 `R`을 사용하지 않으면 면제 후 과다 회수가 가능하므로 두 경로를 함께 연결해야 한다.
- 합성 역할·로컬 원자성은 실제 인증·분산 내구성·법적 효력을 증명하지 않는다. V1 취소 명령 부재에 따른 운영 복구 한계도 남는다.

## 7. 후속 작업

1. Supervisor가 문서를 저장하고 결정 원장·표면 검증을 수행한다. 본 작업은 commit·push·외부 게시를 하지 않는다.
2. 소비 노드는 정본 필드 바인딩, 상각 snapshot 대사, 보조 재생, 면제 및 모든 회수 경로의 조정 한도를 함께 구현한다.
3. §3.2 예시와 회수→면제·면제→회수·상각 전 면제·같은 날 순서·동시 게시·재전송·누락 이력·대사 실패·종결 차단을 검증한다.
4. 회계·세무·법무 전문 검토와 upstream 채택 영수증은 별도 경로로 확보한다.
