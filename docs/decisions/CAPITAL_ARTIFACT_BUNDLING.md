# CAPITAL_ARTIFACT_BUNDLING — 아티팩트 결정 노트 번들링 결정

> 상태: **PROVISIONAL PRODUCT DECISION** — 2026-10-14
>
> 결정자: **Devin swe-2 (RO by prompt), delegated by JunTae 2026-10-08 (model 10-14 10:07)**
>
> 위임 원문 (2026-10-08 18:25 KST, JunTae Park): "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해."
>
> 역사적 위임문은 Fable을 지명했으나 2026-10-14 10:07 기준 이 노드의 결정자는 Devin swe-2다. Fable/claude-fable-5-1은 audit-only다. 같은 흐름에서 위임된 release-acceptance-decision·external-gate-decision의 money/deploy/secrets는 계속 `PENDING_OWNER_ACTION`이며 이 결정이 그것을 실행하지 않는다.
>
> 기준: KIX-CAPITAL main `8787278` · kix-protocol main `adcddc5` (read-only checkout) · vendor FSM pin `7481b0e16ce9b903abbffa62249bb91cd9e63cfe` (`capital/vendor/manifest.json` SHA256 잠금 5파일)
>
> 성격: 이 저장소의 로컬 시뮬레이션·제품 설계를 위한 **문서 전용** 결정이다. 오퍼가 아니며 실자금이 없다. production은 계속 `NOT_AUTHORIZED`다. 법률·세무·회계·면허에 닿는 언급은 전문가 검토 전 작업 가정이며 조언이 아니다. 이 결정은 번들링의 **구현**, 서명, 게시, 배포를 승인하지 않으며 `signed: false`·`published: false`·`LOCAL_SIMULATION_ARTIFACT`를 그대로 둔다. 어떤 upstream 계약도 실제 영수증 없이 채택됐다고 주장하지 않는다.

## 1. 결정 요약

| item | 결정 | CAP rows | consumer node / seam |
|---|---|---|---|
| `notes_bundling_scope` | **BUNDLE.** 빌드 시점 `docs/decisions/*.md` 전부 + `docs/CAP_COVERAGE.md` + `scripts/decision_ledger.py`를 바이트 그대로 아카이브 루트의 동일 상대경로에 포함. `importlib.resources` Traversable 단일 로드 경로. 아티팩트 안 `/api/terms`·`/api/policy`·`/api/decisions`·`/api/underwrite`가 체크아웃과 같은 상태를 보고 | CAP-01, CAP-02, CAP-04, CAP-05, CAP-20 | packaging-release (`scripts/build_release.py`), terms-overlay (`capital/terms.py`), policy-simulator (`capital/policy.py`), decision index (`capital/decisions.py`), underwriting (`capital/underwriting.py`) |
| `artifact_digest_policy` | 번들 파일은 `RELEASE-MANIFEST.json` `files` 맵에 per-file SHA256으로 추가. format `KIX_CAPITAL_RELEASE_V1`, `signed:false`, `published:false`, `mode:LOCAL_SIMULATION_ARTIFACT` 유지. `.pyz` sha256은 코드+docs 통합 내용 주소 | CAP-15, CAP-20 | packaging-release, `scripts/smoke_release.py`, `tests/test_release.py`, `docs/RELEASES.md` |
| `not_bound_labeling` | `notes_source` ∈ {CHECKOUT, BUNDLED_IN_ARTIFACT, OVERRIDE_FILE, NONE} + `note_sha256` 필드를 네 표면과 `/api/state` terms snapshot에 추가. 아티팩트 내부 `NOT_BOUND`의 의미를 "번들 노트 부재·손상·무효·usable ADOPTED 없음"으로 좁힘. 기존 정직 라벨·provisional 표기·`NOT_AUTHORIZED` 전부 유지 | CAP-01, CAP-02, CAP-20 | `/api/terms*`, `/api/policy*`, `/api/decisions`, `/api/underwrite/{id}`, `GET /api/state` |
| `version_source_disclosure` | `capital/__init__.py` 단일 버전 출처와 `--version` 출력 유지. git SHA는 아티팩트에 심지 않음. provenance는 manifest per-file sha256 + `notes_source`/`note_sha256` + 노트 내부 `*_version`으로 공개 | CAP-15, CAP-20 | `GET /api/state`, `--version`, `RELEASE-MANIFEST.json` |
| `build_reproducibility` | 같은 소스 트리 + 같은 인터프리터 → byte-identical `.pyz` 보장 유지. raw bytes, 정렬 열거, 고정 zip 메타. docs 바이트 변경 → digest 변경 (의도된 결합). 크로스 플랫폼 동일성은 미주장 | CAP-20 | `scripts/build_release.py`, `tests/test_release.py`, `.github/workflows/verify.yml` package job |
| `handbook_and_release_docs` | 구현 시 README·핸드북·INTEGRATION·RELEASES·CLI help를 함께 갱신. 기존 0.1.0 기록 보존 + 번들 빌드는 새 entry에 자체 SHA256로 기록 + `__version__` → 0.2.0. `CAP_COVERAGE.md` 인용은 별도 sync diff | CAP-20 | docs 세트, packaging-release 구현 노드의 문서 체크리스트 |

## 2. KIX 비전과의 연결

읽은 Protocol 문서 (read-only checkout `adcddc5`): `README.md`, `docs/DEVELOPMENT_PLAN.md`, `docs/ROADMAP.md` (역사 자료 표기 확인), `docs/COMMERCE_CONTRACTS.md`, `docs/decisions/PROGRAM_DECISIONS_20260928.md`, `docs/decisions/PROGRAM_ROADMAP_20260930.md`, `docs/decisions/AUTHORITY_MODEL_1.md`, `docs/decisions/TOKEN_LAYER_AND_RIGHTS_SCALE_SCOPE_20260929.md`, `docs/decisions/RIGHTS_SCALE_RS0_DECISION_20261008.md`, `docs/aiops/` 색인.

이 결정이 장기 비전에 기여하는 방식:

