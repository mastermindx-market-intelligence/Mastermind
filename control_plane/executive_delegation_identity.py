"""Pure company dialogue identity projection for Executive child Jobs."""
from __future__ import annotations

import dataclasses
import re
from typing import Any

from control_plane.executive_orchestration_principal import digest as orchestration_digest
from control_plane.executive_runtime import Job


_JOB_ID_RE = re.compile(r"\AJOB-\d{3,}\Z")
_WIRE_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_DIGEST_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_OPERATION_KEY_RE = re.compile(r"\A[a-z0-9][a-z0-9._-]{7,127}\Z")
_SESSION_REF_RE = re.compile(r"\Aasd-session-[a-z0-9][a-z0-9-]{7,63}\Z")
_CHILD_ROLES = frozenset({"plan", "work", "review", "repair"})
_PROVENANCE_KEYS = frozenset(
    {
        "schema_version",
        "creator",
        "source_id",
        "source_digest",
        "command_id",
        "job_id",
        "parent_job_id",
        "root_job_id",
        "role",
    }
)


class ExecutiveDelegationIdentityError(ValueError):
    """A Job's self-contained child evidence cannot be projected safely."""


@dataclasses.dataclass(frozen=True)
class ExecutiveDelegationIdentity:
    job_id: str
    root_job_id: str
    operation_key: str
    session_ref: str


def _refuse(reason: str) -> None:
    raise ExecutiveDelegationIdentityError(reason)


def _is_wire_id(value: Any) -> bool:
    return isinstance(value, str) and _WIRE_ID_RE.fullmatch(value) is not None


def _validate_revision_lineage(job: Job) -> None:
    role = job.orchestration_role
    if role == "plan":
        if any(
            value is not None
            for value in (
                job.plan_attempt_id,
                job.plan_digest,
                job.plan_step_id,
                job.repair_round,
                job.reviews_job_id,
                job.supersedes_job_id,
            )
        ):
            _refuse("plan Job carries child revision lineage")
        return

    if (
        not _is_wire_id(job.plan_attempt_id)
        or not isinstance(job.plan_digest, str)
        or _DIGEST_RE.fullmatch(job.plan_digest) is None
        or not _is_wire_id(job.plan_step_id)
        or isinstance(job.repair_round, bool)
        or not isinstance(job.repair_round, int)
    ):
        _refuse("orchestration revision lineage is incomplete")

    if role == "work":
        if (
            job.repair_round != 0
            or job.reviews_job_id is not None
            or job.supersedes_job_id is not None
        ):
            _refuse("work Job revision lineage is incoherent")
    elif role == "review":
        if (
            job.repair_round not in {0, 1, 2}
            or not isinstance(job.reviews_job_id, str)
            or _JOB_ID_RE.fullmatch(job.reviews_job_id) is None
            or job.reviews_job_id in {job.job_id, job.root_job_id}
            or job.supersedes_job_id is not None
        ):
            _refuse("review Job revision lineage is incoherent")
    elif role == "repair":
        if (
            job.repair_round not in {1, 2}
            or not isinstance(job.supersedes_job_id, str)
            or _JOB_ID_RE.fullmatch(job.supersedes_job_id) is None
            or job.supersedes_job_id in {job.job_id, job.root_job_id}
            or job.reviews_job_id is not None
        ):
            _refuse("repair Job revision lineage is incoherent")


def _validate_orchestration_child(job: Job) -> None:
    if not isinstance(job, Job):
        _refuse("identity projection requires one Runtime Job")
    for name, value in {
        "job_id": job.job_id,
        "root_job_id": job.root_job_id,
        "parent_job_id": job.parent_job_id,
    }.items():
        if not isinstance(value, str) or _JOB_ID_RE.fullmatch(value) is None:
            _refuse(f"{name} is not a canonical Runtime Job identifier")
    if job.job_id == job.root_job_id:
        _refuse("orchestration child cannot be its own root")
    if (
        job.parent_job_id != job.root_job_id
        or isinstance(job.depth, bool)
        or not isinstance(job.depth, int)
        or job.depth != 1
    ):
        _refuse("orchestration child is not a direct root child")
    if job.orchestration_role not in _CHILD_ROLES:
        _refuse("Job is not a closed orchestration child role")

    provenance = job.orchestration_provenance
    if not isinstance(provenance, dict) or set(provenance) != _PROVENANCE_KEYS:
        _refuse("orchestration provenance is not the closed wire")
    if (
        provenance["schema_version"]
        != "mastermind.executive_orchestration_provenance/v1"
        or provenance["creator"] != "coo_cycle"
        or provenance["job_id"] != job.job_id
        or provenance["parent_job_id"] != job.parent_job_id
        or provenance["root_job_id"] != job.root_job_id
        or provenance["role"] != job.orchestration_role
        or not _is_wire_id(provenance["source_id"])
        or not isinstance(provenance["source_digest"], str)
        or _DIGEST_RE.fullmatch(provenance["source_digest"]) is None
        or not _is_wire_id(provenance["command_id"])
    ):
        _refuse("orchestration provenance identity is incoherent")
    if (
        not isinstance(job.orchestration_provenance_digest, str)
        or _DIGEST_RE.fullmatch(job.orchestration_provenance_digest) is None
        or job.orchestration_provenance_digest != orchestration_digest(provenance)
    ):
        _refuse("orchestration provenance digest is invalid")

    _validate_revision_lineage(job)


def derive_delegation_identity(job: Job) -> ExecutiveDelegationIdentity:
    """Project a direct child Job's self-contained company dialogue identity.

    Runtime remains the lifecycle, admission, live-root, and predecessor-row
    authority.  This pure helper revalidates only immutable evidence carried by
    the decoded Job and performs no lookup, persistence, routing, or provider
    operation.
    """

    _validate_orchestration_child(job)
    job_token = job.job_id.lower()
    operation_key = f"exec-{job_token}"
    session_ref = f"asd-session-exec-{job_token}"
    if (
        _OPERATION_KEY_RE.fullmatch(operation_key) is None
        or _SESSION_REF_RE.fullmatch(session_ref) is None
    ):
        _refuse("projected dialogue identity is outside the V2 transport contract")
    return ExecutiveDelegationIdentity(
        job_id=job.job_id,
        root_job_id=job.root_job_id,
        operation_key=operation_key,
        session_ref=session_ref,
    )
