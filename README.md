# KIX Capital

로컬 합성 데이터로 Capital의 정산 근거 → 제안 → 모의 승인 → 노출 기록 → 상환 메모 → 종결·재생 검증을 연결하는 개발용 제품입니다. **전체 Capital 청사진 완료·실대출·신용심사·운영 출시가 아닙니다.**

## 실행

Python 3.10 이상, runtime 패키지 설치나 DB 없이 실행합니다.

```sh
python3 -m capital.server
# http://127.0.0.1:8765
# 기본값은 프로세스 메모리입니다. 재시작하면 제안과 receipt가 사라집니다.

python3 -m capital.server --workspace ./var/capital-workspace
# 옵트인 로컬 JSON 작업공간. 재시작 시 receipt·저널을 복원하고 instance_id는 새로 발급합니다.
# state/export의 durable 값은 LOCAL_FILE_WORKSPACE 입니다. stage5 내구 거래가 아닙니다.
```

## 로컬 아티팩트

`python3 scripts/build_release.py --out dist`가 체크아웃 없이 실행하는 stdlib zipapp `dist/capital-<version>.pyz`를 만듭니다. 버전은 `capital/__init__.py`의 `__version__` 하나만 사용합니다. `--version`이 `kix-capital <version>`을 출력하고, `GET /api/state`의 `version`도 그 값입니다.

이 파일은 서명되지 않은 로컬 시뮬레이션 아티팩트입니다 (`LOCAL_SIMULATION_ARTIFACT`, `signed: false`, `published: false`). PyPI 게시, 외부 서명, 배포가 아닙니다. 같은 인터프리터에서 두 번 빌드하면 SHA256이 같습니다. 플랫폼 간 재현을 주장하지 않습니다.

```sh
python3 scripts/build_release.py --out dist
python3 dist/capital-0.1.0.pyz --version
python3 dist/capital-0.1.0.pyz
python3 dist/capital-0.1.0.pyz --workspace ./var/capital-workspace
python3 scripts/smoke_release.py dist/capital-0.1.0.pyz
```

최신 Chromium/Chrome/Edge에서 열어 주세요. 주소는 `127.0.0.1`이며 외부 host/Origin 요청을 거절합니다. 기본 메모리 상태는 서버 재시작 시 사라집니다. `--workspace`는 개발용 단일 파일이며 DB·inbox/outbox·다른 호스트 fencing이 아닙니다. 손상되거나 잠긴 파일은 빈 장부로 시작하지 않고 쓰기를 거절합니다. 금액·역할·공연은 합성 fixture만 사용하며 실명·계좌·신용정보 입력란이 없습니다.

## 구현과 경계

