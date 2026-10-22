# Capital 예상신용손실 충당금 결정 — 측정 기준, 게시 시점, 트루업·환입, 가속·부도 후 처리, 3100→3200 준비금 적립 연결, 리스크 준비금 대사, 컷 범위·export 섹션

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
이 문서는 KIX-CAPITAL 저장소 안의 **시뮬레이션·제품 설계용** 결정이다. 청약이 아니고 실자금이 움직이지 않으며 production은 계속 `NOT_AUTHORIZED`다. 회계·세무 내용은 **전문가 검토 전의 작업 가정(WORKING ASSUMPTION)** 이며 자문이 아니다. `accounting_policy`는 `SYNTHETIC_UNADOPTED`로 유지하고 세무는 `NOT_BOUND`다. 어떤 upstream 계약(`fin-ledger-contract`, `fin-credit-exposure-reconciliation` 등)의 채택도 주장하지 않는다. diff는 `docs/decisions/CAPITAL_LOSS_ALLOWANCE.md` 한 파일이고, `capital/`·`tests/`·vendor 바이트·골든 digest(`tests/golden/demo.json` debit = credit = 385,000)·선행 노트의 상태 토큰은 건드리지 않는다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `loss-allowance-decision` (Decision: expected-credit-loss allowance mechanics for the COA candidate — timing, basis, reversal, reserve pool link) · deps `accounts-tax-legal-decision`, `portfolio-risk-analytics`, `coa-candidate-projection` · kind `decision` · user_merge `False` |
| 결정자 | **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)** |
| 위임 원문 | 2026-10-08 18:25 KST JunTae Park: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." |
| 결정일 | 2026-10-22 |
| 기준 | KIX-CAPITAL main `5c23989` · kix-protocol `d84cc50` (읽기 전용 `/workspace/capital-run/kixproto-ro`) · vendor pin `7481b0e16ce9b903abbffa62249bb91cd9e63cfe` 불변 |
| 읽기 범위 | supervisor pack이 허용한 경로만 읽었다. `CAPITAL_FINANCIAL_TERMS.md`(`CAPITAL-TERMS-V1`)와 COA 노트 본문은 허용 경로 밖이라 **직접 열지 않았다.** 계정 코드 `1190`/`5100`/`3100`/`3200`과 준비금 bps 네 단계(150/500/2500/10000)는 노드 명세의 인용값이며, 이 노트는 그 두 노트의 값을 **바꾸지 않고 필드명·코드로만 인용**한다. 이름·숫자가 충돌하면 선행 노트가 이기고, 충당금 산식·게시 순서·대사 술어는 이 노트가 이긴다 |
| 상태 어휘 | **ADOPTED** = 위임 범위 안의 잠정 값. **UNDETERMINED** = 값을 정할 수 없어 담당·이유만(`value: null`). 일곱 항목 모두 ADOPTED이며, 정할 수 없던 하위 항목 둘(이자 미수금의 기준 포함 여부, 상각 후 회수의 세무 처리)은 항목 안에 `null`+담당으로 적었다 |

용어: 금액은 KRW 정수(합성 단위), 날짜는 오버레이 논리 일 `sim_day`(정수), 비율은 bps다. `1190` = 선지급 익스포저 차감 충당금(contra-asset), `5100` = 신용손실비용(P&L), `3100` = 적립 원천(미처분 잉여 성격), `3200` = 적립된 손실준비금 풀. 코드의 명칭·성격은 `CAPITAL-COA-V1`이 정본이다.

## 1. 결정 요약

