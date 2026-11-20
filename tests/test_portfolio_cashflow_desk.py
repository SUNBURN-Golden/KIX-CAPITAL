"""SIMULATED operator journey: only clock writes after HTTP offer/approve/bind/draw."""
import copy
import json
import re
import shutil
import subprocess
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from capital.server import make_server

ROOT = Path(__file__).resolve().parents[1]


class CashflowDeskJourneyTests(unittest.TestCase):
    def test_clock_crosses_maturity_without_repayment(self):
        server = make_server(0)
        worker = threading.Thread(target=server.serve_forever)
        worker.start()
        token = None

        def call(path, body=None, expected=200):
            client = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            try:
                headers = {'Content-Type': 'application/json'}
                if token:
                    headers['X-Capital-Token'] = token
                client.request('GET' if body is None else 'POST', path,
                               None if body is None else json.dumps(body), headers)
                response = client.getresponse()
                value = json.loads(response.read())
                self.assertEqual(response.status, expected, value)
                return value
            finally:
                client.close()

        try:
            state = call('/api/state')
            token = state['local_token']
            instance = state['instance_id']
            advance = 'sim-cashflow-journey'
            for op, args in [('offer', {'fixture_id': 'sim-committed', 'amount': 90000}),
                             ('approve', {}), ('bind_settlement', {}), ('draw', {})]:
                receipt = call('/api/commands', dict(instance_id=instance, operation_id='cash-'+op.replace('_', '-'),
                               op=op, advance_id=advance, args=args))
                self.assertEqual(receipt['outcome'], 'ACCEPTED')
            path = '/api/portfolio/snapshot?instance_id=' + instance
            initial = call(path)
            schedule = initial['forecast']['advances'][0]
            maturity = schedule['maturity_day']
            window = initial['covenants']['watch_window_days']
            f04 = lambda: (server.service.machine.canonical_state(), copy.deepcopy(server.service.receipts),
                           copy.deepcopy(server.service.case_fixtures), call('/api/state')['operation_count'])
            baseline = f04()
            prior = 0
            digests = []
            for day in (0, maturity-window, maturity-7, maturity, maturity+1):
                if day > prior:
                    call('/api/overlay/commands', dict(instance_id=instance, operation_id=f'cash-clock-{day}',
                         op='advance_day', from_sim_day=prior, to_sim_day=day, reason='SIMULATED maturity journey'))
                frozen_overlay = copy.deepcopy(server.service.overlay_entries)
                snapshot = call(path)
                self.assertEqual(snapshot, call(path), 'same cut must have the same digest')
                self.assertEqual(server.service.overlay_entries, frozen_overlay, 'reads never post memos')
                self.assertTrue(snapshot['complete'], snapshot['completeness'])
                self.assertEqual(snapshot['cut']['sim_day'], day)
                self.assertEqual(snapshot['cut']['state_digest'], initial['cut']['state_digest'])
                self.assertEqual(f04(), baseline, 'no F04 repayment, receipts or exposure mutation')
                forecast = snapshot['forecast']['advances'][0]
                covenant = snapshot['covenants']['advances'][0]
                self.assertEqual((forecast['advance_id'], covenant['advance_id']), (advance, advance))
                self.assertEqual(forecast['draw_day'], 0)
                self.assertEqual(forecast['maturity_day'], covenant['maturity_day'])
                settlement, interest, principal = forecast['legs']
                self.assertEqual([leg['kind'] for leg in forecast['legs']],
                                 ['SETTLEMENT_CASH_IN', 'CONTRACT_INTEREST', 'PRINCIPAL'])
                self.assertEqual((settlement['day'], settlement['bucket'], settlement['status']),
                                 (None, None, 'EXPECTED_DAY_NOT_PROVIDED'))
                bucket = next((name for edge, name in [(7, '0-7'), (30, '8-30'), (60, '31-60'), (90, '61-90')]
                               if maturity-day <= edge), '91+')
                self.assertEqual((interest['bucket'], principal['bucket']), (bucket, bucket))
                codes = [reason['code'] for reason in covenant['reasons']]
                if day < maturity-window:
                    self.assertEqual(covenant['status'], 'CLEAR')
                    self.assertEqual(snapshot['covenants']['watch_list'], [])
                elif day <= maturity:
                    self.assertIn('MATURITY_WINDOW', codes)
                    self.assertEqual(covenant['status'], 'WATCH')
                else:
                    self.assertIn('PAST_MATURITY', codes)
                    self.assertEqual(covenant['status'], 'BREACH')
                if day >= maturity-window:
                    self.assertEqual(snapshot['covenants']['watch_list'][0]['advance_id'], advance)
                self.assertEqual(snapshot['covenants']['reserve']['coverage'], 'NOT_BOUND')
                self.assertFalse(covenant['enforced'])
                self.assertFalse(snapshot['funds_executed'])
                self.assertEqual(snapshot['cut']['overlay_state_digest'], call('/api/overlay')['overlay_state_digest'])
                digests.append(snapshot['snapshot_digest'])
                prior = day
            self.assertEqual(len(set(digests)), len(digests))
            # Role gates stay server-owned; observer cannot consume the snapshot.
            session = call('/api/session', {'role': 'auditor'})
            token = session['local_token']
            self.assertEqual(call(path)['snapshot_digest'], digests[-1])
            session = call('/api/session', {'role': 'observer'})
            token = session['local_token']
            self.assertEqual(call(path, expected=403)['error'], 'ROLE_FORBIDDEN')
        finally:
            server.shutdown()
            server.server_close()
            worker.join(5)
            self.assertFalse(worker.is_alive())


class CashflowDeskModelTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is required for socket-free JS model checks')
    def test_actual_js_validates_renders_and_discards_obsolete_refreshes(self):
        from tests.test_overlay import seed
        service = seed.build_service()
        result = subprocess.run(['node', 'tests/cashflow_desk_harness.cjs'],
                                input=json.dumps({'snapshot': service.portfolio_snapshot(service.instance_id),
                                                  'state': service.snapshot()}),
                                text=True, capture_output=True, cwd=ROOT, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('no HTTP/browser claim', result.stdout)

    def test_late_draw_keeps_recorded_dates_across_maturity_in_process(self):
        from capital.service import CapitalService
        from tests.test_overlay import draw_book, f04_view, tick
        service = CapitalService()
        tick(service, 'late-start', 0, 12)
        draw_book(service, advance='sim-unbound')
        initial = service.portfolio_snapshot(service.instance_id)
        forecast = initial['forecast']['advances'][0]
        self.assertEqual(forecast['draw_day'], 12)
        self.assertEqual(initial['terms_rollup']['rows'][0]['draw_day'], 0)
        baseline = f04_view(service)
        maturity = forecast['maturity_day']
        prior = 12
        for day in (maturity-initial['covenants']['watch_window_days'], maturity-7, maturity, maturity+1):
            tick(service, f'late-{day}', prior, day)
            snapshot = service.portfolio_snapshot(service.instance_id)
            self.assertEqual(snapshot['forecast']['advances'][0]['draw_day'], 12)
            self.assertEqual(f04_view(service), baseline)
            reason = 'PAST_MATURITY' if day > maturity else 'MATURITY_WINDOW'
            self.assertIn(reason, [row['code'] for row in snapshot['covenants']['watch_list'][0]['reasons']])
            if day >= maturity-7:
                self.assertEqual(snapshot['forecast']['advances'][0]['legs'][1]['bucket'], '0-7')
            prior = day
        if shutil.which('node'):
            result = subprocess.run(['node', 'tests/cashflow_desk_harness.cjs'],
                                    input=json.dumps({'snapshot': snapshot, 'state': service.snapshot()}),
                                    text=True, capture_output=True, cwd=ROOT, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)



class CashflowDeskStaticTests(unittest.TestCase):
    def test_snapshot_is_only_forecast_covenant_and_risk_source(self):
        app = (ROOT / 'capital/static/app.js').read_text()
        block = app[app.index('// DESK BEGIN'):app.index('// DESK END')]
        self.assertIn('/api/portfolio/snapshot?instance_id=', block)
        for path in ('/api/risk/covenants', '/api/terms/portfolio/forecast', "request('/api/risk')"):
            self.assertNotIn(path, block)
        for forbidden in ('expected_cash_krw', 'repayment_exact', 'parseFloat', 'toFixed', '.reduce(', 'BigInt', 'Math.'):
            self.assertNotIn(forbidden, block)
        for stream in ('SETTLEMENT_CASH_IN', 'PRINCIPAL', 'CONTRACT_INTEREST'):
            self.assertIn(stream, block)
        for needle in ('leg.exact', 'reason.code', 'reason.severity', 'reason.detail', 'NOT_APPLICABLE',
                       'EXPECTED_DAY_NOT_PROVIDED', 'body.overlay_state_digest===view.cashflow.cut.overlay_state_digest',
                       'snapshotComponentsOk', 'sessionGeneration', 'generation===refreshGeneration',
                       'deskData?.cashflow===snapshot', '!deskCommandsAllowed()'):
            self.assertIn(needle, app)

    def test_accessible_regions_follow_existing_keyboard_controls(self):
        html = (ROOT / 'capital/static/index.html').read_text()
        self.assertLess(html.index('id="desk-timeline-region"'), html.index('id="desk-cashflow"'))
        for name, label in [('desk-cashflow', 'desk-cashflow-title'), ('desk-cash-detail', 'desk-cash-detail-title')]:
            self.assertRegex(html, rf'<section id="{name}" aria-labelledby="{label}"')
        self.assertIn('id="desk-cash-status" role="status"', html)
        self.assertIn('id="desk-cash-detail" aria-labelledby="desk-cash-detail-title" tabindex="-1"', html)
        self.assertNotRegex(html, r'\son\w+=|\sstyle=|<style|<script(?![^>]*src=)')
        app = (ROOT / 'capital/static/app.js').read_text()
        self.assertIn("th.scope='col'", app)
        self.assertIn("textElement('caption',caption)", app)
        self.assertIn("$('desk-cash-detail').focus()", app)
        self.assertIn('가용 현금 잔액이 아니며 합산하지 않습니다', html)


if __name__ == '__main__':
    unittest.main()
