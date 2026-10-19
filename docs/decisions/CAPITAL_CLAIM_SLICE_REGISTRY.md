# Capital 클레임 슬라이스 레지스트리 결정 — 저장 위치, 유일성, 공유 한도, 차입기초 이중사용 방지, 홀더 우선, 손상·소구

**상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
이 문서는 KIX-CAPITAL 저장소 안의 **시뮬레이션·제품 설계용** 결정이다. 청약이 아니고 실자금이 움직이지 않으며 production은 계속 `NOT_AUTHORIZED`다. 청약 라벨은 `SIMULATION_ONLY_NOT_OFFERED_V1`로 유지한다. 제3자 홀더와 토큰화 슬라이스는 `NOT_ADOPTED`다. 법무·회계 내용(소구 매입의 성격, 상계 효력, 도산 시 우선순위)은 **전문가 검토 전의 작업 가정**이며 자문이 아니다. 어떤 upstream 계약의 채택도 주장하지 않는다. diff는 `docs/decisions/CAPITAL_CLAIM_SLICE_REGISTRY.md` 한 파일이다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `claim-slice-registry-decision` (Decision: shadow claim-slice registry — storage, uniqueness, shared caps and borrowing-base guard) · deps `shadow-policy-decision`, `settlement-policy-decision`, `overlay-state-decision`, `financial-terms-decision` · kind `decision` · user_merge `False` |
| 결정자 | **Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)** |
| 위임 원문 | 2026-10-08 18:25 KST JunTae Park: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." |
| 결정일 | 2026-10-18 |
| 기준 | KIX-CAPITAL main `5ec4c95` · kix-protocol `9eb6b9f` (읽기 전용 `/workspace/capital-run/kixproto-ro`) |
| 읽기 범위 | supervisor pack이 허용한 경로만 읽었다. 선행 네 노트(`CAPITAL_SHADOW_POLICY.md`, `CAPITAL_SETTLEMENT_POLICY.md`, `CAPITAL_OVERLAY_STATE.md`, `CAPITAL_FINANCIAL_TERMS.md`)는 허용 경로 밖이라 **이 결정자가 직접 열지 않았다.** 필드·코드 이름은 허용된 노트(`CAPITAL_DEFAULT_RECOVERY.md`, `CAPITAL_DEMO_BOOK.md`, `CAPITAL_ACCOUNTS_TAX_LEGAL.md`)의 인용과, 개정 라운드의 검토자 발췌(오버레이 엔트리 형태 `overlay_id`/`kind`/`payload`, U5 정의, TERMS의 소구 문구와 `fsm_expressible: false` 표기)로만 참조한다. 검토자 발췌는 2차 정보다. **이름·숫자가 충돌하면 선행 노트가 이기고, 레지스트리 구조와 순서 규칙은 이 노트가 이긴다.** |
| 한도 출처 규칙 | 한도·비율·임계값 숫자를 복사하지 않는다. `CAPITAL-TERMS-V1` `underwriting_depth` 필드명(`single_advance_cap_krw`, `beneficiary_aggregate_cap_krw`, `portfolio_cap_krw`, `two_person_threshold_krw`)으로만 인용한다. |
| 상태 어휘 | **ADOPTED** = 위임 범위 안의 잠정 값. **UNDETERMINED** = 값을 정할 수 없어 이유만(`value: null`). 열 항목 모두 ADOPTED이며, 정할 수 없던 하위 항목 둘(시간 기반 손상, 슬라이스 상각)은 해당 항목 안에 `null`+이유로 적었다. |
| 개정 | 리뷰 라운드 1: (1) `shared_cap_accounting.provided_by`의 오기("2026-10-18 placeholder")를 표준 위임 문구로 바로잡았다. (2) 엔트리 형태를 채택된 오버레이 형태(`overlay_id`/`kind`/`payload`)로 맞췄다. (3) U5 정의와의 일치를 적었다. (4) 고정 FSM으로 표현 불가(`fsm_expressible: false`) 표기를 더했다. (5) TERMS의 소구 문구와의 좁힘 차이를 §3.6과 §6에 적었다. |

## 1. 결정 요약

| item | 결정 (요지) | CAP rows | 소비 노드 / seam |
|---|---|---|---|
| `registry_storage_location` | **ADOPTED.** 오버레이 저널 안의 **새 섹션** `state.claim_slices`(빈 = 키 부재, `overlay_schema` 1 유지). 엔트리 6종 `SLICE_PROPOSE/OPEN/IMPAIR/RECOURSE/RESOLVE/VOID`, 형태는 채택된 `overlay_id`/`kind`/`payload`. 고정 FSM으로 표현 불가(`fsm_expressible: false`). 엔벨로프 최상위 섹션·FSM·별도 저장소 기각. 기존 오버레이 엔트리는 불변 | CAP-03, CAP-11, CAP-14 | `claim-slice-registry` |
| `uniqueness_and_open_slice_rule` | **ADOPTED.** `slice_key = (claim_id, payee_label)`당 **비종결 슬라이스 최대 1개**. 증액·분할 없음(VOID 후 재제안). 슬라이스 가능 줄 = 수익자 매핑된 pinned 원장 줄만. 홀더는 `KIX_CAPITAL_LENDER` 하나 | CAP-03, CAP-08 | `claim-slice-registry` |
| `shared_cap_accounting` | **ADOPTED.** 슬라이스 미회수액을 수익자·포트폴리오 노출에 **선지급과 합산**한다. 새 한도 숫자 없음, 기존 세 cap 이름 공유. 변경되는 점검 = **U4** | CAP-04, CAP-01 | `claim-slice-registry`, `UnderwritingPort` |
| `borrowing_base_double_use_guard` | **ADOPTED.** 한 줄의 면(face)은 선지급 예약 또는 슬라이스 중 **한 곳에만** 쓴다. U3 `eligible_face`에서 슬라이스 점유 면을 빼고, 개설 시 양방향 검사, 직렬화 락 + CAS 재평가. 변경되는 점검 = **U3**(와 U4) | CAP-04, CAP-08 | `claim-slice-registry`, `UnderwritingPort` |
| `holder_first_priority_shadow` | **ADOPTED.** 관측된 줄 분배는 **슬라이스 홀더 먼저**, 남는 몫만 선지급 상계 재원. 그림자 산술이며 적용된 분배가 아님 | CAP-03, CAP-05 | `claim-slice-registry`, `setoff-proposal-quote` |
| `impairment_and_recourse_shortfall` | **ADOPTED.** 구조적 부족액 > 0이면 운영자가 `SLICE_IMPAIR`. 부족액은 수익자 **전액 소구** 메모. V1 소구 회수는 같은 수익자 다른 청구 상계(폭포 ②) 하나뿐. 손실 부담 플랫폼 100 % 유지 | CAP-03, CAP-04 | `claim-slice-registry`, `overlay-recovery-writeoff` |
| `slice_lifecycle_states` | **ADOPTED.** `PROPOSED → OPEN → IMPAIRED → RESOLVED`, 종결 `RESOLVED`·`VOID`. 단조, 재개방·증액·홀더 변경 없음, 자동 전이 없음 | CAP-03 | `claim-slice-registry` |
| `authority_and_proposal_only` | **ADOPTED.** 사람 운영자 전용, `two_person_threshold_krw` 초과 2인, AI는 제안만(U5와 일치). 모든 슬라이스는 `SHADOW_NOT_APPLIED`·`funds_executed=false` | CAP-03, CAP-19 | `claim-slice-registry` |
| `capacity_bounds` | **ADOPTED.** 레지스트리 엔트리 ≤ 256, 슬라이스 ≤ 64, 비종결 ≤ 24, 수익자당 비종결 ≤ 3, 슬라이스당 소구 ≤ 8. 초과는 거절이며 축출 없음 | CAP-08, CAP-11 | `claim-slice-registry` |
| `export_and_digest_effect` | **ADOPTED.** 오버레이 digest에만 반영, 슬라이스 없는 책은 모든 digest·골든 바이트 불변, export는 V3 `overlay` 섹션 안에만, COA 게시 없음 | CAP-13, CAP-14, CAP-15 | `claim-slice-registry`, `export-manifest` |

