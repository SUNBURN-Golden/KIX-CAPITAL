"""Pinned byte corruption and fully resealed semantic attacks, verified offline."""
import copy
import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from capital import facts, overlay, slices
from capital.store import canonical_bytes
from scripts import facts_vectors as vectors
from scripts.seed_overlay_slices import register, open_slice

ROOT=Path(__file__).resolve().parents[1]
CORPUS=ROOT/'tests/vectors/facts'
# Independent pinned expectations: the generator's index is not the oracle.
REASONS={
    'clean':None,'clean-empty-overlay':None,
    'corrupt/entry-byte':'PAGE_DIGEST_MISMATCH',
    'corrupt/whitespace':'NONCANONICAL_ENCODING:page-0000.json',
    'corrupt/truncated':'UNREADABLE:page-0000.json',
    'corrupt/missing-final-page':'MISSING_FINAL_PAGE',
    'semantic/row-amount':'ROW_MISMATCH:0',
    'semantic/row-reorder':'ROW_MISMATCH:20',
    'semantic/row-hash':'ROW_HASH_MISMATCH',
    'semantic/chain-before':'CHAIN_BROKEN',
    'semantic/cursor-skip':'CURSOR_MISMATCH',
    'semantic/cut-differs-one-page':'CUT_MISMATCH',
    'semantic/cut-count':'CUT_COUNT_MISMATCH',
    'semantic/state-digest':'STATE_DIGEST_MISMATCH',
    'semantic/entry-amount':'STATE_DIGEST_MISMATCH',
    'semantic/overlay-digest':'OVERLAY_FOLD_MISMATCH',
    'semantic/anchor-principal':'OVERLAY_LINK_MISMATCH',
    'semantic/label':'LABEL_MISMATCH',
    'semantic/fixtures-digest':'FIXTURES_MISMATCH',
}


def write_pages(directory,pages):
    for index,page in enumerate(pages):
        (Path(directory)/f'page-{index:04d}.json').write_bytes(canonical_bytes(page))


