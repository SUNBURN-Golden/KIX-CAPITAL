# Capital 오버레이 digest·export·시계 권위 결정 — digest 범위·export 섹션·sim clock 권위·golden 정책

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
이 문서는 KIX-CAPITAL 저장소 안의 **시뮬레이션·제품 설계용** 결정이다. 실자금은 움직이지 않으며 production은 계속 `NOT_AUTHORIZED`다. 어떤 upstream 계약(stage7 인증 export, `k-stage5-durable-tx`, `fin-ledger-contract` 등)의 채택도 주장하지 않는다. `capital/`·`tests/`·vendor 바이트는 바꾸지 않으며, diff는 이 문서 한 파일이다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `overlay-digest-export-decision` (Decision: overlay digest scope, export section, clock authority and golden digest policy) · deps `terms-overlay`, `persistence-port`, `export-manifest`, `accounts-tax-legal-decision`, `overlay-state-decision` · kind `decision` · user_merge `False` |
| 결정자 | **GLM-5.3 xhigh → swe-2 → Opus 5.5 high, delegated by JunTae 2026-10-08 (tertiary→Opus 10-15 10:14)** |
| 위임 원문 | 2026-10-08 JunTae Park: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." |
| 결정일 | 2026-10-15 |
| KIX-CAPITAL 기준 | main `60ad963` |
| kix-protocol 기준 | `751c51b` (읽기 전용 체크아웃 `/workspace/capital-run/kixproto-ro`) |
| 선행 결정 | [CAPITAL_OVERLAY_STATE.md](CAPITAL_OVERLAY_STATE.md) (`SINGLE_ENVELOPE_TWO_JOURNALS`, `FOLD_THEN_VERIFY`, `envelope_version: 2`/`overlay_schema: 1`, 용량 한도), [CAPITAL_FINANCIAL_TERMS.md](CAPITAL_FINANCIAL_TERMS.md) (`sim_day` 논리 일, ACT/365 단리 메모) |
| 범위 밖 | 코드·upstream·vendor 변경. stage7 인증. 외부 서명 키 |

## 1. 결정 요약

| item | 결정 (요지) | CAP rows | 소비 노드 / seam |
|---|---|---|---|
| `state_digest_scope` | **SEPARATE_DIGESTS_F04_PINNED**. F04 `state_digest`는 pinned `CreditMachine.state_digest()` 그대로 두고 command journal만 덮는다. overlay를 섞지 않는다. `overlay_state.digest`는 도메인 태그를 붙인 별도 SHA256으로, `capital.store.canonical_bytes`를 거친 fold 결과에 대해 계산한다. overlay 섹션 무결성은 섹션 안의 `section_sha256`이 맡는다. `payload`와 `payload_sha256`은 바뀌지 않는다 | CAP-11 | `persistence-port`(`FileWorkspace`), service load 경로, `capital/recon.py` |
| `export_section_policy` | **OPTIONAL_OVERLAY_SECTION_FORMAT_GATED**. overlay journal이 비어 있으면 섹션이 없고, manifest는 `KIX_CAPITAL_EXPORT_MANIFEST_V2` 바이트 그대로다. 비어 있지 않으면 `overlay` 섹션(`overlaypart`)을 넣고 format을 `KIX_CAPITAL_EXPORT_MANIFEST_V3`로 바꾼다. 기존 일곱 섹션의 본문은 overlay가 바꾸지 않는다. 서명 대상은 계속 `content_digest` 하나다 | CAP-11 | `export-manifest`(`capital/export.py`), `SignaturePort` |
| `clock_command_authority` | **OPERATOR_EXPLICIT_CAS_ONLY**. `sim_day`는 로컬 operator 세션의 명시적 `advance_sim_day` 명령으로만 전진한다. 이 명령은 `from_sim_day`→`to_sim_day` compare-and-set이며, 단조 증가만 허용하고 한 번에 최대 366일이다. agent lane은 제안만 할 수 있다. wall-clock·자동 tick·되감기는 금지한다 | CAP-01, CAP-11 | `terms-overlay` 시계, service command 경로, UI |
| `golden_digest_policy` | **EMPTY_OVERLAY_IS_ABSENT**. 빈 overlay에서는 F04 `state_digest`, `payload_sha256`, export `content_digest`, `tests/golden/demo.json`이 바이트 단위로 같다. overlay golden은 새 파일 `tests/golden/overlay_*.json`에만 둔다. CI 자동 재생성은 금지하고, 재생성에는 결정 인용이 있어야 한다 | CAP-11 | `persistence-port`, `export-manifest`, 테스트 |

