#!/usr/bin/env python3
"""Read-only production adapter for deterministic Source Continuity V1 receipts.

This adapter observes one explicit local Git worktree plus authenticated GitHub
GET-only facts, then delegates all classification to the pure verifier in
``control_plane.source_continuity``. It intentionally owns no persistence,
lifecycle, retry/failover, watcher, receiver-transfer, release, merge, provider,
or runtime effect.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys

# This read-only adapter audits ignored/untracked repository state. Prevent its
# own repository imports from creating bytecode dirt before that audit runs.
sys.dont_write_bytecode = True

from threading import Lock
from time import monotonic
from typing import Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control_plane.source_continuity import (  # noqa: E402
    BranchEffectDependency,
    BranchRuleFact,
    BypassActorFact,
    CollisionState,
    ExternalEffectEvidence,
    ExternalEffectState,
    LocalGitFacts,
    ReceiptKind,
    RefusalCode,
    RemoteGitFacts,
    RemotePathEntry,
    RulesetFact,
    SourceContinuityRefusal,
    SourceContinuityRequest,
    WriterGateFacts,
    WriterGateRequest,
    canonical_json,
    request_is_valid,
    verify_source_continuity,
    verify_technical_writer_gate,
    writer_gate_request_is_valid,
)

_GIT = "/usr/bin/git"
_API_ROOT = "https://api.github.com"
_API_VERSION = "2022-11-28"
_COMMAND_TIMEOUT_SECONDS = 20.0
_HTTP_TIMEOUT_SECONDS = 20.0
_MAX_HTTP_BODY_BYTES = 5_000_000
_MAX_GIT_CONFIG_CENSUS_BYTES = 65_536
_MAX_GIT_PATH_BYTES = 4_096
_PAGE_SIZE = 100
_MAX_PAGES = 10
_MAX_FOREIGN_FILE_PAGES = 30
_FOREIGN_PR_WORKERS = 4
_MAX_COLLISION_PRS = 485
# One invocation-local cooperative budget spans both observations, not hard preemption.
_MAX_HTTP_CALLS = 1152
_HTTP_READ_BUDGET_SECONDS = 300.0
_MAX_HTTP_NORMALIZED_BYTES = 128 * 1024 * 1024
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_HOLD_LABELS = frozenset({"hold", "hold-for-sol", "hold_for_sol"})
_PR_FILE_STATUSES = frozenset(
    {"added", "changed", "copied", "modified", "removed", "renamed", "unchanged"}
)
_GIT_CONFIG_OVERRIDES = (
    "core.fsmonitor=false",
    "core.untrackedCache=false",
    "core.hooksPath=/dev/null",
    "core.attributesFile=/dev/null",
    "core.excludesFile=/dev/null",
    "diff.external=",
    "diff.renames=false",
    "core.fileMode=true",
    "core.ignoreStat=false",
    "core.checkStat=default",
    "core.trustctime=true",
    "core.symlinks=true",
    "credential.helper=",
    "protocol.allow=never",
    "protocol.file.allow=always",
)
_GIT_ENV = {
    "LANG": "C",
    "LC_ALL": "C",
    "TZ": "UTC",
    "PATH": "/usr/bin:/bin",
    "HOME": "/",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_ATTR_NOSYSTEM": "1",
    "GIT_LITERAL_PATHSPECS": "1",
    "GIT_NO_REPLACE_OBJECTS": "1",
    "GIT_GRAFT_FILE": os.devnull,
    "GIT_PAGER": "cat",
    "GIT_EDITOR": "/usr/bin/false",
    "GIT_SEQUENCE_EDITOR": "/usr/bin/false",
    "GIT_ASKPASS": "/usr/bin/false",
    "SSH_ASKPASS": "/usr/bin/false",
    "GIT_SSH": "/usr/bin/false",
    "GIT_SSH_COMMAND": "/usr/bin/false",
    "GIT_CONFIG_COUNT": "0",
}


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise ValueError("invalid arguments")


class _AuthProbeError(Exception):
    pass


class _RemoteProbeError(Exception):
    pass


class _RemoteResourceMissing(_RemoteProbeError):
    """A 404 on an endpoint whose absence is itself a lawful observation.

    Subclasses `_RemoteProbeError` so every existing caller keeps failing
    closed unchanged; only an explicit optional readback may read it as
    absence. Transports signal it by the marker attribute, not by class
    identity, so an injected transport can raise its own type.
    """

    source_continuity_resource_missing = True


_MISSING = object()


def _is_resource_missing(error: BaseException) -> bool:
    return getattr(error, "source_continuity_resource_missing", False) is True


class _ReadBudgetExceeded(Exception):
    pass


@dataclass(frozen=True)
class _HTTPRepresentation:
    payload: object
    etag: str | None
    not_modified: bool


@dataclass(frozen=True)
class _ConditionalObservation:
    url: str
    etag: str
    semantics: object


# A changed HTTP 200 is semantically revalidatable only for the open-PR roster
# pages used by the collision census and this invocation's exact subject PR.
# Every other endpoint keeps the original unconditional changed-representation
# refusal required by #346.
_UNPROVABLE = object()


def _open_pull_roster_semantics(url: object, payload: object) -> object:
    if not isinstance(url, str) or not url.startswith(_API_ROOT + "/repos/"):
        return _UNPROVABLE
    path, separator, query = url.partition("?")
    if separator != "?":
        return _UNPROVABLE
    segments = path[len(_API_ROOT) + 1 :].split("/")
    if len(segments) != 4 or segments[0] != "repos" or segments[3] != "pulls":
        return _UNPROVABLE

    pairs: list[tuple[str, str]] = []
    for raw_part in query.split("&"):
        key, equals, value = raw_part.partition("=")
        if equals != "=" or not key:
            return _UNPROVABLE
        pairs.append((key, value))
    if len(pairs) != 3 or len({key for key, _ in pairs}) != 3:
        return _UNPROVABLE
    params = dict(pairs)
    page = params.get("page")
    if (
        params.get("state") != "open"
        or params.get("per_page") != str(_PAGE_SIZE)
        or page is None
        or not page.isdigit()
        or int(page) <= 0
        or int(page) > _MAX_PAGES
    ):
        return _UNPROVABLE

    if not isinstance(payload, list) or len(payload) > _PAGE_SIZE:
        return _UNPROVABLE
    rows: list[tuple[int, str, str, str, str]] = []
    seen_numbers: set[int] = set()
    for row in payload:
        if not isinstance(row, dict):
            return _UNPROVABLE
        number = row.get("number")
        head = row.get("head")
        base = row.get("base")
        if type(number) is not int or number <= 0 or number in seen_numbers:
            return _UNPROVABLE
        if not isinstance(head, dict) or not isinstance(base, dict):
            return _UNPROVABLE
        head_repo = head.get("repo")
        base_repo = base.get("repo")
        if not isinstance(head_repo, dict) or not isinstance(base_repo, dict):
            return _UNPROVABLE
        head_sha = head.get("sha")
        base_sha = base.get("sha")
        head_repository = head_repo.get("full_name")
        base_repository = base_repo.get("full_name")
        if (
            not _is_sha(head_sha)
            or not _is_sha(base_sha)
            or not _is_safe_repository(head_repository)
            or not _is_safe_repository(base_repository)
        ):
            return _UNPROVABLE
        state = row.get("state")
        if state is not None and state != "open":
            return _UNPROVABLE
        seen_numbers.add(number)
        rows.append((number, head_sha, head_repository, base_sha, base_repository))
    return tuple(sorted(rows))


def _subject_pr_identity(payload: object) -> tuple[object, ...] | None:
    """Strict closed shape for changed subject-PR semantic revalidation."""

    if not isinstance(payload, dict):
        return None
    if type(payload.get("draft")) is not bool:
        return None
    labels = payload.get("labels")
    if not isinstance(labels, list):
        return None
    for label in labels:
        if not isinstance(label, dict):
            return None
        if not isinstance(label.get("name"), str):
            return None
    return _pr_identity(payload)


def _conditional_semantics(
    url: object,
    payload: object,
    *,
    subject_pull_url: str | None,
    base_branch_url: str | None,
) -> object:
    """Project only changed representations this invocation may safely re-prove."""

    roster = _open_pull_roster_semantics(url, payload)
    if roster is not _UNPROVABLE:
        return ("open_pull_roster", roster)
    if isinstance(base_branch_url, str) and url == base_branch_url:
        if not isinstance(payload, dict):
            return _UNPROVABLE
        commit = payload.get("commit")
        if not isinstance(commit, dict) or not _is_sha(commit.get("sha")):
            return _UNPROVABLE
        return ("base_branch", commit["sha"])
    if not isinstance(subject_pull_url, str) or url != subject_pull_url:
        return _UNPROVABLE
    identity = _subject_pr_identity(payload)
    if identity is None:
        return _UNPROVABLE
    return ("subject_pull", identity)


class _BoundedHTTPGet:
    def __init__(
        self,
        transport: HTTPGet,
        *,
        subject_pull_url: str | None = None,
        base_branch_url: str | None = None,
    ) -> None:
        self._transport = transport
        self._subject_pull_url = subject_pull_url
        self._base_branch_url = base_branch_url
        self._lock = Lock()
        self._calls = 0
        self._bytes = 0
        self._conditional_observations: list[_ConditionalObservation] = []
        self._semantic_revalidations: list[str] = []
        self._missing_observations: list[str] = []
        self._base_head_update: tuple[str, str] | None = None
        self.parallel_safe = (
            transport is _stdlib_http_get
            or getattr(transport, "_source_continuity_parallel_safe", False) is True
        )
        self.conditional_validation_available = (
            transport is _stdlib_http_get
            or getattr(transport, "_source_continuity_conditional", False) is True
        )
        try:
            started = monotonic()
        except Exception:
            started = None
        if (
            isinstance(started, bool)
            or not isinstance(started, (int, float))
            or not math.isfinite(started)
            or not math.isfinite(started + _HTTP_READ_BUDGET_SECONDS)
        ):
            self._started = None
            self._last_now = None
            self._deadline = float("-inf")
        else:
            self._started = float(started)
            self._last_now = float(started)
            self._deadline = float(started) + _HTTP_READ_BUDGET_SECONDS

    def _checked_now_locked(self) -> float:
        if self._started is None or self._last_now is None:
            raise _ReadBudgetExceeded()
        try:
            now = monotonic()
        except Exception:
            raise _ReadBudgetExceeded() from None
        if (
            isinstance(now, bool)
            or not isinstance(now, (int, float))
            or not math.isfinite(now)
        ):
            raise _ReadBudgetExceeded()
        current = float(now)
        if current < self._last_now or current >= self._deadline:
            raise _ReadBudgetExceeded()
        self._last_now = current
        return current

    def check(self) -> None:
        with self._lock:
            self._checked_now_locked()
            if self._bytes > _MAX_HTTP_NORMALIZED_BYTES:
                raise _ReadBudgetExceeded()

    def _admit_call(self, timeout: float) -> float:
        with self._lock:
            now = self._checked_now_locked()
            if self._calls >= _MAX_HTTP_CALLS:
                raise _ReadBudgetExceeded()
            self._calls += 1
            remaining = self._deadline - now
            call_timeout = min(float(timeout), remaining)
            if not math.isfinite(call_timeout) or call_timeout <= 0:
                raise _ReadBudgetExceeded()
            return call_timeout

    def _account_payload(self, payload: object) -> None:
        try:
            normalized = canonical_json(payload).encode("utf-8", "backslashreplace")
        except Exception:
            raise _RemoteProbeError() from None

        with self._lock:
            self._bytes += len(normalized)
            self._checked_now_locked()
            if self._bytes > _MAX_HTTP_NORMALIZED_BYTES:
                raise _ReadBudgetExceeded()

    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        call_timeout = self._admit_call(timeout)

        payload = self._transport(url, token=token, timeout=call_timeout)
        if self.conditional_validation_available:
            if (
                not isinstance(payload, _HTTPRepresentation)
                or payload.not_modified is not False
                or not _is_valid_etag(payload.etag)
            ):
                raise _RemoteProbeError()
            representation = payload
            self._account_payload(representation.payload)
            semantics = _conditional_semantics(
                url,
                representation.payload,
                subject_pull_url=self._subject_pull_url,
                base_branch_url=self._base_branch_url,
            )
            with self._lock:
                self._conditional_observations.append(
                    _ConditionalObservation(
                        url=url,
                        etag=representation.etag,
                        semantics=semantics,
                    )
                )
            return representation.payload

        self._account_payload(payload)
        return payload

    def _collision_read(self, url: str, *, token: str, timeout: float) -> object:
        """Read one collision-census resource without registering a strict ETag fence."""

        call_timeout = self._admit_call(timeout)
        payload = self._transport(url, token=token, timeout=call_timeout)
        if self.conditional_validation_available:
            if (
                not isinstance(payload, _HTTPRepresentation)
                or payload.not_modified is not False
                or not _is_valid_etag(payload.etag)
            ):
                raise _RemoteProbeError()
            self._account_payload(payload.payload)
            return payload.payload
        self._account_payload(payload)
        return payload

    def collision_census_reader(self) -> "_CollisionCensusHTTP":
        return _CollisionCensusHTTP(self)

    def get_optional(self, url: str, *, token: str, timeout: float) -> object:
        """GET a resource that may lawfully be absent.

        Only an absence the transport marks as such becomes `_MISSING`; every
        other failure propagates and fails closed. The absence is recorded so
        a resource that appears mid-proof is caught as a change.
        """

        try:
            return self(url, token=token, timeout=timeout)
        except Exception as error:
            if not _is_resource_missing(error):
                raise
        with self._lock:
            self._missing_observations.append(url)
        return _MISSING

    def validate_unchanged(self, *, token: str) -> bool:
        if not self.conditional_validation_available:
            raise _RemoteProbeError()
        with self._lock:
            observations = tuple(self._conditional_observations)
            absences = tuple(self._missing_observations)
        for observation in observations:
            call_timeout = self._admit_call(_HTTP_TIMEOUT_SECONDS)
            payload = self._transport(
                observation.url,
                token=token,
                timeout=call_timeout,
                if_none_match=observation.etag,
            )
            if not isinstance(payload, _HTTPRepresentation) or not _is_valid_etag(
                payload.etag
            ):
                raise _RemoteProbeError()
            if payload.not_modified is True:
                if payload.payload is not None or not _etags_match_validator(
                    observation.etag, payload.etag
                ):
                    raise _RemoteProbeError()
                continue
            if payload.not_modified is False:
                # Account every changed body before deciding. Only the open-PR
                # roster and this invocation's exact subject-PR endpoint may survive,
                # and only when their closed canonical projections are identical.
                self._account_payload(payload.payload)
                with self._lock:
                    self._semantic_revalidations.append(observation.url)
                if observation.semantics is _UNPROVABLE:
                    return False
                current_semantics = _conditional_semantics(
                    observation.url,
                    payload.payload,
                    subject_pull_url=self._subject_pull_url,
                    base_branch_url=self._base_branch_url,
                )
                if current_semantics == observation.semantics:
                    continue
                if (
                    observation.url == self._base_branch_url
                    and isinstance(observation.semantics, tuple)
                    and len(observation.semantics) == 2
                    and observation.semantics[0] == "base_branch"
                    and isinstance(current_semantics, tuple)
                    and len(current_semantics) == 2
                    and current_semantics[0] == "base_branch"
                ):
                    old_head = observation.semantics[1]
                    new_head = current_semantics[1]
                    if not _is_sha(old_head) or not _is_sha(new_head):
                        return False
                    with self._lock:
                        update = (old_head, new_head)
                        if self._base_head_update not in (None, update):
                            return False
                        self._base_head_update = update
                    continue
                return False
            raise _RemoteProbeError()
        for url in absences:
            call_timeout = self._admit_call(_HTTP_TIMEOUT_SECONDS)
            try:
                payload = self._transport(url, token=token, timeout=call_timeout)
            except Exception as error:
                if _is_resource_missing(error):
                    continue
                raise
            if isinstance(payload, _HTTPRepresentation):
                self._account_payload(payload.payload)
            return False
        return True

    def base_head_update(self) -> tuple[str, str] | None:
        with self._lock:
            return self._base_head_update


class _CollisionCensusHTTP:
    """Scoped view over one bounded transport for collision-census reads.

    Collision membership is re-proved by a complete second census, so these
    reads must not also become strict per-URL ETag obligations. They still use
    the exact same call/byte/time budget and transport.
    """

    def __init__(self, parent: _BoundedHTTPGet) -> None:
        self._parent = parent
        self.parallel_safe = parent.parallel_safe

    def __call__(
        self,
        url: str,
        *,
        token: str,
        timeout: float,
    ) -> object:
        return self._parent._collision_read(url, token=token, timeout=timeout)


@dataclass(frozen=True)
class _CommandResult:
    returncode: int
    stdout: str


@dataclass(frozen=True)
class _GitTreeEntry:
    mode: str
    object_type: str
    object_sha: str


@dataclass(frozen=True)
class _ForeignPullIdentity:
    pr_number: int
    head_repository: str
    head_sha: str
    base_repository: str
    base_sha: str


@dataclass(frozen=True)
class _SaturatedCollisionEvidence:
    pr_number: int
    proof_method: str
    head_repository: str
    head_sha: str
    base_repository: str
    base_sha: str
    merge_base_sha: str
    owned_path_entries: tuple[
        tuple[str, _GitTreeEntry | None, _GitTreeEntry | None], ...
    ]


@dataclass(frozen=True)
class _ForeignFilesObservation:
    paths: tuple[str, ...]
    saturated: bool


@dataclass(frozen=True)
class _ForeignCollisionRecord:
    pr_number: int
    identity: _ForeignPullIdentity | None
    evidence: tuple[str, ...] | _SaturatedCollisionEvidence
    overlaps: bool


@dataclass(frozen=True)
class _CollisionCensusDetails:
    state: CollisionState
    colliding_pr_numbers: tuple[int, ...]
    complete: bool
    snapshot: tuple[tuple[int, object], ...]
    foreign_records: tuple[_ForeignCollisionRecord, ...]


Runner = Callable[..., object]
HTTPGet = Callable[..., object]
Clock = Callable[[], str]


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _refusal(code: RefusalCode, exit_code: int) -> SourceContinuityRefusal:
    return SourceContinuityRefusal(code=code, exit_code=exit_code)


def _emit(result: object) -> int:
    if isinstance(result, SourceContinuityRefusal):
        print(canonical_json(result.to_dict()))
        return result.exit_code
    print(canonical_json(result.to_dict()))
    return 0


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and _SHA_RE.fullmatch(value) is not None


def _is_safe_remote_path(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    if len(encoded) > 4096:
        return False
    if value.startswith("/") or "\\" in value or "//" in value or "\x00" in value:
        return False
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return False
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or any(part in {"", ".", ".."} for part in parsed.parts):
        return False
    if parsed.parts and parsed.parts[0] == ".git":
        return False
    return str(parsed) == value


def _is_safe_repository(value: object) -> bool:
    return (
        isinstance(value, str)
        and _REPOSITORY_RE.fullmatch(value) is not None
        and ".." not in value
    )


def _is_safe_tree_name(value: object) -> bool:
    return (
        _is_safe_remote_path(value)
        and isinstance(value, str)
        and "/" not in value
    )


def _is_valid_etag(value: object) -> bool:
    if not isinstance(value, str):
        return False
    opaque = value[2:] if value.startswith("W/") else value
    if not opaque.startswith('"') or not opaque.endswith('"') or len(opaque) < 2:
        return False
    for character in opaque[1:-1]:
        codepoint = ord(character)
        if not (
            codepoint == 0x21
            or 0x23 <= codepoint <= 0x7E
            or 0x80 <= codepoint <= 0xFF
        ):
            return False
    return True


def _etag_opaque(value: str) -> str:
    return value[2:] if value.startswith("W/") else value


def _etags_match_validator(left: str, right: str) -> bool:
    return _etag_opaque(left) == _etag_opaque(right)


def _invoke_git(
    runner: Runner,
    workspace: str,
    *arguments: str,
) -> _CommandResult | None:
    command = [_GIT, "--no-pager", "--no-replace-objects"]
    for setting in _GIT_CONFIG_OVERRIDES:
        command.extend(("-c", setting))
    command.append("--work-tree=.")
    command.extend(arguments)
    runner_kwargs = {
        "cwd": workspace,
        "env": dict(_GIT_ENV),
        "text": True,
        "capture_output": True,
        "check": False,
        "timeout": _COMMAND_TIMEOUT_SECONDS,
    }
    try:
        completed = runner(
            command,
            **runner_kwargs,
        )
    except Exception:
        return None
    try:
        returncode = getattr(completed, "returncode")
        stdout = getattr(completed, "stdout")
    except Exception:
        return None
    if type(returncode) is not int or not isinstance(stdout, str):
        return None
    return _CommandResult(returncode=returncode, stdout=stdout)


def _single_etag(headers: object) -> str:
    try:
        values = headers.get_all("ETag")  # type: ignore[attr-defined]
    except Exception:
        return ""
    if not isinstance(values, list) or len(values) != 1:
        return ""
    value = values[0]
    return value if isinstance(value, str) and _is_valid_etag(value) else ""


def _stdlib_http_get(
    url: str,
    *,
    token: str,
    timeout: float,
    if_none_match: str | None = None,
) -> object:
    if not isinstance(url, str) or not url.startswith(_API_ROOT + "/"):
        raise _RemoteProbeError()
    if not isinstance(token, str) or not token:
        raise _AuthProbeError()
    if if_none_match is not None and not _is_valid_etag(if_none_match):
        raise _RemoteProbeError()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": _API_VERSION,
        "User-Agent": "mastermind-source-continuity-v1",
    }
    if if_none_match is not None:
        headers["If-None-Match"] = if_none_match
    request = Request(
        url,
        method="GET",
        headers=headers,
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed GitHub API root
            etag = _single_etag(response.headers)
            if not etag:
                raise _RemoteProbeError()
            raw = response.read(_MAX_HTTP_BODY_BYTES + 1)
    except HTTPError as exc:
        if exc.code == 304:
            etag = _single_etag(exc.headers)
            if not etag:
                raise _RemoteProbeError()
            raw = exc.read(_MAX_HTTP_BODY_BYTES + 1)
            if raw:
                raise _RemoteProbeError()
            return _HTTPRepresentation(payload=None, etag=etag, not_modified=True)
        if exc.code in {401, 403}:
            raise _AuthProbeError() from None
        if exc.code == HTTPStatus.NOT_FOUND:
            raise _RemoteResourceMissing() from None
        raise _RemoteProbeError() from None
    except (URLError, TimeoutError, OSError):
        raise _RemoteProbeError() from None
    if len(raw) > _MAX_HTTP_BODY_BYTES:
        raise _RemoteProbeError()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise _RemoteProbeError() from None
    return _HTTPRepresentation(payload=payload, etag=etag, not_modified=False)


_stdlib_http_get._source_continuity_conditional = True  # type: ignore[attr-defined]


def _api(http_get: HTTPGet, token: str, endpoint: str) -> object:
    if not isinstance(endpoint, str) or endpoint.startswith(("http://", "https://")):
        raise _RemoteProbeError()
    return http_get(
        f"{_API_ROOT}/{endpoint}",
        token=token,
        timeout=_HTTP_TIMEOUT_SECONDS,
    )


def _api_optional(http_get: HTTPGet, token: str, endpoint: str) -> object:
    """Read an endpoint whose absence is a lawful observation, else `_MISSING`."""

    if not isinstance(endpoint, str) or endpoint.startswith(("http://", "https://")):
        raise _RemoteProbeError()
    url = f"{_API_ROOT}/{endpoint}"
    optional = getattr(http_get, "get_optional", None)
    if optional is not None:
        return optional(url, token=token, timeout=_HTTP_TIMEOUT_SECONDS)
    try:
        return http_get(url, token=token, timeout=_HTTP_TIMEOUT_SECONDS)
    except Exception as error:
        if not _is_resource_missing(error):
            raise
    return _MISSING


def _branch_endpoint(repository: str, branch: str) -> str:
    return f"repos/{repository}/branches/{quote(branch, safe='')}"


def _branch_protection_endpoint(repository: str, branch: str) -> str:
    return f"repos/{repository}/branches/{quote(branch, safe='')}/protection"


def _branch_rules_endpoint(repository: str, branch: str) -> str:
    return f"repos/{repository}/rules/branches/{quote(branch, safe='')}"


def _ruleset_endpoint(repository: str, source_type: str, ruleset_id: int) -> str:
    if source_type == "Repository":
        return f"repos/{repository}/rulesets/{ruleset_id}"
    organization = repository.split("/", 1)[0]
    return f"orgs/{organization}/rulesets/{ruleset_id}"


def _pull_files_endpoint(repository: str, pr_number: int, page: int) -> str:
    return f"repos/{repository}/pulls/{pr_number}/files?per_page={_PAGE_SIZE}&page={page}"


def _paged_array(
    http_get: HTTPGet,
    token: str,
    endpoint_for_page: Callable[[int], str],
) -> tuple[list[object], bool]:
    items: list[object] = []
    for page in range(1, _MAX_PAGES + 1):
        payload = _api(http_get, token, endpoint_for_page(page))
        if not isinstance(payload, list):
            raise _RemoteProbeError()
        items.extend(payload)
        if len(payload) < _PAGE_SIZE:
            return items, True
    return items, False


def _hold_from_pr(pr: dict[str, object]) -> bool:
    if pr.get("draft") is True:
        return True
    labels = pr.get("labels")
    if not isinstance(labels, list):
        return False
    for label in labels:
        if not isinstance(label, dict):
            continue
        name = label.get("name")
        if isinstance(name, str) and name.strip().lower() in _HOLD_LABELS:
            return True
    return False


def _pr_identity(pr: object) -> tuple[object, ...] | None:
    if not isinstance(pr, dict):
        return None
    head = pr.get("head")
    base = pr.get("base")
    if not isinstance(head, dict) or not isinstance(base, dict):
        return None
    head_repo = head.get("repo")
    if not isinstance(head_repo, dict):
        return None
    return (
        pr.get("state"),
        _hold_from_pr(pr),
        head.get("ref"),
        head.get("sha"),
        head_repo.get("full_name"),
        base.get("ref"),
    )


def _parse_changed_path_rows(raw_items: Sequence[object]) -> tuple[str, ...]:
    paths: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            raise _RemoteProbeError()
        filename = item.get("filename")
        if not isinstance(filename, str) or not _is_safe_remote_path(filename):
            raise _RemoteProbeError()
        status = item.get("status")
        if not isinstance(status, str) or status not in _PR_FILE_STATUSES:
            raise _RemoteProbeError()
        row_paths: tuple[str, ...]
        if status == "renamed":
            previous_filename = item.get("previous_filename")
            if (
                not isinstance(previous_filename, str)
                or not _is_safe_remote_path(previous_filename)
                or previous_filename == filename
            ):
                raise _RemoteProbeError()
            row_paths = (previous_filename, filename)
        else:
            if "previous_filename" in item:
                raise _RemoteProbeError()
            row_paths = (filename,)
        for path in row_paths:
            if path in seen:
                raise _RemoteProbeError()
            seen.add(path)
            paths.append(path)
    return tuple(paths)


def _pull_files_page(
    http_get: HTTPGet,
    token: str,
    repository: str,
    pr_number: int,
    page: int,
) -> list[object]:
    payload = _api(
        http_get,
        token,
        _pull_files_endpoint(repository, pr_number, page),
    )
    if not isinstance(payload, list) or len(payload) > _PAGE_SIZE:
        raise _RemoteProbeError()
    return payload


def _changed_paths(
    http_get: HTTPGet,
    token: str,
    repository: str,
    pr_number: int,
) -> tuple[tuple[str, ...], bool]:
    raw_items, complete = _paged_array(
        http_get,
        token,
        lambda page: _pull_files_endpoint(repository, pr_number, page),
    )
    return _parse_changed_path_rows(raw_items), complete


def _foreign_files_observation(
    http_get: HTTPGet,
    token: str,
    repository: str,
    pr_number: int,
) -> _ForeignFilesObservation:
    first = _pull_files_page(http_get, token, repository, pr_number, 1)
    if len(first) < _PAGE_SIZE:
        return _ForeignFilesObservation(_parse_changed_path_rows(first), False)

    terminal = _pull_files_page(
        http_get,
        token,
        repository,
        pr_number,
        _MAX_FOREIGN_FILE_PAGES,
    )
    if len(terminal) == _PAGE_SIZE:
        _parse_changed_path_rows(first)
        _parse_changed_path_rows(terminal)
        return _ForeignFilesObservation((), True)

    items = list(first)
    for page in range(2, _MAX_FOREIGN_FILE_PAGES):
        payload = _pull_files_page(http_get, token, repository, pr_number, page)
        items.extend(payload)
        if len(payload) < _PAGE_SIZE:
            if terminal:
                raise _RemoteProbeError()
            return _ForeignFilesObservation(_parse_changed_path_rows(items), False)
    items.extend(terminal)
    return _ForeignFilesObservation(_parse_changed_path_rows(items), False)


def _foreign_pull_identity(
    raw_pr: object,
    repository: str,
) -> _ForeignPullIdentity:
    if not isinstance(raw_pr, dict):
        raise _RemoteProbeError()
    number = raw_pr.get("number")
    head = raw_pr.get("head")
    base = raw_pr.get("base")
    if type(number) is not int or number <= 0:
        raise _RemoteProbeError()
    if not isinstance(head, dict) or not isinstance(base, dict):
        raise _RemoteProbeError()
    head_repo = head.get("repo")
    base_repo = base.get("repo")
    if not isinstance(head_repo, dict) or not isinstance(base_repo, dict):
        raise _RemoteProbeError()
    head_repository = head_repo.get("full_name")
    base_repository = base_repo.get("full_name")
    head_sha = head.get("sha")
    base_sha = base.get("sha")
    if (
        not _is_safe_repository(head_repository)
        or not _is_safe_repository(base_repository)
        or base_repository != repository
        or not _is_sha(head_sha)
        or not _is_sha(base_sha)
    ):
        raise _RemoteProbeError()
    return _ForeignPullIdentity(
        pr_number=number,
        head_repository=head_repository,
        head_sha=head_sha,
        base_repository=base_repository,
        base_sha=base_sha,
    )


def _foreign_merge_base_sha(
    http_get: HTTPGet,
    token: str,
    identity: _ForeignPullIdentity,
) -> str:
    endpoint = (
        f"repos/{identity.base_repository}/compare/"
        f"{identity.base_sha}...{identity.head_sha}"
    )
    payload = _api(http_get, token, endpoint)
    if not isinstance(payload, dict) or payload.get("url") != f"{_API_ROOT}/{endpoint}":
        raise _RemoteProbeError()
    base_commit = payload.get("base_commit")
    merge_base = payload.get("merge_base_commit")
    if (
        not isinstance(base_commit, dict)
        or base_commit.get("sha") != identity.base_sha
        or not isinstance(merge_base, dict)
        or not _is_sha(merge_base.get("sha"))
    ):
        raise _RemoteProbeError()
    return merge_base["sha"]


def _commit_tree_sha(
    http_get: HTTPGet,
    token: str,
    repository: str,
    commit_sha: str,
) -> str:
    payload = _api(
        http_get,
        token,
        f"repos/{repository}/git/commits/{commit_sha}",
    )
    if not isinstance(payload, dict) or payload.get("sha") != commit_sha:
        raise _RemoteProbeError()
    tree = payload.get("tree")
    if not isinstance(tree, dict) or not _is_sha(tree.get("sha")):
        raise _RemoteProbeError()
    return tree["sha"]


_TREE_MODE_TYPES = {
    "040000": "tree",
    "100644": "blob",
    "100755": "blob",
    "120000": "blob",
    "160000": "commit",
}


def _read_tree_entries(
    http_get: HTTPGet,
    token: str,
    repository: str,
    tree_sha: str,
) -> dict[str, _GitTreeEntry]:
    payload = _api(http_get, token, f"repos/{repository}/git/trees/{tree_sha}")
    if (
        not isinstance(payload, dict)
        or payload.get("sha") != tree_sha
        or payload.get("truncated") is not False
    ):
        raise _RemoteProbeError()
    rows = payload.get("tree")
    if not isinstance(rows, list):
        raise _RemoteProbeError()
    entries: dict[str, _GitTreeEntry] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise _RemoteProbeError()
        name = row.get("path")
        mode = row.get("mode")
        object_type = row.get("type")
        object_sha = row.get("sha")
        size = row.get("size")
        if (
            not _is_safe_tree_name(name)
            or not isinstance(mode, str)
            or _TREE_MODE_TYPES.get(mode) != object_type
            or not _is_sha(object_sha)
            or name in entries
            or (size is not None and (type(size) is not int or size < 0))
        ):
            raise _RemoteProbeError()
        entries[name] = _GitTreeEntry(mode, object_type, object_sha)
    return entries


def _resolve_owned_path(
    http_get: HTTPGet,
    token: str,
    repository: str,
    root_tree_sha: str,
    path: str,
    cache: dict[tuple[str, str], dict[str, _GitTreeEntry]],
) -> _GitTreeEntry | None:
    if not _is_safe_remote_path(path) or not _is_sha(root_tree_sha):
        raise _RemoteProbeError()
    tree_sha = root_tree_sha
    parts = PurePosixPath(path).parts
    for index, part in enumerate(parts):
        key = (repository, tree_sha)
        entries = cache.get(key)
        if entries is None:
            entries = _read_tree_entries(http_get, token, repository, tree_sha)
            cache[key] = entries
        entry = entries.get(part)
        if entry is None:
            return None
        if index == len(parts) - 1:
            return entry
        if entry.mode != "040000" or entry.object_type != "tree":
            return None
        tree_sha = entry.object_sha
    raise _RemoteProbeError()


def _saturated_collision_evidence(
    http_get: HTTPGet,
    token: str,
    repository: str,
    raw_pr: object,
    owned_paths: tuple[str, ...],
) -> tuple[_SaturatedCollisionEvidence, bool]:
    identity = _foreign_pull_identity(raw_pr, repository)
    merge_base_sha = _foreign_merge_base_sha(http_get, token, identity)
    base_root_tree = _commit_tree_sha(
        http_get,
        token,
        identity.base_repository,
        merge_base_sha,
    )
    head_root_tree = _commit_tree_sha(
        http_get,
        token,
        identity.head_repository,
        identity.head_sha,
    )
    cache: dict[tuple[str, str], dict[str, _GitTreeEntry]] = {}
    pairs: list[tuple[str, _GitTreeEntry | None, _GitTreeEntry | None]] = []
    collision = False
    for path in sorted(owned_paths):
        base_entry = _resolve_owned_path(
            http_get,
            token,
            identity.base_repository,
            base_root_tree,
            path,
            cache,
        )
        head_entry = _resolve_owned_path(
            http_get,
            token,
            identity.head_repository,
            head_root_tree,
            path,
            cache,
        )
        pairs.append((path, base_entry, head_entry))
        collision = collision or base_entry != head_entry
    return (
        _SaturatedCollisionEvidence(
            pr_number=identity.pr_number,
            proof_method="OWNED_PATH_TREE_DIFF",
            head_repository=identity.head_repository,
            head_sha=identity.head_sha,
            base_repository=identity.base_repository,
            base_sha=identity.base_sha,
            merge_base_sha=merge_base_sha,
            owned_path_entries=tuple(pairs),
        ),
        collision,
    )


def _foreign_collision_evidence(
    http_get: HTTPGet,
    token: str,
    repository: str,
    raw_pr: object,
    pr_number: int,
    owned_paths: tuple[str, ...],
) -> tuple[tuple[str, ...] | _SaturatedCollisionEvidence, bool]:
    files = _foreign_files_observation(
        http_get,
        token,
        repository,
        pr_number,
    )
    if not files.saturated:
        return files.paths, bool(set(owned_paths).intersection(files.paths))
    return _saturated_collision_evidence(
        http_get,
        token,
        repository,
        raw_pr,
        owned_paths,
    )


def _foreign_observations(
    http_get: HTTPGet,
    token: str,
    repository: str,
    jobs: tuple[tuple[int, object], ...],
    owned_paths: tuple[str, ...],
) -> tuple[tuple[int, object, bool], ...]:
    if not jobs:
        return ()
    workers = (
        min(_FOREIGN_PR_WORKERS, len(jobs))
        if getattr(http_get, "_parallel_safe", False)
        else 1
    )
    if workers == 1:
        return tuple(
            (
                number,
                *_foreign_collision_evidence(
                    http_get,
                    token,
                    repository,
                    raw_pr,
                    number,
                    owned_paths,
                ),
            )
            for number, raw_pr in jobs
        )

    results: list[tuple[int, object, bool]] = []
    with ThreadPoolExecutor(
        max_workers=workers,
        thread_name_prefix="source-continuity",
    ) as executor:
        futures = {
            executor.submit(
                _foreign_collision_evidence,
                http_get,
                token,
                repository,
                raw_pr,
                number,
                owned_paths,
            ): number
            for number, raw_pr in jobs
        }
        try:
            for future in as_completed(futures):
                number = futures[future]
                evidence, has_collision = future.result()
                results.append((number, evidence, has_collision))
        except Exception:
            for future in futures:
                future.cancel()
            raise
    return tuple(sorted(results, key=lambda item: item[0]))


def _collision_reader(http_get: HTTPGet) -> HTTPGet:
    factory = getattr(http_get, "collision_census_reader", None)
    if callable(factory):
        return factory()
    return http_get


def _read_open_pull_roster(
    http_get: HTTPGet,
    token: str,
    repository: str,
) -> tuple[list[object], bool]:
    pulls: list[object] = []
    for page in range(1, _MAX_PAGES + 1):
        payload = _api(
            http_get,
            token,
            f"repos/{repository}/pulls?state=open&per_page={_PAGE_SIZE}&page={page}",
        )
        if not isinstance(payload, list) or len(payload) > _PAGE_SIZE:
            raise _RemoteProbeError()
        pulls.extend(payload)
        if len(pulls) > _MAX_COLLISION_PRS:
            return pulls, False
        if len(payload) < _PAGE_SIZE:
            return pulls, True
    return pulls, False


def _collision_census_details(
    http_get: HTTPGet,
    token: str,
    repository: str,
    target_pr: int,
    owned_paths: tuple[str, ...],
) -> _CollisionCensusDetails:
    reader = _collision_reader(http_get)
    pulls, complete = _read_open_pull_roster(reader, token, repository)
    if not complete:
        return _CollisionCensusDetails(
            CollisionState.INCOMPLETE, (), False, (), ()
        )

    seen_numbers: set[int] = set()
    target_seen = False
    foreign: list[tuple[int, object]] = []
    for raw_pr in pulls:
        if not isinstance(raw_pr, dict):
            raise _RemoteProbeError()
        number = raw_pr.get("number")
        state = raw_pr.get("state")
        if (
            type(number) is not int
            or number <= 0
            or number in seen_numbers
            or (state is not None and state != "open")
        ):
            raise _RemoteProbeError()
        seen_numbers.add(number)
        if number == target_pr:
            target_seen = True
        else:
            foreign.append((number, raw_pr))
    if not target_seen:
        raise _RemoteProbeError()

    def observe(item: tuple[int, object]) -> _ForeignCollisionRecord:
        number, raw_pr = item
        try:
            identity = _foreign_pull_identity(raw_pr, repository)
        except _RemoteProbeError:
            # Historical injected transports may provide only the PR number for
            # unsaturated foreign rows. Preserve that accepted test seam; the
            # custody-aware revalidation path is used only when GitHub supplies
            # the complete immutable identity.
            identity = None
        if identity is not None and identity.pr_number != number:
            raise _RemoteProbeError()
        evidence, overlaps = _foreign_collision_evidence(
            reader,
            token,
            repository,
            raw_pr,
            number,
            owned_paths,
        )
        return _ForeignCollisionRecord(number, identity, evidence, overlaps)

    records: list[_ForeignCollisionRecord]
    workers = min(4, len(foreign)) if getattr(reader, "parallel_safe", False) else 1
    if workers <= 1:
        records = [observe(item) for item in foreign]
    else:
        records = []
        executor = ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="source-continuity-read",
        )
        futures = [executor.submit(observe, item) for item in foreign]
        try:
            for future in as_completed(futures):
                records.append(future.result())
        except Exception:
            for future in futures:
                future.cancel()
            raise
        finally:
            executor.shutdown(wait=True, cancel_futures=True)

    ordered_records = tuple(sorted(records, key=lambda item: item.pr_number))
    colliding = tuple(
        record.pr_number for record in ordered_records if record.overlaps
    )
    census: list[tuple[int, object]] = [(target_pr, ())]
    census.extend(
        (record.pr_number, record.evidence) for record in ordered_records
    )
    snapshot = tuple(sorted(census, key=lambda item: item[0]))
    state = (
        CollisionState.OVERLAP
        if colliding
        else CollisionState.DISJOINT
        if ordered_records
        else CollisionState.NONE
    )
    return _CollisionCensusDetails(
        state,
        colliding,
        True,
        snapshot,
        ordered_records,
    )


def _collision_census(
    http_get: HTTPGet,
    token: str,
    repository: str,
    target_pr: int,
    owned_paths: tuple[str, ...],
) -> tuple[
    CollisionState,
    tuple[int, ...],
    bool,
    tuple[tuple[int, tuple[str, ...] | _SaturatedCollisionEvidence], ...],
]:
    details = _collision_census_details(
        http_get,
        token,
        repository,
        target_pr,
        owned_paths,
    )
    return (
        details.state,
        details.colliding_pr_numbers,
        details.complete,
        details.snapshot,
    )


def _revalidate_collision_census(
    http_get: HTTPGet,
    token: str,
    repository: str,
    target_pr: int,
    owned_paths: tuple[str, ...],
    first_records: tuple[_ForeignCollisionRecord, ...],
    first_colliding_pr_numbers: tuple[int, ...],
) -> tuple[bool, bool]:
    """Re-prove custody under a complete second open-PR census.

    Stable foreign identities reuse their first collision evidence. New or
    moved disjoint identities are freshly checked. A missing first-pass
    disjoint PR must be directly proven closed; a colliding PR may never move
    or disappear.
    """

    reader = _collision_reader(http_get)
    pulls, complete = _read_open_pull_roster(reader, token, repository)
    if not complete:
        return False, False

    seen_numbers: set[int] = set()
    target_seen = False
    second_foreign: dict[int, object] = {}
    for raw_pr in pulls:
        if not isinstance(raw_pr, dict):
            raise _RemoteProbeError()
        number = raw_pr.get("number")
        state = raw_pr.get("state")
        if (
            type(number) is not int
            or number <= 0
            or number in seen_numbers
            or (state is not None and state != "open")
        ):
            raise _RemoteProbeError()
        seen_numbers.add(number)
        if number == target_pr:
            target_seen = True
        else:
            second_foreign[number] = raw_pr
    if not target_seen:
        return False, True

    first_by_number = {
        record.pr_number: record for record in first_records
    }
    if len(first_by_number) != len(first_records):
        raise _RemoteProbeError()
    if tuple(sorted(
        number for number, record in first_by_number.items() if record.overlaps
    )) != tuple(sorted(first_colliding_pr_numbers)):
        raise _RemoteProbeError()

    for number, record in first_by_number.items():
        if record.identity is None:
            raise _RemoteProbeError()
        raw_pr = second_foreign.pop(number, None)
        if record.overlaps:
            if raw_pr is None:
                return False, True
            if _foreign_pull_identity(raw_pr, repository) != record.identity:
                return False, True
            continue

        if raw_pr is None:
            direct = _api(http_get=reader, token=token, endpoint=f"repos/{repository}/pulls/{number}")
            if not isinstance(direct, dict) or direct.get("state") != "closed":
                return False, True
            if _foreign_pull_identity(direct, repository).pr_number != number:
                raise _RemoteProbeError()
            continue

        second_identity = _foreign_pull_identity(raw_pr, repository)
        if second_identity == record.identity:
            continue
        _, overlaps = _foreign_collision_evidence(
            reader,
            token,
            repository,
            raw_pr,
            number,
            owned_paths,
        )
        if overlaps:
            return False, True

    for number, raw_pr in second_foreign.items():
        identity = _foreign_pull_identity(raw_pr, repository)
        if identity.pr_number != number:
            raise _RemoteProbeError()
        _, overlaps = _foreign_collision_evidence(
            reader,
            token,
            repository,
            raw_pr,
            number,
            owned_paths,
        )
        if overlaps:
            return False, True

    return True, True

def _probe_remote_prefix(
    http_get: HTTPGet,
    token: str,
    request: SourceContinuityRequest,
) -> tuple[
    tuple[object, ...],
    str,
    str,
    str,
    str,
    str,
    tuple[str, ...],
    bool,
    CollisionState,
    tuple[int, ...],
    bool,
    tuple[tuple[int, object], ...],
] | SourceContinuityRefusal:
    pr_endpoint = f"repos/{request.repository}/pulls/{request.pr_number}"
    first_pr = _api(http_get, token, pr_endpoint)
    first_identity = _pr_identity(first_pr)
    if first_identity is None:
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)

    _, _, remote_branch, remote_head, remote_repo, remote_base = first_identity
    if not _is_sha(remote_head):
        return _refusal(RefusalCode.REMOTE_FACTS_INVALID, 2)

    branch_payload = _api(
        http_get,
        token,
        _branch_endpoint(request.repository, request.branch),
    )
    if not isinstance(branch_payload, dict):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    branch_commit = branch_payload.get("commit")
    if not isinstance(branch_commit, dict) or not _is_sha(branch_commit.get("sha")):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    if branch_commit["sha"] != remote_head:
        return _refusal(RefusalCode.REMOTE_PROOF_CHANGED, 1)

    commit_payload = _api(
        http_get,
        token,
        f"repos/{request.repository}/git/commits/{remote_head}",
    )
    if not isinstance(commit_payload, dict):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    tree = commit_payload.get("tree")
    if not isinstance(tree, dict) or not _is_sha(tree.get("sha")):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    remote_tree = tree["sha"]

    base_payload = _api(
        http_get,
        token,
        _branch_endpoint(request.repository, request.base_ref),
    )
    if not isinstance(base_payload, dict):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    base_commit = base_payload.get("commit")
    if not isinstance(base_commit, dict) or not _is_sha(base_commit.get("sha")):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    current_base_head = base_commit["sha"]

    compare_payload = _api(
        http_get,
        token,
        f"repos/{request.repository}/compare/{current_base_head}...{remote_head}",
    )
    if not isinstance(compare_payload, dict):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    merge_base = compare_payload.get("merge_base_commit")
    if not isinstance(merge_base, dict) or not _is_sha(merge_base.get("sha")):
        return _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    merge_base_sha = merge_base["sha"]

    changed_paths, files_complete = _changed_paths(
        http_get,
        token,
        request.repository,
        request.pr_number,
    )
    collision_details = _collision_census_details(
        http_get,
        token,
        request.repository,
        request.pr_number,
        request.owned_paths,
    )
    collision_state = collision_details.state
    colliding_pr_numbers = collision_details.colliding_pr_numbers
    collisions_complete = collision_details.complete
    collision_snapshot = collision_details.snapshot
    return (
        first_identity,
        str(remote_repo),
        str(remote_branch),
        str(remote_base),
        remote_head,
        remote_tree,
        merge_base_sha,
        current_base_head,
        changed_paths,
        files_complete,
        collision_state,
        colliding_pr_numbers,
        collisions_complete,
        collision_snapshot,
        collision_details.foreign_records,
    )


def _parse_nul_paths(value: str) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(path for path in value.split("\0") if path)


def _same_duplicate_free_paths(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    return (
        len(left) == len(set(left))
        and len(right) == len(set(right))
        and set(left) == set(right)
    )


def _parse_ls_tree(value: str) -> tuple[RemotePathEntry, ...] | None:
    entries: list[RemotePathEntry] = []
    for record in (item for item in value.split("\0") if item):
        try:
            header, path = record.split("\t", 1)
            mode, object_type, object_sha, size_text = header.split()
            size = int(size_text)
        except (ValueError, TypeError):
            return None
        entries.append(
            RemotePathEntry(
                path=path,
                mode=mode,
                object_type=object_type,
                object_sha=object_sha,
                size=size,
            )
        )
    return tuple(entries)


def _sparse_path_is_materialized_or_unsafe(
    workspace: str,
    path: str,
    states: dict[tuple[str, ...], str],
) -> bool:
    parts = PurePosixPath(path).parts
    current = Path(workspace)
    for index, part in enumerate(parts):
        prefix = parts[: index + 1]
        state = states.get(prefix)
        if state == "missing":
            return False
        if state == "unsafe":
            return True
        if state == "directory":
            current /= part
            continue

        current /= part
        try:
            observed = os.lstat(current)
        except FileNotFoundError:
            states[prefix] = "missing"
            return False
        except OSError:
            states[prefix] = "unsafe"
            return True

        if index == len(parts) - 1:
            states[prefix] = "unsafe"
            return True
        if not stat.S_ISDIR(observed.st_mode):
            states[prefix] = "unsafe"
            return True
        states[prefix] = "directory"
    return True


def _index_has_concealed_paths(
    value: str,
    workspace: str,
    protected_paths: set[str],
) -> bool | None:
    states: dict[tuple[str, ...], str] = {}
    root_checked = False
    for record in (item for item in value.split("\0") if item):
        if len(record) < 3 or record[1] != " ":
            return None
        tag = record[0]
        path = record[2:]
        if (
            tag.upper() not in {"H", "S", "M", "R", "C", "K", "?"}
            or not _is_safe_remote_path(path)
        ):
            return None
        if tag != tag.upper():
            return True
        if tag != "S":
            continue
        if path in protected_paths:
            return True
        if not root_checked:
            try:
                root_stat = os.lstat(workspace)
            except OSError:
                return None
            if not stat.S_ISDIR(root_stat.st_mode):
                return None
            root_checked = True
        if _sparse_path_is_materialized_or_unsafe(workspace, path, states):
            return True
    return False


def _grafts_path_if_safe(runner: Runner, workspace: str) -> str | None:
    common_dir_result = _invoke_git(
        runner,
        workspace,
        "rev-parse",
        "--git-common-dir",
    )
    if common_dir_result is None or common_dir_result.returncode != 0:
        return None
    raw_common_dir = common_dir_result.stdout
    if (
        not raw_common_dir.endswith("\n")
        or raw_common_dir.count("\n") != 1
        or "\0" in raw_common_dir
    ):
        return None
    common_dir_text = raw_common_dir[:-1]
    try:
        encoded = common_dir_text.encode("utf-8")
    except UnicodeEncodeError:
        return None
    if not encoded or len(encoded) > _MAX_GIT_PATH_BYTES:
        return None

    common_dir = Path(common_dir_text)
    if not common_dir.is_absolute():
        common_dir = Path(workspace) / common_dir
    grafts_path = os.path.normpath(str(common_dir / "info" / "grafts"))
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        file_descriptor = os.open(grafts_path, flags)
    except FileNotFoundError:
        return grafts_path
    except OSError:
        return None
    try:
        grafts_stat = os.fstat(file_descriptor)
        if not stat.S_ISREG(grafts_stat.st_mode) or grafts_stat.st_size != 0:
            return None
    except OSError:
        return None
    finally:
        os.close(file_descriptor)
    return grafts_path


def _probe_local_and_entries(
    runner: Runner,
    workspace: str,
    request: SourceContinuityRequest,
    remote_head: str,
    merge_base_sha: str,
    remote_changed_paths: tuple[str, ...],
) -> tuple[LocalGitFacts, tuple[RemotePathEntry, ...]] | SourceContinuityRefusal:
    root_result = _invoke_git(runner, workspace, "rev-parse", "--show-toplevel")
    if root_result is None or root_result.returncode != 0:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
    if os.path.normpath(root_result.stdout.strip()) != os.path.normpath(workspace):
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)

    branch_result = _invoke_git(runner, workspace, "symbolic-ref", "--short", "HEAD")
    if branch_result is None:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
    if branch_result.returncode != 0:
        return _refusal(RefusalCode.LOCAL_BRANCH_MISMATCH, 1)
    branch = branch_result.stdout.strip()

    head_result = _invoke_git(runner, workspace, "rev-parse", "HEAD^{commit}")
    tree_result = _invoke_git(runner, workspace, "rev-parse", "HEAD^{tree}")
    if (
        head_result is None
        or tree_result is None
        or head_result.returncode != 0
        or tree_result.returncode != 0
    ):
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
    head_sha = head_result.stdout.strip()
    tree_sha = tree_result.stdout.strip()

    remote_object = _invoke_git(runner, workspace, "cat-file", "-e", f"{remote_head}^{{commit}}")
    if remote_object is None:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
    if remote_object.returncode != 0:
        return _refusal(RefusalCode.REMOTE_HEAD_OBJECT_MISSING, 1)

    merge_base_object = _invoke_git(
        runner,
        workspace,
        "cat-file",
        "-e",
        f"{merge_base_sha}^{{commit}}",
    )
    if merge_base_object is None or merge_base_object.returncode != 0:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)

    first_grafts_path = _grafts_path_if_safe(runner, workspace)
    if first_grafts_path is None:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)

    ancestor_result = _invoke_git(
        runner,
        workspace,
        "merge-base",
        "--is-ancestor",
        remote_head,
        "HEAD",
    )
    if ancestor_result is None or ancestor_result.returncode not in {0, 1}:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
    remote_head_is_ancestor = ancestor_result.returncode == 0

    unpushed_count = 0
    if remote_head_is_ancestor:
        count_result = _invoke_git(
            runner,
            workspace,
            "rev-list",
            "--count",
            f"{remote_head}..HEAD",
        )
        if count_result is None or count_result.returncode != 0:
            return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
        try:
            unpushed_count = int(count_result.stdout.strip())
        except ValueError:
            return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
        if unpushed_count < 0:
            return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)

    diff_controls = (
        "--no-renames",
        "--no-ext-diff",
        "--no-textconv",
        "--ignore-submodules=none",
        "--name-only",
        "-z",
    )
    filter_config = _invoke_git(
        runner,
        workspace,
        "config",
        "--null",
        "--name-only",
        "--get-regexp",
        r"^filter\..*\.(clean|process)$",
    )
    if filter_config is None or filter_config.returncode not in {0, 1}:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
    if (
        len(filter_config.stdout.encode("utf-8")) > _MAX_GIT_CONFIG_CENSUS_BYTES
        or filter_config.returncode == 0
        or filter_config.stdout
    ):
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)

    protected_paths = set(request.owned_paths)
    index_flags_before = _invoke_git(
        runner, workspace, "ls-files", "-v", "-z"
    )
    if index_flags_before is None or index_flags_before.returncode != 0:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
    concealed_before = _index_has_concealed_paths(
        index_flags_before.stdout, workspace, protected_paths
    )
    if concealed_before is None or concealed_before:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)

    unstaged = _invoke_git(runner, workspace, "diff", *diff_controls, "HEAD", "--")
    staged = _invoke_git(runner, workspace, "diff", "--cached", *diff_controls, "--")
    untracked = _invoke_git(runner, workspace, "ls-files", "--others", "-z", "--")
    if any(
        result is None or result.returncode != 0
        for result in (unstaged, staged, untracked)
    ):
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)

    local_diff = _invoke_git(
        runner,
        workspace,
        "diff",
        *diff_controls,
        f"{merge_base_sha}..{remote_head}",
        "--",
    )
    if local_diff is None or local_diff.returncode != 0:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
    local_changed_paths = _parse_nul_paths(local_diff.stdout)
    if not _same_duplicate_free_paths(local_changed_paths, remote_changed_paths):
        return _refusal(RefusalCode.REMOTE_PROOF_CHANGED, 1)

    tree_result = _invoke_git(
        runner,
        workspace,
        "ls-tree",
        "-z",
        "-l",
        remote_head,
        "--",
        *remote_changed_paths,
    )
    if tree_result is None or tree_result.returncode != 0:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
    path_entries = _parse_ls_tree(tree_result.stdout)
    if path_entries is None:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)

    index_flags_after = _invoke_git(
        runner, workspace, "ls-files", "-v", "-z"
    )
    if (
        index_flags_after is None
        or index_flags_after.returncode != 0
        or index_flags_after.stdout != index_flags_before.stdout
    ):
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)
    concealed_after = _index_has_concealed_paths(
        index_flags_after.stdout, workspace, protected_paths
    )
    if concealed_after is None or concealed_after:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)

    second_grafts_path = _grafts_path_if_safe(runner, workspace)
    if second_grafts_path is None or second_grafts_path != first_grafts_path:
        return _refusal(RefusalCode.LOCAL_PROBE_FAILED, 2)

    tracked_paths = set(_parse_nul_paths(unstaged.stdout)) | set(_parse_nul_paths(staged.stdout))
    untracked_paths = set(_parse_nul_paths(untracked.stdout))
    owned = set(request.owned_paths)
    local_facts = LocalGitFacts(
        branch=branch,
        head_sha=head_sha,
        tree_sha=tree_sha,
        remote_head_object_exists=True,
        remote_head_is_ancestor_of_local=remote_head_is_ancestor,
        unpushed_commit_count=unpushed_count,
        uncommitted_in_scope_count=len(tracked_paths & owned),
        untracked_in_scope_count=len(untracked_paths & owned),
        uncommitted_out_of_scope_count=len(tracked_paths - owned),
        untracked_out_of_scope_count=len(untracked_paths - owned),
    )
    return local_facts, path_entries


@dataclass(frozen=True)
class _RemoteRevalidation:
    current_base_head: str
    merge_base_sha: str


def _branch_head_sha(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    commit = payload.get("commit")
    if not isinstance(commit, dict) or not _is_sha(commit.get("sha")):
        return None
    return commit["sha"]


def _compare_terminal_head_sha(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    commits = payload.get("commits")
    if not isinstance(commits, list) or not commits:
        return None
    terminal = commits[-1]
    if not isinstance(terminal, dict) or not _is_sha(terminal.get("sha")):
        return None
    return terminal["sha"]


def _revalidate_moved_base(
    http_get: HTTPGet,
    token: str,
    request: SourceContinuityRequest,
    *,
    old_base_head: str,
    new_base_head: str,
    remote_head: str,
    first_merge_base_sha: str,
) -> _RemoteRevalidation | SourceContinuityRefusal:
    if not all(
        _is_sha(value)
        for value in (old_base_head, new_base_head, remote_head, first_merge_base_sha)
    ):
        raise _RemoteProbeError()
    if old_base_head == new_base_head:
        return _RemoteRevalidation(new_base_head, first_merge_base_sha)

    forward_endpoint = (
        f"repos/{request.repository}/compare/{old_base_head}...{new_base_head}"
    )
    forward = _api(http_get, token, forward_endpoint)
    if not isinstance(forward, dict):
        raise _RemoteProbeError()
    expected_forward_url = f"{_API_ROOT}/{forward_endpoint}"
    if forward.get("url") != expected_forward_url:
        raise _RemoteProbeError()
    forward_base = forward.get("base_commit")
    forward_merge_base = forward.get("merge_base_commit")
    forward_head = _compare_terminal_head_sha(forward)
    if (
        not isinstance(forward_base, dict)
        or not isinstance(forward_merge_base, dict)
        or forward_head is None
    ):
        raise _RemoteProbeError()
    if (
        forward_base.get("sha") != old_base_head
        or forward_merge_base.get("sha") != old_base_head
        or forward_head != new_base_head
    ):
        return _refusal(RefusalCode.REMOTE_PROOF_CHANGED, 1)

    refreshed_endpoint = (
        f"repos/{request.repository}/compare/{new_base_head}...{remote_head}"
    )
    refreshed = _api(http_get, token, refreshed_endpoint)
    if not isinstance(refreshed, dict):
        raise _RemoteProbeError()
    expected_refreshed_url = f"{_API_ROOT}/{refreshed_endpoint}"
    if refreshed.get("url") != expected_refreshed_url:
        raise _RemoteProbeError()
    refreshed_base = refreshed.get("base_commit")
    refreshed_merge_base = refreshed.get("merge_base_commit")
    refreshed_head = _compare_terminal_head_sha(refreshed)
    if (
        not isinstance(refreshed_base, dict)
        or not isinstance(refreshed_merge_base, dict)
        or refreshed_head is None
    ):
        raise _RemoteProbeError()
    if refreshed_base.get("sha") != new_base_head:
        raise _RemoteProbeError()
    if refreshed_head != remote_head:
        return _refusal(RefusalCode.REMOTE_PROOF_CHANGED, 1)
    refreshed_merge_base_sha = refreshed_merge_base.get("sha")
    if not _is_sha(refreshed_merge_base_sha):
        raise _RemoteProbeError()
    if refreshed_merge_base_sha != first_merge_base_sha:
        return _refusal(RefusalCode.REMOTE_PROOF_CHANGED, 1)

    final_base = _api(
        http_get,
        token,
        _branch_endpoint(request.repository, request.base_ref),
    )
    final_base_head = _branch_head_sha(final_base)
    if final_base_head is None:
        raise _RemoteProbeError()
    if final_base_head != new_base_head:
        return _refusal(RefusalCode.REMOTE_PROOF_CHANGED, 1)
    return _RemoteRevalidation(new_base_head, first_merge_base_sha)


def _remote_still_matches(
    http_get: HTTPGet,
    token: str,
    request: SourceContinuityRequest,
    first_identity: tuple[object, ...],
    remote_head: str,
    current_base_head: str,
    first_changed_paths: tuple[str, ...],
    first_files_complete: bool,
    first_collision_state: CollisionState,
    first_colliding_pr_numbers: tuple[int, ...],
    first_collisions_complete: bool,
    first_collision_snapshot: tuple[tuple[int, object], ...],
    first_collision_records: tuple[_ForeignCollisionRecord, ...] = (),
    *,
    first_merge_base_sha: str | None = None,
) -> _RemoteRevalidation | SourceContinuityRefusal | None:
    if getattr(http_get, "conditional_validation_available", False) is True:
        if not http_get.validate_unchanged(token=token):
            return _refusal(RefusalCode.REMOTE_PROOF_CHANGED, 1)
        if (
            not first_collisions_complete
            or first_collision_state is CollisionState.INCOMPLETE
        ):
            return _refusal(RefusalCode.REMOTE_CENSUS_INCOMPLETE, 2)
        if len(first_collision_snapshot) > 1 and not first_collision_records:
            return _refusal(RefusalCode.REMOTE_PROOF_CHANGED, 1)

        if any(record.identity is None for record in first_collision_records):
            second_details = _collision_census_details(
                http_get,
                token,
                request.repository,
                request.pr_number,
                request.owned_paths,
            )
            if (
                not second_details.complete
                or second_details.state is CollisionState.INCOMPLETE
            ):
                return _refusal(RefusalCode.REMOTE_CENSUS_INCOMPLETE, 2)
            collision_matches = (
                second_details.state is first_collision_state
                and second_details.colliding_pr_numbers
                == first_colliding_pr_numbers
                and second_details.snapshot == first_collision_snapshot
            )
            if not collision_matches:
                return _refusal(RefusalCode.REMOTE_PROOF_CHANGED, 1)
        else:
            collision_matches, collision_complete = _revalidate_collision_census(
                http_get,
                token,
                request.repository,
                request.pr_number,
                request.owned_paths,
                first_collision_records,
                first_colliding_pr_numbers,
            )
            if not collision_complete:
                return _refusal(RefusalCode.REMOTE_CENSUS_INCOMPLETE, 2)
            if not collision_matches:
                return _refusal(RefusalCode.REMOTE_PROOF_CHANGED, 1)

        update_reader = getattr(http_get, "base_head_update", None)
        update = update_reader() if callable(update_reader) else None
        if update is None:
            return None
        old_base_head, new_base_head = update
        if not _is_sha(first_merge_base_sha):
            raise _RemoteProbeError()
        if old_base_head != current_base_head:
            return _refusal(RefusalCode.REMOTE_PROOF_CHANGED, 1)
        return _revalidate_moved_base(
            http_get,
            token,
            request,
            old_base_head=old_base_head,
            new_base_head=new_base_head,
            remote_head=remote_head,
            first_merge_base_sha=first_merge_base_sha,
        )

    pr_endpoint = f"repos/{request.repository}/pulls/{request.pr_number}"
    second_pr = _api(http_get, token, pr_endpoint)
    second_identity = _pr_identity(second_pr)
    second_branch = _api(
        http_get,
        token,
        _branch_endpoint(request.repository, request.branch),
    )
    second_base = _api(
        http_get,
        token,
        _branch_endpoint(request.repository, request.base_ref),
    )
    second_base_head = _branch_head_sha(second_base)
    if (
        second_identity is None
        or not isinstance(second_branch, dict)
        or second_base_head is None
    ):
        raise _RemoteProbeError()
    branch_commit = second_branch.get("commit")
    if not isinstance(branch_commit, dict):
        raise _RemoteProbeError()
    if (
        second_identity != first_identity
        or branch_commit.get("sha") != remote_head
    ):
        return _refusal(RefusalCode.REMOTE_PROOF_CHANGED, 1)

    second_changed_paths, second_files_complete = _changed_paths(
        http_get,
        token,
        request.repository,
        request.pr_number,
    )
    if not first_files_complete or not second_files_complete:
        return _refusal(RefusalCode.REMOTE_CENSUS_INCOMPLETE, 2)
    if second_changed_paths != first_changed_paths:
        return _refusal(RefusalCode.REMOTE_PROOF_CHANGED, 1)

    (
        second_collision_state,
        second_colliding_pr_numbers,
        second_collisions_complete,
        second_collision_snapshot,
    ) = _collision_census(
        http_get,
        token,
        request.repository,
        request.pr_number,
        request.owned_paths,
    )
    if (
        not first_collisions_complete
        or first_collision_state is CollisionState.INCOMPLETE
        or not second_collisions_complete
        or second_collision_state is CollisionState.INCOMPLETE
    ):
        return _refusal(RefusalCode.REMOTE_CENSUS_INCOMPLETE, 2)
    if (
        second_collision_state is not first_collision_state
        or second_colliding_pr_numbers != first_colliding_pr_numbers
        or second_collision_snapshot != first_collision_snapshot
    ):
        return _refusal(RefusalCode.REMOTE_PROOF_CHANGED, 1)

    if second_base_head == current_base_head:
        return None
    if not _is_sha(first_merge_base_sha):
        raise _RemoteProbeError()
    return _revalidate_moved_base(
        http_get,
        token,
        request,
        old_base_head=current_base_head,
        new_base_head=second_base_head,
        remote_head=remote_head,
        first_merge_base_sha=first_merge_base_sha,
    )

def _is_github_id(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value <= 2_147_483_647


def _parse_branch_rules(payload: object) -> tuple[BranchRuleFact, ...]:
    if not isinstance(payload, list):
        raise _RemoteProbeError()
    rules: list[BranchRuleFact] = []
    for row in payload:
        if not isinstance(row, dict):
            raise _RemoteProbeError()
        rule_type = row.get("type")
        ruleset_id = row.get("ruleset_id")
        source_type = row.get("ruleset_source_type")
        if (
            not isinstance(rule_type, str)
            or not rule_type
            or not _is_github_id(ruleset_id)
            or not isinstance(source_type, str)
            or not source_type
        ):
            raise _RemoteProbeError()
        rules.append(
            BranchRuleFact(
                rule_type=rule_type,
                ruleset_id=ruleset_id,
                ruleset_source_type=source_type,
            )
        )
    return tuple(rules)


def _parse_ruleset(payload: object, ruleset_id: int, source_type: str) -> RulesetFact:
    if not isinstance(payload, dict):
        raise _RemoteProbeError()
    enforcement = payload.get("enforcement")
    actors = payload.get("bypass_actors")
    if (
        payload.get("id") != ruleset_id
        or payload.get("source_type") != source_type
        or not isinstance(enforcement, str)
        or not isinstance(actors, list)
    ):
        raise _RemoteProbeError()
    parsed: list[BypassActorFact] = []
    for actor in actors:
        if not isinstance(actor, dict):
            raise _RemoteProbeError()
        actor_type = actor.get("actor_type")
        bypass_mode = actor.get("bypass_mode")
        actor_id = actor.get("actor_id")
        if (
            not isinstance(actor_type, str)
            or not isinstance(bypass_mode, str)
            or not (actor_id is None or _is_github_id(actor_id))
        ):
            raise _RemoteProbeError()
        parsed.append(
            BypassActorFact(actor_type=actor_type, actor_id=actor_id, bypass_mode=bypass_mode)
        )
    return RulesetFact(
        ruleset_id=ruleset_id,
        source_type=source_type,
        enforcement=enforcement,
        bypass_actors=tuple(parsed),
    )


def _probe_writer_gate_facts(
    http_get: HTTPGet,
    token: str,
    request: WriterGateRequest,
) -> WriterGateFacts | SourceContinuityRefusal:
    branch_payload = _api(
        http_get,
        token,
        _branch_endpoint(request.repository, request.branch),
    )
    if not isinstance(branch_payload, dict):
        raise _RemoteProbeError()
    branch_commit = branch_payload.get("commit")
    # The summary `protected` flag covers branch protections *or* rulesets, so
    # it is only a shape check here. Classic protection is its own readback.
    summary_protected = branch_payload.get("protected")
    if (
        not isinstance(branch_commit, dict)
        or not _is_sha(branch_commit.get("sha"))
        or type(summary_protected) is not bool
    ):
        raise _RemoteProbeError()

    protection = _api_optional(
        http_get,
        token,
        _branch_protection_endpoint(request.repository, request.branch),
    )
    if protection is _MISSING:
        legacy_branch_protected = False
    elif isinstance(protection, dict):
        legacy_branch_protected = True
    else:
        raise _RemoteProbeError()

    rules = _parse_branch_rules(
        _api(http_get, token, _branch_rules_endpoint(request.repository, request.branch))
    )
    referenced: dict[int, str] = {}
    for rule in rules:
        # Preserve every active applicable rule. The pure verifier owns the
        # closed semantics and fails unknown future types unavailable rather
        # than letting the adapter silently erase them.
        if rule.ruleset_source_type not in {"Repository", "Organization"}:
            return _refusal(RefusalCode.REMOTE_FACTS_INVALID, 2)
        if referenced.setdefault(rule.ruleset_id, rule.ruleset_source_type) != rule.ruleset_source_type:
            return _refusal(RefusalCode.REMOTE_FACTS_INVALID, 2)

    rulesets = tuple(
        _parse_ruleset(
            _api(http_get, token, _ruleset_endpoint(request.repository, source_type, ruleset_id)),
            ruleset_id,
            source_type,
        )
        for ruleset_id, source_type in sorted(referenced.items())
    )
    return WriterGateFacts(
        repository=request.repository,
        branch=request.branch,
        branch_head_sha=branch_commit["sha"],
        legacy_branch_protected=legacy_branch_protected,
        branch_rules=rules,
        rulesets=rulesets,
        readback_complete=True,
    )


def _run_writer_gate(
    args: argparse.Namespace,
    *,
    http_get: HTTPGet,
    environ: Mapping[str, str],
    clock: Clock,
) -> int:
    try:
        request = WriterGateRequest(
            operation_key=args.operation_key,
            repository=args.repository,
            branch=args.branch,
            accepted_integration_id=args.accepted_integration_id,
            verified_at=clock(),
        )
    except Exception:
        return _emit(_refusal(RefusalCode.INVALID_REQUEST, 2))
    if not writer_gate_request_is_valid(request):
        return _emit(_refusal(RefusalCode.INVALID_REQUEST, 2))

    token = environ.get("GITHUB_TOKEN")
    if not isinstance(token, str) or not token:
        return _emit(_refusal(RefusalCode.AUTH_UNAVAILABLE, 2))

    try:
        bounded_get = _BoundedHTTPGet(http_get)
        first = _probe_writer_gate_facts(bounded_get, token, request)
        if isinstance(first, SourceContinuityRefusal):
            return _emit(first)
        result = verify_technical_writer_gate(request, first)
        if getattr(bounded_get, "conditional_validation_available", False) is True:
            unchanged = bounded_get.validate_unchanged(token=token)
        else:
            second = _probe_writer_gate_facts(bounded_get, token, request)
            if isinstance(second, SourceContinuityRefusal):
                return _emit(second)
            unchanged = second == first
        if not unchanged:
            result = _refusal(RefusalCode.REMOTE_PROOF_CHANGED, 1)
        bounded_get.check()
    except _ReadBudgetExceeded:
        result = _refusal(RefusalCode.REMOTE_CENSUS_INCOMPLETE, 2)
    except _AuthProbeError:
        result = _refusal(RefusalCode.AUTH_UNAVAILABLE, 2)
    except _RemoteProbeError:
        result = _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    except Exception:
        result = _refusal(RefusalCode.PROBE_INTERNAL_ERROR, 2)
    return _emit(result)


def _build_parser() -> _SafeArgumentParser:
    parser = _SafeArgumentParser(add_help=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify", add_help=False)
    verify.add_argument("--kind", required=True, choices=("checkpoint", "remote-complete"))
    verify.add_argument("--operation-key", required=True)
    verify.add_argument("--workspace", required=True)
    verify.add_argument("--repository", required=True)
    verify.add_argument("--pr-number", required=True, type=int)
    verify.add_argument("--branch", required=True)
    verify.add_argument("--base-ref", required=True)
    verify.add_argument("--pinned-base-sha", required=True)
    verify.add_argument("--owned-path", required=True, action="append")
    verify.add_argument(
        "--external-effect-state",
        required=True,
        choices=tuple(item.value for item in ExternalEffectState),
    )
    verify.add_argument(
        "--branch-effect-dependency",
        required=True,
        choices=tuple(item.value for item in BranchEffectDependency),
    )
    verify.add_argument("--external-effect-evidence-fingerprint", required=True)
    writer_gate = subparsers.add_parser("writer-gate", add_help=False)
    writer_gate.add_argument("--operation-key", required=True)
    writer_gate.add_argument("--repository", required=True)
    writer_gate.add_argument("--branch", required=True)
    writer_gate.add_argument("--accepted-integration-id", type=int, default=None)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: Runner = subprocess.run,
    http_get: HTTPGet = _stdlib_http_get,
    environ: Mapping[str, str] = os.environ,
    clock: Clock = _utc_now_z,
) -> int:
    try:
        args = _build_parser().parse_args(list(argv) if argv is not None else None)
    except (Exception, SystemExit):
        return _emit(_refusal(RefusalCode.INVALID_REQUEST, 2))
    if args.command == "writer-gate":
        return _run_writer_gate(args, http_get=http_get, environ=environ, clock=clock)

    try:
        workspace = args.workspace
        if not isinstance(workspace, str) or not Path(workspace).is_absolute():
            raise ValueError("invalid workspace")
        receipt_kind = {
            "checkpoint": ReceiptKind.CHECKPOINT_VERIFIED,
            "remote-complete": ReceiptKind.REMOTE_COMPLETE_VERIFIED,
        }[args.kind]
        request = SourceContinuityRequest(
            receipt_kind=receipt_kind,
            operation_key=args.operation_key,
            repository=args.repository,
            pr_number=args.pr_number,
            branch=args.branch,
            base_ref=args.base_ref,
            pinned_base_sha=args.pinned_base_sha,
            owned_paths=tuple(args.owned_path),
            verified_at=clock(),
        )
    except (Exception, SystemExit):
        return _emit(_refusal(RefusalCode.INVALID_REQUEST, 2))

    if not request_is_valid(request):
        return _emit(_refusal(RefusalCode.INVALID_REQUEST, 2))

    token = environ.get("GITHUB_TOKEN")
    if not isinstance(token, str) or not token:
        return _emit(_refusal(RefusalCode.AUTH_UNAVAILABLE, 2))

    try:
        bounded_get = _BoundedHTTPGet(
            http_get,
            subject_pull_url=(
                f"{_API_ROOT}/repos/{request.repository}/pulls/{request.pr_number}"
            ),
            base_branch_url=(
                f"{_API_ROOT}/"
                f"{_branch_endpoint(request.repository, request.base_ref)}"
            ),
        )
        remote_prefix = _probe_remote_prefix(bounded_get, token, request)
        if isinstance(remote_prefix, SourceContinuityRefusal):
            return _emit(remote_prefix)
        (
            first_identity,
            remote_repo,
            remote_branch,
            remote_base,
            remote_head,
            remote_tree,
            merge_base_sha,
            current_base_head,
            changed_paths,
            files_complete,
            collision_state,
            colliding_pr_numbers,
            collisions_complete,
            collision_snapshot,
            collision_records,
        ) = remote_prefix

        if not files_complete or not collisions_complete:
            return _emit(_refusal(RefusalCode.REMOTE_CENSUS_INCOMPLETE, 2))
        if not changed_paths:
            return _emit(_refusal(RefusalCode.REMOTE_FACTS_INVALID, 2))
        if any(path not in set(request.owned_paths) for path in changed_paths):
            return _emit(_refusal(RefusalCode.PATH_OUTSIDE_OWNERSHIP, 1))

        local_probe = _probe_local_and_entries(
            runner,
            workspace,
            request,
            remote_head,
            merge_base_sha,
            changed_paths,
        )
        if isinstance(local_probe, SourceContinuityRefusal):
            return _emit(local_probe)
        local_facts, path_entries = local_probe

        remote_refusal = _remote_still_matches(
            bounded_get,
            token,
            request,
            first_identity,
            remote_head,
            current_base_head,
            changed_paths,
            files_complete,
            collision_state,
            colliding_pr_numbers,
            collisions_complete,
            collision_snapshot,
            collision_records,
            first_merge_base_sha=merge_base_sha,
        )
        if isinstance(remote_refusal, SourceContinuityRefusal):
            return _emit(remote_refusal)
        if isinstance(remote_refusal, _RemoteRevalidation):
            current_base_head = remote_refusal.current_base_head
            merge_base_sha = remote_refusal.merge_base_sha

        remote_facts = RemoteGitFacts(
            repository=remote_repo,
            pr_number=request.pr_number,
            branch=remote_branch,
            base_ref=remote_base,
            pr_open=first_identity[0] == "open",
            pr_draft_or_hold=bool(first_identity[1]),
            head_sha=remote_head,
            tree_sha=remote_tree,
            merge_base_sha=merge_base_sha,
            current_base_head_sha=current_base_head,
            changed_paths=changed_paths,
            path_entries=path_entries,
            collision_state=collision_state,
            colliding_pr_numbers=colliding_pr_numbers,
            pagination_complete=files_complete and collisions_complete,
        )
        external = ExternalEffectEvidence(
            state=ExternalEffectState(args.external_effect_state),
            branch_dependency=BranchEffectDependency(args.branch_effect_dependency),
            evidence_fingerprint=args.external_effect_evidence_fingerprint,
        )
        result = verify_source_continuity(request, local_facts, remote_facts, external)
        bounded_get.check()
    except _ReadBudgetExceeded:
        result = _refusal(RefusalCode.REMOTE_CENSUS_INCOMPLETE, 2)
    except _AuthProbeError:
        result = _refusal(RefusalCode.AUTH_UNAVAILABLE, 2)
    except _RemoteProbeError:
        result = _refusal(RefusalCode.REMOTE_PROBE_FAILED, 2)
    except Exception:
        result = _refusal(RefusalCode.PROBE_INTERNAL_ERROR, 2)
    return _emit(result)


if __name__ == "__main__":
    raise SystemExit(main())
