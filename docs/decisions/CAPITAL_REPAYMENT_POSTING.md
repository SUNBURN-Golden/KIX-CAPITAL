# Capital 상환 기장(repayment posting) 결정 — 결제 명령, F04 repay 결합, 미적용 현금, close gate

> **PROVISIONAL PRODUCT DECISION (잠정 제품 결정).**
> 결정자: Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07) · 결정일 2026-10-17 · KIX-CAPITAL main `4d04a5b` · kix-protocol `244595d`
>
> 시뮬레이션·제품 설계 전용이다. 실자금, 은행·PG 관측, 청약은 없고 production은 계속 `NOT_AUTHORIZED`다. 회계·세무·법무에 닿는 값은 전문가 검토 전 작업 가정(WORKING ASSUMPTION)이며 자문이 아니다. 어떤 upstream 계약(`cr-06-repayment-allocation`, `fin-ledger-contract` 등)의 채택도 주장하지 않는다. diff는 이 노트 한 파일이고, `docs/CAP_COVERAGE.md` 인용 행은 supervisor가 추가한다. 이 결정자는 읽기 전용이라 `scripts/decision_ledger.py`와 unittest는 실행하지 않았다.

| 항목 | 값 |
|---|---|
| 결정 노드 | `repayment-posting-decision` · deps `repay-allocation-preview`, `sim-clock-ledger`, `margin-cure-default`, `overlay-digest-export-decision`, `financial-terms-decision` · kind `decision` · user_merge `False` |
| 위임 원문 | 2026-10-08 JunTae Park: "금융 조건, 정산 정책, 상위 연동, 회계·세무·법무는 일단 Fable이랑 진행해. 우리의 원대한 포부를 고려해서 진행하라고 해." |
| 소비 빌드 노드 | **`overlay-repayment-posting`** |
| 용어 | 금액은 KRW 정수, 비율은 bps, 날짜는 `sim_day`(논리 일, `SIM_LOGICAL_CLOCK`)다 |

## 1. 결정 요약

| item | 결정 (요지) | CAP rows | consumer |
|---|---|---|---|
| `payment_command_shape` | **ADOPTED.** wire `post_repayment`, `POST /api/overlay/commands`, role `organizer` + `overlay:command`. 필수 필드는 `operation_id`·`advance_ref`·`at_sim_day`·`amount_krw` 넷이고 선택 필드는 `evidence_ref`·`proposal_id`다. 분할·시각·납부자 신원은 클라이언트가 보내지 않는다 | CAP-01, CAP-11 | `overlay-repayment-posting` |
| `f04_repay_coupling` | **ADOPTED.** facade가 원금 몫의 F04 repay를 **같은 workspace save 안에서 직접 발행**한다(`ISSUE_F04_REPAY_SAME_SAVE`). 이자만 있는 납부는 F04를 부르지 않는다 | CAP-01, CAP-11 | `overlay-repayment-posting`, `PinnedFsmProducer` 경로 |
| `interest_payment_entry_schema` | **ADOPTED.** overlay entry kind `repayment`. 분할은 서버가 계산한다. 이자는 정확한 정수 분자로 누적한다(분모 3,650,000). 정산 대상은 whole-KRW floor이고 1원 미만 잔여(carry)는 버리지 않는다 | CAP-01, CAP-11 | fold, `repay-allocation-preview` |
| `unapplied_cash_handling` | **ADOPTED.** 초과분은 광고별 `SIM_UNAPPLIED_MEMO`로 한도(1억)까지 보류하고 다음 기장 때 적용한다. 환급 명령은 만들지 않는다 | CAP-01 | fold, UI |
| `close_gate_enforcement` | **ADOPTED.** **ADVISORY — close를 절대 거절하지 않는다.** `interest_due > 0`이면 `close_gate.status = INTEREST_DUE` 경고만 표시한다 | CAP-01, CAP-11 | `/api/overlay`, UI |
| `margin_cure_interaction` | **ADOPTED.** 기장은 cure/default fold의 **입력일 뿐**이다. 명령에 cure 필드가 없고 기장이 cure·default 상태를 쓰지 않는다 | CAP-01 | `margin-cure-default` fold |
| `idempotency_and_lost_response` | **ADOPTED.** 검사 순서는 shape → `operation_id` dedup → 선행조건·시계 CAS다. 부분 결과는 없고, 응답이 유실되면 receipt를 조회하거나 `UNKNOWN`이다 | CAP-11 | service 경로 |
| `capacity_and_envelope_effect` | **ADOPTED.** 금액 ≤ 10¹²원, advance당 기장 ≤ 600건, entry ≤ 1,024 canonical bytes. 초과하면 409 `SIMULATION_CAPACITY`이고 쓰기는 없다 | CAP-11 | `persistence-port` |
| `digest_and_golden_policy` | **ADOPTED.** `overlay_schema`와 digest 도메인 태그는 그대로이고 fold 내용만 바뀐다. `demo.json`과 `overlay_empty.json`은 바이트 동일하게 유지한다. `overlay_demo.json`은 새로 만든다(이미 있으면 이 노트를 인용해 한 번만 재생성한다) | CAP-11 | 테스트, `export-manifest` |

