# Capital 클로즈아웃 다이제스트 아티팩트 결정 — `fin-finance-closeout` 입력 벡터용 결정론적 커밋 산출물

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
이 문서는 KIX-CAPITAL 저장소 안의 **시뮬레이션·제품 설계용** 결정이다. 실자금이 움직이지 않으며, production은 계속 `NOT_AUTHORIZED`다. 어떤 upstream 노드(`fin-finance-closeout` 포함 여덟 후보 전부)의 완료도 주장하지 않고, SEMANTIC_CONFORMANCE도 주장하지 않는다. 채택은 upstream의 실제 PR·병합 영수증만이 증명한다. 이 문서는 kix-protocol·kix-commerce-apps를 수정하지 않고, diff는 `docs/decisions/CAPITAL_CLOSEOUT_ARTIFACT.md` 한 파일이다. `capital/`·`tests/`·`scripts/`·vendor 바이트·골든 digest·기존 결정 노트의 상태 토큰은 건드리지 않는다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `closeout-artifact-decision` (Decision: commit a deterministic closeout digest artifact as the fin-finance-closeout input vector) · deps `finance-vector-pack` · kind `decision` · user_merge `False` |
| 결정자 | **GLM-5.3 xhigh → swe-2 → Fable 5.1, delegated by JunTae 2026-10-08 (tertiary 10-14 18:15)** |
| 위임 원문 | 2026-10-08 18:25 KST JunTae Park: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." |
| 결정일 | 2026-10-15 |
| KIX-CAPITAL 기준 | main `0d7736d`. 선행 결정 문서는 [CAPITAL_FINANCIAL_TERMS.md](CAPITAL_FINANCIAL_TERMS.md), [CAPITAL_UPSTREAM_BINDING.md](CAPITAL_UPSTREAM_BINDING.md), [CAPITAL_ACCOUNTS_TAX_LEGAL.md](CAPITAL_ACCOUNTS_TAX_LEGAL.md), [CAPITAL_SETTLEMENT_POLICY.md](CAPITAL_SETTLEMENT_POLICY.md)이며 이 문서는 그 값·라벨·DEFERRED/NOT_BOUND 상태와 충돌하지 않는다 |
| kix-protocol 기준 | `751c51b` (읽기 전용 체크아웃 `/workspace/capital-run/kixproto-ro`) |
| vendor pin | `capital/vendor/manifest.json` commit `7481b0e16ce9b903abbffa62249bb91cd9e63cfe`, 다섯 파일 SHA256 불변 |
| 문제 | `docs/VALIDATION.md` §`finance-vector-pack`: 여덟 후보 중 `fin-finance-closeout`만 `vectors: null`이다. 그 named input `build/acceptance-evidence.json`이 git 미추적·실행마다 다른 파일(git `head_sha`·로컬 도구 버전을 실음)이라 핀할 안정 바이트가 없기 때문이다 |
| 상태 어휘 | **ADOPTED** = 위임 범위 안의 잠정 값. **UNDETERMINED** = 값을 정할 수 없어 담당·이유만(`value: null`, 방향은 `target`). 다섯 항목 모두 ADOPTED다 |

## 1. 결정 요약

