"""Closed, read-only remote projection for the Chairman Control Room.

The local compositor remains the only join authority.  This module validates
that canonical document recursively, drops every local authority/navigation
field, and emits a deliberately smaller versioned contract.
"""
from __future__ import annotations

import math
import json
import os
import re
import subprocess
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from control_plane import ceo_boot_packet, chairman_control_room as ccr, executive_inbox


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


@dataclass
class CollectorConfig:
    repo_root: Path
    macro_root: Path
    interval_seconds: float = 300.0
    stale_after_seconds: float = 900.0
    timeout_seconds: float = 60.0
    max_output_bytes: int = 4 * 1024 * 1024
    runner: Any = None
    environ: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        self.repo_root = Path(self.repo_root)
        self.macro_root = Path(self.macro_root)
        if self.runner is None:
            self.runner = default_runner
        if self.environ is None:
            self.environ = os.environ
        for value in (
            self.interval_seconds, self.stale_after_seconds, self.timeout_seconds
        ):
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError("collector bounds must be finite and positive")
        if type(self.max_output_bytes) is not int or self.max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be a positive integer")


@dataclass(frozen=True)
class CollectedInputs:
    inbox: dict[str, Any]
    boot_packet: dict[str, Any]
    active_builds: dict[str, Any]
    agent_os_state: dict[str, Any] | None
    runtime_jobs: list[dict[str, Any]] | None
    observed_at: str
    freshness: Mapping[str, SourceFreshness]


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


