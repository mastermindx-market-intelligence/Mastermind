"""Closed activity-read frame over the existing Workspace principal and Runtime.

A distinct operation, not a widening of frozen Workspace v3 admitted-plan or
v2 result contracts. This is a passive transport shape; it never authenticates
a principal or grants access to a machine/native Fabric run.
"""
from __future__ import annotations

import re
from common.executive_workspace_contract import (
    RESOURCE, SCOPE, PRINCIPAL_KEYS, MAX_REQUEST_BYTES,
    canonical, error, _check_work_ref, _check_job_id, _check_attempt_id,
)

FRAME_SCHEMA = "mastermind.executive_workspace_read.v5"
OPERATION = "retained_activity"
BODY_SCHEMA = "mastermind.workspace_retained_activity.v1"
OBSERVATION_SCHEMA = "mastermind.workspace_retained_activity_observation.v1"
MAX_RESPONSE_BYTES = 16_384
REASONS = frozenset({
    "SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "OVER_BUDGET",
    "RESPONSE_OVER_BUDGET",
})
_KEYS = frozenset({"work_ref", "root_job_id", "job_id", "attempt_id"})

def selection(value):
    if (type(value) is not dict or set(value) != _KEYS or
            not _check_work_ref(value["work_ref"]) or
            not _check_job_id(value["root_job_id"]) or
            not _check_job_id(value["job_id"]) or
            not _check_attempt_id(value["attempt_id"]) or
            value["root_job_id"] == value["job_id"]):
        raise ValueError("invalid_input")
    return {key: value[key] for key in sorted(_KEYS)}

def validate_frame(value):
    if (type(value) is not dict or set(value) !=
            {"schema", "operation", "selection", "principal"} or
            value["schema"] != FRAME_SCHEMA or value["operation"] != OPERATION or
            type(value["principal"]) is not dict or set(value["principal"]) != PRINCIPAL_KEYS or
            value["principal"]["resource"] != RESOURCE or
            value["principal"]["scopes"] != [SCOPE] or
            any(type(value["principal"][key]) is not str or
                not 1 <= len(value["principal"][key]) <= 256
                for key in PRINCIPAL_KEYS - {"scopes"})):
        raise ValueError("invalid_input")
    selection(value["selection"])
    if len(canonical(value)) + 1 > MAX_REQUEST_BYTES:
        raise ValueError("invalid_input")
    return value

def unavailable(selected, reason):
    if reason not in REASONS:
        raise ValueError("invalid_input")
    selected = selection(selected)
    return {"ok": True, "result": {
        "schema": BODY_SCHEMA, "selection": selected,
        "availability": "UNAVAILABLE", "reason_codes": [reason], "activity": None,
        "source_observation": {
            "schema": OBSERVATION_SCHEMA, "state": (
                "CONFLICT" if reason == "SOURCE_CHANGED" else "UNKNOWN"
            ),
            "selection": dict(selected), "control_room": None, "runtime": None,
        },
    }}

_CATEGORIES = frozenset({
    "TURN_COMPLETED", "TURN_ACTIVITY", "ITEM_ACTIVITY",
    "TOOL_ACTIVITY", "MODEL_ACTIVITY", "OTHER_REDACTED_EVENT",
})
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_EPOCH = re.compile(r"^[0-9a-f]{32}$")
_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|\+00:00)$")

def _keys(value, expected):
    return type(value) is dict and set(value) == set(expected)

