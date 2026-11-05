# Capital 기대신용손실 충당금 결정 — 측정·게시·환입·준비금·대사

**PROVISIONAL PRODUCT DECISION — 시뮬레이션·제품 설계 전용**

| 항목 | 값 |
|---|---|
| 결정 노드 | `loss-allowance-decision` |
| 지정 결정자·기존 결정 귀속 | Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07) |
| 개정일 | 2026-11-02 |
| 제공된 기준 | Capital main `c4114c7` · kix-protocol `41ace61` |
| 소비 노드 | `loss-allowance-postings` |
| 정책 상태 | `accounting_policy=SYNTHETIC_UNADOPTED`, `policy_adopted=false`, tax `NOT_BOUND` |
| 권한 경계 | `SIMULATED`; 실자금·청약 없음; production `NOT_AUTHORIZED` |

회계·세무·법무 관련 내용은 전문가 검토 전 작업 가정이다. 운영 회계 정책이나 upstream 계약을 채택하지 않는다. `ADOPTED`는 잠정 제품값의 결정이며 구현·검증·운영 승인을 뜻하지 않는다.

이번 개정 작성자는 Codex다. 지정 결정자와 `decided_by`·`provided_by`는 제공된 기존 결정 귀속을 보존하며 해당 모델의 실제 실행을 증명하지 않는다. 근거는 supervisor pack과 제공된 기존 결정문·검토문이다. 기준 커밋은 제공값이며 독립 확인하지 않았다. 저장소 파일 수정이나 검증 명령 실행 없이 전체 문서를 제출한다.

## 1. 결정 요약

| item | decision | CAP rows | consumer |
|---|---|---|---|
| `allowance_measurement_basis` | ADOPTED: 선지급별 실효 원금 × TERMS 버킷 bps, 건별 내림 | CAP-04, CAP-13 | `loss-allowance-postings` |
| `allowance_posting_timing` | ADOPTED: 경제 사건·파생 단계 전이에서 측정; cut까지 순서대로 재생 | CAP-04, CAP-13, CAP-14 | `loss-allowance-postings` |
| `allowance_true_up_and_reversal` | ADOPTED: 1190/5100 차액 게시; 종결 잔액 한 번 환입 | CAP-13 | `loss-allowance-postings` |
| `allowance_after_acceleration_and_default` | ADOPTED: 가속·연체 2,500, 부도 명령 10,000 bps; 상각 전 단일 해제 | CAP-04, CAP-13 | `loss-allowance-postings` |
| `reserve_pool_3100_3200_appropriation_link` | ADOPTED: 3100→3200 무분개; TERMS 풀 목표·부족액은 메모 | CAP-04, CAP-13 | `loss-allowance-postings` |
| `recon_check_allowance_vs_risk_reserve` | ADOPTED: 동일 cut의 풀 목표와 risk 필요액을 허용 오차 0으로 비교 | CAP-04, CAP-13, CAP-14 | `loss-allowance-postings` |
| `cut_scope_and_export_section` | ADOPTED: 상태·오버레이 digest, 논리일, 정책 버전, 전체 KRW 모집단 고정 | CAP-13, CAP-14, CAP-15 | `loss-allowance-postings` |

## 2. KIX 비전 연결

[CAPITAL_REQUIREMENTS_KO.md](../CAPITAL_REQUIREMENTS_KO.md)와 [SEAMS.md](../SEAMS.md)의 제공 발췌에 따라 로컬 시뮬레이션의 재현성과 upstream 채택을 구분한다. 같은 사실·cut·정책 버전에서 위험 측정, 후보 분개와 대사 근거를 재생하도록 결정한다. 대사 성공으로 CAP-14/CAP-16의 `NOT_BOUND`를 바꾸지 않는다.

[CAPITAL_ACCOUNTS_TAX_LEGAL.md](CAPITAL_ACCOUNTS_TAX_LEGAL.md)의 제공 발췌에 따라 합성 숫자를 회계·세무 정책의 증거로 사용하지 않는다. [CAPITAL_DEFAULT_RECOVERY.md](CAPITAL_DEFAULT_RECOVERY.md)의 만기 재기준 `M*`와 부도 **명령일** 기준 상각 적격성을 유지한다. TERMS·COA 상세값은 제공된 기존 결정문과 검토문의 인용에 근거하며 선행 문서를 변경하지 않는다.

