# Capital 기대신용손실 충당금 결정 — 측정·게시·환입·준비금·대사

**PROVISIONAL PRODUCT DECISION — 시뮬레이션·제품 설계 전용.**

| 항목 | 값 |
|---|---|
| 결정 노드 | `loss-allowance-decision` |
| 지정 결정자·기존 결정 귀속 | Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07) |
| 개정일 | 2026-10-30 |
| 제공된 기준 | Capital main `81536bb` · kix-protocol `6dfb03a` |
| 소비 노드 | `loss-allowance-postings` |
| 정책 상태 | `accounting_policy=SYNTHETIC_UNADOPTED`, `policy_adopted=false` |
| 권한 경계 | `SIMULATED`, production `NOT_AUTHORIZED`; tax·legal·operating ledger `NOT_BOUND` |

실자금 이동이나 청약은 없다. 회계·세무 관련 내용은 전문가 검토 전 작업 가정이며 운영 회계 정책이나 upstream 계약의 채택이 아니다. `ADOPTED`는 위임 범위의 잠정 제품값을 뜻하며 구현 완료를 뜻하지 않는다. 모든 항목에 담당 역할과 전문가 검토 플래그를 둔다.

이번 개정 작성자는 Codex다. 지정 결정자 및 JSON의 `decided_by`·`provided_by`는 제공된 기존 결정 귀속을 보존하며, 이번 개정에서 해당 모델을 실행했다는 증명이 아니다. 근거는 supervisor pack, 제공된 기존 결정문과 검토문뿐이다. 잘린 파일의 나머지나 범위 밖 코드를 열지 않았으며 검증 명령을 새로 실행하지 않았다.

## 1. 결정 요약

| item | decision | CAP rows | consumer |
|---|---|---|---|
| `allowance_measurement_basis` | ADOPTED: 선지급별 실효 원금 × TERMS 단계 bps, 건별 내림 | CAP-04, CAP-13 | `loss-allowance-postings` |
| `allowance_posting_timing` | ADOPTED: 경제 사건·파생 전이점에서 측정하고 cut까지 재생 | CAP-04, CAP-13, CAP-14 | `loss-allowance-postings` |
| `allowance_true_up_and_reversal` | ADOPTED: 1190/5100 차액 게시, 종결 시 잔액 환입 | CAP-13 | `loss-allowance-postings` |
| `allowance_after_acceleration_and_default` | ADOPTED: 가속·연체 2,500, 부도 명령 10,000; 상각 전 한 번 해제 | CAP-04, CAP-13 | `loss-allowance-postings` |
| `reserve_pool_3100_3200_appropriation_link` | ADOPTED: 3100→3200 무분개; 풀 목표와 부족액은 메모 | CAP-04, CAP-13 | `loss-allowance-postings` |
| `recon_check_allowance_vs_risk_reserve` | ADOPTED: 동일 cut의 TERMS 풀 목표와 risk 필요액을 허용 오차 0으로 비교 | CAP-04, CAP-13, CAP-14 | `loss-allowance-postings` |
| `cut_scope_and_export_section` | ADOPTED: 이중 digest·논리일·전체 KRW 모집단; 후보 표면에만 노출 | CAP-13, CAP-14, CAP-15 | `loss-allowance-postings` |

## 2. KIX 비전 연결

[CAPITAL_REQUIREMENTS_KO.md](../CAPITAL_REQUIREMENTS_KO.md)와 [SEAMS.md](../SEAMS.md)의 제공 발췌는 로컬 시뮬레이션과 실제 upstream 채택을 구분한다. 이 결정은 같은 사실과 정책 버전에서 위험 측정·후보 장부·감사 행을 재현할 수 있게 한다. 로컬 대사 통과로 CAP-14/CAP-16의 `NOT_BOUND`나 운영 권한을 바꾸지 않는다.

