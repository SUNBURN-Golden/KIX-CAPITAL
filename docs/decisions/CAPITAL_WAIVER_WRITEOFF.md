# Capital 이자 면제·미적용 현금 해제·종결 게이트 재검토 결정

> **PROVISIONAL PRODUCT DECISION**
>
> 결정자 표기(위임 메타데이터): **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**
>
> 결정일: **2026-10-20** · KIX-CAPITAL main **`844d6e2`** · kix-protocol **`6f75594`** — supervisor 제공 기준이며 이 세션에서 Git으로 재검증하지 않았다.
>
> 시뮬레이션·제품 설계만을 위한 잠정 결정이다. 실자금·청약·외부 지급·법적 채무 소멸을 승인하지 않는다. **`funds_executed: false`**, production **`NOT_AUTHORIZED`**를 유지한다. 회계·세무·법무는 **`WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW`**다. 소비 구현은 별도 노드이며 upstream 채택·완료·SEMANTIC_CONFORMANCE를 주장하지 않는다.

## 1. 결정 요약

| item | 결정 | CAP rows | consumer |
|---|---|---|---|
| `waiver_command_existence` | ADOPTED — 명시적 `waive_interest` 오버레이 명령 신설. 자동 면제·과거 기록 수정 없음 | CAP-01, CAP-04 | 후속 waiver 오버레이 구현 |
| `waiver_scope_interest_only_vs_principal` | ADOPTED — 확정 발생한 미납 약정·연체이자만 면제. 원금·수수료·미래이자 제외 | CAP-01, CAP-04 | 이자 계산·회수 투영 |
| `waiver_authority_and_two_person_threshold` | ADOPTED — 운영자 제안과 별도 검토자 승인. 기존 2인 임계 초과 시 금융책임자 추가 | CAP-04, CAP-09 | 승인 검증·명령 접수 |
| `waiver_caps_and_sim_day_recording` | ADOPTED — 잔여 미납이자 100% 이내, 선지급·수익자·포트폴리오 누적 cap 적용, 현재 논리 일만 기록 | CAP-01, CAP-04 | cap·논리 시계·재생 |
| `unapplied_cash_release_or_refund` | ADOPTED — 출처별 보관액의 시뮬레이션 반환 경로 신설. 실제 환불 없음 | CAP-02, CAP-05 | 미적용 현금 대사·해제 |
| `close_gate_reconsideration` | ADOPTED — 잔여 순이자 0을 면제 기록으로 충족 가능. 원금·보관액·UNKNOWN 등 기존 차단 유지 | CAP-01, CAP-04, CAP-20 | advisory close evaluator |
| `overlay_entry_schema_and_digest_effect` | ADOPTED — append-only `overlay_id/kind/payload`, 원자적 반영·중복 방지·오버레이 digest 포함 | CAP-13, CAP-14, CAP-15 | 오버레이 저장·export |
| `tax_and_accounting_working_assumption` | ADOPTED — 면제와 회계상 상각 분리, 보관액 해제는 수익 아님. 전문 검토 전 작업 가정 | CAP-04, CAP-20 | 회계 투영·설명 표면 |
| `agent_lane_proposal_kinds` | ADOPTED — 세 가지 로컬 제안 종류만 허용. 에이전트 승인·게시·지급 금지 | CAP-09, CAP-20 | agent proposal lane |

CAP 매핑은 제공된 선행 노트의 사용례를 따른다. 범위 밖 CAP 정본 전체를 확인했다는 주장은 아니다.

## 2. KIX 비전 연결

