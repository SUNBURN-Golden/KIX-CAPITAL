import json


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def loads(raw):
    if raw.startswith(b'\xef\xbb\xbf') or b'\x00' in raw:
        raise ValueError('rejected encoding')
    return json.loads(
        raw.decode('utf-8'), object_pairs_hook=_strict_object,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
    )
