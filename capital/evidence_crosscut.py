"""Offline cross-artifact consistency evidence over three captured artifacts.

`python3 -m capital.evidence_crosscut --workspace FILE --manifest FILE --facts DIR`
reads each input once, verifies it with the existing offline verifiers
(`audit_workspace_bytes`, `verify_manifest`, `facts.verify_dir`), then compares
the F04 journal, overlay and fixture commitments shared by all three.
Individually valid artifacts captured from different cuts of a workspace fail
with named `CROSS_*` reasons even when every artifact's own hashes verify.

Only commitments represented by all relevant inputs are compared. Each source
file is read without a lock, a write, or a repair. This is deterministic local
consistency evidence: collecting pages, SQL projection checks, new manifest
formats, signing, source authentication, and detecting wholesale replacement
by a fully consistent alternative book are all out of scope and labeled.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

from capital import facts as facts_module
from capital import verify
from capital.audit import audit_workspace_bytes
from capital.export import (
    OVERLAY_SECTION, SECTION_IDS, ExportError, load_dev_key, sha256_hex,
)
from capital.keyset import load_dev_keyset
from capital.producer import FixtureViews
from capital.protocol import CreditMachine
from capital.store import canonical_bytes, overlay_section
from capital.strict_json import loads

FORMAT = 'KIX_CAPITAL_EVIDENCE_CROSSCUT_V1'
MODE = 'EVIDENCE_CROSSCUT_CHECK'
INPUT_CHECKS = ('workspace_audit', 'manifest_verify', 'facts_verify')
CROSS_CHECKS = ('journal_content', 'f04_commitment', 'overlay_presence',
                'overlay_content', 'overlay_commitment', 'fixtures_commitment')
CHECK_ORDER = INPUT_CHECKS + CROSS_CHECKS


def _capture_file(path):
    """Bytes of one regular file, or None. No lock, no write."""
    try:
        path = Path(path)
        if not path.is_file():
            return None
        return path.read_bytes()
    except (OSError, TypeError, ValueError):
        return None


def _parse(raw):
    try:
        return loads(raw)
    except (UnicodeError, ValueError, json.JSONDecodeError, RecursionError, TypeError):
        return None


def _check(checks, name, ok, reason=None, detail=None):
    checks.append({
        'id': name,
        'status': 'NOT_CHECKED' if ok is None else ('MATCHED' if ok else 'MISMATCH'),
        'reason': reason if ok is False else None,
        'detail': detail or {},
    })


def _sha(raw):
    return None if raw is None else hashlib.sha256(raw).hexdigest()


def _workspace_input(path, checks):
    """Read FILE once, audit the same bytes, extract the shared commitments."""
    raw = _capture_file(path)
    report = audit_workspace_bytes(raw, workspace=str(path))
    info = {'path': str(path), 'ok': report['ok'], 'reason': report['reason'],
            'report': report, 'sha256': _sha(raw)}
    extracted = None
    if report['ok']:
        # audit_workspace_bytes already strict-parsed these exact bytes.
        document = _parse(raw)
        if type(document) is dict:
            payload = document['payload']
            section = overlay_section(document)
            extracted = {
                'journal': payload['journal'],
                'state_digest': payload['state_digest'],
                'overlay_journal': [] if section is None else section['journal'],
                'overlay_digest': (None if section is None
                                   else section['overlay_state']['digest']),
            }
        if extracted is None:
            info['ok'], info['reason'] = False, 'WORKSPACE_EXTRACT_FAILED'
    _check(checks, 'workspace_audit', info['ok'], info['reason'])
    return info, extracted


def _manifest_input(path, checks, *, key, key_error, keyset, keyset_error):
    """Read FILE once, verify section hashes/digest/signature, extract bodies."""
    raw = _capture_file(path)
    document = _parse(raw) if raw is not None else None
    if raw is None or document is None:
        pending = {name: 'NOT_CHECKED' for name in SECTION_IDS}
        report = verify._fail('MANIFEST_UNREADABLE', pending)
    else:
        report = verify.verify_manifest(
            document, key, key_error, keyset=keyset, keyset_error=keyset_error)
    info = {'path': str(path), 'ok': report['ok'], 'reason': report['reason'],
            'report': report, 'sha256': _sha(raw)}
    extracted = None
    if report['ok']:
        bodies = {name: document['sections'][name]['body']
                  for name in document['sections']}
        journal = bodies['journal'].get('entries')
        fixture_rows = bodies['fixtures'].get('rows')
        fixtures_digest = bodies['fixtures'].get('fixtures_digest')
        if OVERLAY_SECTION in bodies:
            overlay_body = bodies[OVERLAY_SECTION]
            overlay_journal = overlay_body.get('journal')
            overlay_digest = overlay_body.get('overlay_state_digest')
        else:
            overlay_journal, overlay_digest = [], None
        if (type(journal) is list and type(fixture_rows) is dict
                and type(fixtures_digest) is str
                and type(overlay_journal) is list
                and (OVERLAY_SECTION not in bodies or type(overlay_digest) is str)):
            extracted = {
                'journal': journal,
                'fixture_rows': fixture_rows,
                'fixtures_digest': fixtures_digest,
                'overlay_journal': overlay_journal,
                'overlay_digest': overlay_digest,
            }
        else:
            # A hash-valid manifest can still lack a shared field; fail closed.
            info['ok'], info['reason'] = False, 'MANIFEST_EXTRACT_FAILED'
    _check(checks, 'manifest_verify', info['ok'], info['reason'])
    return info, extracted


def _facts_input(directory, checks):
    """Capture page bytes once, verify DIR, extract the cut and ordered rows."""
    try:
        paths = sorted(Path(directory).glob('page-*.json'))
    except (OSError, TypeError, ValueError):
        paths = []
    pages, captured = [], bytearray()
    capture_ok = True
    for path in paths:
        raw = _capture_file(path)
        page = _parse(raw) if raw is not None else None
        if page is None:
            capture_ok = False
            break
        pages.append(page)
        captured += path.name.encode() + b'\x00' + raw
    report = facts_module.verify_dir(directory)
    pages_sha = _sha(bytes(captured)) if capture_ok and captured else None
    info = {'path': str(directory), 'ok': report['ok'], 'reason': report['reason'],
            'report': report, 'sha256': pages_sha}
    extracted = None
    if report['ok'] and capture_ok and pages:
        journal = [row['entry'] for page in pages for row in page['rows']
                   if row['source'] == 'JOURNAL']
        overlay_journal = [row['entry'] for page in pages for row in page['rows']
                           if row['source'] == 'OVERLAY']
        extracted = {'journal': journal, 'overlay_journal': overlay_journal,
                     'cut': copy.deepcopy(pages[0]['cut'])}
    if report['ok'] and extracted is None:
        # Verification passed but the captured pages could not be replayed for
        # extraction (for example the files changed between the two reads).
        info['ok'], info['reason'] = False, 'FACTS_PAGES_UNREADABLE'
    _check(checks, 'facts_verify', info['ok'], info['reason'])
    return info, extracted


def _cross_checks(workspace, manifest, facts, checks):
    """Compare the commitments shared by three verified inputs."""
    ws_journal, m_journal, f_journal = (
        workspace['journal'], manifest['journal'], facts['journal'])
    cut = facts['cut']
    _check(checks, 'journal_content',
           canonical_bytes(ws_journal) == canonical_bytes(m_journal)
           == canonical_bytes(f_journal),
           'CROSS_JOURNAL_CONTENT_MISMATCH',
           {'workspace': sha256_hex(ws_journal), 'manifest': sha256_hex(m_journal),
            'facts': sha256_hex(f_journal)})
    try:
        replayed = CreditMachine.restore(
            copy.deepcopy(m_journal), FixtureViews()).state_digest()
    except Exception:
        _check(checks, 'f04_commitment', False, 'CROSS_JOURNAL_REPLAY_FAILED')
        f04_matched = False
    else:
        f04_matched = True
        if not (workspace['state_digest'] == replayed == cut['state_digest']):
            _check(checks, 'f04_commitment', False, 'CROSS_STATE_DIGEST_MISMATCH',
                   {'workspace': workspace['state_digest'], 'manifest_replay': replayed,
                    'facts': cut['state_digest']})
            f04_matched = False
        elif not (len(ws_journal) == len(m_journal) == len(f_journal)
                  == cut['journal_length']):
            _check(checks, 'f04_commitment', False, 'CROSS_JOURNAL_LENGTH_MISMATCH',
                   {'workspace': len(ws_journal), 'manifest': len(m_journal),
                    'facts': len(f_journal), 'cut': cut['journal_length']})
            f04_matched = False
    if f04_matched:
        _check(checks, 'f04_commitment', True, None,
               {'state_digest': cut['state_digest'],
                'journal_length': cut['journal_length']})
    presence = (bool(workspace['overlay_journal']),
                bool(manifest['overlay_journal']),
                'overlay_state_digest' in cut)
    _check(checks, 'overlay_presence',
           presence[0] == presence[1] == presence[2],
           'CROSS_OVERLAY_PRESENCE_MISMATCH',
           {'workspace': presence[0], 'manifest': presence[1], 'facts': presence[2]})
    present = all(presence)
    for name, content_reason, digest_reason in (
            ('overlay_content', 'CROSS_OVERLAY_CONTENT_MISMATCH', 'CROSS_OVERLAY_COUNT_MISMATCH'),
            ('overlay_commitment', 'CROSS_OVERLAY_DIGEST_MISMATCH', None)):
        if not presence[0] == presence[1] == presence[2]:
            _check(checks, name, None)
            continue
        if not present:
            _check(checks, name, True, None, {'empty': True})
            continue
        if name == 'overlay_content':
            if not (canonical_bytes(workspace['overlay_journal'])
                    == canonical_bytes(manifest['overlay_journal'])
                    == canonical_bytes(facts['overlay_journal'])):
                _check(checks, name, False, content_reason,
                       {'workspace': sha256_hex(workspace['overlay_journal']),
                        'manifest': sha256_hex(manifest['overlay_journal']),
                        'facts': sha256_hex(facts['overlay_journal'])})
            elif cut.get('overlay_entry_count') != len(manifest['overlay_journal']):
                _check(checks, name, False, digest_reason,
                       {'cut': cut.get('overlay_entry_count'),
                        'entries': len(manifest['overlay_journal'])})
            else:
                _check(checks, name, True, None,
                       {'entry_count': len(manifest['overlay_journal'])})
        else:
            digests = (workspace['overlay_digest'], manifest['overlay_digest'],
                       cut.get('overlay_state_digest'))
            _check(checks, name, digests[0] == digests[1] == digests[2],
                   content_reason,
                   {'workspace': digests[0], 'manifest': digests[1], 'facts': digests[2]})
    rows_digest = sha256_hex(manifest['fixture_rows'])
    _check(checks, 'fixtures_commitment',
           manifest['fixtures_digest'] == rows_digest == cut['fixtures_digest'],
           'CROSS_FIXTURES_MISMATCH',
           {'manifest': manifest['fixtures_digest'], 'manifest_rows': rows_digest,
            'facts': cut['fixtures_digest']})


def _commitments(checks, facts):
    """Shared values only where the matching check MATCHED; else null."""
    status = {row['id']: row['status'] for row in checks}
    cut = facts['cut'] if facts is not None else {}
    present = bool(cut.get('overlay_entry_count')) if 'overlay_state_digest' in cut else False
    return {
        'state_digest': cut.get('state_digest') if status.get('f04_commitment') == 'MATCHED' else None,
        'journal_length': cut.get('journal_length') if status.get('f04_commitment') == 'MATCHED' else None,
        'overlay_present': present if status.get('overlay_presence') == 'MATCHED' else None,
        'overlay_state_digest': (cut.get('overlay_state_digest')
                                 if status.get('overlay_commitment') == 'MATCHED' and present else None),
        'overlay_entry_count': (cut.get('overlay_entry_count')
                                if status.get('overlay_content') == 'MATCHED' and present else None),
        'fixtures_digest': (cut.get('fixtures_digest')
                            if status.get('fixtures_commitment') == 'MATCHED' else None),
    }


def crosscut(workspace_file, manifest_file, facts_dir, *,
             key=None, key_error=None, keyset=None, keyset_error=None):
    """Verify three explicit artifacts and compare their shared commitments.

    `key`/`key_error` and `keyset`/`keyset_error` mirror
    `verify.verify_path`: DEV_ONLY integrity material for the manifest
    signature only. No input is locked, written or repaired.
    """
    checks = []
    workspace_info, workspace = _workspace_input(workspace_file, checks)
    manifest_info, manifest = _manifest_input(
        manifest_file, checks, key=key, key_error=key_error,
        keyset=keyset, keyset_error=keyset_error)
    facts_info, facts = _facts_input(facts_dir, checks)
    if workspace is not None and manifest is not None and facts is not None:
        _cross_checks(workspace, manifest, facts, checks)
    else:
        for name in CROSS_CHECKS:
            _check(checks, name, None)
    ok = all(row['status'] == 'MATCHED' for row in checks)
    reason = next((row['reason'] for row in checks if row['status'] == 'MISMATCH'), None)
    return {
        'ok': ok,
        'reason': reason,
        'format': FORMAT,
        'mode': MODE,
        'label': 'SIMULATED',
        'diagnostic': 'LOCAL_ONLY',
        'inputs': {
            'workspace': workspace_info,
            'manifest': manifest_info,
            'facts': facts_info,
        },
        'checks': checks,
        'commitments': _commitments(checks, facts),
        'lock_taken': False,
        'writes': False,
        'workspace_mutated': False,
        'repair': 'NOT_IMPLEMENTED',
        'funds_executed': False,
        'authentication': 'NOT_BOUND',
        'source_cut': 'NOT_BOUND',
        'common_ownership': 'NOT_BOUND',
        'wholesale_replacement': 'NOT_DETECTABLE',
        'stage7_authenticated_export': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=(
        'Verify an explicit workspace file, export manifest and facts directory '
        'with the existing offline verifiers, then compare their shared F04 '
        'journal, overlay and fixture commitments. Deterministic local '
        'consistency evidence only: no locks, writes or repair; not source '
        'authentication; wholesale replacement by a consistent alternative '
        'book is NOT_DETECTABLE.'))
    parser.add_argument('--workspace', required=True,
                        help='Explicit workspace.json file. Read once, no lock.')
    parser.add_argument('--manifest', required=True,
                        help='Export manifest JSON file.')
    parser.add_argument('--facts', required=True,
                        help='Directory of canonical page-*.json facts files.')
    keys = parser.add_mutually_exclusive_group()
    keys.add_argument('--key-file', default=None,
                      help='DEV_ONLY HMAC key for the manifest signature. Integrity only.')
    keys.add_argument('--keyset-file', default=None,
                      help='Pinned DEV_ONLY local keyset for the manifest signature. Integrity only.')
    args = parser.parse_args(argv)
    key = key_error = None
    if args.key_file is not None:
        try:
            key = load_dev_key(args.key_file, create=False)
        except ExportError as exc:
            key_error = exc.code
    keyset = keyset_error = None
    if args.keyset_file is not None:
        try:
            keyset = load_dev_keyset(args.keyset_file)
        except ExportError as exc:
            keyset_error = exc.code
    report = crosscut(args.workspace, args.manifest, args.facts,
                      key=key, key_error=key_error,
                      keyset=keyset, keyset_error=keyset_error)
    sys.stdout.buffer.write(canonical_bytes(report) + b'\n')
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
