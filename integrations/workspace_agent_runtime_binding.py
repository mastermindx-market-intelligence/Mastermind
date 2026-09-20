"""Stateless current-target resolver for Workspace Agent candidate return.

The signed Workspace return reference carries only one host-minted Executive
operation key and a one-way DialogueBinding digest.  This adapter reconstructs
that binding from existing canonical owners at call time:

* Executive Runtime owns the current Job / Attempt / Worker identity.
* immutable root admission owns work_ref / commission_ref / watch_mode.
* persisted Wake evidence owns the exact physical Agent Dialogue thread.

No Workspace-specific target registry, lifecycle table, replay controller, cursor,
or durable mapping is introduced.  A meaningful target change between the two
Runtime reads refuses the return before Agent Dialogue transport is attempted.
"""
from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable
from typing import Any

from control_plane.executive_delegation_identity import derive_delegation_identity
from control_plane.executive_runtime import (
    AttemptStatus,
    ExecutiveDialogueSource,
    JobStatus,
    WorkerStatus,
    _dialogue_source_from_root_creation,
)
from control_plane.wake_ledger import (
    LedgerPhase,
    WAKE_AGGREGATE_TYPE,
    wake_record_from_event,
)
from control_plane.dialogue_source_resolution import PhysicalDialogueSourceIdentity
from integrations.mastermind_company_mcp.adapter import DialogueBinding
from integrations.workspace_agent_return import WorkspaceReturnError

_OPERATION_KEY = re.compile(r"\Aexec-(job-[0-9]{3,})\Z")
_ALLOWED_MESSAGE_TYPES = ("RESULT",)


@dataclasses.dataclass(frozen=True, slots=True)
class WorkspaceReturnTargetEpoch:
    root_job_id: str
    job_id: str
    session_ref: str
    attempt_id: str
    worker_id: str
    job_status: JobStatus
    attempt_status: AttemptStatus
    fence_generation: int
    worker_status: WorkerStatus


TargetReader = Callable[[str], WorkspaceReturnTargetEpoch]
DialogueSourceReader = Callable[[str], ExecutiveDialogueSource]
@dataclasses.dataclass(frozen=True, slots=True)
class WorkspaceReturnPhysicalSource:
    identity: PhysicalDialogueSourceIdentity
    source_workstream: str


PhysicalSourceReader = Callable[
    [str, str, str], WorkspaceReturnPhysicalSource
]


def _refuse() -> None:
    raise WorkspaceReturnError("BINDING_UNAVAILABLE")


def _job_id_from_operation_key(operation_key: object) -> str:
    if type(operation_key) is not str:
        _refuse()
    match = _OPERATION_KEY.fullmatch(operation_key)
    if match is None:
        _refuse()
    return match.group(1).upper()


def _read_current_target(runtime: Any, operation_key: str) -> WorkspaceReturnTargetEpoch:
    """Read one current Executive target through public Runtime registries."""

    try:
        job_id = _job_id_from_operation_key(operation_key)
        job = runtime.jobs.get_job(job_id)
        if job is None:
            _refuse()
        identity = derive_delegation_identity(job)
        if (
            identity.operation_key != operation_key
            or identity.job_id != job_id
            or job.status not in {JobStatus.RUNNING, JobStatus.CHECKPOINTED}
            or not job.current_attempt_id
        ):
            _refuse()
        attempt = runtime.attempts.get_attempt(job.current_attempt_id)
        if (
            attempt is None
            or attempt.job_id != job_id
            or attempt.status
            not in {
                AttemptStatus.CLAIMED,
                AttemptStatus.RUNNING,
                AttemptStatus.CHECKPOINTED,
            }
            or not attempt.worker_id
            or job.assigned_worker_id != attempt.worker_id
        ):
            _refuse()
        worker = runtime.workers.get_worker(attempt.worker_id)
        if (
            worker is None
            or worker.status is not WorkerStatus.BUSY
            or worker.active_job_id != job_id
        ):
            _refuse()
        return WorkspaceReturnTargetEpoch(
            root_job_id=identity.root_job_id,
            job_id=job_id,
            session_ref=identity.session_ref,
            attempt_id=attempt.attempt_id,
            worker_id=attempt.worker_id,
            job_status=job.status,
            attempt_status=attempt.status,
            fence_generation=attempt.fence_generation,
            worker_status=worker.status,
        )
    except WorkspaceReturnError:
        raise
    except Exception:
        _refuse()


