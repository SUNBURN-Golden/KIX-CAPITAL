# Capital 데모 북 프로필 결정 — 합성 청구 액면, 수취인 구조, 수익자 매핑, 등급 커버리지, 포트폴리오 규모, golden digest 정책, 정직한 라벨

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
이 문서는 KIX-CAPITAL 저장소 안의 **시뮬레이션·제품 설계용** 결정이다. 모든 값은 **합성 fixture 프로필(`SYNTHETIC_FIXTURE_PROFILE`)** 이지 제품 조건·청약·upstream 정책이 아니다. 실자금이 움직이지 않으며 production은 계속 `NOT_AUTHORIZED`다. 어떤 upstream 계약의 채택도 주장하지 않는다. 이 문서는 `capital/`·`tests/`·vendor 바이트를 바꾸지 않고, diff는 `docs/decisions/` 한 파일이다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `demo-book-profile-decision` (Decision: synthetic demo book profile) · deps `financial-terms-decision`, `settlement-policy-decision`, `accounts-tax-legal-decision` · kind `decision` · user_merge `False` |
| 결정자 | **Devin swe-2 (RO by prompt), delegated by JunTae 2026-10-08 (model 10-14 10:07)** |
| 위임 원문 | 2026-10-08 18:25 KST JunTae Park: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." |
| 결정일 | 2026-10-14 |
| KIX-CAPITAL 기준 | main `8787278`. 선행 결정은 [CAPITAL_FINANCIAL_TERMS.md](CAPITAL_FINANCIAL_TERMS.md)(`CAPITAL-TERMS-V1`), [CAPITAL_SETTLEMENT_POLICY.md](CAPITAL_SETTLEMENT_POLICY.md)(`CAPITAL-ALLOC/REFUND/REVSHARE/CLAIM-PURCHASE/RESIDUAL-V1`), [CAPITAL_ACCOUNTS_TAX_LEGAL.md](CAPITAL_ACCOUNTS_TAX_LEGAL.md)(`CAPITAL-COA/REVREC/TAX/LICENCE/RETENTION-V1`)이며 이 문서는 그 위에 쌓는다 |
| kix-protocol 기준 | main `adcddc5` (읽기 전용 `/workspace/capital-run/kixproto-ro`). vendor pin `7481b0e16ce9b903abbffa62249bb91cd9e63cfe` 불변 |
| 한도 출처 규칙 | 이 문서는 한도·비율·임계값 숫자를 **복사하지 않는다.** 모든 cap은 `CAPITAL-TERMS-V1` `underwriting_depth`의 필드명으로 **인용**한다(`single_advance_cap_krw`, `beneficiary_aggregate_cap_krw`, `portfolio_cap_krw`, `two_person_threshold_krw`). fixture 액면은 그 cap의 배수로 설계했으며 노트에 정수로 적은 값은 `CAPITAL-TERMS-V1` 해석상 합성 단위다 |
| 상태 어휘 | **ADOPTED** = 위임 범위 안의 잠정 값. 일곱 항목 모두 ADOPTED다 |

## 1. 결정 요약

