"""Host-bound, seatless Hermes GitHub App source/PR/comment consumer.

The installed Hermes host supplies the session and existing source custody.
There is no model-selected GitHub account, repo, installation, token, API URL,
lease, queue or runtime grant. A failed or ambiguous write never auto-retries.
"""
from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from threading import RLock
from urllib.parse import quote

import httpx

from integrations.github_review_app_token import (
    AUTHORING_PERMISSIONS, GitHubAppInstallationTokens,
)
from integrations.github_review_http import bounded_json

SCHEMA = "mastermind.hermes_github_app.v1"
_REPO = re.compile(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}\Z")
_ROLE = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_OPERATION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_BRANCH = re.compile(r"hermes/[a-z0-9][a-z0-9._/-]{0,99}\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_APP_BOT = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,95}\[bot\]\Z")
_PATH = re.compile(r"[A-Za-z0-9_./-]{1,240}\Z")
_REQUEST = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}\Z")
_LIMIT = 1 << 18
_API = "https://api.github.com"


class GitHubBotRefused(RuntimeError):
    """Proven local refusal, with no attempted GitHub write."""


class GitHubBotUnavailable(RuntimeError):
    """A read cannot be verified, so the requested write was not attempted."""


class GitHubBotEffectUnknown(RuntimeError):
    """A GitHub modifying request may have taken effect; do not replay."""


def _clean_path(value: str) -> bool:
    return (type(value) is str and _PATH.fullmatch(value) is not None
            and not value.startswith(("/", "."))
            and "//" not in value and "/./" not in value
            and ".." not in value and not value.endswith(("/", ".")))


def _current(guard: Callable[[], bool]) -> bool:
    try:
        return guard() is True
    except Exception:
        return False


@dataclass(frozen=True)
class HostGitHubSession:
    """One original Hermes session and operation, composed by its host owner."""

    profile_id: str
    role: str
    session_id: str
    operation_id: str
    repository: str
    branch: str
    base_branch: str
    base_sha: str
    installation_id: int
    app_bot_login: str
    allowed_path_prefixes: tuple[str, ...]
    allowed_issue_numbers: frozenset[int]
    token_source: GitHubAppInstallationTokens
    currentness_guard: Callable[[], bool]

    def __post_init__(self) -> None:
        if (not isinstance(self.profile_id, str) or not self.profile_id
                or not isinstance(self.session_id, str)
                or not 0 < len(self.session_id) <= 128
                or type(self.role) is not str
                or _ROLE.fullmatch(self.role) is None
                or type(self.operation_id) is not str
                or _OPERATION.fullmatch(self.operation_id) is None
                or type(self.repository) is not str
                or _REPO.fullmatch(self.repository) is None
                or type(self.branch) is not str
                or _BRANCH.fullmatch(self.branch) is None
                or ".." in self.branch or "//" in self.branch
                or self.branch.endswith(("/", ".lock"))
                or self.base_branch not in ("main", "master")
                or type(self.base_sha) is not str
                or _SHA.fullmatch(self.base_sha) is None
                or type(self.installation_id) is not int or self.installation_id <= 0
                or type(self.app_bot_login) is not str
                or _APP_BOT.fullmatch(self.app_bot_login) is None):
            raise GitHubBotRefused("GITHUB_HOST_BINDING_INVALID")
        if (not isinstance(self.token_source, GitHubAppInstallationTokens)
                or self.token_source._repository != self.repository
                or self.token_source._installation_id != self.installation_id
                or self.token_source._permissions != AUTHORING_PERMISSIONS):
            raise GitHubBotRefused("GITHUB_HOST_TOKEN_SCOPE_INVALID")
        if (not callable(self.currentness_guard)
                or not _current(self.currentness_guard)
                or not isinstance(self.allowed_path_prefixes, tuple)
                or not self.allowed_path_prefixes
                or any(type(prefix) is not str
                       or not _clean_path(prefix.rstrip("/"))
                       for prefix in self.allowed_path_prefixes)
                or not isinstance(self.allowed_issue_numbers, frozenset)
                or any(type(number) is not int or number < 1
                       for number in self.allowed_issue_numbers)):
            raise GitHubBotRefused("GITHUB_HOST_GRANT_INVALID")

    @property
    def audit_marker(self) -> str:
        session_hash = hashlib.sha256(self.session_id.encode()).hexdigest()[:16]
        return (f"mmx-hermes-app role={self.role} "
                f"operation={self.operation_id} session-sha256={session_hash}")

    def path_is_allowed(self, path: str) -> bool:
        return _clean_path(path) and any(
            path == prefix or (prefix.endswith("/") and path.startswith(prefix))
            for prefix in self.allowed_path_prefixes
        )


