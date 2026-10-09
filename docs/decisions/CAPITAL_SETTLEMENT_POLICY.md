# Capital 정산 정책 결정 — 배정 우선순위, 환불 부담, 리셀 과거계약 취소 부담, 수익 참여, 채권 매입, 잔여·늦은 현금

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
이 문서는 KIX-CAPITAL 저장소 안의 **시뮬레이션·제품 설계용** 결정이다. 청약이나 대출·투자 제안이 아니고, 실자금이 움직이지 않으며, production은 계속 `NOT_AUTHORIZED`다. 법률·세무·회계·인허가·소비자보호 관련 내용은 **전문가 검토 전의 작업 가정(WORKING ASSUMPTION)** 이며 법률·세무·회계 자문이 아니다. 어떤 upstream 계약(kix-protocol `settlement-policy-deepening`, `fin-multi-payee-refund-proof`, `ps-03-resale-contract`, `cr-02`/`cr-06` 등)의 채택도 주장하지 않는다. 채택은 upstream의 실제 PR·병합 영수증만이 증명한다. 이 문서는 kix-protocol·kix-commerce-apps를 수정하지 않고, 어떤 upstream 노드도 완료로 표시하지 않으며, diff는 `docs/decisions/` 한 파일이다. 고정 FSM·아홉 개 F01–F03 fixture·두 시험 배정 순서·500 bps fixture 정책·vendor 바이트는 건드리지 않는다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `settlement-policy-decision` (Decision: allocation priority, refund burden, revenue share, claim purchase) · deps `pr1-merge-ready` · kind `decision` · user_merge `False` |
| 결정자 | **Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08** |
| 위임 원문 | 2026-10-08 18:25 KST JunTae Park: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." |
| 결정일 | 2026-10-09 |
| KIX-CAPITAL 기준 | main `82d6028` (accounts-tax-legal-decision #17). 선행 결정 문서는 [CAPITAL_FINANCIAL_TERMS.md](CAPITAL_FINANCIAL_TERMS.md)(`CAPITAL-TERMS-V1`, 2026-10-08), [CAPITAL_UPSTREAM_BINDING.md](CAPITAL_UPSTREAM_BINDING.md)(2026-10-09), [CAPITAL_ACCOUNTS_TAX_LEGAL.md](CAPITAL_ACCOUNTS_TAX_LEGAL.md)(2026-10-09)이며, 이 문서는 그 값(집행 1차 = 수익자 배분 상계, CAP-03 V1 `NOT_OFFERED`, 메모 계정 9300/9400, `SettlementPolicyPort` DEFERRED, 보존 `RETAIN_ALL`)과 충돌하지 않고 그 위에 쌓는다 |
| kix-protocol 기준 | main `c2cde86` (`c2cde86e21a6e5ba6f24a56548636db6d0a34c6f`, 읽기 전용 체크아웃 `/workspace/capital-run/kixproto-ro`, `.git/refs/heads/main`에서 확인) |
| vendor pin | `capital/vendor/manifest.json` commit `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`, 다섯 파일 SHA256 불변. 정산 FSM `settlement_f01_f03/settlement_fsm.py` `c6d7ae79…`, 산술 `mock_settlement.py` `9e9c2557…` |
| 상태 어휘 | **ADOPTED** = Fable이 위임 범위 안에서 Capital의 잠정 값을 정했다(법률 의존 항목은 전문가 검토 대상). **UNDETERMINED** = 정직하게 값을 정할 수 없어 담당과 이유만 적는다(`value: null`, 방향은 `target`). 이번 노트의 여섯 항목은 모두 ADOPTED다 |
| FSM 표현 가능성 어휘 | 각 항목에 `fsm_expressible`을 적는다. 고정 `SettlementMachine`이 오늘 정책 입력으로 받는 것은 **`distribute(order=[...])`의 명시적 배정 순서 목록**뿐이다(그 밖의 입력은 `PRIMARY_FEE_BPS` 2수취인 정책, 환불 금액·수혜자·사유 라벨, 명세서 성분이며 정책을 **고르는** 자리가 아니다). 따라서 `allocation_order`만 `true`이고 나머지 다섯은 `false`·**`requires upstream FSM change`** 다. `false`인 항목은 소비 노드 `policy-simulator`가 일회용 복제 장부에서 **그림자 계산(SHADOW_NOT_APPLIED)** 만 하고 고정 FSM에 적용하지 않는다 |

용어: 금액은 KRW 정수(최소단위 1원, upstream `AssetSpec {fiat, KRW, 0}`), 비율은 bps(1/10000), 날짜는 오버레이 논리 일(`sim_day`, `CAPITAL-TERMS-V1`). 고정 FSM은 `capital/vendor/settlement_f01_f03/settlement_fsm.py`의 `SettlementMachine`과 `mock_settlement.py`의 `MockSettlement`다. `P_p`는 1차 발행 총액(primary gross), `P_r`은 최신 리셀 금액, `seller_due`·`organizer_due`·`platform_due`는 Move `accept_sale`의 리셀 `Allocation` 세 줄이다.

## 1. 결정 요약

| item | 결정 (요지) | CAP rows | fsm_expressible | 소비 노드 / seam |
|---|---|---|---|---|
| `allocation_order` | **ADOPTED.** `CAPITAL-ALLOC-V1`: 부족 현금은 **클래스 우선순위 → 클래스 안 액면 비례(largest remainder, 동점은 라벨 오름차순)**. 클래스 순서 ① 보호 제3자(공연자·공연장·권리자) ② 거래상대 몫(1차 주최자 잔여, 리셀 `seller_due`) ③ 생태계 로열티(리셀 `organizer_due`) ④ 플랫폼 수수료. 2수취인 fixture에서 도출되는 명시 순서는 `["organizer", "platform"]`. 첫 수락 `distribute`가 순서를 동결하고 정책 digest를 청구 옆에 기록. 거래상대 몫의 사후 적용 순서: 선지급 상계 → 채권 슬라이스 → 수익 참여 → 지급 의도 | CAP-02, CAP-05 | **true** (명시 순서 목록으로; 클래스 안 비례 배정은 FSM 변경 필요) | `policy-simulator` / `SettlementPolicyPort` → upstream `settlement-policy-deepening`, `fin-multi-payee-refund-proof` |
| `refund_bearer` | **ADOPTED.** `CAPITAL-REFUND-BEARER-V1`: 환불 사유 클래스 5종. RC1 구매자 정책 내 환불 = 전 줄 비례 역분개, RC2 공연 취소·주최자 귀책 = 주최자 줄 먼저 → 플랫폼 수수료 줄(전액이면 고정 FSM의 `FIXTURE_FULL_GROSS_RECLASS`와 같은 결과), RC3 플랫폼 귀책 = 플랫폼 100 %, RC4 PG 차지백·분쟁 = RC2와 같되 작업 가정, RC5 리셀 = 별도 항목. 미지급분은 `cancelled_unpaid`, 기지급분은 `recovery_due`(제안만, 자동 상계 없음) | CAP-05, CAP-06 | **false** — requires upstream FSM change (`refund_bearer_policy=UNDEFINED`·배정 정지는 고정 FSM 그대로; 그림자 계산만) | `policy-simulator` → upstream `settlement-policy-deepening` §7 "부분 환불의 부담자", `fin-multi-payee-refund-proof` |
| `resale_prior_contract_cancel_burden` | **ADOPTED.** `CAPITAL-RESALE-UNWIND-V1`: **최신 거래만, 사슬 역추적 없음.** RU1 이전 뒤 공연 취소 = 현재 보유자가 `min(P_r, P_p + organizer_due + platform_due)`를 받음(1차 청구의 `P_p` 환불 + 최신 거래의 로열티·플랫폼 수수료 역분개; 판매자 `seller_due`는 회수하지 않음; 할인 리셀이면 보유자 `P_r`, 판매자 `P_p − P_r`). RU2 결제 기록 뒤·이전 전 리스팅 취소 = 예비 구매자에게 `P_r` 전액(세 줄 모두 역분개, V1 위약금 없음). RU3 이전 뒤 리셀 결제 차지백 = `seller_due` 회수채권 → `organizer_due` → `platform_due`; 권리는 Protocol 권위 | CAP-06 | **false** — requires upstream FSM change (리셀 청구 종류·3줄 분할·거래 사슬 연결·`COMPENSATION_UNDEFINED` 보상 레코드 없음) | `policy-simulator` → upstream `booking-resale-admission-deepening`, `ps-03-resale-contract`, `settlement-policy-deepening` |
| `revenue_participation` | **ADOPTED.** `CAPITAL-REVSHARE-V1`: 참여자 V1은 KIX Capital 자신(제3자 참여자 `NOT_IN_V1`). 기준 수익 B = 그 공연 청구들의 **거래상대 몫 줄에 배정된 현금** − 주최자 부담 환불. 비율 2,000 bps, 상한 = 투입액의 15,000 bps(1.5×), 허들 없음. 거래상대 몫의 회수 순서: 선지급 상계 → 채권 슬라이스 → 수익 참여 → 주최자 지급. 조정 창 = 마지막 명세서 뒤 90일(환불로 B 감소 시 초과 수령분은 회수채권, 늦은 현금은 증액) | CAP-02 | **false** — requires upstream FSM change (참여자 수취인·기준 수익·상한이 정책에 없음) | `policy-simulator` → upstream `settlement-policy-deepening` §7 "수익 waterfall", `k-stage6-economics-reference` |
| `claim_purchase` | **ADOPTED (설계; 제공은 V1 `NOT_OFFERED`).** `CAPITAL-CLAIM-PURCHASE-V1`: **상환청구권 있는 매입 = 대부로 취급**(`CAPITAL-LICENCE-ROUTE-V1`과 동일). 단위 = (청구, 수취인 줄, 슬라이스 액면). 수량 = 줄의 미지급 잔액 − 열린 환불 액면, T1 8,500 bps·T2 0, 줄당 열린 슬라이스 하나, 집계 상한은 `CAPITAL-TERMS-V1`과 공유. 보유자 V1 = KIX Capital 대주 법인만, 슬라이스 등록부(미래 `cr-02`) 유일성. 대가 = 액면 − 할인(T1 700 bps/yr × 예상 일수). 우선순위 = 그 줄의 배정 현금에서 보유자 먼저(선지급 상계와 같은 단계), 복수 보유자는 줄 안 pari passu, 환불 역분개는 주최자 잔여분이 먼저 흡수·부족분은 상환청구 | CAP-03 | **false** — requires upstream FSM change (의무 줄의 양도·보유자 필드 없음; F04 `note_advance`는 예약이지 양도가 아님) | `policy-simulator`(그림자) → upstream `cr-02-claim-eligibility`, `f04-real-funds-lift-criteria` |
| `residual_and_late_cash` | **ADOPTED.** `CAPITAL-RESIDUAL-V1`: 나눗셈 잔여 = largest remainder·라벨 오름차순(2수취인 1차 분할에서는 고정 FSM의 floor 분할과 같은 결과 = 잔여는 잔여 수취인에게). 미배정 현금 상태 4종: UC1 동결 순서 계속 배정, UC2 환불 재원 보류(수취인 배정 금지), UC3 전액 재분류 뒤 늦은 현금은 180일 보류 뒤 운영자 명령으로만 처리, UC4 초과 입금은 제공자 반환. 종결된 선지급은 다시 열지 않음. 지급 의도는 배정마다 생성·D+1 영업일 배치 목표·실행은 Capital 밖. 수취인 holdback 0 bps(`refund_reserve_bps` 필드 예약) | CAP-05, CAP-06 | **false** — requires upstream FSM change (보류·반환·지급 의도 명령 없음; 늦은 현금은 고정 FSM이 미배정으로 둠) | `policy-simulator` → upstream `settlement-policy-deepening` §7 "잔여 단위 우선순위·세금·보류·조정 잔액 해제", `cr-06-repayment-allocation` |

## 2. KIX 비전과의 연결

읽은 kix-protocol 문서(모두 main `c2cde86`)와, 각 선택이 그 비전에 봉사하는 방식이다.

- **모델 1 — 체인 권위 / 오프체인 위임 실행.** `README.md` §1·§3, `docs/decisions/AUTHORITY_MODEL_1.md`(A-4 기록·재생 분리), `docs/DEVELOPMENT_PLAN.md` §1("체인 재고·권리 원권위와 제공자 자금 사실, 오프체인 예약 약정은 다른 사실") §14("금융은 권리·정산채권·채무·부담을 구별"). 그래서 리셀 취소 부담(`CAPITAL-RESALE-UNWIND-V1`)은 **환불 수혜 자격을 체인 사실인 "현재 보유자"에 묶고** 돈의 의무는 전부 오프체인 청구 줄에 둔다. 어떤 항목도 권리 발행·이전·검표·폐기를 건드리지 않으며(`admission_granted`·`right_cancelled`는 계속 거짓), RU3 차지백에서도 권리 상태는 Protocol/Commerce 권위다.
- **정산 계약이 비워 둔 자리를 채우는 것이 R-9의 승인 범위.** `docs/contracts/SETTLEMENT_DISTRIBUTION_F01_F03.md` §0.2(수취인 단일 전제 금지), §0.3(정수 잔여 단위의 결정론적 사전 우선순위, 방법은 UNDETERMINED), §4(F02 호출자 순서는 fixture), §5(`refund_bearer_policy = UNDEFINED`, 배정 정지), §7(의도적으로 비운 항목: waterfall 원가·구간·상한·반올림·지급 시점, 잔여 단위 우선순위, 리셀 분할, 부분 환불 부담자, 거래 간 상계·준비금). `docs/decisions/PROGRAM_ROADMAP_20260930.md` §2 R-9는 "정산 계약 §7 … 초안 작업을 승인"하고 정책 값을 Astra 결정 경로로 둔다. JunTae의 2026-10-08 위임은 Capital 안에서 그 값을 Fable에게 맡긴 것이다. 그래서 여섯 항목 모두 값을 정하되, upstream `settlement-policy-deepening`(A3/ARCHITECTURE)은 여전히 열려 있고 이 문서는 그 **입력 후보**다. `docs/aiops/FINANCE_COMPLETION_DESIGN_KO.md` §4.2("승인된 버전의 배분 정책은 원 총액·대상 자산·수취인 집합·weights/fees·고정 우선순위와 digest를 계산 전에 동결한다. missing policy는 DECISION_REQUIRED")와 §4.3(`q_i = floor(T*w_i/W)`, `R = T − Σq_i`)의 모양을 그대로 따랐다.
- **규모 — RS 65,536석과 ps-07의 100만→3,000만.** `docs/decisions/TOKEN_LAYER_AND_RIGHTS_SCALE_SCOPE_20260929.md`, `docs/decisions/RIGHTS_SCALE_RS0_DECISION_20261008.md` §6(독립 객체 분할, 페이지 단위 위임), `docs/blueprints/rights-scale-v1/README.md` §1.2(여섯 상한)·§3.5·§7(1,024 → 16,384 → 65,536), `docs/aiops/PROGRAM_EXPANSION_20261002_KO.md` `ps-07-scale-qualification`(100만→1,000만→3,000만), `ps-03-resale-contract`. 모든 규칙을 **청구 한 건·최신 거래 한 건에서 O(1)로 닫히게** 설계했다: 배정은 클래스 표 조회, 환불 부담은 사유 클래스 조회, 리셀은 최신 거래만(사슬 역추적 없음), 잔여는 largest remainder 한 번. 어떤 규칙도 과거 거래 전체를 다시 열지 않는다. 클래스 표는 공연자·공연장·권리자·대행사 등 복수 수취인 자리를 미리 둔다(`docs/PROTOCOL_MASTERPLAN_V2.md` §7, `docs/BLUEPRINT_20260914.md` §7의 리셀 배분 정책 필수 항목).
- **"과거 구매자 계속 참여 금지"와 "최종 구매자 환불이 과거 계약 의무를 지우지 않는다".** `PROTOCOL_MASTERPLAN_V2.md` §7("단지 과거 구매자였다는 이유로 후속 리셀 이익을 계속 받는 구조는 … 포함하지 않는다"), `BLUEPRINT_20260914.md` §7("`FULL_CHAIN_UNWIND_FIXTURE`와 `LATEST_TRADE_UNWIND_FIXTURE`는 시험 정책이다 … 과거 거래 모두에 자동으로 전액 환불을 발생시키지 않는다", 금전 정책의 필수 결정 표: 리셀 계약 취소·공연 취소·지급 후 취소·차지백), `docs/ROADMAP.md` 우선순위 3(리셀·배분·제품 정책: 다수 수취인, 반올림, 비용·환불 부담). `CAPITAL-RESALE-UNWIND-V1`은 두 역사 fixture 중 어느 것도 승격하지 않고, **권리에 붙은 환불 자격(1차 액면)이 보유자와 함께 이동한다**는 세 번째 규칙을 정했다. 프리미엄은 보유자의 시장 위험이고 리스팅 때 공개한다.
- **Move·리셀 분할·1차 수수료의 격리.** `docs/contracts/MOVE_PRIMARY_ISSUANCE_PRICE_FEE.md` §1(`accept_sale`의 `organizer_due`·`platform_due`는 u128 바닥 나눗셈, `refund`의 `RefundDutyRequested.amount = last_amount`), PF-C04(환불 때 수수료 반환은 미정)·PF-C05(리셀 bps와 1차 `fee_bps` 격리), `docs/contracts/BOOKING_RESALE_ADMISSION_GATES.md` §10(`ResaleMachine`: `PAYMENT_NOTED` 뒤 `cancel_listing`은 `COMPENSATION_UNDEFINED`, 정산 게이트 `MOCK_COMMIT_OBSERVED`). 이 노트는 리셀 세 줄을 1차 2줄과 섞지 않고(격리 유지), `COMPENSATION_UNDEFINED`에 들어갈 보상 규칙(RU2)을 정하며, 체인의 `last_amount`는 **관측 입력**이지 환불 자격의 정의가 아니라고 적는다(§6 위험).
- **정수 산술·largest remainder·역분개 금지.** `docs/COMMERCE_CONTRACTS.md`(float 금지, 비례 배정의 largest-remainder·동점 라벨 오름차순, `FROZEN_LINE_PRICE_FULL_REVERSAL_V1`, "할인 부담 취소분을 수취 가능한 현금이나 확정된 외부 채권으로 자동 분개하지 않는다"), 정산 계약 §0.3(그 줄 할인 규칙을 정산 정책으로 자동 가져오지 않는다 → 이 노트가 **명시적으로 채택**한다는 점을 적는다), `FINANCE_COMPLETION_DESIGN_KO.md` §4.5("전액 1회 fixture 재분류나 부분 환불의 누적 합을 근거로 자동 환수·상계를 만들지 않는다"). 그래서 기지급분의 부담은 항상 `recovery_due`(제안)이고, 누적 부분 환불은 전액으로 자동 재분류되지 않으며, 수익 참여 조정의 초과 수령분도 회수채권이다.
- **Capital 여신과의 정합.** `CAPITAL_FINANCIAL_TERMS.md` `collateral_execution.mechanics`("수익자 payee에게 배분된 현금을 선지급에 먼저 충당")와 §7("정산 정책 결정이 나오면 그 순서에 맞춰 재확인"). 이 노트가 그 "수익자에게 배분된 현금"을 **클래스 ② 거래상대 몫 줄에 배정된 현금**으로 정의하고, 그 현금의 사후 적용 순서(선지급 상계 → 채권 슬라이스 → 수익 참여 → 지급)를 정했다. 주최자 부담 환불은 `additional_margin.eligible_face`를 줄이고 열린 환불 액면은 F04 `REFUND_OBLIGATION_OPEN`으로 새 인출을 막는다(`docs/contracts/CREDIT_ADVANCE_F04.md` §2·§3). 채권 매입은 `CAPITAL_ACCOUNTS_TAX_LEGAL.md` `claim_trading_cap03`(V1 `NOT_OFFERED`, 목표 = 상환청구권 있는 매입 = 대부)와 같은 형태다.
- **토큰 계층(TL)과 환불·차지백 창.** `docs/blueprints/optional-native-token-v1/README.md` §3.1(여섯 자산 분리), §7.1(고객 예치금·주최자 정산금·환불 준비금은 토큰 지지 금지, TK-4), §9.1·§9.2(보상은 `HELD` → 환불·차지백 창이 끝난 뒤 `ELIGIBLE`, 양도 가능 지급은 차지백 기간 뒤), `docs/adr/0002-token-layer-scope-and-limits.md`. 수익 참여의 기준 수익에서 환불 준비금·고객 예치금을 제외하고, 조정 창 90일과 RC4 차지백 클래스를 TL-3 보상 상태기계의 `HELD` 기간 입력 후보로 둔다. 토큰은 어느 항목에서도 수취인·담보·대가가 아니다.
- **AI 위임 경계.** `DEVELOPMENT_PLAN.md` §14, `docs/contracts/AI_DELEGATION_AUTHORITY.md` §3·§5(QUERY/PROPOSE만, `refund_execution`·`pay` 거부), `docs/RUNTIME_ARCHITECTURE_S062.md` §10(역사: `executionAuthorized=false`), `CAPITAL_UPSTREAM_BINDING.md` `ai_agent_grant_action_permit`. 환불 사유 클래스 배정·회수채권 실행·수익 참여 회수·슬라이스 매입은 모두 사람 명령이고 AI는 클래스와 금액을 **제안**만 한다. 모든 규칙은 결정론적 계산이라 재생 가능하다.
- **5·6·7단계와 export.** `DEVELOPMENT_PLAN.md` §5(6단계 합성 금액 참조 모델, 7단계 인증 export) §13, 로드맵 R-10·R-11, `RUNTIME_ARCHITECTURE_S062.md` §2(역사: Order/Allocation/Obligation/RefundReservation 분리). 배정 결정마다 `policy_version`·`policy_digest`·`source_cut`·`sim_day`를 붙여 `k-stage6-economics-reference`와 `fin-multi-payee-refund-proof` 벡터로 바로 넘길 수 있게 했다.
- **역사 청사진의 안전 요구.** `BLUEPRINT_20260914.md` §3(제작자금과 티켓 결제금은 별도 자금 흐름), §5 `RefundCase`(사유·대상 거래·수혜자·경로·**부담 주체**)·`Obligation/LedgerEntry`(배분 예정·지급 완료·회수채권·환불 의무 분리), §10(금융 근거 항목 분리). 현행 승인이 아니지만 안전 요구는 폐기되지 않았다. 환불 사유 클래스·부담 주체·수혜자·경로를 `RefundCase` 모양으로 정의했다.
- **"포부"의 해석.** 로드맵 §0("사람의 결정이 꼭 필요한 곳 말고는 멈추지 않는다")과 위임. 여섯 항목 모두 값을 정했다. 다만 소비자보호·PG 약관·채권거래·미청구 자금의 법적 결론은 전문가 몫이라 네 항목에 검토자와 검토 항목을 붙였고, 고정 FSM이 표현하지 못하는 다섯 항목은 그림자 계산과 upstream FSM 변경 요청으로 분리했다.

## 3. 항목별 결정

각 항목은 값, 근거, 검토한 대안, 게이트와 FSM 결합 순이다. 공통 제약: 고정 `SettlementMachine`은 `initiate`(정책 `PRIMARY_FEE_BPS`·`fee_bps`·`residual_payee`·`fee_payee`), `commit`/`observe_statement`(명세서 성분 등식), `distribute(order)`, `bind_refund(amount, beneficiary_role, reason)`, `observe_mock_cancel_acceptance`만 받는다. 환불 액면이 열려 있고 전액 재분류가 아니면 `DISTRIBUTION_BLOCKED_REFUND_BEARER_UNDEFINED`, 첫 수락 순서 뒤 다른 순서는 `DISTRIBUTION_ORDER_FROZEN`, `funds_executed`·`bank_debit_observed`·`external_return_closed`·`legal_debtor_bound`는 항상 거짓이다. 이 노트는 그 어떤 것도 바꾸지 않는다.

### 3.1 allocation_order (CAP-02, CAP-05) — fsm_expressible: true

- **값.** `CAPITAL-ALLOC-V1`. 부족 현금(확인 현금 < 의무 액면 합)의 배정은 **클래스 우선순위 → 클래스 안 액면 비례**다. 클래스(순서 있음): ① `PROTECTED_THIRD_PARTY`(공연자·공연장·권리자·대행사 등 계약상 통과 줄; 고정 2수취인 정책에는 없음) ② `COUNTERPARTY_PROCEEDS`(1차 `residual_payee`=주최자 잔여, 리셀 `seller_due`) ③ `ECOSYSTEM_ROYALTY`(리셀 `organizer_due`, 미래 공연자 로열티) ④ `PLATFORM_FEE`(1차 `fee_payee`=플랫폼, 리셀 `platform_due`). 클래스 안에서는 `q_i = floor(C × f_i / F)`(C = 그 클래스에 남은 현금, f_i = 줄의 미지급 잔액, F = 그 합), 잔여 R은 소수부가 큰 줄부터 1원씩, 동점은 수취인 라벨 오름차순. **도출된 명시 순서** = 현재 의무 수취인을 `(클래스, 라벨 오름차순)`으로 정렬한 목록이며, 이것을 고정 FSM `distribute(order=…)`에 넘긴다. 2수취인 fixture 정책에서는 `["organizer", "platform"]`이다(클래스마다 수취인이 하나면 FSM의 순차 채움 = 클래스 순서). 첫 수락 `distribute`가 순서를 동결하고(FSM 규칙), 오버레이는 이 표의 `policy_digest`(sha256)를 청구 옆에 기록한다. **거래상대 몫의 사후 적용 순서**(FSM 밖, 오버레이): 선지급 상계(`CAPITAL-TERMS-V1`) → 채권 슬라이스(§3.5) → 수익 참여(§3.4) → 주최자 지급 의도(§3.6).
- **근거.** (1) 부족 현금은 대개 PG 차감·보류·정산 지연에서 오며, **플랫폼이 자기 수수료를 거래상대보다 먼저 가져가는 구조는 주최자 신뢰를 깎는다.** KIX의 포부는 주최자와 팬이 믿는 정산 계층이므로 플랫폼 수수료를 후순위로 둔다. (2) Capital 선지급의 1차 회수가 "거래상대 몫에 배정된 현금의 상계"이므로, 거래상대 몫을 먼저 채우는 순서가 **신용 위험을 줄이고** 두 결정을 한 방향으로 맞춘다. (3) 보호 제3자 줄을 최상위에 둔 것은 공연자·공연장 통과 대금이 계약상 플랫폼·주최자보다 앞서는 관행을 작업 가정으로 둔 것이다. (4) 클래스 안 비례는 §0.3 원칙(정수·사전 고정·결정론)과 `FINANCE` §4.3 식 그대로다.
- **대안.** (a) 플랫폼 우선(fixture `shortfall-platform` 순서): 신용 위험·신뢰 모두 불리해 기각. (b) 전 줄 비례만: 보호 제3자·플랫폼 후순위 신호를 못 내고 고정 FSM이 표현 못 해 기각. (c) 호출자 자유 순서 유지: `FINANCE` §4.2가 "운영자가 사후 순서를 바꾸지 않는다"고 적어 기각.
- **게이트와 FSM 결합.** `fsm_expressible: true` — 명시 순서 목록으로 표현된다. 단 (i) 한 클래스에 두 수취인 이상(비례 배정), (ii) 리셀 세 줄, (iii) 보호 제3자 줄은 **upstream FSM 변경**(복수 수취인 정책 종류)이 필요하다. 아홉 fixture와 두 시험 순서는 그대로 비교 fixture다. V1 도출 순서가 `shortfall-organizer` fixture의 순서와 일치하더라도 그 fixture가 운영 정책이 되는 것은 아니며, `policy-simulator`는 **도출된 순서**를 별도 시나리오(`derived-order-v1`)로 추가하고 기존 fixture 라벨("어느 순서도 제품 기본 정책으로 채택하지 않습니다")을 유지한다.

### 3.2 refund_bearer (CAP-05, CAP-06) — fsm_expressible: false (requires upstream FSM change)

- **값.** `CAPITAL-REFUND-BEARER-V1`. 환불 의무 R(청구에 묶인 `bind_refund` 금액, 누적 ≤ gross)의 **부담은 사유 클래스가 정한다.** RC1 `BUYER_WITHIN_POLICY`(정책 내 구매자 취소, 주문 줄 전액 역분개 `FROZEN_LINE_PRICE_FULL_REVERSAL_V1`): 전 줄 비례 역분개 `floor(R × face_i / gross)` + largest remainder; 구매자 부담 취소 수수료는 예매 계약의 별도 표(이 규칙 밖). RC2 `EVENT_CANCELLED_OR_ORGANIZER_FAULT`: 주최자 잔여 줄 먼저 액면까지 → 플랫폼 수수료 줄; R = gross이면 고정 FSM의 `FIXTURE_FULL_GROSS_RECLASS`와 같은 결과(전 줄 `cancelled_unpaid`, 기배정분 `recovery_due`). RC3 `PLATFORM_FAULT`(포착 뒤 발행 실패, 중복 청구, 시스템 오류): 플랫폼 100 % — 플랫폼 수수료 줄 먼저, 초과분은 `PLATFORM_PROTOCOL_REVENUE_POOL`의 플랫폼 의무이며 주최자 줄에 손대지 않음. RC4 `PROVIDER_CHARGEBACK_OR_DISPUTE`: RC2와 같되 분쟁이 플랫폼 귀책으로 판정되면 RC3(작업 가정; 가맹점 지위·PG의 차지백 귀속은 토스 프로파일 미확인). RC5 `RESALE_UNWIND`: §3.3. **줄 적용**: 미지급분은 `cancelled_unpaid`로 잔액 감소, 기지급분은 `recovery_due`(회수는 제안, 같은 수취인의 이후 배정 상계가 1단계, AI는 제안만). **누적**: 클래스별로 청구에 누적하고, 부분 환불 합이 gross에 닿아도 전액으로 자동 재분류하지 않는다(FSM 규칙 유지). **클래스 배정 권한**: 증거(취소 통지·분쟁 기록)를 가진 운영자, AI는 제안; 사유 라벨 형식 `RC<n>:<evidence_ref>`. **여신 영향**: 주최자 부담 환불은 `eligible_face`를 줄이고(마진콜 평가), 열린 환불 액면은 새 인출을 막는다(F04 `REFUND_OBLIGATION_OPEN`).
- **근거.** F03는 "누가 그 환불을 부담하는지는 미정"이고 F04는 그동안 메모를 막는다. 사유별 부담자 표가 없으면 선지급·수익 참여·채권 매입 어느 것도 환불 뒤 산술을 닫을 수 없다. RC2에서 전액 환불이 고정 FSM의 전액 재분류와 **같은 결과**가 되도록 설계해, 그림자 계산과 fixture가 어긋나지 않는다. 플랫폼 귀책을 플랫폼 100 %로 둔 것은 주최자에게 시스템 위험을 넘기지 않겠다는 플랫폼의 약속이다.
- **대안.** 전 사유 비례: 공연 취소에서 플랫폼이 주최자와 같은 비율로 부담해 귀책과 어긋나 기각. 전 사유 주최자 100 %: 플랫폼 귀책·구매자 정책 내 환불에 부당해 기각. UNDETERMINED 유지: 위임 범위이고 세 금융 항목의 전제라 기각(법적 결론은 검토 항목으로 분리).
- **게이트와 FSM 결합.** `fsm_expressible: false`. 고정 FSM은 `reason` 라벨을 저장만 하고 `refund_bearer_policy = UNDEFINED`·배정 정지를 유지한다. `policy-simulator`는 일회용 복제 장부에서 클래스별 역분개를 **`SHADOW_NOT_APPLIED`** 로 계산해 보여 준다. upstream FSM 변경 요청(`DECISION_REQUIRED · Astra`): `bind_refund`에 사유 클래스와 부담 규칙 적용, 배정 정지 해제 조건.
- **기초.** WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW — 소비자 환불 규정, 가맹점 지위와 차지백 귀속(토스), 플랫폼 귀책의 계약 정의.

### 3.3 resale_prior_contract_cancel_burden (CAP-06) — fsm_expressible: false (requires upstream FSM change)

- **값.** `CAPITAL-RESALE-UNWIND-V1`, 원칙 **`LATEST_TRADE_ONLY_NO_CHAIN_WALK`**. 입력: `P_p`(1차 총액), `P_r`(최신 수락 리셀 금액, `resale_cap` 이하), 최신 거래의 세 줄 `seller_due`·`organizer_due`·`platform_due`(Move `accept_sale` u128 바닥 나눗셈). **RU1 이전 뒤 공연 취소(RC2 클래스)**: 현재 보유자의 자격 = `min(P_r, P_p + organizer_due + platform_due)`. 재원 순서: 1차 청구의 `P_p` 환불(수혜자 = 현재 보유자, 부담 RC2: 주최자 줄 → 플랫폼 수수료 줄) → 최신 거래 `organizer_due` 역분개 → 최신 거래 `platform_due` 역분개. **판매자의 `seller_due`는 회수하지 않는다.** 할인 리셀(`P_r < P_p`)이면 보유자 `P_r`, 최신 판매자가 `P_p − P_r`을 1차 환불에서 받고 리셀 줄은 역분개하지 않는다. 자격을 넘는 프리미엄은 보유자의 시장 위험이며 리스팅 때 공개한다. **RU2 결제 기록 뒤·이전 전 리스팅 취소**(`ResaleMachine` `PAYMENT_NOTED` + `cancel_listing` = `COMPENSATION_UNDEFINED`): 예비 구매자에게 `P_r` 전액, 기록된 리셀 결제의 세 줄 모두 역분개, 이전 없음, V1 위약금 없음. **RU3 이전 뒤 리셀 결제 차지백**: 보유자 자격 없음(권리는 Protocol 권위), 부담 순서 `seller_due` 회수채권 → `organizer_due` → `platform_due`. **과거 거래**는 어떤 경우에도 다시 열지 않는다. 반올림은 largest remainder·라벨 오름차순.
  합성 예시(상품 값 아님): `P_p` 100,000, 1차 수수료 500 bps(잔여 95,000·수수료 5,000), `P_r` 130,000, `organizer_bps` 500(6,500), `platform_bps` 500(6,500), `seller_due` 117,000. RU1 보유자 수령 = min(130,000, 113,000) = **113,000** = 1차 주최자 줄 95,000 + 1차 플랫폼 줄 5,000 + 리셀 로열티 6,500 + 리셀 플랫폼 수수료 6,500. 판매자 117,000 유지, 보유자 시장 위험 17,000. 할인 예시 `P_r` 80,000: 보유자 80,000, 판매자 20,000, 리셀 줄 역분개 0.
- **근거.** 권리는 체인 객체이고 **1차 액면의 환불 자격이 그 객체에 붙어 보유자와 함께 이동**하면, 사슬 길이와 무관하게 O(1)로 닫히고 과거 구매자가 계속 참여하지 않는다(마스터플랜 §7). 공연 취소에서 주최자와 플랫폼이 리셀 로열티·수수료를 포기하는 것은 "취소된 공연에서 생태계가 이익을 남기지 않는다"는 포부의 표현이고, 판매자 회수를 두지 않는 것은 시장에서 판 사람에게 사후 소급 의무를 만들지 않기 위함이다. RU2는 거래가 완결되지 않았으므로 전액 원상복구가 자연스럽다. RU3는 돈만 다루고 권리는 건드리지 않는 모델 1 경계다.
- **대안.** `FULL_CHAIN_UNWIND`(모든 거래 역분개): 사슬 길이에 비례하는 의무 생성, 과거 구매자 참여, BLUEPRINT §7이 금지한 자동 전액 환불이라 기각. `LATEST_TRADE_UNWIND`(최신 거래만 전액 역분개, 판매자 `seller_due` 회수): 판매자가 1차 대금 없이 권리도 잃어 불공정, 체인 `last_amount`에 끌려 주최자가 받은 적 없는 프리미엄을 부담해 기각. 보유자에게 `P_p`만: 로열티·수수료를 취소 공연에서 보유하는 것이 포부와 어긋나 기각.
- **게이트와 FSM 결합.** `fsm_expressible: false`. 고정 FSM에는 리셀 청구 종류·세 줄 분할·1차 청구와 거래 사슬의 연결이 없고, `ResaleMachine`에는 보상 레코드가 없다. `policy-simulator`는 합성 리셀 사슬을 그림자 장부에서 계산한다. upstream FSM 변경 요청: 리셀 청구 종류(3수취인), 청구 간 링크(right_id·trade_id), `COMPENSATION_UNDEFINED` 보상 레코드, 환불 수혜자 = 현재 보유자 라벨 바인딩.
- **기초.** WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW — 리셀 약관의 소비자보호(프리미엄 미회수 고지), 중개자 책임, 차지백 귀속.

### 3.4 revenue_participation (CAP-02) — fsm_expressible: false (requires upstream FSM change)

- **값.** `CAPITAL-REVSHARE-V1`. **참여자 V1** = KIX Capital 플랫폼 법인 자신(제작자금 참여 계약의 상대는 주최자 법인); 제3자 참여자·투자자 슬라이스는 `NOT_IN_V1`(증권성·온투업 검토 뒤). **투입액 F** = 참여 계약으로 공급한 금액(합성, `funds_executed=false`). **기준 수익 B** = 그 공연 청구들의 **클래스 ② 거래상대 몫 줄에 배정된 현금**(1차 주최자 잔여 + 리셀 `organizer_due`) − 주최자 부담 환불(RC2/RC4의 `recovery_due`·`cancelled_unpaid`). 플랫폼 수수료, 보호 제3자 줄, 명세서 `fee`·`tax`·`held`, 환불 준비금, 고객 예치금은 B에 넣지 않는다(TK-4). **비율** 2,000 bps of B. **상한** 누적 수령 ≤ F × 15,000 bps(1.5×). **허들·우선수익** 없음(V1). **회수 순서(거래상대 몫 안)**: 선지급 상계 → 채권 슬라이스 → 수익 참여 → 주최자 지급. **조정**: 마지막 명세서 관측 뒤 90일 창 안의 주최자 부담 환불은 B를 소급 감소시키고 초과 수령분은 참여자의 `recovery_due`(회수채권, 제안만); 창 안의 늦은 현금은 B를 늘려 다음 배치에 지급; 창 밖의 사실은 기록만. **종료** = 상한 도달 또는 창 종료 중 빠른 쪽. 반올림은 게시 시 1원 내림·나머지 이월. 5천만 원 초과 지급은 2인 원칙, AI는 제안만.
- **근거.** `PROTOCOL_MASTERPLAN_V2.md` §7의 "수익 참여·배분 | 기준 수익 정의·회수 순서·비율/상한·정산 조정"을 네 값으로 닫았다. B를 거래상대 몫으로 한정한 것은 플랫폼 수수료·제3자 통과 대금·고객 자금에 참여하지 않는다는 자금 풀 분리(토큰 청사진 §7.1, BLUEPRINT §3)다. 채무성 청구(선지급·슬라이스)를 지분성 청구(참여)보다 앞세워 `CAPITAL-TERMS-V1`의 회수 폭포와 같은 방향이다. 1.5× 상한은 공연 제작 참여의 보수적 포부 값이며 데이터가 생기면 재검토한다.
- **대안.** 총매출 기준: 환불·PG 차감·제3자 통과 대금을 포함해 과대 참여, 기각. 무상한: 손실 100 % 플랫폼 부담(`CAPITAL-TERMS-V1`)과 비대칭이라 기각. 참여를 선지급보다 선순위: 담보형 회수를 해쳐 기각.
- **게이트와 FSM 결합.** `fsm_expressible: false`. 고정 정책에는 참여자 수취인·기준 수익·상한이 없다. `policy-simulator`는 그림자 계산. upstream FSM 변경 요청: 복수 수취인 정책 종류에 참여 줄과 상한 카운터.
- **기초.** WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW — 수익 참여 계약의 법적 성격(투자계약·대부·공동사업), 회계 처리, 세무(원천징수).

### 3.5 claim_purchase (CAP-03) — fsm_expressible: false (requires upstream FSM change)

- **값.** `CAPITAL-CLAIM-PURCHASE-V1`. **제공 상태** V1 `SIMULATION_ONLY_NOT_OFFERED`(`CAPITAL-LICENCE-ROUTE-V1 claim_trading_cap03.v1 = NOT_OFFERED` 그대로). **형태** = 상환청구권 있는 매입, 같은 등록 아래 대부로 취급(작업 가정). **단위** = 청구 슬라이스 `(claim_id, payee line, slice_face)`, `COMMITTED` 청구·열린 환불 없음. **수량**: 슬라이스 액면 ≤ 그 줄의 미지급 잔액 − 열린 환불 액면; 등급별 선취율 T1 8,500 bps·T2 0(무결합 청구는 매입 불가); 줄당 열린 슬라이스 하나; 집계 상한(건당 5억·수익자 20억·포트폴리오 200억 원)은 선지급과 **공유**. **보유자** V1 = KIX Capital 대주 법인만; 슬라이스 등록부(미래 `cr-02`)가 `(claim_id, payee)` 유일성을 강제하고 중복 슬라이스를 거절; 제3자 보유자·토큰화 슬라이스 `NOT_IN_V1`. **대가** = 액면 − 할인, 할인 = `floor(slice_face × all_in_bps_annual × expected_days / (10000 × 365))`, 금리는 `CAPITAL-TERMS-V1` 등급 금리(T1 700 bps/yr), 예상 일수는 그 기간 규칙; 지급은 합성 메모. **우선순위**: 그 줄에 배정된 현금에서 보유자가 슬라이스 액면까지 먼저(선지급 상계와 같은 단계), 복수 보유자는 줄 안 pari passu(V1 아님), 그 줄이 부담하는 환불 역분개는 주최자 보유 잔여분이 먼저 흡수하고 그 뒤 슬라이스가 손상되며 부족분은 **상환청구**(주최자 책임) → `CAPITAL-TERMS-V1` 회수 폭포. **완전성**: 실자금은 C2 이상. **절대 금지**: 환불 준비금·플랫폼 수수료 줄·보호 제3자 줄 매입, V1 비소구 진정매매, 관람권 담보.
- **근거.** `PROTOCOL_MASTERPLAN_V2.md` §7 "정산채권 양도·매입 | 원 채권·배정량·보유자·우선순위·대가·회수"를 모두 값으로 닫되, 제공은 선행 결정대로 V1에서 끄고 시뮬레이터가 **모양을 먼저 검증**하게 한다. 선취율·상한·금리를 선지급과 공유하면 두 상품이 같은 차입기초를 이중으로 쓰지 못한다(F04 §0 "외부에서 이미 양도·담보된 채권", 마스터플랜 §7 "초과 배정·담보 차단").
- **대안.** 비소구 매입 V1: 증권성·추심업 미검토라 기각. 슬라이스 선순위를 환불보다 앞: 구매자 환불이 투자자 뒤로 밀려 소비자보호와 어긋나 기각. UNDETERMINED: 위임이 설계 결정을 요구하고 제공 여부는 이미 분리돼 있어 기각.
- **게이트와 FSM 결합.** `fsm_expressible: false`. 고정 FSM에는 의무 줄의 양도·보유자 필드가 없고 F04 `note_advance`는 예약이지 양도가 아니다. `policy-simulator`는 그림자 등록부로 계산. upstream FSM 변경 요청: 줄별 `holder`와 양도 명령, 등록부 유일성.
- **기초.** WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW — 대부 vs 팩토링, 채권양도 대항요건, 추심업, 증권성.

### 3.6 residual_and_late_cash (CAP-05, CAP-06) — fsm_expressible: false (requires upstream FSM change)

- **값.** `CAPITAL-RESIDUAL-V1`. **나눗셈 잔여**: largest remainder·동점 라벨 오름차순, 계산 전에 고정·digest. 2수취인 1차 분할에서는 고정 FSM의 `fee = floor`, `residual = gross − fee`가 이미 잔여를 잔여 수취인(주최자)에게 주므로 V1 결과가 같다; N수취인은 FSM 변경 필요. **미배정 현금 상태**(순서 있음): UC1 `FROZEN_ORDER_CONTINUATION` — 의무가 남아 있으면 동결 순서로 계속 배정(FSM 동작 그대로). UC2 `REFUND_FUNDING_SUSPENSE` — 청구에 `refund_outstanding` 또는 `pg_adjustment_outstanding`이 있으면 현금을 환불 재원으로 보류하고 수취인에게 배정하지 않으며 제공자 상계 시 `pg_adjustment_outstanding`과 상쇄. UC3 `LATE_CASH_AFTER_FULL_RECLASS` — 전액 재분류 뒤 늦은 현금은 180일 보류 뒤 운영자 명령으로만 제공자 반환 또는 같은 수취인의 `recovery_due` 상계. UC4 `OVERPAYMENT` — 확인 현금이 줄 액면 합을 넘으면 명세서 정정·제공자 반환, 수취인 배정 금지. **보류 뒤**: 운영자 결정 필요, 미청구 자금·공탁은 검토 항목, 시뮬레이션은 무기한 보존(`RETAIN_ALL`). **종결된 선지급**(`CLOSED`/`DEFAULTED`)은 늦은 현금으로 다시 열지 않는다(`CAPITAL-TERMS-V1`). **지급 의도**: 수락된 `distribute`마다 수취인별 `PAYOUT_INTENT` 메모, 명세서 관측 D+1 영업일 배치 목표(합성 시계), 실행은 Capital 밖(미래 `cr-05`/외부 adapter), `funds_executed=false`. **Holdback**: V1 0 bps(`refund_reserve_bps` 필드 예약); 공연 취소 위험은 RC2 부담 규칙과 선지급 haircut이 덮는다.
- **근거.** 정산 계약 §0.3·§7("세금·보류·조정 잔액의 해제와 실제 회수", "잔여 단위 우선순위")과 fixture `late-cash`("취소된 의무를 늦은 현금으로 다시 배정하지 않는다")를 그대로 지키면서, 그 현금이 **어디에 속하는지**를 상태로 정했다. 환불 재원 보류를 수취인 배정보다 앞세운 것은 구매자 환불이 생태계 지급보다 앞선다는 소비자보호 작업 가정이다.
- **대안.** 늦은 현금을 동결 순서로 수취인에게 배정: 취소된 의무에 돈을 보내는 것이라 기각(fixture와 충돌). 보류 없이 즉시 제공자 반환: 환불 미이행이 남아 있을 때 재원을 잃어 기각. Holdback bps > 0: 현금이 이미 관측된 T1 청구에 이중 보수적이라 V1 0.
- **게이트와 FSM 결합.** `fsm_expressible: false`. 고정 FSM에는 보류·반환·지급 의도 명령이 없고 늦은 현금은 `undistributed_cash`로만 남는다. `policy-simulator`는 상태 라벨을 그림자로 붙인다. upstream FSM 변경 요청: 보류/반환/지급 의도 명령.
- **기초.** PRODUCT_DECISION (미청구 자금·공탁·지급 시점 약관은 검토 항목).

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "settlement-policy-decision",
  "decided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
  "date": "2026-10-09",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "scope": "KIX-CAPITAL simulation and product design only; not an offer; no real money; production NOT_AUTHORIZED; legal, tax, accounting, licensing and consumer-protection content are working assumptions pending professional review; no upstream contract is claimed adopted without a real upstream receipt",
  "delegation": "2026-10-08 18:25 KST JunTae Park delegated financial terms, settlement policy, upstream binding and accounts/tax/legal to Fable with the instruction to proceed with the grand ambition in mind",
  "policy_version": "CAPITAL-SETTLEMENT-POLICY-V1",
  "currency": "KRW",
  "units": {
    "money": "KRW integer, minor unit 1 KRW, pinned FSM MONEY_MAX 1000000000000 (fixture bound)",
    "rate": "bps = 1/10000",
    "time": "sim_day integer kept by the overlay (CAPITAL-TERMS-V1); the pinned settlement journal carries no time"
  },
  "bases": {
    "capital_main": "82d6028",
    "kix_protocol_main": "c2cde86e21a6e5ba6f24a56548636db6d0a34c6f",
    "vendor_pin_commit": "7481b0e16ce9b903abbffa62249bb91cd9e63cfe",
    "vendor_sha256": {
      "settlement_f01_f03/settlement_fsm.py": "c6d7ae79fe0c3289def2d3c195212247d1ab2c2e913feb80612fcd9ff64c77c8",
      "settlement_f01_f03/mock_settlement.py": "9e9c25571fdbe7b90b7539df2cc71afaee83d81905293dc56dbeb9faaf864170",
      "credit_advance_f04/credit_fsm.py": "f4f6b3698dd848538d2efa10b276cb33659eb4877fcbea0feb7429b28456491b",
      "credit_advance_f04/mock_credit.py": "5e75fcc76fb0857f671b2fa33ca0fc851e9d676d4b5db8f357393367bc725d95",
      "credit_advance_f04/test_mock_credit.py": "75cd55f773e3e71553392f674d1595af66cf82560565cc5603bf829a9a29e99d"
    },
    "prior_capital_decisions": [
      "docs/decisions/CAPITAL_FINANCIAL_TERMS.md (CAPITAL-TERMS-V1, 2026-10-08): collateral_execution primary = set-off against beneficiary settlement distribution; caps; tiers; reserve pools",
      "docs/decisions/CAPITAL_UPSTREAM_BINDING.md (2026-10-09): SettlementPolicyPort DEFERRED, expected upstream contract settlement-policy-deepening plus fin-multi-payee-refund-proof vectors",
      "docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md (2026-10-09): claim_trading_cap03 v1 NOT_OFFERED and recourse purchase treated as lending; memo accounts 9300 refund exposure and 9400 recovery due; RETAIN_ALL simulation retention"
    ],
    "upstream_status_unchanged": "kix-protocol docs/contracts/SETTLEMENT_DISTRIBUTION_F01_F03.md sections 0.3, 4, 5 and 7 keep remainder priority, refund bearer, waterfall, resale split, holds and inter-claim set-off UNDETERMINED or DECISION_REQUIRED upstream; this note supplies Capital-local provisional values and input candidates only",
    "fsm_policy_inputs_today": "the pinned SettlementMachine accepts only an explicit distribution order list (distribute(order=[...])) as a policy input; PRIMARY_FEE_BPS two-payee policy, refund amount/beneficiary/reason labels and statement components are data inputs, not policy choices",
    "fixtures_untouched": "nine F01-F03 scenarios in capital/scenarios.py, both test allocation orders (platform-first and organizer-first) and the 500 bps fixture policy remain byte-identical comparison fixtures labelled not an operating policy"
  },
  "fsm_expressibility_summary": {
    "allocation_order": true,
    "refund_bearer": false,
    "resale_prior_contract_cancel_burden": false,
    "revenue_participation": false,
    "claim_purchase": false,
    "residual_and_late_cash": false,
    "meaning_of_false": "requires upstream FSM change; policy-simulator computes the item on a disposable copy and labels the result SHADOW_NOT_APPLIED; the pinned FSM behaviour and its refusal codes stay in force"
  },
  "post_allocation_application_of_counterparty_proceeds_ordered": [
    "CAPITAL_ADVANCE_SETOFF (CAPITAL-TERMS-V1 collateral_execution.primary; interest then principal)",
    "CLAIM_PURCHASE_SLICE (claim_purchase; recourse purchase, economically the same step as set-off)",
    "REVENUE_PARTICIPATION (revenue_participation)",
    "COUNTERPARTY_PAYOUT_INTENT (residual_and_late_cash.payout_intent)"
  ],
  "entries": {
    "allocation_order": {
      "status": "ADOPTED",
      "value": {
        "policy_version": "CAPITAL-ALLOC-V1",
        "method": "CLASS_PRIORITY_THEN_PRO_RATA_LARGEST_REMAINDER",
        "class_table_ordered": [
          {"class": 1, "id": "PROTECTED_THIRD_PARTY", "payee_kinds": ["performer", "venue", "rights_holder", "agency"], "note": "contractual pass-through lines; absent from the pinned two-payee policy"},
          {"class": 2, "id": "COUNTERPARTY_PROCEEDS", "payee_kinds": ["primary residual_payee (organizer)", "resale seller_due"]},
          {"class": 3, "id": "ECOSYSTEM_ROYALTY", "payee_kinds": ["resale organizer_due", "future performer royalty"]},
          {"class": 4, "id": "PLATFORM_FEE", "payee_kinds": ["primary fee_payee (platform)", "resale platform_due"]}
        ],
        "within_class": "q_i = floor(C * f_i / F) where C is cash remaining for the class, f_i the line outstanding, F their sum; remainder R assigned one KRW each to the largest fractional parts; ties by ascending payee label",
        "derived_explicit_order_rule": "sort current obligation payees by (class, label ascending) and pass that list to the pinned distribute(order=...); sequential fill in the pinned FSM equals class order whenever each class holds at most one payee",
        "derived_order_for_pinned_two_payee_policy": ["organizer", "platform"],
        "freeze": "the first accepted distribute freezes the order per claim (pinned DISTRIBUTION_ORDER_FROZEN); the overlay records policy_digest = sha256 of this class table beside the claim before the first distribute",
        "late_cash": "cash arriving after the freeze continues in the frozen order (pinned behaviour) subject to residual_and_late_cash states",
        "never": ["operator re-ordering after the freeze", "float arithmetic", "allocating beyond a line outstanding", "allocating to cancelled_unpaid lines", "a platform line ahead of a counterparty line in the same claim"]
      },
      "fsm_expressible": true,
      "fsm_binding": "expressible today as the explicit order list; within-class pro-rata, more than one payee per class, protected third-party lines and resale three-line claims require upstream FSM change (multi-payee policy kind)",
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-09",
      "cap_rows": ["CAP-02", "CAP-05"],
      "rationale": "Shortfall cash should reach counterparties before the platform takes its fee: it is the trust signal of a settlement layer organizers and fans can rely on, and it enlarges the set-off base that CAPITAL-TERMS-V1 uses as the first recovery step for advances; protected third-party pass-through lines sit first as a contractual working assumption; within-class pro-rata with largest remainder follows the settlement contract section 0.3 principle and the FINANCE design section 4.3 formula, and the whole table is frozen and digested before the first distribute.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "alternatives_rejected": ["platform-first order (fixture shortfall-platform)", "pro-rata only across all lines", "caller-chosen order"],
      "consumer": "policy-simulator (derived-order-v1 scenario beside the untouched nine fixtures) / SettlementPolicyPort; upstream settlement-policy-deepening and fin-multi-payee-refund-proof input candidate",
      "revisit_triggers": ["settlement-policy-deepening user merge with a different order", "first protected third-party payee in a producer tuple", "loss or dispute data by class"]
    },
    "refund_bearer": {
      "status": "ADOPTED",
      "value": {
        "policy_version": "CAPITAL-REFUND-BEARER-V1",
        "unit": "refund obligation R bound on a claim via bind_refund; cumulative R <= gross (pinned REFUND_CEILING)",
        "reason_classes_ordered": [
          {"id": "RC1_BUYER_WITHIN_POLICY", "examples": ["buyer cancellation inside the event refund window", "order-line full reversal FROZEN_LINE_PRICE_FULL_REVERSAL_V1"], "bearer": "PRO_RATA_ALL_LINES", "mechanics": "each obligation line reversed by floor(R * face_i / gross) plus largest-remainder, ties ascending label; a buyer-paid cancellation fee is a separate booking-contract schedule outside this rule"},
          {"id": "RC2_EVENT_CANCELLED_OR_ORGANIZER_FAULT", "bearer": "ORGANIZER_FIRST_THEN_PLATFORM", "mechanics": "organizer residual line reversed first up to its face, then the platform fee line; R == gross reproduces the pinned FIXTURE_FULL_GROSS_RECLASS outcome (all lines cancelled_unpaid, distributed becomes recovery_due)"},
          {"id": "RC3_PLATFORM_FAULT", "examples": ["issuance failure after capture", "duplicate charge", "platform system error"], "bearer": "PLATFORM_100", "mechanics": "platform fee line reversed first; any excess over the platform fee line is a platform obligation funded from PLATFORM_PROTOCOL_REVENUE_POOL and never from organizer lines"},
          {"id": "RC4_PROVIDER_CHARGEBACK_OR_DISPUTE", "bearer": "ORGANIZER_FIRST_THEN_PLATFORM_WORKING_ASSUMPTION", "mechanics": "as RC2 unless the dispute is adjudicated as platform fault (then RC3); merchant-of-record status and PG chargeback allocation are Toss profile unknowns", "review": true},
          {"id": "RC5_RESALE_UNWIND", "bearer": "see resale_prior_contract_cancel_burden"}
        ],
        "application_to_lines": {
          "unpaid_part": "reduces the bearer line outstanding via cancelled_unpaid",
          "paid_part": "becomes recovery_due on the bearer line; recovery is proposed never auto-executed; first recovery step is set-off against the same payee later distributions; AI proposes only"
        },
        "partial_refund_accumulation": "classes accumulate per claim; reaching gross through partial refunds never auto-reclassifies as a full refund (pinned rule kept)",
        "class_assignment_authority": "human operator with evidence (cancellation notice, dispute record); AI may propose a class; reason label format RC<n>:<evidence_ref>",
        "effect_on_capital_credit": "organizer-borne refunds reduce eligible_face in CAPITAL-TERMS-V1 additional_margin; any open refund face still blocks a new draw (F04 REFUND_OBLIGATION_OPEN)",
        "rounding": "largest remainder, ties ascending payee label",
        "shadow_only_in_pinned_fsm": "the pinned FSM keeps refund_bearer_policy UNDEFINED and DISTRIBUTION_BLOCKED_REFUND_BEARER_UNDEFINED; the simulator computes the bearer split on a disposable copy labelled SHADOW_NOT_APPLIED"
      },
      "fsm_expressible": false,
      "fsm_binding": "requires upstream FSM change: bind_refund would need a reason class and bearer application, and a defined condition for lifting the distribution block; until then shadow computation only",
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-09",
      "cap_rows": ["CAP-05", "CAP-06"],
      "rationale": "F03 leaves the bearer undefined and F04 blocks every memo while it is open, so advances, participation and claim purchase cannot close their arithmetic after a refund without a bearer table; a reason-class table keeps the full-refund outcome identical to the pinned fixture reclassification, assigns platform fault to the platform and event cancellation to the organizer, and keeps paid parts as proposed recovery rather than automatic set-off per FINANCE design section 4.5.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "review_owner": "legal counsel designated by JunTae; Toss profile answers for chargeback allocation and merchant-of-record status",
      "review_items": ["consumer refund rules and whether platform fees may be retained on buyer cancellations", "PG chargeback allocation and merchant-of-record status", "contractual definition of platform fault", "VAT treatment of reversed fees (upstream UNDETERMINED)"],
      "alternatives_rejected": ["pro-rata for every reason", "organizer 100 percent for every reason", "leaving the bearer UNDETERMINED"],
      "consumer": "policy-simulator shadow computation; upstream settlement-policy-deepening section 7 partial-refund bearer and fin-multi-payee-refund-proof vectors; TL-3 HELD window input",
      "revisit_triggers": ["settlement-policy-deepening user merge", "Toss profile answers", "refund and chargeback rate data", "counsel review"]
    },
    "resale_prior_contract_cancel_burden": {
      "status": "ADOPTED",
      "value": {
        "policy_version": "CAPITAL-RESALE-UNWIND-V1",
        "principle": "LATEST_TRADE_ONLY_NO_CHAIN_WALK",
        "inputs": {"P_p": "primary gross of the right", "P_r": "latest accepted resale amount (<= resale_cap)", "lines_r": "seller_due, organizer_due, platform_due of the latest trade as computed by rights.move accept_sale (u128 floor)"},
        "triggers": [
          {"id": "RU1_EVENT_CANCELLED_AFTER_TRANSFER", "refund_class": "RC2", "holder_entitlement": "min(P_r, P_p + organizer_due + platform_due)", "funding_ordered": ["primary-claim refund of P_p to the current holder (bearer RC2: organizer line then platform fee line)", "organizer_due of the latest trade reversed to the holder", "platform_due of the latest trade reversed to the holder"], "seller": "keeps seller_due; no clawback", "discount_case": "if P_r < P_p the holder receives P_r and the latest seller receives P_p - P_r out of the primary refund; no resale line is reversed", "unrecovered": "premium beyond the entitlement is the holder market risk, disclosed at listing time"},
          {"id": "RU2_LISTING_CANCELLED_AFTER_PAYMENT_BEFORE_TRANSFER", "holder_entitlement": "the would-be buyer receives P_r in full", "funding": "all three lines of the noted resale payment reversed (seller_due, organizer_due, platform_due); no transfer; no cancellation penalty in V1", "upstream_state": "ResaleMachine PAYMENT_NOTED plus cancel_listing is COMPENSATION_UNDEFINED today"},
          {"id": "RU3_CHARGEBACK_ON_RESALE_PAYMENT_AFTER_TRANSFER", "holder_entitlement": "none; the right stays with the holder under Protocol authority", "burden_ordered": ["seller_due becomes recovery_due", "organizer_due reversed", "platform_due reversed"], "note": "rights status is Protocol and Commerce authority; Capital records money only"}
        ],
        "prior_trades": "never reopened; a prior buyer who sold does not participate in later refunds or proceeds",
        "rounding": "largest remainder, ties ascending label",
        "chain_observation": "rights.move RefundDutyRequested.amount = last_amount is an observation input, not the definition of the entitlement",
        "worked_example_synthetic": {"P_p": 100000, "primary_fee_bps": 500, "P_r": 130000, "organizer_bps": 500, "platform_bps": 500, "seller_due": 117000, "organizer_due": 6500, "platform_due": 6500, "RU1_holder_receives": 113000, "RU1_sources": {"primary_organizer_line": 95000, "primary_platform_line": 5000, "resale_organizer_due": 6500, "resale_platform_due": 6500}, "seller_keeps": 117000, "holder_market_risk": 17000},
        "worked_example_discount": {"P_p": 100000, "P_r": 80000, "holder_receives": 80000, "seller_receives": 20000, "resale_lines_reversed": 0}
      },
      "fsm_expressible": false,
      "fsm_binding": "requires upstream FSM change: a resale claim kind with three payees, a link between the primary claim and the trade chain (right_id, trade_id), a compensation record for COMPENSATION_UNDEFINED, and a refund beneficiary bound to the current holder label; until then shadow computation on a synthetic chain",
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-09",
      "cap_rows": ["CAP-06"],
      "rationale": "Attaching the primary-face refund entitlement to the right so it travels with the holder closes every case in O(1) regardless of chain length, honours the masterplan rule that prior buyers do not keep participating and the blueprint rule that a final-buyer refund neither erases nor auto-creates obligations on past trades; organizer and platform forgo their resale takes on a cancelled event while sellers who sold at market are not clawed back, and the premium is disclosed market risk.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "review_owner": "legal counsel designated by JunTae (consumer protection in resale terms, intermediary liability, chargeback allocation)",
      "review_items": ["enforceability of limiting the holder entitlement to the primary face plus reversed takes", "disclosure duties on resale premium risk", "treatment of RU2 cancellation fees in V2", "alignment of chain last_amount semantics with this entitlement (rs-1, ps-03)"],
      "alternatives_rejected": ["FULL_CHAIN_UNWIND", "LATEST_TRADE_UNWIND with seller clawback", "holder receives P_p only"],
      "consumer": "policy-simulator synthetic resale chain scenarios; upstream booking-resale-admission-deepening, ps-03-resale-contract and settlement-policy-deepening input candidate; Commerce refund-surface must consume the Capital computation, never recompute",
      "revisit_triggers": ["ps-03-resale-contract or booking-resale-admission-deepening user merge", "rs-1 defines refund duty semantics on the new profile", "counsel review", "first multi-hop resale data"]
    },
    "revenue_participation": {
      "status": "ADOPTED",
      "value": {
        "policy_version": "CAPITAL-REVSHARE-V1",
        "participant_v1": "KIX Capital platform entity only; counterparty is the organizer legal entity; third-party participants and investor slices NOT_IN_V1 pending securities and online-investment-linked-finance review",
        "funded_amount": "F = cash supplied under a participation agreement (synthetic; funds_executed false)",
        "participation_base": "B = cash allocated to class 2 COUNTERPARTY_PROCEEDS lines of the event claims (primary organizer residual plus resale organizer_due) minus organizer-borne refunds (RC2 and RC4 recovery_due and cancelled_unpaid); platform fees, protected third-party lines, statement fee tax held components, refund reserve and customer deposits are never in B",
        "ratio_bps_of_base": 2000,
        "cap_bps_of_funded_amount": 15000,
        "floor": "NONE",
        "hurdle_or_preferred_return": "NONE_V1",
        "recovery_order_on_counterparty_proceeds": ["CAPITAL_ADVANCE_SETOFF", "CLAIM_PURCHASE_SLICE", "REVENUE_PARTICIPATION", "ORGANIZER_PAYOUT"],
        "adjustment": {"window_days_after_last_statement": 90, "downward": "organizer-borne refunds inside the window reduce B retroactively; amounts already paid above the adjusted entitlement become recovery_due of the participant (clawback), proposed not auto-executed", "upward": "late cash inside the window increases B and is paid in the next batch", "after_window": "no further adjustment; late facts are recorded only"},
        "term_end": "earlier of cap reached or adjustment window end",
        "rounding": "floor to 1 KRW at each posting, remainder carried",
        "authority": "human operator; two-person rule above 50000000 KRW (CAPITAL-TERMS-V1); AI proposes only",
        "never": ["participation in customer deposits, refund reserve or platform fee lines (TK-4)", "participation by prior ticket buyers", "a participation line inside the pinned two-payee policy", "token-denominated participation"]
      },
      "fsm_expressible": false,
      "fsm_binding": "requires upstream FSM change: a participant payee, a base computation across claims and a cap counter are absent from the pinned PRIMARY_FEE_BPS policy; until then shadow computation",
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-09",
      "cap_rows": ["CAP-02"],
      "rationale": "The masterplan finance group revenue participation needs a base definition, recovery order, ratio and cap; limiting the base to counterparty proceeds keeps the separate-funds boundary, ranking debt-like set-off and slices ahead of equity-like participation mirrors the CAPITAL-TERMS-V1 waterfall, and a 1.5x cap with a 90-day adjustment window sized to the refund and chargeback exposure is an ambitious but bounded production-finance term that data can later retune.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "review_owner": "legal and accounting counsel designated by JunTae (legal character of the participation contract, revenue recognition, withholding)",
      "review_items": ["whether a revenue participation by the platform is lending, investment contract or joint venture under Korean law", "accounting treatment of the participation receivable and clawbacks", "tax and withholding on participation receipts"],
      "alternatives_rejected": ["gross revenue base", "uncapped participation", "participation senior to advances"],
      "consumer": "policy-simulator shadow computation; upstream settlement-policy-deepening section 7 revenue waterfall and k-stage6-economics-reference input candidate",
      "revisit_triggers": ["counsel review", "first synthetic participation loss data", "third-party participant proposal", "settlement-policy-deepening user merge"]
    },
    "claim_purchase": {
      "status": "ADOPTED",
      "value": {
        "policy_version": "CAPITAL-CLAIM-PURCHASE-V1",
        "offering_status": "SIMULATION_ONLY_NOT_OFFERED_V1 (CAPITAL-LICENCE-ROUTE-V1 claim_trading_cap03.v1 NOT_OFFERED unchanged)",
        "form": "RECOURSE_PURCHASE_TREATED_AS_LENDING (working assumption)",
        "unit": "claim slice (claim_id, payee line, slice_face) on a COMMITTED claim with no open refund face",
        "volume": {"per_slice_max": "line outstanding minus open refund face", "advance_rate_bps_by_tier": {"T1_COMMIT_OBSERVED": 8500, "T2_UNBOUND": 0}, "one_open_slice_per_line": true, "aggregate_caps_krw": {"single": 500000000, "beneficiary": 2000000000, "portfolio": 20000000000, "note": "shared with advances under CAPITAL-TERMS-V1"}},
        "holder": {"v1": "KIX Capital lending entity only", "registry": "claim-slice registry (future cr-02) enforcing uniqueness per (claim_id, payee); duplicate slice refused", "third_party_holders": "NOT_IN_V1", "tokenised_slices": "NOT_IN_V1 (TL-L and securities review)"},
        "consideration": {"purchase_price": "slice_face minus discount", "discount": "floor(slice_face * all_in_bps_annual * expected_days / (10000 * 365)) using the CAPITAL-TERMS-V1 tier rate (T1 700 bps per year) and term rule for expected_days", "payment": "synthetic memo; funds_executed false"},
        "priority": {"within_line": "slice holder paid first from that line allocated cash up to slice_face, ahead of the remaining counterparty proceeds (same step as CAPITAL_ADVANCE_SETOFF)", "across_holders": "PRO_RATA_PARI_PASSU_WITHIN_LINE when more than one holder exists (not V1)", "versus_refunds": "refund reversals borne by the line are absorbed first by the organizer retained remainder, then impair the slice; recourse makes the organizer liable for any slice shortfall"},
        "recovery": "shortfall after line cash is a recourse claim against the organizer, then the CAPITAL-TERMS-V1 recovery waterfall",
        "completeness_for_real_funds": "C2 minimum (CAPITAL-TERMS-V1 external_collateral_completeness)",
        "never": ["purchase of refund reserve, platform fee lines or protected third-party lines", "non-recourse true sale in V1", "ticket rights as collateral", "double use of the same borrowing base by an advance and a slice"]
      },
      "fsm_expressible": false,
      "fsm_binding": "requires upstream FSM change: obligation lines have no holder field or assignment command and F04 note_advance is a reservation, not an assignment; until then a shadow slice registry only",
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-09",
      "cap_rows": ["CAP-03"],
      "rationale": "The masterplan finance group claim assignment and purchase needs origin claim, allocated volume, holder, priority, consideration and recovery; sharing tier rates, advance rates and caps with the advance product prevents double use of one borrowing base, the recourse form matches the prior licence-route decision, and keeping the offering off in V1 while simulating the shape lets the registry and priority rules be verified before any investor question is opened.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "review_owner": "legal counsel designated by JunTae; lift decision via f04-real-funds-lift-criteria",
      "review_items": ["recourse purchase as lending versus factoring", "assignment notice and third-party effect", "debt-collection licensing", "securities questions before any third-party holder"],
      "alternatives_rejected": ["non-recourse purchase in V1", "slice priority ahead of buyer refunds", "leaving the design UNDETERMINED"],
      "consumer": "policy-simulator shadow registry; upstream cr-02-claim-eligibility and f04-real-funds-lift-criteria input candidate",
      "revisit_triggers": ["f04-real-funds-lift-criteria user merge", "cr-02 promoted", "counsel review", "any third-party holder proposal"]
    },
    "residual_and_late_cash": {
      "status": "ADOPTED",
      "value": {
        "policy_version": "CAPITAL-RESIDUAL-V1",
        "division_remainder": {"rule": "LARGEST_REMAINDER_TIES_ASCENDING_LABEL, fixed and digested before any computation", "two_payee_primary": "the pinned floor split (fee = floor, residual = gross - fee) already assigns the remainder to the residual payee; V1 keeps that outcome", "n_payee": "requires upstream FSM change"},
        "undistributed_cash_states_ordered": [
          {"id": "UC1_FROZEN_ORDER_CONTINUATION", "when": "lines still outstanding", "rule": "distribute in the frozen order (pinned behaviour)"},
          {"id": "UC2_REFUND_FUNDING_SUSPENSE", "when": "the claim has refund_outstanding or pg_adjustment_outstanding", "rule": "cash held to fund the refund; never distributed to payees; offset against pg_adjustment_outstanding when the provider nets it"},
          {"id": "UC3_LATE_CASH_AFTER_FULL_RECLASS", "when": "fixture_reclassified and no refund outstanding", "rule": "unapplied for the suspense period, then returned to the provider or applied to recovery_due of the same payee only by operator command"},
          {"id": "UC4_OVERPAYMENT", "when": "confirmed cash exceeds the sum of line faces", "rule": "statement correction and return to provider; never a payee distribution"}
        ],
        "suspense_period_days": 180,
        "after_suspense": "operator decision required; unclaimed-funds and deposit law is a review item; simulation retains indefinitely (RETAIN_ALL)",
        "late_cash_after_capital_close": "never reopens a CLOSED or DEFAULTED advance; overlay recovery ledger only (CAPITAL-TERMS-V1)",
        "payout_intent": {"created": "at each accepted distribute per payee", "batch": "D+1 business day after the statement observation (target; synthetic clock)", "execution": "NOT_IN_CAPITAL; future cr-05 or external adapter; funds_executed false"},
        "holdback_reserve": {"v1_bps": 0, "field_reserved": "refund_reserve_bps", "note": "event-cancellation risk is covered by RC2 bearer rules and the Capital advance-rate haircut, not by a payee holdback on COMMITTED claims"},
        "never": ["distributing late cash to cancelled_unpaid lines", "treating suspense cash as a lending base or revenue", "auto-remitting suspense cash"]
      },
      "fsm_expressible": false,
      "fsm_binding": "requires upstream FSM change: no suspense, return or payout-intent command exists; the pinned FSM leaves late cash as undistributed_cash; the two-payee floor split already matches the V1 remainder rule; shadow state labels only",
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-09",
      "cap_rows": ["CAP-05", "CAP-06"],
      "rationale": "The settlement contract fixes the remainder principle but not the method and leaves holds and late cash undefined; naming the remainder method, four undistributed-cash states that put buyer refund funding ahead of payee distribution, a bounded suspense period and a payout intent gives the simulator and the later economics engine deterministic states without ever sending late cash to cancelled obligations.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "review_items": ["unclaimed funds and deposit rules after the suspense period", "payout timing terms with organizers", "provider netting of pg_adjustment_outstanding (Toss)"],
      "alternatives_rejected": ["distributing late cash in the frozen order after reclassification", "immediate provider return without refund funding", "non-zero holdback in V1"],
      "consumer": "policy-simulator shadow state labels; upstream settlement-policy-deepening section 7 remainder priority, holds and adjustment release, and cr-06-repayment-allocation input candidate",
      "revisit_triggers": ["settlement-policy-deepening user merge", "Toss netting answers", "k-stage5-durable-tx storage for suspense timers", "counsel review of unclaimed funds"]
    }
  },
  "upstream_fsm_change_requests_decision_required_astra": [
    "multi-payee policy kind with class table, within-class pro-rata and protected third-party lines",
    "bind_refund reason class and bearer application; condition for lifting DISTRIBUTION_BLOCKED_REFUND_BEARER_UNDEFINED",
    "resale claim kind with seller_due, organizer_due, platform_due; link from primary claim to trade chain; compensation record for ResaleMachine COMPENSATION_UNDEFINED",
    "participant payee, base computation and cap counter",
    "obligation line holder field and assignment command with registry uniqueness",
    "suspense, provider-return and payout-intent commands"
  ],
  "confirmations": {
    "kix_protocol_modified": false,
    "kix_commerce_apps_modified": false,
    "capital_code_modified": false,
    "vendor_unchanged": true,
    "fixtures_unchanged": true,
    "upstream_nodes_marked_complete": [],
    "upstream_adoption_claimed": false,
    "diff_scope": "docs/decisions/CAPITAL_SETTLEMENT_POLICY.md only; capital/, tests/, capital/vendor/, the nine scenarios, both test orders, the 500 bps fixture policy and the five vendor sha256 values unchanged",
    "production": "NOT_AUTHORIZED",
    "real_money": false
  }
}
```

## 5. 수용 기준 매핑

| 수용 기준 | 충족 위치 |
|---|---|
| `docs/decisions/CAPITAL_SETTLEMENT_POLICY.md`에 하나의 ```` ```capital-decision-v1 ```` JSON 블록, 여섯 항목(`allocation_order`, `refund_bearer`, `resale_prior_contract_cancel_burden`, `revenue_participation`(ratio/cap/adjustment/recovery order), `claim_purchase`(volume/holder/consideration/priority), `residual_and_late_cash`) 각 ADOPTED 또는 UNDETERMINED, `value`·`provided_by`·`date`·`cap_rows`·`rationale`·`provisional`·`basis` | §4. 이 문서의 fenced 블록은 하나뿐이고 `entries`에 여섯 키가 모두 있으며 각 항목이 여덟 필수 키를 가진다. `revenue_participation.value`는 `ratio_bps_of_base`·`cap_bps_of_funded_amount`·`adjustment`·`recovery_order_on_counterparty_proceeds`를, `claim_purchase.value`는 `volume`·`holder`·`consideration`·`priority`를 담는다 |
| ADOPTED는 `provided_by "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08"`, `date`, `provisional: true`; 구체적·포부 있는·구현 가능한 값; UNDETERMINED는 이유와 함께만; UNDETERMINED에 value나 ADOPTED에 provided_by/date 누락은 무효 | §4 여섯 항목 모두 ADOPTED이고 같은 문자열·`2026-10-09`·`true`다. UNDETERMINED 항목이 없으므로 무효 조합도 없다. 법률 의존 항목은 UNDETERMINED 대신 `basis: WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW`와 `review_owner`로 표시했다 |
| PROVISIONAL PRODUCT DECISION 라벨(시뮬레이션·제품용, 청약 아님, 실자금 없음, 법률·세무·회계는 작업 가정) | 머리말 상태 배너, §4 `status`·`scope`·`confirmations` |
| KIX 장기 비전과의 연결과 읽은 kix-protocol 문서 경로 인용 | §2 (README §1·§3, DEVELOPMENT_PLAN §1·§5·§11·§13·§14·§18, BLUEPRINT_20260914 §3·§5·§7·§10, ROADMAP 우선순위 3, PROGRAM_ROADMAP_20260930 §0·R-9·R-10·R-11, PROGRAM_DECISIONS_20260928 §2.1·§5, AUTHORITY_MODEL_1, TOKEN_LAYER_AND_RIGHTS_SCALE_SCOPE_20260929, RIGHTS_SCALE_RS0_DECISION_20261008, RUNTIME_ARCHITECTURE_S062 §2·§10, COMMERCE_CONTRACTS, blueprints rights-scale-v1 §1.2·§3.5·§7 및 optional-native-token-v1 §3.1·§7.1·§9, adr/0002, contracts SETTLEMENT_DISTRIBUTION_F01_F03 §0.2·§0.3·§4·§5·§7, CREDIT_ADVANCE_F04 §2·§3·§5, BOOKING_RESALE_ADMISSION_GATES §10, MOVE_PRIMARY_ISSUANCE_PRICE_FEE §1·PF-C04·PF-C05, AI_DELEGATION_AUTHORITY §3·§5, aiops FINANCE_COMPLETION_DESIGN_KO §4·PROGRAM_EXPANSION_20261002_KO(ps-03·ps-07·cr-02·cr-06), PROTOCOL_MASTERPLAN_V2 §7(역사)) |
| 열린 위험 목록 | §6 |
| 모든 수용 항목 매핑 | 이 표 |
| 항목별로 고정 SettlementMachine 표현 가능 여부 기록; 오늘은 명시 배정 순서 목록만 입력이므로 나머지는 'requires upstream FSM change' | 머리말 "FSM 표현 가능성 어휘", §1 표 `fsm_expressible` 열, §3 각 항목 제목과 "게이트와 FSM 결합", §4 `fsm_expressibility_summary`·각 항목 `fsm_expressible`·`fsm_binding`·`upstream_fsm_change_requests_decision_required_astra`. `allocation_order`만 `true`, 나머지 다섯은 `false`·requires upstream FSM change·`SHADOW_NOT_APPLIED` |
| 각 항목에 CAP row(CAP-02/03/05/06)와 근거, 어떤 것도 제품 기본값으로 제시하지 않음 | §1 표·§4 `cap_rows`(모두 CAP-02/03/05/06 안); 모든 값은 `provisional: true`·`policy_adopted` 변경 없음·fixture 라벨 유지(§3.1) |
| diff는 `docs/decisions/`에 한정; 아홉 F01–F03 fixture, 두 시험 배정 순서, 500 bps fixture 정책 불변, vendor 해시 불변 | 머리말과 §4 `bases.fixtures_untouched`·`confirmations`. 이 세션은 읽기 전용이며 파일을 쓰지 않았다. 실제 diff 범위는 supervisor PR과 독립 리뷰어가 확인한다 |
| (이전 요청문) `readiness.py` financial-contracts 차단 사유가 노트를 인용, fixture 라벨은 'not an operating policy' 유지 | 이 노드 범위 밖(코드 변경 없음). §7의 `policy-simulator`가 `capital/readiness.py` `financial-contracts` 차단 사유("수익·원가 정의와 배분 순서/상한", "채권 양도량·보유자·대가·우선순위")와 `capital/service.py` snapshot `decisions` 문구를 이 노트 인용으로 바꾸되 상태값 `DECISION_REQUIRED`→`PROVISIONAL per docs/decisions/CAPITAL_SETTLEMENT_POLICY.md`로의 문구 변경만 하고, `scenarios.py`·`INTEGRATION.md`의 "어느 순서도 제품 기본 정책으로 채택하지 않습니다 / never a selected operating policy" 문구를 유지한다 |
| (이전 요청문) 소유자: JunTae + 금융·법무 자문 | 위임(2026-10-08)으로 결정 권한이 Fable에게 옮겨졌고, 전문가 검토자 지명은 JunTae 몫으로 남았다(upstream D-E). 각 항목의 `review_owner`가 그 자리다 |

