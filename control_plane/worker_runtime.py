"""Small, local worker/job runtime proof for the Mastermind Executive OS.

This module proves persistence and lifecycle semantics only.  It does not launch
Codex, Claude, or any other provider; it stores provider/account labels but no
credentials; and ``authority_level`` is inert classification metadata.

The authoritative state is one JSON snapshot so linked worker/job transitions
are crash-atomic.  Every mutation uses the existing control-plane ``flock``
primitive, then durably replaces the snapshot.  The existing run-event ledger is
used only for best-effort post-commit telemetry, never as state authority.
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, TypeVar
from uuid import uuid4

from control_plane import locks


SCHEMA_VERSION = 1
_ROOT = Path(__file__).resolve().parent.parent
_STATE_RELATIVE_PATH = Path("jobs") / "executive_os_phase1a" / "state.json"
_LOCK_NAME = "global:executive_os_phase1a"
_WORKER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

_T = TypeVar("_T")


class RuntimeProofError(RuntimeError):
    """Base error for operator-visible Phase 1A failures."""


class PersistenceError(RuntimeProofError):
    """The durable snapshot could not be safely read or written."""


class StateConflict(RuntimeProofError):
    """The requested operation conflicts with the current state machine."""


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
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


_ACTIVE_JOB_STATUSES = {
    JobStatus.RUNNING,
    JobStatus.CHECKPOINTED,
    JobStatus.RATE_LIMITED,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _enum_value(value: str | Enum, enum_type: type[Enum]) -> str:
    try:
        return str(enum_type(value).value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise StateConflict(f"invalid {enum_type.__name__} {value!r}; expected one of {allowed}") from exc


def _normalise_capabilities(
    values: str | list[str] | tuple[str, ...] | None,
) -> list[str]:
    if isinstance(values, str):
        values = [values]
    elif values is not None and not isinstance(values, (list, tuple)):
        raise StateConflict("capabilities must be a string or list")
    return sorted({str(value).strip().lower() for value in (values or []) if str(value).strip()})


@dataclasses.dataclass(frozen=True)
class JobPayload:
    """Structured checkpoint/result payload shared by mock and future workers."""

    summary: str = ""
    completed_steps: list[str] = dataclasses.field(default_factory=list)
    current_state: str = ""
    artifacts: list[str] = dataclasses.field(default_factory=list)
    next_actions: list[str] = dataclasses.field(default_factory=list)
    errors: list[str] = dataclasses.field(default_factory=list)

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

        return cls(
            summary=str(value.get("summary") or ""),
            completed_steps=_strings("completed_steps"),
            current_state=str(value.get("current_state") or ""),
            artifacts=_strings("artifacts"),
            next_actions=_strings("next_actions"),
            errors=_strings("errors"),
        )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


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

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Worker":
        try:
            return cls(
                worker_id=str(value["worker_id"]),
                provider=str(value.get("provider") or "").strip().lower(),
                account_label=str(value.get("account_label") or ""),
                worker_type=str(value.get("worker_type") or ""),
                status=WorkerStatus(value["status"]),
                capabilities=_normalise_capabilities(value.get("capabilities") or []),
                active_job_id=(str(value["active_job_id"]) if value.get("active_job_id") else None),
                last_seen_at=str(value.get("last_seen_at") or ""),
                metadata=dict(value.get("metadata") or {}),
                quota_classes=_normalise_quota_class_state(value.get("quota_classes") or {}),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PersistenceError(f"invalid worker record: {exc}") from exc

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

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Job":
        try:
            return cls(
                job_id=str(value["job_id"]),
                objective=str(value["objective"]),
                department=str(value.get("department") or "general"),
                priority=int(value.get("priority") or 0),
                status=JobStatus(value["status"]),
                assigned_worker_id=(
                    str(value["assigned_worker_id"]) if value.get("assigned_worker_id") else None
                ),
                assigned_quota_class=(
                    str(value["assigned_quota_class"])
                    if value.get("assigned_quota_class")
                    else None
                ),
                authority_level=str(value.get("authority_level") or "A0"),
                branch=(str(value["branch"]) if value.get("branch") else None),
                worktree=(str(value["worktree"]) if value.get("worktree") else None),
                checkpoint=(dict(value["checkpoint"]) if value.get("checkpoint") is not None else None),
                result=(dict(value["result"]) if value.get("result") is not None else None),
                created_at=str(value.get("created_at") or ""),
                updated_at=str(value.get("updated_at") or ""),
                constraints=_normalise_constraints(value.get("constraints") or {}),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PersistenceError(f"invalid job record: {exc}") from exc

    def to_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        value["status"] = self.status.value
        return value


def _normalise_constraints(value: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value or {}, dict):
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
    eligible_quota_classes = sorted(
        {str(item).strip().lower() for item in quota_values if str(item).strip()}
    ) or ["default"]
    result: dict[str, Any] = {}
    if provider:
        result["provider"] = provider
    if capabilities:
        result["required_capabilities"] = capabilities
    result["eligible_quota_classes"] = eligible_quota_classes
    return result


def _normalise_quota_class_state(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Validate persisted per-class capacity without inventing quota measurements."""
    if not isinstance(value, dict) or not value:
        raise PersistenceError("worker quota_classes must be a non-empty mapping")
    result: dict[str, dict[str, Any]] = {}
    for raw_name, raw_state in value.items():
        name = str(raw_name).strip().lower()
        if not name or not isinstance(raw_state, dict):
            raise PersistenceError("each quota class needs a non-empty name and mapping state")
        try:
            status = WorkerStatus(raw_state["status"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PersistenceError(f"invalid quota class status for {name!r}") from exc
        active_job_id = str(raw_state["active_job_id"]) if raw_state.get("active_job_id") else None
        if status == WorkerStatus.AVAILABLE and active_job_id:
            raise PersistenceError(f"available quota class {name!r} cannot hold an active job")
        if status == WorkerStatus.BUSY and not active_job_id:
            raise PersistenceError(f"busy quota class {name!r} must hold an active job")
        result[name] = {
            "status": status.value,
            "capabilities": _normalise_capabilities(raw_state.get("capabilities") or []),
            "active_job_id": active_job_id,
        }
    return result


def _new_quota_classes(
    quota_classes: dict[str, list[str]] | list[str] | tuple[str, ...] | None,
    capabilities: list[str],
    status: WorkerStatus,
) -> dict[str, dict[str, Any]]:
    if quota_classes is None:
        declared: dict[str, list[str]] = {"default": capabilities}
    elif isinstance(quota_classes, dict):
        declared = {}
        for name, values in quota_classes.items():
            if values is not None and not isinstance(values, (list, tuple)):
                raise StateConflict("quota-class capabilities must be lists")
            declared[str(name)] = list(values or [])
    elif isinstance(quota_classes, (list, tuple)):
        declared = {str(name): capabilities for name in quota_classes}
    else:
        raise StateConflict("quota_classes must be a mapping or list of class names")
    if not declared:
        raise StateConflict("at least one quota class is required")
    raw = {
        str(name).strip().lower(): {
            "status": status.value,
            "capabilities": _normalise_capabilities(class_capabilities),
            "active_job_id": None,
        }
        for name, class_capabilities in declared.items()
        if str(name).strip()
    }
    if not raw:
        raise StateConflict("at least one named quota class is required")
    return _normalise_quota_class_state(raw)


def _aggregate_worker(
    worker: Worker,
    quota_classes: dict[str, dict[str, Any]],
    *,
    last_seen_at: str | None = None,
) -> Worker:
    """Refresh compatibility summary fields from authoritative per-class state."""
    quota_classes = _normalise_quota_class_state(quota_classes)
    active_ids = sorted(
        {
            str(item["active_job_id"])
            for item in quota_classes.values()
            if item.get("active_job_id")
        }
    )
    statuses = {WorkerStatus(item["status"]) for item in quota_classes.values()}
    for candidate in (
        WorkerStatus.BUSY,
        WorkerStatus.AVAILABLE,
        WorkerStatus.RATE_LIMITED,
        WorkerStatus.DRAINING,
        WorkerStatus.OFFLINE,
        WorkerStatus.ERROR,
    ):
        if candidate in statuses:
            aggregate_status = candidate
            break
    else:  # pragma: no cover - non-empty validated mapping guarantees a status
        aggregate_status = WorkerStatus.ERROR
    all_capabilities = sorted(
        {
            capability
            for item in quota_classes.values()
            for capability in item.get("capabilities") or []
        }
    )
    return dataclasses.replace(
        worker,
        status=aggregate_status,
        capabilities=all_capabilities,
        active_job_id=active_ids[0] if active_ids else None,
        last_seen_at=last_seen_at or worker.last_seen_at,
        quota_classes=quota_classes,
    )


def _fresh_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "next_job_number": 1,
        "workers": {},
        "jobs": {},
    }


def _validate_state(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise PersistenceError("runtime snapshot has an unknown schema")
    if not isinstance(value.get("workers"), dict) or not isinstance(value.get("jobs"), dict):
        raise PersistenceError("runtime snapshot workers/jobs must be mappings")
    if not isinstance(value.get("next_job_number"), int) or value["next_job_number"] < 1:
        raise PersistenceError("runtime snapshot next_job_number must be a positive integer")

    workers = {worker_id: Worker.from_dict(row) for worker_id, row in value["workers"].items()}
    jobs = {job_id: Job.from_dict(row) for job_id, row in value["jobs"].items()}

    for worker_id, worker in workers.items():
        if worker.worker_id != worker_id:
            raise PersistenceError(f"worker key mismatch for {worker_id!r}")
        aggregate = _aggregate_worker(worker, worker.quota_classes)
        if (
            aggregate.status != worker.status
            or aggregate.active_job_id != worker.active_job_id
            or aggregate.capabilities != worker.capabilities
        ):
            raise PersistenceError(f"worker {worker_id!r} summary does not match quota classes")
        for quota_class, capacity in worker.quota_classes.items():
            active_job_id = capacity.get("active_job_id")
            if active_job_id:
                job = jobs.get(active_job_id)
                if (
                    job is None
                    or job.assigned_worker_id != worker_id
                    or job.assigned_quota_class != quota_class
                    or job.status not in _ACTIVE_JOB_STATUSES
                ):
                    raise PersistenceError(
                        f"worker {worker_id!r} quota class {quota_class!r} has an inconsistent job link"
                    )

    for job_id, job in jobs.items():
        if job.job_id != job_id:
            raise PersistenceError(f"job key mismatch for {job_id!r}")
        if bool(job.assigned_worker_id) != bool(job.assigned_quota_class):
            raise PersistenceError(f"job {job_id!r} must pair worker and quota-class assignments")
        if job.status == JobStatus.QUEUED and job.assigned_worker_id is not None:
            raise PersistenceError(f"queued job {job_id!r} cannot be assigned")
        if job.status in _ACTIVE_JOB_STATUSES:
            worker = workers.get(job.assigned_worker_id or "")
            capacity = worker.quota_classes.get(job.assigned_quota_class or "") if worker else None
            if worker is None or capacity is None or capacity.get("active_job_id") != job_id:
                raise PersistenceError(f"active job {job_id!r} has an inconsistent worker link")
        for payload_name in ("checkpoint", "result"):
            payload = getattr(job, payload_name)
            if payload is not None:
                JobPayload.from_value(payload)
    return value


def _atomic_write(path: Path, payload: bytes) -> None:
    """Durably replace the state file without exposing a partial JSON document."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temp.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


class RuntimeStore:
    """Locked, whole-state persistence for the Phase 1A proof."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root).resolve() if root is not None else _ROOT
        self.path = self.root / _STATE_RELATIVE_PATH

    def _read_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return _fresh_state()
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise PersistenceError(f"runtime snapshot is unreadable: {exc!r}") from exc
        return _validate_state(value)

    def snapshot(self) -> dict[str, Any]:
        """Return a validated snapshot. Atomic replacement makes lock-free reads safe."""
        return self._read_unlocked()

    def update(self, mutation: Callable[[dict[str, Any]], _T]) -> _T:
        """Apply one locked read-modify-write transaction."""
        lock = locks.acquire(_LOCK_NAME, root=self.root)
        if lock is None:
            raise PersistenceError("executive OS runtime state is busy or its lock is unavailable")
        with lock:
            state = self._read_unlocked()
            result = mutation(state)
            _validate_state(state)
            try:
                payload = json.dumps(
                    state,
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                ).encode("utf-8")
                _atomic_write(self.path, payload)
            except RuntimeProofError:
                raise
            except Exception as exc:
                raise PersistenceError(f"runtime snapshot write failed: {exc!r}") from exc
            return result


def _emit_transition(
    store: RuntimeStore,
    *,
    step: str,
    job_id: str = "",
    worker_id: str = "",
    status: str = "ok",
    extra: dict[str, Any] | None = None,
) -> None:
    """Best-effort, bounded telemetry after authoritative state has committed."""
    try:
        from control_plane import run_events

        run_events.append(
            {
                "kind": "executive_os_phase1a",
                "job": job_id or "executive_os_phase1a",
                "step": step,
                "status": status,
                "actor": "operator",
                "extra": {
                    "worker_id": worker_id or None,
                    **(extra or {}),
                },
            },
            root=store.root,
        )
    except Exception:
        pass


def _quota_class_matches(job: Job, worker: Worker, quota_class: str) -> bool:
    provider = str(job.constraints.get("provider") or "").lower()
    if provider and worker.provider != provider:
        return False
    eligible = set(job.constraints.get("eligible_quota_classes") or [])
    if eligible and quota_class not in eligible:
        return False
    capacity = worker.quota_classes.get(quota_class)
    if not capacity or capacity.get("status") != WorkerStatus.AVAILABLE.value:
        return False
    if capacity.get("active_job_id"):
        return False
    required = set(job.constraints.get("required_capabilities") or [])
    return required.issubset(set(capacity.get("capabilities") or []))


def _matching_quota_class(job: Job, worker: Worker) -> str | None:
    return next(
        (
            quota_class
            for quota_class in sorted(worker.quota_classes)
            if _quota_class_matches(job, worker, quota_class)
        ),
        None,
    )


def _assign_in_state(
    state: dict[str, Any],
    job_id: str,
    worker_id: str,
    quota_class: str | None = None,
) -> tuple[Job, Worker]:
    job_row = state["jobs"].get(job_id)
    worker_row = state["workers"].get(worker_id)
    if job_row is None:
        raise StateConflict(f"job {job_id!r} does not exist")
    if worker_row is None:
        raise StateConflict(f"worker {worker_id!r} does not exist")
    job = Job.from_dict(job_row)
    worker = Worker.from_dict(worker_row)
    if job.status != JobStatus.QUEUED:
        raise StateConflict(f"job {job_id} is {job.status.value}, not QUEUED")
    selected_quota_class = (
        str(quota_class).strip().lower()
        if quota_class
        else _matching_quota_class(job, worker)
    )
    if not selected_quota_class or not _quota_class_matches(job, worker, selected_quota_class):
        raise StateConflict(f"worker {worker_id} is unavailable or does not match job constraints")

    ts = _now()
    assigned_job = dataclasses.replace(
        job,
        status=JobStatus.RUNNING,
        assigned_worker_id=worker_id,
        assigned_quota_class=selected_quota_class,
        updated_at=ts,
    )
    quota_classes = {name: dict(capacity) for name, capacity in worker.quota_classes.items()}
    quota_classes[selected_quota_class] = {
        **quota_classes[selected_quota_class],
        "status": WorkerStatus.BUSY.value,
        "active_job_id": job_id,
    }
    busy_worker = _aggregate_worker(worker, quota_classes, last_seen_at=ts)
    state["jobs"][job_id] = assigned_job.to_dict()
    state["workers"][worker_id] = busy_worker.to_dict()
    return assigned_job, busy_worker


def _release_assigned_capacity(
    state: dict[str, Any],
    job: Job,
    *,
    timestamp: str,
) -> Worker | None:
    """Detach one job without changing any sibling quota class."""
    if not job.assigned_worker_id or not job.assigned_quota_class:
        return None
    worker_row = state["workers"].get(job.assigned_worker_id)
    if worker_row is None:
        raise StateConflict(f"job {job.job_id} references a missing worker")
    worker = Worker.from_dict(worker_row)
    capacity = worker.quota_classes.get(job.assigned_quota_class)
    if capacity is None or capacity.get("active_job_id") != job.job_id:
        raise StateConflict(
            f"worker {worker.worker_id} quota class {job.assigned_quota_class} "
            f"is not linked to {job.job_id}"
        )
    quota_classes = {
        name: dict(item) for name, item in worker.quota_classes.items()
    }
    quota_classes[job.assigned_quota_class] = {
        **capacity,
        "status": (
            WorkerStatus.AVAILABLE.value
            if capacity["status"] == WorkerStatus.BUSY.value
            else capacity["status"]
        ),
        "active_job_id": None,
    }
    released = _aggregate_worker(worker, quota_classes, last_seen_at=timestamp)
    state["workers"][worker.worker_id] = released.to_dict()
    return released


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
        quota_classes: dict[str, list[str]] | list[str] | tuple[str, ...] | None = None,
        status: WorkerStatus | str = WorkerStatus.AVAILABLE,
        metadata: dict[str, Any] | None = None,
    ) -> Worker:
        worker_id = str(worker_id).strip()
        if not _WORKER_ID_RE.fullmatch(worker_id):
            raise StateConflict("worker_id must be 1-64 characters using letters, digits, '.', '_' or '-'")
        worker_status = WorkerStatus(_enum_value(status, WorkerStatus))
        if worker_status == WorkerStatus.BUSY:
            raise StateConflict("a worker cannot register BUSY without an assigned job")
        provider = str(provider).strip().lower()
        if not provider:
            raise StateConflict("provider is required")
        if metadata is not None and not isinstance(metadata, dict):
            raise StateConflict("worker metadata must be a mapping")
        normalised_capabilities = _normalise_capabilities(capabilities)
        initial_quota_classes = _new_quota_classes(
            quota_classes,
            normalised_capabilities,
            worker_status,
        )

        def _register(state: dict[str, Any]) -> Worker:
            if worker_id in state["workers"]:
                raise StateConflict(f"worker {worker_id!r} is already registered")
            worker = Worker(
                worker_id=worker_id,
                provider=provider,
                account_label=str(account_label),
                worker_type=str(worker_type),
                status=worker_status,
                capabilities=normalised_capabilities,
                active_job_id=None,
                last_seen_at=_now(),
                metadata=dict(metadata or {}),
                quota_classes=initial_quota_classes,
            )
            worker = _aggregate_worker(worker, initial_quota_classes)
            state["workers"][worker_id] = worker.to_dict()
            return worker

        worker = self.store.update(_register)
        _emit_transition(self.store, step="worker_registered", worker_id=worker_id)
        return worker

    def get_worker(self, worker_id: str) -> Worker | None:
        row = self.store.snapshot()["workers"].get(worker_id)
        return Worker.from_dict(row) if row is not None else None

    def list_workers(self) -> list[Worker]:
        rows = self.store.snapshot()["workers"].values()
        return sorted((Worker.from_dict(row) for row in rows), key=lambda worker: worker.worker_id)

    def set_worker_status(
        self,
        worker_id: str,
        status: WorkerStatus | str,
        *,
        quota_class: str | None = None,
    ) -> Worker:
        new_status = WorkerStatus(_enum_value(status, WorkerStatus))
        selected_quota_class = str(quota_class).strip().lower() if quota_class else None

        def _set(state: dict[str, Any]) -> Worker:
            row = state["workers"].get(worker_id)
            if row is None:
                raise StateConflict(f"worker {worker_id!r} does not exist")
            worker = Worker.from_dict(row)
            quota_classes = {
                name: dict(capacity) for name, capacity in worker.quota_classes.items()
            }
            if selected_quota_class and selected_quota_class not in quota_classes:
                raise StateConflict(
                    f"worker {worker_id!r} has no quota class {selected_quota_class!r}"
                )
            targets = [selected_quota_class] if selected_quota_class else sorted(quota_classes)
            for name in targets:
                capacity = quota_classes[name]
                active_job_id = capacity.get("active_job_id")
                if new_status == WorkerStatus.AVAILABLE and active_job_id:
                    raise StateConflict(
                        f"requeue, complete, or fail {active_job_id} before making {name} AVAILABLE"
                    )
                if new_status == WorkerStatus.BUSY:
                    raise StateConflict("assign a job instead of setting quota-class status BUSY")
                capacity["status"] = new_status.value
                if new_status == WorkerStatus.RATE_LIMITED and active_job_id:
                    job = Job.from_dict(state["jobs"][active_job_id])
                    state["jobs"][job.job_id] = dataclasses.replace(
                        job,
                        status=JobStatus.RATE_LIMITED,
                        updated_at=_now(),
                    ).to_dict()
            updated = _aggregate_worker(worker, quota_classes, last_seen_at=_now())
            state["workers"][worker_id] = updated.to_dict()
            return updated

        worker = self.store.update(_set)
        event_job_id = (
            str(worker.quota_classes[selected_quota_class].get("active_job_id") or "")
            if selected_quota_class
            else ""
        )
        _emit_transition(
            self.store,
            step="worker_status",
            job_id=event_job_id,
            worker_id=worker_id,
            status=new_status.value.lower(),
            extra={
                "worker_status": new_status.value,
                "quota_class": selected_quota_class or "*",
                "active_job_ids": sorted(
                    {
                        str(capacity["active_job_id"])
                        for capacity in worker.quota_classes.values()
                        if capacity.get("active_job_id")
                    }
                ),
            },
        )
        return worker

    def assign_job(
        self,
        worker_id: str,
        job_id: str,
        *,
        quota_class: str | None = None,
    ) -> Worker:
        job, worker = self.store.update(
            lambda state: _assign_in_state(state, job_id, worker_id, quota_class)
        )
        _emit_transition(
            self.store,
            step="job_assigned",
            job_id=job.job_id,
            worker_id=worker.worker_id,
            extra={
                "job_status": job.status.value,
                "quota_class": job.assigned_quota_class,
            },
        )
        return worker

    def release_worker(
        self,
        worker_id: str,
        *,
        quota_class: str | None = None,
    ) -> Worker:
        selected_quota_class = str(quota_class).strip().lower() if quota_class else None

        def _release(state: dict[str, Any]) -> Worker:
            row = state["workers"].get(worker_id)
            if row is None:
                raise StateConflict(f"worker {worker_id!r} does not exist")
            worker = Worker.from_dict(row)
            target = selected_quota_class
            if target is None:
                if len(worker.quota_classes) != 1:
                    raise StateConflict("quota_class is required for a multi-class worker")
                target = next(iter(worker.quota_classes))
            capacity = worker.quota_classes.get(target)
            if capacity is None:
                raise StateConflict(f"worker {worker_id!r} has no quota class {target!r}")
            if capacity.get("active_job_id"):
                raise StateConflict(
                    "release assigned capacity through complete_job, fail_job, or requeue_job"
                )
            quota_classes = {
                name: dict(item) for name, item in worker.quota_classes.items()
            }
            quota_classes[target] = {
                **capacity,
                "status": WorkerStatus.AVAILABLE.value,
                "active_job_id": None,
            }
            released = _aggregate_worker(worker, quota_classes, last_seen_at=_now())
            state["workers"][worker_id] = released.to_dict()
            return released

        worker = self.store.update(_release)
        _emit_transition(
            self.store,
            step="worker_released",
            worker_id=worker_id,
            extra={"quota_class": selected_quota_class or next(iter(worker.quota_classes))},
        )
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
    ) -> Job:
        objective = str(objective).strip()
        if not objective:
            raise StateConflict("objective is required")

        def _create(state: dict[str, Any]) -> Job:
            number = state["next_job_number"]
            job_id = f"JOB-{number:03d}"
            while job_id in state["jobs"]:
                number += 1
                job_id = f"JOB-{number:03d}"
            state["next_job_number"] = number + 1
            ts = _now()
            job = Job(
                job_id=job_id,
                objective=objective,
                department=str(department or "general"),
                priority=int(priority),
                status=JobStatus.QUEUED,
                assigned_worker_id=None,
                assigned_quota_class=None,
                authority_level=str(authority_level or "A0"),
                branch=str(branch) if branch else None,
                worktree=str(worktree) if worktree else None,
                checkpoint=None,
                result=None,
                created_at=ts,
                updated_at=ts,
                constraints=_normalise_constraints(constraints),
            )
            state["jobs"][job_id] = job.to_dict()
            return job

        job = self.store.update(_create)
        _emit_transition(
            self.store,
            step="job_created",
            job_id=job.job_id,
            extra={"job_status": job.status.value},
        )
        return job

    def get_job(self, job_id: str) -> Job | None:
        row = self.store.snapshot()["jobs"].get(job_id)
        return Job.from_dict(row) if row is not None else None

    def list_jobs(self) -> list[Job]:
        rows = self.store.snapshot()["jobs"].values()
        return sorted(
            (Job.from_dict(row) for row in rows),
            key=lambda job: (-job.priority, job.created_at, job.job_id),
        )

    def assign_job(
        self,
        job_id: str,
        worker_id: str,
        *,
        quota_class: str | None = None,
    ) -> Job:
        job, worker = self.store.update(
            lambda state: _assign_in_state(state, job_id, worker_id, quota_class)
        )
        _emit_transition(
            self.store,
            step="job_assigned",
            job_id=job.job_id,
            worker_id=worker.worker_id,
            extra={
                "job_status": job.status.value,
                "quota_class": job.assigned_quota_class,
            },
        )
        return job

    def checkpoint_job(self, job_id: str, payload: JobPayload | dict[str, Any]) -> Job:
        checkpoint = JobPayload.from_value(payload).to_dict()

        def _checkpoint(state: dict[str, Any]) -> Job:
            row = state["jobs"].get(job_id)
            if row is None:
                raise StateConflict(f"job {job_id!r} does not exist")
            job = Job.from_dict(row)
            if job.status not in _ACTIVE_JOB_STATUSES:
                raise StateConflict(f"job {job_id} cannot checkpoint from {job.status.value}")
            next_status = JobStatus.RATE_LIMITED if job.status == JobStatus.RATE_LIMITED else JobStatus.CHECKPOINTED
            updated = dataclasses.replace(
                job,
                status=next_status,
                checkpoint=checkpoint,
                updated_at=_now(),
            )
            state["jobs"][job_id] = updated.to_dict()
            return updated

        job = self.store.update(_checkpoint)
        _emit_transition(
            self.store,
            step="job_checkpointed",
            job_id=job_id,
            worker_id=job.assigned_worker_id or "",
            extra={
                "job_status": job.status.value,
                "quota_class": job.assigned_quota_class,
            },
        )
        return job

    def complete_job(self, job_id: str, payload: JobPayload | dict[str, Any]) -> Job:
        result = JobPayload.from_value(payload).to_dict()

        def _complete(state: dict[str, Any]) -> Job:
            row = state["jobs"].get(job_id)
            if row is None:
                raise StateConflict(f"job {job_id!r} does not exist")
            job = Job.from_dict(row)
            if job.status not in {JobStatus.RUNNING, JobStatus.CHECKPOINTED}:
                raise StateConflict(f"job {job_id} cannot complete from {job.status.value}")
            worker_id = job.assigned_worker_id
            quota_class = job.assigned_quota_class
            if not worker_id or not quota_class or worker_id not in state["workers"]:
                raise StateConflict(f"job {job_id} has no assigned worker")
            ts = _now()
            completed = dataclasses.replace(
                job,
                status=JobStatus.COMPLETED,
                result=result,
                updated_at=ts,
            )
            _release_assigned_capacity(state, job, timestamp=ts)
            state["jobs"][job_id] = completed.to_dict()
            return completed

        job = self.store.update(_complete)
        _emit_transition(
            self.store,
            step="job_completed",
            job_id=job_id,
            worker_id=job.assigned_worker_id or "",
            extra={
                "job_status": job.status.value,
                "quota_class": job.assigned_quota_class,
            },
        )
        return job

    def fail_job(self, job_id: str, payload: JobPayload | dict[str, Any]) -> Job:
        result = JobPayload.from_value(payload).to_dict()

        def _fail(state: dict[str, Any]) -> Job:
            row = state["jobs"].get(job_id)
            if row is None:
                raise StateConflict(f"job {job_id!r} does not exist")
            job = Job.from_dict(row)
            if job.status in {JobStatus.FAILED, JobStatus.COMPLETED, JobStatus.CANCELLED}:
                raise StateConflict(f"job {job_id} cannot fail from {job.status.value}")
            ts = _now()
            failed = dataclasses.replace(job, status=JobStatus.FAILED, result=result, updated_at=ts)
            state["jobs"][job_id] = failed.to_dict()
            _release_assigned_capacity(state, job, timestamp=ts)
            return failed

        job = self.store.update(_fail)
        _emit_transition(
            self.store,
            step="job_failed",
            job_id=job_id,
            worker_id=job.assigned_worker_id or "",
            status="error",
            extra={
                "job_status": job.status.value,
                "quota_class": job.assigned_quota_class,
            },
        )
        return job

    def requeue_job(self, job_id: str) -> Job:
        def _requeue(state: dict[str, Any]) -> tuple[Job, str | None]:
            row = state["jobs"].get(job_id)
            if row is None:
                raise StateConflict(f"job {job_id!r} does not exist")
            job = Job.from_dict(row)
            if job.status not in {
                JobStatus.RUNNING,
                JobStatus.CHECKPOINTED,
                JobStatus.RATE_LIMITED,
                JobStatus.FAILED,
            }:
                raise StateConflict(f"job {job_id} cannot requeue from {job.status.value}")
            ts = _now()
            requeued = dataclasses.replace(
                job,
                status=JobStatus.QUEUED,
                assigned_worker_id=None,
                assigned_quota_class=None,
                result=None,
                updated_at=ts,
            )
            state["jobs"][job_id] = requeued.to_dict()
            if job.status != JobStatus.FAILED:
                _release_assigned_capacity(state, job, timestamp=ts)
            return requeued, job.assigned_quota_class

        job, previous_quota_class = self.store.update(_requeue)
        _emit_transition(
            self.store,
            step="job_requeued",
            job_id=job_id,
            extra={
                "job_status": job.status.value,
                "previous_quota_class": previous_quota_class,
            },
        )
        return job


