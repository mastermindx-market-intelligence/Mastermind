"""Durable SQLite worker runtime for the Mastermind Executive OS.

The database is the only lifecycle authority.  Provider execution is performed
explicitly by a separate bounded adapter/supervisor; this module owns the durable
identity, authority receipt, process reference, lease, and result reconstruction
state around that execution.  All linked Job/Attempt/WorkerQuotaClass changes and
their Event receipt commit in one ``BEGIN IMMEDIATE`` transaction.

Phase 1A compatibility is intentional.  ``Runtime.workers``, ``Runtime.jobs``
and ``Runtime.broker`` retain the small registry API while delegating every
active-attempt mutation through a lease token and monotonically increasing
quota-class fence.  Tokens are stored in the protected database but are never
included in events or public ``to_dict`` output.
"""
from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence
from uuid import uuid4

from control_plane.executive_authority import (
    AuthorityDenied,
    AuthorityPolicyError,
    ExecutiveAuthorityPolicy,
)


SCHEMA_VERSION = 2
DEFAULT_LEASE_SECONDS = 60
DEFAULT_BUSY_TIMEOUT_MS = 5_000
_ROOT = Path(__file__).resolve().parent.parent
_DB_RELATIVE_PATH = Path("data") / "control_plane" / "executive.sqlite3"
_WORKER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_COMMAND_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ROUTING_VALUE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SEAT_RE = re.compile(r"^[a-z][a-z0-9._-]{0,31}$")
_JOB_SEATS = frozenset({"coo", "ceo", "chairman"})
_BUSINESS_IMPACTS = frozenset({"routine", "material", "critical"})
_ESCALATION_RANK = {"coo": 0, "ceo": 1, "chairman": 2}
_COST_CLASS_RANK = {"small": 0, "default": 1, "frontier": 2}
_MAX_JOB_DEPTH = 64


class RuntimeProofError(RuntimeError):
    """Base error for operator-visible Executive runtime failures."""


class PersistenceError(RuntimeProofError):
    """The durable SQLite state could not be safely opened or committed."""


class StateConflict(RuntimeProofError):
    """The operation conflicts with the current state machine or lease."""


class WorkerStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"
    DRAINING = "DRAINING"
    RATE_LIMITED = "RATE_LIMITED"
    OFFLINE = "OFFLINE"
    ERROR = "ERROR"


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    CHECKPOINTED = "CHECKPOINTED"
    RATE_LIMITED = "RATE_LIMITED"
    FAILED = "FAILED"
    LOST = "LOST"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class AttemptStatus(str, Enum):
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    CHECKPOINTED = "CHECKPOINTED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    RATE_LIMITED = "RATE_LIMITED"
    FAILED = "FAILED"
    LOST = "LOST"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


_LEASE_ACTIVE_ATTEMPT_STATUSES = {
    AttemptStatus.CLAIMED,
    AttemptStatus.RUNNING,
    AttemptStatus.CHECKPOINTED,
    AttemptStatus.CANCEL_REQUESTED,
}
_WORKER_MUTABLE_ATTEMPT_STATUSES = {
    AttemptStatus.CLAIMED,
    AttemptStatus.RUNNING,
    AttemptStatus.CHECKPOINTED,
}
_TERMINAL_ATTEMPT_STATUSES = {
    AttemptStatus.RATE_LIMITED,
    AttemptStatus.FAILED,
    AttemptStatus.LOST,
    AttemptStatus.COMPLETED,
    AttemptStatus.CANCELLED,
}
_TERMINAL_JOB_STATUSES = {
    JobStatus.RATE_LIMITED,
    JobStatus.FAILED,
    JobStatus.LOST,
    JobStatus.COMPLETED,
    JobStatus.CANCELLED,
}
_ACTIVE_JOB_STATUS_BY_ATTEMPT = {
    AttemptStatus.CLAIMED: JobStatus.RUNNING,
    AttemptStatus.RUNNING: JobStatus.RUNNING,
    AttemptStatus.CHECKPOINTED: JobStatus.CHECKPOINTED,
    AttemptStatus.CANCEL_REQUESTED: JobStatus.CANCEL_REQUESTED,
}


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise StateConflict(f"value is not valid JSON data: {exc}") from exc


def _json_loads(value: str | None, *, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError) as exc:
        raise PersistenceError(f"invalid persisted JSON: {exc}") from exc


def _iso(timestamp_ms: int | None) -> str:
    if timestamp_ms is None:
        return ""
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat(
        timespec="seconds"
    )