## 2. KIX 비전 연결 — 읽은 pack 경로

- `/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md`. 「예약 확정 ≠ 결제 확인 ≠ 체인 권리 발행 완료」에 따라 슬라이스 `OPEN`은 소유권 이전이 아니라 시뮬레이션 예약 기록이다. A-4의 「과거 사실 재생은 새 실행 허가가 아니다」와 「늦은 사실은 현재 권한으로 대사」에 따라, 손상 뒤 늦은 분배도 append-only로 받아 부족액을 줄이고 로그를 잘라 버리지 않는다.
- `/workspace/capital-run/kixproto-ro/README.md` §1·§3. mock·비운영 범위이고 R2와 자체 저장·로그 신규 구현은 금지다. 그래서 레지스트리는 새 저장소가 아니라 기존 오버레이 저널의 폴드다. 이는 `docs/CAPITAL_REQUIREMENTS_KO.md` CAP-11의 "자체 저장엔진 만들지 않음"과도 같다.
- `docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md` §3.4·§3.1. CAP-03은 V1 `NOT_OFFERED`이고, 목표는 대주 법인의 **상환청구권 있는 매입(대부로 취급, 작업 가정)** 이다. 비소구·제3자 투자자 slice·트랜치는 증권성·온투업·채권추심업 검토 뒤에만 연다. 정산 청구는 Capital 자산이 아니라 메모이므로 슬라이스도 소유권 장부가 아니다.
- `docs/decisions/CAPITAL_DEFAULT_RECOVERY.md`. 저널·폴드 패턴(§4.3, §4.10), 재원 보존(`RECOVERY_SOURCE_EXCEEDED`), 폭포 ②(§4.4), 권한(§4.8), 손실 부담 `loss_attribution`의 재검토 조건("CAP-03 채권 매입이 생기면")을 이 노트가 닫는다(§3.6).
- `docs/decisions/CAPITAL_DEMO_BOOK.md`. `beneficiary_payee_map`, `eligible_face` 규칙, `SHADOW_PAYEE_LINES`(`SHADOW_NOT_APPLIED`), 합성 라벨 문법, 데모 예산 `MAX_OPERATIONS 500`의 60 %.
- `docs/decisions/CAPITAL_CLOSEOUT_ARTIFACT.md`. `test_count`가 커버 필드이므로 구현 노드가 다이제스트를 재생성해야 한다. 비주장(non-claims) 문법도 그대로 따른다.
- `docs/SEAMS.md` ShadowPolicyPort 행(모든 결과 `SHADOW_NOT_APPLIED`, `NOT_BOUND`)과 `docs/CAPITAL_REQUIREMENTS_KO.md` CAP-03·08·11·19 행(발췌만).
- 사용하지 않은 pack 경로: `CAPITAL_EXTERNAL_GATES.md`(pack에서 생략), `CAPITAL_ARTIFACT_BUNDLING.md`와 `docs/VALIDATION.md`(발췌만. 번들이 `docs/decisions/*.md`를 통째로 담으므로 새 노트는 자동 포함됨). `CAPITAL_ACCOUNTS_TAX_LEGAL.md`는 492행 중 238행까지만 읽었다.
- 「포부」의 번역: 그림자 단계에서 **이중 사용 방지와 우선순위 산술을 먼저 닫아 둔다.** 그러면 제3자 홀더가 열릴 때 재결정이 필요 없다. 지금 채택하는 것은 아무것도 없다.

## 3. 항목별 결정

공통 정의(모두 정수 KRW):
- 줄 `L = (claim_id, payee_label)`. `eligible_L = max(0, line_face(L) − refund_open(L))`는 `eligible_face`의 줄 단위 항이다.
- `served(S) = min(slice_face, max(0, distributed_to_beneficiary(L) − baseline_distributed_krw))`. `outstanding(S) = slice_face − served(S) − recourse_received(S)`.
- 점유 면 `encumbered(L) = min(outstanding(S), eligible_L)`. 상태 `OPEN`·`IMPAIRED`일 때만 값이 있고 그 외는 0이다.
- `served`, `outstanding`, `encumbered`는 **저널에 저장하지 않는 파생값**이다. 정산 조회와 FSM 조회의 순수 함수다.

### 3.1 registry_storage_location — ADOPTED
- **값.** 슬라이스는 오버레이 저널(두 번째 저널)의 **새 섹션** `state.claim_slices`에 산다. 엔벨로프 최상위 섹션은 추가하지 않는다. 엔트리 종류는 6개다: `SLICE_PROPOSE`(slice_face_krw, quote_ref), `SLICE_OPEN`(baseline, guard_trace), `SLICE_IMPAIR`, `SLICE_RECOURSE`, `SLICE_RESOLVE`, `SLICE_VOID`.
- **엔트리 형태.** 채택된 오버레이 엔트리 형태 `overlay_id`(dedup 키) / `kind` / `payload`를 그대로 쓴다. 여섯 종류는 `kind` 값이고, 아래 필드는 `payload`에 둔다: `slice_id`(= `SLICE_PROPOSE`의 `overlay_id`), `claim_id`, `payee_label`, `beneficiary_role`, `holder_role`, `tier`, `label: SIMULATED`, `application: SHADOW_NOT_APPLIED`, `offering`, `authority`. `sim_day`·`after_journal_index`처럼 오버레이 엔벨로프가 이미 정해 둔 필드는 CAPITAL_OVERLAY_STATE가 두는 자리에 둔다. 위치가 다르면 그 노트가 이긴다. 용량 상한은 §3.9에 있다.
- **FSM 표현 불가.** 슬라이스 레지스트리는 고정 FSM으로 표현할 수 없다(`fsm_expressible: false`, FINANCIAL_TERMS가 claim purchase에 붙인 표기와 같다). vendor FSM 바이트는 바꾸지 않으며, 레지스트리는 FSM 조회와 정산 조회를 읽기만 하는 오버레이 폴드다.
- **OVERLAY_STATE 확장 방식.** 폴드 키 하나와 엔트리 종류 6개를 **더하기만** 한다. 기존 엔트리 종류, 필드, dedup, CAS 시계, `VOLATILE_KEYS` 금지는 바꾸지 않는다. `overlay_schema`는 1로 유지한다. 빈 레지스트리는 키가 없으므로 슬라이스 없는 책의 digest는 바이트 불변이다. 만약 OVERLAY_STATE가 새 폴드 키에 스키마 올림을 요구하면 그 규칙이 이기고 `overlay_schema` 2와 새 골든으로 처리한다. 결정 내용은 바뀌지 않는다.
- **근거.** 슬라이스는 선지급에 묶이지 않으므로 `state.recovery`에 넣을 수 없다. 고정 FSM은 vendor 바이트라 만질 수 없다. 별도 파일은 자체 저장엔진이다.
- **대안.** 엔벨로프 새 섹션은 모든 export·digest를 바꿔서 기각했다.

