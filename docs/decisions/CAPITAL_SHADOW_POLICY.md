# Capital 그림자 산술 결정 — SHADOW_NOT_APPLIED 모순 해소와 Capital 소유 그림자 모듈 범위

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
시뮬레이션·제품 설계용이다. 실자금이 움직이지 않고 production은 `NOT_AUTHORIZED`. 법률·세무·회계 의존 항목은 전문가 검토 전 작업 가정이다. 어떤 upstream 계약 채택도 주장하지 않으며, vendor 바이트·고정 FSM·아홉 fixture·선행 결정 문서 본문은 건드리지 않는다. 코드 변경은 이 노드 범위 밖이다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `shadow-policy-decision` (Decision: resolve the SHADOW_NOT_APPLIED contradiction and the scope of Capital-owned shadow arithmetic) · deps `policy-simulator`, `settlement-policy-decision` · kind `decision` · user_merge `False` |
| 결정자 | GLM-5.3 xhigh (Claude CLI z.ai; Devin swe-2 fallback), delegated by JunTae 2026-10-08 (model 10-14 17:09) |
| 결정일 | 2026-10-14 |
| KIX-CAPITAL 기준 | main `8787278` |
| kix-protocol 기준 | `adcddc5` (읽기 전용 체크아웃 `/workspace/capital-run/kixproto-ro`) |
| 해소 대상 | audit-20 finding F4 — `docs/decisions/CAPITAL_SETTLEMENT_POLICY.md`(`CAPITAL-SETTLEMENT-POLICY-V1`, 2026-10-09)의 그림자 계산 지시와 `capital/policy.py`의 계산 거부가 충돌 |

## 1. 결정 요약

| item | 결정 (요지) | CAP rows | 소비 노드 / seam |
|---|---|---|---|
| `shadow_math_stance` | **ADOPTED `SHADOW_OWNED_SEPARATE_MODULE`.** 노트 §7의 SHADOW_NOT_APPLIED 지시가 **제품 의도로 유효**하고, `policy-simulator`의 거부는 **고정 FSM 적용 경로의 경계 안에서 정당**. 모순은 책임 분리로 해소: 그림자 계산은 별도 Capital 모듈이 소유하고, `policy-simulator`의 `unsupported()` 행은 적용 경로 판정으로 그대로 유지 | CAP-02/03/05/06 | `policy-simulator`(적용 경로) + 새 그림자 모듈(그림자 경로) |
| `shadow_module_ownership` | **ADOPTED `CAPITAL_OWNS_PURE_INTEGER_SHADOW_MODULE`.** `capital/` 아래 전용 모듈(권고명 `capital/shadow.py`) + 버전된 벡터 집합 `CAPITAL-SHADOW-V1`. 입력은 관측 스냅샷·선언 벡터뿐, 출력은 결정론적·digest 부착, vendor를 변경·패치하지 않고 어떤 장부에도 쓰지 않는다 | CAP-02/03/05/06 | 그림자 모듈 구현 노드(후속); `docs/SEAMS.md` 행 추가 없음 |
| `shadow_label_vocabulary` | **ADOPTED `CAPITAL-SHADOW-LABELS-V1`.** `UNSUPPORTED_BY_PINNED_FSM`(적용 경로 판정), `SHADOW_NOT_APPLIED`(모든 그림자 결과 필수), `SHADOW_INPUT_OBSERVED`/`SHADOW_INPUT_DECLARED`(입력 provenance), `SHADOW_INVARIANT_BREACH`, `SHADOW_DEFERRED`. 그림자 출력에 `funds_executed`·`bank_debit_observed`·`right_cancelled`·`external_return_closed`·`legal_debtor_bound`·`admission_granted` 필드 금지 | CAP-05, CAP-06 | 그림자 모듈, 조회·화면 소비자 |
| `rounding_and_tiebreak_rules` | **ADOPTED `CAPITAL-SHADOW-ROUNDING-V1`.** KRW 정수만(≤ `MONEY_MAX` 1e12), `q_i = floor(C·f_i/F)` + largest remainder(소수부 내림차순, 동점 = 수취인 라벨 UTF-8 바이트 오름차순, 1원씩), 역분개 동일 규칙, 게시당 1원 내림·나머지 이월, Move u128 리셀 세 줄은 재계산하지 않고 입력으로 관측, `F=0`이면 전 줄 0·잔여는 미배정 | CAP-05, CAP-06 | 그림자 모듈 모든 항목 |
| `refund_class_inputs` | **ADOPTED `CAPITAL-SHADOW-REFUND-V1`.** 다음 단계 그림자 계산 가능: **RC1·RC2·RC3·RC4** 단일 청구 벡터(2수취인 fixture 형태 선언 입력, R = 40,000 부분 + RC2 100,000 전액은 `FIXTURE_FULL_GROSS_RECLASS`와 결과 동일 검증). **RC5는 독립 벡터 없이 RU 실행 안에서만** 계산 | CAP-05, CAP-06 | 그림자 모듈 |
| `resale_unwind_scope` | **ADOPTED `CAPITAL-SHADOW-RESALE-V1`.** 다음 단계 그림자 계산 가능: **RU1·RU2·RU3 전부**, 선언 합성 사슬 벡터(`P_p`, `P_r`, `seller_due`/`organizer_due`/`platform_due`, 1차 청구 스냅샷). 노트의 두 worked example(113,000 / 80,000·20,000)을 골든 기대값으로 포함. 사슬 역추적 없음 | CAP-06 | 그림자 모듈 |
| `revshare_claim_purchase_deferral` | **ADOPTED `DEFER_NEXT_PHASE`.** `revenue_participation`(CAP-02)과 `claim_purchase`(CAP-03)은 다음 단계 그림자 범위에서 **유보**: 다청구 기준 수익 집계·90일 조정 창 시계와 상태 있는 슬라이스 등록부가 필요하고 법적 성격 검토가 열려 있음. 적용 경로 판정은 여전히 `UNSUPPORTED_BY_PINNED_FSM`, 그림자 라벨은 `SHADOW_DEFERRED` | CAP-02, CAP-03 | 그림자 모듈 2단계 대상 |
| `errata_to_settlement_note` | **ADOPTED.** `CAPITAL_SETTLEMENT_POLICY.md`는 편집하지 않고 §6 errata로 정정: "policy-simulator가 그림자 계산" → "Capital 그림자 모듈이 그림자 계산", "일회용 복제 장부" → "관측 스냅샷 또는 선언 벡터" | CAP-02/03/05/06 | 이 문서 §6 |

