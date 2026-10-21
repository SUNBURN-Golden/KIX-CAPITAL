# Capital 업스트림 리핀 정책 결정 — 실행·참조 핀, 연구 기준과 원자적 갱신

> **PROVISIONAL PRODUCT DECISION — 잠정 제품 결정**
>
> 결정 귀속(요청 지정): **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**
>
> 결정일: **2026-10-21**  
> 기준: **KIX-CAPITAL main `02bc3e5` · kix-protocol `e2313ab`** — supervisor 제공 연구 스냅샷  
> 결정 노드: `upstream-repin-policy-decision`  
> 선행: `upstream-binding-decision`, `audit90-fix2`

Capital 자체 참조의 **시뮬레이션·제품 설계용** 거버넌스다. 실자금은 없으며 production은 **`NOT_AUTHORIZED`**다. 여기서 `ADOPTED`는 로컬 잠정 정책의 결정 상태이며 upstream 계약 채택, seam 채택, SEMANTICFORMANCE 또는 구현 완료를 뜻하지 않는다. 이 문서는 어느 핀도 이동하지 않는다.

위임 원문: “금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해.”

**리뷰 처리:** `d042b67`의 여덟 binding 누락 지적은 타당하다. “별도 선행 PR을 요구하는 문구만으로 해결된다”는 이전 처리를 철회한다. 필요한 등록 변경은 **이 노트와 같은 PR의 결합된 후보 헤드**에 포함해야 한다. 다만 이번 요청은 문서만 출력하도록 명시하고, 등록 파일·checker의 열람 및 모든 파일 쓰기를 허용하지 않는다. 따라서 이 응답으로 등록을 완료했다거나 차단을 해소했다고 주장할 수 없다. 이는 지적의 기술적 반박이 아니라 **요구된 저장소 수정과 허용된 산출물 사이의 범위 충돌**이다. 아래는 완결된 정책 결정이며, 저장소 수용 상태는 여전히 `BLOCKED_MISSING_BINDINGS`다.

## 1. 결정 요약

| item | decision | CAP rows | consumer |
|---|---|---|---|
| `pin_class_vocabulary` | **ADOPTED:** 바이트 구속·인용 구속·연구 출처의 세 클래스 | CAP-01, CAP-20 | 핀 목록, 클레임 표, 결정 노트 |
| `executable_pin_inventory` | **ADOPTED:** vendor `7481b0e`, AI 인용 `e2a029d` 유지 | CAP-11, CAP-15, CAP-16 | manifest, 클레임 표 네 종 |
| `research_baseline_rule` | **ADOPTED:** 역사적 출처 보존, 실행 핀과 동일성 강제 금지 | CAP-01, CAP-20 | 노트의 `기준`·`bases` |
| `repin_trigger_procedure` | **ADOPTED:** 명시적 수용 근거와 원자적 단일 PR | CAP-11, CAP-15, CAP-16, CAP-20 | 향후 리핀 구현·리뷰 |
| `dual_pin_handling` | **ADOPTED:** 활성 구속 표면당 하나의 핀, 상시 이중 핀 창 없음 | CAP-15, CAP-16 | 실행·참조 소비 경로 |
| `claim_table_regeneration_rule` | **ADOPTED:** 핀 이동 시 해당 표·벡터를 항상 같은 PR에서 재생성 | CAP-13, CAP-14, CAP-15 | 클레임 표, 벡터, 관련 골든 |
| `drift_fence_integration` | **ADOPTED:** 여덟 binding을 이 노트와 같은 PR에 등록하고 결합 헤드 검증 | CAP-15, CAP-20 | decision-binding, 문서·벡터·seam 검사 |
| `current_pin_assessment` | **ADOPTED:** 두 현행 핀 모두 `HOLD`; 지금 리핀하지 않음 | CAP-11, CAP-15, CAP-16 | 현행 실행·참조 소비자 |

## 2. KIX 비전 연결

Capital의 확장에는 upstream 계약을 수용할 수 있는 소비 경계와 재현 가능한 출처가 필요하다. 이 정책은 최신 SHA 자체를 목표로 삼지 않고, 어떤 변경을 어떤 소비자가 받아들였는지 검증 가능한 단위로 고정한다.

