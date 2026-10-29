"""SIMULATED case dossiers: source parity, byte stability, role gates and vector drift."""
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

from capital import dossier, overlay
from capital.server import make_server
from capital.service import ApiError, CapitalService
from capital.store import FileWorkspace, canonical_bytes
from capital.terms import DecisionNoteTermsPolicy
from scripts import dossier_vectors
from tests.facade_schema import SchemaError, load_contract, validate
from tests.test_overlay import draw_book, seed, tick

BLOCKS = (*dossier.TERMS_BLOCKS, 'underwriting')


def read(service, advance='sim-a'):
    return service.dossier(advance, service.instance_id)


def numbers(value):
    if type(value) is int:
        return [value]
    if type(value) is dict:
        return [n for item in value.values() for n in numbers(item)]
    if type(value) is list:
        return [n for item in value for n in numbers(item)]
    return []


class DossierTests(unittest.TestCase):
    def check_schema(self, body):
        validate(body, {'$ref': '#/definitions/case_dossier'}, load_contract())

    def test_blocks_equal_sibling_readers_at_recorded_day(self):
        service = CapitalService()
        tick(service, 'before', 0, 3)
        draw_book(service)
        tick(service, 'after', 3, 12)
        body = read(service)
        row = service.overlay_state()['advances'][0]
        self.assertEqual(body['sim_day'], 12)
        self.assertEqual(row['draw_day'], 3)
        self.assertEqual(body['case'], service.machine.view('sim-a'))
        self.assertEqual(body['ledger_row'], row)
        self.assertEqual(body['allocation_quote'], {k: row[k] for k in ('allocation', 'fsm_repay', 'close_ready')})
        self.assertEqual(body['margin_status'], row['margin'])
        self.assertEqual(body['covenant_status'], service.covenants()['advances'][0])
        self.assertEqual(body['underwriting'], service.underwrite('sim-a', service.instance_id, 'DOSSIER_READ_ONLY', sim_day=12))
        subject = service._overlay_subjects(service.overlay_entries)[0]
        self.assertEqual(body['terms_line'], service.terms.overlay(body['case'], subject['claim'],
                         draw_day=3, as_of_day=12, expected_settlement_cash_day=None, gate=subject['gate']))
        self.assertEqual(body['overlay_rows']['entries'], [{'overlay_index': i, 'entry': row}
                         for i, row in enumerate(service.overlay_entries)
                         if row['payload'].get('advance_id') == 'sim-a' or row['kind'] in ('clock', 'terms_binding')])
        self.check_schema(body)

    def test_two_reads_identical_and_guard_holds(self):
        with tempfile.TemporaryDirectory() as tmp, FileWorkspace.open(tmp) as storage:
            service = CapitalService(storage)
            draw_book(service)
            tick(service, 'clock', 0, 8)
            def frozen():
                return (service._frozen(), service.machine.canonical_state(), len(service.machine.export_journal()),
                        overlay.state_digest(overlay.fold(service.overlay_entries)), service.snapshot()['operation_count'],
                        {p.name: p.read_bytes() for p in Path(tmp).iterdir()})
            before = frozen()
            with patch.object(storage, 'save', side_effect=AssertionError('read must not persist')):
                first, second = read(service), read(service)
            self.assertEqual(canonical_bytes(first), canonical_bytes(second))
            self.assertEqual(before, frozen())
            # Detachment prevents a response consumer from changing live evidence.
            first['receipt_chain']['journal'][0]['receipt']['outcome'] = 'tainted'
            first['overlay_rows']['entries'][0]['entry']['kind'] = 'tainted'
            self.assertEqual(canonical_bytes(second), canonical_bytes(read(service)))
            restored = CapitalService(storage)
            self.assertEqual(read(restored)['dossier_digest'], second['dossier_digest'])

    def test_digest_is_independently_recomputed_and_covers_content(self):
        service = seed.build_service()
        body = read(service, 'sim-defaulted')
        # Explicit recursive removal of the established volatile field set.
        from capital.export import VOLATILE_KEYS
        def stable(value):
            if type(value) is dict:
                return {k: stable(v) for k, v in value.items() if k not in VOLATILE_KEYS}
            if type(value) is list:
                return [stable(v) for v in value]
            return value
        material = stable({k: v for k, v in body.items() if k != 'dossier_digest'})
        self.assertEqual(body['dossier_digest'], hashlib.sha256(canonical_bytes(material)).hexdigest())
        for field in ('case', 'receipt_chain', 'underwriting', 'cut', 'settlement_evidence'):
            other = copy.deepcopy(body)
            other[field]['tampered'] = 'changed'
            self.assertNotEqual(dossier.digest(other), body['dossier_digest'], field)

    def test_seeded_receipts_and_fixtures_are_copied_without_case_inference(self):
        service = seed.build_service()
        journal = service.machine.export_journal()
        keys = {row['idempotency_key'] for row in journal}
        for advance, _, _ in seed.EXPECTED:
            body = read(service, advance)
            self.assertEqual(body['receipt_chain']['journal'], [
                {'journal_index': i, 'entry': row, 'receipt': service.receipts[row['idempotency_key']]['receipt']}
                for i, row in enumerate(journal) if row['advance_id'] == advance])
            self.assertEqual(body['workspace_receipts_without_journal_rows'], {
                'scope': 'WORKSPACE_WIDE', 'case_association': 'NOT_INFERRED',
                'rows': [{'idempotency_key': key, 'receipt': service.receipts[key]['receipt']}
                         for key in sorted(service.receipts) if key not in keys]})
            self.assertEqual(body['settlement_evidence']['rows'], [row for row in service.evidence()['rows']
                             if row['claim_id'] in (body['case']['claim_id'], body['case']['settlement_id'])])
            self.check_schema(body)
        self.assertEqual(read(service, 'sim-rejected')['ledger_row'], dossier.not_applicable_block('NOT_DRAWN'))

    def test_one_lock_covers_composition_and_serializes_clock_writer(self):
        service = CapitalService()
        draw_book(service)
        before = read(service)
        entered, release, attempted = threading.Event(), threading.Event(), threading.Event()
        results, errors = {}, []
        original = dossier.build
        def held(*args):
            entered.set()
            if not release.wait(5):
                raise AssertionError('reader was not released')
            return original(*args)
        def reader():
            try:
                results['reader'] = read(service)
            except BaseException as exc:
                errors.append(exc)
        def writer():
            attempted.set()
            try:
                results['writer'] = tick(service, 'concurrent-clock', 0, 1)
            except BaseException as exc:
                errors.append(exc)
        with patch('capital.dossier.build', side_effect=held):
            first, second = threading.Thread(target=reader), threading.Thread(target=writer)
            first.start()
            try:
                self.assertTrue(entered.wait(5))
                second.start()
                self.assertTrue(attempted.wait(5))
                self.assertNotIn('writer', results)
            finally:
                release.set()
                first.join(5)
                if second.ident is not None:
                    second.join(5)
                self.assertFalse(first.is_alive())
                self.assertFalse(second.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results['reader'], before)
        after = read(service)
        self.assertEqual(after['sim_day'], 1)
        self.assertNotEqual(after['dossier_digest'], before['dossier_digest'])

    def test_not_bound_blocks_have_no_numbers(self):
        service = CapitalService(terms=DecisionNoteTermsPolicy(Path('/NO_SUCH_NOTE.md')))
        draw_book(service)
        body = read(service)
        for key in BLOCKS:
            self.assertEqual(body[key]['status'], 'NOT_BOUND', key)
            self.assertEqual(numbers(body[key]), [], key)
        self.check_schema(body)

    def test_drawn_unbound_is_not_bound_not_not_drawn(self):
        service = seed.build_service()
        service.terms = DecisionNoteTermsPolicy(Path('/NO_SUCH_NOTE.md'))
        body = read(service, 'sim-unbound')
        self.assertTrue(body['drawn'])
        for key in BLOCKS:
            self.assertEqual(body[key]['status'], 'NOT_BOUND')
            self.assertEqual(numbers(body[key]), [])
        self.assertEqual(read(service, 'sim-rejected')['terms_line']['status'], 'NOT_BOUND')

    def test_not_bound_sibling_errors_are_labelled_other_errors_propagate(self):
        service = CapitalService()
        draw_book(service)
        del service.receipts['a-draw']['receipt']['result']['credit']['settlement_gate']
        body = read(service)
        for key in dossier.TERMS_BLOCKS:
            self.assertEqual(body[key], dossier.not_bound_block('draw receipt gate not found'))
        for method in ('overlay_state', 'covenants', '_overlay_subjects'):
            service = CapitalService()
            draw_book(service)
            with patch.object(service, method, side_effect=ApiError('NOT_BOUND', 400, {'reason': 'unavailable'})):
                for key in dossier.TERMS_BLOCKS:
                    self.assertEqual(read(service)[key], dossier.not_bound_block('unavailable'))
        with patch.object(service, 'overlay_state', side_effect=ApiError('READ_ONLY_INVARIANT', 500)):
            with self.assertRaisesRegex(ApiError, 'READ_ONLY_INVARIANT'):
                read(service)

    def test_underwriting_and_terms_line_not_bound_errors_are_labelled(self):
        service = CapitalService()
        draw_book(service)
        expected = read(service)
        with patch.object(service, 'underwrite', side_effect=ApiError('NOT_BOUND', 400)):
            body = read(service)
            self.assertEqual(body['underwriting'], dossier.not_bound_block('NOT_BOUND'))
            for key in dossier.TERMS_BLOCKS:
                self.assertEqual(body[key], expected[key])
            self.check_schema(body)
        with patch.object(service.terms, 'overlay', side_effect=ApiError(
                'NOT_BOUND', 400, {'reason': 'terms line unavailable'})):
            body = read(service)
            for key in dossier.TERMS_BLOCKS:
                self.assertEqual(body[key], dossier.not_bound_block('terms line unavailable'))
            self.assertEqual(body['underwriting'], expected['underwriting'])
            self.check_schema(body)
        for target, method in ((service, 'underwrite'), (service.terms, 'overlay')):
            with patch.object(target, method, side_effect=ApiError('READ_ONLY_INVARIANT', 500)):
                with self.assertRaisesRegex(ApiError, 'READ_ONLY_INVARIANT'):
                    read(service)

    def test_unknown_session_mutation_guard_and_schema_unknown_fields(self):
        service = CapitalService()
        draw_book(service)
        for advance, instance, code in (('missing', service.instance_id, 'CASE_NOT_FOUND'), ('sim-a', 'stale', 'SESSION_CHANGED')):
            with self.assertRaisesRegex(ApiError, code):
                service.dossier(advance, instance)
        with patch('capital.dossier.build', side_effect=lambda *args: service.receipts.clear()):
            with self.assertRaisesRegex(ApiError, 'READ_ONLY_INVARIANT'):
                read(service)
        service = seed.build_service()
        for path in ((), ('cut',), ('case',), ('allocation_quote',), ('terms_line',)):
            body = read(service, 'sim-unbound')
            node = body
            for key in path:
                node = node[key]
            node['unexpected'] = True
            with self.assertRaises(SchemaError):
                self.check_schema(body)


