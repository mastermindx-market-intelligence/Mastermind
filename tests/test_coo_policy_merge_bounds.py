"""Regression for the Bridge + protected hierarchy policy composition.

The original read budget and the versioned policy selection are independent
security gates. A source merge must retain BOTH, never an unbounded fallback.
"""
from pathlib import Path

import pytest

from control_plane.executive_coo_policy import (
    CooCyclePolicy, CooCyclePolicyError,
    EXPECTED_POLICY_SHA256, HIERARCHY_POLICY_SHA256,
    _MAX_COO_POLICY_SOURCE_BYTES,
)


@pytest.mark.parametrize(
    "version,expected_depth,expected_fanout,expected_digest",
    [(1, 1, 8, EXPECTED_POLICY_SHA256),
     (2, 3, 16, HIERARCHY_POLICY_SHA256)],
)
def test_closed_policy_version_survives_protected_merge(
    version, expected_depth, expected_fanout, expected_digest
):
    policy = CooCyclePolicy.load(version=version)
    assert policy.schema_version == version
    assert policy.max_depth == expected_depth
    assert policy.max_fan_out_per_parent == expected_fanout
    assert policy.policy_sha256 == expected_digest


@pytest.mark.parametrize("version", [1, 2])
def test_policy_source_byte_ceiling_applies_to_both_versions(version, tmp_path):
    root = Path(__file__).resolve().parents[1]
    base = (root / "config" / "authority_map.yml").read_bytes()
    assert len(base) < _MAX_COO_POLICY_SOURCE_BYTES
    enlarged = tmp_path / "oversize-authority-map.yml"
    enlarged.write_bytes(base + b"\n# " + b"x" * _MAX_COO_POLICY_SOURCE_BYTES)
    with pytest.raises(CooCyclePolicyError, match="exceeds byte limit"):
        CooCyclePolicy.load(enlarged, version=version)
