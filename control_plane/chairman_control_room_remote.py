"""Closed, read-only remote projection for the Chairman Control Room.

The local compositor remains the only join authority.  This module validates
that canonical document recursively, drops every local authority/navigation
field, and emits a deliberately smaller versioned contract.
"""
from __future__ import annotations

import math
import json
import hashlib
import os
import re
import selectors
import signal
import subprocess
import stat
import tempfile
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from control_plane import ceo_boot_packet, chairman_control_room as ccr, executive_inbox


REMOTE_SCHEMA = "mastermind.chairman_control_room_remote.v1"
RELEASE_SCHEMA = "mastermind.control_room_build.v1"
BUILD_METADATA_FILENAME = "control_room_build.json"
ACTIVE_BUILDS_ARTIFACT = Path(
    "/var/lib/mastermind-control-room-sources/project-active-builds.json"
)
REQUIRED_RUNTIME_PATHS = frozenset({
    "app/static/chairman_control/control_room.css",
    "app/static/chairman_control/control_room.js",
    "app/static/chairman_control/remote.html",
    "common/__init__.py",
    "common/redaction.py",
    "config/strategic_state.yml",
    "control_plane/__init__.py",
    "control_plane/ceo_boot_packet.py",
    "control_plane/ceo_intent.py",
    "control_plane/chairman_control_room.py",
    "control_plane/chairman_control_room_remote.py",
    "control_plane/codex_worker.py",
    "control_plane/executive_agent_capabilities.py",
    "control_plane/executive_ambient_process.py",
    "control_plane/executive_authority.py",
    "control_plane/executive_coo_policy.py",
    "control_plane/executive_inbox.py",
    "control_plane/executive_orchestration_principal.py",
    "control_plane/executive_orchestration_result.py",
    "control_plane/executive_runtime.py",
    "control_plane/executive_supervisor.py",
    "control_plane/executive_worker_broker.py",
    "control_plane/executive_workspace.py",
    "control_plane/flags.py",
    "control_plane/operator_harness_contract.py",
    "control_plane/operator_harness_wire.py",
    "control_plane/strategic_state.py",
    "control_plane/surface_bindings.py",
    "control_plane/worker_adapter.py",
    "ops/control_room_remote/mastermind-control-room-remote.service",
    "scripts/__init__.py",
    "scripts/chairman_control_room_remote.py",
    "scripts/ohf/__init__.py",
    "scripts/ohf/redaction.py",
})
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
_PATH_RE = re.compile(
    r"/(?:Users|opt|home|var|private|etc|root|run|srv|tmp|usr)(?:/|$)"
)
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


class ReleaseError(ValueError):
    """A stable release-attestation failure safe to expose in receipts."""

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


def _release_identity(value: Any) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise ReleaseError("release_manifest_identity_invalid")
    return value


def _release_digest(value: Any) -> str:
    if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
        raise ReleaseError("release_manifest_digest_invalid")
    return value


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _release_relative_path(value: Any) -> str:
    if type(value) is not str or not value or "\\" in value or "\x00" in value:
        raise ReleaseError("release_path_invalid")
    path = Path(value)
    if path.is_absolute() or value != path.as_posix() or any(
        part in ("", ".", "..") for part in path.parts
    ):
        raise ReleaseError("release_path_invalid")
    return value


def _release_file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise ReleaseError("release_file_unavailable") from exc
    return "sha256:" + digest.hexdigest()


def _attestable_release_file(path: Path) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as exc:
        raise ReleaseError("release_file_unavailable") from exc
    if stat.S_ISLNK(info.st_mode):
        raise ReleaseError("release_symlink_forbidden")
    if not stat.S_ISREG(info.st_mode):
        raise ReleaseError("release_non_regular_file_forbidden")
    if info.st_nlink != 1:
        raise ReleaseError("release_hardlink_forbidden")
    if info.st_mode & 0o022:
        raise ReleaseError("release_writable_by_group_or_other")
    return info


