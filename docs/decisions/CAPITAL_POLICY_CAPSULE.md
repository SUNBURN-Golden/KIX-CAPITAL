# Capital 정책 캡슐 결정 — 로컬 포착 금융 증거와 나란히 보존하는 정책 입력 사이드카

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
이 문서는 KIX-CAPITAL 저장소 안의 **시뮬레이션·제품 설계용** 결정이다. 청약이나 대출 제안이 아니고, 실자금이 움직이지 않으며, production은 계속 `NOT_AUTHORIZED`다. 어떤 upstream 계약의 채택도 주장하지 않고 SEMANTIC_CONFORMANCE도 주장하지 않는다. diff는 `docs/decisions/CAPITAL_POLICY_CAPSULE.md` 한 파일이고, `capital/`·`tests/`·vendor 바이트·골든·workspace envelope·기존 결정 노트의 상태 토큰은 건드리지 않는다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `policy-capsule-decision` (Decision: preserve policy inputs alongside locally captured financial evidence) · deps `artifact-docs-bundling-decision`, `overlay-digest-export-decision`, `portfolio-history-comparison` · kind `decision` · user_merge `False` |
| 결정자 | **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)** |
| 위임 원문 | 2026-10-08 18:25 KST JunTae Park: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." |
| 결정일 | 2026-11-02 |
| KIX-CAPITAL 기준 | main `c4114c7` |
| kix-protocol 기준 | `fd33335` (읽기 전용 `/workspace/capital-run/kixproto-ro`) |
| 읽기 범위 | supervisor pack이 허용한 경로만 읽었다. deps 중 `CAPITAL_OVERLAY_DIGEST_EXPORT.md`는 허용 경로 밖이라 **직접 열지 않았다.** envelope 어휘(`WORKSPACE_ENVELOPE_V2|V3`, `manifest_sha256`, `workspace_id`)는 노드 명세와 허용 노트의 인용으로만 참조한다. **필드명이 충돌하면 선행 노트가 이기고, 캡슐 형식·판정 규칙은 이 노트가 이긴다.** |
| 상태 어휘 | **ADOPTED** = 위임 범위 안의 잠정 값. **UNDETERMINED** = 값을 정할 수 없어 이유만(`value: null`, 방향은 `target`). 여섯 항목 모두 ADOPTED다 |

## 1. 결정 요약

| item | 결정 (요지) | CAP rows | 소비 노드 / seam |
|---|---|---|---|
| `capsule_contents` | **ADOPTED.** `CAPITAL-POLICY-CAPSULE-V1`: 데이터 전용 JSON 사이드카. 노트 바이트 원문(base64)·`note_sha256`·경로, workspace 약속(`workspace_id`·`manifest_format`·`manifest_sha256`), evaluator 식별 블록. 실행 코드·evaluator 바이트·upstream 바이트는 들어가지 않는다 | CAP-15, CAP-20 | offline capture/verify 스크립트 후속 노드 |
| `workspace_and_policy_binding` | **ADOPTED.** 캡슐은 추가형이다. workspace와는 `manifest_sha256`로만 묶이고 V2/V3 envelope·manifest·비교 산술 바이트는 절대 재작성하지 않는다. 정책과는 노트 원문 바이트+sha256로 묶인다 | CAP-14, CAP-15 | portfolio-history-comparison·export 표면 |
| `capture_time_evidence_grade` | **ADOPTED.** 세 등급 어휘: `CAPTURE_TIME_POLICY_EVIDENCE`(캡슐의 유일한 주장) / `AUTHENTICATED_HISTORICAL_POLICY`(주장 안 함) / `ORIGINAL_DRAW_TIME_PROVENANCE`(주장 안 함, 구 workspace에 소급 출처 없음) | CAP-09, CAP-20 | 모든 캡슐 소비자·export 라벨 |
| `evaluator_identity` | **ADOPTED.** 식별 = `{name, version, source_pin, notes_source, interface}`. `notes_source`는 번들링 노트의 열거(`CHECKOUT/BUNDLED_IN_ARTIFACT/OVERRIDE_FILE/NONE`)를 그대로 쓴다. 식별은 기술적(description)이지 인증·버전 승인이 아니다 | CAP-01, CAP-02 | terms-overlay·policy-simulator 조회 경로 |
| `compatibility_and_refusal_rules` | **ADOPTED.** 캡슐 도중 노트 변경 → `CAPTURE_INCONSISTENT`; 노트 부재 → `INCOMPLETE`+`MISSING_NOTE`; evaluator 불일치 → `NOT_EVALUATED`; 기록된 terms 바인딩과 불일치 → `BINDING_DISAGREEMENT`+`REFUSE`. 기록된 바인딩이 역사적 사실로 우선하고 캡슐은 덮어쓰지 않는다 | CAP-04, CAP-20 | verify 경로 판정 표 |
| `storage_and_consumption_scope` | **ADOPTED.** 첫 소비자는 **오프라인 포착+검증**뿐. 저장은 workspace export 옆 사이드카(`*.policy-capsule.json`)와 선택적 커밋 fixture. 라벨 `LOCAL_SIMULATION_ARTIFACT`/`SIMULATED`. 역사 재생(replay)의 전제조건은 별도 절에 기술하되 채택하지 않는다. CAP-11·CAP-16은 `NOT_BOUND` 유지 | CAP-11, CAP-15 | 후속 capture 노드·미래 replay 후보 |

