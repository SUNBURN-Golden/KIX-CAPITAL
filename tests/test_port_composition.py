"""Local CLAIM_CONFORMANCE: LOCAL_FAKE_IDP -> facade -> LOCAL_FAKE_GATE.

All inputs are SIMULATED or READ_ONLY_FIXTURE. Identity, authentication and
producer adoption remain NOT_BOUND; this is not SEMANTIC_CONFORMANCE.
Only repository-local fixtures are needed, with no upstream checkout.
"""
import copy
from contextlib import contextmanager, ExitStack
from http.client import HTTPConnection
import json
import tempfile
import threading
import unittest
from unittest.mock import patch

from capital.auth import PROVENANCE, ROLES
from capital.compat_preflight import canonical_bytes
from capital.gate_producer import (
    GateHttpProducer, PreflightRejected, load_fake_gate, make_preflighted_fake_producer,
)
from capital.idp_fake import FakeIdpAuthorizer, mint
from capital.producer import PinnedFsmProducer
from capital.server import make_server
from scripts.compat_preflight import CORPUS, MANIFEST
from scripts import gate_faults
# Import helpers only: importing TestCase classes duplicates discovery.
from test_compat_preflight import BundleCopy
from test_fake_idp import NOW, good_claims, good_header, sign
from test_producer_port import VECTORS


class Composition:
    """HTTP requests have bounded timeouts; the context owns both servers."""

    def __init__(self, server, producer):
        self.server, self.producer = server, producer
        self.service = server.service
        status, state = self.call('GET', '/api/state')
        if status != 200:
            raise AssertionError(state)
        self.bootstrap = state['local_token']
        self.instance = state['instance_id']
        self.token = self.bootstrap

    def call(self, method, path, body=None, *, token=None, extra=None):
        headers = dict(extra or {})
        if token is not None:
            headers['X-Capital-Token'] = token
        payload = None
        if body is not None:
            payload = json.dumps(body).encode('ascii')
            headers['Content-Type'] = 'application/json'
        client = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            client.request(method, path, body=payload, headers=headers)
            response = client.getresponse()
            return response.status, json.loads(response.read())
        finally:
            client.close()

    def session(self, role, bearer=None):
        return self.call('POST', '/api/session', {'role': role}, token=self.bootstrap,
                         extra={'Authorization': 'Bearer ' + (
                             mint(role, now=NOW) if bearer is None else bearer)})

    def command(self, key, op='offer', advance='sim-a', args=None):
        return {'instance_id': self.instance, 'operation_id': key, 'op': op,
                'advance_id': advance, 'args': {} if args is None else args}

    def submit(self, body, **kwargs):
        return self.call('POST', '/api/commands', body,
                         token=kwargs.pop('token', self.token), **kwargs)

    def lookup(self, key, token=None):
        return self.call('GET', f'/api/operations/{key}?instance_id={self.instance}',
                         token=self.token if token is None else token)

    def business(self):
        """Exclude observability counters; include both books and saved state."""
        return copy.deepcopy((self.producer.canonical_state(), self.producer.export_journal(),
                              self.service.receipts, self.service.case_fixtures,
                              self.service.overlay_entries, self.service.storage.load()))


@contextmanager
def composed(case=None):
    with ExitStack() as cleanup:
        producer = make_preflighted_fake_producer(
            root=CORPUS / 'bundle', manifest_path=MANIFEST,
            expected_path=CORPUS / 'expected.json')
        cleanup.callback(producer.close)  # also covers facade setup failures
        if case is not None:
            producer.timeout = float(case.get('producer_timeout', 5.0))
            producer.gate.fault_delay = float(case.get('fault_delay', 1.5))
        authorizer = FakeIdpAuthorizer(clock=lambda: NOW)
        server = make_server(0, authorizer=authorizer, producer=producer)
        cleanup.callback(server.server_close)
        worker = threading.Thread(target=server.serve_forever, name='composition-facade')
        worker.start()

        def stop():
            server.shutdown()
            worker.join(timeout=3)
            if worker.is_alive():
                raise AssertionError('composition facade did not stop')
        cleanup.callback(stop)
        yield Composition(server, producer)