## 2. KIX 비전과의 연결

읽은 팩 경로만 인용한다.

- **모델 1 — 체인 권위 / 오프체인 위임 실행**(`/workspace/capital-run/kixproto-ro/README.md` §1·§3; `docs/decisions/AUTHORITY_MODEL_1.md`는 팩에 경로로만 열거). 그림자 모듈은 권리·실행·자금 효과를 만들지 않는 **읽기 경로의 결정론적 계산기**다. `admission_granted`·`right_cancelled`·`funds_executed`를 출력 필드 자체에서 배제해 모델 1 경계를 타입 수준에서 지킨다.
- **승인 범위와 이중 상태의 정직한 관리**(`docs/CAPITAL_REQUIREMENTS_KO.md`: 폐기 표시를 승인으로 읽지 말 것, upstream 채택은 영수증만). `docs/SEAMS.md`의 규칙 — `ADOPTED`는 upstream 영수증이 있을 때만 — 을 그림자에도 그대로 적용한다. 그림자 모듈은 포트가 아니고 SEAMS 행을 추가하지 않으며 모든 행은 `NOT_BOUND` 유지. `SHADOW_NOT_APPLIED`가 `ADOPTED`·적용으로 번역되는 경로를 만들지 않는다.
- **고정 FSM 진실의 보존**(`capital/scenarios.py`: 아홉 fixture는 비교용, `policy_adopted: False`; `capital/policy.py` 라인 1–11: "The note asks for shadow math on those entries; this node does not calculate them"). `policy.py`의 거부는 고정 `SettlementMachine`이 정책 입력으로 명시 순서 목록만 받는다는 사실의 정확한 반영이다. 이 결정은 그 거부를 뒤집지 않고, 계산의 **장소**를 분리한다. fixture·500 bps 정책·두 시험 순서·vendor SHA256은 불변.
- **선행 결정의 값은 그대로 입력**(`docs/decisions/CAPITAL_SETTLEMENT_POLICY.md`: RC1–RC5, RU1–RU3, `CAPITAL-REVSHARE-V1`, `CAPITAL-CLAIM-PURCHASE-V1`, UC1–UC4, largest remainder·라벨 오름차순; `docs/decisions/CAPITAL_FINANCIAL_TERMS.md`: 등급 금리·기간 규칙). 그림자 모듈은 노트 JSON을 읽어 계산하고 숫자 리터럴을 복사하지 않는다 — `policy.py`의 "no copied order literals"와 같은 규율.
- **검증 범위의 정직**(`docs/VALIDATION.md`: 그림자 결과는 내구성·은행 exactly-once·법적 결론의 증거가 아니다). 그림자 산술은 제품 규칙의 **모양 검증**이지 upstream SEMANTIC_CONFORMANCE가 아니다.
- **"포부"의 해석.** 다섯 비표현 항목 중 세 군(환불 부담, 리셀 언와인드, 잔여 현금)은 다음 단계에 실제 수치를 내고, 두 군(수익 참여, 채권 매입)은 무책임한 조기 계산이 아니라 **명시적 유보 사유와 목표 단계**를 가진다. 멈춤이 아니라 순서다.