- [CAPITAL_REQUIREMENTS_KO.md](../CAPITAL_REQUIREMENTS_KO.md)의 제공 발췌는 vendor 바이트 핀과 AI 위임 초안 인용 핀의 구속 범위를 구분한다. 결정 노트의 연구 체크아웃은 두 핀의 범위 밖이다. 이 구분을 정책의 기준으로 삼는다.
- [SEAMS.md](../SEAMS.md)의 제공 발췌는 upstream 계약이 실제로 로컬 구현을 대체하고 영수증이 있어야 seam을 `ADOPTED`로 표시하도록 한다. 핀 변경이나 로컬 벡터 통과는 그 영수증을 대신하지 않는다.
- [VALIDATION.md](../VALIDATION.md)의 제공 발췌는 검증 명령과 과거 실행 결과의 선례다. 2026-10-20 결과를 이번 후보 헤드나 미래 리핀의 통과 증거로 전용하지 않는다.
- [CAPITAL_ARTIFACT_BUNDLING.md](CAPITAL_ARTIFACT_BUNDLING.md)와 [CAPITAL_CLOSEOUT_ARTIFACT.md](CAPITAL_CLOSEOUT_ARTIFACT.md)의 제공 발췌를 따라, 출처와 결정론적 산출물을 함께 추적하며 로컬 증거를 upstream 채택으로 승격하지 않는다.
- [CAPITAL_CLAIM_SLICE_REGISTRY.md](CAPITAL_CLAIM_SLICE_REGISTRY.md), [CAPITAL_DEFAULT_RECOVERY.md](CAPITAL_DEFAULT_RECOVERY.md), [CAPITAL_ACCOUNTS_TAX_LEGAL.md](CAPITAL_ACCOUNTS_TAX_LEGAL.md)에 기록된 서로 다른 연구 SHA는 역사적 출처의 사례다.

허용 목록 밖의 선행 binding 노트는 직접 읽지 않았다. 해당 정책은 제공된 요구사항의 인용 범위에서만 적용한다. 생략된 파일이나 잘린 발췌의 나머지, vendor 파일, 등록 파일, checker 구현은 열람하지 않았다. checker의 누락 판정은 제공된 리뷰를 근거로 한다.

## 3. 항목별 결정

### 3.1 `pin_class_vocabulary`

**ADOPTED.** 다음 세 클래스를 사용한다.

| 클래스 | 구속 대상 | 변경 규칙 |
|---|---|---|
| `EXECUTABLE_VENDOR` | 지정 upstream commit의 vendor 파일 바이트, per-file SHA256, 연결된 소비자 | 원본 commit이나 잠긴 바이트 변경은 리핀 절차 적용 |
| `EXECUTABLE_CITATION` | 지정 commit의 계약·문서·mock을 인용하는 참조 소비자 | 인용 commit 변경은 리핀 절차 적용 |
| `RESEARCH_BASELINE` | 결정 작성에 사용한 역사적 연구 스냅샷 | 출처 기록으로 보존; 실행 핀과 동기화하지 않음 |

앞의 둘을 “실행·참조 핀”으로 묶는다. `EXECUTABLE_CITATION`은 mock이 vendor되거나 운영에서 실행된다는 뜻이 아니다.

분류는 SHA 문자열보다 **소비 역할과 구속 표면**에 붙인다. 같은 SHA가 연구 출처와 실행 기준에 동시에 등장해도 역할은 별개다. 새 소비자가 기존 SHA를 사용하면 소비 범위·검사·binding을 명시적으로 등록한다. 단순 문자열 일치로 구속 범위가 자동 확장되지 않는다.

### 3.2 `executable_pin_inventory`

**ADOPTED.** 현재 목록은 두 실행·참조 핀으로 고정한다.

