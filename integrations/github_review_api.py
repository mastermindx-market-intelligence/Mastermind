"""Installation-token-scoped, endpoint-fenced GitHub REST adapter for PR review.

This is NOT a general GitHub client or a GitHub App credential issuer. It accepts
a host-owned installation token source, never a model-authored URL/credential,
and implements exactly the existing PullRequestReadPort,
ActorPermissionPort and ReviewTransportPort boundaries.
"""
from __future__ import annotations

import re
import math
import time
from collections.abc import Callable
from email.utils import parsedate_to_datetime
from threading import RLock
from typing import Protocol

import httpx

from control_plane.github_review_intent import PullRequestFacts
from control_plane.github_review_intent_ingress import (
    ExpectedReviewPublisher,
    ExternalGitHubSourceFacts,
    PublishedReviewFacts,
    PublicationEffectUnknown,
    OpenPullRequestPage,
    ReviewSourceReadDeferred,
)
from integrations.github_review_http import BoundedResponseError, bounded_json

_API = "https://api.github.com"
_REPO_RE = re.compile(r"\A[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}\Z")
_LOGIN_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9-]{0,38}(?:\[bot\])?\Z")
_SHA_RE = re.compile(r"\A[0-9a-f]{40}\Z")
_MAX_RESPONSE = 1 << 20
_MAX_REVIEW_PAGES = 10
_REQUEST_BUDGET_SECONDS = 3.0
_READ_ATTEMPTS = 2
_READ_BACKOFF_SECONDS = 0.1
_TRANSIENT_READ_STATUSES = frozenset({500, 502, 503, 504})
_STATE_TO_EVENT = {"COMMENTED": "COMMENT", "CHANGES_REQUESTED": "REQUEST_CHANGES"}


class GitHubReviewAPIUnavailable(RuntimeError):
    """Typed refusal with deliberately opaque network/credential details."""


