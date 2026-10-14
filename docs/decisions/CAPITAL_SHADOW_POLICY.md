# Capital 그림자 정책 결정 — SHADOW_NOT_APPLIED 모순 해소와 Capital 소유 그림자 산술의 범위

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
이 문서는 KIX-CAPITAL 저장소 안의 **시뮬레이션·제품 설계용** 결정이다. 청약이나 대출·투자 제안이 아니고, 실자금이 움직이지 않으며, production은 계속 `NOT_AUTHORIZED`다. 법률·세무·회계 내용은 선행 노트의 **작업 가정(WORKING ASSUMPTION)** 을 그대로 상속하며 자문이 아니다. 어떤 upstream 계약의 채택도 주장하지 않는다. 이 문서는 코드·vendor 바이트·`CAPITAL_SETTLEMENT_POLICY.md` 본문을 바꾸지 않는다. 정정은 이 파일의 errata뿐이다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `shadow-policy-decision` · deps `policy-simulator`, `settlement-policy-decision` · kind `decision` · user_merge `False` |
| 결정자 | **GLM-5.3 xhigh → swe-2 → Fable 5.1, delegated by JunTae 2026-10-08 (tertiary 10-14 18:15)** |
| 위임 원문 | 2026-10-08 18:25 KST JunTae Park: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." |
| 결정일 | 2026-10-14 |
| KIX-CAPITAL 기준 | main `8787278`. 선행: [CAPITAL_SETTLEMENT_POLICY.md](CAPITAL_SETTLEMENT_POLICY.md)(`CAPITAL-SETTLEMENT-POLICY-V1`), [CAPITAL_FINANCIAL_TERMS.md](CAPITAL_FINANCIAL_TERMS.md)(`CAPITAL-TERMS-V1`), `capital/policy.py`(`DecisionNoteSettlementPolicy`), `docs/SEAMS.md` |
| kix-protocol 기준 | `9c4da8d` (읽기 전용 `/workspace/capital-run/kixproto-ro`) |
| vendor pin | `capital/vendor/manifest.json` commit `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`, 다섯 파일 SHA256 불변 |
| 상태 어휘 | **ADOPTED** = 위임 범위 안의 잠정 값. **UNDETERMINED** = 값 없음(`value: null`, 방향 `target`). 이번 여덟 항목은 모두 ADOPTED |

## 1. 결정 요약

| item | 결정 (요지) | CAP rows | 소비 |
|---|---|---|---|
| `shadow_math_stance` | **policy-simulator의 거절이 FSM 경로에서 우선한다.** 정산 노트 §7의 "policy-simulator가 SHADOW_NOT_APPLIED로 계산" 지시는 **폐기가 아니라 재배정**: 계산은 별도 그림자 모듈이 한다. 항목마다 FSM 경로 판정(`UNSUPPORTED_BY_PINNED_FSM`)과 그림자 경로 판정(`SHADOW_*`)이 나란히 존재. Audit-20 F4 해소 | CAP-02, CAP-03, CAP-05, CAP-06 | 후속 구현 노드(`shadow-simulator`) |
| `shadow_module_ownership` | Capital 소유 순수 정수 모듈 `capital/shadow.py`(목표 경로) + `ShadowPolicyPort`. vendor·`capital.protocol` import 금지, FSM 명령 없음, 워크스페이스 쓰기 없음. 숫자 정책값은 두 선행 노트 블록에서 읽음. zipapp은 `SHADOW_NOT_BOUND` | CAP-02, CAP-03, CAP-05, CAP-06 | `shadow-simulator` / `docs/SEAMS.md` 새 행 NOT_BOUND |
| `shadow_label_vocabulary` | mode `SHADOW_NOT_APPLIED` 고정, 상태 5종 닫힌 집합, 대조 라벨 3종, **모든 금액 키 `shadow_` 접두**, 상수 false 플래그 9종, provenance `SHADOW_ARITHMETIC_ONLY` | CAP-05, CAP-06 | `shadow-simulator`, 화면, export |
| `rounding_and_tiebreak_rules` | `CAPITAL-SHADOW-V1`: 음이 아닌 int만, 원시 연산 3종(`fill_sequential`, `allocate_largest_remainder`, `capped_pro_rata`), 동점 라벨 코드포인트 오름차순, bps·일수 할인은 마지막 1회 floor, 리셀 세 줄은 입력(재계산 금지), 결정론 digest | CAP-05, CAP-06 | `shadow-simulator` 테스트 골든 |
| `refund_class_inputs` | 입력 벡터 정의. **다음 단계 계산: RC1·RC2·RC3·RC4**(RC4는 RC2 역학 + 판정 플래그). RC5는 리셀 항목으로 라우팅. 벡터 6개·불변식 5개. FSM 경로는 전부 `UNSUPPORTED_BY_PINNED_FSM` | CAP-05, CAP-06 | `shadow-simulator` → upstream `fin-multi-payee-refund-proof` 입력 후보 |
| `resale_unwind_scope` | **RU1·RU2·RU3 모두 다음 단계 계산**, 단 `P_r`·세 줄은 명시 입력(없으면 `SHADOW_INPUT_UNKNOWN`), 사슬 역추적·권리 변경 없음. 벡터 5개 | CAP-06 | `shadow-simulator` → upstream `ps-03-resale-contract` 입력 후보 |
| `revshare_claim_purchase_deferral` | 수익 참여: 단일 청구 게시 산술만 다음 단계, 다중 청구·90일 창·회수는 `SHADOW_DEFERRED`. 채권 매입: 슬라이스 크기·가격만 다음 단계, 등록부·우선순위·손상은 `SHADOW_DEFERRED`. 잔여·늦은 현금: UC1~UC4 분할은 다음 단계, 180일 타이머·D+1 배치는 `SHADOW_DEFERRED` | CAP-02, CAP-03, CAP-05, CAP-06 | `shadow-simulator`; 해제 조건은 `terms-overlay` 논리 시계·저장 adapter |
| `errata_to_settlement_note` | 정산 노트 본문 불변. E1~E4 errata: "policy-simulator가 계산" → "policy-simulator는 UNSUPPORTED로 나열, 그림자 모듈이 계산". 여섯 ADOPTED 값·근거·CAP·upstream 요청은 그대로 | CAP-02, CAP-05, CAP-06 | `CAPITAL_SETTLEMENT_POLICY.md` 독자, `docs/CAPITAL_REQUIREMENTS_KO.md` |

## 2. KIX 비전과의 연결

