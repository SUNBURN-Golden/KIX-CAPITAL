# Capital 이자 면제·미적용 현금 해제·종결 게이트 재검토

> **PROVISIONAL PRODUCT DECISION** · `waiver-writeoff-decision`  
> 지정 결정자 표기 — **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**  
> **2026-11-20** · KIX-CAPITAL main `b24f175` · kix-protocol `14bb3eb` (supervisor 제공 기준)  
> 시뮬레이션·제품 설계 전용. `funds_executed=false`, production `NOT_AUTHORIZED`. 회계·세무·법무의 근거는 `WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW`다.

Sonnet CLI 세 번과 후속 Fable CLI 한 번이 모두 로그인 단계에서 종료됐다. Codex가 제공된 팩과 리뷰에 근거해 이번 개정본을 작성했다.

## 1. 결정 요약

| item | 잠정 제품 결정 | CAP rows | 소비자 |
|---|---|---|---|
| `waiver_command_existence` | 열린 선지급에 명시적 이자 면제 명령을 허용한다. | CAP-01, CAP-04 | 면제 명령 처리기 |
| `waiver_scope_interest_only_vs_principal` | 미납 약정·연체이자만 면제한다. 상각 시 미상환 원금과 순이자로 회수 한도를 대사한다. | CAP-01, CAP-04 | 이자·회수 투영 |
| `waiver_authority_and_two_person_threshold` | 제안·승인 주체를 분리하고 당일 누적액이 임계값을 초과하면 제3자 승인을 요구한다. | CAP-04, CAP-09 | 승인 검증 |
| `waiver_caps_and_sim_day_recording` | 버킷 잔액과 세 누적 예산을 모두 적용하고 현재 논리 일에 게시한다. | CAP-01, CAP-04 | 한도 검증·재생 |
| `unapplied_cash_release_or_refund` | 상환 배분 후 원천 lot의 대사 잔액을 합성 원송금자에게 해제한다. | CAP-02, CAP-05 | 보관액 처리기 |
| `close_gate_reconsideration` | 유효 면제를 순이자 판정에 반영하고 나머지 종결 조건을 모두 적용한다. | CAP-01, CAP-04, CAP-20 | 종결 자문 |
| `overlay_entry_schema_and_digest_effect` | 두 종류 모두 다섯 최상위 필드에 journal 위치·논리 일·효과를 기록한다. | CAP-13, CAP-14, CAP-15 | overlay 저장·export |
| `tax_and_accounting_working_assumption` | 면제·상각·회수·해제를 구분하고 전문 판단 세 가지를 유보한다. | CAP-04, CAP-20 | 회계 투영·전문 검토 |
| `agent_lane_proposal_kinds` | 에이전트는 면제·해제·종결 재검토를 제안할 수 있다. | CAP-09, CAP-20 | 로컬 제안 처리기 |

## 2. KIX 비전 연결

- 결정의 기준 커밋은 출처를 기록한다. 포트 채택에는 해당 upstream 영수증이 필요하며 이번 결정의 범위는 로컬 시뮬레이션이다. [CAPITAL_REQUIREMENTS_KO.md](../CAPITAL_REQUIREMENTS_KO.md) · [SEAMS.md](../SEAMS.md)
- 면제 한도와 승인 임계값은 선행 금융 조건의 정본 필드에서 읽는다. 계정·세무 처리에는 별도 전문 검토가 필요하다. [CAPITAL_CLAIM_SLICE_REGISTRY.md](CAPITAL_CLAIM_SLICE_REGISTRY.md) · [CAPITAL_ACCOUNTS_TAX_LEGAL.md](CAPITAL_ACCOUNTS_TAX_LEGAL.md)
- 검증 결과는 실제 실행한 산출물과 기준 커밋에 귀속한다. 이번 개정의 입력은 제공된 발췌, 기존 면제 결정 본문과 리뷰다. [VALIDATION.md](../VALIDATION.md)

## 3. 항목별 결정

### 3.1 `waiver_command_existence`

`waive_interest`는 정상·연체·부도·상각 후 상태의 **열린 선지급**에 허용한다. 약정이자와 연체이자를 각각 음이 아닌 KRW 정수로 지정하고 합계는 양수여야 한다. 대상, 사유, 근거, 현재 상태·정책 digest 및 승인을 기록한다. 종결된 선지급, 버킷 초과, 자동 면제는 거절한다. V1은 확정 영수증을 보존하며 면제 취소 명령을 제공하지 않는다.

