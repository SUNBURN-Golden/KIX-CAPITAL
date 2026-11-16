"""READ_MODEL_QUERIES point queries: envelope, key sets, errors, auth, non-mutation."""
import copy
import importlib.util
import json
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from capital.protocol import SettlementMachine
from capital.service import ApiError, CapitalService

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / 'tests' / 'golden' / 'demo.json'
KINDS = {
    'credit_advance': 'get_credit_advance',
    'credit_claim': 'get_credit_claim',
    'settlement': 'get_settlement',
}
ENVELOPE_KEYS = {
    'read_schema_version', 'query', 'query_digest', 'fixture_mode', 'accepted_through',
    'visibility_enforced', 'visibility_matrix', 'mode', 'label', 'body',
}
RESERVED = (
    'source_cut', 'projection_watermark', 'snapshot_digest', 'observed_receipt_refs',
    'producer_manifest_digest', 'subject_scope', 'profile_revision',
)
FLAGS = (
    'funds_executed', 'license_granted', 'regulated_product', 'collateral_perfected',
    'priority_bound', 'disposal_controlled', 'revenue_assigned', 'admission_granted',
    'legal_debtor_bound', 'bank_debit_observed', 'external_pledge_complete', 'durable',
    'repayment_observed', 'interest_defined',
)


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed = _load('seed_demo_read', 'seed_demo.py')


def run(service, op, advance, args=None):
    receipt = service.execute({
        'instance_id': service.instance_id,
        'operation_id': f'rd-{advance}-{op.replace("_", "")}-{len(service.receipts)}',
        'op': op, 'advance_id': advance, 'args': {} if args is None else args,
    })
    assert receipt['outcome'] == 'ACCEPTED', receipt
    return receipt


def drawn(service, advance='sim-rd-one', fixture='sim-committed', amount=1000):
    run(service, 'offer', advance, {'fixture_id': fixture, 'amount': amount})
    run(service, 'approve', advance)
    run(service, 'bind_settlement', advance)
    run(service, 'draw', advance)
    return advance


def error(service, kind, ident):
    try:
        service.read_query(kind, ident)
    except ApiError as exc:
        return exc.code, exc.status
    return None


def frozen(service):
    return {
        'state_digest': service.machine.state_digest(),
        'canonical_state': service.machine.canonical_state(),
        'journal': service.machine.export_journal(),
        'receipts': copy.deepcopy(service.receipts),
        'operation_count': len(service.receipts),
        'overlay': copy.deepcopy(service.overlay_entries),
        'fixture_rows': copy.deepcopy(service.fixtures.rows),
    }


class EnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.service = CapitalService()
        self.advance = drawn(self.service)

    def read(self, kind, ident):
        return self.service.read_query(kind, ident)

    def test_envelope_constants_and_unmodified_bodies(self):
        machine, fixtures = self.service.machine, self.service.fixtures
        expected = {
            'credit_advance': (self.advance, machine.view(self.advance)),
            'credit_claim': ('sim-committed', machine.view_claim('sim-committed')),
            'settlement': ('sim-committed', fixtures.view('sim-committed')),
        }
        for kind, (ident, body) in expected.items():
            with self.subTest(kind=kind):
                result = self.read(kind, ident)
                self.assertEqual(set(result), ENVELOPE_KEYS)
                self.assertEqual(result['read_schema_version'], '0.1')
                self.assertEqual(result['query'], KINDS[kind])
                self.assertEqual(result['fixture_mode'], 'REFERENCE_IN_MEMORY')
                self.assertIs(result['visibility_enforced'], False)
                self.assertEqual(result['visibility_matrix'], 'UNDETERMINED')
                self.assertEqual(result['mode'], 'READ_MODEL_REHEARSAL')
                self.assertIn('SIMULATED', result['label'])
                self.assertEqual(result['body'], body)
                self.assertRegex(result['query_digest'], r'\A[0-9a-f]{64}\Z')
                for name in RESERVED + ('logical_time_ms',):
                    self.assertNotIn(name, result)
                    self.assertNotIn(name, result['body'])

    def test_query_digest_binds_query_and_id_only(self):
        one = self.read('credit_advance', self.advance)['query_digest']
        run(self.service, 'repay', self.advance, {'amount': 100, 'sequence': 1})
        self.assertEqual(self.read('credit_advance', self.advance)['query_digest'], one)
        self.assertNotEqual(self.read('credit_claim', 'sim-committed')['query_digest'],
                            self.read('settlement', 'sim-committed')['query_digest'])
        self.assertNotEqual(self.read('settlement', 'sim-committed')['query_digest'],
                            self.read('settlement', 'sim-pending')['query_digest'])

    def test_accepted_through_is_the_journal_length(self):
        service = CapitalService()
        self.assertEqual(service.read_query('settlement', 'sim-committed')['accepted_through'], 4)
        run(service, 'offer', 'sim-rd-two', {'fixture_id': 'sim-committed', 'amount': 1000})
        self.assertEqual(service.read_query('credit_advance', 'sim-rd-two')['accepted_through'], 1)
        run(service, 'approve', 'sim-rd-two')
        run(service, 'bind_settlement', 'sim-rd-two')
        run(service, 'draw', 'sim-rd-two')
        for kind, ident in (('credit_advance', 'sim-rd-two'), ('credit_claim', 'sim-committed')):
            self.assertEqual(service.read_query(kind, ident)['accepted_through'], 4)
            self.assertEqual(service.read_query(kind, ident)['accepted_through'],
                             len(service.machine.export_journal()))
        run(service, 'repay', 'sim-rd-two', {'amount': 1000, 'sequence': 1})
        self.assertEqual(service.read_query('credit_advance', 'sim-rd-two')['accepted_through'], 5)
        self.assertEqual(service.read_query('credit_claim', 'sim-committed')['accepted_through'], 5)

    def test_settlement_accepted_through_matches_a_replayed_book_for_every_fixture(self):
        service = CapitalService()
        self.assertEqual(len(service.fixtures.rows), 13)
        for fixture_id, row in sorted(service.fixtures.rows.items()):
            with self.subTest(fixture=fixture_id):
                result = service.read_query('settlement', fixture_id)
                self.assertEqual(result['body'], row)
                # The fixture book holds one settlement, so the book journal length is its entry count.
                self.assertEqual(result['accepted_through'], row['accepted_entries'])
                # initiate, authorize, capture, then commit and one refund when the fixture has them.
                replayed = 3 + (row['phase'] == 'COMMITTED') + (row['claim']['refund_face'] > 0)
                self.assertEqual(result['accepted_through'], replayed)


