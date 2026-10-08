# Capital 청사진 요구사항과 구현·선행 매핑

2026-10-07. Capital 구현 기준 `e9bea122102b87a1f11ac673d50e01c31cba6922`.
Protocol 읽기 기준 **`7481b0e16ce9b903abbffa62249bb91cd9e63cfe`**, Commerce main 확인 `7c2452645c50b8ede17bdd762794adeabe42319e`.
모든 Protocol 출처는 아래 SHA에 고정한다. 이전 CI·설계 후보·미래 계획의 존재를 현재 구현 완료로 옮기지 않는다.

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

`SIMULATED`는 이 PR의 로컬 합성 범위만, `READ_ONLY_FIXTURE`는 불변 참조 데이터 조회만, `NOT_BOUND`는 실제 producer 계약 미연결, `DECISION_REQUIRED`는 정책 미정이다. 행을 완료 분모에서 제거하지 않는다.

| ID | 청사진 요구 | 현재 제품·검증 | 상태 / 다음 선행 |
|---|---|---|---|
| CAP-01 | 대여·선지급 전 기간 | F04 offer/approve/reject/cancel/bind/draw/repay/close/default/reconcile API·화면, 실제 양/음성 경로 | SIMULATED; 이자·기간·손실 정책은 `f04-mock-deepening` 결정 |
| CAP-02 | 수익참여·배분 | 제품 연동 준비 카드와 계약 입력 목록 | DECISION_REQUIRED: 수익/원가·회수 순서·비율/상한·조정; V2 §7 |
| CAP-03 | 정산채권 양도·매입 | 금융권리/관람권 분리 표시, 원 claim 조회 | DECISION_REQUIRED: 원 채권·배정량·보유자·대가·우선순위·회수 |
| CAP-04 | 담보·준비금 | 공유 액면 예약·해제·미이행 유지 검사 | F04 부분 SIMULATED; 외부 담보 완전성·추가 납입·집행 미구현 |
| CAP-05 | 청구·수취인·분할 정산 | F01–F03 고정 시나리오에서 두 배정 순서·부분 명세서·중복/상충·늦은 현금의 단계별 의무 비교 | READ_ONLY_FIXTURE; 운영 배분 순서/잔여·부담 정책은 미정 |
| CAP-06 | 환불·공연취소·회수 | 배정 전/후 부분 환불, 단일 전액 vs 분할 환불, 취소 수락·회수·은행 미종결 비교 | 일부 SIMULATED; 부분 환불·리셀 과거계약 취소 부담 미정 |
| CAP-07 | 최초 판매·반복 리셀·입장 연계 | trade/claim identity 조회, 권리/금융 분리 | NOT_BOUND: Commerce 실여정·Protocol producer tuple; 이 PR은 티켓 생성/이전 없음 |
| CAP-08 | 초과 배정·현금/한도 구별 | 동일 claim 두 draw 경합, 부분 repay 후 예약 유지, close만 해제; 활성 상태를 바꾸지 않는 인출 사전점검 | SIMULATED; 외부 담보/분산 자원 한도 아님 |
| CAP-09 | 승인액/매출/권리확정/지급/환불 보고 | 로컬 다섯 구분 명세서: 승인·노출/상환/잔액·예약은 FSM 조회(SIMULATED), 정산 확인/배정·환불은 고정 fixture. `primary_sales`·`resale_sales`·`actual_paid`는 NOT_BOUND이고 최초판매와 리셀은 합산하지 않음. cut·fixtures digest·capacity bound 표기 | 로컬 진단만; 실지급·세무 보고·은행 대사 아님 |
| CAP-10 | 원 operation/최초 결과/UNKNOWN | 단일 POST, 원 receipt 조회, absent→UNKNOWN, reload·old-instance fence, 옵트인 로컬 파일 재시작 복원 | SIMULATED; 개발용 LOCAL_FILE_WORKSPACE. stage5 내구 거래·inbox/outbox·호스트 간 fencing은 CAP-11 |
| CAP-11 | 내구 거래·inbox/outbox·장애복구 | 연동 계약과 미지원 상태 | NOT_BOUND: `k-stage5-durable-tx`·backend 채택·v5, 자체 저장엔진 만들지 않음 |
| CAP-12 | 자산별 정확한 금액·FX | KRW 고정 프로파일, int 검증, 포트폴리오 BigInt 표시 | 일부 SIMULATED; u128·registry/정밀도·FX quote/execution은 별도 계약 |
| CAP-13 | 복식 금융 투영 | 로컬 후보 복식 투영 · `SYNTHETIC_UNADOPTED` 표기 · 운영 원장 `NOT_BOUND` | SIMULATED(로컬 후보); fin-ledger-contract·stage5/6 선행 유지, 계정/수익인식/세무 미정 |
| CAP-14 | 원관측·대사 예외 | 로컬 대사 예외: receipt↔저널 키, 거절 receipt의 저널 부재, 재생 digest, 제안↔fixture, 투영↔조회, fixtures digest. 없는 receipt는 UNKNOWN_UNRESOLVED이며 재시도·해소하지 않음 | 로컬 진단만; 은행·PG·제공자 관측, source cut, 제공자 인증 완전성은 NOT_BOUND |
| CAP-15 | 인증 export·일관 source cut | 로컬 journal JSON + 소스 pin/fixture hash/재생 일치 | 로컬 진단만; stage7/finance export, signed manifest·cursor·watermark 미구현 |
| CAP-16 | SDK·API 적합성 | strict 로컬 envelope, 화면에서 vendor byte hash 확인, 자체 namespace | NOT_BOUND: 확대 OpenAPI/SDK/SEMANTIC_CONFORMANCE exact tuple |
| CAP-17 | 공개/비공개·권리 규모 | 외부 의존성과 관람권 비권위 표시 | NOT_BOUND: RS-0~5, privacy/currentness, 1024/16384/65536 규모 검증 없음 |
| CAP-18 | 선택적 토큰 담보·보상 | 향후 연동 설명, 외부 호출·발행 코드 없음 | NOT_AUTHORIZED: TL 계약·coin lock/user 결정; KRW 목을 토큰 한도로 확장 안 함 |
| CAP-19 | AI 운영·권한·최소공개 | 로컬 합성 역할(organizer/auditor/observer)을 서버가 강제하고 receipt에 표시. 계정·비밀번호·개인정보 없음 | NOT_BOUND: AgentGrant/ActionPermit, 실제 IdP·KYC·자격증명, 현재 근거·권한·비밀 분리 |
| CAP-20 | 접근성·통합 수용 | 실제 browser 정상/거절/UNKNOWN/reload, mobile, keyboard, screenshot | 자동검증만; 사용자 수용 PENDING, full T01→T06/서비스 qualification 미실행 |

