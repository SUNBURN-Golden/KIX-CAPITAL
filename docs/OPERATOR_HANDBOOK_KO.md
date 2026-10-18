# KIX Capital 운영 핸드북

이 문서는 로컬 시뮬레이션을 켜고, 화면과 증거 파일을 읽고, 막힌 항목을 오해하지 않기 위한 절차다. 제품 동작을 바꾸지 않는다. 실대출·신용심사·은행 잔액·운영 출시가 아니다.

사람 수용은 아직 없다. 자동 검사가 통과해도 사람이 수용한 것이 아니다.

## 정직한 라벨

화면에 나오는 숫자는 합성 fixture다. 아래 말은 서로 바꾸어 쓰지 않는다.

| 라벨 | 의미 |
|---|---|
| `SIMULATED` | 이 프로세스 안의 합성 여정. 실거래가 아니다. |
| `READ_ONLY_FIXTURE` | 고정된 참조 조회. 운영 정책 채택이 아니다. |
| `NOT_BOUND` | 실제 producer·원장·인증·외부 관측이 연결되지 않음. |
| `DECISION_REQUIRED` | 정책 값이 정해지지 않음. 기본값을 만들지 않는다. |
| `NOT_AUTHORIZED` | 실서비스 실행이 승인되지 않음. |
| `UNKNOWN` | 그 operation의 최초 결과를 이 프로세스가 갖고 있지 않음. 재시도 허가가 아니다. |
| `LOCAL_FILE_WORKSPACE` | 개발용 JSON 파일. stage5 내구 거래가 아니다. |
| `SYNTHETIC_UNADOPTED` | 로컬 복식 투영 후보. `fin-ledger-contract` 채택이 아니다. |
| `SYNTHETIC_FIXTURE_PROFILE` | 결정된 합성 fixture 프로필(`CAPITAL-DEMO-BOOK-V1`)의 대형 액면·수익자 role. 실제 익스포저·매출·법적 당사자가 아니다. |
| `DEV_ONLY` | 옵트인 HMAC. 무결성만이고 인증·외부 키가 아니다. |

잠정 조건 오버레이는 이 트리의 읽기 전용 조회다. 결정 노트의 상태 줄은 **상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).** 이다. 값은 `docs/decisions/CAPITAL_FINANCIAL_TERMS.md` (`CAPITAL-TERMS-V1`)에서만 읽는다. 청약·실자금·벤더 FSM 산술이 아니다. zipapp은 `docs/`를 담지 않으므로 그 실행의 조건은 `terms not bound`다.

요구 20개의 소유와 상태는 [CAP 커버리지](CAP_COVERAGE.md)에 있다. 행을 분모에서 빼지 않는다.

## 체크아웃에서 실행

Python 3.10 이상이면 된다. runtime 패키지와 DB는 필요 없다. 저장소 루트에서 실행한다.

```sh
python3 -m capital.server
```

출력의 주소는 `http://127.0.0.1:<port>`다. 기본 포트는 8765다. 브라우저는 그 루프백 주소만 연다. 다른 host, Origin, cross-site 요청은 거절된다.

기본 저장은 프로세스 메모리다. 프로세스를 끄면 제안과 receipt가 사라진다. 그것이 장애가 아니다.

버전만 보려면 `python3 -m capital.server --version`이다. 출력은 `kix-capital <version>`이고 `<version>`은 `capital/__init__.py`의 `__version__` 하나다.

## zipapp에서 실행

체크아웃 없이 돌릴 로컬 아티팩트다. 서명·PyPI 게시·배포가 아니다. 이 문서에 파일 해시나 테스트 개수를 적지 않는다. `<version>`은 위와 같은 단일 출처다.

```sh
python3 scripts/build_release.py --out dist
python3 dist/capital-<version>.pyz --version
python3 dist/capital-<version>.pyz
python3 dist/capital-<version>.pyz --workspace ./var/capital-workspace
python3 scripts/smoke_release.py dist/capital-<version>.pyz
```

같은 인터프리터로 두 번 빌드하면 바이트가 같다. 다른 플랫폼에서 같다는 뜻은 아니다.

## `--workspace`

옵트인이다. 주지 않으면 메모리만 쓴다.

```sh
python3 -m capital.server --workspace ./var/capital-workspace
```

`DIR/workspace.json` 하나에 저널과 receipt를 넣고, 배타 잠금을 프로세스가 끝날 때까지 잡는다. 재시작하면 receipt를 복원하고 `instance_id`는 새로 만든다. state와 export의 `durable` 값은 `LOCAL_FILE_WORKSPACE`다. DB도 inbox/outbox도 다른 호스트 fencing도 아니다. CAP-11은 계속 `NOT_BOUND`다.

`--dev-hmac`은 `--workspace`와 함께만 쓴다. `DIR/export-dev.key`를 mode 0600으로 만들고, 그 키는 응답과 로그에 나오지 않는다. 무결성 검사용이며 인증이 아니다.

## 역할

`organizer`, `auditor`, `observer`는 화면에서 고르는 합성 역할이다. `agent`는 화면 역할이 아니다. `POST /api/session`이 루프백 토큰에 묶는다. 계정·비밀번호·실명·KYC가 없다. 인증이 아니다.

| 역할 | 쓰는 일 | 읽지 못하는 것 |
|---|---|---|
| organizer | 명령과 민감 조회. 자기 명령에 `proposal_id`를 인용하면 receipt에 표시. 시뮬레이션 시계 전진 명령(`POST /api/overlay/commands`, 권한 `overlay:command`, organizer 전용) | agent 레인 전체 (`POST /api/agent/query_grant`, `POST /api/agent/query_subject`, `POST /api/agent/propose_action`, `POST /api/agent/withdraw_proposal`, `POST /api/agent/propose_grant_change`, `POST /api/agent/execute`) |
| auditor | 없음. 읽기 경로는 모두 읽음: state·receipt·참조(`GET /api/scenarios[/…]`, `GET /api/readiness`, `GET /api/decisions`)·export·투영·대사·명세서·evidence·preview·심사 기록(`GET /api/underwrite/…`)·`GET /api/metrics`·`GET /api/health`. 조건 오버레이(`/api/terms*`)와 오버레이 장부(`GET /api/overlay`), 정책 시뮬레이터(`/api/policy*`)도 읽음 | 명령, agent 레인 |
| observer | 없음. state·receipt·참조(`GET /api/scenarios[/…]`, `GET /api/readiness`, `GET /api/decisions`)·`GET /api/health`를 읽음 | 명령, `GET /api/metrics`, export, 투영, 대사, 명세서, evidence, preview, 심사 기록(`GET /api/underwrite/…`), 조건 오버레이(`/api/terms*`), 오버레이 장부(`GET /api/overlay`), 정책 시뮬레이터(`/api/policy*`), agent 레인 |
| agent | `POST /api/agent/query_grant`, `POST /api/agent/query_subject`, `POST /api/agent/propose_action`, `POST /api/agent/withdraw_proposal`, `POST /api/agent/propose_grant_change`. 제안은 `HUMAN_PENDING`이고 `effects_executed`는 false. `POST /api/agent/execute`는 항상 `403 EXECUTE_AUTHORITY_DISABLED` | 모든 GET 경로 (`403 ROLE_FORBIDDEN`; state·참조·receipt·export·투영·대사·명세서·metrics·health 읽기 모두 거절), 모든 `command:*`, `session:bind` |

거절 코드는 `403 ROLE_FORBIDDEN`이다. 거절된 명령은 operation 수와 저널을 바꾸지 않는다. 실제 IdP·AgentGrant/ActionPermit은 `NOT_BOUND`다. `agent` 레인은 그 계약을 대신하지 않는 `SIMULATED` 픽스처다. 제안 등록부는 프로세스 메모리이고 workspace payload에 넣지 않는다.

## 증거와 `acceptance.py`

한 번에 로컬 사다리를 돌리려면 저장소 루트에서 다음을 실행한다.

```sh
python3 scripts/acceptance.py
```

결과는 커밋하지 않는 `build/acceptance-evidence.json`이다. 형식은 `KIX_CAPITAL_ACCEPTANCE_EVIDENCE_V1`이고 `label`은 `SIMULATED`다. `funds_executed`는 false다. 단계가 빠지거나 실패하면 0이 아닌 코드로 끝난다.

사람이 보는 필드는 다음이다.

- `evidence.ok`
- `evidence.label`
- `evidence.funds_executed`
- `evidence.head_sha`
- `evidence.tool_versions.*` (`python`, `node`, `npm`, `playwright`, `capital`)
- `evidence.vendor_hashes.verified`
- `evidence.golden_digests.status`
- `evidence.stages[*].status` — stage id는 `unit`, `storage-conformance`, `pinned-vendor`, `upstream-claims`, `node-check`, `browser`, `packaged-smoke`, `seeded-demo`, `integrated-journeys` 아홉이다.

합격·불합격 문장은 [수용 점검표](ACCEPTANCE_KO.md)에 있다. 그 점검표를 사람이 채우기 전에는 수용이 아니다.

결정 노트 색인:

```sh
python3 scripts/decision_ledger.py
```

`docs/decisions/*.md` 안의 `capital-decision-v1` 블록을 검사한다. `ADOPTED`는 `provided_by`와 ISO 날짜와 `value`가 있어야 한다. `UNDETERMINED`에 `value`·`provided_by`·`date`가 있으면 실패다. `DEFERRED`와 `NOT_ADOPTED`는 `value`가 null이고 `provided_by`·ISO 날짜·`target`이 있어야 한다. 커버리지가 가리키는데 파일이 없으면 `PENDING`이고, 그것만으로는 실패가 아니다. 없는 노트의 내용을 만들지 않는다.

## `NOT_BOUND`와 `UNKNOWN` 읽기

`GET /api/readiness`는 행동 단위로 20개 요구를 보여 준다. `upstream_binding`은 `NOT_BOUND`다. `source_integrity.all_matched`는 고정 vendor 바이트가 매니페스트와 같은지만 말한다. SDK나 실서비스 자격이 아니다. `upstream_nodes_completed`는 빈 목록이다. `production_authorized`와 `policy_adopted`는 false다.

`AVAILABLE_LOCAL`이 아닌 그룹의 차단 이유는 [수용 점검표](ACCEPTANCE_KO.md)의 생성 블록과 같다. 그 블록을 고치려면 준비도 데이터를 바꾼 노드가 `python3 scripts/not_bound_checklist.py --write`로 다시 써야 한다. 손수 고치면 `--check`가 실패한다.

없는 operation을 조회하면 `UNKNOWN`이다. 그 결과는 명령을 다시 보내도 된다는 뜻이 아니다. 서버를 다시 띄우면 `instance_id`가 바뀌고, 이전 탭의 조회는 `SESSION_CHANGED`다. 이전 명령을 다시 보내지 않는다. 대사에서 없는 receipt는 `UNKNOWN_UNRESOLVED`이고 `retry_authorized`는 false다.

