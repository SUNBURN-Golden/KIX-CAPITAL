# Capital 일회성 만기 연장 결정 — 적격 창·금리·유예·가속 거절·증거 형태

**PROVISIONAL PRODUCT DECISION — 잠정 제품 결정.**

| 항목 | 값 |
|---|---|
| 결정 노드 | `maturity-extension-decision` |
| 결정자 표기 | Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07) |
| 결정일 | 2026-10-28 |
| 기준 | KIX-CAPITAL main `e445f38`; kix-protocol `76ba5ef` — supervisor 제공 출처 기준, 독립 검증하지 않음 |
| 의존 | `financial-terms-decision`, `default-recovery-decision`, `margin-cure-default` |
| 소비 노드 | `maturity-extension-command` |
| 범위 | 시뮬레이션·제품 설계만. 청약 아님, 실자금 없음, production `NOT_AUTHORIZED` |

위임 원문: “금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해.”

이 문서는 supervisor pack과 제공된 기존 노트·리뷰만 사용한다. 결정자 표기는 요청된 위임 메타데이터이며 이번 응답에서 Claude CLI 실행이나 모델 전환을 검증했다는 뜻이 아니다. 법률·회계상 효력과 이자 인식은 `WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW`다. upstream 채택·영수증·운영 권한을 주장하지 않는다.

`ADOPTED`는 로컬 잠정 제품 정책의 결정 상태다. 구현이나 upstream 채택 상태가 아니다. 아래 일곱 항목은 모두 ADOPTED이며 구현 소유자는 `maturity-extension-command`다.

## 1. 결정 요약

| item | decision | CAP rows | consumer |
|---|---|---|---|
| `extension_eligibility_window` | 인출일부터 현재 만기+유예 마지막 날까지, 생존·잔액 양수·미사용·가속 없음·미해결 마진콜 없음 | CAP-01, CAP-04 | `maturity-extension-command` |
| `extension_during_grace_and_default_interest_kept` | 유예 중 허용; 발생한 연체이자 유지; 새 만기는 명령일 이상; 새 만기에서 전체 유예 재시작 | CAP-01, CAP-04 | `maturity-extension-command` |
| `extended_term_rate_and_tier` | 최초 심사 티어 all-in 유지; 재티어링·연장 가산·수수료·복리 없음 | CAP-01 | `maturity-extension-command` |
| `hard_cap_180_interaction_with_settlement_linked_term` | 정산 연동 산식은 원 만기에만; 연장 최대 30일, 총기간 최대 180일; 자동 절사 없음 | CAP-01, CAP-04 | `maturity-extension-command` |
| `acceleration_and_default_eligible_refusal` | 가속 뒤·부도 적격일부터 거절; 미해결 마진콜·재사용·agent 게시 거절 | CAP-01, CAP-04, CAP-19 | `maturity-extension-command` |
| `forecast_rollup_and_cap_check_treatment` | 롤업·예측은 새 만기 사용; 같은 시점의 원금·한도 입력 유지; 과거 심사 기록 보존 | CAP-01, CAP-04 | `maturity-extension-command` |
| `extension_record_fields_and_operator_authority` | `MATURITY_EXTENSION` 오버레이 사실 한 건; 사람 승인, 임계 초과 2인; AI 제안만 | CAP-01, CAP-11, CAP-19 | `maturity-extension-command` |

## 2. KIX 비전 연결

사용한 pack 경로와 근거의 범위는 다음과 같다.

- `docs/CAPITAL_REQUIREMENTS_KO.md` 발췌: 실행·참조 핀과 결정 노트의 역사적 출처 기준을 구분한다. 재핀 정책에 관한 제공된 기존 노트의 인용도 이 구분으로 적용한다. 이번 기준 `e445f38`·`76ba5ef`는 실행 핀 교체가 아니다. FSM 핀 `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`, 위임 초안 핀 `e2a029d8…`, 수명 계약 핀 `e2313ab4…`의 범위는 그대로다.
- `docs/decisions/CAPITAL_DEFAULT_RECOVERY.md` 발췌: 가속 만기 `M* = min(현재 만기, 앵커일)`, 연체 시작 `M*+1`, 부도 적격일 `M*+유예+1`, 가속 철회·연장 금지를 계승한다. 연장한 뒤 발생하는 가속에도 **연장된 현재 만기**를 사용한다.
- `docs/decisions/CAPITAL_CLAIM_SLICE_REGISTRY.md` 발췌: TERMS 상수의 소유권과 오버레이 `overlay_id`/`kind`/`payload` 형태를 계승한다. 실제 필드 경로는 소비자가 정본에서 대조한다.
- `docs/decisions/CAPITAL_ARTIFACT_BUNDLING.md` 발췌: 결정 노트는 번들 대상이다. 번들 포함은 구현 완료나 서명·게시를 뜻하지 않는다.
- `docs/SEAMS.md`, `docs/VALIDATION.md` 발췌: 로컬 검증과 upstream 채택을 구분한다. 이 결정도 `SIMULATED`이며 SEMANTIC_CONFORMANCE를 주장하지 않는다.
- `docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md` 발췌: 법·회계 관련 가정은 전문가 검토 전 상태를 유지한다.