class HermesGitHubApp:
    """Fixed-destination REST adapter; shared App credentials never enter tool output."""

    def __init__(self, binding: HostGitHubSession,
                 *, client: httpx.Client | None = None,
                 clock: Callable[[], float] = time.monotonic):
        if not isinstance(binding, HostGitHubSession):
            raise GitHubBotRefused("GITHUB_HOST_BINDING_INVALID")
        self.binding = binding
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(4.0), follow_redirects=False,
        )
        self._clock = clock
        # One host/session lock, not a cross-host lease or source owner.
        self._lock = RLock()

    def _check(self) -> None:
        if not _current(self.binding.currentness_guard):
            raise GitHubBotRefused("GITHUB_SESSION_REVOKED")

    def _read_or_write(self, method: str, path: str, *,
                       payload: dict | None = None,
                       missing: bool = False) -> object:
        self._check()
        try:
            token = self.binding.token_source.token_for_installation(
                installation_id=self.binding.installation_id,
            )
        except Exception:
            raise GitHubBotUnavailable("GITHUB_APP_TOKEN_UNAVAILABLE") from None
        full_path = "/repos/" + self.binding.repository + path
        start = self._clock()
        try:
            with self._client.stream(
                method, _API + full_path,
                headers={"Authorization": "Bearer " + token,
                         "Accept": "application/vnd.github+json",
                         "Accept-Encoding": "identity",
                         "X-GitHub-Api-Version": "2026-03-10"},
                json=payload, follow_redirects=False, timeout=4.0,
            ) as response:
                if missing and method == "GET" and response.status_code == 404:
                    return None
                if response.status_code not in ((200,) if method == "GET"
                         else (200, 201)):
                    if method != "GET":
                        raise GitHubBotEffectUnknown("GITHUB_WRITE_RESPONSE_UNVERIFIED")
                    raise GitHubBotUnavailable("GITHUB_READ_RESPONSE_UNVERIFIED")
                result = bounded_json(
                    response, max_bytes=_LIMIT,
                    deadline=start + 8.0, clock=self._clock,
                )
        except (GitHubBotEffectUnknown, GitHubBotUnavailable):
            raise
        except Exception:
            if method != "GET":
                raise GitHubBotEffectUnknown("GITHUB_WRITE_EFFECT_UNKNOWN") from None
            raise GitHubBotUnavailable("GITHUB_READ_UNAVAILABLE") from None
        # If a write succeeded but the role was revoked in flight, its effect
        # cannot be relabelled as a no-op. Keep the original operation fenced.
        if not _current(self.binding.currentness_guard):
            if method != "GET":
                raise GitHubBotEffectUnknown("GITHUB_GRANT_CHANGED_DURING_WRITE")
            raise GitHubBotUnavailable("GITHUB_GRANT_CHANGED_DURING_READ")
        return result

    def _ref(self, branch: str, *, missing: bool = False) -> str | None:
        result = self._read_or_write(
            "GET", "/git/ref/heads/" + quote(branch, safe="/"),
            missing=missing,
        )
        if result is None:
            return None
        if (not isinstance(result, dict) or not isinstance(result.get("object"), dict)
                or type(result["object"].get("sha")) is not str
                or _SHA.fullmatch(result["object"]["sha"]) is None):
            raise GitHubBotUnavailable("GITHUB_REF_UNVERIFIED")
        return result["object"]["sha"]

    def status(self) -> dict:
        head = self._ref(self.binding.branch, missing=True)
        return {"schema": SCHEMA, "state": "AVAILABLE",
                "repository": self.binding.repository,
                "branch": self.binding.branch, "head": head,
                "role": self.binding.role,
                "operation": self.binding.operation_id}

    def create_branch(self) -> dict:
        with self._lock:
            base = self._ref(self.binding.base_branch)
            if base != self.binding.base_sha:
                raise GitHubBotRefused("GITHUB_BASE_MOVED")
            existing = self._ref(self.binding.branch, missing=True)
            if existing is not None:
                if existing != base:
                    raise GitHubBotRefused("GITHUB_BRANCH_ALREADY_MODIFIED")
                return {"schema": SCHEMA, "state": "EXISTS", "head": existing}
            result = self._read_or_write("POST", "/git/refs", payload={
                "ref": "refs/heads/" + self.binding.branch, "sha": base,
            })
            if (not isinstance(result, dict)
                    or result.get("ref") != "refs/heads/" + self.binding.branch
                    or (result.get("object") or {}).get("sha") != base):
                raise GitHubBotEffectUnknown("GITHUB_BRANCH_CREATION_UNVERIFIED")
            return {"schema": SCHEMA, "state": "CREATED", "head": base}

    def commit_file(self, *, expected_head: str, path: str,
                    content: str, message: str) -> dict:
        if (type(expected_head) is not str
                or _SHA.fullmatch(expected_head) is None
                or not self.binding.path_is_allowed(path)
                or type(content) is not str or len(content.encode("utf-8")) > 131072
                or type(message) is not str or not 1 <= len(message) <= 180
                or "\n" in message):
            raise GitHubBotRefused("GITHUB_FILE_INPUT_REFUSED")
        with self._lock:
            if self._ref(self.binding.branch) != expected_head:
                raise GitHubBotRefused("GITHUB_BRANCH_HEAD_CHANGED")
            original = self._read_or_write("GET", "/git/commits/" + expected_head)
            if (not isinstance(original, dict)
                    or not isinstance(original.get("tree"), dict)
                    or _SHA.fullmatch(original["tree"].get("sha", "")) is None):
                raise GitHubBotUnavailable("GITHUB_BASE_TREE_UNVERIFIED")
            tree = self._read_or_write("POST", "/git/trees", payload={
                "base_tree": original["tree"]["sha"],
                "tree": [{"path": path, "mode": "100644", "type": "blob",
                          "content": content}],
            })
            if (not isinstance(tree, dict)
                    or _SHA.fullmatch(tree.get("sha", "")) is None):
                raise GitHubBotEffectUnknown("GITHUB_TREE_UNVERIFIED")
            commit = self._read_or_write("POST", "/git/commits", payload={
                "message": (message + "\n\n" + self.binding.audit_marker
                            + "\nHermes-Role: " + self.binding.role
                            + "\nHermes-Operation: " + self.binding.operation_id),
                "tree": tree["sha"], "parents": [expected_head],
            })
            if (not isinstance(commit, dict)
                    or _SHA.fullmatch(commit.get("sha", "")) is None):
                raise GitHubBotEffectUnknown("GITHUB_COMMIT_UNVERIFIED")
            committed_sha = commit["sha"]
            ref = self._read_or_write(
                "PATCH", "/git/refs/heads/" + quote(self.binding.branch, safe="/"),
                payload={"sha": committed_sha, "force": False},
            )
            if (not isinstance(ref, dict)
                    or (ref.get("object") or {}).get("sha") != committed_sha):
                raise GitHubBotEffectUnknown("GITHUB_BRANCH_UPDATE_UNVERIFIED")
            return {"schema": SCHEMA, "state": "COMMITTED",
                    "head": committed_sha, "path": path}

    def _prs(self) -> list:
        owner = self.binding.repository.split("/", 1)[0]
        query = ("?state=all&per_page=100&head="
                 + quote(owner + ":" + self.binding.branch, safe=""))
        result = self._read_or_write("GET", "/pulls" + query)
        if not isinstance(result, list) or len(result) >= 100:
            raise GitHubBotUnavailable("GITHUB_PR_LIST_UNVERIFIED")
        return result

    def create_pr(self, *, expected_head: str, title: str, body: str) -> dict:
        if (type(expected_head) is not str
                or _SHA.fullmatch(expected_head) is None
                or type(title) is not str or not 4 <= len(title) <= 140
                or type(body) is not str or len(body) > 16000):
            raise GitHubBotRefused("GITHUB_PR_INPUT_REFUSED")
        with self._lock:
            if self._ref(self.binding.branch) != expected_head:
                raise GitHubBotRefused("GITHUB_BRANCH_HEAD_CHANGED")
            for pr in self._prs():
                if not isinstance(pr, dict):
                    raise GitHubBotUnavailable("GITHUB_PR_LIST_UNVERIFIED")
                expected_marker = "<!-- " + self.binding.audit_marker + " -->"
                if (pr.get("state") != "open"
                        or type(pr.get("number")) is not int
                        or not isinstance(pr.get("user"), dict)
                        or pr["user"].get("login") != self.binding.app_bot_login
                        or not isinstance(pr.get("head"), dict)
                        or pr["head"].get("ref") != self.binding.branch
                        or pr["head"].get("sha") != expected_head
                        or not isinstance(pr["head"].get("repo"), dict)
                        or pr["head"]["repo"].get("full_name") != self.binding.repository
                        or not isinstance(pr.get("base"), dict)
                        or pr["base"].get("ref") != self.binding.base_branch
                        or expected_marker not in (pr.get("body") or "")):
                    raise GitHubBotRefused("GITHUB_BRANCH_PR_OWNED_BY_OTHER")
                return {"schema": SCHEMA, "state": "EXISTS",
                        "number": pr["number"], "url": pr.get("html_url")}
            result = self._read_or_write("POST", "/pulls", payload={
                "head": self.binding.branch, "base": self.binding.base_branch,
                "title": title,
                "body": body + "\n\n<!-- " + self.binding.audit_marker + " -->",
                "draft": False,
            })
            if (not isinstance(result, dict)
                    or type(result.get("number")) is not int
                    or result["number"] < 1
                    or not isinstance(result.get("user"), dict)
                    or result["user"].get("login") != self.binding.app_bot_login
                    or not isinstance(result.get("head"), dict)
                    or result["head"].get("sha") != expected_head):
                raise GitHubBotEffectUnknown("GITHUB_PR_CREATE_UNVERIFIED")
            return {"schema": SCHEMA, "state": "CREATED",
                    "number": result["number"], "url": result.get("html_url")}

    def _authorized_issue(self, issue_number: int) -> None:
        if issue_number in self.binding.allowed_issue_numbers:
            return
        pr = self._read_or_write("GET", "/pulls/" + str(issue_number), missing=True)
        expected_marker = "<!-- " + self.binding.audit_marker + " -->"
        if (not isinstance(pr, dict) or pr.get("state") != "open"
                or not isinstance(pr.get("user"), dict)
                or pr["user"].get("login") != self.binding.app_bot_login
                or not isinstance(pr.get("head"), dict)
                or pr["head"].get("ref") != self.binding.branch
                or not isinstance(pr["head"].get("repo"), dict)
                or pr["head"]["repo"].get("full_name") != self.binding.repository
                or not isinstance(pr.get("base"), dict)
                or pr["base"].get("ref") != self.binding.base_branch
                or expected_marker not in (pr.get("body") or "")):
            raise GitHubBotRefused("GITHUB_COMMENT_TARGET_NOT_GRANTED")

    def find_comment(self, *, issue_number: int, request_id: str) -> dict | None:
        if (type(issue_number) is not int or issue_number < 1
                or type(request_id) is not str
                or _REQUEST.fullmatch(request_id) is None):
            raise GitHubBotRefused("GITHUB_COMMENT_INPUT_REFUSED")
        self._authorized_issue(issue_number)
        marker = "<!-- " + self.binding.audit_marker + " request=" + request_id + " -->"
        for page in range(1, 5):
            result = self._read_or_write(
                "GET", "/issues/" + str(issue_number)
                + "/comments?per_page=100&page=" + str(page),
            )
            if not isinstance(result, list):
                raise GitHubBotUnavailable("GITHUB_COMMENTS_UNVERIFIED")
            found = [x for x in result if isinstance(x, dict)
                     and isinstance(x.get("user"), dict)
                     and x["user"].get("login") == self.binding.app_bot_login
                     and marker in (x.get("body") or "")]
            if len(found) > 1:
                raise GitHubBotUnavailable("GITHUB_DUPLICATE_COMMENT_AMBIGUOUS")
            if found:
                return {"schema": SCHEMA, "state": "EXISTS",
                        "id": found[0].get("id"), "url": found[0].get("html_url")}
            if len(result) < 100:
                return None
        raise GitHubBotUnavailable("GITHUB_COMMENT_PAGINATION_UNVERIFIED")

    def create_comment(self, *, issue_number: int, request_id: str,
                       body: str) -> dict:
        if type(body) is not str or not body.strip() or len(body) > 16000:
            raise GitHubBotRefused("GITHUB_COMMENT_INPUT_REFUSED")
        with self._lock:
            found = self.find_comment(
                issue_number=issue_number, request_id=request_id,
            )
            if found:
                return found
            marker = "<!-- " + self.binding.audit_marker + " request=" + request_id + " -->"
            result = self._read_or_write(
                "POST", "/issues/" + str(issue_number) + "/comments",
                payload={"body": body + "\n\n" + marker},
            )
            if (not isinstance(result, dict)
                    or type(result.get("id")) is not int or result["id"] < 1
                    or not isinstance(result.get("user"), dict)
                    or result["user"].get("login") != self.binding.app_bot_login
                    or marker not in (result.get("body") or "")):
                raise GitHubBotEffectUnknown("GITHUB_COMMENT_CREATE_UNVERIFIED")
            return {"schema": SCHEMA, "state": "CREATED",
                    "id": result["id"], "url": result.get("html_url")}

    def perform(self, arguments: Mapping[str, object]) -> dict:
        """Closed action surface. The model never supplies a repo, app or token."""
        if not isinstance(arguments, dict):
            raise GitHubBotRefused("GITHUB_ARGUMENTS_INVALID")
        action = arguments.get("action")
        allowed = {
            "status": {"action"},
            "branch_create": {"action"},
            "file_commit": {"action", "expected_head", "path", "content", "message"},
            "pr_create": {"action", "expected_head", "title", "body"},
            "comment_find": {"action", "issue_number", "request_id"},
            "comment_create": {"action", "issue_number", "request_id", "body"},
        }
        if type(action) is not str or action not in allowed or set(arguments) != allowed[action]:
            raise GitHubBotRefused("GITHUB_ACTION_ARGUMENTS_REFUSED")
        if action == "status":
            return self.status()
        if action == "branch_create":
            return self.create_branch()
        if action == "file_commit":
            return self.commit_file(
                expected_head=arguments["expected_head"], path=arguments["path"],
                content=arguments["content"], message=arguments["message"],
            )
        if action == "pr_create":
            return self.create_pr(
                expected_head=arguments["expected_head"], title=arguments["title"],
                body=arguments["body"],
            )
        if action == "comment_find":
            return self.find_comment(
                issue_number=arguments["issue_number"],
                request_id=arguments["request_id"],
            ) or {"schema": SCHEMA, "state": "NOT_FOUND"}
        return self.create_comment(
            issue_number=arguments["issue_number"],
            request_id=arguments["request_id"], body=arguments["body"],
        )