읽은 경로만 인용한다.

- **`/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md`** A-4 "복원/재실행: 과거 사실 재생은 새로운 외부 실행 허가가 아님", "예약 확정 ≠ 결제 확인 ≠ 체인 권리 발행 완료". 그림자 모듈은 **재생 쪽 계산기**다. 결과는 어떤 실행 허가도 아니므로 `applied_to_fsm`·`funds_executed`가 항상 거짓이고 FSM 명령을 내지 않는다.
- **`/workspace/capital-run/kixproto-ro/README.md`** §1(모델 1), §2(변경 금지 파일: 주석·포맷·임시 mutation도 예외 아님), §3(R2 금지이되 "비운영 로컬 래퍼 `readiness/`는 D-3 경계 안에서 허용"). 같은 모양으로 Capital의 잠금 파일은 vendor 다섯 바이트이고, 그림자 모듈은 그 바깥에서만 허용되는 비운영 로컬 계산기다.
- **`docs/decisions/CAPITAL_SETTLEMENT_POLICY.md`** §2("청구 한 건·최신 거래 한 건에서 O(1)"), §6("그림자 결과를 fixture 결과와 혼동하지 않도록 라벨 강제"), §7(3). 모든 벡터는 줄 5개 이하이고, 라벨 강제는 §3.3의 접두·플래그 규칙으로 구체화한다.
- **`docs/decisions/CAPITAL_FINANCIAL_TERMS.md`** `interest_rate.rounding`("유리수 누적·게시 시 1원 내림·이월")과 `claim_purchase` 할인식. 그림자 반올림은 같은 "마지막 1회 floor" 규칙을 쓴다.
- **`capital/policy.py`** docstring("이 노드는 계산하지 않는다")과 `unsupported()`의 `computed: False`. 이 판정을 FSM 경로의 참값으로 유지한다. **`capital/scenarios.py`** 아홉 fixture와 `public_invariants`는 대조 기준이며 불변이다.
- **`docs/SEAMS.md`**("ADOPTED는 영수증 있는 upstream 대체만"), **`docs/VALIDATION.md`**(로컬 게이트는 SEMANTIC_CONFORMANCE가 아님), **`docs/CAPITAL_REQUIREMENTS_KO.md`**(계획의 존재를 구현 완료로 옮기지 않음). 그림자 벡터 통과는 로컬 게이트이고 upstream 적합성 주장이 아니다.

## 3. 항목별 결정

### 3.1 shadow_math_stance (CAP-02, CAP-03, CAP-05, CAP-06)

- **값.** 모순의 양쪽은 서로 다른 경로를 말한다. (a) **FSM 경로**: `DecisionNoteSettlementPolicy.unsupported()`가 `fsm_expressible: false` 다섯 항목을 `UNSUPPORTED_BY_PINNED_FSM`·`computed: false`로 나열하고 아무것도 계산하지 않는다. 이것이 고정 장부의 유일한 참값이며 **우선한다**. (b) **그림자 경로**: 정산 노트 §7(3)의 그림자 계산 지시는 `policy-simulator`가 아니라 §3.2의 별도 모듈에 **재배정**된다. 모든 그림자 결과는 mode `SHADOW_NOT_APPLIED` 아래 `SHADOW_*` 상태를 갖는다. 두 판정은 같은 응답 안에 `pinned`·`shadow` 키로 나란히 놓이고 섞이지 않는다.
- **근거.** policy-simulator가 그림자까지 계산하면 FSM 입력 모듈과 FSM 밖 산술이 한 파일에 섞여 §6 위험(혼동)이 커진다. 그림자를 아예 없애면 다섯 항목이 upstream FSM 변경 전까지 검증되지 않아 포부와 어긋난다. 분리가 둘 다 지킨다.
- **대안.** policy-simulator 안에서 계산: 기각(경계 혼합). 그림자 전면 보류: 기각(검증 공백). upstream FSM 변경을 Capital이 vendor에서 선취: 기각(잠금 위반).

### 3.2 shadow_module_ownership (CAP-02, CAP-03, CAP-05, CAP-06)

- **값.** 소유는 KIX-CAPITAL. 목표 경로 `capital/shadow.py`, 포트 `ShadowPolicyPort`(`capital/ports.py`), `docs/SEAMS.md` 새 행 NOT_BOUND·영수증 NONE. 입력은 facade가 고정 `view()` 스냅샷 또는 합성 리터럴로 만든 **동결 입력 벡터**와, 두 선행 노트의 단일 capital-decision-v1 블록에서 읽은 정책값(클래스 표·사유 클래스·bps·일수; 숫자 리터럴 복사 금지). import는 표준 라이브러리와 노트 로더뿐이며 `capital/vendor/*`·`capital.protocol`·`SettlementMachine`·`MockSettlement` 인스턴스는 절대 받지 않는다. 순수 함수, 워크스페이스 쓰기 없음. 결과에는 `shadow_rules_version`·`note_digest`·`input_digest`·`result_digest`. zipapp은 docs가 없으므로 `SHADOW_NOT_BOUND`(policy.py와 동일). Commerce는 소비만 하고 재계산하지 않는다. 정산 노트의 upstream FSM 변경 요청 여섯 건은 그대로 `DECISION_REQUIRED · Astra`.
- **근거.** "vendor를 건드리지 않고, 적용하지 않고, 자금을 집행하지 않는" 세 조건을 import 금지·순수 함수·상수 플래그로 기계적으로 보장한다.

### 3.3 shadow_label_vocabulary (CAP-05, CAP-06)

- **값.** mode `SHADOW_NOT_APPLIED`(모든 결과). label "shadow arithmetic — not applied to the pinned FSM, not an executed distribution, not a bank movement". FSM 경로 상태 `UNSUPPORTED_BY_PINNED_FSM`(불변). 그림자 상태(닫힌 집합): `SHADOW_COMPUTED`, `SHADOW_DEFERRED`, `SHADOW_NOT_BOUND`(노트 없음·손상), `SHADOW_INPUT_UNKNOWN`(필수 입력 결여), `SHADOW_INCONSISTENT`(불변식 위반). 대조 라벨: `MATCHES_PINNED_FSM`, `DIVERGES_PINNED_FSM_BY_DESIGN`, `NOT_COMPARABLE`. **금액 키 접두 규칙**: 그림자 출력의 모든 정수 금액 키는 `shadow_`로 시작하고 `distributed`·`recovery_due` 같은 FSM 필드명은 금지. 상수 false 플래그: `applied_to_fsm`, `funds_executed`, `policy_adopted`, `bank_debit_observed`, `right_cancelled`, `external_return_closed`, `legal_debtor_bound`, `admission_granted`, `workspace_mutated`. provenance `SHADOW_ARITHMETIC_ONLY`. 화면은 그림자 숫자를 mode 제목이 붙은 블록 안에만 두고 고정 숫자와 같은 열에 놓지 않는다.
- **근거.** 정산 노트 §6의 라벨 강제 요구를 파서와 테스트가 검사할 수 있는 형태로 바꾼다.