### 3.2 `waiver_scope_interest_only_vs_principal`

현재 논리 일까지 확정된 미납 약정·연체이자만 적격이다. 원금, 수수료, 미래 이자, 제3자 보호채무, 반환 의무는 제외한다. 면제로 인출 여력이나 차입기초를 복원하지 않는다. 상각만으로 이자가 면제되지는 않는다.

**상각 개시 대사.** 최초 상각 시점의 동일한 journal 위치에서, 후속 사건을 반영하기 전에 아래 값을 확인한다.

| 값 | 산출 근거 |
|---|---|
| `P` | 상각 시점까지 확정된 원금 상환을 반영한 미상환 원금. 원금 기록에서 독립적으로 읽는다. |
| `C`, `D` | 각각 약정·연체이자의 확정 발생액에서 해당 버킷의 확정 배분과 이전 유효 면제를 정확히 한 번 차감한 순액. snapshot이 이미 순액이면 이력과 대사하고 다시 차감하지 않는다. |
| snapshot 회수 한도 | snapshot이 제시하는 잔여 회수 한도. 위 세 구성액과 독립적으로 비교한다. |

**snapshot 회수 한도가 `P+C+D`와 정확히 같을 때만 `R=P+C+D`, `O=P`로 개시한다.** 모든 구성액은 음이 아닌 KRW 정수여야 한다. 한도 차이를 `O`에 흡수하거나 장부가액으로 `R`을 대체할 수 없다.

예를 들어 원금 100원, 약정이자 20원, 상각 전 면제 10원, 연체이자와 배분액이 각각 0원이면 `P=100, C=10, D=0`이다. 한도 **110원**인 snapshot은 통과하고 **120원**인 snapshot은 거절한다. 후자를 `O=110`으로 맞추면 면제한 10원이 다시 회수 대상이 된다. 대사가 실패하거나 근거가 누락되면 `NOT_BOUND`로 처리해 회수 견적·예약·게시, 상각 후 면제 및 종결 판정을 차단한다.

**상각 후 재생.** 실제 회수는 단일 잔여채권에 게시한다. `POST_WRITEOFF_WAIVER_ATTRIBUTION_V1`은 면제 가능액과 잔여 한도를 대사하기 위한 보조 귀속이다. 최초 snapshot 이후 확정 사건을 같은 날에도 append 순서대로 한 번씩 적용한다.

- 회수액 `x`에는 `0<x≤R`을 요구한다. `aD=min(x,D)`, `aC=min(x−aD,C)`, `aO=x−aD−aC`를 각각 `D,C,O`에서 차감하고 `R`을 `x`만큼 줄인다.
- 면제액 `wC,wD`는 각 버킷 잔액 이내여야 한다. `C,D`에서 각각 차감하고 `R`도 합계만큼 원자적으로 줄인다. `O`는 유지한다. 이후 견적·예약·게시는 모두 조정된 `R`을 읽는다.
- 추가 발생은 선행 정책상 잔여채권에 포함되는 경우에만 해당 버킷과 `R`에 함께 더한다. 매번 `R=C+D+O`와 비음수 조건을 확인한다. 보조 귀속으로 실제 상환 배분, 원금 상환 또는 회계 배분을 증명할 수 없다.

### 3.3 `waiver_authority_and_two_person_threshold`

`SIM_OPERATOR`가 제안하고 별도의 `SIM_FINANCE_REVIEWER`가 승인한다. 동일 수익자의 현재 논리 일 확정 면제액에 제안액을 더해 `CAPITAL-TERMS-V1.underwriting_depth.two_person_threshold_krw`를 **초과**하면 두 사람과 다른 `SIM_FINANCE_OWNER`의 승인도 필요하다. 임계값과 같으면 두 주체로 충분하다. 주체 ID로 구별하고 분할 제안도 누적한다. 게시 시 대상·버킷별 금액·사유·일자·상태 및 정책 digest와 현재 역할을 다시 확인한다. 결속값이 달라지면 재승인한다.

### 3.4 `waiver_caps_and_sim_day_recording`

