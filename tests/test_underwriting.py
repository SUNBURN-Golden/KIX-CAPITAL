"""Simulated underwriting decision record: EVIDENCE_RULES_V1 checks U1-U6."""
import copy
import json
import re
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from capital.service import ApiError, CapitalService
from capital.server import make_server
from capital.terms import DecisionNoteTermsPolicy
from capital.underwriting import (
    UNDERWRITE_LABEL, DecisionNoteUnderwriting, UnderwritingPort,
)

ROOT = Path(__file__).resolve().parents[1]
NOTE = ROOT / 'docs' / 'decisions' / 'CAPITAL_FINANCIAL_TERMS.md'
CONTRACT = ROOT / 'capital' / 'contract' / 'facade-v1.json'
_FENCE = re.compile(r'```capital-decision-v1[ \t]*\n(.*?)```', re.DOTALL)
_U1, _U2, _U3, _U4, _U5, _U6 = (
    'U1_SETTLEMENT_EVIDENCE', 'U2_REFUND_EXPOSURE', 'U3_BORROWING_BASE',
    'U4_CONCENTRATION', 'U5_DECISION_AUTHORITY', 'U6_KYC_AML_STATUS',
)


def note_block():
    blocks = _FENCE.findall(NOTE.read_text(encoding='utf-8'))
    return json.loads(blocks[0])


def depth():
    return note_block()['entries']['underwriting_depth']['value']


def margin():
    return note_block()['entries']['additional_margin']['value']


def write_note(directory, mutate):
    text = NOTE.read_text(encoding='utf-8')
    match = _FENCE.search(text)
    block = json.loads(match.group(1))
    mutate(block)
    body = json.dumps(block, ensure_ascii=False, indent=2)
    path = Path(directory) / 'note.md'
    path.write_text(
        text[:match.start()] + '```capital-decision-v1\n' + body + '\n```' + text[match.end()],
        encoding='utf-8')
    return path


def _has_number(value):
    if type(value) is bool:
        return False
    if type(value) is int or type(value) is float:
        return True
    if type(value) is dict:
        return any(_has_number(item) for item in value.values())
    if type(value) is list:
        return any(_has_number(item) for item in value)
    return False


def check_of(record, check_id):
    return next(row for row in record['checks'] if row['id'] == check_id)


class UnderwritingServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = CapitalService()
        self.counter = 0

    def command(self, op, case='sim-a', **args):
        self.counter += 1
        return self.service.execute({
            'instance_id': self.service.instance_id,
            'operation_id': f'uw-{self.counter}',
            'op': op,
            'advance_id': case,
            'args': args,
        })

    def ready(self, case='sim-a', amount=60000, fixture='sim-committed', bound=True):
        self.assertEqual(
            self.command('offer', case, fixture_id=fixture, amount=amount)['outcome'], 'ACCEPTED')
        self.assertEqual(self.command('approve', case)['outcome'], 'ACCEPTED')
        if bound:
            self.assertEqual(self.command('bind_settlement', case)['outcome'], 'ACCEPTED')

    def record(self, advance_id, **kwargs):
        return self.service.underwrite(
            advance_id, self.service.instance_id, 'organizer', **kwargs)

    def test_candidate_on_committed_passes_all_six_checks(self):
        body = self.record('sim-committed', sim_day=0, amount=60000)
        self.assertEqual(body['label'], UNDERWRITE_LABEL)
        self.assertEqual(body['mode'], 'SIMULATED_UNDERWRITING_RECORD')
        self.assertIs(body['provisional'], True)
        self.assertEqual(body['status'], 'BOUND')
        self.assertEqual(body['rules_version'], depth()['depth'])
        self.assertEqual(body['terms_version'], note_block()['terms_version'])
        self.assertIs(body['candidate'], True)
        self.assertEqual(body['phase'], 'CANDIDATE')
        self.assertEqual(body['tier'], 'T1')
        self.assertEqual(body['decided_by_role'], 'organizer')
        self.assertIs(body['kyc_executed'], False)
        self.assertIs(body['underwriting_executed'], False)
        self.assertIs(body['funds_executed'], False)
        self.assertIs(body['workspace_mutated'], False)
        self.assertIs(body['write_authorized'], False)
        self.assertEqual([row['id'] for row in body['checks']],
                         [item['id'] for item in depth()['checks_ordered']])
        self.assertTrue(all(row['outcome'] == 'PASS' for row in body['checks']))
        self.assertIsNone(body['failed_check'])
        self.assertEqual(body['proposal'], 'APPROVE')
        base = body['borrowing_base']
        self.assertEqual(base['advance_rate_bps'],
                         margin()['advance_rate_bps_by_tier']['T1_COMMIT_OBSERVED'])
        self.assertEqual(base['base_krw'],
                         base['eligible_face'] * base['advance_rate_bps'] // 10000)
        remaining = body['caps_remaining']
        self.assertEqual(remaining['single_advance_krw'],
                         depth()['single_advance_cap_krw'] - 60000)
        self.assertEqual(remaining['beneficiary_aggregate_krw'],
                         depth()['beneficiary_aggregate_cap_krw'] - 60000)
        self.assertEqual(remaining['portfolio_krw'], depth()['portfolio_cap_krw'] - 60000)
        self.assertIs(body['two_person_required'], False)
        self.assertIsInstance(body['sim_day'], int)
        self.assertRegex(body['inputs_digest'], r'[0-9a-f]{64}\Z')
        self.assertIsInstance(body['observed_state_digest'], str)

    def test_inputs_digest_is_stable_and_tracks_inputs(self):
        first = self.record('sim-committed', sim_day=0, amount=60000)['inputs_digest']
        self.assertEqual(first, self.record('sim-committed', sim_day=0, amount=60000)['inputs_digest'])
        fresh_service = CapitalService()
        fresh = fresh_service.underwrite(
            'sim-committed', fresh_service.instance_id, 'organizer',
            sim_day=0, amount=60000)
        self.assertEqual(first, fresh['inputs_digest'])
        changed = {
            'amount': self.record('sim-committed', sim_day=0, amount=60001)['inputs_digest'],
            'sim_day': self.record('sim-committed', sim_day=1, amount=60000)['inputs_digest'],
            'fixture': self.record('sim-pending', sim_day=0, amount=60000)['inputs_digest'],
        }
        self.assertEqual(len({first, *changed.values()}), 1 + len(changed))
        auditor = self.service.underwrite(
            'sim-committed', self.service.instance_id, 'auditor', sim_day=0, amount=60000)
        self.assertNotEqual(first, auditor['inputs_digest'])
        self.assertEqual(auditor['decided_by_role'], 'auditor')

    def test_bound_drawn_case_uses_the_recorded_offer_amount(self):
        self.ready()
        self.assertEqual(self.command('draw')['outcome'], 'ACCEPTED')
        body = self.record('sim-a')
        self.assertIs(body['candidate'], False)
        self.assertEqual(body['phase'], 'DRAWN')
        self.assertEqual(body['amount'], 60000)
        self.assertEqual(body['tier'], 'T1')
        self.assertIsNone(body['failed_check'])
        self.assertEqual(check_of(body, _U6)['detail']['kyc_executed'], False)
        with self.assertRaises(ApiError):
            self.record('sim-a', amount=1)

    def test_u1_fails_on_a_captured_not_committed_fixture(self):
        body = self.record('sim-pending', amount=1000)
        self.assertEqual(body['tier'], 'NOT_APPLICABLE')
        u1 = check_of(body, _U1)
        self.assertEqual(u1['outcome'], 'FAIL')
        self.assertEqual(u1['detail']['reason'], 'SETTLEMENT_NOT_COMMITTED')
        self.assertEqual(body['failed_check'], _U1)
        self.assertEqual(body['proposal'], 'DECLINE')
        self.assertIsNone(body['borrowing_base'])

    def test_unbound_case_resolves_t2_and_its_note_rate(self):
        self.ready(bound=False)
        body = self.record('sim-a')
        self.assertEqual(body['tier'], 'T2')
        self.assertEqual(body['gate'], 'UNBOUND')
        self.assertEqual(body['borrowing_base']['advance_rate_bps'],
                         margin()['advance_rate_bps_by_tier']['T2_UNBOUND'])

    def test_two_person_threshold_marks_the_record_only(self):
        threshold = depth()['two_person_threshold_krw']
        above = self.record('sim-committed', amount=threshold + 1)
        self.assertIs(above['two_person_required'], True)
        self.assertEqual(check_of(above, _U5)['outcome'], 'PASS')
        at = self.record('sim-committed', amount=threshold)
        self.assertIs(at['two_person_required'], False)

    def test_open_refund_fails_u2_and_preserves_state(self):
        before = (
            copy.deepcopy(self.service.receipts),
            self.service.machine.state_digest(),
            len(self.service.receipts),
            self.service.machine.export_journal(),
        )
        body = self.record('sim-refund', amount=60000)
        u2 = check_of(body, _U2)
        self.assertEqual(u2['outcome'], 'FAIL')
        self.assertEqual(u2['detail']['reason'], 'REFUND_OBLIGATION_OPEN')
        claim = self.service.fixtures.view('sim-refund')['claim']
        self.assertEqual(u2['detail']['refund_face'], claim['refund_face'])
        self.assertEqual(u2['detail']['refund_outstanding'], claim['refund_outstanding'])
        self.assertEqual(body['failed_check'], _U2)
        self.assertEqual(body['proposal'], 'DECLINE')
        after = (
            self.service.receipts, self.service.machine.state_digest(),
            len(self.service.receipts), self.service.machine.export_journal())
        self.assertEqual(after, before)
        self.assertEqual(body['observed_state_digest'], before[1])

    def test_approve_stays_a_caller_decision_on_a_decline(self):
        self.assertEqual(
            self.command('offer', 'sim-a', fixture_id='sim-committed', amount=60000)['outcome'],
            'ACCEPTED')
        body = self.record('sim-a')
        self.assertEqual(body['proposal'], 'DECLINE')
        self.assertEqual(body['failed_check'], _U3)
        self.assertEqual(self.command('approve', 'sim-a')['outcome'], 'ACCEPTED')
        self.assertEqual(self.service.machine.view('sim-a')['phase'], 'APPROVED')

    def test_missing_and_undetermined_notes_stay_not_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_note(tmp, lambda block: block['entries'].__setitem__(
                'underwriting_depth', {**block['entries']['underwriting_depth'],
                                       'status': 'UNDETERMINED'}))
            partial = CapitalService(terms=DecisionNoteTermsPolicy(path))
            missing = CapitalService(terms=DecisionNoteTermsPolicy(Path(tmp) / 'missing.md'))
        for service in (partial, missing):
            before = (service.machine.state_digest(), len(service.receipts))
            body = service.underwrite(
                'sim-committed', service.instance_id, 'organizer', sim_day=0, amount=60000)
            self.assertEqual(body['label'], UNDERWRITE_LABEL)
            self.assertEqual(body['status'], 'NOT_BOUND')
            self.assertEqual(body['reason'], 'terms not bound')
            self.assertIsNone(body['rules_version'])
            self.assertNotIn('inputs_digest', body)
            self.assertNotIn('borrowing_base', body)
            self.assertNotIn('checks', body)
            self.assertFalse(_has_number(body))
            self.assertEqual(
                (service.machine.state_digest(), len(service.receipts)), before)

    def test_unknown_and_amount_validation(self):
        with self.assertRaises(ApiError) as caught:
            self.record('sim-missing', amount=1)
        self.assertEqual(caught.exception.code, 'UNKNOWN_ADVANCE')
        with self.assertRaises(ApiError):
            self.record('sim-committed')
        with self.assertRaises(ApiError):
            self.record('sim-committed', amount=0)
        with self.assertRaises(ApiError):
            self.record('sim-committed', amount=1, sim_day=-1)
        with self.assertRaises(ApiError) as changed:
            self.service.underwrite('sim-committed', 'other-instance', 'organizer', amount=1)
        self.assertEqual(changed.exception.code, 'SESSION_CHANGED')

    def test_port_protocol_and_subject_lock(self):
        self.assertIsInstance(self.service.underwriting, UnderwritingPort)
        self.assertIsInstance(DecisionNoteUnderwriting(self.service.terms), UnderwritingPort)


class UnderwritingHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=2)

    def get(self, path, token=None):
        headers = {} if token is None else {'X-Capital-Token': token}
        client = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        client.request('GET', path, headers=headers)
        response = client.getresponse()
        payload = json.loads(response.read().decode())
        status = response.status
        client.close()
        return status, payload

    def test_route_observer_403_and_read_only(self):
        service = self.server.service
        observer = self.server.authorizer.bind_role('observer')
        instance = service.instance_id
        before = (service.machine.state_digest(), len(service.receipts))
        code, body = self.get(
            f'/api/underwrite/sim-refund?instance_id={instance}&amount=60000&sim_day=2')
        self.assertEqual(code, 200, body)
        self.assertEqual(body['failed_check'], _U2)
        self.assertEqual(check_of(body, _U2)['detail']['reason'], 'REFUND_OBLIGATION_OPEN')
        self.assertIs(body['kyc_executed'], False)
        self.assertIs(body['underwriting_executed'], False)
        self.assertEqual(body['decided_by_role'], 'organizer')
        self.assertEqual(body['sim_day'], 2)
        self.assertEqual((service.machine.state_digest(), len(service.receipts)), before)
        code, denied = self.get(
            f'/api/underwrite/sim-committed?instance_id={instance}&amount=1000', observer)
        self.assertEqual(code, 403)
        self.assertEqual(denied['error'], 'ROLE_FORBIDDEN')
        self.assertEqual(denied['role'], 'observer')
        self.assertEqual(denied['permission'], 'projection:read')
        code, missing = self.get(
            f'/api/underwrite/sim-missing?instance_id={instance}&amount=1')
        self.assertEqual(code, 404)
        self.assertEqual(missing['error'], 'UNKNOWN_ADVANCE')
        code, no_amount = self.get(f'/api/underwrite/sim-committed?instance_id={instance}')
        self.assertEqual(code, 400)
        self.assertEqual(no_amount['error'], 'INVALID_ARGUMENTS')
        code, bad_amount = self.get(
            f'/api/underwrite/sim-committed?instance_id={instance}&amount=abc')
        self.assertEqual(code, 400)
        self.assertEqual(bad_amount['error'], 'INVALID_ARGUMENTS')
        code, changed = self.get(
            '/api/underwrite/sim-committed?instance_id=other&amount=1')
        self.assertEqual(code, 409)
        self.assertEqual(changed['error'], 'SESSION_CHANGED')
        self.assertEqual((service.machine.state_digest(), len(service.receipts)), before)

    def test_small_caps_fail_u4_and_name_the_cap(self):
        def mutate(block):
            block['entries']['underwriting_depth']['value']['single_advance_cap_krw'] = 40000

        with tempfile.TemporaryDirectory() as tmp:
            note = write_note(tmp, mutate)
            server = make_server(0, terms=DecisionNoteTermsPolicy(note))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            service = server.service
            instance = service.instance_id
            code, body = self._hit(
                server.server_port,
                f'/api/underwrite/sim-committed?instance_id={instance}&amount=60000')
            self.assertEqual(code, 200, body)
            self.assertEqual(body['failed_check'], _U4)
            u4 = check_of(body, _U4)
            self.assertEqual(u4['outcome'], 'FAIL')
            self.assertEqual(u4['detail']['reason'], 'CAP_EXCEEDED')
            self.assertEqual(u4['detail']['cap'], 'single_advance_cap_krw')
            self.assertEqual(u4['detail']['cap_krw'], 40000)
            self.assertEqual(body['caps_remaining']['single_advance_krw'], 40000 - 60000)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

    def _hit(self, port, path, token=None):
        headers = {} if token is None else {'X-Capital-Token': token}
        client = HTTPConnection('127.0.0.1', port, timeout=5)
        client.request('GET', path, headers=headers)
        response = client.getresponse()
        payload = json.loads(response.read().decode())
        status = response.status
        client.close()
        return status, payload


class UnderwritingSchemaTests(unittest.TestCase):
    def test_flags_are_schema_constants(self):
        doc = json.loads(CONTRACT.read_text(encoding='utf-8'))
        for name in ('credit_view', 'command_result', 'underwrite_bound', 'underwrite_unbound'):
            block = doc['definitions'][name]['properties']
            self.assertEqual(block['underwriting_executed'], {'const': False}, name)
            self.assertEqual(block['kyc_executed'], {'const': False}, name)
        route = next(row for row in doc['routes'] if row['path'] == '/api/underwrite/{advance_id}')
        self.assertEqual(route['method'], 'GET')
        self.assertEqual(route['dispatch'], '/api/underwrite/')
        self.assertEqual(route['permission'], 'projection:read')
        self.assertEqual(route['response'], {'$ref': '#/definitions/underwrite'})
        bound = doc['definitions']['underwrite_bound']
        for field in ('rules_version', 'inputs_digest', 'tier', 'borrowing_base',
                      'caps_remaining', 'decided_by_role', 'sim_day'):
            self.assertIn(field, bound['required'])


if __name__ == '__main__':
    unittest.main()
