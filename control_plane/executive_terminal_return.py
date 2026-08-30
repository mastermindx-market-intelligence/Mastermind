"""Pure, bounded projection of one sealed Executive terminal result.

Runtime remains the owner of Job, Attempt, Worker, seal, and lifecycle truth.
This module only reduces freshly-read immutable Runtime facts into a candidate
for an optional caller-owned projection boundary; it performs no I/O.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Any

from control_plane.executive_delegation_identity import (
    ExecutiveDelegationIdentityError,
    derive_delegation_identity,
)
from control_plane.executive_orchestration_result import (
    OrchestrationResultError,
    canonical_bytes,
    canonical_digest,
    validate_envelope,
)
from control_plane.executive_runtime import Attempt, AttemptStatus, Job, JobStatus, Worker


class TerminalReturnError(ValueError):
    """A terminal Runtime fact cannot safely become a return candidate."""

    def __init__(self, code: str) -> None:
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
    message_key: str
    summary: str
    review_verdict: str | None


_TERMINAL_STATUS_MAP = {
    AttemptStatus.COMPLETED: (JobStatus.COMPLETED, "RESULT"),
}
_TERMINAL_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "job_id",
        "attempt_id",
        "orchestration_role",
        "execution_mode",
        "result_seal_command_id",
        "result_evidence",
        "result_envelope",
        "result_envelope_digest",
        "artifact_receipt_digest",
        "validation_receipt_digest",
        "effective_grant_digest",
        "terminal_evidence_digest",
    }
)


def _refuse(code: str) -> None:
    raise TerminalReturnError(code)


def _same_canonical_json(left: Any, right: Any) -> bool:
    try:
        return canonical_bytes(left) == canonical_bytes(right)
    except TerminalReturnError:
        raise
    except (OrchestrationResultError, TypeError, ValueError):
        return False


def _is_digest(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _validated_completed_result(job: Job, attempt: Attempt) -> tuple[dict[str, Any], str]:
    receipt = attempt.result
    if not isinstance(receipt, dict) or set(receipt) != _TERMINAL_RECEIPT_KEYS:
        _refuse("EVIDENCE_REFUSED")
    if not _same_canonical_json(job.result, receipt):
        _refuse("EVIDENCE_REFUSED")
    role = job.orchestration_role
    execution_mode = attempt.execution_mode or "SEALED_WORKER"
    expected_seal_command = (
        f"orchestration-result-seal:{attempt.attempt_id}"
        if execution_mode == "OPERATOR_HARNESS"
        else f"sealed-worker-result:{attempt.attempt_id}"
    )
    if (
        execution_mode not in {"OPERATOR_HARNESS", "SEALED_WORKER"}
        or receipt.get("schema_version")
        != "mastermind.orchestration_terminal_receipt/v1"
        or receipt.get("status") != "COMPLETED"
        or receipt.get("job_id") != job.job_id
        or receipt.get("attempt_id") != attempt.attempt_id
        or receipt.get("orchestration_role") != role
        or receipt.get("execution_mode") != execution_mode
        or receipt.get("result_seal_command_id") != expected_seal_command
        or not isinstance(receipt.get("result_envelope"), dict)
        or not all(
            _is_digest(receipt.get(name))
            for name in (
                "result_envelope_digest",
                "artifact_receipt_digest",
                "validation_receipt_digest",
                "effective_grant_digest",
                "terminal_evidence_digest",
            )
        )
        or receipt.get("effective_grant_digest") != attempt.effective_grant_digest
        or (
            execution_mode == "OPERATOR_HARNESS"
            and receipt.get("result_evidence") is not None
        )
        or (
            execution_mode == "SEALED_WORKER"
            and not isinstance(receipt.get("result_evidence"), dict)
        )
    ):
        _refuse("EVIDENCE_REFUSED")
    unsigned = dict(receipt)
    terminal_digest = unsigned.pop("terminal_evidence_digest")
    try:
        if canonical_digest(unsigned) != terminal_digest:
            _refuse("EVIDENCE_REFUSED")
        envelope = validate_envelope(
            receipt["result_envelope"],
            expected_job_id=job.job_id,
            expected_run_id=attempt.attempt_id,
            expected_worker_id=attempt.worker_id,
            expected_role=str(role),
            expected_root_job_id=job.root_job_id,
        )
        digest = canonical_digest(envelope)
    except TerminalReturnError:
        raise
    except (OrchestrationResultError, TypeError, ValueError):
        _refuse("EVIDENCE_REFUSED")
    if receipt.get("result_envelope_digest") != digest:
        _refuse("EVIDENCE_REFUSED")
    return envelope, digest


def reduce_terminal_return(*, job: Job, attempt: Attempt, worker: Worker) -> TerminalReturnCandidate:
    """Reduce exactly one current sealed direct-child terminal result.

    All supplied objects must be current, mutually bound Runtime objects.  Any
    missing, stale, foreign, malformed, or noncanonical fact is a typed pure
    refusal; this function never repairs, defaults, or persists it.
    """

    if (
        not isinstance(job, Job)
        or not isinstance(attempt, Attempt)
        or not isinstance(worker, Worker)
    ):
        _refuse("BINDING_REFUSED")
    if (
        job.current_attempt_id != attempt.attempt_id
        or attempt.job_id != job.job_id
        or attempt.worker_id != worker.worker_id
    ):
        _refuse("BINDING_REFUSED")
    terminal = _TERMINAL_STATUS_MAP.get(attempt.status)
    if terminal is None or job.status is not terminal[0]:
        _refuse("NOT_APPLICABLE")
    try:
        identity = derive_delegation_identity(job)
    except ExecutiveDelegationIdentityError:
        _refuse("IDENTITY_REFUSED")

    envelope, digest = _validated_completed_result(job, attempt)
    review_verdict: str | None = None
    if job.orchestration_role == "review":
        verdict = envelope["role_result"].get("verdict")
        if verdict not in {"approve", "reject"}:
            _refuse("EVIDENCE_REFUSED")
        review_verdict = verdict
    return TerminalReturnCandidate(
        job_id=job.job_id,
        attempt_id=attempt.attempt_id,
        worker_id=worker.worker_id,
        root_job_id=identity.root_job_id,
        role=str(job.orchestration_role),
        operation_key=identity.operation_key,
        session_ref=identity.session_ref,
        runtime_status=attempt.status.value,
        result_status=terminal[1],
        result_digest=digest,
        terminal_digest=str(attempt.result["terminal_evidence_digest"]),
        message_key=f"asd-exec-result-{str(attempt.result['terminal_evidence_digest'])}",
        summary=str(envelope["summary"]),
        review_verdict=review_verdict,
    )