def _release_files(root: Path) -> dict[str, str]:
    if not root.is_dir() or root.is_symlink():
        raise ReleaseError("release_root_invalid")
    files: dict[str, str] = {}
    try:
        members = sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix())
    except OSError as exc:
        raise ReleaseError("release_root_invalid") from exc
    for path in members:
        relative = path.relative_to(root).as_posix()
        if relative == BUILD_METADATA_FILENAME:
            continue
        try:
            info = path.lstat()
        except OSError as exc:
            raise ReleaseError("release_file_unavailable") from exc
        if stat.S_ISDIR(info.st_mode):
            continue
        _release_relative_path(relative)
        _attestable_release_file(path)
        files[relative] = _release_file_digest(path)
    return {relative: files[relative] for relative in sorted(files)}


def build_release_manifest(root: Path, *, commit: str, tree: str) -> dict[str, Any]:
    """Attest every regular file in a freshly extracted release archive."""

    accepted_commit = _release_identity(commit)
    accepted_tree = _release_identity(tree)
    files = _release_files(Path(root))
    if not REQUIRED_RUNTIME_PATHS.issubset(files):
        raise ReleaseError("required_runtime_path_missing")
    if set(files) != REQUIRED_RUNTIME_PATHS:
        raise ReleaseError("release_file_set_mismatch")
    artifact_digest = "sha256:" + hashlib.sha256(_canonical_json(files)).hexdigest()
    return {
        "artifact_digest": artifact_digest,
        "commit": accepted_commit,
        "files": files,
        "schema": RELEASE_SCHEMA,
        "tree": accepted_tree,
    }


def write_release_manifest(path: Path, manifest: Mapping[str, Any]) -> None:
    """Atomically write deterministic manifest bytes without following links."""

    destination = Path(path)
    if os.path.lexists(destination):
        _attestable_release_file(destination)
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise ReleaseError("build_metadata_parent_invalid")
    payload = _canonical_json(manifest) + b"\n"
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise ReleaseError("build_metadata_write_failed") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _strict_manifest(path: Path) -> Mapping[str, Any]:
    if path.is_symlink():
        raise ReleaseError("build_metadata_unsafe")
    _attestable_release_file(path)
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise ReleaseError("build_metadata_unavailable") from exc
    if len(payload) > 1024 * 1024:
        raise ReleaseError("build_metadata_too_large")

    def closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        document: dict[str, Any] = {}
        for key, value in pairs:
            if key in document:
                raise ReleaseError("release_manifest_duplicate_key")
            document[key] = value
        return document

    try:
        document = json.loads(
            payload,
            object_pairs_hook=closed_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ReleaseError("release_manifest_non_finite")
            ),
        )
    except ReleaseError:
        raise
    except (UnicodeError, ValueError) as exc:
        raise ReleaseError("release_manifest_invalid_json") from exc
    if not isinstance(document, Mapping):
        raise ReleaseError("release_manifest_invalid_json")
    return document


def verify_release_identity(
    root: Path,
    *,
    expected_commit: str,
    build_metadata: Path,
) -> BuildIdentity:
    """Re-hash an immutable release before any service socket is created."""

    release_root = Path(root)
    metadata = Path(build_metadata)
    _release_identity(expected_commit)
    if metadata.parent != release_root or metadata.name != BUILD_METADATA_FILENAME:
        raise ReleaseError("build_metadata_path_mismatch")
    document = _strict_manifest(metadata)
    if set(document) != {"schema", "commit", "tree", "artifact_digest", "files"}:
        raise ReleaseError("release_manifest_keys_mismatch")
    if document["schema"] != RELEASE_SCHEMA:
        raise ReleaseError("release_manifest_schema_mismatch")
    commit = _release_identity(document["commit"])
    tree = _release_identity(document["tree"])
    if commit != expected_commit:
        raise ReleaseError("release_commit_mismatch")
    artifact_digest = _release_digest(document["artifact_digest"])
    raw_files = document["files"]
    if not isinstance(raw_files, Mapping) or not all(type(key) is str for key in raw_files):
        raise ReleaseError("release_files_invalid")
    files: dict[str, str] = {}
    for relative in sorted(raw_files):
        safe_relative = _release_relative_path(relative)
        files[safe_relative] = _release_digest(raw_files[relative])
    if not REQUIRED_RUNTIME_PATHS.issubset(files):
        raise ReleaseError("required_runtime_path_missing")
    if set(files) != REQUIRED_RUNTIME_PATHS:
        raise ReleaseError("release_file_set_mismatch")
    observed_files = _release_files(release_root)
    if set(observed_files) != REQUIRED_RUNTIME_PATHS:
        raise ReleaseError("release_file_set_mismatch")
    for relative, expected_digest in files.items():
        candidate = release_root / relative
        try:
            _attestable_release_file(candidate)
        except ReleaseError as exc:
            if exc.code == "release_file_unavailable":
                raise ReleaseError("release_file_digest_mismatch") from exc
            raise
        if _release_file_digest(candidate) != expected_digest:
            raise ReleaseError("release_file_digest_mismatch")
    computed_artifact = "sha256:" + hashlib.sha256(_canonical_json(files)).hexdigest()
    if artifact_digest != computed_artifact:
        raise ReleaseError("release_artifact_digest_mismatch")
    return BuildIdentity(commit=commit, tree=tree, artifact_digest=artifact_digest)


