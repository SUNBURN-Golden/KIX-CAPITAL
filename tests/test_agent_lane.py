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

    def test_query_subject_checks_membership_and_writes_nothing(self):
        digest_before = self.service.machine.state_digest()
        view = self.service.agent_query_subject(_call(surface='capital:draw'), role='agent')
        self.assertEqual(view['match'], {'surface': 'capital:draw', 'subject': None, 'in_scope': True})
        self.assertIs(view['subjects'], None)
        self.assertIs(view['duplicate'], False)
        with_subject = self.service.agent_query_subject(
            _call(surface='capital:offer', subject='sim-case'), role='agent')
        self.assertIs(with_subject['match']['in_scope'], True)
        bad_surface = self.raises(lambda: self.service.agent_query_subject(
            _call(surface='capital:nope'), role='agent'))
        self.assertEqual((bad_surface.code, bad_surface.status), ('SCOPE_VIOLATION', 400))
        expired = self.raises(lambda: self.service.agent_query_subject(
            _call(surface='capital:draw', now=PERIOD_NOT_AFTER + 1), role='agent'))
        self.assertEqual(expired.code, 'GRANT_EXPIRED')
        bad_args = self.raises(lambda: self.service.agent_query_subject(_call(), role='agent'))
        self.assertEqual(bad_args.code, 'INVALID_ARGUMENTS')
        denied = self.raises(lambda: self.service.agent_query_subject(
            _call(surface='capital:draw'), role='organizer'))
        self.assertEqual(denied.detail['permission'], 'agent:query_subject')
        self.assertEqual(self.lane.proposals, {})
        self.assertEqual(len(self.service.receipts), 0)
        self.assertEqual(self.service.machine.state_digest(), digest_before)

    def test_withdraw_proposal_moves_pending_to_withdrawn(self):
        self.propose(proposal_id='sim-wd', amount=PER_ACTION // 2)
        self.assertEqual(self.lane._charged(ACTIVE_GRANT_ID), (PER_ACTION // 2, 1))
        view = self.service.agent_withdraw_proposal(_call(now=30, proposal_id='sim-wd'), role='agent')
        self.assertIs(view['duplicate'], False)
        self.assertEqual(view['proposal']['phase'], 'WITHDRAWN')
        self.assertEqual(view['proposal']['tool'], 'withdraw_proposal')
        self.assertIs(view['proposal']['effects_executed'], False)
        self.assertIs(view['proposal']['decision'], None)
        self.assertEqual(self.lane._charged(ACTIVE_GRANT_ID), (0, 0))
        again = self.service.agent_withdraw_proposal(_call(now=31, proposal_id='sim-wd'), role='agent')
        self.assertIs(again['duplicate'], True)
        self.assertEqual(again['proposal']['phase'], 'WITHDRAWN')
        # The period window does not refuse withdrawal: an expired `now` still collects a pending memo.
        self.propose(proposal_id='sim-wd-expired', amount=10)
        expired = self.service.agent_withdraw_proposal(
            _call(now=PERIOD_NOT_AFTER + 1, proposal_id='sim-wd-expired'), role='agent')
        self.assertEqual(expired['proposal']['phase'], 'WITHDRAWN')
        unknown = self.raises(lambda: self.service.agent_withdraw_proposal(
            _call(proposal_id='sim-none'), role='agent'))
        self.assertEqual((unknown.code, unknown.status), ('UNKNOWN_PROPOSAL', 404))
        revoked = self.raises(lambda: self.service.agent_withdraw_proposal(
            _call(grant_id=REVOKED_GRANT_ID, generation=REVOKED_GENERATION, proposal_id='sim-wd'),
            role='agent'))
        self.assertEqual((revoked.code, revoked.status), ('GRANT_REVOKED', 403))
        denied = self.raises(lambda: self.service.agent_withdraw_proposal(
            _call(proposal_id='sim-wd'), role='observer'))
        self.assertEqual(denied.detail['permission'], 'agent:withdraw_proposal')
        # A withdrawn proposal can no longer be cited by a human command.
        self.propose(proposal_id='sim-wd-cite', surface='capital:offer', amount=100)
        self.service.agent_withdraw_proposal(_call(proposal_id='sim-wd-cite'), role='agent')
        cited = self.raises(lambda: self.service.execute({
            'instance_id': self.service.instance_id, 'operation_id': 'sim-wd-cite-op',
            'op': 'offer', 'advance_id': 'sim-wd-cite',
            'args': {'fixture_id': 'sim-committed', 'amount': 100},
            'proposal_id': 'sim-wd-cite'}))
        self.assertEqual((cited.code, cited.status), ('PROPOSAL_BINDING_CONFLICT', 409))
        grant = self.service.agent_query(_call(), role='agent')['grant']
        self.assertEqual(grant['authority'], ['PROPOSE', 'QUERY'])
        self.assertEqual(grant['generation'], ACTIVE_GENERATION)
        self.assertEqual(len(self.service.receipts), 0)

    def test_propose_grant_change_stores_a_memo_and_never_mutates_the_grant(self):
        before = self.service.agent_query(_call(), role='agent')['grant']
        view = self.service.agent_propose_grant_change(
            _call(proposal_id='sim-change', requested={'authority': ['QUERY'], 'note': 'sim-note'}),
            role='agent')
        self.assertIs(view['duplicate'], False)
        proposal = view['proposal']
        self.assertEqual(proposal['tool'], 'propose_grant_change')
        self.assertEqual(proposal['phase'], 'HUMAN_PENDING')
        self.assertIs(proposal['effects_executed'], False)
        self.assertIs(proposal['amount'], None)
        self.assertIs(proposal['surface'], None)
        self.assertIs(proposal['two_person_required'], None)
        self.assertEqual(proposal['memo'], {'authority': ['QUERY'], 'note': 'sim-note'})
        self.assertEqual(self.service.agent_query(_call(), role='agent')['grant'], before)
        self.assertEqual(self.lane._charged(ACTIVE_GRANT_ID), (0, 1))
        again = self.service.agent_propose_grant_change(
            _call(proposal_id='sim-change', requested={'authority': ['QUERY'], 'note': 'sim-note'}),
            role='agent')
        self.assertIs(again['duplicate'], True)
        conflict = self.raises(lambda: self.service.agent_propose_grant_change(
            _call(proposal_id='sim-change', requested={'note': 'other'}), role='agent'))
        self.assertEqual((conflict.code, conflict.status), ('PROPOSAL_BINDING_CONFLICT', 409))
        execute = self.raises(lambda: self.service.agent_propose_grant_change(
            _call(proposal_id='sim-change-exec', requested={'authority': ['EXECUTE']}), role='agent'))
        self.assertEqual((execute.code, execute.status), ('EXECUTE_AUTHORITY_DISABLED', 403))
        self.assertNotIn('sim-change-exec', self.lane.proposals)
        bad = self.raises(lambda: self.service.agent_propose_grant_change(
            _call(proposal_id='sim-change-bad', requested={'widen': True}), role='agent'))
        self.assertEqual((bad.code, bad.status), ('INVALID_ARGUMENTS', 400))
        denied = self.raises(lambda: self.service.agent_propose_grant_change(
            _call(proposal_id='sim-change-role', requested={'note': 'x'}), role='auditor'))
        self.assertEqual(denied.detail['permission'], 'agent:propose_grant_change')
        # A grant-change memo has no surface and cannot be cited by a command.
        cited = self.raises(lambda: self.service.execute({
            'instance_id': self.service.instance_id, 'operation_id': 'sim-change-cite-op',
            'op': 'offer', 'advance_id': 'sim-change-cite',
            'args': {'fixture_id': 'sim-committed', 'amount': 100},
            'proposal_id': 'sim-change'}))
        self.assertEqual((cited.code, cited.status), ('PROPOSAL_BINDING_CONFLICT', 409))
        early = self.raises(lambda: self.service.agent_propose_grant_change(
            _call(now=0, proposal_id='sim-change-early', requested={'note': 'x'}), role='agent'))
        self.assertEqual(early.code, 'GRANT_NOT_CURRENT')
        self.assertEqual(len(self.service.receipts), 0)

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
            self.assertEqual((caught.code, caught.status), ('RECOVERY_AGENT_FORBIDDEN' if op == 'default' else 'ROLE_FORBIDDEN', 403))
            if op != 'default':
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
            {'enum': ['HUMAN_PENDING', 'WITHDRAWN']})
        self.assertEqual(
            doc['definitions']['agent_memo_view']['properties']['effects_executed'],
            {'const': False})
        self.assertIs(doc['definitions']['agent_memo_view']['properties']['decision']['const'], None)
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
            self.assertEqual(payload['error'], 'RECOVERY_AGENT_FORBIDDEN' if op == 'default' else 'ROLE_FORBIDDEN')
            if op != 'default':
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
            ('/api/agent/query_subject', 'agent:query_subject'),
            ('/api/agent/propose_action', 'agent:propose_action'),
            ('/api/agent/withdraw_proposal', 'agent:withdraw_proposal'),
            ('/api/agent/propose_grant_change', 'agent:propose_grant_change'),
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

    def test_agent_tools_cover_the_draft_allowlist(self):
        token = self.agent_token()
        service = self.server.service
        subject = _call(surface='capital:draw')
        validate(subject, self.doc['definitions']['agent_subject_request'], self.doc)
        status, view = self.request('POST', '/api/agent/query_subject', subject, token)
        self.assertEqual(status, 200, view)
        validate(view, self.doc['definitions']['agent_subject_response'], self.doc)
        self.assertEqual(view['match'], {'surface': 'capital:draw', 'subject': None, 'in_scope': True})
        self.assertIs(view['subjects'], None)
        status, proposed = self.request(
            'POST', '/api/agent/propose_action',
            _propose(proposal_id='sim-http-wd', surface='capital:offer', amount=100), token)
        self.assertEqual(status, 200, proposed)
        withdraw = _call(proposal_id='sim-http-wd')
        validate(withdraw, self.doc['definitions']['agent_withdraw_request'], self.doc)
        status, view = self.request('POST', '/api/agent/withdraw_proposal', withdraw, token)
        self.assertEqual(status, 200, view)
        validate(view, self.doc['definitions']['agent_withdraw_response'], self.doc)
        self.assertEqual(view['proposal']['phase'], 'WITHDRAWN')
        self.assertIs(view['proposal']['effects_executed'], False)
        status, again = self.request('POST', '/api/agent/withdraw_proposal', withdraw, token)
        self.assertEqual(status, 200, again)
        self.assertIs(again['duplicate'], True)
        self.assertEqual(again['proposal']['phase'], 'WITHDRAWN')
        change = _call(proposal_id='sim-http-change', requested={'note': 'sim-http-note'})
        validate(change, self.doc['definitions']['agent_grant_change_request'], self.doc)
        status, view = self.request('POST', '/api/agent/propose_grant_change', change, token)
        self.assertEqual(status, 200, view)
        validate(view, self.doc['definitions']['agent_grant_change_response'], self.doc)
        self.assertEqual(view['proposal']['phase'], 'HUMAN_PENDING')
        self.assertEqual(view['proposal']['memo'], {'note': 'sim-http-note'})
        self.assertIs(view['proposal']['amount'], None)
        status, grant = self.request('POST', '/api/agent/query_grant', _call(), token)
        self.assertEqual(grant['grant']['authority'], ['PROPOSE', 'QUERY'])
        self.assertEqual(grant['grant']['generation'], ACTIVE_GENERATION)
        status, refused = self.request(
            'POST', '/api/agent/propose_grant_change',
            _call(proposal_id='sim-http-change-exec', requested={'authority': ['EXECUTE']}), token)
        self.assertEqual((status, refused['error']), (403, 'EXECUTE_AUTHORITY_DISABLED'))
        self.assertNotIn('sim-http-change-exec', service.agent_lane.proposals)
        denied = (
            ('/api/agent/query_subject', 'agent:query_subject', subject),
            ('/api/agent/withdraw_proposal', 'agent:withdraw_proposal', withdraw),
            ('/api/agent/propose_grant_change', 'agent:propose_grant_change', change),
        )
        organizer, _state = self.organizer_token()
        tokens = {'organizer': organizer}
        for role in ('auditor', 'observer'):
            status, opened = self.request('POST', '/api/session', {'role': role}, organizer)
            self.assertEqual(status, 200, opened)
            tokens[role] = opened['local_token']
        for role in ('organizer', 'auditor', 'observer'):
            for path, permission, payload in denied:
                status, reply = self.request('POST', path, payload, tokens[role])
                self.assertEqual((status, reply['error'], reply['permission']),
                                 (403, 'ROLE_FORBIDDEN', permission), (role, path))
        for path, _permission, payload in denied:
            status, reply = self.request('POST', path, payload)
            self.assertEqual((status, reply['error']), (403, 'LOCAL_TOKEN_REQUIRED'), path)
        digest_before = service.machine.state_digest()
        proposals_before = len(service.agent_lane.proposals)
        status, executed = self.request('POST', '/api/agent/execute', {'kind': 'EXECUTE'}, token)
        self.assertEqual((status, executed['error']), (403, 'EXECUTE_AUTHORITY_DISABLED'))
        self.assertEqual(service.machine.state_digest(), digest_before)
        self.assertEqual(len(service.agent_lane.proposals), proposals_before)


if __name__ == '__main__':
    unittest.main()