| 클래스 | 전체 SHA | 구속 범위 |
|---|---|---|
| `EXECUTABLE_VENDOR` | `7481b0e16ce9b903abbffa62249bb91cd9e63cfe` | F04·F01–F03 FSM reference 다섯 파일, vendor manifest SHA256, `tests/upstream_claims.json`, `tests/fsm_contract_claims.json`, `tests/read_model_claims.json`의 관련 인용 |
| `EXECUTABLE_CITATION` | `e2a029d8ac3af7575888dac22fc4bf173ebec232` | AI 위임 권한 계약 초안 0.1, `reference/ai_delegation/` mock의 읽기 전용 인용, `tests/agent_claims.json`의 agent lane |

AI mock은 vendor되지 않았으며 vendor manifest 해시도 없다. 따라서 인용 핀 검사를 vendor 바이트 무결성 검증으로 표시하지 않는다.

Commerce `7c2452645c50b8ede17bdd762794adeabe42319e`는 팩에 기록된 main 확인 출처이며, 이 결정에서는 `RESEARCH_BASELINE`으로 취급한다. Capital `02bc3e5`와 Protocol `e2313ab`도 이번 연구 기준이다.

새 핀은 저장소, 전체 SHA, 대상 경로·계약 범위, 소비자, 검증 방법, 수용 근거를 갖춰 등록한다. 이 결정은 새 핀을 만들지 않는다.

### 3.3 `research_baseline_rule`

**ADOPTED.** 결정 노트의 `기준`·`bases`는 역사적 출처로 보존한다. 리핀에 맞춰 과거 연구 SHA를 일괄 치환하지 않는다. 실행 핀과 연구 SHA가 다르다는 이유만으로 검사 실패를 만들지 않는다.

이는 노트의 스키마·등록·산출물 무결성 검사를 면제하지 않는다. 금지하는 것은 연구 출처에 **현행 실행 SHA와의 동일성**을 요구하는 것이다.

새 노트는 실제 사용한 스냅샷과 출처를 기록하며, 직접 확인한 HEAD와 supervisor 제공 값을 구분한다. 잘못된 출처는 날짜·이유·대체 근거가 있는 정정 기록 또는 후속 노트로 바로잡는다. 기존 기록을 조용히 최신 값으로 덮어쓰지 않는다.

팩에 등장하는 Protocol `51d8380`, `adcddc5`, `9eb6b9f`, `751c51b`, `244595d`는 이러한 출처다. 이 값들의 차이는 그 자체로 실행 핀 드리프트가 아니다.

### 3.4 `repin_trigger_procedure`

**ADOPTED.** 다음 중 하나가 리핀 검토의 근거가 된다.

1. 실제 upstream 채택 영수증을 특정 Capital 소비자에 적용할 필요.
2. 권한 있는 Capital 결정자의 정확성·보안 수정 수용 결정.
3. 특정 핀 이동을 지명한 소유자 지시 또는 위임 결정.

upstream main 전진, 최신화만을 위한 변경, 연구 기준 갱신, 의미 변화 없는 cosmetic diff는 독립적인 트리거가 아니다. 결함 보고는 수정 수용 검토를 개시할 수 있으나 자동 핀 이동을 승인하지 않는다.

리핀은 다음 내용을 **한 PR**에 포함한다.

1. old/new 전체 SHA, 트리거, 수용 결정자, 영향 표면과 호환성 분석.
2. 새 원본 확인, 해당 vendor 바이트와 manifest commit·해시의 동시 변경.
3. 영향 클레임 표·벡터·관련 골든의 재생성과 기대값 변경 근거.
4. 현행 핀 설명 문서, 인용 검사, 관련 decision-binding 갱신.
5. 새 벡터가 있으면 `docs_surface.py` 등록과 README needle 추가.
6. 관련 검사, 전체 unittest, 문서 검사 및 필요한 acceptance 재실행 결과.

검증과 리뷰는 결합된 후보 헤드를 대상으로 한다. 실패하면 전환하지 않는다. 병합 후 rollback도 핀·표·벡터·펜스를 함께 되돌리는 검증된 PR로 처리한다. 기존 핀을 계속 사용할 수 없는 결함이면 해당 소비를 중단하며 검증되지 않은 후보로 자동 전환하지 않는다.

old→new 이력은 리핀 결정 기록과 PR에 남긴다. 실행 핀 변경을 이유로 역사적 연구 출처를 다시 쓰지 않는다.

