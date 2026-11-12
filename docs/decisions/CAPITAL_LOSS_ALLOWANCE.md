# Capital 기대신용손실 충당금 결정 — 측정·게시·환입·준비금·대사

> **PROVISIONAL PRODUCT DECISION**
>
> **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**
>
> Date: **2026-11-10** · Capital main: **`a791651`** · kix-protocol: **`347ce44`**
>
> 시뮬레이션·제품 설계 전용. 실자금·청약 없음. Production **`NOT_AUTHORIZED`**.
> `accounting_policy=SYNTHETIC_UNADOPTED`, `policy_adopted=false`, tax **`NOT_BOUND`**.

노드: `loss-allowance-decision`. 소비자: `loss-allowance-postings`. 모든 항목은 전문가 검토가 필요한 잠정 제품 결정이다. `ADOPTED`는 구현 완료, 운영 회계 정책 또는 upstream 계약 채택을 뜻하지 않는다.

귀속과 기준 커밋은 supervisor 제공값이다. 개정 작성자는 Codex이며 지정 모델의 CLI 실행·실패 횟수·대체 실행은 확인하거나 주장하지 않는다. 제공 발췌와 허용된 `CAPITAL_DEFAULT_RECOVERY.md`를 근거로 작성했다. 저장소 수정 없이 문서만 제출한다.

## 1. 결정 요약

| item | decision | CAP rows | consumer |
|---|---|---|---|
| `allowance_measurement_basis` | ADOPTED: 건별 실효 원금 × TERMS 단계 bps, 건별 내림 | CAP-04, CAP-13 | `loss-allowance-postings` |
| `allowance_posting_timing` | ADOPTED: 사건·기록된 틱에서 평가, 단계 전이 재생, 차액만 후보 게시 | CAP-04, CAP-13, CAP-14 | `loss-allowance-postings` |
| `allowance_true_up_and_reversal` | ADOPTED: 1190/5100 true-up; 종결·상각 시 단일 환입 | CAP-13 | `loss-allowance-postings` |
| `allowance_after_acceleration_and_default` | ADOPTED: 2,500/10,000 bps; 별도 후보 V2에서 환입 후 총액 상각 | CAP-04, CAP-13 | `loss-allowance-postings` |
| `reserve_pool_3100_3200_appropriation_link` | ADOPTED: 3100→3200 무분개; 풀 목표·부족액 메모 | CAP-04, CAP-13 | `loss-allowance-postings` |
| `recon_check_allowance_vs_risk_reserve` | ADOPTED: 동일 cut의 TERMS 풀 목표와 risk 필요액, 오차 0 | CAP-04, CAP-13, CAP-14 | `loss-allowance-postings` |
| `cut_scope_and_export_section` | ADOPTED: 원본 digest·논리일·정책·전체 KRW 모집단 고정 | CAP-13, CAP-14, CAP-15 | `loss-allowance-postings` |

## 2. KIX 비전 연결

[CAPITAL_REQUIREMENTS_KO.md](../CAPITAL_REQUIREMENTS_KO.md)와 [SEAMS.md](../SEAMS.md)의 제공 발췌에 따라 같은 사실과 정책에서 위험·분개·대사가 재현되도록 한다. 로컬 계산의 성공은 upstream 채택이나 CAP-14/CAP-16의 `NOT_BOUND` 해제를 뜻하지 않는다.

[CAPITAL_ACCOUNTS_TAX_LEGAL.md](CAPITAL_ACCOUNTS_TAX_LEGAL.md)의 제공 발췌에 따라 합성 숫자를 회계·세무 정책 채택 근거로 삼지 않는다. [CAPITAL_DEFAULT_RECOVERY.md](CAPITAL_DEFAULT_RECOVERY.md)의 부도 명령일, 사람 승인, 상각 적격성, 잔여 청구와 준비금 미바인딩 경계를 유지한다.

## 3. 항목별 결정

### 3.1 allowance_measurement_basis

건별 목표액은 `L(a,d) = floor(P(a,d) × bucket_bps / 10000)`이다. KRW 정수로 건별 내림한 뒤 합산한다. 나머지 이월은 없다.

`P`는 FSM outstanding에서 **아직 FSM에 반영되지 않은** 오버레이 원금 회수·상각만 차감한 실효 원금이다. 이미 반영된 상환은 다시 빼지 않는다. 1110 미수 이자·9700 메모는 제외한다. 음수 원금이나 중복 차감은 오류로 실패하며 0으로 숨기지 않는다.