class GitHubReviewReadDeferred(ReviewSourceReadDeferred, GitHubReviewAPIUnavailable):
    """A shared GitHub source limit: the existing owner must defer the scan."""


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
        publisher_user_id: int,
        client: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self._repository = _repo_name(repository)
        self._installation_id = _number(installation_id)
        self._token_source = token_source
        if _LOGIN_RE.fullmatch(publisher_login) is None:
            raise GitHubReviewAPIUnavailable("GITHUB_PUBLISHER_IDENTITY_INVALID")
        if type(publisher_user_id) is not int or publisher_user_id <= 0:
            raise GitHubReviewAPIUnavailable("GITHUB_PUBLISHER_IDENTITY_INVALID")
        self._publisher_login = publisher_login
        self._publisher_user_id = publisher_user_id
        self._publisher = publisher_login.casefold()
        self._client = client if client is not None else httpx.Client(
            timeout=httpx.Timeout(3.0), follow_redirects=False
        )
        self._clock, self._sleep, self._wall_clock = clock, sleep, wall_clock
        self._defer_lock = RLock()
        # Transport pacing cache only; no queue, claim or retry authority.
        self._not_before = 0.0
        self._defer_code = "REVIEW_SOURCE_RATE_LIMITED"

    @property
    def repository(self) -> str:
        """Exact host-enrolled source repository; no credential is exposed."""
        return self._repository

    @property
    def installation_id(self) -> int:
        """Exact installation used for every authenticated source read."""
        return self._installation_id

    @property
    def publisher_login(self) -> str:
        """Validated immutable publication account for Executive return binding."""
        return self._publisher

    @property
    def publisher_user_id(self) -> int:
        """Host-configured GitHub App user id. Never taken from a webhook."""
        return self._publisher_user_id

    def expected_publisher(self) -> ExpectedReviewPublisher:
        """Both id and login the reconciliation guard must match."""
        return ExpectedReviewPublisher(
            user_id=self._publisher_user_id, login=self._publisher_login
        )

    def _check_pacing(self) -> None:
        with self._defer_lock:
            remaining = self._not_before - self._clock()
            if remaining > 0:
                raise GitHubReviewReadDeferred(
                    self._defer_code, retry_after_seconds=math.ceil(remaining)
                )

    def _request(self, method: str, path: str, *, payload: dict | None = None) -> object:
        if method not in {"GET", "POST"} or not path.startswith(
            f"/repos/{self._repository}/"
        ):
            raise GitHubReviewAPIUnavailable("GITHUB_ROUTE_NOT_ALLOWLISTED")
        self._check_pacing()
        try:
            token = self._token_source.token_for_installation(
                installation_id=self._installation_id
            )
        except Exception:
            raise GitHubReviewReadDeferred("REVIEW_SOURCE_AUTH_UNAVAILABLE") from None
        if not isinstance(token, str) or not token:
            raise GitHubReviewReadDeferred("REVIEW_SOURCE_AUTH_UNAVAILABLE")
        # Token issuance has its own bounded owner. Both GET attempts share this
        # one operation budget and the same credential/destination.
        deadline = self._clock() + _REQUEST_BUDGET_SECONDS
        attempts = _READ_ATTEMPTS if method == "GET" else 1
        for attempt in range(attempts):
            # Another in-flight call may have observed a limit during token
            # acquisition or our short backoff. Do not spend the second GET.
            self._check_pacing()
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise GitHubReviewAPIUnavailable("GITHUB_READ_BUDGET_EXHAUSTED")
            try:
                with self._client.stream(
                    method, _API + path,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github+json",
                        "Accept-Encoding": "identity",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    json=payload, follow_redirects=False, timeout=remaining,
                ) as response:
                    status = response.status_code
                    # A mutation is never retried, including transient responses.
                    if method == "POST" and status >= 300:
                        if status >= 500:
                            raise PublicationEffectUnknown("GITHUB_REVIEW_EFFECT_UNKNOWN")
                        raise GitHubReviewAPIUnavailable("GITHUB_REVIEW_SUBMIT_REFUSED")
                    if method == "GET":
                        limited = status == 429 or (status == 403 and (
                            response.headers.get("x-ratelimit-remaining") == "0"
                            or "retry-after" in response.headers
                        ))
                        if limited or (status in _TRANSIENT_READ_STATUSES
                                       and "retry-after" in response.headers):
                            self._defer(response, limited=limited)
                        if status in {401, 403}:
                            raise GitHubReviewReadDeferred("REVIEW_SOURCE_AUTH_UNAVAILABLE")
                        if status == 404:
                            raise GitHubReviewAPIUnavailable("GITHUB_READ_NOT_FOUND")
                        if status in _TRANSIENT_READ_STATUSES:
                            if attempt + 1 >= attempts:
                                raise GitHubReviewAPIUnavailable("GITHUB_READ_UNAVAILABLE")
                            # Close without consuming an untrusted error body.
                        elif status >= 300:
                            raise GitHubReviewAPIUnavailable("GITHUB_READ_REFUSED")
                        else:
                            return bounded_json(response, max_bytes=_MAX_RESPONSE,
                                                deadline=deadline, clock=self._clock)
                    else:
                        return bounded_json(response, max_bytes=_MAX_RESPONSE,
                                            deadline=deadline, clock=self._clock)
            except httpx.RequestError:
                if method == "POST":
                    raise PublicationEffectUnknown("GITHUB_REVIEW_EFFECT_UNKNOWN") from None
                if attempt + 1 >= attempts:
                    raise GitHubReviewAPIUnavailable("GITHUB_READ_UNAVAILABLE") from None
            except BoundedResponseError as exc:
                if method == "POST":
                    raise PublicationEffectUnknown("GITHUB_REVIEW_EFFECT_UNKNOWN") from None
                raise GitHubReviewAPIUnavailable(str(exc)) from None
            if deadline - self._clock() <= _READ_BACKOFF_SECONDS:
                raise GitHubReviewAPIUnavailable("GITHUB_READ_BUDGET_EXHAUSTED")
            self._sleep(_READ_BACKOFF_SECONDS)
        raise GitHubReviewAPIUnavailable("GITHUB_READ_UNAVAILABLE")

    def _defer(self, response: httpx.Response, *, limited: bool) -> None:
        """Retain server pacing within this enrolled adapter, never sleep a worker."""
        delay = 60.0
        retry = response.headers.get("retry-after", "")
        if retry.isascii() and retry.isdigit() and len(retry) <= 10:
            delay = max(1.0, float(retry))
        elif retry:
            try:
                delay = max(1.0, parsedate_to_datetime(retry).timestamp() - self._wall_clock())
            except (ValueError, TypeError, OverflowError):
                pass
        reset = response.headers.get("x-ratelimit-reset", "")
        if (response.headers.get("x-ratelimit-remaining") == "0" and
                reset.isascii() and reset.isdigit() and len(reset) <= 12):
            delay = max(delay, float(reset) - self._wall_clock())
        code = "REVIEW_SOURCE_RATE_LIMITED" if limited else "REVIEW_SOURCE_SERVER_DEFERRED"
        with self._defer_lock:
            self._not_before = max(self._not_before, self._clock() + delay)
            self._defer_code = code
            seconds = math.ceil(self._not_before - self._clock())
        raise GitHubReviewReadDeferred(code, retry_after_seconds=max(0, seconds))

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

    def list_open_pull_request_numbers(
        self, *, repository: str, page: int, per_page: int,
    ) -> OpenPullRequestPage:
        """Fixed scoped GET, bounded numeric pagination; never follow Link URLs."""
        route = self._check(repository)
        if (type(page) is not int or not 1 <= page <= 10000
                or type(per_page) is not int or not 1 <= per_page <= 100):
            raise GitHubReviewAPIUnavailable("GITHUB_PULL_PAGE_INVALID")
        rows = self._request(
            "GET", f"{route}/pulls?state=open&sort=created&direction=asc&per_page={per_page}&page={page}",
        )
        if type(rows) is not list or len(rows) > per_page:
            raise GitHubReviewAPIUnavailable("GITHUB_PULL_PAGE_INVALID")
        numbers = tuple(_number(_obj(row).get("number")) for row in rows)
        if len(set(numbers)) != len(numbers):
            raise GitHubReviewAPIUnavailable("GITHUB_PULL_PAGE_INVALID")
        # A full final page intentionally costs one more bounded GET to prove
        # exhaustion; response Link headers never select an authenticated URL.
        return OpenPullRequestPage(numbers=numbers, has_more=len(numbers) == per_page)

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
            or type(obj.get("draft")) is not bool
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
        except GitHubReviewReadDeferred:
            # A shared source limit is not a collaborator permission verdict.
            # Preserve it through HTTP so an authorized trigger is visibly
            # deferred and cannot fall back to static actor association.
            raise
        except GitHubReviewAPIUnavailable as exc:
            if str(exc) == "GITHUB_READ_NOT_FOUND":
                return None
            # Transport/schema failures remain unavailable, not evidence that
            # this actor was observed to have no permission.
            raise
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
                user = obj.get("user")
                if not isinstance(user, dict):
                    continue
                login = user.get("login")
                author_id = user.get("id")
                # Both fields come from the authenticated GET. A missing id is
                # not filled from the configured publisher, and a foreign
                # author is retained so reconciliation can reject it.
                if (
                    not isinstance(login, str)
                    or _LOGIN_RE.fullmatch(login) is None
                    or type(author_id) is not int
                    or author_id <= 0
                ):
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
                    author_user_id=author_id, author_login=login,
                ))
            if len(records) < 100:
                return tuple(result)
        # Never assume absent after an incomplete pagination window.
        raise GitHubReviewAPIUnavailable("GITHUB_REVIEW_READ_TRUNCATED")
