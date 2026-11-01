# Capital 환불 충격 경계 결정 — 차입기초 커버리지를 무너뜨리는 최소 환불 충격(역방향 스트레스)

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
이 문서는 KIX-CAPITAL 저장소 안의 **시뮬레이션·제품 설계용** 결정이다. 청약이나 대출 제안이 아니고, 실자금이 움직이지 않으며, production은 계속 `NOT_AUTHORIZED`다. 법률·회계 관련 언급(손상·소구의 성격)은 **전문가 검토 전의 작업 가정(WORKING ASSUMPTION)** 이며 자문이 아니다. 어떤 upstream 계약의 채택도 주장하지 않고 SEMANTIC_CONFORMANCE도 아니다. 이 문서는 kix-protocol·kix-commerce-apps를 수정하지 않고, diff는 `docs/decisions/CAPITAL_REFUND_FRONTIER.md` 한 파일이다. `capital/`·`tests/`·vendor 바이트·골든 digest·기존 결정 노트·기존 고정 충격 결과의 상태 토큰은 건드리지 않는다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `refund-frontier-decision` (Decision: define the smallest refund shock that breaches borrowing-base coverage) · deps `financial-terms-decision`, `risk-whatif-scenarios`, `claim-slice-registry` · kind `decision` · user_merge `False` |
| 결정자 | **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)** |
| 위임 원문 | 2026-10-08 18:25 KST JunTae Park: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." |
| 결정일 | 2026-11-02 |
| 기준 | KIX-CAPITAL main `c4114c7` · kix-protocol `fd33335` (읽기 전용 `/workspace/capital-run/kixproto-ro`) · vendor pin `7481b0e16ce9b903abbffa62249bb91cd9e63cfe` (다섯 파일 SHA256 불변) |
| 의도 소비자 | `capital/refund_frontier.py` (구현 노드가 새로 쓰는 읽기 전용 모듈)과 `GET /api/risk`의 추가형 `refund_frontier` 블록 |
| 상태 어휘 | **ADOPTED** = 위임 범위 안의 잠정 값. **UNDETERMINED** = 값을 정할 수 없어 이유만(`value: null`, 방향은 `target`). 여섯 항목 모두 ADOPTED |
| 숫자 출처 규칙 | 한도·비율·선지급률 숫자를 복사하지 않는다. `CAPITAL-TERMS-V1` 필드명(`additional_margin`, `underwriting_depth`, 티어별 `advance_rate`)으로만 인용한다. 선행 노트 `CAPITAL_FINANCIAL_TERMS.md`는 허용 경로 밖이라 직접 열지 않았고, 필드명은 허용된 노트의 인용으로만 참조한다. 이름·숫자가 충돌하면 **선행 노트가 이기고, 경계 산술과 라벨은 이 노트가 이긴다.** |

## 1. 결정 요약