[CAPITAL_ACCOUNTS_TAX_LEGAL.md](CAPITAL_ACCOUNTS_TAX_LEGAL.md)의 제공 발췌에 따라 합성 투영을 회계·세무 정책의 증거로 사용하지 않는다. [CAPITAL_DEFAULT_RECOVERY.md](CAPITAL_DEFAULT_RECOVERY.md)의 `M*` 만기 재기준과 부도 **명령일** 기준 상각 적격성을 유지한다. TERMS·COA의 상세 값은 제공된 기존 결정문과 검토문의 인용을 사용하며 선행 노트 자체를 변경하지 않는다.

## 3. 항목별 결정

### 3.1 allowance_measurement_basis

선지급 `a`, 논리일 `d`의 목표 충당금은 다음과 같다.

`level(a,d) = floor(effective_principal(a,d) × bucket_bps / 10000)`

KRW 정수로 건별 내림한 뒤 합산한다. 원금을 먼저 합산해 충당금을 계산하거나 반올림 나머지를 이월하지 않는다. 우선순위는 미인출·상각·종결의 0 기초, DEFAULTED, PAST_DUE_OR_ACCELERATED, T2_PERFORMING, T1_PERFORMING이다. 활성 단계의 설명값은 각각 10,000/2,500/500/150 bps다.

정본은 `CAPITAL-TERMS-V1.reserve.provision_bps_of_outstanding`이다. 설명값을 별도 런타임 설정으로 복제하지 않는다. TERMS를 읽을 수 없거나 매핑이 충돌하면 `NOT_BOUND`로 내고 추정값으로 계산하지 않는다. 계정은 기존 `CAPITAL-COA-V1`을 참조한다.

실효 원금은 FSM outstanding에서 **FSM에 아직 반영되지 않은** 오버레이 원금 회수·상각만 차감한다. 이미 반영된 상환은 다시 빼지 않는다. 1110 미수 이자와 9700 메모는 제외한다. 음수 기초나 중복 차감은 측정 실패이며 0으로 숨기지 않는다. 등급은 인출 당시 기록된 등급으로 고정하며, 증거 누락·모순은 `NOT_BOUND`다.

### 3.2 allowance_posting_timing

매 `sim_day` 틱이나 조회마다 분개하지 않는다. 인출·상환·가속 마커·부도 명령·회수·상각·종결 및 `M*+1`의 파생 연체 전이를 측정점으로 삼는다. cut 요청은 이 측정점들을 재생하는 순수 계산이며 FSM·오버레이에 사건을 추가하지 않는다.

시계가 여러 날을 건너뛰어도 도달한 파생 전이점을 재생한다. 같은 날에는 기존 선지급의 시작일 파생 전이를 먼저 적용하고 실제 사건을 원장 순서와 오버레이 anchor·sequence로 정렬한다. 같은 anchor의 사건을 합치지 않는다. 필요한 순서 증거가 없으면 재생 실패로 표시한다.

파생 사건 ID는 `STAGE_TRANSITION:<advance_id>:<sim_day>`, 실제 사건 ID는 원 operation ID이며 분개 leg를 별도로 구분한다. 늦은 사실은 기록된 게시점에서 반영하고 유효일을 증거로 보존한다. 이미 발행한 과거 cut은 재작성하지 않는다. 동일 cut과 정책 버전은 동일 분개열을 내며, 전이점이 없는 시계 틱은 금액 분개를 만들지 않는다.

### 3.3 allowance_true_up_and_reversal

`Δ = level − carried_1190`으로 정한다.

- 양수: `Dr 5100 / Cr 1190`.
- 음수: `Dr 1190 / Cr 5100`.
- 0: 무분개.

전액 환입 후 재게시는 하지 않는다. 종결 시 남은 충당금은 한 번 환입한다. 분개에는 선지급, 등급, 전후 버킷, TERMS·COA 버전, source cut, 논리일, operation ID, leg를 남긴다.

보존식은 `기말1190 = 기초1190 + 충당금 관련 5100 차변순액`이다. 상각 전 해제도 5100 대변순액에 포함하므로 해제액을 다시 더하지 않는다. 전 수명 기초가 0이면 `5100 순액 = 기말1190`이다. 선지급별 1190은 대변 잔액 또는 0이며 실효 원금을 초과하지 않는다.

