"""Seam registry: every Protocol has a row, and ADOPTED requires an upstream receipt."""
import inspect
import re
import tempfile
import unittest
from pathlib import Path

import capital.ports as ports
from capital.auth import LocalRoleAuthorizer
from capital.export import UnsignedSigner
from capital.producer import PinnedFsmProducer
from capital.projection import SimulationProjection
from capital.service import CapitalService
from capital.store import FileWorkspace, InMemoryStorage

ROOT = Path(__file__).resolve().parents[1]
SEAMS = ROOT / 'docs' / 'SEAMS.md'
RECEIPT = re.compile(r'(?:[0-9a-f]{7,64}|https://github\.com/\S+)')
EMPTY_RECEIPT = {'', 'NONE', 'NOT_BOUND', 'DECISION_REQUIRED', '—', '-', 'N/A'}


def protocol_names():
    found = []
    for name, obj in vars(ports).items():
        if inspect.isclass(obj) and getattr(obj, '_is_protocol', False) and name.endswith('Port'):
            found.append(name)
    return sorted(found)


def parse_rows(text):
    header = None
    rows = []
    for line in text.splitlines():
        if not line.startswith('|'):
            continue
        cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
        if not cells or set(cells[0]) <= set('-: '):
            continue
        if cells[0] == 'Port':
            header = cells
            continue
        if header is None:
            raise AssertionError('seam table has no header')
        if len(cells) != len(header):
            raise AssertionError(f'seam row width {len(cells)} != {len(header)}')
        rows.append(dict(zip(header, cells)))
    if not rows:
        raise AssertionError('seam table is empty')
    return rows


def assert_registry(text, names):
    rows = parse_rows(text)
    by_port = {}
    for row in rows:
        port = row['Port']
        if port in by_port:
            raise AssertionError(f'duplicate seam row {port}')
        by_port[port] = row
        if row['Status'] == 'ADOPTED' and not _receipt(row.get('Upstream receipt', '')):
            raise AssertionError(f'{port} is ADOPTED without an upstream receipt')
    missing = [name for name in names if name not in by_port]
    if missing:
        raise AssertionError('ports missing a seam row: ' + ', '.join(missing))
    extra = [port for port in by_port if port not in names]
    if extra:
        raise AssertionError('seam rows without a Protocol: ' + ', '.join(extra))
    return rows


def _receipt(value):
    token = value.strip()
    if token.upper() in EMPTY_RECEIPT or token in EMPTY_RECEIPT:
        return False
    return RECEIPT.search(token) is not None


