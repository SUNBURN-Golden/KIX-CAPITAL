# Capital 이자 면제·미적용 현금 해제·종결 게이트 재검토 결정

> **PROVISIONAL PRODUCT DECISION**
>
> 결정자 표기(위임 메타데이터): **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**
>
> 위임 원문 (2026-10-08 18:25 KST, JunTae Park): "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해."
>
> 결정일: **2026-10-26** · KIX-CAPITAL main **`aab0a73`** · kix-protocol **`22d05a0`** (supervisor가 준 기준이며, 이 결정자가 Git으로 다시 검증했다고 주장하지 않음).
>
> 이 결정은 **시뮬레이션·제품 설계 전용**이다. 실자금 이동, 청약, 외부 지급, 법적 채무 소멸을 승인하지 않는다. **`funds_executed:false`**와 production **`NOT_AUTHORIZED`**는 그대로 유지한다. 회계·세무·법무 내용은 **`WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW`**이다. 소비 구현은 별도 노드가 맡는다. upstream 채택·완료·SEMANTIC_CONFORMANCE는 주장하지 않는다.

## 1. 결정 요약

| item | 결정 | CAP rows | consumer |
|---|---|---|---|
| `waiver_command_existence` | ADOPTED. 명시적 `waive_interest` 명령을 둔다. 상각 후에도 사용할 수 있다 | CAP-01, CAP-04 | waiver overlay |
| `waiver_scope_interest_only_vs_principal` | ADOPTED. 미납 약정이자·연체이자만 면제한다. 상각 후에는 보조 귀속과 잔여 회수 한도를 같은 원자 단위에서 함께 줄인다 | CAP-01, CAP-04 | 이자·회수 투영 |
| `waiver_authority_and_two_person_threshold` | ADOPTED. 운영자 제안과 별도 검토자 승인을 요구한다. 임계 초과 시 별도 금융책임자를 추가한다 | CAP-04, CAP-09 | 승인 검증 |
| `waiver_caps_and_sim_day_recording` | ADOPTED. 적격 이자의 100% 이내로 한정하고, 리셋 없는 누적 예산을 적용하며, 현재 논리 일로 기록한다 | CAP-01, CAP-04 | cap·재생 |
| `unapplied_cash_release_or_refund` | ADOPTED. 대사된 원천 lot을 시뮬레이션으로만 반환한다 | CAP-02, CAP-05 | 보관액 해제 |
| `close_gate_reconsideration` | ADOPTED. 유효한 면제로 순이자 0을 만들 수 있다. 다른 차단 조건은 모두 유지한다 | CAP-01, CAP-04, CAP-20 | advisory close |
| `overlay_entry_schema_and_digest_effect` | ADOPTED. append-only·원자성·멱등성을 지키고, 보조 귀속 근거도 digest에 결속한다 | CAP-13, CAP-14, CAP-15 | 저장·export |
| `tax_and_accounting_working_assumption` | ADOPTED. 면제·회수·상각을 분리한다. 전문 판단 세 칸은 UNDETERMINED로 둔다 | CAP-04, CAP-20 | 회계 설명·투영 |
| `agent_lane_proposal_kinds` | ADOPTED. 세 종류의 제안만 허용한다. 승인·게시·지급은 금지한다 | CAP-09, CAP-20 | agent proposal lane |

CAP 매핑은 허용된 선행 노트의 사용례를 따랐다. CAP 정본 전체를 확인했다는 뜻은 아니다.

## 2. KIX 비전 연결

- `docs/CAPITAL_REQUIREMENTS_KO.md`: 핀의 범위와 현재 구현 상태를 구분한다. 결정 노트는 실행 구속이 아니며, 설계 후보를 구현 완료로 옮기지 않는다.
- `docs/SEAMS.md`: 로컬 정책 채택은 upstream 계약 채택이 아니다. 이 결정은 어떤 포트의 `NOT_BOUND`도 해제하지 않는다.
- `docs/VALIDATION.md`: 로컬 검증 결과에서 은행 exactly-once, 분산 내구성, 법적 적합성을 추론하지 않는다.
- `docs/decisions/CAPITAL_DEFAULT_RECOVERY.md`: 가속 재기준과 부도 명령일 기준 상각을 그대로 유지한다. **상각 후 회수는 단일 잔여채권에 배분 없이 기록한다**는 규칙도 유지한다. 이 결정은 면제 적격성 판단에만 쓰는 보조 귀속을 덧붙인다.
- `docs/decisions/CAPITAL_CLAIM_SLICE_REGISTRY.md`: 한도 숫자를 복사하지 않고 `CAPITAL-TERMS-V1` 필드명으로 참조한다. 면제로 원금 한도나 차입기초를 복원하지 않는다.
- `docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md`: 합성 차트(`SIMULATION_FIXED_V1`)에서 회계·세무 입장을 추론하지 않는다.