### 3.2 uniqueness_and_open_slice_rule — ADOPTED
- **값.** `slice_id = SLICE_PROPOSE의 overlay_id`(중복이면 원 결과 반환, 페이로드가 다르면 409). **`slice_key`당 비종결 슬라이스(`PROPOSED`·`OPEN`·`IMPAIRED`)는 최대 1개**이며 위반하면 409 `SLICE_OPEN_EXISTS`다. 증액·분할·크기 변경은 없다. 바꾸려면 `PROPOSED`에서 VOID하고 다시 제안한다. 종결(`RESOLVED`·`VOID`) 뒤에는 새 슬라이스가 가능하다. 같은 청구의 다른 payee 줄은 독립 키다.
- **슬라이스 가능 줄.** `payee_label ∈ beneficiary_payee_map[beneficiary]`이면서 pinned 원장에 실제 있는 줄만이다(픽스처에서는 `organizer` 줄). `venue`·`agency` 같은 `SHADOW_NOT_APPLIED` 줄은 409 `SLICE_PAYEE_NOT_SLICEABLE`이다.
- **청구 관문.** 새 관문을 만들지 않는다. 같은 청구에 선지급을 낼 때 필요한 **U1·U2 결과를 그대로** 요구한다. 열린 환불이 있으면 U2가 막는다.
- **홀더.** 값은 `KIX_CAPITAL_LENDER` 하나다. 다른 값은 409 `SLICE_HOLDER_NOT_ADOPTED`다. `token`, `holder_ref`, `transfer_to` 같은 키는 400 `SLICE_FIELD_NOT_ADOPTED`다.
- **근거.** 줄당 슬라이스가 하나면 홀더 우선 산술이 단일 홀더로 닫히고 중첩 매입이 없다.
- **대안.** 줄당 다수 슬라이스는 순위 규칙을 새로 만들어야 하므로 기각했다. 청구당 1개는 줄이 다른 두 줄 사용을 막아 기각했다.

### 3.3 shared_cap_accounting — ADOPTED
- **값.** 수익자 노출 `exposure_B = Σ 선지급 FSM outstanding_exposure(B) + Σ outstanding(S)`(`OPEN`·`IMPAIRED`만). 포트폴리오 노출도 같은 합이다. **새 한도 숫자는 없다.** 슬라이스 개설은 `slice_face_krw ≤ single_advance_cap_krw`, `exposure_B + slice_face_krw ≤ beneficiary_aggregate_cap_krw`, `exposure_portfolio + slice_face_krw ≤ portfolio_cap_krw`를 모두 만족해야 한다. 위반하면 409 `SLICE_CAP_EXCEEDED`이며 `cap_ref`에 필드 이름을 담는다. 선지급 쪽 U4는 `exposure_B`에 슬라이스 항이 들어가도록 **한 항만 더한다.**
- **측정.** 노출은 가격이 아니라 **면 기준 미회수액** `outstanding(S)`다. 가격 ≤ 면이므로 보수적인 상한이다. 정수이고 반올림이 없으며 가격 산식에 의존하지 않는다. 가격 기반 정밀화는 CLAIM-PURCHASE 산식이 바인딩된 뒤로 미룬다.
- **변경되는 점검.** U4만 바뀐다. `PROPOSED`·`VOID`·`RESOLVED`는 0으로 센다. `IMPAIRED`는 계속 센다.
- **근거.** 같은 대주 법인의 같은 수익자 위험이므로 선지급과 슬라이스를 따로 세면 cap이 두 배가 된다.
- **대안.** 슬라이스 전용 sub-limit은 새 숫자가 필요하고 조건 노트의 소유라 기각했다. 열린 위험으로 남긴다.

### 3.4 borrowing_base_double_use_guard — ADOPTED
- **값.** 한 줄의 면은 **선지급 예약 또는 슬라이스 중 한 곳에만** 쓴다.
  - **G0 (U3 변경).** U3의 줄별 `eligible` 항에서 `encumbered(L)`을 뺀다. `eligible_face(B) = Σ eligible_L − Σ encumbered(L)`이고 티어별 선지급률 적용은 그대로다. 슬라이스가 없으면 값이 0이라 응답에 필드가 없어 기존 벡터는 바이트 불변이다.
  - **G1 (슬라이스 개설).** `slice_face ≤ eligible_L − advance_pledged(L)`. `advance_pledged(L) = ceil(reserved_open(claim) × line_share)`로, FSM 공유 액면 예약을 줄 비율로 안분해 올림한 값이다. 위반하면 409 `BASE_ALREADY_ENCUMBERED`다.
  - **G2 (역방향).** 개설 뒤에도 `Σ 선지급 outstanding(B) ≤ 새 base(B)`여야 한다. 이미 초과한 수익자에게도 거절한다. 409 `SLICE_WOULD_BREACH_ADVANCE_BASE`.
  - **G3 (상계 재원).** `source_available(L') = distributed_to_B(L') − served − Σ RECOVERY − Σ SLICE_RECOURSE`가 0 이상이어야 하며 위반 시 기존 409 `RECOVERY_SOURCE_EXCEEDED`를 쓴다.
  - **G4 (직렬화).** 서비스의 단일 operation 락 아래에서 평가한다. 슬라이스 `OPEN` 명령은 `after_journal_index` CAS(409 `REGISTRY_STALE_CAS`)를 쓰고, 선지급 `draw` 명령에서도 U3·U4를 슬라이스 항 포함으로 **다시 평가**한다. 먼저 커밋한 쪽이 이기고 나중 쪽은 남은 base로 재평가된다.
- **불변식 I-BASE.** 승인 시점에 `encumbered(L) + advance_pledged(L) ≤ eligible_L`이다. 이후 환불로 `eligible_L`이 줄면 그 차이는 불변식 위반이 아니라 **손상**(§3.6)으로 나타난다.
- **예시(합성, 줄 `demo-delta-small` organizer 47,500,000, 환불 없음).** 열린 선지급이 25,000,000을 점유하면 자유 면은 22,500,000이다. 슬라이스 25,000,000 요청은 `BASE_ALREADY_ENCUMBERED`로 거절되고 22,500,000은 `OPEN`된다. 이후 선지급 U3의 줄 `eligible`은 25,000,000이 된다.
- **변경되는 점검.** **U3**(`eligible_face` 감산)와 **U4**(§3.3 노출 합)다. U1·U2·U5·U6는 바뀌지 않는다. U5는 사람 운영자·2인 원칙·AI 제안 전용 점검이며, 검토자 확인에 따르면 §3.8과 일치하므로 §3.8은 U5의 레지스트리 쪽 적용일 뿐 U5를 바꾸지 않는다. U6는 정의를 확인하지 못했고, 바뀌지 않는다는 선언만 한다.
- **대안.** 락 없는 사전점검만 하는 방식은 경합에서 같은 base를 두 번 쓸 수 있어 기각했다. 슬라이스를 선지급률로 환산하는 방식은 매각된 면의 소유 이전을 반영하지 못해 기각했다.

### 3.5 holder_first_priority_shadow — ADOPTED (basis: 작업 가정)
- **값.** 설정 순서는 (1) 정산 정책 클래스와 환불(정산 조회가 이미 반영한 값, 재계산하지 않음) → (2) **슬라이스 홀더**(`outstanding(S)`까지) → (3) 선지급 상계 재원(폭포 ①②)이 남은 몫만 사용 → (4) 수익자 잔여다. `served`는 `OPEN` 시점에 기록한 `baseline_distributed_krw` 이후의 누적 분배로만 센다. 그 이전 분배는 선지급 상계 재원에 속한다. 사전 부도 상계 견적(`setoff-proposal-quote`)도 같은 `source_available`을 쓴다.
- **그림자.** 이 우선순위는 레지스트리 조회 산술이며 적용된 분배가 아니다. 고정 `SettlementMachine`의 분배와 `PRIMARY_FEE_BPS` 2수취인 구조는 바뀌지 않는다. 예시: `OPEN` 뒤 분배 30,000,000이 관측되면 `served = 22,500,000`, 선지급 상계 재원은 7,500,000이다.
- **근거.** 매각된 면은 더 이상 수익자의 자산이 아니므로 수익자 자산에 거는 선지급 상계는 남은 몫에만 닿을 수 있다(소유가 먼저). V1에서는 두 도구의 대주가 같지만, 순서를 지금 고정해 두면 홀더가 늘어날 때 재결정이 필요 없다.
- **기초.** WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW — 매각분의 도산 시 지위.