## Finance 후보 8개를 유지하는 후속 위치

`fin-ledger-contract`(계약), `fin-double-entry-projection`, `fin-multi-payee-refund-proof`, `fin-observation-reconciliation`, `fin-credit-exposure-reconciliation`, `fin-consistent-accounting-export`, `fin-catalogue-read-model`, `fin-finance-closeout`의 정확한 이름/선행은 upstream `FINANCE_PENDING_NODES.json`이 정본이다. 이 PR에서 노드를 adopt/DONE으로 바꾸거나 분모를 줄이지 않는다. Capital 시뮬레이션·참조 pin·문서 매핑은 그 실행 영수증을 대신하지 않는다. 후보 node ID가 개정되면 원 정의와 digest를 함께 대조한다.

## 현재 필요한 결정과 진행 가능한 부분

현재 로컬 시뮬레이션은 정책 결정 없이 검증 가능하다. 따라서 단계마다 승인을 요구하지 않고 구현·검증·Draft PR을 진행한다. 향후 금융계약 실행을 열 때만 정확한 미정 항목(수익/우선순위·이자/수수료/기간·환불 부담·계정/법무/면허·source backend 채택)을 사용자/지정 담당자에게 결정 요청한다. 소스 리뷰/CI 통과는 해당 결정을 대신하지 않는다.

## 추가 제품화와 실제 차단점

같은 PR에서 DB 없이 가능한 CAP-05/06의 참조 시나리오를 9개·35단계로 구현했다. 모든 배정·환불 수치는 고정한 upstream 목에서 계산한다. 클라이언트는 수치를 재계산하지 않는다. 다섯 읽기 전용 보존식·예상 거절·거절 시 상태 보존은 별도로 검사한다. CAP-08의 인출 사전점검은 현재 저널의 별도 복제본만 변경하므로 활성 제안·예약·receipt에 효과가 없다. CAP-16의 파일 무결성 표시는 source byte 일치에만 한정된다.

나머지는 화면에서 제품 행동별로 구분한다. CAP-13의 로컬 후보는 `SYNTHETIC_UNADOPTED` 표식의 읽기 전용 투영이며 계정·수익인식·세무를 정하지 않고 `fin-ledger-contract`를 채택하지 않는다. CAP-09의 다섯 구분 명세서와 CAP-14의 대사 예외는 로컬 진단이다. 은행 대사·제공자 인증 완전성·실지급을 주장하지 않고, 최초 판매와 리셀 매출을 합산하지 않는다. 수익참여·채권매입·외부담보 실행은 금융 조건 결정이 필요하다. 실제 주문/리셀/권리 연결은 exact producer/SDK/profile이, 내구 원장·채택 복식·인증 export는 stage5/6/7과 Finance 후보 채택이 필요하다. 다중 자산·권리 규모·비공개·AI 권한은 해당 upstream 계약이 필요하다. 실서비스 실행은 현재 승인되지 않았다. 이 차단점을 가상 계산이나 자체 backend로 대체하지 않는다. 각 행은 계속 전체 Capital 범위에 남는다.