## 2. KIX 비전 연결

- `docs/CAPITAL_REQUIREMENTS_KO.md`는 원 요청·관측·금전 의무·실행을 분리하라고 한다. 그래서 F04 의무(원금 상환)와 overlay 관측(이자·미적용 메모)을 서로 다른 digest로 두고, 기장 entry는 `SIM_REPAY_MEMO` 라벨 메모로만 남긴다.
- `/workspace/capital-run/kixproto-ro/docs/decisions/AUTHORITY_MODEL_1.md` A-4에서 두 가지를 가져온다.
  - "침묵/timeout으로 미사용이라 간주 금지"를 lost response에 적용한다. 응답이 없어도 납부 여부는 확정하지 않고 `UNKNOWN`으로 둔다.
  - "과거 사실 재생은 새 외부 실행 허가가 아님"을 replay에 적용한다. replay는 기록된 F04 receipt를 읽기만 하고 producer를 다시 호출하지 않는다.
- `/workspace/capital-run/kixproto-ro/README.md` §3은 실자금·실 PG·은행을 잠그고 있다. 그래서 납부액은 operator가 주장한 값(`UNVERIFIED_ASSERTED`)이다. 은행 관측은 범위 밖이다.
- `docs/SEAMS.md`: `actor`는 인증이 아니다. `GateHttpProducer`가 응답을 잃으면 `UNKNOWN`이고 재시도하지 않는다. ProducerPort는 `NOT_BOUND`다. 이 때문에 원금 몫이 있는 기장은 in-process 핀 producer에서만 허용한다.
- `docs/VALIDATION.md`: 중복·충돌 receipt, reload fencing, lost-response→`UNKNOWN` 규칙을 그대로 잇는다.
- `docs/decisions/CAPITAL_OVERLAY_DIGEST_EXPORT.md`가 정한 구조를 쓴다.
  - 별도 overlay digest, V3 manifest, "빈 overlay = 부재", `advance_sim_day` CAS, `VOLATILE_KEYS` 금지.
  - 같은 노트의 `overlay_demo` 시나리오 "terms 바인딩 → 0→60 → repay"의 repay 단계가 이 노트의 명령이다.
- `docs/decisions/CAPITAL_FINANCIAL_TERMS.md` 발췌에서 단리·ACT/365·원금 잔액 기준·bps_annual·무수수료·`sim_day`를 가져온다. §3.3 본문은 pack 범위 밖이라 열지 않았고, 그 값을 다시 적지도 않는다.
- `docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md`: `SIM_REPAY_MEMO`와 `WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW`를 따른다. 이 노트에서 어떤 회계·세무 입장도 추론하지 않는다.
- `docs/decisions/CAPITAL_CLOSEOUT_ARTIFACT.md`: closeout digest 산출물은 이 노트로 바뀌지 않는다.

## 3. 항목별 결정

### 3.1 `payment_command_shape` — ADOPTED: `post_repayment`

- 같은 `/api/overlay/commands` 경로를 쓴다. role은 `organizer`이고 permission은 `overlay:command`다. Host/Origin/CSRF, strict input, `operation_id` dedup도 같다. 주체 라벨은 `LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED`다.
- 필드는 strict다. 모르는 키는 400이다. `amount_krw`는 정수 0..10¹²이고 bool·float·문자열은 거절한다.
  - `advance_ref`는 facade가 F04 명령에 이미 쓰는 advance 식별자다.
  - `at_sim_day`는 현재 `sim_day`와 같아야 한다. 다르면 409 `SIM_CLOCK_STALE`이고, 과거로 소급해 기장하는 길은 없다.
  - `evidence_ref`는 선택이고 `^[A-Za-z0-9._:-]{1,64}$`만 허용하며 `UNVERIFIED_ASSERTED`로 라벨한다. 계좌·성명·은행 참조는 받지 않는다(`NO_PERSONAL_DATA_BY_DESIGN_V1`).
  - `proposal_id`는 선택이고 agent 제안 `kind: REPAYMENT_POSTING`을 인용한다.
- agent lane은 제안만 남길 수 있고 기장을 적용하지 못한다.
- 선행조건(실패하면 쓰기 없음)은 다음과 같다.
  - `workspace_status == ACTIVE`.
  - terms가 바인딩되어 있을 것(없으면 409 `REPAYMENT_TERMS_NOT_BOUND`).
  - advance가 F04에 존재할 것.
- receipt에는 `entry_no`, 분할, `f04` 참조, `unapplied_after_krw`, `close_gate`, `label: SIMULATED`가 들어간다.

