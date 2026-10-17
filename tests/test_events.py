"""Offline event-log summary: five-field shape validation, counts, no writes.

`python3 -m capital.events FILE --summary` reads one file, needs no server,
and writes nothing. The fixture log is built in memory (not under
tests/vectors/, which is the pinned-artifact tree). Tampered variants pin
the 1-based line number of the first malformed line. The round-trip test
compares a summary against the writing server's own counters.
"""
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

from capital.events import EventLogError, summarize_path
from capital.observability import HTTP_CLASSES
from capital.server import make_server

ROOT = Path(__file__).resolve().parents[1]
STAMP = r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z'


def _line(stamp, route, status, code, operation_id):
    row = {'time': stamp, 'route': route, 'status': status,
           'code': code, 'operation_id': operation_id}
    return json.dumps(row, ensure_ascii=True, separators=(',', ':'))


# Nine writer-shaped rows, deliberately out of chronological order so
# first_time/last_time must be min/max, not first/last in file order.
GOOD_ROWS = (
    ('2026-10-15T01:02:04.000000Z', '/api/commands', 200, None, 'evs-offer'),
    ('2026-10-15T01:02:03.000004Z', '/api/commands', 200, None, 'evs-approve'),
    ('2026-10-15T01:02:04.500000Z', '/api/commands', 200, None, 'evs-bind'),
    ('2026-10-15T01:02:05.000001Z', '/api/commands', 200, None, 'evs-draw'),
    ('2026-10-15T01:02:04.700000Z', '/api/commands', 200, None, 'evs-repay'),
    ('2026-10-15T01:02:04.900000Z', '/api/commands', 200, None, 'evs-close'),
    ('2026-10-15T01:02:04.950000Z', '/api/commands', 200, None, 'evs-close-2'),
    ('2026-10-15T01:02:04.200000Z', 'other', 404, 'NOT_FOUND', None),
    ('2026-10-15T01:02:04.800000Z', '/api/metrics', 403, 'ROLE_FORBIDDEN', None),
)


def fixture_bytes():
    return ''.join(_line(*row) + '\n' for row in GOOD_ROWS).encode('ascii')


class EventLogSummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, data, name='events.jsonl'):
        path = Path(self.tmp.name) / name
        path.write_bytes(data)
        return path

    def cli(self, *argv):
        return subprocess.run(
            [sys.executable, '-m', 'capital.events', *argv],
            cwd=ROOT, capture_output=True, text=True, timeout=60, check=False)

    def test_summary_counts_routes_statuses_codes_and_times(self):
        path = self.write(fixture_bytes())
        report = summarize_path(path)
        self.assertIs(report['ok'], True)
        self.assertIsNone(report['reason'])
        self.assertEqual(report['mode'], 'OFFLINE_EVENT_LOG_SUMMARY')
        self.assertEqual(report['label'], 'SIMULATED')
        self.assertEqual(report['diagnostic'], 'LOCAL_ONLY')
        self.assertEqual(report['file'], 'events.jsonl')
        self.assertEqual(report['events'], 9)
        self.assertEqual(report['first_time'], '2026-10-15T01:02:03.000004Z')
        self.assertEqual(report['last_time'], '2026-10-15T01:02:05.000001Z')
        self.assertEqual(report['by_route'], {'/api/commands': 7, '/api/metrics': 1, 'other': 1})
        self.assertEqual(report['by_status'], {'200': 7, '403': 1, '404': 1})
        self.assertEqual(report['by_status_class'], {'2xx': 7, '4xx': 2, '5xx': 0})
        self.assertEqual(report['by_code'], {'NOT_FOUND': 1, 'ROLE_FORBIDDEN': 1})
        self.assertEqual(report['without_code'], 7)
        self.assertEqual(report['event_log']['written'], 9)
        self.assertIsNone(report['event_log']['dropped'])
        self.assertIsNone(report['event_log']['errors'])
        self.assertEqual(report['event_log']['dropped_errors'], 'NOT_OBSERVABLE_OFFLINE')
        self.assertIn('counters.event_log', report['event_log']['note'])
        self.assertIs(report['writes'], False)
        self.assertIs(report['server_required'], False)
        self.assertIs(report['funds_executed'], False)
        self.assertEqual(report['not_bound'], {
            'exporter': 'NOT_BOUND',
            'tracing': 'NOT_BOUND',
            'alerting': 'NOT_BOUND',
            'network_sinks': 'NOT_BOUND',
            'audit_or_financial_evidence': 'NOT_BOUND',
        })

    def test_cli_prints_one_json_line_and_exits_zero(self):
        path = self.write(fixture_bytes())
        proc = self.cli(os.fspath(path), '--summary')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, '')
        self.assertEqual(proc.stdout.count('\n'), 1)
        self.assertEqual(json.loads(proc.stdout), summarize_path(path))

    def test_empty_file_is_zero_events_without_error(self):
        path = self.write(b'')
        report = summarize_path(path)
        self.assertIs(report['ok'], True)
        self.assertEqual(report['events'], 0)
        self.assertIsNone(report['first_time'])
        self.assertIsNone(report['last_time'])
        self.assertEqual(report['by_route'], {})
        self.assertEqual(report['by_status'], {})
        self.assertEqual(report['by_status_class'], {'2xx': 0, '4xx': 0, '5xx': 0})
        self.assertEqual(report['by_code'], {})
        self.assertEqual(report['without_code'], 0)
        self.assertEqual(report['event_log']['written'], 0)
        proc = self.cli(os.fspath(path), '--summary')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['events'], 0)

    def test_tampered_variants_exit_non_zero_naming_the_line(self):
        good = _line(*GOOD_ROWS[0])
        later = _line(*GOOD_ROWS[1])
        prefix = (good + '\n' + later + '\n').encode('ascii')
        suffix = (good + '\n').encode('ascii')
        variants = (
            ('BAD_JSON', b'{"time":"2026-10-15T01:02:04.000000Z","route":'),
            ('BAD_JSON', b'   '),
            ('BAD_JSON', good.encode('ascii').replace(b'"status":200', b'"status":200,"status":404')),
            ('BAD_JSON', good[:-1].encode('ascii') + b',\x00"route":"/api/commands"}'),
            ('NOT_AN_OBJECT', b'[1,2]'),
            ('NOT_AN_OBJECT', b'"nope"'),
            ('FIELD_SET', good[:-1].encode('ascii') + b',"extra":1}'),
            ('FIELD_SET', json.dumps(
                {'time': GOOD_ROWS[0][0], 'route': '/api/commands', 'status': 200,
                 'operation_id': None},
                ensure_ascii=True, separators=(',', ':')).encode('ascii')),
            ('FIELD_SET', json.dumps(
                {'time': GOOD_ROWS[0][0], 'route': '/api/commands', 'status': 200,
                 'codes': None, 'operation_id': None},
                ensure_ascii=True, separators=(',', ':')).encode('ascii')),
            ('TIME_SHAPE', _line('2026-10-15 01:02:04.000000Z', *GOOD_ROWS[0][1:]).encode('ascii')),
            ('TIME_SHAPE', _line('2026-13-15T01:02:04.000000Z', *GOOD_ROWS[0][1:]).encode('ascii')),
            ('TIME_SHAPE', _line('2026-02-30T01:02:04.000000Z', *GOOD_ROWS[0][1:]).encode('ascii')),
            ('TIME_SHAPE', _line('2026-10-15T01:02:04.0000Z', *GOOD_ROWS[0][1:]).encode('ascii')),
            ('TIME_SHAPE', _line(20261015, *GOOD_ROWS[0][1:]).encode('ascii')),
            ('ROUTE_SHAPE', _line('2026-10-15T01:02:04.000000Z', '', 200, None, None).encode('ascii')),
            ('ROUTE_SHAPE', _line('2026-10-15T01:02:04.000000Z', '/api/조회', 200, None, None).encode('utf-8')),
            ('STATUS_SHAPE', _line('2026-10-15T01:02:04.000000Z', '/api/commands', '200', None, None).encode('ascii')),
            ('STATUS_SHAPE', _line('2026-10-15T01:02:04.000000Z', '/api/commands', True, None, None).encode('ascii')),
            ('STATUS_SHAPE', _line('2026-10-15T01:02:04.000000Z', '/api/commands', 600, None, None).encode('ascii')),
            ('STATUS_SHAPE', _line('2026-10-15T01:02:04.000000Z', '/api/commands', 200.5, None, None).encode('ascii')),
            ('CODE_SHAPE', _line('2026-10-15T01:02:04.000000Z', '/api/commands', 404, 'not_found', None).encode('ascii')),
            ('CODE_SHAPE', _line('2026-10-15T01:02:04.000000Z', '/api/commands', 404, 'Bearer abc', None).encode('ascii')),
            ('CODE_SHAPE', _line('2026-10-15T01:02:04.000000Z', '/api/commands', 404, 7, None).encode('ascii')),
            ('OPERATION_ID_SHAPE', _line('2026-10-15T01:02:04.000000Z', '/api/commands', 200, None, 'evs oops!').encode('ascii')),
            ('OPERATION_ID_SHAPE', _line('2026-10-15T01:02:04.000000Z', '/api/commands', 200, None, 7).encode('ascii')),
            ('NON_ASCII', '{"time":"2026-10-15T01:02:04.000000Z","route":"/api/값"}'.encode('utf-8')),
            ('BLANK_LINE', b''),
        )
        for reason, line in variants:
            with self.subTest(reason=reason):
                path = self.write(prefix + line + b'\n' + suffix)
                with self.assertRaises(EventLogError) as caught:
                    summarize_path(path)
                self.assertEqual((caught.exception.reason, caught.exception.line_no), (reason, 3))
                self.assertIn(f'{reason} at line 3', str(caught.exception))
        bom = self.write(b'\xef\xbb\xbf' + fixture_bytes())
        with self.assertRaises(EventLogError) as caught:
            summarize_path(bom)
        self.assertEqual((caught.exception.reason, caught.exception.line_no), ('NON_ASCII', 1))
        no_trailing_newline = self.write(fixture_bytes()[:-1])
        self.assertEqual(summarize_path(no_trailing_newline)['events'], 9)

    def test_first_malformed_line_wins_and_names_the_line_on_stderr(self):
        prefix = ''.join(_line(*row) + '\n' for row in GOOD_ROWS[:2])
        suffix = _line(*GOOD_ROWS[2]) + '\n' + '{"time": [1]}\n'
        path = self.write((prefix + '{"route": "/api/commands"}\n' + suffix).encode('ascii'))
        with self.assertRaises(EventLogError) as caught:
            summarize_path(path)
        self.assertEqual((caught.exception.reason, caught.exception.line_no), ('FIELD_SET', 3))
        proc = self.cli(os.fspath(path), '--summary')
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, '')
        self.assertEqual(
            proc.stderr, f'capital.events: {os.fspath(path)}:3: FIELD_SET\n')

    def test_unregistered_route_and_unclassed_status_still_count(self):
        line = _line('2026-10-15T01:02:04.000000Z', '/api/future-tool', 302, None, None)
        path = self.write((line + '\n').encode('ascii'))
        report = summarize_path(path)
        self.assertIs(report['ok'], True)
        self.assertEqual(report['by_route'], {'/api/future-tool': 1})
        self.assertEqual(report['by_status'], {'302': 1})
        self.assertEqual(report['by_status_class'], {'2xx': 0, '4xx': 0, '5xx': 0, 'other': 1})
        self.assertEqual(report['without_code'], 1)

    def test_reads_one_file_and_writes_nothing(self):
        directory = Path(self.tmp.name)
        path = self.write(fixture_bytes())
        before = {entry.name: entry.read_bytes() for entry in sorted(directory.iterdir())}
        self.assertEqual(list(before), ['events.jsonl'])
        proc = self.cli(os.fspath(path), '--summary')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        after = {entry.name: entry.read_bytes() for entry in sorted(directory.iterdir())}
        self.assertEqual(after, before)

    def test_help_and_argument_misuse(self):
        self.assertEqual(self.cli('--help').returncode, 0)
        self.assertEqual(self.cli().returncode, 2)
        path = self.write(fixture_bytes())
        self.assertEqual(self.cli(os.fspath(path)).returncode, 2)

    def test_unreadable_paths_exit_one(self):
        absent = os.path.join(self.tmp.name, 'absent.jsonl')
        proc = self.cli(absent, '--summary')
        self.assertEqual((proc.returncode, proc.stderr.strip()),
                         (1, f'capital.events: {absent}: EVENT_LOG_UNREADABLE'))
        proc = self.cli(self.tmp.name, '--summary')
        self.assertEqual((proc.returncode, proc.stderr.strip()),
                         (1, f'capital.events: {self.tmp.name}: EVENT_LOG_UNREADABLE'))