### 3.4 rounding_and_tiebreak_rules (CAP-05, CAP-06)

- **값.** `CAPITAL-SHADOW-V1`. 정의역은 음이 아닌 Python int, float·Decimal 금지, 상한 1,000,000,000,000(고정 MONEY_MAX); 위반은 `SHADOW_INCONSISTENT`. 원시 연산 3종: `fill_sequential(total, [(label, cap)])` 순차 채움(클래스 우선, RC2·RC3 부담 순서, RU3 부담 순서); `allocate_largest_remainder(T, [(label, w)])` = `q_i = floor(T·w_i/W)`, 잔여 R은 `(T·w_i) mod W` 내림차순으로 1원씩, 동점은 라벨 코드포인트 오름차순, W=0이면 `SHADOW_INCONSISTENT`, T=0이면 전부 0; `capped_pro_rata` = largest remainder 뒤 `q_i > cap_i`인 줄을 cap에 고정하고 초과분을 나머지 줄에 재배정, n라운드 안에 종료. bps는 `floor(amount·bps/10000)` 1회. 일수 할인은 `floor(face·bps_annual·days/(10000·365))` 마지막 1회 floor. 게시는 1원 내림·`shadow_carry` 이월. 리셀 `seller_due`·`organizer_due`·`platform_due`는 Move u128 바닥 나눗셈의 **입력**이며 재계산하지 않는다. 라벨은 유일한 ASCII, 중복은 `SHADOW_INCONSISTENT`. 같은 입력은 바이트 동일한 정규 JSON과 같은 `result_digest`를 낸다.
- **근거.** 정산 노트의 largest remainder·라벨 오름차순과 `CAPITAL-TERMS-V1`의 마지막 1회 floor를 그대로 옮기고, 소수부 비교를 정수 나머지 비교로 바꿔 float를 없앤다.

### 3.5 refund_class_inputs (CAP-05, CAP-06)

- **값.** 입력 벡터: `gross`, `obligations[{payee, face, distributed, cancelled_unpaid, outstanding}]`, `refunds[{refund_id, amount, reason_class, evidence_ref, adjudicated_platform_fault?}]`, 클래스 표와 사유 클래스 표(정산 노트 블록). **다음 단계 계산**: RC1(`capped_pro_rata`, 가중치 face, cap = 남은 face), RC2(주최자 줄 → 플랫폼 줄 `fill_sequential`), RC3(플랫폼 줄 → 초과분 `shadow_platform_pool_obligation`), RC4(RC2 역학, `adjudicated_platform_fault: true`면 RC3, 결과에 `working_assumption: true`). RC5는 §3.6으로 라우팅. 줄별 출력 `shadow_reversal`, `shadow_cancelled_unpaid`(= min(reversal, outstanding)), `shadow_recovery_due`(나머지). 불변식: Σreversal + pool = R; reversal_i ≤ 남은 face_i; cancelled_unpaid_i ≤ outstanding_i; recovery_due_i ≤ distributed_i − 기존 recovery; 누적 R ≤ gross. 벡터는 §4(V-RC1-40k, V-RC2-100k, V-RC2-40k, V-RC3-20k, V-RC4-40k-adjudicated, V-RC1-split). 기대값은 fixture 액면(주최자 95,000·플랫폼 5,000, 플랫폼 우선 배정 92,000/5,000)에서 규칙으로 계산한 예시이며, 구현은 고정 view에서 기대값을 재도출한다. **결정은 규칙이지 숫자가 아니다.** FSM 경로는 다섯 클래스 모두 `UNSUPPORTED_BY_PINNED_FSM`.
- **근거.** 네 클래스는 고정 2수취인 view와 노트 표만으로 닫힌다. RC2 전액은 `full-after` fixture와 `MATCHES_PINNED_FSM`로 대조돼 그림자와 fixture가 어긋나지 않음을 증명한다.

### 3.6 resale_unwind_scope (CAP-06)

- **값.** 원칙 `LATEST_TRADE_ONLY_NO_CHAIN_WALK` 유지. 입력: `P_p`, 1차 두 줄(고정 view), `P_r`, `seller_due`, `organizer_due`, `platform_due`, trigger, `chargeback_amount`(RU3, ≤ `P_r`). 리셀 값은 명시 입력 또는 합성 리터럴이며 고정 FSM에는 없으므로 결여 시 `SHADOW_INPUT_UNKNOWN`. **RU1·RU2·RU3 모두 다음 단계 계산.** RU1 보유자 자격 `min(P_r, P_p + organizer_due + platform_due)`, 1차 환불분은 RC2 그림자를 재사용, 할인 리셀은 보유자 `P_r`·판매자 `P_p − P_r`. RU2는 예비 구매자 `P_r`, 세 줄 전액 역분개. RU3는 `fill_sequential(chargeback, [seller_due, organizer_due, platform_due])`, 판매자 몫은 `shadow_recovery_due`. 출력은 `shadow_holder_entitlement`, `shadow_seller_receives`, `shadow_primary_refund_by_line`, `shadow_resale_line_reversal`, `shadow_holder_market_risk`, `shadow_recovery_due`. 권리·보유자 상태는 절대 출력하지 않는다. FSM 경로는 셋 다 `UNSUPPORTED_BY_PINNED_FSM`, 대조는 `NOT_COMPARABLE`(RU1의 1차 환불분만 전액 재분류와 대조).
- **근거.** 세 경우 모두 줄 5개 이하의 정수 산술이라 보류할 이유가 없다. 합성 입력 조건을 명시해 고정 FSM에 없는 것을 있는 척하지 않는다.

### 3.7 revshare_claim_purchase_deferral (CAP-02, CAP-03, CAP-05, CAP-06)