각 버킷의 적격 잔액을 최대 100%까지 면제한다. 별도 면제 예산은 선지급·발생 당시 수익자·포트폴리오별 평생 누적액에 이번 면제액을 더해 검사한다. 세 한도는 각각 `CAPITAL-TERMS-V1.underwriting_depth`의 `single_advance_cap_krw`, `beneficiary_aggregate_cap_krw`, `portfolio_cap_krw`에서 읽는다. 하나라도 넘으면 전체를 거절한다. 예산은 일자 변경·종결·상각·회수로 초기화되지 않는다. `effective_sim_day`는 게시 당시의 현재 일이다. 소급일·미래일과 금리·기한이익 상실일 재작성은 거절한다. 참조나 누적 이력이 불명확하면 `NOT_BOUND`다.

### 3.5 `unapplied_cash_release_or_refund`

`release_unapplied_cash`로 선행 상환 정책에 합성 해제 경로를 추가한다. 확정 원천 영수증과 보관 lot를 대사하고, 같은 범위에서 확정 가능한 상환 배분을 먼저 수행한다. 남은 가용액 이내의 양의 KRW 정수만 **해당 lot의 합성 원송금자**에게 부분 또는 전액 해제한다. 귀속 불명, 분쟁, 반환 제한, 보호채무, 진행 중 예약, `UNKNOWN`은 차단한다.

별도 운영자·검토자가 원천 lot, 수취인, 금액, 사유, 현재 일과 상태·정책 digest에 결속한다. 원송금자의 당일 누적 해제액에 제안액을 더해 §3.3 임계값을 초과하면 제3의 금융책임자도 승인한다. 보관액 감소와 `SIMULATED_RELEASE` 기록은 원자적이다. 이자 면제로 해제액이 자동 발생하지 않으며 외부 지급은 실행하지 않는다.

### 3.6 `close_gate_reconsideration`

**`CAPITAL_REPAYMENT_POSTING`의 close-gate 규칙은 이 결정을 통해서만 재검토할 수 있다.** 상각 전 이자 조건은 확정 배분과 유효 면제를 반영한 두 순이자 버킷이 모두 0일 때 충족된다. 상각 후에는 §3.2의 개시 대사와 재생이 성공하고 `C+D=0`이어야 한다.

원금 잔액, 기타 채무, 열린 환불·분쟁, 보관액, `UNKNOWN`, 미완료 승인·예약, 대사 실패 등 다른 기존 차단 조건을 모두 적용한다. `R=0`이나 `O` 감소로 원금 상환을 추론하지 않는다. 해제가 보관액을 0으로 만들면 보관액 조건 하나만 충족한다. 결과는 `ADVISORY_ONLY`이며 상태가 바뀌면 다시 평가한다. 이 판정은 pinned FSM 종결이나 실제 자금 이동을 실행하지 않는다.

### 3.7 `overlay_entry_schema_and_digest_effect`

`INTEREST_WAIVER`와 `UNAPPLIED_CASH_RELEASE`는 모두 최상위에 **`overlay_id`, `after_journal_index`, `sim_day`, `kind`, `payload`**를 갖는다. `after_journal_index`는 게시가 근거한 확정 명령 journal의 위치다. `sim_day`는 게시 당시의 현재 논리 일이며 `payload.effective_sim_day`와 일치해야 한다. 종류별 payload를 처리하기 전에 envelope의 필수 필드를 검사한다. journal 위치가 유효하지 않거나 일자가 맞지 않으면 append를 거절한다. 재생은 기록된 위치와 일자에 효과를 적용하고, 동일 위치의 엔트리는 확정 append 순서를 따른다.

payload는 작업 ID, 대상, 금액, 사유, 근거·승인, 기준 overlay digest, 정책 참조·digest 및 `funds_executed=false`를 포함한다. 상각 후 면제에는 개시 대사 근거, 사건 순서, 보조 규칙 버전, `C/D/O/R` 전후값을 결속한다. 신규 게시의 승인·한도·예약·digest 검증과 상태 반영·append는 원자적이다. 회수와 면제가 경합하면 먼저 확정된 효과를 반영한 뒤 다른 요청을 다시 평가한다.

같은 작업 ID와 내용의 재요청은 최초 결과를 반환한다. 내용이 다르면 충돌이다. 응답이 유실되면 해당 ID를 조회한다. journal 위치와 논리 일을 포함한 엔트리 전체, 정책 digest와 재생 근거를 overlay digest 및 export에 포함한다. 벽시계와 프로세스 ID는 제외한다.

### 3.8 `tax_and_accounting_working_assumption`