## 작업공간 오류

손상된 파일을 빈 장부로 바꾸지 않는다. 쓰기를 멈추고 읽기는 상태를 그대로 보여 준다.

| 코드 | 언제 | 운영자가 할 일 |
|---|---|---|
| `WORKSPACE_UNREADABLE` | 잘림, 변조, 체크섬 불일치, JSON 키 중복, 저널·receipt·fixture·digest 불일치 | POST `/api/commands`는 503이다. 파일을 지우거나 빈 객체로 덮어 시작하지 않는다. 마지막 정상 사본이 있으면 그 파일로 되돌린 뒤 프로세스를 다시 연다. |
| `WORKSPACE_LOCKED` | 다른 프로세스가 잠금을 잡고 있음 | 그 프로세스를 끝내기 전에는 이 프로세스가 읽지도 쓰지도 않는다. 잠금 파일을 지워서 두 프로세스를 동시에 열지 않는다. |
| `WORKSPACE_WRITE_FAILED` | 명령은 이 프로세스에 적용됐는데 임시 파일 교체가 실패 | 그 receipt는 이 프로세스에서만 조회된다. 이후 명령은 503이다. 나중 프로세스는 마지막 완전 파일만 보고, 실패한 쓰기의 명령은 보지 못한다. |

`workspace.status`가 `ACTIVE`일 때만 파일 장부에 쓸 수 있다.

## 노드별 추가 절

이후 노드는 이 제목 아래에 자기 절만 추가한다. 시작은 `<!-- handbook-section:<node-id> -->`, 끝은 `<!-- /handbook-section -->`다. 이미 있는 절의 문장을 고치지 않는다.

<!-- handbook-section:operator-handbook-ko -->

### operator-handbook-ko

이 노드는 문서와 검사만 추가한다. `capital/`의 동작, vendor 바이트, `.aiops`는 그대로다.

- 이 핸드북.
- `docs/CAP_COVERAGE.md`의 CAP-01부터 CAP-20까지 한 행.
- `scripts/decision_ledger.py`와 `scripts/not_bound_checklist.py`.
- `docs/ACCEPTANCE_KO.md`의 설치·역할 절차·사람 점검표.

CAP-02와 CAP-03의 잠정 값은 `docs/decisions/CAPITAL_SETTLEMENT_POLICY.md`에 있다. 요구사항 상태와 준비도 그룹은 `DECISION_REQUIRED`다. 그 값을 제품에 적용하지 않는다. 계정·세무 노트는 `docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md`, 바인딩 노트는 `docs/decisions/CAPITAL_UPSTREAM_BINDING.md`다. `DEFERRED`와 `NOT_ADOPTED`는 연결 완료가 아니다. 금리·수수료·한도·배분 순서를 이 노드가 새로 정하지 않는다.

<!-- /handbook-section -->

<!-- handbook-section:terms-overlay -->

### terms-overlay

`GET /api/terms`와 `GET /api/terms/{advance_id}`는 읽기 전용 시뮬레이티드 오버레이다. 라벨은 `simulated overlay — not vendor FSM arithmetic, not an offer`다. 결정 노트 `docs/decisions/CAPITAL_FINANCIAL_TERMS.md`의 상태 줄은 **상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).** 이고 `terms_version`은 `CAPITAL-TERMS-V1`이다. 가정 일(`draw_day`, `as_of_day`, 선택 `expected_settlement_cash_day`)은 질의 인자이며 저장하지 않는다. 노트가 없거나 항목이 모두 쓸 수 없으면 응답은 `terms not bound`다. 금리·수수료·기간 숫자는 코드에 복사하지 않는다. `.pyz`는 `docs/`를 포함하지 않으므로 그 실행은 `NOT_BOUND`다. 이것은 청약이 아니고 실자금이 아니다. CAP-02와 CAP-03은 계속 `DECISION_REQUIRED`다. 병합은 JunTae가 한다.

<!-- /handbook-section -->

<!-- handbook-section:policy-simulator -->

### policy-simulator

`GET /api/policy`와 `GET /api/policy/simulation`은 읽기 전용 시뮬레이티드 정책 적용이다. 라벨은 `simulated policy application — not executed distribution, not bank movement`다. 결정 노트 `docs/decisions/CAPITAL_SETTLEMENT_POLICY.md`의 `allocation_order`가 ADOPTED이면 도출된 순서를 기존 fixture 두 순서와 나란히 보여 준다. UNDETERMINED이면 `POLICY_UNDECIDED`이고 fixture 비교만 남는다. 환불 부담, 리셀 취소, 수익 참여, 채권 매입, 잔여·늦은 현금은 `UNSUPPORTED_BY_PINNED_FSM`이며 금액을 계산하지 않는다. 그림자 산술은 별도 읽기 전용 경로 `GET /api/policy/shadow`에 있다. 환불 부담 RC1–RC4(RC5는 리셀 해제로 라우팅)와 리셀 해제 RU1–RU3를 `SHADOW_NOT_APPLIED` 모드로만 계산하고, 핀드 FSM에는 적용하지 않는다. 노트가 없으면 `SHADOW_NOT_BOUND`다. 권한은 `projection:read`(관찰자 403), `applied_to_fsm`·`funds_executed`·`policy_adopted`는 항상 거짓이며 `state_digest`는 변하지 않는다. 수익 참여·채권 매입·잔여·늦은 현금은 이 노드에서도 계산하지 않는다(`SHADOW_DEFERRED`). `policy_adopted`는 false다. 노트가 없으면 `policy not bound`다. `.pyz`는 `docs/`를 포함하지 않으므로 그 실행은 `NOT_BOUND`다. 이것은 실행된 배분이 아니고 은행 이동이 아니다. 병합은 JunTae가 한다. 이 노드는 배정 우선순위를 인코딩하므로 스스로 병합하지 않는다.

<!-- /handbook-section -->

<!-- handbook-section:upstream-claims-conformance -->

### upstream-claims-conformance

`scripts/upstream_claims_check.py --execute`는 고정된 FSM 래퍼와 로컬 facade에 대해 클레임 표를 실행한다. 수용 사다리 단계 id는 `upstream-claims`이고 그 단계의 label은 `CLAIM_CONFORMANCE`다. `passed`와 `total`은 그 표의 검사 수다. 인자 없이 실행하면 프로토콜 체크아웃이 없어 `SKIPPED`이며, 그 상태는 통과가 아니다. `--protocol-dir`는 인용된 제목과 문자열만 읽기 전용으로 확인한다. 결과는 SIMULATED다. 실자금을 움직이지 않는다. 이 단계는 프로듀서 프로필 채택이 아니다.

<!-- /handbook-section -->

<!-- handbook-section:underwriting-rules -->

### underwriting-rules

`GET /api/underwrite/{advance_id}?instance_id=&sim_day=&amount=`는 읽기 전용 시뮬레이티드 심사 결정 레코드다. 라벨은 `simulated underwriting record — rule checks only, not an approval`이고 `mode`는 `SIMULATED_UNDERWRITING_RECORD`다. 결정 노트 `docs/decisions/CAPITAL_FINANCIAL_TERMS.md`의 `underwriting_depth`(`EVIDENCE_RULES_V1`)가 정한 여섯 검사 U1–U6을 노트 순서대로 평가한다: 정산 증거 등급, 환불 노출, 차입기초, 집중도 한도, 결정 권한(2인 원칙 임계값), `kyc_executed=false` 기록. 한도·비율·임계값 숫자는 노트에서 읽으며 코드에 복사하지 않는다. `approve`는 여전히 호출자 결정이고 이 레코드는 제안(`proposal`)일 뿐 승인을 막지 않는다. 기존 F04 케이스는 기록된 금액으로, fixture id(예: `sim-refund`)는 `?amount=`를 요구하는 후보 평가로 읽는다. 노트가 없거나 필요 항목이 ADOPTED가 아니면 `NOT_BOUND`이고 숫자 필드를 내지 않는다. 권한은 `projection:read`라 observer는 `403 ROLE_FORBIDDEN`이다. 호출은 receipt·저널·`state_digest`·`operation_count`를 바꾸지 않는다. `underwriting_executed`·`kyc_executed`는 스키마상 const false로 남는다. 이것은 실제 심사·KYC·승인이 아니다. 병합은 JunTae가 한다.

<!-- /handbook-section -->

<!-- handbook-section:observability-metrics -->

### observability-metrics

`GET /api/metrics`와 `GET /api/health`는 이 프로세스 안의 관측 값이다. `mode`는 `LOCAL_OBSERVABILITY`이고 metrics의 `label`은 `SIMULATED`이다. 외부 exporter, tracing, network sink, alerting은 `NOT_BOUND`다. `funds_executed`는 false다. 권한 `metrics:read`는 organizer와 auditor만 가진다. observer는 metrics에서 `403 ROLE_FORBIDDEN`이다. `health:read`는 organizer, auditor, observer가 가진다. observer의 health는 `200`이고 본문은 `status`, `uptime_seconds`, `workspace_status`, `mode`뿐이다. agent는 두 권한 모두 없다.

카운터는 프로세스 메모리에만 있다. 프로세스가 끝나면 0부터 다시 센다. idempotency fingerprint, `state_digest`, `operation_count`, workspace payload, export manifest 섹션에 들어가지 않는다. metrics와 health를 읽어도 장부는 바뀌지 않는다. metrics 응답은 그 요청 자신을 세지 않는다. 다음 조회부터 직전 조회가 보인다.

| 이름 | 이 프로세스에서 의미하는 것 | 증명하지 않는 것 |
|---|---|---|
| `counters.commands.{op}.ACCEPTED` / `REJECTED` | 반환된 receipt의 op와 outcome. op는 고정 명령 목록이거나 `other`. | 저널의 서로 다른 명령 수, 내구성, 정확성, 실자금. transport duplicate도 반환될 때마다 다시 센다. 저장 후 파일 쓰기가 503이면 명령 outcome으로 세지 않는다. |
| `counters.rejections.{code}` | receipt에 담긴 도메인 거절 코드와 HTTP `ApiError` 코드. 코드 모양이 아니면 `other`. | 거절이 옳다는 것, 감사 로그, 금융 증거. |
| `counters.operation_lookups.KNOWN` / `UNKNOWN` | `GET /api/operations/…`가 영수증을 찾았는지. | 재시도 허가. UNKNOWN은 retry를 허가하지 않는다. |
| `counters.http_requests.{route}.{2xx\|4xx\|5xx}` | 응답을 보낸 뒤의 HTTP 상태 계급. 경로 라벨은 등록된 dispatch이거나 `other`. | 원인 분석, SLO, 추적. 등록되지 않은 경로의 원문은 라벨이 되지 않는다. |
| `counters.event_log` | `--event-log FILE`이 켜졌는지, 쓴 줄 수, 열기·쓰기 `OSError` 수, 크기 한도로 버린 줄 수, `max_bytes`(1048576). | 전달 보장, 외부 수집, 감사 보관. |
| `latency_ms.{route}` | 고정 밀리초 버킷 `le_5`, `le_25`, `le_100`, `le_500`, `le_2500`, `gt_2500`와 `count`, `max_ms`. 한 요청은 한 버킷만 증가하고 `count`는 그 합이다. | 백분위 SLO, 용량 계획, 분산 추적. |
| `uptime_seconds` | 이 프로세스의 observability 객체가 살아 있는 초. | 호스트 가동 시간, 무중단. |
| `workspace.status`와 health의 `workspace_status` | 로컬 작업공간 상태. `ACTIVE`가 아니면 health는 `degraded`다. path는 넣지 않는다. | 파일 무결성 그 자체. 그 판단은 기존 workspace 코드가 한다. |

