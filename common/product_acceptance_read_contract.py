"""Closed, read-only acceptance companion; frozen Workspace v1-v3 are unchanged."""
from __future__ import annotations

import copy
import re

from common.executive_workspace_contract import (
    MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, canonical, v2_selection,
    validate_v2_frame, _check_job_id, _check_attempt_id, _check_envelope_digest,
)

FRAME_SCHEMA = "mastermind.executive_workspace_read.v4"
FABRIC_SCHEMA = "mastermind.fabric_job_view.v4"
MISSION_SCHEMA = "mastermind.mission_workspace.v4"
VIEW_SCHEMA = "mastermind.product_acceptance_view.v1"
OPERATION = "mission_v4"
REASONS = frozenset({
    "ACCEPTANCE_NOT_COMPOSED", "ACCEPTANCE_UNAVAILABLE", "SELECTION_MISMATCH",
    "PARENT_RETURN_UNVERIFIED", "PARENT_CONSUMPTION_UNPROVEN",
    "SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "RUNTIME_CHANGED",
})
RECEIPT_KEYS = frozenset({
    "state", "subject_job_id", "subject_result_envelope_digest", "ruling_message_key",
    "qualified_ruling_digest", "parent_job_id", "parent_attempt_id",
    "parent_result_envelope_digest", "source_continuity",
})


def selection(value):
    if type(value) is not dict or set(value) != {"work_ref", "root_job_id", "request_message_key"}:
        raise ValueError("invalid_input")
    selected = v2_selection({key: value[key] for key in ("work_ref", "root_job_id")}, "mission_v3")
    key = value["request_message_key"]
    if type(key) is not str or re.fullmatch(r"asd-mcp-[0-9a-f]{32}", key) is None:
        raise ValueError("invalid_input")
    return {**selected, "request_message_key": key}


def validate_frame(frame):
    if (type(frame) is not dict or set(frame) != {"schema", "operation", "selection", "principal"}
            or frame["schema"] != FRAME_SCHEMA or frame["operation"] != OPERATION):
        raise ValueError("invalid_input")
    selected = selection(frame["selection"])
    # Reuse the exact incumbent principal/resource grammar, without widening it.
    validate_v2_frame({"schema": "mastermind.executive_workspace_read.v2",
        "operation": "mission_v3", "selection": {k: selected[k] for k in ("work_ref", "root_job_id")},
        "principal": frame["principal"]})
    if len(canonical(frame)) + 1 > MAX_REQUEST_BYTES:
        raise ValueError("invalid_input")
    return frame


def unavailable(selected, reason):
    if type(reason) is not str or reason not in REASONS:
        raise ValueError("invalid_input")
    return {"schema": VIEW_SCHEMA, "selection": selection(selected), "state": "UNAVAILABLE",
            "reason_codes": [reason], "receipt": None}


def validate_view(value, *, selected):
    selected = selection(selected)
    if (type(value) is not dict or set(value) != {"schema", "selection", "state", "reason_codes", "receipt"}
            or value["schema"] != VIEW_SCHEMA or selection(value["selection"]) != selected):
        raise ValueError("invalid_acceptance_projection")
    if value["state"] == "UNAVAILABLE":
        if (value["receipt"] is not None or type(value["reason_codes"]) is not list
                or len(value["reason_codes"]) != 1 or type(value["reason_codes"][0]) is not str
                or value["reason_codes"][0] not in REASONS):
            raise ValueError("invalid_acceptance_projection")
    elif value["state"] == "ACCEPTED":
        receipt = value["receipt"]
        if (value["reason_codes"] != [] or type(receipt) is not dict or set(receipt) != RECEIPT_KEYS
                or receipt["state"] != "PRODUCT_ACCEPTED" or receipt["parent_job_id"] != selected["root_job_id"]
                or not _check_job_id(receipt["subject_job_id"]) or not _check_attempt_id(receipt["parent_attempt_id"])
                or any(not _check_envelope_digest(receipt[key]) for key in (
                    "subject_result_envelope_digest", "qualified_ruling_digest", "parent_result_envelope_digest"))
                or type(receipt["ruling_message_key"]) is not str
                or re.fullmatch(r"asd-principal-[0-9a-f]{32}", receipt["ruling_message_key"]) is None):
            raise ValueError("invalid_acceptance_projection")
        continuity = receipt["source_continuity"]
        if (type(continuity) is not dict or set(continuity) != {
                "issued_basis_digest", "current_basis_digest", "declaration_digest", "disposition"}
                or any(not _check_envelope_digest(continuity[key]) for key in (
                    "issued_basis_digest", "current_basis_digest", "declaration_digest"))
                or type(continuity["disposition"]) is not str
                or continuity["disposition"] not in {
                    "UNCHANGED_SOURCE", "SOURCE_OBSERVATION_CHANGED_DECLARATION_UNCHANGED"}
                or (continuity["disposition"] == "UNCHANGED_SOURCE") != (
                    continuity["issued_basis_digest"] == continuity["current_basis_digest"])):
            raise ValueError("invalid_acceptance_projection")
    else:
        raise ValueError("invalid_acceptance_projection")
    if len(canonical(value)) + 1 > MAX_RESPONSE_BYTES:
        raise ValueError("invalid_acceptance_projection")
    return copy.deepcopy(value)