@dataclass
class CollectorConfig:
    repo_root: Path
    macro_root: Path
    active_builds_path: Path = ACTIVE_BUILDS_ARTIFACT
    active_builds_directory_owner_uid: int = 0
    active_builds_directory_group_gid: int | None = None
    active_builds_owner_uid: int = 0
    active_builds_group_gid: int | None = None
    interval_seconds: float = 300.0
    stale_after_seconds: float = 900.0
    timeout_seconds: float = 60.0
    max_output_bytes: int = 4 * 1024 * 1024
    environ: Mapping[str, str] | None = None
    runner: Any = None
    release_commit: str | None = None

    def __post_init__(self) -> None:
        self.repo_root = Path(self.repo_root)
        self.macro_root = Path(self.macro_root)
        self.active_builds_path = Path(self.active_builds_path)
        if self.environ is None:
            self.environ = os.environ
        if self.runner is None:
            self.runner = default_runner
        if not callable(self.runner):
            raise ValueError("runner must be callable")
        if self.release_commit is not None and not _SHA_RE.fullmatch(
            self.release_commit
        ):
            raise ValueError("release_commit must be a lowercase 40-hex commit")
        for value in (
            self.interval_seconds, self.stale_after_seconds, self.timeout_seconds
        ):
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError("collector bounds must be finite and positive")
        if type(self.max_output_bytes) is not int or self.max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be a positive integer")
        for name, value in (
            ("active_builds_directory_owner_uid", self.active_builds_directory_owner_uid),
            ("active_builds_owner_uid", self.active_builds_owner_uid),
        ):
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.active_builds_group_gid is not None and (
            type(self.active_builds_group_gid) is not int
            or self.active_builds_group_gid < 0
        ):
            raise ValueError("active_builds_group_gid must be a non-negative integer")
        if self.active_builds_directory_group_gid is not None and (
            type(self.active_builds_directory_group_gid) is not int
            or self.active_builds_directory_group_gid < 0
        ):
            raise ValueError(
                "active_builds_directory_group_gid must be a non-negative integer"
            )


@dataclass(frozen=True)
class CollectedInputs:
    inbox: dict[str, Any]
    boot_packet: dict[str, Any]
    active_builds: dict[str, Any] | None
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


def _project_agent_os_freeform(value: Any) -> str | None:
    """Redact private prose while preserving the closed projection shape."""

    accepted = _optional_string(value)
    if accepted is None:
        return None
    try:
        _reject_sensitive_values(accepted)
    except RemoteProjectionError as exc:
        if exc.code != "sensitive_value":
            raise
        return "agent_os_detail_redacted"
    return accepted


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
        "title": _project_agent_os_freeform(row["title"]),
        "status": _optional_string(row["status"]),
        "program": _project_agent_os_freeform(row["program"]),
        "next_action": _project_agent_os_freeform(row["next_action"]),
        "state": _optional_string(row["state"]),
        "reason_code": _optional_string(row["reason_code"]),
        "reason": _project_agent_os_freeform(row["reason"]),
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