def validate_result(body, selected):
    """Closed public-body boundary. Reject unreviewed source/provider fields."""
    selected = selection(selected)
    fields = {"schema", "selection", "availability", "reason_codes", "activity", "source_observation"}
    if not _keys(body, fields) or body["schema"] != BODY_SCHEMA or body["selection"] != selected:
        raise ValueError("invalid_activity_response")
    if body["availability"] == "UNAVAILABLE":
        reasons = body["reason_codes"]
        if (type(reasons) is not list or len(reasons) != 1 or
                reasons[0] not in REASONS or body != unavailable(selected, reasons[0])["result"]):
            raise ValueError("invalid_activity_response")
        return body
    if body["availability"] != "AVAILABLE" or body["reason_codes"] != []:
        raise ValueError("invalid_activity_response")
    source = body["activity"]
    observed = body["source_observation"]
    if (not _keys(source, {"schema", "selection", "availability", "source",
                           "candidate_receipts_in_sample", "normalized_events_in_sample",
                           "omitted_in_sample", "rows"})
            or source["schema"] != "mastermind.operator_retained_activity_metadata.v1"
            or source["selection"] != selected
            or source["availability"] not in ("RETAINED", "PARTIAL", "NO_RETAINED_CANDIDATES")
            or not _keys(source["source"], {"state", "scope", "source_truncated",
                                           "live_worker_count", "global_event_total"})
            or source["source"]["state"] != "SAME_AS_OF_READ"
            or source["source"]["scope"] != "RETAINED_CANDIDATES_ONLY"
            or type(source["source"]["source_truncated"]) is not bool
            or source["source"]["live_worker_count"] is not None
            or source["source"]["global_event_total"] is not None
            or type(source["rows"]) is not list or len(source["rows"]) > 32
            or any(type(source[field]) is not int or source[field] < 0 or source[field] > 16384
                   for field in ("candidate_receipts_in_sample",
                                 "normalized_events_in_sample", "omitted_in_sample"))
            or source["normalized_events_in_sample"] != len(source["rows"]) + source["omitted_in_sample"]
            or source["candidate_receipts_in_sample"] > 64
            or source["availability"] == "NO_RETAINED_CANDIDATES" and source["rows"] != []):
        raise ValueError("invalid_activity_response")
    for row in source["rows"]:
        if (not _keys(row, {"candidate_event_id", "turn_id", "ordinal_in_candidate",
                            "category", "candidate_recorded_at"})
                or type(row["candidate_event_id"]) is not int or row["candidate_event_id"] <= 0
                or type(row["turn_id"]) is not str or _ID.fullmatch(row["turn_id"]) is None
                or type(row["ordinal_in_candidate"]) is not int
                or not 0 <= row["ordinal_in_candidate"] < 256
                or row["category"] not in _CATEGORIES
                or type(row["candidate_recorded_at"]) is not str
                or _TIME.fullmatch(row["candidate_recorded_at"]) is None):
            raise ValueError("invalid_activity_response")
    if (not _keys(observed, {"schema", "state", "selection", "control_room", "runtime"})
            or observed["schema"] != OBSERVATION_SCHEMA
            or observed["state"] != "SAME" or observed["selection"] != selected
            or not _keys(observed["control_room"], {
                "instance_before", "instance_after", "publication_before",
                "publication_after", "document_digest", "source_validity_digest",
                "cache_currentness_digest",
            }) or not _keys(observed["runtime"], {
                "schema", "state", "source_identity", "before", "after",
            }) or observed["runtime"]["schema"] != "mastermind.runtime_read_observation.v1"
            or observed["runtime"]["state"] != "SAME"
            or type(observed["runtime"]["source_identity"]) is not str
            or _EPOCH.fullmatch(observed["runtime"]["source_identity"]) is None
            or type(observed["runtime"]["before"]) is not int
            or observed["runtime"]["before"] < 0
            or observed["runtime"]["after"] != observed["runtime"]["before"]
            or any(type(observed["control_room"][key]) is not str
                   or _DIGEST.fullmatch(observed["control_room"][key]) is None
                   for key in ("document_digest", "source_validity_digest",
                               "cache_currentness_digest"))
            or type(observed["control_room"]["publication_before"]) is not int
            or observed["control_room"]["publication_before"] <= 0
            or observed["control_room"]["publication_after"] != observed["control_room"]["publication_before"]):
        raise ValueError("invalid_activity_response")
    if (len(canonical({"ok": True, "result": body})) + 1 > MAX_RESPONSE_BYTES):
        raise ValueError("invalid_activity_response")
    return body
