# Capital 정책 캡슐 결정 — 로컬 금융 증거와 함께 보존하는 정책 입력

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
**결정자(선행 결정 기록): Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07).**
**결정일: 2026-11-02 · KIX-CAPITAL main: `c4114c7` · kix-protocol: `41ace61` (supervisor pack 기준).**

시뮬레이션·제품 설계 전용이다. 청약이나 대출 제안이 아니며 실자금은 없다. production은 `NOT_AUTHORIZED`다. upstream 채택·완료, 인증, SEMANTIC_CONFORMANCE를 주장하지 않는다. 회계·세무·법무 입장은 선행 노트의 `WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW`를 유지한다.

노드 `policy-capsule-decision`의 deps는 `artifact-docs-bundling-decision`, `overlay-digest-export-decision`, `portfolio-history-comparison`이다. 위임 원문: “금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해.” 이번 수정 범위는 이 노트와 `tests/decision_bindings.json`의 여섯 등록 행이다. 실행 구현·기존 workspace·vendor·upstream pin은 변경하지 않는다.

읽기 근거는 제공된 팩과 리뷰, 허용된 등록부다. `CAPITAL_OVERLAY_DIGEST_EXPORT.md` 본문은 허용 읽기 범위 밖이라 열지 않았다. 실제 manifest 태그는 리뷰가 제공한 `KIX_CAPITAL_EXPORT_MANIFEST_V2|V3`를 사용한다. 기존 형식·금융 값은 선행 결정이 우선한다. 여기서 ADOPTED는 로컬 잠정 제품 결정이며 upstream 계약 채택을 뜻하지 않는다.

## 1. 결정 요약

| item | 결정 | CAP rows | consumer |
|---|---|---|---|
| `capsule_contents` | ADOPTED — `KIX_CAPITAL_POLICY_CAPSULE_V1`, 정확한 노트 바이트·해시·workspace 약속·evaluator 식별의 유계 데이터 JSON | CAP-15, CAP-20 | `policy-capsule-capture` |
| `workspace_and_policy_binding` | ADOPTED — 기존 manifest 바이트와 기록된 terms 바인딩을 참조하는 추가형 사이드카 | CAP-14, CAP-15 | 오프라인 capture/verify |
| `capture_time_evidence_grade` | ADOPTED — `CAPTURE_TIME_POLICY_EVIDENCE`만 주장; 인증된 역사·인출 시점 출처는 주장하지 않음 | CAP-09, CAP-20 | 모든 캡슐 소비자 |
| `evaluator_identity` | ADOPTED — name/version/source_pin/notes_source/interface; 코드 미포함·자동 버전 수용 없음 | CAP-01, CAP-02 | 오프라인 verifier |
| `compatibility_and_refusal_rules` | ADOPTED — 변경·부재·evaluator 차이·기록 바인딩 충돌을 분리하여 판정 | CAP-04, CAP-20 | 오프라인 verifier |
| `storage_and_consumption_scope` | ADOPTED — 첫 소비자는 오프라인 포착·검증; 역사 재생은 별도 결정 | CAP-11, CAP-15 | `policy-capsule-capture` 후속 노드 |

## 2. KIX 비전 연결

- `docs/decisions/CAPITAL_ARTIFACT_BUNDLING.md` 팩의 노트 원문·per-file SHA256·`notes_source` 규칙을 따른다. 릴리스 전체 번들과 달리 증거 사이드카에는 정책 데이터만 보존한다. `signed:false`, `published:false`, `LOCAL_SIMULATION_ARTIFACT`를 유지한다.
- `docs/decisions/CAPITAL_CLOSEOUT_ARTIFACT.md` 팩의 결정론적 다이제스트 목적을 적용하여 per-run 정보는 digest에서 분리한다. 로컬 산출물을 upstream 수용 영수증으로 취급하지 않는다.
- `docs/VALIDATION.md`의 비교·입력 보존 원칙과 `docs/SEAMS.md`의 로컬 검증 경계를 따른다. 과거 자료를 수정하지 않고, 캡슐 유무가 기존 비교 결과를 바꾸지 않는다.
- `docs/CAPITAL_REQUIREMENTS_KO.md`의 핀별 범위를 유지한다. `docs/decisions/CAPITAL_CLAIM_SLICE_REGISTRY.md`의 한도 출처 원칙에 따라 정책 숫자를 새 값으로 복사·재결정하지 않는다. 회계·법무 경계는 `docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md`의 작업 가정을 계승한다.