1. **모델 1 — 체인 권위 / 오프체인 위임 실행** (`docs/decisions/AUTHORITY_MODEL_1.md`). A-4는 "기록과 재생의 필수 분리"를 요구한다. 결정 노트 바이트는 위임된 제품 결정의 **기록**이다. 그 기록을 아티팩트에 결합하는 것은 권위를 아티팩트로 옮기는 게 아니라 — Capital은 원권위를 갖지 않는다 — 아티팩트가 자신이 시뮬레이션하는 정책의 원본 기록을 함께 운반해, 그 재생이 무엇에 근거했는지 스스로 증명하게 하는 것이다. `BOUND`(번들)는 "기록이 결합됐다"이지 "권위가 이전됐다"가 아니며, 라벨 결정이 그 경계를 지킨다.
2. **"범위는 넓게, 가능성은 최대한"** (`docs/decisions/PROGRAM_DECISIONS_20260928.md` §1, `docs/DEVELOPMENT_PLAN.md` §1). 체크아웃 없이 돌아가는 pyz가 네 표면 전부 `NOT_BOUND`라는 축소된 제품인 것은 장기 방향에 맞지 않는다. 번들링은 아티팩트를 자기 완결 시연 단위로 만들어, 분리된 실행자(심사자, 다른 위임 에이전트, 장래 AI-agent grant lane의 감사 레인)가 같은 정책을 재생·대조하게 한다.
3. **결정 문서 → 게이트 → 구현 노드의 패턴** (`docs/decisions/PROGRAM_ROADMAP_20260930.md` 노드 구조, `docs/decisions/RIGHTS_SCALE_RS0_DECISION_20261008.md`의 "초안 → Astra 검토 → 병합 → 구현 노드"). 이 노드는 문서만 생산하고 구현은 후속 노드가 한다 — 동일한 관행.
4. **stage7 인증 export 방향** (`docs/DEVELOPMENT_PLAN.md` §5, 로드맵 R-11)와 **canonical digest 문화** (`docs/COMMERCE_CONTRACTS.md`의 "원 요청으로 재계산해 해시를 대조"). 번들 파일을 `RELEASE-MANIFEST.json`에 per-file sha256으로 묶고 `note_sha256`으로 응답에 노출하는 것은, 장래 인증 export·source-cut이 요구할 "출처 바이트 + digest + source 라벨" 패턴을 지금의 작은 경계에서 미리 정립하는 것이다.
5. **Finance 후보 유지 원칙** (`docs/CAPITAL_REQUIREMENTS_KO.md`, `docs/aiops/FINANCE_COMPLETION_DESIGN_KO.md`의 PENDING 보존). 번들링은 Finance 후보 노드를 완료로 옮기지 않는다 — producer tuple·운영 원장·인증 export는 계속 `NOT_BOUND`로 보고된다.
6. **잠금과 해제의 분리** (`PROGRAM_DECISIONS_20260928.md` §5, `TOKEN_LAYER_AND_RIGHTS_SCALE_SCOPE_20260929.md`의 "승인은 문서화에 한정"). 이 노드도 문서 결정과 구현 승인을 분리한다. `signed:false`·`published:false`·실자금·배포 잠금은 건드리지 않는다.

## 3. 항목별 결정

### 3.1 `notes_bundling_scope` — 번들 범위

**결정값 (machine-readable):**

- `bundle: true`
- 번들 집합 (빌드 시점, 아카이브 루트에 동일 상대경로로):
  - `docs/decisions/*.md` — 그 시점 존재하는 모든 결정 노트. 최상위 단계, 비재귀, `sorted` 열거.
  - `docs/CAP_COVERAGE.md` — decision index의 expected-path 정렬 근거.
  - `scripts/decision_ledger.py` — 유일한 ledger 파서 소스.
- 로드 메커니즘: `importlib.resources.files('capital').parent` 기준 Traversable. 체크아웃에서는 `pathlib.Path` (저장소 루트), zipapp에서는 `zipfile.Path` (아카이브 루트) — **하나의 코드 경로**. 파일 열거는 Python 3.10 호환을 위해 `iterdir()` 사용.
- ledger 파서: 번들된 소스 바이트를 `exec`/`compile`로 모듈화. 벤더 사본을 두지 않아 파서 단일 출처를 유지하고, 파서가 `capital`을 import하지 않는다는 기존 불변 조건도 유지.
- 제외: `docs/`의 나머지 전부, `scripts/`의 나머지 전부, `tests/`, `.github/`, `.aiops/`, `node_modules/`, `build/`, `dist/`, `.git/`.
- 아티팩트 내부 효과: `/api/terms` → 현 `CAPITAL-TERMS-V1` 아래 `BOUND` (BOUND/PARTIAL/NOT_BOUND 판정 규칙은 체크아웃과 동일), `/api/policy` → `DECIDED`, `/api/decisions` → `BOUND`, `/api/underwrite/{id}` → 평가 가능. `--terms-note`/`--policy-note` 오버라이드는 유지되며 `notes_source=OVERRIDE_FILE`로 보고.
- 여전히 `NOT_BOUND`: producer tuple (CAP-07, CAP-16), 내구 운영 원장 (CAP-11), 인증/IdP/KYC (CAP-19), 은행·PG·제공자 관측 (CAP-09, CAP-14), stage7 인증 export·source cut (CAP-15), RS/TL/AI grant (CAP-17~19).

**근거:** 현재 `.pyz`는 terms/policy/decisions/underwrite 네 표면이 전부 `NOT_BOUND`라 사실상 축소된 제품이다. 결정 노트는 이 제품이 읽는 정책 입력이며, 이미 vendor FSM과 static 자산을 담는 것과 같은 종류의 번들 대상이다. 자기 완결 아티팩트는 더 감사 가능하다 — 아티팩트가 읽는 노트 바이트가 아티팩트 안에 있고 manifest에 해시되므로 심사자가 체크아웃 없이 정책 원본을 대조할 수 있다. 장기적으로는 "위임 결정이 어떻게 제품에 들어갔는가"를 아티팩트 단위로 증명하는 패턴을 정립하며, 장래 producer tuple 바인딩·AI grant lane·stage7 export가 같은 패턴을 재사용한다. 빌드 가능성은 이 세션에서 확인했다: `zipfile.Path`의 `iterdir`/`read_text`/`joinpath`/`parent`와 번들 소스 `exec`가 stdlib만으로 동작한다.

**고려한 대안:**

