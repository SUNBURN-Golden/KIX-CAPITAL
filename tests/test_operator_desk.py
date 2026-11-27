"""Operator desk: static pins on the browser source. SIMULATED.

The desk adds no server arithmetic and no client money maths. These checks read the shipped
static files; behaviour is covered by tests/browser/operator-desk.spec.cjs.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'capital' / 'static'
APP_JS = (STATIC / 'app.js').read_text(encoding='utf-8')
INDEX = (STATIC / 'index.html').read_text(encoding='utf-8')
STYLE = (STATIC / 'style.css').read_text(encoding='utf-8')
SERVER = (ROOT / 'capital' / 'server.py').read_text(encoding='utf-8')
CSP = ("default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
FORBIDDEN_SINKS = ('innerHTML', 'outerHTML', 'insertAdjacentHTML', 'eval(', 'new Function', 'document.write',
                   "setAttribute('style'", 'setAttribute("style"', '.style.')
FORBIDDEN_MATHS = ('BigInt', 'Math.', 'parseFloat', 'toFixed', '.reduce(', 'parseInt', 'Intl.')


def desk_block():
    start = APP_JS.index('// DESK BEGIN')
    end = APP_JS.index('// DESK END')
    return APP_JS[start:end]


class OperatorDeskStaticTests(unittest.TestCase):
    def test_script_has_no_html_or_code_sinks(self):
        for token in FORBIDDEN_SINKS:
            self.assertFalse(token in APP_JS, token)
        self.assertEqual(re.findall(r'\bFunction\s*\(', APP_JS), [])

    def test_csp_literal_is_unchanged_and_page_has_no_inline_code_or_style(self):
        self.assertIn(CSP, SERVER)
        self.assertEqual(SERVER.count('Content-Security-Policy'), 1)
        self.assertNotRegex(INDEX, r'<script(?![^>]*\bsrc=)')
        self.assertNotRegex(INDEX, r'\sstyle=')
        self.assertNotRegex(INDEX, r'\son[a-z]+=')
        self.assertNotIn('<style', INDEX)

    def test_desk_block_has_no_client_money_maths(self):
        block = desk_block()
        for token in FORBIDDEN_MATHS:
            self.assertFalse(token in block, token)
        # the only arithmetic on the wire is the logical day: to_sim_day = from_sim_day + N
        sums = re.findall(r'[A-Za-z_.\]\)]\s*\+\s*Number\(', block)
        self.assertEqual(len(sums), 1)
        self.assertIn('to_sim_day:from+Number(days)', block)
        for forbidden in (' * ', ' / ', ' % '):
            self.assertFalse(forbidden in block, forbidden)

    def test_desk_reads_server_text_and_uses_the_overlay_command_route(self):
        block = desk_block()
        for needle in ('/api/overlay/commands', "op:'advance_day'", "'/api/overlay'", '/api/export/manifest',
                       '/api/preview/', '/api/underwrite/', 'close_ready', 'proposals',
                       'permissionReason', 'aria-disabled', '/api/risk/covenants', 'covenant.reasons',
                       "covenant.status!=='CLEAR'", 'WATCH', 'BREACH'):
            self.assertTrue(needle in block, needle)
        self.assertIn("navigator.locks.request('kix-capital-writer'", APP_JS)
        self.assertEqual(APP_JS.count("navigator.locks.request('kix-capital-writer'"), 2)
        self.assertIn("original.op==='advance_day'", APP_JS)
        self.assertIn('operation_id=', APP_JS)

    def test_auditor_panel_is_text_only_and_has_no_command_callbacks(self):
        block = desk_block()
        audit = block[block.index('function paintDeskAudit('):block.index('function renderDesk(')]
        for forbidden in ('request(', 'fetch(', 'onclick', 'command(', 'Number(', *FORBIDDEN_MATHS):
            self.assertNotIn(forbidden, audit)
        for needle in ('after_journal_index', 'desk-audit-chain', 'desk-audit-checks',
                       'READ_ONLY_FIXTURE', 'not executed here', 'python3 -m capital.verify'):
            self.assertIn(needle, INDEX)
        self.assertIn("check.detail??'—'", audit)
        self.assertIn('report.scope.overlay_state_digest===overlay?.overlay_state_digest', audit)
        self.assertIn("currentRole()!=='auditor'", audit)

    def test_markup_pins_focus_order_and_roles(self):
        order = ['desk-refresh', 'desk-case', 'desk-days', 'desk-advance', 'desk-overlay-region', 'desk-timeline-region']
        positions = [INDEX.index(f'id="{name}"') for name in order]
        self.assertEqual(positions, sorted(positions))
        self.assertNotRegex(INDEX, r'tabindex="[1-9]')
        self.assertIn('id="desk-forbidden" role="status"', INDEX)
        self.assertIn('<a href="#desk">', INDEX)
        self.assertRegex(INDEX, r'<section class="panel" id="desk" hidden')
        self.assertIn('body.desk-open', STYLE)
        self.assertIn(':focus-visible', STYLE)
        self.assertIn('@media(max-width:480px)', STYLE)



class OperatorReasonTimelineTests(unittest.TestCase):
    def test_timeline_associates_receipts_clock_and_repayment_context(self):
        import json
        import shutil
        import subprocess
        if not shutil.which('node'): self.skipTest('node unavailable')
        function = APP_JS[APP_JS.index('function timelineRows('):APP_JS.index('function paintDeskTimeline(')]
        journal = [{'advance_id': 'sim-a', 'op': 'offer', 'idempotency_key': 'offer'},
                   {'advance_id': 'sim-a', 'op': 'draw', 'idempotency_key': 'draw'}]
        entries = [dict(after_journal_index=2, sim_day=1, kind=kind, payload=payload) for kind, payload in [
            ('clock', {'operator_reason': '<b>clock</b>'}),
            ('repayment', {'advance_ref': 'sim-a', 'operator_reason': '<b>payment</b>'}),
            ('repayment', {'advance_ref': 'sim-other', 'operator_reason': 'other'}),
            ('interest', {'advance_id': 'sim-a', 'operator_reason': 5})]]
        manifest = {'sections': {'journal': {'body': {'entries': journal}},
            'receipts': {'body': {'receipts': {'offer': {'receipt': {'operator_reason': '<b>offer</b>'}}}}},
            'overlay': {'body': {'journal': entries}}}}
        proc = subprocess.run(['node', '-e', function + '\nconsole.log(JSON.stringify(timelineRows(' +
            json.dumps(manifest) + ',{advance_id:"sim-a"})));'], capture_output=True, text=True, check=True)
        rows = json.loads(proc.stdout)
        self.assertEqual([row['cells'][5] for row in rows], ['<b>offer</b>', '—', '<b>clock</b>', '<b>payment</b>', '—'])
        self.assertTrue(all(len(row['cells']) == 6 for row in rows))
        self.assertTrue(all('operator_reason' not in row['cells'][4] for row in rows))
        self.assertIn('운영자 사유', INDEX)
        self.assertIn('Operator reason', INDEX)

    def test_docs_describe_context_and_privacy_rule(self):
        for name in ['docs/OPERATOR_HANDBOOK_KO.md', 'docs/INTEGRATION.md']:
            text = (ROOT / name).read_text()
            for needle in ['operator_reason', 'not authentication or approval evidence', 'no personal data']:
                self.assertIn(needle, text, name)

if __name__ == '__main__':
    unittest.main()
