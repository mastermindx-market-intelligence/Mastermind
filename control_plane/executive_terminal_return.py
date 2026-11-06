"""Pure, bounded projection of one sealed Executive terminal result.

Runtime remains the owner of Job, Attempt, Worker, seal, and lifecycle truth.
This module only reduces freshly-read immutable Runtime facts into a candidate
for an optional caller-owned projection boundary; it performs no I/O.
"""
from __future__ import annotations

import dataclasses
import json
import re
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
class TerminalReviewFinding:
    """One already-validated review finding safe for bounded return projection."""

    code: str
    severity: str
    message: str
    evidence_digests: tuple[str, ...] = ()


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
    result_envelope_digest: str
    terminal_evidence_digest: str
    artifact_receipt_digest: str
    validation_receipt_digest: str
    effective_grant_digest: str
    terminal_at: str
    message_key: str
    summary: str
    review_verdict: str | None
    next_actions: tuple[str, ...] = ()
    review_findings: tuple[TerminalReviewFinding, ...] = ()
    dialogue_source: ExecutiveDialogueSource | None = None

    @property
    def result_digest(self) -> str:
        """Compatibility spelling for the result-envelope digest."""

        return self.result_envelope_digest

    @property
    def terminal_digest(self) -> str:
        """Compatibility spelling for the terminal-evidence digest."""

        return self.terminal_evidence_digest


_TERMINAL_STATUS_MAP = {
    AttemptStatus.COMPLETED: (JobStatus.COMPLETED, "RESULT"),
}
def _refuse(code: str) -> None:
    raise TerminalReturnError(code)


def _text_tuple(value: Any, *, code: str = "EVIDENCE_REFUSED") -> tuple[str, ...]:
    if not isinstance(value, list):
        _refuse(code)
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            _refuse(code)
        if item in result:
            _refuse(code)
        result.append(item)
    return tuple(result)


def _review_findings(value: Any) -> tuple[TerminalReviewFinding, ...]:
    if not isinstance(value, list):
        _refuse("EVIDENCE_REFUSED")
    result: list[TerminalReviewFinding] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {
            "code", "severity", "message", "evidence_digests"
        }:
            _refuse("EVIDENCE_REFUSED")
        code = item["code"]
        severity = item["severity"]
        message = item["message"]
        evidence = item["evidence_digests"]
        if (
            not isinstance(code, str)
            or not code
            or severity not in {"info", "warning", "blocking"}
            or not isinstance(message, str)
            or not message
            or not isinstance(evidence, list)
        ):
            _refuse("EVIDENCE_REFUSED")
        digests: list[str] = []
        for digest in evidence:
            if (
                not isinstance(digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                or digest in digests
            ):
                _refuse("EVIDENCE_REFUSED")
            digests.append(digest)
        finding = TerminalReviewFinding(
            code=code,
            severity=severity,
            message=message,
            evidence_digests=tuple(digests),
        )
        if finding in result:
            _refuse("EVIDENCE_REFUSED")
        result.append(finding)
    return tuple(result)


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
    digest_names = (
        "result_envelope_digest",
        "terminal_evidence_digest",
        "artifact_receipt_digest",
        "validation_receipt_digest",
        "effective_grant_digest",
    )
    try:
        digests = {name: terminal_receipt[name] for name in digest_names}
        summary = envelope["summary"]
        next_actions = _text_tuple(envelope["next_actions"])
    except (KeyError, TypeError):
        _refuse("EVIDENCE_REFUSED")
    if (
        not isinstance(summary, str)
        or any(
            not isinstance(value, str)
            or re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in digests.values()
        )
        or digests["result_envelope_digest"] != material.result_digest
        or digests["effective_grant_digest"] != attempt.effective_grant_digest
        or envelope.get("job_id") != job.job_id
        or envelope.get("run_id") != attempt.attempt_id
        or envelope.get("worker_id") != attempt.worker_id
        or envelope.get("role") != job.orchestration_role
    ):
        _refuse("EVIDENCE_REFUSED")
    review_verdict: str | None = None
    review_findings: tuple[TerminalReviewFinding, ...] = ()
    if job.orchestration_role == "review":
        role_result = envelope.get("role_result")
        if not isinstance(role_result, dict):
            _refuse("EVIDENCE_REFUSED")
        verdict = role_result.get("verdict")
        if not isinstance(verdict, str) or verdict not in ("approve", "reject"):
            _refuse("EVIDENCE_REFUSED")
        review_verdict = verdict
        review_findings = _review_findings(role_result.get("findings"))
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
        result_envelope_digest=digests["result_envelope_digest"],
        terminal_evidence_digest=digests["terminal_evidence_digest"],
        artifact_receipt_digest=digests["artifact_receipt_digest"],
        validation_receipt_digest=digests["validation_receipt_digest"],
        effective_grant_digest=digests["effective_grant_digest"],
        terminal_at=_terminal_utc(attempt.finished_at),
        message_key=f"asd-exec-result-{digests['terminal_evidence_digest']}",
        summary=summary,
        review_verdict=review_verdict,
        next_actions=next_actions,
        review_findings=review_findings,
        dialogue_source=material.dialogue_source,
    )