- (a) checkout-only 유지, pyz는 `NOT_BOUND` — **반려.** 소극적이며 출시 아티팩트의 시연·감사 가치를 떨어뜨린다. 노트는 이미 저장소에 공개된 provisional 문서라 `NOT_BOUND`를 유지할 정직상 이유(민감 정보·외부 의존)가 없다.
- (b) 소비 노트 2개만 번들 — **반려.** `/api/decisions`가 계속 `NOT_BOUND`이고 부분 번들은 일관되지 않다.
- (c) `docs/` 전체 번들 — **반려.** 핸드북·요구사항 문서는 런타임 입력이 아니다. 필요한 최소(소비 표면 + 인덱스 정합)만 담는다.
- (d) 노트를 생성 파이썬 모듈로 임베드 — **반려.** 체크아웃 바이트와 아티팩트 바이트의 digest 일치 증명을 깬다.

**게이트:** `scripts/build_release.py`의 entries 확장(번들 파일이 매니페스트 생성 전에 entries에 들어가야 함); `capital/terms.py`·`capital/policy.py`의 `default_note_path()`를 Traversable로; `capital/decisions.py`의 `docs_dir`·ledger 로드를 Traversable + exec로; `tests/test_release.py`의 `_BANNED`/`_expected_names` 갱신. 구현은 이 문서의 승인이 아니라 후속 노드다.

**아티팩트 라벨:** 선택한 경로에서는 아티팩트 내부 `/api/terms`→`BOUND`, `/api/policy`→`DECIDED`, `/api/decisions`→`BOUND`, `/api/underwrite`→`BOUND` (각 표면의 기존 판정 규칙 하에, `notes_source=BUNDLED_IN_ARTIFACT`). 미번들을 택했다면 이 표면들은 아티팩트 내부에서 계속 `NOT_BOUND`였을 것이다.

### 3.2 `artifact_digest_policy` — 다이제스트·매니페스트 정책

**결정값:**

- `manifest_format: "KIX_CAPITAL_RELEASE_V1"` 유지 (가산 변경, 스키마 불변).
- `files` 맵에 `docs/decisions/<name>.md`, `docs/CAP_COVERAGE.md`, `scripts/decision_ledger.py`의 sha256을 아카이브 이름 그대로 추가.
- 유지 필드: `signed:false`, `published:false`, `mode:"LOCAL_SIMULATION_ARTIFACT"`; `RELEASE-MANIFEST.json`은 자신을 `files`에 포함하지 않는 현행 규칙 유지; `protocol_commit`은 vendor FSM pin (`7481b0e1…`) — 의미 변경 없음. 노트의 provenance는 각자의 `files` sha256 + 노트 내부 `*_version`으로 표현.
- `.pyz` sha256 (build 출력)은 코드 + 번들 결정 코퍼스 전체를 포괄하는 내용 주소. docs 바이트 변경 → 다른 아티팩트 digest — **의도된 결합**.
- 새 verifier 없음. `python3 -m capital.verify`는 export manifest 전용으로 유지. smoke가 아카이브 멤버를 manifest와 재해시해도 된다.

**근거:** per-file 해시는 이미 있는 매니페스트 패턴의 확장이며, 자기 기술(self-describing) 아티팩트를 완성한다.

**대안:** (a) `docs_digest` 집계 필드 하나 — 반려(파일 단위 감사성 하락). (b) manifest format V2 bump — 반려(가산 변경으로 충분). (c) docs를 매니페스트에서 제외 — 반려(자기 기술성 파괴).

**게이트:** `scripts/build_release.py` 항목 순서, `test_release.py`의 manifest 어서션, smoke 재해시 여부.

**아티팩트 라벨:** `LOCAL_SIMULATION_ARTIFACT`·`signed:false`·`published:false` 유지 — 번들링이 서명·배포 승인을 만들지 않는다.

### 3.3 `not_bound_labeling` — 라벨링

**결정값:**

- 새 필드 `notes_source` ∈ `{CHECKOUT, BUNDLED_IN_ARTIFACT, OVERRIDE_FILE, NONE}` — `NONE`은 로드된 노트가 없을 때 (그때 상태는 `NOT_BOUND`; missing expected decision row는 `PENDING` 예외).
- 새 필드 `note_sha256` — 실제 로드한 노트 바이트의 sha256 hex; `NONE`이면 `null`.
- 추가 위치: `GET /api/terms`, `GET /api/terms/{id}`, `GET /api/terms/{id}/allocation`, `GET /api/policy`, `GET /api/policy/{id}`, `GET /api/underwrite/{id}`, `GET /api/decisions` (본문 + 행별), `GET /api/state`의 `terms` 스냅샷.
- 상태 어휘 불변: `BOUND`, `PARTIAL`, `NOT_BOUND`, `DECIDED`, `INVALID`, `PENDING`, `UNKNOWN_UNRESOLVED` — 새 상태 토큰을 만들지 않는다.
- 아티팩트 내부 `NOT_BOUND`의 의미: 번들 노트 부재·손상·INVALID·usable ADOPTED 항목 없음 — "docs를 담지 않았다"의 의미가 **아니다**.
- 아티팩트 내부 `BOUND`의 의미: "이 아티팩트가 번들한 provisional 노트 바이트에 바인딩됐다" — upstream 채택도, 운영 승인도, production 권한도 아니다.
- 실패 폐쇄: 손상된 번들 노트는 체크아웃과 똑같이 `INVALID`/`NOT_BOUND`로 떨어진다. 날조된 값으로 넘어가지 않는다.
- 변경 없는 라벨: `simulated overlay — not vendor FSM arithmetic, not an offer`; `simulated policy application — not executed distribution, not bank movement`; `simulated decision index — local note summary, not an adoption`; `simulated underwriting record — rule checks only, not an approval`; `provisional: true`; `policy_adopted: false`; `funds_executed: false`; `LOCAL_SIMULATION_ARTIFACT`; `signed: false`; `published: false`; `terms not bound`; `policy not bound`; `decision notes not bound`. 텍스트 라인(`PROVISIONAL per docs/decisions/… (V1)`)은 그대로 두고 출처는 구조화 필드가 나른다.

**근거:** 새 상태 토큰 대신 `notes_source` 필드를 두면 상태 어휘가 안정적이고 소비자 혼란이 없다. 번들했는데 `NOT_BOUND`라고 거짓 보고하는 것보다, `BOUND` + 출처 공개가 정직하다.