`CAPITAL_REPAYMENT_POSTING.md`와 `CAPITAL_FINANCIAL_TERMS.md`는 선행 정본이지만 허용 경로 밖이어서 직접 읽지 않았다. 이름·숫자가 서로 다르면 선행 정본이 이긴다. 이 노트가 정하는 것은 면제 적격성 규칙과 잔여 회수 한도 조정뿐이며, 둘 다 이 결정이 명시적으로 추가하는 정책이다. 바인딩이 부족하면 해당 소비 경로만 `NOT_BOUND`가 된다. 이미 채택된 정책이 `DECISION_REQUIRED`로 돌아가지는 않는다.

## 3. 항목별 결정

### 3.1 `waiver_command_existence`

**`waive_interest`를 신설한다.** 정상·연체·부도 상태의 열린 선지급과, 회계상 상각 이후의 열린 선지급에 쓸 수 있다.

- 약정이자와 연체이자 면제액을 따로 지정한다. 각 금액은 0 이상의 KRW 정수이고 합계는 양수여야 한다.
- 잔액 초과, 소수, 음수는 거절한다.
- 사유, 기준 digest, 승인 증거가 필수다.

다음은 금지한다. 자동 면제, 과거 영수증 수정, 종결된 기록에 대한 게시, V1의 면제 취소. 명령이 성공해도 시뮬레이션상의 이자청구가 줄어든다는 뜻뿐이다.

### 3.2 `waiver_scope_interest_only_vs_principal`

면제 대상은 현재 `sim_day`까지 발생·확정된 미납 약정이자와 미납 연체이자다. 원금, 수수료, 미래 이자, 제3자 보호채무, 반환 의무는 제외한다.

**상각 전.** 버킷별 적격 잔액은 다음과 같다. 확정 발생액에서 그 버킷에 실제로 확정 배분된 상환·회수액을 빼고, 이전의 유효 면제액을 뺀다. 각 금액은 한 번씩만 차감한다. 상각 자체는 면제가 아니다.

**상각 후.** 실제 회수는 선행 결정대로 단일 잔여채권에 배분 없이 기록한다. 그와 별도로 보조 계산 `POST_WRITEOFF_WAIVER_ATTRIBUTION_V1`을 둔다. 이 계산은 면제 적격성과 잔여청구 대사에만 쓴다. 실제 상환 배분도, 회계 배분도, 원금 상환의 증거도 아니다.

상각 사건 직후의 정본 잔여채권으로 네 값을 초기화한다. 상각 전의 확정 배분과 유효 면제는 이미 차감된 상태다.

- `C`: 미납 약정이자
- `D`: 미납 연체이자
- `R`: 권위 있는 잔여 회수 한도
- `O`: 원금 등 나머지 잔여채권, `O = R − C − D`

불변식은 `R = C + D + O`이고 네 값 모두 0 이상이다. 장부가액 0을 `R = 0`으로 읽지 않는다. 구성을 대사할 수 없으면 추측하거나 0으로 보정하지 않는다. 그 경로는 `NOT_BOUND`로 거절한다.

**회수 귀속.** 확정된 회수액 `x`마다 먼저 `0 < x ≤ R`를 검증한다. 그다음 연체이자 → 약정이자 → 기타 잔여채권 순서로 보조 귀속한다.

- `aD = min(x, D)`
- `aC = min(x − aD, C)`
- `aO = x − aD − aC`

결과로 `(D, C, O, R)`는 `(D − aD, C − aC, O − aO, R − x)`가 된다.

**면제.** 면제액 `(wC, wD)`는 `0 ≤ wC ≤ C`, `0 ≤ wD ≤ D`, `wC + wD > 0`을 만족해야 한다. 성공하면 같은 원자 단위에서 `C −= wC`, `D −= wD`, `R −= wC + wD`가 된다. `O`는 바뀌지 않는다.