- `docs/CAPITAL_REQUIREMENTS_KO.md`의 제공 발췌는 원 요청·관측·금전 의무·실행의 분리와 Protocol·Commerce 비수정을 요구한다. 면제는 관측 현금이나 원금 회수로 위장하지 않고 별도 오버레이 사실로 남긴다.
- `docs/SEAMS.md`의 제공 발췌대로 로컬 대역과 실제 upstream 채택은 다르다. 이 결정은 포트의 `NOT_BOUND`를 해제하지 않는다.
- `docs/VALIDATION.md`의 제공 발췌는 로컬 검증에서 은행 exactly-once·내구성·법적 적합성을 추론하지 못하게 한다. 해제 영수증도 실제 송금 영수증이 아니다.
- `docs/decisions/CAPITAL_DEFAULT_RECOVERY.md`의 제공 발췌에 있는 가속 재기준·부도 명령일 기준 상각 정책을 유지한다. 이자 면제는 그 날짜·이율을 다시 정하는 수단이 아니다.
- `docs/decisions/CAPITAL_CLAIM_SLICE_REGISTRY.md` 및 직접 읽은 `docs/decisions/CAPITAL_DEMO_BOOK.md`의 cap 출처 규칙을 따른다. 금액 상수는 복사하지 않고 `CAPITAL-TERMS-V1` 필드를 참조한다. 원금 회수 없는 한 공유 한도나 차입기초를 면제로 복원하지 않는다.
- `docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md`의 제공 발췌에 따라 합성 차트에서 회계·세무 입장을 추론하지 않는다.
- 직접 읽은 `/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md`의 기록·재생 분리 원칙에 따라 과거 사실 재생은 새로운 외부 실행 권한이 아니다. timeout이나 침묵으로 현금이 반환됐다고 간주하지 않는다.

읽기 한계: `CAPITAL_REPAYMENT_POSTING.md`와 `CAPITAL_FINANCIAL_TERMS.md`는 선행 결정으로 지정됐지만 허용 경로에 없으므로 열지 않았다. 아래 규칙은 기존 정책을 확인했다고 가장하지 않는 **명시적 추가 정책**이다. 기존 계약의 세부 조건·정확한 필드 경로가 부족하면 해당 바인딩만 `NOT_BOUND`로 남기며, 이 노트가 결정한 정책 자체를 `DECISION_REQUIRED`로 되돌리지 않는다.

## 3. 항목별 결정

### 3.1 `waiver_command_existence`

**`waive_interest`를 신설한다.** 선지급별 명시적 금액과 면제 사유, 기준 오버레이 digest, 승인 증거를 받는다. 정상·연체·부도·회계상 상각 이후에도 아직 남은 적격 이자를 대상으로 할 수 있다. 종결된 기록에는 새 명령을 게시하지 않는다.

금액은 양의 KRW 정수다. 잔여 이자가 없으면 거절하며 음수·소수·초과액을 자동 보정하지 않는다. 자동 연령 기반 면제, 숨은 반올림 면제, 기존 상환 영수증 수정은 금지한다. 명령 성공은 오버레이 면제 사실만 의미한다.

### 3.2 `waiver_scope_interest_only_vs_principal`

면제 대상은 현재 `sim_day`까지 발생·확정된 **미납 약정이자와 연체이자**다. 명령은 두 버킷의 금액을 각각 지정하며 합계만 입력해 임의 배분하지 않는다.

각 버킷의 적격 잔액은 발생액에서 확정 상환·회수 배분과 이전 면제를 차감한 값이다. 중복 차감을 막기 위해 실제 원장 사건을 기준으로 계산한다. 회계상 상각은 별도 회수권 잔액과 구별하며, 상각액을 자동 면제하거나 이미 소멸한 권리를 다시 면제하지 않는다.

원금, 수수료, 보호된 제3자 채무, 반환 의무, 미래 미발생 이자는 제외한다. 원금 상각은 선행 default-recovery 정책을 유지한다. 면제 이후에도 미상환 원금에 대한 미래 이자는 기존 조건대로 발생한다. 면제로 원금·원금 익스포저·준비금 해제·담보권 반환을 만들지 않는다.

### 3.3 `waiver_authority_and_two_person_threshold`

모든 면제는 합성 역할 `SIM_OPERATOR`가 제안하고 **다른 주체** `SIM_FINANCE_REVIEWER`가 승인한다. 자기 승인과 동일 주체의 역할 바꿔 승인은 금지한다.

