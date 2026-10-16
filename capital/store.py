"""Local development storage seam. Not a database and not stage5 durable transactions."""
from __future__ import annotations

import copy
import datetime
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path

FORMAT = 'KIX_CAPITAL_LOCAL_WORKSPACE_V1'
# `format` stays the document-type tag. Schema evolution is `envelope_version`, which is
# absent on a legacy v1 record and exactly 2 on a v2 record (docs/decisions/CAPITAL_OVERLAY_STATE.md).
ENVELOPE_KEYS = frozenset({'format', 'payload', 'payload_sha256', 'saved_by_instance', 'saved_at'})
ENVELOPE_KEYS_V2 = ENVELOPE_KEYS | {'envelope_version', 'overlay'}
ENVELOPE_VERSION = 2
OVERLAY_SECTION_KEYS = frozenset({'overlay_schema', 'journal', 'overlay_state', 'section_sha256'})
FILE_NAME = 'workspace.json'
LOCK_NAME = 'workspace.json.lock'


class WorkspaceError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def _loads(raw):
    if raw.startswith(b'\xef\xbb\xbf') or b'\x00' in raw:
        raise ValueError('rejected encoding')
    text = raw.decode('utf-8')
    return json.loads(text, object_pairs_hook=_strict_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))


def _checksum(payload):
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def section_checksum(section):
    """SHA256 over the canonical overlay section minus `section_sha256` itself."""
    return hashlib.sha256(canonical_bytes({key: value for key, value in section.items()
                                           if key != 'section_sha256'})).hexdigest()


def envelope(writer_instance, payload, overlay=None):
    """Always a v2 record. `overlay=None` writes the empty overlay section."""
    if type(writer_instance) is not str or not writer_instance or len(writer_instance) > 80:
        raise WorkspaceError('WORKSPACE_WRITE_FAILED')
    if type(payload) is not dict:
        raise WorkspaceError('WORKSPACE_WRITE_FAILED')
    if overlay is None:
        # Lazy: overlay imports canonical_bytes from this module.
        from capital import overlay as overlay_module
        overlay = overlay_module.empty_section()
    if type(overlay) is not dict or set(overlay) != OVERLAY_SECTION_KEYS:
        raise WorkspaceError('WORKSPACE_WRITE_FAILED')
    body = copy.deepcopy(payload)
    return {'format': FORMAT, 'envelope_version': ENVELOPE_VERSION, 'payload': body,
            'payload_sha256': _checksum(body), 'overlay': copy.deepcopy(overlay),
            'saved_by_instance': writer_instance,
            'saved_at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')}


def envelope_kind(document):
    """1 for a legacy record, 2 for a v2 record, None for anything else.

    Legacy is `envelope_version` ABSENT with the v1 key set. A present value that is
    not the integer 2 (1, True, "2", null, ...) is never legacy.
    """
    if type(document) is not dict or document.get('format') != FORMAT:
        return None
    if 'envelope_version' not in document:
        return 1 if set(document) == ENVELOPE_KEYS else None
    version = document['envelope_version']
    if type(version) is int and version == ENVELOPE_VERSION and set(document) == ENVELOPE_KEYS_V2:
        return ENVELOPE_VERSION
    return None


def overlay_section(document):
    """The checksum-verified overlay section of a v2 record, or None for a legacy record."""
    return document['overlay'] if envelope_kind(document) == ENVELOPE_VERSION else None


def _verify_section(section):
    if type(section) is not dict or set(section) != OVERLAY_SECTION_KEYS:
        raise WorkspaceError('WORKSPACE_UNREADABLE')
    schema, digest = section['overlay_schema'], section['section_sha256']
    if type(schema) is not int or schema != 1 or type(section['journal']) is not list:
        raise WorkspaceError('WORKSPACE_UNREADABLE')
    if type(section['overlay_state']) is not dict:
        raise WorkspaceError('WORKSPACE_UNREADABLE')
    if type(digest) is not str or len(digest) != 64 or any(char not in '0123456789abcdef' for char in digest):
        raise WorkspaceError('WORKSPACE_UNREADABLE')
    if not hmac.compare_digest(section_checksum(section), digest):
        raise WorkspaceError('WORKSPACE_UNREADABLE')


