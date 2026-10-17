# Capital 부도 후 회수·상각·이자 재기준 결정 — 회수 폭포, 상각일, 가속 후 이자 rebase

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
이 문서는 KIX-CAPITAL 저장소 안의 **시뮬레이션·제품 설계용** 결정이다. 청약이나 대출 제안이 아니고, 실자금이 움직이지 않으며, production은 계속 `NOT_AUTHORIZED`다. 법률·세무·회계 관련 내용(상계 효력, 상각 시점, 이자 인식, 시효)은 **전문가 검토 전의 작업 가정(WORKING ASSUMPTION)** 이며 자문이 아니다. 어떤 upstream 계약의 채택도 주장하지 않는다. diff는 `docs/decisions/CAPITAL_DEFAULT_RECOVERY.md` 한 파일이고, `capital/`·`tests/`·vendor 바이트·골든·기존 결정 노트의 상태 토큰은 건드리지 않는다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `default-recovery-decision` (Decision: default recovery waterfall, write-off day and interest rebase after acceleration) · deps `margin-cure-default`, `setoff-proposal-quote`, `financial-terms-decision`, `overlay-state-decision`, `sim-clock-ledger` · kind `decision` · user_merge `False` |
| 결정자 | **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)** |
| 위임 원문 | 2026-10-08 18:25 KST JunTae Park: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." |
| 결정일 | 2026-10-17 |
| KIX-CAPITAL 기준 | main `b442b6a` |
| kix-protocol 기준 | `244595d` (읽기 전용 `/workspace/capital-run/kixproto-ro`) |
| 상태 어휘 | **ADOPTED** = 위임 범위 안의 잠정 값. **UNDETERMINED** = 값을 정할 수 없어 이유만(`value: null`). 열 항목 모두 ADOPTED |

용어: 금액은 KRW 정수, 날짜는 오버레이 논리 일 `sim_day`(정수), 비율은 bps다. 숫자 상수(유예 10일, 상각 90일, 연체 가산 300 bps, 치유 5일, 2인 임계 50,000,000원)는 **`CAPITAL-TERMS-V1`의 필드를 참조**하며 이 노트에서 다시 정하지 않는다. 아래 괄호의 값은 설명용 현재 값이다.

## 1. 결정 요약

| item | 결정 (요지) | CAP rows | 소비 노드 / seam |
|---|---|---|---|
| `acceleration_interest_rebase` | **ADOPTED.** 가속 = 만기 재기준. `M* = min(현재 만기, 앵커일)`(마진콜은 앵커 = 치유 마감일). 연체이자는 `M*+1`부터, 부도 적격일은 `M*+유예+1`. 소급 재계산·복리·가속 철회·연장 없음. `/api/overlay`의 `NOT_REBASED / DECISION_REQUIRED`를 `REBASED`(필드 포함) 또는 `NOT_ACCELERATED`로 교체 | CAP-01, CAP-04 | `overlay-recovery-writeoff` |
| `writeoff_trigger_and_day_basis` | **ADOPTED.** 상각 적격일 = **부도 명령일(`default_sim_day`) + 상각 대기일(90)**. 가속일·부도 적격일 기준이 아님. 상각 기록은 운영자 명령이며 자동 게시 없음 | CAP-01, CAP-04 | `overlay-recovery-writeoff`, `coa-payment-writeoff-postings` |
| `recovery_entry_schema` | **ADOPTED.** 오버레이 저널 entry 종류 `RECOVERY`·`WRITEOFF`. 부도 뒤에만 존재(부도 전은 FSM `repay`). 정수 KRW, 벽시계 키 금지, 개인정보 없음, `label: SIMULATED` | CAP-04, CAP-11 | `overlay-recovery-writeoff` |
| `waterfall_steps_in_scope` | **ADOPTED.** ① 결합 청구 배분 상계 **postable**, ② 같은 수익자 다른 청구 상계 **postable**(조건부), ③ 손실준비금 **not postable**(준비금 원장 없음), ④ 플랫폼 상각 **postable** | CAP-04 | `overlay-recovery-writeoff` |
| `reserve_step_when_unbuilt` | **ADOPTED.** 준비금 원장이 없는 동안 ③은 `NOT_BOUND`로 **0원 흡수 + 명시 표지**, 전액이 ④로 간다. 가상 준비금을 만들지 않고, 나중에 원장이 생겨도 소급 재작성하지 않음 | CAP-04 | `overlay-recovery-writeoff`, `coa-payment-writeoff-postings` |
| `late_recovery_after_writeoff` | **ADOPTED.** 상각 뒤 회수는 허용(시뮬레이션 만료 없음). 잔여 청구액 한도, 이자 없음, 전액 4300(현금주의), 케이스·FSM 재개 없음 | CAP-01, CAP-04, CAP-14 | `overlay-recovery-writeoff`, `coa-payment-writeoff-postings` |
| `interest_stop_rule` | **ADOPTED.** 발생은 종결일 또는 **상각 적격일**(제외) 중 먼저 오는 날 멈춘다. 부도 명령일부터는 메모(9700) 발생, 상각 뒤 잔여 청구에는 이자 없음 | CAP-01, CAP-13 | `overlay-recovery-writeoff`, `coa-payment-writeoff-postings` |
| `recovery_authority` | **ADOPTED.** 부도·회수·상각은 사람 전용, 50,000,000원 초과는 2인, AI는 제안만. 소비 노드 `overlay-recovery-writeoff`, `coa-payment-writeoff-postings` | CAP-01, CAP-04, CAP-19 | 두 소비 노드 |
| `loss_attribution` | **ADOPTED.** 손실 부담 KIX Capital 플랫폼 100 %, 트랜치 없음. 상각은 회계 메모이며 수익자 채무 면제가 아니다(잔여 청구 유지) | CAP-04 | `overlay-recovery-writeoff`, `coa-payment-writeoff-postings` |
| `digest_and_coa_effect` | **ADOPTED.** 오버레이 digest에만 반영(빈 `recovery`는 키 부재, `overlay_schema` 1 유지), F04 digest·`demo.json` 불변, export는 `overlay` 섹션 안에만, COA는 1000/1100/1110/4100/4110/4300/5200/9700 사용 | CAP-11, CAP-13, CAP-14 | `coa-payment-writeoff-postings`, `export-manifest` |