## 3. 항목별 결정

### 3.1 capsule_contents

형식은 `KIX_CAPITAL_POLICY_CAPSULE_V1`, `capsule_version`은 `V1`이다. UTF-8 JSON 한 문서이며 필수 구성은 다음과 같다.

- `subject`: `workspace_id`, `manifest_format`, `manifest_sha256`, `export_digests[]`. 지원 manifest 태그는 `KIX_CAPITAL_EXPORT_MANIFEST_V2`, `KIX_CAPITAL_EXPORT_MANIFEST_V3`다. 각 export 참조는 `{path, sha256}`이며 기존 파일 바이트의 해시다. 원본 envelope나 manifest를 재직렬화하지 않는다.
- `policy_inputs.notes[]`: `{path, note_sha256, bytes_len, encoding, bytes_b64, binding_role}`. `encoding`은 `utf-8`; base64는 정확한 원문 바이트를 보존한다. 줄바꿈·공백·BOM을 정규화하지 않는다. SHA256은 디코딩한 원문에 적용한다. 부재 항목은 별도 `missing_notes[]`에 path/expected_sha256/reason으로 남긴다.
- 대상은 포착 표면이 사용하는 **명시적 노트 목록**과 참조된 `docs/CAP_COVERAGE.md`로 닫는다. 링크를 재귀 탐색하지 않는다. 노트 경로는 repo-relative POSIX이며 중복·절대경로·상위경로 탈출을 거부한다. 포함된 텍스트나 base64는 실행하지 않는다.
- V1 한도는 노트 128개, 노트당 1 MiB, 디코딩된 원문 합계 8 MiB, 완성 JSON 16 MiB다. 한도 초과는 `CAPSULE_LIMIT_EXCEEDED`로 거부하며 자르거나 조용히 생략하지 않는다. 코드·fixture·vendor·evaluator 실행 바이트는 포함하지 않는다.
- `policy_inputs.terms_bindings[]`에는 workspace가 **이미 기록한** 바인딩과 그 위치 참조만 보존한다. 정책 한도·비율을 독립 상수로 복사하지 않는다. 기록이 없으면 `null`과 이유를 남긴다. 노트 원문 속 숫자의 원형 보존은 새 정책 값의 채택이 아니다.
- `evaluator`, `capture{tool,tool_version,volatile}`, `evidence_grade`, `explicit_non_claims`, `status`, `diagnostics`를 둔다. 시각·호스트·로컬 절대경로는 필요한 경우에만 `capture.volatile`에 둔다.

`capsule_digest`는 자기 자신과 `capture.volatile`만 제외한 전체 문서의 SHA256이다. canonical 직렬화는 UTF-8, 객체 키 정렬, 공백 없는 구분자, `ensure_ascii=true`; float·중복 키를 거부한다. notes/missing_notes/export_digests는 path 순서, terms_bindings/diagnostics는 각 항목의 canonical JSON 바이트 순서로 정렬한다. 해시는 소문자 64자리 hex다. verifier는 원문 길이·base64·각 해시와 최종 digest를 각각 확인한다.

해시만 저장하면 노트가 사라졌을 때 입력을 복원하지 못한다. 전체 checkout을 저장하면 실행 코드가 섞인다. 이 유계 원문 집합을 최소 재현 입력으로 채택한다.

### 3.2 workspace_and_policy_binding

workspace 결합은 `workspace_id + manifest_format + manifest_sha256`다. 마지막 값은 **기존 export manifest 파일의 정확한 바이트**를 해시한 캡슐 필드이며 기존 스키마에 같은 필드가 있다고 가정하지 않는다. 기록된 workspace 식별자를 확보할 수 없으면 새 식별자를 역사적 값으로 꾸미지 않는다.