### 3.2 `f04_repay_coupling` — ADOPTED: ISSUE_F04_REPAY_SAME_SAVE

- **이유.** overlay는 `sim_day`를 가진 유일한 곳이고 F04 journal에는 시각이 없다. 원금 감소가 overlay entry 없이 일어나면 이자 계산 기준일을 알 수 없다. 그래서 원금 감소와 기장을 한 번에 묶는다.
- **절차.** workspace lock 안에서 순서대로 진행한다.
  1. F04 미상환 원금과 overlay fold를 읽는다.
  2. 분할을 계산한다(§3.3).
  3. `principal_krw > 0`이면 in-process `PinnedFsmProducer`로 F04 repay를 정확히 그 금액만큼 발행한다.
  4. overlay entry를 붙이고 `after_journal_index`는 F04 명령 반영 후 journal 길이로 한다.
  5. 원자적 save를 **한 번** 한다.
  - 어느 단계든 실패하면 메모리 상태를 되돌리고 쓰기는 0이다.
- F04 operation id는 `rp-` + `sha256("KIX_CAPITAL_REPAY_F04_V1|" + operation_id)`의 앞 32 hex로 결정적으로 만든다. 하나의 `operation_id`로 두 receipt를 모두 조회할 수 있다.
- **overlay는 FSM을 gate하지 않는다.** overlay는 금액만 계산하고, F04의 수락·거절은 핀 FSM이 정한다. F04가 거절하면 409 `REPAYMENT_ADVANCE_STATE`이고 쓰기는 없다.
- 원금 몫이 0보다 큰데 producer가 in-process 핀이 아니면(`gate-fake` 등) 409 `REPAYMENT_PRODUCER_UNSUPPORTED`이고 쓰기는 없다. 원자성이 없는 경로에서 부분 상태를 만들지 않기 위해서다.
- 기존 `/api/commands`의 직접 F04 repay는 그대로 합법이고 바이트도 바뀌지 않는다. overlay가 비어 있지 않을 때 기장 없는 F04 repay가 있으면 다음 규칙으로 처리한다.
  - 해당 journal 위치에서 유효한 `sim_day`로 귀속한다(그 위치까지의 clock entry를 fold한 값).
  - fold `warnings`에 `UNPOSTED_F04_REPAY`를 올린다.
  - overlay는 원금 값을 복제하지 않고 항상 F04에서 읽는다.

### 3.3 `interest_payment_entry_schema` — ADOPTED

- entry 필드: `kind:"repayment"`, `entry_no`, `operation_id`, `after_journal_index`, `sim_day`, `advance_ref`, `amount_krw`, `unapplied_before_krw`, `allocation{default_interest_krw, interest_krw, principal_krw, unapplied_after_krw}`, `witness`, `terms_binding{terms_version}`, `f04_operation_id`(없으면 null), `f04_receipt_ref`, `evidence_ref?`, `proposal_id?`, `label:"SIMULATED"`, `basis:"SIM_REPAY_MEMO"`. 시각 키(`VOLATILE_KEYS`)는 금지다.
- 불변식: `amount_krw + unapplied_before_krw = default_interest_krw + interest_krw + principal_krw + unapplied_after_krw`.
- **분할은 서버만 계산한다.** `repay-allocation-preview`와 **같은 함수**를 쓴다. 충당 순서는 CAPITAL_FINANCIAL_TERMS §3.3이 정한 것을 따르고 이 노트는 재결정하지 않는다. 이 노트의 예시는 `default_interest → interest → principal`(민법 제479조 비용·이자·원본 순서에 맞춘 작업 가정)을 전제한다. 빌드 테스트 `allocation_order_matches_terms`가 §3.3과 어긋나면 중단하고 이 결정을 다시 연다.
- **정확한 잔여 이월(exact-remainder carry).**
  - 분모는 D = 10000 × 365 = 3,650,000이다.
  - 누적 분자는 정수 Σ(원금 × bps × 일수)이다. pot은 `accrued_interest_num`과 `accrued_default_num` 둘이다.
  - 분자는 JS 정밀도 문제를 피하려고 10진 문자열로 직렬화한다.
  - `due_krw = floor(accrued_num / D) − paid_krw`이고, carry = `accrued_num mod D`는 항상 `[0, D)` 범위의 파생값이다.
  - 납부는 whole-KRW만 소거하므로 1원 미만 carry는 사라지거나 두 번 계산되지 않는다. 일수를 나눠 전진해도 합계가 같다(`split_invariance` 벡터).
  - 상한(총 2,000 bps/yr)·만기 후 가산은 terms가 정하는 accrual fold의 책임이다. 기장은 두 pot의 due만 읽는다.
