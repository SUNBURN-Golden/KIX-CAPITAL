"""Operator health desk: API role checks and static pins on the shipped statics. SIMULATED.

The diagnostics sub-panel inside #desk renders existing GET /api/health,
GET /api/metrics, GET /api/state and GET /api/overlay values verbatim — health,
workspace status, command capacity, overlay capacity and the event-log
written/dropped/error counters. It adds no route, no permission, no retry and
no client arithmetic. These checks cover the loopback role boundary it relies
on and pin the static surface; behaviour is covered by
tests/browser/operator-health-desk.spec.cjs.
"""
import http.client
import json
import re
import threading
import unittest
from pathlib import Path

from capital.auth import OP_ORDER
from capital.server import make_server

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'capital' / 'static'
APP_JS = (STATIC / 'app.js').read_text(encoding='utf-8')
INDEX = (STATIC / 'index.html').read_text(encoding='utf-8')
STYLE = (STATIC / 'style.css').read_text(encoding='utf-8')
FORBIDDEN_MATHS = ('BigInt', 'Math.', 'parseFloat', 'toFixed', '.reduce(', 'parseInt', 'Intl.')
DIAG_IDS = (
    'desk-diag', 'desk-diag-refresh', 'desk-diag-label', 'desk-diag-health',
    'desk-diag-capacity-rows', 'desk-diag-command-rows', 'desk-diag-eventlog',
    'desk-diag-gaps', 'desk-diag-note',
)


def desk_block():
    start = APP_JS.index('// DESK BEGIN')
    end = APP_JS.index('// DESK END')
    return APP_JS[start:end]


