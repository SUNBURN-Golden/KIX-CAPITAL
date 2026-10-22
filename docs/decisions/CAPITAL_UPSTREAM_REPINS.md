# Capital 업스트림 리핀 정책 결정 — 실행·참조 핀과 연구 기준의 분리

> **PROVISIONAL PRODUCT DECISION — 잠정 제품 결정**
>
> 결정 귀속(요청 지정): **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**
>
> 결정일: **2026-10-22**  
> 기준: **KIX-CAPITAL main `cde0bc7` · kix-protocol `93cec6a`** — supervisor 제공 기준이며 직접 HEAD를 확인한 결과가 아니다.  
> 결정 노드: `upstream-repin-policy-decision`  
> 선행: `upstream-binding-decision`, `audit90-fix2`

Capital 자체 참조의 **시뮬레이션·제품 설계용** 거버넌스다. 실자금은 없으며 production은 **`NOT_AUTHORIZED`**다. 여기서 `ADOPTED`는 위임 범위 안의 잠정 제품 정책이며, upstream 계약 채택·seam 채택·`SEMANTIC_CONFORMANCE`·구현 완료를 뜻하지 않는다. **이번 결정으로 어느 핀도 이동하지 않는다.**

위임 원문: “금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해.”

## 1. 결정 요약

| item | decision | CAP rows | consumer |
|---|---|---|---|
| `pin_class_vocabulary` | **ADOPTED:** vendor 바이트 구속, 인용 구속, 연구 출처의 세 클래스 | CAP-01, CAP-20 | 참조 목록·클레임 표·결정 노트 |
| `executable_pin_inventory` | **ADOPTED:** vendor `7481b0e`, AI 인용 `e2a029d`와 지정 소비 범위 유지 | CAP-11, CAP-15, CAP-16 | manifest·클레임 표 네 종 |
| `research_baseline_rule` | **ADOPTED:** 역사적 출처 보존; 실행 핀과 동일성 강제 금지 | CAP-01, CAP-20 | 노트의 `기준`·`bases` |
| `repin_trigger_procedure` | **ADOPTED:** 수용 근거·영향 분석·원자적 PR·검증 필수 | CAP-11, CAP-15, CAP-16, CAP-20 | 향후 리핀 구현·리뷰 |
| `dual_pin_handling` | **ADOPTED:** 활성 구속 표면당 하나의 핀; 일반 이중 핀 전환 창 없음 | CAP-15, CAP-16 | 실행·참조 소비 경로 |
| `claim_table_regeneration_rule` | **ADOPTED:** 핀 이동 시 해당 표·벡터를 항상 같은 PR에서 재생성 | CAP-13, CAP-14, CAP-15 | 클레임 표·벡터·관련 골든 |
| `drift_fence_integration` | **ADOPTED:** 여덟 binding 등록 유지·정렬 수정; 후보 전체 findings 0 필수 | CAP-15, CAP-20 | decision-binding·문서·벡터 검사 |
| `current_pin_assessment` | **ADOPTED:** 두 현행 핀 모두 `HOLD`; 지금 리핀하지 않음 | CAP-11, CAP-15, CAP-16 | 현행 실행·참조 소비자 |

## 2. KIX 비전 연결

Capital의 금융 기능을 확장하려면 계약 출처, 소비 범위, 주장과 검증 결과를 함께 재현할 수 있어야 한다. 이번 결정은 그 변경 단위를 명확히 하여 향후 upstream 계약 수용과 어댑터 교체를 가능하게 한다.

