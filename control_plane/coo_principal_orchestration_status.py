"""Read-only reconciliation for an admitted COO principal orchestration root.

The Executive Runtime event/Job remain the only lifecycle record. This module
creates no status table, retry plane, cache, watcher, Job, Attempt, Event, or
provider action. It only validates and projects one existing root by the
original role-neutral COO request reference.
"""
from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from typing import Any

from control_plane import ceo_intent
from control_plane.coo_principal_request import (
    ORCHESTRATION_ACTION_KIND,
    REQUEST_REF_RE,
    principal_intent_id,
)
from control_plane.executive_runtime import (
    PRINCIPAL_ORCHESTRATION_ROOT_CREATOR,
    JobStatus,
    orchestration_digest,
)


STATUS_SCHEMA = "mastermind.executive_principal_orchestration_status.v1"

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_WORK_REF_RE = re.compile(r"^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$")

_BASE_PROVENANCE_KEYS = frozenset(
    {
        "schema",
        "intent_id",
        "request_ref",
        "action_kind",
        "request_fingerprint",
        "bundle_digest",
        "actor",
        "seat",
        "principal_binding_digest",
        "mission_authority_ref",
        "authority_generation_digest",
        "grounding",
        "workstream",
    }
)
_DIALOGUE_PROVENANCE_KEYS = frozenset({"dialogue_source", "dialogue_source_digest"})


class PrincipalOrchestrationStatusError(ValueError):
    """Durable principal-root status could not be proven."""


class PrincipalOrchestrationNotFound(PrincipalOrchestrationStatusError):
    """No durable root currently owns the supplied request identity."""


def _request_ref(value: object) -> str:
    if type(value) is not str or REQUEST_REF_RE.fullmatch(value) is None:
        raise PrincipalOrchestrationStatusError("request_ref is invalid")
    return value


def _work_ref(value: object) -> str:
    if type(value) is not str or _WORK_REF_RE.fullmatch(value) is None:
        raise PrincipalOrchestrationStatusError("work_ref is invalid")
    return value


def _digest(value: object, *, field: str) -> str:
    if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
        raise PrincipalOrchestrationStatusError(f"{field} is invalid")
    return value


