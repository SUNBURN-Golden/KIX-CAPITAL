"""Process-local counters, fixed-bucket latency, and an opt-in JSONL event log.

This is LOCAL_OBSERVABILITY. Counters live in this process and reset when the
process exits. They are not audit evidence, financial evidence, or an SLO.
External exporters, tracing, alerting, and network sinks stay NOT_BOUND.
The event log is size-bounded and never receives bodies, arguments, or tokens.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime, timezone

from capital.auth import OP_ORDER

LATENCY_MS = (5, 25, 100, 500, 2500)
BUCKET_KEYS = tuple(f'le_{bound}' for bound in LATENCY_MS) + ('gt_2500',)
HISTOGRAM_KEYS = BUCKET_KEYS + ('count', 'max_ms')
HTTP_CLASSES = ('2xx', '4xx', '5xx')
EVENT_LOG_KEYS = ('time', 'route', 'status', 'code', 'operation_id')
EVENT_LOG_MAX_BYTES = 1 << 20
OUTCOMES = ('ACCEPTED', 'REJECTED')
LOOKUP_OUTCOMES = ('KNOWN', 'UNKNOWN')

_CODE = re.compile(r'[A-Z][A-Z0-9_]{0,63}\Z')
_OP_ID = re.compile(r'[A-Za-z0-9-]{1,80}\Z')


def _empty_histogram():
    return {key: 0 for key in HISTOGRAM_KEYS}


def _status_class(status):
    if type(status) is not int:
        return None
    if 200 <= status <= 299:
        return '2xx'
    if 400 <= status <= 499:
        return '4xx'
    if 500 <= status <= 599:
        return '5xx'
    return None


def _safe_code(code):
    """Keep rejection labels inside a fixed token shape. Anything else is `other`."""
    if code is None:
        return None
    if type(code) is str and _CODE.fullmatch(code):
        return code
    return 'other'


def _safe_operation_id(value):
    if type(value) is not str or _OP_ID.fullmatch(value) is None:
        return None
    return value


def _utc_now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')


def _elapsed_ms(elapsed_ms):
    if type(elapsed_ms) not in (int, float):
        return 0
    try:
        whole = int(elapsed_ms)
    except (TypeError, ValueError, OverflowError):
        return 0
    if whole < 0:
        return 0
    return whole


class Observability:
    """In-process counters. `routes` is the closed label set; anything else is `other`."""

    def __init__(self, event_log_path=None, routes=()):
        path = None
        if event_log_path not in (None, ''):
            text = os.fspath(event_log_path)
            if type(text) is str and text:
                path = text
        labels = []
        seen = set()
        for label in routes:
            if type(label) is not str or not label or label in seen:
                continue
            seen.add(label)
            labels.append(label)
        if 'other' not in seen:
            labels.append('other')
        self._route_order = tuple(labels)
        self._route_set = set(self._route_order)
        self._ops = frozenset(OP_ORDER)
        self._commands = {op: {'ACCEPTED': 0, 'REJECTED': 0} for op in (*OP_ORDER, 'other')}
        self._rejections = {}
        self._lookups = {'KNOWN': 0, 'UNKNOWN': 0}
        self._http = {label: {klass: 0 for klass in HTTP_CLASSES} for label in self._route_order}
        self._latency = {label: _empty_histogram() for label in self._route_order}
        self._path = path
        self.max_bytes = EVENT_LOG_MAX_BYTES
        self._written = 0
        self._errors = 0
        self._dropped = 0
        self._bytes = 0
        self._handle = None
        self._started = time.monotonic()
        self._lock = threading.Lock()

    def record_command(self, op, outcome, code):
        """Count one returned receipt. Unknown ops collapse to `other`."""
        if outcome not in OUTCOMES:
            return
        label = op if type(op) is str and op in self._ops else 'other'
        with self._lock:
            self._commands[label][outcome] += 1
            safe = _safe_code(code)
            if safe is not None:
                self._rejections[safe] = self._rejections.get(safe, 0) + 1

    def record_lookup(self, outcome):
        if outcome not in LOOKUP_OUTCOMES:
            return
        with self._lock:
            self._lookups[outcome] += 1

    def record_http(self, route, status, code, operation_id, elapsed_ms):
        """Count one finished HTTP response and append one event-log line.

        ApiError codes are counted here. Receipt errors are counted only by
        `record_command`, so a rejected command (HTTP 200) must pass `code=None`.
        An unwritable event log increments `errors` and does not raise.
        """
        with self._lock:
            label = route if type(route) is str and route in self._route_set else 'other'
            klass = _status_class(status)
            if klass is not None:
                self._http[label][klass] += 1
            self._observe_unlocked(label, elapsed_ms)
            safe = _safe_code(code)
            if safe is not None:
                self._rejections[safe] = self._rejections.get(safe, 0) + 1
            logged_status = status if type(status) is int else 0
            self._write_event_unlocked({
                'time': _utc_now(),
                'route': label,
                'status': logged_status,
                'code': safe,
                'operation_id': _safe_operation_id(operation_id),
            })

    def uptime_seconds(self):
        with self._lock:
            return int(time.monotonic() - self._started)

    def snapshot(self):
        with self._lock:
            return {
                'uptime_seconds': int(time.monotonic() - self._started),
                'counters': {
                    'commands': {
                        op: {'ACCEPTED': counts['ACCEPTED'], 'REJECTED': counts['REJECTED']}
                        for op, counts in self._commands.items()
                    },
                    'rejections': dict(self._rejections),
                    'operation_lookups': dict(self._lookups),
                    'http_requests': {
                        label: dict(classes) for label, classes in self._http.items()
                    },
                    'event_log': {
                        'enabled': self._path is not None,
                        'written': self._written,
                        'errors': self._errors,
                        'dropped': self._dropped,
                        'max_bytes': self.max_bytes if type(self.max_bytes) is int else EVENT_LOG_MAX_BYTES,
                    },
                },
                'latency_ms': {
                    label: dict(hist) for label, hist in self._latency.items()
                },
            }

    def close(self):
        with self._lock:
            self._close_handle_unlocked()

    def _observe_unlocked(self, label, elapsed_ms):
        whole = _elapsed_ms(elapsed_ms)
        hist = self._latency[label]
        hist['count'] += 1
        if whole > hist['max_ms']:
            hist['max_ms'] = whole
        for bound in LATENCY_MS:
            if whole <= bound:
                hist[f'le_{bound}'] += 1
                return
        hist['gt_2500'] += 1

    def _write_event_unlocked(self, record):
        if self._path is None:
            return
        try:
            line = json.dumps(
                record, ensure_ascii=True, separators=(',', ':')).encode('ascii') + b'\n'
        except (TypeError, ValueError):
            self._errors += 1
            return
        limit = self.max_bytes if type(self.max_bytes) is int else EVENT_LOG_MAX_BYTES
        try:
            if self._handle is None:
                # Append. Do not create missing parent directories: an unwritable
                # path must surface as event_log_errors, not as a new directory.
                self._handle = open(self._path, 'ab')
                self._bytes = self._handle.seek(0, 2)
            if self._bytes + len(line) > limit:
                self._dropped += 1
                return
            self._handle.write(line)
            self._handle.flush()
            self._bytes += len(line)
            self._written += 1
        except OSError:
            self._errors += 1
            self._close_handle_unlocked()

    def _close_handle_unlocked(self):
        handle = self._handle
        self._handle = None
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