## 6. 열린 위험과 재검토 조건

- **이중 상태.** upstream 정산 계약 §0.3·§4·§5·§7은 잔여 우선순위·부담자·waterfall·리셀 분할·보류를 UNDETERMINED/DECISION_REQUIRED로 두고, Capital은 같은 항목에 잠정 값을 가진다. Capital 값은 **입력 후보**다. `settlement-policy-deepening`(A3/ARCHITECTURE)이 다른 값을 채택하면 이 문서는 개정 대상이다.
- **고정 FSM과 그림자 계산의 괴리.** 다섯 항목이 `fsm_expressible: false`라 `policy-simulator`의 결과는 `SHADOW_NOT_APPLIED`이며 고정 FSM의 `refund_bearer_policy=UNDEFINED`·배정 정지·`undistributed_cash`가 계속 참값이다. 그림자 결과를 fixture 결과와 혼동하는 화면·문서가 생기지 않도록 라벨을 강제해야 한다.
- **체인 `last_amount` 의미.** `rights.move`의 `RefundDutyRequested.amount = last_amount`는 최신 거래 금액을 싣는다. `CAPITAL-RESALE-UNWIND-V1`의 보유자 자격(`min(P_r, P_p + organizer_due + platform_due)`)과 다르다. 이 노트는 체인 값을 관측 입력으로만 두지만, `rs-1`·`ps-03`이 환불 의무 사건을 정의할 때 정합을 확인해야 한다.
- **Move 바닥 나눗셈과 largest remainder.** 리셀 `Allocation`은 u128 바닥 나눗셈이고 잔여는 `seller_due`에 남는다. 이 노트의 largest remainder는 **부족 현금 배정·환불 역분개**에 적용되고 리셀 분할 자체는 Move 값을 그대로 쓴다(PF-C05 격리). 두 규칙이 한 청구에서 만나는 지점은 `fin-multi-payee-refund-proof` 벡터로 검증해야 한다.
- **소비자보호·가맹점 지위(법무·토스).** 구매자 환불에서 플랫폼 수수료 보유 가능 여부, 차지백의 PG 귀속, 가맹점 지위(KIX vs 주최자), 리셀 프리미엄 미회수 고지는 모두 작업 가정이다. 토스 프로파일 미확인 항목과 함께 확인한다.
- **수익 참여·채권 매입의 법적 성격(법무·회계·세무).** 참여 계약이 투자계약·대부·공동사업 중 무엇인지, 상환청구권 매입이 대부인지 팩토링인지, 추심 허가, 증권성은 전문가 몫이다. 결론이 다르면 `CAPITAL-LICENCE-ROUTE-V1`과 함께 다시 연다.
- **미청구 자금·공탁(법무).** 180일 보류 뒤의 처리는 운영자 결정으로 남겼고 법적 처리는 검토 항목이다. 저장소 시뮬레이션은 무기한 보존이라 지금은 문제가 되지 않는다.
- **데이터 부재.** 환불률·차지백률·늦은 현금 빈도·리셀 사슬 길이 데이터가 없다. 비율 2,000 bps·상한 1.5×·조정 창 90일·보류 180일은 제품 설계 판단이다.
- **fixture 일치의 오해.** V1 도출 순서 `["organizer", "platform"]`이 `shortfall-organizer` fixture와 같아도 fixture는 비교용이다. `policy-simulator`는 도출 순서를 **별도 시나리오**로 두고 기존 fixture 라벨과 digest를 바꾸지 않는다.
- **sync와 테스트 결합.** `tests/test_readonly_tools.py`·`tests/test_projection.py`는 readiness 문구와 `policy_adopted=false`를 고정한다. 차단 사유 문구를 이 노트 인용으로 바꾸는 노드는 그 테스트를 함께 갱신하되 `policy_adopted`는 그대로 `false`다.
- **재검토 트리거.** (1) `settlement-policy-deepening`·`booking-resale-admission-deepening`·`ps-03-resale-contract` 사용자 병합, (2) upstream FSM 변경 요청(§4)에 대한 Astra 결정, (3) 토스·법무 회신, (4) `fin-multi-payee-refund-proof`·`k-stage6-economics-reference` 채택, (5) `f04-real-funds-lift-criteria` 사용자 병합, (6) 첫 보호 제3자 수취인·첫 제3자 참여자·첫 다중 리셀 사슬 데이터, (7) `policy-simulator` 구현에서 드러나는 산술 불일치.

