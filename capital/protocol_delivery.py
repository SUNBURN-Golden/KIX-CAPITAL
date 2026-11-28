"""Pinned read-only Protocol delivery used by the local fake gate."""
from __future__ import annotations

import json

from capital.compat_preflight import check_bundle, read_bundle_file, sha256

COMMIT = '8ba7f6c36373ac0ec49246f51f7471c164ac3a28'
MANIFEST = 'sdk/compat/manifests/manifest.bootstrap-2.json'
EXPECTED = 'sdk/compat/delivery.expected.json'
TUPLE = 'sdk/compat/delivery.json'
PIN_HEADER = 'X-Kix-Protocol-Commit'


def read_delivery(root):
    """Check the local BOOTSTRAP files and return the gate's delivery tuple."""
    delivery = json.loads((root / TUPLE).read_bytes())
    vendor = (root / 'capital/vendor/manifest.json').read_bytes()
    report = check_bundle(root, MANIFEST, root / EXPECTED)
    if (not report.matched or report.profile_kind != 'BOOTSTRAP'
            or delivery != {
                'format': 'capital-protocol-delivery/1',
                'repository': 'SUNBURN-Golden/kix-protocol',
                'commit': COMMIT,
                'tree': 'd3f5412ef84f64fe83c5d3a3d3ada173921bfbf9',
                'sdk_manifest_sha256': 'eec1750532d319ea06d8ae61bafa77316067088a84a9b70d20a1f6966dfba1e0',
                'vendor_manifest_sha256': '62056902f9344c4f092d1652baeac607b31ea0ecf4672b86638ac9a740a72d36',
            } or delivery['sdk_manifest_sha256'] != report.manifest_sha256
            or delivery['vendor_manifest_sha256'] != sha256(vendor)
            or json.loads(vendor).get('commit') != COMMIT):
        raise ValueError('Protocol delivery pin mismatch')
    fixture = read_bundle_file(root, 'reference/v0.3-rc1/protocol_contract.json')
    if sha256(fixture) != 'ed827de1a8bfe7c48612473965793dcaab65137e575f862761fd160f77ae4c1e':
        raise ValueError('Protocol catalogue fixture pin mismatch')
    return delivery