| item | 결정 (요지) | CAP rows | 소비 노드 / seam |
|---|---|---|---|
| `fixture_face_values` | **ADOPTED.** 프로필 `CAPITAL-DEMO-BOOK-V1`: 합성 청구 10건·수익자 5명, 총 액면 22,850,000,000(약 `1.14 × portfolio_cap`), 최대 단일 청구 8,000,000,000. 기존 fixture-v1 세 건은 **바이트 불변**, 프로필은 추가형 후보 | CAP-01, CAP-04 | 미래 `demo-book-seed` 구현 노드 → `terms-overlay`·`underwriting` 조회 |
| `payee_structure` | **ADOPTED.** 온-FSM 수취인은 고정 `PRIMARY_FEE_BPS` 2수취인(`residual_payee: organizer`, `fee_payee: platform`, `fee_bps 500`) 그대로. 클래스 ①·③ 커버리지는 `SHADOW_PAYEE_LINES` 메타데이터(`SHADOW_NOT_APPLIED`)로만 | CAP-02, CAP-05 | `policy-simulator` 그림자 계산 → upstream `fin-multi-payee-refund-proof` |
| `beneficiary_payee_map` | **ADOPTED.** `{"fixture-organizer": ["organizer"]}`를 유지하고 합성 수익자 5명을 같은 `organizer` 라벨에 매핑. `venue`·`agency` 라벨은 `SHADOW_NOT_APPLIED` | CAP-01, CAP-04 | `terms-overlay` `eligible_face` 계산 |
| `tier_coverage` | **ADOPTED.** T1 `COMMIT_OBSERVED` 7건, T2 `UNBOUND` 3건, 그중 1건은 COMMITTED + 열린 환불(U2·`REFUND_OBLIGATION_OPEN` 음성 경로) | CAP-01, CAP-04 | `terms-overlay` 등급 선택·`underwrite` U1–U6 |
| `portfolio_scale_target` | **ADOPTED.** 계획된 canonical book = 동시 선지급 최대 15건, 스크립트 operation 예산 ≤ 300(`MAX_OPERATIONS 500`의 60 %, `capital/service.py`). cap 바인딩은 대량 건수가 아니라 대형 액면으로 유도 | CAP-01, CAP-08 | `demo-book-seed`·수용 사다리 `seeded-demo` |
| `golden_digest_policy` | **ADOPTED.** 기존 `tests/golden/demo.json`(debit = credit = 385,000, `SYNTHETIC_UNADOPTED`)과 `state_digest`·`content_digest` **바이트 불변**. 새 북은 별도 golden 파일·결정론적 seed·digest diff는 전용 PR | CAP-13, CAP-14, CAP-15 | `seed_demo.py` 계열 후속 노드·export manifest |
| `honesty_labels` | **ADOPTED.** 모든 데모 북 표면에 `SYNTHETIC_FIXTURE_PROFILE` + 프로필 버전 + `policy_adopted=false` + `funds_executed=false`. cap 숫자는 `CAPITAL-TERMS-V1` 인용, fixture 액면은 합성 단위로 라벨 | CAP-09, CAP-20 | 화면·export·readiness 표기 |

## 2. KIX 비전과의 연결

읽은 팩 경로와 적용이다(인용은 이 팩의 경로로 한정).

- **합성 범위와 라벨 어휘.** `docs/OPERATOR_HANDBOOK_KO.md`의 라벨 표(`SIMULATED`·`READ_ONLY_FIXTURE`·`DECISION_REQUIRED`·`NOT_BOUND`·`SYNTHETIC_UNADOPTED`)와 "화면에 나오는 숫자는 합성 fixture" 원칙이 `honesty_labels`의 정본이다. 데모 북은 그 표에 새 라벨을 **추가**할 뿐 기존 라벨을 재정의하지 않는다.
- **cap이 실제로 묶이는 규모.** `docs/CAPITAL_REQUIREMENTS_KO.md`의 CAP-08(초과 배정·공유 액면)·CAP-04(차입기초·집중도)·CAP-01(전 기간)은 현재 100,000 fixture에서 cap 분기를 검증하지 못한다 — `CAPITAL_FINANCIAL_TERMS.md` §6도 "집중도 한도와 fixture 규모"를 열린 위험으로 적었다. 이 프로필의 대형 액면이 그 공백의 합성 해법이다.
- **고정 FSM 경계.** `capital/scenarios.py`(2수취인 `PRIMARY_FEE_BPS`, 부담 미정 배정 정지)와 `capital/service.py`(`MAX_OPERATIONS 500`, 후보 평가 `?amount=` seam, `beneficiary_payee_map` 소비)가 프로필의 표현 한계다: 고정 FSM이 받는 수취인은 두 명뿐이므로 다수 수취인 커버리지는 그림자 메타데이터로 분리했다(`CAPITAL_SETTLEMENT_POLICY.md`의 `fsm_expressible` 어휘 그대로).
- **golden과 digest 정직성.** `docs/VALIDATION.md`(환불 fixture를 손으로 세팅하지 않고 pinned FSM 명령으로 만든 수리; golden `state_digest` 고정)와 `CAPITAL_ACCOUNTS_TAX_LEGAL.md`(V1 차트·385,000 합계 불변 조건)가 `golden_digest_policy`의 근거다.
- **upstream 인용 핀.** `/workspace/capital-run/kixproto-ro`(main `adcddc5`)는 읽기 전용 출처이며 이 문서는 어떤 upstream 노드도 완료로 표시하지 않는다.

## 3. 항목별 결정