class VectorTests(unittest.TestCase):
    def test_corpus_reasons_and_cli_exit_codes(self):
        self.assertEqual(json.loads((CORPUS/'index.json').read_bytes())['cases'],REASONS)
        for name,reason in REASONS.items():
            with self.subTest(case=name):
                report=facts.verify_dir(CORPUS/name)
                self.assertEqual(report['reason'],reason)
                self.assertEqual(report['ok'],reason is None)
                self.assertEqual(report['authentication'],'NOT_BOUND')
                self.assertIs(report['stage7_authenticated_export'],False)
                proc=subprocess.run([sys.executable,'-m','capital.verify','--facts',str(CORPUS/name)],
                                    capture_output=True,check=False)
                self.assertEqual(proc.returncode,0 if reason is None else 1,proc.stderr)
                self.assertEqual(json.loads(proc.stdout),report)

    def test_schema_and_byte_pins_and_mutated_copy(self):
        self.assertEqual((CORPUS/'schema.json').read_bytes(),canonical_bytes(facts.schema()))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(vectors.main(['--check']),0)
        with tempfile.TemporaryDirectory() as d:
            shutil.copytree(CORPUS,Path(d)/'facts')
            target=Path(d)/'facts/clean/page-0000.json'
            target.write_bytes(target.read_bytes()+b' ')
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(vectors.main(['--check','--dir',str(Path(d)/'facts')]),1)
            self.assertFalse(facts.verify_dir(target.parent)['ok'])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(vectors.main(['--write','--dir',str(Path(d)/'facts')]),0)
                self.assertEqual(vectors.main(['--check','--dir',str(Path(d)/'facts')]),0)

    def test_semantic_attacks_pass_their_enclosing_hashes(self):
        for name in REASONS:
            if not name.startswith('semantic/'):
                continue
            for path in (CORPUS/name).glob('page-*.json'):
                page=json.loads(path.read_bytes())
                self.assertEqual(page['page_digest'],facts.page_digest(page),name)
                if name != 'semantic/row-hash':
                    for row in page['rows']:
                        self.assertEqual(row['row_sha256'],facts.row_digest(row),name)

    def test_malformed_shapes_and_positions_fail_without_tracebacks(self):
        clean=[json.loads(p.read_bytes()) for p in sorted((CORPUS/'clean').glob('page-*.json'))]
        mutations=[
            (lambda p:p[0].update(unexpected=1),'PAGE_SHAPE'),
            (lambda p:p[0].update(rows={}), 'PAGE_SHAPE'),
            (lambda p:p[0].update(limit=True), 'PAGE_SHAPE'),
            (lambda p:p[0].update(schema={}), 'SCHEMA_MISMATCH'),
            (lambda p:p[0]['rows'][0].update(duplicate=True),'ROW_TYPE'),
            (lambda p:p[0]['rows'][0].update(seq=100000000),'ROW_TYPE'),
            (lambda p:p[0]['rows'][0].update(seq=1),'CURSOR_MISMATCH'),
            (lambda p:p[0]['cut'].pop('cut_id'),'CUT_MISMATCH'),
            (lambda p:p[1].update(after=None),'CURSOR_MISMATCH'),
            (lambda p:p[0].update(next_cursor=None),'CURSOR_MISMATCH'),
        ]
        for mutate,reason in mutations:
            pages=copy.deepcopy(clean)
            mutate(pages)
            # Reseal all wrappers including chains, preserving the intended flaw.
            for page in pages:
                if type(page['rows']) is list:
                    for row in page['rows']:
                        row['row_sha256']=facts.row_digest(row)
            if all(type(p['rows']) is list for p in pages) and 'cut_id' in pages[0]['cut']:
                chain=facts.genesis(pages[0]['cut'])
                for page in pages:
                    page['chain_before']=chain
                    for row in page['rows']:
                        chain=facts.chain_step(chain,row)
                    page['chain_after']=chain
            for page in pages:
                page['page_digest']=facts.page_digest(page)
            with tempfile.TemporaryDirectory() as d:
                write_pages(d,pages)
                self.assertEqual(facts.verify_dir(d)['reason'],reason)
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(facts.verify_dir(d)['reason'],'NO_PAGES')
            s=vectors.seed()
            empty=facts.paginate([],[],facts.CreditMachine(facts.FixtureViews()).state_digest(),facts.sha256_hex(s.fixtures.rows))
            write_pages(d,[empty])
            self.assertTrue(facts.verify_dir(d)['ok'])
            (Path(d)/'page-0000.json').write_bytes(b'{"a":1,"a":2}')
            self.assertEqual(facts.verify_dir(d)['reason'],'UNREADABLE:page-0000.json')

    def test_slice_link_validator_and_resealed_slice_witness(self):
        with patch('capital.facts.slices.validate_links',side_effect=overlay.OverlayError('test link')) as validator:
            self.assertEqual(facts.verify_dir(CORPUS/'clean')['reason'],'OVERLAY_LINK_MISMATCH')
            validator.assert_called_once()
        s=vectors.seed()
        register(s,'facts-slice',1000,claim='sim-committed')
        open_slice(s,'facts-slice')
        journal=s.machine.export_journal()
        entries=copy.deepcopy(s.overlay_entries)
        entry=entries[-1]
        entry['payload']['witness']['advances']={}
        entry['payload']=slices.plan_payload(overlay.fold(entries[:-1]),entry)
        # Fold and all digests accept this witness; the F04 link must reject it.
        overlay.fold(entries,len(journal))
        with self.assertRaises(overlay.OverlayError):
            slices.validate_links(entries,journal,s.fixtures.rows)
        cut=facts.make_cut(journal,entries,s.machine.state_digest(),facts.sha256_hex(s.fixtures.rows))
        pages=vectors.pages_for(facts.build_rows(journal,entries),cut)
        with tempfile.TemporaryDirectory() as d:
            write_pages(d,pages)
            self.assertEqual(facts.verify_dir(d)['reason'],'OVERLAY_LINK_MISMATCH')

    def test_cli_modes_are_exclusive(self):
        for extra in (['--workspace','.'],['--key-file','not-read'],['some-manifest.json']):
            proc=subprocess.run([sys.executable,'-m','capital.verify','--facts',str(CORPUS/'clean'),*extra],capture_output=True)
            self.assertEqual(proc.returncode,2)
