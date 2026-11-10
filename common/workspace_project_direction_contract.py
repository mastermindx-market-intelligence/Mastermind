"""Closed observational read of explicit canonical accepted Direction records.

Source publication records a decision. It grants no Runtime or placement authority.
The source owner, permission bracket and fixed publisher remain separate owners.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import re

from common import workspace_project_plan_contract as plan

BODY_SCHEMA = "mastermind.workspace_project_direction.v1"
FRAME_SCHEMA = "mastermind.workspace_project_direction_read.v1"
OPERATION = "project_direction"
MAX_RESPONSE_BYTES = 65536
REASON_CODES = ("NOT_DECLARED", "SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "RECORD_NOT_FOUND",
                "RECORD_INVALID", "LINEAGE_CONFLICT", "LINEAGE_INCOMPLETE", "CONTENT_OVER_BUDGET")
_KEY = r"[A-Z0-9]+(?:-[A-Z0-9]+)*"


def selection(value):
    if type(value) is not dict or set(value) != {"work_ref"}:
        raise ValueError("invalid_input")
    return plan.validate_selection(value)


def validate_frame(value):
    if type(value) is not dict or value.get("schema") != FRAME_SCHEMA or value.get("operation") != OPERATION:
        raise ValueError("invalid_input")
    candidate = dict(value, schema=plan.FRAME_SCHEMA, operation=plan.OPERATION)
    plan.validate_frame(candidate)
    selection(value["selection"])
    return copy.deepcopy(value)


def unavailable(work_ref, reason):
    if type(reason) is not str or reason not in REASON_CODES:
        raise ValueError("invalid_input")
    return {"schema": BODY_SCHEMA, "selection": selection({"work_ref": work_ref}),
            "availability": "UNAVAILABLE", "source": None, "direction": None, "reason_codes": [reason]}


def _require(ok):
    if not ok:
        raise ValueError("invalid_project_direction")


def _text(value, limit):
    return type(value) is str and bool(value.strip()) and len(value.encode("utf-8")) <= limit


def _decision_ref(value):
    return (type(value) is str and value.startswith("DEC:") and 2 <= len(value[4:]) <= 128
            and re.fullmatch(_KEY, value[4:]) is not None)


def _row(value, origin, seen):
    _require(type(value) is dict and set(value) == {"decision_ref", "answer", "rationale", "decided_by",
              "decided_at", "date_precision", "predecessor", "source"})
    ref = value["decision_ref"]
    _require(_decision_ref(ref) and ref not in seen)
    seen.add(ref)
    _require(_text(value["answer"], 4096) and _text(value["rationale"], 4096) and _text(value["decided_by"], 256))
    day = value["decided_at"]
    _require(type(day) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) is not None)
    try:
        _require(dt.date.fromisoformat(day).isoformat() == day)
    except ValueError:
        raise ValueError("invalid_project_direction") from None
    _require(value["date_precision"] == "DAY")
    predecessor = value["predecessor"]
    _require(predecessor is None or _decision_ref(predecessor) and predecessor != ref)
    src = value["source"]
    _require(type(src) is dict and set(src) == {"repository", "commit", "path", "content_sha256"})
    _require(src["repository"] == origin["repository"] and src["commit"] == origin["commit"]
             and src["path"] == "agentos/decisions/DEC-" + ref[4:] + ".md"
             and type(src["content_sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", src["content_sha256"]) is not None)


def validate_body(value):
    _require(type(value) is dict and set(value) == {"schema", "selection", "availability", "source", "direction", "reason_codes"})
    _require(value["schema"] == BODY_SCHEMA)
    selected = selection(value["selection"])
    if value["availability"] == "UNAVAILABLE":
        _require(value["source"] is None and value["direction"] is None and type(value["reason_codes"]) is list
                 and len(value["reason_codes"]) == 1 and value["reason_codes"][0] in REASON_CODES)
    else:
        _require(value["availability"] == "AVAILABLE" and value["reason_codes"] == [])
        source = plan.validate_source(value["source"], selected["work_ref"])
        direction = value["direction"]
        _require(type(direction) is dict and set(direction) == {"work_ref", "workstream_source", "current", "history"}
                 and direction["work_ref"] == selected["work_ref"] and direction["workstream_source"] == source)
        history = direction["history"]
        _require(type(history) is dict and set(history) == {"revisions", "has_more", "total_count"}
                 and type(history["revisions"]) is list and len(history["revisions"]) <= 7
                 and type(history["has_more"]) is bool)
        rows = [direction["current"], *history["revisions"]]
        seen = set()
        for row in rows:
            _row(row, source, seen)
        for head, previous in zip(rows, rows[1:]):
            _require(head["predecessor"] == previous["decision_ref"])
        if history["has_more"]:
            _require(history["total_count"] is None and rows[-1]["predecessor"] is not None
                     and rows[-1]["predecessor"] not in seen)
        else:
            _require(type(history["total_count"]) is int and history["total_count"] == len(rows)
                     and rows[-1]["predecessor"] is None)
    encoded = json.dumps({"ok": True, "result": value}, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    _require(len(encoded) + 1 <= MAX_RESPONSE_BYTES)
    return copy.deepcopy(value)
