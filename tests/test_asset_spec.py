"""KRW declared once as an AssetSpec; any other asset on a command is rejected ASSET_MISMATCH.

PROVISIONAL per docs/decisions/CAPITAL_UPSTREAM_BINDING.md section 3.6. No registry, no FX,
no second asset, no change to the integer amount representation.
"""
import ast
import copy
import importlib.util
import json
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

import capital.protocol  # installs the vendored FSM path
import mock_credit
import mock_settlement

from capital import assets
from capital.assets import ASSETS, KRW
from capital.export import sha256_hex
from capital.server import make_server
from capital.service import ApiError, CapitalService, digest
from capital.store import InMemoryStorage
from capital.verify import verify_manifest

ROOT = Path(__file__).resolve().parents[1]
NOTE = 'CAPITAL_UPSTREAM_BINDING.md'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


decision_ledger = _load('decision_ledger', ROOT / 'scripts' / 'decision_ledger.py')
facade_schema = _load('facade_schema', ROOT / 'tests' / 'facade_schema.py')


def note_entry():
    """The asset_registry_fx entry of the merged upstream-binding decision block."""
    text = (ROOT / 'docs' / 'decisions' / NOTE).read_text(encoding='utf-8')
    blocks = decision_ledger.extract_blocks(text)
    assert len(blocks) == 1
    return blocks[0]['entries']['asset_registry_fx']


def variants():
    """Every way a body can carry something other than the declared spec."""
    def with_(**changes):
        return {**KRW, **changes}
    return {
        'usd spec': {'namespace': 'fiat', 'reference': 'USD', 'decimals': 2, 'max_atoms': 10**12},
        'stablecoin spec': {'namespace': 'crypto', 'reference': 'USDC', 'decimals': 6, 'max_atoms': 2**128 - 1},
        'bare code': 'KRW',
        'bare namespace': 'fiat',
        'null': None,
        'empty string': '',
        'empty object': {},
        'list of the spec': [dict(KRW)],
        'integer': 410,
        'boolean': True,
        'lowercase reference': with_(reference='krw'),
        'other namespace': with_(namespace='crypto'),
        'decimals 2': with_(decimals=2),
        'decimals false': with_(decimals=False),
        'decimals float': with_(decimals=0.0),
        'decimals string': with_(decimals='0'),
        'max_atoms +1': with_(max_atoms=10**12 + 1),
        'max_atoms -1': with_(max_atoms=10**12 - 1),
        'max_atoms float': with_(max_atoms=1e12),
        'max_atoms string': with_(max_atoms='1000000000000'),
        'u128 max_atoms': with_(max_atoms=2**128 - 1),
        'missing max_atoms': {key: value for key, value in KRW.items() if key != 'max_atoms'},
        'extra key': {**KRW, 'registry_version': 1},
    }


class DeclarationTests(unittest.TestCase):
    def test_exactly_one_declared_entry_with_the_pinned_shape(self):
        self.assertEqual(len(ASSETS), 1)
        self.assertEqual(
            KRW, {'namespace': 'fiat', 'reference': 'KRW', 'decimals': 0, 'max_atoms': 1000000000000})
        self.assertEqual(assets.declared(), [KRW])

    def test_max_atoms_is_the_pinned_fsm_fixture_bound(self):
        self.assertEqual(mock_credit.MONEY_MAX, KRW['max_atoms'])
        self.assertEqual(mock_settlement.MONEY_MAX, KRW['max_atoms'])

    def test_declaration_agrees_with_the_merged_decision_note(self):
        declared = note_entry()['target']['krw_profile_declared_now']
        for key in ('namespace', 'reference', 'decimals'):
            self.assertEqual(declared[key], KRW[key], key)
        self.assertTrue(declared['fixture_money_max'].startswith(str(KRW['max_atoms'])))
        self.assertEqual(note_entry()['status'], 'DEFERRED')
        self.assertIn('no cross-asset netting or summation (ASSET_MISMATCH)', note_entry()['target']['rules'])

    def test_declared_returns_a_fresh_copy(self):
        taken = assets.declared()
        taken[0]['reference'] = 'USD'
        taken.append({'reference': 'EUR'})
        self.assertEqual(assets.declared(), [KRW])
        self.assertEqual(KRW['reference'], 'KRW')

    def test_matches_is_strict_about_types_and_keys(self):
        self.assertTrue(assets.matches(dict(KRW)))
        self.assertTrue(assets.matches(dict(reversed(list(KRW.items())))))
        for name, value in variants().items():
            self.assertFalse(assets.matches(value), name)

    def test_module_is_importable_without_other_capital_modules(self):
        source = (ROOT / 'capital' / 'assets.py').read_text(encoding='utf-8')
        imported = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or '').split('.')[0])
        self.assertEqual(imported, {'__future__', 'copy'})
        self.assertNotIn('__file__', source)