def _enum_value(value: str | Enum, enum_type: type[Enum]) -> str:
    try:
        return str(enum_type(value).value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(str(item.value) for item in enum_type)
        raise StateConflict(
            f"invalid {enum_type.__name__} {value!r}; expected one of {allowed}"
        ) from exc


def _normalise_capabilities(
    values: str | list[str] | tuple[str, ...] | None,
) -> list[str]:
    if isinstance(values, str):
        values = [values]
    elif values is not None and not isinstance(values, (list, tuple)):
        raise StateConflict("capabilities must be a string or list")
    return sorted(
        {str(value).strip().lower() for value in (values or []) if str(value).strip()}
    )


def _normalise_constraints(value: dict[str, Any] | None) -> dict[str, Any]:
    if value is not None and not isinstance(value, dict):
        raise StateConflict("job constraints must be a mapping")
    raw = value or {}
    provider = str(raw.get("provider") or "").strip().lower()
    capabilities = _normalise_capabilities(
        raw.get("required_capabilities") or raw.get("capabilities") or []
    )
    quota_values = raw.get("eligible_quota_classes") or raw.get("quota_classes") or []
    if raw.get("quota_class"):
        quota_values = [raw["quota_class"]]
    if isinstance(quota_values, str):
        quota_values = [quota_values]
    if not isinstance(quota_values, (list, tuple)):
        raise StateConflict("eligible_quota_classes must be a list")
    eligible = sorted(
        {str(item).strip().lower() for item in quota_values if str(item).strip()}
    ) or ["default"]
    result: dict[str, Any] = {"eligible_quota_classes": eligible}

    aliases_raw = raw.get("preferred_model_aliases") or []
    if isinstance(aliases_raw, str):
        aliases_raw = [aliases_raw]
    if not isinstance(aliases_raw, (list, tuple)) or len(aliases_raw) > 16:
        raise StateConflict("preferred_model_aliases must be a bounded list")
    aliases: list[str] = []
    for item in aliases_raw:
        alias = str(item).strip().lower()
        if _ROUTING_VALUE_RE.fullmatch(alias) is None:
            raise StateConflict("preferred_model_aliases contains an invalid alias")
        if alias not in aliases:
            aliases.append(alias)
    if aliases:
        result["preferred_model_aliases"] = aliases

    excluded_raw = raw.get("excluded_worker_ids") or []
    if isinstance(excluded_raw, str):
        excluded_raw = [excluded_raw]
    if not isinstance(excluded_raw, (list, tuple)) or len(excluded_raw) > 16:
        raise StateConflict("excluded_worker_ids must be a bounded list")
    excluded: list[str] = []
    for item in excluded_raw:
        worker_id = str(item).strip()
        if _WORKER_ID_RE.fullmatch(worker_id) is None:
            raise StateConflict("excluded_worker_ids contains an invalid worker id")
        if worker_id not in excluded:
            excluded.append(worker_id)
    if excluded:
        result["excluded_worker_ids"] = excluded

    for key in ("task_kind", "risk", "ambiguity", "routing_policy_version"):
        normalized = str(raw.get(key) or "").strip().lower()
        if normalized:
            if _ROUTING_VALUE_RE.fullmatch(normalized) is None:
                raise StateConflict(f"constraint {key} must be a bounded identifier")
            result[key] = normalized

    if aliases and "routing_policy_version" not in result:
        raise StateConflict(
            "preferred_model_aliases requires routing_policy_version"
        )

    reason_codes_raw = raw.get("routing_reason_codes") or []
    if isinstance(reason_codes_raw, str):
        reason_codes_raw = [reason_codes_raw]
    if not isinstance(reason_codes_raw, (list, tuple)) or len(reason_codes_raw) > 16:
        raise StateConflict("routing_reason_codes must be a bounded list")
    reason_codes: list[str] = []
    for item in reason_codes_raw:
        reason = str(item).strip().lower()
        if _ROUTING_VALUE_RE.fullmatch(reason) is None:
            raise StateConflict("routing_reason_codes contains an invalid value")
        if reason not in reason_codes:
            reason_codes.append(reason)
    if reason_codes:
        result["routing_reason_codes"] = reason_codes
    if provider:
        result["provider"] = provider
    if capabilities:
        result["required_capabilities"] = capabilities
    for key in ("model", "effort", "cost_class"):
        normalized = str(raw.get(key) or "").strip().lower()
        if normalized:
            result[key] = normalized
    base_sha = str(raw.get("base_sha") or "").strip().lower()
    if base_sha:
        if re.fullmatch(r"[0-9a-f]{40,64}", base_sha) is None:
            raise StateConflict("constraint base_sha must be a full hexadecimal Git object id")
        result["base_sha"] = base_sha
    return result


def _normalise_seat(value: str, *, field: str) -> str:
    normalized = str(value or "").strip().lower()
    if _SEAT_RE.fullmatch(normalized) is None or normalized not in _JOB_SEATS:
        raise StateConflict(
            f"{field} must be one of {', '.join(sorted(_JOB_SEATS))}"
        )
    return normalized


def _normalise_business_impact(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in _BUSINESS_IMPACTS:
        raise StateConflict(
            "business_impact must be one of routine, material, critical"
        )
    return normalized


def _assert_child_does_not_widen_parent(
    parent_row: sqlite3.Row,
    *,
    requested: Sequence[str],
    allowed_write_paths: Sequence[str],
    constraints: dict[str, Any],
) -> None:
    """Refuse a child that would exceed its parent's grant.  Shrink-only (L6)."""

    parent_authorities = {
        str(item).strip().upper()
        for item in _json_loads(parent_row["requested_authorities_json"], fallback=[])
        if str(item).strip()
    }
    extra_authorities = sorted(set(requested) - parent_authorities)
    if extra_authorities:
        raise StateConflict(
            "child requested_authorities may only shrink relative to the parent: "
            + ", ".join(extra_authorities)
        )
    parent_paths = {
        str(item)
        for item in _json_loads(parent_row["allowed_write_paths_json"], fallback=[])
    }
    extra_paths = sorted(set(allowed_write_paths) - parent_paths)
    if extra_paths:
        raise StateConflict(
            "child allowed_write_paths may only shrink relative to the parent: "
            + ", ".join(extra_paths)
        )
    parent_cost = str(
        _json_loads(parent_row["constraints_json"], fallback={}).get("cost_class") or ""
    ).strip().lower()
    child_cost = str(constraints.get("cost_class") or "").strip().lower()
    if parent_cost and child_cost:
        parent_rank = _COST_CLASS_RANK.get(parent_cost)
        child_rank = _COST_CLASS_RANK.get(child_cost)
        if (
            parent_rank is None
            or child_rank is None
            or child_rank > parent_rank
        ):
            raise StateConflict(
                "child cost_class may only shrink relative to the parent"
            )


def _has_executive_provenance(
    provenance: dict[str, Any] | None, *, target: str
) -> bool:
    """Require a typed executive record before a job can name a higher seat."""

    if not isinstance(provenance, dict):
        return False
    schema = str(provenance.get("schema") or "")
    actor = str(provenance.get("actor") or "").strip().lower()
    if target == "ceo":
        return schema == "mastermind.ceo_intent.v1"
    return (
        schema in {"mastermind.executive_decision.v1", "mastermind.chairman_decision.v1"}
        and actor in {"chairman", "chris", "chairman-chris"}
    )


def _capacity_route_metadata(row: sqlite3.Row) -> dict[str, Any]:
    metadata = _json_loads(row["metadata_json"], fallback={})
    if not isinstance(metadata, dict):
        raise PersistenceError("worker quota-class metadata must be a mapping")
    return metadata


def _capacity_model_alias(row: sqlite3.Row) -> str:
    metadata = _capacity_route_metadata(row)
    return str(metadata.get("model_alias") or "").strip().lower()


def _capacity_matches_route(row: sqlite3.Row, constraints: dict[str, Any]) -> bool:
    if str(row["worker_id"]) in set(constraints.get("excluded_worker_ids") or []):
        return False
    aliases = constraints.get("preferred_model_aliases") or []
    if not aliases:
        return True
    metadata = _capacity_route_metadata(row)
    worker_policy_version = str(
        metadata.get("routing_policy_version") or ""
    ).strip().lower()
    return (
        _capacity_model_alias(row) in aliases
        and worker_policy_version == constraints.get("routing_policy_version")
    )


def _capacity_route_rank(
    row: sqlite3.Row, constraints: dict[str, Any]
) -> tuple[int, str, str]:
    aliases = list(constraints.get("preferred_model_aliases") or [])
    model_alias = _capacity_model_alias(row)
    rank = aliases.index(model_alias) if model_alias in aliases else len(aliases)
    return rank, str(row["worker_id"]), str(row["quota_class"])


@dataclasses.dataclass(frozen=True)
class JobPayload:
    summary: str = ""
    completed_steps: list[str] = dataclasses.field(default_factory=list)
    current_state: str = ""
    artifacts: list[str] = dataclasses.field(default_factory=list)
    next_actions: list[str] = dataclasses.field(default_factory=list)
    errors: list[str] = dataclasses.field(default_factory=list)
    verdict: str = ""

    @classmethod
    def from_value(cls, value: "JobPayload | dict[str, Any]") -> "JobPayload":
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            raise StateConflict("checkpoint/result payload must be a JobPayload or mapping")

        def _strings(key: str) -> list[str]:
            raw = value.get(key, [])
            if raw is None:
                return []
            if not isinstance(raw, list):
                raise StateConflict(f"payload field {key!r} must be a list")
            return [str(item) for item in raw]

        verdict = str(value.get("verdict") or "").strip().lower()
        if verdict not in {"", "approve", "reject"}:
            raise StateConflict(
                "payload field 'verdict' must be empty, 'approve', or 'reject'"
            )
        return cls(
            summary=str(value.get("summary") or ""),
            completed_steps=_strings("completed_steps"),
            current_state=str(value.get("current_state") or ""),
            artifacts=_strings("artifacts"),
            next_actions=_strings("next_actions"),
            errors=_strings("errors"),
            verdict=verdict,
        )

    def to_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        # Verdict is an additive Phase 1F-B field.  Omitting the empty default
        # keeps legacy checkpoint/result payloads byte-shape compatible while
        # still persisting approve/reject on review jobs.
        if not self.verdict:
            value.pop("verdict", None)
        return value


@dataclasses.dataclass(frozen=True)
class WorkerQuotaClass:
    worker_id: str
    quota_class: str
    status: WorkerStatus
    provider: str
    model: str | None
    effort: str | None
    cost_class: str | None
    capabilities: list[str]
    active_attempt_id: str | None
    active_job_id: str | None
    fence_generation: int
    last_seen_at: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        value["status"] = self.status.value
        return value


@dataclasses.dataclass(frozen=True)
class Worker:
    worker_id: str
    provider: str
    account_label: str
    worker_type: str
    status: WorkerStatus
    capabilities: list[str]
    active_job_id: str | None
    last_seen_at: str
    metadata: dict[str, Any]
    quota_classes: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        value["status"] = self.status.value
        return value


@dataclasses.dataclass(frozen=True)
class Job:
    job_id: str
    objective: str
    department: str
    priority: int
    status: JobStatus
    assigned_worker_id: str | None
    assigned_quota_class: str | None
    authority_level: str
    branch: str | None
    worktree: str | None
    checkpoint: dict[str, Any] | None
    result: dict[str, Any] | None
    created_at: str
    updated_at: str
    constraints: dict[str, Any] = dataclasses.field(default_factory=dict)
    current_attempt_id: str | None = None
    attempt_count: int = 0
    attempt_limit: int = 10
    requested_authorities: list[str] = dataclasses.field(default_factory=list)
    authority_policy_hash: str = ""
    allowed_write_paths: list[str] = dataclasses.field(default_factory=list)
    validation_commands: list[list[str]] = dataclasses.field(default_factory=list)
    parent_job_id: str | None = None
    root_job_id: str = ""
    depth: int = 0
    owner_seat: str = "coo"
    escalation_target: str = "coo"
    business_impact: str = "routine"
    review_required: bool = False
    reviews_job_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        value["status"] = self.status.value
        return value


@dataclasses.dataclass(frozen=True)
class Attempt:
    attempt_id: str
    job_id: str
    attempt_number: int
    worker_id: str
    quota_class: str
    status: AttemptStatus
    fence_generation: int
    lease_owner: str
    lease_expires_at: str
    heartbeat_at: str
    checkpoint_sequence: int
    checkpoint: dict[str, Any] | None
    result: dict[str, Any] | None
    error: dict[str, Any] | None
    started_at: str
    finished_at: str
    version: int
    authority_policy_hash: str
    pid: int | None
    pgid: int | None
    process_start_identity: str | None
    boot_id: str | None
    provider_session_id: str | None
    stdout_path: str | None
    stderr_path: str | None
    result_path: str | None
    exit_code: int | None
    launch_metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return public attempt state.  The opaque lease token is never exposed."""
        value = dataclasses.asdict(self)
        value["status"] = self.status.value
        return value


@dataclasses.dataclass(frozen=True)
class AttemptLease:
    attempt: Attempt
    lease_token: str = dataclasses.field(repr=False)

    def to_dict(self) -> dict[str, Any]:
        """Return safe claim output; callers access the token only as an attribute."""
        return {"attempt": self.attempt.to_dict()}


@dataclasses.dataclass(frozen=True)
class Event:
    event_id: int
    aggregate_type: str
    aggregate_id: str
    sequence: int
    event_type: str
    command_id: str
    actor: str
    job_id: str | None
    attempt_id: str | None
    worker_id: str | None
    quota_class: str | None
    payload: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


_MIGRATION_1: tuple[str, ...] = (
    """
    CREATE TABLE workers (
      worker_id TEXT PRIMARY KEY,
      provider TEXT NOT NULL,
      account_label TEXT NOT NULL,
      worker_type TEXT NOT NULL,
      identity_status TEXT NOT NULL DEFAULT 'ONLINE'
        CHECK(identity_status IN ('ONLINE','DRAINING','OFFLINE','ERROR')),
      metadata_json TEXT NOT NULL DEFAULT '{}'
        CHECK(json_valid(metadata_json) AND json_type(metadata_json) = 'object'),
      last_seen_at_ms INTEGER NOT NULL,
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL,
      version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0)
    )
    """,
    """
    CREATE TABLE worker_quota_classes (
      worker_id TEXT NOT NULL,
      quota_class TEXT NOT NULL,
      status TEXT NOT NULL
        CHECK(status IN ('AVAILABLE','BUSY','DRAINING','RATE_LIMITED','OFFLINE','ERROR')),
      provider TEXT NOT NULL,
      model TEXT,
      effort TEXT,
      cost_class TEXT,
      capabilities_json TEXT NOT NULL DEFAULT '[]'
        CHECK(json_valid(capabilities_json) AND json_type(capabilities_json) = 'array'),
      metadata_json TEXT NOT NULL DEFAULT '{}'
        CHECK(json_valid(metadata_json) AND json_type(metadata_json) = 'object'),
      held_attempt_id TEXT,
      fence_counter INTEGER NOT NULL DEFAULT 0 CHECK(fence_counter >= 0),
      last_seen_at_ms INTEGER NOT NULL,
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL,
      version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
      PRIMARY KEY(worker_id, quota_class),
      UNIQUE(held_attempt_id),
      FOREIGN KEY(worker_id) REFERENCES workers(worker_id) ON DELETE RESTRICT,
      FOREIGN KEY(worker_id, quota_class, held_attempt_id)
        REFERENCES attempts(worker_id, quota_class, attempt_id)
        DEFERRABLE INITIALLY DEFERRED,
      CHECK(status != 'AVAILABLE' OR held_attempt_id IS NULL),
      CHECK(status != 'BUSY' OR held_attempt_id IS NOT NULL)
    )
    """,
    """
    CREATE TABLE jobs (
      job_id TEXT PRIMARY KEY,
      objective TEXT NOT NULL CHECK(length(trim(objective)) > 0),
      department TEXT NOT NULL,
      priority INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL
        CHECK(status IN ('QUEUED','RUNNING','CHECKPOINTED','RATE_LIMITED','FAILED',
                         'LOST','CANCEL_REQUESTED','COMPLETED','CANCELLED')),
      assigned_worker_id TEXT,
      assigned_quota_class TEXT,
      current_attempt_id TEXT,
      authority_level TEXT NOT NULL,
      branch TEXT,
      worktree TEXT,
      constraints_json TEXT NOT NULL
        CHECK(json_valid(constraints_json) AND json_type(constraints_json) = 'object'),
      requested_authorities_json TEXT NOT NULL
        CHECK(json_valid(requested_authorities_json) AND json_type(requested_authorities_json) = 'array'),
      authority_policy_hash TEXT NOT NULL CHECK(length(authority_policy_hash) = 64),
      allowed_write_paths_json TEXT NOT NULL DEFAULT '[]'
        CHECK(json_valid(allowed_write_paths_json) AND json_type(allowed_write_paths_json) = 'array'),
      validation_commands_json TEXT NOT NULL DEFAULT '[]'
        CHECK(json_valid(validation_commands_json) AND json_type(validation_commands_json) = 'array'),
      checkpoint_json TEXT CHECK(
        checkpoint_json IS NULL OR (json_valid(checkpoint_json) AND json_type(checkpoint_json) = 'object')
      ),
      result_json TEXT CHECK(
        result_json IS NULL OR (json_valid(result_json) AND json_type(result_json) = 'object')
      ),
      attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
      attempt_limit INTEGER NOT NULL DEFAULT 10 CHECK(attempt_limit > 0),
      available_at_ms INTEGER NOT NULL,
      cancel_requested_at_ms INTEGER,
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL,
      version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
      FOREIGN KEY(assigned_worker_id, assigned_quota_class)
        REFERENCES worker_quota_classes(worker_id, quota_class) ON DELETE RESTRICT,
      FOREIGN KEY(job_id, current_attempt_id, assigned_worker_id, assigned_quota_class)
        REFERENCES attempts(job_id, attempt_id, worker_id, quota_class)
        DEFERRABLE INITIALLY DEFERRED,
      CHECK((assigned_worker_id IS NULL) = (assigned_quota_class IS NULL)),
      CHECK((current_attempt_id IS NULL) = (assigned_worker_id IS NULL)),
      CHECK(status != 'QUEUED' OR current_attempt_id IS NULL),
      CHECK(status NOT IN ('RUNNING','CHECKPOINTED','RATE_LIMITED','FAILED','LOST',
                           'CANCEL_REQUESTED','COMPLETED') OR current_attempt_id IS NOT NULL),
      CHECK(status != 'COMPLETED' OR result_json IS NOT NULL)
    )
    """,
    """
    CREATE TABLE attempts (
      attempt_id TEXT PRIMARY KEY,
      job_id TEXT NOT NULL,
      attempt_number INTEGER NOT NULL CHECK(attempt_number > 0),
      worker_id TEXT NOT NULL,
      quota_class TEXT NOT NULL,
      status TEXT NOT NULL
        CHECK(status IN ('CLAIMED','RUNNING','CHECKPOINTED','CANCEL_REQUESTED',
                         'RATE_LIMITED','FAILED','LOST','COMPLETED','CANCELLED')),
      fence_generation INTEGER NOT NULL CHECK(fence_generation > 0),
      authority_policy_hash TEXT NOT NULL CHECK(length(authority_policy_hash) = 64),
      lease_token TEXT,
      lease_owner TEXT NOT NULL,
      lease_expires_at_ms INTEGER NOT NULL,
      heartbeat_at_ms INTEGER NOT NULL,
      checkpoint_sequence INTEGER NOT NULL DEFAULT 0 CHECK(checkpoint_sequence >= 0),
      checkpoint_json TEXT CHECK(
        checkpoint_json IS NULL OR (json_valid(checkpoint_json) AND json_type(checkpoint_json) = 'object')
      ),
      result_json TEXT CHECK(
        result_json IS NULL OR (json_valid(result_json) AND json_type(result_json) = 'object')
      ),
      error_json TEXT CHECK(
        error_json IS NULL OR (json_valid(error_json) AND json_type(error_json) = 'object')
      ),
      pid INTEGER,
      pgid INTEGER,
      process_start_identity TEXT,
      boot_id TEXT,
      provider_session_id TEXT,
      stdout_path TEXT,
      stderr_path TEXT,
      result_path TEXT,
      exit_code INTEGER,
      launch_metadata_json TEXT NOT NULL DEFAULT '{}'
        CHECK(json_valid(launch_metadata_json) AND json_type(launch_metadata_json) = 'object'),
      started_at_ms INTEGER NOT NULL,
      finished_at_ms INTEGER,
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL,
      version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
      UNIQUE(job_id, attempt_number),
      UNIQUE(worker_id, quota_class, attempt_id),
      UNIQUE(job_id, attempt_id, worker_id, quota_class),
      FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE RESTRICT,
      FOREIGN KEY(worker_id, quota_class)
        REFERENCES worker_quota_classes(worker_id, quota_class) ON DELETE RESTRICT,
      CHECK((status IN ('RATE_LIMITED','FAILED','LOST','COMPLETED','CANCELLED'))
            = (finished_at_ms IS NOT NULL)),
      CHECK(status NOT IN ('RATE_LIMITED','FAILED','LOST','COMPLETED','CANCELLED')
            OR lease_token IS NULL),
      CHECK(status IN ('RATE_LIMITED','FAILED','LOST','COMPLETED','CANCELLED')
            OR lease_token IS NOT NULL),
      CHECK(status != 'COMPLETED' OR result_json IS NOT NULL),
      CHECK(pid IS NULL OR pid > 0),
      CHECK(pgid IS NULL OR pgid > 0),
      CHECK(
        (pid IS NULL AND pgid IS NULL AND process_start_identity IS NULL AND boot_id IS NULL)
        OR
        (pid IS NOT NULL AND pgid IS NOT NULL
         AND length(trim(process_start_identity)) > 0 AND length(trim(boot_id)) > 0)
      )
    )
    """,
    """
    CREATE TABLE events (
      event_id INTEGER PRIMARY KEY AUTOINCREMENT,
      aggregate_type TEXT NOT NULL,
      aggregate_id TEXT NOT NULL,
      sequence INTEGER NOT NULL CHECK(sequence > 0),
      event_type TEXT NOT NULL,
      command_id TEXT NOT NULL UNIQUE,
      actor TEXT NOT NULL,
      job_id TEXT,
      attempt_id TEXT,
      worker_id TEXT,
      quota_class TEXT,
      payload_json TEXT NOT NULL DEFAULT '{}'
        CHECK(json_valid(payload_json) AND json_type(payload_json) = 'object'),
      created_at_ms INTEGER NOT NULL,
      UNIQUE(aggregate_type, aggregate_id, sequence),
      FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE RESTRICT,
      FOREIGN KEY(attempt_id) REFERENCES attempts(attempt_id) ON DELETE RESTRICT,
      FOREIGN KEY(worker_id) REFERENCES workers(worker_id) ON DELETE RESTRICT,
      FOREIGN KEY(worker_id, quota_class)
        REFERENCES worker_quota_classes(worker_id, quota_class) ON DELETE RESTRICT
    )
    """,
    """
    CREATE UNIQUE INDEX one_lease_active_attempt_per_job
      ON attempts(job_id)
      WHERE status IN ('CLAIMED','RUNNING','CHECKPOINTED','CANCEL_REQUESTED')
    """,
    """
    CREATE UNIQUE INDEX one_lease_active_attempt_per_capacity
      ON attempts(worker_id, quota_class)
      WHERE status IN ('CLAIMED','RUNNING','CHECKPOINTED','CANCEL_REQUESTED')
    """,
    "CREATE INDEX jobs_dispatch_order ON jobs(status, available_at_ms, priority DESC, created_at_ms, job_id)",
    "CREATE INDEX attempts_expiry ON attempts(status, lease_expires_at_ms)",
    """
    CREATE TRIGGER events_are_immutable_update
    BEFORE UPDATE ON events BEGIN
      SELECT RAISE(ABORT, 'events are immutable');
    END
    """,
    """
    CREATE TRIGGER events_are_immutable_delete
    BEFORE DELETE ON events BEGIN
      SELECT RAISE(ABORT, 'events are immutable');
    END
    """,
    """
    CREATE TRIGGER terminal_attempts_are_immutable
    BEFORE UPDATE ON attempts
    WHEN OLD.status IN ('RATE_LIMITED','FAILED','LOST','COMPLETED','CANCELLED')
    BEGIN
      SELECT RAISE(ABORT, 'terminal attempts are immutable');
    END
    """,
)

_MIGRATION_2: tuple[str, ...] = (
    "ALTER TABLE jobs ADD COLUMN parent_job_id TEXT REFERENCES jobs(job_id) ON DELETE RESTRICT",
    "ALTER TABLE jobs ADD COLUMN root_job_id TEXT",
    "ALTER TABLE jobs ADD COLUMN depth INTEGER NOT NULL DEFAULT 0 CHECK(depth >= 0)",
    "ALTER TABLE jobs ADD COLUMN owner_seat TEXT NOT NULL DEFAULT 'coo' CHECK(owner_seat IN ('coo','ceo','chairman'))",
    "ALTER TABLE jobs ADD COLUMN escalation_target TEXT NOT NULL DEFAULT 'coo' CHECK(escalation_target IN ('coo','ceo','chairman'))",
    "ALTER TABLE jobs ADD COLUMN business_impact TEXT NOT NULL DEFAULT 'routine' CHECK(business_impact IN ('routine','material','critical'))",
    "ALTER TABLE jobs ADD COLUMN review_required INTEGER NOT NULL DEFAULT 0 CHECK(review_required IN (0,1))",
    "ALTER TABLE jobs ADD COLUMN reviews_job_id TEXT REFERENCES jobs(job_id) ON DELETE RESTRICT",
    "UPDATE jobs SET root_job_id=job_id WHERE root_job_id IS NULL",
    "CREATE INDEX jobs_parent_dispatch ON jobs(parent_job_id,status,available_at_ms,priority DESC,created_at_ms,job_id)",
    "CREATE INDEX jobs_root_order ON jobs(root_job_id,depth,created_at_ms,job_id)",
    """
    CREATE TRIGGER jobs_hierarchy_is_immutable
    BEFORE UPDATE OF parent_job_id,root_job_id,depth,reviews_job_id ON jobs
    WHEN OLD.parent_job_id IS NOT NEW.parent_job_id
      OR OLD.root_job_id IS NOT NEW.root_job_id
      OR OLD.depth IS NOT NEW.depth
      OR OLD.reviews_job_id IS NOT NEW.reviews_job_id
    BEGIN
      SELECT RAISE(ABORT, 'job hierarchy and review pointer are immutable');
    END
    """,
    """
    CREATE TRIGGER jobs_review_pointer_contract
    BEFORE INSERT ON jobs
    WHEN NEW.reviews_job_id IS NOT NULL AND NEW.review_required != 0
    BEGIN
      SELECT RAISE(ABORT, 'a review job cannot require review');
    END
    """,
    """
    CREATE TRIGGER jobs_review_pointer_contract_update
    BEFORE UPDATE OF review_required,reviews_job_id ON jobs
    WHEN NEW.reviews_job_id IS NOT NULL AND NEW.review_required != 0
    BEGIN
      SELECT RAISE(ABORT, 'a review job cannot require review');
    END
    """,
    """
    CREATE TRIGGER jobs_root_contract
    BEFORE INSERT ON jobs
    WHEN NEW.root_job_id IS NULL OR length(trim(NEW.root_job_id)) = 0
    BEGIN
      SELECT RAISE(ABORT, 'root_job_id is required');
    END
    """,
    """
    CREATE TRIGGER jobs_parent_is_not_self
    BEFORE INSERT ON jobs
    WHEN NEW.parent_job_id IS NOT NULL AND NEW.parent_job_id = NEW.job_id
    BEGIN
      SELECT RAISE(ABORT, 'a job cannot be its own parent');
    END
    """,
)

_MIGRATIONS: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (1, "executive_runtime_core", _MIGRATION_1),
    (2, "durable_parent_child_review_contract", _MIGRATION_2),
)


class RuntimeStore:
    """SQLite connection, migration, transaction, and event boundary."""

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        clock: Callable[[], int | float | datetime] | None = None,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
        create: bool = True,
    ) -> None:
        self.root = Path(root).resolve() if root is not None else _ROOT
        self.path = self.root / _DB_RELATIVE_PATH
        self.clock = clock
        self.lease_seconds = int(lease_seconds)
        self.busy_timeout_ms = int(busy_timeout_ms)
        # `create=False` is the read-only accessor a PROJECTION opens the runtime
        # with.  It never creates the directory or the file, never migrates, never
        # chmods, and refuses `transaction()`, so a reader cannot manufacture an
        # Executive OS schema on top of an empty, foreign, or truncated file and
        # then report the result as a quiet company.
        self.create = bool(create)
        if self.lease_seconds <= 0:
            raise StateConflict("lease_seconds must be positive")
        if self.busy_timeout_ms < 0:
            raise StateConflict("busy_timeout_ms cannot be negative")
        self._schema_ready = False
        if self.create:
            try:
                self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                self.path.parent.chmod(0o700)
            except OSError as exc:
                raise PersistenceError(
                    f"cannot protect Executive runtime database directory: {exc}"
                ) from exc
        connection = self._open()
        connection.close()

    def now_ms(self) -> int:
        value: int | float | datetime
        value = self.clock() if self.clock else datetime.now(timezone.utc)
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return int(value.timestamp() * 1000)
        return int(value)

    def _open_readonly(self) -> sqlite3.Connection:
        """Open an EXISTING database read-only: no create, no chmod, no migration.

        SQLite's ``mode=ro`` makes the guarantee structural rather than
        conventional: it refuses to create the file and rejects every write.
        ``journal_mode`` and ``synchronous`` are deliberately NOT set here —
        setting a journal mode is itself a write, and a reader must leave a
        ``delete``-mode or ``wal``-mode database exactly as it found it.

        The schema is then verified rather than assumed.  Without this check an
        empty, truncated, or foreign file reads as a valid database with no rows,
        which a caller would report as "nothing is running".
        """
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                f"{self.path.as_uri()}?mode=ro",
                uri=True,
                timeout=self.busy_timeout_ms / 1000,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
        except (OSError, sqlite3.Error) as exc:
            if connection is not None:
                connection.close()
            raise PersistenceError(
                f"executive runtime database at {self.path} is unavailable: {exc}"
            ) from exc
        if not self._schema_ready:
            try:
                connection.execute("SELECT version FROM schema_migrations LIMIT 1").fetchone()
            except sqlite3.Error as exc:
                connection.close()
                message = str(exc)
                if "no such table" in message:
                    detail = "carries no Executive OS schema"
                elif "not a database" in message:
                    detail = "is not an Executive OS database"
                else:
                    detail = "could not be read"
                raise PersistenceError(
                    f"executive runtime database at {self.path} {detail}: {exc}"
                ) from exc
            self._schema_ready = True
        return connection

    def _open(self) -> sqlite3.Connection:
        if not self.create:
            return self._open_readonly()
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                self.path,
                timeout=self.busy_timeout_ms / 1000,
                isolation_level=None,
            )
            self.path.chmod(0o600)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            if not self._schema_ready:
                self._migrate(connection)
                self._schema_ready = True
            for sidecar in (
                self.path.with_name(f"{self.path.name}-wal"),
                self.path.with_name(f"{self.path.name}-shm"),
            ):
                if sidecar.exists():
                    sidecar.chmod(0o600)
            return connection
        except PersistenceError:
            if connection is not None:
                connection.close()
            raise
        except (OSError, sqlite3.Error) as exc:
            if connection is not None:
                connection.close()
            raise PersistenceError(f"executive runtime database is unavailable: {exc}") from exc

    def _migrate(self, connection: sqlite3.Connection) -> None:
        try:
            connection.execute("BEGIN EXCLUSIVE")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                  version INTEGER PRIMARY KEY,
                  name TEXT NOT NULL UNIQUE,
                  checksum TEXT NOT NULL,
                  applied_at_ms INTEGER NOT NULL
                )
                """
            )
            existing = {
                int(row["version"]): row
                for row in connection.execute("SELECT * FROM schema_migrations")
            }
            known_versions = {version for version, _, _ in _MIGRATIONS}
            unknown = sorted(set(existing) - known_versions)
            if unknown:
                raise PersistenceError(
                    f"database schema is newer than this runtime: versions {unknown}"
                )
            for version, name, statements in _MIGRATIONS:
                checksum = hashlib.sha256(
                    "\n".join(statement.strip() for statement in statements).encode("utf-8")
                ).hexdigest()
                row = existing.get(version)
                if row is not None:
                    if row["name"] != name or row["checksum"] != checksum:
                        raise PersistenceError(
                            f"migration {version} checksum/name does not match code"
                        )
                    continue
                for statement in statements:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migrations(version,name,checksum,applied_at_ms) VALUES(?,?,?,?)",
                    (version, name, checksum, self.now_ms()),
                )
            connection.commit()
            violations = connection.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise PersistenceError(f"database foreign-key check failed: {violations!r}")
        except PersistenceError:
            if connection.in_transaction:
                connection.rollback()
            raise
        except sqlite3.Error as exc:
            if connection.in_transaction:
                connection.rollback()
            raise PersistenceError(f"database migration failed: {exc}") from exc

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        if not self.create:
            # Fail closed: a store opened for projection has no write path at all,
            # so a lifecycle call cannot reach the database even by mistake.
            raise StateConflict(
                "read-only store: this RuntimeStore was opened with create=False "
                "and refuses every lifecycle mutation"
            )
        connection = self._open()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except RuntimeProofError:
            if connection.in_transaction:
                connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            if connection.in_transaction:
                connection.rollback()
            raise StateConflict(f"database invariant rejected the operation: {exc}") from exc
        except sqlite3.Error as exc:
            if connection.in_transaction:
                connection.rollback()
            raise PersistenceError(f"database transaction failed: {exc}") from exc
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        connection = self._open()
        try:
            connection.execute("BEGIN")
            yield connection
            connection.commit()
        except RuntimeProofError:
            if connection.in_transaction:
                connection.rollback()
            raise
        except sqlite3.Error as exc:
            if connection.in_transaction:
                connection.rollback()
            raise PersistenceError(f"database read failed: {exc}") from exc
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def append_event(
        self,
        connection: sqlite3.Connection,
        *,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        actor: str = "operator",
        job_id: str | None = None,
        attempt_id: str | None = None,
        worker_id: str | None = None,
        quota_class: str | None = None,
        payload: dict[str, Any] | None = None,
        command_id: str | None = None,
        timestamp_ms: int | None = None,
    ) -> None:
        sequence = int(
            connection.execute(
                "SELECT COALESCE(MAX(sequence),0)+1 FROM events WHERE aggregate_type=? AND aggregate_id=?",
                (aggregate_type, aggregate_id),
            ).fetchone()[0]
        )
        connection.execute(
            """
            INSERT INTO events(
              aggregate_type,aggregate_id,sequence,event_type,command_id,actor,
              job_id,attempt_id,worker_id,quota_class,payload_json,created_at_ms
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                aggregate_type,
                aggregate_id,
                sequence,
                event_type,
                command_id or uuid4().hex,
                actor,
                job_id,
                attempt_id,
                worker_id,
                quota_class,
                _json_dumps(payload or {}),
                self.now_ms() if timestamp_ms is None else timestamp_ms,
            ),
        )

    def get_event_by_command_id(
        self,
        command_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> Event | None:
        """Return the full Event that owns ``command_id``, or None.

        When ``connection`` is supplied, the lookup uses that open transaction
        so a writer can reconcile UNIQUE ``command_id`` replay inside
        ``BEGIN IMMEDIATE``.  The public EventRegistry wrapper uses a read
        snapshot.  This does not expose arbitrary SQL.
        """

        token = str(command_id or "").strip()
        if not token:
            raise StateConflict("command_id is required")

        def _load(conn: sqlite3.Connection) -> Event | None:
            row = conn.execute(
                "SELECT * FROM events WHERE command_id=?",
                (token,),
            ).fetchone()
            return None if row is None else _event_from_row(row)

        if connection is not None:
            return _load(connection)
        with self.read() as conn:
            return _load(conn)

    def find_event_by_command_id(self, command_id: str) -> dict[str, Any] | None:
        """Return the essentials of the event that owns ``command_id``, or None.

        The reconciliation half of the UNIQUE ``command_id`` index: a caller that
        names its command can ask whether that command already committed instead
        of issuing it twice.  Read-only, no new table, no new store.
        """

        with self.read() as connection:
            row = connection.execute(
                """
                SELECT event_type,job_id,payload_json,created_at_ms
                FROM events WHERE command_id=?
                """,
                (str(command_id),),
            ).fetchone()
        if row is None:
            return None
        return {
            "event_type": str(row["event_type"]),
            "job_id": row["job_id"],
            "payload": _json_loads(row["payload_json"], fallback={}),
            "created_at_ms": int(row["created_at_ms"]),
        }

    def snapshot(self) -> dict[str, Any]:
        """Compatibility/debug snapshot assembled from authoritative rows."""
        runtime = Runtime.from_store(self)
        return {
            "schema_version": SCHEMA_VERSION,
            "workers": {item.worker_id: item.to_dict() for item in runtime.workers.list_workers()},
            "jobs": {item.job_id: item.to_dict() for item in runtime.jobs.list_jobs()},
            "attempts": {
                item.attempt_id: item.to_dict() for item in runtime.attempts.list_attempts()
            },
        }


def _quota_specifications(
    worker_provider: str,
    worker_capabilities: list[str],
    quota_classes: (
        dict[str, list[str] | tuple[str, ...] | dict[str, Any]]
        | list[str]
        | tuple[str, ...]
        | None
    ),
) -> dict[str, dict[str, Any]]:
    if quota_classes is None:
        declared: dict[str, Any] = {"default": worker_capabilities}
    elif isinstance(quota_classes, dict):
        declared = dict(quota_classes)
    elif isinstance(quota_classes, (list, tuple)):
        declared = {str(name): worker_capabilities for name in quota_classes}
    else:
        raise StateConflict("quota_classes must be a mapping or list of class names")
    result: dict[str, dict[str, Any]] = {}
    for raw_name, raw_value in declared.items():
        name = str(raw_name).strip().lower()
        if not name:
            raise StateConflict("quota class names cannot be empty")
        if name in result:
            raise StateConflict(f"duplicate normalized quota class {name!r}")
        if isinstance(raw_value, dict):
            raw_capabilities = (
                raw_value.get("capabilities")
                if "capabilities" in raw_value
                else raw_value.get("caps")
                if "caps" in raw_value
                else worker_capabilities
            )
            capabilities = _normalise_capabilities(
                raw_capabilities
            )
            raw_metadata = raw_value.get("metadata") or {}
            if not isinstance(raw_metadata, dict):
                raise StateConflict("quota-class metadata must be a mapping")
            metadata = dict(raw_metadata)
            provider = str(raw_value.get("provider") or worker_provider).strip().lower()
            model = (
                str(raw_value["model"]).strip().lower()
                if raw_value.get("model")
                else None
            )
            effort = (
                str(raw_value["effort"]).strip().lower()
                if raw_value.get("effort")
                else None
            )
            cost_class = (
                str(raw_value["cost_class"]).strip().lower()
                if raw_value.get("cost_class")
                else None
            )
        elif isinstance(raw_value, (list, tuple)):
            capabilities = _normalise_capabilities(raw_value)
            metadata = {}
            provider = worker_provider
            model = effort = cost_class = None
        else:
            raise StateConflict(
                "each quota class must declare a capability list or metadata mapping"
            )
        if not provider:
            raise StateConflict("quota-class provider is required")
        result[name] = {
            "capabilities": capabilities,
            "metadata": metadata,
            "provider": provider,
            "model": model,
            "effort": effort,
            "cost_class": cost_class,
        }
    if not result:
        raise StateConflict("at least one quota class is required")
    return result


def _attempt_from_row(row: sqlite3.Row) -> Attempt:
    return Attempt(
        attempt_id=str(row["attempt_id"]),
        job_id=str(row["job_id"]),
        attempt_number=int(row["attempt_number"]),
        worker_id=str(row["worker_id"]),
        quota_class=str(row["quota_class"]),
        status=AttemptStatus(row["status"]),
        fence_generation=int(row["fence_generation"]),
        lease_owner=str(row["lease_owner"]),
        lease_expires_at=_iso(int(row["lease_expires_at_ms"])),
        heartbeat_at=_iso(int(row["heartbeat_at_ms"])),
        checkpoint_sequence=int(row["checkpoint_sequence"]),
        checkpoint=_json_loads(row["checkpoint_json"], fallback=None),
        result=_json_loads(row["result_json"], fallback=None),
        error=_json_loads(row["error_json"], fallback=None),
        started_at=_iso(int(row["started_at_ms"])),
        finished_at=_iso(row["finished_at_ms"]),
        version=int(row["version"]),
        authority_policy_hash=str(row["authority_policy_hash"]),
        pid=row["pid"],
        pgid=row["pgid"],
        process_start_identity=row["process_start_identity"],
        boot_id=row["boot_id"],
        provider_session_id=row["provider_session_id"],
        stdout_path=row["stdout_path"],
        stderr_path=row["stderr_path"],
        result_path=row["result_path"],
        exit_code=row["exit_code"],
        launch_metadata=dict(
            _json_loads(row["launch_metadata_json"], fallback={})
        ),
    )


def _job_from_row(row: sqlite3.Row) -> Job:
    return Job(
        job_id=str(row["job_id"]),
        objective=str(row["objective"]),
        department=str(row["department"]),
        priority=int(row["priority"]),
        status=JobStatus(row["status"]),
        assigned_worker_id=row["assigned_worker_id"],
        assigned_quota_class=row["assigned_quota_class"],
        authority_level=str(row["authority_level"]),
        branch=row["branch"],
        worktree=row["worktree"],
        checkpoint=_json_loads(row["checkpoint_json"], fallback=None),
        result=_json_loads(row["result_json"], fallback=None),
        created_at=_iso(int(row["created_at_ms"])),
        updated_at=_iso(int(row["updated_at_ms"])),
        constraints=_normalise_constraints(
            _json_loads(row["constraints_json"], fallback={})
        ),
        current_attempt_id=row["current_attempt_id"],
        attempt_count=int(row["attempt_count"]),
        attempt_limit=int(row["attempt_limit"]),
        requested_authorities=list(
            _json_loads(row["requested_authorities_json"], fallback=[])
        ),
        authority_policy_hash=str(row["authority_policy_hash"]),
        allowed_write_paths=list(
            _json_loads(row["allowed_write_paths_json"], fallback=[])
        ),
        validation_commands=list(
            _json_loads(row["validation_commands_json"], fallback=[])
        ),
        parent_job_id=row["parent_job_id"],
        root_job_id=str(row["root_job_id"] or row["job_id"]),
        depth=int(row["depth"]),
        owner_seat=str(row["owner_seat"]),
        escalation_target=str(row["escalation_target"]),
        business_impact=str(row["business_impact"]),
        review_required=bool(int(row["review_required"])),
        reviews_job_id=row["reviews_job_id"],
    )


def _authorize_job_row(row: sqlite3.Row):
    """Re-authorize a durable job against the policy active at claim time."""
    requested = _json_loads(row["requested_authorities_json"], fallback=[])
    allowed_write_paths = _json_loads(row["allowed_write_paths_json"], fallback=[])
    validation_commands = _json_loads(row["validation_commands_json"], fallback=[])
    try:
        return ExecutiveAuthorityPolicy.load().authorize(
            requested,
            worktree=row["worktree"],
            allowed_write_paths=allowed_write_paths,
            validation_commands=validation_commands,
        )
    except (AuthorityDenied, AuthorityPolicyError) as exc:
        raise StateConflict(f"job authority is denied at claim time: {exc}") from exc


def _living_child_rows(
    connection: sqlite3.Connection, parent_job_id: str
) -> list[sqlite3.Row]:
    placeholders = ",".join("?" for _ in _TERMINAL_JOB_STATUSES)
    terminal = [status.value for status in _TERMINAL_JOB_STATUSES]
    return connection.execute(
        f"SELECT * FROM jobs WHERE parent_job_id=? AND status NOT IN ({placeholders}) "
        "ORDER BY created_at_ms,job_id",
        (parent_job_id, *terminal),
    ).fetchall()


def _review_void_evidence(
    connection: sqlite3.Connection, *, job_id: str, worker_id: str
) -> dict[str, Any] | None:
    review = connection.execute(
        "SELECT reviews_job_id FROM jobs WHERE job_id=?", (job_id,)
    ).fetchone()
    reviewed_id = review["reviews_job_id"] if review else None
    if not reviewed_id:
        return None
    reviewed = connection.execute(
        "SELECT assigned_worker_id,current_attempt_id FROM jobs WHERE job_id=?",
        (reviewed_id,),
    ).fetchone()
    if reviewed is None or not reviewed["assigned_worker_id"]:
        return None
    if str(reviewed["assigned_worker_id"]) != str(worker_id):
        return {"status": "INDEPENDENT", "reviews_job_id": str(reviewed_id)}
    return {
        "status": "VOID",
        "reason": "review_not_independent",
        "voids": reviewed["current_attempt_id"],
        "reviews_job_id": str(reviewed_id),
    }


def _assert_parent_aggregation_allowed(
    connection: sqlite3.Connection, *, parent_job_id: str
) -> None:
    """Fail closed until the explicit Phase 1F-C cycle is allowed to aggregate."""

    children = connection.execute(
        "SELECT * FROM jobs WHERE parent_job_id=? ORDER BY created_at_ms,job_id",
        (parent_job_id,),
    ).fetchall()
    if not children:
        return
    living = [
        row
        for row in children
        if JobStatus(row["status"]) not in _TERMINAL_JOB_STATUSES
    ]
    if living:
        raise StateConflict(
            "aggregation_blocked: parent has living child job(s) "
            + ", ".join(str(row["job_id"]) for row in living)
        )
    for child in children:
        if not bool(int(child["review_required"])):
            continue
        reviews = connection.execute(
            """
            SELECT r.*,a.worker_id AS review_worker_id
            FROM jobs r
            LEFT JOIN attempts a ON a.attempt_id=r.current_attempt_id
            WHERE r.reviews_job_id=? AND r.status='COMPLETED'
            ORDER BY r.updated_at_ms,r.job_id
            """,
            (child["job_id"],),
        ).fetchall()
        independent_approval = False
        for review in reviews:
            payload = JobPayload.from_value(
                _json_loads(review["result_json"], fallback={})
            )
            if (
                payload.verdict == "approve"
                and review["review_worker_id"]
                and child["assigned_worker_id"]
                and str(review["review_worker_id"]) != str(child["assigned_worker_id"])
            ):
                independent_approval = True
                break
        if not independent_approval:
            raise StateConflict(
                "aggregation_blocked: child "
                f"{child['job_id']} requires an independent completed review "
                "with verdict=approve"
            )


def _event_from_row(row: sqlite3.Row) -> Event:
    return Event(
        event_id=int(row["event_id"]),
        aggregate_type=str(row["aggregate_type"]),
        aggregate_id=str(row["aggregate_id"]),
        sequence=int(row["sequence"]),
        event_type=str(row["event_type"]),
        command_id=str(row["command_id"]),
        actor=str(row["actor"]),
        job_id=row["job_id"],
        attempt_id=row["attempt_id"],
        worker_id=row["worker_id"],
        quota_class=row["quota_class"],
        payload=_json_loads(row["payload_json"], fallback={}),
        created_at=_iso(int(row["created_at_ms"])),
    )


def _quota_from_row(row: sqlite3.Row) -> WorkerQuotaClass:
    return WorkerQuotaClass(
        worker_id=str(row["worker_id"]),
        quota_class=str(row["quota_class"]),
        status=WorkerStatus(row["status"]),
        provider=str(row["provider"]),
        model=row["model"],
        effort=row["effort"],
        cost_class=row["cost_class"],
        capabilities=_normalise_capabilities(
            _json_loads(row["capabilities_json"], fallback=[])
        ),
        active_attempt_id=row["held_attempt_id"],
        active_job_id=row["active_job_id"] if "active_job_id" in row.keys() else None,
        fence_generation=int(row["fence_counter"]),
        last_seen_at=_iso(int(row["last_seen_at_ms"])),
        metadata=dict(_json_loads(row["metadata_json"], fallback={})),
    )


class WorkerRegistry:
    def __init__(self, store: RuntimeStore) -> None:
        self.store = store

    def register_worker(
        self,
        worker_id: str,
        *,
        provider: str,
        account_label: str,
        worker_type: str,
        capabilities: str | list[str] | tuple[str, ...] | None = None,
        quota_classes: (
            dict[str, list[str] | tuple[str, ...] | dict[str, Any]]
            | list[str]
            | tuple[str, ...]
            | None
        ) = None,
        status: WorkerStatus | str = WorkerStatus.AVAILABLE,
        metadata: dict[str, Any] | None = None,
    ) -> Worker:
        worker_id = str(worker_id).strip()
        if not _WORKER_ID_RE.fullmatch(worker_id):
            raise StateConflict(
                "worker_id must be 1-64 characters using letters, digits, '.', '_' or '-'"
            )
        provider = str(provider).strip().lower()
        if not provider:
            raise StateConflict("provider is required")
        worker_status = WorkerStatus(_enum_value(status, WorkerStatus))
        if worker_status == WorkerStatus.BUSY:
            raise StateConflict("a worker cannot register BUSY without an assigned job")
        if metadata is not None and not isinstance(metadata, dict):
            raise StateConflict("worker metadata must be a mapping")
        worker_capabilities = _normalise_capabilities(capabilities)
        specifications = _quota_specifications(
            provider, worker_capabilities, quota_classes
        )
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            if connection.execute(
                "SELECT 1 FROM workers WHERE worker_id=?", (worker_id,)
            ).fetchone():
                raise StateConflict(f"worker {worker_id!r} is already registered")
            identity_status = (
                worker_status.value
                if worker_status
                in {WorkerStatus.DRAINING, WorkerStatus.OFFLINE, WorkerStatus.ERROR}
                else "ONLINE"
            )
            connection.execute(
                """
                INSERT INTO workers(
                  worker_id,provider,account_label,worker_type,identity_status,
                  metadata_json,last_seen_at_ms,created_at_ms,updated_at_ms
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    worker_id,
                    provider,
                    str(account_label),
                    str(worker_type),
                    identity_status,
                    _json_dumps(metadata or {}),
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            for quota_class, spec in specifications.items():
                connection.execute(
                    """
                    INSERT INTO worker_quota_classes(
                      worker_id,quota_class,status,provider,model,effort,cost_class,
                      capabilities_json,metadata_json,last_seen_at_ms,created_at_ms,updated_at_ms
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        worker_id,
                        quota_class,
                        worker_status.value,
                        spec["provider"],
                        spec["model"],
                        spec["effort"],
                        spec["cost_class"],
                        _json_dumps(spec["capabilities"]),
                        _json_dumps(spec["metadata"]),
                        timestamp,
                        timestamp,
                        timestamp,
                    ),
                )
            self.store.append_event(
                connection,
                aggregate_type="worker",
                aggregate_id=worker_id,
                event_type="WORKER_REGISTERED",
                worker_id=worker_id,
                payload={"quota_classes": sorted(specifications)},
                timestamp_ms=timestamp,
            )
        worker = self.get_worker(worker_id)
        assert worker is not None
        return worker

    def get_quota_class(
        self, worker_id: str, quota_class: str
    ) -> WorkerQuotaClass | None:
        with self.store.read() as connection:
            row = connection.execute(
                """
                SELECT q.*, a.job_id AS active_job_id
                FROM worker_quota_classes q
                LEFT JOIN attempts a ON a.attempt_id=q.held_attempt_id
                WHERE q.worker_id=? AND q.quota_class=?
                """,
                (worker_id, str(quota_class).strip().lower()),
            ).fetchone()
            return _quota_from_row(row) if row else None

    def get_worker(self, worker_id: str) -> Worker | None:
        with self.store.read() as connection:
            worker_row = connection.execute(
                "SELECT * FROM workers WHERE worker_id=?", (worker_id,)
            ).fetchone()
            if worker_row is None:
                return None
            quota_rows = connection.execute(
                """
                SELECT q.*, a.job_id AS active_job_id
                FROM worker_quota_classes q
                LEFT JOIN attempts a ON a.attempt_id=q.held_attempt_id
                WHERE q.worker_id=? ORDER BY q.quota_class
                """,
                (worker_id,),
            ).fetchall()
        quotas = [_quota_from_row(row) for row in quota_rows]
        statuses = {quota.status for quota in quotas}
        if worker_row["identity_status"] != "ONLINE":
            aggregate_status = WorkerStatus(worker_row["identity_status"])
        else:
            for candidate in (
                WorkerStatus.AVAILABLE,
                WorkerStatus.BUSY,
                WorkerStatus.RATE_LIMITED,
                WorkerStatus.DRAINING,
                WorkerStatus.OFFLINE,
                WorkerStatus.ERROR,
            ):
                if candidate in statuses:
                    aggregate_status = candidate
                    break
            else:  # pragma: no cover - registration guarantees a class
                aggregate_status = WorkerStatus.ERROR
        active_jobs = sorted(
            {quota.active_job_id for quota in quotas if quota.active_job_id}
        )
        capabilities = sorted(
            {item for quota in quotas for item in quota.capabilities}
        )
        legacy_quotas = {
            quota.quota_class: {
                "status": quota.status.value,
                "capabilities": quota.capabilities,
                "active_job_id": quota.active_job_id,
            }
            for quota in quotas
        }
        return Worker(
            worker_id=str(worker_row["worker_id"]),
            provider=str(worker_row["provider"]),
            account_label=str(worker_row["account_label"]),
            worker_type=str(worker_row["worker_type"]),
            status=aggregate_status,
            capabilities=capabilities,
            active_job_id=active_jobs[0] if active_jobs else None,
            last_seen_at=_iso(int(worker_row["last_seen_at_ms"])),
            metadata=dict(_json_loads(worker_row["metadata_json"], fallback={})),
            quota_classes=legacy_quotas,
        )

    def list_workers(self) -> list[Worker]:
        with self.store.read() as connection:
            worker_ids = [
                str(row[0])
                for row in connection.execute(
                    "SELECT worker_id FROM workers ORDER BY worker_id"
                )
            ]
        return [worker for item in worker_ids if (worker := self.get_worker(item))]

    def set_worker_status(
        self,
        worker_id: str,
        status: WorkerStatus | str,
        *,
        quota_class: str | None = None,
    ) -> Worker:
        new_status = WorkerStatus(_enum_value(status, WorkerStatus))
        if new_status == WorkerStatus.BUSY:
            raise StateConflict("assign a job instead of setting quota-class status BUSY")
        selected = str(quota_class).strip().lower() if quota_class else None
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM worker_quota_classes WHERE worker_id=? ORDER BY quota_class",
                (worker_id,),
            ).fetchall()
            if not rows:
                raise StateConflict(f"worker {worker_id!r} does not exist")
            if selected:
                rows = [row for row in rows if row["quota_class"] == selected]
                if not rows:
                    raise StateConflict(
                        f"worker {worker_id!r} has no quota class {selected!r}"
                    )
            for row in rows:
                held_attempt_id = row["held_attempt_id"]
                if new_status == WorkerStatus.AVAILABLE and held_attempt_id:
                    attempt = connection.execute(
                        "SELECT job_id FROM attempts WHERE attempt_id=?", (held_attempt_id,)
                    ).fetchone()
                    raise StateConflict(
                        f"requeue, complete, fail, or cancel {attempt['job_id']} before making "
                        f"{row['quota_class']} AVAILABLE"
                    )
                if new_status == WorkerStatus.RATE_LIMITED and held_attempt_id:
                    self._rate_limit_held_attempt(
                        connection,
                        attempt_id=str(held_attempt_id),
                        timestamp=timestamp,
                    )
                else:
                    connection.execute(
                        """
                        UPDATE worker_quota_classes
                        SET status=?,last_seen_at_ms=?,updated_at_ms=?,version=version+1
                        WHERE worker_id=? AND quota_class=?
                        """,
                        (
                            new_status.value,
                            timestamp,
                            timestamp,
                            worker_id,
                            row["quota_class"],
                        ),
                    )
                    self.store.append_event(
                        connection,
                        aggregate_type="quota_class",
                        aggregate_id=f"{worker_id}:{row['quota_class']}",
                        event_type="QUOTA_STATUS_CHANGED",
                        worker_id=worker_id,
                        quota_class=str(row["quota_class"]),
                        payload={"status": new_status.value},
                        timestamp_ms=timestamp,
                    )
            if selected is None:
                identity_status = (
                    new_status.value
                    if new_status
                    in {
                        WorkerStatus.DRAINING,
                        WorkerStatus.OFFLINE,
                        WorkerStatus.ERROR,
                    }
                    else "ONLINE"
                )
                connection.execute(
                    """
                    UPDATE workers
                    SET identity_status=?,last_seen_at_ms=?,updated_at_ms=?,version=version+1
                    WHERE worker_id=?
                    """,
                    (identity_status, timestamp, timestamp, worker_id),
                )
            active_job_ids = [
                str(item[0])
                for item in connection.execute(
                    """
                    SELECT DISTINCT a.job_id
                    FROM worker_quota_classes q
                    JOIN attempts a ON a.attempt_id=q.held_attempt_id
                    WHERE q.worker_id=?
                    ORDER BY a.job_id
                    """,
                    (worker_id,),
                )
            ]
            self.store.append_event(
                connection,
                aggregate_type="worker",
                aggregate_id=worker_id,
                event_type="WORKER_STATUS_CHANGED",
                worker_id=worker_id,
                payload={
                    "status": new_status.value,
                    "quota_classes": [str(row["quota_class"]) for row in rows],
                    "active_job_ids": active_job_ids,
                },
                timestamp_ms=timestamp,
            )
        worker = self.get_worker(worker_id)
        assert worker is not None
        return worker

    def _rate_limit_held_attempt(
        self,
        connection: sqlite3.Connection,
        *,
        attempt_id: str,
        timestamp: int,
    ) -> None:
        row = connection.execute(
            "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
        ).fetchone()
        if row is None:
            raise StateConflict(f"attempt {attempt_id!r} does not exist")
        if AttemptStatus(row["status"]) not in _WORKER_MUTABLE_ATTEMPT_STATUSES:
            raise StateConflict(f"attempt {attempt_id} cannot rate-limit from {row['status']}")
        if timestamp >= int(row["lease_expires_at_ms"]):
            raise StateConflict(f"attempt {attempt_id} lease has expired; reconcile it first")
        # The compatibility facade reads the protected credential, but the same
        # guarded predicate as an external worker mutation still owns the write.
        AttemptRegistry(self.store)._rate_limit_in_transaction(
            connection,
            row=row,
            fence_generation=int(row["fence_generation"]),
            lease_token=str(row["lease_token"]),
            payload=None,
            timestamp=timestamp,
            actor="operator",
        )

    def release_worker(
        self, worker_id: str, *, quota_class: str | None = None
    ) -> Worker:
        selected = str(quota_class).strip().lower() if quota_class else None
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM worker_quota_classes WHERE worker_id=? ORDER BY quota_class",
                (worker_id,),
            ).fetchall()
            if not rows:
                raise StateConflict(f"worker {worker_id!r} does not exist")
            if selected is None:
                if len(rows) != 1:
                    raise StateConflict("quota_class is required for a multi-class worker")
                selected = str(rows[0]["quota_class"])
            row = next((item for item in rows if item["quota_class"] == selected), None)
            if row is None:
                raise StateConflict(
                    f"worker {worker_id!r} has no quota class {selected!r}"
                )
            if row["held_attempt_id"]:
                raise StateConflict(
                    "release assigned capacity through complete_job, fail_job, requeue_job, or cancel"
                )
            connection.execute(
                """
                UPDATE worker_quota_classes
                SET status='AVAILABLE',last_seen_at_ms=?,updated_at_ms=?,version=version+1
                WHERE worker_id=? AND quota_class=? AND held_attempt_id IS NULL
                """,
                (timestamp, timestamp, worker_id, selected),
            )
            self.store.append_event(
                connection,
                aggregate_type="quota_class",
                aggregate_id=f"{worker_id}:{selected}",
                event_type="QUOTA_RELEASED",
                worker_id=worker_id,
                quota_class=selected,
                timestamp_ms=timestamp,
            )
        worker = self.get_worker(worker_id)
        assert worker is not None
        return worker

    def assign_job(
        self, worker_id: str, job_id: str, *, quota_class: str | None = None
    ) -> Worker:
        runtime = Runtime.from_store(self.store)
        lease = runtime.attempts.claim_job(
            job_id, worker_id=worker_id, quota_class=quota_class
        )
        if lease is None:  # explicit worker selection reports conflict rather than no-op
            raise StateConflict(
                f"worker {worker_id} is unavailable or does not match job constraints"
            )
        worker = self.get_worker(worker_id)
        assert worker is not None
        return worker


class JobRegistry:
    def __init__(self, store: RuntimeStore) -> None:
        self.store = store

    def create_job(
        self,
        objective: str,
        *,
        department: str = "general",
        priority: int = 0,
        authority_level: str = "A0",
        branch: str | None = None,
        worktree: str | None = None,
        constraints: dict[str, Any] | None = None,
        attempt_limit: int = 10,
        available_at_ms: int | None = None,
        requested_authorities: str | list[str] | tuple[str, ...] | None = None,
        allowed_write_paths: list[str] | tuple[str, ...] | None = None,
        validation_commands: list[list[str]] | tuple[tuple[str, ...], ...] | None = None,
        command_id: str | None = None,
        provenance: dict[str, Any] | None = None,
        parent_job_id: str | None = None,
        owner_seat: str = "coo",
        escalation_target: str = "coo",
        business_impact: str = "routine",
        review_required: bool = False,
        reviews_job_id: str | None = None,
    ) -> Job:
        """Insert one QUEUED Job and its ``JOB_CREATED`` receipt in one transaction.

        ``command_id`` lets a bounded caller name the creation command instead of
        taking the default ``uuid4().hex``.  The events table declares
        ``command_id TEXT NOT NULL UNIQUE``, so that is what makes a duplicate
        submission atomic rather than merely unlikely: two concurrent creators
        with the same command id both insert a job row, but the second one's
        event INSERT is rejected *inside* its transaction, and its job row rolls
        back with it.  Exactly one Job survives, with no advisory lock.

        ``provenance`` is recorded under the created event's payload for callers
        that must record who asked and on what grounding.  It changes no job
        column and confers no authority.
        """
        objective = str(objective).strip()
        if not objective:
            raise StateConflict("objective is required")
        if command_id is not None and _COMMAND_ID_RE.fullmatch(str(command_id)) is None:
            # A caller-named command id becomes a durable UNIQUE key, so its
            # shape is fenced here rather than trusted from the call site.
            raise StateConflict("command_id must be a bounded identifier")
        if int(attempt_limit) <= 0:
            raise StateConflict("attempt_limit must be positive")
        owner_seat = _normalise_seat(owner_seat, field="owner_seat")
        escalation_target = _normalise_seat(
            escalation_target, field="escalation_target"
        )
        business_impact = _normalise_business_impact(business_impact)
        if not isinstance(review_required, bool):
            raise StateConflict("review_required must be a boolean")
        if reviews_job_id is not None and review_required:
            raise StateConflict(
                "a review job cannot itself require review when reviews_job_id is set"
            )
        parent_job_id = str(parent_job_id).strip() if parent_job_id else None
        reviews_job_id = str(reviews_job_id).strip() if reviews_job_id else None
        if parent_job_id == "":
            parent_job_id = None
        if reviews_job_id == "":
            reviews_job_id = None
        if owner_seat != "coo" and not _has_executive_provenance(
            provenance, target=owner_seat
        ):
            raise StateConflict(
                f"owner_seat={owner_seat!r} requires its typed executive provenance"
            )
        if escalation_target != "coo" and not _has_executive_provenance(
            provenance, target=escalation_target
        ):
            raise StateConflict(
                f"escalation_target={escalation_target!r} requires its typed executive provenance"
            )
        normalized_constraints = _normalise_constraints(constraints)
        try:
            authority = ExecutiveAuthorityPolicy.load().authorize(
                ["READ"] if requested_authorities is None else requested_authorities,
                worktree=worktree,
                allowed_write_paths=list(allowed_write_paths or []),
                validation_commands=list(validation_commands or []),
            )
        except (AuthorityDenied, AuthorityPolicyError) as exc:
            raise StateConflict(f"job authority is denied: {exc}") from exc
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            parent_row = None
            if parent_job_id is not None:
                parent_row = connection.execute(
                    """
                    SELECT job_id,root_job_id,depth,escalation_target,
                           requested_authorities_json,allowed_write_paths_json,
                           constraints_json
                    FROM jobs WHERE job_id=?
                    """,
                    (parent_job_id,),
                ).fetchone()
                if parent_row is None:
                    raise StateConflict(f"parent job {parent_job_id!r} does not exist")
                if int(parent_row["depth"]) + 1 > _MAX_JOB_DEPTH:
                    raise StateConflict(
                        f"parent job {parent_job_id} would exceed the {_MAX_JOB_DEPTH}-level hierarchy bound"
                    )
                if _ESCALATION_RANK[escalation_target] > _ESCALATION_RANK[
                    str(parent_row["escalation_target"])
                ]:
                    raise StateConflict(
                        "escalation_target may only shrink toward a less authoritative seat"
                    )
                _assert_child_does_not_widen_parent(
                    parent_row,
                    requested=list(authority.requested),
                    allowed_write_paths=list(authority.allowed_write_paths),
                    constraints=normalized_constraints,
                )
            if reviews_job_id is not None:
                reviewed_row = connection.execute(
                    "SELECT job_id,parent_job_id,root_job_id FROM jobs WHERE job_id=?",
                    (reviews_job_id,),
                ).fetchone()
                if reviewed_row is None:
                    raise StateConflict(f"reviewed job {reviews_job_id!r} does not exist")
                if reviewed_row["job_id"] == parent_job_id:
                    raise StateConflict("a job cannot review its own parent container")
                if parent_job_id is None or reviewed_row["parent_job_id"] != parent_job_id:
                    raise StateConflict(
                        "a review job must be a sibling of the job it reviews"
                    )
            depth = 0 if parent_row is None else int(parent_row["depth"]) + 1
            numbers: list[int] = []
            for row in connection.execute("SELECT job_id FROM jobs"):
                match = re.fullmatch(r"JOB-(\d+)", str(row[0]))
                if match:
                    numbers.append(int(match.group(1)))
            number = max(numbers, default=0) + 1
            job_id = f"JOB-{number:03d}"
            root_job_id = (
                job_id
                if parent_row is None
                else str(parent_row["root_job_id"] or parent_row["job_id"])
            )
            connection.execute(
                """
                INSERT INTO jobs(
                  job_id,objective,department,priority,status,authority_level,branch,worktree,
                  constraints_json,requested_authorities_json,authority_policy_hash,
                  allowed_write_paths_json,validation_commands_json,attempt_limit,
                  available_at_ms,created_at_ms,updated_at_ms,parent_job_id,root_job_id,depth,
                  owner_seat,escalation_target,business_impact,review_required,reviews_job_id
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    job_id,
                    objective,
                    str(department or "general"),
                    int(priority),
                    JobStatus.QUEUED.value,
                    str(authority_level or "A0"),
                    str(branch) if branch else None,
                    authority.worktree
                    if authority.worktree is not None
                    else (str(worktree) if worktree else None),
                    _json_dumps(normalized_constraints),
                    _json_dumps(list(authority.requested)),
                    authority.policy_sha256,
                    _json_dumps(list(authority.allowed_write_paths)),
                    _json_dumps([list(item) for item in authority.validation_commands]),
                    int(attempt_limit),
                    timestamp if available_at_ms is None else int(available_at_ms),
                    timestamp,
                    timestamp,
                    parent_job_id,
                    root_job_id,
                    depth,
                    owner_seat,
                    escalation_target,
                    business_impact,
                    int(review_required),
                    reviews_job_id,
                ),
            )
            event_payload: dict[str, Any] = {
                "status": JobStatus.QUEUED.value,
                "parent_job_id": parent_job_id,
                "root_job_id": root_job_id,
                "depth": depth,
                "owner_seat": owner_seat,
                "escalation_target": escalation_target,
                "business_impact": business_impact,
                "review_required": review_required,
                "reviews_job_id": reviews_job_id,
            }
            if provenance is not None:
                event_payload["provenance"] = dict(provenance)
            self.store.append_event(
                connection,
                aggregate_type="job",
                aggregate_id=job_id,
                event_type="JOB_CREATED",
                job_id=job_id,
                payload=event_payload,
                command_id=command_id,
                timestamp_ms=timestamp,
            )
        job = self.get_job(job_id)
        assert job is not None
        return job

    def get_job(self, job_id: str) -> Job | None:
        with self.store.read() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            return _job_from_row(row) if row else None

    def list_jobs(self) -> list[Job]:
        with self.store.read() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY priority DESC,created_at_ms,job_id"
            ).fetchall()
            return [_job_from_row(row) for row in rows]

    def assign_job(
        self, job_id: str, worker_id: str, *, quota_class: str | None = None
    ) -> Job:
        runtime = Runtime.from_store(self.store)
        lease = runtime.attempts.claim_job(
            job_id, worker_id=worker_id, quota_class=quota_class
        )
        if lease is None:
            raise StateConflict(
                f"worker {worker_id} is unavailable or does not match job constraints"
            )
        job = self.get_job(job_id)
        assert job is not None
        return job

    def _credential(self, job_id: str) -> tuple[str, int, str]:
        with self.store.read() as connection:
            row = connection.execute(
                """
                SELECT a.attempt_id,a.fence_generation,a.lease_token
                FROM jobs j JOIN attempts a ON a.attempt_id=j.current_attempt_id
                WHERE j.job_id=?
                """,
                (job_id,),
            ).fetchone()
        if row is None or row["lease_token"] is None:
            raise StateConflict(f"job {job_id} has no active leased attempt")
        return str(row["attempt_id"]), int(row["fence_generation"]), str(row["lease_token"])

    def checkpoint_job(
        self, job_id: str, payload: JobPayload | dict[str, Any]
    ) -> Job:
        attempt_id, fence, token = self._credential(job_id)
        return AttemptRegistry(self.store).checkpoint_attempt(
            attempt_id,
            fence_generation=fence,
            lease_token=token,
            payload=payload,
        )

    def complete_job(
        self, job_id: str, payload: JobPayload | dict[str, Any]
    ) -> Job:
        attempt_id, fence, token = self._credential(job_id)
        return AttemptRegistry(self.store).complete_attempt(
            attempt_id,
            fence_generation=fence,
            lease_token=token,
            payload=payload,
        )

    def fail_job(self, job_id: str, payload: JobPayload | dict[str, Any]) -> Job:
        job = self.get_job(job_id)
        if job is None:
            raise StateConflict(f"job {job_id!r} does not exist")
        if job.status in {
            JobStatus.FAILED,
            JobStatus.COMPLETED,
            JobStatus.CANCELLED,
            JobStatus.LOST,
        }:
            raise StateConflict(f"job {job_id} cannot fail from {job.status.value}")
        attempt_id, fence, token = self._credential(job_id)
        return AttemptRegistry(self.store).fail_attempt(
            attempt_id,
            fence_generation=fence,
            lease_token=token,
            payload=payload,
        )

    def requeue_job(self, job_id: str) -> Job:
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            job_row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if job_row is None:
                raise StateConflict(f"job {job_id!r} does not exist")
            status = JobStatus(job_row["status"])
            if status not in {
                JobStatus.RATE_LIMITED,
                JobStatus.FAILED,
                JobStatus.LOST,
            }:
                raise StateConflict(f"job {job_id} cannot requeue from {status.value}")
            if int(job_row["attempt_count"]) >= int(job_row["attempt_limit"]):
                raise StateConflict(f"job {job_id} exhausted its attempt limit")
            attempt_id = job_row["current_attempt_id"]
            if attempt_id:
                attempt_row = connection.execute(
                    "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
                ).fetchone()
                if attempt_row is None or AttemptStatus(attempt_row["status"]) not in _TERMINAL_ATTEMPT_STATUSES:
                    raise StateConflict(f"job {job_id} still has a lease-active attempt")
                quota_row = connection.execute(
                    """
                    SELECT held_attempt_id FROM worker_quota_classes
                    WHERE worker_id=? AND quota_class=?
                    """,
                    (attempt_row["worker_id"], attempt_row["quota_class"]),
                ).fetchone()
                if quota_row is None:
                    raise PersistenceError(f"job {job_id} lost its quota-class record")
                if status in {JobStatus.RATE_LIMITED, JobStatus.LOST} and (
                    quota_row["held_attempt_id"] != attempt_id
                ):
                    raise PersistenceError(
                        f"job {job_id} terminal attempt is not held by its quota class"
                    )
                connection.execute(
                    """
                    UPDATE worker_quota_classes
                    SET held_attempt_id=NULL,updated_at_ms=?,version=version+1
                    WHERE worker_id=? AND quota_class=? AND held_attempt_id=?
                    """,
                    (
                        timestamp,
                        attempt_row["worker_id"],
                        attempt_row["quota_class"],
                        attempt_id,
                    ),
                )
            connection.execute(
                """
                UPDATE jobs
                SET status='QUEUED',assigned_worker_id=NULL,assigned_quota_class=NULL,
                    current_attempt_id=NULL,result_json=NULL,updated_at_ms=?,version=version+1
                WHERE job_id=?
                """,
                (timestamp, job_id),
            )
            self.store.append_event(
                connection,
                aggregate_type="job",
                aggregate_id=job_id,
                event_type="JOB_REQUEUED",
                job_id=job_id,
                attempt_id=attempt_id,
                payload={"previous_status": status.value},
                timestamp_ms=timestamp,
            )
        job = self.get_job(job_id)
        assert job is not None
        return job

    def cancel_job(self, job_id: str) -> Job:
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            job_row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if job_row is None:
                raise StateConflict(f"job {job_id!r} does not exist")
            status = JobStatus(job_row["status"])
            if status == JobStatus.QUEUED:
                connection.execute(
                    "UPDATE jobs SET status='CANCELLED',updated_at_ms=?,version=version+1 WHERE job_id=?",
                    (timestamp, job_id),
                )
                event_type = "JOB_CANCELLED"
                attempt_id = None
            elif status in {JobStatus.RUNNING, JobStatus.CHECKPOINTED}:
                attempt_id = str(job_row["current_attempt_id"])
                attempt_row = connection.execute(
                    "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
                ).fetchone()
                if attempt_row is None or attempt_row["lease_token"] is None:
                    raise StateConflict(f"job {job_id} has no cancellable attempt")
                AttemptRegistry(self.store)._leased_row(
                    connection,
                    attempt_id=attempt_id,
                    fence_generation=int(attempt_row["fence_generation"]),
                    lease_token=str(attempt_row["lease_token"]),
                    timestamp=timestamp,
                    statuses=_WORKER_MUTABLE_ATTEMPT_STATUSES,
                )
                connection.execute(
                    """
                    UPDATE attempts SET status='CANCEL_REQUESTED',updated_at_ms=?,version=version+1
                    WHERE attempt_id=? AND status IN ('CLAIMED','RUNNING','CHECKPOINTED')
                    """,
                    (timestamp, attempt_id),
                )
                connection.execute(
                    """
                    UPDATE jobs SET status='CANCEL_REQUESTED',cancel_requested_at_ms=?,
                                    updated_at_ms=?,version=version+1
                    WHERE job_id=?
                    """,
                    (timestamp, timestamp, job_id),
                )
                event_type = "JOB_CANCEL_REQUESTED"
            elif status in {
                JobStatus.RATE_LIMITED,
                JobStatus.FAILED,
                JobStatus.LOST,
            }:
                attempt_id = str(job_row["current_attempt_id"])
                attempt_row = connection.execute(
                    "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
                ).fetchone()
                if attempt_row is None or AttemptStatus(attempt_row["status"]) not in _TERMINAL_ATTEMPT_STATUSES:
                    raise PersistenceError(
                        f"terminal job {job_id} has no matching terminal attempt"
                    )
                quota_row = connection.execute(
                    """
                    SELECT held_attempt_id FROM worker_quota_classes
                    WHERE worker_id=? AND quota_class=?
                    """,
                    (attempt_row["worker_id"], attempt_row["quota_class"]),
                ).fetchone()
                if quota_row is None or quota_row["held_attempt_id"] not in {
                    None,
                    attempt_id,
                }:
                    raise PersistenceError(
                        f"terminal job {job_id} has an inconsistent quota-class hold"
                    )
                connection.execute(
                    """
                    UPDATE worker_quota_classes
                    SET held_attempt_id=NULL,updated_at_ms=?,version=version+1
                    WHERE worker_id=? AND quota_class=? AND held_attempt_id=?
                    """,
                    (
                        timestamp,
                        attempt_row["worker_id"],
                        attempt_row["quota_class"],
                        attempt_id,
                    ),
                )
                connection.execute(
                    """
                    UPDATE jobs SET status='CANCELLED',cancel_requested_at_ms=?,
                                    updated_at_ms=?,version=version+1
                    WHERE job_id=?
                    """,
                    (timestamp, timestamp, job_id),
                )
                event_type = "JOB_CANCELLED"
            elif status == JobStatus.CANCEL_REQUESTED:
                return _job_from_row(job_row)
            else:
                raise StateConflict(f"job {job_id} cannot cancel from {status.value}")
            self.store.append_event(
                connection,
                aggregate_type="job",
                aggregate_id=job_id,
                event_type=event_type,
                job_id=job_id,
                attempt_id=attempt_id,
                payload={"previous_status": status.value},
                timestamp_ms=timestamp,
            )
        job = self.get_job(job_id)
        assert job is not None
        return job


class AttemptRegistry:
    def __init__(self, store: RuntimeStore) -> None:
        self.store = store

    def get_attempt(self, attempt_id: str) -> Attempt | None:
        with self.store.read() as connection:
            row = connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
            return _attempt_from_row(row) if row else None

    def list_attempts(self, job_id: str | None = None) -> list[Attempt]:
        with self.store.read() as connection:
            if job_id:
                rows = connection.execute(
                    "SELECT * FROM attempts WHERE job_id=? ORDER BY attempt_number",
                    (job_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM attempts ORDER BY created_at_ms,attempt_id"
                ).fetchall()
            return [_attempt_from_row(row) for row in rows]

    def claim_job(
        self,
        job_id: str,
        *,
        worker_id: str | None = None,
        quota_class: str | None = None,
        lease_seconds: int | None = None,
        lease_owner: str = "local-supervisor",
    ) -> AttemptLease | None:
        duration = self.store.lease_seconds if lease_seconds is None else int(lease_seconds)
        if duration <= 0:
            raise StateConflict("lease_seconds must be positive")
        owner = str(lease_owner).strip()
        if not owner:
            raise StateConflict("lease_owner is required")
        selected_quota = str(quota_class).strip().lower() if quota_class else None
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            job_row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if job_row is None:
                raise StateConflict(f"job {job_id!r} does not exist")
            if JobStatus(job_row["status"]) != JobStatus.QUEUED:
                raise StateConflict(
                    f"job {job_id} is {job_row['status']}, not QUEUED"
                )
            living_children = _living_child_rows(connection, job_id)
            if living_children:
                raise StateConflict(
                    "container job cannot be claimed while child job(s) are living: "
                    + ", ".join(str(row["job_id"]) for row in living_children)
                )
            if timestamp < int(job_row["available_at_ms"]):
                return None
            if int(job_row["attempt_count"]) >= int(job_row["attempt_limit"]):
                raise StateConflict(f"job {job_id} exhausted its attempt limit")
            authority = _authorize_job_row(job_row)
            constraints = _normalise_constraints(
                _json_loads(job_row["constraints_json"], fallback={})
            )
            candidate_rows = connection.execute(
                """
                SELECT q.*,w.provider AS worker_provider,w.identity_status
                FROM worker_quota_classes q JOIN workers w ON w.worker_id=q.worker_id
                WHERE q.status='AVAILABLE' AND q.held_attempt_id IS NULL
                ORDER BY q.worker_id,q.quota_class
                """
            ).fetchall()
            required_provider = str(constraints.get("provider") or "")
            required_model = str(constraints.get("model") or "")
            required_effort = str(constraints.get("effort") or "")
            required_cost_class = str(constraints.get("cost_class") or "")
            required_capabilities = set(
                constraints.get("required_capabilities") or []
            )
            eligible_classes = set(constraints["eligible_quota_classes"])
            candidates: list[sqlite3.Row] = []
            for row in candidate_rows:
                if worker_id and row["worker_id"] != worker_id:
                    continue
                if selected_quota and row["quota_class"] != selected_quota:
                    continue
                if not _capacity_matches_route(row, constraints):
                    continue
                if row["quota_class"] not in eligible_classes:
                    continue
                if required_provider and row["provider"] != required_provider:
                    continue
                if required_model and (row["model"] or "") != required_model:
                    continue
                if required_effort and (row["effort"] or "") != required_effort:
                    continue
                if required_cost_class and (row["cost_class"] or "") != required_cost_class:
                    continue
                if row["identity_status"] != "ONLINE":
                    continue
                capabilities = set(
                    _normalise_capabilities(
                        _json_loads(row["capabilities_json"], fallback=[])
                    )
                )
                if not required_capabilities.issubset(capabilities):
                    continue
                candidates.append(row)
            if not candidates:
                return None
            candidates.sort(key=lambda row: _capacity_route_rank(row, constraints))
            capacity = candidates[0]
            attempt_id = f"ATT-{uuid4().hex}"
            lease_token = secrets.token_urlsafe(32)
            attempt_number = int(job_row["attempt_count"]) + 1
            updated = connection.execute(
                """
                UPDATE worker_quota_classes
                SET status='BUSY',held_attempt_id=?,fence_counter=fence_counter+1,
                    last_seen_at_ms=?,updated_at_ms=?,version=version+1
                WHERE worker_id=? AND quota_class=? AND status='AVAILABLE'
                  AND held_attempt_id IS NULL
                """,
                (
                    attempt_id,
                    timestamp,
                    timestamp,
                    capacity["worker_id"],
                    capacity["quota_class"],
                ),
            )
            if updated.rowcount != 1:
                return None
            fence = int(
                connection.execute(
                    "SELECT fence_counter FROM worker_quota_classes WHERE worker_id=? AND quota_class=?",
                    (capacity["worker_id"], capacity["quota_class"]),
                ).fetchone()[0]
            )
            connection.execute(
                """
                INSERT INTO attempts(
                  attempt_id,job_id,attempt_number,worker_id,quota_class,status,
                  fence_generation,authority_policy_hash,lease_token,lease_owner,lease_expires_at_ms,
                  heartbeat_at_ms,checkpoint_json,started_at_ms,created_at_ms,updated_at_ms
                ) VALUES(?,?,?,?,?,'CLAIMED',?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    attempt_id,
                    job_id,
                    attempt_number,
                    capacity["worker_id"],
                    capacity["quota_class"],
                    fence,
                    authority.policy_sha256,
                    lease_token,
                    owner,
                    timestamp + duration * 1000,
                    timestamp,
                    job_row["checkpoint_json"],
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            updated_job = connection.execute(
                """
                UPDATE jobs
                SET status='RUNNING',assigned_worker_id=?,assigned_quota_class=?,
                    current_attempt_id=?,attempt_count=?,updated_at_ms=?,version=version+1
                WHERE job_id=? AND status='QUEUED' AND current_attempt_id IS NULL
                """,
                (
                    capacity["worker_id"],
                    capacity["quota_class"],
                    attempt_id,
                    attempt_number,
                    timestamp,
                    job_id,
                ),
            )
            if updated_job.rowcount != 1:
                raise StateConflict(f"job {job_id} lost the claim race")
            self.store.append_event(
                connection,
                aggregate_type="job",
                aggregate_id=job_id,
                event_type="JOB_CLAIMED",
                job_id=job_id,
                attempt_id=attempt_id,
                worker_id=str(capacity["worker_id"]),
                quota_class=str(capacity["quota_class"]),
                payload={
                    "attempt_number": attempt_number,
                    "fence_generation": fence,
                    "authority_policy_hash": authority.policy_sha256,
                    "lease_expires_at_ms": timestamp + duration * 1000,
                    "routing_policy_version": constraints.get(
                        "routing_policy_version"
                    ),
                    "preferred_model_aliases": constraints.get(
                        "preferred_model_aliases", []
                    ),
                    "selected_model_alias": _capacity_model_alias(capacity) or None,
                    "routing_reason_codes": constraints.get(
                        "routing_reason_codes", []
                    ),
                },
                timestamp_ms=timestamp,
            )
        attempt = self.get_attempt(attempt_id)
        assert attempt is not None
        return AttemptLease(attempt=attempt, lease_token=lease_token)

    def _leased_row(
        self,
        connection: sqlite3.Connection,
        *,
        attempt_id: str,
        fence_generation: int,
        lease_token: str,
        timestamp: int,
        statuses: set[AttemptStatus],
    ) -> sqlite3.Row:
        row = connection.execute(
            """
            SELECT a.*,j.current_attempt_id,j.status AS job_status,
                   q.held_attempt_id,q.status AS quota_status,
                   q.fence_counter AS quota_fence_counter
            FROM attempts a
            JOIN jobs j ON j.job_id=a.job_id
            JOIN worker_quota_classes q
              ON q.worker_id=a.worker_id AND q.quota_class=a.quota_class
            WHERE a.attempt_id=?
            """,
            (attempt_id,),
        ).fetchone()
        if row is None:
            raise StateConflict(f"attempt {attempt_id!r} does not exist")
        attempt_status = AttemptStatus(row["status"])
        if attempt_status not in statuses:
            raise StateConflict(
                f"attempt {attempt_id} cannot mutate from {row['status']}"
            )
        expected_job_status = _ACTIVE_JOB_STATUS_BY_ATTEMPT[attempt_status]
        if JobStatus(row["job_status"]) != expected_job_status:
            raise PersistenceError(
                f"attempt {attempt_id} and job have inconsistent active states"
            )
        if int(row["fence_generation"]) != int(fence_generation):
            raise StateConflict(f"attempt {attempt_id} has a stale fence")
        if int(row["quota_fence_counter"]) != int(row["fence_generation"]):
            raise PersistenceError(
                f"attempt {attempt_id} and quota class have inconsistent fences"
            )
        persisted_token = row["lease_token"]
        if persisted_token is None or not hmac.compare_digest(
            str(persisted_token), str(lease_token)
        ):
            raise StateConflict(f"attempt {attempt_id} has an invalid lease token")
        if timestamp >= int(row["lease_expires_at_ms"]):
            raise StateConflict(f"attempt {attempt_id} lease has expired")
        if row["current_attempt_id"] != attempt_id or row["held_attempt_id"] != attempt_id:
            raise StateConflict(f"attempt {attempt_id} is no longer current")
        return row

    def adopt_attempt(
        self,
        attempt_id: str,
        *,
        expected_fence_generation: int,
        lease_owner: str,
        lease_seconds: int | None = None,
    ) -> AttemptLease:
        """Rotate a live persisted lease for a restarted trusted supervisor.

        Adoption is compare-and-swap on the public fence generation.  It does
        not assert that the reconstructed process is alive and does not change
        attempt status; the adopter must inspect the persisted process identity
        and then heartbeat, acknowledge cancellation, or explicitly mark it
        lost.  Rotating both fence and token makes every prior owner stale.
        """
        owner = str(lease_owner).strip()
        if not owner:
            raise StateConflict("lease_owner is required for adoption")
        duration = self.store.lease_seconds if lease_seconds is None else int(lease_seconds)
        if duration <= 0:
            raise StateConflict("lease_seconds must be positive")
        timestamp = self.store.now_ms()
        replacement_token = secrets.token_urlsafe(32)
        with self.store.transaction() as connection:
            row = connection.execute(
                """
                SELECT a.*,j.current_attempt_id,j.status AS job_status,q.held_attempt_id,
                       q.fence_counter AS quota_fence_counter
                FROM attempts a
                JOIN jobs j ON j.job_id=a.job_id
                JOIN worker_quota_classes q
                  ON q.worker_id=a.worker_id AND q.quota_class=a.quota_class
                WHERE a.attempt_id=?
                """,
                (attempt_id,),
            ).fetchone()
            if row is None:
                raise StateConflict(f"attempt {attempt_id!r} does not exist")
            attempt_status = AttemptStatus(row["status"])
            if attempt_status not in _LEASE_ACTIVE_ATTEMPT_STATUSES:
                raise StateConflict(
                    f"attempt {attempt_id} cannot be adopted from {row['status']}"
                )
            if JobStatus(row["job_status"]) != _ACTIVE_JOB_STATUS_BY_ATTEMPT[attempt_status]:
                raise PersistenceError(
                    f"attempt {attempt_id} and job have inconsistent active states"
                )
            current_fence = int(row["fence_generation"])
            if current_fence != int(expected_fence_generation):
                raise StateConflict(f"attempt {attempt_id} has a stale adoption fence")
            if int(row["quota_fence_counter"]) != current_fence:
                raise PersistenceError(
                    f"attempt {attempt_id} and quota class have inconsistent fences"
                )
            if timestamp >= int(row["lease_expires_at_ms"]):
                raise StateConflict(f"attempt {attempt_id} lease has expired; reconcile it first")
            if row["lease_token"] is None:
                raise PersistenceError(f"active attempt {attempt_id} has no lease token")
            if row["current_attempt_id"] != attempt_id or row["held_attempt_id"] != attempt_id:
                raise StateConflict(f"attempt {attempt_id} is no longer current")
            if row["pid"] is None and row["provider_session_id"] is None:
                raise StateConflict(
                    f"attempt {attempt_id} has no durable process/provider identity to adopt"
                )
            next_fence = current_fence + 1
            expiry = max(
                int(row["lease_expires_at_ms"]), timestamp + duration * 1_000
            )
            updated_quota = connection.execute(
                """
                UPDATE worker_quota_classes
                SET fence_counter=?,updated_at_ms=?,version=version+1
                WHERE worker_id=? AND quota_class=? AND held_attempt_id=?
                  AND fence_counter=?
                """,
                (
                    next_fence,
                    timestamp,
                    row["worker_id"],
                    row["quota_class"],
                    attempt_id,
                    current_fence,
                ),
            )
            if updated_quota.rowcount != 1:
                raise StateConflict(f"attempt {attempt_id} lost the adoption race")
            updated_attempt = connection.execute(
                """
                UPDATE attempts
                SET fence_generation=?,lease_token=?,lease_owner=?,lease_expires_at_ms=?,
                    heartbeat_at_ms=?,updated_at_ms=?,version=version+1
                WHERE attempt_id=? AND fence_generation=? AND lease_token=?
                  AND status IN ('CLAIMED','RUNNING','CHECKPOINTED','CANCEL_REQUESTED')
                """,
                (
                    next_fence,
                    replacement_token,
                    owner,
                    expiry,
                    timestamp,
                    timestamp,
                    attempt_id,
                    current_fence,
                    row["lease_token"],
                ),
            )
            if updated_attempt.rowcount != 1:
                raise StateConflict(f"attempt {attempt_id} lost the adoption race")
            self.store.append_event(
                connection,
                aggregate_type="attempt",
                aggregate_id=attempt_id,
                event_type="ATTEMPT_ADOPTED",
                actor="supervisor",
                job_id=str(row["job_id"]),
                attempt_id=attempt_id,
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                payload={
                    "previous_fence_generation": current_fence,
                    "fence_generation": next_fence,
                    "previous_lease_owner": str(row["lease_owner"]),
                    "lease_owner": owner,
                    "lease_expires_at_ms": expiry,
                },
                timestamp_ms=timestamp,
            )
        attempt = self.get_attempt(attempt_id)
        assert attempt is not None
        return AttemptLease(attempt=attempt, lease_token=replacement_token)

    def heartbeat_attempt(
        self,
        attempt_id: str,
        *,
        fence_generation: int,
        lease_token: str,
        extend_seconds: int | None = None,
    ) -> Attempt:
        duration = self.store.lease_seconds if extend_seconds is None else int(extend_seconds)
        if duration <= 0:
            raise StateConflict("extend_seconds must be positive")
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = self._leased_row(
                connection,
                attempt_id=attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses=_LEASE_ACTIVE_ATTEMPT_STATUSES,
            )
            expiry = max(int(row["lease_expires_at_ms"]), timestamp + duration * 1000)
            connection.execute(
                """
                UPDATE attempts SET heartbeat_at_ms=?,lease_expires_at_ms=?,updated_at_ms=?,version=version+1
                WHERE attempt_id=?
                """,
                (timestamp, expiry, timestamp, attempt_id),
            )
            connection.execute(
                """
                UPDATE worker_quota_classes
                SET last_seen_at_ms=?,updated_at_ms=?,version=version+1
                WHERE worker_id=? AND quota_class=? AND held_attempt_id=?
                """,
                (timestamp, timestamp, row["worker_id"], row["quota_class"], attempt_id),
            )
            self.store.append_event(
                connection,
                aggregate_type="attempt",
                aggregate_id=attempt_id,
                event_type="ATTEMPT_HEARTBEAT",
                job_id=str(row["job_id"]),
                attempt_id=attempt_id,
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                payload={"lease_expires_at_ms": expiry},
                timestamp_ms=timestamp,
            )
        attempt = self.get_attempt(attempt_id)
        assert attempt is not None
        return attempt

    def record_process(
        self,
        attempt_id: str,
        *,
        fence_generation: int,
        lease_token: str,
        pid: int | None = None,
        pgid: int | None = None,
        process_start_identity: str | None = None,
        boot_id: str | None = None,
        provider_session_id: str | None = None,
        stdout_path: str | None = None,
        stderr_path: str | None = None,
        result_path: str | None = None,
        launch_metadata: dict[str, Any] | None = None,
    ) -> Attempt:
        """Persist the identity needed to reconstruct one claimed invocation.

        A local process is identified by PID, process group, boot identity, and
        process-start identity together so PID reuse cannot be mistaken for the
        claimed process.  A provider-managed invocation may instead be
        reconstructed by its provider session id.
        """
        if launch_metadata is not None and not isinstance(launch_metadata, dict):
            raise StateConflict("launch_metadata must be a mapping")
        local_values = (pid, pgid, process_start_identity, boot_id)
        if pid is None:
            if any(value is not None for value in local_values):
                raise StateConflict(
                    "pid, pgid, process_start_identity, and boot_id must be recorded together"
                )
        else:
            if int(pid) <= 0 or pgid is None or int(pgid) <= 0:
                raise StateConflict("pid and pgid must be positive")
            if not str(process_start_identity or "").strip() or not str(boot_id or "").strip():
                raise StateConflict(
                    "a local process requires process_start_identity and boot_id"
                )
        provider_session = str(provider_session_id or "").strip() or None
        if pid is None and provider_session is None:
            raise StateConflict(
                "record_process requires a local process identity or provider_session_id"
            )
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = self._leased_row(
                connection,
                attempt_id=attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses={AttemptStatus.CLAIMED},
            )
            if row["pid"] is not None or row["provider_session_id"] is not None:
                raise StateConflict(f"attempt {attempt_id} already has a process identity")
            connection.execute(
                """
                UPDATE attempts
                SET pid=?,pgid=?,process_start_identity=?,boot_id=?,provider_session_id=?,
                    stdout_path=?,stderr_path=?,result_path=?,launch_metadata_json=?,
                    updated_at_ms=?,version=version+1
                WHERE attempt_id=? AND status='CLAIMED'
                """,
                (
                    int(pid) if pid is not None else None,
                    int(pgid) if pgid is not None else None,
                    str(process_start_identity).strip()
                    if process_start_identity is not None
                    else None,
                    str(boot_id).strip() if boot_id is not None else None,
                    provider_session,
                    str(stdout_path) if stdout_path is not None else None,
                    str(stderr_path) if stderr_path is not None else None,
                    str(result_path) if result_path is not None else None,
                    _json_dumps(launch_metadata or {}),
                    timestamp,
                    attempt_id,
                ),
            )
            self.store.append_event(
                connection,
                aggregate_type="attempt",
                aggregate_id=attempt_id,
                event_type="ATTEMPT_PROCESS_RECORDED",
                actor="supervisor",
                job_id=str(row["job_id"]),
                attempt_id=attempt_id,
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                payload={"process_kind": "local" if pid is not None else "provider"},
                timestamp_ms=timestamp,
            )
        attempt = self.get_attempt(attempt_id)
        assert attempt is not None
        return attempt

    def mark_running(
        self,
        attempt_id: str,
        *,
        fence_generation: int,
        lease_token: str,
        required_launch_attestation_schema: str | None = None,
    ) -> Attempt:
        """Fence the CLAIMED -> RUNNING transition after invocation identity is durable."""
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = self._leased_row(
                connection,
                attempt_id=attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses={AttemptStatus.CLAIMED},
            )
            if row["pid"] is None and row["provider_session_id"] is None:
                raise StateConflict(
                    f"attempt {attempt_id} has no durable process/provider identity"
                )
            if required_launch_attestation_schema is not None:
                metadata = _json_loads(row["launch_metadata_json"], fallback={})
                attestation = (
                    metadata.get("launch_attestation")
                    if isinstance(metadata, dict)
                    else None
                )
                required = {
                    "schema_version",
                    "created_at",
                    "executable_path",
                    "binary",
                    "rendered_argv",
                    "environment_keys",
                    "permission_profile_sha256",
                    "prompt_sha256",
                    "expected_base_sha",
                    "observed_base_sha",
                    "workspace_identity",
                    "worker_identity",
                    "provider_home_identity",
                    "secret_canary_verdict",
                    "launch_nonce",
                    "process_identity",
                }
                if not isinstance(attestation, dict) or not required.issubset(attestation):
                    raise StateConflict(
                        f"attempt {attempt_id} has no complete launch attestation"
                    )
                if attestation.get("schema_version") != required_launch_attestation_schema:
                    raise StateConflict(
                        f"attempt {attempt_id} launch attestation schema is not accepted"
                    )
                if not isinstance(attestation.get("rendered_argv"), list) or not attestation[
                    "rendered_argv"
                ]:
                    raise StateConflict("launch attestation has no rendered argv")
                environment_keys = attestation.get("environment_keys")
                if (
                    not isinstance(environment_keys, list)
                    or any(not isinstance(key, str) or not key for key in environment_keys)
                    or len(environment_keys) != len(set(environment_keys))
                ):
                    raise StateConflict("launch attestation environment allow-list is invalid")
                for digest_field in ("permission_profile_sha256", "prompt_sha256"):
                    digest = attestation.get(digest_field)
                    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                        raise StateConflict(
                            f"launch attestation {digest_field} is not a SHA-256"
                        )
                canary = attestation.get("secret_canary_verdict")
                if not isinstance(canary, dict) or canary.get("passed") is not True:
                    raise StateConflict("launch attestation secret canary did not pass")
                process_identity = attestation.get("process_identity")
                if not isinstance(process_identity, dict) or any(
                    process_identity.get(key) != expected
                    for key, expected in (
                        ("pid", row["pid"]),
                        ("pgid", row["pgid"]),
                        ("start_identity", row["process_start_identity"]),
                        ("boot_id", row["boot_id"]),
                    )
                ):
                    raise StateConflict(
                        "launch attestation process identity differs from durable columns"
                    )
            updated = connection.execute(
                """
                UPDATE attempts SET status='RUNNING',updated_at_ms=?,version=version+1
                WHERE attempt_id=? AND status='CLAIMED'
                """,
                (timestamp, attempt_id),
            )
            if updated.rowcount != 1:
                raise StateConflict(f"attempt {attempt_id} lost the running transition")
            self.store.append_event(
                connection,
                aggregate_type="attempt",
                aggregate_id=attempt_id,
                event_type="ATTEMPT_RUNNING",
                actor="supervisor",
                job_id=str(row["job_id"]),
                attempt_id=attempt_id,
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                timestamp_ms=timestamp,
            )
        attempt = self.get_attempt(attempt_id)
        assert attempt is not None
        return attempt

    def record_process_exit(
        self,
        attempt_id: str,
        *,
        fence_generation: int,
        lease_token: str,
        exit_code: int,
        result_path: str | None = None,
        provider_session_id: str | None = None,
    ) -> Attempt:
        """Persist a fenced exit observation before the result transition."""
        provider_session = str(provider_session_id or "").strip() or None
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = self._leased_row(
                connection,
                attempt_id=attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses={
                    AttemptStatus.RUNNING,
                    AttemptStatus.CHECKPOINTED,
                    AttemptStatus.CANCEL_REQUESTED,
                },
            )
            if row["exit_code"] is not None:
                raise StateConflict(f"attempt {attempt_id} already has an exit observation")
            if (
                provider_session is not None
                and row["provider_session_id"] is not None
                and row["provider_session_id"] != provider_session
            ):
                raise StateConflict(
                    f"attempt {attempt_id} provider session identity changed"
                )
            connection.execute(
                """
                UPDATE attempts SET exit_code=?,result_path=COALESCE(?,result_path),
                                    provider_session_id=COALESCE(provider_session_id,?),
                                    updated_at_ms=?,version=version+1
                WHERE attempt_id=?
                """,
                (
                    int(exit_code),
                    str(result_path) if result_path is not None else None,
                    provider_session,
                    timestamp,
                    attempt_id,
                ),
            )
            self.store.append_event(
                connection,
                aggregate_type="attempt",
                aggregate_id=attempt_id,
                event_type="ATTEMPT_PROCESS_EXITED",
                actor="supervisor",
                job_id=str(row["job_id"]),
                attempt_id=attempt_id,
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                payload={"exit_code": int(exit_code)},
                timestamp_ms=timestamp,
            )
        attempt = self.get_attempt(attempt_id)
        assert attempt is not None
        return attempt

    def checkpoint_attempt(
        self,
        attempt_id: str,
        *,
        fence_generation: int,
        lease_token: str,
        payload: JobPayload | dict[str, Any],
        checkpoint_sequence: int | None = None,
    ) -> Job:
        checkpoint = JobPayload.from_value(payload).to_dict()
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = self._leased_row(
                connection,
                attempt_id=attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses=_WORKER_MUTABLE_ATTEMPT_STATUSES,
            )
            expected = int(row["checkpoint_sequence"]) + 1
            sequence = expected if checkpoint_sequence is None else int(checkpoint_sequence)
            if sequence != expected:
                raise StateConflict(
                    f"attempt {attempt_id} expected checkpoint sequence {expected}, got {sequence}"
                )
            expiry = max(
                int(row["lease_expires_at_ms"]),
                timestamp + self.store.lease_seconds * 1000,
            )
            connection.execute(
                """
                UPDATE attempts
                SET status='CHECKPOINTED',checkpoint_sequence=?,checkpoint_json=?,heartbeat_at_ms=?,
                    lease_expires_at_ms=?,updated_at_ms=?,version=version+1
                WHERE attempt_id=?
                """,
                (sequence, _json_dumps(checkpoint), timestamp, expiry, timestamp, attempt_id),
            )
            connection.execute(
                """
                UPDATE jobs SET status='CHECKPOINTED',checkpoint_json=?,updated_at_ms=?,version=version+1
                WHERE job_id=? AND current_attempt_id=?
                """,
                (_json_dumps(checkpoint), timestamp, row["job_id"], attempt_id),
            )
            self.store.append_event(
                connection,
                aggregate_type="job",
                aggregate_id=str(row["job_id"]),
                event_type="JOB_CHECKPOINTED",
                job_id=str(row["job_id"]),
                attempt_id=attempt_id,
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                payload={"checkpoint_sequence": sequence},
                timestamp_ms=timestamp,
            )
        job = JobRegistry(self.store).get_job(str(row["job_id"]))
        assert job is not None
        return job

    def _terminal(
        self,
        attempt_id: str,
        *,
        fence_generation: int,
        lease_token: str,
        status: AttemptStatus,
        job_status: JobStatus,
        payload: JobPayload | dict[str, Any],
        event_type: str,
    ) -> Job:
        structured = JobPayload.from_value(payload).to_dict()
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = self._leased_row(
                connection,
                attempt_id=attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses=_WORKER_MUTABLE_ATTEMPT_STATUSES,
            )
            if status is AttemptStatus.COMPLETED:
                _assert_parent_aggregation_allowed(
                    connection, parent_job_id=str(row["job_id"])
                )
            review_evidence = _review_void_evidence(
                connection,
                job_id=str(row["job_id"]),
                worker_id=str(row["worker_id"]),
            )
            result_json = _json_dumps(structured)
            error_json = result_json if status == AttemptStatus.FAILED else None
            connection.execute(
                """
                UPDATE attempts
                SET status=?,lease_token=NULL,result_json=?,error_json=?,finished_at_ms=?,
                    updated_at_ms=?,version=version+1
                WHERE attempt_id=?
                """,
                (
                    status.value,
                    result_json,
                    error_json,
                    timestamp,
                    timestamp,
                    attempt_id,
                ),
            )
            connection.execute(
                """
                UPDATE jobs SET status=?,result_json=?,updated_at_ms=?,version=version+1
                WHERE job_id=? AND current_attempt_id=?
                """,
                (job_status.value, result_json, timestamp, row["job_id"], attempt_id),
            )
            connection.execute(
                """
                UPDATE worker_quota_classes
                SET held_attempt_id=NULL,
                    status=CASE WHEN status='BUSY' THEN 'AVAILABLE' ELSE status END,
                    updated_at_ms=?,version=version+1
                WHERE worker_id=? AND quota_class=? AND held_attempt_id=?
                """,
                (timestamp, row["worker_id"], row["quota_class"], attempt_id),
            )
            event_payload: dict[str, Any] = {"status": job_status.value}
            if review_evidence is not None:
                event_payload["review"] = review_evidence
            self.store.append_event(
                connection,
                aggregate_type="job",
                aggregate_id=str(row["job_id"]),
                event_type=event_type,
                job_id=str(row["job_id"]),
                attempt_id=attempt_id,
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                payload=event_payload,
                timestamp_ms=timestamp,
            )
            job_id = str(row["job_id"])
        job = JobRegistry(self.store).get_job(job_id)
        assert job is not None
        return job

    def complete_attempt(
        self,
        attempt_id: str,
        *,
        fence_generation: int,
        lease_token: str,
        payload: JobPayload | dict[str, Any],
    ) -> Job:
        return self._terminal(
            attempt_id,
            fence_generation=fence_generation,
            lease_token=lease_token,
            status=AttemptStatus.COMPLETED,
            job_status=JobStatus.COMPLETED,
            payload=payload,
            event_type="JOB_COMPLETED",
        )

    def fail_attempt(
        self,
        attempt_id: str,
        *,
        fence_generation: int,
        lease_token: str,
        payload: JobPayload | dict[str, Any],
    ) -> Job:
        return self._terminal(
            attempt_id,
            fence_generation=fence_generation,
            lease_token=lease_token,
            status=AttemptStatus.FAILED,
            job_status=JobStatus.FAILED,
            payload=payload,
            event_type="JOB_FAILED",
        )

    def mark_lost(
        self,
        attempt_id: str,
        *,
        fence_generation: int,
        lease_token: str,
        reason: str,
        verified_process_absent: bool = False,
    ) -> Job:
        """Record a verified missing/killed invocation before lease expiry.

        Callers must first compare the durable PID/start/boot identity (or
        provider session) with the live process.  Unverified suspicions wait for
        lease-expiry reconciliation and cannot prematurely free or fence work.
        """
        reason = str(reason).strip()
        if not reason:
            raise StateConflict("mark_lost requires a reason")
        if verified_process_absent is not True:
            raise StateConflict("mark_lost requires verified_process_absent=True")
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = self._leased_row(
                connection,
                attempt_id=attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses=_LEASE_ACTIVE_ATTEMPT_STATUSES,
            )
            if row["pid"] is None and row["provider_session_id"] is None:
                raise StateConflict(
                    f"attempt {attempt_id} has no durable process/provider identity to verify"
                )
            error = {
                "reason": reason,
                "verified_process_absent": True,
            }
            connection.execute(
                """
                UPDATE attempts
                SET status='LOST',lease_token=NULL,error_json=?,finished_at_ms=?,
                    updated_at_ms=?,version=version+1
                WHERE attempt_id=?
                """,
                (_json_dumps(error), timestamp, timestamp, attempt_id),
            )
            connection.execute(
                """
                UPDATE jobs SET status='LOST',updated_at_ms=?,version=version+1
                WHERE job_id=? AND current_attempt_id=?
                """,
                (timestamp, row["job_id"], attempt_id),
            )
            connection.execute(
                """
                UPDATE worker_quota_classes
                SET status='ERROR',updated_at_ms=?,version=version+1
                WHERE worker_id=? AND quota_class=? AND held_attempt_id=?
                """,
                (timestamp, row["worker_id"], row["quota_class"], attempt_id),
            )
            self.store.append_event(
                connection,
                aggregate_type="job",
                aggregate_id=str(row["job_id"]),
                event_type="ATTEMPT_LOST",
                actor="supervisor",
                job_id=str(row["job_id"]),
                attempt_id=attempt_id,
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                payload=error,
                timestamp_ms=timestamp,
            )
            job_id = str(row["job_id"])
        job = JobRegistry(self.store).get_job(job_id)
        assert job is not None
        return job

    def _rate_limit_in_transaction(
        self,
        connection: sqlite3.Connection,
        *,
        row: sqlite3.Row,
        fence_generation: int,
        lease_token: str,
        payload: JobPayload | dict[str, Any] | None,
        timestamp: int,
        actor: str,
    ) -> str:
        # Re-run all guards even when the compatibility facade sourced the
        # credential from the database.
        guarded = self._leased_row(
            connection,
            attempt_id=str(row["attempt_id"]),
            fence_generation=fence_generation,
            lease_token=lease_token,
            timestamp=timestamp,
            statuses=_WORKER_MUTABLE_ATTEMPT_STATUSES,
        )
        checkpoint = (
            JobPayload.from_value(payload).to_dict() if payload is not None else None
        )
        checkpoint_json = (
            _json_dumps(checkpoint) if checkpoint is not None else guarded["checkpoint_json"]
        )
        checkpoint_sequence = int(guarded["checkpoint_sequence"]) + (
            1 if payload is not None else 0
        )
        connection.execute(
            """
            UPDATE attempts
            SET status='RATE_LIMITED',lease_token=NULL,checkpoint_sequence=?,checkpoint_json=?,
                finished_at_ms=?,updated_at_ms=?,version=version+1
            WHERE attempt_id=?
            """,
            (
                checkpoint_sequence,
                checkpoint_json,
                timestamp,
                timestamp,
                guarded["attempt_id"],
            ),
        )
        connection.execute(
            """
            UPDATE jobs SET status='RATE_LIMITED',checkpoint_json=?,updated_at_ms=?,version=version+1
            WHERE job_id=? AND current_attempt_id=?
            """,
            (checkpoint_json, timestamp, guarded["job_id"], guarded["attempt_id"]),
        )
        connection.execute(
            """
            UPDATE worker_quota_classes
            SET status='RATE_LIMITED',updated_at_ms=?,version=version+1
            WHERE worker_id=? AND quota_class=? AND held_attempt_id=?
            """,
            (
                timestamp,
                guarded["worker_id"],
                guarded["quota_class"],
                guarded["attempt_id"],
            ),
        )
        self.store.append_event(
            connection,
            aggregate_type="job",
            aggregate_id=str(guarded["job_id"]),
            event_type="JOB_RATE_LIMITED",
            actor=actor,
            job_id=str(guarded["job_id"]),
            attempt_id=str(guarded["attempt_id"]),
            worker_id=str(guarded["worker_id"]),
            quota_class=str(guarded["quota_class"]),
            payload={"checkpoint_sequence": checkpoint_sequence},
            timestamp_ms=timestamp,
        )
        return str(guarded["job_id"])

    def rate_limit_attempt(
        self,
        attempt_id: str,
        *,
        fence_generation: int,
        lease_token: str,
        payload: JobPayload | dict[str, Any] | None = None,
    ) -> Job:
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
            if row is None:
                raise StateConflict(f"attempt {attempt_id!r} does not exist")
            job_id = self._rate_limit_in_transaction(
                connection,
                row=row,
                fence_generation=fence_generation,
                lease_token=lease_token,
                payload=payload,
                timestamp=timestamp,
                actor="worker",
            )
        job = JobRegistry(self.store).get_job(job_id)
        assert job is not None
        return job

    def acknowledge_cancel(
        self,
        attempt_id: str,
        *,
        fence_generation: int,
        lease_token: str,
    ) -> Job:
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = self._leased_row(
                connection,
                attempt_id=attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses={AttemptStatus.CANCEL_REQUESTED},
            )
            connection.execute(
                """
                UPDATE attempts SET status='CANCELLED',lease_token=NULL,finished_at_ms=?,
                                    updated_at_ms=?,version=version+1
                WHERE attempt_id=?
                """,
                (timestamp, timestamp, attempt_id),
            )
            connection.execute(
                """
                UPDATE jobs SET status='CANCELLED',updated_at_ms=?,version=version+1
                WHERE job_id=? AND current_attempt_id=? AND status='CANCEL_REQUESTED'
                """,
                (timestamp, row["job_id"], attempt_id),
            )
            connection.execute(
                """
                UPDATE worker_quota_classes
                SET held_attempt_id=NULL,
                    status=CASE WHEN status='BUSY' THEN 'AVAILABLE' ELSE status END,
                    updated_at_ms=?,version=version+1
                WHERE worker_id=? AND quota_class=? AND held_attempt_id=?
                """,
                (timestamp, row["worker_id"], row["quota_class"], attempt_id),
            )
            self.store.append_event(
                connection,
                aggregate_type="job",
                aggregate_id=str(row["job_id"]),
                event_type="JOB_CANCELLED",
                job_id=str(row["job_id"]),
                attempt_id=attempt_id,
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                timestamp_ms=timestamp,
            )
            job_id = str(row["job_id"])
        job = JobRegistry(self.store).get_job(job_id)
        assert job is not None
        return job

    def reconcile_expired(
        self,
        *,
        now_ms: int | None = None,
        attempt_id: str | None = None,
    ) -> list[Attempt]:
        """Fence expired current attempts, optionally one inspected attempt only.

        The targeted form lets a process-aware supervisor prove one persisted
        invocation absent before applying lease-expiry state transitions.  The
        untargeted form remains the registry-level compatibility operation.
        """
        timestamp = self.store.now_ms() if now_ms is None else int(now_ms)
        lost_ids: list[str] = []
        with self.store.transaction() as connection:
            target_clause = " AND a.attempt_id=?" if attempt_id is not None else ""
            parameters: tuple[Any, ...] = (
                (timestamp, str(attempt_id))
                if attempt_id is not None
                else (timestamp,)
            )
            rows = connection.execute(
                f"""
                SELECT a.*,j.current_attempt_id,j.status AS job_status,q.held_attempt_id,
                       q.fence_counter AS quota_fence_counter
                FROM attempts a
                JOIN jobs j ON j.job_id=a.job_id
                JOIN worker_quota_classes q
                  ON q.worker_id=a.worker_id AND q.quota_class=a.quota_class
                WHERE a.status IN ('CLAIMED','RUNNING','CHECKPOINTED','CANCEL_REQUESTED')
                  AND a.lease_expires_at_ms<=?
                  {target_clause}
                ORDER BY a.lease_expires_at_ms,a.attempt_id
                """,
                parameters,
            ).fetchall()
            for row in rows:
                attempt_id = str(row["attempt_id"])
                if row["current_attempt_id"] != attempt_id or row["held_attempt_id"] != attempt_id:
                    raise PersistenceError(
                        f"expired attempt {attempt_id} has inconsistent current links"
                    )
                if int(row["quota_fence_counter"]) != int(row["fence_generation"]):
                    raise PersistenceError(
                        f"expired attempt {attempt_id} has an inconsistent quota fence"
                    )
                attempt_status = AttemptStatus(row["status"])
                if JobStatus(row["job_status"]) != _ACTIVE_JOB_STATUS_BY_ATTEMPT[attempt_status]:
                    raise PersistenceError(
                        f"expired attempt {attempt_id} has an inconsistent job state"
                    )
                cancel_was_requested = (
                    attempt_status == AttemptStatus.CANCEL_REQUESTED
                )
                error = {
                    "reason": "lease_expired",
                    "expired_at_ms": int(row["lease_expires_at_ms"]),
                }
                connection.execute(
                    """
                    UPDATE attempts
                    SET status='LOST',lease_token=NULL,error_json=?,finished_at_ms=?,
                        updated_at_ms=?,version=version+1
                    WHERE attempt_id=? AND status IN ('CLAIMED','RUNNING','CHECKPOINTED','CANCEL_REQUESTED')
                      AND lease_expires_at_ms<=?
                    """,
                    (_json_dumps(error), timestamp, timestamp, attempt_id, timestamp),
                )
                connection.execute(
                    """
                    UPDATE jobs SET status=?,updated_at_ms=?,version=version+1
                    WHERE job_id=? AND current_attempt_id=?
                    """,
                    (
                        JobStatus.CANCELLED.value
                        if cancel_was_requested
                        else JobStatus.LOST.value,
                        timestamp,
                        row["job_id"],
                        attempt_id,
                    ),
                )
                connection.execute(
                    """
                    UPDATE worker_quota_classes
                    SET status='ERROR',
                        held_attempt_id=CASE WHEN ? THEN NULL ELSE held_attempt_id END,
                        updated_at_ms=?,version=version+1
                    WHERE worker_id=? AND quota_class=? AND held_attempt_id=?
                    """,
                    (
                        1 if cancel_was_requested else 0,
                        timestamp,
                        row["worker_id"],
                        row["quota_class"],
                        attempt_id,
                    ),
                )
                self.store.append_event(
                    connection,
                    aggregate_type="job",
                    aggregate_id=str(row["job_id"]),
                    event_type=(
                        "JOB_CANCELLED_AFTER_LEASE_LOSS"
                        if cancel_was_requested
                        else "ATTEMPT_LOST"
                    ),
                    actor="reconciler",
                    job_id=str(row["job_id"]),
                    attempt_id=attempt_id,
                    worker_id=str(row["worker_id"]),
                    quota_class=str(row["quota_class"]),
                    payload=error,
                    timestamp_ms=timestamp,
                )
                lost_ids.append(attempt_id)
        return [
            attempt
            for attempt_id in lost_ids
            if (attempt := self.get_attempt(attempt_id)) is not None
        ]

    restart_reconcile = reconcile_expired


class EventRegistry:
    def __init__(self, store: RuntimeStore) -> None:
        self.store = store

    def get_event_by_command_id(self, command_id: str) -> Event | None:
        """Full Event lookup by durable command id."""

        return self.store.get_event_by_command_id(command_id)

    def list_events(
        self,
        *,
        job_id: str | None = None,
        attempt_id: str | None = None,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
    ) -> list[Event]:
        clauses: list[str] = []
        params: list[str] = []
        if job_id:
            clauses.append("job_id=?")
            params.append(job_id)
        if attempt_id:
            clauses.append("attempt_id=?")
            params.append(attempt_id)
        if aggregate_type:
            clauses.append("aggregate_type=?")
            params.append(str(aggregate_type).strip())
        if aggregate_id:
            clauses.append("aggregate_id=?")
            params.append(str(aggregate_id).strip())
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.store.read() as connection:
            rows = connection.execute(
                f"SELECT * FROM events{where} ORDER BY event_id", params
            ).fetchall()
            return [_event_from_row(row) for row in rows]


class ResourceBroker:
    def __init__(self, store: RuntimeStore) -> None:
        self.store = store

    def _matching_capacity(
        self, job: Job, worker_id: str | None = None
    ) -> WorkerQuotaClass | None:
        required_provider = str(job.constraints.get("provider") or "")
        required_model = str(job.constraints.get("model") or "")
        required_effort = str(job.constraints.get("effort") or "")
        required_cost_class = str(job.constraints.get("cost_class") or "")
        required_capabilities = set(
            job.constraints.get("required_capabilities") or []
        )
        eligible = set(job.constraints["eligible_quota_classes"])
        with self.store.read() as connection:
            rows = connection.execute(
                """
                SELECT q.*,a.job_id AS active_job_id,w.provider AS worker_provider,w.identity_status
                FROM worker_quota_classes q
                JOIN workers w ON w.worker_id=q.worker_id
                LEFT JOIN attempts a ON a.attempt_id=q.held_attempt_id
                WHERE q.status='AVAILABLE' AND q.held_attempt_id IS NULL
                ORDER BY q.worker_id,q.quota_class
                """
            ).fetchall()
        candidates: list[sqlite3.Row] = []
        for row in rows:
            if worker_id and row["worker_id"] != worker_id:
                continue
            if not _capacity_matches_route(row, job.constraints):
                continue
            if row["quota_class"] not in eligible:
                continue
            if required_provider and row["provider"] != required_provider:
                continue
            if required_model and (row["model"] or "") != required_model:
                continue
            if required_effort and (row["effort"] or "") != required_effort:
                continue
            if required_cost_class and (row["cost_class"] or "") != required_cost_class:
                continue
            if row["identity_status"] != "ONLINE":
                continue
            quota = _quota_from_row(row)
            if required_capabilities.issubset(set(quota.capabilities)):
                candidates.append(row)
        if not candidates:
            return None
        candidates.sort(key=lambda row: _capacity_route_rank(row, job.constraints))
        return _quota_from_row(candidates[0])

    def select_worker(self, job: Job | str) -> Worker | None:
        selected_job = (
            JobRegistry(self.store).get_job(job) if isinstance(job, str) else job
        )
        if selected_job is None:
            raise StateConflict(f"job {job!r} does not exist")
        if selected_job.status != JobStatus.QUEUED:
            return None
        with self.store.read() as connection:
            if _living_child_rows(connection, selected_job.job_id):
                return None
        capacity = self._matching_capacity(selected_job)
        return (
            WorkerRegistry(self.store).get_worker(capacity.worker_id)
            if capacity
            else None
        )

    def claim(self, job_id: str, **kwargs: Any) -> AttemptLease | None:
        return AttemptRegistry(self.store).claim_job(job_id, **kwargs)

    def dispatch(self, job_id: str) -> Worker | None:
        lease = self.claim(job_id)
        if lease is None:
            return None
        return WorkerRegistry(self.store).get_worker(lease.attempt.worker_id)


@dataclasses.dataclass(frozen=True)
class Runtime:
    store: RuntimeStore
    workers: WorkerRegistry
    jobs: JobRegistry
    attempts: AttemptRegistry
    events: EventRegistry
    broker: ResourceBroker

    @classmethod
    def from_store(cls, store: RuntimeStore) -> "Runtime":
        return cls(
            store=store,
            workers=WorkerRegistry(store),
            jobs=JobRegistry(store),
            attempts=AttemptRegistry(store),
            events=EventRegistry(store),
            broker=ResourceBroker(store),
        )

    @classmethod
    def at(
        cls,
        root: str | Path | None = None,
        *,
        clock: Callable[[], int | float | datetime] | None = None,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
        create: bool = True,
    ) -> "Runtime":
        return cls.from_store(
            RuntimeStore(
                root,
                clock=clock,
                lease_seconds=lease_seconds,
                busy_timeout_ms=busy_timeout_ms,
                create=create,
            )
        )


__all__ = [
    "Attempt",
    "AttemptLease",
    "AttemptRegistry",
    "AttemptStatus",
    "Event",
    "EventRegistry",
    "Job",
    "JobPayload",
    "JobRegistry",
    "JobStatus",
    "PersistenceError",
    "ResourceBroker",
    "Runtime",
    "RuntimeProofError",
    "RuntimeStore",
    "SCHEMA_VERSION",
    "StateConflict",
    "Worker",
    "WorkerQuotaClass",
    "WorkerRegistry",
    "WorkerStatus",
]
