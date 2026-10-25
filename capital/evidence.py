"""Offline audit evidence pack and its verifier.

`scripts/evidence_pack.py --workspace DIR --out DIR` composes one JSON document
(format KIX_CAPITAL_EVIDENCE_PACK_V1) over DIR/workspace.json bytes: the export
manifest, the offline workspace audit, the reconciliation report, the decision
summary, and the authorization matrix — each sealed as `{'part_tag', 'document'}`
under a SHA-256, all under one `content_digest`. Volatile fields (instance ids,
timestamps, the saved_at envelope stamp) stay out of `content_digest` and the
event log is never packaged, so two runs on the same workspace emit identical
bytes.

`--verify FILE` re-checks every section hash, the volatile block hash, and the
content digest fully offline, then re-verifies the embedded export manifest.
The first failing part supplies the reason; later parts stay NOT_CHECKED.

This is a local diagnostic. Remote attestation, stage7 authenticated export,
and retention enforcement are out of scope and named in `not_bound`. The writer
reads only workspace.json: it never opens a DEV_ONLY HMAC key, never takes the
workspace lock, and never writes the workspace directory. The embedded
manifest's signature stays NOT_BOUND.
"""
from __future__ import annotations

import copy
import hmac
import importlib.util
import json
from pathlib import Path

from capital import audit as audit_module
from capital import store
from capital.decisions import default_root
from capital.export import sha256_hex, strip_volatile
from capital.service import CapitalService
from capital.verify import loads, verify_manifest

PACK_FORMAT = 'KIX_CAPITAL_EVIDENCE_PACK_V1'
PACK_FILE = 'evidence-pack.json'
PACK_SECTION_IDS = (
    'export_manifest',
    'workspace_audit',
    'reconciliation',
    'decisions',
    'auth_matrix',
)
# '<id>block' keeps these tags distinct from the embedded manifest's own
# '<name>part' section tags, so one byte flip can be pinned to its own section.
PACK_PART_TAGS = {
    'export_manifest': 'exportmanifestblock',
    'workspace_audit': 'workspaceauditblock',
    'reconciliation': 'reconciliationblock',
    'decisions': 'decisionsblock',
    'auth_matrix': 'authmatrixblock',
}
OFFLINE_INSTANCE = 'evidence-pack-offline'
AUTH_MATRIX_FORMAT = 'KIX_CAPITAL_AUTH_MATRIX_V1'
AUTH_MATRIX_NOT_BOUND = 'auth matrix source not bound'
NOT_BOUND_ITEMS = (
    ('remote_attestation', 'NOT_BOUND',
     'Remote attestation is out of scope. The pack is local bytes; nothing vouches for it remotely.'),
    ('stage7_authenticated_export', 'NOT_BOUND',
     'Not stage7 authenticated export. The embedded manifest is verified by hash; its signature stays NOT_BOUND.'),
    ('retention_enforcement', 'NOT_BOUND',
     'Retention enforcement is out of scope. The pack retains and deletes nothing.'),
    ('event_log', 'EXCLUDED',
     'The JSONL event log is not packaged (EXCLUDED_NOT_PACKAGED).'),
)
_HEX = frozenset('0123456789abcdef')


class PackError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class _DocumentStorage(store.StoragePort):
    """In-memory port over the workspace envelope. save() must never run."""

    def __init__(self, document):
        self._document = copy.deepcopy(document)

    def load(self):
        return store.verify_document(copy.deepcopy(self._document))

    def save(self, document):
        raise AssertionError('evidence pack does not write')


def read_workspace_document(directory):
    """Strict-parse DIR/workspace.json bytes, or None. No lock, no write."""
    try:
        raw = (Path(directory) / store.FILE_NAME).read_bytes()
        return loads(raw)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, RecursionError):
        return None


def offline_service(document):
    """Restore the workspace document into a read-only service.

    The instance id is fixed before any surface call so pack bytes are
    deterministic. The signer stays the default UnsignedSigner: a DEV_ONLY
    HMAC key file is never read or copied into the pack.
    """
    service = CapitalService(_DocumentStorage(document))
    service.instance_id = OFFLINE_INSTANCE
    service.storage.writer_instance = OFFLINE_INSTANCE
    return service


def _load_module(name, path):
    """Load a scripts/ module by file path; None when absent or unloadable."""
    path = Path(path)
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (OSError, ImportError, SyntaxError):
        return None
    return module


def _auth_matrix_body(root):
    """The SIMULATED route-by-role table, or a NOT_BOUND body when unbound.

    scripts/ and tests/ are absent from the zipapp, so that run reports
    NOT_BOUND instead of failing.
    """
    module = _load_module('capital_auth_matrix', Path(root) / 'scripts' / 'auth_matrix.py')
    if module is not None:
        try:
            table = module.build()
        except Exception:
            table = None
        if type(table) is dict and table.get('format') == AUTH_MATRIX_FORMAT:
            return table
    try:
        table = loads((Path(root) / 'tests' / 'auth_matrix.json').read_bytes())
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, RecursionError):
        table = None
    if type(table) is dict and table.get('format') == AUTH_MATRIX_FORMAT:
        return table
    return {'label': 'SIMULATED', 'status': 'NOT_BOUND', 'reason': AUTH_MATRIX_NOT_BOUND}


