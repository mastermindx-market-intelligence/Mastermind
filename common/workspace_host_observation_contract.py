"""Closed selected-work recorded host READ; no host selector or live clock."""
import hashlib
import json
import re
from common import workspace_resource_capacity_contract as capacity
from common.executive_workspace_contract import canonical

FRAME_SCHEMA = "mastermind.workspace_host_observation_read.v1"
BODY_SCHEMA = "mastermind.workspace_host_observation_result.v1"
OBSERVATION_SCHEMA = "mastermind.workspace_host_observation_source.v1"
OPERATION = "host_observation"
MAX_RESPONSE_BYTES = 16_384
selection = capacity.selection
REASONS = capacity.REASONS

METRICS = ("physical_memory_bytes", "vm_page_size_bytes", "vm_free_pages", "vm_inactive_pages", "vm_speculative_pages",
           "vm_compressed_pages", "swap_total_bytes", "swap_used_bytes", "pool_total_bytes", "pool_free_bytes")


def _snapshot(value):
    fields = {"schema", "host_ref", "boot_ref", "capacity_pool_ref", "observed_at_ms", "sample_window_ms",
        "total_observation_window_ms", "hp0_sha256", "hp0_observed_at_ms", "hp0_sample_window_ms", "logical_cpu_count",
        "load1_milli", "load_ratio_milli", "hp0_telemetry_status", "telemetry_status", "unknown_fields", *METRICS}
    if not capacity._keys(value, fields) or value["schema"] != "mastermind.host_capacity_snapshot/v1":
        raise ValueError("invalid_host_observation")
    for key, prefix in (("host_ref", "host-"), ("boot_ref", "boot-"), ("capacity_pool_ref", "capacity-pool-")):
        if type(value[key]) is not str or re.fullmatch(prefix + r"[0-9a-f]{64}", value[key]) is None:
            raise ValueError("invalid_host_observation")
    if type(value["hp0_sha256"]) is not str or capacity._HASH.fullmatch(value["hp0_sha256"]) is None:
        raise ValueError("invalid_host_observation")
    for key in ("observed_at_ms", "sample_window_ms", "total_observation_window_ms", "hp0_observed_at_ms", "hp0_sample_window_ms", "logical_cpu_count"):
        if not capacity._natural(value[key], 1): raise ValueError("invalid_host_observation")
    if (value["sample_window_ms"] > 10_000 or value["hp0_sample_window_ms"] > 5000
            or value["total_observation_window_ms"] > 3_600_000
            or value["total_observation_window_ms"] < value["sample_window_ms"]
            or value["hp0_observed_at_ms"] > value["observed_at_ms"]
            or value["hp0_observed_at_ms"] < value["hp0_sample_window_ms"]
            or value["total_observation_window_ms"] != value["observed_at_ms"] - value["hp0_observed_at_ms"] + value["hp0_sample_window_ms"]
            or value["logical_cpu_count"] > 4096
            or not capacity._natural(value["load1_milli"]) or not capacity._natural(value["load_ratio_milli"])
            or value["load_ratio_milli"] != value["load1_milli"] // value["logical_cpu_count"]
            or value["hp0_telemetry_status"] not in ("COMPLETE", "PARTIAL")):
        raise ValueError("invalid_host_observation")
    unknown = sorted(key for key in METRICS if value[key] is None)
    if (type(value["unknown_fields"]) is not list or value["unknown_fields"] != unknown
            or value["telemetry_status"] != ("PARTIAL" if unknown else "COMPLETE")):
        raise ValueError("invalid_host_observation")
    for key in METRICS:
        if value[key] is not None and not capacity._natural(value[key], 1 if key in ("physical_memory_bytes", "vm_page_size_bytes") else 0):
            raise ValueError("invalid_host_observation")
    for low, high in (("swap_used_bytes", "swap_total_bytes"), ("pool_free_bytes", "pool_total_bytes")):
        if value[low] is not None and value[high] is not None and value[low] > value[high]:
            raise ValueError("invalid_host_observation")
    return value


def validate_frame(frame):
    if (type(frame) is not dict or frame.get("schema") != FRAME_SCHEMA or frame.get("operation") != OPERATION):
        raise ValueError("invalid_input")
    capacity.validate_frame({**frame, "schema": capacity.FRAME_SCHEMA, "operation": capacity.OPERATION})
    return frame


def unavailable(selected, reason):
    if reason not in REASONS:
        raise ValueError("invalid_input")
    return {"ok": True, "result": {"schema": BODY_SCHEMA, "selection": selection(selected),
        "availability": "UNAVAILABLE", "reason_codes": [reason], "observation": None, "source_observation": None}}