class HealthDeskApiTests(unittest.TestCase):
    def start(self):
        self.server = make_server(0)
        self.port = self.server.server_port
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def stop(self):
        server = getattr(self, 'server', None)
        if server is None:
            return
        server.shutdown()
        server.server_close()
        self.worker.join(timeout=2)
        self.server = None

    def tearDown(self):
        self.stop()

    def request(self, path, headers=None, method='GET', body=None):
        client = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        client.request(method, path, body=body, headers=headers or {})
        response = client.getresponse()
        raw, status = response.read(), response.status
        client.close()
        return status, raw

    def state(self):
        status, raw = self.request('/api/state')
        self.assertEqual(status, 200, raw)
        return json.loads(raw)

    def test_state_exposes_command_capacity_for_the_panel(self):
        self.start()
        view = self.state()
        self.assertIsInstance(view['operation_count'], int)
        self.assertIsInstance(view['operation_capacity'], int)
        self.assertEqual(view['operation_capacity'], 500)
        self.assertEqual(view['workspace']['kind'], 'MEMORY')
        self.assertEqual(view['workspace']['status'], 'ACTIVE')

    def test_organizer_and_auditor_read_metrics_and_health(self):
        self.start()
        view = self.state()
        for token, role in ((view['local_token'], 'organizer'),
                            (self.server.authorizer.bind_role('auditor'), 'auditor')):
            status, raw = self.request('/api/health', headers={'X-Capital-Token': token})
            self.assertEqual(status, 200, (role, raw))
            health = json.loads(raw)
            self.assertEqual(set(health), {'status', 'uptime_seconds', 'workspace_status', 'mode'})
            self.assertIn(health['status'], ('ok', 'degraded'))
            self.assertEqual(health['mode'], 'LOCAL_OBSERVABILITY')
            status, raw = self.request('/api/metrics', headers={'X-Capital-Token': token})
            self.assertEqual(status, 200, (role, raw))
            metrics = json.loads(raw)
            self.assertEqual(metrics['mode'], 'LOCAL_OBSERVABILITY')
            self.assertEqual(metrics['label'], 'SIMULATED')
            self.assertEqual(metrics['instance_id'], view['instance_id'])
            self.assertIs(metrics['funds_executed'], False)
            for field in ('external_exporters', 'tracing', 'alerting', 'network_sinks'):
                self.assertEqual(metrics[field], 'NOT_BOUND', (role, field))
            self.assertEqual(set(metrics['workspace']), {'kind', 'status'})
            self.assertIsInstance(metrics['uptime_seconds'], int)
            event_log = metrics['counters']['event_log']
            self.assertEqual(set(event_log), {'enabled', 'written', 'errors', 'dropped', 'max_bytes'})
            self.assertIsInstance(event_log['written'], int)
            self.assertIsInstance(event_log['errors'], int)
            self.assertIsInstance(event_log['dropped'], int)
            commands = metrics['counters']['commands']
            self.assertEqual(set(commands), set(OP_ORDER) | {'other'})
            for counts in commands.values():
                self.assertEqual(set(counts), {'ACCEPTED', 'REJECTED'})

    def test_observer_gets_health_only_and_agent_gets_no_diagnostics(self):
        self.start()
        observer = self.server.authorizer.bind_role('observer')
        agent = self.server.authorizer.bind_role('agent')
        status, raw = self.request('/api/health', headers={'X-Capital-Token': observer})
        self.assertEqual(status, 200, raw)
        self.assertEqual(set(json.loads(raw)),
                         {'status', 'uptime_seconds', 'workspace_status', 'mode'})
        status, raw = self.request('/api/metrics', headers={'X-Capital-Token': observer})
        denied = json.loads(raw)
        self.assertEqual(status, 403, denied)
        self.assertEqual(denied['error'], 'ROLE_FORBIDDEN')
        self.assertEqual(denied['permission'], 'metrics:read')
        self.assertEqual(denied['role'], 'observer')
        for path, permission in (('/api/health', 'health:read'), ('/api/metrics', 'metrics:read')):
            status, raw = self.request(path, headers={'X-Capital-Token': agent})
            denied = json.loads(raw)
            self.assertEqual(status, 403, (path, denied))
            self.assertEqual(denied['error'], 'ROLE_FORBIDDEN')
            self.assertEqual(denied['permission'], permission)
            self.assertEqual(denied['role'], 'agent')

    def test_overlay_capacity_is_a_labeled_demo_bound(self):
        self.start()
        status, raw = self.request('/api/overlay')
        self.assertEqual(status, 200, raw)
        capacity = json.loads(raw)['capacity']
        if capacity == 'NOT_BOUND':
            return  # notes absent: the panel renders the NOT_BOUND row instead
        self.assertEqual(capacity['label'], 'DEMO_BOUND_NOT_FINANCIAL_LIMIT_NOT_STAGE5_CAPACITY')
        for pair in ('entries', 'decision_records', 'agent_proposals'):
            self.assertEqual(set(capacity[pair]), {'current', 'max'}, pair)
        for scalar in ('entry_max_bytes', 'sim_day_max', 'max_step_days', 'envelope_max_bytes'):
            self.assertIsInstance(capacity[scalar], int, scalar)

    def test_metrics_reads_do_not_move_the_book_and_replays_count_as_accepted(self):
        self.start()
        view = self.state()
        instance, token = view['instance_id'], view['local_token']
        body = json.dumps({
            'instance_id': instance, 'operation_id': 'diag-offer-1', 'op': 'offer',
            'advance_id': 'sim-diag-offer', 'args': {'fixture_id': 'sim-committed', 'amount': 1000},
        })
        headers = {'Content-Type': 'application/json', 'X-Capital-Token': token}
        for expected_duplicate in (False, True):
            status, raw = self.request('/api/commands', headers=headers, method='POST', body=body)
            self.assertEqual(status, 200, raw)
            receipt = json.loads(raw)
            self.assertEqual(receipt['outcome'], 'ACCEPTED')
            self.assertIs(receipt['transport_duplicate'], expected_duplicate)
        digest_after_writes = self.state()['state_digest']
        status, raw = self.request('/api/metrics', headers={'X-Capital-Token': token})
        self.assertEqual(status, 200, raw)
        metrics = json.loads(raw)
        # Each returned receipt is counted, so the replayed ACCEPTED shows up twice.
        self.assertEqual(metrics['counters']['commands']['offer']['ACCEPTED'], 2)
        self.assertEqual(metrics['counters']['commands']['offer']['REJECTED'], 0)
        # Reading metrics again must not move the journal or the receipt count.
        self.request('/api/metrics', headers={'X-Capital-Token': token})
        self.request('/api/health', headers={'X-Capital-Token': token})
        after = self.state()
        self.assertEqual(after['state_digest'], digest_after_writes)
        self.assertEqual(after['operation_count'], 1)


