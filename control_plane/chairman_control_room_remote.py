"""Closed, read-only remote projection for the Chairman Control Room.

The local compositor remains the only join authority.  This module validates
that canonical document recursively, drops every local authority/navigation
field, and emits a deliberately smaller versioned contract.
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit

from control_plane import chairman_control_room as ccr


REMOTE_SCHEMA = "mastermind.chairman_control_room_remote.v1"
SOURCE_AGENT_OS_BRIEF = "agent_os_brief"
SOURCE_AGENT_OS_STATE = "agent_os_state"
SOURCE_ACTIVE_BUILDS = "active_builds"
SOURCE_EXECUTIVE_RUNTIME = "executive_runtime"
COLLECTOR_SOURCES = frozenset({
    SOURCE_AGENT_OS_BRIEF,
    SOURCE_AGENT_OS_STATE,
    SOURCE_ACTIVE_BUILDS,
    SOURCE_EXECUTIVE_RUNTIME,
})

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PRIVATE_HOST_RE = re.compile(
    r"(?i)(?:\blocalhost\b|\b[a-z0-9.-]+\.(?:local|internal)\b|"
    r"\b10(?:\.\d{1,3}){3}\b|\b192\.168(?:\.\d{1,3}){2}\b|"
    r"\b172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}\b)"
)
_PATH_RE = re.compile(r"(?:^|\s)/(?:Users|opt|home|var|private|etc)/")
_SESSION_RE = re.compile(r"(?i)\b(?:provider[_ -]?session(?:[_ -]?id)?|session[_ -]?identity)\s*[:=]")

_ATTENTION_INPUT_KEYS = frozenset({
    "attention_id", "business_impact", "depth", "escalation_target", "evidence",
    "existing_next_actions", "job_id", "kind", "owner_seat", "parent_job_id",
    "reason", "review_required", "reviews_job_id", "root_job_id", "source",
    "status", "target", "workstream", "title", "summary", "reason_code",
})
_WORK_INPUT_KEYS = frozenset({
    "work_ref", "agent_os", "executive", "github", "attention_ids", "bindings",
    "disagreements",
})
_AGENT_OS_KEYS = frozenset({
    "workstream", "title", "status", "program", "next_action", "state",
    "reason_code", "reason", "depends_on", "unmet_dependencies", "source",
})
_EXECUTIVE_KEYS = frozenset({"jobs", "joined_by"})
_JOB_KEYS = frozenset({"job_id", "status", "workstream"})
_GITHUB_KEYS = frozenset({"prs"})
_PR_KEYS = frozenset({"repo", "number", "url", "title", "branch", "draft", "merge_state"})


class RemoteProjectionError(ValueError):
    """A stable, non-secret rejection at the remote projection boundary."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SourceFreshness:
    state: Literal["fresh", "stale", "unavailable"]
    observed_at: str | None
    source_time: str | None
    reason: str | None


@dataclass(frozen=True)
class BuildIdentity:
    commit: str
    tree: str
    artifact_digest: str


def _require_mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RemoteProjectionError("invalid_type")
    if not all(type(key) is str for key in value):
        raise RemoteProjectionError("invalid_type")
    return value


def _require_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise RemoteProjectionError("invalid_type")
    return value


def _require_exact_keys(value: Any, expected: frozenset[str] | set[str]) -> Mapping[str, Any]:
    row = _require_mapping(value)
    if set(row) != set(expected):
        raise RemoteProjectionError("unexpected_keys")
    return row


def _optional_string(value: Any) -> str | None:
    if value is not None and type(value) is not str:
        raise RemoteProjectionError("invalid_type")
    return value


def _string(value: Any) -> str:
    if type(value) is not str:
        raise RemoteProjectionError("invalid_type")
    return value


def _bool(value: Any) -> bool:
    if type(value) is not bool:
        raise RemoteProjectionError("invalid_type")
    return value


def _integer(value: Any) -> int:
    if type(value) is not int:
        raise RemoteProjectionError("invalid_type")
    return value


def _string_list(value: Any) -> list[str]:
    rows = _require_list(value)
    return [_string(item) for item in rows]


def _zulu(value: Any) -> str:
    text = _string(value)
    if not text.endswith("Z"):
        raise RemoteProjectionError("invalid_timestamp")
    try:
        datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise RemoteProjectionError("invalid_timestamp") from exc
    return text


