#!/usr/bin/env python3
"""Read-only, local upstream pin and proposed atomic evidence inspection.

SIMULATED / provisional. Completeness is not approval, adoption, or receipt
authentication. No candidate code or evidence command is ever executed.
"""
from __future__ import annotations

import argparse
import ast
import copy
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

# Trusted helpers must not leave bytecode in inspected trees.
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
NOTE = 'docs/decisions/CAPITAL_UPSTREAM_REPINS.md'
READ_MODEL_NOTE = 'docs/decisions/CAPITAL_READ_MODEL_QUERY_PIN.md'
SCHEMA = 'capital-upstream-repin-evidence-v1'
SHA = re.compile(r'[0-9a-f]{40}\Z')
FOLDERS = ('capital', 'scripts', 'tests', 'docs', 'source_material')
ROOT_FILES = ('README.md', 'AGENTS.md', 'package.json', 'package-lock.json',
              'pyproject.toml', 'playwright.config.cjs')
SKIP = frozenset(('__pycache__', '.pytest_cache', 'node_modules', 'test-results',
                  'playwright-report'))
STEMS = ('upstream', 'fsm_contract', 'read_model', 'ce1', 'agent')
IMPLEMENTATIONS = {stem: (f'scripts/{stem}_claims_check.py' if stem == 'fsm_contract'
                          else f'capital/{stem}_claims.py') for stem in STEMS}
FORMATS = {stem: f'KIX_CAPITAL_{stem.upper()}_CLAIMS_V1' for stem in STEMS}


def trusted_module(name, filename):
    namespace = {'__name__': name, '__file__': str(ROOT / 'scripts' / filename)}
    exec(compile((ROOT / 'scripts' / filename).read_bytes(), filename, 'exec'), namespace)
    return namespace


ledger = trusted_module('repin_ledger', 'decision_ledger.py')
fence = trusted_module('repin_bindings', 'decision_bindings.py')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def read_json(path):
    def reject_constant(value):
        raise ValueError(f'non-finite JSON number: {value}')
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_object,
                      parse_constant=reject_constant)


def safe_path(root, relative):
    if type(relative) is not str or not relative or '\\' in relative:
        raise ValueError(f'invalid local path: {relative!r}')
    rel = Path(relative)
    if rel.is_absolute() or '..' in rel.parts or rel.as_posix() != relative:
        raise ValueError(f'escaping/non-normalized path: {relative}')
    root = Path(root).resolve()
    path = root / rel
    if not path.resolve().is_relative_to(root):
        raise ValueError(f'escaping path: {relative}')
    for part in (path, *path.parents):
        if part == root:
            break
        if part.is_symlink():
            raise ValueError(f'symlink input: {relative}')
    return path


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def file_digest(root, path):
    return digest(safe_path(root, path).read_bytes())


def source_inventory(root):
    """Hash all regular source inputs in the documented inventory, never outputs."""
    root = Path(root).resolve()
    paths = set()
    for name in ROOT_FILES:
        if (root / name).exists():
            paths.add(name)
    for folder in FOLDERS:
        base = safe_path(root, folder)
        if base.exists():
            for path in base.rglob('*'):
                rel = path.relative_to(root)
                if any(part in SKIP for part in rel.parts) or path.suffix in ('.pyc', '.pyo'):
                    continue
                safe_path(root, rel.as_posix())
                if path.is_file():
                    paths.add(rel.as_posix())
    return {path: file_digest(root, path) for path in sorted(paths)}


def content_digest(inventory):
    return digest(json.dumps(inventory, sort_keys=True, separators=(',', ':')).encode())


