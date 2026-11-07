"""Closed metadata-only browser reads of original paid Fabric attempts.

Selectors carry no grant, host, filesystem path or source choice. The existing
Workspace/COO/Runtime and paid owner must establish authority before any read.
"""
from __future__ import annotations

from datetime import datetime
import re

from common.executive_workspace_contract import (
    RESOURCE, SCOPE, PRINCIPAL_KEYS, MAX_REQUEST_BYTES, canonical,
    _check_job_id, _check_attempt_id,
)

FRAME_SCHEMA = "mastermind.workspace.fabric_read.v1"
CATALOG_SCHEMA = "mastermind.attended_fabric_catalog.v1"
STATUS_SCHEMA = "mastermind.fabric_task_status.v1"
CATALOG_OPERATION = "fabric_catalog"
STATUS_OPERATION = "fabric_status"
MAX_CATALOG_BYTES = 65_536
MAX_STATUS_BYTES = 16_384
MAX_ROWS = 32
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_DIGEST = re.compile(r"[a-f0-9]{64}\Z")
_STATES = frozenset({"NOT_FOUND", "STATUS_UNREADABLE", "ACTIVE_OR_WAITING",
    "EFFECT_UNKNOWN", "RESULT_UNAVAILABLE", "TERMINAL_FAILURE", "TERMINAL", "SETTLING"})
_STATUS_FIELDS = frozenset({"schema", "run_id", "root_id", "parent_run_id", "state",
    "rc", "signal", "result_available", "result_bytes", "accepted", "accepted_by",
    "acceptance_state", "acceptance_reason"})
_REASONS = frozenset({"SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "SCAN_LIMIT",
    "ROWS_OMITTED", "STATUS_PARTIAL"})


def _token(value):
    return type(value) is str and _TOKEN.fullmatch(value) is not None


def selection(value):
    if (type(value) is not dict or set(value) != {"root_id", "run_id"}
            or not _check_job_id(value["root_id"]) or not _check_attempt_id(value["run_id"])):
        raise ValueError("invalid_input")
    return dict(value)


def ceiling(operation):
    if operation == CATALOG_OPERATION:
        return MAX_CATALOG_BYTES
    if operation == STATUS_OPERATION:
        return MAX_STATUS_BYTES
    raise ValueError("invalid_input")


def validate_frame(value):
    if (type(value) is not dict or set(value) != {"schema", "operation", "selection", "principal"}
            or value["schema"] != FRAME_SCHEMA
            or type(value["principal"]) is not dict or set(value["principal"]) != PRINCIPAL_KEYS
            or value["principal"]["resource"] != RESOURCE
            or value["principal"]["scopes"] != [SCOPE]
            or any(type(value["principal"][key]) is not str
                or not 1 <= len(value["principal"][key]) <= 256
                for key in PRINCIPAL_KEYS - {"scopes"})):
        raise ValueError("invalid_input")
    ceiling(value["operation"])
    if value["operation"] == CATALOG_OPERATION:
        if value["selection"] is not None:
            raise ValueError("invalid_input")
    else:
        selection(value["selection"])
    if len(canonical(value)) + 1 > MAX_REQUEST_BYTES:
        raise ValueError("invalid_input")
    return value