### 3.6 impairment_and_recourse_shortfall — ADOPTED (basis: 작업 가정)
- **손상.** `shortfall = max(0, outstanding(S) − eligible_L)`을 서버가 계산한다. 1 이상이면 운영자가 `SLICE_IMPAIR`를 게시할 수 있고(`reason`은 `REFUND_REDUCED_LINE`·`CLAIM_VOIDED_OR_REVERSED`·`COVERAGE_SHORTFALL_OTHER`), 아니면 409 `SLICE_NOT_IMPAIRABLE`이다. 자동 손상은 없고 조건이 성립하면 표시 전용 플래그 `SLICE_IMPAIRMENT_ELIGIBLE`만 낸다. 손상 뒤에도 늦은 분배는 계속 `served`로 들어가 부족액을 줄인다(A-4).
- **소구.** 부족액은 수익자에 대한 **전액 소구** 메모다. V1의 회수 경로는 `SLICE_RECOURSE` 하나뿐이며 폭포 ② `SETOFF_OTHER_CLAIMS_SAME_BENEFICIARY`와 같은 조건이다: 원천 청구가 다르고, `beneficiary_payee_map`으로 같은 수익자에 매핑되고, `setoff-proposal-quote` 견적이 있고, 금액이 `min(outstanding, 견적, source_available)` 이하다. `SLICE_RECOURSE.waterfall_step`은 열거형이고 V1 값은 폭포 ② 하나다. 법적 효력은 `NOT_ASSESSED`다. 외부 추심은 없고 관람권 압류·티켓 이전·권리 취소·토큰 압류는 영구 금지다. 선지급 `RECOVERY`와 `SLICE_RECOURSE`가 같은 재원 줄을 쓰면 저널 순서대로 소비하고 새 우선순위를 만들지 않는다.
- **TERMS와의 좁힘 차이.** FINANCIAL_TERMS(검토자 발췌)는 줄 현금 뒤의 부족액을 수익자에 대한 소구 청구로 두고 "그다음 회수 폭포"로 간다고 적는다. 이 노트는 V1 슬라이스의 회수를 폭포 ② 하나로 **좁힌다.** TERMS가 부족액에 폭포의 다른 단계를 더 요구하면, `waterfall_step` 열거형에 값을 추가하는 것으로 처리한다. 엔트리 형태·저장 위치·digest 규칙은 바뀌지 않는다. 문구 조정은 구현 노드가 TERMS 소유 노트와 함께 한다(§6).
- **손실 부담.** `KIX_CAPITAL_PLATFORM_100_PERCENT`, 트랜치 없음을 유지한다. 유일한 홀더가 대주 법인 자신이기 때문이다. DEFAULT_RECOVERY `loss_attribution`의 재검토 조건("CAP-03 채권 매입")은 **대주 법인 단독 홀더에 한해 닫고**, 대주 법인 이외의 첫 홀더나 토큰화 슬라이스(둘 다 `NOT_ADOPTED`)가 생기면 다시 연다.
- **미결 하위 항목.** (a) 시간 기반 손상(분배 지연)은 `null`이다. 정산 시각 근거가 pack에 없어 담당은 `settlement-policy-deepening` upstream이다. (b) 슬라이스 상각은 `null`이다. V1에서는 `NOT_POSTABLE_V1`이며 손상 잔액은 `IMPAIRED`로 보이고 노출에 계속 센다. COA 게시도 없다.
- **기초.** WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW — 소구 매입의 대부 취급, 상계 효력, 도산 시 지위.

### 3.7 slice_lifecycle_states — ADOPTED
- **상태.** `PROPOSED`(기준을 점유하지 않음), `OPEN`(면 점유·노출 계산), `IMPAIRED`, `RESOLVED`(종결), `VOID`(종결).
- **전이.**
  - ∅→`PROPOSED`: `SLICE_PROPOSE`. `quote_ref`와 `slice_face_krw ≤ 견적 면`이 필요하다. 아니면 409 `SLICE_QUOTE_MISMATCH`.
  - `PROPOSED`→`OPEN`: `SLICE_OPEN`. G1–G4와 §3.3 cap 점검, U1·U2를 통과해야 한다.
  - `PROPOSED`→`VOID`: `SLICE_VOID`.
  - `OPEN`→`VOID`: `SLICE_VOID`. `served = 0`일 때만 가능하다(운영 정정, 점유 해제).
  - `OPEN`→`IMPAIRED`: `SLICE_IMPAIR`.
  - `OPEN`→`RESOLVED`: `SLICE_RESOLVE`(`SERVED_IN_FULL`). `outstanding = 0`일 때만 가능하다.
  - `IMPAIRED`→`RESOLVED`: `SLICE_RESOLVE`(`RECOURSE_SATISFIED` 또는 `SERVED_IN_FULL`). `outstanding = 0`일 때만 가능하다.
- **규칙.** 위 표 밖의 전이는 409 `SLICE_STATE_INVALID`다. 재개방·증액·홀더 변경은 없다. 모든 전이는 운영자 명령이며 틱이 자동 전이하지 않는다. `RESOLVED` 조건이 성립하면 표시 전용 `SLICE_RESOLVABLE` 플래그만 낸다.
- **근거.** 파생값(`served`)이 저널 없이 상태를 바꾸면 폴드가 순수하지 않다. 그래서 상태 변화는 모두 명시적 엔트리다.

### 3.8 authority_and_proposal_only — ADOPTED
- **값.** `SLICE_PROPOSE`·`SLICE_OPEN`·`SLICE_IMPAIR`·`SLICE_RECOURSE`·`SLICE_RESOLVE`·`SLICE_VOID`는 **사람 운영자 전용**이다. 금액 기준(`slice_face_krw`, `SLICE_RECOURSE`는 `amount_krw`)이 `two_person_threshold_krw` 이하면 1인, **초과면 서로 다른 `approver_label` 2개 이상**이다(409 `TWO_PERSON_REQUIRED`). 같은 `slice_key`의 같은 `sim_day` 금액은 누적해 비교한다. 이는 U5(사람 운영자, 2인 원칙, AI 제안 전용)를 슬라이스 명령에 적용한 것이다.
- **AI.** 제안만 한다(`executionAuthorized=false`). 제안 종류는 `SLICE_CANDIDATE`·`SLICE_IMPAIRMENT`·`SLICE_RECOURSE_SETOFF`이고, agent lane의 게시 시도는 403 `SLICE_AGENT_FORBIDDEN`으로 거절하며 쓰지 않는다. 운영자가 채택하면 별도 명령이 `proposal_id`를 인용한다. AI 제안은 레지스트리의 `PROPOSED`가 아니며 승인으로 세지 않는다.
- **그림자 경계.** 모든 슬라이스 표면에 상수로 `offering: SIMULATION_ONLY_NOT_OFFERED_V1`, `application: SHADOW_NOT_APPLIED`, `funds_executed: false`, `title_transferred: false`, `legal_effect: NOT_ASSESSED`, `policy_adopted: false`를 붙인다. 제3자 홀더와 토큰화 슬라이스는 `NOT_ADOPTED`다. 홀더·수익자 라벨은 합성 role이며 법적 당사자·계좌가 아니다. 2인 원칙은 시뮬레이션 통제이고 `approver_label`은 인증이 아니다.
- **소비.** `claim-slice-registry`가 명령·거절 코드·`/api/overlay` 조회를 구현한다. 새 `typing.Protocol`은 만들지 않는다. 그래서 `docs/SEAMS.md`의 행 추가 의무가 생기지 않고 ShadowPolicyPort 행의 설명만 갱신한다.