| item | 결정 (요지) | CAP rows | 소비 노드 / seam |
|---|---|---|---|
| `committed_artifact_choice` | **ADOPTED.** `CAPITAL-CLOSEOUT-DIGEST-V1`: 통과한 acceptance evidence에서 per-run 필드를 제거한 결정론적 다이제스트를 `tests/vectors/closeout_digest.json`(format `KIX_CAPITAL_CLOSEOUT_DIGEST_V1`)으로 커밋한다. 다음 `finance_vectors.py --write`가 그룹 `closeout_digest` → 후보 `fin-finance-closeout`으로 내장해 `vectors: null`을 대체한다 | CAP-13, CAP-14 | vector-pack 재생성 / `fin-finance-closeout` 입력 후보 |
| `stripped_fields_policy` | **ADOPTED.** `CAPITAL-CLOSEOUT-STRIP-V1`: `head_sha`, 도구 버전 맵, 시계·소요 필드, `instance_id` 계열, 경로·호스트 필드를 모든 깊이에서 제거(커버 필드는 허용목록). 제거 키 목록은 산출물 `stripped_keys`에 기록 | CAP-14 | closeout digest 생성기 |
| `regeneration_trigger_policy` | **ADOPTED.** `CAPITAL-CLOSEOUT-REGEN-V1`: `ok:true`·`SIMULATED`·`funds_executed:false`인 evidence만 `--write` 허용. 커버 면이 바뀌면 재생성, per-run 필드만 다르면 불요. 수용 런 → write → vectors write → 수용 재런의 2-pass. 손편집 금지 | CAP-20 | 검증 명령 목록 |
| `check_wiring` | **ADOPTED.** `CAPITAL-CLOSEOUT-CHECK-V1`: `scripts/closeout_digest.py --check`(무증거 구조 게이트: canonical·정직 라벨·스트립 키 부재·finance vectors 내장 사본과 바이트 일치) + `--check-evidence`(신선 evidence와 바이트 비교, 첫 drift 경로 명시). acceptance 래더에 단계를 추가하지 않는다(자기참조 방지) | CAP-14, CAP-20 | 검증 목록, `tests/test_closeout_digest.py` |
| `honesty_label_policy` | **ADOPTED.** `CAPITAL-CLOSEOUT-LABEL-V1`: `INPUT_VECTOR_CANDIDATE`, `semantic_conformance:false`, `upstream_nodes_completed:[]`, 분모 8 후보 불변, 사람 수용·독립 리뷰·CI 주장 없음 | CAP-13, CAP-14, CAP-20 | vector pack · upstream 소비자 |

## 2. KIX 비전과의 연결

읽은 것은 supervisor pack이 정한 경로뿐이다.

- **벡터 공급자 역할의 미완성 한 칸을 닫는다.** `docs/decisions/CAPITAL_UPSTREAM_BINDING.md` §3.3 `stage6_finance_candidates`(DEFERRED, CAP-13/14): 여덟 후보의 정본은 `docs/aiops/FINANCE_PENDING_NODES.json`이고 Capital의 역할은 "소비자측 참조 구현과 벡터 공급"이며 `fin-finance-closeout ← build/acceptance-evidence.json`(소비자 증거 후보)로 매핑됐다. `docs/VALIDATION.md` §`finance-vector-pack`은 그 입력이 미추적 per-run 파일이라 `vectors: null`이라고 기록한다. 이 결정은 **같은 evidence에서 파생되지만 핀 가능한 바이트**를 만들어 그 한 칸을 닫는다 — 후보를 DONE으로 만드는 것이 아니라 입력 후보를 실제로 존재하게 하는 것이다.
- **결정론적 재생 — 모델 1의 기록·재생 분리.** `/workspace/capital-run/kixproto-ro/README.md` §1(권위 모델 1: 체인 권위/오프체인 위임 실행, 검증 장치 기준선)과 `docs/decisions/AUTHORITY_MODEL_1.md`(pack이 경로만 제공; 위임 결정 체계의 근거 문서로 인용). 스트립 정책은 "실행 사실(시계·인스턴스·호스트)"과 "재생 가능한 결과(다이제스트·카운트·상태)"를 분리해, 두 번 실행해도 같은 바이트가 나오는 산출물만 커밋한다. `docs/VALIDATION.md` §`manifest-verifier-vectors`의 `strip_volatile` 규약과 §`asset-spec-krw`의 canonical JSON 관례를 그대로 따른다.
- **정직 경계는 기존 seam 문법 그대로.** `docs/SEAMS.md`: `ADOPTED`는 upstream 영수증이 있을 때만이고 로컬 통과는 SEMANTIC_CONFORMANCE가 아니다. 다이제스트는 "이 저장소의 도구가 이 바이트를 만들었다"는 자기 주장 증거이며 외부 검증이 아니다. `docs/VALIDATION.md` §`finance-vector-pack`의 문구(`semantic_conformance:false`, `upstream_nodes_completed:[]`, 분모 불변)를 산출물에 그대로 계승한다.
- **수용 사다리와의 관계.** `CAPITAL_UPSTREAM_BINDING.md` §3.10 `t01_t06_qualification`(CAP-20, DEFERRED)과 `docs/VALIDATION.md`("Human product acceptance is not part of this ladder"). 다이제스트는 래더 통과 사실을 싣지만 사람 수용·통합 수용(Q2 이후)은 계속 미달이다. `docs/CAPITAL_REQUIREMENTS_KO.md`의 규율(이전 CI·미래 계획의 존재를 현재 구현 완료로 옮기지 않는다)에 따라, 커밋된 증거 후보의 존재를 완료로 읽지 않는다.

