# Capital 이자 면제·미적용 현금 해제·종결 게이트 재검토 결정

> **PROVISIONAL PRODUCT DECISION**
>
> 결정자 표기: **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**
>
> 날짜: **2026-11-10** · Capital main: **`a791651`** · kix-protocol: **`61e581a`**
>
> **시뮬레이션·제품 설계 전용.** `funds_executed:false`, production **`NOT_AUTHORIZED`**. 회계·세무·법무는 **`WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW`**다. 소비 구현, 실제 인증, 실자금 실행, upstream 채택은 이 결정으로 승인되지 않는다.

결정자 표기와 기준 커밋은 supervisor 제공 메타데이터다. 이번 개정은 제공된 팩·기존 결정 본문·리뷰에 근거한다. 지정 모델의 CLI 실행, 세 번의 실패, Fable 인계 및 체크아웃 검증은 확인하지 않았으며 주장하지 않는다. 산출물은 이 문서 본문뿐이다.

## 1. 결정 요약

`ADOPTED`는 잠정 제품 정책 채택을 뜻한다. 구현 완료나 upstream 채택을 뜻하지 않는다.

| item | decision | CAP rows | consumer |
|---|---|---|---|
| `waiver_command_existence` | ADOPTED. 열린 선지급에 명시적 `waive_interest`; 상각 후에도 허용 | CAP-01, CAP-04 | waiver overlay |
| `waiver_scope_interest_only_vs_principal` | ADOPTED. 미납 약정·연체이자만; 상각 후 보조 귀속과 잔여 한도 동시 조정 | CAP-01, CAP-04 | 이자·회수 투영 |
| `waiver_authority_and_two_person_threshold` | ADOPTED. 서로 다른 운영자·검토자; 누적 임계 초과 시 제3의 금융책임자 | CAP-04, CAP-09 | 승인 검증 |
| `waiver_caps_and_sim_day_recording` | ADOPTED. 적격 이자 및 누적 예산 이내; 현재 논리 일만 허용 | CAP-01, CAP-04 | cap·재생 |
| `unapplied_cash_release_or_refund` | ADOPTED. 상환 배분 우선; 대사된 원천 lot에서 합성 원송금자에게 해제 | CAP-02, CAP-05 | 보관액 해제 |
| `close_gate_reconsideration` | ADOPTED. 유효 면제를 순이자에 반영; 나머지 차단 조건 보존 | CAP-01, CAP-04, CAP-20 | advisory close |
| `overlay_entry_schema_and_digest_effect` | ADOPTED. append-only·원자성·멱등성; 재생 근거 digest 결속 | CAP-13, CAP-14, CAP-15 | 저장·export |
| `tax_and_accounting_working_assumption` | ADOPTED. 면제·회수·상각 분리; 전문 판단 세 칸은 UNDETERMINED | CAP-04, CAP-20 | 회계 설명·투영 |
| `agent_lane_proposal_kinds` | ADOPTED. 세 종류의 제안만; 승인·게시·지급 권한 없음 | CAP-09, CAP-20 | agent proposal lane |

## 2. KIX 비전 연결

- `docs/CAPITAL_REQUIREMENTS_KO.md`: 역사적 결정 근거와 실행·참조 핀을 구분한다. 이번 기준일 갱신은 vendor 또는 계약 핀 변경이 아니다.
- `docs/SEAMS.md`: 로컬 정책 채택으로 포트의 `NOT_BOUND`를 해제하지 않는다. upstream receipt와 SEMANTIC_CONFORMANCE는 별도 증거가 필요하다.
- `docs/VALIDATION.md`: 합성 검증과 실자금·인증·실행 권한을 구분한다. 다른 노드의 통과 기록을 이번 제출의 검증으로 옮기지 않는다.
- `docs/decisions/CAPITAL_CLAIM_SLICE_REGISTRY.md`: 금융 상한은 정본 필드명으로 참조하고 숫자를 복제하지 않는다.
- `docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md`: 합성 계정표로 전문 회계·세무·법무 결론을 추론하지 않는다.

