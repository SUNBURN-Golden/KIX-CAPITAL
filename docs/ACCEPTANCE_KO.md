# Capital 로컬 수용 절차

체크아웃과 zipapp에서 로컬 시뮬레이션을 실행하고, 역할별로 이미 있는 자동 검사와 맞춰 본 뒤, 사람이 증거 파일을 읽고 합격·불합격을 적는 절차다.

사람 수용은 아직 일어나지 않았다. `scripts/acceptance.py`가 0으로 끝나도 사람이 수용한 것이 아니다. 금액·역할·공연은 합성이다. 실자금, 실 PG, 은행, KYC, 제공자 호출이 없다.

## 체크아웃에서 설치하고 실행

Python 3.10 이상. 패키지 설치와 DB는 없다. 저장소 루트에서 실행한다.

1. `python3 -m capital.server`를 실행하고 브라우저로 `http://127.0.0.1:8765`를 연다. 다른 host는 거절된다. 기본 상태는 프로세스 메모리다. 검증: tests/test_capital.py::HttpTests.test_local_headers_and_static
2. 재시작 뒤에도 receipt를 보려면 `python3 -m capital.server --workspace ./var/capital-workspace`를 쓴다. `durable`은 `LOCAL_FILE_WORKSPACE`이며 stage5 내구 거래가 아니다. 검증: tests/test_persistence.py::FileWorkspaceTests.test_round_trip_restores_canonical_state_and_original_receipts

## zipapp에서 실행

`<version>`은 `capital/__init__.py`의 `__version__`이다. 이 문서에 해시나 빌드 횟수를 적지 않는다. 아티팩트는 서명되지 않았고 게시되지 않았다.

1. `python3 scripts/build_release.py --out dist`로 `dist/capital-<version>.pyz`를 만든다. 검증: tests/test_release.py::BuildTests.test_two_builds_match_and_archive_is_pinned
2. `python3 dist/capital-<version>.pyz --version` 다음 `python3 dist/capital-<version>.pyz`로 체크아웃 없이 같은 루프백 서버를 띄운다. 파일이 필요하면 `python3 dist/capital-<version>.pyz --workspace ./var/capital-workspace`다. 검증: tests/test_release.py::SmokeTests.test_smoke_journey_restart_and_version

## 역할별 절차

역할은 `POST /api/session`으로 고르는 합성 역할이다. 인증이 아니다.

### organizer

1. 화면의 기본 역할로 결합 여정(제안, 승인, 정산 결합, 인출, 상환, 종결)을 끝까지 진행하고 export 재생이 맞는지 본다. 금액은 합성 fixture다. 검증: tests/browser/journey.spec.cjs::complete bound lifecycle, repayment and export
2. 같은 여정이 API에서 액면 예약과 상환 순서를 지키는지 확인한다. 검증: tests/test_capital.py::DomainTests.test_full_journey_and_read_only_settlement

### auditor

1. auditor로 바꾼 뒤 쓰기는 거절되고 export와 대사는 읽히는지 본다. 검증: tests/browser/auditor-role.spec.cjs::auditor session blocks every write and still reads export and reconciliation
2. 민감 읽기 경로가 역할 행렬과 같은지 확인한다. 검증: tests/test_auth.py::HttpAuthTests.test_sensitive_reads_follow_the_matrix

### observer

1. observer는 manifest를 받지 못하고 쓰기 횟수가 늘지 않는지 본다. 검증: tests/browser/export-manifest.spec.cjs::observer cannot export
2. observer의 export 요청이 403인지 확인한다. 검증: tests/test_export_manifest.py::ManifestTests.test_http_auditor_may_export_the_manifest_and_observer_may_not

## 사람 점검표

아래 칸은 사람이 `build/acceptance-evidence.json`을 읽고 채운다. 자동 사다리가 파일을 만들어도 이 점검표가 통과한 것은 아니다. 칸은 비워 둔다.

`stages[*]`는 stage id `unit`, `pinned-vendor`, `node-check`, `browser`, `packaged-smoke`, `seeded-demo` 여섯 전부다.