## 3. 항목별 결정

### 3.1 committed_artifact_choice (CAP-13, CAP-14)

- **값.** `CAPITAL-CLOSEOUT-DIGEST-V1`. **커밋한다.** 산출물 = `tests/vectors/closeout_digest.json`, format `KIX_CAPITAL_CLOSEOUT_DIGEST_V1`, canonical ASCII JSON(키 정렬·단일 trailing newline; 시계·인스턴스·경로 없음 — `finance_vectors.json`과 같은 규약). 파생 원천은 `scripts/acceptance.py`가 쓰는 미추적 `build/acceptance-evidence.json`이다. 커버 필드(허용목록): `ok`, `label`, `funds_executed`, 단계별 결과(단계 id·status/exit·`test_count` — 파서가 의도적으로 null로 두는 node-check·browser 값 포함), seeded-demo의 `state_digest`·`content_digest`·`debit`·`credit`, 패키지 산출물 `sha256`, vendor pin commit과 다섯 파일 `verified` 플래그, `fin-finance-closeout`을 이름붙이는 candidates 인덱스 항목, format·정직 라벨. 그다음 `scripts/finance_vectors.py --write`는 그룹 `closeout_digest`를 추가해 이 문서를 **내장**하고(다른 일곱 그룹과 같은 방식), `candidates["fin-finance-closeout"].vectors`를 `null`+reason에서 다이제스트 참조로 바꾼다. 독립 파일이 재생성 원천으로 남으므로 `finance_vectors.py --check`는 evidence 없이 클린 체크아웃에서 계속 동작한다.
- **근거.** 여덟 번째 후보가 null인 이유는 "핀할 안정 바이트 부재" 하나뿐이다. evidence 자체는 커밋할 수 없지만(`head_sha` 자기참조, 도구 버전 환경 의존), 그 **결정론적 부분집합**은 커밋할 수 있고, 그것이 후보가 요구하는 소비자 증거 후보의 실질이다.
- **대안 기각.** (a) 원본 evidence 통째 커밋: 실행마다 바뀌어 불가. (b) null 유지: 위임상 결정 지연 사유가 아니며 여덟 칸 중 한 칸을 영구히 비운다. (c) 손으로 쓴 요약 문서: 생성기 파생이 아니면 drift를 검증할 수 없다.
- **게이트.** 이 노트는 결정만 한다. 파일 생성·스크립트·테스트·vector-pack 갱신·`CAPITAL_UPSTREAM_BINDING.md` 매핑 문구 갱신은 구현 노드의 diff다.

### 3.2 stripped_fields_policy (CAP-14)

- **값.** `CAPITAL-CLOSEOUT-STRIP-V1`. 두 겹: (1) **허용목록 투영** — §3.1의 커버 필드만 산출물에 들어간다. (2) **키 이름 스트립** — `capital/export.py` `content_material()`/`strip_volatile`과 같은 관례로, 다음 키를 모든 깊이에서 제거: `head_sha`, `instance_id`, `created_at`, `saved_at`, `timestamp`, `timestamps`, `recorded_at`, `duration_s`, `wall_time_s`, `elapsed_s`, `tools`, `tool_versions`, `out_dir`, `output_dir`, `workspace_dir`, `host`, `cwd`, `path`. 클래스별 이유: `head_sha` = 자기참조(산출물을 담은 커밋이 그 값을 바꾼다); 도구 버전 = 환경 의존, per-run evidence와 `docs/VALIDATION.md` 산문의 자리; 시계·소요 = 벽시계; 인스턴스 = 프로세스마다 다름; 경로·호스트 = 개발기 배치. 제거된 키 목록은 산출물의 `stripped_keys`에 기록해 리뷰어가 무엇이 빠졌는지 본다.
- **근거.** 스트립이 있어야 "같은 코드·다른 실행"이 같은 바이트를 낸다. 허용목록이 있어야 새 단계 필드가 우연히 per-run 값을 싣지 않는다.
- **대안 기각.** 도구 버전을 정보용으로 보존: 환경 drift가 `--check`를 깨 결정론을 잃는다. `test_count`도 제거: 파서의 의도적 null까지 포함한 카운트가 오히려 정직한 신호다.

### 3.3 regeneration_trigger_policy (CAP-20)