위 경로는 제공된 발췌만 사용했다. 선행 repayment-posting·default-recovery·financial-terms 정책은 팩의 설명과 기존 결정 본문·리뷰가 확인한 범위에 의존한다. 허용 범위 밖 원문이나 생략된 본문을 읽었다고 주장하지 않는다. 기존 조건의 이름·숫자는 선행 정본을 따르며, 이번 문서는 명시한 면제·해제·종결 평가만 확장한다. 소비 바인딩 누락은 `NOT_BOUND`로 처리하고 이미 채택된 정책을 `DECISION_REQUIRED`로 되돌리지 않는다.

## 3. 항목별 결정

### 3.1 `waiver_command_existence`

`waive_interest`를 신설한다. 정상·연체·부도 및 회계상 상각 이후의 **열린 선지급**에 허용한다. 약정이자·연체이자 금액을 각각 지정하며, KRW 정수·각각 0 이상·합계 양수여야 한다. 적격 잔액 초과, 음수, 소수는 거절한다.

대상, 사유, 근거, 현재 상태·정책 digest, 승인 증거를 필수로 한다. 자동 면제, 종결 기록에 대한 게시, 과거 영수증 수정 및 V1 면제 취소 명령은 허용하지 않는다. 효과는 합성 이자청구 감소다.

### 3.2 `waiver_scope_interest_only_vs_principal`

현재 `sim_day`까지 발생·확정된 미납 약정이자와 연체이자만 면제한다. 원금·수수료·미래 이자·제3자 보호채무·반환 의무는 제외한다. 원금 한도나 차입기초는 복원하지 않는다. 상각 자체를 면제로 보지 않는다.

상각 전 적격액은 버킷별 확정 발생액에서 실제 확정 배분과 이전 유효 면제를 각각 한 번 차감한다. 상각 후 실제 회수는 기존의 **배분 없는 단일 잔여채권 회수**를 유지한다. 면제 적격성과 잔여청구 대사에만 `POST_WRITEOFF_WAIVER_ATTRIBUTION_V1` 보조 귀속을 사용한다.

최초 상각 직후 정본 snapshot에서 이전 배분·면제가 반영된 미납 약정이자 `C`, 연체이자 `D`, 권위 있는 잔여 회수 한도 `R`, 기타 잔여채권 `O=R−C−D`를 초기화한다. 항상 `R=C+D+O`이고 모두 0 이상이다. 장부가액 0을 `R=0`으로 해석하지 않는다.

확정 회수 `x`는 `0<x≤R`이어야 한다. 보조 귀속은 연체이자 → 약정이자 → 기타 순서다. `aD=min(x,D)`, `aC=min(x−aD,C)`, `aO=x−aD−aC`를 각 버킷에서 차감하고 `R`도 `x`만큼 줄인다. 이는 실제 상환 배분·회계 배분·원금 상환 증거가 아니다.

면제 `(wC,wD)`는 버킷 잔액 이내이며 합계 양수여야 한다. `C−=wC`, `D−=wD`, `R−=wC+wD`를 원자적으로 적용하고 `O`는 유지한다. 후속 회수 견적·예약·게시는 조정된 `R`을 사용한다. 이전 상태에 결속된 승인은 무효다.

원래 snapshot부터 같은 날 사건까지 확정 append 순서로 재생한다. 구성·순서 누락, 초과 회수 또는 불변식 위반은 `NOT_BOUND`로 거절하고 종결을 차단한다. 추가 발생은 기존 정책이 허용하고 잔여채권에 포함하는 경우에만 해당 버킷과 `R`에 함께 반영한다.

검증 예시: `C=80,D=20,O=1000,R=1100`에서 회수 50 후 `C=50,D=0,R=1050`이다. 약정이자 60 면제는 거절한다. 40 면제 후 `C=10,R=1010`이며 후속 회수 1015는 거절한다. 예시 숫자는 금융 조건이 아니다.