def load_policy(root):
    raw = safe_path(root, NOTE).read_bytes()
    errors, _ = ledger['validate_note_bytes'](raw, NOTE)
    if errors:
        raise ValueError('; '.join(errors))
    block = ledger['extract_blocks'](raw.decode())[0]
    entries = block['entries']
    # Literal accesses are intentional: these are discoverable binding consumers.
    values = {
        'pin_class_vocabulary': entries['pin_class_vocabulary'],
        'executable_pin_inventory': entries['executable_pin_inventory'],
        'research_baseline_rule': entries['research_baseline_rule'],
        'repin_trigger_procedure': entries['repin_trigger_procedure'],
        'dual_pin_handling': entries['dual_pin_handling'],
        'claim_table_regeneration_rule': entries['claim_table_regeneration_rule'],
        'drift_fence_integration': entries['drift_fence_integration'],
        'current_pin_assessment': entries['current_pin_assessment'],
    }
    if block['decision_id'] != 'upstream-repin-policy-decision':
        raise ValueError('wrong policy decision_id')
    if any(entry['status'] != 'ADOPTED' for entry in values.values()):
        raise ValueError('required policy is not ADOPTED; separate policy review required')
    amendment_raw = safe_path(root, READ_MODEL_NOTE).read_bytes()
    errors, _ = ledger['validate_note_bytes'](amendment_raw, READ_MODEL_NOTE)
    if errors:
        raise ValueError('; '.join(errors))
    amendment = ledger['extract_blocks'](amendment_raw.decode())[0]
    entries = amendment['entries']
    registration = entries['read_model_query_pin']
    if (amendment['decision_id'] != 'read-model-query-pin-decision'
            or registration['status'] != 'ADOPTED'):
        raise ValueError('read-model query pin registration is not ADOPTED')
    record = registration['value']
    if (record['surface'] != 'read_model_draft_pin' or record['previous_surface'] != 'vendor_pin'
            or record['pin']['class'] != 'EXECUTABLE_CITATION'
            or record['pin']['vendored'] is not False
            or record['pin']['bound_tables'] != ['tests/read_model_claims.json']
            or record['source_doc'] != 'docs/contracts/READ_MODEL_QUERIES.md'
            or record['assessment'] != 'HOLD'):
        raise ValueError('unsupported read-model query pin registration')
    values = copy.deepcopy(values)
    values['read_model_query_pin'] = copy.deepcopy(registration)
    inventory = values['executable_pin_inventory']['value']
    inventory['vendor_pin']['bound_tables'].remove('tests/read_model_claims.json')
    inventory['read_model_draft_pin'] = record['pin']
    values['current_pin_assessment']['value']['read_model_draft_pin'] = record['assessment']
    return {'entries': values, 'values': {k: v['value'] for k, v in values.items()},
            'digest': digest(raw + b'\0' + amendment_raw), 'block': block}


def pins(policy):
    inventory = policy['values']['executable_pin_inventory']
    return {key: value for key, value in inventory.items()
            if isinstance(value, dict) and 'sha' in value}


def policy_contract(policy):
    """Fail closed on a governance shape this implementation cannot enforce."""
    v = policy['values']
    vocabulary = v['pin_class_vocabulary']
    dual = v['dual_pin_handling']
    research = v['research_baseline_rule']
    regeneration = v['claim_table_regeneration_rule']
    drift = v['drift_fence_integration']
    assessment = v['current_pin_assessment']
    if (vocabulary['classification_basis'] != 'consumer_role_and_bound_surface'
            or vocabulary['citation_implies_runtime_execution'] is not False
            or type(dual['active_pins_per_bound_surface_at_merge']) is not int
            or dual['active_pins_per_bound_surface_at_merge'] != 1
            or dual['standing_transition_window'] is not False
            or dual['automatic_old_new_fallback'] is not False
            or not research['preserve_historical_provenance']
            or research['must_equal_current_executable_pin']
            or research['repin_rewrites_historical_baselines']
            or research['ordinary_note_validation_exempt']
            or regeneration['deferred_regeneration_allowed']
            or not all(regeneration[key] for key in regeneration if key != 'deferred_regeneration_allowed')
            or drift['checker_bypass_allowed']
            or drift['inventory_order'] != 'sorted_unique_decision_id_entry'
            or assessment['research_head_is_automatic_replacement']
            or assessment['historical_validation_is_current_head_evidence']
            or any(value != 'HOLD' for key, value in assessment.items() if key.startswith(('vendor_pin_', 'ai_draft_pin_', 'read_model_draft_pin')))):
        raise ValueError('unsupported policy contract; separate policy review required')
    declared = pins(policy)
    if set(declared) != {'vendor_pin', 'ai_draft_pin', 'read_model_draft_pin'}:
        raise ValueError('unsupported pin inventory; separate policy review required')
    tables = [table for pin in declared.values() for table in pin['bound_tables']]
    if (len(tables) != len(set(tables)) or set(tables) != {f'tests/{s}_claims.json' for s in STEMS}
            or any(pin['class'] not in vocabulary['binding_classes'] or not SHA.fullmatch(pin['sha'])
                   for pin in declared.values())):
        raise ValueError('unsupported or duplicate declared binding surface')