- **값.** **수익 참여**: 다음 단계는 단일 청구 게시 산술만 — `B = 클래스 ② 배정 현금 − 주최자 부담 그림자 환불`, `shadow_participation = floor(B·2000/10000)`, `shadow_cap = floor(F·15000/10000)`, `shadow_payable = min(participation, cap − paid_to_date)`(비율·상한은 노트에서 읽음). `SHADOW_DEFERRED`: 다중 청구 합산, 90일 조정 창·회수, 늦은 현금 증액, 종료. 해제 조건: `terms-overlay` 논리 시계와 다중 청구 그림자 장부. **채권 매입**: 다음 단계는 `slice_face_max = floor((outstanding − open_refund)·advance_rate_bps/10000)`(T1 8,500·T2 0)와 할인·가격만. `SHADOW_DEFERRED`: 슬라이스 등록부·유일성, 배정 안 보유자 우선, 환불 손상·상환청구, 선지급과 공유하는 집계 상한. 해제 조건: 상태 저장 등록부(StoragePort CAP-11 NOT_BOUND). 제공은 `SIMULATION_ONLY_NOT_OFFERED_V1` 그대로. **잔여·늦은 현금**: 다음 단계는 `undistributed_cash`의 순서 분할 — UC1 = min(undistributed, Σoutstanding), UC2 = min(잔여, refund_outstanding), UC3 = 재분류 상태의 잔여, UC4 = `confirmed_cash > Σface`인 잔여 — 와 N수취인 largest remainder. `SHADOW_DEFERRED`: 180일 보류 타이머, D+1 영업일 지급 의도 배치, 제공자 반환 명령. view에 `reclassified`·`pg_adjustment_outstanding`이 없으면 호출자가 명시 입력하거나 `SHADOW_INPUT_UNKNOWN`. FSM 경로는 셋 다 `UNSUPPORTED_BY_PINNED_FSM`.
- **근거.** 시계·상태 저장이 필요한 부분만 미루고, 순수 함수로 닫히는 부분은 지금 검증한다. 보류 기준이 "어려움"이 아니라 "의존 seam 부재"라 재검토 조건이 명확하다.

### 3.8 errata_to_settlement_note (CAP-02, CAP-05, CAP-06)