분할 회피 방지를 위해 동일 수익자의 현재 논리 일 누적 면제액에 제안액을 더한 값이 `CAPITAL-TERMS-V1 underwriting_depth.two_person_threshold_krw`를 **초과**하면 제안자·검토자와 다른 `SIM_FINANCE_OWNER`의 추가 승인을 요구한다. 임계값 이하여도 기본 2인 통제는 유지한다.

승인은 대상·버킷별 금액·사유·기준 digest·현재 일에 묶인다. 관련 잔액이나 승인이 의존한 정책이 바뀌면 재승인한다. 합성 actor 문자열은 인증이 아니며 실제 IAM이나 은행 권한의 채택을 뜻하지 않는다.

### 3.4 `waiver_caps_and_sim_day_recording`

버킷별 잔여 적격 이자의 **100%까지** 면제할 수 있다. 추가로 누적 면제액에 다음 상한을 적용한다.

- 선지급별: `underwriting_depth.single_advance_cap_krw`
- 수익자별: `underwriting_depth.beneficiary_aggregate_cap_krw`
- 포트폴리오별: `underwriting_depth.portfolio_cap_krw`

이는 기존 인출 cap의 의미를 바꾸는 것이 아니라 같은 정본 값을 참조하는 **별도 면제 손실 예산**이다. 누적액은 전체 보존 이력 기준이며 일자 변경·종결로 리셋하지 않는다. 선지급 소유 수익자는 발생 당시 바인딩으로 고정한다.

`effective_sim_day`는 게시 시점의 현재 논리 일과 같아야 한다. 소급·미래일·이율 재작성·가속일 변경은 거절한다. 필요한 참조값 또는 확정 발생액을 해석할 수 없으면 해당 명령은 `NOT_BOUND`로 거절하고 임의 상수를 사용하지 않는다.

### 3.5 `unapplied_cash_release_or_refund`

**`release_unapplied_cash`를 신설하되 시뮬레이션 반환으로 한정한다.** 대상은 확정된 원천 현금 영수증에 연결되고 출처별 대사가 끝난 보관 lot의 미사용 잔액이다. 부분 해제를 허용하며 합계가 잔액을 넘지 못한다.

반환 귀속은 원천의 동일 합성 송금자다. 임의 제3자·수익자 변경·새 은행 계좌 입력은 받지 않는다. 귀속 불명·분쟁·반환 제한·보호 채무·UNKNOWN·다른 게시 예약이 있으면 보관을 유지한다. 같은 범위의 확정된 상환 배분이 가능한 동안에는 먼저 기존 repayment-posting 절차로 대사한다. 면제로 반환액을 자동 생성하지 않는다.

운영자와 별도 검토자 승인을 항상 요구하며, 동일 송금자의 당일 누적 해제액이 위 2인 임계값을 초과하면 별도 금융책임자 승인도 요구한다. 총량 cap은 출처별 가용 보관액이다.

성공 기록은 보관액 감소와 `SIMULATED_RELEASE`를 원자적으로 남긴다. 지급·회수·매출로 계산하지 않으며 **`funds_executed=false`**다. 실제 환불 API·은행 연결·지급 완료 라벨은 금지한다.

### 3.6 `close_gate_reconsideration`

**`CAPITAL_REPAYMENT_POSTING`의 close-gate 규칙은 이 결정 경로를 통해서만 재검토할 수 있음을 기록한다.** 이번 재검토는 좁게 채택한다. 이자 조건은 `발생이자 − 확정 배분액 − 유효 면제액 = 0`이면 충족할 수 있다. 총발생 이력과 면제액은 그대로 표시한다.

기존 게이트의 다른 조건은 제거하지 않는다. 최소한 원금 잔액, 면제 대상 외 채무, 열린 환불·분쟁, 미적용 보관액, UNKNOWN, 미완료 승인·예약이 남아 있으면 통과하지 못한다. 상각만으로 원금이 상환됐다고 판단하지 않는다. 후속 구현은 기존 조건에 이 추가 규칙을 합성해야 한다.