class SeamRegistryTests(unittest.TestCase):
    def test_every_protocol_has_a_non_adopted_row(self):
        names = protocol_names()
        self.assertEqual(names, [
            'AuthorizerPort', 'ProducerPort', 'ProjectionPort', 'SettlementPolicyPort',
            'SignaturePort', 'StoragePort', 'TermsPolicyPort',
        ])
        rows = assert_registry(SEAMS.read_text(encoding='utf-8'), names)
        for row in rows:
            self.assertNotEqual(row['Status'], 'ADOPTED')
            self.assertEqual(row['Upstream receipt'], 'NONE')
            self.assertIn('CAP-', row['Readiness'])
        by_port = {row['Port']: row for row in rows}
        self.assertIn('PinnedFsmProducer', by_port['ProducerPort']['Local implementation'])
        self.assertIn('InMemoryStorage', by_port['StoragePort']['Local implementation'])
        self.assertIn('SimulationProjection', by_port['ProjectionPort']['Local implementation'])
        self.assertIn('LocalRoleAuthorizer', by_port['AuthorizerPort']['Local implementation'])
        self.assertIn('UnsignedSigner', by_port['SignaturePort']['Local implementation'])
        self.assertIn('DecisionNoteSettlementPolicy', by_port['SettlementPolicyPort']['Local implementation'])
        self.assertEqual(by_port['SettlementPolicyPort']['Status'], 'NOT_BOUND')
        self.assertEqual(by_port['SettlementPolicyPort']['Upstream receipt'], 'NONE')
        self.assertIn('capital-local-facade/1', by_port['ProducerPort']['Upstream contract'])
        text = SEAMS.read_text(encoding='utf-8')
        self.assertIn('NOT_BOUND', text)
        self.assertIn('not a SEMANTIC_CONFORMANCE', text)
        self.assertIn('CAP-16', by_port['ProducerPort']['Readiness'])

    def test_adopted_without_receipt_fails(self):
        bad = (
            '| Port | Local implementation | Upstream contract | Readiness | Status | Upstream receipt |\n'
            '| --- | --- | --- | --- | --- | --- |\n'
            '| StoragePort | local | upstream | CAP-11 | ADOPTED | NONE |\n'
            '| ProjectionPort | local | upstream | CAP-13 | NOT_BOUND | NONE |\n'
            '| AuthorizerPort | local | upstream | CAP-19 | NOT_BOUND | NONE |\n'
            '| SignaturePort | local | upstream | CAP-15 | NOT_BOUND | NONE |\n'
            '| ProducerPort | local | upstream | CAP-16 | NOT_BOUND | NONE |\n'
        )
        with self.assertRaisesRegex(AssertionError, 'ADOPTED without an upstream receipt'):
            assert_registry(bad, protocol_names())

    def test_missing_port_row_fails(self):
        text = SEAMS.read_text(encoding='utf-8').replace('| ProducerPort |', '| RetiredPort |')
        with self.assertRaisesRegex(AssertionError, 'ProducerPort'):
            assert_registry(text, protocol_names())

    def test_default_instances_satisfy_the_protocols(self):
        self.assertIsInstance(InMemoryStorage(), ports.StoragePort)
        with tempfile.TemporaryDirectory() as directory:
            workspace = FileWorkspace.open(directory)
            try:
                self.assertIsInstance(workspace, ports.StoragePort)
            finally:
                workspace.close()
        self.assertIsInstance(SimulationProjection(), ports.ProjectionPort)
        self.assertIsInstance(LocalRoleAuthorizer(), ports.AuthorizerPort)
        self.assertIsInstance(UnsignedSigner(), ports.SignaturePort)
        producer = PinnedFsmProducer()
        self.assertIsInstance(producer, ports.ProducerPort)
        service = CapitalService()
        self.assertIsInstance(service.producer, ports.ProducerPort)
        self.assertIsInstance(service.projection_port, ports.ProjectionPort)
        self.assertIsInstance(service.storage, ports.StoragePort)
        self.assertIsInstance(service.authorizer, ports.AuthorizerPort)
        self.assertIsInstance(service.signer, ports.SignaturePort)
        self.assertIsInstance(service.terms, ports.TermsPolicyPort)
        self.assertIsInstance(service.policy, ports.SettlementPolicyPort)

    def test_readiness_quotes_the_local_contract_and_stays_not_bound(self):
        ready = CapitalService().readiness()
        note = ready['requirement_notes']['CAP-16']
        self.assertIn('capital-local-facade/1', note)
        self.assertIn('capital/contract/facade-v1.json', note)
        self.assertIn('not SEMANTIC_CONFORMANCE', note)
        self.assertIn('NOT_BOUND', note)
        group = next(row for row in ready['groups'] if 'CAP-16' in row['requirements'])
        quoted = group['behavior'] + '\n' + '\n'.join(group['available'])
        self.assertIn('capital-local-facade/1', quoted)
        self.assertIn('capital/contract/facade-v1.json', quoted)
        self.assertIn('NOT_BOUND', quoted)
        self.assertNotEqual(group['status'], 'ADOPTED')
        self.assertTrue(group['blockers'])
        self.assertEqual(ready['upstream_binding'], 'NOT_BOUND')


if __name__ == '__main__':
    unittest.main()