def section_bodies(workspace_dir, document, *, root=None, workspace_label=None):
    """The five surface bodies. Read-only; degrades honestly on failure.

    When the workspace audit fails the audit body carries the failure and the
    service-derived sections are UNAVAILABLE rather than silently rebuilt.
    """
    root = default_root() if root is None else Path(root)
    audit = audit_module.audit_workspace(workspace_dir)
    if workspace_label is not None:
        audit = {**audit, 'workspace': workspace_label}
    bodies = {'workspace_audit': audit}
    if audit['ok'] and type(document) is dict:
        service = offline_service(document)
        bodies['export_manifest'] = service.export_manifest()
        bodies['reconciliation'] = service.reconciliation()
        bodies['decisions'] = service.decisions()
    else:
        for name in ('export_manifest', 'reconciliation', 'decisions'):
            bodies[name] = {
                'label': 'SIMULATED',
                'status': 'UNAVAILABLE',
                'reason': audit['reason'] or 'WORKSPACE_UNREADABLE',
            }
    bodies['auth_matrix'] = _auth_matrix_body(root)
    return bodies


def pack_material(pack):
    """Bytes covered by content_digest: minus the digest and the volatile block.

    Volatile keys are stripped at every depth and each section hash is
    recomputed over the stripped body — the same semantics as
    export.content_material — so process id and clock fields cannot move the
    digest while staying visible in the stored section bytes.
    """
    if type(pack) is not dict:
        raise PackError('PACK_SHAPE')
    covered = {
        key: value for key, value in pack.items()
        if key not in {'content_digest', 'volatile'}
    }
    covered = strip_volatile(covered)
    sections = covered.get('sections')
    if type(sections) is not dict:
        return covered
    stabilized = {}
    for name, section in sections.items():
        if type(section) is not dict or 'body' not in section:
            stabilized[name] = section
            continue
        rewritten = {key: value for key, value in section.items() if key != 'sha256'}
        rewritten['sha256'] = sha256_hex(section['body'])
        stabilized[name] = rewritten
    return {**covered, 'sections': stabilized}


def content_digest(pack) -> str:
    return sha256_hex(pack_material(pack))


def _seal(name, body):
    """Wrap the surface body so an inner document's own digests stay intact."""
    if type(body) is not dict:
        raise PackError('SECTION_BODY')
    sealed = {'part_tag': PACK_PART_TAGS[name], 'document': body}
    return {'sha256': sha256_hex(sealed), 'body': sealed}


def build_pack(*, sections, volatile_body, status, incomplete_reasons):
    """Hash each section and the volatile block. Does not write, sign, or import."""
    reasons = list(incomplete_reasons)
    if status not in {'COMPLETE', 'INCOMPLETE'}:
        raise PackError('PACK_STATUS')
    if status == 'COMPLETE' and reasons:
        raise PackError('PACK_STATUS')
    if status == 'INCOMPLETE' and not reasons:
        raise PackError('PACK_STATUS')
    if set(sections) != set(PACK_SECTION_IDS):
        raise PackError('SECTION_SET')
    pack = {
        'format': PACK_FORMAT,
        'label': 'SIMULATED',
        'diagnostic': 'READ_ONLY',
        'locality': 'LOCAL_ONLY',
        'status': status,
        'incomplete_reasons': reasons,
        'sections': {name: _seal(name, sections[name]) for name in PACK_SECTION_IDS},
        'volatile': {'sha256': sha256_hex(volatile_body), 'body': volatile_body},
        'not_bound': [
            {'id': item_id, 'status': item_status, 'meaning': meaning}
            for item_id, item_status, meaning in NOT_BOUND_ITEMS
        ],
        'authentication': 'NOT_BOUND',
        'signature': 'NOT_BOUND',
        'funds_executed': False,
    }
    pack['content_digest'] = content_digest(pack)
    return pack


def pack_document(workspace_dir, *, root=None, workspace_label=None):
    """Compose and seal the pack over DIR/workspace.json. Never writes.

    `workspace_label` replaces the recorded path for pinned corpora, where the
    generating directory differs between runs.
    """
    document = read_workspace_document(workspace_dir)
    bodies = section_bodies(
        workspace_dir, document, root=root, workspace_label=workspace_label)
    audit = bodies['workspace_audit']
    if audit['ok']:
        status, reasons = 'COMPLETE', []
    else:
        status = 'INCOMPLETE'
        reasons = [f"WORKSPACE_AUDIT:{audit['reason']}"]
    if type(document) is dict:
        saved_by, saved_at = document.get('saved_by_instance'), document.get('saved_at')
    else:
        saved_by = saved_at = None
    volatile_body = {
        'workspace': workspace_label if workspace_label is not None else str(workspace_dir),
        'saved_by_instance': saved_by,
        'saved_at': saved_at,
        'producer_instance': OFFLINE_INSTANCE,
        'event_log': 'EXCLUDED_NOT_PACKAGED',
    }
    return build_pack(
        sections=bodies, volatile_body=volatile_body,
        status=status, incomplete_reasons=reasons)


