#!/usr/bin/env python3
"""SIMULATED relocation of stopped, disposable LOCAL_FILE_WORKSPACE books.

No live workspace argument, backup service, live copying, repair, or DR claim.
Only stdlib, the bundled zipapp, and explicitly staged synthetic inputs are used.
"""
from __future__ import annotations

import sys

if __name__ == '__main__':
    # Even import caches must not write into the checkout during a CLI rehearsal.
    sys.dont_write_bytecode = True

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_release, smoke_release as release
from scripts.seed_overlay_slices import APPROVALS
from capital import overlay
from capital.audit import CHECK_ORDER, audit_workspace_bytes
from capital.keyset import DEV_KEYSET_NAME, load_dev_keyset
from capital.store import FILE_NAME, LOCK_NAME, canonical_bytes
from capital.verify import verify_manifest

CASES = ('unsigned', 'dev-keyset')
FORMAT = 'KIX_CAPITAL_RELOCATION_REHEARSAL_V1'
LIMITATIONS = [
    'SIMULATED synthetic books; funds_executed=false; immutable READ_ONLY_FIXTURE inputs.',
    'LOCAL_FILE_WORKSPACE on one host only; CAP-11 and stage5 durable transactions NOT_BOUND.',
    'Stopped writer only; no backup service, live snapshot copying, or automatic repair.',
    'No disaster-recovery certification or cross-host fencing.',
    'DEV_ONLY shared-HMAC integrity is not authentication; stage7 remains NOT_BOUND.',
    'Recovery coverage is default/write-off history, not observed cash recovery.',
]
RECON_KEYS = ('status', 'replay_matched', 'entry_count', 'state_digest', 'cut',
              'fixtures_digest', 'scope', 'checks', 'unknown_unresolved')
STATEMENT_KEYS = ('state_digest', 'fixtures_digest', 'scope', 'categories', 'not_bound',
                  'sales_combined', 'primary_and_resale', 'funds_executed')


class RehearsalFailure(Exception):
    """Only fixed harness codes are public; never subprocess diagnostics or input data."""


