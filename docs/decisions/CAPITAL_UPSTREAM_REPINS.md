# Capital 업스트림 리핀 정책 결정 — 실행·참조 핀, 연구 기준, 원자적 갱신과 검증

**PROVISIONAL PRODUCT DECISION — 잠정 제품 결정**

| 항목 | 값 |
|---|---|
| 결정 노드 | `upstream-repin-policy-decision` |
| 결정 귀속(요청 지정) | **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)** |
| 결정일 | 2026-10-21 |
| 기준 | KIX-CAPITAL main `02bc3e5` · kix-protocol `e2313ab` — supervisor 제공 연구 스냅샷 |
| 선행 | `upstream-binding-decision`, `audit90-fix2` |
| 범위 | Capital 자체 참조의 시뮬레이션·제품 설계용 거버넌스. 실자금 없음. production `NOT_AUTHORIZED` |
| 산출물 | `docs/decisions/CAPITAL_UPSTREAM_REPINS.md` 전체 수정본. 이번 응답에서 파일 쓰기·검증 실행·리핀 없음 |

위임 원문: “금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해.”

여기서 `ADOPTED`는 위임 범위의 잠정 제품 정책을 결정했다는 뜻이다. upstream 계약 채택, seam의 `ADOPTED`, SEMANTIC_CONFORMANCE, 운영 승인을 뜻하지 않는다. upstream 파일·vendor 바이트·현행 핀은 변경하지 않는다.

**리뷰 차단 사항을 수용한다.** 기존 `scripts/decision_bindings.py` 펜스와 `tests/decision_bindings.json` 등록이 빠졌다. 여덟 항목의 등록을 **별도 선행 PR의 필수 작업**으로 결정하며, 등록과 검증이 완료되기 전 이 노트를 병합하지 않는다. 아래 절차는 등록 완료를 주장하지 않는다. 현재 전달된 리뷰 기준으로 여덟 등록은 미완료다.

## 1. 결정 요약

| item | 결정 | CAP rows | consumer |
|---|---|---|---|
| `pin_class_vocabulary` | **ADOPTED.** `EXECUTABLE_VENDOR`, `EXECUTABLE_CITATION`, `RESEARCH_BASELINE` 세 클래스 | CAP-01, CAP-20 | 핀 목록·클레임 표·결정 노트 |
| `executable_pin_inventory` | **ADOPTED.** vendor `7481b0e`, AI 인용 `e2a029d` 두 핀 유지 | CAP-11, CAP-15, CAP-16 | manifest·클레임 표 네 종 |
| `research_baseline_rule` | **ADOPTED.** 연구 기준은 역사적 출처. 전역 실행 핀과 동기화하지 않음 | CAP-01, CAP-20 | 결정 노트의 `기준`·`bases` |
| `repin_trigger_procedure` | **ADOPTED.** 근거 있는 트리거와 단일 원자 PR. main 전진만으로 리핀하지 않음 | CAP-11, CAP-15, CAP-16, CAP-20 | 향후 리핀 구현·리뷰 |
| `dual_pin_handling` | **ADOPTED.** 병합 시 구속 표면당 하나의 핀. 상시 이중 핀 전환 창 금지 | CAP-15, CAP-16 | 어댑터·참조 소비자 |
| `claim_table_regeneration_rule` | **ADOPTED.** claim-table 핀 이동은 항상 같은 PR에서 해당 표·벡터 재생성 | CAP-13, CAP-14, CAP-15 | 클레임 표·벡터·관련 골든 |
| `drift_fence_integration` | **ADOPTED.** 기존 decision-binding 검사 포함. 여덟 등록의 별도 선행 PR 완료가 이 노트 병합 조건 | CAP-15, CAP-20 | `decision_bindings.py`, 등록 JSON, 문서·벡터·seam 검사 |
| `current_pin_assessment` | **ADOPTED.** 두 핀 모두 `HOLD`. 새 실행 기준을 정당화할 증거가 팩에 없음 | CAP-11, CAP-15, CAP-16 | 현행 실행·참조 소비자 |

## 2. KIX 비전 연결

Capital의 확장 방향은 upstream 계약을 실제로 수용할 수 있는 구조와, 어느 기준으로 동작했는지 재현할 수 있는 증거를 함께 갖추는 것이다. 핀을 무조건 최신으로 옮기는 대신, 소비 범위와 전환 근거를 명시한다.