class KeySetTests(unittest.TestCase):
    def test_key_counts_and_always_false_flags(self):
        service = CapitalService()
        advance = drawn(service)
        advance_body = service.read_query('credit_advance', advance)['body']
        claim_body = service.read_query('credit_claim', 'sim-committed')['body']
        settlement_body = service.read_query('settlement', 'sim-committed')['body']
        self.assertEqual((len(settlement_body), len(advance_body), len(claim_body)), (25, 51, 24))
        for name in FLAGS:
            self.assertIs(advance_body[name], False, name)
            self.assertIs(claim_body[name], False, name)
        self.assertNotIn('lifecycle_authority', claim_body)
        self.assertEqual(set(claim_body) - set(advance_body), set())
        for name in ('funds_executed', 'bank_debit_observed', 'legal_debtor_bound',
                     'admission_granted', 'durable', 'provider_authorization_executed'):
            self.assertIs(settlement_body[name], False, name)
        self.assertEqual(settlement_body['accepted_entries'], 4)

    def test_claim_is_unknown_until_a_draw_notes_it(self):
        service = CapitalService()
        self.assertEqual(error(service, 'credit_claim', 'sim-committed'), ('UNKNOWN_CLAIM', 404))
        run(service, 'offer', 'sim-rd-early', {'fixture_id': 'sim-committed', 'amount': 1000})
        self.assertIs(service.read_query('credit_advance', 'sim-rd-early')['body']['snapshot_frozen'], False)
        self.assertEqual(error(service, 'credit_claim', 'sim-committed'), ('UNKNOWN_CLAIM', 404))
        drawn(service)
        self.assertIs(service.read_query('credit_claim', 'sim-committed')['body']['snapshot_frozen'], True)


class ErrorTests(unittest.TestCase):
    def test_errors_are_exactly_the_four_codes(self):
        service = CapitalService()
        drawn(service)
        unknown = {'credit_advance': 'UNKNOWN_ADVANCE', 'credit_claim': 'UNKNOWN_CLAIM',
                   'settlement': 'UNKNOWN_SETTLEMENT'}
        seen = set()
        for kind, code in unknown.items():
            self.assertEqual(error(service, kind, 'sim-missing'), (code, 404))
            for ident in ('', 'x' * 101, ' sim-missing', 'sim-missing ', 7, None):
                got = error(service, kind, ident)
                self.assertEqual(got, ('INVALID_ID', 400), (kind, ident))
            seen.update((code, 'INVALID_ID'))
        self.assertEqual(seen, {'UNKNOWN_ADVANCE', 'UNKNOWN_CLAIM', 'UNKNOWN_SETTLEMENT', 'INVALID_ID'})
        # A malformed settlement id is INVALID_ID, which the fixture reader alone would call unknown.
        with self.assertRaises(Exception) as caught:
            SettlementMachine().view(' pad')
        self.assertEqual(caught.exception.code, 'INVALID_ID')
        self.assertEqual(error(service, 'settlement', 'x' * 100), ('UNKNOWN_SETTLEMENT', 404))
        self.assertEqual(error(service, 'bogus', 'sim-committed'), ('NOT_FOUND', 404))

    def test_errors_do_not_touch_the_book(self):
        service = CapitalService()
        drawn(service)
        before = frozen(service)
        for kind in KINDS:
            for ident in ('sim-missing', '', ' pad', 'x' * 101):
                error(service, kind, ident)
        self.assertEqual(frozen(service), before)


