"""Offline triage contracts and independent synthetic diagnostic expectations."""
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from capital.observation import LocalFakeObservation
from capital.observation_triage import (ContractError, InputError, INPUT_FORMAT, MAX_BYTES,
                                        parse_input, serialize, triage, validate)

ROOT = Path(__file__).resolve().parents[1]
VECTORS = ROOT / 'tests/vectors/observation_triage'
CASES_SHA256 = 'ed23804ebb9ec9abe35c124d05aaa3dec8e02395fc31820baee7ffee7cd63d2c'
INPUT_SHA256 = '52672cc40b70c178cf6a56673815c47e8716e130e44ca3230861f061777c2b30'
FIELDS = ('provider', 'account', 'environment', 'profile_version', 'payment_key', 'order_id',
          'operation', 'kind', 'amount', 'currency', 'method', 'status', 'occurred_at',
          'offset', 'api_version', 'product')


def envelope(facts=None, bindings=None):
    base = json.loads((VECTORS / 'input.json').read_text())
    return dict(format=INPUT_FORMAT, label='SIMULATED', facts=base['facts'][:1] if facts is None else facts,
                bindings=base['bindings'] if bindings is None else bindings)


def run_triage_vectors(path=VECTORS / 'cases.json'):
    raw = Path(path).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == CASES_SHA256, 'triage corpus byte drift'
    table = json.loads(raw)
    assert table['format'] == 'KIX_CAPITAL_OBSERVATION_TRIAGE_CASES_V1'
    assert table['label'] == 'SIMULATED' and table['applied'] is False
    assert table['cases'] and len({c['name'] for c in table['cases']}) == len(table['cases'])
    for case in table['cases']:
        document = parse_input(json.dumps(case['input']).encode())
        result = triage(document['facts'], bindings=document['bindings'])
        assert hashlib.sha256(serialize(result)).hexdigest() == case['report_sha256'], case['name']
        assert [g['status'] for g in result['groups']] == case['statuses'], case['name']
        assert [g['binding_status'] for g in result['groups']] == case['binding_statuses'], case['name']
        assert [d['reason_code'] for d in result['deliveries']] == case['delivery_reasons'], case['name']
        assert [g['delivery_indices'] for g in result['groups']] == case['group_deliveries'], case['name']
        assert [[v['delivery_indices'] for v in g['variants']] for g in result['groups']] == case['variant_deliveries']
        assert [[c['delivery_index'] for c in g['conflicts']] for g in result['groups']] == case['conflict_deliveries']
        assert [[[d['field'] for d in c['differences']] for c in g['conflicts']]
                for g in result['groups']] == case['conflict_fields']
        assert [[v['binding']['status'] for v in g['variants']] for g in result['groups']] == case['variant_bindings']
    example = (VECTORS / 'input.json').read_bytes()
    assert hashlib.sha256(example).hexdigest() == INPUT_SHA256, 'triage example byte drift'
    parse_input(example)


