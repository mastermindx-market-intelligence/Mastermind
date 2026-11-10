"""Closed passive read over the existing Workspace principal and exact result.

This operation does not widen the frozen result wire contract or authorize a
native send. Runtime owns retained original evidence; delivery is not acceptance.
"""
from __future__ import annotations

import re
from common.executive_workspace_contract import (
    FRAME_SCHEMA_V2, RESULT_OBSERVATION_SCHEMA, MAX_REQUEST_BYTES, canonical, v2_selection,
    validate_v2_frame,
)

FRAME_SCHEMA = "mastermind.workspace_execution_return_read.v1"
BODY_SCHEMA = "mastermind.workspace_execution_return.v1"
OPERATION = "execution_return"
PATH = "/workspace/execution-return/current"
MAX_RESPONSE_BYTES = 32_768
REASONS = frozenset({"SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "OVER_BUDGET", "RESPONSE_OVER_BUDGET"})


def selection(value):
    return v2_selection(value, "result")


def validate_frame(value):
    if (type(value) is not dict or set(value) != {"schema", "operation", "selection", "principal"}
            or value["schema"] != FRAME_SCHEMA or value["operation"] != OPERATION):
        raise ValueError("invalid_input")
    validate_v2_frame({**value, "schema": FRAME_SCHEMA_V2, "operation": "result"})
    if len(canonical(value)) + 1 > MAX_REQUEST_BYTES:
        raise ValueError("invalid_input")
    return value


def unavailable(selected, reason):
    selected = selection(selected)
    if reason not in REASONS:
        raise ValueError("invalid_input")
    return {"ok": True, "result": {
        "schema": BODY_SCHEMA, "selection": selected, "availability": "UNAVAILABLE",
        "reason_codes": [reason], "execution_return": None, "delivery_receipt": None,
        "source_observation": {
            "schema": RESULT_OBSERVATION_SCHEMA,
            "state": "CONFLICT" if reason == "SOURCE_CHANGED" else "UNKNOWN",
            "selection": dict(selected), "control_room": None, "runtime": None,
        },
    }}


def _keys(value, keys):
    return type(value) is dict and set(value) == set(keys)


def validate_body(body, selected=None, *, record_validator, receipt_validator):
    """Closed envelope and same-read proof; caller supplies the original validators."""
    if selected is None:
        selected = body.get("selection") if type(body) is dict else None
    selected = selection(selected)
    if (not _keys(body, {"schema", "selection", "availability", "reason_codes",
                        "source_observation", "execution_return", "delivery_receipt"})
            or body["schema"] != BODY_SCHEMA or body["selection"] != selected):
        raise ValueError("invalid_execution_return_response")
    if body["availability"] == "UNAVAILABLE":
        reasons = body["reason_codes"]
        if (type(reasons) is not list or len(reasons) != 1 or reasons[0] not in REASONS
                or body != unavailable(selected, reasons[0])["result"]):
            raise ValueError("invalid_execution_return_response")
        return body
    if body["availability"] != "AVAILABLE" or body["reason_codes"] != []:
        raise ValueError("invalid_execution_return_response")
    observed = body["source_observation"]
    if (not _keys(observed, {"schema", "state", "selection", "control_room", "runtime"})
            or observed["schema"] != RESULT_OBSERVATION_SCHEMA or observed["state"] != "SAME"
            or observed["selection"] != selected):
        raise ValueError("invalid_execution_return_observation")
    ccr, runtime = observed["control_room"], observed["runtime"]
    if (not _keys(ccr, {"instance_before", "instance_after", "publication_before", "publication_after",
                       "document_digest", "source_validity_digest", "cache_currentness_digest"})
            or type(ccr["instance_before"]) is not str or not 1 <= len(ccr["instance_before"]) <= 64
            or ccr["instance_before"] != ccr["instance_after"]
            or type(ccr["publication_before"]) is not int or ccr["publication_before"] < 1
            or type(ccr["publication_after"]) is not int or ccr["publication_before"] != ccr["publication_after"]
            or any(type(ccr[key]) is not str or re.fullmatch(r"[0-9a-f]{64}", ccr[key]) is None
                   for key in ("document_digest", "source_validity_digest", "cache_currentness_digest"))
            or not _keys(runtime, {"schema", "state", "source_identity", "before", "after"})
            or runtime["schema"] != "mastermind.runtime_read_observation.v1" or runtime["state"] != "SAME"
            or type(runtime["source_identity"]) is not str
            or re.fullmatch(r"[0-9a-f]{32}", runtime["source_identity"]) is None
            or type(runtime["before"]) is not int or runtime["before"] < 0
            or type(runtime["after"]) is not int or runtime["after"] != runtime["before"]):
        raise ValueError("invalid_execution_return_observation")
    record, receipt = body["execution_return"], body["delivery_receipt"]
    if record is None:
        if receipt is not None:
            raise ValueError("receipt_has_no_original_return")
    else:
        validated = record_validator(record)
        if (validated != record or record["attempt"]["root_id"] != selected["root_job_id"]
                or record["attempt"]["attempt_id"] != selected["attempt_id"]):
            raise ValueError("original_return_selection_differs")
        if receipt is not None and receipt_validator(record, receipt) != receipt:
            raise ValueError("original_return_receipt_differs")
    if len(canonical({"ok": True, "result": body})) + 1 > MAX_RESPONSE_BYTES:
        raise ValueError("execution_return_response_over_budget")
    return body
