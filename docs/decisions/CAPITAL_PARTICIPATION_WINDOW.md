# Capital 참여 재생·보정창 결정 — bounded multi-claim participation

**PROVISIONAL PRODUCT DECISION — 잠정 Capital 제품 결정**

- 지정 결정자: **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)**
- 결정일: **2026-11-01**
- 기준: KIX-CAPITAL main **`c4114c7`**, kix-protocol **`fd33335`** — supervisor 제공 기준이며 HEAD를 별도 확인하지 않았다.
- 결정 ID: `participation-window-decision`
- 선행: `shadow-participation-slice-uc`, `claim-slice-registry`, `sim-clock-ledger`
- 예정 소비자: `participation-window-replay` — **PENDING_IMPLEMENTATION**

시뮬레이션·제품 설계만을 위한 결정이다. 실자금은 없으며 production은 **`NOT_AUTHORIZED`**다. 개별 항목의 `ADOPTED`는 잠정 제품 선택이며 upstream 채택이나 구현 완료가 아니다. 문서 전체 상태는 `PROVISIONAL_PRODUCT_DECISION`이다. 청약 라벨 `SIMULATION_ONLY_NOT_OFFERED_V1`과 제3자 투자·토큰화 슬라이스의 `NOT_ADOPTED` 상태를 유지한다.

작성 provenance: 이 문서는 Codex가 작성했다. 위 모델명과 아래 `decided_by`·`provided_by`는 supervisor가 요구한 지정 귀속 문자열이다. Claude CLI 실행, Sonnet 심의, 세 번의 실패 또는 Fable 인계가 실제 발생했다는 증거는 없으며 이를 주장하지 않는다.

`CAPITAL_SHADOW_POLICY.md`는 허용된 읽기 경로 밖이다. 이 문서는 supervisor가 명시한 deferred participation 범위만 확장한다. 기존 참여율·참여 한도·기간 조건의 숫자와 정확한 필드 경로는 **UNDETERMINED**이며, 기존 값을 보존하는 정책 자체는 **ADOPTED**다. 해당 원문을 확인한 소비자가 출처를 고정하기 전에는 계산을 활성화하지 않는다.

## 1. 결정 요약

아래 CAP 연결은 추적 대상이며 현재 구현 완료나 상위 바인딩을 뜻하지 않는다. `replay`는 예정 노드 `participation-window-replay`다.

| item | 결정 | CAP rows | consumer |
|---|---|---|---|
| `event_claim_membership` | 단일 참여계약·단일 수익자, 고정 claim 집합, 합성 분류액과 명시적 사건만 사용 | CAP-01, CAP-08 | replay |
| `statement_anchor_and_day_order` | 불변 명세서 tuple, 명시적 anchor, `(sim_day, sequence)` 순서 | CAP-01, CAP-15 | replay |
| `advance_slice_priority_inputs` | 제외액 분리 → 홀더 우선 → 잔여의 선지급 상계 → 참여 | CAP-04, CAP-08 | replay |
| `adjustment_window_boundary` | `anchor_day ≤ adjustment_day ≤ anchor_day + 90`, 마지막 날 포함 | CAP-01, CAP-05 | replay |
| `cap_clawback_and_term_end` | 누적 양의 참여 배정으로 한도 소비; 환수해도 한도 복원 없음 | CAP-01, CAP-04 | replay |
| `rounding_carry_and_duplicates` | 명세서 내부 정수 누적·나머지 이월, 동일 사건 중복 무효과 | CAP-08, CAP-15 | replay |
| `disposable_replay_bounds` | 32 claims·16 statements·256 events의 일회성 메모리 북 | CAP-08, CAP-13 | replay |
| `provenance_and_output_labels` | 출처·결정·입력 digest, pending 소비자, 합성·비실행 표기 | CAP-09, CAP-20 | replay / 결정 등록 |

## 2. KIX 비전 연결

[CAPITAL_CLAIM_SLICE_REGISTRY.md](CAPITAL_CLAIM_SLICE_REGISTRY.md)의 제공 발췌와 supervisor의 홀더 우선 요구를 따라 동일 잔여액의 이중사용을 금지한다. 여러 claim의 금융 근거를 재현 가능한 북으로 연결하되 복수 payee 배정이나 결제 권위로 확장하지 않는 것이 이 결정의 KIX 비전 해석이다.

