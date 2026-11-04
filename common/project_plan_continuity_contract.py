"""Closed transport projection, not an Agent OS adoption writer or authority.

The canonical Macro owner validates records and lineage. This module verifies
the DTO released by that owner and the supplied captured bodies before an
existing Workspace READ transport can publish them.
"""
from __future__ import annotations

import copy
from datetime import date
import hashlib
import re

from common.executive_workspace_contract import bounded_canonical
from control_plane.project_plan_content import compare_plan_content

SCHEMA = "mastermind.project_plan_continuity.v1"
BODY_SCHEMA_V2 = "mastermind.workspace_project_plan.v2"
MACRO = "mastermindx-market-intelligence/macro"
MASTER = "mastermindx-market-intelligence/Mastermind"
ADOPTION_REASONS = {"SOURCE_UNAVAILABLE", "NOT_DECLARED", "LINEAGE_INVALID",
                    "PROPOSAL_MISMATCH", "CONTENT_OVER_BUDGET"}
COMPARISON_REASONS = {"SOURCE_UNAVAILABLE", "SOURCE_BYTES_MISMATCH", "INVALID_CONTENT",
                      "CONTENT_OVER_BUDGET", "STALE_PREDECESSOR", "PROPOSAL_MISMATCH"}


def _fail():
    raise ValueError("invalid_project_plan_continuity")


def _closed(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        _fail()


def _text(value, limit, *, blank=False):
    if type(value) is not str or len(value) > limit or (not blank and not value.strip()):
        _fail()
    try:
        value.encode("utf-8")
    except UnicodeError:
        _fail()


def _key(value, prefix="", maximum=128):
    if type(value) is not str or not value.startswith(prefix):
        _fail()
    key = value[len(prefix):]
    if not 2 <= len(key) <= maximum or re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)*", key) is None:
        _fail()


def _source(value, work_ref=None):
    _closed(value, {"repository", "path", "commit", "content_sha256"})
    if value["repository"] not in {MACRO, MASTER}:
        _fail()
    path = value["path"]
    _text(path, 512)
    if (path.startswith("/") or not path.endswith(".md") or any(c in path for c in "\x00\r\n\\")
            or any(p in {"", ".", ".."} for p in path.split("/"))):
        _fail()
    for field, size in (("commit", 40), ("content_sha256", 64)):
        if type(value[field]) is not str or re.fullmatch(r"[0-9a-f]{" + str(size) + "}", value[field]) is None:
            _fail()
    if (work_ref and value["repository"] == MACRO and path.lower().startswith("agentos/workstreams/")
            and path != "agentos/workstreams/WS-" + work_ref[3:] + ".md"):
        _fail()


def _metadata(value, work_ref):
    _closed(value, {"schema", "work_ref", "adopted_source", "predecessor", "proposal_source", "display_revision"})
    if value["schema"] != "agentos.project_plan_adoption.v1" or value["work_ref"] != work_ref:
        _fail()
    _source(value["adopted_source"], work_ref)
    if value["predecessor"] is not None:
        _key(value["predecessor"], "DEC:")
    if value["proposal_source"] is not None:
        _source(value["proposal_source"], work_ref)
    if value["display_revision"] is not None:
        _text(value["display_revision"], 128)
        if any(c in value["display_revision"] for c in "\x00\r\n"):
            _fail()


def _declaration(value, work_ref, *, available=False):
    fields = {"decision_ref", "decision_source", "adoption", "decided_by", "decided_at"}
    _closed(value, fields | {"state", "content"} if available else fields)
    _key(value["decision_ref"], "DEC:")
    _source(value["decision_source"])
    if (value["decision_source"]["repository"] != MACRO
            or value["decision_source"]["path"] != "agentos/decisions/DEC-" + value["decision_ref"][4:] + ".md"):
        _fail()
    _metadata(value["adoption"], work_ref)
    if value["adoption"]["predecessor"] == value["decision_ref"]:
        _fail()
    _text(value["decided_by"], 256)
    if type(value["decided_at"]) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value["decided_at"]) is None:
        _fail()
    try:
        date.fromisoformat(value["decided_at"])
    except ValueError:
        _fail()
    if available:
        _text(value["content"], 262144, blank=True)
        raw = value["content"].encode("utf-8")
        if not 1 <= len(raw) <= 262144 or hashlib.sha256(raw).hexdigest() != value["adoption"]["adopted_source"]["content_sha256"]:
            _fail()