| item | 결정 (요지) | CAP rows | 소비 노드 / seam |
|---|---|---|---|
| `allowance_measurement_basis` | **ADOPTED.** 선지급 단위 × 단계 버킷. `allowance = floor(basis × bps / 10000)`, basis = 미상환 원금(열린 상계·회수 반영 후). 버킷 4개 `PERFORMING_T1`/`PERFORMING_T2`/`ACCELERATED`/`DEFAULTED` ↔ `CAPITAL-TERMS-V1` 준비금 bps 필드. 매 `sim_day` 틱에 **파생 뷰로 측정**, 저장 없음 | CAP-01, CAP-04 | `loss-allowance-postings`, `portfolio-risk-analytics` |
| `allowance_posting_timing` | **ADOPTED.** 게시는 **컷에서만**. 컷 = 운영자 명령 `allowance_cut(sim_day)`. 틱·상태 전이는 게시하지 않고 `allowance_stale=true`만 세움. 클로즈아웃 digest 전 컷 필수 | CAP-01, CAP-13 | `loss-allowance-postings`, `closeout-artifact` |
| `allowance_true_up_and_reversal` | **ADOPTED.** 전액 환입·재게시 없음. 선지급별 **델타 트루업**: 증가 Dr 5100 / Cr 1190, 감소 Dr 1190 / Cr 5100. 같은 날 재컷 = 델타 0 무기록. 상각 시 Dr 1190 / Cr 익스포저(충당 한도), 부족분 Dr 5100 | CAP-01, CAP-04, CAP-14 | `loss-allowance-postings` |
| `allowance_after_acceleration_and_default` | **ADOPTED.** 가속일(`M*` 확정일)부터 `ACCELERATED` 버킷, `default_sim_day`부터 `DEFAULTED`(전액). 치유 시 다음 컷에 성과 버킷 복귀. 상각 적격일 = `CAPITAL_DEFAULT_RECOVERY.md` 그대로(부도일 + 상각 대기일). 상각 후 잔액에 충당금 없음, 회수는 Cr 5100 `RECOVERY` 태그 | CAP-01, CAP-04 | `loss-allowance-postings`, `overlay-recovery-writeoff` |
| `reserve_pool_3100_3200_appropriation_link` | **ADOPTED.** 후보 장부에 **게시**(메모 아님). 컷마다 Dr 3100 / Cr 3200 (또는 역) 델타로 3200 잔액 = `GET /api/risk` `reserve.requirement_krw`. 3100 가용액 부족분은 `RESERVE_SHORTFALL` 메모. 1190과 3200은 서로 상쇄하지 않음 | CAP-01, CAP-04, CAP-20 | `loss-allowance-postings`, `portfolio-risk-analytics` |
| `recon_check_allowance_vs_risk_reserve` | **ADOPTED.** 같은 컷 스냅샷에서 `Σ1190 == reserve.requirement_krw` **그리고** `3200 == requirement − shortfall`, 허용오차 0. 결과 `RECON_OK`/`RECON_MISMATCH`/`RECON_STALE`. MISMATCH·STALE은 후보 export 섹션 `ok=false`, FSM·레거시 export는 영향 없음 | CAP-04, CAP-13, CAP-14 | `loss-allowance-postings`, `portfolio-consistent-read` |
| `cut_scope_and_export_section` | **ADOPTED.** 컷은 **포트폴리오 전체**(오버레이의 모든 선지급) 단일 `sim_day`. `cut_id = allowance-cut-{sim_day}`. COA 후보 export에 `loss_allowance` 섹션 추가, 레거시 `capital/export.py` 바이트 불변 | CAP-13, CAP-15, CAP-20 | `loss-allowance-postings`, `coa-candidate-projection`, `closeout-artifact` |

## 2. KIX 비전과의 연결

읽은 팩 경로와 적용만 적는다.

