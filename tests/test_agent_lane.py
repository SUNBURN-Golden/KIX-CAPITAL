"""Simulated agent lane: QUERY and PROPOSE only. Not an AgentGrant or ActionPermit."""
import importlib.util
import json
import http.client
import threading
import unittest
from pathlib import Path

from capital.agent_lane import (
    ACTIVE_GENERATION, ACTIVE_GRANT_ID, AGENT_ID, FALSE_FLAGS, PERIOD_NOT_AFTER,
    PERIOD_NOT_BEFORE, REVOKED_GENERATION, REVOKED_GRANT_ID, AgentLane, AgentLaneError,
)
from capital.auth import PROVENANCE
from capital.protocol import VENDOR
from capital.readiness import source_integrity
from capital.resources import vendor_manifest
from capital.server import make_server
from capital.service import OPS, ApiError, CapitalService, digest
from capital.terms import DecisionNoteTermsPolicy

_SCHEMA = importlib.util.spec_from_file_location(
    'facade_schema', Path(__file__).resolve().with_name('facade_schema.py'))
_facade_schema = importlib.util.module_from_spec(_SCHEMA)
_SCHEMA.loader.exec_module(_facade_schema)
load_contract = _facade_schema.load_contract
validate = _facade_schema.validate

ROOT = Path(__file__).resolve().parents[1]
PER_ACTION = 500_000_000
CUMULATIVE = 2_000_000_000
READS = (
    '/api/state',
    '/api/evidence',
    '/api/projection',
    '/api/export',
    '/api/export/manifest',
    '/api/reconciliation',
    '/api/statement',
    '/api/metrics',
    '/api/health',
    '/api/preview/sim-agent',
    '/api/underwrite/sim-agent',
)


def _call(grant_id=ACTIVE_GRANT_ID, generation=ACTIVE_GENERATION, now=1, **extra):
    body = {'grant_id': grant_id, 'generation': generation, 'now': now}
    body.update(extra)
    return body


def _propose(proposal_id='sim-proposal', surface='capital:draw', amount=100, kind='PROPOSE', **extra):
    body = _call(now=10, proposal_id=proposal_id, surface=surface, amount=amount, kind=kind)
    body.update(extra)
    return body