class VectorTests(unittest.TestCase):
    def test_pinned_dossiers_and_drift_detection(self):
        vectors = dossier_vectors.build_vectors()
        self.assertEqual(vectors, dossier_vectors.build_vectors())
        self.assertEqual(dossier_vectors.find_drift(dossier_vectors.DEFAULT_DIR, vectors), [])
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(dossier_vectors.main(['--write', '--dir', tmp]), 0)
            self.assertEqual(dossier_vectors.main(['--check', '--dir', tmp]), 0)
            path = Path(tmp) / 'sim-closed.json'
            original = path.read_bytes()
            path.write_bytes(original + b' ')
            self.assertEqual(dossier_vectors.main(['--check', '--dir', tmp]), 1)
            path.unlink()
            self.assertTrue(any('missing' in s for s in dossier_vectors.find_drift(tmp, vectors)))
            path.write_bytes(original)
            (Path(tmp) / 'unexpected.json').write_text('{}')
            self.assertTrue(any('unexpected' in s for s in dossier_vectors.find_drift(tmp, vectors)))


class LiveServerTests(unittest.TestCase):
    def setUp(self):
        self.server = make_server(0)
        self.service = seed.apply_steps(self.server.service)
        for role in ('auditor', 'observer', 'agent'):
            self.service.authorizer.bind_role(role)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=2)

    def request(self, method, path, role='organizer', body=None):
        conn = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        headers = {'X-Capital-Token': self.service.authorizer.token_for(role)}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        conn.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = conn.getresponse()
        status, raw = response.status, response.read()
        conn.close()
        return status, raw

    def test_route_role_gate(self):
        path = f'/api/cases/sim-unbound/dossier?instance_id={self.service.instance_id}'
        for role, expected in (('organizer', 200), ('auditor', 200), ('observer', 403), ('agent', 403)):
            status, raw = self.request('GET', path, role)
            self.assertEqual(status, expected, raw)
            if status == 403:
                self.assertEqual(json.loads(raw)['error'], 'ROLE_FORBIDDEN')
            else:
                self.assertEqual(raw, self.request('GET', path, role)[1])

    def test_unknown_advance_404_and_strict_arguments(self):
        suffix = f'?instance_id={self.service.instance_id}'
        for path, status, error in (
            ('/api/cases/missing/dossier'+suffix, 404, 'CASE_NOT_FOUND'),
            ('/api/cases/sim-unbound/other'+suffix, 404, 'NOT_FOUND'),
            ('/api/cases/sim-unbound/nested/dossier'+suffix, 404, 'NOT_FOUND'),
            ('/api/cases/sim-unbound/dossier', 409, 'SESSION_CHANGED'),
            ('/api/cases/sim-unbound/dossier?instance_id=stale', 409, 'SESSION_CHANGED'),
            ('/api/cases/sim-unbound/dossier'+suffix+'&cash=1', 400, 'INVALID_ARGUMENTS'),
            ('/api/cases/sim-unbound/dossier'+suffix+'&instance_id=x', 400, 'INVALID_ARGUMENTS')):
            code, raw = self.request('GET', path)
            self.assertEqual((code, json.loads(raw)['error']), (status, error))