단계 우선순위는 미인출·상각·종결의 0 기초 → DEFAULTED → PAST_DUE_OR_ACCELERATED → T2_PERFORMING → T1_PERFORMING이다. 활성 단계의 설명값은 각각 10,000/2,500/500/150 bps다. 등급은 인출 시 기록된 등급을 사용한다. 종결·상각 증거와 잔여 장부 원금이 모순되면 0 행으로 덮지 않고 실패한다.

정본은 `CAPITAL-TERMS-V1.reserve.provision_bps_of_outstanding`이다. 소비자는 정본을 읽으며 설명값을 기본 설정으로 복제하지 않는다. 정본·등급·원금 증거가 없거나 단계 매핑이 모순되면 `NOT_BOUND`다. 계정은 `CAPITAL-COA-V1`의 기존 코드를 참조한다.

### 3.2 allowance_posting_timing

**cut에서만 측정하지 않는다.** 기록된 각 `sim_day` 틱과 인출·상환·가속·부도 명령·회수·상각·종결 사건에서 목표액을 평가한다. 목표액이 같으면 무분개다. cut 요청은 앞선 측정점의 재생 결과를 조회하며 새로운 게시 사건이 아니다.

시계가 건너뛴 `M*+1` 등의 파생 단계 전이는 해당 논리일에 순서대로 재생한다. 같은 날에는 기존 선지급의 시작일 파생 전이를 먼저, 실제 사건은 원장 순서와 오버레이 anchor·sequence 순으로 처리한다. 같은 날의 복수 사건을 최종 잔액 하나로 합치지 않는다.

실제 사건은 source operation ID, 파생 전이는 `STAGE_TRANSITION:<advance_id>:<sim_day>`로 식별한다. 후보 분개 키에는 정책 버전·advance ID·leg도 포함한다. 필요한 순서 증거가 없으면 실패한다.

늦은 사실은 기록된 시점에 반영하고 유효일을 증거로 보존한다. 이미 발행한 cut은 재작성하지 않는다. 후보 계산은 FSM·오버레이를 **읽기만 하며 쓰지 않는다**. 동일 사실·정책이면 틱 분할이나 반복 조회가 금액 분개열을 바꾸지 않는다.

### 3.3 allowance_true_up_and_reversal

`Δ = L − carried_1190`으로 계산한다.

- `Δ > 0`: `Dr 5100 / Cr 1190`.
- `Δ < 0`: 절댓값으로 `Dr 1190 / Cr 5100`.
- `Δ = 0`: 무분개.

전액 환입 후 재게시는 하지 않는다. 종결은 목표액 0으로 한 번 true-up한다. 상각 사건도 §3.4의 전용 처리에서 한 번 환입하고 일반 true-up을 중복 실행하지 않는다.

각 분개는 advance ID, 등급, 전후 단계, TERMS·COA·충당금 정책 버전, source cut, 논리일, operation ID, leg를 보존한다.

보존식은 `기말1190 = 기초1190 + 충당금 관련 5100 차변순액`이다. 상각 환입은 이미 5100 대변순액에 포함한다. 사건 전체 처리 후 `0 ≤ carried_1190(a) ≤ P(a)`이며, 기초가 0인 전 수명에서 `5100 순액 = 기말1190`이다.

### 3.4 allowance_after_acceleration_and_default

가속 마커와 `M*+1` 중 먼저 도달한 측정점부터 TERMS의 2,500-bps 버킷을 적용한다. 부도 **명령일** `D`부터 10,000-bps 버킷을 적용한다. 부도 적격일 경과만으로 자동 부도 처리하지 않는다. 명령 전에는 연체 버킷을 유지하고 선행 결정의 지연 경고를 따른다. 가속 철회는 도입하지 않는다.

상각 적격일은 `D + CAPITAL-TERMS-V1.default_loss_treatment.writeoff_days_after_default`이며, 기존 운영자 승인·폭포 증거·명령 조건을 유지한다. 적격일만 지나서는 원금이나 충당금을 제거하지 않는다. 부도 후 회수는 원금 배분액만 `P`에서 차감하고 한 번 true-up한다.

**충돌 해소와 버전 경계:** 본 개정은 `CAPITAL-LOSS-ALLOWANCE-V2`, 후보 게시 프로필 `ALLOWANCE_CANDIDATE_V2`를 채택한다. 이 프로필에 한해 선행 `reserve_step_when_unbuilt`와 `digest_and_coa_effect`의 **1190/5100 무분개 규칙을 명시적으로 대체**한다. 기존 `UNBUILT_V1` 경로는 그대로 1190/5100 무분개, `Dr 5200 / Cr 1100` 총액 상각이다.