**대안:** (a) `BOUND_BUNDLED` 신규 상태 — 반려(어휘 파편). (b) 번들해도 `NOT_BOUND` 유지 — 반려(부정직). (c) 텍스트 라인에 `[bundled]` 접미 — 반려(구조화 필드로 충분).

**게이트:** 네 엔드포인트 응답 스키마, 핸드북 라벨 표, UI 문구.

**아티팩트 라벨:** 선택 경로 → `BOUND`/`DECIDED` with `notes_source=BUNDLED_IN_ARTIFACT`; 미선택 경로였다면 `NOT_BOUND` with `notes_source=NONE`.

**Supervisor clarification — ADOPTED 2026-10-23 (JunTae delegated ruling):**
Each endpoint/row hashes its actual loaded input bytes: terms and underwriting use
`CAPITAL_FINANCIAL_TERMS.md`, policy uses `CAPITAL_SETTLEMENT_POLICY.md`, and each
decision row uses its named note. The decision index body uses the named actual-note
anchor `docs/decisions/CAPITAL_FINANCIAL_TERMS.md`, never a collection digest.
A missing/unreadable input has `notes_source=NONE`, `note_sha256=null`, without fallback.
Missing expected rows remain `PENDING` with NONE/null as an explicit exception.
Readable invalid notes retain their actual source/hash and existing INVALID row behavior;
an absent or invalid body anchor makes the body NOT_BOUND while preserving available rows.
Explicit overrides are exclusive. These rules supersede the former §3.5 financial-terms-only
smoke comparison and apply equally to checkout and bundled execution.

### 3.4 `version_source_disclosure` — 버전·출처 공개

**결정값:**

- 단일 버전 출처 `capital/__init__.py.__version__` 유지; `--version` 출력 `kix-capital <version>` 불변; `package.json` 동기 규칙 유지.
- **git SHA를 아티팩트에 심지 않는다** — 빌드는 VCS를 읽지 않으므로 `.git` 없는 깨끗한 트리에서도 동일하게 재현된다. provenance는 digest 기반.
- provenance 공개 채널: `RELEASE-MANIFEST.json` per-file sha256; `notes_source`/`note_sha256`; 노트 내부 `terms_version`/`policy_version`/`bundling_version`.
- 동일 트리 동등 증명: 같은 트리에서 빌드한 pyz와 체크아웃 실행이 같은 `note_sha256`을 보고 → 시뮬레이션 대상의 바이트 동등성이 증명 가능.
- stale 공개: `.pyz`는 빌드 시점 노트 바이트를 서빙하며 이후 체크아웃 편집을 추적하지 않는다는 문장을 README·핸드북에 둔다.

**근거:** digest 기반 provenance는 이미 repo가 쓰는 방식(vendor manifest, export manifest)이며 VCS 비의존 빌드를 지킨다.

**대안:** (a) git commit 임베드 — 반려(빌드의 VCS 의존). (b) `--version`에 digest — 반려(버전은 버전). (c) 별도 BUILD-INFO 파일 — 반려(manifest가 이미 있다).

**게이트:** `GET /api/state`, `--version`, `docs/RELEASES.md`.

**아티팩트 라벨:** 버전 필드는 아티팩트 버전만 정직하게 나른다; 번들 출처 라벨은 `notes_source`에만 둔다.

### 3.5 `build_reproducibility` — 빌드 재현성

**결정값:**

- 보장 유지: 같은 소스 트리 + 같은 인터프리터 → byte-identical `.pyz` (`test_two_builds_match_and_archive_is_pinned`의 현재 보장).
- 제약: 번들 파일은 `read_bytes()`로 raw 바이트(개행·인코딩 정규화 없음); 열거는 `sorted(docs/decisions/*.md)` 최상위만; zip 메타 고정 — `date_time (1980,1,1,0,0,0)`, `create_system 3`, `external_attr 0o644`, `ZIP_STORED`, 이름 정렬 순서 — 불변; `__pycache__`/`.pyc` 제외 불변.
- 미주장: 크로스 플랫폼·크로스 인터프리터 바이트 동일성.
- 결합: docs 바이트 변경 → `.pyz` sha256 변경 (의도).
- 핀된 어서션 이동: `tests/test_release.py` `_BANNED`에서 `'docs/'` 제거 (`'tests/'`, `'.git'`, `'node_modules'`, `'.aiops'`, `'.github'`는 유지 — `docs/` 금지는 명시적 번들 허용목록 + `_expected_names` 완전 일치 검사로 대체). `_expected_names`에 번들 경로 추가.
- smoke 지시: packaged smoke가 `/api/terms`·`/api/policy`·`/api/decisions`의 `notes_source == BUNDLED_IN_ARTIFACT`를 확인하고, `note_sha256`이 실제 입력 노트의 매니페스트 항목과 같은지 대조하며 (terms/underwriting 및 decision body anchor: `CAPITAL_FINANCIAL_TERMS.md`; policy: `CAPITAL_SETTLEMENT_POLICY.md`; decision row: 해당 `note`), `/api/terms` status ∈ {BOUND, PARTIAL} 확인.

**근거:** 번들 추가는 결정론적 빌드를 깨지 않는다 — 이미 vendor·static이 같은 규칙으로 들어간다. docs 바이트와 digest의 결합은 취약점이 아니라 정직성 자산이다.

**대안:** (a) docs 바이트 정규화 — 반려(체크아웃 바이트와의 digest 일치 파괴). (b) 빌드 시 인덱스 사전 생성 후 정적 JSON만 번들 — 반려(런타임 검증·파서 단일 출처 포기). (c) 별도 docs zip — 반려.

**게이트:** `scripts/build_release.py`, `tests/test_release.py`, `verify.yml` package job의 `cmp` 비교.

**아티팩트 라벨:** 매니페스트 `files` 맵이 번들 docs의 존재를 기계 판독 가능하게 한다 — 라벨 자체가 구조화된 정직성이다.

### 3.6 `handbook_and_release_docs` — 핸드북·릴리스 문서

**결정값:**

