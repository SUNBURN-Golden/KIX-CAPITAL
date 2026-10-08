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
        self.assertEqual(len(self.service.fixtures.rows),3)
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

if __name__=='__main__':unittest.main()
