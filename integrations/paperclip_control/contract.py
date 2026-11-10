"""Closed Mastermind views of Paperclip; no new task, identity or execution store."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

SCHEMA = "mastermind.paperclip_workspace.v1"
COMMAND_SCHEMA = "mastermind.paperclip_command.v1"
CONFIG_SCHEMA = "mastermind.paperclip_binding.v1"
DONOR_REVISION = "d69631b01b9c658f80bf8bed389863dce82643e1"
MAX_RESPONSE_BYTES = 2_097_152
MAX_REQUEST_BYTES = 32_768
PAGE_SIZE = 50
UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}", re.I)
DIGEST = re.compile(r"[0-9a-f]{64}")
VIEWS = frozenset({"overview", "people", "projects", "goals", "work", "routines", "artifacts", "activity", "task", "routine", "runtime", "receipt"})
STATUSES = frozenset({"backlog", "todo", "in_progress", "in_review", "done", "blocked", "cancelled"})


class PaperclipError(Exception):
    """Public codes only. Never put an upstream URL, token or body into errors."""
    def __init__(self, code: str, *, effect: str = "NOT_APPLIED", status: int = 503):
        super().__init__(code)
        self.code, self.effect, self.status = code, effect, status


def identifier(value: object) -> str:
    if not isinstance(value, str) or UUID.fullmatch(value) is None:
        raise PaperclipError("INVALID_SELECTION", status=400)
    return value.lower()


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_url(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 32 for c in value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return None
        _ = parsed.port
    except ValueError:
        return None
    return value


def read_selection(raw: object) -> dict:
    if type(raw) is not dict or not {"view"} <= set(raw) or set(raw) - {"view", "itemId", "projectId", "status", "offset", "cursor", "requestId"}:
        raise PaperclipError("INVALID_SELECTION", status=400)
    view = raw["view"]
    if view not in VIEWS:
        raise PaperclipError("INVALID_SELECTION", status=400)
    result = {"view": view}
    for key in ("itemId", "projectId", "requestId"):
        if key in raw:
            result[key] = identifier(raw[key])
    if (view in {"task", "routine", "runtime"}) != ("itemId" in result):
        raise PaperclipError("INVALID_SELECTION", status=400)
    if (view == "receipt") != ("requestId" in result):
        raise PaperclipError("INVALID_SELECTION", status=400)
    if "projectId" in result and view not in {"work", "routines", "artifacts"}:
        raise PaperclipError("INVALID_SELECTION", status=400)
    if "status" in raw:
        if view != "work" or raw["status"] not in STATUSES:
            raise PaperclipError("INVALID_SELECTION", status=400)
        result["status"] = raw["status"]
    if "offset" in raw:
        value = raw["offset"]
        if isinstance(value, str) and re.fullmatch(r"0|[1-9][0-9]{0,5}", value):
            value = int(value)
        if type(value) is not int or not 0 <= value <= 100_000 or view not in {"work", "people", "projects", "goals", "routines"}:
            raise PaperclipError("INVALID_SELECTION", status=400)
        result["offset"] = value
    if "cursor" in raw:
        value = raw["cursor"]
        if view != "artifacts" or not isinstance(value, str) or not 1 <= len(value) <= 2048 or any(ord(c) < 32 for c in value):
            raise PaperclipError("INVALID_SELECTION", status=400)
        result["cursor"] = value
    return result


def command_request(raw: object) -> dict:
    if type(raw) is not dict or set(raw) - {"operation", "requestId", "bindingRevision", "title", "description", "projectId"} or not {"operation", "requestId", "bindingRevision", "title", "description"} <= set(raw):
        raise PaperclipError("INVALID_COMMAND", status=400)
    if raw["operation"] != "create_backlog" or not isinstance(raw["bindingRevision"], str) or DIGEST.fullmatch(raw["bindingRevision"]) is None:
        raise PaperclipError("INVALID_COMMAND", status=400)
    for key, maximum in (("title", 300), ("description", 16_000)):
        if not isinstance(raw[key], str) or len(raw[key]) > maximum or "\x00" in raw[key]:
            raise PaperclipError("INVALID_COMMAND", status=400)
    if not raw["title"].strip():
        raise PaperclipError("INVALID_COMMAND", status=400)
    result = dict(raw, requestId=identifier(raw["requestId"]))
    if "projectId" in result:
        result["projectId"] = identifier(result["projectId"])
    return result


# Deliberately omit adapterConfig, env, runtimeConfig, secrets, prompts, raw logs,
# private tool output and arbitrary activity.details from every projection.
_FIELDS = {
    "company": ("id", "name", "description", "status"),
    "people": ("id", "name", "role", "title", "status", "reportsTo", "adapterType", "lastHeartbeatAt", "updatedAt"),
    "projects": ("id", "name", "description", "status", "goalId", "leadAgentId", "updatedAt"),
    "goals": ("id", "title", "description", "level", "status", "parentId", "ownerAgentId", "updatedAt"),
    "work": ("id", "identifier", "title", "description", "status", "priority", "projectId", "goalId", "parentId", "assigneeAgentId", "updatedAt", "statusVersion"),
    "routines": ("id", "title", "name", "description", "status", "projectId", "assigneeAgentId", "updatedAt"),
    "activity": ("id", "actorType", "actorId", "action", "entityType", "entityId", "createdAt"),
    "comments": ("id", "issueId", "authorAgentId", "authorUserId", "body", "createdAt", "updatedAt"),
    "runs": ("id", "routineId", "issueId", "status", "startedAt", "finishedAt", "createdAt"),
    "revisions": ("id", "routineId", "revisionNumber", "changeSummary", "createdAt"),
    "artifacts": ("id", "title", "name", "mediaKind", "sourceKind", "issueId", "projectId", "agentId", "createdAt", "updatedAt", "url"),
    "products": ("id", "issueId", "title", "kind", "provider", "status", "reviewState", "healthStatus", "summary", "url", "executionWorkspaceId", "createdByRunId", "createdAt", "updatedAt"),
    "executions": ("id", "status", "agentId", "adapterType", "startedAt", "finishedAt", "createdAt", "invocationSource", "errorCode"),
}


def project_record(kind: str, row: object, company_id: str, *, allow_scoped_id: bool = False) -> dict:
    if type(row) is not dict or row.get("locked") is True:
        raise PaperclipError("SOURCE_RECORD_UNAVAILABLE")
    # Collection endpoints supply company scope; a contradictory row never crosses it.
    if row.get("companyId") is not None and identifier(row["companyId"]) != company_id:
        raise PaperclipError("SOURCE_SCOPE_MISMATCH")
    if kind == "executions":
        row = dict(row, id=row.get("runId"))
    if kind == "products":
        row = dict(row, kind=row.get("type"))
    raw_id = row.get("id")
    if allow_scoped_id:
        if not isinstance(raw_id, str) or not 1 <= len(raw_id) <= 256 or any(ord(c) < 32 for c in raw_id):
            raise PaperclipError("SOURCE_RECORD_INVALID")
    else:
        identifier(raw_id)
    if kind == "artifacts":
        # Pinned CompanyArtifact uses nested source summaries, not flat task IDs.
        row = dict(row, sourceKind=row.get("source"), url=row.get("href"))
        for nested, key in (("issue", "issueId"), ("project", "projectId"), ("createdByAgent", "agentId")):
            source = row.get(nested)
            if type(source) is dict and source.get("id") is not None:
                row[key] = identifier(source["id"])
    result: dict = {"id": raw_id}
    for key in _FIELDS[kind]:
        value = row.get(key)
        if value is None:
            continue
        if key == "url":
            if (url := safe_url(value)) is not None:
                result[key] = url
        elif isinstance(value, str):
            if kind == "work" and key == "description":
                value = re.sub(r"\n\n<!-- mmos-paperclip-[0-9a-f]{64} -->$", "", value)
            result[key] = value[:16_000 if key in {"body", "description"} else 1000]
        elif type(value) in {int, float} and key in {"statusVersion", "revisionNumber"}:
            if type(value) is int and 0 <= value <= 2**53 - 1:
                result[key] = value
    return result