### 3.3 `waiver_authority_and_two_person_threshold`

모든 면제는 `SIM_OPERATOR` 제안과 다른 주체인 `SIM_FINANCE_REVIEWER` 승인을 요구한다. 한 주체의 역할 변경은 주체 분리가 아니다.

동일 수익자의 현재 논리 일 누적 면제액에 제안액을 더한 값이 `CAPITAL-TERMS-V1.underwriting_depth.two_person_threshold_krw`를 **초과**하면 앞의 두 주체와 다른 `SIM_FINANCE_OWNER`를 추가한다. 임계값과 같으면 기본 두 주체 요건을 적용한다. 분할 제안도 누적한다.

승인은 대상·버킷 금액·사유·현재 일·상태 digest·정책 digest에 결속한다. 게시 시 현재 역할과 결속을 다시 검증한다. 상태 변경 시 재승인한다. 합성 역할은 실제 인증이나 은행 권한이 아니다.

### 3.4 `waiver_caps_and_sim_day_recording`

면제는 버킷별 적격 이자의 100% 이내다. 별도 누적 면제 예산의 선지급·수익자·포트폴리오 상한은 각각 `underwriting_depth.single_advance_cap_krw`, `beneficiary_aggregate_cap_krw`, `portfolio_cap_krw`를 참조한다. 기존 인출 cap의 의미나 사용액은 바꾸지 않는다.

누적액은 전체 보존 이력 기준이며 종결·일자 변경·상각·회수로 리셋하지 않는다. 수익자는 선지급 발생 당시 바인딩을 따른다. `effective_sim_day`는 게시 시점 현재 일뿐이다. 소급·미래일·이율·가속일 재작성은 거절한다. 필요한 참조나 이력이 없거나 불명확하면 `NOT_BOUND`다.

### 3.5 `unapplied_cash_release_or_refund`

`release_unapplied_cash`를 신설하여 선행 repayment-posting의 “환불 명령 없음”을 이번 결정에서 명시적으로 확장한다. 이는 합성 해제 경로이며 외부 환불 권한은 아니다.

확정 원천 영수증과 대사된 보관 lot의 가용 잔액 안에서 양의 KRW 정수 부분 해제를 허용한다. 수취인은 동일한 합성 원송금자만 가능하다. 귀속 불명·분쟁·반환 제한·보호채무·UNKNOWN·진행 중 예약은 차단한다. 같은 범위에서 확정 상환 배분이 가능하면 기존 대사·배분을 먼저 수행하고 해제 가능액을 다시 계산한다. 면제가 반환액을 자동 생성하지 않는다.

운영자와 별도 검토자가 승인한다. 원송금자의 당일 누적 해제액에 제안액을 더한 값이 §3.3의 임계값을 초과하면 제3의 금융책임자를 추가한다. 승인은 원천 lot·수취인·금액·사유·현재 일·상태 및 정책 digest에 결속한다. 보관액 감소와 `SIMULATED_RELEASE` 기록은 원자적이며 `funds_executed=false`다.

### 3.6 `close_gate_reconsideration`

**`CAPITAL_REPAYMENT_POSTING`의 close-gate 규칙은 이 결정을 통해서만 재검토할 수 있다.** 이번 변경은 유효 면제를 순이자 조건에 반영한다.

상각 전에는 확정 발생액에서 실제 확정 배분과 유효 면제를 차감한 순이자가 0이어야 한다. 상각 후에는 §3.2로 재생한 `C+D=0`이어야 한다. 보조 귀속을 실제 배분과 중복 차감하지 않는다.

원금 잔액, 기타 채무, 열린 환불·분쟁, 보관액, UNKNOWN, 미완료 승인·예약, 상각 후 대사 실패 등 **다른 기존 차단 조건은 모두 유지**한다. `R=0`이나 보조 `O` 감소로 원금 상환을 추론하지 않는다. 해제로 보관액이 0이 되면 보관액 조건 하나만 충족한다.

