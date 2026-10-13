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
| organizer | 명령과 민감 조회. 자기 명령에 `proposal_id`를 인용하면 receipt에 표시 | agent 레인 (`query_grant` / `propose_action`) |
| auditor | 없음. export·투영·대사·명세서는 읽음. 조건 오버레이(`/api/terms*`)와 정책 시뮬레이터(`/api/policy*`)도 읽음 | 명령, agent 레인 |
| observer | 없음. state와 receipt만 읽음 | export, 투영, 대사, 명세서, evidence, preview, 조건 오버레이(`/api/terms*`), 정책 시뮬레이터(`/api/policy*`), agent 레인 |
| agent | `POST /api/agent/query_grant`와 `POST /api/agent/propose_action`만. 제안은 `HUMAN_PENDING`이고 `effects_executed`는 false. `POST /api/agent/execute`는 `EXECUTE_AUTHORITY_DISABLED` | 모든 `command:*`, `session:bind`, export, 투영, 대사, 명세서 |

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
- `evidence.stages[*].status` — stage id는 `unit`, `storage-conformance`, `pinned-vendor`, `upstream-claims`, `node-check`, `browser`, `packaged-smoke`, `seeded-demo` 여덟이다.

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

`GET /api/policy`와 `GET /api/policy/simulation`은 읽기 전용 시뮬레이티드 정책 적용이다. 라벨은 `simulated policy application — not executed distribution, not bank movement`다. 결정 노트 `docs/decisions/CAPITAL_SETTLEMENT_POLICY.md`의 `allocation_order`가 ADOPTED이면 도출된 순서를 기존 fixture 두 순서와 나란히 보여 준다. UNDETERMINED이면 `POLICY_UNDECIDED`이고 fixture 비교만 남는다. 환불 부담, 리셀 취소, 수익 참여, 채권 매입, 잔여·늦은 현금은 `UNSUPPORTED_BY_PINNED_FSM`이며 금액을 계산하지 않는다. 노트가 그림자 계산을 부탁해도 이 노드는 그 산술을 만들지 않는다. `policy_adopted`는 false다. 노트가 없으면 `policy not bound`다. `.pyz`는 `docs/`를 포함하지 않으므로 그 실행은 `NOT_BOUND`다. 이것은 실행된 배분이 아니고 은행 이동이 아니다. 병합은 JunTae가 한다. 이 노드는 배정 우선순위를 인코딩하므로 스스로 병합하지 않는다.

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
