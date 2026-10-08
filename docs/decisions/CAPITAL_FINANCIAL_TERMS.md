# Capital F04 금융 조건 결정 — 이자·수수료·기간·손실·담보·준비금

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
이 문서는 KIX-CAPITAL 저장소 안의 **시뮬레이션·제품 설계용** 결정이다. 청약이나 대출 제안이 아니고, 실자금이 움직이지 않으며, production은 계속 `NOT_AUTHORIZED`다. 법률·세무·회계·인허가 관련 내용은 **전문가 검토 전의 작업 가정(WORKING ASSUMPTION)** 이며 법률·세무·회계 자문이 아니다. 이 문서는 어떤 upstream 계약(kix-protocol `f04-mock-deepening` 등)의 채택도 주장하지 않는다. 그 채택은 upstream의 실제 PR·병합 영수증만이 증명한다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `financial-terms-decision` (Decision: F04 financial terms) · deps `pr1-merge-ready` · kind `decision` |
| 결정자 | **Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08** |
| 위임 원문 | 2026-10-08 18:25 KST JunTae Park: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." |
| 결정일 | 2026-10-08 |
| KIX-CAPITAL 기준 | main `6487a99` (packaging-release #6). `docs/decisions/`는 이 문서 이전에 비어 있었다. 따라서 이 저장소 안에서 따라야 할 선행 결정 문서는 없고, 정합성은 아래 upstream 결정과 유지한다 |
| kix-protocol 기준 | main `d71b411` (읽기 전용 체크아웃 `/workspace/capital-run/kixproto-ro`) |
| vendor pin | `capital/vendor/manifest.json` commit `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`, 다섯 파일 SHA256 불변. 이 결정은 `capital/`·`tests/`·vendor 바이트를 바꾸지 않는다 |
| 적용 소유 노드 | **`terms-overlay`**. 이 문서는 값과 적용 규칙만 정한다. readiness 배선, 오버레이 원장, 화면 반영은 그 노드가 한다 |
| 이전 결정 요청과의 관계 | 이전 요청문의 "에이전트는 숫자 기본값을 만들지 않는다 · 결정자 JunTae" 규칙은 2026-10-08 위임으로 **대체**됐다. 아래 값은 기본값이 아니라 위임받은 결정자의 잠정 결정이며, 각 항목에 결정자·일자·근거·기초(basis)를 붙인다 |

용어: 금액은 KRW 정수(최소단위 1원), 비율은 bps(1/10000), 연율은 `bps_annual`, 날짜는 오버레이의 논리 일(`sim_day`, 정수)이다. 고정 FSM은 `capital/vendor/credit_advance_f04/credit_fsm.py`의 `CreditMachine`, 예약 술어는 `mock_credit.py`의 `MockCredit`다.

## 1. 결정 요약

| item | 결정 (요지) | CAP rows | 소비 노드 / seam |
|---|---|---|---|
| `interest_rate` | 단리·ACT/365·원금 잔액 기준. 기준 300 bps + 등급 스프레드: **T1 COMMIT_OBSERVED 700 bps/yr**, **T2 UNBOUND 1,300 bps/yr**. 만기 후 +300 bps. 총비용 상한 2,000 bps/yr | CAP-01 | `terms-overlay` 이자 메모 원장 → upstream `cr-06-repayment-allocation` |
| `fees` | **ZERO_FEE_INTEREST_ONLY**: 취급·관리·약정·연장·중도상환 수수료 모두 0 bps. PG·정산 수수료는 Capital 수수료가 아님 | CAP-01 | `terms-overlay` |
| `term` | 표준 60일, 최소 7일, 최대 180일(연장 포함), 정산 예정일 연동 규칙, 만기 후 유예 10일, 연장 1회·30일, 중도상환 무벌칙 | CAP-01 | `terms-overlay` 논리 시계 → upstream `cr-03-facility-reservations` |
| `default_loss_treatment` | 운영자 명령으로만 `default`(AI는 제안만). 회수 폭포: 결합 청구 배분 상계 → 같은 수익자 다른 청구 상계 → 손실준비금 → 플랫폼 상각. 부도 후 90일 상각. V1 손실 부담 플랫폼 100 % | CAP-01, CAP-04 | `terms-overlay` 회수 원장 → upstream `cr-07-delinquency-recovery` |
| `underwriting_depth` | **EVIDENCE_RULES_V1**: 개인신용정보 없음. 정산 증거 등급·환불 노출·차입기초·집중도 한도·결정 권한(2인 원칙 5천만 원 초과)·KYC 상태 기록의 6단계 규칙 | CAP-01 | `terms-overlay` 사전점검 → upstream `cr-04-underwriting-consent`, `ai-delegation-contract-mock` |
| `external_collateral_completeness` | 완전성 사다리 C0~C4. 시뮬레이션은 C1(플랫폼 상계 약정, 합성), 실자금 최소 C2(확정일자 있는 채권양도 통지·승낙). 체인 기록은 증거이지 담보 완성이 아님 | CAP-04 | `terms-overlay` → upstream `cr-02-claim-eligibility`, `f04-real-funds-lift-criteria` |
| `additional_margin` | 선지급률 **T1 85 %, T2 50 %** (차입기초 = 수익자 귀속 의무 잔액). 매 명령·매일 재평가, 마진콜 치유 5일, 미치유 시 만기 가속 | CAP-04 | `terms-overlay` 차입기초 검사 |
| `collateral_execution` | 1차 정산 배분 상계, 2차 양수 채권 추심(C2 이상), 3차 법적 회수. 관람권·티켓·토큰에는 절대 손대지 않음. 집행은 사람 2인, AI는 제안만 | CAP-04 | `terms-overlay` 상환 제안 → upstream `cr-05`, `cr-07` |
| `reserve` | 등급 가중 기대손실 충당: T1 150 bps, T2 500 bps, 연체 2,500 bps, DEFAULTED 10,000 bps. 재원은 프로토콜 수익 풀만. 고객 예치금·주최자 정산금·환불준비금·토큰 재무는 금지 | CAP-04 | `terms-overlay` 메모 계정(SIMULATION_FIXED_V2 후보) → `fin-ledger-contract` 후보 |

## 2. KIX 비전과의 연결

읽은 kix-protocol 문서와, 각 선택이 그 비전에 봉사하는 방식이다.

- **체인 권위 / 오프체인 위임 실행(모델 1).** `docs/decisions/AUTHORITY_MODEL_1.md`와 `README.md` §1·§3은 "예약 확정 ≠ 결제 확인 ≠ 체인 권리 발행 완료"이고 체인이 은행 자금·계약상 채무를 보증하지 않는다고 못 박는다. 그래서 담보 완전성(§4.6)을 **체인 기록 = 증거, 법적 완성 = 별도 사다리**로 나눴고, 집행(§4.8)은 관람권·토큰에 손대지 않는 KRW 채권 경로만 둔다.
- **금융권리와 관람권의 분리.** `docs/contracts/CREDIT_ADVANCE_F04.md` §0("금융 메모는 관람·검표 권한이 아니다"), `docs/PROTOCOL_MASTERPLAN_V2.md` §7(역사 자료: 네 금융 계약군, 초과 배정·담보 차단), `docs/DEVELOPMENT_PLAN.md` §14("금융은 권리·정산채권·채무·부담을 구별"). 모든 항목의 `never` 목록과 FSM 플래그 불변(`admission_granted`, `collateral_perfected` 등 항상 false)을 그대로 지킨다.
- **정수 산술·bps·largest-remainder.** `docs/COMMERCE_CONTRACTS.md`(float 금지, 1/10000 bps, 최소단위 정수)와 `docs/contracts/SETTLEMENT_DISTRIBUTION_F01_F03.md` §0.3(정수 잔여 단위 원칙). 이자 계산을 정확한 유리수 누적 + 게시 시점 1원 내림으로 정했고, 모든 값은 정수와 bps다. 이는 `RUNTIME_ARCHITECTURE_S062.md`(역사 자료) §4의 u128 atoms 방향과도 맞는다.
- **mock/sim only와 잠금.** `docs/tasks/TASK_005_MEGA_COMMERCE_PROGRAM.md` 결정 6, `docs/decisions/PROGRAM_DECISIONS_20260928.md` §2.1·§5, `docs/decisions/PROGRAM_ROADMAP_20260930.md` §5. 이 결정은 실자금·실여신·KYC·PG·은행을 열지 않는다. 실자금 해제 기준은 사용자 노드 `f04-real-funds-lift-criteria`가 따로 쓴다. 이 문서는 그 질문지에 넣을 작업 가정을 공급할 뿐이다.
- **정책 심화 R-9와 "포부".** `PROGRAM_ROADMAP_20260930.md` §2 R-9는 F04 계약 §5의 빈 항목을 결정하는 작업을 승인했고, 로드맵 §0은 "한 번 시작하면 사람의 결정이 꼭 필요한 곳 말고는 멈추지 않는다"는 지시를 기록한다. JunTae의 2026-10-08 위임은 Capital 안에서 그 결정을 Fable에게 맡긴 것이다. 그래서 UNDETERMINED를 쓰지 않고 아홉 항목 모두 값을 정했다. 다만 upstream `f04-mock-deepening`(user_merge, `docs/aiops/PROGRAM_ASTRA_DELEGATION.md`)은 여전히 열려 있고, 이 문서는 그 입력 후보다.
- **규모와 위임 실행(RS, 5·6·7단계).** `docs/decisions/TOKEN_LAYER_AND_RIGHTS_SCALE_SCOPE_20260929.md`, `docs/decisions/RIGHTS_SCALE_RS0_DECISION_20261008.md`, `docs/blueprints/rights-scale-v1/README.md`(1,024 → 16,384 → 65,536 슬롯, 페이지 단위 위임), `DEVELOPMENT_PLAN.md` §5(5단계 영속 거래, 6단계 합성 경제, 7단계 인증 export). 한도를 건당 5억·수익자 20억·포트폴리오 200억 원으로 두고, 등급·한도·준비금을 **정책 버전(`CAPITAL-TERMS-V1`)** 으로 묶어 backend 채택 뒤 `cr-03-facility-reservations`의 원자 예약으로 옮길 수 있게 했다.
- **토큰 계층(TL)과 담보.** `docs/blueprints/optional-native-token-v1/README.md` §3.1(여섯 자산 분리), TK-4(재원 분리), TK-12(토큰 단독 담보 금지), §7.1(자금 풀), `docs/adr/0002-token-layer-scope-and-limits.md`. 준비금 재원을 프로토콜 수익 풀로 한정하고 고객 예치금·정산금·환불준비금·토큰 재무를 금지했다. 토큰 담보는 V1에서 받지 않고, 미래에도 KRW·스테이블 담보 위의 추가 담보로만 둔다.
- **AI 위임 경계.** `DEVELOPMENT_PLAN.md` §14(AI는 조회/제안/실행 권한과 scope·금액·기간·회수 조건을 구별, 모델 출력만으로 지급하지 않음), `RUNTIME_ARCHITECTURE_S062.md` §10(`executionAuthorized=false`), 로드맵 노드 `ai-delegation-contract-mock`. 승인·부도·집행은 사람 명령이고, AI는 제안 레코드만 만든다. 2인 원칙 임계값을 둬 미래 `AgentGrant`/`ActionPermit`의 금액 scope에 바로 대응한다.
- **금융 조회의 의미 분리.** `docs/aiops/FINANCE_COMPLETION_DESIGN_KO.md` §6은 `confirmed_cash`·`recovery_due`를 대여 재원에 더하지 말고 한도 재산정·우선순위·이자/상환표·손실·담보 효력을 `f04-mock-deepening` 결정으로 둔다고 적는다. 차입기초를 "수익자 귀속 의무 잔액"으로만 정의하고 확인 현금·회수채권을 더하지 않았다. `docs/aiops/PROGRAM_EXPANSION_20261002_KO.md`의 `cr-01`~`cr-07` 여신 수명 노드가 이 값들의 upstream 소비처다.
- **역사 청사진의 안전 요구.** `docs/BLUEPRINT_20260914.md` §3(제작자금과 티켓 결제금은 별도 자금 흐름), §10(금융 근거의 기준시점·범위), `docs/ROADMAP.md` 우선순위 7. 둘 다 현행 승인이 아니지만 그 안전 요구는 폐기되지 않았다. 재원 분리와 기준시점(`cut`) 표기 요구를 그대로 따른다.

## 3. 항목별 결정

각 항목은 값, 근거, 검토한 대안, 게이트 대상, 고정 FSM과의 결합 순서로 적는다. 고정 FSM의 제약은 공통이다: `offer`에 `product`를 넘기면 `CREDIT_PRODUCT_UNDEFINED`(§7.3), `interest_defined`·`underwriting_executed`·`kyc_executed`·`collateral_perfected` 등은 항상 false로 강제(`_force_false`), `draw`는 제안 금액 전액 한 번(부분 인출 없음), `repay`는 1원 이상·잔액 이하·순번 연속, `close`는 잔액 0일 때만, `default`는 잔액이 있을 때만, `DEFAULTED` 뒤 변경 명령은 `TERMINAL_IMMUTABLE`, 저널에는 시간이 없다. 따라서 **모든 조건은 오버레이 원장에 산다.** FSM은 원금 노출만 안다.

### 3.1 interest_rate (CAP-01)

- **값.** 단리, ACT/365 고정, 원금 잔액(`outstanding_exposure`) 기준, 인출일 포함·상환일 제외, 최소 1일. 기준금리 300 bps/yr + 등급 스프레드. T1 `COMMIT_OBSERVED`(인출 시 `settlement_gate == MOCK_COMMIT_OBSERVED`) 스프레드 400 → **700 bps/yr**. T2 `UNBOUND`(F04가 허용하는 무결합 인출) 스프레드 1,000 → **1,300 bps/yr**. 만기 다음 날부터 +300 bps/yr(연체이자). 총비용 상한 2,000 bps/yr(수수료·연체이자 포함 연환산). 계산은 `floor( Σ(outstanding_i × days_i) × rate_bps / (10000 × 365) )`, 유리수로 누적하고 게시(상환·종결) 시점에만 1원 내림, 나머지는 이월.
- **근거.** T1은 정산 목이 `COMMITTED`(명세서 관측, 즉 현금이 플랫폼 단에 들어온 뒤) 상태에서만 열리므로 위험은 환불·차지백 역전에 한정된다. 증거가 좋은 선지급을 싸게 만드는 것이 티켓 권리 경제의 포부이므로 시장 선정산 상품보다 낮게 잡았다. T2는 현금 미도착·무결합이라 높은 스프레드와 낮은 선지급률을 함께 둔다. 2,000 bps 상한은 한국 대부업법·이자제한법 최고금리(연 20 %, 수수료 포함)를 작업 가정으로 둔 것이다.
- **대안.** (a) 단일 고정 금리: 증거 등급의 가치를 못 살려 기각. (b) 일할 정액 수수료(선정산식): 상한 연환산이 위험하고 FSM 원금 메모와 어긋나 기각. (c) 지수 연동(CD·KOFR): 가격원 계약이 없어 기각하되 `base_rate_bps_annual`을 분리해 두어 나중에 지수로 재결합 가능.
- **FSM 결합.** 등급은 `draw` 수락 영수증의 `credit.settlement_gate`로 한 번 정해 수명 동안 고정. 이자는 FSM 밖 오버레이 메모 계정에만 기록. `repay`에는 원금 몫만 넘긴다(§3.3).

### 3.2 fees (CAP-01)

- **값.** `ZERO_FEE_INTEREST_ONLY`. 취급 수수료 0 bps, 관리 수수료 0 bps/yr, 미인출 약정 수수료 0 bps/yr, 연장 수수료 0, 중도상환 수수료 0, 연체 수수료 없음(연체이자만). PG 수수료·정산 수수료(F01 fixture의 `fee_bps 500`)는 Capital 수수료가 아니며 재청구하지 않는다. 버전 `CAPITAL-FEES-V1`.
- **근거.** (1) 대부업법은 사례금·할인금·수수료를 모두 이자로 본다는 작업 가정 아래, 7~60일짜리 선지급에 건별 수수료를 얹으면 연환산 총비용이 쉽게 상한을 넘는다. (2) KIX의 플랫폼 수익은 정산·리셀 수수료이며 같은 주최자에게 여신 수수료를 겹쳐 받지 않는 것이 생태계 유인에 맞다. (3) 단일 금리는 오버레이 구현과 화면 설명이 단순하다.
- **대안.** 취급 수수료 50~100 bps: 상한 역산 로직이 필요해 기각. 연 서비스 요금: 사업자 금융 UX에 불리해 기각.
- **FSM 결합.** 영향 없음. 상한 검사(`cap_check`)만 오버레이가 모든 수수료 0을 전제로 연환산을 계산한다.

### 3.3 term (CAP-01)

- **값.** 표준 60일, 최소 7일, 최대 180일(연장 포함 총 상한). 정산 예정일을 아는 경우 `term_days = clamp(expected_settlement_cash_day − draw_day + 14, 7, 180)`, 모르면 60일. 만기 = `draw_day + term_days`. 만기 일시상환이되 언제든 부분 상환 가능, 중도상환 무벌칙. 연장 1회·최대 30일·사람 승인. 만기 후 유예 10일, 부도 적격일 = 만기 + 11일. 시뮬레이션 시계는 오버레이 논리 일(`sim_day`, 0부터, 명시적 오버레이 명령으로만 전진, F04 저널에는 안 들어감).
- **근거.** 선지급은 포착된 정산채권에 대한 것이며 공연 뒤 정산 지연까지 걸리므로 60일이 표준, 조기 판매분은 최대 180일까지 필요하다. 제작자금 대여(`cr-01` 범위 1의 별도 상품)는 이 조건의 대상이 아니다.
- **대안.** 무기한 회전 한도: `cr-03` 전에는 공유 한도 보존이 없어 기각. 고정 30일: 공연 주기와 맞지 않아 기각.
- **FSM 결합.** 상환 배분 순서는 연체이자 → 이자 → 원금. 현금 수령액 R에서 이자 몫을 뺀 원금 몫 P > 0일 때만 FSM `repay(amount=P, sequence=next)`를 보낸다(P = 0이면 FSM 호출 없음, `INVALID_AMOUNT` 회피). `close`는 FSM 잔액 0 **그리고** 오버레이 이자 미수 0일 때만 보낸다.

### 3.4 default_loss_treatment (CAP-01, CAP-04)

- **값.** 부도 적격: `outstanding_exposure > 0`이고 `sim_day ≥ 부도 적격일`. FSM `default`는 사람 운영자 명령이며 자동 전이 없음, AI는 `DEFAULT_ELIGIBLE` 제안만. 가속 사유: 마진콜 미치유, 수익자 도산 통지, 증거 위조 판정. 회수 폭포: ① 결합 청구에서 수익자에게 배분되는 현금 상계 → ② 같은 수익자의 다른 청구 상계 → ③ 손실준비금 → ④ 플랫폼 상각. 부도 후 90일에 상각. 상각은 오버레이 회계 메모이며 FSM 노트는 계약대로 `NOTED`로 남아 천장을 계속 잡는다. V1 손실 부담 KIX Capital 플랫폼 100 %, 트랜치 없음. 부도 뒤 치유 없음(FSM 종결). 늦은 회수는 오버레이 회수 원장에만 적고 케이스를 되살리지 않는다.
- **근거.** F04 계약 §7은 `default`를 "연체 판정·상각·처분·유질·우선순위가 아니다"라고 적는다. 그래서 금융적 의미(연체·상각·손실 귀속)를 전부 오버레이로 옮기고 FSM 전이는 그대로 둔다. 손실 100 % 플랫폼 부담은 투자자 트랜치가 생기면(CAP-03 채권 매입) 다시 연다.
- **대안.** 자동 부도 전이: AI·자동 실행 경계 위반이라 기각. 부도 후 FSM `repay` 재개: 고정 FSM이 `TERMINAL_IMMUTABLE`이라 불가.
- **기초.** WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW — 상각 시점·손실 인식(K-IFRS 기대신용손실 등)·도산 시 상계 효력은 회계·법무 검토 대상.

### 3.5 underwriting_depth (CAP-01)

- **값.** `EVIDENCE_RULES_V1`, 개인신용정보·신용점수 없음. 순서: U1 정산 증거 등급(T1은 결합 정산 조회 `COMMITTED`, FSM §7.5 게이트) → U2 환불 노출(`refund_face == 0` 또는 전액 재분류, FSM `REFUND_OBLIGATION_OPEN`이 강제) → U3 차입기초(`amount ≤ floor(eligible_face × advance_rate_bps / 10000)` 오버레이 **그리고** `amount ≤ open_face − reserved_open` FSM) → U4 집중도(건당 500,000,000원, 수익자 합계 2,000,000,000원, 포트폴리오 20,000,000,000원) → U5 결정 권한(사람 운영자 `approve`, 50,000,000원 초과는 2인 원칙, AI는 제안만) → U6 KYC/AML 상태(시뮬레이션은 `kyc_executed=false` 기록, 실자금은 수익자 법인 KYC/AML 필수, 소유 `f04-real-funds-lift-criteria`). 결정 레코드 필드: `rules_version, inputs_digest, tier, borrowing_base, caps_remaining, decided_by_role, sim_day`.
- **근거.** CAP-19·`DEVELOPMENT_PLAN.md` §14의 최소 공개·AI 경계와 Capital README의 "실명·계좌·신용정보 입력란 없음"을 유지하면서 심사를 규칙으로 재현 가능하게 한다. 한도 숫자는 RS 규모(65,536석 공연)와 플랫폼 장부 성장을 전제로 한 포부 값이며 현재 fixture(총액 100,000원)에서는 묶이지 않는다.
- **대안.** 외부 신용평가 연동: NOT_BOUND·개인정보 쟁점이라 기각. 한도 없음: `cr-03` 공유 한도 보존 요구와 충돌해 기각.
- **FSM 결합.** `approve`/`reject`는 호출자 결정으로 유지. `underwriting_executed`·`kyc_executed`는 FSM이 false로 강제하며 오버레이가 이를 참으로 바꾸지 않는다.

### 3.6 external_collateral_completeness (CAP-04)

- **값.** 완전성 사다리(순서 있음): `C0_NONE` → `C1_PLATFORM_SETOFF_AGREEMENT`(플랫폼 약관상 양도·상계 약정, 플랫폼 내부 원장 증거) → `C2_NOTIFIED_ASSIGNMENT_WITH_CERTIFIED_DATE`(확정일자 있는 채권양도 통지·승낙) → `C3_REGISTERED_CLAIM_SECURITY`(채권담보권 등기) → `C4_CHAIN_ANCHORED_CLAIM_SLICE_PLUS_C2`(온체인 claim slice 커밋먼트 + C2). 등급별 요구: T1 시뮬레이션 C1, 실자금 최소 C2. T2 시뮬레이션 C0, 실자금 제공 V1 없음. 시뮬레이션의 C1은 합성 표식이고 FSM 플래그 `collateral_perfected`·`external_pledge_complete`·`priority_bound`는 계속 false. 이중 담보 통제: 내부는 FSM 천장(`reserved_open ≤ open_face`), 외부는 수익자의 무담보 진술·보증 + 미래 `cr-02` claim slice 등록부. 체인 기록의 역할은 `EVIDENCE_NOT_PERFECTION`.
- **근거.** F04 계약 §0·§5와 모델 1: "외부에서 이미 양도·담보된 채권이 이 기록으로 사라졌다고 하지 않는다", 체인 등록만으로 외부 중복 담보가 사라졌다고 주장하지 않는다(마스터플랜 V2 §7). 선지급의 담보는 수익자의 정산 의무 잔액이므로 1차 완성은 플랫폼 상계 약정으로 시작하되, 실자금은 제3자 대항력이 있는 C2 이상을 요구한다.
- **대안.** 담보 완성 불요(무담보 상품): T2로만 남기고 실자금 V1에서 제외. 등기(C3) 필수: 소액·단기 선지급에 과도해 기각하되 사다리에 보존.
- **기초.** WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW — 양도 통지의 대항요건, 상계 가능성, PG·은행의 양도 제한 조항은 법무·파트너 확인 대상.

### 3.7 additional_margin (CAP-04)

- **값.** 선지급률 T1 8,500 bps(85 %), T2 5,000 bps(50 %). 차입기초 `eligible_face` = 수익자에게 귀속되는 정산 의무 줄(`payee ∈ beneficiary_payee_map[beneficiary_role]`)의 `outstanding` 합 − 열린 환불 액면. fixture 매핑 `{"fixture-organizer": ["organizer"]}`. 초기 현금 마진 0 bps(haircut이 마진). 재평가는 모든 오버레이 명령과 매 `sim_day` 틱에 현재 `settlement_source.view`로 한다(FSM 액면 스냅샷은 계약대로 동결). 마진콜 = `outstanding_exposure > floor(current_eligible_face × advance_rate_bps / 10000)`. 치유 5일, 치유 수단 순서: 부분 상환 → 추가 채권 담보(미래 `cr-02`) → 현금 마진 예치(미래, 분리 보관). 미치유 시 가속: 만기 := 치유 마감일, 이후 유예 뒤 부도 적격.
- **근거.** F04 계약 §2는 "스냅샷 이후 정산 변화에 맞춘 한도 재산정"을 비워 뒀다. 이를 FSM 밖 재평가로 채워 FSM 동결 규칙을 건드리지 않는다. `FINANCE_COMPLETION_DESIGN_KO.md` §6의 "확인 현금·회수채권을 한도에 더하지 않는다"를 그대로 지킨다.
- **대안.** 100 % 선지급(FSM 천장 그대로): 환불·차지백 역전에 무방비라 기각. 고정 70 %: 등급 차이를 못 살려 기각.
- **정직한 한계.** Capital 6487a99의 fixture 정산 조회는 불변이므로 지금은 마진콜이 실제로 발화하지 않는다. 검사는 항상 평가되며 seam(`settlement_source.view`)은 이미 있다.

### 3.8 collateral_execution (CAP-04)

- **값.** 1차 `SETOFF_AGAINST_BENEFICIARY_SETTLEMENT_DISTRIBUTION`: 결합 청구에서 수익자 payee에게 배분된 현금을 선지급에 먼저 충당한다. 오버레이가 `min(outstanding, distributed_to_beneficiary)`의 상환 제안을 만들고, `DEFAULTED` 전이면 운영자가 FSM `repay`를, 후이면 오버레이 회수 원장을 쓴다. 2차 `ASSIGNED_CLAIM_COLLECTION`(완전성 C2 이상, 시뮬레이션 밖). 3차 `LEGAL_RECOVERY`(프로토콜 밖, 사람). 절대 금지: 관람권 압류, 티켓 이전, 권리 취소, 토큰 압류. 집행 권한은 사람 2인, AI는 제안만. 토큰 담보는 V1 불수용(TK-12), 미래에도 추가 담보로만.
- **근거.** F04 계약 §7.6·§3: `FORECLOSE`·`PERFECT`·`PRIORITY`는 `CREDIT_PRODUCT_UNDEFINED`로 남고 "`default` 뒤에도 보유자와 버전은 그대로". 집행은 KRW 채권 경로뿐이며 FSM에 집행 명령을 만들지 않는다.
- **대안.** 티켓 재고 처분으로 회수: 모델 1과 F04 불변식 위반이라 기각. 자동 상계 실행: AI·자동 경계 위반이라 제안까지만.
- **기초.** WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW — 상계의 법적 효력, 양수 채권 추심의 허가 요건, 도산 절차에서의 지위.

### 3.9 reserve (CAP-04)

- **값.** 등급 가중 기대손실 충당: 잔액 대비 T1 150 bps, T2 500 bps, 만기 경과(연체) 2,500 bps, `DEFAULTED` 10,000 bps. 재원은 `PLATFORM_PROTOCOL_REVENUE_POOL`만. 금지 재원: 고객 예치금, 주최자 정산금, F03 환불준비금, 토큰 재무. 종결 시 환입, 상각 시 소진. 풀 목표 = max(충당금 합, 포트폴리오 잔액의 100 bps), 하한 0원. 원장은 오버레이 메모 계정(`SIM_LOSS_PROVISION`, `SIM_RESERVE_POOL`)이며 `projection.py`의 `SIMULATION_FIXED_V1` 계정표는 동결이므로 `SIMULATION_FIXED_V2` 후보 계정표로 확장한다(소유: `terms-overlay` + `fin-ledger-contract` 후보).
- **근거.** 토큰 청사진 §7.1·TK-4의 풀 분리와 F03 환불준비금의 별도성을 그대로 Capital 준비금에 적용한다. CAP-04 "담보·준비금"의 준비금 축을 채운다.
- **대안.** 준비금 없음: 손실 폭포 3단이 비어 기각. 고정 1 %: 등급·연체 민감도가 없어 기각.
- **기초.** WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW — 충당 방법과 수익 인식은 회계 검토 대상이며 `accounting_policy=SYNTHETIC_UNADOPTED`를 바꾸지 않는다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "financial-terms-decision",
  "decided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
  "date": "2026-10-08",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "scope": "KIX-CAPITAL simulation and product design only; not an offer; no real money; production NOT_AUTHORIZED; legal, tax, accounting and licensing content are working assumptions pending professional review",
  "delegation": "2026-10-08 18:25 KST JunTae Park delegated financial terms, settlement policy, upstream binding and accounts/tax/legal to Fable with the instruction to proceed with the grand ambition in mind",
  "bases": {
    "capital_main": "6487a99",
    "kix_protocol_main": "d71b411",
    "vendor_pin_commit": "7481b0e16ce9b903abbffa62249bb91cd9e63cfe",
    "pinned_credit_fsm_sha256": "f4f6b3698dd848538d2efa10b276cb33659eb4877fcbea0feb7429b28456491b",
    "pinned_mock_credit_sha256": "5e75fcc76fb0857f671b2fa33ca0fc851e9d676d4b5db8f357393367bc725d95"
  },
  "terms_version": "CAPITAL-TERMS-V1",
  "currency": "KRW",
  "units": {
    "money": "KRW integer, minor unit 1 KRW, FSM MONEY_MAX 1000000000000",
    "rate": "bps = 1/10000; *_bps_annual is per 365-day year",
    "time": "sim_day integer kept by the overlay; the pinned F04 journal carries no time"
  },
  "application_owner_node": "terms-overlay",
  "upstream_adoption_claimed": false,
  "fsm_constraints_respected": [
    "offer must pass product=None; terms never enter the pinned FSM",
    "draw is the full offered amount once; no partial draw",
    "repay carries principal only, amount in 1..outstanding, contiguous sequence",
    "close only when FSM outstanding == 0; overlay additionally requires interest_due == 0",
    "default only when FSM outstanding > 0; DEFAULTED is terminal, later recoveries live in the overlay ledger",
    "interest_defined, underwriting_executed, kyc_executed, collateral_perfected, priority_bound, external_pledge_complete, funds_executed stay false",
    "settlement face snapshot stays frozen (FACE_SNAPSHOT_FROZEN); re-evaluation reads settlement_source.view outside the FSM",
    "ceiling open_face - reserved_open remains the hard cap; overlay checks are stricter, never looser"
  ],
  "entries": {
    "interest_rate": {
      "status": "ADOPTED",
      "value": {
        "method": "SIMPLE_INTEREST_ON_OUTSTANDING_PRINCIPAL",
        "day_count": "ACT_365_FIXED",
        "compounding": "NONE",
        "accrual_start": "DRAW_DAY_INCLUSIVE",
        "accrual_end": "REPAYMENT_DAY_EXCLUSIVE",
        "min_interest_days": 1,
        "rounding": "EXACT_RATIONAL_ACCRUAL_FLOOR_TO_1_KRW_AT_POSTING_CARRY_REMAINDER",
        "formula": "interest = floor( sum_i(outstanding_i * days_i) * rate_bps / (10000 * 365) )",
        "base_rate_bps_annual": 300,
        "tiers": [
          {
            "id": "T1_COMMIT_OBSERVED",
            "condition": {"settlement_gate": "MOCK_COMMIT_OBSERVED", "refund_face": 0},
            "spread_bps_annual": 400,
            "all_in_bps_annual": 700
          },
          {
            "id": "T2_UNBOUND",
            "condition": {"settlement_gate": "UNBOUND"},
            "spread_bps_annual": 1000,
            "all_in_bps_annual": 1300,
            "real_funds_offering": "NOT_IN_V1"
          }
        ],
        "tier_selection": "from the accepted draw receipt credit.settlement_gate; fixed for the life of the advance",
        "default_interest_add_bps_annual": 300,
        "default_interest_from": "MATURITY_DAY_PLUS_1",
        "accrual_stop": "AT_CLOSE_OR_WRITEOFF",
        "all_in_cost_cap_bps_annual": 2000,
        "cap_check": "annualized interest plus all fees plus default interest must be <= all_in_cost_cap_bps_annual for every advance; violation blocks offer",
        "repayment_allocation_order": ["DEFAULT_INTEREST", "INTEREST", "PRINCIPAL"]
      },
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-08",
      "cap_rows": ["CAP-01"],
      "rationale": "Evidence-tiered pricing: T1 opens only after the bound settlement view is COMMITTED, so risk is refund reversal and the rate can be low; T2 is unbound and priced higher with a lower advance rate. Base rate is separated so it can later be rebound to a published index. The 2000 bps cap is a working assumption from the Korean statutory maximum rate including fees.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "review_items": ["statutory all-in rate cap and what counts as interest", "lender entity and licensing route"],
      "revisit_triggers": ["first synthetic or real loss data", "funding cost data", "index contract adopted", "f04-real-funds-lift-criteria merged"],
      "fsm_binding": "interest lives only in the overlay memo ledger; FSM repay receives the principal portion only"
    },
    "fees": {
      "status": "ADOPTED",
      "value": {
        "policy": "ZERO_FEE_INTEREST_ONLY",
        "fee_schedule_version": "CAPITAL-FEES-V1",
        "origination_fee_bps": 0,
        "servicing_fee_bps_annual": 0,
        "commitment_fee_bps_annual_on_undrawn": 0,
        "extension_fee_bps": 0,
        "prepayment_penalty_bps": 0,
        "late_fee": "NONE_DEFAULT_INTEREST_ONLY",
        "pg_and_settlement_fees": "NOT_CAPITAL_FEES; netted upstream in F01-F03 statements; the fee_bps 500 fixture is a settlement test fixture, not a credit fee"
      },
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-08",
      "cap_rows": ["CAP-01"],
      "rationale": "Per-draw fees annualize badly on 7-60 day advances under an all-in cap that treats fees as interest; the platform already earns settlement and resale fees from the same organizer; a single transparent rate is simpler for the overlay and the ticket-rights economy.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "revisit_triggers": ["professional confirmation that a specific fee is outside the cap", "servicing cost data"],
      "fsm_binding": "no FSM effect; cap_check assumes all fees are zero"
    },
    "term": {
      "status": "ADOPTED",
      "value": {
        "simulation_clock": {
          "kind": "OVERLAY_LOGICAL_DAY",
          "field": "sim_day",
          "start": 0,
          "advance": "explicit overlay command recorded in the overlay journal, never an F04 journal entry",
          "fsm_visibility": "NONE"
        },
        "standard_term_days": 60,
        "min_term_days": 7,
        "max_term_days": 180,
        "settlement_slack_days": 14,
        "settlement_linked_rule": "term_days = clamp(expected_settlement_cash_day - draw_day + settlement_slack_days, min_term_days, max_term_days) when an expected settlement cash day is known; otherwise standard_term_days",
        "maturity": "draw_day + term_days",
        "repayment_mode": "BULLET_AT_MATURITY_PARTIAL_ANYTIME",
        "prepayment": "ALLOWED_ANY_TIME_NO_PENALTY",
        "extension": {"count_max": 1, "days_max": 30, "approval": "HUMAN_OPERATOR", "hard_cap_total_days": 180},
        "grace_days_after_maturity": 10,
        "default_eligible_from": "maturity + grace_days_after_maturity + 1",
        "product_scope": "advance against captured settlement claims (F04); production funding before capture is a separate product (cr-01 scope item 1) and is not priced here"
      },
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-08",
      "cap_rows": ["CAP-01"],
      "rationale": "Settlement to organizers follows the show plus a refund window, so 60 days is standard and early-sale claims need up to 180; the FSM has no clock, so the overlay owns a logical day and maps maturity, grace and default eligibility onto FSM commands.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "revisit_triggers": ["real settlement cycle data from Toss profile answers", "cr-03 facility reservations adopted"],
      "fsm_binding": {
        "draw": "all-at-once; no partial draw",
        "repay": "principal portion only after overlay allocation; sequence contiguous; amount >= 1",
        "close": "FSM outstanding == 0 AND overlay interest_due == 0",
        "default": "operator command only when overlay reports DEFAULT_ELIGIBLE and FSM outstanding > 0"
      }
    },
    "default_loss_treatment": {
      "status": "ADOPTED",
      "value": {
        "default_trigger": "outstanding_exposure > 0 AND sim_day >= default_eligible_day; FSM default is a human-operator command, never automatic; AI proposes only",
        "acceleration_events": ["MARGIN_CALL_UNCURED", "BENEFICIARY_INSOLVENCY_NOTICE", "EVIDENCE_FRAUD_FINDING"],
        "recovery_waterfall": ["SETOFF_BOUND_CLAIM_BENEFICIARY_DISTRIBUTION", "SETOFF_OTHER_CLAIMS_SAME_BENEFICIARY", "LOSS_RESERVE", "PLATFORM_WRITEOFF"],
        "post_default_recovery_ledger": "OVERLAY_RECOVERY_LEDGER; the pinned FSM is terminal after DEFAULTED so recoveries are never FSM repay",
        "writeoff_days_after_default": 90,
        "writeoff_effect": "remaining exposure charged to loss reserve then platform P&L memo; FSM note stays NOTED and keeps holding the ceiling per contract; no ticket right is touched",
        "loss_bearer_v1": "KIX_CAPITAL_PLATFORM_100_PERCENT",
        "tranching_v1": "NONE",
        "loss_recognition": "EXPECTED_LOSS_RESERVE_THEN_SPECIFIC_PROVISION_AT_DEFAULT_THEN_WRITEOFF",
        "cure_after_default": "NOT_IN_FSM; late recoveries reduce overlay loss and never reopen the case"
      },
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-08",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "The F04 contract says default is not delinquency judgement, write-off, disposal or priority, so every financial meaning moves to the overlay while the FSM transition stays as pinned; a single platform loss bearer avoids investor-tranche questions until the claim-purchase program (CAP-03) exists.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "review_owner": "accounting and legal counsel designated by JunTae; question sheet via f04-real-funds-lift-criteria",
      "review_items": ["loss recognition and write-off timing under applicable accounting standards", "set-off enforceability in insolvency", "loss sharing once claim purchase or investor participation exists"],
      "fsm_binding": "default stays an operator command; DEFAULTED terminal; note stays NOTED"
    },
    "underwriting_depth": {
      "status": "ADOPTED",
      "value": {
        "depth": "EVIDENCE_RULES_V1",
        "personal_credit_data": "NONE",
        "checks_ordered": [
          {"id": "U1_SETTLEMENT_EVIDENCE", "rule": "tier from FSM settlement_gate; T1 requires the bound settlement view to be COMMITTED (FSM section 7.5 gate)"},
          {"id": "U2_REFUND_EXPOSURE", "rule": "refund_face == 0 or fixture_reclassified; the FSM REFUND_OBLIGATION_OPEN rule enforces it"},
          {"id": "U3_BORROWING_BASE", "rule": "amount <= floor(eligible_face * advance_rate_bps / 10000) in the overlay AND amount <= open_face - reserved_open in the FSM"},
          {"id": "U4_CONCENTRATION", "rule": "amount <= single_advance_cap_krw; beneficiary outstanding + amount <= beneficiary_aggregate_cap_krw; portfolio outstanding + amount <= portfolio_cap_krw"},
          {"id": "U5_DECISION_AUTHORITY", "rule": "approve by a human operator; two-person rule above two_person_threshold_krw; AI proposes only"},
          {"id": "U6_KYC_AML_STATUS", "rule": "simulation records kyc_executed=false; real funds require beneficiary legal-entity KYC/AML, owner f04-real-funds-lift-criteria"}
        ],
        "single_advance_cap_krw": 500000000,
        "beneficiary_aggregate_cap_krw": 2000000000,
        "portfolio_cap_krw": 20000000000,
        "two_person_threshold_krw": 50000000,
        "decision_record_fields": ["rules_version", "inputs_digest", "tier", "borrowing_base", "caps_remaining", "decided_by_role", "sim_day"],
        "ai_role": "PROPOSE_ONLY (executionAuthorized=false)"
      },
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-08",
      "cap_rows": ["CAP-01"],
      "rationale": "Reproducible rule-based underwriting on settlement evidence keeps CAP-19 minimum disclosure and the AI boundary; caps are sized for the rights-scale ambition and a growing book, not for today's 100,000 KRW fixtures.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "review_items": ["KYC/AML scope for legal-entity beneficiaries", "personal data boundaries if individuals ever become beneficiaries"],
      "revisit_triggers": ["AgentGrant/ActionPermit contract adopted", "cr-04 underwriting-consent adopted"],
      "fsm_binding": "approve and reject remain caller decisions; underwriting_executed and kyc_executed stay false"
    },
    "external_collateral_completeness": {
      "status": "ADOPTED",
      "value": {
        "ladder_ordered": ["C0_NONE", "C1_PLATFORM_SETOFF_AGREEMENT", "C2_NOTIFIED_ASSIGNMENT_WITH_CERTIFIED_DATE", "C3_REGISTERED_CLAIM_SECURITY", "C4_CHAIN_ANCHORED_CLAIM_SLICE_PLUS_C2"],
        "required_by_tier": {
          "T1_COMMIT_OBSERVED": {"simulation": "C1_PLATFORM_SETOFF_AGREEMENT", "real_funds_minimum": "C2_NOTIFIED_ASSIGNMENT_WITH_CERTIFIED_DATE"},
          "T2_UNBOUND": {"simulation": "C0_NONE", "real_funds_minimum": "NOT_OFFERED_V1"}
        },
        "simulation_grade_label": "C1 is a synthetic overlay mark; FSM flags collateral_perfected, external_pledge_complete and priority_bound stay false",
        "double_pledge_control": {
          "internal": "FSM ceiling reserved_open <= open_face plus overlay claim-slice uniqueness",
          "external": "beneficiary representation and warranty of no external pledge; future cr-02 claim-slice registry"
        },
        "chain_evidence_role": "EVIDENCE_NOT_PERFECTION"
      },
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-08",
      "cap_rows": ["CAP-04"],
      "rationale": "Model 1 and the F04 contract say chain or platform records do not erase external pledges, so completeness is a legal ladder evidenced but not created by the ledger; platform set-off is the natural first rung for advances against the platform's own settlement obligations.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "review_owner": "legal counsel designated by JunTae; PG and bank assignment clauses via Toss profile answers",
      "review_items": ["third-party effect of assignment notice", "set-off clauses in platform terms", "PG or bank restrictions on assignment of settlement proceeds"],
      "fsm_binding": "no flag is set true; the overlay stores the grade beside the advance"
    },
    "additional_margin": {
      "status": "ADOPTED",
      "value": {
        "advance_rate_bps_by_tier": {"T1_COMMIT_OBSERVED": 8500, "T2_UNBOUND": 5000},
        "eligible_face": "sum of outstanding on settlement obligation lines whose payee maps to the beneficiary, minus open refund face",
        "beneficiary_payee_map": {"fixture-organizer": ["organizer"]},
        "excluded_from_base": ["confirmed_cash", "recovery_due", "platform fee lines", "lines of other payees"],
        "initial_cash_margin_bps": 0,
        "reevaluation": "ON_EVERY_OVERLAY_COMMAND_AND_SIM_DAY_TICK using current settlement_source.view; FSM face snapshot stays frozen",
        "margin_call_trigger": "outstanding_exposure > floor(current_eligible_face * advance_rate_bps / 10000)",
        "cure_window_days": 5,
        "cure_options_ordered": ["PARTIAL_REPAY_TO_WITHIN_BASE", "ADDITIONAL_CLAIM_PLEDGE (future cr-02 claim slice)", "CASH_MARGIN_DEPOSIT (future; segregated, never platform revenue)"],
        "uncured_consequence": "ACCELERATION: maturity := cure_deadline; default-eligible after grace",
        "simulation_note": "fixture settlement views are immutable in Capital 6487a99 so a margin call cannot fire there yet; the check is still implemented and evaluated"
      },
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-08",
      "cap_rows": ["CAP-04"],
      "rationale": "The F04 contract leaves limit recalculation after the snapshot empty; the overlay fills it outside the frozen FSM snapshot and never adds confirmed cash or recovery due to the lending base.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "revisit_triggers": ["live settlement views bound (CAP-07)", "cr-02 claim eligibility adopted", "loss data by tier"],
      "fsm_binding": "stricter than the FSM ceiling; the FSM rule open_face - reserved_open still applies"
    },
    "collateral_execution": {
      "status": "ADOPTED",
      "value": {
        "primary": "SETOFF_AGAINST_BENEFICIARY_SETTLEMENT_DISTRIBUTION",
        "mechanics": "cash distributed to the beneficiary payee on the bound claim is applied to the advance first; the overlay proposes repay = min(outstanding, distributed_to_beneficiary); before DEFAULTED the operator posts FSM repay, after DEFAULTED the overlay recovery ledger records it",
        "secondary": "ASSIGNED_CLAIM_COLLECTION (requires completeness >= C2; outside simulation)",
        "tertiary": "LEGAL_RECOVERY (outside the protocol; human-run)",
        "never": ["ADMISSION_RIGHT_SEIZURE", "TICKET_TRANSFER", "RIGHT_CANCELLATION", "TOKEN_SEIZURE"],
        "execution_authority": "HUMAN_OPERATOR_TWO_PERSON; AI proposes only",
        "token_collateral": "NOT_ACCEPTED_V1 (token blueprint TK-12: never sole collateral; any future token margin is additive only after TL-0 and TL-L)"
      },
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-08",
      "cap_rows": ["CAP-04"],
      "rationale": "FORECLOSE, PERFECT and PRIORITY stay CREDIT_PRODUCT_UNDEFINED in the pinned FSM and default never moves a ticket; execution is a KRW claim path with human authority, consistent with model 1 and the AI boundary.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "review_owner": "legal counsel designated by JunTae",
      "review_items": ["legal effect of set-off against settlement distributions", "licensing requirements for collecting assigned claims", "position in insolvency proceedings"],
      "fsm_binding": "no execution command exists; vendor code is never edited; execution is overlay plus human process"
    },
    "reserve": {
      "status": "ADOPTED",
      "value": {
        "method": "TIER_WEIGHTED_EXPECTED_LOSS_PROVISION",
        "provision_bps_of_outstanding": {"T1_COMMIT_OBSERVED": 150, "T2_UNBOUND": 500, "PAST_DUE_ANY_TIER": 2500, "DEFAULTED": 10000},
        "funding_source": "PLATFORM_PROTOCOL_REVENUE_POOL",
        "forbidden_sources": ["CUSTOMER_DEPOSITS", "ORGANIZER_SETTLEMENT_FUNDS", "REFUND_RESERVE_F03", "TOKEN_TREASURY"],
        "release": "AT_CLOSE provision reversed; AT_WRITEOFF provision consumed",
        "pool_target": "max(sum of provisions, 100 bps of portfolio outstanding)",
        "minimum_pool_floor_krw": 0,
        "ledger": "overlay memo accounts SIM_LOSS_PROVISION and SIM_RESERVE_POOL in a SIMULATION_FIXED_V2 candidate chart; projection.py chart V1 is frozen; extension owned by terms-overlay with the fin-ledger-contract candidate"
      },
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-08",
      "cap_rows": ["CAP-04"],
      "rationale": "Pool separation follows the token blueprint TK-4 and section 7.1 and the F03 refund reserve separation; tier and delinquency weights give the loss waterfall a funded third step.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "review_owner": "accounting counsel designated by JunTae",
      "review_items": ["provisioning method under applicable accounting standards", "whether a pool must be segregated or is a book provision", "tax treatment of provisions"],
      "fsm_binding": "no FSM effect; accounting_policy stays SYNTHETIC_UNADOPTED"
    }
  }
}
```

## 5. 수용 기준 매핑

| 수용 기준 | 충족 위치 |
|---|---|
| `docs/decisions/CAPITAL_FINANCIAL_TERMS.md`에 하나의 ```` ```capital-decision-v1 ```` 블록, 아홉 항목 각 `{status, value, provided_by, date, cap_rows, rationale, provisional, basis}` | §4. 블록은 이 문서에 하나뿐이고, `interest_rate`·`fees`·`term`·`default_loss_treatment`·`underwriting_depth`·`external_collateral_completeness`·`additional_margin`·`collateral_execution`·`reserve` 아홉 항목이 모두 있으며 각 항목이 여덟 필수 키를 가진다 |
| ADOPTED는 `provided_by "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08"`, date, `provisional: true` | §4 아홉 항목 모두 동일 문자열·`2026-10-08`·`true`. UNDETERMINED 항목은 없다. 따라서 "UNDETERMINED에 value", "ADOPTED에 provided_by/date 누락"이라는 무효 조합도 없다 |
| 구체적·포부 있는·구현 가능한 값, UNDETERMINED는 이유와 함께만 | §3 각 항목의 값·근거·대안. UNDETERMINED를 쓰지 않은 이유는 머리말(위임으로 결정 권한이 옮겨짐)과 §2 다섯째 항목. 법률·회계 의존 항목은 UNDETERMINED 대신 `basis: WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW`와 `review_owner`로 표시했다 |
| PROVISIONAL PRODUCT DECISION 라벨, 청약 아님·실자금 없음, 법률·세무·회계는 작업 가정 | 머리말 상태 배너와 §4 `status`/`scope` |
| KIX 장기 비전과의 연결과 읽은 kix-protocol 문서 경로 인용 | §2 (README, DEVELOPMENT_PLAN §1·§5·§11·§14·§18, BLUEPRINT_20260914, ROADMAP, PROGRAM_ROADMAP_20260930, PROGRAM_DECISIONS_20260928, AUTHORITY_MODEL_1, TOKEN_LAYER_AND_RIGHTS_SCALE_SCOPE_20260929, RIGHTS_SCALE_RS0_DECISION_20261008, RUNTIME_ARCHITECTURE_S062, COMMERCE_CONTRACTS, blueprints 2종, contracts CREDIT_ADVANCE_F04·SETTLEMENT_DISTRIBUTION_F01_F03, aiops FINANCE_COMPLETION_DESIGN_KO·PROGRAM_EXPANSION_20261002_KO·PROGRAM_ASTRA_DELEGATION, adr/0002, tasks/TASK_005, PROTOCOL_MASTERPLAN_V2 §7) |
| 열린 위험 목록 | §6 |
| 모든 수용 항목 매핑 | 이 표 |
| 항목별 CAP row(CAP-01, CAP-04)와 적용 소유 노드 `terms-overlay` 명시, 기계 판독 가능 | §1 표의 CAP rows 열, §4 `cap_rows`·`application_owner_node`, 값은 정수·bps·enum·순서 있는 목록. 적용은 §7 첫 항목 |
| diff는 `docs/decisions/`에 한정, `capital/`·`tests/` 불변, 다섯 vendor SHA256 불변 | 이 노트는 문서 한 파일만 추가한다. 코드·테스트·vendor를 건드리지 않으며 `capital/vendor/manifest.json`의 다섯 해시는 §4 `bases`에 그대로 인용했다. 실제 diff 범위 확인은 PR과 독립 리뷰어가 한다 |
| (이전 요청문) readiness·`/api/readiness` CAP-01/CAP-04 행이 결정 노트를 인용 | 이 노드 범위 밖. `terms-overlay`가 한다(§7). 현재 `capital/readiness.py`의 `financial-contracts` 차단 사유와 `capital/service.py` snapshot의 `decisions` 문구가 바뀔 대상이다 |
| (이전 요청문) vendor F04 파일 SHA256 잠금 유지, 조건 적용은 overlay에만 | §4 `fsm_constraints_respected`, 각 항목 `fsm_binding`. vendor 수정은 어느 항목에서도 요구하지 않는다 |

