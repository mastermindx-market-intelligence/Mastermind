"""One fixed selected-work historical capacity READ, never host discovery."""
import re
from datetime import datetime
from common import executive_workspace_activity_contract as activity
from common.executive_workspace_contract import canonical

FRAME_SCHEMA = "mastermind.workspace_resource_capacity_read.v1"
BODY_SCHEMA = "mastermind.workspace_resource_capacity_result.v1"
OBSERVATION_SCHEMA = "mastermind.workspace_resource_capacity_observation.v1"
OPERATION = "resource_capacity"
MAX_RESPONSE_BYTES = 16_384
REASONS = frozenset({"SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "OVER_BUDGET", "RESPONSE_OVER_BUDGET"})
selection = activity.selection
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_HASH = re.compile(r"[0-9a-f]{64}")


def validate_frame(frame):
    if (type(frame) is not dict or frame.get("schema") != FRAME_SCHEMA
            or frame.get("operation") != OPERATION):
        raise ValueError("invalid_input")
    activity.validate_frame({**frame, "schema": activity.FRAME_SCHEMA, "operation": activity.OPERATION})
    return frame


def unavailable(selected, reason):
    if reason not in REASONS:
        raise ValueError("invalid_input")
    return {"ok": True, "result": {"schema": BODY_SCHEMA, "selection": selection(selected),
        "availability": "UNAVAILABLE", "reason_codes": [reason], "provider_capacity": None,
        "source_observation": None}}


def _keys(value, keys):
    return type(value) is dict and set(value) == set(keys)


def _natural(value, minimum=0):
    return type(value) is int and minimum <= value <= 2**53 - 1


def _time(value):
    if type(value) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value) is None:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def validate_provider(value, selected):
    keys = {"schema", "root_job_id", "job_id", "attempt_id", "claim_event_id", "begin_event_id",
        "claim_recorded_at_ms", "observed_at_ms", "age_ms", "source_snapshot_sha256", "source_release_commit",
        "host_ref", "boot_ref", "provider", "provider_enabled", "realm_auth", "provider_health", "cooling",
        "quota_horizons", "current_eligibility", "can_place_work", "observation_kind"}
    if (not _keys(value, keys) or value["schema"] != "mastermind.retained_provider_capacity.v1"
            or any(value[k] != selected[k] for k in ("root_job_id", "job_id", "attempt_id"))
            or any(not _natural(value[k], 1) for k in ("claim_event_id", "begin_event_id", "claim_recorded_at_ms", "observed_at_ms"))
            or value["observed_at_ms"] > 8_640_000_000_000_000 or not _natural(value["age_ms"])
            or not _natural(value["observed_at_ms"] + value["age_ms"])
            or value["claim_recorded_at_ms"] > value["observed_at_ms"] + value["age_ms"]
            or type(value["source_snapshot_sha256"]) is not str or _HASH.fullmatch(value["source_snapshot_sha256"]) is None
            or type(value["source_release_commit"]) is not str or re.fullmatch(r"[0-9a-f]{40}", value["source_release_commit"]) is None
            or any(type(value[k]) is not str or re.fullmatch(prefix + r"[0-9a-f]{64}", value[k]) is None
                   for k, prefix in (("host_ref", "host-"), ("boot_ref", "boot-")))
            or value["provider"] != "minimax" or value["provider_enabled"] is not None and type(value["provider_enabled"]) is not bool
            or value["current_eligibility"] != "NOT_EVALUATED" or value["can_place_work"] is not False
            or value["observation_kind"] != "RETAINED_CLAIM"):
        raise ValueError("invalid_capacity_response")
    auth, health, cooling = value["realm_auth"], value["provider_health"], value["cooling"]
    if (not _keys(auth, {"state", "source_quality"}) or auth["state"] not in ("unknown", "authenticated", "unauthenticated")
            or auth["source_quality"] not in ("unknown", "native_provider")
            or not _keys(health, {"state", "error_class"}) or health["state"] not in ("unknown", "healthy", "unhealthy")
            or health["error_class"] not in (None, "auth", "quota", "transport", "provider")
            or not _keys(cooling, {"active", "kind", "reset_at"}) or cooling["active"] is not None and type(cooling["active"]) is not bool
            or cooling["kind"] not in (None, "rate_limit", "provider", "account")
            or cooling["reset_at"] is not None and not _time(cooling["reset_at"])
            or type(value["quota_horizons"]) is not list or len(value["quota_horizons"]) > 8):
        raise ValueError("invalid_capacity_response")
    names = set()
    for row in value["quota_horizons"]:
        if (not _keys(row, {"name", "remaining", "limit", "reset_at"}) or type(row["name"]) is not str
                or _ID.fullmatch(row["name"]) is None or row["name"] in names
                or not _natural(row["remaining"]) or not _natural(row["limit"], 1)
                or row["remaining"] > row["limit"] or not _time(row["reset_at"])):
            raise ValueError("invalid_capacity_response")
        names.add(row["name"])
    return value


def validate_result(body, selected):
    selected = selection(selected)
    if (not _keys(body, {"schema", "selection", "availability", "reason_codes", "provider_capacity", "source_observation"})
            or body["schema"] != BODY_SCHEMA or body["selection"] != selected):
        raise ValueError("invalid_capacity_response")
    if body["availability"] == "UNAVAILABLE":
        reasons = body["reason_codes"]
        if type(reasons) is not list or len(reasons) != 1 or reasons[0] not in REASONS or body != unavailable(selected, reasons[0])["result"]:
            raise ValueError("invalid_capacity_response")
        return body
    if body["availability"] != "AVAILABLE" or body["reason_codes"] != []:
        raise ValueError("invalid_capacity_response")
    validate_provider(body["provider_capacity"], selected)
    observation = body["source_observation"]
    if (not _keys(observation, {"schema", "state", "selection", "control_room", "runtime"})
            or observation["schema"] != OBSERVATION_SCHEMA or observation["state"] != "SAME" or observation["selection"] != selected):
        raise ValueError("invalid_capacity_response")
    ccr, runtime = observation["control_room"], observation["runtime"]
    if (not _keys(ccr, {"instance_before", "instance_after", "publication_before", "publication_after", "document_digest", "source_validity_digest", "cache_currentness_digest"})
            or type(ccr["instance_before"]) is not str or not 1 <= len(ccr["instance_before"]) <= 256
            or ccr["instance_after"] != ccr["instance_before"] or not _natural(ccr["publication_before"], 1)
            or type(ccr["publication_after"]) is not int or ccr["publication_after"] != ccr["publication_before"]
            or any(type(ccr[k]) is not str or _HASH.fullmatch(ccr[k]) is None for k in ("document_digest", "source_validity_digest", "cache_currentness_digest"))
            or not _keys(runtime, {"schema", "state", "source_identity", "before", "after"})
            or runtime["schema"] != "mastermind.runtime_read_observation.v1" or runtime["state"] != "SAME"
            or type(runtime["source_identity"]) is not str or re.fullmatch(r"[0-9a-f]{32}", runtime["source_identity"]) is None
            or not _natural(runtime["before"]) or type(runtime["after"]) is not int or runtime["after"] != runtime["before"]):
        raise ValueError("invalid_capacity_response")
    if len(canonical({"ok": True, "result": body})) + 1 > MAX_RESPONSE_BYTES:
        raise ValueError("invalid_capacity_response")
    return body