- 구현 시 함께 갱신: `README.md` (zipapp NOT_BOUND 문장들), `docs/OPERATOR_HANDBOOK_KO.md` (라벨 표의 pyz 문장, terms-overlay/policy-simulator/decision-status-surface 절, 새 `handbook-section:artifact-docs-bundling` 절 추가), `docs/INTEGRATION.md` ("until a release decision bundles the note"의 지시 대상 = 이 노트), `docs/RELEASES.md` (Contents 목록 + 번들 빌드 새 entry), `capital/server.py` `--terms-note`/`--policy-note` help ("Not bundled in the zipapp" 제거), `docs/VALIDATION.md`·`docs/ACCEPTANCE_KO.md`의 낡은 pyz-NOT_BOUND 문장 (구현 노드가 grep으로 찾아 수정).
- release entry 규칙: 기존 `## 0.1.0` 기록은 **그대로 둔다** — 그 시점 빌드는 docs를 담지 않았다는 정직한 기록이므로 덮어쓰지 않는다. 번들 빌드는 새 entry에 자체 SHA256으로 기록.
- 버전: 번들링 구현이 병합될 때 `__version__`을 `0.2.0`으로 bump — 아티팩트의 서빙 표면이 바뀌는 변경이다.
- `docs/CAP_COVERAGE.md`는 이 PR이 단일 파일 diff라 갱신하지 않는다 — 후속 sync에서 이 노트를 인용한다 (ledger는 coverage 비인용 노트를 extra로 색인하므로 지금도 통과한다).
- 변경 없음: auth matrix·역할 표, export manifest 스키마·`content_digest`, `tests/golden/demo.json`, vendor pin — 노트는 저널·receipt·`state_digest`에 들어가지 않는다.

**근거:** 문서가 코드와 함께 움직이지 않으면 NOT_BOUND 시절의 문장이 거짓이 된다. 역사 기록의 덮어쓰기 금지와 버전 bump는 모두 정직성 규칙의 연장이다.

**대안:** (a) 0.1.0 entry 갱신 — 반려(역사 재작성). (b) 버전 유지 — 반려(관측 가능한 표면 변화를 숨김). (c) 핸드북도 번들 — 반려(런타임 입력 아님).

**게이트:** packaging-release 구현 노드의 docs 체크리스트.

**아티팩트 라벨:** 문서 전체가 "번들 = 아티팩트 내부 BOUND"와 "upstream 채택·production 승인 아님"을 함께 설명해야 한다.