공통 라벨: 모든 값은 `SYNTHETIC_FIXTURE_PROFILE`, `basis = PRODUCT_DECISION`, `provisional = true`다. 수익자·역할 라벨은 합성 role이며 법적 당사자가 아니다(F01·F04 규칙, `CAPITAL_FINANCIAL_TERMS.md` §6).

### 3.1 fixture_face_values (CAP-01, CAP-04)

- **값.** `CAPITAL-DEMO-BOOK-V1`, 합성 청구 10건. 각 청구는 `recognize_claim` + `PRIMARY_FEE_BPS`(fee_bps 500) 정책이므로 `organizer` 줄 = gross × 95 %, `platform` 줄 = gross × 5 %.

| claim_id (합성) | gross (KRW 정수) | organizer 줄 | 수익자 | 등급 조건 |
|---|---|---|---|---|
| `demo-alpha-arena` | 3,000,000,000 | 2,850,000,000 | `demo-org-alpha` | T1 (COMMITTED) |
| `demo-alpha-hall` | 1,200,000,000 | 1,140,000,000 | `demo-org-alpha` | T1 |
| `demo-beta-festival` | 4,000,000,000 | 3,800,000,000 | `demo-org-beta` | T1 |
| `demo-beta-club` | 800,000,000 | 760,000,000 | `demo-org-beta` | T2 (UNBOUND) |
| `demo-gamma-tour` | 8,000,000,000 | 7,600,000,000 | `demo-org-gamma` | T2 |
| `demo-gamma-annex` | 2,400,000,000 | 2,280,000,000 | `demo-org-gamma` | T1 |
| `demo-delta-small` | 50,000,000 | 47,500,000 | `demo-org-delta` | T1 |
| `demo-delta-mid` | 1,000,000,000 | 950,000,000 | `demo-org-delta` | T2 |
| `demo-epsilon-refund` | 400,000,000 | 380,000,000 | `demo-org-epsilon` | T1 + 열린 환불 액면 60,000,000 |
| `demo-epsilon-clean` | 2,000,000,000 | 1,900,000,000 | `demo-org-epsilon` | T1 |

총 gross 22,850,000,000, organizer 줄 합 21,707,500,000(`> portfolio_cap`, `CAPITAL-TERMS-V1` 인용). 바인딩 설계: (1) `demo-beta-festival`·`demo-gamma-*`에 `single_advance_cap` 초과 offer → U4 거절이 **한 건의 offer**로 발화. (2) `demo-org-beta`는 organizer 줄 합 4,560,000,000이므로 최대 인출 4건 뒤 다섯 번째에서 `beneficiary_aggregate_cap` 발화. (3) 북 전체를 다 인출하려면 `portfolio_cap`이 먼저 멈춘다. (4) `demo-delta-small`은 `two_person_threshold` **이하** 정상 여정을 가능하게 한다. 모든 값은 FSM `MONEY_MAX`(10^12) 아래.
- **근거.** 작은 fixture에서는 U4 집중도 검사가 절대 거절하지 못한다. 대형 액면이 있어야만 cap·등급·마진 경로가 결정 노트의 규칙대로 발화하는지 시연·검증할 수 있다.
- **대안.** cap 숫자를 fixture에 맞춰 낮춤: 조건 결정의 무결성을 깨므로 기각. cap 상대 표현만(정수 없음): seed가 실제 정수를 필요로 하므로 기각하되 cap 참조를 함께 둔다.

### 3.2 payee_structure (CAP-02, CAP-05)

- **값.** 온-FSM 구조는 기존 fixture와 동일한 2수취인(`organizer` 잔여, `platform` 수수료, `fee_bps 500`). `CAPITAL-ALLOC-V1` 클래스 ① `PROTECTED_THIRD_PARTY`·③ `ECOSYSTEM_ROYALTY` 커버리지를 위해 청구 메타데이터에 `SHADOW_PAYEE_LINES`(예: `demo-gamma-annex`에 `venue` 8 % of organizer residual)를 둔다. 그림자 줄은 고정 FSM 장부에 들어가지 않고 `SHADOW_NOT_APPLIED`로 라벨하며 `policy-simulator` 그림자 계산에만 쓰인다.
- **근거.** 고정 `SettlementMachine`은 `PRIMARY_FEE_BPS` 2수취인만 받는다(`CAPITAL_SETTLEMENT_POLICY.md` "복수 수취인은 upstream FSM 변경 필요"). 실제 배정과 그림자 배정을 섞지 않는 것이 `OBLIGATION_CONSERVATION` 불변식을 지킨다.
- **대안.** 3수취인을 FSM에 직접 주입: vendor 수정 없이 불가라 기각. 클래스 커버리지 포기: 노드 목적(클래스 순서 시연)에 반해 기각하되 그림자로 격리.