## 2. KIX 비전 연결

- `docs/CAPITAL_REQUIREMENTS_KO.md`는 청사진에서 **원 요청·관측·금전 의무·실행의 분리**와 V23/V24의 **source-consistent export**를 가져온다.
  - 이 결정은 F04 의무 상태(`state_digest`)와 시뮬레이션 관측 메모(overlay)를 서로 다른 digest로 분리한다.
  - export에서는 overlay가 기존 의무 섹션 본문을 오염시키지 못하게 한다.
- `/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md`의 A-4에서 세 가지 원칙을 가져온다.
  - **유효기간/현재성은 시간원을 따로 기록**한다. 그래서 `sim_day`의 시간원 라벨을 `SIM_LOGICAL_CLOCK`으로 고정한다. 체인 시각이나 은행 영업일이 아니다.
  - **과거 사실의 재생은 새로운 외부 실행 허가가 아니다.** clock entry를 재생해도 아무것도 실행되지 않는다.
  - **local sync를 finality로 대체하지 않는다.**
- `/workspace/capital-run/kixproto-ro/README.md`는 현재 단계를 mock·비운영 범위로 두고, 정책 값을 `DECISION_REQUIRED`/`UNDETERMINED`로 둔다. 그래서 이 결정도 operator를 인증된 주체로 주장하지 않는다.
- `docs/SEAMS.md`에서 가져오는 전제는 세 가지다.
  - `actor`는 인증이 아니다.
  - `SignaturePort`는 채택 경계이며 `NOT_BOUND` 상태다.
  - CAP-11은 `NOT_BOUND`로 남는다.
- `docs/VALIDATION.md`의 재생, reload fencing, lost-response→`UNKNOWN`(재시도 없음) 규칙을 clock 명령의 CAS와 dedup으로 연장한다.
- `docs/RELEASES.md`의 "같은 환경에서 같은 SHA256" 원칙과 `DEV_ONLY` HMAC이 무결성일 뿐 인증이 아니라는 점은 golden 정책의 한계로 그대로 유지한다.
- `capital/export.py`에서 이 결정이 기대는 구조는 다음과 같다.
  - `SECTION_IDS` 집합 동일성 검사(`SECTION_SET`)가 있다.
  - `strip_volatile`이 `VOLATILE_KEYS`를 digest에서 제거한다.
  - `content_digest`만 서명한다.
- `capital/recon.py`의 고정 `CHECK_IDS`와 `capital/scenarios.py`의 `REJECTION_PRESERVES_STATE`, "중복은 한 번만 반영", `workspace_mutated: False`가 이 결정의 위생 규칙의 선례다.
- `CAPITAL_FINANCIAL_TERMS.md`는 `sim_day`를 오버레이의 논리 정수 일로 정의한다.

## 3. 항목별 결정

### 3.1 `state_digest_scope` — ADOPTED: SEPARATE_DIGESTS_F04_PINNED

