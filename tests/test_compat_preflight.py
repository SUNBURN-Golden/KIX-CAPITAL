"""Offline READ_ONLY_FIXTURE checks; byte agreement never qualifies a producer."""
import copy
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from capital.compat_preflight import (
    CompatibilityError, MANIFEST_FORBIDDEN, PROFILE_FORBIDDEN, canonical_bytes,
    check_bundle, decode_input, git_blob, sha256,
)
from capital.store import canonical_bytes as legacy_bytes
from scripts.compat_preflight import CORPUS, MANIFEST, check_corpus


class BundleCopy:
    def __init__(self, directory):
        self.corpus = Path(directory) / 'compat'
        shutil.copytree(CORPUS, self.corpus)
        self.root = self.corpus / 'bundle'
        self.expected_path = self.corpus / 'expected.json'
        self.manifest = decode_input((self.root / MANIFEST).read_bytes())
        self.profile_path = self.root / f"sdk/compat/profiles/{self.manifest['profile_revision']}.profile.json"
        self.profile = decode_input(self.profile_path.read_bytes())

    def save(self):
        raw = canonical_bytes(self.manifest)
        (self.root / MANIFEST).write_bytes(raw)
        (self.root / (MANIFEST + '.sha256')).write_text(sha256(raw) + '\n')
        self.expected_path.write_bytes(canonical_bytes({
            'format': 'capital-compat-expected/1', 'manifest_sha256': sha256(raw), 'tuple': self.manifest,
        }))

    def save_profile(self, raw=None):
        raw = canonical_bytes(self.profile) if raw is None else raw
        self.profile_path.write_bytes(raw)
        self.manifest['profile_sha256'] = sha256(raw)
        self.save()

    def check(self):
        return check_bundle(self.root, MANIFEST, self.expected_path)


def leaf_locations(value, path='tuple'):
    if type(value) is dict:
        for key, item in value.items():
            yield from leaf_locations(item, path + '.' + key)
    elif type(value) is list:
        for index, item in enumerate(value):
            yield from leaf_locations(item, f'{path}[{index}]')
    else:
        yield path


def change_leaf(document, location):
    parts = [int(v) if v.isdigit() else v for v in re.findall(r'[^.\[\]]+', location)]
    target = document
    for part in parts[:-1]:
        target = target[part]
    value = target[parts[-1]]
    target[parts[-1]] = value + '-mismatch' if type(value) is str else not value