시뮬레이션 해제로 보관액이 0이 되면 그 **보관액 조건만** 충족할 수 있다. pinned FSM 종결·실제 채무 소멸·production 자격은 달라지지 않는다. 결과는 `ADVISORY_ONLY`이며 자동 종결 명령을 실행하지 않는다. 기초 상태가 바뀌면 이전 close 평가는 유효하지 않다.

### 3.7 `overlay_entry_schema_and_digest_effect`

엔트리는 `overlay_id`, `kind`, `payload` 형태를 따른다. 새 kind는 `INTEREST_WAIVER`, `UNAPPLIED_CASH_RELEASE`다. 공통 payload는 다음을 포함한다.

`schema_version`, `operation_id`, `effective_sim_day`, `expected_overlay_digest`, 대상 ID, 버킷별 또는 lot별 금액, `reason_code`, 근거 참조, 제안자·승인자 식별자, 승인 바인딩, 정본 정책 참조와 digest, `funds_executed:false`.

면제는 선지급 ID와 이자 두 버킷을, 해제는 원천 영수증·lot·원송금자 바인딩을 필수로 한다. 동일 operation과 동일 내용 재전송은 최초 결과를 반환하고 다시 차감하지 않는다. 다른 내용은 충돌이다. 응답 유실은 조회로 복구하며 결과 미확정 상태에서 새 operation으로 재시도하지 않는다.

잔액·누적 cap·승인·기준 digest 검증과 게시를 하나의 로컬 원자 단위로 처리한다. 승인된 금전 효과 엔트리와 정책 digest는 오버레이 digest·export content에 포함한다. 벽시계·프로세스 ID는 결정론적 digest에서 제외한다. pinned FSM 상태 digest와 기존 golden은 변경하지 않는다. V1에는 면제 취소·해제 취소 명령을 두지 않는다.

### 3.8 `tax_and_accounting_working_assumption`

작업 가정으로 면제는 현금 회수와 별개인 이자청구 감소 사건이다. 투영은 총발생·배분·면제·순잔액을 분리한다. 이미 인식된 이자와 미인식 이자를 구별하고 회계상 상각 이후 면제로 손실을 이중 인식하지 않는다.

미적용 현금은 수익이 아닌 보관 의무로 취급하며 해제도 매출·이자수익이 아니다. 실제 차변·대변 계정 코드, 세무상 손금 인정일·부가세·원천징수·법적 면제 효력의 확정값은 **UNDETERMINED**다. 각각 `value:null`, target은 회계·세무·법무 전문 검토다. 제품 사건 분리 정책은 ADOPTED지만 이 하위 전문 판단을 채택한 것은 아니다. 합성 V1 차트와 기존 합계를 변경하지 않는다.

### 3.9 `agent_lane_proposal_kinds`

로컬 제안 종류 `PROPOSE_INTEREST_WAIVER`, `PROPOSE_UNAPPLIED_CASH_RELEASE`, `REQUEST_ADVISORY_CLOSE_REVIEW`를 채택한다. 에이전트는 초안·계산 근거·사유를 제출할 수 있으나 승인자 수에 포함되지 않고 게시·지급·자동 종결을 할 수 없다.

