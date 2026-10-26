# Capital 기대신용손실 충당금 결정 — 측정·게시·환입·준비금·대사

**PROVISIONAL PRODUCT DECISION — 시뮬레이션·제품 설계 전용.** 실자금과 청약은 없고 production은 `NOT_AUTHORIZED`다. `accounting_policy = SYNTHETIC_UNADOPTED`, `tax = NOT_BOUND`, `legal = NOT_BOUND`, `operating_ledger = NOT_BOUND`를 유지한다. 회계·세무 내용은 전문가 검토 전 작업 가정이며 upstream 채택이나 운영 회계 정책 채택을 주장하지 않는다.

**지정 결정자/기존 결정 귀속:** Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07). **결정일:** 2026-10-26. **기준:** Capital main `aab0a73`, kix-protocol `58dd527`.

**개정 실행 이력:** 이번 개정은 Codex가 작성했다. Claude CLI의 Sonnet 3회 및 Fable 대체 1회는 모두 `Not logged in`으로 추론 전에 실패했다. 아래 `decided_by`·`provided_by`는 요청된 기존 위임 표기를 보존하며 이번 실행 모델의 증명이 아니다.

정책 근거는 supervisor pack과 제공된 기존 결정문이다. 잘린 선행 파일의 나머지, TERMS 원문, risk·COA 코드는 열지 않았다. 개정 확인에 사용한 파일은 이 노트와 추가 허용된 `tests/decision_bindings.json`이며, 명시된 검증 명령을 실행했다. 변경 허용 범위는 이 노트·바인딩·`tests/vectors/pack/`이고 이번에 새 벡터는 만들지 않는다. 일곱 항목의 `ADOPTED`는 잠정 제품값이며 구현 완료가 아니다. 모든 항목에 담당 역할과 전문가 검토 플래그를 둔다.

## 1. 결정 요약

| item | decision | CAP rows | consumer |
|---|---|---|---|
| `allowance_measurement_basis` | ADOPTED: 선지급별 원금 × 단계 bps, 건별 내림 | CAP-04, CAP-13 | `loss-allowance-postings` |
| `allowance_posting_timing` | ADOPTED: 사건·파생 전이점 true-up을 cut까지 재생 | CAP-04, CAP-13, CAP-14 | `loss-allowance-postings` |
| `allowance_true_up_and_reversal` | ADOPTED: 1190/5100 차액만 게시; 종결 환입 | CAP-13 | `loss-allowance-postings` |
| `allowance_after_acceleration_and_default` | ADOPTED: 가속 2,500, 부도 명령 10,000; 상각 전 충당금 해제 | CAP-04, CAP-13 | `loss-allowance-postings` |
| `reserve_pool_3100_3200_appropriation_link` | ADOPTED: 3100→3200 게시 없이 준비금 메모 | CAP-04, CAP-13 | `loss-allowance-postings` |
| `recon_check_allowance_vs_risk_reserve` | ADOPTED: 동일 cut의 Σ1190와 risk 필요액 정확 일치 | CAP-04, CAP-13, CAP-14 | `loss-allowance-postings` |
| `cut_scope_and_export_section` | ADOPTED: 이중 digest·논리일·전체 KRW 장부; 후보 표면만 노출 | CAP-13, CAP-14, CAP-15 | `loss-allowance-postings` |

## 2. KIX 비전 연결

[CAPITAL_REQUIREMENTS_KO.md](../CAPITAL_REQUIREMENTS_KO.md)의 pack 발췌는 로컬 구현 권한과 운영·upstream 권한을 구분한다. 이 결정은 감사 가능한 후보 장부를 진전시키며 그 권한 경계를 유지한다. [SEAMS.md](../SEAMS.md)의 로컬 대역은 실제 채택 영수증이 아니므로 공용 측정 함수나 대사 통과도 upstream 채택으로 승격하지 않는다.

