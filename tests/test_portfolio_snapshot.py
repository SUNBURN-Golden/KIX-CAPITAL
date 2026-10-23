"""SIMULATED local cuts: parity, isolation, deterministic hashes and concurrency."""
import copy
import hashlib
import io
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

from capital import overlay, portfolio_snapshot as snapshot
from capital.gate_producer import GateHttpProducer
from capital.producer import FixtureViews, PinnedFsmProducer
from capital.server import make_server
from capital.service import ApiError, CapitalService
from capital.store import FileWorkspace, InMemoryStorage, WorkspaceError, envelope
from capital.terms import DecisionNoteTermsPolicy
from tests.facade_schema import SchemaError, load_contract, validate
from tests.test_overlay import draw_book, run, seed, tick


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def read(service):
    return service.portfolio_snapshot(service.instance_id)


def without_envelope(body):
    return {k: v for k, v in body.items() if k not in (
        'instance_id', 'observed_state_digest', 'funds_executed', 'workspace_mutated', 'write_authorized')}


class SnapshotTests(unittest.TestCase):
    def assert_schema(self, body):
        doc = load_contract()
        validate(body, {'$ref': '#/definitions/portfolio_snapshot'}, doc)

    def test_components_match_existing_reads_and_date_assumptions_remain_visible(self):
        service = CapitalService()
        # Deliberately draw out of lexical order; existing reads sort subjects.
        draw_book(service, 'sim-z', fixture='demo-alpha-arena', amount=10000, prefix='z')
        draw_book(service)
        tick(service, 'late-clock', 0, 12)
        draw_book(service, 'sim-late', fixture='demo-alpha-arena', amount=15000, prefix='late')
        run(service, 'offer', 'sim-preview', 'preview-offer', fixture_id='sim-committed', amount=1000)
        run(service, 'approve', 'sim-preview', 'preview-approve')
        body = read(service)
        self.assertTrue(body['complete'], body['completeness'])
        for name, existing in (
            ('terms_rollup', service.terms_portfolio(service.instance_id, as_of_day=12)),
            ('risk', service.risk()), ('covenants', service.covenants()),
            ('forecast', service.forecast(service.instance_id))):
            self.assertEqual(body[name], without_envelope(existing), name)
        late_terms = next(r for r in body['terms_rollup']['rows'] if r['advance_id'] == 'sim-late')
        late_forecast = next(r for r in body['forecast']['advances'] if r['advance_id'] == 'sim-late')
        self.assertEqual((late_terms['draw_day'], late_terms['draw_day_source']), (0, 'DEFAULT'))
        self.assertEqual(late_forecast['draw_day'], 12)
        self.assertEqual(late_forecast['maturity_day'] - late_terms['maturity_day'], 12)
        self.assertEqual(late_forecast['legs'][0]['status'], 'EXPECTED_DAY_NOT_PROVIDED')
        self.assertEqual(body['authenticated_source_cut'], 'NOT_BOUND')
        self.assert_schema(body)

    def test_seeded_demo_sections_match_existing_calculations(self):
        service = seed.build_service()
        body = read(service)
        self.assertTrue(body['complete'], body['completeness'])
        for name, existing in (
            ('terms_rollup', service.terms_portfolio(service.instance_id, as_of_day=body['cut']['sim_day'])),
            ('risk', service.risk()), ('covenants', service.covenants()),
            ('forecast', service.forecast(service.instance_id))):
            self.assertEqual(body[name], without_envelope(existing), name)
        self.assert_schema(body)

    def test_cut_digests_and_snapshot_digest_are_independently_recomputed(self):
        service = CapitalService()
        draw_book(service)
        tick(service, 'clock', 0, 8)
        body = read(service)
        cut = body['cut']
        self.assertEqual(cut['state_digest'], hashlib.sha256(service.machine.canonical_state().encode()).hexdigest())
        self.assertEqual(cut['fixtures_digest'], sha(service.fixtures.rows))
        self.assertEqual(cut['overlay_state_digest'], overlay.state_digest(overlay.fold(service.overlay_entries)))
        self.assertEqual(cut['sim_day'], 8)
        policy = {'items': service.terms.items, 'version': service.terms.version,
                  'top': service.terms.top, 'reason': service.terms.reason, 'bounds': service.overlay_bounds,
                  'assumptions': body['assumptions']}
        self.assertEqual(cut['policy_inputs_digest'], sha({'version': 1, **policy}))
        fixtures = {'rows': service.fixtures.rows, 'profiles': service.fixtures.profiles,
                    'beneficiaries': service.fixtures.beneficiaries, 'projection_ids': sorted(service.fixtures.projection_ids)}
        gates = {'sim-a': service.receipts['a-draw']['receipt']['result']['credit']['settlement_gate']}
        self.assertEqual(cut['inputs_digest'], sha({
            'version': 1, 'cut': {k: v for k, v in cut.items() if k != 'inputs_digest'},
            'fixtures': fixtures, 'case_fixtures': service.case_fixtures,
            'draw_gates': gates, 'overlay_entries': service.overlay_entries,
            'policy_items_json': json.dumps(service.terms.items, separators=(',', ':'), ensure_ascii=True)}))
        self.assertEqual(body['snapshot_digest'], sha({
            'format': body['format'], 'cut': cut, 'assumptions': body['assumptions'],
            'completeness': body['completeness'], **{k: body[k] for k in snapshot.SECTIONS}}))

    def test_repeated_reads_preserve_workspace_bytes_and_all_business_state(self):
        with tempfile.TemporaryDirectory() as tmp, FileWorkspace.open(tmp) as store:
            service = CapitalService(storage=store)
            draw_book(service)
            tick(service, 'clock', 0, 8)
            frozen = (service._frozen(), copy.deepcopy(service.case_fixtures), copy.deepcopy(service.fixtures.__dict__),
                      copy.deepcopy(service.terms.__dict__), copy.deepcopy(service.overlay_bounds))
            files = {p.name: p.read_bytes() for p in Path(tmp).iterdir()}
            with patch.object(store, 'save', side_effect=AssertionError('snapshot must never save')):
                bodies = [read(service) for _ in range(4)]
            self.assertTrue(all(body == bodies[0] for body in bodies))
            self.assertEqual(files, {p.name: p.read_bytes() for p in Path(tmp).iterdir()})
            self.assertEqual(frozen, (service._frozen(), service.case_fixtures, service.fixtures.__dict__,
                                      service.terms.__dict__, service.overlay_bounds))
            # A new session restores identical input facts, with a different instance id.
            other = CapitalService(storage=store)
            self.assertNotEqual(other.instance_id, service.instance_id)
            self.assertEqual(read(other)['snapshot_digest'], bodies[0]['snapshot_digest'])

    def test_policy_metadata_and_receipt_sessions_are_not_digest_inputs(self):
        service = CapitalService()
        draw_book(service)
        before = read(service)
        service.terms.path = Path('/tmp/unused-note-name')
        service.receipts['a-draw']['receipt']['instance_id'] = 'different-session'
        service._persist()
        self.assertEqual(read(service)['snapshot_digest'], before['snapshot_digest'])
        service.fixtures.profiles['sim-committed'] = 'different-profile'
        after = read(service)
        self.assertEqual(before['cut']['fixtures_digest'], after['cut']['fixtures_digest'])
        self.assertNotEqual(before['cut']['inputs_digest'], after['cut']['inputs_digest'])
        service.terms.items['reserve']['value']['provision_bps_of_outstanding']['T1_COMMIT_OBSERVED'] += 1
        changed = read(service)
        self.assertNotEqual(after['cut']['policy_inputs_digest'], changed['cut']['policy_inputs_digest'])

    def test_input_capture_is_detached_and_immutable(self):
        producer = PinnedFsmProducer()
        captured = producer.snapshot_inputs()
        captured['fixtures']['rows'].clear()
        self.assertTrue(producer.fixtures.rows)
        service = CapitalService()
        frozen = snapshot.FrozenInputs.capture(producer.snapshot_inputs(), {}, {}, [], service.terms, service.overlay_bounds)
        detached = frozen.detached()
        detached['policy']['items'].clear()
        self.assertTrue(frozen.detached()['policy']['items'])
        self.assertEqual(producer.snapshot_inputs()['state_digest'], producer.state_digest())

    def test_unbound_and_partial_terms_never_complete_or_fabricate_totals(self):
        for missing in (True, False):
            terms = DecisionNoteTermsPolicy('/tmp/nonexistent-kix-snapshot-note') if missing else DecisionNoteTermsPolicy()
            if not missing:
                terms.items['fees'] = {'mark': 'NOT_BOUND', 'value': None}
                terms.top = 'PARTIAL'
            service = CapitalService(terms=terms)
            body = read(service)
            self.assertFalse(body['complete'])
            self.assertIn('TERMS_NOT_BOUND', body['completeness']['reasons'])
            self.assertTrue(all(body[k] is None for k in snapshot.SECTIONS))
            self.assert_schema(body)

    def test_missing_required_terms_on_an_otherwise_bound_empty_book_are_incomplete(self):
        # The note loader can mark the supplied entries BOUND when another
        # required entry is absent entirely. An empty book must not hide that.
        for name in ('interest_rate', 'fees', 'term', 'default_loss_treatment',
                     'reserve', 'additional_margin', 'underwriting_depth'):
            service = CapitalService()
            del service.terms.items[name]
            self.assertEqual(service.terms.top, 'BOUND')
            with self.subTest(name=name):
                body = read(service)
                self.assertFalse(body['complete'])
                self.assertIn('TERMS_NOT_BOUND', body['completeness']['reasons'])
                self.assertTrue(all(body[k] is None for k in snapshot.SECTIONS))

    def test_unsupported_producers_are_rejected_without_machine_or_remote_reads(self):
        class Unsupported:
            @property
            def machine(self):
                raise AssertionError('unsupported machine was accessed')
        for producer, reason in ((Unsupported(), 'COHERENT_SNAPSHOT_UNSUPPORTED'),
                                 (GateHttpProducer.__new__(GateHttpProducer), 'GATE_FAKE_UNSUPPORTED')):
            service = CapitalService(producer=producer)
            body = read(service)
            self.assertFalse(body['complete'])
            self.assertEqual(body['completeness']['reasons'], [reason])
            self.assertTrue(all(v is None for k, v in body['cut'].items() if k != 'kind'))
            self.assert_schema(body)
        service = CapitalService()
        with patch.object(service.producer, 'snapshot_inputs', None):
            self.assertEqual(read(service)['completeness']['reasons'], ['COHERENT_SNAPSHOT_UNSUPPORTED'])

    def test_non_pinned_machine_and_non_decision_note_policy_are_unsupported(self):
        service = CapitalService(producer=PinnedFsmProducer(machine=object()))
        self.assertEqual(read(service)['completeness']['reasons'], ['COHERENT_SNAPSHOT_UNSUPPORTED'])
        service = CapitalService()
        service.terms = object()
        self.assertEqual(read(service)['completeness']['reasons'], ['FROZEN_TERMS_UNSUPPORTED'])

    def test_mutable_fixtures_are_unsupported(self):
        class Mutable(FixtureViews):
            settlement_views_mutable = True
        service = CapitalService(producer=PinnedFsmProducer(Mutable()))
        body = read(service)
        self.assertEqual(body['completeness']['reasons'], ['IMMUTABLE_FIXTURES_REQUIRED'])
        self.assertFalse(body['complete'])
        self.assert_schema(body)

    def test_storage_corruption_startup_after_startup_and_failed_save(self):
        store = InMemoryStorage()
        store._document = {'broken': True}
        self.assertIn('WORKSPACE_UNREADABLE', read(CapitalService(storage=store))['completeness']['reasons'])
        service = CapitalService()
        draw_book(service)
        service.storage._document['payload_sha256'] = '0' * 64
        body = read(service)
        self.assertIn('WORKSPACE_UNREADABLE', body['completeness']['reasons'])
        self.assertFalse(body['complete'])
        self.assert_schema(body)
        service = CapitalService()
        draw_book(service)
        with patch.object(service.storage, 'save', side_effect=WorkspaceError('WORKSPACE_WRITE_FAILED')):
            with self.assertRaises(ApiError):
                run(service, 'repay', 'sim-a', 'fail-save', amount=1000, sequence=1)
        self.assertIn('WORKSPACE_WRITE_FAILED', read(service)['completeness']['reasons'])

    def test_absent_nonempty_and_checksum_valid_disagreement_are_degraded(self):
        service = CapitalService()
        self.assertTrue(read(service)['complete'])  # unsaved empty workspace
        draw_book(service)
        document = copy.deepcopy(service.storage._document)
        service.storage._document = None
        self.assertIn('STORAGE_STATE_MISMATCH', read(service)['completeness']['reasons'])
        document['payload']['case_fixtures']['sim-a'] = 'sim-pending'
        service.storage._document = envelope(service.instance_id, document['payload'], document['overlay'])
        self.assertIn('STORAGE_STATE_MISMATCH', read(service)['completeness']['reasons'])

    def test_missing_draw_receipt_and_failed_reconciliation_never_complete(self):
        service = CapitalService()
        draw_book(service)
        del service.receipts['a-draw']['receipt']['result']['credit']['settlement_gate']
        service._persist()
        body = read(service)
        self.assertIn('DRAW_RECEIPT_GATE_MISSING', body['completeness']['reasons'])
        self.assertFalse(body['complete'])
        self.assert_schema(body)
        service = CapitalService()
        draw_book(service)
        original = snapshot.risk.build
        def mismatch(*args, **kwargs):
            body = original(*args, **kwargs)
            body['reconciliation']['matched'] = False
            return body
        with patch.object(snapshot.risk, 'build', mismatch):
            body = read(service)
        self.assertFalse(body['complete'])
        self.assertIn('RECONCILIATION_FAILED', body['completeness']['reasons'])
        self.assert_schema(body)

    def test_risk_is_computed_once_and_shared_with_covenants(self):
        service = CapitalService()
        draw_book(service)
        with patch.object(snapshot.risk, 'build', wraps=snapshot.risk.build) as risk_build, patch.object(
                snapshot.covenants, 'build', wraps=snapshot.covenants.build) as covenant_build:
            body = read(service)
        self.assertEqual(risk_build.call_count, 1)
        self.assertIs(covenant_build.call_args.args[3], body['risk'])

    def test_closed_schema_rejects_unknown_fields_and_false_completeness(self):
        service = CapitalService()
        draw_book(service)
        tick(service, 'clock', 0, 90)  # nonempty covenant breach reasons
        body = read(service)
        self.assert_schema(body)
        for path in ((), ('cut',), ('completeness',), ('assumptions',), ('terms_rollup',),
                     ('risk',), ('covenants',), ('forecast',), ('covenants', 'advances', 0),
                     ('covenants', 'advances', 0, 'reasons', 0)):
            changed = copy.deepcopy(body)
            node = changed
            for key in path:
                node = node[key]
            node['unknown'] = True
            with self.subTest(path=path), self.assertRaises(SchemaError):
                self.assert_schema(changed)
        changed = copy.deepcopy(body)
        changed['completeness']['storage'] = 'DEGRADED'
        with self.assertRaises(SchemaError):
            self.assert_schema(changed)


