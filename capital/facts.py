"""SIMULATED typed facts and offline corruption checks; source authority NOT_BOUND.

A cut binds the pinned F04 and optional overlay digests separately. Hashes are
integrity checks, not authentication. There is no import or resume operation.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

from capital import overlay, recovery, slices
from capital.assets import KRW
from capital.export import sha256_hex
from capital.producer import FixtureViews
from capital.protocol import CreditError, CreditMachine
from capital.store import canonical_bytes
from capital.strict_json import loads

SCHEMA_ID = 'KIX_CAPITAL_FACTS_SCHEMA_V1'
PAGE_FORMAT = 'KIX_CAPITAL_FACTS_PAGE_V1'
ROW = 'KIX_CAPITAL_FACTS_ROW_V1'
CHAIN = 'KIX_CAPITAL_FACTS_CHAIN_V1'
PAGE = 'KIX_CAPITAL_FACTS_PAGE_V1'
CUT = 'KIX_CAPITAL_FACTS_CUT_V1'
LIMIT_DEFAULT, LIMIT_MAX = 100, 500
UINT_MAX = 99_999_999
HEX = re.compile(r'[0-9a-f]{64}\Z')
CURSOR = re.compile(r'kfc1\.([0-9]{8})\.([0-9a-f]{64})\Z')
LABELS = {
    'label': 'SIMULATED', 'source_cut': 'NOT_BOUND', 'authentication': 'NOT_BOUND',
    'stage7_authenticated_export': False, 'not_claims': ['k-stage7-authenticated-export'],
    'funds_executed': False, 'import_endpoint': 'NOT_PROVIDED', 'resume_endpoint': 'NOT_PROVIDED',
    'workspace_status': 'ACTIVE', 'completeness': 'COMPLETE_AT_CUT',
}
COLUMNS = [
    {'name': 'seq', 'type': 'uint', 'width': 8},
    {'name': 'fact_id', 'type': 'ascii_fixed', 'width': 10},
    {'name': 'source', 'type': 'ascii_fixed', 'width': 7},
    {'name': 'journal_position', 'type': 'uint', 'width': 8},
    {'name': 'kind', 'type': 'ascii_id', 'max_width': 32},
    {'name': 'amount_krw', 'type': 'int_atoms_krw', 'width': 13, 'nullable': True},
    {'name': 'sim_day', 'type': 'uint', 'width': 8, 'nullable': True},
    {'name': 'duplicate', 'type': 'flag01', 'width': 1},
    {'name': 'entry', 'type': 'canonical_json_object', 'width': 'variable'},
    {'name': 'row_sha256', 'type': 'hex', 'width': 64},
]
ROW_KEYS = frozenset(col['name'] for col in COLUMNS)
PAGE_KEYS = frozenset({
    'format', 'schema_id', 'schema_sha256', 'schema', 'cut', 'after', 'start_seq', 'limit',
    'row_count_total', 'rows', 'chain_before', 'chain_after', 'next_cursor', 'page_digest',
    *LABELS,
})


class FactsError(ValueError):
    def __init__(self, code, status=400):
        self.code, self.status = code, status
        super().__init__(code)


def schema():
    return {
        'schema_id': SCHEMA_ID, 'label': 'SIMULATED', 'source_cut': 'NOT_BOUND',
        'authentication': 'NOT_BOUND', 'stage7_authenticated_export': False,
        'asset': copy.deepcopy(KRW), 'columns': copy.deepcopy(COLUMNS),
        'rules': [
            'seq is contiguous from 0. uint width is maximum decimal digits; booleans are not integers.',
            'fact_id is J:%08d or O:%08d using the source list index. source is JOURNAL or OVERLAY.',
            'journal_position is the journal index or the raw overlay after_journal_index.',
            'kind is the journal op or overlay kind: 1..32 ASCII letters, digits or underscore.',
            'amount_krw is journal body.amount or overlay payload.amount_krw when present; '
            'it must be an integer in 0..asset.max_atoms, otherwise null only when absent.',
            'sim_day is null for journal rows and the raw unsigned overlay sim_day otherwise.',
            'duplicate is 1 only for an identical repeated overlay_id, ignored by fold; otherwise 0.',
            'entry is the complete raw canonical JSON object; row_sha256 is lowercase hexadecimal.',
            'Preserve both source list orders. Before each overlay entry emit remaining journal indices '
            'less than the running maximum of overlay after_journal_index; then emit remaining journal rows.',
            'cut has state_digest, journal_length, fixtures_digest, cut_id. overlay_state_digest and '
            'overlay_entry_count are both present exactly when the overlay list is nonempty; never null.',
            'Digests use capital.store.canonical_bytes and domain-tagged SHA256. Row material is '
            '{domain:ROW,row:row_without_hash}; chain genesis is {domain:CHAIN,cut_id,schema_sha256}; '
            'chain step is {domain:CHAIN,previous,row_sha256}; page material is {domain:PAGE,page:page_without_digest}; '
            'cut material is {domain:CUT,...cut_without_cut_id}. Domain constants are KIX_CAPITAL_FACTS_*_V1.',
            'Cursor is kfc1.<next seq as eight decimal digits>.<cut_id>. Limits 1..500, default 100. '
            'Canonical ASCII JSON bytes have no trailing newline. Hashes detect corruption, not authentication.',
        ],
    }


def _uint(value):
    return type(value) is int and 0 <= value <= UINT_MAX


def validate_row(row, *, sealed=True):
    if type(row) is not dict or set(row) != (ROW_KEYS if sealed else ROW_KEYS - {'row_sha256'}):
        raise FactsError('FACTS_ROW_INVALID', 500)
    valid = (
        _uint(row['seq']) and _uint(row['journal_position'])
        and type(row['source']) is str and row['source'] in ('JOURNAL', 'OVERLAY')
        and type(row['fact_id']) is str and re.fullmatch(r'[JO]:[0-9]{8}', row['fact_id']) is not None
        and row['fact_id'][0] == row['source'][0]
        and type(row['kind']) is str and re.fullmatch(r'[A-Za-z0-9_]{1,32}', row['kind']) is not None
        and (row['amount_krw'] is None or (type(row['amount_krw']) is int and 0 <= row['amount_krw'] <= KRW['max_atoms']))
        and (row['sim_day'] is None or _uint(row['sim_day']))
        and type(row['duplicate']) is int and row['duplicate'] in (0, 1)
        and type(row['entry']) is dict
    )
    if sealed:
        valid = valid and type(row['row_sha256']) is str and HEX.fullmatch(row['row_sha256']) is not None
    if not valid:
        raise FactsError('FACTS_ROW_INVALID', 500)


def build_rows(journal, overlay_entries):
    """Pure merge preserving both raw lists, including old-anchor duplicates."""
    rows, seen = [], {}

    def emit(entry, source, index):
        try:
            is_overlay = source == 'OVERLAY'
            body = entry['payload'] if is_overlay else entry['body']
            amount = body.get('amount_krw' if is_overlay else 'amount')
            if ('amount_krw' if is_overlay else 'amount') in body and type(amount) is not int:
                raise ValueError('amount type')
            duplicate = 0
            if is_overlay:
                key = entry['overlay_id']
                if key in seen:
                    if seen[key] != entry:
                        raise ValueError('conflicting duplicate')
                    duplicate = 1
                seen[key] = entry
            row = {'seq': len(rows), 'fact_id': f'{source[0]}:{index:08d}', 'source': source,
                   'journal_position': entry['after_journal_index'] if is_overlay else index,
                   'kind': entry['kind'] if is_overlay else entry['op'], 'amount_krw': amount,
                   'sim_day': entry['sim_day'] if is_overlay else None, 'duplicate': duplicate,
                   'entry': copy.deepcopy(entry)}
            validate_row(row, sealed=False)
            rows.append(row)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise FactsError('FACTS_ROW_INVALID', 500) from exc

    j, position = 0, 0
    for index, entry in enumerate(overlay_entries):
        anchor = entry.get('after_journal_index') if type(entry) is dict else None
        if not _uint(anchor) or anchor > len(journal):
            raise FactsError('FACTS_ROW_INVALID', 500)
        position = max(position, anchor)
        while j < position:
            emit(journal[j], 'JOURNAL', j)
            j += 1
        emit(entry, 'OVERLAY', index)
    while j < len(journal):
        emit(journal[j], 'JOURNAL', j)
        j += 1
    return rows


def cut_digest(cut):
    return sha256_hex({'domain': CUT, **{k: v for k, v in cut.items() if k != 'cut_id'}})


def make_cut(journal, entries, state_digest, fixtures_digest):
    cut = {'state_digest': state_digest, 'journal_length': len(journal), 'fixtures_digest': fixtures_digest}
    if entries:
        cut.update(overlay_state_digest=overlay.state_digest(overlay.fold(entries, len(journal))),
                   overlay_entry_count=len(entries))
    cut['cut_id'] = cut_digest(cut)
    return cut


def cursor(seq, cut):
    return f"kfc1.{seq:08d}.{cut['cut_id']}"


def decode_cursor(value):
    match = CURSOR.fullmatch(value) if type(value) is str else None
    if match is None or int(match[1]) == 0:
        raise FactsError('INVALID_CURSOR')
    return int(match[1]), match[2]


def row_digest(row):
    return sha256_hex({'domain': ROW, 'row': {k: v for k, v in row.items() if k != 'row_sha256'}})


def genesis(cut):
    return sha256_hex({'domain': CHAIN, 'cut_id': cut['cut_id'], 'schema_sha256': sha256_hex(schema())})


def chain_step(previous, row):
    return sha256_hex({'domain': CHAIN, 'previous': previous, 'row_sha256': row['row_sha256']})


def page_digest(page):
    return sha256_hex({'domain': PAGE, 'page': {k: v for k, v in page.items() if k != 'page_digest'}})


def seal(rows_unsealed, cut, after, start_seq, limit, total):
    """Seal one page from the complete unsealed row list (prefix supplies its chain)."""
    rows = [{**copy.deepcopy(row), 'row_sha256': row_digest(row)} for row in rows_unsealed]
    chain = genesis(cut)
    for row in rows[:start_seq]:
        chain = chain_step(chain, row)
    before = chain
    selected = rows[start_seq:start_seq + limit]
    for row in selected:
        chain = chain_step(chain, row)
    end = start_seq + len(selected)
    page = {'format': PAGE_FORMAT, 'schema_id': SCHEMA_ID, 'schema_sha256': sha256_hex(schema()),
            'schema': schema(), **copy.deepcopy(LABELS), 'cut': copy.deepcopy(cut), 'after': after,
            'start_seq': start_seq, 'limit': limit, 'row_count_total': total, 'rows': selected,
            'chain_before': before, 'chain_after': chain,
            'next_cursor': cursor(end, cut) if end < total else None}
    page['page_digest'] = page_digest(page)
    return page


def paginate(journal, entries, state_digest, fixtures_digest, after=None, limit=LIMIT_DEFAULT):
    if type(limit) is not int or not 1 <= limit <= LIMIT_MAX:
        raise FactsError('INVALID_ARGUMENTS')
    rows = build_rows(journal, entries)
    try:
        cut = make_cut(journal, entries, state_digest, fixtures_digest)
    except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
        raise FactsError('FACTS_ROW_INVALID', 500) from exc
    start = 0
    if after is not None:
        start, cut_id = decode_cursor(after)
        if cut_id != cut['cut_id']:
            raise FactsError('CUT_MOVED', 409)
        if start >= len(rows):
            raise FactsError('INVALID_CURSOR')
    return seal(rows, cut, after, start, limit, len(rows))


def verify_dir(directory):
    """Read canonical page files only; replay locally, never write or restore a service."""
    pages, rows = [], []

    def report(reason=None):
        return {'ok': reason is None, 'reason': reason, 'pages': len(pages), 'rows': len(rows),
                'authentication': 'NOT_BOUND', 'stage7_authenticated_export': False}

    try:
        paths = sorted(Path(directory).glob('page-*.json'))
    except OSError:
        return report('NO_PAGES')
    if not paths:
        return report('NO_PAGES')
    for path in paths:
        try:
            raw = path.read_bytes()
            page = loads(raw)
        except (OSError, ValueError, UnicodeError, RecursionError):
            return report('UNREADABLE:' + path.name)
        try:
            if raw != canonical_bytes(page):
                return report('NONCANONICAL_ENCODING:' + path.name)
        except (ValueError, RecursionError):
            return report('NONCANONICAL_ENCODING:' + path.name)
        pages.append(page)
    for page in pages:
        if type(page) is not dict or set(page) != PAGE_KEYS or page['format'] != PAGE_FORMAT:
            return report('PAGE_SHAPE')
        if any(canonical_bytes(page[k]) != canonical_bytes(v) for k, v in LABELS.items()):
            return report('LABEL_MISMATCH')
        if (page['schema_id'] != SCHEMA_ID or canonical_bytes(page['schema']) != canonical_bytes(schema())
                or page['schema_sha256'] != sha256_hex(schema())):
            return report('SCHEMA_MISMATCH')
        if (type(page['rows']) is not list or not _uint(page['start_seq'])
                or not _uint(page['row_count_total']) or type(page['limit']) is not int
                or not 1 <= page['limit'] <= LIMIT_MAX or type(page['cut']) is not dict):
            return report('PAGE_SHAPE')
    for page in pages:
        if page['page_digest'] != page_digest(page):
            return report('PAGE_DIGEST_MISMATCH')
    for page in pages:
        for row in page['rows']:
            try:
                validate_row(row)
            except FactsError:
                return report('ROW_TYPE')
            if row['row_sha256'] != row_digest(row):
                return report('ROW_HASH_MISMATCH')
            rows.append(row)
    cut = pages[0]['cut']
    if any(type(p['cut'].get('cut_id')) is not str or HEX.fullmatch(p['cut']['cut_id']) is None for p in pages):
        return report('CUT_MISMATCH')
    chain = genesis(cut)
    for page in pages:
        if page['chain_before'] != chain:
            return report('CHAIN_BROKEN')
        for row in page['rows']:
            chain = chain_step(chain, row)
        if page['chain_after'] != chain:
            return report('CHAIN_BROKEN')
    count, after = 0, None
    for index, page in enumerate(pages):
        if (page['start_seq'] != count or page['after'] != after
                or (index > 0 and after is None)
                or (not page['rows'] and (len(pages) != 1 or page['row_count_total'] != 0))):
            return report('CURSOR_MISMATCH')
        if after is not None:
            try:
                seq, _ = decode_cursor(after)
            except FactsError:
                return report('CURSOR_MISMATCH')
            if seq != count or seq >= page['row_count_total']:
                return report('CURSOR_MISMATCH')
        if any(row['seq'] != count + i for i, row in enumerate(page['rows'])):
            return report('CURSOR_MISMATCH')
        count += len(page['rows'])
        if len(page['rows']) > page['limit'] or (index < len(pages) - 1 and len(page['rows']) != page['limit']):
            return report('CURSOR_MISMATCH')
        if page['next_cursor'] is not None and page['next_cursor'] != cursor(count, page['cut']):
            return report('CURSOR_MISMATCH')
        after = page['next_cursor']
    cut_keys = {'state_digest', 'journal_length', 'fixtures_digest', 'cut_id'}
    if (set(cut) not in (cut_keys, cut_keys | {'overlay_state_digest', 'overlay_entry_count'})
            or not _uint(cut.get('journal_length'))
            or any(type(cut[k]) is not str or HEX.fullmatch(cut[k]) is None
                   for k in ('state_digest', 'fixtures_digest', 'cut_id'))
            or cut['cut_id'] != cut_digest(cut)):
        return report('CUT_MISMATCH')
    if any(page['cut'] != cut or page['row_count_total'] != pages[0]['row_count_total'] for page in pages):
        return report('CUT_MISMATCH')
    if after is not None or count != pages[0]['row_count_total']:
        return report('MISSING_FINAL_PAGE')
    journal = [row['entry'] for row in rows if row['source'] == 'JOURNAL']
    entries = [row['entry'] for row in rows if row['source'] == 'OVERLAY']
    if (len(journal) != cut['journal_length'] or bool(entries) != ('overlay_state_digest' in cut)
            or (entries and (type(cut['overlay_entry_count']) is not int or cut['overlay_entry_count'] != len(entries)))):
        return report('CUT_COUNT_MISMATCH')
    fixtures = FixtureViews()
    if cut['fixtures_digest'] != sha256_hex(fixtures.rows):
        return report('FIXTURES_MISMATCH')
    try:
        machine = CreditMachine.restore(journal, fixtures)
    except (CreditError, ValueError, KeyError, TypeError, ArithmeticError, AttributeError):
        return report('JOURNAL_REPLAY_FAILED')
    if machine.state_digest() != cut['state_digest']:
        return report('STATE_DIGEST_MISMATCH')
    try:
        folded = overlay.fold(entries, len(journal))
        if entries and overlay.state_digest(folded) != cut['overlay_state_digest']:
            return report('OVERLAY_FOLD_MISMATCH')
    except (ValueError, KeyError, TypeError, ArithmeticError):
        return report('OVERLAY_FOLD_MISMATCH')
    try:
        recovery.validate_links(entries, journal)
        slices.validate_links(entries, journal, fixtures.rows)
    except (ValueError, KeyError, TypeError, ArithmeticError):
        return report('OVERLAY_LINK_MISMATCH')
    try:
        expected = build_rows(journal, entries)
    except FactsError:
        return report('ROW_TYPE')
    for index, (actual, rebuilt) in enumerate(zip(rows, expected)):
        if canonical_bytes(actual) != canonical_bytes({**rebuilt, 'row_sha256': row_digest(rebuilt)}):
            return report(f'ROW_MISMATCH:{index}')
    return report()