## 2. 작업 예시 (가속된 선지급, T1)

| 사건 | sim_day | 계산 |
|---|---|---|
| 인출, 기간 60일 | 0 | 원 만기 60 |
| 마진콜 발생, 치유 마감 | 20 → 25 | 20 + 치유 5일 |
| 미치유 → 가속 | `M* = 25` | `min(60, 25)` |
| 연체이자 시작 | 26 | `M* + 1` |
| 부도 적격일 | 36 | `M* + 유예 10 + 1` |
| 운영자 부도 명령 `D` | 36 | 사람 명령 |
| 메모 발생 구간 | 36 ~ 125 | 9700 인식 유예 |
| 상각 적격일 = 이자 발생 중단일 | **126** | `D + 90`, 126일째는 발생하지 않음 |

부도 명령 전에 UI와 `/api/overlay`가 보이는 `earliest_writeoff_sim_day`는 부도 적격일 + 90 = 126이다.

## 3. KIX 비전 연결 — 읽은 pack 경로

- `/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md` (A-4). 두 가지를 가져왔다.
  - 「과거 사실의 재생은 새로운 외부 실행 허가가 아니다」: 회수·상각 entry를 재생해도 아무것도 실행되지 않는다.
  - 「로그를 잘라 늦은 사실·반환 의무를 버리는 것은 금지, 늦은 사실은 현재 권한으로 대사」: 상각이 청구를 지우지 않고, 상각 뒤 회수를 append-only로 계속 받는다.
  - 「예약 확정 ≠ 결제 확인」: 회수 금액은 현금 수취 확정이 아니라 `SIMULATED` 메모다.
- `/workspace/capital-run/kixproto-ro/README.md` §1·§3. 현재는 mock·비운영 범위이고 실자금·실 PG/은행/KYC는 잠겨 있다. 그래서 `DECISION_REQUIRED` 표지를 값으로 바꾸되 실집행 의미는 주지 않는다.
- `docs/decisions/CAPITAL_FINANCIAL_TERMS.md` §3.1(연체이자 +300 bps, `accrual_stop`), §3.3(유예·부도 적격일), §3.4(회수 폭포·90일 상각·플랫폼 100 %), §3.7(치유 5일·가속), §3.8(집행 권한), §3.9(준비금).
- `docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md` §3.1(`CAPITAL-COA-V1` 계정), §3.2(`DEFAULTED` 뒤 인식 유예·4300 현금주의).
- `docs/decisions/CAPITAL_OVERLAY_DIGEST_EXPORT.md` §3.1~§3.4(분리 digest, V3 `overlay` 섹션, 빈 overlay = 부재, 명시적 CAS 시계).
- `docs/CAPITAL_REQUIREMENTS_KO.md`·`docs/SEAMS.md`·`docs/VALIDATION.md` (pack 발췌만 사용). 이전 계획의 존재를 구현 완료로 옮기지 않는다. `actor`는 인증이 아니므로 2인 원칙은 시뮬레이션 통제다. 실자금·은행 exactly-once를 추론하지 않는다.
- 사용하지 않은 pack 경로: `CAPITAL_ARTIFACT_BUNDLING.md`, `CAPITAL_CLOSEOUT_ARTIFACT.md`, `CAPITAL_DEMO_BOOK.md`.
- 「포부」의 번역: 부도 이후의 수명을 모두 결정론적 폴드(시계 입력 → 날짜·금액)로 만들고, 폭포의 단계별 결과를 `waterfall_trace`로 남긴다. 그래야 회계·감사·재생이 가능하다.

## 4. 항목별 결정

### 4.1 acceleration_interest_rebase — ADOPTED
- **값.** 이자는 원금 잔액에 대한 단리 일할이라 선계산 이자가 없고, 가속이 바꾸는 것은 만기·연체이자 시작일·부도 적격일뿐이다. `M* = min(현재 만기, 앵커일)`이다. 마진콜 미치유는 앵커 = 치유 마감일이고, 도산 통지·증거 위조는 앵커 = 운영자가 기록한 사건 `sim_day`(치유 창 없음)이다. 연체이자(티어 all-in + 가산)는 `M*+1`부터 적용된다. 그 이전 날들은 계약 금리 그대로이고 **소급 재계산·복리는 없다**. 부도 적격일은 `M*+유예+1`로 유예 길이는 줄이지 않는다. 가속은 철회되지 않고(늦은 부분 상환이 있어도 `M*` 유지) 가속 뒤 연장은 거절된다. 나중 마커는 만기를 더 앞으로만 당길 수 있다. 총비용 상한은 T1 1,000 / T2 1,600 bps로 2,000 bps 안이다.
- **결정론.** 폴드는 마커와 `sim_day`의 순수 함수다. 시계를 한 번에 최대 366일 전진시켜도 일별 금리가 만기 대비 날짜로 정해지므로 결과가 같다.
- **`/api/overlay` 표지.** 가속된 건은 `status: REBASED` + `accelerated_maturity_sim_day`, `default_interest_from_sim_day`, `default_eligible_sim_day`, `earliest_writeoff_sim_day`(부도 뒤에는 `writeoff_sim_day`). 가속 안 된 건은 `NOT_ACCELERATED`다. `DECISION_REQUIRED`는 더 나오지 않는다.
- **대안.** 가속일부터 연체이자: 치유 창 안의 날을 소급 처벌해 기각. 부도 적격일부터: 유예 전 구간이 계약 금리라 가속 의미가 없어 기각. 가속 철회 허용: 되돌림 때문에 폴드 단조성이 깨져 기각.
- **비마진 사건의 기록.** 도산·위조 사건 기록 명령은 사람 전용이며 `overlay-recovery-writeoff`가 만든다.