## 4. 기계 판독 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "artifact-docs-bundling-decision",
  "decided_by": "Devin swe-2 (RO by prompt), delegated by JunTae 2026-10-08 (model 10-14 10:07)",
  "date": "2026-10-14",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "scope": "KIX-CAPITAL simulation and product design only; docs-only decision; not an offer; no real money; production NOT_AUTHORIZED; bundling implementation, signing, publishing and deployment are separate later actions; legal, tax, accounting and licensing mentions are working assumptions pending professional review",
  "delegation": "2026-10-08 18:25 KST JunTae Park delegated financial terms, settlement policy, upstream binding and accounts/tax/legal with the instruction to proceed with the grand ambition in mind; the historical quote names Fable but as of 2026-10-14 10:07 the decider for this node is Devin swe-2 and Fable/claude-fable-5-1 is audit-only",
  "bases": {
    "capital_main": "8787278",
    "kix_protocol_main": "adcddc5",
    "vendor_pin_commit": "7481b0e16ce9b903abbffa62249bb91cd9e63cfe",
    "pinned_credit_fsm_sha256": "f4f6b3698dd848538d2efa10b276cb33659eb4877fcbea0feb7429b28456491b",
    "pinned_mock_credit_sha256": "5e75fcc76fb0857f671b2fa33ca0fc851e9d676d4b5db8f357393367bc725d95",
    "prior_capital_decisions": [
      "docs/decisions/CAPITAL_FINANCIAL_TERMS.md (CAPITAL-TERMS-V1)",
      "docs/decisions/CAPITAL_SETTLEMENT_POLICY.md (CAPITAL-SETTLEMENT-POLICY-V1)",
      "docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md",
      "docs/decisions/CAPITAL_UPSTREAM_BINDING.md"
    ]
  },
  "bundling_version": "CAPITAL-ARTIFACT-BUNDLING-V1",
  "artifact_honesty_label": {
    "chosen": {"notes_source": "BUNDLED_IN_ARTIFACT", "terms": "BOUND", "policy": "DECIDED", "decisions": "BOUND", "underwrite": "BOUND"},
    "rejected_alternative": {"notes_source": "NONE", "terms": "NOT_BOUND", "policy": "NOT_BOUND", "decisions": "NOT_BOUND", "underwrite": "NOT_BOUND"},
    "signed": false,
    "published": false,
    "mode": "LOCAL_SIMULATION_ARTIFACT",
    "production": "NOT_AUTHORIZED"
  },
  "upstream_adoption_claimed": false,
  "implementation_authorized": false,
  "entries": {
    "notes_bundling_scope": {
      "status": "ADOPTED",
      "value": {
        "bundle": true,
        "bundled_paths": {
          "docs/decisions/*.md": "all decision notes present at build time, top level only, non-recursive, enumerated sorted",
          "docs/CAP_COVERAGE.md": "expected-path ordering source for the decision index",
          "scripts/decision_ledger.py": "the single ledger parser source, loaded by exec/compile from bundled bytes"
        },
        "archive_layout": "identical relative paths at the archive root",
        "load_mechanism": "importlib.resources.files('capital').parent Traversable; pathlib.Path in checkout, zipfile.Path in zipapp; one code path; enumeration via iterdir() for Python 3.10 compatibility",
        "ledger_parser": "exec/compile of bundled source bytes; no vendored copy; scripts/decision_ledger.py stays the single parser source and still must not import capital",
        "excluded": ["docs/ all other files", "scripts/ all other files", "tests/", ".github/", ".aiops/", "node_modules/", "build/", "dist/", ".git/"],
        "inside_artifact_effect": {
          "GET /api/terms": "BOUND under CAPITAL-TERMS-V1 as bundled (same BOUND/PARTIAL/NOT_BOUND rules as checkout)",
          "GET /api/policy": "DECIDED under CAPITAL-SETTLEMENT-POLICY-V1 as bundled",
          "GET /api/decisions": "BOUND with a row per bundled note",
          "GET /api/underwrite/{id}": "evaluable when the bundled terms note is BOUND",
          "--terms-note/--policy-note": "CLI overrides keep working; notes_source reports OVERRIDE_FILE"
        },
        "still_not_bound": ["producer tuple (CAP-07, CAP-16)", "durable operating ledger (CAP-11)", "authentication/IdP/KYC (CAP-19)", "bank/PG/provider observations (CAP-09, CAP-14)", "stage7 authenticated export and source cut (CAP-15)", "RS/TL/AI grant lanes (CAP-17, CAP-18, CAP-19)"],
        "upstream_adoption_claimed": false
      },
      "provided_by": "Devin swe-2 (RO by prompt), delegated by JunTae 2026-10-08 (model 10-14 10:07)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-01", "CAP-02", "CAP-04", "CAP-05", "CAP-20"],
      "rationale": "A zipapp that reports NOT_BOUND on every decision surface is a degraded product; decision notes are policy inputs of the same kind as the vendored FSMs already bundled; bundling makes the artifact self-contained and self-describing with hashable provenance",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "alternatives_rejected": ["checkout-only with NOT_BOUND inside the artifact (timid, lowers demo/audit value, no honesty reason since notes are already public provisional documents)", "bundle only the two consumer notes (leaves /api/decisions NOT_BOUND; partial bundling is inconsistent)", "bundle all of docs/ (handbook and requirements docs are not runtime inputs)", "embed notes as generated python (breaks byte-identity/digest equality with checkout notes)"],
      "consumer": "scripts/build_release.py; capital/terms.py; capital/policy.py; capital/decisions.py; capital/underwriting.py",
      "gates": ["build_release entries extension before manifest generation", "default_note_path() switched to Traversable", "DecisionIndex docs_dir and ledger load switched to Traversable + exec-of-source", "tests/test_release.py _BANNED/_expected_names updated"],
      "revisit_triggers": ["artifacts circulate beyond the dev loopback", "signing or publishing is ever authorized", "the ledger parser grows a capital import"]
    },
    "artifact_digest_policy": {
      "status": "ADOPTED",
      "value": {
        "manifest_format": "KIX_CAPITAL_RELEASE_V1",
        "files_map_additions": "every bundled path in notes_bundling_scope enters RELEASE-MANIFEST.json files{} with the sha256 of its archive bytes under its archive name",
        "unchanged_fields": {"signed": false, "published": false, "mode": "LOCAL_SIMULATION_ARTIFACT", "protocol_commit": "vendor FSM pin commit 7481b0e1, meaning unchanged"},
        "self_hash_rule": "RELEASE-MANIFEST.json is still not listed in its own files map",
        "artifact_digest": "sha256 printed by build_release now covers runtime code plus the bundled decision corpus; a docs byte change produces a different artifact digest — intended content-address coupling",
        "verification": "no new verifier; python3 -m capital.verify stays export-manifest-only; smoke may re-hash archive members against RELEASE-MANIFEST.json"
      },
      "provided_by": "Devin swe-2 (RO by prompt), delegated by JunTae 2026-10-08 (model 10-14 10:07)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-15", "CAP-20"],
      "rationale": "Per-file sha256 extends the existing manifest pattern and makes the artifact self-describing; aggregate digest fields or a format bump add no auditability over per-file entries",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "alternatives_rejected": ["single docs_digest aggregate field (less auditable)", "manifest format bump to V2 (additive change needs none)", "exclude docs from the manifest (breaks self-describing property)"],
      "consumer": "scripts/build_release.py; scripts/smoke_release.py; tests/test_release.py; docs/RELEASES.md",
      "gates": ["bundled entries must land in the entries dict before the manifest is generated"],
      "revisit_triggers": ["RELEASE-MANIFEST format ever needs a V2", "signed artifacts make manifest semantics stronger"]
    },
    "not_bound_labeling": {
      "status": "ADOPTED",
      "value": {
        "new_fields": {
          "notes_source": ["CHECKOUT", "BUNDLED_IN_ARTIFACT", "OVERRIDE_FILE", "NONE"],
          "note_sha256": "hex sha256 of actual loaded note bytes; terms/underwriting and decision body anchor CAPITAL_FINANCIAL_TERMS.md; policy CAPITAL_SETTLEMENT_POLICY.md; rows their named note; null when NONE; missing expected rows remain PENDING with NONE/null; readable invalid rows preserve INVALID and source/hash"
        },
        "fields_added_to": ["GET /api/terms", "GET /api/terms/{id}", "GET /api/terms/{id}/allocation", "GET /api/policy", "GET /api/policy/{id}", "GET /api/underwrite/{id}", "GET /api/decisions (body and per-row)", "GET /api/state terms snapshot"],
        "status_vocabulary_unchanged": ["BOUND", "PARTIAL", "NOT_BOUND", "DECIDED", "INVALID", "PENDING", "UNKNOWN_UNRESOLVED"],
        "not_bound_meaning_inside_artifact": "bundled note absent, malformed, INVALID or lacking a usable ADOPTED entry — never 'docs are not shipped'",
        "bound_meaning_inside_artifact": "the artifact is bound to the provisional note bytes it bundles; not an upstream adoption, not production authority",
        "labels_unchanged": ["simulated overlay — not vendor FSM arithmetic, not an offer", "simulated policy application — not executed distribution, not bank movement", "simulated decision index — local note summary, not an adoption", "simulated underwriting record — rule checks only, not an approval", "provisional: true", "policy_adopted: false", "funds_executed: false", "LOCAL_SIMULATION_ARTIFACT", "signed: false", "published: false", "terms not bound", "policy not bound", "decision notes not bound"],
        "fail_closed": "a malformed bundled note yields INVALID/NOT_BOUND exactly as in checkout; no fallback to invented terms",
        "reason_strings_unchanged": true
      },
      "provided_by": "Devin swe-2 (RO by prompt), delegated by JunTae 2026-10-08 (model 10-14 10:07)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-01", "CAP-02", "CAP-20"],
      "rationale": "A structured notes_source field carries the bundled/checkout distinction without fragmenting the status vocabulary; BOUND plus provenance disclosure is more honest than either a new BUNDLED status or falsely reporting NOT_BOUND",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "alternatives_rejected": ["new BOUND_BUNDLED status token (fragments vocabulary)", "report NOT_BOUND even when bundled (dishonest)", "text-line [bundled] suffix (structured fields suffice)"],
      "consumer": "server response schemas; operator handbook label table; UI copy",
      "gates": ["four endpoint response schemas", "/api/state terms snapshot"],
      "revisit_triggers": ["any surface drops the provisional banners", "a real producer tuple binds and needs its own source enum"]
    },
    "version_source_disclosure": {
      "status": "ADOPTED",
      "value": {
        "version_single_source": "capital/__init__.py __version__; --version stays 'kix-capital <version>'; package.json sync rule unchanged",
        "no_vcs_embed": "the build does not read or embed a git commit; provenance is digest-based so a clean tree without .git rebuilds identically",
        "provenance_channels": ["RELEASE-MANIFEST.json per-file sha256 for every bundled doc", "notes_source and note_sha256 on the four surfaces and the /api/state terms snapshot", "note-internal *_version fields (terms_version, policy_version, bundling_version)"],
        "same_tree_equality": "a checkout run and a pyz built from the same tree report identical note_sha256 values — provable byte equality of what is being simulated",
        "stale_artifact_disclosure": "a .pyz serves the note bytes it was built with and does not track later checkout edits; README and the operator handbook must state this"
      },
      "provided_by": "Devin swe-2 (RO by prompt), delegated by JunTae 2026-10-08 (model 10-14 10:07)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-15", "CAP-20"],
      "rationale": "Digest-based provenance matches the existing vendor and export manifest discipline and keeps the build free of VCS dependence",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "alternatives_rejected": ["embed git commit into the manifest (build-time VCS dependence breaks clean-tree rebuilds)", "note digest inside --version output (a version string stays a version)", "separate BUILD-INFO file (the manifest already exists)"],
      "consumer": "GET /api/state; --version; docs/RELEASES.md",
      "gates": ["state endpoint disclosure fields"],
      "revisit_triggers": ["artifact distribution beyond the dev loopback requires source-commit disclosure"]
    },
    "build_reproducibility": {
      "status": "ADOPTED",
      "value": {
        "guarantee": "same source tree plus same interpreter produces byte-identical .pyz (retained)",
        "constraints": ["bundled files are read with read_bytes() — no newline or encoding normalization", "deterministic enumeration: sorted(docs/decisions/*.md) top level only", "zip metadata unchanged: date_time (1980,1,1,0,0,0), create_system 3, external_attr 0o644, ZIP_STORED, sorted entry order", "__pycache__ and .pyc exclusions unchanged"],
        "not_claimed": "byte identity across platforms or interpreter versions",
        "digest_coupling": "any bundled docs byte change changes the .pyz sha256 (intended)",
        "pinned_assertions_to_update": ["tests/test_release.py _BANNED drops 'docs/' — tests/, .git, node_modules, .aiops, .github stay banned and _expected_names equality forbids strays", "test_two_builds_match_and_archive_is_pinned _expected_names gains the bundled paths"],
        "smoke_direction": ["packaged smoke asserts notes_source == BUNDLED_IN_ARTIFACT on /api/terms, /api/policy, /api/decisions", "note_sha256 equals the manifest entry for the actual loaded note: terms/underwriting and decision body anchor CAPITAL_FINANCIAL_TERMS.md; policy CAPITAL_SETTLEMENT_POLICY.md; each decision row its named note", "/api/terms status in [BOUND, PARTIAL] under the bundled CAPITAL-TERMS-V1 note"]
      },
      "provided_by": "Devin swe-2 (RO by prompt), delegated by JunTae 2026-10-08 (model 10-14 10:07)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-20"],
      "rationale": "Bundling does not break the deterministic build — vendored and static files already enter under the same rules — and the docs-to-digest coupling is an honesty asset, not a defect",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "alternatives_rejected": ["normalize doc bytes at build time (breaks digest equality with checkout files)", "pre-generate the index and bundle a static JSON (gives up runtime validation and single parser source)", "ship docs in a separate archive"],
      "consumer": "scripts/build_release.py; tests/test_release.py; .github/workflows/verify.yml package job",
      "gates": ["verify.yml package job's dist vs dist2 cmp check must still pass"],
      "revisit_triggers": ["cross-platform byte identity is ever claimed", "build moves to a different packager"]
    },
    "handbook_and_release_docs": {
      "status": "ADOPTED",
      "value": {
        "docs_updated_at_implementation": ["README.md (zipapp-NOT_BOUND sentences)", "docs/OPERATOR_HANDBOOK_KO.md (label table pyz sentence; terms-overlay, policy-simulator, decision-status-surface sections; new handbook-section:artifact-docs-bundling)", "docs/INTEGRATION.md (the 'does not bundle docs' sentences — the 'until a release decision' pointer resolves to this note)", "docs/RELEASES.md (Contents list plus a new entry for the bundled build)", "capital/server.py --terms-note/--policy-note help text ('Not bundled in the zipapp' removed)", "docs/VALIDATION.md and docs/ACCEPTANCE_KO.md (any stale pyz-NOT_BOUND sentences found by grep)"],
        "release_entry_rule": "the existing 0.1.0 entry stays unchanged — it honestly recorded an unbundled build; the bundled build gets a new entry with its own SHA256",
        "version_bump": "__version__ goes to 0.2.0 when bundling lands — the artifact's served surface changes",
        "coverage_citation": "docs/CAP_COVERAGE.md cites this note in a later sync diff; the ledger indexes this note as an extra until then and still passes",
        "unchanged": ["auth matrix and role table", "export manifest schema and content_digest", "tests/golden/demo.json", "vendor pin set"]
      },
      "provided_by": "Devin swe-2 (RO by prompt), delegated by JunTae 2026-10-08 (model 10-14 10:07)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-20"],
      "rationale": "Docs must move with code or the NOT_BOUND-era sentences become false; preserving the 0.1.0 record and bumping the version are both honesty rules",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "alternatives_rejected": ["rewrite the 0.1.0 entry in place (rewrites history)", "keep __version__ 0.1.0 (hides the observable surface change)", "bundle the handbook too (not a runtime input)"],
      "consumer": "docs set; packaging-release implementation checklist; release acceptance",
      "gates": ["implementation PR must update the listed docs in the same diff or a paired sync"],
      "revisit_triggers": ["a second bundled build ships without a release-note entry"]
    }
  }
}
```

## 5. 수용 기준 매핑

| 수용 항목 | 이 문서에서 충족하는 위치 |
|---|---|
| `docs/decisions/CAPITAL_ARTIFACT_BUNDLING.md` 존재 + `capital-decision-v1` 블록 하나가 모든 decision_item을 커버 + `python3 scripts/decision_ledger.py` 통과 | 이 파일 자체. §4 블록은 `notes_bundling_scope`·`artifact_digest_policy`·`not_bound_labeling`·`version_source_disclosure`·`build_reproducibility`·`handbook_and_release_docs` 여섯 항목 전부를 `ADOPTED`로 담고, 각 entry는 `value`(non-null)·`provided_by`·`date`·`cap_rows`(CAP-01~CAP-20 범위)·`rationale`·`provisional`을 갖는다 — `scripts/decision_ledger.py`의 `_validate_entry` ADOPTED 규칙과 일치. fence는 정확히 하나. 이 노트는 coverage 미인용 상태에서 extra로 색인되며 `collect_errors`는 기존 파일의 오류만 보므로 exit 0을 유지한다. |
| 선택지별 아티팩트 정직 라벨 (zipapp 내부 BOUND vs NOT_BOUND) 명시 + `signed:false`/`published:false`/`LOCAL_SIMULATION_ARTIFACT` 유지 | §3 각 항목의 "아티팩트 라벨" 행이 선택/미선택 양쪽의 라벨을 명시한다. §4 `artifact_honesty_label` 필드에 chosen(`BUNDLED_IN_ARTIFACT` → `BOUND`/`DECIDED`)과 rejected alternative(`NONE` → `NOT_BOUND`), 그리고 `signed:false`·`published:false`·`mode:LOCAL_SIMULATION_ARTIFACT`·`production:NOT_AUTHORIZED`가 기계 판독 가능하게 들어 있다. |
| diff가 `docs/decisions/CAPITAL_ARTIFACT_BUNDLING.md` 하나만 건드림 | 이 결정은 문서 하나의 추가만 요구한다. 코드·빌드·테스트·coverage 변경은 전부 후속 구현 노드로 게이트했다(§3.1 게이트, §6). |

## 6. Open risks

- **낡은 아티팩트 위험.** 오래된 `.pyz`는 빌드 시점의 provisional 노트를 서빙한다 — 노트가 개정돼도 예전 pyz는 예전 정책을 보고한다. `note_sha256`·`notes_source`·`*_version`·RELEASES entry가 이를 드러내지만, 아티팩트가 dev loopback 밖으로 유통되기 시작하면 재검토 트리거다.
- **과대 주장 위험.** 아티팩트 내부 `BOUND`를 upstream 채택으로 오독할 수 있다. 어느 표면이든 provisional 배너·`policy_adopted:false`·`simulated … not …` 라벨이 빠지면 이 결정 전체를 재검토한다.
- **재현성 드리프트.** 플랫폼별 개행·파일 순서 차이로 바이트가 갈릴 수 있다 — raw bytes·정렬 열거로 방어하되, 크로스 플랫폼 동일성을 주장하게 되면 재검토.
- **파서 드리프트.** exec-of-source는 파서 단일 출처를 지키지만, `decision_ledger.py`가 `capital`을 import하게 되면 아카이브 내부 로드가 깨진다 — 그때 재검토 (파서를 `capital/`로 옮기는 대안 포함).
- **매니페스트 결합.** `RELEASE-MANIFEST.json`에 docs 섹션이나 V2가 필요해지면 digest 정책을 연다.
- **코퍼스 성장.** 결정 노트가 늘면 아티팩트도 선형으로 커진다 — 현재 크기는 무시 가능하지만 임계(~1MB) 근처에서 범위를 재검토.
- **서명·게시된 미래.** `signed:true`나 `published:true`가 승인되는 날, 번들된 provisional 문서가 더 강한 주장 의미를 얻으므로 이 결정 전체를 재검토해야 한다.
- **전문가 검토 항목.** 이 결정은 법률·세무·회계·면허 값을 새로 정하지 않으므로 새 검토 의무를 만들지 않는다. 다만 번들된 `CAPITAL_ACCOUNTS_TAX_LEGAL.md`는 자신의 `WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW` 라벨을 그대로 운반한다 — 번들이 그 검토를 대체하지 않는다.

## 7. 후속 작업

| 소비자 | 이 결정을 쓰는 방식 |
|---|---|
| `packaging-release` (구현 노드) | `scripts/build_release.py`에 번들 경로 추가(매니페스트 생성 전 entries), `_BANNED`·`_expected_names` 갱신, `verify.yml` package job의 두 빌드 `cmp` 통과 유지 |
| `terms-overlay` | `capital/terms.py` `default_note_path()`를 Traversable로 전환; `notes_source`/`note_sha256` 응답 추가 |
| `policy-simulator` | `capital/policy.py` 동일 전환 |
| decision index | `capital/decisions.py` — `docs_dir` Traversable, coverage/`*.md` 열거는 `iterdir`, ledger는 번들 소스 `exec`/`compile` |
| `underwriting`/`server` | 포트 주입으로 상속; `--terms-note`/`--policy-note` help 갱신 |
| release acceptance | packaged smoke에 `notes_source == BUNDLED_IN_ARTIFACT`·`note_sha256 == manifest entry`·status ∈ {BOUND, PARTIAL} 검사 추가 |
| external gate | 변경 없음 — 정직 라벨·`NOT_AUTHORIZED`·`signed:false`·`published:false`가 그대로 외부 게이트의 소비 입력 |
| handbook/release docs | §3.6 목록 갱신 + `CAP_COVERAGE.md` 인용 sync + 0.2.0 release entry |

**명시적 범위 밖:** 번들링의 구현, 서명, 게시, 배포, 실자금·secrets 조작 — 전부 별도 노드·별도 승인이며 money/deploy/secrets는 `PENDING_OWNER_ACTION`으로 남는다. 이 문서는 어느 upstream 계약도 채택하지 않았고, 어느 잠금도 해제하지 않는다.
