# Capital 일회성 만기 연장 결정 — 적격 창·금리·유예·가속 거절·증거 형태

**PROVISIONAL PRODUCT DECISION — 잠정 제품 결정.**

| 항목 | 값 |
|---|---|
| 결정 노드 | `maturity-extension-decision` |
| 결정자 | Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07) |
| 결정일 | 2026-10-30 |
| 기준 | KIX-CAPITAL main `59900e9`; kix-protocol `6dfb03a` — supervisor 제공 기준 |
| 의존 | `financial-terms-decision`, `default-recovery-decision`, `margin-cure-default`, `decision-guard-additions` |
| 구현 소유자·소비 노드 | `maturity-extension-command` |
| 범위 | 시뮬레이션·제품 설계만. 청약 아님, 실자금 없음, production `NOT_AUTHORIZED` |

위임 원문: “금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해.”

결정자 표기는 요청된 위임 메타데이터이며, 이번 작성에서 Claude CLI 실행이나 모델 전환을 검증했다는 뜻이 아니다. 근거는 제공된 supervisor pack·기존 문서·리뷰다. 법률·회계상 효력과 이자 인식은 `WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW`다. upstream 채택·영수증·운영 권한을 주장하지 않는다.

`ADOPTED`는 위임 범위의 로컬 잠정 제품 정책이며 구현 완료를 뜻하지 않는다. 아래 일곱 항목은 모두 ADOPTED이고 소유자는 `maturity-extension-command`다.

## 1. 결정 요약

| item | decision | CAP rows | consumer |
|---|---|---|---|
| `extension_eligibility_window` | 인출일부터 현재 만기+유예 마지막 날까지; 생존·원금 양수·미사용·가속 없음·미해결 마진콜 없음 | CAP-01, CAP-04 | `maturity-extension-command` |
| `extension_during_grace_and_default_interest_kept` | 유예 중 허용; 명령일까지 발생한 연체이자 보존; 새 만기에서 전체 유예 재시작 | CAP-01, CAP-04 | `maturity-extension-command` |
| `extended_term_rate_and_tier` | 최초 심사 티어 all-in 유지; 재티어링·연장 가산·수수료·복리 없음 | CAP-01 | `maturity-extension-command` |
| `hard_cap_180_interaction_with_settlement_linked_term` | 정산 산식은 원 만기에만 적용; 연장 최대 30일·총기간 최대 180일; 초과 요청 거절 | CAP-01, CAP-04 | `maturity-extension-command` |
| `acceleration_and_default_eligible_refusal` | 가속 이후·부도 적격일부터 거절; 미해결 마진콜·재사용·agent 게시 거절 | CAP-01, CAP-04, CAP-19 | `maturity-extension-command` |
| `forecast_rollup_and_cap_check_treatment` | 현재 롤업·예측은 새 만기 사용; 같은 시점의 원금·한도 입력과 과거 심사 기록 보존 | CAP-01, CAP-04 | `maturity-extension-command` |
| `extension_record_fields_and_operator_authority` | `MATURITY_EXTENSION` 사실 한 건; 사람 승인, 임계 초과 2인; AI는 제안만 | CAP-01, CAP-11, CAP-19 | `maturity-extension-command` |

## 2. KIX 비전 연결

이 결정은 만기 조정을 재생 가능한 사실로 남겨 명령 처리·예측·감사가 같은 일별 금리와 만기를 사용하도록 한다. 다음 pack 발췌만 근거로 사용했다.

- `docs/CAPITAL_REQUIREMENTS_KO.md`: 실행·참조 핀과 결정 문서의 역사적 출처를 구분한다. 이번 `59900e9`·`6dfb03a`는 출처 기준이며 재핀이 아니다. FSM 핀 `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`, 위임 초안 핀 `e2a029d8ac3af7575888dac22fc4bf173ebec232`, 수명 계약 핀 `e2313ab473ea1b5a7b5b9246a564749188c1c2c8`의 기존 소비 범위를 유지한다. 실행 기준 변경은 별도 재핀 정책과 검증을 따른다.
- `docs/decisions/CAPITAL_DEFAULT_RECOVERY.md`: 가속 만기 `M* = min(현재 만기, 앵커일)`, 연체 시작 `M*+1`, 부도 적격일 `M*+유예+1`, 가속 철회·연장 금지를 계승한다. 연장 뒤 가속할 때는 연장된 현재 만기를 사용한다.
- `docs/decisions/CAPITAL_CLAIM_SLICE_REGISTRY.md`: TERMS 상수의 소유권과 `overlay_id`/`kind`/`payload` 형태를 계승한다. 상수를 중복 설정하지 않는다.
- `docs/decisions/CAPITAL_ARTIFACT_BUNDLING.md`: 결정 문서 번들은 구현 완료·서명·게시의 증거가 아니다.
- `docs/SEAMS.md`, `docs/VALIDATION.md`: 로컬 검증과 upstream 채택을 구분한다. 이 결정은 `SIMULATED`이며 SEMANTIC_CONFORMANCE를 주장하지 않는다.
- `docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md`: 법률·회계 관련 사항은 전문가 검토 전 작업 가정이다.