- **기록과 재생의 분리(A-4).** `/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md`는 "과거 사실 재생은 새로운 외부 실행 허가가 아니다"와 "늦은 사실은 현재 권한으로 대사한다"를 요구한다. 충당금을 틱마다 **측정은 하되 게시는 컷에서만** 하는 이유가 이것이다. 컷은 증거 가능한 단일 지점이며, 컷 사이의 전이는 재생 시 같은 값을 다시 만들 수 있는 파생 뷰로 남는다.
- **mock·비운영 범위.** `/workspace/capital-run/kixproto-ro/README.md` §3·§4는 실자금·실 PG·운영 엔드포인트를 잠그고 "정책 값은 DECISION_REQUIRED, 외부 답변 의존 값은 담당 명시 UNDETERMINED"를 요구한다. 이 노트의 모든 값은 합성 장부용이며 세무·외부 회계 입장은 담당을 적은 `null`로 남겼다.
- **골든 불변과 레거시 바이트 가드.** `docs/VALIDATION.md`(711 통과, export byte guard 수리 기록)와 `docs/CAPITAL_REQUIREMENTS_KO.md`(두 고정 핀의 범위 한정)에 따라 충당금 섹션은 후보 export에만 들어가고 레거시 export·골든 digest는 바이트 불변이다.
- **포트 seam.** `docs/SEAMS.md`의 원칙(새 노드는 새 Protocol·새 행, 어떤 행도 `ADOPTED` 아님)대로 `loss-allowance-postings`는 `AllowancePort` 행을 추가하되 `NOT_BOUND`로 둔다.
- **선행 노트 연계.** `CAPITAL_DEFAULT_RECOVERY.md`(가속 = 만기 재기준 `M*`, 상각 적격일 = `default_sim_day` + 상각 대기일, 자동 게시 없음)와 `CAPITAL_DEMO_BOOK.md`(T2 500 bps 충당 경로, 대형 액면으로 cap 발화)가 버킷 전이일과 시연 경로의 근거다. `CAPITAL_CLOSEOUT_ARTIFACT.md`의 "per-run 필드 제거한 결정론적 다이제스트" 규칙을 `loss_allowance` 섹션에도 적용한다. `CAPITAL_ACCOUNTS_TAX_LEGAL.md`의 `basis = WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW`를 회계 항목에 상속한다.

## 3. 항목별 결정

공통: `basis = PRODUCT_DECISION`, `provisional = true`, `professional_review = PENDING`, `accounting_policy = SYNTHETIC_UNADOPTED`, `tax = NOT_BOUND`. 숫자 상수는 `CAPITAL-TERMS-V1` 필드를 참조하며 괄호 값은 설명용 현재 값이다.

### 3.1 allowance_measurement_basis (CAP-01, CAP-04)

- **값.** 측정 단위는 **선지급(advance) 1건**이다. 버킷은 네 개이며 `CAPITAL-TERMS-V1`의 준비금 bps 필드에 1:1 대응한다: `PERFORMING_T1`(150) · `PERFORMING_T2`(500) · `ACCELERATED`(2500) · `DEFAULTED`(10000). 기준액 `basis_krw` = 해당 `sim_day`의 **미상환 원금**(인출액 − 상환 원금 − 확정 상계·회수 원금). 산식 `allowance_krw = floor(basis_krw × bps / 10000)`, 선지급별 내림 후 합산(합산 후 내림 아님). 측정은 **기록된 모든 `sim_day` 틱**에서 파생 뷰 `GET /api/risk` 쪽과 같은 스냅샷으로 계산하되 저장하지 않는다(게시는 §3.2).
- **하위 항목 UNDETERMINED.** 발생이자·연체가산(300 bps)·수수료 미수금의 기준액 포함 여부 — `value: null`, owner `accounts-tax-legal-decision` 후속(전문가 검토). V1은 원금만 쓴다.
- **근거.** 선지급별·내림 방식이어야 합산과 per-advance 명세가 항상 일치하고, 리스크 뷰와 장부가 같은 함수를 공유해 대사(§3.6)가 허용오차 0으로 성립한다.
- **대안.** 포트폴리오 집합 기준(등급별 합산 후 bps): 선지급 명세와 불일치 가능해 기각. 시간 경과 기반 단계 상향(DPD 모델): `CAPITAL_CLAIM_SLICE_REGISTRY.md`도 시간 기반 손상을 `null`로 남겼으므로 V1 제외.

### 3.2 allowance_posting_timing (CAP-01, CAP-13)

