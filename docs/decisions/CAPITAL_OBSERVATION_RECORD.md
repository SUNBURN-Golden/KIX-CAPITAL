# Capital 기록된 외부 사실 모델 결정 — 사실 클래스, 검증 라벨, 기록 권한, 소비자

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
이 문서는 KIX-CAPITAL 저장소 안의 **시뮬레이션·제품 설계용** 결정이다. 청약이나 대출 제안이 아니고, 실자금이 움직이지 않으며, production은 계속 `NOT_AUTHORIZED`다. 기록된 외부 사실(recorded external fact)은 **운영자의 주장 기록**이지 제공자·은행·체인의 확인이 아니며, 어떤 upstream 계약의 채택도 주장하지 않는다. 이 문서는 `capital/`·`tests/`·vendor 바이트·골든·기존 결정 노트의 상태 토큰을 건드리지 않고, diff는 `docs/decisions/CAPITAL_OBSERVATION_RECORD.md` 한 파일이다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `observation-record-decision` (Decision: recorded external-fact model — classes, verification labels, recording authority and consumers) · deps `upstream-binding-decision`, `settlement-policy-decision` · kind `decision` · user_merge `False` |
| 결정자 | **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)** |
| 위임 원문 | 2026-10-08 18:25 KST JunTae Park: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." |
| 결정일 | 2026-10-25 |
| KIX-CAPITAL 기준 | main `e56224a` |
| kix-protocol 기준 | `53c16b2` (읽기 전용 `/workspace/capital-run/kixproto-ro`) |
| vendor pin | `capital/vendor/manifest.json` commit `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`, 다섯 파일 SHA256 불변 |
| 읽기 범위 | supervisor pack이 허용한 경로만 읽었다. deps 두 노트(`CAPITAL_UPSTREAM_BINDING.md`, `CAPITAL_SETTLEMENT_POLICY.md`)는 허용 경로 밖이라 **이 결정자가 직접 열지 않았다.** 필드·라벨 이름은 허용된 노트의 인용(`fsm_expressible`, AI lane QUERY/PROPOSE·HUMAN_PENDING·effects_executed false, §3.9 핀 `e2a029d`)과 `docs/CAPITAL_REQUIREMENTS_KO.md` CAP-19·CAP-12 행으로만 참조한다. **이름이 충돌하면 선행 노트가 이기고, 사실 모델의 구조·라벨·소비 규칙은 이 노트가 이긴다.** |
| 상태 어휘 | **ADOPTED** = 위임 범위 안의 잠정 값. 여덟 항목 모두 ADOPTED |
| 개정 | 리뷰 라운드(blocking, 범위 초과): 이 노드의 허용 diff는 이 노트·`tests/decision_bindings.json`·`tests/vectors/pack/`뿐이다. 브랜치에 섞인 `scripts/decision_ledger.py`(`--check` 별칭)·`tests/test_coa_candidate.py`(이 노트 바이트 핀)·`tests/test_decisions.py` 변경은 **이 결정의 일부가 아니며 철회 대상**이다 — 별도 선행 변경(prerequisite PR)으로 분리하거나 허용 범위를 공식 개정한 뒤에만 들어올 수 있다. 결정 내용은 그 세 파일에 의존하지 않는다. 기준값을 main `e56224a`·kix `53c16b2`로 갱신했다 |

## 1. 결정 요약

