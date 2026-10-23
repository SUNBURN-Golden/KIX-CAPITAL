"""Committed closeout digest: tests/vectors/closeout_digest.json.

The digest is SIMULATED and supplies INPUT_VECTOR_CANDIDATE material for the
FINANCE_PENDING_NODES candidate fin-finance-closeout. It is not SEMANTIC_CONFORMANCE
and it completes no upstream node. Expected values below are written by hand from
the acceptance ladder and the decision note, so the generator is not its own oracle.
The evidence the generator reads is also built by hand here, never by running the
ladder, so these tests need no browser and no build.
"""
import contextlib
import copy
import importlib.util
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from capital import __version__ as CAPITAL_VERSION

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / 'tests' / 'vectors' / 'closeout_digest.json'
VECTORS = ROOT / 'tests' / 'vectors' / 'finance_vectors.json'
GOLDEN = ROOT / 'tests' / 'golden' / 'demo.json'
SCRIPT = ROOT / 'scripts' / 'closeout_digest.py'
VENDOR = ROOT / 'capital' / 'vendor' / 'manifest.json'
README = ROOT / 'README.md'
VALIDATION = ROOT / 'docs' / 'VALIDATION.md'
HANDBOOK = ROOT / 'docs' / 'OPERATOR_HANDBOOK_KO.md'
BINDING = ROOT / 'docs' / 'decisions' / 'CAPITAL_UPSTREAM_BINDING.md'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = _load('closeout_digest', SCRIPT)
acceptance_ladder = _load('acceptance_for_closeout', ROOT / 'scripts' / 'acceptance.py')

# Written by hand: the acceptance ladder and the exact command texts per stage.
STAGES = (
    ('unit', ['python3 -m unittest discover -s tests -v',
              'python3 scripts/decision_bindings.py --check']),
    ('storage-conformance', ['python3 -m unittest discover -s tests -p test_storage_conformance.py -v',
                             'python3 -m unittest tests.test_crash_replay -v']),
    ('pinned-vendor', ['python3 -m unittest discover -s capital/vendor/credit_advance_f04 -p test_mock_credit.py -v']),
    ('upstream-claims', ['python3 scripts/upstream_claims_check.py --execute',
                         'python3 scripts/agent_claims_check.py --execute',
                         'python3 scripts/read_model_claims_check.py --execute',
                         'python3 scripts/ce1_claims_check.py --execute',
                         'python3 scripts/adapter_identity_claims_check.py --execute']),
    ('node-check', ['node --check capital/static/app.js']),
    ('browser', ['npm run test:browser']),
    ('packaged-smoke', ['python3 scripts/build_release.py --out build/acceptance-dist',
                        'python3 scripts/smoke_release.py <built-zipapp>']),
    ('seeded-demo', ['python3 scripts/seed_demo.py']),
    ('integrated-journeys', ['python3 scripts/sim_journeys.py']),
)
STRIP_KEYS = [
    'head_sha', 'instance_id', 'created_at', 'saved_at', 'timestamp', 'timestamps', 'recorded_at',
    'duration_s', 'wall_time_s', 'elapsed_s', 'tools', 'tool_versions', 'out_dir', 'output_dir',
    'workspace_dir', 'host', 'cwd', 'path',
]
NON_CLAIMS = [
    'not SEMANTIC_CONFORMANCE',
    'completes no upstream node — fin-finance-closeout stays a PENDING candidate and the denominator stays eight',
    "self-asserted evidence produced by this repo's own tooling; not independent review, not CI, not human acceptance",
    'claims nothing about which commit or toolchain produced it — head_sha and tool versions are stripped by '
    'design; actual run SHAs stay in docs/VALIDATION.md prose',
]
FAKE_HEAD = '0123456789abcdef0123456789abcdef01234567'
FAKE_SMOKE_SHA = 'ab' * 32
SHA40 = re.compile(r'(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])')
UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
TIMESTAMP = re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}')
HOST_PATH = re.compile(r'/(?:home|tmp|workspace|Users|var|root)/')


def vendor_manifest():
    return json.loads(VENDOR.read_text(encoding='utf-8'))


def golden():
    return json.loads(GOLDEN.read_text(encoding='utf-8'))


