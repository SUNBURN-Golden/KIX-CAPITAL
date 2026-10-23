#!/usr/bin/env python3
"""Write or verify an offline audit evidence pack. SIMULATED / LOCAL_ONLY.

`--workspace DIR --out DIR` reads DIR/workspace.json bytes directly (no lock,
no write, no repair) and writes OUT/evidence-pack.json: export manifest,
workspace audit, reconciliation, decisions summary, and the authorization
matrix — five sha256-sectioned bodies under one content_digest, with volatile
fields (instance ids, timestamps, the event log) excluded or separately
digested. Two runs on the same workspace produce identical bytes.

`--verify FILE` re-checks every section hash, the volatile hash, the content
digest, and the embedded export manifest fully offline and exits 1 on the
first tampered byte. A pinned tamper corpus lives in tests/vectors/pack/.

Dev HMAC keys and tokens are never read or copied into the pack; the embedded
manifest's signature stays NOT_BOUND. Remote attestation, stage7 authenticated
export, and retention enforcement are out of scope. This is a local
diagnostic, not an import or resume route.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital import evidence


def _write_report(report):
    sys.stdout.write(json.dumps(report, sort_keys=True, separators=(',', ':')) + '\n')


def _write(args):
    pack = evidence.pack_document(args.workspace)
    report = {
        'ok': False,
        'reason': None,
        'format': evidence.PACK_FORMAT,
        'label': 'SIMULATED',
        'diagnostic': 'READ_ONLY',
        'locality': 'LOCAL_ONLY',
        'mode': 'WRITE',
        'pack': None,
        'pack_status': pack['status'],
        'incomplete_reasons': pack['incomplete_reasons'],
        'sections': sorted(pack['sections']),
        'content_digest': pack['content_digest'],
        'authentication': 'NOT_BOUND',
        'remote_attestation': 'NOT_BOUND',
        'funds_executed': False,
    }
    try:
        args.out.mkdir(parents=True, exist_ok=True)
        target = args.out / evidence.PACK_FILE
        target.write_bytes(evidence.dump(pack))
    except OSError as exc:
        report['reason'] = 'PACK_WRITE_FAILED'
        report['error'] = str(exc)
        _write_report(report)
        return 1
    report['pack'] = str(target)
    verified = evidence.verify_path(target)
    report['verified'] = verified['ok']
    if not verified['ok']:
        report['reason'] = f"WRITTEN_PACK_INVALID:{verified['reason']}"
        _write_report(report)
        return 1
    report['ok'] = pack['status'] == 'COMPLETE'
    if not report['ok']:
        report['reason'] = pack['incomplete_reasons'][0]
    _write_report(report)
    return 0 if report['ok'] else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=(
        'Compose an offline audit evidence pack over DIR/workspace.json '
        '(read-only: no lock, no write, no repair), or re-check one offline. '
        'SIMULATED / LOCAL_ONLY. Not remote attestation, not stage7 '
        'authenticated export, not an import or resume route.'
    ))
    parser.add_argument('--workspace', type=Path, default=None,
                        help='Workspace directory holding workspace.json. Read-only.')
    parser.add_argument('--out', type=Path, default=None,
                        help='Directory the pack is written to, as evidence-pack.json.')
    parser.add_argument('--verify', type=Path, default=None,
                        help='Re-check an evidence pack file offline. Exit 1 on any tampered byte.')
    args = parser.parse_args(argv)
    if args.verify is not None:
        if args.workspace is not None or args.out is not None:
            parser.error('--verify is mutually exclusive with --workspace/--out')
        report = evidence.verify_path(args.verify)
        _write_report(report)
        return 0 if report['ok'] else 1
    if args.workspace is None or args.out is None:
        parser.error('--workspace DIR --out DIR or --verify FILE is required')
    return _write(args)


if __name__ == '__main__':
    sys.exit(main())