### 3.9 capacity_bounds — ADOPTED
- **값.** 레지스트리 엔트리 ≤ 256, 슬라이스(전 상태) ≤ 64, 비종결 ≤ 24, 수익자당 비종결 ≤ 3, 슬라이스당 `SLICE_RECOURSE` ≤ 8, 문자열 필드 ≤ 64바이트, 자유 텍스트 없음(`reason`은 열거형이라 개인정보가 들어갈 자리가 없다). 초과는 409 `SIMULATION_CAPACITY`이며 `scope: claim_slice_registry`를 담는다. 축출·자동 VOID는 없다(A-4). 전체 오버레이 상한이 더 낮으면 그것이 이긴다. 서비스가 오버레이 명령을 `MAX_OPERATIONS 500`에 센다면 레지스트리 시연 스크립트 예산은 ≤ 40 operation이다(데모 북 예산 300 안에 든다).
- **근거.** 줄당 비종결 1개이므로 비종결 수는 어차피 줄 수 이하다. 데모 북은 청구 10건이라 24가 충분하다. 계정·좌석 식별자가 아니라 줄이 키이므로 좌석 규모(RS)와 무관하다.

### 3.10 export_and_digest_effect — ADOPTED
- **digest.** 슬라이스 엔트리는 `overlay_state.digest`의 폴드 `state.claim_slices`에 들어간다. 빈 레지스트리는 키가 없어 `overlay_schema`는 1 그대로다. F04 `state_digest`, `payload_sha256`, `tests/golden/demo.json`, 슬라이스 없는 기존 오버레이 골든은 **바이트 불변**이다. 파생값은 digest에 넣지 않는다. 새 골든은 `tests/golden/overlay_claim_slices.json`(제안 → 개설 → 이중 사용 거절 → 홀더 우선 분배 → 손상 → 소구 상계 → 종결)이다.
- **export.** V3 `overlay` 섹션 안에만 나타난다. 기존 일곱 섹션, 서명 대상 `content_digest`, recon `CHECK_IDS`는 바뀌지 않는다. 불변식은 쓰기 시점과 로드 시 폴드 재검증에서 닫는다. `SLICE_OPEN`의 `guard_trace`는 `after_journal_index`까지의 FSM 접두를 재생해 검증한다.
- **COA.** 슬라이스는 게시하지 않는다(`CAPITAL-COA-V1` 불변). 메모 계정이 필요하면 후속 투영 노드가 정한다.
- **영향.** 구현 노드가 단위 테스트를 추가하면 `test_count`(CLOSEOUT 커버 필드)가 바뀌므로 `CAPITAL-CLOSEOUT-REGEN-V1` 절차로 다이제스트와 벡터 팩을 재생성해야 한다.