workspace envelope, V2/V3 manifest, 기존 digest 범위, 비교 산술·분류·출력은 그대로 둔다. 캡슐은 비교 입력의 필수 요소도, 기존 동등성 판정의 추가 조건도 아니다. 캡슐 검증 결과는 별도 결과다. 관련 pack 벡터를 새 정책에 맞춰 재생성하지 않는다.

구 workspace에 manifest가 없으면 digest를 `null`로 남기고 `binding_note`에 이유를 적는다. 진단용 포착은 가능하지만 상태는 `INCOMPLETE`, workspace 검증은 `WORKSPACE_UNBOUND`다. 기록된 terms 바인딩의 부재도 명시한다. 현재 노트를 붙였다는 이유로 당시 바인딩이 생기지 않는다. 기존 기록은 변조하지 않으며, 그 기록이 실제로 참이었다는 인증도 부여하지 않는다.

### 3.3 capture_time_evidence_grade

`evidence_grade`의 유일한 값은 `CAPTURE_TIME_POLICY_EVIDENCE`다. 이는 포착 과정에서 관찰한 정책 입력을 설명한다. 캡슐 자체의 해시 일치는 자기 일관성 검사이며, 독립적인 시각 증명·서명·인출 당시 정책 증명이 아니다.

`explicit_non_claims`에는 `AUTHENTICATED_HISTORICAL_POLICY:false`, `ORIGINAL_DRAW_TIME_PROVENANCE:false`를 반드시 둔다. 과거 workspace에 오늘 캡슐을 붙여도 소급 출처는 없다. 부재·충돌 상태의 캡슐은 진단 기록이며 완전한 포착 증거로 승격하지 않는다. 유효 캡슐도 평가 결과의 옳음이나 실거래의 정당성을 보증하지 않는다.

### 3.4 evaluator_identity

`evaluator = {name, version, source_pin, notes_source, interface}`를 보존한다. `source_pin`은 종류와 값을 함께 기록한다. 실제 사용한 소스 commit 또는 릴리스 manifest SHA256이며, 단순히 현재 main을 넣지 않는다. 변경된 작업 트리를 깨끗한 commit 실행으로 표시하지 않는다. 식별을 확정할 수 없으면 해당 값을 `null`과 이유로 남기고 완전 검증을 거부한다.

`notes_source`는 선행 번들링 결정의 `CHECKOUT`, `BUNDLED_IN_ARTIFACT`, `OVERRIDE_FILE`, `NONE`이다. `interface`는 포착한 표면·계약 버전을 식별한다. 이 튜플은 기술적 식별이며 인증이나 승인 목록이 아니다.

첫 verifier는 보존된 바이트·바인딩·식별 튜플만 검사하며 금융 정책을 실행하지 않는다. 지정된 검증 대상 evaluator와 튜플이 다르면 `EVALUATOR_MISMATCH`/`NOT_EVALUATED`다. 바이트 무결성 결과는 별도로 보고할 수 있지만, 튜플 일치도 구 evaluator의 자동 수용이나 정책 재평가 성공을 뜻하지 않는다.

### 3.5 compatibility_and_refusal_rules

포착은 입력 목록을 먼저 고정하고 그 목록의 바이트를 읽는다. 그 바이트에서 해시와 식별 정보를 만들고, 종료 전에 목록·노트·workspace commitment를 다시 확인한다. 가능한 입력은 하나의 불변 스냅샷을 사용한다. 재읽기만 가능한 경우 순간 변경 후 복귀까지 탐지했다고 주장하지 않는다.