- [CAPITAL_REQUIREMENTS_KO.md](../CAPITAL_REQUIREMENTS_KO.md)의 제공 발췌는 vendor 바이트 핀과 AI 위임 초안 인용 핀을 구분한다. 노트별 연구 체크아웃은 출처 증명이며 두 핀의 구속 범위 밖이라고 명시한다. 이 구분을 분류·변경 절차로 고정한다.
- [SEAMS.md](../SEAMS.md)의 제공 발췌는 upstream 계약이 로컬 구현을 실제 대체하고 영수증이 있어야 seam을 `ADOPTED`로 표시한다고 정한다. 로컬 벡터 통과나 핀 변경만으로 계약 채택을 주장하지 않는다.
- [VALIDATION.md](../VALIDATION.md)의 제공 발췌는 2026-10-20의 로컬 검증 기록이다. 재현 가능한 검증의 선례로 사용하되, 그 결과를 이번 헤드나 향후 리핀의 통과 증거로 재사용하지 않는다.
- [CAPITAL_ARTIFACT_BUNDLING.md](CAPITAL_ARTIFACT_BUNDLING.md)와 [CAPITAL_CLOSEOUT_ARTIFACT.md](CAPITAL_CLOSEOUT_ARTIFACT.md)의 제공 발췌는 결정 노트·산출물의 바이트 출처와 비운영 라벨을 유지한다. 리핀도 원본·표·벡터·문서가 어떤 기준을 사용했는지 추적 가능해야 한다.
- [CAPITAL_CLAIM_SLICE_REGISTRY.md](CAPITAL_CLAIM_SLICE_REGISTRY.md), [CAPITAL_DEFAULT_RECOVERY.md](CAPITAL_DEFAULT_RECOVERY.md), [CAPITAL_ACCOUNTS_TAX_LEGAL.md](CAPITAL_ACCOUNTS_TAX_LEGAL.md)의 제공 발췌에 기록된 서로 다른 연구 SHA는 역사적 출처의 실례다. 이 차이는 실행 핀 드리프트가 아니다.

`CAPITAL_UPSTREAM_BINDING.md`는 선행 정책이지만 이번 허용 읽기 목록 밖이다. 직접 읽었다고 주장하지 않으며, 제공된 요구사항의 §3.9 인용과 구속 범위를 적용한다. 생략된 파일과 잘린 발췌의 나머지는 사용하지 않았다. decision-binding 펜스의 동작은 이번 리뷰가 제공한 정적 검사 결과를 근거로 한다.

## 3. 항목별 결정

### 3.1 `pin_class_vocabulary`

**ADOPTED.** 세 클래스를 사용한다.

| 클래스 | 구속 대상 | 변경의 의미 |
|---|---|---|
| `EXECUTABLE_VENDOR` | 지정 upstream commit에서 가져온 파일 바이트와 per-file SHA256, 관련 실행·테스트 소비자 | 원본 commit 또는 잠긴 바이트 변경은 리핀 절차 대상 |
| `EXECUTABLE_CITATION` | 지정 commit의 문서·mock을 읽기 전용으로 인용하는 참조 소비자 | 인용 commit 변경은 리핀 절차 대상 |
| `RESEARCH_BASELINE` | 결정 작성에 사용한 역사적 체크아웃의 출처 | 출처 기록이며 실행 기준 전환이 아님 |

앞의 두 클래스를 이 정책의 “실행·참조 핀”으로 묶는다. `EXECUTABLE_CITATION`이라는 이름은 해당 mock을 vendor하거나 운영에서 실행한다는 뜻이 아니다.

분류는 SHA 문자열 자체가 아니라 **그 SHA를 사용하는 역할과 구속 범위**에 붙인다. 같은 commit이 연구 출처와 실행 핀에 동시에 등장해도 각 역할은 별개다. 새 소비자가 기존 SHA를 인용한다는 이유만으로 자동으로 기존 핀 범위에 편입되지 않는다. 소비 범위 확대는 목록·바인딩·검증을 함께 갱신해야 한다.

### 3.2 `executable_pin_inventory`

**ADOPTED.** 제공된 현행 요구사항에서 확인되는 실행·참조 핀은 다음 둘이다.

