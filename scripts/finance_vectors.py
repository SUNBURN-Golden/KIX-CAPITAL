#!/usr/bin/env python3
"""Regenerate and byte-pin the finance input vectors in tests/vectors/finance_vectors.json.

The artifact is SIMULATED and deterministic: no clock, no random instance id, no
path. It supplies INPUT_VECTOR_CANDIDATE material for FINANCE_PENDING_NODES
candidates, which is the vector-supplier role of
docs/decisions/CAPITAL_UPSTREAM_BINDING.md (entry stage6_finance_candidates).
Seven groups, each naming one candidate id:

- scenario_obligations -> fin-multi-payee-refund-proof: the nine F01-F03
  scenarios of capital/scenarios.py, 35 steps, with the per-payee obligation
  values and cash and refund totals after every step. No policy is chosen.
- f04_command_outcomes -> fin-ledger-contract: the 22 seed_demo commands run
  through CapitalService.execute with their outcome, error, phase and
  state_digest, plus the 21 accepted journal entries.
- journal_projection_digests -> fin-double-entry-projection: for every journal
  prefix, the restored state_digest and the SIMULATION_FIXED_V1 entries,
  accounts and read-model digests with debit and credit totals.
- seed_reconciliation -> fin-observation-reconciliation: the six-check
  reconciliation report on the fixed-instance seed book, with one probed
  operation id that was never issued.
- statement_and_previews -> fin-credit-exposure-reconciliation: the
  five-category statement and the read-only draw preview of every case.
- manifest_section_digests -> fin-consistent-accounting-export: the manifest v2
  section sha256 values and content_digest of the fixed-instance seed book.
- facade_read_model -> fin-catalogue-read-model: the response definition
  digests of every GET route in capital/contract/facade-v1.json.

fin-finance-closeout has no vectors. Its named input, build/acceptance-evidence.json,
is an untracked per-run file, so the candidates index says why and holds null.
The report, statement and preview bodies are stored with instance id keys removed
(capital.export.strip_volatile), so the artifact carries no instance id.

This is not SEMANTIC_CONFORMANCE and it completes no upstream node. Passing
--check says only that the pinned local code still produces these bytes. It
changes no projection, no chart and no accounting policy.

--check regenerates in memory and exits 1 when the file differs or is missing.
--write rewrites it. --file points both at another path.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital.export import SECTION_IDS, content_digest, content_material, strip_volatile
from capital.producer import FixtureViews
from capital.projection import SimulationProjection
from capital.protocol import CreditMachine
from capital.recon import CHECK_IDS
from capital.resources import vendor_manifest
from capital.scenarios import replay_scenarios
from capital.service import CapitalService, digest

DEFAULT_FILE = ROOT / 'tests' / 'vectors' / 'finance_vectors.json'
FACADE_SOURCE = 'capital/contract/facade-v1.json'
FACADE_FILE = ROOT.joinpath(*FACADE_SOURCE.split('/'))
FORMAT = 'KIX_CAPITAL_FINANCE_VECTORS_V1'
INSTANCE_ID = 'finance-vectors'
ROLE = 'INPUT_VECTOR_CANDIDATE'
# docs/aiops/FINANCE_PENDING_NODES.json in kix-protocol is the source of truth for
# these ids. The binding note copies them, and tests/test_finance_vectors.py checks
# that copy.
CANDIDATES = (
    'fin-ledger-contract',
    'fin-double-entry-projection',
    'fin-observation-reconciliation',
    'fin-multi-payee-refund-proof',
    'fin-credit-exposure-reconciliation',
    'fin-consistent-accounting-export',
    'fin-catalogue-read-model',
    'fin-finance-closeout',
)
GROUP_CANDIDATES = {
    'scenario_obligations': 'fin-multi-payee-refund-proof',
    'f04_command_outcomes': 'fin-ledger-contract',
    'journal_projection_digests': 'fin-double-entry-projection',
    'seed_reconciliation': 'fin-observation-reconciliation',
    'statement_and_previews': 'fin-credit-exposure-reconciliation',
    'manifest_section_digests': 'fin-consistent-accounting-export',
    'facade_read_model': 'fin-catalogue-read-model',
}
CLOSEOUT = 'fin-finance-closeout'
CLOSEOUT_REASON = (
    'build/acceptance-evidence.json is an untracked per-run file (it records the git head_sha and the local '
    'tool versions), so no stable bytes exist to pin as a vector. The input stays named in '
    'docs/decisions/CAPITAL_UPSTREAM_BINDING.md only.'
)
PROBE_OPERATION_ID = 'op-never-issued'
STATEMENT_CATEGORIES = ('approved', 'exposure', 'reserved', 'settlement', 'refund')
DEFINITION_PREFIX = '#/definitions/'
NOTE = (
    'SIMULATED input vectors for FINANCE_PENDING_NODES candidates. INPUT_VECTOR_CANDIDATE is the '
    'vector-supplier role of docs/decisions/CAPITAL_UPSTREAM_BINDING.md. This is not SEMANTIC_CONFORMANCE, '
    'completes no upstream node, adopts no accounting policy and chooses no settlement policy. A candidate '
    'can only adopt these with its own upstream completion proof.'
)
VIEW_CASH = ('confirmed_cash', 'distributed_cash', 'undistributed_cash', 'recovery_due',
             'refund_face', 'refund_accepted', 'refund_outstanding')
OBLIGATION_KEYS = ('payee', 'face', 'distributed', 'cancelled_unpaid', 'recovery_due', 'outstanding')
JOURNAL_SCALARS = (int, str, bool)


class VectorError(Exception):
    pass


def _load_seed():
    spec = importlib.util.spec_from_file_location('seed_demo', ROOT / 'scripts' / 'seed_demo.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dump(body) -> bytes:
    return (json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode('ascii')


def _require(condition, message):
    if not condition:
        raise VectorError(message)


def _view_vector(view):
    """Obligation rows and cash totals of one settlement view, plus a digest of the whole view."""
    return {
        'obligations': [{key: row[key] for key in OBLIGATION_KEYS} for row in view['obligations']],
        'totals': {key: view[key] for key in VIEW_CASH},
        'view_digest': digest(view),
    }


def scenario_obligations():
    results = replay_scenarios()
    scenarios = []
    for scenario_id, result in results.items():
        steps = []
        for row in result['steps']:
            checks = {item['predicate']: item['matched'] for item in row['checks']}
            _require(all(checks.values()), f'{scenario_id} step {row["ordinal"]} predicate failed')
            steps.append({
                'ordinal': row['ordinal'], 'op': row['op'], 'args': row['args'],
                'outcome': row['outcome'], 'error': row['error'],
                'expected_error': row['expected_error'], 'duplicate': row['duplicate'],
                'checks': checks, **_view_vector(row['view']),
            })
        scenarios.append({
            'id': scenario_id, 'step_count': len(steps),
            'all_predicates_matched': result['all_predicates_matched'],
            'initial': _view_vector(result['initial']), 'steps': steps,
            'final_view_digest': digest(result['final']),
        })
    _require(len(scenarios) == 9, f'{len(scenarios)} scenarios, expected 9')
    _require(sum(row['step_count'] for row in scenarios) == 35, 'scenario steps are not 35')
    return {
        'candidate': GROUP_CANDIDATES['scenario_obligations'], 'label': ROLE, 'data_label': 'SIMULATED',
        'source': 'capital.scenarios.replay_scenarios on disposable MockSettlement books',
        'policy_chosen': False, 'scenario_count': len(scenarios),
        'step_count': sum(row['step_count'] for row in scenarios), 'scenarios': scenarios,
    }


def _journal_row(index, entry):
    body = entry['body']
    return {
        'index': index, 'op': entry['op'], 'advance_id': entry['advance_id'],
        'idempotency_key': entry['idempotency_key'],
        'body_scalars': {key: body[key] for key in sorted(body) if type(body[key]) in JOURNAL_SCALARS},
        'body_digest': digest(body),
    }


def replay_f04(seed):
    """Run the seed_demo story through the real command path. Returns the service and per-step rows."""
    service = CapitalService()
    service.instance_id = INSTANCE_ID
    service.storage.writer_instance = INSTANCE_ID
    rows = []
    for operation_id, op, advance_id, args, outcome, error in seed.STEPS:
        before = len(service.machine.export_journal())
        receipt = service.execute({
            'instance_id': INSTANCE_ID, 'operation_id': operation_id, 'op': op,
            'advance_id': advance_id, 'args': args,
        })
        _require(receipt.get('outcome') == outcome and receipt.get('error') == error,
                 f'{operation_id} outcome {receipt.get("outcome")} error {receipt.get("error")}')
        _require(receipt.get('funds_executed') is False, f'{operation_id} funds_executed')
        journal = service.machine.export_journal()
        view = service.machine.view(advance_id)
        rows.append({
            'ordinal': len(rows) + 1, 'operation_id': operation_id, 'op': op, 'advance_id': advance_id,
            'args': args, 'outcome': receipt['outcome'], 'error': receipt.get('error'),
            'journal_entry': len(journal) - 1 if len(journal) > before else None,
            'journal_length_after': len(journal),
            'phase_after': view['phase'], 'drawn_exposure_after': view['drawn_exposure'],
            'outstanding_exposure_after': view['outstanding_exposure'],
            'state_digest_after': service.machine.state_digest(),
        })
    return service, rows


def f04_command_outcomes(service, rows):
    journal = service.machine.export_journal()
    restored = CreditMachine.restore(journal, service.fixtures)
    _require(restored.canonical_state() == service.machine.canonical_state(), 'journal does not restore the book')
    return {
        'candidate': GROUP_CANDIDATES['f04_command_outcomes'], 'label': ROLE, 'data_label': 'SIMULATED',
        'source': 'scripts/seed_demo.py STEPS through CapitalService.execute on the pinned FSM producer',
        'command_count': len(rows), 'accepted': sum(row['outcome'] == 'ACCEPTED' for row in rows),
        'rejected': sum(row['outcome'] == 'REJECTED' for row in rows),
        'commands': rows,
        'journal': [_journal_row(index, entry) for index, entry in enumerate(journal)],
        'journal_digest': digest(journal), 'state_digest': service.machine.state_digest(),
    }


def journal_projection_digests(service):
    journal = service.machine.export_journal()
    fixtures = FixtureViews()
    evidence = [fixtures.view(key) for key in sorted(fixtures.projection_ids)]
    port = SimulationProjection()
    prefixes = []
    projected = None
    for length in range(len(journal) + 1):
        prefix = copy.deepcopy(journal[:length])
        projected = port.project(prefix, copy.deepcopy(evidence))
        accounts = projected['accounts']
        debit = sum(row['debit_total'] for row in accounts)
        credit = sum(row['credit_total'] for row in accounts)
        _require(debit == credit, f'prefix {length} does not balance')
        prefixes.append({
            'journal_length': length,
            'state_digest': CreditMachine.restore(prefix, fixtures).state_digest(),
            'entry_count': len(projected['entries']),
            'entries_digest': digest(projected['entries']),
            'accounts_digest': digest(accounts),
            'read_model_digest': digest(projected['read_model']),
            'debit': debit, 'credit': credit,
        })
    _require(all(item['matched'] for item in projected['conservation']), 'conservation predicate failed')
    return {
        'candidate': GROUP_CANDIDATES['journal_projection_digests'], 'label': ROLE, 'data_label': 'SIMULATED',
        'source': 'capital.projection.SimulationProjection over each journal prefix and the three fixture views',
        'chart': SimulationProjection.CHART_VERSION, 'accounting_policy': 'SYNTHETIC_UNADOPTED',
        'evidence_digest': digest(evidence), 'journal_digest': digest(journal),
        'prefixes': prefixes,
        'final': {
            'conservation': projected['conservation'],
            'accounts': [{key: row[key] for key in ('code', 'debit_total', 'credit_total', 'balance')}
                         for row in projected['accounts']],
        },
    }


def seed_reconciliation(service):
    """The six-check report on the seed book. Instance ids are stripped, so the report is the same on any instance."""
    report = strip_volatile(service.reconciliation(probe_operation_id=PROBE_OPERATION_ID))
    _require(report['status'] == 'MATCHED', f'reconciliation status {report["status"]}')
    _require([(row['id'], row['status']) for row in report['checks']] == [(name, 'MATCHED') for name in CHECK_IDS],
             'reconciliation checks are not the six CHECK_IDS, all MATCHED')
    _require([row['operation_id'] for row in report['unknown_unresolved']] == [PROBE_OPERATION_ID],
             'probe row missing from unknown_unresolved')
    return {
        'candidate': GROUP_CANDIDATES['seed_reconciliation'], 'label': ROLE, 'data_label': 'SIMULATED',
        'source': 'CapitalService.reconciliation on the fixed-instance seed book (capital/recon.py)',
        'check_ids': list(CHECK_IDS), 'probe_operation_id': PROBE_OPERATION_ID,
        'report': report, 'report_digest': digest(report),
    }


def statement_and_previews(service):
    """The five-category statement and one read-only draw preview per case, instance ids stripped."""
    statement = strip_volatile(service.statement())
    category_ids = [row['id'] for row in statement['categories']]
    _require(category_ids == list(STATEMENT_CATEGORIES), f'statement categories {category_ids}')
    previews = [strip_volatile(service.preview_draw(advance_id, INSTANCE_ID))
                for advance_id in sorted(service.case_fixtures)]
    _require(all(row['funds_executed'] is False and row['workspace_mutated'] is False for row in previews),
             'a preview wrote or moved funds')
    return {
        'candidate': GROUP_CANDIDATES['statement_and_previews'], 'label': ROLE, 'data_label': 'SIMULATED',
        'source': 'CapitalService.statement and preview_draw on the fixed-instance seed book (capital/statement.py)',
        'category_ids': category_ids, 'statement': statement, 'statement_digest': digest(statement),
        'previews': previews,
    }


def manifest_section_digests(service):
    """Section hashes and content_digest of the v2 manifest. The manifest body itself is not copied.

    section_sha256 is the stored hash, which covers a body that carries this seed's instance id.
    section_content_sha256 is the hash content_digest covers, with instance and timestamp keys removed.
    """
    manifest = service.export_manifest()
    _require(manifest['status'] == 'COMPLETE' and manifest['incomplete_reasons'] == [],
             f'manifest status {manifest["status"]}')
    _require(list(manifest['sections']) == list(SECTION_IDS), 'manifest section set changed')
    _require(content_digest(manifest) == manifest['content_digest'], 'content_digest does not recompute')
    covered = content_material(manifest)['sections']
    return {
        'candidate': GROUP_CANDIDATES['manifest_section_digests'], 'label': ROLE, 'data_label': 'SIMULATED',
        'source': 'CapitalService.export_manifest on the fixed-instance seed book (capital/export.py)',
        'manifest_format': manifest['format'], 'status': manifest['status'],
        'incomplete_reasons': manifest['incomplete_reasons'], 'section_ids': list(SECTION_IDS),
        'section_sha256': {name: manifest['sections'][name]['sha256'] for name in SECTION_IDS},
        'section_content_sha256': {name: covered[name]['sha256'] for name in SECTION_IDS},
        'signature_status': manifest['signature']['status'], 'signature_alg': manifest['signature']['alg'],
        'stage7_authenticated_export': manifest['stage7_authenticated_export'],
        'content_digest': manifest['content_digest'],
    }


def _definition_refs(node, found):
    """Add every '#/definitions/<name>' target under node to found."""
    if type(node) is dict:
        for key, item in node.items():
            if key == '$ref' and type(item) is str and item.startswith(DEFINITION_PREFIX):
                found.add(item[len(DEFINITION_PREFIX):])
            else:
                _definition_refs(item, found)
    elif type(node) is list:
        for item in node:
            _definition_refs(item, found)


def _definition_closure(definitions, names):
    """Sorted names of the given definitions and every definition they reach through $ref."""
    seen = set()
    pending = list(names)
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        _require(name in definitions, f'facade definition {name} is not declared')
        seen.add(name)
        nested = set()
        _definition_refs(definitions[name], nested)
        pending.extend(nested - seen)
    return sorted(seen)


def facade_read_model():
    """Response definition digests of every GET api route. Reads the contract file, no server."""
    contract = json.loads(FACADE_FILE.read_text(encoding='utf-8'))
    _require(contract['namespace'] == 'capital-local-facade/1' and contract['semantic_conformance'] is False,
             'facade contract is not the local, non-conformance one')
    definitions = contract['definitions']
    routes = []
    reached = set()
    for route in contract['routes']:
        if route['kind'] != 'api' or route['method'] != 'GET':
            continue
        refs = set()
        _definition_refs(route['response'], refs)
        _require(refs, f'{route["path"]} response names no definition')
        closure = _definition_closure(definitions, refs)
        reached.update(closure)
        routes.append({
            'path': route['path'], 'operation_id': route['operationId'], 'permission': route['permission'],
            'response_definitions': [{'definition': name, 'definition_digest': digest(definitions[name])}
                                     for name in sorted(refs)],
            'closure': closure, 'closure_digest': digest({name: definitions[name] for name in closure}),
        })
    return {
        'candidate': GROUP_CANDIDATES['facade_read_model'], 'label': ROLE, 'data_label': 'SIMULATED',
        'source': FACADE_SOURCE, 'namespace': contract['namespace'], 'contract_label': contract['label'],
        'semantic_conformance': contract['semantic_conformance'], 'cap16_exact_tuple': contract['cap16_exact_tuple'],
        'catalogue': False, 'route_count': len(routes), 'routes': routes,
        'definitions_digest': digest({name: definitions[name] for name in sorted(reached)}),
        'contract_digest': digest(contract),
    }


def candidate_row(name):
    """Index row: the group that supplies the candidate, or null with the reason none does."""
    group = next((group for group, held in GROUP_CANDIDATES.items() if held == name), None)
    return {'id': name, 'vectors': group,
            'reason': CLOSEOUT_REASON if group is None and name == CLOSEOUT else None}


def build_body() -> dict:
    seed = _load_seed()
    service, rows = replay_f04(seed)
    try:
        groups = {
            'scenario_obligations': scenario_obligations(),
            'f04_command_outcomes': f04_command_outcomes(service, rows),
            'journal_projection_digests': journal_projection_digests(service),
            'seed_reconciliation': seed_reconciliation(service),
            'statement_and_previews': statement_and_previews(service),
            'manifest_section_digests': manifest_section_digests(service),
            'facade_read_model': facade_read_model(),
        }
    finally:
        seed._release(service.producer)
    body = {
        'format': FORMAT, 'label': 'SIMULATED', 'funds_executed': False, 'vector_role': ROLE,
        'semantic_conformance': False, 'upstream_nodes_completed': [],
        'source_commit': vendor_manifest()['commit'],
        'candidates': [candidate_row(name) for name in CANDIDATES],
        'note': NOTE, 'groups': groups,
    }
    try:
        seed._reject_volatile(body)
    except seed.SeedError as exc:
        raise VectorError(str(exc)) from exc
    return body


def build_artifact() -> bytes:
    """The full file bytes. Pure: nothing is written."""
    return dump(build_body())


def drift_paths(expected: bytes, actual: bytes, limit=8):
    """JSON paths where the two byte strings differ, or a reason when either does not parse."""
    seed = _load_seed()
    try:
        return seed.diff_paths(json.loads(expected), json.loads(actual))[:limit]
    except ValueError:
        return ['unparseable']


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true', help='Byte-compare the artifact. Exit 1 on drift.')
    mode.add_argument('--write', action='store_true', help='Regenerate the artifact.')
    parser.add_argument('--file', type=Path, default=DEFAULT_FILE,
                        help='Artifact path. Default tests/vectors/finance_vectors.json')
    args = parser.parse_args(argv)
    try:
        data = build_artifact()
        if args.write:
            args.file.parent.mkdir(parents=True, exist_ok=True)
            args.file.write_bytes(data)
            print(f'finance vectors written: {len(data)} bytes to {args.file}')
            return 0
        if not args.file.is_file():
            print(f'finance vectors missing: {args.file}', file=sys.stderr)
            print('run python3 scripts/finance_vectors.py --write to regenerate', file=sys.stderr)
            return 1
        recorded = args.file.read_bytes()
    except (OSError, VectorError) as exc:
        print(f'finance vectors failed: {exc}', file=sys.stderr)
        return 1
    if recorded != data:
        print('finance vectors drift: ' + ', '.join(drift_paths(recorded, data)), file=sys.stderr)
        print('run python3 scripts/finance_vectors.py --write to regenerate', file=sys.stderr)
        return 1
    print(f'finance vectors ok: {len(data)} bytes match')
    return 0


if __name__ == '__main__':
    sys.exit(main())