| item | 결정 (요지) | CAP rows | 소비 노드 / seam |
|---|---|---|---|
| `shock_basis_and_domain` | **ADOPTED.** 충격은 수익자별 정수 KRW 환불 액면 합 `s ∈ [0, Σ eligible_L]`(각 줄 `s_L ∈ [0, eligible_L]`). 기존 bps 그리드 `[500,1000,2500,5000]`는 바이트 불변, 경계는 그 역문제 | CAP-04, CAP-12 | `capital/refund_frontier.py` |
| `coverage_breach_predicate` | **ADOPTED.** 엄밀 위반 = 기존 마진 평가 술어를 그대로 반전: `outstanding_B > base_B(s)`(`=`는 커버됨). `base_B(s) = Σ_L floor(max(0, eligible_L(s) − encumbered_L(s)) × advance_rate(tier_L)/10000)` | CAP-04, CAP-01 | `capital/refund_frontier.py`, `GET /api/risk` |
| `eligible_case_scope` | **ADOPTED.** 대상 = `SIMULATED_DISPOSABLE_BOOK`의 수익자별 노출만. 부도·종결 등 종결 선지급, 노출 0, 매핑·티어 입력 부재, 소유 모호 줄은 각 전용 라벨로 미산출 | CAP-01, CAP-04 | `capital/refund_frontier.py` |
| `shared_claim_and_slice_treatment` | **ADOPTED.** 청구 공유는 줄 단위 귀속으로 닫고, 슬라이스 점유 `encumbered_L`을 감산한 자유 면만 충격이 줄인다. 충격 시 `eligible_L(s) < outstanding_S`이면 가상 `SLICE_IMPAIRMENT_ELIGIBLE` 표지를 함께 보고(기록 없음) | CAP-03, CAP-04, CAP-08 | `capital/refund_frontier.py`, `claim-slice-registry` 조회 |
| `rounding_and_boundary_witness` | **ADOPTED.** 줄별 내림 → 합산 → 엄밀 비교 순서. `s*`는 **전 배분 최소**로 정의하고, 대표 증인은 각 줄의 base 감소 스텝 위치를 전역 오름차순으로 살린 배분 + `s*−1`/`s*` 두 지점의 (base, outstanding) | CAP-04, CAP-12 | `capital/refund_frontier.py` |
| `result_labels_and_consumers` | **ADOPTED.** 라벨 열거 6종 + 상수 플래그(`SIMULATED`, `hypothetical:true`, `applied:false`, `margin_call_recorded:false`, `journal_written:false`, `funds_executed:false`). 기록된 마진콜·부도 적격·손실 확률·대출 승인과 명시 구분 | CAP-04, CAP-09 | `GET /api/risk` `refund_frontier` 블록 |

## 2. KIX 비전 연결 — 읽은 pack 경로

- `/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md` (모델 1·A-4). 「과거 사실의 재생은 새로운 외부 실행 허가가 아니다」와 「예약 확정 ≠ 결제 확인」에 따라, 경계 계산은 저널에 아무것도 쓰지 않는 순수 함수다. 가상 충격이 만드는 "위반"은 기록된 사실이 아니라 조건부 답이다.
- `/workspace/capital-run/kixproto-ro/README.md` §1·§3. 현재는 mock·비운영 범위이고 자체 저장·로그 신규 구현은 금지다. 그래서 결과는 상태가 아니라 요청 시점 입력의 파생값으로만 존재한다.
- `docs/CAPITAL_REQUIREMENTS_KO.md` CAP-04 행(읽기 전용 `/api/risk`, 고정 환불 충격 `[500,1000,2500,5000]` bps는 SIMULATED 가정이며 마진콜을 기록하지 않음, `SIMULATED_DISPOSABLE_BOOK`에서만 마진 발동, fixture는 `FIXTURE_VIEWS_IMMUTABLE`). 이 노트는 그 표면의 **역문제**를 같은 격리 규칙 아래 둔다. CAP-01·03·08·12 행(발췌만).
- `docs/decisions/CAPITAL_CLAIM_SLICE_REGISTRY.md` §3.4·§3.6(G0 `eligible_face` 감산, `encumbered(L) = min(outstanding(S), eligible_L)`, 불변식 I-BASE와 "환불로 `eligible_L`이 줄면 손상" 규칙), §3.5(홀더 우선). 경계 계산은 같은 줄 산술을 공유한다.
- `docs/decisions/CAPITAL_DEFAULT_RECOVERY.md` §4.1·§4.8(마진콜→치유→가속은 **기록된** 마커의 폴드, 사람 명령). 이 노트의 가상 위반은 그 폴드에 진입하지 않는다.
- `docs/decisions/CAPITAL_DEMO_BOOK.md` §3.3(`beneficiary_payee_map`, `eligible_face` 규칙, `SHADOW_NOT_APPLIED` 라벨 문법)과 정직 라벨 규칙.
- `docs/SEAMS.md`(새 `typing.Protocol`·행 추가 없음 — 읽기 전용 산술은 port가 아님), `docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md` §3.1(COA 게시 없음), `docs/decisions/CAPITAL_CLOSEOUT_ARTIFACT.md` §3.3(구현 시 `test_count`가 바뀌면 `CAPITAL-CLOSEOUT-REGEN-V1` 재생성 절차).
- 사용하지 않은 pack 경로: `CAPITAL_ARTIFACT_BUNDLING.md`(새 노트는 번들에 자동 포함), `docs/VALIDATION.md`(발췌만).
- 「포부」의 번역: 고정 충격이 "주어진 충격에 견디는가"를 묻는다면 경계는 "어디서 무너지는가"를 닫는다. 담보 기하(공유 줄·슬라이스 점유)를 구현 전에 먼저 정해 두면, what-if 엔진이 커질 때 재결정이 필요 없다.

