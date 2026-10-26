# Capital 청사진 요구사항과 구현·선행 매핑

CAP-14 observation seam: `ObservationPort` / `LocalFakeObservation` now supplies a
SIMULATED, read-only fixture fold only. CAP-14 and CAP-16 remain NOT_BOUND. The
fixture separately pins ADAPTER_EVENT_IDENTITY draft 0.1 at `e2a029d8ac3af7575888dac22fc4bf173ebec232`,
SHA256 `e640151bbdff15b67584337e6cdb6e95b2cc9c060f48dcc9de45df84f8de5345`,
as cited in CAPITAL_UPSTREAM_BINDING section 2. This is not the FSM pin or an
adoption of production identity, aliasing, authenticated queries, or wire layout.

2026-10-18. Capital 구현 기준 main `f1c5651b40bf9a15077a37a9769276dc28b8e1a1`.
실행·참조 소비자가 고정하는 Protocol 기준은 셋이며 범위가 다르다. (1) **`7481b0e16ce9b903abbffa62249bb91cd9e63cfe`**: vendor된 F04·F01–F03 FSM reference 다섯 파일의 바이트 핀(`capital/vendor/manifest.json`에 SHA256 잠금). (2) **`e2a029d8ac3af7575888dac22fc4bf173ebec232`**: AI 위임 권한 계약 초안 0.1(`docs/contracts/AI_DELEGATION_AUTHORITY.md`)과 `reference/ai_delegation/` mock의 읽기 전용 인용 핀([CAPITAL_UPSTREAM_BINDING.md](decisions/CAPITAL_UPSTREAM_BINDING.md) §3.9; agent lane, `tests/agent_claims.json`이 인용). (2)의 mock은 `capital/vendor/`에 vendor하지 않았고 manifest에 해시도 없다. (3) **`e2313ab473ea1b5a7b5b9246a564749188c1c2c8`**: STATE_LIFECYCLE.md LC-TERM/LC-FACT/LC-CUT 인용 핀(`tests/lifecycle_claims.json`); FSM vendor 핀과 별개다. Commerce main 확인 `7c2452645c50b8ede17bdd762794adeabe42319e`.
위 고정은 나열한 실행·참조 소비자에만 묶는다. (1)은 FSM 원본·vendor 바이트와 그 FSM·읽기 모델 클레임 표(`tests/upstream_claims.json`, `tests/fsm_contract_claims.json`, `tests/read_model_claims.json`)의 인용에, (2)는 AI 위임 초안 인용과 `tests/agent_claims.json`에, (3)은 수명 계약 인용과 `tests/lifecycle_claims.json`에 적용된다. `docs/decisions/`의 각 결정 노트는 `기준`·`bases` 칸에 그 노트 작성 시점의 역사적 연구 체크아웃을 따로 기록한다(예: [CAPITAL_CLAIM_SLICE_REGISTRY.md](decisions/CAPITAL_CLAIM_SLICE_REGISTRY.md)의 kix-protocol `9eb6b9f`). 그 값은 노트의 출처 증명이며 실행·참조 구속이 아니므로 위 고정의 범위 밖이다. 이전 CI·설계 후보·미래 계획의 존재를 현재 구현 완료로 옮기지 않는다.

DEV_ONLY `--dev-keyset`은 로컬 shared-HMAC 다중 kid·명시적 retirement 실험입니다.
`KEY_RETIRED`는 제공된 keyset snapshot 기준이며 운영 폐기 정책이 아닙니다.
CAP-15 stage7 인증 export, external key, authentication은 계속 NOT_BOUND입니다.

## portfolio-history-comparison

`capital/portfolio_compare.py` / `tests/test_portfolio_compare.py`:
`python3 -m capital.portfolio_compare --before SNAPSHOT_A --after SNAPSHOT_B`는
명시한 두 디렉터리의 `workspace.json`을 각각 한 번 읽고 같은 바이트로 오프라인
감사·메모리 복원을 수행한다. 기존 risk/covenant 계산을 재실행하여 advance별·합성
beneficiary_role별 노출, 만기/연체, 준비금 요구량, watch 상태·사유의 관측 차이를
결정적 `KIX_CAPITAL_PORTFOLIO_COMPARISON_V1` JSON으로 출력한다. 입력 해시와
순서가 고정된 비교 가능성 사유, 합계·증감 대사를 포함하며 입력 트리에 쓰거나
잠금을 잡지 않는다. 결과는 `SIMULATED`다.

