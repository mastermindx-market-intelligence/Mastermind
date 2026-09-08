"""Durable supervisor for one isolated Executive Codex attempt.

This module is deliberately a narrow composition layer.  The SQLite runtime
owns queue/lease/transition authority, :mod:`control_plane.codex_worker` owns
provider-process mechanics, and this supervisor makes their boundary explicit:

* claim first, then launch exactly one process;
* persist its PID/start/boot identity before marking the attempt RUNNING;
* heartbeat while the process is live;
* validate authority again before accepting a result;
* persist a collection receipt before the terminal database transition; and
* after restart, treat an absent or ambiguous process as LOST, never success.

Importing this module starts no process and creates no scheduler integration.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
import pwd
import signal
import stat
import time
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from uuid import uuid4

from control_plane.codex_worker import (
    ISOLATION_MANIFEST_SCHEMA_VERSION,
    LAUNCH_ATTESTATION_SCHEMA_VERSION,
    ProcessIdentityError,
)
from control_plane.worker_execution_contract import (
    CollectionReceipt,
    ProcessInspector,
    ValidationReceipt,
    WorkerLaunchSpec,
    WorkerProcessRef,
    WorkerRunStatus,
)
from control_plane.worker_adapter import WorkerExecutionAdapter
from control_plane.executive_agent_capabilities import (
    CapabilityPolicyError,
    ExecutionCapabilityRegistry,
)
from control_plane.executive_authority import (
    AuthorityDenied,
    AuthorityPolicyError,
    ExecutiveAuthorityPolicy,
)
from control_plane.executive_runtime import (
    Attempt,
    AttemptLease,
    AttemptStatus,
    Job,
    JobPayload,
    JobStatus,
    OrchestrationDispatchOutcome,
    Runtime,
    RuntimeProofError,
    StateConflict,
)
from control_plane.executive_workspace import (
    AssignmentSealError,
    seal_control_owned_paths,
)


RESULT_SCHEMA_VERSION = "mastermind.executive_worker_result/v1"
_ACTIVE_ATTEMPT_STATUSES = {
    AttemptStatus.CLAIMED,
    AttemptStatus.RUNNING,
    AttemptStatus.CHECKPOINTED,
    AttemptStatus.CANCEL_REQUESTED,
}


class SupervisorError(RuntimeProofError):
    """The supervisor could not safely launch or accept an attempt."""


class TerminalAssignmentSealError(SupervisorError):
    """A worker assignment could not be sealed before terminal state."""


class _ValidationCancelled(Exception):
    """Durable cancellation won while a supervisor validation was running."""


class ReconcileStatus(str, Enum):
    """One restart-reconciliation outcome."""

    EXPIRED_LOST = "EXPIRED_LOST"
    MISSING_LOST = "MISSING_LOST"
    MISSING_CANCELLED = "MISSING_CANCELLED"
    REQUEUED = "REQUEUED"
    LIVE_QUARANTINED = "LIVE_QUARANTINED"
    AWAITING_LEASE_EXPIRY = "AWAITING_LEASE_EXPIRY"
    IDENTITY_AMBIGUOUS = "IDENTITY_AMBIGUOUS"
    OPERATOR_RECOVERED = "OPERATOR_RECOVERED"


class ProcessPresence(str, Enum):
    """PID/start/boot/PGID comparison result for one persisted invocation."""

    LIVE = "LIVE"
    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"


class PersistedProcessController(Protocol):
    """Identity-safe process control seam, injectable in model-free tests."""

    def presence(self, attempt: Attempt) -> ProcessPresence: ...

    def absence_verified(self, attempt: Attempt) -> bool: ...

    def terminate(self, attempt: Attempt) -> None: ...


class IdentitySafeProcessController:
    """Terminate a persisted local process group without trusting a bare PID."""

    def __init__(
        self,
        inspector: ProcessInspector,
        *,
        term_grace_seconds: float = 2.0,
        kill_grace_seconds: float = 5.0,
        poll_seconds: float = 0.05,
    ) -> None:
        self.inspector = inspector
        self.term_grace_seconds = float(term_grace_seconds)
        self.kill_grace_seconds = float(kill_grace_seconds)
        self.poll_seconds = float(poll_seconds)

    def presence(self, attempt: Attempt) -> ProcessPresence:
        if attempt.pid is None or attempt.pgid is None:
            return ProcessPresence.UNKNOWN
        if not attempt.process_start_identity or not attempt.boot_id:
            return ProcessPresence.UNKNOWN
        try:
            if self.inspector.boot_session_id() != attempt.boot_id:
                return ProcessPresence.ABSENT
            identity, pgid = self.inspector.identity(attempt.pid)
        except ProcessIdentityError:
            # ProcessInspector intentionally fails closed when identity cannot be
            # resolved.  Distinguish a truly absent PID from an extant PID whose
            # identity is merely unreadable before authorizing LOST/requeue.
            try:
                os.kill(attempt.pid, 0)
            except ProcessLookupError:
                return ProcessPresence.ABSENT
            except (PermissionError, OSError):
                return ProcessPresence.UNKNOWN
            return ProcessPresence.UNKNOWN
        except Exception:
            return ProcessPresence.UNKNOWN
        if identity != attempt.process_start_identity or pgid != attempt.pgid:
            return ProcessPresence.ABSENT
        return ProcessPresence.LIVE

    def _wait_for_absence(self, attempt: Attempt, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            presence = self.presence(attempt)
            group_presence = self._group_presence(attempt)
            if (
                presence is ProcessPresence.ABSENT
                and group_presence is ProcessPresence.ABSENT
            ):
                return True
            if (
                presence is ProcessPresence.UNKNOWN
                or group_presence is ProcessPresence.UNKNOWN
            ):
                raise SupervisorError(
                    f"process or process-group identity became ambiguous for attempt {attempt.attempt_id}"
                )
            if time.monotonic() >= deadline:
                return False
            time.sleep(self.poll_seconds)

    @staticmethod
    def _group_presence(attempt: Attempt) -> ProcessPresence:
        if attempt.pgid is None:
            return ProcessPresence.UNKNOWN
        try:
            os.killpg(attempt.pgid, 0)
        except ProcessLookupError:
            return ProcessPresence.ABSENT
        except (PermissionError, OSError):
            return ProcessPresence.UNKNOWN
        return ProcessPresence.LIVE

    def absence_verified(self, attempt: Attempt) -> bool:
        return (
            self.presence(attempt) is ProcessPresence.ABSENT
            and self._group_presence(attempt) is ProcessPresence.ABSENT
        )

    def _signal(self, attempt: Attempt, value: signal.Signals) -> bool:
        if self.presence(attempt) is not ProcessPresence.LIVE:
            return False
        assert attempt.pgid is not None
        try:
            os.killpg(attempt.pgid, value)
        except ProcessLookupError:
            return False
        except OSError as exc:
            raise SupervisorError(
                f"could not signal verified process group {attempt.pgid}: {exc}"
            ) from exc
        return True

    def _signal_residual_group(
        self, attempt: Attempt, value: signal.Signals
    ) -> bool:
        """Signal descendants after the verified group leader has exited.

        This is used only inside one termination operation after SIGTERM was
        sent while the full leader boot/start/PGID identity matched.  A live
        group with the original PGID is therefore residual work that must be
        killed before the attempt can be terminalized or requeued.
        """

        if self._group_presence(attempt) is not ProcessPresence.LIVE:
            return False
        assert attempt.pgid is not None
        try:
            os.killpg(attempt.pgid, value)
        except ProcessLookupError:
            return False
        except OSError as exc:
            raise SupervisorError(
                f"could not signal residual process group {attempt.pgid}: {exc}"
            ) from exc
        return True

    def terminate(self, attempt: Attempt) -> None:
        presence = self.presence(attempt)
        if presence is ProcessPresence.ABSENT:
            if self._group_presence(attempt) is ProcessPresence.ABSENT:
                return
            raise SupervisorError(
                f"attempt {attempt.attempt_id} leader exited before its process group"
            )
        if presence is not ProcessPresence.LIVE:
            raise SupervisorError(
                f"attempt {attempt.attempt_id} is not a verified live local process"
            )
        self._signal(attempt, signal.SIGTERM)
        if self._wait_for_absence(attempt, self.term_grace_seconds):
            return
        # Re-resolve the full boot/start/PGID identity immediately before the
        # destructive escalation so PID or process-group reuse is never signalled.
        leader_presence = self.presence(attempt)
        if leader_presence is ProcessPresence.LIVE:
            escalated = self._signal(attempt, signal.SIGKILL)
        elif leader_presence is ProcessPresence.ABSENT:
            escalated = self._signal_residual_group(attempt, signal.SIGKILL)
        else:
            raise SupervisorError(
                f"attempt {attempt.attempt_id} became ambiguous before SIGKILL"
            )
        if not escalated:
            if self._wait_for_absence(attempt, 0):
                return
            raise SupervisorError(
                f"attempt {attempt.attempt_id} could not be verified before SIGKILL"
            )
        if not self._wait_for_absence(attempt, self.kill_grace_seconds):
            raise SupervisorError(
                f"verified process group for attempt {attempt.attempt_id} survived SIGKILL"
            )


@dataclasses.dataclass(frozen=True)
class ActiveRun:
    """In-memory handle for one process whose identity is already durable."""

    lease: AttemptLease = dataclasses.field(repr=False)
    process_ref: WorkerProcessRef
    launch_spec: WorkerLaunchSpec
    effective_grant: Mapping[str, Any] | None = dataclasses.field(
        default=None, repr=False
    )


@dataclasses.dataclass(frozen=True)
class OrchestrationLaunchSpec(WorkerLaunchSpec):
    """LaunchSpec carrying the immutable v4 grant without widening legacy bytes."""

    effective_grant_digest: str = ""


@dataclasses.dataclass(frozen=True)
class SupervisorReceipt:
    job: Job
    attempt: Attempt
    collection: CollectionReceipt
    collection_receipt_path: str
    validations: tuple[ValidationReceipt, ...] = ()
    validation_receipt_path: str | None = None
    assignment_seal_receipt_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job": self.job.to_dict(),
            "attempt": self.attempt.to_dict(),
            "collection": _collection_to_dict(self.collection),
            "collection_receipt_path": self.collection_receipt_path,
            "validations": _jsonable(self.validations),
            "validation_receipt_path": self.validation_receipt_path,
            "assignment_seal_receipt_path": self.assignment_seal_receipt_path,
        }


@dataclasses.dataclass(frozen=True)
class ReconcileReceipt:
    attempt_id: str
    job_id: str
    status: ReconcileStatus
    process_was_live: bool
    requeued: bool = False
    uid_sweep_receipt_path: str | None = None
    assignment_seal_receipt_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        value["status"] = self.status.value
        return value


def worker_result_schema(
    *,
    job_id: str,
    run_id: str,
    worker_id: str,
    effective_grant_digest: str | None = None,
    orchestration_role: str | None = None,
    root_job_id: str | None = None,
) -> dict[str, Any]:
    """Return the strict final-output contract for one immutable attempt."""

    if orchestration_role is not None:
        if effective_grant_digest is None:
            raise SupervisorError("orchestration result schema requires an effective grant")
        from control_plane.executive_orchestration_result import (
            orchestration_result_schema,
        )

        result = orchestration_result_schema(
            orchestration_role,
            job_id=job_id,
            run_id=run_id,
            worker_id=worker_id,
            root_job_id=root_job_id,
        )
        result["x-mastermind-effective-grant-digest"] = effective_grant_digest
        return result

    string_list = {"type": "array", "items": {"type": "string"}}
    result = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "job_id",
            "run_id",
            "worker_id",
            "status",
            "summary",
            "completed_steps",
            "current_state",
            "artifacts",
            "next_actions",
            "errors",
            "validations",
        ],
        "properties": {
            "schema_version": {"type": "string", "const": RESULT_SCHEMA_VERSION},
            "job_id": {"type": "string", "const": job_id},
            "run_id": {"type": "string", "const": run_id},
            "worker_id": {"type": "string", "const": worker_id},
            "status": {"type": "string", "enum": ["COMPLETED", "FAILED"]},
            "summary": {"type": "string"},
            "completed_steps": string_list,
            "current_state": {"type": "string"},
            "artifacts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["path"],
                    "properties": {"path": {"type": "string"}},
                },
            },
            "next_actions": string_list,
            "errors": string_list,
            "validations": {
                "type": "array",
                "maxItems": 0,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["argv", "exit_code"],
                    "properties": {
                        "argv": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string"},
                        },
                        "exit_code": {"type": "integer"},
                    },
                },
            },
        },
    }
    if effective_grant_digest is not None:
        result["x-mastermind-effective-grant-digest"] = effective_grant_digest
    return result


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {field.name: _jsonable(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _collection_to_dict(receipt: CollectionReceipt) -> dict[str, Any]:
    return _jsonable(receipt)


def _write_private_json(path: Path, value: Any) -> None:
    """Create one owner-only, fsynced JSON receipt without overwriting evidence."""

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    payload = (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:  # pragma: no cover - defensive OS boundary
                raise OSError("short write while persisting supervisor receipt")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _payload_from_output(output: Mapping[str, Any]) -> JobPayload:
    artifacts: list[str] = []
    for item in output.get("artifacts", []):
        if isinstance(item, Mapping) and isinstance(item.get("path"), str):
            artifacts.append(str(item["path"]))
    return JobPayload(
        summary=str(output.get("summary") or ""),
        completed_steps=[str(item) for item in output.get("completed_steps", [])],
        current_state=str(output.get("current_state") or ""),
        artifacts=artifacts,
        next_actions=[str(item) for item in output.get("next_actions", [])],
        errors=[str(item) for item in output.get("errors", [])],
    )


def _validate_output_scope(job: Job, output: Mapping[str, Any]) -> None:
    """Reject any model-authored validation claim.

    The supervisor executes every persisted command itself before accepting
    COMPLETED, so worker output must leave the compatibility field empty.
    """

    raw_validations = output.get("validations")
    if not isinstance(raw_validations, (list, tuple)):
        raise SupervisorError("worker result validations must be an array")
    if raw_validations:
        raise SupervisorError(
            "worker result must leave validations=[]; supervisor validation is authoritative"
        )
    if str(output.get("status")) == "COMPLETED" and output.get("errors"):
        raise SupervisorError("completed worker result contains errors")


class ExecutiveSupervisor:
    """Coordinate one durable job with one injected worker execution adapter."""

    def __init__(
        self,
        runtime: Runtime,
        adapter: WorkerExecutionAdapter,
        *,
        runs_root: str | Path | None = None,
        isolation_roots: Sequence[str | Path] = (),
        receipts_root: str | Path | None = None,
        worker_user: str | None = None,
        worker_uid: int | None = None,
        worker_gid: int | None = None,
        shared_run_gid: int | None = None,
        secret_canary_verdict: Mapping[str, Any] | None = None,
        require_complete_launch_attestation: bool = False,
        heartbeat_interval_seconds: float | None = None,
        inspector: ProcessInspector | None = None,
        process_controller: PersistedProcessController | None = None,
        validation_timeout_seconds: float = 300.0,
        instance_id: str | None = None,
    ) -> None:
        self.runtime = runtime
        self.adapter = adapter
        self.runs_root = (
            Path(runs_root).resolve()
            if runs_root is not None
            else runtime.store.root / "data" / "control_plane" / "runs"
        )
        configured_isolation_roots = tuple(Path(value) for value in isolation_roots)
        if any(not value.is_absolute() for value in configured_isolation_roots):
            raise SupervisorError("worker isolation roots must be absolute")
        self.isolation_roots = tuple(
            value.resolve(strict=False) for value in configured_isolation_roots
        )
        self.receipts_root = (
            Path(receipts_root).resolve() if receipts_root is not None else None
        )
        if worker_user is None:
            worker_user = pwd.getpwuid(os.geteuid()).pw_name
        self.worker_user = str(worker_user)
        self.worker_uid = int(worker_uid) if worker_uid is not None else None
        self.worker_gid = int(worker_gid) if worker_gid is not None else None
        self.shared_run_gid = int(shared_run_gid) if shared_run_gid is not None else None
        self.secret_canary_verdict = dict(secret_canary_verdict or {})
        self.require_complete_launch_attestation = bool(
            require_complete_launch_attestation
        )
        default_interval = min(10.0, max(0.1, runtime.store.lease_seconds / 3))
        self.heartbeat_interval_seconds = float(
            default_interval
            if heartbeat_interval_seconds is None
            else heartbeat_interval_seconds
        )
        if self.heartbeat_interval_seconds <= 0:
            raise SupervisorError("heartbeat interval must be positive")
        self.inspector = inspector or adapter.inspector
        self.process_controller = process_controller or IdentitySafeProcessController(
            self.inspector
        )
        self.validation_timeout_seconds = float(validation_timeout_seconds)
        if not 0.1 <= self.validation_timeout_seconds <= 3600:
            raise SupervisorError("validation timeout must be between 0.1 and 3600 seconds")
        self.instance_id = instance_id or f"supervisor-{uuid4().hex}"

    def _job(self, job_id: str) -> Job:
        job = self.runtime.jobs.get_job(job_id)
        if job is None:
            raise SupervisorError(f"job {job_id!r} does not exist")
        return job

    @staticmethod
    def _revalidate_authority(job: Job, attempt: Attempt) -> None:
        try:
            decision = ExecutiveAuthorityPolicy.load().authorize(
                job.requested_authorities,
                worktree=job.worktree,
                allowed_write_paths=job.allowed_write_paths,
                validation_commands=job.validation_commands,
            )
        except (AuthorityDenied, AuthorityPolicyError) as exc:
            raise SupervisorError(f"job authority no longer validates: {exc}") from exc
        if decision.policy_sha256 != attempt.authority_policy_hash:
            raise SupervisorError("authority policy changed after claim; result is rejected")

    @staticmethod
    def _effective_grant(job: Job, attempt: Attempt) -> dict[str, Any] | None:
        """Return the exact orchestration grant, leaving legacy Jobs byte-stable."""

        ExecutiveSupervisor._revalidate_authority(job, attempt)
        if job.orchestration_role is None:
            if attempt.effective_grant is not None or attempt.effective_grant_digest is not None:
                raise SupervisorError("role-null Attempt carries orchestration grant evidence")
            return None
        value = attempt.effective_grant
        keys = {
            "schema_version",
            "authorities",
            "write_paths",
            "validation_argv",
            "policy_sha",
            "job_id",
            "role",
        }
        if (
            not isinstance(value, dict)
            or set(value) != keys
            or value.get("schema_version")
            != "mastermind.executive_effective_grant/v1"
            or value.get("job_id") != job.job_id
            or value.get("role") != job.orchestration_role
            or value.get("policy_sha") != attempt.authority_policy_hash
            or not isinstance(value.get("authorities"), list)
            or not isinstance(value.get("write_paths"), list)
            or not isinstance(value.get("validation_argv"), list)
            or any(item not in job.requested_authorities for item in value["authorities"])
            or any(item not in job.allowed_write_paths for item in value["write_paths"])
            or any(item not in job.validation_commands for item in value["validation_argv"])
        ):
            raise SupervisorError("orchestration Attempt effective grant is malformed or widened")
        digest = hashlib.sha256(
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        if digest != attempt.effective_grant_digest:
            raise SupervisorError("orchestration Attempt effective grant digest drifted")
        return dict(value)

    def _run_dir(self, attempt_id: str) -> Path:
        return self.runs_root / attempt_id

    @staticmethod
    def _isolation_manifest(
        roots: Sequence[Path], *, workspace: Path, run_dir: Path
    ) -> tuple[tuple[Path, ...], Mapping[str, Any], str | None]:
        if not roots:
            return (), {}, None
        def identity(path: Path, info: os.stat_result) -> dict[str, Any]:
            return {
                "path": str(path),
                "device": int(info.st_dev),
                "inode": int(info.st_ino),
                "mode": stat.S_IMODE(info.st_mode),
                "uid": int(info.st_uid),
                "gid": int(info.st_gid),
                "mtime_ns": int(info.st_mtime_ns),
            }

        denied: set[Path] = set()
        assignments = {workspace.resolve(strict=True), run_dir.resolve(strict=True)}
        canonical_roots: list[Path] = []
        root_documents: list[dict[str, Any]] = []
        entry_documents: list[dict[str, Any]] = []
        for lexical in roots:
            info = lexical.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise SupervisorError("worker isolation roots must be real directories")
            canonical = lexical.resolve(strict=True)
            info = canonical.lstat()
            mode = stat.S_IMODE(info.st_mode)
            if info.st_uid != os.geteuid() or mode & 0o022:
                raise SupervisorError(
                    "worker isolation roots must be control-owned and non-worker-writable"
                )
            canonical_roots.append(canonical)
            root_documents.append(identity(canonical, info))
            assigned = {path for path in assignments if path.parent == canonical}
            for path in assignments:
                try:
                    relative = path.relative_to(canonical)
                except ValueError:
                    continue
                if len(relative.parts) != 1:
                    raise SupervisorError(
                        "assigned workspace and run must be direct isolation-root children"
                    )
            try:
                entries = list(os.scandir(canonical))
            except OSError as exc:
                raise SupervisorError("worker isolation root cannot be enumerated") from exc
            observed: set[Path] = set()
            for entry in entries:
                candidate = canonical / entry.name
                try:
                    entry_info = entry.stat(follow_symlinks=False)
                except OSError as exc:
                    raise SupervisorError(
                        "worker isolation-root entry cannot be inspected"
                    ) from exc
                if entry.is_symlink() or not stat.S_ISDIR(entry_info.st_mode):
                    raise SupervisorError(
                        "worker isolation roots may contain only real assignment directories"
                    )
                resolved = candidate.resolve(strict=True)
                observed.add(resolved)
                if resolved == workspace:
                    disposition = "CURRENT_WORKSPACE"
                elif resolved == run_dir:
                    disposition = "CURRENT_RUN"
                else:
                    disposition = "DENY"
                    denied.add(resolved)
                entry_documents.append(
                    {
                        "root_path": str(canonical),
                        "disposition": disposition,
                        "identity": identity(resolved, entry_info),
                    }
                )
            if not assigned.issubset(observed):
                raise SupervisorError(
                    "assigned path disappeared during isolation-root enumeration"
                )
        manifest = {
            "schema_version": ISOLATION_MANIFEST_SCHEMA_VERSION,
            "roots": sorted(root_documents, key=lambda value: str(value["path"])),
            "entries": sorted(
                entry_documents,
                key=lambda value: str(value["identity"]["path"]),
            ),
            "workspace_path": str(workspace.resolve(strict=True)),
            "run_dir": str(run_dir.resolve(strict=True)),
        }
        payload = json.dumps(
            manifest,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        return (
            tuple(sorted(denied, key=str)),
            manifest,
            hashlib.sha256(payload).hexdigest(),
        )

    def _receipt_path(self, attempt_id: str, name: str, *, legacy: Path) -> Path:
        if self.receipts_root is None:
            return legacy
        directory = self.receipts_root / attempt_id
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(directory, 0o700)
        return directory / name

    def _write_schema(
        self,
        run_dir: Path,
        *,
        job: Job,
        attempt: Attempt,
        effective_grant: Mapping[str, Any] | None = None,
    ) -> Path:
        run_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
        os.chmod(run_dir, 0o770 if self.shared_run_gid is not None else 0o700)
        input_dir = run_dir / "input"
        input_dir.mkdir(mode=0o750 if self.shared_run_gid is not None else 0o700)
        schema_path = input_dir / "worker-result.schema.json"
        _write_private_json(
            schema_path,
            worker_result_schema(
                job_id=job.job_id,
                run_id=attempt.attempt_id,
                worker_id=attempt.worker_id,
                effective_grant_digest=(
                    attempt.effective_grant_digest
                    if effective_grant is not None
                    else None
                ),
                orchestration_role=job.orchestration_role,
                root_job_id=(job.root_job_id if job.orchestration_role else None),
            ),
        )
        if self.shared_run_gid is not None:
            for path, mode in (
                (run_dir, 0o770),
                (input_dir, 0o750),
                (schema_path, 0o640),
            ):
                os.chown(path, -1, self.shared_run_gid)
                os.chmod(path, mode)
        return schema_path

    def _prompt(
        self,
        job: Job,
        attempt: Attempt,
        effective_grant: Mapping[str, Any] | None = None,
    ) -> str:
        authorities = (
            list(effective_grant["authorities"])
            if effective_grant is not None
            else job.requested_authorities
        )
        write_paths = (
            list(effective_grant["write_paths"])
            if effective_grant is not None
            else job.allowed_write_paths
        )
        validations = (
            list(effective_grant["validation_argv"])
            if effective_grant is not None
            else job.validation_commands
        )
        packet = {
            "schema_version": "mastermind.executive_job_packet/v1",
            "job_id": job.job_id,
            "run_id": attempt.attempt_id,
            "worker_id": attempt.worker_id,
            "objective": job.objective,
            "department": job.department,
            "authorities": authorities,
            "allowed_write_paths": write_paths,
            "validation_commands": validations,
            "base_sha": job.constraints.get("base_sha"),
            "provider": job.constraints.get("provider"),
            "model": job.constraints.get("model"),
            "effort": job.constraints.get("effort"),
            "cost_class": job.constraints.get("cost_class"),
            "task_kind": job.constraints.get("task_kind"),
            "risk": job.constraints.get("risk"),
            "ambiguity": job.constraints.get("ambiguity"),
            "preferred_model_aliases": job.constraints.get(
                "preferred_model_aliases", []
            ),
            "routing_policy_version": job.constraints.get(
                "routing_policy_version"
            ),
            "execution_profile_id": job.constraints.get("execution_profile_id"),
            "execution_profile_digest": job.constraints.get(
                "execution_profile_digest"
            ),
            "capability_policy_version": job.constraints.get(
                "capability_policy_version"
            ),
            "capability_policy_digest": job.constraints.get(
                "capability_policy_digest"
            ),
            "assigned_quota_class": attempt.quota_class,
            "checkpoint": job.checkpoint,
        }
        if effective_grant is not None:
            packet["effective_grant_digest"] = attempt.effective_grant_digest
            packet["orchestration"] = {
                "role": job.orchestration_role,
                "root_job_id": job.root_job_id,
                "plan_attempt_id": job.plan_attempt_id,
                "plan_digest": job.plan_digest,
                "plan_step_id": job.plan_step_id,
                "repair_round": job.repair_round,
                "supersedes_job_id": job.supersedes_job_id,
                "reviews_job_id": job.reviews_job_id,
                "creation_provenance": job.orchestration_provenance,
            }
            if job.orchestration_role == "aggregation":
                packet["orchestration"]["aggregation_handoff"] = (
                    self.runtime.jobs.get_cycle_handoff(job.job_id)
                )
        return (
            "You are the one-shot Mastermind Executive worker for the JSON job packet below.\n"
            "Treat every authority and path as an exact allow-list. Do not push, open a PR, "
            "merge, deploy, access credentials, call the network, or mutate financial/runtime "
            "state. You may use read-only repository inspection and bounded edit operations "
            "needed to write the declared paths. Do not execute or self-attest validation "
            "commands; set validations=[] exactly. The supervisor will run every persisted "
            "argv directly after your process exits. "
            "Return only one JSON object matching the provided output schema. "
            + (
                "For this orchestration role, only the closed COMPLETED typed envelope is "
                "accepted; process or protocol failure must terminate through the supervisor, "
                "never through invented result fields.\n\n"
                if effective_grant is not None
                else "Use status FAILED and explain errors if the bounded task cannot be completed safely.\n\n"
            )
            + json.dumps(packet, sort_keys=True, ensure_ascii=False, indent=2)
        )

    def _launch_spec(
        self,
        job: Job,
        lease: AttemptLease,
        schema_path: Path,
        effective_grant: Mapping[str, Any] | None = None,
    ) -> WorkerLaunchSpec:
        attempt = lease.attempt
        quota = self.runtime.workers.get_quota_class(attempt.worker_id, attempt.quota_class)
        if quota is None:
            raise SupervisorError("claimed worker quota class disappeared")
        if not job.worktree:
            raise SupervisorError("real worker job requires an assigned isolated worktree")
        model = quota.model or str(job.constraints.get("model") or "gpt-5.6-sol")
        effort = quota.effort or str(job.constraints.get("effort") or "xhigh")
        workspace = Path(job.worktree).resolve(strict=True)
        run_dir = self._run_dir(attempt.attempt_id).resolve(strict=True)
        (
            isolation_denied,
            isolation_manifest,
            isolation_manifest_sha256,
        ) = self._isolation_manifest(
            self.isolation_roots,
            workspace=workspace,
            run_dir=run_dir,
        )
        spec_type = (
            OrchestrationLaunchSpec
            if effective_grant is not None
            else WorkerLaunchSpec
        )
        spec_kwargs: dict[str, Any] = {
            "effective_grant_digest": attempt.effective_grant_digest
        } if effective_grant is not None else {}
        return spec_type(
            run_id=attempt.attempt_id,
            job_id=job.job_id,
            worker_id=attempt.worker_id,
            workspace_path=workspace,
            run_dir=run_dir,
            prompt=self._prompt(job, attempt, effective_grant),
            result_schema_path=schema_path,
            authorities=tuple(
                effective_grant["authorities"]
                if effective_grant is not None
                else job.requested_authorities
            ),
            model=model,
            reasoning_effort=effort,
            worker_user=self.worker_user,
            expected_base_sha=str(job.constraints.get("base_sha") or "") or None,
            allowed_artifact_paths=tuple(
                effective_grant["write_paths"]
                if effective_grant is not None
                else job.allowed_write_paths
            ),
            isolation_roots=self.isolation_roots,
            isolation_denied_paths=isolation_denied,
            isolation_manifest=isolation_manifest,
            isolation_manifest_sha256=isolation_manifest_sha256,
            forbidden_paths=(self.runtime.store.path,),
            expected_worker_uid=self.worker_uid,
            expected_worker_gid=self.worker_gid,
            shared_run_gid=self.shared_run_gid,
            secret_canary_verdict=self.secret_canary_verdict,
            require_secret_canary=self.require_complete_launch_attestation,
            **spec_kwargs,
        )

    def _validate_execution_profile(
        self,
        job: Job,
        lease: AttemptLease,
        effective_grant: Mapping[str, Any] | None = None,
    ) -> None:
        """Bind a routed sealed worker to the exact reviewed capability profile.

        Legacy Jobs without a profile keep their historical path. Newly routed
        stage-2 Jobs cannot cross the provider boundary on metadata alone: the
        installed release policy must still resolve to the same profile/policy
        digests and the claimed capacity must advertise the same identity.
        The current sealed adapter has no MCP/plugin/native-helper surface, so
        any profile requesting one is refused before process launch.
        """

        profile_id = str(job.constraints.get("execution_profile_id") or "")
        if not profile_id:
            return
        quota = self.runtime.workers.get_quota_class(
            lease.attempt.worker_id, lease.attempt.quota_class
        )
        if quota is None:
            raise SupervisorError("claimed worker quota class disappeared")
        metadata = quota.metadata
        keys = (
            "execution_profile_id",
            "execution_profile_digest",
            "capability_policy_version",
            "capability_policy_digest",
        )
        if any(
            str(metadata.get(key) or "").strip().lower()
            != str(job.constraints.get(key) or "").strip().lower()
            for key in keys
        ):
            raise SupervisorError("claimed capacity execution-profile identity drifted")
        try:
            registry = ExecutionCapabilityRegistry.load()
            profile = registry.resolve(profile_id)
        except CapabilityPolicyError as exc:
            raise SupervisorError(f"execution capability policy is invalid: {exc}") from exc
        if (
            registry.policy_version
            != job.constraints.get("capability_policy_version")
            or registry.policy_digest
            != job.constraints.get("capability_policy_digest")
            or profile.profile_digest
            != job.constraints.get("execution_profile_digest")
        ):
            raise SupervisorError("installed execution capability policy drifted")
        if (
            profile.execution_surface != "codex-exec"
            or profile.auth_realm != "dedicated-worker-account"
            or profile.approval_policy != "never"
            or profile.network_policy != "disabled"
            or profile.native_helper_policy.value != "DISABLED"
            or profile.skills
            or profile.mcp_servers
            or profile.plugins
        ):
            raise SupervisorError(
                "sealed worker refuses an execution profile with an unimplemented surface"
            )
        authorities = (
            effective_grant["authorities"]
            if effective_grant is not None
            else job.requested_authorities
        )
        if "WRITE_BRANCH" in authorities and not profile.write_capable:
            raise SupervisorError(
                "read-only execution profile refuses a write-capable Job grant"
            )

    def _launch_metadata(
        self,
        *,
        job: Job,
        lease: AttemptLease,
        spec: WorkerLaunchSpec,
        process_ref: WorkerProcessRef,
        effective_grant: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        quota = self.runtime.workers.get_quota_class(
            lease.attempt.worker_id, lease.attempt.quota_class
        )
        quota_metadata = quota.metadata if quota is not None else {}
        attestation_reader = getattr(self.adapter, "launch_attestation", None)
        if callable(attestation_reader):
            attestation_value = attestation_reader(process_ref)
            attestation = (
                attestation_value.to_dict()
                if hasattr(attestation_value, "to_dict")
                else _jsonable(attestation_value)
            )
        else:
            attestation = {
                "schema_version": "mastermind.executive_launch_attestation/legacy-partial",
                "launch_nonce": process_ref.launch_nonce,
                "observed_base_sha": process_ref.base_sha,
                "binary": _jsonable(process_ref.binary),
                "process_identity": {
                    "pid": process_ref.pid,
                    "pgid": process_ref.pgid,
                    "start_identity": process_ref.process_start_identity,
                    "boot_id": process_ref.boot_session_id,
                },
            }
        if (self.require_complete_launch_attestation or effective_grant is not None) and (
            not isinstance(attestation, dict)
            or attestation.get("schema_version") != LAUNCH_ATTESTATION_SCHEMA_VERSION
        ):
            raise SupervisorError("worker adapter did not provide a complete launch attestation")
        if effective_grant is not None:
            if "effective_grant_digest" in attestation:
                raise SupervisorError("worker launch attestation preempted supervisor grant binding")
            attestation = {
                **attestation,
                "effective_grant_digest": lease.attempt.effective_grant_digest,
            }
        payload = (
            json.dumps(attestation, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            .encode("utf-8")
        )
        receipt_path = self._receipt_path(
            lease.attempt.attempt_id,
            "launch-attestation.json",
            legacy=spec.run_dir / "input" / "launch-attestation.json",
        )
        _write_private_json(receipt_path, attestation)
        result = {
            "schema_version": "mastermind.executive_process_launch/v1",
            "launch_attestation": attestation,
            "launch_attestation_sha256": hashlib.sha256(payload).hexdigest(),
            "launch_attestation_path": str(receipt_path),
            "authority_policy_hash": lease.attempt.authority_policy_hash,
            "authorities": (
                list(effective_grant["authorities"])
                if effective_grant is not None
                else job.requested_authorities
            ),
            "quota_class": lease.attempt.quota_class,
            "routing": {
                "policy_version": job.constraints.get("routing_policy_version"),
                "preferred_model_aliases": job.constraints.get(
                    "preferred_model_aliases", []
                ),
                "selected_model_alias": quota_metadata.get("model_alias"),
                "provider_alias": quota_metadata.get("provider_alias"),
                "adapter_id": quota_metadata.get("adapter_id"),
                "execution_profile_id": job.constraints.get(
                    "execution_profile_id"
                ),
                "execution_profile_digest": job.constraints.get(
                    "execution_profile_digest"
                ),
                "capability_policy_version": job.constraints.get(
                    "capability_policy_version"
                ),
                "capability_policy_digest": job.constraints.get(
                    "capability_policy_digest"
                ),
            },
        }
        if effective_grant is not None:
            result["effective_grant_digest"] = lease.attempt.effective_grant_digest
            result["write_paths"] = list(effective_grant["write_paths"])
            result["validation_argv"] = list(effective_grant["validation_argv"])
        return result

    def _fail_claim(self, lease: AttemptLease, message: str) -> Job:
        return self.runtime.attempts.fail_attempt(
            lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
            payload=JobPayload(
                summary="Executive Codex launch failed",
                current_state="failed before accepted result",
                errors=[message[:3000]],
            ),
        )

    async def start_job(self, job_id: str) -> ActiveRun:
        """Claim and launch one legacy role-null Job."""

        lease = self.runtime.broker.claim(job_id, lease_owner=self.instance_id)
        if lease is None:
            raise SupervisorError(f"no eligible worker capacity for {job_id}")
        return await self._start_claimed_job(job_id, lease)

    async def start_cycle_job(
        self, job_id: str, *, command_id: str
    ) -> ActiveRun | OrchestrationDispatchOutcome:
        """Claim exactly ``job_id`` under ``command_id`` and launch it once.

        Replaying an already active/terminal dispatch returns the immutable
        command-bound outcome.  It never scans or claims another queued Job.
        """

        outcome = self.runtime.attempts.dispatch_cycle_job(
            job_id,
            command_id=command_id,
            lease_owner=self.instance_id,
        )
        if outcome is None:
            raise SupervisorError(f"no eligible worker capacity for {job_id}")
        if outcome.outcome == "TERMINAL" or outcome.attempt.status is not AttemptStatus.CLAIMED:
            return outcome
        if outcome.lease_token is None:  # pragma: no cover - dataclass invariant
            raise SupervisorError("active cycle dispatch lost its lease token")
        return await self._start_claimed_job(
            job_id,
            AttemptLease(
                attempt=outcome.attempt,
                lease_token=outcome.lease_token,
            ),
        )

    async def _start_claimed_job(
        self, job_id: str, lease: AttemptLease
    ) -> ActiveRun:
        """Launch one already claimed exact Job and persist its principal."""

        job = self._job(job_id)
        effective_grant = self._effective_grant(job, lease.attempt)
        process_ref: WorkerProcessRef | None = None
        start_invoked = False
        try:
            self._validate_execution_profile(job, lease, effective_grant)
            schema_path = self._write_schema(
                self._run_dir(lease.attempt.attempt_id),
                job=job,
                attempt=lease.attempt,
                effective_grant=effective_grant,
            )
            spec = self._launch_spec(job, lease, schema_path, effective_grant)
            start_invoked = True
            process_ref = await self.adapter.start(spec)
            launch_metadata = self._launch_metadata(
                job=job,
                lease=lease,
                spec=spec,
                process_ref=process_ref,
                effective_grant=effective_grant,
            )
            self.runtime.attempts.record_process(
                lease.attempt.attempt_id,
                fence_generation=lease.attempt.fence_generation,
                lease_token=lease.lease_token,
                pid=process_ref.pid,
                pgid=process_ref.pgid,
                process_start_identity=process_ref.process_start_identity,
                boot_id=process_ref.boot_session_id,
                provider_session_id=process_ref.provider_session_id,
                stdout_path=process_ref.stdout_path,
                stderr_path=process_ref.stderr_path,
                result_path=process_ref.result_path,
                launch_metadata=launch_metadata,
            )
            self.runtime.attempts.mark_running(
                lease.attempt.attempt_id,
                fence_generation=lease.attempt.fence_generation,
                lease_token=lease.lease_token,
                required_launch_attestation_schema=(
                    LAUNCH_ATTESTATION_SCHEMA_VERSION
                    if self.require_complete_launch_attestation
                    else None
                ),
            )
            # Persist a useful recovery point while the worker is still live.
            # A control-service crash therefore cannot erase the fact that the
            # exact process identity and complete launch attestation crossed
            # the durable RUNNING boundary. The terminal worker checkpoint is
            # a later sequence and may never arrive after a restart/kill.
            self.runtime.attempts.checkpoint_attempt(
                lease.attempt.attempt_id,
                fence_generation=lease.attempt.fence_generation,
                lease_token=lease.lease_token,
                payload=JobPayload(
                    summary="Authorized worker launch accepted",
                    completed_steps=[
                        "process identity and launch attestation persisted"
                    ],
                    current_state="worker process running under supervisor",
                    next_actions=[
                        "collect a schema-valid result or reconcile the attempt as LOST"
                    ],
                ),
            )
            return ActiveRun(
                lease=lease,
                process_ref=process_ref,
                launch_spec=spec,
                effective_grant=effective_grant,
            )
        except Exception as exc:
            if process_ref is not None:
                try:
                    await self.adapter.cancel(process_ref, "supervisor launch persistence failed")
                except Exception as cancel_exc:
                    raise SupervisorError(
                        f"launch failed and process could not be safely cancelled: {cancel_exc}"
                    ) from exc
            unbound_sweep: Mapping[str, Any] | None = None
            if start_invoked and process_ref is None:
                cleanup = getattr(self.adapter, "cleanup_unbound_run", None)
                if callable(cleanup):
                    try:
                        unbound_sweep = await cleanup(lease.attempt.attempt_id)
                        self._validate_terminal_uid_sweep(unbound_sweep)
                    except Exception as cleanup_exc:
                        raise SupervisorError(
                            "ambiguous launch could not prove the unbound run absent"
                        ) from cleanup_exc
            # If the adapter cannot clean an unbound start, retain the active
            # claim.  The service observes that durable state and quarantines;
            # it must never publish a false terminal failure.
            if not start_invoked or process_ref is not None or unbound_sweep is not None:
                try:
                    run_dir = self._run_dir(lease.attempt.attempt_id)
                    if not start_invoked and not run_dir.exists():
                        # Policy/profile rejection can happen before the run
                        # assignment is materialized.  No provider or worker-UID
                        # process crossed the boundary, so there is nothing to
                        # sweep or seal; preserve the original refusal as the
                        # durable terminal reason instead of masking it with a
                        # synthetic missing-run seal failure.
                        self._fail_claim(lease, f"{type(exc).__name__}: {exc}")
                        if isinstance(exc, SupervisorError):
                            raise exc
                        raise SupervisorError(
                            f"Codex launch failed: {type(exc).__name__}: {exc}"
                        ) from exc
                    sweep = (
                        self._active_terminal_uid_sweep(
                            ActiveRun(
                                lease=lease,
                                process_ref=process_ref,
                                launch_spec=spec,
                            )
                        )
                        if process_ref is not None
                        else unbound_sweep
                    )
                    self._seal_terminal_assignment(
                        attempt_id=lease.attempt.attempt_id,
                        job_id=job.job_id,
                        workspace=job.worktree or "",
                        run_dir=run_dir,
                        uid_sweep=sweep,
                        require_uid_sweep=start_invoked,
                    )
                    self._fail_claim(lease, f"{type(exc).__name__}: {exc}")
                except TerminalAssignmentSealError:
                    raise
                except RuntimeProofError:
                    # Preserve the original launch error.  A reconciler will
                    # fence an attempt whose lease changed before cleanup.
                    pass
            if isinstance(exc, SupervisorError):
                raise
            raise SupervisorError(f"Codex launch failed: {type(exc).__name__}: {exc}") from exc

    async def _collect_with_heartbeats(self, active: ActiveRun) -> CollectionReceipt:
        task = asyncio.create_task(self.adapter.collect_result(active.process_ref))
        attempt = active.lease.attempt
        try:
            while True:
                done, _ = await asyncio.wait(
                    {task}, timeout=self.heartbeat_interval_seconds
                )
                if task in done:
                    return task.result()
                job = self._job(attempt.job_id)
                if job.status == JobStatus.CANCEL_REQUESTED:
                    await self.adapter.cancel(active.process_ref, "durable cancellation request")
                    return await task
                self.runtime.attempts.heartbeat_attempt(
                    attempt.attempt_id,
                    fence_generation=attempt.fence_generation,
                    lease_token=active.lease.lease_token,
                )
        except Exception:
            if not task.done():
                try:
                    await self.adapter.cancel(active.process_ref, "supervisor ownership lost")
                finally:
                    await asyncio.gather(task, return_exceptions=True)
            raise

    def _persist_collection(self, active: ActiveRun, receipt: CollectionReceipt) -> Path:
        path = self._receipt_path(
            active.lease.attempt.attempt_id,
            "collection-receipt.json",
            legacy=active.launch_spec.run_dir / "output" / "collection-receipt.json",
        )
        collection = _collection_to_dict(receipt)
        sweep_reader = getattr(self.adapter, "uid_sweep_receipt", None)
        if callable(sweep_reader):
            uid_sweep = _jsonable(sweep_reader(active.process_ref))
            payload: Any = {
                "schema_version": "mastermind.executive_collection_evidence/v1",
                "collection": collection,
                "uid_sweep": uid_sweep,
            }
            if active.effective_grant is not None:
                payload["effective_grant_digest"] = (
                    active.lease.attempt.effective_grant_digest
                )
        else:
            if self.require_complete_launch_attestation:
                raise SupervisorError(
                    "complete remote collection has no dedicated-UID sweep receipt"
                )
            payload = collection
        _write_private_json(path, payload)
        return path

    @staticmethod
    def _read_private_receipt(path: Path, *, name: str) -> dict[str, Any]:
        """Re-read one supervisor receipt through a closed local-file fence."""

        try:
            info = path.lstat()
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_ISLNK(info.st_mode)
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o077
            ):
                raise SupervisorError(f"{name} is not a private control-owned file")
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            raise SupervisorError(f"{name} cannot be revalidated") from exc
        if not isinstance(value, dict):
            raise SupervisorError(f"{name} is not a JSON object")
        return value

    def _orchestration_terminal_payload(
        self,
        *,
        active: ActiveRun,
        job: Job,
        output: Mapping[str, Any],
        collection_path: Path,
        validation_path: Path,
        assignment_path: Path,
    ) -> dict[str, Any]:
        """Build the closed SEALED_WORKER terminal receipt from owned evidence."""

        if active.effective_grant is None or job.orchestration_role is None:
            raise SupervisorError("orchestration terminal receipt requires a typed grant")
        from control_plane.executive_orchestration_result import (
            canonical_digest,
            validate_envelope,
        )

        try:
            json_output = _jsonable(output)
            if not isinstance(json_output, dict):  # pragma: no cover - mapping invariant
                raise SupervisorError("orchestration result did not project to an object")
            envelope = validate_envelope(
                json_output,
                expected_job_id=job.job_id,
                expected_run_id=active.lease.attempt.attempt_id,
                expected_worker_id=active.lease.attempt.worker_id,
                expected_role=job.orchestration_role,
                expected_root_job_id=job.root_job_id,
            )
        except Exception as exc:
            raise SupervisorError(f"orchestration result protocol refused: {exc}") from exc
        collection = self._read_private_receipt(
            collection_path, name="orchestration collection receipt"
        )
        validations = self._read_private_receipt(
            validation_path, name="orchestration validation receipt"
        )
        assignment = self._read_private_receipt(
            assignment_path, name="orchestration assignment seal receipt"
        )
        result = collection.get("collection", {}).get("result")
        if not isinstance(result, dict) or not isinstance(
            result.get("artifact_manifest"), list
        ):
            raise SupervisorError("orchestration collection lost its artifact manifest")
        evidence = {
            "schema_version": "mastermind.sealed_worker_result_evidence/v1",
            "collection_receipt": collection,
            "collection_receipt_digest": canonical_digest(collection),
            "validation_receipts": validations,
            "validation_receipts_digest": canonical_digest(validations),
            "assignment_seal_receipt": assignment,
            "assignment_seal_receipt_digest": canonical_digest(assignment),
        }
        payload: dict[str, Any] = {
            "schema_version": "mastermind.orchestration_terminal_receipt/v1",
            "status": JobStatus.COMPLETED.value,
            "job_id": job.job_id,
            "attempt_id": active.lease.attempt.attempt_id,
            "orchestration_role": job.orchestration_role,
            "execution_mode": "SEALED_WORKER",
            "result_seal_command_id": (
                f"sealed-worker-result:{active.lease.attempt.attempt_id}"
            ),
            "result_evidence": evidence,
            "result_envelope": envelope,
            "result_envelope_digest": canonical_digest(envelope),
            "artifact_receipt_digest": canonical_digest(result["artifact_manifest"]),
            "validation_receipt_digest": evidence["validation_receipts_digest"],
            "effective_grant_digest": active.lease.attempt.effective_grant_digest,
        }
        payload["terminal_evidence_digest"] = canonical_digest(payload)
        return payload

    def _terminal_assignment_receipt_path(self, attempt_id: str) -> Path:
        return self._receipt_path(
            attempt_id,
            "assignment-seal-receipt.json",
            legacy=(
                self.runtime.store.path.parent
                / "assignment-seal-receipts"
                / attempt_id
                / "assignment-seal-receipt.json"
            ),
        )

    @staticmethod
    def _validate_terminal_uid_sweep(value: Any) -> Mapping[str, Any]:
        from control_plane.executive_worker_broker import uid_sweep_receipt_is_passing

        if not uid_sweep_receipt_is_passing(value):
            raise TerminalAssignmentSealError(
                "terminal assignment has no passing final dedicated-UID sweep"
            )
        return value

    def _seal_terminal_assignment(
        self,
        *,
        attempt_id: str,
        job_id: str,
        workspace: str | Path,
        run_dir: str | Path,
        uid_sweep: Mapping[str, Any] | None,
        effective_grant_digest: str | None = None,
        require_uid_sweep: bool | None = None,
    ) -> Path:
        """Persist revocation evidence before any durable terminal transition."""

        sweep_required = (
            self.require_complete_launch_attestation
            if require_uid_sweep is None
            else bool(require_uid_sweep)
        )
        if sweep_required:
            verified_sweep: Mapping[str, Any] | None = self._validate_terminal_uid_sweep(
                uid_sweep
            )
        else:
            verified_sweep = uid_sweep
        try:
            seal = seal_control_owned_paths(
                {"run": run_dir, "workspace": workspace},
                control_uid=os.geteuid(),
            )
        except AssignmentSealError as exc:
            raise TerminalAssignmentSealError(str(exc)) from exc
        payload = {
            **seal,
            "attempt_id": attempt_id,
            "job_id": job_id,
            "uid_sweep": _jsonable(verified_sweep),
        }
        if effective_grant_digest is not None:
            payload["effective_grant_digest"] = effective_grant_digest
        path = self._terminal_assignment_receipt_path(attempt_id)
        try:
            _write_private_json(path, payload)
        except FileExistsError:
            # A control crash can occur after the seal receipt is durable but
            # before SQLite crosses its terminal boundary.  Reconciliation may
            # safely reuse only a private receipt with this exact assignment.
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                info = path.lstat()
            except (OSError, ValueError, TypeError) as exc:
                raise TerminalAssignmentSealError(
                    "existing assignment seal receipt cannot be verified"
                ) from exc
            if (
                not isinstance(existing, dict)
                or existing.get("schema_version")
                != "mastermind.executive_assignment_seal/v1"
                or existing.get("passed") is not True
                or existing.get("attempt_id") != attempt_id
                or existing.get("job_id") != job_id
                or (
                    effective_grant_digest is not None
                    and existing.get("effective_grant_digest")
                    != effective_grant_digest
                )
                or not stat.S_ISREG(info.st_mode)
                or stat.S_ISLNK(info.st_mode)
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o077
            ):
                raise TerminalAssignmentSealError(
                    "existing assignment seal receipt identity drifted"
                )
        except OSError as exc:
            raise TerminalAssignmentSealError(
                "assignment seal receipt could not be persisted"
            ) from exc
        return path

    def _active_terminal_uid_sweep(
        self, active: ActiveRun
    ) -> Mapping[str, Any] | None:
        sweep_reader = getattr(self.adapter, "uid_sweep_receipt", None)
        if not callable(sweep_reader):
            if self.require_complete_launch_attestation:
                raise TerminalAssignmentSealError(
                    "complete terminalization has no dedicated-UID sweep receipt"
                )
            return None
        try:
            value = sweep_reader(active.process_ref)
        except Exception as exc:
            raise TerminalAssignmentSealError(
                "terminal dedicated-UID sweep could not be read"
            ) from exc
        if self.require_complete_launch_attestation:
            return self._validate_terminal_uid_sweep(value)
        return value if isinstance(value, Mapping) else None

    async def _collect_validation_with_heartbeats(
        self,
        active: ActiveRun,
        argv: list[str],
    ) -> ValidationReceipt:
        """Run one exact argv while retaining the same fenced lease ownership."""

        attempt = active.lease.attempt
        task = asyncio.create_task(
            self.adapter.run_validation_argv(
                active.launch_spec,
                tuple(argv),
                timeout_seconds=self.validation_timeout_seconds,
            )
        )
        cancellation_requested = False
        try:
            while True:
                done, _ = await asyncio.wait(
                    {task}, timeout=self.heartbeat_interval_seconds
                )
                if task in done:
                    receipt = task.result()
                    if cancellation_requested:
                        raise _ValidationCancelled
                    return receipt
                job = self._job(attempt.job_id)
                if job.status == JobStatus.CANCEL_REQUESTED:
                    # The direct validation already crossed the broker boundary.
                    # Wait for its bounded timeout/UID sweep instead of dropping
                    # the control request while a worker-UID process may remain.
                    cancellation_requested = True
                self.runtime.attempts.heartbeat_attempt(
                    attempt.attempt_id,
                    fence_generation=attempt.fence_generation,
                    lease_token=active.lease.lease_token,
                )
        except (_ValidationCancelled, StateConflict):
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            raise
        except Exception as exc:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            raise SupervisorError(
                f"supervisor validation could not run: {type(exc).__name__}: {exc}"
            ) from exc

    def _persist_validations(
        self,
        active: ActiveRun,
        receipts: tuple[ValidationReceipt, ...],
    ) -> Path:
        path = self._receipt_path(
            active.lease.attempt.attempt_id,
            "supervisor-validation-receipt.json",
            legacy=(
                active.launch_spec.run_dir
                / "output"
                / "supervisor-validation-receipt.json"
            ),
        )
        payload: dict[str, Any] = {
            "attempt_id": active.lease.attempt.attempt_id,
            "job_id": active.lease.attempt.job_id,
            "commands": _jsonable(receipts),
        }
        if active.effective_grant is not None:
            payload["effective_grant_digest"] = (
                active.lease.attempt.effective_grant_digest
            )
        sweep_reader = getattr(self.adapter, "uid_sweep_receipt", None)
        if callable(sweep_reader):
            payload["uid_sweep"] = _jsonable(sweep_reader(active.process_ref))
        elif self.require_complete_launch_attestation:
            raise SupervisorError(
                "complete remote validation has no dedicated-UID sweep receipt"
            )
        _write_private_json(path, payload)
        return path

    async def _run_supervisor_validations(
        self,
        active: ActiveRun,
        job: Job,
    ) -> tuple[tuple[ValidationReceipt, ...], Path, str | None]:
        receipts: list[ValidationReceipt] = []
        validation_commands = (
            list(active.effective_grant["validation_argv"])
            if active.effective_grant is not None
            else job.validation_commands
        )
        for argv in validation_commands:
            receipt = await self._collect_validation_with_heartbeats(active, argv)
            receipts.append(receipt)
            if (
                receipt.exit_code != 0
                or receipt.timed_out
                or receipt.error is not None
            ):
                break
        persisted = tuple(receipts)
        path = self._persist_validations(active, persisted)
        if len(persisted) != len(validation_commands):
            return (
                persisted,
                path,
                f"supervisor validation sequence stopped early; receipt: {path}",
            )
        failed = next(
            (
                item
                for item in persisted
                if item.exit_code != 0 or item.timed_out or item.error is not None
            ),
            None,
        )
        if failed is not None:
            detail = failed.error or f"exit code {failed.exit_code}"
            return (
                persisted,
                path,
                f"supervisor validation failed for {list(failed.argv)!r}: {detail}; receipt: {path}",
            )
        return persisted, path, None

    async def _terminalize(
        self, active: ActiveRun, receipt: CollectionReceipt, receipt_path: Path
    ) -> tuple[Job, tuple[ValidationReceipt, ...], Path | None, Path]:
        attempt = active.lease.attempt
        fence = attempt.fence_generation
        token = active.lease.lease_token
        seal_path: Path | None = None

        def ensure_sealed() -> Path:
            nonlocal seal_path
            if seal_path is None:
                seal_path = self._seal_terminal_assignment(
                    attempt_id=attempt.attempt_id,
                    job_id=attempt.job_id,
                    workspace=active.launch_spec.workspace_path,
                    run_dir=active.launch_spec.run_dir,
                    uid_sweep=self._active_terminal_uid_sweep(active),
                    effective_grant_digest=(
                        active.lease.attempt.effective_grant_digest
                        if active.effective_grant is not None
                        else None
                    ),
                )
            return seal_path

        if receipt.result.exit_code is None:
            raise SupervisorError("Codex process has no terminal exit code")
        self.runtime.attempts.record_process_exit(
            attempt.attempt_id,
            fence_generation=fence,
            lease_token=token,
            exit_code=receipt.result.exit_code,
            result_path=receipt.process_ref.result_path,
            provider_session_id=receipt.result.provider_session_id,
        )
        job = self._job(attempt.job_id)
        if job.status == JobStatus.CANCEL_REQUESTED:
            ensure_sealed()
            cancelled = self.runtime.attempts.acknowledge_cancel(
                attempt.attempt_id, fence_generation=fence, lease_token=token
            )
            return cancelled, (), None, ensure_sealed()
        output = receipt.result.structured_output
        if receipt.result.status == WorkerRunStatus.SUCCEEDED and isinstance(output, Mapping):
            validation_receipts: tuple[ValidationReceipt, ...] = ()
            validation_path: Path | None = None
            try:
                self._revalidate_authority(job, self.runtime.attempts.get_attempt(attempt.attempt_id) or attempt)
                if job.orchestration_role is None:
                    _validate_output_scope(job, output)
                    payload: JobPayload | dict[str, Any] = _payload_from_output(output)
                else:
                    if str(output.get("status")) != "COMPLETED":
                        raise SupervisorError(
                            "orchestration worker result must use the closed COMPLETED envelope"
                        )
                    payload = {}
                if str(output.get("status")) == "COMPLETED":
                    (
                        validation_receipts,
                        validation_path,
                        validation_error,
                    ) = await self._run_supervisor_validations(active, job)
                    if validation_error is not None:
                        raise SupervisorError(validation_error)
                    # Cancellation can win while the final direct argv is
                    # exiting; honour it before checkpoint/completion.
                    job = self._job(attempt.job_id)
                    if job.status == JobStatus.CANCEL_REQUESTED:
                        ensure_sealed()
                        cancelled = self.runtime.attempts.acknowledge_cancel(
                            attempt.attempt_id,
                            fence_generation=fence,
                            lease_token=token,
                        )
                        return (
                            cancelled,
                            validation_receipts,
                            validation_path,
                            ensure_sealed(),
                        )
                if job.orchestration_role is None:
                    self.runtime.attempts.checkpoint_attempt(
                        attempt.attempt_id,
                        fence_generation=fence,
                        lease_token=token,
                        payload=payload,
                    )
                if str(output.get("status")) == "COMPLETED":
                    assignment_path = ensure_sealed()
                    if job.orchestration_role is not None:
                        if validation_path is None:  # pragma: no cover - helper invariant
                            raise SupervisorError(
                                "orchestration completion lost its validation receipt"
                            )
                        payload = self._orchestration_terminal_payload(
                            active=active,
                            job=job,
                            output=output,
                            collection_path=receipt_path,
                            validation_path=validation_path,
                            assignment_path=assignment_path,
                        )
                    completed = self.runtime.attempts.complete_attempt(
                        attempt.attempt_id,
                        fence_generation=fence,
                        lease_token=token,
                        payload=payload,
                    )
                    return completed, validation_receipts, validation_path, ensure_sealed()
                ensure_sealed()
                failed = self.runtime.attempts.fail_attempt(
                    attempt.attempt_id,
                    fence_generation=fence,
                    lease_token=token,
                    payload=payload,
                )
                return failed, validation_receipts, validation_path, ensure_sealed()
            except _ValidationCancelled:
                ensure_sealed()
                cancelled = self.runtime.attempts.acknowledge_cancel(
                    attempt.attempt_id,
                    fence_generation=fence,
                    lease_token=token,
                )
                return cancelled, validation_receipts, validation_path, ensure_sealed()
            except TerminalAssignmentSealError:
                raise
            except StateConflict:
                # A concurrent cancel is the only stale-state transition this
                # owner may acknowledge.  Fence/adoption/expiry races must
                # propagate instead of being converted with a stale token.
                current = self._job(attempt.job_id)
                if current.status == JobStatus.CANCEL_REQUESTED:
                    ensure_sealed()
                    cancelled = self.runtime.attempts.acknowledge_cancel(
                        attempt.attempt_id,
                        fence_generation=fence,
                        lease_token=token,
                    )
                    return (
                        cancelled,
                        validation_receipts,
                        validation_path,
                        ensure_sealed(),
                    )
                raise
            except SupervisorError as exc:
                current = self._job(attempt.job_id)
                if current.status == JobStatus.CANCEL_REQUESTED:
                    ensure_sealed()
                    cancelled = self.runtime.attempts.acknowledge_cancel(
                        attempt.attempt_id,
                        fence_generation=fence,
                        lease_token=token,
                    )
                    return (
                        cancelled,
                        validation_receipts,
                        validation_path,
                        ensure_sealed(),
                    )
                try:
                    ensure_sealed()
                    failed = self.runtime.attempts.fail_attempt(
                        attempt.attempt_id,
                        fence_generation=fence,
                        lease_token=token,
                        payload=JobPayload(
                            summary="Worker result rejected",
                            current_state=f"collection receipt: {receipt_path}",
                            errors=[str(exc)],
                        ),
                    )
                except StateConflict:
                    current = self._job(attempt.job_id)
                    if current.status != JobStatus.CANCEL_REQUESTED:
                        raise
                    ensure_sealed()
                    failed = self.runtime.attempts.acknowledge_cancel(
                        attempt.attempt_id,
                        fence_generation=fence,
                        lease_token=token,
                    )
                return failed, validation_receipts, validation_path, ensure_sealed()
        ensure_sealed()
        failed = self.runtime.attempts.fail_attempt(
            attempt.attempt_id,
            fence_generation=fence,
            lease_token=token,
            payload=JobPayload(
                summary="Codex worker did not return an accepted result",
                current_state=f"collection receipt: {receipt_path}",
                errors=[receipt.result.error or receipt.result.status.value],
            ),
        )
        return failed, (), None, ensure_sealed()

    async def finish_job(self, active: ActiveRun) -> SupervisorReceipt:
        receipt = await self._collect_with_heartbeats(active)
        receipt_path = self._persist_collection(active, receipt)
        job, validations, validation_path, seal_path = await self._terminalize(
            active, receipt, receipt_path
        )
        attempt = self.runtime.attempts.get_attempt(active.lease.attempt.attempt_id)
        if attempt is None:  # pragma: no cover - FK and transaction invariants
            raise SupervisorError("terminal attempt disappeared")
        return SupervisorReceipt(
            job=job,
            attempt=attempt,
            collection=receipt,
            collection_receipt_path=str(receipt_path),
            validations=validations,
            validation_receipt_path=(
                str(validation_path) if validation_path is not None else None
            ),
            assignment_seal_receipt_path=str(seal_path),
        )

    async def run_once(self, job_id: str) -> SupervisorReceipt:
        """Claim, execute, validate, and terminalize exactly one queued job."""

        return await self.finish_job(await self.start_job(job_id))

    async def run_cycle_once(
        self, job_id: str, *, command_id: str
    ) -> SupervisorReceipt | OrchestrationDispatchOutcome:
        """Execute one command-bound orchestration Job without fleet fallback."""

        started = await self.start_cycle_job(job_id, command_id=command_id)
        if isinstance(started, OrchestrationDispatchOutcome):
            return started
        return await self.finish_job(started)

    def _maybe_requeue(self, job_id: str) -> bool:
        job = self._job(job_id)
        if job.status != JobStatus.LOST or job.attempt_count >= job.attempt_limit:
            return False
        if self.require_complete_launch_attestation:
            # A complete terminal attempt has a sealed workspace.  Only the
            # service's explicit requeue path may archive it and prepare a fresh
            # worker-accessible assignment before returning the Job to QUEUED.
            return False
        self.runtime.jobs.requeue_job(job_id)
        return True

    def _persist_reconciliation_evidence(
        self,
        outcome: ReconcileReceipt,
        *,
        uid_sweep: Mapping[str, Any] | None,
    ) -> ReconcileReceipt:
        if uid_sweep is None:
            return outcome
        path = self._receipt_path(
            outcome.attempt_id,
            "reconciliation-receipt.json",
            legacy=(
                self.runtime.store.path.parent
                / "reconciliation-receipts"
                / outcome.attempt_id
                / "reconciliation-receipt.json"
            ),
        )
        _write_private_json(
            path,
            {
                "schema_version": "mastermind.executive_reconciliation_evidence/v1",
                "outcome": outcome.to_dict(),
                "uid_sweep": _jsonable(uid_sweep),
            },
        )
        return dataclasses.replace(outcome, uid_sweep_receipt_path=str(path))

    def _restart_uid_sweep(self, attempt: Attempt) -> Mapping[str, Any] | None:
        sweep_reader = getattr(self.process_controller, "uid_sweep_receipt", None)
        if not callable(sweep_reader):
            if self.require_complete_launch_attestation:
                raise SupervisorError(
                    "complete restart reconciliation has no dedicated-UID sweep receipt"
                )
            return None
        try:
            sweep = sweep_reader(attempt)
        except Exception as exc:
            if self.require_complete_launch_attestation:
                raise SupervisorError(
                    "complete restart reconciliation could not obtain a dedicated-UID sweep"
                ) from exc
            return None
        from control_plane.executive_worker_broker import uid_sweep_receipt_is_passing

        if not uid_sweep_receipt_is_passing(sweep):
            raise SupervisorError(
                "restart reconciliation received a non-passing dedicated-UID sweep"
            )
        return sweep

    def reconcile_restart(self, *, requeue_lost: bool = True) -> list[ReconcileReceipt]:
        """Inspect durable nonterminal attempts after a supervisor restart.

        A live local child cannot be reconstructed because the in-memory JSONL
        parser was lost.  It is identity-safely terminated and verified absent
        before any fence rotation, cancellation acknowledgement, LOST state, or
        requeue.  Ambiguous and provider-only identities remain quarantined.
        """

        outcomes: list[ReconcileReceipt] = []
        for attempt in self.runtime.attempts.list_attempts():
            if attempt.status not in _ACTIVE_ATTEMPT_STATUSES:
                continue
            if attempt.execution_mode == "OPERATOR_HARNESS":
                # Rich-session generations have their own writer/epoch law;
                # sealed-worker LOST reconciliation must never fence them.
                continue
            presence = self.process_controller.presence(attempt)
            process_was_live = presence is ProcessPresence.LIVE
            uid_sweep: Mapping[str, Any] | None = None
            if process_was_live:
                self.process_controller.terminate(attempt)
                if not self.process_controller.absence_verified(attempt):
                    raise SupervisorError(
                        f"attempt {attempt.attempt_id} remained live or ambiguous after termination"
                    )
                presence = ProcessPresence.ABSENT
            if presence is ProcessPresence.ABSENT:
                if not self.process_controller.absence_verified(attempt):
                    presence = ProcessPresence.UNKNOWN
                else:
                    # This must be fresh for an initially absent process too;
                    # otherwise a broker-restart race can rotate the fence on
                    # the strength of an old startup observation.
                    uid_sweep = self._restart_uid_sweep(attempt)
            if presence is ProcessPresence.UNKNOWN:
                outcomes.append(
                    ReconcileReceipt(
                        attempt_id=attempt.attempt_id,
                        job_id=attempt.job_id,
                        status=ReconcileStatus.IDENTITY_AMBIGUOUS,
                        process_was_live=process_was_live,
                    )
                )
                continue

            # Reload after OS inspection.  A concurrent terminal mutation wins;
            # never infer or overwrite it from the stale pre-inspection row.
            current = self.runtime.attempts.get_attempt(attempt.attempt_id)
            if current is None or current.status not in _ACTIVE_ATTEMPT_STATUSES:
                continue
            job_before_terminal = self._job(current.job_id)
            if not job_before_terminal.worktree:
                raise TerminalAssignmentSealError(
                    "persisted worker attempt has no assigned workspace to seal"
                )
            seal_path = self._seal_terminal_assignment(
                attempt_id=current.attempt_id,
                job_id=current.job_id,
                workspace=job_before_terminal.worktree,
                run_dir=self._run_dir(current.attempt_id),
                uid_sweep=uid_sweep,
            )
            expired = self.runtime.attempts.reconcile_expired(
                attempt_id=current.attempt_id
            )
            if expired:
                expired_attempt = expired[0]
                job = self._job(expired_attempt.job_id)
                requeued = requeue_lost and self._maybe_requeue(job.job_id)
                cancelled = job.status == JobStatus.CANCELLED
                outcomes.append(
                    self._persist_reconciliation_evidence(
                        ReconcileReceipt(
                            attempt_id=expired_attempt.attempt_id,
                            job_id=expired_attempt.job_id,
                            status=(
                                ReconcileStatus.MISSING_CANCELLED
                                if cancelled
                                else (
                                    ReconcileStatus.REQUEUED
                                    if requeued
                                    else ReconcileStatus.EXPIRED_LOST
                                )
                            ),
                            process_was_live=process_was_live,
                            requeued=requeued,
                            assignment_seal_receipt_path=str(seal_path),
                        ),
                        uid_sweep=uid_sweep,
                    )
                )
                continue
            current = self.runtime.attempts.get_attempt(attempt.attempt_id)
            if current is None or current.status not in _ACTIVE_ATTEMPT_STATUSES:
                continue

            if current.pid is None and current.provider_session_id is None:
                outcomes.append(
                    self._persist_reconciliation_evidence(
                        ReconcileReceipt(
                            attempt_id=current.attempt_id,
                            job_id=current.job_id,
                            status=ReconcileStatus.AWAITING_LEASE_EXPIRY,
                            process_was_live=process_was_live,
                            assignment_seal_receipt_path=str(seal_path),
                        ),
                        uid_sweep=uid_sweep,
                    )
                )
                continue
            try:
                adopted = self.runtime.attempts.adopt_attempt(
                    current.attempt_id,
                    expected_fence_generation=current.fence_generation,
                    lease_owner=self.instance_id,
                )
                if current.status == AttemptStatus.CANCEL_REQUESTED:
                    self.runtime.attempts.acknowledge_cancel(
                        current.attempt_id,
                        fence_generation=adopted.attempt.fence_generation,
                        lease_token=adopted.lease_token,
                    )
                    status = ReconcileStatus.MISSING_CANCELLED
                    requeued = False
                else:
                    self.runtime.attempts.mark_lost(
                        current.attempt_id,
                        fence_generation=adopted.attempt.fence_generation,
                        lease_token=adopted.lease_token,
                        reason="process identity absent during supervisor restart",
                        verified_process_absent=True,
                    )
                    requeued = requeue_lost and self._maybe_requeue(current.job_id)
                    status = ReconcileStatus.REQUEUED if requeued else ReconcileStatus.MISSING_LOST
            except StateConflict:
                # Lease expiry or another reconciler may win after inspection.
                # Only reconcile the process identity already proven absent.
                newly_expired = self.runtime.attempts.reconcile_expired(
                    attempt_id=current.attempt_id
                )
                if not newly_expired:
                    raise
                requeued = requeue_lost and self._maybe_requeue(current.job_id)
                status = ReconcileStatus.REQUEUED if requeued else ReconcileStatus.EXPIRED_LOST
            outcomes.append(
                self._persist_reconciliation_evidence(
                    ReconcileReceipt(
                        attempt_id=current.attempt_id,
                        job_id=current.job_id,
                        status=status,
                        process_was_live=process_was_live,
                        requeued=requeued,
                        assignment_seal_receipt_path=str(seal_path),
                    ),
                    uid_sweep=uid_sweep,
                )
            )
        return outcomes


__all__ = [
    "ActiveRun",
    "ExecutiveSupervisor",
    "IdentitySafeProcessController",
    "PersistedProcessController",
    "ProcessPresence",
    "ReconcileReceipt",
    "ReconcileStatus",
    "RESULT_SCHEMA_VERSION",
    "SupervisorError",
    "SupervisorReceipt",
    "worker_result_schema",
]
