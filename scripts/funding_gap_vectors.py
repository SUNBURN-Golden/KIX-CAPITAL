#!/usr/bin/env python3
"""Regenerate or check the bounded SIMULATED funding-gap examples."""
import argparse
import hashlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from capital import overlay, store
from capital.evidence import offline_service
from capital.funding_gap import report_workspace
from capital.service import CapitalService

VECTOR_DIR = ROOT / 'tests' / 'vectors' / 'funding_gap'
ADVANCE = 'sim-gap-arena'
BENEFICIARY = 'demo-org-alpha'
BASIS = 'PROSPECTIVE_PRE_SETOFF_ALLOCATION'


def draw(service, ref=ADVANCE, fixture='demo-alpha-arena', amount=10_000):
    for op, args in (('offer', {'fixture_id': fixture, 'amount': amount}), ('approve', {}),
                     ('bind_settlement', {}), ('draw', {})):
        receipt = service.execute({
            'instance_id': service.instance_id, 'operation_id': ref + '-' + op.replace('_', '-'),
            'op': op, 'advance_id': ref, 'args': args})
        if receipt['outcome'] != 'ACCEPTED':
            raise ValueError(f'vector {op} refused: {receipt}')


def book():
    service = CapitalService()
    service.instance_id = service.storage.writer_instance = 'funding-gap-vector'
    return service


def document(service, *, bind_day_zero=True):
    envelope = service.storage.load()
    if bind_day_zero and not envelope['overlay']['journal']:
        # Pin a valid binding-only section so the example cut can stay at day zero.
        # Normal workspace clock commands advance past day zero.
        binding = {'terms_version': service.terms.version, 'status': service.terms.top}
        entry = {'kind': overlay.KIND_TERMS, 'sim_day': 0, 'after_journal_index': 0,
                 'overlay_id': 'funding-gap-vector-terms', 'payload': binding}
        envelope['overlay'] = overlay.build_section([entry])
    envelope['saved_at'] = '2000-01-01T00:00:00.000000Z'
    return envelope


def dump(value):
    return store.canonical_bytes(value) + b'\n'


def source(kind='FIXTURE', ref='demo-alpha-hall', *, amount=10_115, day=60, delay=0):
    return {'reference': {'kind': kind, 'id': ref}, 'basis': BASIS, 'budget_krw': 12_000,
            'delay_days': delay, 'releases': [
                {'release_id': 'hall-1', 'base_available_sim_day': day, 'amount_krw': amount}]}


def schedule(envelope, scenario_id='timely', **changes):
    service = offline_service(envelope)
    snapshot = service.portfolio_snapshot(service.instance_id)
    return {'scenario_id': scenario_id, 'workspace_id': 'sha256:' + hashlib.sha256(dump(envelope)).hexdigest(),
            'snapshot_digest': snapshot['snapshot_digest'], 'beneficiary_id': BENEFICIARY,
            'advance_ids': [ADVANCE], 'horizon_days': 62, 'sources': [source()], **changes}


def vectors():
    service = book()
    draw(service)
    envelope = document(service)
    files = {store.FILE_NAME: dump(envelope)}
    base = schedule(envelope)
    cases = {
        'timely': ({}, ('EVALUATED_HYPOTHETICAL', 0, 0)),
        'late': ({'sources': [source(delay=2)]}, ('EVALUATED_HYPOTHETICAL', 10_115, 0)),
        'insufficient': ({'sources': [source(amount=10_114)]}, ('EVALUATED_HYPOTHETICAL', 1, 1)),
        'post-setoff': ({'sources': [{**source(), 'basis': 'POST_SETOFF_PROCEEDS'}]},
                        ('UNEVALUATED', None, None)),
    }
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        (workspace / store.FILE_NAME).write_bytes(files[store.FILE_NAME])
        for name, (changes, expected) in cases.items():
            scenario = {**base, 'scenario_id': name, **changes}
            schedule_name, report_name = f'{name}.schedule.json', f'{name}.report.json'
            files[schedule_name] = dump(scenario)
            path = workspace / schedule_name
            path.write_bytes(files[schedule_name])
            report = report_workspace(workspace, path)
            metrics = report['metrics'] or {}
            actual = (report['status'], metrics.get('peak_shortage_krw'), metrics.get('terminal_shortage_krw'))
            if actual != expected:
                raise ValueError(f'{name}: expected {expected}, got {actual}, {report["issues"]}')
            files[report_name] = dump(report)
        draw(service, 'sim-pledged-hall', 'demo-alpha-hall', 300)
        pledged = document(service)
        files['pledged/workspace.json'] = dump(pledged)
        files['pledged/hall.schedule.json'] = dump(schedule(pledged, 'unselected-hall-draw'))
        (workspace / store.FILE_NAME).write_bytes(files['pledged/workspace.json'])
        path = workspace / 'hall.schedule.json'
        path.write_bytes(files['pledged/hall.schedule.json'])
        report = report_workspace(workspace, path)
        if report['status'] != 'UNEVALUATED' or report['sources'][0].get('reason') != 'UNSELECTED_ADVANCE_COMMITMENT':
            raise ValueError(f'unselected Hall draw must leave the report unevaluated: {report["issues"]}')
        files['pledged/hall.report.json'] = dump(report)
    return files


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--check', action='store_true')
    action.add_argument('--write', action='store_true')
    parser.add_argument('--dir', type=Path, default=VECTOR_DIR)
    args = parser.parse_args(argv)
    expected = vectors()
    if args.write:
        for name, raw in expected.items():
            path = args.dir / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    actual = {path.relative_to(args.dir).as_posix(): path for path in args.dir.rglob('*')
              if not path.is_dir() or path.is_symlink()}
    findings = [f'unexpected {name}' for name in sorted(actual.keys() - expected.keys())]
    for name, raw in expected.items():
        path = actual.get(name)
        if path is None:
            findings.append(f'missing {name}')
        elif not path.is_file() or path.is_symlink() or path.read_bytes() != raw:
            findings.append(f'changed {name}')
    if findings:
        print('\n'.join(findings), file=sys.stderr)
        return 1
    print(f'funding-gap vectors: {len(expected)} files match')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