class PortCompositionTests(unittest.TestCase):
    def bind(self, env, role='organizer'):
        status, session = env.session(role)
        self.assertEqual(status, 200, session)
        self.assertEqual(session['role'], role)
        self.assertEqual(session['mode'], 'LOCAL_FAKE_IDP')
        self.assertEqual(session['role_provenance'], PROVENANCE)
        for key in ('identity', 'authentication', 'idp', 'kyc', 'agent_grant', 'action_permit'):
            self.assertEqual(session[key], 'NOT_BOUND')
        return session['local_token']

    def accepted(self, env, body):
        status, receipt = env.submit(body)
        self.assertEqual(status, 200, receipt)
        self.assertEqual(receipt['outcome'], 'ACCEPTED', receipt)
        self.assertEqual(receipt['role'], 'organizer')
        self.assertEqual(receipt['role_provenance'], PROVENANCE)
        self.assertIs(receipt['funds_executed'], False)
        self.assertIs(receipt['economic_finality_claimed'], False)
        self.assertIs(receipt['transport_duplicate'], False)
        key = body['operation_id']
        self.assertEqual(env.producer.post_count(key), 1)
        self.assertEqual(env.lookup(key), (200, receipt))
        upstream = env.producer.lookup(key)
        self.assertEqual(upstream['result'], receipt['result'])
        self.assertEqual(upstream['label'], 'LOCAL_FAKE_GATE')
        self.assertEqual(upstream['mode'], 'SIMULATED')
        self.assertEqual(upstream['binding'], 'NOT_BOUND')
        for flag in ('semantic_conformance', 'funds_executed', 'actor_is_authentication'):
            self.assertIs(upstream[flag], False)
        request = env.producer.gate.last_request
        self.assertEqual(set(request), {'operationId', 'actor', 'action', 'body'})
        self.assertEqual(request['operationId'], key)
        self.assertEqual(request['body']['operation_id'], key)
        self.assertEqual(request['action'], body['op'])
        self.assertEqual(request['actor'], 'SIMULATED')
        self.assertEqual(request['body']['args'], body['args'])
        self.assertEqual(request['body']['advance_id'], body['advance_id'])
        self.assertEqual(request['body']['bound_settlement_id'],
                         env.service.case_fixtures[body['advance_id']]
                         if body['op'] == 'bind_settlement' else None)
        return receipt

    def lifecycle(self, env, steps=None):
        steps = dict(VECTORS)['accept-lifecycle'] if steps is None else steps
        receipts = []
        for index, step in enumerate(steps):
            receipt = self.accepted(env, env.command(
                f'composition-{index}', step['op'], step['advance_id'], step['args']))
            if 'phase' in step:
                self.assertEqual(receipt['result']['credit']['phase'], step['phase'])
            if 'gate' in step:
                self.assertEqual(receipt['result']['credit']['settlement_gate'], step['gate'])
            if 'matched' in step:
                self.assertIs(receipt['result']['matched'], step['matched'])
            receipts.append(receipt)
        return receipts

    def test_preflighted_session_lifecycle_and_authorized_reads(self):
        with composed() as env:
            self.assertIsInstance(env.producer, GateHttpProducer)
            report = env.producer.preflight_report.as_dict()
            for key, value in (('byte_agreement', 'MATCHED'), ('profile_kind', 'BOOTSTRAP'),
                               ('semantic_consumption', 'HOLD'), ('adoption', 'NOT_BOUND')):
                self.assertEqual(report[key], value)
            self.assertIs(report['semantic_conformance'], False)
            env.token = self.bind(env)
            receipts = self.lifecycle(env)
            before = env.business()
            tokens = {'organizer': env.token}
            tokens.update((role, self.bind(env, role)) for role in ROLES if role != 'organizer')
            catalogs = []
            for role, token in tokens.items():
                for path in ('/api/state', '/api/permissions', '/api/evidence',
                             f'/api/operations/composition-0?instance_id={env.instance}'):
                    with self.subTest(role=role, path=path):
                        status, body = env.call('GET', path, token=token)
                        denied = role == 'agent' or (role == 'observer' and path == '/api/evidence')
                        if denied:
                            self.assertEqual((status, body['error']), (403, 'ROLE_FORBIDDEN'))
                            continue
                        self.assertEqual(status, 200, body)
                        if path == '/api/state':
                            self.assertEqual(body['auth']['mode'], 'LOCAL_FAKE_IDP')
                            self.assertEqual(body['auth']['role'], role)
                        elif path == '/api/permissions':
                            catalogs.append(body)
                            self.assertEqual(body['label'], 'SIMULATED')
                            self.assertEqual(body['identity'], 'NOT_BOUND')
                            self.assertEqual(body['authentication'], 'NOT_BOUND')
                            self.assertNotIn('local_token', json.dumps(body))
                            for secret in (*tokens.values(), *(mint(r, now=NOW) for r in ROLES)):
                                self.assertNotIn(secret, json.dumps(body))
                        elif path == '/api/evidence':
                            self.assertEqual(body['mode'], 'READ_ONLY_FIXTURE')
                        else:
                            self.assertEqual(body, receipts[0])
            self.assertEqual(len(catalogs), 3)
            self.assertTrue(all(body == catalogs[0] for body in catalogs))
            self.assertEqual(env.business(), before)
            for index in range(len(receipts)):
                self.assertEqual(env.producer.post_count(f'composition-{index}'), 1)

    def test_invalid_sessions_and_denied_commands_never_reach_producer(self):
        with composed() as env:
            before = env.business()
            bad = (
                (mint('auditor', now=NOW - 60, ttl=60), 401, 'IDP_TOKEN_INVALID', 'EXPIRED'),
                (sign(good_header(), good_claims(aud='other')), 401, 'IDP_TOKEN_INVALID', 'AUDIENCE'),
                (mint('observer', now=NOW), 403, 'ROLE_MISMATCH', None),
            )
            with patch.object(env.producer, 'apply', wraps=env.producer.apply) as apply:
                for bearer, expected_status, error, reason in bad:
                    with self.subTest(error=error, reason=reason):
                        status, body = env.session('auditor', bearer)
                        self.assertEqual((status, body['error']), (expected_status, error))
                        if reason:
                            self.assertEqual(body['reason'], reason)
                        self.assertNotIn('local_token', body)
                        self.assertIsNone(env.server.authorizer.token_for('auditor'))
                        self.assertIsNone(env.server.authorizer.token_for('observer'))
                        self.assertEqual(env.business(), before)
                organizer = self.bind(env)
                auditor = self.bind(env, 'auditor')
                command = env.command('denied-offer', args={'fixture_id': 'sim-committed', 'amount': 60000})
                for token, extra, error in (
                    (organizer, {'X-Capital-Role': 'auditor'}, 'ROLE_MISMATCH'),
                    (auditor, {}, 'ROLE_FORBIDDEN'),
                ):
                    status, body = env.submit(command, token=token, extra=extra)
                    self.assertEqual((status, body['error']), (403, error))
                    self.assertEqual(env.business(), before)
                apply.assert_not_called()
            self.assertEqual(env.producer.post_count('denied-offer'), 0)
            self.assertEqual(env.producer.gate.post_counts, {})

    def test_preflight_mismatch_prevents_gate_construction(self):
        for drift in ('expected-tuple', 'referenced-bytes'):
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as tmp:
                bundle = BundleCopy(tmp)
                if drift == 'expected-tuple':
                    expected = json.loads(bundle.expected_path.read_bytes())
                    expected['tuple']['producer']['source_tree'] = '0' * 40
                    bundle.expected_path.write_bytes(canonical_bytes(expected))
                else:
                    (bundle.root / bundle.manifest['sdk_output']['path']).write_bytes(b'drift')
                with patch('capital.gate_producer.GateHttpProducer') as constructor, \
                        patch.object(load_fake_gate(), 'start') as start:
                    with self.assertRaises(PreflightRejected) as caught:
                        make_preflighted_fake_producer(root=bundle.root, manifest_path=MANIFEST,
                                                      expected_path=bundle.expected_path)
                    self.assertEqual(caught.exception.code, 'COMPAT_PREFLIGHT_MISMATCH')
                    constructor.assert_not_called()
                    start.assert_not_called()

    def test_hostile_reply_corpus_through_bound_session_and_preflight(self):
        for case in gate_faults.load_corpus()['cases']:
            with self.subTest(case=case['id']), composed(case) as env:
                env.token = self.bind(env)
                originals = {}
                for step in case['steps']:
                    key = step['operation_id']
                    before_step = env.business()
                    if step['fault'] is not None:
                        env.producer.gate.arm(key, step['fault'])
                    if step['post'] == 'gate':
                        # Intentional direct POST for conflict coverage, not a retry.
                        status, body = gate_faults._http(
                            'POST', env.producer.base_url + '/v1/commands', gate_faults._gate_envelope(step))
                    else:
                        status, body = env.submit(gate_faults._facade_command(env.instance, step))
                    lookup_status, lookup = env.lookup(key)
                    self.assertEqual(lookup_status, 200, lookup)
                    upstream = env.producer.lookup(key)
                    observed = {
                        'http': status, 'outcome': body.get('outcome'), 'error': body.get('error'),
                        'retry_authorized': body.get('retry_authorized'),
                        'transport_duplicate': body.get('transport_duplicate'),
                        'post_count': env.producer.post_count(key), 'lookup': lookup.get('outcome'),
                        'upstream_receipt': None if upstream is None else upstream['outcome'],
                        'phase': gate_faults._observe_phase(env.producer, step['advance_id']),
                    }
                    self.assertEqual(observed, step['expect'])
                    if status == 409:
                        self.assertEqual(env.business(), before_step)
                    if lookup['outcome'] == 'UNKNOWN':
                        self.assertEqual(lookup['label'], 'LOCAL_FAKE_GATE')
                        self.assertIs(lookup['retry_authorized'], False)
                    if body.get('outcome') == 'UNKNOWN':
                        self.assertEqual(body, lookup)
                    if upstream is not None:
                        self.assertEqual(upstream['label'], 'LOCAL_FAKE_GATE')
                        self.assertEqual(upstream['binding'], 'NOT_BOUND')
                        self.assertIs(upstream['semantic_conformance'], False)
                        self.assertIs(upstream['funds_executed'], False)
                        originals.setdefault(key, (lookup, upstream))
                        self.assertEqual((lookup, upstream), originals[key])
                    # Reads must not reconcile UNKNOWN receipts or resend anything.
                    before = env.business()
                    for _ in range(2):
                        self.assertEqual(env.lookup(key), (lookup_status, lookup))
                        self.assertEqual(env.producer.lookup(key), upstream)
                    self.assertEqual(env.producer.post_count(key), step['expect']['post_count'])
                    self.assertEqual(env.business(), before)
                self.assertEqual(len(env.producer.export_journal()), case['journal_length'])

    def test_accepted_and_domain_rejected_replays_keep_first_result_after_state_changes(self):
        with composed() as env:
            env.token = self.bind(env)
            offer = env.command('first-offer', args={'fixture_id': 'sim-committed', 'amount': 60000})
            accepted = self.accepted(env, offer)
            draw = env.command('first-draw', 'draw')
            status, rejected = env.submit(draw)
            self.assertEqual((status, rejected['outcome'], rejected['error']),
                             (200, 'REJECTED', 'ILLEGAL_TRANSITION'))
            self.accepted(env, env.command('later-approve', 'approve'))
            self.accepted(env, env.command('later-bind', 'bind_settlement'))
            # A fresh draw would now succeed. The rejected operation must still
            # return its first rejection, without reaching the gate again.
            before = env.business()
            for command, first in ((offer, accepted), (draw, rejected)):
                key = command['operation_id']
                upstream = env.producer.lookup(key)
                status, replay = env.submit(command)
                self.assertEqual((status, replay), (200, {**first, 'transport_duplicate': True}))
                self.assertEqual(env.lookup(key), (200, first))
                changed = {**command, 'op': 'approve' if command['op'] == 'draw' else 'offer',
                           'args': {} if command['op'] == 'draw' else {**command['args'], 'amount': 1}}
                status, conflict = env.submit(changed)
                self.assertEqual((status, conflict['error']), (409, 'IDEMPOTENCY_CONFLICT'))
                self.assertEqual(env.producer.lookup(key), upstream)
                self.assertEqual(env.producer.post_count(key), 1)
                self.assertEqual(env.business(), before)
            drawn = self.accepted(env, env.command('later-draw', 'draw'))
            self.assertEqual(drawn['result']['credit']['phase'], 'DRAWN')

    def test_unsupported_operations_refuse_without_in_process_fallback(self):
        # Scope patches to the Capital service: the fake gate legitimately uses
        # the pinned producer internally. No new financial values are chosen.
        with patch('capital.service.PinnedFsmProducer', wraps=PinnedFsmProducer) as fallback:
            with composed() as env:
                env.token = self.bind(env)
                self.lifecycle(env, dict(VECTORS)['accept-lifecycle'][:4])
                status, tick = env.call('POST', '/api/overlay/commands', {
                    'instance_id': env.instance, 'operation_id': 'composition-clock',
                    'op': 'advance_day', 'from_sim_day': 0, 'to_sim_day': 1,
                    'reason': 'SIMULATED composition fixture'}, token=env.token)
                self.assertEqual((status, tick['outcome']), (200, 'APPLIED'))
                self.assertIsNotNone(env.service.overlay_state()['terms_binding'])
                before = env.business()
                with patch.object(env.producer, 'apply', wraps=env.producer.apply) as apply:
                    status, refusal = env.call('POST', '/api/overlay/commands', {
                        'instance_id': env.instance, 'operation_id': 'composition-overlay-repay',
                        'op': 'post_repayment', 'advance_ref': 'sim-a', 'at_sim_day': 1,
                        'amount_krw': 60000}, token=env.token)
                    self.assertEqual((status, refusal['error']), (409, 'REPAYMENT_PRODUCER_UNSUPPORTED'))
                    status, facts = env.call('GET', '/api/export/facts?instance_id=' + env.instance,
                                             token=env.token)
                    self.assertEqual((status, facts['error']), (503, 'COHERENT_SNAPSHOT_UNSUPPORTED'))
                    status, snapshot = env.call('GET', '/api/portfolio/snapshot?instance_id=' + env.instance,
                                                token=env.token)
                    self.assertEqual(status, 200, snapshot)
                    self.assertEqual(snapshot['status'], 'INCOMPLETE')
                    self.assertIs(snapshot['complete'], False)
                    self.assertEqual(snapshot['completeness']['reasons'], ['GATE_FAKE_UNSUPPORTED'])
                    apply.assert_not_called()
                self.assertIs(env.service.producer, env.producer)
                self.assertEqual(env.business(), before)
                self.assertEqual(env.producer.gate.post_counts,
                                 {f'composition-{i}': 1 for i in range(4)})
            fallback.assert_not_called()


if __name__ == '__main__':
    unittest.main()