class NonMutationTests(unittest.TestCase):
    """Draft section 8: every query leaves the machine, receipts and fixtures as they were."""

    def sweep(self, service, advance_ids):
        fixture_ids = sorted(service.fixtures.rows)
        before = frozen(service)
        for fixture_id in fixture_ids:
            service.read_query('settlement', fixture_id)
            error(service, 'credit_claim', fixture_id)
            error(service, 'credit_advance', fixture_id)
        for advance_id in advance_ids:
            service.read_query('credit_advance', advance_id)
        for kind in KINDS:
            for ident in ('sim-missing', '', ' pad', 'x' * 101):
                error(service, kind, ident)
        self.assertEqual(frozen(service), before)

    def test_every_fixture_id_on_an_empty_book(self):
        service = CapitalService()
        self.assertEqual(len(service.fixtures.rows), 13)
        self.sweep(service, [])

    def test_every_fixture_id_with_a_drawn_advance_and_a_repayment(self):
        service = CapitalService()
        advance = drawn(service)
        run(service, 'repay', advance, {'amount': 400, 'sequence': 1})
        self.sweep(service, [advance])
        for fixture_id in sorted(service.fixtures.rows):
            before = service.machine.state_digest()
            error(service, 'credit_claim', fixture_id)
            self.assertEqual(service.machine.state_digest(), before)

    def test_demo_book_keeps_the_golden_digest(self):
        service = seed.build_service()
        golden = json.loads(GOLDEN.read_text(encoding='utf-8'))
        self.assertEqual(service.machine.state_digest(), golden['state_digest'])
        advance_ids = [row[0] for row in seed.EXPECTED]
        self.sweep(service, advance_ids)
        for advance_id in advance_ids:
            body = service.read_query('credit_advance', advance_id)['body']
            self.assertEqual(body, service.machine.view(advance_id))
        self.assertEqual(service.machine.state_digest(), golden['state_digest'])
        self.assertEqual(seed.capture(service)['state_digest'], golden['state_digest'])

    def test_a_query_that_changed_the_book_would_be_refused(self):
        service = CapitalService()
        drawn(service)
        real = service._read_body

        def mutating(kind, ident):
            service.receipts['rd-injected'] = {'fingerprint': 'x', 'receipt': {}}
            return real(kind, ident)

        service._read_body = mutating
        with self.assertRaises(ApiError) as caught:
            service.read_query('credit_advance', 'sim-rd-one')
        self.assertEqual((caught.exception.code, caught.exception.status), ('READ_ONLY_INVARIANT', 500))


