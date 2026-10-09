# CAP-01..CAP-20 커버리지

이 표는 요구사항 20개를 빼지 않은 분모다. 한 행이 로컬 후보라는 것은 그 행이 끝났다는 뜻이 아니다. `upstream_nodes_completed`는 빈 목록으로 남는다.

상태 칸은 `SIMULATED`, `READ_ONLY_FIXTURE`, `NOT_BOUND`, `DECISION_REQUIRED`, `NOT_AUTHORIZED` 중 하나다. [요구사항 문서](CAPITAL_REQUIREMENTS_KO.md) 상태 칸에서 처음 나오는 같은 토큰과 맞아야 한다. 준비도 그룹이 겹치면 그 그룹들이 허용하는 상태의 합집합 안에 있어야 한다.

`product-journey`는 노드 슬러그가 생기기 전의 PR #1(`a87977b`, Build Capital simulation product journey)이다. 이후 노드가 그 행을 대신 소유하지 않는다.

`terms-overlay`는 이 트리의 읽기 전용 시뮬레이티드 오버레이다. CAP-01과 CAP-04는 [docs/decisions/CAPITAL_FINANCIAL_TERMS.md](decisions/CAPITAL_FINANCIAL_TERMS.md)의 **상태: PROVISIONAL PRODUCT DECISION (잠정 제품 결정).** (`CAPITAL-TERMS-V1`)을 인용한다. 청약·upstream 채택이 아니다. CAP-02와 CAP-03의 잠정 값은 [docs/decisions/CAPITAL_SETTLEMENT_POLICY.md](decisions/CAPITAL_SETTLEMENT_POLICY.md)에 있으나 상태 칸은 요구사항·준비도와 같이 `DECISION_REQUIRED`다. 계정·세무 잠정 노트는 [docs/decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md](decisions/CAPITAL_ACCOUNTS_TAX_LEGAL.md)이고, 바인딩 잠정 노트는 [docs/decisions/CAPITAL_UPSTREAM_BINDING.md](decisions/CAPITAL_UPSTREAM_BINDING.md)다. 그 노트의 `DEFERRED`·`NOT_ADOPTED`는 제품 연결이 아니다. 없는 결정 노트는 원장에서 PENDING이며, 이 표가 그 내용을 만들지 않는다. 근거에 upstream이라고 적은 이름은 채택되지 않았다.