def _reject_non_finite(value: Any) -> None:
    if type(value) is float and not math.isfinite(value):
        raise RemoteProjectionError("non_finite_number")
    if isinstance(value, Mapping):
        for key, child in value.items():
            _reject_non_finite(key)
            _reject_non_finite(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _reject_non_finite(child)


def _reject_sensitive_values(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            _reject_sensitive_values(key)
            _reject_sensitive_values(child)
        return
    if isinstance(value, (list, tuple)):
        for child in value:
            _reject_sensitive_values(child)
        return
    if type(value) is not str:
        return
    if (
        _EMAIL_RE.search(value)
        or _PRIVATE_HOST_RE.search(value)
        or _PATH_RE.search(value)
        or _SESSION_RE.search(value)
        or "X-CCR-Token" in value
        or "traceback" in value.lower()
    ):
        raise RemoteProjectionError("sensitive_value")


def _project_pr(value: Any) -> dict[str, Any]:
    row = _require_exact_keys(value, _PR_KEYS)
    url = _string(row["url"])
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "github.com" or not parsed.path.startswith("/"):
        raise RemoteProjectionError("url_not_allowed")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RemoteProjectionError("url_not_allowed")
    return {
        "repo": _string(row["repo"]),
        "number": _integer(row["number"]),
        "url": url,
        "title": _string(row["title"]),
        "branch": _string(row["branch"]),
        "draft": _bool(row["draft"]),
        "merge_state": _optional_string(row["merge_state"]),
    }


def _project_attention(value: Any) -> dict[str, list[dict[str, Any]]]:
    buckets = _require_exact_keys(value, {"chairman", "ceo", "coo"})
    out: dict[str, list[dict[str, Any]]] = {}
    for target in ("chairman", "ceo", "coo"):
        projected: list[dict[str, Any]] = []
        for item in _require_list(buckets[target]):
            row = _require_mapping(item)
            if not set(row).issubset(_ATTENTION_INPUT_KEYS):
                raise RemoteProjectionError("unexpected_keys")
            required = {"attention_id", "kind", "workstream"}
            if not required.issubset(row):
                raise RemoteProjectionError("unexpected_keys")
            kind = _string(row["kind"])
            summary = row.get("summary", row.get("reason"))
            status = row.get("status")
            reason_code = row.get("reason_code") or kind
            projected.append({
                "attention_id": _string(row["attention_id"]),
                "kind": kind,
                "title": _optional_string(row.get("title")) or kind.replace("_", " ").title(),
                "summary": _optional_string(summary),
                "workstream": _optional_string(row.get("workstream")),
                "state": _optional_string(status),
                "reason_code": _optional_string(reason_code),
            })
        out[target] = projected
    return out


def _project_agent_os(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    row = _require_exact_keys(value, _AGENT_OS_KEYS)
    return {
        "workstream": _string(row["workstream"]),
        "title": _optional_string(row["title"]),
        "status": _optional_string(row["status"]),
        "program": _optional_string(row["program"]),
        "next_action": _optional_string(row["next_action"]),
        "state": _optional_string(row["state"]),
        "reason_code": _optional_string(row["reason_code"]),
        "reason": _optional_string(row["reason"]),
        "depends_on": _string_list(row["depends_on"]),
        "unmet_dependencies": _string_list(row["unmet_dependencies"]),
    }


def _project_work(value: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in _require_list(value):
        row = _require_exact_keys(item, _WORK_INPUT_KEYS)
        executive = _require_exact_keys(row["executive"], _EXECUTIVE_KEYS)
        jobs = []
        for job_value in _require_list(executive["jobs"]):
            job = _require_exact_keys(job_value, _JOB_KEYS)
            jobs.append({key: _string(job[key]) for key in ("job_id", "status", "workstream")})
        github = _require_exact_keys(row["github"], _GITHUB_KEYS)
        out.append({
            "work_ref": _string(row["work_ref"]),
            "agent_os": _project_agent_os(row["agent_os"]),
            "executive": {
                "jobs": jobs,
                "joined_by": _optional_string(executive["joined_by"]),
            },
            "github": {"prs": [_project_pr(pr) for pr in _require_list(github["prs"])]},
            "attention_ids": _string_list(row["attention_ids"]),
            "disagreements": _string_list(row["disagreements"]),
        })
    return out


def _project_freshness(value: Any) -> dict[str, dict[str, Any]]:
    row = _require_mapping(value)
    if set(row) != COLLECTOR_SOURCES:
        raise RemoteProjectionError("freshness_sources_mismatch")
    out = {}
    for name in sorted(COLLECTOR_SOURCES):
        entry = row[name]
        if not isinstance(entry, SourceFreshness):
            raise RemoteProjectionError("invalid_type")
        if entry.state not in ("fresh", "stale", "unavailable"):
            raise RemoteProjectionError("invalid_freshness_state")
        out[name] = {
            "state": entry.state,
            "observed_at": _zulu(entry.observed_at) if entry.observed_at is not None else None,
            "source_time": _zulu(entry.source_time) if entry.source_time is not None else None,
            "reason": _optional_string(entry.reason),
        }
    return out


def _project_identity(value: Any) -> dict[str, str]:
    if not isinstance(value, BuildIdentity):
        raise RemoteProjectionError("invalid_build_identity")
    if not _SHA_RE.fullmatch(value.commit) or not _SHA_RE.fullmatch(value.tree):
        raise RemoteProjectionError("invalid_build_identity")
    if not _DIGEST_RE.fullmatch(value.artifact_digest):
        raise RemoteProjectionError("invalid_build_identity")
    return asdict(value)


def project_remote_document(
    canonical: Mapping[str, Any],
    *,
    observed_at: str,
    freshness: Mapping[str, SourceFreshness],
    build_identity: BuildIdentity,
) -> dict[str, Any]:
    """Validate and project one canonical document through a closed allowlist."""
    _reject_non_finite(canonical)
    source = _require_exact_keys(canonical, ccr.OUTPUT_KEYS)
    if source["schema"] != ccr.SCHEMA:
        raise RemoteProjectionError("schema_mismatch")
    _string_list(source["degraded"])
    # These local-only branches are still type-checked so malformed future
    # canonical documents cannot be accepted merely because they are omitted.
    _require_mapping(source["sources"])
    _require_list(source["unbound_surfaces"])
    _require_list(source["binding_conflicts"])
    projected = {
        "schema": REMOTE_SCHEMA,
        "observed_at": _zulu(observed_at),
        "code_identity": _project_identity(build_identity),
        "source_freshness": _project_freshness(freshness),
        "degraded": _string_list(source["degraded"]),
        "attention": _project_attention(source["attention"]),
        "work": _project_work(source["work"]),
        "unjoined_open_prs": [_project_pr(pr) for pr in _require_list(source["unjoined_open_prs"])],
    }
    _reject_sensitive_values(projected)
    return projected