### 4.2 writeoff_trigger_and_day_basis — ADOPTED
- **값.** `D`는 승인된 FSM `default` 명령의 오버레이 entry에 기록된 `sim_day`다. 이 entry가 없으면 409 `DEFAULT_DAY_UNKNOWN`으로 닫고 추정하지 않는다. 상각 적격일 = `D + 90`(`sim_day ≥ D+90`). 기준은 부도 명령일뿐이며 가속일이나 부도 적격일이 아니다. 상각 게시는 운영자 명령이고 틱이 자동으로 게시하지 않는다. 전제는 FSM `DEFAULTED`, 적격일 도달, 실효 원금 > 0, `waterfall_trace` 완비다. 관측되었으나 소비되지 않은 상계 재원이 남아 있으면 `setoff_declined_reason` 없이는 409 `WRITEOFF_SETOFF_AVAILABLE`로 거절한다. 늦게 게시해도 `writeoff_effective_sim_day`는 적격일이고 이자는 이미 그날 멈췄다.
- **부도 명령이 없으면.** 자동 부도·자동 상각은 없다(AI·자동 경계). 적격일 후 30 sim_day가 지나면 표시 전용 플래그 `DEFAULT_COMMAND_OVERDUE`를 낸다. 이 구간의 이자는 `4110` 인식 상태로 계속 발생한다.
- **근거.** 터미널이고 시간 정보가 없는 FSM `default`에 금융 의미를 붙이려면 날짜의 앵커가 하나여야 한다. 부도 명령일은 사람이 기록한 유일한 부도 사실이다.
- **기초.** WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW — 상각 시점·손실 인식.

### 4.3 recovery_entry_schema — ADOPTED
- **공통 필드.** `entry_id`(= `operation_id`, dedup), `entry_kind`(`RECOVERY`|`WRITEOFF`), `advance_id`, `claim_id`, `beneficiary_role`, `tier`, `sim_day`, `after_journal_index`, `phase`(`POST_DEFAULT`|`POST_WRITEOFF`), `label: SIMULATED`, `authority{role, approvals[], proposal_id?}`.
- **RECOVERY.** `waterfall_step`(①②만), `amount_krw`(≥1), `allocation{default_interest_krw, interest_krw, principal_krw}`(`POST_DEFAULT`만), `residual_claim_krw`(`POST_WRITEOFF`만), `source_ref{claim_id, payee_label, source_cut}`, `quote_ref`(`setoff-proposal-quote` 산출 식별자).
- **WRITEOFF.** `default_sim_day`, `writeoff_effective_sim_day`, `writeoff_principal_krw`, `accrued_interest_reversed_krw`, `suspended_interest_released_krw`, `residual_claim_krw`, `waterfall_trace[4]{step, status, absorbed_krw}`, `reserve_binding: NOT_BOUND`, `loss_krw`, `loss_bearer`.
- **불변식.** 금액은 정수 KRW다. `VOLATILE_KEYS`(`instance_id`·`created_at`·`saved_at`·`timestamp`·`timestamps`)와 개인정보는 쓸 수 없다(400 `OVERLAY_VOLATILE_KEY`). 같은 `(claim_id, payee line)` 재원은 모든 선지급을 통틀어 관측 배분액까지만 소비한다(409 `RECOVERY_SOURCE_EXCEEDED`). 회수 합계는 청구 한도를 넘지 못한다(409 `RECOVERY_EXCEEDS_CLAIM`). 부도 전 호출은 409 `RECOVERY_NOT_DEFAULTED`다.
- **배분.** 상각 전 부도 후 회수는 연체(`DEFAULT`) 이자 → 계약 이자 → 원금 순이며 게시 시 1원 내림·이월은 `CAPITAL-TERMS-V1`과 같다. 상각 뒤에는 배분하지 않는다(§4.6).

### 4.4 waterfall_steps_in_scope — ADOPTED
- ① `SETOFF_BOUND_CLAIM_BENEFICIARY_DISTRIBUTION`: **postable.** FSM `DEFAULTED` 뒤, 결합 청구에서 수익자 payee에게 배분된 것으로 **관측된** 현금에 대해, `setoff-proposal-quote`의 견적 이하로만 게시한다. 부도 전의 같은 상계는 기존대로 FSM `repay`다.
- ② `SETOFF_OTHER_CLAIMS_SAME_BENEFICIARY`: **postable(조건부).** ①의 조건에 더해 원천 청구가 결합 청구와 다르고 `beneficiary_payee_map`으로 같은 수익자에 매핑되며 견적이 있어야 한다. 견적이 없으면 게시할 수 없다. 법적 효력은 `NOT_ASSESSED`다.
- ③ `LOSS_RESERVE`: **not postable** (§4.5).
- ④ `PLATFORM_WRITEOFF`: **postable** (§4.2).
- **순서 규칙.** ④는 ①②를 시도한 뒤에만 열린다(`waterfall_trace`가 증거). 외부 회수(양수 채권 추심·법적 회수)는 실제 수금이 범위 밖이라 V1 postable이 아니다. 관람권 압류·티켓 이전·권리 취소·토큰 압류는 영구 금지다.
- **기초.** WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW — 상계의 법적 효력·도산 시 지위.