class TriageTests(unittest.TestCase):
    def setUp(self):
        self.document = envelope()
        self.fact = self.document['facts'][0]
        self.bindings = self.document['bindings']

    def report(self, facts, bindings=None):
        return triage(facts, bindings=self.bindings if bindings is None else bindings)

    def test_vectors(self):
        run_triage_vectors()

    def test_persistent_conflict_order_variants_and_comparison_only(self):
        a = self.fact
        b = dict(copy.deepcopy(a), amount=999, method='sim-other-method')
        c = dict(copy.deepcopy(a), operation='sim-unbound-op', offset='+09:00')
        other = dict(copy.deepcopy(a), item_key='sim-other')
        facts = [a, other, b, a, b, c]
        result = self.report(facts)
        group = result['groups'][0]
        self.assertEqual(group['delivery_indices'], [0, 2, 3, 4, 5])
        self.assertEqual(group['reference_role'], 'COMPARISON_ONLY')
        self.assertEqual(group['reference_delivery_index'], 0)
        self.assertEqual(group['status'], 'CONFLICT')
        self.assertEqual(group['binding_status'], 'MATCHED_FIXTURE')
        self.assertEqual([v['delivery_indices'] for v in group['variants']], [[0, 3], [2, 4], [5]])
        self.assertEqual([d['fold_classification'] for d in result['deliveries']],
                         ['FIRST', 'FIRST', 'CONFLICT', 'DUPLICATE', 'CONFLICT', 'CONFLICT'])
        self.assertEqual(result['deliveries'][4]['redelivery_reason_code'], 'IDENTICAL_REDELIVERY')
        self.assertEqual(group['conflicts'][0]['differences'], [
            dict(field='amount', reference_value=1000, incoming_value=999),
            dict(field='method', reference_value='sim-card', incoming_value='sim-other-method')])
        self.assertEqual([v['binding']['status'] for v in group['variants']],
                         ['MATCHED_FIXTURE', 'MATCHED_FIXTURE', 'UNMATCHED'])
        for fact, delivery in zip(facts, result['deliveries']):
            key = {n: fact[n] for n in ('provider', 'account', 'environment', 'profile_version', 'item_key')}
            material = json.dumps(dict(profile='LOCAL_SYNTHETIC_JSON_SHA256_V1', key=key),
                                  sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
            self.assertEqual(delivery['event_item_id'], 'sim-event-' + hashlib.sha256(material).hexdigest())
            self.assertEqual(delivery['transmission'], fact['transmission'])
        reversed_group = self.report([b, a])['groups'][0]
        self.assertEqual(reversed_group['variants'][0]['normalized_fact']['amount'], 999)
        self.assertEqual(reversed_group['conflicts'][0]['differences'][0]['reference_value'], 999)
        self.assertEqual(self.report([a, b, a])['groups'][0]['status'], 'CONFLICT')
        changed_b = dict(b, transmission=dict(b['transmission'], id='sim-new'))
        repeated = self.report([a, b, changed_b])['deliveries'][2]
        self.assertEqual(repeated['fold_classification'], 'CONFLICT')
        self.assertEqual(repeated['redelivery_reason_code'], 'TRANSMISSION_METADATA_CHANGED')

    def test_every_normalized_content_field_and_scope(self):
        for field in FIELDS:
            if field == 'currency':  # Existing schema accepts KRW only.
                continue
            changed = dict(copy.deepcopy(self.fact), **{field: 7 if field == 'amount' else 'sim-changed'})
            with self.subTest(field=field):
                groups = self.report([self.fact, changed])['groups']
                if field in ('provider', 'account', 'environment', 'profile_version'):
                    self.assertEqual(len(groups), 2)
                else:
                    self.assertEqual(len(groups), 1)
                    self.assertEqual(groups[0]['conflicts'][0]['differences'],
                                     [dict(field=field, reference_value=self.fact[field], incoming_value=changed[field])])

    def test_each_transmission_field_is_metadata_not_content(self):
        for field in ('id', 'received_at', 'raw_evidence_ref'):
            changed = copy.deepcopy(self.fact)
            changed['transmission'][field] = 'sim-changed'
            result = self.report([self.fact, self.fact, changed, changed])
            self.assertEqual([d['reason_code'] for d in result['deliveries']],
                             ['FIRST_OBSERVATION', 'IDENTICAL_REDELIVERY',
                              'TRANSMISSION_METADATA_CHANGED', 'IDENTICAL_REDELIVERY'])
            self.assertEqual(len(result['groups'][0]['variants']), 1)
            self.assertEqual(result['groups'][0]['conflicts'], [])

    def test_binding_absence_mismatch_and_per_variant_lookup(self):
        for fields in (('payment_key',), ('order_id',), ('payment_key', 'order_id')):
            b = dict(self.bindings[0], **{f: 'sim-mismatch' for f in fields})
            group = self.report([self.fact], [b])['groups'][0]
            self.assertEqual(group['status'], 'BINDING_CONFLICT')
            explanation = group['variants'][0]['binding']
            self.assertEqual(explanation['supplied_binding'], b)
            self.assertEqual([d['field'] for d in explanation['differences']], list(fields))
        group = self.report([self.fact], [])['groups'][0]
        self.assertEqual(group['status'], 'UNMATCHED')
        self.assertIsNone(group['variants'][0]['binding']['supplied_binding'])
        changed = dict(self.fact, payment_key='sim-mismatch')
        group = self.report([self.fact, changed])['groups'][0]
        self.assertEqual(group['binding_status'], 'MATCHED_FIXTURE')
        self.assertEqual(group['variants'][1]['binding']['status'], 'BINDING_CONFLICT')

    def test_fold_once_detached_and_deterministic(self):
        calls = []
        class Spy(LocalFakeObservation):
            def fold(inner, facts, *, bindings):
                calls.append((facts, bindings))
                output = super().fold(facts, bindings=bindings)
                facts.clear()
                bindings.clear()
                return output
        before = copy.deepcopy(self.document)
        result = triage(self.document['facts'], bindings=self.bindings, observation_port=Spy())
        self.assertEqual(len(calls), 1)
        self.assertEqual(before, self.document)
        self.assertEqual(result, self.report(self.document['facts']))
        self.assertEqual(serialize(result), serialize(self.report([dict(reversed(list(self.fact.items())))])))
        self.assertTrue(serialize(result).endswith(b'\n'))
        result['groups'][0]['variants'][0]['normalized_fact']['amount'] = 0
        self.assertEqual(self.fact['amount'], 1000)
        empty = self.report([], [])
        self.assertEqual(empty['groups'], [])
        self.assertEqual(empty['deliveries'], [])
        for report in (empty, self.report([self.fact])):
            self.assertEqual(report['label'], 'SIMULATED')
            self.assertIs(report['applied'], False)
            self.assertIs(report['funds_executed'], False)
            self.assertIs(report['semantic_conformance'], False)
            self.assertEqual(report['binding_status'], 'NOT_BOUND')
            self.assertEqual(report['applied_effects'], [])

    def test_adapter_contract_drift_and_failure(self):
        changes = [lambda r: r.update(applied=True), lambda r: r.update(funds_executed=0),
                   lambda r: r.update(identity_profile='other'), lambda r: r.update(deliveries=[]),
                   lambda r: r['event_items'][0].update(status='UNMATCHED'),
                   lambda r: r['event_items'][0].update(event_item_id='bad'),
                   lambda r: r['duplicates'][0].update(delivery_index=True),
                   lambda r: r['conflicts'].clear(), lambda r: r.update(applied_effects=['effect']),
                   lambda r: r['deliveries'].reverse(), lambda r: r.update(extra=1)]
        facts = [self.fact, self.fact, dict(self.fact, amount=3, transmission=dict(self.fact['transmission'], id='sim-3'))]
        for change in changes:
            class Drift(LocalFakeObservation):
                def fold(inner, facts, *, bindings):
                    result = super().fold(facts, bindings=bindings)
                    change(result)
                    return result
            with self.subTest(change=change), self.assertRaises(ContractError):
                triage(facts, bindings=self.bindings, observation_port=Drift())
        class Broken:
            def fold(self, facts, *, bindings):
                raise RuntimeError('sensitive internal detail')
        with self.assertRaisesRegex(ContractError, '^observation adapter failed$'):
            triage([], bindings=[], observation_port=Broken())

    def test_populated_service_is_unchanged(self):
        from capital.service import CapitalService
        from test_overlay import draw_book, tick
        service = CapitalService()
        draw_book(service)
        tick(service, 'sim-triage-tick', 0, 1)
        def snapshot():
            return copy.deepcopy((service.machine.canonical_state(), service.machine.export_journal(),
                service.receipts, service.overlay_state(), service.overlay_entries))
        before = snapshot()
        for case in json.loads((VECTORS / 'cases.json').read_text())['cases']:
            triage(case['input']['facts'], bindings=case['input']['bindings'])
        self.assertEqual(before, snapshot())


class ParsingTests(unittest.TestCase):
    def test_reject_before_fold(self):
        document = envelope()
        bad_documents = [None, [], {}, dict(document, extra=1), dict(document, label='REAL'),
                         dict(document, format='other'), dict(document, bindings=None),
                         dict(document, facts={}), {k: v for k, v in document.items() if k != 'bindings'}]
        for change in ({'amount': True}, {'amount': 1.0}, {'amount': -1}, {'currency': 'USD'},
                       {'offset': 5}, {'offset': ''}, {'item_key': ''}, {'provenance': 'REAL'},
                       {'extra': 0}, {'method': '\ud800'}, {'transmission': {}}, {'product': 'x' * 4097}):
            bad_documents.append(dict(document, facts=[dict(document['facts'][0], **change)]))
        for bindings in ([{}], [None], [dict(document['bindings'][0], extra=1)],
                         [dict(document['bindings'][0], operation='')],
                         document['bindings'] + [dict(document['bindings'][0], order_id='sim-other')]):
            bad_documents.append(dict(document, bindings=bindings))
        with patch.object(LocalFakeObservation, 'fold', side_effect=AssertionError('must not fold')):
            for body in bad_documents:
                with self.subTest(body=repr(body)[:100]), self.assertRaises(InputError):
                    parse_input(json.dumps(body).encode())
        raws = [b'{', b'\xff', b'\xef\xbb\xbf{}', b'{}\0', b'{"x":NaN}', b'{"x":Infinity}',
                b'{"a":1,"a":2}', b'{"x":{"a":1,"a":2}}', b'[' * 2000 + b']' * 2000,
                b'{"x":' + b'1' * 5000 + b'}', b'{} {}', b'{"x":1e9999}']
        for raw in raws:
            with self.subTest(raw=raw[:60]), self.assertRaises(InputError):
                parse_input(raw)

    def test_resource_boundaries(self):
        document = envelope()
        document['facts'][0]['product'] = 'x' * 4096
        validate(document)
        document['facts'] = [envelope()['facts'][0]] * 256
        validate(document)
        document['facts'].append(document['facts'][0])
        with self.assertRaises(InputError):
            validate(document)
        document = envelope(facts=[])
        document['bindings'] *= 256
        validate(document)
        document['bindings'].append(document['bindings'][0])
        with self.assertRaises(InputError):
            validate(document)
        raw = json.dumps(envelope(facts=[], bindings=[])).encode()
        parse_input(raw + b' ' * (MAX_BYTES - len(raw)))
        with self.assertRaises(InputError):
            parse_input(raw + b' ' * (MAX_BYTES + 1 - len(raw)))
        from capital.observation_triage import _tree
        nested = None
        for _ in range(7):
            nested = [nested]
        _tree(nested)
        with self.assertRaises(InputError):
            _tree([nested])
        huge = envelope(facts=[dict(envelope()['facts'][0], product='x' * 4096)] * 64)
        with self.assertRaises(InputError):
            validate(huge)
        raw = json.dumps(envelope(), ensure_ascii=False).replace('sim-product', '합성').encode()
        self.assertEqual(parse_input(raw)['facts'][0]['product'], '합성')


class CliTests(unittest.TestCase):
    command = [sys.executable, str(ROOT / 'scripts/observation_triage.py')]

    def test_stdout_exit_codes_and_no_workspace_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'input.json'
            path.write_bytes((VECTORS / 'input.json').read_bytes())
            (root / 'workspace.json').write_bytes(b'synthetic existing workspace sentinel')
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            run = subprocess.run(self.command + ['--input', str(path)], cwd=root, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            document = parse_input(path.read_bytes())
            self.assertEqual(run.stdout, serialize(triage(document['facts'], bindings=document['bindings'])))
            self.assertEqual(run.stderr, b'')
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})
            for raw in (b'{', b'{"a":1,"a":1}', b'x' * (MAX_BYTES + 1)):
                path.write_bytes(raw)
                self.check_error(['--input', str(path)], 1, 'INVALID_INPUT')
            self.check_error(['--input', str(root / 'missing')], 1, 'INVALID_INPUT')
            self.check_error(['--input', str(root)], 1, 'INVALID_INPUT')
            fifo = root / 'fifo'
            os.mkfifo(fifo)
            self.check_error(['--input', str(fifo)], 1, 'INVALID_INPUT')
            self.check_error(['--input', 'https://example.invalid/facts'], 1, 'INVALID_INPUT')
        for args in ([], ['--input'], ['--input', 'x', '--output', 'y']):
            self.check_error(args, 2, 'ARGUMENT_ERROR')

    def check_error(self, args, code, error):
        run = subprocess.run(self.command + args, capture_output=True, timeout=10)
        self.assertEqual(run.returncode, code, run.stderr)
        self.assertEqual(run.stdout, b'')
        body = json.loads(run.stderr)
        self.assertEqual(body['error_code'], error)
        self.assertEqual(body['label'], 'SIMULATED')
        self.assertIs(body['applied'], False)
        self.assertIs(body['funds_executed'], False)

    def test_internal_exit_code_and_serialization_before_stdout(self):
        code = ("import runpy,sys; from unittest.mock import patch; "
                "m=runpy.run_path(sys.argv[1]); "
                "m['main'].__globals__['triage']=lambda *a,**k: set(); "
                "sys.exit(m['main'](['--input',sys.argv[2]]))")
        run = subprocess.run([sys.executable, '-c', code, str(ROOT / 'scripts/observation_triage.py'),
                              str(VECTORS / 'input.json')], capture_output=True)
        self.assertEqual(run.returncode, 3, run.stderr)
        self.assertEqual(run.stdout, b'')
        self.assertEqual(json.loads(run.stderr)['error_code'], 'INTERNAL_ERROR')
        code = code.replace("lambda *a,**k: set()", "lambda *a,**k: (_ for _ in ()).throw(m['ContractError']('adapter failed'))")
        run = subprocess.run([sys.executable, '-c', code, str(ROOT / 'scripts/observation_triage.py'),
                              str(VECTORS / 'input.json')], capture_output=True)
        self.assertEqual(run.returncode, 3, run.stderr)
        self.assertEqual(run.stdout, b'')
        self.assertEqual(json.loads(run.stderr)['error_code'], 'ADAPTER_CONTRACT_ERROR')

    def test_vector_checker_drift_controls(self):
        command = [sys.executable, str(ROOT / 'scripts/observation_triage_vectors.py'), '--check']
        run = subprocess.run(command, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'cases.json'
            for data in (b'{', b'{}', (VECTORS / 'cases.json').read_bytes().replace(b'CONFLICT', b'UNMATCHED')):
                path.write_bytes(data)
                self.assertEqual(subprocess.run(command + ['--file', str(path)], capture_output=True).returncode, 1)
            self.assertEqual(subprocess.run(command + ['--file', str(path.parent / 'missing')], capture_output=True).returncode, 1)


if __name__ == '__main__':
    unittest.main()