[CAPITAL_ACCOUNTS_TAX_LEGAL.md](CAPITAL_ACCOUNTS_TAX_LEGAL.md)의 제공 발췌는 회계 작업 가정과 합성 투영의 경계를 정한다. COA 코드·bps·선행 분개 세부는 supervisor가 제공한 기존 결정문과 수용 기준의 인용을 사용했다. [CAPITAL_DEFAULT_RECOVERY.md](CAPITAL_DEFAULT_RECOVERY.md)의 pack 발췌에서 확인되는 `M*`와 부도 명령일 기준 상각 적격성을 유지한다. 이 결정의 목표는 동일 사실·동일 정책 버전에서 risk, 후보 장부, 감사 행이 원 단위로 일치하는 것이다.

## 3. 항목별 결정

### 3.1 allowance_measurement_basis

`level(a,d) = floor(effective_principal(a,d) × bucket_bps / 10000)`로 정한다. KRW 정수이며 반올림 나머지를 이월하지 않는다. 합산한 원금에 한 번 비율을 적용하지 않는다. 우선순위는 미인출·상각·종결의 0 기초, DEFAULTED, PAST_DUE_OR_ACCELERATED, T2_PERFORMING, T1_PERFORMING이다. 활성 버킷의 현재 설명값은 각각 10,000 / 2,500 / 500 / 150 bps다.

비율의 정본은 `CAPITAL-TERMS-V1.reserve.provision_bps_of_outstanding`이며 숫자를 별도 설정으로 복제하지 않는다. 계정은 `CAPITAL-COA-V1`의 1190·5100·3100·3200을 재사용한다. 직접 읽지 못한 버킷 대응은 기존 제공문에 근거한 제품 매핑이며 TERMS와 충돌하면 TERMS가 우선한다. 충돌은 표시하고 소비자가 정합시켜야 하며 임의 기본값으로 계산하지 않는다.

실효 원금은 FSM outstanding에서 FSM에 아직 반영되지 않은 오버레이 원금 회수·상각만 차감한다. 이미 반영된 상환을 다시 빼지 않는다. 1110 미수 이자와 9700 메모는 제외한다. 음수 기초·중복 차감은 측정 실패이며 0으로 숨기지 않는다. 등급은 인출 당시 기록된 등급으로 고정한다. 등급 증거가 없으면 `NOT_BOUND`이며 T1로 추정하지 않는다.

### 3.2 allowance_posting_timing

매 논리일 틱이나 보고서 요청마다 게시하지 않는다. 인출·상환·가속 마커·부도 명령·회수·상각·종결과 만기 다음 날 `M*+1`을 게시점으로 정하고 cut까지 접는다. 시계가 여러 날 건너뛰어도 파생 전이점을 누락하지 않는다. cut 요청은 순수 재계산이며 FSM이나 오버레이에 새 사건을 쓰지 않는다.

같은 날은 기존 선지급의 시작일 파생 전이를 먼저 적용하고, 실제 사건은 원장 순서와 오버레이 anchor·sequence로 정렬한다. 같은 anchor의 오버레이 사건을 합치지 않는다. 파생 id는 `STAGE_TRANSITION:<advance_id>:<sim_day>`, 실제 사건은 원 operation id이며 분개 leg를 별도로 구분한다. 필요한 순서 증거가 없으면 재생을 실패시킨다.

늦은 사실은 기록된 게시점에서 반영하고 유효일은 별도 증거로 보존한다. 이미 발행한 과거 cut을 재작성하지 않는다. 동일 cut·정책 버전은 동일 분개열을 낸다. 시계 틱만 추가되어 원본 digest가 달라져도 경제 사건열이 같으면 금액·단계 전이열은 같아야 한다.

### 3.3 allowance_true_up_and_reversal

`Δ = level − carried_1190`이다. 양수면 `Dr 5100 / Cr 1190`, 음수면 `Dr 1190 / Cr 5100`, 0이면 무분개다. 전액 환입 후 재게시는 기각한다. 종결은 잔액을 한 번 해제한다. 선지급·등급·전후 버킷·terms/chart 버전·source_cut·sim_day·operation_id·leg를 분개에 남긴다.