| item | 결정 (요지) | CAP rows | 소비 노드 / seam |
|---|---|---|---|
| `fact_class_set` | **ADOPTED.** `CAPITAL-OBSERVED-FACT-V1`: 클래스 세 개 `PROVIDER_PAYMENT_CAPTURE`·`SETTLEMENT_CASH_ARRIVAL`·`REFUND_EVENT_OBSERVED`. 모든 사실에 상수 `label: SIMULATED`, `verification: UNVERIFIED_ASSERTED`, `funds_executed: false`, `provider_call_made: false`, `legal_effect: NOT_ASSESSED` | CAP-09, CAP-14 | `observation-record` 구현 노드 → `/api/overlay` |
| `verification_label_vocabulary` | **ADOPTED.** 기록 사실은 `UNVERIFIED_ASSERTED`만 쓸 수 있다. `PROVIDER_CONFIRMED`·`BANK_MATCHED`·`CHAIN_CONFIRMED`는 선언만 하고 `NOT_BOUND`로 거절(409 `FACT_VERIFICATION_NOT_BOUND`). 파생값은 `DERIVED_FROM_UNVERIFIED_ASSERTED` provenance를 상속하고 라벨을 승격할 수 없다 | CAP-09, CAP-14, CAP-19 | recon·forecast 표면 |
| `recording_authority` | **ADOPTED.** 기록은 사람 운영자(organizer) 전용 — 기존 `POST /api/overlay/commands` organizer seam의 새 명령 종류. AI는 `EXTERNAL_FACT` 제안만(`executionAuthorized=false`, 403 `FACT_AGENT_FORBIDDEN`). auditor/observer 읽기 전용. 2인 원칙은 V1에서 요구하지 않는다(무검증 주장은 자금 행위가 아니다) | CAP-01, CAP-19 | `observation-record`, agent lane |
| `fact_fold_location` | **ADOPTED.** 오버레이 저널의 추가형 폴드 키 `state.external_facts`. 채택된 엔트리 형태 `overlay_id`/`kind`/`payload`, 단일 `kind: EXTERNAL_FACT` + `payload.fact_class` 구분. 새 엔벨로프 섹션·새 파일 없음. append-only, 정정은 `supersedes_fact_id`를 단 새 엔트리 | CAP-10, CAP-14 | `observation-record`, overlay fold |
| `recon_consumption_rule` | **ADOPTED.** 소비자는 recon과 forecast actuals뿐. 명세서 `actual_paid`는 `NOT_BOUND` 유지, 사실은 별도 `recorded_actuals` 블록. 고정 FSM·shadow slice 파생(`served`/`outstanding`/`source_available`)·`eligible_face`·U1–U6·상계 견적 재원에는 절대 들어가지 않는다 — 주장된 현금은 대사 재원이 아니다 | CAP-09, CAP-14 | `/api/reconciliation`, `/api/terms/portfolio/forecast` |
| `derived_value_source_rule` | **ADOPTED.** 파생값은 저널+오버레이의 순수 함수로 저장하지 않는다. `derived: true`, `source_fact_ids`, `derivation` 규칙명을 달고, `superseded` 사실은 재계산에서 빠진다. 사실이 없으면 파생 블록 자체가 없다 | CAP-01, CAP-14 | recon·forecast·`/api/overlay` 표면 |
| `capacity_bounds` | **ADOPTED.** 사실 엔트리 ≤ 128, claim당 ≤ 16, supersede 체인 ≤ 4, 문자열 ≤ 64바이트, 자유 텍스트 없음, 금액은 정수 KRW ≤ `MONEY_MAX`. 초과는 409 `SIMULATION_CAPACITY`(`scope: external_facts`), 축출 없음 | CAP-08, CAP-11 | `observation-record` |
| `digest_export_effect` | **ADOPTED.** 사실은 `overlay_state.digest` 폴드에만 반영되고 빈 책은 키 부재라 `overlay_schema` 1·모든 digest·골든 바이트 불변. export는 V3 `overlay` 섹션 안에만. 기존 일곱 섹션·`content_digest`·`CHECK_IDS` 불변. COA 게시 없음(`NOT_POSTABLE_V1`) | CAP-13, CAP-14, CAP-15 | `export-manifest`, `coa-candidate` |

## 2. KIX 비전 연결 — 읽은 pack 경로

