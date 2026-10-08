"""CAP coverage map against the requirements doc and readiness groups."""
import re
import unittest
from collections import Counter
from pathlib import Path

from capital.readiness import GROUPS
from capital.service import CapitalService

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / 'docs' / 'CAPITAL_REQUIREMENTS_KO.md'
COVERAGE = ROOT / 'docs' / 'CAP_COVERAGE.md'

CAP_IDS = [f'CAP-{index:02d}' for index in range(1, 21)]
STATUS_TOKENS = (
    'SIMULATED',
    'READ_ONLY_FIXTURE',
    'NOT_BOUND',
    'DECISION_REQUIRED',
    'NOT_AUTHORIZED',
)
LOCAL_CANDIDATE = ('CAP-09', 'CAP-10', 'CAP-13', 'CAP-14', 'CAP-15', 'CAP-16')
_TOKEN = re.compile(
    r'(?<![A-Z_])(SIMULATED|READ_ONLY_FIXTURE|NOT_BOUND|DECISION_REQUIRED|NOT_AUTHORIZED)(?![A-Z_])')
_OWNER_NODE = re.compile(r'`[^`]+`')
_OWNER_NOTE = re.compile(r'docs/decisions/[A-Za-z0-9][A-Za-z0-9_.-]*\.md')
_ALLOWED = {
    'AVAILABLE_LOCAL': {'SIMULATED', 'READ_ONLY_FIXTURE'},
    'DECISION_REQUIRED': {'DECISION_REQUIRED', 'SIMULATED'},
    'UPSTREAM_REQUIRED': {'NOT_BOUND', 'NOT_AUTHORIZED', 'SIMULATED'},
    'NOT_AUTHORIZED': {'NOT_AUTHORIZED', 'SIMULATED'},
}


def first_status(cell):
    match = _TOKEN.search(cell)
    return match.group(1) if match else None


def table_rows(text):
    rows = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith('|'):
            continue
        cells = [cell.strip() for cell in stripped.strip('|').split('|')]
        if not cells or not re.fullmatch(r'CAP-\d+', cells[0]):
            continue
        rows.append((cells, line))
    return rows


def readiness_map(groups):
    """cap -> list of group statuses, in group order."""
    found = {cap: [] for cap in CAP_IDS}
    for group in groups:
        status = group['status']
        for cap in group['requirements']:
            found.setdefault(cap, []).append(status)
    return found


def allowed_statuses(group_statuses):
    union = set()
    for status in group_statuses:
        if status not in _ALLOWED:
            return None
        union |= _ALLOWED[status]
    return union


def check_coverage(coverage_text, requirements_text, groups):
    """Errors for a coverage table. Empty means the table agrees."""
    errors = []
    coverage_rows = table_rows(coverage_text)
    ids = [cells[0] for cells, _line in coverage_rows]
    counts = Counter(ids)
    for cap in CAP_IDS:
        if counts[cap] == 0:
            errors.append(f'missing {cap}')
        elif counts[cap] > 1:
            errors.append(f'duplicate {cap}')
    for cap in counts:
        if cap not in CAP_IDS:
            errors.append(f'unknown id {cap}')
    if ids != CAP_IDS and not any(error.startswith(('missing ', 'duplicate ', 'unknown id ')) for error in errors):
        errors.append('CAP ids are not in order CAP-01..CAP-20')

    requirement_status = {}
    requirement_rows = table_rows(requirements_text)
    requirement_ids = [cells[0] for cells, _line in requirement_rows]
    if requirement_ids != CAP_IDS:
        errors.append('requirements doc does not list CAP-01..CAP-20 once each')
    for cells, line in requirement_rows:
        if '완료 아님' not in line and '완료' in line:
            errors.append(f'{cells[0]}: requirements row contains 완료')
        if re.search(r'\bCOMPLETE\b|\bDONE\b', line):
            errors.append(f'{cells[0]}: requirements row contains COMPLETE or DONE')
        if len(cells) < 4:
            errors.append(f'{cells[0]}: requirements row is short')
            continue
        token = first_status(cells[3])
        if token is None:
            errors.append(f'{cells[0]}: requirements status has no token')
        else:
            requirement_status[cells[0]] = token
        if cells[0] in LOCAL_CANDIDATE and '로컬' not in cells[3]:
            errors.append(f'{cells[0]}: requirements status missing local-candidate marker')

    groups_for = readiness_map(groups)
    seen = set()
    for cells, _line in coverage_rows:
        cap = cells[0]
        if cap in seen or cap not in CAP_IDS:
            continue
        seen.add(cap)
        if len(cells) != 5:
            errors.append(f'{cap}: coverage row must have 5 columns')
            continue
        _identity, requirement, owner, status, reason = cells
        if not requirement or not reason:
            errors.append(f'{cap}: requirement and reason must be non-empty')
        if not owner or not (_OWNER_NODE.search(owner) or _OWNER_NOTE.search(owner)):
            errors.append(f'{cap}: owner must name a node or a decision note')
        if status not in STATUS_TOKENS:
            errors.append(f'{cap}: status {status!r} is not allowed')
            continue
        if cap in requirement_status and status != requirement_status[cap]:
            errors.append(
                f'{cap}: coverage {status} disagrees with requirements token {requirement_status[cap]}')
        group_statuses = groups_for.get(cap) or []
        if not group_statuses:
            errors.append(f'{cap}: missing from readiness groups')
            continue
        union = allowed_statuses(group_statuses)
        if union is None:
            errors.append(f'{cap}: unknown readiness status in {group_statuses}')
            continue
        if status not in union:
            errors.append(f'{cap}: {status} is outside readiness statuses {group_statuses}')
        if status == 'DECISION_REQUIRED' and 'DECISION_REQUIRED' not in group_statuses:
            errors.append(f'{cap}: DECISION_REQUIRED coverage needs a DECISION_REQUIRED group')
    return errors


