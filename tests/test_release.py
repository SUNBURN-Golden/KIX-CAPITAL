"""Deterministic local zipapp: accessor, archive bytes, and smoke journey."""
import compileall
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from capital import __version__
from capital.readiness import source_integrity
from capital.resources import VENDOR, install_vendor_path, read_note, read_static, vendor_manifest, vendor_sys_path
from capital.service import CapitalService

REPO = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = _load('build_release').build
smoke = _load('smoke_release').smoke

_BANNED = ('tests/', '.git', 'node_modules', '.aiops', '.github')


class ResourceTests(unittest.TestCase):
    def test_note_is_read_once_and_an_explicit_missing_parser_has_no_fallback(self):
        class Note:
            reads = 0

            def read_bytes(self):
                self.reads += 1
                return b'```capital-decision-v1\n{"schema":"capital-decision-v1"}\n```'

        note = Note()
        result = read_note(note, ledger=None)
        self.assertEqual(note.reads, 1)
        self.assertIsNone(result['block'])
        self.assertEqual(result['note_sha256'], hashlib.sha256(result['raw_bytes']).hexdigest())

    def test_package_modules_do_not_use_path_dunder_file(self):
        for path in sorted((REPO / 'capital').glob('*.py')):
            text = path.read_text(encoding='utf-8')
            self.assertIsNone(re.search(r'Path\s*\(\s*__file__\s*\)', text), path.name)

    def test_accessor_bytes_match_checkout_files(self):
        self.assertIsInstance(VENDOR, Path)
        for name in ('index.html', 'app.js', 'style.css'):
            self.assertEqual(read_static(name), (REPO / 'capital' / 'static' / name).read_bytes())
        disk = json.loads((REPO / 'capital' / 'vendor' / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(vendor_manifest(), disk)
        self.assertEqual(CapitalService().snapshot()['version'], __version__)

    def test_vendor_path_install_is_idempotent(self):
        install_vendor_path()
        before = list(sys.path)
        install_vendor_path()
        self.assertEqual(sys.path, before)
        for entry in vendor_sys_path():
            self.assertIn(entry, sys.path)
            self.assertFalse(entry.endswith('/') or entry.endswith('\\'))


class BuildTests(unittest.TestCase):
    def _expected_names(self, pinned):
        names = {'__main__.py', 'RELEASE-MANIFEST.json'}
        for path in (REPO / 'capital').glob('*.py'):
            names.add(f'capital/{path.name}')
        for path in (REPO / 'capital' / 'static').iterdir():
            if path.is_file() and path.suffix != '.pyc':
                names.add(f'capital/static/{path.name}')
        names.update(f'docs/decisions/{p.name}' for p in (REPO / 'docs' / 'decisions').iterdir()
                     if p.is_file() and p.name.endswith('.md'))
        names.update(('docs/CAP_COVERAGE.md', 'scripts/decision_ledger.py'))
        names.add('capital/vendor/manifest.json')
        for rel in pinned['files']:
            names.add(f'capital/vendor/{rel}')
        return names

    def test_two_builds_match_and_archive_is_pinned(self):
        self.assertTrue(compileall.compile_dir(str(REPO / 'capital'), quiet=1))
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            left = build(first, REPO)
            right = build(second, REPO)
            left_bytes = left.read_bytes()
            right_bytes = right.read_bytes()
            self.assertEqual(hashlib.sha256(left_bytes).hexdigest(), hashlib.sha256(right_bytes).hexdigest())
            self.assertEqual(left_bytes, right_bytes)
            self.assertTrue(left_bytes.startswith(b'#!/usr/bin/env python3\n'))
            self.assertEqual(left.name, f'capital-{__version__}.pyz')
            with zipfile.ZipFile(left) as archive:
                infos = archive.infolist()
                names = [info.filename for info in infos]
                self.assertEqual(names, sorted(names))
                self.assertTrue(all(not name.endswith('/') for name in names))
                for info in infos:
                    self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                    self.assertNotIn('__pycache__', info.filename)
                    self.assertFalse(info.filename.endswith('.pyc'))
                    self.assertFalse(any(info.filename.startswith(prefix) for prefix in _BANNED))
                pinned = json.loads((REPO / 'capital' / 'vendor' / 'manifest.json').read_text(encoding='utf-8'))
                self.assertEqual(set(names), self._expected_names(pinned))
                self.assertIn('capital/vendor/credit_advance_f04/test_mock_credit.py', names)
                for rel, expected in pinned['files'].items():
                    payload = archive.read(f'capital/vendor/{rel}')
                    self.assertEqual(payload, (REPO / 'capital' / 'vendor' / rel).read_bytes())
                    self.assertEqual(hashlib.sha256(payload).hexdigest(), expected)
                raw = archive.read('RELEASE-MANIFEST.json')
                self.assertTrue(raw.endswith(b'\n'))
                self.assertNotIn(b'\r', raw)
                manifest = json.loads(raw.decode('utf-8'))
                self.assertEqual(raw.decode('utf-8'), json.dumps(manifest, sort_keys=True, indent=2) + '\n')
                self.assertEqual(set(manifest['files']), set(names) - {'RELEASE-MANIFEST.json'})
                self.assertNotIn('RELEASE-MANIFEST.json', manifest['files'])
                for name, expected in manifest['files'].items():
                    self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), expected)
                    if name.startswith(('docs/', 'scripts/')):
                        self.assertEqual(archive.read(name), (REPO / name).read_bytes())
                self.assertEqual(manifest['format'], 'KIX_CAPITAL_RELEASE_V1')
                self.assertEqual(manifest['name'], 'kix-capital')
                self.assertEqual(manifest['version'], __version__)
                self.assertEqual(manifest['protocol_commit'], pinned['commit'])
                self.assertIs(manifest['signed'], False)
                self.assertIs(manifest['published'], False)
                self.assertEqual(manifest['mode'], 'LOCAL_SIMULATION_ARTIFACT')
                report = source_integrity(zipfile.Path(archive) / 'capital/vendor', pinned)
                self.assertTrue(report['all_matched'])
                self.assertEqual(len(report['files']), len(pinned['files']))

    def test_package_json_version_matches_single_source(self):
        package = json.loads((REPO / 'package.json').read_text(encoding='utf-8'))
        self.assertEqual(package['version'], __version__)

    def test_only_authorized_inputs_are_added_and_note_bytes_change_the_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'source'
            shutil.copytree(REPO / 'capital', root / 'capital',
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            shutil.copytree(REPO / 'docs' / 'decisions', root / 'docs' / 'decisions')
            shutil.copyfile(REPO / 'docs' / 'CAP_COVERAGE.md', root / 'docs' / 'CAP_COVERAGE.md')
            (root / 'scripts').mkdir()
            shutil.copyfile(REPO / 'scripts' / 'decision_ledger.py', root / 'scripts' / 'decision_ledger.py')
            for rel in ('docs/decisions/nested/EXCLUDED.md', 'docs/decisions/EXCLUDED.txt',
                        'docs/EXCLUDED.md', 'scripts/excluded.py', 'tests/test_excluded.py',
                        'keysets/dev.json', 'var/workspace.json', '.git/config', 'build/excluded'):
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'SIMULATED exclusion fixture')
            first = build(Path(tmp) / 'first', root)
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(set(archive.namelist()), self._expected_names(vendor_manifest()))
            note = root / 'docs' / 'decisions' / 'CAPITAL_FINANCIAL_TERMS.md'
            note.write_bytes(note.read_bytes() + b'\n<!-- SIMULATED byte-change fixture -->\n')
            second = build(Path(tmp) / 'second', root)
            self.assertNotEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(second) as archive:
                raw = archive.read('docs/decisions/CAPITAL_FINANCIAL_TERMS.md')
                self.assertEqual(raw, note.read_bytes())
                manifest = json.loads(archive.read('RELEASE-MANIFEST.json'))
                self.assertEqual(manifest['files']['docs/decisions/CAPITAL_FINANCIAL_TERMS.md'],
                                 hashlib.sha256(raw).hexdigest())