- **값.** `CAPITAL-CLOSEOUT-REGEN-V1`. **쓰기 게이트**: 생성기는 evidence가 `ok:true`·`label SIMULATED`·`funds_executed:false`일 때만 `--write`를 받아들인다(실패 런을 다이제스트로 굳히는 것을 막는다). **재생성 필수**: (a) 래더 단계 구성이나 커버된 단계 결과 변경, (b) 커버된 카운트·다이제스트 변경(unit/conformance 카운트, 골든 `state_digest`/`content_digest`, `debit`/`credit`, 패키지 `sha256`, vendor pin·`verified`), (c) 스트립 목록·format 버전 변경, (d) `FINANCE_PENDING_NODES` 후보 집합 변경. **불요**: per-run 필드만 다른 경우(새 `head_sha`, 다른 도구 버전, 새 타임스탬프) — 스트립 덕에 커버 바이트가 동일하다; docs-only·비커버 변경 — `--check`가 판정자다. **절차**: 작업 병합 → `python3 scripts/acceptance.py` → `closeout_digest.py --write` → `finance_vectors.py --write` → `acceptance.py` 재실행 한 번; 두 번째 evidence의 커버 필드가 첫 번째와 바이트 일치해야 한다(카운트·digest는 같은 트리에서 안정). 손편집 금지, `--update` 류 플래그는 `--write`뿐이다.
- **근거.** 2-pass는 재귀를 푼다: unit 단계는 갱신된 vector pack을 트리 안에서 검증하므로, 재런 evidence가 첫 런의 커버 필드와 같으면 산출물이 자기 검증을 포함한 최종 트리를 정확히 기술한다.

### 3.4 check_wiring (CAP-14, CAP-20)

- **값.** `CAPITAL-CLOSEOUT-CHECK-V1`. CLI `scripts/closeout_digest.py --write | --check | --check-evidence [--file PATH]`(`manifest_vectors.py`·`finance_vectors.py` 관례). **`--check`** = 무증거 구조 게이트(클린 체크아웃에서 동작): format 태그, canonical 바이트 형태, `label INPUT_VECTOR_CANDIDATE`, `semantic_conformance:false`, `upstream_nodes_completed:[]`, `ok:true`, 스트립 키가 어느 깊이에도 없음, 그리고 `tests/vectors/finance_vectors.json` 그룹 `closeout_digest` 내장 사본과의 바이트 일치. **`--check-evidence`** = `build/acceptance-evidence.json`(`ok:true` 필수)에서 재생성해 바이트 비교; drift·파일 부재 시 exit 1이며 첫 번째로 다른 JSON 경로를 이름붙인다. **래더**: `scripts/acceptance.py`에 새 단계를 넣지 않는다 — evidence가 래더를 기술하고 다이제스트는 그 하류라, 래더 안에 넣으면 자기참조다. 검증 명령 목록에는 `decision_ledger.py`·`not_bound_checklist.py --check`·`finance_vectors.py --check` 옆에 `closeout_digest.py --check`가 들어가고, 커버 면을 건드린 노드는 acceptance 런 뒤 `--check-evidence`를 쓴다. **테스트**: `tests/test_closeout_digest.py`는 기댓값을 손으로 쓰고(생성기에서 읽지 않음) 변이 검사를 포함한다 — `ok:false` 거부, `head_sha` 주입 시 부재, 키 순서 변경 후 동일 바이트, 내장 사본 변조 검출.
- **대안 기각.** `--check`가 항상 evidence를 요구: 클린 체크아웃의 다른 검증이 전부 막힌다. evidence 없이 구조 검사만: drift를 못 잡아 `--check-evidence`를 병행한다.

### 3.5 honesty_label_policy (CAP-13, CAP-14, CAP-20)