| 클래스 | 전체 SHA | 구속 범위 |
|---|---|---|
| `EXECUTABLE_VENDOR` | `7481b0e16ce9b903abbffa62249bb91cd9e63cfe` | vendor된 F04·F01–F03 FSM reference 다섯 파일, manifest의 SHA256 잠금, `tests/upstream_claims.json`, `tests/fsm_contract_claims.json`, `tests/read_model_claims.json`의 해당 인용 |
| `EXECUTABLE_CITATION` | `e2a029d8ac3af7575888dac22fc4bf173ebec232` | AI 위임 권한 계약 초안 0.1과 `reference/ai_delegation/` mock의 읽기 전용 인용, `tests/agent_claims.json`의 agent lane |

AI mock은 vendor하지 않았고 vendor manifest 해시도 없다. 향후 인용 핀 검사를 보강해도 이를 vendor 바이트 검증과 같은 것으로 표시하지 않는다.

Commerce `7c2452645c50b8ede17bdd762794adeabe42319e`는 팩에서 “main 확인”으로 주어진 `RESEARCH_BASELINE`이다. 이 노트의 Capital `02bc3e5`와 Protocol `e2313ab` 역시 supervisor가 제공한 연구 기준이다.

새 핀을 추가하려면 대상 저장소·전체 SHA·파일 또는 계약 범위·소비자·검증 방법·결정 근거를 명시하고 등록한다. 이 결정은 새로운 핀을 추가하지 않는다.

### 3.3 `research_baseline_rule`

**ADOPTED.** `기준`·`bases`의 연구 기록은 추가전용 출처로 보존한다. 실행 핀을 옮겨도 과거 노트의 연구 SHA를 일괄 교체하지 않는다. 연구 기준과 실행 핀이 다르다는 이유로 테스트를 실패시키지 않는다.

이 규칙은 노트 자체의 스키마·등록·바이트 검사를 면제하지 않는다. 금지하는 것은 **연구 SHA와 현행 실행 SHA의 동일성을 요구하는 게이트**다.

새 노트는 실제 사용한 스냅샷과 출처를 기록한다. 직접 확인한 HEAD와 supervisor가 제공한 기준을 구분하며, 확인하지 않은 값을 “현재 최신 main”이라고 쓰지 않는다. 잘못된 출처는 기존 기록을 지우지 않고 날짜·이유·대체 출처가 있는 정정 기록이나 후속 노트로 바로잡는다.

Protocol `51d8380`, `adcddc5`, `9eb6b9f`, `751c51b`, `244595d` 등 제공된 선행 노트의 기준은 이러한 역사적 출처다. 서로 다른 값이라는 이유만으로 리핀 작업이 발생하지 않는다.

### 3.4 `repin_trigger_procedure`

**ADOPTED.** 리핀 검토를 시작할 수 있는 트리거는 다음 셋이다.

1. 실제 upstream 채택 영수증을 Capital의 특정 소비자에 적용해야 하는 경우.
2. 정확성·보안 수정의 수용을 권한 있는 Capital 결정자가 명시한 경우.
3. 소유자 지시 또는 위임된 결정이 특정 핀의 이동을 지명한 경우.

트리거는 검토 개시 조건이다. 그 자체로 변경·병합이나 운영 사용을 승인하지 않는다. main 전진, 최신화 욕구, 연구 기준 갱신, 표면의 의미 변화가 없는 cosmetic diff만으로는 리핀하지 않는다.

실제 리핀은 다음을 **한 PR에서 원자적으로** 처리한다.

1. old/new 전체 SHA, 트리거, 수용 결정자, 대상 표면, upstream 차이와 호환성 영향을 기록한다.
2. 새 원본과 소비 범위를 확인한다. vendor이면 대상 바이트와 manifest commit·SHA256을 함께 교체한다.
3. 영향받는 클레임 표·벡터·골든을 재생성한다. 기대 결과 변경에는 의미상 근거를 붙인다.
4. 현재 핀을 설명하는 문서, 인용 검사, `docs_surface.py` 등록·README needle, 영향받는 `tests/decision_bindings.json` 바인딩을 갱신한다. 과거 연구 기준은 보존한다.
5. 기존 decision-binding 검사와 관련 테스트를 실행하고, 전체 unittest·벡터·문서 검사를 통과시킨다. acceptance 입력이나 결과에 영향을 주면 acceptance도 다시 실행한다.
6. 후보 헤드에 대한 결과와 변경 근거를 남기고 통상 리뷰·병합 절차를 따른다.

old→new 이력은 리핀 노트와 PR에 기록한다. `scripts/decision_ledger.py`를 임의의 이력 저장소로 간주하거나 스크립트 소스에 사건을 추가하도록 요구하지 않는다. 기존 ledger가 읽는 형식과 실제 통합 방법은 구현자가 해당 범위에서 확인해야 한다.

