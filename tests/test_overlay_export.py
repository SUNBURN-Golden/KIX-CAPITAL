"""V3 overlay export section, conditional reconciliation check, and verifier format gating.

CAPITAL_OVERLAY_DIGEST_EXPORT.md 3.2: an empty overlay keeps the V2 manifest byte for byte;
a non-empty overlay moves the manifest to V3 with one `overlay` section. SIMULATED only.
"""
from __future__ import annotations

import copy
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest import mock

from capital import export, overlay, recon, verify
from capital.server import make_server
from capital.store import FileWorkspace
from tests import facade_schema
from tests.test_overlay import GOLDEN_DIR, seed, tick

V2 = 'KIX_CAPITAL_EXPORT_MANIFEST_V2'
V3 = 'KIX_CAPITAL_EXPORT_MANIFEST_V3'
OLD_SECTIONS = export.SECTION_IDS


def ticked_service(storage=None):
    service = seed.build_service(storage)
    tick(service, 'x-1', 0, 60)
    return service


def resealed(manifest):
    """Re-hash a hand-edited manifest so only the structural defect remains."""
    manifest = copy.deepcopy(manifest)
    manifest['content_digest'] = export.content_digest(manifest)
    return manifest


class ManifestFormatTests(unittest.TestCase):
    def test_empty_overlay_is_byte_identical_v2(self):
        service = seed.build_service()
        manifest = service.export_manifest()
        demo = json.loads((GOLDEN_DIR / 'demo.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['format'], V2)
        self.assertEqual(tuple(manifest['sections']), OLD_SECTIONS)
        self.assertEqual(manifest['content_digest'], demo['content_digest'])
        recon_body = manifest['sections']['reconciliation']['body']
        self.assertEqual(len(recon_body['checks']), 6)
        self.assertNotIn('overlay_state_digest', recon_body['scope'])
        self.assertNotEqual(service.overlay_state()['export'], 'NOT_INCLUDED')
        self.assertEqual(service.overlay_state()['export'], 'ABSENT_WHEN_EMPTY')

    def test_advance_day_moves_the_manifest_to_v3_with_an_overlay_section(self):
        service = seed.build_service()
        before = service.export_manifest()
        tick(service, 'x-1', 0, 60)
        after = service.export_manifest()
        self.assertEqual(after['format'], V3)
        self.assertEqual(tuple(after['sections']), export.SECTION_IDS_V3)
        body = after['sections']['overlay']['body']
        self.assertEqual(body['part_tag'], 'overlaypart')
        expected = overlay.export_section(service.overlay_entries, len(service.machine.export_journal()))
        self.assertEqual({k: v for k, v in body.items() if k != 'part_tag'}, expected)
        self.assertEqual(body['label'], 'SIMULATED')
        self.assertEqual(body['sim_day'], 60)
        self.assertEqual(body['clock_source'], 'SIM_LOGICAL_CLOCK')
        self.assertEqual(body['entry_count'], len(body['journal']))
        self.assertEqual(body['overlay_state_digest'], overlay.state_digest(body['state']))
        text = json.dumps(body)
        for key in export.VOLATILE_KEYS:
            self.assertNotIn(f'"{key}"', text)
        # The other five unchanged sections do not see the overlay.
        for name in ('journal', 'receipts', 'projection', 'statement', 'fixtures', 'source_pin'):
            self.assertEqual(after['sections'][name]['sha256'], before['sections'][name]['sha256'], name)
        self.assertNotEqual(after['sections']['reconciliation']['sha256'],
                            before['sections']['reconciliation']['sha256'])
        self.assertEqual(service.overlay_state()['export'], 'INCLUDED_IN_MANIFEST_V3')

    def test_export_does_not_write(self):
        service = ticked_service()
        frozen = service._frozen()
        service.export_manifest()
        service.reconciliation()
        self.assertEqual(service._frozen(), frozen)

    def test_build_manifest_gates_the_section_set_by_format(self):
        service = ticked_service()
        manifest = service.export_manifest()
        sections = {name: copy.deepcopy(manifest['sections'][name]['body']) for name in export.SECTION_IDS_V3}
        for body in sections.values():
            body.pop('part_tag')
        # Without `overlay` the set is a plain V2 set; dropping any other section breaks both formats.
        broken = {k: v for k, v in sections.items() if k != 'journal'}
        with self.assertRaises(export.ExportError) as caught:
            export.build_manifest(sections=broken, instance_id='i', signer=export.UnsignedSigner(),
                                  status='COMPLETE', incomplete_reasons=[])
        self.assertEqual(caught.exception.code, 'SECTION_SET')
        built = export.build_manifest(sections=sections, instance_id='i', signer=export.UnsignedSigner(),
                                      status='COMPLETE', incomplete_reasons=[])
        self.assertEqual(built['format'], V3)


class VerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v3 = ticked_service().export_manifest()
        cls.v2 = seed.build_service().export_manifest()

    def test_accepts_v2_and_v3(self):
        for manifest, fmt, count in ((self.v2, V2, 7), (self.v3, V3, 8)):
            report = verify.verify_manifest(copy.deepcopy(manifest))
            self.assertTrue(report['ok'], report)
            self.assertEqual(report['format'], fmt)
            self.assertEqual(len(report['sections']), count)
            self.assertEqual(set(report['sections'].values()), {'MATCHED'})

    def test_rejects_v3_without_overlay_as_section_set(self):
        doc = copy.deepcopy(self.v3)
        del doc['sections']['overlay']
        report = verify.verify_manifest(resealed(doc))
        self.assertFalse(report['ok'])
        self.assertEqual(report['reason'], 'SECTION_SET')

    def test_rejects_v2_with_overlay_as_section_set(self):
        doc = copy.deepcopy(self.v3)
        doc['format'] = V2
        report = verify.verify_manifest(resealed(doc))
        self.assertEqual(report['reason'], 'SECTION_SET')
        self.assertFalse(report['ok'])

    def test_other_set_deviations_stay_manifest_shape(self):
        doc = copy.deepcopy(self.v3)
        del doc['sections']['journal']
        self.assertEqual(verify.verify_manifest(doc)['reason'], 'MANIFEST_SHAPE')
        doc = copy.deepcopy(self.v2)
        doc['sections']['extra'] = doc['sections']['journal']
        self.assertEqual(verify.verify_manifest(doc)['reason'], 'MANIFEST_SHAPE')
        doc = copy.deepcopy(self.v3)
        doc['format'] = 'KIX_CAPITAL_EXPORT_MANIFEST_V9'
        self.assertEqual(verify.verify_manifest(doc)['reason'], 'MANIFEST_SHAPE')

    def test_overlay_byte_flip_is_a_section_hash_mismatch(self):
        doc = copy.deepcopy(self.v3)
        doc['sections']['overlay']['body']['sim_day'] += 1
        report = verify.verify_manifest(doc)
        self.assertEqual(report['reason'], 'SECTION_HASH_MISMATCH:overlay')
        self.assertEqual(report['sections']['overlay'], 'SECTION_HASH_MISMATCH')

    def test_verify_path_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'm.json'
            path.write_bytes(export.canonical_bytes(self.v3))
            self.assertTrue(verify.verify_path(path)['ok'])


class ReconciliationTests(unittest.TestCase):
    def test_check_is_conditional_on_a_non_empty_overlay(self):
        service = seed.build_service()
        empty = service.reconciliation()
        self.assertEqual([c['id'] for c in empty['checks']], list(recon.CHECK_IDS))
        self.assertNotIn('overlay_state_digest', empty['scope'])
        tick(service, 'x-1', 0, 60)
        report = service.reconciliation()
        self.assertEqual(len(report['checks']), 7)
        last = report['checks'][-1]
        self.assertEqual(last['id'], 'overlay_fold_digest_equals_persisted')
        self.assertEqual(last['status'], 'MATCHED')
        self.assertEqual(report['status'], 'MATCHED')
        self.assertEqual(report['scope']['overlay_state_digest'],
                         overlay.state_digest(overlay.fold(service.overlay_entries)))

    def test_file_workspace_checks_the_persisted_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            port = FileWorkspace.open(tmp)
            try:
                service = ticked_service(port)
                self.assertEqual(service.reconciliation()['checks'][-1]['status'], 'MATCHED')
                good = port.load()
                bad = copy.deepcopy(good)
                bad['overlay']['overlay_state']['digest'] = '0' * 64
                with mock.patch.object(port, 'load', return_value=bad):
                    report = service.reconciliation()
                    self.assertEqual(report['status'], 'RECON_MISMATCH')
                    self.assertEqual(report['checks'][-1]['status'], 'RECON_MISMATCH')
                    manifest = service.export_manifest()
                self.assertEqual(manifest['format'], V3)
                self.assertEqual(manifest['status'], 'INCOMPLETE')
                self.assertIn('RECONCILIATION_NOT_CLEAN', manifest['incomplete_reasons'])
            finally:
                port.close()

    def test_fold_check_reports_a_corrupt_journal(self):
        entries = ticked_service().overlay_entries
        broken = copy.deepcopy(entries)
        broken[0]['kind'] = 'bogus'
        matched, digest, detail = recon.overlay_fold_check(broken, {}, 0)
        self.assertEqual((matched, digest, detail), (False, None, 'overlay_fold'))


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.port = cls.server.server_port
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        cls.contract = facade_schema.load_contract()
        cls.instance, cls.token = None, None
        state = cls.call('GET', '/api/state')[1]
        cls.instance, cls.token = state['instance_id'], state['local_token']

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=2)

    @classmethod
    def call(cls, method, path, body=None):
        headers = {}
        payload = None
        if body is not None:
            headers['Content-Type'] = 'application/json'
            payload = json.dumps(body).encode()
        if cls.token is not None:
            headers['X-Capital-Token'] = cls.token
        client = HTTPConnection('127.0.0.1', cls.port, timeout=5)
        try:
            client.request(method, path, body=payload, headers=headers)
            response = client.getresponse()
            return response.status, json.loads(response.read().decode('utf-8'))
        finally:
            client.close()

    def check(self, name, value):
        facade_schema.validate(value, self.contract['definitions'][name], self.contract)

    def test_empty_then_non_empty_overlay_over_http(self):
        status, manifest = self.call('GET', '/api/export/manifest')
        self.assertEqual((status, manifest['format']), (200, V2))
        self.check('manifest', manifest)
        self.assertTrue(verify.verify_manifest(manifest)['ok'])
        status, quote = self.call('GET', '/api/overlay')
        self.assertEqual(quote['export'], 'ABSENT_WHEN_EMPTY')
        self.check('overlay_state', quote)
        status, receipt = self.call('POST', '/api/overlay/commands', {
            'instance_id': self.instance, 'operation_id': 'http-1', 'op': 'advance_day',
            'from_sim_day': 0, 'to_sim_day': 30, 'reason': 'http'})
        self.assertEqual(status, 200, receipt)
        status, manifest = self.call('GET', '/api/export/manifest')
        self.assertEqual(manifest['format'], V3)
        self.check('manifest', manifest)
        self.assertTrue(verify.verify_manifest(manifest)['ok'])
        status, report = self.call('GET', '/api/reconciliation')
        self.check('reconciliation', report)
        self.assertEqual(report['checks'][-1]['id'], 'overlay_fold_digest_equals_persisted')
        status, quote = self.call('GET', '/api/overlay')
        self.assertEqual(quote['export'], 'INCLUDED_IN_MANIFEST_V3')
        self.check('overlay_state', quote)


if __name__ == '__main__':
    unittest.main()
