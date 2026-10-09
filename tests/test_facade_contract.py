"""Local facade schema: real journey responses, unknown fields, catalogue names."""
import hashlib
import importlib.util
import json
import re
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from capital.server import ASSETS, GET_DISPATCH, POST_DISPATCH
from capital.service import OPS

_SCHEMA = importlib.util.spec_from_file_location(
    'facade_schema', Path(__file__).resolve().with_name('facade_schema.py'))
_facade_schema = importlib.util.module_from_spec(_SCHEMA)
_SCHEMA.loader.exec_module(_facade_schema)
SchemaError = _facade_schema.SchemaError
load_contract = _facade_schema.load_contract
validate = _facade_schema.validate

ROOT = Path(__file__).resolve().parents[1]

# Promoted catalogue at kix-protocol 7481b0e16ce9b903abbffa62249bb91cd9e63cfe
# reference/v0.3-rc1/protocol_contract.json domain kix:fixture:lifecycle:0.3.
# Snapshot only. This test does not bind that contract. CAP-16 exact tuple stays NOT_BOUND.
PROMOTED_CATALOGUE = (
    'abort_effect', 'abort_trade', 'accept_gift', 'accept_trade', 'adjust_pg_cancel', 'admit',
    'advance_clock', 'authorize_marketing', 'cancel_event', 'cancel_gift', 'cancel_listing',
    'capture', 'claim_effect', 'close_delegation', 'close_sales', 'commit_trade', 'complete_event',
    'create_event', 'create_listing', 'delegate', 'dispatch_effect', 'expire_trade',
    'finalize_effect', 'issue_invitation', 'observe_dispatch_lookup', 'observe_effect',
    'observe_funding', 'observe_recovery', 'observe_return', 'offer_gift', 'open_admission',
    'prepare_effect', 'prepare_trade', 'refund_ticket', 'release_inventory', 'reserve_listing',
    'send_effect', 'set_consent', 'settle_capture', 'void_unissued',
)
# sha256 of the catalogue names joined by newlines. Changing a name must update this digest.
PROMOTED_DIGEST = '18183027d422a9c55366862d1015985ee747f259440888185f8931f072bd782c'


def _property_names(node, found):
    if type(node) is dict:
        properties = node.get('properties')
        if type(properties) is dict:
            found.update(properties)
        for value in node.values():
            _property_names(value, found)
    elif type(node) is list:
        for item in node:
            _property_names(item, found)


class FacadeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = load_contract()
        cls.server = __import__('capital.server', fromlist=['make_server']).make_server(0)
        cls.port = cls.server.server_port
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=2)

    def request(self, method, path, body=None, token=None):
        headers = {}
        payload = None
        if body is not None:
            headers['Content-Type'] = 'application/json'
            payload = body if isinstance(body, bytes) else json.dumps(body).encode()
        if token is not None:
            headers['X-Capital-Token'] = token
        client = HTTPConnection('127.0.0.1', self.port, timeout=5)
        client.request(method, path, body=payload, headers=headers)
        response = client.getresponse()
        raw = response.read()
        status = response.status
        client.close()
        return status, json.loads(raw.decode('utf-8'))

    def route(self, method, path):
        for item in self.doc['routes']:
            if item['method'] == method and item['path'] == path:
                return item
        self.fail(f'missing route {method} {path}')

    def check(self, value, schema):
        validate(value, schema, self.doc)

    def test_namespace_is_local_and_not_a_conformance_claim(self):
        self.assertEqual(self.doc['namespace'], 'capital-local-facade/1')
        self.assertEqual(self.doc['unknownFields'], 'REJECT')
        self.assertIs(self.doc['semantic_conformance'], False)
        self.assertEqual(self.doc['cap16_exact_tuple'], 'NOT_BOUND')
        self.assertNotEqual(self.doc['namespace'], 'kix:fixture:lifecycle:0.3')
        self.assertIn('Not SEMANTIC_CONFORMANCE', self.doc['description'])

    def test_routes_cover_the_server_dispatch(self):
        api = [row for row in self.doc['routes'] if row['kind'] == 'api']
        self.assertEqual(
            {row['dispatch'] for row in api if row['method'] == 'GET'},
            {prefix for prefix, _children, _name in GET_DISPATCH},
        )
        self.assertEqual(
            {row['dispatch'] for row in api if row['method'] == 'POST'},
            {prefix for prefix, _permission in POST_DISPATCH},
        )
        static = [row for row in self.doc['routes'] if row['kind'] == 'static']
        self.assertEqual({row['path'] for row in static}, set(ASSETS))
        codes = {row['code'] for row in self.doc['errors']}
        used = set()
        for row in self.doc['routes']:
            self.assertTrue(row['errors'])
            unknown = set(row['errors']) - codes
            self.assertFalse(unknown, unknown)
            used.update(row['errors'])
        self.assertEqual(used, codes)
        self.assertEqual(set(self.doc['commands']), set(OPS))
        for op, spec in self.doc['commands'].items():
            self.assertEqual(set(spec['args']), OPS[op])

    def test_error_literals_are_in_the_schema(self):
        found = set()
        for path in (ROOT / 'capital').rglob('*.py'):
            if 'vendor' in path.parts or 'contract' in path.parts:
                continue
            text = path.read_text(encoding='utf-8')
            found.update(re.findall(r"ApiError\(\s*'([A-Z][A-Z0-9_]*)'", text))
            found.update(re.findall(r"WorkspaceError\(\s*'([A-Z][A-Z0-9_]*)'", text))
            if path.name == 'auth.py':
                found.update(re.findall(r"_fail\(\s*'([A-Z][A-Z0-9_]*)'", text))
        codes = {row['code'] for row in self.doc['errors']}
        self.assertTrue(found <= codes, sorted(found - codes))
        self.assertIn('NOT_FOUND', codes)
        self.assertIn('WORKSPACE_UNREADABLE', codes)

    def test_names_do_not_collide_with_the_promoted_catalogue(self):
        self.assertEqual(len(PROMOTED_CATALOGUE), 40)
        self.assertEqual(len(set(PROMOTED_CATALOGUE)), 40)
        self.assertEqual(
            hashlib.sha256('\n'.join(PROMOTED_CATALOGUE).encode()).hexdigest(),
            PROMOTED_DIGEST,
        )
        names = set(self.doc['commands'])
        names.update(row['code'] for row in self.doc['errors'])
        names.update(row['operationId'] for row in self.doc['routes'])
        names.update(self.doc['definitions'])
        properties = set()
        _property_names(self.doc, properties)
        names.update(properties)
        collision = names & set(PROMOTED_CATALOGUE)
        self.assertFalse(collision, sorted(collision))
        self.assertNotIn(self.doc['namespace'], PROMOTED_CATALOGUE)

    def test_scripted_journey_matches_and_an_unknown_field_is_rejected(self):
        status, state = self.request('GET', '/api/state')
        self.assertEqual(status, 200)
        self.check(state, self.route('GET', '/api/state')['response'])
        token = state['local_token']
        instance = state['instance_id']
        commands = self.route('POST', '/api/commands')

        def command(op, advance, args, key):
            body = {
                'instance_id': instance, 'operation_id': key, 'op': op,
                'advance_id': advance, 'args': args,
            }
            self.check(body, commands['request'])
            code, payload = self.request('POST', '/api/commands', body, token)
            self.assertEqual(code, 200, payload)
            self.check(payload, commands['response'])
            return payload

        self.assertEqual(command('offer', 'sim-journey', {'fixture_id': 'sim-committed', 'amount': 60000}, 'j-offer')['outcome'], 'ACCEPTED')
        command('approve', 'sim-journey', {}, 'j-approve')
        command('bind_settlement', 'sim-journey', {}, 'j-bind')
        command('draw', 'sim-journey', {}, 'j-draw')
        refused = command('close', 'sim-journey', {}, 'j-close')
        self.assertEqual(refused['outcome'], 'REJECTED')
        self.assertEqual(refused['error'], 'OUTSTANDING_REMAINS')
        command('repay', 'sim-journey', {'amount': 60000, 'sequence': 1}, 'j-repay')
        closed = command('close', 'sim-journey', {}, 'j-close-2')
        self.assertEqual(closed['result']['credit']['phase'], 'CLOSED')
        reads = [
            ('GET', '/api/evidence', '/api/evidence', None),
            ('GET', '/api/projection', '/api/projection', None),
            ('GET', '/api/terms', '/api/terms', None),
            ('GET', f'/api/terms/sim-journey?instance_id={instance}&draw_day=0&as_of_day=0', '/api/terms/{{advance_id}}', None),
            ('GET', '/api/readiness?unused=1', '/api/readiness', None),
            ('GET', '/api/scenarios', '/api/scenarios', None),
            ('GET', '/api/scenarios/full-after', '/api/scenarios/{id}', None),
            ('GET', f'/api/preview/sim-journey?instance_id={instance}', '/api/preview/{{advance_id}}', None),
            ('GET', f'/api/operations/j-offer?instance_id={instance}', '/api/operations/{{operation_id}}', None),
            ('GET', '/api/export', '/api/export', None),
            ('GET', '/api/export/manifest', '/api/export/manifest', None),
            ('GET', '/api/reconciliation', '/api/reconciliation', None),
            ('GET', '/api/statement', '/api/statement', None),
        ]
        for method, path, template, _query in reads:
            code, payload = self.request(method, path)
            self.assertEqual(code, 200, path)
            schema_path = template.replace('{{', '{').replace('}}', '}')
            self.check(payload, self.route(method, schema_path)['response'])
        code, missing = self.request('GET', '/api/scenarios/not-a-scenario')
        self.assertEqual(code, 404)
        self.check(missing, self.doc['definitions']['error_envelope'])
        session = self.route('POST', '/api/session')
        body = {'role': 'observer'}
        self.check(body, session['request'])
        code, opened = self.request('POST', '/api/session', body, token)
        self.assertEqual(code, 200)
        self.check(opened, session['response'])
        tainted = dict(state)
        tainted['not_in_facade'] = 'REJECT'
        with self.assertRaises(SchemaError) as caught:
            self.check(tainted, self.route('GET', '/api/state')['response'])
        self.assertIn('unknown field', str(caught.exception))
        nested = json.loads(json.dumps(state))
        nested['workspace']['extra'] = True
        with self.assertRaises(SchemaError):
            self.check(nested, self.route('GET', '/api/state')['response'])


if __name__ == '__main__':
    unittest.main()