def _read_dialogue_source(runtime: Any, root_job_id: str) -> ExecutiveDialogueSource:
    """Re-use Executive's immutable root-source verifier; do not copy its law."""

    try:
        with runtime.store.read() as connection:
            source = _dialogue_source_from_root_creation(
                connection,
                root_job_id=root_job_id,
            )
    except Exception:
        _refuse()
    if type(source) is not ExecutiveDialogueSource:
        _refuse()
    return source


def _read_physical_source(
    runtime: Any,
    operation_key: str,
    job_id: str,
    attempt_id: str,
) -> WorkspaceReturnPhysicalSource:
    """Read the unique physical dialogue thread already owned by Wake.

    Multiple attention events and both supervisor seats may legitimately point
    at one thread.  A second distinct thread identity for the same current
    Executive Attempt is ambiguous and therefore refuses instead of choosing
    "latest".
    """

    try:
        with runtime.store.read() as connection:
            identities = connection.execute(
                """
                SELECT DISTINCT
                    json_extract(payload_json,'$.physical_source.workspace_id'),
                    json_extract(payload_json,'$.physical_source.channel_id'),
                    json_extract(payload_json,'$.physical_source.thread_ts'),
                    json_extract(payload_json,'$.physical_source.parent_fingerprint')
                FROM events
                WHERE aggregate_type=?
                  AND event_type=?
                  AND job_id=?
                  AND attempt_id=?
                  AND json_type(payload_json,'$.physical_source')='object'
                  AND json_extract(
                    payload_json,'$.physical_source.operation_key'
                  )=?
                ORDER BY 1,2,3,4
                LIMIT 2
                """,
                (
                    WAKE_AGGREGATE_TYPE,
                    LedgerPhase.WAKE_REQUESTED.value,
                    job_id,
                    attempt_id,
                    operation_key,
                ),
            ).fetchall()
            if len(identities) != 1:
                _refuse()
            workspace_id, channel_id, thread_ts, parent_fingerprint = tuple(
                identities[0]
            )
            command = connection.execute(
                """
                SELECT command_id
                FROM events
                WHERE aggregate_type=?
                  AND event_type=?
                  AND job_id=?
                  AND attempt_id=?
                  AND json_type(payload_json,'$.physical_source')='object'
                  AND json_extract(
                    payload_json,'$.physical_source.operation_key'
                  )=?
                  AND json_extract(
                    payload_json,'$.physical_source.workspace_id'
                  )=?
                  AND json_extract(
                    payload_json,'$.physical_source.channel_id'
                  )=?
                  AND json_extract(
                    payload_json,'$.physical_source.thread_ts'
                  )=?
                  AND json_extract(
                    payload_json,'$.physical_source.parent_fingerprint'
                  )=?
                ORDER BY event_id DESC
                LIMIT 1
                """,
                (
                    WAKE_AGGREGATE_TYPE,
                    LedgerPhase.WAKE_REQUESTED.value,
                    job_id,
                    attempt_id,
                    operation_key,
                    workspace_id,
                    channel_id,
                    thread_ts,
                    parent_fingerprint,
                ),
            ).fetchone()
            if command is None:
                _refuse()
            event = runtime.store.get_event_by_command_id(
                str(command[0]),
                connection=connection,
            )
            if event is None:
                _refuse()
            record = wake_record_from_event(event)
    except WorkspaceReturnError:
        raise
    except Exception:
        _refuse()

    physical = record.physical_source
    obligation = record.obligation
    if (
        type(physical) is not PhysicalDialogueSourceIdentity
        or obligation is None
        or physical.operation_key != operation_key
        or physical.workspace_id != workspace_id
        or physical.channel_id != channel_id
        or physical.thread_ts != thread_ts
        or physical.parent_fingerprint != parent_fingerprint
        or physical.candidate.job_id != job_id
        or physical.candidate.attempt_id != attempt_id
        or obligation.job_id != job_id
        or obligation.attempt_id != attempt_id
    ):
        _refuse()
    source_workstream = getattr(obligation, "source_workstream", None)
    if type(source_workstream) is not str or not source_workstream:
        _refuse()
    return WorkspaceReturnPhysicalSource(
        identity=physical,
        source_workstream=source_workstream,
    )


