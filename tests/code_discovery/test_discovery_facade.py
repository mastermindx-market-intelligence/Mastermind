"""Status-first behavioral tests for the stable model-facing discovery facade."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from experiments.code_discovery.discovery_contract import (
    RepositoryIndexStatus,
    validate_discovery_request,
)
from experiments.code_discovery.discovery_facade import (
    DiscoveryFacade,
    DiscoveryFacadeError,
)
from experiments.code_discovery.index_manifest import IndexManifest, RepositorySpec
from experiments.code_discovery.zoekt_client import RawZoektMatch, RawZoektResult


class _Client:
    def __init__(self, result: RawZoektResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def search(self, query: str, **kwargs: object) -> RawZoektResult:
        self.calls.append({"query": query, **kwargs})
        return self.result


def _manifest() -> IndexManifest:
    return IndexManifest(
        schema_version="mastermind.codeintel_index_manifest.v1",
        repositories=(
            RepositorySpec(
                repository_id="mastermind",
                repository_name="mastermindx-market-intelligence/Mastermind",
                source_snapshot_root=Path("/host/snapshots/mastermind"),
                ref_label="master",
                commit_sha="a" * 40,
                included_prefixes=("engine/**",),
                excluded_globs=(),
                source_tree_digest="b" * 64,
            ),
            RepositorySpec(
                repository_id="macro",
                repository_name="mastermindx-market-intelligence/macro",
                source_snapshot_root=Path("/host/snapshots/macro"),
                ref_label="main",
                commit_sha="c" * 40,
                included_prefixes=("engine/**",),
                excluded_globs=(),
                source_tree_digest="d" * 64,
            ),
        ),
    )


def _status(spec: RepositorySpec, *, health: str = "healthy") -> RepositoryIndexStatus:
    observed = datetime(2026, 8, 30, 12, tzinfo=UTC)
    return RepositoryIndexStatus(
        repository_id=spec.repository_id,
        ref_label=spec.ref_label,
        indexed_commit_sha=spec.commit_sha,
        source_tree_digest=spec.source_tree_digest,
        shard_namespace=spec.shard_namespace,
        health=health,
        coverage="covered",
        generated_at=observed,
        observed_at=observed,
        freshness_seconds=1.0,
    )


def _raw_result(
    *,
    matches: tuple[RawZoektMatch, ...] = (),
    truncated: bool = False,
    pinned_response_contract_digest: str | None = "e" * 64,
) -> RawZoektResult:
    return RawZoektResult(
        matches=matches,
        total_match_count=len(matches),
        query_completed=True,
        truncated=truncated,
        pinned_response_contract_digest=pinned_response_contract_digest,
    )


def test_search_is_status_first_sorts_deterministically_and_attaches_exact_sha() -> None:
    """Engine metadata never substitutes for manifest-selected source provenance."""

    manifest = _manifest()
    client = _Client(
        _raw_result(
            matches=(
                RawZoektMatch(
                    repository_name="mastermindx-market-intelligence/macro",
                    branches=("main",),
                    language="python",
                    path="engine/z.py",
                    line_start=9,
                    line_end=9,
                    preview="MACRO",
                    context_before=(),
                    context_after=(),
                ),
                RawZoektMatch(
                    repository_name="mastermindx-market-intelligence/Mastermind",
                    branches=("master",),
                    language="python",
                    path="engine/a.py",
                    line_start=2,
                    line_end=2,
                    preview="MASTER",
                    context_before=(),
                    context_after=(),
                ),
            )
        )
    )
    facade = DiscoveryFacade(
        manifest=manifest,
        statuses=tuple(_status(spec) for spec in manifest.repositories),
        client=client,
        freshness_budget_seconds=30,
    )

    response = facade.call(
        validate_discovery_request(
            "search_code", {"query": "SENTINEL", "limit": 10, "context_lines": 0}
        )
    )

    assert [match["repository_id"] for match in response["matches"]] == [
        "macro",
        "mastermind",
    ]
    assert response["matches"][0]["indexed_commit_sha"] == "c" * 40
    assert response["matches"][1]["indexed_commit_sha"] == "a" * 40
    assert response["negative_result_authority"] == "unavailable"
    assert response["coverage_summary"] == {
        "selected_count": 2,
        "observed_status_count": 2,
        "missing_statuses": [],
    }
    assert client.calls == [
        {
            "query": "SENTINEL",
            "limit": 10,
            "context_lines": 0,
            "case_sensitive": False,
            "regex": False,
            "repository_names": (
                "mastermindx-market-intelligence/Mastermind",
                "mastermindx-market-intelligence/macro",
            ),
            "refs": ("master", "main"),
            "path_prefixes": (),
            "languages": (),
        }
    ]


def test_negative_authority_requires_every_selected_ref_to_be_healthy_complete_and_fresh() -> None:
    """A plausible empty result must remain explicitly non-authoritative on doubt."""

    manifest = _manifest()
    request = validate_discovery_request(
        "search_code",
        {
            "query": "absent",
            "repositories": ["mastermind"],
            "refs": ["master"],
        },
    )
    healthy = DiscoveryFacade(
        manifest=manifest,
        statuses=(_status(manifest.repositories[0]),),
        client=_Client(_raw_result(pinned_response_contract_digest="e" * 64)),
        freshness_budget_seconds=30,
    )
    stale = DiscoveryFacade(
        manifest=manifest,
        statuses=(_status(manifest.repositories[0], health="stale"),),
        client=_Client(_raw_result(pinned_response_contract_digest=None)),
        freshness_budget_seconds=30,
    )
    truncated = DiscoveryFacade(
        manifest=manifest,
        statuses=(_status(manifest.repositories[0]),),
        client=_Client(_raw_result(truncated=True)),
        freshness_budget_seconds=30,
    )

    assert healthy.call(request)["negative_result_authority"] == (
        "not_found_on_healthy_covered_ref"
    )
    stale_result = stale.call(request)
    assert stale_result["negative_result_authority"] == "unavailable"
    assert "health_stale" in stale_result["negative_result_reasons"]
    truncated_result = truncated.call(request)
    assert truncated_result["negative_result_authority"] == "unavailable"
    assert "response_truncated" in truncated_result["negative_result_reasons"]

    omitted = DiscoveryFacade(
        manifest=manifest,
        statuses=(),
        client=_Client(_raw_result()),
        freshness_budget_seconds=30,
    ).call(request)
    assert omitted["coverage_summary"] == {
        "selected_count": 1,
        "observed_status_count": 0,
        "missing_statuses": [{"repository_id": "mastermind", "ref_label": "master"}],
    }


def test_unreviewed_selection_and_unmapped_engine_match_fail_closed() -> None:
    """Logical IDs resolve only through the reviewed manifest, never a raw engine name."""

    manifest = _manifest()
    facade = DiscoveryFacade(
        manifest=manifest,
        statuses=tuple(_status(spec) for spec in manifest.repositories),
        client=_Client(
            _raw_result(
                matches=(
                    RawZoektMatch(
                        repository_name="unreviewed/private",
                        branches=("main",),
                        language="python",
                        path="secret.py",
                        line_start=1,
                        line_end=1,
                        preview="secret",
                        context_before=(),
                        context_after=(),
                    ),
                )
            )
        ),
        freshness_budget_seconds=30,
    )

    with pytest.raises(DiscoveryFacadeError, match="unreviewed"):
        facade.call(
            validate_discovery_request(
                "search_code", {"query": "secret", "repositories": ["does-not-exist"]}
            )
        )
    with pytest.raises(DiscoveryFacadeError, match="unmapped"):
        facade.call(validate_discovery_request("search_code", {"query": "secret"}))


def test_list_and_index_status_are_closed_non_search_calls() -> None:
    """The model can inspect reviewed status but cannot invoke index administration."""

    manifest = _manifest()
    client = _Client(_raw_result())
    facade = DiscoveryFacade(
        manifest=manifest,
        statuses=tuple(_status(spec) for spec in manifest.repositories),
        client=client,
        freshness_budget_seconds=30,
    )

    repositories = facade.call(validate_discovery_request("list_repositories", {}))
    status = facade.call(validate_discovery_request("index_status", {}))

    assert [item["repository_id"] for item in repositories["repositories"]] == [
        "macro",
        "mastermind",
    ]
    assert [item["health"] for item in status["repository_statuses"]] == [
        "healthy",
        "healthy",
    ]
    assert client.calls == []


def test_facade_refuses_returned_unselected_path_or_language_instead_of_discarding_it() -> None:
    """A server-side filter miss cannot become a quiet partial search."""

    manifest = _manifest()
    request = validate_discovery_request(
        "search_code",
        {
            "query": "needle",
            "repositories": ["mastermind"],
            "refs": ["master"],
            "path_prefixes": ["engine"],
            "languages": ["python"],
        },
    )
    wrong_path = RawZoektMatch(
        repository_name="mastermindx-market-intelligence/Mastermind",
        branches=("master",),
        language="python",
        path="docs/outside.py",
        line_start=1,
        line_end=1,
        preview="needle",
        context_before=(),
        context_after=(),
    )
    wrong_language = RawZoektMatch(
        repository_name="mastermindx-market-intelligence/Mastermind",
        branches=("master",),
        language="javascript",
        path="engine/outside.js",
        line_start=1,
        line_end=1,
        preview="needle",
        context_before=(),
        context_after=(),
    )
    for unexpected in (wrong_path, wrong_language):
        facade = DiscoveryFacade(
            manifest=manifest,
            statuses=(_status(manifest.repositories[0]),),
            client=_Client(_raw_result(matches=(unexpected,))),
            freshness_budget_seconds=30,
        )
        with pytest.raises(DiscoveryFacadeError, match="outside requested"):
            facade.call(request)


def test_empty_result_is_not_decision_eligible_without_pinned_response_evidence() -> None:
    """A hand-authored fixture is not proof that the pinned binary spoke this protocol."""

    manifest = _manifest()
    response = DiscoveryFacade(
        manifest=manifest,
        statuses=(_status(manifest.repositories[0]),),
        client=_Client(_raw_result(pinned_response_contract_digest=None)),
        freshness_budget_seconds=30,
    ).call(
        validate_discovery_request(
            "search_code",
            {"query": "absent", "repositories": ["mastermind"], "refs": ["master"]},
        )
    )

    assert response["negative_result_authority"] == "unavailable"
    assert "pinned_response_evidence_missing" in response["negative_result_reasons"]