class PackagedNoteTests(unittest.TestCase):
    """Damaged artifacts are synthetic fixtures; runtime must fail closed."""
    TERMS = 'docs/decisions/CAPITAL_FINANCIAL_TERMS.md'
    POLICY = 'docs/decisions/CAPITAL_SETTLEMENT_POLICY.md'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pyz = build(self.root / 'build', REPO)
        self.cwd = self.root / 'unrelated'
        self.cwd.mkdir()

    def probe(self, pyz=None, **overrides):
        code = '''import json, sys
sys.path.insert(0, sys.argv[1])
from capital.terms import DecisionNoteTermsPolicy
from capital.policy import DecisionNoteSettlementPolicy
from capital.service import CapitalService
options = json.loads(sys.argv[2])
ports = {}
if 'terms' in options:
    ports['terms'] = DecisionNoteTermsPolicy(options['terms'])
if 'policy' in options:
    ports['policy'] = DecisionNoteSettlementPolicy(options['policy'])
service = CapitalService(**ports)
print(json.dumps({'terms': service.terms_status(), 'policy': service.policy_status(),
    'decisions': service.decisions(), 'state_terms': service.snapshot()['terms'],
    'underwriting': service.underwrite('sim-committed', service.instance_id, 'organizer', amount=60000)}))
'''
        env = dict(os.environ)
        env.pop('PYTHONPATH', None)
        proc = subprocess.run([sys.executable, '-B', '-c', code, str(pyz or self.pyz),
                               json.dumps(overrides)], cwd=self.cwd, env=env,
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def damaged(self, changes):
        target = self.root / 'damaged.pyz'
        with zipfile.ZipFile(self.pyz) as original, zipfile.ZipFile(target, 'w') as archive:
            for name in original.namelist():
                raw = changes.get(name, original.read(name))
                if raw is not None:
                    archive.writestr(name, raw)
        return target

    def assert_provenance(self, body, source, raw):
        self.assertEqual(body['notes_source'], source)
        self.assertEqual(body['note_sha256'], None if raw is None else hashlib.sha256(raw).hexdigest())

    def test_explicit_overrides_win_including_missing_and_unusable_files(self):
        overrides = {}
        for key, name in (('terms', self.TERMS), ('policy', self.POLICY)):
            path = self.root / f'{key}.md'
            raw = (REPO / name).read_bytes() + b'\n<!-- SIMULATED override fixture -->\n'
            path.write_bytes(raw)
            overrides[key] = str(path)
        body = self.probe(**overrides)
        self.assertEqual(body['terms']['status'], 'BOUND')
        self.assertEqual(body['policy']['outcome'], 'DECIDED')
        for key in ('terms', 'state_terms', 'underwriting'):
            self.assert_provenance(body[key], 'OVERRIDE_FILE', Path(overrides['terms']).read_bytes())
        self.assert_provenance(body['policy'], 'OVERRIDE_FILE', Path(overrides['policy']).read_bytes())
        self.assert_provenance(body['decisions'], 'BUNDLED_IN_ARTIFACT', (REPO / self.TERMS).read_bytes())
        for raw in (None, b'\xff', b'```capital-decision-v1\n{"schema":"capital-decision-v1","entries":{}}\n```'):
            with self.subTest(raw=raw):
                for value in overrides.values():
                    path = Path(value)
                    if raw is None:
                        path.unlink()
                    else:
                        path.write_bytes(raw)
                body = self.probe(**overrides)
                self.assertEqual(body['terms']['status'], 'NOT_BOUND')
                self.assertEqual(body['policy']['outcome'], 'NOT_BOUND')
                self.assertEqual(body['underwriting']['status'], 'NOT_BOUND')
                for key in ('terms', 'state_terms', 'underwriting', 'policy'):
                    self.assert_provenance(body[key], 'NONE' if raw is None else 'OVERRIDE_FILE', raw)

    def test_missing_and_malformed_bundled_inputs_never_fall_back_to_checkout(self):
        valid = (REPO / self.TERMS).read_bytes()
        for raw in (None, b'\xff', b'# no block',
                    b'```capital-decision-v1\n{"schema":"capital-decision-v1","schema":"x"}\n```',
                    valid + valid, b'```capital-decision-v1\n[]\n```'):
            with self.subTest(raw=None if raw is None else raw[:70]):
                body = self.probe(self.damaged({self.TERMS: raw, self.POLICY: raw}))
                self.assertEqual(body['terms']['status'], 'NOT_BOUND')
                self.assertEqual(body['policy']['outcome'], 'NOT_BOUND')
                self.assertEqual(body['underwriting']['status'], 'NOT_BOUND')
                self.assertEqual(body['decisions']['status'], 'NOT_BOUND')
                for key in ('terms', 'state_terms', 'underwriting', 'policy', 'decisions'):
                    self.assert_provenance(body[key], 'NONE' if raw is None else 'BUNDLED_IN_ARTIFACT', raw)
                rows = {row['note']: row for row in body['decisions']['rows']}
                self.assertTrue(rows)  # A broken body anchor does not discard available rows.
                row = rows[self.TERMS]
                self.assertEqual(row['status'], 'PENDING' if raw is None else 'INVALID')
                self.assert_provenance(row, 'NONE' if raw is None else 'BUNDLED_IN_ARTIFACT', raw)

    def test_missing_or_broken_bundled_ledger_and_coverage_fail_closed(self):
        for changes in ({'scripts/decision_ledger.py': None},
                        {'scripts/decision_ledger.py': b'not valid python !'},
                        {'docs/CAP_COVERAGE.md': b'\xff'}):
            with self.subTest(changes=changes):
                body = self.probe(self.damaged(changes))
                self.assertEqual(body['decisions']['status'], 'NOT_BOUND')
                self.assertEqual(body['decisions']['rows'], [])
                if 'scripts/decision_ledger.py' in changes:
                    self.assertEqual(body['terms']['status'], 'NOT_BOUND')
                    self.assertEqual(body['policy']['outcome'], 'NOT_BOUND')


class SmokeTests(unittest.TestCase):
    def test_smoke_journey_restart_and_version(self):
        with tempfile.TemporaryDirectory() as out, tempfile.TemporaryDirectory() as work:
            pyz = build(out, REPO)
            checks = smoke(pyz, work)
        self.assertEqual(checks, [
            'version-flag', 'state-version', 'static-index', 'bundled-policy-provenance',
            'bundled-accrual', 'restart-overlay-provenance', 'journey-accepted',
            'source-integrity', 'restart-instance', 'restart-receipts', 'restart-closed'])


class ReleaseDocTests(unittest.TestCase):
    def test_release_note_template_and_package_job(self):
        notes = (REPO / 'docs' / 'RELEASES.md').read_text(encoding='utf-8')
        for heading in ('# Releases', '## 0.2.0', '## 0.1.0', '## Template'):
            self.assertIn(heading, notes)
        for token in ('LOCAL_SIMULATION_ARTIFACT', 'signed', 'published', 'capital/__init__.py', 'PyPI'):
            self.assertIn(token, notes)
        self.assertIn('dist/', (REPO / '.gitignore').read_text(encoding='utf-8'))
        workflow = (REPO / '.github' / 'workflows' / 'verify.yml').read_text(encoding='utf-8')
        package = workflow.split('\n  package:\n', 1)[1]
        for step in (
            'python3 scripts/build_release.py --out dist',
            'python3 scripts/build_release.py --out dist2',
            'cmp dist/capital-*.pyz dist2/capital-*.pyz',
            'python3 scripts/smoke_release.py dist/capital-*.pyz',
        ):
            self.assertIn(step, package)
        self.assertNotIn('upload-artifact', package)
        self.assertNotIn('twine', package.lower())
        self.assertNotIn('pypi', package.lower())


if __name__ == '__main__':
    unittest.main()