필수 정책 6개(`interest_rate`, `term`, `default_loss_treatment`, `reserve`,
`additional_margin`, `underwriting_depth`)가 모두 존재하고 사용 가능한 ADOPTED여야
한다. 빈 장부나 BOUND 표시만으로 완전성을 대신하지 않는다.
실제 임시 결정 노트를 읽는 회귀 테스트도 빈 장부·인출 장부 양쪽에서 필수 항목별
검증 실패를 확인한다. 해시가 같아도 사용 불가 정책은 비교할 수 없다. 적용 대상 tier의
margin cure/rate/payee 입력도 필요하다. fixture/policy 입력 해시 및 fixture
profile/수익자 매핑 일치, sim_day 비감소, F04/overlay journal prefix 호환,
기존 advance 매핑·draw gate 안정성, 기록된 terms binding 호환을 요구한다.
추가 overlay는 이전 F04 journal 끝 이후에만 위치해야 한다. 불일치 시
`NON_COMPARABLE`, `changes: null`(exit 1), 성공 exit 0, 인수 오류 exit 2다.

차이는 after-before이며 준비금은 advance별 기존 정수 내림 계산이다. 실제 지급,
인과관계, 파일의 인증된 공통 소유권은 추론하지 않는다. 비교 시점 로컬 정책을
사용하므로 historical_policy_provenance/authentication/common_ownership/actual_payments는
`NOT_BOUND`다. reserve funding/coverage도 `NOT_BOUND`이며 준비금을 기장하지 않는다.
자동 수집·import·예측·what-if·영속 이력 DB·새 회계정책은 범위 밖이다.
계약은 `docs/INTEGRATION.md`, 실제 실행 증거는 `docs/VALIDATION.md`를 참조한다.

## 권위와 전체 범위

사용자의 2026-10-07 지시는 Capital을 `SUNBURN-Golden/KIX-CAPITAL`에 구현하며 KIX Protocol의 큰 청사진을 따르라는 것이다. 따라서 과거 Finance 후보의 “새 저장소 없음/화면은 Commerce” 토폴로지는 이번 **Capital 로컬 개발 위치**에 적용하지 않는다. 그것이 후보 금융 정책 채택·AIOPS 신규 프로그램 생성·upstream 노드 완료·운영 권한 확대를 뜻하지는 않는다. Protocol·Commerce는 수정하지 않는다.