## 3. 항목별 결정

### 3.1 allowance_measurement_basis

선지급 `a`, 논리일 `d`의 목표 충당금:

`level(a,d) = floor(effective_principal(a,d) × bucket_bps / 10000)`

KRW 정수로 **건별 내림 후 합산**한다. 합산 원금에 버킷을 적용하거나 나머지를 이월하지 않는다. 단계 우선순위는 미인출·상각·종결의 0 기초, DEFAULTED, PAST_DUE_OR_ACCELERATED, T2_PERFORMING, T1_PERFORMING이다. 활성 버킷의 설명값은 각각 10,000/2,500/500/150 bps다.

정본은 `CAPITAL-TERMS-V1.reserve.provision_bps_of_outstanding`이다. 소비자는 정본을 읽으며 설명값을 독립 설정으로 복제하지 않는다. TERMS 부재나 버킷 매핑 모순은 `NOT_BOUND`다. 계정은 `CAPITAL-COA-V1`의 기존 코드를 참조한다.

실효 원금은 FSM outstanding에서 **FSM에 아직 반영되지 않은** 오버레이 원금 회수·상각만 차감한다. 이미 반영된 상환은 중복 차감하지 않는다. 1110 미수 이자와 9700 메모는 제외한다. 음수 원금·중복 차감은 측정 실패이며 0으로 숨기지 않는다. 등급은 인출 시 기록된 등급으로 고정한다. 필수 등급·원금 증거가 없거나 모순되면 `NOT_BOUND`다.

### 3.2 allowance_posting_timing

매 `sim_day` 틱이나 조회마다 분개하지 않는다. 인출, 상환, 가속 마커, 부도 명령, 회수, 상각, 종결과 `M*+1`의 파생 연체 전이를 측정점으로 삼는다. 각 측정점에서 목표액을 재계산하고 변동액만 게시한다. cut은 이 측정점들을 재생한 결과이며 요청 자체가 분개 원인이 되지 않는다.

시계가 여러 날을 건너뛰면 도달한 파생 전이점을 모두 재생한다. 같은 날에는 기존 선지급의 시작일 파생 전이를 먼저 적용하고 실제 사건은 원장 순서와 오버레이 anchor·sequence에 따른다. 같은 anchor의 사건도 합치지 않는다. 필요한 순서 증거가 없으면 재생 실패다.

파생 ID는 `STAGE_TRANSITION:<advance_id>:<sim_day>`, 실제 사건 ID는 원 operation ID이며 분개 leg를 구분한다. 늦은 사실은 기록된 게시점에 반영하고 유효일을 증거로 보존한다. 이미 발행한 cut은 재작성하지 않는다. 동일 cut·정책 버전은 동일 분개열을 내며 전이 없는 틱은 금액 분개를 만들지 않는다. 후보 계산은 FSM·오버레이를 쓰지 않는다.

### 3.3 allowance_true_up_and_reversal

`Δ = level − carried_1190`으로 정한다.

- `Δ > 0`: `Dr 5100 / Cr 1190`.
- `Δ < 0`: 절댓값으로 `Dr 1190 / Cr 5100`.
- `Δ = 0`: 무분개.

전액 환입 후 재게시는 하지 않는다. 종결 시 남은 충당금을 한 번 환입한다. 각 분개에 advance ID, 등급, 전후 버킷, TERMS·COA·충당금 정책 버전, source cut, 논리일, operation ID와 leg를 남긴다.

보존식은 `기말1190 = 기초1190 + 충당금 관련 5100 차변순액`이다. 상각 전 해제는 이미 5100 대변순액에 포함하므로 별도로 다시 더하지 않는다. 전 수명 기초가 0이면 `5100 순액 = 기말1190`이다. 선지급별 1190은 대변 잔액 또는 0이며 실효 원금을 초과하지 않는다.

### 3.4 allowance_after_acceleration_and_default

기록된 가속 마커와 `M*+1` 중 먼저 도달한 측정점부터 TERMS의 2,500-bps 버킷을 적용한다. 기록된 부도 명령일 `D`부터 10,000-bps 버킷을 적용한다. 부도 적격일 경과만으로 자동 부도 처리하지 않는다. 명령 지연은 경고로 표시하며 연체 버킷을 유지한다. 가속 철회는 도입하지 않는다.