## 3. 항목별 결정

공통 정의(모두 정수 KRW, 선행 노트와 동일): 줄 `L = (claim_id, payee_label)`, `eligible_L = max(0, line_face(L) − refund_open(L))`, `encumbered_L(s_L) = min(outstanding_S(L), eligible_L − s_L)`(비종결 슬라이스가 없으면 0), 자유 면 `free_L(s_L) = max(0, eligible_L − s_L − encumbered_L(s_L))`. 수익자 `B`의 줄 집합 = `B`에 바인딩된 청구 중 `payee_label ∈ beneficiary_payee_map[B]`인 pinned 원장 줄.

### 3.1 shock_basis_and_domain — ADOPTED
- **값.** 충격은 수익자 하나에 대한 **가상 환불 액면의 줄별 배분** `s = (s_L)`, 각 `s_L ∈ [0, eligible_L]` 정수, 총량 `|s| = Σ s_L ∈ [0, Σ eligible_L]`. `eligible_L`을 넘는 충격은 의미가 없다(자유 면은 이미 0). 정의역 상한에서 `base_B = 0`이므로 `outstanding_B ≥ 1`이면 위반은 항상 도달 가능하다.
- **기존 스트레스와의 관계.** 기존 고정 충격(환불 액면 대비 bps 그리드)은 **그대로 유지**하며 결과 바이트·라벨·그리드를 바꾸지 않는다. 경계는 그 역문제: "위반이 시작되는 최소 총량 `s* = min{ |s| : breach(s) }`".
- **근거.** 절대 KRW 정수는 bps 변환의 반올림을 배제해 경계를 정확히 잡는다. 줄 상한이 있는 유한 정의역은 "도달 불가" 판정을 결정론적으로 만든다.

### 3.2 coverage_breach_predicate — ADOPTED
- **값.** 위반 술어는 기존 마진 평가와 **동일한 술어의 반전**이다: `breach_B(s) ⇔ outstanding_B > base_B(s)`. 등식(`outstanding = base`)은 커버됨이며 위반이 아니다 — 커버리지 부족은 **엄밀 부등호**다. `base_B(s) = Σ_L floor(free_L(s_L) × advance_rate_bps(tier_L) / 10000)`이고, 티어별 선지급률 적용·줄별 내림은 기존 U3/마진 산술의 순서를 그대로 쓴다(이 노트가 새 반올림을 만들지 않는다). 선행 TERMS의 마진 발화 술어가 이 형태와 다르면 **TERMS 술어가 이기고**, 경계는 그 술어를 그대로 반전한다. 가상 충격은 `outstanding_B`를 바꾸지 않는다(환불은 담보를 줄이지 부채를 줄이지 않는다).
- **근거.** 기존 발화 조건과 다른 술어를 만들면 "가상 위반인데 기록된 마진콜 조건은 아님"이라는 모순이 생긴다. 같은 술어의 반전이라야 경계가 진짜 경계다.

