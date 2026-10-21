# Capital 업스트림 리핀 정책 결정 — 실행·참조 핀과 연구 기준의 분리

> **PROVISIONAL PRODUCT DECISION — 잠정 제품 결정**
>
> 결정 귀속(요청 지정): **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**
>
> 결정일: **2026-10-21**  
> 기준: **KIX-CAPITAL main `02bc3e5` · kix-protocol `eef11da`** — supervisor 제공 기준이며 직접 HEAD를 확인한 결과가 아니다.  
> 결정 노드: `upstream-repin-policy-decision`  
> 선행: `upstream-binding-decision`, `audit90-fix2`

Capital 자체 참조의 **시뮬레이션·제품 설계용** 거버넌스다. 실자금은 없으며 production은 **`NOT_AUTHORIZED`**다. `ADOPTED`는 위임 범위 안의 로컬 잠정 정책 결정이며 upstream 계약 채택, seam 채택, `SEMANTIC_CONFORMANCE`, 구현 완료를 뜻하지 않는다. 이 결정으로 어느 핀도 이동하지 않는다.

위임 원문: “금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해.”

## 1. 결정 요약

| item | decision | CAP rows | consumer |
|---|---|---|---|
| `pin_class_vocabulary` | **ADOPTED:** vendor 바이트 구속, 인용 구속, 연구 출처의 세 클래스 | CAP-01, CAP-20 | 참조 목록·클레임 표·결정 노트 |
| `executable_pin_inventory` | **ADOPTED:** vendor `7481b0e`, AI 인용 `e2a029d`와 지정 소비 범위 유지 | CAP-11, CAP-15, CAP-16 | manifest·클레임 표 네 종 |
| `research_baseline_rule` | **ADOPTED:** 역사적 출처 보존; 실행 핀과 동일성 강제 금지 | CAP-01, CAP-20 | 노트의 `기준`·`bases` |
| `repin_trigger_procedure` | **ADOPTED:** 특정 변경의 수용 근거, 영향 분석, 원자적 PR과 검증 필요 | CAP-11, CAP-15, CAP-16, CAP-20 | 향후 리핀 구현·리뷰 |
| `dual_pin_handling` | **ADOPTED:** 활성 구속 표면당 하나의 핀; 일반 이중 핀 전환 창 없음 | CAP-15, CAP-16 | 실행·참조 소비 경로 |
| `claim_table_regeneration_rule` | **ADOPTED:** claim-table 핀 이동은 항상 해당 표·벡터를 같은 PR에서 재생성 | CAP-13, CAP-14, CAP-15 | 클레임 표·벡터·관련 골든 |
| `drift_fence_integration` | **ADOPTED:** 최초 등록은 실제 선행 변경으로 공급 가능; 노트 포함 후보에서 여덟 binding과 전체 findings 0 필수 | CAP-15, CAP-20 | decision-binding·문서·벡터 검사 |
| `current_pin_assessment` | **ADOPTED:** 두 현행 핀 모두 `HOLD`; 지금 리핀하지 않음 | CAP-11, CAP-15, CAP-16 | 현행 실행·참조 소비자 |

## 2. KIX 비전 연결

Capital이 더 넓은 금융 기능과 upstream 계약을 수용하려면, 변경의 출처와 소비자가 받아들이는 범위를 재현할 수 있어야 한다. 최신 SHA를 따라가는 것보다 계약·바이트·주장·검증 결과를 하나의 변경 단위로 유지하는 것이 이 결정의 목적이다.

- [CAPITAL_REQUIREMENTS_KO.md](../CAPITAL_REQUIREMENTS_KO.md)의 제공 발췌는 vendor 핀과 AI 위임 초안 인용 핀의 범위를 구분하고, 결정 노트의 연구 체크아웃을 그 범위 밖으로 둔다. 이를 분류의 기준으로 삼는다.
- [SEAMS.md](../SEAMS.md)는 실제 upstream 계약 대체와 영수증을 seam 채택 조건으로 둔다. 핀 이동과 로컬 벡터 통과는 이를 대체하지 않는다.
- [VALIDATION.md](../VALIDATION.md)는 로컬 검증의 범위와 과거 실행 결과를 제공한다. 그 결과를 이번 후보 헤드의 통과 증거로 재사용하지 않는다.
- [CAPITAL_ARTIFACT_BUNDLING.md](CAPITAL_ARTIFACT_BUNDLING.md)와 [CAPITAL_CLOSEOUT_ARTIFACT.md](CAPITAL_CLOSEOUT_ARTIFACT.md)의 발췌를 따라, 결정 출처와 결정론적 산출물을 추적하되 upstream 채택을 추정하지 않는다.
- [CAPITAL_CLAIM_SLICE_REGISTRY.md](CAPITAL_CLAIM_SLICE_REGISTRY.md), [CAPITAL_DEFAULT_RECOVERY.md](CAPITAL_DEFAULT_RECOVERY.md), [CAPITAL_ACCOUNTS_TAX_LEGAL.md](CAPITAL_ACCOUNTS_TAX_LEGAL.md)의 서로 다른 Protocol SHA는 역사적 연구 출처의 사례다.

