# Capital 기대신용손실 충당금 결정 — 측정 기준, 게시 시점, 트루업·환입, 가속·부도 후 처리, 3100→3200 적립 연결, 리스크 대사, 컷 범위

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
이 문서는 KIX-CAPITAL 저장소 안의 **시뮬레이션·제품 설계용** 결정이다. 청약이 아니고 실자금이 움직이지 않으며 production은 계속 `NOT_AUTHORIZED`다. 충당금·상각·환입·적립에 닿는 내용은 **전문가 검토 전의 작업 가정**이며 회계·세무 자문이 아니다. 회계정책 라벨은 `accounting_policy = SYNTHETIC_UNADOPTED`로 유지하고 세무는 `NOT_BOUND`다. 어떤 upstream 계약의 채택도 주장하지 않는다. diff는 `docs/decisions/CAPITAL_LOSS_ALLOWANCE.md` 한 파일이다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `loss-allowance-decision` (Decision: expected-credit-loss allowance mechanics for the COA candidate — timing, basis, reversal, reserve pool link) · deps `accounts-tax-legal-decision`, `portfolio-risk-analytics`, `coa-candidate-projection` · kind `decision` · user_merge `False` |
| 결정자 | **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)** |
| 위임 원문 | 2026-10-08 18:25 KST JunTae Park: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." |
| 결정일 | 2026-10-22 |
| 기준 | KIX-CAPITAL main `5c23989` · kix-protocol `d84cc50` (읽기 전용 `/workspace/capital-run/kixproto-ro`) |
| 읽기 범위 | supervisor pack이 허용한 경로만 읽었다. `CAPITAL_FINANCIAL_TERMS.md`와 `CAPITAL-COA-V1` 본문(`CAPITAL_ACCOUNTS_TAX_LEGAL.md`의 발췌 이후 부분)은 열지 않았다. 충당 bps 네 값(150/500/2500/10000)과 계정 코드 1190/5100/3100/3200은 노드 명세의 인용이며 **두 노트의 값·의미를 바꾸지 않는다**. 이름·숫자가 충돌하면 선행 노트가 이기고, 충당 산식·게시 순서·대사 술어는 이 노트가 이긴다 |
| 숫자 출처 규칙 | bps·대기일·임계값은 `CAPITAL-TERMS-V1` 필드 참조로만 쓴다. 괄호의 값은 설명용 현재 값이다 |
| 상태 어휘 | **ADOPTED** = 위임 범위 안의 잠정 값. **UNDETERMINED** = 값을 정할 수 없어 담당·이유만(`value: null`). 일곱 항목 모두 ADOPTED이며 각 항목에 `owner`와 `professional_review` 플래그를 둔다 |

용어: 금액은 KRW 정수(합성 단위), 날짜는 오버레이 논리 일 `sim_day`, 비율은 bps. 1190 = 충당금(자산 차감), 5100 = 손상비용, 3100 = 적립 원천 자본, 3200 = 손실준비 적립금.

## 1. 결정 요약