제안은 현재 상태·정책 digest와 제한된 대상 범위를 명시한다. stale 제안은 다시 계산한다. upstream AI 위임 계약에 이 종류가 존재하거나 채택됐다고 주장하지 않는다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "waiver-writeoff-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-10-20",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "scope": "Simulation product policy only; no real money",
  "funds_executed": false,
  "production": "NOT_AUTHORIZED",
  "entries": {
    "waiver_command_existence": {
      "status": "ADOPTED",
      "value": {
        "command": "waive_interest",
        "automatic_waiver": false,
        "closed_record_posting": false,
        "historical_receipt_mutation": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-20",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Explicit overlay events resolve unpaid interest without pretending cash recovery.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "waiver_scope_interest_only_vs_principal": {
      "status": "ADOPTED",
      "value": {
        "included": ["ACCRUED_UNPAID_CONTRACT_INTEREST", "ACCRUED_UNPAID_OVERDUE_INTEREST"],
        "excluded": ["PRINCIPAL", "FEES", "FUTURE_INTEREST", "THIRD_PARTY_OBLIGATIONS"],
        "explicit_bucket_amounts": true,
        "future_accrual": "UNCHANGED_EXISTING_TERMS",
        "writeoff_is_waiver": false,
        "principal_capacity_release": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-20",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Interest concessions must not erase principal or protected obligations.",
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
        "agent_approval": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-20",
      "cap_rows": ["CAP-04", "CAP-09"],
      "rationale": "Distinct approvals and aggregate threshold checks prevent self-approval and splitting.",
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
        "effective_day": "CURRENT_SIM_DAY_ONLY",
        "missing_reference": "NOT_BOUND_REJECT"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-20",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Full interest relief is possible within bounded cumulative budgets without copied cap literals.",
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
        "funds_executed": false,
        "external_refund": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-20",
      "cap_rows": ["CAP-02", "CAP-05"],
      "rationale": "Reconciled held cash needs an auditable return simulation, not a fictitious payment.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "close_gate_reconsideration": {
      "status": "ADOPTED",
      "value": {
        "repayment_posting_reconsideration_route": "THIS_DECISION_ONLY",
        "interest_condition": "ACCRUED_MINUS_CONFIRMED_ALLOCATIONS_MINUS_VALID_WAIVERS_EQUALS_ZERO",
        "other_existing_blockers": "PRESERVE_ALL",
        "minimum_blockers": ["PRINCIPAL_OUTSTANDING", "OTHER_OBLIGATIONS", "OPEN_REFUND_OR_DISPUTE", "HELD_UNAPPLIED_CASH", "UNKNOWN", "PENDING_APPROVAL_OR_RESERVATION"],
        "writeoff_counts_as_principal_payment": false,
        "scope": "ADVISORY_ONLY",
        "automatic_close": false,
        "state_change": "INVALIDATE_PRIOR_EVALUATION"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-20",
      "cap_rows": ["CAP-01", "CAP-04", "CAP-20"],
      "rationale": "Valid waivers may satisfy net interest only; no other close requirement is relaxed.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "overlay_entry_schema_and_digest_effect": {
      "status": "ADOPTED",
      "value": {
        "envelope": ["overlay_id", "kind", "payload"],
        "kinds": ["INTEREST_WAIVER", "UNAPPLIED_CASH_RELEASE"],
        "common_payload": ["schema_version", "operation_id", "effective_sim_day", "expected_overlay_digest", "target_ids", "amounts_krw", "reason_code", "evidence_refs", "proposer_id", "approver_ids", "approval_binding", "policy_refs", "policy_digest", "funds_executed"],
        "posting": "ATOMIC_VALIDATION_AND_APPEND_ONLY_EFFECT",
        "same_operation_same_content": "IMMUTABLE_FIRST_RESULT",
        "same_operation_different_content": "CONFLICT",
        "lost_response": "LOOKUP_ONLY_UNTIL_RESOLVED",
        "digest_effect": "INCLUDE_EFFECT_ENTRIES_AND_POLICY_DIGEST_IN_OVERLAY_AND_EXPORT",
        "exclude_from_digest": ["WALL_CLOCK", "PROCESS_ID"],
        "pinned_fsm_digest": "UNCHANGED",
        "existing_goldens": "UNCHANGED",
        "reversal_command_v1": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-20",
      "cap_rows": ["CAP-13", "CAP-14", "CAP-15"],
      "rationale": "Replay must preserve distinct monetary facts without duplicate reductions or upstream mutation.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "tax_and_accounting_working_assumption": {
      "status": "ADOPTED",
      "value": {
        "professional_basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
        "waiver": "SEPARATE_NONCASH_INTEREST_CLAIM_REDUCTION",
        "projection": "SEPARATE_GROSS_ACCRUAL_ALLOCATION_WAIVER_AND_NET",
        "writeoff_double_loss": "PROHIBITED",
        "held_cash": "CUSTODIAL_OBLIGATION_NOT_REVENUE",
        "release": "NOT_REVENUE_OR_RECOVERY",
        "existing_synthetic_chart": "UNCHANGED",
        "professional_determinations": {
          "account_codes_and_posting": {
            "status": "UNDETERMINED",
            "value": null,
            "target": "ACCOUNTS_PROFESSIONAL_REVIEW",
            "reason": "Adopted professional account mappings are absent from the permitted evidence."
          },
          "tax_treatment_and_dates": {
            "status": "UNDETERMINED",
            "value": null,
            "target": "TAX_PROFESSIONAL_REVIEW",
            "reason": "No reviewed deductibility, VAT or withholding determination is supplied."
          },
          "legal_discharge_effect": {
            "status": "UNDETERMINED",
            "value": null,
            "target": "LEGAL_PROFESSIONAL_REVIEW",
            "reason": "A simulation event does not establish enforceable discharge."
          }
        }
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-20",
      "cap_rows": ["CAP-04", "CAP-20"],
      "rationale": "Adopt event separation while leaving professional accounting, tax and legal determinations unresolved.",
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
        "upstream_adoption_claimed": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-20",
      "cap_rows": ["CAP-09", "CAP-20"],
      "rationale": "Agents can prepare bounded proposals without acquiring financial execution authority.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

- 최종 저장 대상: `docs/decisions/CAPITAL_WAIVER_WRITEOFF.md`. 이 문서에는 단일 `capital-decision-v1` 블록과 아홉 필수 entry가 있다.
- 모든 최상위 ADOPTED entry에 값·결정자·ISO 날짜·CAP·잠정 근거를 기재했다. 미정 전문 판단은 하위 객체에서 `value:null`·담당 target·이유로 구분했다.
- repayment-posting close-gate 재검토 경로, `funds_executed:false`, production `NOT_AUTHORIZED`를 명시했다.
- **검증 미실행:** 읽기 전용 세션이므로 파일 저장, `python3 scripts/decision_ledger.py`, `python3 -m unittest tests.test_decisions tests.test_decisions_surface`를 실행하지 않았다. 원장 등록·종료 코드 0·테스트 통과·파서 호환은 주장하지 않는다.

## 6. Open risks

- 허용되지 않은 repayment-posting 원문과 실제 schema의 결합 검토가 남는다. 기존 차단 조건을 삭제하는 구현은 본 결정 위반이다.
- 합성 다중 역할은 실제 인증·권한 분리를 증명하지 않는다. 전문 검토 없는 계정·세무·법적 효력은 미정이다.
- 상각·상환·면제가 교차할 때 이중 차감 위험이 있다. V1의 취소 명령 부재는 잘못 게시한 기록의 운영 복구 한계다.
- 로컬 원자성과 UNKNOWN 처리는 분산 내구성·은행 지급 보장을 뜻하지 않는다.

## 7. 후속 작업

1. Supervisor가 지정 파일로 저장하고 결정 원장·표면 테스트를 실행한다.
2. 별도 소비 노드가 선행 정본을 읽어 참조를 바인딩하고 명령·승인·cap·보관 lot·advisory 평가를 구현한다.
3. 초과 면제, 분할 승인, stale digest, 동시 상환·면제, 중복·충돌·응답 유실, 부분 해제, 귀속 불명, 상각 이후 이중 손실, 종결 차단 보존을 검증한다.
4. 전문 검토와 실제 upstream 영수증은 별도 경로로 확보한다. 그 전까지 production·외부 자금 실행은 계속 금지한다.