### 3.3 eligible_case_scope — ADOPTED
- **값.** 대상 = `SIMULATED_DISPOSABLE_BOOK` 안에서, `outstanding_B ≥ 1`이고 비종결 선지급이 있는 수익자. 워크스페이스 fixture(`FIXTURE_VIEWS_IMMUTABLE`)는 기존대로 미발동이다. 미산출은 각각 명시 라벨로 답한다(§3.6):
  - `s* = 0`이 되는 기존 위반(`outstanding_B > base_B(0)`): `ALREADY_BREACHED_ZERO_SHOCK` — **가상 평가의 결과이지 기록된 마진콜과 동일하지 않다.**
  - 노출 0: `FRONTIER_UNDEFINED_NO_OUTSTANDING`(`s*` 없음; base ≥ 0 = outstanding이므로 엄밀 위반 불가).
  - 해당 수익자의 모든 선지급이 종결(FSM `CLOSED`/`DEFAULTED`, 오버레이 상각 게시): `NOT_COMPUTED_TERMINAL` — 종결 건의 커버리지는 회수 폭포의 문제이지 차입기초의 문제가 아니다.
  - 매핑된 줄이 하나도 없거나 줄에 티어 선지급률이 없어 `base_B`를 구성할 수 없음: `NOT_COMPUTED_MISSING_INPUTS`(`missing` 목록 첨부). 선지급률 0인 줄은 배분 후보에서 제외되나 정상 산출이다.
  - 한 줄이 둘 이상의 수익자 `eligible_face`에 동시 기여하는 모호 소유(V1 맵 구조상 발생하지 않아야 함): `NOT_COMPUTED_AMBIGUOUS_LINE_OWNERSHIP`.
- **근거.** "경계 없음"을 "0"이나 "무한"으로 압축하면 소비자가 위험도를 오독한다. 원인별 라벨이 정직한 답이다.

### 3.4 shared_claim_and_slice_treatment — ADOPTED
- **값.** (a) **공유 청구:** 충격은 줄 단위로 귀속된다. 수익자 B의 경계는 B의 줄 집합에만 적용되고, 같은 청구의 다른 payee 줄(다른 수익자 소유, 또는 `SHADOW_NOT_APPLIED` 그림자 줄)은 건드리지 않는다. 그림자 줄은 base에 기여하지 않으므로 배분 후보가 아니다. (b) **슬라이스 점유:** 자유 면 산식 `free_L(s_L)`에 이미 `encumbered_L` 감산이 들어 있고, 충격으로 `eligible_L`이 `outstanding_S` 아래로 줄면 점유가 함께 줄어 자유 면은 0에 수렴한다 — 즉 **슬라이스 점유 줄에 대한 충격은 빠르게 무력화된다**(감산 항이 함께 사라져 base 감소가 `outstanding_S`까지만 일어남). 이는 I-BASE 위반이 아니라 레지스트리 노트 §3.6의 **손상** 조건이므로, `s*` 계산과 별도로 `impairment_threshold_krw = min{ |s| : ∃L, eligible_L − s_L < outstanding_S(L) }`(충족 줄 없으면 null)를 함께 보고하고 결과에 `would_trigger: SLICE_IMPAIRMENT_ELIGIBLE`을 단다. 홀더 우선 순서(`served`)는 분배 사건이 없으므로 경계에 영향이 없다. (c) **소구·손상 기록 없음:** 가상 손상은 `SLICE_IMPAIR` 명령을 만들지 않고, 추천도 하지 않는다.
- **근거.** 매각된 면은 수익자 자산이 아니므로(레지스트리 §3.5) 환불 충격이 먹는 것은 홀더 앞의 잔여가 아니라 줄의 자유 면이다. 구현 노드가 요구한 "공유 담보·슬라이스 처리"를 이 산식으로 닫는다.