[SEAMS.md](../SEAMS.md)와 [CAPITAL_REQUIREMENTS_KO.md](../CAPITAL_REQUIREMENTS_KO.md)의 제공 발췌에 따라 로컬 재생은 상위 계약 채택이나 SEMANTIC_CONFORMANCE가 아니다. [CAPITAL_ACCOUNTS_TAX_LEGAL.md](CAPITAL_ACCOUNTS_TAX_LEGAL.md)의 회계·법률 검토 경계도 유지한다. 인용은 제공 발췌에 한정하며 링크된 추가 원문은 열지 않았다.

## 3. 항목별 결정

### 3.1 `event_claim_membership`

북 manifest는 `book_id`, `agreement_id`, 단일 `beneficiary_id`, 참여 조건 출처, 고정 claim 목록, 시작일 `S`, 종료일 `T`, 관측일 `as_of_day`를 가진다. 금액은 이미 분류된 합성 KRW 정수다. 외부 매출·결제·환불 사실을 조회하거나 새로 분류하지 않는다.

각 claim은 북에서 하나의 명세서에만 속하고 하나의 `ORIGINAL` 사건을 가진다. 동일 원천 금액의 중복 투입을 막기 위해 `source_amount_id`도 북 전체에서 유일해야 한다. 각 claim의 단일 수익자는 manifest 수익자와 일치해야 한다.

사건 종류는 `ORIGINAL`과 `ADJUSTMENT`뿐이다. 보정은 원 사건 ID와 동일 claim·명세서를 참조하고, 기존 분류를 유지한 **대체 금액**을 제출한다. delta는 재생기가 계산한다. 음수 금액, 원 사건 없는 보정, 분류 변경, 미등록 claim, 중복 원천 또는 소급 멤버 추가는 북 전체를 거절한다.

보호 줄·플랫폼 수수료·환불 준비금은 별도 제외액이다. 이 금액을 참여 가능 잔여로 전환하는 사건은 지원하지 않는다.

### 3.2 `statement_anchor_and_day_order`

명세서 정체성은 `(book_id, agreement_id, anchor_day)` tuple이다. 같은 계약·anchor의 claims는 하나의 명세서에 모인다. `anchor_day`는 manifest의 명시적 `sim_day`이며 최초 실행 시각이나 마지막 보정일로 정하지 않는다.

원 사건은 자기 명세서의 anchor 당일에만 발생할 수 있고 `S ≤ anchor_day ≤ T`여야 한다. 원 사건 추가·보정·재실행은 명세서 ID를 바꾸거나 보정창을 재시작하지 않는다. 내용 변경은 별도 `revision_digest`로 식별한다.

정렬키는 `(sim_day, sequence)`다. `sequence`는 당일 유일한 비음수 정수이며 입력 배열 위치를 사용하지 않는다. 원 사건은 참조 보정보다 먼저 와야 한다. 같은 날 원 사건 → 보정 순서를 입력 sequence로 명시하며, 충돌·누락은 거절한다.

각 사건의 산술과 한도 상태를 순서대로 반영한 뒤 그날 종료 시 창·기간 상태를 갱신한다. 한도 도달 후 같은 날 발생한 환수도 한도를 재개방하지 않는다. 벽시계와 영업일 달력은 사용하지 않는다.

### 3.3 `advance_slice_priority_inputs`

각 claim에는 서로 겹치지 않는 원천 범위, 합성 홀더 우선 청구액 `H_due`, 잔여에만 적용 가능한 선지급 상계액 `A_due`를 고정한다. 같은 선지급의 claim별 상계 예산 합은 그 선지급의 입력 잔액을 넘을 수 없다. 우선순위·담보 범위가 불명확하거나 중복되면 `PRIORITY_INPUT_CONFLICT`로 거절한다.

보호·수수료·준비금을 제외한 분류액을 `Q`라 할 때:

- 홀더 몫 `H = min(Q, H_due)`
- 선지급 상계 `A = min(Q − H, A_due)`
- 참여 기초 `N = Q − H − A`
- 참여 배정 `E`와 수익자 잔여 `R`는 `N = E + R`