| item | 결정 (요지) | CAP rows | 소비 노드 / seam |
|---|---|---|---|
| `allowance_measurement_basis` | **ADOPTED.** 선지급 단위 × 단계 버킷. `required = floor(exposure × bps / 10000)`. 노출 = 후보 장부의 원금 잔액 + 후보에 게시된 이자 채권. 단계는 오버레이 상태의 순수 함수 | CAP-01, CAP-04 | `loss-allowance-postings` |
| `allowance_posting_timing` | **ADOPTED.** 측정은 매 `sim_day`에 가능하되 **게시는 컷에서만**. 컷은 `PERIODIC`(포트폴리오 전체)과 `EVENT`(단계 전이 선지급 한 건) 두 종류 | CAP-01, CAP-13 | `loss-allowance-postings`, `coa-candidate-projection` |
| `allowance_true_up_and_reversal` | **ADOPTED.** 트루업 델타 게시. 증가 Dr 5100 / Cr 1190, 감소 Dr 1190 / Cr 5100. 전액 환입·재게시 없음. 키 `(advance_id, cut_id)` 멱등 | CAP-01, CAP-15 | `loss-allowance-postings` |
| `allowance_after_acceleration_and_default` | **ADOPTED.** ACCELERATED → 가속 버킷, DEFAULTED → 전액 버킷(10000), 상각일에 1190 소진 후 부족분 5100. 상각 후 회수는 Cr 5100 | CAP-01, CAP-04 | `loss-allowance-postings`, `overlay-recovery-writeoff` |
| `reserve_pool_3100_3200_appropriation_link` | **ADOPTED.** 후보 장부에 **게시**(메모 아님). `PERIODIC` 컷에서 Dr 3100 / Cr 3200 = `max(0, target − 3200잔액)`, 하락 시 역분개. 3100 잔액 초과분은 `RESERVE_SHORTFALL` 메모 | CAP-01, CAP-20 | `loss-allowance-postings`, `portfolio-risk-analytics` |
| `recon_check_allowance_vs_risk_reserve` | **ADOPTED.** 같은 컷의 `GET /api/risk` `reserve.requirement_krw`와 1190 잔액 **정수 일치**, 3200 잔액 = `min(requirement, 3100 가용)`. 허용오차 0. 불일치는 `ALLOWANCE_RECON_MISMATCH` 라벨, 자동 보정 없음 | CAP-04, CAP-13 | `loss-allowance-postings`, `portfolio-risk-analytics` |
| `cut_scope_and_export_section` | **ADOPTED.** `PERIODIC` 컷 = 한 `sim_day`의 후보 전체 스냅샷(일관 읽기), `EVENT` 컷 = 선지급 한 건. export에 추가형 섹션 `loss_allowance`(format `KIX_CAPITAL_LOSS_ALLOWANCE_V1`), 레거시 export 바이트 불변 | CAP-13, CAP-15, CAP-20 | `loss-allowance-postings`, export manifest |

## 2. KIX 비전과의 연결

읽은 팩 경로와 적용이다.

- **`/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md`** — A-4 "기록과 재생의 분리"와 "늦은 사실은 현재 권한으로 대사"가 이 노트의 뼈대다. 충당금은 **상태의 순수 함수로 측정**하고 **컷에서만 게시**해 재생 시 같은 입력이 같은 게시를 낸다. 컷 이후 도착한 늦은 사실은 다음 컷에서 델타로 대사하며 과거 게시를 지우지 않는다.
- **`/workspace/capital-run/kixproto-ro/README.md`** — "정책 값·새 명령은 DECISION_REQUIRED, 외부 답변 의존 값은 담당을 명시한 UNDETERMINED" 어휘를 그대로 따른다. 실자금·실 제공자·운영 엔드포인트는 열지 않는다.
- **`docs/decisions/CAPITAL_DEFAULT_RECOVERY.md`** — 가속 = 만기 재기준 `M*`, 상각 적격일 = `default_sim_day + 상각 대기일`, 상각은 운영자 명령이라는 규칙을 충당 단계 전이의 입력으로 쓴다. 이 노트는 그 날짜를 다시 정하지 않는다.
- **`docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md`** — `SIMULATION_FIXED_V1` 합성 계정과 `SYNTHETIC_UNADOPTED`, `WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW` 라벨을 상속한다. 기존 golden(debit = credit = 385,000)은 바이트 불변이다.
- **`docs/decisions/CAPITAL_DEMO_BOOK.md`** — T1/T2 등급별 충당 bps 분기가 live fixture로 바인딩돼야 한다는 요구가 측정 기준(등급 버킷)의 근거다. `SYNTHETIC_FIXTURE_PROFILE` 라벨 규칙을 export 섹션에 적용한다.
- **`docs/decisions/CAPITAL_CLAIM_SLICE_REGISTRY.md`**, **`CAPITAL_CLOSEOUT_ARTIFACT.md`** — "숫자를 복사하지 않고 필드명으로 인용", "per-run 필드를 뺀 결정론적 다이제스트" 규칙을 export 섹션 설계에 적용한다.
- **`docs/SEAMS.md`**, **`docs/VALIDATION.md`**, **`docs/CAPITAL_REQUIREMENTS_KO.md`** — 로컬 포트는 `NOT_BOUND` 스탠드인이며 SEMANTIC_CONFORMANCE가 아니라는 경계를 유지한다.