### 3.5 `dual_pin_handling`

**ADOPTED.** 병합된 활성 구성에서는 **구속 표면당 정확히 하나의 핀**만 허용한다. 같은 표면에서 old/new SHA를 상황에 따라 선택하는 상시 전환 창과 자동 fallback은 금지한다.

PR의 비교 검증에는 old/new 결과를 함께 둘 수 있다. 이전 결과는 비활성 비교 증거로 표시하고 활성 소비 경로에서 제외한다. Git 이력이나 비교 자료의 보존은 이중 핀 운영이 아니다.

vendor와 AI 인용처럼 별개의 표면이 서로 다른 핀을 사용하는 것은 허용한다. 단계적 이전이 필요하면 별도 위임 결정이 표면 경계, 선택 규칙, 종료 조건, 검증과 rollback을 먼저 정해야 한다. 이번 정책의 일반 전환 기간은 **없음**이다.

### 3.6 `claim_table_regeneration_rule`

**ADOPTED. claim-table 핀 이동은 항상 해당 표와 벡터를 같은 PR에서 재생성한다.** 재생성을 후속 PR로 미루지 않는다.

vendor 이동은 앞의 세 클레임 표를, AI 인용 이동은 agent 표를 기본 영향 범위로 검토하고 실제 의존 범위를 기록한다. 관련 골든도 같은 PR에서 갱신한다.

재생성 결과가 기존 바이트와 같으면 인위적인 diff는 필요 없다. 대신 재생성 절차, 대상 파일, 동일 결과를 후보 헤드의 증거로 남긴다. 동일할 것이라는 추정으로 실행을 생략할 수 없다.

자동 생성기가 없는 표·벡터는 새 핀의 주장별 근거와 독립적인 기대 결과를 재구성·검토한다. SHA 치환만 하거나 실제 출력에 맞춰 기대값을 무조건 덮어쓰는 것은 재생성이 아니다.

핀을 유지하면서 표의 오류나 커버리지를 수정할 수는 있다. 이때도 인용 근거와 관련 벡터를 검증한다. 새 벡터 파일의 문서 표면 등록은 같은 PR에서 완료한다.

### 3.7 `drift_fence_integration`

**ADOPTED.** 기존 펜스를 유지하고 각 검사가 보증하는 범위를 구분한다.

| 펜스 | 보증 대상 |
|---|---|
| vendor manifest 및 무결성 테스트 | 원본 commit·vendor 바이트·해시의 일치 |
| 클레임 인용 검사·벡터 테스트 | 인용 핀·주장·기대 동작의 일치 |
| `python3 scripts/manifest_vectors.py --check` | 해당 도구가 관리하는 manifest 벡터 |
| `python3 scripts/docs_surface.py --check` | 등록 문서 표면·산출물·README 연결 |
| `scripts/decision_bindings.py` 및 등록 JSON | ADOPTED 항목의 binding 누락·유효성 |
| `tests/test_seams.py` | upstream 영수증 없는 seam ADOPTED 금지 |

**이번 변경의 필수 구성은 이 노트와 `tests/decision_bindings.json`의 여덟 등록을 포함하는 단일 PR이다.** 별도 선행 PR을 적어 두는 것으로 등록을 대체하지 않는다. 등록 키는 §1의 여덟 item과 정확히 일치해야 하며 기존 스키마를 따른다.

각 binding이 연결해야 할 실제 소비·검증 책임은 다음과 같다. 이는 등록 JSON의 미확인 필드명을 새로 정의하는 표가 아니다.

| item | 연결할 책임 |
|---|---|
| `pin_class_vocabulary` | 세 클래스와 역할별 구속 범위를 유지하는 참조 정책 |
| `executable_pin_inventory` | 두 핀과 네 클레임 표의 범위 일치 |
| `research_baseline_rule` | 역사적 출처 보존과 실행 핀 동일성 강제 배제 |
| `repin_trigger_procedure` | 근거·변경 묶음·검증을 갖춘 리핀 리뷰 |
| `dual_pin_handling` | 활성 표면당 단일 핀과 fallback 금지 |
| `claim_table_regeneration_rule` | 같은 PR의 표·벡터 재생성 증거 |
| `drift_fence_integration` | 여덟 유효 binding과 기존 검사 유지 |
| `current_pin_assessment` | 두 현행 핀의 HOLD 유지 |