- **F04 `state_digest`는 바뀌지 않는다.** vendor `CreditMachine.state_digest()`의 출력이며 command journal만 덮는다. overlay 내용, `sim_day`, 이자 메모는 이 값에 들어가지 않는다. vendor 바이트 잠금상 바꿀 수도 없다. `recon.py` `replay_digest_equals_state_digest`도 그대로다.
- **`overlay_state.digest`** = `sha256(canonical_bytes({"domain":"KIX_CAPITAL_OVERLAY_STATE_DIGEST_V1","overlay_schema":1,"state":<fold 결과>}))`.
  - fold 결과에는 다음이 들어간다: `sim_day`, terms 바인딩(`terms_version`·status), interest/recovery 메모 집계와 행, `decision_records`, `agent_proposals` 결과, `entry_count`, `last_after_journal_index`.
  - 직렬화기는 export가 이미 쓰는 `capital.store.canonical_bytes` 하나로 통일한다. 세 번째 직렬화기는 만들지 않는다.
  - F04 `state_digest`를 anchor로 섞지 않는다. journal 결합은 각 entry의 `after_journal_index`로 하고, 매달린 참조는 선행 결정에 따라 fail closed로 처리한다.
- **섹션 무결성.** `payload_sha256`은 계속 `payload` 네 키(`receipts`·`journal`·`case_fixtures`·`state_digest`)만 덮는다. 그래서 v1에서 v2로 승격할 때 `payload`와 `payload_sha256`은 바이트 단위로 같다.
  - overlay 섹션은 내부에 `section_sha256`을 가진다. 이 값은 `section_sha256`을 뺀 overlay 섹션 전체의 canonical SHA256이다.
  - 알고리즘은 같은 SHA256이고, 선행 결정의 "checksum algorithm UNCHANGED"와 충돌하지 않는다.
  - 로드 순서상 이 검증은 `verify_checksum` 단계 안에서 `payload_sha256` 검증 직후에 한다. 불일치하면 envelope 전체를 거부한다.
- **wall-clock 금지.** overlay entry와 fold 결과에는 `VOLATILE_KEYS`(`instance_id`·`created_at`·`saved_at`·`timestamp`·`timestamps`)를 쓰지 않는다.
  - 이유: `strip_volatile`이 그 키들을 digest에서 조용히 빼 버리므로, 들어가면 덮이지 않는 데이터가 생긴다.
  - 쓰기 시 해당 키가 있으면 400 `OVERLAY_VOLATILE_KEY`로 거부하고 아무것도 기록하지 않는다.

### 3.2 `export_section_policy` — ADOPTED: OPTIONAL_OVERLAY_SECTION_FORMAT_GATED

- **빈 overlay**(journal entry 0개):
  - `overlay` 섹션을 넣지 않는다. format은 `KIX_CAPITAL_EXPORT_MANIFEST_V2`, `SECTION_IDS` 일곱 개 그대로다.
  - reconciliation 본문에 overlay 키나 검사를 추가하지 않는다.
  - 결과적으로 `content_digest`가 overlay 도입 전과 바이트 단위로 같다.
- **비어 있지 않은 overlay**:
  - format을 `KIX_CAPITAL_EXPORT_MANIFEST_V3`로 바꾸고, 필수 일곱 섹션에 `overlay` 하나를 더한다(`PART_TAGS['overlay'] = 'overlaypart'`).
  - V2를 엄격하게 검증하는 소비자는 섹션 집합이 아니라 format에서 명확하게 거절한다. "선택 섹션"을 V2 안에 숨겨 집합 동일성 계약을 조용히 깨지 않는다.
  - V3 manifest에서 `overlay` 섹션이 없으면 `SECTION_SET`으로 거부한다. V2 manifest에 `overlay`가 있어도 거부한다.
- **overlay 섹션 본문**:
  - 필드: `{label:"SIMULATED", overlay_schema:1, sim_day, clock_source:"SIM_LOGICAL_CLOCK", terms_binding, entry_count, journal:[...], state:<fold>, overlay_state_digest}`.
  - 이자·회수 금액은 `SIM_REPAY_MEMO` 계열의 메모 라벨을 유지한다. 채권이나 수취 확정으로 표기하지 않는다.
  - 개인 데이터는 넣지 않는다(`NO_PERSONAL_DATA_BY_DESIGN_V1`의 데이터 클래스 범위). 보존 기간도 넣지 않는다(`retention_policy` 다섯 칸은 비어 있는 상태 유지).