- `witness`는 기장 직전의 분자 두 개, 기납입액 두 개, 직전 원금을 담는다. 로드할 때 fold가 재계산하고, 불일치하면 기존 FOLD_THEN_VERIFY 경로로 envelope을 fail closed 거부한다.
- 원천징수 등 세무 처리는 모델링하지 않는다.

### 3.4 `unapplied_cash_handling` — ADOPTED: HOLD_BOUNDED_APPLY_ON_NEXT_POSTING

- (default 이자 + 이자 + F04 미상환 원금)을 넘는 금액은 advance별 `unapplied_cash_krw`(`SIM_UNAPPLIED_MEMO`)로 보류한다. 채권·부채·수익이 아니고 이자도 붙지 않는다.
- 한도는 advance당 1억원(합성 단위)이다. 초과하면 409 `REPAYMENT_UNAPPLIED_CAP`이고 쓰기는 없다.
- 보류분은 같은 advance의 **다음 기장에서 가용 현금에 먼저 합산**한다. 시계 전진 때 자동 적용하지 않는다. 명령을 늘리지 않으려고 `amount_krw = 0`을 `unapplied_before > 0`일 때만 허용한다(적용 전용). 그 외 0은 400 `REPAYMENT_AMOUNT`이다.
- 보류분은 cure 판정과 노출 감소에 쓰지 않는다. 적용된 뒤에만 인정한다.
- F04 closed 이후에도 기장은 받는다. 이자 잔여가 먼저이고 나머지는 보류한다.
- 환급·지급 명령은 만들지 않는다(DEFERRED). 마감 시 남은 보류는 `UNAPPLIED_AT_CLOSE`로 표시한다. 보류 현금의 법적 성격(예수금 등)과 계정 매핑은 전문가 검토 전까지 아무 입장도 취하지 않는다.

### 3.5 `close_gate_enforcement` — ADOPTED: ADVISORY_NEVER_REJECTS_F04_CLOSE

- overlay `interest_due > 0`이어도 F04 `close`는 거절하지 않는다. "FSM은 overlay로 gate되지 않는다" 규칙을 FSM뿐 아니라 facade 사전검사 층까지 확장해 유지한다.
- **이유.**
  1. 면제나 상각 명령이 없는 상태에서 gate를 걸면 이자를 못 받은 건이 닫히지 못하는 교착이 생긴다.
  2. 빈 overlay에서는 close 경로가 바이트 단위로 같아야 한다.
  3. replay가 overlay에 의존하면 안 된다.
- 대신 `close_gate` 블록을 노출한다(overlay가 비어 있지 않을 때만). 이것은 `GET /api/overlay`와 `/api/state`에 들어가고 UI는 close 버튼 옆에 비차단 경고를 보여 준다.
  - `status`: `CLEAR | INTEREST_DUE | UNAPPLIED_HELD`.
  - 필드: `default_interest_due_krw`, `interest_due_krw`, `unapplied_cash_krw`.
- close 이후 accrual은 close가 귀속된 `sim_day`에서 멈추고 잔여는 동결한다(`closed_with_interest_due`). 이후 이자 몫만 기장해 소거할 수 있다.
- 면제·상각 명령이 생기면 새 결정 노트로만 이 판단을 다시 연다.

### 3.6 `margin_cure_interaction` — ADOPTED: POSTING_IS_INPUT_ONLY

- 명령에 `cure_ref` 같은 필드는 없고, 기장은 cure·default 상태를 쓰지 않는다. cure/default는 `margin-cure-default`가 소유한 **순수 fold**이고 기장 entry의 `sim_day`와 `allocation`만 읽는다.
- 순서는 overlay journal의 `entry_no` 순이 정본이다. 마감일 당일의 기장이 `advance_sim_day` 전진보다 먼저 기록되면 기한 안으로 인정하고, 나중이면 인정하지 않는다. 마감일 비교(경계 포함 여부)는 그 노트가 정한다.
- 이미 default인 advance에도 기장은 같은 분할로 받는다. agent는 cure할 수 없다. 보류 현금은 인정하지 않는다.

### 3.7 `idempotency_and_lost_response` — ADOPTED

- 검사 순서: ① strict shape(400) → ② `operation_id` dedup → ③ 선행조건·시계 CAS → ④ 용량 → ⑤ 적용. **dedup이 CAS보다 먼저**여서, 응답을 잃은 뒤 시계가 전진해도 같은 요청은 원래 receipt를 돌려받는다.
- 동일 본문 재전송은 원 receipt를 돌려주고 entry와 F04 repay를 다시 만들지 않는다. 같은 id에 다른 본문이면 기존 충돌 거절 규칙을 따르고 쓰기는 없다. 거절은 쓰기도 receipt도 없고 id는 계속 쓸 수 있다.
- 단일 save이므로 결과는 APPLIED, 거절(쓰기 없음), `UNKNOWN`(응답 유실) 셋뿐이다. 응답이 유실되면 `operation_id`로 조회한다. 없으면 `UNKNOWN`이고 자동 재시도는 하지 않는다. 같은 id로 운영자가 수동 재전송하는 것은 안전하다.