def resolve_pin(root, relative, seen=()):
    """Resolve only a single module-level constant or a declared import alias."""
    if relative in seen:
        raise ValueError('cyclic PINNED_SHA alias')
    tree = ast.parse(safe_path(root, relative).read_text(encoding='utf-8'))
    writes = [node for node in ast.walk(tree) if isinstance(node, ast.Name)
              and node.id == 'PINNED_SHA' and isinstance(node.ctx, ast.Store)]
    assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'PINNED_SHA' for t in node.targets)]
    if len(writes) != 1 or len(assignments) != 1:
        raise ValueError(f'{relative}: competing or dynamic PINNED_SHA configuration')
    value = assignments[0].value
    if isinstance(value, ast.Constant) and type(value.value) is str and SHA.fullmatch(value.value):
        return value.value
    imports = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == 'capital':
            for alias in node.names:
                imports[alias.asname or alias.name] = f'capital/{alias.name}.py'
    if (isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name)
            and value.attr == 'PINNED_SHA' and value.value.id in imports
            and imports[value.value.id] in IMPLEMENTATIONS.values()):
        return resolve_pin(root, imports[value.value.id], (*seen, relative))
    raise ValueError(f'{relative}: unsupported PINNED_SHA expression/fallback')


def report():
    return {'schema': 'capital-upstream-repin-report-v1', 'label': 'SIMULATED',
            'provisional': True, 'repin_performed': False, 'approval': 'NOT_BOUND',
            'adoption': 'NOT_BOUND', 'receipt_authentication': 'NOT_BOUND',
            'findings': [], 'classifications': {}, 'research': {}, 'research_changes': [],
            'inspected_hashes': {}, 'missing_artifacts': [], 'missing_validation': []}


def finish(result, success):
    result['findings'] = sorted(set(result['findings']))
    result['status'] = 'FINDINGS' if result['findings'] else success
    return result


def inspect_snapshot(root, policy=None, proposed=None):
    root = Path(root).resolve()
    result = report()
    try:
        policy = load_policy(root) if policy is None else policy
        policy_contract(policy)
        result['policy_digest'] = policy['digest']
        result['inspected_hashes'] = source_inventory(root)
        result['content_digest'] = content_digest(result['inspected_hashes'])
        for surface, pin in pins(policy).items():
            expected = (proposed or {}).get(surface, pin['sha'])
            result['classifications'][surface] = {'class': pin['class'], 'sha': expected,
                                                 'bound_tables': pin['bound_tables']}
            for table_path in pin['bound_tables']:
                try:
                    table = read_json(safe_path(root, table_path))
                    stem = Path(table_path).stem.removesuffix('_claims')
                    if (table.get('format') != FORMATS[stem] or table.get('label') != 'CLAIM_CONFORMANCE'
                            or not isinstance(table.get('claims'), list) or not table['claims']):
                        raise ValueError('invalid claim table header/rows')
                    ids = []
                    for row in table['claims']:
                        if not isinstance(row, dict) or any(not _text(row.get(key)) for key in
                                ('id', 'source_doc', 'section', 'pinned_sha', 'claim', 'check_id', 'needle')) or 'expected' not in row:
                            raise ValueError('invalid claim row fields')
                        safe_path(root, row['source_doc'])
                        if stem == 'ce1' and 'input' not in row:
                            raise ValueError('CE1 row missing embedded input vector')
                        ids.append(row['id'])
                    if len(ids) != len(set(ids)):
                        raise ValueError('duplicate claim id')
                    active = {table.get('pinned_sha')}
                    active.update(row.get('pinned_sha') for row in table['claims'])
                    if len(active) != policy['values']['dual_pin_handling']['active_pins_per_bound_surface_at_merge'] or active != {expected}:
                        raise ValueError(f'undeclared/competing active pins: {sorted(map(str, active))}')
                    if resolve_pin(root, IMPLEMENTATIONS[stem]) != expected:
                        raise ValueError('consumer constant disagrees with declared pin')
                except (OSError, ValueError, KeyError, TypeError, AttributeError, SyntaxError) as exc:
                    result['findings'].append(f'{surface}/{table_path}: {exc}')
            if 'manifest' in pin:
                manifest = read_json(safe_path(root, pin['manifest']))
                if manifest['commit'] != expected or len(manifest['files']) != pin['file_count']:
                    result['findings'].append(f'{surface}: manifest commit/count mismatch')
                for path, expected_hash in manifest['files'].items():
                    actual = file_digest(root, 'capital/vendor/' + path)
                    if actual != expected_hash:
                        result['findings'].append(f'{surface}: vendor hash mismatch: {path}')
        # Research provenance is path/role based, never inferred from matching SHAs.
        for path in sorted((root / 'docs/decisions').glob('*.md')):
            raw = safe_path(root, path.relative_to(root).as_posix()).read_bytes()
            errors, _ = ledger['validate_note_bytes'](raw, path.relative_to(root).as_posix())
            result['findings'].extend(errors)
            text = raw.decode()
            blocks = ledger['extract_blocks'](text)
            result['research'][path.relative_to(root).as_posix()] = {
                'digest': digest(raw),
                'provenance': {'bases': blocks[0].get('bases'),
                               'basis_lines': [line for line in text.splitlines() if '기준:' in line or (
                                   '기준' in line and re.search(r'`[0-9a-f]{7,40}`', line))]},
                'class': policy['values']['pin_class_vocabulary']['classes'][-1]}
        mapping = read_json(safe_path(root, policy['values']['drift_fence_integration']['registration_file']))
        identities = [(row['decision_id'], row['entry']) for row in mapping['entries']]
        if identities != sorted(set(identities)):
            result['findings'].append('decision bindings: inventory must be sorted and unique')
        for entry in policy['values']['drift_fence_integration']['required_items']:
            if (policy['block']['decision_id'], entry) not in identities:
                result['findings'].append(f'decision bindings: missing policy entry {entry}')
        result['findings'].extend(fence['collect_findings'](root, mapping))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, SyntaxError, RecursionError) as exc:
        result['findings'].append(f'invalid snapshot: {exc}')
    return finish(result, 'HOLD')