홀더 몫은 합성 내부 역할이며 제3자 투자를 채택하지 않는다. 상계·홀더 지급으로 사용한 금액을 참여 기초에 다시 넣지 않는다. 보정은 원 사건의 고정 우선권 입력으로 분해를 다시 계산하고 이전 결과와의 차이를 표시한다. 미상계·미충족 잔액은 진단으로 남기며 다른 claim으로 자동 이동하지 않는다.

다음 숫자는 산술 전용 합성 단위다. 이 예시와 아래 경계·한도·나머지 예시는 모두 `UNSUPPORTED_BY_PINNED_FSM`인 로컬 제품 산술이며 vendor FSM 실행·대사 결과가 아니다. 참여 배정은 명세서 합계에서만 계산하며 claim별 참여자 배분을 만들지 않는다.

| claim | 총 분류액 | 보호 | 수수료 | 준비금 | Q | H | A | N |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| c1 | 1,000 | 100 | 50 | 50 | 800 | 200 | 300 | 300 |
| c2 | 600 | 50 | 20 | 30 | 500 | 100 | 100 | 300 |
| 합계 | 1,600 | 150 | 70 | 80 | 1,300 | 300 | 400 | 600 |

참여율을 설명용 `r_demo = 1,000 bps`로 놓고 한도가 충분하면 참여 60, 잔여 540이다. **300 제외액 + 300 홀더 + 400 상계 + 60 참여 + 540 잔여 = 1,600**이다. 이 10%는 기존 참여율의 주장이나 변경이 아니다.

### 3.4 `adjustment_window_boundary`

보정 가능 조건은 정확히 **`0 ≤ adjustment_day − anchor_day ≤ 90`**이다. anchor 당일과 그 뒤 90개 논리 일의 보정을 허용한다. 날짜값으로는 91개가 포함되며, `anchor + 90`일 종료 후 닫힌다. `anchor + 91`부터 결과는 `OUTSIDE_WINDOW`다.

창 밖 사건은 입력 digest와 진단에 포함하지만 기존 명세서 금액·나머지·한도를 변경하지 않는다. 재명세서화나 새 사건 ID로 창을 우회할 수 없다.

위 예시의 anchor가 10일이고 c1의 `Q`만 800에서 700으로 감소한다고 하자. 고정 `H_due=200`, `A_due=300`이므로 c1의 `N`은 200, 전체 `N`은 500이 된다. 참여율은 동일한 설명용 10%다. 다음 세 행은 **각각 독립된 재생**이다.

| 보정일 | 경과일 | 결과 | 참여 / 잔여 |
|---|---:|---|---:|
| 99 | 89 | 수용, 참여 10 감소 | 50 / 450 |
| 100 | 90 | 경계 당일 수용, 동일 감소 | 50 / 450 |
| 101 | 91 | `OUTSIDE_WINDOW`, 기존 결과 유지 | 60 / 540 |

수용된 두 경우는 **300 제외액 + 300 홀더 + 400 상계 + 50 참여 + 450 잔여 = 수정 총액 1,500**이다. 참여 10 감소는 합성 환수 조정이며 실제 현금 유입이 아니다. 창 밖 사례는 100의 불일치를 별도 미반영 차이로 표시한다.

### 3.5 `cap_clawback_and_term_end`

기존 참여율 `r`과 계약 전체 참여 한도 `C`를 그대로 사용한다. 새로운 claim·명세서·실행별 한도를 만들지 않는다. 과거 이력을 생략한 중간 북은 허용하지 않으며 계약 시작부터 재생해야 한다.

`G`는 지금까지 수용한 **양의 참여 배정 합계**다. 환수는 순참여액을 줄이지만 `G`를 줄이지 않는다. 추가 배정은 `C − G`까지만 가능하다. `G=C`가 되면 `CAP_REACHED`를 영구 latch하고 이후 양의 배정을 중단한다. 미배정 초과액은 수익자 잔여이며 미래 지급 대기열이 아니다.

명세서의 미상한 참여 계산값을 `U`, 현재 순배정을 `E`라 한다. 사건마다 `d = U_new − U_old`를 계산한다.

