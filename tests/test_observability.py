"""Process-local metrics, health, and the opt-in JSONL event log."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from pathlib import Path

from capital.auth import OP_ORDER
from capital.export import SECTION_IDS
from capital.observability import (
    EVENT_LOG_KEYS, EVENT_LOG_MAX_BYTES, LATENCY_MS, Observability,
)
from capital.server import make_server, route_label, route_labels
from capital.service import digest
from capital.store import WorkspaceError

ROOT = Path(__file__).resolve().parents[1]
BUCKETS = ('le_5', 'le_25', 'le_100', 'le_500', 'le_2500', 'gt_2500')


def _http_zeros():
    labels = tuple(route_labels()) + ('other',)
    return {label: {'2xx': 0, '4xx': 0, '5xx': 0} for label in labels}


class ObservabilityUnitTests(unittest.TestCase):
    def test_latency_buckets_are_fixed_and_exclusive(self):
        self.assertEqual(LATENCY_MS, (5, 25, 100, 500, 2500))
        self.assertEqual(tuple(f'le_{bound}' for bound in LATENCY_MS) + ('gt_2500',), BUCKETS)
        obs = Observability(routes=('/api/commands',))
        samples = (0, 5, 6, 25, 26, 100, 101, 500, 501, 2500, 2501)
        for elapsed in samples:
            obs.record_http('/api/commands', 200, None, None, elapsed)
        hist = obs.snapshot()['latency_ms']['/api/commands']
        self.assertEqual(set(hist), set(BUCKETS) | {'count', 'max_ms'})
        self.assertEqual(hist['le_5'], 2)
        self.assertEqual(hist['le_25'], 2)
        self.assertEqual(hist['le_100'], 2)
        self.assertEqual(hist['le_500'], 2)
        self.assertEqual(hist['le_2500'], 2)
        self.assertEqual(hist['gt_2500'], 1)
        self.assertEqual(hist['count'], len(samples))
        self.assertEqual(hist['count'], sum(hist[key] for key in BUCKETS))
        self.assertEqual(hist['max_ms'], 2501)
        obs.close()

    def test_unknown_op_and_route_collapse_and_unsafe_codes_do_not(self):
        obs = Observability(routes=('/api/commands',))
        obs.record_command('not-a-real-op', 'REJECTED', 'UNSUPPORTED_OPERATION')
        obs.record_command('offer', 'REJECTED', 'token-looking-value')
        obs.record_http('/api/not-a-route', 404, 'NOT_FOUND', None, 1)
        snap = obs.snapshot()
        self.assertEqual(set(snap['counters']['commands']), set(OP_ORDER) | {'other'})
        self.assertEqual(snap['counters']['commands']['other']['REJECTED'], 1)
        self.assertNotIn('not-a-real-op', snap['counters']['commands'])
        self.assertEqual(snap['counters']['rejections']['UNSUPPORTED_OPERATION'], 1)
        self.assertEqual(snap['counters']['rejections']['other'], 1)
        self.assertNotIn('token-looking-value', json.dumps(snap))
        self.assertNotIn('/api/not-a-route', snap['counters']['http_requests'])
        self.assertEqual(snap['counters']['http_requests']['other']['4xx'], 1)
        self.assertFalse(snap['counters']['event_log']['enabled'])
        self.assertEqual(snap['counters']['event_log']['max_bytes'], EVENT_LOG_MAX_BYTES)
        obs.close()
        obs.close()

    def test_event_log_lines_have_the_fixed_keys_and_drop_at_the_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'events.jsonl')
            obs = Observability(path, routes=('/api/commands',))
            obs.record_http('/api/commands', 200, None, 'obs-offer', 3)
            obs.max_bytes = os.path.getsize(path)
            obs.record_http('/api/commands', 404, 'NOT_FOUND', 'obs-miss', 4)
            snap = obs.snapshot()
            self.assertEqual(snap['counters']['event_log']['written'], 1)
            self.assertEqual(snap['counters']['event_log']['dropped'], 1)
            self.assertEqual(snap['counters']['event_log']['errors'], 0)
            obs.close()
            lines = Path(path).read_text(encoding='utf-8').splitlines()
            self.assertEqual(len(lines), 1)
            row = json.loads(lines[0])
            self.assertEqual(EVENT_LOG_KEYS, ('time', 'route', 'status', 'code', 'operation_id'))
            self.assertEqual(set(row), set(EVENT_LOG_KEYS))
            self.assertEqual(list(row), list(EVENT_LOG_KEYS))
            self.assertRegex(row['time'], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z\Z')
            self.assertEqual(row['route'], '/api/commands')
            self.assertEqual(row['status'], 200)
            self.assertIsNone(row['code'])
            self.assertEqual(row['operation_id'], 'obs-offer')

    def test_unwritable_event_log_increments_errors_and_does_not_raise(self):
        obs = Observability('/nonexistent-dir/x.jsonl', routes=('/api/commands',))
        obs.record_http('/api/commands', 200, None, 'obs-offer', 1)
        snap = obs.snapshot()
        self.assertTrue(snap['counters']['event_log']['enabled'])
        self.assertGreaterEqual(snap['counters']['event_log']['errors'], 1)
        self.assertEqual(snap['counters']['event_log']['written'], 0)
        self.assertEqual(snap['counters']['http_requests']['/api/commands']['2xx'], 1)
        obs.close()

    def test_route_label_keeps_a_closed_set(self):
        self.assertEqual(route_label('/api/metrics'), '/api/metrics')
        self.assertEqual(route_label('/api/health'), '/api/health')
        self.assertEqual(route_label('/api/operations/obs-offer'), '/api/operations/')
        self.assertEqual(route_label('/api/export/manifest'), '/api/export/manifest')
        self.assertEqual(route_label('/api/commands'), '/api/commands')
        self.assertEqual(route_label('/api/nope'), 'other')
        self.assertEqual(route_label('/api/metrics/extra'), 'other')
        self.assertEqual(route_label('/'), 'other')
        self.assertNotIn('/api/nope', route_labels())

    def test_event_log_flag_is_optional(self):
        proc = subprocess.run(
            [sys.executable, '-m', 'capital.server', '--help'],
            cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('--event-log', proc.stdout)


class ObservabilityHttpTests(unittest.TestCase):
    def start(self, event_log=None):
        self.server = make_server(0, event_log=event_log)
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

    def request(self, method, path, body=None, headers=None):
        client = HTTPConnection('127.0.0.1', self.port, timeout=5)
        client.request(method, path, body=body, headers=headers or {})
        response = client.getresponse()
        raw, status = response.read(), response.status
        client.close()
        return status, raw

    def state(self):
        status, raw = self.request('GET', '/api/state')
        self.assertEqual(status, 200, raw)
        return json.loads(raw)

    def command(self, instance, token, op, args, key, advance):
        body = {
            'instance_id': instance, 'operation_id': key, 'op': op,
            'advance_id': advance, 'args': args,
        }
        status, raw = self.request('POST', '/api/commands', json.dumps(body), {
            'Content-Type': 'application/json', 'X-Capital-Token': token,
        })
        self.assertEqual(status, 200, raw)
        return json.loads(raw)

    def settle(self):
        previous = None
        stable = 0
        deadline = time.monotonic() + 2
        snap = None
        while time.monotonic() < deadline:
            snap = self.server.service.observability.snapshot()
            token = json.dumps(snap['counters'], sort_keys=True)
            if token == previous:
                stable += 1
                if stable >= 2:
                    return snap
            else:
                stable = 0
                previous = token
            time.sleep(0.02)
        self.fail('observability counters did not settle')

    def assert_histogram(self, hist, expected_count):
        self.assertEqual(set(hist), set(BUCKETS) | {'count', 'max_ms'})
        self.assertEqual(hist['count'], sum(hist[key] for key in BUCKETS))
        self.assertEqual(hist['count'], expected_count)
        self.assertGreaterEqual(hist['max_ms'], 0)

    def test_scripted_journey_counters_match_and_do_not_touch_the_book(self):
        self.start()
        view = self.state()
        instance, token = view['instance_id'], view['local_token']
        advance = 'sim-obs-journey'
        offer = self.command(instance, token, 'offer', {'fixture_id': 'sim-committed', 'amount': 60000}, 'obs-offer', advance)
        self.assertEqual(offer['outcome'], 'ACCEPTED')
        self.command(instance, token, 'approve', {}, 'obs-approve', advance)
        self.command(instance, token, 'bind_settlement', {}, 'obs-bind', advance)
        self.command(instance, token, 'draw', {}, 'obs-draw', advance)
        refused = self.command(instance, token, 'close', {}, 'obs-close', advance)
        self.assertEqual((refused['outcome'], refused['error']), ('REJECTED', 'OUTSTANDING_REMAINS'))
        self.command(instance, token, 'repay', {'amount': 60000, 'sequence': 1}, 'obs-repay', advance)
        closed = self.command(instance, token, 'close', {}, 'obs-close-2', advance)
        self.assertEqual(closed['result']['credit']['phase'], 'CLOSED')
        status, raw = self.request('GET', f'/api/operations/obs-absent?instance_id={instance}')
        self.assertEqual(status, 200, raw)
        self.assertEqual(json.loads(raw)['outcome'], 'UNKNOWN')
        observer = self.server.authorizer.bind_role('observer')
        auditor = self.server.authorizer.bind_role('auditor')
        status, raw = self.request('GET', '/api/health', headers={'X-Capital-Token': observer})
        self.assertEqual(status, 200, raw)
        health = json.loads(raw)
        self.assertEqual(set(health), {'status', 'uptime_seconds', 'workspace_status', 'mode'})
        self.assertEqual(health['status'], 'ok')
        self.assertEqual(health['workspace_status'], 'ACTIVE')
        self.assertEqual(health['mode'], 'LOCAL_OBSERVABILITY')
        status, raw = self.request('GET', '/api/metrics', headers={'X-Capital-Token': observer})
        denied = json.loads(raw)
        self.assertEqual(status, 403, denied)
        self.assertEqual(denied['error'], 'ROLE_FORBIDDEN')
        self.assertEqual(denied['permission'], 'metrics:read')
        self.assertEqual(denied['role'], 'observer')
        status, raw = self.request('GET', '/api/nope')
        self.assertEqual((status, json.loads(raw)['error']), (404, 'NOT_FOUND'))
        self.settle()
        service = self.server.service
        digest_before = service.machine.state_digest()
        count_before = len(service.receipts)
        manifest_before = service.export_manifest()
        status, raw = self.request('GET', '/api/metrics', headers={'X-Capital-Token': token})
        self.assertEqual(status, 200, raw)
        metrics = json.loads(raw)
        self.assertEqual(metrics['mode'], 'LOCAL_OBSERVABILITY')
        self.assertEqual(metrics['label'], 'SIMULATED')
        self.assertEqual(metrics['instance_id'], instance)
        self.assertIs(metrics['funds_executed'], False)
        for field in ('external_exporters', 'tracing', 'alerting', 'network_sinks'):
            self.assertEqual(metrics[field], 'NOT_BOUND', field)
        self.assertEqual(set(metrics['workspace']), {'kind', 'status'})
        self.assertEqual(metrics['workspace'], {'kind': 'MEMORY', 'status': 'ACTIVE'})
        expected_commands = {op: {'ACCEPTED': 0, 'REJECTED': 0} for op in (*OP_ORDER, 'other')}
        for op in ('offer', 'approve', 'bind_settlement', 'draw', 'repay'):
            expected_commands[op]['ACCEPTED'] = 1
        expected_commands['close']['ACCEPTED'] = 1
        expected_commands['close']['REJECTED'] = 1
        self.assertEqual(metrics['counters']['commands'], expected_commands)
        self.assertEqual(metrics['counters']['rejections'], {
            'OUTSTANDING_REMAINS': 1,
            'ROLE_FORBIDDEN': 1,
            'NOT_FOUND': 1,
        })
        self.assertEqual(metrics['counters']['operation_lookups'], {'KNOWN': 0, 'UNKNOWN': 1})
        expected_http = _http_zeros()
        expected_http['/api/state']['2xx'] = 1
        expected_http['/api/commands']['2xx'] = 7
        expected_http['/api/operations/']['2xx'] = 1
        expected_http['/api/health']['2xx'] = 1
        expected_http['/api/metrics']['4xx'] = 1
        expected_http['other']['4xx'] = 1
        self.assertEqual(metrics['counters']['http_requests'], expected_http)
        self.assertEqual(metrics['counters']['http_requests']['/api/metrics']['2xx'], 0)
        for route, classes in expected_http.items():
            self.assert_histogram(
                metrics['latency_ms'][route], classes['2xx'] + classes['4xx'] + classes['5xx'])
        self.assertEqual(metrics['counters']['event_log'], {
            'enabled': False, 'written': 0, 'errors': 0, 'dropped': 0,
            'max_bytes': EVENT_LOG_MAX_BYTES,
        })
        blob = json.dumps(metrics)
        health_blob = json.dumps(health)
        for secret in (
            token, observer, auditor, advance, 'sim-committed', '60000',
            'obs-offer', 'obs-approve', 'obs-bind', 'obs-draw', 'obs-close',
            'obs-repay', 'obs-close-2', 'obs-absent',
        ):
            self.assertNotIn(secret, blob, secret)
            self.assertNotIn(secret, health_blob, secret)
        self.assertNotIn(instance, health_blob)
        self.assertEqual(service.machine.state_digest(), digest_before)
        self.assertEqual(len(service.receipts), count_before)
        self.assertNotIn('metrics', manifest_before['sections'])
        self.assertNotIn('health', manifest_before['sections'])
        self.assertEqual(set(manifest_before['sections']), set(SECTION_IDS))
        self.settle()
        status, raw = self.request('GET', '/api/metrics', headers={'X-Capital-Token': auditor})
        self.assertEqual(status, 200, raw)
        again = json.loads(raw)
        self.assertEqual(again['counters']['http_requests']['/api/metrics']['2xx'], 1)
        self.assertEqual(service.machine.state_digest(), digest_before)
        self.assertEqual(len(service.receipts), count_before)
        self.assertEqual(service.export_manifest()['content_digest'], manifest_before['content_digest'])
        status, raw = self.request('GET', '/api/state')
        self.assertEqual(status, 200, raw)
        after = json.loads(raw)
        self.assertEqual(after['state_digest'], digest_before)
        self.assertEqual(after['operation_count'], count_before)

    def test_unknown_command_lands_under_other(self):
        self.start()
        view = self.state()
        body = {
            'instance_id': view['instance_id'], 'operation_id': 'obs-unknown-op',
            'op': 'not-a-real-op', 'advance_id': 'sim-obs-other', 'args': {},
        }
        status, raw = self.request('POST', '/api/commands', json.dumps(body), {
            'Content-Type': 'application/json', 'X-Capital-Token': view['local_token'],
        })
        self.assertEqual((status, json.loads(raw)['error']), (400, 'UNSUPPORTED_OPERATION'))
        status, raw = self.request('GET', '/api/not-a-route')
        self.assertEqual(status, 404, raw)
        self.settle()
        snap = self.server.service.observability.snapshot()
        self.assertEqual(snap['counters']['commands']['other']['REJECTED'], 1)
        self.assertNotIn('not-a-real-op', snap['counters']['commands'])
        self.assertEqual(snap['counters']['rejections']['UNSUPPORTED_OPERATION'], 1)
        self.assertEqual(snap['counters']['rejections']['NOT_FOUND'], 1)
        self.assertNotIn('/api/not-a-route', snap['counters']['http_requests'])
        self.assertGreaterEqual(snap['counters']['http_requests']['other']['4xx'], 1)
        self.assertEqual(len(self.server.service.receipts), 0)

    def test_agent_cannot_read_metrics_or_health(self):
        self.start()
        agent = self.server.authorizer.bind_role('agent')
        for path, permission in (('/api/metrics', 'metrics:read'), ('/api/health', 'health:read')):
            status, raw = self.request('GET', path, headers={'X-Capital-Token': agent})
            body = json.loads(raw)
            self.assertEqual(status, 403, (path, body))
            self.assertEqual(body['error'], 'ROLE_FORBIDDEN')
            self.assertEqual(body['role'], 'agent')
            self.assertEqual(body['permission'], permission)

    def test_counters_stay_out_of_the_fingerprint_and_the_digest(self):
        self.start()
        view = self.state()
        advance = 'sim-obs-fp'
        args = {'fixture_id': 'sim-committed', 'amount': 1000}
        receipt = self.command(view['instance_id'], view['local_token'], 'offer', args, 'obs-fp', advance)
        self.assertEqual(receipt['outcome'], 'ACCEPTED')
        service = self.server.service
        fingerprint = service.receipts['obs-fp']['fingerprint']
        self.assertEqual(fingerprint, digest({
            'operation_id': 'obs-fp', 'op': 'offer', 'advance_id': advance, 'args': args,
        }))
        digest_before = service.machine.state_digest()
        for _ in range(3):
            self.request('GET', '/api/metrics')
            self.request('GET', '/api/health')
        self.settle()
        self.assertEqual(service.machine.state_digest(), digest_before)
        self.assertEqual(len(service.receipts), 1)
        self.assertEqual(service.receipts['obs-fp']['fingerprint'], fingerprint)
        self.assertEqual(service.observability.snapshot()['counters']['commands']['offer']['ACCEPTED'], 1)
        again = self.command(view['instance_id'], view['local_token'], 'offer', args, 'obs-fp', advance)
        self.assertIs(again['transport_duplicate'], True)
        self.settle()
        self.assertEqual(service.receipts['obs-fp']['fingerprint'], fingerprint)
        self.assertEqual(service.machine.state_digest(), digest_before)
        self.assertEqual(len(service.receipts), 1)
        self.assertEqual(service.observability.snapshot()['counters']['commands']['offer']['ACCEPTED'], 2)

    def test_persist_failure_is_not_a_command_outcome(self):
        self.start()
        view = self.state()

        def boom(_document):
            raise WorkspaceError('WORKSPACE_WRITE_FAILED')

        self.server.service.storage.save = boom
        body = {
            'instance_id': view['instance_id'], 'operation_id': 'obs-boom', 'op': 'offer',
            'advance_id': 'sim-obs-boom', 'args': {'fixture_id': 'sim-committed', 'amount': 1000},
        }
        status, raw = self.request('POST', '/api/commands', json.dumps(body), {
            'Content-Type': 'application/json', 'X-Capital-Token': view['local_token'],
        })
        self.assertEqual((status, json.loads(raw)['error']), (503, 'WORKSPACE_WRITE_FAILED'))
        self.settle()
        snap = self.server.service.observability.snapshot()
        self.assertEqual(snap['counters']['commands']['offer']['ACCEPTED'], 0)
        self.assertEqual(snap['counters']['commands']['offer']['REJECTED'], 0)
        self.assertEqual(snap['counters']['rejections']['WORKSPACE_WRITE_FAILED'], 1)
        status, raw = self.request('GET', '/api/health')
        self.assertEqual(status, 200, raw)
        health = json.loads(raw)
        self.assertEqual(health['status'], 'degraded')
        self.assertEqual(health['workspace_status'], 'WORKSPACE_WRITE_FAILED')

    def test_event_log_omits_bodies_and_a_bad_path_does_not_fail_the_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'pathleak7f3c9a.jsonl')
            self.start(event_log=path)
            view = self.state()
            advance = 'sim-argleak7f3c'
            receipt = self.command(
                view['instance_id'], view['local_token'], 'offer',
                {'fixture_id': 'sim-committed', 'amount': 424242}, 'opleak7f3c', advance)
            self.assertEqual(receipt['outcome'], 'ACCEPTED')
            status, raw = self.request('GET', '/api/nope')
            self.assertEqual(status, 404, raw)
            self.settle()
            text = Path(path).read_text(encoding='utf-8')
            lines = [line for line in text.splitlines() if line]
            self.assertGreaterEqual(len(lines), 2)
            for line in lines:
                row = json.loads(line)
                self.assertEqual(set(row), set(EVENT_LOG_KEYS))
                self.assertNotIn(view['local_token'], line)
                self.assertNotIn('sim-committed', line)
                self.assertNotIn(advance, line)
                self.assertNotIn('424242', line)
                self.assertNotIn('fixture_id', line)
                self.assertNotIn('args', line)
                self.assertNotIn('local_token', line)
                self.assertNotIn('pathleak7f3c9a', line)
            commands = [json.loads(line) for line in lines if json.loads(line)['route'] == '/api/commands']
            self.assertTrue(any(
                row['operation_id'] == 'opleak7f3c' and row['status'] == 200 and row['code'] is None
                for row in commands))
            missing = [json.loads(line) for line in lines if json.loads(line)['route'] == 'other']
            self.assertTrue(any(row['status'] == 404 and row['code'] == 'NOT_FOUND' and row['operation_id'] is None for row in missing))
            status, raw = self.request('GET', '/api/metrics')
            self.assertEqual(status, 200, raw)
            metrics = json.loads(raw)
            blob = json.dumps(metrics) + json.dumps(json.loads(self.request('GET', '/api/health')[1]))
            for secret in (view['local_token'], advance, 'opleak7f3c', 'pathleak7f3c9a', '424242', 'sim-committed'):
                self.assertNotIn(secret, blob, secret)
            event = metrics['counters']['event_log']
            self.assertTrue(event['enabled'])
            self.assertGreaterEqual(event['written'], 2)
            self.assertEqual(event['errors'], 0)
        self.stop()
        self.start(event_log='/nonexistent-dir/x.jsonl')
        view = self.state()
        receipt = self.command(
            view['instance_id'], view['local_token'], 'offer',
            {'fixture_id': 'sim-committed', 'amount': 1000}, 'obs-unwritable', 'sim-obs-unwritable')
        self.assertEqual(receipt['outcome'], 'ACCEPTED')
        self.settle()
        event = self.server.service.observability.snapshot()['counters']['event_log']
        self.assertTrue(event['enabled'])
        self.assertGreaterEqual(event['errors'], 1)
        self.assertEqual(event['written'], 0)

    def test_event_log_drop_is_visible_and_the_command_still_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'tiny.jsonl')
            self.start(event_log=path)
            self.server.service.observability.max_bytes = 1
            view = self.state()
            receipt = self.command(
                view['instance_id'], view['local_token'], 'offer',
                {'fixture_id': 'sim-committed', 'amount': 1000}, 'obs-drop', 'sim-obs-drop')
            self.assertEqual(receipt['outcome'], 'ACCEPTED')
            self.settle()
            event = self.server.service.observability.snapshot()['counters']['event_log']
            self.assertGreaterEqual(event['dropped'], 1)
            self.assertEqual(event['errors'], 0)
            self.assertEqual(event['written'], 0)
            self.assertEqual(Path(path).read_bytes(), b'')


if __name__ == '__main__':
    unittest.main()