## 4. 기계 판독 결정 블록

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "claim-slice-registry-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-10-18",
  "provisional": true,
  "status": "PROVISIONAL_PRODUCT_DECISION",
  "scope": "KIX-CAPITAL simulation and product design only; not an offer; no real money; production NOT_AUTHORIZED; legal and accounting content are working assumptions pending professional review; no upstream contract claimed adopted",
  "bases": {"capital_main": "5ec4c95", "kix_protocol": "9eb6b9f", "terms_version": "CAPITAL-TERMS-V1", "claim_purchase_version": "CAPITAL-CLAIM-PURCHASE-V1", "coa_version": "CAPITAL-COA-V1"},
  "offering": "SIMULATION_ONLY_NOT_OFFERED_V1",
  "third_party_holders": "NOT_ADOPTED",
  "tokenised_slices": "NOT_ADOPTED",
  "upstream_adoption_claimed": false,
  "name_conflict_rule": "the four dependency notes were not opened by this decider; field and code names come from the allowed notes and from reviewer excerpts of the dependency notes (second-hand); on a name or number conflict the dependency note wins, on registry structure and ordering this note wins",
  "entries": {
    "registry_storage_location": {
      "status": "ADOPTED",
      "value": {
        "location": "NEW_OVERLAY_SECTION",
        "journal": "overlay journal (second journal); fold key state.claim_slices; key absent when no entries",
        "overlay_schema": "UNCHANGED_1",
        "fsm_expressible": false,
        "fsm_note": "the registry cannot be expressed by the pinned FSM and the vendor bytes stay untouched; the registry only reads FSM and settlement views",
        "rejected_locations": ["pinned FSM state or vendor bytes", "new top-level envelope section", "separate file or store", "inside state.recovery (slices are not advance-bound)"],
        "extends_overlay_state": "additive only: one fold key and six entry kinds; existing entry kinds, fields, dedup, CAS clock and VOLATILE_KEYS rule unchanged",
        "entry_shape": "adopted overlay entry shape overlay_id (dedup key) / kind / payload; the six kinds below are values of kind",
        "entry_kinds": ["SLICE_PROPOSE", "SLICE_OPEN", "SLICE_IMPAIR", "SLICE_RECOURSE", "SLICE_RESOLVE", "SLICE_VOID"],
        "common_payload_fields": ["slice_id (= overlay_id of SLICE_PROPOSE)", "claim_id", "payee_label", "beneficiary_role", "holder_role (const KIX_CAPITAL_LENDER)", "tier", "label (SIMULATED)", "application (SHADOW_NOT_APPLIED)", "offering (SIMULATION_ONLY_NOT_OFFERED_V1)", "authority {role, approvals[], proposal_id?}"],
        "envelope_fields_stay_where_overlay_state_puts_them": ["sim_day", "after_journal_index"],
        "kind_fields": {
          "SLICE_PROPOSE": ["slice_face_krw (>=1)", "quote_ref (claim_purchase shadow quote under CAPITAL-CLAIM-PURCHASE-V1)", "recourse (const FULL_RECOURSE_TO_BENEFICIARY)"],
          "SLICE_OPEN": ["baseline_distributed_krw", "guard_trace {eligible_line_krw, advance_pledged_krw, beneficiary_exposure_before_krw, portfolio_exposure_before_krw, u1, u2, u3, u4}"],
          "SLICE_IMPAIR": ["reason (REFUND_REDUCED_LINE | CLAIM_VOIDED_OR_REVERSED | COVERAGE_SHORTFALL_OTHER)", "shortfall_krw (server computed, not supplied)", "served_at_impairment_krw", "outstanding_at_impairment_krw", "eligible_line_krw"],
          "SLICE_RECOURSE": ["amount_krw (>=1)", "waterfall_step (enumeration; V1 only SETOFF_OTHER_CLAIMS_SAME_BENEFICIARY)", "source_ref {claim_id, payee_label, source_cut}", "quote_ref (from setoff-proposal-quote)"],
          "SLICE_RESOLVE": ["resolution (SERVED_IN_FULL | RECOURSE_SATISFIED)", "served_krw", "recourse_received_krw"],
          "SLICE_VOID": ["reason (OPERATOR_WITHDRAWN | SUPERSEDED_BY_NEW_PROPOSAL | OPERATOR_CORRECTION)"]
        },
        "derived_not_journaled": ["served_krw", "outstanding_krw", "encumbered_face_krw", "exposure_krw", "SLICE_IMPAIRMENT_ELIGIBLE", "SLICE_RESOLVABLE"],
        "forbidden_keys": ["instance_id", "created_at", "saved_at", "timestamp", "timestamps", "any personal data", "token", "holder_ref", "transfer_to"],
        "fallback": "if CAPITAL_OVERLAY_STATE requires a schema bump for a new fold key, bump overlay_schema to 2 and add a new golden; the decision is otherwise unchanged",
        "consumer": "claim-slice-registry"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-18",
      "cap_rows": ["CAP-03", "CAP-11", "CAP-14"],
      "rationale": "Slices are not advance-bound, the pinned FSM cannot express them and cannot change, and a second store is forbidden, so a new fold key in the existing overlay journal, in the adopted entry shape, is the only location that keeps every existing digest byte-identical when no slice exists.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "uniqueness_and_open_slice_rule": {
      "status": "ADOPTED",
      "value": {
        "slice_id": "overlay_id of SLICE_PROPOSE; same overlay_id returns the original result, a different payload is 409",
        "slice_key": "(claim_id, payee_label)",
        "non_terminal_states": ["PROPOSED", "OPEN", "IMPAIRED"],
        "rule": "at most one non-terminal slice per slice_key",
        "reject": "409 SLICE_OPEN_EXISTS",
        "resize_topup_split": "NONE; VOID a PROPOSED slice and propose again",
        "after_terminal": "a new slice on the same key is allowed after RESOLVED or VOID",
        "sliceable_lines": "payee_label in beneficiary_payee_map[beneficiary] and present on the pinned ledger; SHADOW_NOT_APPLIED lines (venue, agency) are 409 SLICE_PAYEE_NOT_SLICEABLE",
        "claim_gates": "U1 and U2 outcomes required exactly as for an advance on the same claim; no new gate",
        "holder": "KIX_CAPITAL_LENDER only; other values 409 SLICE_HOLDER_NOT_ADOPTED; token or holder keys 400 SLICE_FIELD_NOT_ADOPTED",
        "consumer": "claim-slice-registry"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-18",
      "cap_rows": ["CAP-03", "CAP-08"],
      "rationale": "One non-terminal slice per line keeps the holder-first arithmetic single-holder and rules out stacked purchases of the same face.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "shared_cap_accounting": {
      "status": "ADOPTED",
      "value": {
        "exposure_beneficiary": "sum of FSM outstanding_exposure of the beneficiary's advances + sum of outstanding(S) of its OPEN and IMPAIRED slices",
        "exposure_portfolio": "same sum over all beneficiaries",
        "measure": "face-denominated unserved amount outstanding(S) = slice_face - served - recourse_received; integer; conservative upper bound on price-based exposure",
        "slice_open_checks": ["slice_face_krw <= CAPITAL-TERMS-V1.underwriting_depth.single_advance_cap_krw", "exposure_beneficiary + slice_face_krw <= underwriting_depth.beneficiary_aggregate_cap_krw", "exposure_portfolio + slice_face_krw <= underwriting_depth.portfolio_cap_krw"],
        "reject": "409 SLICE_CAP_EXCEEDED with cap_ref naming the field",
        "advance_side": "U4 adds the slice exposure term to the beneficiary and portfolio sums; single_advance_cap_krw still applies per draw only",
        "counted_states": {"PROPOSED": 0, "OPEN": "outstanding", "IMPAIRED": "outstanding", "RESOLVED": 0, "VOID": 0},
        "new_cap_literals": "NONE; no slice-specific sub-limit",
        "check_changed": "U4",
        "consumer": "claim-slice-registry"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-18",
      "cap_rows": ["CAP-04", "CAP-01"],
      "rationale": "Advances and slices are the same lender's risk on the same beneficiary, so counting them separately would double the caps; a face-denominated measure needs no pricing formula and over-counts rather than under-counts.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "borrowing_base_double_use_guard": {
      "status": "ADOPTED",
      "value": {
        "principle": "a unit of eligible line face backs either an advance reservation or a slice, never both",
        "definitions": {"eligible_L": "max(0, line_face(L) - refund_open(L))", "encumbered_L": "min(outstanding(S), eligible_L) for OPEN and IMPAIRED, else 0", "advance_pledged_L": "ceil(reserved_open(claim) * line_share), pro-rata by recognized line share, rounded up"},
        "G0_u3_change": "U3 eligible_face(B) = sum(eligible_L) - sum(encumbered_L); tier advance-rate application unchanged; zero encumbrance leaves the field absent so existing vectors stay byte-identical",
        "G1_slice_open": "slice_face <= eligible_L - advance_pledged_L else 409 BASE_ALREADY_ENCUMBERED",
        "G2_reverse": "sum of the beneficiary's advance outstanding <= base after the new encumbrance, also when already breached before; else 409 SLICE_WOULD_BREACH_ADVANCE_BASE",
        "G3_recovery_sources": "source_available(L') = distributed_to_beneficiary(L') - served - sum(RECOVERY consumed) - sum(SLICE_RECOURSE consumed) >= 0 else 409 RECOVERY_SOURCE_EXCEEDED",
        "G4_serialization": "evaluated under the service single operation lock; SLICE_OPEN carries after_journal_index CAS (409 REGISTRY_STALE_CAS); the advance draw command re-runs U3 and U4 with slice terms; the first commit wins and the second is re-evaluated on the remainder",
        "invariant_I_BASE": "at admission encumbered_L + advance_pledged_L <= eligible_L; later shrinkage of eligible_L is recorded as impairment, not as a violation",
        "checks_changed": ["U3", "U4"],
        "checks_unchanged": ["U1", "U2", "U5", "U6"],
        "u5_note": "U5 (human operator, two-person rule, AI proposes only) is applied to slice commands by authority_and_proposal_only and is not changed; U6 definition not confirmed, only declared unchanged",
        "example_synthetic": "line 47,500,000 with 25,000,000 pledged leaves 22,500,000: a 25,000,000 slice is BASE_ALREADY_ENCUMBERED, a 22,500,000 slice opens, later advance U3 sees 25,000,000 eligible",
        "consumer": "claim-slice-registry"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-18",
      "cap_rows": ["CAP-04", "CAP-08"],
      "rationale": "Subtracting encumbered face in U3, checking in both directions at admission and re-evaluating under the operation lock closes every path by which the same face could back an advance and a slice, including the set-off source path.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "holder_first_priority_shadow": {
      "status": "ADOPTED",
      "value": {
        "scope": "observed distribution to the beneficiary on the line, already net of settlement policy classes and refunds as the settlement view reports them",
        "order": ["settlement policy classes and refunds (as observed, not recomputed)", "slice holder up to outstanding(S)", "advance set-off sources (recovery steps 1 and 2) from the remainder", "beneficiary remainder"],
        "served": "min(slice_face, max(0, distributed_to_beneficiary(L) - baseline_distributed_krw)); baseline recorded at SLICE_OPEN; earlier distributions stay available to advance set-off",
        "pre_default_setoff_quote": "setoff-proposal-quote uses source_available",
        "shadow": "arithmetic on the registry view only; never an applied distribution; pinned SettlementMachine distribution and the two-payee PRIMARY_FEE_BPS structure unchanged",
        "example_synthetic": "slice 22,500,000 OPEN, distribution 30,000,000 observed afterwards: served 22,500,000, advance set-off source 7,500,000",
        "holder_in_v1": "KIX_CAPITAL_LENDER; ordering fixed now so a future non-lender holder needs no re-decision; nothing is adopted",
        "consumer": "claim-slice-registry"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-18",
      "cap_rows": ["CAP-03", "CAP-05"],
      "rationale": "A sold face is no longer the beneficiary's asset, so set-off for the beneficiary's advance can only reach what remains after the holder; fixing the order in shadow now means a later holder needs no re-decision.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "review_items": ["priority of a sold slice against set-off in the beneficiary's insolvency"]
    },
    "impairment_and_recourse_shortfall": {
      "status": "ADOPTED",
      "value": {
        "shortfall": "max(0, outstanding(S) - eligible_L), computed by the server; SLICE_IMPAIR requires shortfall >= 1 else 409 SLICE_NOT_IMPAIRABLE",
        "trigger": "operator command only; display-only flag SLICE_IMPAIRMENT_ELIGIBLE; no automatic impairment",
        "late_distributions": "after impairment later distributions still count as served and reduce the shortfall",
        "recourse": {"nature": "FULL_RECOURSE_TO_BENEFICIARY memo", "only_recovery_path_v1": "SLICE_RECOURSE = waterfall step SETOFF_OTHER_CLAIMS_SAME_BENEFICIARY conditions (different source claim, same beneficiary via beneficiary_payee_map, setoff-proposal-quote exists, amount <= min(outstanding, quote, source_available))", "waterfall_step_enumeration": "V1 contains only SETOFF_OTHER_CLAIMS_SAME_BENEFICIARY; further steps may be added as enumeration values without changing the entry shape or digest rules", "terms_reconciliation": "narrows the FINANCIAL_TERMS wording that a shortfall after line cash is a recourse claim against the organizer and then goes to the recovery waterfall; to be reconciled at implementation, the terms note wins on its own names and numbers", "legal_effect": "NOT_ASSESSED", "external_collection": "NOT_POSTABLE", "never": ["ADMISSION_RIGHT_SEIZURE", "TICKET_TRANSFER", "RIGHT_CANCELLATION", "TOKEN_SEIZURE"], "shared_source_order": "journal order across RECOVERY and SLICE_RECOURSE; no new priority"},
        "loss_bearer": "KIX_CAPITAL_PLATFORM_100_PERCENT",
        "tranching": "NONE",
        "loss_attribution_reopen": "closed for the lender-only holder; reopens at the first non-lender holder or tokenised slice (both NOT_ADOPTED)",
        "slice_writeoff": null,
        "slice_writeoff_reason": "NOT_POSTABLE_V1: impaired residual stays visible as IMPAIRED and keeps counting toward exposure; no COA postings; owner coa-payment-writeoff-postings if ever decided",
        "time_based_impairment": null,
        "time_based_impairment_reason": "no settlement timing source in the readable pack; owner settlement-policy-deepening upstream",
        "consumer": "claim-slice-registry"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-18",
      "cap_rows": ["CAP-03", "CAP-04"],
      "rationale": "A structural shortfall is the only impairment that needs no timing source; full recourse with the existing step-2 set-off path gives the shortfall a collection route without inventing a new waterfall, and the sole holder being the lender keeps loss attribution unchanged.",
      "provisional": true,
      "basis": "WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW",
      "review_items": ["characterisation of a recourse purchase as lending", "effect of set-off against settlement distributions", "position in insolvency proceedings"]
    },
    "slice_lifecycle_states": {
      "status": "ADOPTED",
      "value": {
        "states": ["PROPOSED", "OPEN", "IMPAIRED", "RESOLVED", "VOID"],
        "terminal": ["RESOLVED", "VOID"],
        "transitions": [
          "none -> PROPOSED via SLICE_PROPOSE (quote_ref required, slice_face <= quoted face else 409 SLICE_QUOTE_MISMATCH)",
          "PROPOSED -> OPEN via SLICE_OPEN (G1-G4, cap checks, U1 and U2)",
          "PROPOSED -> VOID via SLICE_VOID",
          "OPEN -> VOID via SLICE_VOID only when served = 0",
          "OPEN -> IMPAIRED via SLICE_IMPAIR",
          "OPEN -> RESOLVED via SLICE_RESOLVE (SERVED_IN_FULL) when outstanding = 0",
          "IMPAIRED -> RESOLVED via SLICE_RESOLVE (RECOURSE_SATISFIED or SERVED_IN_FULL) when outstanding = 0"
        ],
        "other_transitions": "409 SLICE_STATE_INVALID; also 409 SLICE_NOT_RESOLVABLE when outstanding > 0",
        "forbidden": ["reopen", "resize", "holder change", "automatic transition by tick"],
        "proposed_holds_base": false,
        "consumer": "claim-slice-registry"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-18",
      "cap_rows": ["CAP-03"],
      "rationale": "Derived values must not change state without a journal entry or the fold stops being pure, so every transition is an explicit operator command and the machine is monotone.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "authority_and_proposal_only": {
      "status": "ADOPTED",
      "value": {
        "human_only_actions": ["SLICE_PROPOSE", "SLICE_OPEN", "SLICE_IMPAIR", "SLICE_RECOURSE", "SLICE_RESOLVE", "SLICE_VOID"],
        "threshold_ref": "CAPITAL-TERMS-V1.underwriting_depth.two_person_threshold_krw",
        "up_to_threshold": "single human operator",
        "above_threshold": "approvals[] with at least 2 distinct approver_label values, else 409 TWO_PERSON_REQUIRED",
        "amount_basis": {"open_and_propose": "slice_face_krw", "recourse": "amount_krw"},
        "aggregation": "amounts on the same slice_key and sim_day are summed against the threshold",
        "u5_alignment": "applies the U5 rule (human operator, two-person rule, AI proposes only) to slice commands; U5 itself is not changed",
        "ai_lane": {"role": "PROPOSE_ONLY", "executionAuthorized": false, "proposal_kinds": ["SLICE_CANDIDATE", "SLICE_IMPAIRMENT", "SLICE_RECOURSE_SETOFF"], "post_attempt": "403 SLICE_AGENT_FORBIDDEN, no write", "adoption": "operator posts a separate command citing proposal_id; an AI proposal is not a registry PROPOSED slice and never counts as an approval"},
        "constant_labels": {"offering": "SIMULATION_ONLY_NOT_OFFERED_V1", "application": "SHADOW_NOT_APPLIED", "funds_executed": false, "title_transferred": false, "legal_effect": "NOT_ASSESSED", "policy_adopted": false},
        "not_adopted": {"third_party_holders": "NOT_ADOPTED", "tokenised_slices": "NOT_ADOPTED", "non_recourse_sale": "NOT_ADOPTED", "tranching": "NOT_ADOPTED"},
        "control_strength": "SIMULATED control; approver_label is not authentication",
        "seam": "no new typing.Protocol; no new docs/SEAMS.md row; ShadowPolicyPort and UnderwritingPort read the registry",
        "consumer": "claim-slice-registry"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-18",
      "cap_rows": ["CAP-03", "CAP-19"],
      "rationale": "Reuses the human two-person and AI propose-only authority already decided for default and recovery, and keeps every slice a shadow record so the offering label and the NOT_ADOPTED holders stay true.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "capacity_bounds": {
      "status": "ADOPTED",
      "value": {
        "max_registry_entries": 256,
        "max_slices_total": 64,
        "max_non_terminal_slices": 24,
        "max_non_terminal_per_beneficiary": 3,
        "max_recourse_entries_per_slice": 8,
        "max_string_bytes": 64,
        "free_text": "NONE; reasons are enumerations",
        "reject": "409 SIMULATION_CAPACITY with scope claim_slice_registry",
        "eviction": "NONE; no automatic VOID or truncation",
        "relation_to_overlay_bound": "the lower of this and the overlay global bound applies",
        "demo_script_budget_operations": 40,
        "demo_budget_basis": "inside the demo book budget of 300 operations (60 percent of MAX_OPERATIONS 500) if overlay commands count toward it",
        "keyed_by": "line, not seat or ticket slot"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-18",
      "cap_rows": ["CAP-08", "CAP-11"],
      "rationale": "One non-terminal slice per line bounds the live set by the number of lines; the demo book has ten claims so 24 is sufficient, and rejection without eviction preserves late facts.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "export_and_digest_effect": {
      "status": "ADOPTED",
      "value": {
        "overlay_digest": {"fold_key": "state.claim_slices", "empty": "KEY_ABSENT", "overlay_schema": "UNCHANGED_1", "derived_values_in_digest": false, "new_golden": "tests/golden/overlay_claim_slices.json", "existing_goldens": "unchanged when they contain no slice"},
        "f04": {"state_digest": "UNCHANGED", "payload_sha256": "UNCHANGED", "tests_golden_demo_json": "UNCHANGED"},
        "export": {"where": "V3 overlay section only", "existing_seven_sections": "UNTOUCHED", "content_digest_signing_target": "unchanged for books without slices", "new_recon_check_ids": "NONE", "label": "SIMULATED, SHADOW_NOT_APPLIED"},
        "invariants_verified_at_write_and_load_fold": ["one non-terminal slice per slice_key", "holder_role is KIX_CAPITAL_LENDER", "encumbered_L + advance_pledged_L <= eligible_L at admission", "exposure sums within the three CAPITAL-TERMS-V1 caps at admission", "source consumption <= distributed - served", "state machine monotone", "integer KRW, no volatile keys, no personal data", "constant false flags"],
        "guard_trace_verification": "replay of the FSM journal prefix at after_journal_index",
        "coa": "no postings; CAPITAL-COA-V1 unchanged",
        "closeout_digest": "unit test_count is a covered field; the implementing node regenerates the closeout digest and finance vectors per CAPITAL-CLOSEOUT-REGEN-V1",
        "consumers": ["claim-slice-registry", "export-manifest"]
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-18",
      "cap_rows": ["CAP-13", "CAP-14", "CAP-15"],
      "rationale": "Empty-is-absent keeps every existing digest and golden byte-identical, keeping derived values out of the digest keeps the fold pure, and overlay-only export leaves the seven obligation sections untouched.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  }
}
```

## 5. 수용 기준 매핑

| 수용 기준 | 충족 위치 |
|---|---|
| `CAPITAL_CLAIM_SLICE_REGISTRY.md`에 `capital-decision-v1` 블록이 있고 `python3 scripts/decision_ledger.py` 통과 | §4: 블록은 하나이고 열 항목이 모두 ADOPTED이며 모두 같은 표준 `provided_by`·ISO `date`·`value`·`provisional`을 가진다(리뷰 라운드 1에서 `shared_cap_accounting`의 `provided_by` 오기를 바로잡음). 이 결정자는 읽기 전용이라 스크립트를 **실행하지 않았다.** supervisor가 병합 시점에 확인한다. |
| `registry_storage_location`이 새 오버레이 섹션 여부, 엔트리 종류, 용량 상한을 말하고 OVERLAY_STATE 기존 엔트리를 바꾸지 않음 | §3.1, §3.9, 블록 `registry_storage_location`(`NEW_OVERLAY_SECTION`, 6종, 채택된 `overlay_id`/`kind`/`payload` 형태, `extends_overlay_state`: additive only) |
| `borrowing_base_double_use_guard`가 U3·U4 base·cap 공유, 이중 사용 방지, 바뀌는 점검을 명시 | §3.4(G0–G4, I-BASE, 바뀌는 점검 U3·U4), §3.3 |
| 청약 라벨 `SIMULATION_ONLY_NOT_OFFERED_V1`, 제3자 홀더·토큰화 슬라이스 `NOT_ADOPTED` | 머리말, §3.2, §3.8, 블록 최상위 `offering`·`third_party_holders`·`tokenised_slices` |
| 소비자 `claim-slice-registry` 명명, `docs/CAP_COVERAGE.md` 인용, `python3 -m unittest tests.test_decisions tests.test_coverage` 통과 | 모든 항목 `consumer`에 `claim-slice-registry`를 적었다. `docs/CAP_COVERAGE.md`는 허용 경로 밖이라 **수정·실행하지 않았다.** 이 항목은 **병합 전 닫아야 하는 열린 항목**이다: supervisor가 CAP-03(와 CAP-04·CAP-08) 행에 `docs/decisions/CAPITAL_CLAIM_SLICE_REGISTRY.md` 인용을 더한 뒤 두 테스트를 실행하고, 통과를 확인하기 전에는 이 기준을 충족했다고 주장하지 않는다. |

## 6. Open risks

- **선행 네 노트 미열람.** `CAPITAL_SHADOW_POLICY.md`, `CAPITAL_SETTLEMENT_POLICY.md`, `CAPITAL_OVERLAY_STATE.md`, `CAPITAL_FINANCIAL_TERMS.md`는 이 결정자가 직접 열지 못했다. 개정 라운드에서 검토자가 확인한 범위(세 cap 이름, U3/U4, 줄당 슬라이스 1개, 홀더 우선, 플랫폼 100 % 손실 부담, V1 홀더, U5 정의)에는 모순이 없다고 한다. 이는 2차 정보다. `quote_ref` 형식, 견적 면 필드명, 오버레이의 새 폴드 키 규칙, U6 정의는 아직 확인하지 못했다. 충돌하면 선행 노트가 이름·숫자를 이기고 구조는 이 노트를 따른다.
- **오버레이 엔트리 필드 위치.** 엔트리 형태는 `overlay_id`/`kind`/`payload`로 맞췄지만, `sim_day`·`after_journal_index`·`authority` 등이 엔벨로프인지 `payload`인지는 CAPITAL_OVERLAY_STATE가 정한다. 구현 노드는 그 노트를 따른다.
- **TERMS 소구 문구와의 좁힘 차이.** 이 노트는 V1 슬라이스 소구 회수를 폭포 ② 하나로 좁혔다(§3.6). TERMS의 "이후 회수 폭포" 문구와 맞추는 일이 남아 있고, 필요하면 `waterfall_step` 열거형에 값을 추가해 처리한다.
- **U3·U4 의미는 간접 인용.** U3 = 차입기초, U4 = 집중도·cap이라는 해석은 노드 설명과 `CAPITAL_DEMO_BOOK.md`에서 가져왔다. `advance_pledged`의 단위 변환(`reserved_open` ↔ 줄 면)은 보수적 기본값(줄 비율 안분, 올림)이며 구현 시 확인이 필요하다.
- **직렬화 가정.** 선지급 `draw`와 오버레이 명령이 같은 서비스 락 아래에 있다고 가정했다. 다르면 G4가 성립하지 않고 이중 사용 경합이 남는다.
- **면 기준 노출의 과대계상.** 가격이 아닌 면을 세므로 cap이 일찍 발화하고, 슬라이스 전용 sub-limit이 없어 슬라이스가 선지급 cap을 잠식할 수 있다. sub-limit이 필요한지는 조건 노트 소유자가 정할 일이다.
- **CAP_COVERAGE 인용 미완.** `docs/CAP_COVERAGE.md`가 이 노트를 아직 인용하지 않는다. 병합 전에 닫지 않으면 `tests.test_coverage`가 실패할 수 있다(§5).
- **법무·회계(작업 가정).** 소구 매입의 대부 취급, 상계 효력, 매각분의 도산 시 지위는 전문가 검토 대상이다.
- **미결 하위 항목.** 시간 기반 손상과 슬라이스 상각은 정하지 않았다. 손상 잔액은 노출에 계속 남는다.
- **그림자와 실효.** `OPEN` 슬라이스는 시뮬레이션 심사 결과를 바꾼다. 소유권·자금은 움직이지 않는다. 슬라이스 없는 책의 결과만 기존 골든과 바이트 동일하다.
- **2인 원칙은 인증이 아니다.** 로컬 파일을 쓸 수 있는 사람은 오버레이를 다시 쓸 수 있다.

## 7. 후속 작업

- **`claim-slice-registry`(구현 노드).** 폴드·6개 명령·거절 코드, `/api/overlay`의 `claim_slices` 조회, U3·U4 변경(`capital/underwriting.py`), 선지급 `draw` 재평가, ShadowPolicyPort `claim_purchase` 견적의 `registry_check`(읽기 전용), `tests/golden/overlay_claim_slices.json`, 이중 사용 속성 테스트(I-BASE)를 구현한다. 구현 시작 전 네 선행 노트를 열어 엔트리 필드 위치, U5·U6 정의, TERMS 소구 문구를 대조하고, 충돌이 있으면 §6 규칙대로 정리한다.
- **supervisor 병합 전 점검.** `docs/CAP_COVERAGE.md`에 인용을 더하고 `python3 scripts/decision_ledger.py`와 `python3 -m unittest tests.test_decisions tests.test_coverage`를 실행해 결과를 기록한다.