def synthetic_evidence():
    """Hand-built evidence in the shape of scripts/acceptance.py, with every per-run field filled in."""
    pinned = vendor_manifest()
    recorded = golden()
    stages = []
    for ordinal, (stage_id, commands) in enumerate(STAGES):
        records = []
        for text in commands:
            argv = text.split(' ')
            argv[0] = '/usr/local/bin/python3.13' if argv[0] == 'python3' else argv[0]
            if argv[-1] == '<built-zipapp>':
                argv[-1] = f'build/acceptance-dist/capital-{CAPITAL_VERSION}.pyz'
            tail = f'ok at 2026-10-17T09:30:00Z in /home/builder/{stage_id}'
            if 'build_release.py' in text:
                tail = f'build/acceptance-dist/capital-{CAPITAL_VERSION}.pyz {FAKE_SMOKE_SHA}'
            records.append({'argv': argv, 'exit_code': 0, 'test_count': None, 'output_tail': tail})
        stages.append({
            'id': stage_id, 'status': 'passed', 'injected': False, 'exit_code': 0,
            'test_count': {'ran': 10 + ordinal, 'passed': 10 + ordinal, 'failed': 0} if stage_id != 'node-check' else None,
            'commands': records, 'duration_s': 1.5 + ordinal, 'timestamp': '2026-10-17T09:30:00Z',
        })
    return {
        'format': 'KIX_CAPITAL_ACCEPTANCE_EVIDENCE_V1', 'label': 'SIMULATED', 'funds_executed': False,
        'note': 'Local simulation ladder.', 'head_sha': FAKE_HEAD, 'head_error': None,
        'tool_versions': {'python': '3.13.99', 'node': 'v99.1.2', 'npm': '99.0.1', 'playwright': '9.9.9',
                          'capital': CAPITAL_VERSION},
        'vendor_hashes': {'commit': pinned['commit'], 'hashes': dict(pinned['files']), 'verified': True},
        'golden_digests': {
            'status': 'recorded', 'state_digest': recorded['state_digest'],
            'projection_totals': recorded['projection_totals'], 'content_digest': recorded['content_digest'],
        },
        'stages': stages, 'ok': True,
    }