등록은 실제 로컬 거버넌스 소비 또는 검증 근거를 연결해야 한다. 존재하지 않는 consumer, upstream 영수증 또는 검사 통과를 만들어 넣지 않는다. 기존 스키마가 이를 표현하지 못한다면 필요한 최소 checker·테스트 지원도 같은 PR에 포함하며 누락 검사는 유지한다. 노트 검색 제외, 무조건 통과 예외, 등록 회피용 `UNDETERMINED` 전환은 금지한다.

결합된 후보에서 다음 검사를 실행한다.

`python3 -m unittest discover -s tests -p 'test_decision_bindings.py' -v`

여덟 누락뿐 아니라 전체 binding findings가 0이어야 한다. 이후 전체 unittest와 `docs_surface.py --check`를 통과시킨다. 관련 실행 결과는 검증 대상 헤드와 함께 기록한다.

**현재 증거:** 리뷰는 여덟 등록 부재를 보고했다. 이번 응답에는 등록 파일 변경이나 검사 실행이 없다. 따라서 차단은 미해소이며, 문서의 정책 채택과 저장소 검증 통과를 혼동하지 않는다.

### 3.8 `current_pin_assessment`

**ADOPTED. 두 핀 모두 `HOLD`; 지금 리핀하지 않는다.**

- **vendor `7481b0e`: HOLD.** 현행 요구사항이 다섯 reference 파일과 세 클레임 표의 기준으로 명시한다. 이를 대체할 특정 수정 수용 결정이나 실제 채택 영수증은 팩에 없다.
- **AI 인용 `e2a029d`: HOLD.** 초안 0.1·mock 인용과 agent 표의 기준이다. 새 계약·조항으로 이동할 근거가 제공되지 않았다. 연구 기준 `e2313ab`만으로 이동하지 않는다.