def status_metadata(value, *, run_id, root_id, parent_run_id=None):
    """Copy approved fields only; never infer acceptance or terminal success."""
    if type(value) is not dict or not _STATUS_FIELDS <= set(value):
        raise ValueError("invalid_fabric_status")
    row = {key: value[key] for key in _STATUS_FIELDS}
    if (row["schema"] != STATUS_SCHEMA or row["run_id"] != run_id or not _token(run_id)
            or row["state"] not in _STATES
            or row["root_id"] not in (None, root_id)
            or row["root_id"] is not None and not _token(row["root_id"])
            or row["parent_run_id"] is not None and not _token(row["parent_run_id"])
            or parent_run_id is not None and row["parent_run_id"] not in (None, parent_run_id)
            or row["rc"] is not None and (type(row["rc"]) is not int or not 0 <= row["rc"] <= 255)
            or row["signal"] is not None and not _token(row["signal"])
            or type(row["result_available"]) is not bool
            or row["result_bytes"] is not None and (type(row["result_bytes"]) is not int
                or not 0 <= row["result_bytes"] <= 2**53 - 1)
            or not row["result_available"] and row["result_bytes"] is not None
            or row["accepted"] is not None and type(row["accepted"]) is not bool
            or row["accepted_by"] not in (None, "none", "deterministic", "reviewer")
            or not _token(row["acceptance_reason"])):
        raise ValueError("invalid_fabric_status")
    if row["accepted"] is None:
        valid = row["accepted_by"] is None and row["acceptance_state"] == "UNVERIFIED"
    elif row["accepted"] is True:
        valid = (row["acceptance_state"] == "ACCEPTED"
            and row["accepted_by"] in ("deterministic", "reviewer")
            and row["state"] == "TERMINAL" and row["rc"] == 0 and row["signal"] == "ok"
            and row["result_available"] and row["root_id"] is not None)
    else:
        valid = row["acceptance_state"] == "NOT_ACCEPTED"
    if not valid or len(canonical(row)) + 1 > MAX_STATUS_BYTES:
        raise ValueError("invalid_fabric_status")
    return row


def validate_catalog(value):
    if (type(value) is not dict or set(value) != {"schema", "availability", "observed_at",
            "source", "coverage", "items", "reason_codes"}
            or value["schema"] != CATALOG_SCHEMA or value["availability"] != "PARTIAL"
            or type(value["items"]) is not list or len(value["items"]) > MAX_ROWS
            or type(value["reason_codes"]) is not list
            or any(type(reason) is not str or reason not in _REASONS for reason in value["reason_codes"])
            or len(set(value["reason_codes"])) != len(value["reason_codes"])
            or "ROWS_OMITTED" not in value["reason_codes"]):
        raise ValueError("invalid_fabric_catalog")
    try:
        if datetime.fromisoformat(value["observed_at"].replace("Z", "+00:00")).utcoffset() is None:
            raise ValueError("invalid_fabric_catalog")
    except (TypeError, AttributeError):
        raise ValueError("invalid_fabric_catalog") from None
    source, coverage = value["source"], value["coverage"]
    if (type(source) is not dict or set(source) != {"owner", "observation_kind", "revision", "scope", "atomic", "time_basis"}
            or source["owner"] != "ATTENDED_FABRIC"
            or source["observation_kind"] != "CONTROLLER_STATUS_SNAPSHOT"
            or type(source["revision"]) is not str or _DIGEST.fullmatch(source["revision"]) is None
            or source["scope"] != "EXACT_RUN_SET" or source["atomic"] is not False
            or source["time_basis"] != "LOCAL_READ"
            or type(coverage) is not dict or set(coverage) != {"returned_count", "candidate_count",
                "omitted_count", "scan_complete", "status_complete"}
            or type(coverage["returned_count"]) is not int or coverage["returned_count"] != len(value["items"])
            or coverage["candidate_count"] is not None or coverage["omitted_count"] is not None
            or coverage["scan_complete"] is not False or type(coverage["status_complete"]) is not bool):
        raise ValueError("invalid_fabric_catalog")
    seen = set()
    for item in value["items"]:
        if (type(item) is not dict or set(item) != {"run_id", "controller_modified_at", "status", "reason_code"}
                or not _token(item["run_id"]) or item["run_id"] in seen
                or item["controller_modified_at"] is not None):
            raise ValueError("invalid_fabric_catalog")
        seen.add(item["run_id"])
        if item["status"] is None:
            if item["reason_code"] not in {"STATUS_UNAVAILABLE", "SOURCE_CHANGED", "STATUS_INVALID"}:
                raise ValueError("invalid_fabric_catalog")
        elif (item["reason_code"] is not None or item["status"] != status_metadata(item["status"],
                run_id=item["run_id"], root_id=item["status"].get("root_id"))):
            raise ValueError("invalid_fabric_catalog")
    if (coverage["status_complete"] != all(item["status"] is not None for item in value["items"])
            or (not coverage["status_complete"] and "STATUS_PARTIAL" not in value["reason_codes"])
            or len(canonical(value)) + 1 > MAX_CATALOG_BYTES):
        raise ValueError("invalid_fabric_catalog")
    return value