SELECTED_CHILD_RESULT_SCHEMA = "mastermind.executive_selected_child_result/v1"
SELECTED_CHILD_RESULT_MAX_BYTES = 32 * 1024
_SELECTED_CHILD_RESULT_IDENTITIES = ("command_id", "job_id", "attempt_id", "root_job_id", "role")
_SELECTED_CHILD_RESULT_DIGESTS = (
    "result_envelope_digest", "terminal_evidence_digest", "artifact_receipt_digest",
    "validation_receipt_digest", "effective_grant_digest",
)
_SELECTED_CHILD_RESULT_KEYS = frozenset((
    "schema", "summary", "next_actions", "parent_consumed",
    *_SELECTED_CHILD_RESULT_IDENTITIES, *_SELECTED_CHILD_RESULT_DIGESTS,
))


def validate_selected_child_result_capsule(value: Any, *, observation: dict[str, Any]) -> dict[str, Any]:
    """Validate content against the same original completed observation.

    This is a projection of existing sealed Runtime facts, not a read grant.
    parent_consumed=False describes this read: it writes no acceptance or ACK.
    The native conversation session is deliberately absent from this capsule.
    """
    if (type(value) is not dict or set(value) != _SELECTED_CHILD_RESULT_KEYS
            or value["schema"] != SELECTED_CHILD_RESULT_SCHEMA
            or value["parent_consumed"] is not False
            or observation.get("state") != "COMPLETED"
            or observation.get("result_status") != "RESULT"
            or observation.get("attempt_status") != "COMPLETED"
            or observation.get("job_status") != "COMPLETED"
            or type(value["role"]) is not str or value["role"] not in {"work", "repair"}):
        raise ValueError("selected child result is not an exact completed read")
    for key in _SELECTED_CHILD_RESULT_IDENTITIES:
        item = value[key]
        if (type(item) is not str or not item
                or observation.get(key) != item):
            raise ValueError("selected child result belongs to another observation")
    for key in _SELECTED_CHILD_RESULT_DIGESTS:
        if type(value[key]) is not str or re.fullmatch(r"[0-9a-f]{64}", value[key]) is None:
            raise ValueError("selected child result receipt is invalid")
    for key in ("result_envelope_digest", "terminal_evidence_digest"):
        if observation.get(key) != value[key]:
            raise ValueError("selected child result receipt changed")
    summary, actions = value["summary"], value["next_actions"]
    if (type(summary) is not str or len(summary) > 8192 or "\x00" in summary
            or type(actions) is not list or len(actions) > 16
            or any(type(item) is not str or not 1 <= len(item) <= 8192 or "\x00" in item for item in actions)
            or len(set(actions)) != len(actions)):
        raise ValueError("selected child result content is invalid")
    try:
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError):
        raise ValueError("selected child result is not canonical UTF-8") from None
    if len(encoded) > SELECTED_CHILD_RESULT_MAX_BYTES:
        raise ValueError("selected child result exceeds its response budget")
    return json.loads(encoded)


def selected_child_result_capsule(
    candidate: TerminalReturnCandidate, *, command_id: str,
) -> dict[str, Any] | None:
    """Project a complete bounded synopsis, or retain metadata without slicing."""
    if (type(candidate) is not TerminalReturnCandidate
            or candidate.runtime_status != "COMPLETED"
            or candidate.result_status != "RESULT" or candidate.role not in {"work", "repair"}):
        raise ValueError("selected child completion is not qualified")
    value = {
        "schema": SELECTED_CHILD_RESULT_SCHEMA, "command_id": command_id,
        "job_id": candidate.job_id, "attempt_id": candidate.attempt_id,
        "root_job_id": candidate.root_job_id, "role": candidate.role,
        **{key: getattr(candidate, key) for key in _SELECTED_CHILD_RESULT_DIGESTS},
        "summary": candidate.summary, "next_actions": list(candidate.next_actions),
        "parent_consumed": False,
    }
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(encoded) > SELECTED_CHILD_RESULT_MAX_BYTES:
        return None
    observation = {
        **{key: value[key] for key in _SELECTED_CHILD_RESULT_IDENTITIES},
        "state": "COMPLETED", "result_status": "RESULT",
        "attempt_status": "COMPLETED", "job_status": "COMPLETED",
        "result_envelope_digest": candidate.result_envelope_digest,
        "terminal_evidence_digest": candidate.terminal_evidence_digest,
    }
    return validate_selected_child_result_capsule(value, observation=observation)