| 조건 | 기록과 판정 |
|---|---|
| 포착 도중 목록·노트 바이트 변경 | `CAPTURE_INCONSISTENT`, 차이를 diagnostics에 남김, `REFUSE_VERIFIED`; 조용한 재시도나 한쪽 선택 금지 |
| 필수 노트 부재 | `MISSING_NOTE`, expected_sha256 또는 null, `INCOMPLETE`; 빈 바이트를 정상 노트로 저장하지 않음 |
| evaluator 튜플 불일치 | `EVALUATOR_MISMATCH`, `NOT_EVALUATED`; 기존 코드 실행·다운로드 없음 |
| 포착 노트 해시와 기록된 terms 바인딩 불일치 | `BINDING_DISAGREEMENT`, `REFUSE`; 기록된 바인딩 유지, 현재 노트로 덮어쓰지 않음 |
| 알 수 없는 capsule/manifest 형식 | `UNSUPPORTED_CAPSULE_VERSION`, `REFUSE`; `OTHER`를 지원 형식으로 수용하지 않음 |
| workspace 식별자·manifest 해시 불일치 또는 결합 자료 부재 | `WORKSPACE_UNBOUND`, `REFUSE`; 부재 포착 상태는 `INCOMPLETE` |
| 원문 길이·해시·capsule digest 불일치 또는 형식 한도 위반 | 무결성 진단과 `REFUSE` |

현재 노트가 과거 기록과 다른 것과 **포착 도중 변경된 것**은 별개다. 전자는 `BINDING_DISAGREEMENT`, 후자는 `CAPTURE_INCONSISTENT`이며 둘 다 있으면 모두 기록한다. 우선순위는 `REFUSE > REFUSE_VERIFIED > INCOMPLETE > NOT_EVALUATED > VERIFIED_CAPTURE_ONLY`다. 마지막 판정은 완전한 입력·결합·식별·무결성 검사를 통과한 포착에만 사용하며 역사 인증이나 재생 승인이 아니다.

### 3.6 storage_and_consumption_scope

첫 소비 노드는 `policy-capsule-capture`: 오프라인 포착과 검증만 구현한다. 저장은 export 옆 `<workspace>.policy-capsule.json`이며 원본을 수정하지 않는다. `LOCAL_SIMULATION_ARTIFACT`, `SIMULATED`, `signed:false`, `published:false`를 유지한다. CAP-11·CAP-16은 계속 `NOT_BOUND`다.

여섯 ADOPTED 항목은 `tests/decision_bindings.json`에 각각 `PENDING_CONSUMER`로 등록한다. `capital/export.py`는 contents/workspace-binding/storage의 기존 anchor, `capital/terms.py`는 evidence-grade/evaluator/refusal의 기존 anchor다. 이는 파일 변경이나 소비 구현 완료를 뜻하지 않는다. 미구현 스크립트 경로를 존재하는 소비자로 등록하지 않는다.