요청된 **kix-protocol `CREDIT_ADVANCE_F04` §5 open items**를 만기 연장 정책의 상위 참조로 인용한다. 해당 원문은 pack에 없으므로 세부 문구·정확한 항목명은 `UNDETERMINED`다. 이 결정은 요청된 미정 금융 정책에 대한 Capital의 잠정 답변이며 F04 계약이나 FSM을 수정하지 않는다. `AUTHORITY_MODEL_1.md`와 Protocol README는 경로만 제공됐으므로 내용을 읽었다고 주장하지 않는다.

포부는 만기 변경을 재생 가능한 사실로 남겨, 명령 순서·시계 이동·예측·감사에서 같은 결과가 나오도록 하는 것으로 구체화한다.

## 3. 항목별 결정

공통 기호는 `d0` 인출일, `M` 연장 직전 예정 만기, `E` 명령일, `k` 요청 연장일, `M' = M+k`, `G` TERMS 유예일이다. 모두 정수 논리 일이며 명령이 시계를 변경하지 않는다.

`CAPITAL-TERMS-V1`의 **선지급당 1회, 최대 30일, 총기간 180일 하드캡, HUMAN_OPERATOR 승인, 연장 수수료 0**을 변경 없이 인용한다. 유예 10일과 기타 비율·승인 임계는 제공된 기존 노트의 2차 인용이다. 구현은 정본 값을 로드하며 이 문서의 설명 숫자를 별도 설정값으로 복사하지 않는다.

### 3.1 `extension_eligibility_window` — ADOPTED

적격 창은 `d0 ≤ E ≤ M+G`다. 만기일 당일은 만기 전과 동일하게 허용한다. 선지급이 실제 인출되어 생존하고, 실효 미상환 원금이 양수이며, 이전 연장·가속·미해결 마진콜이 없어야 한다. 명령은 사람 운영자가 제출한다.

치유 마감이 지났어도 마진콜이 미해결이면 연장을 허용하지 않는다. 가속 기록이 아직 없다는 이유로 마감 경계를 우회할 수 없다. 치유가 먼저 유효하게 기록되어 종료된 마진콜은 다른 조건을 만족하면 장애가 아니다.

적격성은 명령 직전 상태에서 평가하고 기록까지 원자적으로 처리한다. 같은 선지급에 경쟁하는 두 연장 중 하나만 성공한다. 동일 명령의 재생은 두 번째 사용으로 세지 않는다. 만기 이후 전면 금지는 유예 중 조정 가능성을 없애므로 채택하지 않는다.

### 3.2 `extension_during_grace_and_default_interest_kept` — ADOPTED

`M < E ≤ M+G`에서도 연장한다. 명령 직전 기존 정책으로 발생한 연체이자는 그대로 유지한다. 면제·소급 재금리·원금 편입·복리를 하지 않는다. 명령일 `E`에 귀속되는 발생분까지 기존 조건을 적용하며 변경 효과는 다음 논리 일부터다.

`M' ≥ E`를 강제한다. 따라서 최소 요청은 `max(1, E−M)`일이다. `M'=E`도 허용하지만 미래 계약 금리 구간은 비어 있으며 다음 날부터 새 만기 기준 연체가 시작된다. 새 부도 적격일은 `M'+G+1`이다. 총기간 하드캡은 예정 만기에 적용하며 유예를 잘라내지 않는다.

`accrued_default_interest_kept_krw`는 서버가 기존 발생 규칙과 원금 이력으로 계산한 보존 증거다. 추가 청구나 상환 잔액을 만드는 항목이 아니며, 이미 지급된 금액을 다시 부과하지 않는다. 이 보존 정책의 법적 효력·인식 시점은 전문가 검토 전 작업 가정이다.

