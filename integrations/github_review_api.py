"""Installation-token-scoped, endpoint-fenced GitHub REST adapter for PR review.

This is NOT a general GitHub client or a GitHub App credential issuer. It accepts
a host-owned installation token source, never a model-authored URL/credential,
and implements exactly the existing PullRequestReadPort,
ActorPermissionPort and ReviewTransportPort boundaries.
"""
from __future__ import annotations

import re
from typing import Protocol

import httpx

from control_plane.github_review_intent import PullRequestFacts
from control_plane.github_review_intent_ingress import (
    ExternalGitHubSourceFacts,
    PublishedReviewFacts,
    PublicationEffectUnknown,
)

_API = "https://api.github.com"
_REPO_RE = re.compile(r"\A[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}\Z")
_LOGIN_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9-]{0,38}(?:\[bot\])?\Z")
_SHA_RE = re.compile(r"\A[0-9a-f]{40}\Z")
_MAX_RESPONSE = 1 << 20
_MAX_REVIEW_PAGES = 10
_STATE_TO_EVENT = {"COMMENTED": "COMMENT", "CHANGES_REQUESTED": "REQUEST_CHANGES"}


class GitHubReviewAPIUnavailable(RuntimeError):
    """Typed refusal with deliberately opaque network/credential details."""


class InstallationTokenSource(Protocol):
    """Existing host-owned GitHub App credential issuer, never model-authored."""

    def token_for_installation(self, *, installation_id: int) -> str:
        """Return a fresh installation-scoped token or raise."""


def _obj(value: object) -> dict:
    if not isinstance(value, dict):
        raise GitHubReviewAPIUnavailable("GITHUB_RESPONSE_INVALID")
    return value


def _text(value: object, *, length: int) -> str:
    if not isinstance(value, str) or not value or len(value) > length:
        raise GitHubReviewAPIUnavailable("GITHUB_RESPONSE_INVALID")
    return value


def _repo_name(value: object) -> str:
    name = _text(value, length=201)
    if _REPO_RE.fullmatch(name) is None:
        raise GitHubReviewAPIUnavailable("GITHUB_RESPONSE_INVALID")
    return name


