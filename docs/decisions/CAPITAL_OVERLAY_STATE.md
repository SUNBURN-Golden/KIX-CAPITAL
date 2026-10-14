# Capital 오버레이 상태 결정 — 저장 형태·리플레이·엔벌로프 버전·용량

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
이 문서는 KIX-CAPITAL 저장소 안의 **시뮬레이션·제품 설계용** 결정이다. 실자금이 움직이지 않으며, production은 계속 `NOT_AUTHORIZED`다. 어떤 upstream 계약(`k-stage5-durable-tx`, `fin-ledger-contract` 등)의 채택도 주장하지 않는다 — 로컬 JSON 파일은 그 계약이 아니다(SEAMS.md). `capital/`·`tests/`·vendor 바이트를 바꾸지 않으며 diff는 `docs/decisions/CAPITAL_OVERLAY_STATE.md` 한 파일이다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `overlay-state-decision` (Decision: overlay storage, replay, envelope version and capacity) · deps `terms-overlay`, `persistence-port`, `export-manifest`, `accounts-tax-legal-decision` · kind `decision` · user_merge `False` |
| 결정자 | **GLM-5.3 xhigh → swe-2 → Fable 5.1, delegated by JunTae 2026-10-08 (tertiary 10-14 18:15)** |
| 위임 원문 | 2026-10-08 18:25 KST JunTae Park: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." |
| 결정일 | 2026-10-14 |
| KIX-CAPITAL 기준 | main `8787278` |
| kix-protocol 기준 | `ced0e2f` (읽기 전용 체크아웃 `/workspace/capital-run/kixproto-ro`) |
| 선행 결정 | [CAPITAL_FINANCIAL_TERMS.md](CAPITAL_FINANCIAL_TERMS.md)(`CAPITAL-TERMS-V1`, sim_day·이자 메모 원장·terms_version), [CAPITAL_ACCOUNTS_TAX_LEGAL.md](CAPITAL_ACCOUNTS_TAX_LEGAL.md)(`SIM_REPAY_MEMO`·보존 술어·`SYNTHETIC_UNADOPTED`) |
| 범위 밖 | digest/export/clock 권위 → `overlay-digest-export-decision`. 코드·upstream·vendor 변경 없음 |

## 1. 결정 요약

| item | 결정 (요지) | CAP rows | 소비 노드 / seam |
|---|---|---|---|
| `overlay_storage_shape` | **SINGLE_ENVELOPE_TWO_JOURNALS**: 별도 `overlay` 저널을 기존 단일 workspace envelope 안의 섹션으로 영속한다(derived-only 아님, 두 번째 파일 아님). materialized `overlay_state`는 fold 결과의 검증용 캐시다 | CAP-11 | `persistence-port` 어댑터(`capital/store.py`), `terms-overlay` |
| `overlay_replay_rule` | **FOLD_THEN_VERIFY**: checksum → `envelope_version` 검사 → command journal 재생(기존 pinned FSM 경로) → overlay journal deterministic fold → 재계산 digest와 persisted `overlay_state.digest` 비교. 불일치·unreadable → fail closed, 자동 복구 없음 | CAP-11 | service load 경로, replay vectors |
| `workspace_envelope_version` | **`envelope_version: 2`, 내부 `overlay_schema: 1`**. v1 파일(overlay 섹션 없음)은 정상 승격 로드 후 다음 save에서 v2로 기록. 상위 미지원 버전·parse 실패·overlay 섹션 unreadable → envelope 전체 거부 | CAP-11 | `FileWorkspace`, `tests/storage_conformance.py` |
| `overlay_capacity_bounds` | `OVERLAY_MAX_ENTRIES=2000`, `OVERLAY_ENTRY_MAX_BYTES=4096`, `SIM_DAY_MAX=3650`, `AGENT_PROPOSALS_MAX=500`, `DECISION_RECORDS_MAX=64`, `ENVELOPE_MAX_BYTES=4194304`. 초과 시 fail-closed 거부·미기록·`state_digest` 불변. 데모 한계이지 금융 한도가 아니다 | CAP-11 | service 용량 검사, `GET /api/state` `capacity` 블록 |

## 2. KIX 비전 연결