class ObservedLock:
    """Signals an actual contention attempt before blocking on the service RLock."""
    def __init__(self, lock, target, attempted):
        self.lock, self.target, self.attempted = lock, target, attempted
    def __enter__(self):
        if threading.current_thread().name == self.target:
            self.attempted.set()
        self.lock.acquire()
        return self
    def __exit__(self, *_):
        self.lock.release()


class ConcurrentCutTests(unittest.TestCase):
    def test_reader_and_writer_orderings_for_repayment_and_overlay_clock(self):
        for operation in ('repay', 'clock'):
            for reader_first in (True, False):
                with self.subTest(operation=operation, reader_first=reader_first):
                    self.exercise(operation, reader_first)

    def exercise(self, operation, reader_first):
        service = CapitalService()
        draw_book(service)
        before = read(service)
        entered, release, attempted = threading.Event(), threading.Event(), threading.Event()
        results, errors = {}, []
        service.lock = ObservedLock(service.lock, 'writer' if reader_first else 'reader', attempted)
        def writer():
            receipt = (run(service, 'repay', 'sim-a', 'repay-one', amount=1000, sequence=1)
                       if operation == 'repay' else tick(service, 'tick-one', 0, 61))
            self.assertEqual(receipt['outcome'], 'ACCEPTED' if operation == 'repay' else 'APPLIED')
            return receipt
        def pause(call):
            def paused(*args, **kwargs):
                result = call(*args, **kwargs)
                entered.set()
                if not release.wait(5):
                    raise AssertionError('test barrier timed out')
                return result
            return paused
        def invoke(name, call):
            try:
                results[name] = call()
            except BaseException as exc:
                errors.append(exc)
        # Pause between component calculations, or before the writer persists.
        target = snapshot.risk if reader_first else service
        attribute = 'build' if reader_first else '_persist'
        threads = []
        with patch.object(target, attribute, pause(getattr(target, attribute))):
            first = threading.Thread(name='reader' if reader_first else 'writer', target=invoke,
                                     args=('reader', lambda: read(service)) if reader_first else ('writer', writer))
            second = threading.Thread(name='writer' if reader_first else 'reader', target=invoke,
                                      args=('writer', writer) if reader_first else ('reader', lambda: read(service)))
            try:
                first.start(); threads.append(first)
                self.assertTrue(entered.wait(5), 'first thread did not reach barrier')
                second.start(); threads.append(second)
                self.assertTrue(attempted.wait(5), 'contender did not attempt the service lock')
                self.assertNotIn('writer' if reader_first else 'reader', results)
            finally:
                release.set()
                for thread in threads:
                    thread.join(5)
                    self.assertFalse(thread.is_alive(), 'worker did not stop')
        self.assertEqual(errors, [])
        after = read(service)
        self.assertNotEqual(before['snapshot_digest'], after['snapshot_digest'])
        self.assertEqual(results['reader'], before if reader_first else after)
        self.assertEqual(read(service), after)


class RouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.service = cls.server.service
        for role in ('auditor', 'observer', 'agent'):
            cls.service.authorizer.bind_role(role)
        cls.worker = threading.Thread(target=cls.server.serve_forever)
        cls.worker.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.worker.join(5)
    def request(self, query='', role=None):
        headers = {} if role is None else {'X-Capital-Token': self.service.authorizer.token_for(role)}
        client = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            client.request('GET', '/api/portfolio/snapshot' + query, headers=headers)
            response = client.getresponse()
            return response.status, json.loads(response.read())
        finally:
            client.close()
    def test_roles_identity_and_strict_query(self):
        instance = self.service.instance_id
        for role in (None, 'organizer', 'auditor'):
            status, body = self.request('?instance_id=' + instance, role)
            self.assertEqual(status, 200, body)
            self.assertTrue(body['complete'])
        for role in ('observer', 'agent'):
            # Authorization must precede invalid identity/query/capability checks.
            status, body = self.request('?extra=1', role)
            self.assertEqual((status, body['error']), (403, 'ROLE_FORBIDDEN'))
        for query in ('', '?instance_id=', '?instance_id=stale'):
            status, body = self.request(query)
            self.assertEqual((status, body['error']), (409, 'SESSION_CHANGED'))
        for query in ('?instance_id=x&instance_id=y', '?instance_id=&instance_id=', '?extra=1',
                      '?instance_id=' + instance + '&sim_day=0'):
            status, body = self.request(query)
            self.assertEqual((status, body['error']), (400, 'INVALID_ARGUMENTS'))