- **기존 섹션 불가침.** `journal`·`receipts`·`projection`·`reconciliation`·`statement`·`fixtures`·`source_pin` 본문은 command journal과 fixture만의 함수로 유지한다. overlay에서 파생된 메모, `sim_day`, terms 바인딩은 `overlay` 섹션에만 나타난다.
- **reconciliation 확장(조건부).** overlay가 비어 있지 않을 때만 recon `checks`에 `overlay_fold_digest_equals_persisted`를 하나 덧붙이고, `scope`에 `overlay_state_digest`를 넣는다. 빈 overlay에서는 `CHECK_IDS` 여섯 개 그대로다.
- **서명.** 서명 대상은 `content_digest` 하나다. V3의 `content_digest`가 overlay 섹션 해시를 포함하므로, overlay 전용 서명은 만들지 않는다. `UnsignedSigner`/`DevHmacSigner`의 의미도 그대로다(무결성일 뿐 `authentication: NOT_BOUND`). `manifest_status`의 COMPLETE/INCOMPLETE 규칙은 V3에도 동일하게 적용하고, overlay fold 불일치는 `RECONCILIATION_NOT_CLEAN`으로 이어진다.

### 3.3 `clock_command_authority` — ADOPTED: OPERATOR_EXPLICIT_CAS_ONLY

- **유일한 전진 경로**는 command `advance_sim_day {operation_id, from_sim_day, to_sim_day, reason}`이다.
  - 기존 facade 쓰기 경로를 탄다(Host/Origin/CSRF, strict input, `operation_id` dedup).
  - 주체 라벨은 `LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED`이며, 인증된 신원이 아니다.
- **CAS 펜싱.** 현재 `sim_day ≠ from_sim_day`이면 409 `SIM_CLOCK_STALE`로 거부하고 아무것도 기록하지 않는다. reload 이후 오래된 탭의 재전송을 막는 기존 fencing과 같은 원리다.
- **단조 증가와 상한.**
  - `to_sim_day ≤ from_sim_day`이면 400 `SIM_CLOCK_NOT_ADVANCING`이다. 되감기 명령은 존재하지 않는다.
  - 한 번의 전진폭은 `to_sim_day - from_sim_day ≤ 366`이고, 초과하면 400 `SIM_CLOCK_STEP`이다.
  - `to_sim_day > SIM_DAY_MAX(3650)`이면 선행 결정에 따라 409 `SIMULATION_CAPACITY`로 거부하고 아무것도 기록하지 않는다.
- **전제 조건.** `workspace_status == "ACTIVE"`가 아니면 거부한다(fail closed).
- **결과.**
  - 한 번의 원자적 save로 `clock` entry 하나를 남긴다(`after_journal_index` = 현재 command journal 길이).
  - 이자·회수 메모는 `CAPITAL-TERMS-V1`을 참조해 deterministic fold가 계산한다. 숫자를 여기에 다시 적지 않는다.
  - F04 `state_digest`는 바뀌지 않는다.
- **lost response.** 같은 `operation_id`로 조회해 receipt를 받는다. receipt가 없으면 `UNKNOWN`이며 자동 재시도하지 않는다(기존 정책).
- **agent lane.** `agent_proposals`에 `kind: CLOCK_ADVANCE` 제안을 남길 수만 있고, 제안은 시계를 움직이지 않는다. operator가 채택하면 별도의 `advance_sim_day`가 실행되고, 그 entry는 `proposal_id`를 인용한다.
- **금지 사항.**
  - wall-clock 연동, 서버 기동 시 tick, 배경 타이머, 재생 중 시계 재계산은 금지한다. 재생은 기록된 clock entry만 fold한다.
  - 시계를 고치는 방법은 새 workspace뿐이다(선행 결정의 자기수복 금지와 같은 이유).

### 3.4 `golden_digest_policy` — ADOPTED: EMPTY_OVERLAY_IS_ABSENT