부도 후 원금 회수는 실효 원금 감소와 함께 한 번 true-up한다. 상각은 선행 결정의 `D + TERMS 상각대기일` 적격성과 기록된 운영자 명령을 따른다. 기존 `UNBUILT_V1` 경로에서 `Dr 1190 / Cr 5100`으로 충당금을 한 번 해제한 뒤 기존 원금 상각 `Dr 5200 / Cr 1100`을 유지한다. 일반 true-up과 상각 해제를 중복 실행하지 않는다. 상각 후 기초는 0이며 늦은 회수 `Dr 1000 / Cr 4300`은 충당금을 재생성하지 않는다.

예: T1 원금 100,000,000의 충당금은 1,500,000이다. 원금 40,000,000 상환 후 900,000, 가속 후 15,000,000, 부도 명령 후 60,000,000, 원금 10,000,000 회수 후 50,000,000이다. 잔여 원금 상각 시 충당금 50,000,000을 해제하고 원금 50,000,000을 5200에 게시한다. 전 수명 5100 순액과 기말1190은 모두 0이다.

### 3.5 reserve_pool_3100_3200_appropriation_link

`RESERVE_POOL_MEMO_V1`을 채택한다.

- `allowance_component_krw = Σ1190 대변잔액`.
- `portfolio_floor_krw = floor(Σ effective_principal × floor_bps / 10000)`.
- `pool_target_krw = max(allowance_component_krw, portfolio_floor_krw)`.
- `binding_component`는 `ALLOWANCE` 또는 `PORTFOLIO_FLOOR`; 동률은 `ALLOWANCE`.
- 후보가 인식한 `funded_krw = 0`, `shortfall_krw = pool_target_krw`, `status = MEMO_NOT_POSTED`.

검토문에 따르면 바닥의 100 bps는 TERMS의 **`pool_target` 공식 문자열 안에 있으며 독립 필드가 아니다.** 위 `floor_bps`는 이 문서의 수학 기호이지 기존 TERMS 필드명이나 신규 설정 키가 아니다. 소비자는 해당 공식과 버전에 대한 명시적 해석·출처를 남겨야 한다. 공식 해석을 검증할 수 없으면 바닥·풀 목표·부족액은 `NOT_BOUND`다. 100을 기본값으로 넣거나 Σ1190으로 대체하지 않는다.

바닥은 전체 모집단에서 한 번 내림한다. 정상 T1 두 건이 각 66원이면 건별 충당금은 각각 0, 바닥은 1원, 풀 목표·부족액은 1원이다. 바닥 초과분은 1190에 게시하지 않는다.

`Dr 3100 / Cr 3200`은 게시하지 않는다. 1190은 차감 자산이며 현금 준비금이 아니다. funded 0은 후보가 인식한 재원을 뜻하며 외부 준비금 부재를 단정하지 않는다. 폭포 `LOSS_RESERVE`는 `NOT_BOUND`, `absorbed_krw=0`을 유지한다. 적립 게시에는 가용 3100 증거, 3200 분류의 전문가 검토, 별도 준비금 바인딩 결정과 버전 구현이 필요하다.

### 3.6 recon_check_allowance_vs_risk_reserve

`allowance_vs_risk_reserve`는 동일 cut·모집단·정책 문맥에서 다음을 검사한다.

`max(Σ1190 대변잔액, portfolio_floor_krw) == GET /api/risk reserve.requirement_krw`

허용 오차는 0이다. 결과는 `MATCH`, `MISMATCH`, `CUT_MISMATCH`, 필수 증거 부재의 `NOT_BOUND`다. 마지막 셋은 통과가 아니다. 충당금 구성요소, 바닥, 지배 구성요소와 `delta_krw = pool_target − requirement`를 함께 출력한다. risk가 건별 충당액을 제공하면 `Σ1190 == Σ risk 건별 충당액`도 보조 검사한다.

제공된 검토문은 현 risk 필요액을 바닥 없는 건별 충당금 합계로 설명한다. 그 동작에서는 66원 두 건 사례가 반드시 `MISMATCH`다. 다른 cut에서 금액이 같아도 전체 TERMS 공식 준수를 증명하지 않는다. 불일치를 허용하거나 TERMS를 변경하지 않는다.