- `/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md` (A-4). 「예약 확정 ≠ 결제 확인 ≠ 체인 권리 발행 완료」와 「local sync/sequence를 chain finality로 대체 금지」가 `UNVERIFIED_ASSERTED`의 정본이다 — 운영자 기록은 제공자 사실이 아니다. 「늦은 사실은 현재 권한으로 대사하고 로그를 잘라 버리지 않는다」가 append-only + supersede 구조의 근거다. 「과거 사실 재생은 새 외부 실행 허가가 아니다」가 재생 시 아무것도 실행되지 않음의 근거다.
- `/workspace/capital-run/kixproto-ro/README.md` §1·§3. mock·비운영 범위이고 실 PG/은행 호출은 잠겨 있다. 그래서 사실 기록은 provider 호출이 아니라 사람 주장이며 `provider_call_made: false`다. 자체 저장·로그 신규 구현 금지라 별도 파일이 아니라 기존 오버레이 저널의 폴드다.
- `docs/CAPITAL_REQUIREMENTS_KO.md`. CAP-09의 `actual_paid`·`primary_sales`·`resale_sales` `NOT_BOUND`와 "최초판매와 리셀을 합산하지 않음" — 사실은 그 칸을 채우지 않고 별도 라벨 블록으로 둔다. CAP-14의 은행·제공자 관측 `NOT_BOUND`, CAP-19의 agent lane(`SIMULATED QUERY/PROPOSE`, `HUMAN_PENDING`, `effects_executed=false`), CAP-12의 `ASSET_MISMATCH`·KRW `AssetSpec`이 각각 소비·권한·자산 규칙의 근거다.
- `docs/decisions/CAPITAL_DEFAULT_RECOVERY.md` §4.3·§4.8·§4.10. 오버레이 엔트리 스키마(필드·`VOLATILE_KEYS` 금지·dedup), 사람 전용 + AI 제안 경계(403 + `proposal_id` 인용), 빈 = 키 부재 + V3 `overlay` 섹션의 digest 규칙을 그대로 가져온다.
- `docs/decisions/CAPITAL_CLAIM_SLICE_REGISTRY.md` §3.1·§3.9·§3.10. 채택된 오버레이 엔트리 형태 `overlay_id`/`kind`/`payload`, `overlay_schema` 1 유지 + 스키마 올림 규칙(그 노트가 요구하면 그 규칙이 이긴다), 용량 거절(`SIMULATION_CAPACITY`, 축출 없음), 새 `typing.Protocol` 없이 SEAMS 행 추가 의무 없음의 패턴을 따른다.
- `docs/decisions/CAPITAL_DEMO_BOOK.md`. `beneficiary_payee_map`의 줄 개념(`SETTLEMENT_CASH_ARRIVAL`의 `claim_id`+`payee_label` 키)과 합성 라벨 문법을 인용한다.
- `docs/SEAMS.md`, `docs/VALIDATION.md`(발췌), `docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md`, `CAPITAL_ARTIFACT_BUNDLING.md`, `CAPITAL_CLOSEOUT_ARTIFACT.md`는 인용 범위로만 사용했다(새 노트는 번들에 자동 포함, `test_count` 변화 시 CLOSEOUT 재생성).
- 「포부」의 번역: 주장·관측·확인의 계층을 지금 분리해 두면, 실제 제공자 연결이 와도 `UNVERIFIED_ASSERTED → PROVIDER_CONFIRMED`의 승격 경로만 열면 되고 모델을 다시 짜지 않는다.

## 3. 항목별 결정

공통 상수: 모든 기록 사실은 `label: SIMULATED`, `verification: UNVERIFIED_ASSERTED`, `funds_executed: false`, `provider_call_made: false`, `legal_effect: NOT_ASSESSED`, `recorded_by_role: organizer`다. 금액은 KRW 정수, 날짜는 `sim_day` 정수, `VOLATILE_KEYS`와 개인정보·계좌·사람 이름은 쓸 수 없다(400 `OVERLAY_VOLATILE_KEY`).

### 3.1 fact_class_set — ADOPTED

- **값.** `CAPITAL-OBSERVED-FACT-V1`, `payload.fact_class` 세 값과 필드:
  - `PROVIDER_PAYMENT_CAPTURE`: `claim_id`, `order_ref`(≤64B, 합성 토큰), `amount_krw`, `captured_sim_day`, `claimed_provider_ref`(≤64B 불투명 합성 문자열). 주장 내용 = "미래 제공자가 이 주문의 매수자 대금을 capture했다".
  - `SETTLEMENT_CASH_ARRIVAL`: `claim_id`, `payee_label`, `amount_krw`, `arrival_sim_day`. 주장 내용 = "정산 현금이 도착했다". `payee_label`은 pinned 원장에 있는 줄만 허용하고 `SHADOW_NOT_APPLIED` 줄(`venue`·`agency`)은 409 `FACT_PAYEE_NOT_BOUND`다.
  - `REFUND_EVENT_OBSERVED`: `claim_id`, `amount_krw`, `refund_reason ∈ {BUYER_CANCEL, EVENT_CANCEL, PARTIAL_OTHER}`, `effective_sim_day`.
- **공통 payload 필드.** `fact_class`, `sim_day`(기록일), `effective_sim_day`(주장 사건일, `≤ sim_day`; 미래일은 409 `FACT_FUTURE_DAY`), `authority{role, approvals[], proposal_id?}`, 상수 다섯 개. `claimed_event_day`가 기록일보다 늦은 "예정 사실"은 V1에서 기록하지 않는다(사실은 과거 주장이다).
- **V1에서 채택하지 않는 클래스.** 은행 명세 도착 `BANK_STATEMENT_LINE`, KYC·신원 사건, 체인 tx 관측, 제공자 webhook 수신은 `NOT_ADOPTED_V1`이며 다른 `fact_class`는 400 `FACT_CLASS_NOT_ADOPTED`다.
- **근거.** 세 클래스는 pack이 지명한 최소 집합이며, 정산·환불·결제 capture라는 세 다른 외부 사실 종류를 커버한다. 은행 명세는 진짜 외부 증거라 시뮬레이션 안에선 주장과 구별이 안 돼 연다.

