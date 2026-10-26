"""Hash-consistent semantic mutants for the offline, synthetic SQL cross-check."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from capital import evidence, export, sql_audit as audit
from capital.service import CapitalService

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / 'tests/vectors/pack/clean.json'


def manifest(pack):
    return pack['sections']['export_manifest']['body']['document']


def body(pack, name):
    return manifest(pack)['sections'][name]['body']


def reseal(pack):
    """Repair every affected hash; never use the auditor as the mutant oracle."""
    embedded = manifest(pack)
    fixtures = body(pack, 'fixtures')
    fixtures['fixtures_digest'] = export.sha256_hex(fixtures['rows'])
    for section in embedded['sections'].values():
        section['sha256'] = export.sha256_hex(section['body'])
    embedded['content_digest'] = export.content_digest(embedded)
    for section in pack['sections'].values():
        section['sha256'] = export.sha256_hex(section['body'])
    pack['content_digest'] = evidence.content_digest(pack)
    return evidence.dump(pack)


class SqlAuditTests(unittest.TestCase):
    def setUp(self):
        self.pack = json.loads(CLEAN.read_bytes())

    def assert_mutant(self, check_id, *, detail=None):
        raw = reseal(self.pack)
        verified = evidence.verify_pack(json.loads(raw))
        self.assertTrue(verified['ok'], verified)
        result = audit.audit_bytes(raw)
        self.assertFalse(result['ok'], result)
        self.assertNotIn('totals', result)
        checks = {row['id']: row for row in result['checks']}
        self.assertEqual(checks['integrity']['status'], 'MATCHED')
        self.assertEqual(checks[check_id]['status'], 'MISMATCH', result)
        if detail:
            self.assertEqual(checks[check_id]['detail'], detail)
        return result

    def test_seed_exact_totals_and_deterministic_report(self):
        raw = CLEAN.read_bytes()
        result = audit.audit_bytes(raw)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result, audit.audit_path(CLEAN))
        self.assertEqual(result['totals'], dict(drawn=65000, repaid=20000, outstanding=45000, debit=385000, credit=385000))
        self.assertTrue(all(row['status'] == 'MATCHED' for row in result['checks']))
        self.assertEqual(result['input_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result['digests']['pack'], self.pack['content_digest'])
        self.assertEqual(result['digests']['manifest'], manifest(self.pack)['content_digest'])
        self.assertEqual(result['digests']['pack_sections'], {k: v['sha256'] for k, v in self.pack['sections'].items()})
        self.assertEqual(result['digests']['manifest_sections'], {k: v['sha256'] for k, v in manifest(self.pack)['sections'].items()})
        self.assertEqual(result['locality'], 'LOCAL_ONLY')
        self.assertEqual(result['accounting_policy'], 'SYNTHETIC_UNADOPTED')
        self.assertFalse(result['funds_executed'])
        self.assertEqual(result['stage7_authenticated_export'], 'NOT_BOUND')
        self.assertEqual(result['external_assurance'], 'NOT_BOUND')

    def test_empty_journal_book(self):
        # A fresh service provides a genuine empty-journal V2 manifest. The
        # auditor receives bytes only and never restores or invokes that service.
        empty = CapitalService().export_manifest()
        self.assertEqual(empty['sections']['journal']['body']['entries'], [])
        self.pack['sections']['export_manifest']['body']['document'] = empty
        result = audit.audit_bytes(reseal(self.pack))
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['totals'], dict(drawn=0, repaid=0, outstanding=0, debit=300000, credit=300000))

    def test_multiple_repayments_and_cumulative_principal_limit(self):
        service = CapitalService()
        for index, (op, args) in enumerate((
            ('offer', {'fixture_id': 'sim-committed', 'amount': 60000}),
            ('approve', {}), ('bind_settlement', {}), ('draw', {}),
            ('repay', {'amount': 20000, 'sequence': 1}),
            ('repay', {'amount': 40000, 'sequence': 2}), ('close', {}),
        )):
            receipt = service.execute({'instance_id': service.instance_id,
                                       'operation_id': 'multi-' + str(index),
                                       'op': op, 'advance_id': 'sim-multi', 'args': args})
            self.assertEqual(receipt['outcome'], 'ACCEPTED', receipt)
        self.pack['sections']['export_manifest']['body']['document'] = service.export_manifest()
        result = audit.audit_bytes(reseal(self.pack))
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['totals'], dict(drawn=60000, repaid=60000, outstanding=0,
                                              debit=420000, credit=420000))
        # Each payment is below the offer, but their cumulative sum exceeds it.
        body(self.pack, 'journal')['entries'][5]['body']['amount'] += 1
        self.assert_mutant('journal_principal')

    def test_independent_of_projection_reconciliation_and_service_restore(self):
        raw = CLEAN.read_bytes()
        with mock.patch('capital.projection.SimulationProjection.project', side_effect=AssertionError('projection called')), \
             mock.patch('capital.recon.build_reconciliation', side_effect=AssertionError('reconciliation called')), \
             mock.patch('capital.service.CapitalService.__init__', side_effect=AssertionError('service restored')):
            self.assertTrue(audit.audit_bytes(raw)['ok'])

    def test_bad_hash_never_opens_sqlite(self):
        body(self.pack, 'journal')['entries'][0]['body']['amount'] += 1
        with mock.patch.object(audit.sqlite3, 'connect', side_effect=AssertionError('opened before verification')) as connect:
            result = audit.audit_bytes(evidence.dump(self.pack))
        connect.assert_not_called()
        self.assertEqual(result['reason'], 'integrity')
        self.assertTrue(all(row['status'] == 'NOT_CHECKED' for row in result['checks'][2:]))

    def test_rehashed_stale_fixture_digest_never_opens_sqlite(self):
        # The shared verifier covers section bytes, but does not check this
        # declared digest's relationship to the rows within its section.
        fixtures = body(self.pack, 'fixtures')
        fixtures['rows']['sim-pending']['claim']['confirmed_cash'] += 1
        embedded = manifest(self.pack)
        section = embedded['sections']['fixtures']
        section['sha256'] = export.sha256_hex(section['body'])
        embedded['content_digest'] = export.content_digest(embedded)
        section = self.pack['sections']['export_manifest']
        section['sha256'] = export.sha256_hex(section['body'])
        self.pack['content_digest'] = evidence.content_digest(self.pack)
        raw = evidence.dump(self.pack)
        self.assertTrue(evidence.verify_pack(json.loads(raw))['ok'])
        with mock.patch.object(audit.sqlite3, 'connect', side_effect=AssertionError('stale digest')) as connect:
            result = audit.audit_bytes(raw)
        connect.assert_not_called()
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'fixture_digest')
        self.assertNotIn('totals', result)

    def test_required_labels_and_section_no_real_effect(self):
        base = copy.deepcopy(self.pack)
        for section, key, value in (
            ('statement', 'label', 'REAL'),
            ('statement', 'diagnostic', 'EXTERNAL_ASSURANCE'),
            ('statement', 'mode', 'OPERATING_LEDGER'),
            ('projection', 'mode', 'LOCAL_PROJECTION_COA_CANDIDATE'),
            ('journal', 'funds_executed', True),
            ('fixtures', 'bank_debit_observed', True),
        ):
            with self.subTest(section=section, key=key):
                self.pack = copy.deepcopy(base)
                body(self.pack, section)[key] = value
                with mock.patch.object(audit.sqlite3, 'connect', side_effect=AssertionError('ineligible')):
                    self.assert_mutant('eligibility')

    def test_balanced_wrong_projection_lines_and_accounts(self):
        projection = body(self.pack, 'projection')
        entry = next(e for e in projection['entries'] if e['txn_id'] == 'op-defaulted-draw')
        for line in entry['lines']:
            line['amount'] += 1
        for account in projection['accounts']:
            if account['code'].endswith(':sim-defaulted'):
                account['debit_total' if 'EXPOSURE' in account['code'] else 'credit_total'] += 1
                account['balance'] += 1
        result = self.assert_mutant('posting_lines')
        self.assertEqual(next(c for c in result['checks'] if c['id'] == 'step_balance')['status'], 'MATCHED')

    def test_conserved_but_wrong_principal_projection(self):
        advance = next(a for a in body(self.pack, 'projection')['read_model']['advances'] if a['advance_id'] == 'sim-defaulted')
        advance['drawn'] += 1
        advance['outstanding'] += 1
        self.assert_mutant('principal_projection')

    def test_offsetting_projection_rows_do_not_hide_behind_totals(self):
        advances = body(self.pack, 'projection')['read_model']['advances']
        for name, delta in (('sim-defaulted', 1), ('sim-unbound', -1)):
            row = next(a for a in advances if a['advance_id'] == name)
            row['drawn'] += delta
            row['outstanding'] += delta
        self.assert_mutant('principal_projection')

    def test_duplicate_source_event(self):
        journal = body(self.pack, 'journal')['entries']
        journal.insert(2, copy.deepcopy(journal[1]))
        result = self.assert_mutant('journal_identity')
        self.assertEqual(next(c for c in result['checks'] if c['id'] == 'posting_lines')['status'], 'NOT_CHECKED')

    def test_duplicate_offer_with_different_event_identity(self):
        journal = body(self.pack, 'journal')['entries']
        duplicate = copy.deepcopy(journal[0])
        duplicate['idempotency_key'] = 'extra-offer'
        journal.append(duplicate)
        self.assert_mutant('journal_identity')

    def test_claim_total_and_fixture_gross_constraints(self):
        base = copy.deepcopy(self.pack)
        for mutation in ('fixture_gross', 'claim_gross', 'face', 'zero_gross', 'zero_face', 'empty', 'duplicate', 'refund_sum', 'refund_above_gross'):
            with self.subTest(mutation=mutation):
                self.pack = copy.deepcopy(base)
                view = body(self.pack, 'fixtures')['rows']['sim-refund']
                claim = view['claim']
                if mutation == 'fixture_gross':
                    view['gross'] += 1
                elif mutation == 'claim_gross':
                    claim['gross'] += 1
                elif mutation == 'face':
                    claim['obligations'][0]['face'] += 1
                elif mutation == 'zero_gross':
                    claim['gross'] = view['gross'] = 0
                elif mutation == 'zero_face':
                    claim['obligations'][0]['face'] = 0
                    claim['obligations'][1]['face'] = claim['gross']
                elif mutation == 'empty':
                    claim['obligations'] = []
                elif mutation == 'duplicate':
                    claim['obligations'].append(copy.deepcopy(claim['obligations'][0]))
                elif mutation == 'refund_sum':
                    claim['refund_accepted'] += 1
                else:
                    claim['refund_face'] = claim['refund_outstanding'] = claim['gross'] + 1
                self.assert_mutant('claim_constraints')

    def test_source_constraint_even_when_exported_claim_is_also_changed(self):
        view = body(self.pack, 'fixtures')['rows']['sim-refund']
        claim = view['claim']
        claim['refund_face'] = claim['refund_outstanding'] = claim['gross'] + 1
        exported = next(c for c in body(self.pack, 'projection')['read_model']['claims'] if c['claim_id'] == 'sim-refund')
        exported['refund_face'] = exported['refund_outstanding'] = claim['refund_face']
        category = next(c for c in body(self.pack, 'statement')['categories'] if c['id'] == 'refund')
        row = next(c for c in category['rows'] if c['claim_id'] == 'sim-refund')
        for key in ('refund_face', 'refund_outstanding'):
            category[key] += claim[key] - row[key]
            row[key] = claim[key]
        self.assert_mutant('claim_constraints')

    def test_wrong_exported_claim_and_payee(self):
        base = copy.deepcopy(self.pack)
        for target in ('claim', 'payee', 'duplicate_claim', 'duplicate_payee'):
            with self.subTest(target=target):
                self.pack = copy.deepcopy(base)
                claims = body(self.pack, 'projection')['read_model']['claims']
                if target == 'claim':
                    claims[0]['gross'] += 1
                elif target == 'payee':
                    claims[0]['obligations'][0]['face'] += 1
                elif target == 'duplicate_claim':
                    claims.append(copy.deepcopy(claims[0]))
                else:
                    claims[0]['obligations'].append(copy.deepcopy(claims[0]['obligations'][0]))
                self.assert_mutant('claim_projection')

    def test_journal_principal_constraints(self):
        base = copy.deepcopy(self.pack)
        for target in ('zero_offer', 'zero_repay', 'excess_repay', 'sequence', 'repay_before_draw', 'draw_before_offer', 'double_draw'):
            with self.subTest(target=target):
                self.pack = copy.deepcopy(base)
                journal = body(self.pack, 'journal')['entries']
                if target == 'zero_offer':
                    journal[0]['body']['amount'] = 0
                elif target == 'zero_repay':
                    journal[4]['body']['amount'] = 0
                elif target == 'excess_repay':
                    journal[4]['body']['amount'] = 20001
                elif target == 'sequence':
                    journal[4]['body']['sequence'] = 2
                elif target == 'repay_before_draw':
                    journal[3], journal[4] = journal[4], journal[3]
                elif target == 'draw_before_offer':
                    journal[0], journal[3] = journal[3], journal[0]
                else:
                    duplicate = copy.deepcopy(journal[3])
                    duplicate['idempotency_key'] = 'extra-draw'
                    journal.append(duplicate)
                self.assert_mutant('journal_principal')

    def test_duplicate_repayment_identity_and_order(self):
        journal = body(self.pack, 'journal')['entries']
        journal[4]['body']['amount'] = 10000
        duplicate = copy.deepcopy(journal[4])
        duplicate['idempotency_key'] = 'another-repay'
        duplicate['body']['sequence'] = 2
        journal.insert(5, duplicate)
        self.assert_mutant('journal_identity')

    def test_empty_transaction_header_mutants(self):
        base = copy.deepcopy(self.pack)
        for index in (3, 4, 5, 8):  # offer, approval, binding, terminal close
            for mutation in ('delete', 'duplicate', 'reorder', 'relabel', 'advance', 'missing_advance', 'step'):
                with self.subTest(index=index, mutation=mutation):
                    self.pack = copy.deepcopy(base)
                    entries = body(self.pack, 'projection')['entries']
                    self.assertEqual(entries[index]['lines'], [])
                    if mutation == 'delete':
                        entries.pop(index)
                    elif mutation == 'duplicate':
                        entries.insert(index, copy.deepcopy(entries[index]))
                    elif mutation == 'reorder':
                        entries[index], entries[index+1] = entries[index+1], entries[index]
                    elif mutation == 'relabel':
                        entries[index]['txn_id'] = 'false-empty-transaction'
                    elif mutation == 'advance':
                        entries[index]['advance_id'] = 'other'
                    elif mutation == 'missing_advance':
                        del entries[index]['advance_id']
                    else:
                        entries[index]['step'] += 1
                    self.assert_mutant('transaction_headers')

    def test_statement_rows_totals_and_duplicates(self):
        base = copy.deepcopy(self.pack)
        for kind, field in (('exposure', 'drawn'), ('settlement', 'confirmed_cash'), ('refund', 'refund_face')):
            for mutation in ('row', 'total', 'duplicate'):
                with self.subTest(kind=kind, mutation=mutation):
                    self.pack = copy.deepcopy(base)
                    cat = next(c for c in body(self.pack, 'statement')['categories'] if c['id'] == kind)
                    if mutation == 'row':
                        cat['rows'][0][field] += 1
                    elif mutation == 'duplicate':
                        cat['rows'].append(copy.deepcopy(cat['rows'][0]))
                    else:
                        cat['confirmed' if kind == 'settlement' else field] += 1
                    self.assert_mutant('statement_' + kind)

    def test_all_fixture_scope_including_non_posted_claim(self):
        view = body(self.pack, 'fixtures')['rows']['demo-alpha-arena']
        view['claim']['confirmed_cash'] += 1
        self.assert_mutant('statement_settlement')

    def test_posting_line_order_side_and_duplicates(self):
        base = copy.deepcopy(self.pack)
        for mutation in ('order', 'account', 'side', 'duplicate'):
            with self.subTest(mutation=mutation):
                self.pack = copy.deepcopy(base)
                lines = body(self.pack, 'projection')['entries'][0]['lines']
                if mutation == 'order':
                    lines[1], lines[2] = lines[2], lines[1]
                elif mutation == 'account':
                    lines[1]['account'] += '-other'
                elif mutation == 'side':
                    lines[1]['side'] = 'debit'
                else:
                    lines.append(copy.deepcopy(lines[1]))
                self.assert_mutant('posting_lines')

    def test_account_totals_balance_identity_and_duplicates(self):
        base = copy.deepcopy(self.pack)
        for mutation in ('debit_total', 'credit_total', 'balance', 'code', 'kind', 'duplicate'):
            with self.subTest(mutation=mutation):
                self.pack = copy.deepcopy(base)
                rows = body(self.pack, 'projection')['accounts']
                if mutation == 'duplicate':
                    rows.append(copy.deepcopy(rows[0]))
                elif mutation in ('code', 'kind'):
                    rows[0][mutation] += '-other'
                else:
                    rows[0][mutation] += 1
                self.assert_mutant('account_totals')

    def test_strict_number_types_and_monetary_bounds(self):
        base = copy.deepcopy(self.pack)
        for value in (True, False, '20000', -1, audit.MONEY_MAX+1):
            with self.subTest(value=value):
                self.pack = copy.deepcopy(base)
                body(self.pack, 'journal')['entries'][0]['body']['amount'] = value
                self.assert_mutant('shape_and_bounds')

    def test_individual_boundary_and_boundary_minus_one(self):
        base = copy.deepcopy(self.pack)
        for amount in (audit.MONEY_MAX-1, audit.MONEY_MAX):
            self.pack = copy.deepcopy(base)
            body(self.pack, 'journal')['entries'][11]['body']['amount'] = amount  # undrawn rejected offer
            row = next(r for r in body(self.pack, 'projection')['read_model']['advances'] if r['advance_id'] == 'sim-rejected')
            row['amount'] = amount
            result = audit.audit_bytes(reseal(self.pack))
            self.assertTrue(result['ok'], result)

    def test_aggregate_budget_before_sql_connection(self):
        cat = next(c for c in body(self.pack, 'statement')['categories'] if c['id'] == 'exposure')
        cat['drawn'] = audit.MAX_INT
        with mock.patch.object(audit.sqlite3, 'connect', side_effect=AssertionError('budget must precede SQLite')):
            self.assert_mutant('shape_and_bounds', detail='ARITHMETIC_BUDGET_EXCEEDED')

    def test_draw_at_monetary_bound_keeps_aggregate_exact(self):
        amount = audit.MONEY_MAX
        delta = amount - 30000
        journal = body(self.pack, 'journal')['entries']
        next(j for j in journal if j['op'] == 'offer' and j['advance_id'] == 'sim-defaulted')['body']['amount'] = amount
        projection = body(self.pack, 'projection')
        advance = next(a for a in projection['read_model']['advances'] if a['advance_id'] == 'sim-defaulted')
        for key in ('amount', 'drawn', 'outstanding'):
            advance[key] = amount
        for entry in projection['entries']:
            if entry['txn_id'] == 'op-defaulted-draw':
                for line in entry['lines']:
                    line['amount'] = amount
        for account in projection['accounts']:
            if account['code'].endswith(':sim-defaulted'):
                account['debit_total' if 'EXPOSURE' in account['code'] else 'credit_total'] = amount
                account['balance'] = amount
        exposure = next(c for c in body(self.pack, 'statement')['categories'] if c['id'] == 'exposure')
        row = next(a for a in exposure['rows'] if a['advance_id'] == 'sim-defaulted')
        for key in ('drawn', 'outstanding'):
            row[key] = amount
            exposure[key] += delta
        raw = reseal(self.pack)
        self.assertTrue(evidence.verify_pack(json.loads(raw))['ok'])
        result = audit.audit_bytes(raw)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['totals']['drawn'], amount+35000)
        self.assertEqual(result['totals']['debit'], 385000+delta)
        self.assertTrue(all(type(v) is int for v in result['totals'].values()))

    def test_transaction_text_is_bound_as_data(self):
        txn_id = "x');DROP_TABLE_journal;--"
        body(self.pack, 'journal')['entries'][0]['idempotency_key'] = txn_id
        body(self.pack, 'projection')['entries'][3]['txn_id'] = txn_id
        raw = reseal(self.pack)
        self.assertTrue(evidence.verify_pack(json.loads(raw))['ok'])
        result = audit.audit_bytes(raw)
        self.assertTrue(result['ok'], result)

    def test_unreadable_and_unsupported_path_arguments(self):
        for path in (None, [], '\0', ROOT):
            with self.subTest(path=path):
                result = audit.audit_path(path)
                self.assertEqual(result['reason'], 'INPUT_UNREADABLE')
                self.assertFalse(result['ok'])
                self.assertNotIn('totals', result)

    def test_reject_bad_json_before_hashing_or_sql(self):
        for raw in (b'{', b'[]', b'\xff', b'\xef\xbb\xbf{}', b'{"x":1,"x":2}',
                    br'{"x":1,"\u0078":2}', b'{"x":1.0}', b'{"x":1e0}', b'{"x":NaN}',
                    b'{"x":Infinity}', b'{"x":-Infinity}', b'{}\0', b'{} trailing',
                    br'{"x":"\u0000"}', br'{"x":"\ud800"}'):
            with self.subTest(raw=raw), mock.patch.object(audit.sqlite3, 'connect', side_effect=AssertionError('opened')):
                result = audit.audit_bytes(raw)
                self.assertFalse(result['ok'])
                self.assertNotIn('totals', result)

    def test_unsupported_eligibility_and_part_tags(self):
        base = copy.deepcopy(self.pack)
        for mutation in ('incomplete_pack', 'incomplete_manifest', 'unavailable', 'chart', 'asset', 'pin', 'manifest_tag', 'pack_tag', 'real_effect'):
            with self.subTest(mutation=mutation):
                self.pack = copy.deepcopy(base)
                if mutation == 'incomplete_pack':
                    self.pack['status'] = 'INCOMPLETE'
                elif mutation == 'incomplete_manifest':
                    manifest(self.pack)['status'] = 'INCOMPLETE'
                elif mutation == 'unavailable':
                    body(self.pack, 'fixtures')['status'] = 'UNAVAILABLE'
                elif mutation == 'chart':
                    body(self.pack, 'projection')['chart'] = 'SIMULATION_FIXED_V2'
                elif mutation == 'asset':
                    body(self.pack, 'source_pin')['assets'][0]['decimals'] = False
                elif mutation == 'pin':
                    body(self.pack, 'source_pin')['commit'] = 'unknown'
                elif mutation == 'manifest_tag':
                    body(self.pack, 'journal')['part_tag'] = 'wrongpart'
                elif mutation == 'pack_tag':
                    self.pack['sections']['decisions']['body']['part_tag'] = 'wrongpart'
                else:
                    self.pack['funds_executed'] = True
                with mock.patch.object(audit.sqlite3, 'connect', side_effect=AssertionError('ineligible')):
                    self.assert_mutant('eligibility')

    def test_malformed_shapes_and_no_real_effect(self):
        base = copy.deepcopy(self.pack)
        for mutation in ('journal', 'obligations', 'advance', 'identifier', 'phase', 'fixture_key', 'flag', 'body_flag', 'missing', 'category'):
            with self.subTest(mutation=mutation):
                self.pack = copy.deepcopy(base)
                if mutation == 'journal':
                    body(self.pack, 'journal')['entries'] = {}
                elif mutation == 'obligations':
                    body(self.pack, 'fixtures')['rows']['sim-pending']['claim']['obligations'] = None
                elif mutation == 'advance':
                    body(self.pack, 'projection')['read_model']['advances'][0] = []
                elif mutation == 'identifier':
                    body(self.pack, 'journal')['entries'][0]['advance_id'] = 'bad:id'
                elif mutation == 'phase':
                    body(self.pack, 'fixtures')['rows']['sim-pending']['phase'] = ''
                elif mutation == 'fixture_key':
                    rows = body(self.pack, 'fixtures')['rows']
                    rows['other'] = rows.pop('sim-pending')
                elif mutation == 'flag':
                    body(self.pack, 'fixtures')['rows']['sim-pending']['claim']['legal_debtor_bound'] = True
                elif mutation == 'body_flag':
                    body(self.pack, 'journal')['entries'][0]['body']['funds_executed'] = True
                elif mutation == 'missing':
                    del body(self.pack, 'projection')['accounts'][0]['balance']
                else:
                    body(self.pack, 'statement')['categories'].append(copy.deepcopy(body(self.pack, 'statement')['categories'][0]))
                self.assert_mutant('shape_and_bounds')

    def test_v3_overlay_hashes_verified_but_accounting_excluded(self):
        # Genuine V3 export with a nonempty simulated overlay.
        from tests.test_overlay_export import ticked_service
        self.pack['sections']['export_manifest']['body']['document'] = ticked_service().export_manifest()
        raw = reseal(self.pack)
        self.assertEqual(manifest(self.pack)['format'], export.FORMAT_V3)
        result = audit.audit_bytes(raw)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['scope']['overlay_accounting'], 'NOT_CHECKED')
        body(self.pack, 'overlay')['sim_day'] += 1
        section = self.pack['sections']['export_manifest']
        section['sha256'] = export.sha256_hex(section['body'])
        self.pack['content_digest'] = evidence.content_digest(self.pack)
        result = audit.audit_bytes(evidence.dump(self.pack))
        self.assertEqual(result['reason'], 'integrity')

    def test_memory_only_sql_and_unconditional_cleanup(self):
        connections = []
        class TrackingConnection(sqlite3.Connection):
            def close(self):
                self.was_closed = True
                super().close()
        real_connect = sqlite3.connect
        def connect(name):
            self.assertEqual(name, ':memory:')
            db = real_connect(name, factory=TrackingConnection)
            db.was_closed = False
            connections.append(db)
            return db
        with mock.patch.object(audit.sqlite3, 'connect', side_effect=connect):
            self.assertTrue(audit.audit_path(CLEAN)['ok'])
            with mock.patch.object(audit, '_checks', side_effect=audit.AuditError('forced load failure')):
                self.assertFalse(audit.audit_path(CLEAN)['ok'])
        self.assertEqual(len(connections), 2)
        self.assertTrue(all(db.was_closed for db in connections))

    def test_cli_exits_determinism_and_no_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'pack.json'
            raw = CLEAN.read_bytes()
            path.write_bytes(raw)
            before = (path.stat().st_mtime_ns, path.read_bytes(), sorted(Path(directory).iterdir()))
            def run(*args):
                return subprocess.run([sys.executable, '-m', 'capital.sql_audit', *map(str, args)],
                                      cwd=ROOT, capture_output=True, timeout=30)
            result = run(path)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), audit.audit_bytes(raw))
            self.assertEqual(before, (path.stat().st_mtime_ns, path.read_bytes(), sorted(Path(directory).iterdir())))
            self.assertEqual(run().returncode, 2)
            self.assertEqual(run(path, '--out', 'other').returncode, 2)
            self.assertEqual(run(path.parent / 'missing').returncode, 1)
            path.write_bytes(b'{')
            self.assertEqual(run(path).returncode, 1)
            path.write_bytes(reseal(self.pack))
            body(self.pack, 'projection')['accounts'][0]['balance'] += 1
            path.write_bytes(reseal(self.pack))
            self.assertEqual(run(path).returncode, 1)
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()), ['pack.json'])

    def test_main_callable(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(audit.main([str(CLEAN)]), 0)
        self.assertTrue(json.loads(out.getvalue())['ok'])


if __name__ == '__main__':
    unittest.main()