class ExposureTests(unittest.TestCase):
    def setUp(self):
        self.service = CapitalService()

    def test_state_exposes_the_one_entry(self):
        state = self.service.snapshot()
        self.assertEqual(state['assets'], [KRW])
        state['assets'][0]['reference'] = 'USD'
        state['assets'].append({})
        self.assertEqual(self.service.snapshot()['assets'], [KRW])

    def test_state_assets_are_the_same_for_every_role(self):
        for role in ('organizer', 'auditor', 'observer'):
            self.assertEqual(self.service.snapshot(role)['assets'], [KRW], role)

    def test_manifest_source_pin_carries_the_same_entry(self):
        manifest = self.service.export_manifest()
        body = manifest['sections']['source_pin']['body']
        self.assertEqual(body['assets'], [KRW])
        self.assertEqual(len(body['assets']), 1)
        self.assertEqual(manifest['sections']['source_pin']['sha256'], sha256_hex(body))

    def test_manifest_assets_sit_under_the_section_hash(self):
        manifest = self.service.export_manifest()
        self.assertTrue(verify_manifest(manifest)['ok'])
        tampered = copy.deepcopy(manifest)
        tampered['sections']['source_pin']['body']['assets'][0]['reference'] = 'USD'
        report = verify_manifest(tampered)
        self.assertFalse(report['ok'])
        self.assertEqual(report['reason'], 'SECTION_HASH_MISMATCH:source_pin')
        dropped = copy.deepcopy(manifest)
        dropped['sections']['source_pin']['body']['assets'] = []
        self.assertEqual(verify_manifest(dropped)['reason'], 'SECTION_HASH_MISMATCH:source_pin')

    def test_the_v1_export_and_the_state_digest_do_not_carry_assets(self):
        before = self.service.snapshot()['state_digest']
        self.service.export_manifest()
        self.assertEqual(self.service.snapshot()['state_digest'], before)
        self.assertNotIn('assets', self.service.export())

    def test_reading_the_declaration_writes_nothing(self):
        before = (self.service.machine.export_journal(), copy.deepcopy(self.service.receipts))
        self.service.snapshot()
        self.service.export_manifest()
        self.assertEqual((self.service.machine.export_journal(), self.service.receipts), before)