def run(*argv):
    """Call script.main with its status lines swallowed; return (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = script.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class Workdir:
    """Temp directory with an evidence file, a digest target and a copy of the finance pack."""

    def __init__(self, test):
        self._tmp = tempfile.TemporaryDirectory()
        test.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.evidence = self.root / 'evidence.json'
        self.artifact = self.root / 'out' / 'closeout_digest.json'
        self.vectors = self.root / 'finance_vectors.json'

    def put_evidence(self, evidence):
        self.evidence.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding='utf-8')

    def args(self, *mode):
        return (*mode, '--evidence', str(self.evidence), '--file', str(self.artifact), '--vectors', str(self.vectors))

    def write(self, evidence=None):
        self.put_evidence(synthetic_evidence() if evidence is None else evidence)
        code, _, err = run(*self.args('--write'))
        assert code == 0, err
        return self.artifact.read_bytes()

    def embed(self, document=None):
        """A finance pack copy whose closeout_digest group is the given document (default: this digest)."""
        pack = json.loads(VECTORS.read_text(encoding='ascii'))
        pack['groups']['closeout_digest'] = json.loads(self.artifact.read_bytes()) if document is None else document
        self.vectors.write_bytes(script.dump(pack))


class StageTableTests(unittest.TestCase):
    """The digest built from hand-written evidence has exactly the hand-written shape."""

    def setUp(self):
        self.work = Workdir(self)
        self.raw = self.work.write()
        self.digest = json.loads(self.raw)

    def test_the_ladder_is_the_nine_stages_in_order(self):
        self.assertEqual(tuple(acceptance_ladder.REQUIRED_STAGES), tuple(stage for stage, _ in STAGES))
        self.assertEqual(len(STAGES), 9)
        self.assertEqual([row['stage_id'] for row in self.digest['stages']], [stage for stage, _ in STAGES])

    def test_every_stage_row_is_a_simulated_clean_pass(self):
        for row, (stage_id, commands) in zip(self.digest['stages'], STAGES):
            with self.subTest(stage=stage_id):
                self.assertEqual(sorted(row), ['command', 'expected_exit', 'funds_executed', 'label',
                                               'stage_id', 'status', 'test_count'])
                self.assertEqual(row['command'], commands)
                self.assertEqual(row['status'], 'passed')
                self.assertEqual(row['expected_exit'], 0)
                self.assertEqual(row['label'], 'SIMULATED')
                self.assertIs(row['funds_executed'], False)

    def test_test_counts_keep_the_parser_intentional_null(self):
        counts = {row['stage_id']: row['test_count'] for row in self.digest['stages']}
        self.assertIsNone(counts['node-check'])
        self.assertEqual(counts['unit'], {'ran': 10, 'passed': 10, 'failed': 0})
        self.assertEqual(counts['seeded-demo'], {'ran': 17, 'passed': 17, 'failed': 0})

    def test_top_level_labels_and_non_claims(self):
        digest = self.digest
        self.assertEqual(digest['format'], 'KIX_CAPITAL_CLOSEOUT_DIGEST_V1')
        self.assertEqual(digest['label'], 'INPUT_VECTOR_CANDIDATE')
        self.assertEqual(digest['data_label'], 'SIMULATED')
        self.assertEqual(digest['candidate'], 'fin-finance-closeout')
        self.assertIs(digest['simulated'], True)
        self.assertIs(digest['provisional'], True)
        self.assertIs(digest['semantic_conformance'], False)
        self.assertEqual(digest['upstream_nodes_completed'], [])
        self.assertIs(digest['funds_executed'], False)
        self.assertEqual(digest['human_product_acceptance'], 'NOT_PART_OF_LADDER')
        self.assertEqual(digest['production'], 'NOT_AUTHORIZED')
        self.assertIs(digest['ok'], True)
        self.assertEqual(digest['evidence_format'], 'KIX_CAPITAL_ACCEPTANCE_EVIDENCE_V1')
        self.assertEqual(digest['non_claims'], NON_CLAIMS)
        self.assertEqual(digest['stripped_keys'], STRIP_KEYS)
        self.assertIn('not SEMANTIC_CONFORMANCE', digest['note'])
        self.assertIn('completes no upstream node', digest['note'])

    def test_covered_digests_and_pins(self):
        recorded = golden()
        self.assertEqual(self.digest['golden'], {
            'status': 'recorded', 'state_digest': recorded['state_digest'],
            'content_digest': recorded['content_digest'], 'debit': 385000, 'credit': 385000,
        })
        pinned = vendor_manifest()
        self.assertEqual(pinned['commit'], '7481b0e16ce9b903abbffa62249bb91cd9e63cfe')
        self.assertEqual(self.digest['vendor']['commit'], '7481b0e16ce9b903abbffa62249bb91cd9e63cfe')
        self.assertIs(self.digest['vendor']['verified'], True)
        self.assertEqual(self.digest['vendor']['files'], {name: True for name in sorted(pinned['files'])})
        self.assertEqual(len(self.digest['vendor']['files']), 5)
        self.assertEqual(self.digest['packaged'], {'sha256': FAKE_SMOKE_SHA, 'artifact_kind': 'LOCAL_SIMULATION_ARTIFACT'})

    def test_a_vendor_file_that_does_not_match_its_pin_is_refused(self):
        raw = self.raw
        for name in sorted(vendor_manifest()['files']):
            with self.subTest(file=name):
                evidence = synthetic_evidence()
                evidence['vendor_hashes']['hashes'][name] = '0' * 64
                self.assertIs(evidence['vendor_hashes']['verified'], True)
                self.work.put_evidence(evidence)
                code, _, err = run(*self.work.args('--write'))
                self.assertEqual(code, 1)
                self.assertIn(name, err)
                self.assertEqual(self.work.artifact.read_bytes(), raw)
                self.work.artifact.unlink()
                self.assertEqual(run(*self.work.args('--write'))[0], 1)
                self.assertFalse(self.work.artifact.exists())
                self.work.artifact.write_bytes(raw)


class DeterminismTests(unittest.TestCase):
    def setUp(self):
        self.work = Workdir(self)

    def test_two_runs_are_byte_identical_and_canonical(self):
        first = self.work.write()
        self.work.artifact.unlink()
        second = self.work.write()
        self.assertEqual(first, second)
        self.assertTrue(first.endswith(b'\n') and not first.endswith(b'\n\n'))
        first.decode('ascii')
        self.assertEqual(first, (json.dumps(json.loads(first), sort_keys=True, separators=(',', ':'),
                                            ensure_ascii=True) + '\n').encode('ascii'))

    def test_key_order_of_the_evidence_does_not_change_the_bytes(self):
        base = self.work.write()
        evidence = synthetic_evidence()
        reordered = {key: evidence[key] for key in reversed(list(evidence))}
        reordered['stages'] = [{key: stage[key] for key in reversed(list(stage))} for stage in evidence['stages']]
        self.assertEqual(self.work.write(reordered), base)

    def test_per_run_fields_do_not_change_the_bytes(self):
        base = self.work.write()
        evidence = synthetic_evidence()
        evidence['head_sha'] = 'f' * 40
        evidence['head_error'] = 'detached'
        evidence['tool_versions'] = {'python': '2.7.0', 'node': 'v1.0.0', 'npm': '1.0.0', 'playwright': '0.0.1',
                                     'capital': '9.9.9'}
        for stage in evidence['stages']:
            stage['duration_s'] = 987.6
            stage['timestamp'] = '2031-01-01T00:00:00Z'
            for record in stage['commands']:
                record['output_tail'] = record['output_tail'].replace('09:30', '23:59').replace('/home/builder', '/srv/x')
        evidence['stages'][0]['commands'][0]['argv'][0] = '/opt/other/bin/python3'
        self.assertEqual(self.work.write(evidence), base)

    def test_a_changed_covered_field_changes_the_bytes(self):
        base = self.work.write()
        for what, mutate in {
            'a test count': lambda e: e['stages'][0]['test_count'].update(ran=11),
            'the packaged sha256': lambda e: e['stages'][6]['commands'][0].update(
                output_tail=f'build/acceptance-dist/capital-0.pyz {"cd" * 32}'),
            'a golden digest': lambda e: e['golden_digests'].update(state_digest='1' * 64),
            'the debit total': lambda e: e['golden_digests']['projection_totals'].update(debit=1),
        }.items():
            with self.subTest(change=what):
                evidence = synthetic_evidence()
                mutate(evidence)
                self.assertNotEqual(self.work.write(evidence), base)

    def test_injected_strip_keys_are_absent(self):
        base = self.work.write()
        evidence = synthetic_evidence()
        evidence['head_sha'] = FAKE_HEAD
        evidence['golden_digests']['projection_totals']['instance_id'] = 'abc'
        evidence['golden_digests']['host'] = 'build-box'
        evidence['vendor_hashes']['path'] = '/home/x'
        evidence['stages'][0]['cwd'] = '/home/x'
        evidence['stages'][0]['test_count']['elapsed_s'] = 4
        raw = self.work.write(evidence)
        self.assertEqual(raw, base)
        self.assertNotIn(FAKE_HEAD.encode(), raw)

    def test_the_defensive_walk_deletes_a_strip_key_at_every_depth(self):
        keys = set(STRIP_KEYS)
        value = {'a': {'head_sha': 1, 'b': [{'path': 2, 'keep': 3}, {'tools': {'x': 1}}]}, 'timestamp': 4, 'ok': True}
        self.assertEqual(script.strip_keys_at_every_depth(value, keys), {'a': {'b': [{'keep': 3}, {}]}, 'ok': True})

    def test_the_write_creates_the_parent_directory_and_check_evidence_passes(self):
        self.work.write()
        code, out, err = run(*self.work.args('--check-evidence'))
        self.assertEqual((code, err), (0, ''))
        self.assertIn('matches the evidence', out)


class WriteGateTests(unittest.TestCase):
    """CAPITAL-CLOSEOUT-REGEN-V1: only ok:true SIMULATED evidence with every stage passed may be written."""

    def setUp(self):
        self.work = Workdir(self)

    def refuses(self, mutate, fragment):
        evidence = synthetic_evidence()
        mutate(evidence)
        self.work.put_evidence(evidence)
        code, _, err = run(*self.work.args('--write'))
        self.assertEqual(code, 1, err)
        self.assertIn(fragment, err)
        self.assertFalse(self.work.artifact.exists(), 'a refused write must leave no artifact')

    def test_ok_false_is_refused(self):
        self.refuses(lambda e: e.update(ok=False), 'ok is not true')

    def test_a_non_simulated_label_is_refused(self):
        self.refuses(lambda e: e.update(label='REAL'), 'SIMULATED')

    def test_funds_executed_true_is_refused(self):
        self.refuses(lambda e: e.update(funds_executed=True), 'funds_executed')

    def test_a_failed_stage_is_refused(self):
        def mutate(evidence):
            evidence['stages'][5].update(status='failed', exit_code=1)
        self.refuses(mutate, 'browser did not pass')

    def test_an_unrun_stage_is_refused(self):
        def mutate(evidence):
            evidence['stages'][2].update(status='unrun', exit_code=None, commands=[])
        self.refuses(mutate, 'pinned-vendor did not pass')

    def test_a_missing_stage_is_refused(self):
        self.refuses(lambda e: e['stages'].pop(), 'lacks stage integrated-journeys')

    def test_an_extra_stage_is_refused(self):
        def mutate(evidence):
            evidence['stages'].append({**copy.deepcopy(evidence['stages'][0]), 'id': 'closeout'})
        self.refuses(mutate, 'exactly the ladder')

    def test_a_wrong_evidence_format_is_refused(self):
        self.refuses(lambda e: e.update(format='OTHER'), 'evidence format')

    def test_an_injected_stage_is_refused(self):
        self.refuses(lambda e: e['stages'][0].update(injected=True), 'unit exit_code or injected')

    def test_a_build_that_prints_no_sha256_is_refused(self):
        def mutate(evidence):
            evidence['stages'][6]['commands'][0]['output_tail'] = 'build/acceptance-dist/capital.pyz'
        self.refuses(mutate, 'sha256')

    def test_unrecorded_golden_digests_are_refused(self):
        self.refuses(lambda e: e['golden_digests'].update(status='unrun'), 'golden_digests')

    def test_unverified_vendor_evidence_is_refused(self):
        self.refuses(lambda e: e['vendor_hashes'].update(verified=False), 'vendor_hashes is not verified')

    def test_missing_or_unreadable_evidence_exits_one(self):
        code, _, err = run(*self.work.args('--write'))
        self.assertEqual(code, 1)
        self.assertIn('evidence unreadable', err)
        self.work.evidence.write_text('{', encoding='utf-8')
        self.assertEqual(run(*self.work.args('--write'))[0], 1)
        self.assertFalse(self.work.artifact.exists())

    def test_a_refused_write_leaves_an_existing_artifact_alone(self):
        raw = self.work.write()
        evidence = synthetic_evidence()
        evidence['ok'] = False
        self.work.put_evidence(evidence)
        self.assertEqual(run(*self.work.args('--write'))[0], 1)
        self.assertEqual(self.work.artifact.read_bytes(), raw)


class CheckEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.work = Workdir(self)
        self.work.write()

    def test_a_covered_drift_exits_one_and_names_the_path(self):
        evidence = synthetic_evidence()
        evidence['stages'][0]['test_count']['ran'] = 99
        self.work.put_evidence(evidence)
        code, _, err = run(*self.work.args('--check-evidence'))
        self.assertEqual(code, 1)
        self.assertIn('closeout digest drift: $.stages[0].test_count.ran', err)

    def test_a_per_run_only_difference_is_not_drift(self):
        evidence = synthetic_evidence()
        evidence['head_sha'] = 'e' * 40
        evidence['tool_versions']['node'] = 'v1.1.1'
        self.work.put_evidence(evidence)
        self.assertEqual(run(*self.work.args('--check-evidence'))[0], 0)

    def test_missing_evidence_missing_artifact_and_failed_evidence_exit_one(self):
        self.work.evidence.unlink()
        self.assertEqual(run(*self.work.args('--check-evidence'))[0], 1)
        self.work.put_evidence(synthetic_evidence())
        self.work.artifact.unlink()
        code, _, err = run(*self.work.args('--check-evidence'))
        self.assertEqual(code, 1)
        self.assertIn('missing', err)
        self.work.write()
        evidence = synthetic_evidence()
        evidence['ok'] = False
        self.work.put_evidence(evidence)
        self.assertEqual(run(*self.work.args('--check-evidence'))[0], 1)


class CheckTests(unittest.TestCase):
    """--check on a temp digest and a temp finance pack: each mutation must fail it."""

    def setUp(self):
        self.work = Workdir(self)
        self.raw = self.work.write()
        self.work.embed()

    def check(self):
        return run('--check', '--file', str(self.work.artifact), '--vectors', str(self.work.vectors))

    def test_a_clean_pair_passes_and_writes_nothing(self):
        before = (self.work.artifact.read_bytes(), self.work.vectors.read_bytes(), sorted(self.work.root.iterdir()))
        code, out, err = self.check()
        self.assertEqual((code, err), (0, ''))
        self.assertIn('closeout digest ok', out)
        self.assertEqual(before, (self.work.artifact.read_bytes(), self.work.vectors.read_bytes(),
                                  sorted(self.work.root.iterdir())))

    def test_a_removed_artifact_fails(self):
        self.work.artifact.unlink()
        code, _, err = self.check()
        self.assertEqual(code, 1)
        self.assertIn('missing', err)

    def test_an_edited_stage_status_fails(self):
        for stage_id in ('unit', 'browser', 'seeded-demo'):
            with self.subTest(stage=stage_id):
                document = json.loads(self.raw)
                row = next(item for item in document['stages'] if item['stage_id'] == stage_id)
                row['status'] = 'failed'
                self.work.artifact.write_bytes(script.dump(document))
                self.work.embed(document)
                code, _, err = self.check()
                self.assertEqual(code, 1)
                self.assertIn(f'stage {stage_id} is not a clean SIMULATED pass', err)

    def test_a_tampered_embedded_copy_fails_and_names_the_path(self):
        pack = json.loads(self.work.vectors.read_bytes())
        pack['groups']['closeout_digest']['golden']['debit'] = 1
        self.work.vectors.write_bytes(script.dump(pack))
        code, _, err = self.check()
        self.assertEqual(code, 1)
        self.assertIn('differs from the digest: $.golden.debit', err)

    def test_vendor_flags_must_all_be_true_even_when_both_copies_match(self):
        for name in sorted(vendor_manifest()['files']):
            with self.subTest(file=name):
                document = json.loads(self.raw)
                document['vendor']['files'][name] = False
                self.assertIs(document['vendor']['verified'], True)
                self.assertIs(document['ok'], True)
                self.work.artifact.write_bytes(script.dump(document))
                self.work.embed(document)
                code, _, err = self.check()
                self.assertEqual(code, 1)
                self.assertIn('$.vendor', err)

    def test_vendor_pin_file_set_and_summary_must_match_the_manifest(self):
        for what, mutate in {
            'wrong commit': lambda v: v.update(commit='0' * 40),
            'missing file': lambda v: v['files'].pop(next(iter(v['files']))),
            'extra file': lambda v: v['files'].update({'extra.py': True}),
            'unverified': lambda v: v.update(verified=False),
            'non-boolean flag': lambda v: v['files'].update({next(iter(v['files'])): 1}),
            'missing vendor': lambda v: v.clear(),
        }.items():
            with self.subTest(change=what):
                document = json.loads(self.raw)
                mutate(document['vendor'])
                self.work.artifact.write_bytes(script.dump(document))
                self.work.embed(document)
                code, _, err = self.check()
                self.assertEqual(code, 1)
                self.assertIn('$.vendor', err)

    def test_a_tampered_digest_with_a_stale_embedded_copy_fails(self):
        document = json.loads(self.raw)
        document['packaged']['sha256'] = '0' * 64
        self.work.artifact.write_bytes(script.dump(document))
        code, _, err = self.check()
        self.assertEqual(code, 1)
        self.assertIn('$.packaged.sha256', err)

    def test_the_candidate_index_must_name_the_group(self):
        pack = json.loads(self.work.vectors.read_bytes())
        for row in pack['candidates']:
            if row['id'] == 'fin-finance-closeout':
                row['vectors'] = None
        self.work.vectors.write_bytes(script.dump(pack))
        self.assertEqual(self.check()[0], 1)

    def test_a_missing_group_fails(self):
        pack = json.loads(self.work.vectors.read_bytes())
        del pack['groups']['closeout_digest']
        self.work.vectors.write_bytes(script.dump(pack))
        self.assertEqual(self.check()[0], 1)

    def test_non_canonical_bytes_fail(self):
        for what, changed in {
            'indented': json.dumps(json.loads(self.raw), indent=2, sort_keys=True).encode() + b'\n',
            'no trailing newline': self.raw.rstrip(b'\n'),
            'two trailing newlines': self.raw + b'\n',
            'truncated': self.raw[:len(self.raw) // 2],
            'empty': b'',
        }.items():
            with self.subTest(bytes=what):
                self.work.artifact.write_bytes(changed)
                self.assertEqual(self.check()[0], 1)

    def test_a_dishonest_label_fails(self):
        for key, value in {
            'semantic_conformance': True, 'upstream_nodes_completed': ['fin-finance-closeout'],
            'ok': False, 'funds_executed': True, 'label': 'ADOPTED', 'data_label': 'REAL',
            'format': 'KIX_CAPITAL_CLOSEOUT_DIGEST_V2', 'candidate': 'fin-ledger-contract',
        }.items():
            with self.subTest(key=key):
                document = json.loads(self.raw)
                document[key] = value
                self.work.artifact.write_bytes(script.dump(document))
                self.work.embed(document)
                code, _, err = self.check()
                self.assertEqual(code, 1)
                self.assertIn(f'$.{key}', err)

    def test_a_strip_key_at_any_depth_fails(self):
        for where in ('top', 'stage', 'golden', 'vendor', 'packaged'):
            with self.subTest(where=where):
                document = json.loads(self.raw)
                target = document if where == 'top' else document['stages'][0] if where == 'stage' else document[where]
                target['head_sha'] = FAKE_HEAD
                self.work.artifact.write_bytes(script.dump(document))
                self.work.embed(document)
                code, _, err = self.check()
                self.assertEqual(code, 1)
                self.assertIn('strip key present', err)

    def test_a_changed_strip_list_a_dropped_stage_or_a_reorder_fails(self):
        for what, mutate in {
            'shorter stripped_keys': lambda d: d['stripped_keys'].pop(),
            'dropped stage': lambda d: d['stages'].pop(),
            'reordered stages': lambda d: d['stages'].reverse(),
        }.items():
            with self.subTest(change=what):
                document = json.loads(self.raw)
                mutate(document)
                self.work.artifact.write_bytes(script.dump(document))
                self.work.embed(document)
                self.assertEqual(self.check()[0], 1)

    def test_a_mode_is_required_and_the_modes_exclude_each_other(self):
        for argv in ([], ['--check', '--write'], ['--check', '--check-evidence']):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    script.main(argv)
                self.assertEqual(caught.exception.code, 2)


class CommittedArtifactTests(unittest.TestCase):
    """The committed bytes, against the hand-written shape."""

    @classmethod
    def setUpClass(cls):
        cls.raw = ARTIFACT.read_bytes()
        cls.digest = json.loads(cls.raw)

    def test_bytes_are_canonical_ascii(self):
        self.assertTrue(self.raw.endswith(b'\n') and not self.raw.endswith(b'\n\n'))
        self.raw.decode('ascii')
        self.assertEqual(script.dump(self.digest), self.raw)

    def test_the_committed_digest_is_an_honest_clean_pass_of_the_nine_stage_ladder(self):
        digest = self.digest
        self.assertEqual(digest['format'], 'KIX_CAPITAL_CLOSEOUT_DIGEST_V1')
        self.assertEqual(digest['label'], 'INPUT_VECTOR_CANDIDATE')
        self.assertEqual(digest['data_label'], 'SIMULATED')
        self.assertEqual(digest['candidate'], 'fin-finance-closeout')
        self.assertIs(digest['semantic_conformance'], False)
        self.assertEqual(digest['upstream_nodes_completed'], [])
        self.assertIs(digest['funds_executed'], False)
        self.assertIs(digest['ok'], True)
        self.assertEqual(digest['non_claims'], NON_CLAIMS)
        self.assertEqual(digest['stripped_keys'], STRIP_KEYS)
        self.assertEqual([(row['stage_id'], row['command']) for row in digest['stages']], list(STAGES))
        for row in digest['stages']:
            self.assertEqual((row['status'], row['expected_exit'], row['label'], row['funds_executed']),
                             ('passed', 0, 'SIMULATED', False), row['stage_id'])

    def test_covered_counts_are_plausible_and_the_parser_nulls_are_kept(self):
        counts = {row['stage_id']: row['test_count'] for row in self.digest['stages']}
        self.assertIsNone(counts['node-check'])
        self.assertGreater(counts['unit']['ran'], 300)
        for stage_id in ('unit', 'storage-conformance', 'pinned-vendor', 'upstream-claims', 'seeded-demo'):
            with self.subTest(stage=stage_id):
                count = counts[stage_id]
                self.assertEqual(count['failed'], 0)
                self.assertEqual(count['passed'], count['ran'])
        self.assertEqual(counts['seeded-demo'], {'ran': 1, 'passed': 1, 'failed': 0})

    def test_golden_vendor_and_packaged_pins(self):
        recorded = golden()
        self.assertEqual(self.digest['golden'], {
            'status': 'recorded', 'state_digest': recorded['state_digest'],
            'content_digest': recorded['content_digest'], 'debit': 385000, 'credit': 385000})
        self.assertEqual(self.digest['vendor']['commit'], '7481b0e16ce9b903abbffa62249bb91cd9e63cfe')
        self.assertEqual(sorted(self.digest['vendor']['files']), sorted(vendor_manifest()['files']))
        self.assertTrue(all(value is True for value in self.digest['vendor']['files'].values()))
        self.assertRegex(self.digest['packaged']['sha256'], r'^[0-9a-f]{64}$')

    def test_no_strip_key_is_a_key_at_any_depth(self):
        def keys(value, found):
            if type(value) is dict:
                for key, item in value.items():
                    found.append(key)
                    keys(item, found)
            elif type(value) is list:
                for item in value:
                    keys(item, found)
            return found
        self.assertEqual(sorted(set(keys(self.digest, [])) & set(STRIP_KEYS)), [])

    def test_a_byte_scan_finds_no_head_sha_tool_version_timestamp_or_instance_id(self):
        # The stripped_keys array names the removed keys, so it is the only place those words may appear.
        text = self.raw.decode('ascii')
        listed = '"stripped_keys":' + json.dumps(STRIP_KEYS, separators=(',', ':'))
        self.assertEqual(text.count(listed), 1)
        body = text.replace(listed, '')
        # head_sha is named once, in the decided non_claims sentence; its value is what must be absent.
        self.assertEqual(body.count('head_sha'), 1)
        self.assertIn('head_sha and tool versions are stripped by design', self.digest['non_claims'][3])
        for word in ('instance_id', 'tool_versions', 'timestamp', 'created_at', 'duration_s', 'cwd'):
            self.assertNotIn(word, body)
        self.assertEqual(SHA40.findall(body.replace(vendor_manifest()['commit'], '')), [], 'a 40-hex sha is present')
        self.assertEqual(UUID.findall(body), [])
        self.assertEqual(TIMESTAMP.findall(body), [])
        self.assertEqual(HOST_PATH.findall(body), [])
        versions = [sys.version.split()[0], CAPITAL_VERSION]
        for tool in (['node', '--version'], ['npm', '--version']):
            try:
                found = subprocess.run(tool, capture_output=True, text=True, timeout=20, check=False).stdout.strip()
            except (OSError, subprocess.SubprocessError):
                found = ''
            if found:
                versions.append(found)
        for version in versions:
            with self.subTest(version=version):
                self.assertNotIn(version, body)

    def test_the_head_sha_of_a_present_evidence_file_or_the_checkout_is_absent(self):
        shas = set()
        evidence = ROOT / 'build' / 'acceptance-evidence.json'
        if evidence.is_file():
            try:
                shas.add(json.loads(evidence.read_text(encoding='utf-8')).get('head_sha'))
            except ValueError:
                pass
        try:
            proc = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True,
                                  timeout=20, check=False)
            shas.add(proc.stdout.strip() if proc.returncode == 0 else None)
        except (OSError, subprocess.SubprocessError):
            pass
        shas.discard(None)
        shas.discard('')
        for sha in shas:
            self.assertNotIn(sha.encode(), self.raw)

    def test_check_passes_on_the_committed_pair_through_the_cli(self):
        proc = subprocess.run([sys.executable, str(SCRIPT), '--check'], cwd=ROOT,
                              capture_output=True, text=True, timeout=120, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, '')

    def test_the_policy_read_from_the_note_is_the_hand_written_one(self):
        policy = script.load_policy()
        self.assertEqual(list(policy['strip_keys']), STRIP_KEYS)
        self.assertEqual(policy['non_claims'], NON_CLAIMS)
        self.assertEqual(policy['labels'], {
            'label': 'INPUT_VECTOR_CANDIDATE', 'simulated': True, 'provisional': True,
            'semantic_conformance': False, 'upstream_nodes_completed': [], 'funds_executed': False,
            'human_product_acceptance': 'NOT_PART_OF_LADDER', 'production': 'NOT_AUTHORIZED'})


class FinanceVectorWiringTests(unittest.TestCase):
    def setUp(self):
        self.pack = json.loads(VECTORS.read_text(encoding='ascii'))

    def test_the_group_is_the_digest_file_byte_for_byte(self):
        self.assertEqual(script.dump(self.pack['groups']['closeout_digest']), ARTIFACT.read_bytes())
        self.assertEqual(self.pack['groups']['closeout_digest']['candidate'], 'fin-finance-closeout')

    def test_eight_of_eight_candidates_carry_vectors_with_a_null_reason(self):
        rows = self.pack['candidates']
        self.assertEqual(len(rows), 8)
        self.assertTrue(all(row['vectors'] is not None and row['reason'] is None for row in rows))
        by_id = {row['id']: row['vectors'] for row in rows}
        self.assertEqual(by_id['fin-finance-closeout'], 'closeout_digest')

    def test_the_honesty_fields_did_not_move(self):
        self.assertIs(self.pack['semantic_conformance'], False)
        self.assertEqual(self.pack['upstream_nodes_completed'], [])

    def test_the_vector_generator_reads_the_committed_digest_and_refuses_a_missing_one(self):
        finance = _load('finance_vectors_for_closeout', ROOT / 'scripts' / 'finance_vectors.py')
        self.assertEqual(finance.dump(finance.closeout_digest()), ARTIFACT.read_bytes())
        with tempfile.TemporaryDirectory() as tmp:
            original = finance.CLOSEOUT_FILE
            finance.CLOSEOUT_FILE = Path(tmp) / 'absent.json'
            try:
                with self.assertRaises(finance.VectorError):
                    finance.closeout_digest()
            finally:
                finance.CLOSEOUT_FILE = original


class DocsTests(unittest.TestCase):
    def test_script_docstring_states_the_non_claim_and_the_modes(self):
        for phrase in ('not SEMANTIC_CONFORMANCE', 'completes no upstream node', '--write', '--check', '--check-evidence'):
            self.assertIn(phrase, script.__doc__)

    def test_readme_validation_and_handbook_document_the_artifact_and_its_check(self):
        readme = README.read_text(encoding='utf-8')
        for needle in ('tests/vectors/closeout_digest.json', 'KIX_CAPITAL_CLOSEOUT_DIGEST_V1',
                       'scripts/closeout_digest.py --check', 'scripts/closeout_digest.py --write'):
            with self.subTest(doc='README', needle=needle):
                self.assertIn(needle, readme)
        validation = VALIDATION.read_text(encoding='utf-8')
        self.assertIn('\n## closeout-evidence-vector', validation)
        section = validation.split('\n## closeout-evidence-vector', 1)[1].split('\n## ', 1)[0]
        for needle in ('closeout_digest.json', '--check-evidence', 'not SEMANTIC_CONFORMANCE',
                       'completes no upstream node', 'head_sha'):
            with self.subTest(doc='VALIDATION', needle=needle):
                self.assertIn(needle, section)
        handbook = HANDBOOK.read_text(encoding='utf-8')
        self.assertIn('<!-- handbook-section:closeout-evidence-vector -->', handbook)
        part = handbook.split('<!-- handbook-section:closeout-evidence-vector -->', 1)[1].split(
            '<!-- /handbook-section -->', 1)[0]
        for needle in ('closeout_digest.json', 'closeout_digest.py --check', '--check-evidence',
                       'SEMANTIC_CONFORMANCE', 'upstream'):
            with self.subTest(doc='handbook', needle=needle):
                self.assertIn(needle, part)

    def test_the_binding_note_maps_the_candidate_to_the_digest(self):
        text = BINDING.read_text(encoding='utf-8')
        self.assertIn('tests/vectors/closeout_digest.json (derived from that evidence)', text)
        self.assertNotIn('"fin-finance-closeout": "build/acceptance-evidence.json as consumer-side evidence candidate"', text)

    def test_the_ladder_gained_no_closeout_stage(self):
        self.assertEqual(len(acceptance_ladder.REQUIRED_STAGES), 9)
        self.assertEqual([stage['id'] for stage in acceptance_ladder.build_plan()],
                         list(acceptance_ladder.REQUIRED_STAGES))
        self.assertNotIn('closeout', ' '.join(acceptance_ladder.REQUIRED_STAGES))


if __name__ == '__main__':
    unittest.main()