def validation_registry():
    """Trusted technical contract. Each acceptance command is a separate record."""
    py = 'python3'
    unit = [py, '-m', 'unittest', 'discover', '-s', 'tests']
    registry = {
        'decision-ledger': [py, 'scripts/decision_ledger.py'],
        'decision-bindings': [py, 'scripts/decision_bindings.py', '--check'],
        'focused-bindings': unit + ['-p', 'test_decision_bindings.py', '-v'],
        'full-unit': unit + ['-v'],
        'docs-surface': [py, 'scripts/docs_surface.py', '--check'],
        'focused-repin': unit + ['-p', 'test_upstream_repin_check.py', '-v'],
        'manifest-vectors': [py, 'scripts/manifest_vectors.py', '--check'],
        'pack-vectors': [py, 'scripts/pack_vectors.py', '--check'],
        'finance-vectors': [py, 'scripts/finance_vectors.py', '--check'],
        'auth-matrix': [py, 'scripts/auth_matrix.py', '--check'],
        'read-model-queries': unit + ['-p', 'test_read_model_queries.py', '-v'],
    }
    for stem in STEMS:
        registry['claims:' + stem] = [py, f'scripts/{stem}_claims_check.py', '--execute']
        registry['test:' + stem] = unit + ['-p', f'test_{stem}_claims.py', '-v']
    stages = {
        'unit': [unit + ['-v'], registry['decision-bindings']],
        'storage-conformance': [unit + ['-p', 'test_storage_conformance.py', '-v'],
                                [py, '-m', 'unittest', 'tests.test_crash_replay', '-v']],
        'pinned-vendor': [[py, '-m', 'unittest', 'discover', '-s', 'capital/vendor/credit_advance_f04', '-p', 'test_mock_credit.py', '-v']],
        'upstream-claims': [[py, f'scripts/{stem}_claims_check.py'] + ([] if stem == 'read_model' else ['--execute']) for stem in
                            ('upstream', 'agent', 'read_model', 'ce1', 'adapter_identity', 'lifecycle', 'readiness')],
        'node-check': [['node', '--check', 'capital/static/app.js']],
        'browser': [['npm', 'run', 'test:browser']],
        'packaged-smoke': [[py, 'scripts/build_release.py', '--out', 'build/acceptance-dist'],
                           [py, 'scripts/smoke_release.py', 'build/acceptance-dist/capital-<version>.pyz']],
        'seeded-demo': [[py, 'scripts/seed_demo.py']],
        'integrated-journeys': [[py, 'scripts/sim_journeys.py', '--check']],
    }
    for stage, commands in stages.items():
        for index, command in enumerate(commands):
            registry[f'acceptance:{stage}:{index}'] = command
    return registry


