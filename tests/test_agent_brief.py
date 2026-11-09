"""Disclosure tests use synthetic local evidence, never provider data."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from capital import agent_brief as brief
from capital.auth import ALL_PERMISSIONS, Decision
from capital.service import CapitalService
from tests.facade_schema import SchemaError, load_contract, validate

SUBJECT = {'case_id': 'sim-case', 'beneficiary_id': 'fixture-organizer'}
DENIED = {'status': 'UNAVAILABLE', 'code': 'CASE_BRIEF_UNAVAILABLE'}


def seed(service, advance='sim-case', fixture='sim-committed', draw=True):
    for op, args in [('offer', {'fixture_id': fixture, 'amount': 40000}),
                     ('approve', {}), ('bind_settlement', {})] + ([('draw', {})] if draw else []):
        result = service.execute({'instance_id': service.instance_id, 'operation_id': advance + '-' + op.replace('_', '-'),
                                  'advance_id': advance, 'op': op, 'args': args})
        if result['outcome'] != 'ACCEPTED':
            raise AssertionError(result)


def issue(service, subject=None, claim='sim-committed', advance='sim-case'):
    subject = dict(SUBJECT if subject is None else subject)
    grant = service.issue_agent_case_grant(subject, claim, advance)
    return {'grant_id': grant['grant_id'], 'subject': subject}


def state(service):
    return copy.deepcopy({'journal': service.producer.export_journal(), 'receipts': service.receipts,
                          'case_fixtures': service.case_fixtures, 'overlay': service.overlay_entries,
                          'proposals': service.agent_lane.proposals,
                          'grants': vars(service.agent_case_grants),
                          'canonical': service.producer.canonical_state()})


class BriefTests(unittest.TestCase):
    def setUp(self):
        self.service = CapitalService()
        seed(self.service)
        self.body = issue(self.service)

    def query(self, body=None):
        return self.service.agent_query_case(self.body if body is None else body, role='agent')

    def test_closed_success_sources_digest_and_non_mutation(self):
        before = state(self.service)
        result = self.query()
        self.assertEqual(result['facts'], {'beneficiary_claim_outstanding_krw': 95000,
                                         'beneficiary_refund_exposure_krw': 0,
                                         'advance_principal_outstanding_krw': 40000})
        digest = result['provenance'].pop('brief_sha256')
        self.assertEqual(digest, hashlib.sha256(brief.canonical(result)).hexdigest())
        result['provenance']['brief_sha256'] = digest
        leaves = []
        def collect(value, prefix=''):
            for key, item in value.items():
                path = prefix + key
                if type(item) is dict:
                    collect(item, path + '.')
                else:
                    leaves.append(path)
        collect(result)
        self.assertEqual(set(leaves), set(self.service.agent_brief_policy.values['case_brief_field_allowlist']['leaf_fields']))
        self.assertEqual(len(leaves), 14)
        self.assertEqual(brief.canonical(self.query()), brief.canonical(result))
        # Compare policy values separately: policies have object identity, not equality.
        after = state(self.service)
        before['grants'].pop('policy'); after['grants'].pop('policy')
        self.assertEqual(before, after)

    def test_unrelated_case_and_excluded_fields_leave_entire_brief_unchanged(self):
        initial = brief.canonical(self.query())
        seed(self.service, 'sim-sibling', 'sim-pending', draw=False)
        self.service.receipts['excluded-read-fixture'] = {'SIMULATED': 'excluded'}
        self.service.fixtures.rows['sim-refund']['claim']['gross'] = 999
        self.service.fixtures.rows['sim-committed']['claim']['trade_id'] = 'excluded-fixture'
        self.assertEqual(initial, brief.canonical(self.query()))
        self.service.fixtures.rows['sim-committed']['claim']['obligations'][0]['outstanding'] = 90000
        self.assertNotEqual(initial, brief.canonical(self.query()))

    def test_all_currentness_failures_precede_case_access(self):
        registry = self.service.agent_case_grants
        row = registry.grants[self.body['grant_id']]
        mutations = [('run_id', 'old-run'), ('agent_id', 'other-agent'), ('permission', 'QUERY'),
                     ('generation', 0), ('generation', True), ('revoked', True),
                     ('expires_before_period', 0), ('not_before_period', 1),
                     ('advance_id', '*'), ('claim_id', None)]
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                original = row[key]; row[key] = value
                with patch.object(self.service.producer, 'view', side_effect=AssertionError('protected access')) as reader:
                    self.assertEqual(self.query(), DENIED); reader.assert_not_called()
                row[key] = original
        for body in [None, [], {}, {**self.body, 'generation': 1},
                     {**self.body, 'subject': {**SUBJECT, 'case_id': 'sim-sibling'}},
                     {**self.body, 'subject': {**SUBJECT, 'beneficiary_id': 'other-organizer'}},
                     {**self.body, 'grant_id': 'sim-grant-agent'}]:
            with patch.object(self.service.producer, 'view') as reader:
                self.assertEqual(self.service.agent_query_case(body, role='agent'), DENIED)
                reader.assert_not_called()
        for key in ('include_receipts', 'portfolio_total', 'raw_journal', 'credentials'):
            self.assertEqual(self.query({**self.body, key: True}), DENIED)
        with patch.object(self.service.agent_lane, 'case_query_eligible', return_value=False), patch.object(self.service.producer, 'view') as reader:
            self.assertEqual(self.query(), DENIED); reader.assert_not_called()
        for field, value in [('logical_period', 1), ('logical_period', -1), ('period_high_water', 1)]:
            old = getattr(registry, field); setattr(registry, field, value)
            with patch.object(self.service.producer, 'view') as reader:
                self.assertEqual(self.query(), DENIED); reader.assert_not_called()
            setattr(registry, field, old)

    def test_generation_replacement_revocation_period_restart_and_overflow(self):
        old = copy.deepcopy(self.body)
        self.body = issue(self.service)
        self.assertEqual(self.query(old), DENIED)
        self.assertIn('facts', self.query())
        self.service.revoke_agent_case_grant(self.body['grant_id'])
        self.assertEqual(self.query(), DENIED)
        self.body = issue(self.service)
        self.service.set_agent_logical_period(1)
        self.assertEqual(self.query(), DENIED)
        with self.assertRaises(brief.Unavailable): self.service.set_agent_logical_period(0)
        self.assertEqual(CapitalService().agent_query_case(self.body, role='agent'), DENIED)
        registry = self.service.agent_case_grants
        registry.generations[('sim-agent', *SUBJECT.values())] = brief.INPUT_CEILING
        with self.assertRaises(brief.Unavailable): issue(self.service)
        self.assertEqual(self.query(), DENIED)
        registry.logical_period = registry.period_high_water = brief.INPUT_CEILING
        with self.assertRaises(brief.Unavailable): issue(self.service)

    def test_corrupt_generation_counters_cannot_restore_old_grants(self):
        registry = self.service.agent_case_grants
        old = copy.deepcopy(self.body)
        self.body = issue(self.service)
        slot = ('sim-agent', SUBJECT['case_id'], SUBJECT['beneficiary_id'])
        registry.generations[slot] = 1
        with patch.object(self.service.producer, 'view') as reader:
            self.assertEqual(self.query(old), DENIED)
            reader.assert_not_called()
        with self.assertRaises(brief.Unavailable): issue(self.service)
        del registry.generations[slot]
        with self.assertRaises(brief.Unavailable): issue(self.service)

    def test_handles_are_opaque_collision_checked_and_records_detached(self):
        registry = self.service.agent_case_grants
        row = registry.grants[self.body['grant_id']]
        self.assertEqual(set(row), brief._GRANT_KEYS)
        self.assertNotIn(row['permission'], ALL_PERMISSIONS)
        with patch('capital.agent_brief.secrets.token_hex', return_value=self.body['grant_id']):
            before = copy.deepcopy(registry.generations)
            with self.assertRaises(brief.Unavailable): issue(self.service)
            self.assertEqual(registry.generations, before)
        record = self.service.issue_agent_case_grant(SUBJECT, 'sim-committed', 'sim-case')
        record['revoked'] = True
        self.assertIs(registry.grants[record['grant_id']]['revoked'], False)

    def test_dual_gate_absent_cases_binding_and_adapter_fail_closed(self):
        for role in ('organizer', 'auditor', 'observer', '', None):
            self.assertEqual(self.service.agent_query_case(self.body, role=role), DENIED)
        with patch.object(self.service.authorizer, 'authorize', return_value=Decision(False, 'fixture')):
            self.assertEqual(self.query(), DENIED)
        absent = issue(self.service, {'case_id': 'sim-absent', 'beneficiary_id': 'fixture-organizer'}, advance='sim-absent')
        self.assertEqual(self.query(absent), DENIED)
        self.service.case_fixtures['sim-case'] = 'sim-refund'
        self.assertEqual(self.query(), DENIED)
        self.service.case_fixtures['sim-case'] = 'sim-committed'
        with patch.object(self.service.fixtures, 'beneficiary', return_value='same-label-other-owner'):
            self.assertEqual(self.query(), DENIED)
        with patch.object(self.service.producer, 'view', side_effect=RuntimeError('private reason')):
            self.assertEqual(self.query(), DENIED)
        class Unsafe:
            def __getattr__(self, _): raise AssertionError('unsafe adapter called')
        self.service.producer = Unsafe()
        self.assertEqual(self.query(), DENIED)

    def test_refund_recipient_is_not_bearer_and_unissued_principal_is_zero(self):
        seed(self.service, 'sim-undrawn', 'sim-pending', draw=False)
        body = issue(self.service, {**SUBJECT, 'case_id': 'sim-undrawn'}, 'sim-pending', 'sim-undrawn')
        self.assertEqual(self.query(body)['facts']['advance_principal_outstanding_krw'], 0)
        # The pinned FSM refuses offers against open refunds. Exercise the unchanged
        # built-in buyer-refund evidence directly with a synthetic isolated binding.
        grant = copy.deepcopy(self.service.agent_case_grants.grants[self.body['grant_id']])
        grant['claim_id'] = 'sim-refund'
        advance = self.service.producer.view('sim-case')
        advance.update(claim_id='sim-refund', settlement_id='sim-refund')
        result = brief.project(self.service.agent_brief_policy, grant, advance,
                               self.service.fixtures.view('sim-refund'), 'fixture-organizer',
                               {'fixture-organizer': ['organizer']})
        self.assertIsNone(result['facts']['beneficiary_refund_exposure_krw'])
        self.assertEqual(result['facts']['beneficiary_claim_outstanding_krw'], 95000)

    def test_projector_worked_synthetic_example_unknown_and_ambiguous_facts(self):
        grant = self.service.agent_case_grants.grants[self.body['grant_id']]
        advance = self.service.producer.view('sim-case')
        settlement = self.service.fixtures.view('sim-committed')
        claim = settlement['claim']
        # Dedicated synthetic attribution example; never relabel the built-in buyer refund.
        claim['obligations'] = [{'payee': 'organizer', 'outstanding': 100000}]
        claim.update(refund_outstanding=5000, refund_bearer='fixture-organizer')
        def project(mapping=None):
            return brief.project(self.service.agent_brief_policy, grant, advance, settlement,
                                 'fixture-organizer', {'fixture-organizer':['organizer']} if mapping is None else mapping)['facts']
        self.assertEqual(list(project().values()), [100000, 5000, 40000])
        claim['obligations'].append({'payee': 'organizer', 'outstanding': 10})
        self.assertIsNone(project()['beneficiary_claim_outstanding_krw'])
        self.assertIsNone(project({})['beneficiary_claim_outstanding_krw'])
        claim['refund_bearer'] = 'other-organizer'
        self.assertIsNone(project()['beneficiary_refund_exposure_krw'])
        advance['settlement_id'] = 'other-claim'
        with self.assertRaises(brief.Unavailable): project()

    def test_policy_is_loaded_and_every_unsupported_entry_fails_closed(self):
        raw = brief.note_path(brief.NOTE).read_bytes()
        block = brief.read_note(brief.note_path(brief.NOTE))['block']
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'note.md'
            for name in brief._USABLE:
                changed = copy.deepcopy(block); changed['entries'][name]['status'] = 'DEFERRED'
                path.write_text('```capital-decision-v1\n' + json.dumps(changed) + '\n```')
                self.assertFalse(brief.DisclosurePolicy(path).ready, name)
                changed['entries'][name]['status'] = 'ADOPTED'; changed['entries'][name]['value'] = {}
                path.write_text('```capital-decision-v1\n' + json.dumps(changed) + '\n```')
                self.assertFalse(brief.DisclosurePolicy(path).ready, name)
            path.write_bytes(raw); self.assertTrue(brief.DisclosurePolicy(path).ready)
            path.unlink(); policy = brief.DisclosurePolicy(path)
            self.assertFalse(policy.ready); self.assertEqual(policy.denial(), DENIED)
        self.service.agent_brief_policy.values = {}
        with patch.object(self.service.producer, 'view') as reader:
            self.assertEqual(self.query(), DENIED); reader.assert_not_called()

    def test_closed_facade_amount_constraints_and_requests(self):
        contract = load_contract(); defs = contract['definitions']
        result = self.query()
        validate(result, defs['agent_case_response'], contract)
        validate(DENIED, defs['agent_case_response'], contract)
        validate(self.body, defs['agent_case_request'], contract)
        for value in (-1, 1.5, True, 10**12 + 1):
            bad = copy.deepcopy(result); bad['facts']['advance_principal_outstanding_krw'] = value
            with self.assertRaises(SchemaError): validate(bad, defs['agent_case_response'], contract)
        for section in ('subject', 'facts', 'provenance', 'authority'):
            bad = copy.deepcopy(result); bad[section]['extra'] = None
            with self.assertRaises(SchemaError): validate(bad, defs['agent_case_response'], contract)
        for body in ({**self.body, 'extra': True}, {**self.body, 'subject': {**SUBJECT, 'claim_id': 'no'}},
                     {**self.body, 'grant_id': 'A' * 32}):
            with self.assertRaises(SchemaError): validate(body, defs['agent_case_request'], contract)