`--event-log FILE`은 옵트인 JSONL이다. 한 줄의 키는 정확히 `time`, `route`, `status`, `code`, `operation_id`다. 본문, 인자, 토큰은 쓰지 않는다. `time`은 UTC ISO-8601이다. HTTP 200인 거절 receipt의 `code`는 null이다. 도메인 코드는 `counters.rejections`에만 있다. 다음 줄이 `max_bytes`를 넘으면 그 줄을 쓰지 않고 `dropped`를 올린다. 경로를 열거나 쓸 수 없어도 명령은 실패하지 않고 `errors`가 증가한다. 부모 디렉터리를 만들지 않는다. 이 파일은 감사 증거도 금융 증거도 아니다.

이 카운터는 정확성, 내구성, 자금 이동, 신원, SLO를 증명하지 않는다. 외부로 내보내지 않는다. 병합은 JunTae가 한다.

<!-- /handbook-section -->

<!-- handbook-section:decision-status-surface -->

### decision-status-surface

`GET /api/decisions`는 `docs/decisions/`의 `capital-decision-v1` 블록을 기계가 읽을 수 있게 요약한다. 라벨은 `simulated decision index — local note summary, not an adoption`이고 `mode`는 `READ_ONLY_DECISION_INDEX`다. `rows`는 노트마다 한 줄이다. 각 줄은 `note`, `decision_id`, `status`, `provisional`, `version`, 항목별 상태 지도 `entries`를 가진다. `status`는 노트 블록의 상태이거나 검사기가 보고한 `INVALID`(블록이 틀림)와 `PENDING`(커버리지가 가리키는데 파일이 없음)이다. `provisional`과 `version`은 블록에 있는 값만 보이고 없으면 null이다. 현재 계정·세무 노트와 바인딩 노트에는 버전 필드가 없으므로 `version`이 null이다. `entries` 값은 `ADOPTED`, `UNDETERMINED`, `DEFERRED`, `NOT_ADOPTED` 중 하나다. `DEFERRED`와 `NOT_ADOPTED`는 연결 완료가 아니다. 금리·수수료·한도 같은 값은 응답에 복사하지 않는다.

파싱은 `python3 scripts/decision_ledger.py`와 같은 코드를 쓴다. 그 스크립트의 출력은 바뀌지 않는다. 권한은 `reference:read`라 organizer, auditor, observer가 읽고 agent는 `403 ROLE_FORBIDDEN`이다. 호출은 receipt·저널·`state_digest`·`operation_count`를 바꾸지 않는다.

`docs/`가 없으면(`.pyz` 실행 등) `status`는 `NOT_BOUND`, `reason`은 `decision notes not bound`, `rows`는 빈 목록이고 숫자 필드는 없다. 이것은 노트가 없다는 뜻이 아니라 이 실행이 노트를 읽을 수 없다는 뜻이다.

`GET /api/readiness`의 `financial-contracts` 차단 사유 중 금융 조건 노트를 인용하는 줄은 이제 이 노트 행에서 만든다. 형식은 `<status> per <note> (<version>)`이고, 예를 들면 `PROVISIONAL_PRODUCT_DECISION per docs/decisions/CAPITAL_FINANCIAL_TERMS.md (CAPITAL-TERMS-V1)`다. 노트를 읽을 수 없으면 `NOT_BOUND per docs/decisions/CAPITAL_FINANCIAL_TERMS.md`다. 그룹 상태 `DECISION_REQUIRED`와 `policy_adopted=false`는 그대로다. 이 줄이 바뀌면 [수용 점검표](ACCEPTANCE_KO.md)의 생성 블록도 `python3 scripts/not_bound_checklist.py --write`로 다시 쓴다. 이 응답은 채택이 아니고 청약이 아니며 실자금과 무관하다. 법무·세무 항목은 전문가 검토 전까지 작업 가정이다. 병합은 JunTae가 한다.

<!-- /handbook-section -->

<!-- handbook-section:auth-matrix-freeze -->

### auth-matrix-freeze

등록된 모든 경로를 organizer, auditor, observer, agent와 토큰 없는 호출자로 나눠 허용·거절을 `tests/auth_matrix.json`에 고정했다. 이 노드는 표와 검사만 추가한다. 경로, 권한, 역할은 바뀌지 않았고 새 권한도 IdP도 없다. 위 `## 역할`의 요약 표는 그대로 두며, 두 표가 다르면 아래 생성 표가 맞다. 아래 표는 루프백 서버로 칸마다 확인한 값이다. 이 표는 합성 역할의 자리표시자이며 권한 정책이 아니다. 신원과 인증은 계속 `NOT_BOUND`다.

<!-- generated:auth-matrix begin -->
이 블록은 `tests/auth_matrix.json`(`KIX_CAPITAL_AUTH_MATRIX_V1`)에서 `python3 scripts/auth_matrix.py --write`가 만든다. 손으로 고치지 않는다. 라벨은 `SIMULATED`이고 역할 출처는 `SYNTHETIC_LOCAL_ROLE`다. 신원과 인증은 `NOT_BOUND`이며 이 표는 권한 정책이 아니라 합성 자리표시자다. `python3 -m unittest tests.test_auth_matrix`가 모든 칸을 루프백 서버에 실제로 보내 확인한다.

`허용`은 그 역할이 권한을 가진다는 뜻이고 `거절`은 `403 ROLE_FORBIDDEN`이다. `no-token`은 `X-Capital-Token`이 없는 호출자다. GET은 기본 `organizer`로 처리돼 그 열과 같고, POST는 어느 권한이든 `403 LOCAL_TOKEN_REQUIRED`(`토큰 필요`)다. 정적 파일(`/`, `/app.js`, `/style.css`)은 인증 전에 응답해 권한이 없다.

| 권한 | organizer | auditor | observer | agent | no-token | 경로 |
|---|---|---|---|---|---|---|
| `command:submit` | 허용 | 거절 | 거절 | 거절 | 토큰 필요 | `POST /api/commands` |
| `command:offer` | 허용 | 거절 | 거절 | 거절 | 토큰 필요 | `POST /api/commands` (op `offer`) |
| `command:approve` | 허용 | 거절 | 거절 | 거절 | 토큰 필요 | `POST /api/commands` (op `approve`) |
| `command:reject` | 허용 | 거절 | 거절 | 거절 | 토큰 필요 | `POST /api/commands` (op `reject`) |
| `command:cancel` | 허용 | 거절 | 거절 | 거절 | 토큰 필요 | `POST /api/commands` (op `cancel`) |
| `command:bind_settlement` | 허용 | 거절 | 거절 | 거절 | 토큰 필요 | `POST /api/commands` (op `bind_settlement`) |
| `command:draw` | 허용 | 거절 | 거절 | 거절 | 토큰 필요 | `POST /api/commands` (op `draw`) |
| `command:repay` | 허용 | 거절 | 거절 | 거절 | 토큰 필요 | `POST /api/commands` (op `repay`) |
| `command:close` | 허용 | 거절 | 거절 | 거절 | 토큰 필요 | `POST /api/commands` (op `close`) |
| `command:default` | 허용 | 거절 | 거절 | 거절 | 토큰 필요 | `POST /api/commands` (op `default`) |
| `command:reconcile` | 허용 | 거절 | 거절 | 거절 | 토큰 필요 | `POST /api/commands` (op `reconcile`) |
| `state:read` | 허용 | 허용 | 허용 | 거절 | 허용 | `GET /api/state` |
| `reference:read` | 허용 | 허용 | 허용 | 거절 | 허용 | `GET /api/scenarios[/…]`, `GET /api/readiness`, `GET /api/decisions` |
| `projection:read` | 허용 | 허용 | 거절 | 거절 | 허용 | `GET /api/evidence`, `GET /api/projection`, `GET /api/terms[/…]`, `GET /api/overlay`, `GET /api/risk`, `GET /api/policy[/…]`, `GET /api/preview/…`, `GET /api/underwrite/…` |
| `receipt:read` | 허용 | 허용 | 허용 | 거절 | 허용 | `GET /api/operations/…` |
| `export:read` | 허용 | 허용 | 거절 | 거절 | 허용 | `GET /api/export`, `GET /api/export/manifest` |
| `reconciliation:read` | 허용 | 허용 | 거절 | 거절 | 허용 | `GET /api/reconciliation` |
| `statement:read` | 허용 | 허용 | 거절 | 거절 | 허용 | `GET /api/statement` |
| `metrics:read` | 허용 | 허용 | 거절 | 거절 | 허용 | `GET /api/metrics` |
| `health:read` | 허용 | 허용 | 허용 | 거절 | 허용 | `GET /api/health` |
| `session:bind` | 허용 | 허용 | 허용 | 거절 | 토큰 필요 | `POST /api/session` |
| `overlay:command` | 허용 | 거절 | 거절 | 거절 | 토큰 필요 | `POST /api/overlay/commands` |
| `agent:query_grant` | 거절 | 거절 | 거절 | 허용 | 토큰 필요 | `POST /api/agent/query_grant` |
| `agent:query_subject` | 거절 | 거절 | 거절 | 허용 | 토큰 필요 | `POST /api/agent/query_subject` |
| `agent:propose_action` | 거절 | 거절 | 거절 | 허용 | 토큰 필요 | `POST /api/agent/propose_action`, `POST /api/agent/execute` |
| `agent:withdraw_proposal` | 거절 | 거절 | 거절 | 허용 | 토큰 필요 | `POST /api/agent/withdraw_proposal` |
| `agent:propose_grant_change` | 거절 | 거절 | 거절 | 허용 | 토큰 필요 | `POST /api/agent/propose_grant_change` |

권한 표 밖에서 표가 고정한 오류 코드는 다음과 같다.