- Capital 전용 loopback API와 웹 화면, 포트폴리오, fixture-v1 세 건과 `CAPITAL-DEMO-BOOK-V1` 합성 북 10건(`SYNTHETIC_FIXTURE_PROFILE`, pinned `SettlementMachine` replay만으로 만든 대형 액면)의 정산/환불 fixture.
- Protocol의 F04 상태기계를 정확한 소스 SHA 및 파일 hash에 고정한 로컬 참조 adapter. 산술·원본 FSM은 수정하지 않습니다.
- 같은 operation의 최초 결과/충돌 검사, 공유 액면 경합, 부분 상환·미이행·종결, 재생 일치.
- 응답 유실 시 UNKNOWN, 브라우저 새로고침 뒤 원 receipt 조회, 새 쓰기 차단. 자동 재시도 없음.
- API는 별도의 `UNBOUND` 목 draw를 허용하는 F04 의미를 유지합니다. 화면의 기본 여정은 정산 결합을 먼저 요구합니다.
- F01–F03 고정 시나리오 9개·35단계: 부족 현금의 배정 순서 비교, 부분/전액 환불, 회수 의무, 중복/상충 관측, 늦은 현금. 별도 메모리에서 재생하며 작업 중 제안을 변경하지 않습니다.
- 선택 제안의 읽기 전용 인출 사전점검과 20개 청사진 요구사항의 구현/결정/연동 선행 필터.
- 잠정 금융 조건 오버레이(`GET /api/terms`). `docs/decisions/CAPITAL_FINANCIAL_TERMS.md`의 ADOPTED 값만 읽고, 라벨은 simulated overlay이며 청약·벤더 FSM 산술·실자금이 아닙니다. 노트가 없으면 `terms not bound`입니다. zipapp은 `docs/`를 담지 않아 그 실행은 `NOT_BOUND`입니다.
- 읽기 전용 상환 배정 견적(`GET /api/terms/{advance_id}/allocation`). 가상의 `cash`·`as_of_day`만 받아 노트의 결정 순서(DEFAULT_INTEREST → INTEREST → PRINCIPAL)로 나누고, 계약이자·만기 후 연체이자를 정확한 유리수에서 1원 내림으로 보여 줍니다. `fsm_repay`는 원금 몫이 있을 때만 들고, `close_ready`는 가상 지급 뒤 잔액·이자가 모두 0일 때만 true입니다. FSM 저널·수령·예약은 그대로이고 아무것도 저장하지 않습니다.
- 읽기 전용 상계·회수 제안 견적(`GET /api/terms/{advance_id}/setoff`). 결합된 불변 정산 조회에서 수익자 매핑 수취인 줄(CAPITAL-ALLOC-V1 상대방 수익 클래스)에 이미 배정된 현금만 세어 `min(미상환 노출, 그 현금)`을 제안하고 노트의 상환 순서로 나눕니다. 회수 의무 아래의 현금은 세지 않고 배정이 없으면 `ALLOCATION_NOT_OBSERVED`로 0을 보고합니다. `fsm_repay`는 원금 몫뿐이고 집행 권한은 노트의 사람 2인에 머뭅니다. `proposal_only`는 true이고 `applied`는 false이며 receipt·예약·`state_digest`·`operation_count`는 바뀌지 않습니다. 청약도 집행도 아닙니다.
- 읽기 전용 포트폴리오 조건 롤업(`GET /api/terms/portfolio`). 모든 모의 노출을 한 줄씩 보여 주고, 각 줄은 등급·가정 인출일 출처·만기일·만기 경과일·계약/연체 이자(정확한 유리수, 1원 내림)·연환산 총비용 bps와 노트의 `all_in_cost_cap_bps_annual`에 대한 `cap_check` PASS/FAIL을 담습니다. 합계 줄은 유리수를 먼저 더한 뒤 한 번만 내림합니다. 롤업은 의도적으로 질의의 가정 일수(`draw_day`, `as_of_day`)를 쓰며 `draw_day_source`(`QUERY_PARAMETER` 또는 `DEFAULT`)가 그 사실을 표시합니다. 기록된 시계는 오버레이 원장(`GET /api/overlay`)의 `sim_day`와 노출별 `draw_day`에 있고 롤업은 그것을 읽지 않습니다. 노트가 없으면 숫자 없이 `terms not bound`입니다. 이 롤업은 노출 버킷·집중도 한도·준비금·환불 충격 스트레스를 계산하지 않으며, 그것들은 `GET /api/risk`(기록된 `sim_day`, 질의 문자열 없음)에서 읽기 전용으로 봅니다.
- 시뮬레이션 오버레이 원장(`GET /api/overlay`, `POST /api/overlay/commands`). 조직자만 명시적 `advance_day`(`from_sim_day`→`to_sim_day`, CAS·단조 증가·1회 최대 366일)로 논리 시계 `sim_day`를 전진시키고, 같은 저장 한 번에 `CAPITAL-TERMS-V1`의 ACT/365 단리 이자 메모(등급은 인출 영수증의 `settlement_gate`, 만기 후 연체이자, 정확한 유리수의 누적 내림과 이월 잔액)를 게시합니다. 상환 배정 제안·읽기 전용 `close_ready`·유실 응답 조회(`?operation_id=`)를 제공하고, F04 저널·`state_digest`·`tests/golden/demo.json`은 바꾸지 않으며 FSM을 막지도 않습니다. 오버레이는 워크스페이스 envelope v2의 `overlay` 섹션에 저장되고 재시작 때 fold로 복원하며, 손상되면 fail-closed(`WORKSPACE_UNREADABLE`)이고 빈 오버레이로 대체하지 않습니다. 노트가 `NOT_BOUND`이면 `terms not bound`로 거절하고 아무것도 계산하지 않습니다. `capital/margin.py`가 모든 `advance_day`마다 `additional_margin` 규칙을 평가합니다(`GET /api/overlay`의 `margin` 블록, 행별 `margin`). 마진콜은 `outstanding > floor(eligible_face × advance_rate_bps / 10000)`인 첫 틱에 발화해 `cure_deadline = day + 5`를 기록하고, 부분 상환으로 한도 안에 들어오면 치유(`margin_cure`)가 오버레이 저널에 남으며, 미치유 시 `ACCELERATED`(`maturity := cure_deadline`, `default_eligible_day = maturity + 10 + 1`)가 되어 사람 운영자용 `DEFAULT_ELIGIBLE` 제안만 만듭니다. F04 `default`는 호출하지 않습니다. 워크스페이스 정산 조회는 불변이므로 거기서는 `checked: true`, `triggered: false`, `limit: FIXTURE_VIEWS_IMMUTABLE`로 표시하고 저널에 쓰지 않으며, 규칙은 일회용 `ScenarioReplaySource`(SIMULATED, F01–F03 시나리오 단계 재생)에서만 실제로 시험합니다. 연체이자·상각일을 가속 만기로 다시 잡는 재기준(rebase)은 `docs/decisions/CAPITAL_DEFAULT_RECOVERY.md`가 잠정 제품 결정(PROVISIONAL)으로 정했지만 아직 구현되지 않았습니다(`overlay-recovery-writeoff`). 그때까지 `interest_rebased`는 false입니다. 오버레이가 비어 있지 않으면 `GET /api/export/manifest`가 `KIX_CAPITAL_EXPORT_MANIFEST_V3`(일곱 섹션 + `overlay`/`overlaypart`)를 내고 `GET /api/reconciliation`에 `overlay_fold_digest_equals_persisted` 검사와 `scope.overlay_state_digest`가 조건부로 붙으며, 비어 있으면 V2 그대로입니다(`demo.json` 바이트 동일). 이자 지급 기록·회수 폭포는 아직 없습니다(`NOT_RECORDED`).
- 읽기 전용 포트폴리오 위험 분석(`GET /api/risk`, 라벨 SIMULATED, `projection:read`). 저널·오버레이 시계·결정 노트를 정수로만 접어 등급별 노출, 만기 버킷(0-30/31-60/61-90/>90일), 연체 경과, 수익자 집중도(HHI ‰와 U4 한도 사용률), 손실 준비금 요구액(노트 표 150/500/2500/10000 bps의 건별 내림 합, 회계 정책 아님), 고정 환불 충격 `[500, 1000, 2500, 5000]` bps 스트레스를 보여 줍니다. 아무것도 기록하지 않으며 마진콜은 가정입니다. 노트가 없으면 NOT_BOUND이고 숫자가 없습니다.
- 시뮬레이션 운영 데스크(`#desk`, 라벨 SIMULATED, 브라우저 전용이라 서버·계약·인가·골든 변경이 없습니다). 위험 요약 타일(`GET /api/risk`), `sim_day` 제어, 사례 타임라인, 서버가 사유를 붙인 다음 작업, 오버레이 원장 표를 한 화면에 보여 줍니다. `sim_day` 제어는 `POST /api/overlay/commands`의 `advance_day`를 한 번 보내며, 응답을 잃으면 `UNKNOWN`이고 자동 재시도 없이 `GET /api/overlay?operation_id=` 조회만 합니다. 사례 타임라인은 내보내기 매니페스트의 F04 저널과 오버레이 저널을 `after_journal_index`로 합치고 F04 행에 `sim_day`를 만들어 붙이지 않습니다. 다음 작업의 활성·비활성과 사유는 서버 값이며, 비활성은 `aria-disabled`이고 눌러도 명령을 보내지 않습니다. 심사 `DECLINE`은 자문일 뿐 승인을 막지 않습니다. 화면은 금액을 계산하지 않고 서버 숫자와 사유 문장만 보여 주며, 유일한 산술은 요청 형식이 요구하는 논리 시계 `to_sim_day = from_sim_day + 진행 일수`입니다. 역할별로 organizer는 전부 보고, auditor는 타일·원장·타임라인만 읽고 명령 조작은 숨겨지며(`overlay:command` 사유 한 줄), observer는 `projection:read` 금지 안내만 보고 데스크용 요청을 보내지 않습니다. 실자금·승인 화면이 아니며 사람 수용이 아닙니다.
- 잠정 배정 순서 시뮬레이터(`GET /api/policy`, `GET /api/policy/simulation`). `docs/decisions/CAPITAL_SETTLEMENT_POLICY.md`의 배정 순서만 일회용 장부의 고정 FSM에 적용합니다. 라벨은 simulated policy application이며 실행된 배분·은행 이동이 아닙니다. 환불 부담·수익 참여·채권 매입 등 고정 FSM이 표현하지 못하는 항목은 계산하지 않고 `UNSUPPORTED_BY_PINNED_FSM`으로 남습니다. 노트 §7의 그림자 계산은 별도 읽기 전용 경로 `GET /api/policy/shadow`(`capital/shadow.py`)에서만 합니다 — `SHADOW_NOT_APPLIED` 모드의 환불 부담 RC1–RC4(RC5는 리셀 해제로 라우팅)와 리셀 해제 RU1–RU3를 고정 벡터 위에서 계산하고, 고정 FSM에는 적용하지 않으며 모든 비집행 플래그는 거짓입니다. 노트가 없으면 `SHADOW_NOT_BOUND`입니다. `policy_adopted`는 false입니다. 노트가 없으면 `policy not bound`입니다. zipapp은 `docs/`를 담지 않아 그 실행은 `NOT_BOUND`입니다.
- 읽기 전용 심사 기록(`GET /api/underwrite/{advance_id}`). `docs/decisions/CAPITAL_FINANCIAL_TERMS.md`의 `underwriting_depth`(EVIDENCE_RULES_V1)가 정한 여섯 검사 U1–U6을 노트 순서대로 평가한 `SIMULATED_UNDERWRITING_RECORD`입니다. 라벨은 `simulated underwriting record — rule checks only, not an approval`이고, `proposal`(`APPROVE`/`DECLINE`)은 제안일 뿐 승인이 아니며 `approve`는 호출자 결정으로 남습니다. `kyc_executed`와 `underwriting_executed`는 false이고 receipt·예약·`state_digest`·`operation_count`는 바뀌지 않습니다. 권한은 `projection:read`입니다. 노트가 없거나 필요한 항목이 ADOPTED가 아니면 숫자 없이 `NOT_BOUND`(`terms not bound`)입니다. zipapp은 `docs/`를 담지 않아 그 실행은 `NOT_BOUND`입니다. 웹 화면은 조건 오버레이, 정책 비교표, 이 U1–U6 심사 기록을 읽기 전용 패널로 보여 줍니다.
- 수락된 저널과 불변 정산 fixture를 고정 합성 계정표로 읽는 로컬 복식 투영 후보. `accounting_policy`는 `SYNTHETIC_UNADOPTED`이고, 세무·법무·운영 원장은 `NOT_BOUND`이며 `fin-ledger-contract`를 채택하지 않습니다.
- 읽기 전용 대사 예외와 다섯 구분 명세서. 둘 다 로컬 진단입니다. 은행·PG·제공자 관측, source cut, 제공자 인증 완전성은 `NOT_BOUND`입니다. 최초 판매와 리셀 매출은 합산하지 않고 `actual_paid`는 `NOT_BOUND`입니다.
- export manifest(`GET /api/export/manifest`)는 오버레이가 비어 있으면 `KIX_CAPITAL_EXPORT_MANIFEST_V2`, 비어 있지 않으면 `overlay` 섹션을 더한 `KIX_CAPITAL_EXPORT_MANIFEST_V3`이며, 섹션별 SHA-256과 content digest를 담습니다. 기본 서명은 `NOT_BOUND`입니다. `--dev-hmac`은 작업공간 디렉터리에 mode 0600인 `DEV_ONLY` HMAC 키를 만들며, 그 키는 무결성만이고 인증이 아니며 응답이나 로그에 나오지 않습니다. `python3 -m capital.verify FILE --key-file K`가 오프라인에서 섹션 해시, digest, 서명을 다시 계산합니다. cursor·watermark·source cut·외부 키·보존 기간 값은 없고(retention_policy는 주인만 있는 다섯 빈 칸), stage7 인증 export가 아닙니다. v1 `GET /api/export`는 그대로입니다. 가져오기·재개 경로는 없습니다.
- 원본 목 정산 조회·노출·현금·회수 의무는 서로 다른 의미입니다. 합계를 실제 은행 잔액으로 표시하지 않습니다.
- 로컬 인가 경계: 합성 역할 organizer/auditor/observer는 `POST /api/session`으로 자기선택되고 역할별 루프백 토큰에 묶입니다. 이것은 인증이 아닙니다. 계정·비밀번호·실명 신원은 없습니다. observer는 export와 projection을 읽지 못하고 auditor는 읽을 수 있습니다. `agent`는 화면 밖 SIMULATED QUERY/PROPOSE 레인입니다. 고정된 초안 허용 목록의 도구 다섯(`query_grant`, `query_subject`, `propose_action`, `withdraw_proposal`, `propose_grant_change`)만 열리고 `execute`는 항상 `403 EXECUTE_AUTHORITY_DISABLED`입니다. 제안은 HUMAN_PENDING이고 effects_executed는 false입니다. 실제 IdP·KYC·자격증명·AgentGrant/ActionPermit은 NOT_BOUND입니다.
- 경로별·역할별 인가 표(`tests/auth_matrix.json`). 등록된 모든 경로를 organizer·auditor·observer·agent·토큰 없는 호출자로 나눠 기대 상태 코드와 권한을 고정했고, 루프백 서버로 모든 칸을 확인합니다. `python3 scripts/auth_matrix.py --write`가 표와 `docs/INTEGRATION.md`·운영 핸드북의 생성 블록을 다시 쓰고 `--check`가 어긋남을 잡습니다. 경로·권한·역할은 바뀌지 않았고 표는 합성 자리표시자입니다. 신원과 인증은 `NOT_BOUND`입니다.
- export manifest 변조 코퍼스(`tests/vectors/manifest/`). 고정된 manifest 12개입니다. 정상본은 서명 없는 `unsigned.json`과 `DEV_HMAC_SHA256`으로 서명한 `dev-hmac.json`이고, 나머지는 섹션 일곱 곳의 한 바이트 변조 `section-<id>.json`, `content-digest.json`, `signature.json`, 중간에서 잘린 `malformed.json`입니다. 각 파일은 `python3 -m capital.verify FILE --key-file K`의 기대 결과를 고정합니다. 변조본은 `SECTION_HASH_MISMATCH:<id>`, `CONTENT_DIGEST_MISMATCH`, `SIGNATURE_MISMATCH`, `MANIFEST_UNREADABLE`로 거절되고 `dev-hmac.json`의 서명 상태는 `VERIFIED_DEV_ONLY_INTEGRITY`입니다. `tests/vectors/export-dev.key`는 `dev-hmac.json`용 고정 합성 `DEV_ONLY` 키로, 자격증명이 아니라 테스트 벡터 자료입니다. git에는 0644로 저장되고 검증기는 0600인 키 파일만 읽으므로 복사해 `chmod 0600`한 뒤 `--key-file`에 넘깁니다. 공유 HMAC 키는 무결성만이고 인증이 아니며 stage7 인증 export가 아닙니다. 코퍼스는 `seed_demo` 이야기와 고정 instance id에서 만든 `SIMULATED` 데이터이고 `python3 scripts/manifest_vectors.py --write`가 같은 바이트로 다시 씁니다. `python3 scripts/manifest_vectors.py --check`는 바이트를 비교해 어긋남·누락·예상 밖 파일이 있으면 1로 끝납니다.
- 오프라인 작업공간 감사(`python3 -m capital.verify --workspace DIR`). 서버 없이 `DIR/workspace.json` 바이트를 직접 읽어 봉투 모양·중복 키·`payload_sha256`·저널 재생 `state_digest`·receipt↔저널 지문과 대사 여섯 검사(`GET /api/reconciliation`과 같은 함수)를 다시 계산하고 검사마다 `MATCHED`/`MISMATCH`를 찍습니다. 첫 어긋남에서 1로 끝나고 이유는 `WORKSPACE_UNREADABLE` 또는 `RECON_MISMATCH`입니다. 잠금을 잡지 않고 아무것도 쓰지 않아 살아 있는 서버가 잡고 있는 파일도 읽기만 하며, 복구·가져오기·재개 경로는 없습니다. `tests/vectors/workspace/`의 고정 변조 코퍼스는 `python3 scripts/workspace_vectors.py --write`가 같은 바이트로 다시 쓰고 `--check`가 어긋남·누락·예상 밖 파일에 1로 끝납니다. 라벨은 `SIMULATED`/`LOCAL_ONLY`이고 CAP-11은 `NOT_BOUND`입니다.
- 금융 벡터 팩(`tests/vectors/finance_vectors.json`, 형식 `KIX_CAPITAL_FINANCE_VECTORS_V1`, 라벨 `SIMULATED`). 일곱 그룹이 각각 `FINANCE_PENDING_NODES` 후보 하나(`fin-ledger-contract`, `fin-double-entry-projection`, `fin-observation-reconciliation`, `fin-multi-payee-refund-proof`, `fin-credit-exposure-reconciliation`, `fin-consistent-accounting-export`, `fin-catalogue-read-model`)의 입력으로 `INPUT_VECTOR_CANDIDATE` 역할을 합니다. `fin-finance-closeout`은 `build/acceptance-evidence.json`이 커밋하지 않는 실행별 파일이라 `vectors`가 null이고 그 이유를 `reason`에 적었습니다. `semantic_conformance`는 false이고 `upstream_nodes_completed`는 비어 있습니다. `SEMANTIC_CONFORMANCE`가 아니며 어떤 upstream 노드도 완료하지 않고, 회계 정책을 채택하거나 정산 정책을 고르지도 않습니다. 후보는 자기 upstream 완료 증거가 있어야만 이 벡터를 채택할 수 있습니다. `python3 scripts/finance_vectors.py --write`가 다시 쓰고 `python3 scripts/finance_vectors.py --check`가 바이트를 비교해 어긋남이나 누락이면 1로 끝나며, 고정된 로컬 코드가 여전히 같은 바이트를 낸다는 뜻일 뿐 의미 적합성의 증거가 아닙니다.
- AI 위임 클레임 표(`tests/agent_claims.json`)와 실행 스크립트(`scripts/agent_claims_check.py`). 각 행은 고정된 upstream 초안 `docs/contracts/AI_DELEGATION_AUTHORITY.md`(kix-protocol `e2a029d8ac3af7575888dac22fc4bf173ebec232`)의 클레임 문자열·절·needle을 인용하고, `capital/agent_claims.py`의 검사가 SIMULATED agent lane을 loopback facade로 실행합니다. 표의 `HUMAN_PENDING`은 초안 `PROPOSED` 메모 단계의 Capital 라벨이고, 실행 거절 `EXECUTE_AUTHORITY_DISABLED`(403)는 초안의 항상 거절 `attempt_execution`을 반영합니다. organizer 명령은 pending `proposal_id`를 receipt에 인용으로 새기고 메모를 실행하지 않습니다. `--protocol-dir` 없이는 `SKIPPED`이며 통과가 아니고, `upstream-claims` 수용 단계가 이 스크립트를 두 번째 명령으로 실행해 라벨 `CLAIM_CONFORMANCE` 아래 합산합니다. `ai_delegation_mock.py`는 vendor하지 않고 ActionPermit·EXECUTE·인가 변경은 범위 밖입니다.
- 읽기 모델 클레임 표(`tests/read_model_claims.json`)와 실행 스크립트(`scripts/read_model_claims_check.py`). 각 행은 고정된 upstream 초안 `docs/contracts/READ_MODEL_QUERIES.md`(kix-protocol `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`, vendor 핀과 동일)의 `get_credit_advance`(§2.12)·`get_credit_claim`(§2.13)·비변경 술어(§8)를 인용하고 `capital/read_model_claims.py`의 검사가 기존 읽기 표면을 loopback facade로 실행합니다. 매핑은 어댑터로 명시합니다: `get_credit_advance`는 `GET /api/state`의 case 뷰(그대로 `CreditMachine.view` dict)에, `get_credit_claim`은 in-process `CreditMachine.view_claim`에 대응하고, `GET /api/evidence`는 §2.11 정산 claim 객체라 대응하지 않습니다. upstream 쿼리 이름을 구현하지 않고 경로도 추가하지 않습니다. 모든 검사는 §8 비변경 가드(canonical_state·저널 길이·오버레이 digest·operation_count) 아래 읽기를 실행해 변경이 있으면 그 클레임이 실패합니다. `--protocol-dir` 없이는 `SKIPPED`이며 통과가 아니고, `upstream-claims` 수용 단계가 이 스크립트를 세 번째 명령으로 실행해 라벨 `CLAIM_CONFORMANCE` 아래 합산합니다.
- 결정 노트 요약(`GET /api/decisions`). `docs/decisions/`의 `capital-decision-v1` 블록마다 `decision_id`, `status`, `provisional`, `version`, 항목별 상태 지도만 보여 줍니다. 값은 복사하지 않고 `scripts/decision_ledger.py`와 같은 파서를 씁니다. 권한은 `reference:read`이며 agent는 거절됩니다. `docs/`가 없는 `.pyz`에서는 `NOT_BOUND`와 reason만 돌려줍니다. 채택이 아니라 노트가 말하는 것의 요약입니다.
- 프로세스 로컬 관측(`GET /api/metrics`, `GET /api/health`). 카운터, 고정 밀리초 지연 버킷, uptime, 작업공간 상태만 보여 준다. 라벨은 `SIMULATED` / `LOCAL_OBSERVABILITY`이고 exporter, tracing, alerting, network sink는 `NOT_BOUND`다. `--event-log FILE`은 크기 제한 JSONL이며 본문과 토큰을 쓰지 않는다. 카운터는 fingerprint와 `state_digest`에 들어가지 않고 프로세스가 끝나면 사라진다. 정확성, 내구성, 실자금의 증거가 아니다.
- 이벤트 로그 오프라인 요약(`python3 -m capital.events FILE --summary`). 서버 없이 파일 하나만 읽어 줄마다 정확히 다섯 필드(`time`, `route`, `status`, `code`, `operation_id`) 모양을 검사하고, 경로·상태·코드별 건수와 `without_code`, 첫·마지막 UTC 시각을 한 줄 JSON으로 낸다. 어긋난 줄이 있으면 그 줄의 1부터 세는 번호를 stderr에 붙여 0이 아닌 코드로 끝나고, 빈 파일은 0건으로 요약한다. 바이트만 읽고 아무것도 쓰지 않는다. `dropped`·`errors`는 프로세스 카운터라 파일에서 관측되지 않아 null과 `NOT_OBSERVABLE_OFFLINE`로 표시하고 `GET /api/metrics`의 `counters.event_log`를 가리킨다. 이벤트 로그 형식·크기 한도·서버 동작은 바꾸지 않는다. exporter, tracing, 감사·금융 증거가 아니다.
- 자산은 KRW 하나만 선언합니다. `GET /api/state`와 export manifest `source_pin`의 `assets`가 `{namespace: fiat, reference: KRW, decimals: 0, max_atoms: 1000000000000}` 한 건이고, 명령 본문의 선택 필드 `asset`이 이와 다르면 `400 ASSET_MISMATCH`로 적용 전에 거절하며 저널·receipt를 남기지 않습니다. 금액은 정수이고 FX·교차 자산 합산·asset registry는 없습니다(PROVISIONAL per `docs/decisions/CAPITAL_UPSTREAM_BINDING.md` §3.6).
- 추가형 `CAPITAL-COA-V1` 후보 투영은 `GET /api/projection?mode=coa-candidate`로만 읽습니다(`capital/coa.py`, chart `SIMULATION_FIXED_V2`). 4자리 코드와 차원(`asset`, `advance_id`, `claim_id`, `sim_day`, `chart_version`, `terms_version`), KRW AssetSpec 한 개, 오버레이 이자 전기(1110/4100/4110, DEFAULTED 이후는 9700 메모), 청구 액면은 9100/9110 메모에만 둡니다. `GET /api/reconciliation?mode=coa-candidate`만 `coa_candidate_totals_vs_v1`, `interest_ledger_vs_projection` 두 검사를 더합니다. V1 응답·manifest·golden은 그대로이고 `accounting_policy`는 `SYNTHETIC_UNADOPTED`, `tax`는 `NOT_BOUND`입니다. 수익인식·세무 채택이 아닙니다.
- 로컬 facade 계약은 `capital-local-facade/1` (`capital/contract/facade-v1.json`)입니다. `ProducerPort`의 기본 구현은 고정 FSM wrapper입니다. 양성·음성 vectors는 SEMANTIC_CONFORMANCE가 아니고, CAP-16 exact tuple은 NOT_BOUND입니다. 옵트인 `--producer gate-fake`는 127.0.0.1의 `LOCAL_FAKE_GATE`(`scripts/fake_gate.py`)에만 붙습니다. 그 라벨은 채택이 아니고 ProducerPort는 NOT_BOUND입니다. 포트 목록은 [docs/SEAMS.md](docs/SEAMS.md)에 있습니다.