- [CAPITAL_REQUIREMENTS_KO.md](../CAPITAL_REQUIREMENTS_KO.md)의 제공 발췌가 vendor 핀, AI 초안 인용 핀, 결정 노트의 연구 기준을 구분한다. 이를 분류 기준으로 삼는다.
- [SEAMS.md](../SEAMS.md)의 제공 발췌에 따라 실제 계약 대체와 upstream 영수증이 있어야 seam을 채택할 수 있다. 리핀이나 로컬 벡터 통과는 영수증을 대체하지 않는다.
- [VALIDATION.md](../VALIDATION.md)의 과거 검증 결과는 이번 후보의 통과 증거로 재사용하지 않는다.
- [CAPITAL_ARTIFACT_BUNDLING.md](CAPITAL_ARTIFACT_BUNDLING.md)와 [CAPITAL_CLOSEOUT_ARTIFACT.md](CAPITAL_CLOSEOUT_ARTIFACT.md)의 제공 발췌에 따라 결정 출처와 결정론적 산출물을 추적한다.
- [CAPITAL_CLAIM_SLICE_REGISTRY.md](CAPITAL_CLAIM_SLICE_REGISTRY.md), [CAPITAL_DEFAULT_RECOVERY.md](CAPITAL_DEFAULT_RECOVERY.md), [CAPITAL_ACCOUNTS_TAX_LEGAL.md](CAPITAL_ACCOUNTS_TAX_LEGAL.md)의 서로 다른 Protocol SHA는 역사적 연구 출처의 사례다.

이번 fix round 3에서는 선행 [CAPITAL_UPSTREAM_BINDING.md](CAPITAL_UPSTREAM_BINDING.md)의 결정 블록과 checker·생성기를 직접 읽었다. 선행 `ai_agent_grant_action_permit`의 `ADOPTED` 범위는 grant·QUERY/PROPOSE lane이며, 지정 핀은 `e2a029d8ac3af7575888dac22fc4bf173ebec232`다. 이 문서의 현재 AI 인용 분류는 그 결정을 취소하거나 adapter 구현 완료를 뜻하지 않는다. 선행의 `DEFERRED`·`UNDETERMINED` 범위는 계속 `NOT_BOUND`로 둔다. 수정 범위는 이 노트, binding 등록과 `tests/vectors/pack/`이며 upstream 파일과 실행 핀은 바꾸지 않는다.

## 3. 항목별 결정

### 3.1 `pin_class_vocabulary`

**ADOPTED.** 클래스는 SHA 문자열 자체가 아니라 **소비 역할과 구속 표면**에 붙인다.

| 클래스 | 구속 의미 | 변경 통제 |
|---|---|---|
| `EXECUTABLE_VENDOR` | 지정 commit의 vendor 파일 바이트·manifest 해시와 연결된 소비자를 구속 | 원본 commit 또는 잠긴 바이트 변경은 리핀 |
| `EXECUTABLE_CITATION` | 지정 commit의 계약·문서·mock 인용을 해당 참조 소비자에 구속 | 인용 commit 변경은 리핀 |
| `RESEARCH_BASELINE` | 결정 작성에 사용한 역사적 연구 스냅샷 | 출처 보존 및 명시적 정정 |

앞의 둘을 실행·참조 핀으로 묶는다. `EXECUTABLE_CITATION`은 runtime 실행, mock vendor 편입 또는 인증 채택을 뜻하지 않는다.

동일 SHA가 연구 출처와 실행 기준에 함께 등장해도 역할은 별개다. 새 소비자는 기존 SHA를 사용하더라도 대상 경로·소비 범위·검사·binding을 명시해야 한다. 문자열 일치만으로 기존 구속 범위가 확장되지 않는다.

### 3.2 `executable_pin_inventory`

**ADOPTED.** 현재 실행·참조 핀은 다음 두 개다.

| 클래스 | 전체 SHA | 구속 범위 |
|---|---|---|
| `EXECUTABLE_VENDOR` | `7481b0e16ce9b903abbffa62249bb91cd9e63cfe` | F04·F01–F03 FSM reference 다섯 파일, vendor manifest SHA256, `tests/upstream_claims.json`·`tests/fsm_contract_claims.json`·`tests/read_model_claims.json`의 관련 인용 |
| `EXECUTABLE_CITATION` | `e2a029d8ac3af7575888dac22fc4bf173ebec232` | AI 위임 권한 계약 초안 0.1, `reference/ai_delegation/` mock의 읽기 전용 인용, `tests/agent_claims.json` |

