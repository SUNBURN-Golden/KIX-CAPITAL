"""SIMULATED demo-book slice admission, shared sources and sealed replay attacks."""
import copy
import importlib.util
import json
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from capital import overlay, slices
from capital.export import content_digest, sha256_hex
from capital.producer import PinnedFsmProducer
from capital.service import ApiError, CapitalService
from capital.shadow import FALSE_FLAGS
from capital.store import FileWorkspace, InMemoryStorage, WorkspaceError, section_checksum
from capital.verify import verify_manifest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('seed_overlay_slices', ROOT / 'scripts/seed_overlay_slices.py')
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


def run(s, op, key, advance='sim-slice', **args):
    return s.execute({'instance_id': s.instance_id, 'operation_id': key, 'op': op, 'advance_id': advance, 'args': args})


def advance(s, amount, claim='demo-delta-small', name='sim-slice', draw=True):
    steps = [('offer', {'fixture_id': claim, 'amount': amount}), ('approve', {}), ('bind_settlement', {})]
    if draw: steps.append(('draw', {}))
    for op, args in steps:
        result = run(s, op, name + '-' + op.replace('_', '-'), name, **args)
        assert result['outcome'] == 'ACCEPTED', result


def recourse(s, sid, amount, key='recourse', source='demo-delta-mid'):
    row = next(r for r in s.overlay_slices()['slices'] if r['slice_id'] == sid)
    q = next(q for q in row['quotes'] if q['source_ref']['claim_id'] == source)
    return seed.post(s, 'post_slice_recourse', key, slice_id=sid, source_ref=q['source_ref'], quote_ref=q['quote_ref'], amount_krw=amount)