### 3.3 `extended_term_rate_and_tier` — ADOPTED

연장 구간에는 최초 인출 심사 때 고정된 티어 all-in 금리를 사용한다. 재티어링·프리미엄·수수료가 없다. ACT/365 단리, 원금 변동·반올림·상환 종료일 처리 등 기존 발생 관행을 그대로 사용한다.

일별 금리 분류는 다음과 같다.

- `E ≤ M`: 기존 예정 만기 이후 `M < t ≤ M'`에 계약 금리.
- `E > M`: `M < t ≤ E`에 기존 연체 금리, `E < t ≤ M'`에 계약 금리.
- `t > M'`: 새 만기 기준의 기존 연체 정책.

이 구간은 금리를 고르는 규칙이다. 기존 상환일 제외 규칙 등으로 이자가 발생하지 않는 날에 새 이자를 만들지 않는다. 보존 스냅샷을 구간 계산 결과에 다시 더하지 않는다.

연장은 새로운 비용을 추가하지 않는다. 기존 총비용 상한 검사를 우회하지 않으며, 연체 가산까지 상한을 자동 충족한다고 주장하지 않는다. 이후 가속은 DEFAULT_RECOVERY 규칙으로 전향 적용하고 이미 발생한 구간을 다시 쓰지 않는다.

### 3.4 `hard_cap_180_interaction_with_settlement_linked_term` — ADOPTED

정산 연동 기간 산식은 원 만기를 정한다. 연장 명령은 산식을 재실행하거나 정산일 변경을 자동 반영하지 않는다.

허용 범위는 다음과 같다.

`k_min = max(1, E−M)`

`k_max = max(0, min(TERMS.extension.days_max, TERMS.extension.hard_cap_total_days−(M−d0)))`

`k_min ≤ k ≤ k_max`

현재 TERMS 인용값은 최대 30일, 총기간 180일이다. 범위를 벗어나면 `409 EXTENSION_CAP_EXCEEDED`와 `min_admissible_extension_days`, `max_admissible_extension_days`를 반환한다. 최소가 최대보다 크면 가능한 연장이 없다. 자동 절사·원 만기 수정·새 인출 처리는 하지 않는다.

### 3.5 `acceleration_and_default_eligible_refusal` — ADOPTED

권한과 입력 형식을 먼저 확인하고, 동일 `overlay_id`의 완전히 같은 요청은 원 결과를 반환한다. 같은 ID의 다른 요청은 충돌이다. 신규 명령의 사업 거절 우선순위는 아래 순서로 고정한다.

| 조건 | 응답 |
|---|---|
| agent 게시 | `403 EXTENSION_AGENT_FORBIDDEN` |
| 가속 사실 존재 | `409 EXTENSION_AFTER_ACCELERATION` |
| FSM DEFAULTED 또는 `E ≥ 현재 default_eligible_sim_day` | `409 EXTENSION_DEFAULT_ELIGIBLE` |
| 미인출·종료·실효 원금 0 | `409 EXTENSION_NOT_LIVE` |
| 마진콜 미해결 | `409 EXTENSION_MARGIN_CALL_OPEN` |
| 연장 이미 사용 | `409 EXTENSION_ALREADY_USED` |
| 명령일이 인출일보다 앞섬 | `409 EXTENSION_OUTSIDE_WINDOW` |
| 기간 범위 위반 | `409 EXTENSION_CAP_EXCEEDED` |
| 필요한 두 번째 승인 부재 | `409 TWO_PERSON_REQUIRED` |

가속 후 날짜가 다시 적격 창 안처럼 보여도 거절한다. 부도 명령이 아직 없어도 부도 **적격일**부터 거절한다. 거절은 상태·저널·횟수를 바꾸지 않는다. 응답 유실은 기존 식별자로 조회하며 새 식별자를 발급해 자동 재제출하지 않는다.

### 3.6 `forecast_rollup_and_cap_check_treatment` — ADOPTED

연장 엔트리를 포함한 읽기 스냅샷부터 롤업·현금흐름 예측은 `M'`을 예정 만기로 사용한다. 과거 스냅샷은 `M`을 유지한다. 기존 예정 상환 흐름을 이동하며 두 만기에 중복 계상하지 않는다. 연장된 선지급에만 `original_maturity_sim_day`, `extension_days`를 추가한다.

예측은 §3.3의 금리 구간과 이미 지급된 금액을 반영한다. 예측일보다 과거인 새 만기는 기존 연체 표시 규칙을 따른다. 화면에 미래 상환을 확정하거나 회수 성공을 보장하지 않는다.