### 3.8 `capacity_and_envelope_effect` — ADOPTED

- `amount_krw ≤ 1,000,000,000,000`. advance당 `repayment` entry는 600건 이하다(3,650일 기준 주 1회보다 넉넉하다). entry 하나의 canonical 크기는 1,024 bytes 이하이고 테스트로 확인한다.
- 기장은 CAPITAL_OVERLAY_STATE의 공유 overlay entry·envelope 한도에도 계산된다. 초과하면 409 `SIMULATION_CAPACITY`이고 쓰기는 없다. envelope 바이트 한도에 먼저 닿으면 600은 **낮추기만** 한다. `SIM_DAY_MAX(3650)`은 그대로다.

### 3.9 `digest_and_golden_policy` — ADOPTED

- **F04 `state_digest`**: 원금 몫이 있는 기장에서만 바뀐다. 그 변화는 실제 F04 명령이 journal에 들어가서 생기는 정상적인 결과다. `payload_sha256`도 같은 이유로, 해당 workspace에서만 바뀐다.
- **`overlay_state_digest`**: 기장 entry와 `state.repayment` 블록(광고별 기납입 이자·원금, 보류 현금, `close_gate`, `warnings`)이 fold에 들어가므로 바뀐다. 도메인 태그 `KIX_CAPITAL_OVERLAY_STATE_DIGEST_V1`과 `overlay_schema: 1`은 유지한다. 이전 결정의 `overlay_demo` 시나리오가 이미 repay 단계를 전제하므로 schema를 올리지 않는다.
- **V3 manifest**: `content_digest`는 바뀐다. 섹션 집합(7 + `overlay`), overlay 섹션 필드 목록, recon 조건부 검사 한 개(`overlay_fold_digest_equals_persisted`)는 그대로다. 이 검사가 기장 행도 덮는다. 빈 overlay의 V2는 바이트 동일하다.
- **golden**:
  - `tests/golden/demo.json`과 `tests/golden/overlay_empty.json`은 바이트 동일해야 하며, 바뀌면 blocking 회귀다.
  - `tests/golden/overlay_demo.json`은 `overlay-repayment-posting`이 만든다. 시나리오는 terms 바인딩 → `advance_sim_day` 0→60 → `post_repayment`(이자 전액 + 원금 일부, F04 repay 발행)이다. 파일이 이미 있으면 이 노트를 인용한 커밋으로 **한 번만** 재생성할 수 있다.
  - CI 자동 재생성은 금지다. 추가 벡터는 golden이 아닌 테스트로 둔다: 과납→보류, 0원 적용, 오래된 시계, dedup 우선, 미지원 producer, F04 거절 롤백, replay 시 producer 미호출, 한도.

## 4. capital-decision-v1

