"""Stdlib checker for capital/contract/facade-v1.json.

Unknown fields are rejected wherever a schema object lists `properties` and
does not set `additionalProperties` to true or to a nested schema. This is
the local facade namespace `capital-local-facade/1`. It is not the promoted
Protocol catalogue and not SEMANTIC_CONFORMANCE.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path


class SchemaError(Exception):
    def __init__(self, path, message):
        self.path = path
        self.message = message
        super().__init__(f'{path}: {message}')


def contract_path():
    return Path(__file__).resolve().parents[1] / 'capital' / 'contract' / 'facade-v1.json'


def load_contract(path=None):
    raw = Path(path).read_bytes() if path is not None else contract_path().read_bytes()
    if raw.startswith(b'\xef\xbb\xbf') or b'\x00' in raw:
        raise SchemaError('$', 'rejected encoding')
    return json.loads(raw.decode('utf-8'))


def validate(value, schema, root=None, path='$'):
    if root is None:
        root = schema
    if '$ref' in schema:
        target = copy.deepcopy(_resolve(root, schema['$ref']))
        if 'partTag' in schema:
            target.setdefault('properties', {})['part_tag'] = {'const': schema['partTag']}
            target['required'] = list(target.get('required', [])) + ['part_tag']
        return validate(value, target, root, path)
    if 'anyOf' in schema:
        errors = []
        for index, alternative in enumerate(schema['anyOf']):
            try:
                validate(value, alternative, root, path)
                return
            except SchemaError as exc:
                errors.append(str(exc))
        raise SchemaError(path, 'no alternative matched: ' + ' | '.join(errors[:4]))
    if 'const' in schema and value != schema['const']:
        raise SchemaError(path, f'const {schema["const"]!r}')
    if 'enum' in schema and value not in schema['enum']:
        raise SchemaError(path, f'not in enum')
    expected = schema.get('type')
    if expected is not None:
        kinds = expected if type(expected) is list else [expected]
        if not any(_is_type(value, kind) for kind in kinds):
            raise SchemaError(path, f'type {expected} got {type(value).__name__}')
    if type(value) is dict and ('properties' in schema or 'additionalProperties' in schema or 'required' in schema):
        _object(value, schema, root, path)
    if type(value) is list and 'items' in schema:
        minimum = schema.get('minItems', 0)
        maximum = schema.get('maxItems')
        if len(value) < minimum:
            raise SchemaError(path, 'minItems')
        if maximum is not None and len(value) > maximum:
            raise SchemaError(path, 'maxItems')
        for index, item in enumerate(value):
            validate(item, schema['items'], root, f'{path}[{index}]')
    if type(value) is str and 'pattern' in schema:
        import re
        if re.fullmatch(schema['pattern'], value) is None:
            raise SchemaError(path, 'pattern')


def _resolve(root, ref):
    prefix = '#/definitions/'
    if not ref.startswith(prefix):
        raise SchemaError(ref, 'unsupported ref')
    name = ref[len(prefix):]
    try:
        return root['definitions'][name]
    except KeyError as exc:
        raise SchemaError(ref, 'missing definition') from exc


def _is_type(value, kind):
    if kind == 'object':
        return type(value) is dict
    if kind == 'array':
        return type(value) is list
    if kind == 'string':
        return type(value) is str
    if kind == 'integer':
        return type(value) is int
    if kind == 'boolean':
        return type(value) is bool
    if kind == 'null':
        return value is None
    raise SchemaError('$', f'unknown type {kind}')


def _object(value, schema, root, path):
    required = schema.get('required', [])
    properties = schema.get('properties', {})
    additional = schema.get('additionalProperties', False)
    for name in required:
        if name not in value:
            raise SchemaError(path, f'missing {name}')
    for name, item in value.items():
        if name in properties:
            validate(item, properties[name], root, f'{path}.{name}')
            continue
        if additional is False:
            raise SchemaError(path, f'unknown field {name}')
        if additional is True:
            continue
        if type(additional) is dict:
            validate(item, additional, root, f'{path}.{name}')
            continue
        raise SchemaError(path, 'additionalProperties')
