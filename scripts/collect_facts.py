#!/usr/bin/env python3
"""Collect bounded SIMULATED loopback facts; publish completion after offline replay.

No retries, resume, commands, source authentication or workspace import.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import math
import os
from pathlib import Path
import re
import socket
import sys
import time
from urllib.parse import urlencode

# A read-only collector must not create caches in the checkout it imports.
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capital import facts
from capital.store import canonical_bytes
from capital.strict_json import loads


class CollectionError(ValueError):
    """Static diagnostic only: never include response bodies, URLs or tokens."""


def endpoint_port(value):
    match = re.fullmatch(r'http://127\.0\.0\.1:([1-9][0-9]{0,4})/?', value)
    if match is None or int(match[1]) > 65535:
        raise argparse.ArgumentTypeError('endpoint must be http://127.0.0.1:PORT')
    return int(match[1])


def positive_int(value):
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError('expected positive integer') from None
    if number < 1:
        raise argparse.ArgumentTypeError('expected positive integer')
    return number


def positive_timeout(value):
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError('expected finite positive timeout') from None
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError('expected finite positive timeout')
    return number


class DeadlineSocket(socket.socket):
    """SocketIO calls recv_into even while http.client parses slow headers."""

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        self.settimeout(remaining)

    def recv_into(self, *args):
        self.remaining()
        return super().recv_into(*args)


class DeadlineConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = DeadlineSocket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.deadline = self.deadline
        self.sock.remaining()
        self.sock.connect(('127.0.0.1', self.port))


class Transport:
    def __init__(self, args):
        self.args = args
        self.received = 0

    def get(self, path, token=None):
        conn = DeadlineConnection('127.0.0.1', self.args.endpoint, timeout=self.args.timeout)
        conn.deadline = time.monotonic() + self.args.timeout
        try:
            headers = {'Host': f'127.0.0.1:{self.args.endpoint}', 'Accept': 'application/json',
                       'Accept-Encoding': 'identity', 'Connection': 'close'}
            if token is not None:
                headers['X-Capital-Token'] = token
            conn.request('GET', path, headers=headers)
            with conn.getresponse() as response:
                lengths = response.headers.get_all('Content-Length', [])
                if (len(lengths) != 1 or re.fullmatch(r'[0-9]{1,20}', lengths[0]) is None
                        or response.headers.get_all('Transfer-Encoding')
                        or response.headers.get_all('Content-Encoding')):
                    raise CollectionError('RESPONSE_FRAMING')
                length = int(lengths[0])
                if length > self.args.max_response_bytes:
                    raise CollectionError('RESPONSE_BYTE_BOUND')
                if length > self.args.max_total_bytes - self.received:
                    raise CollectionError('TOTAL_BYTE_BOUND')
                # Connection: close is required; probe one byte beyond the declared
                # length to refuse extra body bytes as well as truncation.
                body = response.fp.read(length + 1)
                self.received += len(body)
                if len(body) != length:
                    raise CollectionError('RESPONSE_TRUNCATED')
                if time.monotonic() > conn.deadline:
                    raise CollectionError('RESPONSE_TIMEOUT')
                if 300 <= response.status < 400:
                    raise CollectionError('REDIRECT_REFUSED')
                if response.status != 200:
                    # The status suffices; untrusted error messages can contain tokens.
                    raise CollectionError(f'HTTP_{response.status}')
                types = response.headers.get_all('Content-Type', [])
                if len(types) != 1 or types[0].lower() not in (
                        'application/json', 'application/json; charset=utf-8'):
                    raise CollectionError('RESPONSE_CONTENT_TYPE')
                return body
        except (TimeoutError, socket.timeout):
            raise CollectionError('RESPONSE_TIMEOUT') from None
        except (OSError, http.client.HTTPException, OverflowError):
            raise CollectionError('TRANSPORT_FAILED') from None
        finally:
            conn.close()


def contains_token(value, token):
    if type(value) is str:
        return token in value
    if type(value) is dict:
        return any(contains_token(k, token) or contains_token(v, token) for k, v in value.items())
    if type(value) is list:
        return any(contains_token(v, token) for v in value)
    return False


class PageSequence:
    """Validate the wire page before persisting or following its cursor.

    Replay and semantic source validation remain the existing verifier's job.
    """

    def __init__(self, limit):
        self.limit, self.start, self.after = limit, 0, None
        self.cut, self.total, self.chain = None, None, None

    def accept(self, raw, token):
        try:
            page = loads(raw)
            if contains_token(page, token):
                raise CollectionError('TOKEN_IN_PAGE')
            if type(page) is not dict or set(page) != facts.PAGE_KEYS or raw != canonical_bytes(page):
                raise ValueError
            if page['format'] != facts.PAGE_FORMAT or page['schema_id'] != facts.SCHEMA_ID:
                raise ValueError
            if (canonical_bytes(page['schema']) != canonical_bytes(facts.schema())
                    or page['schema_sha256'] != facts.sha256_hex(facts.schema())
                    or any(canonical_bytes(page[k]) != canonical_bytes(v) for k, v in facts.LABELS.items())):
                raise ValueError
            cut = page['cut']
            keys = {'state_digest', 'journal_length', 'fixtures_digest', 'cut_id'}
            if type(cut) is not dict or set(cut) not in (keys, keys | {'overlay_state_digest', 'overlay_entry_count'}):
                raise ValueError
            if (not facts._uint(cut['journal_length'])
                    or any(type(cut[k]) is not str or facts.HEX.fullmatch(cut[k]) is None
                           for k in ('state_digest', 'fixtures_digest', 'cut_id'))
                    or cut['cut_id'] != facts.cut_digest(cut)):
                raise ValueError
            if 'overlay_entry_count' in cut and (
                    not facts._uint(cut['overlay_entry_count']) or cut['overlay_entry_count'] == 0
                    or type(cut['overlay_state_digest']) is not str
                    or facts.HEX.fullmatch(cut['overlay_state_digest']) is None):
                raise ValueError
            if self.cut is None:
                self.cut, self.total, self.chain = cut, page['row_count_total'], facts.genesis(cut)
            if (cut != self.cut or not facts._uint(page['row_count_total'])
                    or page['row_count_total'] != self.total or not facts._uint(page['start_seq'])
                    or page['start_seq'] != self.start or page['after'] != self.after
                    or type(page['limit']) is not int or page['limit'] != self.limit
                    or type(page['rows']) is not list or page['chain_before'] != self.chain
                    or len(page['rows']) != min(self.limit, self.total - self.start)
                    or (not page['rows'] and (self.start != 0 or self.total != 0))):
                raise ValueError
            for index, row in enumerate(page['rows']):
                facts.validate_row(row)
                if row['seq'] != self.start + index or row['row_sha256'] != facts.row_digest(row):
                    raise ValueError
                self.chain = facts.chain_step(self.chain, row)
            end = self.start + len(page['rows'])
            expected = facts.cursor(end, cut) if end < self.total else None
            if (page['chain_after'] != self.chain or page['next_cursor'] != expected
                    or page['page_digest'] != facts.page_digest(page)):
                raise ValueError
            self.start, self.after = end, expected
            return page
        except CollectionError:
            raise
        except (ValueError, KeyError, TypeError, UnicodeError, RecursionError, OverflowError):
            raise CollectionError('PAGE_INVALID') from None


def output_path(value):
    path = Path(value).absolute()
    # Resolve ancestors, but never follow an existing output symlink.
    if os.path.lexists(path):
        raise CollectionError('OUTPUT_EXISTS')
    parent = path.parent.resolve(strict=True)
    resolved = parent / path.name
    if resolved == ROOT or ROOT in resolved.parents:
        raise CollectionError('OUTPUT_IN_CHECKOUT')
    for ancestor in (parent, *parent.parents):
        if any(os.path.lexists(ancestor / name) for name in ('workspace.json', 'workspace.json.lock')):
            raise CollectionError('OUTPUT_IN_WORKSPACE')
    return resolved


def write_private(directory_fd, name, raw):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory_fd)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def collect(args):
    out = output_path(args.out)
    out.mkdir(mode=0o700)  # Exclusive; parent must already exist.
    directory_fd = os.open(out, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        transport = Transport(args)
        try:
            state = loads(transport.get('/api/state'))
            instance, token = state['instance_id'], state['local_token']
            if any(type(v) is not str or re.fullmatch(r'[A-Za-z0-9_-]{1,256}', v) is None
                   for v in (instance, token)):
                raise ValueError
            del state
        except (ValueError, KeyError, TypeError, UnicodeError, RecursionError) as exc:
            if isinstance(exc, CollectionError):
                raise
            raise CollectionError('BOOTSTRAP_INVALID') from None
        sequence, saved, page_bytes = PageSequence(args.limit), [], 0
        while True:
            if len(saved) >= args.max_pages or len(saved) > facts.UINT_MAX:
                raise CollectionError('PAGE_COUNT_BOUND')
            query = {'instance_id': instance, 'limit': args.limit}
            if sequence.after is not None:
                query['after'] = sequence.after
            raw = transport.get('/api/export/facts?' + urlencode(query), token)
            page = sequence.accept(raw, token)
            name = f'page-{len(saved):08d}.json'
            write_private(directory_fd, name, raw)
            saved.append({'name': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
            page_bytes += len(raw)
            if page['next_cursor'] is None:
                break
        verification = facts.verify_dir(out)
        if verification['ok'] is not True:
            raise CollectionError('OFFLINE_VERIFICATION_FAILED')
        marker = {'format': 'KIX_CAPITAL_FACTS_COLLECTION_V1', 'status': 'VERIFIED_COMPLETE',
                  'label': 'SIMULATED', 'source_cut': 'NOT_BOUND', 'authentication': 'NOT_BOUND',
                  'stage7_authenticated_export': False, 'funds_executed': False,
                  'pages': saved, 'page_bytes_total': page_bytes, 'verification': verification}
        write_private(directory_fd, '.COMPLETE.tmp', canonical_bytes(marker))
        # Atomic no-replace publication: this successful link is the commit point.
        os.link('.COMPLETE.tmp', 'COMPLETE.json', src_dir_fd=directory_fd, dst_dir_fd=directory_fd,
                follow_symlinks=False)
        try:
            os.unlink('.COMPLETE.tmp', dir_fd=directory_fd)
        except OSError:
            pass  # Publication already succeeded; a leftover temporary link is harmless.
    finally:
        os.close(directory_fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', required=True, type=endpoint_port)
    parser.add_argument('--out', required=True)
    parser.add_argument('--limit', type=positive_int, default=100)
    parser.add_argument('--max-pages', type=positive_int, default=1000)
    parser.add_argument('--max-response-bytes', type=positive_int, default=4194304)
    parser.add_argument('--max-total-bytes', type=positive_int, default=67108864)
    parser.add_argument('--timeout', type=positive_timeout, default=10)
    args = parser.parse_args(argv)
    if args.limit > facts.LIMIT_MAX:
        parser.error('limit must be in 1..500')
    try:
        collect(args)
    except CollectionError as exc:
        print('collection failed: ' + str(exc), file=sys.stderr)
        return 1
    except (OSError, ValueError, RecursionError, OverflowError):
        print('collection failed: STORAGE_OR_VERIFICATION_FAILED', file=sys.stderr)
        return 1
    print('SIMULATED VERIFIED_COMPLETE; authentication NOT_BOUND')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