class CoverageTests(unittest.TestCase):
    def test_committed_map_matches_requirements_and_readiness(self):
        errors = check_coverage(
            COVERAGE.read_text(encoding='utf-8'),
            REQUIREMENTS.read_text(encoding='utf-8'),
            GROUPS)
        self.assertEqual(errors, [])
        ready = CapitalService().readiness()
        self.assertEqual(ready['upstream_nodes_completed'], [])
        self.assertEqual([cells[0] for cells, _line in table_rows(REQUIREMENTS.read_text(encoding='utf-8'))], CAP_IDS)

    def test_missing_duplicate_and_flipped_status_fail(self):
        original = COVERAGE.read_text(encoding='utf-8')
        requirements = REQUIREMENTS.read_text(encoding='utf-8')
        dropped = original.replace(
            '| CAP-07 | 최초 판매·반복 리셀·입장 연계 | `Commerce` · `Protocol` | NOT_BOUND | upstream, not adopted. Commerce 실여정과 Protocol producer tuple이 없다. |\n',
            '',
            1)
        self.assertTrue(any(error == 'missing CAP-07' for error in check_coverage(dropped, requirements, GROUPS)))
        duplicated = original.replace(
            '| CAP-01 |',
            '| CAP-01 |\n| CAP-01 | 중복 | `product-journey` | SIMULATED | 중복 행 |',
            1)
        self.assertTrue(any(error == 'duplicate CAP-01' for error in check_coverage(duplicated, requirements, GROUPS)))
        flipped = original.replace(
            '| CAP-05 | 청구·수취인·분할 정산 | `product-journey` | READ_ONLY_FIXTURE |',
            '| CAP-05 | 청구·수취인·분할 정산 | `product-journey` | NOT_BOUND |',
            1)
        flipped_errors = check_coverage(flipped, requirements, GROUPS)
        self.assertTrue(any('CAP-05' in error and 'disagrees' in error for error in flipped_errors))
        self.assertTrue(any('CAP-05' in error and 'outside readiness' in error for error in flipped_errors))

    def test_requirements_row_without_a_token_is_an_error(self):
        text = REQUIREMENTS.read_text(encoding='utf-8')
        mutated = text.replace(
            'SIMULATED(자동검증만); 사용자 수용 PENDING',
            '사용자 수용 PENDING',
            1)
        errors = check_coverage(COVERAGE.read_text(encoding='utf-8'), mutated, GROUPS)
        self.assertTrue(any('CAP-20: requirements status has no token' in error for error in errors))

    def test_decision_required_coverage_needs_that_group(self):
        groups = [
            {'id': 'local-only', 'status': 'AVAILABLE_LOCAL', 'requirements': ['CAP-02']},
        ]
        text = (
            '| ID | 요구 | 소유 노드 / 결정 노트 | 상태 | 근거 |\n'
            '| CAP-02 | 수익 | docs/decisions/revenue-participation.md | DECISION_REQUIRED | 미정 |\n'
        )
        requirements = '| CAP-02 | 수익 | 본문 | DECISION_REQUIRED: 미정 |\n'
        errors = check_coverage(text, requirements, groups)
        self.assertTrue(any('DECISION_REQUIRED group' in error for error in errors))


if __name__ == '__main__':
    unittest.main()