class EncodingTests(unittest.TestCase):
    def test_independent_encoding_vectors_and_legacy_divergence(self):
        corpus = decode_input((CORPUS / 'canonical.json').read_bytes())
        for case in corpus['cases']:
            with self.subTest(case=case['name']):
                raw = case['utf8'].encode('utf-8')
                self.assertEqual(canonical_bytes(decode_input(raw)), raw)
                self.assertEqual(sha256(raw), case['sha256'])
        value = {'é': '한😀', '__proto__': 'e\u0301'}
        self.assertNotEqual(canonical_bytes(value), legacy_bytes(value))
        self.assertEqual(canonical_bytes(value), b'{"__proto__":"e\xcc\x81","\xc3\xa9":"\xed\x95\x9c\xf0\x9f\x98\x80"}')
        self.assertEqual(canonical_bytes(decode_input(b'"\\ud800"')), b'"\\ud800"')

    def test_noncanonical_and_invalid_inputs(self):
        for raw in (
            b'{"a":1,"a":2}', b'{"a":{"x":1,"\\u0078":2}}',
            b'{"z":0,"a":0}', b'{"a": 1}', b' [0]', b'0\n', b'0 0',
            b'01', b'-0', b'1.0', b'1e0', b'NaN', b'Infinity',
            b'9007199254740992', b'-9007199254740992', b'"\\u00e9"',
            b'"\\/"', b'"\\u000a"', b'"\\uD800"', b'"\\ud83d\\ude00"',
            b'"\xff"', b'"\xed\xa0\x80"', b'\xef\xbb\xbf{}', b'{', b'',
            b'[' * 33 + b'0' + b']' * 33,
            b'[' * 2000 + b'0' + b']' * 2000,
        ):
            with self.subTest(raw=raw[:60]), self.assertRaises(CompatibilityError):
                decode_input(raw)
        for value in (1.0, float('inf'), 9007199254740992, {1: 'key'}, object()):
            with self.assertRaises(CompatibilityError):
                canonical_bytes(value)
        for raw in (b'null', b'true', b'false', b'[]', b'{}', '"é"'.encode()):
            self.assertEqual(canonical_bytes(decode_input(raw)), raw)


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bundle = BundleCopy(self.temp.name)

    def assert_error(self, code, location=None):
        report = self.bundle.check()
        self.assertFalse(report.matched, report.as_dict())
        errors = list(report.errors)
        self.assertTrue(any(e['code'] == code and (location is None or e['location'] == location)
                            for e in errors), errors)
        return report

    def test_offline_match_holds_semantics_and_adoption(self):
        with patch.object(socket, 'socket', side_effect=AssertionError('offline only')):
            report = self.bundle.check()
        self.assertTrue(report.matched, report.errors)
        self.assertEqual(report.as_dict()['byte_agreement'], 'MATCHED')
        self.assertEqual(report.as_dict()['semantic_consumption'], 'HOLD')
        self.assertEqual(report.as_dict()['adoption'], 'NOT_BOUND')
        self.assertIs(report.as_dict()['semantic_conformance'], False)
        self.assertEqual(report.as_dict()['label'], 'SIMULATED')
        self.assertTrue(check_corpus().matched)

    def test_each_independently_expected_tuple_leaf_has_a_mismatch(self):
        original = decode_input(self.bundle.expected_path.read_bytes())
        locations = decode_input((CORPUS / 'mismatches.json').read_bytes())['locations']
        self.assertEqual(set(locations), set(leaf_locations(original['tuple'])) | {'expected.manifest_sha256'})
        for location in locations:
            with self.subTest(location=location):
                changed = copy.deepcopy(original)
                if location == 'expected.manifest_sha256':
                    changed['manifest_sha256'] = '0' * 64
                    expected_code = 'manifest-digest-mismatch'
                else:
                    change_leaf(changed, location)
                    expected_code = 'tuple-mismatch'
                self.bundle.expected_path.write_bytes(canonical_bytes(changed))
                self.assert_error(expected_code, location)

    def test_exact_types_order_and_field_sets(self):
        original = decode_input(self.bundle.expected_path.read_bytes())
        for edit in (
            lambda d: d.pop('tuple'),
            lambda d: d['tuple']['producer'].pop('source_tree'),
            lambda d: d['tuple']['producer'].update(unknown='x'),
            lambda d: d['tuple']['vectors'].append(copy.deepcopy(d['tuple']['vectors'][0])),
            lambda d: d['tuple']['producer'].update(repository=True),
            lambda d: d.update(format='other'),
        ):
            changed = copy.deepcopy(original)
            edit(changed)
            self.bundle.expected_path.write_bytes(canonical_bytes(changed))
            self.assertFalse(self.bundle.check().matched)
        self.bundle.expected_path.write_bytes(b'{"format":1,"format":1}')
        self.assert_error('duplicate-key')
        self.assertFalse(check_bundle(self.bundle.root, MANIFEST, None).matched)

    def test_forbidden_manifest_and_profile_keys_with_refreshed_hashes(self):
        original_manifest = copy.deepcopy(self.bundle.manifest)
        original_profile = copy.deepcopy(self.bundle.profile)
        for key in MANIFEST_FORBIDDEN:
            with self.subTest(manifest=key):
                self.bundle.manifest = copy.deepcopy(original_manifest)
                self.bundle.manifest[key] = 'forbidden'
                self.bundle.save()
                self.assertFalse(self.bundle.check().matched)
                # Keep expectations valid so candidate validation reaches forbidden-field.
                expected = decode_input(self.bundle.expected_path.read_bytes())
                expected['tuple'].pop(key)
                self.bundle.expected_path.write_bytes(canonical_bytes(expected))
                self.assert_error('forbidden-field', 'manifest.' + key)
        self.bundle.manifest = original_manifest
        for key in PROFILE_FORBIDDEN:
            with self.subTest(profile=key):
                self.bundle.profile = copy.deepcopy(original_profile)
                self.bundle.profile[key] = 'forbidden'
                self.bundle.save_profile()
                self.assert_error('forbidden-field', 'profile.' + key)

    def test_duplicate_keys_are_rejected_in_manifest_profile_contract_and_metadata(self):
        for which in ('manifest', 'profile', 'contract_only', 'integration_gate', 'extension_profile', 'toolchain'):
            with self.subTest(which=which):
                # Fresh copy for each input; refresh every dependent digest.
                with tempfile.TemporaryDirectory() as tmp:
                    b = BundleCopy(tmp)
                    duplicate = b'{"a":1,"\\u0061":2}'
                    if which == 'manifest':
                        (b.root / MANIFEST).write_bytes(duplicate)
                        (b.root / (MANIFEST + '.sha256')).write_text(sha256(duplicate) + '\n')
                    elif which == 'profile':
                        b.save_profile(duplicate)
                    elif which == 'toolchain':
                        (b.root / 'toolchains.json').write_bytes(duplicate)
                    else:
                        refs = b.manifest['source_references'] if which == 'extension_profile' else b.manifest['contract']
                        ref = refs[which]
                        (b.root / ref['path']).write_bytes(duplicate)
                        ref.update(sha256=sha256(duplicate), gitBlob=git_blob(duplicate))
                        if which == 'contract_only':
                            b.profile['catalogue']['openapi_sha256'] = sha256(duplicate)
                        b.save_profile()
                    self.assertIn('duplicate-key', [e['code'] for e in b.check().errors])
                    if which == 'extension_profile':
                        self.assertEqual(b.check().errors, ({'code': 'duplicate-key', 'location': 'json'},))

    def test_file_hash_git_blob_sidecar_profile_and_toolchain_drift(self):
        paths = [p for p in (self.bundle.root).rglob('*') if p.is_file()]
        for path in paths:
            raw = path.read_bytes()
            with self.subTest(path=path.relative_to(self.bundle.root)):
                path.unlink()
                self.assertFalse(self.bundle.check().matched)
                path.write_bytes(raw)
                if path.relative_to(self.bundle.root).as_posix() != self.bundle.manifest['source_references']['fixture_profile']:
                    path.write_bytes(b'corrupt')
                    self.assertFalse(self.bundle.check().matched)
                    path.write_bytes(raw)
        self.bundle.manifest['contract']['integration_gate']['gitBlob'] = '0' * 40
        self.bundle.save()
        self.assert_error('git-blob-mismatch')

    def test_profile_catalogue_and_identity_binding(self):
        original = copy.deepcopy(self.bundle.profile)
        changes = (
            ('profile-binding', lambda p: p.update(profile_revision='different')),
            ('bootstrap-grants', lambda p: p.update(grants='semantic')),
            ('catalogue-binding', lambda p: p['catalogue'].update(openapi_path='other.json')),
            ('command-set-digest', lambda p: p['catalogue'].update(command_set_sha256='0'*64)),
            ('schema-digest', lambda p: p['catalogue']['schema_digests'].update(simulated_noop='0'*64)),
            ('schema-digest-map', lambda p: p['catalogue']['schema_digests'].update(extra='0'*64)),
            ('profile-binding', lambda p: p.update(vectors=[])),
            ('field-set', lambda p: p.update(extra=True)),
        )
        for code, change in changes:
            with self.subTest(code=code):
                self.bundle.profile = copy.deepcopy(original)
                change(self.bundle.profile)
                self.bundle.save_profile()
                self.assert_error(code)

    def test_vectors_duplicate_identities_and_noncanonical_bytes(self):
        self.bundle.manifest['vectors'].append(copy.deepcopy(self.bundle.manifest['vectors'][0]))
        self.bundle.profile['vectors'] = self.bundle.manifest['vectors']
        self.bundle.save_profile()
        self.assert_error('duplicate-vector')
        self.bundle.manifest['vectors'].pop()
        raw = b'{"label": "READ_ONLY_FIXTURE"}'
        ref = self.bundle.manifest['vectors'][0]
        (self.bundle.root / ref['path']).write_bytes(raw)
        ref['sha256'] = sha256(raw)
        self.bundle.save_profile()
        self.assert_error('non-canonical')

    def test_all_declared_and_derived_paths_are_confined(self):
        path_locations = [v for v in leaf_locations(self.bundle.manifest, '')
                          if v.endswith('.path') or v.endswith('.fixture_profile')]
        original = copy.deepcopy(self.bundle.manifest)
        for location in path_locations:
            for unsafe in ('../outside', '/tmp/outside', 'a/../../outside', 'a\\outside'):
                with self.subTest(location=location, unsafe=unsafe):
                    self.bundle.manifest = copy.deepcopy(original)
                    parts = [int(v) if v.isdigit() else v for v in re.findall(r'[^.\[\]]+', location)]
                    target = self.bundle.manifest
                    for part in parts[:-1]:
                        target = target[part]
                    target[parts[-1]] = unsafe
                    self.bundle.save()
                    self.assert_error('unsafe-path')
        self.bundle.manifest = original
        for bad in ('../manifest', '/tmp/manifest', 'a/../manifest'):
            self.assertFalse(check_bundle(self.bundle.root, bad, self.bundle.expected_path).matched)
        self.bundle.manifest['profile_revision'] = '../../escape'
        self.bundle.save()
        self.assert_error('profile-revision')

    def test_symlink_escape_and_nonregular_declared_and_derived_files(self):
        outside = Path(self.temp.name) / 'outside'
        outside.write_bytes(b'outside')
        for relative in (MANIFEST, MANIFEST + '.sha256', 'toolchains.json',
                         self.bundle.profile_path.relative_to(self.bundle.root).as_posix(),
                         self.bundle.manifest['generator']['path']):
            path = self.bundle.root / relative
            raw = path.read_bytes()
            with self.subTest(path=relative):
                path.unlink()
                path.symlink_to(outside)
                self.assert_error('unsafe-path')
                path.unlink()
                path.mkdir()
                self.assert_error('nonregular-file')
                path.rmdir()
                path.write_bytes(raw)

    def test_false_extension_profile_is_supported(self):
        self.bundle.manifest['source_references']['extension_profile'] = False
        self.bundle.save()
        self.assertTrue(self.bundle.check().matched)

    def test_cli_explicit_check_misuse_and_read_only_drift(self):
        cli = [sys.executable, 'scripts/compat_preflight.py']
        for args, status in ((['--check'], 0), ([], 2), (['--check', '--bundle', '.'], 2),
                             (['--bundle', str(self.bundle.root), '--manifest', MANIFEST,
                               '--expected', str(self.bundle.expected_path)], 0)):
            result = subprocess.run(cli + args, capture_output=True, text=True)
            self.assertEqual(result.returncode, status, result.stderr + result.stdout)
            if status == 0:
                self.assertEqual(json.loads(result.stdout)['semantic_consumption'], 'HOLD')
        path = self.bundle.root / self.bundle.manifest['sdk_output']['path']
        path.write_bytes(b'drift')
        before = {str(p): p.read_bytes() for p in self.bundle.corpus.rglob('*') if p.is_file()}
        self.assertFalse(check_corpus(self.bundle.corpus).matched)
        failed = subprocess.run(cli + ['--bundle', str(self.bundle.root), '--manifest', MANIFEST,
                                      '--expected', str(self.bundle.expected_path)], capture_output=True, text=True)
        self.assertEqual(failed.returncode, 1)
        self.assertEqual(json.loads(failed.stdout)['byte_agreement'], 'MISMATCH')
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.bundle.corpus.rglob('*') if p.is_file()})


if __name__ == '__main__':
    unittest.main()