class AgentLaneTests(unittest.TestCase):
    def setUp(self):
        self.service = CapitalService()
        self.lane = self.service.agent_lane

    def raises(self, call):
        with self.assertRaises(ApiError) as caught:
            call()
        return caught.exception

    def query(self, role='agent', **extra):
        return self.service.agent_query(_call(**extra), role=role)

    def propose(self, role='agent', **extra):
        return self.service.agent_propose(_propose(**extra), role=role)

    def test_limits_come_from_the_adopted_note(self):
        limits = self.lane.limits()
        depth = self.lane._depth()
        self.assertEqual(limits['per_action_max'], depth['single_advance_cap_krw'])
        self.assertEqual(limits['cumulative_max'], depth['beneficiary_aggregate_cap_krw'])
        self.assertEqual(limits['per_action_max'], PER_ACTION)
        self.assertEqual(limits['cumulative_max'], CUMULATIVE)
        self.assertEqual(limits['count_max'], 10**12)
        self.assertEqual(limits['count_max_meaning'], 'DRAFT_INPUT_CEILING_NOT_A_PRODUCT_LIMIT')
        self.assertEqual(limits['currency'], 'KRW')

    def test_query_returns_the_active_fixture_and_writes_nothing(self):
        digest_before = self.service.machine.state_digest()
        count = len(self.service.receipts)
        view = self.query()
        self.assertEqual(view['label'], 'SIMULATED')
        self.assertEqual(view['mode'], 'SIMULATED_AGENT_GRANT')
        self.assertEqual(view['provenance'], 'SIMULATED_AGENT_GRANT')
        self.assertEqual(view['upstream_receipt'], 'NONE')
        self.assertIs(view['workspace_mutated'], False)
        self.assertIs(view['duplicate'], False)
        self.assertEqual(view['action_permit'], 'NOT_BOUND')
        self.assertEqual(view['identity'], 'NOT_BOUND')
        grant = view['grant']
        self.assertEqual(grant['grant_id'], ACTIVE_GRANT_ID)
        self.assertEqual(grant['generation'], ACTIVE_GENERATION)
        self.assertEqual(grant['agent_id'], AGENT_ID)
        self.assertEqual(grant['phase'], 'ACTIVE')
        self.assertEqual(grant['authority'], ['PROPOSE', 'QUERY'])
        self.assertIs(grant['scope']['subjects'], None)
        self.assertEqual(grant['period']['not_before'], PERIOD_NOT_BEFORE)
        self.assertEqual(grant['period']['not_after'], PERIOD_NOT_AFTER)
        self.assertEqual(grant['period']['period_meaning'], 'SIMULATED_LOGICAL_WINDOW')
        for flag in FALSE_FLAGS:
            self.assertIs(view[flag], False, flag)
        self.assertEqual(self.lane.proposals, {})
        self.assertIsNone(self.service.storage.load())
        self.assertEqual(self.service.machine.state_digest(), digest_before)
        self.assertEqual(len(self.service.receipts), count)

    def test_period_and_generation_and_revocation(self):
        self.assertEqual(self.query(now=PERIOD_NOT_BEFORE)['grant']['phase'], 'ACTIVE')
        self.assertEqual(self.query(now=PERIOD_NOT_AFTER)['grant']['phase'], 'ACTIVE')
        early = self.raises(lambda: self.query(now=0))
        self.assertEqual((early.code, early.status), ('GRANT_NOT_CURRENT', 403))
        expired = self.raises(lambda: self.query(now=PERIOD_NOT_AFTER + 1))
        self.assertEqual((expired.code, expired.status), ('GRANT_EXPIRED', 403))
        stale = self.raises(lambda: self.query(generation=ACTIVE_GENERATION - 1))
        self.assertEqual(stale.code, 'GRANT_NOT_CURRENT')
        revoked = self.raises(lambda: self.query(
            grant_id=REVOKED_GRANT_ID, generation=REVOKED_GENERATION))
        self.assertEqual((revoked.code, revoked.status), ('GRANT_REVOKED', 403))
        wrong_gen = self.raises(lambda: self.query(
            grant_id=REVOKED_GRANT_ID, generation=ACTIVE_GENERATION))
        self.assertEqual(wrong_gen.code, 'GRANT_NOT_CURRENT')
        missing = self.raises(lambda: self.query(grant_id='sim-grant-missing'))
        self.assertEqual((missing.code, missing.status), ('UNKNOWN_GRANT', 404))
        self.assertEqual(self.lane.proposals, {})

    def test_execute_and_limits_and_pending_proposal(self):
        refused = self.raises(lambda: self.propose(kind='EXECUTE', proposal_id='sim-exec'))
        self.assertEqual((refused.code, refused.status), ('EXECUTE_AUTHORITY_DISABLED', 403))
        self.assertNotIn('sim-exec', self.lane.proposals)
        direct = self.raises(lambda: self.service.agent_execute({'kind': 'EXECUTE'}, role='agent'))
        self.assertEqual(direct.code, 'EXECUTE_AUTHORITY_DISABLED')
        self.assertEqual(direct.detail['role'], 'agent')
        self.assertEqual(self.lane.proposals, {})
        over = self.raises(lambda: self.propose(amount=PER_ACTION + 1, proposal_id='sim-over'))
        self.assertEqual((over.code, over.status), ('PER_ACTION_EXCEEDED', 400))
        for index in range(4):
            view = self.propose(amount=PER_ACTION, proposal_id=f'sim-full-{index}', now=20 + index)
            self.assertEqual(view['proposal']['phase'], 'HUMAN_PENDING')
            self.assertIs(view['proposal']['effects_executed'], False)
            self.assertIs(view['proposal']['decision'], None)
            self.assertIs(view['proposal']['two_person_required'], True)
            self.assertIs(view['effects_executed'], False)
            self.assertIs(view['execution_enabled'], False)
        cumulative = self.raises(lambda: self.propose(amount=1, proposal_id='sim-cumulative'))
        self.assertEqual((cumulative.code, cumulative.status), ('CUMULATIVE_EXCEEDED', 400))
        self.assertNotIn('sim-cumulative', self.lane.proposals)
        digest_before = self.service.machine.state_digest()
        self.assertEqual(len(self.service.receipts), 0)
        self.assertEqual(self.service.machine.state_digest(), digest_before)
        self.assertIsNone(self.service.storage.load())

    def test_duplicate_does_not_recharge_or_recheck_the_window(self):
        first = self.propose(proposal_id='sim-dup', amount=40_000_000, subject='sim-case')
        self.assertIs(first['duplicate'], False)
        self.assertIs(first['proposal']['two_person_required'], False)
        again = self.propose(proposal_id='sim-dup', amount=40_000_000, subject='sim-case', now=PERIOD_NOT_AFTER + 5)
        self.assertIs(again['duplicate'], True)
        self.assertEqual(again['proposal']['phase'], 'HUMAN_PENDING')
        charged, count = self.lane._charged(ACTIVE_GRANT_ID)
        self.assertEqual((charged, count), (40_000_000, 1))
        conflict = self.raises(lambda: self.propose(
            proposal_id='sim-dup', amount=40_000_000, surface='capital:close', now=PERIOD_NOT_AFTER + 5))
        self.assertEqual((conflict.code, conflict.status), ('PROPOSAL_BINDING_CONFLICT', 409))
        above = self.propose(proposal_id='sim-two', amount=50_000_001)
        self.assertIs(above['proposal']['two_person_required'], True)
        edge = self.propose(proposal_id='sim-edge', amount=50_000_000)
        self.assertIs(edge['proposal']['two_person_required'], False)

    def test_bad_arguments_and_unbound_note(self):
        self.assertEqual(self.raises(lambda: self.query(now=-1)).code, 'INVALID_PERIOD')
        self.assertEqual(self.raises(lambda: self.query(generation=0)).code, 'INVALID_ARGUMENTS')
        self.assertEqual(self.raises(lambda: self.propose(amount=0)).code, 'INVALID_AMOUNT')
        self.assertEqual(self.raises(lambda: self.propose(amount=True)).code, 'INVALID_AMOUNT')
        self.assertEqual(self.raises(lambda: self.propose(surface='capital:nope')).code, 'SCOPE_VIOLATION')
        denied = self.raises(lambda: self.service.agent_query(_call(), role='organizer'))
        self.assertEqual(denied.code, 'ROLE_FORBIDDEN')
        self.assertEqual(denied.detail['permission'], 'agent:query_grant')
        auditor = self.raises(lambda: self.service.agent_propose(_propose(), role='auditor'))
        self.assertEqual(auditor.detail['permission'], 'agent:propose_action')
        unbound = AgentLane(DecisionNoteTermsPolicy(ROOT / 'docs' / 'missing-terms-note.md'))
        with self.assertRaises(AgentLaneError) as caught:
            unbound.query_grant(_call())
        self.assertEqual(caught.exception.code, 'NOT_BOUND')

    def test_count_ceiling_is_checked_after_money(self):
        self.lane.proposals['sim-count'] = {
            'grant_id': ACTIVE_GRANT_ID, 'phase': 'HUMAN_PENDING', 'amount': 1,
        }
        grant = {'grant_id': ACTIVE_GRANT_ID, 'limits': {
            'per_action_max': 10, 'cumulative_max': 100, 'count_max': 1,
        }}
        with self.assertRaises(AgentLaneError) as caught:
            self.lane._require_room(grant, 1)
        self.assertEqual(caught.exception.code, 'COUNT_EXCEEDED')
        money = {'grant_id': ACTIVE_GRANT_ID, 'limits': {
            'per_action_max': 10, 'cumulative_max': 1, 'count_max': 1,
        }}
        with self.assertRaises(AgentLaneError) as cumulative:
            self.lane._require_room(money, 1)
        self.assertEqual(cumulative.exception.code, 'CUMULATIVE_EXCEEDED')

    def test_tool_not_allowed_when_the_fixture_authority_is_narrowed(self):
        real = self.lane._grants

        def narrowed():
            grants = real()
            grants[ACTIVE_GRANT_ID]['authority'] = ['QUERY']
            return grants

        self.lane._grants = narrowed
        try:
            caught = self.raises(lambda: self.propose())
        finally:
            self.lane._grants = real
        self.assertEqual((caught.code, caught.status), ('TOOL_NOT_ALLOWED', 403))
        self.assertEqual(self.lane.proposals, {})

    def test_citation_stamps_the_receipt_and_leaves_the_fingerprint(self):
        proposal_id = 'sim-cite'
        proposed = self.propose(proposal_id=proposal_id, surface='capital:offer', amount=100)
        self.assertEqual(proposed['proposal']['phase'], 'HUMAN_PENDING')
        self.assertIs(proposed['proposal']['effects_executed'], False)
        body = {
            'instance_id': self.service.instance_id,
            'operation_id': 'sim-cite-op',
            'op': 'offer',
            'advance_id': 'sim-agent-cite',
            'args': {'fixture_id': 'sim-committed', 'amount': 100},
            'proposal_id': proposal_id,
        }
        receipt = self.service.execute(body)
        self.assertEqual(receipt['outcome'], 'ACCEPTED')
        self.assertEqual(receipt['proposal_id'], proposal_id)
        self.assertEqual(receipt['role'], 'organizer')
        stored = self.service.receipts['sim-cite-op']
        identity = {
            'operation_id': body['operation_id'], 'op': body['op'],
            'advance_id': body['advance_id'], 'args': body['args'],
        }
        self.assertEqual(stored['fingerprint'], digest(identity))
        self.assertNotEqual(stored['fingerprint'], digest({**identity, 'proposal_id': proposal_id}))
        self.assertNotIn('proposal_id', identity)
        row = self.lane.proposals[proposal_id]
        self.assertEqual(row['phase'], 'HUMAN_PENDING')
        self.assertIs(row['effects_executed'], False)
        replay = dict(body)
        replay['proposal_id'] = 'sim-other-citation'
        duplicate = self.service.execute(replay)
        self.assertIs(duplicate['transport_duplicate'], True)
        self.assertEqual(duplicate['proposal_id'], proposal_id)
        self.assertNotIn('sim-other-citation', self.lane.proposals)
        self.assertIs(self.lane.proposals[proposal_id]['effects_executed'], False)
        mismatch = dict(body)
        mismatch['operation_id'] = 'sim-cite-mismatch'
        mismatch['proposal_id'] = 'sim-amount-mismatch'
        mismatch['args'] = {'fixture_id': 'sim-committed', 'amount': 99}
        self.propose(proposal_id='sim-amount-mismatch', surface='capital:offer', amount=100)
        conflict = self.raises(lambda: self.service.execute(mismatch))
        self.assertEqual((conflict.code, conflict.status), ('PROPOSAL_BINDING_CONFLICT', 409))
        self.assertNotIn('sim-cite-mismatch', self.service.receipts)
        draw = dict(body)
        draw['operation_id'] = 'sim-cite-draw'
        draw['op'] = 'draw'
        draw['args'] = {}
        draw['proposal_id'] = proposal_id
        surface = self.raises(lambda: self.service.execute(draw))
        self.assertEqual(surface.code, 'PROPOSAL_BINDING_CONFLICT')
        unknown = dict(body)
        unknown['operation_id'] = 'sim-cite-unknown'
        unknown['proposal_id'] = 'sim-not-stored'
        missing = self.raises(lambda: self.service.execute(unknown))
        self.assertEqual((missing.code, missing.status), ('UNKNOWN_PROPOSAL', 404))
        bad = dict(body)
        bad['operation_id'] = 'sim-cite-bad'
        bad['proposal_id'] = ' sim-spaced'
        self.assertEqual(self.raises(lambda: self.service.execute(bad)).code, 'INVALID_ARGUMENTS')
        self.assertNotIn('sim-cite-bad', self.service.receipts)
        document = self.service.storage.load()
        self.assertEqual(set(document['payload']), {'receipts', 'journal', 'case_fixtures', 'state_digest'})
        self.assertNotIn('proposals', document['payload'])

    def test_a_new_process_does_not_keep_the_proposal_register(self):
        self.propose(proposal_id='sim-restart', surface='capital:approve', amount=10)
        fresh = CapitalService()
        body = {
            'instance_id': fresh.instance_id,
            'operation_id': 'sim-restart-op',
            'op': 'approve',
            'advance_id': 'sim-agent-restart',
            'args': {},
            'proposal_id': 'sim-restart',
        }
        missing = self.raises(lambda: fresh.execute(body))
        self.assertEqual(missing.code, 'UNKNOWN_PROPOSAL')
        self.assertEqual(fresh.agent_lane.proposals, {})

    def test_agent_cannot_run_commands(self):
        digest_before = self.service.machine.state_digest()
        for op in OPS:
            args = {'fixture_id': 'sim-committed', 'amount': 100} if op == 'offer' else (
                {'amount': 1, 'sequence': 1} if op == 'repay' else {})
            body = {
                'instance_id': self.service.instance_id,
                'operation_id': f'sim-agent-{op}',
                'op': op,
                'advance_id': 'sim-agent-denied',
                'args': args,
            }
            caught = self.raises(lambda body=body: self.service.execute(body, role='agent'))
            self.assertEqual((caught.code, caught.status), ('ROLE_FORBIDDEN', 403))
            self.assertEqual(caught.detail['permission'], f'command:{op}')
            self.assertEqual(caught.detail['role'], 'agent')
        self.assertEqual(self.service.receipts, {})
        self.assertEqual(self.service.machine.state_digest(), digest_before)

    def test_false_flags_are_schema_constants_and_the_seam_stays_unbound(self):
        doc = load_contract()
        for name in ('agent_query_response', 'agent_proposal_response'):
            props = doc['definitions'][name]['properties']
            for flag in FALSE_FLAGS:
                self.assertEqual(props[flag], {'const': False}, (name, flag))
        self.assertEqual(
            doc['definitions']['agent_proposal_view']['properties']['effects_executed'],
            {'const': False})
        self.assertEqual(
            doc['definitions']['agent_proposal_view']['properties']['phase'],
            {'const': 'HUMAN_PENDING'})
        self.assertIs(doc['definitions']['agent_proposal_view']['properties']['decision']['const'], None)
        report = source_integrity(VENDOR, vendor_manifest())
        self.assertIs(report['all_matched'], True)
        self.assertEqual(vendor_manifest()['commit'], '7481b0e16ce9b903abbffa62249bb91cd9e63cfe')
        self.assertEqual(len(vendor_manifest()['files']), 5)
        names = {path.name for path in (ROOT / 'capital' / 'vendor').rglob('*') if path.is_file()}
        self.assertNotIn('ai_delegation_mock.py', names)
        text = (ROOT / 'docs' / 'SEAMS.md').read_text(encoding='utf-8')
        row = next(line for line in text.splitlines() if line.startswith('| AuthorizerPort |'))
        cells = [cell.strip() for cell in row.strip('|').split('|')]
        self.assertEqual(cells[4], 'NOT_BOUND')
        self.assertEqual(cells[5], 'NONE')


class AgentHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.port = cls.server.server_port
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        cls.doc = load_contract()

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
        client = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        client.request(method, path, body=payload, headers=headers)
        response = client.getresponse()
        raw = response.read()
        status = response.status
        client.close()
        return status, json.loads(raw.decode())

    def organizer_token(self):
        status, body = self.request('GET', '/api/state')
        self.assertEqual(status, 200)
        return body['local_token'], body

    def agent_token(self):
        organizer, _state = self.organizer_token()
        status, opened = self.request('POST', '/api/session', {'role': 'agent'}, organizer)
        self.assertEqual(status, 200, opened)
        validate(opened, self.doc['definitions']['session'], self.doc)
        validate({'role': 'agent'}, self.doc['definitions']['session_request'], self.doc)
        self.assertEqual(opened['agent_grant'], 'NOT_BOUND')
        self.assertEqual(opened['action_permit'], 'NOT_BOUND')
        self.assertEqual(opened['identity'], 'NOT_BOUND')
        self.assertEqual(opened['role_provenance'], PROVENANCE)
        return opened['local_token']

    def test_agent_token_can_query_and_propose_and_nothing_else(self):
        token = self.agent_token()
        query = _call()
        validate(query, self.doc['definitions']['agent_query_request'], self.doc)
        status, view = self.request('POST', '/api/agent/query_grant', query, token)
        self.assertEqual(status, 200, view)
        validate(view, self.doc['definitions']['agent_query_response'], self.doc)
        self.assertEqual(view['grant']['phase'], 'ACTIVE')
        proposal = _propose(proposal_id='sim-http', surface='capital:offer', amount=100)
        validate(proposal, self.doc['definitions']['agent_propose_request'], self.doc)
        status, proposed = self.request('POST', '/api/agent/propose_action', proposal, token)
        self.assertEqual(status, 200, proposed)
        validate(proposed, self.doc['definitions']['agent_proposal_response'], self.doc)
        self.assertEqual(proposed['proposal']['phase'], 'HUMAN_PENDING')
        self.assertIs(proposed['proposal']['effects_executed'], False)
        for flag in ('execution_enabled', 'issued', 'paid', 'signed', 'transferred'):
            self.assertIs(proposed[flag], False, flag)
        status, executed = self.request('POST', '/api/agent/execute', {'kind': 'EXECUTE'}, token)
        self.assertEqual(status, 403, executed)
        self.assertEqual(executed['error'], 'EXECUTE_AUTHORITY_DISABLED')
        validate(executed, self.doc['definitions']['error_envelope'], self.doc)
        organizer, state = self.organizer_token()
        instance = state['instance_id']
        for op in OPS:
            args = {'fixture_id': 'sim-committed', 'amount': 100} if op == 'offer' else (
                {'amount': 1, 'sequence': 1} if op == 'repay' else {})
            status, payload = self.request('POST', '/api/commands', {
                'instance_id': instance, 'operation_id': f'sim-http-{op}', 'op': op,
                'advance_id': 'sim-http-denied', 'args': args,
            }, token)
            self.assertEqual(status, 403, (op, payload))
            self.assertEqual(payload['error'], 'ROLE_FORBIDDEN')
            self.assertEqual(payload['permission'], 'command:submit')
            self.assertEqual(payload['role'], 'agent')
        status, session = self.request('POST', '/api/session', {'role': 'observer'}, token)
        self.assertEqual((status, session['error'], session['permission']), (403, 'ROLE_FORBIDDEN', 'session:bind'))
        for path in READS:
            status, payload = self.request('GET', path, token=token)
            self.assertEqual(status, 403, (path, payload))
            self.assertEqual(payload['error'], 'ROLE_FORBIDDEN')
            self.assertEqual(payload['role'], 'agent')
        for path, permission in (
            ('/api/agent/query_grant', 'agent:query_grant'),
            ('/api/agent/propose_action', 'agent:propose_action'),
            ('/api/agent/execute', 'agent:propose_action'),
        ):
            status, payload = self.request('POST', path, {'ignored': True}, organizer)
            self.assertEqual(status, 403, (path, payload))
            self.assertEqual(payload['error'], 'ROLE_FORBIDDEN')
            self.assertEqual(payload['permission'], permission)
        bare, bare_body = self.request('POST', '/api/agent/query_grant', query)
        self.assertEqual((bare, bare_body['error']), (403, 'LOCAL_TOKEN_REQUIRED'))
        status, receipt = self.request('POST', '/api/commands', {
            'instance_id': instance, 'operation_id': 'sim-http-cite', 'op': 'offer',
            'advance_id': 'sim-http-cite', 'args': {'fixture_id': 'sim-committed', 'amount': 100},
            'proposal_id': 'sim-http',
        }, organizer)
        self.assertEqual(status, 200, receipt)
        validate(receipt, self.doc['definitions']['accepted_receipt'], self.doc)
        self.assertEqual(receipt['proposal_id'], 'sim-http')
        self.assertIs(receipt['funds_executed'], False)
        stored = self.server.service.agent_lane.proposals['sim-http']
        self.assertEqual(stored['phase'], 'HUMAN_PENDING')
        self.assertIs(stored['effects_executed'], False)
        after = self.server.service
        frozen = (after.machine.state_digest(), len(after.receipts), dict(after.agent_lane.proposals))
        status, again = self.request('POST', '/api/agent/query_grant', query, token)
        self.assertEqual(status, 200, again)
        self.assertEqual(after.machine.state_digest(), frozen[0])
        self.assertEqual(len(after.receipts), frozen[1])
        self.assertEqual(after.agent_lane.proposals['sim-http']['effects_executed'], False)
        kind = _propose(proposal_id='sim-http-exec', kind='EXECUTE')
        status, refused = self.request('POST', '/api/agent/propose_action', kind, token)
        self.assertEqual((status, refused['error']), (403, 'EXECUTE_AUTHORITY_DISABLED'))
        self.assertNotIn('sim-http-exec', after.agent_lane.proposals)


if __name__ == '__main__':
    unittest.main()