HOLD는 무기한 안전성 보증이 아니다. §3.4의 근거가 생기면 재평가한다. CAP-11·CAP-15·CAP-16의 해당 미구속 범위는 계속 `NOT_BOUND`이며, 핀 유지·이동 어느 쪽도 운영 권한을 확대하지 않는다.

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
      "rationale": "바이트 구속, 인용 구속, 역사적 출처를 분리한다.",
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
        "commerce_check": {
          "sha": "7c2452645c50b8ede17bdd762794adeabe42319e",
          "class": "RESEARCH_BASELINE"
        },
        "repin_performed": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-21",
      "cap_rows": ["CAP-11", "CAP-15", "CAP-16"],
      "rationale": "제공된 요구사항의 두 핀과 소비 범위를 유지한다.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "research_baseline_rule": {
      "status": "ADOPTED",
      "value": {
        "append_only_provenance": true,
        "must_equal_current_executable_pin": false,
        "repin_rewrites_historical_baselines": false,
        "new_notes_record": "actual_used_snapshot_and_source",
        "corrections": "dated_addendum_or_superseding_note",
        "ordinary_note_validation_exempt": false
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-21",
      "cap_rows": ["CAP-01", "CAP-20"],
      "rationale": "연구 출처를 보존하고 실행 핀과의 잘못된 동일성 요구를 막는다.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "repin_trigger_procedure": {
      "status": "ADOPTED",
      "value": {
        "triggers": ["applicable_upstream_adoption_receipt", "authorized_acceptance_of_correctness_or_security_fix", "explicit_owner_or_delegated_directive"],
        "non_triggers": ["upstream_main_advance", "freshness_only", "cosmetic_only", "research_baseline_refresh"],
        "atomic_pr_contents": ["old_new_sha_and_rationale", "source_and_hash_updates", "affected_tables_vectors_goldens", "current_reference_docs", "decision_bindings", "validation_evidence"],
        "history_location": "repin_decision_record_and_PR",
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
      "rationale": "활성 소비 경로의 구속 기준을 하나로 재현 가능하게 유지한다.",
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
        "fences": [
          "vendor_manifest_and_integrity_tests",
          "claim_pin_and_vector_tests",
          "python3 scripts/manifest_vectors.py --check",
          "python3 scripts/docs_surface.py --check",
          "scripts/decision_bindings.py",
          "tests/decision_bindings.json",
          "tests/test_seams.py"
        ],
        "registration_delivery": "same_PR_as_this_note",
        "registration_schema": "existing_repository_schema",
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
        "decision_binding_check": "python3 -m unittest discover -s tests -p 'test_decision_bindings.py' -v",
        "merge_gate": "all_eight_valid_bindings_and_zero_findings_on_combined_candidate_head",
        "separate_prerequisite_text_satisfies_registration": false,
        "checker_bypass_allowed": false,
        "future_repin_binding_updates_same_PR": true,
        "repin_adopts_no_seam": true,
        "delivery_evidence": {
          "registration_completed_in_this_response": false,
          "validation_run_in_this_response": false,
          "repository_acceptance": "BLOCKED_MISSING_BINDINGS"
        }
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-21",
      "cap_rows": ["CAP-15", "CAP-20"],
      "rationale": "別途 선행 PR 문구를 철회하고 실제 등록과 결합 헤드 검증을 같은 PR의 수용 조건으로 정한다.",
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
        "historical_validation_is_current_head_evidence": false,
        "production": "NOT_AUTHORIZED"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-21",
      "cap_rows": ["CAP-11", "CAP-15", "CAP-16"],
      "rationale": "현재 구속 범위는 명확하지만 이동을 정당화할 새 근거는 없다.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

- 단일 `capital-decision-v1` 블록에 여덟 항목, 상태, 값, 귀속, 날짜와 잠정성을 명시했다.
- vendor `7481b0e`, AI 인용 `e2a029d`, 역사적 연구 기준을 분류했으며 리핀하지 않는다.
- claim-table 핀 이동은 항상 같은 PR에서 해당 표·벡터를 재생성하도록 결정했다.
- 리뷰가 요구한 실제 등록과 결합 헤드 검증을 같은 PR의 필수 구성으로 바로잡았다.
- **저장소 수용은 미충족이다.** 문서만으로 등록 누락을 해결할 수 없으며, 제공된 차단 판정을 해소했다는 주장은 하지 않는다.

## 6. Open risks

- 등록 스키마와 실제 consumer 지원 범위는 팩에 없다. 구체적인 등록 레코드는 미확정이며 허위 형식을 제시하지 않는다.
- 클레임 인용 검사와 생성기의 전체 커버리지는 확인하지 않았다. 관련 구현은 검사 공백을 같은 PR에서 닫아야 한다.
- 선행 binding 노트 전문, 현재 파일 상태와 후보 헤드 검증 결과는 직접 확인하지 않았다.
- 요청 지정 모델 귀속은 보존했지만 이 응답은 Claude CLI 실행이나 해당 모델의 검토 영수증을 제공하지 않는다.
- CAP 연결은 잠정 정책 범위다. 회계·세무·법무의 기존 전문가 검토 전 작업 가정이나 운영 제한을 변경하지 않는다.

## 7. 후속 작업

1. supervisor가 이 노트와 여덟 실제 binding 등록을 **동일 PR**에 포함한 결합 후보를 구성한다. 필요한 checker 지원은 누락 검사를 유지하는 최소 변경으로 제한한다.
2. 결합 헤드에서 decision-binding 검사, 전체 unittest, `docs_surface.py --check`를 실행하고 헤드와 결과를 기록한다. 등록 또는 검증이 빠진 헤드는 병합하지 않는다.
3. 현행 두 핀은 `HOLD`를 유지한다. 향후 승인된 리핀은 표·벡터·문서·binding을 같은 PR에서 갱신한다.
4. 구현 시 기존 export 바이트 가드와 DEV_ONLY keyset fixture의 임시 파일 mode 0600 규칙을 유지한다. 이 정책 결정은 upstream 변경이나 운영 권한 확대를 승인하지 않는다.