결과는 `ADVISORY_ONLY`다. pinned FSM 종결이나 실제 채무 소멸을 실행하지 않는다. 상태 변경 시 평가를 무효화한다. `funds_executed=false`, production `NOT_AUTHORIZED`를 유지한다.

### 3.7 `overlay_entry_schema_and_digest_effect`

엔트리는 `overlay_id`/`kind`/`payload`이며 kind는 `INTEREST_WAIVER`, `UNAPPLIED_CASH_RELEASE`다. payload에 operation·현재 일·대상·금액·사유·근거·승인·기준 overlay digest·정책 참조와 digest·`funds_executed:false`를 담는다.

상각 후 면제는 snapshot 참조, 보조 규칙 버전, 확정 사건 순서, `C/D/O/R` 전후 값을 추가한다. 검증·승인·cap·잔여 한도·예약 충돌 확인과 append는 원자적이다. 같은 기준 digest의 회수와 면제는 하나가 먼저 성공하면 다른 요청을 재평가한다.

동일 operation·동일 내용은 최초 결과를 반환하고 내용이 다르면 충돌이다. 응답 유실 시 새 operation으로 재게시하지 않고 기존 결과를 조회한다. 효과·정책 digest·재생 근거는 overlay digest와 export에 포함하며 벽시계·프로세스 ID는 제외한다. pinned FSM digest와 기존 golden은 변경하지 않는다. pack 등록 벡터 갱신은 정책·문서 결속 검증으로 구분한다.

### 3.8 `tax_and_accounting_working_assumption`

면제는 비현금 이자청구 감소이며 회수·회계상 상각과 구별한다. 투영은 총발생·실제 배분·면제·상각 후 보조 귀속·순잔액을 분리한다. 상각 후 면제로 손실을 이중 인식하지 않는다. 보조 귀속 순서는 수익 인식 순서가 아니다. 보관액은 보관 의무이며 해제는 수익·회수가 아니다.

계정 코드·분개, 세무 처리·인정일, 법적 면제 효력은 각각 `UNDETERMINED`, `value:null`이다. 지정 target은 회계·세무·법무 전문 검토다. 합성 차트와 기존 합계는 변경하지 않는다.

### 3.9 `agent_lane_proposal_kinds`

로컬 제안은 `PROPOSE_INTEREST_WAIVER`, `PROPOSE_UNAPPLIED_CASH_RELEASE`, `REQUEST_ADVISORY_CLOSE_REVIEW`만 허용한다. 대상 범위·상태 및 정책 digest에 결속된 초안과 계산 근거를 제출한다.