요청된 **kix-protocol `CREDIT_ADVANCE_F04` §5 open items**를 금융 정책 미정 사항의 상위 참조로 인용한다. 원문이 pack에 없으므로 정확한 문구·항목명은 `UNDETERMINED`이며 소유자는 `maturity-extension-command`다. 이 인용은 supervisor 제공 참조이고 F04 계약·FSM 채택이나 변경이 아니다. Protocol README와 `AUTHORITY_MODEL_1.md`는 내용이 제공되지 않아 근거로 사용하지 않았다.

## 3. 항목별 결정

공통 기호: `d0`는 인출일, `M`은 연장 직전 예정 만기, `E`는 명령일, `k`는 요청 연장일, `M' = M+k`, `G`는 TERMS 유예일이다. 날짜·일수는 정수 논리 일 `sim_day`이며 연장 명령은 시계를 움직이지 않는다.

`CAPITAL-TERMS-V1`의 **선지급당 1회, 최대 30일, 총기간 180일 하드캡, HUMAN_OPERATOR 승인, 연장 수수료 0**을 변경 없이 인용한다. 유예 10일과 다른 비율·승인 임계는 pack의 선행 결정 인용을 따른다. TERMS 정본은 직접 열지 않았다. 소비자는 정본에서 값을 로드하며 설명용 숫자를 별도 설정값으로 복사하지 않는다.

### 3.1 `extension_eligibility_window` — ADOPTED

적격 창은 `d0 ≤ E ≤ M+G`다. 만기 당일도 허용한다. 선지급은 인출되어 생존하고 실효 미상환 원금이 양수여야 한다. 이전 연장·가속·미해결 마진콜이 없어야 하며 사람 운영자가 명령을 제출한다.

치유 마감이 지나도 미해결 마진콜이 있으면 거절한다. 가속 기록 부재로 치유 의무를 우회할 수 없다. 치유가 먼저 유효하게 기록되어 종료된 마진콜은 다른 조건을 충족하면 장애가 아니다.

명령 직전 상태 평가와 기록을 원자적으로 처리한다. 경쟁하는 두 연장 중 하나만 성공한다. 동일 명령 재생은 추가 사용으로 세지 않는다. 소유자는 `maturity-extension-command`다.

### 3.2 `extension_during_grace_and_default_interest_kept` — ADOPTED

`M < E ≤ M+G`에서도 허용한다. 명령일 `E` 귀속분까지 기존 조건으로 발생한 연체이자를 보존하고 변경 효과는 다음 논리 일부터 적용한다. 면제·소급 재금리·원금 편입·복리를 하지 않는다.

`M' ≥ E`를 강제한다. 최소 요청은 `max(1, E−M)`일이다. `M'=E`이면 미래 계약 금리 구간은 비어 있고 다음 날부터 새 만기 기준 연체가 시작된다. 새 부도 적격일은 `M'+G+1`이다. 180일 하드캡은 예정 만기에 적용하며 유예를 단축하지 않는다.

`accrued_default_interest_kept_krw`는 기존 발생 규칙과 원금 이력으로 계산한 관측 증거다. 추가 채권을 만들거나 이미 지급된 금액을 재청구하지 않는다. 법적 효력·인식 시점은 전문가 검토 전 작업 가정이다. 구현 소유자는 `maturity-extension-command`다.

### 3.3 `extended_term_rate_and_tier` — ADOPTED

연장 구간에는 최초 인출 심사에서 고정된 티어 all-in 금리를 적용한다. 재티어링·연장 프리미엄·수수료는 없다. 기존 ACT/365 단리, 원금 변동, 반올림과 상환 종료일 관행을 유지한다.

| 조건 | 일별 금리 |
|---|---|
| `E ≤ M` | `M < t ≤ M'`에 계약 금리 |
| `E > M` | `M < t ≤ E`에 기존 연체 금리; `E < t ≤ M'`에 계약 금리 |
| `t > M'` | 새 만기 기준 기존 연체 정책 |

