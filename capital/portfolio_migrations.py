"""SIMULATED offline observed aging/watch transitions between explicit snapshots.

Principal changes and absence do not establish payments or causes. Historical
policy, authentication, common ownership and actual payments remain NOT_BOUND.
"""
from __future__ import annotations

import argparse
import copy
import sys

from capital import portfolio_compare, risk
from capital.store import canonical_bytes

FORMAT = 'KIX_CAPITAL_PORTFOLIO_MIGRATIONS_V1'
ABSENT_BEFORE = 'ABSENT_BEFORE'
ABSENT_AFTER = 'ABSENT_AFTER'
DIMENSIONS = {'aging': ('aging', risk.AGING_IDS),
              'watch_status': ('covenant_status', portfolio_compare.WATCH_STATUSES)}
MEASURES = ('advance_count', 'before_principal_krw', 'after_principal_krw',
            'before_open_advance_count', 'after_open_advance_count')


def _sum(items):
    items = list(items)
    return {key: sum(item[key] for item in items) for key in MEASURES}


def _aggregate(rows, dimension):
    """Dense union-population matrix, using audited classifications unchanged."""
    field, categories = DIMENSIONS[dimension]
    before_categories = [*categories, ABSENT_BEFORE]
    after_categories = [*categories, ABSENT_AFTER]
    cells = {(a, b): {'before_category': a, 'after_category': b,
                      **dict.fromkeys(MEASURES, 0)}
             for a in before_categories for b in after_categories}
    for row in rows:
        before, after = row['before'], row['after']
        cell = cells[(before[field] if before is not None else ABSENT_BEFORE,
                      after[field] if after is not None else ABSENT_AFTER)]
        cell['advance_count'] += 1
        for side, endpoint in (('before', before), ('after', after)):
            principal = 0 if endpoint is None else endpoint['outstanding_krw']
            cell[f'{side}_principal_krw'] += principal
            cell[f'{side}_open_advance_count'] += int(principal > 0)
    values = list(cells.values())
    return {'before_categories': before_categories, 'after_categories': after_categories,
            'cells': values,
            'row_totals': [{'before_category': a, **_sum(cells[a, b] for b in after_categories)}
                           for a in before_categories],
            'column_totals': [{'after_category': b, **_sum(cells[a, b] for a in before_categories)}
                              for b in after_categories],
            'grand_totals': _sum(values)}