투영에 총발생액, 실제 배분, 비현금 이자 면제, 상각, 상각 후 보조 귀속 및 순잔액을 구분해 표시한다. 상각 후 면제로 같은 손실을 이중 인식하지 않는다. 보관액은 보관 의무로 취급하고 해제를 수익이나 회수에 포함하지 않는다. 계정·분개, 세무 처리·인정일, 법적 채무 소멸 효력은 전문 검토 근거가 없어 각각 `UNDETERMINED`다. §4에 검토 대상을 지정한다.

### 3.9 `agent_lane_proposal_kinds`

로컬 에이전트는 `PROPOSE_INTEREST_WAIVER`, `PROPOSE_UNAPPLIED_CASH_RELEASE`, `REQUEST_ADVISORY_CLOSE_REVIEW`만 제출할 수 있다. 각 초안에 대상 범위, 상태·정책 digest, 계산 근거를 결속한다. 오래된 초안은 재계산한다. 승인 인원은 §3.3과 §3.5의 운영 주체로 충족한다. 에이전트 권한은 제안 제출까지다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "waiver-writeoff-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-11-20",
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
      "date": "2026-11-20",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "An explicit command records the amount and evidence of each waiver.",
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
            "cut": "ORIGINAL_WRITEOFF_BEFORE_FIRST_POST_WRITEOFF_EVENT",
            "P": "INDEPENDENT_OUTSTANDING_PRINCIPAL_AT_WRITEOFF",
            "C": "UNPAID_CONTRACT_INTEREST_NET_OF_CONFIRMED_ALLOCATIONS_AND_PRIOR_VALID_WAIVERS_ONCE",
            "D": "UNPAID_OVERDUE_INTEREST_NET_OF_CONFIRMED_ALLOCATIONS_AND_PRIOR_VALID_WAIVERS_ONCE",
            "O": "P",
            "R": "P+C+D",
            "snapshot_cap_check": "REQUIRE_SNAPSHOT_RESIDUAL_RECOVERY_CAP_EQUALS_P+C+D",
            "on_mismatch": "NOT_BOUND_REJECT_SNAPSHOT_BLOCK_RECOVERY_WAIVER_AND_ADVISORY_CLOSE"
          },
          "invariant": "R=C+D+O; ALL_NONNEGATIVE_INTEGER_KRW",
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
      "date": "2026-11-20",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Independent opening principal prevents a gross recovery cap from reintroducing waived interest.",
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
      "date": "2026-11-20",
      "cap_rows": ["CAP-04", "CAP-09"],
      "rationale": "Distinct subjects and a cumulative threshold cover self-approval and split proposals.",
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
      "date": "2026-11-20",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Canonical limits bound cumulative relief across advances and beneficiaries.",
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
      "date": "2026-11-20",
      "cap_rows": ["CAP-02", "CAP-05"],
      "rationale": "Source-lot reconciliation and repayment priority determine the releasable balance.",
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
      "date": "2026-11-20",
      "cap_rows": ["CAP-01", "CAP-04", "CAP-20"],
      "rationale": "A valid waiver can satisfy the interest condition while principal requires independent evidence.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "overlay_entry_schema_and_digest_effect": {
      "status": "ADOPTED",
      "value": {
        "envelope": ["overlay_id", "after_journal_index", "sim_day", "kind", "payload"],
        "kinds": ["INTEREST_WAIVER", "UNAPPLIED_CASH_RELEASE"],
        "after_journal_index": "CONFIRMED_COMMAND_JOURNAL_POSITION_AT_POSTING",
        "sim_day": "CURRENT_SIM_DAY_AT_POSTING_EQUALS_PAYLOAD_EFFECTIVE_SIM_DAY",
        "invalid_anchor_or_day": "REJECT_BEFORE_APPEND",
        "common_payload": ["schema_version", "operation_id", "effective_sim_day", "expected_overlay_digest", "target_ids", "amounts_krw", "reason_code", "evidence_refs", "proposer_id", "approver_ids", "approval_binding", "policy_refs", "policy_digest", "funds_executed"],
        "post_writeoff_evidence": ["writeoff_snapshot_ref", "opening_principal_and_net_interest_evidence_ref", "attribution_rule_version", "confirmed_event_order_ref", "balances_C_D_O_R_before", "balances_C_D_O_R_after"],
        "posting": "ATOMIC_BALANCE_CAP_APPROVAL_DIGEST_RESERVATION_VALIDATION_AND_APPEND",
        "concurrent_recovery_and_waiver": "SERIALIZE_WITH_EXPECTED_DIGEST_AND_RECHECK_ADJUSTED_RESIDUAL",
        "same_operation_same_content": "IMMUTABLE_FIRST_RESULT",
        "same_operation_different_content": "CONFLICT",
        "lost_response": "LOOKUP_ONLY_UNTIL_RESOLVED",
        "digest_effect": "INCLUDE_ENVELOPE_EFFECT_POLICY_DIGEST_AND_REPLAYABLE_EVIDENCE_IN_OVERLAY_AND_EXPORT",
        "exclude_from_digest": ["WALL_CLOCK", "PROCESS_ID"],
        "pinned_fsm_digest": "UNCHANGED",
        "existing_goldens": "UNCHANGED",
        "reversal_command_v1": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-20",
      "cap_rows": ["CAP-13", "CAP-14", "CAP-15"],
      "rationale": "Both entry kinds bind their effect to a journal position and a simulation day.",
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
            "reason": "Reviewed account mappings and entries are unavailable."
          },
          "tax_treatment_and_dates": {
            "status": "UNDETERMINED",
            "value": null,
            "target": "TAX_PROFESSIONAL_REVIEW",
            "reason": "Reviewed tax treatment and recognition dates are unavailable."
          },
          "legal_discharge_effect": {
            "status": "UNDETERMINED",
            "value": null,
            "target": "LEGAL_PROFESSIONAL_REVIEW",
            "reason": "Enforceable discharge requires legal review."
          }
        }
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-20",
      "cap_rows": ["CAP-04", "CAP-20"],
      "rationale": "Separate simulation effects while reserving professional judgments for review.",
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
      "date": "2026-11-20",
      "cap_rows": ["CAP-09", "CAP-20"],
      "rationale": "Scoped proposals carry calculation evidence and leave posting to the authorized operators.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| 기준 | 근거·검증 범위 |