이 표는 금리 선택 규칙이다. 기존 상환일 제외 규칙 등으로 발생하지 않는 이자를 새로 만들지 않는다. 보존 스냅샷을 구간 계산 결과에 다시 더하지 않는다.

기존 총비용 상한 검사는 계속 적용하며 연체 가산까지 자동 적합하다고 주장하지 않는다. 이후 가속은 DEFAULT_RECOVERY 규칙으로 전향 적용하고 과거 발생 구간을 다시 쓰지 않는다. 소유자는 `maturity-extension-command`다.

### 3.4 `hard_cap_180_interaction_with_settlement_linked_term` — ADOPTED

정산 연동 산식은 원 만기를 정한다. 연장 명령은 산식을 재실행하거나 정산일 변경을 자동 반영하지 않는다.

- `k_min = max(1, E−M)`
- `k_max = max(0, min(TERMS.extension.days_max, TERMS.extension.hard_cap_total_days−(M−d0)))`
- 허용 범위: `k_min ≤ k ≤ k_max`

최대 30일·총기간 180일이라는 TERMS 값을 유지한다. 범위를 벗어나면 `409 EXTENSION_CAP_EXCEEDED`와 `min_admissible_extension_days`, `max_admissible_extension_days`를 반환한다. 최소가 최대보다 크면 가능한 연장이 없다. 자동 절사·원 만기 수정·새 인출 처리는 없다. 소유자는 `maturity-extension-command`다.

### 3.5 `acceleration_and_default_eligible_refusal` — ADOPTED

권한과 입력 형식을 먼저 확인한다. agent 게시에는 `403 EXTENSION_AGENT_FORBIDDEN`을 반환한다. 권한 있는 동일 `overlay_id`·동일 요청 재생은 원 결과를 반환하고, 같은 ID의 다른 요청은 `409` 충돌이다. 신규 명령의 사업 거절 우선순위는 다음과 같다.

| 순서 | 조건 | 응답 |
|---|---|---|
| 1 | 가속 사실 존재 | `409 EXTENSION_AFTER_ACCELERATION` |
| 2 | FSM DEFAULTED 또는 `E ≥ 현재 default_eligible_sim_day` | `409 EXTENSION_DEFAULT_ELIGIBLE` |
| 3 | 미인출·종료·실효 원금 0 | `409 EXTENSION_NOT_LIVE` |
| 4 | 마진콜 미해결 | `409 EXTENSION_MARGIN_CALL_OPEN` |
| 5 | 연장 사용 완료 | `409 EXTENSION_ALREADY_USED` |
| 6 | `E < d0` | `409 EXTENSION_OUTSIDE_WINDOW` |
| 7 | 기간 범위 위반 | `409 EXTENSION_CAP_EXCEEDED` |
| 8 | 필요한 두 번째 승인 부재 | `409 TWO_PERSON_REQUIRED` |

가속 이후 날짜가 적격 창처럼 보여도 거절한다. 부도 명령이 없어도 부도 적격일부터 거절한다. 거절은 상태·저널·사용 횟수를 변경하지 않는다. 응답 유실은 기존 식별자로 조회하며 새 식별자를 발급해 자동 재제출하지 않는다. 소유자는 `maturity-extension-command`다.

### 3.6 `forecast_rollup_and_cap_check_treatment` — ADOPTED

연장 사실이 포함된 스냅샷부터 롤업·현금흐름 예측은 `M'`을 예정 만기로 사용한다. 과거 스냅샷은 `M`을 유지한다. 예정 상환 흐름을 이동하고 두 만기에 중복 계상하지 않는다. 연장된 선지급에만 `original_maturity_sim_day`, `extension_days`를 추가한다.

예측은 §3.3 금리 구간과 이미 지급된 금액을 반영한다. 예측일보다 과거인 만기는 기존 연체 표시 규칙을 따르며 회수를 보장하지 않는다.

원 심사 U1–U6 기록은 보존한다. 연장 자체는 액면·원금·환불·수익자·차입기초를 바꾸지 않으므로 같은 논리 일·잔액 상태에서 cap_check 금액 결과는 같다. 이후 시계 이동·상환·인출에 따른 변화는 허용된다. cap_check가 만기를 표시하면 새 만기를 사용하되 노출 감소나 한도 복원으로 처리하지 않는다. 소유자는 `maturity-extension-command`다.

### 3.7 `extension_record_fields_and_operator_authority` — ADOPTED

오버레이 사실의 종류는 `MATURITY_EXTENSION`이며 다음 논리 필드를 필수로 기록한다.

