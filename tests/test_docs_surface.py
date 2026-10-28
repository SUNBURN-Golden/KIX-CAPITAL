"""scripts/docs_surface.py: each drift class fails on a mutated temporary doc copy."""
import contextlib
import importlib.util
import io
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / 'docs' / 'INTEGRATION.md'
README = ROOT / 'README.md'
HANDBOOK = ROOT / 'docs' / 'OPERATOR_HANDBOOK_KO.md'
ACCEPTANCE = ROOT / 'docs' / 'ACCEPTANCE_KO.md'
VECTORS = ROOT / 'tests' / 'vectors'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


docs_surface = _load('docs_surface', ROOT / 'scripts' / 'docs_surface.py')


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = docs_surface.main(argv)
    return code, out.getvalue(), err.getvalue()


def _mutated_copy(path, mutate):
    """Write a temp copy of `path` with `mutate` applied to its text."""
    tmp = tempfile.TemporaryDirectory()
    copy = Path(tmp.name) / path.name
    copy.write_text(mutate(path.read_text(encoding='utf-8')), encoding='utf-8')
    return tmp, copy


def _drop_line(text, marker):
    lines = [line for line in text.splitlines(keepends=True) if marker not in line]
    assert len(lines) != len(text.splitlines(keepends=True)), marker
    return ''.join(lines)


def _rename_stage(text):
    lines = text.splitlines(keepends=True)
    index = next(i for i, line in enumerate(lines) if 'stage id' in line)
    assert '`unit`' in lines[index]
    lines[index] = lines[index].replace('`unit`', '`units`', 1)
    return ''.join(lines)


class CurrentTreeTests(unittest.TestCase):
    def test_current_tree_has_zero_findings(self):
        code, out, err = _run(['--check'])
        self.assertEqual(code, 0, err)
        self.assertRegex(out, r'docs surface ok: \d+ routes, \d+ artifacts, \d+ stages')

    def test_route_registry_covers_exactly_the_live_routes(self):
        routes = docs_surface.live_routes()
        self.assertEqual(set(docs_surface.ROUTE_NEEDLES), set(routes))
        self.assertIn(('GET', '/api/terms'), routes)
        self.assertIn(('POST', '/api/agent/execute'), routes)


class JourneyDocTests(unittest.TestCase):
    def test_names_paths_and_check_command_are_required_in_both_docs(self):
        needles = {docs_surface.JOURNEY_COMMAND}
        for values in docs_surface.JOURNEY_NEEDLES.values():
            needles.update(values)
        for source, option in ((README, '--readme'), (ACCEPTANCE, '--acceptance')):
            for needle in sorted(needles):
                with self.subTest(source=source.name, needle=needle):
                    tmp, copy = _mutated_copy(source, lambda text: text.replace(needle, 'REMOVED'))
                    try:
                        code, _, err = _run(['--check', option, str(copy)])
                        self.assertEqual(code, 1)
                        self.assertIn('journey needle', err)
                    finally:
                        tmp.cleanup()

    def test_missing_new_golden_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings, _ = docs_surface.find_drift(golden_dir=Path(tmp))
        for artifact in docs_surface.JOURNEY_NEEDLES:
            self.assertTrue(any(artifact in finding for finding in findings))


class MutatedDocTests(unittest.TestCase):
    def test_missing_route_bullet_fails_naming_the_needle(self):
        tmp, copy = _mutated_copy(INTEGRATION, lambda text: _drop_line(text, '- `GET /api/statement`:'))
        self.addCleanup(tmp.cleanup)
        code, _out, err = _run(['--check', '--integration', str(copy)])
        self.assertEqual(code, 1)
        self.assertIn('GET /api/statement', err)
        self.assertIn('- `GET /api/statement`:', err)

    def test_permissions_route_requires_hand_maintained_prose(self):
        self.assertIn(('GET', '/api/permissions'), docs_surface.live_routes())
        tmp, copy = _mutated_copy(
            INTEGRATION, lambda text: _drop_line(text, '- `GET /api/permissions`:'))
        self.addCleanup(tmp.cleanup)
        self.assertIn('`/api/permissions`', copy.read_text(encoding='utf-8'))
        code, _out, err = _run(['--check', '--integration', str(copy)])
        self.assertEqual(code, 1)
        self.assertIn('GET /api/permissions', err)

    def test_missing_portfolio_snapshot_bullet_fails(self):
        tmp, copy = _mutated_copy(INTEGRATION, lambda text: _drop_line(text, '- `GET /api/portfolio/snapshot`:'))
        self.addCleanup(tmp.cleanup)
        code, _out, err = _run(['--check', '--integration', str(copy)])
        self.assertEqual(code, 1)
        self.assertIn('GET /api/portfolio/snapshot', err)

    def test_agent_routes_in_generated_block_do_not_count(self):
        # The agent POST names also sit in the generated auth-matrix table; only
        # the prose sentence is the hand enumeration, so deleting it must fail.
        tmp, copy = _mutated_copy(
            INTEGRATION, lambda text: _drop_line(text, '`POST /api/agent/query_grant` maps to'))
        self.addCleanup(tmp.cleanup)
        self.assertIn('`POST /api/agent/query_grant`', INTEGRATION.read_text(encoding='utf-8'))
        code, _out, err = _run(['--check', '--integration', str(copy)])
        self.assertEqual(code, 1)
        self.assertIn('POST /api/agent/query_grant', err)

    def test_missing_readme_bullet_fails_naming_the_artifact(self):
        tmp, copy = _mutated_copy(
            README, lambda text: _drop_line(text, 'tests/vectors/finance_vectors.json'))
        self.addCleanup(tmp.cleanup)
        code, _out, err = _run(['--check', '--readme', str(copy)])
        self.assertEqual(code, 1)
        self.assertIn('tests/vectors/finance_vectors.json', err)
        # The --check command is still named by the verification block.
        self.assertNotIn('scripts/finance_vectors.py --check', err)

    def test_lifecycle_claim_readme_needles_are_required(self):
        for needle in docs_surface.CLAIM_NEEDLES['tests/lifecycle_claims.json']:
            with self.subTest(needle=needle):
                tmp, copy = _mutated_copy(README, lambda text: text.replace(needle, 'REMOVED'))
                self.addCleanup(tmp.cleanup)
                code, _out, err = _run(['--check', '--readme', str(copy)])
                self.assertEqual(code, 1)
                self.assertIn(needle, err)

    def test_unexpected_vector_file_fails_naming_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            vectors = Path(tmp) / 'vectors'
            shutil.copytree(VECTORS, vectors)
            (vectors / 'extra.json').write_text('{}', encoding='utf-8')
            code, _out, err = _run(['--check', '--vectors', str(vectors)])
        self.assertEqual(code, 1)
        self.assertIn('extra.json', err)

    def test_renamed_stage_fails_naming_the_doc(self):
        for flag, doc in (('--handbook', HANDBOOK), ('--acceptance', ACCEPTANCE)):
            tmp, copy = _mutated_copy(doc, _rename_stage)
            self.addCleanup(tmp.cleanup)
            with self.subTest(doc=doc.name):
                code, _out, err = _run(['--check', flag, str(copy)])
                self.assertEqual(code, 1, err)
                self.assertIn('units', err)
                self.assertIn(doc.name, err)


if __name__ == '__main__':
    unittest.main()