## 2. KIX 비전과의 연결

읽은 팩 경로와 적용이다(인용은 이 팩의 경로로 한정).

- **기록과 재생의 필수 분리.** `/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md`의 승인 A-4 — "과거 사실 재생은 새로운 외부 실행 허가가 아니"고 "과거에 유효했던 약정은 당시 의미와 증거로 복원"한다 — 이 `capture_time_evidence_grade`의 정본이다. 캡슐은 *기록*이지 *재생 허가*가 아니다.
- **권위 모델 경계.** 같은 문서와 `/workspace/capital-run/kixproto-ro/README.md`(모델 1: 체인 권위/오프체인 위임 실행, 실자금·체인 보증 없음)는 캡슐이 오프체인 증거이며 온체인 권위·인증을 주장하지 않는 근거다.
- **번들링·라벨 선행.** `docs/decisions/CAPITAL_ARTIFACT_BUNDLING.md`의 `notes_source` 열거와 `note_sha256` 표면·`RELEASE-MANIFEST.json` per-file SHA256 규칙을 `evaluator_identity`와 캡슐 다이제스트에 그대로 재사용한다. `signed:false`·`published:false`·`LOCAL_SIMULATION_ARTIFACT` 라벨도 계승한다.
- **결정론적 다이제스트 선행.** `docs/decisions/CAPITAL_CLOSEOUT_ARTIFACT.md`의 "per-run 필드를 제거한 결정론적 다이제스트" 패턴을 캡슐의 `volatile` 분리에 적용한다.
- **비교·envelope 불변.** `docs/VALIDATION.md`의 portfolio history comparison(워크스페이스 비교는 fixture 게이트, 바이트 보존)이 `workspace_and_policy_binding`의 "envelope·manifest·비교 의미론 불변" 조건이다.
- **정직 라벨.** `docs/decisions/CAPITAL_DEMO_BOOK.md`의 `SYNTHETIC_*` 라벨 규칙과 `docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md`의 `WORKING_ASSUMPTION` 태도를 캡슐 라벨에 따른다. `docs/SEAMS.md`·`docs/CAPITAL_REQUIREMENTS_KO.md`의 `NOT_BOUND` 어휘를 유지한다.

## 3. 항목별 결정

공통 라벨: 모든 값은 `basis = PRODUCT_DECISION`, `provisional = true`다.

### 3.1 capsule_contents (CAP-15, CAP-20)