## 3. 항목별 결정

공통: `basis = PRODUCT_DECISION`, `provisional = true`, `professional_review = WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW`, `owner = loss-allowance-postings`(구현) / 위임 결정자(정책).

### 3.1 allowance_measurement_basis (CAP-01, CAP-04)

- **값.** 선지급(advance) 단위로 측정한다. `required_krw(advance, sim_day) = floor(exposure_krw × bps(stage) / 10000)`. 노출(`exposure_krw`) = 후보 장부의 원금 잔액 + 후보에 **이미 게시된** 이자 채권. 부도 후 연체 가산(`CAPITAL-TERMS-V1` 연체 가산 bps)으로 생기는 이자는 메모이며 노출에 넣지 않는다. 그림자 수취인 줄·슬라이스·미인출 한도는 노출이 아니다.
- **단계 사다리.** `CURRENT_T1` → `CAPITAL-TERMS-V1` T1 충당 bps(150), `CURRENT_T2` → T2 충당 bps(500), `ACCELERATED` → 가속 충당 bps(2500), `DEFAULTED` → 전액(10000), `WRITTEN_OFF` → 노출 0. 단계는 오버레이 상태(`REBASED`/`NOT_ACCELERATED`, `default_sim_day`, 상각 기록)의 순수 함수이고 운영자가 단계를 직접 지정하지 않는다. `CAPITAL-TERMS-V1`의 매핑이 다르면 TERMS가 이긴다.
- **근거.** 포트폴리오 집계 비율은 등급·가속·부도 분기를 fixture로 바인딩하지 못한다(DEMO_BOOK §3.4). 선지급 단위 floor는 합계가 결정론적이고 리스크 엔드포인트와 같은 규칙을 공유할 수 있다.
- **대안.** 집계 단위 측정: 대사 불능이라 기각. 시간 경과 기반 단계(연체 일수 버킷): 슬라이스 노트가 이미 `null`로 둔 영역이라 V1에서는 가속·부도 **명령**만 전이로 쓴다.

### 3.2 allowance_posting_timing (CAP-01, CAP-13)

- **값.** `required_krw`는 어떤 `sim_day`에도 계산 가능하지만 **1190/5100 게시는 컷에서만** 일어난다. 컷은 두 종류다. (1) `PERIODIC`: 운영자 명령 또는 export/closeout이 여는 포트폴리오 전체 컷. (2) `EVENT`: 가속·부도·상각 명령이 그 선지급 한 건에 자동으로 여는 컷. 매 tick 자동 게시는 없다.
- **근거.** A-4의 기록/재생 분리: 측정은 재생 가능한 함수, 게시는 명시적 컷 사실. tick마다 게시하면 golden digest가 시계에 종속된다.
- **대안.** 컷만(이벤트 컷 없음): 가속·부도 직후 충당이 다음 periodic 컷까지 비는 구간이 생겨 기각.

### 3.3 allowance_true_up_and_reversal (CAP-01, CAP-15)

- **값.** 컷마다 `delta = required_krw − carried_krw`(carried = 그 선지급의 1190 누적). `delta > 0`: Dr 5100 / Cr 1190. `delta < 0`: Dr 1190 / Cr 5100(같은 비용 계정으로 환입, 별도 환입 계정 없음). `delta = 0`: 분개 없음. 전액 환입 후 재게시는 금지. 게시 키는 `(advance_id, cut_id)`이며 같은 키 재실행은 no-op(멱등). 컷 이후 도착한 늦은 사실은 과거 컷을 수정하지 않고 다음 컷의 델타로 흡수한다.
- **근거.** 델타 게시는 분개 수가 적고 digest가 안정적이며 A-4의 "과거 사실은 당시 의미로 보존" 규칙에 맞는다.
- **대안.** 전액 환입·재게시: 매 컷 분개 두 줄이 늘고 비용 총액이 부풀어 기각.