def _reconcile(matrices, changes):
    """Check cells, marginals, endpoint views and beneficiary additivity."""
    checks = []

    def check(name, scope, dimension, matched):
        checks.append({'id': name, 'scope': scope, 'dimension': dimension,
                       'matched': bool(matched)})

    scopes = [('portfolio', matrices['portfolio'], changes['advances'], changes['totals'])]
    endpoints_by_role = {row['beneficiary_role']: row for row in changes['beneficiaries']}
    for item in matrices['beneficiaries']:
        role = item['beneficiary_role']
        rows = [row for row in changes['advances']
                if (row['after'] or row['before'])['beneficiary_role'] == role]
        scopes.append((role, item, rows, endpoints_by_role[role]))

    for scope, pair, rows, totals in scopes:
        for dimension, (field, categories) in DIMENSIONS.items():
            matrix = pair[dimension]
            cells = matrix['cells']
            expected_pairs = [(a, b) for a in (*categories, ABSENT_BEFORE)
                              for b in (*categories, ABSENT_AFTER)]
            check('dense_shape', scope, dimension,
                  matrix['before_categories'] == [*categories, ABSENT_BEFORE]
                  and matrix['after_categories'] == [*categories, ABSENT_AFTER]
                  and [(c['before_category'], c['after_category']) for c in cells] == expected_pairs)
            check('integer_measures', scope, dimension, all(
                type(c[key]) is int and c[key] >= 0 for c in cells for key in MEASURES))
            for side, axis, margins in (
                    ('before', 'before_category', matrix['row_totals']),
                    ('after', 'after_category', matrix['column_totals'])):
                axis_categories = [*categories, ABSENT_BEFORE if side == 'before' else ABSENT_AFTER]
                check(side + '_marginal_shape', scope, dimension,
                      [m[axis] for m in margins] == axis_categories)
                check(side + '_marginal_sums', scope, dimension, all(
                    {key: m[key] for key in MEASURES}
                    == _sum(c for c in cells if c[axis] == m[axis]) for m in margins))
                endpoint_rows = [r[side] for r in rows if r[side] is not None]
                for marginal in margins:
                    category = marginal[axis]
                    selected = [r for r in endpoint_rows if r[field] == category]
                    is_absent = category == axis_categories[-1]
                    count = (sum(r[side] is None for r in rows) if is_absent else len(selected))
                    check(f'{side}_{category}_endpoint', scope, dimension,
                          marginal['advance_count'] == count
                          and marginal[f'{side}_principal_krw'] == sum(r['outstanding_krw'] for r in selected)
                          and marginal[f'{side}_open_advance_count'] == sum(r['outstanding_krw'] > 0 for r in selected))
                check(side + '_endpoint_grand', scope, dimension,
                      matrix['grand_totals'][f'{side}_principal_krw'] == totals[side]['outstanding_krw']
                      and matrix['grand_totals'][f'{side}_open_advance_count']
                      == sum(r['outstanding_krw'] > 0 for r in endpoint_rows))
                # Comparator totals have already reconciled to risk/covenant views.
                if dimension == 'aging':
                    matched = {m[axis]: m[f'{side}_principal_krw'] for m in margins if m[axis] in categories}
                    expected = totals[side]['aging_exposure_krw']
                else:
                    matched = {m[axis]: m['advance_count'] for m in margins if m[axis] in categories}
                    expected = totals[side]['watch_status_counts']
                check(side + '_endpoint_view', scope, dimension, matched == expected)
            check('grand_sums', scope, dimension,
                  matrix['grand_totals'] == _sum(cells)
                  == _sum(matrix['row_totals']) == _sum(matrix['column_totals'])
                  and matrix['grand_totals']['advance_count'] == len(rows))
        check('dimension_totals', scope, 'both',
              pair['aging']['grand_totals'] == pair['watch_status']['grand_totals'])

    check('beneficiary_population', 'portfolio', 'both',
          [b['beneficiary_role'] for b in matrices['beneficiaries']] == sorted(endpoints_by_role))
    for dimension in DIMENSIONS:
        portfolio = matrices['portfolio'][dimension]
        beneficiaries = [b[dimension] for b in matrices['beneficiaries']]
        for section in ('cells', 'row_totals', 'column_totals'):
            check('beneficiary_' + section, 'portfolio', dimension, all(
                {key: item[key] for key in MEASURES} == _sum(b[section][i] for b in beneficiaries)
                for i, item in enumerate(portfolio[section])))
        check('beneficiary_grand_totals', 'portfolio', dimension,
              portfolio['grand_totals'] == _sum(b['grand_totals'] for b in beneficiaries))
    return {'matched': all(c['matched'] for c in checks), 'checks': checks}


def compose(comparison):
    """Pure additive report builder for a result from portfolio_compare.

    Non-comparable results never reach aggregation. Comparator diagnostics and
    provenance are retained without modifying the supplied comparison object.
    """
    report = copy.deepcopy({key: value for key, value in comparison.items() if key != 'changes'})
    report.update(format=FORMAT, matrices=None, reconciliation={'matched': False, 'checks': []},
                  interpretation='Observed endpoint transitions only; absence and principal changes '
                  'do not imply repayment, causation or transition probabilities.')
    if comparison['status'] != 'COMPARABLE':
        return report
    changes = comparison['changes']
    rows = changes['advances']
    roles = sorted({(row['after'] or row['before'])['beneficiary_role'] for row in rows})
    matrices = {'portfolio': {dim: _aggregate(rows, dim) for dim in DIMENSIONS},
                'beneficiaries': [
                    {'beneficiary_role': role, **{dim: _aggregate(
                        [row for row in rows if (row['after'] or row['before'])['beneficiary_role'] == role], dim)
                        for dim in DIMENSIONS}} for role in roles]}
    report['reconciliation'] = _reconcile(matrices, changes)
    if report['reconciliation']['matched']:
        report['matrices'] = matrices
    else:
        report.update(status='NON_COMPARABLE', reason='MATRIX_RECONCILIATION_FAILED')
    return report


def report_workspaces(before_dir, after_dir):
    """Use the existing comparator exactly once as the sole compatibility gate."""
    return compose(portfolio_compare.compare_workspaces(before_dir, after_dir))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', required=True, help='explicit directory containing workspace.json')
    parser.add_argument('--after', required=True, help='explicit directory containing workspace.json')
    args = parser.parse_args(argv)
    report = report_workspaces(args.before, args.after)
    sys.stdout.buffer.write(canonical_bytes(report) + b'\n')
    return 0 if report['status'] == 'COMPARABLE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