실패하면 기존 핀을 유지한다. 병합 후 되돌림도 핀·표·벡터·펜스를 함께 되돌리는 검증된 PR로 수행한다. 문제가 있는 기존 핀을 유지할 수 없는 경우 관련 소비를 중단하며, 검증되지 않은 새 핀으로 자동 전환하지 않는다.

### 3.5 `dual_pin_handling`

**ADOPTED.** 병합된 활성 구성에는 구속 표면당 정확히 하나의 실행·참조 핀만 둔다. 같은 표면에서 두 SHA 중 상황에 따라 선택하는 전환 창과 자동 fallback은 허용하지 않는다.

리핀 PR 안에서는 비교를 위해 old/new 결과를 함께 제시할 수 있다. 이전 결과는 비교 증거로 명시하고 활성 소비 경로에서 제외한다. 과거 Git 이력과 비활성 증거의 보존은 이중 핀이 아니다.

vendor와 AI 인용처럼 서로 다른 표면이 서로 다른 핀을 사용하는 것은 허용한다. 단계적 이전이 필요하면 별도 위임 결정에서 표면 분리, 선택 규칙, 종료 조건, 검증·되돌림 방식을 먼저 정해야 한다. 이번 결정이 허용하는 상시 전환 기간은 **없음**이다.

### 3.6 `claim_table_regeneration_rule`

**ADOPTED. claim-table 핀 이동은 항상 해당 표와 벡터를 같은 PR에서 재생성한다.** 별도 후속 PR로 재생성을 미루지 않는다.

적용 대상은 네 클레임 표 중 인용 핀이 바뀌는 표와 그 표에 연결된 벡터·관련 골든이다. vendor 핀 이동은 앞의 세 표를, AI 핀 이동은 agent 표를 기본 영향 범위로 검토한다. 실제 의존 범위를 PR에 명시한다.

재생성 결과가 이전과 바이트 단위로 같을 수 있다. 이 경우 불필요한 변경을 만들지 않고, 실행한 재생성 절차·대상 파일·동일 결과를 후보 헤드의 증거로 남긴다. “바이트가 같을 것”이라는 추정으로 실행을 생략하지 않는다.

자동 생성기가 없는 표·벡터는 새 핀에 대한 주장별 근거와 독립적인 기대 결과를 다시 구성·검토한다. SHA 문자열만 치환하는 것은 재생성이 아니다. 관측된 출력에 맞춰 기대값을 무조건 덮어쓰는 것도 허용하지 않는다.

핀을 유지한 채 표의 오류나 커버리지를 수정하는 작업은 가능하다. 이 경우 인용 근거와 관련 벡터를 함께 검증한다. 금지하는 것은 핀 이동과 그에 따른 표·벡터 갱신을 분리하는 것이다. 새 벡터 파일은 제공된 저장소 지침대로 `docs_surface.py` 항목과 README needle도 같은 PR에 포함한다.

### 3.7 `drift_fence_integration`

**ADOPTED.** 다음 펜스는 서로 다른 사실을 검증하며 대체 관계가 아니다.

| 펜스 | 검증 대상 |
|---|---|
| vendor manifest 및 관련 테스트 | 지정 원본·commit·vendored 바이트·SHA256의 일치 |
| 클레임 인용 검사와 관련 벡터 테스트 | 핀, 주장, 기대 동작의 일치 |
| `python3 scripts/manifest_vectors.py --check` | 이 도구가 관리하는 결정론적 manifest 벡터 |
| `python3 scripts/docs_surface.py --check` | 등록된 문서 표면·산출물·README 연결 |
| `scripts/decision_bindings.py`와 `tests/decision_bindings.json` | 결정 노트의 ADOPTED 항목에 대한 기존 바인딩 등록과 유효성 |
| `tests/test_seams.py` | upstream 영수증 없는 seam `ADOPTED` 금지 |

manifest 벡터 검사가 모든 claim-table 인용을 검사한다고 가정하지 않는다. 제공 팩에 없는 세부 검사 범위는 미확인이다. 리핀 구현자는 관련 표면의 검사 공백을 같은 PR에서 닫아야 한다.