역사 재생은 별도다. 필요한 전제는 당시 입력의 완전성과 인증 출처 정책, 별도 확보한 evaluator 및 명시적 버전 수용 정책, 결정론적 실행 환경·재생 검증 벡터, 별도 권한 결정과 적용 가능한 upstream 영수증이다. 서명만으로 당시 적용 사실이 입증되지 않는다. 원래 정책 재생에 신정책 마이그레이션을 강제하지 않는다. live migration·소급 채택·법정 보존기간·인증 도입·구 버전 자동 수용·upstream repin은 이 결정 밖이다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "policy-capsule-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-11-02",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "scope": "Simulation/product design only; no real money; not an offer; production NOT_AUTHORIZED; no upstream adoption or SEMANTIC_CONFORMANCE claimed",
  "bases": {
    "capital_main": "c4114c7",
    "kix_protocol": "41ace61"
  },
  "unread_deps": "CAPITAL_OVERLAY_DIGEST_EXPORT.md was not opened; actual export-manifest tags come from the supplied review; prior decisions govern existing formats",
  "upstream_adoption_claimed": false,
  "entries": {
    "capsule_contents": {
      "status": "ADOPTED",
      "value": {
        "format": "KIX_CAPITAL_POLICY_CAPSULE_V1",
        "kind": "DATA_ONLY_SIDECAR",
        "fields": [
          "format",
          "capsule_version",
          "capsule_digest",
          "subject",
          "policy_inputs",
          "evaluator",
          "capture",
          "evidence_grade",
          "explicit_non_claims",
          "status",
          "diagnostics"
        ],
        "manifest_formats": [
          "KIX_CAPITAL_EXPORT_MANIFEST_V2",
          "KIX_CAPITAL_EXPORT_MANIFEST_V3"
        ],
        "note_set_bound": "Explicit capture-surface decision-note inventory plus docs/CAP_COVERAGE.md when referenced; no recursive traversal, code, vendor or evaluator bytes",
        "limits": {
          "max_notes": 128,
          "max_note_bytes": 1048576,
          "max_total_note_bytes": 8388608,
          "max_capsule_bytes": 16777216
        },
        "digest_rule": "SHA256 of UTF-8 JSON: sorted object keys, compact separators, ensure_ascii=true, no floats or duplicate keys; omit only capsule_digest and capture.volatile; arrays sorted as specified in section 3.1"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": [
        "CAP-15",
        "CAP-20"
      ],
      "rationale": "Exact note bytes, hashes, workspace commitments and evaluator identity provide bounded data-only capture evidence.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "workspace_and_policy_binding": {
      "status": "ADOPTED",
      "value": {
        "workspace_link": "workspace_id + manifest_format + SHA256 of exact existing export-manifest bytes; no workspace, V2/V3 manifest or comparison changes",
        "policy_link": "Preserve existing terms bindings as recorded; compare referenced note digests without substituting current policy",
        "missing_manifest": "null digest with reason; capture INCOMPLETE, workspace verification WORKSPACE_UNBOUND",
        "missing_terms_binding": "null with reason; no inferred or retroactive provenance"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": [
        "CAP-14",
        "CAP-15"
      ],
      "rationale": "An additive sidecar preserves historical bytes and existing comparison semantics.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "capture_time_evidence_grade": {
      "status": "ADOPTED",
      "value": {
        "claimed": "CAPTURE_TIME_POLICY_EVIDENCE",
        "explicit_non_claims": {
          "AUTHENTICATED_HISTORICAL_POLICY": false,
          "ORIGINAL_DRAW_TIME_PROVENANCE": false
        },
        "retroactive_provenance": "none; self-consistent capture data does not authenticate history or original draw-time policy"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": [
        "CAP-09",
        "CAP-20"
      ],
      "rationale": "Capture-time inputs and integrity checks cannot establish authenticated historical policy.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "evaluator_identity": {
      "status": "ADOPTED",
      "value": {
        "fields": [
          "name",
          "version",
          "source_pin",
          "notes_source",
          "interface"
        ],
        "source_pin": "Typed actual source commit or release-manifest SHA256; unknown values are null with reason",
        "notes_source_enum": [
          "CHECKOUT",
          "BUNDLED_IN_ARTIFACT",
          "OVERRIDE_FILE",
          "NONE"
        ],
        "bytes_embedded": false,
        "auto_acceptance": false,
        "verification": "Offline byte-integrity and binding checks only; policy evaluation is not run"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": [
        "CAP-01",
        "CAP-02"
      ],
      "rationale": "Descriptive evaluator identity supports later reproducibility without code bundling or version approval.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "compatibility_and_refusal_rules": {
      "status": "ADOPTED",
      "value": {
        "changed_notes_during_capture": {
          "status": "CAPTURE_INCONSISTENT",
          "verdict": "REFUSE_VERIFIED"
        },
        "missing_notes": {
          "marker": "MISSING_NOTE",
          "status": "INCOMPLETE",
          "verdict": "INCOMPLETE"
        },
        "evaluator_mismatch": {
          "marker": "EVALUATOR_MISMATCH",
          "verdict": "NOT_EVALUATED"
        },
        "binding_disagreement": {
          "marker": "BINDING_DISAGREEMENT",
          "verdict": "REFUSE",
          "winner": "Recorded workspace binding remains unchanged, without authentication claim"
        },
        "unknown_format": {
          "marker": "UNSUPPORTED_CAPSULE_VERSION",
          "verdict": "REFUSE"
        },
        "workspace_mismatch": {
          "marker": "WORKSPACE_UNBOUND",
          "verdict": "REFUSE"
        },
        "precedence": [
          "REFUSE",
          "REFUSE_VERIFIED",
          "INCOMPLETE",
          "NOT_EVALUATED",
          "VERIFIED_CAPTURE_ONLY"
        ],
        "integrity_failure": "REFUSE; retain all diagnostics; never silently choose or repair inputs"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": [
        "CAP-04",
        "CAP-20"
      ],
      "rationale": "Distinct failure modes and explicit precedence prevent silent acceptance or replacement of recorded evidence.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "storage_and_consumption_scope": {
      "status": "ADOPTED",
      "value": {
        "first_consumer": "policy-capsule-capture: offline capture and offline verification only",
        "location": "Sidecar <workspace>.policy-capsule.json beside exports; optional separately registered synthetic fixture",
        "labels": [
          "LOCAL_SIMULATION_ARTIFACT",
          "SIMULATED"
        ],
        "signed": false,
        "published": false,
        "not_bound": [
          "CAP-11",
          "CAP-16"
        ],
        "replay_prerequisites_not_adopted": [
          "Historical input completeness and authenticated provenance policy",
          "Separately obtained evaluator and explicit version acceptance",
          "Deterministic environment and replay conformance vectors",
          "Separate authority decision and applicable upstream receipts"
        ]
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": [
        "CAP-11",
        "CAP-15"
      ],
      "rationale": "Offline capture and verification are buildable now; historical replay requires separate evidence and acceptance decisions.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| 수용 기준 | 충족 위치 |
|---|---|
| 단일 유효 결정 블록, 여섯 항목 | §4; 모두 ADOPTED, 값·출처·날짜·CAP·근거 포함 |
| 유계 데이터 전용 원문·해시·workspace·evaluator | §3.1–3.2, §3.4 |
| 포착·인증된 역사·인출 출처 구별 | §3.3; 소급 주장 없음 |
| 변경·부재·evaluator 차이·terms 충돌 | §3.5; 개별 진단과 우선순위 |
| envelope·V2/V3·비교 불변 | §3.2; 추가형 사이드카만 |
| 결정 등록 | §3.6; 여섯 `PENDING_CONSUMER` 행 |

수정 후 검증: `python3 scripts/decision_ledger.py`, `python3 scripts/decision_bindings.py --check`, `python3 scripts/docs_surface.py --check` 모두 exit 0. `python3 -m unittest discover -s tests -p test_decision_bindings.py -v`는 25개 테스트 통과(실제 트리·정렬 등록부 검사 포함). 이는 결정·등록 검증이며 정책 캡슐 구현 테스트의 통과를 의미하지 않는다.

## 6. Open risks

- overlay export 선행 본문은 미독이다. 리뷰가 제공한 실제 태그를 반영했으며, 기존 필드의 구체적 추출 경로는 후속 구현에서 선행 결정과 대조한다.
- 정확한 노트 원문에는 민감한 override 내용이 있을 수 있다. 공개·자동 업로드를 하지 않으며, 원문을 제거한 산출물을 완전한 캡슐로 표시하지 않는다.
- V1 크기 한도를 넘는 입력은 거부된다. 한도 확대는 버전·자원 검증과 함께 별도 검토한다.
- 구 workspace의 부재 증거와 식별 불가능한 evaluator는 이 사이드카로 복원할 수 없다.

## 7. 후속 작업

1. `policy-capsule-capture`에서 오프라인 capture/verify와 §3.5의 실패 사례를 구현한다. 정확한 바이트 왕복, 결정론, 무변경 workspace, evaluator 불일치, 바인딩 충돌을 검증한다.
2. 합성 fixture를 새로 커밋할 때 `scripts/docs_surface.py`와 README 등록을 함께 수행한다. 이번 수정에는 fixture나 pack 벡터 변경이 없다.
3. 소비 구현과 검증 영수증이 생긴 항목만 등록부 상태를 갱신한다. UI 표면과 역사 재생은 각각 별도 작업으로 남긴다.
