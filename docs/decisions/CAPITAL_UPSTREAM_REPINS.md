# Capital 업스트림 리핀 정책 결정 — 핀 분류 어휘, 실행 핀 목록, 연구 기준 규칙, 리핀 트리거·절차, 이중 핀, 클레임 표 재생성, 드리프트 펜스, 현행 핀 평가

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
이 문서는 KIX-CAPITAL 저장소 안의 **시뮬레이션·제품 설계용** 거버넌스 결정이다. 실자금이 움직이지 않으며 production은 계속 `NOT_AUTHORIZED`다. 어떤 upstream 파일도 바꾸지 않고, 어떤 핀도 실제로 옮기지 않으며, 어떤 upstream 계약·노드의 채택·완료도 주장하지 않는다. 채택은 upstream의 실제 영수증(commit·review URL·profile digest)만이 증명한다(`docs/SEAMS.md`의 ADOPTED 정의). diff는 `docs/decisions/CAPITAL_UPSTREAM_REPINS.md` 한 파일이다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `upstream-repin-policy-decision` (Decision: executable pin classes, re-pin triggers and procedure for upstream reference baselines) · deps `upstream-binding-decision`, `audit90-fix2` · kind `decision` · user_merge `False` |
| 결정자 | **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)** |
| 위임 원문 | 2026-10-08 18:25 KST JunTae Park: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." |
| 결정일 | 2026-10-21 |
| KIX-CAPITAL 기준 | main `4cf1de3` |
| kix-protocol 기준 | `a114b5b` (읽기 전용 `/workspace/capital-run/kixproto-ro`) — **이 값 자체가 RESEARCH_BASELINE의 예다** |
| 상태 어휘 | **ADOPTED** = 위임 범위 안의 잠정 값. **UNDETERMINED** = 값을 정할 수 없어 이유만(`value: null`). 여덟 항목 모두 ADOPTED다 |

## 1. 결정 요약

| item | 결정 (요지) | CAP rows | 소비 노드 / seam |
|---|---|---|---|
| `pin_class_vocabulary` | **ADOPTED.** 세 클래스: `EXECUTABLE_VENDOR`(manifest 바이트 잠금), `EXECUTABLE_CITATION`(읽기 전용 인용 핀), `RESEARCH_BASELINE`(출처 기록, 비구속). 앞의 둘만 "실행 핀" | CAP-01, CAP-20 | 모든 결정 노트·claim table·감사 |
| `executable_pin_inventory` | **ADOPTED.** 실행 핀은 정확히 둘: vendor pin `7481b0e`(5파일 SHA256)와 citation pin `e2a029d`(AI 위임 초안 0.1+mock). Commerce `7c24526` 확인값은 BASELINE | CAP-11, CAP-15, CAP-16 | `capital/vendor/manifest.json`, claim 표 4종 |
| `research_baseline_rule` | **ADOPTED.** `기준`/`bases` 칸은 추가전용 출처다. 테스트를 게이트하지 않고, 리핀이 과거 baseline을 소급 수정하지 않으며, 새 노트는 작성 시점 main을 기록 | CAP-01, CAP-20 | `docs/decisions/*` 전부 |
| `repin_trigger_procedure` | **ADOPTED.** 트리거 = 영수증 있는 upstream 채택·수정/보안 픽스 수용 결정·위임된 결정/소유자 지시. upstream main 전진은 트리거가 아님. 절차 = 단일 원자 PR | CAP-11, CAP-15, CAP-16, CAP-20 | `scripts/manifest_vectors.py`, `scripts/docs_surface.py` |
| `dual_pin_handling` | **ADOPTED.** 병합 시점에 bound surface당 핀은 정확히 하나. 상시 이중 핀 전환 창 금지. 서로 다른 surface의 복수 핀은 이중 핀이 아님 | CAP-15, CAP-16 | 향후 리핀 PR |
| `claim_table_regeneration_rule` | **ADOPTED.** claim-table 핀 이동은 **항상 같은 PR에서** 표·벡터를 재생성한다. 핀만 옮긴 PR·핀 없이 표만 바꾼 PR 모두 무효 | CAP-13, CAP-14, CAP-15 | `tests/upstream_claims.json`, `tests/fsm_contract_claims.json`, `tests/read_model_claims.json`, `tests/agent_claims.json` |
| `drift_fence_integration` | **ADOPTED.** 펜스 = manifest SHA256 잠금 + `manifest_vectors.py --check` + `docs_surface.py --check`/README needle + `test_seams.py` 영수증 규칙. 리핀 PR은 모든 펜스 갱신을 같은 diff에 담는다 | CAP-15, CAP-20 | 위 스크립트·`tests/vectors/`·`AGENTS.md` 규칙 |
| `current_pin_assessment` | **ADOPTED.** 두 실행 핀 모두 **HOLD(리핀 보류)**. 사유는 §4.8 | CAP-11, CAP-15, CAP-16 | 현행 main `4cf1de3`의 테스트·골든 |