### 3.4 allowance_after_acceleration_and_default

기록된 가속 마커 또는 `M*+1` 중 먼저 도달한 측정점부터 2,500 bps 버킷을 적용한다. 부도 명령일 `D`부터 10,000 bps 버킷이다. 적격일 경과만으로 자동 부도 처리하지 않는다. 부도 명령 지연은 경고로 표시하고 연체 버킷을 유지한다. 가속 철회는 도입하지 않는다.

부도 뒤 원금 회수는 실효 원금 감소와 함께 true-up한다. 상각은 선행 결정의 `D + TERMS 상각대기일` 적격성과 기록된 운영자 명령을 따른다. 기존 `UNBUILT_V1` 경로에서는 해당 충당금을 `Dr 1190 / Cr 5100`으로 한 번 해제한 뒤 기존 원금 상각 `Dr 5200 / Cr 1100`을 유지한다. 일반 true-up과 상각 해제를 중복 실행하지 않는다. 상각 후 충당금 기초는 0이며 늦은 회수 `Dr 1000 / Cr 4300`은 충당금을 재생성하지 않는다.

예를 들어 T1 원금 100,000,000의 충당금은 1,500,000이다. 원금 40,000,000 상환 후 900,000, 가속 후 15,000,000, 부도 명령 후 60,000,000, 원금 10,000,000 회수 후 50,000,000이다. 잔여 원금 상각 시 충당금 50,000,000을 해제하고 원금 50,000,000을 5200에 게시한다. 이 선지급의 전 수명 5100 순액과 기말1190은 모두 0이다.

### 3.5 reserve_pool_3100_3200_appropriation_link

`RESERVE_POOL_MEMO_V1`을 채택한다. 선행 TERMS의 풀 목표 공식과 충당금 구성요소를 구분한다.

- `allowance_component_krw = Σ1190 대변잔액`.
- `portfolio_floor_krw = floor(Σ effective_principal × TERMS 포트폴리오 바닥 bps / 10000)`.
- `pool_target_krw = max(allowance_component_krw, portfolio_floor_krw)`.
- `binding_component`는 `ALLOWANCE` 또는 `PORTFOLIO_FLOOR`이며 동률은 `ALLOWANCE`.
- 후보가 인식한 `funded_krw = 0`, `shortfall_krw = pool_target_krw`, `status = MEMO_NOT_POSTED`.

바닥은 포트폴리오 단위로 한 번 내림한다. 현재 설명값 100 bps는 TERMS에서 읽으며 별도 설정으로 복제하지 않는다. 정상 T1 두 건의 원금이 각 66원이면 건별 충당금은 각각 0, 바닥은 1원, 풀 목표와 부족액은 1원이다. 바닥 초과분은 1190에 게시하지 않는다.

`Dr 3100 / Cr 3200`은 게시하지 않는다. 1190은 차감 자산이며 현금 준비금이 아니다. funded 0은 후보가 인식한 재원으로, 외부 준비금 부재를 단정하지 않는다. 폭포 `LOSS_RESERVE`는 `NOT_BOUND`, `absorbed_krw=0`을 유지한다.

적립 게시에는 가용 3100 잔액 증거, 3200 분류의 전문가 검토, 별도 준비금 바인딩 결정과 버전 구현이 필요하다. TERMS 바닥 정의가 없으면 바닥과 풀 목표는 `NOT_BOUND`이며 Σ1190으로 대체하지 않는다.

### 3.6 recon_check_allowance_vs_risk_reserve

검사 `allowance_vs_risk_reserve`는 같은 cut·모집단·정책 문맥에서 다음을 검증한다.

`max(Σ1190 대변잔액, portfolio_floor_krw) == GET /api/risk reserve.requirement_krw`

