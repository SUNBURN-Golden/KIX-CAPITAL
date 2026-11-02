# Capital 환불 충격 경계 결정 — 차입기초 커버리지를 위반하는 최소 환불액

**PROVISIONAL PRODUCT DECISION — 시뮬레이션·제품 설계 전용. 실자금 없음. production `NOT_AUTHORIZED`.**

| 항목 | 값 |
|---|---|
| 결정 노드 | `refund-frontier-decision` |
| 요청된 결정자·위임 표기 | **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)** |
| 날짜·기준 | 2026-11-02 · Capital main `c4114c7` · kix-protocol `590d68d` |
| 의존 결정·구현 | `financial-terms-decision`, `risk-whatif-scenarios`, `claim-slice-registry` |
| 의도 소비자 | `capital/refund_frontier.py`, `GET /api/risk`의 추가형 `refund_frontier` |
| 변경 범위 | 이 결정 문서만. 기존 terms·마진 정책·고정 충격 결과 불변 |

위 결정자 표기는 요청된 위임 메타데이터다. 이 개정은 현재 Codex 응답으로 작성했으며, 지정 Claude CLI 실행·세 번의 실패·대체 모델 승계는 확인하지 않았다. upstream 채택·영수증·SEMANTIC_CONFORMANCE를 주장하지 않는다. 법률·회계적 해석은 `WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW`이며 이 문서로 확정하지 않는다.

## 1. 결정 요약

| item | decision | CAP rows | consumer |
|---|---|---|---|
| `shock_basis_and_domain` | 실제 식별되는 청구·payee 줄의 추가 환불액을 정수 KRW로 배분한다. 목적값은 중복 제거한 총 환불액이다. | CAP-04, CAP-12 | `capital/refund_frontier.py` |
| `coverage_breach_predicate` | 선지급별 바인딩 청구·선지급률로 평가한다. 적격 액면 합산 → 비율 적용 → 한 번 내림 → `outstanding > base`. 수익자 요약은 어느 선지급이든 위반하는 최초 경계다. | CAP-01, CAP-04 | frontier, `/api/risk` |
| `eligible_case_scope` | 일회용 장부의 비종결 선지급을 평가한다. 기존 위반은 0, 노출 0은 경계 없음. 입력 부재·지원 제외는 별도 상태다. | CAP-01, CAP-04 | frontier |
| `shared_claim_and_slice_treatment` | 공유 청구의 환불은 한 번만 세고 연결된 모든 선지급을 재평가한다. 양수 슬라이스 점유 청구는 V1 미지원으로 확정한다. | CAP-03, CAP-04, CAP-08 | frontier, registry 조회 |
| `rounding_and_boundary_witness` | 선지급별 정확한 닫힌식의 최솟값을 사용한다. 전역 감소 스텝 정렬은 폐기한다. 정해진 배분과 1원 전 경계를 출력한다. | CAP-04, CAP-12 | frontier |
| `result_labels_and_consumers` | 파생 조회값만 제공한다. 마진콜 기록·부도 적격·확률·대출 승인과 구분하고 기존 고정 충격 결과를 보존한다. | CAP-04, CAP-09 | `/api/risk` |

여섯 항목의 `ADOPTED`는 잠정 제품 결정을 뜻한다. 미지원 범위를 결정한 것은 그 범위의 수치 경계를 결정했다는 뜻이 아니다.

## 2. KIX 비전 연결 — 사용한 pack 근거