- [ ] 사다리 결과
  - PASS: evidence.ok == true 이고 evidence.stages[*].status == "passed"
  - FAIL: evidence.ok 가 false 이거나 한 stage의 status가 passed가 아니다
- [ ] 정직 라벨
  - PASS: evidence.label == "SIMULATED" 이고 evidence.funds_executed == false
  - FAIL: evidence.label 이 SIMULATED가 아니거나 evidence.funds_executed 가 true다
- [ ] vendor 바이트
  - PASS: evidence.vendor_hashes.verified == true
  - FAIL: evidence.vendor_hashes.verified 가 false다
- [ ] golden digest
  - PASS: evidence.golden_digests.status == "recorded"
  - FAIL: evidence.golden_digests.status 가 recorded가 아니다
- [ ] 추적 정보
  - PASS: evidence.head_sha 가 있고 evidence.tool_versions.* 의 python, node, npm, playwright, capital 이 비어 있지 않다
  - FAIL: evidence.head_sha 가 없거나 evidence.tool_versions.* 의 한 값이 비어 있다

## 아직 묶이지 않은 준비도

이 블록은 `python3 scripts/not_bound_checklist.py --write`가 `CapitalService().readiness()`로 만든다. `GET /api/readiness`와 같은 함수다. instance id와 시각은 넣지 않는다. 사람 수용 결과가 아니다. 준비도가 바뀌면 `--write`로 다시 쓰고, `python3 scripts/not_bound_checklist.py --check`가 어긋남을 실패로 본다.

<!-- generated:not-bound begin -->
- [ ] financial-contracts (DECISION_REQUIRED; CAP-02, CAP-03, CAP-04): 수익·원가 정의와 배분 순서/상한
- [ ] financial-contracts (DECISION_REQUIRED; CAP-02, CAP-03, CAP-04): 채권 양도량·보유자·대가·우선순위
- [ ] financial-contracts (DECISION_REQUIRED; CAP-02, CAP-03, CAP-04): 이자·수수료·기간·연체/손실·외부 담보 완전성
- [ ] producer-binding (UPSTREAM_REQUIRED; CAP-07, CAP-16): 확대 catalogue와 generated SDK의 exact source/manifest
- [ ] producer-binding (UPSTREAM_REQUIRED; CAP-07, CAP-16): SEMANTIC_CONFORMANCE profile과 양성/음성 vectors
- [ ] producer-binding (UPSTREAM_REQUIRED; CAP-07, CAP-16): Commerce/Protocol 동일 producer tuple과 실제 서비스 qualification
- [ ] durable-finance (UPSTREAM_REQUIRED; CAP-11, CAP-13, CAP-14, CAP-15): 채택 backend와 stage5/6 경제 원천
- [ ] durable-finance (UPSTREAM_REQUIRED; CAP-11, CAP-13, CAP-14, CAP-15): Finance 후보 8개 채택과 계정/세무 정책
- [ ] durable-finance (UPSTREAM_REQUIRED; CAP-11, CAP-13, CAP-14, CAP-15): stage7 source cut·watermark·인증 export·부분 자료 거절
- [ ] assets-and-rights (UPSTREAM_REQUIRED; CAP-12, CAP-17, CAP-18, CAP-19): asset registry/u128/FX 계약과 적합성
- [ ] assets-and-rights (UPSTREAM_REQUIRED; CAP-12, CAP-17, CAP-18, CAP-19): RS 규모·privacy·currentness, TL 및 coin 잠금 결정
- [ ] assets-and-rights (UPSTREAM_REQUIRED; CAP-12, CAP-17, CAP-18, CAP-19): AgentGrant/ActionPermit 및 최소 공개 계약
- [ ] release (NOT_AUTHORIZED; CAP-20): 사용자 제품 수용과 적용 가능한 독립 감사
- [ ] release (NOT_AUTHORIZED; CAP-20): 실여신/PG/은행/KYC·면허/법무와 운영 책임
- [ ] release (NOT_AUTHORIZED; CAP-20): 인증/TLS/보존·복구·개인정보·배포 명시 승인
upstream_binding: NOT_BOUND
source_integrity.all_matched: true
<!-- generated:not-bound end -->