def _provenance(
    value: object,
    *,
    request_ref: str,
    intent_id: str,
    work_ref: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PrincipalOrchestrationStatusError("root creation provenance is unavailable")
    keys = set(value)
    if (
        keys != set(_BASE_PROVENANCE_KEYS)
        and keys != set(_BASE_PROVENANCE_KEYS | _DIALOGUE_PROVENANCE_KEYS)
    ):
        raise PrincipalOrchestrationStatusError("root creation provenance fields differ")
    if (
        value.get("schema") != "mastermind.executive_principal_orchestration.v1"
        or value.get("intent_id") != intent_id
        or value.get("request_ref") != request_ref
        or value.get("action_kind") != ORCHESTRATION_ACTION_KIND
        or value.get("actor") != "coo-principal"
        or value.get("seat") != "coo"
        or value.get("workstream") != work_ref
    ):
        raise PrincipalOrchestrationStatusError("root creation identity differs")
    for field in (
        "request_fingerprint",
        "bundle_digest",
        "principal_binding_digest",
        "authority_generation_digest",
    ):
        _digest(value.get(field), field=field)
    mission_authority_ref = value.get("mission_authority_ref")
    if (
        type(mission_authority_ref) is not str
        or not mission_authority_ref
        or mission_authority_ref != mission_authority_ref.strip()
    ):
        raise PrincipalOrchestrationStatusError("mission_authority_ref is invalid")
    grounding = value.get("grounding")
    if not isinstance(grounding, Mapping):
        raise PrincipalOrchestrationStatusError("grounding is unavailable")

    if _DIALOGUE_PROVENANCE_KEYS <= keys:
        dialogue_source = value.get("dialogue_source")
        if not isinstance(dialogue_source, Mapping):
            raise PrincipalOrchestrationStatusError("dialogue source is invalid")
        _digest(value.get("dialogue_source_digest"), field="dialogue_source_digest")
    return dict(value)


def resolve_principal_orchestration(
    runtime: Any,
    *,
    request_ref: str,
    work_ref: str,
) -> dict[str, Any]:
    """Project one existing principal root from durable Runtime state only."""

    request_ref = _request_ref(request_ref)
    work_ref = _work_ref(work_ref)
    intent_id = principal_intent_id(request_ref)
    command_id = ceo_intent.command_id_for(intent_id)

    store = getattr(runtime, "store", None)
    jobs = getattr(runtime, "jobs", None)
    if (
        store is None
        or jobs is None
        or not callable(getattr(store, "find_event_by_command_id", None))
        or not callable(getattr(jobs, "get_job", None))
    ):
        raise PrincipalOrchestrationStatusError("Runtime status owner is unavailable")

    event = store.find_event_by_command_id(command_id)
    if event is None:
        raise PrincipalOrchestrationNotFound("principal orchestration has no durable root")
    if (
        type(event) is not dict
        or event.get("event_type") != "JOB_CREATED"
        or type(event.get("job_id")) is not str
        or type(event.get("created_at_ms")) is not int
        or event["created_at_ms"] < 0
    ):
        raise PrincipalOrchestrationStatusError("principal root creation event is invalid")

    job = jobs.get_job(event["job_id"])
    if job is None:
        raise PrincipalOrchestrationStatusError("principal root Job is unavailable")
    cycle = getattr(job, "orchestration_provenance", None)
    cycle_digest = getattr(job, "orchestration_provenance_digest", None)
    if (
        getattr(job, "orchestration_role", None) != "aggregation"
        or getattr(job, "parent_job_id", None) is not None
        or getattr(job, "root_job_id", None) != getattr(job, "job_id", None)
        or not isinstance(cycle, Mapping)
        or cycle.get("creator") != PRINCIPAL_ORCHESTRATION_ROOT_CREATOR
        or cycle.get("source_id") != intent_id
        or cycle.get("command_id") != command_id
        or cycle.get("job_id") != job.job_id
        or cycle.get("root_job_id") != job.job_id
        or cycle.get("parent_job_id") is not None
        or cycle.get("role") != "aggregation"
        or type(cycle_digest) is not str
        or _DIGEST_RE.fullmatch(cycle_digest) is None
        or cycle_digest != orchestration_digest(cycle)
    ):
        raise PrincipalOrchestrationStatusError("principal root Runtime lineage differs")

    provenance = _provenance(
        event.get("payload", {}).get("provenance")
        if isinstance(event.get("payload"), Mapping)
        else None,
        request_ref=request_ref,
        intent_id=intent_id,
        work_ref=work_ref,
    )
    if provenance["bundle_digest"] != cycle.get("source_digest"):
        raise PrincipalOrchestrationStatusError("principal root source digest differs")

    status = getattr(job, "status", None)
    if not isinstance(status, JobStatus):
        raise PrincipalOrchestrationStatusError("principal root status is invalid")
    return {
        "schema": STATUS_SCHEMA,
        "request_ref": request_ref,
        "intent_id": intent_id,
        "action_kind": ORCHESTRATION_ACTION_KIND,
        "work_ref": work_ref,
        "job_id": job.job_id,
        "job_status": status.value,
        "accepted": True,
        "created_at_ms": event["created_at_ms"],
        "request_fingerprint": provenance["request_fingerprint"],
        "bundle_digest": provenance["bundle_digest"],
        "principal_binding_digest": provenance["principal_binding_digest"],
        "mission_authority_ref": provenance["mission_authority_ref"],
        "authority_generation_digest": provenance["authority_generation_digest"],
        "orchestration_provenance_digest": cycle_digest,
        "has_dialogue_source": "dialogue_source" in provenance,
    }


__all__ = [
    "STATUS_SCHEMA",
    "PrincipalOrchestrationNotFound",
    "PrincipalOrchestrationStatusError",
    "resolve_principal_orchestration",
]