AI mock은 vendor되지 않았고 manifest 해시도 없다. 인용 핀 검사를 vendor 바이트 검증으로 표시하지 않는다.

팩의 Commerce `7c2452645c50b8ede17bdd762794adeabe42319e`는 확인 출처다. 이 문서가 Commerce에 새 실행 구속을 만들지는 않는다. 이번 Capital `cde0bc7`과 Protocol `93cec6a`도 문서의 연구 기준이다.

향후 핀 등록에는 저장소, 전체 SHA, 대상 경로·계약 범위, 소비자, 검증 방법과 수용 근거를 기록한다. 현재 목록의 바이트·SHA·소비 범위는 변경하지 않는다.

### 3.3 `research_baseline_rule`

**ADOPTED.** 결정 노트의 `기준`·`bases`는 역사적 출처로 보존한다. 리핀을 이유로 과거 연구 SHA를 일괄 치환하거나 실행 핀과 다르다는 이유만으로 실패 처리하지 않는다.

팩의 Protocol `51d8380`, `adcddc5`, `9eb6b9f`, `751c51b`, `244595d`는 이런 출처다. 값이 서로 다르다는 사실은 실행 드리프트의 증거가 아니다. 일반적인 노트 스키마, binding, 번들 무결성 검사는 계속 적용한다.

새 노트는 실제 사용한 자료의 기준과 출처를 기록하고 직접 확인한 HEAD와 supervisor 제공 값을 구분한다. 잘못된 출처는 날짜·이유·대체 근거를 남겨 정정한다. **2026-10-22 정정:** 이전 원고의 `a2a2e29`를 이번 supervisor pack과 최종 출력 지시의 `93cec6a`로 바로잡는다. 이는 연구 출처 정정이며 실행 핀 이동이 아니다.

### 3.4 `repin_trigger_procedure`

**ADOPTED.** 다음 근거가 있으면 리핀 검토를 개시한다.

1. 실제 upstream 채택 영수증을 특정 Capital 소비자에 적용할 필요.
2. 권한 있는 Capital 결정자의 정확성·보안 수정 수용 결정.
3. 특정 핀 이동을 지명한 소유자 지시 또는 위임 결정.

결함 보고는 검토를 시작할 수 있으나 후보 SHA의 자동 수용은 아니다. upstream main 전진, 최신화 목적, 연구 기준 갱신 또는 cosmetic 변경만으로는 리핀하지 않는다.

리핀 담당자는 old/new 전체 SHA, 트리거, 수용 결정자, 영향 소비자, 호환성·권한 변화와 rollback 방법을 기록한다. 하나의 PR에 다음을 결합한다.

- 새 원본 확인 및 필요한 vendor 바이트·manifest commit·해시 변경.
- 영향 클레임 표·벡터·관련 골든 재생성과 기대값 변경 근거.
- 현행 참조 문서·인용 검사·관련 decision-binding 갱신.
- 새 벡터 파일의 `docs_surface.py` 수동 등록과 README needle.
- 관련 검사, 전체 unittest, 문서 검사 및 영향받는 acceptance 결과.

모든 변경이 결합된 후보를 검증하고 후보 SHA를 증거에 남긴다. 검증 후 내용이 바뀌면 영향받는 검사를 다시 수행한다. 실패 시 전환하지 않는다. 기존 핀을 계속 소비할 수 없는 결함이면 해당 소비를 중단하며 검증되지 않은 후보로 자동 전환하지 않는다.

rollback도 핀·표·벡터·문서·binding을 함께 복원하는 검증된 PR이다. 리핀은 Protocol·Commerce 수정이나 운영 권한 확대를 승인하지 않는다.