U1–U6의 원 심사 기록은 변경하지 않는다. 연장 자체는 액면·원금·환불·수익자·차입기초를 바꾸지 않으므로 **같은 논리 일과 같은 잔액 상태**에서 cap_check 금액 결과는 같다. 시계 이동·상환·새 인출로 이후 결과가 바뀌는 것은 정상이다. cap_check가 만기를 표시한다면 새 만기를 사용하되 노출 감소나 한도 복원으로 취급하지 않는다.

### 3.7 `extension_record_fields_and_operator_authority` — ADOPTED

로컬 오버레이 사실은 `kind: MATURITY_EXTENSION`이다. 논리 엔트리는 다음 필드를 반드시 기록한다.

| 위치 | 필드 |
|---|---|
| 공통 엔트리 | `overlay_id`, `kind`, `sim_day`, `after_journal_index`, `payload` |
| `payload` 식별 | `advance_id`, `claim_id`, `beneficiary_role` |
| 기간·금리 증거 | `draw_sim_day`, `original_maturity_sim_day`, `extension_days`, `new_maturity_sim_day`, `tier` |
| 금액 증거 | `outstanding_principal_krw_at_command`, `accrued_default_interest_kept_krw`, `fee_krw: 0` |
| 근거·권한 | `terms_refs`, `authority`, `label: SIMULATED` |

`authority = {role: HUMAN_OPERATOR, approvals: [{approver_label}], proposal_id?}`다. 승인 라벨은 중복 제거하고 정렬한다. 명령 시점 실효 원금이 TERMS의 `two_person_threshold_krw`를 초과하면 서로 다른 사람 승인 두 개가 필요하다. 이하에서는 한 명이다. 같은 요청의 재생·실패를 합산해 승인 금액을 부풀리지 않는다. 로컬 라벨은 인증이 아니다.

`terms_refs`에는 `terms_version`, 사용 노트의 `note_sha256`, 적용한 연장·유예·금리·승인 조항의 정본 참조를 기록한다. 정확한 조항 경로는 정본에서 확인하며 새 값을 만들지 않는다. AI 후보는 `MATURITY_EXTENSION_CANDIDATE`, `executionAuthorized=false`; 운영자의 별도 명령만 기록되며 제안은 승인이 아니다.

서버가 날짜·원금·티어·보존액을 산출한다. 클라이언트가 보낸 값을 사실로 신뢰하지 않는다. 금액은 정수 KRW, 날짜·일수는 정수이며 자유 텍스트·개인정보·wall-clock 필드는 금지한다. 파생 부도일·구간표·잔여 여유일은 재생 시 계산한다.

폴드는 `state.maturity_extension[advance_id]`에 성공 사실 하나를 보존한다. 빈 경우 키가 없다. `after_journal_index`만으로 같은 인덱스의 여러 오버레이 사실을 구분하지 않고 기존 오버레이 저널 순서를 함께 사용한다. 공통 메타데이터의 실제 직렬화 위치·스키마 버전은 기존 오버레이 계약에 맞추며, 이 표로 호환성을 우회하지 않는다.

