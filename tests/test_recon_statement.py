import copy
import hashlib
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from capital.protocol import CreditMachine
from capital.recon import CHECK_IDS, build_reconciliation
from capital.server import make_server
from capital.service import MAX_OPERATIONS, CapitalService, digest
from capital.statement import APPROVED_PHASES
from capital.store import FileWorkspace, StoragePort, WorkspaceError, canonical_bytes, envelope, verify_document


def command(service, op, case, operation_id, **args):
    return service.execute({
        'instance_id': service.instance_id, 'operation_id': operation_id,
        'op': op, 'advance_id': case, 'args': args,
    })


def check(report, check_id):
    return next(row for row in report['checks'] if row['id'] == check_id)


def category(report, category_id):
    return next(row for row in report['categories'] if row['id'] == category_id)


def frozen(service):
    return (
        json.dumps(service.receipts, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode(),
        service.machine.state_digest(),
        len(service.receipts),
        service.machine.canonical_state(),
    )


class FakeStorage(StoragePort):
    durable_label = False

    def __init__(self, document):
        self.document = document
        self.saves = 0

    def load(self):
        return verify_document(copy.deepcopy(self.document))

    def save(self, payload):
        self.saves += 1
        raise AssertionError('statement and reconciliation must not save')


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.service = CapitalService()

    def ready(self, case='sim-a', amount=60_000, fixture='sim-committed', draw=True):
        self.assertEqual(command(self.service, 'offer', case, case + '-offer', fixture_id=fixture, amount=amount)['outcome'], 'ACCEPTED')
        command(self.service, 'approve', case, case + '-approve')
        command(self.service, 'bind_settlement', case, case + '-bind')
        if draw:
            self.assertEqual(command(self.service, 'draw', case, case + '-draw')['outcome'], 'ACCEPTED')

    def test_clean_workspace_is_matched_with_not_bound_gaps(self):
        empty = self.service.reconciliation()
        self.assertEqual(empty['status'], 'MATCHED')
        self.assertTrue(empty['replay_matched'])
        self.assertEqual([row['id'] for row in empty['checks']], list(CHECK_IDS))
        self.assertTrue(all(row['status'] == 'MATCHED' for row in empty['checks']))
        self.assertGreaterEqual(len(empty['not_bound']), 3)
        self.assertEqual(
            [row['id'] for row in empty['not_bound']],
            ['bank_pg_provider_observations', 'source_cut', 'completeness'],
        )
        self.assertTrue(all(row['status'] == 'NOT_BOUND' for row in empty['not_bound']))
        self.assertEqual(empty['bank_reconciliation'], 'NOT_BOUND')
        self.assertEqual(empty['provider_authenticated_completeness'], 'NOT_BOUND')
        self.assertEqual(empty['source_cut'], 'NOT_BOUND')
        self.assert_scope(empty, self.service)
        self.ready()
        rejected = command(self.service, 'offer', 'sim-refund-case', 'refund-offer', fixture_id='sim-refund', amount=100)
        self.assertEqual(rejected['outcome'], 'REJECTED')
        before = frozen(self.service)
        report = self.service.reconciliation()
        self.assertEqual(frozen(self.service), before)
        self.assertEqual(report['status'], 'MATCHED')
        self.assertTrue(report['replay_matched'])
        self.assertEqual(report['state_digest'], before[1])
        self.assertEqual(report['entry_count'], len(self.service.machine.export_journal()))
        self.assertFalse(report['funds_executed'])
        self.assertFalse(report['durable'])
        self.assertFalse(report['workspace_mutated'])
        self.assertEqual(check(report, 'rejected_receipts_absent_from_journal')['status'], 'MATCHED')
        self.assert_scope(report, self.service)

    def test_reconcile_receipt_is_accepted_outside_the_journal(self):
        self.ready(draw=False)
        receipt = command(self.service, 'reconcile', 'sim-a', 'sim-a-reconcile')
        self.assertEqual(receipt['outcome'], 'ACCEPTED')
        self.assertEqual(receipt['result']['applied'], 'reconcile')
        self.assertTrue(receipt['result']['matched'])
        journal_keys = [entry['idempotency_key'] for entry in self.service.machine.export_journal()]
        self.assertNotIn('sim-a-reconcile', journal_keys)
        before = frozen(self.service)
        report = self.service.reconciliation()
        self.assertEqual(frozen(self.service), before)
        self.assertEqual(report['status'], 'MATCHED')
        self.assertEqual(check(report, 'receipts_vs_journal_keys')['status'], 'MATCHED')
        self.assertEqual(report['entry_count'], len(journal_keys))
        self.assertGreater(len(self.service.receipts), report['entry_count'])

    def test_absent_receipt_stays_unknown_unresolved(self):
        self.ready(draw=False)
        before = frozen(self.service)
        report = self.service.reconciliation('never-sent')
        self.assertEqual(report['status'], 'MATCHED')
        self.assertEqual(report['unknown_unresolved'], [{
            'operation_id': 'never-sent', 'outcome': 'UNKNOWN_UNRESOLVED',
            'retry_authorized': False, 'resolved': False,
        }])
        self.assertFalse(report['unknown_policy']['retry_authorized'])
        self.assertFalse(report['unknown_policy']['resolved_by_reconciliation'])
        looked = self.service.operation('never-sent', self.service.instance_id)
        self.assertEqual(looked['outcome'], 'UNKNOWN')
        self.assertFalse(looked['retry_authorized'])
        self.assertNotIn('never-sent', self.service.receipts)
        again = self.service.reconciliation('never-sent')
        self.assertEqual(again['unknown_unresolved'], report['unknown_unresolved'])
        self.assertEqual(frozen(self.service), before)
        self.assertEqual(self.service.reconciliation('sim-a-offer')['unknown_unresolved'], [])

    def test_statement_categories_do_not_sum_primary_and_resale(self):
        self.ready()
        command(self.service, 'repay', 'sim-a', 'sim-a-repay', amount=20_000, sequence=1)
        command(self.service, 'offer', 'sim-b', 'sim-b-offer', fixture_id='sim-pending', amount=10_000)
        command(self.service, 'approve', 'sim-b', 'sim-b-approve')
        before = frozen(self.service)
        report = self.service.statement()
        self.assertEqual(frozen(self.service), before)
        self.assertEqual(report['mode'], 'READ_ONLY_STATEMENT')
        self.assertEqual(report['label'], 'SIMULATED')
        self.assertFalse(report['sales_combined'])
        self.assertEqual(report['primary_and_resale'], 'NOT_SUMMED')
        self.assertEqual(report['tax_reporting'], 'NOT_BOUND')
        self.assertEqual([row['id'] for row in report['not_bound']], ['primary_sales', 'resale_sales', 'actual_paid'])
        self.assertTrue(all(row['status'] == 'NOT_BOUND' for row in report['not_bound']))
        self.assert_no_sales_numbers(report)
        self.assertEqual([row['id'] for row in report['categories']], ['approved', 'exposure', 'reserved', 'settlement', 'refund'])
        views = {key: self.service.machine.view(key) for key in sorted(self.service.case_fixtures)}
        approved = category(report, 'approved')
        exposure = category(report, 'exposure')
        reserved = category(report, 'reserved')
        settlement = category(report, 'settlement')
        refund = category(report, 'refund')
        self.assertEqual(approved['source'], 'SIMULATED')
        self.assertEqual(approved['total'], sum(row['amount'] for row in views.values() if row['phase'] in APPROVED_PHASES))
        self.assertEqual(approved['total'], 70_000)
        self.assertEqual(exposure['drawn'], sum(row['drawn_exposure'] for row in views.values()))
        self.assertEqual(exposure['repaid'], sum(row['repaid_exposure'] for row in views.values()))
        self.assertEqual(exposure['outstanding'], sum(row['outstanding_exposure'] for row in views.values()))
        self.assertEqual((exposure['drawn'], exposure['repaid'], exposure['outstanding']), (60_000, 20_000, 40_000))
        self.assertTrue(reserved['consistent'])
        by_claim = {}
        for row in views.values():
            by_claim.setdefault(row['claim_id'], row['reserved_open'])
            self.assertEqual(by_claim[row['claim_id']], row['reserved_open'])
        self.assertEqual(reserved['total'], sum(by_claim.values()))
        self.assertEqual(set(by_claim), {'sim-committed', 'sim-pending'})
        fixtures = self.service.fixtures.rows
        self.assertEqual(settlement['source'], 'READ_ONLY_FIXTURE')
        self.assertEqual(settlement['confirmed'], sum(row['claim']['confirmed_cash'] for row in fixtures.values()))
        self.assertEqual(settlement['distributed'], sum(row['claim']['distributed_cash'] for row in fixtures.values()))
        self.assertEqual(refund['refund_face'], sum(row['claim']['refund_face'] for row in fixtures.values()))
        self.assertEqual(refund['refund_outstanding'], sum(row['claim']['refund_outstanding'] for row in fixtures.values()))
        self.assertEqual(refund['refund_face'], 10_000)
        self.assert_scope(report, self.service)
        self.assertFalse(report['funds_executed'])
        self.assertFalse(report['durable'])

    def test_endpoints_are_read_only_over_http(self):
        server = make_server(0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            service = server.service
            command(service, 'offer', 'sim-a', 'http-offer', fixture_id='sim-committed', amount=1000)
            before = frozen(service)
            host = f'127.0.0.1:{server.server_port}'

            def get(path):
                client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                client.request('GET', path, headers={'Host': host})
                response = client.getresponse()
                raw, status = response.read(), response.status
                client.close()
                return status, json.loads(raw)

            status, recon = get('/api/reconciliation?operation_id=absent-http')
            self.assertEqual(status, 200)
            self.assertEqual(recon['status'], 'MATCHED')
            self.assertEqual(recon['unknown_unresolved'][0]['outcome'], 'UNKNOWN_UNRESOLVED')
            status, statement = get('/api/statement')
            self.assertEqual(status, 200)
            self.assertEqual(statement['categories'][0]['total'], 0)
            status, missing = get('/api/operations/absent-http?instance_id=' + service.instance_id)
            self.assertEqual(missing['outcome'], 'UNKNOWN')
            self.assertFalse(missing['retry_authorized'])
            self.assertEqual(frozen(service), before)
            self.assertNotIn('absent-http', service.receipts)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

    def test_readiness_names_local_diagnostics_only(self):
        notes = self.service.readiness()['requirement_notes']
        self.assertIn('never summed', notes['CAP-09'])
        self.assertIn('NOT_BOUND', notes['CAP-09'])
        self.assertIn('no bank reconciliation', notes['CAP-14'])
        self.assertIn('provider-authenticated completeness', notes['CAP-14'])
        local = next(row for row in self.service.readiness()['groups'] if row['id'] == 'local-simulation')
        self.assertIn('은행 대사', local['behavior'])
        self.assertIn('제공자 인증 완전성', local['behavior'])
        durable = next(row for row in self.service.readiness()['groups'] if row['id'] == 'durable-finance')
        self.assertIn('은행 대사', durable['claim'])
        self.assertEqual(durable['status'], 'UPSTREAM_REQUIRED')

    def assert_scope(self, report, service):
        self.assertEqual(report['cut'], report['state_digest'])
        self.assertEqual(report['fixtures_digest'], digest(service.fixtures.rows))
        self.assertEqual(report['operation_capacity'], MAX_OPERATIONS)
        self.assertEqual(report['scope']['cut'], report['cut'])
        self.assertEqual(report['scope']['fixtures_digest'], report['fixtures_digest'])
        self.assertEqual(report['scope']['capacity_bound'], MAX_OPERATIONS)
        self.assertEqual(report['scope']['source_cut'], 'NOT_BOUND')
        self.assertEqual(report['scope']['completeness'], 'NOT_BOUND')

    def assert_no_sales_numbers(self, value):
        if type(value) is dict:
            for key, child in value.items():
                if 'sales' in key or key in {'actual_paid', 'primary_and_resale'}:
                    self.assertNotIn(type(child), {int, float})
                self.assert_no_sales_numbers(child)
        elif type(value) is list:
            for child in value:
                self.assert_no_sales_numbers(child)


class TamperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.open_ports = []

    def tearDown(self):
        for port in self.open_ports:
            port.close()
        self.tmp.cleanup()

    def service(self):
        port = FileWorkspace.open(self.dir)
        self.open_ports.append(port)
        return CapitalService(port)

    def close_ports(self):
        for port in self.open_ports:
            port.close()
        self.open_ports.clear()

    def rewrite(self, mutate):
        path = self.dir / 'workspace.json'
        document = json.loads(path.read_text())
        mutate(document['payload'])
        document['payload_sha256'] = hashlib.sha256(canonical_bytes(document['payload'])).hexdigest()
        path.write_bytes(canonical_bytes(document))
        verify_document(json.loads(path.read_text()))
        return path

    def test_dropped_receipt_is_recon_mismatch_and_not_resolved(self):
        original = CapitalService()
        command(original, 'offer', 'sim-a', 'op-1', fixture_id='sim-committed', amount=60_000)
        payload = copy.deepcopy(original.storage.load()['payload'])
        del payload['receipts']['op-1']
        port = FakeStorage(envelope('tamper-writer', payload))
        service = CapitalService(port)
        self.assertEqual(service.workspace_status, 'WORKSPACE_UNREADABLE')
        before = frozen(service)
        report = service.reconciliation()
        self.assertEqual(port.saves, 0)
        self.assertEqual(report['status'], 'RECON_MISMATCH')
        self.assertEqual(check(report, 'receipts_vs_journal_keys')['status'], 'RECON_MISMATCH')
        self.assertEqual(check(report, 'receipts_vs_journal_keys')['id'], 'receipts_vs_journal_keys')
        self.assertEqual(report['unknown_unresolved'], [{
            'operation_id': 'op-1', 'outcome': 'UNKNOWN_UNRESOLVED',
            'retry_authorized': False, 'resolved': False,
        }])
        looked = service.operation('op-1', service.instance_id)
        self.assertEqual(looked['outcome'], 'UNKNOWN')
        self.assertFalse(looked['retry_authorized'])
        self.assertNotIn('op-1', service.receipts)
        self.assertNotIn('op-1', port.document['payload']['receipts'])
        again = service.reconciliation()
        self.assertEqual(again['unknown_unresolved'][0]['outcome'], 'UNKNOWN_UNRESOLVED')
        self.assertFalse(again['unknown_unresolved'][0]['resolved'])
        self.assertEqual(port.saves, 0)
        self.assertEqual(frozen(service), before)

    def test_changed_journal_amount_names_the_check(self):
        original = self.service()
        command(original, 'offer', 'sim-a', 'offer-a', fixture_id='sim-committed', amount=60_000)
        command(original, 'approve', 'sim-a', 'approve-a')
        self.close_ports()

        def change_amount(payload):
            offer = next(entry for entry in payload['journal'] if entry['op'] == 'offer')
            self.assertEqual(offer['body']['amount'], 60_000)
            offer['body']['amount'] = 61_000

        path = self.rewrite(change_amount)
        before_bytes = path.read_bytes()
        service = self.service()
        self.assertEqual(service.workspace_status, 'WORKSPACE_UNREADABLE')
        before = frozen(service)
        report = service.reconciliation()
        self.assertEqual(path.read_bytes(), before_bytes)
        self.assertEqual(frozen(service), before)
        self.assertEqual(report['status'], 'RECON_MISMATCH')
        self.assertEqual(check(report, 'replay_digest_equals_state_digest')['status'], 'RECON_MISMATCH')
        self.assertEqual(check(report, 'replay_digest_equals_state_digest')['id'], 'replay_digest_equals_state_digest')
        self.assertFalse(report['replay_matched'])
        self.assertNotEqual(report['status'], 'WORKSPACE_UNREADABLE')

    def test_recomputed_digest_still_mismatches_the_receipt_amount(self):
        original = self.service()
        command(original, 'offer', 'sim-a', 'offer-a', fixture_id='sim-committed', amount=60_000)
        fixtures = original.fixtures
        self.close_ports()

        def change_and_resign(payload):
            offer = next(entry for entry in payload['journal'] if entry['op'] == 'offer')
            offer['body']['amount'] = 61_000
            payload['state_digest'] = CreditMachine.restore(copy.deepcopy(payload['journal']), fixtures).state_digest()

        path = self.rewrite(change_and_resign)
        before_bytes = path.read_bytes()
        service = self.service()
        self.assertEqual(service.workspace_status, 'ACTIVE')
        self.assertEqual(service.machine.view('sim-a')['amount'], 61_000)
        self.assertEqual(service.operation('offer-a', service.instance_id)['result']['credit']['amount'], 60_000)
        before = frozen(service)
        report = service.reconciliation()
        self.assertEqual(path.read_bytes(), before_bytes)
        self.assertEqual(frozen(service), before)
        self.assertEqual(report['status'], 'RECON_MISMATCH')
        self.assertEqual(check(report, 'projection_totals_vs_case_views')['status'], 'RECON_MISMATCH')
        self.assertEqual(check(report, 'projection_totals_vs_case_views')['id'], 'projection_totals_vs_case_views')
        self.assertTrue(report['replay_matched'])

    def test_corrupt_checksum_stays_workspace_unreadable(self):
        original = self.service()
        command(original, 'offer', 'sim-a', 'offer-a', fixture_id='sim-committed', amount=1000)
        self.close_ports()
        path = self.dir / 'workspace.json'
        document = json.loads(path.read_text())
        document['payload_sha256'] = '0' * 64
        path.write_bytes(canonical_bytes(document))
        with self.assertRaises(WorkspaceError):
            verify_document(json.loads(path.read_text()))
        service = self.service()
        report = service.reconciliation()
        self.assertEqual(service.workspace_status, 'WORKSPACE_UNREADABLE')
        self.assertEqual(report['status'], 'WORKSPACE_UNREADABLE')
        self.assertNotEqual(report['status'], 'MATCHED')
        self.assertTrue(report['not_bound'])


class DirectBuilderTests(unittest.TestCase):
    def test_builder_does_not_require_the_server(self):
        report = build_reconciliation(
            payload={'receipts': [], 'journal': {}, 'case_fixtures': None, 'state_digest': ''},
            unreadable=None, fixture_rows={}, fixtures_digest='abc', settlement_source=None,
            projection_port=None, probe_operation_id='missing', instance_id='inst',
            operation_capacity=500, workspace_status='ACTIVE',
        )
        self.assertEqual(report['status'], 'RECON_MISMATCH')
        self.assertEqual(report['unknown_unresolved'][0]['outcome'], 'UNKNOWN_UNRESOLVED')
        self.assertIn('receipts_vs_journal_keys', CHECK_IDS)