- **값.** `CAPITAL-CLOSEOUT-LABEL-V1`. 산출물 최상위: `label: INPUT_VECTOR_CANDIDATE`, `simulated:true`, `provisional:true`, `semantic_conformance:false`, `upstream_nodes_completed:[]`, `funds_executed:false`, `human_product_acceptance:"NOT_PART_OF_LADDER"`, `production:"NOT_AUTHORIZED"`, 그리고 `non_claims` 배열: (i) SEMANTIC_CONFORMANCE 아님; (ii) 어떤 upstream 노드도 완료하지 않음 — `fin-finance-closeout`은 PENDING 후보로 남고 분모는 여덟 그대로; (iii) 자기 주장 증거 — 이 저장소 자체 도구의 산출물이며 독립 리뷰·CI·사람 수용이 아님; (iv) 어느 커밋·툴체인이 만들었는지 주장하지 않음 — `head_sha`·도구 버전은 설계상 제거되며 실제 런의 SHA·버전은 `docs/VALIDATION.md` 산문에 남는다. candidates 인덱스의 `reason` 문자열은 제거되고 상태는 `INPUT_VECTOR_CANDIDATE`를 유지한다.
- **근거.** 이전 노트·산출물의 정직 문법(§2 인용)과 동일한 라벨이어야 소비자가 벡터를 적합성 증명으로 오독하지 않는다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "closeout-artifact-decision",
  "decided_by": "GLM-5.3 xhigh → swe-2 → Fable 5.1, delegated by JunTae 2026-10-08 (tertiary 10-14 18:15)",
  "date": "2026-10-15",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "scope": "KIX-CAPITAL simulation and product design only; not an offer; no real money; production NOT_AUTHORIZED; the artifact is INPUT_VECTOR_CANDIDATE material only: no SEMANTIC_CONFORMANCE, no upstream node completed, no denominator change",
  "delegation": "2026-10-08 18:25 KST JunTae Park delegated financial terms, settlement policy, upstream binding and accounts/tax/legal to Fable with the instruction to proceed with the grand ambition in mind; GLM-5.3 xhigh primary via Claude CLI, swe-2 supervisor fallback (tertiary delegation 2026-10-14 18:15)",
  "policy_version": "CAPITAL-CLOSEOUT-DIGEST-V1",
  "bases": {
    "capital_main": "0d7736d",
    "kix_protocol": "751c51b",
    "vendor_pin_commit": "7481b0e16ce9b903abbffa62249bb91cd9e63cfe",
    "prior_capital_decisions": [
      "docs/decisions/CAPITAL_UPSTREAM_BINDING.md section 3.3 stage6_finance_candidates (DEFERRED, CAP-13/14): eight candidate ids owned by docs/aiops/FINANCE_PENDING_NODES.json; fin-finance-closeout <- build/acceptance-evidence.json",
      "docs/decisions/CAPITAL_UPSTREAM_BINDING.md section 3.10 t01_t06_qualification (DEFERRED, CAP-20): human product acceptance not part of the ladder"
    ],
    "validation_source": "docs/VALIDATION.md finance-vector-pack: seven of eight candidates carry vectors; fin-finance-closeout has vectors null because its named input is an untracked per-run file recording head_sha and tool versions",
    "upstream_status_unchanged": "docs/aiops/FINANCE_PENDING_NODES.json stays the source of truth; all eight candidates stay PENDING upstream; this note supplies a committable input vector candidate only"
  },
  "entries": {
    "committed_artifact_choice": {
      "status": "ADOPTED",
      "value": {
        "policy_version": "CAPITAL-CLOSEOUT-DIGEST-V1",
        "decision": "COMMIT_DETERMINISTIC_CLOSEOUT_DIGEST",
        "artifact_path": "tests/vectors/closeout_digest.json",
        "format": "KIX_CAPITAL_CLOSEOUT_DIGEST_V1",
        "serialization": "canonical ASCII JSON, sorted keys, single trailing newline; no clock, no instance id, no path",
        "derived_from": "build/acceptance-evidence.json (untracked per-run output of scripts/acceptance.py)",
        "covered_fields_allowlist": ["ok", "label", "funds_executed", "per-stage id/status/exit/test_count including parser-intentional nulls", "seeded-demo state_digest/content_digest/debit/credit", "packaged artifact sha256", "vendor pin commit and five verified flags", "candidates index entry naming fin-finance-closeout", "format and honesty labels"],
        "feeds": "next scripts/finance_vectors.py --write adds group closeout_digest naming candidate fin-finance-closeout and embeds this document; candidates.fin-finance-closeout.vectors changes from null to the digest reference",
        "never": ["committing the raw evidence file", "head_sha or tool versions inside the artifact", "hand-editing the artifact"]
      },
      "provided_by": "GLM-5.3 xhigh → swe-2 → Fable 5.1, delegated by JunTae 2026-10-08 (tertiary 10-14 18:15)",
      "date": "2026-10-15",
      "cap_rows": ["CAP-13", "CAP-14"],
      "rationale": "The eighth candidate is null for exactly one reason: no stable bytes exist to pin. The raw evidence cannot be committed (head_sha self-reference, tool-version environment dependence), but its deterministic subset is the substance of the consumer-evidence candidate, so committing a stripped derived digest closes the gap without claiming anything stronger than the other seven groups.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "alternatives_rejected": ["commit raw acceptance-evidence.json", "keep vectors null", "hand-written summary document"],
      "consumer": "finance-vector-pack regeneration (group closeout_digest) / fin-finance-closeout input candidate; upstream completion proof stays upstream's own"
    },
    "stripped_fields_policy": {
      "status": "ADOPTED",
      "value": {
        "policy_version": "CAPITAL-CLOSEOUT-STRIP-V1",
        "layers": ["covered_fields allowlist projection", "key-name strip at every depth, same convention as capital/export.py content_material()/strip_volatile"],
        "strip_keys": ["head_sha", "instance_id", "created_at", "saved_at", "timestamp", "timestamps", "recorded_at", "duration_s", "wall_time_s", "elapsed_s", "tools", "tool_versions", "out_dir", "output_dir", "workspace_dir", "host", "cwd", "path"],
        "reason_per_class": {"head_sha": "self-referential: the commit containing the artifact changes it", "tool_versions": "environment-specific; their place is the per-run evidence and VALIDATION.md prose", "timestamps_and_durations": "wall clock", "instance_ids": "per-process", "paths_and_host": "developer-machine layout"},
        "recorded_in_artifact": "the strip list itself under stripped_keys so a reviewer sees what was removed",
        "kept": "exit codes, ok/status booleans, test_count including parser-intentional nulls, digests, sha256, labels, candidate ids"
      },
      "provided_by": "GLM-5.3 xhigh → swe-2 → Fable 5.1, delegated by JunTae 2026-10-08 (tertiary 10-14 18:15)",
      "date": "2026-10-15",
      "cap_rows": ["CAP-14"],
      "rationale": "Only stripped bytes are reproducible across runs and machines; only an allowlist prevents a new per-run field from slipping into a committed pin. Recording stripped_keys inside the artifact keeps the removal auditable instead of silent.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "alternatives_rejected": ["keep tool versions informational", "also strip test_count"],
      "consumer": "closeout digest generator (scripts/closeout_digest.py)"
    },
    "regeneration_trigger_policy": {
      "status": "ADOPTED",
      "value": {
        "policy_version": "CAPITAL-CLOSEOUT-REGEN-V1",
        "write_gate": "generator refuses unless the evidence has ok=true, label=SIMULATED, funds_executed=false",
        "regenerate_when": ["acceptance ladder stage set or any covered stage outcome changes", "any covered count or digest changes (unit/conformance counts, golden state_digest/content_digest, debit/credit, packaged artifact sha256, vendor pin or verified flags)", "the strip list or format version changes", "the FINANCE_PENDING_NODES candidate set changes"],
        "not_required_when": ["only per-run fields differ (new head_sha, different tool versions, new timestamps) — covered bytes are identical after stripping", "docs-only or non-covered changes; --check is the arbiter"],
        "procedure": ["merge the work", "python3 scripts/acceptance.py for fresh evidence", "python3 scripts/closeout_digest.py --write", "python3 scripts/finance_vectors.py --write (embeds the digest)", "python3 scripts/acceptance.py once more; covered fields must byte-match the first run"],
        "no_hand_edit": true
      },
      "provided_by": "GLM-5.3 xhigh → swe-2 → Fable 5.1, delegated by JunTae 2026-10-08 (tertiary 10-14 18:15)",
      "date": "2026-10-15",
      "cap_rows": ["CAP-20"],
      "rationale": "The write gate keeps a failing ladder run from being frozen into a vector; the two-pass procedure resolves the recursion that the unit stage verifies the regenerated vectors in-tree; exempting per-run-only changes is exactly what stripping buys.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "consumer": "verification command list in docs/VALIDATION.md sections"
    },
    "check_wiring": {
      "status": "ADOPTED",
      "value": {
        "policy_version": "CAPITAL-CLOSEOUT-CHECK-V1",
        "cli": "scripts/closeout_digest.py --write | --check | --check-evidence [--file PATH]",
        "check": "evidence-free structural gate for clean checkouts: format tag, canonical byte form, label INPUT_VECTOR_CANDIDATE, semantic_conformance=false, upstream_nodes_completed=[], ok=true, no stripped key at any depth, byte-equality with the digest embedded in tests/vectors/finance_vectors.json group closeout_digest",
        "check_evidence": "requires build/acceptance-evidence.json with ok=true; regenerates the stripped canonical document and byte-compares; exit 1 names the first differing JSON path; missing evidence exits 1",
        "ladder": "no new stage inside scripts/acceptance.py — the evidence describes the ladder and the digest sits downstream, so a stage inside it would self-reference",
        "verification_list": "runs beside decision_ledger.py, not_bound_checklist.py --check, finance_vectors.py --check; nodes that touch the covered surface run acceptance.py then --check-evidence",
        "tests": "tests/test_closeout_digest.py with hand-written expectations; mutations: ok=false refused, injected head_sha absent, key reorder yields identical bytes, tampered embedded copy detected"
      },
      "provided_by": "GLM-5.3 xhigh → swe-2 → Fable 5.1, delegated by JunTae 2026-10-08 (tertiary 10-14 18:15)",
      "date": "2026-10-15",
      "cap_rows": ["CAP-14", "CAP-20"],
      "rationale": "Mirroring the existing --write/--check CLIs keeps the drift gate uniform; the evidence-free --check keeps clean-checkout verification working while --check-evidence carries the real byte comparison after an acceptance run.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "alternatives_rejected": ["--check always requiring evidence (breaks clean-checkout verification)", "structural check only (catches no drift)"],
      "consumer": "per-node verification list; CI evidence sections"
    },
    "honesty_label_policy": {
      "status": "ADOPTED",
      "value": {
        "policy_version": "CAPITAL-CLOSEOUT-LABEL-V1",
        "labels": {"label": "INPUT_VECTOR_CANDIDATE", "simulated": true, "provisional": true, "semantic_conformance": false, "upstream_nodes_completed": [], "funds_executed": false, "human_product_acceptance": "NOT_PART_OF_LADDER", "production": "NOT_AUTHORIZED"},
        "non_claims": ["not SEMANTIC_CONFORMANCE", "completes no upstream node — fin-finance-closeout stays a PENDING candidate and the denominator stays eight", "self-asserted evidence produced by this repo's own tooling; not independent review, not CI, not human acceptance", "claims nothing about which commit or toolchain produced it — head_sha and tool versions are stripped by design; actual run SHAs stay in docs/VALIDATION.md prose"],
        "candidates_index": "fin-finance-closeout vectors:null plus reason is replaced by the digest reference; the reason string is removed; the entry label stays INPUT_VECTOR_CANDIDATE",
        "binding_note": "the CAPITAL_UPSTREAM_BINDING.md mapping 'fin-finance-closeout <- build/acceptance-evidence.json' is superseded by 'fin-finance-closeout <- tests/vectors/closeout_digest.json (derived from that evidence)'; that note edit belongs to the implementing node, not this diff"
      },
      "provided_by": "GLM-5.3 xhigh → swe-2 → Fable 5.1, delegated by JunTae 2026-10-08 (tertiary 10-14 18:15)",
      "date": "2026-10-15",
      "cap_rows": ["CAP-13", "CAP-14", "CAP-20"],
      "rationale": "Identical honesty grammar to the existing vector pack and seam docs so no consumer reads a locally generated digest as conformance, acceptance, or upstream completion.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "consumer": "vector pack readers and upstream fin-finance-closeout (input candidate only)"
    }
  },
  "confirmations": {
    "kix_protocol_modified": false,
    "kix_commerce_apps_modified": false,
    "capital_code_modified": false,
    "vendor_unchanged": true,
    "upstream_nodes_marked_complete": [],
    "semantic_conformance_claimed": false,
    "denominator_changed": false,
    "diff_scope": "docs/decisions/CAPITAL_CLOSEOUT_ARTIFACT.md only; capital/, tests/, scripts/, capital/vendor/ bytes and every existing note's status tokens unchanged",
    "production": "NOT_AUTHORIZED",
    "real_money": false
  }
}
```

## 5. 수용 기준 매핑

| 수용 기준 | 충족 위치 |
|---|---|
| `docs/decisions/CAPITAL_CLOSEOUT_ARTIFACT.md`에 정확히 하나의 ```` ```capital-decision-v1 ```` 블록, 각 항목이 status·(ADOPTED 시)value·provided_by·date·provisional을 가짐 | §4. fenced 블록은 하나뿐, `entries`에 다섯 키 전부, 각 항목이 필수 키를 가진다 |
| `python3 scripts/decision_ledger.py` exit 0·`closeout-artifact-decision`과 per-entry status 나열 | §4 블록은 선행 노트와 같은 스키마(`ADOPTED` = `value`+`provided_by`+ISO `date`+`provisional:true`)다. 실제 exit 0은 supervisor가 이 파일을 쓴 뒤 확인한다 — 이 세션은 읽기 전용이다 |
| INPUT_VECTOR_CANDIDATE 전용·SEMANTIC_CONFORMANCE 없음·upstream 완료 없음·분모 불변 명시 | 머리말, §3.5, §4 `scope`·`honesty_label_policy.value.non_claims`·`confirmations` |
| diff는 이 파일 하나; `capital/`·`tests/`·vendor 바이트·기존 노트 상태 토큰 불변 | §4 `confirmations.diff_scope`. 구현(스크립트·벡터 파일)은 모두 후속 노드로 명시했다 |

