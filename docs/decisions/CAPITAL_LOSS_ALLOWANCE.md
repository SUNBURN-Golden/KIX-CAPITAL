# Capital 기대신용손실 충당금 메커니즘 결정 — 측정 기준, 게시 시점, true-up·환입, 가속·부도 처리, 준비금 풀 연결, risk 대사, cut 범위

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
이 문서는 KIX-CAPITAL 저장소 안에서 시뮬레이션과 제품 설계에만 쓰는 결정이다. 청약이나 대출 제안이 아니다. 실자금은 움직이지 않고 production은 계속 `NOT_AUTHORIZED`다. 이 노트는 회계 정책을 채택하지 않는다. `accounting_policy = SYNTHETIC_UNADOPTED`, `tax = NOT_BOUND`, `legal = NOT_BOUND`, `operating_ledger = NOT_BOUND`는 그대로 둔다. 충당금의 분류, 측정 모형, 세무상 손금 여부는 **전문가 검토 전의 작업 가정**이며 자문이 아니다. 어떤 upstream 계약의 채택도 주장하지 않는다. diff는 `docs/decisions/CAPITAL_LOSS_ALLOWANCE.md` 한 파일이다. `capital/`, `tests/`, `scripts/`, vendor 바이트, 골든, `capital/export.py`, 기존 결정 노트는 건드리지 않는다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `loss-allowance-decision` (Decision: expected-credit-loss allowance mechanics for the COA candidate — timing, basis, reversal, reserve pool link) · deps `accounts-tax-legal-decision`, `portfolio-risk-analytics`, `coa-candidate-projection` · kind `decision` · user_merge `False` |
| 결정자 | **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)** |
| 위임 원문 | 2026-10-08 18:25 KST JunTae Park: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." |
| 결정일 | 2026-10-26 |
| 기준 | KIX-CAPITAL main `aab0a73` · kix-protocol `1bb000b` (읽기 전용 `/workspace/capital-run/kixproto-ro`) · vendor pin `7481b0e16ce9b903abbffa62249bb91cd9e63cfe` 불변 |
| 읽기 범위 | supervisor pack의 허용 경로만 읽었다. `CAPITAL_FINANCIAL_TERMS.md`(`CAPITAL-TERMS-V1`)와 `portfolio-risk-analytics`·`coa-candidate-projection` 노트·코드는 허용 경로 밖이라 **직접 열지 않았다**. 준비금 bps와 `reserve.*` 필드명은 `CAPITAL_ACCOUNTS_TAX_LEGAL.md`·`CAPITAL_DEFAULT_RECOVERY.md`·`CAPITAL_DEMO_BOOK.md`의 인용으로만 참조한다. 이름이나 숫자가 충돌하면 `CAPITAL-TERMS-V1`가 이기고, 시점·게시·대사 규칙은 이 노트가 이긴다 |
| 상태 어휘 | **ADOPTED** = 위임 범위 안의 잠정 값. **UNDETERMINED** = `value: null` + 이유 + `target`. 일곱 항목 모두 ADOPTED이고 각 항목에 `owner`와 `professional_review_required`를 붙였다 |

용어: 금액은 KRW 정수, 날짜는 오버레이 논리 일 `sim_day`, 비율은 bps다. 준비금 비율은 **`CAPITAL-TERMS-V1` `reserve.provision_bps_of_outstanding`** 을 참조하며 이 노트에서 다시 정하지 않는다. 설명용 현재 값은 150 / 500 / 2,500 / 10,000이다. 계정은 `CAPITAL-COA-V1` 1190(차감 자산), 5100(신용손실 비용), 3100(프로토콜 수익 풀), 3200(손실 적립)을 그대로 쓴다.

## 1. 결정 요약