### 3.2 verification_label_vocabulary — ADOPTED

- **값.** 기록 사실의 `verification` 필드는 V1에서 `UNVERIFIED_ASSERTED` 하나만 받는다. 어휘는 세 층이다:
  - 기록층: `UNVERIFIED_ASSERTED`(유일하게 기록 가능). 선언만 하는 `PROVIDER_CONFIRMED`·`BANK_MATCHED`·`CHAIN_CONFIRMED`는 `NOT_BOUND`이며 입력 시 409 `FACT_VERIFICATION_NOT_BOUND`.
  - 파생층: 파생값은 `provenance: DERIVED_FROM_UNVERIFIED_ASSERTED`를 달고 `source_fact_ids`를 나열한다. 어떤 파생 규칙도 라벨을 확인층으로 승격하지 않는다.
  - 상태층(폴드 파생): 사실의 `status`는 `ACTIVE | SUPERSEDED`이며 `supersedes_fact_id`를 참조한 뒤 엔트리가 있으면 `SUPERSEDED`다. 삭제가 아니라 파생 표지다.
- **근거.** 라벨을 미리 선언해 두면(값은 NOT_BOUND) 미래 제공자 연결이 어휘 재설계 없이 승격 경로만 연다. CAP-09의 `actual_paid: NOT_BOUND`와 일관되게 "확인됨" 인상을 주는 라벨은 V1 표면에 나오지 않는다.

### 3.3 recording_authority — ADOPTED

- **값.** 기록 명령은 `POST /api/overlay/commands`의 새 종류 `record_external_fact`로, 기존 organizer seam의 역할 강제를 그대로 쓴다(새 경로·새 `typing.Protocol` 없음 — `docs/SEAMS.md` 행 추가 의무 없음). 사람 운영자만 게시하고 auditor·observer는 403 `FACT_ROLE_FORBIDDEN`이다.
- **AI.** 제안만 한다(`executionAuthorized=false`). 제안 종류 `EXTERNAL_FACT`이고 agent lane의 게시 시도는 403 `FACT_AGENT_FORBIDDEN`으로 거절하며 쓰지 않는다. 운영자 채택은 별도 명령이 `proposal_id`를 인용한다(CAP-19 `HUMAN_PENDING` 패턴). AI 제안은 사실이 아니며 승인으로도 세지 않는다.
- **2인 원칙.** V1에서는 요구하지 않는다. 기록은 자금·장부 효과가 없는 무검증 주장이라 회수·상각(재무 효과)과 다르다. 주장이 파생값을 통해 잘못 읽히는 위험은 `UNVERIFIED_ASSERTED` 라벨과 소비 제한(§3.5)으로 닫는다.
- **한계.** `approver_label`은 인증이 아니다(`LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED`).

### 3.4 fact_fold_location — ADOPTED

- **값.** 오버레이 저널(두 번째 저널)의 폴드 `state.external_facts`에 산다. 엔트리 형태는 채택된 `overlay_id`(dedup 키)/`kind`/`payload`다. `kind`는 `EXTERNAL_FACT` 하나이고 클래스 구분은 `payload.fact_class`다. `overlay_id` 재사용은 같은 페이로드면 원 결과, 다르면 409 `FACT_IDEMPOTENCY_CONFLICT`다. `sim_day`·`after_journal_index`는 오버레이 엔벨로프가 정한 자리에 둔다.
- **append-only.** 수정·삭제 없음. 정정은 `supersedes_fact_id`를 단 새 `EXTERNAL_FACT`다(A-4). FSM 저널·vendor 바이트·엔벨로프 최상위 섹션은 만지지 않는다.
- **스키마.** `overlay_schema`는 1 유지다(빈 = 키 부재). 만약 OVERLAY_STATE 규칙이 새 폴드 키에 스키마 올림을 요구하면 그 규칙이 이기고 `overlay_schema` 2와 새 골든으로 처리한다 — 결정 내용은 바뀌지 않는다.
- **대안.** 엔트리 `kind`를 클래스별로 쪼갬: 세 `kind`가 소비자 분기를 늘릴 뿐이라 기각. 별도 파일: 자체 저장엔진이라 기각.

### 3.5 recon_consumption_rule — ADOPTED

