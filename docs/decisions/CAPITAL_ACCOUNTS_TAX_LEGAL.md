# Capital 회계·세무·법무·인허가·보존 결정 — 계정표 매핑, 수익 인식, 세무 처리, 여신·채권거래 인허가 경로, 데이터 보존·개인정보

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
이 문서는 KIX-CAPITAL 저장소 안의 **시뮬레이션·제품 설계용** 결정이다. 청약이나 대출 제안이 아니고, 실자금이 움직이지 않으며, production은 계속 `NOT_AUTHORIZED`다. 회계·세무·법무·인허가·개인정보 관련 내용은 **전문가 검토 전의 작업 가정(WORKING ASSUMPTION)** 이며 법률·세무·회계 자문이 아니다. 다섯 항목 모두 `basis = WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW`다. 어떤 upstream 계약(kix-protocol `fin-ledger-contract`, `settlement-policy-deepening`, `f04-real-funds-lift-criteria`, `k2-retention-proposal` 후속 등)의 채택도 주장하지 않는다. 합성 투영(`SIMULATION_FIXED_V1`)의 숫자·fixture에서 어떤 회계·세무 입장도 추론하지 않는다. 이 문서는 kix-protocol·kix-commerce-apps를 수정하지 않고, 어떤 upstream 노드도 완료로 표시하지 않으며, diff는 `docs/decisions/` 한 파일이다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `accounts-tax-legal-decision` (Decision: account chart, tax treatment, legal/licensing and retention constraints) · deps `finance-projection` · kind `decision` · user_merge `False` |
| 결정자 | **Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08** |
| 위임 원문 | 2026-10-08 18:25 KST JunTae Park: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." |
| 결정일 | 2026-10-09 |
| KIX-CAPITAL 기준 | main `361a55c` (upstream-binding-decision #16). 선행 결정 문서는 [CAPITAL_FINANCIAL_TERMS.md](CAPITAL_FINANCIAL_TERMS.md)(`CAPITAL-TERMS-V1`, 2026-10-08)와 [CAPITAL_UPSTREAM_BINDING.md](CAPITAL_UPSTREAM_BINDING.md)(2026-10-09)이며, 이 문서는 두 문서의 값(이자·수수료·준비금·손실 인식, 보존 네 칸 구조, IdP/KYC 비채택, ProjectionPort 목표 = `fin-ledger-contract` ProjectionEntry)과 충돌하지 않고 그 위에 쌓는다 |
| finance-projection 입력 | `capital/projection.py` `SimulationProjection.CHART_VERSION = SIMULATION_FIXED_V1`, 합성 계정 다섯 종(`SIM_CLAIM_FACE`, `SIM_PAYEE_OBLIGATION`, `SIM_ADVANCE_EXPOSURE`, `SIM_ADVANCE_OBLIGATION`, `SIM_REPAY_MEMO`), 보존 술어 다섯 개. `tests/golden/demo.json`은 debit = credit = 385,000(합성 단위), `accounting_policy = SYNTHETIC_UNADOPTED`를 고정한다 |
| kix-protocol 기준 | main `51d8380` (`51d83808478e56c81c6f43e2a13450d435e922e6`, 읽기 전용 체크아웃 `/workspace/capital-run/kixproto-ro`, `.git/refs/heads/main`에서 확인) |
| vendor pin | `capital/vendor/manifest.json` commit `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`, 다섯 파일 SHA256 불변. 이 결정은 `capital/`·`tests/`·vendor 바이트를 바꾸지 않는다 |
| 상태 어휘 | **ADOPTED** = Fable이 위임 범위 안에서 Capital의 잠정 값을 정했다(전문가 검토 대상). **UNDETERMINED** = 정직하게 값을 정할 수 없어 담당과 이유만 적는다(`value: null`, 방향은 `target`). 이번 노트의 다섯 항목은 모두 ADOPTED이고, 기간 숫자처럼 upstream 사용자 결정(#139 R1)이 "멈춘 채로 둔다"고 정한 값만 ADOPTED 구조 안의 `NOT_SET_OWNER_SUPPLIED` 자리로 남긴다 |
| owner 어휘 | 각 항목의 `owner`는 **Capital 안의 소유 역할**이다. 현재 보유자는 위임에 따른 Fable 5.1이고, 전문가 검토자(회계사·세무사·법무/개인정보 담당)는 JunTae가 지명한다(upstream D-E, `PROGRAM_ROADMAP_20260930.md` §2). 아직 이름은 없다 |
| SIMULATION 차트 유지 여부 | **유지한다.** `SIMULATION_FIXED_V1`은 출시 로컬 제품의 기본이자 유일한 `ProjectionPort` 출력으로 남는다. 라벨(`accounting_policy=SYNTHETIC_UNADOPTED`, `tax=NOT_BOUND`, `legal=NOT_BOUND`, `operating_ledger=NOT_BOUND`)·계정 kind(`SYNTHETIC_*`)·숫자·golden digest는 바뀌지 않는다. 이 노트의 계정표(`CAPITAL-COA-V1`)는 **매핑 문서 + 추가형 후보**이며 V1을 대체하지 않는다(§3.1) |

용어: 금액은 KRW 정수(최소단위 1원, upstream `AssetSpec {fiat, KRW, 0}`), 비율은 bps, 날짜는 오버레이 논리 일(`sim_day`, `CAPITAL-TERMS-V1`). 고정 FSM은 `capital/vendor/credit_advance_f04/credit_fsm.py`와 `capital/vendor/settlement_f01_f03/settlement_fsm.py`이며 이 결정은 어느 FSM도 바꾸지 않는다.

## 1. 결정 요약

| item | 결정 (요지) | CAP rows | 소비 노드 / seam |
|---|---|---|---|
| `chart_of_accounts_mapping` | **ADOPTED.** `CAPITAL-COA-V1`: 자산별(AssetSpec) 원장, 4자리 분류 코드 + 식별자 차원(계정 코드에 식별자를 넣지 않음), 재무 계정(1000·1100·1110·1190·1300·2300·3100·3200·4100·4110·4200·4300·5100·5200)과 메모 계정(9100~9700). V1 다섯 계정과 분개 7종을 COA-V1로 매핑. 정산 청구 액면은 Capital 자산이 아니라 **메모(9100/9110)** | CAP-13, CAP-14, CAP-15 | `ProjectionPort` — 추가형 `SIMULATION_FIXED_V2`/`CAPITAL_COA_V1_CANDIDATE` 구현(`terms-overlay` + `projection-coa-candidate`), V1 불변 · `reconciliation` — 새 검사 `coa_candidate_totals_vs_v1` · `export manifest` — `projection` 섹션의 chart 표기 |
| `revenue_recognition_basis` | **ADOPTED.** `CAPITAL-REVREC-V1`: Capital 수익은 이자(4100)·연체이자(4110)·상각 후 회수(4300)뿐(수수료 0). 발생주의·시간비례(단리 ACT/365, `CAPITAL-TERMS-V1`), 인출 수락 영수증에서 시작, 종결에서 종료, `DEFAULTED` 뒤 발생 이자는 **인식 유예(9700 메모)·현금 수령 시 인식**, 상각 시 미수 이자 환입. 정산 청구 액면·플랫폼 정산 수수료·최초판매/리셀 매출은 Capital 수익이 아님 | CAP-13, CAP-14 | `ProjectionPort` V2 후보(1110/4100/4110/4300 분개는 오버레이 이자 원장에서) · `reconciliation`(이자 원장 ↔ 투영 합계 새 검사) · `statement`는 수익 구분을 추가하지 않음(CAP-09 문구 불변) · `export manifest` statement/projection 섹션 |
| `tax_reporting_treatment` | **ADOPTED.** `CAPITAL-TAX-V1`(KR 작업 가정): 이자소득 = 부가가치세 **면세 금융용역**(세금계산서 없음), Capital 수수료(0)는 발생 시 과세, 플랫폼 정산 수수료의 VAT는 upstream 미정으로 Capital 몫 아님. 수취 이자 **원천징수 필드 예약**(`withholding_rate_bps`, 시뮬레이션 0, 1300 선납세금 계정). 충당금·상각의 세무상 차이는 BTD 메모. 정산 명세서 `tax` 성분은 PG 측 차감 관측이며 Capital 세금이 아님. 출시 제품의 `tax=NOT_BOUND`·`tax_reporting=NOT_BOUND`는 유지, 어떤 산출물도 세무 신고가 아님 | CAP-13, CAP-15 | `ProjectionPort` V2 후보(1300·2300·BTD 메모) · `export manifest`(미래 `tax_memo` 섹션; 회계사 검토 뒤에만) · `statement`는 `tax_reporting: NOT_BOUND` 유지 — **adapter 전까지 로컬 소비자 없음** |
| `lending_or_claim_trading_licence` | **ADOPTED (설계 경로; 법적 적용 판단은 PENDING_PROFESSIONAL_REVIEW).** `CAPITAL-LICENCE-ROUTE-V1`: V1 상품 = 주최자 법인 대상 정산채권 선지급(B2B, 예금 없음, 투자자 없음). **1차 경로 = 대부업법 등록 대주 법인(KIX Capital 전담 법인)**, 대안 = 면허 파트너 대주 + KIX Capital 플랫폼·서비서. CAP-03 채권매입은 V1 `NOT_OFFERED`, 목표는 대주 법인의 상환청구권 있는 매입(=대부로 취급, 작업 가정), 제3자 투자자 slice·non-recourse는 증권성·온투업·채권추심업 검토 뒤. 실자금 해제는 사용자 노드 `f04-real-funds-lift-criteria` | CAP-13, CAP-15 | **no local consumer** (seam 없음; FSM 플래그 `license_granted`·`regulated_product` 거짓 유지; `readiness` release 그룹 차단 사유와 CAP-03 행이 이 노트를 인용하도록 sync) |
| `data_retention_privacy` | **ADOPTED.** `CAPITAL-RETENTION-PRIVACY-V1`: 데이터 분류 7종(모두 PII 없음), `NO_PERSONAL_DATA_BY_DESIGN_V1`, 보존 칸 **다섯**(upstream R1 네 칸 + Capital 추가 `tax_accounting_records`), 칸마다 주인, **기간 숫자는 비움**(upstream #139 R1 사용자 결정 준수), 시뮬레이션 보존 = `RETAIN_ALL_NO_AUTOMATIC_DELETION`(용량 상한은 거절이지 축출 아님), 법정·분쟁 보류 우선, 체인 앵커 자료에 개인정보 금지, 미래 개인정보 삭제는 IdP/KYC 제공자 측 | CAP-14, CAP-15 | `export manifest` — `retention_policy` 자리(`retention-slots-sync`가 `NOT_BOUND` 상수를 이름 있는 빈 칸으로 교체) · `reconciliation`(`unknown_policy.retry_authorized=false` 불변) · `readiness` release 그룹 |
| (상태) SIMULATION 차트 | **출시 로컬 제품에 남는다.** 조건은 §3.1 끝 표 | CAP-13 | `ProjectionPort` 기본 구현 `SimulationProjection` 불변 |

## 2. KIX 비전과의 연결

읽은 kix-protocol 문서(모두 main `51d8380`)와, 각 선택이 그 비전에 봉사하는 방식이다.

- **모델 1 — 체인 권위 / 오프체인 위임 실행과 "다른 사실의 분리".** `README.md` §1·§3, `docs/decisions/AUTHORITY_MODEL_1.md`(A-4: 기록과 재생의 필수 분리, "오프체인 커밋 위치와 체인 확정 위치를 각각 보존"), `docs/DEVELOPMENT_PLAN.md` §1("체인 재고·권리 원권위와 제공자 자금 사실, 오프체인 예약 약정은 다른 사실") §14("금융은 권리·정산채권·채무·부담을 구별"). 그래서 계정표는 **정산 청구 액면을 Capital 자산으로 올리지 않고 메모(9100/9110)** 로 두고, Capital 자산은 자기 선지급 원금·미수 이자뿐이다. 관람권·토큰은 어떤 계정에도 들어가지 않는다(TK-1).
- **5·6·7단계와 데이터 처리 계층.** `DEVELOPMENT_PLAN.md` §3 계층표("데이터 처리 | 일관된 export·CPU 분석·SQL 감사"), §5(5단계 영속 거래 → 6단계 합성 금액 참조 모델 → 7단계 인증 export), §13("인증된 일관 export부터 구현하고 source cut과 projection watermark를 구분"), `docs/decisions/PROGRAM_ROADMAP_20260930.md` R-10·R-11, `docs/RUNTIME_ARCHITECTURE_S062.md`(역사: committed facts → Arrow/Parquet → DuckDB 대사, §4 u128 atoms + 인증 registry, §9 "event time과 commit/observation ordering을 point-in-time 재구성을 위해 보존"). COA-V1의 모든 분개는 `source_cut`·`sim_day`·`chart_version`·`terms_version` 차원을 갖고, 수익은 **cut 단위로만** 보고하며 cut이 다른 보고서를 하나의 닫힌 잔액으로 합치지 않는다.
- **Finance 설계의 UNDETERMINED 목록을 그대로 채우는 것이 이 노드의 몫.** `docs/aiops/FINANCE_COMPLETION_DESIGN_KO.md` §3은 "계정 체계·수익 인식·예수/준비금/회수채권/손실 분류·세금·보존기간은 UNDETERMINED … User와 지명 외부 회계·법무 담당이 답할 목록"이라고 적고, "account 라벨은 승인되지 않은 법적 당사자·은행 계좌·회계 계정과목의 의미를 갖지 않는 합성 role"이라고 못 박는다. §7은 "tax filing·GAAP/IFRS 준수·regulated lending 보고서라는 표식을 주지 않는다"고 적는다. 이 노트는 그 목록에 **Capital 로컬 잠정 값**을 넣되 upstream 상태를 바꾸지 않고, V1 합성 role은 그대로 합성 role로 둔다.
- **역사 청사진이 요구한 금융 근거의 분해.** `docs/BLUEPRINT_20260914.md` §3("금융 제공자가 제작자금을 공급하는 계약과 티켓 구매자의 결제는 별도 자금 흐름"), §4 표("배분·환불·회수 의무 → 고정 정책과 확인된 사건으로 계산한 회계 원장; 의무별 잔액, 지급·회수·상각 처리 근거"), §5 `Obligation / LedgerEntry`("수취인, 발생 원인, 금액·통화, 정책, 차변·대변; 배분 예정·지급 완료·회수채권·환불 의무 분리"), §10("승인액, 권리 확정액, 최초 판매와 리셀 거래액, 배분 의무, 실지급, 미완료 환불, 미확정 지급, 미회수금, 수수료·세금·보류를 각각 표시… 리셀 총액을 주최자 수익에 전부 더하지 않는다"), `docs/ROADMAP.md` 우선순위 7. 현행 승인은 아니지만 안전 요구는 폐기되지 않았다. 메모 계정 9200/9300/9400과 `primary_and_resale = NOT_SUMMED` 유지가 그 요구의 번역이다.
- **정수 산술과 명세서 성분 등식.** `docs/COMMERCE_CONTRACTS.md`(AssetSpec, float 금지, "할인 부담 취소분을 수취 가능한 현금이나 확정된 외부 채권으로 자동 분개하지 않는다"), `docs/contracts/SETTLEMENT_DISTRIBUTION_F01_F03.md` §3(`gross = amount + fee + tax + held + adjustment`; "fee·tax·held·adjustment는 배정 가능한 현금이 아니고 의무 액면을 줄이지 않는다") §7(세금·보류·조정 잔액의 해제와 실제 회수는 미정). 그래서 `tax_reporting_treatment`는 명세서 `tax` 성분을 **PG 측 차감 관측**으로만 읽고 Capital 세금으로 삼지 않는다.
- **F04 계약이 의도적으로 비운 항목과 E06.** `docs/contracts/CREDIT_ADVANCE_F04.md` §0(E06: "인허가 판단, 법적 책임, 개인정보 보존"은 고정하지 않음), §1(`license_granted`·`regulated_product`·`legal_debtor_bound` 등 항상 거짓), §5(대주·차주 법적 확정, 인허가, 준비금, 규제 준수 등 빈 항목), `docs/status/ORIGINAL_32_STATUS.md` E06("환불·담보 당사자와 법적 책임, 개인정보 접근/보존 계약", 설계중), `docs/status/CURRENT_CAPABILITY_REGISTER.md` E06 행("법무/개인정보/회계·보존·당사자 서면 입력"). 인허가 경로와 보존·개인정보 결정은 이 빈 항목의 **Capital 측 작업 가정**이며 FSM 플래그를 참으로 바꾸지 않고 E06 라벨도 올리지 않는다.
- **잠금과 해제 조건.** `docs/decisions/PROGRAM_DECISIONS_20260928.md` §2.1(F04는 mock·시뮬레이션만) §5("실제 여신·규제 금융 | 법률·인허가 검토와 Astra·사용자 명시 승인"), `PROGRAM_ROADMAP_20260930.md` §2 D-E("법률·회계·세무·금융 검토의 주체와 시점은 사람이 정할 일이라 사용자 몫", `tl-legal-brief`) §5(실자금·실제 여신·규제 금융은 실행 노드로 넣지 않음; `f04-real-funds-lift-criteria`는 사용자 노드), `docs/aiops/PROGRAM_EXPANSION_20261002_KO.md` `cr-01-product-authority`("정산채권 기반 선지급의 대주·차주·정책·증거 권위를 먼저 확정… 금리·수수료·기간·담보 효력을 임의 결정하지 않는다", pending). 인허가 경로는 **설계 가정과 입력 후보**이며 실자금 해제는 여전히 사용자 노드다.
- **보존 네 칸과 I10.** `docs/decisions/RETENTION_PERIODS_PROPOSAL_20261009.md`(R1, PR #139 `6e54e723…` 사용자 병합: 네 칸을 유지하고 값은 멈춘 채, 제공자 공개값은 기간이 아님, 세무·회계 보존 담당은 질문서에 없어 사용자가 지명), `docs/DEVELOPMENT_PLAN.md` §6.3, `docs/contracts/STATE_LIFECYCLE.md` §6("메모리 결과 캐시의 축출은 권위 이력 폐기가 아니다… dispute/법정 보존 참조를 확인"), `docs/contracts/FIRST_BATCH_OPEN_INPUTS.md` I10·I11·I13, `docs/contracts/PG_TOSS_CARD_PROFILE.md`(15일 멱등키는 보존기간이 아님), `docs/status/FIRST_BATCH_OWNER_QUESTION_SHEETS_KO.md`("개인정보 원문은 질문서·Git·채팅에 넣지 말라"), `docs/reviews/TOSS_METHOD_EXPANSION_REVIEW.md` TM09(환불계좌 개인정보 최소 수집·보관·삭제 보류, 현금영수증/세금 및 채권·수익 인식). `data_retention_privacy`는 이 구조를 Capital 데이터 분류와 함께 채택하고 숫자는 주인에게 남긴다.
- **규모(RS)와 계정표 설계.** `docs/decisions/TOKEN_LAYER_AND_RIGHTS_SCALE_SCOPE_20260929.md`, `docs/decisions/RIGHTS_SCALE_RS0_DECISION_20261008.md`(독립 객체 분할, 페이지 단위 위임), `docs/blueprints/rights-scale-v1/README.md` §1.2(여섯 상한)·§7(1,024 → 16,384 → 65,536), `docs/contracts/RIGHTS_SCALE_PROFILE.md` RR-4("공개 트리의 보존 기간은 UNDETERMINED"). V1처럼 계정 코드에 식별자를 넣으면 65,536석 공연에서 계정표가 폭발한다. COA-V1은 **계정 코드와 서브원장 키(차원)를 분리**해 RS-4 L3 규모를 전제한다.
- **토큰 계층(TL)과 회계·세무 쟁점.** `docs/blueprints/optional-native-token-v1/README.md` §3.1(여섯 자산 분리)·§7.1(자금 풀: 고객 예치금·주최자 정산금·환불 준비금은 토큰 지지에 금지)·§10.2(검토 쟁점 5 회계 처리, 6 세무, 7 개인정보·AML·KYC)·TL-L, `docs/adr/0002-token-layer-scope-and-limits.md`(선행 결정이 인용). 준비금 재원 계정 3100을 프로토콜 수익 풀로 한정하고, 미래 토큰 담보는 신용가치 0의 메모(9500)로만 둔다.
- **AI 위임 경계.** `docs/contracts/AI_DELEGATION_AUTHORITY.md` §9("법적·세무·회계·제공자 답이 필요한 값도 비워 둔다"), `DEVELOPMENT_PLAN.md` §14, `docs/PROTOCOL_MASTERPLAN_V2.md`(역사) 190행("기록 자체에 개인정보가 과다 축적되지 않도록 보관 범위를 정한다")·T08(개인정보 최소화). AI 제안은 분개가 아니라 분개 메타데이터(`proposal_id`)일 뿐이며, 보존·개인정보 정책은 그 기록에도 적용된다.
- **1차 발행 수수료 VAT는 upstream 미정.** `docs/contracts/MOVE_PRIMARY_ISSUANCE_PRICE_FEE.md` §6("수수료의 법률·세무·회계 처리. 수수료에 대한 부가가치세… `UNDETERMINED — 사용자와 법률·회계 담당`"). 그래서 Capital은 플랫폼 수수료 VAT를 **자기 범위 밖**으로 선언하고 경계만 적는다.
- **"포부"의 해석.** `PROGRAM_ROADMAP_20260930.md` §0("한 번 시작하면 사람의 결정이 꼭 필요한 곳 말고는 멈추지 않는다")과 JunTae의 2026-10-08 위임. 그래서 다섯 항목 모두 **값을 정했다**. 다만 법률·세무·회계 결론은 전문가의 몫이므로 모든 항목에 검토자와 검토 항목을 붙였고, 사용자 병합으로 이미 "멈춘 채로 둔다"고 정해진 보존 기간 숫자만 빈 자리로 남겼다.

## 3. 항목별 결정

각 항목은 값, 근거, 검토한 대안, 게이트와 소비 seam 순이다. 공통 제약: 고정 FSM(`CreditMachine`, `SettlementMachine`)은 바꾸지 않고, FSM이 거짓으로 강제하는 플래그(`interest_defined`, `license_granted`, `regulated_product`, `legal_debtor_bound`, `collateral_perfected`, `funds_executed`, `durable` 등)는 어떤 계정·정책도 참으로 바꾸지 않는다. 모든 회계적 의미는 `CAPITAL-TERMS-V1`과 같은 방식으로 **오버레이와 투영 후보**에 산다.

### 3.1 chart_of_accounts_mapping (CAP-13, CAP-14, CAP-15)

- **값.** `CAPITAL-COA-V1`. (1) **자산별 원장**: 자산은 upstream `AssetSpec(namespace, reference, decimals, max_atoms)`로 식별하고(KRW = `{fiat, KRW, 0}`), 자산을 넘는 합산·상계는 `ASSET_MISMATCH`로 거절한다. (2) **코드 체계**: 4자리 분류 코드 + 고정 차원. 식별자(`advance_id`, `claim_id`, producer tuple이 주는 show/page/slot)는 차원이지 계정 코드가 아니다. (3) **분개 차원**: `asset`, `advance_id`, `claim_id`, `beneficiary_role`, `tier`, `terms_version`, `chart_version`, `source_cut`, `sim_day`, `operation_id`, 선택 `proposal_id`(AI lane). 이는 `CAPITAL_UPSTREAM_BINDING.md` §3.3이 적은 `fin-ledger-contract` `ProjectionEntry` 목표(원 사건 identity, 자산/registry version, source cut, watermark, 자산별 debit=credit, reversal 연결)와 같은 모양이다.

| 코드 | 이름 | 분류(작업 가정) | 정상 잔액 | 원천 / 시뮬레이션 비고 |
|---|---|---|---|---|
| 1000 | CASH_AND_FUNDING_PLATFORM_TREASURY | 자산 | 차변 | 시뮬레이션에서는 **대응 메모**. 현금은 움직이지 않고 `funds_executed=false` |
| 1100 | ADVANCES_RECEIVABLE_PRINCIPAL | 자산 | 차변 | 서브원장 `advance_id`. 잔액 = FSM `outstanding_exposure` 합 |
| 1110 | ACCRUED_INTEREST_RECEIVABLE | 자산 | 차변 | 차원 `interest_kind ∈ {CONTRACT, DEFAULT}`. 원천: 오버레이 이자 메모 원장(`CAPITAL-TERMS-V1`) |
| 1190 | ALLOWANCE_FOR_EXPECTED_CREDIT_LOSSES | 차감 자산 | 대변 | `CAPITAL-TERMS-V1 reserve.provision_bps_of_outstanding` → `SIM_LOSS_PROVISION` 후보의 자리 |
| 1300 | WITHHOLDING_TAX_RECEIVABLE_ON_INTEREST | 자산 | 차변 | 시뮬레이션 0. 요율은 주인이 공급(§3.3) |
| 2300 | VAT_PAYABLE_ON_TAXABLE_FEES | 부채 | 대변 | `ZERO_FEE_INTEREST_ONLY`라 0. 자리만 |
| 3100 | PROTOCOL_REVENUE_POOL_RETAINED | 자본 | 대변 | 3200의 **유일한 허용 재원**(TK-4, `reserve.funding_source`) |
| 3200 | APPROPRIATED_RESERVE_FOR_CREDIT_LOSSES | 자본 적립(작업 가정) | 대변 | `SIM_RESERVE_POOL` 후보의 자리. 자본 적립 vs 부채성 충당은 검토 항목 |
| 4100 | INTEREST_INCOME_ADVANCES | 수익 | 대변 | 약정 이자 |
| 4110 | DEFAULT_INTEREST_INCOME | 수익 | 대변 | 만기 다음 날부터 `DEFAULTED` 전까지 |
| 4200 | FEE_INCOME_CAPITAL | 수익 | 대변 | `CAPITAL-FEES-V1`으로 0. 자리만 |
| 4300 | RECOVERIES_OF_WRITTEN_OFF_ADVANCES | 수익 | 대변 | 상각 뒤 회수(현금주의) |
| 5100 | CREDIT_LOSS_EXPENSE | 비용 | 차변 | 충당 설정 |
| 5200 | WRITE_OFF_LOSS_BEYOND_ALLOWANCE | 비용 | 차변 | 충당 초과 상각액 |
| 9100 | MEMO_SETTLEMENT_CLAIM_FACE_OBSERVED | 메모(부외) | 차변 | ← `SIM_CLAIM_FACE`. 정산 청구는 **Capital 자산이 아님** |
| 9110 | MEMO_PAYEE_OBLIGATION_FACE | 메모(부외) | 대변 | ← `SIM_PAYEE_OBLIGATION` |
| 9150 | MEMO_BENEFICIARY_REPAYMENT_OBLIGATION | 메모(부외) | 대변 | ← `SIM_ADVANCE_OBLIGATION` 잔액(= outstanding) |
| 9160 | MEMO_REPAYMENTS_RECEIVED_CUMULATIVE | 메모(부외) | 대변 | ← `SIM_REPAY_MEMO` |
| 9200 | MEMO_OPEN_FACE_RESERVED | 메모(부외) | 대변 | ← FSM `reserved_open` |
| 9300 | MEMO_REFUND_OBLIGATION_EXPOSURE | 메모(부외) | 대변 | ← 정산 조회 `refund_face`/`refund_outstanding` |
| 9400 | MEMO_RECOVERY_DUE_ON_FACE | 메모(부외) | 차변 | ← 정산 조회 `recovery_due`(한도·재원 아님) |
| 9500 | MEMO_SUPPLEMENTARY_TOKEN_COLLATERAL_ZERO_CREDIT_VALUE | 메모(부외) | 차변 | 미래 TL 자산. haircut 100 %(TK-12). V1 사용 없음 |
| 9700 | MEMO_SUSPENDED_INTEREST_AFTER_DEFAULT | 메모(부외) | 차변 | `DEFAULTED` 뒤 계산되나 인식 유예된 이자(§3.2) |

V1 분개와 COA-V1 분개의 대응(`a` = 제안 금액, `p` = 원금 상환액, `g` = 청구 총액, `f_i` = 수취인 액면):

| V1 분개 (`SIMULATION_FIXED_V1`) | COA-V1 분개 | 의미 |
|---|---|---|
| EVIDENCE: Dr `SIM_CLAIM_FACE` g / Cr `SIM_PAYEE_OBLIGATION` f_i | 메모: Dr 9100 g / Cr 9110 f_i | 정산 청구 액면 관측. 부외. Capital 자산 아님 |
| draw: Dr `SIM_ADVANCE_EXPOSURE` a / Cr `SIM_ADVANCE_OBLIGATION` a | Dr 1100 a / Cr 1000 a | 선지급 원금 인식. 시뮬레이션의 1000은 대응 메모(현금 없음) |
| repay: Dr `SIM_ADVANCE_OBLIGATION` p / Cr `SIM_REPAY_MEMO` p | Dr 1000 p / Cr 1100 p | 원금 상환. FSM `repay`는 원금 몫만 받는다(`CAPITAL-TERMS-V1`) |
| (V1 없음) | 이자 발생: Dr 1110 / Cr 4100; 연체이자: Dr 1110(DEFAULT) / Cr 4110 — `DEFAULTED` 뒤에는 9700 메모 | 오버레이 `sim_day` 틱. 소유 `terms-overlay` |
| (V1 없음) | 현금 R 수령: Dr 1000 R (+ Dr 1300 w, 원천징수 시) / Cr 1110 이자 몫 / Cr 1100 원금 몫 | 배분 순서 연체이자 → 이자 → 원금 |
| (V1 없음) | 충당: Dr 5100 / Cr 1190; 적립: Dr 3100 / Cr 3200; 종결 시 둘 다 환입 | `reserve` 등급 가중 bps |
| (V1 없음) | 상각(부도 + 90 `sim_day`): Dr 1190(충당 한도) + Dr 5200(초과) / Cr 1100; 미수 이자 환입 Dr 4100·4110 / Cr 1110; 이후 회수 Dr 1000 / Cr 4300 | FSM 노트는 `NOTED`로 남고 천장을 계속 잡음 |

계정 단위 매핑: `SIM_CLAIM_FACE → 9100`, `SIM_PAYEE_OBLIGATION → 9110`, `SIM_ADVANCE_EXPOSURE → 1100 차변(총 인출)`, `SIM_ADVANCE_OBLIGATION → 1000 움직임(인출 때 대변, 상환 때 차변; 잔액은 9150과 같음)`, `SIM_REPAY_MEMO → 1100 대변(누적 상환; 9160과 같음)`. 불변식: 자산별 매 분개 debit = credit; 9100 = Σ9110(청구별); 1100 잔액 = Σ FSM `outstanding_exposure` = 9150; 9160 = Σ `repaid_exposure`; 9200 = 청구별 `reserved_open`; 어떤 분개도 FSM 항상-거짓 플래그를 참으로 만들지 않음; 어떤 계정에도 사람·계좌·법적 당사자 의미를 부여하지 않음(`FINANCE_COMPLETION_DESIGN_KO.md` §3).

- **근거.** V1의 다섯 계정은 보존 술어 검증용 **합성 role**이고 upstream이 "회계 계정과목의 의미를 갖지 않는다"고 적었으므로, 그대로 운영 계정표로 승격할 수 없다. 반면 `CAPITAL-TERMS-V1`은 이미 이자·충당·준비금·상각을 정했고 그 수치가 들어갈 계정 자리가 없다. COA-V1은 그 자리(1110·1190·3100·3200·4100·4110·4300·5100·5200)를 만들고, 정산 청구를 메모로 묶어 모델 1·F04 §0("외부에서 이미 양도·담보된 채권이 이 기록으로 사라졌다고 하지 않는다")을 지킨다. 분류 열은 한국 대주 법인의 K-IFRS 식 표시를 **작업 가정**으로 둔 것이며 회계사가 다시 배치할 수 있다.
- **대안.** (a) V1 kind를 운영 계정으로 채택: 합성 role이라 기각. (b) 식별자를 계정 코드에 넣는 V1 방식 유지: RS-4 L3(65,536석)에서 계정표 폭발, 기각. (c) 정산 청구 액면을 Capital 채권으로 인식: 모델 1·F04 §0 위반, 기각. (d) 계정표를 UNDETERMINED로 둠: 위임 범위이고 `terms-overlay`가 당장 자리를 필요로 하므로 기각.
- **게이트와 소비 seam.** `ProjectionPort`: `SimulationProjection`(V1)은 **불변**이며 기본·유일 모드로 남는다. COA-V1은 `terms-overlay`와 후속 `projection-coa-candidate` 노드가 **추가형** 구현(`SIMULATION_FIXED_V2` 또는 `CAPITAL_COA_V1_CANDIDATE`)으로 넣되, 라벨은 여전히 `SYNTHETIC_UNADOPTED`·`tax=NOT_BOUND`·`legal=NOT_BOUND`·`operating_ledger=NOT_BOUND`다(`capital/contract/facade-v1.json`은 그 세 값을 `const`로 잠근다). 새 mode 이름은 그 노드의 결정이며 `service.projection`은 지금 `None`·`simulation` 외를 `NOT_BOUND`로 거절한다. `reconciliation`: 기존 `projection_totals_vs_case_views`는 V1 접두사(`SIM_ADVANCE_EXPOSURE:` 등)에 묶여 있으므로 그대로 두고, 후보용 `coa_candidate_totals_vs_v1`(1100 잔액 = V1 `SIM_ADVANCE_OBLIGATION` 잔액 합, 9100 = V1 `SIM_CLAIM_FACE` 합)을 새로 둔다. `export manifest`: `projection` 섹션이 `chart` 문자열을 이미 담으므로 후보 chart 표기는 필드 추가 없이 가능하다. upstream: `fin-ledger-contract`(사용자 병합) 입력 벡터 후보.

**SIMULATION 차트가 출시 로컬 제품에 남는가 — 남는다.** 조건:

| 조건 | 근거 |
|---|---|
| `SIMULATION_FIXED_V1`이 기본·유일 `ProjectionPort` 출력. 계정 다섯 종·kind `SYNTHETIC_*`·라벨·보존 술어 다섯 개 불변 | `capital/projection.py`, `tests/test_projection.py`(`chart == SIMULATION_FIXED_V1`, 세 라벨 고정), `capital/static/app.js` 41행 guard |
| `tests/golden/demo.json`의 `state_digest`·`content_digest`·debit = credit = 385,000 불변. 이 매핑은 숫자를 한 원도 바꾸지 않음 | `scripts/seed_demo.py`, `docs/VALIDATION.md` Acceptance ladder |
| COA-V1은 문서 수준 매핑 + 추가형 후보. 후보도 `SYNTHETIC_UNADOPTED`이고 `fin-ledger-contract` 채택 전까지 `policy_adopted=false` | `docs/SEAMS.md` ProjectionPort 행 `NOT_BOUND`, `tests/test_seams.py` |
| V1 숫자·fixture(총액 100,000, 수수료 500 bps, 3 fixture)에서 어떤 회계·세무 입장도 추론하지 않음. 385,000은 보존 검사 합계이지 재무상태표가 아님 | `FINANCE_COMPLETION_DESIGN_KO.md` §3, 이 노트 머리말 |
| `/api/projection`의 `tax`·`legal`·`operating_ledger`는 adapter와 전문가 검토 전까지 `NOT_BOUND` | `facade-v1.json` const |

### 3.2 revenue_recognition_basis (CAP-13, CAP-14)

- **값.** `CAPITAL-REVREC-V1`. **Capital의 수익 흐름**은 약정 이자(4100), 연체이자(4110), 상각 후 회수(4300), 수수료(4200, `CAPITAL-FEES-V1`로 0) 넷뿐이다. **Capital 수익이 아닌 것**: 정산 청구 총액과 수취인 의무 액면(F01–F03, 주최자·플랫폼 정산), 플랫폼 정산 수수료(fixture `fee_payee = platform`은 KIX 정산 사업의 수익이지 Capital의 수익이 아니다), `primary_sales`·`resale_sales`(`statement.py`: NOT_BOUND, `NOT_SUMMED`), 명세서의 PG `fee`·`tax`·`held`·`adjustment` 성분, `confirmed_cash`·`recovery_due`(한도·재원·수익 어느 것도 아님). **인식 기준**: 발생주의·시간비례. 원금 잔액에 대한 단리 ACT/365(`CAPITAL-TERMS-V1`), 수수료가 0이므로 유효이자율 = 약정이자율(작업 가정). **인식 사건**: 시작 = 인출 수락 영수증(`draw_day` 포함); 틱 = 매 오버레이 `sim_day`; 게시 = `repay`·`close`·`default`·상각·매 export cut; 종료 = 종결 수락 영수증(상환일 제외); **유예** = `default` 수락 영수증부터 약정·연체 이자는 채권으로 계산되되 9700 메모에 두고 현금 수령 시에만 4110·4300으로 인식; 상각(부도 + 90 `sim_day`) 시 미수 이자 환입; 상각 뒤 회수는 현금주의로 4300, 케이스는 되살리지 않음. **측정**: KRW 정수, 정확한 유리수 누적, 게시 시 1원 내림·나머지 이월(`CAPITAL-TERMS-V1`). 상환 배분 순서 연체이자 → 이자 → 원금. **cut 의미**: 수익은 명명된 cut(`state_digest` + `sim_day`)에 대해서만 보고하고 cut이 다른 보고서를 하나의 닫힌 잔액으로 합치지 않는다. **시뮬레이션 상태**: V1 투영은 수익을 인식하지 않는다(이자는 오버레이에 살고 오버레이는 미구현). 다섯 구분 명세서에 수익 구분은 없고 `tax_reporting=NOT_BOUND`다. **절대 금지**: 청구 액면·확인 현금·배정 현금을 Capital 수익으로 인식, fixture 500 bps 수수료에서 이자 인식, 이자 평탄화·선인식, UNKNOWN·REJECTED 영수증에 대한 수익 인식.
- **근거.** `CAPITAL-TERMS-V1`이 이미 누적 방식·배분 순서·상각 시점을 정했으므로 인식 기준은 그 계산의 **인식 시점 규칙**만 더하면 된다. 부도 뒤 유예는 신용손상 자산의 이자 인식을 보수적으로 두려는 작업 가정이며(K-IFRS 1109의 순장부금액 기준 이자와의 정합은 검토 항목), 터무니없는 미수 이자 적체를 막는다. 플랫폼 정산 수수료를 Capital 수익에서 제외하는 것은 `BLUEPRINT_20260914.md` §3의 "별도 자금 흐름"과 `FINANCE_COMPLETION_DESIGN_KO.md` §2의 작성자 경계를 따른 것이다.
- **대안.** 현금주의: 발생주의 계산(`CAPITAL-TERMS-V1`)과 어긋나고 K-IFRS 작업 가정과 맞지 않아 기각. 플랫폼 정산 수수료를 Capital 수익으로: 사업 경계 위반, 기각. 선취 수수료 인식: 수수료 0이라 무의미. `DEFAULTED` 뒤에도 손익에 계속 발생: 미수 이자 과대, 기각.
- **게이트와 소비 seam.** `ProjectionPort` V2 후보: 1110/4100/4110/4300 분개는 `terms-overlay` 이자 원장에서 나온다. `reconciliation`: 이자 원장 합계 ↔ 후보 투영 1110·4100 합계 검사(새 검사). `statement`: 수익 구분을 **추가하지 않는다**(CAP-09 다섯 구분과 `primary_and_resale = NOT_SUMMED` 유지). `export manifest`: statement/projection 섹션. upstream: `fin-ledger-contract`·`fin-credit-exposure-reconciliation` 입력 후보.

### 3.3 tax_reporting_treatment (CAP-13, CAP-15)

- **값.** `CAPITAL-TAX-V1`, 관할 KR, 주체 가정 = Capital 대여 장부를 운영하는 내국법인(§3.4). **부가가치세**: 이자소득(4100·4110·4300)은 **면세 금융용역**(작업 가정; 세금계산서 없음; 면세 공급 보고 의무는 검토 항목), Capital 수수료(4200)는 발생하면 과세 10 %와 세금계산서(작업 가정), 플랫폼 정산 수수료의 VAT는 upstream 미정(`MOVE_PRIMARY_ISSUANCE_PRICE_FEE.md` §6, `settlement-policy-deepening`)이며 Capital 범위 밖, 면세·과세 겸영 시 공통매입세액 안분은 검토 항목. **수취 이자 원천징수**: 매개변수 `withholding_rate_bps`(주인 공급), 시뮬레이션 값 0, 상태 `NOT_MODELED_V1_FIELD_RESERVED`; 설계는 총액 이자를 4100에 인식하고 수익자가 원천징수한 금액을 1300(선납법인세)으로, 현금은 순액 수령; 법인 수익자가 Capital 법인에 지급하는 이자가 원천징수 대상인지는 대주 법인의 업종 분류에 따라 달라지므로 검토 항목. **법인세**: 이자소득 과세(발생 vs 수입 시점의 세무 귀속시기는 검토), 1190 충당금은 세무상 전액 손금으로 가정하지 않고 `BTD_PROVISION` 메모로 장부·세무 차이를 보존, 5200 상각은 법정 대손 요건 충족 시에만 손금(`BTD_WRITEOFF` 메모), 3200 자본 적립은 세효과 없음(작업 가정). **정산 명세서 `tax` 성분**: `gross = amount + fee + tax + held + adjustment`의 `tax`는 청구에 대한 **제공자 측 차감 관측**이며 Capital의 세금도 Capital의 VAT도 아니다(비현금 성분으로만 기록). **증빙**: 면세 이자에 세금계산서 없음(작업 가정); 계산서·현금영수증·전자 증빙 의무는 검토 항목(TM09). **보고 산출물**: 출시 제품의 `projection.tax = NOT_BOUND`(const), `statement.tax_reporting = NOT_BOUND`, `evidence.unavailable ∋ tax_reporting`, manifest는 신고가 아님 — 모두 불변. 미래 `tax_memo` export 섹션(기간 cut, 면세 수익, 과세 수익, 원천징수 미수, BTD 메모)은 회계사 검토와 adapter 노드 뒤에만 두고 **절대 세무 신고로 라벨하지 않는다**(`FINANCE_COMPLETION_DESIGN_KO.md` §7). **국외**: 비거주자 수익자·조세조약 원천징수는 `NOT_IN_V1`. **절대 금지**: Capital 산출물을 세무 신고·GAAP/IFRS 재무제표·규제 여신 보고서로 라벨, V1 숫자·fixture에서 세무 입장 추론, FSM `repay` 명령에서 원천징수를 원금과 상계.
- **근거.** 세무는 수익 인식(§3.2)과 인허가 경로(§3.4)에 종속된다. 가장 큰 설계 영향은 **원천징수**다. 수익자가 이자에서 원천징수하면 Capital이 받는 현금은 총액 이자보다 작아지고, `CAPITAL-TERMS-V1`의 배분(연체이자 → 이자 → 원금)이 총액 기준인지 순액 기준인지가 갈린다. 그래서 요율 0의 **필드를 지금 예약**해 오버레이가 총액 인식·순액 수령·1300 선납세금 구조를 처음부터 갖게 했다. 충당금·상각의 장부·세무 차이도 메모로 분리해 `reserve`의 "tax treatment of provisions" 검토 항목에 바로 답할 수 있게 했다.
- **대안.** 세무를 전부 UNDETERMINED로 둠: 필드 예약조차 못 해 오버레이 설계가 뒤집힐 수 있어 기각. 이자를 과세 용역으로 가정: 금융용역 면세 작업 가정과 어긋나 기각(검토 결과가 다르면 4100의 VAT 처리를 다시 연다). 원천징수를 모델링하지 않음: 실자금 전환 시 상환 산술이 깨지므로 기각(필드만 두고 값은 0).
- **게이트와 소비 seam.** `ProjectionPort` V2 후보(1300·2300·BTD 메모 계정). `export manifest` 미래 `tax_memo` 섹션(회계사 검토 뒤). `statement`는 `tax_reporting: NOT_BOUND` 유지. 따라서 **adapter와 전문가 검토 전까지 로컬 소비자는 없다**. upstream: `settlement-policy-deepening`(명세서 `tax` 경계), `f04-real-funds-lift-criteria`·`tl-legal-brief`(검토 질문), TM09.

### 3.4 lending_or_claim_trading_licence (CAP-13, CAP-15; 관련 CAP-01·CAP-03·CAP-19)

- **값.** `CAPITAL-LICENCE-ROUTE-V1`. **V1 상품**: 주최자 **법인**을 수익자로 하는 포착 정산채권 선지급(F04). 소비자 대출 없음, 예금·예치 없음, 투자자 참여 없음. **1차 경로(설계 목표)**: `DEDICATED_KIX_CAPITAL_LENDING_ENTITY_REGISTERED_AS_MONEY_LENDER` — KIX Capital 전담 대주 법인을 대부업법에 따라 등록한다(등록 관할과 온라인 대부 분류는 규모·영업 방식에 따라 다르므로 법무 확인). `CAPITAL-TERMS-V1`의 총비용 상한 2,000 bps/yr 작업 가정은 이 경로와 짝이다. **대안 경로**: `LICENSED_PARTNER_LENDER_WITH_KIX_CAPITAL_AS_PLATFORM_AND_SERVICER` — 면허 금융기관이 대주가 되고 KIX Capital은 플랫폼·서비서(이 경우 금융소비자보호법상 대출성 상품 판매대리·중개 등록 질문과 파트너·PG의 계약상 제한이 생긴다, 토스 프로파일 미확인 항목과 연결). **CAP-03 채권매입·거래**: V1 `NOT_OFFERED`. 목표는 대주 법인이 **상환청구권 있는 매입**만 하고 이를 같은 등록 아래의 대부로 취급(작업 가정). 상환청구권 없는 진정매매, 제3자 투자자 claim slice, 트랜치는 자본시장법 증권성·온라인투자연계금융업·신용정보법 채권추심업 검토 **뒤에만** 설계한다(`tranching_v1 = NONE`, `CAPITAL-TERMS-V1`). **양수 채권 추심**: 완전성 C2 이상의 2차 집행은 채권추심업 허가 요건 확인이 선행(`collateral_execution` 검토 항목). **KYC/AML**: 의무 주체는 대주 법인(작업 가정), Capital은 attested fact만 소비(`identity_provider_kyc` NOT_ADOPTED), 벤더 UNDETERMINED. **소비자 보호**: V1 수익자는 사업자; 개인이 수익자가 되면 금융소비자보호법·신용정보법 검토, `NOT_IN_V1`. **FSM 플래그**: `license_granted`, `regulated_product`, `legal_debtor_bound`, `collateral_perfected`, `priority_bound`, `funds_executed` 거짓 유지. **게이트**: 실자금·실여신·실 KYC는 `PROGRAM_DECISIONS_20260928.md` §5 잠금 그대로, 해제 결정은 사용자 노드 `f04-real-funds-lift-criteria`이며 이 경로는 **Capital의 설계 가정과 그 노드의 입력 후보**다. **법적 적용 판단**: `PENDING_PROFESSIONAL_REVIEW`. E06 라벨은 upstream 설계중 그대로.
- **근거.** 선지급은 이자를 받는 신용 공여이므로 "플랫폼 선정산"이라는 이름만으로 규제 밖이라고 가정하지 않는다(작업 가정). 대주 법인 직접 등록 경로를 1차로 둔 이유는 (1) `CAPITAL-TERMS-V1`의 증거 등급 가격·2인 원칙·회수 폭포를 **Capital이 통제**해야 티켓 권리 경제의 포부(정산 증거로 신용을 가격하는 것)가 실현되고, (2) 20 % 상한 작업 가정이 그 경로의 법령과 맞으며, (3) 파트너 경로는 상품 조건 통제력을 잃고 별도 중개 등록 질문이 생기기 때문이다. 채권매입을 V1에서 빼고 투자자 slice를 검토 뒤로 둔 것은 손실 부담 100 % 플랫폼·트랜치 없음(`CAPITAL-TERMS-V1`)과 일치한다. `cr-01-product-authority`(pending)가 "대주·차주·정책·증거 권위를 먼저 확정"하라고 적으므로 이 경로는 그 노드와 `f04-real-funds-lift-criteria`의 입력이다.
- **대안.** 미등록 "플랫폼 선지급" 운영: 작업 가정상 신용 공여라 기각. 온투업(P2P) 경로 V1: 투자자가 없고 트랜치 없음, 기각. 비소구 채권매입 마켓플레이스 V1: 증권성·추심 쟁점 미해결, 기각. 경로 자체를 UNDETERMINED로 둠: 위임이 설계 결정을 요구하고 법적 판단은 어차피 법무 몫으로 분리할 수 있어 기각(그 분리를 `applicability_determination`으로 명시).
- **게이트와 소비 seam.** **no local consumer.** 인허가를 읽는 seam은 없다. `readiness.py` release 그룹 차단 사유("실여신/PG/은행/KYC·면허/법무와 운영 책임")와 `CAPITAL_REQUIREMENTS_KO.md` CAP-03 행이 이 노트를 인용하도록 sync 노드가 문구만 바꾼다(상태값 불변). FSM 플래그는 그대로다. upstream: `f04-real-funds-lift-criteria`(사용자), `tl-legal-brief`, `cr-01-product-authority`(pending) 입력 후보.

### 3.5 data_retention_privacy (CAP-14, CAP-15; 관련 CAP-10·CAP-19)

- **값.** `CAPITAL-RETENTION-PRIVACY-V1`. **개인정보 자세**: `NO_PERSONAL_DATA_BY_DESIGN_V1` — 역할 라벨(`fixture-organizer`, `beneficiary_role`, `debtor_role`, `fixture-buyer`)은 사람이 아니고, 계정·비밀번호·실명·계좌·신용정보가 없으며, 자유 문자열 필드(`adjustment_reason`, reason 식별자)에 개인정보를 넣지 않는다는 규칙을 둔다. **데이터 분류**: `journal`(수락 F04 명령: id·금액·fixture id, PII 없음, 메모리 또는 `LOCAL_FILE_WORKSPACE`), `receipts`(operation_id·instance_id·outcome·역할 라벨·결과/오류, PII 없음), `case_fixtures`, `derived_views`(투영·대사·명세서·시나리오·사전점검: 저장하지 않고 요청마다 재계산), `export_manifests`(journal·receipts 본문을 담으므로 **본문이 PII-free여야** 호스트 밖으로 나갈 수 있음; 정체는 `content_digest`), `dev_hmac_key`(DEV_ONLY, mode 0600, 응답·로그에 없음), `test_and_ci_artifacts`(golden digest, 스크린샷은 커밋 안 함). **보존 칸 다섯**: `legal_dispute_hold`(주인 법무/개인정보, JunTae 지명), `business_reconciliation`(주인 토스 계약/기술), `retry_support`(주인 Astra), `memory_residency{count, bytes, age}`(주인 Astra; `MAX_OPERATIONS 500`은 데모 용량 상한이지 값이 아님), **`tax_accounting_records`**(Capital이 더한 다섯째 칸, 주인 = JunTae가 지명하는 회계·세무 담당; upstream 질문서에 없던 칸). **기간 숫자는 모두 `NOT_SET_OWNER_SUPPLIED` / `NOT_SET_DECISION_REQUIRED`** — upstream R1(#139, 사용자 병합)이 값을 멈춘 채로 두고 제공자 공개값(15일 멱등키 등)을 기간으로 쓰지 말라고 정했고, 법무 회신(L10-R·L10-H·U10-C)이 없기 때문이다. **시뮬레이션 보존**: `RETAIN_ALL_NO_AUTOMATIC_DELETION` — journal·receipts는 append-only, 용량 상한은 `SIMULATION_CAPACITY` 거절이지 축출이 아니며, 작업공간 파일 삭제는 운영자 행위고, 재시작 프로세스는 새 `instance_id`로 원 receipt를 그대로 제공한다. **규칙**: 열린 법정·분쟁 보류는 다른 칸과 무관하게 삭제를 막는다; 캐시 축출은 권위 기록 폐기가 아니다; 없는 receipt는 `UNKNOWN_UNRESOLVED`이며 미실행 증거가 아니다; 체인에 앵커된 사실은 지울 수 없으므로 Capital은 앵커되거나 공유 manifest에 해시될 수 있는 자료에 개인정보를 절대 쓰지 않는다; 미래 개인정보의 삭제 요청은 IdP/KYC 제공자에서 처리하고 Capital은 가명 참조만 보유한다(`identity_provider_kyc`); fixture·테스트·golden·질문서·Git·채팅에 개인정보 없음. **접근**: 역할 매트릭스 유지(observer는 export·projection·statement·reconciliation 읽기 불가, auditor는 읽기만, organizer 쓰기, agent lane은 이들 읽기 없음). **키 자료**: dev HMAC 키는 무결성 전용·DEV_ONLY, 작업공간과 함께 삭제, 자격증명도 법정 기록도 아님. **출시 제품 규칙**: manifest `retention_policy = NOT_BOUND`(const)는 `retention-slots-sync`가 이름 있는 빈 칸으로 바꿀 때까지 유지하고, 코드는 어떤 기간도 기본값으로 채우지 않는다.
- **근거.** `CAPITAL_UPSTREAM_BINDING.md` §3.11이 네 칸 구조를 Capital에 받아들였고 세무·회계 담당 부재를 적었다. 이 항목은 그 위에 **무엇을 보존하는지(분류)**, **개인정보가 없다는 설계 사실과 유지 규칙**, **다섯째 칸**을 더한다. 숫자를 지금 적는 것은 사용자 병합 결정(#139 R1)과 선행 Capital 결정에 어긋나고 법적 결론을 가장하는 일이므로 하지 않는다. 체인 비가역성과 manifest 공유 가능성 때문에 "앵커 자료에 PII 금지"가 Capital이 지금 지킬 수 있는 가장 강한 개인정보 규칙이다.
- **대안.** 단일 보존 기간: upstream R2 갈래, 기각. 법정 기간을 지금 숫자로 채움: 법무 회신 전 금지(R1), 기각. 세무·회계 칸을 두지 않음: 회계사가 답할 자리가 없어 기각(빈 칸만 추가). 개인정보 자세를 UNDETERMINED로 둠: Capital에 개인정보가 **없다는 것은 코드 사실**이라 결정할 수 있어 기각.
- **게이트와 소비 seam.** `export manifest`: `retention_policy` 자리(`retention-slots-sync`가 다섯 칸 구조와 주인으로 교체; `data_classes`는 manifest `note`에 요약 가능). `reconciliation`: `unknown_policy.retry_authorized=false` 불변. `readiness`: release 그룹 "보존·복구·개인정보" 차단 사유가 이 노트를 인용. 값 적용은 `k-stage5-durable-tx` 저장이 생기고 주인이 답한 뒤에만.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "accounts-tax-legal-decision",
  "decided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
  "date": "2026-10-09",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "scope": "KIX-CAPITAL simulation and product design only; not an offer; no real money; production NOT_AUTHORIZED; every entry is a working assumption pending review by professionals designated by JunTae; nothing here is legal, tax or accounting advice; no accounting or tax position is inferred from the synthetic projection; no upstream contract is claimed adopted",
  "delegation": "2026-10-08 18:25 KST JunTae Park delegated financial terms, settlement policy, upstream binding and accounts/tax/legal to Fable with the instruction to proceed with the grand ambition in mind",
  "basis_default": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
  "bases": {
    "capital_main": "361a55c",
    "kix_protocol_main": "51d83808478e56c81c6f43e2a13450d435e922e6",
    "vendor_pin_commit": "7481b0e16ce9b903abbffa62249bb91cd9e63cfe",
    "vendor_sha256": {
      "credit_advance_f04/credit_fsm.py": "f4f6b3698dd848538d2efa10b276cb33659eb4877fcbea0feb7429b28456491b",
      "credit_advance_f04/mock_credit.py": "5e75fcc76fb0857f671b2fa33ca0fc851e9d676d4b5db8f357393367bc725d95",
      "credit_advance_f04/test_mock_credit.py": "75cd55f773e3e71553392f674d1595af66cf82560565cc5603bf829a9a29e99d",
      "settlement_f01_f03/mock_settlement.py": "9e9c25571fdbe7b90b7539df2cc71afaee83d81905293dc56dbeb9faaf864170",
      "settlement_f01_f03/settlement_fsm.py": "c6d7ae79fe0c3289def2d3c195212247d1ab2c2e913feb80612fcd9ff64c77c8"
    },
    "prior_capital_decisions": [
      "docs/decisions/CAPITAL_FINANCIAL_TERMS.md (CAPITAL-TERMS-V1, 2026-10-08): interest, fees, term, default/loss, underwriting, collateral, margin, execution, reserve",
      "docs/decisions/CAPITAL_UPSTREAM_BINDING.md (2026-10-09): ProjectionPort target fin-ledger-contract ProjectionEntry; KRW AssetSpec; identity_provider_kyc NOT_ADOPTED; four retention slots with owners and no values"
    ],
    "finance_projection_input": "capital/projection.py SimulationProjection CHART_VERSION SIMULATION_FIXED_V1 with five synthetic accounts and five conservation predicates; tests/golden/demo.json pins debit=credit=385000, accounting_policy SYNTHETIC_UNADOPTED, content_digest c06f05d3417973287f5c698e4328df710125a3a367e79fe09952e8f464377502",
    "upstream_status_unchanged": "kix-protocol docs/aiops/FINANCE_COMPLETION_DESIGN_KO.md section 3 keeps chart of accounts, revenue recognition, provisions, tax and retention UNDETERMINED upstream; CREDIT_ADVANCE_F04 section 5 and ORIGINAL_32 E06 stay as written; this note supplies Capital-local provisional values and input candidates only",
    "upstream_receipts_cited": {
      "retention_structure": {"repo": "SUNBURN-Golden/kix-protocol", "pr": 139, "merge_commit": "6e54e723d582e88ae89df309eb144d4664c7e1f5", "path": "docs/decisions/RETENTION_PERIODS_PROPOSAL_20261009.md", "adopts": "R1 four separate retention slots with owners; values stay stopped"}
    }
  },
  "simulation_chart_in_shipped_product": {
    "decision": "REMAINS",
    "chart": "SIMULATION_FIXED_V1",
    "conditions": [
      "SimulationProjection stays the default and only ProjectionPort output; mode None or simulation only; any other mode stays NOT_BOUND",
      "the five SYNTHETIC_* kinds, labels, numbers and the five conservation predicates are unchanged",
      "accounting_policy SYNTHETIC_UNADOPTED, tax NOT_BOUND, legal NOT_BOUND, operating_ledger NOT_BOUND stay (facade-v1.json const, tests, app.js guard)",
      "tests/golden/demo.json state_digest and content_digest are unchanged by this decision",
      "CAPITAL-COA-V1 ships only as a mapping document plus an additive SYNTHETIC_UNADOPTED candidate projection implemented by a later node; policy_adopted stays false until fin-ledger-contract is user-merged",
      "no accounting or tax position is inferred from V1 numbers or fixtures; debit=credit=385000 is a conservation check, not a balance sheet"
    ]
  },
  "entries": {
    "chart_of_accounts_mapping": {
      "status": "ADOPTED",
      "owner": "Capital Accounting Policy Owner (interim holder: Fable 5.1 under the 2026-10-08 delegation; professional reviewer: accountant designated by JunTae, not yet named)",
      "value": {
        "chart_version": "CAPITAL-COA-V1",
        "nature": "target operating chart and V1-to-COA mapping document; SIMULATION_FIXED_V1 remains the shipped projection; COA-V1 ships only as an additive SYNTHETIC_UNADOPTED candidate when a later node implements it",
        "asset_model": "one ledger per AssetSpec; KRW declared as {namespace fiat, reference KRW, decimals 0}; integer atoms; no cross-asset netting (ASSET_MISMATCH)",
        "code_scheme": "4-digit class code plus fixed subledger dimensions; identities (advance_id, claim_id, show/page/slot from the producer tuple) are dimensions and never part of the account code, so a 65,536-slot show does not expand the chart",
        "posting_dimensions": ["asset", "advance_id", "claim_id", "beneficiary_role", "tier", "terms_version", "chart_version", "source_cut", "sim_day", "operation_id", "proposal_id (optional, AI lane)"],
        "accounts": [
          {"code": "1000", "name": "CASH_AND_FUNDING_PLATFORM_TREASURY", "class": "ASSET", "normal": "debit", "simulation": "contra memo only; funds_executed stays false; no cash moves"},
          {"code": "1100", "name": "ADVANCES_RECEIVABLE_PRINCIPAL", "class": "ASSET", "normal": "debit", "subledger": "advance_id"},
          {"code": "1110", "name": "ACCRUED_INTEREST_RECEIVABLE", "class": "ASSET", "normal": "debit", "dimension": "interest_kind in {CONTRACT, DEFAULT}", "source": "terms-overlay interest memo ledger"},
          {"code": "1190", "name": "ALLOWANCE_FOR_EXPECTED_CREDIT_LOSSES", "class": "CONTRA_ASSET", "normal": "credit", "source": "CAPITAL-TERMS-V1 reserve.provision_bps_of_outstanding (SIM_LOSS_PROVISION candidate)"},
          {"code": "1300", "name": "WITHHOLDING_TAX_RECEIVABLE_ON_INTEREST", "class": "ASSET", "normal": "debit", "simulation": "0; withholding_rate_bps owner-supplied"},
          {"code": "2300", "name": "VAT_PAYABLE_ON_TAXABLE_FEES", "class": "LIABILITY", "normal": "credit", "simulation": "0 under ZERO_FEE_INTEREST_ONLY"},
          {"code": "3100", "name": "PROTOCOL_REVENUE_POOL_RETAINED", "class": "EQUITY", "normal": "credit", "note": "only permitted funding source of 3200 (token blueprint TK-4; CAPITAL-TERMS-V1 reserve.funding_source)"},
          {"code": "3200", "name": "APPROPRIATED_RESERVE_FOR_CREDIT_LOSSES", "class": "EQUITY_APPROPRIATION", "normal": "credit", "source": "SIM_RESERVE_POOL candidate", "review": "equity appropriation vs liability provision"},
          {"code": "4100", "name": "INTEREST_INCOME_ADVANCES", "class": "REVENUE", "normal": "credit"},
          {"code": "4110", "name": "DEFAULT_INTEREST_INCOME", "class": "REVENUE", "normal": "credit"},
          {"code": "4200", "name": "FEE_INCOME_CAPITAL", "class": "REVENUE", "normal": "credit", "note": "0 by CAPITAL-FEES-V1; placeholder"},
          {"code": "4300", "name": "RECOVERIES_OF_WRITTEN_OFF_ADVANCES", "class": "REVENUE", "normal": "credit"},
          {"code": "5100", "name": "CREDIT_LOSS_EXPENSE", "class": "EXPENSE", "normal": "debit"},
          {"code": "5200", "name": "WRITE_OFF_LOSS_BEYOND_ALLOWANCE", "class": "EXPENSE", "normal": "debit"},
          {"code": "9100", "name": "MEMO_SETTLEMENT_CLAIM_FACE_OBSERVED", "class": "MEMO_OFF_BALANCE", "normal": "debit", "from": "SIM_CLAIM_FACE; settlement claims are never a Capital asset"},
          {"code": "9110", "name": "MEMO_PAYEE_OBLIGATION_FACE", "class": "MEMO_OFF_BALANCE", "normal": "credit", "from": "SIM_PAYEE_OBLIGATION"},
          {"code": "9150", "name": "MEMO_BENEFICIARY_REPAYMENT_OBLIGATION", "class": "MEMO_OFF_BALANCE", "normal": "credit", "from": "SIM_ADVANCE_OBLIGATION balance (equals outstanding)"},
          {"code": "9160", "name": "MEMO_REPAYMENTS_RECEIVED_CUMULATIVE", "class": "MEMO_OFF_BALANCE", "normal": "credit", "from": "SIM_REPAY_MEMO"},
          {"code": "9200", "name": "MEMO_OPEN_FACE_RESERVED", "class": "MEMO_OFF_BALANCE", "normal": "credit", "from": "FSM reserved_open"},
          {"code": "9300", "name": "MEMO_REFUND_OBLIGATION_EXPOSURE", "class": "MEMO_OFF_BALANCE", "normal": "credit", "from": "settlement view refund_face and refund_outstanding"},
          {"code": "9400", "name": "MEMO_RECOVERY_DUE_ON_FACE", "class": "MEMO_OFF_BALANCE", "normal": "debit", "from": "settlement view recovery_due; never a lending base"},
          {"code": "9500", "name": "MEMO_SUPPLEMENTARY_TOKEN_COLLATERAL_ZERO_CREDIT_VALUE", "class": "MEMO_OFF_BALANCE", "normal": "debit", "note": "future TL asset; haircut 100 percent (TK-12); unused in V1"},
          {"code": "9700", "name": "MEMO_SUSPENDED_INTEREST_AFTER_DEFAULT", "class": "MEMO_OFF_BALANCE", "normal": "debit", "note": "computed but unrecognized interest after DEFAULTED"}
        ],
        "v1_entry_mapping": [
          {"v1": "EVIDENCE: Dr SIM_CLAIM_FACE gross / Cr SIM_PAYEE_OBLIGATION face_i", "coa": "MEMO: Dr 9100 gross / Cr 9110 face_i", "meaning": "settlement claim faces are off-balance observations, never a Capital asset"},
          {"v1": "draw: Dr SIM_ADVANCE_EXPOSURE a / Cr SIM_ADVANCE_OBLIGATION a", "coa": "Dr 1100 a / Cr 1000 a", "meaning": "advance principal recognized; in simulation 1000 is a contra memo and funds_executed stays false"},
          {"v1": "repay: Dr SIM_ADVANCE_OBLIGATION p / Cr SIM_REPAY_MEMO p", "coa": "Dr 1000 p / Cr 1100 p", "meaning": "principal repayment; FSM repay carries the principal portion only"},
          {"v1": "none", "coa": "interest accrual Dr 1110 / Cr 4100; default interest Dr 1110 (DEFAULT) / Cr 4110 until DEFAULTED, then 9700 memo", "owner": "terms-overlay sim_day tick"},
          {"v1": "none", "coa": "cash R received: Dr 1000 R (+ Dr 1300 w when withheld) / Cr 1110 interest portion / Cr 1100 principal portion", "meaning": "allocation order DEFAULT_INTEREST, INTEREST, PRINCIPAL"},
          {"v1": "none", "coa": "provision Dr 5100 / Cr 1190; appropriation Dr 3100 / Cr 3200; both reversed at close"},
          {"v1": "none", "coa": "write-off at default + 90 sim days: Dr 1190 (up to allowance) + Dr 5200 (excess) / Cr 1100; unpaid accrued interest reversed Dr 4100 and 4110 / Cr 1110; later recoveries Dr 1000 / Cr 4300; FSM note stays NOTED"}
        ],
        "v1_account_mapping": {
          "SIM_CLAIM_FACE": "9100",
          "SIM_PAYEE_OBLIGATION": "9110",
          "SIM_ADVANCE_EXPOSURE": "1100 debit side (gross drawn)",
          "SIM_ADVANCE_OBLIGATION": "1000 movement (credit on draw, debit on repay); balance equals 9150",
          "SIM_REPAY_MEMO": "1100 credit side (cumulative repaid); equals 9160"
        },
        "statement_class_candidates": "ASSET, LIABILITY, EQUITY, REVENUE, EXPENSE labels are working assumptions for a K-IFRS-style presentation of a Korean lending entity; the accountant may remap; V1 kinds stay SYNTHETIC_* and never carry these classes",
        "invariants": [
          "per-asset debit equals credit on every posting",
          "9100 equals the sum of 9110 per claim",
          "1100 balance equals the sum of FSM outstanding_exposure and equals 9150",
          "9160 equals the sum of FSM repaid_exposure",
          "9200 equals FSM reserved_open per claim",
          "no posting may set any FSM always-false flag true",
          "no account carries a person, bank account or legal party meaning (FINANCE_COMPLETION_DESIGN_KO section 3)"
        ],
        "shipped_product_rule": "SIMULATION_FIXED_V1 remains the default and only projection mode; its five SYNTHETIC_* kinds, labels, numbers and the golden content_digest are unchanged by this mapping"
      },
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-09",
      "cap_rows": ["CAP-13", "CAP-14", "CAP-15"],
      "rationale": "The five V1 accounts are synthetic roles that upstream says carry no accounting-class meaning, while CAPITAL-TERMS-V1 already fixed interest, provisions, reserve and write-off that need ledger places; COA-V1 creates those places, keeps settlement claims off-balance per model 1 and F04 section 0, separates account codes from identity dimensions for RS-4 scale, and pre-shapes postings to the fin-ledger-contract ProjectionEntry target.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "review_owner": "accountant designated by JunTae (roadmap D-E); input candidate for upstream fin-ledger-contract",
      "review_items": ["statement class of each code, especially 3200 appropriation vs provision liability", "applicable framework for the lending entity (K-IFRS 1109 vs K-GAAP)", "whether settlement claims under C1 platform set-off are off-balance for Capital", "treatment of 1000 once real disbursement exists"],
      "alternatives_rejected": ["adopt SIMULATION_FIXED_V1 kinds as the operating chart", "identity-embedded account codes at RS-4 scale", "recognizing settlement claim faces as Capital receivables", "leaving the chart UNDETERMINED while terms-overlay needs ledger places"],
      "consumer": "ProjectionPort (additive SIMULATION_FIXED_V2 or CAPITAL_COA_V1_CANDIDATE implementation by terms-overlay and projection-coa-candidate; V1 untouched); reconciliation (new check coa_candidate_totals_vs_v1 beside projection_totals_vs_case_views); export manifest (projection section chart string; stage-7 landing fields unchanged)",
      "revisit_triggers": ["fin-ledger-contract user merge", "accountant review", "k-stage6-economics-reference adopted", "CAP-03 claim purchase or investor tranche introduced", "non-KRW asset admitted"]
    },
    "revenue_recognition_basis": {
      "status": "ADOPTED",
      "owner": "Capital Accounting Policy Owner (interim holder: Fable 5.1 under the 2026-10-08 delegation; professional reviewer: accountant designated by JunTae)",
      "value": {
        "policy_version": "CAPITAL-REVREC-V1",
        "capital_revenue_streams": {"4100": "contract interest on outstanding principal", "4110": "default interest from maturity + 1 while not DEFAULTED", "4200": "fees (zero by CAPITAL-FEES-V1)", "4300": "recoveries after write-off"},
        "not_capital_revenue": [
          "settlement claim gross and payee obligation faces (F01-F03; organizer and platform settlement)",
          "platform settlement fee (fee_payee platform) belongs to the KIX settlement business, not Capital",
          "primary_sales and resale_sales (NOT_BOUND, never summed, statement.py)",
          "PG fee, tax, held and adjustment components of settlement statements",
          "confirmed_cash and recovery_due (never a lending base, never revenue)"
        ],
        "basis": "ACCRUAL_TIME_PROPORTION_SIMPLE_INTEREST_ACT_365 on outstanding principal per CAPITAL-TERMS-V1; with zero fees the effective interest rate equals the contractual rate (working assumption)",
        "recognition_events": {
          "start": "accepted draw receipt; draw_day inclusive",
          "tick": "each overlay sim_day; postings at repay, close, default, write-off and every export cut",
          "stop": "accepted close receipt; repayment day exclusive",
          "suspension": "from the accepted default receipt, contract and default interest are computed as a claim but recognized only on cash receipt (9700 memo, then 4110 or 4300)",
          "writeoff": "default + 90 sim days; unpaid accrued interest reversed from 4100 and 4110",
          "recoveries": "cash basis to 4300; the case never reopens"
        },
        "measurement": "KRW integer atoms; exact rational accrual; floor to 1 KRW at posting with remainder carry (CAPITAL-TERMS-V1 rounding)",
        "repayment_allocation_for_recognition": ["DEFAULT_INTEREST", "INTEREST", "PRINCIPAL"],
        "cut_semantics": "revenue is reported only against a named cut (state_digest plus overlay sim_day); reports at different cuts are never combined into one closed balance (FINANCE_COMPLETION_DESIGN_KO section 7)",
        "simulation_status": "SIMULATION_FIXED_V1 recognizes no revenue because interest lives in the overlay and the overlay is not implemented; the five-category statement has no revenue category and keeps primary_and_resale NOT_SUMMED; tax_reporting stays NOT_BOUND",
        "never": ["recognize settlement claim face, confirmed cash or distributed cash as Capital revenue", "recognize interest from the fixture 500 bps settlement fee", "smooth or front-load interest", "recognize revenue on an UNKNOWN or REJECTED receipt"]
      },
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-09",
      "cap_rows": ["CAP-13", "CAP-14"],
      "rationale": "CAPITAL-TERMS-V1 already fixes the accrual arithmetic, allocation order and write-off timing, so recognition only needs timing rules bound to FSM receipts; suspension after DEFAULTED keeps accrued interest from inflating, and excluding the platform settlement fee keeps the separate-funds boundary of BLUEPRINT_20260914 section 3 and the writer boundary of FINANCE_COMPLETION_DESIGN_KO section 2.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "review_owner": "accountant designated by JunTae",
      "review_items": ["K-IFRS 1109 effective interest and stage-3 net-basis interest versus this suspension rule", "revenue framework applicable to the lending entity", "treatment of default interest and post-write-off recoveries", "period cut for financial statements versus sim_day"],
      "alternatives_rejected": ["cash basis", "recognizing the platform settlement fee as Capital revenue", "upfront fee recognition (moot under zero fees)", "continuing accrual to income after DEFAULTED"],
      "consumer": "ProjectionPort (V2 candidate postings 1110, 4100, 4110, 4300 from the terms-overlay interest ledger); reconciliation (interest ledger totals vs candidate projection, new check); statement (no revenue category added; CAP-09 text unchanged); export manifest (statement and projection sections)",
      "revisit_triggers": ["accountant review", "terms-overlay implemented", "live settlement views bound (CAP-07)", "fin-credit-exposure-reconciliation adopted"]
    },
    "tax_reporting_treatment": {
      "status": "ADOPTED",
      "owner": "Capital Tax Policy Owner (interim holder: Fable 5.1 under the 2026-10-08 delegation; professional reviewers: tax adviser and accountant designated by JunTae)",
      "value": {
        "policy_version": "CAPITAL-TAX-V1",
        "jurisdiction": "KR",
        "entity_assumption": "domestic corporation operating the Capital lending book (see lending_or_claim_trading_licence)",
        "vat": {
          "interest_income_4100_4110_4300": "EXEMPT_FINANCIAL_SERVICE (working assumption; no tax invoice; exempt-supply reporting duties to be reviewed)",
          "capital_fees_4200": "TAXABLE_10_PERCENT_IF_EVER_NONZERO with a tax invoice to the beneficiary (working assumption)",
          "platform_settlement_fee": "NOT_CAPITAL; VAT on platform fees is upstream UNDETERMINED (MOVE_PRIMARY_ISSUANCE_PRICE_FEE section 6; settlement-policy-deepening)",
          "input_vat_apportionment": "mixed exempt and taxable supplier rules to be reviewed"
        },
        "withholding_on_interest_received": {
          "parameter": "withholding_rate_bps",
          "simulation_value": 0,
          "status": "NOT_MODELED_V1_FIELD_RESERVED",
          "design": "gross interest recognized in 4100; the amount withheld by the beneficiary posted to 1300 as prepaid corporate tax; cash received net; FSM repay still carries principal only",
          "review": "whether interest paid by a corporate beneficiary to the Capital entity is subject to withholding depends on the lender entity classification"
        },
        "corporate_income_tax": {
          "interest_income": "taxable; accrual versus receipt timing for tax purposes to be reviewed",
          "provisions_1190": "book expected-credit-loss provision is not assumed deductible; BTD_PROVISION memo carries the book-tax difference",
          "writeoffs_5200": "deductible only when statutory bad-debt conditions are met; BTD_WRITEOFF memo",
          "reserve_3200": "equity appropriation has no tax effect (working assumption)"
        },
        "settlement_statement_tax_component": "the tax field in F01-F03 settlement statements (gross = amount + fee + tax + held + adjustment) is a provider-side deduction observed on the claim; it is never Capital's tax and never Capital's VAT; recorded only as a non-cash component",
        "invoices_receipts": "no tax invoice for exempt interest (working assumption); exempt-supply invoice, cash receipt and e-invoice duties are review items (TOSS_METHOD_EXPANSION_REVIEW TM09)",
        "reporting_artifacts": {
          "shipped_product": "projection tax const NOT_BOUND, statement tax_reporting NOT_BOUND, evidence unavailable includes tax_reporting, manifest is not a filing; all unchanged",
          "future": "a tax_memo export section (period cut, exempt revenue, taxable revenue, withholding receivable, BTD memos) only after accountant review and an adapter node; never labelled a tax filing (FINANCE_COMPLETION_DESIGN_KO section 7)"
        },
        "cross_border": "non-resident beneficiaries and treaty withholding NOT_IN_V1",
        "never": ["label any Capital artifact as a tax filing, GAAP/IFRS statement or regulated lending report", "infer a tax position from SIMULATION_FIXED_V1 numbers or fixtures", "net withholding against principal inside the FSM repay command"]
      },
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-09",
      "cap_rows": ["CAP-13", "CAP-15"],
      "rationale": "Tax follows revenue recognition and the licence route; the design-critical item is withholding on interest received, which changes net cash versus gross interest in the repayment allocation, so the field is reserved now at rate 0 while VAT exemption of interest, taxability of fees and book-tax differences on provisions and write-offs are recorded as working assumptions with named reviewers.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "review_owner": "tax adviser and accountant designated by JunTae; questions via f04-real-funds-lift-criteria, tl-legal-brief and TM09",
      "review_items": ["VAT exemption of interest for a non-bank lending entity", "withholding on interest received from corporate beneficiaries", "tax timing of interest income", "deductibility limits of credit-loss provisions and bad-debt write-offs", "invoice and receipt duties for exempt supplies", "input VAT apportionment"],
      "alternatives_rejected": ["leaving tax wholly UNDETERMINED (no field reservation possible)", "treating interest as a taxable service", "not modelling withholding at all", "booking the settlement statement tax component as Capital tax"],
      "consumer": "ProjectionPort (V2 candidate accounts 1300, 2300 and BTD memos); export manifest (future tax_memo section after accountant review); statement keeps tax_reporting NOT_BOUND; effectively no local consumer until the adapter and professional review",
      "revisit_triggers": ["tax adviser review", "lender entity decided (f04-real-funds-lift-criteria)", "settlement-policy-deepening decides the fee VAT boundary", "first non-zero fee or non-resident beneficiary"]
    },
    "lending_or_claim_trading_licence": {
      "status": "ADOPTED",
      "owner": "Capital Regulatory Route Owner (interim holder: Fable 5.1 under the 2026-10-08 delegation; professional reviewer: legal counsel designated by JunTae; lift decision: JunTae via f04-real-funds-lift-criteria)",
      "value": {
        "policy_version": "CAPITAL-LICENCE-ROUTE-V1",
        "v1_product": "B2B advance against captured settlement claims of organizer legal entities (F04); no consumer lending; no deposits; no investor participation",
        "primary_route": "DEDICATED_KIX_CAPITAL_LENDING_ENTITY_REGISTERED_AS_MONEY_LENDER (registration under the Korean Money Lending Business Act; registration authority and online-lending classification to be confirmed by counsel)",
        "fallback_route": "LICENSED_PARTNER_LENDER_WITH_KIX_CAPITAL_AS_PLATFORM_AND_SERVICER (adds loan-product agency or brokerage registration questions under the Financial Consumer Protection Act and partner or PG contractual limits; Toss profile unknowns)",
        "rate_cap_linkage": "the all-in cost cap of 2000 bps per year in CAPITAL-TERMS-V1 is the working assumption paired with the primary route",
        "claim_trading_cap03": {
          "v1": "NOT_OFFERED",
          "target": "recourse purchase of settlement claims only by the lending entity, treated as lending under the same registration (working assumption)",
          "deferred": "non-recourse true sale, third-party investor claim slices and tranching require securities-law, online-investment-linked-finance and debt-collection-licence review before any design; tranching_v1 NONE per CAPITAL-TERMS-V1"
        },
        "collection_of_assigned_claims": "second-tier execution (completeness C2 or higher) requires debt-collection licensing confirmation (CAPITAL-TERMS-V1 collateral_execution review item)",
        "kyc_aml": "duty-bearer is the lending entity (working assumption); Capital consumes attested facts only (identity_provider_kyc NOT_ADOPTED); vendor UNDETERMINED",
        "consumer_protection": "beneficiaries are businesses in V1; any individual beneficiary triggers consumer-finance and credit-information review; NOT_IN_V1",
        "fsm_flags_stay_false": ["license_granted", "regulated_product", "legal_debtor_bound", "collateral_perfected", "priority_bound", "funds_executed"],
        "gate": "real funds, real lending and real KYC stay locked (PROGRAM_DECISIONS_20260928 section 5); the lift decision is the user node f04-real-funds-lift-criteria; this route is Capital's design assumption and an input candidate, not the lift",
        "applicability_determination": "PENDING_PROFESSIONAL_REVIEW",
        "e06_label": "ORIGINAL_32 E06 regulation/compliance stays design-in-progress upstream; this note does not raise it"
      },
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-09",
      "cap_rows": ["CAP-13", "CAP-15"],
      "rationale": "An interest-bearing advance is credit under the working assumption, so a registered lending entity is the route that keeps CAPITAL-TERMS-V1 pricing, two-person authority and the recovery waterfall under Capital's control and matches the 20 percent all-in cap assumption; claim purchase and investor slices stay out of V1 consistent with 100 percent platform loss bearing and no tranching, and the legal applicability is explicitly left to counsel while the real-funds lift stays with the user node.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "review_owner": "legal counsel designated by JunTae; input to f04-real-funds-lift-criteria (user node), tl-legal-brief and pending cr-01-product-authority",
      "review_items": ["whether the V1 advance is lending under the Money Lending Business Act and which registration applies", "recourse claim purchase as lending versus factoring", "debt-collection licensing for assigned-claim collection", "securities and online-investment-linked-finance questions before any investor slice", "KYC/AML duty-bearer and scope for legal-entity beneficiaries", "partner-route agency or brokerage registration if the fallback is chosen"],
      "alternatives_rejected": ["operating as an unregistered platform advance", "online investment-linked finance route in V1 (no investors, tranching NONE)", "non-recourse claim purchase marketplace in V1", "leaving the route UNDETERMINED (the delegation asks for a design decision; the legal determination is separated as PENDING_PROFESSIONAL_REVIEW)"],
      "consumer": "no local consumer (no seam reads a licence; readiness release-group blocker text and the CAPITAL_REQUIREMENTS_KO CAP-03 row cite this note via a sync node; FSM flags unchanged)",
      "revisit_triggers": ["legal counsel review", "f04-real-funds-lift-criteria user merge", "cr-01-product-authority promoted", "any individual beneficiary or investor participation proposed"]
    },
    "data_retention_privacy": {
      "status": "ADOPTED",
      "owner": "Capital Data Protection and Records Owner (interim holder: Fable 5.1 under the 2026-10-08 delegation; professional reviewer: legal/privacy counsel designated by JunTae; slot owners per upstream R1 plus the accountant for the tax/accounting slot)",
      "value": {
        "policy_version": "CAPITAL-RETENTION-PRIVACY-V1",
        "pii_posture": "NO_PERSONAL_DATA_BY_DESIGN_V1: role labels (fixture-organizer, beneficiary_role, debtor_role, fixture-buyer) are not persons; there are no accounts, passwords, real names, bank accounts or credit data; free-text fields (adjustment_reason, reason labels) must never carry personal data",
        "data_classes": [
          {"id": "journal", "content": "accepted F04 commands (ids, amounts, fixture ids)", "pii": "none", "store": "memory or LOCAL_FILE_WORKSPACE payload.journal", "recomputable": false},
          {"id": "receipts", "content": "operation_id, instance_id, outcome, role label, result or error", "pii": "none", "store": "memory or workspace payload.receipts", "recomputable": false},
          {"id": "case_fixtures", "content": "advance_id to fixture id", "pii": "none", "store": "workspace payload.case_fixtures", "recomputable": false},
          {"id": "derived_views", "content": "projection, reconciliation, statement, scenarios, preview", "pii": "none", "store": "not stored; recomputed per request", "recomputable": true},
          {"id": "export_manifests", "content": "hashed sections including journal and receipts bodies", "pii": "none by construction; bodies must stay PII-free because manifests may leave the host", "store": "wherever the operator saves them; identity by content_digest", "recomputable": true},
          {"id": "dev_hmac_key", "content": "DEV_ONLY integrity key", "pii": "none", "store": "WORKSPACE/export-dev.key mode 0600; never in responses or logs", "recomputable": false},
          {"id": "test_and_ci_artifacts", "content": "golden digests, screenshots", "pii": "none", "store": "repo (golden) and CI artifacts (screenshots, not committed)", "recomputable": true}
        ],
        "retention_slots": {
          "legal_dispute_hold": {"owner": "legal/privacy counsel designated by JunTae", "duration": "NOT_SET_OWNER_SUPPLIED"},
          "business_reconciliation": {"owner": "Toss contract/technical (provider-side window)", "duration": "NOT_SET_OWNER_SUPPLIED"},
          "retry_support": {"owner": "Astra", "duration": "NOT_SET_DECISION_REQUIRED"},
          "memory_residency": {"owner": "Astra", "bounds": {"count": "NOT_SET_DECISION_REQUIRED", "bytes": "NOT_SET_DECISION_REQUIRED", "age": "NOT_SET_DECISION_REQUIRED"}, "note": "MAX_OPERATIONS 500 is a demo capacity bound, not a residency value"},
          "tax_accounting_records": {"owner": "accountant and tax adviser designated by JunTae (Capital-added fifth slot; absent from the upstream question sheet)", "duration": "NOT_SET_OWNER_SUPPLIED"}
        },
        "why_no_durations": "upstream RETENTION_PERIODS_PROPOSAL R1 (PR #139, user-merged) keeps every value stopped and forbids provider public values such as the 15-day idempotency key as retention values; CAPITAL_UPSTREAM_BINDING mirrored that; counsel has not answered L10-R, L10-H or U10-C",
        "simulation_retention": "RETAIN_ALL_NO_AUTOMATIC_DELETION: journal and receipts are append-only; the capacity bound rejects new writes (SIMULATION_CAPACITY) instead of evicting; workspace files are deleted only by the operator; a restarted process serves original receipts under a new instance_id",
        "rules": [
          "an open legal or dispute hold blocks deletion regardless of the other slots",
          "cache eviction is not disposal of the authoritative record",
          "an absent receipt is UNKNOWN_UNRESOLVED and never evidence of non-execution",
          "chain-anchored facts cannot be erased, so Capital never writes personal data into material that may be anchored or hashed into a shared manifest",
          "erasure of future personal data is performed at the identity or KYC provider; Capital holds pseudonymous references only (identity_provider_kyc)",
          "no personal data in fixtures, tests, golden files, question sheets, Git or chat (upstream question-sheet rule)"
        ],
        "access_control": "role matrix retained: observer cannot read export, projection, statement or reconciliation; auditor reads everything and writes nothing; organizer writes; the agent lane reads none of these; export and manifest are export:read",
        "key_material": "the dev HMAC key is integrity only, DEV_ONLY, deleted with its workspace; it is not a credential and its retention is not a legal record",
        "shipped_product_rule": "manifest retention_policy const NOT_BOUND stays until retention-slots-sync replaces it with the named empty slots; code never defaults a duration"
      },
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-09",
      "cap_rows": ["CAP-14", "CAP-15"],
      "rationale": "Capital holds no personal data today and that is a code fact, so the privacy posture and data classification can be decided now; the retention structure mirrors the user-merged upstream R1 and the prior Capital binding note, adds the missing tax/accounting slot, and leaves durations to their owners because filling them before counsel answers would both contradict the upstream decision and impersonate a legal conclusion; the strongest rule Capital can keep now is that nothing anchored or hashed into a shareable manifest may carry personal data.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "review_owner": "legal/privacy counsel designated by JunTae (I10: L10-R, L10-H, U10-C); Astra for retry and memory slots; Toss for the reconciliation window; accountant for tax and accounting records",
      "review_items": ["statutory, dispute and tax retention durations per data class", "whether pseudonymous role labels or future principal references are personal data", "erasure handling when a hold is open", "cross-border transfer if manifests leave Korea"],
      "alternatives_rejected": ["a single retention period (upstream R2 branch)", "filling statutory durations before counsel answers", "omitting a tax/accounting slot", "leaving the privacy posture UNDETERMINED although the code holds no personal data"],
      "consumer": "export manifest (retention_policy slot via retention-slots-sync; data_classes summarized in the manifest note); reconciliation (unknown_policy retry_authorized false unchanged); readiness release group text",
      "revisit_triggers": ["counsel answers L10-R, L10-H, U10-C", "Astra decides retry support and memory residency", "k-stage5-durable-tx storage exists to apply values", "any personal data class is introduced (identity adapter)"]
    }
  },
  "consumer_map": {
    "ProjectionPort": {"default": "SimulationProjection SIMULATION_FIXED_V1 unchanged", "candidate": "additive COA-V1 candidate implementing chart_of_accounts_mapping, revenue_recognition_basis postings and tax_reporting_treatment accounts (1300, 2300, BTD memos); still SYNTHETIC_UNADOPTED; owner terms-overlay plus projection-coa-candidate"},
    "reconciliation": {"unchanged": "six checks and unknown_policy", "added_later": "coa_candidate_totals_vs_v1 and interest ledger totals vs candidate projection"},
    "export_manifest": {"unchanged": "seven sections, content_digest rule, retention_policy NOT_BOUND until retention-slots-sync", "later": "named empty retention slots; tax_memo section only after accountant review; never a filing"},
    "statement": {"unchanged": "five categories, primary_and_resale NOT_SUMMED, tax_reporting NOT_BOUND"},
    "no_local_consumer": ["lending_or_claim_trading_licence (readiness and requirements text sync only; FSM flags unchanged)"]
  },
  "confirmations": {
    "kix_protocol_modified": false,
    "kix_commerce_apps_modified": false,
    "capital_code_modified": false,
    "vendor_unchanged": true,
    "upstream_nodes_marked_complete": [],
    "upstream_adoption_claimed": false,
    "simulation_chart_remains": true,
    "accounting_or_tax_position_inferred_from_synthetic_projection": false,
    "diff_scope": "docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md only; capital/, tests/, capital/vendor/ and the five vendor sha256 values unchanged",
    "production": "NOT_AUTHORIZED",
    "real_money": false
  }
}
```

## 5. 수용 기준 매핑

| 수용 기준 | 충족 위치 |
|---|---|
| `docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md`에 하나의 capital-decision-v1 JSON 블록, 다섯 항목(`chart_of_accounts_mapping`, `revenue_recognition_basis`, `tax_reporting_treatment`, `lending_or_claim_trading_licence`, `data_retention_privacy`) 각 `status`·`owner`·`value`·`provided_by`·`date`·`cap_rows`·`rationale`·`provisional`·`basis` | §4. 이 문서의 fenced 블록은 하나뿐이고 `entries`에 다섯 키가 모두 있으며 각 항목이 아홉 키를 가진다. `basis`는 다섯 항목 모두 `WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW`, `cap_rows`는 CAP-13/14/15 안이다 |
| ADOPTED는 `provided_by "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08"`, `date`, `provisional: true`; 구체적·포부 있는·구현 가능한 값; UNDETERMINED는 이유와 함께만; UNDETERMINED에 value나 ADOPTED에 provided_by/date 누락은 무효 | §4 다섯 항목 모두 ADOPTED이고 같은 문자열·`2026-10-09`·`true`다. UNDETERMINED 항목은 없으므로 무효 조합도 없다. 보존 기간 숫자는 ADOPTED 구조 값 안의 `NOT_SET_OWNER_SUPPLIED` 자리이며 이유(`why_no_durations`)를 적었다. 인허가의 법적 적용 판단은 값 안의 `applicability_determination: PENDING_PROFESSIONAL_REVIEW`로 분리했다 |
| PROVISIONAL PRODUCT DECISION 라벨, 청약 아님·실자금 없음, 법률·세무·회계는 작업 가정; KIX 장기 비전과의 연결과 읽은 kix-protocol 문서 경로; 열린 위험; 모든 수용 항목 매핑 | 머리말 상태 배너와 §4 `status`/`scope`/`basis_default`; §2(README, DEVELOPMENT_PLAN §1·§3·§5·§6.3·§13·§14·§18, BLUEPRINT_20260914 §3·§4·§5·§10·§12, ROADMAP, PROGRAM_ROADMAP_20260930 §0·§2·§5, PROGRAM_DECISIONS_20260928 §2.1·§5, AUTHORITY_MODEL_1, TOKEN_LAYER_AND_RIGHTS_SCALE_SCOPE_20260929, RIGHTS_SCALE_RS0_DECISION_20261008, RETENTION_PERIODS_PROPOSAL_20261009, RUNTIME_ARCHITECTURE_S062, COMMERCE_CONTRACTS, blueprints 2종, contracts CREDIT_ADVANCE_F04·SETTLEMENT_DISTRIBUTION_F01_F03·AI_DELEGATION_AUTHORITY·FIRST_BATCH_OPEN_INPUTS·STATE_LIFECYCLE·PG_TOSS_CARD_PROFILE·RIGHTS_SCALE_PROFILE·MOVE_PRIMARY_ISSUANCE_PRICE_FEE, aiops FINANCE_COMPLETION_DESIGN_KO·PROGRAM_EXPANSION_20261002_KO, status ORIGINAL_32_STATUS·CURRENT_CAPABILITY_REGISTER·FIRST_BATCH_OWNER_QUESTION_SHEETS_KO, reviews TOSS_METHOD_EXPANSION_REVIEW, PROTOCOL_MASTERPLAN_V2(역사)); §6; 이 표 |
| SIMULATION 차트가 출시 로컬 제품에 남을 수 있는지 명시; 합성 투영에서 회계·세무 입장을 추론하지 않음 | 머리말 표 마지막 행, §1 마지막 행, §3.1 끝 조건표, §4 `simulation_chart_in_shipped_product`(`REMAINS`)와 `confirmations.accounting_or_tax_position_inferred_from_synthetic_projection: false` |
| 각 ADOPTED 값을 소비 seam(ProjectionPort, reconciliation, export manifest)이나 'no local consumer'에 매핑 | §1 표 "소비 노드 / seam" 열, §3 각 항목의 "게이트와 소비 seam", §4 각 항목 `consumer`와 `consumer_map`. `lending_or_claim_trading_licence`는 `no local consumer`로 명시 |
| 모든 항목에 `owner`(이름 있는 소유 역할)와 `basis WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW` | §4 각 항목의 `owner`(역할 + 현재 보유자 + 검토자)와 `basis`; 머리말 "owner 어휘" |
| diff는 `docs/decisions/`에 한정, vendor·코드 변경 없음 | 머리말과 §4 `confirmations`. 이 세션은 읽기 전용이며 파일을 쓰지 않았다. 실제 diff 범위는 supervisor PR과 독립 리뷰어가 확인한다 |
| (이전 요청문) 소유자: JunTae + 회계·법무 자문 | 위임(2026-10-08)으로 결정 권한이 Fable에게 옮겨졌고, 전문가 검토자 지명은 JunTae 몫으로 남았다(upstream D-E). 각 항목의 `review_owner`가 그 자리다 |

## 6. 열린 위험과 재검토 조건

- **이중 상태.** upstream `FINANCE_COMPLETION_DESIGN_KO.md` §3은 계정·수익 인식·세금·보존을 UNDETERMINED로 두고, Capital은 같은 항목에 잠정 값을 가진다. Capital 값은 upstream 상태를 바꾸지 않는 **입력 후보**다. upstream이 다른 값을 채택하면 이 문서는 개정 대상이다.
- **인허가 경로(법무).** 대부업 등록 대주 법인이 1차 경로이지만, 선지급의 법적 성격(대부 vs 채권매입), 등록 관할, 온라인 영업 분류, 양수 채권 추심 허가, 파트너 경로의 중개 등록은 전부 작업 가정이다. 결론이 다르면 `CAPITAL-TERMS-V1`의 2,000 bps 상한과 `collateral_execution` 2차 집행을 함께 다시 연다.
- **원천징수(세무).** 법인 수익자가 Capital 법인에 지급하는 이자에 원천징수가 붙으면 상환 현금이 총액 이자보다 작아진다. 필드(`withholding_rate_bps`, 1300)는 예약했지만 값 0의 시뮬레이션은 그 분기를 검증하지 못한다. 값이 정해지면 `terms-overlay`의 배분 산술에 총액/순액 규칙이 들어가야 한다.
- **VAT 면세 가정과 겸영 안분(세무).** 이자 면세가 대주 법인에 적용되지 않거나 과세·면세 겸영이면 4100의 처리와 매입세액 안분이 바뀐다. 플랫폼 수수료 VAT는 upstream 미정이라 Capital 경계 밖이지만, 두 사업이 한 법인이면 안분 문제가 Capital에도 닿는다.
- **충당·상각의 장부·세무 차이(회계·세무).** 1190/5100/5200/3200의 분류(자본 적립 vs 부채성 충당), K-IFRS 1109 적용 여부, 부도 뒤 이자 인식 유예와 순장부금액 기준 이자의 정합, 상각의 손금 요건은 회계사·세무사 검토 전까지 작업 가정이다.
- **계정 코드 충돌.** upstream `fin-ledger-contract`가 다른 코드 체계·차원 이름을 채택하면 COA-V1은 매핑 표를 다시 쓴다. V1 다섯 계정은 바뀌지 않으므로 출시 제품은 영향이 없다.
- **보존 숫자 공백.** 다섯 칸 모두 값이 없다. 저장 backend(`k-stage5-durable-tx`)가 생겨도 값이 없으면 회수·축출을 켤 수 없다. 이는 의도된 정지다(upstream R1).
- **PII 유입 경로.** `adjustment_reason`(최대 100자 자유 문자열)과 reason 라벨, 미래 principal 참조는 개인정보가 들어올 수 있는 유일한 자리다. 규칙은 적었지만 코드 검사는 없다. identity adapter가 열릴 때 입력 검증을 함께 둬야 한다.
- **manifest 외부 공유.** export manifest는 journal·receipts 본문을 담고 `content_digest`로 식별된다. 호스트 밖으로 나가면 회수할 수 없으므로 본문 PII-free 규칙이 깨지면 삭제 요청에 응할 수 없다.
- **세무·회계 검토자 부재.** upstream 질문서에 세무·회계 담당 행이 없고(RETENTION R1 §4), Capital에도 이름이 없다. JunTae가 지명하기 전에는 이 문서의 모든 회계·세무 값이 검토되지 않은 채 남는다.
- **sync 노드의 테스트 결합.** `tests/test_projection.py`는 CAP-13 note 문구와 durable-finance 그룹의 `blockers`·`available` 문구를 정확히 고정한다. readiness 문구를 이 노트 인용으로 바꾸는 sync 노드는 그 테스트를 함께 갱신해야 한다(상태값은 그대로).
- **재검토 트리거.** (1) JunTae의 회계사·세무사·법무/개인정보 담당 지명과 서면 회신, (2) `fin-ledger-contract`·`settlement-policy-deepening`·`f04-mock-deepening` 사용자 병합, (3) `f04-real-funds-lift-criteria` 사용자 병합(대주 법인·KYC 주체), (4) `k2-retention-proposal` 후속 회신(L10-R·L10-H·U10-C, U09-R, T08), (5) `k-stage5-durable-tx`·`k-stage7-authenticated-export` 병합, (6) 첫 비KRW 자산·첫 개인 수익자·첫 투자자 참여 제안, (7) `terms-overlay` 구현에서 드러나는 산술 불일치.

## 7. 후속 작업

- **`terms-overlay`(선행 결정의 적용 소유 노드) 확장.** `CAPITAL-TERMS-V1` 적용 시 이자·충당·준비금·회수 메모를 COA-V1 코드(1110·1190·3100·3200·4100·4110·4300·5100·5200·9700)와 차원(`terms_version`, `chart_version`, `sim_day`, `source_cut`)으로 기록한다. `withholding_rate_bps` 필드를 0으로 예약하고 총액 인식·순액 수령·1300 구조를 둔다. V1 투영과 골든은 건드리지 않는다.
- **`projection-coa-candidate`(새 노드, 코드).** `capital/ports.py` `ProjectionPort`의 두 번째 구현(`SIMULATION_FIXED_V2` 또는 `CAPITAL_COA_V1_CANDIDATE`)을 추가형으로 넣는다. 라벨은 `SYNTHETIC_UNADOPTED`·`tax=NOT_BOUND`·`legal=NOT_BOUND`·`operating_ledger=NOT_BOUND` 그대로. 기본 `mode`는 V1 유지, 후보 mode 이름은 그 노드가 정하고 `facade-v1.json`·`app.js` guard·`tests/test_projection.py`의 mode 거절 목록을 함께 갱신한다. `capital/recon.py`에 `coa_candidate_totals_vs_v1` 검사를 더한다. `docs/SEAMS.md` ProjectionPort 행은 `NOT_BOUND` 그대로(영수증 없음).
- **`readiness-decision-note-sync`(동기화, 문구만).** `capital/readiness.py` durable-finance 그룹 `blockers`("Finance 후보 8개 채택과 계정/세무 정책")와 release 그룹 `blockers`("면허/법무", "보존·복구·개인정보"), `capital/service.py` snapshot `decisions`, `requirement_notes` CAP-13/14/15, `docs/CAPITAL_REQUIREMENTS_KO.md` CAP-03·CAP-13·CAP-14·CAP-15 행이 "PROVISIONAL per docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md"를 인용하도록 바꾼다. 상태값(`UPSTREAM_REQUIRED`, `NOT_AUTHORIZED`, `NOT_BOUND`)은 바꾸지 않는다. `tests/test_projection.py`의 고정 문구를 같은 PR에서 갱신한다.
- **`retention-slots-sync`(선행 결정이 명명; 범위 확장).** manifest `retention_policy`의 `NOT_BOUND` 상수를 다섯 칸(네 upstream 칸 + `tax_accounting_records`)·주인·`NOT_SET_*` 값 구조로 바꾸고, `data_classes` 요약을 manifest `note`에 넣는다. 어떤 기간도 기본값으로 채우지 않는다. `facade-v1.json`과 `capital/verify.py`·`tests/test_export_manifest.py`를 함께 갱신한다.
- **upstream 제출 후보(채택 주장 없음).** `fin-ledger-contract`(COA-V1 계정·차원·V1 매핑·불변식을 입력 벡터로), `settlement-policy-deepening`(명세서 `tax` 성분 경계와 플랫폼 수수료 VAT 질문), `f04-real-funds-lift-criteria`(인허가 경로·KYC 주체·원천징수·검토 항목), `tl-legal-brief`·`k1-open-inputs-brief`(I10 보존·개인정보 질문, TM09, 세무·회계 담당 지명 요청), `cr-01-product-authority`(pending; 대주·차주·정책 권위 입력). 채택은 upstream PR 영수증만이 증명한다.
- **전문가 검토 착수(JunTae).** 회계사·세무사·법무/개인정보 담당을 지명한다(upstream D-E). 질문지는 §4 각 항목의 `review_items`를 그대로 쓴다. 회신이 오면 이 문서를 개정하고, 결론이 다른 항목은 `CAPITAL_FINANCIAL_TERMS.md`의 연결 값(상한·준비금·집행)과 함께 다시 연다.
- **Commerce.** 이 문서는 Commerce 화면을 바꾸지 않는다. 화면이 계정·세무·보존 상태를 보여 주려면 Capital 조회(`/api/projection`, `/api/export/manifest`, `/api/readiness`)를 소비해야 하며 클라이언트 산술은 금지다.