### 3.4 allowance_after_acceleration_and_default (CAP-01, CAP-04)

- **값.** (1) 가속 명령(`M*` 재기준, DEFAULT_RECOVERY) → `EVENT` 컷, 단계 `ACCELERATED`, 가속 bps로 델타 게시. (2) 부도 명령(`default_sim_day`) → `EVENT` 컷, 단계 `DEFAULTED`, 전액 bps로 델타 게시(1190 = 노출). (3) 상각 적격일(`default_sim_day + 상각 대기일`, TERMS 필드) 이후 운영자 상각 명령 → `EVENT` 컷: Dr 1190 / Cr 채권 = 상각 노출, 1190이 부족하면 부족분 Dr 5100. 상각 후 단계 `WRITTEN_OFF`, 노출 0, carried 0. (4) 상각 **후** 회수(DEFAULT_RECOVERY 회수 폭포가 정하는 금액)는 Cr 5100으로 게시한다(V1에 별도 회수이익 계정 없음). 상각 **전** 회수는 노출을 줄이므로 다음 컷의 델타로 자연 반영된다. (5) 가속 철회·부도 철회는 선행 노트대로 없으므로 단계는 단조 증가한다.
- **근거.** 상각일·가속일은 선행 노트가 이미 정했다. 충당은 그 사실을 소비만 한다.
- **대안.** 부도 시 즉시 상각: 선행 노트의 90일 대기와 충돌해 기각.

### 3.5 reserve_pool_3100_3200_appropriation_link (CAP-01, CAP-20)

- **값.** 적립은 후보 장부에 **게시**한다(메모 아님). `PERIODIC` 컷에서만: `target = min(risk.reserve.requirement_krw, balance_3100_before)`, `delta = target − balance_3200`. `delta > 0`: Dr 3100 / Cr 3200. `delta < 0`: Dr 3200 / Cr 3100. `EVENT` 컷에서는 적립을 건드리지 않는다. `requirement_krw > balance_3100_before`이면 초과분을 `RESERVE_SHORTFALL` 메모로 export에 적는다. 적립은 자본 내부 이동이라 손익·자산 합계에 영향이 없고 `OBLIGATION_CONSERVATION`을 깨지 않는다. 라벨 `APPROPRIATION_SYNTHETIC`.
- **근거.** 게시해야 3200 잔액이 대사 술어의 피연산자가 된다. 메모로 두면 리스크 요구량과 장부가 영원히 분리된다.
- **대안.** 메모 유지: 대사 불능이라 기각. 1190과 3200을 같은 금액으로 묶기: 자산 차감과 자본 적립은 성격이 달라 두 술어로 분리한다.

### 3.6 recon_check_allowance_vs_risk_reserve (CAP-04, CAP-13)

- **값.** 같은 `cut_id`·같은 `sim_day`·같은 오버레이 스냅샷(일관 읽기)에서 (a) `balance_1190 == risk.reserve.requirement_krw`, (b) `balance_3200 == min(requirement_krw, balance_3100_before)`. 두 술어 모두 **정수 정확 일치, 허용오차 0**. 이를 위해 `GET /api/risk`는 이 노트의 산식(선지급 단위 floor, 같은 노출 정의, 같은 단계 사다리)을 써야 한다. `EVENT` 컷은 (a)만 그 선지급 범위로 검사한다. 불일치는 `ALLOWANCE_RECON_MISMATCH`와 원인 코드(`ROUNDING`, `EXPOSURE_BASIS`, `STAGE_DISAGREEMENT`, `STALE_SNAPSHOT`)로 export에 기록하고 **자동 보정하지 않는다**.
- **근거.** 허용오차를 두면 산식 불일치가 숨는다. 합성 정수 장부에서 0 오차는 달성 가능하다.
- **대안.** 1원 허용오차: 반올림 차이를 영구 은폐해 기각.

