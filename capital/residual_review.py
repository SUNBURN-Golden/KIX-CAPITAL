"""Render the audited SIMULATED residual register as offline, read-only HTML.

Save stdout explicitly outside the source workspace. No server or browser is
started; this presentation consumes report_workspace without additional reads.
"""
from __future__ import annotations

import argparse
from html import escape
from pathlib import Path
import sys

from capital import residuals


LABELS = {
    'closed_unpaid_interest': 'Closed advances — unpaid interest',
    'unapplied_cash': 'Unapplied cash',
    'defaulted_unwritten': 'Defaulted advances — before write-off',
    'post_writeoff_residual_claims': 'Post-write-off residual claims',
    'impaired_slice_residuals': 'Impaired slice residuals',
}
IDENTITY = ('advance_id', 'slice_id', 'claim_id', 'beneficiary_role', 'payee_label', 'holder_role')
HONESTY = ('label', 'mode', 'authentication', 'actual_payments', 'legal_collectability',
           'funds_executed', 'workspace_mutated')
STATUS_EXPLANATIONS = {
    'COMPLETE': 'Only the declared recorded population was audited and reconciled. '
                'This does not establish complete settlement history or authenticity.',
    'INCOMPLETE': 'Monetary evidence is missing or reconciliation failed. '
                  'Available evidence is retained; unknown amounts are not zero.',
    'AUDIT_FAILED': 'Workspace audit or in-memory restore failed. '
                    'Obligation sections are unavailable; this is not a clean report.',
}
STYLE = """
body { font: 1rem/1.5 system-ui, sans-serif; margin: 2rem; color: #18232d; background: #fff; }
h1, h2, h3 { line-height: 1.25; }
a { color: #174f8b; }
a:focus, summary:focus { outline: 3px solid #aa5000; }
nav ul { padding-left: 1.5rem; }
.status { border: 3px solid #526575; padding: 1rem; }
.attention { border-color: #a32a12; background: #fff3ee; }
.table-scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
caption { text-align: left; font-weight: bold; }
th, td { border: 1px solid #9cabb5; padding: .5rem; vertical-align: top; text-align: left; }
thead, tfoot { background: #edf2f5; }
dt { font-weight: bold; overflow-wrap: anywhere; }
dd { margin: 0 0 .5rem 1rem; overflow-wrap: anywhere; white-space: pre-wrap; }
details { border: 1px solid #9cabb5; padding: .75rem; margin: .75rem 0; }
summary { cursor: pointer; font-weight: bold; overflow-wrap: anywhere; }
section { margin-top: 2rem; }
@media print { details { break-inside: avoid; } }
"""


def _text(value):
    if value is None:
        value = 'not recorded'
    elif value is True:
        value = 'true'
    elif value is False:
        value = 'false'
    return escape(str(value), quote=True)


def _structure(value):
    """Labeled native structures, retaining every supplied nested key/value."""
    if isinstance(value, dict):
        if not value:
            return '<p>No recorded fields.</p>'
        return '<dl>' + ''.join('<dt>' + _text(k) + '</dt><dd>' + _structure(value[k]) + '</dd>'
                               for k in sorted(value)) + '</dl>'
    if isinstance(value, (list, tuple)):
        if not value:
            return '<p>No recorded items.</p>'
        return '<ol start="0">' + ''.join('<li>' + _structure(v) + '</li>' for v in value) + '</ol>'
    return _text(value)


def _money(value):
    return 'NOT_BOUND — unknown' if value is None else _text(value)


