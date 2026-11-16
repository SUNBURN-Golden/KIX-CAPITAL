"""Independent contribution evaluation and adversarial historical evidence checks."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from capital import audit, evidence, store
from capital.producer import DEMO_BOOK_PROFILE
from capital.service import CapitalService
from capital.statement_trace import dump, trace_workspace, trace_workspace_bytes
from scripts.statement_trace_vectors import build_vectors, command, ready, scene

ROOT = Path(__file__).resolve().parents[1]
VECTORS = ROOT / 'tests' / 'vectors' / 'statement_trace'


def resolve(document, pointer):
    value = document
    if not pointer:
        return value
    assert pointer.startswith('/')
    for token in pointer[1:].split('/'):
        token = token.replace('~1', '/').replace('~0', '~')
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def numeric_leaves(value, path=''):
    # Independent traversal; bool must not count as a statement amount.
    result = {}
    if isinstance(value, bool):
        return result
    if isinstance(value, (int, float)):
        return {path: value}
    items = value.items() if isinstance(value, dict) else enumerate(value) if isinstance(value, list) else []
    for key, item in items:
        escaped = str(key).replace('~', '~0').replace('/', '~1')
        result.update(numeric_leaves(item, path + '/' + escaped))
    return result


def evaluate(test, report):
    """No production aggregation/evaluation helper is used here."""
    test.assertTrue(report['ok'], report)
    statement, provenance = report['statement'], report['provenance']
    roots = provenance['roots']
    test.assertEqual(set(provenance['fields']), set(numeric_leaves(statement)))
    evaluated = {}
    for target, field in provenance['fields'].items():
        for ref in field['sources'] + field['journal'] + field['receipts'] + field['validated_receipt_fields']:
            resolve(roots[ref['root']], ref['pointer'])
        test.assertTrue(field['witnesses'])
        for witness_id in field['witnesses']:
            witness = provenance['witnesses'][witness_id]
            test.assertEqual(witness['target'], {'root': 'statement', 'pointer': target})
            amount = 0
            for term in witness['terms']:
                ref = term['source']
                value = resolve(roots[ref['root']], ref['pointer'])
                test.assertIs(type(value), int)
                test.assertIs(type(term['sign']), int)
                test.assertIn(term['sign'], (-1, 1))
                amount += value * term['sign']
            test.assertEqual(amount, resolve(statement, target), target)
            test.assertEqual(amount, witness['computed'])
            test.assertEqual(amount, witness['statement_value'])
            test.assertEqual(witness['status'], 'MATCHED')
            evaluated[target] = amount
    return evaluated


def rehash(document):
    document['payload_sha256'] = store._checksum(document['payload'])
    return dump(document)


def report(name='lifecycle'):
    return trace_workspace_bytes(dump(scene(name)))


def envelope_for(service):
    return store.envelope('trace-test', {
        'journal': service.machine.export_journal(), 'receipts': copy.deepcopy(service.receipts),
        'case_fixtures': dict(service.case_fixtures), 'state_digest': service.machine.state_digest()})


class ContributionTests(unittest.TestCase):
    def test_reconstruct_every_numeric_field_and_all_five_totals(self):
        result = report()
        actual = evaluate(self, result)
        expected = {
            '/categories/0/total': 190000,
            '/categories/1/drawn': 190000, '/categories/1/repaid': 60000,
            '/categories/1/outstanding': 130000, '/categories/2/total': 130000,
            '/categories/3/confirmed': 12658694000, '/categories/3/distributed': 0,
            '/categories/4/refund_face': 60010000, '/categories/4/refund_accepted': 0,
            '/categories/4/refund_outstanding': 60010000,
        }
        for target, amount in expected.items():
            self.assertEqual(actual[target], amount)
        for index, (drawn, repaid, outstanding, confirmed) in enumerate((
                (60000, 60000, 0, 97000), (30000, 0, 30000, 97000),
                (100000, 0, 100000, 2910000000))):
            for key, amount in zip(('drawn', 'repaid', 'outstanding', 'confirmed_cash_on_face'),
                                   (drawn, repaid, outstanding, confirmed)):
                self.assertEqual(actual[f'/categories/1/rows/{index}/{key}'], amount)
        self.assertEqual([c['id'] for c in result['statement']['categories']],
                         ['approved', 'exposure', 'reserved', 'settlement', 'refund'])
        # Hand-authored fixture expectations, independent of FixtureViews and
        # both production statement/provenance aggregators.
        confirmed_by_fixture = {
            'demo-alpha-arena': 2910000000, 'demo-alpha-hall': 1164000000,
            'demo-beta-club': 0, 'demo-beta-festival': 3880000000,
            'demo-delta-mid': 0, 'demo-delta-small': 48500000,
            'demo-epsilon-clean': 1940000000, 'demo-epsilon-refund': 388000000,
            'demo-gamma-annex': 2328000000, 'demo-gamma-tour': 0,
            'sim-committed': 97000, 'sim-pending': 0, 'sim-refund': 97000,
        }
        for index, fixture in enumerate(sorted(confirmed_by_fixture)):
            self.assertEqual(actual[f'/categories/3/rows/{index}/confirmed_cash'],
                             confirmed_by_fixture[fixture])
            self.assertEqual(actual[f'/categories/3/rows/{index}/distributed_cash'], 0)
            refund = {'sim-refund': 10000, 'demo-epsilon-refund': 60000000}.get(fixture, 0)
            for field, expected_amount in (('refund_face', refund), ('refund_accepted', 0),
                                            ('refund_outstanding', refund)):
                self.assertEqual(actual[f'/categories/4/rows/{index}/{field}'], expected_amount)
        for index, amount in enumerate((60000, 30000, 100000)):
            self.assertEqual(actual[f'/categories/0/rows/{index}/amount'], amount)
        for index, amount in enumerate((30000, 30000, 100000)):
            self.assertEqual(actual[f'/categories/2/rows/{index}/reserved_open'], amount)

    def test_independent_evaluator_rejects_missing_and_malformed_witnesses(self):
        baseline = report('empty')
        changed = copy.deepcopy(baseline)
        changed['provenance']['fields'].pop('/operation_capacity')
        with self.assertRaises(AssertionError):
            evaluate(self, changed)
        changed = copy.deepcopy(baseline)
        changed['provenance']['witnesses']['w0']['terms'][0]['sign'] = True
        with self.assertRaises(AssertionError):
            evaluate(self, changed)
        changed = copy.deepcopy(baseline)
        changed['provenance']['witnesses']['w0']['terms'][0]['source']['pointer'] = '/missing'
        with self.assertRaises(KeyError):
            evaluate(self, changed)

    def test_empty_and_nonapproved_cases(self):
        evaluate(self, report('empty'))
        service = CapitalService()
        command(service, 'offer', 'sim-offer', 'offer-only', fixture_id='sim-committed', amount=1000)
        command(service, 'offer', 'sim-cancel', 'cancel-offer', fixture_id='sim-pending', amount=2000)
        command(service, 'cancel', 'sim-cancel', 'cancel')
        command(service, 'offer', 'sim-reject', 'reject-offer', fixture_id='sim-pending', amount=3000)
        command(service, 'reject', 'sim-reject', 'reject')
        result = trace_workspace_bytes(dump(envelope_for(service)))
        actual = evaluate(self, result)
        for target in ('/categories/0/total', '/categories/1/drawn', '/categories/1/repaid',
                       '/categories/1/outstanding', '/categories/2/total'):
            self.assertEqual(actual[target], 0)

    def test_shared_claim_reservation_and_cash_count_once(self):
        shared, lifecycle, empty = report('shared-claim'), report(), report('empty')
        self.assertEqual(shared['statement']['categories'][2]['total'], 90000)
        self.assertEqual([r['reserved_open'] for r in shared['statement']['categories'][2]['rows']], [90000, 90000])
        self.assertEqual(lifecycle['statement']['categories'][2]['total'], 130000)
        for result in (shared, lifecycle):
            evaluate(self, result)
            for index in (3, 4):
                self.assertEqual(result['statement']['categories'][index], empty['statement']['categories'][index])
                self.assertEqual(len(result['statement']['categories'][index]['rows']), 13)
        witness = lifecycle['provenance']['witnesses'][lifecycle['provenance']['fields']['/categories/2/total']['witnesses'][0]]
        self.assertEqual([t['sign'] for t in witness['terms']], [1, 1, -1, 1])
        self.assertEqual(len({(t['journal_index'], t['sign']) for t in witness['terms']}), 4)

    def test_full_repayment_retains_reservation_until_close(self):
        service = CapitalService()
        ready(service, 'sim-a', 60000)
        ready(service, 'sim-b', 30000)
        command(service, 'repay', 'sim-a', 'a-full', amount=60000, sequence=1)
        before = trace_workspace_bytes(dump(envelope_for(service)))
        self.assertEqual(evaluate(self, before)['/categories/2/total'], 90000)
        command(service, 'close', 'sim-a', 'a-close')
        after = trace_workspace_bytes(dump(envelope_for(service)))
        self.assertEqual(evaluate(self, after)['/categories/2/total'], 30000)

    def test_demo_labels_follow_cases_fixtures_and_terms(self):
        result = report()
        provenance = result['provenance']
        demo_case = provenance['roots']['cases']['sim-demo']
        demo_fixture = provenance['roots']['fixtures']['demo-alpha-arena']
        terms = [term for witness in provenance['witnesses'].values() for term in witness['terms']
                 if term.get('profile_version') == DEMO_BOOK_PROFILE]
        self.assertTrue(terms)
        for item in [demo_case, demo_fixture] + terms:
            self.assertEqual(item['label'], 'SYNTHETIC_FIXTURE_PROFILE')
            self.assertEqual(item['profile_version'], DEMO_BOOK_PROFILE)
            self.assertEqual(item['source_classification'], 'READ_ONLY_FIXTURE')
            self.assertIs(item['policy_adopted'], False)
            self.assertIs(item['funds_executed'], False)
            self.assertEqual(item['units'], 'SYNTHETIC_KRW_INTEGER')
            self.assertEqual(item['roles'], 'SYNTHETIC_ROLES')
        self.assertEqual(demo_case['classification'], 'F04_CASE_EVIDENCE')

    def test_unavailable_sales_payments_and_external_evidence(self):
        result = report()
        gaps = result['statement']['not_bound']
        self.assertEqual([g['id'] for g in gaps], ['primary_sales', 'resale_sales', 'actual_paid'])
        for gap in gaps + result['provenance']['not_bound']:
            self.assertEqual(gap['status'], 'NOT_BOUND')
            self.assertFalse(numeric_leaves(gap))
        self.assertFalse(result['funds_executed'])
        self.assertFalse(result['workspace_mutated'])

    def test_statement_is_exact_existing_builder_output_and_hashes_match(self):
        document = scene('lifecycle')
        raw = dump(document)
        result = trace_workspace_bytes(raw)
        service = evidence.offline_service(document)
        self.assertEqual(result['statement'], service.statement())
        hashes = result['provenance']['hashes']
        self.assertEqual(hashes['workspace_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(hashes['payload_sha256'], document['payload_sha256'])
        self.assertEqual(hashes['state_digest'], document['payload']['state_digest'])
        for key, value in (('fixture_inputs_sha256', result['provenance']['fixture_inputs']),
                           ('statement_sha256', result['statement'])):
            self.assertEqual(hashes[key], hashlib.sha256(store.canonical_bytes(value)).hexdigest())


class ReceiptTests(unittest.TestCase):
    def test_historical_receipts_are_checked_against_their_prefix(self):
        result = report()
        self.assertTrue(result['ok'])
        roots = result['provenance']['roots']
        # The first draw receipt precedes repayment, sibling draw and close.
        historic = roots['receipts']['sim-a-draw']['receipt']['result']['credit']
        final = roots['cases']['sim-a']['view']
        self.assertEqual((historic['drawn_exposure'], historic['repaid_exposure'], historic['reserved_open']),
                         (60000, 0, 60000))
        self.assertEqual((final['repaid_exposure'], final['reserved_open']), (60000, 30000))
        for check in result['provenance']['receipt_checks']:
            if check['journal_index'] is not None:
                self.assertEqual(check['prefix_length'], check['journal_index'] + 1)
                self.assertEqual(check['status'], 'MATCHED')
                for item in check['checked']:
                    left, right = item['receipt'], item['expected']
                    actual = resolve(roots[left['root']], left['pointer'])
                    replayed = resolve(roots[right['root']], right['pointer'])
                    self.assertIs(type(actual), type(replayed))
                    self.assertEqual(actual, replayed)

    def test_rehashed_contradictory_known_receipt_details_fail_after_audit_passes(self):
        mutations = [
            ('sim-a-draw', ['credit', 'drawn_exposure'], 60001),
            ('sim-a-draw', ['credit', 'amount'], True),
            ('a-close', ['credit', 'reserved_open'], 0),
            ('a-close', ['effect', 'outstanding_exposure'], 1),
            ('b-default', ['credit', 'phase'], 'CLOSED'),
            ('b-default', ['effect', 'outstanding_exposure'], 0),
            ('b-default', ['credit', 'outstanding_exposure'], 1),
            ('a-final', ['credit', 'repayments', 0, 'amount'], 1),
            ('a-final', ['credit', 'repayments', 0, 'sequence'], 2),
            ('sim-a-draw', ['credit', 'draw_id'], 'wrong'),
            ('sim-a-draw', ['credit', 'settlement_gate'], 'wrong'),
            ('sim-a-draw', ['credit', 'note_status'], 'RELEASED'),
            ('sim-a-draw', ['credit', 'claim_id'], 'sim-pending'),
            ('sim-a-draw', ['credit', 'confirmed_cash_on_face'], 0),
            ('sim-a-draw', ['credit', 'beneficiary_role'], 'wrong'),
            ('sim-a-draw', ['applied'], 'repay'),
            ('sim-a-draw', ['duplicate'], True),
            ('sim-a-draw', ['effect'], None),
            ('sim-a-draw', ['credit'], []),
            ('sim-a-draw', [], None),
        ]
        baseline = scene('lifecycle')
        for key, parts, value in mutations:
            with self.subTest(key=key, path=parts):
                document = copy.deepcopy(baseline)
                receipt = document['payload']['receipts'][key]['receipt']
                if parts:
                    parent = receipt['result']
                    for part in parts[:-1]:
                        parent = parent[part]
                    parent[parts[-1]] = value
                else:
                    receipt['result'] = value
                raw = rehash(document)
                self.assertTrue(audit.audit_workspace_bytes(raw, workspace='test')['ok'])
                result = trace_workspace_bytes(raw)
                self.assertFalse(result['ok'])
                self.assertEqual(result['reason'], 'RECEIPT_RESULT_MISMATCH')
                self.assertEqual(result['detail']['operation_id'], key)
                self.assertIsNone(result['statement'])
                self.assertIsNone(result['provenance'])

    def test_missing_optional_details_not_fabricated_unknown_extensions_unvalidated(self):
        document = scene('optional-detail')
        # A wholly absent result and nested optional fields remain unavailable.
        document['payload']['receipts']['sim-b-draw']['receipt'].pop('result')
        document['payload']['receipts']['sim-a-offer']['receipt']['result']['credit'].pop('note_status')
        result = trace_workspace_bytes(rehash(document))
        evaluate(self, result)
        checks = {r['operation_id']: r for r in result['provenance']['receipt_checks']}
        for key, pointer in (
                ('sim-a-draw', '/sim-a-draw/receipt/result/credit'),
                ('sim-b-draw', '/sim-b-draw/receipt/result'),
                ('sim-a-offer', '/sim-a-offer/receipt/result/credit/note_status')):
            self.assertIn({'root': 'receipts', 'pointer': pointer, 'status': 'NOT_BOUND',
                           'reason': 'OPTIONAL_DETAIL_ABSENT'}, checks[key]['unavailable'])
        self.assertIn({'root': 'receipts', 'pointer': '/sim-a-draw/receipt/result/extension'},
                      checks['sim-a-draw']['unvalidated'])
        receipts = result['provenance']['roots']['receipts']
        self.assertNotIn('credit', receipts['sim-a-draw']['receipt']['result'])
        self.assertNotIn('result', receipts['sim-b-draw']['receipt'])
        self.assertEqual(receipts, document['payload']['receipts'])
        for witness in result['provenance']['witnesses'].values():
            for term in witness['terms']:
                self.assertNotIn(term['source']['root'], ('receipts', 'historical_replay'))

    def test_existing_audit_required_details_are_still_required(self):
        for key, field in (('sim-a-offer', 'amount'), ('a-final', 'repayments')):
            with self.subTest(field=field):
                document = scene('lifecycle')
                document['payload']['receipts'][key]['receipt']['result']['credit'].pop(field)
                result = trace_workspace_bytes(rehash(document))
                self.assertFalse(result['ok'])
                self.assertEqual(result['reason'], 'RECON_MISMATCH')
                self.assertIsNone(result['provenance'])

    def test_rejected_and_reconcile_receipts_have_no_inferred_case_association(self):
        result = report()
        checks = {c['operation_id']: c for c in result['provenance']['receipt_checks']}
        for key in ('bad-offer', 'demo-reconcile'):
            self.assertEqual(checks[key]['status'], 'NOT_BOUND')
            self.assertEqual(checks[key]['case_association'], 'NOT_BOUND')
            self.assertFalse(checks[key]['contributes_amounts'])
            self.assertIsNone(checks[key]['journal_index'])

    def test_original_receipts_preserved_without_restore_added_role_labels(self):
        document = scene('shared-claim')
        for stored in document['payload']['receipts'].values():
            stored['receipt'].pop('role', None)
            stored['receipt'].pop('role_provenance', None)
        result = trace_workspace_bytes(rehash(document))
        self.assertTrue(result['ok'])
        self.assertEqual(result['provenance']['roots']['receipts'], document['payload']['receipts'])


class CaptureAndFailureTests(unittest.TestCase):
    def test_single_capture_survives_file_replacement(self):
        raw = dump(scene('shared-claim'))
        real_audit = audit.audit_workspace_bytes
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / store.FILE_NAME
            path.write_bytes(raw)
            reads = []
            original_read = Path.read_bytes

            def read_once(current):
                if current == path:
                    reads.append(current)
                return original_read(current)

            def replace(captured, **kwargs):
                path.write_bytes(b'replaced after capture')
                return real_audit(captured, **kwargs)

            with patch.object(Path, 'read_bytes', read_once), patch.object(audit, 'audit_workspace_bytes', replace):
                result = trace_workspace(tmp)
            self.assertEqual(reads, [path])
            self.assertTrue(result['ok'])
            self.assertEqual(result['provenance']['hashes']['workspace_sha256'], hashlib.sha256(raw).hexdigest())

    def test_success_and_failure_leave_all_source_names_bytes_modes_unchanged(self):
        for name in ('lifecycle', 'tampered-input'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / store.FILE_NAME
                path.write_bytes(dump(scene(name)))
                path.chmod(0o640)
                (Path(tmp) / 'events.jsonl').write_bytes(b'not an input')
                (Path(tmp) / 'keyset.json').write_bytes(b'not a key')
                snapshot = lambda: {p.name: (p.read_bytes(), p.stat().st_mode) for p in Path(tmp).iterdir()}
                before = snapshot()
                with patch.object(evidence._DocumentStorage, 'save', side_effect=AssertionError('save')):
                    result = trace_workspace(tmp)
                self.assertEqual(result['ok'], name == 'lifecycle')
                self.assertEqual(snapshot(), before)

    def test_existing_file_workspace_lock_does_not_block_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / store.FILE_NAME).write_bytes(dump(scene('shared-claim')))
            with store.FileWorkspace.open(tmp):
                self.assertTrue(trace_workspace(tmp)['ok'])

    def test_statement_and_detached_views_captured_under_service_lock_and_resources_closed(self):
        original = evidence.offline_service
        services = []

        def guarded(document):
            service = original(document)
            services.append(service)
            view = service.machine.view

            def checked_view(key):
                self.assertTrue(service.lock._is_owned())
                return view(key)

            service.machine.view = checked_view
            return service

        with patch.object(evidence, 'offline_service', guarded), patch.object(
                evidence._DocumentStorage, 'close') as close:
            self.assertTrue(report()['ok'])
            self.assertFalse(report('tampered-input')['ok'])
        self.assertEqual(len(services), 2)
        self.assertEqual(close.call_count, 2)

    def test_legacy_envelope_and_nonempty_overlay(self):
        document = scene('shared-claim')
        document.pop('overlay')
        document.pop('envelope_version')
        evaluate(self, trace_workspace_bytes(dump(document)))
        service = CapitalService()
        ready(service, 'sim-a', 1000)
        service.overlay_command({'instance_id': service.instance_id, 'operation_id': 'tick',
                                 'op': 'advance_day', 'from_sim_day': 0, 'to_sim_day': 1,
                                 'reason': 'statement trace test'}, role='organizer')
        self.assertTrue(service.overlay_entries)
        evaluate(self, trace_workspace_bytes(dump(service.storage.load())))

    def test_malformed_checksum_linkage_and_state_fail_diagnostically(self):
        inputs = [None, b'{', b'{"a":1,"a":2}', b'[]']
        original = scene('shared-claim')
        checksum = copy.deepcopy(original)
        checksum['payload']['state_digest'] = '0' * 64
        inputs.append(dump(checksum))
        missing_receipt = copy.deepcopy(original)
        missing_receipt['payload']['receipts'].pop('sim-a-draw')
        inputs.append(rehash(missing_receipt))
        mapping = copy.deepcopy(original)
        mapping['payload']['case_fixtures']['sim-a'] = 'missing'
        inputs.append(rehash(mapping))
        journal = copy.deepcopy(original)
        journal['payload']['journal'][0]['body']['amount'] = 1
        inputs.append(rehash(journal))
        for raw in inputs:
            with self.subTest(raw=raw[:50] if raw else raw):
                result = trace_workspace_bytes(raw)
                self.assertFalse(result['ok'])
                self.assertTrue(result['reason'])
                self.assertTrue(result['failed_check'])
                self.assertIsNone(result['statement'])
                self.assertIsNone(result['provenance'])
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(trace_workspace(Path(tmp) / 'absent')['ok'])
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_conflicting_sibling_reservations_fail(self):
        original = evidence.offline_service

        def inconsistent(document):
            service = original(document)
            view = service.machine.view

            def changed(case):
                result = view(case)
                if case == 'sim-b':
                    result['reserved_open'] += 1
                return result

            service.machine.view = changed
            return service

        with patch.object(evidence, 'offline_service', inconsistent):
            result = report('shared-claim')
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'INCONSISTENT_CLAIM_RESERVATION')

    def test_references_escape_slashes_and_tildes(self):
        # Historical fixture envelopes may carry pinned keys outside facade ID syntax.
        from capital.statement_trace import _ref, _resolve
        ref = _ref('receipts', 'a/b~c', 'amount')
        self.assertEqual(ref['pointer'], '/a~1b~0c/amount')
        roots = {'receipts': {'a/b~c': {'amount': 7}}}
        self.assertEqual(_resolve(roots, ref), 7)
        self.assertEqual(resolve(roots['receipts'], ref['pointer']), 7)

    def test_cli_deterministic_bytes_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / store.FILE_NAME
            raw = dump(scene('shared-claim'))
            path.write_bytes(raw)
            argv = [sys.executable, str(ROOT / 'scripts' / 'statement_trace.py'), '--workspace', tmp]
            first = subprocess.run(argv, capture_output=True)
            second = subprocess.run(argv, capture_output=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(first.stdout, second.stdout)
            self.assertEqual(first.stdout, dump(trace_workspace_bytes(raw)))
            self.assertEqual(path.read_bytes(), raw)
            path.write_bytes(dump(scene('tampered-input')))
            failed = subprocess.run(argv, capture_output=True)
            self.assertEqual(failed.returncode, 1)
            self.assertEqual(json.loads(failed.stdout)['reason'], 'RECEIPT_RESULT_MISMATCH')
            misuse = subprocess.run(argv[:2], capture_output=True)
            self.assertEqual(misuse.returncode, 2)

    def test_pinned_corpus_and_check_mode_are_read_only(self):
        generated = build_vectors()
        self.assertEqual(set(generated), {p.name for p in VECTORS.iterdir()})
        for name, raw in generated.items():
            self.assertEqual((VECTORS / name).read_bytes(), raw, name)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'absent'
            result = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'statement_trace_vectors.py'),
                                     '--check', '--dir', str(target)], capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