### 3.3 beneficiary_payee_map (CAP-01, CAP-04)

- **값.** 기존 `{"fixture-organizer": ["organizer"]}` 불변 + 확장: `{"demo-org-alpha": ["organizer"], "demo-org-beta": ["organizer"], "demo-org-gamma": ["organizer"], "demo-org-delta": ["organizer"], "demo-org-epsilon": ["organizer"], "demo-venue-east": ["venue"], "demo-agency-south": ["agency"]}`. `venue`·`agency` 키는 그림자 줄 전용(`SHADOW_NOT_APPLIED`)으로, pinned 청구에 해당 payee 줄이 없으면 `eligible_face` 기여는 0이다. 청구→수익자 바인딩은 seed가 `case_fixtures`에 기록하는 1:1 관계다.
- **근거.** `eligible_face` = "수익자에 매핑된 payee 줄의 outstanding 합 − 열린 환불 액면"(`CAPITAL-TERMS-V1` `additional_margin`). 다수 수익자가 있어야 `beneficiary_aggregate_cap`과 수익자별 마진이 의미를 가진다.
- **대안.** 한 수익자에 모든 청구: 수익자 cap과 포트폴리오 cap을 구분해 발화시킬 수 없어 기각.

### 3.4 tier_coverage (CAP-01, CAP-04)

- **값.** T1 `COMMIT_OBSERVED` 7건, T2 `UNBOUND` 3건(표 §3.1). `demo-epsilon-refund`는 COMMITTED이되 열린 환불 액면 60,000,000을 가진다 — U1 통과·U2 `REFUND_OBLIGATION_OPEN` 거절의 음성 경로와 `eligible_face` 감소(380,000,000 − 60,000,000)를 함께 시연한다. T2는 `CAPITAL-TERMS-V1`의 `real_funds_offering: NOT_IN_V1` 라벨을 계속 달고, 화면 기본 여정의 결합 우선 동작은 유지한다.
- **근거.** 등급별 금리·선지급률·충당 비율이 서로 다르므로 두 등급과 "COMMITTED지만 환불 열림" 중간 상태가 모두 있어야 오버레이 산술의 각 분기가 바인딩된다.
- **대안.** T1만: T2 스프레드·50 % 선지급률·500 bps 충당 경로 미검증이라 기각.

### 3.5 portfolio_scale_target (CAP-01, CAP-08)

- **값.** canonical 시연 북: seed 10건, 동시 진행 선지급 최대 15건, 스크립트 전체 operation 예산 `≤ 300`(`MAX_OPERATIONS 500`, `capital/service.py` 상한의 60 %). cap 발화는 액면 크기로 유도하므로 포트폴리오 cap 포화까지 필요한 대량 건수(40+ 인출)는 **스크립트에 포함하지 않고** "북 총액면 > portfolio_cap"으로 대신한다. 예상 operation ≈ 140(인출당 평균 ~6명령 × 15 + 거절 경로).
- **근거.** `SIMULATION_CAPACITY`는 용량 거절이지 금융 한도가 아니다(서비스 주석 그대로). 예산 60 %는 재시작·탐색 여유를 남긴다. `demo-org-beta`의 수익자 cap 발화(≈5건 × ~4명령)와 `single_advance_cap` 1건 거절은 이 예산 안에 든다.
- **대안.** 포트폴리오 cap까지 실제 인출로 채움: ~200 operation을 소비하고 브라우저 여정을 불안정하게 해 기각.

### 3.6 golden_digest_policy (CAP-13, CAP-14, CAP-15)