이 문서는 제공된 팩과 리뷰만 사용했다. 허용 목록 밖의 선행 binding 노트 전문, 등록 JSON, checker 구현은 직접 읽지 않았다. 제공되지 않은 선행 정책을 새로 정하거나 덮어쓰지 않는다.

## 3. 항목별 결정

### 3.1 `pin_class_vocabulary`

**ADOPTED.** 분류는 SHA 문자열 자체보다 **소비 역할과 구속 표면**에 붙인다.

| 클래스 | 의미 | 변경 통제 |
|---|---|---|
| `EXECUTABLE_VENDOR` | 지정 commit의 vendor 파일 바이트, manifest 해시와 연결된 소비자를 구속 | 원본 commit 또는 잠긴 바이트 변경은 리핀 절차 |
| `EXECUTABLE_CITATION` | 지정 commit의 계약·문서·mock을 읽는 참조 소비자를 구속 | 인용 commit 변경은 리핀 절차 |
| `RESEARCH_BASELINE` | 결정 작성에 사용한 역사적 연구 스냅샷 | 출처 보존과 명시적 정정 절차 |

앞의 둘을 실행·참조 핀으로 묶는다. `EXECUTABLE_CITATION`은 mock의 vendor 편입, runtime 실행 또는 인증 채택을 뜻하지 않는다.

동일 SHA가 연구 출처와 실행 기준에 함께 등장해도 역할은 별개다. 새 소비자는 기존 SHA를 사용하더라도 대상 경로, 소비 범위, 검사와 binding을 명시해야 한다. 문자열 일치로 구속 범위가 자동 확장되지 않는다.

### 3.2 `executable_pin_inventory`

**ADOPTED.** 현재 실행·참조 목록은 다음 두 핀이다.

| 클래스 | 전체 SHA | 구속 범위 |
|---|---|---|
| `EXECUTABLE_VENDOR` | `7481b0e16ce9b903abbffa62249bb91cd9e63cfe` | F04·F01–F03 FSM reference 다섯 파일, vendor manifest SHA256, `tests/upstream_claims.json`·`tests/fsm_contract_claims.json`·`tests/read_model_claims.json`의 관련 인용 |
| `EXECUTABLE_CITATION` | `e2a029d8ac3af7575888dac22fc4bf173ebec232` | AI 위임 권한 계약 초안 0.1, `reference/ai_delegation/` mock의 읽기 전용 인용, `tests/agent_claims.json` |

AI mock은 vendor되지 않았으며 manifest 해시도 없다. 인용 핀 검사를 vendor 바이트 검증으로 표시하지 않는다.

팩의 Commerce `7c2452645c50b8ede17bdd762794adeabe42319e`는 확인 출처로 취급하며, 이 결정이 Commerce에 새 실행 구속을 만들지는 않는다. 이번 Capital `02bc3e5`와 Protocol `eef11da`도 연구 기준이다.

새 핀 등록에는 저장소, 전체 SHA, 대상 경로·계약 범위, 소비자, 검증 방법, 수용 근거가 필요하다. 현재 문서는 새 핀을 등록하지 않는다.

### 3.3 `research_baseline_rule`

**ADOPTED.** 결정 노트의 `기준`·`bases`는 역사적 출처로 보존한다. 리핀 때문에 과거 연구 SHA를 일괄 치환하거나 현행 실행 핀과 다르다는 이유로 실패 처리하지 않는다.

팩의 Protocol `51d8380`, `adcddc5`, `9eb6b9f`, `751c51b`, `244595d`는 이러한 출처다. 서로 다른 값이라는 사실만으로 실행 드리프트가 되지 않는다. 다만 일반적인 노트 스키마, binding, 번들 무결성 검사는 계속 적용한다.

새 노트는 실제 사용한 스냅샷과 출처를 기록한다. 직접 확인한 HEAD와 supervisor 제공 값을 구분한다. 잘못된 출처는 날짜·이유·대체 근거를 남겨 정정한다.