### 4.5 reserve_step_when_unbuilt — ADOPTED
- **값.** 준비금 원장(`SIM_LOSS_PROVISION`, `SIM_RESERVE_POOL`)이 없는 동안 ③은 `{step: LOSS_RESERVE, status: NOT_BOUND, absorbed_krw: 0}`을 남기고 전액이 ④로 간다. 상각 entry에는 `reserve_binding: NOT_BOUND`, `reserve_step_version: UNBUILT_V1`을 박는다. `CAPITAL-TERMS-V1`의 충당 bps(150/500/2,500/10,000)를 잔액으로 가정하지 않는다. COA는 `1190`·`5100`·`3100`·`3200`을 게시하지 않고 `5200`에 원금 전액을 차변한다.
- **재작성 금지.** 원장이 나중에 생겨도 `UNBUILT_V1` entry는 소급 재작성하지 않는다. 바인딩 노드가 `overlay_schema`를 올리고 새 골든을 추가한다(이전은 재생 벡터).
- **근거.** 준비금은 플랫폼 수익 풀이라 총 플랫폼 손실은 같고 손익 표시(`5200` 대 `5100/1190`)만 다르다. 막으면 부도 노출이 영구히 남는다.

### 4.6 late_recovery_after_writeoff — ADOPTED
- **값.** 상각 뒤 회수는 허용한다(`phase: POST_WRITEOFF`, 시뮬레이션 만료 없음). 한도는 `residual_claim_krw = 상각 원금 + 적격일까지의 미수 이자 − 이후 회수 합`이다. 이자는 더 붙지 않고, 배분 없이 **전액 `Dr 1000 / Cr 4300`(현금주의)** 이다. FSM은 `DEFAULTED`·노트 `NOTED` 그대로이며 케이스를 되살리지 않고 FSM `repay`도 쓰지 않는다. 준비금 보충은 자동이 아니다. 원천은 ①②의 상계 재원뿐이다.
- **기초.** WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW — 소멸시효·상각 후 회수의 회계 처리.

### 4.7 interest_stop_rule — ADOPTED
- **값.** 발생은 인출일 포함, 종료일 제외다. 종료일은 종결(상환일) 또는 상각 적격일 `D+90` 중 먼저 오는 날이다. `D ≤ d < D+90`의 이자는 같은 금리(티어 all-in + 연체 가산)로 계산하되 `9700` 메모에 두고 현금 수령 시에만 `4110`으로 인식한다. 상각 시 인식된 미수 이자는 환입하고 메모는 손익 없이 해제한다. 상각 뒤 잔여 청구에는 이자·연체이자가 붙지 않는다. 이자에 이자는 없다.
- **근거.** `accrual_stop: AT_CLOSE_OR_WRITEOFF`와 `CAPITAL-REVREC-V1` 인식 유예를 한 규칙으로 닫는다. 게시 시점이 아니라 적격일에서 멈추므로 늦은 게시가 메모를 부풀리지 않는다.

### 4.8 recovery_authority — ADOPTED
- **값.** FSM `default` 명령, 회수 게시, 상각 게시, 비마진 가속 사건 기록은 사람 운영자 전용이다. 금액이 `underwriting_depth.two_person_threshold_krw`(50,000,000원) 이하면 1인, **초과면 서로 다른 `approver_label` 2개 이상**이 필요하다(409 `TWO_PERSON_REQUIRED`). 금액 기준은 부도 = FSM 잔액 원금, 회수 = `amount_krw`, 상각 = `writeoff_principal_krw`다. 같은 `advance_id`에 대해 같은 `sim_day`의 회수 합계를 누적해 임계값을 비교한다(쪼개기 회피 차단).
- **AI.** 제안만 한다(`executionAuthorized=false`). 제안 종류는 `DEFAULT_ELIGIBLE`·`RECOVERY_SETOFF`·`WRITEOFF`이고, agent lane의 게시 시도는 403 `RECOVERY_AGENT_FORBIDDEN`으로 거절하며 기록하지 않는다. 운영자가 채택하면 별도 명령이 `proposal_id`를 인용한다. 제안은 승인으로 세지 않는다.
- **한계.** 2인 원칙은 시뮬레이션 통제다. 라벨은 인증이 아니다(`LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED`).
- **소비 노드.** `overlay-recovery-writeoff`(폴드·명령·거절 코드·`/api/overlay` 필드), `coa-payment-writeoff-postings`(분개).

### 4.9 loss_attribution — ADOPTED
- **값.** 손실 부담은 `KIX_CAPITAL_PLATFORM_100_PERCENT`, 트랜치 없음(`loss_bearer_v1`). `loss_krw`는 상각 원금에서 ③ 흡수액(현재 0)을 뺀 값이다. 고객 예치금·주최자 정산금·F03 환불준비금·토큰 재무·관람권 보유자에게 손실을 귀속하거나 상계하지 않는다. 상각은 회계 메모이며 수익자 채무의 면제가 아니다(`claim_status: RESIDUAL_CLAIM_RETAINED`).
- **재검토.** CAP-03 채권 매입 또는 투자자 참여가 생기면 연다.
- **기초.** WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW.