- **값.** 형식 `KIX_CAPITAL_POLICY_CAPSULE_V1`, 단일 JSON 문서, UTF-8. 최상위 필드:
  - `format`, `capsule_version`("V1"), `capsule_digest`(아래 digestible 부분집합의 canonical JSON SHA256).
  - `subject`: `{workspace_id, manifest_format ∈ {WORKSPACE_ENVELOPE_V2, WORKSPACE_V3, OTHER}, manifest_sha256, export_digests[]}` — 모두 **참조**(digest)만, envelope 바이트 재포함 없음.
  - `policy_inputs.notes[]`: `{path(repo-relative POSIX), note_sha256, bytes_len, encoding:"utf-8", bytes_b64, binding_role}`. 대상 집합은 **유계(bounded)**: 포착 표면이 해석하는 `docs/decisions/*.md` 결정 노트와 그 노트가 참조하는 coverage 문서만. 코드·fixture·vendor 바이트·실행물은 어떤 형태로도 포함하지 않는다.
  - `policy_inputs.terms_bindings[]`: workspace 표면이 이미 기록한 바인딩(`note_sha256`, terms 버전 참조 예 `CAPITAL-TERMS-V1` **이름 인용만**, 숫자 복사 금지 — `한도 출처 규칙`과 같은 원칙).
  - `evaluator`: §3.4.
  - `capture`: `{tool, tool_version, volatile{…}}` — 시각·호스트·로컬 경로 등 per-run 값은 `volatile`에만 두고 `capsule_digest`에서 제외한다(closeout 다이제스트 선례).
  - `evidence_grade`, `status`(§3.3, §3.5).
- **근거.** "정확한 노트 바이트 + 해시 + workspace 약속 + evaluator 식별"이 수용 기준이 요구하는 최소 완전 집합이다. 바이트 원문을 넣되 유계 집합으로 제한하면 재현 검증이 가능하고 증거 안에 실행 코드가 섞이지 않는다.
- **대안.** 해시만 기록: 노트가 체크아웃에서 사라지면 검증 불가라 기각. checkout 전체 스냅샷: 비유계·코드 혼입이라 기각.

### 3.2 workspace_and_policy_binding (CAP-14, CAP-15)

- **값.** (1) 캡슐→workspace 결합은 `manifest_sha256` + `workspace_id` 한 쌍이다. V2/V3 manifest·envelope·`section-*`/`content-digest` 벡터·비교 산술은 **한 바이트도 바꾸지 않는다** — 캡슐은 옆에 놓이는 사이드카다. (2) 캡슐→정책 결합은 `notes[].note_sha256`과 `terms_bindings[]`의 digest 대조다. (3) envelope digest가 없는 workspace(구 fixture 등)는 `manifest_sha256: null` + `binding_note`를 기록하고 포착은 허용하되 검증 등급은 §3.3 상한을 넘지 않는다.
- **근거.** 역사 workspace를 다시 쓰지 않는다는 노드 목적 그대로다. 추가형 결합만이 기존 비교 의미론을 보존한다.
- **대안.** envelope 안에 캡슐 참조 삽입: 역사 바이트 재작성이라 기각.

### 3.3 capture_time_evidence_grade (CAP-09, CAP-20)

- **값.** `evidence_grade` 필드는 정확히 `CAPTURE_TIME_POLICY_EVIDENCE`다. 의미: "캡처 시점에 이 evaluator가 해석한 정책 입력이 이 바이트들이었다." 다음 둘은 **명시적 비주장** 라벨로 문서·필드에 남긴다: `AUTHENTICATED_HISTORICAL_POLICY: false`(서명·인증 없음), `ORIGINAL_DRAW_TIME_PROVENANCE: false`(인출 시점 출처 아님). 캡슐이 없던 과거 workspace는 어떤 소급 출처 주장도 받지 않는다 — 오늘 포착한 캡슐은 "포착일의 노트"를 증명할 뿐 "인출일의 노트"를 증명하지 않는다.
- **근거.** A-4의 기록/재생 분리와 `signed:false` 번들 선행에 정확히 대응한다.
- **대안.** "best-effort provenance" 중간 등급: 애매한 주장이 오독을 부르므로 기각 — 등급은 셋으로 닫는다.