- **허용 소비자 둘.**
  - `GET /api/reconciliation`: 사실이 있을 때만 추가 검사 세 개가 붙는다(기본 `CHECK_IDS` 불변): `recorded_captures_vs_claim_face`, `recorded_settlement_cash_vs_distributed`, `recorded_refunds_vs_refund_face`. 결과는 `MATCH | ASSERTED_MISMATCH | NO_FACTS`이고 불일치는 진단 플래그 `OBSERVED_FACT_MISMATCH`만 낸다. 자동 정정·재시도·해소는 없다.
  - `GET /api/terms/portfolio/forecast`(`SIMULATED_CASH_FORECAST`): `SETTLEMENT_CASH_ARRIVAL` 사실을 버킷별 `recorded_actuals_krw`로 겹쳐 보일 수 있다. 블록에는 `actuals_source: UNVERIFIED_ASSERTED`를 상수로 단다. 사실이 없으면 블록 자체가 없다.
- **금지 소비자.** 고정 FSM(사실에서 명령·상태를 유도하지 않음, F04 저널·`state_digest` 불변), shadow slice 파생(`served`·`outstanding`·`encumbered`·`source_available`은 정산·FSM 조회만 읽는다), `eligible_face`·차입기초·U1–U6, `setoff-proposal-quote`와 폭포 ①②의 재원. **주장된 도착 현금은 상계 재원이 아니다** — asserted ≠ ledger-observed.
- **근거.** recon은 "저널과 주장의 비교"가 본래 일이고 forecast는 예상 vs 주장 actuals의 표시다. 둘 다 읽기 표면이라 FSM 불변식을 침범하지 않는다.

### 3.6 derived_value_source_rule — ADOPTED

- **값.** 파생값은 저장하지 않는다. 저널+오버레이의 순수 함수로 매 조회마다 계산하고 `derived: true`, `derivation`(규칙명), `source_fact_ids`를 단다. `SUPERSEDED` 사실은 모든 파생에서 빠진다(뒤엔트리가 대신한다). 파생값은 `provenance: DERIVED_FROM_UNVERIFIED_ASSERTED`를 상속하고 확인층 라벨로 올라가지 못한다. 사실이 없으면 파생 블록이 통째로 없어서 빈 책의 출력·digest는 바이트 불변이다. 파생 산술은 정수·결정론적이며 `sim_day`·시각·`instance_id`를 쓰지 않는다.
- **근거.** 파생을 저장하면 저널과 파생이 어긋날 자리가 생긴다(claim-slice-registry의 `served`·`outstanding` 미저장과 같은 이유).

### 3.7 capacity_bounds — ADOPTED

- **값.** 사실 엔트리 ≤ 128, `claim_id`당 ≤ 16, supersede 체인 깊이 ≤ 4(초과 시 409 `FACT_SUPERSEDE_DEPTH`), 문자열 필드 ≤ 64바이트, `reason` 계열은 열거형이라 자유 텍스트·개인정보가 들어갈 자리가 없다. `amount_krw`는 1 이상 `MONEY_MAX`(10^12) 이하 정수. 초과는 409 `SIMULATION_CAPACITY`에 `scope: external_facts`를 담고 축출·자동 삭제는 없다. 전체 오버레이 상한이 더 낮으면 그것이 이긴다. 기록 명령이 `MAX_OPERATIONS 500`에 센다면 시연 스크립트 예산은 ≤ 30 operation이다.
- **근거.** 데모 북(청구 10건)에서 claim당 16·총 128은 recon·forecast 분기를 모두 시연하고도 남는다.

### 3.8 digest_export_effect — ADOPTED