def validate_observation(value, selected):
    fields = {"schema", "platform", "observed_host_role", "observation_kind", "root_job_id", "job_id", "attempt_id",
        "claim_event_id", "begin_event_id", "claim_recorded_at_ms", "begin_recorded_at_ms", "capture_decision_at_ms", "read_at_ms", "age_ms",
        "oldest_observation_age_ms", "snapshot_sha256", "snapshot", "source", "capability", "admission_state", "can_place_work"}
    if (not capacity._keys(value, fields) or value["schema"] != "mastermind.retained_host_observation.v1"
            or value["platform"] != "darwin" or value["observed_host_role"] != "PHYSICAL_RESOURCE_HOST"
            or value["observation_kind"] != "RETAINED_PHYSICAL_BEGIN"
            or value["capability"] != "OBSERVATION_ONLY" or value["admission_state"] != "NOT_EVALUATED"
            or value["can_place_work"] is not False or any(value[k] != selected[k] for k in ("root_job_id", "job_id", "attempt_id"))):
        raise ValueError("invalid_host_observation")
    for key in ("claim_event_id", "begin_event_id", "claim_recorded_at_ms", "begin_recorded_at_ms", "capture_decision_at_ms", "read_at_ms"):
        if not capacity._natural(value[key], 1):
            raise ValueError("invalid_host_observation")
    if any(value[k] > 8_640_000_000_000_000 for k in ("claim_recorded_at_ms", "begin_recorded_at_ms", "read_at_ms")):
        raise ValueError("invalid_host_observation")
    raw = value["snapshot"]
    snapshot = _snapshot(raw)
    for metric in snapshot.values():
        if type(metric) is int and not capacity._natural(metric):
            raise ValueError("invalid_host_observation")
    if (snapshot["observed_at_ms"] < snapshot["total_observation_window_ms"]
            or not value["begin_recorded_at_ms"] <= value["claim_recorded_at_ms"] <= value["read_at_ms"]
            or not snapshot["observed_at_ms"] <= value["capture_decision_at_ms"] <= value["read_at_ms"]
            or not value["begin_recorded_at_ms"] <= value["capture_decision_at_ms"] < value["begin_recorded_at_ms"] + 1000
            or not capacity._natural(value["age_ms"]) or value["age_ms"] != value["read_at_ms"] - snapshot["observed_at_ms"]
            or not capacity._natural(value["oldest_observation_age_ms"])
            or value["oldest_observation_age_ms"] != value["age_ms"] + snapshot["total_observation_window_ms"]
            or value["snapshot_sha256"] != hashlib.sha256((json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")).hexdigest()):
        raise ValueError("invalid_host_observation")
    source = value["source"]
    if (not capacity._keys(source, {"commit_sha", "helper_sha256", "policy_revision", "host_qualification_revision"})
            or type(source["commit_sha"]) is not str or re.fullmatch(r"[0-9a-f]{40}", source["commit_sha"]) is None
            or type(source["helper_sha256"]) is not str or re.fullmatch(r"[0-9a-f]{64}", source["helper_sha256"]) is None
            or any(type(source[k]) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", source[k]) is None
                   for k in ("policy_revision", "host_qualification_revision"))):
        raise ValueError("invalid_host_observation")
    return value


def validate_result(body, selected):
    selected = selection(selected)
    if (not capacity._keys(body, {"schema", "selection", "availability", "reason_codes", "observation", "source_observation"})
            or body["schema"] != BODY_SCHEMA or body["selection"] != selected):
        raise ValueError("invalid_host_observation")
    if body["availability"] == "UNAVAILABLE":
        if (type(body["reason_codes"]) is not list or len(body["reason_codes"]) != 1 or body["reason_codes"][0] not in REASONS
                or body["observation"] is not None or body["source_observation"] is not None):
            raise ValueError("invalid_host_observation")
        return body
    if body["availability"] != "AVAILABLE" or body["reason_codes"] != []:
        raise ValueError("invalid_host_observation")
    validate_observation(body["observation"], selected)
    # Reuse the incumbent closed source bracket grammar without a provider row.
    bracket = body["source_observation"]
    if (not capacity._keys(bracket, {"schema", "state", "selection", "control_room", "runtime"})
            or bracket["schema"] != OBSERVATION_SCHEMA or bracket["state"] != "SAME" or bracket["selection"] != selected):
        raise ValueError("invalid_host_observation")
    ccr, runtime = bracket["control_room"], bracket["runtime"]
    if (not capacity._keys(ccr, {"instance_before", "instance_after", "publication_before", "publication_after", "document_digest", "source_validity_digest", "cache_currentness_digest"})
            or type(ccr["instance_before"]) is not str or not 1 <= len(ccr["instance_before"]) <= 256
            or ccr["instance_after"] != ccr["instance_before"] or not capacity._natural(ccr["publication_before"], 1)
            or type(ccr["publication_after"]) is not int or ccr["publication_after"] != ccr["publication_before"]
            or any(type(ccr[k]) is not str or capacity._HASH.fullmatch(ccr[k]) is None for k in ("document_digest", "source_validity_digest", "cache_currentness_digest"))
            or not capacity._keys(runtime, {"schema", "state", "source_identity", "before", "after"})
            or runtime["schema"] != "mastermind.runtime_read_observation.v1" or runtime["state"] != "SAME"
            or type(runtime["source_identity"]) is not str or re.fullmatch(r"[0-9a-f]{32}", runtime["source_identity"]) is None
            or not capacity._natural(runtime["before"]) or type(runtime["after"]) is not int or runtime["after"] != runtime["before"]):
        raise ValueError("invalid_host_observation")
    if len(canonical({"ok": True, "result": body})) + 1 > MAX_RESPONSE_BYTES:
        raise ValueError("invalid_host_observation")
    return body