class HandlerTests(LiveServerTests):
    """Real parser/dispatcher on byte streams; does not claim a loopback bind."""
    def setUp(self):
        class CapturedServer:
            def __init__(self, address, handler):
                self.server_port, self.handler = 8765, handler
        with patch('capital.server.CapitalHTTPServer', CapturedServer):
            self.server = make_server(8765)
        self.service = seed.apply_steps(self.server.service)
        for role in ('auditor', 'observer', 'agent'):
            self.service.authorizer.bind_role(role)

    def tearDown(self):
        self.server.observability.close()

    def request(self, method, path, role='organizer', body=None):
        class ByteConnection:
            def __init__(self, raw):
                self.raw, self.output = raw, bytearray()
            def makefile(self, *_):
                return io.BytesIO(self.raw)
            def sendall(self, data):
                self.output.extend(data)
        raw = (f'{method} {path} HTTP/1.0\r\nHost: 127.0.0.1:8765\r\n'
               f'X-Capital-Token: {self.service.authorizer.token_for(role)}\r\n\r\n').encode()
        connection = ByteConnection(raw)
        self.server.handler(connection, ('127.0.0.1', 10000), self.server)
        head, raw_body = bytes(connection.output).split(b'\r\n\r\n', 1)
        return int(head.split()[1]), raw_body


if __name__ == '__main__':
    unittest.main()
