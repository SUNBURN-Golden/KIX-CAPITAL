#!/usr/bin/env python3
"""Pin SIMULATED facts pages and resealed semantic tampering; no external calls.

--check regenerates in memory and byte-compares the entire owned directory.
--write is the explicit corpus writer; --dir selects a disposable copy.
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital import facts, overlay
from capital.service import CapitalService, digest
from capital.store import canonical_bytes
from scripts.seed_demo import apply_steps

DEFAULT_DIR = ROOT / 'tests/vectors/facts'
LIMIT = 4


def seed():
    service = CapitalService()
    apply_steps(service)
    return service


def with_overlay(service):
    service.overlay_command({'instance_id': service.instance_id, 'operation_id': 'facts-clock',
                            'op': 'advance_day', 'from_sim_day': 0, 'to_sim_day': 3,
                            'reason': 'SIMULATED facts vector'})
    receipt = service.execute({'instance_id': service.instance_id, 'operation_id': 'facts-default',
                               'op': 'default', 'advance_id': 'sim-unbound', 'args': {}})
    assert receipt['outcome'] == 'ACCEPTED'
    return service


def pages_for(rows, cut):
    pages = []
    after = None
    for start in range(0, max(1, len(rows)), LIMIT):
        page = facts.seal(rows, cut, after, start, LIMIT, len(rows))
        pages.append(page)
        after = page['next_cursor']
    return pages


def build():
    service = seed()
    journal = service.machine.export_journal()
    empty_cut = facts.make_cut(journal, [], service.machine.state_digest(), digest(service.fixtures.rows))
    empty_pages = pages_for(facts.build_rows(journal, []), empty_cut)
    with_overlay(service)
    journal, entries = service.machine.export_journal(), copy.deepcopy(service.overlay_entries)
    rows = facts.build_rows(journal, entries)
    cut = facts.make_cut(journal, entries, service.machine.state_digest(), digest(service.fixtures.rows))
    clean = pages_for(rows, cut)
    result = {'schema.json': canonical_bytes(facts.schema())}
    expected = {}

    def add(name, pages, reason=None):
        expected[name] = reason
        for index, page in enumerate(pages):
            result[f'{name}/page-{index:04d}.json'] = canonical_bytes(page)

    def mutate(name, callback, reason):
        pages = copy.deepcopy(clean)
        callback(pages)
        for page in pages:
            page['page_digest'] = facts.page_digest(page)
        add('semantic/' + name, pages, reason)

    def recut(name, key, value, reason):
        changed = {**cut, key: value}
        changed['cut_id'] = facts.cut_digest(changed)
        add('semantic/' + name, pages_for(rows, changed), reason)

    add('clean', clean)
    add('clean-empty-overlay', empty_pages)
    add('corrupt/entry-byte', clean, 'PAGE_DIGEST_MISMATCH')
    path = 'corrupt/entry-byte/page-0000.json'
    assert b'"amount":20000' in result[path]
    result[path] = result[path].replace(b'"amount":20000', b'"amount":20001', 1)
    add('corrupt/whitespace', clean, 'NONCANONICAL_ENCODING:page-0000.json')
    result['corrupt/whitespace/page-0000.json'] += b' '
    add('corrupt/truncated', clean, 'UNREADABLE:page-0000.json')
    result['corrupt/truncated/page-0000.json'] = result['corrupt/truncated/page-0000.json'][:-1]
    add('corrupt/missing-final-page', clean[:-1], 'MISSING_FINAL_PAGE')

    changed = copy.deepcopy(rows)
    changed[0]['amount_krw'] += 1
    add('semantic/row-amount', pages_for(changed, cut), 'ROW_MISMATCH:0')
    changed = copy.deepcopy(rows)
    changed[20], changed[21] = changed[21], changed[20]
    for i, row in enumerate(changed):
        row['seq'] = i
    add('semantic/row-reorder', pages_for(changed, cut), 'ROW_MISMATCH:20')
    mutate('row-hash', lambda p: p[0]['rows'][0].update(row_sha256='0' * 64), 'ROW_HASH_MISMATCH')
    mutate('chain-before', lambda p: p[1].update(chain_before='0' * 64), 'CHAIN_BROKEN')
    mutate('cursor-skip', lambda p: p[1].update(after=facts.cursor(8, cut)), 'CURSOR_MISMATCH')

    def different_cut(pages):
        pages[-1]['cut']['state_digest'] = '0' * 64
        pages[-1]['cut']['cut_id'] = facts.cut_digest(pages[-1]['cut'])
    mutate('cut-differs-one-page', different_cut, 'CUT_MISMATCH')
    recut('cut-count', 'journal_length', cut['journal_length'] + 1, 'CUT_COUNT_MISMATCH')
    recut('state-digest', 'state_digest', '0' * 64, 'STATE_DIGEST_MISMATCH')
    recut('overlay-digest', 'overlay_state_digest', '0' * 64, 'OVERLAY_FOLD_MISMATCH')
    recut('fixtures-digest', 'fixtures_digest', '0' * 64, 'FIXTURES_MISMATCH')
    changed_journal = copy.deepcopy(journal)
    next(e for e in changed_journal if e['advance_id'] == 'sim-cancelled' and e['op'] == 'offer')['body']['amount'] += 1
    add('semantic/entry-amount', pages_for(facts.build_rows(changed_journal, entries), cut), 'STATE_DIGEST_MISMATCH')
    changed_entries = copy.deepcopy(entries)
    next(e for e in changed_entries if e['kind'] == 'default_anchor')['payload']['principal_krw'] += 1
    changed_cut = facts.make_cut(journal, changed_entries, cut['state_digest'], cut['fixtures_digest'])
    add('semantic/anchor-principal', pages_for(facts.build_rows(journal, changed_entries), changed_cut), 'OVERLAY_LINK_MISMATCH')
    mutate('label', lambda p: p[0].update(source_cut='BOUND'), 'LABEL_MISMATCH')
    result['index.json'] = canonical_bytes({'label': 'SIMULATED', 'authentication': 'NOT_BOUND',
                                           'stage7_authenticated_export': False, 'cases': expected})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--write', action='store_true')
    parser.add_argument('--dir', type=Path, default=DEFAULT_DIR)
    args = parser.parse_args(argv)
    expected = build()
    try:
        existing = {str(p.relative_to(args.dir)): p for p in args.dir.rglob('*') if p.is_file()}
        if args.write:
            for name, path in existing.items():
                if name not in expected:
                    path.unlink()
            for name, raw in expected.items():
                path = args.dir / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
        else:
            drift = set(existing) ^ set(expected)
            drift.update(name for name in existing.keys() & expected.keys() if existing[name].read_bytes() != expected[name])
            if drift:
                print('facts vector drift: ' + ', '.join(sorted(drift)), file=sys.stderr)
                return 1
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f'facts vectors ok: {len(expected)} canonical/intentional-tamper files; SIMULATED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