**보존식 정정:** `기말1190 = 기초1190 + 충당금 관련 5100 차변순액`. 전 수명 기초가 0이면 `Σ5100 순액 = Σ1190`이다. 상각 해제는 이미 5100 대변에 들어가므로 해제액을 우변에 다시 더하지 않는다. 기존 초안의 `Σ1190 + Σ상각해제` 식은 폐기한다. 1190은 대변 잔액 또는 0이고 각 선지급의 실효 원금을 초과하지 않는다.

### 3.4 allowance_after_acceleration_and_default

기록된 가속 마커 또는 `M*+1` 중 먼저 도달한 게시점부터 2,500 버킷이다. 부도 명령일 `D`부터 10,000 버킷으로 이동한다. 적격일 경과만으로 자동 부도시키지 않는다. 미실행 부도 명령은 경고로 표시하며 그동안 연체 버킷을 유지한다. 가속 철회는 도입하지 않는다.

부도 뒤 원금 회수는 실효 원금 감소와 동시에 true-up한다. 상각은 선행 결정의 `D + TERMS 상각대기일` 적격성과 기록된 운영자 명령을 따른다. `UNBUILT_V1`에서는 해당 충당금 전액을 `Dr 1190 / Cr 5100`으로 한 번 해제한 뒤 기존 `Dr 5200 / Cr 1100` 원금 상각을 유지한다. 일반 true-up과 별도 상각 해제를 중복 실행하지 않는다. 상각 후 기초는 0이며 늦은 회수 `Dr 1000 / Cr 4300`은 충당금을 재생성하지 않는다.

예시: T1 원금 100,000,000에서 level은 1,500,000. 원금 40,000,000 상환 후 900,000, 가속 후 15,000,000, 부도 명령 후 60,000,000, 원금 10,000,000 회수 후 50,000,000이다. 상각 때 50,000,000을 해제하고 같은 원금을 5200에 게시한다. 전 수명 5100 순액은 0, 1190은 0, 5200은 50,000,000이다. 여러 건의 장부에서는 `5100 순액 + 원금상각5200 = 기말1190 + 누적상각원금`이며 4300 회수이익은 이 항등식 밖이다.

### 3.5 reserve_pool_3100_3200_appropriation_link

`RESERVE_POOL_MEMO_V1`을 채택한다. `appropriation_target_krw = Σ1190`, 이 후보에서 인식한 `funded_krw = 0`, `shortfall_krw = target`, `status = MEMO_NOT_POSTED`다. 0은 후보가 인식한 재원이며 외부 준비금 존재 여부를 단정하지 않는다.

`Dr 3100 / Cr 3200`은 게시하지 않는다. 1190은 차감 자산이지 현금 준비금이 아니다. 폭포 ③ `LOSS_RESERVE`는 `NOT_BOUND`, `absorbed_krw = 0`을 유지한다. 실제 가용 3100 잔액 증거, 3200 분류의 전문가 검토, 별도 준비금 바인딩 결정·버전 구현이 모두 있어야 적립 게시로 전환한다. 이 노트는 미래 이용형 상각을 현재 승인하지 않는다.

### 3.6 recon_check_allowance_vs_risk_reserve

후보 검사 `allowance_vs_risk_reserve`는 같은 cut·대상 집합·정책 버전에서 `Σ1190 대변잔액 == GET /api/risk reserve.requirement_krw`를 검사한다. 허용 오차는 0이다. `MATCH`, `MISMATCH`, `CUT_MISMATCH`, 필수 증거 부재의 `NOT_BOUND`를 구분하며 마지막 셋은 통과가 아니다.

차이는 후보 금액 minus risk 금액으로 표시하고 advance_id·버킷·실효 원금·bps·level·carried를 제공한다. 공용 bucket/level 함수와 §3.3 보존식을 사용한다. 공용 코드의 같은 오류가 양쪽에 나타날 수 있으므로 독립 손계산 벡터로도 검증한다. risk가 다르면 근거를 대조해 양쪽을 정합시키며 이 노트만으로 선행 정책을 덮어쓰지 않는다. V1 대사와 export 검사는 그대로 둔다.

### 3.7 cut_scope_and_export_section