## 3. 항목별 결정

### 3.1 shadow_math_stance — F4 해소

**결정: 노트 §7의 지시가 승자이되, 실행 주체가 바뀐다.** `CAPITAL-SETTLEMENT-POLICY-V1`이 `fsm_expressible: false` 항목에 `SHADOW_NOT_APPLIED` 계산을 요구한 것은 유효한 제품 지시다(위임 범위 안, ADOPTED 값의 검증 수단). `policy-simulator`(`capital/policy.py`)가 계산을 거부한 것도 그 자체로 정확하다 — 그 노드의 계약은 "결정된 순서를 고정 FSM `distribute(order=…)`에 적용"이며, `unsupported()`의 `computed: False`는 고정 FSM 경계의 정직한 보고다. 모순의 진짜 원인은 **한 노드에 두 의무**(적용 경로 + 그림자 계산)가 겹친 것이다. 해소: (a) 적용 경로 판정 `UNSUPPORTED_BY_PINNED_FSM`은 `policy-simulator`가 계속 소유·변경 없음, (b) `SHADOW_NOT_APPLIED` 계산은 §3.2의 별도 모듈로 이관. 어느 쪽 문서·코드도 이 결정에서 편집하지 않는다.

### 3.2 shadow_module_ownership

**Capital이 소유한다.** 순수 정수 모듈, 제약은 타입·입력으로 강제: (1) 입력 = 고정 FSM `view()`의 직렬화 스냅샷(`SHADOW_INPUT_OBSERVED`, 일회용 장부 재생으로 얻어도 됨) 또는 노트가 정의한 선언 벡터(`SHADOW_INPUT_DECLARED`); (2) 출력 = 결정론적 결과 + sha256(canonical JSON(inputs, policy_version)); (3) vendor를 import·패치·재핀하지 않고, 어떤 장부의 mutating op도 호출하지 않고, 적용 표시를 출력하지 않는다. SEAMS 포트가 아니므로 `SEAMS.md`에 행을 추가하지 않는다(upstream 계약을 대체하는 것이 아니다). `facade` 노출은 읽기 전용 조회로, "not an operating policy" 문구는 유지한다.

### 3.3 shadow_label_vocabulary

위 요약 표의 여섯 토큰이 전부다. 규칙: (a) `SHADOW_NOT_APPLIED`는 모든 그림자 결과 행·시나리오의 필수 라벨, (b) 적용 경로 토큰(`UNSUPPORTED_BY_PINNED_FSM`, `POLICY_INCONSISTENT`, `POLICY_UNDECIDED`, `NOT_BOUND`, `DECIDED`)과 그림자 경로 토큰은 서로의 출력에 나타나지 않는다, (c) 실효 필드 6종은 그림자 출력 스키마에 존재하지 않는다(false로 출력하는 것도 금지 — 스키마 부재가 더 강한 증거다), (d) 공통 라벨 문자열: `simulated shadow computation — not applied to the pinned FSM, not executed, not bank movement`.

### 3.4 rounding_and_tiebreak_rules

