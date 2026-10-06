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
_ROOT_ROLE = "aggregation"
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


@dataclasses.dataclass(frozen=True)
class NestedExecutiveDelegationIdentity:
    """Immutable identity for one admitted depth-2 orchestration child."""

    job_id: str
    parent_job_id: str
    root_job_id: str
    operation_key: str
    session_ref: str


def _refuse(reason: str) -> None:
    raise ExecutiveDelegationIdentityError(reason)


def _is_wire_id(value: Any) -> bool:
    return isinstance(value, str) and _WIRE_ID_RE.fullmatch(value) is not None


def _validate_revision_lineage(job: Job) -> None:
    role = job.orchestration_role
    if role == _ROOT_ROLE:
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
            _refuse("aggregation root carries child revision lineage")
        return

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
    required_ids = {
        "job_id": job.job_id,
        "root_job_id": job.root_job_id,
    }
    if job.orchestration_role != _ROOT_ROLE:
        required_ids["parent_job_id"] = job.parent_job_id
    for name, value in required_ids.items():
        if not isinstance(value, str) or _JOB_ID_RE.fullmatch(value) is None:
            _refuse(f"{name} is not a canonical Runtime Job identifier")
    if job.orchestration_role == _ROOT_ROLE:
        if (
            job.job_id != job.root_job_id
            or job.parent_job_id is not None
            or isinstance(job.depth, bool)
            or not isinstance(job.depth, int)
            or job.depth != 0
        ):
            _refuse("aggregation root is not a strict root")
    else:
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
        or provenance["job_id"] != job.job_id
        or provenance["root_job_id"] != job.root_job_id
        or provenance["role"] != job.orchestration_role
        or provenance["parent_job_id"] != job.parent_job_id
        or (
            provenance["creator"] != "ceo_intent"
            if job.orchestration_role == _ROOT_ROLE
            else provenance["creator"] != "coo_cycle"
        )
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

def _validate_nested_orchestration_child(job: Job, parent: Job) -> None:
    """Validate immutable lineage only; never grant nested delegation authority.

    The parent must already be a canonical direct-root ``work`` child.  That is
    the existing role a future domain coordinator can occupy without adding a
    sixth orchestration-role enum.  Runtime/Capacity remain responsible for
    proving that this particular work Job was admitted as a coordinator, that
    one root budget covers every descendant, and that child returns are
    consumed by the same parent.
    """

    if not isinstance(job, Job) or not isinstance(parent, Job):
        _refuse("nested identity projection requires Runtime Jobs")

    # Reuse the protected V1 validator for the depth-1 parent.  It proves the
    # strict root relationship, closed provenance wire and revision lineage.
    _validate_orchestration_child(parent)
    if parent.orchestration_role != "work" or parent.depth != 1:
        _refuse("nested delegation parent is not a direct-root work Job")

    required_ids = {
        "job_id": job.job_id,
        "parent_job_id": job.parent_job_id,
        "root_job_id": job.root_job_id,
    }
    for name, value in required_ids.items():
        if not isinstance(value, str) or _JOB_ID_RE.fullmatch(value) is None:
            _refuse(f"{name} is not a canonical Runtime Job identifier")

    if (
        job.job_id in {parent.job_id, parent.root_job_id}
        or job.parent_job_id != parent.job_id
        or job.root_job_id != parent.root_job_id
        or isinstance(job.depth, bool)
        or not isinstance(job.depth, int)
        or job.depth != 2
        or job.orchestration_role not in {"work", "review", "repair"}
    ):
        _refuse("nested orchestration lineage is not one conserved-root depth-2 child")

    provenance = job.orchestration_provenance
    if not isinstance(provenance, dict) or set(provenance) != _PROVENANCE_KEYS:
        _refuse("nested orchestration provenance is not the closed wire")
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
        _refuse("nested orchestration provenance identity is incoherent")
    if (
        not isinstance(job.orchestration_provenance_digest, str)
        or _DIGEST_RE.fullmatch(job.orchestration_provenance_digest) is None
        or job.orchestration_provenance_digest != orchestration_digest(provenance)
    ):
        _refuse("nested orchestration provenance digest is invalid")

    _validate_revision_lineage(job)


def derive_nested_delegation_identity(
    job: Job, parent: Job
) -> NestedExecutiveDelegationIdentity:
    """Project a depth-2 child's lineage-bound company dialogue identity.

    This is an additive fail-closed contract for the Sol-led domain-coordinator
    program.  It performs no Runtime lookup, child creation, capacity claim,
    provider launch, result consumption or authority expansion.  Callers must
    separately prove the parent's coordinator admission and the conserved root
    budget before START.
    """

    _validate_nested_orchestration_child(job, parent)
    job_token = job.job_id.lower()
    operation_key = f"exec-{job_token}"
    session_ref = f"asd-session-exec-{job_token}"
    if (
        _OPERATION_KEY_RE.fullmatch(operation_key) is None
        or _SESSION_REF_RE.fullmatch(session_ref) is None
    ):
        _refuse("projected nested dialogue identity is outside the V2 transport contract")
    return NestedExecutiveDelegationIdentity(
        job_id=job.job_id,
        parent_job_id=parent.job_id,
        root_job_id=job.root_job_id,
        operation_key=operation_key,
        session_ref=session_ref,
    )
