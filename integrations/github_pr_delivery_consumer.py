"""Bounded delivery read consumer over the incumbent GitHub App transport.

No credential source, HTTP client, watcher, retry loop, Job, mutation or store is
created here. The installed host supplies its existing GitHubReviewAPI. Source
qualification is a separate existing-owner input, never PR-authored prose.
"""
from __future__ import annotations

import math
import time
from collections.abc import Callable
from datetime import datetime, timezone

from control_plane.github_pr_delivery_evidence import (
    pr_signature, project_delivery_evidence,
    validate_identity,
)
from control_plane.github_pr_lifecycle import DraftReadinessFacts
from integrations.github_review_api import GitHubReviewAPI


class GitHubPRDeliveryUnavailable(RuntimeError):
    """An incomplete live read must never be represented as qualified source."""


class GitHubPRDeliveryConsumer:
    def __init__(
        self, *, github: GitHubReviewAPI, repository: str,
        clock: Callable[[], float] = time.monotonic,
        observed_at: Callable[[], str] | None = None,
        ci_observations_enabled: bool = False,
    ) -> None:
        if type(github) is not GitHubReviewAPI:
            raise GitHubPRDeliveryUnavailable("DELIVERY_GITHUB_OWNER_UNBOUND")
        validate_identity(repository, 1)
        github._check(repository)
        if type(ci_observations_enabled) is not bool:
            raise GitHubPRDeliveryUnavailable("DELIVERY_CI_BINDING_INVALID")
        self._ci_enabled = ci_observations_enabled
        self._api = github
        self._repository = repository
        self._clock = clock
        self._observed_at = observed_at or (lambda: datetime.now(timezone.utc).isoformat())

    @property
    def repository(self) -> str:
        return self._repository

    def inspect(
        self, *, pull_number: int, expected_head_sha: str | None = None,
        max_pages: int = 3, time_budget_seconds: float = 30.0,
        qualification: DraftReadinessFacts | None = None,
        qualification_evidence_digest: str | None = None,
    ) -> dict:
        """One bounded read. It is not an atomic snapshot or release approval.

        Fixed numeric pages never follow response URLs. Per-request timeout,
        authentication, pacing and read retry remain owned by GitHubReviewAPI.
        The cooperative total budget is checked before and after each request;
        one existing in-flight request may consume its original bounded timeout.
        """
        validate_identity(self._repository, pull_number)
        if type(max_pages) is not int or not 1 <= max_pages <= 30:
            raise GitHubPRDeliveryUnavailable("DELIVERY_PAGE_BOUND_INVALID")
        if (type(time_budget_seconds) not in {int, float}
                or not math.isfinite(time_budget_seconds)
                or not 0 < time_budget_seconds <= 60):
            raise GitHubPRDeliveryUnavailable("DELIVERY_TIME_BOUND_INVALID")
        if expected_head_sha is not None:
            import re
            if type(expected_head_sha) is not str or re.fullmatch(r"[0-9a-f]{40}", expected_head_sha) is None:
                raise GitHubPRDeliveryUnavailable("DELIVERY_EXPECTED_HEAD_INVALID")
        route = self._api._check(self._repository, pull_number)
        repository_route = self._api._check(self._repository)
        deadline = self._clock() + time_budget_seconds

        def read(path: str) -> object:
            if self._clock() >= deadline:
                raise GitHubPRDeliveryUnavailable("DELIVERY_READ_BUDGET_EXHAUSTED")
            value = self._api._request("GET", path)
            if self._clock() >= deadline:
                raise GitHubPRDeliveryUnavailable("DELIVERY_READ_BUDGET_EXHAUSTED")
            return value

        before = read(route)
        identity = pr_signature(before, repository=self._repository, pull_number=pull_number)
        if expected_head_sha is not None and identity["head_sha"] != expected_head_sha:
            raise GitHubPRDeliveryUnavailable("DELIVERY_EXPECTED_HEAD_MOVED")
        head = identity["head_sha"]
        routes = {
            "files": (route + "/files", None, identity["changed_files"]),
            "issue_comments": (repository_route + f"/issues/{pull_number}/comments", None, identity["comments"]),
            "review_comments": (route + "/comments", None, identity["review_comments"]),
            "reviews": (route + "/reviews", None, None),
            "checks": (repository_route + f"/commits/{head}/check-runs?filter=latest", "check_runs", None),
            "statuses": (repository_route + f"/commits/{head}/statuses", None, None),
        }
        collections: dict[str, tuple[dict, ...]] = {}
        complete: dict[str, bool] = {}
        requests = 1
        for name, (endpoint, key, expected_count) in routes.items():
            if name in {"checks", "statuses"} and not self._ci_enabled:
                collections[name] = ()
                complete[name] = False
                continue
            rows: list[dict] = []
            exhausted = expected_count == 0
            for page in range(1, max_pages + 1):
                if exhausted:
                    break
                separator = "&" if "?" in endpoint else "?"
                raw = read(endpoint + f"{separator}per_page=100&page={page}")
                requests += 1
                total = None
                if key is not None:
                    if type(raw) is not dict or type(raw.get("total_count")) is not int or raw["total_count"] < 0:
                        raise GitHubPRDeliveryUnavailable("DELIVERY_CHECK_PAGE_INVALID")
                    total = raw["total_count"]
                    items = raw.get(key)
                else:
                    items = raw
                if type(items) is not list or len(items) > 100 or any(type(x) is not dict for x in items):
                    raise GitHubPRDeliveryUnavailable("DELIVERY_PAGE_INVALID")
                rows.extend(items)
                if total is not None and len(rows) >= total:
                    exhausted = len(rows) == total
                    break
                if len(items) < 100:
                    exhausted = total is None or len(rows) == total
                    break
                if expected_count is not None and len(rows) >= expected_count:
                    exhausted = len(rows) == expected_count
                    break
            # GitHub caps PR file results at 3000. Exact declared size is also
            # checked by the projection; a clipped 3000-row response is not full.
            collections[name] = tuple(rows)
            complete[name] = exhausted
        after = read(route)
        result = project_delivery_evidence(
            repository=self._repository, pull_number=pull_number,
            before=before, after=after, collections=collections, complete=complete,
            observed_at=self._observed_at(), qualification=qualification,
            qualification_evidence_digest=qualification_evidence_digest,
        )
        result["read_request_count"] = requests + 1
        result["ci_binding"] = "HOST_ENROLLED" if self._ci_enabled else "NOT_ENROLLED"
        result["observation_limitations"] = [
            "MULTI_REQUEST_OBSERVATION_NOT_ATOMIC",
            "FILE_LIST_IS_NOT_FULL_SOURCE_REVIEW",
            "CHECK_COUNTS_ARE_NOT_REQUIRED_CHECK_POLICY",
            "RESTRICTION_TEXT_IS_NOT_RELEASE_AUTHORITY",
        ]
        return result