에이전트는 승인자 수에 포함되지 않으며 게시·지급·자동 종결 권한이 없다. stale 제안은 재계산한다. 로컬 제안 종류 추가는 upstream AI 위임 계약이나 도구 범위 채택을 뜻하지 않는다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "waiver-writeoff-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-11-10",
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
        "eligible_records": "OPEN_ADVANCES",
        "post_writeoff_allowed": true,
        "closed_record_posting": false,
        "automatic_waiver": false,
        "historical_receipt_mutation": false,
        "reversal_command_v1": false,
        "amounts": "NONNEGATIVE_INTEGER_KRW_BUCKETS_WITH_POSITIVE_SUM"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-10",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Explicit relief on open advances with immutable evidence.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "waiver_scope_interest_only_vs_principal": {
      "status": "ADOPTED",
      "value": {
        "included": ["ACCRUED_UNPAID_CONTRACT_INTEREST", "ACCRUED_UNPAID_OVERDUE_INTEREST"],
        "excluded": ["PRINCIPAL", "FEES", "FUTURE_INTEREST", "THIRD_PARTY_OBLIGATIONS", "RETURN_OBLIGATIONS"],
        "pre_writeoff_balance": "ACCRUAL_MINUS_ACTUAL_CONFIRMED_BUCKET_ALLOCATIONS_MINUS_VALID_WAIVERS",
        "post_writeoff": {
          "rule": "POST_WRITEOFF_WAIVER_ATTRIBUTION_V1",
          "actual_recovery": "SINGLE_RESIDUAL_CLAIM_WITHOUT_ALLOCATION",
          "purpose": "WAIVER_ELIGIBILITY_AND_RESIDUAL_RECONCILIATION_ONLY",
          "initialization": {
            "C": "SNAPSHOT_UNPAID_CONTRACT_INTEREST_NET_OF_PRIOR_ALLOCATIONS_AND_WAIVERS",
            "D": "SNAPSHOT_UNPAID_OVERDUE_INTEREST_NET_OF_PRIOR_ALLOCATIONS_AND_WAIVERS",
            "R": "AUTHORITATIVE_RESIDUAL_RECOVERY_CAP_NOT_BOOK_VALUE",
            "O": "R-C-D"
          },
          "invariant": "R=C+D+O; ALL_NONNEGATIVE",
          "replay": "ORIGINAL_WRITEOFF_SNAPSHOT_THEN_CONFIRMED_APPEND_ORDER_INCLUDING_SAME_DAY_EVENTS",
          "historical_receipts": "IMMUTABLE",
          "recovery_precondition": "0<x<=R",
          "recovery_formula": ["aD=min(x,D)", "aC=min(x-aD,C)", "aO=x-aD-aC"],
          "recovery_effect": ["D'=D-aD", "C'=C-aC", "O'=O-aO", "R'=R-x"],
          "waiver_precondition": "0<=wC<=C; 0<=wD<=D; wC+wD>0",
          "waiver_atomic_effect": ["C'=C-wC", "D'=D-wD", "O'=O", "R'=R-wC-wD"],
          "all_future_recovery_paths": "USE_ADJUSTED_R_IN_QUOTES_RESERVATIONS_AND_POSTING",
          "new_accrual": "EXISTING_POLICY_MUST_AUTHORIZE_AND_INCLUDE_IN_RESIDUAL; UPDATE_BUCKET_AND_R_ATOMICALLY",
          "missing_or_inconsistent_history": "NOT_BOUND_REJECT_AND_BLOCK_CLOSE",
          "memo_is_actual_payment_allocation": false,
          "memo_is_accounting_allocation": false,
          "memo_proves_principal_payment": false,
          "duplicate_subtraction": false
        },
        "writeoff_is_waiver": false,
        "principal_capacity_release": false,
        "future_accrual": "UNCHANGED_EXISTING_TERMS"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-10",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Prevent waiver of recovered interest and collection of waived interest.",
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
        "distinctness": "SUBJECT_IDENTITY_NOT_ROLE_LABEL",
        "approval_binding": ["TARGET", "BUCKET_AMOUNTS", "REASON", "STATE_DIGEST", "POLICY_DIGEST", "SIM_DAY"],
        "posting_check": "CURRENT_ROLES_AND_APPROVAL_BINDING",
        "state_change": "REAPPROVE",
        "agent_approval": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-10",
      "cap_rows": ["CAP-04", "CAP-09"],
      "rationale": "Separate actors and cumulative thresholds prevent self-approval and splitting.",
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
        "draw_cap_semantics": "UNCHANGED",
        "beneficiary_binding": "AT_ADVANCE_ORIGINATION",
        "effective_day": "CURRENT_SIM_DAY_ONLY",
        "rewrite_rates_or_acceleration_day": false,
        "missing_reference_or_history": "NOT_BOUND_REJECT"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-10",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Bound cumulative relief using canonical financial references.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "unapplied_cash_release_or_refund": {
      "status": "ADOPTED",
      "value": {
        "command": "release_unapplied_cash",
        "result": "SIMULATED_RELEASE",
        "recipient": "ORIGINAL_SYNTHETIC_REMITTER_ONLY",
        "amount": "POSITIVE_INTEGER_KRW",
        "partial_release": true,
        "cap": "SOURCE_LOT_AVAILABLE_RECONCILED_BALANCE",
        "priority": "EXISTING_CONFIRMED_REPAYMENT_ALLOCATION_FIRST_THEN_RECALCULATE",
        "blockers": ["UNKNOWN", "DISPUTE", "UNRESOLVED_OWNERSHIP", "PROTECTED_OBLIGATION", "RETURN_RESTRICTION", "PENDING_RESERVATION"],
        "approval": "DISTINCT_OPERATOR_AND_REVIEWER",
        "approval_binding": ["SOURCE_LOT", "RECIPIENT", "AMOUNT", "REASON", "SIM_DAY", "STATE_DIGEST", "POLICY_DIGEST"],
        "additional_owner_threshold_ref": "CAPITAL-TERMS-V1.underwriting_depth.two_person_threshold_krw",
        "threshold_basis": "ORIGINAL_REMITTER_SIM_DAY_RELEASES_INCLUDING_PROPOSAL",
        "threshold_comparison": "GREATER_THAN",
        "above_threshold": "ADDITIONAL_DISTINCT_SIM_FINANCE_OWNER",
        "posting": "ATOMIC_HELD_BALANCE_REDUCTION_AND_RELEASE_RECORD",
        "waiver_automatically_creates_refund": false,
        "funds_executed": false,
        "external_refund": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-10",
      "cap_rows": ["CAP-02", "CAP-05"],
      "rationale": "Extend the prior no-refund-command policy with reconciled simulation releases.",
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
        "funds_executed": false,
        "production": "NOT_AUTHORIZED",
        "state_change": "INVALIDATE_PRIOR_EVALUATION"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-10",
      "cap_rows": ["CAP-01", "CAP-04", "CAP-20"],
      "rationale": "Reflect valid waivers while preserving every other close requirement.",
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
        "digest_effect": "INCLUDE_EFFECT_ENTRIES_POLICY_DIGEST_AND_REPLAYABLE_EVIDENCE_IN_OVERLAY_AND_EXPORT",
        "exclude_from_digest": ["WALL_CLOCK", "PROCESS_ID"],
        "pinned_fsm_digest": "UNCHANGED",
        "existing_goldens": "UNCHANGED",
        "reversal_command_v1": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-10",
      "cap_rows": ["CAP-13", "CAP-14", "CAP-15"],
      "rationale": "Atomic replayable effects prevent duplicate relief and stale recovery.",
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
            "reason": "Reviewed waiver and post-writeoff mappings are not supplied."
          },
          "tax_treatment_and_dates": {
            "status": "UNDETERMINED",
            "value": null,
            "target": "TAX_PROFESSIONAL_REVIEW",
            "reason": "Reviewed tax treatment and recognition dates are not supplied."
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
      "date": "2026-11-10",
      "cap_rows": ["CAP-04", "CAP-20"],
      "rationale": "Separate product events while leaving professional determinations unresolved.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "agent_lane_proposal_kinds": {
      "status": "ADOPTED",
      "value": {
        "local_proposal_kinds": ["PROPOSE_INTEREST_WAIVER", "PROPOSE_UNAPPLIED_CASH_RELEASE", "REQUEST_ADVISORY_CLOSE_REVIEW"],
        "required_binding": ["TARGET_SCOPE", "STATE_DIGEST", "POLICY_DIGEST"],
        "calculation_evidence": "REQUIRED",
        "stale_proposal": "RECOMPUTE",
        "agent_can_approve": false,
        "agent_can_post": false,
        "agent_can_execute_funds": false,
        "agent_can_auto_close": false,
        "upstream_adoption_claimed": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-10",
      "cap_rows": ["CAP-09", "CAP-20"],
      "rationale": "Scoped proposals confer no approval or execution authority.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| 기준 | 이번 제출의 근거·상태 |
|---|---|
| 단일 블록·아홉 항목 | §4에 수록. 모든 ADOPTED 항목에 값·제공자·ISO 날짜·잠정 표시가 있다. |
| UNDETERMINED | 전문 판단 세 칸에 `value:null`, 이유, 이름 있는 target이 있다. |
| close-gate 재검토와 실행 경계 | §3.6 및 해당 JSON에 전용 재검토 경로·`ADVISORY_ONLY`·실자금 미실행·production 미승인을 명시했다. |
| 파일 존재·원장·테스트 | supervisor 저장 후 확인할 조건이다. 이번 응답에서는 파일 저장이나 명령을 실행하지 않았으며 exit 0을 주장하지 않는다. |
| 바인딩 | 리뷰가 확인한 `PENDING_CONSUMER`는 구현 완료로 승격하지 않는다. |
| PR 범위 | 아래 두 지적의 실제 복원·diff 확인은 이번 문서 제출로 증명되지 않는다. |

**리뷰 차단 사항 처리:** 두 지적 모두 타당하며 정책 변경 사유는 아니다. `DECISION_REQUIRED.md`의 무관한 본문 교체는 PR diff에서 제거해야 한다. `tests/test_coa_candidate.py`의 `--diff-filter=MDRTCUXB` 변경 역시 제거하고 `origin/main` 바이트를 보존해야 한다. guard 약화를 대안으로 채택하지 않는다.

최종 REVISION SCOPE는 두 파일의 읽기·수정을 허용하지 않고 산출물을 문서로 한정한다. 따라서 이 응답은 복원 완료나 PR의 BLOCK 해소를 주장할 수 없다. 이는 추가 제품 결정을 요구하는 상태가 아니라 저장소 정리·검증 증거가 남은 상태다. 이전 라운드의 테스트 수치와 READY 문구는 이번 head의 검증 증거로 사용하지 않는다.

## 6. Open risks

- 상각 snapshot·사건 순서·정본 한도가 없으면 해당 경로는 `NOT_BOUND`다. 숫자 추정으로 해제하지 않는다.
- 면제와 모든 회수 경로가 같은 조정 잔여 한도를 사용해야 과다 회수를 막을 수 있다.
- 합성 역할·로컬 원자성은 실제 인증·분산 내구성·법적 효력을 입증하지 않는다. V1 취소 명령 부재는 복구 제약이다.
- 두 범위 위반의 실제 정리와 저장된 문서의 검증은 확인되지 않았다. 통과 여부는 실행 증거로 판단한다.

## 7. 후속 작업

1. supervisor 저장·통합 단계에서 두 범위 밖 변경을 PR에서 제거하고 guard의 `origin/main` 바이트 일치를 확인한다. 이 문서로 그 조치를 대체하지 않는다.
2. 저장된 head에서 `python3 scripts/decision_ledger.py`의 종료 코드 0과 본 노드의 `PROVISIONAL_PRODUCT_DECISION` 표기를 확인한다. `python3 -m unittest tests.test_decisions tests.test_decisions_surface` 및 `python3 scripts/docs_surface.py --check`를 실행하여 실제 결과를 기록한다.
3. 소비 노드는 정본 바인딩·상각 재생·공통 잔여 한도·해제·advisory close를 구현한다. 회수↔면제 순서, 동일 일자 사건, 임계값 경계·분할, 동시 게시·재전송, 누락 이력·종결 차단을 검증한다.
4. 새 벡터 파일에는 docs surface 등록과 README needles가 필요하다. 허용 범위 밖 등록 수정이 필요한 신규 파일은 이번 문서 제출에서 추가하지 않는다.
5. 전문 판단과 upstream 채택은 지정 검토·실제 영수증으로 별도 확정한다. 이번 제출은 commit·push·외부 게시·실자금 실행을 수행하지 않는다.
