import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from capital.service import CapitalService, ApiError, VENDOR
from capital.protocol import SettlementMachine
from capital.readiness import source_integrity
from capital.scenarios import public_invariants


class ReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.service = CapitalService()
        self.n = 0

    def command(self, op, case='sim-a', **args):
        self.n += 1
        return self.service.execute({'instance_id': self.service.instance_id,
            'operation_id': str(self.n), 'op': op, 'advance_id': case, 'args': args})

    def approved(self, case='sim-a', fixture='sim-committed', bind=True):
        self.command('offer', case, fixture_id=fixture, amount=60_000)
        self.command('approve', case)
        if bind:self.command('bind_settlement', case)

    def test_all_scenario_steps_match_contract_and_preserve_workspace(self):
        self.approved();before=self.service.machine.canonical_state()
        receipts=copy.deepcopy(self.service.receipts)
        rows=self.service.scenarios()['scenarios']
        self.assertEqual(len(rows),9)
        self.assertEqual(sum(row['steps'] for row in rows),35)
        for row in rows:
            s=self.service.scenarios(row['id'])['scenario']
            self.assertTrue(s['all_predicates_matched'],row['id'])
            self.assertFalse(s['workspace_mutated']);self.assertFalse(s['policy_adopted'])
            for step in s['steps']:
                self.assertTrue(all(check['matched'] for check in step['checks']))
        self.assertEqual(before,self.service.machine.canonical_state())
        self.assertEqual(receipts,self.service.receipts)

    def final(self,name):return self.service.scenarios(name)['scenario']['final']

    def test_order_comparison_exposes_different_shortfall_without_changing_faces(self):
        a,b=self.final('shortfall-platform'),self.final('shortfall-organizer')
        owed=lambda row: {line['payee']:line['outstanding'] for line in row['obligations']}
        self.assertEqual(owed(a),{'organizer':3000,'platform':0})
        self.assertEqual(owed(b),{'organizer':0,'platform':3000})
        self.assertEqual(a['distributed_cash'],97000);self.assertEqual(b['distributed_cash'],97000)
        self.assertEqual(a['confirmed_cash'],b['confirmed_cash'])

    def test_full_and_split_refunds_keep_distinct_history_and_nonclaims(self):
        full,split=self.final('full-after'),self.final('split-refund')
        self.assertEqual(full['recovery_due'],97000)
        self.assertEqual(full['refund_outstanding'],0)
        self.assertEqual(full['pg_adjustment_outstanding'],100000)
        self.assertEqual(full['confirmed_cash'],97000)
        self.assertFalse(full['external_return_closed']);self.assertFalse(full['bank_debit_observed'])
        self.assertEqual(split['refund_face'],100000)
        self.assertFalse(split['fixture_reclassified'])
        self.assertEqual(split['refund_bearer_policy'],'UNDEFINED')
        self.assertEqual(split['recovery_due'],0)

    def test_late_cash_and_duplicate_facts_never_double_allocate(self):
        late=self.final('late-cash')
        self.assertEqual((late['distributed_cash'],late['undistributed_cash']),(0,100000))
        duplicate=self.service.scenarios('duplicate-statement')['scenario']
        self.assertTrue(duplicate['steps'][1]['duplicate'])
        self.assertEqual(duplicate['final']['confirmed_cash'],97000)
        self.assertEqual(self.final('split-statement')['distributed_cash'],97000)

    def test_partial_after_does_not_automatically_claw_back(self):
        after=self.final('partial-after');before=self.final('partial-before')
        self.assertEqual(after['distributed_cash'],97000);self.assertEqual(before['distributed_cash'],0)
        self.assertEqual(after['recovery_due'],0)
        self.assertTrue(after['distribution_blocked']);self.assertTrue(before['distribution_blocked'])

    def test_refund_fixture_is_pinned_partial_bind_refund_and_offer_refused(self):
        row=self.service.fixtures.view('sim-refund');claim=row['claim']
        committed=self.service.fixtures.view('sim-committed')
        self.assertEqual((claim['refund_face'],claim['refund_accepted'],claim['refund_outstanding']),(10000,0,10000))
        self.assertEqual(claim['refund_bearer_policy'],'UNDEFINED')
        self.assertIs(claim['fixture_reclassified'],False)
        # Bearer UNDEFINED must come from the pinned view, which also blocks distribution.
        self.assertIs(claim['distribution_blocked'],True)
        self.assertRegex(claim['refund_beneficiary'] or '',r'^fixture-[a-z-]+$')
        self.assertEqual((claim['recovery_due'],claim['pg_adjustment_outstanding']),(0,0))
        self.assertEqual((claim['confirmed_cash'],claim['distributed_cash'],claim['undistributed_cash']),(97000,0,97000))
        self.assertTrue(all(line['cancelled_unpaid']==0 and line['recovery_due']==0 for line in claim['obligations']))
        self.assertTrue(all(c['matched'] for c in public_invariants(claim)))
        # Provenance: one accepted settlement command beyond commit, equal to an independent pinned replay.
        self.assertEqual(row['accepted_entries'],committed['accepted_entries']+1)
        reference=SettlementMachine()
        reference.initiate('sim-refund',idempotency_key='init',trade_id=row['trade_id'],gross=row['gross'],
                           debtor_role=row['debtor_role'],policy=row['policy'])
        reference.authorize('sim-refund',idempotency_key='authorize');reference.capture('sim-refund',idempotency_key='capture')
        reference.commit('sim-refund',idempotency_key='commit',movement_id=row['commit_movement_id'],gross=row['gross'],
                         amount=claim['confirmed_cash'],fee=claim['non_cash_accounted'],tax=0,held=0,adjustment=0)
        reference.bind_refund('sim-refund',idempotency_key='refund',refund_id='sim-reference-refund',amount=10_000,
                              beneficiary_role=claim['refund_beneficiary'],reason='SYNTHETIC_REFERENCE')
        self.assertEqual(claim,reference.view('sim-refund')['claim'])
        clean=committed['claim']
        self.assertEqual((clean['refund_face'],clean['refund_bearer_policy'],clean['refund_beneficiary'],clean['distribution_blocked']),(0,'NONE',None,False))
        before=self.service.machine.canonical_state()
        receipt=self.command('offer','sim-refund-case',fixture_id='sim-refund',amount=100)
        self.assertEqual((receipt['outcome'],receipt['error']),('REJECTED','REFUND_OBLIGATION_OPEN'))
        self.assertNotIn('sim-refund-case',self.service.case_fixtures)
        self.assertEqual(before,self.service.machine.canonical_state())

    def test_predicate_checker_detects_corrupt_values(self):
        view=self.final('late-cash');view['confirmed_cash']+=1
        checks={row['predicate']:row['matched'] for row in public_invariants(view)}
        self.assertFalse(checks['CASH_ALLOCATION_CONSERVATION'])
        view['funds_executed']=True
        self.assertFalse(next(c['matched'] for c in public_invariants(view) if c['predicate']=='NO_REAL_EFFECT'))

    def test_preview_accept_and_reject_never_create_receipt_or_release_reservation(self):
        self.approved();self.approved('sim-b')
        original=self.service.machine.canonical_state();receipts=copy.deepcopy(self.service.receipts)
        result=self.service.preview_draw('sim-a',self.service.instance_id)
        self.assertEqual(result['outcome'],'WOULD_ACCEPT')
        self.assertEqual(result['settlement_gate'],'MOCK_COMMIT_OBSERVED')
        self.assertFalse(result['write_authorized'])
        self.assertEqual(original,self.service.machine.canonical_state());self.assertEqual(receipts,self.service.receipts)
        self.command('draw','sim-a')
        result=self.service.preview_draw('sim-b',self.service.instance_id)
        self.assertEqual(result['reason'],'ADVANCE_EXCEEDS_OPEN_FACE')
        self.assertEqual(self.service.machine.view('sim-b')['phase'],'APPROVED')

    def test_preview_pending_unbound_terminal_and_old_session(self):
        self.approved(fixture='sim-pending')
        self.assertEqual(self.service.preview_draw('sim-a',self.service.instance_id)['reason'],'SETTLEMENT_NOT_COMMITTED')
        self.approved('sim-u',fixture='sim-pending',bind=False)
        self.assertEqual(self.service.preview_draw('sim-u',self.service.instance_id)['settlement_gate'],'UNBOUND')
        self.command('cancel','sim-u')
        self.assertEqual(self.service.preview_draw('sim-u',self.service.instance_id)['outcome'],'NOT_APPLICABLE')
        with self.assertRaisesRegex(ApiError,'SESSION_CHANGED'):self.service.preview_draw('sim-a','old')
        with self.assertRaisesRegex(ApiError,'UNKNOWN_ADVANCE'):self.service.preview_draw('sim-missing',self.service.instance_id)

    def test_readiness_preserves_all_requirements_and_does_not_claim_node_completion(self):
        ready=self.service.readiness()
        self.assertEqual({x for g in ready['groups'] for x in g['requirements']},{f'CAP-{i:02}' for i in range(1,21)})
        self.assertEqual(ready['upstream_binding'],'NOT_BOUND')
        self.assertEqual(ready['upstream_nodes_completed'],[])
        self.assertFalse(ready['production_authorized']);self.assertFalse(ready['policy_adopted'])
        self.assertTrue(ready['source_integrity']['all_matched'])
        for row in ready['groups']:
            if row['status']!='AVAILABLE_LOCAL':self.assertTrue(row['blockers'])

    def test_source_integrity_detects_missing_or_modified_file(self):
        with tempfile.TemporaryDirectory() as directory:
            dest=Path(directory)/'vendor';shutil.copytree(VENDOR,dest)
            manifest=json.loads((dest/'manifest.json').read_text())
            name=next(iter(manifest['files']));file=dest/name
            file.write_text(file.read_text()+'\n# mutation\n')
            self.assertFalse(source_integrity(dest,manifest)['all_matched'])
            file.unlink();self.assertFalse(source_integrity(dest,manifest)['all_matched'])

    def test_read_results_are_copies_and_unknown_scenario_rejected(self):
        result=self.service.scenarios('full-after');result['scenario']['steps'].clear()
        self.assertEqual(len(self.service.scenarios('full-after')['scenario']['steps']),7)
        ready=self.service.readiness();ready['groups'].clear();self.assertEqual(len(self.service.readiness()['groups']),6)
        with self.assertRaisesRegex(ApiError,'UNKNOWN_SCENARIO'):self.service.scenarios('../../server.py')

if __name__=='__main__':unittest.main()
