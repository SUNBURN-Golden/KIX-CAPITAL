#!/usr/bin/env python3
"""Build a deterministic local zipapp of the Capital simulation.

The artifact is LOCAL_SIMULATION_ARTIFACT: unsigned, unpublished, and not a
deployment. Same-interpreter rebuilds match; this does not claim cross-platform
byte identity. ZIP_STORED avoids zlib-version drift in the hash.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import zipapp
import zipfile
from pathlib import Path

_VERSION = re.compile(r'\d+\.\d+\.\d+')


class BuildError(RuntimeError):
    pass


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def read_version(path: Path) -> str:
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    except (OSError, SyntaxError) as exc:
        raise BuildError(f'cannot read version from {path}') from exc
    found = None
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if '__version__' not in names:
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            found = node.value.value
    if found is None or _VERSION.fullmatch(found) is None:
        raise BuildError(f'capital version must match {_VERSION.pattern}: {found!r}')
    return found


def _iter_vendor_files(vendor: Path) -> dict[str, bytes]:
    found = {}
    for path in sorted(vendor.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(vendor)
        if '__pycache__' in relative.parts or path.suffix == '.pyc':
            continue
        found[relative.as_posix()] = path.read_bytes()
    return found


def _package_entries(root: Path) -> tuple[str, str, dict[str, bytes]]:
    capital = root / 'capital'
    version = read_version(capital / '__init__.py')
    entries: dict[str, bytes] = {}
    for path in sorted(capital.glob('*.py')):
        entries[f'capital/{path.name}'] = path.read_bytes()
    static = capital / 'static'
    for path in sorted(static.iterdir()):
        if path.is_file() and path.suffix != '.pyc':
            entries[f'capital/static/{path.name}'] = path.read_bytes()

    vendor_files = _iter_vendor_files(capital / 'vendor')
    manifest_bytes = vendor_files.get('manifest.json')
    if manifest_bytes is None:
        raise BuildError('vendor manifest.json missing')
    try:
        manifest = json.loads(manifest_bytes.decode('utf-8'))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BuildError('vendor manifest is not utf-8 json') from exc
    pinned = manifest.get('files')
    commit = manifest.get('commit')
    if type(pinned) is not dict or type(commit) is not str or not commit:
        raise BuildError('vendor manifest missing commit or files')
    found = set(vendor_files) - {'manifest.json'}
    expected = set(pinned)
    if found != expected:
        raise BuildError(
            'vendor file set does not match manifest: '
            f'extra={sorted(found - expected)} missing={sorted(expected - found)}')
    for rel, expected_hash in pinned.items():
        if type(rel) is not str or type(expected_hash) is not str:
            raise BuildError(f'invalid vendor manifest entry: {rel!r}')
        actual = hashlib.sha256(vendor_files[rel]).hexdigest()
        if actual != expected_hash:
            raise BuildError(f'vendor hash mismatch: {rel}')
        entries[f'capital/vendor/{rel}'] = vendor_files[rel]
    entries['capital/vendor/manifest.json'] = manifest_bytes
    entries['__main__.py'] = b'from capital.server import main\nmain()\n'
    return version, commit, entries


def _release_manifest(version: str, commit: str, entries: dict[str, bytes]) -> bytes:
    payload = {
        'format': 'KIX_CAPITAL_RELEASE_V1',
        'name': 'kix-capital',
        'version': version,
        'protocol_commit': commit,
        'signed': False,
        'published': False,
        'mode': 'LOCAL_SIMULATION_ARTIFACT',
        'files': {name: hashlib.sha256(data).hexdigest() for name, data in entries.items()},
    }
    return (json.dumps(payload, sort_keys=True, indent=2) + '\n').encode('utf-8')


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(entries):
            info = zipfile.ZipInfo(filename=name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, entries[name])
    return buf.getvalue()


def _write_pyz(payload: bytes, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f'.{destination.name}.', suffix='.tmp', dir=destination.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        stream = io.BytesIO(payload)
        try:
            zipapp.create_archive(stream, os.fspath(tmp), interpreter='/usr/bin/env python3')
        except (TypeError, AttributeError, zipapp.ZipAppError):
            prefix = b'#!/usr/bin/env python3\n'
            body = payload if payload.startswith(b'#!') else prefix + payload
            tmp.write_bytes(body)
            tmp.chmod(0o755)
        os.replace(tmp, destination)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def build(out_dir, root=None) -> Path:
    root = repo_root() if root is None else Path(root)
    version, commit, entries = _package_entries(root)
    entries['RELEASE-MANIFEST.json'] = _release_manifest(version, commit, entries)
    destination = Path(out_dir) / f'capital-{version}.pyz'
    _write_pyz(_zip_bytes(entries), destination)
    return destination


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, help='Directory for dist/capital-<version>.pyz')
    args = parser.parse_args(argv)
    try:
        path = build(args.out)
    except BuildError as exc:
        print(f'build failed: {exc}', file=sys.stderr)
        return 1
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f'{path} {digest}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