### 4.10 digest_and_coa_effect — ADOPTED
- **digest.** `RECOVERY`·`WRITEOFF`은 오버레이 저널 entry이고 `overlay_state.digest`의 폴드 `state.recovery`에 들어간다. entry가 없으면 `recovery` 키가 없어서(빈 = 부재) `overlay_schema`는 1 그대로다. F04 `state_digest`, `payload_sha256`, `tests/golden/demo.json`은 불변이다. 새 골든은 `tests/golden/overlay_recovery.json`(인출 → 미치유 마진콜 → 부도 → 상계 회수 → 상각 → 늦은 회수)이다. 기존 오버레이 골든이 가속된 선지급을 포함하면 digest가 바뀌므로 이 노트를 인용해 재생성한다.
- **export.** 회수 데이터는 V3 `overlay` 섹션 안에만 나타난다. 기존 일곱 섹션, 서명 대상(`content_digest`), recon `CHECK_IDS`는 바뀌지 않는다. 불변식은 쓰기 시점과 로드 시 폴드 재검증에서 닫는다.
- **COA** (`CAPITAL-COA-V1`).
  - 회수 현금 R: `Dr 1000 R / Cr 1100`(원금 몫), `Cr 1110`(인식된 미수 이자 몫), `Cr 4110`(9700 메모 이자 몫, 현금 수령 시 인식). 이자 몫은 오래된 날부터 배분한다. 9700 해제의 상대 메모 다리는 소비 노드가 정한다.
  - 상각: `Dr 5200 원금 / Cr 1100`, 미수 이자 환입 `Dr 4100·4110 / Cr 1110`, 9700 해제(손익 없음). `1190`·`5100`·`3100`·`3200`은 게시하지 않는다.
  - 늦은 회수: `Dr 1000 / Cr 4300`.
  - 부도 후 FSM 잔액은 줄지 않으므로 FSM 합계에 묶인 COA 보존식은 부도 건에서 오버레이 항으로 재진술해야 한다. 예: `1100 = Σ(FSM.outstanding − 오버레이 원금 회수 − 상각 원금)`. `9150`·`9160`도 같다.

