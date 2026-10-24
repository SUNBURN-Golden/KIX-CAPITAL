import hashlib
import hmac
import os
from pathlib import Path
import secrets
import stat

from capital.export import ExportError, SignerConfigError, SignaturePort, build_signer as legacy_build_signer
from capital.store import canonical_bytes
from capital.strict_json import loads

DEV_KEYSET_NAME = 'export-dev-keyset.json'
DEV_KEYSET_FORMAT = 'KIX_CAPITAL_DEV_KEYSET_V1'
DEV_KEYSET_ALG = 'DEV_KEYSET_HMAC_SHA256'
_KEYSET_MAX = 65536


def validate_dev_keyset(value):
    invalid = ExportError('SIGNATURE_KEYSET_INVALID')
    if type(value) is not dict or set(value) != {'format', 'label', 'active_kid', 'keys'}:
        raise invalid
    if value['format'] != DEV_KEYSET_FORMAT or value['label'] != 'DEV_ONLY':
        raise invalid
    if type(value['keys']) is not list or not value['keys'] or len(value['keys']) > 100:
        raise invalid
    seen = {}
    for entry in value['keys']:
        if type(entry) is not dict or set(entry) != {'kid', 'alg', 'status', 'key_hex'}:
            raise invalid
        kid = entry['kid']
        if type(kid) is not str or not 1 <= len(kid) <= 128 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._' for c in kid):
            raise invalid
        if kid in seen or entry['alg'] != DEV_KEYSET_ALG or entry['status'] not in ('ACTIVE', 'RETIRED'):
            raise invalid
        key = entry['key_hex']
        if type(key) is not str or len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
            raise invalid
        seen[kid] = entry
    active = value['active_kid']
    if type(active) is not str or active not in seen or seen[active]['status'] != 'ACTIVE':
        raise invalid
    return value


def load_dev_keyset(path, *, create=False):
    path = Path(path)
    if create:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        except FileExistsError:
            pass
        except OSError:
            raise ExportError('SIGNATURE_KEYSET_UNREADABLE') from None
        else:
            try:
                os.fchmod(fd, 0o600)
                value = {'format': DEV_KEYSET_FORMAT, 'label': 'DEV_ONLY', 'active_kid': 'kid-1',
                         'keys': [{'kid': 'kid-1', 'alg': DEV_KEYSET_ALG, 'status': 'ACTIVE',
                                   'key_hex': secrets.token_hex(32)}]}
                view = memoryview(canonical_bytes(value) + b'\n')
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise OSError()
                    view = view[written:]
                os.fsync(fd)
            except OSError:
                raise ExportError('SIGNATURE_KEYSET_UNREADABLE') from None
            finally:
                os.close(fd)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0))
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
                raise ExportError('SIGNATURE_KEYSET_MODE')
            raw = bytearray()
            while len(raw) <= _KEYSET_MAX:
                part = os.read(fd, _KEYSET_MAX + 1 - len(raw))
                if not part:
                    break
                raw.extend(part)
        finally:
            os.close(fd)
    except OSError:
        raise ExportError('SIGNATURE_KEYSET_UNREADABLE') from None
    if len(raw) > _KEYSET_MAX:
        raise ExportError('SIGNATURE_KEYSET_INVALID')
    try:
        return validate_dev_keyset(loads(bytes(raw)))
    except (ValueError, UnicodeError, RecursionError):
        raise ExportError('SIGNATURE_KEYSET_INVALID') from None


def keyset_mac(entry, digest):
    material = {'alg': DEV_KEYSET_ALG, 'kid': entry['kid'], 'content_digest': digest}
    return hmac.new(bytes.fromhex(entry['key_hex']), canonical_bytes(material), hashlib.sha256).hexdigest()


class DevKeysetSigner(SignaturePort):
    def __init__(self, directory):
        self.path = Path(directory) / DEV_KEYSET_NAME
        keyset = load_dev_keyset(self.path, create=True)
        self._entry = next(entry for entry in keyset['keys'] if entry['kid'] == keyset['active_kid'])

    def sign(self, content_digest: str) -> dict:
        if type(content_digest) is not str or len(content_digest) != 64 or any(c not in '0123456789abcdef' for c in content_digest):
            raise ExportError('CONTENT_DIGEST')
        return {'port': 'SignaturePort', 'alg': DEV_KEYSET_ALG, 'kid': self._entry['kid'],
                'status': 'DEV_ONLY', 'label': 'DEV_ONLY', 'purpose': 'INTEGRITY_ONLY',
                'authentication': 'NOT_BOUND', 'value': keyset_mac(self._entry, content_digest)}

    def __repr__(self):
        return 'DevKeysetSigner(label=DEV_ONLY, purpose=INTEGRITY_ONLY, key=REDACTED)'


def build_signer(workspace, dev_hmac=False, dev_keyset=False):
    if dev_hmac and dev_keyset:
        raise SignerConfigError('DEV_SIGNER_CONFLICT')
    if not dev_keyset:
        return legacy_build_signer(workspace, dev_hmac)
    if not workspace:
        raise SignerConfigError('DEV_KEYSET_REQUIRES_WORKSPACE')
    return DevKeysetSigner(workspace)