### 3.5 `dual_pin_handling`

**ADOPTED.** 병합된 활성 구성에서는 **구속 표면당 정확히 하나의 핀**만 허용한다. 같은 표면에서 old/new 자동 선택, 실패 시 fallback, 상시 이중 핀 전환 창은 허용하지 않는다.

PR 검토 중 old/new 결과 비교는 허용한다. 이전 결과는 비활성 비교 증거로 표시하고 활성 소비 경로에서 제외한다. Git 이력이나 비교 자료 보존은 이중 핀 운영이 아니다.

vendor와 AI 인용처럼 별개 표면이 서로 다른 핀을 쓰는 것은 허용한다. 단계적 이전이 필요하면 별도 위임 결정에서 표면 경계, 선택 규칙, 종료 조건, 검증과 rollback을 먼저 정한다. 이번 결정이 허용하는 일반 전환 기간은 **없음**이다.

### 3.6 `claim_table_regeneration_rule`

**ADOPTED. claim-table 핀 이동은 항상 해당 표와 벡터를 같은 PR에서 재생성한다.** 후속 PR로 미루지 않는다. 관련 골든과 인용 검사도 동일 변경 단위에 포함한다.

vendor 핀 이동은 세 FSM·읽기 모델 클레임 표를, AI 인용 핀 이동은 agent 표를 기본 영향 범위로 삼는다. 리핀 담당자는 각 표와 연결 벡터를 대응시켜 누락 여부를 검토한다.

재생성 결과가 같은 바이트이면 인위적인 diff는 필요 없다. 대신 대상 파일, 재생성 절차와 동일 결과를 후보 증거로 남긴다. 동일할 것이라는 추정으로 재생성을 생략하지 않는다.

생성기가 없는 표·벡터는 새 핀의 주장별 근거와 독립적인 기대 결과를 재구성하고 검토한다. SHA 치환이나 실제 출력에 맞춘 기대값 덮어쓰기는 재생성이 아니다.

핀을 유지하면서 표의 오류·커버리지를 고칠 수 있다. 이 경우에도 근거와 관련 벡터를 검증한다. 새 `tests/vectors/` 파일은 문서 표면 등록과 README needle까지 같은 PR에 포함한다.

### 3.7 `drift_fence_integration`

**ADOPTED. 정렬 위반 blocking finding을 수용하고 실제 등록 순서를 수정했다.**

`tests/decision_bindings.json`의 여덟 레코드를 다음 entry 순서로 정렬했다. 각 레코드의 내용과 다른 레코드는 보존했다.

| entry — 등록 순서 | binding kind / path |
|---|---|
| `claim_table_regeneration_rule` | `module` / `scripts/finance_vectors.py` |
| `current_pin_assessment` | `test_module` / `tests/test_upstream_claims.py` |
| `drift_fence_integration` | `module` / `scripts/decision_bindings.py` |
| `dual_pin_handling` | `test_module` / `tests/test_upstream_claims.py` |
| `executable_pin_inventory` | `test_module` / `tests/test_upstream_claims.py` |
| `pin_class_vocabulary` | `test_module` / `tests/test_upstream_claims.py` |
| `repin_trigger_procedure` | `module` / `scripts/decision_bindings.py` |
| `research_baseline_rule` | `module` / `scripts/decision_bindings.py` |

여덟 binding은 모두 **`PENDING_CONSUMER`**다. 기존 파일은 통합 지점이며 정책별 자동 검증이 구현됐다는 주장이 아니다. 각 `reason`에 미구현 범위가 있다. `consumer_node = upstream-repin-policy-enforcement`는 **후속 로컬 구현 작업명**이며 기존 완료 노드나 upstream 노드라는 뜻이 아니다.

정책 값은 결정됐으므로 `ADOPTED`를 유지한다. 소비 구현의 대기는 정책 미결정과 구분한다. 노트 검색 제외, 무조건 통과 예외, 등록 회피를 위한 `UNDETERMINED` 전환은 금지한다.