class CountingStorage(InMemoryStorage):
    def __init__(self):
        super().__init__()
        self.saves = 0

    def save(self, document):
        self.saves += 1
        super().save(document)


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.storage = CountingStorage()
        self.service = CapitalService(storage=self.storage)
        self.saves_at_start = self.storage.saves

    def body(self, key='asset-op-1', op='offer', advance='sim-asset', args=None, **extra):
        if args is None:
            args = {'fixture_id': 'sim-committed', 'amount': 60000}
        return {'instance_id': self.service.instance_id, 'operation_id': key, 'op': op,
                'advance_id': advance, 'args': args, **extra}

    def frozen(self):
        counters = self.service.observability.snapshot()['counters']
        return {'journal': copy.deepcopy(self.service.machine.export_journal()),
                'receipts': copy.deepcopy(self.service.receipts),
                'digest': self.service.machine.state_digest(),
                'cases': dict(self.service.case_fixtures),
                'commands': counters['commands'], 'rejections': counters['rejections'],
                'saves': self.storage.saves}

    def test_the_declared_asset_is_accepted_exactly_as_no_asset(self):
        plain = CapitalService()
        left = plain.execute({**self.body(), 'instance_id': plain.instance_id})
        right = self.service.execute(self.body(asset=dict(KRW)))
        self.assertEqual(right['outcome'], 'ACCEPTED')
        self.assertEqual(left['outcome'], 'ACCEPTED')
        self.assertEqual(left['result'], right['result'])
        self.assertEqual(plain.machine.state_digest(), self.service.machine.state_digest())
        self.assertNotIn('asset', right)
        self.assertNotIn('asset', self.service.receipts['asset-op-1']['receipt'])

    def test_every_operation_accepts_the_declared_asset(self):
        steps = [('offer', {'fixture_id': 'sim-committed', 'amount': 60000}), ('approve', {}),
                 ('bind_settlement', {}), ('draw', {}), ('repay', {'amount': 60000, 'sequence': 1}),
                 ('close', {})]
        for index, (op, args) in enumerate(steps):
            receipt = self.service.execute(self.body(key=f'all-{index}', op=op, args=args, asset=dict(KRW)))
            self.assertEqual(receipt['outcome'], 'ACCEPTED', op)
        self.assertEqual(self.service.machine.view('sim-asset')['phase'], 'CLOSED')

    def test_every_other_value_is_rejected_without_a_trace(self):
        before = self.frozen()
        for name, value in variants().items():
            with self.assertRaises(ApiError, msg=name) as caught:
                self.service.execute(self.body(asset=copy.deepcopy(value)))
            self.assertEqual((caught.exception.code, caught.exception.status), ('ASSET_MISMATCH', 400), name)
            self.assertEqual(self.frozen(), before, name)
        self.assertEqual(self.service.receipts, {})
        self.assertEqual(self.service.machine.export_journal(), [])
        self.assertEqual(self.storage.saves, self.saves_at_start)

    def test_a_rejected_operation_is_unknown_and_its_id_is_still_free(self):
        with self.assertRaises(ApiError):
            self.service.execute(self.body(asset=variants()['usd spec']))
        self.assertEqual(self.service.operation('asset-op-1', self.service.instance_id)['outcome'], 'UNKNOWN')
        accepted = self.service.execute(self.body(asset=dict(KRW)))
        self.assertEqual(accepted['outcome'], 'ACCEPTED')
        self.assertFalse(accepted['transport_duplicate'])

    def test_a_foreign_asset_on_a_replay_does_not_return_or_change_the_stored_receipt(self):
        stored = self.service.execute(self.body())
        before = self.frozen()
        with self.assertRaises(ApiError) as caught:
            self.service.execute(self.body(asset=variants()['usd spec']))
        self.assertEqual(caught.exception.code, 'ASSET_MISMATCH')
        self.assertEqual(self.frozen(), before)
        self.assertEqual(self.service.receipts['asset-op-1']['receipt'], stored)

    def test_asset_is_not_part_of_the_idempotency_fingerprint(self):
        first = self.service.execute(self.body())
        replay = self.service.execute(self.body(asset=dict(KRW)))
        self.assertTrue(replay['transport_duplicate'])
        self.assertEqual(replay['result'], first['result'])
        self.assertEqual(len(self.service.receipts), 1)
        same = digest({'operation_id': 'asset-op-1', 'op': 'offer', 'advance_id': 'sim-asset',
                       'args': {'fixture_id': 'sim-committed', 'amount': 60000}})
        self.assertEqual(self.service.receipts['asset-op-1']['fingerprint'], same)
        with self.assertRaises(ApiError) as caught:
            self.service.execute(self.body(args={'fixture_id': 'sim-committed', 'amount': 1}, asset=dict(KRW)))
        self.assertEqual(caught.exception.code, 'IDEMPOTENCY_CONFLICT')

    def test_role_and_session_checks_come_before_the_asset_check(self):
        foreign = variants()['usd spec']
        with self.assertRaises(ApiError) as caught:
            self.service.execute(self.body(asset=foreign), role='observer')
        self.assertEqual(caught.exception.code, 'ROLE_FORBIDDEN')
        stale = {**self.body(asset=foreign), 'instance_id': 'another-process'}
        with self.assertRaises(ApiError) as caught:
            self.service.execute(stale)
        self.assertEqual(caught.exception.code, 'SESSION_CHANGED')
        with self.assertRaises(ApiError) as caught:
            self.service.execute(self.body(asset=foreign))
        self.assertEqual(caught.exception.code, 'ASSET_MISMATCH')

    def test_the_envelope_is_still_strict(self):
        for extra in ({'currency': 'KRW'}, {'assets': [dict(KRW)]}, {'Asset': dict(KRW)}):
            with self.assertRaises(ApiError) as caught:
                self.service.execute(self.body(**extra))
            self.assertEqual(caught.exception.code, 'INVALID_COMMAND', extra)
        with self.assertRaises(ApiError) as caught:
            self.service.execute({**self.body(), 'args': {'fixture_id': 'sim-committed', 'amount': 1, 'asset': dict(KRW)}})
        self.assertEqual(caught.exception.code, 'INVALID_ARGUMENTS')
        self.assertEqual(self.service.receipts, {})

    def test_asset_may_travel_with_a_proposal_citation(self):
        with self.assertRaises(ApiError) as caught:
            self.service.execute(self.body(asset=dict(KRW), proposal_id='prop-1'))
        self.assertEqual(caught.exception.code, 'UNKNOWN_PROPOSAL')
        with self.assertRaises(ApiError) as caught:
            self.service.execute(self.body(asset=variants()['usd spec'], proposal_id='prop-1'))
        self.assertEqual(caught.exception.code, 'ASSET_MISMATCH')

    def test_the_declared_asset_does_not_loosen_the_integer_amount_rules(self):
        for index, amount in enumerate((1.5, True, '60000', 10**12 + 1, 0, -5)):
            receipt = self.service.execute(self.body(
                key=f'amount-{index}', args={'fixture_id': 'sim-committed', 'amount': amount}, asset=dict(KRW)))
            self.assertEqual(receipt['outcome'], 'REJECTED', amount)
        self.assertEqual(self.service.machine.export_journal(), [])


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
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
            payload = json.dumps(body).encode()
        if token is not None:
            headers['X-Capital-Token'] = token
        client = HTTPConnection('127.0.0.1', self.port, timeout=5)
        client.request(method, path, body=payload, headers=headers)
        response = client.getresponse()
        status, raw = response.status, response.read()
        client.close()
        return status, json.loads(raw.decode('utf-8'))

    def command(self, key, **extra):
        _status, state = self.request('GET', '/api/state')
        body = {'instance_id': state['instance_id'], 'operation_id': key, 'op': 'offer',
                'advance_id': 'sim-http-asset', 'args': {'fixture_id': 'sim-committed', 'amount': 100}, **extra}
        return state, body, self.request('POST', '/api/commands', body, state['local_token'])

    def test_state_and_manifest_expose_exactly_one_entry(self):
        status, state = self.request('GET', '/api/state')
        self.assertEqual((status, state['assets']), (200, [KRW]))
        status, manifest = self.request('GET', '/api/export/manifest')
        self.assertEqual((status, manifest['sections']['source_pin']['body']['assets']), (200, [KRW]))

    def test_declared_asset_is_200_and_a_foreign_asset_is_400_ASSET_MISMATCH(self):
        state, _body, (status, receipt) = self.command('http-asset-ok', asset=dict(KRW))
        self.assertEqual((status, receipt['outcome']), (200, 'ACCEPTED'))
        before = self.request('GET', '/api/state')[1]
        for name, value in variants().items():
            _state, body, (status, error) = self.command(f'http-asset-bad-{abs(hash(name))}', asset=value)
            self.assertEqual((status, error['error']), (400, 'ASSET_MISMATCH'), name)
            status, found = self.request(
                'GET', f"/api/operations/{body['operation_id']}?instance_id={state['instance_id']}")
            self.assertEqual((status, found['outcome']), (200, 'UNKNOWN'), name)
        after = self.request('GET', '/api/state')[1]
        self.assertEqual(after['state_digest'], before['state_digest'])
        self.assertEqual(after['operation_count'], before['operation_count'])


class FacadeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = facade_schema.load_contract()

    def route(self, method, path):
        return next(row for row in self.doc['routes'] if row['method'] == method and row['path'] == path)

    def check(self, value, schema):
        facade_schema.validate(value, schema, self.doc)

    def test_asset_spec_definition_documents_the_declared_shape(self):
        spec = self.doc['definitions']['asset_spec']
        self.assertIs(spec['additionalProperties'], False)
        self.assertEqual(spec['required'], ['namespace', 'reference', 'decimals', 'max_atoms'])
        self.assertEqual({key: value['const'] for key, value in spec['properties'].items()}, KRW)
        self.assertEqual({key: value['type'] for key, value in spec['properties'].items()},
                         {'namespace': 'string', 'reference': 'string', 'decimals': 'integer', 'max_atoms': 'integer'})
        self.assertIn('CAPITAL_UPSTREAM_BINDING', spec['description'])
        self.assertIn('ASSET_MISMATCH', spec['description'])
        self.check(dict(KRW), {'$ref': '#/definitions/asset_spec'})
        for name, value in variants().items():
            if type(value) is dict and not (set(value) == set(KRW) and all(type(value[k]) is type(KRW[k]) for k in KRW)):
                continue
            if value != KRW:
                with self.assertRaises(facade_schema.SchemaError, msg=name):
                    self.check(value, {'$ref': '#/definitions/asset_spec'})

    def test_the_rejection_code_is_a_registered_command_error(self):
        self.assertIn({'code': 'ASSET_MISMATCH', 'status': 400}, self.doc['errors'])
        self.assertIn('ASSET_MISMATCH', self.doc['errorGroups']['command'])
        self.assertIn('ASSET_MISMATCH', self.route('POST', '/api/commands')['errors'])
        self.assertIn('ASSET_MISMATCH', self.doc['definitions']['error_envelope']['properties']['error']['enum'])
        for method, path in (('GET', '/api/state'), ('GET', '/api/export/manifest')):
            self.assertNotIn('ASSET_MISMATCH', self.route(method, path)['errors'])

    def test_state_and_source_section_require_the_one_entry_array(self):
        for name in ('state', 'source_section'):
            definition = self.doc['definitions'][name]
            self.assertIn('assets', definition['required'], name)
            self.assertEqual(definition['properties']['assets'], {'$ref': '#/definitions/assets'}, name)
        array = self.doc['definitions']['assets']
        self.assertEqual((array['type'], array['minItems'], array['maxItems']), ('array', 1, 1))
        self.assertEqual(array['items'], {'$ref': '#/definitions/asset_spec'})
        self.check([dict(KRW)], {'$ref': '#/definitions/assets'})
        for bad in ([], [dict(KRW), dict(KRW)], [{**KRW, 'reference': 'USD'}]):
            with self.assertRaises(facade_schema.SchemaError):
                self.check(bad, {'$ref': '#/definitions/assets'})

    def test_every_command_shape_takes_the_optional_asset(self):
        routed = self.route('POST', '/api/commands')['request']
        defined = self.doc['definitions']['command_request']
        self.assertEqual(routed, defined)
        self.assertEqual(len(defined['anyOf']), 3)
        for branch in defined['anyOf']:
            self.assertEqual(branch['properties']['asset'], {'$ref': '#/definitions/asset_spec'})
            self.assertNotIn('asset', branch['required'])
            self.assertNotIn('asset', branch['properties']['args'].get('properties', {}))
        shapes = [
            ('offer', {'fixture_id': 'sim-committed', 'amount': 1}),
            ('approve', {}),
            ('repay', {'amount': 1, 'sequence': 1}),
        ]
        for op, args in shapes:
            body = {'instance_id': 'i', 'operation_id': 'o', 'op': op, 'advance_id': 'sim-a', 'args': args}
            self.check(body, defined)
            self.check({**body, 'asset': dict(KRW)}, defined)
            with self.assertRaises(facade_schema.SchemaError, msg=op):
                self.check({**body, 'asset': {**KRW, 'reference': 'USD'}}, defined)
            with self.assertRaises(facade_schema.SchemaError, msg=op):
                self.check({**body, 'asset': 'KRW'}, defined)

    def test_live_responses_validate_against_the_updated_schemas(self):
        service = CapitalService()
        self.check(service.snapshot() | {'local_token': 'x'}, self.route('GET', '/api/state')['response'])
        self.check(service.export_manifest(), self.route('GET', '/api/export/manifest')['response'])
        self.check(service.readiness(), self.route('GET', '/api/readiness')['response'])
        stripped = service.snapshot() | {'local_token': 'x'}
        del stripped['assets']
        with self.assertRaises(facade_schema.SchemaError):
            self.check(stripped, self.route('GET', '/api/state')['response'])
        manifest = service.export_manifest()
        del manifest['sections']['source_pin']['body']['assets']
        with self.assertRaises(facade_schema.SchemaError):
            self.check(manifest, self.route('GET', '/api/export/manifest')['response'])