요약 표 그대로. 추가 상세: 최대 공약수 정규화 없이 `floor` 결과 + 소수부 `{C·f_i mod F}` 내림차순으로 R을 소진; 소수부 동점은 라벨 UTF-8 바이트 오름차순; 환불 역분개는 `f_i = face_i`, `F = gross`, `C = R_refund`; 수익 참여(2단계 대상이더라도 규칙은 지금 고정)는 게시당 1원 내림·나머지 이월; 리셀 세 줄은 Move u128 바닥 나눗셈 값을 입력으로 받고 재계산은 교차 검증용으로만(PF-C05 격리 유지); 모든 벡터는 비음수·정수·`MONEY_MAX` 이하 검증, 위반 시 `SHADOW_INVARIANT_BREACH`이고 금액을 출력하지 않는다.

### 3.5 refund_class_inputs

다음 단계 범위: RC1(전 줄 비례 역분개), RC2(주최자 줄 → 플랫폼 줄; R = gross 벡터는 `FIXTURE_FULL_GROSS_RECLASS` 결과와 수치 동일을 골든으로 검증), RC3(플랫폼 100%, 초과는 `PLATFORM_PROTOCOL_REVENUE_POOL` 표식), RC4(RC2형·RC3형 두 판정 벡터 모두). 입력 스키마: `{claim_snapshot, R, reason_class: "RC<n>", evidence_ref}`. 출력: 줄별 `cancelled_unpaid`·`recovery_due` 델타 — 회수는 제안이며 자동 상계 없음(노트 규칙 그대로). RC5는 단독 벡터가 없고 §3.6 RU 실행 안에서만 나타난다.

### 3.6 resale_unwind_scope

RU1·RU2·RU3 전부 다음 단계 그림자 계산. 입력은 노트 `CAPITAL-RESALE-UNWIND-V1`이 정의한 선언 벡터이고, 골든 기대값으로 프리미엄 예시(`P_p` 100,000 → 보유자 113,000)와 할인 예시(80,000/20,000, 역분개 0)를 벡터에 포함한다. RU3는 돈만 다루고 권리 상태는 입력으로도 출력으로도 갖지 않는다. 사슬 역추적은 벡터 스키마 자체가 차단한다(입력에 과거 거래 목록이 없다).

### 3.7 revshare_claim_purchase_deferral

두 항목 모두 `fsm_expressible: false`·`UNSUPPORTED_BY_PINNED_FSM` 판정은 불변이고, 다음 단계 그림자 범위에서는 `SHADOW_DEFERRED`로 유보한다. 사유: 수익 참여는 **다청구 이벤트 집합 집계 + 90일 조정 창의 `sim_day` 시계**가 필요하고, 채권 매입은 **`(claim_id, payee)` 유일성을 강제하는 상태 있는 슬라이스 등록부**라는 두 번째 산출물이 필요하다 — 둘 다 순수 무상태 함수 경계를 넘는다. 게다가 법적 성격(투자계약/대부/증권성) 검토가 열려 있어 조기 수치 고정은 검토를 선취한다. 목표: 무상태 벡터가 머지되고 이벤트 집합·등록부의 선언 입력 스키마를 별도 결정으로 정한 뒤 2단계.

### 3.8 errata_to_settlement_note