`docs/CAPITAL_REQUIREMENTS_KO.md`의 청사진 매핑은 원 요청·관측·금전 의무·실행 분리와 금융 근거의 기준시점/범위를 요구한다. 오버레이의 `sim_day`·이자 메모 원장·결정 기록은 그 "관측·기준시점" 계층의 로컬 구현체이며, 금전 의무나 실행을 대표하지 않는다. `docs/SEAMS.md`가 고정한 바대로 `StoragePort`의 upstream 목표는 `k-stage5-durable-tx`이고 CAP-11은 `NOT_BOUND`로 남는다 — 본 결정의 envelope v2는 그 계약의 채택이 아니라 로컬 seam 안의 진화다. `docs/INTEGRATION.md`의 `terms` 스냅샷(`{status, reason, terms_version}`)·`capacity`·`workspace status` 표면이 본 결정의 상태를 읽는 소비자다. `docs/VALIDATION.md`는 이미 replay·capacity·malformed JSON 벡터를 다루므로 본 결정은 그 검증 틀의 연장이다. `capital/service.py`의 `MAX_OPERATIONS=500`("bounded local demo, not a financial limit")과 journal·receipt·`state_digest` 위생이 용량·실패 규칙의 선례다. `capital/ports.py`의 `StoragePort`("load and save one local workspace envelope")가 단일 envelope 제약의 근거이다.

## 3. 항목별 결정

### 3.1 `overlay_storage_shape` — ADOPTED: SINGLE_ENVELOPE_TWO_JOURNALS

**결정.** 오버레이는 단일 workspace envelope 안의 별도 `overlay` 저널(append-only entry 열)로 영속한다. derived-only와 두 번째 파일을 모두 기각한다.

- 섹션: `clock`(sim_day, tick 사유·발생 overlay index), `interest_ledger`(일별 단리 메모; rate·basis는 `CAPITAL-TERMS-V1`을 **참조**하고 숫자를 재명시하지 않는다), `recovery_ledger`, `decision_records`(note id·`terms_version`·`status` 바인딩 시점), `agent_proposals`(`proposal_id`, lane ident, 접수 index, outcome).
- 각 entry는 `overlay_id`(dedup 키), `after_journal_index`(자신이 의존하는 command journal 위치), `sim_day`, `kind`, `payload`를 가진다.
- `overlay_state` materialized 블록 + `overlay_digest`를 함께 저장하되 **권위는 저널 fold**다. materialized 블록은 로드 시 검증용 캐시일 뿐이다.

**기각 이유.** (a) derived-only: `sim_day` tick, decision-note 적용(terms_version 바인딩), agent proposal 접수는 command journal에서 유도 불가한 자체 이벤트다. 이자·회수 메모는 command와 1:1이 아니라 시간 경과에 붙는다. (b) 두 번째 파일: `FileWorkspace`의 checksum+rename 원자성은 한 문서 단위다 — 두 파일은 부분 갱신 창을 만든다. (c) 스냅샷-only: 감사·재생 근거가 사라진다.

### 3.2 `overlay_replay_rule` — ADOPTED: FOLD_THEN_VERIFY

로드 순서를 다음으로 고정한다:

1. `verify_document` checksum 검증(기존 동일).
2. `envelope_version` 검사(§3.3).
3. command journal을 기존 pinned FSM 경로로 순서 재생 — op id dedup·영수증 재구성은 현행 규칙 그대로.
4. overlay journal을 `after_journal_index` 오름차순으로 deterministic fold. `overlay_id` 중복은 멱등 무시( operation id dedup과 동일 철학).
5. fold 결과의 digest와 persisted `overlay_state.digest` 비교.

**실패 규칙.** checksum·스키마·digest 불일치, 존재하지 않는 `after_journal_index` 참조, 필수 필드 누락, 미지원 `overlay_schema` → **fail closed**: envelope 전체를 거부하고 `workspace_status`를 실패 라벨로 보고한다. 부분 overlay로 계속 진행, fold 결과로 자동 덮어쓰기(자기수복), commands만 살리고 overlay를 버리는 경로는 모두 금지다 — terms_version 바인딩이 유실된 채 재생되면 무단 rate가 적용될 수 있다. 재생성은 명시적 새 workspace에서만 허용한다.

**경계.** `sim_day`의 경제적 권위와 overlay digest의 export 서명은 `overlay-digest-export-decision` 소관이다. 본 결정은 저장과 재생의 정합 규칙만 정한다.

### 3.3 `workspace_envelope_version` — ADOPTED: envelope_version 2 / overlay_schema 1

