"""Cross-artifact consistency evidence: individually valid artifacts from different cuts.

The CLI reads each explicit input once with the existing offline verifiers and
then compares the F04 journal, overlay and fixture commitments shared by the
workspace file, the export manifest and the facts directory. Fixtures are
SIMULATED and built in temporary directories; nothing is committed under
tests/vectors/ for these tests.
"""
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from capital import evidence_crosscut as crosscut, facts
from capital.export import content_digest, sha256_hex
from capital.service import CapitalService, digest
from capital.store import FILE_NAME, FileWorkspace, canonical_bytes
from scripts.seed_demo import apply_steps

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / 'tests' / 'golden' / 'demo.json'
KEYSET_FIXTURE = ROOT / 'tests' / 'vectors' / 'dev-keyset-active.json'
KEYSET_MANIFEST = ROOT / 'tests' / 'vectors' / 'manifest' / 'dev-keyset-kid-1.json'
CORRUPT_FACTS = ROOT / 'tests' / 'vectors' / 'facts' / 'corrupt' / 'entry-byte'


def tick(service, key, start, end):
    """advance_day overlay command; appends terms_binding/clock/posting entries only."""
    receipt = service.overlay_command({
        'instance_id': service.instance_id, 'operation_id': key,
        'op': 'advance_day', 'from_sim_day': start, 'to_sim_day': end,
        'reason': 'SIMULATED crosscut fixture'})
    assert receipt.get('outcome') == 'APPLIED', receipt


def write_pages(directory, journal, entries, state_digest, fixtures_digest):
    directory.mkdir()
    after, index = None, 0
    while True:
        page = facts.paginate(journal, entries, state_digest, fixtures_digest, after, 500)
        (directory / f'page-{index:04d}.json').write_bytes(canonical_bytes(page))
        index += 1
        after = page['next_cursor']
        if after is None:
            break


def build_book(root, name, *, ticks=()):
    """One coherent cut: workspace file, manifest file and facts directory.

    Returns (workspace_file, manifest_file, facts_dir, service_data).
    """
    workspace_dir = root / f'{name}-workspace'
    workspace_dir.mkdir()
    storage = FileWorkspace.open(workspace_dir)
    service = CapitalService(storage)
    try:
        apply_steps(service)
        for index, end in enumerate(ticks):
            start = 0 if index == 0 else ticks[index - 1]
            tick(service, f'tick-{index}', start, end)
        manifest = service.export_manifest()
        journal = service.machine.export_journal()
        entries = copy.deepcopy(service.overlay_entries)
        state_digest = service.machine.state_digest()
        fixtures_digest = digest(service.fixtures.rows)
    finally:
        service.observability.close()
        storage.close()
    workspace_file = workspace_dir / FILE_NAME
    manifest_file = root / f'{name}-manifest.json'
    manifest_file.write_bytes(canonical_bytes(manifest))
    facts_dir = root / f'{name}-facts'
    write_pages(facts_dir, journal, entries, state_digest, fixtures_digest)
    data = {'journal': journal, 'entries': entries, 'state_digest': state_digest,
            'fixtures_digest': fixtures_digest, 'manifest': manifest}
    return workspace_file, manifest_file, facts_dir, data


def build_other_book(root, name='other'):
    """A second independently valid book with a different journal."""
    workspace_dir = root / f'{name}-workspace'
    workspace_dir.mkdir()
    storage = FileWorkspace.open(workspace_dir)
    service = CapitalService(storage)
    try:
        service.execute({'instance_id': service.instance_id, 'operation_id': 'other-offer',
                         'op': 'offer', 'advance_id': 'sim-other',
                         'args': {'fixture_id': 'sim-committed', 'amount': 1}})
        manifest = service.export_manifest()
        journal = service.machine.export_journal()
        state_digest = service.machine.state_digest()
        fixtures_digest = digest(service.fixtures.rows)
    finally:
        service.observability.close()
        storage.close()
    manifest_file = root / f'{name}-manifest.json'
    manifest_file.write_bytes(canonical_bytes(manifest))
    facts_dir = root / f'{name}-facts'
    write_pages(facts_dir, journal, [], state_digest, fixtures_digest)
    return workspace_dir / FILE_NAME, manifest_file, facts_dir


def reseal(manifest, mutate):
    """Mutate section bodies, then restore internally valid hashes.

    The manifest stays UNSIGNED, so recomputing the section hashes and the
    content digest yields a document the manifest verifier still accepts while
    its content no longer matches the other artifacts.
    """
    changed = copy.deepcopy(manifest)
    mutate(changed['sections'])
    for section in changed['sections'].values():
        section['sha256'] = sha256_hex(section['body'])
    changed['content_digest'] = content_digest(changed)
    return changed


