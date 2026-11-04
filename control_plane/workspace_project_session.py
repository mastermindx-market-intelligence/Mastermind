"""Observation of real Runtime materialization, independent of continuation grants.

The fixed Workspace reader must supply its current catalogue/permission bracket,
qualified immutable Macro source and original broker request owner. Nothing here
selects a provider, creates a session, opens a store or acquires Send authority.
"""
from __future__ import annotations

import dataclasses
import hashlib

from common.executive_workspace_contract import canonical, digest
from common import workspace_project_session_contract as wire
from control_plane import ceo_intent
from control_plane.executive_runtime import Runtime
from control_plane.operator_harness_contract import ProcessGenerationRef, SessionEpochRef
from control_plane.operator_materialization_receipt import operator_materialization_status

_MINT = object()


@dataclasses.dataclass(frozen=True)
class CreationEvidence:
    """Read-only same-root evidence, not a serializable permission capability."""
    selected: dict
    source: dict
    creation: dict
    runtime: Runtime = dataclasses.field(repr=False, compare=False)
    _mint: object = dataclasses.field(repr=False, compare=False)


def read_creation_evidence(runtime, *, selected, project_source):
    """Reconcile recognized immutable CEO creation through its original owner.

    project_source is obtained by the installed immutable Macro collector, never
    a public selector. This function deliberately does not infer its Git proof.
    The Workspace integration owns that source qualification and release fence.
    """
    selected = wire.selection(selected)
    source = wire.validate_project_source(project_source, selected)
    if type(runtime) is not Runtime:
        raise ValueError("source_unavailable")
    root = runtime.jobs.get_job(selected["root_job_id"])
    cycle = getattr(root, "orchestration_provenance", None)
    if (root is None or root.parent_job_id is not None or root.root_job_id != root.job_id
            or root.orchestration_role != "aggregation" or type(cycle) is not dict):
        raise ValueError("source_mismatch")
    command = cycle.get("command_id")
    if type(command) is not str or not command.startswith(ceo_intent.COMMAND_ID_PREFIX):
        raise ValueError("source_mismatch")
    intent_id = command[len(ceo_intent.COMMAND_ID_PREFIX):]
    # The existing owner verifies its recognized provenance, fingerprint,
    # immutable event and root identity instead of accepting a receipt echo.
    receipt = ceo_intent.resolve_intent(runtime, intent_id)
    if (receipt.get("job_id") != root.job_id or receipt.get("work_ref") != selected["work_ref"]
            or receipt.get("grounding", {}).get("macro_sha") != source["commit"]
            or receipt.get("accepted") is not True or receipt.get("dispatched") is not False):
        raise ValueError("source_mismatch")
    event = runtime.store.find_event_by_command_id(command)
    if type(event) is not dict or len(canonical(event)) > 131072:
        raise ValueError("source_unavailable")
    again = ceo_intent._receipt_from_event(runtime, event, intent_id=intent_id,
                                          fingerprint=receipt["fingerprint"])
    if again["job_id"] != root.job_id:
        raise ValueError("source_changed")
    return CreationEvidence(dict(selected), dict(source), {
        "intent_id": intent_id, "fingerprint": receipt["fingerprint"],
        "creation_event_sha256": digest(event),
    }, runtime, _MINT)


def _opaque(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def compose_project_session_association(evidence, *, epoch, generation,
                                        requested_profile_digest, broker_status):
    """Project an actual broker READ; callers cannot convert it to a send target.

    epoch/generation/profile are the original trusted materialization request,
    not browser fields. The adapter must recheck the same owner/status and its
    Workspace source/authorization bracket before releasing the returned body.
    """
    if type(evidence) is not CreationEvidence or evidence._mint is not _MINT:
        raise ValueError("source_unavailable")
    selected = wire.selection(evidence.selected)
    try:
        wire.validate_project_source(evidence.source, selected)
        if type(epoch) is not SessionEpochRef or type(generation) is not ProcessGenerationRef:
            raise ValueError("source_unavailable")
        if not wire._hex(requested_profile_digest):
            raise ValueError("source_unavailable")
        runtime = evidence.runtime
        actual_epoch, actual_generation = runtime.operator_harness.generation_refs(generation.process_generation_id)
        if actual_epoch != epoch or actual_generation != generation:
            return wire.unavailable(selected, "SOURCE_MISMATCH")
        attempt = runtime.attempts.get_attempt(epoch.attempt_id)
        job = runtime.jobs.get_job(attempt.job_id) if attempt else None
        if (attempt is None or job is None or job.root_job_id != selected["root_job_id"]
                or attempt.worker_id != epoch.worker_id or generation.worker_id != epoch.worker_id):
            return wire.unavailable(selected, "SOURCE_MISMATCH")
        status = operator_materialization_status(broker_status)
        if status.status == "CONFLICT":
            return wire.unavailable(selected, "MATERIALIZATION_CONFLICT")
        body = {"schema": wire.SCHEMA, "selection": selected, "availability": "AVAILABLE",
            "state": "PREPARING", "reason": "NOT_MATERIALIZED", "observational_only": True,
            "can_send": False, "continuation_target": None, "project_source": dict(evidence.source),
            "runtime_creation": dict(evidence.creation), "materialization": None}
        if status.status == "ABSENT":
            return wire.validate_body(body)
        receipt = status.receipt
        if (receipt.attempt_id != epoch.attempt_id or receipt.worker_id != epoch.worker_id
                or receipt.session_epoch_id != epoch.session_epoch_id
                or receipt.process_generation_id != generation.process_generation_id
                or receipt.generation_number != generation.generation_number
                or receipt.requested_profile_digest != requested_profile_digest):
            return wire.unavailable(selected, "SOURCE_MISMATCH")
        if status.status == "RECEIPT_CURRENT_IN_LIVE_BROKER":
            if (job.current_attempt_id != attempt.attempt_id
                    or runtime.operator_harness.current_writer_generation(epoch) != generation):
                return wire.unavailable(selected, "SOURCE_CHANGED")
            body.update(state="MATERIALIZED_OBSERVATION", reason=None)
        else:
            body.update(state="RECORDED_MATERIALIZATION", reason="BROKER_RESTARTED")
        body["materialization"] = {"receipt_sha256": receipt.receipt_digest,
            "recorded_at": receipt.created_at, "operation_kind": receipt.operation_kind,
            "epoch_sha256": _opaque(receipt.session_epoch_id),
            "process_generation_sha256": _opaque(receipt.process_generation_id),
            "provider_session_sha256": _opaque(receipt.provider_session_id),
            "generation_number": receipt.generation_number}
        return wire.validate_body(body)
    except Exception:
        return wire.unavailable(selected)