def required_evidence(policy, surface, baseline, candidate):
    """Return the minimum atomic dependency closure, including unchanged outputs."""
    pin = pins(policy)[surface]
    hashes = source_inventory(candidate)
    base_hashes = source_inventory(baseline)
    artifacts = {}
    def add(path, role):
        artifacts.setdefault(path, role)
    for table in pin['bound_tables']:
        stem = Path(table).stem.removesuffix('_claims')
        for path, role in ((table, 'claim-table-and-embedded-vectors'),
                           (IMPLEMENTATIONS[stem], 'producer-and-embedded-vectors'),
                           (f'scripts/{stem}_claims_check.py', 'citation-checker'),
                           (f'tests/test_{stem}_claims.py', 'producer-vectors')):
            add(path, role)
        data = read_json(safe_path(candidate, table))
        for claim in data['claims']:
            add(f'source_material/{surface}/' + claim['source_doc'], 'source')
    # Shared artifact formats carry pin, receipts and decisions for either class.
    for path in set(hashes) | set(base_hashes):
        if path.startswith(('tests/vectors/manifest/', 'tests/vectors/pack/', 'tests/golden/')):
            add(path, 'vectors-or-goldens')
    for path in ('capital/export.py', 'capital/verify.py', 'capital/evidence.py', 'capital/protocol.py', 'capital/service.py',
                 'README.md', 'docs/OPERATOR_HANDBOOK_KO.md', 'docs/INTEGRATION.md',
                 'docs/VALIDATION.md', 'docs/CAPITAL_REQUIREMENTS_KO.md',
                 'docs/SEAMS.md', 'docs/RELEASES.md',
                 'tests/decision_bindings.json', 'scripts/docs_surface.py', NOTE, READ_MODEL_NOTE):
        add(path, 'current-reference-or-binding' if path.startswith(('docs/', 'README', 'tests/decision')) else 'receipt-export-pack')
    checks = {'decision-ledger', 'decision-bindings', 'focused-bindings', 'full-unit',
              'docs-surface', 'focused-repin', 'manifest-vectors', 'pack-vectors'}
    for table in pin['bound_tables']:
        stem = Path(table).stem.removesuffix('_claims')
        checks.update(('claims:' + stem, 'test:' + stem, 'citation:' + stem))
    if surface == 'read_model_draft_pin':
        for path in ('capital/server.py', 'capital/auth.py', 'capital/contract/facade-v1.json',
                     'scripts/auth_matrix.py', 'tests/auth_matrix.json',
                     'tests/test_read_model_queries.py', 'tests/test_read_model_surface_claims.py',
                     'tests/vectors/finance_vectors.json'):
            add(path, 'read-model-query-surface')
        checks.update(('finance-vectors', 'auth-matrix', 'read-model-queries'))
    vendor = 'manifest' in pin
    if vendor:
        manifest = read_json(safe_path(candidate, pin['manifest']))
        add(pin['manifest'], 'manifest')
        for path in manifest['files']:
            add('capital/vendor/' + path, 'vendor')
            add(f'source_material/{surface}/' + manifest['source_prefix'] + path, 'source')
        add('tests/vectors/finance_vectors.json', 'finance-vectors')
        checks.add('finance-vectors')
    registry = validation_registry()
    stages = {'unit', 'upstream-claims', 'browser', 'packaged-smoke', 'seeded-demo', 'integrated-journeys'}
    changed = {path for path in set(hashes) | set(base_hashes) if hashes.get(path) != base_hashes.get(path)}
    storage_inputs = {'capital/events.py', 'capital/overlay.py', 'capital/projection.py',
                      'capital/strict_json.py', 'capital/resources.py'}
    if vendor or changed & storage_inputs or any(path.startswith((
            'capital/store', 'tests/test_storage', 'tests/test_crash',
            'tests/vectors/workspace/', 'tests/vectors/workspace_crash')) for path in changed):
        stages.add('storage-conformance')
    if vendor or any(path.startswith('capital/vendor/') for path in changed):
        stages.add('pinned-vendor')
    if vendor or 'capital/static/app.js' in changed:
        stages.add('node-check')
    checks.update(key for key in registry if key.startswith('acceptance:') and key.split(':')[1] in stages)
    commands = {key: registry[key] for key in sorted(checks) if key in registry}
    for table in pin['bound_tables']:
        stem = Path(table).stem.removesuffix('_claims')
        commands['citation:' + stem] = ['python3', f'scripts/{stem}_claims_check.py', '--protocol-dir', f'source_material/{surface}']
    # Package name is statically derived from the supplied candidate, never imported.
    tree = ast.parse(safe_path(candidate, 'capital/__init__.py').read_text())
    version = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == '__version__' for t in n.targets))
    if not isinstance(version, str) or not re.fullmatch(r'[A-Za-z0-9_.+-]+', version):
        raise ValueError('invalid candidate version')
    commands = {key: [arg.replace('<version>', version) for arg in argv] for key, argv in commands.items()}
    return {'artifacts': dict(sorted(artifacts.items())), 'validation': dict(sorted(commands.items()))}