- **값.** `CAPITAL_SETTLEMENT_POLICY.md`는 편집하지 않는다. E1: 머리말 "FSM 표현 가능성 어휘"·§1 표·§3.2~§3.6 "게이트와 FSM 결합"·§4 `meaning_of_false`·§7(3)의 "policy-simulator가 … SHADOW_NOT_APPLIED로 계산"은 "policy-simulator는 `UNSUPPORTED_BY_PINNED_FSM`(`computed: false`)로 나열하고, 그림자 모듈이 mode `SHADOW_NOT_APPLIED`로 계산한다"로 읽는다. E2: 다섯 항목 `consumer` 문자열의 "policy-simulator shadow computation/registry/state labels"는 "shadow module(`ShadowPolicyPort`)"로 읽으며, `unsupported()`가 되돌려 주는 그 문자열은 계산 주장이 아니다. E3: §6 "라벨 강제"는 §3.3의 규칙으로 구체화됐다. E4: §7(3)의 그림자 목록은 §3.7의 다음 단계/보류 구분을 따른다. 여섯 ADOPTED 값·근거·`basis`·`review_items`·CAP·upstream FSM 변경 요청·confirmations는 모두 유효하다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "shadow-policy-decision",
  "decided_by": "GLM-5.3 xhigh → swe-2 → Fable 5.1, delegated by JunTae 2026-10-08 (tertiary 10-14 18:15)",
  "date": "2026-10-14",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "policy_version": "CAPITAL-SHADOW-V1",
  "scope": "KIX-CAPITAL simulation and product design only; not an offer; no real money; production NOT_AUTHORIZED; legal, tax and accounting bases are inherited working assumptions from CAPITAL-SETTLEMENT-POLICY-V1 and CAPITAL-TERMS-V1; no upstream adoption claimed",
  "bases": {
    "capital_main": "8787278",
    "kix_protocol": "9c4da8d",
    "vendor_pin_commit": "7481b0e16ce9b903abbffa62249bb91cd9e63cfe",
    "prior_capital_decisions": [
      "docs/decisions/CAPITAL_SETTLEMENT_POLICY.md (CAPITAL-SETTLEMENT-POLICY-V1, 2026-10-09): six ADOPTED entries; five fsm_expressible false",
      "docs/decisions/CAPITAL_FINANCIAL_TERMS.md (CAPITAL-TERMS-V1, 2026-10-08): tier rates, advance rates, rounding rule"
    ],
    "merged_simulator": "capital/policy.py DecisionNoteSettlementPolicy: fsm_expressible false entries listed as UNSUPPORTED_BY_PINNED_FSM with computed false; nothing shadow-computed",
    "audit_finding": "Audit-20 F4: settlement note says policy-simulator computes SHADOW_NOT_APPLIED results; merged simulator refuses"
  },
  "entries": {
    "shadow_math_stance": {
      "status": "ADOPTED",
      "value": {
        "prevails": "POLICY_SIMULATOR_REFUSAL_ON_FSM_PATH",
        "section_7_instruction": "REASSIGNED_NOT_REVOKED: shadow arithmetic is owned by a separate Capital pure-integer module (shadow_module_ownership); DecisionNoteSettlementPolicy.unsupported() keeps status UNSUPPORTED_BY_PINNED_FSM and computed false and never calculates",
        "two_path_rule": "every fsm_expressible false item carries an FSM-path verdict (UNSUPPORTED_BY_PINNED_FSM from capital/policy.py, the only truth about the pinned book) and a shadow-path verdict (SHADOW_* status under mode SHADOW_NOT_APPLIED); both are returned side by side under keys pinned and shadow and are never merged",
        "audit_20_f4": "RESOLVED by errata E1: the note's sentence that policy-simulator computes is corrected; the shadow module computes; the pinned FSM refusal codes (DISTRIBUTION_BLOCKED_REFUND_BEARER_UNDEFINED, DISTRIBUTION_ORDER_FROZEN) and undistributed_cash stay the facts of record",
        "never": ["shadow math inside capital/policy.py or capital/scenarios.py", "a shadow value written into a SettlementMachine or MockSettlement book", "a vendor edit to express a shadow item", "a shadow result presented as a distribution, recovery or payout"]
      },
      "provided_by": "GLM-5.3 xhigh → swe-2 → Fable 5.1, delegated by JunTae 2026-10-08 (tertiary 10-14 18:15)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-02", "CAP-03", "CAP-05", "CAP-06"],
      "rationale": "Mixing FSM-input derivation and off-FSM arithmetic in one module would blur the boundary the settlement note itself flags as a risk, while dropping shadow math would leave five decided items unverified until an upstream FSM change; separating the two paths keeps the pinned refusal as the record and still lets the decided rules be exercised.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "shadow_module_ownership": {
      "status": "ADOPTED",
      "value": {
        "owner": "KIX-CAPITAL; not kix-protocol, not kix-commerce-apps",
        "target_module": "capital/shadow.py (next-phase implementation node; code out of scope here)",
        "port": "ShadowPolicyPort typing.Protocol in capital/ports.py; docs/SEAMS.md row with Readiness CAP-02, CAP-03, CAP-05, CAP-06, Status NOT_BOUND, Upstream receipt NONE",
        "inputs": "frozen input vector dicts built by the facade from a pinned view() snapshot or synthetic literals, plus policy values read from the single capital-decision-v1 block of docs/decisions/CAPITAL_SETTLEMENT_POLICY.md and docs/decisions/CAPITAL_FINANCIAL_TERMS.md; no copied numeric literals",
        "imports": "stdlib plus the note loader only; never capital/vendor/*, never capital.protocol, never a SettlementMachine or MockSettlement instance",
        "effects": "pure function; no workspace write; no FSM command; results placed beside pinned views under separate keys pinned and shadow",
        "zipapp": "docs/ not bundled, so the zipapp run is SHADOW_NOT_BOUND (same as policy.py NOT_BOUND)",
        "digests": ["shadow_rules_version CAPITAL-SHADOW-V1", "note_digest = sha256 of the canonical settlement block", "input_digest", "result_digest"],
        "commerce": "consumes Capital shadow output; never recomputes (settlement note rule kept)",
        "upstream": "the six upstream FSM change requests in the settlement note stay DECISION_REQUIRED Astra; the shadow module never pre-empts them"
      },
      "provided_by": "GLM-5.3 xhigh → swe-2 → Fable 5.1, delegated by JunTae 2026-10-08 (tertiary 10-14 18:15)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-02", "CAP-03", "CAP-05", "CAP-06"],
      "rationale": "Import bans, pure functions and constant false flags make the three constraints (never touch vendor FSMs, never applied, never funds_executed) mechanically checkable by tests rather than by reading prose.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "shadow_label_vocabulary": {
      "status": "ADOPTED",
      "value": {
        "mode": "SHADOW_NOT_APPLIED on every shadow result",
        "label": "shadow arithmetic — not applied to the pinned FSM, not an executed distribution, not a bank movement",
        "fsm_path_status": "UNSUPPORTED_BY_PINNED_FSM (unchanged; from capital/policy.py)",
        "shadow_status_closed_set": ["SHADOW_COMPUTED", "SHADOW_DEFERRED", "SHADOW_NOT_BOUND", "SHADOW_INPUT_UNKNOWN", "SHADOW_INCONSISTENT"],
        "reconciliation_closed_set": ["MATCHES_PINNED_FSM", "DIVERGES_PINNED_FSM_BY_DESIGN", "NOT_COMPARABLE"],
        "amount_key_prefix": "every integer amount key in a shadow result starts with shadow_; unprefixed FSM field names (distributed, outstanding, cancelled_unpaid, recovery_due, distributed_cash) are forbidden in shadow output",
        "constant_false_flags": ["applied_to_fsm", "funds_executed", "policy_adopted", "bank_debit_observed", "right_cancelled", "external_return_closed", "legal_debtor_bound", "admission_granted", "workspace_mutated"],
        "provenance": "SHADOW_ARITHMETIC_ONLY beside the existing MOCK_SETTLEMENT_ONLY",
        "ui_rule": "shadow numbers appear only inside a block titled with the mode label and never in the same column as pinned numbers"
      },
      "provided_by": "GLM-5.3 xhigh → swe-2 → Fable 5.1, delegated by JunTae 2026-10-08 (tertiary 10-14 18:15)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-05", "CAP-06"],
      "rationale": "The settlement note section 6 demands label enforcement against confusing shadow results with fixture results; a closed status set, a key prefix and constant flags turn that demand into something a parser and a test can check.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "rounding_and_tiebreak_rules": {
      "status": "ADOPTED",
      "value": {
        "rules_version": "CAPITAL-SHADOW-V1",
        "domain": "non-negative Python int only; no float, no Decimal; inputs <= 1000000000000 (pinned MONEY_MAX); negative or over-bound input -> SHADOW_INCONSISTENT",
        "primitives": {
          "fill_sequential": "fill ordered (label, cap) lines from a total until exhausted; used for class priority, RC2 and RC3 bearer order, RU3 burden order",
          "allocate_largest_remainder": "q_i = floor(T*w_i/W); R = T - sum(q_i); one KRW each to lines in descending (T*w_i) mod W; ties by ascending label in code-point order; W == 0 -> SHADOW_INCONSISTENT; T == 0 -> all zeros",
          "capped_pro_rata": "allocate_largest_remainder, then fix every q_i > cap_i at cap_i and re-allocate the excess among uncapped lines; repeat; terminates within n rounds"
        },
        "bps": "floor(amount * bps / 10000), single floor",
        "time_discount": "floor(face * bps_annual * days / (10000 * 365)), single floor at the end (CAPITAL-TERMS-V1 rule)",
        "posting": "floor to 1 KRW per posting; remainder carried as shadow_carry",
        "resale_lines": "seller_due, organizer_due, platform_due are inputs (Move u128 floor) and are never recomputed",
        "labels": "unique ASCII payee labels required; duplicate label -> SHADOW_INCONSISTENT",
        "determinism": "identical input vector -> byte-identical canonical JSON (sort_keys, ensure_ascii) and identical result_digest; golden digests pinned in tests beside, never replacing, the nine fixture digests"
      },
      "provided_by": "GLM-5.3 xhigh → swe-2 → Fable 5.1, delegated by JunTae 2026-10-08 (tertiary 10-14 18:15)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-05", "CAP-06"],
      "rationale": "Carries the settlement note's largest-remainder and ascending-label rules and the terms note's single final floor into one integer-only rule set, replacing fractional-part comparison with integer remainder comparison so no float ever enters.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "refund_class_inputs": {
      "status": "ADOPTED",
      "value": {
        "input_vector": {
          "gross": "int",
          "obligations": "[{payee, face, distributed, cancelled_unpaid, outstanding}] from a pinned view snapshot",
          "refunds": "[{refund_id, amount, reason_class RC1..RC5, evidence_ref, adjudicated_platform_fault (RC4 only, bool)}]",
          "class_table": "settlement note allocation_order.value.class_table_ordered",
          "bearer_rules": "settlement note refund_bearer.value.reason_classes_ordered"
        },
        "next_phase_shadow_computed": [
          "RC1_BUYER_WITHIN_POLICY: capped_pro_rata weighted by face, cap = remaining face",
          "RC2_EVENT_CANCELLED_OR_ORGANIZER_FAULT: fill_sequential organizer residual line then platform fee line",
          "RC3_PLATFORM_FAULT: fill_sequential platform fee line, excess -> shadow_platform_pool_obligation; organizer lines untouched",
          "RC4_PROVIDER_CHARGEBACK_OR_DISPUTE: RC2 mechanics; adjudicated_platform_fault true -> RC3 mechanics; result carries working_assumption true"
        ],
        "routed": "RC5_RESALE_UNWIND -> resale_unwind_scope",
        "fsm_path": "RC1-RC5 all stay UNSUPPORTED_BY_PINNED_FSM",
        "outputs_per_line": ["shadow_reversal", "shadow_cancelled_unpaid = min(reversal, outstanding)", "shadow_recovery_due = reversal - shadow_cancelled_unpaid"],
        "outputs_claim": ["shadow_platform_pool_obligation", "shadow_cumulative_refund", "auto_reclassified false always"],
        "invariants": ["sum(shadow_reversal) + shadow_platform_pool_obligation == R", "shadow_reversal_i <= face_i - prior reversals_i", "shadow_cancelled_unpaid_i <= outstanding_i", "shadow_recovery_due_i <= distributed_i - prior recovery_i", "cumulative R <= gross (pinned REFUND_CEILING)"],
        "vectors": [
          {"id": "V-RC1-40k", "base": "fixture partial-after: organizer face 95000 distributed 92000 outstanding 3000; platform face 5000 distributed 5000", "refund": 40000, "expected": {"organizer": {"shadow_reversal": 38000, "shadow_cancelled_unpaid": 3000, "shadow_recovery_due": 35000}, "platform": {"shadow_reversal": 2000, "shadow_cancelled_unpaid": 0, "shadow_recovery_due": 2000}}, "reconciliation": "DIVERGES_PINNED_FSM_BY_DESIGN (pinned refuses DISTRIBUTION_BLOCKED_REFUND_BEARER_UNDEFINED and keeps faces)"},
          {"id": "V-RC2-100k", "base": "fixture full-after", "refund": 100000, "expected": {"organizer": {"shadow_reversal": 95000, "shadow_cancelled_unpaid": 3000, "shadow_recovery_due": 92000}, "platform": {"shadow_reversal": 5000, "shadow_cancelled_unpaid": 0, "shadow_recovery_due": 5000}}, "reconciliation": "MATCHES_PINNED_FSM (FIXTURE_FULL_GROSS_RECLASS: per-line cancelled_unpaid and total recovery_due 97000 equal)"},
          {"id": "V-RC2-40k", "base": "fixture partial-after", "refund": 40000, "expected": {"organizer": {"shadow_reversal": 40000, "shadow_cancelled_unpaid": 3000, "shadow_recovery_due": 37000}, "platform": {"shadow_reversal": 0}}, "reconciliation": "DIVERGES_PINNED_FSM_BY_DESIGN"},
          {"id": "V-RC3-20k", "base": "fixture partial-after", "refund": 20000, "expected": {"platform": {"shadow_reversal": 5000, "shadow_recovery_due": 5000}, "organizer": {"shadow_reversal": 0}, "shadow_platform_pool_obligation": 15000}, "reconciliation": "DIVERGES_PINNED_FSM_BY_DESIGN"},
          {"id": "V-RC4-40k-adjudicated", "base": "fixture partial-after, adjudicated_platform_fault true", "refund": 40000, "expected": {"platform": {"shadow_reversal": 5000, "shadow_recovery_due": 5000}, "shadow_platform_pool_obligation": 35000, "working_assumption": true}, "reconciliation": "DIVERGES_PINNED_FSM_BY_DESIGN"},
          {"id": "V-RC1-split-40k-60k", "base": "fixture split-refund mechanics on partial-after", "refunds": [40000, 60000], "expected": {"second_refund": {"organizer": 57000, "platform": 3000}, "cumulative": {"organizer": {"shadow_cancelled_unpaid": 3000, "shadow_recovery_due": 92000}, "platform": {"shadow_recovery_due": 5000}}, "auto_reclassified": false}, "reconciliation": "DIVERGES_PINNED_FSM_BY_DESIGN"}
        ],
        "expected_values_note": "illustrative outputs computed by the rule from the fixture faces (organizer 95000, platform 5000; platform-first distribution 92000/5000); the implementation re-derives expectations from the pinned view; the rule, not the number, is the decision"
      },
      "provided_by": "GLM-5.3 xhigh → swe-2 → Fable 5.1, delegated by JunTae 2026-10-08 (tertiary 10-14 18:15)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-05", "CAP-06"],
      "rationale": "Four reason classes close on the pinned two-payee view plus the note tables alone, and the RC2 full-refund vector reconciles with the pinned fixture reclassification, proving the shadow rules and the fixtures do not drift apart.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "resale_unwind_scope": {
      "status": "ADOPTED",
      "value": {
        "principle": "LATEST_TRADE_ONLY_NO_CHAIN_WALK kept",
        "input_vector": {"P_p": "primary gross", "primary_lines": "organizer and platform faces and distributed from the pinned view", "P_r": "latest resale amount <= resale_cap", "seller_due": "input", "organizer_due": "input", "platform_due": "input", "trigger": "RU1 | RU2 | RU3", "chargeback_amount": "RU3 only, <= P_r"},
        "inputs_rule": "resale lines and P_r are explicit inputs or synthetic literals; the pinned FSM has none; missing -> SHADOW_INPUT_UNKNOWN; never a chain walk, never a holder or right change",
        "next_phase_shadow_computed": [
          "RU1: shadow_holder_entitlement = min(P_r, P_p + organizer_due + platform_due); primary refund portion reuses the RC2 shadow; discount case holder P_r and seller P_p - P_r with no resale line reversed",
          "RU2: would-be buyer receives P_r; seller_due, organizer_due, platform_due reversed in full",
          "RU3: fill_sequential(chargeback_amount, [seller_due, organizer_due, platform_due]); the seller part is shadow_recovery_due"
        ],
        "fsm_path": "RU1-RU3 all stay UNSUPPORTED_BY_PINNED_FSM; reconciliation NOT_COMPARABLE except the RU1 primary-refund portion, which must MATCH the pinned full reclassification when the P_p refund equals gross",
        "outputs": ["shadow_holder_entitlement", "shadow_seller_receives", "shadow_primary_refund_by_line", "shadow_resale_line_reversal", "shadow_holder_market_risk", "shadow_recovery_due"],
        "vectors": [
          {"id": "V-RU1-premium", "inputs": {"P_p": 100000, "P_r": 130000, "seller_due": 117000, "organizer_due": 6500, "platform_due": 6500}, "expected": {"shadow_holder_entitlement": 113000, "shadow_primary_refund_by_line": {"organizer": 95000, "platform": 5000}, "shadow_resale_line_reversal": {"organizer_due": 6500, "platform_due": 6500, "seller_due": 0}, "shadow_seller_receives": 0, "shadow_holder_market_risk": 17000}},
          {"id": "V-RU1-discount", "inputs": {"P_p": 100000, "P_r": 80000}, "expected": {"shadow_holder_entitlement": 80000, "shadow_seller_receives": 20000, "shadow_resale_line_reversal": {"organizer_due": 0, "platform_due": 0, "seller_due": 0}}},
          {"id": "V-RU2", "inputs": {"P_r": 130000, "seller_due": 117000, "organizer_due": 6500, "platform_due": 6500}, "expected": {"shadow_holder_entitlement": 130000, "shadow_resale_line_reversal": {"seller_due": 117000, "organizer_due": 6500, "platform_due": 6500}}},
          {"id": "V-RU3-full", "inputs": {"chargeback_amount": 130000}, "expected": {"shadow_recovery_due": {"seller_due": 117000}, "shadow_resale_line_reversal": {"organizer_due": 6500, "platform_due": 6500}, "shadow_holder_entitlement": 0}},
          {"id": "V-RU3-partial-50k", "inputs": {"chargeback_amount": 50000}, "expected": {"shadow_recovery_due": {"seller_due": 50000}, "shadow_resale_line_reversal": {"organizer_due": 0, "platform_due": 0}}}
        ]
      },
      "provided_by": "GLM-5.3 xhigh → swe-2 → Fable 5.1, delegated by JunTae 2026-10-08 (tertiary 10-14 18:15)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-06"],
      "rationale": "All three triggers are integer arithmetic over at most five lines, so none needs deferral; making the resale lines explicit inputs keeps the shadow honest about what the pinned FSM does not hold and keeps rights state with Protocol authority.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "revshare_claim_purchase_deferral": {
      "status": "ADOPTED",
      "value": {
        "revenue_participation": {
          "next_phase": "single-claim posting arithmetic only: B = shadow class-2 allocated cash minus organizer-borne shadow refunds (RC2/RC4 shadow_recovery_due plus shadow_cancelled_unpaid); shadow_participation = floor(B * ratio_bps / 10000); shadow_cap = floor(F * cap_bps / 10000); shadow_payable = min(shadow_participation, shadow_cap - paid_to_date); ratio and cap read from the settlement note",
          "deferred_SHADOW_DEFERRED": ["multi-claim base aggregation per event", "90-day adjustment window and clawback", "upward late-cash adjustment", "term_end"],
          "unblock": "terms-overlay logical clock (sim_day) and a multi-claim shadow book",
          "vector": {"id": "V-RP-single", "inputs": {"class2_allocated": 95000, "organizer_borne_refunds": 0, "F": 50000}, "expected": {"shadow_base": 95000, "shadow_participation": 19000, "shadow_cap": 75000, "shadow_payable": 19000}}
        },
        "claim_purchase": {
          "next_phase": "slice sizing and price only: shadow_slice_face_max = floor((line outstanding - open refund face) * advance_rate_bps / 10000) with T1 8500 and T2 0 read from the note; shadow_discount = floor(slice_face * all_in_bps_annual * expected_days / (10000 * 365)); shadow_price = slice_face - shadow_discount",
          "deferred_SHADOW_DEFERRED": ["slice registry and uniqueness", "holder-first priority inside distributions", "impairment under refunds and recourse", "aggregate caps shared with advances"],
          "unblock": "a shadow registry needs state; StoragePort CAP-11 NOT_BOUND; offering stays SIMULATION_ONLY_NOT_OFFERED_V1",
          "vector": {"id": "V-CP-size", "inputs": {"outstanding": 95000, "open_refund_face": 0, "tier": "T1_COMMIT_OBSERVED", "expected_days": 60}, "expected": {"shadow_slice_face_max": 80750, "shadow_discount": 929, "shadow_price": 79821}}
        },
        "residual_and_late_cash": {
          "next_phase": "ordered partition of undistributed_cash as a pure function of the pinned view: UC1 = min(undistributed, sum outstanding); UC2 = min(remaining, refund_outstanding); UC3 = remaining when reclassified; UC4 = remaining when confirmed_cash > sum of faces; plus the N-payee largest-remainder primitive",
          "deferred_SHADOW_DEFERRED": ["180-day suspense timer", "D+1 business-day payout intent batch", "provider return command"],
          "unblock": "terms-overlay logical clock and business-day calendar",
          "input_unknown_rule": "if the pinned view lacks reclassified or pg_adjustment_outstanding the caller passes them explicitly or the result is SHADOW_INPUT_UNKNOWN",
          "vectors": [
            {"id": "V-UC-split-statement", "expected": "UC1 takes the undistributed cash while lines are outstanding"},
            {"id": "V-UC-late-cash-open-refund", "base": "fixture late-cash: undistributed 100000, refund_outstanding 100000", "expected": {"shadow_uc2": 100000}},
            {"id": "V-UC-late-cash-accepted", "base": "late-cash after full mock acceptance: refund_outstanding 0, reclassified", "expected": {"shadow_uc3": 100000}},
            {"id": "V-UC-overpay", "base": "synthetic: confirmed 101000, faces 100000, all distributed", "expected": {"shadow_uc4": 1000}}
          ]
        },
        "fsm_path": "all three stay UNSUPPORTED_BY_PINNED_FSM"
      },
      "provided_by": "GLM-5.3 xhigh → swe-2 → Fable 5.1, delegated by JunTae 2026-10-08 (tertiary 10-14 18:15)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-02", "CAP-03", "CAP-05", "CAP-06"],
      "rationale": "Only the parts that need a clock or persistent state are deferred, and each deferral names the seam that unblocks it; the pure-function parts are verified now so that the later overlay and registry work starts from tested arithmetic.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "errata_to_settlement_note": {
      "status": "ADOPTED",
      "value": {
        "note": "docs/decisions/CAPITAL_SETTLEMENT_POLICY.md is not edited; these errata are read together with it",
        "E1": {"where": "header row FSM 표현 가능성 어휘; section 1 fsm_expressible column; sections 3.2-3.6 게이트와 FSM 결합; section 4 fsm_expressibility_summary.meaning_of_false; section 7 item (3)", "reads": "policy-simulator computes the item on a disposable copy labelled SHADOW_NOT_APPLIED", "corrected_to": "policy-simulator lists the item as UNSUPPORTED_BY_PINNED_FSM (computed false, requires upstream FSM change); the Capital-owned shadow module decided in CAPITAL_SHADOW_POLICY.md computes it under mode SHADOW_NOT_APPLIED"},
        "E2": {"where": "section 4 consumer strings of refund_bearer, resale_prior_contract_cancel_burden, revenue_participation, claim_purchase, residual_and_late_cash", "corrected_to": "shadow module (ShadowPolicyPort) per CAPITAL_SHADOW_POLICY.md; the strings echoed by DecisionNoteSettlementPolicy.unsupported() are unchanged text and carry no computation claim"},
        "E3": {"where": "section 6 고정 FSM과 그림자 계산의 괴리", "corrected_to": "label enforcement is concrete: mode SHADOW_NOT_APPLIED, shadow_ amount-key prefix, constant false flags, reconciliation labels"},
        "E4": {"where": "section 7 item (3) list of shadow computations", "corrected_to": "next phase computes RC1-RC4, RU1-RU3, the UC1-UC4 partition, single-claim participation posting and slice sizing/price; window, timers, registry and multi-claim base are SHADOW_DEFERRED"},
        "unchanged": "all six ADOPTED values, bases, review items, CAP rows, upstream FSM change requests and the fixture and vendor confirmations of the settlement note stand"
      },
      "provided_by": "GLM-5.3 xhigh → swe-2 → Fable 5.1, delegated by JunTae 2026-10-08 (tertiary 10-14 18:15)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-02", "CAP-05", "CAP-06"],
      "rationale": "The merged note is a decided product policy and stays byte-identical; a reader needs one place that says which sentence is superseded and by what, without reopening any decided value.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  },
  "confirmations": {
    "kix_protocol_modified": false,
    "kix_commerce_apps_modified": false,
    "capital_code_modified": false,
    "settlement_note_modified": false,
    "vendor_unchanged": true,
    "fixtures_unchanged": true,
    "upstream_nodes_marked_complete": [],
    "upstream_adoption_claimed": false,
    "diff_scope": "docs/decisions/CAPITAL_SHADOW_POLICY.md only",
    "production": "NOT_AUTHORIZED",
    "real_money": false
  }
}
```

## 5. 수용 기준 매핑

| 수용 기준 | 충족 위치 |
|---|---|
| 파일 존재, 하나의 capital-decision-v1 블록, 모든 decision_item, `scripts/decision_ledger.py` 통과 | §4. fenced 블록은 하나이고 `entries`에 여덟 키가 있으며 각 항목이 `status`·`value`·`provided_by`·`date`·`cap_rows`·`rationale`·`provisional`·`basis`를 갖는다. 이 세션은 읽기 전용이라 ledger 스크립트를 실행하지 않았다. supervisor가 실행해 확인한다 |
| 거절 vs §7 지시 중 무엇이 우선하는지, F4 해소 | §3.1·§4 `shadow_math_stance.prevails`·`audit_20_f4` |
| RC1~RC5·RU1~RU3·수익 참여·채권 매입·잔여 현금 중 다음 단계 계산/보류 명시 | §3.5~§3.7, §4 `next_phase_shadow_computed`·`deferred_SHADOW_DEFERRED`·`fsm_path` |
| 정산 노트 미편집, 정정은 errata | §3.8·§4 `errata_to_settlement_note`·`confirmations.settlement_note_modified` |

## 6. 열린 위험

- **두 참값의 혼동.** 접두·플래그·mode 규칙을 테스트가 강제하지 않으면 화면이 그림자 숫자를 배정으로 보일 수 있다. 구현 노드가 `tests/test_shadow.py`에 라벨 검사를 넣어야 한다.
- **upstream 값 변경.** `settlement-policy-deepening`이 다른 부담자·반올림을 채택하면 그림자 벡터는 입력 후보로서 개정된다.
- **합성 리셀 입력.** RU 벡터는 노트의 예시값이며 실제 리셀 사슬·Move 출력 데이터가 없다.
- **단일 청구 참여 수치의 오독.** `V-RP-single`은 게시 산술 검증이지 지급 자격이 아니다. 다중 청구·창 조정 전에는 상한 추적이 없다.
- **법적 기초 상속.** RC4·리셀·참여·매입의 작업 가정은 정산 노트의 `review_items` 그대로 열려 있다.
- **zipapp.** docs가 없는 실행은 `SHADOW_NOT_BOUND`이며 그림자 기능이 없다.

## 7. 후속 작업

- **구현 노드(`shadow-simulator`, 이름은 supervisor 확정).** `capital/shadow.py`·`ShadowPolicyPort`·`docs/SEAMS.md` 행(NOT_BOUND)·`tests/test_shadow.py`(§4 벡터 17개, 대조 라벨, 접두·플래그 검사, 골든 digest)·facade `pinned`/`shadow` 키·화면 블록. `capital/policy.py`는 바꾸지 않는다(docstring의 "이 노드는 계산하지 않는다"는 계속 참). 아홉 fixture·vendor 해시·골든 digest 불변.
- **`docs/CAPITAL_REQUIREMENTS_KO.md`** CAP-02/03/05/06 행에 이 노트 인용 추가. `policy_adopted=false` 유지.
- **2단계 그림자(`terms-overlay` 논리 시계 뒤).** 90일 조정 창·회수, 180일 보류 타이머, D+1 지급 의도 배치, 다중 청구 기준 수익.
- **3단계 그림자(저장 adapter 뒤).** 슬라이스 등록부·유일성·배정 안 보유자 우선·손상.
- **upstream 제출 후보(채택 주장 없음).** 벡터 표를 `fin-multi-payee-refund-proof`·`ps-03-resale-contract`·`settlement-policy-deepening` 입력 후보로. 채택은 upstream PR 영수증만이 증명한다.