- **값.** 게시는 운영자 명령 **`allowance_cut(sim_day)`** 에서만 일어난다. 틱 진행·`ACCELERATED`·`DEFAULTED`·상각·상환은 게시를 만들지 않고 오버레이에 `allowance_stale: true`와 `stale_since_sim_day`를 세운다. 컷은 명령일 이전의 모든 전이를 반영하며, 컷 `sim_day`가 마지막 컷보다 작으면 `CUT_NOT_MONOTONIC` 거절. 클로즈아웃 digest(`CAPITAL_CLOSEOUT_ARTIFACT.md`)는 `allowance_stale == false`를 전제 조건으로 요구한다. 첫 컷 전에는 1190·5100·3200 잔액이 0이며 `/api/risk`만 요구액을 보여준다.
- **근거.** `CAPITAL_DEFAULT_RECOVERY.md`의 "상각 기록은 운영자 명령, 자동 게시 없음"과 같은 원칙이다. 컷 단일 지점이 A-4의 재생 경계를 만든다.
- **대안.** 틱마다 자동 게시: 분개 수가 operation 예산(`CAPITAL_DEMO_BOOK.md` ≤ 300)을 잠식하고 재생 시 순서 의존이 생겨 기각.

### 3.3 allowance_true_up_and_reversal (CAP-01, CAP-04, CAP-14)

- **값.** 컷마다 선지급별 `delta = allowance_now − allowance_posted_prev`. `delta > 0`: Dr 5100 / Cr 1190. `delta < 0`: Dr 1190 / Cr 5100 (환입도 5100을 통과, 별도 환입 계정 없음). `delta == 0`: 분개 없음. 분개 키 `(advance_id, cut_id)` 유일, 같은 날 재컷은 전부 델타 0이라 no-op(멱등). 전액 환입 후 재게시는 **금지**. 상각 명령 시: Dr 1190 / Cr 선지급 익스포저 계정 = `min(1190 잔액(해당 건), 상각액)`, 부족분 Dr 5100 / Cr 익스포저, 초과 충당은 같은 분개에서 Dr 1190 / Cr 5100으로 환입. 상각 후 해당 건의 1190 잔액은 0.
- **근거.** 델타 방식은 분개 수를 최소화하고 `OBLIGATION_CONSERVATION` 류 보존 술어(차변 = 대변)를 컷 단위로 검사할 수 있게 한다.
- **대안.** 전액 환입·재게시: 분개 2배, digest 잡음, 기각.

### 3.4 allowance_after_acceleration_and_default (CAP-01, CAP-04)

- **값.** (1) `ACCELERATED` 버킷 진입일 = `CAPITAL_DEFAULT_RECOVERY.md`의 가속 재기준일(`M*` 확정 명령일). 마진콜 치유 기간 중(`cure` 대기)은 아직 성과 버킷이며, 치유 마감 미치유로 가속되면 그날부터 `ACCELERATED`. (2) `DEFAULTED` 버킷 진입일 = `default_sim_day`, bps 10000 = 기준액 전액. (3) 치유·전액 상환으로 가속이 해제되면 다음 컷에서 성과 버킷으로 복귀하고 §3.3 델타로 환입(페널티 없음). (4) 상각 적격일·상각 명령은 선행 노트를 그대로 따르며 이 노트는 충당 소진 분개(§3.3)만 추가한다. (5) 상각 후 회수(상계·잔여 배분): Dr 현금성/익스포저 상대 / Cr 5100 `memo: RECOVERY`, 1190은 건드리지 않는다.
- **하위 항목 UNDETERMINED.** 상각 후 회수의 세무 처리(손금·익금 시점) — `value: null`, owner `accounts-tax-legal-decision` 후속, `tax = NOT_BOUND`.
- **근거.** 버킷 전이일을 선행 노트의 명령일에 묶어야 오버레이 재생으로 같은 충당금이 나온다.
- **대안.** 가속 즉시 전액 충당: `ACCELERATED` 단계(2500)의 의미가 사라지고 회수 폭포 전 손실을 과대 인식해 기각.

### 3.5 reserve_pool_3100_3200_appropriation_link (CAP-01, CAP-04, CAP-20)