소비 구현은 bucket·level·floor 계산을 공용화하되 독립 손계산 벡터와 보존식 검사도 둔다. 동일 코드의 오류가 양쪽에 전파되어 허위 일치를 만들 수 있기 때문이다. 기존 V1 대사·export 검사는 유지한다.

### 3.7 cut_scope_and_export_section

cut은 `{f04_state_digest, overlay_digest, overlay_sim_day}`다. 비교 문맥에 `terms_version`, `chart_version`, `allowance_policy_version`을 포함한다. 충당금 정책 식별자는 `CAPITAL-LOSS-ALLOWANCE-V1`이며 소비 증거에는 실제 결정문 digest도 보존한다.

각 원본 digest가 고정한 사실만 사용한다. 역사 원본을 재구성할 수 없으면 해당 cut은 `NOT_BOUND`다. 최신 상태에 과거 날짜만 붙이지 않는다. 모집단은 하나의 KRW AssetSpec에 속한 cut 장부의 모든 advance ID이며 미인출·종결·상각도 0 행으로 남긴다. 서로 다른 cut을 합치거나 과거 후보를 현재 risk와 비교하지 않는다.

출력은 후보 allowance 블록, 후보 대사와 준비금 메모로 한정한다. `SIMULATED`, `policy_adopted=false`, `NOT_IN_EXPORT_V1`을 표시한다. 기존 export 구성·서명 경계·digest 계산은 변경하지 않는다. export 확대는 별도 버전 결정이다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "loss-allowance-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-11-02",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "bases": {
    "capital_main": "c4114c7",
    "kix_protocol": "41ace61",
    "source": "Supervisor pack and supplied review; not independently verified.",
    "terms_version": "CAPITAL-TERMS-V1",
    "chart_version": "CAPITAL-COA-V1"
  },
  "allowance_policy_version": "CAPITAL-LOSS-ALLOWANCE-V1",
  "accounting_policy": "SYNTHETIC_UNADOPTED",
  "tax": "NOT_BOUND",
  "policy_adopted": false,
  "consumers": ["loss-allowance-postings"],
  "revision_execution": {
    "editor": "Codex",
    "model_execution_verified": false,
    "repository_modified": false,
    "checks_executed": false
  },
  "entries": {
    "allowance_measurement_basis": {
      "status": "ADOPTED",
      "value": {
        "unit": "advance_id",
        "formula": "floor(effective_principal * bucket_bps / 10000); sum rounded advance levels",
        "bps_ref": "CAPITAL-TERMS-V1.reserve.provision_bps_of_outstanding",
        "bucket_order": ["UNFUNDED_OR_WRITTEN_OFF_OR_CLOSED", "DEFAULTED", "PAST_DUE_OR_ACCELERATED", "T2_PERFORMING", "T1_PERFORMING"],
        "descriptive_bps": [0, 10000, 2500, 500, 150],
        "principal": "FSM outstanding minus overlay principal recoveries and write-offs not already reflected; exclude 1110 and 9700.",
        "tier": "Recorded draw tier.",
        "invalid_basis": "Fail negative principal or duplicate deductions; missing or contradictory source evidence -> NOT_BOUND.",
        "runtime_terms": "Resolve authoritative TERMS; never use descriptive bps as independent defaults."
      },
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": ["CAP-04", "CAP-13"],
      "rationale": "Preserve TERMS buckets, explainable per-advance rounding and principal provenance.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "allowance_posting_timing": {
      "status": "ADOPTED",
      "value": {
        "mode": "EVENT_DRIVEN_POSTING_POINTS_FOLDED_TO_CUT",
        "points": ["draw", "repayment", "acceleration marker", "default command", "RECOVERY", "WRITEOFF", "close", "derived M*+1 transition"],
        "order": "sim_day; opening-day derived transitions for existing advances; source journal order with overlay anchor and sequence.",
        "identity": "Source operation ID or STAGE_TRANSITION:<advance_id>:<sim_day>; distinguish legs.",
        "clock_jumps": "Replay crossed transitions; no posting for ticks without transitions.",
        "late_facts": "Apply when recorded; retain effective date; preserve issued cuts.",
        "writes": "Pure candidate derivation; no FSM or overlay writes.",
        "missing_order": "Fail replay."
      },
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": ["CAP-04", "CAP-13", "CAP-14"],
      "rationale": "Economic transitions determine postings independently of tick frequency and report requests.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "allowance_true_up_and_reversal": {
      "status": "ADOPTED",
      "value": {
        "delta": "target level minus carried 1190 credit balance",
        "increase": "Dr 5100 / Cr 1190",
        "decrease": "Dr 1190 / Cr 5100",
        "zero": "no posting",
        "close": "Release remaining balance once.",
        "full_reversal_and_repost": false,
        "roll_forward": "closing 1190 = opening 1190 + allowance-related net Dr 5100, including write-off release credits",
        "bounds": "0 <= carried 1190(a) <= effective_principal(a)",
        "dimensions": ["advance_id", "tier", "bucket_from", "bucket_to", "terms_version", "chart_version", "allowance_policy_version", "source_cut", "sim_day", "operation_id", "leg"]
      },
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": ["CAP-13"],
      "rationale": "Delta postings preserve a direct roll-forward without inflated turnover.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "allowance_after_acceleration_and_default": {
      "status": "ADOPTED",
      "value": {
        "acceleration": "TERMS 2500-bps bucket from recorded acceleration marker or M*+1, whichever first; no acceleration reversal.",
        "default": "TERMS 10000-bps bucket from recorded default command D; eligibility alone does not default.",
        "delayed_default": "Warn and retain past-due bucket until the command.",
        "recovery": "Reduce effective principal and true-up once.",
        "writeoff_day": "D plus TERMS waiting period; eligibility and recorded operator command required.",
        "writeoff": "UNBUILT_V1: release Dr 1190 / Cr 5100 once before existing Dr 5200 / Cr 1100; no duplicate generic release.",
        "after_writeoff": "Zero allowance; late recovery Dr 1000 / Cr 4300 does not recreate allowance."
      },
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": ["CAP-04", "CAP-13"],
      "rationale": "Preserve predecessor command timing and prevent duplicate releases.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "reserve_pool_3100_3200_appropriation_link": {
      "status": "ADOPTED",
      "value": {
        "mode": "RESERVE_POOL_MEMO_V1",
        "post_3100_to_3200": false,
        "allowance_component_krw": "sum 1190 credit balances",
        "portfolio_floor_krw": "floor(sum effective_principal over cut population * floor_bps / 10000)",
        "floor_source": "CAPITAL-TERMS-V1 pool_target formula string; descriptive 100 bps, not a standalone TERMS field.",
        "floor_binding": "Explicit version-aware interpretation with source evidence; no invented field or default.",
        "pool_target_krw": "max(allowance_component_krw, portfolio_floor_krw)",
        "binding_component": "ALLOWANCE or PORTFOLIO_FLOOR; tie -> ALLOWANCE",
        "funded_krw": 0,
        "shortfall_krw": "pool_target_krw - funded_krw",
        "status": "MEMO_NOT_POSTED",
        "floor_posted_to_1190": false,
        "missing_floor": "Missing or unverifiable formula interpretation -> floor, pool target and shortfall NOT_BOUND; no substitution.",
        "waterfall": "LOSS_RESERVE NOT_BOUND; absorbed_krw 0",
        "future_gate": ["available 3100 balance evidence", "professional review of 3200 classification", "separate reserve-binding decision and versioned implementation"]
      },
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": ["CAP-04", "CAP-13"],
      "rationale": "Preserve the TERMS pool floor without inventing a named field, funded reserve or equity appropriation.",
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
        "components": ["allowance_component_krw", "portfolio_floor_krw", "binding_component"],
        "delta_krw": "pool_target_krw minus risk requirement_krw",
        "auxiliary": "Compare sum 1190 with risk per-advance provisions when available.",
        "risk_without_floor": "MISMATCH when floor exceeds allowance; equality elsewhere does not prove formula compliance.",
        "missing_evidence": "NOT_BOUND, never zero or MATCH.",
        "independent_vector": "Two T1 advances of 66 KRW each: allowance 0, floor 1, pool target 1.",
        "implementation": "Shared bucket/level/floor functions plus independent arithmetic vectors and roll-forward checks."
      },
      "owner": "Capital Reconciliation Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": ["CAP-04", "CAP-13", "CAP-14"],
      "rationale": "Exact comparable-cut reconciliation exposes missing floors without overriding TERMS.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "cut_scope_and_export_section": {
      "status": "ADOPTED",
      "value": {
        "cut": ["f04_state_digest", "overlay_digest", "overlay_sim_day"],
        "policy_context": ["terms_version", "chart_version", "allowance_policy_version"],
        "decision_evidence": "Preserve the consumed decision-note digest.",
        "population": "All advance IDs in the cut ledger for one KRW AssetSpec; retain unfunded, closed and written-off zero rows.",
        "history": "Use facts fixed by source digests; unavailable historical sources -> NOT_BOUND.",
        "surfaces": ["candidate allowance block", "candidate reconciliation", "reserve_pool memo"],
        "export": "NOT_IN_EXPORT_V1; preserve legacy construction, signature boundaries and digest calculation.",
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
      "date": "2026-11-02",
      "cap_rows": ["CAP-13", "CAP-14", "CAP-15"],
      "rationale": "Complete source cuts and policy evidence support reproduction without expanding legacy exports.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

결정 블록은 하나이며 일곱 항목 모두 `ADOPTED`, non-null value, owner, `professional_review_required=true`, consumer를 갖는다. TERMS의 150/500/2,500/10,000 bps와 COA 1190/5100/3100/3200을 참조로 재사용한다. 회계 정책은 `SYNTHETIC_UNADOPTED`, tax는 `NOT_BOUND`다.

검토문이 확인한 일곱 `PENDING_CONSUMER` 바인딩의 item ID와 consumer를 유지한다. 저장 후 결정 ledger, `python3 scripts/decision_bindings.py --check`, `python3 scripts/docs_surface.py --check`, pack 재생성·검사와 읽기 전용 `GET /api/decisions` 확인이 필요하다. 본 제출은 현재 바이트의 파싱·HTTP 노출·검사 통과를 주장하지 않는다.

**Blocking finding에 대한 범위 반론:** 오래된 루트 `DECISION_REQUIRED.md`가 merge를 차단한다는 지적은 수용한다. 그러나 최종 명시적 범위는 결정문·바인딩·pack뿐이고 supervisor가 문서를 저장하므로, 이 제출에서 루트 파일 삭제나 `docs/VALIDATION.md` 정정은 허용되지 않는다. “루트 blocker 제거 완료”와 “저장소 전체 diff가 허용 세 범주로 한정됨”이라는 주장은 본 문서에서 명시적으로 부인한다. 검토문이 지적한 저장소 모순은 미해결이며, 이 문서로 해소됐다고 표시해서는 안 된다. 이는 정책 결정의 미완료가 아니라 제출 범위 밖 저장소 정리 사항이다.

## 6. Open risks

TERMS 바닥은 독립 필드가 아닌 공식 문자열이다. 소비자는 해석 증거를 제공해야 하며, 제공할 수 없으면 관련 출력은 `NOT_BOUND`다. 검토문이 보고한 risk 바닥 누락도 소비 구현에서 해결해야 한다.

원금 전용 측정, 상각 표시와 3200 분류는 전문가 검토가 남는다. 제품 버킷이 규정상 ECL 단계를 충족한다고 주장하지 않는다. 과거 COA guard 실패나 HTTP 성공은 이번 개정의 검증 결과가 아니다. upstream 채택·운영 승인 영수증은 없다.

## 7. 후속 작업

`loss-allowance-postings`는 측정·재생·환입·상각 단일 해제·준비금 메모·대사를 구현한다. `portfolio-risk-analytics`는 동일 cut과 TERMS 풀 목표를 제공하고, `coa-payment-writeoff-postings`는 원금 차감과 충당금 해제의 중복을 막는다. 소비 검증 뒤에만 바인딩을 구현 완료로 전환한다.

검증은 T1/T2, 내림·바닥 경계, 같은 날 복수 사건, 시계 점프, 늦은 사실, 부도 명령 지연, 상각 단일 해제, 반복 조회, cut 불일치·증거 누락을 포함한다.

Supervisor의 저장소 정리 작업은 오래된 루트 blocker 삭제와 검증 기록 정합화다. COA guard와 승인된 추가 결정문 범위의 충돌은 정상 검토 흐름에서 해결한다. 테스트·CI·Git reference 변경으로 통과를 가장하지 않는다. 본 문서는 구현·merge·배포 완료를 선언하지 않는다.