**이번 노트의 필수 선행 작업:** 별도 Capital PR에서 `tests/decision_bindings.json`에 이 `decision_id`의 여덟 항목을 기존 스키마와 checker 규칙대로 모두 등록한다. 대상은 §1의 여덟 item과 정확히 같아야 한다. 로컬 거버넌스 소비·검증 근거를 연결하며 upstream 채택 영수증을 만들어 넣지 않는다.

등록 스키마와 정확한 consumer 필드는 허용 팩에 없어 **UNDETERMINED — 이번 문서에서 추측하지 않음**이다. 등록 담당은 별도 구현 노드다. 이 문서는 JSON 레코드 모양이나 지원 여부가 확인되지 않은 예외 유형을 신설하지 않는다.

선행 PR은 기존 checker의 누락·유효성 검사를 유지해야 한다. 이 노트를 검색 대상에서 제외하거나, 허위 바인딩을 넣거나, 정책상 결정된 여덟 항목을 등록 회피 목적으로 `UNDETERMINED`로 바꾸지 않는다. 사전 등록이 기존 규칙에 맞지 않으면 정상 검증을 유지하는 선행 구현으로 해결해야 하며, 해결 전에는 이 노트 병합 조건이 충족되지 않는다.

**실제 decision-binding 검증 명령**은 다음과 같다.

`python3 -m unittest discover -s tests -p 'test_decision_bindings.py' -v`

리뷰에 따르면 이 테스트는 `scripts/decision_bindings.py` 검사가 zero findings일 것을 요구한다. 등록만 있는 선행 헤드의 통과로 끝내지 않고, **선행 변경과 이 노트가 함께 있는 최종 후보 트리에서** 재실행해야 한다. 그 결과와 선행 PR 병합 commit을 이 노트 PR에 남긴다. 이후 전체 unittest와 `docs_surface.py --check`도 통과해야 한다.

이 문서만 추가한 상태에서는 리뷰가 지적한 여덟 미등록 오류가 해소되지 않는다. 현재 등록 영수증은 없으며 병합 조건은 미충족이다. 향후 실제 리핀에서는 관련 바인딩 갱신을 리핀 PR 안에서 처리한다. 이번 별도 선행 PR은 문서 전용 결정 노드의 등록을 위한 것이며 일반적인 원자 갱신 규칙의 예외로 확장하지 않는다.

### 3.8 `current_pin_assessment`

**ADOPTED. 두 핀 모두 `HOLD`: 지금 리핀하지 않는다.**

- **vendor `7481b0e`: HOLD.** 제공된 요구사항이 FSM 원본·vendor 바이트와 세 클레임 표의 기준으로 명시한다. 팩에는 이 기준을 대체할 특정 수정 수용 결정이나 upstream 채택 영수증이 없다. 2026-10-20의 검증 기록은 과거 로컬 결과이며 이번 `02bc3e5`의 재검증을 뜻하지 않는다.
- **AI 인용 `e2a029d`: HOLD.** 범위는 초안 0.1과 mock의 읽기 전용 인용 및 agent 표다. 새 계약·새 조항으로 이동해야 할 근거가 팩에 없다. `e2313ab`라는 더 나중의 연구 기준만으로 이동하지 않는다.