- **값.** (1) 기존 세 fixture(`fixture-v1`, gross 100,000 각)와 `tests/golden/demo.json`의 `state_digest`·`content_digest`·debit = credit = 385,000은 **바이트 불변**이다. (2) 데모 북은 별도 golden(`tests/golden/demo_book.json` 후보, 이름은 구현 노드가 확정)을 둔다. (3) seed는 결정론적이어야 한다: 고정 id·고정 `sim_day` 입력, digest에는 `instance_id`·시각을 넣지 않는다(CAP-15의 `content_digest` 규칙 그대로). (4) 재생성은 `--update-golden` 류 명령으로만 하고 diff는 digest 줄 변화로 한정, 전용 PR + 증거. (5) 프로필 버전을 올리면 새 golden 파일을 추가하고 이전 파일은 그대로 둔다.
- **근거.** `docs/VALIDATION.md`의 환불 fixture 수리는 "손으로 세팅한 view는 pinned FSM이 만들 수 없는 상태였다"는 교훈이다 — fixture는 pinned 명령의 산출물이어야 한다. `CAPITAL_ACCOUNTS_TAX_LEGAL.md`는 V1 차트·385,000 불변을 조건으로 못 박았다.
- **대안.** 기존 golden을 데모 북과 함께 갱신: 무관한 회귀를 숨길 수 있어 기각.

### 3.7 honesty_labels (CAP-09, CAP-20)