def default_runner(argv, *, cwd: Path, timeout: float, max_bytes: int) -> dict[str, Any]:
    """Run one read-only collector command with bounded captured output."""
    try:
        proc = subprocess.Popen(
            [os.fspath(item) for item in argv],
            cwd=os.fspath(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            close_fds=True,
        )
    except OSError:
        return {"code": None, "stdout": "", "stderr": "", "timed_out": False}
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        timed_out = True
    stdout = stdout[: max_bytes + 1]
    stderr = stderr[: max_bytes + 1]
    return {
        "code": proc.returncode,
        "stdout": stdout.decode("utf-8", errors="strict") if stdout else "",
        "stderr": stderr.decode("utf-8", errors="replace") if stderr else "",
        "timed_out": timed_out,
    }


def _reject_duplicate_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise RemoteProjectionError("duplicate_json_key")
        out[key] = value
    return out


def _reject_json_constant(_value: str):
    raise RemoteProjectionError("non_finite_number")


def run_json_document(
    runner,
    argv: Sequence[str],
    *,
    cwd: Path,
    timeout: float,
    max_bytes: int,
    expected_schema: str,
) -> dict[str, Any]:
    """Run and strictly decode one bounded stdout-only JSON document."""
    try:
        result = runner(
            list(argv), cwd=cwd, timeout=timeout, max_bytes=max_bytes
        )
    except Exception as exc:  # noqa: BLE001 - converted to a stable boundary code
        raise RemoteProjectionError("active_builds_command_unavailable") from exc
    if not isinstance(result, Mapping):
        raise RemoteProjectionError("active_builds_command_failed")
    if result.get("timed_out") is True:
        raise RemoteProjectionError("active_builds_command_timed_out")
    if result.get("code") != 0:
        raise RemoteProjectionError("active_builds_command_failed")
    stdout = result.get("stdout")
    if type(stdout) is not str:
        raise RemoteProjectionError("invalid_collector_output")
    try:
        size = len(stdout.encode("utf-8"))
    except UnicodeError as exc:
        raise RemoteProjectionError("invalid_collector_output") from exc
    if size > max_bytes:
        raise RemoteProjectionError("collector_output_too_large")
    try:
        loaded = json.loads(
            stdout,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except RemoteProjectionError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RemoteProjectionError("invalid_json") from exc
    document = _require_mapping(loaded)
    _reject_non_finite(document)
    if document.get("schema") != expected_schema:
        raise RemoteProjectionError("active_builds_schema_mismatch")
    return dict(document)


def _freshness_entry(
    present: bool,
    *,
    observed_at: str,
    source_time: Any,
    unavailable_reason: str,
) -> SourceFreshness:
    if not present:
        return SourceFreshness("unavailable", observed_at, None, unavailable_reason)
    valid_source_time = source_time if type(source_time) is str else None
    return SourceFreshness("fresh", observed_at, valid_source_time, None)


def collect_once(config: CollectorConfig, *, now: str) -> CollectedInputs:
    """Collect one generation without reading the stale active-build artifact."""
    observed_at = _zulu(now)
    packet = ceo_boot_packet.build_packet(
        repo_root=config.repo_root,
        macro_root_flag=os.fspath(config.macro_root),
        environ=config.environ,
        now=observed_at,
        timeout=config.timeout_seconds,
    )
    inbox = executive_inbox.build_inbox(
        repo_root=config.repo_root,
        boot_packet=packet,
        environ=config.environ,
        now=observed_at,
        timeout=config.timeout_seconds,
    )
    active_builds = run_json_document(
        config.runner,
        [
            sys.executable,
            os.fspath(config.macro_root / "scripts" / "build_project_active_build_map.py"),
            "--json-stdout",
        ],
        cwd=config.macro_root,
        timeout=config.timeout_seconds,
        max_bytes=config.max_output_bytes,
        expected_schema=ccr.ACTIVE_BUILDS_SCHEMA,
    )
    agent_os_state, agent_os_error = ccr._read_agent_os_state(os.fspath(config.macro_root))
    runtime_jobs, runtime_error = ccr._read_runtime_jobs(config.repo_root)

    brief = packet.get("brief") if isinstance(packet, Mapping) else None
    brief_ok = isinstance(brief, Mapping) and brief.get("schema") == ccr.AGENT_OS_BRIEF_SCHEMA
    agent_state_ok = (
        isinstance(agent_os_state, Mapping)
        and agent_os_state.get("schema") == ccr.AGENT_OS_STATE_SCHEMA
    )
    freshness = {
        SOURCE_AGENT_OS_BRIEF: _freshness_entry(
            brief_ok,
            observed_at=observed_at,
            source_time=packet.get("generated_at") if isinstance(packet, Mapping) else None,
            unavailable_reason="agent_os_brief_unavailable",
        ),
        SOURCE_AGENT_OS_STATE: _freshness_entry(
            agent_state_ok,
            observed_at=observed_at,
            source_time=agent_os_state.get("generated_at") if agent_state_ok else None,
            unavailable_reason="agent_os_state_unavailable" if agent_os_error else "agent_os_state_invalid",
        ),
        SOURCE_ACTIVE_BUILDS: _freshness_entry(
            True,
            observed_at=observed_at,
            source_time=active_builds.get("collected_at"),
            unavailable_reason="active_builds_unavailable",
        ),
        SOURCE_EXECUTIVE_RUNTIME: _freshness_entry(
            runtime_jobs is not None,
            observed_at=observed_at,
            source_time=observed_at if runtime_jobs is not None else None,
            unavailable_reason="executive_runtime_unavailable" if runtime_error else "executive_runtime_invalid",
        ),
    }
    if not isinstance(packet, dict) or not isinstance(inbox, dict):
        raise RemoteProjectionError("collector_document_invalid")
    return CollectedInputs(
        inbox=inbox,
        boot_packet=packet,
        active_builds=active_builds,
        agent_os_state=dict(agent_os_state) if isinstance(agent_os_state, Mapping) else None,
        runtime_jobs=runtime_jobs,
        observed_at=observed_at,
        freshness=freshness,
    )


def compose_collected(inputs: CollectedInputs, build_identity: BuildIdentity) -> dict[str, Any]:
    """Call the canonical pure compositor exactly once for one collection."""
    canonical = ccr.compose_control_room(
        inbox=inputs.inbox,
        boot_packet=inputs.boot_packet,
        active_builds=inputs.active_builds,
        agent_os_state=inputs.agent_os_state,
        runtime_jobs=inputs.runtime_jobs,
        bindings=None,
        binding_problems=(),
        generated_at=inputs.observed_at,
    )
    return project_remote_document(
        canonical,
        observed_at=inputs.observed_at,
        freshness=inputs.freshness,
        build_identity=build_identity,
    )


class RemoteStateCache:
    """Single-flight, process-memory-only cache with a hard last-good bound."""

    def __init__(
        self,
        config: CollectorConfig,
        build_identity: BuildIdentity,
        *,
        monotonic_fn=time.monotonic,
        now_fn=ccr._utc_now_z,
    ) -> None:
        self.config = config
        self.build_identity = build_identity
        self._monotonic_fn = monotonic_fn
        self._now_fn = now_fn
        self._lock = threading.Lock()
        self._refreshing = False
        self._accepted_bytes: bytes | None = None
        self._accepted_monotonic: float | None = None
        self.last_error: str | None = None

    def refresh(self) -> bool:
        with self._lock:
            if self._refreshing:
                return False
            self._refreshing = True
        try:
            inputs = collect_once(self.config, now=self._now_fn())
            document = compose_collected(inputs, self.build_identity)
            encoded = json.dumps(
                document, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
            accepted_at = self._monotonic_fn()
        except RemoteProjectionError as exc:
            with self._lock:
                self.last_error = exc.code
            return False
        except Exception:  # noqa: BLE001 - never expose source or exception text
            with self._lock:
                self.last_error = "refresh_failed"
            return False
        else:
            with self._lock:
                self._accepted_bytes = encoded
                self._accepted_monotonic = accepted_at
                self.last_error = None
            return True
        finally:
            with self._lock:
                self._refreshing = False

    def snapshot(self) -> dict[str, Any] | None:
        now = self._monotonic_fn()
        with self._lock:
            encoded = self._accepted_bytes
            accepted_at = self._accepted_monotonic
            if encoded is None or accepted_at is None:
                return None
            if now - accepted_at > self.config.stale_after_seconds:
                return None
            copied = bytes(encoded)
        return json.loads(copied)

    def run(self, stop_event: threading.Event) -> None:
        """Refresh immediately, then at the configured 300-second cadence."""
        self.refresh()
        while not stop_event.wait(self.config.interval_seconds):
            self.refresh()