| item | 결정 (요지) | CAP rows | consumer |
|---|---|---|---|
| `allowance_measurement_basis` | **ADOPTED.** 선지급별·단계 버킷별 **수준(level)** 측정. `allowance = floor(effective_principal × bucket_bps / 10,000)`. 버킷은 `T1_PERFORMING`(150), `T2_PERFORMING`(500), `PAST_DUE_OR_ACCELERATED`(2,500), `DEFAULTED`(10,000). 기초는 원금뿐(1110 미수 이자 제외). 측정값은 (FSM 상태, 오버레이 폴드, `sim_day`)의 순수 함수 | CAP-04, CAP-13 | `loss-allowance-postings` |
| `allowance_posting_timing` | **ADOPTED.** 매 틱 게시도 아니고 cut 시에만 게시하는 것도 아니다. **사건 기반 게시점**에서 게시한다. 게시점은 원장 사건(인출·상환·가속 마커·부도 명령·회수·상각·종결)과 파생 단계 전이일(`M*+1`)이며, cut `sim_day` 이하만 접는다. 결과는 cut 요청 횟수와 시계 점프 크기에 의존하지 않는다 | CAP-04, CAP-13, CAP-14 | `loss-allowance-postings` |
| `allowance_true_up_and_reversal` | **ADOPTED.** 게시점마다 선지급별 **차액 true-up**만 한다. 증가는 `Dr 5100 / Cr 1190`, 감소는 `Dr 1190 / Cr 5100`. 전액 환입 후 재게시는 기각. 종결 시 잔액 0으로 해제 | CAP-13 | `loss-allowance-postings` |
| `allowance_after_acceleration_and_default` | **ADOPTED.** 가속 마커일(또는 만기 경과 `M*+1`)부터 2,500 버킷, 부도 명령일 `D`부터 10,000 버킷. 부도 뒤 기초는 실효 원금(FSM outstanding − 오버레이 원금 회수 − 상각 원금). 상각(`UNBUILT_V1`) 시 해당 건의 1190 잔액을 먼저 해제한 뒤 `CAPITAL_DEFAULT_RECOVERY`의 `Dr 5200 / Cr 1100`을 바꾸지 않고 둔다. 상각 뒤 회수는 충당금을 되살리지 않음 | CAP-04, CAP-13 | `loss-allowance-postings`, `coa-payment-writeoff-postings` |
| `reserve_pool_3100_3200_appropriation_link` | **ADOPTED.** 3200 적립은 후보에서 **메모로 둔다**(`RESERVE_POOL_MEMO_V1`). `appropriation_target_krw = Σ1190`, `funded_krw = 0`, `shortfall_krw`만 보고. `Dr 3100 / Cr 3200`은 게시하지 않는다. 폭포 ③ `LOSS_RESERVE`는 `NOT_BOUND` 유지 | CAP-04, CAP-13 | `loss-allowance-postings` |
| `recon_check_allowance_vs_risk_reserve` | **ADOPTED.** 새 후보 검사 `allowance_vs_risk_reserve`. 같은 cut에서 `Σ1190 잔액 == GET /api/risk reserve.requirement_krw`를 정확 일치로 검사(허용 오차 0). cut이 다르면 `CUT_MISMATCH`(통과 아님). 선지급별 drill-down 포함 | CAP-04, CAP-13, CAP-14 | `loss-allowance-postings`, `portfolio-risk-analytics` |
| `cut_scope_and_export_section` | **ADOPTED.** cut = (F04 `state_digest`, 오버레이 digest, 오버레이 `sim_day`), KRW AssetSpec 하나, cut 시점 장부의 모든 선지급. 이번 단계에서 충당금은 export에 **넣지 않는다**(`NOT_IN_EXPORT_V1`; `capital/export.py` 바이트 가드 존중). 후보 투영 응답과 후보 대사에만 나타남 | CAP-13, CAP-14, CAP-15 | `loss-allowance-postings` |

## 2. KIX 비전 연결

- **`/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md` A-4.**
  - 「과거 사실 재생은 새로운 외부 실행 허가가 아님」: 충당금은 기록된 사실을 다시 접어서 얻는 파생값이다. 재계산해도 아무것도 실행되지 않고 현금도 움직이지 않는다.
  - 「로그를 잘라 늦은 사실을 버리는 것은 금지, 늦은 사실은 현재 권한으로 대사」: 늦게 들어온 회수·상각 사실은 그 `sim_day` 게시점에서 true-up으로 반영한다. 과거 게시를 지우지 않는다.
  - 「오프체인 커밋 위치와 체인 확정 위치를 각각 보존」: cut이 F04 digest와 오버레이 digest를 따로 들고 다니는 이유다.