## 5. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "default-recovery-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-10-17",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "scope": "KIX-CAPITAL simulation and product design only; not an offer; no real money; production NOT_AUTHORIZED; legal, tax and accounting content are working assumptions pending professional review; no upstream contract claimed adopted",
  "bases": {"capital_main": "b442b6a", "kix_protocol": "244595d", "terms_version": "CAPITAL-TERMS-V1", "coa_version": "CAPITAL-COA-V1"},
  "entries": {
    "acceleration_interest_rebase": {
      "status": "ADOPTED",
      "value": {
        "mode": "REBASE_MATURITY_NO_RETROACTION",
        "applies_to_events": ["MARGIN_CALL_UNCURED", "BENEFICIARY_INSOLVENCY_NOTICE", "EVIDENCE_FRAUD_FINDING"],
        "anchor_sim_day": {"MARGIN_CALL_UNCURED": "cure_deadline_sim_day = margin_call_sim_day + cure_window_days", "BENEFICIARY_INSOLVENCY_NOTICE": "operator_recorded_event_sim_day", "EVIDENCE_FRAUD_FINDING": "operator_recorded_event_sim_day"},
        "accelerated_maturity_sim_day": "min(current_maturity_sim_day, anchor_sim_day)",
        "default_interest_from_sim_day": "accelerated_maturity_sim_day + 1",
        "default_eligible_sim_day": "accelerated_maturity_sim_day + grace_days_after_maturity + 1",
        "rate_through_accelerated_maturity": "tier all-in rate unchanged",
        "rate_after_accelerated_maturity": "tier all-in rate + default_interest_add_bps_annual",
        "retroactive_recalculation": "NONE",
        "compounding": "NONE",
        "reversal_after_late_cure_or_partial_repay": "NONE",
        "extension_after_acceleration": "REJECTED",
        "maturity_monotone": "later markers can only move maturity earlier",
        "determinism": "pure fold of recorded markers and sim_day; independent of tick granularity",
        "cost_cap_check": "tier all-in + default add <= all_in_cost_cap_bps_annual",
        "non_margin_event_recording": "human operator command, two-person above threshold, owned by overlay-recovery-writeoff",
        "api_overlay_marker": {"replaces": "NOT_REBASED / DECISION_REQUIRED", "accelerated": {"status": "REBASED", "fields": ["accelerated_maturity_sim_day", "default_interest_from_sim_day", "default_eligible_sim_day", "earliest_writeoff_sim_day", "writeoff_sim_day_after_default"]}, "not_accelerated": {"status": "NOT_ACCELERATED"}},
        "terms_refs": ["CAPITAL-TERMS-V1.interest_rate.default_interest_add_bps_annual", "CAPITAL-TERMS-V1.term.grace_days_after_maturity", "CAPITAL-TERMS-V1.additional_margin.cure_window_days", "CAPITAL-TERMS-V1.additional_margin.uncured_consequence"]
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Interest is simple daily accrual on outstanding principal, so acceleration only moves maturity, default-interest start and default eligibility; a min() anchor keeps maturity monotone, no retroactive default rate avoids penalising days inside the cure window, and a pure fold keeps replay deterministic across clock jumps.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "writeoff_trigger_and_day_basis": {
      "status": "ADOPTED",
      "value": {
        "default_sim_day_source": "sim_day on the overlay entry of the accepted FSM default command; absent -> 409 DEFAULT_DAY_UNKNOWN, no guessing",
        "writeoff_eligible_sim_day": "default_sim_day + writeoff_days_after_default",
        "anchor": "default command day only; never acceleration day or default-eligible day",
        "day_basis": "calendar sim_day integers; eligible when sim_day >= default_sim_day + writeoff_days_after_default",
        "earliest_writeoff_sim_day_before_default": "default_eligible_sim_day + writeoff_days_after_default",
        "posting": "OPERATOR_COMMAND_ONLY_NO_AUTOMATIC_POSTING",
        "preconditions": ["FSM state DEFAULTED", "sim_day >= writeoff_eligible_sim_day", "effective principal > 0", "waterfall_trace complete", "setoff_declined_reason required when observed unconsumed set-off sources > 0, else 409 WRITEOFF_SETOFF_AVAILABLE"],
        "late_posting": "allowed; writeoff_effective_sim_day stays the eligible day and interest already stopped there",
        "no_default_command": "no automatic default or write-off; accrual continues recognized; display-only flag DEFAULT_COMMAND_OVERDUE 30 sim_days after default eligibility",
        "worked_example": {"draw": 0, "original_maturity": 60, "margin_call": 20, "cure_deadline": 25, "accelerated_maturity": 25, "default_interest_from": 26, "default_eligible": 36, "default_command": 36, "writeoff_eligible": 126},
        "terms_refs": ["CAPITAL-TERMS-V1.default_loss_treatment.writeoff_days_after_default"]
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "The pinned FSM default is terminal and carries no time, so the only human-recorded default fact is the operator command day; anchoring write-off there gives one auditable date, and operator-only posting keeps the no-automatic-transition boundary.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "review_items": ["write-off timing and loss recognition under applicable accounting standards"]
    },
    "recovery_entry_schema": {
      "status": "ADOPTED",
      "value": {
        "journal": "overlay journal (second journal); fold key state.recovery; key absent when no entries",
        "entry_kinds": ["RECOVERY", "WRITEOFF"],
        "existence": "only after FSM DEFAULTED; pre-default set-off stays on the FSM repay path",
        "common_fields": ["entry_id (= operation_id, dedup)", "entry_kind", "advance_id", "claim_id", "beneficiary_role", "tier", "sim_day", "after_journal_index", "phase (POST_DEFAULT | POST_WRITEOFF)", "label (SIMULATED)", "authority {role, approvals[], proposal_id?}"],
        "recovery_fields": ["waterfall_step (step 1 or 2 only)", "amount_krw (>= 1)", "allocation {default_interest_krw, interest_krw, principal_krw} (POST_DEFAULT only)", "residual_claim_krw (POST_WRITEOFF only)", "source_ref {claim_id, payee_label, source_cut}", "quote_ref (from setoff-proposal-quote)"],
        "writeoff_fields": ["default_sim_day", "writeoff_effective_sim_day", "writeoff_principal_krw", "accrued_interest_reversed_krw", "suspended_interest_released_krw", "residual_claim_krw", "waterfall_trace [4] {step, status, absorbed_krw}", "reserve_binding (NOT_BOUND)", "loss_krw", "loss_bearer"],
        "allocation_order": ["DEFAULT_INTEREST", "INTEREST", "PRINCIPAL"],
        "rounding": "floor to 1 KRW at posting, carry remainder (CAPITAL-TERMS-V1)",
        "forbidden_keys": ["instance_id", "created_at", "saved_at", "timestamp", "timestamps", "any personal data"],
        "source_conservation": "sum of recoveries per (claim_id, payee line) across all advances <= observed distribution to the beneficiary",
        "rejects": ["409 RECOVERY_NOT_DEFAULTED", "409 RECOVERY_SOURCE_EXCEEDED", "409 RECOVERY_EXCEEDS_CLAIM", "409 WRITEOFF_NOT_ELIGIBLE", "409 WRITEOFF_SETOFF_AVAILABLE", "409 DEFAULT_DAY_UNKNOWN", "409 TWO_PERSON_REQUIRED", "403 RECOVERY_AGENT_FORBIDDEN", "400 OVERLAY_VOLATILE_KEY"],
        "lost_response": "lookup by operation_id else UNKNOWN, no automatic retry"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-04", "CAP-11"],
      "rationale": "The pinned FSM is terminal after DEFAULTED so recoveries cannot be repay commands; a typed append-only overlay entry with integer money, no wall-clock keys and an explicit waterfall trace makes the post-default life replayable and auditable without touching vendor bytes.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "waterfall_steps_in_scope": {
      "status": "ADOPTED",
      "value": {
        "order": ["SETOFF_BOUND_CLAIM_BENEFICIARY_DISTRIBUTION", "SETOFF_OTHER_CLAIMS_SAME_BENEFICIARY", "LOSS_RESERVE", "PLATFORM_WRITEOFF"],
        "SETOFF_BOUND_CLAIM_BENEFICIARY_DISTRIBUTION": {"postable": true, "condition": "FSM DEFAULTED; observed distribution to the beneficiary payee on the bound claim; amount <= min(claim due, quote amount, unconsumed source); quote_ref from setoff-proposal-quote"},
        "SETOFF_OTHER_CLAIMS_SAME_BENEFICIARY": {"postable": true, "condition": "same as step 1 plus source claim differs from bound claim, payee maps to the same beneficiary via beneficiary_payee_map, and a quote exists; without a quote not postable", "legal_effect": "NOT_ASSESSED"},
        "LOSS_RESERVE": {"postable": false, "state": "NOT_BOUND_NO_RESERVE_LEDGER"},
        "PLATFORM_WRITEOFF": {"postable": true, "condition": "see writeoff_trigger_and_day_basis"},
        "pre_default_set_off": "existing FSM repay path, not the recovery ledger",
        "step_4_gate": "waterfall_trace records steps 1-3 outcome before write-off",
        "not_postable_in_v1": ["ASSIGNED_CLAIM_COLLECTION", "LEGAL_RECOVERY", "any external collection"],
        "never": ["ADMISSION_RIGHT_SEIZURE", "TICKET_TRANSFER", "RIGHT_CANCELLATION", "TOKEN_SEIZURE"]
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-04"],
      "rationale": "Set-off against observed beneficiary distributions is the only collateral path the terms allow in simulation and needs no real collection; the reserve step cannot post without a ledger and external collection is out of scope, so exactly three of the four steps are postable.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "review_items": ["legal effect of set-off against settlement distributions", "position in insolvency proceedings"]
    },
    "reserve_step_when_unbuilt": {
      "status": "ADOPTED",
      "value": {
        "behavior": "SKIP_WITH_EXPLICIT_MARKER_FULL_LOSS_TO_STEP_4",
        "trace_row": {"step": "LOSS_RESERVE", "status": "NOT_BOUND", "absorbed_krw": 0},
        "entry_marker": {"reserve_binding": "NOT_BOUND", "reserve_step_version": "UNBUILT_V1"},
        "no_synthetic_reserve": "CAPITAL-TERMS-V1 reserve provision bps are not applied as balances",
        "coa": "no postings to 1190, 3100, 3200, 5100; write-off debits 5200 for the full principal",
        "restatement": "NONE; UNBUILT_V1 entries are never restated when a reserve ledger is bound",
        "binding_path": "a reserve ledger node bumps overlay_schema, adds a new golden and keeps this one as a replay vector",
        "economic_effect": "none on total platform loss; only P&L presentation (5200 vs 5100/1190)"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-04"],
      "rationale": "The reserve is the platform's own revenue pool, so skipping it changes presentation not loss; blocking write-off until a ledger exists would freeze defaulted exposure indefinitely, and silently assuming balances would invent numbers.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "late_recovery_after_writeoff": {
      "status": "ADOPTED",
      "value": {
        "allowed": true,
        "phase": "POST_WRITEOFF",
        "expiry_in_simulation": "NONE",
        "sources": "set-off steps 1 and 2 only",
        "cap": "residual_claim_krw = writeoff principal + accrued interest to eligible day - later recoveries",
        "allocation": "NONE; whole amount applied to the residual claim",
        "interest_on_residual_claim": "NONE",
        "coa": "Dr 1000 / Cr 4300 (cash basis)",
        "fsm": "DEFAULTED and note NOTED unchanged; case never reopened; no FSM repay",
        "reserve_refill": "NOT_AUTOMATIC",
        "authority": "same as recovery_authority"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-01", "CAP-04", "CAP-14"],
      "rationale": "AUTHORITY_MODEL_1 A-4 forbids discarding late facts by cutting the log; keeping post-write-off recoveries append-only, capped by the residual claim and booked cash-basis to 4300 honours that without reopening the terminal FSM case.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "review_items": ["limitation period for recovering written-off claims", "accounting treatment of recoveries after write-off"]
    },
    "interest_stop_rule": {
      "status": "ADOPTED",
      "value": {
        "accrual_start": "DRAW_DAY_INCLUSIVE",
        "accrual_stop": "earliest of close day (exclusive) and writeoff_eligible_sim_day (exclusive)",
        "post_default_interest": "accrues from default_sim_day at tier all-in + default add as a 9700 memo, recognized to 4110 only on cash",
        "stop_basis": "eligible day, not posting day; late posting never extends accrual",
        "at_writeoff": "recognized unpaid accrued interest reversed; suspended memo released without P&L",
        "after_writeoff": "no interest or default interest on the residual claim",
        "compounding": "NONE"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-01", "CAP-13"],
      "rationale": "Stopping on the eligible day closes accrual_stop AT_CLOSE_OR_WRITEOFF and the CAPITAL-REVREC-V1 suspension into one date-based rule that does not depend on when an operator posts.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "review_items": ["interest recognition on credit-impaired advances"]
    },
    "recovery_authority": {
      "status": "ADOPTED",
      "value": {
        "human_only_actions": ["FSM default command", "recovery posting", "write-off posting", "non-margin acceleration event recording"],
        "threshold_ref": "CAPITAL-TERMS-V1.underwriting_depth.two_person_threshold_krw",
        "threshold_krw_at_decision": 50000000,
        "up_to_threshold": "single human operator",
        "above_threshold": "two-person: approvals[] with at least 2 distinct approver_label values, else 409 TWO_PERSON_REQUIRED",
        "amount_basis": {"default": "FSM outstanding principal at command", "recovery": "amount_krw", "writeoff": "writeoff_principal_krw"},
        "aggregation": "recoveries on the same advance_id and sim_day are summed against the threshold",
        "control_strength": "SIMULATED control; approver_label is not authentication (actor is not authentication)",
        "ai_lane": {"role": "PROPOSE_ONLY", "executionAuthorized": false, "proposal_kinds": ["DEFAULT_ELIGIBLE", "RECOVERY_SETOFF", "WRITEOFF"], "post_attempt": "403 RECOVERY_AGENT_FORBIDDEN, no write", "adoption": "operator posts a separate command citing proposal_id; a proposal never counts as an approval"},
        "consumers": ["overlay-recovery-writeoff", "coa-payment-writeoff-postings"]
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-01", "CAP-04", "CAP-19"],
      "rationale": "Keeps CAPITAL-TERMS-V1 execution authority (human two-person, AI proposes only) for default and recovery and extends it to write-off; aggregating per advance and day closes split-to-evade, and the simulated label avoids claiming authentication.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "loss_attribution": {
      "status": "ADOPTED",
      "value": {
        "bearer_ref": "CAPITAL-TERMS-V1.default_loss_treatment.loss_bearer_v1",
        "bearer": "KIX_CAPITAL_PLATFORM_100_PERCENT",
        "tranching": "NONE",
        "loss_krw": "writeoff_principal_krw - loss_reserve_absorbed_krw (currently 0)",
        "never_attributed_to": ["CUSTOMER_DEPOSITS", "ORGANIZER_SETTLEMENT_FUNDS", "REFUND_RESERVE_F03", "TOKEN_TREASURY", "TICKET_HOLDERS"],
        "claim_status": "RESIDUAL_CLAIM_RETAINED",
        "reopen_on": ["CAP-03 claim purchase", "investor participation"]
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-04"],
      "rationale": "Write-off is a memo of the platform's own loss, not forgiveness; naming the bearer and the forbidden funds keeps the settlement, refund and token separations from the terms intact.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "review_items": ["loss sharing once claim purchase or investor participation exists"]
    },
    "digest_and_coa_effect": {
      "status": "ADOPTED",
      "value": {
        "overlay_digest": {"new_journal_kinds": ["RECOVERY", "WRITEOFF"], "fold_key": "state.recovery", "empty": "KEY_ABSENT", "overlay_schema": "UNCHANGED_1", "new_golden": "tests/golden/overlay_recovery.json", "existing_goldens": "unchanged unless one contains an ACCELERATED advance; then regenerate citing this note"},
        "f04": {"state_digest": "UNCHANGED", "payload_sha256": "UNCHANGED", "tests_golden_demo_json": "UNCHANGED"},
        "export": {"where": "V3 overlay section only (state.recovery and journal)", "existing_seven_sections": "UNTOUCHED", "new_recon_check_ids": "NONE", "label": "SIMULATED memo, never a cash receipt"},
        "coa_postings": {
          "post_default_recovery_cash": "Dr 1000 R / Cr 1100 principal share / Cr 1110 recognized accrued interest share / Cr 4110 9700-memo interest share recognized on cash; interest applied oldest day first; 9700 counter-leg defined by coa-payment-writeoff-postings",
          "writeoff": "Dr 5200 principal / Cr 1100; reverse recognized unpaid interest Dr 4100 and 4110 / Cr 1110; release 9700 memo without P&L; no 1190, 5100, 3100, 3200 postings",
          "late_recovery": "Dr 1000 / Cr 4300"
        },
        "invariants_to_restate": ["1100 = sum over advances (FSM.outstanding - overlay principal recovered - overlay principal written off)", "9150 and 9160 are tied to FSM totals and need the overlay recovery terms for DEFAULTED advances"],
        "consumers": ["overlay-recovery-writeoff", "coa-payment-writeoff-postings"]
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-11", "CAP-13", "CAP-14"],
      "rationale": "Empty-is-absent keeps every existing digest and golden byte-identical, overlay-only export keeps the seven obligation sections clean, and the COA mapping reuses CAPITAL-COA-V1 accounts so only the FSM-tied conservation predicates need restating once recoveries stop being FSM repay.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 6. 수용 기준 매핑

- `docs/decisions/CAPITAL_DEFAULT_RECOVERY.md`와 `capital-decision-v1` 블록 하나(열 항목 전부 ADOPTED, 필수 키 보유): §5. `python3 scripts/decision_ledger.py`는 이 결정자가 읽기 전용이라 실행하지 않았으며, supervisor가 병합 시점에 확인한다.
- `acceleration_interest_rebase`가 `NOT_REBASED / DECISION_REQUIRED`를 교체하고 연체이자 시작일·상각일을 명시: §2, §4.1, §4.2.
- `waterfall_steps_in_scope`가 네 단계 중 postable 여부와 준비금 단계 동작을 명시: §4.4, §4.5.
- `recovery_authority`가 사람 2인(50,000,000원 초과)·AI 제안만을 유지하고 소비 노드 두 개를 명시: §4.8.
- `docs/CAP_COVERAGE.md`가 이 노트를 인용하고 `python3 -m unittest tests.test_decisions tests.test_coverage`가 통과해야 함: 이 파일은 허용 경로 밖이라 **이 결정자는 수정·실행하지 않았다.** supervisor가 CAP-01·CAP-04 행에 `docs/decisions/CAPITAL_DEFAULT_RECOVERY.md`를 인용하는 줄을 더한 뒤 두 테스트를 실행해야 한다.

## 7. Open risks

- **pack 밖 입력.** `CAPITAL_OVERLAY_STATE.md`와 `margin-cure-default`·`setoff-proposal-quote`·`sim-clock-ledger` 노트는 허용 경로 목록에 없어 읽지 않았다. 가속 마커 필드명, `default_sim_day` 출처, `quote_ref` 형식은 이름으로만 참조했다. 필드명이 충돌하면 해당 노트가 이기고 날짜·금리·순서 규칙은 이 노트가 이긴다.
- **법무·회계 (작업 가정).** 90일 상각, 상계의 도산 시 효력, 인식 유예 이자를 `4110`으로 통일한 분류, 상각 뒤 회수의 시효와 회계 처리는 전문가 검토 대상이다.
- **COA 보존식.** 부도 후 FSM 잔액이 줄지 않아 `1100`·`9150`·`9160` 보존식 재진술이 필수다. `coa-payment-writeoff-postings`가 재진술하지 않으면 recon이 깨진다. `9700` 해제의 상대 메모 다리는 이 노트가 정하지 않았다.
- **2인 원칙은 인증이 아니다.** 로컬 파일을 쓸 수 있는 사람은 오버레이를 다시 쓸 수 있다.
- **마진콜 미발화.** fixture 정산 조회가 불변이라면 가속 경로는 단위·합성 fixture로만 검증된다. 기존 오버레이 골든에 가속 건이 있으면 재생성이 필요하다. 이를 확인하지 못했다.
- **부도 명령 부재.** 자동 부도가 없으므로 사람이 부도 명령을 내리기 전에는 `4110` 인식 이자가 계속 쌓인다. 현재 완화책은 표시 전용 플래그뿐이다.
- **준비금 표시 차이.** 원장 도입 뒤에는 새 건의 손익 표시가 `5100/1190` 쪽으로 달라진다. 소급 재작성이 없으므로 `UNBUILT_V1` 건과 표시 차이가 남는다.

## 8. 후속 작업

- **`overlay-recovery-writeoff`.**
  - `RECOVERY`/`WRITEOFF` 폴드와 명령, 거절 코드, 2인·AI 403 벡터를 구현한다.
  - 가속 건의 `/api/overlay` rebase 필드와 `DEFAULT_COMMAND_OVERDUE` 플래그를 구현한다.
  - `overlay_recovery.json` 골든과, 클록 점프에서도 같은 결과가 나오는 가속 벡터를 추가한다.
- **`coa-payment-writeoff-postings`.** §4.10의 분개와 `9700` 상대 다리를 구현하고 FSM 보존식을 재진술한다.
- **준비금 원장 노드(미래).** ③을 바인딩하면서 `overlay_schema`를 올리고 새 골든을 추가한다.
- **`docs/CAP_COVERAGE.md`·`readiness`.** CAP-01·CAP-04 행이 이 노트를 인용하게 한다(상태값 불변).
- **`f04-real-funds-lift-criteria`.** §7의 법무·회계 검토 항목을 질문지에 전달한다.
