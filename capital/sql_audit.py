"""Offline SQLite expression of V1 synthetic principal and settlement checks.

Only verified embedded facts enter a disposable :memory: database. No service
restore, projection port, reconciliation builder, key loading or persistent SQL
storage is used. Hash equality does not authenticate facts or prove completeness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

from capital import assets, evidence, export
from capital.resources import vendor_manifest

MAX_INT = (1 << 63) - 1
MONEY_MAX = assets.KRW['max_atoms']
POSTED_CLAIMS = ('sim-committed', 'sim-pending', 'sim-refund')
CHECK_IDS = ('json', 'integrity', 'eligibility', 'fixture_digest', 'shape_and_bounds',
             'claim_constraints', 'journal_identity', 'journal_principal',
             'principal_projection', 'claim_projection', 'statement_exposure',
             'statement_settlement', 'statement_refund', 'transaction_headers',
             'posting_lines', 'account_totals', 'step_balance')
_IDENT = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,80}\Z')
_REAL_FLAGS = ('funds_executed', 'bank_debit_observed', 'legal_debtor_bound',
               'admission_granted', 'right_cancelled', 'external_return_closed',
               'economic_finality_claimed', 'durable')


class AuditError(ValueError):
    pass


def _require(condition, reason):
    if not condition:
        raise AuditError(reason)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, 'DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def _reject_number(_):
    raise AuditError('NON_INTEGER_JSON_NUMBER')


def _loads(raw):
    _require(type(raw) is bytes, 'INPUT_BYTES_REQUIRED')
    _require(not raw.startswith(b'\xef\xbb\xbf') and b'\0' not in raw, 'BOM_OR_NUL')
    document = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                          parse_float=_reject_number, parse_constant=_reject_number)
    pending = [document]
    while pending:
        value = pending.pop()
        if type(value) is dict:
            pending.extend(value.keys())
            pending.extend(value.values())
        elif type(value) is list:
            pending.extend(value)
        elif type(value) is str:
            _require('\0' not in value and not any(0xD800 <= ord(c) <= 0xDFFF for c in value),
                     'INVALID_JSON_STRING')
    return document


def _dict(value):
    _require(type(value) is dict, 'OBJECT_REQUIRED')
    return value


def _list(value):
    _require(type(value) is list, 'ARRAY_REQUIRED')
    return value


def _text(value, ident=False):
    _require(type(value) is str and 0 < len(value) <= 200
             and not any(c.isspace() or ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value),
             'TEXT_GRAMMAR')
    _require(not ident or _IDENT.fullmatch(value) is not None, 'IDENTIFIER_GRAMMAR')
    return value


def _integer(value, aggregate=False):
    _require(type(value) is int, 'EXACT_INTEGER_REQUIRED')
    _require(0 <= value <= (MAX_INT if aggregate else MONEY_MAX), 'INTEGER_BOUND')
    return value


def _no_real(value, required=True):
    _dict(value)
    if required:
        _require(value.get('funds_executed') is False, 'NO_REAL_EFFECT')
    for key in _REAL_FLAGS:
        if key in value:
            _require(value[key] is False, 'NO_REAL_EFFECT')


def _eligibility(pack):
    _require(pack.get('status') == 'COMPLETE' and pack.get('incomplete_reasons') == [], 'PACK_INCOMPLETE')
    _require(pack.get('label') == 'SIMULATED' and pack.get('locality') == 'LOCAL_ONLY'
             and pack.get('diagnostic') == 'READ_ONLY', 'PACK_LABELS')
    _no_real(pack)
    for name, tag in evidence.PACK_PART_TAGS.items():
        body = _dict(pack['sections'][name]['body'])
        _require(body.get('part_tag') == tag, 'PACK_PART_TAG')
        doc = _dict(body.get('document'))
        _require(doc.get('status') not in ('UNAVAILABLE', 'NOT_BOUND'), 'SECTION_UNAVAILABLE')
    manifest = pack['sections']['export_manifest']['body']['document']
    _require(manifest.get('status') == 'COMPLETE' and manifest.get('incomplete_reasons') == [], 'MANIFEST_INCOMPLETE')
    _require(manifest.get('label') == 'SIMULATED' and manifest.get('diagnostic') == 'READ_ONLY'
             and manifest.get('stage7_authenticated_export') is False, 'MANIFEST_LABELS')
    _no_real(manifest)
    sections = {}
    for name, section in manifest['sections'].items():
        body = _dict(section['body'])
        _require(body.get('part_tag') == export.PART_TAGS[name], 'MANIFEST_PART_TAG')
        _require(body.get('status') != 'UNAVAILABLE', 'SECTION_UNAVAILABLE')
        _no_real(body, required=False)
        sections[name] = body
    pin = sections['source_pin']
    expected = vendor_manifest()
    _require(all(pin.get(k) == expected[k] for k in ('repository', 'commit', 'files')), 'SOURCE_PIN_UNSUPPORTED')
    declared = pin.get('assets')
    _require(type(declared) is list and len(declared) == 1 and assets.matches(declared[0]), 'ASSET_UNSUPPORTED')
    _require(pin.get('label') == 'READ_ONLY_FIXTURE', 'SOURCE_LABEL')
    projection = sections['projection']
    _require(projection.get('chart') == 'SIMULATION_FIXED_V1', 'CHART_UNSUPPORTED')
    _require(projection.get('source_commit') == expected['commit'], 'SOURCE_PIN_UNSUPPORTED')
    _require(projection.get('accounting_policy') == 'SYNTHETIC_UNADOPTED'
             and projection.get('policy_adopted') is False
             and projection.get('mode') == 'LOCAL_PROJECTION_CANDIDATE', 'PROJECTION_LABELS')
    for name in ('projection', 'statement'):
        _no_real(sections[name])
    _require(sections['journal'].get('label') == 'SIMULATED'
             and sections['fixtures'].get('label') == 'READ_ONLY_FIXTURE', 'FACT_LABELS')
    statement = sections['statement']
    _require(statement.get('label') == 'SIMULATED'
             and statement.get('diagnostic') == 'LOCAL_ONLY'
             and statement.get('mode') == 'READ_ONLY_STATEMENT', 'STATEMENT_LABELS')
    return manifest, sections


# All identifiers and SQL below are program constants. Values only enter through
# bound parameters. Integer and text checks avoid SQLite's affinity coercions.
_SCHEMAS = {
    'journal': 'position I, op T, txn_id T, advance_id T, amount I, role T, repay_id T, sequence I',
    'claims': 'claim_id T, settlement_id T, fixture_gross I, gross I, phase T, confirmed_cash I, distributed_cash I, refund_face I, refund_accepted I, refund_outstanding I',
    'payees': 'claim_id T, payee T, face I, distributed I, outstanding I, recovery_due I',
    'exported_advances': 'advance_id T, role T, amount I, drawn I, repaid I, outstanding I',
    'exported_claims': 'claim_id T, phase T, gross I, confirmed_cash I, refund_face I, refund_outstanding I',
    'exported_payees': 'claim_id T, payee T, face I, distributed I, outstanding I, recovery_due I',
    'exported_headers': 'position I, step I, source T, txn_id T, advance_id T, advance_id_present I',
    'exported_lines': 'entry_position I, line_position I, account T, side T, amount I',
    'exported_accounts': 'code T, kind T, debit_total I, credit_total I, balance I',
    'statement_exposure': 'advance_id T, drawn I, repaid I, outstanding I',
    'statement_exposure_total': 'drawn I, repaid I, outstanding I',
    'statement_settlement': 'claim_id T, phase T, confirmed_cash I, distributed_cash I',
    'statement_settlement_total': 'confirmed_cash I, distributed_cash I',
    'statement_refund': 'claim_id T, refund_face I, refund_accepted I, refund_outstanding I',
    'statement_refund_total': 'refund_face I, refund_accepted I, refund_outstanding I',
}


def _budget(rows):
    # Conservative admission bound, including worst-case repeated draw postings,
    # joins, cumulative repayment windows, balances and sums on either side.
    # False rejection near the int64 ceiling is preferable to SQLite promotion.
    total = sum(v for group in rows.values() for row in group for v in row if type(v) is int)
    journal = rows['journal']
    worst_draws = len(journal) * max((r[4] for r in journal if r[1] == 'offer'), default=0)
    _require(4 * (total + worst_draws) <= MAX_INT, 'ARITHMETIC_BUDGET_EXCEEDED')


def _rows(sections):
    rows = {name: [] for name in _SCHEMAS}
    def add(name, *values):
        rows[name].append(values)
    for pos, raw in enumerate(_list(sections['journal']['entries']), 1):
        _dict(raw)
        _require(set(raw) == {'op', 'idempotency_key', 'advance_id', 'body'}, 'JOURNAL_SHAPE')
        body = _dict(raw['body'])
        _no_real(body, required=False)
        op = _text(raw['op'])
        _require(op in ('offer', 'approve', 'reject', 'cancel', 'bind_settlement', 'draw', 'repay', 'close', 'default'), 'JOURNAL_OP_UNSUPPORTED')
        amount = _integer(body['amount']) if op in ('offer', 'repay') else 0
        role = _text(body['beneficiary_role'], True) if op == 'offer' else ''
        repay_id = _text(body['repay_id']) if op == 'repay' else ''
        sequence = _integer(body['sequence'], True) if op == 'repay' else 0
        add('journal', pos, op, _text(raw['idempotency_key']), _text(raw['advance_id'], True), amount, role, repay_id, sequence)
        if op == 'offer':
            _no_real(body['face'])
    for fixture_id, view in _dict(sections['fixtures']['rows']).items():
        _text(fixture_id, True)
        _no_real(view)
        claim = _dict(view['claim'])
        _no_real(claim)
        _require(fixture_id == claim.get('claim_id'), 'FIXTURE_IDENTITY')
        claim_id = _text(claim['claim_id'], True)
        add('claims', claim_id, _text(view['settlement_id'], True), _integer(view['gross']),
            _integer(claim['gross']), _text(view['phase']), *(_integer(claim[k]) for k in
            ('confirmed_cash', 'distributed_cash', 'refund_face', 'refund_accepted', 'refund_outstanding')))
        for payee in _list(claim['obligations']):
            _dict(payee)
            add('payees', claim_id, _text(payee['payee'], True), *(_integer(payee[k]) for k in
                ('face', 'distributed', 'outstanding', 'recovery_due')))
    _require(set(POSTED_CLAIMS) <= set(sections['fixtures']['rows']), 'V1_POSTING_SCOPE_MISSING')
    projection = sections['projection']
    model = _dict(projection['read_model'])
    for row in _list(model['advances']):
        _dict(row)
        add('exported_advances', _text(row['advance_id'], True), _text(row['beneficiary_role'], True),
            *(_integer(row[k]) for k in ('amount', 'drawn', 'repaid', 'outstanding')))
    for row in _list(model['claims']):
        _dict(row)
        claim_id = _text(row['claim_id'], True)
        add('exported_claims', claim_id, _text(row['phase']), *(_integer(row[k]) for k in
            ('gross', 'confirmed_cash', 'refund_face', 'refund_outstanding')))
        for payee in _list(row['obligations']):
            _dict(payee)
            add('exported_payees', claim_id, _text(payee['payee'], True), *(_integer(payee[k]) for k in
                ('face', 'distributed', 'outstanding', 'recovery_due')))
    for pos, entry in enumerate(_list(projection['entries']), 1):
        _dict(entry)
        _require(set(entry) in ({'step', 'source', 'txn_id', 'lines'},
                               {'step', 'source', 'txn_id', 'lines', 'advance_id'}), 'HEADER_SHAPE')
        present = int('advance_id' in entry)
        add('exported_headers', pos, _integer(entry['step'], True), _text(entry['source']),
            _text(entry['txn_id']), _text(entry['advance_id'], True) if present else '', present)
        for line_pos, line in enumerate(_list(entry['lines']), 1):
            _dict(line)
            _require(set(line) == {'account', 'side', 'amount'}, 'LINE_SHAPE')
            _require(line['side'] in ('debit', 'credit'), 'LINE_SIDE')
            add('exported_lines', pos, line_pos, _text(line['account']), line['side'], _integer(line['amount']))
    for row in _list(projection['accounts']):
        _dict(row)
        add('exported_accounts', _text(row['code']), _text(row['kind']),
            *(_integer(row[k], True) for k in ('debit_total', 'credit_total', 'balance')))
    categories = _list(sections['statement']['categories'])
    _require(all(type(c) is dict for c in categories), 'CATEGORY_SHAPE')
    _require(sorted(c['id'] for c in categories) == ['approved', 'exposure', 'refund', 'reserved', 'settlement'], 'CATEGORY_IDENTITIES')
    for cat in categories:
        kind = cat['id']
        if kind == 'exposure':
            _require(cat.get('source') == 'SIMULATED', 'STATEMENT_SOURCE')
            keys = ('drawn', 'repaid', 'outstanding')
            for row in _list(cat['rows']):
                _dict(row)
                add('statement_exposure', _text(row['advance_id'], True), *(_integer(row[k]) for k in keys))
        elif kind in ('settlement', 'refund'):
            _require(cat.get('source') == 'READ_ONLY_FIXTURE', 'STATEMENT_SOURCE')
            keys = ('confirmed_cash', 'distributed_cash') if kind == 'settlement' else ('refund_face', 'refund_accepted', 'refund_outstanding')
            for row in _list(cat['rows']):
                _dict(row)
                values = [_text(row['claim_id'], True)]
                if kind == 'settlement':
                    values.append(_text(row['phase']))
                add('statement_' + kind, *values, *(_integer(row[k]) for k in keys))
        else:
            continue
        total_keys = ('confirmed', 'distributed') if kind == 'settlement' else keys
        add('statement_' + kind + '_total', *(_integer(cat[k], True) for k in total_keys))
    _budget(rows)
    return rows


_VIEWS = """
CREATE VIEW posted_claims AS SELECT * FROM claims
 WHERE claim_id IN ('sim-committed','sim-pending','sim-refund');