이번 개정은 요청된 기준에 따라 이전 원고의 `e2313ab`를 supervisor 제공 `eef11da`로 정정한다. 이는 이 문서의 출처 정정이며 두 실행·참조 핀의 이동이 아니다.

### 3.4 `repin_trigger_procedure`

**ADOPTED.** 리핀 검토는 다음 근거 중 하나로 개시한다.

1. 실제 upstream 채택 영수증을 특정 Capital 소비자에 적용할 필요.
2. 권한 있는 Capital 결정자의 정확성·보안 수정 수용 결정.
3. 특정 핀 이동을 지명한 소유자 지시 또는 위임 결정.

upstream main 전진, 최신화 목적, 연구 기준 갱신, cosmetic 변경만으로는 리핀하지 않는다. 결함 보고는 검토를 개시할 수 있지만 후보 SHA의 자동 수용을 뜻하지 않는다.

리핀 PR에는 old/new 전체 SHA, 트리거, 수용 결정자, 영향 표면, 호환성 분석과 다음 변경을 함께 넣는다.

- 새 원본 확인과, vendor가 대상이면 바이트·manifest commit·해시 갱신.
- 영향 클레임 표·벡터·관련 골든 재생성과 기대값 변경 근거.
- 현행 참조 문서, 인용 검사, 관련 decision-binding 갱신.
- 새 벡터 파일의 문서 표면 등록 및 README needle.
- 관련 검사, 전체 unittest, 문서 검사와 영향받는 acceptance 결과.

검증은 모든 변경이 결합된 후보 헤드를 대상으로 한다. 실패하면 전환하지 않는다. 이전 핀에 계속 의존할 수 없는 결함이면 해당 소비를 중단하고 검증되지 않은 후보로 자동 전환하지 않는다.

rollback도 핀·표·벡터·문서·binding을 함께 복원하는 검증된 PR이다. 변경 이력은 리핀 기록과 PR에 남기며 역사적 연구 출처는 보존한다.

### 3.5 `dual_pin_handling`

**ADOPTED.** 병합된 활성 구성에서는 구속 표면당 정확히 하나의 핀만 허용한다. 같은 표면의 old/new 자동 선택, 실패 시 fallback, 상시 이중 핀 전환 창은 허용하지 않는다.

PR에서 old/new 결과를 비교할 수는 있다. 이전 결과는 비활성 비교 증거로 표시하며 활성 소비 경로에서 제외한다. Git 이력과 비교 자료의 보존은 이중 핀 운영이 아니다.

vendor와 AI 인용처럼 별개 표면이 다른 핀을 쓰는 것은 허용한다. 단계적 이전이 필요하면 별도 위임 결정이 표면 경계, 선택 규칙, 종료 조건, 검증과 rollback을 먼저 정해야 한다. 이번 결정이 허용하는 일반 전환 기간은 **없음**이다.

### 3.6 `claim_table_regeneration_rule`

**ADOPTED. claim-table 핀 이동은 항상 해당 표와 벡터를 같은 PR에서 재생성한다.** 후속 PR로 미루지 않는다. 관련 골든과 인용 검사도 동일 변경 단위에 포함한다.

vendor 핀 이동은 세 FSM·읽기 모델 클레임 표를, AI 인용 핀 이동은 agent 표를 기본 영향 범위로 삼고 실제 의존 범위를 기록한다.

재생성 결과가 같은 바이트라면 인위적인 diff는 필요 없다. 대신 대상 파일, 재생성 절차와 동일 결과를 후보 헤드의 증거로 남긴다. 동일할 것이라는 추정으로 재생성을 생략하지 않는다.

생성기가 없는 표·벡터는 새 핀의 주장별 근거와 독립적인 기대 결과를 재구성하고 검토한다. SHA 치환이나 실행 결과에 맞춘 기대값 덮어쓰기는 재생성이 아니다.

핀을 유지한 채 표의 오류·커버리지를 수정할 수 있다. 이 경우에도 근거와 관련 벡터를 검증한다. 새 `tests/vectors/` 파일은 `scripts/docs_surface.py`의 수동 등록과 README needle을 같은 PR에 포함한다.

### 3.7 `drift_fence_integration`

**ADOPTED.** 기존 펜스의 책임을 유지한다.

| 펜스 | 책임 |
|---|---|
| vendor manifest·무결성 검사 | 원본 commit, vendor 바이트와 해시의 일치 |
| 클레임 인용·벡터 검사 | 핀, 주장과 기대 동작의 일치 |
| `scripts/manifest_vectors.py --check` | 해당 도구가 관리하는 manifest 벡터 |
| `scripts/docs_surface.py --check` | 등록된 문서 표면·산출물·README 연결 |
| decision-binding 검사와 등록 JSON | ADOPTED 항목의 실제 binding과 유효성 |
| seam 검사 | 실제 upstream 영수증 없는 seam 채택 방지 |