- `d>0`: 기간 내이고 cap latch 전이면 `min(d, C−G)`만 배정한다.
- `d<0`: 해당 명세서에서 `min(E, −d)`만 환수 조정한다.
- 수용하지 못한 양의 차이는 이월 청구권으로 남기지 않는다. 음의 차이도 다른 명세서에서 추가 회수하지 않는다.

설명용 `C_demo=100`, 기존 `G=90`에서 양의 차이 20이 오면 10만 배정하고 latch한다. 이후 환수 30이면 순배정은 70이지만 `G=100`이다. 다음 양의 차이 20은 배정되지 않는다. 실제 기존 한도의 값은 이 예시에서 추론하지 않는다.

기간 종료 `T` 당일 사건까지 양의 배정이 가능하다. `T+1`부터 신규 원 사건·양의 배정은 중단하고, 기존 명세서의 창 안 음의 조정만 반영한다. 양의 보정은 계산·진단하되 배정하지 않는다. 마지막 창이 닫히면 `FINAL_SIMULATED`이며, 이는 실제 채무 소멸이나 법적 종결이 아니다.

### 3.6 `rounding_carry_and_duplicates`

각 명세서에서 현재 claim별 참여 기초의 합을 `N_s`라 한다. 정수 bps 참여율을 사용하여 `U_s = (N_s × r) // 10000`, `carry_s = (N_s × r) % 10000`으로 계산한다. 부동소수점과 claim별 선반올림은 금지한다.

나머지는 동일 명세서의 다음 사건으로 이월하며 보정 때 합계에서 다시 계산한다. 설명용 10%에서 기초 7과 7은 각각 절사하지 않고 합계 14에서 참여 1, 나머지 4,000을 만든다. 다른 명세서·계약으로 나머지를 이전하지 않는다. 창 종료 시 나머지를 진단에 보존하고 지급액으로 올림하지 않는다.

동일 `event_id`와 동일 정규화 payload는 한 번만 처리한다. 같은 ID의 다른 payload는 `DUPLICATE_CONFLICT`로 북 전체를 거절한다. 다른 ID로 반복한 동일 대체 금액은 차이가 0이므로 추가 배정을 만들지 않는다. 입력 재배열은 결과를 바꾸지 않지만 sequence 변경은 의미 변경이므로 digest도 달라진다.

### 3.7 `disposable_replay_bounds`

V1은 계약 1개·수익자 1명, claims 최대 32개, 명세서 최대 16개, 중복 제거 전 사건 최대 256개, 입력 UTF-8 최대 1 MiB로 제한한다. 전체 `sim_day` 범위는 `S`부터 최대 365일 차이이며 마지막 anchor의 90일 창까지 이 범위 안에 있어야 한다. 금액 및 각 시점 북 총액의 상한은 합성 단위 `10^12`다.

이 숫자는 로컬 재생 용량이며 금융 한도가 아니다. 크기 초과·불완전 이력·산술 불변식 실패는 전체 거절하고 부분 성공 결과를 내지 않는다.

호출은 입력을 복사하여 메모리에서 재생한 결과만 반환한다. persistent command, workspace 저장, overlay append, 스케줄러, 자동 지급, 실제 상계 실행은 없다. 반환한 북을 다음 호출의 신뢰 상태로 재사용하지 않고 원 입력부터 다시 계산한다.

### 3.8 `provenance_and_output_labels`

출력에는 결정 ID·정책 버전·조건 출처와 digest·입력 digest·명세서 tuple·revision digest·정렬키·원 사건 참조·제외액·우선 분해·참여 전후값·한도 소비·환수·나머지·창 밖 차이를 포함한다.

필수 라벨은 `SIMULATED`, `SYNTHETIC_FIXTURE_PROFILE`, `SHADOW_NOT_APPLIED`, `UNSUPPORTED_BY_PINNED_FSM`, `SIMULATION_ONLY_NOT_OFFERED_V1`, `fsm_expressible:false`, `vendor_fsm_reconciliation:false`, `funds_executed:false`, `persistent_commands:false`, `automatic_payouts:false`, `production:NOT_AUTHORIZED`, `upstream_adoption_claimed:false`다. 로컬 digest는 인증·체인 확정·회계 증빙을 뜻하지 않는다.