- **값.** (1) 모든 데모 북 조회·화면·export 행에 `SYNTHETIC_FIXTURE_PROFILE` 라벨과 `profile_version: CAPITAL-DEMO-BOOK-V1`, `policy_adopted: false`, `funds_executed: false`를 붙인다. (2) cap·금리·비율은 숫자로 복사하지 않고 `CAPITAL-TERMS-V1` 필드명으로 인용한다. (3) fixture 액면은 "합성 단위의 KRW 정수"로 표기하고 실제 익스포저·매출·채권으로 읽히지 않게 한다. (4) 수익자·payee 라벨은 합성 role이며 법적 당사자·계좌가 아니라는 표기를 유지한다. (5) 기존 라벨 표(`SIMULATED`·`READ_ONLY_FIXTURE`·`NOT_BOUND`·`DECISION_REQUIRED`·`NOT_AUTHORIZED`·`UNKNOWN`·`LOCAL_FILE_WORKSPACE`·`SYNTHETIC_UNADOPTED`·`DEV_ONLY`)의 의미를 바꾸지 않는다.
- **근거.** 대형 액면이 화면에 오르면 "실제 규모의 장부"로 오독할 위험이 커진다. 프로필 라벨 하나를 명시적으로 만들어 큰 숫자도 합성으로 읽히게 한다.
- **대안.** 기존 `SIMULATED` 하나로 통합: fixture-고정 조회와 결정된 프로필 seed의 차이가 지워져 기각.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "demo-book-profile-decision",
  "decided_by": "Devin swe-2 (RO by prompt), delegated by JunTae 2026-10-08 (model 10-14 10:07)",
  "date": "2026-10-14",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "scope": "KIX-CAPITAL simulation and product design only; every value is a SYNTHETIC_FIXTURE_PROFILE, not product terms and not upstream policy; not an offer; no real money; production NOT_AUTHORIZED",
  "delegation": "2026-10-08 18:25 KST JunTae Park delegated financial terms, settlement policy, upstream binding and accounts/tax/legal to Fable; this node is decided by Devin swe-2 under the same delegation (model 10-14 10:07)",
  "bases": {
    "capital_main": "8787278",
    "kix_protocol_main": "adcddc5",
    "vendor_pin_commit": "7481b0e16ce9b903abbffa62249bb91cd9e63cfe"
  },
  "profile_version": "CAPITAL-DEMO-BOOK-V1",
  "cap_reference_rule": "Caps are cited by CAPITAL-TERMS-V1 field name (underwriting_depth.single_advance_cap_krw, beneficiary_aggregate_cap_krw, portfolio_cap_krw, two_person_threshold_krw); this note copies no cap literal",
  "existing_fixtures_and_goldens": "BYTE_IDENTICAL: the three fixture-v1 settlement views (gross 100,000 each) and tests/golden/demo.json digests do not change; the demo book is an additive candidate profile only",
  "upstream_adoption_claimed": false,
  "entries": {
    "fixture_face_values": {
      "status": "ADOPTED",
      "value": {
        "label": "SYNTHETIC_FIXTURE_PROFILE",
        "profile_version": "CAPITAL-DEMO-BOOK-V1",
        "policy": {"kind": "PRIMARY_FEE_BPS", "fee_bps": 500, "residual_payee": "organizer", "fee_payee": "platform"},
        "claims": [
          {"claim_id": "demo-alpha-arena", "gross_krw": 3000000000, "beneficiary": "demo-org-alpha", "tier": "T1_COMMIT_OBSERVED"},
          {"claim_id": "demo-alpha-hall", "gross_krw": 1200000000, "beneficiary": "demo-org-alpha", "tier": "T1_COMMIT_OBSERVED"},
          {"claim_id": "demo-beta-festival", "gross_krw": 4000000000, "beneficiary": "demo-org-beta", "tier": "T1_COMMIT_OBSERVED"},
          {"claim_id": "demo-beta-club", "gross_krw": 800000000, "beneficiary": "demo-org-beta", "tier": "T2_UNBOUND"},
          {"claim_id": "demo-gamma-tour", "gross_krw": 8000000000, "beneficiary": "demo-org-gamma", "tier": "T2_UNBOUND"},
          {"claim_id": "demo-gamma-annex", "gross_krw": 2400000000, "beneficiary": "demo-org-gamma", "tier": "T1_COMMIT_OBSERVED"},
          {"claim_id": "demo-delta-small", "gross_krw": 50000000, "beneficiary": "demo-org-delta", "tier": "T1_COMMIT_OBSERVED"},
          {"claim_id": "demo-delta-mid", "gross_krw": 1000000000, "beneficiary": "demo-org-delta", "tier": "T2_UNBOUND"},
          {"claim_id": "demo-epsilon-refund", "gross_krw": 400000000, "beneficiary": "demo-org-epsilon", "tier": "T1_COMMIT_OBSERVED", "open_refund_face_krw": 60000000},
          {"claim_id": "demo-epsilon-clean", "gross_krw": 2000000000, "beneficiary": "demo-org-epsilon", "tier": "T1_COMMIT_OBSERVED"}
        ],
        "total_gross_krw": 22850000000,
        "organizer_line_total_krw": 21707500000,
        "binding_design": {
          "single_advance_cap": "fires on one offer above CAPITAL-TERMS-V1 underwriting_depth.single_advance_cap_krw on demo-beta-festival or demo-gamma-* (organizer line large enough that U3 alone would pass)",
          "beneficiary_aggregate_cap": "demo-org-beta organizer lines sum 4,560,000,000 so beneficiary_aggregate_cap_krw binds on roughly the fifth max-size advance",
          "portfolio_cap": "book total face exceeds portfolio_cap_krw so the cap halts the book before exhaustion; saturation is not scripted",
          "two_person_threshold": "any draw above two_person_threshold_krw shows the two-person path; demo-delta-small allows a sub-threshold journey"
        },
        "fsm_bounds": "all faces < pinned MONEY_MAX 10^12; existing three fixtures byte-identical"
      },
      "provided_by": "Devin swe-2 (RO by prompt), delegated by JunTae 2026-10-08 (model 10-14 10:07)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Small fixtures can never trigger U4 concentration checks; faces sized as multiples of the decided caps make caps, tiers and margin paths actually bind while staying inside the pinned FSM money bound.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "review_items": ["fixture faces are synthetic units, not modeled real sales", "cap literals remain owned by CAPITAL-TERMS-V1"],
      "fsm_binding": "faces enter only via recognize_claim/policy on new fixture rows; no pinned byte changes"
    },
    "payee_structure": {
      "status": "ADOPTED",
      "value": {
        "label": "SYNTHETIC_FIXTURE_PROFILE",
        "on_fsm": {"kind": "PRIMARY_FEE_BPS", "payees": ["organizer", "platform"], "fee_bps": 500},
        "shadow_payee_lines": {
          "status": "SHADOW_NOT_APPLIED",
          "purpose": "CAPITAL-ALLOC-V1 class coverage (PROTECTED_THIRD_PARTY, ECOSYSTEM_ROYALTY) for policy-simulator shadow books only",
          "example": {"claim_id": "demo-gamma-annex", "lines": [{"payee": "demo-venue-east", "class": "PROTECTED_THIRD_PARTY", "share_of_organizer_residual_bps": 800}]}
        }
      },
      "provided_by": "Devin swe-2 (RO by prompt), delegated by JunTae 2026-10-08 (model 10-14 10:07)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-02", "CAP-05"],
      "rationale": "The pinned SettlementMachine accepts only the two-payee PRIMARY_FEE_BPS policy; class coverage beyond it must stay shadow until an upstream multi-payee FSM exists.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "fsm_binding": "shadow lines never enter the pinned ledger; OBLIGATION_CONSERVATION unaffected"
    },
    "beneficiary_payee_map": {
      "status": "ADOPTED",
      "value": {
        "label": "SYNTHETIC_FIXTURE_PROFILE",
        "extends": {"fixture-organizer": ["organizer"]},
        "map": {
          "demo-org-alpha": ["organizer"],
          "demo-org-beta": ["organizer"],
          "demo-org-gamma": ["organizer"],
          "demo-org-delta": ["organizer"],
          "demo-org-epsilon": ["organizer"],
          "demo-venue-east": ["venue"],
          "demo-agency-south": ["agency"]
        },
        "shadow_only_payee_labels": ["venue", "agency"],
        "eligible_face_rule": "sum of outstanding on lines whose payee is in map[beneficiary_role] minus open refund face, per CAPITAL-TERMS-V1 additional_margin; labels with no pinned line contribute 0"
      },
      "provided_by": "Devin swe-2 (RO by prompt), delegated by JunTae 2026-10-08 (model 10-14 10:07)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Multiple beneficiaries let beneficiary aggregate and per-beneficiary margin bind independently of the portfolio cap; shadow payee labels pre-position multi-payee mapping without touching the pinned FSM.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "tier_coverage": {
      "status": "ADOPTED",
      "value": {
        "label": "SYNTHETIC_FIXTURE_PROFILE",
        "T1_COMMIT_OBSERVED": ["demo-alpha-arena", "demo-alpha-hall", "demo-beta-festival", "demo-gamma-annex", "demo-delta-small", "demo-epsilon-refund", "demo-epsilon-clean"],
        "T2_UNBOUND": ["demo-beta-club", "demo-gamma-tour", "demo-delta-mid"],
        "negative_paths": {
          "refund_open": "demo-epsilon-refund is COMMITTED with open refund face 60,000,000: U1 passes, U2 / REFUND_OBLIGATION_OPEN rejects draws, eligible_face reduced",
          "t2_real_funds_note": "T2 stays labelled NOT_IN_V1 for real funds per CAPITAL-TERMS-V1"
        }
      },
      "provided_by": "Devin swe-2 (RO by prompt), delegated by JunTae 2026-10-08 (model 10-14 10:07)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Tier-dependent rate, advance-rate and provision branches each need a live fixture; a committed-but-refund-open claim exercises the negative gate and borrowing-base haircut together.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "fsm_binding": "tier derives from the draw receipt settlement_gate; no flag is forced"
    },
    "portfolio_scale_target": {
      "status": "ADOPTED",
      "value": {
        "label": "SYNTHETIC_FIXTURE_PROFILE",
        "seeded_claims": 10,
        "max_concurrent_advances": 15,
        "operation_budget": 300,
        "operation_budget_basis": "60 percent of MAX_OPERATIONS 500 in capital/service.py; SIMULATION_CAPACITY is a demo capacity bound, not a financial limit",
        "expected_operations": 140,
        "cap_saturation_scripted": false
      },
      "provided_by": "Devin swe-2 (RO by prompt), delegated by JunTae 2026-10-08 (model 10-14 10:07)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-01", "CAP-08"],
      "rationale": "Cap binding is induced by face size rather than operation count, so the scripted book fits a bounded demo while every cap branch is still exercisable.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "golden_digest_policy": {
      "status": "ADOPTED",
      "value": {
        "label": "SYNTHETIC_FIXTURE_PROFILE",
        "existing_goldens": "BYTE_IDENTICAL: tests/golden/demo.json state_digest, content_digest and debit = credit = 385,000 unchanged; three fixture-v1 views unchanged",
        "new_golden": "separate candidate file (working name tests/golden/demo_book.json; final name set by the implementing node)",
        "determinism": "fixed claim ids, fixed sim_day inputs; digests exclude instance_id and wall-clock per the CAP-15 content_digest rule",
        "regeneration": "dedicated generator flag (e.g. --update-golden equivalent) only; digest-line diffs only; separate PR with evidence",
        "version_bumps": "new profile version adds a new golden file; old goldens are never edited in place"
      },
      "provided_by": "Devin swe-2 (RO by prompt), delegated by JunTae 2026-10-08 (model 10-14 10:07)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-13", "CAP-14", "CAP-15"],
      "rationale": "Fixtures must be products of pinned commands (the VALIDATION refund-fixture repair lesson) and V1 digests are pinned by the accounts/tax/legal decision; a separate golden keeps unrelated regressions visible.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "honesty_labels": {
      "status": "ADOPTED",
      "value": {
        "profile_label": "SYNTHETIC_FIXTURE_PROFILE",
        "required_fields": {"profile_version": "CAPITAL-DEMO-BOOK-V1", "policy_adopted": false, "funds_executed": false},
        "cap_citation_rule": "cite CAPITAL-TERMS-V1 field names; never restate cap literals as fixture facts",
        "amount_label": "KRW integer synthetic units; not real exposure, sales or claims",
        "role_label": "beneficiary and payee labels are synthetic roles, not legal parties or accounts",
        "existing_labels": "handbook label table unchanged; this profile adds one label, redefines none"
      },
      "provided_by": "Devin swe-2 (RO by prompt), delegated by JunTae 2026-10-08 (model 10-14 10:07)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-09", "CAP-20"],
      "rationale": "Large faces raise the risk of reading the demo book as a real-scale ledger; one explicit profile label keeps every large number marked synthetic.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| 수용 기준 | 충족 위치 |