## 2. KIX 비전과의 연결

인용은 팩이 허용한 경로로 한정한다.

- **기준 구분의 선례.** `/workspace/capital-run/kixproto-ro/README.md`는 "이 문서 작업 시작 시 확인한 main HEAD"를 "기준 스냅샷이며 영원히 최신 HEAD라는 뜻이 아니다"로 라벨하고, 태그·검토 SHA·실험 보존본의 용도를 `docs/status/BASELINES.md`에서 한 번에 구분한다. Capital의 `RESEARCH_BASELINE` vs 실행 핀 구분은 이 패턴의 로컬 적용이다.
- **바이트 잠금의 선례.** 같은 README §2는 검토한 동작을 Git blob으로 잠그고 "주석·명칭·포맷·자동 수정도 잠금 예외가 아니다"라고 못 박는다. `capital/vendor/manifest.json`의 5파일 SHA256 잠금은 동일한 강도의 펜스다.
- **출처와 권위의 분리.** `/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md`는 승인 원문의 Git blob을 기록하되 요약본과 현재 승인의 정본을 분리한다. 결정 노트의 `기준` 칸이 출처 증명이지 실행 구속이 아니라는 규칙의 근거다.
- **현행 핀 목록의 정본.** `docs/CAPITAL_REQUIREMENTS_KO.md`는 두 고정(① `7481b0e` vendor 바이트 핀, ② `e2a029d` AI 위임 초안 읽기 전용 인용 핀)과 각각의 구속 범위를 명시하고, 노트별 `기준` 값은 "출처 증명이며 실행·참조 구속이 아니므로 위 두 고정의 범위 밖"이라고 이미 선언한다. 이 결정은 그 선언을 어휘·절차·펜스로 제도화할 뿐 핀 값을 바꾸지 않는다.
- **펜스 도구.** `docs/SEAMS.md`(영수증 없는 ADOPTED 금지, `test_seams.py`), `docs/VALIDATION.md`(검증 명령 표), 저장소 `AGENTS.md`(`tests/vectors/` 신규 파일은 `docs_surface.py` 항목 + README needle 필요, export 바이트 가드)가 drift 펜스의 실제 집행자다.
- **선행 결정.** [CAPITAL_CLOSEOUT_ARTIFACT.md](CAPITAL_CLOSEOUT_ARTIFACT.md)·[CAPITAL_ARTIFACT_BUNDLING.md](CAPITAL_ARTIFACT_BUNDLING.md)는 vendor pin `7481b0e` 불변을 전제로 쌓였고, [CAPITAL_CLAIM_SLICE_REGISTRY.md](CAPITAL_CLAIM_SLICE_REGISTRY.md)·[CAPITAL_DEFAULT_RECOVERY.md](CAPITAL_DEFAULT_RECOVERY.md)·[CAPITAL_ACCOUNTS_TAX_LEGAL.md](CAPITAL_ACCOUNTS_TAX_LEGAL.md)의 `기준` 칸(`51d8380`·`9eb6b9f`·`244595d`·`adcddc5`·`751c51b`)이 RESEARCH_BASELINE의 실례다.

## 3. 항목별 결정

공통 라벨: 모든 값 `provisional: true`, `basis: PRODUCT_DECISION`. 이 노트는 핀을 옮기지 않는다.

### 3.1 pin_class_vocabulary (CAP-01, CAP-20)

