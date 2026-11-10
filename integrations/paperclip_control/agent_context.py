"""Compact company facts for an existing authenticated project/role reader.

The original host owns selection and grants. Company visibility is not project
membership, execution admission or permission to contact a visible teammate.
"""
from datetime import datetime
import json
import math
import re

from .connections import KINDS, project_connections
from .contract import DONOR_REVISION, SCHEMA, PaperclipError, identifier, project_record

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


def company_context(raw, *, work_ref, now):
    """Validate consumed fields and omit oversized facts rather than truncate.

    This is only a view of a bounded, separately acquired source observation.
    It never binds the Mission's Executive root to a Paperclip issue or agent.
    """
    try:
        if (type(raw) is not dict or raw.get("schema") != SCHEMA or raw.get("view") != "overview"
                or raw.get("state") not in ("CURRENT", "PARTIAL")
                or raw.get("qualifiedRevision") != DONOR_REVISION
                or raw.get("sourceRevision") != DONOR_REVISION
                or type(now) not in (int, float) or not math.isfinite(now)
                or type(work_ref) is not str or re.fullmatch(r"WS:[A-Za-z0-9][A-Za-z0-9._-]{0,127}", work_ref) is None):
            raise ValueError
        for key in ("bindingRevision", "scopeKey"):
            if type(raw.get(key)) is not str or re.fullmatch(r"[0-9a-f]{64}", raw[key]) is None:
                raise ValueError
        stamp = datetime.fromisoformat(raw["observedAt"].replace("Z", "+00:00"))
        if stamp.utcoffset() is None or not 0 <= now - stamp.timestamp() <= 120:
            return unavailable_company("company_read_not_current")
        company_id = identifier(raw["company"]["id"])
        collections = raw["collections"]
        if type(collections) is not dict or set(collections) - {*KINDS, "routines"}:
            raise ValueError
        sanitized = {}
        for kind, source in collections.items():
            if (type(source) is not dict or source["state"] not in ("CURRENT", "UNAVAILABLE")
                    or type(source["items"]) is not list or len(source["items"]) > 50
                    or type(source["hasMore"]) is not bool
                    or type(source.get("restrictedCount", 0)) is not int
                    or not 0 <= source.get("restrictedCount", 0) <= 50
                    or source["state"] == "UNAVAILABLE" and source["items"]):
                raise ValueError
            sanitized[kind] = {**source, "items": [project_record(kind, row, company_id) for row in source["items"]]}
        capabilities = raw["capabilities"]
        if type(capabilities) is not list or capabilities not in ([], ["create_backlog"]):
            raise ValueError
        value = {**raw, "collections": sanitized}
        graph = project_connections(value)
        if raw.get("connections", graph) != graph or graph["state"] == "WITHHELD":
            return unavailable_company("company_relationships_unqualified")
        projects = sanitized.get("projects", {}).get("items", [])
        visible_projects = {identifier(row["id"]): row for row in projects}
        mappings = [row for row in raw["projectBindings"]
                    if row["workRef"] == work_ref and identifier(row["projectId"]) in visible_projects]
        if len(mappings) > 1:
            raise ValueError
        project_id = identifier(mappings[0]["projectId"]) if mappings else None
        omitted_fields = 0

        def facts(row, keys):
            nonlocal omitted_fields
            result = {"id": identifier(row["id"])}
            for key in keys:
                if key not in row:
                    continue
                if type(row[key]) is str and len(row[key]) <= 160:
                    result[key] = row[key]
                else:
                    omitted_fields += 1
            return result

        people = sanitized.get("people", {}).get("items", [])
        tasks = [row for row in sanitized.get("work", {}).get("items", []) if project_id and row.get("projectId") == project_id]
        context = {
            "state": "AVAILABLE", "scope": "VISIBLE_COMPANY_NOT_PROJECT_MEMBERSHIP",
            "companyId": company_id, "workRef": work_ref,
            "projectMapping": "CONFIGURED_VISIBLE_REFERENCE" if project_id else "NOT_OBSERVED_IN_VISIBLE_WINDOW",
            "project": facts(visible_projects[project_id], ("name", "status", "goalId", "leadAgentId")) if project_id else None,
            "people": [facts(row, ("name", "role", "title", "status", "reportsTo")) for row in people[:MAX_PEOPLE]],
            "work": [facts(row, ("identifier", "title", "status", "parentId", "assigneeAgentId")) for row in tasks[:MAX_WORK_ITEMS]],
            "omittedPeople": max(0, len(people) - MAX_PEOPLE), "omittedWork": max(0, len(tasks) - MAX_WORK_ITEMS),
            "omittedFields": omitted_fields, "collectionCoverage": graph["collectionCoverage"],
            "helpAvenues": graph["helpAvenues"], "consistency": graph["consistency"],
            "helpAvenuesScope": "COMPANY_WORKSPACE_NOT_NATIVE_TOOL_BINDINGS",
            "sourceRevision": raw["sourceRevision"], "bindingRevision": raw["bindingRevision"],
            "observedAt": raw["observedAt"], "sourceFreshness": "NOT_ATTESTED_BY_OWNER",
            "executionLineage": "NOT_PROJECTED", "parentConsumption": "NOT_OBSERVED",
            "newWorkAuthorized": False,
        }
        if len(json.dumps(context, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_CONTEXT_BYTES:
            return unavailable_company("company_context_over_budget")
        return context
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError, PaperclipError):
        return unavailable_company("invalid_company_document")