def _text(value):
    return type(value) is str and bool(value.strip())


def _validate_artifacts(change, required, candidate, findings):
    records = change.get('artifacts', [])
    if type(records) is not list:
        raise ValueError('artifacts must be a list')
    seen = set()
    for record in records:
        path = record['path']
        if path in seen:
            findings.append(f'duplicate artifact: {path}')
        seen.add(path)
        if (record.get('digest') != file_digest(candidate, path)
                or record.get('role') != required['artifacts'].get(path, record.get('role'))
                or not _text(record.get('role'))
                or not _text(record.get('procedure'))
                or record.get('result') not in ('REGENERATED', 'UNCHANGED_REGENERATED', 'SOURCE_INSPECTED')):
            findings.append(f'invalid artifact/regeneration evidence: {path}')
        if record.get('result') == 'SOURCE_INSPECTED' and record.get('role') != 'source':
            findings.append(f'artifact requires regeneration result: {path}')
        if required['artifacts'].get(path) in ('claim-table-and-embedded-vectors', 'producer-and-embedded-vectors', 'producer-vectors') and record.get('method') != 'manual':
            findings.append(f'hand-maintained claim/vector requires manual reconstruction evidence: {path}')
        if record.get('method') not in ('manual', 'generator'):
            findings.append(f'artifact needs regeneration method: {path}')
        if record.get('method') == 'manual':
            sources = record.get('claim_evidence', [])
            expectations = record.get('independent_expectations', [])
            claims = {}
            if required['artifacts'].get(path) in ('claim-table-and-embedded-vectors', 'producer-and-embedded-vectors', 'producer-vectors'):
                stem = Path(path).stem.removeprefix('test_').removesuffix('_check').removesuffix('_claims')
                claims = {row['id']: row for row in read_json(safe_path(candidate, f'tests/{stem}_claims.json'))['claims']}
            valid = isinstance(sources, list) and isinstance(expectations, list) and bool(sources) and bool(expectations)
            if valid:
                valid = all(isinstance(item, dict) and _text(item.get('claim_id'))
                            and _text(item.get('explanation'))
                            and item.get('source_digest') == file_digest(candidate, item['source_path'])
                            for item in sources)
                valid = valid and all(isinstance(item, dict) and _text(item.get('claim_id'))
                                      and 'expected' in item and _text(item.get('rationale'))
                                      for item in expectations)
                if valid:
                    source_ids = [item['claim_id'] for item in sources]
                    expected_ids = [item['claim_id'] for item in expectations]
                    valid = (len(source_ids) == len(set(source_ids)) and len(expected_ids) == len(set(expected_ids))
                             and set(claims) <= set(source_ids) & set(expected_ids))
                    for item in sources:
                        if item['claim_id'] in claims:
                            source_path = f"source_material/{change['surface']}/" + claims[item['claim_id']]['source_doc']
                            valid = valid and item['source_path'] == source_path
                    for item in expectations:
                        if item['claim_id'] in claims:
                            valid = valid and json.dumps(item['expected'], sort_keys=True) == json.dumps(claims[item['claim_id']]['expected'], sort_keys=True)
            if not valid:
                findings.append(f'manual regeneration needs claim evidence and independent expectations: {path}')
    return sorted(set(required['artifacts']) - seen)