- **값.** 세 클래스를 고정한다.
  - `EXECUTABLE_VENDOR` — upstream commit + vendored 바이트의 per-file SHA256이 `capital/vendor/manifest.json`에 잠긴 핀. 실행·테스트 경로를 구속한다.
  - `EXECUTABLE_CITATION` — upstream commit이 결정 노트(§3.9)와 claim-table JSON에 인용돼 읽기 전용 참조를 구속하는 핀. vendor하지 않고 manifest 해시도 없다.
  - `RESEARCH_BASELINE` — 노트 작성 시점의 체크아웃을 `기준`/`bases`에 기록한 값. 출처 증명이며 어떤 테스트·실행도 게이트하지 않는다.
- `EXECUTABLE_*` 둘을 합쳐 "실행 핀"이라 부른다. 실행 핀의 이동만이 "리핀"이며 이 노트의 절차를 따른다. BASELINE 갱신은 리핀이 아니다.

### 3.2 executable_pin_inventory (CAP-11, CAP-15, CAP-16)

- **값.** 현행 실행 핀 목록은 정확히 둘이다.

| 핀 | 클래스 | upstream 기준 | 구속 범위 | 펜스 |
|---|---|---|---|---|
| vendor pin | `EXECUTABLE_VENDOR` | kix-protocol `7481b0e16ce9b903abbffa62249bb91cd9e63cfe` | vendor된 F04·F01–F03 FSM reference 5파일의 바이트; `tests/upstream_claims.json`, `tests/fsm_contract_claims.json`, `tests/read_model_claims.json`의 인용 | `capital/vendor/manifest.json` SHA256 |
| AI draft pin | `EXECUTABLE_CITATION` | kix-protocol `e2a029d8ac3af7575888dac22fc4bf173ebec232` | `docs/contracts/AI_DELEGATION_AUTHORITY.md` 초안 0.1 + `reference/ai_delegation/` mock의 읽기 전용 인용; `tests/agent_claims.json`(agent lane) | claim JSON의 인용 SHA + binding 노트 §3.9 |

- Commerce main `7c2452645c50b8ede17bdd762794adeabe42319e`는 "확인" 기록이며 `RESEARCH_BASELINE`이다. 새 실행 핀 추가는 위임된 결정 + 펜스 등록 없이 불가하다.

### 3.3 research_baseline_rule (CAP-01, CAP-20)

- **값.** (1) `기준`/`bases` 칸은 **추가전용(append-only)**: 기록된 값은 소급 수정하지 않고, 정정이 필요하면 superseding 노트가 새 baseline을 기록한다. (2) BASELINE은 어떤 테스트·게이트도 묶지 않는다 — 노트가 인용한 연구 시점의 출처일 뿐이다. (3) 새 노트는 작성 시점의 main을 기록한다(이 노트의 `a114b5b`처럼). (4) 실행 핀 리핀은 과거 노트의 BASELINE을 갱신하지 않는다 — 각 노트는 자기 시점의 출처를 영구 보존한다. (5) BASELINE의 전진(upstream main 이동)은 어떤 작업 의무도 발생시키지 않는다.
- **근거.** 출처를 최신으로 고쳐 쓰면 감사가 "어느 시점 연구를 보고 결정했는가"를 재구성할 수 없다. kix-protocol의 blob 잠금·스냅샷 라벨 관행과 같은 이유다.

### 3.4 repin_trigger_procedure (CAP-11, CAP-15, CAP-16, CAP-20)

- **트리거(허용 목록).** 아래 중 하나가 성립할 때만 리핀 PR을 열 수 있다.
  1. **영수증 있는 채택** — upstream 계약이 실제 영수증과 함께 ADOPTED돼(`SEAMS.md`) 관련 표면이 채택 커밋을 가리켜야 할 때.
  2. **수용 결정된 수정** — 핀된 upstream 파일의 정확성·보안 수정을 Capital이 가져오기로 위임 범위 안에서 결정했을 때.
  3. **명시 지시** — 소유자 지시 또는 새 delegated 결정 노트가 특정 핀의 이동을 지명했을 때.
- **비트리거.** upstream main의 전진 자체, "최신화" 욕구, 표면 변경 없는 cosmetic diff, BASELINE 갱신. 핀은 의도적으로 main을 추적하지 않는다.
- **절차(단일 원자 PR).** ① 핀 기록 갱신(commit 필드, 해당 시 manifest commit) → ② vendor의 경우 바이트 재vendor + 5파일 SHA256 재잠금 → ③ 영향받는 claim 표·벡터·골든을 **같은 diff에서** 재생성(§3.6) → ④ `docs_surface.py` 항목·README needle 등 문서 펜스 갱신 → ⑤ `scripts/decision_ledger.py`에 old→new 핀 쌍과 트리거 사유 기록 → ⑥ 검증: `python3 -m unittest discover -s tests -v`, `python3 scripts/manifest_vectors.py --check`, `python3 scripts/docs_surface.py --check`, 필요 시 `python3 scripts/acceptance.py`(VALIDATION.md 표의 명령군) → ⑦ 통상 리뷰·정확헤드 병합 흐름.