- `docs/CAPITAL_REQUIREMENTS_KO.md` 제공 발췌는 실행 핀과 역사적 결정 출처를 구분한다. 이 문서의 기준 커밋도 출처이며 upstream 구속이나 채택 증명이 아니다.
- `docs/SEAMS.md` 제공 발췌에 따라 로컬 검증을 upstream 적합성으로 승격하지 않는다. frontier는 기존 입력을 읽는 계산 소비자이며 새 port 채택을 선언하지 않는다.
- `docs/decisions/CAPITAL_CLAIM_SLICE_REGISTRY.md` 제공 발췌의 공유 한도·이중사용 방지 목적을 유지한다. 공유 담보를 중복 환불하거나, 확인되지 않은 슬라이스 배분 규칙을 만들어내지 않는다.
- `docs/decisions/CAPITAL_DEFAULT_RECOVERY.md` 제공 발췌의 가속·부도·상각 구분을 유지한다. 가상 경계는 기록된 운영 사건을 발생시키지 않는다.
- `docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md` 제공 발췌처럼 합성 산술에서 법률·회계 입장을 추론하지 않는다.

기존 고정 충격의 질문을 “어느 환불액에서 처음 위반하는가”로 확장하되, 현재 마진 평가의 의미를 보존한다. 검토자가 제공한 `capital/margin.py:72–84` 및 FINANCIAL_TERMS 설명은 **2차 근거**로 사용했다. 해당 원문은 허용 경로 밖이라 열지 않았다. 발췌가 생략된 Protocol 문서의 내용은 근거로 주장하지 않는다.

## 3. 항목별 결정

### 3.1 `shock_basis_and_domain` — ADOPTED

물리적 줄의 키는 `L = (claim_id, payee_label)`이다. 같은 줄이 여러 선지급에 연결돼도 충격 변수는 하나다.

- `E_L = max(0, line_face_L − refund_open_L)`: 현재 적격 액면.
- `x_L`: 기존 환불에 추가되는 가상 환불액.
- 정의역: `x_L ∈ {0, …, E_L}`.
- 총 충격: `s = Σ_L x_L`. 합계는 중복 제거한 줄 집합에 대해 계산한다.

기존 환불은 `E_L`에 이미 반영했으므로 다시 차감하지 않는다. 가상 환불은 선지급 잔액을 상환하지 않는다. 현금 흐름·시간·티어·수수료·이자는 고정한다.

수익자 B의 충격 후보는 평가 대상 선지급들의 바인딩 청구에서 B에게 매핑된 줄의 합집합이다. 다른 수익자의 줄과 그림자 줄은 후보가 아니다. 특정 선지급의 경계를 찾을 때는 그 선지급에 영향을 주는 줄만 필요하다.

기존 고정 bps 충격은 독립적으로 유지한다. 이 경계는 고정 그리드의 보간값이나 “최소 bps”가 아니라, 허용된 모든 정수 배분에 대한 최소 KRW다.

### 3.2 `coverage_breach_predicate` — ADOPTED

검토 발췌에 맞춰 평가 단위를 **선지급 a**로 고정한다.

- `L(a)`: a의 바인딩 청구에서 해당 수익자에게 매핑된 적격 줄.
- `E_a = Σ_{L∈L(a)} E_L`.
- `O_a`: 기존 마진 평가에 쓰이는 a의 미상환 노출.
- `r_a`: 기존 terms·티어 매핑으로 해석된 a의 정수 bps 선지급률.

지원 범위의 술어는 다음 하나다.

```text
base_a(x) = ((E_a − Σ[L∈L(a)] x_L) × r_a) // 10000
breach_a(x) ⇔ O_a > base_a(x)
breach_B(x) ⇔ 평가 대상 a 중 breach_a(x)가 하나라도 참
```

`//`는 비음수 정수 내림이다. **줄별 내림을 합산하지 않는다.** 서로 다른 청구의 담보를 수익자별로 합쳐 다른 선지급의 부족분을 상쇄하지 않는다. 선지급마다 다른 비율이 있으면 각 평가에 따로 적용한다. 동일 청구에 여러 선지급이 묶여도 노출을 합쳐 새 마진 술어를 만들지 않는다.