펜스별 책임은 다음과 같다.

- vendor 무결성 검사: 원본 commit·vendor 바이트·manifest 해시.
- 클레임·벡터 검사: 인용 핀·주장·기대 동작.
- `scripts/manifest_vectors.py --check`: 해당 도구가 관리하는 manifest 벡터.
- `scripts/docs_surface.py --check`: 문서 표면·산출물 등록·README 연결.
- `scripts/decision_bindings.py`: `ADOPTED` 항목의 binding 등록과 유효성.
- decision-binding 테스트: 전체 `(decision_id, entry)` 목록의 정렬·유일성.
- seam 검사: 실제 upstream 영수증 없는 seam 채택 방지.

**등록 검증:** 앞선 개정에서 여덟 레코드를 재배열했다. 이번 round 3에서 전체 **98개** identity가 `sorted(set(identities))`와 같고 여덟 binding이 모두 `PENDING_CONSUMER`임을 재확인했다. `scripts/decision_bindings.py --check`는 findings 0, `scripts/docs_surface.py --check`는 29 routes·38 artifacts·9 stages로 통과했다. 기존 등록 내용은 이번 round에서 바꾸지 않는다.

**CI 수정:** 결정 블록의 누락된 최상위 `status`를 `PROVISIONAL_PRODUCT_DECISION`으로 명시했다. 개별 여덟 정책의 `ADOPTED`와 노트 전체의 잠정 제품 결정 라벨은 별개다. 누락으로 생긴 decision-surface의 `KeyError: 'status'`와 잘못된 rollup을 함께 바로잡았다. `scripts/pack_vectors.py --check`로 아홉 fixture의 드리프트도 재현했다. 이전 clean pack에는 이 노트의 여덟 `ADOPTED` entry 요약이 빠져 있었다. 생성된 pack과 비교하면 `decisions` section만 바뀌고 나머지 네 section은 동일하다. 정본 생성기의 `--write`로 clean pack과 모든 변조·절단 fixture를 함께 재생성했다. 해시나 기대 오류를 수동으로 고치지 않았으며, 기존 파일만 갱신하므로 새 docs-surface 등록은 필요 없다.

후보 검증 명령은 다음과 같다. 전체 실행의 제한과 실패는 §6에 구분하며, checker 통과를 전체 수용 통과로 표시하지 않는다.

```text
python3 -m unittest discover -s tests -p 'test_decision_bindings.py' -v
python3 scripts/decision_bindings.py --check
python3 scripts/docs_surface.py --check
python3 scripts/pack_vectors.py --check
python3 -m unittest discover -s tests -p 'test_evidence_pack.py' -v
python3 -m unittest discover -s tests -v
```

첫 명령은 리뷰가 지정한 정렬 펜스를 포함한 decision-binding 검사다. 신규 여덟 항목뿐 아니라 **전체 binding findings 0**을 요구한다. 계획이나 선행 PR 링크로 실제 등록과 후보 검증을 대체하지 않는다.

round 3 로컬 결과: pack 17개·binding 22개·결정 파서 9개·비HTTP decision-surface 14개·vendor mock 7개 테스트 통과, pack 아홉 파일의 `--check` 통과, `compileall`과 `node --check` 통과. 이 결과는 `SIMULATED` 로컬 검증이며 전체 HTTP·browser·acceptance 통과가 아니다(§6).

### 3.8 `current_pin_assessment`

**ADOPTED. 두 핀 모두 `HOLD`; 지금 리핀하지 않는다.**

- **vendor `7481b0e`: HOLD.** 요구사항이 다섯 reference 파일과 세 클레임 표의 기준으로 명시한다. 대체할 특정 수정 수용 결정이나 실제 채택 영수증이 팩에 없다.
- **AI 인용 `e2a029d`: HOLD.** 초안 0.1·mock 인용과 agent 표의 기준이다. 다른 계약·조항으로 이동할 구체 근거가 제공되지 않았다.