CREATE VIEW principal AS
 SELECT o.advance_id, o.role, o.amount,
 (SELECT COUNT(*) FROM journal d WHERE d.advance_id=o.advance_id AND d.op='draw') * o.amount AS drawn,
 COALESCE((SELECT SUM(r.amount) FROM journal r WHERE r.advance_id=o.advance_id AND r.op='repay'),0) AS repaid
 FROM journal o WHERE o.op='offer';
CREATE VIEW expected_advances AS
 SELECT advance_id,role,amount,drawn,repaid,drawn-repaid AS outstanding FROM principal;
CREATE VIEW expected_headers AS
 SELECT ROW_NUMBER() OVER (ORDER BY claim_id) AS position,
 ROW_NUMBER() OVER (ORDER BY claim_id) AS step, 'EVIDENCE' AS source,
 'evidence:'||claim_id AS txn_id, '' AS advance_id, 0 AS advance_id_present FROM posted_claims
 UNION ALL SELECT position+(SELECT COUNT(*) FROM posted_claims),
 position+(SELECT COUNT(*) FROM posted_claims),'JOURNAL',txn_id,advance_id,1 FROM journal;
CREATE VIEW expected_lines AS
 SELECT h.position AS entry_position,1 AS line_position,'SIM_CLAIM_FACE:'||c.claim_id AS account,
 'debit' AS side,c.gross AS amount FROM posted_claims c JOIN expected_headers h ON h.txn_id='evidence:'||c.claim_id
 UNION ALL
 SELECT h.position,1+ROW_NUMBER() OVER (PARTITION BY p.claim_id ORDER BY p.payee),
 'SIM_PAYEE_OBLIGATION:'||p.claim_id||':'||p.payee,'credit',p.face
 FROM payees p JOIN expected_headers h ON h.txn_id='evidence:'||p.claim_id
 UNION ALL
 SELECT h.position,1,'SIM_ADVANCE_EXPOSURE:'||j.advance_id,'debit',o.amount
 FROM journal j JOIN journal o ON o.advance_id=j.advance_id AND o.op='offer'
 JOIN expected_headers h ON h.txn_id=j.txn_id WHERE j.op='draw'
 UNION ALL
 SELECT h.position,2,'SIM_ADVANCE_OBLIGATION:'||j.advance_id,'credit',o.amount
 FROM journal j JOIN journal o ON o.advance_id=j.advance_id AND o.op='offer'
 JOIN expected_headers h ON h.txn_id=j.txn_id WHERE j.op='draw'
 UNION ALL
 SELECT h.position,1,'SIM_ADVANCE_OBLIGATION:'||j.advance_id,'debit',j.amount
 FROM journal j JOIN expected_headers h ON h.txn_id=j.txn_id WHERE j.op='repay'
 UNION ALL
 SELECT h.position,2,'SIM_REPAY_MEMO:'||j.advance_id,'credit',j.amount
 FROM journal j JOIN expected_headers h ON h.txn_id=j.txn_id WHERE j.op='repay';
