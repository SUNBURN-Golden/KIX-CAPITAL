"""Deterministic local zipapp: accessor, archive bytes, and smoke journey."""
import compileall
import hashlib
import importlib.util
import json
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from capital import __version__
from capital.readiness import source_integrity
from capital.resources import VENDOR, install_vendor_path, read_static, vendor_manifest, vendor_sys_path
from capital.service import CapitalService

REPO = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = _load('build_release').build
smoke = _load('smoke_release').smoke

_BANNED = ('tests/', 'docs/', '.git', 'node_modules', '.aiops', '.github')


class ResourceTests(unittest.TestCase):
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


class SmokeTests(unittest.TestCase):
    def test_smoke_journey_restart_and_version(self):
        with tempfile.TemporaryDirectory() as out, tempfile.TemporaryDirectory() as work:
            pyz = build(out, REPO)
            checks = smoke(pyz, work)
        self.assertEqual(checks, [
            'version-flag', 'state-version', 'static-index', 'journey-accepted',
            'source-integrity', 'restart-instance', 'restart-receipts', 'restart-closed'])


class ReleaseDocTests(unittest.TestCase):
    def test_release_note_template_and_package_job(self):
        notes = (REPO / 'docs' / 'RELEASES.md').read_text(encoding='utf-8')
        for heading in ('# Releases', '## 0.1.0', '## Template'):
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