리뷰가 제공한 선행 참여 정책 분류에 따라 cross-claim 계산·참여 배정·cap 추적은 **`UNSUPPORTED_BY_PINNED_FSM`**이다. 여덟 선택 전체에 `fsm_expressible:false`를 기록한다. `SHADOW_NOT_APPLIED`는 미적용, FSM 비지원은 표현 불가능이라는 별도 분류다. 문서 채택·바인딩 검사 통과로 이 분류가 바뀌지 않는다.

제공된 이전 라운드 문서와 리뷰에 따르면 `tests/decision_bindings.json`에 여덟 행이 등록되어 있다. 모두 `kind:module`, `status:PENDING_CONSUMER`, `consumer_node:participation-window-replay`이며 reason은 기존 통합 앵커와 미완료 구현을 구분한다. 구현 상태는 계속 `PENDING_IMPLEMENTATION`이다.

| entry | 기존 integration anchor | 미구현 내용 |
|---|---|---|
| `event_claim_membership` | `capital/shadow.py` | 고정 다중 claim 멤버십 |
| `statement_anchor_and_day_order` | `capital/overlay.py` | 불변 명세서·당일 순서 |
| `advance_slice_priority_inputs` | `capital/shadow.py` | 홀더·상계·참여 분해 |
| `adjustment_window_boundary` | `capital/overlay.py` | 참여 90일 보정창 |
| `cap_clawback_and_term_end` | `capital/terms.py` | 누적 한도·환수 latch |
| `rounding_carry_and_duplicates` | `capital/shadow.py` | 명세서 나머지·중복 처리 |
| `disposable_replay_bounds` | `capital/service.py` | 제한된 일회성 재생 |
| `provenance_and_output_labels` | `capital/export.py` | 재생 출처·FSM 비지원 출력 |

