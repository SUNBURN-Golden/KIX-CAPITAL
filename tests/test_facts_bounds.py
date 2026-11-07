"""Bounded filesystem and memory inputs for the offline facts verifier."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from capital import facts, overlay
from capital.producer import FixtureViews
from capital.store import canonical_bytes

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / 'tests' / 'vectors' / 'facts'


def copy_clean(directory):
    for path in sorted((CORPUS / 'clean').glob('page-*.json')):
        (Path(directory) / path.name).write_bytes(path.read_bytes())


def write_maximum_export(directory):
    """Synthesize the largest export the adopted producer bounds allow:
    500 journal rows near the 8192-byte request cap plus 2000 foldable overlay
    clock entries near OVERLAY_ENTRY_MAX_BYTES=4096, sealed at page limit 500.
    """
    journal = [{'op': 'offer', 'advance_id': f'sim-pad-{index:04d}',
                'body': {'amount': 1, 'pad': 'j' * 7800}} for index in range(500)]
    entries = [{'overlay_id': f'clock-{index:04d}', 'after_journal_index': 0,
                'sim_day': index + 1, 'kind': 'clock',
                'payload': {'from_sim_day': index, 'to_sim_day': index + 1,
                            'actor': overlay.ACTOR, 'clock_source': overlay.CLOCK_SOURCE,
                            'reason': 'SIMULATED ' + 'o' * 3800}}
               for index in range(2000)]
    cut = facts.make_cut(journal, entries, '0' * 64, facts.sha256_hex(FixtureViews().rows))
    rows = facts.build_rows(journal, entries)
    after = None
    for start in range(0, len(rows), 500):
        page = facts.seal(rows, cut, after, start, 500, len(rows))
        (Path(directory) / f'page-{start // 500:04d}.json').write_bytes(canonical_bytes(page))
        after = page['next_cursor']


class BoundaryTests(unittest.TestCase):
    def test_exact_limits_accept_and_one_over_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            copy_clean(d)
            entries = list(os.scandir(d))
            names = sorted(entry.name for entry in entries)
            sizes = [os.lstat(Path(d) / name).st_size for name in names]
            depth = max(facts._json_depth(facts.loads((Path(d) / name).read_bytes()))
                        for name in names)
            cases = [
                ('max_dir_entries', len(entries), 'INPUT_DIR_ENTRIES'),
                ('max_pages', len(names), 'INPUT_PAGES'),
                ('max_page_bytes', max(sizes), 'INPUT_PAGE_TOO_LARGE:'),
                ('max_total_bytes', sum(sizes), 'INPUT_TOTAL_TOO_LARGE:'),
                ('max_json_depth', depth, 'INPUT_JSON_DEPTH:'),
            ]
            for key, exact, reason in cases:
                with self.subTest(bound=key):
                    self.assertTrue(facts.verify_dir(d, limits={key: exact})['ok'])
                    report = facts.verify_dir(d, limits={key: exact - 1})
                    self.assertFalse(report['ok'])
                    self.assertTrue(report['reason'].startswith(reason), report['reason'])

    def test_excessive_directory_entries_and_unmatched_files(self):
        with tempfile.TemporaryDirectory() as d:
            copy_clean(d)
            for index in range(12):
                (Path(d) / f'filler-{index:02d}.tmp').write_bytes(b'x')
            self.assertTrue(facts.verify_dir(d)['ok'])
            count = len(list(os.scandir(d)))
            self.assertTrue(facts.verify_dir(d, limits={'max_dir_entries': count})['ok'])
            report = facts.verify_dir(d, limits={'max_dir_entries': count - 1})
            self.assertEqual(report['reason'], 'INPUT_DIR_ENTRIES')
            self.assertTrue(facts.verify_dir(d, limits={'max_pages': 7})['ok'])
            self.assertEqual(facts.verify_dir(d, limits={'max_pages': 6})['reason'], 'INPUT_PAGES')

    def test_non_regular_pages_refused_without_following(self):
        def verdict(setup):
            with tempfile.TemporaryDirectory() as d:
                setup(Path(d))
                return facts.verify_dir(d)['reason']
        # A dangling symlink would raise FileNotFoundError if it were ever followed.
        self.assertEqual(
            verdict(lambda d: os.symlink(d / 'missing-target', d / 'page-0000.json')),
            'INPUT_NOT_REGULAR:page-0000.json')
        # A symlink into a real page file is still refused before it is opened.
        def linked(d):
            (d / 'real-page').write_bytes((CORPUS / 'clean/page-0000.json').read_bytes())
            os.symlink(d / 'real-page', d / 'page-0000.json')
        self.assertEqual(verdict(linked), 'INPUT_NOT_REGULAR:page-0000.json')
        self.assertEqual(verdict(lambda d: (d / 'page-0000.json').mkdir()),
                         'INPUT_NOT_REGULAR:page-0000.json')
        if hasattr(os, 'mkfifo'):
            # The lstat refusal is before any open, so a fifo can never block the read.
            self.assertEqual(verdict(lambda d: os.mkfifo(d / 'page-0000.json')),
                             'INPUT_NOT_REGULAR:page-0000.json')
        # Non-matching exotic entries are never opened at all.
        with tempfile.TemporaryDirectory() as d:
            copy_clean(d)
            os.symlink(Path(d) / 'missing-target', Path(d) / 'unmatched-link')
            if hasattr(os, 'mkfifo'):
                os.mkfifo(Path(d) / 'unmatched-fifo')
            self.assertTrue(facts.verify_dir(d)['ok'])

    def test_replacement_vanish_and_rewrite_give_input_changed(self):
        with tempfile.TemporaryDirectory() as d:
            good, other = Path(d) / 'good.json', Path(d) / 'other.json'
            good.write_bytes(b'{"a":1}')
            other.write_bytes(b'{"a":1}')
            # A stale lstat must never match the opened descriptor.
            with self.assertRaises(facts._ChangedError):
                facts._read_regular(other, good.lstat())
            stale = good.lstat()
            good.unlink()
            with self.assertRaises(facts._ChangedError):
                facts._read_regular(good, stale)

        real_open, real_read = os.open, os.read

        def swap_once(target_name, act):
            def wrapper(path, flags, *args):
                if Path(path).name == target_name:
                    act(Path(path))
                return real_open(path, flags, *args)
            return wrapper

        with tempfile.TemporaryDirectory() as d:
            copy_clean(d)
            # A rename replacement between lstat and open changes the inode.
            def replaced(path):
                staging = path.with_name('staging.tmp')
                staging.write_bytes(path.read_bytes() + b' ')
                os.replace(staging, path)
            with patch('capital.facts.os.open', swap_once('page-0003.json', replaced)):
                self.assertEqual(facts.verify_dir(d)['reason'], 'INPUT_CHANGED:page-0003.json')
            copy_clean(d)
            with patch('capital.facts.os.open', swap_once('page-0004.json', Path.unlink)):
                self.assertEqual(facts.verify_dir(d)['reason'], 'INPUT_CHANGED:page-0004.json')
            copy_clean(d)
            # A same-size rewrite observed through a distinct mtime; an in-place
            # rewrite inside the filesystem timestamp granularity is undetectable.
            def rewritten(path):
                path.write_bytes(path.read_bytes().replace(b'0', b'1', 1))
                os.utime(path, ns=(path.stat().st_atime_ns, path.lstat().st_mtime_ns + 1))
            with patch('capital.facts.os.open', swap_once('page-0004.json', rewritten)):
                self.assertEqual(facts.verify_dir(d)['reason'], 'INPUT_CHANGED:page-0004.json')
            copy_clean(d)
            # Growth in the read window is caught by the EOF probe and the post-read fstat.
            fds = {}
            def record_open(path, flags, *args):
                fd = real_open(path, flags, *args)
                fds[Path(path).name] = fd
                return fd
            def grew(fd, n):
                data = real_read(fd, n)
                if fd == fds.get('page-0005.json') and n == 1 and not data:
                    with (Path(d) / 'page-0005.json').open('ab') as handle:
                        handle.write(b' ')
                    data = real_read(fd, n)
                return data
            with patch('capital.facts.os.open', record_open), patch('capital.facts.os.read', grew):
                self.assertEqual(facts.verify_dir(d)['reason'], 'INPUT_CHANGED:page-0005.json')

    def test_deep_json_duplicate_keys_and_truncated_pages_return_reasons(self):
        depth = facts.INPUT_LIMITS['max_json_depth'] + 1
        with tempfile.TemporaryDirectory() as d:
            page = Path(d) / 'page-0000.json'
            # Nesting that parses but exceeds the depth budget.
            page.write_bytes(b'{"k":' * depth + b'1' + b'}' * depth)
            self.assertEqual(facts.verify_dir(d)['reason'], 'INPUT_JSON_DEPTH:page-0000.json')
            # Nesting beyond the interpreter recursion limit stays a clean refusal.
            page.write_bytes(b'[' * 20000 + b'1' + b']' * 20000)
            self.assertEqual(facts.verify_dir(d)['reason'], 'UNREADABLE:page-0000.json')
            page.write_bytes(b'{"a":1,"a":2}')
            self.assertEqual(facts.verify_dir(d)['reason'], 'UNREADABLE:page-0000.json')
            clean = (CORPUS / 'clean/page-0000.json').read_bytes()
            page.write_bytes(clean[:-1])
            self.assertEqual(facts.verify_dir(d)['reason'], 'UNREADABLE:page-0000.json')
            # A document exactly at the depth budget passes the depth check and
            # reaches the canonical-encoding check; one level over refuses.
            raw = b'{"k":' * (depth - 1) + b'1' + b'}' * (depth - 1) + b' '
            page.write_bytes(raw)
            report = facts.verify_dir(d, limits={'max_json_depth': depth - 1})
            self.assertEqual(report['reason'], 'NONCANONICAL_ENCODING:page-0000.json')
            report = facts.verify_dir(d, limits={'max_json_depth': depth - 2})
            self.assertEqual(report['reason'], 'INPUT_JSON_DEPTH:page-0000.json')

    def test_lexicographic_page_order_is_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ('page-2.json', 'page-10.json'):
                (Path(d) / name).write_bytes(b'{bad')
            self.assertEqual(facts.verify_dir(d)['reason'], 'UNREADABLE:page-10.json')

    def test_generated_maximum_export_fits_the_default_bounds(self):
        with tempfile.TemporaryDirectory() as d:
            write_maximum_export(d)
            sizes = [path.stat().st_size for path in Path(d).glob('page-*.json')]
            self.assertLessEqual(max(sizes), facts.INPUT_LIMITS['max_page_bytes'])
            self.assertLessEqual(sum(sizes), facts.INPUT_LIMITS['max_total_bytes'])
            self.assertLessEqual(len(sizes), facts.INPUT_LIMITS['max_pages'])
            report = facts.verify_dir(d)
            # Every page was read under the defaults; only the fake journal op
            # fails, and that is a semantic reason, not an input budget.
            self.assertEqual(report['pages'], 5)
            self.assertEqual(report['reason'], 'JOURNAL_REPLAY_FAILED')
        # A real paginate(limit=500) page stays far below the page budget.
        from scripts.facts_vectors import seed
        service = seed()
        journal = service.machine.export_journal()
        page = facts.paginate(journal, [], service.machine.state_digest(),
                              facts.sha256_hex(service.fixtures.rows), limit=500)
        raw = canonical_bytes(page)
        self.assertLess(len(raw), facts.INPUT_LIMITS['max_page_bytes'])
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'page-0000.json').write_bytes(raw)
            self.assertTrue(facts.verify_dir(d)['ok'])

    def test_no_partial_success_no_writes_and_no_leaked_contents(self):
        sentinel = b'UNIQUE_SENTINEL_9f3c_DO_NOT_LEAK'
        with tempfile.TemporaryDirectory() as d:
            copy_clean(d)
            page = Path(d) / 'page-0007.json'
            page.write_bytes(b'{"leak":"' + sentinel + b'"} ')
            before = {p.name: p.read_bytes() for p in Path(d).iterdir()}
            report = facts.verify_dir(d)
            self.assertFalse(report['ok'])
            self.assertEqual(report['reason'], 'NONCANONICAL_ENCODING:page-0007.json')
            self.assertNotIn(sentinel, json.dumps(report).encode())
            self.assertEqual(before, {p.name: p.read_bytes() for p in Path(d).iterdir()})

    def test_cli_exit_codes_reasons_and_no_leaked_contents(self):
        sentinel = b'UNIQUE_SENTINEL_9f3c_DO_NOT_LEAK'
        proc = subprocess.run([sys.executable, '-m', 'capital.verify', '--facts',
                               str(CORPUS / 'clean')], capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(json.loads(proc.stdout)['ok'])
        with tempfile.TemporaryDirectory() as d:
            page = Path(d) / 'page-0000.json'
            page.write_bytes(b'{"leak":"' + sentinel + b'"} ')
            before = page.read_bytes()
            proc = subprocess.run([sys.executable, '-m', 'capital.verify', '--facts', d],
                                  capture_output=True)
            self.assertEqual(proc.returncode, 1)
            report = json.loads(proc.stdout)
            self.assertFalse(report['ok'])
            self.assertEqual(report['reason'], 'NONCANONICAL_ENCODING:page-0000.json')
            self.assertNotIn(sentinel, proc.stdout + proc.stderr)
            self.assertEqual(page.read_bytes(), before)
        with tempfile.TemporaryDirectory() as d:
            os.symlink(Path(d) / 'missing-target', Path(d) / 'page-0000.json')
            proc = subprocess.run([sys.executable, '-m', 'capital.verify', '--facts', d],
                                  capture_output=True)
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(json.loads(proc.stdout)['reason'],
                             'INPUT_NOT_REGULAR:page-0000.json')


if __name__ == '__main__':
    unittest.main()