```capital-decision-v1
{
  "schema": "capital-decision-v1",
  "decision_id": "repayment-posting-decision",
  "decided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
  "date": "2026-10-17",
  "provisional": true,
  "entries": {
    "payment_command_shape": {
      "status": "ADOPTED",
      "value": {
        "command": "post_repayment",
        "endpoint": "POST /api/overlay/commands",
        "role": "organizer",
        "permission": "overlay:command",
        "fields": ["operation_id", "advance_ref", "at_sim_day", "amount_krw"],
        "optional_fields": ["evidence_ref", "proposal_id"],
        "strict": "UNKNOWN_KEYS_400_NO_CLIENT_SPLIT_NO_TIMESTAMP_NO_PAYER_IDENTITY",
        "amount_krw": "INT_0_TO_1000000000000_BOOL_FLOAT_STRING_REJECTED",
        "clock_fence": "at_sim_day_EQUALS_CURRENT_ELSE_409_SIM_CLOCK_STALE",
        "actor_label": "LOCAL_OPERATOR_SESSION_NOT_AUTHENTICATED",
        "agent_lane": "PROPOSAL_ONLY_kind_REPAYMENT_POSTING",
        "preconditions": ["workspace_status_ACTIVE", "terms_bound_else_409_REPAYMENT_TERMS_NOT_BOUND", "advance_known_to_F04"],
        "facade_issues_f04_principal_repay": true
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-01", "CAP-11"],
      "rationale": "One strict operator command on the existing overlay command path, clock-fenced like advance_sim_day, with no client-supplied split or payer identity so the server is the only allocator and no personal data enters the overlay.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "f04_repay_coupling": {
      "status": "ADOPTED",
      "value": {
        "mode": "ISSUE_F04_REPAY_SAME_SAVE",
        "f04_call": "PRINCIPAL_PORTION_ONLY_VIA_IN_PROCESS_PinnedFsmProducer",
        "interest_only_posting": "NO_F04_CALL_F04_DIGEST_UNCHANGED",
        "f04_operation_id": "rp- + sha256(KIX_CAPITAL_REPAY_F04_V1|operation_id) first 32 hex",
        "atomicity": "F04_COMMAND_AND_OVERLAY_ENTRY_IN_ONE_WORKSPACE_SAVE_UNDER_WORKSPACE_LOCK_ANY_FAILURE_ZERO_WRITE",
        "f04_reject": "409_REPAYMENT_ADVANCE_STATE_NO_WRITE",
        "unsupported_producer": "409_REPAYMENT_PRODUCER_UNSUPPORTED_WHEN_PRINCIPAL_GT_0_NO_WRITE",
        "overlay_gates_fsm": false,
        "principal_source": "F04_OUTSTANDING_READ_NEVER_DUPLICATED",
        "direct_f04_repay_path": "UNCHANGED_LEGAL_UNPOSTED_ATTRIBUTED_TO_SIM_DAY_IN_FORCE_PLUS_WARNING",
        "replay": "FOLD_RECORDED_f04_receipt_ref_NEVER_CALLS_PRODUCER"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-01", "CAP-11"],
      "rationale": "Only the overlay carries sim_day, so a principal reduction without an overlay entry has no interest accrual date; issuing the F04 repay inside the same single-envelope save removes the half-posted window while the overlay only computes the amount and never gates the pinned FSM.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "interest_payment_entry_schema": {
      "status": "ADOPTED",
      "value": {
        "entry_kind": "repayment",
        "fields": ["kind", "entry_no", "operation_id", "after_journal_index", "sim_day", "advance_ref", "amount_krw", "unapplied_before_krw", "allocation", "witness", "terms_binding", "f04_operation_id", "f04_receipt_ref", "evidence_ref", "proposal_id", "label", "basis"],
        "allocation_fields": ["default_interest_krw", "interest_krw", "principal_krw", "unapplied_after_krw"],
        "allocation_invariant": "amount_krw+unapplied_before_krw=default_interest_krw+interest_krw+principal_krw+unapplied_after_krw",
        "allocation_source": "SHARED_PREVIEW_FUNCTION_ORDER_FROM_FINANCIAL_TERMS_3_3_NOT_RESTATED",
        "interest_math": "EXACT_INTEGER_NUMERATOR_DENOMINATOR_3650000",
        "pots": ["accrued_interest_num", "accrued_default_num"],
        "numerator_serialization": "DECIMAL_STRINGS",
        "due_rounding": "FLOOR_WHOLE_KRW_SUBWON_CARRY_DERIVED_NEVER_ROUNDED_OR_LOST",
        "split_invariance": true,
        "fold_verify": "WITNESS_RECOMPUTED_ON_LOAD_MISMATCH_FAIL_CLOSED",
        "volatile_keys": "REJECT_400_OVERLAY_VOLATILE_KEY",
        "label": "SIMULATED",
        "memo_basis": "SIM_REPAY_MEMO",
        "tax_withholding": "NOT_MODELED"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-01", "CAP-11"],
      "rationale": "Simple ACT/365 bps interest is exactly representable as an integer numerator over 3,650,000, so whole-KRW floor dues with a derived sub-won carry make payments path-independent without rounding disputes, and a stored witness lets the load-time fold verify every entry.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "unapplied_cash_handling": {
      "status": "ADOPTED",
      "value": {
        "mode": "HOLD_BOUNDED_APPLY_ON_NEXT_POSTING",
        "excess": "HELD_PER_ADVANCE_AS_SIM_UNAPPLIED_MEMO",
        "max_krw_per_advance": 100000000,
        "cap_exceeded": "409_REPAYMENT_UNAPPLIED_CAP_NO_WRITE",
        "zero_amount": "ALLOWED_ONLY_WHEN_UNAPPLIED_BEFORE_GT_0_ELSE_400_REPAYMENT_AMOUNT",
        "auto_apply_on_clock_advance": false,
        "interest_bearing": false,
        "counts_for_cure_or_exposure": false,
        "closed_advance": "INTEREST_RESIDUAL_FIRST_THEN_UNAPPLIED",
        "refund_or_payout": "DEFERRED_NO_COMMAND",
        "accounting_tax_legal_position": "NONE_WORKING_ASSUMPTION_PENDING_PROFESSIONAL_REVIEW"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-01"],
      "rationale": "Recording an asserted overpayment as a bounded memo keeps the ledger honest without inventing a payout flow or a legal characterization, and applying it only on the next explicit posting avoids hidden activity on clock advance.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "close_gate_enforcement": {
      "status": "ADOPTED",
      "value": {
        "mode": "ADVISORY_NEVER_REJECTS_F04_CLOSE",
        "interest_due_gt_0": "CLOSE_ALLOWED_STATUS_INTEREST_DUE",
        "fsm_never_gated_rule": "PRESERVED_INCLUDING_FACADE_PRECHECK_LAYER",
        "close_gate_block": {
          "status": ["CLEAR", "INTEREST_DUE", "UNAPPLIED_HELD"],
          "fields": ["default_interest_due_krw", "interest_due_krw", "unapplied_cash_krw"]
        },
        "surfaces": "GET_api_overlay_and_api_state_ONLY_WHEN_OVERLAY_NON_EMPTY_UI_NON_BLOCKING_WARNING",
        "after_close": "ACCRUAL_FREEZES_RESIDUAL_FROZEN_INTEREST_ONLY_POSTINGS_ALLOWED",
        "reconsider": "ONLY_BY_NEW_DECISION_AFTER_WAIVER_OR_WRITE_OFF_COMMAND_EXISTS"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-01", "CAP-11"],
      "rationale": "With no waiver or write-off command a hard gate would strand loans whose interest is never paid, and gating close would make the pinned F04 path depend on overlay state and break empty-overlay byte identity; a visible advisory plus a frozen residual keeps both the rule and the information.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "margin_cure_interaction": {
      "status": "ADOPTED",
      "value": {
        "mode": "POSTING_IS_INPUT_ONLY",
        "cure_default_fields_in_command": false,
        "posting_writes_cure_or_default_state": false,
        "evaluation": "PURE_FOLD_OF_JOURNAL_OWNED_BY_margin-cure-default",
        "ordering": "entry_no_ORDER_SAME_DAY_POSTING_BEFORE_CLOCK_ADVANCE_COUNTS",
        "in_time_basis": "entry.sim_day_AND_entry.allocation_ONLY",
        "deadline_boundary": "OWNED_BY_margin-cure-default",
        "unapplied_cash": "NOT_COUNTED_UNTIL_APPLIED",
        "defaulted_advance": "POSTINGS_ACCEPTED_SAME_ALLOCATION",
        "agent_lane": "CANNOT_CURE"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-01"],
      "rationale": "Keeping cure and default as a derived fold of the journal, with posting contributing only sim_day and allocation, avoids two writers of one state and makes order within a day deterministic from the overlay journal.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "idempotency_and_lost_response": {
      "status": "ADOPTED",
      "value": {
        "order_of_checks": ["strict_shape_400", "operation_id_dedup", "preconditions_and_clock_cas", "capacity", "apply"],
        "identical_replay": "ORIGINAL_RECEIPT_NO_SECOND_ENTRY_NO_SECOND_F04_REPAY",
        "same_id_different_body": "EXISTING_CONFLICT_REJECTION_NO_WRITE",
        "rejection": "NO_WRITE_NO_RECEIPT_ID_REMAINS_FREE",
        "lost_response": "LOOKUP_BY_OPERATION_ID_ELSE_UNKNOWN_NO_AUTO_RETRY_MANUAL_SAME_ID_RESEND_SAFE",
        "partial_outcomes": "IMPOSSIBLE_SINGLE_ATOMIC_SAVE",
        "silence_means": "NEITHER_PAID_NOR_UNPAID"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-11"],
      "rationale": "Putting dedup before the clock CAS lets a lost-response retry succeed after the clock has advanced, and a single atomic save means the only uncertain outcome is UNKNOWN, matching AUTHORITY_MODEL_1 A-4 that silence is not evidence of non-payment.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "capacity_and_envelope_effect": {
      "status": "ADOPTED",
      "value": {
        "amount_max_krw": 1000000000000,
        "entries_per_advance_max": 600,
        "entry_canonical_bytes_max": 1024,
        "unapplied_max_krw_per_advance": 100000000,
        "shared_caps": "COUNTS_TOWARD_OVERLAY_ENTRY_AND_ENVELOPE_CAPS_OF_CAPITAL_OVERLAY_STATE_409_SIMULATION_CAPACITY_NO_WRITE",
        "sim_day_max": "UNCHANGED_3650",
        "tune_rule": "entries_per_advance_max_MAY_ONLY_DECREASE_IF_ENVELOPE_BYTES_REACHED_FIRST"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-11"],
      "rationale": "Bounds keep amounts inside the JS safe-integer range and the journal inside the shared overlay capacity, failing closed with no write rather than truncating.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    },
    "digest_and_golden_policy": {
      "status": "ADOPTED",
      "value": {
        "f04_state_digest": "CHANGES_ONLY_WHEN_PRINCIPAL_PORTION_GT_0_AS_A_REAL_F04_COMMAND",
        "payload_sha256": "SAME_CONDITION_COVERS_PAYLOAD_ONLY",
        "overlay_state_digest": "CHANGES_REPAYMENT_ROWS_AND_STATE_REPAYMENT_BLOCK_ENTER_FOLD",
        "domain_tag_and_overlay_schema": "UNCHANGED_KIX_CAPITAL_OVERLAY_STATE_DIGEST_V1_SCHEMA_1",
        "v3_manifest": "CONTENT_DIGEST_CHANGES_SECTION_SET_AND_RECON_CHECK_LIST_UNCHANGED",
        "v2_manifest_empty_overlay": "BYTE_IDENTICAL",
        "golden_demo_json": "UNCHANGED_BYTE_IDENTICAL_BLOCKING_IF_CHANGED",
        "golden_overlay_empty_json": "UNCHANGED",
        "golden_overlay_demo_json": "CREATE_OR_ONE_REGENERATION_CITING_THIS_NOTE",
        "overlay_demo_scenario": "terms binding -> advance_sim_day 0->60 -> post_repayment interest plus partial principal with F04 repay",
        "auto_regeneration": "FORBIDDEN",
        "consuming_build_node": "overlay-repayment-posting"
      },
      "provided_by": "Sonnet 5.5 xhigh (Fable 5.1 after 3 failed attempts), delegated by JunTae 2026-10-08 (lanes 10-16 09:07)",
      "date": "2026-10-17",
      "cap_rows": ["CAP-11"],
      "rationale": "The prior digest note already presumes a repay step in the overlay_demo scenario, so repayment extends schema 1 rather than bumping it; the default demo path never posts, so empty-overlay goldens stay byte-identical and only the new overlay golden captures the change.",
      "provisional": true,
      "basis": "PRODUCT_DECISION"
    }
  },
  "status": "PROVISIONAL_PRODUCT_DECISION"
}
```

