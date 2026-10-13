"""LOCAL_FAKE_GATE adapter. Not SEMANTIC_CONFORMANCE. CAP-16 stays NOT_BOUND."""
import json
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from capital.gate_producer import (
    LABEL, GateHttpProducer, GateProtocolError, ProducerUnknown, load_fake_gate,
)
from capital.ports import ProducerPort
from capital.producer import PinnedFsmProducer
from capital.server import make_server
from capital.service import CapitalService
from capital.store import FileWorkspace
from test_producer_port import VECTORS, run_producer_vectors

ROOT = Path(__file__).resolve().parents[1]
SEAMS = ROOT / 'docs' / 'SEAMS.md'
GOLDEN = ROOT / 'tests' / 'golden' / 'demo.json'
fake_gate = load_fake_gate()


def _load_seed():
    import importlib.util
    spec = importlib.util.spec_from_file_location('seed_demo_gate', ROOT / 'scripts' / 'seed_demo.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed = _load_seed()


def _raw(method, url, payload=None, timeout=2):
    data = None
    headers = {'Accept': 'application/json'}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    return status, json.loads(raw.decode('utf-8'))


def _offer(producer, key='offer-1', amount=1000, fixture='sim-committed', advance='sim-a'):
    return producer.apply(
        'offer', advance, idempotency_key=key,
        args={'fixture_id': fixture, 'amount': amount}, bound_settlement_id=None)


class GateProducerTests(unittest.TestCase):
    def test_vectors_pass_over_loopback_without_claiming_conformance(self):
        opened = []

        def factory():
            producer = GateHttpProducer()
            opened.append(producer)
            self.assertTrue(producer.base_url.startswith('http://127.0.0.1:'))
            self.assertIsInstance(producer, ProducerPort)
            self.assertEqual(producer.label, 'LOCAL_FAKE_GATE')
            self.assertIs(producer.semantic_conformance, False)
            return producer

        try:
            run_producer_vectors(factory)
            self.assertEqual(len(opened), len(VECTORS))
        finally:
            for producer in opened:
                producer.close()

    def test_gate_fake_seed_matches_the_pinned_golden_digests(self):
        pinned = seed.build_service()
        gated = seed.build_service(producer_name='gate-fake')
        try:
            left = seed.capture(pinned)
            right = seed.capture(gated)
            self.assertEqual(left['state_digest'], right['state_digest'])
            self.assertEqual(left['content_digest'], right['content_digest'])
            self.assertEqual(left, right)
            self.assertEqual(right, json.loads(GOLDEN.read_text(encoding='utf-8')))
            self.assertEqual(gated.producer.label, 'LOCAL_FAKE_GATE')
        finally:
            gated.producer.close()
        self.assertEqual(seed.main(['--producer', 'gate-fake', '--golden', str(GOLDEN)]), 0)

    def test_gate_fake_workspace_reloads_on_the_pinned_producer(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(seed.main(['--workspace', tmp, '--producer', 'gate-fake', '--golden', str(GOLDEN)]), 0)
            storage = FileWorkspace.open(tmp)
            try:
                restored = CapitalService(storage)
                self.assertEqual(seed.capture(restored), json.loads(GOLDEN.read_text(encoding='utf-8')))
            finally:
                storage.close()

    def test_dropped_response_after_apply_is_unknown_without_retry(self):
        control = GateHttpProducer()
        faulted = GateHttpProducer()
        try:
            _offer(control, key='offer-1')
            expected = control.apply(
                'approve', 'sim-a', idempotency_key='approve-1', args={}, bound_settlement_id=None)
            _offer(faulted, key='offer-1')
            before = faulted.post_count('approve-1')
            faulted.gate.arm('approve-1', 'drop-after')
            with self.assertRaises(ProducerUnknown) as caught:
                faulted.apply('approve', 'sim-a', idempotency_key='approve-1', args={}, bound_settlement_id=None)
            self.assertEqual(caught.exception.code, 'UNKNOWN')
            self.assertEqual(caught.exception.outcome, 'UNKNOWN')
            self.assertIs(caught.exception.retry_authorized, False)
            self.assertEqual(faulted.post_count('approve-1'), before + 1)
            self.assertEqual(faulted.gate.post_count('approve-1'), 1)
            receipt = faulted.lookup('approve-1')
            self.assertEqual(receipt['label'], 'LOCAL_FAKE_GATE')
            self.assertIs(receipt['semantic_conformance'], False)
            self.assertIs(receipt['funds_executed'], False)
            self.assertEqual(receipt['binding'], 'NOT_BOUND')
            self.assertEqual(receipt['outcome'], 'ACCEPTED')
            self.assertEqual(receipt['operationId'], 'approve-1')
            self.assertIs(receipt['actor_is_authentication'], False)
            self.assertEqual(receipt['result'], expected)
            self.assertEqual(faulted.view('sim-a')['phase'], 'APPROVED')
            self.assertEqual(faulted.post_count('approve-1'), 1)
        finally:
            control.close()
            faulted.close()

    def test_drop_before_apply_does_not_change_the_book(self):
        producer = GateHttpProducer()
        try:
            _offer(producer)
            digest = producer.state_digest()
            producer.gate.arm('approve-1', 'drop-before')
            with self.assertRaises(ProducerUnknown) as caught:
                producer.apply('approve', 'sim-a', idempotency_key='approve-1', args={}, bound_settlement_id=None)
            self.assertEqual(caught.exception.code, 'UNKNOWN')
            self.assertIs(caught.exception.retry_authorized, False)
            self.assertEqual(producer.post_count('approve-1'), 1)
            self.assertIsNone(producer.lookup('approve-1'))
            self.assertEqual(producer.state_digest(), digest)
            self.assertEqual(producer.view('sim-a')['phase'], 'OFFERED')
        finally:
            producer.close()

    def test_timeout_is_unknown_and_the_original_receipt_remains(self):
        producer = GateHttpProducer(timeout=0.4)
        producer.gate.fault_delay = 1.0
        try:
            _offer(producer)
            producer.gate.arm('approve-1', 'timeout')
            started = time.monotonic()
            with self.assertRaises(ProducerUnknown) as caught:
                producer.apply('approve', 'sim-a', idempotency_key='approve-1', args={}, bound_settlement_id=None)
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, 0.9)
            self.assertEqual(caught.exception.code, 'UNKNOWN')
            self.assertIs(caught.exception.retry_authorized, False)
            self.assertEqual(producer.post_count('approve-1'), 1)
            receipt = producer.lookup('approve-1')
            self.assertEqual(receipt['outcome'], 'ACCEPTED')
            self.assertEqual(receipt['result']['credit']['phase'], 'APPROVED')
            self.assertIs(receipt['result']['duplicate'], False)
            self.assertEqual(producer.post_count('approve-1'), 1)
        finally:
            producer.close()

    def test_unknown_fields_and_operation_id_mismatch_are_rejected(self):
        producer = GateHttpProducer()
        try:
            digest = producer.state_digest()
            valid = {
                'operationId': 'offer-1',
                'actor': 'SIMULATED',
                'action': 'offer',
                'body': {
                    'operation_id': 'offer-1',
                    'advance_id': 'sim-a',
                    'args': {'fixture_id': 'sim-committed', 'amount': 1000},
                    'bound_settlement_id': None,
                },
            }
            extra = {**valid, 'note': 'nope'}
            status, body = _raw('POST', producer.base_url + '/v1/commands', extra)
            self.assertEqual(status, 400)
            self.assertEqual(body['error'], 'UNKNOWN_FIELDS')
            self.assertEqual(body['label'], 'LOCAL_FAKE_GATE')
            self.assertIs(body['semantic_conformance'], False)
            nested = json.loads(json.dumps(valid))
            nested['body']['extra'] = True
            status, body = _raw('POST', producer.base_url + '/v1/commands', nested)
            self.assertEqual(status, 400)
            self.assertEqual(body['error'], 'UNKNOWN_FIELDS')
            args = json.loads(json.dumps(valid))
            args['body']['args']['fee'] = 1
            status, body = _raw('POST', producer.base_url + '/v1/commands', args)
            self.assertEqual(status, 400)
            self.assertEqual(body['error'], 'UNKNOWN_FIELDS')
            mismatch = json.loads(json.dumps(valid))
            mismatch['body']['operation_id'] = 'offer-2'
            status, body = _raw('POST', producer.base_url + '/v1/commands', mismatch)
            self.assertEqual(status, 400)
            self.assertEqual(body['error'], 'OPERATION_ID_MISMATCH')
            self.assertEqual(producer.post_count('offer-1'), 0)
            self.assertEqual(producer.state_digest(), digest)
            result = _offer(producer, key='offer-1')
            self.assertEqual(producer.gate.last_request['operationId'], 'offer-1')
            self.assertEqual(producer.gate.last_request['body']['operation_id'], 'offer-1')
            self.assertEqual(result['credit']['phase'], 'OFFERED')
            self.assertIs(result['funds_executed'], False)
        finally:
            producer.close()

    def test_actor_is_not_authentication(self):
        producer = GateHttpProducer(actor='not-a-role')
        try:
            _offer(producer, key='offer-9')
            receipt = producer.lookup('offer-9')
            self.assertEqual(receipt['actor'], 'not-a-role')
            self.assertIs(receipt['actor_is_authentication'], False)
            self.assertNotIn('organizer', receipt['actor'])
            self.assertNotIn('authenticated', receipt)
            status, body = _raw('POST', producer.base_url + '/v1/commands', {
                'operationId': 'offer-8',
                'actor': 'organizer',
                'action': 'offer',
                'body': {
                    'operation_id': 'offer-8',
                    'advance_id': 'sim-b',
                    'args': {'fixture_id': 'sim-committed', 'amount': 100},
                    'bound_settlement_id': None,
                },
            })
            self.assertEqual(status, 200)
            self.assertEqual(body['actor'], 'organizer')
            self.assertIs(body['actor_is_authentication'], False)
            self.assertEqual(body['result']['credit']['phase'], 'OFFERED')
        finally:
            producer.close()

    def test_non_loopback_bind_is_refused(self):
        for host in ('0.0.0.0', 'localhost', '8.8.8.8', ''):
            with self.assertRaises(fake_gate.FakeGateError) as caught:
                fake_gate.start(host, 0)
            self.assertEqual(caught.exception.code, 'NON_LOOPBACK_BIND', host)
        self.assertEqual(fake_gate.main(['--host', '0.0.0.0', '--port', '9']), 2)
        gate = fake_gate.start('127.0.0.1', 0)
        try:
            self.assertEqual(gate.host, '127.0.0.1')
            self.assertTrue(gate.url.startswith('http://127.0.0.1:'))
        finally:
            gate.close()

    def test_same_command_matches_the_pinned_producer(self):
        pinned = PinnedFsmProducer()
        gated = GateHttpProducer()
        try:
            kwargs = dict(idempotency_key='offer-1', args={'fixture_id': 'sim-committed', 'amount': 1000}, bound_settlement_id=None)
            left = pinned.apply('offer', 'sim-a', **kwargs)
            right = gated.apply('offer', 'sim-a', **kwargs)
            self.assertEqual(left, right)
            self.assertEqual(pinned.state_digest(), gated.state_digest())
            self.assertEqual(pinned.canonical_state(), gated.canonical_state())
            self.assertEqual(pinned.export_journal(), gated.export_journal())
        finally:
            gated.close()

    def test_server_flag_is_opt_in_and_stops(self):
        proc = subprocess.Popen(
            [sys.executable, '-m', 'capital.server', '--port', '0', '--producer', 'gate-fake'],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        lines = []

        def _read_banner():
            for _ in range(2):
                lines.append(proc.stdout.readline())

        reader = threading.Thread(target=_read_banner, daemon=True)
        reader.start()
        try:
            reader.join(5)
            self.assertEqual(len(lines), 2, lines or (proc.stderr.read() if proc.poll() is not None else 'no stdout'))
            line, producer_line = lines
            self.assertIn('http://127.0.0.1:', line)
            self.assertIn('LOCAL_FAKE_GATE', producer_line)
            self.assertIn('NOT_BOUND', producer_line)
            self.assertIn('semantic_conformance=false', producer_line)
            port = int(line.rsplit(':', 1)[-1].strip())
            status, body = _raw('GET', f'http://127.0.0.1:{port}/api/state')
            self.assertEqual(status, 200)
            self.assertEqual(body['mode'], 'LOCAL_SIMULATION')
            self.assertIs(body['funds_executed'], False)
        finally:
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
            proc.stdout.close()
            proc.stderr.close()

    def test_make_server_uses_an_injected_gate_producer(self):
        producer = GateHttpProducer()
        server = make_server(0, producer=producer)
        try:
            self.assertIs(server.service.producer, producer)
            self.assertEqual(server.service.producer.label, LABEL)
            pinned = CapitalService()
            body = {
                'instance_id': server.service.instance_id, 'operation_id': 'injected-offer', 'op': 'offer',
                'advance_id': 'sim-a', 'args': {'fixture_id': 'sim-committed', 'amount': 1000},
            }
            left = server.service.execute(body)
            right = pinned.execute({**body, 'instance_id': pinned.instance_id})
            self.assertEqual(left['outcome'], 'ACCEPTED')
            self.assertEqual(left['result']['credit']['phase'], right['result']['credit']['phase'])
            self.assertEqual(server.service.machine.state_digest(), pinned.machine.state_digest())
        finally:
            server.server_close()

    def test_seams_keep_producer_port_not_bound(self):
        text = SEAMS.read_text(encoding='utf-8')
        row = next(line for line in text.splitlines() if line.startswith('| ProducerPort |'))
        cells = [cell.strip() for cell in row.strip().strip('|').split('|')]
        self.assertEqual(cells[4], 'NOT_BOUND')
        self.assertEqual(cells[5], 'NONE')
        self.assertIn('LOCAL_FAKE_GATE', cells[1])
        self.assertIn('PinnedFsmProducer', cells[1])
        self.assertIn('not a SEMANTIC_CONFORMANCE', text)
        self.assertIn('still not a SEMANTIC_CONFORMANCE', text)
        integration = (ROOT / 'docs' / 'INTEGRATION.md').read_text(encoding='utf-8')
        self.assertIn('LOCAL_FAKE_GATE', integration)
        self.assertIn('not SEMANTIC_CONFORMANCE', integration)
        for relative in ('capital/gate_producer.py', 'scripts/fake_gate.py'):
            source = (ROOT / relative).read_text(encoding='utf-8')
            self.assertIn('LOCAL_FAKE_GATE', source)
            self.assertIn('NOT_BOUND', source)
            for line in source.splitlines():
                if 'SEMANTIC_CONFORMANCE' in line:
                    self.assertIn('not ', line.lower(), line)

    def test_client_refuses_a_non_loopback_base_url(self):
        with self.assertRaises(GateProtocolError) as caught:
            GateHttpProducer(base_url='http://8.8.8.8:9')
        self.assertEqual(caught.exception.code, 'NON_LOOPBACK')


if __name__ == '__main__':
    unittest.main()
