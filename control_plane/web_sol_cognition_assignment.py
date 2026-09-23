"""Bounded read-only assignment projection for ChatGPT Web cognition workers.

This module is a pure projection over existing Executive Runtime identity,
immutable commission provenance, and the bounded Agent OS Web-Sol continuation
owner. It starts no browser work, grants no authority, owns no lifecycle or
result store, and accepts no caller-authored free-form prompt body.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping
from typing import Any, Final

from control_plane.executive_orchestration_result import orchestration_result_schema
from control_plane.executive_runtime import (
    Attempt,
    AttemptStatus,
    ExecutiveDialogueSource,
    Job,
    JobStatus,
)
from control_plane.web_sol_continuation import (
    WebSolContinuationError,
    build_continuation,
)


ASSIGNMENT_SCHEMA: Final[str] = "mastermind.web_sol_cognition_assignment/v1"
MAX_ASSIGNMENT_JSON_BYTES: Final[int] = 22 * 1024
MAX_RENDERED_ASSIGNMENT_BYTES: Final[int] = 24 * 1024
WORK_COGNITION_AUTHORITIES: Final[frozenset[str]] = frozenset({"READ", "RESEARCH"})
REVIEW_COGNITION_AUTHORITIES: Final[frozenset[str]] = frozenset({"READ"})
SUPPORTED_ROLES: Final[frozenset[str]] = frozenset({"work", "review"})

_FIXED_DIRECTIVE = "\n".join(
    (
        "MASTERMIND WEB COGNITION ASSIGNMENT v1",
        "",
        "This is one already-admitted read/research-only Executive Attempt.",
        "Do not perform writes, sends, mutations, installs, submissions, commits, pushes, merges, deployments, service-control actions, credential changes, account changes, or other external effects.",
        "Use only read/research actions that are positively available and serviceable in this exact session. A missing read capability is a blocker to report, not permission to switch accounts, sessions, transports, or action class.",
        "The JSON below is a bounded projection of existing Executive OS and Agent OS owners. It grants no authority and creates no lifecycle state.",
        "At completion, the final assistant message MUST be exactly one canonical JSON object matching result_contract.schema: UTF-8, object keys lexicographically sorted, separators ',' and ':', no insignificant whitespace, no BOM, no Markdown fence, and no prose before or after it.",
        "",
        "ASSIGNMENT_JSON",
    )
)


class WebSolCognitionAssignmentError(ValueError):
    """A cognition assignment cannot cross the bounded browser ingress."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise WebSolCognitionAssignmentError("ASSIGNMENT_NOT_CANONICAL_JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _require_exact_runtime_binding(job: Job, attempt: Attempt) -> None:
    if not isinstance(job, Job) or not isinstance(attempt, Attempt):
        raise WebSolCognitionAssignmentError("RUNTIME_IDENTITY_INVALID")
    if (
        job.job_id != attempt.job_id
        or job.current_attempt_id != attempt.attempt_id
        or job.assigned_worker_id != attempt.worker_id
        or job.assigned_quota_class != attempt.quota_class
        or not job.root_job_id
    ):
        raise WebSolCognitionAssignmentError("RUNTIME_IDENTITY_MISMATCH")
    if job.status is not JobStatus.RUNNING or attempt.status is not AttemptStatus.CLAIMED:
        raise WebSolCognitionAssignmentError("ATTEMPT_NOT_PRESTART_CLAIMED")


def _require_research_only(job: Job) -> None:
    role = job.orchestration_role
    if role not in SUPPORTED_ROLES:
        raise WebSolCognitionAssignmentError("ROLE_NOT_COGNITION_ASSIGNABLE")
    expected_authorities = (
        WORK_COGNITION_AUTHORITIES
        if role == "work"
        else REVIEW_COGNITION_AUTHORITIES
    )
    authorities = list(job.requested_authorities)
    if (
        len(authorities) != len(set(authorities))
        or frozenset(authorities) != expected_authorities
        or list(job.allowed_write_paths)
        or list(job.validation_commands)
    ):
        raise WebSolCognitionAssignmentError("JOB_NOT_RESEARCH_ONLY")
    if not isinstance(job.objective, str) or not job.objective.strip():
        raise WebSolCognitionAssignmentError("OBJECTIVE_INVALID")


def _source_projection(
    dialogue_source: ExecutiveDialogueSource,
    *,
    workstream: str,
) -> dict[str, Any]:
    if not isinstance(dialogue_source, ExecutiveDialogueSource):
        raise WebSolCognitionAssignmentError("DIALOGUE_SOURCE_INVALID")
    if dialogue_source.work_ref != workstream:
        raise WebSolCognitionAssignmentError("DIALOGUE_SOURCE_WORKSTREAM_MISMATCH")
    source = dialogue_source.to_dict()
    return {
        "work_ref": workstream,
        "commission_ref": source["commission_ref"],
        "dialogue_source_digest": _digest(source),
    }