class ResourceBroker:
    """Deterministic first-match broker for one queued job."""

    def __init__(self, store: RuntimeStore) -> None:
        self.store = store

    def select_worker(self, job: Job | str) -> Worker | None:
        snapshot = self.store.snapshot()
        if isinstance(job, str):
            row = snapshot["jobs"].get(job)
            if row is None:
                raise StateConflict(f"job {job!r} does not exist")
            selected_job = Job.from_dict(row)
        else:
            selected_job = job
        if selected_job.status != JobStatus.QUEUED:
            return None
        workers = sorted(
            (Worker.from_dict(row) for row in snapshot["workers"].values()),
            key=lambda worker: worker.worker_id,
        )
        return next(
            (worker for worker in workers if _matching_quota_class(selected_job, worker)),
            None,
        )

    def dispatch(self, job_id: str) -> Worker | None:
        def _dispatch(state: dict[str, Any]) -> tuple[Job, Worker] | None:
            row = state["jobs"].get(job_id)
            if row is None:
                raise StateConflict(f"job {job_id!r} does not exist")
            job = Job.from_dict(row)
            if job.status != JobStatus.QUEUED:
                raise StateConflict(f"job {job_id} is {job.status.value}, not QUEUED")
            candidates = sorted(
                (Worker.from_dict(item) for item in state["workers"].values()),
                key=lambda worker: worker.worker_id,
            )
            selected = next(
                (
                    (candidate, quota_class)
                    for candidate in candidates
                    if (quota_class := _matching_quota_class(job, candidate)) is not None
                ),
                None,
            )
            if selected is None:
                return None
            worker, quota_class = selected
            return _assign_in_state(state, job_id, worker.worker_id, quota_class)

        result = self.store.update(_dispatch)
        if result is None:
            return None
        job, worker = result
        _emit_transition(
            self.store,
            step="job_dispatched",
            job_id=job_id,
            worker_id=worker.worker_id,
            extra={
                "job_status": job.status.value,
                "quota_class": job.assigned_quota_class,
            },
        )
        return worker


@dataclasses.dataclass(frozen=True)
class Runtime:
    """Convenience bundle used by the CLI and tests."""

    store: RuntimeStore
    workers: WorkerRegistry
    jobs: JobRegistry
    broker: ResourceBroker

    @classmethod
    def at(cls, root: str | Path | None = None) -> "Runtime":
        store = RuntimeStore(root)
        return cls(
            store=store,
            workers=WorkerRegistry(store),
            jobs=JobRegistry(store),
            broker=ResourceBroker(store),
        )