[청사진 요구사항·선행 매핑](docs/CAPITAL_REQUIREMENTS_KO.md), [API·연동 경계](docs/INTEGRATION.md), [검증 범위](docs/VALIDATION.md)를 참고하세요. 운영 절차는 [운영 핸드북](docs/OPERATOR_HANDBOOK_KO.md), [CAP 커버리지](docs/CAP_COVERAGE.md), [수용 점검표](docs/ACCEPTANCE_KO.md)에 있습니다. 채택된 금융 원장·수익참여·채권양수·담보/준비금·다중 자산·실제 Commerce/Protocol 연동은 정의와 선행조건을 유지하며 미구현 상태를 표시합니다. 로컬 복식 투영은 비채택 후보입니다.

## 검증

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v
python3 scripts/manifest_vectors.py --check
python3 scripts/workspace_vectors.py --check
python3 scripts/finance_vectors.py --check
python3 scripts/docs_surface.py --check
npm ci
npx playwright install chromium
npm run test:browser
```

한 명령 수용 사다리는 위 검사에 패키지 스모크와 시드 데모를 더합니다. 사람 수용 결정은 포함하지 않습니다.

```sh
python3 scripts/acceptance.py
```

결과는 커밋하지 않는 `build/acceptance-evidence.json`입니다. 명령, 종료 코드, 테스트 수, HEAD SHA, 도구 버전, vendor 해시, golden digest가 들어 있습니다. 단계가 실패하거나 빠지면 0이 아닌 코드로 끝납니다. CI는 매 HEAD에서 이 명령을 실행하고 evidence 파일을 올립니다. `storage-conformance` 단계는 `run_storage_vectors(factory)`로 메모리와 `LOCAL_FILE_WORKSPACE`를 같은 벡터에 통과시킨다. 그 통과는 SEMANTIC_CONFORMANCE가 아니고 CAP-11은 `NOT_BOUND`다. `upstream-claims` 단계의 라벨은 `CLAIM_CONFORMANCE`다. 프로토콜 체크아웃이 없으면 `scripts/upstream_claims_check.py`와 `scripts/agent_claims_check.py`, `scripts/read_model_claims_check.py`는 `SKIPPED`이며 그 상태는 통과가 아니다.

`python3 scripts/seed_demo.py`는 고정 operation id로 종결·미이행·거절·취소·UNBOUND·정산 대기 케이스를 만듭니다. `tests/golden/demo.json`은 여섯 케이스의 `phase`·`settlement_gate`(`cases`), `state_digest`, 투영 합계, manifest `content_digest`, 그리고 읽기 전용 위험 분석의 `risk` 블록(`sim_day` 0, 미상환·준비금 요구액·HHI·`risk_digest`)을 고정합니다. instance id와 시각은 넣지 않습니다. 값이 달라지면 실패하고, 핀을 고치려면 `python3 scripts/seed_demo.py --update-golden`이 필요합니다. 금액은 합성 fixture 단위입니다.

`python3 scripts/sim_journeys.py`는 이름 붙은 합성 여정 `T05-sim`(부분 배정·상환·상환 중 환불·마진 콜·가속·늦은 현금·종결 또는 부도)과 `T06-sim`(`--workspace` 서버 SIGKILL 재시작·UNKNOWN 펜스·agent 제안을 사람이 실행)을 루프백 API로 돌립니다. 둘 다 `SIMULATED`이고 `funds_executed`와 `integrated`는 false이며 T01–T06 자격 주장이 아닙니다. 핀은 `tests/golden/journey_t05_sim.json`, `tests/golden/journey_t06_sim.json`이고 어긋나면 실패합니다. 핀을 고치려면 `python3 scripts/sim_journeys.py --update-golden`이 필요합니다. `scripts/acceptance.py`의 `integrated-journeys` 단계가 이를 돌립니다.

브라우저 검사는 포트폴리오, 케이스, 투영, 명세서, 대사, 준비도, 운영 데스크(`#desk`), organizer/auditor/observer 화면을 데스크톱과 375px로 `test-results/`에 저장합니다. 운영 데스크는 `test-results/operator-desk/{desktop,mobile}/`에 `organizer.png`, `auditor.png`, `observer.png`로 남습니다. 빈 화면이나 콘솔 오류면 실패합니다. 스크린샷은 CI 아티팩트이며 커밋하지 않습니다.

CI는 동일 검사를 새 HEAD마다 실행합니다. UI 자동 검증과 독립 코드 리뷰는 실제 사용자 수용·아키텍처 승인·운영 승인과 구분합니다. Python HTTP 서버, 기본 메모리 receipt, 옵트인 `LOCAL_FILE_WORKSPACE` 파일은 개발용입니다. 내구 원장·멀티테넌트 인증·분산 잠금·stage5 durable transaction이 아닙니다.
