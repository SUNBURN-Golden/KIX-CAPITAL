"""Offline renderer semantics over audited SIMULATED disposable workspaces."""
import builtins
import copy
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from capital import audit, evidence, margin, overlay, recovery, residual_review, residuals, store
from capital.producer import PinnedFsmProducer
from capital.service import CapitalService

ROOT = Path(__file__).resolve().parents[1]


class Element:
    def __init__(self, tag, attrs=(), parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.children = []

    @property
    def text(self):
        return ''.join(c if isinstance(c, str) else c.text for c in self.children)

    def find(self, tag):
        return [c for c in self.children if isinstance(c, Element)
                for c in ([c] if c.tag == tag else []) + c.find(tag)]


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = self.current = Element('document')
        self.feed(html)
        self.close()
        if self.current is not self.root:
            raise AssertionError('unclosed element: ' + self.current.tag)

    def handle_starttag(self, tag, attrs):
        element = Element(tag, attrs, self.current)
        self.current.children.append(element)
        if tag not in ('meta',):
            self.current = element

    def handle_endtag(self, tag):
        if self.current.tag != tag:
            raise AssertionError((self.current.tag, tag))
        self.current = self.current.parent

    def handle_data(self, data):
        self.current.children.append(data)

    def find(self, tag):
        return self.root.find(tag)


def command(s, op, ref, key, **args):
    result = s.execute(dict(instance_id=s.instance_id, operation_id=key, op=op,
                            advance_id=ref, args=args))
    assert result['outcome'] == 'ACCEPTED', result
    return result


def draw(s, ref, amount=9000):
    for op, args in [('offer', dict(fixture_id='sim-committed', amount=amount)),
                     ('approve', {}), ('bind_settlement', {}), ('draw', {})]:
        command(s, op, ref, ref + '-' + op.replace('_', '-'), **args)


def post(s, op, key, **args):
    return s.overlay_command(dict(instance_id=s.instance_id, operation_id=key, op=op,
                                 at_sim_day=overlay.fold(s.overlay_entries)['sim_day'], **args))


def tick(s, day, key):
    return s.overlay_command(dict(instance_id=s.instance_id, operation_id=key, op='advance_day',
                                 from_sim_day=overlay.fold(s.overlay_entries)['sim_day'],
                                 to_sim_day=day, reason='SIMULATED review fixture'))


def closed(s, ref='sim-closed', cash=None):
    draw(s, ref)
    tick(s, overlay.fold(s.overlay_entries)['sim_day'] + 5, ref + '-tick')
    command(s, 'repay', ref, ref + '-principal', amount=9000, sequence=1)
    command(s, 'close', ref, ref + '-close')
    if cash is not None:
        gate = overlay.advance_gate(overlay.fold(s.overlay_entries), ref)
        post(s, 'post_repayment', ref + '-cash', advance_ref=ref,
             amount_krw=gate['interest_due_krw'] + gate['default_interest_due_krw'] + cash)


class ResidualReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.path = self.directory / store.FILE_NAME

    def service(self):
        source = margin.ScenarioReplaySource()
        s = CapitalService(producer=PinnedFsmProducer(fixtures=source))
        self.addCleanup(s.observability.close)
        return source, s

    def capture(self, s, legacy=False):
        payload = dict(receipts=s.receipts, journal=s.machine.export_journal(),
                       case_fixtures=dict(s.case_fixtures), state_digest=s.machine.state_digest())
        document = store.envelope('SIMULATED_REVIEW_FIXTURE', payload,
                                  overlay=overlay.build_section(s.overlay_entries))
        if legacy:
            del document['overlay'], document['envelope_version']
        self.path.write_bytes(store.canonical_bytes(document))
        self.path.chmod(0o600)
        self.assertTrue(audit.audit_workspace(self.directory)['ok'])
        return residuals.report_workspace(self.directory)

    def cli(self, *args, env=None):
        return subprocess.run([sys.executable, '-m', 'capital.residual_review', *args],
                              cwd=ROOT, capture_output=True, env=env, timeout=30)

    def validate_page(self, report):
        html = residual_review.render_report(report)
        page = Page(html)
        self.assertTrue(html.startswith('<!doctype html>'))
        self.assertEqual(page.find('html')[0].attrs, {'lang': 'en'})
        self.assertEqual([t.text for t in page.find('caption')],
                         [label + ' — independent KRW metrics' for label in residual_review.LABELS.values()])
        self.assertEqual(len(page.find('table')), 5)
        self.assertEqual([h.text for h in page.find('h1')], ['Residual obligation review'])
        headings = [h.text for h in page.find('h2')]
        for label in residual_review.LABELS.values():
            self.assertIn(label, headings)
        nodes = page.root.find('html')[0]
        all_nodes = []
        def visit(node):
            all_nodes.append(node)
            for child in node.children:
                if isinstance(child, Element):
                    visit(child)
        visit(nodes)
        ids = [n.attrs['id'] for n in all_nodes if 'id' in n.attrs]
        self.assertEqual(len(ids), len(set(ids)))
        for n in all_nodes:
            self.assertIn(n.tag, {'html', 'head', 'meta', 'title', 'style', 'body', 'header', 'main',
                                 'section', 'h1', 'h2', 'h3', 'p', 'dl', 'dt', 'dd', 'ol', 'li',
                                 'nav', 'ul', 'a', 'div', 'table', 'caption', 'thead', 'tbody',
                                 'tfoot', 'tr', 'th', 'td', 'details', 'summary'})
            for key, value in n.attrs.items():
                self.assertFalse(key.startswith('on'))
                self.assertNotIn(key, {'src', 'srcset', 'action', 'formaction', 'style', 'data', 'background'})
                if key == 'href':
                    self.assertTrue(value.startswith('#'))
                    self.assertIn(value[1:], ids)
                if key == 'http-equiv':
                    self.fail('http-equiv can load resources')
        for th in page.find('th'):
            self.assertIn(th.attrs.get('scope'), ('row', 'col'))
        self.assertNotIn('url(', html.lower())
        self.assertNotIn('@import', html.lower())
        # Honesty fields must remain visible without opening any disclosure.
        visible = []
        def visible_text(node):
            if node.tag != 'details':
                for child in node.children:
                    if isinstance(child, str):
                        visible.append(child)
                    else:
                        visible_text(child)
        visible_text(page.root)
        for key in residual_review.HONESTY:
            self.assertIn(key, ''.join(visible))
            value = report[key]
            self.assertIn(str(value).lower() if isinstance(value, bool) else value, ''.join(visible))
        return page

    def test_empty_and_unavailable_are_five_distinct_semantic_tables(self):
        _, s = self.service()
        empty = self.capture(s)
        page = self.validate_page(empty)
        self.assertEqual(page.root.text.count('Audited empty recorded population'), 5)
        self.assertEqual(len(page.find('tfoot')), 5)
        self.path.unlink()
        failed = residuals.report_workspace(self.directory)
        page = self.validate_page(failed)
        self.assertEqual(len(page.find('tfoot')), 0)
        self.assertEqual(page.root.text.count('Counts and totals are unavailable.'), 5)
        self.assertIn('AUDIT_FAILED', page.find('h2')[0].text)

    def assert_metrics(self, page, report):
        for category, table in zip(residuals.METRICS, page.find('table')):
            section = report['sections'][category]
            rows = table.find('tbody')[0].find('tr')
            if section['rows']:
                for row, expected in zip(rows, section['rows']):
                    cells = row.find('td')
                    self.assertEqual([c.text for c in cells[2:-1]],
                                     ['NOT_BOUND — unknown' if expected['amounts'][m] is None
                                      else str(expected['amounts'][m]) for m in residuals.METRICS[category]])
            for foot, field in zip(table.find('tfoot')[0].find('tr'),
                                   ('known_subtotal_krw', 'unknown_rows', 'total_krw')):
                self.assertEqual([c.text for c in foot.find('td')[:-1]],
                                 ['NOT_BOUND — unknown' if section['totals'][m][field] is None
                                  else str(section['totals'][m][field]) for m in residuals.METRICS[category]])

    def test_closed_interest_cash_unknown_zero_and_fraction_remain_separate(self):
        _, s = self.service()
        closed(s, 'sim-cash', cash=500)
        closed(s, 'sim-interest')
        draw(s, 'sim-unknown')
        report = self.capture(s)
        self.assertEqual(report['status'], 'INCOMPLETE')
        page = self.validate_page(report)
        self.assert_metrics(page, report)
        cash = report['sections']['unapplied_cash']['totals']['unapplied_cash_krw']
        self.assertEqual(cash, dict(known_subtotal_krw=500, unknown_rows=1, total_krw=None))
        interest = report['sections']['closed_unpaid_interest']['rows']
        self.assertEqual(interest[0]['amounts']['interest_due_krw'], 0)
        self.assertGreater(interest[1]['amounts']['interest_due_krw'], 0)
        self.assertIn(interest[1]['remainders']['contract_subwon'], page.root.text)
        self.assertIn('NOT_CHECKED', page.root.text)
        self.assertIn('CLOSED', page.root.text)
        self.assertIn('MONETARY_EVIDENCE_NOT_BOUND', page.root.text)
        self.assertNotIn('grand_total', residual_review.render_report(report))

    def test_defaulted_and_written_off_claims_keep_original_journal_references(self):
        _, s = self.service()
        for ref in ('sim-default', 'sim-written'):
            draw(s, ref)
        tick(s, 10, 'day10')
        for ref in ('sim-default', 'sim-written'):
            command(s, 'default', ref, ref + '-default')
        eligible = recovery.anchor(overlay.fold(s.overlay_entries), 'sim-written')['writeoff_eligible_sim_day']
        tick(s, eligible + 1, 'writeoff-day')
        post(s, 'post_writeoff', 'sim-writeoff', advance_ref='sim-written',
             setoff_declined_reason='SIMULATED_FIXTURE_DECLINE')
        report = self.capture(s)
        self.assertEqual(report['status'], 'COMPLETE')
        page = self.validate_page(report)
        self.assert_metrics(page, report)
        for category in ('defaulted_unwritten', 'post_writeoff_residual_claims'):
            row = report['sections'][category]['rows'][0]
            self.assertGreater(row['amounts'][residuals.METRICS[category][-1]], 0)
            self.assertEqual(row['lifecycle_status'], 'DEFAULTED')
            detail = next(d for d in page.find('details') if d.attrs.get('id') == category + '-evidence-0')
            for block in ('accrual', 'repayment', 'recovery', 'position', 'slice', 'derived', 'observation'):
                self.assertIn(block, [dt.text for dt in detail.find('dt')])
            for ref in row['references']:
                journal = s.machine.export_journal() if ref['journal'] == 'F04' else s.overlay_entries
                original = journal[ref['index']]
                self.assertEqual(ref['entry_id'], original.get('idempotency_key', original.get('overlay_id')))
                self.assertIn(ref['entry_id'], detail.text)
                self.assertIn(ref['kind'], detail.text)
                for field in ('journal', 'index', 'entry_id', 'kind', 'after_journal_index', 'sim_day'):
                    self.assertIn(field, [dt.text for dt in detail.find('dt')])
            self.assertIn('not recorded', detail.text)
        self.assertIn('sim-writeoff', page.root.text)

    def test_late_recovery_evidence_is_retained(self):
        # Adapt the public synthetic journey, without importing any test helpers.
        import runpy
        scenario = runpy.run_path(str(ROOT / 'scripts/seed_overlay_recovery.py'))
        s, _ = scenario['build']()
        self.addCleanup(s.observability.close)
        report = self.capture(s)
        row = report['sections']['post_writeoff_residual_claims']['rows'][0]
        self.assertGreater(row['amounts']['residual_claim_krw'], 0)
        page = self.validate_page(report)
        self.assert_metrics(page, report)
        self.assertIn('recovery-late', page.root.text)
        self.assertIn('recovery-writeoff', page.root.text)

    def impaired(self):
        import runpy
        seed = runpy.run_path(str(ROOT / 'scripts/seed_overlay_slices.py'))
        source, s = self.service()
        claim = 'demo-delta-small'
        face = s.slice_policy['threshold'] // 5
        seed['register'](s, 'sim-slice', face, claim)
        seed['open_slice'](s, 'sim-slice')
        line = next(r for r in source.view(claim)['claim']['obligations'] if r['payee'] == 'organizer')
        seed['refund'](source, claim, line['outstanding'])
        seed['post'](s, 'impair_slice', 'impair', slice_id='sim-slice', reason='REFUND_REDUCED_LINE')
        return s

    def test_impaired_slice_keeps_outstanding_and_shortfall_in_independent_columns(self):
        report = self.capture(self.impaired())
        page = self.validate_page(report)
        self.assert_metrics(page, report)
        row = report['sections']['impaired_slice_residuals']['rows'][0]
        self.assertEqual(row['amounts']['outstanding_krw'], row['amounts']['shortfall_krw'])
        self.assertGreater(row['amounts']['outstanding_krw'], 0)
        self.assertIn('LAST_RECORDED_OBSERVATION', page.root.text)
        self.assertIn(row['fold_values']['observation']['claim_view_sha'], page.root.text)

    def test_partially_bound_slice_preserves_face_without_inventing_unknown_totals(self):
        s = self.impaired()
        report = self.capture(s)
        real_compose = residuals._compose
        def missing_baseline(service, state, journal, entries):
            state['claim_slices']['slices']['sim-slice'].pop('baseline_distributed_krw')
            return real_compose(service, state, journal, entries)
        with patch.object(residuals, '_compose', side_effect=missing_baseline):
            report = residuals.report_workspace(self.directory)
        self.assertEqual(report['status'], 'INCOMPLETE')
        page = self.validate_page(report)
        self.assert_metrics(page, report)
        row = report['sections']['impaired_slice_residuals']['rows'][0]
        self.assertGreater(row['amounts']['slice_face_krw'], 0)
        self.assertIsNone(row['amounts']['outstanding_krw'])
        self.assertIn('SLICE_BASELINE_NOT_BOUND', page.root.text)

    def test_hostile_dynamic_strings_and_nested_keys_are_literal_text(self):
        _, s = self.service()
        closed(s)
        report = self.capture(s)
        hostile = '\"><script>alert(1)</script><img src="https://bad.invalid" onerror="x"> & \' 한글'
        row = report['sections']['closed_unpaid_interest']['rows'][0]
        for field in residual_review.IDENTITY + ('lifecycle_status', 'evidence_status', 'basis'):
            row[field] = hostile
        row['reasons'] = [hostile]
        row['references'][0]['entry_id'] = hostile
        row['fold_values']['accrual'][hostile] = {hostile: [hostile]}
        report['source']['audit']['workspace'] = hostile
        report['interpretation'] += hostile
        report['reasons'] = [hostile]
        report['format'] = hostile
        page = self.validate_page(report)
        self.assertIn(hostile, page.root.text)
        self.assertGreater(page.root.text.count(hostile), 10)
        self.assertNotIn('<script>', residual_review.render_report(report))
        self.assertIn(hostile, [dt.text for dt in page.find('dt')])

    def test_source_hashes_audit_checks_coverage_and_reconciliation_survive(self):
        _, s = self.service()
        closed(s)
        report = self.capture(s)
        page = self.validate_page(report)
        def assert_structure(value):
            if isinstance(value, dict):
                for k, v in value.items():
                    self.assertIn(k, [dt.text for dt in page.find('dt')])
                    assert_structure(v)
            elif isinstance(value, list):
                for v in value:
                    assert_structure(v)
            elif value is not None:
                self.assertIn(str(value).lower() if isinstance(value, bool) else str(value), page.root.text)
        assert_structure(report['source'])
        for section in report['sections'].values():
            assert_structure(section['coverage'])
            assert_structure(section['reconciliation'])

    def test_pure_renderer_is_deterministic_does_no_io_and_does_not_mutate_report(self):
        _, s = self.service()
        closed(s)
        report = self.capture(s)
        before = copy.deepcopy(report)
        with patch.object(builtins, 'open', side_effect=AssertionError('I/O')), \
             patch.object(Path, 'read_bytes', side_effect=AssertionError('read')), \
             patch.object(Path, 'write_bytes', side_effect=AssertionError('write')), \
             patch.object(socket, 'socket', side_effect=AssertionError('network')):
            first = residual_review.render_report(report)
            self.assertEqual(first, residual_review.render_report(report))
        self.assertEqual(report, before)

    def test_cli_utf8_deterministic_and_workspace_inventory_bytes_modes_unchanged(self):
        _, s = self.service()
        closed(s)
        report = self.capture(s)
        def inventory():
            return {p.relative_to(self.directory).as_posix():
                    (p.stat().st_mode, p.read_bytes() if p.is_file() else None)
                    for p in [self.directory, *self.directory.rglob('*')]}
        before = inventory()
        env = {**os.environ, 'PYTHONIOENCODING': 'ascii'}
        first = self.cli('--workspace', str(self.directory), env=env)
        second = self.cli('--workspace', str(self.directory), env=env)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(first.stdout, residual_review.render_report(report).encode('utf-8') + b'\n')
        self.assertEqual(inventory(), before)

    def main_for_report(self, report):
        out = io.BytesIO()
        with patch.object(residuals, 'report_workspace', return_value=report) as produce, \
             patch.object(sys, 'stdout', type('Output', (), {'buffer': out})()):
            code = residual_review.main(['--workspace', str(self.directory)])
        produce.assert_called_once_with(self.directory)
        self.assertEqual(out.getvalue(), residual_review.render_report(report).encode('utf-8') + b'\n')
        return code

    def test_missing_and_corrupt_cli_preserve_failure_and_explanations(self):
        for raw in (None, b'{"x":1,"x":2}'):
            with self.subTest(raw=raw):
                if raw is not None:
                    self.path.write_bytes(raw)
                report = residuals.report_workspace(self.directory)
                result = self.cli('--workspace', str(self.directory))
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(self.main_for_report(report), 1)
                page = self.validate_page(report)
                self.assertIn('not a clean report', page.root.text)
                for reason in report['reasons']:
                    self.assertIn(reason, page.root.text)

    def test_inactive_restore_cli_failure_does_not_show_empty_population(self):
        _, s = self.service()
        closed(s)
        self.capture(s)
        restored = evidence.offline_service(json.loads(self.path.read_bytes()))
        restored.workspace_status = 'WORKSPACE_UNREADABLE'
        with patch.object(evidence, 'offline_service', return_value=restored):
            report = residuals.report_workspace(self.directory)
        self.assertEqual(self.main_for_report(report), 1)
        page = self.validate_page(report)
        self.assertIn('RESTORE_NOT_ACTIVE', page.root.text)
        self.assertNotIn('Audited empty', page.root.text)

    def test_legacy_missing_evidence_and_reconciliation_failure_keep_nonzero_outcomes(self):
        _, s = self.service()
        closed(s)
        legacy = self.capture(s, legacy=True)
        self.assertEqual(self.main_for_report(legacy), 1)
        self.assert_metrics(self.validate_page(legacy), legacy)
        self.capture(s)
        real_gate, real_compose = overlay.advance_gate, residuals._compose
        def mismatch(*args):
            def wrong(state, ref):
                return {**real_gate(state, ref), 'interest_due_krw': 12345}
            with patch.object(overlay, 'advance_gate', side_effect=wrong):
                return real_compose(*args)
        with patch.object(residuals, '_compose', side_effect=mismatch):
            report = residuals.report_workspace(self.directory)
        self.assertEqual(self.main_for_report(report), 1)
        page = self.validate_page(report)
        self.assertIn('RECONCILIATION_FAILED', page.root.text)
        self.assertIn('MISMATCH', page.root.text)
        self.assertIn('sim-closed-close', page.root.text)

    def test_cli_argument_misuse_exits_two_without_html(self):
        for args in ((), ('--workspace', str(self.directory), '--output', 'elsewhere.html')):
            result = self.cli(*args)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b'')
            self.assertIn(b'usage:', result.stderr)


if __name__ == '__main__':
    unittest.main()