- **값.** 후보 장부에 **게시한다**(메모 아님). 컷마다 `target_3200 = reserve.requirement_krw`(같은 스냅샷의 `GET /api/risk`), `appropriable = 3100 가용 잔액`, `post = min(target_3200, 3200_prev + appropriable) − 3200_prev`. `post > 0`: Dr 3100 / Cr 3200, `post < 0`(요구액 감소): Dr 3200 / Cr 3100. `target_3200 − 3200_after > 0`이면 `RESERVE_SHORTFALL` 메모 필드(금액)와 리스크 뷰 플래그. 1190(손실 인식)과 3200(준비금 적립)은 **독립 두 줄**이며 서로 상쇄·합산하지 않는다. 적립은 지급·실자금 이동이 아니고 합성 장부 내 등식 유지일 뿐이다.
- **근거.** 노드 명세의 "reserve pool link"를 메모로 두면 후보 장부가 리스크 뷰와 분리되어 대사가 무의미하다. 게시하되 3100 한도로 묶으면 부족을 숨기지 않는다.
- **대안.** 메모만: 기각(위). 3100 한도 없이 무조건 적립(음수 3100 허용): 보존 술어 위반, 기각.

### 3.6 recon_check_allowance_vs_risk_reserve (CAP-04, CAP-13, CAP-14)

- **값.** 술어는 컷 `sim_day`의 **단일 스냅샷**(portfolio-consistent read, main `cde0bc7` 노드)에서 평가한다.
  `P1: Σ_advance 1190_balance == risk.reserve.requirement_krw`
  `P2: 3200_balance == risk.reserve.requirement_krw − reserve_shortfall_krw`
  `P3: Σ debit == Σ credit` (컷 분개 집합)
  허용오차 0(동일 `floor` 함수·동일 bps 원천). 결과 코드: 셋 다 참 `RECON_OK`; `risk` 스냅샷 `sim_day` ≠ 마지막 `cut_id` 일 → `RECON_STALE`; 그 외 `RECON_MISMATCH`(어긴 술어 id와 양측 값 포함). `RECON_OK`가 아니면 후보 export 섹션 `ok=false`이고 클로즈아웃 digest 생성이 거부된다. FSM 명령·레거시 export·`/api/state`는 영향 없다.
- **근거.** 리스크 뷰와 장부가 같은 함수를 쓰므로 오차 허용은 결함 은폐다.
- **대안.** 비율 허용오차: 내림 누적 차이를 정당화할 이유가 없어 기각.

### 3.7 cut_scope_and_export_section (CAP-13, CAP-15, CAP-20)