허용 오차는 0이다. 결과는 `MATCH`, `MISMATCH`, `CUT_MISMATCH`, 필수 증거 부재의 `NOT_BOUND`이며 마지막 셋은 통과가 아니다. 충당금 구성요소, 바닥, 지배 구성요소, `delta_krw = pool_target − requirement`를 함께 출력한다. risk가 건별 충당액을 제공하면 `Σ1190 == Σ risk 건별 충당액`도 보조 검사한다.

제공된 검토문에 따르면 현 risk 필요액은 포트폴리오 바닥 없는 건별 충당금 합계다. 따라서 바닥이 지배하는 66원 두 건 사례는 반드시 `MISMATCH`다. 두 값이 우연히 같은 cut에서 금액 대사가 통과해도 전체 TERMS 공식 준수를 증명하지 않는다. 이 결정으로 TERMS를 변경하거나 불일치를 허용하지 않는다.

소비자는 bucket·level·floor 함수를 공용화하되 독립 손계산 벡터도 사용한다. 공유 코드에 같은 오류가 있으면 양쪽 금액이 함께 틀릴 수 있기 때문이다. 기존 V1 대사와 export 검사는 유지한다.

### 3.7 cut_scope_and_export_section

cut은 `{f04_state_digest, overlay_digest, overlay_sim_day}`다. 비교 문맥에는 `terms_version`, `chart_version`, `allowance_policy_version`을 추가한다. 각 원본 digest가 고정한 상태와 사실만 사용한다. 과거 원본을 재구성할 수 없으면 해당 역사 cut은 `NOT_BOUND`이며 최신 상태에 과거 날짜만 붙이지 않는다.

모집단은 하나의 KRW AssetSpec에 속한 해당 cut 장부의 모든 advance ID다. 미인출·종결·상각 건도 0 행으로 남긴다. 서로 다른 cut을 합치거나 과거 후보 장부를 현재 risk와 비교하지 않는다.