- **`/workspace/capital-run/kixproto-ro/README.md` §1·§3.** R1 v4는 "내구성 있는 경제 엔진"이 아니다. 실자금·실 PG/은행/KYC는 잠겨 있다. 그래서 충당금은 후보 투영 안의 합성 숫자로만 두고 회계 정책 채택으로 올리지 않는다.
- **`docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md` §3.1–§3.3.** 1190 = `reserve.provision_bps_of_outstanding`가 들어갈 자리, 3100 = 3200의 유일한 허용 재원, 분개 형태 "충당 Dr 5100 / Cr 1190, 적립 Dr 3100 / Cr 3200, 종결 시 환입", 차원(`source_cut`·`sim_day`·`terms_version`·`chart_version`), cut 단위 보고 원칙, `BTD_PROVISION` 메모(세무는 `NOT_BOUND`), 검토 항목 "3200 자본 적립 vs 부채성 충당".
- **`docs/decisions/CAPITAL_DEFAULT_RECOVERY.md` §4.1·§4.2·§4.5·§4.10.** `M*`, 부도 명령일 `D`, 상각 적격일 `D+90`, 준비금 원장이 없는 동안 ③ `NOT_BOUND`와 `UNBUILT_V1` 비재작성, 부도 뒤 FSM 잔액이 줄지 않으므로 보존식을 오버레이 항으로 재진술해야 한다는 점.
- **`docs/decisions/CAPITAL_DEMO_BOOK.md` §3.4.** T2 경로의 "500 bps 충당"이 등급 버킷 대응의 증거다. T1 7건과 T2 3건 커버리지가 두 성과 버킷을 모두 바인딩한다.
- **`docs/CAPITAL_REQUIREMENTS_KO.md`·`docs/SEAMS.md`·`docs/VALIDATION.md`(pack 발췌).** 이전 계획을 구현 완료로 옮기지 않는다. ProjectionPort는 `NOT_BOUND`이고 로컬 클래스는 대역이다. `test_coa_candidate.py` 35건이 후보 표면을 지킨다.
- 사용하지 않은 pack 경로: `CAPITAL_ARTIFACT_BUNDLING.md`, `CAPITAL_CLAIM_SLICE_REGISTRY.md`, `CAPITAL_CLOSEOUT_ARTIFACT.md`(발췌만 확인).
- **「포부」의 번역.** 충당금을 선지급 수명 전체에 걸친 결정론적 폴드로 만든다. 같은 cut이면 risk 화면, 후보 원장, 감사 drill-down이 **한 원 단위까지 같은 숫자**를 보이게 한다. 정산 증거로 신용을 가격하는 장부가 감사 가능해진다.

## 3. 항목별 결정

### 3.1 allowance_measurement_basis — ADOPTED
- **값.** 단위는 `advance_id`다. `level(a, d) = floor(effective_principal(a, d) × bps(bucket(a, d)) / 10,000)`이다. 상태가 없는 수준 계산이라 이월 나머지는 없다.
- **버킷 우선순위** (위가 이긴다):
  1. `WRITTEN_OFF` 또는 `CLOSED` → 기초 0
  2. `DEFAULTED`(FSM `DEFAULTED` 또는 `D` 기록) → 10,000
  3. `PAST_DUE_OR_ACCELERATED`(`d ≥ M*+1`, 가속 마커 기록일 포함) → 2,500
  4. `T2_PERFORMING` → 500
  5. `T1_PERFORMING` → 150
- 등급(T1/T2)은 인출 영수증의 `settlement_gate`에서 정한다. 이후 사건으로 등급을 올리지 않는다.
- **기초.** 원금만 쓴다. 부도 전 `effective_principal`은 FSM `outstanding_exposure`이고, 부도 뒤에는 FSM outstanding − 오버레이 원금 회수 − 상각 원금이다. 1110 미수 이자는 제외한다. 부도 뒤 이자는 9700 메모라 자산이 아니고, 상각 때 미수 이자는 환입된다.
- **수식 소유.** 버킷 판정과 `level`은 **단일 함수**이며 `/api/risk`와 후보 투영이 함께 호출한다(§3.6).
- **대안.** 포트폴리오 합계에 한 번만 bps 적용: 선지급별 drill-down과 상각 해제가 불가능해 기각. 미수 이자 포함: 9700 메모와 이중 처리라 기각. 올림: `CAPITAL-TERMS-V1`의 1원 내림 관례와 어긋나 기각.

### 3.2 allowance_posting_timing — ADOPTED
- **값.** 매 `sim_day` 틱에 게시하지 않고, cut 요청 시점에 게시하지도 않는다. 게시점 집합은 다음 둘의 합집합이다.
  - 원장 사건: 인출 수락, 상환 수락, 가속 마커, 부도 명령, `RECOVERY`, `WRITEOFF`, 종결 수락.
  - 파생 전이일: 만기 경과 `M*+1`.