| 위치 | 필드 |
|---|---|
| 공통 엔트리 | `overlay_id`, `kind`, `sim_day`, `after_journal_index`, `payload` |
| payload 식별 | `advance_id`, `claim_id`, `beneficiary_role` |
| 기간·금리 | `draw_sim_day`, `original_maturity_sim_day`, `extension_days`, `new_maturity_sim_day`, `tier` |
| 금액 | `outstanding_principal_krw_at_command`, `accrued_default_interest_kept_krw`, `fee_krw: 0` |
| 근거·권한 | `terms_refs`, `authority`, `label: SIMULATED` |

`authority = {role: HUMAN_OPERATOR, approvals: [{approver_label}], proposal_id?}`다. 승인 라벨은 중복 제거·정렬한다. 명령 시점 실효 원금이 TERMS의 `two_person_threshold_krw`를 초과하면 서로 다른 사람 두 명, 이하이면 한 명이 승인한다. 실패·재생을 합산해 승인 금액을 부풀리지 않는다. 로컬 라벨은 인증이 아니다.

`terms_refs`는 `terms_version`, 사용 노트의 `note_sha256`, 적용한 연장·유예·금리·승인 조항의 정본 참조를 기록한다. 정확한 조항 경로는 정본에서 확인한다. AI 제안은 `MATURITY_EXTENSION_CANDIDATE`, `executionAuthorized=false`이며 운영자의 별도 명령이 있어야 사실이 기록된다.

서버가 날짜·원금·티어·보존액을 산출한다. 금액은 정수 KRW, 날짜·일수는 정수다. 자유 텍스트·개인정보·wall-clock 필드를 추가하지 않는다. 파생 부도일·금리 구간·잔여 여유일은 재생 시 계산한다.

폴드는 `state.maturity_extension[advance_id]`에 성공 사실 하나를 보존하며 연장이 없으면 키가 없다. 같은 `after_journal_index`의 사실은 기존 오버레이 저널 순서로 구분한다. 공통 메타데이터의 물리적 위치·스키마 버전은 기존 계약을 준수한다.