- **변경 여부 명시**:
  - (a) F04 `state_digest`: **변경 없음**.
  - (b) `workspace.json`의 `payload_sha256`: **변경 없음**. `payload`는 그대로 보존된다.
    - 단, `workspace.json` **파일 전체 바이트**는 선행 결정에 따라 v2로 승격하면서 `envelope_version`과 빈 `overlay` 섹션이 생겨 달라진다. 그래서 파일 전체 바이트는 golden 대상이 아니다.
  - (c) `tests/golden/demo.json`: **변경 없음(바이트 동일)**. 기본 demo 경로는 overlay entry를 쓰지 않는다.
- **빈 overlay = 부재.** export, recon, golden이 포착하는 모든 표면에서 빈 overlay는 키 자체가 없다. 예외는 선행 결정이 섹션 존재를 의무화한 workspace envelope 하나다.
  - `GET /api/state`도 빈 overlay에서는 overlay 블록을 생략한다. UI는 블록이 없으면 `sim_day 0`·terms `NOT_BOUND`로 표시한다.
- **새 golden은 별도 파일에만 둔다.**
  - `tests/golden/overlay_empty.json`: 빈 fold의 `overlay_state.digest`(코드에 리터럴로 넣지 않고 함수로 계산한 값을 golden으로 고정), V2 manifest의 `content_digest`가 `demo.json`과 같음을 고정한다.
  - `tests/golden/overlay_demo.json`: 고정 시나리오(terms 바인딩 → `advance_sim_day` 0→60 → 상환)의 V3 `content_digest`와 `overlay_state.digest`를 고정한다.
- **재생성 규칙.**
  - CI나 테스트가 golden을 자동으로 다시 쓰지 않는다.
  - golden 재생성 커밋은 canonicalization, `overlay_schema`, terms 버전 변경을 승인한 결정 문서를 인용해야 한다.
  - `demo.json`이 바뀌면 그것만으로 blocking 회귀다.
  - `overlay_schema`를 올리면 새 golden 파일을 추가하고, 이전 schema golden은 재생 벡터로 남긴다.
  - golden 일치는 같은 인터프리터·같은 트리에서만 유효하다(RELEASES 원칙). 플랫폼 간 재현성을 주장하지 않는다.