class HealthDeskStaticTests(unittest.TestCase):
    def test_diag_markup_sits_inside_desk_but_outside_desk_body(self):
        for element in DIAG_IDS:
            self.assertIn(f'id="{element}"', INDEX, element)
        self.assertIn('<section id="desk-diag" role="region" aria-label="진단">', INDEX)
        # Sibling placement: #desk-body is closed before the diagnostics region.
        self.assertLess(INDEX.index('id="desk-body"'), INDEX.index('id="desk-diag"'))
        self.assertLess(INDEX.index('id="desk-timeline-region"'), INDEX.index('id="desk-diag"'))
        self.assertIn('</div><section id="desk-diag"', INDEX)
        self.assertIn('LOCAL_OBSERVABILITY', INDEX)
        self.assertIn('SIMULATED', INDEX)
        # The refresh control keeps the pinned focus order: it is the last
        # focusable element inside #desk.
        order = ['desk-refresh', 'desk-case', 'desk-days', 'desk-advance',
                 'desk-overlay-region', 'desk-timeline-region', 'desk-diag-refresh']
        positions = [INDEX.index(f'id="{name}"') for name in order]
        self.assertEqual(positions, sorted(positions))
        self.assertNotRegex(INDEX, r'tabindex="[1-9]')

    def test_desk_block_reads_health_and_metrics_behind_permissions(self):
        block = desk_block()
        for needle in ('/api/health', '/api/metrics', 'health:read', 'metrics:read',
                       'event_log', 'written', 'dropped', 'errors', 'operation_capacity',
                       'LOCAL_OBSERVABILITY', 'SIMULATED', 'instance_id', 'unavailable',
                       'DEMO_BOUND_NOT_FINANCIAL_LIMIT_NOT_STAGE5_CAPACITY',
                       'desk-diag-refresh', 'desk-diag-capacity-rows',
                       'desk-diag-command-rows', 'desk-diag-eventlog', 'desk-diag-gaps',
                       'desk-diag-note', 'desk-diag-health', 'desk-diag-label'):
            self.assertIn(needle, block, needle)
        # metrics is only fetched after the server-side permission check.
        permission = block.index("next.auth.permissions['metrics:read']")
        fetch = block.index("request('/api/metrics')")
        self.assertLess(permission, fetch)
        # The stale-session guard keeps an older instance's values off screen.
        self.assertIn('diag.instance_id!==state?.instance_id', block)

    def test_diag_adds_no_client_maths_or_retry_paths(self):
        block = desk_block()
        for token in FORBIDDEN_MATHS:
            self.assertFalse(token in block, token)
        sums = re.findall(r'[A-Za-z_.\]\)]\s*\+\s*Number\(', block)
        self.assertEqual(len(sums), 1)
        for forbidden in (' * ', ' / ', ' % '):
            self.assertFalse(forbidden in block, forbidden)
        self.assertNotIn('setInterval', block)
        self.assertNotIn('setTimeout', block)
        self.assertNotIn('POST', APP_JS[APP_JS.index('function paintDeskDiag'):APP_JS.index('function renderDesk(')])

    def test_diag_styles_are_scoped_to_the_panel(self):
        self.assertIn('#desk-diag', STYLE)
        self.assertIn('.unavailable', STYLE)
        self.assertIn('@media(max-width:480px)', STYLE)


if __name__ == '__main__':
    unittest.main()