- cut `sim_day` 이하 게시점을 시간순(같은 날은 `after_journal_index` 순)으로 접는다. 각 게시점의 `operation_id`는 원 사건 id이고, 파생 전이는 `STAGE_TRANSITION:<advance_id>:<sim_day>`다.
- **결정론.** 같은 cut이면 같은 분개열이 나온다. projection을 몇 번 요청했는지, 시계를 몇 일씩 전진시켰는지와 무관하다. 오버레이 원장에 새 entry를 **쓰지 않는다**. 충당금은 파생 투영이라 오버레이 digest·`overlay_schema`·`demo.json`이 그대로다.
- **대안.** 매 틱 게시: 하루 단위 노이즈와 분개 폭증, 버킷이 변하지 않는 날은 0원 분개만 나와 기각. cut 시점에만 게시: 같은 장부도 cut 요청 이력에 따라 분개열이 달라져 감사 재생성이 깨지므로 기각.

### 3.3 allowance_true_up_and_reversal — ADOPTED
- **값.** 게시점 `p`마다 `Δ = level(a, p) − carried(a)`를 계산한다. `Δ > 0`이면 `Dr 5100 Δ / Cr 1190 Δ`, `Δ < 0`이면 `Dr 1190 |Δ| / Cr 5100 |Δ|`, `Δ = 0`이면 분개하지 않는다.
- 분개 차원은 `advance_id`, `tier`, `bucket_from`, `bucket_to`, `terms_version`, `chart_version`, `source_cut`, `sim_day`, `operation_id`다.
- 종결 수락 시 `level = 0`이므로 잔액 전부를 해제한다. `CAPITAL-COA-V1`의 "종결 시 환입"이 이 경우다.
- **불변식.** `1190 잔액(a) = level(a, 마지막 게시점)`, `Σ 5100 순액 = Σ 1190 잔액 + Σ 상각 해제액`, 1190은 대변 잔액이거나 0이고 음수가 되지 않는다.
- **대안.** 매 게시점 전액 환입 후 재게시: 5100 총액이 부풀어 손익 해석이 흐려지고 분개가 두 배라 기각.

### 3.4 allowance_after_acceleration_and_default — ADOPTED
- **가속.** 가속 마커 기록일(마진콜 미치유면 치유 마감일 = 앵커)에 `PAST_DUE_OR_ACCELERATED`로 간다. 가속이 없어도 `M*+1`에 같은 버킷으로 간다. 가속은 철회되지 않으므로 버킷도 되돌아가지 않는다(`CAPITAL_DEFAULT_RECOVERY` §4.1).
- **부도.** 부도 명령일 `D`에 `DEFAULTED`(100 % of 실효 원금)로 간다. `D`가 없으면 자동 부도도 없다. 적격일이 지나도 2,500 버킷이 유지되고 `DEFAULT_COMMAND_OVERDUE`는 표시 전용이다. 부도 뒤 회수(①②)로 원금이 줄면 그 회수 게시점에서 감소 true-up을 한다.
- **상각 (`reserve_step_version: UNBUILT_V1`).** `writeoff_effective_sim_day`에 그 건의 1190 잔액 전부를 `Dr 1190 / Cr 5100`(`ALLOWANCE_RELEASE_ON_WRITEOFF_V1`)로 먼저 해제한다. 그다음 `CAPITAL_DEFAULT_RECOVERY`가 정한 `Dr 5200 원금 / Cr 1100`을 **그대로** 둔다. 총 손실(5100 순액 + 5200)은 상각 원금과 같다. COA-V1의 이용형 분개(`Dr 1190 한도 + Dr 5200 초과 / Cr 1100`)는 준비금 바인딩 노드가 `overlay_schema`를 올린 뒤의 목표 형태다.
- **상각 뒤.** 실효 원금 기초는 0이다. 늦은 회수(`Dr 1000 / Cr 4300`)는 충당금을 되살리지 않는다.
- **작업 예시 (T1, 원금 100,000,000).**

| 사건 | sim_day | 버킷 | level | 분개 |
|---|---|---|---|---|
| 인출 | 0 | T1 | 1,500,000 | Dr 5100 / Cr 1190 1,500,000 |
| 상환 40,000,000 | 10 | T1 | 900,000 | Dr 1190 / Cr 5100 600,000 |
| 미치유 가속 | 25 | PD/ACC | 15,000,000 | Dr 5100 / Cr 1190 14,100,000 |
| 부도 명령 | 36 | DEF | 60,000,000 | Dr 5100 / Cr 1190 45,000,000 |
| 상계 회수 원금 10,000,000 | 50 | DEF | 50,000,000 | Dr 1190 / Cr 5100 10,000,000 |
| 상각 | 126 | WO | 0 | Dr 1190 / Cr 5100 50,000,000 → Dr 5200 / Cr 1100 50,000,000 |

