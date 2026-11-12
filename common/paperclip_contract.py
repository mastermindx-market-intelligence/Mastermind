"""Closed company-context facts shared by readers and integration producers.

This standard-library contract owns validation only, never source acquisition,
project membership, execution admission or a second state store.
"""
from __future__ import annotations

from datetime import datetime
import json
import re

DONOR_REVISION = "d69631b01b9c658f80bf8bed389863dce82643e1"

UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}", re.I)
KINDS = {"people": "agent", "projects": "project", "goals": "goal", "work": "issue"}


class PaperclipError(Exception):
    """Public codes only. Never put an upstream URL, token or body into errors."""
    def __init__(self, code: str, *, effect: str = "NOT_APPLIED", status: int = 503):
        super().__init__(code)
        self.code, self.effect, self.status = code, effect, status


def identifier(value: object) -> str:
    if not isinstance(value, str) or UUID.fullmatch(value) is None:
        raise PaperclipError("INVALID_SELECTION", status=400)
    return value.lower()


MAX_CONTEXT_BYTES = 8192
MAX_PEOPLE = 16
MAX_WORK_ITEMS = 8


def unavailable_company(reason):
    return {"state": "UNAVAILABLE", "reason": reason, "newWorkAuthorized": False}


def validate_context(value, *, work_ref):
    """Closed consumed facts only; the authenticated reader owns their source."""
    unavailable_reasons = {"company_read_not_current", "company_relationships_unqualified",
        "company_context_over_budget", "invalid_company_document", "company_not_composed",
        "company_current_read_unavailable"}
    if type(value) is not dict:
        raise ValueError("invalid_company_context")
    if value.get("state") == "UNAVAILABLE":
        if value.get("reason") not in unavailable_reasons or value != unavailable_company(value["reason"]):
            raise ValueError("invalid_company_context")
        return value
    keys = {"state", "scope", "companyId", "workRef", "projectMapping", "project", "people", "work",
        "omittedPeople", "omittedWork", "omittedFields", "collectionCoverage", "helpAvenues", "consistency",
        "helpAvenuesScope", "sourceRevision", "bindingRevision", "observedAt", "sourceFreshness",
        "executionLineage", "parentConsumption", "newWorkAuthorized"}
    if (set(value) != keys or value["state"] != "AVAILABLE" or value["workRef"] != work_ref
            or value["scope"] != "VISIBLE_COMPANY_NOT_PROJECT_MEMBERSHIP"
            or value["helpAvenuesScope"] != "COMPANY_WORKSPACE_NOT_NATIVE_TOOL_BINDINGS"
            or value["sourceRevision"] != DONOR_REVISION or value["sourceFreshness"] != "NOT_ATTESTED_BY_OWNER"
            or value["executionLineage"] != "NOT_PROJECTED" or value["parentConsumption"] != "NOT_OBSERVED"
            or value["newWorkAuthorized"] is not False or value["consistency"] != "SEPARATE_READS_NOT_ATOMIC"
            or type(value["bindingRevision"]) is not str or re.fullmatch(r"[0-9a-f]{64}", value["bindingRevision"]) is None):
        raise ValueError("invalid_company_context")
    identifier(value["companyId"])
    if datetime.fromisoformat(value["observedAt"].replace("Z", "+00:00")).utcoffset() is None:
        raise ValueError("invalid_company_context")
    for name in ("omittedPeople", "omittedWork", "omittedFields"):
        if type(value[name]) is not int or not 0 <= value[name] <= 1024:
            raise ValueError("invalid_company_context")
    project = value["project"]
    if (value["projectMapping"] != ("CONFIGURED_VISIBLE_REFERENCE" if project is not None
            else "NOT_OBSERVED_IN_VISIBLE_WINDOW") or project is None and value["work"]):
        raise ValueError("invalid_company_context")
    def facts(rows, fields, limit):
        if type(rows) is not list or len(rows) > limit:
            raise ValueError("invalid_company_context")
        seen = set()
        for row in rows:
            if type(row) is not dict or "id" not in row or set(row) - {"id", *fields}:
                raise ValueError("invalid_company_context")
            native_id = identifier(row["id"])
            if native_id in seen or any(type(v) is not str or len(v) > 160 for k, v in row.items() if k != "id"):
                raise ValueError("invalid_company_context")
            seen.add(native_id)
    facts([] if project is None else [project], ("name", "status", "goalId", "leadAgentId"), 1)
    facts(value["people"], ("name", "role", "title", "status", "reportsTo"), MAX_PEOPLE)
    facts(value["work"], ("identifier", "title", "status", "parentId", "assigneeAgentId"), MAX_WORK_ITEMS)
    coverage = value["collectionCoverage"]
    if type(coverage) is not list or [r.get("collection") for r in coverage if type(r) is dict] != list(KINDS):
        raise ValueError("invalid_company_context")
    for row in coverage:
        if (set(row) != {"collection", "state", "loaded", "hasMore", "restrictedCount"}
                or row["state"] not in {"CURRENT", "UNAVAILABLE", "NOT_REQUESTED"}
                or type(row["hasMore"]) is not bool
                or any(type(row[k]) is not int or not 0 <= row[k] <= 50 for k in ("loaded", "restrictedCount"))):
            raise ValueError("invalid_company_context")
    avenues = value["helpAvenues"]
    if (type(avenues) is not list or len(avenues) != 6 or avenues[:2] != [
            {"kind": "browse_team", "state": "READ_ROUTE"}, {"kind": "inspect_runtime", "state": "READ_ROUTE"}]
            or avenues[2] not in [{"kind": "create_backlog", "state": state}
                for state in ("COMMAND_BOUND", "NOT_BOUND_IN_THIS_SURFACE")]
            or avenues[3:] != [{"kind": kind, "state": "NOT_BOUND_IN_THIS_SURFACE"}
                for kind in ("consult", "delegate", "resume")]):
        raise ValueError("invalid_company_context")
    if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode()) > MAX_CONTEXT_BYTES:
        raise ValueError("invalid_company_context")
    return value
