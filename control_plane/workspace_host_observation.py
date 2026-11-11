"""Original physical-host capture, not a current host/worker observation.

Consumes only the incumbent bounded Runtime claim/BEGIN source. It never calls
NativeCapacitySource, a probe, a host collector or a provider. The capture host
is the physical resource owner (which may be the controller), not an inferred
remote worker or a fleet population.
"""
from __future__ import annotations

import hashlib
import json

from control_plane.physical_capacity_capture import build_capture_payload
from control_plane.executive_host_capacity import MAX_TOTAL_OBSERVATION_WINDOW_MS
from control_plane.retained_capacity_projection import _stamp_ms
from control_plane.workspace_resource_capacity import project_capacity_source


def runtime_source_identity(runtime):
    """Existing database-file/schema identity; no OS telemetry acquisition."""
    from control_plane.executive_physical_admission import runtime_identity
    with runtime.store.read() as connection:
        value = runtime_identity(runtime.store, connection)
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def project_host_observation(snapshot, receipt, *, work_ref, root_job_id, job_id,
                             attempt_id, now_ms, expected_runtime_identity):
    # Reuse the accepted source receipt, exact tuple, claim and physical BEGIN
    # chain qualification. No current provider eligibility is inferred here.
    provider = project_capacity_source(snapshot, receipt, work_ref=work_ref,
        root_job_id=root_job_id, job_id=job_id, attempt_id=attempt_id, now_ms=now_ms)
    capture = snapshot.begin_event.payload.get("capacity_capture")
    fields = {"schema", "snapshot", "snapshot_sha256", "binding", "decision_time_ms", "capability", "can_place_work"}
    if (type(capture) is not dict or set(capture) != fields
            or capture["schema"] != "mastermind.physical_capacity_capture/v1"
            or capture["capability"] != "OBSERVATION_ONLY" or capture["can_place_work"] is not False
            or type(capture["binding"]) is not dict):
        raise ValueError("HOST_OBSERVATION_NOT_RETAINED")
    binding = capture["binding"]
    physical = snapshot.claim_event.payload["capacity_evidence"]["physical_capacity"]
    if (binding.get("host_ref") != physical["host_ref"]
            or binding.get("boot_ref") != physical["boot_ref"]
            or binding.get("operation_key") != f"finite-initial:{job_id}"
            or binding.get("request_fingerprint") != physical["request_fingerprint"]
            or binding.get("runtime_identity_sha256") != expected_runtime_identity):
        raise ValueError("HOST_OBSERVATION_BINDING_MISMATCH")
    begin_ms = _stamp_ms(snapshot.begin_event.created_at)
    decision_ms = capture["decision_time_ms"]
    # Event.created_at is the incumbent second-resolution clock. Preserve that
    # precision rather than inventing millisecond equality with capture time.
    if (type(decision_ms) is not int or not begin_ms <= decision_ms < begin_ms + 1000
            or decision_ms > now_ms):
        raise ValueError("HOST_OBSERVATION_CLOCK_MISMATCH")
    normalized = build_capture_payload(capture["snapshot"], expected_binding=binding,
        snapshot_sha256=capture["snapshot_sha256"], decision_time_ms=decision_ms,
        # This is a structural historical bound, not a new current freshness
        # promise or reconstructed original policy. Original mint checked its
        # actual policy before the Event committed. No read refreshes its time.
        max_age_ms=MAX_TOTAL_OBSERVATION_WINDOW_MS)
    if normalized != capture:
        raise ValueError("HOST_OBSERVATION_CAPTURE_INVALID")
    source = normalized["snapshot"]
    if source["observed_at_ms"] < source["total_observation_window_ms"]:
        raise ValueError("HOST_OBSERVATION_CLOCK_MISMATCH")
    result = {
        "schema": "mastermind.retained_host_observation.v1", "platform": "darwin",
        "observed_host_role": "PHYSICAL_RESOURCE_HOST", "observation_kind": "RETAINED_PHYSICAL_BEGIN",
        "root_job_id": root_job_id, "job_id": job_id, "attempt_id": attempt_id,
        "claim_event_id": provider["claim_event_id"], "begin_event_id": provider["begin_event_id"],
        "claim_recorded_at_ms": provider["claim_recorded_at_ms"], "begin_recorded_at_ms": begin_ms,
        "capture_decision_at_ms": decision_ms,
        "read_at_ms": now_ms, "age_ms": now_ms - source["observed_at_ms"],
        "oldest_observation_age_ms": now_ms - (source["observed_at_ms"] - source["total_observation_window_ms"]),
        "snapshot_sha256": capture["snapshot_sha256"], "snapshot": source,
        "source": {key: binding[key] for key in ("source_commit_sha", "source_helper_sha256", "policy_revision", "host_qualification_revision")},
        "capability": "OBSERVATION_ONLY", "admission_state": "NOT_EVALUATED", "can_place_work": False,
    }
    result["source"]["commit_sha"] = result["source"].pop("source_commit_sha")
    result["source"]["helper_sha256"] = result["source"].pop("source_helper_sha256")
    return result
