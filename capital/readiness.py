"""Product behavior and blocked prerequisites. No upstream node completion claim."""
from __future__ import annotations

import hashlib

GROUPS = [
    {'id': 'local-simulation', 'title': '정산·노출·환불의 로컬 검증', 'status': 'AVAILABLE_LOCAL',
     'requirements': ['CAP-01', 'CAP-04', 'CAP-05', 'CAP-06', 'CAP-08', 'CAP-09', 'CAP-10', 'CAP-14', 'CAP-20'],
     'behavior': '모의 제안부터 종결까지 조작하고, 부족 현금·부분 환불·회수 의무와 UNKNOWN을 별도 확인합니다.',
     'available': ['F04 모의 여정', 'F01-F03 시나리오 비교', '선택 제안의 읽기 전용 인출 사전점검', '원 결과 조회와 브라우저 경합 검증'],
     'blockers': [], 'owner': 'Capital implementation', 'claim': '로컬 합성 프로파일만 사용 가능; 전체 금융 완료 아님'},
    {'id': 'financial-contracts', 'title': '수익참여·채권 매입·담보 상품', 'status': 'DECISION_REQUIRED',
     'requirements': ['CAP-02', 'CAP-03', 'CAP-04'],
     'behavior': '수익 회수 순서·채권 양수·담보 부족 처리와 약정 조건을 실행하려면 승인된 계약이 필요합니다.',
     'available': ['원 청구/수취인별 의무 조회', '공유 노출 한도 시뮬레이션'],
     'blockers': ['수익·원가 정의와 배분 순서/상한', '채권 양도량·보유자·대가·우선순위', '이자·수수료·기간·연체/손실·외부 담보 완전성'],
     'owner': '사용자 및 지정 금융·법무 담당 / f04-mock-deepening, settlement-policy-deepening',
     'claim': '상품 조건의 임의 기본값 없음'},
    {'id': 'producer-binding', 'title': '실제 주문·리셀·Protocol 연결', 'status': 'UPSTREAM_REQUIRED',
     'requirements': ['CAP-07', 'CAP-16'],
     'behavior': '실제 producer의 주문/claim/권리 identity를 읽고 동일 계약의 명령·결과를 연결합니다.',
     'available': ['고정 참조 소스 무결성 검사', '로컬 API/receipt의 명시적 분리'],
     'blockers': ['확대 catalogue와 generated SDK의 exact source/manifest', 'SEMANTIC_CONFORMANCE profile과 양성/음성 vectors', 'Commerce/Protocol 동일 producer tuple과 실제 서비스 qualification'],
     'owner': 'Protocol / Commerce producer 및 계약 리뷰', 'claim': 'SDK 작업·UNKNOWN 소유권 변경 없음'},
    {'id': 'durable-finance', 'title': '내구 원장·복식 투영·대사·인증 export', 'status': 'UPSTREAM_REQUIRED',
     'requirements': ['CAP-11', 'CAP-13', 'CAP-14', 'CAP-15'],
     'behavior': '재시작 뒤에도 원 거래와 금융 투영을 복원하고 자료 범위가 증명된 보고서를 제공합니다.',
     'available': ['프로세스 내 저널 재생', '고정 fixture와 source hash 조회',
                   '로컬 후보 복식 투영 (SYNTHETIC_UNADOPTED · 비채택)'],
     'blockers': ['채택 backend와 stage5/6 경제 원천', 'Finance 후보 8개 채택과 계정/세무 정책', 'stage7 source cut·watermark·인증 export·부분 자료 거절'],
     'owner': 'Protocol stage5/6/7 및 사용자/회계 담당', 'claim': '현재 JSON은 내구 원장·인증 회계 export가 아님'},
    {'id': 'assets-and-rights', 'title': '다중 자산·권리 규모·비공개·AI', 'status': 'UPSTREAM_REQUIRED',
     'requirements': ['CAP-12', 'CAP-17', 'CAP-18', 'CAP-19'],
     'behavior': '자산별 금액·대규모 권리·최소 공개·위임 권한을 동일 producer 계약으로 연결합니다.',
     'available': ['KRW 목 정수 검증', '금융권리와 관람권 분리', '개인금융정보 없는 합성 역할'],
     'blockers': ['asset registry/u128/FX 계약과 적합성', 'RS 규모·privacy·currentness, TL 및 coin 잠금 결정', 'AgentGrant/ActionPermit 및 최소 공개 계약'],
     'owner': 'Protocol RS/TL/AI 및 사용자 결정', 'claim': '토큰 발행·개인신용판정·대규모 처리량 주장 없음'},
    {'id': 'release', 'title': '실서비스 수용·출시', 'status': 'NOT_AUTHORIZED',
     'requirements': ['CAP-20'], 'behavior': '실제 사용자·제공자·운영 환경에서 제품을 사용합니다.',
     'available': ['브라우저 합성 여정과 독립 코드 리뷰'],
     'blockers': ['사용자 제품 수용과 적용 가능한 독립 감사', '실여신/PG/은행/KYC·면허/법무와 운영 책임', '인증/TLS/보존·복구·개인정보·배포 명시 승인'],
     'owner': '사용자 및 지정 외부/운영 담당', 'claim': '개발 CI는 실거래 또는 배포 승인이 아님'},
]


def source_integrity(vendor, manifest):
    rows = []
    for path, expected in manifest['files'].items():
        file = vendor / path
        actual = hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() else None
        rows.append({'path': path, 'expected_sha256': expected, 'actual_sha256': actual,
                     'matched': actual == expected})
    return {'all_matched': all(row['matched'] for row in rows), 'files': rows,
            'meaning': 'Pinned local source-byte equality only; no SDK, runtime or service qualification.'}