F04 상태·FSM·COA 게시를 변경하지 않는다. 연장 없는 책의 digest·골든은 유지한다. 연장 있는 책의 오버레이 digest와 이를 포함한 export `content_digest`는 내용에 맞게 다시 계산한다. export 구조와 recon 식별자 유지가 digest 값 불변을 의미하지 않는다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "maturity-extension-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-10-28",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "bases": {
    "capital_main": "e445f38",
    "kix_protocol": "76ba5ef",
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
        "conditions": ["drawn and live", "outstanding principal > 0", "unused extension", "no acceleration", "no unresolved margin call"],
        "count_max_ref": "CAPITAL-TERMS-V1 extension.count_max (1, unchanged)",
        "atomicity": "evaluate and append atomically; one successful extension per advance",
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-28",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Allow adjustment through the final grace day without bypassing default or an unresolved cure obligation.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "extension_during_grace_and_default_interest_kept": {
      "status": "ADOPTED",
      "value": {
        "grace_extension": "ALLOWED",
        "accrued_interest": "Keep existing accrual through E; no forgiveness, retroactive repricing, capitalization or duplicate charge",
        "new_maturity": "M_prime = M + k >= E",
        "new_default_eligible_day": "M_prime + G + 1",
        "evidence": "server-computed accrued_default_interest_kept_krw; observational snapshot, not a new receivable",
        "professional_review": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-28",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Preserve prior facts while making the new maturity and full grace period explicit.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "extended_term_rate_and_tier": {
      "status": "ADOPTED",
      "value": {
        "rate": "original underwriting tier all-in",
        "segments": {
          "E_le_M": "contract rate for M < t <= M_prime",
          "E_gt_M": "existing overdue rate for M < t <= E; contract rate for E < t <= M_prime",
          "after_new_maturity": "existing overdue policy"
        },
        "conventions": "existing ACT/365 simple accrual, principal history, rounding and repayment stop-day rules",
        "tier_migration": false,
        "extension_premium": false,
        "fee_ref": "CAPITAL-TERMS-V1 extension_fee_bps (0, unchanged)",
        "cost_cap": "existing checks remain applicable; no blanket exemption",
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-28",
      "cap_rows": ["CAP-01"],
      "rationale": "Retain the agreed rate and deterministic daily boundaries without introducing new pricing.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "hard_cap_180_interaction_with_settlement_linked_term": {
      "status": "ADOPTED",
      "value": {
        "settlement_formula": "original maturity only; never rerun for extension",
        "minimum_days": "max(1, E - M)",
        "maximum_days": "max(0, min(terms.extension.days_max, terms.extension.hard_cap_total_days - (M - d0)))",
        "terms_citations": ["extension.days_max = 30 unchanged", "extension.hard_cap_total_days = 180 unchanged"],
        "invalid_request": "409 EXTENSION_CAP_EXCEEDED with min_admissible_extension_days and max_admissible_extension_days; no clamping",
        "cap_scope": "scheduled maturity minus draw day; grace is not shortened",
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-28",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Combine the original term formula with both extension limits without silently changing the request.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "acceleration_and_default_eligible_refusal": {
      "status": "ADOPTED",
      "value": {
        "authority_first": "403 EXTENSION_AGENT_FORBIDDEN for agent posting",
        "idempotency": "same ID and same request returns original result; conflicting request returns 409",
        "business_refusal_order": [
          "EXTENSION_AFTER_ACCELERATION",
          "EXTENSION_DEFAULT_ELIGIBLE",
          "EXTENSION_NOT_LIVE",
          "EXTENSION_MARGIN_CALL_OPEN",
          "EXTENSION_ALREADY_USED",
          "EXTENSION_OUTSIDE_WINDOW",
          "EXTENSION_CAP_EXCEEDED",
          "TWO_PERSON_REQUIRED"
        ],
        "default_boundary": "E >= current default_eligible_sim_day or FSM DEFAULTED; no default command required",
        "refusal_effect": "no state, journal or count change",
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-28",
      "cap_rows": ["CAP-01", "CAP-04", "CAP-19"],
      "rationale": "Make acceleration refusal and default eligibility enforceable even when subsequent commands have not yet been recorded.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "forecast_rollup_and_cap_check_treatment": {
      "status": "ADOPTED",
      "value": {
        "rollup_forecast": "snapshots containing the entry use M_prime; historical snapshots retain M; move rather than duplicate scheduled repayment",
        "additive_fields": ["original_maturity_sim_day", "extension_days"],
        "unused_fields": "absent on advances without extension",
        "interest_forecast": "use the adopted segments without adding the kept-interest snapshot again",
        "underwriting": "preserve original U1-U6 record",
        "cap_check": "amount results unchanged by extension at the same logical day and balance state; any displayed maturity becomes M_prime",
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-28",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Reflect the changed schedule without manufacturing available capacity or rewriting past underwriting.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "extension_record_fields_and_operator_authority": {
      "status": "ADOPTED",
      "value": {
        "entry_kind": "MATURITY_EXTENSION",
        "entry_fields": ["overlay_id", "kind", "sim_day", "after_journal_index", "payload"],
        "payload_fields": [
          "advance_id",
          "claim_id",
          "beneficiary_role",
          "draw_sim_day",
          "original_maturity_sim_day",
          "extension_days",
          "new_maturity_sim_day",
          "tier",
          "outstanding_principal_krw_at_command",
          "accrued_default_interest_kept_krw",
          "fee_krw",
          "terms_refs",
          "authority",
          "label"
        ],
        "constants": {"fee_krw": 0, "label": "SIMULATED"},
        "terms_refs": ["terms_version", "note_sha256", "canonical clause references"],
        "authority": {
          "role": "HUMAN_OPERATOR",
          "approvals": "sorted unique approver_label objects",
          "amount_basis": "outstanding principal at command",
          "threshold_ref": "CAPITAL-TERMS-V1 underwriting_depth.two_person_threshold_krw",
          "required": "one human up to threshold; two distinct humans above threshold",
          "proposal_id": "optional",
          "authentication_claimed": false
        },
        "ai": {"kind": "MATURITY_EXTENSION_CANDIDATE", "executionAuthorized": false},
        "fold": "state.maturity_extension[advance_id]; absent when empty",
        "ordering": "existing overlay journal order plus after_journal_index",
        "physical_layout": "preserve existing overlay metadata placement and schema rules; verify before implementation",
        "digests": "F04 unchanged; changed overlay and containing export content digests recomputed; books without extension unchanged",
        "coa_posting": false,
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-28",
      "cap_rows": ["CAP-01", "CAP-11", "CAP-19"],
      "rationale": "Record sufficient deterministic evidence and human approval while retaining local simulation and existing overlay compatibility boundaries.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

- **결정 문서·파싱·조회:** 이 문서는 정확히 하나의 `capital-decision-v1` 블록과 일곱 ADOPTED 항목을 제공한다. 각각 소유자·날짜·CAP·근거·소비 노드를 명시했다. 이번 응답에서는 파일 저장, 파서 실행, `GET /api/decisions` 조회를 수행하지 않았다.
- **TERMS 불변:** 1회·30일·180일·사람 승인·수수료 없음은 변경 없이 인용했다. 정본 경로 대조 책임은 소비 노드에 있다.
- **엔트리·소비자:** §3.7과 JSON이 `MATURITY_EXTENSION` 필드와 `maturity-extension-command`를 지정한다.
- **pending consumer anchor:** `tests/decision_bindings.json`은 일곱 항목을 각각 `PENDING_CONSUMER`, `consumer_node: maturity-extension-command`로 등록해야 한다. pending 앵커는 구현 증거가 아니다. 이번 응답에서 파일 내용이나 `python3 scripts/decision_bindings.py --check` 통과를 재검증하지 않았다.
- **리뷰 blocking 처리:** `tests/test_coa_candidate.py`의 SHA256 예외 추가는 이 결정이 승인하지 않는다. 최종 변경에서는 해당 파일이 base와 같아야 한다. 이번 지시는 문서만 반환하고 그 테스트의 편집을 금지하므로 여기서 복구했다고 주장할 수 없다. supervisor가 기존 범위 밖 변경을 제거하고 확인할 때까지 해당 blocking finding은 해소된 것으로 표시하지 않는다.

## 6. Open risks

- TERMS 정본·오버레이 공통 스키마·F04 §5 원문을 직접 확인하지 않았다. **정확한 필드 경로·직렬화 적합성·상위 문구는 UNDETERMINED**, 사유는 pack 부재이며 소유자는 `maturity-extension-command`다. 새 금융 결정이 필요한 상태라는 뜻은 아니다.
- 유예 중 연체이자 보존의 법적 효력·회계 인식은 전문가 검토 전이다. 소유자는 `accounts-tax-legal-decision` 후속 검토다.
- 명령일 발생분, 부분 상환, 같은 날 명령 순서가 맞물린다. 일별 금리 분류와 기존 발생·종료일 관행을 함께 검증해야 한다.
- 로컬 승인 라벨·해시·재생 성공은 인증이나 대외 채무 변경의 증거가 아니다.

## 7. 후속 작업

1. **Supervisor:** 이 문서를 지정 경로에 저장하고 pending 일곱 행을 확인한다. 범위 밖 compatibility guard 변경을 base로 복구한다. commit·push·게시를 이 문서가 승인하지 않는다.
2. **검증 담당:** `python3 scripts/decision_bindings.py --check`, 결정 파서·조회 검증, `python3 scripts/docs_surface.py --check`를 실행하고 실제 결과를 기록한다. 이전 라운드의 성공 기록을 이번 실행 결과로 재사용하지 않는다.
3. **`maturity-extension-command`:** 적격 창의 양 끝, 마지막 유예일·첫 부도 적격일, 180일 경계, 미해결 치유 마감, 가속 전후, 부분 상환, 경쟁 명령·동일 재생·충돌, 2인 승인·agent 거절, 시계 점프와 하루씩 진행의 동등성을 검증한다. 재무·closeout 벡터 변경은 해당 재생성 정책과 등록 규칙을 따른다.