V2 후보에서는 상각 직전 해당 원금에 대응하는 충당금을 `Dr 1190 / Cr 5100`으로 한 번 환입한 다음, 기존 `Dr 5200 / Cr 1100`을 한 번 표시한다. 원금 상각을 별도로 두 번 생성하지 않는다. 동일 후보에서 V1과 V2 분개를 섞거나 V2 환입을 `UNBUILT_V1` 동작이라고 표시하지 않는다.

원본 entry의 `reserve_step_version=UNBUILT_V1`은 출처로 그대로 보존한다. 별도 V2 후보의 `posting_profile`과 구분하며 기존 entry·cut·골든을 재작성하지 않는다. 과거 사실의 V2 재생은 새 정책으로 식별한 별도 후보이지 과거 발행물의 교체가 아니다. 이는 준비금 원장 바인딩이 아니므로 overlay schema를 올리거나 LOSS_RESERVE를 활성화하지 않는다.

예: T1 원금 100,000,000의 충당금은 1,500,000이다. 40,000,000 상환 후 900,000, 가속 후 15,000,000, 부도 후 60,000,000, 원금 10,000,000 회수 후 50,000,000이다. 잔여 전액 상각 시 V2는 50,000,000을 환입하고 5200에 같은 원금을 게시한다. 기말1190과 전 수명 5100 순액은 0이다. 상각 뒤 회수 `Dr 1000 / Cr 4300`은 충당금을 재생성하거나 잔여 청구를 임의 소멸시키지 않는다.

### 3.5 reserve_pool_3100_3200_appropriation_link

`RESERVE_POOL_MEMO_V1`을 채택한다.

`A = Σ1190 대변잔액`

`F = floor(ΣP × floor_bps / 10000)`

`pool_target_krw = max(A,F)`

`binding_component`는 `ALLOWANCE` 또는 `PORTFOLIO_FLOOR`, 동률은 `ALLOWANCE`다. 후보가 인식한 `funded_krw=0`, `shortfall_krw=pool_target_krw`, `status=MEMO_NOT_POSTED`다.

제공 검토문에 따르면 설명값 100 bps는 TERMS `pool_target` 공식 문자열에 들어 있다. `floor_bps`는 수학 기호이며 신규 TERMS 필드가 아니다. 소비자는 공식·버전의 명시적 해석과 출처를 남긴다. 해석을 검증할 수 없으면 F·풀 목표·부족액은 `NOT_BOUND`다. 100을 기본값으로 쓰거나 A로 대체하지 않는다.

바닥은 전체 모집단에서 한 번 내림한다. 정상 T1 두 건이 각각 66원이면 A=0, F=1, 풀 목표=1이다. 바닥 초과분은 1190에 게시하지 않는다.

`Dr 3100 / Cr 3200`은 게시하지 않는다. 1190은 차감 자산이며 현금 준비금이 아니다. funded 0은 후보의 인식 범위일 뿐 외부 재원 부재의 단정이 아니다. `LOSS_RESERVE`는 `NOT_BOUND`, `absorbed_krw=0`을 유지한다. 실제 적립에는 가용 3100 증거, 3200 분류 검토, 별도 준비금 바인딩 결정이 필요하다.

### 3.6 recon_check_allowance_vs_risk_reserve

동일 cut·모집단·정책 문맥에서 다음을 검사한다.

`max(Σ1190 대변잔액, portfolio_floor_krw) == GET /api/risk reserve.requirement_krw`

허용 오차는 0이다. 결과는 `MATCH`, `MISMATCH`, `CUT_MISMATCH`, 필수 증거 부재의 `NOT_BOUND`이며 뒤의 셋은 통과가 아니다. A·F·지배 구성요소와 `delta_krw = pool_target − requirement`를 출력한다. risk가 건별 충당액을 제공하면 `A == Σ risk 건별 충당액`도 보조 검사한다.

제공 검토문은 기존 risk 필요액을 바닥 없는 건별 합계로 설명한다. 그 동작이면 66원 두 건 사례는 반드시 `MISMATCH`다. 다른 사례의 금액 일치로 TERMS 공식 준수를 추정하지 않는다. 현재 구현 동작은 이 제출에서 재검증하지 않았다.