class WordingTests(unittest.TestCase):
    def test_readiness_cap_12_cites_the_upstream_binding_decision(self):
        ready = CapitalService().readiness()
        note = ready['requirement_notes']['CAP-12']
        self.assertIn('docs/decisions/CAPITAL_UPSTREAM_BINDING.md', note)
        self.assertIn('PROVISIONAL', note)
        self.assertIn('ASSET_MISMATCH', note)
        self.assertIn('NOT_BOUND', note)
        group = next(row for row in ready['groups'] if row['id'] == 'assets-and-rights')
        self.assertIn('CAP-12', group['requirements'])
        self.assertEqual(group['status'], 'UPSTREAM_REQUIRED')
        self.assertTrue(group['blockers'])
        self.assertTrue(any('CAPITAL_UPSTREAM_BINDING.md' in line and 'ASSET_MISMATCH' in line
                            for line in group['available']))
        self.assertTrue(any('registry' in line and 'FX' in line for line in group['blockers']))
        self.assertEqual(ready['upstream_binding'], 'NOT_BOUND')
        self.assertEqual(ready['upstream_nodes_completed'], [])
        self.assertIs(ready['production_authorized'], False)

    def test_requirement_and_coverage_rows_cite_the_decision_and_stay_simulated(self):
        for name in ('CAPITAL_REQUIREMENTS_KO.md', 'CAP_COVERAGE.md'):
            rows = [line for line in (ROOT / 'docs' / name).read_text(encoding='utf-8').splitlines()
                    if line.startswith('| CAP-12 ')]
            self.assertEqual(len(rows), 1, name)
            self.assertIn('CAPITAL_UPSTREAM_BINDING.md', rows[0], name)
            self.assertIn('ASSET_MISMATCH', rows[0], name)
            self.assertIn('FX', rows[0], name)
        coverage = [line for line in (ROOT / 'docs' / 'CAP_COVERAGE.md').read_text(encoding='utf-8').splitlines()
                    if line.startswith('| CAP-12 ')][0]
        self.assertIn('| SIMULATED |', coverage)

    def test_integration_doc_records_the_block_the_field_and_the_code(self):
        text = (ROOT / 'docs' / 'INTEGRATION.md').read_text(encoding='utf-8')
        for needle in ('`assets`', 'ASSET_MISMATCH', 'max_atoms: 1000000000000', 'capital/assets.py',
                       'CAPITAL_UPSTREAM_BINDING.md', '`source_pin` body carries'):
            self.assertIn(needle, text, needle)


if __name__ == '__main__':
    unittest.main()