### 3.5 dual_pin_handling (CAP-15, CAP-16)

- **값.** **병합 시점에 bound surface당 실행 핀은 정확히 하나**다. 같은 surface를 두 SHA가 동시에 구속하는 상시 전환 창은 금지한다. 리핀 PR의 생애 안에서 old/new 아티팩트가 공존하는 것은 허용되나 병합 커밋에는 단일 핀만 남는다. vendor pin과 citation pin처럼 **서로 다른 surface**의 복수 핀은 이중 핀이 아니며 허용·현행 상태다. 진정한 단계적 이전이 필요해지면 이 노트가 아니라 새 delegated 결정이 승인해야 한다.
- **근거.** 이중 핀 창은 "어느 기준이 claim을 구속하는가"를 시간 의존으로 만들어 감사 재현성을 깬다. 원자 교체가 이 저장소의 펜스 구조(SHA256 잠금 + 결정론적 벡터)와 맞다.

### 3.6 claim_table_regeneration_rule (CAP-13, CAP-14, CAP-15)

- **값.** **claim-table 핀 이동은 항상 그 표와 벡터를 같은 PR에서 재생성한다.** 구체적으로: (1) `tests/upstream_claims.json`, `tests/fsm_contract_claims.json`, `tests/read_model_claims.json`, `tests/agent_claims.json` 중 인용 SHA가 바뀌는 표는 같은 diff에서 재작성한다. (2) 표에서 파생되는 `tests/vectors/` 산출물·골든 digest도 같은 PR에서 재생성한다(`AGENTS.md`의 docs_surface·README needle 규칙 포함). (3) 핀만 옮기고 표를 그대로 둔 PR은 무효, 핀 변경 없이 표의 인용을 바꾼 PR도 무효 — 단 재생성 절차 자체의 버그 픽스는 인용 SHA를 바꾸지 않는 조건으로 허용한다. (4) 재생성 결과와 핀이 불일치하면 `manifest_vectors.py --check`/해당 테스트가 병합 전에 잡아야 하며, 못 잡는 공백은 발견 시 펜스 추가 PR로 닫는다.
- **근거.** 클레임 표는 "핀된 upstream 텍스트에서 무엇을 주장하는가"의 결정론적 산출물이다. 둘이 어긋난 커밋이 하나라도 존재하면 bisect·감사가 깨진다.

### 3.7 drift_fence_integration (CAP-15, CAP-20)

- **값.** 리핀을 둘러싼 펜스와 그 PR이 보이는 모습을 고정한다.
  - **바이트 펜스:** `capital/vendor/manifest.json`의 commit + 5파일 SHA256. vendor 바이트·핀 값 불일치는 테스트가 거절한다.
  - **벡터 펜스:** `python3 scripts/manifest_vectors.py --check`가 19개 파일의 기대 digest를 대조. 재생성 누락은 여기서 드러난다.
  - **문서 펜스:** `tests/vectors/` 신규 파일은 `scripts/docs_surface.py`의 수동 유지 항목 + README needle이 필요(`AGENTS.md`); `--check`가 zero findings여야 한다.
  - **결정 바인딩 펜스:** claim JSON의 인용 SHA가 핀 기록과 일치해야 하며, `tests/test_seams.py`는 영수증 없는 `ADOPTED` 행을 거절한다 — **리핀은 그 자체로 어떤 seam도 ADOPTED로 만들지 않는다.**
  - **원자성:** 위 펜스가 참조하는 old pin은 모두 같은 diff에서 갱신한다. 후속 PR로의 펜스 갱신 유보는 금지다.

### 3.8 current_pin_assessment (CAP-11, CAP-15, CAP-16)