- 이후의 모든 회수 견적·예약·게시는 줄어든 `R`을 쓴다. 기존 승인과 견적은 무효가 된다.
- 따라서 이미 회수에 귀속된 이자는 면제할 수 없고, 면제된 이자는 다시 회수할 수 없다.

**재생.** 최초 상각 snapshot부터 확정 append 순서로 재생한다. 같은 날의 사건도 커밋 순서를 따른다. 과거 회수는 원본을 수정하지 않고 재생한다. 순서나 구성의 누락, 초과 회수, 불변식 위반은 `NOT_BOUND`이며 대사 차단 사유가 된다.

상각 후 추가 발생은 기존 정책이 허용하고 잔여채권에 포함하는 경우에만 반영한다. 그때 해당 버킷과 `R`을 같은 원자 단위에서 함께 늘린다.

**검증 예시** (금융 조건이 아니다). `C=80, D=20, O=1000, R=1100`에서 시작한다.

1. 회수 50 → `D` 20, `C` 30에 귀속되어 `C=50, D=0, R=1050`이 된다.
2. 약정이자 60 면제 → `C=50`을 넘으므로 거절한다.
3. 약정이자 40 면제 → `C=10, R=1010`이 된다.
4. 회수 1015 → `R=1010`을 넘으므로 거절한다.

### 3.3 `waiver_authority_and_two_person_threshold`

- 모든 면제는 `SIM_OPERATOR`의 제안과, 그와 다른 주체인 `SIM_FINANCE_REVIEWER`의 승인을 요구한다. 같은 주체가 역할만 바꾼 것은 분리 승인으로 인정하지 않는다.
- 동일 수익자의 당일 누적 면제액에 이번 제안액을 더한 값이 `CAPITAL-TERMS-V1.underwriting_depth.two_person_threshold_krw`를 **초과**하면, 앞의 두 주체와 다른 `SIM_FINANCE_OWNER`를 추가로 요구한다. 나눠서 제안해도 누적으로 계산한다.
- 승인은 대상, 버킷별 금액, 사유, 현재 일, 상태 digest, 정책 digest에 결속한다. 상태가 바뀌면 다시 승인받아야 한다.
- 합성 역할은 실제 인증이나 은행 권한이 아니다.

### 3.4 `waiver_caps_and_sim_day_recording`

- 버킷별 적격 잔액의 100%까지 면제할 수 있다.
- 이와 별도로 누적 면제 예산을 둔다. 선지급·수익자·포트폴리오 예산은 각각 `underwriting_depth.single_advance_cap_krw`, `beneficiary_aggregate_cap_krw`, `portfolio_cap_krw`를 참조한다. 기존 인출 cap의 의미는 바꾸지 않는다.
- 누적액은 보존된 전체 이력 기준이다. 종결, 일자 변경, 상각, 회수로 리셋되지 않는다.
- 수익자 귀속은 선지급 발생 당시의 바인딩을 따른다.
- `effective_sim_day`는 게시 시점의 현재 논리 일이다. 소급일·미래일은 거절하고, 이율이나 가속일을 다시 쓰는 요청도 거절한다.
- 참조값이 불명확하면 `NOT_BOUND`로 거절한다.

### 3.5 `unapplied_cash_release_or_refund`

**`release_unapplied_cash`를 신설한다.** 확정된 원천 영수증과 대사된 보관 lot에 대해, 가용 잔액 안에서 부분 시뮬레이션 반환을 허용한다. 수취인은 동일한 합성 원송금자로 한정한다.

- 다음 중 하나라도 있으면 해제하지 않는다: 귀속 불명, 분쟁, 반환 제한, 보호채무, UNKNOWN, 진행 중 예약.
- 같은 범위에서 확정 상환 배분이 가능하면 기존 repayment-posting 대사를 먼저 수행한다.
- 면제가 반환액을 자동으로 만들지 않는다.

승인 구조는 §3.3과 같다. 운영자와 별도 검토자가 승인하고, 원송금자의 당일 누적 해제액이 같은 2인 임계값을 초과하면 별도 금융책임자를 추가한다. 보관액 감소와 `SIMULATED_RELEASE` 기록은 원자적으로 함께 남기며 `funds_executed=false`다. 실제 환불 API, 은행 연결, 지급 완료 표시는 허용하지 않는다.