현행 범위의 정본은 [DEVELOPMENT_PLAN](https://github.com/SUNBURN-Golden/kix-protocol/blob/7481b0e16ce9b903abbffa62249bb91cd9e63cfe/docs/DEVELOPMENT_PLAN.md)과 채택된 결정이다. `BLUEPRINT_20260914` 및 `PROTOCOL_MASTERPLAN_V2/V23/V24`의 폐기 표시는 **현행 작업 승인으로 사용하지 말라는 의미**다. 금융 목표와 과거 안전 요구를 버리라는 의미로 읽지 않는다. `FINANCE_COMPLETION_DESIGN_KO`는 PENDING_NOT_ADOPTED이며 stage5/6 선행을 유지한다.

읽은 계획군과 적용 사항:

- `docs/BLUEPRINT_20260914.md` §§5–7,10–16: 원 요청·관측·금전 의무·실행 분리, 금융 근거의 기준시점/범위, 최초 판매·리셀·환불·미회수금, 통합 수용 및 비공개/독립 복구.
- `docs/PROTOCOL_MASTERPLAN_V2.md` §§3–14: 전체 객체, 복수 결제·부분 성공, 다중 자산, 네 금융 계약군, 관람권 분리, AI 권한, T01→T03→T04→T05→T06 통합 수용.
- `docs/PROTOCOL_MASTERPLAN_V23.md` §§2–8 및 `V24` 전체: Rust-first 운영 경계, u128/asset registry, source-consistent export, UNKNOWN와 자원 격리. 역사적 PostgreSQL-only·자동 R2를 현재 결정으로 채택하지 않음.
- `docs/decisions/AUTHORITY_MODEL_1.md`, `PROGRAM_DECISIONS_20260928.md`, `PROGRAM_ROADMAP_20260930.md` R-1~R-11: 체인 권리/위임 실행, 현재 mock 허용, 정책 심화·stage5/6/7·RS/TL 선행, User-only 결정.
- `docs/decisions/TOKEN_LAYER_AND_RIGHTS_SCALE_SCOPE_20260929.md`: RS와 TL은 별개 선행, 16슬롯 역사 참조를 큰 규모 완료로 읽지 않음, coin/운영 잠금.
- `docs/aiops/FINANCE_COMPLETION_DESIGN_KO.md` §§1–10: 금융 투영·복식 수치·관측·대사·노출·export·조회 8개 후보를 삭제하지 않음. 회계·정산 정책과 실제 producer 선행 유지.
- `docs/aiops/CONTRACT_RELEASE_AND_COMPLETION_DESIGN_KO.md`: exact producer/SDK/manifest/profile/vector 계약, pending 소비·분모·실제 서비스 qualification 구분.
- `docs/contracts/CREDIT_ADVANCE_F04.md`, `SETTLEMENT_DISTRIBUTION_F01_F03.md`: 이미 구현된 참조 의미와 미정 금융 정책 구별.
- Commerce `docs/credit-depth-apps-bind.md`, `settlement-depth-apps-bind.md`, `docs/aiops/COMMERCE_PRODUCT_EVOLUTION_KO.md`: 클라이언트 산술 금지, UNKNOWN 재전송 차단, read cut/모드/사용자 수용 분리. 실제 확대 catalogue와 live mode는 NOT_BOUND.

## 요구사항 매트릭스

`SIMULATED`는 현재 main 구현의 로컬 합성 범위만, `READ_ONLY_FIXTURE`는 불변 참조 데이터 조회만, `NOT_BOUND`는 실제 producer 계약 미연결, `DECISION_REQUIRED`는 정책 미정이다. 행을 완료 분모에서 제거하지 않는다.

| ID | 청사진 요구 | 현재 제품·검증 | 상태 / 다음 선행 |
|---|---|---|---|
| CAP-01 | 대여·선지급 전 기간 | F04 offer/approve/reject/cancel/bind/draw/repay/close/default/reconcile API·화면, 조건 오버레이(조회 `GET /api/overlay`; sim_day 시계의 유일한 작성자 `POST /api/overlay/commands` — organizer 전용 advance_day from→to CAS가 sim_day를 전진시키고 ACT/365 단리 이자 메모를 계상, F04 저널·state_digest 불변), 읽기 전용 상환 배분 견적(`GET /api/terms/{id}/allocation`), 읽기 전용 포트폴리오 조건 롤업(`GET /api/terms/portfolio`), 읽기 전용 현금 사다리 예측(`GET /api/terms/portfolio/forecast`, `SIMULATED_CASH_FORECAST`)과 U1–U6 인수 기록(`GET /api/underwrite/{id}`, `SIMULATED_UNDERWRITING_RECORD`), 운영 데스크(`#desk`, 브라우저 전용 화면: `POST /api/overlay/commands`의 advance_day로 sim_day를 전진시키는 제어, F04 저널과 오버레이 기록을 합친 사례 타임라인, 서버가 사유를 붙인 다음 작업; 새 서버 경로·권한 없음). 고정된 upstream 읽기 모델 초안 `docs/contracts/READ_MODEL_QUERIES.md`(`7481b0e`)의 §2.12 `get_credit_advance`·§2.13 `get_credit_claim`·§8 비변경을 인용한 클레임 표 `tests/read_model_claims.json`과 `scripts/read_model_claims_check.py`가 기존 읽기 표면(`GET /api/state`의 case 뷰, in-process `CreditMachine.view_claim`)에 대조한다(`CLAIM_CONFORMANCE`; 모든 검사는 §8 비변경 가드 아래 읽기를 실행하고, upstream 쿼리 이름 구현·경로 추가·카탈로그 승격은 아님) | SIMULATED; 이자·기간·손실은 [docs/decisions/CAPITAL_FINANCIAL_TERMS.md](decisions/CAPITAL_FINANCIAL_TERMS.md)의 **PROVISIONAL (CAPITAL-TERMS-V1)** 를 오버레이가 표시한다. 청약·실자금·upstream 채택 아님. 로컬 합성만: 쓰기는 오버레이 시계 명령뿐, 이자는 미지급 메모, 실자금 이동 없음 |
| CAP-02 | 수익참여·배분 | 제품 연동 준비 카드와 일회용 장부의 잠정 배정 순서 비교 | DECISION_REQUIRED: 수익/원가·회수 순서·비율/상한·조정은 PROVISIONAL per docs/decisions/CAPITAL_SETTLEMENT_POLICY.md 이고 고정 FSM이 표현하지 못해 FSM 경로는 계산하지 않음; 단일 청구 게시만 `GET /api/policy/shadow`가 SHADOW_NOT_APPLIED 그림자로 계산(CAPITAL_SHADOW_POLICY §3.7); V2 §7 |
| CAP-03 | 정산채권 양도·매입 | 금융권리/관람권 분리 표시, 원 claim 조회 | DECISION_REQUIRED: 원 채권·배정량·보유자·대가·우선순위·회수는 PROVISIONAL per docs/decisions/CAPITAL_SETTLEMENT_POLICY.md 이고 UNSUPPORTED_BY_PINNED_FSM; 슬라이스 크기·가격만 SHADOW_NOT_APPLIED 그림자로 계산하고 등록부는 SHADOW_DEFERRED (CAPITAL_SHADOW_POLICY §3.7) |
| CAP-04 | 담보·준비금 | 공유 액면 예약·해제·미이행 유지 검사, 읽기 전용 완전성·차입기초·준비금 표시, 읽기 전용 상계·회수 제안 견적(`GET /api/terms/{advance_id}/setoff` — CAPITAL-TERMS-V1의 ADOPTED `collateral_execution` 1차 단계 `SETOFF_AGAINST_BENEFICIARY_SETTLEMENT_DISTRIBUTION`만 적용, `proposal_only` true·`applied` false), 마진콜·치유기간(cure window)·가속·DEFAULT_ELIGIBLE 제안(사람 운영자용 제안뿐, F04 default 미호출·F04 저널 불변)을 `POST /api/overlay/commands`의 advance_day 틱이 오버레이에 기록하고 `GET /api/overlay`의 margin 블록이 조회한다. 일회용 장부(SIMULATED_DISPOSABLE_BOOK, ScenarioReplaySource)에서만 발동하고 워크스페이스 fixture는 FIXTURE_VIEWS_IMMUTABLE로 triggered false, 읽기 전용 포트폴리오 위험 분석 `GET /api/risk`(라벨 SIMULATED, `projection:read`): 손실 준비금 요구액은 CAPITAL-TERMS-V1 표(150/500/2500/10000 bps)의 건별 내림 합이며 회계 정책이 아니고 기장하지 않음(applied false), 고정 환불 충격 `[500, 1000, 2500, 5000]` bps 스트레스는 SIMULATED 가정이며 마진콜을 기록하지 않음(applied false) | SIMULATED; [docs/decisions/CAPITAL_FINANCIAL_TERMS.md](decisions/CAPITAL_FINANCIAL_TERMS.md) **PROVISIONAL (CAPITAL-TERMS-V1)**. 집행·심사 규칙은 applied false. 청약·upstream 채택 아님. 로컬 합성만; 마진 규칙은 SIMULATED 메모이며 담보 집행·법적 채무불이행 아님; 가속 후 이자 재기준과 부도 명령일 기준 상각 적격일, 부도 후 회수·상각 메모는 PROVISIONAL per docs/decisions/CAPITAL_DEFAULT_RECOVERY.md 를 적용한 overlay-recovery-writeoff로 구현됨(가속 건 interest_rebased true, recovery 블록 SIMULATED·proposal_only true·f04_default_called false); 준비금 원장은 NOT_BOUND |
| CAP-05 | 청구·수취인·분할 정산 | F01–F03 고정 시나리오에서 두 배정 순서·부분 명세서·중복/상충·늦은 현금의 단계별 의무 비교. 잠정 순서는 일회용 장부에서만 비교 | READ_ONLY_FIXTURE; 운영 배분 순서는 미채택. 잠정 순서는 PROVISIONAL per docs/decisions/CAPITAL_SETTLEMENT_POLICY.md |
| CAP-06 | 환불·공연취소·회수 | 배정 전/후 부분 환불, 단일 전액 vs 분할 환불, 취소 수락·회수·은행 미종결 비교; 환불 부담 RC1–RC4(RC5는 리셀로 라우팅)·리셀 해제 RU1–RU3의 읽기 전용 그림자 산술 `GET /api/policy/shadow`(SHADOW_NOT_APPLIED, 적용·자금 집행 아님) | 일부 SIMULATED; 부분 환불·리셀 과거계약 취소 부담은 PROVISIONAL per docs/decisions/CAPITAL_SETTLEMENT_POLICY.md 이고 requires upstream FSM change; 그림자 결과는 FSM에 적용하지 않음(applied_to_fsm false), 단일 청구 수익 참여 게시·슬라이스 크기/가격·UC1–UC4 분할은 SHADOW_NOT_APPLIED 그림자로만 계산하고 다중 청구·창·등록부·타이머·배치는 SHADOW_DEFERRED |
| CAP-07 | 최초 판매·반복 리셀·입장 연계 | trade/claim identity 조회, 권리/금융 분리 | NOT_BOUND: Commerce 실여정·Protocol producer tuple; 이 PR은 티켓 생성/이전 없음 |
| CAP-08 | 초과 배정·현금/한도 구별 | 동일 claim 두 draw 경합, 부분 repay 후 예약 유지, close만 해제; 활성 상태를 바꾸지 않는 인출 사전점검 | SIMULATED; 외부 담보/분산 자원 한도 아님 |
| CAP-09 | 승인액/매출/권리확정/지급/환불 보고 | 로컬 다섯 구분 명세서: 승인·노출/상환/잔액·예약은 FSM 조회(SIMULATED), 정산 확인/배정·환불은 고정 fixture. `primary_sales`·`resale_sales`·`actual_paid`는 NOT_BOUND이고 최초판매와 리셀은 합산하지 않음. cut·fixtures digest·capacity bound 표기 | SIMULATED(로컬 후보); 로컬 진단만; 실지급·세무 보고·은행 대사 아님 |
| CAP-10 | 원 operation/최초 결과/UNKNOWN | 단일 POST, 원 receipt 조회, absent→UNKNOWN, reload·old-instance fence, 옵트인 로컬 파일 재시작 복원. `tests/lifecycle_claims.json`·`scripts/lifecycle_claims_check.py --execute`의 12개 loopback HTTP 대응 검사(CLAIM_CONFORMANCE / SIMULATED / funds_executed false); 체크아웃 없으면 인용 SKIPPED. 후기 현금은 READ_ONLY_FIXTURE이며 운영 종결·provider custody·분산 lease fencing 구현은 아님 | SIMULATED(로컬 후보); 개발용 LOCAL_FILE_WORKSPACE. stage5 내구 거래·inbox/outbox·호스트 간 fencing은 CAP-11 |
| CAP-11 | 내구 거래·inbox/outbox·장애복구 | 연동 계약과 미지원 상태 | NOT_BOUND: `k-stage5-durable-tx`·backend 채택·v5, 자체 저장엔진 만들지 않음 |
| CAP-12 | 자산별 정확한 금액·FX | KRW 고정 프로파일, int 검증, 포트폴리오 BigInt 표시. KRW를 코드에 한 번 선언한 AssetSpec(`{namespace: fiat, reference: KRW, decimals: 0, max_atoms: 10^12}`)을 `GET /api/state`와 export manifest `source_pin`의 `assets`로 노출하고, 명령 본문의 선택 `asset`이 그 선언과 다르면 `ASSET_MISMATCH`로 적용 전에 거절한다(저널·receipt 없음). `docs/decisions/CAPITAL_UPSTREAM_BINDING.md` §3.6의 PROVISIONAL 결정 | 일부 SIMULATED; u128·registry/정밀도·FX quote/execution은 별도 계약. registry DEFERRED, FX NOT_ADOPTED, 다중 자산 원장·교차 자산 합산 없음 |
| CAP-13 | 복식 금융 투영 | 로컬 후보 복식 투영 · `SYNTHETIC_UNADOPTED` 표기 · 운영 원장 `NOT_BOUND` | SIMULATED(로컬 후보); fin-ledger-contract·stage5/6 선행 유지, 계정/수익인식/세무 미정; 추가형 `CAPITAL-COA-V1` 후보(`mode=coa-candidate`, `SIMULATION_FIXED_V2`)도 `SYNTHETIC_UNADOPTED` |
| CAP-14 | 원관측·대사 예외 | 로컬 대사 예외: receipt↔저널 키, 거절 receipt의 저널 부재, 재생 digest, 제안↔fixture, 투영↔조회, fixtures digest. 오버레이가 비어 있지 않을 때만 조건부 검사 `overlay_fold_digest_equals_persisted`(오버레이 fold digest가 저장된 digest와 같은지)가 붙는다. `GET /api/reconciliation?mode=coa-candidate`에서만 `coa_candidate_totals_vs_v1`(후보 투영 합계가 V1과 같은지)과 `interest_ledger_vs_projection`(후보 이자 기장이 오버레이 fold와 같은지) 두 검사가 더 붙고, 기본 검사 여섯 개(`CHECK_IDS`)는 그대로다. 없는 receipt는 UNKNOWN_UNRESOLVED이며 재시도·해소하지 않음 | SIMULATED(로컬 후보); 로컬 진단만; 은행·PG·제공자 관측, source cut, 제공자 인증 완전성은 NOT_BOUND |
| CAP-15 | 인증 export·일관 source cut | v1 journal JSON은 그대로 두고, 오버레이가 비어 있으면 `KIX_CAPITAL_EXPORT_MANIFEST_V2`(`tests/golden/demo.json`과 바이트 동일)가 journal·receipts·projection·reconciliation·statement·fixtures·source pin 일곱 섹션을 각각 canonical JSON sha256으로 묶고, 오버레이가 비어 있지 않으면 `KIX_CAPITAL_EXPORT_MANIFEST_V3`가 그 일곱 섹션에 `overlay` 섹션을 더한다. 오프라인 verifier는 V2와 V3를 모두 받고, 포맷과 섹션 집합이 어긋나면(`overlay` 없는 V3, `overlay` 있는 V2) `SECTION_SET`으로 거절한다. content_digest는 instance_id와 시각을 제외한다. cursor·watermark·source_cut은 null이며 NOT_BOUND. SignaturePort의 기본 서명은 NOT_BOUND이고, 옵트인 Dev HMAC은 DEV_ONLY·무결성만이다. 오프라인 verifier가 섹션 해시·digest·서명을 다시 계산한다 | SIMULATED(로컬 후보); 로컬 진단만. stage7 인증 export가 아니다. 외부 키·교차 서비스 cursor·watermark·보존 기간 값은 없다. retention_policy는 다섯 이름 있는 빈 칸(칸마다 owner·status)이다. SignaturePort가 이후 인증을 붙이는 채택 경계다 |
| CAP-16 | SDK·API 적합성 | 로컬 계약 `capital-local-facade/1` (`capital/contract/facade-v1.json`)와 ProducerPort 양성·음성 vectors. strict 로컬 envelope와 vendor byte hash. 이 vectors는 SEMANTIC_CONFORMANCE가 아니다 | NOT_BOUND(로컬 후보); 확대 OpenAPI/SDK/SEMANTIC_CONFORMANCE exact tuple. 로컬 facade 계약이 그 tuple을 대체하지 않는다 |
| CAP-17 | 공개/비공개·권리 규모 | 외부 의존성과 관람권 비권위 표시 | NOT_BOUND: RS-0~5, privacy/currentness, 1024/16384/65536 규모 검증 없음 |
| CAP-18 | 선택적 토큰 담보·보상 | 향후 연동 설명, 외부 호출·발행 코드 없음 | NOT_AUTHORIZED: TL 계약·coin lock/user 결정; KRW 목을 토큰 한도로 확장 안 함 |
| CAP-19 | AI 운영·권한·최소공개 | 로컬 합성 역할(organizer/auditor/observer/agent)을 서버가 강제하고 receipt에 표시. agent는 SIMULATED QUERY/PROPOSE 픽스처만 호출하고 제안은 HUMAN_PENDING이며 effects_executed는 false. 계정·비밀번호·개인정보 없음. `tests/agent_claims.json`과 `scripts/agent_claims_check.py`가 초안 `e2a029d`의 클레임을 이 SIMULATED agent lane에 대조한다(`CLAIM_CONFORMANCE`; 결과는 SIMULATED이고, upstream 인용 드리프트 검사는 프로토콜 체크아웃 없이는 `SKIPPED`이며 통과가 아니다) | NOT_BOUND: AgentGrant/ActionPermit, 실제 IdP·KYC·자격증명, 현재 근거·권한·비밀 분리. SIMULATED 레인은 실권한 아님 |
| CAP-20 | 접근성·통합 수용 | 실제 browser 정상/거절/UNKNOWN/reload, mobile, keyboard, screenshot, 운영 데스크 `#desk`(sim_day 제어·사례 타임라인·서버 사유 다음 작업)의 organizer/auditor/observer 데스크톱·375px 검증(`tests/browser/operator-desk.spec.cjs`) | SIMULATED(자동검증만); 사용자 수용 PENDING, full T01→T06/서비스 qualification 미실행 |

## Finance 후보 8개를 유지하는 후속 위치

`fin-ledger-contract`(계약), `fin-double-entry-projection`, `fin-multi-payee-refund-proof`, `fin-observation-reconciliation`, `fin-credit-exposure-reconciliation`, `fin-consistent-accounting-export`, `fin-catalogue-read-model`, `fin-finance-closeout`의 정확한 이름/선행은 upstream `FINANCE_PENDING_NODES.json`이 정본이다. 이 PR에서 노드를 adopt/DONE으로 바꾸거나 분모를 줄이지 않는다. Capital 시뮬레이션·참조 pin·문서 매핑은 그 실행 영수증을 대신하지 않는다. 후보 node ID가 개정되면 원 정의와 digest를 함께 대조한다.

## 현재 필요한 결정과 진행 가능한 부분

현재 로컬 시뮬레이션은 정책 결정 없이 검증 가능하다. 따라서 단계마다 승인을 요구하지 않고 구현·검증·Draft PR을 진행한다. 향후 금융계약 실행을 열 때만 정확한 미정 항목(수익/우선순위·이자/수수료/기간·환불 부담·계정/법무/면허·source backend 채택)을 사용자/지정 담당자에게 결정 요청한다. 소스 리뷰/CI 통과는 해당 결정을 대신하지 않는다.

## 추가 제품화와 실제 차단점

같은 PR에서 DB 없이 가능한 CAP-05/06의 참조 시나리오를 9개·35단계로 구현했다. 모든 배정·환불 수치는 고정한 upstream 목에서 계산한다. 클라이언트는 수치를 재계산하지 않는다. 다섯 읽기 전용 보존식·예상 거절·거절 시 상태 보존은 별도로 검사한다. CAP-08의 인출 사전점검은 현재 저널의 별도 복제본만 변경하므로 활성 제안·예약·receipt에 효과가 없다. CAP-16의 파일 무결성 표시는 source byte 일치에만 한정된다. 로컬 부분은 `capital-local-facade/1` 계약과 ProducerPort vectors이며, SEMANTIC_CONFORMANCE exact tuple은 NOT_BOUND다.

나머지는 화면에서 제품 행동별로 구분한다. CAP-13의 로컬 후보는 `SYNTHETIC_UNADOPTED` 표식의 읽기 전용 투영이며 계정·수익인식·세무를 정하지 않고 `fin-ledger-contract`를 채택하지 않는다. CAP-09의 다섯 구분 명세서와 CAP-14의 대사 예외는 로컬 진단이다. 은행 대사·제공자 인증 완전성·실지급을 주장하지 않고, 최초 판매와 리셀 매출을 합산하지 않는다. 수익참여·채권매입·외부담보 실행은 금융 조건 결정이 필요하다. 실제 주문/리셀/권리 연결은 exact producer/SDK/profile이, 내구 원장·채택 복식·인증 export는 stage5/6/7과 Finance 후보 채택이 필요하다. 로컬 manifest와 SignaturePort는 그 채택을 대체하지 않는다. 공유 HMAC 키는 무결성일 뿐 인증이 아니다. 다중 자산·권리 규모·비공개·AI 권한은 해당 upstream 계약이 필요하다. 실서비스 실행은 현재 승인되지 않았다. 이 차단점을 가상 계산이나 자체 backend로 대체하지 않는다. 각 행은 계속 전체 Capital 범위에 남는다.

- portfolio-consistent-read: `GET /api/portfolio/snapshot` / `capital/portfolio_snapshot.py` / `tests/test_portfolio_snapshot.py`: one lock-held SIMULATED local diagnostic cut of terms, risk, covenants and forecast; explicit completeness, current instance and projection:read. Authenticated/cross-process cuts and historical storage remain NOT_BOUND/out of scope.

어댑터 정체성의 로컬 CLAIM_CONFORMANCE: `tests/adapter_identity_claims.json`과 `python3 scripts/adapter_identity_claims_check.py --execute` (SIMULATED, facade analogue, method divergence 명시). 운영 절차는 [adapter-identity-claims](OPERATOR_HANDBOOK_KO.md#adapter-identity-claims)를 참조한다. 체크아웃 없는 drift는 SKIPPED다.