## 4. capital-decision-v1

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "overlay-digest-export-decision",
  "decided_by": "GLM-5.3 xhigh → swe-2 → Opus 5.5 high, delegated by JunTae 2026-10-08 (tertiary→Opus 10-15 10:14)",
  "date": "2026-10-15",
  "provisional": true,
  "entries": {
    "state_digest_scope": {
      "status": "ADOPTED",
      "value": {
        "mode": "SEPARATE_DIGESTS_F04_PINNED",
        "f04_state_digest": "UNCHANGED_PINNED_CreditMachine.state_digest_COMMAND_JOURNAL_ONLY",
        "overlay_digest_field": "overlay_state.digest",
        "overlay_digest_material": "sha256(canonical_bytes({domain:KIX_CAPITAL_OVERLAY_STATE_DIGEST_V1, overlay_schema:1, state:fold_result}))",
        "serializer": "capital.store.canonical_bytes",
        "f04_anchor_in_overlay_digest": false,
        "journal_binding": "after_journal_index per entry; dangling ref FAIL_CLOSED",
        "payload_sha256": "UNCHANGED_COVERS_PAYLOAD_ONLY",
        "overlay_section_integrity": "section_sha256 inside overlay section, SHA256 over canonical section minus itself, verified in verify_checksum step",
        "volatile_keys_in_overlay": "REJECT_400_OVERLAY_VOLATILE_KEY_NO_WRITE"
      },
      "provided_by": "GLM-5.3 xhigh → swe-2 → Opus 5.5 high, delegated by JunTae 2026-10-08 (tertiary→Opus 10-15 10:14)",
      "date": "2026-10-15",
      "cap_rows": ["CAP-11"],
      "rationale": "The pinned F04 digest is vendor-locked and represents obligation state; mixing simulated memos into it would blur the blueprint's observation/obligation separation and break existing replay checks. A separate domain-tagged overlay digest plus a section checksum covers the overlay without touching payload_sha256, and banning volatile keys prevents strip_volatile from silently uncovering data.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "export_section_policy": {
      "status": "ADOPTED",
      "value": {
        "mode": "OPTIONAL_OVERLAY_SECTION_FORMAT_GATED",
        "empty_overlay": "NO_OVERLAY_SECTION_FORMAT_KIX_CAPITAL_EXPORT_MANIFEST_V2_BYTE_IDENTICAL",
        "non_empty_overlay": "FORMAT_KIX_CAPITAL_EXPORT_MANIFEST_V3_SEVEN_SECTIONS_PLUS_overlay",
        "part_tag": "overlaypart",
        "v3_without_overlay": "REJECT_SECTION_SET",
        "v2_with_overlay": "REJECT_SECTION_SET",
        "overlay_section_fields": ["label", "overlay_schema", "sim_day", "clock_source", "terms_binding", "entry_count", "journal", "state", "overlay_state_digest"],
        "existing_sections": "FUNCTION_OF_COMMAND_JOURNAL_AND_FIXTURES_ONLY_OVERLAY_NEVER_ALTERS",
        "reconciliation_extra_check": "overlay_fold_digest_equals_persisted ONLY_WHEN_OVERLAY_NON_EMPTY",
        "signature": "content_digest only; no separate overlay signature; authentication NOT_BOUND",
        "personal_data": "NONE",
        "retention_durations": "NONE"
      },
      "provided_by": "GLM-5.3 xhigh → swe-2 → Opus 5.5 high, delegated by JunTae 2026-10-08 (tertiary→Opus 10-15 10:14)",
      "date": "2026-10-15",
      "cap_rows": ["CAP-11"],
      "rationale": "export.py enforces exact SECTION_IDS set equality, so an optional section hidden inside V2 would silently break strict consumers; gating presence on a V3 format tag keeps empty-overlay manifests byte-identical and makes overlay-bearing exports self-describing, while content_digest already covers the new section for any SignaturePort.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "clock_command_authority": {
      "status": "ADOPTED",
      "value": {
        "mode": "OPERATOR_EXPLICIT_CAS_ONLY",
        "command": "advance_sim_day",
        "fields": ["operation_id", "from_sim_day", "to_sim_day", "reason"],
        "actor_label": "LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED",
        "clock_source": "SIM_LOGICAL_CLOCK",
        "stale_from": "409_SIM_CLOCK_STALE_NO_WRITE",
        "non_advancing_or_rewind": "400_SIM_CLOCK_NOT_ADVANCING_NO_WRITE",
        "max_step_days": 366,
        "step_overflow": "400_SIM_CLOCK_STEP_NO_WRITE",
        "beyond_SIM_DAY_MAX": "409_SIMULATION_CAPACITY_NO_WRITE",
        "requires_workspace_status": "ACTIVE",
        "lost_response": "LOOKUP_BY_OPERATION_ID_ELSE_UNKNOWN_NO_RETRY",
        "agent_lane": "PROPOSAL_ONLY_CLOCK_ADVANCE_NEVER_APPLIES",
        "wall_clock_or_auto_tick": "FORBIDDEN",
        "replay": "FOLD_RECORDED_CLOCK_ENTRIES_ONLY_NO_RECOMPUTE",
        "correction": "NEW_WORKSPACE_ONLY",
        "f04_state_digest_effect": "NONE"
      },
      "provided_by": "GLM-5.3 xhigh → swe-2 → Opus 5.5 high, delegated by JunTae 2026-10-08 (tertiary→Opus 10-15 10:14)",
      "date": "2026-10-15",
      "cap_rows": ["CAP-01", "CAP-11"],
      "rationale": "sim_day drives CAPITAL-TERMS-V1 interest memos, so it needs one explicit, idempotent, fenced writer; AUTHORITY_MODEL_1 A-4 requires the time source to be recorded separately and replay not to grant new execution, so wall-clock ticks are banned and agent lanes may only propose.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "golden_digest_policy": {
      "status": "ADOPTED",
      "value": {
        "mode": "EMPTY_OVERLAY_IS_ABSENT",
        "f04_state_digest_changes": false,
        "workspace_payload_sha256_changes": false,
        "workspace_json_file_bytes": "CHANGE_ON_V2_PROMOTION_NOT_A_GOLDEN_TARGET",
        "tests_golden_demo_json_changes": false,
        "empty_overlay_surfaces": "KEY_ABSENT_IN_EXPORT_RECON_API_STATE_AND_GOLDENS_EXCEPT_WORKSPACE_ENVELOPE",
        "new_goldens": ["tests/golden/overlay_empty.json", "tests/golden/overlay_demo.json"],
        "overlay_demo_scenario": "terms binding -> advance_sim_day 0->60 -> repay",
        "auto_regeneration": "FORBIDDEN",
        "regeneration_requires": "commit citing an authorizing decision note",
        "demo_json_diff": "BLOCKING_REGRESSION",
        "schema_bump": "ADD_NEW_GOLDEN_KEEP_OLD_AS_REPLAY_VECTOR",
        "reproducibility_claim": "SAME_INTERPRETER_SAME_TREE_ONLY"
      },
      "provided_by": "GLM-5.3 xhigh → swe-2 → Opus 5.5 high, delegated by JunTae 2026-10-08 (tertiary→Opus 10-15 10:14)",
      "date": "2026-10-15",
      "cap_rows": ["CAP-11"],
      "rationale": "Treating an empty overlay as absent everywhere except the mandated envelope section keeps every existing book, manifest and demo golden byte-identical, so overlay work cannot hide regressions; overlay behavior gets its own goldens with human-cited regeneration only.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

- 네 항목이 모두 ADOPTED로 블록에 들어 있다 → §4. `python3 scripts/decision_ledger.py` 통과 여부는 supervisor가 병합 시점에 확인한다. 이 결정자는 읽기 전용이라 실행하지 않았다.
- 변경 여부 명시 → §3.4: `state_digest` 변경 없음, `payload_sha256` 변경 없음, `tests/golden/demo.json` 변경 없음. 빈 overlay의 book과 export는 바이트 동일하다.
- diff는 이 문서 한 파일이며 `capital/`·`tests/`·vendor는 수정하지 않는다.

## 6. Open risks

- `tests/golden/demo.json`과 `capital/store.py`는 이 결정자의 읽기 범위 밖이었다.
  - demo가 `GET /api/state` 같은 표면을 포착한다면 §3.4의 "빈 overlay = 부재" 규칙이 그 표면에서 구현돼야 바이트 동일성이 유지된다.
  - `payload_sha256`이 `payload`만 덮는다는 전제도 구현 노드가 확인해야 한다. 전제와 다르면 fail closed로 처리하고 이 결정을 다시 열어야 한다.
- V2/V3 두 format이 공존하므로 소비자가 두 형식을 모두 처리해야 한다.
- operator는 인증된 주체가 아니다. 로컬 파일을 쓸 수 있는 사람은 overlay와 checksum을 함께 다시 쓸 수 있다. 무결성 검사는 손상 탐지용이지 적대자 방어가 아니다.
- export-manifest 노드의 CAP 행은 pack에 없어서 CAP-11로만 인용했다.

## 7. 후속 작업

- `persistence-port`
  - `section_sha256`, volatile key 거부, `overlay_state.digest` 계산을 구현한다.
  - 다음 벡터를 추가한다: 섹션 checksum 불일치, digest 불일치, volatile key 거부.
- `terms-overlay`
  - `advance_sim_day`의 CAS·단조성·366일 상한·`SIMULATION_CAPACITY` 경로와 agent 제안 분리를 구현한다.
  - 다음 벡터를 추가한다: stale, rewind, step, lost response.
- `export-manifest`
  - V3 format gating, `overlaypart`, 조건부 recon 검사를 구현한다.
  - V2/V3 섹션 집합 위반 거부 테스트를 추가한다.
- 테스트
  - `overlay_empty.json`과 `overlay_demo.json`을 추가한다.
  - `demo.json`이 바이트 동일함을 단언하는 회귀 테스트를 둔다.