class HandlerTests(unittest.TestCase):
    """Exercise the real HTTP handler on byte streams, without opening a socket.

    Complements the live-loopback tests; these are in-process HTTP parser and
    dispatcher checks, not a claim that a server bound successfully.
    """
    def test_authorization_query_validation_and_complete_incomplete_schemas(self):
        class CapturedServer:
            def __init__(self, address, handler):
                self.server_port = 8765
                self.handler = handler
        class ByteConnection:
            def __init__(self, request):
                self.request, self.output = request, bytearray()
            def makefile(self, *_):
                return io.BytesIO(self.request)
            def sendall(self, data):
                self.output.extend(data)
        with patch('capital.server.CapitalHTTPServer', CapturedServer):
            server = make_server(8765)
        service = server.service
        for role in ('auditor', 'observer', 'agent'):
            service.authorizer.bind_role(role)
        def request(query, role=None):
            token = '' if role is None else 'X-Capital-Token: ' + service.authorizer.token_for(role) + '\r\n'
            raw = ('GET /api/portfolio/snapshot' + query + ' HTTP/1.0\r\nHost: 127.0.0.1:8765\r\n' + token + '\r\n').encode()
            connection = ByteConnection(raw)
            server.handler(connection, ('127.0.0.1', 10000), server)
            head, body = bytes(connection.output).split(b'\r\n\r\n', 1)
            return int(head.split()[1]), json.loads(body)
        query = '?instance_id=' + service.instance_id
        for role in (None, 'organizer', 'auditor'):
            status, body = request(query, role)
            self.assertEqual(status, 200)
            self.assertTrue(body['complete'])
            doc = load_contract()
            validate(body, {'$ref': '#/definitions/portfolio_snapshot'}, doc)
        for role in ('observer', 'agent'):
            status, body = request('?extra=1', role)
            self.assertEqual((status, body['error']), (403, 'ROLE_FORBIDDEN'))
        for query in ('', '?instance_id=', '?instance_id=stale'):
            status, body = request(query)
            self.assertEqual((status, body['error']), (409, 'SESSION_CHANGED'))
        for query in ('?instance_id=x&instance_id=y', '?extra=1', '?instance_id=&instance_id='):
            status, body = request(query)
            self.assertEqual((status, body['error']), (400, 'INVALID_ARGUMENTS'))
        service.terms = DecisionNoteTermsPolicy('/tmp/nonexistent-kix-snapshot-note')
        status, body = request('?instance_id=' + service.instance_id)
        self.assertEqual(status, 200)
        self.assertFalse(body['complete'])
        validate(body, {'$ref': '#/definitions/portfolio_snapshot'}, doc)
        service.observability.close()


if __name__ == '__main__':
    unittest.main()
