"""Closed observation of an existing managed session; never a send target."""
from __future__ import annotations

import datetime as dt
import json
import re

from common.executive_workspace_contract import canonical, _check_job_id, validate_v3_frame, FRAME_SCHEMA_V3
from common.workspace_project_journal_contract import validate_selection as work_selection

SCHEMA = "mastermind.workspace_project_session_association.v1"
FRAME_SCHEMA = "mastermind.workspace_project_session_read.v1"
OPERATION = "project_session"
MAX_RESPONSE_BYTES = 16_384
REASONS = frozenset({"MATERIALIZATION_CONFLICT", "SOURCE_UNAVAILABLE", "SOURCE_CHANGED",
                     "SOURCE_MISMATCH", "RESPONSE_OVER_BUDGET"})
_KEYS = {"schema", "selection", "availability", "state", "reason", "observational_only",
         "can_send", "continuation_target", "project_source", "runtime_creation", "materialization"}


def selection(value):
    if (type(value) is not dict or set(value) != {"work_ref", "root_job_id"}
            or not _check_job_id(value["root_job_id"])):
        raise ValueError("invalid_input")
    work_selection({"work_ref": value["work_ref"]})
    return dict(value)


def validate_frame(value):
    """The original Workspace READ principal; no caller session selectors."""
    if (type(value) is not dict or set(value) != {"schema", "operation", "principal", "selection"}
            or value["schema"] != FRAME_SCHEMA or value["operation"] != OPERATION):
        raise ValueError("invalid_input")
    selected = selection(value["selection"])
    validate_v3_frame({"schema": FRAME_SCHEMA_V3, "operation": "admitted_plan",
                       "principal": value["principal"], "selection": selected})
    return json.loads(canonical(value))


def _require(condition):
    if not condition:
        raise ValueError("invalid_project_session_association")


def _hex(value, length=64):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value) is not None


def _timestamp(value):
    if (type(value) is not str or len(value) > 40 or re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", value) is None):
        return False
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() == dt.timedelta(0)
    except ValueError:
        return False


def validate_project_source(value, selected):
    _require(type(value) is dict and set(value) == {
        "repository", "commit", "path", "content_sha256", "request_sha256"})
    _require(value["repository"] == "macro" and _hex(value["commit"], 40)
             and value["path"] == "agentos/workstreams/WS-" + selected["work_ref"][3:] + ".md"
             and _hex(value["content_sha256"]) and _hex(value["request_sha256"]))
    return dict(value)


def validate_body(value):
    try:
        _require(type(value) is dict and set(value) == _KEYS and value["schema"] == SCHEMA)
        selected = selection(value["selection"])
        _require(value["observational_only"] is True and value["can_send"] is False
                 and value["continuation_target"] is None)
        if value["state"] == "UNAVAILABLE":
            _require(value["availability"] == "UNAVAILABLE" and type(value["reason"]) is str
                     and value["reason"] in REASONS and all(value[key] is None for key in
                     ("project_source", "runtime_creation", "materialization")))
        else:
            _require(value["availability"] == "AVAILABLE")
            validate_project_source(value["project_source"], selected)
            creation = value["runtime_creation"]
            _require(type(creation) is dict and set(creation) == {
                "intent_id", "fingerprint", "creation_event_sha256"})
            _require(type(creation["intent_id"]) is str and re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}", creation["intent_id"]) is not None
                and _hex(creation["fingerprint"]) and _hex(creation["creation_event_sha256"]))
            if value["state"] == "PREPARING":
                _require(value["reason"] == "NOT_MATERIALIZED" and value["materialization"] is None)
            else:
                _require((value["state"], value["reason"]) in {
                    ("MATERIALIZED_OBSERVATION", None), ("RECORDED_MATERIALIZATION", "BROKER_RESTARTED")})
                material = value["materialization"]
                _require(type(material) is dict and set(material) == {"receipt_sha256", "recorded_at",
                    "operation_kind", "epoch_sha256", "process_generation_sha256", "provider_session_sha256",
                    "generation_number"})
                _require(all(_hex(material[key]) for key in ("receipt_sha256", "epoch_sha256",
                    "process_generation_sha256", "provider_session_sha256")) and _timestamp(material["recorded_at"]))
                _require(type(material["generation_number"]) is int and
                    (material["operation_kind"], material["generation_number"]) in {("start_session", 1), ("resume_session", 2)})
        raw = canonical(value)
        _require(len(raw) + 1 <= MAX_RESPONSE_BYTES)
        return json.loads(raw)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise ValueError("invalid_project_session_association") from None


def unavailable(selected, reason="SOURCE_UNAVAILABLE"):
    return validate_body({"schema": SCHEMA, "selection": selection(selected), "availability": "UNAVAILABLE",
        "state": "UNAVAILABLE", "reason": reason, "observational_only": True, "can_send": False,
        "continuation_target": None, "project_source": None, "runtime_creation": None, "materialization": None})


def validate_source_observation(value, *, work_ref, record_commit):
    """Private sealed-child output, not an authenticated browser request."""
    work_selection({"work_ref": work_ref})
    _require(_hex(record_commit, 40))
    _require(type(value) is dict and set(value) == {"schema", "work_ref", "availability", "source", "reason"})
    _require(value["schema"] == "mastermind.agentos_project_creation_source.v1" and value["work_ref"] == work_ref)
    if value["availability"] == "AVAILABLE":
        validate_project_source(value["source"], {"work_ref": work_ref})
        _require(value["source"]["commit"] == record_commit and value["reason"] is None)
    else:
        _require(value["availability"] == "UNAVAILABLE" and value["source"] is None
            and type(value["reason"]) is str and value["reason"] in {"SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "SOURCE_MISMATCH"})
    raw = canonical(value)
    _require(len(raw) + 1 <= 4096)
    return json.loads(raw)
