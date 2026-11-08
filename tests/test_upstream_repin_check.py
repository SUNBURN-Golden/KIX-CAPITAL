"""Synthetic local snapshots and evidence; no real upstream adoption or re-pin."""
import contextlib
import copy
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('upstream_repin_checker', ROOT / 'scripts/upstream_repin_check.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


class RepinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.baseline = Path(cls.temp.name) / 'baseline'
        cls.baseline.mkdir()
        for path in checker.source_inventory(ROOT):
            target = cls.baseline / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, target)
        cls.policy = checker.load_policy(cls.baseline)
        cls.base_report = checker.inspect_snapshot(cls.baseline)
        assert cls.base_report['findings'] == [], cls.base_report['findings']

    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.candidate = Path(self.work.name) / 'candidate'
        shutil.copytree(self.baseline, self.candidate)
        self.logs = Path(self.work.name) / 'evidence'
        self.logs.mkdir()

    def inspect(self):
        return checker.inspect_snapshot(self.candidate)

    def move(self, surface):
        pin = checker.pins(self.policy)[surface]
        new = ('a' if surface == 'vendor_pin' else 'b') * 40
        for table_path in pin['bound_tables']:
            path = self.candidate / table_path
            table = checker.read_json(path)
            table['pinned_sha'] = new
            sources = {}
            for claim in table['claims']:
                claim['pinned_sha'] = new
                sources.setdefault(claim['source_doc'], []).extend((claim['section'], claim['needle']))
            write_json(path, table)
            for relative, parts in sources.items():
                source = self.candidate / 'source_material' / surface / relative
                source.parent.mkdir(parents=True, exist_ok=True)
                with source.open('a') as stream:
                    stream.write('\nSIMULATED / READ_ONLY_FIXTURE\n' + '\n'.join(parts))
        implementation = 'capital/upstream_claims.py' if surface == 'vendor_pin' else 'capital/agent_claims.py'
        path = self.candidate / implementation
        path.write_text(path.read_text().replace("PINNED_SHA = '" + pin['sha'] + "'", "PINNED_SHA = '" + new + "'"))
        if 'manifest' in pin:
            path = self.candidate / pin['manifest']
            manifest = checker.read_json(path)
            manifest['commit'] = new
            write_json(path, manifest)
            for relative in manifest['files']:
                source = self.candidate / 'source_material' / surface / manifest['source_prefix'] / relative
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(self.candidate / 'capital/vendor' / relative, source)
        return new

    def evidence(self, surfaces=()):
        proposed = {surface: self.move(surface) for surface in surfaces}
        cand = checker.inspect_snapshot(self.candidate, self.policy, proposed)
        self.assertEqual(cand['findings'], [])
        evidence = {'schema': checker.SCHEMA, 'baseline_id': 'SIMULATED-baseline',
                    'candidate_id': 'SIMULATED-candidate', 'baseline_digest': self.base_report['content_digest'],
                    'candidate_digest': cand['content_digest'],
                    'policy_digests': {'baseline': self.policy['digest'], 'candidate': checker.load_policy(self.candidate)['digest']},
                    'changes': []}
        for surface in surfaces:
            required = checker.required_evidence(self.policy, surface, self.baseline, self.candidate)
            change = {'surface': surface, 'old_sha': checker.pins(self.policy)[surface]['sha'],
                      'new_sha': proposed[surface], 'trigger': self.policy['values']['repin_trigger_procedure']['triggers'][0],
                      **{key: 'SIMULATED fixture; not real authority or execution' for key in
                         ('acceptance_basis', 'decision_maker', 'consumer_impact', 'compatibility_authority_analysis', 'rollback')},
                      'artifacts': [], 'validation': []}
            for path, role in required['artifacts'].items():
                artifact = {'path': path, 'role': role,
                    'digest': checker.file_digest(self.candidate, path), 'method': 'generator',
                    'procedure': 'SIMULATED fixture generation; no real regeneration claimed',
                    'result': 'SOURCE_INSPECTED' if role == 'source' else 'UNCHANGED_REGENERATED'}
                if role in ('claim-table-and-embedded-vectors', 'producer-and-embedded-vectors', 'producer-vectors'):
                    artifact['method'] = 'manual'
                    stem = Path(path).stem.removeprefix('test_').removesuffix('_check').removesuffix('_claims')
                    claims = checker.read_json(self.candidate / f'tests/{stem}_claims.json')['claims']
                    artifact['claim_evidence'] = [{'claim_id': row['id'],
                        'source_path': 'source_material/' + surface + '/' + row['source_doc'],
                        'source_digest': checker.file_digest(self.candidate, 'source_material/' + surface + '/' + row['source_doc']),
                        'explanation': 'SIMULATED claim reconstruction'} for row in claims]
                    artifact['independent_expectations'] = [{'claim_id': row['id'], 'expected': row['expected'],
                        'rationale': 'SIMULATED independent expectation'} for row in claims]
                change['artifacts'].append(artifact)
            for key, argv in required['validation'].items():
                log = self.logs / (surface + '-' + key.replace(':', '-') + '.log')
                text = 'SIMULATED fixture PASS; no real command execution claimed\n'
                if key.startswith('citation:'):
                    count = len(checker.read_json(self.candidate / ('tests/' + key.split(':')[1] + '_claims.json'))['claims'])
                    text += f'CLAIM_DRIFT verified={count} total={count}\n'
                log.write_text(text)
                change['validation'].append({'check_id': key, 'argv': argv,
                    'candidate_id': evidence['candidate_id'], 'candidate_digest': evidence['candidate_digest'],
                    'exit_code': 0, 'result': 'PASS',
                    'logs': [{'path': log.name, 'digest': checker.digest(log.read_bytes())}]})
            evidence['changes'].append(change)
        return evidence

    def compare(self, evidence):
        return checker.compare_snapshots(self.baseline, self.candidate, evidence, log_root=self.logs)

    def refresh(self, evidence):
        evidence['candidate_digest'] = checker.content_digest(checker.source_inventory(self.candidate))
        evidence['policy_digests']['candidate'] = checker.load_policy(self.candidate)['digest']
        for change in evidence['changes']:
            for record in change['validation']:
                record['candidate_digest'] = evidence['candidate_digest']

    def assertFinding(self, result, needle):
        self.assertTrue(any(needle in finding for finding in result['findings']), result['findings'])
        self.assertEqual(result['status'], 'FINDINGS')
        self.assertEqual(result['findings'], sorted(set(result['findings'])))

    def test_pin_class_vocabulary_and_executable_pin_inventory(self):
        result = self.inspect()
        self.assertEqual(result['status'], 'HOLD')
        self.assertEqual({key: row['class'] for key, row in result['classifications'].items()},
                         {key: pin['class'] for key, pin in checker.pins(self.policy).items()})
        tables = [t for row in result['classifications'].values() for t in row['bound_tables']]
        self.assertEqual(set(tables), {f'tests/{stem}_claims.json' for stem in checker.STEMS})
        self.assertNotIn('tests/contract_invariants.json', tables)
        self.assertNotIn('tests/adapter_identity_claims.json', tables)
        self.assertTrue(all(row['class'] == 'RESEARCH_BASELINE' for row in result['research'].values()))

    def test_current_pin_assessment_is_hold_and_honest(self):
        result = self.inspect()
        self.assertFalse(result['repin_performed'])
        for field in ('approval', 'adoption', 'receipt_authentication'):
            self.assertEqual(result[field], 'NOT_BOUND')
        self.assertTrue(result['provisional'])
        self.assertEqual(result['label'], 'SIMULATED')
        self.assertEqual(result['status'], 'HOLD')

    def test_fully_evidenced_synthetic_vendor_and_citation_moves(self):
        for surfaces in (('vendor_pin',), ('ai_draft_pin',)):
            with self.subTest(surfaces=surfaces):
                # Reset between independent hypothetical moves.
                shutil.rmtree(self.candidate)
                shutil.copytree(self.baseline, self.candidate)
                result = self.compare(self.evidence(surfaces))
                self.assertEqual(result['findings'], [])
                self.assertEqual(result['status'], 'EVIDENCE_COMPLETE')
                self.assertEqual(result['approval'], 'NOT_BOUND')

    def test_combined_move_requires_both_independent_surfaces(self):
        self.assertEqual(self.compare(self.evidence(('vendor_pin', 'ai_draft_pin')))['findings'], [])

    def test_undeclared_pin_movement(self):
        evidence = self.evidence()
        self.move('ai_draft_pin')
        self.refresh(evidence)
        self.assertFinding(self.compare(evidence), 'undeclared/competing active pins')

    def test_dual_pin_handling_rejects_mixed_rows_and_constants(self):
        path = self.candidate / 'tests/agent_claims.json'
        table = checker.read_json(path)
        table['claims'][0]['pinned_sha'] = 'c' * 40
        write_json(path, table)
        self.assertFinding(self.inspect(), 'competing active pins')
        path = self.candidate / 'capital/agent_claims.py'
        path.write_text(path.read_text() + "\nPINNED_SHA = '" + 'c' * 40 + "'\n")
        with self.assertRaisesRegex(ValueError, 'competing'):
            checker.resolve_pin(self.candidate, 'capital/agent_claims.py')

    def test_static_resolution_aliases_and_fallback_rejection(self):
        self.assertEqual(checker.resolve_pin(self.candidate, 'capital/read_model_claims.py'),
                         checker.pins(self.policy)['vendor_pin']['sha'])
        path = self.candidate / 'capital/agent_claims.py'
        original = path.read_text()
        old = "PINNED_SHA = '" + checker.pins(self.policy)['ai_draft_pin']['sha'] + "'"
        for expression in ("PINNED_SHA = 'x' if ready else 'y'", "PINNED_SHA = get_pin()", "PINNED_SHA = old or new"):
            path.write_text(original.replace(old, expression))
            self.assertFinding(self.inspect(), 'unsupported PINNED_SHA expression/fallback')
        path.write_text(original + '\nif False:\n    PINNED_SHA = "fallback"\n')
        self.assertFinding(self.inspect(), 'competing or dynamic')

    def test_each_declared_table_and_its_rows_are_inspected(self):
        for pin in checker.pins(self.policy).values():
            for relative in pin['bound_tables']:
                path = self.candidate / relative
                original = path.read_bytes()
                table = checker.read_json(path)
                table['claims'][-1]['pinned_sha'] = 'c' * 40
                write_json(path, table)
                self.assertFinding(self.inspect(), relative)
                path.write_bytes(original)

    def test_vendor_hash_and_manifest_count(self):
        path = self.candidate / 'capital/vendor/manifest.json'
        manifest = checker.read_json(path)
        vendor = self.candidate / 'capital/vendor' / next(iter(manifest['files']))
        vendor.write_bytes(vendor.read_bytes() + b'\n# SIMULATED tamper\n')
        self.assertFinding(self.inspect(), 'vendor hash mismatch')
        manifest['files'].pop(next(iter(manifest['files'])))
        write_json(path, manifest)
        self.assertFinding(self.inspect(), 'manifest commit/count mismatch')

    def test_same_pin_vendor_tampering_cannot_hide_in_rehashed_manifest(self):
        evidence = self.evidence()
        path = self.candidate / 'capital/vendor/manifest.json'
        manifest = checker.read_json(path)
        relative = next(iter(manifest['files']))
        vendor = self.candidate / 'capital/vendor' / relative
        vendor.write_bytes(vendor.read_bytes() + b'\n# SIMULATED\n')
        manifest['files'][relative] = checker.digest(vendor.read_bytes())
        write_json(path, manifest)
        self.refresh(evidence)
        self.assertFinding(self.compare(evidence), 'undeclared vendor byte movement')

    def test_baseline_must_match_its_own_inventory(self):
        self.move('ai_draft_pin')
        result = checker.compare_snapshots(self.candidate, self.baseline, {}, log_root=self.logs)
        self.assertFinding(result, 'baseline: ai_draft_pin')

    def test_candidate_cannot_weaken_baseline_policy(self):
        evidence = self.evidence(('ai_draft_pin',))
        path = self.candidate / checker.NOTE
        original = path.read_text()
        for entry, key, value in (
            ('dual_pin_handling', 'active_pins_per_bound_surface_at_merge', 2),
            ('claim_table_regeneration_rule', 'deferred_regeneration_allowed', True),
            ('executable_pin_inventory', 'ai_draft_pin', {'sha': 'b' * 40, 'class': 'RESEARCH_BASELINE', 'bound_tables': []}),
            ('repin_trigger_procedure', 'triggers', ['freshness_only']),
        ):
            block = checker.ledger['extract_blocks'](original)[0]
            block['entries'][entry]['value'][key] = value
            path.write_text('```capital-decision-v1\n' + json.dumps(block) + '\n```\n')
            self.refresh(evidence)
            self.assertFinding(self.compare(evidence), 'candidate policy governance changed')
        path.write_text(original)

    def test_inventory_only_candidate_policy_sha_replacement_is_allowed(self):
        evidence = self.evidence(('ai_draft_pin',))
        path = self.candidate / checker.NOTE
        old = checker.pins(self.policy)['ai_draft_pin']['sha']
        path.write_text(path.read_text().replace('"sha": "' + old + '"', '"sha": "' + 'b' * 40 + '"'))
        self.refresh(evidence)
        self.assertEqual(self.compare(evidence)['findings'], [])

    def test_explicit_baseline_policy_is_authority_not_checker_checkout(self):
        surface = 'ai_draft_pin'
        self.move(surface)
        path = self.candidate / checker.NOTE
        pin = checker.pins(self.policy)[surface]
        path.write_text(path.read_text().replace('"sha": "' + pin['sha'] + '"', '"sha": "' + 'b' * 40 + '"'))
        self.assertEqual(self.inspect()['findings'], [])
        self.assertFinding(checker.inspect_snapshot(self.candidate, self.policy), 'undeclared/competing')

    def test_repin_trigger_procedure_rejects_nontriggers_and_missing_atomic_fields(self):
        evidence = self.evidence(('ai_draft_pin',))
        for nontrigger in self.policy['values']['repin_trigger_procedure']['non_triggers']:
            evidence['changes'][0]['trigger'] = nontrigger
            self.assertFinding(self.compare(evidence), 'unauthorized/non-trigger')
        evidence['changes'][0]['trigger'] = self.policy['values']['repin_trigger_procedure']['triggers'][0]
        for key in ('acceptance_basis', 'decision_maker', 'consumer_impact', 'compatibility_authority_analysis', 'rollback'):
            old = evidence['changes'][0].pop(key)
            self.assertFinding(self.compare(evidence), 'missing ' + key)
            evidence['changes'][0][key] = old

    def test_claim_table_regeneration_rule_requires_every_artifact_even_unchanged(self):
        evidence = self.evidence(('vendor_pin',))
        change = evidence['changes'][0]
        required = checker.required_evidence(self.policy, 'vendor_pin', self.baseline, self.candidate)
        for record in list(change['artifacts']):
            with self.subTest(path=record['path']):
                altered = dict(change, artifacts=[r for r in change['artifacts'] if r is not record])
                missing = checker._validate_artifacts(altered, required, self.candidate, [])
                self.assertEqual(missing, [record['path']])
        self.assertTrue(all(p in required['artifacts'] for p in checker.pins(self.policy)['vendor_pin']['bound_tables']))
        self.assertIn('tests/vectors/finance_vectors.json', required['artifacts'])
        self.assertIn('tests/golden/demo.json', required['artifacts'])
        self.assertIn('capital/evidence.py', required['artifacts'])
        self.assertIn('tests/test_ce1_claims.py', required['artifacts'])

    def test_missing_tables_vectors_docs_and_validation_are_reported(self):
        evidence = self.evidence(('ai_draft_pin',))
        evidence['changes'][0]['artifacts'] = []
        evidence['changes'][0]['validation'] = []
        result = self.compare(evidence)
        self.assertIn('ai_draft_pin:tests/agent_claims.json', result['missing_artifacts'])
        self.assertIn('ai_draft_pin:README.md', result['missing_artifacts'])
        self.assertIn('ai_draft_pin:tests/vectors/pack/clean.json', result['missing_artifacts'])
        self.assertIn('ai_draft_pin:acceptance:packaged-smoke:1', result['missing_validation'])

    def test_every_command_result_required_not_stage_summaries(self):
        evidence = self.evidence(('vendor_pin',))
        change = evidence['changes'][0]
        required = checker.required_evidence(self.policy, 'vendor_pin', self.baseline, self.candidate)
        cand = {'content_digest': evidence['candidate_digest'], 'root': str(self.candidate)}
        for record in list(change['validation']):
            with self.subTest(check=record['check_id']):
                altered = dict(change, validation=[r for r in change['validation'] if r is not record])
                self.assertEqual(checker._validate_results(altered, required, evidence, cand, self.logs, []), [record['check_id']])
        stage_commands = [key for key in required['validation'] if key.startswith('acceptance:upstream-claims:')]
        self.assertEqual(len(stage_commands), 7)
        self.assertEqual({k.split(':')[1] for k in required['validation'] if k.startswith('acceptance:')},
                         {'unit', 'storage-conformance', 'pinned-vendor', 'upstream-claims', 'node-check',
                          'browser', 'packaged-smoke', 'seeded-demo', 'integrated-journeys'})

    def test_validation_registry_agrees_with_trusted_acceptance_contract(self):
        acceptance = checker.trusted_module('repin_acceptance_test', 'acceptance.py')
        registry = checker.validation_registry()
        for stage in acceptance['build_plan']():
            for index, argv in enumerate(stage['commands']):
                argv = list(argv)
                if argv[0] == sys.executable:
                    argv[0] = 'python3'
                self.assertEqual(registry[f'acceptance:{stage["id"]}:{index}'], argv)
        self.assertIn('acceptance:packaged-smoke:1', registry)

    def test_citation_stage_requirements_expand_with_changed_inputs(self):
        self.evidence(('ai_draft_pin',))
        required = checker.required_evidence(self.policy, 'ai_draft_pin', self.baseline, self.candidate)
        self.assertNotIn('acceptance:node-check:0', required['validation'])
        for path, stage in (('capital/static/app.js', 'node-check'), ('capital/store.py', 'storage-conformance'),
                            ('capital/vendor/manifest.json', 'pinned-vendor')):
            target = self.candidate / path
            raw = target.read_bytes()
            target.write_bytes(raw + b'\n')
            required = checker.required_evidence(self.policy, 'ai_draft_pin', self.baseline, self.candidate)
            self.assertIn(f'acceptance:{stage}:0', required['validation'])
            target.write_bytes(raw)

    def test_validation_stale_failed_skipped_wrong_argv_duplicates_and_logs(self):
        evidence = self.evidence(('ai_draft_pin',))
        change = evidence['changes'][0]
        original = copy.deepcopy(change['validation'][0])
        for patch in ({'candidate_id': 'other'}, {'candidate_digest': '0' * 64}, {'exit_code': 1},
                      {'exit_code': False}, {'result': 'SKIPPED'}, {'argv': ['true']}, {'logs': []}):
            change['validation'][0] = dict(original, **patch)
            self.assertFinding(self.compare(evidence), 'invalid/stale/failed validation')
        change['validation'][0] = original
        change['validation'].append(original)
        self.assertFinding(self.compare(evidence), 'duplicate validation')
        change['validation'].pop()
        log = self.logs / original['logs'][0]['path']
        log.write_text('FAILED (errors=1)\n')
        original['logs'][0]['digest'] = checker.digest(log.read_bytes())
        self.assertFinding(self.compare(evidence), 'contradictory failed/skipped log')
        log.write_text('changed after hashing')
        self.assertFinding(self.compare(evidence), 'log digest mismatch')

    def test_citation_requires_local_material_and_verified_not_skipped_result(self):
        evidence = self.evidence(('ai_draft_pin',))
        change = evidence['changes'][0]
        record = next(r for r in change['validation'] if r['check_id'] == 'citation:agent')
        log = self.logs / record['logs'][0]['path']
        log.write_text('SKIPPED\n')
        record['logs'][0]['digest'] = checker.digest(log.read_bytes())
        self.assertFinding(self.compare(evidence), 'citation source verification missing/skipped')
        source = next((self.candidate / 'source_material/ai_draft_pin').rglob('*.md'))
        source.write_text('SIMULATED missing source headings')
        self.refresh(evidence)
        self.assertFinding(self.compare(evidence), 'source citation missing')

    def test_manual_regeneration_requires_claim_sources_and_independent_expectations(self):
        evidence = self.evidence(('ai_draft_pin',))
        change = evidence['changes'][0]
        record = next(r for r in change['artifacts'] if r['path'] == 'tests/agent_claims.json')
        record['method'] = 'manual'
        record.pop('claim_evidence', None)
        record.pop('independent_expectations', None)
        self.assertFinding(self.compare(evidence), 'manual regeneration needs')
        table = checker.read_json(self.candidate / record['path'])
        record['claim_evidence'] = [{'claim_id': row['id'], 'source_path': 'source_material/ai_draft_pin/' + row['source_doc'],
            'source_digest': checker.file_digest(self.candidate, 'source_material/ai_draft_pin/' + row['source_doc']),
            'explanation': 'SIMULATED reconstruction'} for row in table['claims']]
        record['independent_expectations'] = [{'claim_id': row['id'], 'expected': row['expected'],
            'rationale': 'SIMULATED independent expectation fixture'} for row in table['claims']]
        self.assertEqual(self.compare(evidence)['findings'], [])
        record['independent_expectations'].pop()
        self.assertFinding(self.compare(evidence), 'manual regeneration needs')

    def test_research_baseline_rule_keeps_changes_separate_and_preserves_original(self):
        evidence = self.evidence()
        path = self.candidate / 'docs/decisions/CAPITAL_DEFAULT_RECOVERY.md'
        text = path.read_text()
        path.write_text('> 기준: SIMULATED research-only correction abc1234\n' + text)
        self.refresh(evidence)
        result = self.compare(evidence)
        self.assertTrue(result['research_changes'])
        self.assertTrue(all(f.startswith('research provenance correction') for f in result['findings']))
        relative = path.relative_to(self.candidate).as_posix()
        original = self.base_report['research'][relative]
        evidence['research_corrections'] = [{'path': relative, 'date': '2026-11-01', 'reason': 'SIMULATED correction',
            'replacement_basis': 'SIMULATED local research source', 'original_digest': original['digest'],
            'original_provenance': original['provenance']}]
        result = self.compare(evidence)
        self.assertEqual(result['findings'], [])
        self.assertEqual(result['research_changes'][0]['original'], original)
        self.assertEqual(result['classifications'], self.base_report['classifications'])

    def test_unrelated_same_sha_surfaces_are_not_blanket_reclassified(self):
        evidence = self.evidence()
        path = self.candidate / 'tests/contract_invariants.json'
        table = checker.read_json(path)
        table['pinned_sha'] = 'd' * 40
        write_json(path, table)
        self.refresh(evidence)
        self.assertEqual(self.compare(evidence)['findings'], [])

    def test_drift_fence_integration_enforces_complete_sorted_unique_inventory(self):
        path = self.candidate / 'tests/decision_bindings.json'
        data = checker.read_json(path)
        data['entries'].reverse()
        write_json(path, data)
        self.assertFinding(self.inspect(), 'sorted and unique')
        data['entries'].reverse()
        row = next(row for row in data['entries'] if row['decision_id'] == 'upstream-repin-policy-decision')
        row['bindings'][0] = {'kind': 'module', 'path': 'scripts/upstream_repin_check.py', 'status': 'PENDING_CONSUMER',
                              'consumer_node': 'fake', 'reason': 'fake'}
        write_json(path, data)
        self.assertFinding(self.inspect(), 'unlisted CONSUMED module')

    def test_artifact_digest_duplicates_result_and_manual_method_fail_closed(self):
        evidence = self.evidence(('ai_draft_pin',))
        change = evidence['changes'][0]
        record = next(r for r in change['artifacts'] if r['path'] == 'tests/agent_claims.json')
        required = checker.required_evidence(self.policy, 'ai_draft_pin', self.baseline, self.candidate)
        for field, value, finding in (('digest', '0' * 64, 'invalid artifact'),
                                     ('result', 'SOURCE_INSPECTED', 'requires regeneration result'),
                                     ('method', 'generator', 'requires manual reconstruction')):
            old = record[field]
            record[field] = value
            findings = []
            checker._validate_artifacts(change, required, self.candidate, findings)
            self.assertTrue(any(finding in f for f in findings), findings)
            record[field] = old
        change['artifacts'].append(record)
        findings = []
        checker._validate_artifacts(change, required, self.candidate, findings)
        self.assertTrue(any('duplicate artifact' in f for f in findings), findings)

    def test_invalid_movement_records_and_missing_artifact_files(self):
        evidence = self.evidence(('ai_draft_pin',))
        change = evidence['changes'][0]
        for field, value in (('surface', 'unrelated'), ('old_sha', '0' * 40), ('new_sha', 'short')):
            old = change[field]
            change[field] = value
            self.assertFinding(self.compare(evidence), 'invalid comparison')
            change[field] = old
        evidence['changes'].append(change)
        self.assertFinding(self.compare(evidence), 'unknown/duplicate changed surface')
        evidence['changes'].pop()
        (self.candidate / 'tests/agent_claims.json').unlink()
        result = self.compare(evidence)
        self.assertFinding(result, 'tests/agent_claims.json')

    def test_vendor_membership_and_source_bytes_are_checked(self):
        evidence = self.evidence(('vendor_pin',))
        manifest = checker.read_json(self.candidate / 'capital/vendor/manifest.json')
        relative = next(iter(manifest['files']))
        source = self.candidate / 'source_material/vendor_pin' / manifest['source_prefix'] / relative
        source.write_bytes(source.read_bytes() + b'\n# SIMULATED conflicting source\n')
        self.refresh(evidence)
        self.assertFinding(self.compare(evidence), 'source/vendor bytes disagree')
        path = self.candidate / 'capital/vendor/manifest.json'
        manifest['files']['../escape.py'] = manifest['files'].pop(relative)
        write_json(path, manifest)
        self.refresh(evidence)
        self.assertFinding(self.compare(evidence), 'vendor manifest membership/source identity changed')

    def test_bad_shapes_duplicate_json_keys_and_argument_misuse(self):
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            path = self.logs / 'bad.json'
            path.write_text('{"schema":1,"schema":2}')
            checker.read_json(path)
        for value in ({}, {'schema': checker.SCHEMA}, {'schema': checker.SCHEMA, 'changes': 'wrong'}):
            self.assertFinding(self.compare(value), 'invalid comparison')
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
            checker.main(['--check', '--baseline', str(self.baseline)])
        self.assertEqual(exc.exception.code, 2)

    def test_path_traversal_symlinks_and_external_evidence_boundary(self):
        for path in ('../secret', '/etc/passwd', 'capital/../README.md', 'capital\\secret'):
            with self.assertRaises(ValueError):
                checker.safe_path(self.candidate, path)
        (self.candidate / 'capital/escape.py').symlink_to(self.logs / 'secret.py')
        self.assertFinding(self.inspect(), 'escaping path')
        (self.candidate / 'capital/escape.py').unlink()
        evidence = self.evidence(('ai_draft_pin',))
        evidence['changes'][0]['validation'][0]['logs'][0]['path'] = '../outside.log'
        self.assertFinding(self.compare(evidence), 'escaping/non-normalized path')
        result = checker.compare_snapshots(self.baseline, self.candidate, evidence, log_root=self.candidate)
        self.assertFinding(result, 'logs must be external')

    def test_evidence_identity_and_candidate_content_digests(self):
        evidence = self.evidence(('ai_draft_pin',))
        evidence['candidate_digest'] = '0' * 64
        self.assertFinding(self.compare(evidence), 'candidate_digest mismatch')
        self.refresh(evidence)
        path = self.candidate / 'tests/test_agent_claims.py'
        path.write_text(path.read_text() + '\n# SIMULATED late mutation\n')
        self.assertFinding(self.compare(evidence), 'candidate_digest mismatch')

    def test_cli_and_comparison_never_write_fetch_or_execute_candidate(self):
        evidence = self.evidence(('ai_draft_pin',))
        marker = self.logs / 'executed'
        path = self.candidate / 'capital/agent_claims.py'
        path.write_text(path.read_text() + '\nraise RuntimeError("candidate must not execute")\n')
        self.refresh(evidence)
        record = next(r for r in evidence['changes'][0]['artifacts'] if r['path'] == 'capital/agent_claims.py')
        record['digest'] = checker.file_digest(self.candidate, record['path'])
        evidence_path = self.logs / 'evidence.json'
        write_json(evidence_path, evidence)
        before = checker.source_inventory(self.candidate)
        with mock.patch.object(subprocess, 'run', side_effect=AssertionError('must not execute')):
            self.assertEqual(self.compare(evidence)['findings'], [])
        proc = subprocess.run([sys.executable, str(ROOT / 'scripts/upstream_repin_check.py'), '--baseline', str(self.baseline),
                               '--candidate', str(self.candidate), '--evidence', str(evidence_path)],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['status'], 'EVIDENCE_COMPLETE')
        self.assertEqual(before, checker.source_inventory(self.candidate))
        self.assertFalse(marker.exists())
        self.assertFalse(list(self.candidate.rglob('__pycache__')))


if __name__ == '__main__':
    unittest.main()