이번 개정에서는 구현 파일을 열거나 수정하지 않았다. overlay 앵커는 영속 append를, export 앵커는 legacy export construction 변경을 승인하지 않는다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "participation-window-decision",
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-11-01",
  "provisional": true,
  "bases": {"capital_main": "c4114c7", "kix_protocol_main": "fd33335", "verification": "SUPERVISOR_SUPPLIED"},
  "execution_provenance": {"document_author": "Codex", "model_attribution": "SUPERVISOR_REQUIRED", "claude_cli_execution_verified": false},
  "consumer_registration": {"target": "participation-window-replay", "status": "PENDING_CONSUMER", "implementation_status": "PENDING_IMPLEMENTATION", "registry": "tests/decision_bindings.json", "entry_count": 8, "registration_applied": true, "verification": "SUPERVISOR_REVIEW_SUPPLIED"},
  "entries": {
    "event_claim_membership": {
      "status": "ADOPTED",
      "value": {"agreements": 1, "beneficiaries": 1, "membership": "FIXED_MANIFEST", "claim_originals": "ONE_PER_CLAIM_PER_BOOK", "source_amount_identity": "UNIQUE_PER_BOOK", "events": ["ORIGINAL", "ADJUSTMENT"], "adjustment": "SAME_CLASSIFICATION_REPLACEMENT_AMOUNT", "inputs": "SYNTHETIC_ALREADY_CLASSIFIED_ONLY", "fsm_expressible": false, "fsm_support": "UNSUPPORTED_BY_PINNED_FSM"},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-01",
      "cap_rows": ["CAP-01", "CAP-08"],
      "rationale": "Fixed membership and unique source amounts prevent repeated use of one claim.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "statement_anchor_and_day_order": {
      "status": "ADOPTED",
      "value": {"identity": ["book_id", "agreement_id", "anchor_day"], "anchor": "EXPLICIT_IMMUTABLE_SIM_DAY", "original_day": "ANCHOR_DAY", "order": ["sim_day", "sequence"], "sequence": "UNIQUE_WITHIN_DAY", "close": "AFTER_ALL_EVENTS_OF_DAY", "wall_clock": false, "fsm_expressible": false, "fsm_support": "UNSUPPORTED_BY_PINNED_FSM"},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-01",
      "cap_rows": ["CAP-01", "CAP-15"],
      "rationale": "Immutable anchors and explicit ordering make replay independent of arrival order.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "advance_slice_priority_inputs": {
      "status": "ADOPTED",
      "value": {"excluded": ["PROTECTED_LINES", "PLATFORM_FEES", "REFUND_RESERVES"], "order": ["SLICE_HOLDER_FIRST", "ADVANCE_SETOFF_ON_REMAINDER", "PARTICIPATION", "BENEFICIARY_RESIDUAL"], "obligations": "PINNED_DISJOINT_CLAIM_BUDGETS", "conflict": "REJECT_BOOK", "conservation": "GROSS_EQUALS_EXCLUDED_PLUS_HOLDER_PLUS_ADVANCE_PLUS_PARTICIPATION_PLUS_RESIDUAL", "fsm_expressible": false, "fsm_support": "UNSUPPORTED_BY_PINNED_FSM"},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-01",
      "cap_rows": ["CAP-04", "CAP-08"],
      "rationale": "Holder priority and disjoint advance budgets prevent cash reuse.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "adjustment_window_boundary": {
      "status": "ADOPTED",
      "value": {"days_after_anchor": 90, "predicate": "anchor_day <= adjustment_day <= anchor_day + 90", "boundary_inclusive": true, "outside_window": "DIAGNOSTIC_ONLY_NO_RESTATEMENT", "reanchor": false, "fsm_expressible": false, "fsm_support": "UNSUPPORTED_BY_PINNED_FSM"},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-01",
      "cap_rows": ["CAP-01", "CAP-05"],
      "rationale": "An inclusive integer-day boundary eliminates ambiguous cutoff handling.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "cap_clawback_and_term_end": {
      "status": "ADOPTED",
      "value": {"terms": "PRESERVE_EXISTING_RATIO_CAP_AND_TERM", "missing_terms": "BLOCK_CALCULATION", "cap_basis": "CUMULATIVE_ACCEPTED_POSITIVE_ALLOCATIONS", "clawback_reopens_cap": false, "cap_reached": "IRREVERSIBLE_LATCH", "negative_delta": "LIMIT_TO_CURRENT_STATEMENT_NET_ALLOCATION", "unallocated_positive_delta": "NO_BACKLOG", "term_end": "INCLUSIVE_THEN_NEGATIVE_ADJUSTMENTS_ONLY_WITHIN_ORIGINAL_WINDOW", "fsm_expressible": false, "fsm_support": "UNSUPPORTED_BY_PINNED_FSM"},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-01",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Clawbacks correct prior allocations without creating revolving participation capacity.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "rounding_carry_and_duplicates": {
      "status": "ADOPTED",
      "value": {"arithmetic": "INTEGER_BPS", "uncapped_amount": "floor(sum_current_claim_bases * ratio_bps / 10000)", "carry": "REMAINDER_WITHIN_STATEMENT_ONLY", "final_fraction": "DISCLOSE_WITHOUT_ROUNDUP", "duplicate_identical": "NO_OP", "duplicate_conflicting": "REJECT_BOOK", "adjustments": "RECOMPUTE_FROM_REPLACEMENT_AMOUNTS", "fsm_expressible": false, "fsm_support": "UNSUPPORTED_BY_PINNED_FSM"},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-01",
      "cap_rows": ["CAP-08", "CAP-15"],
      "rationale": "Statement-level integer arithmetic preserves fractional carry and duplicate safety.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "disposable_replay_bounds": {
      "status": "ADOPTED",
      "value": {"max_claims": 32, "max_statements": 16, "max_input_events": 256, "max_input_bytes": 1048576, "max_day_span": 365, "max_book_amount": 1000000000000, "complete_history_required": true, "persistent_commands": false, "automatic_payouts": false, "failure": "ATOMIC_REJECTION", "fsm_expressible": false, "fsm_support": "UNSUPPORTED_BY_PINNED_FSM"},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-01",
      "cap_rows": ["CAP-08", "CAP-13"],
      "rationale": "A bounded disposable book supports complete deterministic replay without persistent execution.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "provenance_and_output_labels": {
      "status": "ADOPTED",
      "value": {"labels": ["SIMULATED", "SYNTHETIC_FIXTURE_PROFILE", "SHADOW_NOT_APPLIED", "SIMULATION_ONLY_NOT_OFFERED_V1", "UNSUPPORTED_BY_PINNED_FSM"], "production": "NOT_AUTHORIZED", "funds_executed": false, "upstream_adoption_claimed": false, "consumer": "participation-window-replay", "consumer_status": "PENDING_CONSUMER", "registration_applied": true, "required_provenance": ["DECISION", "TERMS_SOURCE", "INPUT_DIGEST", "STATEMENT_IDENTITY", "REVISION_DIGEST", "EVENT_LINEAGE"], "fsm_expressible": false, "fsm_support": "UNSUPPORTED_BY_PINNED_FSM", "implementation_status": "PENDING_IMPLEMENTATION", "vendor_fsm_reconciliation": false, "persistent_commands": false, "automatic_payouts": false},
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-01",
      "cap_rows": ["CAP-09", "CAP-20"],
      "rationale": "Explicit provenance separates provisional product choices from implementation and authority.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| 기준 | 대응·현재 상태 |
|---|---|
| 여덟 결정과 단일 기계 판독 블록 | §3·§4, 항목은 잠정 `ADOPTED`; 최상위 상태는 `PROVISIONAL_PRODUCT_DECISION` |
| 멤버십·정체성·순서·90일 경계 | §3.1–3.2·3.4, 89/90/91일 독립 예시 |
| 상계·홀더 우선·참여 보존 | §3.3–3.4, 제외액 포함 합계 대사 |
| 한도·환수·나머지·일회성 북 | §3.5–3.7 |
| FSM 표현 가능성 | §3.3·3.8·§4, 모두 `UNSUPPORTED_BY_PINNED_FSM`; 합성 산술과 vendor 대사 구분 |
| pending 소비자 등록과 검사 | 제공 리뷰가 여덟 `PENDING_CONSUMER` 행 확인; 검사 provenance는 §7 |
| 기존 범위와 owner gates 유지 | 복수 payee·영업일 배치·외부사실·법률 승인·제3자 투자·production 제외 |

## 6. Open risks

기존 참여 조건의 정확한 값·필드와 전체 슬라이스 우선권 규칙은 제공 발췌만으로 확인할 수 없다. 구현자는 원문과 충돌하면 영향을 받는 계산을 중단하고 별도 후속 결정으로 해결해야 한다. 이 문서로 기존 조건을 묵시적으로 덮어쓰지 않는다.

비회전 한도는 환수 후 순참여액이 한도보다 낮아지는 결과를 의도적으로 허용한다. 창 밖 차이는 미해결 진단이며 회계·법률상 면책을 뜻하지 않는다. 계정·세무·법률 취급은 **전문가 검토 전 작업 가정(`WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW`)이며 법률·세무·회계 자문이 아니다.**

## 7. 후속 작업

Supervisor가 최종 결정문을 저장한다. 이번 개정은 최상위 `status:PROVISIONAL_PRODUCT_DECISION`을 추가하여 항목 상태의 roll-up 문제를 해소하고, 비자문 문구를 명시한다. 여덟 제품 선택과 pending 소비자 등록은 유지한다.

제공된 이전 라운드 문서는 2026-11-01에 `python3 scripts/decision_ledger.py`, `python3 scripts/decision_bindings.py --check`, `python3 scripts/docs_surface.py --check`가 각각 exit 0이었다고 보고했다. Ledger의 `--check` 시도는 exit 2였으며 지원되는 기본 명령으로 확인했다고 기록했다. **이번 문서 출력 라운드에서는 명령을 재실행하지 않았다.** 저장 후 동일 검사와 결정 표면의 잠정 상태 확인이 필요하다. 이전 검사 결과를 이번 개정 바이트의 통과 증거로 간주하지 않는다.

후속 소비자는 기존 조건 출처를 고정하고 경계일, 같은 날 순서, 홀더 부족, 상계 예산 중복, cap 후 환수, 음의 보정과 나머지, 중복 충돌, 용량 거절을 검증한다. 새 vectors에는 `scripts/docs_surface.py` 수동 목록과 README needles를 함께 반영한다. pack vectors, parked multi-payee 입력과 기존 `PENDING_OWNER_ACTION` gates는 이번 개정으로 변경하지 않는다. 문서·등록 검사는 재생 구현 완료나 vendor FSM 적합성을 증명하지 않는다.
