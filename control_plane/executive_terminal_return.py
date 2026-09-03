"""Pure, bounded projection of one sealed Executive terminal result.

Runtime remains the owner of Job, Attempt, Worker, seal, and lifecycle truth.
This module only reduces freshly-read immutable Runtime facts into a candidate
for an optional caller-owned projection boundary; it performs no I/O.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
from typing import Any

from control_plane.executive_delegation_identity import (
    ExecutiveDelegationIdentityError,
    derive_delegation_identity,
)
from control_plane.executive_runtime import (
    AttemptExecutionMode,
    AttemptStatus,
    ExecutiveDialogueSource,
    JobStatus,
    ValidatedRoleCompletion,
)


class TerminalReturnError(ValueError):
    """A terminal Runtime fact cannot safely become a return candidate."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


_PROJECTION_ERROR_CODES = frozenset(
    {
        "DIALOGUE_BINDING_UNAVAILABLE",
        "DIALOGUE_REFUSED",
        "SERVICE_UNAVAILABLE",
        "TRANSPORT_UNAVAILABLE",
        "EFFECT_UNKNOWN",
        "PRE_SUBMIT_PROTOCOL_REFUSED",
    }
)


class TerminalReturnProjectionError(RuntimeError):
    """A terminal candidate could not cross its optional projection boundary."""

    def __init__(self, code: str) -> None:
        if code not in _PROJECTION_ERROR_CODES:
            raise ValueError("unknown terminal-return projection error code")
        self.code = code
        super().__init__(code)


@dataclasses.dataclass(frozen=True)
class TerminalReturnCandidate:
    """The complete, bounded pure projection of one terminal direct child."""

    job_id: str
    attempt_id: str
    worker_id: str
    root_job_id: str
    role: str
    operation_key: str
    session_ref: str
    runtime_status: str
    result_status: str
    result_digest: str | None
    terminal_digest: str | None
    terminal_at: str
    message_key: str
    summary: str
    review_verdict: str | None
    dialogue_source: ExecutiveDialogueSource | None = None


_TERMINAL_STATUS_MAP = {
    AttemptStatus.COMPLETED: (JobStatus.COMPLETED, "RESULT"),
}
def _refuse(code: str) -> None:
    raise TerminalReturnError(code)


def _terminal_utc(value: Any) -> str:
    if not isinstance(value, str):
        _refuse("EVIDENCE_REFUSED")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _refuse("EVIDENCE_REFUSED")
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() != timedelta(0)
        or parsed.microsecond != 0
    ):
        _refuse("EVIDENCE_REFUSED")
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def reduce_terminal_return(
    *, material: ValidatedRoleCompletion
) -> TerminalReturnCandidate:
    """Reduce one canonical Runtime-owned completion snapshot without I/O.

    Runtime has already validated both receipt families, exact lineage, and the
    Job/Attempt terminal receipt.  This reducer deliberately does not copy that
    law; it only checks the snapshot's local binding and derives the projection
    candidate.
    """

    if not isinstance(material, ValidatedRoleCompletion):
        _refuse("BINDING_REFUSED")
    job = material.job
    attempt = material.attempt
    effective_execution_mode = (
        attempt.execution_mode or AttemptExecutionMode.SEALED_WORKER.value
    )
    if (
        job.current_attempt_id != attempt.attempt_id
        or attempt.job_id != job.job_id
        or effective_execution_mode != material.execution_mode
    ):
        _refuse("BINDING_REFUSED")
    terminal = _TERMINAL_STATUS_MAP.get(attempt.status)
    if terminal is None or job.status is not terminal[0]:
        _refuse("NOT_APPLICABLE")
    try:
        identity = derive_delegation_identity(job)
    except ExecutiveDelegationIdentityError:
        _refuse("IDENTITY_REFUSED")

    envelope = material.result_envelope
    terminal_receipt = material.terminal_receipt
    try:
        terminal_digest = terminal_receipt["terminal_evidence_digest"]
        summary = envelope["summary"]
    except (KeyError, TypeError):
        _refuse("EVIDENCE_REFUSED")
    if (
        not isinstance(terminal_digest, str)
        or not isinstance(summary, str)
        or envelope.get("job_id") != job.job_id
        or envelope.get("run_id") != attempt.attempt_id
        or envelope.get("worker_id") != attempt.worker_id
        or envelope.get("role") != job.orchestration_role
    ):
        _refuse("EVIDENCE_REFUSED")
    review_verdict: str | None = None
    if job.orchestration_role == "review":
        verdict = envelope["role_result"].get("verdict")
        if verdict not in {"approve", "reject"}:
            _refuse("EVIDENCE_REFUSED")
        review_verdict = verdict
    return TerminalReturnCandidate(
        job_id=job.job_id,
        attempt_id=attempt.attempt_id,
        worker_id=attempt.worker_id,
        root_job_id=identity.root_job_id,
        role=str(job.orchestration_role),
        operation_key=identity.operation_key,
        session_ref=identity.session_ref,
        runtime_status=attempt.status.value,
        result_status=terminal[1],
        result_digest=material.result_digest,
        terminal_digest=terminal_digest,
        terminal_at=_terminal_utc(attempt.finished_at),
        message_key=f"asd-exec-result-{terminal_digest}",
        summary=summary,
        review_verdict=review_verdict,
        dialogue_source=material.dialogue_source,
    )
