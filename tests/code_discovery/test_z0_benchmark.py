"""Decision tests for Z0's path-policy evidence gate."""

from __future__ import annotations

import pytest

from experiments.code_discovery.z0_benchmark import (
    PathPolicyError,
    PathPolicyMeasurement,
    select_path_policy,
)


def _measurement(policy_id: str, case_id: str, **overrides: object) -> PathPolicyMeasurement:
    values: dict[str, object] = {
        "policy_id": policy_id,
        "case_id": case_id,
        "relevant_path_recall": 1.0,
        "false_positive_count": 10,
        "indexed_file_count": 100,
        "indexed_bytes": 1_000,
        "shard_bytes": 500,
        "build_seconds": 3.0,
        "refresh_seconds": 1.0,
        "query_latency_ms": 10.0,
    }
    values.update(overrides)
    return PathPolicyMeasurement(**values)


def _complete(**overrides: object) -> tuple[PathPolicyMeasurement, ...]:
    return tuple(
        _measurement(policy, case, **overrides)
        for policy in ("P0", "P1", "P2")
        for case in ("E1", "X3", "R3", "A1")
    )


def test_selects_narrow_full_recall_policy_from_complete_case_evidence() -> None:
    """P1/P2 win only with answer-key coverage plus lower measured burden."""

    measurements = list(_complete())
    for index, measurement in enumerate(measurements):
        if measurement.policy_id == "P1":
            measurements[index] = _measurement(
                "P1",
                measurement.case_id,
                false_positive_count=2,
                indexed_bytes=600,
                shard_bytes=300,
                build_seconds=2,
                refresh_seconds=0.8,
                query_latency_ms=8,
            )

    assert select_path_policy(tuple(measurements)) == "P1"


def test_refuses_incomplete_evidence_and_p0_recall_only_selection() -> None:
    """No policy can graduate without all cases or by broad recall alone."""

    with pytest.raises(PathPolicyError, match="cover"):
        select_path_policy(_complete()[:-1])

    measurements = list(_complete())
    for index, measurement in enumerate(measurements):
        if measurement.policy_id == "P0":
            measurements[index] = _measurement(
                "P0",
                measurement.case_id,
                false_positive_count=99,
                indexed_bytes=9_000,
                shard_bytes=9_000,
                build_seconds=99,
                refresh_seconds=99,
                query_latency_ms=99,
            )
    assert select_path_policy(tuple(measurements)) == "P1"