## 5. 수용 기준 매핑

- **capital-decision-v1 블록**: §4에 하나 있고, provisional이 true이며 아홉 항목이 모두 ADOPTED다. `decision_ledger.py` 통과 여부는 supervisor가 병합 시점에 확인한다.
- **`payment_command_shape`**: wire `post_repayment`, strict 필드, role `organizer` + `overlay:command`를 §3.1에 두었다. facade가 F04 원금 repay를 **직접 발행**하며, 같은 save 안이라는 점은 §3.2에 있다.
- **`close_gate_enforcement`**: ADVISORY로, 기존 "FSM은 overlay로 gate되지 않는다" 규칙을 유지한다(§3.5).
- **digest·manifest·golden**: §3.9에 있다. 소비 빌드 노드는 `overlay-repayment-posting`이다.
- **`docs/CAP_COVERAGE.md`**: 읽기 범위 밖이라 편집하지 않았다. supervisor가 CAP-01·CAP-11 행에 `CAPITAL_REPAYMENT_POSTING.md`를 인용하는 행을 추가하고 `python3 -m unittest tests.test_decisions tests.test_coverage`를 돌려야 한다.

## 6. Open risks

- CAPITAL_FINANCIAL_TERMS §3.3 본문은 pack에서 잘려 있어 보지 못했다. 분모 3,650,000 모델은 발췌(단리·ACT/365·bps)에서 도출했고, 충당 순서는 재결정하지 않았다. §3.3과 어긋나면 빌드가 중단되고 이 결정을 다시 연다.
- 핀 F04 repay의 부분 금액 의미와 필드명은 pack에 없었다. F04가 거절하면 명령 전체를 거절하도록(fail closed) 정했다. 핀 FSM이 전액 상환만 받는다면 부분 원금 납부는 upstream 변경 전까지 쓸 수 없다. `advance_ref`는 기존 facade 식별자로 가정했다.
- 원자성은 in-process 핀 producer와 단일 envelope save에서만 성립한다. 이것은 stage5 내구 트랜잭션이 아니며 CAP-11은 `NOT_BOUND`로 남는다.
- 기장 없는 직접 F04 repay는 기준일 귀속이 휴리스틱이라 이자를 과소·과대 추정할 수 있다. 경고만 있고 recon 검사는 늘리지 않았다.
- close가 advisory여서 이자 잔여를 둔 채 닫히는 건이 생긴다. 면제·상각 경로는 없다.
- 납부액은 operator가 주장한 값이며 은행 관측이 아니다. 로컬 파일을 쓸 수 있는 사람은 entry를 다시 쓸 수 있다. 보류 현금의 법적 성격은 평가하지 않았다.
- `margin-cure-default`의 마감일 경계와 cure 정의는 pack에 없어서 그 노트에 위임했다.

## 7. 후속 작업

- `overlay-repayment-posting`: 명령, 공유 분할 함수, fold, witness 검증, §3.9의 벡터, `overlay_demo.json`, UI의 close 경고를 구현한다.
- supervisor: CAP_COVERAGE 행을 추가하고 ledger와 unittest를 확인한다.
- `margin-cure-default` 빌드: cure fold가 기장 행을 읽도록 연결하고 같은 날 순서 벡터를 추가한다.
- 후속 결정 후보: 면제·상각 명령, 보류 현금 환급, close gate 재검토, `SIM_UNAPPLIED_MEMO`의 COA 후보 매핑.