### 3.4 evaluator_identity (CAP-01, CAP-02)

- **값.** `evaluator = {name, version, source_pin, notes_source, interface}`. `source_pin`은 체크아웃 main SHA 또는 아티팩트 manifest SHA256 중 캡처 경로가 실제로 쓴 것. `notes_source`는 `CAPITAL_ARTIFACT_BUNDLING`의 열거를 그대로 쓴다. **evaluator 실행 바이트는 넣지 않는다** — 식별은 "어떤 evaluator였는가"의 기술이지 그 버전의 정확성·승인이 아니다. 구 evaluator 결과의 자동 수용은 범위 밖(노드 명세)이며 이 항목은 그 자동 수용을 만들지 않는다.
- **근거.** 재현성에는 "누가 읽었는가"가 필요하고, 코드 미포함에는 "바이트 대신 식별자"가 필요하다.
- **대안.** evaluator 소스 해시만: 어떤 소스 트리의 해시인지 애매하므로 name+version+pin 셋을 채택.

### 3.5 compatibility_and_refusal_rules (CAP-04, CAP-20)

- **값.** 판정 표(검증 verdict):
  - 포착 중 노트 변경(읽기-해시-재읽기 불일치, 또는 `note_sha256` ≠ 기록된 바인딩): `status: CAPTURE_INCONSISTENT`로 발행하되 `mismatches[]`를 적고 검증 verdict `REFUSE_VERIFIED`. 어느 한 쪽을 조용히 선택하지 않는다.
  - 기록된 바인딩이 가리키는 노트 부재: `MISSING_NOTE` 엔트리(`path`, `expected_sha256` 또는 `null`, 바이트 없음), `status: INCOMPLETE`, verdict `INCOMPLETE`. 조용한 생략 금지.
  - verifier evaluator ≠ 캡슐 `evaluator`: `EVALUATOR_MISMATCH` → verdict `NOT_EVALUATED`. 명시적 거부이며 자동 수용이 아니다.
  - 캡슐 `note_sha256` ≠ workspace 기록 terms 바인딩: `BINDING_DISAGREEMENT` → verdict `REFUSE`. **기록된 바인딩이 역사적 사실로 이기고** 캡슐은 그것을 덮어쓰지 않는다.
  - 알 수 없는 `format`/`capsule_version`: `UNSUPPORTED_CAPSULE_VERSION` → 거부.
  - `manifest_sha256`가 workspace와 불일치: `WORKSPACE_UNBOUND` → 거부.
- **근거.** "무엇이 틀렸는가"를 verdict 이름으로 남기는 것이 조용한 통과보다 증거로 낫고, 기존 `REFUSE`/`NOT_EVALUATED` 류 거부 어휘와 맞는다.

### 3.6 storage_and_consumption_scope (CAP-11, CAP-15)

