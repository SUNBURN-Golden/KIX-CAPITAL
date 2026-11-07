"""LOCAL_FAKE_OBSERVATION adapter. Not SEMANTIC_CONFORMANCE. CAP-14 stays NOT_BOUND."""
import copy
import json
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import capital.observation_http as observation_http
from capital.observation import LocalFakeObservation
from capital.observation_http import (
    LABEL, ObservationHttpAdapter, ObservationProtocolError, ObservationUnavailable,
    load_fake_observation,
)
from capital.ports import ObservationPort
from capital.service import CapitalService
from test_observation_port import CORPUS, run_observation_vectors

ROOT = Path(__file__).resolve().parents[1]
SEAMS = ROOT / 'docs' / 'SEAMS.md'
fake_observation = load_fake_observation()
_TABLE = json.loads(CORPUS.read_text())
BASE_FACT = _TABLE['base_fact']
BASE_BINDINGS = _TABLE['bindings']


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


class ObservationHttpTests(unittest.TestCase):
    def test_vectors_pass_over_loopback(self):
        shared = fake_observation.start()
        opened = []

        def factory():
            adapter = ObservationHttpAdapter(fake=shared)
            opened.append(adapter)
            return adapter

        try:
            run_observation_vectors(factory)
            self.assertTrue(opened)
            self.assertGreater(shared.posts, 0)
        finally:
            shared.close()

    def test_adapter_reports_honest_labels(self):
        adapter = ObservationHttpAdapter()
        try:
            self.assertIsInstance(adapter, ObservationPort)
            self.assertEqual(adapter.label, 'LOCAL_FAKE_OBSERVATION')
            self.assertIs(adapter.semantic_conformance, False)
            self.assertTrue(adapter.base_url.startswith('http://127.0.0.1:'))
            self.assertEqual(adapter.post_count(), 0)
            result = adapter.fold([BASE_FACT], bindings=BASE_BINDINGS)
            self.assertEqual(result, LocalFakeObservation().fold(
                [copy.deepcopy(BASE_FACT)], bindings=copy.deepcopy(BASE_BINDINGS)))
            self.assertEqual(adapter.post_count(), 1)
        finally:
            adapter.close()

    def test_populated_state_unchanged_for_every_case(self):
        from test_overlay import draw_book, tick
        service = CapitalService()
        draw_book(service)
        tick(service, 'sim-observation-http-tick', 0, 1)

        def snapshot():
            return copy.deepcopy((service.machine.state_digest(), service.machine.canonical_state(),
                                  service.machine.export_journal(), service.receipts,
                                  service.overlay_state(), service.overlay_entries, len(service.receipts)))

        before = snapshot()
        self.assertTrue(service.machine.export_journal())
        self.assertTrue(service.overlay_entries)
        shared = fake_observation.start()
        self_test = self

        class Checked(ObservationHttpAdapter):
            def fold(self, facts, *, bindings):
                result = super().fold(facts, bindings=bindings)
                self_test.assertEqual(snapshot(), before)
                return result

        try:
            run_observation_vectors(lambda: Checked(fake=shared))
        finally:
            shared.close()
        self.assertEqual(snapshot(), before)

    def test_non_loopback_bind_is_refused(self):
        for host in ('0.0.0.0', 'localhost', '8.8.8.8', ''):
            with self.assertRaises(fake_observation.FakeObservationError) as caught:
                fake_observation.start(host, 0)
            self.assertEqual(caught.exception.code, 'NON_LOOPBACK_BIND', host)
        self.assertEqual(fake_observation.main(['--host', '0.0.0.0', '--port', '9']), 2)
        self.assertEqual(
            fake_observation.main(['--port', '0', '--fault', 'bogus']), 2)
        fake = fake_observation.start('127.0.0.1', 0)
        try:
            self.assertEqual(fake.host, '127.0.0.1')
            self.assertTrue(fake.url.startswith('http://127.0.0.1:'))
        finally:
            fake.close()

    def test_client_refuses_a_non_loopback_base_url(self):
        for url in ('http://8.8.8.8:9', 'http://localhost:9', 'https://127.0.0.1:9',
                    'ftp://127.0.0.1:9', 'http://127.0.0.1:9/path', 'http://127.0.0.1:9/?q=1',
                    'http://user@127.0.0.1:9', 'http://127.0.0.1', 'not-a-url', 7):
            with self.subTest(url=url), self.assertRaises(ObservationProtocolError) as caught:
                ObservationHttpAdapter(base_url=url)
            self.assertEqual(caught.exception.code, 'NON_LOOPBACK', url)

    def _fault_fold(self, fault, timeout=5.0, fault_delay=1.0):
        fake = fake_observation.start(fault_delay=fault_delay)
        adapter = ObservationHttpAdapter(fake=fake, timeout=timeout)
        fake.arm(fault)
        return fake, adapter

    def test_malformed_json_reply_is_a_protocol_error(self):
        fake, adapter = self._fault_fold('malformed-json')
        try:
            with self.assertRaises(ObservationProtocolError) as caught:
                adapter.fold([BASE_FACT], bindings=BASE_BINDINGS)
            self.assertEqual(caught.exception.code, 'INVALID_JSON')
            self.assertEqual(fake.posts, 1)
            self.assertEqual(adapter.post_count(), 1)
        finally:
            fake.close()

    def test_duplicate_key_reply_is_a_protocol_error(self):
        fake, adapter = self._fault_fold('duplicate-key')
        try:
            with self.assertRaises(ObservationProtocolError) as caught:
                adapter.fold([BASE_FACT], bindings=BASE_BINDINGS)
            self.assertEqual(caught.exception.code, 'INVALID_JSON')
            self.assertEqual(fake.posts, 1)
            self.assertEqual(adapter.post_count(), 1)
        finally:
            fake.close()

    def test_oversized_reply_is_a_protocol_error(self):
        fake, adapter = self._fault_fold('oversized')
        try:
            with self.assertRaises(ObservationProtocolError) as caught:
                adapter.fold([BASE_FACT], bindings=BASE_BINDINGS)
            self.assertEqual(caught.exception.code, 'REPLY_TOO_LARGE')
            self.assertEqual(fake.posts, 1)
            self.assertEqual(adapter.post_count(), 1)
        finally:
            fake.close()

    def test_dropped_connection_is_unavailable_and_not_retried(self):
        fake, adapter = self._fault_fold('drop')
        try:
            with self.assertRaises(ObservationUnavailable) as caught:
                adapter.fold([BASE_FACT], bindings=BASE_BINDINGS)
            self.assertEqual(caught.exception.code, 'OBSERVATION_UNAVAILABLE')
            self.assertEqual(fake.posts, 1)
            self.assertEqual(adapter.post_count(), 1)
        finally:
            fake.close()

    def test_timeout_is_unavailable_and_not_retried(self):
        fake, adapter = self._fault_fold('timeout', timeout=0.4, fault_delay=1.0)
        try:
            started = time.monotonic()
            with self.assertRaises(ObservationUnavailable) as caught:
                adapter.fold([BASE_FACT], bindings=BASE_BINDINGS)
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, 0.9)
            self.assertEqual(caught.exception.code, 'OBSERVATION_UNAVAILABLE')
            self.assertEqual(fake.posts, 1)
            self.assertEqual(adapter.post_count(), 1)
        finally:
            fake.close()

    def test_redirect_is_refused_not_followed(self):
        fake, adapter = self._fault_fold('redirect')
        try:
            with self.assertRaises(ObservationProtocolError) as caught:
                adapter.fold([BASE_FACT], bindings=BASE_BINDINGS)
            self.assertEqual(caught.exception.code, 'REDIRECT_REFUSED')
            self.assertEqual(caught.exception.status, 302)
            self.assertEqual(fake.posts, 1)
            self.assertEqual(adapter.post_count(), 1)
        finally:
            fake.close()

    def test_altered_identity_label_is_refused(self):
        fake, adapter = self._fault_fold('alter-identity')
        try:
            with self.assertRaises(ObservationProtocolError) as caught:
                adapter.fold([BASE_FACT], bindings=BASE_BINDINGS)
            self.assertEqual(caught.exception.code, 'IDENTITY_MISMATCH')
            self.assertEqual(fake.posts, 1)
            self.assertEqual(adapter.post_count(), 1)
        finally:
            fake.close()

    def test_altered_execution_labels_are_refused(self):
        fake, adapter = self._fault_fold('alter-execution')
        try:
            with self.assertRaises(ObservationProtocolError) as caught:
                adapter.fold([BASE_FACT], bindings=BASE_BINDINGS)
            self.assertEqual(caught.exception.code, 'FUNDS_EXECUTED')
            self.assertEqual(fake.posts, 1)
            self.assertEqual(adapter.post_count(), 1)
        finally:
            fake.close()

    def test_domain_validation_maps_to_value_error(self):
        fake = fake_observation.start()
        adapter = ObservationHttpAdapter(fake=fake)
        try:
            bad = dict(BASE_FACT, amount=-1)
            with self.assertRaises(ValueError) as caught:
                adapter.fold([bad], bindings=BASE_BINDINGS)
            self.assertEqual(str(caught.exception), 'FOLD_INVALID')
            self.assertEqual(fake.posts, 1)
        finally:
            fake.close()

    def test_non_list_arguments_fail_before_transport(self):
        fake = fake_observation.start()
        adapter = ObservationHttpAdapter(fake=fake)
        try:
            for facts, bindings in ((None, []), ({}, []), ([BASE_FACT], None), ([BASE_FACT], {})):
                with self.subTest(facts=facts, bindings=bindings), self.assertRaises(ValueError):
                    adapter.fold(facts, bindings=bindings)
            self.assertEqual(fake.posts, 0)
        finally:
            fake.close()

    def test_reply_validation_refuses_dishonest_stamps(self):
        result = LocalFakeObservation().fold(
            [copy.deepcopy(BASE_FACT)], bindings=copy.deepcopy(BASE_BINDINGS))
        envelope = {
            'label': LABEL, 'mode': 'SIMULATED', 'binding': 'NOT_BOUND',
            'semantic_conformance': False, 'funds_executed': False,
            'result': copy.deepcopy(result)}
        for mutate, code in (
                (lambda p: p.update(label='OTHER'), 'LABEL_MISMATCH'),
                (lambda p: p.update(mode='REAL'), 'LABEL_MISMATCH'),
                (lambda p: p.update(binding='BOUND'), 'LABEL_MISMATCH'),
                (lambda p: p.update(semantic_conformance=True), 'CONFORMANCE_CLAIM_REFUSED'),
                (lambda p: p.update(funds_executed=True), 'FUNDS_EXECUTED'),
                (lambda p: p.update(extra=1), 'ENVELOPE_INVALID'),
                (lambda p: p.pop('result'), 'ENVELOPE_INVALID')):
            payload = copy.deepcopy(envelope)
            mutate(payload)
            with self.subTest(code=code), self.assertRaises(ObservationProtocolError) as caught:
                observation_http._validated_result(observation_http._honest(payload))
            self.assertEqual(caught.exception.code, code)
        for mutate, code in (
                (lambda r: r.update(label='REAL'), 'LABEL_MISMATCH'),
                (lambda r: r.update(funds_executed=True), 'FUNDS_EXECUTED'),
                (lambda r: r.update(applied=True), 'EFFECTS_CLAIMED'),
                (lambda r: r.update(semantic_conformance=True), 'CONFORMANCE_CLAIM_REFUSED'),
                (lambda r: r.update(binding_status='BOUND'), 'LABEL_MISMATCH'),
                (lambda r: r.update(identity_profile='KERNEL'), 'IDENTITY_MISMATCH'),
                (lambda r: r.update(applied_effects=[{'label': 'SIMULATED', 'applied': False,
                                                    'funds_executed': False}]), 'EFFECTS_CLAIMED'),
                (lambda r: r['event_items'][0].update(label='REAL'), 'LABEL_MISMATCH'),
                (lambda r: r['deliveries'][0].update(applied=True), 'EFFECTS_CLAIMED'),
                (lambda r: r.update(event_items={}), 'ENVELOPE_INVALID')):
            payload = copy.deepcopy(envelope)
            mutate(payload['result'])
            with self.subTest(code=code), self.assertRaises(ObservationProtocolError) as caught:
                observation_http._validated_result(observation_http._honest(payload))
            self.assertEqual(caught.exception.code, code)

    def test_request_shape_is_checked_server_side(self):
        fake = fake_observation.start()
        try:
            valid = {'facts': [BASE_FACT], 'bindings': BASE_BINDINGS}
            extra = {**valid, 'note': 'nope'}
            status, body = _raw('POST', fake.url + '/v1/fold', extra)
            self.assertEqual(status, 400)
            self.assertEqual(body['error'], 'ENVELOPE_INVALID')
            self.assertEqual(body['label'], 'LOCAL_FAKE_OBSERVATION')
            self.assertIs(body['semantic_conformance'], False)
            missing = {'facts': [BASE_FACT]}
            status, body = _raw('POST', fake.url + '/v1/fold', missing)
            self.assertEqual(status, 400)
            self.assertEqual(body['error'], 'ENVELOPE_INVALID')
            self.assertEqual(fake.posts, 0)
            status, body = _raw('GET', fake.url + '/v1/counters')
            self.assertEqual(status, 200)
            self.assertEqual(body['posts'], 0)
            self.assertEqual(body['binding'], 'NOT_BOUND')
        finally:
            fake.close()

    def test_seams_keep_observation_port_not_bound(self):
        text = SEAMS.read_text(encoding='utf-8')
        row = next(line for line in text.splitlines() if line.startswith('| ObservationPort |'))
        cells = [cell.strip() for cell in row.strip().strip('|').split('|')]
        self.assertEqual(cells[4], 'NOT_BOUND')
        self.assertEqual(cells[5], 'NONE')
        self.assertIn('LocalFakeObservation', cells[1])
        self.assertIn('LOCAL_FAKE_OBSERVATION', cells[1])
        integration = (ROOT / 'docs' / 'INTEGRATION.md').read_text(encoding='utf-8')
        self.assertIn('LOCAL_FAKE_OBSERVATION', integration)
        self.assertIn('not SEMANTIC_CONFORMANCE', integration)
        for relative in ('capital/observation_http.py', 'scripts/fake_observation.py'):
            source = (ROOT / relative).read_text(encoding='utf-8')
            self.assertIn('LOCAL_FAKE_OBSERVATION', source)
            self.assertIn('NOT_BOUND', source)
            for line in source.splitlines():
                if 'SEMANTIC_CONFORMANCE' in line:
                    self.assertIn('not ', line.lower(), line)


if __name__ == '__main__':
    unittest.main()