- **digest.** 사실 엔트리는 `overlay_state.digest`의 폴드 `state.external_facts`에 들어간다. 빈 책은 키가 없어 `overlay_schema` 1·F04 `state_digest`·`payload_sha256`·`tests/golden/demo.json`·사실 없는 기존 오버레이 골든이 **바이트 불변**이다. 파생값은 digest에 넣지 않는다. 새 골든 후보는 `tests/golden/overlay_external_facts.json`(캡처 주장 → 정산 도착 주장 → recon MATCH → 상충 주장 → supersede → ASSERTED_MISMATCH)이다.
- **export.** V3 `overlay` 섹션 안에만 나타난다. 기존 일곱 섹션·`content_digest`·recon `CHECK_IDS`·섹션 집합 규칙(V2/V3 `SECTION_SET`)은 바뀌지 않는다. 오버레이가 비어 있는 책의 export는 V2 그대로다.
- **COA.** 사실은 게시하지 않는다(`NOT_POSTABLE_V1`, `CAPITAL-COA-V1` 불변). 메모 계정이 필요하면 후속 투영 노드가 정한다.
- **영향.** 구현 노드가 테스트를 추가하면 `test_count`가 바뀌므로 `CAPITAL-CLOSEOUT-REGEN-V1` 절차로 클로즈아웃 다이제스트를 재생성한다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "observation-record-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-10-25",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "scope": "KIX-CAPITAL simulation and product design only; not an offer; no real money; production NOT_AUTHORIZED; every recorded fact is an unverified operator assertion, not provider/bank/chain confirmation; no upstream contract claimed adopted",
  "bases": {"capital_main": "e56224a", "kix_protocol": "53c16b2", "vendor_pin_commit": "7481b0e16ce9b903abbffa62249bb91cd9e63cfe"},
  "profile_version": "CAPITAL-OBSERVED-FACT-V1",
  "recorded_fact_constants": {"label": "SIMULATED", "verification": "UNVERIFIED_ASSERTED", "recorded_by_role": "organizer", "funds_executed": false, "provider_call_made": false, "legal_effect": "NOT_ASSESSED"},
  "upstream_adoption_claimed": false,
  "name_conflict_rule": "the two dependency notes (CAPITAL_UPSTREAM_BINDING.md, CAPITAL_SETTLEMENT_POLICY.md) were not opened by this decider; names come from allowed notes and requirements excerpts (second-hand); on a name conflict the dependency note wins, on fact-model structure this note wins",
  "entries": {
    "fact_class_set": {
      "status": "ADOPTED",
      "value": {
        "version": "CAPITAL-OBSERVED-FACT-V1",
        "classes": {
          "PROVIDER_PAYMENT_CAPTURE": ["claim_id", "order_ref", "amount_krw", "captured_sim_day", "claimed_provider_ref"],
          "SETTLEMENT_CASH_ARRIVAL": ["claim_id", "payee_label", "amount_krw", "arrival_sim_day"],
          "REFUND_EVENT_OBSERVED": ["claim_id", "amount_krw", "refund_reason (BUYER_CANCEL|EVENT_CANCEL|PARTIAL_OTHER)", "effective_sim_day"]
        },
        "common_payload": ["fact_class", "sim_day (record day)", "effective_sim_day (claimed event day <= sim_day; future -> 409 FACT_FUTURE_DAY)", "authority {role, approvals[], proposal_id?}"],
        "payee_label_rule": "must be a line present on the pinned ledger; SHADOW_NOT_APPLIED labels -> 409 FACT_PAYEE_NOT_BOUND",
        "not_adopted_classes": {"BANK_STATEMENT_LINE": "NOT_ADOPTED_V1", "KYC_EVENT": "NOT_ADOPTED_V1", "CHAIN_TX_OBSERVED": "NOT_ADOPTED_V1", "PROVIDER_WEBHOOK_RECEIPT": "NOT_ADOPTED_V1", "other": "400 FACT_CLASS_NOT_ADOPTED"},
        "constants": {"label": "SIMULATED", "verification": "UNVERIFIED_ASSERTED", "funds_executed": false, "provider_call_made": false, "legal_effect": "NOT_ASSESSED"}
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-25",
      "cap_rows": ["CAP-09", "CAP-14"],
      "rationale": "Three classes cover the named external fact kinds (capture, settlement cash, refund) with the minimal schema; real-evidence classes like bank statements are kept NOT_ADOPTED_V1 so assertions stay distinguishable from evidence.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "verification_label_vocabulary": {
      "status": "ADOPTED",
      "value": {
        "recordable": ["UNVERIFIED_ASSERTED"],
        "declared_not_bound": {"PROVIDER_CONFIRMED": "NOT_BOUND", "BANK_MATCHED": "NOT_BOUND", "CHAIN_CONFIRMED": "NOT_BOUND", "reject": "409 FACT_VERIFICATION_NOT_BOUND"},
        "derived_provenance": "DERIVED_FROM_UNVERIFIED_ASSERTED; derived values carry source_fact_ids and can never upgrade the label",
        "fold_status": "ACTIVE | SUPERSEDED (derived flag; supersede does not delete)"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-25",
      "cap_rows": ["CAP-09", "CAP-14", "CAP-19"],
      "rationale": "A three-layer vocabulary (recorded asserted / declared-not-bound confirmed / derived) keeps every simulated observation honest today while pre-declaring the upgrade path a real provider integration would use.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "recording_authority": {
      "status": "ADOPTED",
      "value": {
        "command": "record_external_fact on POST /api/overlay/commands (existing organizer seam; no new route, no new Protocol, no SEAMS row)",
        "human": "organizer role only; auditor/observer -> 403 FACT_ROLE_FORBIDDEN",
        "agent": "propose only, kind EXTERNAL_FACT, executionAuthorized=false; posting attempt -> 403 FACT_AGENT_FORBIDDEN, not recorded; operator adoption cites proposal_id (HUMAN_PENDING pattern)",
        "two_person": "NOT_REQUIRED_V1 — unverified assertions carry no funds or ledger effect",
        "authentication_honesty": "LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED; role label is not authentication"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-25",
      "cap_rows": ["CAP-01", "CAP-19"],
      "rationale": "Reusing the organizer-only overlay seam keeps one authority boundary; agent proposals stay in the existing simulated QUERY/PROPOSE lane, and two-person is reserved for actions with financial effect.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "fact_fold_location": {
      "status": "ADOPTED",
      "value": {
        "journal": "overlay journal (second journal); fold key state.external_facts; key absent when no entries",
        "entry_form": "overlay_id (dedup) / kind / payload; single kind EXTERNAL_FACT, class in payload.fact_class",
        "dedup": "same overlay_id + same payload returns original; different payload -> 409 FACT_IDEMPOTENCY_CONFLICT",
        "append_only": "no edit or delete; corrections are new entries carrying supersedes_fact_id (A-4)",
        "envelope": "no new envelope section, no new file; pinned FSM journal and vendor bytes untouched",
        "overlay_schema": "1; if OVERLAY_STATE requires a bump for a new fold key, that rule wins -> overlay_schema 2 plus new golden, decision content unchanged"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-25",
      "cap_rows": ["CAP-10", "CAP-14"],
      "rationale": "One kind plus a class discriminator minimises consumer branching; folding into the existing overlay journal keeps the no-new-storage-engine rule and the empty-equals-absent digest invariant.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "recon_consumption_rule": {
      "status": "ADOPTED",
      "value": {
        "allowed_consumers": {
          "reconciliation": "three additive checks when facts exist: recorded_captures_vs_claim_face, recorded_settlement_cash_vs_distributed, recorded_refunds_vs_refund_face; results MATCH | ASSERTED_MISMATCH | NO_FACTS; diagnostic flag OBSERVED_FACT_MISMATCH only, no auto-repair; base CHECK_IDS unchanged",
          "forecast": "GET /api/terms/portfolio/forecast may overlay SETTLEMENT_CASH_ARRIVAL as recorded_actuals_krw per bucket with constant actuals_source: UNVERIFIED_ASSERTED; absent when no facts"
        },
        "statement_surface": "actual_paid stays NOT_BOUND; facts appear only in a separate recorded_actuals block; primary and resale never summed",
        "forbidden_consumers": ["pinned FSM (no command or state derived; F04 journal and state_digest unchanged)", "shadow slice derivations (served/outstanding/encumbered/source_available)", "eligible_face and borrowing base", "underwrite U1-U6", "setoff-proposal-quote and waterfall sources"],
        "boundary": "asserted cash is not ledger-observed cash and is never a set-off source"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-25",
      "cap_rows": ["CAP-09", "CAP-14"],
      "rationale": "Recon compares journal to assertions and forecast displays asserted actuals; both are read surfaces, so facts stay useful without ever feeding the pinned FSM, slice arithmetic, borrowing base or set-off sources.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "derived_value_source_rule": {
      "status": "ADOPTED",
      "value": {
        "storage": "derived values are never stored; pure function of journal + overlay computed per read",
        "fields": ["derived: true", "derivation (rule name)", "source_fact_ids"],
        "provenance": "DERIVED_FROM_UNVERIFIED_ASSERTED inherited; no upgrade",
        "supersede": "SUPERSEDED facts excluded from all derivations; replacement entry takes effect on next read",
        "empty": "no facts -> derived blocks entirely absent -> byte-identical output and digests",
        "determinism": "integer arithmetic only; no wall-clock, sim_day-of-read or instance_id inputs"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-25",
      "cap_rows": ["CAP-01", "CAP-14"],
      "rationale": "Unstored pure derivations cannot drift from the journal, inherited provenance keeps honesty, and absent-when-empty preserves golden digests on fact-free books.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "capacity_bounds": {
      "status": "ADOPTED",
      "value": {
        "max_fact_entries": 128,
        "max_facts_per_claim": 16,
        "max_supersede_chain_depth": 4,
        "string_field_bytes": 64,
        "free_text": "none; reason fields are enums so no PII slot exists",
        "amount_krw": "integer >= 1 and <= MONEY_MAX 10^12",
        "overflow": "409 SIMULATION_CAPACITY with scope external_facts; no eviction",
        "precedence": "a lower global overlay bound wins",
        "script_budget": "<= 30 operations if fact commands count toward MAX_OPERATIONS 500"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-25",
      "cap_rows": ["CAP-08", "CAP-11"],
      "rationale": "Bounded enumerable facts fit the ten-claim demo book with headroom, keep fold cost flat, and refuse growth rather than evicting recorded assertions.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "digest_export_effect": {
      "status": "ADOPTED",
      "value": {
        "digest": "facts fold into overlay_state.digest under state.external_facts; empty book -> key absent -> overlay_schema 1; F04 state_digest, payload_sha256, tests/golden/demo.json and fact-free overlay goldens byte-identical; derived values excluded from digests",
        "export": "facts appear only inside the V3 overlay section; the seven existing sections, content_digest signing surface, CHECK_IDS and the V2/V3 SECTION_SET rule are unchanged; an overlay-empty book still exports V2",
        "new_golden_candidate": "tests/golden/overlay_external_facts.json",
        "coa": "NOT_POSTABLE_V1; CAPITAL-COA-V1 unchanged; memo accounts are a later projection node's decision",
        "closeout": "implementation node's test_count change requires CAPITAL-CLOSEOUT-REGEN-V1 digest regeneration"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-25",
      "cap_rows": ["CAP-13", "CAP-14", "CAP-15"],
      "rationale": "Keeping facts inside the existing V3 overlay fold guarantees byte-identical digests and exports on fact-free books, no new manifest section, and no accounting claim from unverified assertions.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

- `docs/decisions/CAPITAL_OBSERVATION_RECORD.md`에 여덟 항목(`fact_class_set`·`verification_label_vocabulary`·`recording_authority`·`fact_fold_location`·`recon_consumption_rule`·`derived_value_source_rule`·`capacity_bounds`·`digest_export_effect`) 각각의 status를 담은 `capital-decision-v1` 블록 하나 → §4.
- 모든 기록 사실은 `SIMULATED` + `UNVERIFIED_ASSERTED` + organizer-only + `funds_executed: false` → 상수를 §3 공통, 각 entry의 `value.constants`, 블록 최상위 `recorded_fact_constants`에 고정.
- `python3 scripts/decision_ledger.py --check`: 블록 스키마·필드는 main의 MERGED 노트(`default-recovery`, `claim-slice-registry`)와 같은 형태이고, 같은 검증 경로인 인자 없는 `python3 scripts/decision_ledger.py`가 이 노트를 schema finding 없이 파싱한다. main `e56224a`의 스크립트는 `--check` 플래그를 아직 받지 않으므로, 플래그 형태 그대로의 통과는 별도 선행 변경(§6)이 merge된 뒤에 성립한다 — 이 노트는 그 변경을 포함하지 않는다.

## 6. Open risks

- deps 두 노트를 직접 읽지 못했다(허용 경로 밖). `fsm_expressible`·agent lane 이름이 인용과 다르면 선행 노트가 이긴다 — 구현 노드가 인용 검사 시 확인한다.
- `SETTLEMENT_CASH_ARRIVAL`의 `payee_label`이 pinned 줄이 아닐 때의 라벨은 V1에서 거절로 닫았다; 다수 수취인 FSM이 오면 재검토.
- `PROVIDER_CONFIRMED` 승격 경로는 선언뿐이라 제공자 연결 계약(`fin-observation-reconciliation` 후보)이 정본을 정한다.
- 범위 분리: `--check` 별칭이 없으면 수용 기준 3의 문자 그대로 명령이 argparse 오류로 끝난다. 또 main의 `test_coa_candidate` 바이트 가드가 새 결정 노트를 diff로 잡는다면 그 처리도 이 노트가 아닌 선행 변경의 몫이다.

## 7. 후속 작업

- 선행 변경(이 노드 밖): `decision_ledger.py --check` 별칭과 그 테스트, 새 결정 노트에 대한 `test_coa_candidate` 가드 처리. 이 노트의 바이트를 테스트에 핀하지 않는다.
- `observation-record` 구현 노드: `record_external_fact` 명령·폴드·거절 코드·`/api/overlay` 조회·recon 세 검사·forecast `recorded_actuals` 구현, 골든 `overlay_external_facts.json` 추가, `scripts/docs_surface.py`·README needle·`scripts/decision_ledger.py --check` 갱신.
- recon 표면과 `fin-observation-reconciliation` upstream 후보의 대조는 별도 노드; 이 결정은 그 노드를 완료로 표시하지 않는다.
- `test_count` 변화 시 `CAPITAL-CLOSEOUT-REGEN-V1`으로 클로즈아웃 다이제스트 재생성.