## 6. 열린 위험과 재검토 조건

- **최고금리·수수료 정의(법무).** 2,000 bps 총비용 상한과 "모든 수수료는 이자"라는 전제는 작업 가정이다. 대주 주체가 대부업 등록 사업자인지 제휴 금융기관인지에 따라 적용 법령이 달라진다. 전문가 검토 결과가 다르면 `interest_rate.all_in_cost_cap_bps_annual`과 `fees`를 다시 연다.
- **대주·차주·담보권자의 법적 확정(법무·인허가).** 아홉 항목 밖이지만 모든 항목의 전제다. F04 계약 §5 첫 줄의 빈 항목이며 `f04-real-funds-lift-criteria`(사용자 병합)가 소유한다. 이 문서는 실자금 해제 근거가 아니다.
- **채권양도 대항요건·상계·도산(법무).** C2 요구와 1차 집행(상계)의 효력은 PG·은행의 양도 제한 조항과 도산 절차에 좌우된다. 토스 프로파일의 미확인 항목(MID·가맹 범위·정산 대금 복수 수취인)과 함께 확인해야 한다.
- **손실 인식·충당·세무(회계·세무).** 상각 90일, 충당 bps, 준비금 풀의 성격(분리 보관 vs 장부 충당)과 이자소득 과세는 회계·세무 검토 대상이다. `accounting_policy=SYNTHETIC_UNADOPTED`는 유지된다.
- **금리·선지급률·충당 bps의 데이터 부재.** 손실·연체·자금조달 비용 데이터가 없다. 숫자는 제품 설계 판단이며 첫 합성 손실 실험(`fin-credit-exposure-reconciliation`)이나 실데이터가 생기면 재검토한다.
- **T2 UNBOUND 등급.** F04가 무결합 인출을 허용하므로 조건을 정했지만 실자금 V1에서는 제공하지 않는다. 화면 기본 여정이 결합을 먼저 요구하는 현재 동작은 유지한다.
- **시뮬레이션 시계.** `sim_day`는 논리 일이다. 실제 시간·제공자 시각·체인 시각이 아니다. 오버레이 저널에 시계 전진을 적어야 재생이 결정론적이다. 이는 `terms-overlay`의 설계 부담이다.
- **마진콜 미발화.** fixture 정산 조회가 불변이라 현재 저장소에서 마진콜·가속 경로를 실제로 검증할 수 없다. 라이브 조회(CAP-07) 또는 가변 fixture가 생길 때까지 해당 분기는 단위 검사로만 덮인다.
- **집중도 한도와 fixture 규모.** 억 단위 한도는 100,000원 fixture에서 절대 묶이지 않는다. 한도 검사의 거절 분기는 합성 대형 fixture로 따로 검증해야 한다.
- **수익자 라벨 매핑.** `fixture-organizer` ↔ `organizer` 매핑은 fixture 전용이다. 실제 producer 바인딩 전에는 역할 라벨이 법적 당사자가 아니라는 F01·F04 규칙이 그대로다.
- **토큰 담보.** TL-0·TL-L 전에는 토큰을 담보로 받지 않는다. TL 결정이 바뀌어도 KRW 손실의 단독 담보로는 쓰지 않는다(TK-12).
- **upstream 정합성.** upstream `f04-mock-deepening`이 다른 값을 채택하면 이 문서는 개정 대상이다. 이 문서가 upstream 결정을 대신하지 않는다.

