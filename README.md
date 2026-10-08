# KIX Capital

로컬 합성 데이터로 Capital의 정산 근거 → 제안 → 모의 승인 → 노출 기록 → 상환 메모 → 종결·재생 검증을 연결하는 개발용 제품입니다. **전체 Capital 청사진 완료·실대출·신용심사·운영 출시가 아닙니다.**

## 실행

Python 3.10 이상, runtime 패키지 설치나 DB 없이 실행합니다.

```sh
python3 -m capital.server
# http://127.0.0.1:8765
```

최신 Chromium/Chrome/Edge에서 열어 주세요. 주소는 `127.0.0.1`이며 외부 host/Origin 요청을 거절합니다. 메모리 상태는 서버 재시작 시 사라집니다. 금액·역할·공연은 합성 fixture만 사용하며 실명·계좌·신용정보 입력란이 없습니다.

## 구현과 경계

- Capital 전용 loopback API와 웹 화면, 포트폴리오, 세 가지 정산/환불 fixture.
- Protocol의 F04 상태기계를 정확한 소스 SHA 및 파일 hash에 고정한 로컬 참조 adapter. 산술·원본 FSM은 수정하지 않습니다.
- 같은 operation의 최초 결과/충돌 검사, 공유 액면 경합, 부분 상환·미이행·종결, 재생 일치.
- 응답 유실 시 UNKNOWN, 브라우저 새로고침 뒤 원 receipt 조회, 새 쓰기 차단. 자동 재시도 없음.
- API는 별도의 `UNBOUND` 목 draw를 허용하는 F04 의미를 유지합니다. 화면의 기본 여정은 정산 결합을 먼저 요구합니다.
- F01–F03 고정 시나리오 9개·35단계: 부족 현금의 배정 순서 비교, 부분/전액 환불, 회수 의무, 중복/상충 관측, 늦은 현금. 별도 메모리에서 재생하며 작업 중 제안을 변경하지 않습니다.
- 선택 제안의 읽기 전용 인출 사전점검과 20개 청사진 요구사항의 구현/결정/연동 선행 필터.
- 수락된 저널과 불변 정산 fixture를 고정 합성 계정표로 읽는 로컬 복식 투영 후보. `accounting_policy`는 `SYNTHETIC_UNADOPTED`이고, 세무·법무·운영 원장은 `NOT_BOUND`이며 `fin-ledger-contract`를 채택하지 않습니다.
- 원본 목 정산 조회·노출·현금·회수 의무는 서로 다른 의미입니다. 합계를 실제 은행 잔액으로 표시하지 않습니다.

[청사진 요구사항·선행 매핑](docs/CAPITAL_REQUIREMENTS_KO.md), [API·연동 경계](docs/INTEGRATION.md), [검증 범위](docs/VALIDATION.md)를 참고하세요. 채택된 금융 원장·수익참여·채권양수·담보/준비금·다중 자산·실제 Commerce/Protocol 연동은 정의와 선행조건을 유지하며 미구현 상태를 표시합니다. 로컬 복식 투영은 비채택 후보입니다.

## 검증

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v
npm ci
npx playwright install chromium
npm run test:browser
```

CI는 동일 검사를 새 HEAD마다 실행합니다. UI 자동 검증과 독립 코드 리뷰는 실제 사용자 수용·아키텍처 승인·운영 승인과 구분합니다. Python HTTP 서버와 메모리 receipt는 개발용이며 내구 원장·멀티테넌트 인증·분산 잠금이 아닙니다.
