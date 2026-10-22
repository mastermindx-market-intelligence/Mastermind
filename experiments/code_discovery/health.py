"""Closed health evaluation for indexed source truth and plausible-empty safety."""

from __future__ import annotations

import hashlib
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from .discovery_contract import RepositoryIndexStatus
from .index_manifest import RepositorySpec


CLOSED_HEALTH_VALUES: Final = frozenset(
    {
        "healthy",
        "stale",
        "coverage_unknown",
        "index_failed",
        "corrupt",
        "process_unavailable",
        "manifest_mismatch",
    }
)


@dataclass(frozen=True)
class HealthEvidence:
    """Host-observed facts required before an index can assert healthy coverage."""

    indexed_commit_sha: str | None
    source_tree_digest: str | None
    shard_namespace: str | None
    shard_path: Path | None
    expected_shard_sha256: str | None
    generated_at: datetime
    observed_at: datetime
    coverage_complete: bool
    process_available: bool
    index_succeeded: bool


def evaluate_index_health(
    spec: RepositorySpec,
    evidence: HealthEvidence,
    *,
    freshness_budget_seconds: float,
    observed_at: datetime | None = None,
) -> RepositoryIndexStatus:
    """Return one closed status without allowing an empty response to self-bless."""

    if freshness_budget_seconds <= 0:
        raise ValueError("freshness_budget_seconds must be positive")
    current = observed_at or evidence.observed_at
    if current.tzinfo is None or evidence.generated_at.tzinfo is None:
        raise ValueError("health timestamps must be timezone-aware")
    freshness_seconds = max(
        0.0, (current.astimezone(UTC) - evidence.generated_at.astimezone(UTC)).total_seconds()
    )
    health = _health_value(spec, evidence, freshness_seconds, freshness_budget_seconds)
    return RepositoryIndexStatus(
        repository_id=spec.repository_id,
        ref_label=spec.ref_label,
        indexed_commit_sha=evidence.indexed_commit_sha,
        source_tree_digest=evidence.source_tree_digest,
        shard_namespace=evidence.shard_namespace,
        health=health,
        coverage="covered" if evidence.coverage_complete else "unknown",
        generated_at=evidence.generated_at,
        observed_at=current,
        freshness_seconds=freshness_seconds,
    )


def _health_value(
    spec: RepositorySpec,
    evidence: HealthEvidence,
    freshness_seconds: float,
    freshness_budget_seconds: float,
) -> str:
    if not evidence.process_available:
        return "process_unavailable"
    if not evidence.index_succeeded:
        return "index_failed"
    if not evidence.coverage_complete:
        return "coverage_unknown"
    if (
        evidence.indexed_commit_sha != spec.commit_sha
        or evidence.source_tree_digest != spec.source_tree_digest
        or evidence.shard_namespace != spec.shard_namespace
    ):
        return "manifest_mismatch"
    if not _shard_matches_digest(evidence.shard_path, evidence.expected_shard_sha256):
        return "corrupt"
    if freshness_seconds > freshness_budget_seconds:
        return "stale"
    return "healthy"


def _shard_matches_digest(path: Path | None, expected_sha256: str | None) -> bool:
    if (
        path is None
        or not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
    ):
        return False
    try:
        metadata = path.lstat()
    except OSError:
        return False
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        return False
    digest = hashlib.sha256()
    try:
        with path.open("rb") as shard:
            while block := shard.read(1024 * 1024):
                digest.update(block)
    except OSError:
        return False
    return digest.hexdigest() == expected_sha256