CREATE VIEW expected_accounts AS
 SELECT account AS code,
 CASE WHEN account LIKE 'SIM_CLAIM_FACE:%' THEN 'SYNTHETIC_CLAIM_FACE'
 WHEN account LIKE 'SIM_PAYEE_OBLIGATION:%' THEN 'SYNTHETIC_PAYEE_OBLIGATION'
 WHEN account LIKE 'SIM_ADVANCE_EXPOSURE:%' THEN 'SYNTHETIC_ADVANCE_EXPOSURE'
 WHEN account LIKE 'SIM_ADVANCE_OBLIGATION:%' THEN 'SYNTHETIC_ADVANCE_OBLIGATION'
 ELSE 'SYNTHETIC_REPAY_MEMO' END AS kind,
 SUM(CASE side WHEN 'debit' THEN amount ELSE 0 END) AS debit_total,
 SUM(CASE side WHEN 'credit' THEN amount ELSE 0 END) AS credit_total,
 CASE WHEN account LIKE 'SIM_CLAIM_FACE:%' OR account LIKE 'SIM_ADVANCE_EXPOSURE:%'
 THEN SUM(CASE side WHEN 'debit' THEN amount ELSE -amount END)
 ELSE SUM(CASE side WHEN 'credit' THEN amount ELSE -amount END) END AS balance
 FROM expected_lines GROUP BY account;
