import copy
import http.client
import json
import threading
import unittest

from capital.projection import ProjectionError, ProjectionPort, SimulationProjection
from capital.server import make_server
from capital.service import ApiError, CapitalService


PREDICATES = [
    'DEBITS_EQUAL_CREDITS_EVERY_STEP', 'CLAIM_FACE_EQUALS_PAYEE_FACES',
    'ADVANCE_EXPOSURE_CONSERVATION', 'REFUND_ACCEPTANCE_CONSERVATION', 'NO_REAL_EFFECT',
]


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.service = CapitalService()
        self.n = 0

    def command(self, op, case='sim-a', **args):
        self.n += 1
        return self.service.execute({'instance_id': self.service.instance_id, 'operation_id': f'op-{self.n}',
                                      'op': op, 'advance_id': case, 'args': args})

    def ready(self, case='sim-a', amount=60_000, fixture='sim-committed', bound=True):
        self.assertEqual(self.command('offer', case, fixture_id=fixture, amount=amount)['outcome'], 'ACCEPTED')
        self.command('approve', case)
        if bound:
            self.command('bind_settlement', case)

    def picture(self):
        view = self.service.machine.view('sim-a') if 'sim-a' in self.service.case_fixtures else None
        return {'receipts': json.dumps(self.service.receipts, sort_keys=True),
                'canonical': self.service.machine.canonical_state(),
                'digest': self.service.machine.state_digest(),
                'count': len(self.service.receipts),
                'rows': copy.deepcopy(self.service.fixtures.rows),
                'reserved': None if view is None else view['reserved_open']}

    def test_port_is_a_replacement_seam(self):
        with self.assertRaises(NotImplementedError):
            ProjectionPort().project([], [])

    def test_balanced_every_step_and_totals_equal_fixture_faces(self):
        faces = sum(row['claim']['gross'] for row in self.service.fixtures.rows.values())
        obligation_faces = sum(line['face'] for row in self.service.fixtures.rows.values() for line in row['claim']['obligations'])
        self.assertEqual(faces, 300_000)
        self.assertEqual(obligation_faces, faces)
        self.ready()
        offered = self.service.projection(None)
        self.assert_balanced(offered)
        self.assertEqual(self.side_totals(offered), (faces, faces))
        self.assertFalse(any(row['code'].startswith('SIM_ADVANCE_') for row in offered['accounts']))
        self.command('draw')
        drawn = self.service.projection('simulation')
        self.assert_balanced(drawn)
        self.assertEqual(self.side_totals(drawn), (faces + 60_000, faces + 60_000))
        self.command('repay', amount=20_000, sequence=1)
        self.command('repay', amount=40_000, sequence=2)
        self.command('close')
        final = self.service.projection(None)
        self.assert_balanced(final)
        self.assertEqual(self.side_totals(final), (faces + 120_000, faces + 120_000))
        self.assertEqual(len(final['entries']), 10)
        self.assertEqual(sum(1 for entry in final['entries'] if entry['source'] == 'EVIDENCE'), 3)
        self.assertEqual(sum(1 for entry in final['entries'] if entry['lines']), 6)
        accounts = {row['code']: row for row in final['accounts']}
        view = self.service.machine.view('sim-a')
        exposure, obligation, memo = (accounts['SIM_ADVANCE_EXPOSURE:sim-a'], accounts['SIM_ADVANCE_OBLIGATION:sim-a'], accounts['SIM_REPAY_MEMO:sim-a'])
        self.assertEqual(exposure['debit_total'], view['drawn_exposure'])
        self.assertEqual(exposure['credit_total'], 0)
        self.assertEqual(obligation['balance'], view['outstanding_exposure'])
        self.assertEqual(memo['credit_total'], view['repaid_exposure'])
        self.assertEqual((view['outstanding_exposure'], view['repaid_exposure'], view['drawn_exposure']), (0, 60_000, 60_000))
        payee_credit = sum(row['credit_total'] for row in final['accounts'] if row['code'].startswith('SIM_PAYEE_OBLIGATION:'))
        claim_debit = sum(row['debit_total'] for row in final['accounts'] if row['code'].startswith('SIM_CLAIM_FACE:'))
        self.assertEqual(payee_credit, obligation_faces)
        self.assertEqual(claim_debit, faces)
        for account in final['accounts']:
            self.assertTrue(account['label'])
            self.assertTrue(account['kind'].startswith('SYNTHETIC_'))
            normal_debit = account['kind'] in {'SYNTHETIC_CLAIM_FACE', 'SYNTHETIC_ADVANCE_EXPOSURE'}
            expected = account['debit_total'] - account['credit_total'] if normal_debit else account['credit_total'] - account['debit_total']
            self.assertEqual(account['balance'], expected)
        advance = final['read_model']['advances']
        self.assertEqual(advance, [{'advance_id': 'sim-a', 'beneficiary_role': 'fixture-organizer', 'amount': 60_000,
                                     'drawn': 60_000, 'repaid': 60_000, 'outstanding': 0}])
        self.assert_claims_match_fixtures(final)

    def test_projection_is_read_only(self):
        self.ready()
        self.command('draw')
        journal = self.service.machine.export_journal()
        evidence = [self.service.fixtures.view(key) for key in sorted(self.service.fixtures.rows)]
        raw_journal, raw_evidence = copy.deepcopy(journal), copy.deepcopy(evidence)
        before = self.picture()
        first = self.service.projection(None)
        self.assertEqual(journal, raw_journal)
        self.assertEqual(evidence, raw_evidence)
        self.assertEqual(self.picture(), before)
        first['entries'].clear()
        second = self.service.projection('simulation')
        self.assertEqual(self.picture(), before)
        self.assertEqual(second['cut'], before['digest'])
        self.assertTrue(second['entries'])
        self.assertNotEqual(first['entries'], second['entries'])
        direct = SimulationProjection().project(journal, evidence)
        self.assertEqual(journal, raw_journal)
        self.assertEqual(evidence, raw_evidence)
        self.assertEqual(len(direct['entries']), len(second['entries']))

    def test_projection_flags_and_cut(self):
        body = self.service.projection(None)
        self.assertEqual(body['mode'], 'LOCAL_PROJECTION_CANDIDATE')
        self.assertEqual(body['chart'], 'SIMULATION_FIXED_V1')
        self.assertEqual(body['accounting_policy'], 'SYNTHETIC_UNADOPTED')
        self.assertEqual(body['tax'], 'NOT_BOUND')
        self.assertEqual(body['legal'], 'NOT_BOUND')
        self.assertEqual(body['operating_ledger'], 'NOT_BOUND')
        self.assertEqual(body['cut'], self.service.machine.state_digest())
        self.assertEqual(body['source_commit'], self.service.source['commit'])
        self.assertFalse(body['funds_executed'])
        self.assertFalse(body['policy_adopted'])
        self.assertFalse(body['workspace_mutated'])
        self.assertEqual(body['instance_id'], self.service.instance_id)
        self.assertEqual([row['predicate'] for row in body['conservation']], PREDICATES)
        json.dumps(body)

    def test_mode_not_bound(self):
        before = self.service.machine.canonical_state()
        for mode in ('operating-ledger', 'operating', 'ledger', 'OPERATING', '', 'simulation ', ['simulation']):
            with self.assertRaises(ApiError) as caught:
                self.service.projection(mode)
            self.assertEqual(caught.exception.code, 'NOT_BOUND')
            self.assertEqual(caught.exception.status, 400)
        self.assertEqual(self.service.machine.canonical_state(), before)
        self.assertEqual(len(self.service.receipts), 0)

    def test_rejected_draw_and_unbound_draw_follow_the_journal_only(self):
        self.ready(fixture='sim-pending')
        self.assertEqual(self.command('draw')['error'], 'SETTLEMENT_NOT_COMMITTED')
        pending = self.service.projection(None)
        self.assertFalse(any(row['code'].startswith('SIM_ADVANCE_') for row in pending['accounts']))
        self.ready('sim-u', fixture='sim-committed', bound=False)
        self.command('draw', 'sim-u')
        unbound = self.service.projection('simulation')
        self.assertEqual(self.service.machine.view('sim-u')['settlement_gate'], 'UNBOUND')
        accounts = {row['code']: row for row in unbound['accounts']}
        self.assertEqual(accounts['SIM_ADVANCE_EXPOSURE:sim-u']['debit_total'], 60_000)
        self.assertEqual(accounts['SIM_ADVANCE_OBLIGATION:sim-u']['balance'], 60_000)
        self.command('default', 'sim-u')
        defaulted = self.service.projection(None)['read_model']['advances']
        row = next(item for item in defaulted if item['advance_id'] == 'sim-u')
        self.assertEqual((row['outstanding'], row['repaid'], row['drawn']), (60_000, 0, 60_000))

    def test_imbalance_is_refused(self):
        evidence = [self.service.fixtures.view('sim-committed')]
        evidence[0]['gross'] = 1
        evidence[0]['claim']['gross'] = 1
        with self.assertRaises(ProjectionError) as caught:
            SimulationProjection().project([], evidence)
        self.assertEqual(caught.exception.code, 'PROJECTION_INVARIANT')
        with self.assertRaises(ProjectionError):
            SimulationProjection().project(
                [{'op': 'draw', 'idempotency_key': 'x', 'advance_id': 'sim-a', 'body': {}}],
                [self.service.fixtures.view('sim-committed')])

    def test_readiness_keeps_cap13_upstream(self):
        ready = self.service.readiness()
        self.assertEqual(ready['requirement_notes']['CAP-13'], 'local candidate projection; fin-ledger-contract still upstream')
        ready['requirement_notes']['CAP-13'] = 'changed'
        self.assertEqual(self.service.readiness()['requirement_notes']['CAP-13'],
                         'local candidate projection; fin-ledger-contract still upstream')
        group = next(row for row in ready['groups'] if row['id'] == 'durable-finance')
        fresh = next(row for row in self.service.readiness()['groups'] if row['id'] == 'durable-finance')
        self.assertEqual(fresh['status'], 'UPSTREAM_REQUIRED')
        self.assertEqual(fresh['requirements'], ['CAP-11', 'CAP-13', 'CAP-14', 'CAP-15'])
        self.assertEqual(fresh['blockers'], ['채택 backend와 stage5/6 경제 원천', 'Finance 후보 8개 채택과 계정/세무 정책',
                                              'stage7 source cut·watermark·인증 export·부분 자료 거절'])
        self.assertEqual(fresh['available'], ['프로세스 내 저널 재생', '고정 fixture와 source hash 조회',
                                               '로컬 후보 복식 투영 (SYNTHETIC_UNADOPTED · 비채택)'])
        self.assertEqual({item for row in self.service.readiness()['groups'] for item in row['requirements']},
                         {f'CAP-{i:02}' for i in range(1, 21)})
        self.assertEqual(self.service.readiness()['upstream_nodes_completed'], [])
        self.assertFalse(self.service.readiness()['policy_adopted'])
        self.assertEqual(group['status'], 'UPSTREAM_REQUIRED')

    def assert_balanced(self, body):
        debit = credit = 0
        for entry in body['entries']:
            step_debit = sum(line['amount'] for line in entry['lines'] if line['side'] == 'debit')
            step_credit = sum(line['amount'] for line in entry['lines'] if line['side'] == 'credit')
            self.assertEqual(step_debit, step_credit)
            debit += step_debit
            credit += step_credit
            self.assertEqual(debit, credit)
        self.assertEqual(self.side_totals(body), (debit, credit))
        self.assertEqual([row['predicate'] for row in body['conservation']], PREDICATES)
        self.assertTrue(all(row['matched'] for row in body['conservation']))

    def side_totals(self, body):
        return (sum(row['debit_total'] for row in body['accounts']), sum(row['credit_total'] for row in body['accounts']))

    def assert_claims_match_fixtures(self, body):
        projected = {row['claim_id']: row for row in body['read_model']['claims']}
        self.assertEqual(set(projected), set(self.service.fixtures.rows))
        for key, source in self.service.fixtures.rows.items():
            claim = source['claim']
            row = projected[key]
            self.assertEqual(row['phase'], source['phase'])
            self.assertEqual(row['gross'], claim['gross'])
            self.assertEqual(row['confirmed_cash'], claim['confirmed_cash'])
            self.assertEqual(row['refund_face'], claim['refund_face'])
            self.assertEqual(row['refund_outstanding'], claim['refund_outstanding'])
            self.assertEqual(claim['refund_face'], claim['refund_accepted'] + claim['refund_outstanding'])
            for src, dst in zip(claim['obligations'], row['obligations']):
                for field in ('payee', 'face', 'distributed', 'outstanding', 'recovery_due'):
                    self.assertEqual(dst[field], src[field])