- **값.** 두 실행 핀 모두 **`HOLD` — 지금 리핀하지 않는다.**
  - **vendor pin `7481b0e`: HOLD.** 현행 개발계획 정본이 이 커밋의 `DEVELOPMENT_PLAN.md`를 가리키고(`CAPITAL_REQUIREMENTS_KO.md`), vendor 바이트·세 claim 표·골든·export 바이트 가드가 전부 이 기준에서 정렬돼 711 unittest가 통과한다(`docs/VALIDATION.md`). 이동을 정당화할 upstream 영수증·수정 수용 결정·지시가 없다. upstream main(`a114b5b`)이 앞서 있지만 main 전진은 비트리거이며, 신선도 목적의 리핀은 감사된 기준선을 근거 없이 무효화한다.
  - **AI draft pin `e2a029d`: HOLD.** 초안 0.1의 읽기 전용 인용이고 agent lane/`agent_claims.json`에만 묶이며 mock은 vendor도 해시 잠금도 아니다. 더 새 초안으로 옮기면 채택된 계약 없이 claim 표만 소모성으로 churn된다. upstream이 안정 authority 계약을 내거나 agent lane이 새 조항을 필요로 할 때 §3.4 트리거로 재평가한다.
- **비주장.** HOLD 판정은 두 핀이 가리키는 upstream 내용의 채택·완성을 주장하지 않는다. CAP-11·CAP-15·CAP-16은 계속 `NOT_BOUND`다.

## 4. 결정 블록

```capital-decision-v1
{"schema":"capital-decision-v1","decision_id":"upstream-repin-policy-decision","decided_by":"Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)","date":"2026-10-21","provisional":true,
 "entries":{
  "pin_class_vocabulary":{"status":"ADOPTED","value":{"classes":["EXECUTABLE_VENDOR","EXECUTABLE_CITATION","RESEARCH_BASELINE"],"executable_union":["EXECUTABLE_VENDOR","EXECUTABLE_CITATION"],"baseline_gates_tests":false},"provided_by":"Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)","date":"2026-10-21","cap_rows":["CAP-01","CAP-20"],"rationale":"바이트 잠금·읽기 인용·출처 기록은 구속력이 다르므로 감사가 혼동하지 않게 세 클래스로 분리","provisional":true,"basis":"PRODUCT_DECISION"},
  "executable_pin_inventory":{"status":"ADOPTED","value":{"vendor_pin":{"sha":"7481b0e16ce9b903abbffa62249bb91cd9e63cfe","class":"EXECUTABLE_VENDOR","fence":"capital/vendor/manifest.json","bound_tables":["tests/upstream_claims.json","tests/fsm_contract_claims.json","tests/read_model_claims.json"]},"ai_draft_pin":{"sha":"e2a029d8ac3af7575888dac22fc4bf173ebec232","class":"EXECUTABLE_CITATION","vendored":false,"bound_tables":["tests/agent_claims.json"]},"commerce_check":"7c2452645c50b8ede17bdd762794adeabe42319e (RESEARCH_BASELINE)"},"provided_by":"Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)","date":"2026-10-21","cap_rows":["CAP-11","CAP-15","CAP-16"],"rationale":"실행 핀을 정확히 둘로 열거해 감사의 목록 질문을 닫는다","provisional":true,"basis":"PRODUCT_DECISION"},
  "research_baseline_rule":{"status":"ADOPTED","value":{"append_only":true,"gates_tests":false,"repin_updates_old_baselines":false,"new_notes_record_current_main":true},"provided_by":"Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)","date":"2026-10-21","cap_rows":["CAP-01","CAP-20"],"rationale":"출처 증명의 시간축 보존 — kix-protocol baseline/blob 관행과 동일 논리","provisional":true,"basis":"PRODUCT_DECISION"},
  "repin_trigger_procedure":{"status":"ADOPTED","value":{"triggers":["adopted_upstream_receipt","accepted_correctness_or_security_fix","explicit_delegated_decision_or_owner_directive"],"non_triggers":["upstream_main_advanced","freshness","cosmetic_diff","baseline_refresh"],"procedure":"single atomic PR: pin record -> re-vendor+rehash -> regenerate tables/vectors/goldens -> docs fences -> ledger old->new -> full verification -> normal review"},"provided_by":"Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)","date":"2026-10-21","cap_rows":["CAP-11","CAP-15","CAP-16","CAP-20"],"rationale":"허용 목록 트리거로 drift-chasing을 원천 차단하고 원자 절차로 재현성 확보","provisional":true,"basis":"PRODUCT_DECISION"},
  "dual_pin_handling":{"status":"ADOPTED","value":{"max_pins_per_surface_at_merge":1,"standing_transition_window":false,"distinct_surfaces_multi_pin_allowed":true,"staged_migration_requires":"new delegated decision"},"provided_by":"Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)","date":"2026-10-21","cap_rows":["CAP-15","CAP-16"],"rationale":"시간 의존 이중 기준은 감사 재현성을 깨므로 병합 시 단일 핀만 허용","provisional":true,"basis":"PRODUCT_DECISION"},
  "claim_table_regeneration_rule":{"status":"ADOPTED","value":{"atomic_with_pin_move":true,"pin_move_without_regen":"invalid","regen_without_pin_move":"invalid unless regeneration-bug fix not changing cited SHAs","applies_to":["tests/upstream_claims.json","tests/fsm_contract_claims.json","tests/read_model_claims.json","tests/agent_claims.json","tests/vectors/","goldens"]},"provided_by":"Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)","date":"2026-10-21","cap_rows":["CAP-13","CAP-14","CAP-15"],"rationale":"클레임 표는 핀의 결정론적 산출물 — 같은 PR 재생성이 불일치 커밋을 막는다","provisional":true,"basis":"PRODUCT_DECISION"},
  "drift_fence_integration":{"status":"ADOPTED","value":{"fences":["capital/vendor/manifest.json SHA256 lock","scripts/manifest_vectors.py --check","scripts/docs_surface.py --check + README needles","claim-JSON cited-SHA match","tests/test_seams.py receipt rule"],"all_fence_updates_same_diff":true,"repin_adopts_no_seam":true},"provided_by":"Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)","date":"2026-10-21","cap_rows":["CAP-15","CAP-20"],"rationale":"기존 펜스가 리핀을 그대로 관측하도록 갱신 원자성을 규정","provisional":true,"basis":"PRODUCT_DECISION"},
  "current_pin_assessment":{"status":"ADOPTED","value":{"vendor_pin_7481b0e":"HOLD","ai_draft_pin_e2a029d":"HOLD","reasons":{"vendor_pin_7481b0e":"정본 계획 앵커 + 전 표면 정렬·711 tests green + 트리거 부재","ai_draft_pin_e2a029d":"초안 인용·agent lane 한정 + 채택 계약 없이 이동 시 churn만 발생"},"next_review":"when any §3.4 trigger fires"},"provided_by":"Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)","date":"2026-10-21","cap_rows":["CAP-11","CAP-15","CAP-16"],"rationale":"두 핀 모두 이동 근거 없음 — 감사된 기준선 유지가 정직한 상태 라벨","provisional":true,"basis":"PRODUCT_DECISION"}
 }}
```