`CAPITAL_SETTLEMENT_POLICY.md` 본문은 편집하지 않는다. 정정은 이 문서 §6에만 존재한다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "shadow-policy-decision",
  "decided_by": "GLM-5.3 xhigh (Claude CLI z.ai; Devin swe-2 fallback), delegated by JunTae 2026-10-08 (model 10-14 17:09)",
  "date": "2026-10-14",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "scope": "KIX-CAPITAL simulation and product design only; not an offer; no real money; production NOT_AUTHORIZED; shadow outputs never applied to any FSM book; no upstream contract claimed adopted without a real upstream receipt",
  "resolves": "audit-20 finding F4: SHADOW_NOT_APPLIED instruction vs policy-simulator refusal — resolved by splitting owners, not by editing either artifact",
  "policy_version": "CAPITAL-SHADOW-POLICY-V1",
  "bases": {
    "capital_main": "8787278",
    "kix_protocol_main": "adcddc5",
    "prior_decision": "docs/decisions/CAPITAL_SETTLEMENT_POLICY.md (CAPITAL-SETTLEMENT-POLICY-V1) supplies all five shadow item values; this note changes none of them",
    "implementation_boundary": "capital/policy.py owns the apply path and its UNSUPPORTED_BY_PINNED_FSM verdicts; the shadow module owns computation on observed snapshots and declared vectors only"
  },
  "label_vocabulary": {
    "apply_path": ["UNSUPPORTED_BY_PINNED_FSM", "POLICY_INCONSISTENT", "POLICY_UNDECIDED", "NOT_BOUND", "DECIDED"],
    "shadow_path": ["SHADOW_NOT_APPLIED", "SHADOW_INPUT_OBSERVED", "SHADOW_INPUT_DECLARED", "SHADOW_INVARIANT_BREACH", "SHADOW_DEFERRED"],
    "forbidden_fields_in_shadow_output": ["funds_executed", "bank_debit_observed", "right_cancelled", "external_return_closed", "legal_debtor_bound", "admission_granted"],
    "common_label": "simulated shadow computation — not applied to the pinned FSM, not executed, not bank movement"
  },
  "next_phase_shadow_scope": {
    "computable": ["refund_bearer RC1-RC4", "refund_bearer RC5 only inside RU runs", "resale unwind RU1-RU3", "residual cash states UC1-UC4"],
    "deferred": ["revenue_participation", "claim_purchase"],
    "unsupported_by_pinned_fsm_all_five": "every fsm_expressible:false item keeps UNSUPPORTED_BY_PINNED_FSM on the apply path regardless of shadow computability"
  },
  "entries": {
    "shadow_math_stance": {
      "status": "ADOPTED",
      "value": {"resolution": "SHADOW_OWNED_SEPARATE_MODULE", "prevails": "the settlement note SHADOW_NOT_APPLIED instruction prevails as product intent; the simulator refusal prevails inside the pinned apply path; the contradiction dissolves by splitting owners", "apply_path_verdicts_unchanged": true},
      "fsm_expressible": false,
      "provided_by": "GLM-5.3 xhigh (Claude CLI z.ai; Devin swe-2 fallback), delegated by JunTae 2026-10-08 (model 10-14 17:09)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-02", "CAP-03", "CAP-05", "CAP-06"],
      "rationale": "Both artifacts were locally correct: the note issued a valid product instruction and the simulator correctly refused to compute outside the pinned FSM policy-input boundary; the real defect was one node carrying two duties, so the computation moves to a dedicated module while UNSUPPORTED_BY_PINNED_FSM stays the authoritative apply-path verdict.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "consumer": "policy-simulator keeps unsupported(); new shadow module computes"
    },
    "shadow_module_ownership": {
      "status": "ADOPTED",
      "value": {"owner": "CAPITAL", "form": "pure-integer deterministic module under capital/ (suggested capital/shadow.py) plus versioned vector set CAPITAL-SHADOW-V1", "inputs": "serialized pinned-FSM view snapshots or declared vectors only", "never": ["vendor import for mutation or repin", "mutating ops on any book", "applied or executed markings", "SEAMS row addition", "float arithmetic", "copied note literals (read the decision JSON)"]},
      "fsm_expressible": false,
      "provided_by": "GLM-5.3 xhigh (Claude CLI z.ai; Devin swe-2 fallback), delegated by JunTae 2026-10-08 (model 10-14 17:09)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-02", "CAP-03", "CAP-05", "CAP-06"],
      "rationale": "A Capital-owned pure module keeps the vendor pin byte-identical, keeps every seam NOT_BOUND, and makes shadow math a deterministic replayable product instrument rather than an implicit extension of the apply path.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "consumer": "follow-on implementation node; read-only facade query surface later"
    },
    "shadow_label_vocabulary": {
      "status": "ADOPTED",
      "value": {"policy_version": "CAPITAL-SHADOW-LABELS-V1", "tokens": {"UNSUPPORTED_BY_PINNED_FSM": "apply-path verdict only, fsm_expressible false", "SHADOW_NOT_APPLIED": "mandatory on every shadow result", "SHADOW_INPUT_OBSERVED": "input from a serialized pinned view", "SHADOW_INPUT_DECLARED": "input from a declared synthetic vector", "SHADOW_INVARIANT_BREACH": "conservation or bound check failed; emit no amounts", "SHADOW_DEFERRED": "decided item outside next-phase scope"}, "no_cross_contamination": "apply-path and shadow-path tokens never appear in each other's outputs"},
      "fsm_expressible": false,
      "provided_by": "GLM-5.3 xhigh (Claude CLI z.ai; Devin swe-2 fallback), delegated by JunTae 2026-10-08 (model 10-14 17:09)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-05", "CAP-06"],
      "rationale": "The settlement note's own open risk was shadow results being mistaken for FSM truth; a disjoint token set plus a forbidden-field schema makes that confusion a structural impossibility rather than a documentation plea.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "consumer": "shadow module, tests, any consumer of shadow rows"
    },
    "rounding_and_tiebreak_rules": {
      "status": "ADOPTED",
      "value": {"policy_version": "CAPITAL-SHADOW-ROUNDING-V1", "money": "non-negative KRW integers <= MONEY_MAX 1000000000000; floats forbidden", "split": "q_i = floor(C*f_i/F); remainder assigned +1 KRW in descending fractional part; ties ascending payee label in UTF-8 byte order", "reversal": "same rule with f_i = face_i, F = gross", "posting": "floor to 1 KRW per posting, remainder carried", "resale_lines": "Move u128 floor outputs are inputs, never recomputed except cross-check with identical semantics", "zero_denominator": "F = 0 yields all-zero splits and unallocated remainder, flagged SHADOW_INVARIANT_BREACH if cash would be dropped", "digest": "sha256 canonical JSON of (inputs, policy_version) on every run"},
      "fsm_expressible": false,
      "provided_by": "GLM-5.3 xhigh (Claude CLI z.ai; Devin swe-2 fallback), delegated by JunTae 2026-10-08 (model 10-14 17:09)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-05", "CAP-06"],
      "rationale": "One canonical integer rule across allocation, refund reversal and late-cash handling matches the settlement contract section 0.3 determinism principle, the FINANCE design formula and the pinned two-payee floor outcome, while treating Move resale splits as observed inputs preserves PF-C05 isolation.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "consumer": "all shadow computations"
    },
    "refund_class_inputs": {
      "status": "ADOPTED",
      "value": {"policy_version": "CAPITAL-SHADOW-REFUND-V1", "input_schema": "{claim_snapshot, R, reason_class RC<n>, evidence_ref}", "vectors_required": ["RC1 R=40000 pro-rata reversal", "RC2 R=40000 organizer-then-platform", "RC2 R=100000 must equal FIXTURE_FULL_GROSS_RECLASS", "RC3 R=40000 platform 100 percent with pool marker for excess", "RC4 R=40000 under both adjudications"], "rc5": "no standalone vector; computed only inside RU runs", "outputs": "per-line cancelled_unpaid and recovery_due deltas; recovery proposed never auto-executed"},
      "fsm_expressible": false,
      "provided_by": "GLM-5.3 xhigh (Claude CLI z.ai; Devin swe-2 fallback), delegated by JunTae 2026-10-08 (model 10-14 17:09)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-05", "CAP-06"],
      "rationale": "Single-claim bearer arithmetic is a pure function of one snapshot plus a declared class, so RC1-RC4 are shadow-computable next phase while RC5 correctly rides on the resale vectors it was defined through; golden-equality with the pinned full-reclass fixture keeps shadow and FSM agreeable.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "consumer": "shadow module next phase; fin-multi-payee-refund-proof input candidate"
    },
    "resale_unwind_scope": {
      "status": "ADOPTED",
      "value": {"policy_version": "CAPITAL-SHADOW-RESALE-V1", "triggers": ["RU1_EVENT_CANCELLED_AFTER_TRANSFER", "RU2_LISTING_CANCELLED_AFTER_PAYMENT_BEFORE_TRANSFER", "RU3_CHARGEBACK_ON_RESALE_PAYMENT_AFTER_TRANSFER"], "inputs": "declared vectors {P_p, P_r, seller_due, organizer_due, platform_due, primary claim snapshot}; chain last_amount observation only", "golden_vectors": [{"case": "premium", "holder_receives": 113000, "seller_keeps": 117000}, {"case": "discount", "holder_receives": 80000, "seller_receives": 20000, "resale_lines_reversed": 0}], "chain_walk": "none; vector schema contains no prior-trade list"},
      "fsm_expressible": false,
      "provided_by": "GLM-5.3 xhigh (Claude CLI z.ai; Devin swe-2 fallback), delegated by JunTae 2026-10-08 (model 10-14 17:09)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-06"],
      "rationale": "LATEST_TRADE_ONLY_NO_CHAIN_WALK makes all three triggers pure functions of declared inputs, and embedding the note's two worked examples as golden vectors turns the policy into a checkable artifact before any upstream FSM change is requested.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "consumer": "shadow module next phase; ps-03 and fin-multi-payee-refund-proof input candidate"
    },
    "revshare_claim_purchase_deferral": {
      "status": "ADOPTED",
      "value": {"decision": "DEFER_NEXT_PHASE", "revenue_participation": "SHADOW_DEFERRED: needs cross-claim event-set aggregation and a 90-day adjustment-window clock plus open legal-character review", "claim_purchase": "SHADOW_DEFERRED: needs a stateful slice registry enforcing (claim_id, payee) uniqueness, a second artifact beyond pure functions, plus securities and lending review", "apply_path": "both keep UNSUPPORTED_BY_PINNED_FSM", "target": "phase 2 after stateless vectors merge and a declared input schema for event sets and the registry is decided"},
      "fsm_expressible": false,
      "provided_by": "GLM-5.3 xhigh (Claude CLI z.ai; Devin swe-2 fallback), delegated by JunTae 2026-10-08 (model 10-14 17:09)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-02", "CAP-03"],
      "rationale": "Both items are decided policy but not yet honest shadow targets: they need state or clocks the pure module deliberately lacks, and premature numbers would pre-empt pending legal review; an explicit deferral with a named target phase is the ambitious-but-buildable answer.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "consumer": "shadow module phase 2"
    },
    "errata_to_settlement_note": {
      "status": "ADOPTED",
      "value": {"note_not_edited": true, "errata": ["E1: header FSM vocabulary row, fsm_expressibility_summary.meaning_of_false, section 5 mapping row and section 7 item (3): read 'policy-simulator computes shadow' as 'Capital shadow module computes shadow'; policy-simulator unsupported() stays the authoritative apply-path verdict", "E2: 'disposable copy' is one way to obtain an observed snapshot, not a requirement; declared vectors are equally valid inputs", "E3: section 6 risk on shadow/FSM divergence is mitigated by CAPITAL-SHADOW-LABELS-V1 disjoint tokens and forbidden fields"], "unchanged": "all six ADOPTED values, all fsm_expressible flags, all upstream change requests"},
      "fsm_expressible": false,
      "provided_by": "GLM-5.3 xhigh (Claude CLI z.ai; Devin swe-2 fallback), delegated by JunTae 2026-10-08 (model 10-14 17:09)",
      "date": "2026-10-14",
      "cap_rows": ["CAP-02", "CAP-03", "CAP-05", "CAP-06"],
      "rationale": "The settlement note is merged product policy; corrections belong in a dated errata here so its decision history stays intact while consumers read the reinterpreted consumer and input rules.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "consumer": "readers of CAPITAL_SETTLEMENT_POLICY.md section 7"
    }
  },
  "confirmations": {
    "capital_settlement_policy_edited": false,
    "capital_code_changed_by_this_decision": false,
    "vendor_unchanged": true,
    "fixtures_unchanged": true,
    "upstream_adoption_claimed": false,
    "production": "NOT_AUTHORIZED",
    "real_money": false
  }
}
```

## 5. 수용 기준 매핑

| 수용 기준 | 충족 위치 |
|---|---|
| `docs/decisions/CAPITAL_SHADOW_POLICY.md` 존재, ```` ```capital-decision-v1 ```` 블록이 모든 decision_item을 커버, `decision_ledger.py` 통과 | §4 하나의 fenced 블록, `entries`에 여덟 항목 전부, 각 항목 `status`·`value`·`provided_by`·`date`·`cap_rows`·`rationale`·`provisional`·`basis` 보유 |
| policy-simulator 거부 vs 노트 §7 SHADOW_NOT_APPLIED 지시 중 무엇이 우선하는지 명시해 F4 해소 | §3.1 + §4 `shadow_math_stance.prevails`: 노트 지시가 제품 의도로 유효, 거부는 적용 경로 안에서 유지, 소유자 분리로 해소 |
| RC1–RC5·RU1–RU3·수익 참여·채권 매입·잔여 현금 중 다음 단계 그림자 계산 가능 항목과 `UNSUPPORTED_BY_PINNED_FSM` 유지 항목을 명명 | §1 표·§3.5–3.7 + §4 `next_phase_shadow_scope`: 계산 가능 = RC1–RC4(RC5는 RU 안에서만)·RU1–RU3·UC1–UC4; 유보 = 수익 참여·채권 매입(`SHADOW_DEFERRED`); 다섯 항목 모두 적용 경로 판정 `UNSUPPORTED_BY_PINNED_FSM` 불변 |
| `CAPITAL_SETTLEMENT_POLICY.md` 미편집, 정정은 신규 파일의 errata | §6 E1–E3 + §4 `errata_to_settlement_note`·`confirmations.capital_settlement_policy_edited: false` |