|---|---|
| 결정 완전성 | §4의 단일 JSON 블록을 메모리에서 파싱했다. 채택 9건에 값·제공자·ISO 날짜·잠정 표시가 있고, 전문 판단 3건에 `null` 값·사유·검토 대상이 있다. |
| 개시 한도 대사 | §3.2와 §4는 독립적으로 산출한 `P+C+D`와 snapshot 한도의 일치를 요구한다. 10원 면제 사례의 기대 결과는 110원 통과, 120원 거절이다. |
| 재생 위치 | §3.7과 §4는 두 종류 모두에 최상위 `after_journal_index`와 `sim_day`를 요구한다. |
| 종결·실행 경계 | §3.6에 전용 재검토 경로와 자문 범위를 명시했다. `funds_executed=false`, production `NOT_AUTHORIZED`다. |
| 저장본 수용 | supervisor가 `docs/decisions/CAPITAL_WAIVER_WRITEOFF.md`를 저장한 뒤 별도 CI에서 `python3 scripts/decision_ledger.py`의 노드 상태 `PROVISIONAL_PRODUCT_DECISION` 및 종료 코드 0, `python3 -m unittest tests.test_decisions tests.test_decisions_surface`의 종료 코드 0을 확인한다. 이번 제출의 검증은 메모리 단위다. |

## 6. Open risks

- 상각 시점 원금, 순이자 또는 확정 사건 순서를 복원할 수 없는 이력에서는 회수 가능액과 종결 적격성을 확정할 수 없다.
- 견적·예약·게시가 서로 다른 회수 한도를 읽으면 면제한 이자를 다시 청구할 수 있다. 아홉 바인딩의 리뷰 상태는 `PENDING_CONSUMER`다.

## 7. 후속 작업

1. 소비 노드는 110원·120원 개시 사례, 같은 날 회수와 면제의 순서, 두 종류 각각의 최상위 필드 누락과 일자 불일치를 재생 검증한다.
2. 해제와 상환 배분의 경합, 임계값 일치·초과·분할, 재전송, 원금이 남은 종결 요청을 검증한다. 저장본의 문서 등록은 `python3 scripts/docs_surface.py --check`로 확인한다.
3. 회계·세무·법무 검토 결과는 지정 target별로 기록한다. upstream 채택 판정에는 별도 영수증이 필요하다.