def require(condition, code):
    if not condition:
        raise RehearsalFailure(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def select(body, keys):
    return {key: copy.deepcopy(body[key]) for key in keys}


def policy_body(body, instance):
    # These two API envelopes carry exactly one top-level session identity.
    # Nested fields, including any original writer identities, remain compared.
    require(body['instance_id'] == instance, 'POLICY_SESSION_MISMATCH')
    return {key: value for key, value in body.items() if key != 'instance_id'}


def inventory(directory):
    return {(p.relative_to(directory).as_posix() + ('/' if p.is_dir() else '')):
            ('DIRECTORY' if p.is_dir() else sha(p.read_bytes()))
            for p in sorted(directory.rglob('*'))}


def stage_keyset(directory):
    """Copy the committed synthetic fixture, set exact 0600 BEFORE loading."""
    path = directory / DEV_KEYSET_NAME
    path.write_bytes((ROOT / 'tests/vectors/dev-keyset-active.json').read_bytes())
    path.chmod(0o600)
    require(path.stat().st_mode & 0o777 == 0o600, 'KEYSET_MODE')
    return load_dev_keyset(path)


def post(server, state, bodies, route, operation_id, op, **fields):
    body = dict(instance_id=state['instance_id'], operation_id=operation_id, op=op, **fields)
    result = release._json(server.port, 'POST', route, body, state['local_token'])
    require(result['outcome'] == ('ACCEPTED' if route == '/api/commands' else 'APPLIED'),
            'POPULATION_REFUSED')
    bodies.append((route, body, result))
    return result


def populate(server, state):
    bodies = []
    for key, op, args in release.STEPS[:4]:
        post(server, state, bodies, '/api/commands', key, op,
             advance_id=release.ADVANCE, args=args)
    route = '/api/overlay/commands'
    post(server, state, bodies, route, 'sim-relocation-clock', 'advance_day',
         from_sim_day=0, to_sim_day=3, reason='SIMULATED relocation rehearsal')
    view = release._json(server.port, 'GET', '/api/overlay')
    due = view['advances'][0]['interest_due_krw']
    require(due > 0, 'INTEREST_HISTORY_ABSENT')
    # Existing test_overlay synthetic amount: interest due plus 1000 principal.
    paid = post(server, state, bodies, route, 'sim-relocation-repay', 'post_repayment',
                advance_ref=release.ADVANCE, at_sim_day=3, amount_krw=due + 1000)
    require(paid['allocation']['principal_krw'] == 1000, 'PRINCIPAL_HISTORY_ABSENT')
    post(server, state, bodies, '/api/commands', 'sim-relocation-default', 'default',
         advance_id=release.ADVANCE, args={}, approvals=APPROVALS)
    view = release._json(server.port, 'GET', '/api/overlay')
    day = view['recovery']['advances'][0]['writeoff_sim_day']
    post(server, state, bodies, route, 'sim-relocation-writeoff-day', 'advance_day',
         from_sim_day=3, to_sim_day=day, reason='SIMULATED relocation write-off eligibility')
    post(server, state, bodies, route, 'sim-relocation-writeoff', 'post_writeoff',
         advance_ref=release.ADVANCE, at_sim_day=day, approvals=APPROVALS,
         setoff_declined_reason='SIMULATED_OPERATOR_DECLINES_REMAINING_SETOFF')
    quote = release._json(server.port, 'GET', '/api/overlay/slices?'
                          'quote_claim_id=demo-delta-small&quote_payee_label=organizer&expected_days=60')['quote']
    # Synthetic sizing only: the seed/test pattern of one fifth of an existing bound.
    face = quote['shadow_slice_face_max'] // 5
    require(face > 0, 'SLICE_QUOTE_UNUSABLE')
    post(server, state, bodies, route, 'sim-relocation-slice', 'register_slice',
         at_sim_day=day, approvals=APPROVALS, claim_id='demo-delta-small',
         payee_label='organizer', slice_face_krw=face, holder_role='KIX_CAPITAL_LENDER',
         expected_days=60, quote_ref=quote['result_digest'])
    journal = release._json(server.port, 'GET', '/api/export')['journal']
    post(server, state, bodies, route, 'sim-relocation-slice-open', 'open_slice',
         at_sim_day=day, approvals=APPROVALS, slice_id='sim-relocation-slice',
         expected_after_journal_index=len(journal))
    return bodies


def lookup(server, instance, route, body):
    key = body['operation_id']
    if route == '/api/commands':
        return release._json(server.port, 'GET', f'/api/operations/{key}?instance_id={instance}')
    return release._json(server.port, 'GET', f'/api/overlay?operation_id={key}')['operation']


def evidence(server, pyz, state, bodies, keyset):
    """Explicit stable projection; original F04 receipt identities remain covered."""
    port = server.port
    release._bundled_surfaces(pyz, port, state['instance_id'], state)
    manifest = release._json(port, 'GET', '/api/export/manifest')
    verified = verify_manifest(manifest, keyset=keyset)
    require(verified['ok'], 'MANIFEST_INVALID')
    require(manifest['status'] == 'COMPLETE', 'MANIFEST_INCOMPLETE')
    sections = {name: section['body'] for name, section in manifest['sections'].items()}
    recon = release._json(port, 'GET', '/api/reconciliation')
    statement = release._json(port, 'GET', '/api/statement')
    require(recon['status'] == 'MATCHED' and all(c['status'] == 'MATCHED' for c in recon['checks']),
            'RECONCILIATION_MISMATCH')
    require(select(recon, RECON_KEYS) == select(sections['reconciliation'], RECON_KEYS),
            'MANIFEST_RECONCILIATION_DRIFT')
    require(select(statement, STATEMENT_KEYS) == select(sections['statement'], STATEMENT_KEYS),
            'MANIFEST_STATEMENT_DRIFT')
    exported = release._json(port, 'GET', '/api/export')
    require(exported['replay_matched'] and exported['journal'] == sections['journal']['entries'],
            'JOURNAL_DRIFT')
    receipts = sections['receipts']['receipts']
    lookups = {body['operation_id']: lookup(server, state['instance_id'], route, body)
               for route, body, _ in bodies}
    for key, stored in receipts.items():
        found = release._json(port, 'GET', f"/api/operations/{key}?instance_id={state['instance_id']}")
        require(found == stored['receipt'], 'RECEIPT_LOOKUP_DRIFT')
    return dict(state_digest=exported['state_digest'],
                overlay_state_digest=sections['overlay']['overlay_state_digest'],
                journal=exported['journal'], overlay_journal=sections['overlay']['journal'],
                receipts=receipts, lookups=lookups,
                statement=select(statement, STATEMENT_KEYS), reconciliation=select(recon, RECON_KEYS),
                fixtures=sections['fixtures'], source_pin=sections['source_pin'],
                terms=policy_body(release._json(port, 'GET', '/api/terms'), state['instance_id']),
                policy=policy_body(release._json(port, 'GET', '/api/policy'), state['instance_id']),
                slices=release._json(port, 'GET', '/api/overlay/slices'),
                content_digest=manifest['content_digest'], signature_check=verified['signature'])


def compare_evidence(before, after):
    require(before == after, 'BUSINESS_EVIDENCE_DRIFT')


def audit(raw, stable):
    report = audit_workspace_bytes(raw, workspace='DISPOSABLE_CAPTURE')
    require(report['ok'] and report['checks'] == {name: 'MATCHED' for name in CHECK_ORDER},
            'CAPTURE_AUDIT_FAILED')
    require(select(report['recon'], RECON_KEYS) == stable['reconciliation'], 'AUDIT_RECON_DRIFT')
    require(report['state_digest'] == stable['state_digest'], 'AUDIT_DIGEST_DRIFT')
    doc = json.loads(raw)
    require(doc['payload']['journal'] == stable['journal']
            and doc['payload']['receipts'] == stable['receipts']
            and doc['overlay']['journal'] == stable['overlay_journal']
            and doc['overlay']['overlay_state']['digest'] == stable['overlay_state_digest'],
            'CAPTURE_EVIDENCE_DRIFT')
    return report


def expect_error(server, method, path, body, token, status, code):
    actual, raw = release._request(server.port, method, path, body, token)
    require(actual == status and json.loads(raw).get('error') == code, 'EXPECTED_FENCE_MISSING')


def session_and_replay(server, old, new, bodies, stable, workspace):
    require(new['instance_id'] != old['instance_id'] and new['local_token'] != old['local_token'],
            'SESSION_REUSED')
    original = (workspace / FILE_NAME).read_bytes()
    for route, body, first in bodies:
        fresh = {**body, 'instance_id': new['instance_id']}
        expect_error(server, 'POST', route, fresh, old['local_token'], 403, 'LOCAL_TOKEN_REQUIRED')
        expect_error(server, 'POST', route, body, new['local_token'], 409, 'SESSION_CHANGED')
        result = release._json(server.port, 'POST', route, fresh, new['local_token'])
        require(result.get('transport_duplicate') is True, 'FIRST_RESULT_MISSING')
        prior = stable['lookups'][body['operation_id']]
        if route == '/api/commands':
            require(result == {**prior, 'transport_duplicate': True}, 'FIRST_RECEIPT_DRIFT')
        else:
            # Compare precisely the lookup core; POST adds a current-session envelope.
            expected = {**prior}
            if 'label' in expected:
                # Recovery POST overlays the generic memo label; lookup retains SIMULATED.
                expected['label'] = first['label']
            require(select(first, expected) == expected, 'ORIGINAL_OVERLAY_RECEIPT_DRIFT')
            require(select(result, expected) == expected and result['instance_id'] == new['instance_id'],
                    'FIRST_OVERLAY_RECEIPT_DRIFT')
        require(lookup(server, new['instance_id'], route, fresh) == prior, 'REPLAY_LOOKUP_DRIFT')
    key = bodies[0][1]['operation_id']
    expect_error(server, 'GET', f"/api/operations/{key}?instance_id={old['instance_id']}",
                 None, None, 409, 'SESSION_CHANGED')
    route, body, _ = bodies[0]
    expect_error(server, 'POST', route,
                 {**body, 'instance_id': new['instance_id'], 'args': {**body['args'], 'amount': body['args']['amount'] + 1}},
                 new['local_token'], 409, 'IDEMPOTENCY_CONFLICT')
    route, body, _ = next((r, b, first) for r, b, first in bodies if b['op'] == 'post_repayment')
    expect_error(server, 'POST', route,
                 {**body, 'instance_id': new['instance_id'], 'amount_krw': body['amount_krw'] + 1},
                 new['local_token'], 409, 'IDEMPOTENCY_CONFLICT')
    require((workspace / FILE_NAME).read_bytes() == original, 'REPLAY_WROTE_WORKSPACE')
    return dict(instance_changed=True, token_changed=True, old_token='403 LOCAL_TOKEN_REQUIRED',
                stale_commands='409 SESSION_CHANGED', stale_lookup='409 SESSION_CHANGED',
                first_results_preserved=True, conflicting_bodies='409 IDEMPOTENCY_CONFLICT',
                workspace_bytes_unchanged=True, replayed_commands=len(bodies))


def corruptions(raw):
    checksum = json.loads(raw)
    checksum['payload']['state_digest'] = '0' * 64
    linked = json.loads(raw)
    anchor = next(e for e in linked['overlay']['journal'] if e['kind'] == 'default_anchor')
    anchor['payload']['f04_operation_id'] = 'sim-wrong-default-link'
    # Re-fold AND reseal; this must pass checksums/folding and fail the F04 link validator.
    linked['overlay'] = overlay.build_section(linked['overlay']['journal'])
    return {'truncated': raw[:len(raw) // 2], 'payload-checksum': canonical_bytes(checksum),
            'resealed-f04-link': canonical_bytes(linked)}


def check_corruptions(raw, pyz, root, cwd, env, signed):
    results = {}
    for name, damaged in corruptions(raw).items():
        directory = root / name
        directory.mkdir()
        path = directory / FILE_NAME
        path.write_bytes(damaged)
        if signed:
            stage_keyset(directory)
        report = audit_workspace_bytes(damaged, workspace='DISPOSABLE_CORRUPT_COPY')
        require(not report['ok'] and report['reason'] == 'WORKSPACE_UNREADABLE', 'CORRUPT_AUDIT_ACCEPTED')
        if name == 'resealed-f04-link':
            require(report['failed_check'] == 'service_restore', 'LINK_NOT_EXERCISED')
        server = release._start(pyz, directory, cwd, env, dev_keyset=signed)
        try:
            state = release._json(server.port, 'GET', '/api/state')
            require(state['workspace']['status'] == 'WORKSPACE_UNREADABLE', 'CORRUPT_RUNTIME_ACCEPTED')
            for route in ('/api/commands', '/api/overlay/commands'):
                body = dict(instance_id=state['instance_id'], operation_id='sim-corrupt-command')
                if route == '/api/commands':
                    body.update(op='offer', advance_id=release.ADVANCE, args=release.STEPS[0][2])
                else:
                    body.update(op='advance_day', from_sim_day=0, to_sim_day=3, reason='SIMULATED')
                expect_error(server, 'POST', route, body,
                             state['local_token'], 503, 'WORKSPACE_UNREADABLE')
        finally:
            server.stop()
        require(server.proc.poll() is not None and path.read_bytes() == damaged, 'CORRUPT_COPY_REPAIRED')
        results[name] = dict(audit='WORKSPACE_UNREADABLE', failed_check=report['failed_check'],
                             runtime='WORKSPACE_UNREADABLE', both_command_routes=503,
                             bytes_unchanged=True, child_reaped=True)
    return results


def insecure_keyset(pyz, root, cwd, env):
    directory = root / 'insecure-keyset'
    directory.mkdir()
    stage_keyset(directory)
    path = directory / DEV_KEYSET_NAME
    before = path.read_bytes()
    path.chmod(0o644)
    result = subprocess.run([sys.executable, '-B', os.fspath(pyz), '--workspace', os.fspath(directory),
                             '--port', '0', '--dev-keyset'], cwd=cwd, env=env,
                            capture_output=True, timeout=30, check=False)
    require(result.returncode == 2 and b'SIGNATURE_KEYSET_MODE' in result.stderr,
            'INSECURE_KEYSET_ACCEPTED')
    require(path.read_bytes() == before and path.stat().st_mode & 0o777 == 0o644,
            'INSECURE_KEYSET_REPAIRED')
    require(not (directory / FILE_NAME).exists(), 'INSECURE_KEYSET_WROTE_WORKSPACE')
    return 'SIGNATURE_KEYSET_MODE; unchanged'


def run_case(pyz, case, root):
    signed = case == 'dev-keyset'
    source = root / 'source-runtime' / 'workspace'
    source.mkdir(parents=True)
    cwd = root / 'unrelated-cwd'
    cwd.mkdir()
    capture = root / 'untouched-capture'
    capture.mkdir()
    destination = root / 'relocated-runtime'
    destination.mkdir()
    env = release._child_env()
    require('PYTHONPATH' not in env, 'CHECKOUT_ENV_PRESENT')
    keyset = stage_keyset(source) if signed else None
    key_bytes = (source / DEV_KEYSET_NAME).read_bytes() if signed else None
    server = release._start(pyz, source, cwd, env, dev_keyset=signed)
    try:
        old = release._json(server.port, 'GET', '/api/state')
        bodies = populate(server, old)
        before = evidence(server, pyz, old, bodies, keyset)
    finally:
        server.stop()
    require(server.proc.poll() is not None, 'WRITER_STILL_RUNNING')
    # Exactly one capture read, after confirmed writer exit; the preserved copy is never served.
    raw = (source / FILE_NAME).read_bytes()
    (capture / FILE_NAME).write_bytes(raw)
    captured_inventory = inventory(capture)
    audit(raw, before)
    kinds = sorted({e['kind'] for e in before['overlay_journal']})
    require({'repayment', 'default_anchor', 'WRITEOFF', 'SLICE_PROPOSE', 'SLICE_OPEN'} <= set(kinds),
            'REQUIRED_HISTORY_ABSENT')
    source_inventory = inventory(source)
    expected = {FILE_NAME, LOCK_NAME} | ({DEV_KEYSET_NAME} if signed else set())
    require(set(source_inventory) == expected, 'UNEXPECTED_RUNTIME_INPUT')
    # Only this stopped disposable writer's lock artifact is removed.
    (source / LOCK_NAME).unlink()
    relocated = destination / 'workspace'
    shutil.move(os.fspath(source), relocated)
    staged_pyz = destination / pyz.name
    shutil.copyfile(pyz, staged_pyz)
    require(not source.exists() and relocated.resolve() != source.resolve(), 'NOT_RELOCATED')
    require(sha(staged_pyz.read_bytes()) == sha(pyz.read_bytes()), 'ARCHIVE_STAGING_DRIFT')
    require((relocated / FILE_NAME).is_file() and (relocated / FILE_NAME).read_bytes() == raw,
            'WORKSPACE_STAGING_DRIFT')
    if signed:
        require((relocated / DEV_KEYSET_NAME).is_file()
                and (relocated / DEV_KEYSET_NAME).read_bytes() == key_bytes
                and (relocated / DEV_KEYSET_NAME).stat().st_mode & 0o777 == 0o600, 'KEYSET_STAGING_DRIFT')
    require(set(inventory(destination)) == {staged_pyz.name, 'workspace/', 'workspace/' + FILE_NAME}
            | ({'workspace/' + DEV_KEYSET_NAME} if signed else set()), 'UNEXPECTED_STAGED_INPUT')
    server = release._start(staged_pyz, relocated, cwd, env, dev_keyset=signed)
    try:
        new = release._json(server.port, 'GET', '/api/state')
        require(new['workspace']['status'] == 'ACTIVE'
                and Path(new['workspace']['path']) == (relocated / FILE_NAME).resolve(), 'WRONG_RUNTIME_WORKSPACE')
        after = evidence(server, staged_pyz, new, bodies, keyset)
        compare_evidence(before, after)
        sessions = session_and_replay(server, old, new, bodies, before, relocated)
        compare_evidence(before, evidence(server, staged_pyz, new, bodies, keyset))
    finally:
        server.stop()
    final_raw = (relocated / FILE_NAME).read_bytes()
    audit(final_raw, before)
    require(final_raw == raw, 'RELOCATED_BYTES_DRIFT')
    require(inventory(relocated) == source_inventory, 'RUNTIME_INVENTORY_DRIFT')
    if signed:
        require((relocated / DEV_KEYSET_NAME).read_bytes() == key_bytes
                and (relocated / DEV_KEYSET_NAME).stat().st_mode & 0o777 == 0o600,
                'RUNTIME_KEYSET_DRIFT')
    corrupt = check_corruptions(raw, staged_pyz, root, cwd, env, signed)
    keyset_check = insecure_keyset(staged_pyz, root, cwd, env) if signed else 'NOT_STAGED'
    require(inventory(capture) == captured_inventory and (capture / FILE_NAME).read_bytes() == raw,
            'CAPTURE_MUTATED')
    categories = before['statement']['categories']
    result = dict(case=case, status='PASSED', checks=dict(
        writer_stopped_before_capture=True, capture_audit='MATCHED', final_audit='MATCHED',
        actual_directory_move=True, old_path_absent=True, unrelated_cwd=True,
        pythonpath_removed=True, explicit_runtime_inputs_only=True,
        bundled_policy_provenance='MATCHED', stable_business_evidence='MATCHED',
        replay_economic_effects='UNCHANGED', source_capture_unchanged=True, children_reaped=True,
        keyset_mode='0600' if signed else 'NOT_STAGED', insecure_keyset=keyset_check),
        evidence=dict(state_digest=before['state_digest'], overlay_state_digest=before['overlay_state_digest'],
            content_digest=before['content_digest'], workspace_sha256=sha(raw),
            journal_sha256=sha(canonical_bytes(before['journal'])),
            overlay_journal_sha256=sha(canonical_bytes(before['overlay_journal'])),
            receipts_sha256=sha(canonical_bytes(before['receipts'])),
            lookup_cores_sha256=sha(canonical_bytes(before['lookups'])),
            fixtures_sha256=sha(canonical_bytes(before['fixtures'])),
            source_pin_sha256=sha(canonical_bytes(before['source_pin'])),
            terms_sha256=sha(canonical_bytes(before['terms'])),
            policy_sha256=sha(canonical_bytes(before['policy'])),
            journal_entries=len(before['journal']), overlay_entries=len(before['overlay_journal']),
            receipt_count=len(before['receipts']), history_kinds=kinds,
            statement_totals={c['id']: {k: v for k, v in c.items() if type(v) is int}
                              for c in categories},
            reconciliation=before['reconciliation']['checks'], signature_check=before['signature_check']),
        session_checks=sessions, corruption_checks=corrupt)
    if signed:
        surfaces = canonical_bytes(result) + staged_pyz.read_bytes()
        with zipfile.ZipFile(staged_pyz) as archive:
            require(all(Path(name).name != DEV_KEYSET_NAME for name in archive.namelist()),
                    'KEYSET_DISCLOSURE')
        require(key_bytes not in surfaces, 'KEYSET_DISCLOSURE')
        for entry in keyset['keys']:
            require(entry['key_hex'].encode() not in surfaces
                    and bytes.fromhex(entry['key_hex']) not in surfaces, 'KEY_DISCLOSURE')
    return result


def report_base():
    return dict(format=FORMAT, label='SIMULATED', workspace_kind='LOCAL_FILE_WORKSPACE',
                funds_executed=False, authentication='NOT_BOUND', stage5_durable_transactions='NOT_BOUND',
                stage7_authenticated_export=False, cases=[], limitations=list(LIMITATIONS))


def rehearse(cases=CASES):
    require(bool(cases) and all(case in CASES for case in cases), 'INVALID_CASE')
    report = report_base()
    with tempfile.TemporaryDirectory(prefix='kix-relocation-') as tmp:
        root = Path(tmp)
        pyz = build_release.build(root / 'build')
        for case in cases:
            with tempfile.TemporaryDirectory(prefix='kix-relocation-case-') as case_tmp:
                try:
                    result = run_case(pyz, case, Path(case_tmp))
                except RehearsalFailure as exc:
                    result = dict(case=case, status='FAILED', failure_code=str(exc))
                except Exception:
                    # Raw HTTP/subprocess exceptions can contain tokens or runtime input bytes.
                    result = dict(case=case, status='FAILED', failure_code='REHEARSAL_FAILED')
                report['cases'].append(result)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=CASES, help='Default: run both modes independently')
    args = parser.parse_args(argv)
    try:
        report = rehearse((args.case,) if args.case else CASES)
    except Exception:
        report = report_base()
        report.update(status='FAILED', failure_code='BUILD_FAILED')
        print(json.dumps(report, sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0 if all(case['status'] == 'PASSED' for case in report['cases']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