- `envelope_version: 2`는 envelope 최상위 필드, `overlay_schema: 1`은 `overlay` 섹션 내부 필드다. checksum 알고리즘과 vendor 바이트는 변경 없다.
- **v1 로드 규칙(승격).** v1 envelope는 `overlay` 섹션이 없다. 부재는 오류가 아니라 "빈 overlay"로 간주해 정상 로드한다: `sim_day=0`에서 시작하고 terms 미적용 상태(`NOT_BOUND`)로 fold하며, **다음 save에서 v2로 기록**(in-place 승격). v1의 기존 필드·순서·receipt는 재작성·재서명하지 않고 보존한다.
- **실패 규칙(fail closed).** `envelope_version` 미존재·0·음수·현행 초과(>2) → 거부. `overlay` 섹션이 존재하나 unreadable(JSON parse 실패, `overlay_schema` 미지원, entry 스키마 위반, digest 불일치) → **envelope 전체 거부**. overlay만 폐기하고 진행하는 것은 §3.2와 동일 이유로 금지다.

### 3.4 `overlay_capacity_bounds` — ADOPTED: demo bound set

| bound | 값 | 근거 |
|---|---|---|
| `OVERLAY_MAX_ENTRIES` | 2000 | `MAX_OPERATIONS=500`의 op당 최대 ~4 overlay events(제안 접수·terms 적용·tick·메모) 커버 |
| `OVERLAY_ENTRY_MAX_BYTES` | 4096 | 메모·proposal payload는 키-값 수준; 대형 blob은 overlay가 아니라 evidence 채널 소관 |
| `SIM_DAY_MAX` | 3650 | 논리 10년 — 표준 60일·연장 포함 180일 상한(`CAPITAL-TERMS-V1`)의 수십 배 여유 |
| `AGENT_PROPOSALS_MAX` | 500 | `MAX_OPERATIONS`와 동형 — lane 제안은 command를 초과하지 않는다 |
| `DECISION_RECORDS_MAX` | 64 | decision note 바인딩은 드문 이벤트 |
| `ENVELOPE_MAX_BYTES` | 4194304 (4 MiB) | rename-atomic 단일 JSON의 보수적 상한 |

**초과 동작.** command/overlay 어느 쓰기든 한도 초과 시 `CAPACITY_EXCEEDED` 계열로 거부하고 journal·overlay 미기록·`state_digest` 불변(400 `ASSET_MISMATCH`가 journal 무기록을 보장하는 것과 동일한 fail-closed 위생). `GET /api/state` `capacity` 블록에 한도·현재치를 계속 노출한다. 이 한도는 `MAX_OPERATIONS`와 같은 **데모 경계이지 신용·금융 한도가 아니며**, stage5 내구 트랜잭션의 용량 주장도 아니다.

## 4. capital-decision-v1