def verify_document(document):
    """Checksum and envelope shape only. Service restore owns journal and overlay semantics."""
    if envelope_kind(document) is None:
        raise WorkspaceError('WORKSPACE_UNREADABLE')
    payload, digest = document['payload'], document['payload_sha256']
    writer, saved_at = document['saved_by_instance'], document['saved_at']
    if type(payload) is not dict or type(digest) is not str or len(digest) != 64:
        raise WorkspaceError('WORKSPACE_UNREADABLE')
    if any(char not in '0123456789abcdef' for char in digest):
        raise WorkspaceError('WORKSPACE_UNREADABLE')
    if type(writer) is not str or not writer or len(writer) > 80 or type(saved_at) is not str or not saved_at:
        raise WorkspaceError('WORKSPACE_UNREADABLE')
    actual = _checksum(payload)
    if not hmac.compare_digest(actual, digest):
        raise WorkspaceError('WORKSPACE_UNREADABLE')
    if envelope_kind(document) == ENVELOPE_VERSION:
        _verify_section(document['overlay'])
    return document


class StoragePort:
    """load returns a verified envelope, or None when this workspace has never been saved."""
    durable_label = False
    writer_instance = ''
    path = None

    def load(self):
        raise NotImplementedError

    def save(self, document, overlay=None):
        raise NotImplementedError

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
        return False


class InMemoryStorage(StoragePort):
    """Process-local default. The last envelope stays in RAM and is never written."""
    durable_label = False

    def __init__(self):
        self._document = None

    def load(self):
        if self._document is None:
            return None
        return verify_document(copy.deepcopy(self._document))

    def save(self, document, overlay=None):
        self._document = envelope(self.writer_instance, document, overlay)


class UnavailableWorkspace(StoragePort):
    """Lock or create failed. Reads must not invent an empty writable book."""
    durable_label = 'LOCAL_FILE_WORKSPACE'

    def __init__(self, directory, code):
        self.directory = Path(directory)
        self.path = self.directory / FILE_NAME
        self.code = code

    def load(self):
        raise WorkspaceError(self.code)

    def save(self, document, overlay=None):
        raise WorkspaceError(self.code)


class FileWorkspace(StoragePort):
    """One JSON file, exclusive process lock, atomic replace. Development workspace only."""
    durable_label = 'LOCAL_FILE_WORKSPACE'

    def __init__(self, directory, lock_path, lock_fd):
        self.directory = directory
        self.lock_path = lock_path
        self._lock_fd = lock_fd
        self.path = directory / FILE_NAME

    @classmethod
    def open(cls, directory):
        if isinstance(directory, Path):
            directory = Path(directory)
        elif type(directory) is str:
            if not directory.strip():
                raise WorkspaceError('WORKSPACE_UNREADABLE')
            directory = Path(directory)
        else:
            raise WorkspaceError('WORKSPACE_UNREADABLE')
        try:
            directory = directory.resolve()
            if directory.exists() and not directory.is_dir():
                raise WorkspaceError('WORKSPACE_UNREADABLE')
            directory.mkdir(parents=True, exist_ok=True)
            lock_path = directory / LOCK_NAME
            fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        except WorkspaceError:
            raise
        except OSError as exc:
            raise WorkspaceError('WORKSPACE_UNREADABLE') from exc
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(fd)
            raise WorkspaceError('WORKSPACE_LOCKED') from exc
        except OSError as exc:
            os.close(fd)
            raise WorkspaceError('WORKSPACE_UNREADABLE') from exc
        workspace = cls(directory, lock_path, fd)
        try:
            workspace._clear_stale_temps()
        except Exception:
            workspace.close()
            raise
        return workspace

    def load(self):
        if not self.path.exists():
            return None
        if not self.path.is_file():
            raise WorkspaceError('WORKSPACE_UNREADABLE')
        try:
            raw = self.path.read_bytes()
        except OSError as exc:
            raise WorkspaceError('WORKSPACE_UNREADABLE') from exc
        try:
            document = _loads(raw)
        except (UnicodeError, ValueError, json.JSONDecodeError, RecursionError) as exc:
            raise WorkspaceError('WORKSPACE_UNREADABLE') from exc
        return verify_document(document)

    def save(self, document, overlay=None):
        body = canonical_bytes(envelope(self.writer_instance, document, overlay))
        self._atomic_write(body)

    def close(self):
        fd, self._lock_fd = self._lock_fd, None
        if fd is None:
            return
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def _clear_stale_temps(self):
        try:
            children = list(self.directory.iterdir())
        except OSError as exc:
            raise WorkspaceError('WORKSPACE_UNREADABLE') from exc
        for child in children:
            if child.is_file() and child.name.startswith('.workspace.json.') and child.name.endswith('.tmp'):
                try:
                    child.unlink()
                except FileNotFoundError:
                    pass

    def _atomic_write(self, data):
        tmp = self.directory / f'.workspace.json.{os.getpid()}.tmp'
        fd = None
        try:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError('short write')
                view = view[written:]
            os.fsync(fd)
            os.close(fd)
            fd = None
            os.replace(tmp, self.path)
            directory_fd = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as exc:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise WorkspaceError('WORKSPACE_WRITE_FAILED') from exc