def _section(category, section):
    metrics = residuals.METRICS[category]
    heading = LABELS[category]
    out = [f'<section id="{category}"><h2>{heading}</h2>']
    if section is None:
        out.append('<p>Unavailable — audit or restore failed. Counts and totals are unavailable.</p>')
    else:
        out.append('<h3>Coverage</h3>' + _structure(section['coverage']))
    out.append(f'<div class="table-scroll"><table><caption>{heading} — independent KRW metrics</caption>'
               '<thead><tr><th scope="col">Case or slice identity</th>'
               '<th scope="col">Lifecycle status</th><th scope="col">Evidence status</th>')
    out.extend('<th scope="col">' + _text(m) + '</th>' for m in metrics)
    out.append('<th scope="col">Evidence details</th></tr></thead><tbody>')
    if section is None or not section['rows']:
        message = 'Unavailable' if section is None else 'Audited empty recorded population'
        out.append(f'<tr><td colspan="{len(metrics) + 4}">{message}</td></tr>')
    else:
        for pos, row in enumerate(section['rows']):
            target = f'{category}-evidence-{pos}'
            out.append(f'<tr id="{category}-row-{pos}"><th scope="row">' +
                       _structure({k: row[k] for k in IDENTITY}) + '</th><td>' +
                       _text(row['lifecycle_status']) + '</td><td>' + _text(row['evidence_status']) + '</td>')
            out.extend('<td>' + _money(row['amounts'][m]) + '</td>' for m in metrics)
            out.append(f'<td><a href="#{target}">Evidence {pos + 1}</a></td></tr>')
    out.append('</tbody>')
    if section is not None:
        out.append('<tfoot>')
        for field in ('known_subtotal_krw', 'unknown_rows', 'total_krw'):
            out.append('<tr><th scope="row" colspan="3">' + field + '</th>')
            out.extend('<td>' + _money(section['totals'][m][field]) + '</td>' for m in metrics)
            out.append('<td>Independent per metric</td></tr>')
        out.append('</tfoot>')
    out.append('</table></div>')
    if section is not None:
        out.append('<details><summary>Reconciliation and checks</summary>' +
                   _structure(section['reconciliation']) + '</details>')
        for pos, row in enumerate(section['rows']):
            out.append(f'<details id="{category}-evidence-{pos}"><summary>Evidence {pos + 1}: ' +
                       _text(row['advance_id'] or row['slice_id']) + '</summary>')
            out.append('<h3>Identity</h3>' + _structure({k: row[k] for k in IDENTITY}))
            out.append('<h3>Evidence status, reasons and basis</h3>' + _structure(
                {k: row[k] for k in ('lifecycle_status', 'evidence_status', 'reasons', 'basis')}))
            out.append('<h3>Exact fractional remainders — excluded from integer totals</h3>' +
                       _structure(row['remainders']))
            out.append('<h3>Recorded fold values</h3>' + _structure(row['fold_values']))
            out.append('<h3>Original journal references</h3><p>index is zero-based; '
                       'after_journal_index is the recorded anchor; sim_day is the recorded day. '
                       'A missing F04 date is not recorded.</p>' + _structure(row['references']))
            out.append(f'<a href="#{category}-row-{pos}">Return to obligation row</a></details>')
    out.append('<a href="#top">Back to top</a></section>')
    return ''.join(out)


def render_report(report: dict) -> str:
    """Present supplied report fields without monetary arithmetic or I/O."""
    status = report['status']
    out = ['<!doctype html><html lang="en"><head><meta charset="utf-8">'
           '<meta name="viewport" content="width=device-width, initial-scale=1">'
           '<title>Residual obligation review — SIMULATED</title><style>' + STYLE +
           '</style></head><body><header id="top"><h1>Residual obligation review</h1>',
           '<p>Offline operator review — read-only recorded evidence.</p>',
           _structure({k: report[k] for k in HONESTY}),
           '<p>Report format: ' + _text(report['format']) + '</p></header>',
           '<main><section class="status' + ('' if status == 'COMPLETE' else ' attention') +
           '" aria-labelledby="report-status"><h2 id="report-status">Report status: ' +
           _text(status) + '</h2><p>' + _text(STATUS_EXPLANATIONS.get(status, 'Unrecognized report status.')) +
           '</p><h3>Status reasons</h3>' + _structure(report['reasons']) + '</section>',
           '<section id="interpretation"><h2>Interpretation and evidence limits</h2><p>' +
           _text(report['interpretation']) + '</p><p>Hashes identify integrity, not authentication. '
           'Amounts are copied as supplied. Known subtotals, unknown row counts, and totals remain '
           'separate. NOT_BOUND — unknown is distinct from recorded zero. '
           'Native details elements expand the retained evidence.</p></section>',
           '<nav aria-label="Report navigation"><ul><li><a href="#source">Source and audit evidence</a></li>']
    out.extend(f'<li><a href="#{c}">{LABELS[c]}</a></li>' for c in residuals.METRICS)
    out.append('</ul></nav><section id="source"><h2>Source and audit evidence</h2>'
               '<details><summary>Source hashes, audit metadata and checks</summary>' +
               _structure(report['source']) + '</details></section>')
    for category in residuals.METRICS:
        section = None if report['sections'] is None else report['sections'][category]
        out.append(_section(category, section))
    out.append('</main></body></html>')
    return ''.join(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
    args = parser.parse_args(argv)
    report = residuals.report_workspace(args.workspace)
    sys.stdout.buffer.write(render_report(report).encode('utf-8') + b'\n')
    return 0 if report['status'] == 'COMPLETE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
