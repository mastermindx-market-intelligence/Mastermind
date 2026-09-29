"""Coordination tasks through the existing work role and bounded Runtime reader.

No new model role, dispatcher, result store, or acceptance authority. This module
composes established grant, result-schema, acquisition and projection owners.
Artifact bytes must come from the existing authorized artifact reader, not a path
opened here. Source equality is not a permission grant or a claim of model quality.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from control_plane.chairman_cognition import ChairmanCognitionError
from control_plane.chairman_coordination import (
    evaluate_coordination_candidate,
    render_coordination_brief,
)
from control_plane.executive_orchestration_result import (
    OrchestrationResultError,
    canonical_bytes,
    parse_canonical_json,
)
from control_plane.executive_runtime import (
    Attempt, AttemptStatus, Job, JobStatus, Runtime,
)
from control_plane.executive_supervisor import (
    SupervisorError, validate_effective_grant, worker_result_schema,
)
from control_plane.fabric_result_projection import (
    FabricResultProjectionError, project_fabric_role_result,
)
from control_plane.wake_events import canonical_json_bytes

_ARTIFACT_LIMIT = 128 * 1024


def _artifact_path(value: Any) -> str:
    if (type(value) is not str or not value or len(value) > 1024
            or value != value.strip() or "\\" in value
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ChairmanCognitionError("invalid coordination artifact path")
    path = PurePosixPath(value)
    if (path.is_absolute() or str(path) != value or ".." in path.parts
            or ".git" in path.parts or value in {".", ".."}):
        raise ChairmanCognitionError("artifact path is not exact workspace-relative data")
    return value


def render_coordination_work_request(
    document: Mapping[str, Any], *, context: Mapping[str, Any],
    context_bundle: Mapping[str, Any], bundle_source_ref: str,
    job: Job, attempt: Attempt, authority_decision: Any, artifact_path: str,
) -> dict[str, Any]:
    """Build task input for an already-admitted ordinary work-role Attempt.

    The host obtains Job, Attempt and the same Job's authorization decision from
    current owners. The shared effective-grant validator is called unchanged.
    The result is task content, not an alternative BEGIN_TURN or native profile.
    In particular the fixed plan-only interactive lane is never widened here.
    """
    path = _artifact_path(artifact_path)
    if type(job) is not Job or type(attempt) is not Attempt:
        raise ChairmanCognitionError("current Runtime Job and Attempt are required")
    if job.orchestration_role != "work":
        raise ChairmanCognitionError("coordination artifact task requires existing work role")
    if (job.current_attempt_id != attempt.attempt_id or attempt.job_id != job.job_id
            or job.assigned_worker_id != attempt.worker_id
            or job.status is not JobStatus.RUNNING
            or attempt.status not in {AttemptStatus.CLAIMED, AttemptStatus.RUNNING}):
        raise ChairmanCognitionError("work task does not match the current active Attempt")
    if (not job.root_job_id or not job.plan_attempt_id or not job.plan_digest
            or not job.plan_step_id or job.repair_round != 0):
        raise ChairmanCognitionError("work task lacks accepted orchestration lineage")
    try:
        grant = validate_effective_grant(job, attempt, authority_decision)
    except (SupervisorError, AttributeError, TypeError, ValueError) as exc:
        raise ChairmanCognitionError("work effective grant is not current and exact") from exc
    if (grant is None or "WRITE_BRANCH" not in grant["authorities"]
            or path not in grant["write_paths"]):
        raise ChairmanCognitionError("decision artifact is not an exact granted write")
    brief = render_coordination_brief(
        document, context=context, context_bundle=context_bundle,
        bundle_source_ref=bundle_source_ref,
    )
    result_schema = worker_result_schema(
        job_id=job.job_id, run_id=attempt.attempt_id, worker_id=attempt.worker_id,
        effective_grant_digest=attempt.effective_grant_digest,
        orchestration_role=job.orchestration_role, root_job_id=job.root_job_id,
    )
    # Keep the original complete work-result schema. The coordinator candidate
    # lives in an ordinary granted artifact, never in place of the role envelope.
    task = {
        "coordination_brief": brief,
        "decision_artifact_path": path,
        "work_lineage": {
            "root_job_id": job.root_job_id, "plan_attempt_id": job.plan_attempt_id,
            "plan_digest": job.plan_digest, "plan_step_id": job.plan_step_id,
            "repair_round": job.repair_round,
        },
        "result_schema": result_schema,
    }
    instruction = (
        "Perform the scoped coordination judgment described in the evidence below. "
        "Do not replace your admitted work role, effective grant, or final role_result "
        "with a coordinator-only JSON object. Write the candidate as one canonical "
        "UTF-8 JSON artifact at the exact declared granted path. Include that path "
        "and SHA-256 of the file bytes in the ordinary work role_result.artifacts. "
        "Keep all existing result identity and plan lineage. Return the original "
        "work-result envelope, not the candidate artifact as your final result. "
        "The candidate is a proposal: do not execute its next_step. It grants no "
        "additional authority and must not be used to bypass a hold or denial. "
        "Do not self-attest tests or approval; preserve the supervisor's validation "
        "and independent review boundaries. If the assignment cannot produce a "
        "valid evidence-based proposal, report that gap under your existing result "
        "contract rather than inventing progress.\n\n"
    )
    prompt = instruction + json.dumps(task, sort_keys=True, ensure_ascii=True, allow_nan=False)
    if len(prompt.encode("utf-8")) > 768 * 1024:
        raise ChairmanCognitionError("work prompt exceeds bound; recompile context")
    out = {
        "schema": "mastermind.chairman_coordination_work_request.v1",
        "job_id": job.job_id, "attempt_id": attempt.attempt_id,
        "root_job_id": job.root_job_id, "effective_grant_digest": attempt.effective_grant_digest,
        "artifact_path": path, "brief_digest": brief["brief_digest"],
        "prompt": prompt, "result_schema": result_schema,
        "execution_authority_granted": False,
    }
    out["request_digest"] = hashlib.sha256(canonical_json_bytes(out)).hexdigest()
    return out


def read_coordination_work_return(
    document: Mapping[str, Any], *, context: Mapping[str, Any], runtime: Runtime,
    root_job_id: str, job_id: str, expected_attempt_id: str,
    expected_result_envelope_digest: str, artifact_path: str, artifact_bytes: bytes,
) -> dict[str, Any]:
    """Acquire one exact completed result through the bounded Runtime owner.

    A caller-supplied initialized write Runtime does not qualify: the existing
    read owner will produce UNKNOWN without its trusted namespace binding and
    the shared projector refuses that receipt. There is no raw SQLite fallback,
    latest-result search, reacquisition retry, or filesystem artifact read here.
    """
    path = _artifact_path(artifact_path)
    if type(artifact_bytes) is not bytes or not 0 < len(artifact_bytes) <= _ARTIFACT_LIMIT:
        raise ChairmanCognitionError("coordination artifact is empty, mutable, or over budget")
    if type(runtime) is not Runtime:
        raise ChairmanCognitionError("existing Runtime reader is required")
    try:
        with runtime.observe_bounded_read() as observation:
            snapshot = observation.read_role_result_bounded(
                root_job_id, job_id, expected_attempt_id=expected_attempt_id,
                expected_result_envelope_digest=expected_result_envelope_digest,
            )
        # Read only after physical observation close; reuse its full validator.
        projection = project_fabric_role_result(snapshot, observation.receipt).complete
    except Exception as exc:
        raise ChairmanCognitionError("exact current Runtime result is unavailable") from exc
    if (not isinstance(context, Mapping)
            or snapshot.root_metadata.work_ref != context.get("project_ref")):
        raise ChairmanCognitionError("result root does not belong to this project")
    if projection["role"] != "work":
        raise ChairmanCognitionError("result is not an admitted work-role artifact")
    if snapshot.completion.result_envelope["errors"]:
        raise ChairmanCognitionError("work result reports unresolved errors")
    artifacts = projection["content"]["role_result"]["artifacts"]
    selected = [item for item in artifacts if item["path"] == path]
    if len(selected) != 1:
        raise ChairmanCognitionError("the exact decision artifact is absent or ambiguous")
    artifact_digest = hashlib.sha256(artifact_bytes).hexdigest()
    if selected[0]["digest"] != artifact_digest:
        raise ChairmanCognitionError("decision artifact bytes differ from the canonical result")
    try:
        candidate = parse_canonical_json(artifact_bytes.decode("utf-8"))
    except (OrchestrationResultError, UnicodeError, TypeError, ValueError, RecursionError) as exc:
        raise ChairmanCognitionError("decision artifact is not complete canonical JSON") from exc
    review = evaluate_coordination_candidate(document, context=context, candidate=candidate)
    review["runtime_result_evidence"] = {
        **projection["selection"], "role": projection["role"],
        "role_result_digest": projection["role_result_digest"],
        "source_state": projection["generation"]["state"],
        "source_identity": projection["generation"]["source_identity"],
        "artifact_path": path, "artifact_digest": artifact_digest,
        "artifact_byte_length": len(artifact_bytes),
        "runtime_acceptance": projection["acceptance"],
        "summary_used": False,
    }
    del review["packet_digest"]
    review["packet_digest"] = hashlib.sha256(canonical_json_bytes(review)).hexdigest()
    return review



def read_coordination_work_request(
    document: Mapping[str, Any], *, context: Mapping[str, Any],
    context_bundle: Mapping[str, Any], bundle_source_ref: str,
    runtime: Runtime, root_job_id: str, job_id: str, expected_attempt_id: str,
    authority_decision: Any, artifact_path: str,
) -> dict[str, Any]:
    """Bind task content to an existing exact current work-role assignment.

    Reuse the installed source join's bounded root observation and provenance
    validator rather than inventing another root/project mapping. The policy
    owner supplies its authorization decision; this function neither loads new
    authority nor claims that the read fence lasts until a later dispatch.
    """
    from control_plane.workspace_source_join import _root_evidence

    if type(runtime) is not Runtime or not isinstance(context, Mapping):
        raise ChairmanCognitionError("current bound Runtime and project context are required")
    for identity in (root_job_id, job_id, expected_attempt_id):
        if type(identity) is not str or not identity or identity != identity.strip():
            raise ChairmanCognitionError("exact Runtime selection is required")
    try:
        jobs, attempts, provenance, receipt = _root_evidence(runtime, root_job_id)
    except Exception as exc:
        raise ChairmanCognitionError("current root observation is unavailable") from exc
    root_source = provenance.get(root_job_id)
    if (not isinstance(root_source, Mapping)
            or root_source.get("workstream") != context.get("project_ref")):
        raise ChairmanCognitionError("task root does not belong to this project")
    selected_jobs = [job for job in jobs if job.job_id == job_id]
    selected_attempts = [attempt for attempt in attempts
                         if attempt.attempt_id == expected_attempt_id and attempt.job_id == job_id]
    if len(selected_jobs) != 1 or len(selected_attempts) != 1:
        raise ChairmanCognitionError("exact work Job and Attempt are not in the selected root")
    result = render_coordination_work_request(
        document, context=context, context_bundle=context_bundle,
        bundle_source_ref=bundle_source_ref, job=selected_jobs[0],
        attempt=selected_attempts[0], authority_decision=authority_decision,
        artifact_path=artifact_path,
    )
    result["project_ref"] = context["project_ref"]
    result["source_generation"] = dict(receipt)
    del result["request_digest"]
    result["request_digest"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    return result