def _terminate_process_group(proc) -> bool:
    """Kill an owned process group and reap its leader with bounded waits only."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        if proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass
    try:
        proc.wait(timeout=0.5)
        return True
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=0.5)
        return True
    except subprocess.TimeoutExpired:
        return False


def default_runner(argv, *, cwd: Path, timeout: float, max_bytes: int) -> dict[str, Any]:
    """Run a command with incremental hard-capped capture and prompt reap."""
    try:
        proc = subprocess.Popen(
            [os.fspath(item) for item in argv],
            cwd=os.fspath(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            close_fds=True,
            start_new_session=True,
        )
    except OSError:
        return {
            "code": None,
            "stdout": "",
            "stderr": "",
            "timed_out": False,
            "limit_exceeded": False,
            "invalid_utf8": False,
        }

    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    selector = selectors.DefaultSelector()
    for name, pipe in (("stdout", proc.stdout), ("stderr", proc.stderr)):
        if pipe is not None:
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ, name)
    deadline = time.monotonic() + timeout
    timed_out = False
    limit_exceeded = False
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                _terminate_process_group(proc)
                break
            ready = selector.select(timeout=min(remaining, 0.1))
            for key, _mask in ready:
                name = key.data
                allowance = max_bytes + 1 - len(buffers[name])
                try:
                    chunk = os.read(key.fileobj.fileno(), min(65536, max(1, allowance)))
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                buffers[name].extend(chunk)
                if len(buffers[name]) > max_bytes:
                    del buffers[name][max_bytes:]
                    limit_exceeded = True
                    _terminate_process_group(proc)
                    break
            if limit_exceeded:
                break
        if proc.poll() is None and not (timed_out or limit_exceeded):
            remaining = max(0.0, deadline - time.monotonic())
            try:
                proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                timed_out = True
                _terminate_process_group(proc)
    finally:
        selector.close()
        for pipe in (proc.stdout, proc.stderr):
            if pipe is not None and not pipe.closed:
                pipe.close()
        # The leader may have exited cleanly after forking a quiet descendant
        # which closed both capture streams.  The runner owns the whole session,
        # so always terminate that process group before returning.
        _terminate_process_group(proc)

    invalid_utf8 = False
    try:
        stdout = bytes(buffers["stdout"]).decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        stdout = ""
        invalid_utf8 = True
    try:
        stderr = bytes(buffers["stderr"]).decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        stderr = ""
        invalid_utf8 = True
    return {
        "code": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "timed_out": timed_out,
        "limit_exceeded": limit_exceeded,
        "invalid_utf8": invalid_utf8,
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
    if result.get("limit_exceeded") is True:
        raise RemoteProjectionError("collector_output_too_large")
    if result.get("invalid_utf8") is True:
        raise RemoteProjectionError("invalid_collector_output")
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


def classify_source_freshness(
    source: str,
    *,
    present: bool,
    observed_at: str,
    source_time: Any,
    stale_after_seconds: float,
) -> SourceFreshness:
    """Classify one source against the single collection-generation clock."""

    if not present:
        return SourceFreshness("unavailable", observed_at, None, f"{source}_unavailable")
    if source_time is None:
        return SourceFreshness(
            "unavailable", observed_at, None, f"{source}_source_time_missing"
        )
    if type(source_time) is not str:
        return SourceFreshness(
            "unavailable", observed_at, None, f"{source}_source_time_malformed"
        )
    if source_time.endswith("Z"):
        parseable_source_time = source_time[:-1] + "+00:00"
        normalized_source_time = source_time
    elif source_time.endswith("+00:00"):
        parseable_source_time = source_time
        normalized_source_time = source_time[:-6] + "Z"
    else:
        try:
            datetime.fromisoformat(source_time)
        except ValueError:
            reason = f"{source}_source_time_malformed"
        else:
            reason = f"{source}_source_time_non_utc"
        return SourceFreshness("unavailable", observed_at, None, reason)
    try:
        generation = datetime.fromisoformat(observed_at[:-1] + "+00:00")
        source_clock = datetime.fromisoformat(parseable_source_time)
    except ValueError:
        return SourceFreshness(
            "unavailable", observed_at, None, f"{source}_source_time_malformed"
        )
    if source_clock.utcoffset() is None or source_clock.utcoffset().total_seconds() != 0:
        return SourceFreshness(
            "unavailable", observed_at, None, f"{source}_source_time_non_utc"
        )
    age = (generation - source_clock).total_seconds()
    if age < 0:
        return SourceFreshness(
            "unavailable",
            observed_at,
            normalized_source_time,
            f"{source}_source_time_future",
        )
    if age > stale_after_seconds:
        return SourceFreshness(
            "stale", observed_at, normalized_source_time, f"{source}_source_over_age"
        )
    return SourceFreshness("fresh", observed_at, normalized_source_time, None)


def _artifact_failure(observed_at: str, reason: str) -> tuple[None, SourceFreshness]:
    return None, SourceFreshness("unavailable", observed_at, None, reason)


def read_active_builds_artifact(
    config: CollectorConfig, *, observed_at: str
) -> tuple[dict[str, Any] | None, SourceFreshness]:
    """Read the fixed external producer artifact without following links."""

    path = config.active_builds_path
    try:
        parent_info = path.parent.lstat()
    except FileNotFoundError:
        return _artifact_failure(observed_at, "active_builds_not_found")
    except OSError:
        return _artifact_failure(observed_at, "active_builds_path_unsafe")
    if (
        stat.S_ISLNK(parent_info.st_mode)
        or not stat.S_ISDIR(parent_info.st_mode)
        or parent_info.st_uid != config.active_builds_directory_owner_uid
        or (
            config.active_builds_directory_group_gid is not None
            and parent_info.st_gid != config.active_builds_directory_group_gid
        )
        or stat.S_IMODE(parent_info.st_mode) != 0o750
    ):
        return _artifact_failure(observed_at, "active_builds_path_unsafe")
    try:
        before = path.lstat()
    except FileNotFoundError:
        return _artifact_failure(observed_at, "active_builds_not_found")
    except OSError:
        return _artifact_failure(observed_at, "active_builds_path_unsafe")
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        return _artifact_failure(observed_at, "active_builds_path_unsafe")
    if before.st_nlink != 1:
        return _artifact_failure(observed_at, "active_builds_hardlink_forbidden")
    if before.st_uid != config.active_builds_owner_uid:
        return _artifact_failure(observed_at, "active_builds_owner_mismatch")
    if (
        config.active_builds_group_gid is not None
        and before.st_gid != config.active_builds_group_gid
    ):
        return _artifact_failure(observed_at, "active_builds_group_mismatch")
    if stat.S_IMODE(before.st_mode) != 0o640:
        return _artifact_failure(observed_at, "active_builds_mode_unsafe")
    if not hasattr(os, "O_NOFOLLOW"):
        return _artifact_failure(observed_at, "active_builds_nofollow_unavailable")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return _artifact_failure(observed_at, "active_builds_not_found")
    except OSError:
        return _artifact_failure(observed_at, "active_builds_path_unsafe")
    try:
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            return _artifact_failure(observed_at, "active_builds_path_changed")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(65536, config.max_output_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > config.max_output_bytes:
                return _artifact_failure(observed_at, "active_builds_too_large")
    finally:
        os.close(descriptor)
    try:
        payload = b"".join(chunks).decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return _artifact_failure(observed_at, "active_builds_invalid_utf8")
    try:
        document = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except RemoteProjectionError as exc:
        reason = {
            "duplicate_json_key": "active_builds_duplicate_json_key",
            "non_finite_number": "active_builds_non_finite_number",
        }.get(exc.code, "active_builds_invalid_json")
        return _artifact_failure(observed_at, reason)
    except (TypeError, ValueError, json.JSONDecodeError):
        return _artifact_failure(observed_at, "active_builds_invalid_json")
    if not isinstance(document, Mapping):
        return _artifact_failure(observed_at, "active_builds_invalid_json")
    if document.get("schema") != ccr.ACTIVE_BUILDS_SCHEMA:
        return _artifact_failure(observed_at, "active_builds_schema_mismatch")
    freshness = classify_source_freshness(
        SOURCE_ACTIVE_BUILDS,
        present=True,
        observed_at=observed_at,
        source_time=document.get("collected_at"),
        stale_after_seconds=config.stale_after_seconds,
    )
    if freshness.state == "unavailable":
        return None, freshness
    return dict(document), freshness


def _runtime_source_time(config: CollectorConfig) -> str | None:
    try:
        info = (config.repo_root / executive_inbox.DB_RELATIVE_PATH).lstat()
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode):
        return None
    return datetime.fromtimestamp(info.st_mtime, timezone.utc).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")


def _sanitize_collected_degraded(
    document: dict[str, Any], *, source: str
) -> dict[str, Any]:
    """Replace only sensitive source diagnostics before canonical composition."""

    sanitized = dict(document)
    entries = document.get("degraded")
    if not isinstance(entries, list):
        return sanitized
    public_entries: list[Any] = []
    for entry in entries:
        try:
            _reject_sensitive_values(entry)
        except RemoteProjectionError:
            public_entries.append(f"{source}_detail_redacted")
        else:
            public_entries.append(entry)
    sanitized["degraded"] = public_entries
    return sanitized


def collect_once(config: CollectorConfig, *, now: str) -> CollectedInputs:
    """Collect one generation from independent read-only source boundaries."""
    observed_at = _zulu(now)
    packet = ceo_boot_packet.build_packet(
        repo_root=config.repo_root,
        macro_root_flag=os.fspath(config.macro_root),
        environ=config.environ,
        now=observed_at,
        timeout=config.timeout_seconds,
        runner=config.runner,
        max_output_bytes=config.max_output_bytes,
        mastermind_identity=(
            {"sha": config.release_commit, "branch": "immutable-release"}
            if config.release_commit is not None
            else None
        ),
    )
    inbox = executive_inbox.build_inbox(
        repo_root=config.repo_root,
        boot_packet=packet,
        environ=config.environ,
        now=observed_at,
        timeout=config.timeout_seconds,
    )
    if isinstance(packet, dict):
        packet = _sanitize_collected_degraded(packet, source="boot_packet")
    if isinstance(inbox, dict):
        inbox = _sanitize_collected_degraded(inbox, source="executive_inbox")
    active_builds, active_builds_freshness = read_active_builds_artifact(
        config, observed_at=observed_at
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
        SOURCE_AGENT_OS_BRIEF: classify_source_freshness(
            SOURCE_AGENT_OS_BRIEF,
            present=brief_ok,
            observed_at=observed_at,
            source_time=brief.get("generated_at") if brief_ok else None,
            stale_after_seconds=config.stale_after_seconds,
        ),
        SOURCE_AGENT_OS_STATE: classify_source_freshness(
            SOURCE_AGENT_OS_STATE,
            present=agent_state_ok,
            observed_at=observed_at,
            source_time=agent_os_state.get("generated_at") if agent_state_ok else None,
            stale_after_seconds=config.stale_after_seconds,
        ),
        SOURCE_ACTIVE_BUILDS: active_builds_freshness,
        SOURCE_EXECUTIVE_RUNTIME: classify_source_freshness(
            SOURCE_EXECUTIVE_RUNTIME,
            present=runtime_jobs is not None,
            observed_at=observed_at,
            source_time=_runtime_source_time(config) if runtime_jobs is not None else None,
            stale_after_seconds=config.stale_after_seconds,
        ),
    }
    if not isinstance(packet, dict) or not isinstance(inbox, dict):
        raise RemoteProjectionError("collector_document_invalid")
    packet_for_composition = dict(packet)
    if freshness[SOURCE_AGENT_OS_BRIEF].state == "unavailable":
        packet_for_composition["brief"] = None
    agent_state_for_composition = (
        dict(agent_os_state)
        if freshness[SOURCE_AGENT_OS_STATE].state != "unavailable"
        and isinstance(agent_os_state, Mapping)
        else None
    )
    runtime_for_composition = (
        runtime_jobs
        if freshness[SOURCE_EXECUTIVE_RUNTIME].state != "unavailable"
        else None
    )
    return CollectedInputs(
        inbox=inbox,
        boot_packet=packet_for_composition,
        active_builds=active_builds,
        agent_os_state=agent_state_for_composition,
        runtime_jobs=runtime_for_composition,
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
