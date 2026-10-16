# Capital 외부 관문 결정 — 실자금 파일럿, 면허 대주 법인, IdP·KYC 벤더, 공개 엔드포인트·TLS, 회계·세무 서명, 보존 기간, 상위 연동 영수증 검토

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
결정자: **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**. 결정일 2026-10-17, KIX-CAPITAL main `663b492`, kix-protocol `9d0860c`.

이 문서는 **docs-only**다. 시뮬레이션·제품 설계용이며 청약이나 대출 제안이 아니다. 실자금, production, 공개 배포는 계속 `NOT_AUTHORIZED`다. 돈을 쓰거나, 배포하거나, 시크릿·과금을 건드리는 일은 실행하지 않았고 **전부 `PENDING_OWNER_ACTION`(JunTae)** 으로 남긴다. 자금이 움직였다, 배포됐다, 자격증명이 설정됐다, 전문가가 서명했다는 주장은 이 문서에 없다. 법률·세무·회계·인허가 내용은 전문가 검토 전의 작업 가정이며 자문이 아니다. 실제 upstream 영수증(repo·PR·merge commit·경로) 없이 어떤 upstream 계약도 채택됐다고 적지 않는다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `external-gate-decision` · deps 일곱 결정 노드(전부 MERGED) · kind `decision` · user_merge `False` · 이 노드에 의존하는 노드 없음 |
| 위임 원문 | 2026-10-08 18:25 KST JunTae Park: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." (2026-10-14 07:24 추가 지시: docs-only, 돈·배포·시크릿은 PENDING_OWNER_ACTION) |
| kix-protocol 기준 | `9d0860c`는 감독자가 제공한 값이며 이 세션에서 git으로 재확인하지 않았다. `kixproto-ro/README.md`가 적은 main HEAD `d5b9f2d…`는 그 문서 작업 시점의 스냅샷이다(README 스스로 "영원히 최신 HEAD가 아니다"라고 적음). |
| vendor pin | `capital/vendor/manifest.json` commit `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`, 불변. 이 노트는 `capital/`·`tests/`·vendor·다른 docs를 바꾸지 않고 diff는 `docs/decisions/` 한 파일이다. |
| 읽은 범위 | 감독자가 지정한 여섯 경로만. 선행 결정 중 `CAPITAL_UPSTREAM_BINDING.md`와 `CAPITAL_ACCOUNTS_TAX_LEGAL.md`만 읽었다(두 문서 모두 앞쪽 산문 부분 중심). `CAPITAL_FINANCIAL_TERMS.md`와 overlay·shadow·demo·artifact·digest-export 다섯 노트는 팩 밖이라 읽지 않았고, 이 노트는 그 값과 충돌하지 않도록 값을 **복사하지 않고 이름으로만** 인용한다. |
| 상태 어휘 | **ADOPTED** = Capital이 위임 범위 안에서 정한 잠정 값(upstream 채택 아님). **UNDETERMINED** = 외부 답이 있어야 정해지는 값. 담당과 이유를 적고 `value: null`, 방향은 `target`. **NOT_AUTHORIZED** = 사람 관문 전에는 금지되는 행위. `value: null`. `basis = PENDING_OWNER_ACTION`은 돈·배포·시크릿·과금·서명이 필요해 에이전트가 할 수 없다는 뜻이다. |

## 1. 결정 요약

| item | 결정 | CAP rows | 소비 노드 / seam |
|---|---|---|---|
| `real_funds_pilot` | **NOT_AUTHORIZED** (PENDING_OWNER_ACTION). 파일럿 형태와 진입 기준은 정했고, 한도 숫자·자금원·개시 승인은 JunTae 몫이다. | CAP-11, CAP-14, CAP-19, CAP-20 | 로컬 소비자 없음. 해제는 upstream 사용자 노드 `f04-real-funds-lift-criteria` |
| `licensed_lender_entity` | **UNDETERMINED** (PENDING_OWNER_ACTION). 경로는 `CAPITAL-LICENCE-ROUTE-V1`(전담 등록 대주 법인 1차, 면허 파트너 대안)을 재확인하고 선택 규칙을 더했다. 법인은 아직 없다. | CAP-03, CAP-13, CAP-15 | 로컬 소비자 없음 (FSM 플래그 `license_granted`·`regulated_product` 거짓 유지) |
| `idp_kyc_vendor` | **UNDETERMINED** (PENDING_OWNER_ACTION). 선택 순서(대주 법인 확정 뒤)와 선택 기준을 정했다. 벤더명은 정하지 않는다. | CAP-19 | `AuthorizerPort` (`identity`·`authentication` `NOT_BOUND` 유지) |
| `public_endpoint_tls` | **NOT_AUTHORIZED** (PENDING_OWNER_ACTION). loopback 전용 유지, TLS·인증서·키는 Capital 밖. 첫 파일럿은 공개 엔드포인트 없이 운영자 데스크 전용으로 설계한다. | CAP-15, CAP-20 | 로컬 소비자 없음 (서버는 `127.0.0.1`만) |
| `accounting_tax_signoff` | **UNDETERMINED** (PENDING_OWNER_ACTION). 서명 패키지 범위와 기록 형식만 정했다. 서명은 없다. | CAP-13, CAP-14, CAP-15 | `ProjectionPort`·export 라벨 (`SYNTHETIC_UNADOPTED`, `tax`·`legal`·`operating_ledger` `NOT_BOUND` 유지) |
| `retention_period` | **UNDETERMINED** (PENDING_OWNER_ACTION). 다섯 칸의 주인과 실데이터 반입 전제 조건만 정했고 기간 숫자는 비운다. | CAP-14, CAP-15 | export manifest `retention_policy` 다섯 칸 (이미 이름 있는 빈 칸) |
| `upstream_adoption_receipt_review` | **ADOPTED** (Capital의 검토 규칙과 판정표). upstream 계약을 새로 채택하는 것이 아니다. | CAP-07, CAP-11, CAP-15, CAP-16, CAP-19 | `docs/SEAMS.md` (ADOPTED 행 없음 유지), `GET /api/readiness` 문구 |

