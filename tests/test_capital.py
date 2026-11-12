import concurrent.futures
import copy
import hashlib
import http.client
import json
import threading
import unittest
from pathlib import Path

from capital.service import ApiError, CapitalService, MAX_OPERATIONS, VENDOR
from capital.server import make_server


class DomainTests(unittest.TestCase):
    def setUp(self):
        self.service = CapitalService()
        self.counter = 0

    def command(self, op, case='sim-a', key=None, **args):
        self.counter += 1
        return self.service.execute(dict(instance_id=self.service.instance_id,
            operation_id=key or f'operation-{self.counter}',op=op,advance_id=case,args=args))

    def ready(self, case='sim-a', amount=60000, fixture='sim-committed', bound=True):
        self.assertEqual(self.command('offer',case,fixture_id=fixture,amount=amount)['outcome'],'ACCEPTED')
        self.command('approve',case)
        if bound:self.command('bind_settlement',case)

    def test_full_journey_and_read_only_settlement(self):
        before=copy.deepcopy(self.service.fixtures.rows)
        self.ready();self.command('draw')
        self.command('repay',amount=20000,sequence=1)
        c=self.service.machine.view('sim-a')
        self.assertEqual((c['outstanding_exposure'],c['reserved_open']),(40000,60000))
        self.assertEqual(self.command('close')['error'],'OUTSTANDING_REMAINS')
        self.command('repay',amount=40000,sequence=2);self.command('close')
        self.assertEqual(self.service.machine.view('sim-a')['phase'],'CLOSED')
        self.assertEqual(self.service.machine.view('sim-a')['reserved_open'],0)
        self.assertTrue(self.service.export()['replay_matched'])
        self.assertEqual(before,self.service.fixtures.rows)
        self.assertFalse(self.service.machine.view('sim-a')['funds_executed'])

    def test_terminal_default_keeps_reservation(self):
        self.ready();self.command('draw');self.command('default')
        c=self.service.machine.view('sim-a');self.assertEqual(c['phase'],'DEFAULTED')
        self.assertEqual(c['reserved_open'],60000)
        self.assertEqual(self.command('repay',amount=1,sequence=1)['error'],'TERMINAL_IMMUTABLE')
        self.assertEqual(self.command('reconcile')['outcome'],'ACCEPTED')

    def test_pending_settlement_and_refund_adverse_cases(self):
        self.ready(fixture='sim-pending')
        self.assertEqual(self.command('draw',key='sticky')['error'],'SETTLEMENT_NOT_COMMITTED')
        self.assertEqual(self.command('draw',key='sticky')['error'],'SETTLEMENT_NOT_COMMITTED')
        self.assertEqual(self.service.machine.view('sim-a')['outstanding_exposure'],0)
        self.assertEqual(self.command('offer','sim-refund-case',fixture_id='sim-refund',amount=100)['error'],'REFUND_OBLIGATION_OPEN')

    def test_unbound_is_explicit_supported_protocol_model(self):
        self.ready(fixture='sim-pending',bound=False)
        r=self.command('draw')['result']['credit']
        self.assertEqual(r['settlement_gate'],'UNBOUND');self.assertFalse(r['mock_settlement_commit_observed'])

    def test_shared_face_contention(self):
        self.ready('sim-a');self.ready('sim-b')
        self.command('draw','sim-a')
        self.assertEqual(self.command('draw','sim-b')['error'],'ADVANCE_EXCEEDS_OPEN_FACE')
        self.assertEqual(self.service.machine.view('sim-b')['phase'],'APPROVED')

    def test_concurrent_draws_are_serialized(self):
        self.ready('sim-a');self.ready('sim-b')
        def draw(case):return self.service.execute(dict(instance_id=self.service.instance_id,operation_id=case,op='draw',advance_id=case,args={}))
        with concurrent.futures.ThreadPoolExecutor(2) as pool:results=list(pool.map(draw,['sim-a','sim-b']))
        self.assertEqual(sorted(r['outcome'] for r in results),['ACCEPTED','REJECTED'])
        self.assertEqual(sum(c['outstanding_exposure'] for c in self.service.snapshot()['cases']),60000)

    def test_first_receipt_and_conflict(self):
        self.ready();first=self.command('draw',key='draw-stable')
        self.command('repay',amount=10000,sequence=1)
        duplicate=self.command('draw',key='draw-stable')
        self.assertTrue(duplicate['transport_duplicate'])
        self.assertEqual(first['result'],duplicate['result'])
        with self.assertRaisesRegex(ApiError,'IDEMPOTENCY_CONFLICT'):self.command('close',key='draw-stable')
        self.assertEqual(self.service.machine.view('sim-a')['outstanding_exposure'],50000)

    def test_lost_receipt_lookup_does_not_repeat_effect(self):
        self.ready();self.command('draw',key='lost')
        count=len(self.service.machine.export_journal())
        self.assertEqual(self.service.operation('lost',self.service.instance_id)['outcome'],'ACCEPTED')
        self.assertEqual(len(self.service.machine.export_journal()),count)
        self.assertEqual(self.service.operation('absent',self.service.instance_id)['outcome'],'UNKNOWN')
        with self.assertRaisesRegex(ApiError,'SESSION_CHANGED'):self.service.operation('lost','old')

    def test_reject_and_cancel_terminals(self):
        for case,op in [('sim-reject','reject'),('sim-cancel','cancel')]:
            self.command('offer',case,fixture_id='sim-committed',amount=100)
            self.command(op,case)
            self.assertEqual(self.command('approve',case)['error'],'TERMINAL_IMMUTABLE')

    def test_invalid_amounts_and_repayment_order(self):
        for value in [True,1.5,'100',0,-1,10**12+1]:
            self.assertEqual(self.command('offer',fixture_id='sim-committed',amount=value)['error'],'INVALID_AMOUNT')
        self.ready();self.command('draw')
        self.assertEqual(self.command('repay',amount=1,sequence=2)['error'],'REPAYMENT_ORDER')
        self.assertEqual(self.command('repay',amount=60001,sequence=1)['error'],'REPAYMENT_EXCEEDS_OUTSTANDING')

    def test_restricted_schema_and_execution(self):
        for op in ['DISBURSE','UNDERWRITE','KYC','execute','__getattribute__']:
            with self.assertRaisesRegex(ApiError,'UNSUPPORTED_OPERATION'):self.command(op)
        with self.assertRaisesRegex(ApiError,'INVALID_ARGUMENTS'):self.command('offer',fixture_id='sim-committed',amount=1,product={})
        with self.assertRaisesRegex(ApiError,'SYNTHETIC_ID_REQUIRED'):self.command('offer','person',fixture_id='sim-committed',amount=1)
        self.assertEqual(self.service.snapshot()['cases'],[])

    def test_read_copies_and_bounded_capacity(self):
        snapshot=self.service.snapshot();snapshot['fixtures'].clear()
        self.assertEqual(len(self.service.fixtures.rows),13)
        for i in range(MAX_OPERATIONS):self.command('approve',key=str(i))
        with self.assertRaisesRegex(ApiError,'SIMULATION_CAPACITY'):self.command('approve',key='overflow')
        self.assertTrue(self.command('approve',key='0')['transport_duplicate'])

    def test_vendor_pin_byte_integrity(self):
        manifest=json.loads((VENDOR/'manifest.json').read_text())
        for name,expected in manifest['files'].items():self.assertEqual(hashlib.sha256((VENDOR/name).read_bytes()).hexdigest(),expected,name)


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=make_server(0);cls.port=cls.server.server_port
        cls.worker=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.worker.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.worker.join()
    def request(self,method,path,body=None,headers=None):
        client=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        client.request(method,path,body=body,headers=headers or {});r=client.getresponse();raw=r.read();status=r.status;h=dict(r.getheaders());client.close();return status,raw,h
    def state(self):return json.loads(self.request('GET','/api/state')[1])
    def payload(self):return dict(instance_id=self.state()['instance_id'],operation_id='http-case',op='offer',advance_id='sim-http',args={'fixture_id':'sim-committed','amount':100})
    def post(self,body,**headers):
        return self.request('POST','/api/commands',body,{'Content-Type':'application/json','X-Capital-Token':self.state()['local_token'],**headers})
    def test_local_headers_and_static(self):
        status,raw,h=self.request('GET','/');self.assertEqual(status,200);self.assertIn(b'KIX Capital',raw)
        self.assertEqual(h['Cache-Control'],'no-store');self.assertIn("frame-ancestors 'none'",h['Content-Security-Policy'])
        self.assertEqual(self.request('GET','/../service.py')[0],404)
    def test_cross_origin_and_host_denied(self):
        self.assertEqual(self.request('GET','/api/state',headers={'Host':'evil.example'})[0],403)
        self.assertEqual(self.request('GET','/api/state',headers={'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('GET','/api/state',headers={'Sec-Fetch-Site':'cross-site'})[0],403)
        self.assertEqual(self.request('POST','/api/commands','{}',{'Content-Type':'application/json'})[0],403)
    def test_invalid_json_and_schema(self):
        for body in ['{','{"op":1,"op":2}','NaN','[]','['*1500+']'*1500]:
            self.assertEqual(self.post(body)[0],400)
        self.assertEqual(self.post('x'*8193)[0],413)
        self.assertEqual(self.post('{}',**{'Content-Type':'text/plain'})[0],415)
    def test_unicode_surrogate_rejection_receipt(self):
        body=self.payload();body['operation_id']='unicode';body['args']['fixture_id']='\ud800'
        status,raw,_=self.post(json.dumps(body));self.assertEqual(status,200)
        self.assertEqual(json.loads(raw)['error'],'UNKNOWN_SETTLEMENT')
    def test_command_and_receipt_endpoint(self):
        body=self.payload();status,raw,_=self.post(json.dumps(body));self.assertEqual(status,200)
        self.assertEqual(json.loads(raw)['outcome'],'ACCEPTED')
        path=f"/api/operations/http-case?instance_id={body['instance_id']}"
        self.assertEqual(json.loads(self.request('GET',path)[1])['outcome'],'ACCEPTED')
        self.assertTrue(json.loads(self.request('GET','/api/export')[1])['replay_matched'])
    def test_readonly_routes_and_unknown_scenario(self):
        for path in ['/api/scenarios','/api/scenarios/full-after','/api/readiness']:
            self.assertEqual(self.request('GET',path)[0],200)
            self.assertEqual(self.request('GET',path,headers={'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('GET','/api/scenarios/unknown')[0],404)
        self.assertEqual(self.request('GET','/api/preview/sim-http?instance_id=old')[0],409)
        self.assertEqual(self.request('POST','/api/scenarios','{}',{'Content-Type':'application/json','X-Capital-Token':self.state()['local_token']})[0],404)

    def test_old_session_never_applies(self):
        body=self.payload();body['instance_id']='old'
        self.assertEqual(self.post(json.dumps(body))[0],409)


class OperatorReasonTests(unittest.TestCase):
    invalid = ['', None, 5, True, 'x' * 201, 'é', '\n', '\x7f', '\x00', '\t', '\ud800']

    @staticmethod
    def command(service, **extra):
        return dict(instance_id=service.instance_id, operation_id='reason-offer', op='offer',
                    advance_id='sim-reason', args={'fixture_id': 'sim-committed', 'amount': 100}, **extra)

    def test_context_does_not_change_identity_and_absent_receipt_is_unchanged(self):
        from tests import facade_schema
        contract = facade_schema.load_contract()
        for reason in ['x', 'x' * 200, '<b>x</b>', ' ']:
            with self.subTest(reason=reason):
                plain, noted = CapitalService(), CapitalService()
                noted.instance_id = plain.instance_id
                request = self.command(noted, operator_reason=reason)
                facade_schema.validate(request, next(r for r in contract['routes'] if r['path'] == '/api/commands')['request'], contract)
                old, new = plain.execute(self.command(plain)), noted.execute(request)
                self.assertEqual(new.pop('operator_reason'), reason)
                self.assertEqual(new, old)
                self.assertEqual(noted.receipts['reason-offer']['fingerprint'], plain.receipts['reason-offer']['fingerprint'])
                duplicate = noted.execute(request)
                self.assertTrue(duplicate['transport_duplicate'])
                self.assertEqual(duplicate['operator_reason'], reason)
                facade_schema.validate(duplicate, contract['definitions']['accepted_receipt'], contract)
                for replacement in [{}, {'operator_reason': 'changed'}]:
                    with self.assertRaisesRegex(ApiError, 'IDEMPOTENCY_CONFLICT'):
                        noted.execute(self.command(noted, **replacement))
                self.assertTrue(noted.export()['replay_matched'])
        service = CapitalService()
        request = self.command(service, operator_reason='rejected context')
        request['args']['amount'] = -1
        receipt = service.execute(request)
        self.assertEqual(receipt['outcome'], 'REJECTED')
        self.assertEqual(receipt['operator_reason'], 'rejected context')
        facade_schema.validate(receipt, contract['definitions']['rejected_receipt'], contract)

    def test_invalid_context_precedes_idempotency_and_apply(self):
        from unittest import mock
        service = CapitalService()
        service.execute(self.command(service))
        before = copy.deepcopy((service.receipts, service.machine.export_journal(), service.machine.state_digest()))
        with mock.patch.object(service.producer, 'apply', side_effect=AssertionError('must not apply')):
            for reason in self.invalid:
                with self.subTest(reason=repr(reason)), self.assertRaises(ApiError) as caught:
                    service.execute(self.command(service, operator_reason=reason))
                self.assertEqual((caught.exception.status, caught.exception.code), (400, 'INVALID_REASON'))
        self.assertEqual(before, (service.receipts, service.machine.export_journal(), service.machine.state_digest()))

    def test_reason_capacity_admission_is_before_every_producer(self):
        from unittest import mock
        from capital import overlay
        from capital.store import canonical_bytes
        from capital.gate_producer import GateHttpProducer
        for gated in [False, True]:
            producer = GateHttpProducer() if gated else None
            try:
                service = CapitalService(producer=producer) if gated else CapitalService()
                payload = {'receipts': service.receipts, 'journal': service.machine.export_journal(),
                           'case_fixtures': service.case_fixtures, 'state_digest': service.machine.state_digest()}
                reason = '\\' * 200
                boundary = overlay.section_size(payload, service.overlay_entries) + len(canonical_bytes(reason)) + len('"operator_reason":') + 1
                service.overlay_bounds = {**service.overlay_bounds, 'ENVELOPE_MAX_BYTES': boundary - 1}
                before = copy.deepcopy((service.receipts, service.machine.export_journal(), service.machine.state_digest()))
                with mock.patch.object(service.producer, 'apply', wraps=service.producer.apply) as apply:
                    with self.assertRaises(ApiError) as caught:
                        service.execute(self.command(service, operator_reason=reason))
                    self.assertEqual(caught.exception.code, 'SIMULATION_CAPACITY')
                    self.assertEqual(caught.exception.detail['bound'], 'ENVELOPE_MAX_BYTES')
                    apply.assert_not_called()
                self.assertEqual(before, (service.receipts, service.machine.export_journal(), service.machine.state_digest()))
                service.overlay_bounds['ENVELOPE_MAX_BYTES'] = boundary
                self.assertEqual(service.execute(self.command(service, operator_reason=reason))['outcome'], 'ACCEPTED')
            finally:
                if producer is not None:
                    producer.close()

    def test_http_validation_and_agent_precedence_leave_workspace_unchanged(self):
        import tempfile
        from tests.test_repayment_posting import body as payment_body, whole
        with tempfile.TemporaryDirectory() as directory:
            server = make_server(0, workspace=Path(directory) / 'ws')
            worker = threading.Thread(target=server.serve_forever)
            worker.start()
            try:
                service = server.service
                token = json.loads(self.http(server, 'GET', '/api/state')[1])['local_token']
                commands = [('/api/commands', self.command(service)),
                            ('/api/overlay/commands', dict(instance_id=service.instance_id, operation_id='reason-clock',
                              op='advance_day', from_sim_day=0, to_sim_day=1, reason='SIMULATED test')),
                            ('/api/overlay/commands', payment_body(service, 'reason-pay', 1))]
                path = Path(directory) / 'ws' / 'workspace.json'
                before = (whole(service), path.read_bytes() if path.exists() else None)
                for route, body in commands:
                    for reason in self.invalid:
                        status, raw = self.http(server, 'POST', route, {**body, 'operator_reason': reason}, token)
                        self.assertEqual((status, json.loads(raw)['error']), (400, 'INVALID_REASON'))
                self.assertEqual(before, (whole(service), path.read_bytes() if path.exists() else None))
                for index, reason in enumerate(['x', 'x' * 200]):
                    request = self.command(service, operator_reason=reason)
                    request.update(operation_id=f'http-reason-{index}', advance_id=f'sim-http-reason-{index}')
                    status, raw = self.http(server, 'POST', '/api/commands', request, token)
                    self.assertEqual(status, 200)
                    self.assertEqual(json.loads(raw)['operator_reason'], reason)
                status, raw = self.http(server, 'POST', '/api/session', {'role': 'agent'}, token)
                agent = json.loads(raw)['local_token']
                self.assertEqual(status, 200)
                for op, expected in [('default', 'RECOVERY_AGENT_FORBIDDEN'), ('draw', 'ROLE_FORBIDDEN'),
                                     ('advance_day', 'ROLE_FORBIDDEN'), ('post_repayment', 'ROLE_FORBIDDEN'),
                                     ('post_writeoff', 'RECOVERY_AGENT_FORBIDDEN'), ('post_recovery', 'RECOVERY_AGENT_FORBIDDEN'),
                                     ('register_slice', 'SLICE_AGENT_FORBIDDEN')]:
                    route = '/api/commands' if op in ['default', 'draw'] else '/api/overlay/commands'
                    status, raw = self.http(server, 'POST', route, {**commands[0][1], 'op': op, 'operator_reason': '\n'}, agent)
                    self.assertEqual((status, json.loads(raw)['error']), (403, expected), op)
            finally:
                server.shutdown(); server.server_close(); worker.join()

    @staticmethod
    def http(server, method, path, body=None, token=None):
        client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        headers = {'Content-Type': 'application/json'}
        if token: headers['X-Capital-Token'] = token
        try:
            client.request(method, path, None if body is None else json.dumps(body), headers)
            response = client.getresponse()
            return response.status, response.read()
        finally:
            client.close()


class OperatorReasonAgentTests(unittest.TestCase):
    def test_agents_cannot_attach_context_to_tools_or_change_proposals(self):
        from tests.test_agent_lane import _propose
        from tests.test_overlay import draw_book
        service = CapitalService()
        draw_book(service)
        service.agent_propose(_propose(), role='agent')
        before = copy.deepcopy(service.agent_lane.proposals)
        for proposal in [_propose(operator_reason='x'), _propose(proposal_id='sim-other', operator_reason='x')]:
            with self.assertRaises(ApiError) as caught:
                service.agent_propose(proposal, role='agent')
            self.assertEqual(caught.exception.code, 'INVALID_ARGUMENTS')
            self.assertEqual(service.agent_lane.proposals, before)
        receipt = service.execute(dict(instance_id=service.instance_id, operation_id='cited-reason', op='draw',
            advance_id='sim-a', args={}, proposal_id='sim-proposal', operator_reason='organizer context'))
        self.assertEqual(receipt['operator_reason'], 'organizer context')
        self.assertEqual(receipt['proposal_id'], 'sim-proposal')
        self.assertEqual(service.agent_lane.proposals, before)

if __name__=='__main__':unittest.main()