출력은 후보 `allowance` 블록, 후보 대사, 준비금 메모로 한정한다. `SIMULATED`, `policy_adopted=false`를 표시하며 `NOT_IN_EXPORT_V1`이다. 기존 export 구성·서명 경계·digest 계산을 변경하지 않는다. export 확대는 별도 버전 결정이다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "loss-allowance-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-10-30",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "bases": {
    "capital_main": "81536bb",
    "kix_protocol": "6dfb03a",
    "source": "supervisor-provided context; not independently verified",
    "terms_version": "CAPITAL-TERMS-V1",
    "chart_version": "CAPITAL-COA-V1"
  },
  "accounting_policy": "SYNTHETIC_UNADOPTED",
  "tax": "NOT_BOUND",
  "policy_adopted": false,
  "consumers": ["loss-allowance-postings"],
  "revision_execution": {
    "editor": "Codex",
    "model_execution_verified": false,
    "attribution": "Preserves supplied existing decision attribution; does not attest execution by the named models."
  },
  "entries": {
    "allowance_measurement_basis": {
      "status": "ADOPTED",
      "value": {
        "unit": "advance_id",
        "formula": "floor(effective_principal * bucket_bps / 10000)",
        "bps_ref": "CAPITAL-TERMS-V1.reserve.provision_bps_of_outstanding",
        "bucket_order": ["UNFUNDED_OR_WRITTEN_OFF_OR_CLOSED", "DEFAULTED", "PAST_DUE_OR_ACCELERATED", "T2_PERFORMING", "T1_PERFORMING"],
        "descriptive_bps": [0, 10000, 2500, 500, 150],
        "runtime_bps": "Resolve TERMS; snapshots are not independent configuration.",
        "principal": "FSM outstanding minus overlay principal recoveries and write-offs not already reflected in FSM; exclude 1110 and 9700.",
        "tier": "Recorded draw tier; missing or contradictory evidence -> NOT_BOUND.",
        "invalid_basis": "Fail negative principal or duplicate deductions; never clamp."
      },
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-30",
      "cap_rows": ["CAP-04", "CAP-13"],
      "rationale": "Per-advance rounding preserves explainable balances and the existing reserve schedule.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "allowance_posting_timing": {
      "status": "ADOPTED",
      "value": {
        "mode": "EVENT_DRIVEN_POSTING_POINTS_FOLDED_TO_CUT",
        "points": ["draw", "repayment", "acceleration marker", "default command", "RECOVERY", "WRITEOFF", "close", "derived M*+1 transition"],
        "order": "sim_day; opening-day derived transitions for existing advances; source journal order with overlay anchor and sequence.",
        "identity": "Source operation ID or STAGE_TRANSITION:<advance_id>:<sim_day>; distinguish posting legs.",
        "clock_jumps": "Replay crossed stage transitions; ticks without transitions add no posting.",
        "late_facts": "Apply when recorded; retain effective date; preserve previously issued cuts.",
        "writes": "Pure candidate derivation; no FSM or overlay writes.",
        "missing_order": "Fail replay."
      },
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-30",
      "cap_rows": ["CAP-04", "CAP-13", "CAP-14"],
      "rationale": "Economic transitions determine postings independently of report requests and tick frequency.",
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
        "dimensions": ["advance_id", "tier", "bucket_from", "bucket_to", "terms_version", "chart_version", "source_cut", "sim_day", "operation_id", "leg"]
      },
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-30",
      "cap_rows": ["CAP-13"],
      "rationale": "Delta postings avoid inflated turnover and preserve a direct allowance roll-forward.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "allowance_after_acceleration_and_default": {
      "status": "ADOPTED",
      "value": {
        "acceleration": "TERMS 2500-bps bucket from recorded acceleration marker or M*+1, whichever first; no acceleration reversal.",
        "default": "TERMS 10000-bps bucket from recorded default command D; eligibility alone does not default.",
        "recovery": "Reduce effective principal and true-up once.",
        "writeoff_day": "D plus TERMS waiting period; eligibility and recorded operator command required.",
        "writeoff": "UNBUILT_V1: release Dr 1190 / Cr 5100 once before existing Dr 5200 / Cr 1100; no duplicate generic release.",
        "after_writeoff": "Zero allowance; late recovery Dr 1000 / Cr 4300 does not recreate allowance."
      },
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-30",
      "cap_rows": ["CAP-04", "CAP-13"],
      "rationale": "Recorded commands preserve predecessor timing and prevent duplicate loss recognition.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "reserve_pool_3100_3200_appropriation_link": {
      "status": "ADOPTED",
      "value": {
        "mode": "RESERVE_POOL_MEMO_V1",
        "post_3100_to_3200": false,
        "allowance_component_krw": "sum 1190 credit balances",
        "portfolio_floor_krw": "floor(sum effective_principal over cut population * TERMS reserve portfolio-floor bps / 10000); descriptive bps 100",
        "pool_target_krw": "max(allowance_component_krw, portfolio_floor_krw)",
        "binding_component": "ALLOWANCE or PORTFOLIO_FLOOR; tie -> ALLOWANCE",
        "funded_krw": 0,
        "shortfall_krw": "pool_target_krw - funded_krw",
        "status": "MEMO_NOT_POSTED",
        "floor_posted_to_1190": false,
        "missing_floor": "Floor and pool target -> NOT_BOUND; no substitution.",
        "waterfall": "LOSS_RESERVE NOT_BOUND; absorbed_krw 0",
        "future_gate": ["available 3100 balance evidence", "professional review of 3200 classification", "separate reserve-binding decision and versioned implementation"]
      },
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-30",
      "cap_rows": ["CAP-04", "CAP-13"],
      "rationale": "The TERMS floor remains a pool requirement without inventing funded reserves or equity appropriations.",
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
        "implementation": "Shared bucket/level/floor functions plus independent arithmetic vectors and allowance roll-forward checks."
      },
      "owner": "Capital Reconciliation Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-30",
      "cap_rows": ["CAP-04", "CAP-13", "CAP-14"],
      "rationale": "Exact comparable-cut reconciliation exposes missing portfolio floors without overriding TERMS.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "cut_scope_and_export_section": {
      "status": "ADOPTED",
      "value": {
        "cut": ["f04_state_digest", "overlay_digest", "overlay_sim_day"],
        "policy_context": ["terms_version", "chart_version", "allowance_policy_version"],
        "population": "All advance IDs in the cut ledger for one KRW AssetSpec; retain unfunded, closed and written-off zero rows.",
        "history": "Use facts fixed by the respective source digests; unavailable historical sources -> NOT_BOUND.",
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
      "date": "2026-10-30",
      "cap_rows": ["CAP-13", "CAP-14", "CAP-15"],
      "rationale": "Complete source cuts and version context support reproduction without expanding legacy exports.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

이 문서는 결정 블록 하나, 일곱 `ADOPTED` 항목, 각 항목의 owner·professional-review flag·consumer를 제공한다. TERMS bps와 COA 1190/5100/3100/3200은 참조로 재사용하며 선행 정책을 수정하지 않는다.

제공된 검토문은 이전 버전의 블록 파싱과 일곱 `PENDING_CONSUMER` 바인딩을 확인했다. 이번 개정에서도 항목 ID와 consumer는 유지한다. 이 문서는 아직 supervisor가 저장하기 전인 전체 파일 산출물이므로 현재 개정에 대한 검사 통과나 HTTP 노출을 주장하지 않는다. 저장 후 `python3 scripts/decision_ledger.py`, `python3 scripts/decision_bindings.py --check`, `python3 scripts/docs_surface.py --check` 및 읽기 전용 `GET /api/decisions`로 확인한다. 기존 pack 바이트·digest도 개정문에 맞춰 갱신·검사해야 한다.

**Blocking 지적 처리:** 검토문이 지적한 루트 `DECISION_REQUIRED.md`의 오래된 차단 선언은 삭제 대상이라는 판단을 수용한다. 다만 이번 명시적 편집 범위는 결정문·바인딩·pack뿐이며, 유일한 제출물도 이 문서다. 따라서 해당 파일 삭제나 `docs/VALIDATION.md` 수정은 수행하지 않았고 “제거 완료” 주장도 채택하지 않는다. 이 범위 충돌은 정책 재결정 사유가 아니지만 저장소의 merge blocker는 해소되지 않았다. 담당은 Capital program supervisor / COA test owner다.

## 6. Open risks

TERMS 바닥 필드명과 구현 세부는 직접 확인하지 않았다. 검토문이 보고한 risk의 바닥 누락은 소비 구현에서 해결해야 한다. 원금 전용 측정, 상각 표시, 3200 분류는 전문가 검토가 남으며 제품 버킷이 규정상 ECL 단계를 충족한다고 주장하지 않는다.

과거 기록에 있는 COA blanket guard 실패나 HTTP 성공을 이번 개정의 검증 결과로 승계하지 않는다. 시험·CI·Git reference를 바꿔 통과를 만들지 않는다. upstream 채택·운영 승인 영수증은 없다.

## 7. 후속 작업

`loss-allowance-postings`가 측정, 사건 재생, 환입·상각 순서, 준비금 메모와 대사를 구현한다. `portfolio-risk-analytics`는 동일 cut·정책 문맥과 TERMS 풀 목표를 제공하고, `coa-payment-writeoff-postings`는 원금 차감·충당금 해제의 중복을 막는다. 소비 검증 후에만 바인딩을 구현 완료 상태로 전환한다.

검증에는 T1/T2, 내림과 바닥 경계, 같은 날 복수 사건, 시계 점프, 늦은 사실, 부도 명령 지연, 상각 단일 해제, 반복 조회, cut 불일치·증거 누락을 포함한다. supervisor는 문서 저장·pack 갱신과 별도로 오래된 루트 blocker를 제거하고 필요한 guard 정합을 정상 검토 흐름에서 처리한다. 이번 결정은 구현·merge·배포 완료를 선언하지 않는다.