"""


def _load(connection, rows):
    connection.execute('PRAGMA temp_store=MEMORY')
    # DDL is fixed, generated solely from the constant schema descriptions.
    for name, schema in _SCHEMAS.items():
        columns = []
        for field in schema.split(', '):
            key, kind = field.split()
            if kind == 'I':
                columns.append(f"{key} INTEGER NOT NULL CHECK(typeof({key})='integer' AND {key}>=0)")
            else:
                columns.append(f"{key} TEXT NOT NULL CHECK(typeof({key})='text')")
        connection.execute(f'CREATE TABLE {name} ({", ".join(columns)})')
    with connection:
        for name, group in rows.items():
            count = len(_SCHEMAS[name].split(', '))
            connection.executemany(f'INSERT INTO {name} VALUES ({",".join("?" for _ in range(count))})', group)
    # executescript commits an outstanding transaction; all inserts above have
    # already been atomically committed, before creating read-only views.
    connection.executescript(_VIEWS)


def _checks(db, check):
    def empty(check_id, sql, detail):
        return check(check_id, not db.execute(sql).fetchall(), detail)
    def same(check_id, source, exported):
        # Compare full ordered multisets: duplicates must never disappear through
        # DISTINCT, dictionaries, EXCEPT, or conflict-ignore insertion.
        check(check_id, sorted(db.execute(source).fetchall()) == sorted(db.execute(exported).fetchall()),
              'SQL rows and exact integers compared, including multiplicity')
    if not empty('claim_constraints', """
      SELECT claim_id FROM claims c WHERE claim_id<>settlement_id OR gross<>fixture_gross OR gross<=0
      OR refund_face<>refund_accepted+refund_outstanding OR refund_face>gross
      OR NOT EXISTS(SELECT 1 FROM payees p WHERE p.claim_id=c.claim_id)
      OR gross<>(SELECT SUM(face) FROM payees p WHERE p.claim_id=c.claim_id)
      UNION ALL SELECT claim_id FROM payees WHERE face<=0
      UNION ALL SELECT claim_id FROM payees GROUP BY claim_id,payee HAVING COUNT(*)<>1
    """, 'claim identity, positive gross/faces, unique payees, face and refund conservation'):
        return
    if not empty('journal_identity', """
      SELECT txn_id FROM journal GROUP BY txn_id HAVING COUNT(*)<>1
      UNION ALL SELECT advance_id FROM journal WHERE op='offer' GROUP BY advance_id HAVING COUNT(*)<>1
      UNION ALL SELECT repay_id FROM journal WHERE op='repay' GROUP BY advance_id,repay_id HAVING COUNT(*)<>1
      UNION ALL SELECT txn_id FROM journal WHERE txn_id IN (SELECT txn_id FROM expected_headers WHERE source='EVIDENCE')
    """, 'unique source events, offers and per-advance repayment identities'):
        return
    if not empty('journal_principal', """
      SELECT txn_id FROM journal j WHERE
      (op IN ('offer','repay') AND amount<=0)
      OR (op<>'offer' AND (SELECT COUNT(*) FROM journal o WHERE o.op='offer'
          AND o.advance_id=j.advance_id AND o.position<j.position)<>1)
      OR (op='draw' AND (SELECT COUNT(*) FROM journal d WHERE d.op='draw' AND d.advance_id=j.advance_id)<>1)
      OR (op='repay' AND ((SELECT COUNT(*) FROM journal d WHERE d.op='draw' AND d.advance_id=j.advance_id AND d.position<j.position)<>1
          OR sequence<>(SELECT COUNT(*) FROM journal r WHERE r.op='repay' AND r.advance_id=j.advance_id AND r.position<=j.position)
          OR (SELECT SUM(r.amount) FROM journal r WHERE r.op='repay' AND r.advance_id=j.advance_id AND r.position<=j.position)
             >(SELECT o.amount FROM journal o WHERE o.op='offer' AND o.advance_id=j.advance_id)))
    """, 'positive offers/repayments, ordered references, one draw, repayment sequence and remaining principal'):
        return
    same('principal_projection', 'SELECT * FROM expected_advances', 'SELECT * FROM exported_advances')
    claim_query = 'SELECT claim_id,phase,gross,confirmed_cash,refund_face,refund_outstanding FROM posted_claims'
    check('claim_projection', sorted(db.execute(claim_query).fetchall()) == sorted(db.execute('SELECT * FROM exported_claims').fetchall())
          and sorted(db.execute('SELECT p.* FROM payees p JOIN posted_claims c ON c.claim_id=p.claim_id').fetchall())
          == sorted(db.execute('SELECT * FROM exported_payees').fetchall()), 'V1 claim and payee rows compared with multiplicity')
    for kind, source, fields in (
        ('exposure', 'expected_advances', 'drawn,repaid,outstanding'),
        ('settlement', 'claims', 'confirmed_cash,distributed_cash'),
        ('refund', 'claims', 'refund_face,refund_accepted,refund_outstanding'),
    ):
        identity = 'advance_id' if kind == 'exposure' else 'claim_id,phase' if kind == 'settlement' else 'claim_id'
        actual = db.execute(f'SELECT {identity},{fields} FROM {source}').fetchall()
        expected = db.execute(f'SELECT * FROM statement_{kind}').fetchall()
        sums = ','.join(f'COALESCE(SUM({field}),0)' for field in fields.split(','))
        totals = db.execute(f'SELECT {sums} FROM {source}').fetchall()
        check('statement_' + kind, sorted(actual) == sorted(expected)
              and totals == db.execute(f'SELECT * FROM statement_{kind}_total').fetchall(),
              'SQL rows and aggregate totals compared; all fixtures for settlement/refund')
    same('transaction_headers', 'SELECT * FROM expected_headers', 'SELECT * FROM exported_headers')
    same('posting_lines', 'SELECT * FROM expected_lines', 'SELECT * FROM exported_lines')
    same('account_totals', 'SELECT * FROM expected_accounts', 'SELECT * FROM exported_accounts')
    empty('step_balance', """
      SELECT h.position FROM exported_headers h LEFT JOIN exported_lines l ON l.entry_position=h.position
      GROUP BY h.position HAVING COALESCE(SUM(CASE l.side WHEN 'debit' THEN l.amount ELSE -l.amount END),0)<>0
    """, 'every header included, including zero-line transactions; debit equals credit')


def _report(raw=None):
    return {'format': 'KIX_CAPITAL_SQL_AUDIT_V1', 'ok': False, 'reason': None,
            'label': 'SIMULATED', 'locality': 'LOCAL_ONLY', 'accounting_policy': 'SYNTHETIC_UNADOPTED',
            'funds_executed': False, 'stage7_authenticated_export': 'NOT_BOUND', 'external_assurance': 'NOT_BOUND',
            'input_sha256': hashlib.sha256(raw).hexdigest() if type(raw) is bytes else None,
            'digests': {}, 'scope': {'chart': 'SIMULATION_FIXED_V1', 'posting_claims': list(POSTED_CLAIMS),
                                   'statement_fixtures': 'ALL_EMBEDDED', 'overlay_accounting': 'NOT_CHECKED',
                                   'approved_reserved_categories': 'NOT_CHECKED',
                                   'source_authentication': 'NOT_BOUND', 'completeness': 'NOT_BOUND',
                                   'money_max_atoms': MONEY_MAX, 'sqlite_integer_max': MAX_INT},
            'checks': [{'id': name, 'status': 'NOT_CHECKED', 'detail': None} for name in CHECK_IDS]}


def audit_bytes(raw: bytes) -> dict:
    """Verify first, then audit exact embedded integers; always return a report."""
    report = _report(raw)
    stage = 'json'
    def check(name, matched, detail):
        row = next(row for row in report['checks'] if row['id'] == name)
        row.update(status='MATCHED' if matched else 'MISMATCH', detail=detail)
        if not matched and report['reason'] is None:
            report['reason'] = name
        return matched
    try:
        pack = _loads(raw)
        check(stage, True, 'strict UTF-8 JSON; integer tokens only')
        stage = 'integrity'
        integrity = evidence.verify_pack(pack)
        _require(integrity['ok'], integrity['reason'])
        check(stage, True, 'pack and embedded manifest hashes verified; authentication NOT_BOUND')
        stage = 'eligibility'
        manifest, sections = _eligibility(pack)
        report['digests'] = {'pack': pack['content_digest'], 'manifest': manifest['content_digest'],
                             'pack_sections': {k: v['sha256'] for k, v in pack['sections'].items()},
                             'manifest_sections': {k: v['sha256'] for k, v in manifest['sections'].items()},
                             'fixtures': sections['fixtures']['fixtures_digest']}
        check(stage, True, 'complete supported V2/V3 pack; V1 chart and pinned KRW/source')
        stage = 'fixture_digest'
        _require(sections['fixtures']['fixtures_digest'] == export.sha256_hex(sections['fixtures']['rows']),
                 'FIXTURE_DIGEST_MISMATCH')
        check(stage, True, 'declared fixture digest matches embedded row bytes')
        stage = 'shape_and_bounds'
        rows = _rows(sections)
        check(stage, True, 'typed facts and conservative signed-int64 arithmetic budget validated')
        connection = sqlite3.connect(':memory:')
        try:
            _load(connection, rows)
            _checks(connection, check)
            if report['reason'] is None:
                report['totals'] = dict(zip(('drawn', 'repaid', 'outstanding'), connection.execute(
                    'SELECT COALESCE(SUM(drawn),0),COALESCE(SUM(repaid),0),COALESCE(SUM(outstanding),0) FROM expected_advances').fetchone()))
                debit, credit = connection.execute('SELECT COALESCE(SUM(debit_total),0),COALESCE(SUM(credit_total),0) FROM expected_accounts').fetchone()
                report['totals'].update(debit=debit, credit=credit)
        finally:
            connection.close()
        report['ok'] = report['reason'] is None
    except (AuditError, ValueError, UnicodeError, RecursionError, KeyError, TypeError, OverflowError, sqlite3.Error) as exc:
        # Never leave successful aggregate results on a failed audit.
        report.pop('totals', None)
        check(stage, False, str(exc) if isinstance(exc, AuditError) else 'MALFORMED_OR_UNSUPPORTED_INPUT')
    return report


def audit_path(path) -> dict:
    """Read the input once. No sidecars, keys, locks, server or output files."""
    try:
        raw = Path(path).read_bytes()
    except (OSError, ValueError, TypeError):
        report = _report()
        report['reason'] = 'INPUT_UNREADABLE'
        return report
    return audit_bytes(raw)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='LOCAL_ONLY / SYNTHETIC_UNADOPTED SQLite evidence-pack cross-check')
    parser.add_argument('file', help='offline KIX_CAPITAL_EVIDENCE_PACK_V1 JSON')
    args = parser.parse_args(argv)
    report = audit_path(args.file)
    sys.stdout.write(json.dumps(report, sort_keys=True, separators=(',', ':')) + '\n')
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