모든 항목의 상태는 `GET /api/decisions`(`scripts/decision_ledger.py`와 같은 파서)가 읽기만 하고 아무것도 채택하지 않는다. `readiness` release 그룹 차단 사유 문구를 이 노트에 맞추는 일은 이 노드에 의존하지 않는 별도 노드의 몫이다.

## 2. KIX 비전과의 연결

읽은 문서는 팩에 든 경로뿐이다. 다른 upstream 문서(프로그램 결정 §5, #139 등)는 위 두 Capital 노트가 인용한 범위에서만 언급하며 이번에 다시 읽지 않았다.

- **모델 1과 "다른 사실의 분리".** `kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md`: `예약 확정 ≠ 결제 확인 ≠ 체인 권리 발행 완료`이고 체인이 실제 은행 자금을 보증하지 않는다. 그래서 Capital의 "수락" 영수증은 자금 이동의 증거가 아니며, 실자금 파일럿은 은행·PG의 **외부 관측 사실**(CAP-14, 현재 `NOT_BOUND`)이 묶이기 전에는 시작할 수 없다. A-4 표는 "침묵/timeout으로 미사용이라 간주 금지", "과거 사실 재생은 새로운 외부 실행 허가가 아님"이라고 적는다. 파일럿 진입 기준의 UNKNOWN·재생 규칙이 여기서 나온다.
- **잠금과 해제.** `kixproto-ro/README.md` §3 끝 단락과 §4: 실자금·실 PG/은행/KYC·공개 운영 엔드포인트는 계속 잠겨 있고 로드맵의 조건부 로컬 구현도 열지 않는다. §4는 토스페이먼츠를 잠정 선택했지만 **리셀·금융 대금의 실제 가맹 범위는 미확인**이라고 적는다. 정산 상계를 1차 회수 수단으로 쓰는 Capital에는 이것이 파일럿의 실질 차단 사유다. §6 끝: "공개 배포용 라이선스는 부여하지 않았습니다." 이 문장은 공개 게시 결정에 쓰인다(§3.4).
- **Capital 쪽 근거.** `docs/RELEASES.md`(`LOCAL_SIMULATION_ARTIFACT`, `signed:false`, `published:false`, 호스팅·릴리스 채널 미선정, DEV HMAC은 인증도 서명도 아님), `docs/INTEGRATION.md`(토큰 없는 요청이 organizer 토큰을 받는 loopback 경계, `identity`·`authentication` `NOT_BOUND`, manifest `retention_policy` 다섯 칸, 모든 "ADOPTED 행 없음"), `CAPITAL_UPSTREAM_BINDING.md`(IdP/KYC NOT_ADOPTED, 배포·TLS·보존 DEFERRED, 영수증 목록), `CAPITAL_ACCOUNTS_TAX_LEGAL.md`(`CAPITAL-LICENCE-ROUTE-V1`, COA·REVREC·TAX, 보존 다섯 칸).
- **"포부"의 해석.** 위임은 큰 야망을 전제로 하되 사람이 꼭 필요한 곳에서만 멈추라는 뜻이다. 그래서 외부 답이 없어 값을 못 정하는 칸도 **순서, 선택 기준, 진입 조건, JunTae가 할 일**까지는 지금 정해 두어, 답이 도착한 날 다음 단계가 기계적으로 열리게 한다.

## 3. 항목별 결정

### 3.0 관문 순서 (이 노트가 정하는 것)

`G1` 법무 적용 판단(JunTae가 지명한 법무) → `G2` 대주 법인 또는 면허 파트너 확정 → `G3` 회계·세무 서명 ∥ `G4` IdP·KYC 벤더 → `G6` 공개 엔드포인트(선택, 파일럿 필수 아님) → `G7` `f04-real-funds-lift-criteria` 사용자 병합 + JunTae 명시 승인. `G5` upstream 영수증(stage5 내구 거래, stage7 인증 export, SEMANTIC_CONFORMANCE tuple, `fin-ledger-contract`)은 사람 답 없이 upstream 병합만으로 진행되므로 G1~G4와 **병렬**이며 G7 전에 닫혀야 한다. 순서의 이유는 KYC/AML 주체가 대주 법인이라 벤더를 먼저 고르면 결정 순서가 뒤집히기 때문이다(`CAPITAL_UPSTREAM_BINDING.md` §3.5). 법무가 순서를 바꾸자고 하면 따른다.

### 3.1 real_funds_pilot (CAP-11, CAP-14, CAP-19, CAP-20) — NOT_AUTHORIZED

- **방향.** 파일럿이 열린다면 형태는 다음으로 고정한다. B2B 전용(주최자 법인 수익자), 선지급은 정산 분배 상계로 회수, 운영자 데스크(`capital-desk`) 전용과 2인 원칙, AI는 제안만, 투자자·채권매입(CAP-03 `NOT_OFFERED`)·토큰 담보 없음. **한도는 JunTae가 공급**하며 `CAPITAL-TERMS-V1`의 시뮬레이션 상한을 넘을 수 없는 천장으로만 쓴다. 이 노트는 숫자를 만들지 않는다.
- **진입 기준(Capital 쪽 체크리스트, upstream 노드의 입력 후보일 뿐 그 노드의 채택이 아님).** G1~G5가 실제 영수증과 함께 닫힘 · 은행/PG 관측 binding(CAP-14) · 토스 가맹 범위 확인(README §4) · UNKNOWN 자동 재시도 없음 · 중지 권한자 지정.
- **근거.** AUTHORITY_MODEL_1(체인·Capital 어느 쪽도 자금 이동을 보증하지 않음), README §3·§4 잠금.
- **대안.** "작게 먼저 해 보고 서류는 나중에": 작업 가정상 이자부 신용 공여는 인허가 대상이라 기각. 시뮬레이션 숫자를 그대로 실한도로 승격: 기각.
- **PENDING_OWNER_ACTION.** `f04-real-funds-lift-criteria` 개시 결정 · 자금원과 계좌 지정 · 파일럿 한도와 중지 권한자 승인. 코드는 `funds_executed`, `license_granted`, `regulated_product`를 계속 거짓으로 둔다.

### 3.2 licensed_lender_entity (CAP-03, CAP-13, CAP-15) — UNDETERMINED

- **방향.** `CAPITAL-LICENCE-ROUTE-V1`을 재확인한다. 1차는 KIX Capital 전담 대부업 등록 대주 법인, 대안은 면허 파트너 대주와 Capital의 플랫폼·서비서 역할이다. **G2 선택 규칙**: 가격, 2인 원칙, 회수 폭포를 Capital이 통제해야 하면 1차, 등록 일정이나 자본 요건이 막으면 대안을 택한다. 대안은 중개 등록 질문과 파트너·PG 제약을 다시 연다. Capital 코드는 대주(lender of record)가 되지 않으며 저장소에는 법인명을 쓰지 않는다. 존재하지 않는 법인의 자리표시자가 실제처럼 보이면 안 된다.
- **UNDETERMINED인 이유.** 법인 설립, 등록 신청, 자본 납입, 자문 계약은 돈과 서류가 드는 사람 행위이고 적용 판단은 `PENDING_PROFESSIONAL_REVIEW`다.
- **PENDING_OWNER_ACTION.** 법무 지명 · G1 의견 의뢰 · G2 경로 확정 · 법인 설립과 등록.

### 3.3 idp_kyc_vendor (CAP-19) — UNDETERMINED

- **결정한 선택 기준.** (1) 계약 주체는 대주 법인이며 Capital 코드가 아니다. (2) Capital은 `kyc_status`, `verified_at`, `provider_ref` 같은 **attested fact**만 받고 원본 개인정보는 받지 않는다(`NO_PERSONAL_DATA_BY_DESIGN_V1`). (3) 사람 principal은 OIDC 형태 bearer(발급자·대상·만료·`kix_role` 검증)이고 Commerce·통합 관문과 같은 경계를 쓴다. (4) 삭제 요청은 벤더 쪽에서 처리한다. (5) 클라이언트 시크릿·서명 키는 저장소, 노트, fixture, 로그에 두지 않는다. (6) AI `agent` lane은 IdP와 무관하게 제안 전용이다. 벤더명은 정하지 않는다.
- **현재 상태.** 역할은 loopback에서 자기 선택하는 합성 값이며(`LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED`) 인증이 아니다.
- **PENDING_OWNER_ACTION.** G2 뒤 벤더 선정 · 계약과 과금 · 테스트 테넌트와 API 키 발급(시크릿).

### 3.4 public_endpoint_tls (CAP-15, CAP-20) — NOT_AUTHORIZED

- **방향.** 서버는 `127.0.0.1` 전용이고 Capital 프로세스는 TLS를 종단하지 않으며 인증서·키를 갖지 않는다. 외부 접근이 필요해지면 운영자 소유 reverse proxy가 종단하되 **G4(실제 인증) 뒤에만** 연다. 이유는 구체적이다. 토큰 없는 요청이 organizer 토큰을 받는 현재 경계(INTEGRATION.md)를 그대로 노출하면 누구나 organizer가 된다. **첫 파일럿은 공개 엔드포인트 없이 운영자 데스크 전용**으로 설계한다. 주최자 셀프서비스를 위한 공개 접속은 파일럿 이후다.
- **아티팩트.** `.pyz`는 `signed:false`, `published:false`이며 호스팅·릴리스 채널은 정하지 않았다. 이 아티팩트는 vendor된 upstream 바이트를 담는데 upstream README §6은 공개 배포용 라이선스를 부여하지 않았다고 적는다. 따라서 **공개 게시는 upstream 저장소 소유자(JunTae)의 라이선스 결정 전까지 NOT_AUTHORIZED**다. 서명 키 생성은 시크릿이므로 PENDING_OWNER_ACTION이고 DEV HMAC을 서명으로 표시하지 않는다.
- **대안.** Capital 내장 TLS(`ssl`): 키 보관 권한이 생겨 기각(binding §3.11).
- **PENDING_OWNER_ACTION.** 도메인·DNS·인증서·호스팅 계정·과금 · 라이선스 결정 · 릴리스 서명 키.

### 3.5 accounting_tax_signoff (CAP-13, CAP-14, CAP-15) — UNDETERMINED

- **서명 패키지 범위(결정).** `CAPITAL-COA-V1`과 V1→COA 매핑, `CAPITAL-REVREC-V1`(특히 부도 후 이자의 9700 유예), `CAPITAL-TAX-V1`(금융용역 면세 가정, `withholding_rate_bps`, BTD 메모), `CAPITAL-LICENCE-ROUTE-V1`의 적용 판단, 보존 숫자.
- **기록 형식(결정).** 검토자 성명과 자격, 일자, 검토한 각 노트의 git blob SHA, 범위, 결과(`APPROVED`/`APPROVED_WITH_CHANGES`/`REJECTED`)를 **후속 결정 노트의 포인터**로만 남긴다. 코드 상수가 아니며 blob이 바뀌면 서명은 무효다. 에이전트 출력은 서명이 될 수 없다.
- **그때까지.** `accounting_policy=SYNTHETIC_UNADOPTED`, `tax`·`legal`·`operating_ledger` `NOT_BOUND`. 어떤 산출물도 세무 신고나 재무제표가 아니다.
- **PENDING_OWNER_ACTION.** 회계사·세무사 지명과 계약(수임료) · `withholding_rate_bps` 공급.

### 3.6 retention_period (CAP-14, CAP-15) — UNDETERMINED

- **결정.** 다섯 칸(`legal_dispute_hold`, `business_reconciliation`, `retry_support`, `memory_residency`, `tax_accounting_records`)과 주인은 `CAPITAL-RETENTION-PRIVACY-V1`을 따른다. 숫자는 비운다. upstream R1이 값을 멈춘 채로 두었고 제공자 공개값(예: 15일 멱등키)은 기간이 아니다. 새로 정하는 규칙: **다섯 칸이 모두 주인 공급 값을 받고 법정·분쟁 보류 칸이 답하기 전에는 실자금 유래 데이터(개인정보든 금융 기록이든)를 저장하지 않는다.** 그 전까지 시뮬레이션은 `RETAIN_ALL_NO_AUTOMATIC_DELETION`이고 `MAX_OPERATIONS 500`은 보존 값이 아니다.
- **PENDING_OWNER_ACTION.** 법무·개인정보 담당과 회계·세무 담당 지명, 토스 계약/기술·Astra의 회신 확보.

### 3.7 upstream_adoption_receipt_review (CAP-07, CAP-11, CAP-15, CAP-16, CAP-19) — ADOPTED

두 노트가 적은 영수증을 규칙에 따라 판정한다. 판정은 노트에 기록된 값 기준이며 `9d0860c`에서 다시 검증하지 않았다.

| 영수증 (노트 기록) | 종류 | Capital 판정 |
|---|---|---|
| PR #140 `bb193efb…` 백엔드 PostgreSQL 17.11 | 결정 문서 병합 | 존재 확인. 목표 backend일 뿐 `k-stage5-durable-tx` 미병합이라 binding DEFERRED |
| PR #139 `6e54e723…` 보존 R1 | 결정 문서 병합 | 네 칸 구조 채택, 값은 멈춤. Capital이 다섯째 칸 추가 |
| PR #138 `a483ab17…` v5 crate 설계 | 결정 문서 병합 | `k-stage2-v5-impl` 미병합. 묶을 대상 없음 |
| PR #142 `b6cc9978…` 통합 (a) | 결정 문서 병합 | (a) DEFERRED. 조치 없음 |
| PR #130 AI 위임 계약+mock (`e2a029d` 포함) | 계약 초안+mock | 목표 binding만. **merge commit 미기록**, vendor 복사 미수행, 코드는 `NOT_BOUND` |
| `manifest.bootstrap-1.json` | BOOTSTRAP | 모양 참조일 뿐 binding 아님 |
| PR #125 RS-0, #126 TL ADR | 계약 초안, ADR | 식별자·범위 참조만 |

규칙: (R1) Capital 노트의 "ADOPTED"는 목표 binding 결정이다. 코드에서 "bound"가 되려면 adapter 노드, vendor manifest 핀, `docs/SEAMS.md` 행 변경이 필요하며 SEAMS에는 지금 ADOPTED 행이 없다. 따라서 `CAPITAL_UPSTREAM_BINDING.md`의 "ADOPTED(부분)"와 INTEGRATION.md의 "`AuthorizerPort` NOT_BOUND, receipt NONE"은 R1 아래서 모순이 아니며 어느 쪽 문구도 고치지 않는다. (R2) repo·PR·merge commit SHA·경로·포함 commit 중 하나라도 없으면 영수증은 INCOMPLETE이고 상태를 올리지 않는다. (R3) 결정 문서 병합은 후손 기능의 채택이 아니다. (R4) Capital은 어떤 upstream 노드도 완료로 표시하지 않는다. (R5) G5는 병합된 계약과 실행 가능한 증거(SEMANTIC_CONFORMANCE manifest, 테스트)가 함께 있는 영수증만 받는다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "external-gate-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-10-17",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "scope": "KIX-CAPITAL simulation and product design only; docs only; not an offer; no real money; production, real funds and public deployment NOT_AUTHORIZED; legal, tax, accounting and licensing content are working assumptions pending professional review; money, deploy, secrets and billing steps are PENDING_OWNER_ACTION for JunTae and are never executed by the loop; no upstream contract is claimed adopted without a real upstream receipt",
  "delegation": "2026-10-08 18:25 KST JunTae Park delegated financial terms, settlement policy, upstream binding and accounts/tax/legal to Fable; 2026-10-14 07:24 KST docs-only external gate decision delegated to Sonnet 5.5 xhigh",
  "bases": {
    "capital_main": "663b492",
    "kix_protocol_main_as_supplied": "9d0860c (supplied by supervisor; not re-verified in this session)",
    "vendor_pin_commit": "7481b0e16ce9b903abbffa62249bb91cd9e63cfe",
    "not_read": "CAPITAL_FINANCIAL_TERMS.md and the overlay, shadow, demo-book, artifact-bundling and overlay-digest-export notes were outside the allowed read set; no value is copied from them"
  },
  "gate_order": [
    "G1 legal applicability opinion (counsel designated by JunTae)",
    "G2 lender entity or licensed partner lender confirmed (after G1)",
    "G3 accounting and tax sign-off (after G2) in parallel with G4 IdP and KYC vendor (after G2)",
    "G5 upstream receipts closed (stage5 durable tx, stage7 authenticated export, SEMANTIC_CONFORMANCE tuple, fin-ledger-contract); runs in parallel from now, must close before G7",
    "G6 public endpoint and TLS (optional for a desk-only pilot; only after G4)",
    "G7 f04-real-funds-lift-criteria user-merged and explicit JunTae approval"
  ],
  "never_claimed": {
    "real_funds_moved": false,
    "production_deployed": false,
    "public_endpoint_live": false,
    "credentials_configured": false,
    "signing_key_created": false,
    "lender_entity_formed": false,
    "licence_obtained": false,
    "kyc_vendor_contracted": false,
    "professional_signoff_obtained": false,
    "retention_numbers_set": false,
    "upstream_contract_adopted_without_receipt": false
  },
  "entries": {
    "real_funds_pilot": {
      "status": "NOT_AUTHORIZED",
      "value": null,
      "target": {
        "shape": "B2B only; organizer legal entity borrower; advance recovered by set-off against settlement distribution; operator-desk only with two-person rule; AI propose-only; no investors, no claim purchase, no token collateral",
        "caps": "owner-supplied and never above the simulated CAPITAL-TERMS-V1 ceilings; no number is set by this note",
        "entry_criteria": ["G1 to G5 closed with real receipts", "bank and PG observation bound (CAP-14)", "provider merchant scope for resale and financial funds confirmed", "UNKNOWN never auto-retried; silence is not proof of non-use", "stop authority named", "f04-real-funds-lift-criteria user-merged and explicit JunTae approval"]
      },
      "blocked": ["any funds movement", "funds_executed true", "license_granted true", "regulated_product true"],
      "pending_owner_action": ["open and decide f04-real-funds-lift-criteria", "designate funding source and bank account", "approve pilot caps and stop authority"],
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-11", "CAP-14", "CAP-19", "CAP-20"],
      "rationale": "Model 1 separates reservation, payment confirmation and chain issuance and the chain does not guarantee bank funds, so Capital cannot run real funds before external bank and PG observations are bound; upstream keeps real funds locked and the provider merchant scope for resale and financial funds is unconfirmed. The pilot shape and entry criteria are decided now; amounts, funding and go-live are owner actions.",
      "provisional": true,
      "basis": "PENDING_OWNER_ACTION",
      "consumer": "none locally; GET /api/decisions reports status only"
    },
    "licensed_lender_entity": {
      "status": "UNDETERMINED",
      "value": null,
      "target": {
        "route": "CAPITAL-LICENCE-ROUTE-V1: dedicated KIX Capital lending entity registered as money lender (primary); licensed partner lender with KIX Capital as platform and servicer (alternative)",
        "g2_selection_rule": "choose primary when KIX Capital must control pricing, two-person rule and recovery waterfall; choose alternative only if registration timeline or capital requirement blocks, accepting intermediary registration and partner or PG restrictions",
        "code_boundary": "Capital code is never the lender of record; no entity name is written into the repository until the entity exists"
      },
      "blocked": ["license_granted true", "regulated_product true", "claim purchase (CAP-03 stays NOT_OFFERED)"],
      "pending_owner_action": ["designate legal counsel", "commission G1 applicability opinion", "confirm G2 route", "form and register the entity or sign the partner agreement"],
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-03", "CAP-13", "CAP-15"],
      "rationale": "The route was decided in the accounts-tax-legal note and is reaffirmed with a selection rule, but entity formation, registration, capital and counsel are paid human acts and the legal applicability judgment is pending professional review.",
      "provisional": true,
      "basis": "PENDING_OWNER_ACTION",
      "consumer": "none locally"
    },
    "idp_kyc_vendor": {
      "status": "UNDETERMINED",
      "value": null,
      "target": {
        "order": "after G2 because the KYC and AML duty-bearer is the lender entity",
        "criteria": ["contract holder is the lender entity, not Capital code", "Capital receives attested facts only (kyc_status, verified_at, provider_ref), never raw personal data", "human principals via OIDC-style bearer verified for issuer, audience, expiry and kix_role, shared with Commerce and the gate", "deletion requests handled at the vendor", "client secrets and signing keys never in repository, notes, fixtures or logs", "agent lane stays propose-only regardless of IdP"],
        "vendor_name": "not chosen"
      },
      "blocked": ["identity BOUND", "authentication BOUND", "kyc_executed true"],
      "pending_owner_action": ["select vendor after G2", "sign contract and accept billing", "create test tenant and issue API keys held in the owner secret store"],
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-19"],
      "rationale": "Selecting a vendor before the lender entity inverts the decision order recorded in the upstream-binding note; criteria and order are decided here while vendor choice, contract, billing and credentials require the owner.",
      "provisional": true,
      "basis": "PENDING_OWNER_ACTION",
      "consumer": "AuthorizerPort (NOT_BOUND)"
    },
    "public_endpoint_tls": {
      "status": "NOT_AUTHORIZED",
      "value": null,
      "target": {
        "v1": "loopback 127.0.0.1 only; Capital terminates no TLS and holds no certificates or keys",
        "ingress": "operator-owned reverse proxy only, opened after G4 because a request without a token currently receives the organizer token",
        "first_pilot": "operator-desk only, no public endpoint; public organizer self-service is post-pilot",
        "artifact": "capital-<version>.pyz stays LOCAL_SIMULATION_ARTIFACT, signed false, published false; public publication stays NOT_AUTHORIZED until the upstream owner grants a distribution licence because the artifact bundles vendored upstream bytes and upstream README grants none; DEV HMAC is never presented as a signature"
      },
      "blocked": ["public deployment", "TLS termination in Capital", "artifact publication", "release signing"],
      "pending_owner_action": ["domain, DNS, certificates, hosting account and billing", "licence decision for vendored upstream bytes", "release signing key creation"],
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-15", "CAP-20"],
      "rationale": "Local roles are self-selected and a tokenless request is organizer, so exposing the server before real authentication would make every caller an organizer; TLS and keys are secrets and deployment is spend, both owner actions.",
      "provisional": true,
      "basis": "PENDING_OWNER_ACTION",
      "consumer": "none locally"
    },
    "accounting_tax_signoff": {
      "status": "UNDETERMINED",
      "value": null,
      "target": {
        "package_scope": ["CAPITAL-COA-V1 and V1-to-COA mapping", "CAPITAL-REVREC-V1 including the 9700 suspension after default", "CAPITAL-TAX-V1 including the VAT-exempt financial service assumption, withholding_rate_bps and BTD memos", "CAPITAL-LICENCE-ROUTE-V1 applicability", "retention numbers"],
        "record_format": "reviewer name and qualification, date, git blob SHA of each reviewed note, scope and outcome (APPROVED, APPROVED_WITH_CHANGES, REJECTED), stored as a pointer in a later decision note and never as a code constant; any edit to a reviewed blob voids the sign-off",
        "agent_output": "never counts as a sign-off"
      },
      "blocked": ["accounting_policy other than SYNTHETIC_UNADOPTED", "tax or legal or operating_ledger BOUND", "labeling any output as a tax filing or financial statement"],
      "pending_owner_action": ["designate accountant and tax adviser", "engage them and accept fees", "supply withholding_rate_bps"],
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-13", "CAP-14", "CAP-15"],
      "rationale": "The accounting, revenue and tax values are working assumptions that only a designated professional can sign; the scope and record format are decided here so a later sign-off is a pointer, not a redesign.",
      "provisional": true,
      "basis": "PENDING_OWNER_ACTION",
      "consumer": "ProjectionPort and export labels (unchanged)"
    },
    "retention_period": {
      "status": "UNDETERMINED",
      "value": null,
      "target": {
        "slots": ["legal_dispute_hold", "business_reconciliation", "retry_support", "memory_residency", "tax_accounting_records"],
        "owners": "legal and privacy owner and tax and accounting owner designated by JunTae; Toss contract and technical for business_reconciliation; Astra for retry_support and memory_residency",
        "real_data_precondition": "no data originating from real funds, personal or financial, is stored until all five slots hold owner-supplied values and the legal and dispute hold slot is answered",
        "interim": "simulation keeps RETAIN_ALL_NO_AUTOMATIC_DELETION; MAX_OPERATIONS 500 is a demo bound; provider-published values such as a 15 day idempotency key are not retention periods"
      },
      "blocked": ["any retention duration, bound or timer", "automatic deletion"],
      "pending_owner_action": ["designate legal and privacy owner", "designate tax and accounting owner", "obtain Toss and Astra replies"],
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-14", "CAP-15"],
      "rationale": "Upstream R1 left retention values stopped and requires legal replies; this note adds only the owner map and a precondition that keeps real data out until the numbers exist.",
      "provisional": true,
      "basis": "PENDING_OWNER_ACTION",
      "consumer": "export manifest retention_policy (five named slots, no durations)"
    },
    "upstream_adoption_receipt_review": {
      "status": "ADOPTED",
      "value": {
        "meaning": "Capital adopts these review rules and verdicts; no upstream contract is adopted by this entry",
        "rules": {
          "R1": "ADOPTED in a Capital note is a target binding decision; bound in code requires an adapter node, a vendor manifest pin and a docs/SEAMS.md row change, and SEAMS has no ADOPTED row today",
          "R2": "a receipt needs repo, PR, merge commit SHA, path and containing commit; a missing field makes it INCOMPLETE and the status is not raised",
          "R3": "a decision-document merge is not adoption of descendant features",
          "R4": "Capital never marks an upstream node complete",
          "R5": "gate G5 accepts only a merged contract together with executable proof such as a SEMANTIC_CONFORMANCE manifest and tests"
        },
        "verdicts": {
          "PR 140 bb193efb5d238581096372c8a20bee1271dfe4df": "backend target PostgreSQL 17.11 only; stage5 binding DEFERRED until k-stage5-durable-tx merges",
          "PR 139 6e54e723d582e88ae89df309eb144d4664c7e1f5": "four retention slots adopted structurally, values stopped; Capital adds a fifth slot",
          "PR 138 a483ab1777ad0c3e15ff71798822cbf6b3666f83": "k-stage2-v5-impl not merged; nothing to bind",
          "PR 142 b6cc9978c64b1ff54f822ea930424b5d78dfca2a": "integration (a) DEFERRED; no action",
          "PR 130 AI delegation contract and mock": "INCOMPLETE receipt: merge commit not recorded, vendor copy not made, code stays NOT_BOUND",
          "manifest.bootstrap-1.json": "shape reference only, BOOTSTRAP",
          "PR 125 and PR 126": "identifier and scope references only"
        },
        "findings": ["PR 130 merge commit SHA is unrecorded", "receipts were judged against the commits each earlier note recorded and were not re-verified at kix-protocol 9d0860c", "the upstream-binding note calling the agent lane ADOPTED and INTEGRATION.md calling AuthorizerPort NOT_BOUND are consistent under R1 and neither wording is changed"]
      },
      "blocked": ["marking any seam ADOPTED without adapter node, byte pin and receipt", "marking any upstream node complete"],
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-07", "CAP-11", "CAP-15", "CAP-16", "CAP-19"],
      "rationale": "Earlier notes already list the receipts they found; reviewing them against a single rule set, and recording the unrecorded PR 130 merge commit and the unverified base drift as findings, needs no spend or secret and keeps every adoption claim tied to a real receipt.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "consumer": "docs/SEAMS.md and GET /api/readiness wording (separate sync node)"
    }
  }
}
```

## 5. 수용 기준 매핑

- `docs/decisions/CAPITAL_EXTERNAL_GATES.md`에 `capital-decision-v1` 블록이 정확히 하나 있다. 실행 가능한 답이 없는 여섯 항목은 `UNDETERMINED` 또는 `NOT_AUTHORIZED`이고 `basis = PENDING_OWNER_ACTION`이다. 이 세션은 읽기 전용이라 `python3 scripts/decision_ledger.py`를 **실행하지 못했다**. 통과 여부는 감독자가 파일을 쓴 뒤 확인해야 한다.
- 이 노드에 의존하는 노드는 없다. 어떤 upstream 계약도 영수증 없이 채택됐다고 쓰지 않았고, 영수증이 불완전한 곳(PR #130)은 그렇게 적었다.
- production, 실자금, 공개 배포는 `NOT_AUTHORIZED`다. `never_claimed`의 모든 플래그가 거짓이다. 돈, 배포, 시크릿, 서명, 과금은 `PENDING_OWNER_ACTION`으로 JunTae에게 남겼다.

## 6. Open risks

1. **관문 순서는 설계 가정이다.** 법무가 인허가 신청에 KYC 벤더나 회계 서명을 먼저 요구하면 순서를 바꿔야 한다.
2. **현재 loopback 경계는 인증이 아니다.** 토큰 없는 요청이 organizer 토큰을 받는다. 어떤 형태로든 외부에 노출하는 순간 위험하므로 G4 전 공개는 금지다.
3. **vendor 바이트의 공개 배포 라이선스가 없다.** 아티팩트 게시 계획이 생기면 JunTae의 라이선스 결정이 먼저다.
4. **upstream 기준 커밋이 노트마다 다르다**(`e2a029d`, `51d8380`, `9d0860c`, README의 `d5b9f2d`). 영수증은 `9d0860c`에서 재검증되지 않았고 vendor pin `7481b0e1…`이 현재 upstream과 얼마나 벌어졌는지도 확인하지 않았다.
5. **읽지 않은 선행 노트.** `CAPITAL_FINANCIAL_TERMS.md`와 다섯 결정 노트 사이에 충돌이 있어도 이 문서는 탐지하지 못한다. 특히 artifact-bundling 결정이 게시 문구와 만날 수 있다.
6. **토스 가맹 범위(리셀·금융 대금)가 미확인**이라 정산 상계 기반 회수 자체가 막힐 수 있다.
7. **법률·세무·회계 내용 전체가 작업 가정**이다. 대부업법 경로와 면세 가정이 틀리면 §3.2, §3.5의 범위가 바뀐다.

## 7. 후속 작업

- **감독자.** 이 파일을 쓰고 `python3 scripts/decision_ledger.py`를 실행한다. 읽기 전용 git으로 §3.7 영수증을 `9d0860c` 기준으로 재검증하고 PR #130의 merge commit SHA를 기록한다(별도 노드, 이 노드에 의존하지 않음).
- **JunTae (PENDING_OWNER_ACTION, 우선순위 순).** (1) 법무·개인정보 담당과 회계·세무 담당 지명 (2) G1 법무 의견 의뢰 (3) G2 대주 법인 또는 파트너 경로 확정 (4) vendor된 upstream 바이트의 공개 배포 라이선스 결정(게시 계획이 있을 때만) (5) G2 뒤 IdP·KYC 벤더 선정과 시크릿 보관 (6) 토스 가맹 범위와 Astra 보존 값 회신 확보 (7) G1~G5가 닫히면 `f04-real-funds-lift-criteria` 개시 (8) 파일럿 한도와 중지 권한자 승인.
- **별도 노드 후보 (이 노드 의존 아님).** `readiness` release 그룹과 CAP 행의 차단 사유 문구가 이 노트를 인용하도록 sync, `agent-grant-authorizer-adapter`(PR #130 merge SHA 기록 뒤).