## 6. 열린 위험과 재검토 조건

- **커버 면 drift = 재생성 의무.** 래더 단계·카운트·골든 digest가 바뀌는 노드는 다이제스트와 vector pack을 함께 갱신해야 한다. `--check`/`--check-evidence`가 판정자이고, 이를 건너뛴 노드는 두 파일이 어긋난 채 병합된다.
- **환경 의존 필드의 잔존 가능성.** 스트립 목록 밖의 새 per-run 필드가 evidence에 추가되면 허용목록이 막지만, 커버 필드 자체가 환경 의존적으로 변하면(예: 브라우저 카운트 파싱 변화) `--check-evidence`가 다른 기여자 환경에서 실패할 수 있다. 그때는 스트립이 아니라 커버 정의를 개정하는 별도 결정이다.
- **자기 주장 증거의 한계.** 다이제스트는 "이 도구가 이 바이트를 만들었다"는 사실만 싣는다. upstream `fin-finance-closeout`이 요구하는 소비자 증거의 의미(독립 실행·인증 export)를 충족한다고 읽히면 안 되며, 그 판단은 upstream 노드의 몫이다.
- **바인딩 노트 문구 지연.** `CAPITAL_UPSTREAM_BINDING.md` §3.3의 매핑 문구가 구현 노드 전까지 옛 입력(`build/acceptance-evidence.json`)을 가리킨다. 두 문서가 잠시 어긋나 보이는 것은 의도된 순서이며, §4 `binding_note`가 후속 편집을 명시한다.
- **재검토 트리거.** (1) `FINANCE_PENDING_NODES` 후보 집합 변경, (2) acceptance 래더 단계 추가 요구, (3) `fin-finance-closeout` upstream 정의가 다른 입력 형태를 요구하는 경우, (4) 스트립 규칙과 충돌하는 필수 provenance 요구(그때는 `head_sha`를 evidence 측 참조로만 다루는 V2).

## 7. 후속 작업

- **구현 노드(이 결정의 유일한 직접 소비자).** (1) `scripts/closeout_digest.py`를 `--write`/`--check`/`--check-evidence`로 작성, (2) `tests/vectors/closeout_digest.json` 생성, (3) `scripts/finance_vectors.py`에 그룹 `closeout_digest` 내장과 candidates 인덱스 갱신, (4) `tests/test_closeout_digest.py` 손쓴 기댓값·변이 검사, (5) `docs/VALIDATION.md`에 노드 섹션(실제 실행 명령·결과), (6) `CAPITAL_UPSTREAM_BINDING.md` §3.3 매핑 문구를 §4 `binding_note`대로 갱신 — 모두 그 노드의 diff다.
- **upstream 제출 후보(채택 주장 없음).** `fin-finance-closeout`에 다이제스트를 입력 벡터로 제시; 채택은 upstream PR·병합 영수증만이 증명하며 후보는 그때까지 PENDING이다.
- **검증 목록.** 이후 노드들의 명령 목록에 `python3 scripts/closeout_digest.py --check`를 추가하고, 커버 면을 건드리는 노드는 acceptance 런 뒤 `--check-evidence`를 실행한다.
