"""Closed bounded canonical archive sample; read-only and catalogue-bound."""
from __future__ import annotations

import copy
import datetime as dt
import json
import re

from common import workspace_project_plan_contract as plan

BODY_SCHEMA = "mastermind.workspace_project_archive.v1"
FRAME_SCHEMA = "mastermind.workspace_project_archive_read.v1"
OPERATION = "project_archive"
PAGE_FRAME_SCHEMA = "mastermind.workspace_project_archive_page_read.v1"
PAGE_OPERATION = "project_archive_page"
MAX_RESPONSE_BYTES = 262144
MAX_MEMBERS = 128
REASONS = ("SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "CONTENT_OVER_BUDGET")


def _require(condition):
    if not condition:
        raise ValueError("invalid_project_archive")


def _hex(value, size):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{" + str(size) + r"}", value) is not None


def _text(value, limit):
    return type(value) is str and bool(value.strip()) and len(value.encode("utf-8")) <= limit


def work_ref(value):
    plan.validate_selection({"work_ref": value})
    return value


def validate_refs(value):
    _require(type(value) is list and len(value) <= MAX_MEMBERS and all(work_ref(ref) for ref in value)
             and len(set(value)) == len(value) and value == sorted(value))
    return list(value)


def validate_frame(value):
    _require(type(value) is dict and set(value) == {"schema", "operation", "principal"})
    _require(value["schema"] == FRAME_SCHEMA and value["operation"] == OPERATION)
    # Reuse the established principal validator through its fixed rootless READ.
    plan.validate_frame(dict(value, schema=plan.FRAME_SCHEMA, operation=plan.OPERATION,
                             selection={"work_ref": "WS:ARCHIVE-VALIDATION"}))
    return copy.deepcopy(value)


def page_selection(value):
    _require(type(value) is dict and set(value) == {"after_work_ref", "catalogue_digest"})
    work_ref(value["after_work_ref"])
    _require(_hex(value["catalogue_digest"], 64))
    return dict(value)


def validate_page_frame(value):
    _require(type(value) is dict and set(value) == {"schema", "operation", "principal", "selection"})
    _require(value["schema"] == PAGE_FRAME_SCHEMA and value["operation"] == PAGE_OPERATION)
    page_selection(value["selection"])
    validate_frame({"schema": FRAME_SCHEMA, "operation": OPERATION, "principal": value["principal"]})
    return copy.deepcopy(value)


def validate_read_frame(value):
    if type(value) is dict and value.get("schema") == PAGE_FRAME_SCHEMA:
        return validate_page_frame(value)
    return validate_frame(value)


def unavailable(reason="SOURCE_UNAVAILABLE"):
    _require(reason in REASONS)
    return {"schema": BODY_SCHEMA, "availability": "UNAVAILABLE", "catalogue": None,
            "sample": None, "reason_codes": [reason]}


def validate_sample(value, refs, commit):
    _require(type(value) is dict and set(value) == {"schema", "source_commit", "coverage", "availability", "reason", "items", "can_restore"})
    _require(value["schema"] == "agentos.project_archive_sample.v1" and value["source_commit"] == commit
             and value["availability"] == "AVAILABLE" and value["reason"] is None and value["can_restore"] is False)
    coverage = value["coverage"]
    _require(type(coverage) is dict and set(coverage) == {"kind", "supplied_count", "observed_count", "company_total"})
    _require(coverage["kind"] == "QUALIFIED_CATALOGUE_SAMPLE" and coverage["company_total"] is None
             and type(coverage["supplied_count"]) is int and type(coverage["observed_count"]) is int
             and coverage["supplied_count"] == coverage["observed_count"] == len(refs))
    items, seen = value["items"], set()
    _require(type(items) is list and len(items) <= len(refs))
    for row in items:
        _require(type(row) is dict and set(row) == {"work_ref", "title", "objective", "archive", "source"})
        ref = work_ref(row["work_ref"])
        _require(ref in refs and ref not in seen and _text(row["title"], 4096) and _text(row["objective"], 16384))
        seen.add(ref)
        archive = row["archive"]
        _require(type(archive) is dict and set(archive) == {"schema", "state", "archived_on", "archived_by", "reason"})
        _require(archive["schema"] == "agentos.workstream_archive.v1" and archive["state"] == "ARCHIVED"
                 and _text(archive["archived_by"], 256) and _text(archive["reason"], 2000))
        day = archive["archived_on"]
        _require(type(day) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) is not None)
        _require(dt.date.fromisoformat(day).isoformat() == day)
        source = row["source"]
        _require(type(source) is dict and set(source) == {"repository", "commit", "path", "content_sha256"})
        _require(source["repository"] == "macro" and source["commit"] == commit
                 and source["path"] == "agentos/workstreams/WS-" + ref[3:] + ".md" and _hex(source["content_sha256"], 64))
    return copy.deepcopy(value)


def validate_body(value):
    _require(type(value) is dict and set(value) == {"schema", "availability", "catalogue", "sample", "reason_codes"})
    _require(value["schema"] == BODY_SCHEMA)
    if value["availability"] == "UNAVAILABLE":
        _require(value["catalogue"] is None and value["sample"] is None and type(value["reason_codes"]) is list
                 and len(value["reason_codes"]) == 1 and value["reason_codes"][0] in REASONS)
    else:
        _require(value["availability"] == "AVAILABLE" and value["reason_codes"] == [])
        cat = value["catalogue"]
        _require(type(cat) is dict and set(cat) == {"document_digest", "macro_sha", "work_refs", "qualified_catalogue_count"})
        _require(_hex(cat["document_digest"], 64) and _hex(cat["macro_sha"], 40))
        refs = cat["work_refs"]
        validate_refs(refs)
        _require(type(cat["qualified_catalogue_count"]) is int and len(refs) <= cat["qualified_catalogue_count"] <= 500)
        validate_sample(value["sample"], refs, cat["macro_sha"])
    raw = json.dumps({"ok": True, "result": value}, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    _require(len(raw) + 1 <= MAX_RESPONSE_BYTES)
    return copy.deepcopy(value)