def validate_continuity(value, work_ref):
    """Validate a closed DTO, independently rechecking available byte comparisons."""
    try:
        _key(work_ref, "WS:", 64)
        _closed(value, {"schema", "work_ref", "adoption", "proposals"})
        if value["schema"] != SCHEMA or value["work_ref"] != work_ref:
            _fail()
        adoption = value["adoption"]
        declaration = None
        if type(adoption) is not dict:
            _fail()
        if adoption.get("state") == "AVAILABLE":
            _declaration(adoption, work_ref, available=True)
            declaration = adoption
        elif adoption.get("state") == "UNAVAILABLE":
            declared = "declared_decision" in adoption
            _closed(adoption, {"state", "reason", "declared_decision"} if declared else {"state", "reason"})
            if adoption["reason"] not in ADOPTION_REASONS:
                _fail()
            if declared:
                if adoption["reason"] not in {"SOURCE_UNAVAILABLE", "PROPOSAL_MISMATCH"}:
                    _fail()
                _declaration(adoption["declared_decision"], work_ref)
                declaration = adoption["declared_decision"]
        else:
            _fail()
        proposals = value["proposals"]
        if type(proposals) is not dict or proposals.get("coverage") != "CAPTURED_ASSOCIATIONS_ONLY":
            _fail()
        if proposals.get("state") == "UNAVAILABLE":
            _closed(proposals, {"state", "reason", "coverage"})
            if proposals["reason"] not in {"SOURCE_UNAVAILABLE", "LINEAGE_INVALID", "RECORD_INVALID", "CONTENT_OVER_BUDGET"}:
                _fail()
        elif proposals.get("state") == "AVAILABLE":
            _closed(proposals, {"state", "items", "coverage"})
            if type(proposals["items"]) is not list or len(proposals["items"]) > 32:
                _fail()
            seen = set()
            for item in proposals["items"]:
                if type(item) is not dict:
                    _fail()
                _source(item.get("proposal_source"))
                if item.get("state") == "UNAVAILABLE":
                    _closed(item, {"proposal_source", "state", "reason"})
                    if item["reason"] != "RECORD_INVALID":
                        _fail()
                    continue
                _closed(item, {"proposal_source", "state", "schema", "proposal_id", "work_ref", "base_adoption",
                               "base_source", "candidate_sha256", "rationale", "evidence", "adoption_relation",
                               "comparison", "comparison_basis"})
                if item["state"] != "RECORDED_PROPOSAL" or item["schema"] != "agentos.project_plan_proposal.v1" or item["work_ref"] != work_ref:
                    _fail()
                _key(item["proposal_id"])
                if item["proposal_id"] in seen:
                    _fail()
                seen.add(item["proposal_id"])
                if item["base_adoption"] is not None:
                    _key(item["base_adoption"], "DEC:")
                _source(item["base_source"], work_ref)
                if type(item["candidate_sha256"]) is not str or re.fullmatch(r"[0-9a-f]{64}", item["candidate_sha256"]) is None:
                    _fail()
                _text(item["rationale"], 4096)
                if type(item["evidence"]) is not list or len(item["evidence"]) > 32:
                    _fail()
                for ref in item["evidence"]:
                    _source(ref)
                referenced = declaration is not None and declaration["adoption"]["proposal_source"] == item["proposal_source"]
                expected_relation = "CURRENT_DECISION_REFERENCES_PROPOSAL" if referenced else "UNASSOCIATED_WITH_CURRENT_DECISION"
                expected_basis = ("RECORDED_PREDECESSOR" if referenced else "DECLARED_ADOPTION_SOURCE"
                                  if declaration and adoption["state"] != "AVAILABLE" else "ADOPTED_CONTENT"
                                  if declaration else "RECORDED_SOURCE")
                if item["adoption_relation"] != expected_relation or item["comparison_basis"] != expected_basis:
                    _fail()
                comparison = item["comparison"]
                if type(comparison) is not dict:
                    _fail()
                if comparison.get("state") == "UNAVAILABLE":
                    _closed(comparison, {"state", "reason"})
                    if comparison["reason"] not in COMPARISON_REASONS:
                        _fail()
                elif comparison.get("state") == "AVAILABLE":
                    _closed(comparison, {"state", "base_source", "candidate_sha256", "base_text", "candidate_text",
                                         "diff", "identical", "added_lines", "removed_lines"})
                    if (type(comparison["identical"]) is not bool
                            or any(type(comparison[k]) is not int or not 0 <= comparison[k] <= 9007199254740991
                                   for k in ("added_lines", "removed_lines"))):
                        _fail()
                    if declaration and adoption["state"] != "AVAILABLE":
                        _fail()
                    _text(comparison.get("base_text"), 262144, blank=True)
                    _text(comparison.get("candidate_text"), 131072, blank=True)
                    expected = compare_plan_content(base_source=item["base_source"], base_bytes=comparison["base_text"].encode("utf-8"),
                        candidate_sha256=item["candidate_sha256"], candidate_bytes=comparison["candidate_text"].encode("utf-8"))
                    if expected.get("state") != "AVAILABLE" or comparison != expected:
                        _fail()
                    if referenced and item["base_adoption"] != declaration["adoption"]["predecessor"]:
                        _fail()
                    if not referenced and declaration and (item["base_adoption"] != declaration["decision_ref"]
                            or item["base_source"] != declaration["adoption"]["adopted_source"]):
                        _fail()
                    if not declaration and item["base_adoption"] is not None:
                        _fail()
                else:
                    _fail()
        else:
            _fail()
        bounded_canonical(value, limit=126976)
        return copy.deepcopy(value)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, UnicodeError):
        _fail()