def _validate_results(change, required, evidence, candidate_report, log_root, findings):
    seen = set()
    records = change.get('validation', [])
    if type(records) is not list:
        raise ValueError('validation must be a list')
    for record in records:
        key = record['check_id']
        if key in seen:
            findings.append(f'duplicate validation: {key}')
        seen.add(key)
        if (key not in required['validation'] or record.get('argv') != required['validation'][key]
                or record.get('candidate_id') != evidence['candidate_id']
                or record.get('candidate_digest') != candidate_report['content_digest']
                or type(record.get('exit_code')) is not int or record['exit_code'] != 0
                or record.get('result') != 'PASS'
                or not record.get('logs')):
            findings.append(f'invalid/stale/failed validation: {key}')
        log_paths = set()
        log_text = []
        for log in record.get('logs', []):
            if log['path'] in log_paths:
                findings.append(f'duplicate log: {key}/{log["path"]}')
            log_paths.add(log['path'])
            if file_digest(log_root, log['path']) != log.get('digest'):
                findings.append(f'log digest mismatch: {key}/{log["path"]}')
            log_text.append(safe_path(log_root, log['path']).read_text(encoding='utf-8'))
        output = '\n'.join(log_text)
        if re.search(r'(?m)^(?:FAILED\b|FAIL[ :]|SKIPPED(?:\b|_)|DRIFT[ :]|Traceback\b|Error:|[0-9]+ failed\b)|(?:failed|failures|errors|skipped)=[1-9][0-9]*', output):
            findings.append(f'contradictory failed/skipped log: {key}')
        if not output.strip():
            findings.append(f'empty validation log: {key}')
        if key.startswith('citation:'):
            stem = key.split(':')[1]
            count = len(read_json(safe_path(candidate_report['root'], f'tests/{stem}_claims.json'))['claims'])
            if f'CLAIM_DRIFT verified={count} total={count}' not in output or 'SKIPPED' in output:
                findings.append(f'citation source verification missing/skipped: {key}')
    return sorted(set(required['validation']) - seen)