소비자는 공통 bucket·level·floor 계산과 별도로 손계산 벡터·보존식 검사를 둔다. 양쪽이 같은 계산 오류를 공유한 채 대사만 통과하는 것을 막는다.

### 3.7 cut_scope_and_export_section

cut은 `{f04_state_digest, overlay_digest, overlay_sim_day}`다. 비교 문맥은 `terms_version`, `chart_version`, `allowance_policy_version`, `posting_profile` 및 소비 결정문 digest를 포함한다.

모집단은 한 KRW AssetSpec의 cut 장부 전체 advance ID다. 미인출·종결·상각도 0 행으로 남긴다. 대상 AssetSpec과 정렬된 ID 목록 또는 그 digest를 보존한다. 서로 다른 모집단·정책·cut은 금액이 같아도 비교 통과시키지 않는다.

각 digest가 고정한 원본과 순서를 재구성할 수 있어야 한다. 과거 원본을 확보하지 못하면 `NOT_BOUND`이며 현재 상태에 과거 날짜를 붙이지 않는다.

출력은 후보 allowance 블록·후보 대사·준비금 메모다. `SIMULATED`, `policy_adopted=false`, `NOT_IN_EXPORT_V1`을 표시한다. 기존 export 구성·서명 경계·digest 계산은 유지한다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "loss-allowance-decision",
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-11-10",
  "provisional": true,
  "bases": {
    "capital_main": "a791651",
    "kix_protocol": "347ce44",
    "provenance": "Supervisor supplied; revisions not independently verified.",
    "terms_version": "CAPITAL-TERMS-V1",
    "chart_version": "CAPITAL-COA-V1"
  },
  "allowance_policy_version": "CAPITAL-LOSS-ALLOWANCE-V2",
  "posting_profile": "ALLOWANCE_CANDIDATE_V2",
  "accounting_policy": "SYNTHETIC_UNADOPTED",
  "tax": "NOT_BOUND",
  "policy_adopted": false,
  "consumers": ["loss-allowance-postings"],
  "entries": {
    "allowance_measurement_basis": {
      "status": "ADOPTED",
      "value": {
        "unit": "advance_id",
        "formula": "floor(effective_principal * bucket_bps / 10000); sum rounded levels",
        "bps_ref": "CAPITAL-TERMS-V1.reserve.provision_bps_of_outstanding",
        "bucket_order": ["UNFUNDED_OR_WRITTEN_OFF_OR_CLOSED", "DEFAULTED", "PAST_DUE_OR_ACCELERATED", "T2_PERFORMING", "T1_PERFORMING"],
        "descriptive_bps": [0, 10000, 2500, 500, 150],
        "principal": "FSM outstanding minus overlay principal recoveries and write-offs not already reflected; exclude 1110 and 9700",
        "tier": "Recorded draw tier",
        "invalid": "Fail negative principal, duplicate deductions or contradictory terminal balances; missing source or terms mapping -> NOT_BOUND",
        "runtime_terms": "Read authoritative TERMS; descriptive values are not defaults"
      },
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-10",
      "cap_rows": ["CAP-04", "CAP-13"],
      "rationale": "Preserve TERMS buckets and attributable per-advance principal and rounding.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "allowance_posting_timing": {
      "status": "ADOPTED",
      "value": {
        "measurement": "Every recorded sim_day tick and economic event; replay crossed stage transitions",
        "posting": "Delta only; unchanged ticks and cut requests create no amount postings",
        "events": ["draw", "repayment", "acceleration", "default command", "RECOVERY", "WRITEOFF", "close", "derived M*+1"],
        "order": "Logical day; opening-day transitions for existing advances; journal order with overlay anchor and sequence",
        "identity": "Policy version, advance_id, source operation ID or STAGE_TRANSITION:<advance_id>:<sim_day>, and leg",
        "late_facts": "Apply when recorded; retain effective date; preserve issued cuts",
        "writes": "Read FSM and overlay; no writes",
        "missing_order": "Fail replay"
      },
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-10",
      "cap_rows": ["CAP-04", "CAP-13", "CAP-14"],
      "rationale": "Measure throughout the recorded lifecycle without making report requests or tick frequency economic events.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "allowance_true_up_and_reversal": {
      "status": "ADOPTED",
      "value": {
        "delta": "Target level minus carried 1190 credit balance",
        "increase": "Dr 5100 / Cr 1190",
        "decrease": "Dr 1190 / Cr 5100",
        "zero": "No posting",
        "close": "True-up to zero once",
        "writeoff": "Dedicated V2 release; suppress duplicate generic true-up",
        "full_reversal_and_repost": false,
        "roll_forward": "Closing 1190 = opening 1190 + allowance-related net Dr 5100, including release credits",
        "bounds": "After each complete event: 0 <= carried 1190(a) <= effective_principal(a)",
        "evidence": ["advance_id", "tier", "bucket_from", "bucket_to", "policy_versions", "source_cut", "sim_day", "operation_id", "leg"]
      },
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-10",
      "cap_rows": ["CAP-13"],
      "rationale": "Delta postings provide a direct roll-forward and prevent duplicate releases.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "allowance_after_acceleration_and_default": {
      "status": "ADOPTED",
      "value": {
        "acceleration": "TERMS 2500-bps bucket from recorded acceleration or M*+1, whichever first; no reversal",
        "default": "TERMS 10000-bps bucket from recorded default command D; no automatic default",
        "recovery": "Reduce principal by its allocated recovery once; true-up once",
        "writeoff_eligibility": "D + CAPITAL-TERMS-V1.default_loss_treatment.writeoff_days_after_default; preserve operator authority and waterfall prerequisites",
        "posting_profile": "ALLOWANCE_CANDIDATE_V2",
        "scoped_supersession": {
          "predecessor": "CAPITAL_DEFAULT_RECOVERY.md",
          "entries": ["reserve_step_when_unbuilt", "digest_and_coa_effect"],
          "scope": "Only the prohibition on 1190/5100 postings in the separate V2 candidate",
          "legacy": "UNBUILT_V1 remains no 1190/5100 postings and full principal Dr 5200 / Cr 1100"
        },
        "v2_writeoff": "Release attributable allowance Dr 1190 / Cr 5100 once, then include existing gross Dr 5200 / Cr 1100 once",
        "history": "Preserve source UNBUILT_V1 markers, issued cuts and goldens; identify V2 derivations separately; never mix profiles",
        "reserve": "No reserve binding or overlay schema change",
        "after_writeoff": "Zero allowance on written-off principal; late recovery Dr 1000 / Cr 4300; residual claim retained"
      },
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-10",
      "cap_rows": ["CAP-04", "CAP-13"],
      "rationale": "Explicit versioned supersession resolves the predecessor conflict while preserving legacy replay and command authority.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "reserve_pool_3100_3200_appropriation_link": {
      "status": "ADOPTED",
      "value": {
        "mode": "RESERVE_POOL_MEMO_V1",
        "post_3100_to_3200": false,
        "allowance_component_krw": "Sum 1190 credit balances",
        "portfolio_floor_krw": "floor(sum effective_principal over full cut population * floor_bps / 10000)",
        "floor_source": "CAPITAL-TERMS-V1 pool_target formula string; descriptive 100 bps, not a standalone field or default",
        "pool_target_krw": "max(allowance_component_krw, portfolio_floor_krw)",
        "binding_component": "ALLOWANCE or PORTFOLIO_FLOOR; tie -> ALLOWANCE",
        "funded_krw": 0,
        "shortfall_krw": "pool_target_krw",
        "status": "MEMO_NOT_POSTED",
        "floor_posted_to_1190": false,
        "missing_floor": "Unverifiable formula interpretation -> floor, target and shortfall NOT_BOUND",
        "waterfall": {"step": "LOSS_RESERVE", "status": "NOT_BOUND", "absorbed_krw": 0},
        "future_gate": ["Available 3100 evidence", "Professional review of 3200 classification", "Separate reserve-binding decision"]
      },
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-10",
      "cap_rows": ["CAP-04", "CAP-13"],
      "rationale": "Preserve the TERMS pool floor without inventing funded reserves or equity appropriations.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "recon_check_allowance_vs_risk_reserve": {
      "status": "ADOPTED",
      "value": {
        "check_id": "allowance_vs_risk_reserve",
        "predicate": "Same cut, population and policy context AND max(sum 1190 credit balances, portfolio_floor_krw) == GET /api/risk reserve.requirement_krw",
        "tolerance_krw": 0,
        "outcomes": ["MATCH", "MISMATCH", "CUT_MISMATCH", "NOT_BOUND"],
        "only_pass": "MATCH",
        "components": ["allowance_component_krw", "portfolio_floor_krw", "binding_component"],
        "delta_krw": "pool_target_krw minus risk requirement_krw",
        "auxiliary": "Compare sum 1190 with risk per-advance provisions when supplied",
        "independent_vector": "Two T1 advances of 66 KRW: allowance 0, floor 1, target 1; floorless risk 0 -> MISMATCH",
        "missing_evidence": "NOT_BOUND; never substitute zero",
        "validation": "Shared calculations plus independent arithmetic vectors and roll-forward checks"
      },
      "owner": "Capital Reconciliation Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-10",
      "cap_rows": ["CAP-04", "CAP-13", "CAP-14"],
      "rationale": "Exact comparable-cut reconciliation exposes floor omissions without changing TERMS.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "cut_scope_and_export_section": {
      "status": "ADOPTED",
      "value": {
        "cut": ["f04_state_digest", "overlay_digest", "overlay_sim_day"],
        "policy_context": ["terms_version", "chart_version", "allowance_policy_version", "posting_profile", "decision_note_digest"],
        "population": "All advance IDs for one KRW AssetSpec in the cut ledger; retain unfunded, closed and written-off zero rows",
        "population_evidence": "AssetSpec identifier and sorted advance IDs or their digest",
        "history": "Reconstruct facts and ordering fixed by source digests; unavailable sources -> NOT_BOUND",
        "surfaces": ["candidate allowance block", "candidate reconciliation", "reserve_pool memo"],
        "export": "NOT_IN_EXPORT_V1; preserve legacy construction, signature boundaries and digest calculation",
        "labels": {
          "accounting_policy": "SYNTHETIC_UNADOPTED",
          "tax": "NOT_BOUND",
          "policy_adopted": false,
          "mode": "SIMULATED"
        }
      },
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-10",
      "cap_rows": ["CAP-13", "CAP-14", "CAP-15"],
      "rationale": "Complete source and policy evidence makes candidates reproducible and prevents cross-version comparisons.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

단일 결정 블록에 일곱 `ADOPTED` 항목, non-null value, owner, `professional_review_required=true`, consumer를 명시했다. TERMS bps와 COA 1190/5100/3100/3200을 재사용하며 선행 파일은 수정하지 않는다. 기존 일곱 binding의 item ID와 `loss-allowance-postings` 소비자를 유지하고, 구현 전 상태는 `PENDING_CONSUMER`다.

저장 후 수용 게이트는 decision ledger 파싱, `GET /api/decisions` 노출, `python3 scripts/decision_bindings.py --check`, `python3 scripts/docs_surface.py --check` 및 변경된 pack의 검사다. 이번 문서 제출에서 실행하거나 통과했다고 주장하지 않는다.

**범위 지적에 대한 답변:** 이전 제출의 루트 파일 삭제·검증 기록 정합화 주장은 철회한다. 제공된 2026-11-05 resolution에 따라 그 건은 제품 결정이 아닌 supervisor 통합 사항으로 취급하며, 이 문서에서 다시 미해결 제품 blocker로 선언하지 않는다. 이번 deliverable은 이 결정문 전체뿐이다. 이전의 `DECISION_REQUIRED.md`·`docs/VALIDATION.md` 변경은 이 개정의 일부로 승인하거나 제출하지 않는다. 저장소 전체 diff 정리 완료 여부는 확인하지 않았다.

## 6. Open risks

제품 버킷은 규정상 ECL 단계 준수를 보증하지 않는다. 원금 전용 측정, 상각 시 환입·총액 손실 표시, 3200 분류는 전문가 검토 대상이다. TERMS 바닥 공식 해석과 과거 원본 확보가 실패하면 해당 산출물은 `NOT_BOUND`다. 제공 검토문의 risk 바닥 누락은 소비 구현에서 검증해야 한다. 세무 바인딩·upstream 영수증·운영 승인은 없다.

## 7. 후속 작업

`loss-allowance-postings`는 V2 후보 측정·차액 게시·단일 환입·준비금 메모·대사를 구현한다. `coa-payment-writeoff-postings`와 원금 상각 소유권을 맞춰 같은 상각을 한 번만 표시한다. `portfolio-risk-analytics`는 동일 cut·모집단과 TERMS 풀 목표를 제공한다.

검증에는 T1/T2, 내림·바닥 경계, 동일일 복수 사건, 틱 분할·점프, 늦은 사실, 부도 명령 지연, 상각 단일 환입, 반복 조회, cut·정책 불일치, 증거 누락을 포함한다. `UNBUILT_V1` 기존 재생과 별도 V2 후보를 함께 검사하고, 소비 검증 뒤에만 binding을 구현 완료로 전환한다.