- **값.** 컷 범위 = **포트폴리오 전체**(오버레이의 모든 선지급, 수익자·등급 필터 없음), 단일 `sim_day`. `cut_id = "allowance-cut-{sim_day}"`. 수익자별·청구별 소계는 섹션 안의 집계 필드로만 제공한다. COA 후보 export에 섹션 `loss_allowance`를 추가한다: `{format: "KIX_CAPITAL_LOSS_ALLOWANCE_V1", cut_id, sim_day, accounting_policy: "SYNTHETIC_UNADOPTED", tax: "NOT_BOUND", label: "SIMULATED", bps_source: "CAPITAL-TERMS-V1", coa_source: "CAPITAL-COA-V1", lines: [{advance_id, bucket, basis_krw, bps_field, allowance_krw, delta_krw}], totals: {allowance_1190, expense_5100_period, reserve_3200, shortfall}, recon: {code, predicates}, journal: [...]}`. 섹션 digest는 `instance_id`·벽시계 제외(CAP-15 `content_digest` 규칙). 레거시 `capital/export.py` 바이트·`tests/golden/demo.json`·`state_digest`는 **불변**이며 섹션은 후보 export 경로에만 붙는다. 새 벡터 파일은 `tests/vectors/loss_allowance.json` 후보이고 `scripts/docs_surface.py` 등록은 구현 노드가 한다.
- **근거.** 전체 컷 하나여야 P1·P2가 포트폴리오 요구액과 1:1로 맞고, 부분 컷은 `RECON_STALE` 판정을 복잡하게 만든다.
- **대안.** 수익자별 컷: 요구액 집계 시점이 어긋나 기각.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "loss-allowance-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-10-22",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "scope": "KIX-CAPITAL simulation and product design only; not an accounting policy adoption; accounting_policy SYNTHETIC_UNADOPTED; tax NOT_BOUND; no real money; production NOT_AUTHORIZED",
  "bases": {"capital_main": "5c23989", "kix_protocol": "d84cc50", "vendor_pin_commit": "7481b0e16ce9b903abbffa62249bb91cd9e63cfe"},
  "accounting_policy": "SYNTHETIC_UNADOPTED",
  "tax": "NOT_BOUND",
  "professional_review": "PENDING",
  "reference_rule": "reserve bps cited by CAPITAL-TERMS-V1 field per bucket; account codes 1190/5100/3100/3200 cited from CAPITAL-COA-V1; neither note is changed by this decision",
  "consumer": "loss-allowance-postings",
  "upstream_adoption_claimed": false,
  "entries": {
    "allowance_measurement_basis": {
      "status": "ADOPTED",
      "value": {
        "unit": "per_advance",
        "buckets": {"PERFORMING_T1": "CAPITAL-TERMS-V1.reserve_bps.t1", "PERFORMING_T2": "CAPITAL-TERMS-V1.reserve_bps.t2", "ACCELERATED": "CAPITAL-TERMS-V1.reserve_bps.accelerated", "DEFAULTED": "CAPITAL-TERMS-V1.reserve_bps.defaulted"},
        "illustrative_bps": [150, 500, 2500, 10000],
        "basis_krw": "outstanding principal after repaid, confirmed setoff and recovered principal",
        "formula": "allowance_krw = floor(basis_krw * bps / 10000) per advance, then sum",
        "measured_at": "every recorded sim_day tick as a derived view; nothing stored",
        "accrued_interest_in_basis": {"status": "UNDETERMINED", "value": null, "owner": "accounts-tax-legal-decision follow-up", "reason": "interest, late premium and fee receivables need professional review; V1 uses principal only"}
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Per-advance floor keeps the line detail and the total identical and lets the risk view and the ledger share one function so reconciliation holds with zero tolerance.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "professional_review": "PENDING",
      "owner": "loss-allowance-postings"
    },
    "allowance_posting_timing": {
      "status": "ADOPTED",
      "value": {
        "posting": "CUT_ONLY",
        "command": "allowance_cut(sim_day)",
        "between_cuts": "state transitions set allowance_stale=true and stale_since_sim_day; no journal",
        "monotonic": "cut sim_day < last cut -> CUT_NOT_MONOTONIC",
        "closeout_precondition": "allowance_stale == false",
        "before_first_cut": "1190, 5100, 3200 balances are 0; /api/risk still shows requirement"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-01", "CAP-13"],
      "rationale": "One operator cut is the evidence point A-4 asks for; replaying ticks reproduces the same derived view without order-dependent postings.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "professional_review": "PENDING",
      "owner": "loss-allowance-postings"
    },
    "allowance_true_up_and_reversal": {
      "status": "ADOPTED",
      "value": {
        "method": "DELTA_TRUE_UP",
        "increase": "Dr 5100 / Cr 1190",
        "decrease": "Dr 1190 / Cr 5100",
        "zero_delta": "no journal",
        "journal_key": "(advance_id, cut_id) unique; same-day re-cut is a no-op",
        "full_reversal_and_repost": "FORBIDDEN",
        "writeoff": "Dr 1190 / Cr advance exposure up to that advance's 1190 balance; shortfall Dr 5100 / Cr exposure; excess Dr 1190 / Cr 5100; 1190 for the advance ends at 0"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-01", "CAP-04", "CAP-14"],
      "rationale": "Delta postings minimise journal count, stay idempotent and keep debit = credit checkable per cut.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "professional_review": "PENDING",
      "owner": "loss-allowance-postings"
    },
    "allowance_after_acceleration_and_default": {
      "status": "ADOPTED",
      "value": {
        "accelerated_from": "acceleration rebase command day (M* fixed) per CAPITAL_DEFAULT_RECOVERY.md; cure window days stay in performing bucket",
        "defaulted_from": "default_sim_day; bucket DEFAULTED = full basis",
        "cure": "next cut returns to performing bucket and reverses by delta; no penalty",
        "writeoff_day": "unchanged: CAPITAL_DEFAULT_RECOVERY.md writeoff_trigger_and_day_basis",
        "after_writeoff": "no allowance on written-off balance; recoveries Cr 5100 memo RECOVERY; 1190 untouched",
        "tax_on_recovery": {"status": "UNDETERMINED", "value": null, "owner": "accounts-tax-legal-decision follow-up", "reason": "tax NOT_BOUND"}
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-01", "CAP-04"],
      "rationale": "Binding bucket transitions to the prior note's command days makes overlay replay reproduce the same allowance.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "professional_review": "PENDING",
      "owner": "loss-allowance-postings"
    },
    "reserve_pool_3100_3200_appropriation_link": {
      "status": "ADOPTED",
      "value": {
        "mode": "POSTED_IN_CANDIDATE",
        "target_3200": "GET /api/risk reserve.requirement_krw at the same cut snapshot",
        "post": "min(target_3200, 3200_prev + appropriable_3100) - 3200_prev; positive Dr 3100 / Cr 3200, negative Dr 3200 / Cr 3100",
        "shortfall": "RESERVE_SHORTFALL memo amount when target exceeds appropriable; 3100 never negative",
        "independence": "1190 and 3200 are separate lines, never netted",
        "funds": "no payment, no real money"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-01", "CAP-04", "CAP-20"],
      "rationale": "A memo-only pool would detach the candidate ledger from the risk view; posting it bounded by 3100 keeps conservation and exposes shortfall honestly.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "professional_review": "PENDING",
      "owner": "loss-allowance-postings"
    },
    "recon_check_allowance_vs_risk_reserve": {
      "status": "ADOPTED",
      "value": {
        "snapshot": "single portfolio-consistent read at cut sim_day",
        "P1": "sum(1190_balance) == risk.reserve.requirement_krw",
        "P2": "3200_balance == risk.reserve.requirement_krw - reserve_shortfall_krw",
        "P3": "sum(debit) == sum(credit) over the cut journal",
        "tolerance_krw": 0,
        "codes": ["RECON_OK", "RECON_STALE", "RECON_MISMATCH"],
        "stale_rule": "risk snapshot sim_day != last cut_id day",
        "on_failure": "candidate export section ok=false; closeout digest refused; FSM, legacy export and /api/state unaffected"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-04", "CAP-13", "CAP-14"],
      "rationale": "Ledger and risk view share one function and one bps source, so any tolerance would only hide defects.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "professional_review": "PENDING",
      "owner": "loss-allowance-postings"
    },
    "cut_scope_and_export_section": {
      "status": "ADOPTED",
      "value": {
        "scope": "whole portfolio at one sim_day; no beneficiary or tier filter",
        "cut_id": "allowance-cut-{sim_day}",
        "export_section": "loss_allowance",
        "format": "KIX_CAPITAL_LOSS_ALLOWANCE_V1",
        "fields": ["cut_id", "sim_day", "accounting_policy", "tax", "label", "bps_source", "coa_source", "lines", "totals", "recon", "journal"],
        "digest": "excludes instance_id and wall-clock per CAP-15 content_digest rule",
        "legacy_export": "capital/export.py bytes, tests/golden/demo.json and state_digest BYTE_IDENTICAL",
        "vector_candidate": "tests/vectors/loss_allowance.json; docs_surface registration by the implementing node"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-22",
      "cap_rows": ["CAP-13", "CAP-15", "CAP-20"],
      "rationale": "One whole-portfolio cut matches the requirement one-to-one and keeps the stale rule simple; the section lives only on the candidate path so the byte guard stays green.",
      "provisional": true,
      "basis": "PRODUCT_DECISION",
      "professional_review": "PENDING",
      "owner": "loss-allowance-postings"
    }
  }
}
```

## 5. 수용 기준 매핑

| 수용 기준 | 충족 위치 |
|---|---|
| `docs/decisions/CAPITAL_LOSS_ALLOWANCE.md`에 `capital-decision-v1` 블록 하나, `decision_ledger.py`·`GET /api/decisions` | §4 블록 하나뿐. 일곱 항목 모두 `status`·`value`·`provided_by`·ISO `date`·`cap_rows`·`rationale`·`basis` 보유 |
| `CAPITAL-TERMS-V1` bps(150/500/2500/10000)·`CAPITAL-COA-V1` 1190/5100/3100/3200 재사용, 두 노트 불변 | 블록 `reference_rule`, §3.1 필드명 인용, `illustrative_bps`는 설명용. 두 노트의 diff 없음 |
| 각 항목 ADOPTED/UNDETERMINED + owner + 전문가 검토 플래그, `accounting_policy = SYNTHETIC_UNADOPTED` | 각 entry `owner`·`professional_review: PENDING`; 하위 `null` 둘은 owner 명시. 블록 최상위 `accounting_policy`·`tax` |
| `loss-allowance-postings` 소비자 명시, `scripts/decision_bindings.py --check` | 블록 `consumer`, §1 표 소비 열. 실행 확인은 supervisor·독립 리뷰어가 한다(이 결정자는 읽기 전용) |

## 6. Open risks

- **선행 노트 미열람.** `CAPITAL-TERMS-V1` 준비금 bps 필드의 실제 키 이름과 `CAPITAL-COA-V1` 계정 명칭을 직접 확인하지 못했다. 구현 노드가 필드명을 노트에서 로드하며, 불일치 시 선행 노트가 이긴다.
- **내림 누적.** 선지급별 내림이라 포트폴리오 집합 계산과 1 KRW 단위 차이가 날 수 있다. 리스크 뷰도 같은 per-advance 함수를 써야 `tolerance 0`이 성립한다.
- **3100 가용 잔액의 정의.** 합성 북에 3100 잔액이 0이면 컷마다 `RESERVE_SHORTFALL`이 전액으로 뜬다. 이는 결함이 아니라 정직한 표기이며, 초기 3100 seed 값은 `demo-book-seed` 류 노드가 정한다.
- **치유 환입의 손익 변동.** 가속↔치유 반복 시 5100이 컷마다 흔들린다. 시연 북에서는 의도된 경로지만 실제 회계 처리는 전문가 검토 대상이다.
- **DPD·시간 기반 단계 부재.** V1은 명령 기반 전이만 쓴다. 연체 일수 기반 상향은 `CAPITAL_CLAIM_SLICE_REGISTRY.md`의 `null`과 함께 후속이다.

## 7. 후속 작업

- `loss-allowance-postings`(구현 노드): `AllowancePort` Protocol + `docs/SEAMS.md` 행(`NOT_BOUND`), `allowance_cut` 명령, 후보 export `loss_allowance` 섹션, `tests/vectors/loss_allowance.json`과 `scripts/docs_surface.py` 등록, 레거시 export 바이트 가드 통과 증거.
- `portfolio-risk-analytics`: `reserve.requirement_krw`를 같은 per-advance 내림 함수로 계산하고 `reserve_shortfall_krw`·스냅샷 `sim_day`를 노출.
- `closeout-artifact`: `allowance_stale == false`·`RECON_OK` 전제 조건 추가.
- `accounts-tax-legal-decision` 후속: 이자 미수금 기준 포함 여부, 상각 후 회수 세무 처리(전문가 검토).
- upstream 입력 후보: `fin-credit-exposure-reconciliation`·`fin-ledger-contract`에 P1–P3 술어와 섹션 포맷 전달. upstream 노드 완료 표시 없음.
