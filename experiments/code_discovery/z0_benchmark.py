"""Deterministic decision rules for the production-inert Z0 path-policy study."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from .evaluation_manifest import EvaluationManifest


REQUIRED_BENCHMARK_CASES: Final = frozenset({"E1", "X3", "R3", "A1"})
PATH_POLICY_IDS: Final = frozenset({"P0", "P1", "P2"})
TOPOLOGY_IDS: Final = frozenset({"T0", "T1"})
NO_SAFE_TOPOLOGY: Final = "NO_SAFE_TOPOLOGY"
_SHA256_RE: Final = re.compile(r"[0-9a-f]{64}\Z")


class PathPolicyError(ValueError):
    """The evidence is insufficient to select a path policy."""


class TopologyError(ValueError):
    """The topology evidence is malformed rather than safely rejectable."""


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
    hard_failure_code: str | None = None


@dataclass(frozen=True)
class P0Justification:
    """The manifest-bound preregistered authority required for a P0 winner."""

    manifest_digest: str
    tie_break_rule_digest: str

    def __post_init__(self) -> None:
        for label, digest in (
            ("manifest_digest", self.manifest_digest),
            ("tie_break_rule_digest", self.tie_break_rule_digest),
        ):
            if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
                raise PathPolicyError(f"{label} must be a lowercase SHA-256")

    @classmethod
    def from_manifest(cls, manifest: EvaluationManifest) -> P0Justification:
        if not isinstance(manifest, EvaluationManifest):
            raise PathPolicyError("P0 justification requires an EvaluationManifest")
        return cls(
            manifest_digest=manifest.digest,
            tie_break_rule_digest=manifest.tie_break_rule_digest,
        )


@dataclass(frozen=True)
class TopologyEnvelope:
    """One fixed host resource envelope allowed for a disposable Z0 topology."""

    topology_id: str
    max_cpu_ms: int
    max_rss_bytes: int
    max_disk_bytes: int


@dataclass(frozen=True)
class TopologyMeasurement:
    """One observed topology footprint; None means unknown, not zero."""

    topology_id: str
    cpu_ms: int | None
    rss_bytes: int | None
    disk_bytes: int | None
    hard_failure_code: str | None = None


def select_path_policy(
    measurements: tuple[PathPolicyMeasurement, ...],
    *,
    evaluation_manifest: EvaluationManifest | None = None,
    p0_justification: P0Justification | None = None,
) -> str:
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
    failures = tuple(
        measurement.hard_failure_code
        for cases in by_policy.values()
        for measurement in cases.values()
        if measurement.hard_failure_code is not None
    )
    if failures:
        raise PathPolicyError(
            "constitutional failure dominates path-policy performance: "
            + ",".join(sorted(failures))
        )
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
    if winner == "P0" and not _has_manifest_bound_p0_justification(
        evaluation_manifest,
        p0_justification,
    ):
        raise PathPolicyError(
            "P0 cannot win on recall alone without a manifest-bound preregistered "
            "non-recall justification"
        )
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


def _has_manifest_bound_p0_justification(
    evaluation_manifest: EvaluationManifest | None,
    p0_justification: P0Justification | None,
) -> bool:
    return (
        isinstance(evaluation_manifest, EvaluationManifest)
        and isinstance(p0_justification, P0Justification)
        and p0_justification.manifest_digest == evaluation_manifest.digest
        and (
            p0_justification.tie_break_rule_digest
            == evaluation_manifest.tie_break_rule_digest
        )
    )


def select_topology(
    measurements: tuple[TopologyMeasurement, ...],
    envelopes: tuple[TopologyEnvelope, ...],
) -> str:
    """Select T0/T1 only with complete, known observations inside fixed budgets.

    A resource unknown, an overage, or a constitutional failure yields the
    typed NO_SAFE_TOPOLOGY result. Malformed evidence raises separately so a
    caller cannot mislabel a parser defect as a capacity result.
    """

    if not isinstance(measurements, tuple) or not isinstance(envelopes, tuple):
        raise TopologyError("topology measurements and envelopes must be tuples")
    by_topology: dict[str, TopologyMeasurement] = {}
    for measurement in measurements:
        if not isinstance(measurement, TopologyMeasurement):
            raise TopologyError("topology measurements must have closed shape")
        if measurement.topology_id not in TOPOLOGY_IDS:
            raise TopologyError("unknown topology")
        if measurement.topology_id in by_topology:
            raise TopologyError("duplicate topology measurement")
        by_topology[measurement.topology_id] = measurement
    by_envelope: dict[str, TopologyEnvelope] = {}
    for envelope in envelopes:
        if not isinstance(envelope, TopologyEnvelope):
            raise TopologyError("topology envelopes must have closed shape")
        if envelope.topology_id not in TOPOLOGY_IDS:
            raise TopologyError("unknown topology")
        if envelope.topology_id in by_envelope:
            raise TopologyError("duplicate topology envelope")
        if any(
            type(value) is not int or value < 0
            for value in (
                envelope.max_cpu_ms,
                envelope.max_rss_bytes,
                envelope.max_disk_bytes,
            )
        ):
            raise TopologyError("topology envelope values must be non-negative integers")
        by_envelope[envelope.topology_id] = envelope
    if set(by_topology) != TOPOLOGY_IDS or set(by_envelope) != TOPOLOGY_IDS:
        raise TopologyError("T0 and T1 both require measured envelopes")

    candidates: list[TopologyMeasurement] = []
    for topology_id in sorted(TOPOLOGY_IDS):
        measurement = by_topology[topology_id]
        envelope = by_envelope[topology_id]
        values = (measurement.cpu_ms, measurement.rss_bytes, measurement.disk_bytes)
        if measurement.hard_failure_code is not None:
            continue
        if any(type(value) is not int or value < 0 for value in values):
            continue
        assert isinstance(measurement.cpu_ms, int)
        assert isinstance(measurement.rss_bytes, int)
        assert isinstance(measurement.disk_bytes, int)
        if (
            measurement.cpu_ms > envelope.max_cpu_ms
            or measurement.rss_bytes > envelope.max_rss_bytes
            or measurement.disk_bytes > envelope.max_disk_bytes
        ):
            continue
        candidates.append(measurement)
    if not candidates:
        return NO_SAFE_TOPOLOGY
    candidates.sort(
        key=lambda item: (
            item.cpu_ms,
            item.rss_bytes,
            item.disk_bytes,
            item.topology_id,
        )
    )
    return candidates[0].topology_id


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
    if measurement.hard_failure_code is not None and (
        not isinstance(measurement.hard_failure_code, str)
        or not measurement.hard_failure_code
    ):
        raise PathPolicyError("hard_failure_code must be non-empty text or None")


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
