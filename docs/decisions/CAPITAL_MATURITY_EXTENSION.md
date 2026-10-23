# Capital 일회성 만기 연장 결정 — 적격 창, 연체이자 유지, 연장구간 금리, 180일 하드캡, 가속·부도 적격 후 거절, 롤업·예측·cap_check, 오버레이 엔트리 형태

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
이 문서는 KIX-CAPITAL 저장소 안의 **시뮬레이션·제품 설계용** 결정이다. 청약이나 대출 제안이 아니고 실자금이 움직이지 않으며 production은 계속 `NOT_AUTHORIZED`다. 이자·기간 관련 내용 중 법·회계에 닿는 부분은 **전문가 검토 전 작업 가정**이며 자문이 아니다. 어떤 upstream 계약의 채택도 주장하지 않는다. diff는 `docs/decisions/CAPITAL_MATURITY_EXTENSION.md` 한 파일이고 `capital/`·`tests/`·vendor 바이트·골든·기존 결정 노트의 상태 토큰은 건드리지 않는다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `maturity-extension-decision` (Decision: one-time maturity extension — eligibility window, rate, grace/default interplay, acceleration refusal, evidence shape) · deps `financial-terms-decision`, `default-recovery-decision`, `margin-cure-default` · kind `decision` · user_merge `False` |
| 결정자 | **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)** |
| 위임 원문 | 2026-10-08 18:25 KST JunTae Park: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." |
| 결정일 | 2026-10-22 |
| 기준 | KIX-CAPITAL main `5c23989` · kix-protocol `56d5f59` (읽기 전용 `/workspace/capital-run/kixproto-ro`). 재핀 정책 결정([CAPITAL-UPSTREAM-REPIN-POLICY-DECISION], main `5c23989`)에 따라 이 두 값은 **출처 증명용 역사적 체크아웃**이며 실행·참조 구속이 아니다. 실행 핀 — vendor `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`(다섯 파일 SHA256)과 AI 위임 초안 `e2a029d8…` — 은 이 노트가 다시 건드리지 않는다 |
| 읽기 범위 | supervisor pack 허용 경로만 읽었다. `CAPITAL_FINANCIAL_TERMS.md`(CAPITAL-TERMS-V1 정본)과 `docs/contracts/CREDIT_ADVANCE_F04.md` §5는 허용 경로 밖이라 **직접 열지 않았다.** TERMS의 연장 값(횟수 1회, 최대 30일, 180일 하드캡, 사람 승인, 수수료 없음)은 노드 수용 기준문이 "cited unchanged"로 지정한 값 그대로 인용하며 필드명은 구현 시 정본에서 확정한다. **이름·숫자가 충돌하면 TERMS와 F04 계약 문서가 이기고, 창·순서·엔트리 구조는 이 노트가 이긴다.** |
| 상태 어휘 | **ADOPTED** = 위임 범위 안의 잠정 값. **UNDETERMINED** = 값을 정할 수 없어 이유만(`value: null`). 일곱 항목 모두 ADOPTED |

용어: 금액은 KRW 정수, 날짜는 오버레이 논리 일 `sim_day`(정수), 비율은 bps. `d0` = 인출일, `M` = 현재 예정 만기(연장은 가속 마커 이전에만 가능하므로 사실상 원 만기), `E` = 연장 명령일, `k` = 연장 일수, `M'` = 새 만기. 유예·연체 가산·치유·2인 임계 등 상수는 `CAPITAL-TERMS-V1` 필드를 참조한다(현재 값: 유예 10일, 연체 가산 300 bps, 치유 5일, 2인 임계 50,000,000원).

## 1. 결정 요약