## 7. 후속 작업

- **`terms-overlay`(적용 소유).** §4 JSON을 `CAPITAL-TERMS-V1`로 로드한다. 할 일: (1) 오버레이 원장과 오버레이 저널(이자 메모, 충당, 회수, 시계 전진, 결정 레코드)을 F04 저널과 분리해 두고 digest로 덮는다. (2) 인출 사전점검(`/api/preview`)과 `offer`/`draw` 앞에 U1~U6·차입기초·상한 검사를 둔다. 거절은 FSM 호출 전에 오버레이 코드로 돌려준다. (3) 상환 배분(연체이자 → 이자 → 원금) 뒤 원금 몫만 FSM `repay`에 넘기고, `close` 앞에 이자 미수 0을 확인한다. (4) `capital/readiness.py`의 `financial-contracts` 차단 사유와 `capital/service.py` snapshot의 `decisions` 문구를 이 문서 인용으로 바꾸고, `/api/readiness` CAP-01·CAP-04 행이 `PROVISIONAL per docs/decisions/CAPITAL_FINANCIAL_TERMS.md (CAPITAL-TERMS-V1)`를 보이게 한다. (5) `SIMULATION_FIXED_V2` 후보 계정표를 별도 `ProjectionPort` 구현으로 추가하되 V1은 그대로 둔다. (6) vendor 바이트와 다섯 해시는 불변이어야 하고 `test_vendor_pin_byte_integrity`가 계속 통과해야 한다.
- **`docs/RELEASES.md` 템플릿.** "금리·수수료·한도를 지어내지 말라"는 규칙은 유지한다. 이후 릴리스 노트는 값을 적지 않고 이 문서의 `terms_version`을 인용한다.
- **upstream `f04-mock-deepening`(사용자 병합, Astra 게이트).** 이 문서의 §4를 입력 후보로 제출할 수 있다. 채택은 upstream PR 영수증만이 증명하며, 채택 전까지 Capital의 `upstream_adoption_claimed=false`를 유지한다.
- **upstream `f04-real-funds-lift-criteria`(사용자).** §6의 법무·회계·세무·인허가 항목과 각 항목의 `review_items`를 질문지로 넘긴다.
- **upstream 여신 수명 노드 `cr-01`~`cr-07`(pending catalogue).** 매핑: `cr-01` 상품·주체·정책 버전 ← `terms_version`·등급·한도, `cr-02` 적격성·차입기초 ← `additional_margin.eligible_face`·완전성 사다리, `cr-03` 약정·공유 한도 ← 집중도 한도, `cr-04` 심사·동의 ← `underwriting_depth`, `cr-05` 지급 관측 ← 범위 밖(실자금), `cr-06` 상환 배분 ← 이자 공식·배분 순서, `cr-07` 연체·회수·상각 ← `default_loss_treatment`.
- **`fin-credit-exposure-reconciliation`·`fin-ledger-contract` 후보.** 노출·이자·충당 메모의 보존식과 `cut` 표기를 그 후보 계약에 넘긴다. 분모를 줄이거나 노드를 완료로 표시하지 않는다.
- **`settlement-policy-deepening`(정산 정책, 같은 위임 범위).** 1차 집행(배분 상계)은 F02 배정 순서 결정에 의존한다. 그 결정 노트가 나오면 `collateral_execution.mechanics`의 "수익자에게 배분된 현금" 정의를 그 순서에 맞춰 재확인한다.
- **TL·AI 노드.** `tl-0`·`tl-legal-brief`가 토큰 담보 가능성을 다루면 `collateral_execution.token_collateral`을 재검토한다. `ai-delegation-contract-mock`이 `AgentGrant`/`ActionPermit`을 정하면 `two_person_threshold_krw`를 그 금액 scope에 결합한다.
- **Commerce `bind-credit-fsm`.** 이 문서는 Commerce 화면을 바꾸지 않는다. 화면이 조건을 보여 주려면 Capital 오버레이의 조회를 소비해야 하며 클라이언트 산술은 금지다.