## 7. 후속 작업

- **`policy-simulator`(구현 소유, 이 노드의 유일한 직접 소비자).** §4 JSON을 `CAPITAL-SETTLEMENT-POLICY-V1`로 로드한다. 할 일: (1) `capital/ports.py`에 `SettlementPolicyPort`를 `typing.Protocol`로 추가하고 기본 구현이 이 JSON을 읽는다(`docs/SEAMS.md` 행은 영수증 없음 → `NOT_BOUND` 유지). (2) `allocation_order`: 클래스 표에서 명시 순서를 도출해 일회용 복제 장부의 고정 `distribute(order=…)`에 넘기는 `derived-order-v1` 시나리오를 **기존 아홉 fixture와 분리해** 추가한다; fixture 파일·라벨·digest 불변. (3) 나머지 다섯 항목은 `SHADOW_NOT_APPLIED` 라벨의 그림자 계산(환불 클래스별 역분개, 합성 리셀 사슬 RU1~RU3, 참여 기준 수익·상한·조정, 슬라이스 등록부, 미배정 현금 상태 UC1~UC4)으로 보여 주고 고정 FSM 조회와 나란히 둔다. (4) `capital/readiness.py` `financial-contracts` 차단 사유와 `capital/service.py` snapshot `decisions` 문구를 "PROVISIONAL per docs/decisions/CAPITAL_SETTLEMENT_POLICY.md (CAPITAL-SETTLEMENT-POLICY-V1)"로 바꾸되 상태값과 `policy_adopted=false`는 유지하고, `docs/CAPITAL_REQUIREMENTS_KO.md` CAP-02/03/05/06 행에 같은 인용을 더한다. (5) `facade-v1.json`·`app.js`·테스트를 같은 PR에서 갱신하고, `scenarios.py`·`INTEGRATION.md`의 "not an operating policy" 문구는 그대로 둔다. (6) vendor 바이트·다섯 해시·`test_vendor_pin_byte_integrity`·골든 digest 불변.
- **`terms-overlay`(선행 결정의 적용 노드)와의 접점.** `collateral_execution.mechanics`의 "수익자에게 배분된 현금"을 **클래스 ② 거래상대 몫 줄에 배정된 현금**으로 읽고, 사후 적용 순서(선지급 상계 → 슬라이스 → 참여 → 지급 의도)를 오버레이 상환 제안에 반영한다. 주최자 부담 환불은 `eligible_face` 재평가 입력이다.
- **upstream 제출 후보(채택 주장 없음).** `settlement-policy-deepening`(§4 전체: 잔여 방법, 부담자 표, waterfall, 리셀 분할·취소 부담, 보류·지급 시점), `fin-multi-payee-refund-proof`(클래스별 역분개·largest remainder·RU1~RU3 보존식 벡터), `ps-03-resale-contract`·`booking-resale-admission-deepening`(RU2 보상 레코드, 프리미엄 고지), `cr-02-claim-eligibility`(슬라이스 등록부·유일성), `cr-06-repayment-allocation`(지급 의도·배치), `k-stage6-economics-reference`(참여 기준 수익·상한), `tl-3-offchain`(RC4·조정 창을 `HELD` 기간 입력으로), `k1-open-inputs-brief`·`tl-legal-brief`·`f04-real-funds-lift-criteria`(§6 법무·토스 질문). 채택은 upstream PR 영수증만이 증명한다.
- **upstream FSM 변경 요청(`DECISION_REQUIRED · Astra`).** §4 `upstream_fsm_change_requests_decision_required_astra` 여섯 건. 어느 것도 Capital이 vendor를 고쳐 선취하지 않는다. 변경이 병합되면 재핀은 별도 노드·별도 영수증이다.
- **전문가 검토 착수(JunTae).** 법무(소비자보호·가맹점 지위·차지백·채권거래·미청구 자금), 회계·세무(참여 수익 인식·원천징수)를 지명한다. 질문지는 §4 각 항목의 `review_items`를 그대로 쓴다.
- **Commerce.** 이 문서는 Commerce 화면을 바꾸지 않는다. `refund-surface`·`bind-settlement-fsm`이 부담자·리셀 취소·참여 수치를 보여 주려면 Capital 조회(`policy-simulator` 결과)를 소비해야 하며 클라이언트 산술은 금지다.
