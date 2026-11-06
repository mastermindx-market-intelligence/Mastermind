"""Source-bound review-risk reader on the incumbent GitHub App transport.

This binds the pure risk collector to the *existing* GitHubReviewAPI's
installation-scoped, bounded GET transport. There is no new credential,
httpx client, scheduler, webhook, review Job or publication capability.

The host must construct and qualify the GitHubReviewAPI before passing it here.
Do not expose this adapter to webhook/PR author supplied host configuration.
"""
from __future__ import annotations

from control_plane.github_review_risk_source import SourceFile, SourcePR
from integrations.github_review_api import GitHubReviewAPI


class GitHubReviewRiskReadUnavailable(RuntimeError):
    """Authenticated source data could not be represented safely."""


def _mapping(value: object) -> dict:
    if type(value) is not dict:
        raise GitHubReviewRiskReadUnavailable("PR_RISK_GITHUB_OBJECT_INVALID")
    return value


def _nonempty(value: object) -> str:
    if type(value) is not str or not value or len(value) > 512:
        raise GitHubReviewRiskReadUnavailable("PR_RISK_GITHUB_TEXT_INVALID")
    return value


def _natural(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 10_000_000:
        raise GitHubReviewRiskReadUnavailable("PR_RISK_GITHUB_COUNT_INVALID")
    return value


class GitHubReviewRiskReader:
    """Bind one trusted installation owner to risk source read methods.

    GitHubReviewAPI._request is intentionally reused rather than introducing
    a second GitHub transport. Its repository fence, host token and GET
    response-size/rate-limit contract remain in force.
    """

    def __init__(self, *, api: GitHubReviewAPI, repository: str) -> None:
        if type(api) is not GitHubReviewAPI:
            raise GitHubReviewRiskReadUnavailable("PR_RISK_GITHUB_API_UNBOUND")
        if type(repository) is not str:
            raise GitHubReviewRiskReadUnavailable("PR_RISK_REPOSITORY_UNBOUND")
        # Reuse incumbent canonical route constructor and its identity guard.
        api._check(repository)
        self._api = api
        self._repository = repository

    def _route(self, repository: str, pull_number: int) -> str:
        if repository != self._repository or type(pull_number) is not int:
            raise GitHubReviewRiskReadUnavailable("PR_RISK_IDENTITY_MISMATCH")
        return self._api._check(repository, pull_number)

    def read_pr_risk_source(self, *, repository: str, pull_number: int) -> SourcePR:
        route = self._route(repository, pull_number)
        obj = _mapping(self._api._request("GET", route))
        if type(obj.get("number")) is not int or obj["number"] != pull_number:
            raise GitHubReviewRiskReadUnavailable("PR_RISK_PULL_MISMATCH")
        head = _mapping(obj.get("head"))
        base = _mapping(obj.get("base"))
        head_repo = _mapping(head.get("repo"))
        base_repo = _mapping(base.get("repo"))
        state = _nonempty(obj.get("state"))
        if state not in ("open", "closed"):
            raise GitHubReviewRiskReadUnavailable("PR_RISK_STATE_INVALID")
        draft = obj.get("draft")
        if type(draft) is not bool:
            raise GitHubReviewRiskReadUnavailable("PR_RISK_DRAFT_INVALID")
        return SourcePR(
            repository=repository,
            pull_number=pull_number,
            head_sha=_nonempty(head.get("sha")),
            base_sha=_nonempty(base.get("sha")),
            head_repository=_nonempty(head_repo.get("full_name")),
            base_repository=_nonempty(base_repo.get("full_name")),
            open=state == "open",
            draft=draft,
            changed_files=_natural(obj.get("changed_files")),
            additions=_natural(obj.get("additions")),
            deletions=_natural(obj.get("deletions")),
        )

    def read_pr_risk_file_page(
        self, *, repository: str, pull_number: int, page: int, per_page: int
    ) -> tuple[SourceFile, ...]:
        route = self._route(repository, pull_number)
        if (type(page) is not int or not 1 <= page <= 3
                or type(per_page) is not int or per_page != 100):
            raise GitHubReviewRiskReadUnavailable("PR_RISK_PAGE_INVALID")
        # Only this narrow fixed route, no URL input, redirects or pagination
        # links. Existing _request enforces GitHub App token and bounded GETs.
        response = self._api._request(
            "GET", f"{route}/files?per_page={per_page}&page={page}",
        )
        if type(response) is not list or len(response) > per_page:
            raise GitHubReviewRiskReadUnavailable("PR_RISK_FILES_INVALID")
        result: list[SourceFile] = []
        for item in response:
            f = _mapping(item)
            filename = _nonempty(f.get("filename"))
            status = _nonempty(f.get("status"))
            previous = f.get("previous_filename")
            if previous is not None:
                previous = _nonempty(previous)
            patch = f.get("patch")
            if patch is not None and type(patch) is not str:
                raise GitHubReviewRiskReadUnavailable("PR_RISK_PATCH_INVALID")
            result.append(SourceFile(
                filename=filename,
                status=status,
                additions=_natural(f.get("additions")),
                deletions=_natural(f.get("deletions")),
                previous_filename=previous,
                patch_available=patch is not None,
            ))
        return tuple(result)
