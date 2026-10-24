#!/usr/bin/env python3
"""Read-only declared-reference fence, not proof of financial correctness.

AST recognition covers note-specific literal entry access, terms _USABLE keys,
self._value/_ready calls, entries.get/subscripts, and overlay _adopted calls.
Generic enumeration and dynamic access are not semantic proof of consumption.
Pending targets are existing integration anchors, not implementation claims.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


ledger = load_module('binding_ledger', ROOT / 'scripts/decision_ledger.py')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key {key}')
        result[key] = value
    return result


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_object)


def literal(node):
    return node.value if isinstance(node, ast.Constant) and type(node.value) is str else None


def inventory(root, findings):
    trees = {}
    for folder in ('capital', 'scripts'):
        for path in sorted((root / folder).rglob('*.py')):
            if 'vendor' in path.relative_to(root).parts or path.is_symlink():
                continue
            try:
                trees[path.relative_to(root).as_posix()] = ast.parse(path.read_text(encoding='utf-8'))
            except (OSError, UnicodeError, SyntaxError) as exc:
                findings.append(f'{path.relative_to(root)}: cannot inspect: {exc}')
    return trees


def discover_consumers(trees, rows):
    found = set()
    by_note = {Path(row['note']).name: row for row in rows}
    for path, tree in trees.items():
        strings = {Path(literal(node)).name for node in ast.walk(tree) if literal(node)}
        notes = [row for name, row in by_note.items() if name in strings]
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute):
                    if func.attr in ('_value', '_ready') or (
                            func.attr == 'get' and isinstance(func.value, ast.Name)
                            and func.value.id == 'entries'):
                        names.update(filter(None, map(literal, node.args)))
                elif isinstance(func, ast.Name) and func.id == '_adopted' and len(node.args) == 2:
                    names.add(literal(node.args[1]))
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == 'entries':
                names.add(literal(node.slice))
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_USABLE' for t in node.targets):
                if isinstance(node.value, ast.Dict):
                    names.update(map(literal, node.value.keys))
        for row in notes:
            for name in names:
                if row['entries'].get(name) == 'ADOPTED':
                    found.add((row['decision_id'], name, path))
    return found


def live_routes(trees):
    values = {}
    for path, names in (('capital/server.py', ('GET_DISPATCH', 'POST_DISPATCH')),
                        ('capital/auth.py', ('ROUTE_PERMISSIONS',))):
        for node in ast.walk(trees.get(path, ast.Module(body=[], type_ignores=[]))):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in names:
                        values[target.id] = [tuple(
                            item.id if isinstance(item, ast.Name) else ast.literal_eval(item)
                            for item in row.elts) for row in node.value.elts]
    get = values['GET_DISPATCH']
    if [(p, c) for p, c, _ in get] != [(p, c) for p, _, c in values['ROUTE_PERMISSIONS']]:
        raise ValueError('GET_DISPATCH disagrees with ROUTE_PERMISSIONS')
    return {('GET', p) for p, _, _ in get} | {('POST', p) for p, _ in values['POST_DISPATCH']}


def collect_findings(root, mapping):
    root = Path(root).resolve()
    findings = []
    expected = ledger.expected_note_paths((root / 'docs/CAP_COVERAGE.md').read_text(encoding='utf-8'))
    decisions = root / 'docs/decisions'
    findings.extend(ledger.collect_errors(decisions, expected))
    rows = ledger.build_index(decisions, expected)
    adopted = {}
    ids = set()
    for row in rows:
        decision = row['decision_id']
        if decision is not None:
            if decision in ids:
                findings.append(f'duplicate decision_id {decision}')
            ids.add(decision)
        for name, status in row['entries'].items():
            if status == 'ADOPTED':
                adopted[(decision, name)] = row['note']
    trees = inventory(root, findings)
    try:
        routes = live_routes(trees)
    except (KeyError, ValueError, TypeError, AttributeError):
        findings.append('route registry invalid: missing, malformed, or inconsistent dispatch/permissions')
        routes = set()
    if type(mapping) is not dict or set(mapping) != {'schema', 'entries'} or mapping.get('schema') != 'capital-decision-bindings-v1' or type(mapping.get('entries')) is not list:
        return sorted(findings + ['invalid binding map schema'])
    listed = set()
    consumed = set()
    for row in mapping['entries']:
        if type(row) is not dict or set(row) != {'decision_id', 'entry', 'note', 'bindings'} or not all(type(row.get(k)) is str and row[k].strip() for k in ('decision_id', 'entry', 'note')):
            findings.append('invalid binding entry shape')
            continue
        identity = (row['decision_id'], row['entry'])
        label = '/'.join(identity)
        if identity in listed:
            findings.append(f'{label}: duplicate binding entry')
        listed.add(identity)
        if identity not in adopted:
            findings.append(f'{label}: not an ADOPTED entry')
        elif row['note'] != adopted[identity]:
            findings.append(f'{label}: mismatched note')
        bindings = row['bindings']
        if type(bindings) is not list or not bindings:
            findings.append(f'{label}: requires bindings')
            continue
        seen = set()
        for binding in bindings:
            if type(binding) is not dict:
                findings.append(f'{label}: invalid binding shape')
                continue
            kind, status = binding.get('kind'), binding.get('status')
            keys = {'kind', 'status'} | ({'method', 'route_id'} if kind == 'route' else {'path'})
            if status == 'PENDING_CONSUMER':
                keys |= {'consumer_node', 'reason'}
            if set(binding) != keys or kind not in ('module', 'test_module', 'route') or status not in ('CONSUMED', 'PENDING_CONSUMER') or not all(type(v) is str and v.strip() for v in binding.values()):
                findings.append(f'{label}: invalid binding shape/status or pending consumer metadata')
                continue
            token = tuple(sorted(binding.items()))
            if token in seen:
                findings.append(f'{label}: duplicate binding')
            seen.add(token)
            if kind == 'route':
                target = (binding['method'], binding['route_id'])
                if target not in routes:
                    findings.append(f'{label}: missing route {target}')
                continue
            relative = Path(binding['path'])
            target = root / relative
            valid = not relative.is_absolute() and '..' not in relative.parts and target.resolve().is_relative_to(root)
            valid = valid and target.is_file() and relative.suffix == '.py'
            valid = valid and (relative.parts[0] == 'tests' and relative.name.startswith('test_') if kind == 'test_module' else relative.parts[0] in ('capital', 'scripts') and 'vendor' not in relative.parts)
            if not valid:
                findings.append(f'{label}: missing or invalid {kind} {relative}')
            if status == 'CONSUMED':
                consumed.add((*identity, relative.as_posix()))
    for identity in adopted.keys() - listed:
        findings.append(f'{"/".join(identity)}: ADOPTED entry lacks binding')
    for decision, name, path in discover_consumers(trees, rows) - consumed:
        findings.append(f'{decision}/{name}: unlisted CONSUMED module {path} (absent or mislabeled pending)')
    return sorted(set(findings))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', required=True)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        findings = collect_findings(args.root, read_json(args.root / 'tests/decision_bindings.json'))
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        findings = [f'cannot check bindings: {exc}']
    for finding in findings:
        print(finding, file=sys.stderr)
    if not findings:
        print('decision bindings ok: declared references only; pending anchors are not implementation')
    return int(bool(findings))


if __name__ == '__main__':
    sys.exit(main())