### 3.7 cut_scope_and_export_section (CAP-13, CAP-15, CAP-20)

- **값.** `PERIODIC` 컷 범위 = 후보 전체(모든 선지급·3100/3200)를 한 `sim_day`의 단일 스냅샷으로 읽는다. `EVENT` 컷 범위 = 선지급 한 건. `cut_id = sha256(canonical(sim_day, cut_kind, scope_ids))` 접두 16자로 결정론적. export에 추가형 섹션 `loss_allowance`를 둔다: `{format: KIX_CAPITAL_LOSS_ALLOWANCE_V1, cut_id, sim_day, cut_kind, rows:[{advance_id, stage, exposure_krw, bps_ref, required_krw, carried_krw, delta_krw}], totals, appropriation:{target, delta, shortfall}, recon:{ok, mismatch_codes}, labels:{accounting_policy: SYNTHETIC_UNADOPTED, tax: NOT_BOUND, professional_review: WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW, funds_executed: false}}`. `instance_id`·시각은 넣지 않는다. 레거시 `capital/export.py` 바이트와 `tests/golden/demo.json`은 불변이며 섹션은 소비 노드가 어댑터로 덧붙인다.
- **근거.** CLOSEOUT_ARTIFACT의 결정론 규칙과 `tests/test_coa_candidate.py` 바이트 가드.
- **대안.** 레거시 export 안에 필드 삽입: 바이트 가드 위반이라 기각.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "loss-allowance-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-10-22",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "scope": "KIX-CAPITAL simulation and product design only; not an accounting policy adoption; accounting_policy stays SYNTHETIC_UNADOPTED; tax NOT_BOUND; no real money; production NOT_AUTHORIZED",
  "bases": {"capital_main": "5c23989", "kix_protocol": "d84cc50", "vendor_pin_commit": "7481b0e16ce9b903abbffa62249bb91cd9e63cfe"},
  "reuses": {"terms": "CAPITAL-TERMS-V1 reserve bps by field reference (illustrative 150/500/2500/10000)", "coa": "CAPITAL-COA-V1 codes 1190/5100/3100/3200 unchanged"},
  "consumer": "loss-allowance-postings",
  "upstream_adoption_claimed": false,
  "entries": {
    "allowance_measurement_basis": {
      "status": "ADOPTED",
      "value": {"unit": "per_advance", "formula": "required_krw = floor(exposure_krw * bps(stage) / 10000)", "exposure": "principal outstanding + interest receivable already posted in candidate; post-default delinquency add-on, shadow payee lines, slices and undrawn limits excluded", "stage_ladder": {"CURRENT_T1": "CAPITAL-TERMS-V1 T1 reserve bps", "CURRENT_T2": "CAPITAL-TERMS-V1 T2 reserve bps", "ACCELERATED": "CAPITAL-TERMS-V1 accelerated reserve bps", "DEFAULTED": "10000", "WRITTEN_OFF": "exposure 0"}, "stage_source": "pure function of overlay state (REBASED/NOT_ACCELERATED, default_sim_day, write-off record); no manual stage override", "conflict_rule": "CAPITAL-TERMS-V1 mapping wins on bps"},
      "owner": "loss-allowance-postings",
      "professional_review": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Per-advance floor on a stage bucket binds tier, acceleration and default branches on live fixtures and yields a deterministic sum the risk endpoint can share.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "allowance_posting_timing": {
      "status": "ADOPTED",
      "value": {"measure": "computable at any sim_day", "post": "only at a cut", "cut_kinds": {"PERIODIC": "operator command or export/closeout; whole candidate book", "EVENT": "auto-opened by acceleration, default or write-off command for the affected advance only"}, "per_tick_posting": false},
      "owner": "loss-allowance-postings",
      "professional_review": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-01", "CAP-13"],
      "rationale": "Measurement stays a replayable function and posting stays an explicit cut fact (AUTHORITY_MODEL_1 A-4); event cuts avoid an unprovisioned gap after acceleration or default.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "allowance_true_up_and_reversal": {
      "status": "ADOPTED",
      "value": {"method": "delta true-up", "increase": "Dr 5100 / Cr 1190", "decrease": "Dr 1190 / Cr 5100", "zero_delta": "no entry", "full_reversal_and_repost": false, "idempotency_key": "(advance_id, cut_id)", "late_facts": "absorbed as delta at the next cut; prior cuts never rewritten"},
      "owner": "loss-allowance-postings",
      "professional_review": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-01", "CAP-15"],
      "rationale": "Delta posting keeps entry counts and digests stable and preserves past postings as recorded facts.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "allowance_after_acceleration_and_default": {
      "status": "ADOPTED",
      "value": {"on_acceleration": "EVENT cut; stage ACCELERATED; delta at accelerated bps on exposure at M* rebase", "on_default": "EVENT cut at default_sim_day; stage DEFAULTED; 1190 raised to full exposure", "on_write_off": "operator command on/after default_sim_day + CAPITAL-TERMS-V1 write-off wait; Dr 1190 / Cr receivable for exposure; shortfall Dr 5100; stage WRITTEN_OFF, carried 0", "recovery_before_write_off": "reduces exposure; reflected as delta at next cut", "recovery_after_write_off": "Cr 5100 per CAPITAL_DEFAULT_RECOVERY waterfall amount; no separate recovery account in V1", "stage_monotonic": true},
      "owner": "loss-allowance-postings",
      "professional_review": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Acceleration, default and write-off days are already decided in CAPITAL_DEFAULT_RECOVERY; the allowance only consumes those facts and never re-dates them.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "reserve_pool_3100_3200_appropriation_link": {
      "status": "ADOPTED",
      "value": {"posted_in_candidate": true, "memo_only": false, "when": "PERIODIC cuts only", "target": "min(risk.reserve.requirement_krw, balance_3100_before)", "increase": "Dr 3100 / Cr 3200", "decrease": "Dr 3200 / Cr 3100", "shortfall": "requirement above 3100 balance recorded as RESERVE_SHORTFALL memo", "label": "APPROPRIATION_SYNTHETIC", "pnl_effect": "none; equity-internal"},
      "owner": "loss-allowance-postings",
      "professional_review": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-01", "CAP-20"],
      "rationale": "Posting the appropriation makes the 3200 balance a reconcilable operand; a memo would leave the risk requirement and the book permanently unlinked.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "recon_check_allowance_vs_risk_reserve": {
      "status": "ADOPTED",
      "value": {"same_cut": "same cut_id, sim_day and overlay snapshot (consistent read)", "predicate_a": "balance_1190 == risk.reserve.requirement_krw", "predicate_b": "balance_3200 == min(requirement_krw, balance_3100_before)", "tolerance_krw": 0, "event_cut_scope": "predicate_a over the affected advance only", "risk_endpoint_obligation": "GET /api/risk must use this note's formula, exposure basis and stage ladder", "on_mismatch": {"label": "ALLOWANCE_RECON_MISMATCH", "codes": ["ROUNDING", "EXPOSURE_BASIS", "STAGE_DISAGREEMENT", "STALE_SNAPSHOT"], "auto_correct": false}},
      "owner": "loss-allowance-postings",
      "professional_review": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-04", "CAP-13"],
      "rationale": "Zero tolerance on an integer synthetic ledger is achievable and exposes formula drift instead of hiding it.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "cut_scope_and_export_section": {
      "status": "ADOPTED",
      "value": {"periodic_scope": "whole candidate book at one sim_day single snapshot", "event_scope": "one advance", "cut_id": "sha256(canonical(sim_day, cut_kind, scope_ids))[:16]", "export_section": "loss_allowance", "format": "KIX_CAPITAL_LOSS_ALLOWANCE_V1", "fields": ["cut_id", "sim_day", "cut_kind", "rows[advance_id, stage, exposure_krw, bps_ref, required_krw, carried_krw, delta_krw]", "totals", "appropriation{target, delta, shortfall}", "recon{ok, mismatch_codes}", "labels{accounting_policy: SYNTHETIC_UNADOPTED, tax: NOT_BOUND, professional_review, funds_executed: false}"], "excluded": ["instance_id", "wall-clock"], "legacy_export_bytes": "BYTE_IDENTICAL; section added by consumer adapter", "existing_goldens": "BYTE_IDENTICAL"},
      "owner": "loss-allowance-postings",
      "professional_review": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-13", "CAP-15", "CAP-20"],
      "rationale": "A deterministic, additive section honours the export byte guard and the closeout-digest determinism rule while keeping every allowance number labelled synthetic.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| 수용 기준 | 충족 위치 |
|---|---|
| `CAPITAL_LOSS_ALLOWANCE.md`에 `capital-decision-v1` 블록 하나, `decision_ledger.py` 파싱, `GET /api/decisions` 표시 | §4 블록 하나뿐. 일곱 entry 모두 `status`·`value`·`provided_by`·ISO `date`·`cap_rows` 보유 |
| `CAPITAL-TERMS-V1` 충당 bps와 `CAPITAL-COA-V1` 코드 재사용, 두 노트 불변 | §3.1 단계 사다리는 TERMS 필드 참조, 코드 1190/5100/3100/3200은 그대로 인용. 두 노트의 diff 없음 |
| 각 항목 ADOPTED/UNDETERMINED + owner + 전문가 검토 플래그, `SYNTHETIC_UNADOPTED` 유지 | 모든 entry에 `owner`·`professional_review`, 블록 `scope`와 §3.7 labels |
| consumer `loss-allowance-postings` 명시, `decision_bindings.py --check` 통과 | 블록 `consumer` 필드와 §1 표. 실제 실행 확인은 supervisor·PR CI가 한다 |

## 6. Open risks

- **리스크 엔드포인트 산식 일치.** `GET /api/risk`가 다른 반올림·노출 정의를 쓰면 대사는 항상 실패한다. 의도된 설계이지만 `portfolio-risk-analytics` 쪽 수정이 선행돼야 한다.
- **TERMS 매핑 미확인.** 결정자가 `CAPITAL_FINANCIAL_TERMS.md`를 직접 열지 않았다. 150/500/2500/10000의 단계 배정이 TERMS와 다르면 TERMS가 이기고 §3.1 사다리만 고친다.
- **3100 잔액 부족.** 합성 장부에서 3100이 요구량보다 작으면 `RESERVE_SHORTFALL`만 남는다. 자본 보충 명령은 V1 범위 밖이다.
- **회수 계정 단순화.** 상각 후 회수를 5100 환입으로 처리한 것은 작업 가정이다. 전문가 검토에서 별도 계정이 요구되면 COA 개정 노드가 필요하다.
- **시간 기반 단계 부재.** 연체 일수 버킷이 없어 가속·부도 명령 전에는 충당이 T1/T2 수준에 머문다.

## 7. 후속 작업

- `loss-allowance-postings`(구현 노드): §3 산식·컷·분개·export 섹션 구현, 새 golden은 별도 파일, 레거시 export·golden 바이트 불변 검증.
- `portfolio-risk-analytics`: `reserve.requirement_krw`를 이 노트 산식으로 정렬하고 컷 일관 읽기에 묶기.
- `scripts/docs_surface.py`·README needle: 새 export 섹션·벡터 추가 시 수동 등록.
- 전문가 검토 입력: 충당 노출 정의, 환입 계정, 적립 게시 성격을 검토 항목으로 전달. upstream 노드 완료 표시 없음.
