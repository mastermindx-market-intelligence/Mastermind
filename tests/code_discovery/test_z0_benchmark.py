"""Decision tests for Z0's path-policy evidence gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from experiments.code_discovery.evaluation_manifest import load_evaluation_manifest
from experiments.code_discovery.z0_benchmark import (
    NO_SAFE_TOPOLOGY,
    P0Justification,
    PathPolicyError,
    PathPolicyMeasurement,
    TopologyEnvelope,
    TopologyMeasurement,
    select_path_policy,
    select_topology,
)


_MANIFEST = (
    Path(__file__).parent.parent
    / "fixtures"
    / "code_discovery"
    / "evaluation-manifest.v1.json"
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


def test_p0_cannot_win_on_recall_alone_and_constitutional_failure_dominates_cost() -> None:
    """A broad policy needs a non-recall justification; a hard failure ends ranking."""

    measurements = list(_complete())
    for index, measurement in enumerate(measurements):
        if measurement.policy_id in {"P1", "P2"}:
            measurements[index] = _measurement(
                measurement.policy_id,
                measurement.case_id,
                relevant_path_recall=0.9,
                false_positive_count=1,
                indexed_bytes=1,
                shard_bytes=1,
                build_seconds=1,
                refresh_seconds=1,
                query_latency_ms=1,
            )
    with pytest.raises(PathPolicyError, match="P0 cannot win on recall alone"):
        select_path_policy(tuple(measurements))

    failed = list(_complete())
    failed[0] = _measurement(
        "P0",
        "E1",
        hard_failure_code="SOURCE_MOVED",
    )
    with pytest.raises(PathPolicyError, match="constitutional failure"):
        select_path_policy(tuple(failed))


def test_p0_requires_a_manifest_bound_preregistered_justification() -> None:
    """A truthy caller flag cannot stand in for the frozen tie-break authority."""

    measurements = list(_complete())
    for index, measurement in enumerate(measurements):
        if measurement.policy_id in {"P1", "P2"}:
            measurements[index] = _measurement(
                measurement.policy_id,
                measurement.case_id,
                relevant_path_recall=0.9,
            )
    manifest = load_evaluation_manifest(_MANIFEST)

    with pytest.raises(PathPolicyError, match="manifest-bound"):
        select_path_policy(
            tuple(measurements),
            evaluation_manifest=manifest,
            p0_justification=True,
        )
    with pytest.raises(PathPolicyError, match="manifest-bound"):
        select_path_policy(
            tuple(measurements),
            evaluation_manifest=manifest,
            p0_justification=P0Justification(
                manifest_digest=manifest.digest,
                tie_break_rule_digest="f" * 64,
            ),
        )

    assert select_path_policy(
        tuple(measurements),
        evaluation_manifest=manifest,
        p0_justification=P0Justification.from_manifest(manifest),
    ) == "P0"


def test_topology_is_selected_only_inside_t0_t1_resource_envelopes() -> None:
    """Unknown/over-budget topology is a typed no-safe result, never a default zero."""

    envelopes = (
        TopologyEnvelope("T0", max_cpu_ms=10, max_rss_bytes=20, max_disk_bytes=30),
        TopologyEnvelope("T1", max_cpu_ms=20, max_rss_bytes=30, max_disk_bytes=40),
    )
    observations = (
        TopologyMeasurement("T0", cpu_ms=9, rss_bytes=19, disk_bytes=29),
        TopologyMeasurement("T1", cpu_ms=12, rss_bytes=20, disk_bytes=25),
    )
    assert select_topology(observations, envelopes) == "T0"

    unsafe = (
        TopologyMeasurement("T0", cpu_ms=None, rss_bytes=1, disk_bytes=1),
        TopologyMeasurement("T1", cpu_ms=21, rss_bytes=1, disk_bytes=1),
    )
    assert select_topology(unsafe, envelopes) == NO_SAFE_TOPOLOGY
