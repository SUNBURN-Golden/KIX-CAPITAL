#!/usr/bin/env python3
"""Project build/acceptance-evidence.json into the committed closeout digest.

The artifact is tests/vectors/closeout_digest.json, format
KIX_CAPITAL_CLOSEOUT_DIGEST_V1. It is the INPUT_VECTOR_CANDIDATE material for the
FINANCE_PENDING_NODES candidate fin-finance-closeout, the eighth group of
tests/vectors/finance_vectors.json (scripts/finance_vectors.py embeds it). The
policy is docs/decisions/CAPITAL_CLOSEOUT_ARTIFACT.md: the strip keys, the honesty
labels and the non-claims are read from that note, not copied here.

The digest keeps only an allowlist of the evidence: per acceptance stage the id,
the commands, the status, the expected exit, the test count, the label SIMULATED
and funds_executed false; the seeded-demo digests and totals; the vendor pin
commit with its five verified flags; and the packaged artifact sha256. The git
head_sha, tool versions, timestamps, instance ids, paths and hosts are never
carried (and any strip key is also deleted at every depth), so the same tree gives
the same bytes on any machine. The artifact is canonical ASCII JSON.

This is not SEMANTIC_CONFORMANCE and it completes no upstream node. It is
self-asserted evidence from this repository's own tooling.

--write regenerates the artifact from the evidence and refuses unless the evidence
is ok:true, SIMULATED, funds_executed false and holds every required stage passed.
--check needs no evidence: it checks the committed bytes and the copy embedded in
tests/vectors/finance_vectors.json and exits 1 on any drift.
--check-evidence regenerates from fresh evidence, byte-compares, and names the first
differing JSON path.
--file points the artifact, --evidence the evidence, --vectors the finance pack.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_FILE = ROOT / 'tests' / 'vectors' / 'closeout_digest.json'
DEFAULT_EVIDENCE = ROOT / 'build' / 'acceptance-evidence.json'
DEFAULT_VECTORS = ROOT / 'tests' / 'vectors' / 'finance_vectors.json'
DECISION_NOTE = ROOT / 'docs' / 'decisions' / 'CAPITAL_CLOSEOUT_ARTIFACT.md'
VENDOR_MANIFEST = ROOT / 'capital' / 'vendor' / 'manifest.json'
FORMAT = 'KIX_CAPITAL_CLOSEOUT_DIGEST_V1'
EVIDENCE_FORMAT = 'KIX_CAPITAL_ACCEPTANCE_EVIDENCE_V1'
CANDIDATE = 'fin-finance-closeout'
GROUP = 'closeout_digest'
ROLE = 'INPUT_VECTOR_CANDIDATE'
SOURCE = 'build/acceptance-evidence.json (untracked per-run output of scripts/acceptance.py)'
EXPECTED_EXIT = 0
BUILT_ARTIFACT = '<built-zipapp>'
# The acceptance ladder, in order. Written here so a dropped or added stage is drift, not silently followed.
REQUIRED_STAGES = (
    'unit', 'storage-conformance', 'pinned-vendor', 'upstream-claims',
    'node-check', 'browser', 'packaged-smoke', 'seeded-demo',
)
PACKAGED_STAGE = 'packaged-smoke'
GOLDEN_KEYS = ('status', 'state_digest', 'content_digest')
TEST_COUNT_KEYS = ('ran', 'passed', 'failed')
NOTE = (
    'SIMULATED closeout digest of the acceptance ladder: the stage results, golden digests, vendor pin and '
    'packaged sha256 that the evidence recorded, with every per-run field stripped (see stripped_keys). '
    'INPUT_VECTOR_CANDIDATE only. This is not SEMANTIC_CONFORMANCE, it completes no upstream node, and it is '
    'self-asserted by this repository.'
)
_SHA256 = re.compile(r'[0-9a-f]{64}\Z')
_PYZ_LINE = re.compile(r'^\S+\.pyz ([0-9a-f]{64})$')


class DigestError(Exception):
    pass


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dump(body) -> bytes:
    return (json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode('ascii')


def _require(condition, message):
    if not condition:
        raise DigestError(message)


def load_policy(note=DECISION_NOTE) -> dict:
    """Strip keys and honesty labels, read from the ADOPTED entries of the decision note."""
    try:
        blocks = _load_script('decision_ledger').extract_blocks(Path(note).read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError) as exc:
        raise DigestError(f'decision note unreadable: {exc}') from exc
    _require(len(blocks) == 1, f'{note} must hold exactly one capital-decision-v1 block')
    entries = blocks[0].get('entries', {})
    try:
        strip = entries['stripped_fields_policy']
        label = entries['honesty_label_policy']
        _require(strip['status'] == 'ADOPTED' and label['status'] == 'ADOPTED', 'closeout policy is not ADOPTED')
        strip_keys = strip['value']['strip_keys']
        labels = label['value']['labels']
        non_claims = label['value']['non_claims']
    except (KeyError, TypeError) as exc:
        raise DigestError(f'decision note lacks {exc}') from exc
    _require(type(strip_keys) is list and strip_keys and all(type(key) is str for key in strip_keys),
             'strip_keys is not a string list')
    _require(type(labels) is dict and type(non_claims) is list, 'honesty labels are malformed')
    return {'strip_keys': tuple(strip_keys), 'labels': labels, 'non_claims': non_claims}


def strip_keys_at_every_depth(value, keys):
    if type(value) is dict:
        return {key: strip_keys_at_every_depth(item, keys) for key, item in value.items() if key not in keys}
    if type(value) is list:
        return [strip_keys_at_every_depth(item, keys) for item in value]
    return value


def load_evidence(path) -> dict:
    try:
        evidence = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError) as exc:
        raise DigestError(f'evidence unreadable: {path}: {exc}') from exc
    _require(type(evidence) is dict, 'evidence is not an object')
    return evidence


def gate(evidence):
    """The write gate of CAPITAL-CLOSEOUT-REGEN-V1. Raises DigestError unless the ladder passed honestly."""
    _require(evidence.get('format') == EVIDENCE_FORMAT, f'evidence format is not {EVIDENCE_FORMAT}')
    _require(evidence.get('ok') is True, 'evidence ok is not true')
    _require(evidence.get('label') == 'SIMULATED', 'evidence label is not SIMULATED')
    _require(evidence.get('funds_executed') is False, 'evidence funds_executed is not false')
    stages = evidence.get('stages')
    _require(type(stages) is list, 'evidence stages is not a list')
    by_id = {}
    for stage in stages:
        _require(type(stage) is dict and type(stage.get('id')) is str, 'evidence stage is malformed')
        _require(stage['id'] not in by_id, f'evidence stage {stage["id"]} is duplicated')
        by_id[stage['id']] = stage
    for stage_id in REQUIRED_STAGES:
        _require(stage_id in by_id, f'evidence lacks stage {stage_id}')
        _require(by_id[stage_id].get('status') == 'passed', f'evidence stage {stage_id} did not pass')
        _require(by_id[stage_id].get('exit_code') == EXPECTED_EXIT and by_id[stage_id].get('injected') is False,
                 f'evidence stage {stage_id} exit_code or injected is not clean')
    _require(list(by_id) == list(REQUIRED_STAGES), 'evidence stages are not exactly the ladder, in order')
    return by_id


def _command_text(argv):
    """One command as text: the interpreter path becomes python3 and the built zipapp path (it names the capital version) a placeholder."""
    _require(type(argv) is list and argv and all(type(part) is str for part in argv), 'a stage command is malformed')
    parts = []
    for index, part in enumerate(argv):
        if index == 0 and part.startswith('/') and Path(part).name.startswith('python'):
            part = 'python3'
        elif part.endswith('.pyz'):
            part = BUILT_ARTIFACT
        parts.append(part)
    for part in parts:
        _require(not part.startswith('/'), f'a stage command carries the absolute path {part}')
    return ' '.join(parts)


def _test_count(value):
    if value is None:
        return None
    _require(type(value) is dict, 'a test_count is malformed')
    return {key: value.get(key) for key in TEST_COUNT_KEYS}


def _stage_row(stage):
    return {
        'stage_id': stage['id'],
        'command': [_command_text(record.get('argv')) for record in stage.get('commands', [])],
        'status': stage['status'],
        'expected_exit': EXPECTED_EXIT,
        'test_count': _test_count(stage.get('test_count')),
        'label': 'SIMULATED',
        'funds_executed': False,
    }


def _packaged_sha256(stage):
    """sha256 of the built zipapp, from the last stdout line of the build command."""
    for record in stage.get('commands', []):
        lines = [line for line in str(record.get('output_tail', '')).strip().splitlines() if line.strip()]
        match = _PYZ_LINE.match(lines[-1].strip()) if lines else None
        if match and 'build_release.py' in ' '.join(record.get('argv', [])):
            return match.group(1)
    raise DigestError('packaged-smoke build record prints no "<path>.pyz <sha256>" line')


def _vendor_manifest():
    try:
        return json.loads(VENDOR_MANIFEST.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError) as exc:
        raise DigestError(f'vendor manifest unreadable: {exc}') from exc


def _vendor(evidence):
    vendor = evidence.get('vendor_hashes')
    _require(type(vendor) is dict and vendor.get('verified') is True, 'evidence vendor_hashes is not verified')
    pinned = _vendor_manifest()
    _require(vendor.get('commit') == pinned.get('commit'), 'evidence vendor commit differs from the manifest pin')
    hashes = vendor.get('hashes')
    _require(type(hashes) is dict and sorted(hashes) == sorted(pinned['files']), 'evidence vendor file set differs')
    for name, expected in sorted(pinned['files'].items()):
        _require(hashes[name] == expected, f'evidence vendor hash differs from the manifest pin: {name}')
    return {
        'commit': pinned['commit'],
        'files': {name: hashes[name] == expected for name, expected in sorted(pinned['files'].items())},
        'verified': True,
    }


def _golden(evidence):
    golden = evidence.get('golden_digests')
    _require(type(golden) is dict and golden.get('status') == 'recorded', 'evidence golden_digests are not recorded')
    totals = golden.get('projection_totals')
    _require(type(totals) is dict and 'debit' in totals and 'credit' in totals, 'golden projection_totals missing')
    for key in ('state_digest', 'content_digest'):
        _require(type(golden.get(key)) is str and _SHA256.match(golden[key]), f'golden {key} is not a sha256')
    return {
        'status': golden['status'], 'state_digest': golden['state_digest'],
        'content_digest': golden['content_digest'], 'debit': totals['debit'], 'credit': totals['credit'],
    }


def build_digest(evidence, policy=None) -> dict:
    """The digest body. Pure: the evidence is read, nothing is written. Raises DigestError at the gate."""
    policy = load_policy() if policy is None else policy
    by_id = gate(evidence)
    packaged = _packaged_sha256(by_id[PACKAGED_STAGE])
    body = {
        'format': FORMAT, 'label': ROLE, 'data_label': 'SIMULATED', 'candidate': CANDIDATE,
        **policy['labels'], 'non_claims': policy['non_claims'],
        'ok': True, 'evidence_format': EVIDENCE_FORMAT, 'source': SOURCE,
        'stripped_keys': list(policy['strip_keys']),
        'stages': [_stage_row(by_id[stage_id]) for stage_id in REQUIRED_STAGES],
        'golden': _golden(evidence), 'vendor': _vendor(evidence),
        'packaged': {'sha256': packaged, 'artifact_kind': 'LOCAL_SIMULATION_ARTIFACT'},
        'note': NOTE,
    }
    covered = strip_keys_at_every_depth(
        {key: value for key, value in body.items() if key != 'stripped_keys'}, set(policy['strip_keys']))
    covered['stripped_keys'] = body['stripped_keys']
    return covered


def build_artifact(evidence, policy=None) -> bytes:
    return dump(build_digest(evidence, policy))


def drift_paths(expected: bytes, actual: bytes, limit=8):
    """JSON paths where the two byte strings differ, or a reason when either does not parse."""
    try:
        return _load_script('seed_demo').diff_paths(json.loads(expected), json.loads(actual))[:limit] or ['$']
    except ValueError:
        return ['unparseable']


def _has_strip_key(value, keys, path='$'):
    if type(value) is dict:
        for key, item in value.items():
            if key in keys:
                return f'{path}.{key}'
            found = _has_strip_key(item, keys, f'{path}.{key}')
            if found:
                return found
    elif type(value) is list:
        for index, item in enumerate(value):
            found = _has_strip_key(item, keys, f'{path}[{index}]')
            if found:
                return found
    return None


def structural_problems(raw: bytes, policy) -> list:
    """Why the committed bytes are not an honest, canonical digest; empty when they are."""
    try:
        document = json.loads(raw.decode('ascii'))
    except (UnicodeError, ValueError):
        return ['not ascii json']
    if type(document) is not dict:
        return ['not an object']
    problems = []
    if dump(document) != raw:
        problems.append('bytes are not canonical')
    expected = {'format': FORMAT, 'label': ROLE, 'data_label': 'SIMULATED', 'candidate': CANDIDATE,
                'ok': True, 'semantic_conformance': False, 'upstream_nodes_completed': [],
                'funds_executed': False, 'simulated': True, 'provisional': True}
    for key, value in expected.items():
        if document.get(key) != value or type(document.get(key)) is not type(value):
            problems.append(f'$.{key} is not {value!r}')
    if document.get('stripped_keys') != list(policy['strip_keys']):
        problems.append('$.stripped_keys differs from the decision note')
    body = {key: value for key, value in document.items() if key != 'stripped_keys'}
    found = _has_strip_key(body, set(policy['strip_keys']))
    if found:
        problems.append(f'strip key present at {found}')
    try:
        pinned = _vendor_manifest()
    except DigestError as exc:
        problems.append(str(exc))
    else:
        expected_vendor = {
            'commit': pinned['commit'],
            'files': {name: True for name in pinned['files']},
            'verified': True,
        }
        if dump(document.get('vendor')) != dump(expected_vendor):
            problems.append('$.vendor must match the manifest pin and verify every pinned file')
    stages = document.get('stages')
    if type(stages) is not list or [row.get('stage_id') for row in stages if type(row) is dict] != list(REQUIRED_STAGES):
        problems.append('$.stages is not the acceptance ladder')
    else:
        for row in stages:
            if (row.get('status') != 'passed' or row.get('expected_exit') != EXPECTED_EXIT
                    or row.get('label') != 'SIMULATED' or row.get('funds_executed') is not False):
                problems.append(f'stage {row.get("stage_id")} is not a clean SIMULATED pass')
    return problems


def check(file, vectors, policy):
    """Evidence-free gate. Returns a list of failure lines; empty means clean."""
    try:
        raw = Path(file).read_bytes()
    except OSError:
        return [f'closeout digest missing: {file}']
    failures = [f'closeout digest: {item}' for item in structural_problems(raw, policy)]
    try:
        pack = json.loads(Path(vectors).read_text(encoding='ascii'))
        embedded = pack['groups'][GROUP]
        index = {row['id']: row['vectors'] for row in pack['candidates']}
    except (OSError, UnicodeError, ValueError, KeyError, TypeError):
        return failures + [f'finance vectors lack group {GROUP}: {vectors}']
    if dump(embedded) != raw:
        paths = drift_paths(raw, dump(embedded))
        failures.append(f'finance vectors group {GROUP} differs from the digest: ' + ', '.join(paths))
    if index.get(CANDIDATE) != GROUP:
        failures.append(f'finance vectors candidates index does not name {GROUP} for {CANDIDATE}')
    return failures


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write', action='store_true', help='Regenerate the artifact from ok:true evidence.')
    mode.add_argument('--check', action='store_true', help='Evidence-free structural and embedded-copy gate. Exit 1 on drift.')
    mode.add_argument('--check-evidence', action='store_true', help='Byte-compare against a fresh regeneration. Exit 1 on drift.')
    parser.add_argument('--file', type=Path, default=DEFAULT_FILE, help='Artifact path. Default tests/vectors/closeout_digest.json')
    parser.add_argument('--evidence', type=Path, default=DEFAULT_EVIDENCE,
                        help='Evidence path. Default build/acceptance-evidence.json')
    parser.add_argument('--vectors', type=Path, default=DEFAULT_VECTORS,
                        help='Finance vector pack path. Default tests/vectors/finance_vectors.json')
    args = parser.parse_args(argv)
    try:
        policy = load_policy()
        if args.check:
            failures = check(args.file, args.vectors, policy)
            if failures:
                for line in failures:
                    print(line, file=sys.stderr)
                print('run the CAPITAL-CLOSEOUT-REGEN-V1 procedure: acceptance.py, closeout_digest.py --write, '
                      'finance_vectors.py --write', file=sys.stderr)
                return 1
            print(f'closeout digest ok: {args.file.stat().st_size} bytes, embedded in finance vectors')
            return 0
        data = build_artifact(load_evidence(args.evidence), policy)
        if args.write:
            args.file.parent.mkdir(parents=True, exist_ok=True)
            args.file.write_bytes(data)
            print(f'closeout digest written: {len(data)} bytes to {args.file}')
            return 0
        if not args.file.is_file():
            print(f'closeout digest missing: {args.file}', file=sys.stderr)
            return 1
        recorded = args.file.read_bytes()
    except (OSError, DigestError) as exc:
        print(f'closeout digest failed: {exc}', file=sys.stderr)
        return 1
    if recorded != data:
        print('closeout digest drift: ' + ', '.join(drift_paths(recorded, data)), file=sys.stderr)
        print('run python3 scripts/closeout_digest.py --write after a fresh acceptance run', file=sys.stderr)
        return 1
    print(f'closeout digest matches the evidence: {len(data)} bytes')
    return 0


if __name__ == '__main__':
    sys.exit(main())