|---|---|
| `docs/decisions/CAPITAL_DEMO_BOOK.md`에 정확히 하나의 `capital-decision-v1` 블록, 모든 decision_item 커버, `decision_ledger.py` 통과 | §4 블록 하나뿐, 일곱 항목 모두 ADOPTED·`provided_by`·ISO `date`·`value` 보유. UNDETERMINED 없음이라 무효 조합 없음 |
| ADOPTED 값은 합성 fixture 프로필 라벨, cap은 `CAPITAL_FINANCIAL_TERMS.md` 인용 | 각 entry의 `label: SYNTHETIC_FIXTURE_PROFILE`, 블록 `cap_reference_rule`, §3 본문의 필드명 인용. cap 숫자를 이 문서에서 값으로 복사하지 않음 |
| 세 fixture와 현재 golden digest의 바이트 동일 여부 명시 | 머리말 표, §3.6, 블록 `existing_fixtures_and_goldens`·`existing_goldens` — 모두 **BYTE_IDENTICAL** 명시 |
| diff는 이 파일 하나, `capital/`·`tests/`·vendor 불변 | 이 문서는 `docs/decisions/CAPITAL_DEMO_BOOK.md` 하나다. 실제 diff 확인은 PR·독립 리뷰어가 한다 |

## 6. Open risks

