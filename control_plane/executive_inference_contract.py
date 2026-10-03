"""Closed VPS service vocabulary. No lifecycle, credential, or provider owner."""
import copy
import re
from collections.abc import Mapping

from control_plane import ceo_request, executive_service_principal as esp

PRINCIPAL_ID = "svc-vps-inference"
TOOLS = ("submit_service_intent", "service_intent_status", "executive_fabric")
MAX_RESULT_BYTES = 256 * 1024


def normalize_request(value):
    if not isinstance(value, Mapping) or set(value) != {"operation_key", "objective"}:
        raise ValueError("bounded service request requires operation_key and objective only")
    normalized = ceo_request.normalize_high_level_request(dict(
        value, department="executive-infrastructure", priority=3,
        execution_profile="research_only", attempt_limit=1,
    ))
    return {key: normalized[key] for key in ("operation_key", "objective")}


def intent_id(operation_key):
    request = normalize_request(dict(operation_key=operation_key, objective="Identity validation"))
    return esp.service_intent_id(esp.service_principal(PRINCIPAL_ID), request["operation_key"])


def derive(request, grounding):
    request = normalize_request(request)
    return esp.derive_intent(esp.service_principal(PRINCIPAL_ID), dict(
        request, department="executive-infrastructure", priority=3,
        execution_profile="research_only", attempt_limit=1, grounding=grounding,
    ))


def validate_receipt(receipt, operation_key):
    """Refuse foreign/malformed receipts before a consumer treats them as admission."""
    from common.executive_workspace_contract import _check_job_id
    from control_plane import ceo_intent, executive_ceo_ingress as ingress
    from control_plane.executive_runtime import JobStatus
    keys = {"schema", "intent_id", "fingerprint", "job_id", "status", "accepted", "duplicate",
            "dispatched", "authority", "grounding", "created_at_ms"}
    def digest(v): return isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v) is not None
    if (not isinstance(receipt, dict) or set(receipt) != keys
            or receipt["schema"] != ceo_intent.RECEIPT_SCHEMA_SERVICE
            or receipt["intent_id"] != intent_id(operation_key)
            or not _check_job_id(receipt["job_id"]) or not digest(receipt["fingerprint"])
            or receipt["accepted"] is not True or receipt["dispatched"] is not False
            or type(receipt["duplicate"]) is not bool
            or receipt["status"] not in {s.value for s in JobStatus}
            or type(receipt["created_at_ms"]) is not int or receipt["created_at_ms"] < 0
            or ingress._coerce_grounding_shape(receipt["grounding"]) is None):
        raise ValueError("service receipt unavailable")
    authority = receipt["authority"]
    if (not isinstance(authority, dict)
            or set(authority) != {"requested", "policy_sha256", "authority_level"}
            or authority["requested"] != ["READ", "RESEARCH"]
            or authority["authority_level"] != "A0" or not digest(authority["policy_sha256"])):
        raise ValueError("service receipt authority refused")
    return receipt


def _same_generation(value):
    return (isinstance(value, dict)
            and set(value) == {"schema", "state", "source_identity", "before", "after"}
            and value["schema"] == "mastermind.runtime_read_observation.v1"
            and value["state"] == "SAME"
            and isinstance(value["source_identity"], str)
            and re.fullmatch(r"[0-9a-f]{32}", value["source_identity"]) is not None
            and type(value["before"]) is int and value["before"] >= 0
            and type(value["after"]) is int and value["after"] == value["before"])


def validate_result(value, selection):
    """Accept only the exact complete terminal aggregation projection, not acceptance."""
    selection = validate_selection(selection)
    outer_keys = {"schema", "tool", "ok", "server_version", "mode", "generated_at",
                  "grounding", "data", "degraded", "bounded", "error"}
    if (not isinstance(value, dict) or set(value) != outer_keys
            or value["schema"] != "mastermind.executive_mcp_result.v1"
            or value["tool"] != "executive_fabric" or value["ok"] is not True
            or value["error"] is not None or value["bounded"] != [] or value["degraded"] != []):
        raise ValueError("Fabric result unavailable")
    data = value["data"]
    keys = {"schema", "selection", "role", "execution_status", "acceptance", "role_result_digest",
            "generation", "availability", "content_complete", "review", "counts", "content", "omitted"}
    if (not isinstance(data, dict) or set(data) != keys
            or data["schema"] != "mastermind.fabric_role_result_view.v1"
            or data["selection"] != selection or data["role"] != "aggregation"
            or data["acceptance"] != "NOT_PROJECTED" or data["review"] is not None
            or data["availability"] != "AVAILABLE" or data["content_complete"] is not True
            or data["execution_status"] != "COMPLETED" or data["omitted"] != []
            or not _same_generation(data["generation"])
            or not isinstance(data["role_result_digest"], str)
            or re.fullmatch(r"[0-9a-f]{64}", data["role_result_digest"]) is None
            or not isinstance(data["content"], dict)
            or set(data["content"]) != {"role_result", "summary", "next_actions"}):
        raise ValueError("exact complete Fabric result unavailable")
    content, counts = data["content"], data["counts"]
    from control_plane.executive_orchestration_result import canonical_bytes, canonical_digest
    if (not isinstance(content["role_result"], dict)
            or not isinstance(content["summary"], str)
            or not isinstance(content["next_actions"], list)
            or any(not isinstance(item, str) for item in content["next_actions"])
            or not isinstance(counts, dict) or set(counts) != {"findings", "next_actions"}
            or counts["findings"] is not None or type(counts["next_actions"]) is not int
            or counts["next_actions"] != len(content["next_actions"])
            or canonical_digest(content["role_result"]) != data["role_result_digest"]):
        raise ValueError("Fabric result content disagrees with projection")
    if len(canonical_bytes(data)) > MAX_RESULT_BYTES:
        raise ValueError("Fabric result exceeds bounded response")
    # Preserve the closed projector document, including NOT_PROJECTED. Completion
    # never becomes acceptance, and no arbitrary response metadata is propagated.
    return copy.deepcopy(data)