def dump(pack) -> bytes:
    return store.canonical_bytes(pack) + b'\n'


def _hex_equal(expected, actual):
    if type(expected) is not str or type(actual) is not str:
        return False
    if len(expected) != len(actual) or len(expected) != 64:
        return False
    if any(char not in _HEX for char in expected) or any(char not in _HEX for char in actual):
        return False
    return hmac.compare_digest(expected, actual)


def _report(*, ok, reason, sections, volatile, digest_status, embedded, pack_status):
    return {
        'ok': ok,
        'reason': reason,
        'format': PACK_FORMAT,
        'label': 'SIMULATED',
        'diagnostic': 'READ_ONLY',
        'locality': 'LOCAL_ONLY',
        'pack_status': pack_status,
        'sections': sections,
        'volatile': volatile,
        'content_digest': digest_status,
        'embedded_manifest': embedded,
        'authentication': 'NOT_BOUND',
        'remote_attestation': 'NOT_BOUND',
        'funds_executed': False,
    }


def _fail(reason, sections, volatile='NOT_CHECKED', digest_status='NOT_CHECKED',
          embedded='NOT_CHECKED', pack_status=None):
    return _report(
        ok=False, reason=reason, sections=sections, volatile=volatile,
        digest_status=digest_status, embedded=embedded, pack_status=pack_status)


def verify_pack(document):
    """Re-check section hashes, the volatile hash, the digest, the embedded manifest.

    The first failing part supplies the reason; later parts stay NOT_CHECKED
    so a body change is not reported as a digest failure.
    """
    pending = {name: 'NOT_CHECKED' for name in PACK_SECTION_IDS}
    pack_status = document.get('status') if type(document) is dict else None
    if type(document) is not dict or document.get('format') != PACK_FORMAT:
        return _fail('PACK_SHAPE', pending, pack_status=pack_status)
    sections = document.get('sections')
    if type(sections) is not dict or set(sections) != set(PACK_SECTION_IDS):
        return _fail('SECTION_SET', pending, pack_status=pack_status)
    for name in PACK_SECTION_IDS:
        section = sections.get(name)
        if type(section) is not dict or set(section) != {'sha256', 'body'}:
            pending[name] = 'SECTION_SHAPE'
            return _fail(f'SECTION_HASH_MISMATCH:{name}', pending, pack_status=pack_status)
        if not _hex_equal(section.get('sha256'), sha256_hex(section['body'])):
            pending[name] = 'SECTION_HASH_MISMATCH'
            return _fail(f'SECTION_HASH_MISMATCH:{name}', pending, pack_status=pack_status)
        pending[name] = 'MATCHED'
    volatile = document.get('volatile')
    if type(volatile) is not dict or set(volatile) != {'sha256', 'body'}:
        return _fail(
            'VOLATILE_HASH_MISMATCH', pending, volatile='VOLATILE_SHAPE',
            pack_status=pack_status)
    if not _hex_equal(volatile.get('sha256'), sha256_hex(volatile['body'])):
        return _fail(
            'VOLATILE_HASH_MISMATCH', pending, volatile='VOLATILE_HASH_MISMATCH',
            pack_status=pack_status)
    try:
        expected = content_digest(document)
    except PackError:
        return _fail(
            'CONTENT_DIGEST_MISMATCH', pending, volatile='MATCHED',
            digest_status='CONTENT_DIGEST_MISMATCH', pack_status=pack_status)
    if not _hex_equal(document.get('content_digest'), expected):
        return _fail(
            'CONTENT_DIGEST_MISMATCH', pending, volatile='MATCHED',
            digest_status='CONTENT_DIGEST_MISMATCH', pack_status=pack_status)
    body = sections['export_manifest']['body']
    embedded = body.get('document') if type(body) is dict else None
    if type(embedded) is not dict or embedded.get('status') == 'UNAVAILABLE':
        embedded_status = 'NOT_APPLICABLE'
    else:
        report = verify_manifest(embedded)
        embedded_status = 'MATCHED' if report['ok'] else 'MISMATCH'
        if not report['ok']:
            return _fail(
                f"EMBEDDED_MANIFEST:{report['reason']}", pending, volatile='MATCHED',
                digest_status='MATCHED', embedded=embedded_status, pack_status=pack_status)
    return _report(
        ok=True, reason=None, sections=pending, volatile='MATCHED',
        digest_status='MATCHED', embedded=embedded_status, pack_status=pack_status)


def verify_path(path):
    """Read FILE bytes strictly and verify. PACK_UNREADABLE when it cannot parse."""
    try:
        raw = Path(path).read_bytes()
        document = loads(raw)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, RecursionError):
        pending = {name: 'NOT_CHECKED' for name in PACK_SECTION_IDS}
        return _fail('PACK_UNREADABLE', pending)
    return verify_pack(document)