```capital-decision-v1
{"schema":"capital-decision-v1","decision_id":"overlay-state-decision","decided_by":"GLM-5.3 xhigh → swe-2 → Fable 5.1, delegated by JunTae 2026-10-08 (tertiary 10-14 18:15)","date":"2026-10-14","provisional":true,
  "entries":{
    "overlay_storage_shape":{"status":"ADOPTED","value":{"mode":"SINGLE_ENVELOPE_TWO_JOURNALS","overlay_sections":["clock","interest_ledger","recovery_ledger","decision_records","agent_proposals"],"materialized_state":"CACHE_OF_FOLD","authoritative":"overlay_journal_fold","derived_only":false,"second_file":false,"entry_fields":["overlay_id","after_journal_index","sim_day","kind","payload"]},"provided_by":"GLM-5.3 xhigh → swe-2 → Fable 5.1, delegated by JunTae 2026-10-08 (tertiary 10-14 18:15)","date":"2026-10-14","cap_rows":["CAP-11"],"rationale":"sim_day ticks, terms_version bindings and agent proposal intake are not derivable from the command journal, so overlay needs its own persisted journal; FileWorkspace checksum+rename atomicity is single-document, so the journal lives inside the one envelope; materialized state stays a verification cache with the fold as authority.","provisional":true,"basis":"PRODUCT_DECISION"},
    "overlay_replay_rule":{"status":"ADOPTED","value":{"order":["verify_checksum","check_envelope_version","replay_command_journal","fold_overlay_journal_by_after_journal_index","compare_fold_digest_to_persisted"],"idempotency":"overlay_id dedup","dangling_journal_ref":"FAIL_CLOSED","mismatch_or_unreadable":"FAIL_CLOSED_NO_REPAIR_NO_PARTIAL_OVERLAY","digest_export_and_clock_authority":"overlay-digest-export-decision"},"provided_by":"GLM-5.3 xhigh → swe-2 → Fable 5.1, delegated by JunTae 2026-10-08 (tertiary 10-14 18:15)","date":"2026-10-14","cap_rows":["CAP-11"],"rationale":"Mirrors the existing command-journal replay hygiene (dedup, state_digest integrity) and prevents a lost terms_version binding from silently applying unauthorized rates; self-repair by rewriting is rejected because it erases the audit trail.","provisional":true,"basis":"PRODUCT_DECISION"},
    "workspace_envelope_version":{"status":"ADOPTED","value":{"envelope_version":2,"overlay_schema":1,"v1_load":"ACCEPT_AS_EMPTY_OVERLAY_AND_PROMOTE_ON_NEXT_SAVE","v1_field_preservation":"no rewrite or resign","version_absent_or_gt_supported":"REJECT","unreadable_overlay_section":"REJECT_WHOLE_ENVELOPE","checksum_algorithm":"UNCHANGED"},"provided_by":"GLM-5.3 xhigh → swe-2 → Fable 5.1, delegated by JunTae 2026-10-08 (tertiary 10-14 18:15)","date":"2026-10-14","cap_rows":["CAP-11"],"rationale":"A single top-level version bump keeps v1 files loadable without migration tooling while an inner overlay_schema lets the overlay evolve independently; rejecting the whole envelope on a broken overlay preserves the binding integrity that a partial load would silently lose.","provisional":true,"basis":"PRODUCT_DECISION"},
    "overlay_capacity_bounds":{"status":"ADOPTED","value":{"OVERLAY_MAX_ENTRIES":2000,"OVERLAY_ENTRY_MAX_BYTES":4096,"SIM_DAY_MAX":3650,"AGENT_PROPOSALS_MAX":500,"DECISION_RECORDS_MAX":64,"ENVELOPE_MAX_BYTES":4194304,"overflow":"CAPACITY_EXCEEDED_FAIL_CLOSED_NO_WRITE_STATE_DIGEST_UNCHANGED","exposed_in":"GET /api/state capacity block","label":"DEMO_BOUND_NOT_FINANCIAL_LIMIT_NOT_STAGE5_CAPACITY"},"provided_by":"GLM-5.3 xhigh → swe-2 → Fable 5.1, delegated by JunTae 2026-10-08 (tertiary 10-14 18:15)","date":"2026-10-14","cap_rows":["CAP-11"],"rationale":"Extends the MAX_OPERATIONS=500 bounded-demo posture to the overlay with headroom (~4 overlay events per op, 10-year logical clock, 4 MiB atomic-rename envelope); overflow fails closed with no journal write, matching existing command hygiene.","provisional":true,"basis":"PRODUCT_DECISION"}
  }}
```

## 5. 수용 기준 매핑

- `docs/decisions/CAPITAL_OVERLAY_STATE.md` + capital-decision-v1 블록이 네 항목을 모두 ADOPTED로 커버 → §4 블록.
- v1 파일의 v2 하의 로드 규칙 → §3.3 "v1 로드 규칙(승격)".
- unreadable overlay 섹션의 fail-closed → §3.2 실패 규칙 + §3.3 `REJECT_WHOLE_ENVELOPE`.
- diff는 본 문서 한 파일; `capital/`·`tests/`·vendor 무수정.

## 6. Open risks

- materialized `overlay_state` 캐시와 fold의 drift 가능성 — digest 비교로 탐지하되 자기수복은 금지했으므로 운영 복구 절차가 별도 필요하다.
- v1→v2 승격 도중 크래시 창 — rename 원자성이 커버한다고 가정하지만 마이그레이션 벡터가 없으면 미검증이다.
- 4 MiB/2000 entries 상한이 장기 시뮬레이션 데모를 자를 수 있다 — 상한 상향은 후속 결정 사안.
- CAP-11은 여전히 `NOT_BOUND`; 본 결정은 stage5 내구 트랜잭션·exactly-once를 주장하지 않는다.

## 7. 후속 작업

- `persistence-port` 노드: envelope v2/`overlay_schema` 1을 `FileWorkspace` 어댑터에 구현하고 `tests/storage_conformance.py`에 v1→v2 승격·unreadable overlay·overflow·digest-mismatch 벡터 추가.
- `terms-overlay`: §3.1 스키마로 `interest_ledger`·`decision_records` 기록(`CAPITAL-TERMS-V1` 참조, 숫자 재명시 금지).
- `overlay-digest-export-decision`: `sim_day` 경제적 권위와 overlay digest의 export/서명 경계 확정.
- `decision_ledger.py` 인덱스에 본 노드 등록 확인.