등식은 커버됨이다. 별도 완충률이나 새로운 마진 임계값을 추가하지 않는다. 기존 문서의 “TERMS가 다르면 다른 산식을 적용”하는 조항은 삭제한다. 구현에서 이 산식과 기존 마진 결과의 불일치가 발견되면 호환성 실패로 처리하고 정확한 frontier 출력을 보류한다. 두 정의 중 하나를 조용히 선택하거나 기존 마진 정책을 수정하지 않는다.

### 3.3 `eligible_case_scope` — ADOPTED

`SIMULATED_DISPOSABLE_BOOK`에서만 계산한다. fixture에는 계산을 적용하지 않는다.

선지급별 처리 순서는 다음과 같다.

1. FSM `CLOSED`·`DEFAULTED` 또는 상각 게시된 선지급은 `NOT_COMPUTED_TERMINAL`.
2. 잔액을 알 수 없으면 `NOT_COMPUTED_MISSING_INPUTS`. 알려진 `O_a = 0`이면 `FRONTIER_UNDEFINED_NO_OUTSTANDING`.
3. 양수 노출의 청구·payee 매핑·티어·비율·registry 상태를 검증한다. 누락은 `NOT_COMPUTED_MISSING_INPUTS`, 중첩 소유는 `NOT_COMPUTED_AMBIGUOUS_LINE_OWNERSHIP`.
4. 양수 슬라이스 점유 또는 지원하지 않는 평가 형태는 §3.4·§3.6의 전용 상태.
5. 검증된 입력에서 `O_a > base_a(0)`이면 `ALREADY_BREACHED_ZERO_SHOCK`, 경계는 0.
6. 그 외 양수 노출은 정확한 양수 경계를 계산한다.

알려진 0과 누락은 다르다. 비율 0·양수 노출은 기존 위반이다. 유효한 줄들이 모두 적격 액면 0이어도 양수 노출이면 기존 위반이다. 매핑된 줄 자체가 없으면 담보 0으로 추정하지 않고 입력 부재로 처리한다.

수익자 요약은 평가 가능한 양수 노출들의 경계 중 최솟값이다. 미지원·입력 부재 건이 남으면 정확한 수익자 경계는 `null`이다. 단, 검증된 선지급 하나가 이미 위반이면 전체 최소값 0은 확정할 수 있으며 `evaluation_complete:false`를 함께 표시한다. 종결·노출 0인 건은 양수 노출 집합에서 제외하고 이유를 유지한다.

### 3.4 `shared_claim_and_slice_treatment` — ADOPTED

**공유 청구:** 같은 물리적 줄의 환불액은 목적값에서 한 번만 센다. 해당 줄에 연결된 선지급은 모두 같은 충격을 받는다. 수익자 내부에서 한 청구를 여러 선지급이 참조한다는 이유만으로 입력을 모호하다고 하지 않는다. 이는 기존 선지급별 평가를 재현하는 것이며, 담보 재사용이나 추가 대출을 허가하지 않는다.

서로 다른 수익자가 동일 청구의 분리된 payee 줄을 갖는 것은 허용한다. 같은 물리적 줄이 서로 다른 수익자에게 중첩 매핑되면 영향을 받는 평가를 미산출한다. 임의의 비례 배분으로 해결하지 않는다.

**슬라이스:** V1은 관련 청구의 registry 상태가 완전하고 **잔존 점유가 0임을 확인한 경우만** 수치 경계를 지원한다. 관련 청구에 양수 점유가 있으면 `NOT_COMPUTED_SLICE_ENCUMBRANCE`, `frontier_krw:null`이다. 종료 슬라이스도 잔존 점유가 있으면 같은 처리다. registry 조회가 없으면 무점유로 간주하지 않는다.

이 제한은 구체적인 지원 범위 결정이다. pack은 자유 면 감산 정책의 존재를 보여주지만, 그 감산을 현재 선지급별 마진 평가의 어느 입력에 반영하는지까지 증명하지 않는다. frontier에서만 점유를 빼면 기존 마진의 역산이라는 주장이 깨질 수 있다. 따라서 구현자가 새로운 감산·우선순위·손실 배분을 선택하게 두지 않는다.

