"""Content-addressed export manifest and the SignaturePort seam.

This is a local diagnostic. It is not stage7 authenticated export. There is
no external key, cross-service cursor, watermark, or retention policy.
`SignaturePort` is the adoption seam: `UnsignedSigner` leaves the signature
NOT_BOUND, and `DevHmacSigner` is an opt-in per-workspace HMAC. A shared HMAC
key is integrity only, not authentication. The key is labeled DEV_ONLY, created
mode 0600, and is never placed in a manifest, response, or log.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import stat
from abc import ABC, abstractmethod
from pathlib import Path

from capital.store import canonical_bytes

FORMAT = 'KIX_CAPITAL_EXPORT_MANIFEST_V2'
SECTION_IDS = (
    'journal',
    'receipts',
    'projection',
    'reconciliation',
    'statement',
    'fixtures',
    'source_pin',
)
PART_TAGS = {
    'journal': 'journalpart',
    'receipts': 'receiptspart',
    'projection': 'projectionpart',
    'reconciliation': 'reconciliationpart',
    'statement': 'statementpart',
    'fixtures': 'fixturespart',
    'source_pin': 'sourcepinpart',
}
VOLATILE_KEYS = frozenset({
    'instance_id',
    'created_at',
    'saved_at',
    'timestamp',
    'timestamps',
})
NOT_BOUND_FIELDS = (
    ('cursor', '교차 서비스 cursor는 연결되지 않았습니다.'),
    ('watermark', 'watermark는 연결되지 않았습니다.'),
    ('source_cut', '인증된 source cut이 없습니다.'),
    ('external_key', '외부 서명 키는 연결되지 않았습니다.'),
    ('retention_policy', '보존 정책은 정해지지 않았습니다.'),
    ('authentication', 'stage7 인증 export가 아닙니다. SignaturePort는 채택 경계입니다.'),
)
NOTE = (
    'Local content-addressed manifest. Not stage7 authenticated export. '
    'No external key, cross-service cursor, watermark, or retention policy. '
    'SignaturePort is the adoption seam. A shared HMAC key is integrity only, not authentication.'
)
DEV_KEY_NAME = 'export-dev.key'
_DEV_PREFIX = b'DEV_ONLY\n'
_KEY_LEN = 32


class ExportError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class SignerConfigError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def sha256_hex(value) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def strip_volatile(value):
    """Drop instance id and timestamp keys at every depth. Other keys stay."""
    if type(value) is dict:
        return {
            key: strip_volatile(item)
            for key, item in value.items()
            if key not in VOLATILE_KEYS
        }
    if type(value) is list:
        return [strip_volatile(item) for item in value]
    return value


def content_material(manifest):
    """Bytes covered by content_digest. Excludes the digest, the signature, instance_id, and timestamps."""
    if type(manifest) is not dict:
        raise ExportError('MANIFEST_SHAPE')
    covered = {
        key: value for key, value in manifest.items()
        if key not in {'content_digest', 'signature'}
    }
    return strip_volatile(covered)


def content_digest(manifest) -> str:
    return sha256_hex(content_material(manifest))


def manifest_status(reconciliation_status, workspace_status):
    """INCOMPLETE unless reconciliation is clean and the workspace is readable.

    A local COMPLETE status is section coverage on a matched book. It is not
    stage7 completeness and it is never reported when either check failed.
    """
    reasons = []
    if workspace_status != 'ACTIVE':
        reasons.append(f'WORKSPACE_NOT_ACTIVE:{workspace_status}')
    if reconciliation_status != 'MATCHED':
        reasons.append('RECONCILIATION_NOT_CLEAN')
    if reasons:
        return 'INCOMPLETE', reasons
    return 'COMPLETE', []


def _seal_section(name, body):
    if type(body) is not dict or 'part_tag' in body:
        raise ExportError('SECTION_BODY')
    sealed = {'part_tag': PART_TAGS[name], **body}
    return {'sha256': sha256_hex(sealed), 'body': sealed}


def build_manifest(*, sections, instance_id, signer, status, incomplete_reasons):
    """Hash each section and sign the content digest. Does not write or import."""
    reasons = list(incomplete_reasons)
    if status not in {'COMPLETE', 'INCOMPLETE'}:
        raise ExportError('MANIFEST_STATUS')
    if status == 'COMPLETE' and reasons:
        raise ExportError('MANIFEST_STATUS')
    if status == 'INCOMPLETE' and not reasons:
        raise ExportError('MANIFEST_STATUS')
    if set(sections) != set(SECTION_IDS):
        raise ExportError('SECTION_SET')
    sealed = {name: _seal_section(name, sections[name]) for name in SECTION_IDS}
    manifest = {
        'format': FORMAT,
        'label': 'SIMULATED',
        'diagnostic': 'READ_ONLY',
        'status': status,
        'incomplete_reasons': reasons,
        'instance_id': instance_id,
        'cursor': None,
        'watermark': None,
        'source_cut': None,
        'timestamps': None,
        'not_bound': [
            {'id': gap_id, 'value': None, 'status': 'NOT_BOUND', 'meaning': meaning}
            for gap_id, meaning in NOT_BOUND_FIELDS
        ],
        'external_key': 'NOT_BOUND',
        'retention_policy': 'NOT_BOUND',
        'authentication': 'NOT_BOUND',
        'stage7_authenticated_export': False,
        'signature_port': 'SignaturePort',
        'funds_executed': False,
        'import_endpoint': 'NOT_PROVIDED',
        'resume_endpoint': 'NOT_PROVIDED',
        'sections': sealed,
        'note': NOTE,
    }
    manifest['content_digest'] = content_digest(manifest)
    signature = signer.sign(manifest['content_digest'])
    if type(signature) is not dict or signature.get('port') != 'SignaturePort':
        raise ExportError('SIGNATURE_SHAPE')
    if signature.get('authentication') != 'NOT_BOUND' or 'key' in signature:
        raise ExportError('SIGNATURE_SHAPE')
    value = signature.get('value')
    if value is not None and type(value) is not str:
        raise ExportError('SIGNATURE_SHAPE')
    manifest['signature'] = signature
    return manifest


class SignaturePort(ABC):
    """Adoption seam for a later stage7 authenticator. This node does not authenticate."""

    @abstractmethod
    def sign(self, content_digest: str) -> dict:
        """Return a signature block. The block must not contain key material."""


class UnsignedSigner(SignaturePort):
    """Default signer. The signature stays NOT_BOUND."""

    def sign(self, content_digest: str) -> dict:
        return {
            'port': 'SignaturePort',
            'alg': 'UNSIGNED',
            'status': 'NOT_BOUND',
            'label': 'NOT_BOUND',
            'purpose': 'NOT_BOUND',
            'authentication': 'NOT_BOUND',
            'value': None,
        }

    def __repr__(self):
        return 'UnsignedSigner(status=NOT_BOUND)'


def load_dev_key(path, *, create=False) -> bytes:
    """Read a DEV_ONLY key. Create it mode 0600 only when `create` is set.

    The returned bytes are for the caller to HMAC with. Callers must not put
    them in a response, a manifest, or a log line.
    """
    path = Path(path)
    if create:
        try:
            return _create_dev_key(path)
        except FileExistsError:
            pass
    return _read_dev_key(path)


def _create_dev_key(path: Path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, 0o600)
    key = secrets.token_bytes(_KEY_LEN)
    try:
        os.fchmod(fd, 0o600)
        payload = _DEV_PREFIX + key
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError('short write')
            view = view[written:]
        os.fsync(fd)
    except Exception:
        os.close(fd)
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        raise
    os.close(fd)
    loaded = _read_dev_key(path)
    if not hmac.compare_digest(loaded, key):
        raise ExportError('SIGNATURE_KEY_UNREADABLE')
    return key


def _read_dev_key(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ExportError('SIGNATURE_KEY_UNREADABLE') from exc
    try:
        info = os.fstat(fd)
        mode = stat.S_IMODE(info.st_mode)
        if not stat.S_ISREG(info.st_mode) or mode != 0o600:
            raise ExportError('SIGNATURE_KEY_MODE')
        raw = os.read(fd, len(_DEV_PREFIX) + _KEY_LEN + 1)
    except ExportError:
        raise
    except OSError as exc:
        raise ExportError('SIGNATURE_KEY_UNREADABLE') from exc
    finally:
        os.close(fd)
    if len(raw) != len(_DEV_PREFIX) + _KEY_LEN or not raw.startswith(_DEV_PREFIX):
        raise ExportError('SIGNATURE_KEY_UNREADABLE')
    return raw[len(_DEV_PREFIX):]


class DevHmacSigner(SignaturePort):
    """Opt-in per-workspace HMAC. DEV_ONLY integrity, not authentication."""

    def __init__(self, directory):
        directory = Path(directory)
        if directory.exists() and not directory.is_dir():
            raise ExportError('SIGNATURE_KEY_UNREADABLE')
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / DEV_KEY_NAME
        self._key = load_dev_key(self.path, create=True)

    def sign(self, content_digest: str) -> dict:
        if type(content_digest) is not str or len(content_digest) != 64:
            raise ExportError('CONTENT_DIGEST')
        mac = hmac.new(self._key, content_digest.encode('ascii'), hashlib.sha256).hexdigest()
        return {
            'port': 'SignaturePort',
            'alg': 'DEV_HMAC_SHA256',
            'status': 'DEV_ONLY',
            'label': 'DEV_ONLY',
            'purpose': 'INTEGRITY_ONLY',
            'authentication': 'NOT_BOUND',
            'value': mac,
        }

    def __repr__(self):
        return 'DevHmacSigner(label=DEV_ONLY, purpose=INTEGRITY_ONLY, key=REDACTED)'


def build_signer(workspace, dev_hmac):
    """Default is unsigned. `--dev-hmac` needs a workspace directory for the key file."""
    if not dev_hmac:
        return UnsignedSigner()
    if not workspace:
        raise SignerConfigError('DEV_HMAC_REQUIRES_WORKSPACE')
    return DevHmacSigner(workspace)