### 3.6 `close_gate_reconsideration`

**`CAPITAL_REPAYMENT_POSTING`의 close-gate 규칙은 이 결정을 통해서만 재검토할 수 있다.** 이번 변경은 이자 조건에만 적용된다.

- 상각 전: 발생액에서 확정 배분과 유효 면제를 뺀 값이 0이면 이자 조건을 충족한다.
- 상각 후: §3.2로 재생한 `C + D`가 0이면 충족한다. 보조 귀속을 실제 배분과 중복으로 빼지 않는다.

기존 차단 조건은 모두 유지한다: 원금 잔액, 기타 채무, 열린 환불·분쟁, 보관액, UNKNOWN, 미완료 승인·예약, 상각 후 대사 실패. `R=0`이나 보조 `O`의 감소만으로 원금 상환을 추론하지 않는다.

해제로 보관액이 0이 되면 보관액 조건 하나만 충족한다. 평가 결과는 `ADVISORY_ONLY`이며, pinned FSM 종결이나 실제 채무 소멸을 실행하지 않는다. 상태가 바뀌면 이전 평가는 무효가 된다.

### 3.7 `overlay_entry_schema_and_digest_effect`

- 엔트리 형태는 `overlay_id`/`kind`/`payload`다. 새 kind는 `INTEREST_WAIVER`와 `UNAPPLIED_CASH_RELEASE` 두 가지다.
- payload에는 operation, 현재 일, 대상, 금액, 사유, 근거, 승인, 기준 overlay digest, 정책 참조와 digest, `funds_executed:false`를 넣는다.
- 상각 후 면제는 추가로 상각 snapshot 참조, 보조 규칙 버전, 사건 순서 근거, `C/D/O/R`의 전후 값을 결속한다.
- 검증, 승인, cap, 잔여 한도, 예약 충돌 확인과 게시는 하나의 원자 단위로 처리한다. 같은 기준 digest를 놓고 회수와 면제가 동시에 들어오면 하나만 성공한다.
- 같은 operation에 같은 내용이면 최초 결과를 돌려준다. 같은 operation에 다른 내용이면 충돌이다. 응답이 유실되면 조회로만 복구한다.
- 효과 엔트리, 정책 digest, 보조 근거는 overlay digest와 export에 포함한다. 벽시계와 프로세스 ID는 제외한다.
- pinned FSM digest와 기존 golden은 변경하지 않는다.

### 3.8 `tax_and_accounting_working_assumption`

- 면제는 비현금 이자청구 감소다. 회수나 회계상 상각과 구분한다.
- 투영은 총발생, 실제 배분, 면제, 상각 후 보조 귀속, 순잔액을 서로 구별해서 보여준다.
- 상각 후 면제로 손실을 이중 인식하지 않는다. 보조 귀속 순서는 수익 인식 순서가 아니다.
- 보관액은 보관 의무이며, 해제는 수익도 회수도 아니다.

계정 코드·분개, 세무 처리·인정일, 법적 면제 효력은 `UNDETERMINED`, `value:null`로 둔다. target은 각각 회계·세무·법무 전문 검토다. 합성 차트와 기존 합계는 변경하지 않는다.

### 3.9 `agent_lane_proposal_kinds`

`PROPOSE_INTEREST_WAIVER`, `PROPOSE_UNAPPLIED_CASH_RELEASE`, `REQUEST_ADVISORY_CLOSE_REVIEW` 세 종류만 채택한다.

- 에이전트는 제한된 대상과 상태·정책 digest에 결속된 초안과 계산 근거만 제출한다.
- 에이전트는 승인자 수에 포함되지 않는다. 게시, 지급, 자동 종결 권한도 없다.
- stale 제안은 다시 계산한다.
- upstream AI 위임 계약의 채택을 주장하지 않는다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "waiver-writeoff-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-10-26",
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
        "reversal_command_v1": false,
        "amounts": "NONNEGATIVE_INTEGER_KRW_BUCKETS_WITH_POSITIVE_SUM"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-26",
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
            "C": "UNPAID_CONTRACT_INTEREST_IN_WRITEOFF_RESIDUAL_NET_OF_PRIOR_ALLOCATIONS_AND_WAIVERS",
            "D": "UNPAID_OVERDUE_INTEREST_IN_WRITEOFF_RESIDUAL_NET_OF_PRIOR_ALLOCATIONS_AND_WAIVERS",
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
      "date": "2026-10-26",
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
      "date": "2026-10-26",
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
      "date": "2026-10-26",
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
      "date": "2026-10-26",
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
        "funds_executed": false,
        "production": "NOT_AUTHORIZED",
        "state_change": "INVALIDATE_PRIOR_EVALUATION"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-26",
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
      "date": "2026-10-26",
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
      "date": "2026-10-26",
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
      "date": "2026-10-26",
      "cap_rows": ["CAP-09", "CAP-20"],
      "rationale": "Bounded proposals do not grant financial execution authority.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