def validate_submission_receipt(receipt, request):
    receipt = validate_receipt(receipt, request["operation_key"])
    if receipt["fingerprint"] != esp.fingerprint(derive(request, receipt["grounding"])):
        raise ValueError("service receipt does not match submitted request")
    return receipt


def validate_selection(selection):
    from common.executive_workspace_contract import _check_job_id, _check_attempt_id, _check_envelope_digest
    if (not isinstance(selection, Mapping)
            or set(selection) != {"root_job_id", "job_id", "attempt_id", "result_envelope_digest"}
            or selection["job_id"] != selection["root_job_id"]
            or not _check_job_id(selection["root_job_id"]) or not _check_job_id(selection["job_id"])
            or not _check_attempt_id(selection["attempt_id"])
            or not _check_envelope_digest(selection["result_envelope_digest"])):
        raise ValueError("exact Fabric result selection required")
    return dict(selection)


def validate_terminal_result_ref(value, receipt, operation_key):
    """Pure operation-bound navigation check; UNVALIDATED is not result validation."""
    receipt = validate_receipt(receipt, operation_key)
    if value is None:
        return None
    if (not isinstance(value, dict)
            or set(value) != {"root_job_id", "job_id", "attempt_id", "result_envelope_digest",
                              "orchestration_role", "validation"}
            or value["orchestration_role"] != "aggregation" or value["validation"] != "UNVALIDATED"):
        raise ValueError("terminal result reference unavailable")
    selection = validate_selection({key: value[key] for key in
        ("root_job_id", "job_id", "attempt_id", "result_envelope_digest")})
    if selection["root_job_id"] != receipt["job_id"]:
        raise ValueError("terminal result reference belongs to another operation")
    return dict(value)


def validate_status(value, operation_key):
    """Service status wraps the unchanged sink receipt and an optional locator."""
    if not isinstance(value, dict) or set(value) not in (
            {"receipt"}, {"receipt", "terminal_result_ref"}):
        raise ValueError("service status unavailable")
    receipt = validate_receipt(value["receipt"], operation_key)
    return {"receipt": receipt, "terminal_result_ref": validate_terminal_result_ref(
        value.get("terminal_result_ref"), receipt, operation_key)}


def terminal_result_ref_from_index(index, receipt, operation_key):
    """Pure helper for a future host resolver over the existing Fabric index.

    An optional admitted orchestration lane may call
    compose_fabric_result_reference_index on the canonical bounded root observation.
    Routine service inference uses the direct Executive Job result instead. This
    helper performs no Runtime acquisition.
    """
    from control_plane.fabric_job_view import RESULT_REFERENCE_INDEX_SCHEMA
    receipt = validate_receipt(receipt, operation_key)
    keys = {"schema", "root_job_id", "snapshot_digest", "generation", "availability",
            "refs", "absent_job_ids", "omitted_job_ids", "truncated"}
    if (not isinstance(index, dict) or set(index) != keys
            or index["schema"] != RESULT_REFERENCE_INDEX_SCHEMA
            or index["root_job_id"] != receipt["job_id"]
            or index["availability"] != "AVAILABLE" or not _same_generation(index["generation"])
            or index["truncated"] is not False or index["omitted_job_ids"] != []
            or not isinstance(index["snapshot_digest"], str)
            or re.fullmatch(r"[0-9a-f]{64}", index["snapshot_digest"]) is None
            or not isinstance(index["refs"], list)):
        raise ValueError("canonical terminal reference index unavailable")
    roots = [ref for ref in index["refs"] if isinstance(ref, dict)
             and ref.get("job_id") == receipt["job_id"]]
    if len(roots) > 1:
        raise ValueError("ambiguous terminal reference")
    return validate_terminal_result_ref(roots[0] if roots else None, receipt, operation_key)