5100 순액은 0, 5200은 50,000,000이다. 손실은 상각 원금과 같다.

### 3.5 reserve_pool_3100_3200_appropriation_link — ADOPTED
- **값.** `RESERVE_POOL_MEMO_V1`. 후보 투영은 `Dr 3100 / Cr 3200`을 **게시하지 않는다**. 대신 cut마다 메모 블록 `reserve_pool: {appropriation_target_krw: Σ1190, funded_krw: 0, shortfall_krw: target − funded, status: MEMO_NOT_POSTED, funding_source_ref: "CAPITAL-TERMS-V1 reserve.funding_source → 3100"}`을 보고한다.
- 폭포 ③ `LOSS_RESERVE`는 `NOT_BOUND`와 `absorbed_krw 0`을 유지한다. 1190은 손익 표시이고 손실 흡수 재원이 아니다.
- **근거.** 3100은 결산된 프로토콜 수익 풀이다. 시뮬레이션에는 기간 결산이 없고, 플랫폼 정산 수수료는 Capital 수익이 아니다(`CAPITAL-REVREC-V1`). 따라서 3100 잔액이 없다. 지금 게시하면 존재하지 않는 자본을 만들어 내는 셈이다. 3200의 자본 적립 vs 부채성 충당 분류도 아직 검토 항목이다.
- **게시 전환 조건.** 기간 결산(3100 형성) 노드, 회계사 검토, 준비금 바인딩 노드의 `overlay_schema` 상향. 이 셋이 모두 갖춰져야 한다.
- **대안.** 1190과 같은 금액을 3200에 자동 적립: 미재원 자본을 발명하므로 기각. 3100 음수 허용: 기각.

### 3.6 recon_check_allowance_vs_risk_reserve — ADOPTED
- **값.** 후보 대사 표면에 검사 `allowance_vs_risk_reserve`를 `coa_candidate_totals_vs_v1` 옆에 둔다.
- **술어.** `cut(projection) == cut(risk)`이고 `Σ_a 1190 잔액(a) == reserve.requirement_krw`, 허용 오차 0.
- 결과는 `MATCH`, `MISMATCH{delta_krw, per_advance[]}`, `CUT_MISMATCH{projection_cut, risk_cut}` 중 하나다. `CUT_MISMATCH`는 통과가 아니다.
- 선지급별 행은 `advance_id, bucket, effective_principal, bps, level, carried`다.
- **보조 술어.** `Σ 5100 순액 = Σ1190 + Σ 상각 해제`. 모든 `a`에 대해 `1190(a) ≤ effective_principal(a)`.
- **단일 출처.** 일치를 보장하는 방법은 허용 오차가 아니라 §3.1의 공용 함수를 함께 쓰는 것이다. risk 쪽 반올림이나 버킷이 다르면 검사가 크게 실패하고, 그 경우 risk 노드를 고친다.
- **경계.** V1 `projection_totals_vs_case_views`와 V1 recon `CHECK_IDS`, export에 실리는 대사는 바꾸지 않는다.

