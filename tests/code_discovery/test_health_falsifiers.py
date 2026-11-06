"""Falsifiers for health claims that would otherwise bless plausible empties."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from experiments.code_discovery.health import (
    CLOSED_HEALTH_VALUES,
    HealthEvidence,
    evaluate_index_health,
)
from experiments.code_discovery.index_manifest import RepositorySpec


def _spec() -> RepositorySpec:
    return RepositorySpec(
        repository_id="mastermind",
        repository_name="mastermindx-market-intelligence/Mastermind",
        source_snapshot_root=Path("/host/snapshots/mastermind"),
        ref_label="master",
        commit_sha="a" * 40,
        included_prefixes=("engine/**",),
        excluded_globs=(),
        source_tree_digest="b" * 64,
    )


def _evidence(shard: Path, *, now: datetime) -> HealthEvidence:
    return HealthEvidence(
        indexed_commit_sha="a" * 40,
        source_tree_digest="b" * 64,
        shard_namespace=_spec().shard_namespace,
        shard_path=shard,
        expected_shard_sha256=hashlib.sha256(shard.read_bytes()).hexdigest(),
        generated_at=now,
        observed_at=now,
        coverage_complete=True,
        process_available=True,
        index_succeeded=True,
    )


def test_closed_health_values_cover_every_absence_falsifier() -> None:
    """A caller cannot mint an optimistic new health word at runtime."""

    assert CLOSED_HEALTH_VALUES == frozenset(
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


def test_corrupt_or_truncated_shard_refuses_healthy_empty_result(tmp_path: Path) -> None:
    """A 200/empty response cannot override observed shard byte corruption."""

    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    shard = tmp_path / "repository.zoekt"
    shard.write_bytes(b"complete disposable shard")
    evidence = _evidence(shard, now=now)
    healthy = evaluate_index_health(_spec(), evidence, freshness_budget_seconds=30)
    assert healthy.health == "healthy"
    assert healthy.coverage == "covered"

    shard.write_bytes(b"truncated")
    corrupt = evaluate_index_health(_spec(), evidence, freshness_budget_seconds=30)
    assert corrupt.health == "corrupt"
    assert corrupt.coverage == "covered"


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ({"process_available": False}, "process_unavailable"),
        ({"index_succeeded": False}, "index_failed"),
        ({"coverage_complete": False}, "coverage_unknown"),
        ({"indexed_commit_sha": "c" * 40}, "manifest_mismatch"),
        ({"source_tree_digest": "d" * 64}, "manifest_mismatch"),
    ],
)
def test_status_never_blesses_missing_or_mismatched_evidence(
    tmp_path: Path, override: dict[str, object], expected: str
) -> None:
    """Every selected repository/ref reports its specific non-healthy reason."""

    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    shard = tmp_path / "repository.zoekt"
    shard.write_bytes(b"healthy shard")
    evidence = _evidence(shard, now=now)
    evidence = HealthEvidence(**{**evidence.__dict__, **override})

    assert evaluate_index_health(_spec(), evidence, freshness_budget_seconds=30).health == expected


def test_age_over_budget_is_stale_with_exact_indexed_sha_preserved(tmp_path: Path) -> None:
    """Staleness reports source mismatch potential instead of erasing provenance."""

    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    shard = tmp_path / "repository.zoekt"
    shard.write_bytes(b"healthy shard")
    evidence = _evidence(
        shard, now=now - timedelta(seconds=31)
    )
    stale = evaluate_index_health(
        _spec(),
        evidence,
        freshness_budget_seconds=30,
        observed_at=now,
    )

    assert stale.health == "stale"
    assert stale.indexed_commit_sha == "a" * 40
    assert stale.freshness_seconds == 31.0