cut은 `{f04_state_digest, overlay_digest, overlay_sim_day}`이고 별도 비교 문맥에 terms/chart/allowance-policy 버전을 넣는다. 두 원본 digest가 포함한 사실만 사용한다. 과거 원본을 재구성할 수 없으면 역사 cut은 `NOT_BOUND`다. 최신 상태를 과거 날짜로 다시 표시하지 않는다.

KRW AssetSpec 하나와 해당 cut 장부의 모든 advance_id를 포함한다. 미인출·종결·상각 건도 0 행으로 남긴다. 서로 다른 cut을 합치거나 현재 위험 잔액과 과거 후보 장부를 비교하지 않는다. 후보 `allowance` 블록·준비금 메모·후보 대사에만 노출하고 `SIMULATED`, `policy_adopted=false`를 표시한다. `NOT_IN_EXPORT_V1`이며 기존 export 구성·서명 경계·digest 계산을 변경하지 않는다. 미래 export 확대는 별도 버전 결정이다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "loss-allowance-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-10-26",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "bases": {
    "capital_main": "aab0a73",
    "kix_protocol": "58dd527",
    "terms_version": "CAPITAL-TERMS-V1",
    "chart_version": "CAPITAL-COA-V1"
  },
  "accounting_policy": "SYNTHETIC_UNADOPTED",
  "tax": "NOT_BOUND",
  "consumers": ["loss-allowance-postings"],
  "revision_execution": {
    "editor": "Codex",
    "requested_cli": "Sonnet three attempts, then Fable one attempt: all failed before inference; Not logged in",
    "attribution": "decided_by and provided_by preserve the supplied delegation attribution, not proof of this revision model execution"
  },
  "entries": {
    "allowance_measurement_basis": {
      "status": "ADOPTED",
      "value": {
        "unit": "advance_id",
        "formula": "floor(effective_principal * bucket_bps / 10000)",
        "bps_ref": "CAPITAL-TERMS-V1.reserve.provision_bps_of_outstanding",
        "bucket_order": ["UNFUNDED_OR_WRITTEN_OFF_OR_CLOSED: zero", "DEFAULTED: 10000", "PAST_DUE_OR_ACCELERATED: 2500", "T2_PERFORMING: 500", "T1_PERFORMING: 150"],
        "bps_literals": "documentation snapshots only; resolve adopted terms at runtime",
        "principal": "FSM outstanding less overlay principal recoveries and write-offs not already reflected in FSM; exclude 1110 and 9700",
        "tier": "recorded draw tier; missing or contradictory evidence -> NOT_BOUND, never default T1",
        "invalid_basis": "negative or double-counted principal -> failed measurement, never clamp to zero"
      },
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-26",
      "cap_rows": ["CAP-04", "CAP-13"],
      "rationale": "Per-advance principal levels preserve drill-down and use the existing reserve schedule.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "allowance_posting_timing": {
      "status": "ADOPTED",
      "value": {
        "mode": "EVENT_DRIVEN_POSTING_POINTS_FOLDED_TO_CUT",
        "points": ["draw", "repayment", "acceleration marker", "default command", "RECOVERY", "WRITEOFF", "close", "derived maturity+1 transition"],
        "order": "sim_day; derived opening-day transition for existing advances; source journal order with overlay anchor and overlay sequence tie-break",
        "operation_id": "source operation id; derived STAGE_TRANSITION:<advance_id>:<sim_day>",
        "late_fact": "apply when recorded, retain effective date as evidence; never rewrite an earlier cut",
        "writes": "derived candidate postings only; no overlay or FSM writes",
        "determinism": "same cut and policy versions -> same sequence; clock-only ticks add no posting"
      },
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-26",
      "cap_rows": ["CAP-04", "CAP-13", "CAP-14"],
      "rationale": "Event replay retains stage transitions across clock jumps without request-dependent postings.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "allowance_true_up_and_reversal": {
      "status": "ADOPTED",
      "value": {
        "delta": "target level minus carried credit balance of 1190",
        "increase": "Dr 5100 / Cr 1190",
        "decrease": "Dr 1190 / Cr 5100",
        "zero": "no posting",
        "close": "release remaining balance once",
        "roll_forward": "closing 1190 = opening 1190 + allowance-related net Dr 5100, including write-off release credits",
        "full_life": "zero opening -> allowance-related net 5100 = closing 1190; do not add write-off releases again",
        "dimensions": ["advance_id", "tier", "bucket_from", "bucket_to", "terms_version", "chart_version", "source_cut", "sim_day", "operation_id", "leg"]
      },
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-26",
      "cap_rows": ["CAP-13"],
      "rationale": "Delta true-up avoids gross posting inflation; the corrected identity agrees with release-before-write-off.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "allowance_after_acceleration_and_default": {
      "status": "ADOPTED",
      "value": {
        "acceleration": "2500 bucket from recorded acceleration marker or maturity+1, whichever first; no reversal of acceleration",
        "default": "10000 bucket from recorded default command D; eligibility alone does not default",
        "recovery": "reduce principal and true-up at recorded recovery; count each principal reduction once",
        "writeoff": "UNBUILT_V1: release carried allowance Dr 1190 / Cr 5100 once, then retain Dr 5200 / Cr 1100 for written-off principal",
        "writeoff_day": "existing default-recovery eligibility from D plus terms waiting period; recorded operator command required",
        "after_writeoff": "zero allowance; late recovery retains Dr 1000 / Cr 4300 and does not recreate allowance",
        "identity": "full-life allowance-related net 5100 + principal-writeoff 5200 = closing 1190 + cumulative principal written off; excludes 4300 recoveries"
      },
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-26",
      "cap_rows": ["CAP-04", "CAP-13"],
      "rationale": "Command dates preserve prior default mechanics; release and write-off must not recognize the same loss twice.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "reserve_pool_3100_3200_appropriation_link": {
      "status": "ADOPTED",
      "value": {
        "mode": "RESERVE_POOL_MEMO_V1",
        "post_3100_to_3200": false,
        "memo": {
          "appropriation_target_krw": "sum 1190 credit balances",
          "funded_krw": 0,
          "shortfall_krw": "target",
          "status": "MEMO_NOT_POSTED"
        },
        "funding_source_ref": "CAPITAL-TERMS-V1.reserve.funding_source -> 3100",
        "waterfall": "LOSS_RESERVE NOT_BOUND; absorbed_krw 0",
        "future_gate": ["evidenced available 3100 balance", "professional review of 3200 classification", "separate reserve-binding decision and versioned implementation"]
      },
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-26",
      "cap_rows": ["CAP-04", "CAP-13"],
      "rationale": "A contra-asset allowance is not funded cash; memo treatment avoids inventing reserve resources.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "recon_check_allowance_vs_risk_reserve": {
      "status": "ADOPTED",
      "value": {
        "check_id": "allowance_vs_risk_reserve",
        "predicate": "same complete cut, population, terms and chart versions AND sum 1190 credit balances == GET /api/risk reserve.requirement_krw",
        "tolerance_krw": 0,
        "outcomes": ["MATCH", "MISMATCH", "CUT_MISMATCH", "NOT_BOUND"],
        "missing_evidence": "NOT_BOUND, never zero or MATCH",
        "delta_krw": "candidate allowance minus risk requirement",
        "per_advance": ["advance_id", "bucket", "effective_principal", "bps", "level", "carried"],
        "auxiliary": ["0 <= 1190(a) <= effective_principal(a)", "closing 1190 = opening 1190 + allowance-related net 5100"],
        "shared_function": "risk and candidate share bucket/level; independent hand-calculated vectors test correctness"
      },
      "owner": "Capital Reconciliation Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-26",
      "cap_rows": ["CAP-04", "CAP-13", "CAP-14"],
      "rationale": "Exact equality proves reconciliation only at comparable cuts; common code still requires independent vectors.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "cut_scope_and_export_section": {
      "status": "ADOPTED",
      "value": {
        "cut": ["f04_state_digest", "overlay_digest", "overlay_sim_day"],
        "policy_context": ["terms_version", "chart_version", "allowance_policy_version"],
        "population": "all advance_id at the cut, one KRW AssetSpec; unfunded, closed and written-off remain zero rows",
        "history": "use only facts included in both source digests; unavailable historical cut -> NOT_BOUND",
        "surfaces": ["candidate allowance block", "candidate reconciliation", "reserve_pool memo"],
        "export": "NOT_IN_EXPORT_V1; legacy export code, sections and existing digest calculation unchanged",
        "labels": {
          "accounting_policy": "SYNTHETIC_UNADOPTED",
          "tax": "NOT_BOUND",
          "policy_adopted": false,
          "mode": "SIMULATED"
        }
      },
      "owner": "Capital Accounting Policy Owner",
      "professional_review_required": true,
      "consumer": "loss-allowance-postings",
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-26",
      "cap_rows": ["CAP-13", "CAP-14", "CAP-15"],
      "rationale": "A complete source cut and version context bound reproducibility without expanding legacy exports.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

- 이 노트에는 결정 블록 하나와 일곱 ADOPTED 항목이 있다. 모든 항목에 owner, professional_review_required, consumer가 있으며 회계·세무 라벨을 유지한다.
- 현재 worktree의 `tests/decision_bindings.json`에는 이미 이 결정의 일곱 행이 있다. 모두 `PENDING_CONSUMER`, `consumer_node: loss-allowance-postings`, 이유와 기존 module anchor를 갖춘다. 측정은 `capital/risk.py`, 대사는 `capital/recon.py`, 나머지 다섯 항목은 `capital/coa.py`를 가리킨다. 중복 행을 추가하지 않는다. anchor는 구현 증거가 아니다.
- 2026-10-26 `python3 scripts/decision_bindings.py --check`는 종료 0과 `decision bindings ok: declared references only; pending anchors are not implementation`을 반환했다. 따라서 첫 blocking finding의 누락 상태는 현재 worktree에서 재현되지 않는다.
- `python3 scripts/decision_ledger.py`는 종료 0으로 이 노트와 일곱 `=ADOPTED` 항목을 출력했다. 현재 체크아웃에서 추가 CAP_COVERAGE 편집 없이 색인되는 것을 확인했다. coverage 파일 자체는 읽거나 수정하지 않았으며 모든 미등록 노트에 대한 일반 동작을 추정하지 않는다.
- `GET /api/decisions` HTTP 호출은 이번에 검증하지 않았다. 색인 성공을 HTTP 검증 성공으로 바꾸어 적지 않는다. endpoint 노출의 직접 확인은 남은 수용 검증이다. CLI 모델 실행 실패도 위에 별도로 기록했다.

## 6. Open risks

TERMS 버킷 매핑·risk 계산·COA 세부 구현은 직접 확인하지 못했다. 충돌·증거 부재는 소비자가 NOT_BOUND 또는 실패로 드러내야 한다. 제품 버킷은 규정상 ECL 단계 적합성을 주장하지 않는다. 원금 전용 측정, 5200 표시, 3200 분류와 세무 처리의 전문 검토는 남는다. HTTP 노출은 미검증이며 운영·upstream 승인 영수증은 없다.

## 7. 후속 작업

`loss-allowance-postings`가 공용 측정 함수, 사건 폴드, 환입·상각 순서, 준비금 메모와 대사를 구현한다. `portfolio-risk-analytics`는 같은 cut·버전 문맥을 제공하고 `coa-payment-writeoff-postings`는 원금 중복 차감과 해제 중복을 막는다. 소비 검증 후에만 PENDING_CONSUMER 바인딩을 갱신한다.

검증에는 T1/T2, 내림 경계, 같은 날 복수 사건, 시계 점프, 늦은 회수, 부도 명령 지연, 상각 한 번 해제, 반복 조회, cut 불일치·증거 누락을 포함한다. 새 벡터의 향후 구현에서는 저장소 규칙에 따른 docs_surface 등록·README needle과 `python3 scripts/docs_surface.py --check`를 함께 수행한다. 이번 문서 개정은 기존 export·선행 정책·vendor·골든을 변경하지 않는다.