### 3.7 cut_scope_and_export_section — ADOPTED
- **cut.** `{f04_state_digest, overlay_digest, overlay_sim_day}`. 범위는 KRW AssetSpec 하나이고, cut 시점 장부의 모든 `advance_id`를 포함한다. 종결·상각 건은 0 행으로 남긴다.
- cut이 다른 두 보고를 하나의 닫힌 잔액으로 합치지 않는다(`CAPITAL-REVREC-V1` cut 의미). 각 분개는 `source_cut`을 갖는다.
- **노출.** 후보 투영 응답의 `allowance` 블록(행·합계·`reserve_pool` 메모)과 후보 대사 검사에만 나온다. 라벨은 `SYNTHETIC_UNADOPTED`·`SIMULATED`·`policy_adopted=false`이고, `tax=NOT_BOUND`이며 `BTD_PROVISION` 메모는 게시하지 않는다.
- **export.** `NOT_IN_EXPORT_V1`. `capital/export.py`와 manifest의 일곱 섹션, `content_digest`는 바이트 불변이다(`tests/test_coa_candidate.py` 가드). 미래 export 섹션 `allowance`는 새 export 버전에서 `SignaturePort` 경계 밖 추가형으로만 연다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "loss-allowance-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-10-26",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "scope": "KIX-CAPITAL simulation and product design only; not an offer; no real money; production NOT_AUTHORIZED; not an accounting policy adoption; accounting_policy SYNTHETIC_UNADOPTED; tax NOT_BOUND; accounting classification and measurement are working assumptions pending professional review; no upstream contract claimed adopted",
  "bases": {"capital_main": "aab0a73", "kix_protocol": "1bb000b", "vendor_pin_commit": "7481b0e16ce9b903abbffa62249bb91cd9e63cfe", "terms_version": "CAPITAL-TERMS-V1", "coa_version": "CAPITAL-COA-V1"},
  "accounting_policy": "SYNTHETIC_UNADOPTED",
  "tax": "NOT_BOUND",
  "consumers": ["loss-allowance-postings"],
  "entries": {
    "allowance_measurement_basis": {
      "status": "ADOPTED",
      "owner": "Capital Accounting Policy Owner (interim: delegated decider; reviewer: accountant designated by JunTae)",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "value": {
        "unit": "advance_id",
        "formula": "level = floor(effective_principal * bucket_bps / 10000)",
        "bps_ref": "CAPITAL-TERMS-V1.reserve.provision_bps_of_outstanding",
        "buckets_in_precedence": [
          {"bucket": "WRITTEN_OFF_OR_CLOSED", "base": 0},
          {"bucket": "DEFAULTED", "bps_at_decision": 10000},
          {"bucket": "PAST_DUE_OR_ACCELERATED", "bps_at_decision": 2500, "entry": "sim_day >= accelerated_maturity_sim_day + 1 or acceleration marker recorded"},
          {"bucket": "T2_PERFORMING", "bps_at_decision": 500},
          {"bucket": "T1_PERFORMING", "bps_at_decision": 150}
        ],
        "tier_source": "draw receipt settlement_gate; never upgraded",
        "effective_principal": "pre-default FSM outstanding_exposure; post-default FSM outstanding - overlay principal recovered - principal written off",
        "accrued_interest_1110_in_base": false,
        "single_source_function": "bucket and level are one shared function called by /api/risk and the COA candidate"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-26",
      "cap_rows": ["CAP-04", "CAP-13"],
      "rationale": "Per-advance stage-bucket levels reuse the decided reserve bps unchanged, enable per-advance drill-down and write-off release, and as a pure function of recorded state stay replayable; principal-only base avoids double counting with the 9700 memo.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "review_items": ["stage mapping versus K-IFRS 1109 three-stage ECL", "principal-only base"]
    },
    "allowance_posting_timing": {
      "status": "ADOPTED",
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "value": {
        "mode": "EVENT_DRIVEN_POSTING_POINTS_FOLDED_TO_CUT",
        "posting_points": ["draw accepted", "repay accepted", "acceleration marker", "default command", "RECOVERY entry", "WRITEOFF entry", "close accepted", "derived transition at accelerated_maturity_sim_day + 1"],
        "order": "sim_day then after_journal_index",
        "derived_operation_id": "STAGE_TRANSITION:<advance_id>:<sim_day>",
        "rejected": ["every sim_day tick", "cut-request-time only"],
        "overlay_journal_writes": "NONE; allowance is a derived projection; overlay digest, overlay_schema and tests/golden/demo.json unchanged",
        "determinism": "same cut gives same posting sequence regardless of request count or clock jump size"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-26",
      "cap_rows": ["CAP-04", "CAP-13", "CAP-14"],
      "rationale": "Event-driven posting points make the posting history a function of facts, not of how often a cut is requested, while avoiding zero-delta daily noise; no journal writes keeps every digest byte-identical.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "allowance_true_up_and_reversal": {
      "status": "ADOPTED",
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "value": {
        "mode": "DELTA_TRUE_UP_PER_ADVANCE",
        "increase": "Dr 5100 / Cr 1190",
        "decrease": "Dr 1190 / Cr 5100",
        "zero_delta": "no posting",
        "close": "level 0 releases full carried balance",
        "dimensions": ["advance_id", "tier", "bucket_from", "bucket_to", "terms_version", "chart_version", "source_cut", "sim_day", "operation_id"],
        "invariants": ["1190(a) equals level at last posting point", "sum 5100 net = sum 1190 + sum write-off releases", "1190 never debit-balance"],
        "rejected": "full reversal and re-post"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-26",
      "cap_rows": ["CAP-13"],
      "rationale": "Delta true-up keeps 5100 equal to the economic change in expected loss and halves posting volume versus reverse-and-repost, matching the CAPITAL-COA-V1 provision and release-at-close pattern.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "allowance_after_acceleration_and_default": {
      "status": "ADOPTED",
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "value": {
        "accelerated": "PAST_DUE_OR_ACCELERATED from acceleration marker day or accelerated_maturity_sim_day + 1; never reverts",
        "defaulted": "DEFAULTED from default_sim_day; no automatic default; overdue default command keeps PAST_DUE_OR_ACCELERATED",
        "post_default_recovery": "decrease true-up at the recovery posting point",
        "writeoff_unbuilt_v1": "ALLOWANCE_RELEASE_ON_WRITEOFF_V1: Dr 1190 / Cr 5100 full carried balance at writeoff_effective_sim_day, then CAPITAL_DEFAULT_RECOVERY Dr 5200 / Cr 1100 unchanged",
        "target_after_reserve_binding": "CAPITAL-COA-V1 utilization form Dr 1190 up to allowance + Dr 5200 excess / Cr 1100 once overlay_schema is bumped by a reserve binding node",
        "after_writeoff": "base 0; late recoveries Dr 1000 / Cr 4300 never re-create allowance",
        "total_loss_identity": "5100 net + 5200 = written-off principal"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-26",
      "cap_rows": ["CAP-04", "CAP-13"],
      "rationale": "Anchoring buckets to the decided acceleration and default dates keeps one date authority, and releasing before the unchanged UNBUILT_V1 write-off leg adds a leg without restating the default-recovery note.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "review_items": ["presentation of 5200 when allowance was fully provided"]
    },
    "reserve_pool_3100_3200_appropriation_link": {
      "status": "ADOPTED",
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "value": {
        "mode": "RESERVE_POOL_MEMO_V1",
        "posted_in_candidate": false,
        "memo": {"appropriation_target_krw": "sum 1190", "funded_krw": 0, "shortfall_krw": "target - funded", "status": "MEMO_NOT_POSTED", "funding_source_ref": "CAPITAL-TERMS-V1.reserve.funding_source -> 3100"},
        "waterfall_step_3": "LOSS_RESERVE stays NOT_BOUND, absorbed_krw 0",
        "post_when": ["period-close node forms a 3100 balance", "accountant review of 3200 equity appropriation vs liability", "reserve binding node bumps overlay_schema"]
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-26",
      "cap_rows": ["CAP-04", "CAP-13"],
      "rationale": "3100 has no balance without a period close and platform settlement fees are not Capital revenue, so posting 3200 would invent equity; a memo with target and shortfall shows the pool gap honestly.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "recon_check_allowance_vs_risk_reserve": {
      "status": "ADOPTED",
      "owner": "Capital Reconciliation Owner",
      "professional_review_required": false,
      "consumer": "loss-allowance-postings",
      "value": {
        "check_id": "allowance_vs_risk_reserve",
        "surface": "COA candidate reconciliation beside coa_candidate_totals_vs_v1; V1 CHECK_IDS unchanged",
        "predicate": "cut(projection) == cut(risk) and sum over advances of 1190 balance == GET /api/risk reserve.requirement_krw",
        "tolerance_krw": 0,
        "outcomes": ["MATCH", "MISMATCH{delta_krw, per_advance[]}", "CUT_MISMATCH{projection_cut, risk_cut}"],
        "cut_mismatch_passes": false,
        "per_advance_row": ["advance_id", "bucket", "effective_principal", "bps", "level", "carried"],
        "auxiliary": ["sum 5100 net == sum 1190 + sum write-off releases", "1190(a) <= effective_principal(a)"],
        "equality_mechanism": "shared bucket and level function, not tolerance"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-26",
      "cap_rows": ["CAP-04", "CAP-13", "CAP-14"],
      "rationale": "Exact equality at a shared cut lets risk, ledger and auditor see the same number; a cut mismatch is reported, never passed.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "cut_scope_and_export_section": {
      "status": "ADOPTED",
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "value": {
        "cut": ["f04_state_digest", "overlay_digest", "overlay_sim_day"],
        "asset": "KRW AssetSpec {fiat, KRW, 0} only",
        "population": "every advance_id in the book at the cut; closed and written-off as zero rows",
        "cross_cut_combination": "FORBIDDEN",
        "surfaces": ["COA candidate projection allowance block (rows, totals, reserve_pool memo)", "candidate reconciliation check"],
        "labels": {"accounting_policy": "SYNTHETIC_UNADOPTED", "tax": "NOT_BOUND", "policy_adopted": false, "label": "SIMULATED"},
        "btd_provision_memo": "NOT_POSTED (tax NOT_BOUND)",
        "export": "NOT_IN_EXPORT_V1; capital/export.py, seven manifest sections and content_digest byte-identical",
        "future_export": "additive allowance section only in a new export version outside the SignaturePort guard"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-26",
      "cap_rows": ["CAP-13", "CAP-14", "CAP-15"],
      "rationale": "A dual-digest cut follows A-4 separation of commit positions, and keeping the allowance out of export respects the export byte guard until a versioned section exists.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

- 노트와 블록: `docs/decisions/CAPITAL_LOSS_ALLOWANCE.md`, `capital-decision-v1` 블록 하나(§4). `decision_ledger.py` 파싱과 `GET /api/decisions` 노출은 supervisor가 병합 시 확인한다. 이 결정자는 읽기 전용이라 실행하지 않았다.
- 재사용: 준비금 bps 150/500/2,500/10,000은 `CAPITAL-TERMS-V1.reserve.provision_bps_of_outstanding`를 참조했고, 코드 1190/5100/3100/3200은 `CAPITAL-COA-V1`을 썼다. 두 노트 모두 수정하지 않았다.
- 상태와 라벨: 일곱 항목 모두 ADOPTED이고 `owner`와 `professional_review_required`가 있다. `accounting_policy: SYNTHETIC_UNADOPTED`, `tax: NOT_BOUND`.
- 소비자: 모든 entry와 블록 `consumers`에 `loss-allowance-postings`를 적었다. `python3 scripts/decision_bindings.py --check`는 supervisor가 실행해야 한다(미실행).

## 6. Open risks

- **pack 밖 입력.** `CAPITAL-TERMS-V1`의 버킷↔bps 대응 중 2,500 = 연체·가속, 10,000 = 부도는 인용으로 추론했다. 500 = T2는 `CAPITAL_DEMO_BOOK` §3.4로 확인했다. 필드 구조가 다르면 TERMS가 이긴다.
- **risk 수식 미확인.** `portfolio-risk-analytics`의 `reserve.requirement_krw` 계산을 직접 읽지 않았다. 반올림이나 버킷이 다르면 검사가 실패한다. 의도된 실패이며 공용 함수로 맞춰야 한다.
- **5200 표시.** `UNBUILT_V1`에서는 해제 후 5200에 전액을 차변하므로, 충당을 다 쌓은 건도 "충당 초과 손실"로 보인다. 총 손실은 같다. 준비금 바인딩 뒤 이용형으로 바꾸면 해결된다.
- **보존식.** 부도 건의 1100 보존식 재진술(`CAPITAL_DEFAULT_RECOVERY` §4.10)을 `coa-payment-writeoff-postings`가 하지 않으면 실효 원금 기초가 FSM 잔액과 어긋난다.
- **회계 작업 가정.** 단계 매핑과 K-IFRS 1109 ECL(12개월/전기간) 사이의 정합, 원금 전용 기초, 3200 분류, 충당금 손금 불산입(`BTD_PROVISION`)은 전문가 검토 대상이다.

## 7. 후속 작업

- **`loss-allowance-postings`.**
  - 공용 `bucket`/`level` 함수를 만들고 risk와 공유한다.
  - 게시점 폴드, true-up 분개, `ALLOWANCE_RELEASE_ON_WRITEOFF_V1`, `reserve_pool` 메모, 검사 `allowance_vs_risk_reserve`를 구현한다.
  - §3.4 예시를 결정론 벡터로 만든다. `tests/vectors/`에 추가하면 `scripts/docs_surface.py` 항목과 README needle을 함께 넣는다.
  - `capital/export.py`는 바꾸지 않는다.
- **`portfolio-risk-analytics`.** `reserve.requirement_krw`를 공용 함수로 계산하고 cut 삼중값을 응답에 싣는다.
- **`coa-payment-writeoff-postings`.** 해제 다리 다음에 5200 다리를 두는 순서와 1100 보존식 재진술을 맞춘다.
- **미래 준비금 바인딩·기간 결산 노드.** 3100 형성, 3200 게시, 이용형 상각, `overlay_schema` 상향을 맡는다.
- **`f04-real-funds-lift-criteria` 질문지.** §6의 회계·세무 검토 항목을 전달한다.