| 코드 | 뜻 |
|---|---|
| `ROLE_FORBIDDEN` | 토큰의 역할에 그 권한이 없다. |
| `LOCAL_TOKEN_REQUIRED` | 토큰이 없거나 알 수 없다. 모든 POST는 먼저 토큰을 본다. |
| `EXECUTE_AUTHORITY_DISABLED` | agent 레인이 EXECUTE를 거절한다. 게이트는 통과했다. |
| `INVALID_ARGUMENTS` | 게이트를 통과한 뒤 인자 검사에서 쓰기 전에 거절됐다. |
| `NOT_FOUND` | 등록되지 않은 (메서드, 경로)다. 기본 거절이다. |
| `ROLE_MISMATCH` | `X-Capital-Role`이 토큰의 역할과 다르다. 헤더로 역할을 바꿀 수 없다. |
| `SESSION_REQUIRED` | 토큰 없이 organizer가 아닌 역할을 주장했다. 먼저 `POST /api/session`이 필요하다. |
| `ROLE_UNKNOWN` | `X-Capital-Role`이 알 수 없거나 중복된 역할이다. |
<!-- generated:auth-matrix end -->

경로나 권한을 바꾸면 `python3 scripts/auth_matrix.py --write`로 표와 두 문서의 생성 블록을 다시 쓴다. 그 전에는 `python3 -m unittest discover -s tests`가 실패한다. 표만 검사하려면 `python3 scripts/auth_matrix.py --check`를 쓴다. 병합은 JunTae가 한다.

<!-- /handbook-section -->

<!-- handbook-section:retention-slots-sync -->

### retention-slots-sync

