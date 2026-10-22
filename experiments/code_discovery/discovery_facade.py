"""Stable status-first facade over the host-only disposable Zoekt client."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from .discovery_contract import (
    CodeMatch,
    DiscoveryRequest,
    RepositoryIndexStatus,
    SearchResult,
)
from .index_manifest import IndexManifest, RepositorySpec
from .zoekt_client import RawZoektMatch, RawZoektResult


class DiscoveryFacadeError(ValueError):
    """The request cannot be resolved to current reviewed discovery coverage."""


class _SearchClient(Protocol):
    def search(
        self,
        query: str,
        *,
        limit: int,
        context_lines: int,
        case_sensitive: bool,
        regex: bool,
        repository_names: tuple[str, ...],
        refs: tuple[str, ...],
        path_prefixes: tuple[str, ...],
        languages: tuple[str, ...],
    ) -> RawZoektResult: ...


@dataclass(frozen=True)
class DiscoveryFacade:
    """Resolve logical identity before an engine result can reach the caller."""

    manifest: IndexManifest
    statuses: tuple[RepositoryIndexStatus, ...]
    client: _SearchClient
    freshness_budget_seconds: float

    def __post_init__(self) -> None:
        if self.freshness_budget_seconds <= 0:
            raise ValueError("freshness_budget_seconds must be positive")
        status_keys = [(status.repository_id, status.ref_label) for status in self.statuses]
        if len(status_keys) != len(set(status_keys)):
            raise ValueError("statuses must not duplicate a repository/ref row")

    def call(self, request: DiscoveryRequest) -> Mapping[str, object]:
        """Serve only the three closed discovery calls from the frozen contract."""

        selected = self._selected_specs(request.arguments)
        if request.tool == "list_repositories":
            return {
                "repositories": [
                    _repository_payload(spec)
                    for spec in sorted(selected, key=_repository_sort_key)
                ]
            }
        if request.tool == "index_status":
            return {
                "repository_statuses": [
                    _status_payload(status)
                    for status in self._statuses_for(selected)
                    if status is not None
                ]
            }
        if request.tool != "search_code":
            raise DiscoveryFacadeError(f"unrecognized closed discovery tool: {request.tool}")
        response = dict(_search_payload(self._search(request, selected)))
        response["coverage_summary"] = _coverage_summary(
            selected, _status_map(self.statuses)
        )
        return response

    def _search(
        self, request: DiscoveryRequest, selected: tuple[RepositorySpec, ...]
    ) -> SearchResult:
        arguments = request.arguments
        raw_result = self.client.search(
            _string_argument(arguments, "query"),
            limit=_integer_argument(arguments, "limit"),
            context_lines=_integer_argument(arguments, "context_lines"),
            case_sensitive=_boolean_argument(arguments, "case_sensitive"),
            regex=_boolean_argument(arguments, "regex"),
            repository_names=tuple(spec.repository_name for spec in selected),
            refs=tuple(spec.ref_label for spec in selected),
            path_prefixes=_string_sequence(arguments.get("path_prefixes", ()), "path_prefixes"),
            languages=_string_sequence(arguments.get("languages", ()), "languages"),
        )
        status_by_key = _status_map(self.statuses)
        matches: list[CodeMatch] = []
        for raw_match in raw_result.matches:
            mapped = _manifest_specs_for_raw_match(self.manifest.repositories, raw_match)
            if not mapped:
                raise DiscoveryFacadeError(
                    f"unmapped engine repository/ref: {raw_match.repository_name}"
                )
            if len(mapped) != 1:
                raise DiscoveryFacadeError(
                    f"ambiguous engine repository/ref: {raw_match.repository_name}"
                )
            spec = mapped[0]
            if spec not in selected:
                raise DiscoveryFacadeError("engine match is outside requested repository/ref")
            if not _within_requested_prefixes(
                raw_match.path,
                _string_sequence(arguments.get("path_prefixes", ()), "path_prefixes"),
            ):
                raise DiscoveryFacadeError("engine match is outside requested path prefix")
            if not _within_requested_languages(
                raw_match.language,
                _string_sequence(arguments.get("languages", ()), "languages"),
            ):
                raise DiscoveryFacadeError("engine match is outside requested language")
            status = status_by_key.get((spec.repository_id, spec.ref_label))
            matches.append(
                CodeMatch(
                    repository_id=spec.repository_id,
                    ref_label=spec.ref_label,
                    indexed_commit_sha=(
                        status.indexed_commit_sha
                        if status is not None and status.indexed_commit_sha is not None
                        else spec.commit_sha
                    ),
                    path=raw_match.path,
                    line_start=raw_match.line_start,
                    line_end=raw_match.line_end,
                    preview=raw_match.preview,
                    context_before=raw_match.context_before,
                    context_after=raw_match.context_after,
                    engine_score=None,
                )
            )
        matches.sort(
            key=lambda match: (
                match.repository_id,
                match.ref_label,
                match.path,
                match.line_start,
                match.line_end,
            )
        )
        statuses = tuple(
            status
            for status in self._statuses_for(selected)
            if status is not None
        )
        reasons = _negative_result_reasons(
            selected,
            status_by_key,
            raw_result,
            matches_present=bool(matches),
            freshness_budget_seconds=self.freshness_budget_seconds,
        )
        return SearchResult(
            matches=tuple(matches),
            repository_statuses=statuses,
            query_completed=raw_result.query_completed,
            truncated=raw_result.truncated,
            negative_result_authority=(
                "not_found_on_healthy_covered_ref"
                if not reasons
                else "unavailable"
            ),
            negative_result_reasons=tuple(sorted(reasons)),
        )

    def _selected_specs(self, arguments: Mapping[str, object]) -> tuple[RepositorySpec, ...]:
        repositories = _string_sequence(arguments.get("repositories", ()), "repositories")
        refs = _string_sequence(arguments.get("refs", ()), "refs")
        known_ids = {spec.repository_id for spec in self.manifest.repositories}
        unknown_ids = set(repositories) - known_ids
        if unknown_ids:
            raise DiscoveryFacadeError(
                f"unreviewed logical repository IDs: {sorted(unknown_ids)}"
            )
        known_refs = {spec.ref_label for spec in self.manifest.repositories}
        unknown_refs = set(refs) - known_refs
        if unknown_refs:
            raise DiscoveryFacadeError(f"unreviewed logical ref labels: {sorted(unknown_refs)}")
        selected = tuple(
            spec
            for spec in self.manifest.repositories
            if (not repositories or spec.repository_id in repositories)
            and (not refs or spec.ref_label in refs)
        )
        if not selected:
            raise DiscoveryFacadeError("request resolves to no reviewed repository/ref rows")
        return selected

    def _statuses_for(
        self, selected: Sequence[RepositorySpec]
    ) -> tuple[RepositoryIndexStatus | None, ...]:
        status_by_key = _status_map(self.statuses)
        return tuple(
            status_by_key.get((spec.repository_id, spec.ref_label))
            for spec in sorted(selected, key=_repository_sort_key)
        )


def _manifest_specs_for_raw_match(
    repositories: Sequence[RepositorySpec], raw_match: RawZoektMatch
) -> tuple[RepositorySpec, ...]:
    return tuple(
        spec
        for spec in repositories
        if spec.repository_name == raw_match.repository_name
        and spec.ref_label in raw_match.branches
    )


def _negative_result_reasons(
    selected: Sequence[RepositorySpec],
    statuses: Mapping[tuple[str, str], RepositoryIndexStatus],
    raw_result: RawZoektResult,
    *,
    matches_present: bool,
    freshness_budget_seconds: float,
) -> set[str]:
    reasons: set[str] = set()
    if matches_present:
        reasons.add("matches_present")
    if not raw_result.query_completed:
        reasons.add("query_incomplete")
    if raw_result.truncated:
        reasons.add("response_truncated")
    if raw_result.pinned_response_contract_digest is None:
        reasons.add("pinned_response_evidence_missing")
    for spec in selected:
        status = statuses.get((spec.repository_id, spec.ref_label))
        if status is None:
            reasons.add("coverage_missing")
            continue
        if status.health != "healthy":
            reasons.add(f"health_{status.health}")
        if status.coverage != "covered":
            reasons.add(f"coverage_{status.coverage}")
        if status.indexed_commit_sha != spec.commit_sha:
            reasons.add("indexed_sha_mismatch")
        if status.source_tree_digest != spec.source_tree_digest:
            reasons.add("source_tree_digest_mismatch")
        if (
            status.freshness_seconds is None
            or status.freshness_seconds > freshness_budget_seconds
        ):
            reasons.add("freshness_exceeded")
    return reasons


def _status_map(
    statuses: Sequence[RepositoryIndexStatus],
) -> dict[tuple[str, str], RepositoryIndexStatus]:
    return {(status.repository_id, status.ref_label): status for status in statuses}


def _within_requested_prefixes(path: str, prefixes: tuple[str, ...]) -> bool:
    return not prefixes or any(
        path == prefix or path.startswith(f"{prefix}/") for prefix in prefixes
    )


def _within_requested_languages(language: str, languages: tuple[str, ...]) -> bool:
    return not languages or language in languages


def _repository_sort_key(spec: RepositorySpec) -> tuple[str, str]:
    return spec.repository_id, spec.ref_label


def _repository_payload(spec: RepositorySpec) -> Mapping[str, object]:
    return {
        "repository_id": spec.repository_id,
        "repository_name": spec.repository_name,
        "ref_label": spec.ref_label,
        "commit_sha": spec.commit_sha,
        "source_tree_digest": spec.source_tree_digest,
    }


def _status_payload(status: RepositoryIndexStatus) -> Mapping[str, object]:
    return {
        "repository_id": status.repository_id,
        "ref_label": status.ref_label,
        "indexed_commit_sha": status.indexed_commit_sha,
        "source_tree_digest": status.source_tree_digest,
        "shard_namespace": status.shard_namespace,
        "health": status.health,
        "coverage": status.coverage,
        "generated_at": status.generated_at.isoformat(),
        "observed_at": status.observed_at.isoformat(),
        "freshness_seconds": status.freshness_seconds,
    }


def _coverage_summary(
    selected: Sequence[RepositorySpec],
    statuses: Mapping[tuple[str, str], RepositoryIndexStatus],
) -> Mapping[str, object]:
    missing = [
        {"repository_id": spec.repository_id, "ref_label": spec.ref_label}
        for spec in sorted(selected, key=_repository_sort_key)
        if (spec.repository_id, spec.ref_label) not in statuses
    ]
    return {
        "selected_count": len(selected),
        "observed_status_count": len(selected) - len(missing),
        "missing_statuses": missing,
    }


def _search_payload(result: SearchResult) -> Mapping[str, object]:
    return {
        "matches": [
            {
                "repository_id": match.repository_id,
                "ref_label": match.ref_label,
                "indexed_commit_sha": match.indexed_commit_sha,
                "path": match.path,
                "line_start": match.line_start,
                "line_end": match.line_end,
                "preview": match.preview,
                "context_before": list(match.context_before),
                "context_after": list(match.context_after),
                "engine_score": match.engine_score,
            }
            for match in result.matches
        ],
        "repository_statuses": [
            _status_payload(status) for status in result.repository_statuses
        ],
        "query_completed": result.query_completed,
        "truncated": result.truncated,
        "negative_result_authority": result.negative_result_authority,
        "negative_result_reasons": list(result.negative_result_reasons),
    }


def _string_sequence(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not all(isinstance(item, str) for item in value):
        raise DiscoveryFacadeError(f"{field} must come from validated immutable arguments")
    return value


def _string_argument(arguments: Mapping[str, object], field: str) -> str:
    value = arguments.get(field)
    if not isinstance(value, str):
        raise DiscoveryFacadeError(f"{field} must come from validated immutable arguments")
    return value


def _integer_argument(arguments: Mapping[str, object], field: str) -> int:
    value = arguments.get(field)
    if type(value) is not int:
        raise DiscoveryFacadeError(f"{field} must come from validated immutable arguments")
    return value


def _boolean_argument(arguments: Mapping[str, object], field: str) -> bool:
    value = arguments.get(field)
    if type(value) is not bool:
        raise DiscoveryFacadeError(f"{field} must come from validated immutable arguments")
    return value
