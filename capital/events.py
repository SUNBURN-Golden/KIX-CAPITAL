"""Offline summary reader for the opt-in size-bounded JSONL event log.

`python3 -m capital.events FILE --summary` reads one file with no server:
every line must have exactly the writer's five fields (`time`, `route`,
`status`, `code`, `operation_id`), and the report prints per-route,
per-status, and per-code counts, `without_code`, and the first/last UTC
timestamps as one JSON line. The first malformed line stops the run with a
non-zero exit that names its 1-based line number. `dropped` and `errors`
are process counters the file does not carry, so they stay null under
`NOT_OBSERVABLE_OFFLINE` — read GET /api/metrics `counters.event_log` for
them. Pure stdlib; reads bytes, writes nothing. This is not an exporter,
not a trace, and not audit or financial evidence.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from capital.observability import EVENT_LOG_KEYS, HTTP_CLASSES, _CODE, _OP_ID, _status_class
from capital.verify import loads

# The writer's exact stamp: _utc_now() is '%Y-%m-%dT%H:%M:%S.%fZ' with a
# six-digit %f, so other ISO-8601 spellings are malformed for this format.
_TIME = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z')
_TIME_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'
_KEY_SET = frozenset(EVENT_LOG_KEYS)


class EventLogError(Exception):
    """The first malformed line, with its `reason` and 1-based `line_no`."""

    def __init__(self, reason, line_no):
        super().__init__(f'{reason} at line {line_no}')
        self.reason = reason
        self.line_no = line_no


def _validated(chunk, line_no):
    """Parse one line and enforce the writer's exact five-field shape.

    Route labels are not checked against the closed dispatch set: a log
    written by a build with other routes must still summarize.
    """

    def bad(reason):
        raise EventLogError(reason, line_no)

    if not chunk:
        bad('BLANK_LINE')
    if not chunk.isascii():
        bad('NON_ASCII')
    try:
        row = loads(chunk)
    except (ValueError, RecursionError):
        bad('BAD_JSON')
    if type(row) is not dict:
        bad('NOT_AN_OBJECT')
    if set(row) != _KEY_SET:
        bad('FIELD_SET')
    stamp = row['time']
    if type(stamp) is not str or _TIME.fullmatch(stamp) is None:
        bad('TIME_SHAPE')
    try:
        moment = datetime.strptime(stamp, _TIME_FORMAT)
    except ValueError:
        bad('TIME_SHAPE')
    route = row['route']
    if type(route) is not str or not route or not route.isascii():
        bad('ROUTE_SHAPE')
    status = row['status']
    if type(status) is not int or not 0 <= status <= 599:
        bad('STATUS_SHAPE')
    code = row['code']
    if code is not None and (type(code) is not str or _CODE.fullmatch(code) is None):
        bad('CODE_SHAPE')
    operation_id = row['operation_id']
    if operation_id is not None and (
            type(operation_id) is not str or _OP_ID.fullmatch(operation_id) is None):
        bad('OPERATION_ID_SHAPE')
    return route, status, code, stamp, moment


def _summarize(raw, name):
    by_route = {}
    by_status = {}
    by_status_class = {klass: 0 for klass in HTTP_CLASSES}
    unclassed = 0
    by_code = {}
    without_code = 0
    events = 0
    first_stamp = first_moment = last_stamp = last_moment = None
    lines = raw.split(b'\n')
    if lines and lines[-1] == b'':
        lines.pop()  # every writer record ends with exactly one newline
    for line_no, chunk in enumerate(lines, start=1):
        route, status, code, stamp, moment = _validated(chunk, line_no)
        events += 1
        by_route[route] = by_route.get(route, 0) + 1
        label = str(status)
        by_status[label] = by_status.get(label, 0) + 1
        klass = _status_class(status)
        if klass is None:
            unclassed += 1
        else:
            by_status_class[klass] += 1
        if code is None:
            without_code += 1
        else:
            by_code[code] = by_code.get(code, 0) + 1
        if first_moment is None or moment < first_moment:
            first_moment, first_stamp = moment, stamp
        if last_moment is None or moment > last_moment:
            last_moment, last_stamp = moment, stamp
    if unclassed:
        by_status_class['other'] = unclassed
    return {
        'ok': True,
        'reason': None,
        'mode': 'OFFLINE_EVENT_LOG_SUMMARY',
        'label': 'SIMULATED',
        'diagnostic': 'LOCAL_ONLY',
        'file': name,
        'events': events,
        'first_time': first_stamp,
        'last_time': last_stamp,
        'by_route': by_route,
        'by_status': by_status,
        'by_status_class': by_status_class,
        'by_code': by_code,
        'without_code': without_code,
        'event_log': {
            'written': events,
            'dropped': None,
            'errors': None,
            'dropped_errors': 'NOT_OBSERVABLE_OFFLINE',
            'note': ('dropped and errors are process counters '
                     '(GET /api/metrics counters.event_log); '
                     'a file-only reader cannot observe them'),
        },
        'writes': False,
        'server_required': False,
        'funds_executed': False,
        'not_bound': {
            'exporter': 'NOT_BOUND',
            'tracing': 'NOT_BOUND',
            'alerting': 'NOT_BOUND',
            'network_sinks': 'NOT_BOUND',
            'audit_or_financial_evidence': 'NOT_BOUND',
        },
    }


def summarize_path(path):
    """Read FILE bytes and return the summary report dict.

    Raises EventLogError on the first malformed line and OSError when the
    file cannot be read. Nothing is written; no server is contacted.
    """
    name = os.fspath(path)
    return _summarize(Path(name).read_bytes(), os.path.basename(name))


def main(argv=None):
    parser = argparse.ArgumentParser(description=(
        'Summarize one opt-in size-bounded JSONL event log offline. '
        'Reads bytes only, writes nothing, needs no server. '
        'Not an exporter, a trace, or audit or financial evidence.'
    ))
    parser.add_argument('file', nargs='?', help='JSONL event log written by --event-log FILE')
    parser.add_argument('--summary', action='store_true', required=True,
                        help='Print one JSON line: per-route, per-status, per-code counts, '
                             'without_code, and first/last UTC timestamps. The only mode.')
    args = parser.parse_args(argv)
    if args.file is None:
        parser.error('file is required')
    try:
        report = summarize_path(args.file)
    except EventLogError as exc:
        sys.stderr.write(f'capital.events: {args.file}:{exc.line_no}: {exc.reason}\n')
        return 1
    except OSError:
        sys.stderr.write(f'capital.events: {args.file}: EVENT_LOG_UNREADABLE\n')
        return 1
    sys.stdout.write(json.dumps(report, sort_keys=True, separators=(',', ':')) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
