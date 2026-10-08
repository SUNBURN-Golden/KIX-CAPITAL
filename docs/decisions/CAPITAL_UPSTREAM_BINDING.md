# Capital 상위 연동 결정 — producer/SDK tuple, stage5/6/7, IdP·KYC, 자산 registry, RS/TL/AI, T01–T06, 배포·TLS·보존

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
이 문서는 KIX-CAPITAL 저장소 안의 **시뮬레이션·제품 설계용** 결정이다. 청약이나 대출 제안이 아니고, 실자금이 움직이지 않으며, production은 계속 `NOT_AUTHORIZED`다. 법률·세무·회계·인허가 관련 내용은 **전문가 검토 전의 작업 가정(WORKING ASSUMPTION)** 이며 법률·세무·회계 자문이 아니다. 어떤 upstream 계약도 실제 upstream 영수증(repo·PR·commit·파일 경로) 없이 채택됐다고 적지 않는다. 이 문서는 kix-protocol·kix-commerce-apps를 수정하지 않고, 어떤 upstream 노드도 완료로 표시하지 않으며, diff는 `docs/decisions/` 한 파일이다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `upstream-binding-decision` (Decision: upstream adoptions, backend/IdP choices, RS/TL/AI scope, T01–T06) · deps `pr1-merge-ready` · kind `decision` |
| 결정자 | **Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08** |
| 위임 원문 | 2026-10-08 18:25 KST JunTae Park: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." |
| 결정일 | 2026-10-09 |
| KIX-CAPITAL 기준 | main `0514789` (audit10-fix3 #15). 선행 결정 문서는 [docs/decisions/CAPITAL_FINANCIAL_TERMS.md](CAPITAL_FINANCIAL_TERMS.md)(`CAPITAL-TERMS-V1`, 2026-10-08) 하나이며, 이 문서는 그 값과 충돌하지 않는다 |
| kix-protocol 기준 | main `e2a029d8ac3af7575888dac22fc4bf173ebec232` (읽기 전용 체크아웃 `/workspace/capital-run/kixproto-ro`, `.git/refs/heads/main`과 `origin/main` 동일) |
| kix-commerce-apps 기준 | 이번 세션에 체크아웃 없음. `docs/CAPITAL_REQUIREMENTS_KO.md`가 기록한 Commerce main `7c2452645c50b8ede17bdd762794adeabe42319e`만 인용하며 다시 읽지 않았다 |
| vendor pin | `capital/vendor/manifest.json` commit `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`, 다섯 파일 SHA256 불변. 이 결정은 `capital/`·`tests/`·vendor 바이트를 바꾸지 않는다 |
| 상태 어휘 | **ADOPTED** = 실제 존재하는 upstream 산출물을 Capital의 binding 대상으로 지금 채택(영수증 필수, adapter 노드 개방 가능). **DEFERRED** = 목표 binding은 정했으나 Capital이 묶을 upstream 산출물이 아직 없거나 묶을 수 있는 상태가 아님(명명한 영수증이 생기면 adapter 노드 개방). **NOT_ADOPTED** = 요청된 형태로는 V1에서 묶지 않기로 결정하고 대안 방향을 적음. `value`는 ADOPTED에서만 채우고 나머지는 `target`에 방향을 적는다 |

## 1. 결정 요약

| item | 결정 | CAP rows | 소비 노드 / seam |
|---|---|---|---|
| `producer_sdk_tuple` | **DEFERRED.** 목표 binding은 upstream 확대 catalogue(credit·settlement 명령 포함) + `kix-compat-manifest/1` tuple + `SEMANTIC_CONFORMANCE` profile. Capital은 Python이므로 TS SDK를 내장하지 않고, 같은 OpenAPI 계약·같은 manifest tuple을 핀하여 loopback 통합 관문(HTTP)에 결합한다. 현재 upstream에는 BOOTSTRAP(`bootstrap-1`, 40개 명령, credit/settlement 명령 없음)만 있어 묶을 수 없다 | CAP-07, CAP-16 | `producer-port-catalogue-adapter` / `ProducerPort` |
| `stage5_durable_backend` | **DEFERRED** (upstream 영수증 있음: PR #140 `bb193efb…`가 5단계 로컬·비운영 **PostgreSQL 17.11**을 채택). Capital의 StoragePort 목표 backend는 그 결정과 동일하며 다른 backend를 고르지 않는다. 단 Capital이 묶을 `k-stage5-durable-tx`(inbox/outbox·예산·재생 계약)는 미착수이고 v5 crate가 선행이라 binding은 보류 | CAP-11 | `storage-port-postgres-adapter` / `StoragePort` |
| `stage6_finance_candidates` | **DEFERRED.** 여덟 후보 ID는 `docs/aiops/FINANCE_PENDING_NODES.json`이 정본(PENDING_NOT_IN_PLAN). Capital은 두 번째 원장을 만들지 않고, 로컬 산출물(투영·대사·명세서·시나리오·manifest)을 각 후보의 **입력 벡터 후보**로 제공한다. `fin-ledger-contract`가 사용자 병합되면 ProjectionPort adapter를 연다 | CAP-13, CAP-14 | `projection-port-ledger-contract-adapter` / `ProjectionPort` |
| `stage7_authenticated_export` | **DEFERRED.** 목표는 `runtime/AUTHENTICATED_EXPORT.md`(architecture v5)의 ExportManifestV1 확장 필드와 서명/루트/registry 경계. Capital manifest v2의 `cursor`·`watermark`·`source_cut`·`external_key`·`retention_policy`·`authentication`가 그 자리에 들어간다. DEV HMAC은 그때까지 DEV_ONLY | CAP-15 | `signature-port-stage7-adapter` / `SignaturePort` |
| `identity_provider_kyc` | **NOT_ADOPTED (V1).** Capital은 자체 IdP·KYC를 운영하지 않는다. 목표 모양은 KIX 표면 공통의 **OIDC 형태 bearer 토큰 → Capital principal** 경계(역할 클레임을 Capital 권한 매트릭스로 매핑)이고, KYC/AML 결과는 Capital이 계산하지 않는 **외부 attested fact**로만 받는다. 벤더는 UNDETERMINED(법무·인허가 의존). 합성 역할(organizer/auditor/observer)은 V1 그대로 | CAP-19 | 이번에 열지 않음 (`f04-real-funds-lift-criteria` 뒤) / `AuthorizerPort` |
| `asset_registry_fx` | **DEFERRED.** 목표 자산 모델은 upstream `AssetSpec(namespace, reference, decimals, max_atoms ≤ 2^128−1)` + 인증된 registry version(S062 §4·개발계획 §11). Capital은 KRW 프로파일을 그 모양으로 **명시 선언**하고 자산별 분리 원장·교차 자산 합산 금지를 지킨다. **FX 견적·환전 실행은 Capital 안에 두지 않는다(NOT_ADOPTED)**; 외부 adapter·`tl-price-source-contract` 이후 | CAP-12 | `asset-spec-declaration`(동기화, adapter 아님) |
| `rights_scale_privacy` | **DEFERRED.** Capital은 권리 권위가 아니며(NOT_ADOPTED: rights authority·비공개 노트 보관), RS-0 프로파일 0.1(#125)의 식별 체계(ShowControl·페이지·슬롯·세대)를 producer tuple을 통해 **참조만** 한다. 규모 가정은 65,536석(RS-4 L3)으로 두고 Capital 한도·용량을 그에 맞춘다 | CAP-17 | producer tuple 뒤 / `ProducerPort` |
| `token_layer_coin_lock` | **DEFERRED.** coin/TIX 잠금(Task 005 결정 5, ADR-0002)을 그대로 지킨다. Capital에는 영원히 coin 모듈이 없다. 담보·준비금 엔진을 **자산 불문(AssetSpec)** 으로 설계해 TL-2 localnet·`tl-price-source-contract`·TL-L 뒤에 **보조 담보**로만 꽂을 수 있게 한다. 토큰 단독 담보·토큰 수수료·보유=혜택은 NOT_ADOPTED(TK-12·청사진 §4.3) | CAP-18 | TL-2·TL-L 뒤 / `TermsPolicyPort` |
| `ai_agent_grant_action_permit` | **ADOPTED (부분 범위: grant·proposal lane).** upstream `docs/contracts/AI_DELEGATION_AUTHORITY.md` 초안 0.1(#130)과 `reference/ai_delegation/ai_delegation_mock.py`(main `e2a029d`)를 F04와 같은 방식으로 **바이트 핀 vendor 복사**해 AuthorizerPort의 `agent` principal lane으로 묶는다. AI는 QUERY/PROPOSE만, EXECUTE는 거절. `ActionPermit`은 upstream에 없어 **NOT_ADOPTED**(`ai-delegation-execution-decision` 사용자 결정 뒤) | CAP-19 | `agent-grant-authorizer-adapter`(지금 개방 권고) / `AuthorizerPort` |
| `t01_t06_qualification` | **DEFERRED.** T01–T06(`PROTOCOL_MASTERPLAN_V2` §13, 역사 문서)을 Capital 수용 사다리 Q0–Q5로 매핑한다. T05(금융 연계)와 T06(복구·AI)은 Capital 소유, T01–T04는 producer 소유. 지금 가능한 것은 T05/T06의 **합성 변형**(Q0·Q1)뿐이며 통합 수용·서비스 qualification은 tuple·host 자격 뒤 | CAP-20 | `acceptance.py` 확장(동기화) |
| `deployment_tls_retention` | **DEFERRED.** 보존은 upstream 보존 기간 제안 R1(#139 `6e54e723…`)의 **네 칸 구조**(법정·분쟁 보류 / 사업상 대사 / 재시도 지원 / 메모리 상주)를 Capital manifest의 `retention_policy` 자리에 채택 방향으로 두되 값은 비움. 배포는 V1에서 loopback(`127.0.0.1`) 전용, TLS 종단은 Capital이 하지 않음(NOT_ADOPTED: 공개 엔드포인트), `public-endpoint-readiness-plan`과 프로그램 결정 §5 해제 뒤 | CAP-15, CAP-20 | `retention-slots-sync`(동기화) |

## 2. KIX 비전과의 연결

읽은 kix-protocol 문서(모두 main `e2a029d`)와, 각 선택이 그 비전에 봉사하는 방식이다.

- **모델 1 — 체인 권위 / 오프체인 위임 실행.** `README.md` §1·§3, `docs/decisions/AUTHORITY_MODEL_1.md`(A-4 기록·재생 분리표), `docs/DEVELOPMENT_PLAN.md` §1·§12. 체인 재고·권리 원권위, 제공자 자금 사실, 오프체인 약정은 서로 다른 사실이다. 그래서 Capital은 권리 권위를 **절대 맡지 않고**(`rights_scale_privacy`), producer tuple이 주는 claim/trade identity만 읽으며, 금융 명령은 관람권·토큰에 손대지 않는다(`CAPITAL-TERMS-V1`의 `never` 목록 유지).
- **Track K 단계(5단계 영속 거래 → 6단계 합성 경제 → 7단계 인증 export).** `docs/DEVELOPMENT_PLAN.md` §5 표·§10·§13, `docs/decisions/PROGRAM_ROADMAP_20260930.md` R-6·R-10·R-11, `docs/decisions/BACKEND_ADOPTION_PROPOSAL_20261009.md` §6·§7, `runtime/AUTHENTICATED_EXPORT.md`. Capital의 StoragePort·ProjectionPort·SignaturePort 목표를 정확히 그 세 단계의 산출물로 고정했다. 자체 저장 엔진·R2·복제·합의는 열지 않는다(프로그램 결정 §5).
- **결정 문서 병합 ≠ ADOPT.** `docs/aiops/CONTRACT_RELEASE_AND_COMPLETION_DESIGN_KO.md` §5.1은 "User 결정 문서가 병합돼 DONE인 것과 권고 기능이 실제 채택된 것은 별개"이고 `none yet`은 DEFERRED·HOLD라고 적는다. `stage5_durable_backend`를 ADOPTED가 아닌 DEFERRED로 둔 이유가 이 규칙이다. 반대로 `ai_agent_grant_action_permit`은 계약 초안 **그리고** 실행 가능한 mock·테스트가 main에 있고 CI가 그 suite를 돌리므로(`validation/2026-10-08-ai-delegation-contract-mock/README.md` Addendum) F04 핀과 같은 등급의 채택이 가능하다.
- **Track P — 계약 전용 OpenAPI·비운영 0.x SDK·분리 앱.** `docs/decisions/PROGRAM_DECISIONS_20260928.md` §2.1, `sdk/README.md`, `sdk/sdk-pin.json`, `sdk/compat/manifests/manifest.bootstrap-1.json`, `docs/contracts/sdk/COMPATIBILITY_MANIFEST_V1.md`, `docs/aiops/FINANCE_COMPLETION_DESIGN_KO.md` §7. "BOOTSTRAP은 카탈로그 스키마 결합만 부여"하므로 producer tuple은 `SEMANTIC_CONFORMANCE`를 기다린다. Capital은 Commerce와 **같은 tuple**을 소비해야 하므로(§7 4항) SDK 언어가 달라도 OpenAPI·manifest 핀은 동일하게 둔다.
- **Finance 설계와 여덟 후보.** `docs/aiops/FINANCE_COMPLETION_DESIGN_KO.md` §§1–10, `docs/aiops/FINANCE_PENDING_NODES.json`, `docs/status/CURRENT_CAPABILITY_REGISTER.md`("Finance는 별도 repo/program이 아니다", "pending 정의를 현재 구현으로 세지 않는다"). Capital은 그 여덟 노드의 **소비자측 참조 구현**으로 자리 잡고, 분모를 줄이거나 노드를 DONE으로 만들지 않는다.
- **RS 규모(1,024 → 16,384 → 65,536)와 페이지 단위 위임.** `docs/decisions/TOKEN_LAYER_AND_RIGHTS_SCALE_SCOPE_20260929.md`, `docs/decisions/RIGHTS_SCALE_RS0_DECISION_20261008.md` §6, `docs/blueprints/rights-scale-v1/README.md` §1·§3.5·§6(위임 최소 단위는 페이지, `GrantControl` 한 곳의 회수 cut). Capital 한도(건당 5억·수익자 20억·포트폴리오 200억, `CAPITAL-TERMS-V1`)와 운영 용량 목표는 65,536석 공연을 전제로 한 포부 값이며, 데모 상한 500 operation은 StoragePort binding 뒤 걷어낸다.
- **TL — 선택적 토큰 계층과 잠금.** `docs/blueprints/optional-native-token-v1/README.md` §3.1(여섯 자산 분리)·§3.2(TK-1~TK-12)·§4.3(U2·U3만 설계 대상)·§7.1(자금 풀), `docs/adr/0002-token-layer-scope-and-limits.md` §4·§5(잠금 경로 불변), `docs/tasks/TASK_005_MEGA_COMMERCE_PROGRAM.md` 결정 5. 담보 엔진을 자산 불문으로 두되 토큰은 보조 담보 후보로만 둔다.
- **AI 위임 경계.** `docs/DEVELOPMENT_PLAN.md` §14, `docs/contracts/AI_DELEGATION_AUTHORITY.md` §3·§5·§8(허용/거부 목록, 항상 거짓 플래그), `docs/contracts/FIRST_BATCH_OPEN_INPUTS.md` I11(AI 자기 위임 확대 금지), `docs/RUNTIME_ARCHITECTURE_S062.md` §10(역사: `executionAuthorized=false`), `docs/PROTOCOL_MASTERPLAN_V2.md` §7·§10(역사: AgentGrant/ActionPermit/DecisionRecord). 모델 출력만으로 발행·지급하지 않는다는 원칙을 Capital AuthorizerPort의 `agent` lane으로 코드화한다.
- **어댑터 정체성·보존 기간·종결.** `docs/contracts/ADAPTER_EVENT_IDENTITY.md` §2·§6.2(송신 전 결합 넷), `docs/decisions/RETENTION_PERIODS_PROPOSAL_20261009.md` §3·§6(R1 네 칸, 값 없음), `docs/contracts/STATE_LIFECYCLE.md` 0.6 LC-TERM/LC-FACT/LC-CUT(참조). Capital의 UNKNOWN fencing·원 receipt 조회·재시도 금지는 그대로이며 보존 값은 주인이 가져온다.
- **역사 문서의 안전 요구.** `docs/BLUEPRINT_20260914.md` §3·§4·§10·§12, `docs/ROADMAP.md`, `docs/RUNTIME_ARCHITECTURE_S062.md`, `docs/COMMERCE_CONTRACTS.md`, `docs/PROTOCOL_MASTERPLAN_V2.md` §13(T01–T09). 모두 "현행 아님"이지만 제작자금과 티켓 결제금 분리, 기준시점·증거 범위 표기, u128 atoms + registry, 통합 수락 시나리오의 확인 항목은 폐기되지 않았다(`CAPITAL_REQUIREMENTS_KO.md` 권위 절과 동일한 읽기).
- **"포부"의 해석.** `PROGRAM_ROADMAP_20260930.md` §0("한 번 시작하면 사람의 결정이 꼭 필요한 곳 말고는 멈추지 않는다")과 JunTae의 2026-10-08 위임. 따라서 열한 항목 모두 방향·목표·계획·차단 조건을 **결정**했고, UNDETERMINED는 벤더·보존 숫자·운영 책임자처럼 외부 답이 필요한 칸에만 이유와 함께 남겼다.

## 3. 항목별 결정

각 항목은 값/방향, 근거, 검토한 대안, 게이트(차단·개방 조건) 순이다.

### 3.1 producer_sdk_tuple (CAP-07, CAP-16) — DEFERRED

- **방향(target).** Capital `ProducerPort`가 묶을 정확한 tuple은 `docs/contracts/sdk/COMPATIBILITY_MANIFEST_V1.md` §2의 manifest-v1 필드 전부다: `producer.{repository, source_commit, source_tree, protocol_domain, contract_schema_version}`, `contract.{contract_only, integration_gate}.{path, gitBlob, sha256}`, `generator.{path, sha256, toolchain=node-24}`, `sdk_output.sha256`, `profile_kind=SEMANTIC_CONFORMANCE`, `profile_revision`, `profile_sha256`, `vectors[]`. `protocol_domain`은 `openapi-catalogue-promotion`이 credit·settlement·booking·resale·admission 명령을 올린 뒤의 후속 도메인(이름은 upstream이 정함)이어야 한다. **결합 방식은 `GATE_HTTP_LOOPBACK`**: Capital은 TypeScript SDK를 내장하지 않고, 같은 contract-only OpenAPI를 핀해 명령 본문을 `additionalProperties:false`·`unknownFields:REJECT`로 검증한 뒤 비운영 loopback 통합 관문(`integration_gate/`)에 `{operationId, actor, action, body}`로 보낸다. `operationId`는 Capital `operation_id`에 1:1, `actor`는 인증이 아니다(sdk/README 5항). Capital의 claim/trade identity(CAP-07)는 같은 tuple의 settlement/booking/resale 명령 결과에서만 읽는다.
- **지금 있는 것(채택 아님).** `sdk/compat/manifests/manifest.bootstrap-1.json`: producer `SUNBURN-Golden/kix-protocol` source_commit `7481b0e1…` tree `8495c765…`, domain `kix:fixture:lifecycle:0.3`, 40개 명령, profile_kind `BOOTSTRAP`, profile_sha256 `4c92cf6d…`, sdk_output sha256 `891ddd65…`. 이 핀은 Capital vendor commit과 같은 커밋이라 **모양 참조**로 쓴다. BOOTSTRAP은 "카탈로그 스키마 결합만" 부여하고 credit 명령이 없으므로 Capital이 묶을 수 없다.
- **근거.** `FINANCE_COMPLETION_DESIGN_KO.md` §7 1~4항(새 tuple마다 새 SDK·manifest·SEMANTIC_CONFORMANCE, 이전 PASS 비전이, Commerce와 동일 producer), `docs/INTEGRATION.md`의 "Upstream adapter replacement prerequisites". Python 소비자가 TS SDK를 내장하면 두 번째 producer가 생기므로 OpenAPI·manifest 핀 수준에서 동일성을 보장하는 쪽이 모델 1의 단일 권위에 맞는다.
- **대안.** (a) TS SDK를 Node subprocess로 호출: 런타임 의존이 늘고 stdlib 원칙 위반이라 기각. (b) Capital 로컬 facade를 그대로 tuple로 승격: `capital-local-facade/1`은 Capital 전용이며 SEMANTIC_CONFORMANCE가 아니므로 기각(SEAMS.md). (c) 지금 BOOTSTRAP에 결합: credit 명령 부재로 불가.
- **게이트.** 개방 조건 = upstream `openapi-catalogue-promotion`(사용자 병합) + `p-sdk-1` + `contract-compatibility-profile`의 SEMANTIC_CONFORMANCE manifest(그 커밋·tree·sha256). 차단 유지 = CAP-07 실여정, CAP-16 exact tuple, `run_producer_vectors` 통과를 적합성으로 읽는 일.

### 3.2 stage5_durable_backend (CAP-11) — DEFERRED

- **방향.** Capital StoragePort의 목표 backend는 upstream이 채택한 것과 **동일**: PostgreSQL 17.11 (Debian 17.11-0+deb13u1), 단일 프로세스·단일 작성자·기본 꺼짐·운영 플래그(`protocolTruth`, `productionConformance`, `productionReadiness`, `productionEndpoint`, FSM `durable`) false, R2·복제·합의 없음(`BACKEND_ADOPTION_PROPOSAL_20261009.md` §6 원문). Capital adapter는 `--storage postgresql://`(unix socket만) 옵트인, 기본은 지금처럼 메모리/`LOCAL_FILE_WORKSPACE`. 저장 단위는 upstream 탐색 adapter와 같은 업무 단위(명령 identity, payload sha256, 최초 결과, 외부 의도 `FIXTURE_NOT_DISPATCHED`, 금액은 u128 십진 문자열)이며 `k-stage5-durable-tx`가 정할 inbox/outbox·count/byte/age 예산·재생 규칙을 **그대로 가져온다**. 자체 내구 엔진·저널 포맷은 만들지 않는다.
- **upstream 영수증(결정의 존재 증명, 채택 증명 아님).** `docs/decisions/BACKEND_ADOPTION_PROPOSAL_20261009.md`, PR #140, 병합 commit `bb193efb5d238581096372c8a20bee1271dfe4df`, merged_by BeautifulMind-JT(`DEVELOPMENT_PLAN.md` §5 「병합된 문서 위치(2026-10-09)」 표).
- **근거.** 같은 제안 §7: "`runtime/crates`에는 오늘 v5 crate가 없다 … v5 구현이 병합되기 전에는 5단계가 그 crate에 기댈 수 없다"; `DEVELOPMENT_PLAN.md` §10 "전부 미착수"; `CONTRACT_RELEASE_AND_COMPLETION_DESIGN_KO.md` §5.1. 묶을 계약이 없는 상태에서 Capital이 먼저 PostgreSQL 스키마를 만들면 upstream stage 5와 어긋난 두 번째 영속 모델이 된다.
- **대안.** FoundationDB(제안 B): upstream이 권고하지 않았고 독립 장애 도메인이 아니라 기각. 지금 psycopg 기반 adapter 선행 구현: stdlib 원칙·upstream 선행 위반이라 기각. 영구 파일 작업공간 유지: 개발용이며 CAP-11이 아님.
- **게이트.** 개방 = `k-stage5-durable-tx` 병합 영수증(commit, 스키마·예산·재생 규칙 문서). 차단 = stage5 내구 거래·inbox/outbox·호스트 간 fencing(CAP-11), `durable=true`.

### 3.3 stage6_finance_candidates (CAP-13, CAP-14) — DEFERRED

- **방향.** 여덟 ID(`fin-ledger-contract`, `fin-double-entry-projection`, `fin-observation-reconciliation`, `fin-multi-payee-refund-proof`, `fin-credit-exposure-reconciliation`, `fin-consistent-accounting-export`, `fin-catalogue-read-model`, `fin-finance-closeout`)의 정의·선행·digest는 `docs/aiops/FINANCE_PENDING_NODES.json`이 정본이다. Capital의 역할은 **소비자측 참조 구현과 벡터 공급**이다. 매핑: `fin-ledger-contract` ← `SIMULATION_FIXED_V1` 계정표와 `CAPITAL-TERMS-V1`의 `SIMULATION_FIXED_V2` 후보(수치·매핑 벡터), `ProjectionPort` 목표 = 그 ADR의 `ProjectionEntry`(원 사건 identity·자산/registry version·source cut·watermark·자산별 debit=credit·reversal 연결); `fin-double-entry-projection` ← `projection.py`의 다섯 보존 술어; `fin-observation-reconciliation` ← `recon.py` 여섯 검사(로컬 진단); `fin-multi-payee-refund-proof` ← `scenarios.py` 9개·35단계(정책 선택 없음); `fin-credit-exposure-reconciliation` ← `statement.py` 다섯 구분과 `/api/preview`; `fin-consistent-accounting-export` ← manifest v2 섹션; `fin-catalogue-read-model` ← `facade-v1.json` 읽기 모양(카탈로그 아님); `fin-finance-closeout` ← `build/acceptance-evidence.json`(소비자 증거 후보). 경제 원천은 `k-stage6-economics-reference`(R-10, 합성 금액)이며 그때 `FixtureViews`를 그 원천 읽기로 바꾼다.
- **근거.** `FINANCE_COMPLETION_DESIGN_KO.md` §2(투영은 재계산 가능한 파생 데이터, 권위 없음)·§3·§8·§9, `FINANCE_PENDING_NODES.json` rule("Candidate nodes cannot be copied unchanged … Promotion requires authoritative completion proof"), `CURRENT_CAPABILITY_REGISTER.md` Finance 절. Capital이 투영을 "채택"하면 그 자체가 두 번째 원장 권위가 되므로 금지된다.
- **대안.** Capital 자체 Finance 계약 작성 후 upstream 제출: 제출은 가능하나 채택은 upstream 영수증뿐이라 상태는 그대로 DEFERRED. 후보 ID를 Capital readiness에서 DONE으로 표시: 금지.
- **게이트.** 개방 = (1) 여덟 후보를 담은 사용자 병합 plan revision, (2) `fin-ledger-contract` 사용자 병합 영수증. 차단 = `accounting_policy=SYNTHETIC_UNADOPTED`, `operating_ledger=NOT_BOUND`, 은행·PG 대사.

### 3.4 stage7_authenticated_export (CAP-15) — DEFERRED

- **방향.** Capital manifest v2(`KIX_CAPITAL_EXPORT_MANIFEST_V2`)를 `runtime/AUTHENTICATED_EXPORT.md` §3의 ExportManifestV1 확장 필드로 **이관**한다: `exportId/exportMode/executionProfile`, `sourceShardCuts[]/consistentCutProofOrDecisionBoundary`, `projectionAppliedSourceWatermarks[]`, `fullSnapshot{isolationLevel, snapshotId, fingerprint, xmin, xmax}` 또는 `incremental{cursorKind, startCursor, endCursor, boundarySemantics}`, `provenance`, `content{rowCount, fileCount, perFileHash[], manifestHash}`. 현재 `NOT_BOUND_FIELDS`(`cursor`, `watermark`, `source_cut`, `external_key`, `retention_policy`, `authentication`) 여섯 자리가 그 필드의 자리다. `SignaturePort`의 목표 구현은 stage 7의 서명·루트·registry 경계 + anti-rollback 정책(§4)이며, 금액은 손실 없는 정수 문자열(`FINANCE` §7). 정규화는 upstream `kix-canonical-json/1`에 맞춘다(현재 `service.digest`는 `ensure_ascii=True`라 비ASCII 처리가 다르다 — adapter 시점에 정렬).
- **근거.** `DEVELOPMENT_PLAN.md` §13("인증된 일관 export부터 구현하고 source cut과 projection watermark를 구분"), 로드맵 R-11(5단계 로컬 원천 위에서만 시작), `FINANCE` §7(stage 7 재사용, 기준시점 다른 보고서를 하나의 닫힌 잔액으로 표시하지 않음).
- **대안.** Capital 자체 Ed25519 서명 도입: stdlib에 없고 "외부 키 없음" 경계를 깨며 stage 7 권위를 선점하므로 기각. HMAC을 인증으로 승격: 금지(DEV_ONLY 유지).
- **게이트.** 개방 = `k-stage7-authenticated-export` 병합 영수증(서명 경계·manifest wire schema 버전). 차단 = `stage7_authenticated_export=false`, 외부 키, 교차 서비스 cursor·watermark.

### 3.5 identity_provider_kyc (CAP-19) — NOT_ADOPTED (V1), 방향 결정

- **방향.** (1) Capital은 **자체 IdP·계정·비밀번호·개인정보 저장소를 두지 않는다.** (2) 인간 principal의 목표 모양은 KIX 표면(통합 관문·Commerce·Capital) 공통의 **OIDC 형태 bearer 토큰**이며, Capital `AuthorizerPort.authenticate`는 토큰의 발급자·대상·만료·`kix_role` 클레임만 검증해 Capital 권한 매트릭스(`command:*`, `*:read`)로 매핑한다. 역할은 organizer/auditor/observer에 `agent`(§3.9)·`capital-desk`(두 번째 승인자)를 더한다. (3) KYC/AML은 Capital이 **계산하지 않는다**: 면허 제공자의 attested fact(`kyc_status`, 검증일, 제공자 참조)를 `U6_KYC_AML_STATUS`(`CAPITAL-TERMS-V1`) 입력으로만 읽고, 실자금 전까지 `kyc_executed=false`를 유지한다. (4) IdP 벤더·KYC 제공자는 **UNDETERMINED — 법무·인허가·JunTae 지정**이다. 이유: 한국 금융 KYC/AML 의무의 주체(대주 법인)와 적용 법령이 `f04-real-funds-lift-criteria`(사용자 노드)로 열려 있어 벤더를 먼저 고르면 결정 순서가 뒤집힌다.
- **근거.** `sdk/README.md`("`actor`를 인증 결과로 믿지 않는다. 인증 구현은 이 문서에 없다"), `AI_DELEGATION_AUTHORITY.md` §1(인간 주체 등록부는 fixture), `FIRST_BATCH_OPEN_INPUTS.md` I11(사람 승인 주체 지정), `BLUEPRINT_20260914.md` §6(역사: `authenticatedActorRef`, 역할 문자열을 인증으로 쓰지 않음), 프로그램 결정 §5(실 KYC 잠금), `docs/INTEGRATION.md` 로컬 인가 경계.
- **대안.** Capital 전용 로그인 구현: 신원 권위가 셋이 되어 기각. 체인 지갑 서명 로그인(zkLogin 등): RS-5·키 관리 결정 뒤의 선택지로 보존, V1 아님.
- **게이트.** 개방 = (a) upstream/Commerce가 공통 인증 경계(`actorContext`)를 계약으로 올릴 때, (b) `f04-real-funds-lift-criteria` 병합으로 KYC 주체가 정해질 때. 차단 = `identity: NOT_BOUND`, `authentication: NOT_BOUND`.

### 3.6 asset_registry_fx (CAP-12) — DEFERRED (registry), NOT_ADOPTED (FX in Capital)

- **방향.** Capital 자산 모델의 목표는 upstream `reference/v0.3-rc1/assets.py`의 `AssetSpec(namespace, reference, decimals ≤ 38, max_atoms ≤ 2^128−1)`에 `RUNTIME_ARCHITECTURE_S062.md` §4·`DEVELOPMENT_PLAN.md` §11의 "u128 atoms + 인증된 asset/registry version"을 더한 것이다. 지금 할 수 있는 것: Capital facade와 projection 계정에 KRW를 `{"namespace":"fiat","reference":"KRW","decimals":0}`로 **명시 선언**하고 금액 필드를 (asset, atoms)로 적는다. FSM `MONEY_MAX 10^12`는 fixture 상한으로 남긴다. 규칙: 자산별 복식 원장, 교차 자산 합산 금지(`ASSET_MISMATCH`), signed 축소 금지. **FX 견적·환전 실행은 Capital 밖**: 다중 자산이 생기면 "자산별 수량·환전 의무·비용·부족분"(T04)을 별도 자산 표시 의무로 적고, 환전은 외부 adapter(또는 `tl-price-source-contract`)가 관측 사실로 공급한다. 스테이블코인은 자산 레지스트리 채택 전까지 fixture다.
- **근거.** `COMMERCE_CONTRACTS.md` 금액·자산 규격(float 금지, "no FX"), 토큰 청사진 §2.2·§5.5, `FINANCE` §3(Wide128 무손실, 교차 자산 netting 금지), `runtime/AUTHENTICATED_EXPORT.md` §5(Fast64/Wide128).
- **대안.** KRW 정수만 영구 고정: 다중 자산 범위 삭제가 되어 기각(개발계획 §1 "삭제하지 않는다"). Capital 내부 환율표: 가격원 계약 없이 권위를 만드는 것이라 기각.
- **게이트.** 개방 = 인증 registry 계약(S062 §4 방향의 upstream 계약 또는 `fin-ledger-contract`의 registry binding). 차단 = 비KRW 자산 수락, FX.

### 3.7 rights_scale_privacy (CAP-17) — DEFERRED, 권위 비채택

- **방향.** Capital은 권리 발행·이전·검표·폐기에 어떤 쓰기도 하지 않고 ZK 노트·nullifier·secret을 보관하지 않는다(NOT_ADOPTED: rights authority, private-note custody). 참조 식별 체계는 `docs/contracts/RIGHTS_SCALE_PROFILE.md` 0.1·RS-0 결정(§6: 독립 객체 분할, 위임 최소 단위 페이지, `GrantControl`)을 따르며 Capital claim identity에는 `(network, package, ShowControl id, page id, slot, generation)`이 producer tuple로 들어올 때만 들어온다. 비공개 경로 티켓과 연결된 정산 청구는 공개 정산 사실만 참조한다(최소 공개). 규모 목표는 RS-4 L3(65,536석·복수 공연 동시)이며, Capital 집중도 한도와 운영 용량은 그 규모로 설계한다.
- **근거.** `TOKEN_LAYER_AND_RIGHTS_SCALE_SCOPE_20260929.md` §2(RS는 핵심 과제), RS-0 결정 §2 조건 (a)~(e), 청사진 §1.2(여섯 상한 구분)·§6 규칙 1~6, `AUTHORITY_MODEL_1.md`.
- **대안.** Capital이 페이지 위임 grant를 담보로 읽기: 관람권·금융권리 분리 위반이라 기각.
- **게이트.** 개방 = RS-1 localnet + producer tuple에 RS 식별자 포함. 차단 = CAP-17 규모 검증·privacy·currentness 주장.

### 3.8 token_layer_coin_lock (CAP-18) — DEFERRED, 세부 NOT_ADOPTED

- **방향.** Capital에는 coin/TIX 모듈·발행·풀·바이백 코드가 **영원히 없다**(TK-9, 잠금 경로는 `tl-coin-lock-adr` 사용자 병합 + Astra 재결정). 담보·준비금 엔진(`CAPITAL-TERMS-V1` `external_collateral_completeness`·`reserve`)은 자산 불문으로 설계해, TL-2 localnet 패키지가 생기고 `tl-price-source-contract`가 토큰↔KRW 평가를 주고 TL-L 검토가 끝난 뒤 **보조 담보**(KRW·스테이블 담보 위 초과 담보)로만 꽂는다. 그때까지 토큰 담보의 haircut은 **100%(신용가치 0)**. U3 보상은 Capital이 지급하지 않으며, 보상 영수 객체(F3)·오프체인 포인트(F4)는 차입기초에 넣지 않는다. NOT_ADOPTED: 토큰 단독 담보(TK-12), 수수료의 토큰 강제(U1), 보유=혜택(U5), 토큰 재무를 준비금 재원으로 쓰는 일(TK-4).
- **근거.** 청사진 §3.1·§3.2·§4.2 U2("wrong-way risk … 단독 담보로 부적합")·§7.1, ADR-0002 §4·§5·§6, 로드맵 R-3·§5(토큰 발행·판매 미승인), `CAPITAL_FINANCIAL_TERMS.md` `collateral_execution.token_collateral=NOT_ACCEPTED_V1`.
- **대안.** TL을 Capital 범위에서 아예 제외: 위임이 "원대한 포부"를 전제하므로 자산 불문 설계로 문을 열어 두는 쪽을 택했다.
- **게이트.** 개방 = `tl-0` 사용자 병합 + TL-2 + `tl-price-source-contract` + TL-L 서면. 차단 = CAP-18 `NOT_AUTHORIZED` 그대로.

### 3.9 ai_agent_grant_action_permit (CAP-19) — ADOPTED (grant·proposal lane), ActionPermit NOT_ADOPTED

- **값.** upstream 계약 `docs/contracts/AI_DELEGATION_AUTHORITY.md` 초안 0.1(이슈 #97, PR #130)과 mock `reference/ai_delegation/ai_delegation_mock.py`, 테스트 `reference/ai_delegation/test_ai_delegation_mock.py`를 kix-protocol main `e2a029d8ac3af7575888dac22fc4bf173ebec232`에서 **바이트 핀 vendor 복사**(`capital/vendor/ai_delegation/`, SHA256은 adapter 노드가 `capital/vendor/manifest.json`에 기록)한다. 매핑: **AgentGrant ↔ 부여 기록**(`grant_id`, `generation`, `issuer`=등록된 인간 주체, `agent_id`, `authority ⊆ {QUERY, PROPOSE}`, `scope.surfaces`, `limits{per_action_max, cumulative_max, count_max, currency=KRW}`, `period{not_before, not_after}`); **ActionPermit ↔ 없음(NOT_ADOPTED)** — EXECUTE는 `EXECUTE_AUTHORITY_DISABLED`/`DELEGATED_EXECUTION_DISABLED`로 거절되고 `HUMAN_APPROVED` 제안은 `effects_executed=false` 메모다. Capital AuthorizerPort에 `agent` principal lane을 추가한다: `agent`는 `call_tool(query_grant|query_subject|propose_action|withdraw_proposal|propose_grant_change)`만 가능, 모든 `command:*`·`session:bind`·export/projection 읽기는 `ROLE_FORBIDDEN`. Capital surfaces는 불투명 식별자 `capital:offer`, `capital:approve`, `capital:draw`, `capital:repay`, `capital:close`, `capital:default`, `capital:reconcile`. 제안 금액 한도는 `CAPITAL-TERMS-V1`에 종속(`per_action_max ≤ 500,000,000`, `cumulative_max ≤ 2,000,000,000` KRW, 5천만 원 초과는 2인 원칙). 인간 organizer가 `HUMAN_APPROVED` 제안을 **자기 명령으로** 실행하며, 영수증에 `proposal_id`와 `role_provenance=AI_DELEGATION_MOCK` 참조를 남긴다. 항상 거짓 플래그(`execution_enabled`, `issued`, `paid`, `signed`, `transferred`, `refund_executed`, `chain_grant_confirmed`, `revocation_cut_confirmed`, `durable`, `legal_authority`)는 그대로다.
- **영수증(실존).** repo `SUNBURN-Golden/kix-protocol`(FINANCE_PENDING·로드맵 문서는 `BeautifulMind-JT/kix-protocol`로 표기, 같은 저장소의 별칭), PR #130(`DEVELOPMENT_PLAN.md` §5 「병합된 문서 위치(2026-10-08)」), 파일이 들어 있는 commit `e2a029d8ac3af7575888dac22fc4bf173ebec232`(이 세션이 읽은 main), 검증 기록 `validation/2026-10-08-ai-delegation-contract-mock/README.md`(22 tests OK; CI 발견 Addendum). 병합 commit SHA 자체는 읽은 문서에 없으므로 adapter 노드가 GitHub에서 확인해 manifest에 적는다.
- **근거.** F04·F01–F03을 같은 방식(계약 초안 + mock 바이트 핀)으로 묶은 Capital 선례, `DEVELOPMENT_PLAN.md` §14, I11, 프로그램 결정 §2.1("AI 위임 권한 계약과 mock … 모델 출력만으로 발행하거나 지급하지 않는다"), `CAPITAL-TERMS-V1`의 `ai_role: PROPOSE_ONLY`와 2인 원칙. 이 lane은 stdlib·loopback·고정 FSM 불변으로 지금 구현 가능하고, 미래 wire 명령·온체인 grant(RS-3a)·Rust 결합(RS-3b)이 생겨도 principal 모델을 다시 설계할 필요가 없다.
- **대안.** DEFERRED로 두고 `ai-delegation-execution-decision`을 기다림: 실행 결정은 EXECUTE에만 관한 것이라 QUERY/PROPOSE lane까지 미룰 이유가 없다. Capital 자체 grant 모델 작성: 두 번째 권한 계약이 되어 기각.
- **게이트.** 차단 = EXECUTE/ActionPermit(`ai-delegation-execution-decision` 사용자 병합 + RS-3a/3b), 실제 IdP·KYC(§3.5), 제품 한도·집계 창(`AI_DELEGATION_AUTHORITY.md` §9 UNDETERMINED · Astra — Capital은 `CAPITAL-TERMS-V1` 값을 **Capital 로컬 상한**으로만 쓴다). 초안 0.1이 바뀌면 바이트 핀이 보호하고 재핀은 별도 노드다.

### 3.10 t01_t06_qualification (CAP-20) — DEFERRED

- **방향.** `PROTOCOL_MASTERPLAN_V2.md` §13(역사 문서)의 T01 묶음·할인, T02 여러 결제, T03 공개/비공개 리셀, T04 다중 자산, T05 금융 연계, T06 복구·AI를 Capital 사다리로 매핑한다. **Q0** 로컬 수용 사다리(`scripts/acceptance.py`, 존재) · **Q1** facade 계약·producer 벡터(존재) · **Q2** producer tuple SEMANTIC_CONFORMANCE(§3.1 뒤) · **Q3** T05+T06 통합 합성 여정(Protocol 관문 + Commerce 화면 + Capital, 정산채권 일부 배정·자금 공급·상환 중 공연 취소·호출 전/후 종료·늦은 지급·AI 제안) · **Q4** 사용자 제품 수용(JunTae, PENDING) · **Q5** 서비스/host qualification(Q0~Q4 + 실환경 unlock). 소유: T05·T06은 Capital, T01·T02·T03은 Protocol/Commerce producer, T04는 §3.6 뒤. 지금 할 수 있는 것은 T05/T06의 **합성 변형**을 Q0에 이름 붙여 넣는 일(`T05-sim`, `T06-sim`)이며 통합 완료로 세지 않는다.
- **근거.** 같은 §13("비공개·금융·AI도 단독 모형 성공만으로 통합 완료로 세지 않는다"), `CAPITAL_REQUIREMENTS_KO.md` CAP-20(사용자 수용 PENDING), `docs/VALIDATION.md` Acceptance ladder("사람 수용 결정은 포함하지 않는다").
- **대안.** T01–T06 전부 Capital에서 흉내: producer 산술 복제 금지(Commerce 규칙)라 기각.
- **게이트.** 개방 = Q2 tuple + Commerce `w6a-evidence`·`bind-credit-fsm` 영수증 + host qualification 경로. 차단 = CAP-20 통합 수용·출시.

### 3.11 deployment_tls_retention (CAP-15, CAP-20) — DEFERRED, 배포 V1 NOT_ADOPTED

- **방향.** **배포:** V1은 `127.0.0.1` loopback 전용, 외부 Host/Origin 거절 유지, Capital 프로세스는 TLS를 종단하지 않는다. 공개 엔드포인트·TLS·DNS는 `public-endpoint-readiness-plan`(문서)과 프로그램 결정 §5(인증·TLS·운영 책임자·장애 대응·사용자 승인) 뒤 운영 책임자 소유의 ingress/reverse proxy에서만 한다(책임자 **UNDETERMINED — JunTae 지정**). 아티팩트는 `LOCAL_SIMULATION_ARTIFACT`·`signed:false`·`published:false` 그대로. **보존:** upstream R1의 네 칸을 Capital manifest `retention_policy` 자리에 **구조로** 둔다 — `legal_dispute_hold`(주인 법무/개인정보, `UNDETERMINED`), `business_reconciliation`(주인 토스 계약/기술, `UNDETERMINED`), `retry_support`(주인 Astra, `DECISION_REQUIRED`), `memory_residency{count, bytes, age}`(주인 Astra, `DECISION_REQUIRED`). 규칙: 법정·분쟁 보류 참조가 열려 있으면 다른 세 칸이 삭제를 허락하지 않는다; 메모리에서 빠진 결과는 권위가 아니다; 제공자 공개값(15일 등)을 기간으로 쓰지 않는다. Capital의 `MAX_OPERATIONS 500`은 데모 `memory_residency.count` 상한이지 보존 값이 아니다. 세무·회계 보존 담당은 질문서에 없으므로 JunTae가 지명한다.
- **upstream 영수증(구조의 존재 증명).** `docs/decisions/RETENTION_PERIODS_PROPOSAL_20261009.md`, PR #139, 병합 commit `6e54e723d582e88ae89df309eb144d4664c7e1f5`(R1만 채택, 값은 멈춘 채).
- **근거.** 같은 제안 §3·§6, `DEVELOPMENT_PLAN.md` §6.3, `READINESS_RUNTIME.md` 통합 관문 절(기본 `127.0.0.1`, `0.0.0.0` 거절)·보류 절(TLS 제품화 보류), 로드맵 §5(공개 운영 엔드포인트 행).
- **대안.** Capital 내장 TLS(`ssl` stdlib): 키·인증서 보관 권한이 생겨 "키·시크릿 미승인"(ADR-0002 §4 5항) 경계를 넘으므로 기각. 단일 보존 기간: R2 갈래, upstream이 기각.
- **게이트.** 개방 = `k-stage5-durable-tx`(보존 값을 실제로 적용할 저장), 법무/토스/Astra 회신. 차단 = 공개 배포, TLS 종단, 보존 숫자.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "upstream-binding-decision",
  "decided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
  "date": "2026-10-09",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "scope": "KIX-CAPITAL simulation and product design only; not an offer; no real money; production NOT_AUTHORIZED; legal, tax, accounting and licensing content are working assumptions pending professional review; no upstream contract is claimed adopted without a real upstream receipt",
  "delegation": "2026-10-08 18:25 KST JunTae Park delegated financial terms, settlement policy, upstream binding and accounts/tax/legal to Fable with the instruction to proceed with the grand ambition in mind",
  "status_vocabulary": {
    "ADOPTED": "a real upstream artifact (receipt field) is bound as Capital's target now; an adapter node may open",
    "DEFERRED": "target binding decided; the upstream artifact Capital will bind to does not exist yet or is not bindable; adapter node opens on the named receipt",
    "NOT_ADOPTED": "Capital decides not to bind this item in the requested form in V1 and records the alternative direction"
  },
  "bases": {
    "capital_main": "0514789",
    "kix_protocol_main": "e2a029d8ac3af7575888dac22fc4bf173ebec232",
    "kix_commerce_apps_main_as_recorded": "7c2452645c50b8ede17bdd762794adeabe42319e (from docs/CAPITAL_REQUIREMENTS_KO.md; not re-read in this session)",
    "vendor_pin_commit": "7481b0e16ce9b903abbffa62249bb91cd9e63cfe",
    "prior_capital_decision": "docs/decisions/CAPITAL_FINANCIAL_TERMS.md (CAPITAL-TERMS-V1, 2026-10-08)",
    "finance_pending_source_of_truth": "kix-protocol docs/aiops/FINANCE_PENDING_NODES.json (schema_version 1, status PENDING_NOT_IN_PLAN)"
  },
  "upstream_receipts_found": {
    "backend_adoption": {"repo": "SUNBURN-Golden/kix-protocol", "pr": 140, "merge_commit": "bb193efb5d238581096372c8a20bee1271dfe4df", "path": "docs/decisions/BACKEND_ADOPTION_PROPOSAL_20261009.md", "adopts": "PostgreSQL 17.11 (Debian 17.11-0+deb13u1) for stage-5 local non-production scope only"},
    "retention_structure": {"repo": "SUNBURN-Golden/kix-protocol", "pr": 139, "merge_commit": "6e54e723d582e88ae89df309eb144d4664c7e1f5", "path": "docs/decisions/RETENTION_PERIODS_PROPOSAL_20261009.md", "adopts": "R1 four separate retention slots with owners; no durations"},
    "v5_crate_design": {"repo": "SUNBURN-Golden/kix-protocol", "pr": 138, "merge_commit": "a483ab1777ad0c3e15ff71798822cbf6b3666f83", "path": "docs/decisions/STAGE2_V5_CRATE_DESIGN_DECISION_20261008.md", "adopts": "option O1; implementation node k-stage2-v5-impl not merged"},
    "integration_a": {"repo": "SUNBURN-Golden/kix-protocol", "pr": 142, "merge_commit": "b6cc9978c64b1ff54f822ea930424b5d78dfca2a", "path": "docs/decisions/INTEGRATION_A_DECISION_PROPOSAL_20261009.md", "adopts": "option B: integration (a) DEFERRED"},
    "ai_delegation_contract_mock": {"repo": "SUNBURN-Golden/kix-protocol", "pr": 130, "containing_commit": "e2a029d8ac3af7575888dac22fc4bf173ebec232", "merge_commit": "NOT_RECORDED_IN_DOCS_READ; adapter node records it from GitHub", "paths": ["docs/contracts/AI_DELEGATION_AUTHORITY.md", "reference/ai_delegation/ai_delegation_mock.py", "reference/ai_delegation/test_ai_delegation_mock.py", "validation/2026-10-08-ai-delegation-contract-mock/README.md"]},
    "sdk_bootstrap_manifest": {"repo": "SUNBURN-Golden/kix-protocol", "path": "sdk/compat/manifests/manifest.bootstrap-1.json", "producer_source_commit": "7481b0e16ce9b903abbffa62249bb91cd9e63cfe", "profile_kind": "BOOTSTRAP", "profile_revision": "bootstrap-1", "profile_sha256": "4c92cf6d905f83fb3f5cd52e166dbadf057451ae46441fce1f91baaaa4367d34", "note": "shape reference only; BOOTSTRAP grants catalogue-schema binding only and the 40-command catalogue has no credit or settlement commands"},
    "rs0_profile": {"repo": "SUNBURN-Golden/kix-protocol", "pr": 125, "paths": ["docs/contracts/RIGHTS_SCALE_PROFILE.md", "docs/decisions/RIGHTS_SCALE_RS0_DECISION_20261008.md"], "note": "contract draft 0.1; identifier scheme reference only"},
    "tl_a_adr": {"repo": "SUNBURN-Golden/kix-protocol", "pr": 126, "path": "docs/adr/0002-token-layer-scope-and-limits.md", "note": "scope and limits; coin/TIX lock unchanged"}
  },
  "entries": {
    "producer_sdk_tuple": {
      "status": "DEFERRED",
      "value": null,
      "target": {
        "binding_mode": "GATE_HTTP_LOOPBACK",
        "tuple_shape": "kix-compat-manifest/1: producer{repository, source_commit, source_tree, protocol_domain, contract_schema_version}, contract{contract_only, integration_gate}{path, gitBlob, sha256}, generator{path, sha256, toolchain=node-24}, sdk_output{path, sha256}, profile_kind=SEMANTIC_CONFORMANCE, profile_revision, profile_sha256, vectors[]",
        "required_catalogue": "post openapi-catalogue-promotion domain including credit (F04), settlement (F01-F03), booking, resale and admission commands; name decided upstream",
        "capital_consumption": "pin the same contract-only OpenAPI and manifest as Commerce; validate bodies additionalProperties=false unknownFields=REJECT; POST {operationId, actor, action, body} to the non-production loopback integration gate; operationId == Capital operation_id; actor is not authentication; no client arithmetic; UNKNOWN ownership unchanged",
        "shared_with": "kix-commerce-apps bind-credit-fsm / bind-settlement-fsm must consume the identical tuple",
        "local_gateway_check": "tests/test_producer_port.py run_producer_vectors must still pass; passing is not SEMANTIC_CONFORMANCE"
      },
      "plan": "open producer-port-catalogue-adapter when openapi-catalogue-promotion (user merge), p-sdk-1 and contract-compatibility-profile publish a SEMANTIC_CONFORMANCE manifest for that catalogue; record producer.source_commit, source_tree, both OpenAPI sha256 and profile_sha256 in capital/vendor/manifest.json",
      "blocked": ["CAP-07 live order/resale/admission journey", "CAP-16 exact producer/SDK/manifest/profile tuple", "any mapping of similar catalogue names onto settle_capture or offer_gift"],
      "interim_reference": "sdk/compat/manifests/manifest.bootstrap-1.json at 7481b0e1 (BOOTSTRAP, not an adoption)",
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-09",
      "cap_rows": ["CAP-07", "CAP-16"],
      "rationale": "Only a BOOTSTRAP manifest for the 40-command fixture catalogue exists upstream and it has no credit or settlement commands; Capital must consume the same promoted tuple as Commerce, so the binding waits for SEMANTIC_CONFORMANCE and binds at the OpenAPI and manifest pin level rather than embedding the TypeScript SDK.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "consumer": "ProducerPort / producer-binding readiness group"
    },
    "stage5_durable_backend": {
      "status": "DEFERRED",
      "value": null,
      "target": {
        "backend": "PostgreSQL 17.11 (Debian 17.11-0+deb13u1), identical to upstream PR #140 section 6",
        "scope": "single process, single writer, default off, operational flags protocolTruth/productionConformance/productionReadiness/productionEndpoint false, FSM durable false, no R2, no replication, no consensus",
        "capital_adapter": "opt-in StoragePort --storage postgresql:// over a unix socket only; default remains MEMORY or LOCAL_FILE_WORKSPACE; driver is an optional extra never required by the stdlib default",
        "unit_of_record": "command identity, payload sha256, first result, external intent FIXTURE_NOT_DISPATCHED, u128 amounts as decimal strings, count/byte/age budgets and replay rules exactly as k-stage5-durable-tx defines them",
        "never": ["own durability engine or journal format", "cross-host fencing claims", "durable=true before the upstream contract"]
      },
      "plan": "open storage-port-postgres-adapter when k-stage5-durable-tx merges (its schema, inbox/outbox and budget rules are the contract); k-stage2-v5-impl is its upstream prerequisite",
      "blocked": ["CAP-11 durable transactions, inbox/outbox, failure recovery", "durable label other than false or LOCAL_FILE_WORKSPACE"],
      "upstream_receipt": "PR #140 bb193efb5d238581096372c8a20bee1271dfe4df (backend decision only; per CONTRACT_RELEASE_AND_COMPLETION_DESIGN_KO.md section 5.1 a decision-document merge is not an adoption of descendants)",
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-09",
      "cap_rows": ["CAP-11"],
      "rationale": "The backend is chosen upstream and Capital adopts the same choice as its target, but the durable-transaction contract Capital would bind to has not started (BACKEND_ADOPTION_PROPOSAL section 7: no v5 crate; DEVELOPMENT_PLAN section 10: not started), so binding stays deferred rather than inventing a second persistence model.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "consumer": "StoragePort / durable-finance readiness group"
    },
    "stage6_finance_candidates": {
      "status": "DEFERRED",
      "value": null,
      "candidate_ids": ["fin-ledger-contract", "fin-double-entry-projection", "fin-observation-reconciliation", "fin-multi-payee-refund-proof", "fin-credit-exposure-reconciliation", "fin-consistent-accounting-export", "fin-catalogue-read-model", "fin-finance-closeout"],
      "target": {
        "capital_role": "consumer-side reference implementation and vector supplier; no second ledger authority",
        "projection_port_target": "fin-ledger-contract ProjectionEntry: source event/operation/order/claim/advance identity, per-asset atoms with registry version, source cut and projection watermark, per-asset debit equals credit, explicit reversal/replacement linkage, duplicate/gap/UNKNOWN states",
        "economic_source": "k-stage6-economics-reference synthetic events replace FixtureViews when adopted",
        "artifact_map": {
          "fin-ledger-contract": "SIMULATION_FIXED_V1 chart and the SIMULATION_FIXED_V2 candidate from CAPITAL-TERMS-V1 as numeric and mapping vectors",
          "fin-double-entry-projection": "capital/projection.py five conservation predicates",
          "fin-observation-reconciliation": "capital/recon.py six checks (local diagnostics only)",
          "fin-multi-payee-refund-proof": "capital/scenarios.py nine scenarios, 35 steps, no policy chosen",
          "fin-credit-exposure-reconciliation": "capital/statement.py five categories and /api/preview",
          "fin-consistent-accounting-export": "capital/export.py manifest v2 sections",
          "fin-catalogue-read-model": "capital/contract/facade-v1.json read shapes (not a catalogue)",
          "fin-finance-closeout": "build/acceptance-evidence.json as consumer-side evidence candidate"
        }
      },
      "plan": "open projection-port-ledger-contract-adapter when (1) a user-merged plan revision carries the eight candidates and (2) fin-ledger-contract is user-merged; Capital never marks any candidate DONE and never reduces the denominator",
      "blocked": ["CAP-13 adopted double-entry (accounting_policy SYNTHETIC_UNADOPTED, operating_ledger NOT_BOUND)", "CAP-14 bank/PG/provider reconciliation and authenticated completeness"],
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-09",
      "cap_rows": ["CAP-13", "CAP-14"],
      "rationale": "The eight nodes are PENDING_NOT_IN_PLAN upstream and FINANCE_COMPLETION_DESIGN_KO.md section 2 makes finance projection derived data without authority; Capital's local artifacts are the natural vector inputs and its ProjectionPort will map onto the ledger contract once it exists.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "consumer": "ProjectionPort / durable-finance readiness group"
    },
    "stage7_authenticated_export": {
      "status": "DEFERRED",
      "value": null,
      "target": {
        "manifest_fields": "runtime/AUTHENTICATED_EXPORT.md section 3: exportId/exportMode/executionProfile, sourceClusterId/authorityScope/authorityPlacementVersion, sourceShardCuts[]/consistentCutProofOrDecisionBoundary, sourceSchemaVersion/kernelSemanticsVersions/exportSchemaVersion, projectionAppliedSourceWatermarks[], fullSnapshot{isolationLevel, snapshotId, fingerprint, xmin, xmax} or incremental{cursorKind, startCursor, endCursor, boundarySemantics}, provenance, content{rowCount, fileCount, perFileHash[], manifestHash, partitionManifest}",
        "capital_slots": "cursor, watermark, source_cut, external_key, retention_policy, authentication in KIX_CAPITAL_EXPORT_MANIFEST_V2 are the landing fields",
        "signature_port_target": "stage-7 signing/root/registry boundary with anti-rollback policy (section 4); DevHmacSigner stays DEV_ONLY integrity until then",
        "canonicalization": "align Capital digests to kix-canonical-json/1 at adapter time (service.digest currently uses ensure_ascii=True)",
        "amounts": "lossless integer strings with asset profile"
      },
      "plan": "open signature-port-stage7-adapter when k-stage7-authenticated-export merges; migrate manifest v2 to the registered wire schema version without reinterpreting the same canonical identity",
      "blocked": ["CAP-15 stage7_authenticated_export stays false", "external key", "cross-service cursor and watermark", "multi-shard global atomic claims"],
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-09",
      "cap_rows": ["CAP-15"],
      "rationale": "Stage 7 starts only on the stage-5 local source (roadmap R-11) and the export contract exists only as architecture v5; Capital pre-shapes its manifest to those fields so adoption is a field mapping, not a redesign.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "consumer": "SignaturePort / durable-finance readiness group"
    },
    "identity_provider_kyc": {
      "status": "NOT_ADOPTED",
      "value": null,
      "target": {
        "capital_owned_idp": "NEVER (no accounts, passwords, personal data or credential store in Capital)",
        "human_principal_shape": "OIDC-style bearer token shared across KIX surfaces (gate, Commerce, Capital); AuthorizerPort.authenticate verifies issuer, audience, expiry and a kix_role claim and maps it to the Capital permission matrix",
        "roles_v2": ["organizer", "auditor", "observer", "agent", "capital-desk"],
        "kyc_aml": "attested fact from a licensed provider (status, verified_at, provider_ref) consumed by CAPITAL-TERMS-V1 check U6; never computed in Capital; kyc_executed stays false until real funds",
        "vendor": "UNDETERMINED - legal/licensing review and JunTae designation; reason: the lending entity and applicable KYC/AML duty are decided by f04-real-funds-lift-criteria, so choosing a vendor first inverts the decision order"
      },
      "plan": "no adapter node now; synthetic loopback roles remain V1; open an authorizer adapter only after (a) an upstream shared authentication boundary contract (actorContext) exists and (b) f04-real-funds-lift-criteria names the KYC subject",
      "blocked": ["identity NOT_BOUND", "authentication NOT_BOUND", "real KYC/AML calls (program decision section 5 lock)"],
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-09",
      "cap_rows": ["CAP-19"],
      "rationale": "No upstream identity contract exists and real KYC is locked; the decided shape (shared OIDC-style boundary, attested KYC facts, no Capital-owned identity) lets the later adapter replace LocalRoleAuthorizer without touching command semantics.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "review_owner": "legal and compliance counsel designated by JunTae; questions via f04-real-funds-lift-criteria",
      "consumer": "AuthorizerPort / assets-and-rights readiness group"
    },
    "asset_registry_fx": {
      "status": "DEFERRED",
      "value": null,
      "target": {
        "asset_model": "AssetSpec(namespace, reference, decimals<=38, max_atoms<=2^128-1) per reference/v0.3-rc1/assets.py plus authenticated asset/registry version per RUNTIME_ARCHITECTURE_S062 section 4 and DEVELOPMENT_PLAN section 11",
        "krw_profile_declared_now": {"namespace": "fiat", "reference": "KRW", "decimals": 0, "fixture_money_max": "1000000000000 (pinned FSM MONEY_MAX, a fixture bound not a registry limit)"},
        "rules": ["one ledger per asset", "no cross-asset netting or summation (ASSET_MISMATCH)", "no signed truncation of u128", "amounts carried as (asset, atoms)"],
        "fx": "NOT_ADOPTED inside Capital: no quote, no execution; foreign-asset obligations are recorded as separate asset-denominated obligations (T04: per-asset quantity, conversion obligation, cost, shortfall) and conversion facts come from an external adapter or tl-price-source-contract"
      },
      "plan": "asset-spec-declaration sync node (no adapter): declare the KRW AssetSpec in facade-v1.json and projection account keys; open a registry adapter when an authenticated registry contract exists upstream (fin-ledger-contract registry binding or a stage-6 asset registry contract)",
      "blocked": ["CAP-12 non-KRW assets", "FX quote/execution", "stablecoin beyond fixture"],
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-09",
      "cap_rows": ["CAP-12"],
      "rationale": "The upstream asset model is explicit (AssetSpec, no FX, u128 atoms) while an authenticated registry is not; declaring KRW in that shape now makes multi-asset a registry binding later and keeps FX authority outside Capital.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "consumer": "ProjectionPort, ProducerPort / assets-and-rights readiness group"
    },
    "rights_scale_privacy": {
      "status": "DEFERRED",
      "value": null,
      "target": {
        "rights_authority": "NOT_ADOPTED: Capital never writes issue/transfer/admission/revoke and never holds ZK notes, nullifiers or secrets",
        "identifier_scheme": "RIGHTS_SCALE_PROFILE 0.1 / RS-0 decision: (network, package, ShowControl id, page id, slot, generation); enters Capital claim identity only through the producer tuple",
        "privacy": "claims tied to private-path tickets reference public settlement facts only (minimum disclosure)",
        "scale_assumption": "RS-4 L3: 65,536 slots, concurrent shows; Capital caps and operational capacity are sized for it; the 500-operation demo bound is lifted after StoragePort binds"
      },
      "plan": "no separate adapter; the producer-port-catalogue-adapter carries RS identifiers when RS-1 localnet and the promoted catalogue expose them",
      "blocked": ["CAP-17 scale validation, privacy and currentness claims", "page-level grants as collateral"],
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-09",
      "cap_rows": ["CAP-17"],
      "rationale": "Model 1 keeps rights authority on chain; Capital's ambition is served by sizing for the RS-4 scale and referencing the RS-0 identifier scheme, not by touching rights.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "consumer": "ProducerPort / assets-and-rights readiness group"
    },
    "token_layer_coin_lock": {
      "status": "DEFERRED",
      "value": null,
      "target": {
        "coin_module_in_capital": "NEVER (TK-9; coin/TIX lock path: tl-coin-lock-adr user merge plus Astra re-ruling)",
        "collateral_engine": "asset-agnostic via AssetSpec so a TL asset can be a supplementary collateral after TL-2 localnet, tl-price-source-contract and TL-L; haircut 100 percent (zero credit value) until a price source exists",
        "not_adopted": ["token as sole collateral (TK-12)", "fees payable in token (U1)", "hold equals benefit (U5)", "token treasury as reserve funding (TK-4)", "Capital-paid rewards (U3 belongs to TL)"],
        "rewards_in_borrowing_base": "F3 receipt objects and F4 off-chain points are never part of eligible_face"
      },
      "plan": "revisit when tl-0 is user-merged, TL-2 exists on localnet, tl-price-source-contract is adopted and TL-L written review is received; consistent with CAPITAL-TERMS-V1 collateral_execution.token_collateral NOT_ACCEPTED_V1",
      "blocked": ["CAP-18 NOT_AUTHORIZED", "any token-denominated limit extension of the KRW mock"],
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-09",
      "cap_rows": ["CAP-18"],
      "rationale": "ADR-0002 keeps the coin/TIX lock and the blueprint rejects wrong-way-risk sole collateral; designing the collateral engine asset-agnostic preserves the ambition without opening the lock.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "review_items": ["legal character of token collateral and slashing (TL-L)", "chargeback window for transferable rewards"],
      "consumer": "TermsPolicyPort / assets-and-rights readiness group"
    },
    "ai_agent_grant_action_permit": {
      "status": "ADOPTED",
      "value": {
        "adopted_scope": "AGENT_GRANT_QUERY_PROPOSE_LANE",
        "upstream_contract": "docs/contracts/AI_DELEGATION_AUTHORITY.md draft 0.1 (issue #97)",
        "upstream_mock": "reference/ai_delegation/ai_delegation_mock.py",
        "upstream_tests": "reference/ai_delegation/test_ai_delegation_mock.py",
        "pin_commit": "e2a029d8ac3af7575888dac22fc4bf173ebec232",
        "pin_mode": "byte-pinned vendor copy under capital/vendor/ai_delegation/ exactly like capital/vendor/credit_advance_f04; sha256 of each file recorded in capital/vendor/manifest.json by the adapter node",
        "agent_grant_mapping": "grant record: grant_id, generation, issuer (registered human principal), agent_id, authority subset of {QUERY, PROPOSE}, scope.surfaces (+ optional subjects), limits {per_action_max, cumulative_max, count_max, currency=KRW}, period {not_before, not_after}; one ACTIVE grant per (issuer, agent_id); revocation voids pending proposals and keeps history",
        "action_permit": "NOT_ADOPTED: no upstream permit exists; EXECUTE is refused (EXECUTE_AUTHORITY_DISABLED, DELEGATED_EXECUTION_DISABLED); HUMAN_APPROVED proposal is a memo with effects_executed=false",
        "capital_surfaces": ["capital:offer", "capital:approve", "capital:draw", "capital:repay", "capital:close", "capital:default", "capital:reconcile"],
        "authorizer_rule": "principal role agent may only call_tool(query_grant, query_subject, propose_action, withdraw_proposal, propose_grant_change); every command:*, session:bind, export/projection/statement/reconciliation read is ROLE_FORBIDDEN for agent; a human organizer executes a HUMAN_APPROVED proposal by issuing the command; receipts carry proposal_id and role_provenance AI_DELEGATION_MOCK",
        "limits_binding": "grant limits are Capital-local upper bounds: per_action_max <= 500000000 KRW, cumulative_max <= 2000000000 KRW (CAPITAL-TERMS-V1 caps); two-person rule above 50000000 KRW; product limits and aggregation windows remain UNDETERMINED upstream (contract section 9)",
        "flags_always_false": ["execution_enabled", "funds_executed", "issued", "paid", "signed", "transferred", "refund_executed", "chain_grant_confirmed", "revocation_cut_confirmed", "durable", "legal_authority"]
      },
      "receipt": {
        "repo": "SUNBURN-Golden/kix-protocol (alias BeautifulMind-JT/kix-protocol in roadmap and FINANCE_PENDING_NODES.json)",
        "pr": 130,
        "containing_commit": "e2a029d8ac3af7575888dac22fc4bf173ebec232",
        "merge_commit": "NOT_RECORDED_IN_DOCS_READ; the adapter node records the merge SHA from GitHub before pinning",
        "paths": ["docs/contracts/AI_DELEGATION_AUTHORITY.md", "reference/ai_delegation/ai_delegation_mock.py", "reference/ai_delegation/test_ai_delegation_mock.py", "validation/2026-10-08-ai-delegation-contract-mock/README.md"],
        "merge_boundary": "docs/aiops/PROGRAM_ASTRA_DELEGATION.md row ai-delegation-contract-mock: contract_change YES, user merge, A3"
      },
      "plan": "open agent-grant-authorizer-adapter now: vendor-pin the two files plus test, add the agent lane to AuthorizerPort, update docs/SEAMS.md AuthorizerPort row to PARTIAL (agent lane ADOPTED with this receipt; identity NOT_BOUND) and the seam test lock accordingly, update readiness CAP-19 to SIMULATED for AgentGrant semantics while IdP/KYC stay NOT_BOUND",
      "blocked": ["ActionPermit / EXECUTE (ai-delegation-execution-decision user merge; RS-3a, RS-3b)", "real IdP and KYC (see identity_provider_kyc)", "wire command, on-chain grant, durable grant ledger"],
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-09",
      "cap_rows": ["CAP-19"],
      "rationale": "The contract draft and an executable mock with tests exist on main and CI discovers the suite, which is the same grade of artifact Capital already pinned for F04; binding the QUERY/PROPOSE lane now puts the AI layer into Capital's authorization seam without enabling execution, consistent with DEVELOPMENT_PLAN section 14 and I11.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "consumer": "AuthorizerPort / assets-and-rights readiness group"
    },
    "t01_t06_qualification": {
      "status": "DEFERRED",
      "value": null,
      "target": {
        "source": "PROTOCOL_MASTERPLAN_V2.md section 13 (historical; acceptance requirements retained)",
        "ladder": {
          "Q0": "local acceptance ladder scripts/acceptance.py (exists)",
          "Q1": "facade contract capital-local-facade/1 and producer vectors (exists)",
          "Q2": "producer tuple SEMANTIC_CONFORMANCE (after producer_sdk_tuple)",
          "Q3": "integrated synthetic journey T05 plus T06 across Protocol gate, Commerce surfaces and Capital",
          "Q4": "user product acceptance by JunTae (PENDING)",
          "Q5": "service and host qualification (Q0-Q4 plus real-environment unlocks)"
        },
        "ownership": {"T05_finance_link": "Capital", "T06_recovery_ai": "Capital (UNKNOWN fencing, AI propose-only)", "T01_T02_T03": "Protocol/Commerce producer", "T04_multi_asset": "after asset_registry_fx"},
        "now": "name the existing synthetic variants T05-sim and T06-sim inside Q0; they are not integrated acceptance"
      },
      "plan": "extend scripts/acceptance.py with the T05-sim/T06-sim labels (sync, no adapter); Q3 opens after Q2 plus Commerce w6a-evidence and bind-credit-fsm receipts; Q5 follows the host qualification path",
      "blocked": ["CAP-20 integrated acceptance and release", "full T01 to T06 combined transaction"],
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-09",
      "cap_rows": ["CAP-20"],
      "rationale": "The masterplan forbids counting isolated mock success as integrated completion; mapping T01-T06 onto a Capital ladder makes the remaining steps explicit and keeps Capital from replicating producer arithmetic.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "consumer": "release readiness group / scripts/acceptance.py"
    },
    "deployment_tls_retention": {
      "status": "DEFERRED",
      "value": null,
      "target": {
        "deployment_v1": "loopback 127.0.0.1 only; external Host/Origin refused; artifact LOCAL_SIMULATION_ARTIFACT signed=false published=false",
        "tls": "NOT_ADOPTED in Capital: the process never terminates TLS; a public endpoint, TLS and DNS belong to an operator-owned ingress after public-endpoint-readiness-plan and program decision section 5 unlock; operator UNDETERMINED - JunTae designation",
        "retention_structure": {
          "source": "RETENTION_PERIODS_PROPOSAL_20261009.md R1 (PR #139, 6e54e723)",
          "slots": {
            "legal_dispute_hold": {"owner": "legal/privacy counsel", "value": "UNDETERMINED"},
            "business_reconciliation": {"owner": "Toss contract/technical", "value": "UNDETERMINED"},
            "retry_support": {"owner": "Astra", "value": "DECISION_REQUIRED"},
            "memory_residency": {"owner": "Astra", "value": {"count": "DECISION_REQUIRED", "bytes": "DECISION_REQUIRED", "age": "DECISION_REQUIRED"}}
          },
          "rules": ["an open legal/dispute hold blocks deletion regardless of the other three slots", "cache eviction is not disposal of the authoritative duplicate-prevention record", "provider public values (e.g. 15-day idempotency key) are never used as retention values", "MAX_OPERATIONS 500 is a demo memory_residency.count bound, not a retention value"],
          "tax_accounting_retention_owner": "UNDETERMINED - not in the upstream question sheet; JunTae designates"
        }
      },
      "plan": "retention-slots-sync node (docs/readiness, no adapter): replace retention_policy NOT_BOUND with the four named empty slots and owners; apply values only through k-stage5-durable-tx storage after owners answer",
      "blocked": ["public deployment", "TLS termination", "retention durations", "CAP-20 release"],
      "upstream_receipt": "PR #139 6e54e723d582e88ae89df309eb144d4664c7e1f5 (structure only; values remain stopped)",
      "provided_by": "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08",
      "date": "2026-10-09",
      "cap_rows": ["CAP-15", "CAP-20"],
      "rationale": "Upstream adopted the four-slot retention structure without values; Capital mirrors that structure so later values are a fill-in, and keeps deployment loopback-only because public endpoints, TLS and key custody are locked by program decision section 5 and ADR-0002 section 4.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "review_owner": "legal/privacy counsel and operations owner designated by JunTae",
      "consumer": "SignaturePort retention slot, release readiness group"
    }
  },
  "port_map": {
    "StoragePort": {"local": "InMemoryStorage and opt-in FileWorkspace (capital/store.py)", "expected_upstream_contract": "k-stage5-durable-tx on the user-adopted PostgreSQL 17.11 local non-production backend (PR #140)", "status": "DEFERRED", "receipt": "NONE for the contract; backend decision receipt bb193efb"},
    "ProjectionPort": {"local": "SimulationProjection SIMULATION_FIXED_V1 (capital/projection.py)", "expected_upstream_contract": "fin-ledger-contract ProjectionEntry over k-stage6-economics-reference events", "status": "DEFERRED", "receipt": "NONE"},
    "AuthorizerPort": {"local": "LocalRoleAuthorizer (capital/auth.py)", "expected_upstream_contract": "shared OIDC-style authentication boundary (actorContext) for humans; AI_DELEGATION_AUTHORITY grant/proposal lane for agents", "status": "PARTIAL: agent lane ADOPTED (receipt PR #130 at e2a029d), identity and KYC NOT_BOUND", "receipt": "ai_delegation_contract_mock receipt above"},
    "SignaturePort": {"local": "UnsignedSigner default, DevHmacSigner opt-in DEV_ONLY (capital/export.py)", "expected_upstream_contract": "k-stage7-authenticated-export signing/root/registry boundary per runtime/AUTHENTICATED_EXPORT.md v5", "status": "DEFERRED", "receipt": "NONE"},
    "ProducerPort": {"local": "PinnedFsmProducer over pinned CreditMachine and SettlementMachine (capital/producer.py)", "expected_upstream_contract": "promoted catalogue plus kix-compat-manifest/1 SEMANTIC_CONFORMANCE tuple consumed through the loopback integration gate; identical tuple to Commerce", "status": "DEFERRED", "receipt": "NONE (BOOTSTRAP bootstrap-1 is a shape reference only)"},
    "TermsPolicyPort": {"local": "not yet a typing.Protocol in capital/ports.py; values live in docs/decisions/CAPITAL_FINANCIAL_TERMS.md CAPITAL-TERMS-V1 and are applied by terms-overlay", "expected_upstream_contract": "f04-mock-deepening decided revision of CREDIT_ADVANCE_F04 section 5, then pending cr-01-product-authority / cr-04-underwriting-consent", "status": "DEFERRED (Capital provisional terms supplied as input candidate)", "receipt": "NONE"},
    "SettlementPolicyPort": {"local": "not yet a typing.Protocol; scenarios.py replays fixture policies only (500 bps fee, two allocation orders, no default)", "expected_upstream_contract": "settlement-policy-deepening decided revision of SETTLEMENT_DISTRIBUTION_F01_F03 section 7 plus fin-multi-payee-refund-proof vectors", "status": "DEFERRED (the sibling settlement-policy decision note under the same delegation, when present, supplies the input candidate)", "receipt": "NONE"}
  },
  "next_adapter_nodes": [
    {"node": "agent-grant-authorizer-adapter", "opens": "NOW (ADOPTED item)", "scope": "vendor-pin reference/ai_delegation at e2a029d with sha256 in capital/vendor/manifest.json; agent principal lane in AuthorizerPort; SEAMS.md and tests/test_seams.py lock update; readiness CAP-19 note; no EXECUTE, no identity"},
    {"node": "storage-port-postgres-adapter", "opens": "on k-stage5-durable-tx merge receipt", "scope": "opt-in PostgreSQL 17.11 StoragePort over unix socket, upstream schema and budgets, default off"},
    {"node": "producer-port-catalogue-adapter", "opens": "on SEMANTIC_CONFORMANCE manifest for the promoted catalogue (openapi-catalogue-promotion, p-sdk-1, contract-compatibility-profile)", "scope": "OpenAPI-pinned command validation and loopback gate transport; run_producer_vectors must pass; RS identifiers flow through"},
    {"node": "signature-port-stage7-adapter", "opens": "on k-stage7-authenticated-export merge receipt", "scope": "ExportManifestV1 extension fields, stage-7 signer, kix-canonical-json/1 alignment"},
    {"node": "projection-port-ledger-contract-adapter", "opens": "on fin-ledger-contract user merge plus plan revision carrying the eight candidates", "scope": "ProjectionEntry mapping of SIMULATION_FIXED charts; no second ledger"}
  ],
  "sync_nodes_without_adoption": [
    {"node": "readiness-binding-note-sync", "scope": "capital/readiness.py groups producer-binding, durable-finance, assets-and-rights and the service snapshot decisions list cite this note; FINANCE_PENDING_NODES.json stays the source of truth for candidate ids; no status becomes ADOPTED except the agent lane after its adapter"},
    {"node": "retention-slots-sync", "scope": "four named empty retention slots with owners in the export manifest"},
    {"node": "asset-spec-declaration", "scope": "KRW AssetSpec declared in facade-v1.json and projection account keys"},
    {"node": "acceptance-ladder-labels", "scope": "T05-sim and T06-sim labels in scripts/acceptance.py"}
  ],
  "confirmations": {
    "kix_protocol_modified": false,
    "kix_commerce_apps_modified": false,
    "upstream_nodes_marked_complete": [],
    "finance_candidates_marked_done": [],
    "diff_scope": "docs/decisions/CAPITAL_UPSTREAM_BINDING.md only; capital/, tests/, capital/vendor/ and the five vendor sha256 values unchanged",
    "production": "NOT_AUTHORIZED",
    "real_money": false
  }
}
```

## 5. 수용 기준 매핑

| 수용 기준 | 충족 위치 |
|---|---|
| `docs/decisions/CAPITAL_UPSTREAM_BINDING.md`에 하나의 ```` ```capital-decision-v1 ```` 블록, 열한 항목(`producer_sdk_tuple`, `stage5_durable_backend`, `stage6_finance_candidates`(여덟 FINANCE_PENDING id), `stage7_authenticated_export`, `identity_provider_kyc`, `asset_registry_fx`, `rights_scale_privacy`, `token_layer_coin_lock`, `ai_agent_grant_action_permit`, `t01_t06_qualification`, `deployment_tls_retention`) | §4. 블록은 이 문서에 하나뿐이고 열한 키가 모두 `entries`에 있다. `stage6_finance_candidates.candidate_ids`가 여덟 id를 나열하고 `bases.finance_pending_source_of_truth`가 정본을 가리킨다 |
| 각 항목은 ADOPTED(실존 upstream repo/PR/commit·영수증 필수) / NOT_ADOPTED / DEFERRED, `provided_by "Fable 5.1 (claude-fable-5-1), delegated by JunTae 2026-10-08"`, `date`, `provisional: true`, 선택한 target binding/plan, 차단 항목 | §4 모든 항목에 `status`·`provided_by`·`date`·`provisional`·`cap_rows`·`rationale`·`basis`·`target` 또는 `value`·`plan`·`blocked`. ADOPTED는 `ai_agent_grant_action_permit` 하나이며 `receipt`(repo, PR #130, 포함 commit `e2a029d…`, 파일 경로 4개, 병합 경계 표 행)를 가진다. 나머지는 `value: null`이고 방향은 `target`에 있다. 실존 upstream 영수증을 가진 DEFERRED 항목(#140, #139)은 영수증을 `upstream_receipt`에 적되 §5.1 규칙에 따라 ADOPTED로 올리지 않았다 |
| PROVISIONAL PRODUCT DECISION 라벨, 청약 아님·실자금 없음, 법률·세무·회계는 작업 가정 | 머리말 상태 배너와 §4 `status`/`scope`; 법률 의존 항목은 `basis: WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW`와 `review_owner` |
| KIX 장기 비전과의 연결과 읽은 kix-protocol 문서 경로 인용 | §2 (README, DEVELOPMENT_PLAN §1·§5·§10·§11·§12·§13·§14·§18, BLUEPRINT_20260914, ROADMAP, PROGRAM_ROADMAP_20260930, PROGRAM_DECISIONS_20260928, AUTHORITY_MODEL_1, TOKEN_LAYER_AND_RIGHTS_SCALE_SCOPE_20260929, RIGHTS_SCALE_RS0_DECISION_20261008, RUNTIME_ARCHITECTURE_S062, COMMERCE_CONTRACTS, blueprints 2종, BACKEND_ADOPTION_PROPOSAL_20261009, RETENTION_PERIODS_PROPOSAL_20261009, STAGE2_V5·INTEGRATION_A·CUT_PROOF(§5 표 경유), adr/0002, contracts CREDIT_ADVANCE_F04·SETTLEMENT_DISTRIBUTION_F01_F03·AI_DELEGATION_AUTHORITY·ADAPTER_EVENT_IDENTITY·READINESS_RUNTIME·PG_TOSS_CARD_PROFILE·FIRST_BATCH_OPEN_INPUTS·sdk/COMPATIBILITY_MANIFEST_V1, runtime/AUTHENTICATED_EXPORT, sdk/README·sdk-pin·manifest.bootstrap-1, aiops FINANCE_COMPLETION_DESIGN_KO·FINANCE_PENDING_NODES·CONTRACT_RELEASE_AND_COMPLETION_DESIGN_KO §5.1·PROGRAM_EXPANSION_20261002_KO·PROGRAM_ASTRA_DELEGATION, status/CURRENT_CAPABILITY_REGISTER, tasks/TASK_005, PROTOCOL_MASTERPLAN_V2 §7·§13, validation 기록 3건, `.aiops/program.json`) |
| 열린 위험 목록 | §6 |
| 모든 수용 항목 매핑 | 이 표 |
| 일곱 port(StoragePort, ProjectionPort, AuthorizerPort, SignaturePort, ProducerPort, TermsPolicyPort, SettlementPolicyPort) → 대체할 upstream 계약 | §4 `port_map` (local, expected_upstream_contract, status, receipt). TermsPolicyPort·SettlementPolicyPort는 아직 `capital/ports.py`에 없음을 명시했다 |
| 개방할 next adapter 노드(Fable 권고) | §4 `next_adapter_nodes`(ADOPTED 항목만 지금 개방, 나머지는 영수증 조건부)와 `sync_nodes_without_adoption`; §7 |
| kix-protocol·kix-commerce-apps 미수정, upstream 노드 완료 표시 없음, diff는 `docs/decisions/`에 한정 | 머리말과 §4 `confirmations`. 이 세션은 읽기 전용이며 파일을 쓰지 않았다. 실제 diff 범위는 supervisor PR과 독립 리뷰어가 확인한다 |
| (이전 요청문) `readiness.py` producer-binding·durable-finance·assets-and-rights 그룹이 이 노트를 인용, `FINANCE_PENDING_NODES.json`이 후보 id 정본 유지 | 이 노드 범위 밖(코드 변경 없음). §4 `sync_nodes_without_adoption[readiness-binding-note-sync]`와 §7이 소유 노드로 지정; `bases.finance_pending_source_of_truth`가 정본을 고정 |
| (이전 요청문) seam별 upstream 계약 명명, 영수증 없는 ADOPTED 금지 | `port_map`과 `docs/SEAMS.md` 규칙 동일. `tests/test_seams.py`는 현재 모든 행을 비ADOPTED로 잠그므로 agent lane adapter 노드가 그 잠금을 함께 갱신해야 한다(§7) |

## 6. 열린 위험과 재검토 조건

- **AI 위임 계약이 초안 0.1이다.** 상위 개정(0.2+)이나 `ai-delegation-execution-decision`이 EXECUTE·집계 창·복수 ACTIVE grant 규칙을 바꾸면 Capital 핀은 바이트로 보호되지만 의미가 어긋날 수 있다. 재핀은 별도 노드·별도 영수증으로만 한다. 병합 commit SHA가 읽은 문서에 없어 adapter 노드가 GitHub에서 확인해야 한다.
- **저장소 이름 별칭.** vendor manifest와 sdk manifest는 `SUNBURN-Golden/kix-protocol`, 로드맵·FINANCE_PENDING은 `BeautifulMind-JT/kix-protocol`을 쓴다. 같은 저장소로 읽었으나 adapter 노드는 URL로 동일성을 확인해 manifest에 하나로 적는다.
- **BOOTSTRAP ≠ SEMANTIC_CONFORMANCE.** `manifest.bootstrap-1.json`을 모양 참조로 쓰는 것이 채택으로 읽히면 CAP-16이 거짓 완료가 된다. readiness 문구는 계속 `NOT_BOUND`다.
- **정규화 프로파일 차이.** Capital `service.digest`는 `ensure_ascii=True`, upstream `kix-canonical-json/1`은 비ASCII를 이스케이프하지 않는다. stage 7 adapter 전에 `canonical_bytes`를 그 프로파일로 맞추면 `tests/golden/demo.json`의 `content_digest`가 바뀐다(`--update-golden` 필요).
- **stage 5 선행의 깊이.** `k-stage5-durable-tx`는 `k-stage2-v5-impl`(미병합)과 backend 결정 뒤에만 시작한다. Capital StoragePort binding 시점을 Capital이 당길 수 없다. PostgreSQL 드라이버는 stdlib가 아니므로 옵트인 extra로만 둔다는 제약은 유지된다.
- **Finance 후보 미편입.** 여덟 후보가 plan revision으로 편입되기 전에는 `fin-ledger-contract`도 시작하지 않는다. Capital 투영을 쓰는 화면·문서가 "채택"처럼 보이지 않도록 `SYNTHETIC_UNADOPTED`·`NOT_BOUND` 라벨을 유지한다.
- **Commerce 미열람.** kix-commerce-apps를 이 세션에서 읽지 않았다. 동일 tuple 요구(§3.1)는 FINANCE 설계 §7과 Capital 요구사항 문서에 근거한 것이며, Commerce가 다른 결합 방식을 택했다면 producer adapter 노드에서 재검토한다.
- **법무·인허가(작업 가정).** IdP/KYC 주체·벤더, 전자서명·인증서 보관(TLS·export 서명 키)의 법적 효력, 보존 의무(세무·회계 담당 미지정)는 전문가 검토 대상이다. `f04-real-funds-lift-criteria`·`tl-legal-brief` 질문지에 넘긴다.
- **운영 책임자 부재.** 배포·TLS·백업·복구 책임자 이름이 없다(upstream BACKEND 제안 §8과 같은 상태). JunTae 지정 전에는 loopback 밖으로 나가지 않는다.
- **역사 문서 의존.** T01–T06과 AgentGrant/ActionPermit 이름은 `PROTOCOL_MASTERPLAN_V2`(현행 아님)에서 왔다. 현행 계약이 다른 이름(부여/제안)을 쓰므로 Capital 문서는 두 이름의 대응을 항상 병기한다.
- **재검토 트리거.** (1) `openapi-catalogue-promotion`·`p-sdk-1`·`contract-compatibility-profile` 병합, (2) `k-stage5-durable-tx`·`k-stage7-authenticated-export` 병합, (3) Finance plan revision·`fin-ledger-contract` 병합, (4) `ai-delegation-execution-decision`·`tl-0`·`tl-coin-lock-adr`·`f04-real-funds-lift-criteria`·`public-endpoint-readiness-plan` 사용자 결정, (5) 토스·법무·Astra 회신(보존 값), (6) AI 위임 계약 개정.

## 7. 후속 작업

- **`agent-grant-authorizer-adapter`(지금 개방 권고, 유일한 ADOPTED 항목).** (1) `reference/ai_delegation/ai_delegation_mock.py`·`test_ai_delegation_mock.py`를 `capital/vendor/ai_delegation/`에 바이트 복사하고 `capital/vendor/manifest.json`에 commit(`e2a029d…`, 병합 SHA 확인 후 병기)·SHA256을 추가; 기존 다섯 해시 불변. (2) `capital/auth.py`에 `agent` 역할과 `call_tool` 경로, `capital/ports.py` AuthorizerPort 문서화, 모든 `command:*`를 agent에 거부. (3) `docs/SEAMS.md` AuthorizerPort 행을 `PARTIAL`로, 영수증 열에 PR #130·commit을 기록하고 `tests/test_seams.py`의 "모든 행 비ADOPTED·영수증 NONE" 잠금을 그 행만 예외로 갱신. (4) readiness CAP-19 note를 "AgentGrant semantics SIMULATED via pinned AI_DELEGATION_AUTHORITY 0.1; ActionPermit, IdP, KYC NOT_BOUND"로. (5) 제안 금액 한도를 `CAPITAL-TERMS-V1` 상한에 묶고 2인 원칙을 proposal 승인 경로에 적용. 실행·서명·지급은 어떤 경로로도 열지 않는다.
- **`readiness-binding-note-sync`(동기화).** `capital/readiness.py`의 producer-binding·durable-finance·assets-and-rights 그룹 `blockers`/`claim`과 `capital/service.py` snapshot `decisions` 문구가 이 문서를 인용하도록 바꾼다("PROVISIONAL per docs/decisions/CAPITAL_UPSTREAM_BINDING.md"). `FINANCE_PENDING_NODES.json`이 후보 id 정본임을 CAP-13/14 note에 적는다. 상태값은 바꾸지 않는다.
- **`retention-slots-sync`·`asset-spec-declaration`·`acceptance-ladder-labels`(동기화, 채택 아님).** §3.11·§3.6·§3.10의 "지금 할 수 있는 것"만 반영한다.
- **조건부 adapter 노드.** `storage-port-postgres-adapter`, `producer-port-catalogue-adapter`, `signature-port-stage7-adapter`, `projection-port-ledger-contract-adapter`는 §4 `next_adapter_nodes`의 영수증 조건이 충족된 뒤에만 연다. 각 노드는 영수증(repo·PR·commit·파일 sha256)을 `docs/SEAMS.md`와 vendor manifest에 적고 나서야 해당 행을 ADOPTED로 바꾼다.
- **`terms-overlay`와 정산 정책 결정 노드.** `TermsPolicyPort`·`SettlementPolicyPort`를 `capital/ports.py`의 `typing.Protocol`로 추가하는 일은 각각 `terms-overlay`(CAPITAL-TERMS-V1 적용)와 정산 정책 결정의 적용 노드가 한다. 이 문서는 두 port의 upstream 대응만 정했다.
- **upstream 제출 후보(채택 주장 없음).** `f04-mock-deepening`(CAPITAL-TERMS-V1), `fin-ledger-contract`(Capital 투영 계정표·보존 술어), `fin-multi-payee-refund-proof`(9 시나리오), `k1-open-inputs-brief`/`tl-legal-brief`/`f04-real-funds-lift-criteria`(§6 법무·인허가 질문). 채택은 upstream PR 영수증만이 증명하며, 그 전까지 Capital `upstream_binding: NOT_BOUND`(agent lane 제외)를 유지한다.
- **Commerce.** 이 문서는 Commerce 화면을 바꾸지 않는다. Capital producer adapter는 Commerce `bind-credit-fsm`·`bind-settlement-fsm`과 같은 tuple을 핀해야 하며, 다르면 producer adapter 노드에서 멈추고 결정으로 올린다.
