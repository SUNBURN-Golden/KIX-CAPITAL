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

# Bootstrap-2 catalogue at the pinned Protocol delivery.
PROMOTED_OPENAPI = ROOT / 'docs/contracts/openapi/kix-protocol.contract-only.openapi.json'
PROMOTED_DIGEST = '86d33d0bd438afdb0cfdfae43a942443cbee85317c31c19bdc2e8da1d9eb022b'


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

    def test_permission_catalog_response_matches_closed_schema(self):
        status, body = self.request('GET', '/api/permissions')
        self.assertEqual(status, 200)
        schema = self.route('GET', '/api/permissions')['response']
        self.check(body, schema)
        for changed in ({**body, 'token': 'not-exposed'},
                        {**body, 'role_permissions': {**body['role_permissions'], 'unlisted': []}}):
            with self.assertRaises(SchemaError):
                self.check(changed, schema)

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
            self.assertTrue(
                set(self.doc['errorGroups']['boundary']) <= set(row['errors']),
                (row['method'], row['path'], 'missing shared boundary errors'),
            )
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
        schemas = json.loads(PROMOTED_OPENAPI.read_bytes())['components']['schemas']
        promoted_catalogue = sorted(set(schemas) - {'LocalCallEnvelope'})
        self.assertEqual(len(promoted_catalogue), 84)
        self.assertEqual(
            hashlib.sha256('\n'.join(promoted_catalogue).encode()).hexdigest(),
            PROMOTED_DIGEST,
        )
        names = set(self.doc['commands'])
        names.update(row['code'] for row in self.doc['errors'])
        names.update(row['operationId'] for row in self.doc['routes'])
        names.update(self.doc['definitions'])
        properties = set()
        _property_names(self.doc, properties)
        names.update(properties)
        collision = names & set(promoted_catalogue)
        self.assertFalse(collision, sorted(collision))
        self.assertNotIn(self.doc['namespace'], promoted_catalogue)

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
        for kind, ident in (('credit_advance', 'sim-journey'), ('credit_claim', 'sim-committed')):
            code, envelope = self.request('GET', f'/api/read/{kind}/{ident}', token=token)
            self.assertEqual(code, 200)
            schema = self.route('GET', f'/api/read/{kind}/{{id}}')['response']
            self.check(envelope, schema)
            terms = envelope['body']['open_terms']
            self.assertEqual(terms['mock_boundary'], 'UNFILLED')
            self.assertEqual(len(terms['terms']), 5)
            for row in terms['terms'].values():
                self.assertIsNone(row['decided_value'])
            for change in ('missing', 'extra', 'filled'):
                bad = json.loads(json.dumps(envelope))
                if change == 'missing':
                    del bad['body']['open_terms']
                elif change == 'extra':
                    bad['body']['open_terms']['terms']['seniority']['extra'] = False
                else:
                    bad['body']['open_terms']['terms']['seniority']['decided_value'] = 1
                with self.subTest(kind=kind, change=change), self.assertRaises(SchemaError):
                    self.check(bad, schema)
        reads = [
            ('GET', f'/api/cases/sim-journey/dossier?instance_id={instance}', '/api/cases/{advance_id}/dossier', None),
            ('GET', '/api/evidence', '/api/evidence', None),
            ('GET', '/api/projection', '/api/projection', None),
            ('GET', '/api/terms', '/api/terms', None),
            ('GET', f'/api/portfolio/snapshot?instance_id={instance}', '/api/portfolio/snapshot', None),
            ('GET', f'/api/terms/portfolio?instance_id={instance}&as_of_day=30', '/api/terms/portfolio', None),
            ('GET', f'/api/terms/portfolio/forecast?instance_id={instance}&expected_settlement_cash_day=45', '/api/terms/portfolio/forecast', None),
            ('GET', '/api/policy', '/api/policy', None),
            ('GET', '/api/policy/simulation', '/api/policy/simulation', None),
            ('GET', f'/api/terms/sim-journey?instance_id={instance}&draw_day=0&as_of_day=0', '/api/terms/{{advance_id}}', None),
            ('GET', f'/api/terms/sim-journey/allocation?instance_id={instance}&as_of_day=30&cash=50000', '/api/terms/{{advance_id}}/allocation', None),
            ('GET', f'/api/terms/sim-journey/setoff?instance_id={instance}&as_of_day=30', '/api/terms/{{advance_id}}/setoff', None),
            ('GET', '/api/readiness?unused=1', '/api/readiness', None),
            ('GET', '/api/decisions', '/api/decisions', None),
            ('GET', '/api/scenarios', '/api/scenarios', None),
            ('GET', '/api/scenarios/full-after', '/api/scenarios/{id}', None),
            ('GET', f'/api/preview/sim-journey?instance_id={instance}', '/api/preview/{{advance_id}}', None),
            ('GET', f'/api/underwrite/sim-journey?instance_id={instance}&sim_day=0', '/api/underwrite/{{advance_id}}', None),
            ('GET', f'/api/operations/j-offer?instance_id={instance}', '/api/operations/{{operation_id}}', None),
            ('GET', '/api/read/credit_advance/sim-journey', '/api/read/credit_advance/{id}', None),
            ('GET', '/api/read/credit_claim/sim-committed', '/api/read/credit_claim/{id}', None),
            ('GET', '/api/read/settlement/sim-committed', '/api/read/settlement/{id}', None),
            ('GET', '/api/export', '/api/export', None),
            ('GET', '/api/export/manifest', '/api/export/manifest', None),
            ('GET', f'/api/export/facts?instance_id={instance}', '/api/export/facts', None),
            ('GET', '/api/export/facts/schema', '/api/export/facts/schema', None),
            ('GET', '/api/reconciliation', '/api/reconciliation', None),
            ('GET', '/api/statement', '/api/statement', None),
            ('GET', '/api/metrics', '/api/metrics', None),
            ('GET', '/api/health', '/api/health', None),
            ('GET', '/api/risk', '/api/risk', None),
            ('GET', '/api/risk/shared-caps', '/api/risk/shared-caps', None),
        ]
        for method, path, template, _query in reads:
            code, payload = self.request(method, path)
            self.assertEqual(code, 200, path)
            schema_path = template.replace('{{', '{').replace('}}', '}')
            self.check(payload, self.route(method, schema_path)['response'])
        overlay_command = self.route('POST', '/api/overlay/commands')
        advance = {'instance_id': instance, 'operation_id': 'j-advance', 'op': 'advance_day',
                   'from_sim_day': 0, 'to_sim_day': 3, 'reason': 'facade journey'}
        self.check(advance, overlay_command['request'])
        code, applied = self.request('POST', '/api/overlay/commands', advance, token)
        self.assertEqual(code, 200, applied)
        self.check(applied, overlay_command['response'])
        code, again = self.request('POST', '/api/overlay/commands', advance, token)
        self.check(again, overlay_command['response'])
        self.assertTrue(again['transport_duplicate'])
        code, quote = self.request('GET', '/api/overlay?operation_id=j-advance')
        self.assertEqual(code, 200)
        self.check(quote, self.route('GET', '/api/overlay')['response'])
        code, unknown = self.request('GET', '/api/overlay?operation_id=j-never')
        self.check(unknown, self.route('GET', '/api/overlay')['response'])
        tainted_quote = json.loads(json.dumps(quote))
        tainted_quote['advances'] = [{**quote['advances'][0], 'not_in_facade': 1}] if quote['advances'] else [{'x': 1}]
        with self.assertRaises(SchemaError):
            self.check(tainted_quote, self.route('GET', '/api/overlay')['response'])
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