def adoption_summary(continuity, authored_source, *, authored_bytes=None):
    adoption = continuity["adoption"]
    if adoption["state"] == "UNAVAILABLE":
        return {"state": "UNAVAILABLE", "reason": adoption["reason"]}
    ref = adoption["adoption"]["adopted_source"]
    matches = ref["content_sha256"] == authored_source["content_sha256"]
    if authored_bytes is not None:
        if (type(authored_bytes) is not bytes
                or hashlib.sha256(authored_bytes).hexdigest() != authored_source["content_sha256"]):
            _fail()
        matches = authored_bytes == adoption["content"].encode("utf-8")
    return {"state": "AVAILABLE", "decision_ref": adoption["decision_ref"],
            "adopted_source": copy.deepcopy(ref), "display_revision": adoption["adoption"]["display_revision"],
            "matches_authored_record": matches}


def compose_body_v2(base_body, continuity, *, authored_bytes):
    from common import workspace_project_plan_contract as old
    base = old.validate_body(base_body)
    if base["availability"] != "AVAILABLE":
        return base  # Existing closed v1 typed unavailability remains compatible.
    if (type(authored_bytes) is not bytes or not 1 <= len(authored_bytes) <= 262144
            or hashlib.sha256(authored_bytes).hexdigest() != base["source"]["content_sha256"]):
        _fail()
    continuity = validate_continuity(continuity, base["selection"]["work_ref"])
    result = copy.deepcopy(base)
    result["schema"] = BODY_SCHEMA_V2
    result["continuity"] = continuity
    result["plan"]["adoption"] = adoption_summary(continuity, base["source"], authored_bytes=authored_bytes)
    try:
        bounded_canonical({"ok": True, "result": result}, limit=old.MAX_RESPONSE_BYTES - 1)
    except ValueError:
        continuity = {"schema": SCHEMA, "work_ref": base["selection"]["work_ref"],
                      "adoption": {"state": "UNAVAILABLE", "reason": "CONTENT_OVER_BUDGET"},
                      "proposals": {"state": "UNAVAILABLE", "reason": "CONTENT_OVER_BUDGET",
                                    "coverage": "CAPTURED_ASSOCIATIONS_ONLY"}}
        result["continuity"] = continuity
        result["plan"]["adoption"] = adoption_summary(continuity, base["source"])
        try:
            bounded_canonical({"ok": True, "result": result}, limit=old.MAX_RESPONSE_BYTES - 1)
        except ValueError:
            return old.unavailable(base["selection"]["work_ref"], "CONTENT_OVER_BUDGET")
    return validate_body_v2(result)


def validate_body_v2(value):
    try:
        return _validate_body_v2(value)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, UnicodeError):
        _fail()


def _validate_body_v2(value):
    from common import workspace_project_plan_contract as old
    _closed(value, set(old.BODY_KEYS) | {"continuity"})
    if value["schema"] != BODY_SCHEMA_V2 or value["availability"] != "AVAILABLE":
        _fail()
    continuity = validate_continuity(value["continuity"], old.validate_selection(value["selection"])["work_ref"])
    base = copy.deepcopy(value)
    del base["continuity"]
    base["schema"] = old.BODY_SCHEMA
    summary = base["plan"]["adoption"]
    if type(summary) is not dict:
        _fail()
    if summary.get("state") == "AVAILABLE" and type(summary.get("matches_authored_record")) is not bool:
        _fail()
    base["plan"]["adoption"] = {"state": "UNAVAILABLE", "reason": "NOT_DECLARED"}
    base = old.validate_body(base)
    if summary != adoption_summary(continuity, base["source"]):
        _fail()
    declaration = continuity["adoption"] if continuity["adoption"]["state"] == "AVAILABLE" else continuity["adoption"].get("declared_decision")
    if declaration and declaration["decision_source"]["commit"] != base["source"]["commit"]:
        _fail()
    for proposal in continuity["proposals"].get("items", []):
        if (proposal["proposal_source"]["repository"] == MACRO
                and proposal["proposal_source"]["commit"] != base["source"]["commit"]
                and (declaration is None or declaration["adoption"]["proposal_source"] != proposal["proposal_source"])):
            _fail()
    bounded_canonical({"ok": True, "result": value}, limit=old.MAX_RESPONSE_BYTES - 1)
    return copy.deepcopy(value)