def _number(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise GitHubReviewAPIUnavailable("GITHUB_RESPONSE_INVALID")
    return value


class GitHubReviewAPI:
    """Minimal GitHub App REST port with an exact destination and identity fence."""

    def __init__(
        self,
        *,
        repository: str,
        installation_id: int,
        token_source: InstallationTokenSource,
        publisher_login: str,
        client: httpx.Client | None = None,
    ) -> None:
        self._repository = _repo_name(repository)
        self._installation_id = _number(installation_id)
        self._token_source = token_source
        if _LOGIN_RE.fullmatch(publisher_login) is None:
            raise GitHubReviewAPIUnavailable("GITHUB_PUBLISHER_IDENTITY_INVALID")
        self._publisher = publisher_login.casefold()
        self._client = client if client is not None else httpx.Client(
            timeout=httpx.Timeout(3.0), follow_redirects=False
        )

    def _request(self, method: str, path: str, *, payload: dict | None = None) -> object:
        if method not in {"GET", "POST"} or not path.startswith(
            f"/repos/{self._repository}/"
        ):
            raise GitHubReviewAPIUnavailable("GITHUB_ROUTE_NOT_ALLOWLISTED")
        token = self._token_source.token_for_installation(
            installation_id=self._installation_id
        )
        if not isinstance(token, str) or not token:
            raise GitHubReviewAPIUnavailable("GITHUB_INSTALLATION_TOKEN_UNAVAILABLE")
        try:
            response = self._client.request(
                method,
                _API + path,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                json=payload,
                follow_redirects=False,
                timeout=3.0,
            )
        except httpx.RequestError as exc:
            if method == "POST":
                raise PublicationEffectUnknown("GITHUB_REVIEW_EFFECT_UNKNOWN") from None
            raise GitHubReviewAPIUnavailable("GITHUB_READ_UNAVAILABLE") from None
        if response.status_code == 404 and method == "GET":
            raise GitHubReviewAPIUnavailable("GITHUB_READ_NOT_FOUND")
        if response.status_code >= 300:
            if method == "POST":
                # A 5xx may be applied; never blindly retry after ambiguity.
                if response.status_code >= 500:
                    raise PublicationEffectUnknown("GITHUB_REVIEW_EFFECT_UNKNOWN")
                raise GitHubReviewAPIUnavailable("GITHUB_REVIEW_SUBMIT_REFUSED")
            raise GitHubReviewAPIUnavailable("GITHUB_READ_REFUSED")
        if len(response.content) > _MAX_RESPONSE:
            if method == "POST":
                raise PublicationEffectUnknown("GITHUB_REVIEW_EFFECT_UNKNOWN")
            raise GitHubReviewAPIUnavailable("GITHUB_RESPONSE_OVER_BOUND")
        try:
            return response.json()
        except ValueError:
            if method == "POST":
                raise PublicationEffectUnknown("GITHUB_REVIEW_EFFECT_UNKNOWN") from None
            raise GitHubReviewAPIUnavailable("GITHUB_RESPONSE_INVALID") from None

    def _check(self, repository: str, pull_number: int | None = None) -> str:
        if repository != self._repository:
            raise GitHubReviewAPIUnavailable("GITHUB_REPOSITORY_OUT_OF_SCOPE")
        if pull_number is None:
            return f"/repos/{self._repository}"
        return f"/repos/{self._repository}/pulls/{_number(pull_number)}"

    def read_pull_request(self, *, repository: str, pull_number: int) -> PullRequestFacts:
        route = self._check(repository, pull_number)
        obj = _obj(self._request("GET", route))
        if _number(obj.get("number")) != pull_number:
            raise GitHubReviewAPIUnavailable("GITHUB_PULL_IDENTITY_MISMATCH")
        head = _obj(obj.get("head"))
        base = _obj(obj.get("base"))
        head_repo = _obj(head.get("repo"))
        base_repo = _obj(base.get("repo"))
        state = _text(obj.get("state"), length=12)
        sha = _text(head.get("sha"), length=40)
        base_sha = _text(base.get("sha"), length=40)
        if _SHA_RE.fullmatch(sha) is None or _SHA_RE.fullmatch(base_sha) is None:
            raise GitHubReviewAPIUnavailable("GITHUB_SHA_INVALID")
        if type(obj.get("draft")) is not bool:
            raise GitHubReviewAPIUnavailable("GITHUB_DRAFT_STATE_INVALID")
        title = obj.get("title")
        body = obj.get("body")
        if not isinstance(title, str) or not isinstance(body, (str, type(None))):
            raise GitHubReviewAPIUnavailable("GITHUB_PR_TEXT_INVALID")
        return PullRequestFacts(
            repository=repository, number=pull_number,
            state=state, draft=obj["draft"], head_sha=sha,
            head_repository=_repo_name(head_repo.get("full_name")),
            base_repository=_repo_name(base_repo.get("full_name")),
            base_sha=base_sha, title=title[:16000], body=(body or "")[:16000],
        )

    def read_external_source(
        self, *, repository: str, pull_number: int
    ) -> ExternalGitHubSourceFacts:
        """Current App-authenticated submitter identity, NOT actual builder.

        Only explicit external-review mode consumes these facts. Unlike
        webhook.user text, this identity is freshly read from GitHub.
        A source requiring native two-worker evidence must never use it.
        """
        route = self._check(repository, pull_number)
        obj = _obj(self._request("GET", route))
        if (
            _number(obj.get("number")) != pull_number
            or obj.get("state") != "open"
            or obj.get("draft") is not False
        ):
            raise GitHubReviewAPIUnavailable("GITHUB_EXTERNAL_SOURCE_UNAVAILABLE")
        head = _obj(obj.get("head"))
        base = _obj(obj.get("base"))
        if (
            _repo_name(_obj(head.get("repo")).get("full_name")) != repository
            or _repo_name(_obj(base.get("repo")).get("full_name")) != repository
        ):
            raise GitHubReviewAPIUnavailable("GITHUB_EXTERNAL_REPO_MISMATCH")
        sha = _text(head.get("sha"), length=40)
        if _SHA_RE.fullmatch(sha) is None:
            raise GitHubReviewAPIUnavailable("GITHUB_EXTERNAL_SHA_INVALID")
        submitter = _obj(obj.get("user"))
        login = _text(submitter.get("login"), length=50)
        if _LOGIN_RE.fullmatch(login) is None:
            raise GitHubReviewAPIUnavailable("GITHUB_EXTERNAL_LOGIN_INVALID")
        if login.casefold() == self._publisher:
            raise GitHubReviewAPIUnavailable("GITHUB_EXTERNAL_SELF_REVIEW_REFUSED")
        return ExternalGitHubSourceFacts(
            repository=repository, pull_number=pull_number,
            head_sha=sha, submitter_login=login,
            submitter_id=_number(submitter.get("id")),
        )

    def read_current_permission(self, *, repository: str, login: str) -> str | None:
        route = self._check(repository)
        if _LOGIN_RE.fullmatch(login) is None:
            return None
        try:
            obj = _obj(self._request(
                "GET", f"{route}/collaborators/{login}/permission"
            ))
        except GitHubReviewAPIUnavailable:
            return None
        user = obj.get("user")
        if not isinstance(user, dict) or not isinstance(user.get("login"), str):
            return None
        if user["login"].casefold() != login.casefold():
            return None
        permission = obj.get("permission")
        role_name = obj.get("role_name")
        # GitHub's legacy "permission" maps maintain->write and triage->read.
        # For standard roles, use the exact authenticated role_name so an
        # explicit maintain/admin policy can never silently weaken to write.
        if role_name in {"admin", "maintain", "write", "triage", "read"}:
            if role_name == "maintain" and permission == "write":
                return "maintain"
            if role_name == "triage" and permission == "read":
                return "triage"
            if role_name == permission:
                return role_name
        return permission if permission in {"admin", "write", "read", "none"} else None

    def submit_review(
        self,
        *,
        repository: str,
        pull_number: int,
        commit_id: str,
        event: str,
        body: str,
    ) -> str:
        route = self._check(repository, pull_number)
        if _SHA_RE.fullmatch(commit_id) is None:
            raise GitHubReviewAPIUnavailable("GITHUB_COMMIT_INVALID")
        if event not in {"COMMENT", "REQUEST_CHANGES"}:
            raise GitHubReviewAPIUnavailable("GITHUB_EVENT_REFUSED")
        if not isinstance(body, str) or not body or len(body) > 16000:
            raise GitHubReviewAPIUnavailable("GITHUB_REVIEW_BODY_INVALID")
        response = self._request(
            "POST", f"{route}/reviews",
            payload={"commit_id": commit_id, "event": event, "body": body},
        )
        # A 2xx is already an effect: a corrupt/absent review-id receipt is
        # not evidence of no effect and must never trigger a second POST.
        try:
            return str(_number(_obj(response).get("id")))
        except (GitHubReviewAPIUnavailable, ValueError, TypeError):
            raise PublicationEffectUnknown("GITHUB_REVIEW_EFFECT_UNKNOWN") from None

    def read_reviews(
        self, *, repository: str, pull_number: int, commit_id: str
    ) -> tuple[PublishedReviewFacts, ...]:
        route = self._check(repository, pull_number)
        if _SHA_RE.fullmatch(commit_id) is None:
            raise GitHubReviewAPIUnavailable("GITHUB_COMMIT_INVALID")
        result = []
        for page in range(1, _MAX_REVIEW_PAGES + 1):
            records = self._request(
                "GET", f"{route}/reviews?per_page=100&page={page}"
            )
            if not isinstance(records, list):
                raise GitHubReviewAPIUnavailable("GITHUB_RESPONSE_INVALID")
            for item in records:
                obj = _obj(item)
                user = _obj(obj.get("user"))
                login = user.get("login")
                # Never treat an unrelated actor's mimicked review as our own.
                if not isinstance(login, str) or login.casefold() != self._publisher:
                    continue
                review_sha = obj.get("commit_id")
                event = _STATE_TO_EVENT.get(obj.get("state"))
                review_body = obj.get("body")
                if review_sha != commit_id or event is None:
                    continue
                if not isinstance(review_body, str) or len(review_body) > 16000:
                    continue
                result.append(PublishedReviewFacts(
                    review_id=str(_number(obj.get("id"))),
                    commit_id=review_sha, event=event, body=review_body,
                ))
            if len(records) < 100:
                return tuple(result)
        # Never assume absent after an incomplete pagination window.
        raise GitHubReviewAPIUnavailable("GITHUB_REVIEW_READ_TRUNCATED")