슬라이스 손상 임계값도 이번 버전에서는 `null`이다. 가상 `SLICE_IMPAIR` 명령·손상 기록·추천을 생성하지 않는다. 양수 점유 지원에는 기존 마진과 registry 입력의 연결을 확인한 별도 결정이 필요하다.

### 3.5 `rounding_and_boundary_witness` — ADOPTED

반올림 순서는 **줄별 정수 잔여액 → 바인딩 청구 내 합산 → 해당 선지급률 곱셈 → 한 번 내림 → 엄밀 비교**다. 부동소수 연산은 사용하지 않는다.

지원되는 선지급이 현재 커버되고 `O_a > 0`이면 `r_a > 0`이며 다음이 정확하다.

```text
T_a = (10000 × O_a − 1) // r_a
f_a = E_a − T_a
```

이유는 `floor(z × r_a / 10000) < O_a`와 `z × r_a ≤ 10000 × O_a − 1`이 동치이기 때문이다. 따라서 `1 ≤ f_a ≤ E_a`. 모든 관련 줄을 환불하면 base가 0이므로 양수 노출의 위반은 도달 가능하다.

완전한 수익자 평가에서는 `f_B = min_a f_a`다. 어느 배분이 선지급 a를 위반시키려면 그 청구에 적어도 `f_a`원이 필요하고, 전체 충격은 그보다 작을 수 없다. 반대로 최소 `f_a`를 가진 선지급의 줄에 그 금액을 배분하면 실제 위반하므로 하한과 상한이 일치한다.

대표 증인은 최소 경계 선지급을 고르되 동률이면 `advance_id`의 UTF-8 바이트 순으로 선택한다. 선택한 선지급의 줄을 `(claim_id, payee_label)` 같은 순서로 정렬하고, 앞줄부터 `E_L` 한도까지 채워 총 `f_B`원을 배분한다. 여기서는 같은 선지급률이 합산액에 한 번 적용되므로 모든 동일 총액 배분의 base가 같다. 이 규칙은 최적화 휴리스틱이 아니라 증인의 결정론적 선택이다.

1원 전 증인은 위 배분의 마지막 양수 줄에서 1원을 뺀다. 양쪽에서 모든 관련 선지급의 base를 다시 출력한다. 전역 최소성 증명은 위 식이며, 한 경로의 두 점만 확인해서 최소라고 주장하지 않는다. 0 경계에는 음수 충격 증인을 만들지 않는다.

아래 숫자는 합성 검증 입력이며 새로운 금융 조건이 아니다.

| 예시 | 입력 | 정확한 경계와 양측 값 |
|---|---|---|
| 단일 줄 | `E=47,500,000`, `r=5000`, `O=20,000,000` | `f=7,500,001`. 직전 base `20,000,000`, 경계 base `19,999,999`. |
| 같은 청구의 두 줄 | `E=(6,4)`, `r=5000`, `O=4` | `f=3`, 증인 `(3,0)`. 직전 `(2,0)`은 base `4`, 경계는 `3`. |
| 서로 다른 청구·비율 | A: `E=20,r=8500,O=15`; B: `E=10,r=5000,O=3` | 개별 경계 A=`3`, B=`5`; 수익자 경계 `3`. `(2,0)`의 bases=`(15,5)`, `(3,0)`의 bases=`(14,5)`. |
| 기존 위반 반례 | 두 청구 각각 `E=100,r=5000`; 노출 `(60,10)` | bases=`(50,50)`. 첫 선지급이 이미 위반이므로 경계 `0`. 합산 노출 `70`과 합산 base `100`으로 상쇄하지 않는다. |
| 동일 청구 공유 | 한 청구 `E=100,r=5000`; 선지급 노출 `(50,10)` | 개별 경계 `(1,81)`. 환불 `1`원을 한 번 세면 bases=`(49,49)`이고 첫 선지급이 위반한다. |

