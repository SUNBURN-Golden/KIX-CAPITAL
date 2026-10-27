"""scripts/load_harness.py — deterministic smoke profile and report shape.

The smoke profile is a device check, not a performance measurement: no
wall-clock thresholds are asserted anywhere in this module.
"""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = 4242
WORKLOAD_IDS = (
    'low-load-uniform', 'uniform', 'hot-seat',
    'same-command-retry', 'history-growth', 'saturation',
)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


load_harness = _load('load_harness', ROOT / 'scripts' / 'load_harness.py')


class HelperTests(unittest.TestCase):
    def test_nearest_rank_picks_a_sample_never_an_average(self):
        self.assertIsNone(load_harness._nearest_rank([], 99))
        self.assertEqual(load_harness._nearest_rank([10, 20, 30, 40], 50), 20)
        self.assertEqual(load_harness._nearest_rank([10, 20, 30, 40], 90), 40)
        self.assertEqual(load_harness._nearest_rank([10, 20, 30, 40], 99), 40)
        self.assertEqual(load_harness._nearest_rank([7], 99), 7)
        stats = load_harness._stats([30, 10, 20])
        self.assertEqual(
            stats, {'count': 3, 'min': 10, 'p50': 20, 'p90': 30, 'p99': 30, 'max': 30})
        self.assertIsNone(load_harness._stats([]))

    def test_classify_maps_the_facade_contract(self):
        classify = load_harness._classify
        self.assertEqual(classify(200, {'outcome': 'ACCEPTED', 'transport_duplicate': False}), 'new_success')
        self.assertEqual(classify(200, {'outcome': 'ACCEPTED', 'transport_duplicate': True}), 'replay')
        self.assertEqual(classify(200, {'outcome': 'REJECTED', 'error': 'X'}), 'reject')
        self.assertEqual(classify(200, {'outcome': 'REJECTED', 'transport_duplicate': True}), 'replay')
        self.assertEqual(classify(409, {'error': 'IDEMPOTENCY_CONFLICT'}), 'conflict')
        self.assertEqual(classify(409, {'error': 'SIMULATION_CAPACITY'}), 'capacity')
        for status, payload in (
            (400, {'error': 'INVALID_COMMAND'}), (409, {'error': 'SESSION_CHANGED'}),
            (200, {'outcome': 'UNKNOWN'}), (500, {}), (200, 'oops'),
        ):
            self.assertEqual(classify(status, payload), 'other', (status, payload))

    def test_fingerprint_covers_only_seeded_inputs(self):
        first = load_harness.input_fingerprint(
            load_harness.build_inputs('smoke', SEED, ('memory',)))
        again = load_harness.input_fingerprint(
            load_harness.build_inputs('smoke', SEED, ('memory',)))
        self.assertEqual(first, again)
        self.assertRegex(first, r'[0-9a-f]{64}\Z')
        other_seed = load_harness.input_fingerprint(
            load_harness.build_inputs('smoke', SEED + 1, ('memory',)))
        other_mode = load_harness.input_fingerprint(
            load_harness.build_inputs('smoke', SEED, ('workspace',)))
        self.assertNotEqual(first, other_seed)
        self.assertNotEqual(first, other_mode)

    def test_specs_never_carry_volatile_fields(self):
        inputs = load_harness.build_inputs('smoke', SEED, ('memory',))
        blob = json.dumps(inputs['workloads'], sort_keys=True, default=list)
        for volatile in ('instance_id', 'local_token', 'server_port'):
            self.assertNotIn(volatile, blob)
        for workload in inputs['workloads']:
            for phase in workload['phases']:
                for thread in phase['threads']:
                    for spec in thread:
                        self.assertRegex(spec['operation_id'], r'[a-zA-Z0-9-]{1,80}\Z')
                        self.assertRegex(spec['advance_id'], r'sim-[a-zA-Z0-9-]{1,60}\Z')


class SmokeProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.memory = load_harness.run(profile='smoke', mode='memory', seed=SEED)
        cls.workspace = load_harness.run(profile='smoke', mode='workspace', seed=SEED)

    def _workloads(self, report):
        by_id = {}
        for workload in report['workloads']:
            self.assertNotIn(workload['id'], by_id, workload['id'])
            by_id[workload['id']] = workload
        return by_id

    def _assert_report(self, report, mode, kind):
        self.assertEqual(report['format'], 'KIX_CAPITAL_LOAD_REPORT_V1')
        self.assertEqual(report['label'], 'LOCAL_EXPLORATION')
        self.assertEqual(report['evidence'], 'NOT_PRODUCTION_PERFORMANCE_EVIDENCE')
        self.assertIs(report['funds_executed'], False)
        self.assertTrue(report['ok'])
        self.assertEqual(report['modes'], [mode])
        for name in ('python', 'implementation', 'os', 'machine', 'cpu_count'):
            self.assertIn(name, report['environment'])
        self.assertEqual(
            report['input_fingerprint'],
            load_harness.input_fingerprint(
                load_harness.build_inputs('smoke', SEED, (mode,))))
        workloads = self._workloads(report)
        self.assertEqual(tuple(workloads), WORKLOAD_IDS)
        for workload_id, workload in workloads.items():
            self.assertEqual(workload['mode'], mode, workload_id)
            self.assertEqual(workload['workspace_kind'], kind, workload_id)
            self.assertTrue(workload['ok'], (workload_id, workload['assertions']))
            for name, passed in workload['assertions'].items():
                self.assertTrue(passed, (workload_id, name))
            self.assertEqual(
                workload['operation_count'],
                workload['assertions'] and sum(
                    stats['count']
                    for cls, stats in workload['classes'].items()
                    if cls in ('new_success', 'reject')))
            self.assertEqual(
                workload['journal_length'],
                workload['classes'].get('new_success', {}).get('count', 0))
            total = sum(stats['count'] for stats in workload['classes'].values())
            self.assertEqual(total, workload['requests'], workload_id)
            self.assertEqual(len(workload['samples']), workload['requests'])
            for cls, stats in workload['classes'].items():
                bucket = [s for s in workload['samples'] if s['class'] == cls]
                self.assertEqual(stats['count'], len(bucket), (workload_id, cls))
                if stats['service_ms'] is not None:
                    self.assertEqual(stats['service_ms']['count'], len(bucket))
        return workloads

    def test_memory_smoke_six_workloads(self):
        self._assert_report(self.memory, 'memory', 'MEMORY')

    def test_workspace_smoke_six_workloads(self):
        self._assert_report(self.workspace, 'workspace', 'LOCAL_FILE_WORKSPACE')

    def test_outcome_classes_observed_where_expected(self):
        for report in (self.memory, self.workspace):
            workloads = self._workloads(report)
            self.assertEqual(
                set(workloads['low-load-uniform']['classes']), {'new_success'})
            for workload_id, expected in (
                ('uniform', {'new_success', 'reject'}),
                ('hot-seat', {'new_success', 'reject'}),
                ('same-command-retry', {'new_success', 'reject', 'replay'}),
                ('history-growth', {'new_success', 'conflict'}),
                ('saturation', {'reject', 'capacity', 'replay', 'conflict'}),
            ):
                self.assertEqual(set(workloads[workload_id]['classes']), expected, workload_id)

    def test_saturation_records_the_capacity_boundary(self):
        for report in (self.memory, self.workspace):
            saturation = self._workloads(report)['saturation']
            self.assertEqual(saturation['operation_count'], load_harness.MAX_OPERATIONS)
            self.assertEqual(saturation['journal_length'], 0)
            capacity = [s for s in saturation['samples'] if s['class'] == 'capacity']
            self.assertEqual(len(capacity), 6)
            self.assertIsInstance(saturation['first_capacity_index'], int)
            self.assertGreater(saturation['samples_after_first_capacity'], 0)
            replay = [s for s in saturation['samples'] if s['class'] == 'replay']
            self.assertEqual(len(replay), 1)
            self.assertIs(replay[0]['receipt_match'], True)

    def test_retry_and_conflict_classes_write_nothing(self):
        for report in (self.memory, self.workspace):
            workloads = self._workloads(report)
            retry = workloads['same-command-retry']
            self.assertEqual(retry['journal_length'], 1)
            self.assertEqual(retry['operation_count'], 2)
            self.assertTrue(all(
                sample['receipt_match']
                for sample in retry['samples'] if sample['class'] == 'replay'))
            growth = workloads['history-growth']
            conflicts = [s for s in growth['samples'] if s['class'] == 'conflict']
            self.assertGreaterEqual(len(conflicts), 2)
            for check in growth['phase_checks']:
                if check['name'] == 'conflict':
                    self.assertEqual(check['journal_delta'], 0)
                    self.assertEqual(check['receipts_delta'], 0)

    def test_report_makes_no_slo_or_tps_claim(self):
        for report in (self.memory, self.workspace):
            self.assertEqual(report['claims'], {
                'slo': 'NOT_MEASURED',
                'tps': 'NOT_REPORTED',
                'throughput': 'NOT_REPORTED',
                'production': 'NOT_AUTHORIZED',
            })
            blob = json.dumps(report, sort_keys=True)
            for key in ('"slo"', '"tps"', '"throughput"'):
                value = blob.split(key, 1)[1].lstrip(' :').split(',', 1)[0]
                self.assertTrue(value.startswith('"NOT_'), (key, value))
            self.assertNotIn('mixed', blob)

    def test_schedule_and_service_fields_stay_separate(self):
        for report in (self.memory, self.workspace):
            for workload in report['workloads']:
                for sample in workload['samples']:
                    self.assertIn('scheduled_at_ms', sample)
                    self.assertIn('service_ms', sample)
                    if sample['scheduled_at_ms'] is None:
                        self.assertIsNone(sample['schedule_delay_ms'])
                        self.assertIsNone(sample['scheduled_latency_ms'])


if __name__ == '__main__':
    unittest.main()