class ExecutiveWorkspaceReturnBindingResolver:
    """Reconstruct one exact current DialogueBinding without new durable state."""

    def __init__(
        self,
        runtime: Any,
        *,
        target_reader: TargetReader | None = None,
        dialogue_source_reader: DialogueSourceReader | None = None,
        physical_source_reader: PhysicalSourceReader | None = None,
    ) -> None:
        if runtime is None:
            raise TypeError("runtime is required")
        self._runtime = runtime
        self._target_reader = target_reader or (
            lambda operation_key: _read_current_target(runtime, operation_key)
        )
        self._dialogue_source_reader = dialogue_source_reader or (
            lambda root_job_id: _read_dialogue_source(runtime, root_job_id)
        )
        self._physical_source_reader = physical_source_reader or (
            lambda operation_key, job_id, attempt_id: _read_physical_source(
                runtime,
                operation_key,
                job_id,
                attempt_id,
            )
        )

    def resolve(self, operation_key: str) -> DialogueBinding:
        expected_job_id = _job_id_from_operation_key(operation_key)
        first = self._target_reader(operation_key)
        if (
            type(first) is not WorkspaceReturnTargetEpoch
            or first.job_id != expected_job_id
        ):
            _refuse()

        try:
            source = self._dialogue_source_reader(first.root_job_id)
            physical_source = self._physical_source_reader(
                operation_key,
                first.job_id,
                first.attempt_id,
            )
        except WorkspaceReturnError:
            raise
        except Exception:
            _refuse()

        if (
            type(source) is not ExecutiveDialogueSource
            or type(physical_source) is not WorkspaceReturnPhysicalSource
            or physical_source.source_workstream != source.work_ref
            or type(physical_source.identity) is not PhysicalDialogueSourceIdentity
            or physical_source.identity.operation_key != operation_key
            or physical_source.identity.candidate.root_job_id != first.root_job_id
            or physical_source.identity.candidate.job_id != first.job_id
            or physical_source.identity.candidate.attempt_id != first.attempt_id
            or physical_source.identity.candidate.worker_id != first.worker_id
        ):
            _refuse()

        second = self._target_reader(operation_key)
        if type(second) is not WorkspaceReturnTargetEpoch or second != first:
            _refuse()

        actor_ref = {
            "kind": "worker_attempt",
            "job_id": second.job_id,
            "attempt_id": second.attempt_id,
            "worker_id": second.worker_id,
        }
        applies_to = {
            "kind": "executive_attempt",
            "job_id": second.job_id,
            "attempt_id": second.attempt_id,
            "worker_id": second.worker_id,
        }
        try:
            return DialogueBinding(
                actor_ref=actor_ref,
                work_ref=source.work_ref,
                commission_ref=source.commission_ref.to_dict(),
                session_ref=second.session_ref,
                operation_key=operation_key,
                watch_mode=source.watch_mode,
                applies_to=applies_to,
                thread_ts=physical_source.identity.thread_ts,
                allowed_message_types=_ALLOWED_MESSAGE_TYPES,
                reply_to_message_key=None,
            )
        except Exception:
            _refuse()


__all__ = [
    "ExecutiveWorkspaceReturnBindingResolver",
    "WorkspaceReturnPhysicalSource",
    "WorkspaceReturnTargetEpoch",
]