**리뷰 판정은 타당하다.** 제공된 리뷰에 따르면 `d4b8d20`에는 여덟 등록이 없으며, 설명문이나 `BLOCKED_MISSING_BINDINGS` 표기는 이를 해결하지 않는다.

이번 개정은 **최초 거버넌스 등록**과 **향후 핀 이동**의 전달 규칙을 분리한다.

- 이 노트의 여덟 최초 binding은 등록 파일을 다룰 수 있는 범위의 **실제 선행 변경**으로 공급할 수 있다. 노트 PR은 그 변경이 포함된 기반에 재배치하거나 허용된 결합 후보에 해당 커밋을 포함해야 한다.
- 선행 PR의 링크, 계획, 병합 예정만으로는 충족되지 않는다. **노트가 존재하는 최종 후보 트리**에 여덟 유효 등록이 실제로 있어야 한다.
- 향후 claim-table 핀 이동은 §3.6에 따라 표·벡터를 반드시 같은 리핀 PR에서 재생성한다. 그 이동에 필요한 binding·검사 변경도 같은 PR에 포함한다.
- 따라서 이번 docs-only 노트 PR은 이미 반영된 등록 선행 변경을 기반으로 유지할 수 있다. 이전 원고의 “최초 등록도 반드시 이 노트와 같은 PR의 diff에 있어야 한다”는 요구는 철회한다.

등록 대상은 §1의 여덟 item 전부다. 기존 스키마에 따라 실제 거버넌스 소비·검증 책임을 연결해야 한다. 단순 키 추가만으로 유효성을 주장하지 않는다. 등록 구조와 필요한 최소 checker 지원은 팩에 없어 **구체 구현은 UNDETERMINED**다.

노트 검색 제외, 무조건 통과 예외, 등록 회피용 `UNDETERMINED` 전환은 금지한다. 선행 변경만 따로 검사한 결과로도 충분하지 않다. 노트를 포함한 후보 헤드에서 다음 검사를 통과해야 한다.

`python3 -m unittest discover -s tests -p 'test_decision_bindings.py' -v`

여덟 누락뿐 아니라 **전체 binding findings가 0**이어야 한다. 전체 unittest와 `python3 scripts/docs_surface.py --check`도 통과하고 검증 헤드를 기록한다.

**이번 응답의 한계:** 허용된 산출물은 문서뿐이고 등록 파일 열람·수정은 범위 밖이다. 실제 선행 등록을 완료하거나 후보에 편입했다는 주장은 하지 않는다. 따라서 이 개정은 전달 규칙의 충돌을 해소하지만, 리뷰의 저장소 차단은 실제 등록과 검증 전까지 해소되지 않는다.

### 3.8 `current_pin_assessment`

**ADOPTED. 두 핀 모두 `HOLD`; 지금 리핀하지 않는다.**

- **vendor `7481b0e`: HOLD.** 요구사항이 다섯 reference 파일과 세 클레임 표의 기준으로 명시한다. 대체할 특정 수정 수용 결정이나 실제 채택 영수증이 팩에 없다.
- **AI 인용 `e2a029d`: HOLD.** 초안 0.1·mock 인용과 agent 표의 기준이다. 다른 계약·조항으로 이동할 근거가 제공되지 않았다.

연구 기준 `eef11da`는 어느 핀의 대체 후보로도 자동 승격하지 않는다. HOLD는 안전성 인증이나 영구 동결이 아니며 §3.4의 근거가 생기면 재평가한다.

CAP-11·CAP-15·CAP-16의 해당 미구속 범위는 계속 `NOT_BOUND`다. 핀 유지나 이동이 운영 권한을 확대하지 않는다.