연구 기준 `93cec6a`는 자동 대체 후보가 아니다. HOLD는 안전성 인증이나 영구 동결이 아니며 §3.4의 근거가 생기면 재평가한다. CAP-11·CAP-15·CAP-16의 해당 미구속 범위는 계속 `NOT_BOUND`다.

## 4. 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "decision_id": "upstream-repin-policy-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-10-22",
  "provisional": true,
  "entries": {
    "pin_class_vocabulary": {
      "status": "ADOPTED",
      "value": {
        "classes": ["EXECUTABLE_VENDOR", "EXECUTABLE_CITATION", "RESEARCH_BASELINE"],
        "binding_classes": ["EXECUTABLE_VENDOR", "EXECUTABLE_CITATION"],
        "classification_basis": "consumer_role_and_bound_surface",
        "citation_implies_runtime_execution": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-01", "CAP-20"],
      "rationale": "바이트 구속, 인용 구속과 역사적 출처를 분리한다.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "executable_pin_inventory": {
      "status": "ADOPTED",
      "value": {
        "vendor_pin": {
          "sha": "7481b0e16ce9b903abbffa62249bb91cd9e63cfe",
          "class": "EXECUTABLE_VENDOR",
          "file_count": 5,
          "manifest": "capital/vendor/manifest.json",
          "bound_tables": ["tests/upstream_claims.json", "tests/fsm_contract_claims.json", "tests/read_model_claims.json"]
        },
        "ai_draft_pin": {
          "sha": "e2a029d8ac3af7575888dac22fc4bf173ebec232",
          "class": "EXECUTABLE_CITATION",
          "vendored": false,
          "bound_tables": ["tests/agent_claims.json"]
        },
        "repin_performed": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-11", "CAP-15", "CAP-16"],
      "rationale": "요구사항에 명시된 두 핀과 소비 범위를 유지한다.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "research_baseline_rule": {
      "status": "ADOPTED",
      "value": {
        "preserve_historical_provenance": true,
        "must_equal_current_executable_pin": false,
        "repin_rewrites_historical_baselines": false,
        "new_notes_record": "actual_used_snapshot_and_source",
        "corrections": "dated_reason_and_replacement_basis",
        "ordinary_note_validation_exempt": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-01", "CAP-20"],
      "rationale": "역사적 출처를 보존하면서 일반 노트 검증은 유지한다.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "repin_trigger_procedure": {
      "status": "ADOPTED",
      "value": {
        "triggers": [
          "applicable_upstream_adoption_receipt",
          "authorized_acceptance_of_correctness_or_security_fix",
          "explicit_owner_or_delegated_directive"
        ],
        "non_triggers": ["upstream_main_advance", "freshness_only", "cosmetic_only", "research_baseline_refresh"],
        "atomic_pr_contents": [
          "old_new_sha_and_acceptance_basis",
          "consumer_impact_and_compatibility_analysis",
          "applicable_source_and_hash_updates",
          "affected_tables_vectors_goldens",
          "current_reference_docs_and_bindings",
          "candidate_validation_evidence"
        ],
        "failed_validation": "do_not_switch_pin",
        "unsafe_existing_pin": "suspend_affected_consumption",
        "rollback": "atomic_verified_PR"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-11", "CAP-15", "CAP-16", "CAP-20"],
      "rationale": "수용 근거와 소비자 변경을 하나의 검증 가능한 PR로 묶는다.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "dual_pin_handling": {
      "status": "ADOPTED",
      "value": {
        "active_pins_per_bound_surface_at_merge": 1,
        "standing_transition_window": false,
        "automatic_old_new_fallback": false,
        "inactive_comparison_evidence_allowed": true,
        "distinct_surface_pins_allowed": true,
        "staged_migration_requires": "separate_delegated_decision"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-15", "CAP-16"],
      "rationale": "활성 소비 표면의 구속 기준을 하나로 유지한다.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "claim_table_regeneration_rule": {
      "status": "ADOPTED",
      "value": {
        "every_claim_table_pin_move_regenerates_table_and_vectors_in_same_PR": true,
        "related_goldens_and_citation_checks_in_same_PR": true,
        "unchanged_output_requires_regeneration_evidence": true,
        "deferred_regeneration_allowed": false,
        "manual_regeneration_requires_claim_evidence_and_independent_expectations": true,
        "new_vectors_require_docs_surface_and_readme_registration": true
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-13", "CAP-14", "CAP-15"],
      "rationale": "핀 이동과 주장·벡터·기대 결과의 재생성을 분리하지 않는다.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "drift_fence_integration": {
      "status": "ADOPTED",
      "value": {
        "registration_file": "tests/decision_bindings.json",
        "registration_schema": "capital-decision-bindings-v1",
        "required_items": [
          "claim_table_regeneration_rule",
          "current_pin_assessment",
          "drift_fence_integration",
          "dual_pin_handling",
          "executable_pin_inventory",
          "pin_class_vocabulary",
          "repin_trigger_procedure",
          "research_baseline_rule"
        ],
        "initial_binding_status": "PENDING_CONSUMER",
        "consumer_node": "upstream-repin-policy-enforcement",
        "consumer_node_is_new_local_followup": true,
        "inventory_order": "sorted_unique_decision_id_entry",
        "checker": "scripts/decision_bindings.py",
        "decision_binding_check": "python3 -m unittest discover -s tests -p 'test_decision_bindings.py' -v",
        "additional_checks": [
          "python3 scripts/docs_surface.py --check",
          "python3 -m unittest discover -s tests -v"
        ],
        "merge_gate": "all_eight_valid_bindings_sorted_unique_inventory_and_zero_total_findings_on_combined_candidate",
        "checker_bypass_allowed": false,
        "future_repin_binding_updates_same_PR": true,
        "repin_adopts_no_seam": true,
        "revision_evidence": {
          "registrations_present": 8,
          "registrations_reordered": 8,
          "total_inventory_entries_checked": 98,
          "complete_inventory_equals_sorted_unique_identities": true,
          "json_roundtrip_verified": true,
          "all_registration_record_contents_preserved": true,
          "non_target_lines_unchanged": true,
          "pending_consumer_status_preserved": true,
          "policy_specific_automatic_enforcement_implemented": false,
          "full_checker_run": true,
          "final_candidate_verified": false
        }
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-15", "CAP-20"],
      "rationale": "정렬 위반을 수정하고 전체 목록의 정렬·유일성을 직접 확인하되 후보 전체 검증과 구분한다.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "current_pin_assessment": {
      "status": "ADOPTED",
      "value": {
        "vendor_pin_7481b0e": "HOLD",
        "ai_draft_pin_e2a029d": "HOLD",
        "reason": "no_specific_repin_trigger_evidence_in_supplied_pack",
        "next_review": "on_any_authorized_repin_trigger",
        "research_head_is_automatic_replacement": false,
        "historical_validation_is_current_head_evidence": false,
        "production": "NOT_AUTHORIZED"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-11", "CAP-15", "CAP-16"],
      "rationale": "현행 구속 범위는 명확하지만 이동을 정당화할 구체 근거가 없다.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

- 단일 결정 블록에 여덟 필수 항목의 상태·값·귀속·날짜·CAP 연결·잠정성을 명시했다.
- vendor `7481b0e`, AI 인용 `e2a029d`, 연구 기준을 분류하고 두 실행·참조 핀을 유지했다.
- claim-table 핀 이동 시 해당 표·벡터의 같은 PR 재생성을 예외 없이 요구했다.
- 앞선 개정의 여덟 등록 정렬을 유지하고 전체 98개 identity의 정렬·유일성과 checker findings 0을 재확인했다. pack fixture는 이 노트의 결정 요약을 포함하도록 정본 생성기로 갱신했다. 전체 수용 통과 여부는 §6의 검증 한계와 구분한다.

## 6. Open risks

- 정책별 자동 검증은 `PENDING_CONSUMER`다. 구현 전에는 리핀 리뷰 담당자가 영향 목록과 같은 PR 재생성 증거를 확인해야 한다.
- round 3 환경은 `socket.bind(('127.0.0.1', 0))`에 `PermissionError: [Errno 1] Operation not permitted`를 반환한다. HTTP·loopback 검증은 이 환경에서 통과했다고 주장하지 않는다. Chromium은 있지만 프로젝트의 Node Playwright test 의존성은 없고, `npm run test:browser`는 `unknown command 'test'`로 실패한다.
- `tests/test_coa_candidate.py::V1UnchangedTests.test_v1_and_golden_files_are_untouched`는 `docs/decisions/` 전체를 `origin/main`과 비교하여 이번에 명시적으로 허용된 노트도 거부한다. 같은 guard 경로에 대한 실제 diff는 `docs/decisions/CAPITAL_UPSTREAM_REPINS.md` 하나이며, guard 대상 Capital 코드·vendor·`.aiops/` 변경은 없다. 이 문서 변경은 V1 코드 회귀가 아니므로 guard 결과에 이 근거로 이의 제기한다. 테스트를 약화하거나 허용 범위 밖에서 수정하지 않는다.
- 제공된 CI acceptance의 unit 단계는 300초 timeout이었다. 오래된 pack의 대용량 assertion diff는 재생성으로 제거하지만 이 환경의 loopback·browser 제한과 위 guard 충돌 때문에 전체 acceptance 통과·CI 시간 내 완료를 주장하지 않는다. 정상 loopback·Node Playwright 환경과 guard 소유자의 확인이 필요하다.
- 이번 round의 실제 `python3 scripts/acceptance.py` 결과도 `ok=false`다. 최종 unit 실행은 730개 중 659개 통과·6 failures·65 errors이며, 남은 원인은 loopback 제한과 위 문서 guard다. pinned-vendor(7개)·upstream-claims(220개)·node-check·seeded-demo는 통과했고 browser·storage-conformance·packaged-smoke·integrated-journeys는 환경 제약으로 실패했다. 이 결과는 로컬 작업 트리 증거이며 exact-head CI 통과나 통합 수용이 아니다.
- 요청 지정 모델 귀속을 기록했으나 Claude CLI 실행이나 해당 모델의 검토 영수증을 주장하지 않는다.
- 회계·세무·법무 내용은 전문가 검토 전 작업 가정이다. DEV_ONLY shared-HMAC은 인증이 아니며 CAP-15 stage7 인증 export·external key·authentication은 계속 `NOT_BOUND`다.

## 7. 후속 작업

1. Supervisor는 이 노트·기존 binding 등록·재생성된 아홉 pack fixture를 같은 후보에 포함한다. §3.7 검사를 수행하고 §6의 guard 충돌과 실행 환경 제한을 해소한 뒤 CI 결과를 확인한다. 이번 unattended builder는 commit·push·게시·병합하지 않는다.
2. `upstream-repin-policy-enforcement`는 등록된 통합 지점에 정책별 검증을 구현한다. 실제 소비 증거가 생긴 항목만 `CONSUMED`로 바꾼다.
3. 현행 두 핀은 `HOLD`다. 향후 승인된 이동은 표·벡터·관련 골든·문서·binding을 같은 리핀 PR에서 갱신한다.
4. upstream 파일은 변경하지 않는다. 향후 구현도 기존 export 바이트 가드와 DEV_ONLY fixture의 mode 0600 임시 파일 로딩 규칙을 지킨다.