HOLD는 무기한 안전성 보증이 아니다. §3.4 트리거가 발생하면 재평가한다. 신뢰할 수 있는 결함 보고도 수정 수용 여부를 검토할 이유가 된다. 실제 채택이나 운영 권한은 별도 증거가 필요하며 CAP-11·CAP-15·CAP-16의 해당 미구속 범위는 계속 `NOT_BOUND`다.

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
      "rationale": "바이트 구속, 인용 구속, 연구 출처를 구분한다.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "executable_pin_inventory": {
      "status": "ADOPTED",
      "value": {
        "vendor_pin": {
          "sha": "7481b0e16ce9b903abbffa62249bb91cd9e63cfe",
          "class": "EXECUTABLE_VENDOR",
          "manifest": "capital/vendor/manifest.json",
          "file_count": 5,
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
      "rationale": "제공된 요구사항의 두 실행·참조 핀과 소비 범위를 유지한다.",
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
      "rationale": "연구 출처를 보존하면서 실행 핀과의 허위 동일성 요구를 막는다.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "repin_trigger_procedure": {
      "status": "ADOPTED",
      "value": {
        "triggers": ["applicable_upstream_adoption_receipt", "authorized_acceptance_of_correctness_or_security_fix", "explicit_owner_or_delegated_directive"],
        "non_triggers": ["upstream_main_advance", "freshness_only", "cosmetic_only", "research_baseline_refresh"],
        "atomic_pr_contents": ["old_new_sha_and_rationale", "source_and_hash_updates", "affected_tables_vectors_goldens", "current_reference_docs", "decision_bindings", "validation_evidence"],
        "history_location": "repin_note_and_PR",
        "failed_validation": "do_not_switch_pin",
        "rollback": "atomic_verified_PR"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-21",
      "cap_rows": ["CAP-11", "CAP-15", "CAP-16", "CAP-20"],
      "rationale": "근거 있는 전환만 허용하고 핀과 소비자 변경을 원자적으로 검증한다.",
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
      "rationale": "병합된 소비 경로의 구속 기준을 하나로 재현 가능하게 유지한다.",
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
        "unchanged_pin_table_corrections_allowed_with_validation": true,
        "new_vectors_require_docs_surface_and_readme_registration": true
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-21",
      "cap_rows": ["CAP-13", "CAP-14", "CAP-15"],
      "rationale": "핀移動과 주장·기대 결과의 갱신을 분리하지 않는다.",
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
        "decision_binding_check": "python3 -m unittest discover -s tests -p 'test_decision_bindings.py' -v",
        "this_note_prerequisite": {
          "delivery": "separate_prerequisite_PR",
          "registry": "tests/decision_bindings.json",
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
          "use_existing_binding_schema": true,
          "registration_receipt": null,
          "completion_claimed": false
        },
        "merge_gate": "prerequisite_merged_and_final_combined_candidate_has_zero_binding_findings",
        "checker_bypass_allowed": false,
        "future_repin_binding_updates_same_PR": true,
        "repin_adopts_no_seam": true
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-21",
      "cap_rows": ["CAP-15", "CAP-20"],
      "rationale": "レビューで判明した八項目の未登録を必須の先行作業と最終候補検証で解消する。",
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
      "rationale": "현행 두 핀의 범위는 명확하지만 이동을 정당화할 새 근거는 제공되지 않았다.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

- 단일 `capital-decision-v1` 블록에 여덟 필수 항목과 각각의 `ADOPTED` 상태를 명시했다.
- vendor `7481b0e`, AI 인용 `e2a029d`, 연구 기준을 분류했으며 어느 핀도 변경하지 않는다.
- claim-table 핀 이동 시 항상 같은 PR에서 해당 표·벡터를 재생성하도록 결정했다.
- 리뷰의 누락된 decision-binding 펜스, 등록 대상 여덟 항목, 범위가 분리된 선행 PR, 실제 검사 명령과 최종 후보 검증을 명시했다.
- **저장소 병합 수용은 아직 미충족이다.** 등록 PR과 통과 영수증은 제공되지 않았다. 문서 수정만으로 여덟 오류가 사라졌다고 주장하지 않는다.

## 6. Open risks

- 인용 SHA 검사와 벡터 생성기의 실제 커버리지는 팩만으로 확정할 수 없다. 향후 구현에서 공백을 확인하고 변경과 함께 닫아야 한다.
- decision-binding 등록 스키마와 사전 등록의 허용 여부는 미확인이다. 선행 작업은 기존 검사를 유지한 상태에서 이를 해결해야 한다.
- 선행 binding 노트의 전체 내용과 현재 HEAD 검증 결과는 직접 확인하지 않았다. 제공 발췌 밖의 계약·영수증·통과 결과를 추론하지 않는다.
- CAP 매핑은 제공 노트와 이번 노드 범위에 따른 잠정 연결이다. 금융·법무·세무 정책이나 운영 권한을 확대하지 않는다.

## 7. 후속 작업

1. 별도 구현 노드가 여덟 decision-binding 등록을 선행 PR로 완료한다. checker 우회나 허위 영수증을 허용하지 않는다.
2. supervisor가 선행 변경과 이 문서가 결합된 후보에서 decision-binding 검사, 전체 unittest, `docs_surface.py --check`를 실행하고 결과를 PR에 기록한다. 이 응답에서는 실행하지 않았다.
3. 실제 리핀 트리거가 생기면 영향 표·벡터·문서·바인딩을 같은 PR에서 갱신한다. export 바이트 가드와 DEV_ONLY fixture의 임시 파일 0600 규칙 등 기존 검증 제약을 유지한다.
4. 등록과 검증이 완료될 때까지 이 노트는 병합하지 않는다. 두 현행 핀은 계속 `HOLD`다.