## 4. 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "upstream-repin-policy-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-10-21",
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
      "date": "2026-10-21",
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
      "date": "2026-10-21",
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
      "date": "2026-10-21",
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
          "impact_and_compatibility_analysis",
          "applicable_source_and_hash_updates",
          "affected_tables_vectors_goldens",
          "current_reference_docs_and_bindings",
          "validation_evidence"
        ],
        "failed_validation": "do_not_switch_pin",
        "unsafe_existing_pin": "suspend_affected_consumption",
        "rollback": "atomic_verified_PR"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-21",
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
      "date": "2026-10-21",
      "cap_rows": ["CAP-15", "CAP-16"],
      "rationale": "활성 소비 표면의 구속 기준을 하나로 유지한다.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "claim_table_regeneration_rule": {
      "status": "ADOPTED",
      "value": {
        "every_claim_table_pin_move_regenerates_table_and_vectors_in_same_PR": true,
        "related_goldens_in_same_PR": true,
        "unchanged_output_requires_regeneration_evidence": true,
        "deferred_regeneration_allowed": false,
        "manual_regeneration_requires_claim_evidence_and_independent_expectations": true,
        "new_vectors_require_docs_surface_and_readme_registration": true
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-21",
      "cap_rows": ["CAP-13", "CAP-14", "CAP-15"],
      "rationale": "핀 이동과 주장·벡터·기대 결과의 재생성을 분리하지 않는다.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "drift_fence_integration": {
      "status": "ADOPTED",
      "value": {
        "initial_registration_delivery": "actual_prerequisite_changes_included_in_note_candidate_tree",
        "initial_registration_must_be_in_note_PR_diff": false,
        "prerequisite_reference_without_changes_is_sufficient": false,
        "required_items": [
          "pin_class_vocabulary",
          "executable_pin_inventory",
          "research_baseline_rule",
          "repin_trigger_procedure",
          "dual_pin_handling",
          "claim_table_regeneration_rule",
          "drift_fence_integration",
          "current_pin_assessment"
        ],
        "registration_schema": "existing_repository_schema",
        "registration_implementation": {
          "status": "UNDETERMINED",
          "value": null,
          "target": "eight_valid_bindings_without_bypassing_missing_binding_checks",
          "reason": "registration_schema_and_checker_implementation_not_in_allowed_pack"
        },
        "merge_gate": "all_eight_valid_bindings_and_zero_total_findings_on_candidate_containing_this_note",
        "decision_binding_check": "python3 -m unittest discover -s tests -p 'test_decision_bindings.py' -v",
        "additional_checks": [
          "python3 -m unittest discover -s tests -v",
          "python3 scripts/docs_surface.py --check"
        ],
        "checker_bypass_allowed": false,
        "future_repin_binding_updates_same_PR": true,
        "repin_adopts_no_seam": true,
        "delivery_evidence": {
          "registrations_completed_in_this_response": false,
          "candidate_integration_verified": false,
          "validation_run_in_this_response": false,
          "reported_review_blocker_resolved": false
        }
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-21",
      "cap_rows": ["CAP-15", "CAP-20"],
      "rationale": "최초 등록은 실제 선행 변경으로 공급하되 노트 포함 후보의 검증을 필수로 하고, 향후 리핀의 동일 PR 원칙은 유지한다.",
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
      "date": "2026-10-21",
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
- vendor `7481b0e`, AI 인용 `e2a029d`, 역사적 연구 기준을 분류했으며 어느 핀도 이동하지 않는다.
- claim-table 핀 이동 시 해당 표와 벡터를 항상 같은 PR에서 재생성한다.
- 최초 등록 선행 변경을 허용하여 docs-only 노트와 전달 규칙을 조정했다. 실제 등록·후보 편입·검증은 완료되지 않았으므로 **저장소 수용은 아직 미충족**이다.

## 6. Open risks

- 등록 스키마와 실제 consumer 지원은 팩에 없다. 구체 등록 레코드와 필요한 checker 변경은 미확정이다.
- 선행 binding 노트 전문, 생성기 커버리지, 후보 헤드 상태를 직접 확인하지 않았다.
- 요청 지정 모델 귀속은 보존했지만 Claude CLI 실행이나 해당 모델의 검토 영수증은 제공하지 않는다.
- 기존 회계·세무·법무의 전문가 검토 전 작업 가정, DEV_ONLY의 비인증 성격, 운영 제한은 유지한다.

## 7. 후속 작업

1. supervisor의 등록 작업 범위에서 기존 스키마를 확인하고 여덟 실제 binding을 공급하는 선행 변경을 완료한다. 필요한 checker 지원은 누락 검사를 유지한다.
2. 그 변경을 포함한 기반에 노트 후보를 구성한다. 노트 포함 헤드에서 decision-binding findings 0, 전체 unittest, `docs_surface.py --check`를 확인하고 헤드와 결과를 기록한다. 통과 전에는 병합하지 않는다.
3. 현행 두 핀은 `HOLD`로 유지한다. 향후 승인된 리핀은 표·벡터·관련 골든·문서·binding을 같은 PR에서 갱신한다.
4. 구현 작업은 기존 export 바이트 가드와 DEV_ONLY fixture의 mode 0600 임시 파일 로딩 규칙을 지킨다. upstream 파일은 변경하지 않는다.