- `docs/decisions/CAPITAL_WAIVER_WRITEOFF.md`는 단일 `capital-decision-v1` 블록에 아홉 항목을 모두 담는다. 각 ADOPTED 항목에는 `provided_by`, ISO 날짜(2026-10-26), 값이 있다. 전문 판단 세 칸은 `value:null`이고 이름 있는 target이 있다.
- §3.6과 `close_gate_reconsideration`에 다음을 기록했다: repayment-posting close-gate는 이 결정을 통해서만 재검토할 수 있다는 점, `funds_executed:false`, production `NOT_AUTHORIZED`.
- `python3 scripts/decision_ledger.py`와 `python3 -m unittest tests.test_decisions tests.test_decisions_surface`는 이번 라운드에서 **실행하지 않았다.** supervisor가 문서를 저장한 뒤 종료 코드 0을 확인해야 한다.
- **리뷰 [blocking] `tests/test_coa_candidate.py:214` 대응.** 이 변경은 결정 문서의 내용이 아니다. 읽기 전용 `git log`/`git diff`로 확인하니 브랜치의 merge commit `3ef782c`에서 들어왔다. 이 결정자의 수정 허용 범위(이 노트, `tests/decision_bindings.json`, `tests/vectors/pack/`) 밖이어서 여기서 되돌리지 않았다. **supervisor는 `tests/test_coa_candidate.py`를 `origin/main` 바이트로 되돌린 뒤 이 노트를 저장해야 한다.** 새 노트 추가를 허용하는 호환 수정은 별도 PR로 보낸다. 다만 main의 guard는 추가된 `docs/decisions/*` 파일도 diff로 잡을 수 있다. 그래서 되돌린 뒤 `tests.test_coa_candidate`가 실패하면, 그것은 이 노트의 결함이 아니라 별도 PR로 해결할 main 쪽 guard 문제다.

## 6. Open risks

- 상각 시점의 구성이나 사건 순서가 없는 이력은 보조 재생을 안전하게 할 수 없다. 그런 경로는 대사 전까지 `NOT_BOUND`다.
- 회수 소비자가 조정된 `R`을 쓰지 않으면 면제 후 과다 회수가 생길 수 있다. 면제 경로와 회수 경로를 함께 연결해야 한다.
- 합성 역할과 로컬 원자성은 실제 인증, 분산 내구성, 법적 효력을 증명하지 않는다. V1에 취소 명령이 없어서 생기는 운영 복구 한계도 남는다.
- COA guard 호환 수정이 별도 PR로 분리되기 전까지, 결정 노트를 추가하는 브랜치에서는 `tests.test_coa_candidate`가 실패할 수 있다.

## 7. 후속 작업

1. supervisor: `tests/test_coa_candidate.py`를 main 바이트로 되돌린다. 이 노트를 저장하고 원장·표면 검증을 수행한다. COA guard 호환 수정은 별도 PR로 낸다. 이 결정자는 commit·push·게시를 하지 않는다.
2. 소비 노드: 다음을 함께 구현한다.
   - 정본 필드 바인딩
   - 상각 snapshot 대사와 보조 재생
   - 면제 경로와 모든 회수 경로의 조정된 한도
   - `release_unapplied_cash`
   - advisory close 평가
3. 검증 벡터:
   - §3.2 예시
   - 회수→면제, 면제→회수 순서
   - 같은 날 사건 순서
   - 동시 게시와 재전송
   - 누락 이력과 대사 실패
   - 종결 차단
4. 회계·세무·법무 전문 검토와 upstream 채택 영수증은 별도 경로로 확보한다.