class GateFakeTests(unittest.TestCase):
    def test_remote_book_serves_advance_and_settlement_but_not_the_claim_view(self):
        service = seed.build_service(producer_name='gate-fake')
        try:
            before = service.machine.state_digest()
            advance = service.read_query('credit_advance', 'sim-closed')
            self.assertEqual(advance['body']['phase'], 'CLOSED')
            self.assertEqual(advance['accepted_through'], len(service.machine.export_journal()))
            self.assertEqual(service.read_query('settlement', 'sim-committed')['accepted_through'], 4)
            self.assertEqual(error(service, 'credit_claim', 'sim-committed'), ('NOT_BOUND', 400))
            self.assertEqual(error(service, 'credit_advance', 'sim-none'), ('UNKNOWN_ADVANCE', 404))
            self.assertEqual(service.machine.state_digest(), before)
        finally:
            service.producer.close()


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = __import__('capital.server', fromlist=['make_server']).make_server(0)
        cls.port = cls.server.server_port
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        status, state = cls.request('GET', '/api/state')
        cls.instance = state['instance_id']
        cls.tokens = {'organizer': state['local_token']}
        for role in ('auditor', 'observer', 'agent'):
            _status, session = cls.request('POST', '/api/session', {'role': role}, cls.tokens['organizer'])
            cls.tokens[role] = session['local_token']
        for op, args in (('offer', {'fixture_id': 'sim-committed', 'amount': 1000}),
                         ('approve', {}), ('bind_settlement', {}), ('draw', {})):
            status, receipt = cls.request('POST', '/api/commands', {
                'instance_id': cls.instance, 'operation_id': 'rd-http-' + op.replace('_', ''),
                'op': op, 'advance_id': 'sim-rd-http', 'args': args}, cls.tokens['organizer'])
            assert status == 200 and receipt['outcome'] == 'ACCEPTED', receipt

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=2)

    @classmethod
    def request(cls, method, path, body=None, token=None):
        headers = {}
        payload = None
        if body is not None:
            headers['Content-Type'] = 'application/json'
            payload = json.dumps(body).encode()
        if token is not None:
            headers['X-Capital-Token'] = token
        client = HTTPConnection('127.0.0.1', cls.port, timeout=5)
        client.request(method, path, body=payload, headers=headers)
        response = client.getresponse()
        raw = response.read()
        status = response.status
        client.close()
        return status, json.loads(raw.decode('utf-8'))

    def paths(self):
        return (('credit_advance', '/api/read/credit_advance/sim-rd-http'),
                ('credit_claim', '/api/read/credit_claim/sim-committed'),
                ('settlement', '/api/read/settlement/sim-committed'))

    def test_routes_return_the_envelope_for_organizer_auditor_and_no_token(self):
        for kind, path in self.paths():
            for token in (None, self.tokens['organizer'], self.tokens['auditor']):
                with self.subTest(path=path, token=token is not None):
                    status, body = self.request('GET', path, token=token)
                    self.assertEqual(status, 200, body)
                    self.assertEqual(set(body), ENVELOPE_KEYS)
                    self.assertEqual(body['query'], KINDS[kind])
                    self.assertEqual(body['accepted_through'], 4)
                    self.assertIs(body['visibility_enforced'], False)

    def test_observer_and_agent_are_forbidden_and_read_nothing(self):
        for _kind, path in self.paths():
            for role in ('observer', 'agent'):
                with self.subTest(path=path, role=role):
                    status, body = self.request('GET', path, token=self.tokens[role])
                    self.assertEqual(status, 403)
                    self.assertEqual(body['error'], 'ROLE_FORBIDDEN')
                    self.assertEqual(body['permission'], 'projection:read')
                    self.assertNotIn('body', body)

    def test_http_errors(self):
        cases = (
            ('/api/read/credit_advance/sim-none', 404, 'UNKNOWN_ADVANCE'),
            ('/api/read/credit_claim/sim-none', 404, 'UNKNOWN_CLAIM'),
            ('/api/read/settlement/sim-none', 404, 'UNKNOWN_SETTLEMENT'),
            ('/api/read/credit_advance/', 400, 'INVALID_ID'),
            ('/api/read/credit_claim/' + 'x' * 101, 400, 'INVALID_ID'),
            ('/api/read/settlement/', 400, 'INVALID_ID'),
            ('/api/read/settlement', 404, 'NOT_FOUND'),
            ('/api/read/', 404, 'NOT_FOUND'),
            ('/api/read/bogus/sim-committed', 404, 'NOT_FOUND'),
            ('/api/read/settlement/sim-committed/extra', 404, 'NOT_FOUND'),
            ('/api/read/list_settlements', 404, 'NOT_FOUND'),
            ('/api/read/credit_advance?limit=5', 404, 'NOT_FOUND'),
        )
        for path, status, code in cases:
            with self.subTest(path=path):
                got, body = self.request('GET', path)
                self.assertEqual((got, body.get('error')), (status, code), body)

    def test_query_string_is_ignored_and_post_is_not_a_route(self):
        _status, plain = self.request('GET', '/api/read/settlement/sim-committed')
        _status, with_query = self.request('GET', '/api/read/settlement/sim-committed?limit=1&cursor=x')
        self.assertEqual(plain, with_query)
        client = HTTPConnection('127.0.0.1', self.port, timeout=5)
        client.request('POST', '/api/read/settlement/sim-committed', body=b'{}',
                       headers={'Content-Type': 'application/json',
                                'X-Capital-Token': self.tokens['organizer']})
        response = client.getresponse()
        response.read()
        client.close()
        self.assertEqual(response.status, 404)

    def test_state_is_unchanged_by_reads(self):
        _status, before = self.request('GET', '/api/state')
        for _kind, path in self.paths():
            self.request('GET', path)
        self.request('GET', '/api/read/credit_claim/sim-none')
        _status, after = self.request('GET', '/api/state')
        for key in ('state_digest', 'operation_count'):
            self.assertEqual(before[key], after[key])


if __name__ == '__main__':
    unittest.main()