def _job_projection(job: Job, attempt: Attempt) -> dict[str, Any]:
    return {
        "attempt_id": attempt.attempt_id,
        "job_id": job.job_id,
        "objective": job.objective,
        "plan_attempt_id": job.plan_attempt_id,
        "plan_digest": job.plan_digest,
        "plan_step_id": job.plan_step_id,
        "quota_class": attempt.quota_class,
        "repair_round": job.repair_round,
        "review_required": job.review_required,
        "reviews_job_id": job.reviews_job_id,
        "role": job.orchestration_role,
        "root_job_id": job.root_job_id,
        "worker_id": attempt.worker_id,
    }


def _effect_contract(job: Job) -> dict[str, Any]:
    return {
        "allowed_write_paths": [],
        "external_effects_allowed": False,
        "requested_authorities": sorted(job.requested_authorities),
    }


@dataclasses.dataclass(frozen=True, slots=True)
class WebSolCognitionAssignment:
    """One deterministic non-authoritative browser assignment projection."""

    document: Mapping[str, Any] = dataclasses.field(repr=False)
    canonical_json: str = dataclasses.field(repr=False)
    assignment_digest: str
    rendered_prompt: str = dataclasses.field(repr=False)
    rendered_prompt_bytes: int

    def __post_init__(self) -> None:
        if self.assignment_digest != hashlib.sha256(
            self.canonical_json.encode("utf-8")
        ).hexdigest():
            raise WebSolCognitionAssignmentError("ASSIGNMENT_DIGEST_MISMATCH")
        if self.rendered_prompt != f"{_FIXED_DIRECTIVE}\n{self.canonical_json}":
            raise WebSolCognitionAssignmentError("ASSIGNMENT_RENDER_DRIFT")
        if len(self.rendered_prompt.encode("utf-8")) != self.rendered_prompt_bytes:
            raise WebSolCognitionAssignmentError("ASSIGNMENT_BYTE_LENGTH_MISMATCH")
        if self.rendered_prompt_bytes > MAX_RENDERED_ASSIGNMENT_BYTES:
            raise WebSolCognitionAssignmentError("ASSIGNMENT_TOO_LARGE")


def build_web_sol_cognition_assignment(
    *,
    job: Job,
    attempt: Attempt,
    dialogue_source: ExecutiveDialogueSource,
    agentos: Mapping[str, Any],
    workstream: str,
) -> WebSolCognitionAssignment:
    """Build one bounded prompt for an already-selected cognition-only Attempt.

    The caller remains responsible for Executive admission, exact-session capability
    preflight, RuntimeBinding, browser transport, and lifecycle transitions. This
    function only projects already-canonical inputs into deterministic browser text.
    """

    _require_exact_runtime_binding(job, attempt)
    _require_research_only(job)
    source = _source_projection(dialogue_source, workstream=workstream)

    try:
        continuation = build_continuation(agentos, workstream)
    except (WebSolContinuationError, TypeError, ValueError) as exc:
        raise WebSolCognitionAssignmentError("CONTINUATION_REFUSED") from exc

    result_schema = orchestration_result_schema(
        str(job.orchestration_role),
        job_id=job.job_id,
        run_id=attempt.attempt_id,
        worker_id=attempt.worker_id,
        root_job_id=job.root_job_id,
    )
    document: dict[str, Any] = {
        "continuation": continuation,
        "continuation_digest": _digest(continuation),
        "effect_contract": _effect_contract(job),
        "job": _job_projection(job, attempt),
        "result_contract": {
            "schema": result_schema,
            "schema_digest": _digest(result_schema),
        },
        "schema_version": ASSIGNMENT_SCHEMA,
        "source": source,
    }
    encoded = _canonical_bytes(document)
    if len(encoded) > MAX_ASSIGNMENT_JSON_BYTES:
        raise WebSolCognitionAssignmentError("ASSIGNMENT_JSON_TOO_LARGE")
    canonical_json = encoded.decode("utf-8")
    rendered = f"{_FIXED_DIRECTIVE}\n{canonical_json}"
    rendered_bytes = len(rendered.encode("utf-8"))
    if rendered_bytes > MAX_RENDERED_ASSIGNMENT_BYTES:
        raise WebSolCognitionAssignmentError("ASSIGNMENT_TOO_LARGE")
    return WebSolCognitionAssignment(
        document=document,
        canonical_json=canonical_json,
        assignment_digest=hashlib.sha256(encoded).hexdigest(),
        rendered_prompt=rendered,
        rendered_prompt_bytes=rendered_bytes,
    )


__all__ = [
    "ASSIGNMENT_SCHEMA",
    "MAX_ASSIGNMENT_JSON_BYTES",
    "MAX_RENDERED_ASSIGNMENT_BYTES",
    "REVIEW_COGNITION_AUTHORITIES",
    "WORK_COGNITION_AUTHORITIES",
    "SUPPORTED_ROLES",
    "WebSolCognitionAssignment",
    "WebSolCognitionAssignmentError",
    "build_web_sol_cognition_assignment",
]