class ProjectionHttpTests(unittest.TestCase):
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
        cls.worker.join()

    def request(self, path, headers=None):
        client = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        client.request('GET', path, headers=headers or {})
        response = client.getresponse()
        raw, status = response.read(), response.status
        client.close()
        return status, raw

    def test_http_projection_flags_cut_and_not_bound(self):
        status, raw = self.request('/api/projection')
        self.assertEqual(status, 200)
        body = json.loads(raw)
        state = json.loads(self.request('/api/state')[1])
        self.assertEqual(body['cut'], state['state_digest'])
        self.assertEqual(body['mode'], 'LOCAL_PROJECTION_CANDIDATE')
        self.assertEqual(body['chart'], 'SIMULATION_FIXED_V1')
        self.assertEqual(body['accounting_policy'], 'SYNTHETIC_UNADOPTED')
        self.assertEqual(body['tax'], 'NOT_BOUND')
        self.assertEqual(body['legal'], 'NOT_BOUND')
        self.assertEqual(body['operating_ledger'], 'NOT_BOUND')
        self.assertFalse(body['funds_executed'])
        self.assertFalse(body['policy_adopted'])
        self.assertFalse(body['workspace_mutated'])
        self.assertEqual(body['entries'][0]['source'], 'EVIDENCE')
        self.assertNotIn('advance_id', body['entries'][0])
        for path in ('/api/projection?mode=operating-ledger', '/api/projection?mode=operating', '/api/projection?mode=ledger'):
            status, raw = self.request(path)
            self.assertEqual(status, 400)
            self.assertEqual(json.loads(raw)['error'], 'NOT_BOUND')
        again = json.loads(self.request('/api/state')[1])
        self.assertEqual(again['state_digest'], state['state_digest'])
        self.assertEqual(again['operation_count'], state['operation_count'])
        simulated = json.loads(self.request('/api/projection?mode=simulation')[1])
        self.assertEqual(simulated['entries'], body['entries'])
        self.assertEqual(self.request('/api/projection', headers={'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.request('/api/projection?mode=simulation&mode=operating')[0], 400)


if __name__ == '__main__':
    unittest.main()