두 줄 예시에서 충격 `(1,1)`은 총 2원이고 올바른 base는 `floor((5+3)/2)=4`다. 줄별 내림 합계 `2+1=3`은 잘못된 위반을 만든다.

검토의 `20@8500`, `10@5000`을 하나의 합산 base로 보고 노출 18을 비교하는 목적함수는 채택하지 않는다. 위 세 번째 예시는 노출을 실제 선지급별로 명시한다. 기존 전역 스텝 정렬은 누적 비용과 선행 스텝 제약을 처리하지 못하므로 폐기한다. 한 선지급 안에서 줄마다 비율이 다른 입력도 이번 닫힌식의 지원 범위가 아니다.

### 3.6 `result_labels_and_consumers` — ADOPTED

수치 경계 상태는 `BREACH_FRONTIER_KRW`, `ALREADY_BREACHED_ZERO_SHOCK`이다. 그 외 상태의 `frontier_krw`는 `null`이며 이유와 영향을 받는 선지급을 명시한다. 라벨 전체는 §4에 고정한다.

결과에는 평가 범위, 선지급·청구 식별자, 입력 출처, 계산 완전성, 줄별 배분, 경계와 직전의 선지급별 base·노출을 담는다. 같은 입력의 출력 순서는 결정론적이어야 한다.

공통 플래그는 `label:SIMULATED`, `hypothetical:true`, `applied:false`, `margin_call_recorded:false`, `default_eligibility_changed:false`, `journal_written:false`, `funds_executed:false`, `policy_adopted:false`다. 여기서 기록·적용 플래그는 **이 계산의 효과**를 뜻하며 기존 장부에 마진콜이 없다는 뜻이 아니다.

`capital/refund_frontier.py`는 조회 입력의 순수 소비자다. `/api/risk`에 추가 블록으로 연결하며 기존 고정 충격의 값·순서·라벨·계산을 바꾸지 않는다. 기능이 빠진 기존 응답은 그대로 유지한다. 새 저널·COA·자동 호출·port를 만들지 않는다.