- **프로필→코드 간격.** 이 노트는 값만 정한다. seed 구현 노드(`demo-book-seed` 후보)가 pinned 명령으로 fixture를 만들어야 하며, 그 전까지 프로필은 문서다.
- **cap 개정 민감도.** 액면은 현재 `CAPITAL-TERMS-V1` cap의 배수로 설계됐다. cap이 바뀌면 바인딩 설계(§3.1 표)를 재확인해야 한다 — 그래서 숫자가 아니라 필드명으로 인용했다.
- **그림자 수취인의 오독.** `venue`·`agency` 줄은 pinned 장부에 없다. 그림자 계산 결과가 실제 배정으로 보이지 않도록 `SHADOW_NOT_APPLIED` 표기를 강제한다.
- **T2 노출.** T2는 `real_funds_offering: NOT_IN_V1`이다. 데모에서 T2 인출이 커 보이는 것은 합성 설계일 뿐 제공 승인이 아니다.
- **수익자 1:1 가정.** 한 청구에 두 수익자를 매핑하는 경우는 V1에 없다. 다수 수익자·다수 payee 조합은 `fin-multi-payee-refund-proof` 류 upstream 변경 뒤 다시 연다.

## 7. 후속 작업

- `demo-book-seed`(신규 노드): 이 프로필을 pinned `SettlementMachine`/`MockCredit` 명령으로 seed하고 `GET /api/underwrite` 후보 경로로 cap 발화를 시연. `tests/golden/demo_book.json` 생성·라벨 배선.
- `terms-overlay`·`policy-simulator`: `beneficiary_payee_map` 확장분과 `SHADOW_PAYEE_LINES` 소비. fixture 라벨 표기(`SYNTHETIC_FIXTURE_PROFILE`).
- upstream 후보 입력: `fin-multi-payee-refund-proof`·`cr-02`·`fin-credit-exposure-reconciliation`에 이 북의 cap 발화 벡터를 전달. upstream 노드 완료 표시 없음.
