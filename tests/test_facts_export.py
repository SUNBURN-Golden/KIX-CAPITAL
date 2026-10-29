"""Typed SIMULATED facts, coherent cuts, storage fences and HTTP authority gates."""
import copy
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from capital import facts, overlay
from capital.producer import PinnedFsmProducer
from capital.server import make_server
from capital.service import ApiError, CapitalService
from capital.store import FileWorkspace, WorkspaceError, canonical_bytes, envelope
from facade_schema import load_contract, validate
from scripts.facts_vectors import seed, with_overlay


def fetch(service, **query):
    return service.export_facts(urlencode({'instance_id': service.instance_id, **query}))


def clock(key, anchor, start, end):
    return {'overlay_id': key, 'after_journal_index': anchor, 'sim_day': end, 'kind': 'clock',
            'payload': {'from_sim_day': start, 'to_sim_day': end,
                        'actor': overlay.ACTOR, 'clock_source': overlay.CLOCK_SOURCE, 'reason': 'SIMULATED'}}


class FactsTests(unittest.TestCase):
    def assert_error(self, code, status, call):
        with self.assertRaises(ApiError) as cm:
            call()
        self.assertEqual((cm.exception.code, cm.exception.status), (code, status))

    def test_stitch_equals_exports_canonical_bytes_and_preserves_state(self):
        for has_overlay in (False, True):
            s = seed()
            if has_overlay:
                with_overlay(s)
            before = s._frozen()
            manifest = s.export_manifest()
            for limit in (1, 3, 500):
                rows, after = [], None
                while True:
                    page = fetch(s, limit=limit, **({'after': after} if after else {}))
                    doc = load_contract()
                    validate(page, doc['definitions']['facts_page'], doc)
                    self.assertEqual(page['schema'], facts.schema())
                    self.assertEqual(page['schema_sha256'], facts.sha256_hex(facts.schema()))
                    self.assertEqual(page['page_digest'], facts.page_digest(page))
                    for k, v in facts.LABELS.items():
                        self.assertEqual(page[k], v)
                    rows.extend(page['rows'])
                    after = page['next_cursor']
                    if after is None:
                        break
                journal = [r['entry'] for r in rows if r['source'] == 'JOURNAL']
                self.assertEqual(canonical_bytes(journal), canonical_bytes(s.export()['journal']))
                entries = [r['entry'] for r in rows if r['source'] == 'OVERLAY']
                if has_overlay:
                    body = manifest['sections']['overlay']['body']
                    self.assertEqual(canonical_bytes(entries), canonical_bytes(body['journal']))
                    self.assertEqual(page['cut']['overlay_state_digest'], body['overlay_state_digest'])
                    self.assertEqual(page['cut']['overlay_entry_count'], len(entries))
                else:
                    self.assertNotIn('overlay_state_digest', page['cut'])
                    self.assertNotIn('overlay_entry_count', page['cut'])
                self.assertEqual([r['seq'] for r in rows], list(range(len(rows))))
                self.assertEqual(s._frozen(), before)

    def test_query_limits_cursor_and_session_fail_closed(self):
        s = seed()
        for limit in ('0', '-1', '501', '1000', '', '01', '1.0', 'true', '١', '1e2'):
            self.assert_error('INVALID_ARGUMENTS', 400, lambda: fetch(s, limit=limit))
        for extra in ('&unknown=1', '&limit=1&limit=2', '&after=a&after=b', '&instance_id=x'):
            self.assert_error('INVALID_ARGUMENTS', 400, lambda: s.export_facts('instance_id='+s.instance_id+extra))
        self.assert_error('SESSION_CHANGED', 409, lambda: s.export_facts(''))
        self.assert_error('SESSION_CHANGED', 409, lambda: fetch(s, instance_id='stale'))
        cut = fetch(s)['cut']
        for cursor in ('', 'bad', facts.cursor(0, cut), facts.cursor(21, cut),
                       facts.cursor(99, cut), facts.cursor(1, cut)+' ', facts.cursor(1, cut).upper()):
            self.assert_error('INVALID_CURSOR', 400, lambda: fetch(s, after=cursor))
        self.assertEqual(fetch(s)['limit'], facts.LIMIT_DEFAULT)

    def test_journal_and_overlay_only_movement_refuse_old_cursor(self):
        for mode in ('journal', 'overlay'):
            s = seed()
            old = fetch(s, limit=1)['next_cursor']
            before = s.machine.state_digest()
            if mode == 'journal':
                s.execute({'instance_id':s.instance_id,'operation_id':'more-offer','op':'offer',
                           'advance_id':'sim-more','args':{'fixture_id':'sim-committed','amount':1}})
            else:
                s.overlay_command({'instance_id':s.instance_id,'operation_id':'only-overlay','op':'advance_day',
                                   'from_sim_day':0,'to_sim_day':1,'reason':'SIMULATED'})
                self.assertEqual(s.machine.state_digest(), before)
            self.assert_error('CUT_MOVED', 409, lambda: fetch(s, limit=1, after=old))

    def test_duplicate_order_in_pure_merge_and_reloaded_mode_0600_workspace(self):
        s = CapitalService()
        s.execute({'instance_id':s.instance_id,'operation_id':'one-offer','op':'offer',
                   'advance_id':'sim-one','args':{'fixture_id':'sim-committed','amount':1}})
        journal = s.machine.export_journal()
        entries = [clock('early', 0, 0, 1), clock('late', 1, 1, 2)]
        entries.append(copy.deepcopy(entries[0]))
        self.assertEqual(overlay.fold(entries, 1)['entry_count'], 2)
        rows = facts.build_rows(journal, entries)
        self.assertEqual([r['fact_id'] for r in rows], ['O:00000000', 'J:00000000', 'O:00000001', 'O:00000002'])
        self.assertEqual([r['duplicate'] for r in rows], [0, 0, 0, 1])
        self.assertEqual(rows[-1]['journal_position'], 0)
        with tempfile.TemporaryDirectory() as d:
            document = s.storage.load()
            raw = canonical_bytes(envelope('synthetic-copy', document['payload'], overlay.build_section(entries)))
            path = Path(d) / 'workspace.json'
            path.write_bytes(raw)
            path.chmod(0o600)
            with FileWorkspace.open(d) as storage:
                restored = CapitalService(storage)
                self.assertEqual(restored.workspace_status, 'ACTIVE')
                result = fetch(restored)
                self.assertEqual([r['duplicate'] for r in result['rows']], [0,0,0,1])
                extracted = [r['entry'] for r in result['rows'] if r['source']=='OVERLAY']
                self.assertEqual(extracted, overlay.export_section(entries, 1)['journal'])
                self.assertEqual(extracted, restored.export_manifest()['sections']['overlay']['body']['journal'])

    def test_unhealthy_workspace_refuses_first_and_continuing_pages(self):
        with tempfile.TemporaryDirectory() as d:
            with FileWorkspace.open(d) as storage:
                s = CapitalService(storage)
                from scripts.seed_demo import apply_steps
                apply_steps(s)
                old = fetch(s, limit=1)['next_cursor']
                original = storage.path.read_bytes()
                for corrupted in (b'{broken', b''):
                    storage.path.write_bytes(corrupted)
                    for query in ({}, {'after':old}):
                        self.assert_error('WORKSPACE_UNREADABLE', 503, lambda: fetch(s, **query))
                storage.path.write_bytes(original)
                with patch.object(storage, 'load', side_effect=WorkspaceError('WORKSPACE_UNREADABLE')):
                    self.assert_error('WORKSPACE_UNREADABLE',503,lambda:fetch(s,after=old))
                # A checksum-valid different book on disk must not be mistaken for the loaded book.
                other = CapitalService()
                other.execute({'instance_id':other.instance_id,'operation_id':'other','op':'offer',
                               'advance_id':'sim-other','args':{'fixture_id':'sim-committed','amount':1}})
                storage.path.write_bytes(canonical_bytes(other.storage.load()))
                self.assert_error('STORAGE_STATE_MISMATCH',503,lambda:fetch(s,after=old))
                storage.path.write_bytes(b'{broken')
            with FileWorkspace.open(d) as storage:
                failed = CapitalService(storage)
                self.assertEqual(failed.workspace_status,'WORKSPACE_UNREADABLE')
                self.assert_error('WORKSPACE_UNREADABLE',503,lambda:fetch(failed))

    def test_unsupported_producer_and_row_widths_fail_closed(self):
        s = seed()
        class Unpinned(PinnedFsmProducer):
            pass
        s.producer = Unpinned()
        self.assert_error('COHERENT_SNAPSHOT_UNSUPPORTED',503,lambda:fetch(s))
        row = facts.build_rows(seed().machine.export_journal(), [])[0]
        for key, value in [('seq', True), ('seq', 100000000), ('kind','é'), ('kind','a'*33),
                           ('amount_krw',True),('amount_krw',-1),('amount_krw',facts.KRW['max_atoms']+1),
                           ('sim_day',-1),('duplicate',True),('fact_id','J:1'),('source','journal')]:
            with self.subTest(key=key,value=value), self.assertRaises(facts.FactsError):
                facts.validate_row({**row,key:value},sealed=False)
        for value in (True, '1', 1.5, None, facts.KRW['max_atoms']+1):
            journal = copy.deepcopy(seed().machine.export_journal())
            journal[0]['body']['amount']=value
            with self.assertRaises(facts.FactsError) as cm:
                facts.build_rows(journal,[])
            self.assertEqual((cm.exception.code,cm.exception.status),('FACTS_ROW_INVALID',500))

    def test_empty_book_has_one_final_page(self):
        p=fetch(CapitalService())
        self.assertEqual(p['rows'],[])
        self.assertEqual(p['row_count_total'],0)
        self.assertIsNone(p['next_cursor'])
        self.assertEqual(p['chain_before'],p['chain_after'])