| ID | 요구 | 소유 노드 / 결정 노트 | 상태 | 근거 |
|---|---|---|---|---|
| CAP-01 | 대여·선지급 전 기간 | docs/decisions/CAPITAL_FINANCIAL_TERMS.md | SIMULATED | 로컬 F04 여정은 합성이다. 읽기 전용 오버레이가 docs/decisions/CAPITAL_FINANCIAL_TERMS.md (CAPITAL-TERMS-V1, PROVISIONAL PRODUCT DECISION)를 표시한다. 청약이 아니고 upstream 채택이 아니다. |
| CAP-02 | 수익참여·배분 | docs/decisions/CAPITAL_SETTLEMENT_POLICY.md | DECISION_REQUIRED | 잠정 노트 `settlement-policy-decision`의 `revenue_participation`이다. 제품에 적용되지 않았고 준비도 그룹은 DECISION_REQUIRED다. 이 표가 비율·상한·회수 순서를 정하지 않는다. |
| CAP-03 | 정산채권 양도·매입 | docs/decisions/CAPITAL_SETTLEMENT_POLICY.md | DECISION_REQUIRED | 잠정 노트 `settlement-policy-decision`의 `claim_purchase`다. 제품에 적용되지 않았고 준비도 그룹은 DECISION_REQUIRED다. 이 표가 배정량·보유자·대가·우선순위를 정하지 않는다. |
| CAP-04 | 담보·준비금 | docs/decisions/CAPITAL_FINANCIAL_TERMS.md | SIMULATED | 공유 액면 예약은 로컬 합성이다. 담보 완전성·차입기초·준비금 표시는 읽기 전용 오버레이이며 docs/decisions/CAPITAL_FINANCIAL_TERMS.md (CAPITAL-TERMS-V1, PROVISIONAL PRODUCT DECISION)를 인용한다. 집행은 applied false다. |
| CAP-05 | 청구·수취인·분할 정산 | `product-journey` | READ_ONLY_FIXTURE | PR #1의 고정 F01–F03 시나리오다. 운영 배분 순서는 제품에 채택되지 않았다. 잠정 값은 docs/decisions/CAPITAL_SETTLEMENT_POLICY.md에 있고 fixture를 바꾸지 않는다. |
| CAP-06 | 환불·공연취소·회수 | `product-journey` | SIMULATED | PR #1의 일부 합성 환불 비교다. 잠정 환불·리셀 부담은 docs/decisions/CAPITAL_SETTLEMENT_POLICY.md에 있고 합성 비교를 바꾸지 않는다. |
| CAP-07 | 최초 판매·반복 리셀·입장 연계 | `Commerce` · `Protocol` | NOT_BOUND | upstream, not adopted. Commerce 실여정과 Protocol producer tuple이 없다. |
| CAP-08 | 초과 배정·현금/한도 구별 | `product-journey` | SIMULATED | 공유 액면과 읽기 전용 인출 사전점검이다. 외부 한도가 아니다. |
| CAP-09 | 승인액/매출/권리확정/지급/환불 보고 | `recon-statement` | SIMULATED | 로컬 다섯 구분 명세서다. 실지급이 아니고 최초 판매와 리셀을 합산하지 않는다. |
| CAP-10 | 원 operation/최초 결과/UNKNOWN | `persistence-port` | SIMULATED | 개발용 LOCAL_FILE_WORKSPACE다. stage5 내구 거래가 아니다. |
| CAP-11 | 내구 거래·inbox/outbox·장애복구 | `k-stage5-durable-tx` | NOT_BOUND | upstream, not adopted. 자체 저장엔진을 만들지 않는다. |
| CAP-12 | 자산별 정확한 금액·FX | `product-journey` | SIMULATED | KRW 정수 검증만 로컬이다. u128·registry·FX는 upstream, not adopted. |
| CAP-13 | 복식 금융 투영 | `finance-projection` | SIMULATED | 로컬 후보 SYNTHETIC_UNADOPTED다. `fin-ledger-contract`는 upstream, not adopted. |
| CAP-14 | 원관측·대사 예외 | `recon-statement` | SIMULATED | 로컬 진단이다. 은행·PG·제공자 관측은 NOT_BOUND다. |
| CAP-15 | 인증 export·일관 source cut | `export-manifest` | SIMULATED | 로컬 해시 manifest와 SignaturePort다. stage7 인증 export가 아니다. |
| CAP-16 | SDK·API 적합성 | `facade-contract-seams` | NOT_BOUND | 로컬 capital-local-facade/1은 exact tuple이 아니다. SEMANTIC_CONFORMANCE가 아니다. |
| CAP-17 | 공개/비공개·권리 규모 | `RS-0~5` | NOT_BOUND | upstream, not adopted. privacy·currentness와 규모 검증이 없다. |
| CAP-18 | 선택적 토큰 담보·보상 | `TL` | NOT_AUTHORIZED | upstream, not adopted. coin lock 결정이 없고 토큰 호출 코드가 없다. |
| CAP-19 | AI 운영·권한·최소공개 | `CAPITAL-AUTH-BOUNDARY` | NOT_BOUND | 로컬 합성 역할만 있다. IdP·KYC·AgentGrant/ActionPermit은 upstream, not adopted. |
| CAP-20 | 접근성·통합 수용 | `acceptance-suite` | SIMULATED | 자동 검증만이다. 브라우저 여정은 `journeys-portfolio`에도 있다. 사람 수용은 PENDING이고 실서비스 출시는 승인되지 않았다. |