- **값.** (1) 첫 소비자는 **오프라인 포착 + 오프라인 검증**뿐이다. (2) 저장 위치: workspace export 산출물 옆 사이드카 `<workspace>.policy-capsule.json`; 재현 fixture는 `tests/vectors/` 아래 커밋 후보(구현 시 `scripts/docs_surface.py` 등록·README needle이 필요 — 저장소 검증 규칙). (3) 라벨 `LOCAL_SIMULATION_ARTIFACT`/`SIMULATED`; production·인증·보존기간 주장 없음. CAP-11(durable transactions)·CAP-16(producer tuple)은 `NOT_BOUND` 유지. (4) **후일 역사 재생(replay)의 전제조건 — 기술하되 채택하지 않음**: 서명된 manifest(인증된 노트 출처), evaluator 버전 레지스트리와 수용 정책, 구 노트→신 정책 마이그레이션 규칙, upstream 영수증. 넷 모두 이 노트 밖의 별도 결정이다.
- **근거.** 범위를 offline capture/verify로 닫으면 결정 가능하고, replay 전제를 열거하면 다음 노드가 무엇을 닫아야 하는지 보인다.
- **대안.** 지금 replay까지 정의: 인증·버전 수용이 범위 밖이라 기각.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "policy-capsule-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-11-02",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "scope": "KIX-CAPITAL simulation and product design only; no real money; production NOT_AUTHORIZED; not an offer; no upstream adoption claimed",
  "delegation": "2026-10-08 18:25 KST JunTae Park delegated financial terms, settlement policy, upstream binding and accounts/tax/legal; decided by Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), lanes 10-16 09:07",
  "bases": {"capital_main": "c4114c7", "kix_protocol": "fd33335"},
  "unread_deps": "CAPITAL_OVERLAY_DIGEST_EXPORT.md was outside the allowed read set; envelope field names (WORKSPACE_ENVELOPE_V2|V3, manifest_sha256, workspace_id) are cited by name only and the prior note wins on collision",
  "upstream_adoption_claimed": false,
  "entries": {
    "capsule_contents": {
      "status": "ADOPTED",
      "value": {
        "format": "KIX_CAPITAL_POLICY_CAPSULE_V1",
        "kind": "DATA_ONLY_SIDECAR",
        "fields": ["format", "capsule_version", "capsule_digest", "subject{workspace_id,manifest_format,manifest_sha256,export_digests}", "policy_inputs.notes[]{path,note_sha256,bytes_len,encoding,bytes_b64,binding_role}", "policy_inputs.terms_bindings[]", "evaluator", "capture{tool,tool_version,volatile}", "evidence_grade", "status"],
        "note_set_bound": "docs/decisions/*.md notes resolved by the capture surface plus their cited coverage doc; no code, no vendor bytes, no evaluator bytes",
        "digest_rule": "capsule_digest = SHA256 of canonical digestible subset; per-run capture fields isolated under capture.volatile and excluded"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": ["CAP-15", "CAP-20"],
      "rationale": "Exact note bytes plus hashes plus workspace commitments plus evaluator identity is the minimal complete set the acceptance asks for; bounding the note set keeps executable code out of evidence.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "workspace_and_policy_binding": {
      "status": "ADOPTED",
      "value": {
        "workspace_link": "manifest_sha256 + workspace_id reference only; V2/V3 envelopes, manifests and comparison bytes are never rewritten",
        "policy_link": "notes[].note_sha256 compared against recorded terms_bindings[]",
        "missing_manifest": "manifest_sha256: null + binding_note; capture allowed, verification grade capped"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": ["CAP-14", "CAP-15"],
      "rationale": "Additive sidecar binding is the only form that preserves historical workspaces and existing comparison semantics.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "capture_time_evidence_grade": {
      "status": "ADOPTED",
      "value": {
        "claimed": "CAPTURE_TIME_POLICY_EVIDENCE",
        "explicit_non_claims": {"AUTHENTICATED_HISTORICAL_POLICY": false, "ORIGINAL_DRAW_TIME_PROVENANCE": false},
        "retroactive_provenance": "none; older workspaces get no retroactive claim, a capsule proves notes-at-capture only"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": ["CAP-09", "CAP-20"],
      "rationale": "Mirrors the approved A-4 record/replay separation: the capsule is a record, not replay authorization and not draw-time provenance.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "evaluator_identity": {
      "status": "ADOPTED",
      "value": {
        "fields": ["name", "version", "source_pin", "notes_source", "interface"],
        "notes_source_enum": ["CHECKOUT", "BUNDLED_IN_ARTIFACT", "OVERRIDE_FILE", "NONE"],
        "bytes_embedded": false,
        "auto_acceptance": "none; identity is descriptive, not version approval"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": ["CAP-01", "CAP-02"],
      "rationale": "Reproducibility needs which evaluator read the notes; keeping bytes out requires an identifying tuple, reusing the bundling note's notes_source vocabulary.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "compatibility_and_refusal_rules": {
      "status": "ADOPTED",
      "value": {
        "changed_notes_during_capture": {"status": "CAPTURE_INCONSISTENT", "verdict": "REFUSE_VERIFIED", "records": "mismatches[]"},
        "missing_notes": {"entry": "MISSING_NOTE{path,expected_sha256|null}", "status": "INCOMPLETE", "verdict": "INCOMPLETE"},
        "evaluator_mismatch": {"marker": "EVALUATOR_MISMATCH", "verdict": "NOT_EVALUATED"},
        "binding_disagreement": {"marker": "BINDING_DISAGREEMENT", "verdict": "REFUSE", "winner": "recorded workspace terms binding"},
        "unknown_format": {"marker": "UNSUPPORTED_CAPSULE_VERSION", "verdict": "REFUSE"},
        "workspace_mismatch": {"marker": "WORKSPACE_UNBOUND", "verdict": "REFUSE"}
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": ["CAP-04", "CAP-20"],
      "rationale": "Every failure mode gets a named verdict; silent pass and silent selection are forbidden, and recorded bindings remain the historical fact.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "storage_and_consumption_scope": {
      "status": "ADOPTED",
      "value": {
        "first_consumer": "offline capture + offline verification only",
        "location": "sidecar <workspace>.policy-capsule.json beside workspace exports; optional committed fixture under tests/vectors/ with docs_surface registration",
        "labels": ["LOCAL_SIMULATION_ARTIFACT", "SIMULATED"],
        "not_bound": ["CAP-11 durable transactions", "CAP-16 producer/SDK tuple"],
        "replay_prerequisites_not_adopted": ["signed manifests / authenticated note provenance", "evaluator version registry + acceptance policy", "old-note migration policy", "upstream receipts"]
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": ["CAP-11", "CAP-15"],
      "rationale": "Scoping the first consumer to offline capture/verify keeps the decision inside delegation while naming exactly what a future replay node must close.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| 수용 기준 | 충족 위치 |
|---|---|
| 하나의 유효한 `capital-decision-v1` 블록, 모든 항목 커버 | §4, entries 여섯 개 전부 |
| 유계 데이터 전용 동반 형식: 노트 바이트·해시·workspace 약속·evaluator 식별 | §3.1 (`KIX_CAPITAL_POLICY_CAPSULE_V1`) |
| 포착 시점 증거 ↔ 인증된 역사 정책 ↔ 인출 시점 출처 구분; 구 workspace 소급 출처 없음 | §3.3 |
| 캡처 중 노트 변경·노트 부재·evaluator 불일치·terms 바인딩 불일치 동작 | §3.5 판정 표 |
| workspace envelope·V2/V3 manifest·비교 의미론 보존; `decision_ledger.py` 통과 | §3.2(추가형 사이드카), §4 단일 블록 |

## 6. Open risks

- `CAPITAL_OVERLAY_DIGEST_EXPORT.md` 미독: envelope 필드명이 실제와 다르면 구현 노드가 선행 노트 표기로 맞춘다(선행 노트 우선 규칙).
- 노트 바이트 임베딩은 캡슐 크기를 키운다 — 유계 집합이라 실용적이지만, docs가 크게 늘면 바이트 대신 해시+위임 저장으로 V2를 검토할 수 있다.
- `MISSING_NOTE`의 `expected_sha256`는 기록된 바인딩이 없으면 채울 수 없다 — 그 경우 `null`로 두고 `INCOMPLETE`를 유지한다.
- evaluator `version` 문자열의 정본(릴리스 태그 vs 코드 상수)은 아직 없다 — capture 구현 노드가 정한다.

## 7. 후속 작업

1. capture 스크립트(후보 `scripts/capture_policy_capsule.py`)와 verify 스크립트 — 이 노트의 형식·판정 표를 그대로 구현.
2. `tests/vectors/` 커밋 fixture 시 `scripts/docs_surface.py` 엔트리·README needle 추가 후 `--check` 통과(저장소 검증 규칙).
3. `/api/state` 등 표면에 캡슐 존재·검증 verdict 노출 여부는 별도 표면 결정.
4. replay 전제 넷(서명 manifest, evaluator 레지스트리, 마이그레이션, upstream 영수증)은 각각 독립 결정 노드 후보.