| item | 결정 (요지) | CAP rows | 소비 노드 / seam |
|---|---|---|---|
| `extension_eligibility_window` | **ADOPTED.** 창 = 인출일부터 `M + 유예`까지(마지막 적격일 = 부도 적격일 − 1). 전제: FSM 생존·실효 원금 > 0·가속 마커 없음·열린 마진콜 치유창 없음·미사용(선지급당 1회). 위반은 전부 409/403 거절 | CAP-01, CAP-04 | `maturity-extension-command` |
| `extension_during_grace_and_default_interest_kept` | **ADOPTED.** 유예 중 연장 허용. 이미 발생한 연체이자(`M+1..E`, 티어 all-in + 가산)는 **그대로 유지** — 면제·소급 재금리·복리 없음. 유예는 `M'`에서 전체 길이로 재가동. `M' ≥ E` 강제 | CAP-01, CAP-04 | `maturity-extension-command` |
| `extended_term_rate_and_tier` | **ADOPTED.** 연장일은 심사 시점 티어 all-in 그대로(재티어링·프리미엄·수수료 없음). ACT/365 단리 메모 관행 불변. 연체이자 구간과 계약 금리 구간의 경계는 저널 사실(M, E, M')의 순수 함수 | CAP-01 | `maturity-extension-command` |
| `hard_cap_180_interaction_with_settlement_linked_term` | **ADOPTED.** 정산 연동 기간 산식은 **원 만기에만** 적용되고 연장이 산식을 재실행하지 않는다. 하드캡은 총기간 `M' − d0 ≤ 180`으로 묶는다. `k ≤ min(30, 180 − (M − d0))`. 자동 절사 없이 거절 + `max_admissible_extension_days` 제시 | CAP-01, CAP-04 | `maturity-extension-command` |
| `acceleration_and_default_eligible_refusal` | **ADOPTED.** 가속 마커 존재 → 409 `EXTENSION_AFTER_ACCELERATION`(DEFAULT_RECOVERY `extension_after_acceleration: REJECTED`의 실행화). `sim_day ≥ 부도 적격일` 또는 FSM `DEFAULTED` → 409 `EXTENSION_DEFAULT_ELIGIBLE`. 열린 치유창 → 409 `EXTENSION_MARGIN_CALL_OPEN`. 재사용 → 409 `EXTENSION_ALREADY_USED`. agent 게시 → 403 | CAP-01, CAP-04 | `maturity-extension-command` |
| `forecast_rollup_and_cap_check_treatment` | **ADOPTED.** 롤업·현금 사다리 예측은 `after_journal_index` 이후 `M'`을 만기로 보고하고 additive 필드(`original_maturity_sim_day`, `extension_days`)는 연장 있는 건에만. U1–U6·cap_check 불변(액면·실효·환불 상태가 안 바뀌므로). 연장 시 재심사 없음 | CAP-01, CAP-04 | `maturity-extension-command`, `GET /api/terms/portfolio(\/forecast)` |
| `extension_record_fields_and_operator_authority` | **ADOPTED.** 오버레이 저널 새 폴드 `state.maturity_extension`(빈 = 키 부재, `overlay_schema` 1 유지), 엔트리 종류 `MATURITY_EXTENSION`, 채택된 `overlay_id`/`kind`/`payload` 형태. 사람 전용, 임계 초과 2인, AI 제안만. 연장 없는 책은 모든 digest·골든 바이트 불변, COA 게시 없음 | CAP-01, CAP-11, CAP-19 | `maturity-extension-command` |

## 2. KIX 비전 연결 — 읽은 pack 경로

- `/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md` (A-4). 「과거 사실의 재생은 새로운 외부 실행 허가가 아니다」: 연장 엔트리를 재생해도 새로운 연장이 아니며 `overlay_id` dedup이 같은 재생에 같은 결과를 돌려준다. 「로그를 잘라 늦은 사실을 버리는 것은 금지」: 이미 발생한 연체이자를 연장으로 소급 소멸시키지 않는다(§4.2). 「예약 확정 ≠ 결제 확인」: `M'`은 시뮬레이션 만기 기록이지 채무 변경의 대외 확정이 아니다.
- `/workspace/capital-run/kixproto-ro/README.md` §1·§3. mock·비운영 범위, 실자금·실 PG/은행 잠금. 연장 표면은 `SIMULATED` 라벨을 유지하고 실제 여신 변경으로 읽히지 않게 한다.
- `docs/CAPITAL_REQUIREMENTS_KO.md`. CAP-01(오버레이 시계 `advance_day` CAS가 sim_day의 유일한 작성자, ACT/365 단리 메모, 롤업·예측·U1–U6 조회), CAP-04(마진콜·치유·가속·DEFAULT_ELIGIBLE 제안), 두 실행 핀과 결정 노트 기준칸의 성격(출처 증명)을 가져왔다. F04 §5는 이 문서의 인용(`docs/contracts/CREDIT_ADVANCE_F04.md` — 이미 구현된 참조 의미와 **미정 금융 정책**의 구별)으로만 참조했다. 만기 연장은 그 미정 항목군에 속하며 이 노트는 그 항목에 대한 **Capital 오버레이 쪽 잠정 답변**일 뿐 vendor FSM 바이트(`7481b0e` 핀)나 upstream 채택을 건드리지 않는다.
- `docs/decisions/CAPITAL_DEFAULT_RECOVERY.md`(MERGED 의존). 가속 = 만기 재기준 `M* = min(현재 만기, 앵커)`, 연체이자 `M*+1`부터, 부도 적격일 `M*+유예+1`, `extension_after_acceleration: REJECTED`, 소급 재계산·복리 없음, 권한(사람 전용·2인·AI 제안만), 저널·폴드·거절 코드 패턴을 그대로 적용한다.
- `docs/decisions/CAPITAL_CLAIM_SLICE_REGISTRY.md`. 채택된 오버레이 엔트리 형태 `overlay_id`/`kind`/`payload`, 빈 = 키 부재·`overlay_schema` 1 유지, 폴드 키 추가 시 스키마 올림 fallback, 파생값 미저널 원칙, `VOLATILE_KEYS` 금지를 계승한다.
- `docs/decisions/CAPITAL_DEMO_BOOK.md`. 한도·비율은 숫자로 복사하지 않고 `CAPITAL-TERMS-V1` 필드명 인용 규칙, 합성 라벨 문법.
- `docs/decisions/CAPITAL_ARTIFACT_BUNDLING.md`(발췌). 번들이 `docs/decisions/*.md` 전부를 바이트 그대로 싣므로 이 노트는 병합되면 아티팩트·`GET /api/decisions`에 자동으로 드러난다.
- 사용하지 않은 pack 경로 발췌: `docs/SEAMS.md`(새 `typing.Protocol` 행을 만들지 않으므로 행 추가 의무 없음), `docs/VALIDATION.md`, `CAPITAL_ACCOUNTS_TAX_LEGAL.md`, `CAPITAL_CLOSEOUT_ARTIFACT.md`(재생성 절차만 §6에서 인용).
- 「포부」의 번역: 연장까지 포함한 만기 생애 전체를 **저널 사실의 결정론적 폴드**로 닫아, 회계·감사·재생이 몇 번의 시계 점프와 무관하게 같은 결과를 내게 한다.

## 3. 항목별 결정

공통: 모든 값은 `label: SIMULATED`, `basis = PRODUCT_DECISION`(§3.2만 작업 가정), `provisional = true`다.

### 3.1 extension_eligibility_window — ADOPTED
- **값.** 연장 명령이 적격이려면 명령일 `E`에 **모두** 성립해야 한다: (1) FSM 선지급이 생존(`CLOSED`·`DEFAULTED` 아님)이고 실효 원금 > 0, (2) 가속 마커(`MARGIN_CALL_UNCURED`·`BENEFICIARY_INSOLVENCY_NOTICE`·`EVIDENCE_FRAUD_FINDING`)가 하나도 없고, (3) 열린 마진콜 치유창(마커 기록·치유 마감 미경과)이 없으며, (4) 그 선지급에 연장 엔트리가 없고(선지급당 1회, TERMS), (5) `d0 ≤ E ≤ M + 유예`(마지막 적격일 = 부도 적격일 − 1). 위반은 각각 §3.5의 409로 거절되고 상태는 보존된다.
- **근거.** 창을 유예의 마지막 날까지 열면 예정 만기 직후의 일시적 미회수를 가속·부도 경로 없이 흡수할 수 있다. 치유창 중 연장 금지는 연장이 치유 마감을 피하는 수단이 되는 것을 막고 DEFAULT_RECOVERY의 "마커 뒤 만기는 앞으로만" 단조성을 지킨다.
- **대안.** 만기 이후 전면 금지: 유예 제도와 모순되어 기각. 부도 적격일 이후까지 허용: 부도 절차와 경합해 기각.

### 3.2 extension_during_grace_and_default_interest_kept — ADOPTED (기초: 작업 가정)
- **값.** 유예 중(`M < E ≤ M + 유예`) 연장은 허용한다. `M+1..E`에 이미 발생한 연체이자(티어 all-in + 연체 가산)는 **유지된다**: 면제 없음, 계약 금리로의 소급 재금리 없음, 복리 없음(단리 원칙 불변). 엔트리에 서버 계산 스냅샷 `accrued_default_interest_kept_krw`를 증거로 기록한다(새로운 청구가 아니라 관측). 유예는 `M'`에서 **전체 길이로 재가동**한다(부도 적격일' = `M' + 유예 + 1`; 유예 단축 없음). `M' = M + k ≥ E`를 강제해 과거 만기를 만들지 않는다(`E − M > k`면 409 `EXTENSION_CAP_EXCEEDED`과 함께 최소 적격 `k`를 안내).
- **근거.** DEFAULT_RECOVERY의 무소급 원칙을 연장에 그대로 적용하면 발생분 소멸·재금리가 모두 차단된다. 유예 재가동은 "유예 길이는 줄이지 않는다"와 같은 선이다.
- **기초.** WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW — 자발적 연장 후에도 유예 중 연체이자를 그대로 과사할 수 있는지(이자 인식 포함).

### 3.3 extended_term_rate_and_tier — ADOPTED
- **값.** 연장일 구간(만기 전 연장은 `M+1..M'`, 유예 중 연장은 `E+1..M'`)은 **인출 심사 시점의 티어 all-in 금리 그대로** 발생한다. 재티어링 없음, 연장 프리미엄·스프레드 없음, 수수료 없음(TERMS: no fee; 엔트리에 `fee_krw: 0`으로 기록). ACT/365 단리·인출일 포함/종료일 제외 관행, 미지급 메모 표기는 불변. 금리가 바뀌지 않으므로 총비용 상한(`all_in_cost_cap_bps_annual` 인용) 검사도 자동으로 유지된다. 연체 구간과 계약 금리 구간의 경계는 저널 사실 `M`·`E`·`M'`의 순수 함수라 시계를 몇 칸씩 전진시켜도 같다.
- **대안.** 연장일에 가산금리: TERMS에 근거 숫자가 없어 새 숫자를 만들어야 해서 기각. 재티어링: 심사 기록과의 정합이 깨져 기각.

### 3.4 hard_cap_180_interaction_with_settlement_linked_term — ADOPTED
- **값.** 정산 연동 기간 산식은 **원 만기 `M`의 산출에만** 적용된다. 연장은 산식을 재실행·재유도하지 않고 운영자가 정수 `k`를 명령한다. 하드캡은 총기간에 묶는다: `M' − d0 ≤ 180`(TERMS 180일 하드캡 인용), 즉 `1 ≤ k ≤ min(30, 180 − (M − d0))`. 여유일 < 1이면 모든 연장은 409 `EXTENSION_CAP_EXCEEDED`. 요청 `k`가 여유를 넘으면 **자동 절사하지 않고 거절**하며 응답에 `max_admissible_extension_days`를 담는다(운영자가 재제출). 향후 TERMS 개정으로 원 만기 자체가 180일 이상이 되면 여유는 0이고 이 노트는 원 만기를 다시 쓰지 않는다.
- **근거.** 산식 소유권을 TERMS에 두고 이 노트는 총기간 상한의 결합만 정의하면 새 숫자 없이 두 규칙이 만난다. 절사 거절은 묵시적 조건 변경을 막는다.

### 3.5 acceleration_and_default_eligible_refusal — ADOPTED
- **값.** (1) 가속 마커가 하나라도 있으면 409 `EXTENSION_AFTER_ACCELERATION` — DEFAULT_RECOVERY `extension_after_acceleration: REJECTED`의 명령 코드 실행화. (2) `sim_day ≥ 부도 적격일` 또는 FSM `DEFAULTED`면 409 `EXTENSION_DEFAULT_ELIGIBLE`. (3) 열린 마진콜 치유창이면 409 `EXTENSION_MARGIN_CALL_OPEN`(§3.1 (3)). (4) 이미 사용했으면 409 `EXTENSION_ALREADY_USED`. (5) agent lane의 게시 시도는 403 `EXTENSION_AGENT_FORBIDDEN`, 기록 없음. 잃어버린 응답은 `operation_id` 조회 없으면 `UNKNOWN`, 자동 재시도 없음(SEAMS 규율). 거절은 어떤 상태도 바꾸지 않는다.
- **근거.** 의존 노트가 이미 "가속 뒤 연장 거절"을 채택했으므로 이 노트는 거절 코드·판정 시점만 닫는다. 치유창 거절은 §3.1의 단조성 근거와 같다.

### 3.6 forecast_rollup_and_cap_check_treatment — ADOPTED
- **값.** (1) `GET /api/terms/portfolio` 롤업과 `GET /api/terms/portfolio/forecast`(SIMULATED_CASH_FORECAST)는 해당 연장 엔트리의 `after_journal_index`부터 그 선지급의 만기를 `M'`으로 보고하고, 상환 최초 도래일을 `M'`로 잡는다. additive 읽기 전용 필드 `original_maturity_sim_day`·`extension_days`는 연장 있는 선지급에만 붙는다(없으면 필드 부재 → 기존 벡터·골든 바이트 불변). 예측의 이자 분해는 연체 구간(`M+1..E`)은 연체 금리, 연장일(`E+1..M'` 또는 `M+1..M'`)은 계약 금리로 구간을 나눠 보여준다(경계는 저널에서 유도). (2) `GET /api/underwrite/{id}`의 U1–U6 인수 기록과 cap_check는 **불변**: 연장은 액면·실효 원금·환불 상태·수익자 매핑·차입기초를 하나도 바꾸지 않으므로 U3(차입기초)·U4(집중도·cap) 입력이 그대로다. 연장 시 재심사·재인수는 없다. (3) `GET /api/overlay`는 `extension` 블록(`status: EXTENDED` + §3.7 필드)을 노출하고 연장 없는 건은 블록 부재다.
- **근거.** 만기 연장은 시간표 변경이지 노출 변경이 아니므로 cap 체계를 그대로 둬야 한다. 필드 부재 원칙이 기존 골든을 지킨다.

### 3.7 extension_record_fields_and_operator_authority — ADOPTED
- **저장.** 오버레이 저널(두 번째 저널)의 새 폴드 키 `state.maturity_extension`. 빈 = 키 부재, `overlay_schema` 1 유지(fallback: CAPITAL_OVERLAY_STATE가 새 폴드 키에 스키마 올림을 요구하면 2로 올리고 새 골든 추가, 결정 내용 불변). 엔트리 종류는 하나 `MATURITY_EXTENSION`, 형태는 채택된 `overlay_id`(dedup 키; 같은 id는 원 결과 반환, 다른 payload면 409) / `kind` / `payload`. `sim_day`·`after_journal_index`는 CAPITAL_OVERLAY_STATE가 정한 자리에 둔다(그 노트가 이긴다).
- **payload 필드.** `advance_id`, `claim_id`, `beneficiary_role`, `tier`, `original_maturity_sim_day`, `extension_days`(1..30 정수), `new_maturity_sim_day`(= `original_maturity_sim_day + extension_days`), `accrued_default_interest_kept_krw`(서버 계산, 유예 중 연장에서만 ≥ 0, 그 외 0), `fee_krw`(상수 0), `label: SIMULATED`, `authority {role, approvals[], proposal_id?}`, `terms_refs`(TERMS 연장 조항 인용). 금지: `VOLATILE_KEYS`(`instance_id`·`created_at`·`saved_at`·`timestamp`·`timestamps`)·개인정보·자유 텍스트. 금액은 정수 KRW. 파생값(부도 적격일'·구간 스케줄·여유일)은 저널하지 않는다.
- **권한.** 연장 명령은 **사람 운영자 전용**. 금액 기준은 명령 시점 FSM 실효 원금이며 `two_person_threshold_krw` 이하 1인, 초과 시 서로 다른 `approver_label` 2개 이상(409 `TWO_PERSON_REQUIRED`). 같은 `advance_id`·같은 `sim_day`의 신청은 누적 비교한다. AI는 제안만(`executionAuthorized=false`, 종류 `MATURITY_EXTENSION_CANDIDATE`), 게시는 403, 운영자 채택 시 `proposal_id`를 인용한 별도 명령, 제안은 승인으로 안 센다. `approver_label`은 인증이 아니다(시뮬레이션 통제).
- **digest·export·COA.** 폴드 결과는 `overlay_state.digest`에만 반영; 연장 없는 책의 모든 digest·골든은 바이트 불변; F04 `state_digest`·`payload_sha256`·`tests/golden/demo.json` 불변. 새 골든 후보 `tests/golden/overlay_maturity_extension.json`(인출 → 만기 전 연장 → 추가 인출 없이 `M'` 상환 / 유예 중 연장은 연체이자 유지 벡터). export는 V3 `overlay` 섹션 안에만, 일곱 섹션·`content_digest`·recon `CHECK_IDS` 불변. COA 게시 없음(이자는 기존 미지급 메모·인식 규칙 그대로, `CAPITAL-COA-V1` 불변). 구현 노드가 테스트를 추가하면 `test_count`가 바뀌므로 `CAPITAL-CLOSEOUT-REGEN-V1` 절차로 closeout digest·재무 벡터를 재생성한다.
- **소비 노드.** `maturity-extension-command`가 명령·거절 코드·폴드·`/api/overlay` extension 블록·§3.6 조회 필드를 구현한다. 새 `typing.Protocol`은 만들지 않는다(`docs/SEAMS.md` 행 추가 의무 없음).

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "maturity-extension-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-10-22",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "scope": "KIX-CAPITAL simulation and product design only; not an offer; no real money; production NOT_AUTHORIZED; interest and term content touching law or accounting is a working assumption pending professional review; no upstream contract claimed adopted",
  "bases": {"capital_main": "5c23989", "kix_protocol": "56d5f59 (historical provenance per the upstream re-pin policy decision on main 5c23989; not an executable pin)", "vendor_pin_commit": "7481b0e16ce9b903abbffa62249bb91cd9e63cfe (unchanged, not re-pinned)", "terms_version": "CAPITAL-TERMS-V1"},
  "consumer_node": "maturity-extension-command",
  "upstream_adoption_claimed": false,
  "terms_citation_rule": "CAPITAL-TERMS-V1 maturity-extension values are cited unchanged (1 extension per advance, 30 days max, 180-day hard cap on total term, human approval, no fee); the terms note was outside the readable pack, so field names are confirmed against the note at implementation; on a name or number conflict the terms note wins, on window, ordering and entry structure this note wins",
  "f04_open_items": "CREDIT_ADVANCE_F04 section 5 open items are referenced second-hand via docs/CAPITAL_REQUIREMENTS_KO.md (implemented reference semantics vs undecided financial policy); this note is the Capital-overlay provisional answer for the maturity-extension open item only and touches no vendor FSM byte",
  "entries": {
    "extension_eligibility_window": {
      "status": "ADOPTED",
      "value": {
        "window": "draw_sim_day <= command_sim_day E <= M + grace_days_after_maturity; last eligible day = default_eligible_sim_day - 1",
        "preconditions": ["FSM advance live (not CLOSED, not DEFAULTED)", "outstanding principal > 0", "no acceleration marker (MARGIN_CALL_UNCURED, BENEFICIARY_INSOLVENCY_NOTICE, EVIDENCE_FRAUD_FINDING)", "no open margin-call cure window (marker recorded, cure deadline not passed)", "no prior extension entry on this advance (one per advance per CAPITAL-TERMS-V1)"],
        "violations": "each precondition maps to a 409/403 in acceleration_and_default_eligible_refusal; state preserved on reject",
        "terms_refs": ["CAPITAL-TERMS-V1 extension count 1", "CAPITAL-TERMS-V1.term.grace_days_after_maturity"],
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Opening the window to the last grace day absorbs a brief post-maturity shortfall without touching the default path, while refusing during an open cure window keeps an extension from buying time against a margin call and keeps the default-recovery maturity monotonicity intact.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "extension_during_grace_and_default_interest_kept": {
      "status": "ADOPTED",
      "value": {
        "extension_during_grace": "allowed while command_sim_day <= M + grace_days_after_maturity",
        "accrued_default_interest": "KEPT: overdue interest accrued for M+1..E at tier all-in + default_interest_add_bps_annual is neither forgiven, retroactively re-rated to the contract rate, nor compounded (simple interest unchanged)",
        "evidence_field": "accrued_default_interest_kept_krw, server-computed snapshot recorded on the entry (observation, not a new charge)",
        "grace_restart": "grace restarts in full from M': default_eligible_sim_day' = M' + grace_days_after_maturity + 1; grace never shortens",
        "no_past_maturity": "M' = M + k >= E enforced; k < E - M is 409 EXTENSION_CAP_EXCEEDED with the minimum admissible k returned",
        "terms_refs": ["CAPITAL-TERMS-V1.interest_rate.default_interest_add_bps_annual", "CAPITAL-TERMS-V1.term.grace_days_after_maturity"],
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Applying the default-recovery no-retroaction principle to extension means accrued overdue interest survives the extension untouched, and restarting the full grace window at the new maturity is the same never-shorten-grace rule already adopted for acceleration.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "review_items": ["permissibility of retaining overdue interest accrued during grace after a voluntary extension", "interest recognition for the mixed-rate segments"]
    },
    "extended_term_rate_and_tier": {
      "status": "ADOPTED",
      "value": {
        "extended_days_rate": "tier all-in rate fixed at underwriting, unchanged",
        "segments": {"in_grace_extension": "M+1..E at tier all-in + default add (kept); E+1..M' at tier all-in", "pre_maturity_extension": "M+1..M' at tier all-in"},
        "conventions": "ACT/365 simple daily accrual memo on outstanding principal, draw day inclusive, stop day exclusive, unpaid memo labels unchanged",
        "tier_migration": "NONE", "extension_premium": "NONE", "fee": "NONE (fee_krw: 0 recorded; CAPITAL-TERMS-V1 no-fee cited unchanged)",
        "cost_cap": "rate unchanged so the all_in_cost_cap_bps_annual check stays satisfied by construction",
        "determinism": "segment boundaries are a pure function of journaled M, E, M'; independent of tick granularity",
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-01"],
      "rationale": "Keeping the underwriting-time tier and rate invents no new number, keeps the underwriting record consistent, and leaves the total-cost cap holding by construction.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "hard_cap_180_interaction_with_settlement_linked_term": {
      "status": "ADOPTED",
      "value": {
        "formula_ownership": "the settlement-linked term formula owns the ORIGINAL term M - d0 only; extension never re-runs or re-derives the formula",
        "hard_cap_binding": "total term: M' - d0 <= 180 (CAPITAL-TERMS-V1 180-day hard cap cited unchanged)",
        "bounds": "1 <= k <= min(30, 180 - (M - d0)); headroom < 1 rejects every extension with 409 EXTENSION_CAP_EXCEEDED",
        "no_silent_clamp": "a request above headroom is refused with max_admissible_extension_days in the response; the operator re-submits",
        "future_terms_revision": "if an original term ever reaches 180 days the headroom is zero and this note never rewrites the original term",
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Leaving the formula to the terms note and binding only the total to the hard cap combines the two rules without a new number, and refusing instead of clamping prevents implicit term changes.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "acceleration_and_default_eligible_refusal": {
      "status": "ADOPTED",
      "value": {
        "after_acceleration": "any acceleration marker present -> 409 EXTENSION_AFTER_ACCELERATION (operationalises default-recovery extension_after_acceleration REJECTED)",
        "default_eligible": "sim_day >= default_eligible_sim_day or FSM DEFAULTED -> 409 EXTENSION_DEFAULT_ELIGIBLE",
        "margin_call_open": "open cure window -> 409 EXTENSION_MARGIN_CALL_OPEN",
        "already_used": "second extension on the same advance -> 409 EXTENSION_ALREADY_USED",
        "agent_lane": "403 EXTENSION_AGENT_FORBIDDEN, no write",
        "lost_response": "lookup by operation_id else UNKNOWN, no automatic retry",
        "reject_effect": "NONE; no state changes on any refusal",
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "The dependency note already adopted rejection after acceleration, so this closes only the reject codes and decision points; the margin-call-open refusal keeps the maturity-monotone fold property.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "forecast_rollup_and_cap_check_treatment": {
      "status": "ADOPTED",
      "value": {
        "rollup_forecast": "GET /api/terms/portfolio and /forecast (SIMULATED_CASH_FORECAST) report M' as the advance maturity from the entry's after_journal_index; first repayment due date moves to M'",
        "additive_fields": "original_maturity_sim_day, extension_days present only on extended advances; absent otherwise so existing vectors and goldens stay byte-identical",
        "forecast_interest_segments": "overdue segment (M+1..E) at the overdue rate and extended days at the contract rate, derived from journaled boundaries",
        "underwriting_and_cap_check": "U1-U6 record and cap_check UNCHANGED: extension changes no face, outstanding, refund state or beneficiary mapping, so U3 and U4 inputs are identical; no re-underwriting or re-pricing at extension",
        "api_overlay": "extension block with status EXTENDED plus the entry fields; block absent when no extension",
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "An extension reschedules time, not exposure, so the cap system is untouched, and absent-when-unused fields keep every existing golden byte-identical.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "extension_record_fields_and_operator_authority": {
      "status": "ADOPTED",
      "value": {
        "storage": "overlay journal (second journal); new fold key state.maturity_extension; key absent when empty; overlay_schema unchanged 1; fallback: bump to 2 with a new golden if CAPITAL_OVERLAY_STATE requires it for a new fold key, decision otherwise unchanged",
        "entry_kind": "MATURITY_EXTENSION",
        "entry_shape": "adopted overlay entry shape overlay_id (dedup key; same id returns the original result, different payload 409) / kind / payload",
        "payload_fields": ["advance_id", "claim_id", "beneficiary_role", "tier", "original_maturity_sim_day", "extension_days (1..30 int)", "new_maturity_sim_day (= original_maturity_sim_day + extension_days)", "accrued_default_interest_kept_krw (server-computed; >= 0 only for in-grace extensions, else 0)", "fee_krw (const 0)", "label (SIMULATED)", "authority {role, approvals[], proposal_id?}", "terms_refs"],
        "envelope_fields_stay_where_overlay_state_puts_them": ["sim_day", "after_journal_index"],
        "derived_not_journaled": ["default_eligible_sim_day'", "rate segment schedule", "cap headroom", "max_admissible_extension_days"],
        "forbidden_keys": ["instance_id", "created_at", "saved_at", "timestamp", "timestamps", "any personal data", "free text"],
        "authority": {"human_only": true, "amount_basis": "FSM outstanding principal at command", "up_to_threshold": "single human operator", "above_threshold": "at least 2 distinct approver_label values else 409 TWO_PERSON_REQUIRED (threshold CAPITAL-TERMS-V1.underwriting_depth.two_person_threshold_krw)", "aggregation": "same advance_id and sim_day summed against the threshold", "ai_lane": {"role": "PROPOSE_ONLY", "executionAuthorized": false, "proposal_kinds": ["MATURITY_EXTENSION_CANDIDATE"], "post_attempt": "403 EXTENSION_AGENT_FORBIDDEN, no write", "adoption": "operator posts a separate command citing proposal_id; a proposal never counts as an approval"}, "control_strength": "SIMULATED control; approver_label is not authentication"},
        "digest_export_coa": {"overlay_digest_only": true, "books_without_extension": "all digests and goldens byte-identical", "f04": "state_digest, payload_sha256, tests/golden/demo.json unchanged", "new_golden_candidate": "tests/golden/overlay_maturity_extension.json (pre-maturity extension repaid at M'; in-grace extension with kept overdue interest)", "export": "V3 overlay section only; seven sections, content_digest, recon CHECK_IDS unchanged", "coa": "no postings; CAPITAL-COA-V1 unchanged; interest stays on the existing memo and recognition rules", "closeout_regen": "if the implementing node adds tests, regenerate the closeout digest and finance vectors per CAPITAL-CLOSEOUT-REGEN-V1"},
        "consumer": "maturity-extension-command"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-01", "CAP-11", "CAP-19"],
      "rationale": "A typed append-only overlay entry in the adopted shape, with integer money, no wall-clock keys, derived values kept out of the journal and the already-decided human two-person and AI propose-only authority, makes the extended life replayable and auditable without touching vendor bytes or any existing golden.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

- **노트 존재 + `capital-decision-v1` 블록 1개(`scripts/decision_ledger.py` 파싱, `GET /api/decisions` 노출):** §4 블록 하나, 일곱 항목 모두 ADOPTED·`provided_by`·ISO `date`·`value`. 이 결정자는 읽기 전용이라 스크립트를 **실행하지 않았다.** supervisor가 병합 시점에 `python3 scripts/decision_ledger.py`와 `GET /api/decisions`를 확인한다. 번들 결정이 `docs/decisions/*.md` 전부를 싣으므로 아티팩트·조회는 병합과 함께 자동 반영된다.
- **모든 항목 ADOPTED/UNDETERMINED + 소유자, CAPITAL-TERMS-V1 값(1회, 30일, 180일 하드캡, 사람 승인, 수수료 없음) 변경 없이 인용:** §4 전 항목 ADOPTED·소유자 명기. 값은 머리말·§3.1·§3.3·§3.4·§3.7에서 변경 없이 인용하고 `terms_citation_rule`에 인용 규칙을 두었다.
- **`maturity-extension-command` 소비 노드 명명 + 오버레이 엔트리 종류·필드 명시:** 모든 entry의 `consumer`, §3.7(종류 `MATURITY_EXTENSION`, payload 필드 목록, envelope 위임 규칙).
- **`python3 scripts/decision_bindings.py --check`가 새 항목을 pending consumer anchor로 목록:** 이 결정자는 실행하지 않았다. supervisor가 병합 시점에 실행해 이 노트의 consumer anchor가 pending으로 목록되는지 확인한다.

## 6. Open risks

- **TERMS 정본 미열람.** 연장 값은 노드 수용 기준문이 지정한 값 그대로 인용했으나 필드명을 정본에서 대조하지 못했다. 충돌 시 TERMS가 이름·숫자를 이긴다.
- **F04 §5 2차 인용.** `docs/contracts/CREDIT_ADVANCE_F04.md` §5를 직접 열지 않았다(허용 경로 밖). open items 지목은 요구사항 문서의 인용에 근거한 2차 정보다.
- **유예 중 연체이자 발생 가정.** 가속 없이 자연 만기가 지난 뒤 유예 구간에 연체 금리가 붙는다는 해석은 DEFAULT_RECOVERY의 재기준 규칙(`M*+1`부터)에서 유도했다. TERMS가 유예일을 계약 금리로 둔다면 "유지" 대상이 0원이 될 뿐 규칙 자체는 무해하게 퇴화한다.
- **정산 연동 기간 산식 미열람.** 하드캡 결합 규칙은 구조적으로 닫았으나 산식 필드명·단위(관측일 기준 여부)는 구현 시 확인이 필요하다.
- **치유창 중 거절은 이 노트의 선택.** 의존 노트는 "가속 뒤 거절"만 적었다. `EXTENSION_MARGIN_CALL_OPEN`은 이 노트가 추가한 상품 규칙이다.
- **표면 필드 추가.** 롤업·예측의 additive 필드는 부재 원칙을 지켜야 골든이 유지된다. 구현이 빈 값이라도 내보내면 기존 벡터가 깨진다.
- **2인 원칙은 인증이 아니다.** 로컬 파일을 쓸 수 있는 사람은 오버레이를 다시 쓸 수 있다.

## 7. 후속 작업

- **`maturity-extension-command`(구현 노드).** 명령·거절 코드·폴드·`/api/overlay` extension 블록, §3.6 롤업·예측 additive 필드, `tests/golden/overlay_maturity_extension.json`(만기 전 연장·유예 중 연체이자 유지 벡터), 시계 점프 결정론 벡터, agent 403 벡터를 구현한다. 착수 전 `CAPITAL_FINANCIAL_TERMS.md`·`CAPITAL_OVERLAY_STATE.md`·`margin-cure-default` 노트를 열어 필드명·엔트리 자리·치유창 표지를 대조한다.
- **supervisor 병합 전 점검.** `python3 scripts/decision_ledger.py`, `python3 scripts/decision_bindings.py --check`(이 노트의 consumer anchor pending 목록), `GET /api/decisions`, 필요하면 `docs/CAP_COVERAGE.md` CAP-01·CAP-04·CAP-19 행 인용 추가 후 `python3 -m unittest tests.test_decisions tests.test_coverage`.
- **`f04-real-funds-lift-criteria`.** §3.2의 검토 항목(연장 후 연체이자 과사 가능 여부)을 질문지에 전달한다.