class SliceTests(unittest.TestCase):
    def setUp(self):
        self.source, self.s = seed.book()
        self.threshold = self.s.slice_policy['threshold']
        self.face = self.threshold // 5

    def refuse(self, code, call):
        frozen = self.s._frozen()
        with self.assertRaises(ApiError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.s._frozen(), frozen)
        return caught.exception

    def opened(self, face=None, claim='demo-delta-small', key='slice-a'):
        seed.register(self.s, key, self.face if face is None else face, claim)
        return seed.open_slice(self.s, key)

    def impaired(self):
        self.opened()
        claim = self.source.view('demo-delta-small')['claim']
        seed.refund(self.source, 'demo-delta-small', claim['gross'])
        return seed.post(self.s, 'impair_slice', 'impair', slice_id='slice-a', reason='REFUND_REDUCED_LINE')

    def test_sizing_registry_quote_duplicates_and_idempotency(self):
        q = self.s.overlay_slices('demo-delta-small', 'organizer', 60)['quote']
        line = self.source.view('demo-delta-small')['claim']['obligations'][0]
        rate = self.s.slice_policy['sizing_rates']['T1_COMMIT_OBSERVED']
        self.assertEqual(q['shadow_slice_face_max'], line['outstanding'] * rate // 10000)
        first = seed.register(self.s, 'slice-a', self.face)
        duplicate = self.s.overlay_command({'instance_id': self.s.instance_id, 'operation_id': 'slice-a', **first['entry']['command']})
        self.assertTrue(duplicate['transport_duplicate'])
        self.assertEqual(first['entry'], duplicate['entry'])
        self.refuse('IDEMPOTENCY_CONFLICT', lambda: self.s.overlay_command({'instance_id': self.s.instance_id, 'operation_id': 'slice-a', **first['entry']['command'], 'slice_face_krw': self.face + 1}))
        self.refuse('SLICE_OPEN_EXISTS', lambda: seed.register(self.s, 'slice-b', self.face))
        q = self.s.overlay_slices('demo-delta-small', 'organizer', 60)['quote']['registry_check']
        self.assertEqual(q['status'], 'REFUSED')
        self.assertIn('SLICE_OPEN_EXISTS', q['codes'])
        self.assertEqual(first['entry']['slice_id'], 'slice-a')
        self.assertEqual(self.s.machine.export_journal(), [])

    def test_quote_is_bound_to_registry_and_face(self):
        q = self.s.overlay_slices('demo-delta-small', 'organizer', 60)['quote']
        body = dict(instance_id=self.s.instance_id, operation_id='bad-q', op='register_slice', at_sim_day=0,
                    claim_id='demo-delta-small', payee_label='organizer', slice_face_krw=self.face,
                    holder_role='KIX_CAPITAL_LENDER', expected_days=60, quote_ref='0'*64)
        self.refuse('SLICE_QUOTE_MISMATCH', lambda: self.s.overlay_command(body))
        body.update(quote_ref=q['result_digest'], slice_face_krw=q['shadow_slice_face_max']+1)
        self.refuse('SLICE_QUOTE_MISMATCH', lambda: self.s.overlay_command(body))
        seed.register(self.s, 'other', self.face, 'demo-alpha-arena')
        body.update(slice_face_krw=self.face)
        self.refuse('SLICE_QUOTE_MISMATCH', lambda: self.s.overlay_command(body))

    def test_payee_holder_fields_authority_and_clock(self):
        self.refuse('SLICE_PAYEE_NOT_SLICEABLE', lambda: seed.register(self.s, 'venue', self.face, payee='venue'))
        q = self.s.overlay_slices('demo-delta-small', 'organizer', 60)['quote']
        body = dict(instance_id=self.s.instance_id, operation_id='bad', op='register_slice', at_sim_day=0,
                    claim_id='demo-delta-small', payee_label='organizer', slice_face_krw=self.face,
                    holder_role='sim-third-party', expected_days=60, quote_ref=q['result_digest'])
        self.refuse('SLICE_HOLDER_NOT_ADOPTED', lambda: self.s.overlay_command(body))
        for field in ('token', 'holder_ref', 'transfer_to'):
            self.refuse('SLICE_FIELD_NOT_ADOPTED', lambda: self.s.overlay_command({**body, field: 'sim-extra'}))
        self.refuse('INVALID_COMMAND', lambda: self.s.overlay_command({**body, 'unknown': True}))
        for invalid_op in ([], {}, True, None):
            self.refuse('INVALID_COMMAND', lambda: self.s.overlay_command({'op': invalid_op}))
        for op in slices.COMMANDS:
            self.refuse('SLICE_AGENT_FORBIDDEN', lambda: self.s.overlay_command({'op': op}, role='agent'))
        self.refuse('SIM_CLOCK_STALE', lambda: self.s.overlay_command({**body, 'at_sim_day': 1}))
        self.refuse('INVALID_COMMAND', lambda: self.s.overlay_command({**body, 'slice_face_krw': True}))

    def test_u1_u2_reuse_and_not_bound(self):
        # A captured bound claim has the same U1 refusal as underwriting (no T1).
        q = self.s.overlay_slices('demo-delta-mid', 'organizer', 60)['quote']
        self.assertEqual(q['status'], 'SHADOW_INPUT_UNKNOWN')
        self.refuse('SLICE_U1_REFUSED', lambda: seed.register(self.s, 'captured', self.face, 'demo-delta-mid'))
        self.refuse('SLICE_U2_REFUSED', lambda: seed.register(self.s, 'refund', self.face, 'demo-epsilon-refund'))
        self.assertIsNone(slices.load_policy(self.s.terms, ROOT / 'does-not-exist'))
        quoted = self.s.overlay_slices('demo-delta-small', 'organizer', 60)['quote']
        self.s.slice_policy = None
        self.assertEqual(self.s.overlay_slices()['status'], 'NOT_BOUND')
        self.refuse('NOT_BOUND', lambda: seed.post(self.s, 'register_slice', 'unbound', claim_id='demo-delta-small', payee_label='organizer', slice_face_krw=self.face, holder_role='KIX_CAPITAL_LENDER', expected_days=60, quote_ref=quoted['result_digest']))

    def test_g1_and_g2_are_independent_and_success_changes_u3_u4(self):
        amount = self.threshold // 2
        advance(self.s, amount)
        eligible = self.source.view('demo-delta-small')['claim']['obligations'][0]['outstanding']
        free = eligible - amount
        seed.register(self.s, 'slice-a', free+1)
        self.refuse('BASE_ALREADY_ENCUMBERED', lambda: seed.open_slice(self.s, 'slice-a'))
        seed.post(self.s, 'void_slice', 'void-a', slice_id='slice-a', reason='OPERATOR_WITHDRAWN')
        seed.register(self.s, 'slice-b', free)
        self.refuse('SLICE_WOULD_BREACH_ADVANCE_BASE', lambda: seed.open_slice(self.s, 'slice-b'))
        seed.post(self.s, 'void_slice', 'void-b', slice_id='slice-b', reason='OPERATOR_WITHDRAWN')
        rate = self.s.slice_policy['rates']['T1_COMMIT_OBSERVED']
        allowed = eligible - slices.ceil_div(amount * 10000, rate)
        before = self.s.underwrite('sim-slice', self.s.instance_id, 'organizer')
        self.opened(allowed, key='slice-c')
        after = self.s.underwrite('sim-slice', self.s.instance_id, 'organizer')
        self.assertEqual(after['borrowing_base']['eligible_face'], before['borrowing_base']['eligible_face'] - allowed)
        self.assertEqual(after['caps_remaining']['beneficiary_aggregate_krw'], before['caps_remaining']['beneficiary_aggregate_krw']-allowed)
        self.assertEqual(after['caps_remaining']['portfolio_krw'], before['caps_remaining']['portfolio_krw']-allowed)
        self.assertTrue(verify_manifest(self.s.export_manifest())['ok'])

    def test_cas_and_idempotent_open_after_same_day_draw(self):
        advance(self.s, self.face, draw=False)
        seed.register(self.s, 'slice-a', self.face)
        index = len(self.s.machine.export_journal())
        run(self.s, 'draw', 'later-draw')
        self.refuse('REGISTRY_STALE_CAS', lambda: seed.post(self.s, 'open_slice', 'stale', slice_id='slice-a', expected_after_journal_index=index))
        r = seed.open_slice(self.s, 'slice-a')
        advance(self.s, self.face, 'demo-alpha-arena', 'sim-other')
        result = self.s.overlay_command({'instance_id': self.s.instance_id, 'operation_id': r['operation_id'], **r['entry']['command']})
        self.assertTrue(result['transport_duplicate'])
        self.assertEqual(r['entry'], result['entry'])

    def test_draw_rechecks_slice_base_without_writing_a_receipt(self):
        self.opened()
        claim = self.source.view('demo-delta-small')['claim']
        rate = self.s.slice_policy['rates']['T1_COMMIT_OBSERVED']
        base = (claim['obligations'][0]['outstanding'] - self.face)*rate//10000
        advance(self.s, base+1, draw=False)
        self.refuse('SLICE_DRAW_REFUSED', lambda: run(self.s, 'draw', 'refused-draw'))
        self.assertNotIn('refused-draw', self.s.receipts)
        self.assertEqual(self.s.machine.view('sim-slice')['phase'], 'APPROVED')

    def test_portfolio_recheck_across_beneficiaries(self):
        # Explicit boundary-test policy: use the adopted single cap as the
        # portfolio cap, so the demo book can reach it without invented clients.
        cap = self.s.slice_policy['caps']['single_advance_cap_krw']
        self.s.terms.items['underwriting_depth']['value']['portfolio_cap_krw'] = cap
        self.s.slice_policy = slices.load_policy(self.s.terms)
        self.opened()
        advance(self.s, cap-self.face+1, 'demo-alpha-arena', 'sim-other', draw=False)
        exc = self.refuse('SLICE_DRAW_REFUSED', lambda: run(self.s, 'draw', 'cross-draw', 'sim-other'))
        self.assertEqual(exc.detail['failed_check'], 'U4_CONCENTRATION')
        self.assertEqual(exc.detail['reason']['cap'], 'portfolio_cap_krw')

    def test_cap_refusal_and_cumulative_authority(self):
        cap = self.s.slice_policy['caps']['single_advance_cap_krw']
        seed.register(self.s, 'huge', cap+1, 'demo-alpha-arena')
        self.assertEqual(self.refuse('SLICE_CAP_EXCEEDED', lambda: seed.open_slice(self.s, 'huge')).detail['cap_ref'], 'single_advance_cap_krw')
        seed.post(self.s, 'void_slice', 'void-huge', slice_id='huge', reason='OPERATOR_WITHDRAWN')
        claim='demo-beta-festival'
        face=self.threshold//2+1
        seed.register(self.s, 'first', face, claim, approvals=[])
        seed.post(self.s, 'void_slice', 'void-first', slice_id='first', reason='OPERATOR_WITHDRAWN')
        self.refuse('TWO_PERSON_REQUIRED', lambda: seed.register(self.s, 'second', face, claim, approvals=[]))
        self.s.overlay_command(dict(instance_id=self.s.instance_id, operation_id='next-day', op='advance_day', from_sim_day=0, to_sim_day=1, reason='SIMULATED'))
        seed.register(self.s, 'next', face, claim, approvals=[])

    def test_refund_impairment_shortfall_and_false_flags(self):
        self.opened()
        self.refuse('SLICE_NOT_IMPAIRABLE', lambda: seed.post(self.s, 'impair_slice', 'no', slice_id='slice-a', reason='REFUND_REDUCED_LINE'))
        self.refuse('SLICE_NOT_RESOLVABLE', lambda: seed.post(self.s, 'resolve_slice', 'no-resolve', slice_id='slice-a', resolution='SERVED_IN_FULL'))
        seed.refund(self.source, 'demo-delta-small', self.source.view('demo-delta-small')['claim']['gross'])
        row=self.s.overlay_slices()['slices'][0]
        self.assertTrue(row['SLICE_IMPAIRMENT_ELIGIBLE'])
        self.assertEqual(row['shortfall_krw'], self.face)
        result=seed.post(self.s, 'impair_slice', 'impair', slice_id='slice-a', reason='REFUND_REDUCED_LINE')
        self.assertEqual(result['entry']['shortfall_krw'], self.face)
        for obj in (result, result['entry'], self.s.overlay_slices(), self.s.overlay_slices()['slices'][0]):
            self.assertEqual(obj['application'], 'SHADOW_NOT_APPLIED')
            self.assertTrue(obj['holder_first'] if 'holder_first' in obj else True)
            self.assertTrue(all(obj[k] is False for k in FALSE_FLAGS))
        self.refuse('SLICE_STATE_INVALID', lambda: seed.post(self.s, 'void_slice', 'no-void', slice_id='slice-a', reason='OPERATOR_WITHDRAWN'))

    def test_holder_first_setoff_and_resolved_hold(self):
        advance(self.s, self.face)
        self.opened()
        seed.distribute(self.source, 'demo-delta-small')
        claim=self.source.view('demo-delta-small')['claim']
        row=self.s.overlay_slices()['slices'][0]
        quote=self.s.case_setoff('sim-slice',self.s.instance_id,draw_day=0,as_of_day=0)
        line=next(l for l in claim['obligations'] if l['payee']=='organizer')
        self.assertEqual(quote['setoff']['base_krw'],line['distributed']-line['recovery_due']-self.face)
        seed.post(self.s,'resolve_slice','resolve',slice_id='slice-a',resolution='SERVED_IN_FULL')
        self.assertEqual(self.s.case_setoff('sim-slice',self.s.instance_id,draw_day=0,as_of_day=0)['setoff'],quote['setoff'])
        self.refuse('SLICE_STATE_INVALID',lambda:seed.open_slice(self.s,'slice-a','reopen'))
        self.assertEqual(row['served_krw'],self.face)

    def test_recourse_and_recovery_share_source_in_both_orders(self):
        for recourse_first in (False, True):
            with self.subTest(recourse_first=recourse_first):
                self.source,self.s=seed.book()
                advance(self.s,self.face)
                self.impaired()
                run(self.s,'default','default')
                seed.distribute(self.source,'demo-delta-mid')
                def recovery_quote():
                    return next(q for r in self.s.overlay_state()['recovery']['advances'] for q in r['quotes'] if q['source_ref']['claim_id']=='demo-delta-mid')
                def post_recovery(amount,key):
                    q=recovery_quote()
                    return seed.post(self.s,'post_recovery',key,advance_ref='sim-slice',source_ref=q['source_ref'],quote_ref=q['quote_ref'],amount_krw=amount)
                q=recovery_quote(); available=q['available_krw']
                # Consume part from the first lane, then check the other lane's quote.
                half=self.face//2
                if recourse_first:
                    recourse(self.s,'slice-a',half,'first')
                    self.assertEqual(recovery_quote()['available_krw'],available-half)
                    post_recovery(half,'second')
                else:
                    post_recovery(half,'first')
                    q2=self.s.overlay_slices()['slices'][0]['quotes'][0]
                    self.assertEqual(q2['available_krw'],available-half)
                    recourse(self.s,'slice-a',half,'second')
                self.assertTrue(verify_manifest(self.s.export_manifest())['ok'])
                recourse(self.s,'slice-a',half,'finish')
                seed.post(self.s,'resolve_slice','resolve',slice_id='slice-a',resolution='RECOURSE_SATISFIED')
                self.assertEqual(self.s.overlay_slices()['slices'][0]['status'],'RESOLVED')

    def test_recourse_rejects_source_overrun_and_stale_quote(self):
        self.impaired()
        # Commit only a small synthetic observed cash amount on the other claim.
        c='demo-delta-mid'; gross=self.source.view(c)['claim']['gross']; cash=self.face//2
        seed.replay(self.source,c,'small','commit_settlement',movement_id='sim-low',gross=gross,amount=cash,fee=0,tax=0,held=gross-cash,adjustment=0)
        seed.replay(self.source,c,'small-dist','apply_distribution',order=['organizer','platform'])
        self.refuse('RECOVERY_SOURCE_EXCEEDED',lambda:recourse(self.s,'slice-a',cash+1))
        q=self.s.overlay_slices()['slices'][0]['quotes'][0]
        recourse(self.s,'slice-a',1,'first')
        self.refuse('RECOVERY_QUOTE_STALE',lambda:seed.post(self.s,'post_slice_recourse','stale',slice_id='slice-a',source_ref=q['source_ref'],quote_ref=q['quote_ref'],amount_krw=1))

    def test_capacity_and_write_failure_preserve_registry(self):
        self.opened()
        self.s.slice_policy['bounds']['max_registry_entries']=2
        # A policy changed in memory cannot be used to silently change an existing slice.
        self.refuse('SIMULATION_CAPACITY',lambda:seed.register(self.s,'capacity',self.face,'demo-alpha-arena'))
        self.s.slice_policy=slices.load_policy(self.s.terms)
        before=copy.deepcopy(self.s.overlay_entries)
        with patch.object(self.s.storage,'save',side_effect=WorkspaceError('WORKSPACE_WRITE_FAILED')):
            with self.assertRaises(ApiError) as caught:
                seed.register(self.s,'write-fail',self.face,'demo-alpha-arena')
        self.assertEqual(caught.exception.code,'WORKSPACE_WRITE_FAILED')
        self.assertEqual(before,self.s.overlay_entries)

    def test_file_restart_and_corrupt_workspace_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            store=FileWorkspace.open(d)
            source,s=seed.book(store)
            seed.register(s,'persist',self.face); seed.open_slice(s,'persist')
            expected=overlay.fold(s.overlay_entries)
            self.assertEqual(store.path.stat().st_mode & 0o777,0o600)
            store.close()
            store=FileWorkspace.open(d)
            restored=CapitalService(store,producer=PinnedFsmProducer(source))
            self.assertEqual(restored.workspace_status,'ACTIVE')
            self.assertEqual(overlay.fold(restored.overlay_entries),expected)
            document=json.loads(store.path.read_text())
            document['overlay']['journal'][-1]['payload']['guard_trace']['advance_pledged_krw']+=1
            store.path.write_text(json.dumps(document))
            store.close()
            store=FileWorkspace.open(d)
            broken=CapitalService(store,producer=PinnedFsmProducer(source))
            self.assertEqual(broken.workspace_status,'WORKSPACE_UNREADABLE')
            store.close()

    def test_resealed_witness_omission_and_exposure_forgery_fail_all_readers(self):
        advance(self.s,self.face)
        self.opened()
        original=copy.deepcopy(self.s.overlay_entries)
        for attack in ('omitted','exposure','pledge','prefix'):
            with self.subTest(attack=attack):
                entries=copy.deepcopy(original)
                e=entries[-1]; w=e['payload']['witness']
                if attack=='omitted': w['advances']={}
                elif attack=='exposure': w['advances']['sim-slice']['outstanding_exposure']=0
                elif attack=='pledge': w['advances']['sim-slice']['reserved_open']+=1
                else:
                    e['after_journal_index']-=1
                    e['payload']['command']['expected_after_journal_index']-=1
                    for earlier in entries[:-1]:
                        earlier['after_journal_index']=min(earlier['after_journal_index'],e['after_journal_index'])
                if attack!='prefix':
                    e['payload']=slices.plan_payload(overlay.fold(entries[:-1]),e)
                # Recompute every wrapper hash and the folded state: byte checks alone pass.
                state=overlay.fold(entries)
                self.s.overlay_entries=entries
                self.s._persist(entries)
                doc=self.s.storage.load()
                with self.assertRaises(WorkspaceError): self.s._validated_restore(doc)
                self.assertEqual(verify_manifest(self.s.export_manifest())['reason'],'OVERLAY_FOLD_MISMATCH')
                report=self.s.reconciliation()
                self.assertEqual(report['status'],'RECON_MISMATCH')
                check=next(c for c in report['checks'] if c['id']=='overlay_fold_digest_equals_persisted')
                self.assertEqual(check['detail'],'claim_slice_link')
                self.s.overlay_entries=copy.deepcopy(original);self.s._persist(original)

    def test_guard_trace_and_constant_flags_are_recomputed(self):
        self.opened()
        for key in ('advance_pledged_krw','eligible_line_krw','portfolio_exposure_before_krw'):
            entries=copy.deepcopy(self.s.overlay_entries);entries[-1]['payload']['guard_trace'][key]+=1
            with self.assertRaises(overlay.OverlayError):overlay.fold(entries)
        entries=copy.deepcopy(self.s.overlay_entries);entries[-1]['payload']['funds_executed']=True
        with self.assertRaises(overlay.OverlayError):overlay.fold(entries)

    def test_resealed_guard_trace_corruption_is_identified_by_all_readers(self):
        self.opened()
        manifest=self.s.export_manifest()
        document=self.s.storage.load()
        entries=copy.deepcopy(self.s.overlay_entries)
        entries[-1]['payload']['guard_trace']['advance_pledged_krw']+=1
        document['overlay']['journal']=entries
        document['overlay']['section_sha256']=section_checksum(document['overlay'])
        self.s.storage._document=document
        self.s.overlay_entries=entries
        with self.assertRaises(WorkspaceError):self.s._validated_restore(document)
        section=manifest['sections']['overlay']
        section['body']['journal']=entries
        section['sha256']=sha256_hex(section['body'])
        manifest['content_digest']=content_digest(manifest)
        self.assertEqual(verify_manifest(manifest)['reason'],'OVERLAY_FOLD_MISMATCH')
        report=self.s.reconciliation()
        self.assertEqual(report['status'],'RECON_MISMATCH')
        row=next(c for c in report['checks'] if c['id']=='overlay_fold_digest_equals_persisted')
        self.assertEqual(row['detail'],'claim_slice_link')

    def test_racing_opens_have_one_winner(self):
        seed.register(self.s,'slice-a',self.face)
        results=[]
        def attempt(i):
            try: results.append(seed.open_slice(self.s,'slice-a','open-'+str(i))['outcome'])
            except ApiError as exc: results.append(exc.code)
        threads=[threading.Thread(target=attempt,args=(i,)) for i in range(2)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertCountEqual(results,['APPLIED','SLICE_STATE_INVALID'])
        self.assertEqual(sum(e['kind']=='SLICE_OPEN' for e in self.s.overlay_entries),1)

    def test_multiple_pending_notes_cannot_reserve_slice_face_twice(self):
        self.opened()
        advance(self.s, self.face*2, name='sim-one', draw=False)
        advance(self.s, self.face*2, name='sim-two', draw=False)
        self.assertEqual(run(self.s, 'draw', 'first-face', 'sim-one')['outcome'], 'ACCEPTED')
        self.refuse('SLICE_DRAW_REFUSED', lambda: run(self.s, 'draw', 'shared-face', 'sim-two'))

    def test_cross_journal_splice_cannot_move_unsafe_slice_before_draw(self):
        self.opened()
        entries = copy.deepcopy(self.s.overlay_entries)
        source, other = seed.book()
        advance(other, self.threshold*7//10)
        # Every slice witness matches index 0; only the later draw exposes this
        # forged ordering. Rebuild the entire envelope and manifest consistently.
        other.overlay_entries = entries
        other._persist(entries)
        with self.assertRaises(WorkspaceError):
            other._validated_restore(other.storage.load())
        self.assertEqual(verify_manifest(other.export_manifest())['reason'], 'OVERLAY_FOLD_MISMATCH')
        self.assertEqual(other.reconciliation()['status'], 'RECON_MISMATCH')

    def test_partial_holder_service_impairment_and_late_cash(self):
        c='demo-delta-mid'; gross=self.source.view(c)['claim']['gross']
        cash=self.face//2
        seed.replay(self.source,c,'small-cash','commit_settlement',movement_id='sim-small',gross=gross,amount=cash,fee=0,tax=0,held=gross-cash,adjustment=0)
        self.opened(claim=c)
        seed.replay(self.source,c,'first-distribution','apply_distribution',order=['organizer','platform'])
        row=self.s.overlay_slices()['slices'][0]
        self.assertEqual(row['served_krw'],cash)
        outstanding_line=next(l['outstanding'] for l in self.source.view(c)['claim']['obligations'] if l['payee']=='organizer')
        seed.refund(self.source,c,outstanding_line)
        seed.post(self.s,'impair_slice','impair',slice_id='slice-a',reason='REFUND_REDUCED_LINE')
        before=self.s.overlay_slices()['slices'][0]
        # The pure view accepts a later bound distribution without an automatic
        # lifecycle transition, including after impairment.
        state=overlay.fold(self.s.overlay_entries)
        obs=slices.observation(self.source.view(c)['claim'],['organizer'])
        obs['lines']['organizer']['distributed']+=cash//2
        late=slices.derived(slices.registry(state)['slice-a'],obs)
        self.assertEqual(late['outstanding_krw'],before['outstanding_krw']-cash//2)
        self.assertEqual(late['shortfall_krw'],before['shortfall_krw']-cash//2)
        self.assertEqual(slices.registry(state)['slice-a']['status'],'IMPAIRED')

    def test_served_slice_and_changed_settlement_cut_do_not_invent_historical_exposure(self):
        self.opened()
        seed.distribute(self.source,'demo-delta-small')
        advance(self.s,self.face,'demo-alpha-arena','sim-other')
        self.assertTrue(verify_manifest(self.s.export_manifest())['ok'])

    def test_http_listing_quote_and_agent_refusal(self):
        from capital.server import make_server
        from http.client import HTTPConnection
        server=make_server(0)
        worker=threading.Thread(target=server.serve_forever)
        worker.start()
        try:
            s=server.service
            seed.register(s,'http-slice',self.face)
            for role,status in (('organizer',200),('auditor',200),('observer',403)):
                token=s.authorizer.bind_role(role)
                client=HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                client.request('GET','/api/overlay/slices',headers={'X-Capital-Token':token})
                response=client.getresponse();payload=json.loads(response.read());client.close()
                self.assertEqual(response.status,status)
                if status==200:self.assertEqual(payload['slices'][0]['slice_id'],'http-slice')
            token=s.authorizer.bind_role('organizer')
            client=HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            client.request('GET','/api/overlay/slices?quote_claim_id=demo-alpha-arena&quote_payee_label=organizer&expected_days=60',headers={'X-Capital-Token':token})
            response=client.getresponse();payload=json.loads(response.read());client.close()
            self.assertEqual(response.status,200)
            self.assertEqual(payload['quote']['registry_check']['status'],'ADMISSIBLE')
            before=s._frozen()
            client=HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            client.request('POST','/api/overlay/commands',json.dumps({'op':'register_slice'}),{'Content-Type':'application/json','X-Capital-Token':s.authorizer.bind_role('agent'),'Origin':'http://127.0.0.1:'+str(server.server_port)})
            response=client.getresponse();payload=json.loads(response.read());client.close()
            self.assertEqual((response.status,payload['error']),(403,'SLICE_AGENT_FORBIDDEN'))
            self.assertEqual(before,s._frozen())
        finally:
            server.shutdown();server.server_close();worker.join(timeout=5)

    def test_contract_covers_slice_commands_receipts_listing_and_underwriting(self):
        from tests.facade_schema import load_contract, validate
        doc=load_contract()
        receipt=seed.register(self.s,'contract',self.face)
        body={'instance_id':self.s.instance_id,'operation_id':'contract',**receipt['entry']['command']}
        validate(body,doc['definitions']['overlay_command_request'],doc)
        validate(receipt,doc['definitions']['overlay_command_receipt'],doc)
        self.assertEqual(receipt['label'],'SIMULATED')
        validate(self.s.overlay_state('contract')['operation'],doc['definitions']['overlay_recorded_operation'],doc)
        seed.open_slice(self.s,'contract')
        validate(self.s.overlay_slices('demo-alpha-arena','organizer',60),doc['definitions']['slice_registry_listing'],doc)
        advance(self.s,self.face)
        validate(self.s.underwrite('sim-slice',self.s.instance_id,'organizer'),doc['definitions']['underwrite_bound'],doc)

    def test_golden_v3_and_empty_registry_legacy_goldens(self):
        service,result=seed.build()
        self.assertEqual(json.loads(seed.GOLDEN.read_text()),result)
        self.assertTrue(verify_manifest(service.export_manifest())['ok'])
        self.assertNotIn('claim_slices',overlay.fold([]))
        for script in ('seed_demo.py','seed_overlay_recovery.py'):
            proc=subprocess.run(['python3',str(ROOT/'scripts'/script)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)


if __name__=='__main__':unittest.main()