## 6. Errata — `CAPITAL_SETTLEMENT_POLICY.md` (본문 미편집)

- **E1.** 머리말 "FSM 표현 가능성 어휘" 행, §4 `fsm_expressibility_summary.meaning_of_false`, §5 수용 매핑의 SHADOW_NOT_APPLIED 언급, §7(3)의 "policy-simulator가 … 그림자 계산" 표현은 모두 **"Capital 그림자 모듈이 그림자 계산한다"**로 읽는다. `capital/policy.py`의 `unsupported()` 행(`computed: False`, `requires: upstream FSM change`)은 적용 경로의 정확한 판정으로 그대로다.
- **E2.** "일회용 복제 장부"는 관측 스냅샷을 얻는 한 방법이다. 선언 벡터(§3.5·§3.6 스키마)도 동등한 입력이다.
- **E3.** §6 "고정 FSM과 그림자 계산의 괴리" 위험은 `CAPITAL-SHADOW-LABELS-V1`(분리된 토큰 + 금지 필드 스키마)로 완화된다. 이외 여섯 ADOPTED 값·`fsm_expressible` 플래그·upstream 변경 요청은 변경 없음.

## 7. 열린 위험

- **그림자-진실 혼동 잔여 위험**: 라벨 분리가 스키마를 지키지만, 화면·문서가 `SHADOW_NOT_APPLIED` 수치를 적용 결과로 렌더링할 위험은 소비 노드의 책임으로 남는다.
- **2단계 입력 스키마 미정**: 이벤트 청구 집합·`sim_day`·슬라이스 등록부의 선언 입력 형식이 없어 수익 참여·채권 매입 유보가 장기화될 수 있다.
- **골든 벡터와 노트 수치의 일치 의존**: RU 골든은 노트 worked example을 그대로 쓴다 — 노트가 개정되면 벡터도 함께 개정돼야 한다.
- **법적 검토 선행 유보 항목**: RC4 판정·리셀 프리미엄 고지·참여·매입의 법적 성격은 전문가 몫으로 열려 있고, 결론이 다르면 해당 벡터는 재계산된다.

## 8. 후속 작업

- **그림자 모듈 구현 노드(신규)**: `CAPITAL-SHADOW-POLICY-V1` + `CAPITAL-SETTLEMENT-POLICY-V1` JSON을 읽어 §3.2 제약 아래 RC1–RC4·RU1–RU3·UC1–UC4 벡터를 구현하고 골든 기대값 검증. 라벨 토큰·금지 필드·digest 규칙을 테스트로 고정.
- **`policy-simulator`**: 변경 없음 — `unsupported()` 출력이 적용 경로 판정으로 계속 소비된다.
- **2단계 입력 스키마 결정 노드(신규)**: 이벤트 청구 집합·조정 창 시계·슬라이스 등록부의 선언 입력 형식을 정한 뒤 수익 참여·채권 매입 그림자를 연다.
- **upstream**: `settlement-policy-deepening`·`fin-multi-payee-refund-proof`에 그림자 벡터를 입력 후보로 제출(채택 주장 없음, 영수증만이 증거).
