"""Deterministic decision rules for the production-inert Z0 path-policy study."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


REQUIRED_BENCHMARK_CASES: Final = frozenset({"E1", "X3", "R3", "A1"})
PATH_POLICY_IDS: Final = frozenset({"P0", "P1", "P2"})


class PathPolicyError(ValueError):
    """The evidence is insufficient to select a path policy."""


@dataclass(frozen=True)
class PathPolicyMeasurement:
    """One answer-key and resource measurement for a candidate include policy."""

    policy_id: str
    case_id: str
    relevant_path_recall: float
    false_positive_count: int
    indexed_file_count: int
    indexed_bytes: int
    shard_bytes: int
    build_seconds: float
    refresh_seconds: float
    query_latency_ms: float


def select_path_policy(measurements: tuple[PathPolicyMeasurement, ...]) -> str:
    """Choose only from complete evidence; P0 cannot win on recall alone."""

    by_policy: dict[str, dict[str, PathPolicyMeasurement]] = {}
    for measurement in measurements:
        _validate_measurement(measurement)
        policy = by_policy.setdefault(measurement.policy_id, {})
        if measurement.case_id in policy:
            raise PathPolicyError(
                f"duplicate measurement: {measurement.policy_id}/{measurement.case_id}"
            )
        policy[measurement.case_id] = measurement
    if set(by_policy) != PATH_POLICY_IDS:
        raise PathPolicyError("P0, P1 and P2 each require complete measured evidence")
    if any(set(cases) != REQUIRED_BENCHMARK_CASES for cases in by_policy.values()):
        raise PathPolicyError("each policy must cover E1, X3, R3 and A1")

    candidates = [
        policy_id
        for policy_id, cases in by_policy.items()
        if all(item.relevant_path_recall == 1.0 for item in cases.values())
    ]
    if not candidates:
        raise PathPolicyError("no policy reaches full answer-key recall")
    candidates.sort(key=lambda policy_id: _policy_cost(by_policy[policy_id]))
    winner = candidates[0]
    if winner == "P0" and len(candidates) > 1:
        p0 = _policy_cost(by_policy["P0"])
        best_narrow = min(
            _policy_cost(by_policy[policy_id])
            for policy_id in candidates
            if policy_id != "P0"
        )
        if p0[0] > best_narrow[0] or p0[1:] > best_narrow[1:]:
            raise PathPolicyError(
                "P0 cannot win solely by recall when a narrower full-recall policy "
                "has lower false-positive or resource burden"
            )
    return winner


def _validate_measurement(measurement: PathPolicyMeasurement) -> None:
    if measurement.policy_id not in PATH_POLICY_IDS:
        raise PathPolicyError("unknown path policy")
    if measurement.case_id not in REQUIRED_BENCHMARK_CASES:
        raise PathPolicyError("unknown benchmark case")
    if not 0.0 <= measurement.relevant_path_recall <= 1.0:
        raise PathPolicyError("recall must be in 0..1")
    numeric_values = (
        measurement.false_positive_count,
        measurement.indexed_file_count,
        measurement.indexed_bytes,
        measurement.shard_bytes,
        measurement.build_seconds,
        measurement.refresh_seconds,
        measurement.query_latency_ms,
    )
    if any(value < 0 for value in numeric_values):
        raise PathPolicyError("measurements must be non-negative")


def _policy_cost(
    cases: dict[str, PathPolicyMeasurement],
) -> tuple[float, int, int, float, float, float]:
    return (
        sum(item.false_positive_count for item in cases.values()),
        sum(item.shard_bytes for item in cases.values()),
        sum(item.indexed_bytes for item in cases.values()),
        max(item.build_seconds for item in cases.values()),
        max(item.refresh_seconds for item in cases.values()),
        max(item.query_latency_ms for item in cases.values()),
    )