## 5. 수용 기준 매핑

- ✅ 이 노트는 `capital-decision-v1` 블록에 여덟 항목을 status와 함께 이름으로 나열한다(§4, 전부 ADOPTED).
- ✅ `7481b0e` vendor pin·`e2a029d` AI 초안 pin·기록된 research baseline을 §3.2·§3.3에서 분류했고 **어떤 핀도 옮기지 않았다**(diff는 이 노트 한 파일).
- ✅ §3.6이 claim-table 핀 이동은 **항상 같은 PR에서 표·벡터를 재생성**함을 명시한다.

## 6. Open risks

- citation pin(`e2a029d`)의 기계적 펜스가 vendor manifest보다 얇다 — 인용 SHA 불일치를 잡는 전용 테스트가 없으면 드리프트가 늦게 발견될 수 있다.
- "수정 수용 결정" 트리거(§3.4-②)의 판정 주체가 명시 지시 없이는 모호할 수 있다 — 실제 발동 시 누가 수용을 결정했는지 PR에 반드시 기록해야 한다.
- CAP row 매핑은 커버리지 표 원문이 아닌 인용 기준이라 차후 조정될 수 있다.

## 7. 후속 작업

- `tests/agent_claims.json`의 인용 SHA를 `e2a029d`와 대조하는 자동 게이트 추가(별도 구현 노드).
- 리핀이 실제로 발동될 때 `scripts/decision_ledger.py`에 old→new 핀 쌍 기록 절차를 첫 실행으로 검증.
- upstream 안정 authority 계약 또는 채택 영수증이 나오면 `current_pin_assessment`를 §3.4 절차로 재평가.