class FactsHttpTests(unittest.TestCase):
    def setUp(self):
        self.server=make_server(0)
        self.worker=threading.Thread(target=self.server.serve_forever)
        self.worker.start()
        self.addCleanup(self.stop)
        from scripts.seed_demo import apply_steps
        apply_steps(self.server.service)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()

    def request(self,path,role=None):
        conn=HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        try:
            conn.request('GET',path,headers={'X-Capital-Role':role} if role else {})
            response=conn.getresponse()
            return response.status,response.read()
        finally:
            conn.close()

    def test_canonical_body_schema_and_role_gate(self):
        s=self.server.service
        path='/api/export/facts?'+urlencode({'instance_id':s.instance_id,'limit':3})
        status,raw=self.request(path)
        self.assertEqual(status,200)
        page=json.loads(raw)
        self.assertEqual(raw,canonical_bytes(page))
        self.assertFalse(raw.endswith(b'\n'))
        status,raw=self.request('/api/export/facts/schema')
        self.assertEqual((status,raw),(200,canonical_bytes(facts.schema())))
        for role in ('observer','agent'):
            # Bind synthetic tokens through the same authorizer used by the server.
            token=self.server.authorizer.bind_role(role)
            conn=HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
            try:
                conn.request('GET',path,headers={'X-Capital-Token':token})
                response=conn.getresponse()
                self.assertEqual(response.status,403)
                self.assertEqual(json.loads(response.read())['error'],'ROLE_FORBIDDEN')
            finally:
                conn.close()
        status,raw=self.request(path+'&after=bad')
        self.assertEqual((status,json.loads(raw)['error']),(400,'INVALID_CURSOR'))