`GET /api/export/manifest`의 `retention_policy`가 `NOT_BOUND` 상수에서 다섯 이름 있는 빈 칸으로 바뀌었다. 칸과 주인은 upstream RETENTION_PERIODS_PROPOSAL R1(kix-protocol PR #139 `6e54e723`, 사용자 병합)의 네 칸과 `docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md`의 `CAPITAL-RETENTION-PRIVACY-V1`이 더한 세무·회계 칸이다.

| 칸 | owner | status |
|---|---|---|
| `legal_dispute_hold` | legal/privacy counsel designated by JunTae | `UNDETERMINED` |
| `business_reconciliation` | Toss contract/technical | `UNDETERMINED` |
| `retry_support` | Astra | `DECISION_REQUIRED` |
| `memory_residency` | Astra | `DECISION_REQUIRED` |
| `tax_accounting_records` | accountant and tax adviser designated by JunTae | `UNDETERMINED` |

각 칸은 `{owner, status}` 두 필드뿐이다. 기간·상한 숫자는 어디에도 없다 — `memory_residency`의 `{count, bytes, age}` 상한은 노트에 prose로만 있고 manifest에는 `DECISION_REQUIRED` 하나로 눌린다. `MAX_OPERATIONS 500`은 데모 용량 상한이지 보존 값이 아니다. `not_bound` 목록에는 `retention_policy` 행이 그대로 남아 기간과 상한 값이 정해지지 않았음을 말한다. 삭제·축출·타이머 코드는 없다 — 시뮬레이션은 `RETAIN_ALL_NO_AUTOMATIC_DELETION`이고, 열린 법정·분쟁 보류가 다른 칸의 삭제를 막는다는 규칙은 노트의 문장이지 이 코드의 동작이 아니다.

`python3 -m capital.verify FILE`는 섹션 해시·content digest·서명만 검사하므로 새 manifest도 그대로 검증된다. `retention_policy`는 `content_digest`에 들어가므로 구조를 바꾸면 `python3 scripts/seed_demo.py --update-golden`으로 golden을, `python3 scripts/manifest_vectors.py --write`로 `tests/vectors/manifest/`를 다시 쓴다. golden diff는 `content_digest` 한 줄만 달라야 한다. `capital/contract/facade-v1.json`은 다섯 칸을 `additionalProperties: false`로 고정하고 status를 칸별 `const`로 잠근다. 값을 채우는 것은 `k-stage5-durable-tx` 저장이 생기고 주인들이 답한 뒤다. 병합은 JunTae가 한다.

<!-- /handbook-section -->

<!-- handbook-section:delegation-claims-conformance -->

### delegation-claims-conformance

`tests/agent_claims.json`(`KIX_CAPITAL_AGENT_CLAIMS_V1`, 66행)은 시뮬레이티드 agent 레인을 kix-protocol `e2a029d8ac3af7575888dac22fc4bf173ebec232`의 초안 `docs/contracts/AI_DELEGATION_AUTHORITY.md`에 비춰 고정한 클레임 표다. `python3 scripts/agent_claims_check.py --execute`가 `CLAIM_CONFORMANCE passed=66 total=66 failed=0`을 낸다. 위 `upstream-claims-conformance` 절의 "그 표의 검사 수"는 표가 하나였을 때의 문장이며 고치지 않는다. 지금 값은 이 절이 말한다.

수용 사다리의 `upstream-claims` 단계는 이제 명령을 둘 실행한다. 첫째가 `scripts/upstream_claims_check.py --execute`(`tests/upstream_claims.json`, 87행)이고 둘째가 `scripts/agent_claims_check.py --execute`(66행)다. 단계가 보고하는 `passed`와 `total`은 두 표의 `CLAIM_CONFORMANCE` 줄을 합한 값이다. 87+66=153이고 label은 그대로 `CLAIM_CONFORMANCE`다. 첫 명령이 0이 아닌 코드로 끝나면 둘째는 실행하지 않고, 둘째가 0이 아니어도 그 단계는 `failed`다.

인자 없이 실행하면(`--execute`도 `--protocol-dir`도 없을 때) 두 스크립트 모두 `SKIPPED`를 찍고 종료 코드 0으로 끝난다. 그 상태는 통과가 아니고 성공 개수도 없다. `--protocol-dir`는 초안의 제목과 인용 문자열만 읽기 전용으로 확인하며 `CLAIM_DRIFT verified=N total=N`을 낸다.

표 안의 두 이름은 어댑터 매핑이다. `HUMAN_PENDING`은 초안의 `PROPOSED` 메모 단계를 가리키는 Capital 레인의 라벨이고, 저장된 메모는 `effects_executed` false로 남는다. `EXECUTE_AUTHORITY_DISABLED`(403)는 초안의 항상 실패하는 `attempt_execution`(`DELEGATED_EXECUTION_DISABLED`)에 대응하는 레인의 거절이다. 초안의 `PROPOSED`/`HUMAN_APPROVED` 결정 흐름에는 레인 쪽 짝이 없다. 업스트림 `ai_delegation_mock.py`는 vendor하지 않았고 읽기 전용 참조로만 남는다. 결과는 SIMULATED이고 실자금을 움직이지 않는다. 이 단계는 SEMANTIC_CONFORMANCE도 프로듀서 프로필 채택도 아니다. 인증, EXECUTE, ActionPermit은 바뀌지 않았다. 병합은 JunTae가 한다.

<!-- /handbook-section -->

<!-- handbook-section:asset-spec-krw -->

### asset-spec-krw

Capital이 선언하는 자산은 하나다. `capital/assets.py`의 AssetSpec `{namespace: "fiat", reference: "KRW", decimals: 0, max_atoms: 1000000000000}`이다. `max_atoms`는 고정된 FSM의 `MONEY_MAX` fixture 상한이지 registry 한도가 아니다. 이 선언은 `docs/decisions/CAPITAL_UPSTREAM_BINDING.md` 3.6절의 `PROVISIONAL` 항목이다. 자산 registry는 `DEFERRED`, FX와 자산 간 합산은 `NOT_ADOPTED`이며 둘째 자산은 어디서도 받지 않는다. 금액은 이 한 자산의 정수로 남는다.

선언은 `GET /api/state`의 `assets`(항목이 정확히 하나인 배열)와 export manifest의 `source_pin`에서 읽는다. organizer, auditor, observer가 읽는 값은 같고(agent는 GET이 모두 거절이다) 읽어도 장부는 바뀌지 않는다.

`POST /api/commands`의 `asset`은 선택 필드다. 있으면 선언된 AssetSpec과 모든 필드와 그 자료형까지 같아야 한다. 문자열 `"KRW"`, 정수 자리의 float나 bool, 키가 더하거나 모자란 객체는 모두 틀린 값이다. 틀리면 `400 ASSET_MISMATCH`다. 이 검사는 역할 검사와 `SESSION_CHANGED` 뒤, idempotency 조회 앞에서 한다. 그래서 권한 없는 역할은 이 검증으로 아무것도 알 수 없다. 거절된 요청은 저널 항목도 receipt도 idempotency 기록도 남기지 않는다. `GET /api/operations/{operation_id}`는 계속 `UNKNOWN`이고 `state_digest`와 `operation_count`는 그대로이며 그 operation id는 아직 비어 있다. 이미 받아들여진 operation id에 틀린 `asset`을 실어 다시 보내도 `400 ASSET_MISMATCH`일 뿐 저장된 receipt를 돌려주지도 바꾸지도 않는다. 선언된 값을 실은 요청은 `asset` 없는 요청과 똑같이 처리되고, `asset`은 receipt나 idempotency fingerprint에 들어가지 않는다. 같은 operation id에 다른 인자를 보내면 `asset`이 있어도 `IDEMPOTENCY_CONFLICT`다.

이것은 통화 지원이 아니다. 둘째 자산, 환산, u128 금액은 `NOT_BOUND`다. 병합은 JunTae가 한다.

<!-- /handbook-section -->

<!-- handbook-section:manifest-verifier-vectors -->

### manifest-verifier-vectors

`python3 -m capital.verify FILE [--key-file KEY]`가 오프라인 manifest 검증기다. `tests/vectors/manifest/`는 그 검증기가 변조를 잡는지 보는 SIMULATED 변조 코퍼스다. 같은 `seed_demo` 이야기를 파일 작업공간에 고정 instance id `manifest-vectors`로 다시 돌려 만들어서 실행마다 같은 바이트가 나온다.

| 파일 | 만든 방법 | 기대하는 결과 |
|---|---|---|
| `unsigned.json` | 서명 없는 깨끗한 manifest | `ok` true, signature `NOT_BOUND` |
| `dev-hmac.json` | 같은 장부를 `DEV_HMAC_SHA256`으로 서명 | `ok` true, signature `VERIFIED_DEV_ONLY_INTEGRITY` (키 필요) |
| `section-<id>.json` | 그 섹션 본문의 한 바이트를 뒤집음. 섹션은 `journal`, `receipts`, `projection`, `reconciliation`, `statement`, `fixtures`, `source_pin` 일곱 개 | `SECTION_HASH_MISMATCH:<id>` |
| `content-digest.json` | `content_digest`의 16진 한 글자를 뒤집음 | `CONTENT_DIGEST_MISMATCH` |
| `signature.json` | HMAC 값의 16진 한 글자를 뒤집음 | `SIGNATURE_MISMATCH` (키 필요) |
| `malformed.json` | 서명된 manifest를 문서 중간에서 자름 | `MANIFEST_UNREADABLE` |

`tests/vectors/export-dev.key`는 `dev-hmac.json`과 `signature.json`을 위한 고정 합성 DEV_ONLY 키로, 시험 재료이지 자격 증명이 아니고 다른 곳에 쓰지 않는다. git에서는 모드 0644로 저장되는데 검증기는 모드 0600인 키 파일만 읽는다. 그대로 `--key-file`에 주면 `SIGNATURE_KEY_MODE`다. 임시 위치에 복사한 뒤 `chmod 0600`을 하고 그 사본을 넘긴다. 통과하면 종료 코드 0, 거절이면 1이다.

`python3 scripts/manifest_vectors.py --check`는 메모리에서 코퍼스를 다시 만들어 바이트를 비교하고, 다르거나 빠졌거나 `manifest/` 아래에 예상 밖 파일이 있으면 1로 끝난다. `--write`는 파일을 다시 쓰고 나머지 `manifest/*.json`을 지운다. manifest 구조를 바꾸면 `python3 scripts/seed_demo.py --update-golden`과 함께 `--write`가 필요하다. 공유 HMAC은 무결성만 확인하고 인증이 아니다. 이것은 stage7 인증 export가 아니고 새 서명 방식도 아니다. 병합은 JunTae가 한다.

<!-- /handbook-section -->

<!-- handbook-section:finance-vector-pack -->

### finance-vector-pack

`tests/vectors/finance_vectors.json`(`KIX_CAPITAL_FINANCE_VECTORS_V1`)은 결정적 입력 벡터 묶음이다. `label`은 `SIMULATED`, `vector_role`은 `INPUT_VECTOR_CANDIDATE`다. `docs/decisions/CAPITAL_UPSTREAM_BINDING.md`의 `stage6_finance_candidates`(DEFERRED)가 말하는 대로, Capital이 두 번째 원장을 만들지 않고 로컬 산출물을 여덟 `FINANCE_PENDING_NODES` 후보의 입력 벡터 후보로 내놓는다. 파일은 고정 instance `finance-vectors`로 만들지만 instance id는 담지 않는다. 시계, 무작위 값, 경로도 없다.

| 묶음 | 후보 | 담는 것 |
|---|---|---|
| `scenario_obligations` | `fin-multi-payee-refund-proof` | F01–F03 시나리오 9개, 35 단계의 payee별 의무 값과 현금·환불 합계. 정책은 고르지 않는다. |
| `f04_command_outcomes` | `fin-ledger-contract` | `seed_demo` 명령 22개의 outcome·오류·phase·`state_digest`와 받아들여진 저널 항목 21개 |
| `journal_projection_digests` | `fin-double-entry-projection` | 저널 prefix마다 복원한 `state_digest`와 `SIMULATION_FIXED_V1` 항목·계정·read-model digest, 차변·대변 합계 |
| `seed_reconciliation` | `fin-observation-reconciliation` | 고정 instance seed 장부의 대사 검사 여섯 개 보고서와 발급된 적 없는 operation id 하나 |
| `statement_and_previews` | `fin-credit-exposure-reconciliation` | 다섯 범주 명세서와 모든 케이스의 읽기 전용 draw preview |
| `manifest_section_digests` | `fin-consistent-accounting-export` | manifest v2 섹션 sha256과 `content_digest` |
| `facade_read_model` | `fin-catalogue-read-model` | `capital/contract/facade-v1.json`의 모든 GET 경로 응답 정의 digest |

`fin-finance-closeout`은 벡터가 없다. 그 입력인 `build/acceptance-evidence.json`은 실행마다 달라지고 커밋하지 않는 파일이라 고정할 바이트가 없다. 후보 색인의 그 행은 `vectors`가 null이고 이유를 적어 둔다.

`python3 scripts/finance_vectors.py --check`는 메모리에서 다시 만들어 파일과 비교하고, 다르거나 파일이 없으면 1로 끝난다. 통과는 고정된 로컬 코드가 아직 이 바이트를 만든다는 말뿐이다. 투영, 계정과목, 회계 정책을 바꾸지 않는다. 원본 산출물이 바뀌어 검사가 실패하면 `--write`로 다시 쓴다. 파일은 `semantic_conformance` false, `funds_executed` false, `upstream_nodes_completed` 빈 목록을 스스로 적는다. SEMANTIC_CONFORMANCE가 아니고 어떤 업스트림 노드도 끝내지 않으며 회계·정산 정책을 채택하지 않는다. 후보가 이 벡터를 쓰려면 그 후보 자신의 업스트림 완료 증거가 있어야 한다. 병합은 JunTae가 한다.

<!-- /handbook-section -->

<!-- handbook-section:setoff-proposal-quote -->

### setoff-proposal-quote

`GET /api/terms/{advance_id}/setoff`는 읽기 전용 상계·회수 제안 견적이다. 라벨은 `simulated overlay — not vendor FSM arithmetic, not an offer`이고 `mode`는 `SIMULATED_OVERLAY`다. 결정 노트 `docs/decisions/CAPITAL_FINANCIAL_TERMS.md`의 ADOPTED `collateral_execution` 1차 단계(`SETOFF_AGAINST_BENEFICIARY_SETTLEMENT_DISTRIBUTION`)를 그 advance가 결합한 불변 정산 조회에 적용한다. 수익자 매핑 수취인 줄 가운데 결정 노트 `docs/decisions/CAPITAL_SETTLEMENT_POLICY.md`의 CAPITAL-ALLOC-V1 클래스 표에서 상대방 수익(COUNTERPARTY_PROCEEDS) 클래스인 줄만 세고, `setoff_amount`는 `min(outstanding_exposure, 그 줄들의 배정 현금 − recovery_due)`다. 회수 의무 아래의 현금은 세지 않고 배정이 없으면 `ALLOCATION_NOT_OBSERVED`로 0을 보고하며 현금을 지어내지 않는다. `allocation` 절은 노트의 `repayment_allocation_order`(DEFAULT_INTEREST → INTEREST → PRINCIPAL)로 나누고 `fsm_repay`는 원금 몫만 들거나 null이다. `route`는 DRAWN이면 `FSM_REPAY`, DEFAULTED이면 `OVERLAY_RECOVERY_LEDGER`, 그 외는 `NOT_APPLICABLE`이고 `post_default`는 `OVERLAY_RECOVERY_LEDGER_NOT_IN_SCOPE`다. 집행 권한은 노트의 사람 2인(`HUMAN_OPERATOR_TWO_PERSON; AI proposes only`)에 머물고 채택된 1차 단계가 상계가 아니거나 권한이 사람이 아니면 견적은 숫자를 내지 않는다. 권한은 `projection:read`(organizer·auditor)이고 observer는 `403 ROLE_FORBIDDEN`이다. 노트가 없거나 필요한 항목이 ADOPTED가 아니면 숫자 없이 `terms not bound`다. `.pyz`는 `docs/`를 포함하지 않으므로 그 실행은 `NOT_BOUND`다. `proposal_only`는 true이고 `applied`는 false이며 receipt·예약·저널·`state_digest`·`operation_count`는 바뀌지 않는다. 이것은 제안일 뿐이며 집행이 아니고 청약이 아니고 고정 FSM을 부르지 않는다. 병합은 JunTae가 한다.

<!-- /handbook-section -->

<!-- handbook-section:terms-portfolio-rollup -->

### terms-portfolio-rollup

`GET /api/terms/portfolio`는 읽기 전용 포트폴리오 조건 롤업이다. 라벨은 `simulated overlay — not vendor FSM arithmetic, not an offer`이고 `mode`는 `SIMULATED_OVERLAY`다. 리터럴 `/api/terms/portfolio`는 `{advance_id}` 패턴보다 먼저 매치되고, 알 수 없는 advance id는 여전히 `404 UNKNOWN_ADVANCE`다. 평가된 각 줄은 등급·가정 인출일 출처(`draw_day_source`, `QUERY_PARAMETER` 또는 `DEFAULT`)·기간·만기일·만기 경과일·계약/연체 이자(정확한 유리수, 줄마다 1원 내림)·연환산 총비용 bps(유리수 문자열)·`cap_check`(PASS/FAIL)를 담고, 상한은 실행 시 노트의 `interest_rate.all_in_cost_cap_bps_annual`에서 읽는다. 코드에 옮기지 않는다. `cap` 절은 그 값과 `fees.policy`·`fee_schedule_version`을 함께 인용한다. 저널에는 노출별 시계가 없어 모든 줄이 질의의 가정 `draw_day`를 공유한다. 합계 줄은 유리수를 먼저 더하고 한 번만 내리며 `cap_check`는 하나라도 FAIL이면 FAIL, 평가된 줄이 없으면 NOT_APPLICABLE이다. 티어·원금을 정할 수 없거나 필요한 항목이 ADOPTED가 아닌 줄은 숫자 없이 `NOT_APPLICABLE`/`NOT_BOUND`만 담는다. 노트가 없거나 쓸 수 없으면 `rows` 없이 `terms not bound`이고 숫자가 없다. `.pyz`는 `docs/`를 포함하지 않으므로 그 실행은 `NOT_BOUND`다. 상한 FAIL은 상한을 낮춘 임시 합성 노트(`--terms-note`)로만 재현하며 커밋된 노트는 바꾸지 않는다. 권한은 `projection:read`(organizer·auditor)이고 observer는 `403 ROLE_FORBIDDEN`이다. receipt·예약·저널·`state_digest`·`operation_count`는 바뀌지 않는다. 노출 버킷·집중도 한도·준비금·환불 충격 스트레스는 범위 밖이다. 이것은 청약도 심사도 아니고 벤더 FSM 산술도 아니다. 병합은 JunTae가 한다.

<!-- /handbook-section -->

<!-- handbook-section:portfolio-risk-analytics -->

### portfolio-risk-analytics

`GET /api/risk`는 읽기 전용 포트폴리오 위험 분석이다. 라벨은 `SIMULATED portfolio risk analytics — read-only, not a credit decision, not an accounting policy`이고 `mode`는 `SIMULATED_RISK_ANALYTICS`, 권한은 `projection:read`라 observer·agent는 `403 ROLE_FORBIDDEN`이다. 수락된 저널, 오버레이 시계 `sim_day`, `CAPITAL-TERMS-V1` 노트를 정수 나눗셈으로만 접으며 영수증·저널·오버레이 항목을 쓰지 않는다. 등급별 노출, 만기 버킷(표준 만기까지 남은 일수 0-30, 31-60, 61-90, >90; 만기일 당일과 연체 노출은 0-30), 연체 경과(`NOT_DUE`, 만기 후 1-30, 31-60, 61-90, >90일, `DEFAULTED`)의 합은 총 미상환과 같고 `reconciliation`이 로컬 투영의 advance 미상환과 맞춘다. 집중도는 수익자(`beneficiary_role`)별 정수 permille HHI와 `underwriting_depth` U4 세 한도(단일 건, 수익자 합계, 포트폴리오)에 대한 사용률(permille)이다. 준비금 요구액은 노트 `reserve.provision_bps_of_outstanding` 표(현재 150/500/2500/10000 bps)를 건별로 적용해 `floor(미상환 × bps / 10000)`을 더한 값이며 회계 정책이 아니고 `applied`는 false다. 스트레스는 마진 조건이 있는 `DRAWN` 건의 `eligible_face`를 고정 정수 충격 `[500, 1000, 2500, 5000]` bps만큼 줄여 다시 재고, 충격이 클수록 마진콜 건수는 줄지 않는다. 이 마진콜은 가정이며 오버레이에 기록되지 않는다. 장부가 알고 있는 만기는 표준 60일뿐이라 실제 데이터에서는 61-90, >90 버킷이 비어 있고 순수 함수 시험으로만 확인한다. 마진 가속 후의 만기 재기준(`NOT_REBASED / DECISION_REQUIRED`)은 반영하지 않는다. 노트가 없으면 `NOT_BOUND`이고 숫자가 없다. 브라우저 패널 `#risk`는 `textContent`만 쓴다. 확률 모형, 부동소수점, 외부 데이터, 회계 채택은 범위 밖이다.

<!-- /handbook-section -->

<!-- handbook-section:agent-lane-tools -->

### agent-lane-tools

시뮬레이티드 agent 레인이 고정된 초안(`docs/contracts/AI_DELEGATION_AUTHORITY.md`, kix-protocol `e2a029d8ac3af7575888dac22fc4bf173ebec232`)의 허용 목록 다섯을 모두 연다. `POST /api/agent/query_subject`(`agent:query_subject`)는 `surface`와 선택 `subject`의 소속만 확인하는 QUERY 조회다. fixture의 `subjects`는 null이고 그 값은 제한 없음을 뜻한다. `POST /api/agent/withdraw_proposal`(`agent:withdraw_proposal`)는 저장된 대기 제안을 `WITHDRAWN`으로 두고 `effects_executed`는 false로 남는다. 두 번째 철회는 `duplicate: true`고 기간 창은 이 도구를 거절하지 않는다. 철회된 줄은 한도 몫을 되돌리고 사람 명령이 더는 인용할 수 없다(`PROPOSAL_BINDING_CONFLICT`). `POST /api/agent/propose_grant_change`(`agent:propose_grant_change`)는 `requested` 메모(`authority`, `scope`, `limits`, `period`, `note`만)를 `HUMAN_PENDING`으로 저장하고 부여 본문은 바뀌지 않는다. 메모는 금액 없이 건수만 쓰고 `authority`에 `EXECUTE`가 있으면 `EXECUTE_AUTHORITY_DISABLED`(403)로 아무것도 남기지 않는다. 세 경로 모두 organizer·auditor·observer는 `403 ROLE_FORBIDDEN`, 토큰 없음은 `403 LOCAL_TOKEN_REQUIRED`다. `POST /api/agent/execute`는 여전히 `403 EXECUTE_AUTHORITY_DISABLED`로 아무것도 쓰지 않는다. 제안은 프로세스 메모리에만 있고 workspace payload에 넣지 않는다. 레이블은 그대로 `SIMULATED_AGENT_GRANT`/`IN_MEMORY_FIXTURE`/`NOT_BOUND`다.

`tests/agent_claims.json`은 이제 94행이고 `python3 scripts/agent_claims_check.py --execute`가 `CLAIM_CONFORMANCE passed=94 total=94 failed=0`을 낸다. 위 `delegation-claims-conformance` 절의 66행과 87+66=153 문장은 그 표가 작았을 때의 문장이며 고치지 않는다. 지금 값은 이 절이 말한다(87+94=181). facade 계약은 `agent_subject_*`, `agent_withdraw_*`, `agent_grant_change_*`, `agent_memo_view` 정의를 더했고 재전송된 철회 제안이 저장된 단계를 그대로 보고하므로 `agent_proposal_view`의 `phase`는 `HUMAN_PENDING`/`WITHDRAWN` enum이다. `python3 scripts/auth_matrix.py --write`가 표와 이 파일의 생성 블록을 다시 썼다. 병합은 JunTae가 한다.

<!-- /handbook-section -->

<!-- handbook-section:workspace-offline-audit -->

### workspace-offline-audit

`python3 -m capital.verify --workspace DIR`은 서버를 띄우지 않고 `DIR/workspace.json`을 감사한다. 바이트를 직접 읽을 뿐 `workspace.json.lock`을 열지도 잠그지도 않고 아무것도 쓰지 않아서, 살아 있는 서버가 잠금을 잡고 있는 동안에도 읽기만 한다. 출력은 한 줄 JSON이고 `mode`는 `OFFLINE_WORKSPACE_AUDIT`, `label`은 `SIMULATED`, `diagnostic`은 `LOCAL_ONLY`다.

검사는 순서대로 `workspace_file`, `strict_json`(절단·BOM/NUL·NaN·중복 키), `envelope_shape`, `payload_sha256`, `payload_shape`, `journal_replay`(스크래치 기계로 재생), `state_digest`, `service_restore`(서버가 쓰는 `verify_document`/`_validated_restore` 경로 그대로), `receipt_journal_fingerprints`(저널 항목마다 지문 재계산; REJECTED와 reconcile receipt는 args가 저장되지 않아 모양과 유일성만 본다), `recon`(`GET /api/reconciliation`과 같은 여섯 검사를 그대로 싣고, overlay가 비어 있지 않으면 `overlay_fold_digest_equals_persisted` 검사와 `scope.overlay_state_digest`도 싣는다)다. 첫 어긋남이 이유를 정한다: `WORKSPACE_UNREADABLE`이거나, 봉투는 온전한데 대사 검사가 어긋나면 `RECON_MISMATCH`다. 종료 코드는 `ok`면 0, 첫 불일치면 1, 인자 오용이면 2다. 파일을 고치거나 교체하지 않고 가져오기·재개 경로도 없다.

고정 변조 코퍼스는 `tests/vectors/workspace/` 아래 여섯 파일이다: `clean.json`, 중간에서 잘린 `truncated.json`, payload 한 바이트를 뒤집은 `payload-byte.json`, `payload_sha256`의 16진 한 글자를 뒤집은 `digest.json`, 최상위 `format` 키를 하나 더 넣은 `duplicate-key.json`, `state_digest`만 바꾸고 `payload_sha256`은 다시 계산한 `stale-digest.json`. `python3 scripts/workspace_vectors.py --write`가 같은 바이트로 다시 쓰고 `--check`가 어긋남·누락·예상 밖 파일에 1로 끝난다. 이것은 로컬 진단이지 stage5 내구 거래 증거가 아니고 CAP-11은 `NOT_BOUND`다. 병합은 JunTae가 한다.

<!-- /handbook-section -->

<!-- handbook-section:event-log-summary -->

### event-log-summary

`python3 -m capital.events FILE --summary`는 `--event-log FILE`이 남긴 JSONL 파일 하나를 서버 없이 읽는 오프라인 요약 도구다. 출력은 한 줄 JSON이고 `mode`는 `OFFLINE_EVENT_LOG_SUMMARY`, `label`은 `SIMULATED`, `diagnostic`은 `LOCAL_ONLY`다. 줄마다 정확히 다섯 필드(`time`, `route`, `status`, `code`, `operation_id`) 모양을 검사한다. `time`은 작성자가 쓰는 `YYYY-MM-DDTHH:MM:SS.ffffffZ` 여섯 자리 마이크로초 고정 형식이어야 하고 달·날짜도 실제여야 한다(13월, 2월 30일 거절). `route`는 비지 않은 ASCII 문자열이면 족하고 등록된 경로 집합 검사는 하지 않는다. 다른 빌드가 남긴 로그도 요약되어야 하기 때문이다. `status`는 0..599 정수(불린·문자열 거절)이고, `code`는 `null`이거나 대문자 토큰 모양, `operation_id`는 `null`이거나 영숫자·하이픈 1..80자다.

보고서는 `by_route`, `by_status`, `by_status_class`(2xx/4xx/5xx, 분류 안 되는 상태는 `other`), `by_code`, `without_code`, `events`, `first_time`, `last_time`을 낸다. HTTP 200 거절 receipt의 `code`는 null이므로 도메인 거절 코드는 `by_code`에 없고 `GET /api/metrics`의 `counters.rejections`에만 있다. `event_log.dropped`와 `event_log.errors`는 프로세스 카운터라 파일에서 관측되지 않는다. 보고서는 그 두 칸을 null로 찍고 `dropped_errors`를 `NOT_OBSERVABLE_OFFLINE`로 표시하며 metrics를 가리킨다. 0을 지어내어 실제 숫자처럼 보고하지 않는다.

어긋난 줄(잘못된 JSON, 중복 키, 여분·누락·이름이 다른 필드, 배열이나 문자열 줄, 빈 줄, 비ASCII 바이트, BOM, NUL, 모양이 틀린 값)을 만나면 그 줄의 1부터 세는 번호와 이유를 stderr에 찍고 1로 끝난다. 읽을 수 없는 경로는 `EVENT_LOG_UNREADABLE`로 1, 인자 오용은 2다. 빈 파일은 0건으로 요약하고 0으로 끝난다. 파일을 한 개만 바이트로 읽고, 아무것도 쓰지 않으며, 잠금도 열지 않는다. 이벤트 로그 형식·크기 한도·서버 동작은 바꾸지 않았다. 이 도구는 exporter도 tracing도 감사·금융 증거도 아니다. 병합은 JunTae가 한다.

<!-- /handbook-section -->

<!-- handbook-section:shadow-refund-resale -->

### shadow-refund-resale

`GET /api/policy/shadow`는 환불 부담자(RC1–RC4. RC5는 재판매로 간다)와 재판매 되감기(RU1–RU3)를 `CAPITAL-SHADOW-V1` 노트로 산수만 해 보여 주는 읽기 경로다. 권한은 `projection:read`이고 observer는 `403 ROLE_FORBIDDEN`을 받는다. 모드는 `SHADOW_NOT_APPLIED`이고 라벨은 "shadow arithmetic — not applied to the pinned FSM, not an executed distribution, not a bank movement"다. 항목마다 고정 FSM의 `UNSUPPORTED_BY_PINNED_FSM` 판정과 그림자 판정이 나란히 나온다.

그림자 판정은 `SHADOW_COMPUTED`, `SHADOW_DEFERRED`, `SHADOW_NOT_BOUND`, `SHADOW_INPUT_UNKNOWN`, `SHADOW_INCONSISTENT` 중 하나다. 수익 참여, 청구권 매입, 잔여·지연 현금은 계산하지 않고 `SHADOW_DEFERRED`로 남는다. `applied_to_fsm`, `funds_executed`, `policy_adopted`를 포함한 상수 false 플래그가 붙는다. 고정 FSM은 호출하지 않고 `state_digest`도 바뀌지 않는다. 노트가 없거나 깨졌거나 `.pyz`로 실행하면 `SHADOW_NOT_BOUND`다. 이것은 `SIMULATED` 산수이지 집행된 분배가 아니다.

<!-- /handbook-section -->

<!-- handbook-section:caps-binding-fixtures -->

### caps-binding-fixtures

데모 장부 `CAPITAL-DEMO-BOOK-V1`(라벨 `SYNTHETIC_FIXTURE_PROFILE`)은 합성 청구 열 건과 수혜자 다섯을 fixture-v1 세 뷰에 더한다. 고정 `SettlementMachine` 호출로만 재생한다. `demo-epsilon-refund`가 열린 환불 면을 묶기 때문에 `GET /api/underwrite`가 실제 `DECLINE` 기록을 낼 수 있다. 청구 면가는 결정 노트 `docs/decisions/CAPITAL_DEMO_BOOK.md`에 있고 이 문서는 숫자를 옮겨 적지 않는다.

U4 한도 검사는 단건, 수혜자, 포트폴리오 순이다. 필드는 `single_advance_cap_krw`, `beneficiary_aggregate_cap_krw`, `portfolio_cap_krw`이고 값은 실행 때 `CAPITAL-TERMS-V1`에서 읽는다. V1 투영과 `state_digest`는 그대로이고 `content_digest`만 움직였다.

<!-- /handbook-section -->

<!-- handbook-section:sim-clock-ledger -->

### sim-clock-ledger

`sim_day`를 쓰는 길은 `POST /api/overlay/commands`의 `op: advance_day` 하나다. 권한은 `overlay:command`이고 organizer만 쓴다. auditor, observer, agent는 `403 ROLE_FORBIDDEN`이다. `from_sim_day`를 `to_sim_day`로 바꾸는 compare-and-set이다. `from_sim_day`가 접힌 `sim_day`와 다르면 `409 SIM_CLOCK_STALE`이니 `GET /api/overlay`를 다시 읽고 그 `sim_day`로 보낸다. 되감기나 제자리는 `400 SIM_CLOCK_NOT_ADVANCING`, 결정 노트의 `max_step_days`를 넘기면 `400 SIM_CLOCK_STEP`, 용량 한도를 넘기면 `409 SIMULATION_CAPACITY`다. 시계 원천은 `SIM_LOGICAL_CLOCK`이고 벽시계를 쓰지 않는다.

응답을 잃었으면 `GET /api/overlay?operation_id=…`로 조회한다. 기록된 receipt를 돌려주거나 `{outcome: UNKNOWN, retry_authorized: false}`를 돌려준다. `UNKNOWN`은 재시도 허락이 아니다. 같은 본문을 다시 보내면 저장된 receipt가 `transport_duplicate: true`로 돌아오고, 같은 id에 다른 본문은 `409 IDEMPOTENCY_CONFLICT`다.

오버레이가 읽히지 않으면 `WORKSPACE_UNREADABLE`이다. 항목을 고쳐 다시 서명했거나, digest가 낡았거나, 매달린 항목이 있거나, `overlay_schema`가 1이 아니거나, 섹션 키가 더 있거나, v2 봉투에 `overlay`가 없거나, `envelope_version`이 틀린 경우다. 봉투 전체를 거절하고 수리도 부분 오버레이도 없으며 파일을 빈 것으로 바꾸지 않는다. `POST /api/overlay/commands`와 `POST /api/commands`는 503이다. `GET /api/overlay`는 읽히고 `workspace_status`를 보고한다. 이때 메모리의 오버레이는 비어 있어 `sim_day` 0과 `entry_count` 0이 진짜 빈 오버레이라는 뜻이 아니므로 `workspace_status`를 먼저 본다. `python3 -m capital.verify --workspace DIR`도 `WORKSPACE_UNREADABLE`을 보고한다. F04 저널, `state_digest`, receipt는 바뀌지 않는다. 이자는 `SIMULATED` 메모이고 `funds_executed`는 false다.

<!-- /handbook-section -->

<!-- handbook-section:margin-cure-default -->

### margin-cure-default

`advance_day`마다 `additional_margin` 규칙을 평가하고 같은 원자 저장 안에 `margin_call`, `margin_cure`, `margin_acceleration`, `default_eligible_proposal` 항목을 쓴다. `GET /api/overlay`에는 최상위와 행마다 `margin` 블록이 붙는다.

workspace의 정산 뷰는 바꿀 수 없다. 그곳에서는 `checked` true, `triggered` false, `limit` `FIXTURE_VIEWS_IMMUTABLE`(원천 `READ_ONLY_FIXTURE`)이고 아무것도 기록하지 않는다. 마진 콜은 버려지는 `ScenarioReplaySource` 장부(`SIMULATED_DISPOSABLE_BOOK`)에서만 일어난다. `DEFAULT_ELIGIBLE`은 사람 운영자를 위한 제안일 뿐이다. `proposal_only` true, `f04_default_called` false이고 F04 저널을 쓰지 않으며 F04 `default`를 호출하지 않는다. 치유 선택지 2와 3은 `NOT_BOUND`다. 이자와 상각은 다시 기준을 잡지 않으며(`interest_rebased` false, `NOT_REBASED / DECISION_REQUIRED`) 재산정은 재무 조건 소유자가 정한다. 치유 기간과 이율 값은 여기에 옮겨 적지 않는다.

<!-- /handbook-section -->

<!-- handbook-section:audit70-fix1 -->

### audit70-fix1

`default-recovery-decision`(`docs/decisions/CAPITAL_DEFAULT_RECOVERY.md`)과 `repayment-posting-decision`(`docs/decisions/CAPITAL_REPAYMENT_POSTING.md`)은 잠정 제품 결정(PROVISIONAL PRODUCT DECISION) 노트다. 시뮬레이션 전용이고 production은 `NOT_AUTHORIZED`이며 법무·회계 항목은 작업 가정이다.

두 노트가 정한 것은 아직 구현되지 않았다. 운영자 화면에서는 계속 `interest_rebased` false, `interest_payments` `NOT_RECORDED`이고 `post_repayment` 명령도, 회수·상각 명령도 없다. 구현은 `overlay-recovery-writeoff`, `coa-payment-writeoff-postings`, `overlay-repayment-posting` 노드가 맡는다.

이 절은 바로 위 `margin-cure-default` 절의 재기준 문장을 대체한다. 재기준은 잠정 결정됐지만 구현 전이다. 이율·일수·한도 같은 수치는 여기에 옮기지 않으며 `CAPITAL-TERMS-V1`에 둔다.

<!-- /handbook-section -->

<!-- handbook-section:coa-candidate-projection -->

### coa-candidate-projection

`GET /api/projection?mode=coa-candidate`는 `projection:read`, `GET /api/reconciliation?mode=coa-candidate`는 `reconciliation:read` 권한이 필요하다. 두 경로 모두 organizer와 auditor만 읽고 observer와 agent는 `403 ROLE_FORBIDDEN`을 받는다. 읽기 전용이라 영수증, 저널, `state_digest`, `operation_count`는 바뀌지 않는다. `mode`를 생략하거나 `mode=simulation`이면 기존대로 `SIMULATION_FIXED_V1`(`LOCAL_PROJECTION_CANDIDATE`)이 나온다. 후보 모드는 `mode=LOCAL_PROJECTION_COA_CANDIDATE`, `chart=SIMULATION_FIXED_V2`, `coa_version=CAPITAL-COA-V1`을 돌려준다. 그 밖의 `mode`(`operating`, `ledger` 등)나 `mode` 키 중복은 `400 NOT_BOUND`다.

후보 계정표는 `accounting_policy=SYNTHETIC_UNADOPTED`다. `tax`, `legal`, `operating_ledger`는 `NOT_BOUND`이고 `policy_adopted`, `funds_executed`, `workspace_mutated`는 false다. `fin-ledger-contract`나 수익 인식 정책을 채택한 것이 아니며 공식 원장도 아니다. 모든 계정 코드에는 `chart_status`(`NOT_RECORDED`, `DERIVED_MEMO` 등)가 붙고 조용히 빠지는 계정은 없다. 이자 납부는 `NOT_RECORDED`라서 1110 계정은 감소하지 않는다.

`9790 MEMO_SUSPENDED_INTEREST_CONTRA`는 계정 노트에 없는(`adopted_in_note=false`) 후보 전용 메모 계정이다. 수락된 `default` 이후의 이자 발생은 수익 계정 4100/4110이 아니라 `9700` 차변 메모와 `9790` 대변 상대 메모로 기록된다. 자체 금액 가치는 없으며 유지·개명·삭제는 회계 담당자가 정한다. 대사 모드는 `coa_candidate_totals_vs_v1`, `interest_ledger_vs_projection` 검사와 `coa_candidate` 라벨 블록을 추가한다. 오버레이가 비어 있지 않으면 `overlay_fold_digest_equals_persisted`도 나온다(`audit60-fix2` 절 참고). 기본 대사 보고서와 매니페스트의 `reconciliation` 절에는 이 두 COA 검사가 없다. 세무 신고는 범위 밖이다.

<!-- /handbook-section -->

<!-- handbook-section:audit60-fix2 -->

### audit60-fix2

오버레이 저널이 비어 있으면 내보내기는 `KIX_CAPITAL_EXPORT_MANIFEST_V2`이며 `tests/golden/demo.json`과 바이트가 같다. 첫 `advance_day` 이후 오버레이가 비어 있지 않으면 `KIX_CAPITAL_EXPORT_MANIFEST_V3`가 되어 기존 일곱 절에 `overlay` 절(파트 태그 `overlaypart`)이 더해진다. `GET /api/overlay`의 `export`는 `INCLUDED_IN_MANIFEST_V3` 또는 `ABSENT_WHEN_EMPTY`로 표시된다. 매니페스트 읽기는 `export:read`(organizer, auditor)가 필요하다. 서명 방식은 그대로이며 단일 `content_digest`를 서명한다. 인증된 내보내기가 아니다.

`python3 -m capital.verify FILE`은 V2와 V3를 모두 받는다. V3에 `overlay`가 없거나 V2에 `overlay`가 있으면 `SECTION_SET`을, 그 밖의 절 구성 차이는 `MANIFEST_SHAPE`를 돌려준다. `overlay` 절의 바이트가 바뀌면 `SECTION_HASH_MISMATCH:overlay`다. 대사 검사 `overlay_fold_digest_equals_persisted`와 `scope.overlay_state_digest`는 오버레이가 비어 있지 않을 때만 나타나며, 불일치하면 매니페스트가 `INCOMPLETE`(`RECONCILIATION_NOT_CLEAN`)가 된다. 빈 오버레이는 기존 여섯 검사를 유지한다.

`tests/golden/overlay_demo.json`은 `SIMULATED` 라벨, `overlay_schema` 1이며 `export_manifest_v3_content_digest`, `overlay_state_digest`, `entry_count`, `sim_day`, `interest_krw`, `scenario`를 고정한다. 시나리오는 고정된 F04 `repay` 명령을 쓴다. `tests/test_overlay.py`의 `GoldenTests`가 비교만 하며 재생성하지 않는다. `CAPITAL_REPAYMENT_POSTING.md`에 따라 재생성은 repayment-posting 노드만 한 번 할 수 있다. 운영자가 다이제스트 불일치를 보면 골든을 고칠 일이 아니라 드리프트로 취급한다. `demo.json`과 `overlay_empty.json`은 바이트가 그대로다.

<!-- /handbook-section -->

<!-- handbook-section:t05-t06-sim-journeys -->

### t05-t06-sim-journeys

`python3 scripts/sim_journeys.py`는 이름 붙은 합성 여정 `T05-sim`과 `T06-sim`을 루프백 HTTP API로 끝까지 돌린다. 둘 다 `label`은 `SIMULATED`, `funds_executed`는 false, `integrated`는 false다. `docs/decisions/CAPITAL_UPSTREAM_BINDING.md`가 말하듯 T05/T06의 합성 변형을 Q0 안에 이름 붙이는 일이며, 통합 수용(Q3)도 T01–T06 자격 주장도 아니다. 사람 점검표 칸은 이 여정이 채우지 않는다. 고정 operation id와 고정 시드(`CAPITAL-SIM-JOURNEYS-V1`)로 돌고 시계·무작위 값·instance id·토큰·포트·경로를 기록하지 않는다.

`T05-sim`(35단계)은 한 서버 프로세스 안의 일회용 정산 장부(`ScenarioReplaySource`) 위에서 돈다. 마진 규칙은 이 장부에서만 저널에 남기 때문이다. `--workspace` 서버의 fixture는 읽기 전용이다. 순서: 두 건의 advance가 정산채권의 주최자 줄 일부만 점유(부분 배정) → 상환 → 상환 중 부분 환불. Capital에는 정산 이벤트 HTTP 경로가 없으므로 환불은 장부에서 직접 재생하고, 그 단계에 `SIMULATED_OUT_OF_BAND_SETTLEMENT_EVENT`를 붙인다. 이어서 고정 거절 `REFUND_OBLIGATION_OPEN`과 `DISTRIBUTION_BLOCKED_REFUND_BEARER_UNDEFINED` 옆에 `GET /api/policy/shadow`의 환불 분할(`UNSUPPORTED_BY_PINNED_FSM`인 pinned 쪽과 `SHADOW_COMPUTED`인 shadow 쪽, `applied_to_fsm` false)을 나란히 기록한다. shadow 벡터는 고정 입력(`partial-after`)이지 이 장부가 아니다. 그 뒤 마진 콜 → 기한일 포함 → 하루 뒤 가속(`NOT_REBASED`, 이자·상각 기준일은 그대로) → 늦은 현금. 환불로 기준이 낮아져 할당 조회는 `NOT_APPLICABLE`이고, 사람이 `interest_payments`가 `NOT_RECORDED`인 채 이자 우선 순서로 원금 몫만 `repay`한다. 가속은 되돌려지지 않는다. 다른 advance는 0까지 상환 후 `close`. 마지막으로 `DEFAULT_ELIGIBLE` 제안이 한 건 생기고(`f04_default_called` false) 사람이 `default` 명령을 낸다.

`T06-sim`(33단계)은 `python3 -m capital.server --port 0 --workspace TMP` 하위 프로세스를 쓴다. agent가 `query_grant`와 `propose_action`을 부르고, `POST /api/agent/execute`와 `kind: EXECUTE` 제안은 `403 EXECUTE_AUTHORITY_DISABLED`, agent 토큰의 명령은 `403 ROLE_FORBIDDEN`이며 digest와 operation 수는 그대로다. 사람(organizer)이 `proposal_id`를 인용해 `repay`하면 receipt에 `proposal_id`와 `role`이 남고 제안은 여전히 `HUMAN_PENDING`이다. 응답을 일부러 버린 요청은 UNKNOWN으로 막힌다: 하네스는 그동안 어떤 쓰기도 네트워크로 보내지 않고, operation id 조회만 한다. 조회 결과가 `UNKNOWN`이어도 `retry_authorized`는 false다. 그 다음 하위 프로세스를 SIGKILL로 죽이고 같은 작업공간으로 다시 띄운다. 옛 토큰은 `LOCAL_TOKEN_REQUIRED`, 새 토큰에 옛 `instance_id`를 쓰면 `SESSION_CHANGED`(명령과 조회 모두)다. `state_digest`·operation 수·오버레이 digest가 같고, receipt는 원래 `instance_id`와 `proposal_id` 그대로 복원되며, 새 프로세스의 명령 카운터는 0이다. 제안 등록부는 프로세스 메모리라 재시작 뒤 옛 `proposal_id` 인용은 `404 UNKNOWN_PROPOSAL`이다. 하네스는 같은 operation id를 두 번 보내지 않았음을 마지막에 확인한다.

핀은 `tests/golden/journey_t05_sim.json`과 `tests/golden/journey_t06_sim.json`이다. 여정이 어긋나거나 핀이 없으면 1로 끝난다. 의도한 변경일 때만 사람이 확인한 뒤 `python3 scripts/sim_journeys.py --update-golden`으로 다시 쓴다. 핀은 결정 노트(`CAPITAL-TERMS-V1`)의 수치에 의존하므로 노트가 바뀌면 같이 바뀐다. `scripts/acceptance.py`의 `integrated-journeys` 단계가 이 스크립트를 돌리고 evidence의 `stages[*].journeys.items`에 `T05-sim`·`T06-sim`의 단계 수와 `SIMULATED` 라벨과 digest를 싣는다. evidence 최상위의 `integrated`는 false이고 `qualification.claimed`도 false다.

<!-- /handbook-section -->

<!-- handbook-section:operator-console-ux -->

### operator-console-ux

운영 데스크는 `http://127.0.0.1:<port>/#desk`로 연다. 왼쪽 메뉴의 `10 운영 데스크`도 같은 주소다. 열면 다른 패널은 숨고, 다른 메뉴를 누르면 원래 화면으로 돌아간다. 서버 경로, 권한, 역할은 바뀌지 않았다. 화면은 계산하지 않고 서버가 준 숫자와 사유 문장을 그대로 보여 준다. 예외는 `to_sim_day = from_sim_day + 진행 일수`뿐이며, 이는 요청 형식이 요구하는 논리 시계 정수다. 단계 상한과 낡은 시계 판정은 서버가 한다.

영역은 위에서 아래로 다섯이다.

- **위험 요약 타일**: `GET /api/risk`의 미상환, 열린·기록된 노출, 준비금 요구액(기장 안 함), HHI, 마지막 충격 행의 부족액, sim_day. 조건이 `NOT_BOUND`이면 라벨과 사유만 나온다.
- **sim_day 제어**: `진행 일수`를 넣고 `sim_day 진행`을 누르면 `POST /api/overlay/commands`(`advance_day`)를 한 번 보낸다. 같은 탭 간 쓰기 잠금(`kix-capital-writer`)과 대기 기록을 쓴다. 응답을 잃으면 `UNKNOWN`이며 자동 재시도하지 않는다. `원 요청 결과 조회`는 `GET /api/overlay?operation_id=`만 읽고, 서버에 반영돼 있을 때만 대기 기록을 지운다. `SIM_CLOCK_STALE`, `SIM_CLOCK_NOT_ADVANCING`, `SIM_CLOCK_STEP`, `SIMULATION_CAPACITY`는 서버 거절이다.
- **다음 작업**: 선택한 사례에서 보낼 수 있는 F04 명령. 활성·비활성과 사유는 서버 값이다. 노출 기록은 `GET /api/preview`의 `WOULD_REJECT` 사유, 종결은 `close_ready`와 원금·이자 필드, 미이행 메모는 마진 `default_eligible` 제안과 `margin.state`, `margin.limit`, `default_eligible_day`, 권한은 역할 권한 사유다. 심사 기록(`GET /api/underwrite`)의 `DECLINE`은 승인 옆에 자문 문장으로만 나오고 승인을 막지 않는다. 비활성 항목은 `aria-disabled`이며 눌러도 명령을 보내지 않는다.
- **조건 오버레이 원장**: `GET /api/overlay`의 `interest_due_krw`, `default_interest_due_krw`, `close_ready`.
- **사례 타임라인**: 내보내기 매니페스트의 F04 저널과 오버레이 저널을 `after_journal_index` 기준으로 합친다. 같은 위치에서는 오버레이가 F04 행 앞에 온다. F04 행에는 sim_day를 만들어 붙이지 않는다. 시계와 조건 연결 행은 `오버레이 · 전역`으로 표시한다.

역할별 모습은 다음과 같다. organizer는 전부 본다. auditor는 타일, 원장, 타임라인만 보고 명령 조작은 숨겨지며 사유가 한 줄 나온다. observer는 `projection:read` 사유가 담긴 금지 안내만 보고 데스크용 요청을 보내지 않는다.

키보드만으로 쓰려면 Tab 순서가 `데스크 새로고침` → `사례` → `진행 일수` → `sim_day 진행` → 다음 작업 버튼 → 오버레이 원장 → 타임라인이다. 일수를 넣고 `sim_day 진행`에서 Enter 또는 Space를 누른다. 완료 후 초점은 `sim_day 진행`에 남는다. 375px 폭에서 가로 넘침이 없고, 표는 자체 영역 안에서만 가로로 스크롤된다.

스크린샷은 `npm run test:browser` 실행이 `test-results/operator-desk/desktop/`와 `test-results/operator-desk/mobile/`에 `organizer.png`, `auditor.png`, `observer.png`로 저장한다(데스크톱 1280px, 모바일 375px). 합성 데모 작업공간(`scripts/seed_demo.py`)에서 찍은 `SIMULATED` 화면이며 실제 자금·승인 화면이 아니다. 저장소에 커밋하지 않는다.

<!-- /handbook-section -->