def compare_snapshots(baseline, candidate, evidence, *, log_root):
    result = report()
    try:
        if any(Path(log_root).resolve().is_relative_to(Path(p).resolve()) for p in (baseline, candidate)):
            raise ValueError('logs must be external to source snapshots')
        policy = load_policy(baseline)
        base = inspect_snapshot(baseline, policy)
        result['findings'].extend('baseline: ' + f for f in base['findings'])
        if base['findings']:
            return finish(result, 'EVIDENCE_COMPLETE')
        if evidence.get('schema') != SCHEMA:
            raise ValueError('invalid evidence schema')
        if not all(_text(evidence.get(key)) for key in ('baseline_id', 'candidate_id')):
            raise ValueError('explicit baseline_id/candidate_id required')
        if not isinstance(evidence.get('changes'), list):
            raise ValueError('changes must be a list')
        proposed = {}
        for change in evidence['changes']:
            surface = change['surface']
            if surface not in pins(policy) or surface in proposed:
                raise ValueError('unknown/duplicate changed surface')
            if (change['old_sha'] != pins(policy)[surface]['sha']
                    or not SHA.fullmatch(change['new_sha']) or change['new_sha'] == change['old_sha']):
                raise ValueError('invalid old/new full SHA')
            proposed[surface] = change['new_sha']
        cand_policy = load_policy(candidate)
        expected = copy.deepcopy(policy['entries'])
        for surface, sha in proposed.items():
            expected['executable_pin_inventory']['value'][surface]['sha'] = sha
            if surface == 'read_model_draft_pin':
                expected['read_model_query_pin']['value']['pin']['sha'] = sha
        if json.dumps(cand_policy['entries'], sort_keys=True) not in (
                json.dumps(policy['entries'], sort_keys=True), json.dumps(expected, sort_keys=True)):
            result['findings'].append('candidate policy governance changed beyond declared inventory SHA replacements')
        cand = inspect_snapshot(candidate, policy, proposed)
        result['findings'].extend('candidate: ' + f for f in cand['findings'])
        result.update({key: cand[key] for key in ('classifications', 'research', 'inspected_hashes')})
        result['baseline_digest'] = base['content_digest']
        result['candidate_digest'] = cand.get('content_digest')
        result['policy_digests'] = {'baseline': policy['digest'], 'candidate': cand_policy['digest']}
        for key in ('baseline_digest', 'candidate_digest', 'policy_digests'):
            if evidence.get(key) != result[key]:
                result['findings'].append(f'evidence {key} mismatch')
        # Vendor content cannot move invisibly under the same commit; membership
        # is established by baseline, even if candidate edits its own manifest.
        vendor = pins(policy)['vendor_pin']
        old_manifest = read_json(safe_path(baseline, vendor['manifest']))
        new_manifest = read_json(safe_path(candidate, vendor['manifest']))
        if (set(old_manifest['files']) != set(new_manifest['files'])
                or old_manifest['repository'] != new_manifest['repository']
                or old_manifest['source_prefix'] != new_manifest['source_prefix']):
            result['findings'].append('vendor manifest membership/source identity changed')
        if 'vendor_pin' not in proposed:
            for path in [vendor['manifest'], *('capital/vendor/' + p for p in old_manifest['files'])]:
                if file_digest(baseline, path) != file_digest(candidate, path):
                    result['findings'].append(f'undeclared vendor byte movement: {path}')
        for change in evidence['changes']:
            surface = change['surface']
            if change.get('trigger') not in policy['values']['repin_trigger_procedure']['triggers']:
                result['findings'].append(f'{surface}: unauthorized/non-trigger review basis')
            for field in ('acceptance_basis', 'decision_maker', 'consumer_impact',
                          'compatibility_authority_analysis', 'rollback'):
                if not _text(change.get(field)):
                    result['findings'].append(f'{surface}: missing {field}')
            required = required_evidence(policy, surface, baseline, candidate)
            for table_path in pins(policy)[surface]['bound_tables']:
                table = read_json(safe_path(candidate, table_path))
                for claim in table['claims']:
                    source_path = f'source_material/{surface}/' + claim['source_doc']
                    source_text = safe_path(candidate, source_path).read_text(encoding='utf-8')
                    if claim['section'] not in source_text or claim['needle'] not in source_text:
                        result['findings'].append(f'{surface}: source citation missing: {table_path}/{claim["id"]}')
            cand['root'] = str(Path(candidate).resolve())
            result['missing_artifacts'].extend(f'{surface}:{path}' for path in
                _validate_artifacts(change, required, candidate, result['findings']))
            result['missing_validation'].extend(f'{surface}:{key}' for key in
                _validate_results(change, required, evidence, cand, log_root, result['findings']))
            # Verify source copies match vendor bytes, rather than just carrying hashes.
            if 'manifest' in pins(policy)[surface]:
                for path in new_manifest['files']:
                    source = f'source_material/{surface}/' + new_manifest['source_prefix'] + path
                    if file_digest(candidate, source) != file_digest(candidate, 'capital/vendor/' + path):
                        result['findings'].append(f'{surface}: source/vendor bytes disagree: {path}')
        # Historical sources may differ without executable drift. Corrections
        # retain the original record and require dated replacement provenance.
        corrections = evidence.get('research_corrections', [])
        if not isinstance(corrections, list):
            raise ValueError('research_corrections must be a list')
        by_path = {item['path']: item for item in corrections}
        if len(by_path) != len(corrections):
            raise ValueError('duplicate research correction')
        for path, original in base['research'].items():
            current = cand['research'].get(path)
            if current is None or original['provenance'] != current['provenance']:
                result['research_changes'].append({'path': path, 'original': original, 'candidate': current})
                correction = by_path.get(path, {})
                try:
                    datetime.date.fromisoformat(correction.get('date', ''))
                    valid = (correction.get('original_digest') == original['digest']
                             and correction.get('original_provenance') == original['provenance']
                             and _text(correction.get('reason')) and _text(correction.get('replacement_basis'))
                             and current is not None)
                except (ValueError, TypeError):
                    valid = False
                if not valid:
                    result['findings'].append(f'research provenance correction incomplete: {path}')
        result['missing_artifacts'].sort()
        result['missing_validation'].sort()
        result['findings'].extend('missing artifact: ' + path for path in result['missing_artifacts'])
        result['findings'].extend('missing validation: ' + key for key in result['missing_validation'])
    except (OSError, ValueError, KeyError, TypeError, AttributeError, SyntaxError, RecursionError, StopIteration) as exc:
        result['findings'].append(f'invalid comparison: {exc}')
    return finish(result, 'EVIDENCE_COMPLETE')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--root', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args(argv)
    if args.check:
        if not args.root or args.baseline or args.candidate or args.evidence:
            parser.error('--check requires --root only')
        result = inspect_snapshot(args.root)
    else:
        if args.root or not all((args.baseline, args.candidate, args.evidence)):
            parser.error('comparison requires --baseline, --candidate and --evidence')
        try:
            # Evidence/logs live outside either source snapshot, preventing a
            # self-referential digest and accidental evidence-as-source claims.
            evidence_path = args.evidence.resolve()
            if any(evidence_path.is_relative_to(p.resolve()) for p in (args.baseline, args.candidate)):
                raise ValueError('evidence must be external to source snapshots')
            result = compare_snapshots(args.baseline, args.candidate, read_json(evidence_path),
                                       log_root=evidence_path.parent)
        except (OSError, ValueError, RecursionError) as exc:
            result = finish(dict(report(), findings=[f'invalid evidence: {exc}']), 'EVIDENCE_COMPLETE')
    print(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False))
    return int(bool(result['findings']))


if __name__ == '__main__':
    sys.exit(main())