경계는 기록된 마진콜도, 치유 창 시작도, 가속·부도 적격 변경도 아니다. 손실 확률·기대손실·실제 담보 가치·대출 또는 인출 승인도 아니다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "refund-frontier-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-11-02",
  "provisional": true,
  "bases": {
    "capital_main": "c4114c7",
    "kix_protocol": "590d68d",
    "terms_version": "CAPITAL-TERMS-V1"
  },
  "upstream_adoption_claimed": false,
  "entries": {
    "shock_basis_and_domain": {
      "status": "ADOPTED",
      "value": {
        "unit": "integer KRW additional refund face",
        "line_key": ["claim_id", "payee_label"],
        "eligible": "E_L = max(0, line_face_L - refund_open_L)",
        "domain": "integer 0 <= x_L <= E_L",
        "objective": "minimize sum x_L over distinct physical lines",
        "scope": "union of beneficiary-mapped lines on evaluated bound claims",
        "fixed_shocks": "existing grid, calculations, values and labels unchanged",
        "consumer": "capital/refund_frontier.py"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": ["CAP-04", "CAP-12"],
      "rationale": "A distinct-line integer domain measures additional refunds without duplicate collateral shocks or bps conversion rounding.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "coverage_breach_predicate": {
      "status": "ADOPTED",
      "value": {
        "evaluation_unit": "one advance and its bound claim",
        "inputs": "O_a from existing margin exposure; r_a from existing terms and tier mapping; E_a is the sum of mapped eligible lines on the bound claim",
        "base": "base_a(x) = ((E_a - sum(x_L for L in L(a))) * r_a) // 10000",
        "predicate": "O_a > base_a(x); equality is covered",
        "beneficiary_predicate": "any evaluated advance breaches; never compare summed exposure with summed claim bases",
        "debt": "unchanged by hypothetical refunds",
        "compatibility": "mismatch with existing margin evaluation blocks exact output; no alternate terms override or policy rewrite",
        "consumer": "capital/refund_frontier.py; GET /api/risk"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Per-advance evaluation and aggregate-then-floor arithmetic preserve the margin semantics supplied in the review.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "eligible_case_scope": {
      "status": "ADOPTED",
      "value": {
        "workspace": "SIMULATED_DISPOSABLE_BOOK only",
        "precedence": ["terminal", "unknown or zero exposure", "input and ownership validation", "unsupported case", "existing breach", "positive frontier"],
        "terminal": "CLOSED, DEFAULTED or posted writeoff; exclude with explicit status",
        "zero_exposure": "frontier null; strict breach impossible",
        "existing_breach": "validated O_a > base_a(0) gives frontier 0",
        "missing": "unknown exposure, claim, mapped lines, tier rate or registry state; never substitute zero",
        "known_zero_rate": "positive exposure is already breached",
        "beneficiary_summary": "minimum of eligible advance frontiers only when complete; unresolved cases yield null, except a validated zero frontier proves the global minimum zero",
        "empty_summary": "all terminal gives terminal status; otherwise no positive nonterminal exposure gives no-outstanding status",
        "consumer": "capital/refund_frontier.py"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Separate terminal, zero, missing and unsupported cases so absence of a computed frontier cannot be mistaken for coverage.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "shared_claim_and_slice_treatment": {
      "status": "ADOPTED",
      "value": {
        "shared_claim": "one shock variable per physical line; count once and re-evaluate every linked advance independently",
        "ownership": "disjoint payee lines may belong to different beneficiaries; overlapping ownership is not computed",
        "slice_support": "V1 requires complete registry evidence of zero residual encumbrance on relevant claims",
        "positive_encumbrance": {
          "status": "NOT_COMPUTED_SLICE_ENCUMBRANCE",
          "frontier_krw": null,
          "reason": "pack does not establish integration of slice deductions with existing per-advance margin evaluation",
          "target": "separate compatibility decision before enabling encumbered claims"
        },
        "impairment_threshold_krw": null,
        "slice_effects": "no inferred loss allocation, impairment entry, priority change or recommendation",
        "consumer": "capital/refund_frontier.py; claim-slice-registry read fold"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": ["CAP-03", "CAP-04", "CAP-08"],
      "rationale": "Preserve physical shock identity and explicitly exclude unverified encumbrance semantics instead of introducing a new margin policy.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "rounding_and_boundary_witness": {
      "status": "ADOPTED",
      "value": {
        "rounding_order": ["integer remaining eligible face per line", "sum within bound claim and beneficiary mapping", "multiply by advance rate", "floor once", "strict comparison"],
        "positive_frontier": "f_a = E_a - ((10000 * O_a - 1) // r_a), for supported covered positive exposure",
        "summary_frontier": "f_B = min_a f_a, subject to completeness rules",
        "canonical_witness": "choose minimum f_a, ties by UTF-8 advance_id; fill its lines in UTF-8 (claim_id, payee_label) order up to E_L",
        "predecessor": "for positive frontier remove one KRW from the last positive witness line; re-evaluate all relevant advances at both allocations",
        "minimality": "any breach requires at least one advance-specific f_a; the selected witness attains the minimum",
        "rejected_method": "global sorting of cumulative or incremental base-reduction steps",
        "unsupported_shape": "multiple line rates within one advance or incompatible margin inputs",
        "witness_fields": ["frontier_krw", "selected_advance_id", "allocation", "predecessor_allocation", "advance_evaluations_at_frontier", "advance_evaluations_at_predecessor", "evaluation_complete"],
        "consumer": "capital/refund_frontier.py"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": ["CAP-04", "CAP-12"],
      "rationale": "The exact integer inverse proves minimality; deterministic witness selection needs no invalid step-cost heuristic.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "result_labels_and_consumers": {
      "status": "ADOPTED",
      "value": {
        "labels": [
          "BREACH_FRONTIER_KRW",
          "ALREADY_BREACHED_ZERO_SHOCK",
          "FRONTIER_UNDEFINED_NO_OUTSTANDING",
          "NOT_COMPUTED_TERMINAL",
          "NOT_COMPUTED_MISSING_INPUTS",
          "NOT_COMPUTED_AMBIGUOUS_LINE_OWNERSHIP",
          "NOT_COMPUTED_SLICE_ENCUMBRANCE",
          "NOT_COMPUTED_UNSUPPORTED_EVALUATION",
          "NOT_COMPUTED_INCOMPLETE_SCOPE",
          "NOT_COMPUTED_WORKSPACE_SCOPE"
        ],
        "constant_flags": {
          "label": "SIMULATED",
          "hypothetical": true,
          "applied": false,
          "margin_call_recorded": false,
          "default_eligibility_changed": false,
          "journal_written": false,
          "funds_executed": false,
          "policy_adopted": false
        },
        "flags_meaning": "effects of this calculation only; not assertions that historical records are absent",
        "surface": "read-only additive refund_frontier block; preserve all existing fixed-shock results and responses where feature is absent",
        "non_claims": ["recorded margin call", "cure or default eligibility", "loss probability or expected loss", "lending or draw authorization", "real collateral valuation", "upstream adoption"],
        "consumer": "capital/refund_frontier.py; GET /api/risk"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": ["CAP-04", "CAP-09"],
      "rationale": "Explicit status and effect labels prevent a hypothetical threshold from being consumed as an operational event or authorization.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

- 단일 결정 블록·여섯 항목·소비 대상: §4.
- 정수 정의역·환불 기준·엄밀 위반·내림 순서: §3.1–3.2, §3.5.
- 기존 위반·노출 0·매핑 부재·종결·공유·슬라이스: §3.3–3.4.
- 정확한 다중 줄 경계·기존 위반 반례: §3.5. 닫힌식은 합성 **190개 경우의 전수 배분 탐색**과 일치했고 양수 경계 예시의 양측 산술도 확인했다.
- 기록·확률·승인과의 구분 및 고정 충격 보존: §3.6.
- `python3 scripts/decision_ledger.py`: **UNVERIFIED**. 이 응답에서는 저장소를 수정하지 않았고, 스크립트는 허용된 읽기 경로 밖이므로 실행하지 않았다. 감독자가 문서를 저장한 뒤 검증해야 하며 통과를 주장하지 않는다.

## 6. Open risks

- 마진·TERMS 원문 대신 검토 발췌에 의존했다. 구현의 기존 마진 동등성 검증은 필수다.
- 양수 슬라이스 점유의 수치 경계는 의도적으로 미지원이다. 이를 0 점유로 대체하면 안 된다.
- 불완전한 수익자 평가에서 일부 계산값을 전체 최소값으로 표시하면 안 된다.
- 큰 금액은 중간 곱셈까지 정확한 정수로 계산해야 한다.

## 7. 후속 작업

구현 노드는 `capital/refund_frontier.py`와 추가 조회 블록을 만들고, 기존 마진 결과와의 동등성·공유 줄의 단일 계수·다중 줄 내림·상태 우선순위·불완전 요약을 검증한다. 고정 충격 결과의 회귀 보존도 확인한다.

감독자는 문서 저장 후 `python3 scripts/decision_ledger.py`를 실행하고 필요한 결정 바인딩을 검증한다. 새 벡터를 추가하는 구현에서는 README와 `scripts/docs_surface.py` 등록 및 `--check`를 수행한다. 양수 슬라이스 지원은 기존 마진 입력과 registry 연결을 확인한 별도 결정 이후 진행한다.