def tree(root):
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(Path(root).rglob('*')) if p.is_file()}


def statuses(report):
    return {row['id']: row['status'] for row in report['checks']}


def reasons(report):
    return {row['id']: row['reason'] for row in report['checks']}


class CrosscutFixtureTests(unittest.TestCase):
    """The seeded fixtures themselves: V2 empty-overlay and V3 non-empty books."""

    def test_fixture_books_are_coherent_and_differ_only_by_overlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, _, _, a = build_book(root, 'a')
            _, _, _, b = build_book(root, 'b', ticks=(60,))
            self.assertEqual(a['journal'], b['journal'])
            self.assertEqual(a['state_digest'], b['state_digest'])
            self.assertEqual(a['entries'], [])
            self.assertTrue(b['entries'])
            self.assertNotIn('overlay', a['manifest']['sections'])
            self.assertIn('overlay', b['manifest']['sections'])
            golden = json.loads(GOLDEN.read_text(encoding='utf-8'))
            self.assertEqual(a['state_digest'], golden['state_digest'])


class CrosscutCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ws_a, self.manifest_a, self.facts_a, self.data_a = build_book(self.root, 'a')
        self.ws_b, self.manifest_b, self.facts_b, self.data_b = build_book(self.root, 'b', ticks=(60,))

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, '-m', 'capital.evidence_crosscut', *map(str, args)],
            cwd=ROOT, capture_output=True, timeout=120)

    def args(self, workspace=None, manifest=None, facts_dir=None):
        return ('--workspace', workspace or self.ws_a,
                '--manifest', manifest or self.manifest_a,
                '--facts', facts_dir or self.facts_a)

    def test_matched_v2_set_passes_and_is_byte_deterministic(self):
        before = tree(self.root)
        first, second = self.run_cli(*self.args()), self.run_cli(*self.args())
        self.assertEqual((first.returncode, first.stderr), (0, b''))
        self.assertEqual(first.stdout, second.stdout)
        report = json.loads(first.stdout)
        self.assertEqual(first.stdout, canonical_bytes(report) + b'\n')
        self.assertIs(report['ok'], True)
        self.assertIsNone(report['reason'])
        self.assertEqual(report['format'], 'KIX_CAPITAL_EVIDENCE_CROSSCUT_V1')
        self.assertEqual(report['mode'], 'EVIDENCE_CROSSCUT_CHECK')
        self.assertEqual(report['label'], 'SIMULATED')
        self.assertEqual(report['diagnostic'], 'LOCAL_ONLY')
        self.assertEqual(statuses(report),
                         {name: 'MATCHED' for name in crosscut.CHECK_ORDER})
        golden = json.loads(GOLDEN.read_text(encoding='utf-8'))
        self.assertEqual(report['commitments'], {
            'state_digest': golden['state_digest'],
            'journal_length': len(self.data_a['journal']),
            'overlay_present': False,
            'overlay_state_digest': None,
            'overlay_entry_count': None,
            'fixtures_digest': self.data_a['fixtures_digest'],
        })
        for key in ('authentication', 'source_cut', 'common_ownership'):
            self.assertEqual(report[key], 'NOT_BOUND')
        self.assertEqual(report['wholesale_replacement'], 'NOT_DETECTABLE')
        self.assertIs(report['stage7_authenticated_export'], False)
        self.assertIs(report['funds_executed'], False)
        self.assertIs(report['lock_taken'], False)
        self.assertIs(report['writes'], False)
        self.assertIs(report['workspace_mutated'], False)
        self.assertEqual(report['repair'], 'NOT_IMPLEMENTED')
        inputs = report['inputs']
        self.assertEqual(inputs['workspace']['sha256'],
                         hashlib.sha256(self.ws_a.read_bytes()).hexdigest())
        self.assertEqual(inputs['manifest']['sha256'],
                         hashlib.sha256(self.manifest_a.read_bytes()).hexdigest())
        self.assertIsNotNone(inputs['facts']['sha256'])
        self.assertIs(inputs['workspace']['report']['ok'], True)
        self.assertIs(inputs['manifest']['report']['ok'], True)
        self.assertIs(inputs['facts']['report']['ok'], True)
        self.assertEqual(tree(self.root), before)

    def test_matched_v3_set_passes(self):
        proc = self.run_cli(*self.args(self.ws_b, self.manifest_b, self.facts_b))
        self.assertEqual((proc.returncode, proc.stderr), (0, b''))
        report = json.loads(proc.stdout)
        self.assertEqual(statuses(report),
                         {name: 'MATCHED' for name in crosscut.CHECK_ORDER})
        self.assertEqual(report['commitments']['overlay_present'], True)
        self.assertEqual(report['commitments']['overlay_state_digest'],
                         self.data_b['manifest']['sections']['overlay']['body']['overlay_state_digest'])
        self.assertEqual(report['commitments']['overlay_entry_count'],
                         len(self.data_b['entries']))
        self.assertEqual(report['commitments']['state_digest'], self.data_a['state_digest'])

    def test_independently_valid_books_fail_with_named_reasons(self):
        ws_o, manifest_o, facts_o = build_other_book(self.root)
        before = tree(self.root)
        proc = self.run_cli(*self.args(ws_o, manifest_o, facts_o))
        # The coherent other book passes on its own.
        self.assertEqual(proc.returncode, 0)
        proc = self.run_cli('--workspace', self.ws_a,
                            '--manifest', manifest_o, '--facts', facts_o)
        self.assertEqual((proc.returncode, proc.stderr), (1, b''))
        report = json.loads(proc.stdout)
        self.assertEqual(reasons(report)['journal_content'], 'CROSS_JOURNAL_CONTENT_MISMATCH')
        self.assertEqual(reasons(report)['f04_commitment'], 'CROSS_STATE_DIGEST_MISMATCH')
        # Both books carry an empty overlay: presence matches vacuously.
        for name in ('overlay_presence', 'overlay_content', 'overlay_commitment'):
            self.assertEqual(statuses(report)[name], 'MATCHED')
        self.assertEqual(statuses(report)['fixtures_commitment'], 'MATCHED')
        self.assertEqual(report['reason'], 'CROSS_JOURNAL_CONTENT_MISMATCH')
        # Every artifact still verifies on its own merits.
        for side in ('workspace', 'manifest', 'facts'):
            self.assertIs(report['inputs'][side]['ok'], True)
        self.assertEqual(tree(self.root), before)

    def test_overlay_only_cut_fails_presence_with_same_journal(self):
        # Same seeded book before and after an overlay-only clock tick: the F04
        # journal, state digest and fixtures all match; only the overlay moved.
        proc = self.run_cli('--workspace', self.ws_a,
                            '--manifest', self.manifest_b, '--facts', self.facts_b)
        self.assertEqual(proc.returncode, 1)
        report = json.loads(proc.stdout)
        self.assertEqual(statuses(report)['journal_content'], 'MATCHED')
        self.assertEqual(statuses(report)['f04_commitment'], 'MATCHED')
        self.assertEqual(reasons(report)['overlay_presence'], 'CROSS_OVERLAY_PRESENCE_MISMATCH')
        detail = next(row for row in report['checks'] if row['id'] == 'overlay_presence')['detail']
        self.assertEqual(detail, {'workspace': False, 'manifest': True, 'facts': True})
        for name in ('overlay_content', 'overlay_commitment'):
            self.assertEqual(statuses(report)[name], 'NOT_CHECKED')
        self.assertEqual(statuses(report)['fixtures_commitment'], 'MATCHED')
        # Reversed mix: a non-empty overlay cut against an empty-overlay manifest/facts.
        proc = self.run_cli('--workspace', self.ws_b,
                            '--manifest', self.manifest_a, '--facts', self.facts_a)
        report = json.loads(proc.stdout)
        self.assertEqual(reasons(report)['overlay_presence'], 'CROSS_OVERLAY_PRESENCE_MISMATCH')

    def test_overlay_content_and_commitment_mismatch(self):
        # A hash-valid V3 manifest whose overlay journal belongs to a later cut.
        _, manifest_c, facts_c, data_c = build_book(self.root, 'c', ticks=(60, 61))
        proc = self.run_cli('--workspace', self.ws_b,
                            '--manifest', manifest_c, '--facts', facts_c)
        self.assertEqual(proc.returncode, 1)
        report = json.loads(proc.stdout)
        self.assertEqual(statuses(report)['journal_content'], 'MATCHED')
        self.assertEqual(statuses(report)['overlay_presence'], 'MATCHED')
        self.assertEqual(reasons(report)['overlay_content'], 'CROSS_OVERLAY_CONTENT_MISMATCH')
        self.assertEqual(reasons(report)['overlay_commitment'], 'CROSS_OVERLAY_DIGEST_MISMATCH')
        self.assertEqual(statuses(report)['fixtures_commitment'], 'MATCHED')
        self.assertEqual(data_c['entries'][:len(self.data_b['entries'])], self.data_b['entries'])

    def test_resealed_manifest_fixtures_mismatch_passes_own_verifier(self):
        tampered = reseal(self.data_a['manifest'], lambda s: s['fixtures']['body'].update(
            fixtures_digest='0' * 64))
        path = self.root / 'tampered-fixtures.json'
        path.write_bytes(canonical_bytes(tampered))
        from capital.verify import verify_manifest
        self.assertIs(verify_manifest(json.loads(path.read_bytes()))['ok'], True)
        proc = self.run_cli('--workspace', self.ws_a, '--manifest', path, '--facts', self.facts_a)
        self.assertEqual(proc.returncode, 1)
        report = json.loads(proc.stdout)
        self.assertEqual(statuses(report)['manifest_verify'], 'MATCHED')
        self.assertEqual(statuses(report)['journal_content'], 'MATCHED')
        self.assertEqual(reasons(report)['fixtures_commitment'], 'CROSS_FIXTURES_MISMATCH')
        self.assertEqual(report['reason'], 'CROSS_FIXTURES_MISMATCH')
        self.assertIsNone(report['commitments']['fixtures_digest'])

    def test_resealed_manifest_non_dict_body_fails_closed(self):
        # `verify_manifest` accepts a resealed V2 envelope whose section body is
        # not a mapping; extraction must fail closed rather than raise.
        from capital.verify import verify_manifest
        mutations = {
            'journal-body-list': lambda s: s['journal'].__setitem__('body', []),
            'fixtures-body-list': lambda s: s['fixtures'].__setitem__('body', []),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                tampered = reseal(self.data_a['manifest'], mutate)
                path = self.root / f'{name}.json'
                path.write_bytes(canonical_bytes(tampered))
                self.assertIs(verify_manifest(json.loads(path.read_bytes()))['ok'], True)
                proc = self.run_cli('--workspace', self.ws_a, '--manifest', path,
                                    '--facts', self.facts_a)
                self.assertEqual((proc.returncode, proc.stderr), (1, b''))
                report = json.loads(proc.stdout)
                self.assertEqual(statuses(report)['workspace_audit'], 'MATCHED')
                self.assertEqual(statuses(report)['manifest_verify'], 'MISMATCH')
                self.assertEqual(reasons(report)['manifest_verify'],
                                 'MANIFEST_EXTRACT_FAILED')
                self.assertEqual(statuses(report)['facts_verify'], 'MATCHED')
                for check_name in crosscut.CROSS_CHECKS:
                    self.assertEqual(statuses(report)[check_name], 'NOT_CHECKED')

    def test_facts_verification_uses_the_captured_bytes(self):
        # Capture each page once, then corrupt the directory: replay of the
        # captured bytes is unaffected while a fresh directory read fails.
        paths = sorted(self.facts_a.glob('page-*.json'))
        raws = [(path.name, path.read_bytes()) for path in paths]
        paths[0].write_bytes(b'{}')
        self.assertTrue(facts.verify_raw_pages(raws)['ok'])
        self.assertIs(facts.verify_dir(self.facts_a)['ok'], False)

    def test_resealed_manifest_journal_replay_fails(self):
        def mutate(sections):
            entries = copy.deepcopy(sections['journal']['body']['entries'])
            entries[0] = {**entries[0], 'op': 'BOGUS'}
            sections['journal']['body']['entries'] = entries
        tampered = reseal(self.data_a['manifest'], mutate)
        path = self.root / 'tampered-journal.json'
        path.write_bytes(canonical_bytes(tampered))
        proc = self.run_cli('--workspace', self.ws_a, '--manifest', path, '--facts', self.facts_a)
        self.assertEqual(proc.returncode, 1)
        report = json.loads(proc.stdout)
        self.assertEqual(statuses(report)['manifest_verify'], 'MATCHED')
        self.assertEqual(reasons(report)['journal_content'], 'CROSS_JOURNAL_CONTENT_MISMATCH')
        self.assertEqual(reasons(report)['f04_commitment'], 'CROSS_JOURNAL_REPLAY_FAILED')

    def test_missing_and_failed_inputs_leave_dependents_not_checked(self):
        cases = [
            ('missing workspace', self.root / 'absent.json', self.manifest_a, self.facts_a,
             'WORKSPACE_UNREADABLE'),
            ('unparseable workspace', self.root / 'bad.json', self.manifest_a, self.facts_a,
             'WORKSPACE_UNREADABLE'),
            ('missing manifest', self.ws_a, self.root / 'absent.json', self.facts_a,
             'MANIFEST_UNREADABLE'),
            ('corrupt manifest', self.ws_a, self.root / 'corrupt-manifest.json', self.facts_a,
             'MANIFEST_UNREADABLE'),
            ('missing facts', self.ws_a, self.manifest_a, self.root / 'no-such-dir',
             'NO_PAGES'),
            ('corrupt facts', self.ws_a, self.manifest_a, CORRUPT_FACTS,
             'PAGE_DIGEST_MISMATCH'),
        ]
        (self.root / 'bad.json').write_bytes(b'{')
        (self.root / 'corrupt-manifest.json').write_bytes(canonical_bytes(self.data_a['manifest'])[:40])
        for name, ws, manifest, facts_dir, reason in cases:
            with self.subTest(name=name):
                proc = self.run_cli('--workspace', ws, '--manifest', manifest, '--facts', facts_dir)
                self.assertEqual((proc.returncode, proc.stderr), (1, b''))
                report = json.loads(proc.stdout)
                self.assertIs(report['ok'], False)
                self.assertEqual(report['reason'], reason)
                for check_name in crosscut.CROSS_CHECKS:
                    self.assertEqual(statuses(report)[check_name], 'NOT_CHECKED', check_name)
        # A workspace that parses but fails its own audit still gates dependents.
        document = json.loads(self.ws_a.read_bytes())
        document['payload_sha256'] = '0' * 64
        bad = self.root / 'checksum-fail.json'
        bad.write_bytes(canonical_bytes(document))
        proc = self.run_cli('--workspace', bad, '--manifest', self.manifest_a, '--facts', self.facts_a)
        self.assertEqual(proc.returncode, 1)
        report = json.loads(proc.stdout)
        self.assertEqual(reasons(report)['workspace_audit'], 'WORKSPACE_UNREADABLE')
        self.assertEqual(report['inputs']['workspace']['report']['failed_check'], 'payload_sha256')
        for check_name in crosscut.CROSS_CHECKS:
            self.assertEqual(statuses(report)[check_name], 'NOT_CHECKED')

    def test_read_only_under_held_workspace_lock(self):
        before = tree(self.root)
        held = FileWorkspace.open(self.ws_a.parent)
        try:
            proc = self.run_cli(*self.args())
            self.assertEqual(proc.returncode, 0)
        finally:
            held.close()
        self.assertEqual(tree(self.root), before)

    def test_dev_keyset_manifest_verified_with_0600_fixture(self):
        keyset = self.root / 'keyset.json'
        shutil.copyfile(KEYSET_FIXTURE, keyset)
        keyset.chmod(0o600)
        args = self.args(manifest=KEYSET_MANIFEST) + ('--keyset-file', keyset)
        proc = self.run_cli(*args)
        self.assertEqual((proc.returncode, proc.stderr), (0, b''))
        report = json.loads(proc.stdout)
        self.assertEqual(report['inputs']['manifest']['report']['signature'],
                         'VERIFIED_DEV_ONLY_INTEGRITY')
        self.assertEqual(statuses(report),
                         {name: 'MATCHED' for name in crosscut.CHECK_ORDER})
        # The committed fixture mode (0644) is refused by the existing loader.
        keyset.chmod(0o644)
        proc = self.run_cli(*args)
        self.assertEqual(proc.returncode, 1)
        report = json.loads(proc.stdout)
        self.assertEqual(reasons(report)['manifest_verify'], 'SIGNATURE_KEYSET_MODE')
        for check_name in crosscut.CROSS_CHECKS:
            self.assertEqual(statuses(report)[check_name], 'NOT_CHECKED')
        # Key material never reaches the report.
        fixture = json.loads(KEYSET_FIXTURE.read_bytes())
        for entry in fixture['keys']:
            self.assertNotIn(entry['key_hex'], proc.stdout.decode())

    def test_argument_errors_exit_two(self):
        self.assertEqual(self.run_cli().returncode, 2)
        self.assertEqual(self.run_cli('--workspace', self.ws_a).returncode, 2)
        proc = self.run_cli(*self.args(), '--key-file', 'x', '--keyset-file', 'y')
        self.assertEqual(proc.returncode, 2)


if __name__ == '__main__':
    unittest.main()