F04 상태·FSM·COA 게시를 변경하지 않는다. 연장 없는 책의 digest·골든은 유지한다. 연장 있는 책의 오버레이 digest와 이를 포함한 export `content_digest`는 내용에 맞게 재계산한다. export 구조와 recon 식별자 유지가 digest 값 불변을 뜻하지 않는다. 소유자는 `maturity-extension-command`다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "maturity-extension-decision",
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-10-30",
  "provisional": true,
  "bases": {
    "capital_main": "59900e9",
    "kix_protocol": "6dfb03a",
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
        "conditions": ["drawn and live", "positive outstanding principal", "unused extension", "no acceleration", "no unresolved margin call"],
        "count_max_ref": "CAPITAL-TERMS-V1 extension.count_max (1, unchanged)",
        "atomicity": "evaluate and append atomically; one success per advance; replay is not another use",
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-30",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Allow adjustment through the final grace day without bypassing default or an unresolved cure obligation.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "extension_during_grace_and_default_interest_kept": {
      "status": "ADOPTED",
      "value": {
        "grace_extension": "ALLOWED",
        "accrued_interest": "preserve existing accrual through E; no forgiveness, retroactive repricing, capitalization or duplicate charge",
        "new_maturity": "M_prime = M + k >= E",
        "new_default_eligible_day": "M_prime + G + 1",
        "evidence": "server-computed accrued_default_interest_kept_krw is an observational snapshot, not a new receivable",
        "professional_review": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-30",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Preserve prior accrual while establishing the new maturity and full grace period.",
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
        "cost_cap": "existing checks remain applicable",
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-30",
      "cap_rows": ["CAP-01"],
      "rationale": "Retain agreed pricing and deterministic daily boundaries without introducing new charges.",
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
      "date": "2026-10-30",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Apply both extension limits to the original settlement-linked term without silently changing requests.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "acceleration_and_default_eligible_refusal": {
      "status": "ADOPTED",
      "value": {
        "authority_first": "403 EXTENSION_AGENT_FORBIDDEN for agent posting",
        "idempotency": "authorized same-ID same-request replay returns original result; conflicting request returns 409",
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
      "date": "2026-10-30",
      "cap_rows": ["CAP-01", "CAP-04", "CAP-19"],
      "rationale": "Enforce acceleration and default eligibility boundaries independently of later command recording.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "forecast_rollup_and_cap_check_treatment": {
      "status": "ADOPTED",
      "value": {
        "rollup_forecast": "snapshots containing the entry use M_prime; historical snapshots retain M; move scheduled repayment without duplication",
        "additive_fields": ["original_maturity_sim_day", "extension_days"],
        "unused_fields": "absent on advances without extension",
        "interest_forecast": "use adopted segments and payments without adding the kept-interest snapshot again",
        "underwriting": "preserve original U1-U6 record",
        "cap_check": "amount results unchanged by extension at the same logical day and balance state; displayed maturity becomes M_prime; no capacity release",
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-30",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Reflect the revised schedule while preserving exposure and historical underwriting evidence.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "extension_record_fields_and_operator_authority": {
      "status": "ADOPTED",
      "value": {
        "entry_kind": "MATURITY_EXTENSION",
        "entry_fields": ["overlay_id", "kind", "sim_day", "after_journal_index", "payload"],
        "payload_fields": [
          "advance_id", "claim_id", "beneficiary_role",
          "draw_sim_day", "original_maturity_sim_day", "extension_days",
          "new_maturity_sim_day", "tier",
          "outstanding_principal_krw_at_command",
          "accrued_default_interest_kept_krw", "fee_krw",
          "terms_refs", "authority", "label"
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
        "physical_layout": "preserve existing overlay metadata placement and schema rules",
        "digests": "F04 unchanged; changed overlay and containing export content digests recomputed; books without extension unchanged",
        "coa_posting": false,
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-30",
      "cap_rows": ["CAP-01", "CAP-11", "CAP-19"],
      "rationale": "Record deterministic evidence and human approval within existing local overlay boundaries.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

- **문서·파싱·조회:** 지정 경로는 `docs/decisions/CAPITAL_MATURITY_EXTENSION.md`다. 기계 판독 블록은 정확히 하나이며 일곱 ADOPTED 항목 모두 귀속·날짜·CAP·근거·소비 소유자를 포함한다. 저장 후 결정 파서와 `GET /api/decisions`가 이를 노출해야 한다.
- **TERMS·증거:** 1회·30일·180일·사람 승인·수수료 0을 유지한다. §3.7과 JSON이 소비 노드 및 필수 엔트리 필드를 지정한다.
- **바인딩:** 일곱 항목은 `tests/decision_bindings.json`에서 `PENDING_CONSUMER`, `consumer_node: maturity-extension-command`인 앵커로 등록한다. pending은 구현 완료의 증거가 아니다.
- **검증 출처·리뷰:** supervisor는 검토 대상 head의 관련 검사 통과를 확인했다. 이전 문서의 guard 변경 미해결 경고와 복구 지시는 현재 차단 사유로 유지하지 않는다. 제공 리뷰에는 정책상 blocking defect가 없으며, BLOCK은 독립 검토 미완료를 뜻한다. 이번 작성은 명령 실행·파일 저장·검사 재실행·독립 승인을 주장하지 않는다.

## 7. Open risks

- TERMS 정본의 정확한 조항 경로, 오버레이 물리적 직렬화 적합성, F04 §5 원문은 `UNDETERMINED`다. 사유는 pack 부재이며 소유자는 `maturity-extension-command`다. 결정된 금융 정책을 다시 `DECISION_REQUIRED`로 돌리는 사유는 아니다.
- 연체이자 보존의 법적 효력·회계 인식은 전문가 검토 전이다. 소유자는 `accounts-tax-legal-decision` 후속 검토다.
- 명령일 발생분·부분 상환·같은 날 명령 순서는 소비 노드가 기존 발생 관행과 함께 검증한다.
- 승인 라벨·해시·로컬 재생 성공은 인증이나 대외 채무 변경 효력을 입증하지 않는다.

## 8. 후속 작업

1. **Supervisor:** 완성 문서를 저장하고 일곱 pending 앵커와 연결한다.
2. **검증 담당:** 저장된 최종 바이트에 대해 `python3 scripts/decision_bindings.py --check`, 결정 파서·API 조회, `python3 scripts/docs_surface.py --check` 결과를 기록한다. supervisor의 기존 확인과 후속 실행 결과를 구분한다.
3. **`maturity-extension-command`:** 적격 창 양 끝, 마지막 유예일·첫 부도 적격일, 180일 경계, 미해결 마진콜, 가속 전후, 부분 상환, 경쟁 명령·재생·충돌, 승인 임계·agent 거절, 시계 점프와 일별 진행의 동등성을 검증한다. 새 벡터는 기존 등록 규칙을 따른다.

이 문서는 코드·FSM 변경, 실자금 실행, commit·push·게시를 수행하거나 승인하지 않는다.