### 3.5 rounding_and_boundary_witness — ADOPTED
- **값.** 산술 순서: (1) 줄별 `free_L` 정수 계산 → (2) 줄별 `× advance_rate_bps` 후 **내림** → (3) 합산 → (4) `outstanding_B`와 엄밀 비교. 부동소수 없음.
- **`s*` 정의.** `s* = min{ Σ s_L : breach_B(s) }`(전 배분 최소). 각 줄의 base 기여는 `s_L`의 비증가 계단 함수이고 단위 충격의 한계 감소는 0 또는 1이므로, `s*`는 "k번째 base 감소 스텝이 필요한 충격 단위 수"를 모든 줄에 대해 전역 오름차순으로 정렬해 필요한 감소량 `R = base_B(0) − outstanding_B + 1`번째까지 채우는 값과 같다. **대표 증인 배분** = 그 정렬 순서대로 채운 배분(동률은 `(claim_id, payee_label)` 오름차순)으로 유일하게 고정한다. 단순한 "최고 선지급률 줄 포화"는 정의가 아니다(내림 경계에서 엄밀 최소가 아닐 수 있음).
- **증인 필드.** `frontier_krw`, `allocation[{claim_id, payee_label, shock_krw}]`, `base_at_frontier`, `base_at_frontier_minus_1`, `outstanding`, `required_reduction R`. `s*−1`에서는 술어가 성립(커버됨), `s*`에서는 위반이어야 한다 — 양쪽 값을 함께 낸다.
- **작업 예시 1(합성, 슬라이스 없음).** 줄 `demo-delta-small` organizer 면 47,500,000, `refund_open` 0, 선지급률 5000 bps, `outstanding` 20,000,000. `base(0) = floor(47,500,000 × 0.5) = 23,750,000`, `R = 3,750,001`. 자유 면을 `x`로 두면 `floor(x/2) ≤ 19,999,999 ⇔ x ≤ 39,999,999`이므로 `s* = 47,500,000 − 39,999,999 = 7,500,001`. 검증: `s*−1 = 7,500,000` → 자유 40,000,000 → `base = 20,000,000 = outstanding`(커버됨, 엄밀 위반 아님); `s*` → 자유 39,999,999 → `base = 19,999,999 < outstanding`(위반).
- **작업 예시 2(슬라이스 점유).** 같은 줄에 `outstanding_S = 10,000,000`, `outstanding` 8,000,000. `base(0) = floor((47,500,000−10,000,000)/2) = 18,750,000`. 위반에는 자유 면 `< 16,000,000`이 필요 → `eligible − s − 10,000,000 ≤ 15,999,999` → `s ≥ 21,500,001` = `s*`. 이때 `eligible(s*) = 25,999,999 > outstanding_S`라 `impairment_threshold_krw`는 `s* > 37,500,000` 이후라 별도 보고되고 경계 자체는 손상 없이 도달한다.