class EventLogRoundTripTests(unittest.TestCase):
    def settle(self, server):
        previous = None
        stable = 0
        deadline = time.monotonic() + 2
        snap = None
        while time.monotonic() < deadline:
            snap = server.service.observability.snapshot()
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

    def request(self, method, path, server, body=None, headers=None):
        client = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        client.request(method, path, body=body, headers=headers or {})
        response = client.getresponse()
        raw, status = response.read(), response.status
        client.close()
        return status, raw

    def test_summary_matches_the_writing_servers_counters(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'events.jsonl')
            server = make_server(0, event_log=path)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                status, raw = self.request('GET', '/api/state', server)
                self.assertEqual(status, 200, raw)
                view = json.loads(raw)
                instance, token = view['instance_id'], view['local_token']
                advance = 'sim-evs-journey'

                def command(op, key, args):
                    body = {'instance_id': instance, 'operation_id': key, 'op': op,
                            'advance_id': advance, 'args': args}
                    status, raw = self.request('POST', '/api/commands', server, json.dumps(body), {
                        'Content-Type': 'application/json', 'X-Capital-Token': token})
                    self.assertEqual(status, 200, raw)
                    return json.loads(raw)

                self.assertEqual(command('offer', 'evs-offer', {
                    'fixture_id': 'sim-committed', 'amount': 60000})['outcome'], 'ACCEPTED')
                command('approve', 'evs-approve', {})
                command('bind_settlement', 'evs-bind', {})
                command('draw', 'evs-draw', {})
                refused = command('close', 'evs-close', {})
                self.assertEqual((refused['outcome'], refused['error']),
                                 ('REJECTED', 'OUTSTANDING_REMAINS'))
                command('repay', 'evs-repay', {'amount': 60000, 'sequence': 1})
                self.assertEqual(command('close', 'evs-close-2', {})['result']['credit']['phase'],
                                 'CLOSED')
                status, raw = self.request('GET', '/api/nope', server)
                self.assertEqual((status, json.loads(raw)['error']), (404, 'NOT_FOUND'))
                observer = server.authorizer.bind_role('observer')
                status, raw = self.request(
                    'GET', '/api/metrics', server, headers={'X-Capital-Token': observer})
                self.assertEqual((status, json.loads(raw)['error']), (403, 'ROLE_FORBIDDEN'))
                # The in-process snapshot adds no request, so the file and the
                # counters share one window once the counters settle.
                snap = self.settle(server)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(5)
            event = snap['counters']['event_log']
            self.assertIs(event['enabled'], True)
            self.assertEqual((event['errors'], event['dropped']), (0, 0))
            report = summarize_path(path)
            self.assertEqual(report['events'], event['written'])
            self.assertEqual(report['events'], 10)
            expected_routes = {
                route: sum(classes.values())
                for route, classes in snap['counters']['http_requests'].items()
                if sum(classes.values())}
            self.assertEqual(report['by_route'], expected_routes)
            expected_class = {klass: 0 for klass in HTTP_CLASSES}
            for classes in snap['counters']['http_requests'].values():
                for klass, count in classes.items():
                    expected_class[klass] += count
            self.assertEqual(report['by_status_class'], expected_class)
            self.assertEqual(report['by_status'], {'200': 8, '403': 1, '404': 1})
            self.assertEqual(report['by_code'], {'NOT_FOUND': 1, 'ROLE_FORBIDDEN': 1})
            # HTTP 200 rejection receipts carry code null, so the domain code
            # stays in counters.rejections and out of the file's by_code.
            self.assertEqual(snap['counters']['rejections'], {
                'OUTSTANDING_REMAINS': 1, 'ROLE_FORBIDDEN': 1, 'NOT_FOUND': 1})
            self.assertNotIn('OUTSTANDING_REMAINS', report['by_code'])
            self.assertEqual(report['without_code'], report['by_status']['200'])
            self.assertRegex(report['first_time'], rf'^{STAMP}$')
            self.assertRegex(report['last_time'], rf'^{STAMP}$')
            self.assertLessEqual(report['first_time'], report['last_time'])


if __name__ == '__main__':
    unittest.main()