### 3.6 result_labels_and_consumers — ADOPTED
- **라벨 열거.** `BREACH_FRONTIER_KRW`(증인 포함) · `ALREADY_BREACHED_ZERO_SHOCK`(`frontier_krw: 0`, `base(0)`·`outstanding` 포함) · `FRONTIER_UNDEFINED_NO_OUTSTANDING` · `NOT_COMPUTED_TERMINAL` · `NOT_COMPUTED_MISSING_INPUTS` · `NOT_COMPUTED_AMBIGUOUS_LINE_OWNERSHIP`.
- **상수 플래그(모든 결과).** `label: SIMULATED`, `hypothetical: true`, `applied: false`, `margin_call_recorded: false`, `default_eligibility_changed: false`, `journal_written: false`, `funds_executed: false`, `policy_adopted: false`.
- **소비.** 의도 소비자 `capital/refund_frontier.py`(순수 함수, FSM·오버레이·슬라이스 조회를 입력으로 받음)와 `GET /api/risk` 응답의 추가형 `refund_frontier` 블록(일회용 장부에서만; 부재 시 기존 응답 바이트 불변). 새 `typing.Protocol`·`docs/SEAMS.md` 행·저널 엔트리·COA 분개·골든 변경은 없다. AI lane은 조회만 가능하고 이 결과로 실행을 제안할 수 있다(`proposal` 소비는 별도 권한 규칙).
- **비주장(non-claims).** 이 결과는 (i) 기록된 마진콜이 아니며 치유 창·가속·부도 적격 계산을 시작하지 않고, (ii) 확률·기대손실이 아니다(정확한 결정론적 역치이며 `loss probability` 주장 없음), (iii) 대출 승인·인출 게이트(U1–U6)와 무관한 자문값이며, (iv) 실제 담보 평가·집행이 아니다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "refund-frontier-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-11-02",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "scope": "KIX-CAPITAL simulation and product design only; not an offer; no real money; production NOT_AUTHORIZED; deterministic hypothetical bound, not a probability, not a recorded margin call, not lending authorization; no upstream contract claimed adopted",
  "bases": {"capital_main": "c4114c7", "kix_protocol": "fd33335", "vendor_pin_commit": "7481b0e16ce9b903abbffa62249bb91cd9e63cfe", "terms_version": "CAPITAL-TERMS-V1"},
  "upstream_adoption_claimed": false,
  "name_conflict_rule": "CAPITAL_FINANCIAL_TERMS.md was not opened (outside allowed paths); field and check names come from allowed notes citing it; on a name or number conflict the terms note wins, on frontier arithmetic and labels this note wins",
  "entries": {
    "shock_basis_and_domain": {
      "status": "ADOPTED",
      "value": {
        "shock_unit": "integer KRW refund face per line",
        "allocation_domain": "s_L in [0, eligible_L] integer for each beneficiary-owned line L; total |s| in [0, sum eligible_L]",
        "beneficiary_lines": "lines on claims bound to beneficiary B with payee_label in beneficiary_payee_map[B] and present on the pinned ledger",
        "reachability": "if outstanding_B >= 1 breach is always reachable because base_B = 0 at the domain top; s = 0 means already breached",
        "bps_grid": "existing fixed shocks [500,1000,2500,5000] bps unchanged, byte-identical; the frontier is the inverse question in absolute KRW",
        "consumer": "capital/refund_frontier.py"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": ["CAP-04", "CAP-12"],
      "rationale": "Absolute integer KRW removes bps-conversion rounding at the boundary, and a finite per-line domain makes reachability decidable while leaving the existing bps stress grid untouched.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "coverage_breach_predicate": {
      "status": "ADOPTED",
      "value": {
        "predicate": "breach_B(s) iff outstanding_B > base_B(s); equality is covered, not a breach (strict inequality)",
        "base": "base_B(s) = sum over L of floor(max(0, eligible_L - s_L - encumbered_L(s_L)) * advance_rate_bps(tier_L) / 10000); per-line floor and tier-rate application follow the existing U3/margin arithmetic exactly",
        "terms_override": "if CAPITAL-TERMS-V1's actual margin trigger differs in form, that predicate wins and the frontier is defined as its inverse; the strict-breach convention is kept",
        "outstanding_unchanged": "hypothetical refunds shrink collateral, never the advance debt",
        "consumer": "capital/refund_frontier.py; GET /api/risk refund_frontier block"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": ["CAP-04", "CAP-01"],
      "rationale": "The frontier only means something if it inverts the same predicate that fires recorded margin calls; a divergent predicate would manufacture imaginary breaches.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "eligible_case_scope": {
      "status": "ADOPTED",
      "value": {
        "computed_for": "beneficiaries in SIMULATED_DISPOSABLE_BOOK with outstanding_B >= 1 and at least one non-terminal advance",
        "workspace_fixtures": "FIXTURE_VIEWS_IMMUTABLE; not computed, same as existing margin machinery",
        "not_computed_labels": {
          "ALREADY_BREACHED_ZERO_SHOCK": "outstanding_B > base_B(0); frontier 0; still hypothetical, not a recorded call",
          "FRONTIER_UNDEFINED_NO_OUTSTANDING": "outstanding_B = 0",
          "NOT_COMPUTED_TERMINAL": "all advances CLOSED/DEFAULTED or written off",
          "NOT_COMPUTED_MISSING_INPUTS": "no mapped lines or missing tier advance rate; missing list attached",
          "NOT_COMPUTED_AMBIGUOUS_LINE_OWNERSHIP": "one line feeding two beneficiaries' eligible_face"
        },
        "zero_rate_lines": "advance_rate 0 lines are excluded from the allocation set but the case still computes",
        "consumer": "capital/refund_frontier.py"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Each reason a frontier cannot exist gets its own honest label instead of collapsing to 0 or infinity, which a consumer would misread as risk level.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "shared_claim_and_slice_treatment": {
      "status": "ADOPTED",
      "value": {
        "line_scoping": "shock applies only to beneficiary B's own mapped lines; other payee lines on the same claim and SHADOW_NOT_APPLIED shadow lines are untouched and are not allocation candidates",
        "slice_encumbrance": "free_L(s_L) = max(0, eligible_L - s_L - min(outstanding_S(L), eligible_L - s_L)); shocks on encumbered lines lose effect once eligible reaches outstanding_S, because the encumbrance shrinks with the line",
        "impairment_reporting": "impairment_threshold_krw = min |s| making eligible_L - s_L < outstanding_S(L) on any line (null if none); result carries would_trigger SLICE_IMPAIRMENT_ELIGIBLE; no SLICE_IMPAIR entry and no recommendation is produced",
        "holder_first": "no distribution event inside a hypothetical shock, so served/holder-first arithmetic does not apply",
        "invariant": "shock-induced encumbrance shrinkage is impairment exposure per CLAIM_SLICE_REGISTRY section 3.6, never an I-BASE violation",
        "consumer": "capital/refund_frontier.py; reads the claim-slice registry fold"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": ["CAP-03", "CAP-04", "CAP-08"],
      "rationale": "Encumbered face is already not the beneficiary's to lose, so a refund shock only eats the free remainder; reporting the impairment threshold beside the frontier closes the shared-collateral question before implementation.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "review_items": ["position of slice holders and refund obligations in insolvency"]
    },
    "rounding_and_boundary_witness": {
      "status": "ADOPTED",
      "value": {
        "rounding_order": ["per-line free_L integer", "per-line floor(x * rate_bps / 10000)", "sum", "strict compare against outstanding_B"],
        "frontier_definition": "s* = min over all allocations of total shock such that breach_B(s); the true minimum, not the saturate-highest-rate approximation (floors make that an upper bound only)",
        "canonical_witness": "fill base-reduction steps of all lines in global ascending per-step shock cost; ties by (claim_id, payee_label) ascending; unique by construction",
        "witness_fields": ["frontier_krw", "allocation per line", "base_at_frontier", "base_at_frontier_minus_1", "outstanding", "required_reduction"],
        "boundary_check": "predicate holds (covered) at s*-1 and fails at s*; both sides emitted",
        "worked_examples": [
          {"face": 47500000, "rate_bps": 5000, "slice": 0, "outstanding": 20000000, "base0": 23750000, "s_star": 7500001, "base_at_s_star_minus_1": 20000000, "base_at_s_star": 19999999},
          {"face": 47500000, "rate_bps": 5000, "outstanding_S": 10000000, "outstanding": 8000000, "base0": 18750000, "s_star": 21500001, "impairment_threshold": 37500001}
        ],
        "consumer": "capital/refund_frontier.py"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": ["CAP-04", "CAP-12"],
      "rationale": "Pinning the per-line floor order and a unique canonical witness makes the boundary reproducible and lets tests assert both sides of the strict inequality on the exact integer edge.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "result_labels_and_consumers": {
      "status": "ADOPTED",
      "value": {
        "labels": ["BREACH_FRONTIER_KRW", "ALREADY_BREACHED_ZERO_SHOCK", "FRONTIER_UNDEFINED_NO_OUTSTANDING", "NOT_COMPUTED_TERMINAL", "NOT_COMPUTED_MISSING_INPUTS", "NOT_COMPUTED_AMBIGUOUS_LINE_OWNERSHIP"],
        "constant_flags": {"label": "SIMULATED", "hypothetical": true, "applied": false, "margin_call_recorded": false, "default_eligibility_changed": false, "journal_written": false, "funds_executed": false, "policy_adopted": false},
        "surface": "capital/refund_frontier.py pure function; additive refund_frontier block inside GET /api/risk on disposable books only; absent key keeps existing responses byte-identical",
        "no_new": ["typing.Protocol or docs/SEAMS.md row", "journal entry", "COA posting", "golden change", "draw gate change"],
        "non_claims": ["not a recorded margin call; starts no cure window, acceleration or default-eligibility computation", "not a probability or expected loss; an exact deterministic threshold", "not lending authorization; unrelated to U1-U6 draw gates", "not real collateral valuation or enforcement"],
        "consumer": "capital/refund_frontier.py; GET /api/risk refund_frontier block"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-11-02",
      "cap_rows": ["CAP-04", "CAP-09"],
      "rationale": "Honest labels keep a hypothetical coverage failure visibly distinct from recorded margin calls, default eligibility, loss probability and lending authorization, while an additive read-only block preserves every existing risk surface byte.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

- **한 개의 `capital-decision-v1` 블록, 여섯 항목 전부** → §4, 모두 ADOPTED.
- **정수 충격 정의역·환불 기준·엄밀 위반 술어·반올림 순서·정확 경계 예시** → §3.1·§3.2·§3.5(예시 2개, `s*−1`/`s*` 양쪽 수치 포함).
- **기존 위반·노출 0·매핑 부재·종결 선지급·공유 청구·슬라이스 점유의 명시 처리** → §3.3(원인별 라벨)·§3.4.
- **가상 커버리지 실패 vs 기록된 마진콜·부도 적격·손실 확률·대출 승인의 구분** → §3.6 비주장과 상수 플래그.
- **`capital/refund_frontier.py` 소비자 명명·기존 고정 충격 보존** → §1 표·§3.1·§3.6(부재 시 바이트 불변).
- **`scripts/decision_ledger.py` 통과·소비 대상과 미지원 케이스 명시** → 결정 블록 단일, 소비자 필드와 `not_computed_labels` 기록.

## 6. Open risks

- TERMS 원문의 마진 발화 술어(완충 비율 포함 여부)를 직접 읽지 못했다. 다르면 TERMS 술어가 이기고 `s*` 값만 달라지며 구조는 유지된다.
- `beneficiary_payee_map` 다대일·중첩 소유가 생기면 `AMBIGUOUS_LINE_OWNERSHIP` 경로가 실제로 쓰인다; 맵 스키마가 바뀌면 재검토.
- 청구→수익자 바인딩 소유권은 데모 북 규칙에 의존한다. 바인딩이 다원화되면 줄 귀속 규칙을 다시 연다.
- 손상 임계와 경계의 상대 순서(예시 2)가 구현에서 뒤집히는 책이 있을 수 있다 — 슬라이스가 큰 책은 `impairment_threshold < frontier`가 일반적일 것.

## 7. 후속 작업

- 구현 노드: `capital/refund_frontier.py` + `/api/risk` 추가 블록, 결정론 단위 테스트(예시 1·2, 라벨 전 종류, `s*−1`/`s*` 양측 검증), `docs_surface.py`·`decision_bindings.py` 등록.
- `test_count` 변동 시 `CAPITAL-CLOSEOUT-REGEN-V1` 절차로 closeout digest·vector pack 재생성.
- TERMS 마진 술어 확인 라운드에서 §3.2의 `terms_override` 조항 실제 검증.
