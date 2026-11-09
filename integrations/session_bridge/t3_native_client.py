"""Capacity-only foreground client for the EXISTING T3 MCP server.

No listener, authentication, subprocess, database, scheduler or retry owner.
An independently authorized connection injects native tools and their advertised
schemas. A project brief is description, never a native enforcement grant.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

MAX_BYTES = 262_144
MAX_TEXT = 32_768
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/%+@-]{0,511}\Z")
_SECRET = re.compile(r"\bsk-(?:admin-|proj-)?[A-Za-z0-9_-]{20,}|\bBearer\s+\S{16,}")
TERMINAL = frozenset({"completed", "failed", "cancelled", "interrupted", "rolled_back"})


class Unavailable(RuntimeError):
    """Missing capability or unqualified observation; never an empty success."""


class Conflict(Unavailable):
    """Original identity/state changed; no substitute is selected."""


class Rejected(RuntimeError):
    """Typed native pre-effect refusal. Does not permit fallback or replay."""
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Native request refused: {code}")


class EffectUnknown(RuntimeError):
    """Retain exact original operation, connection and thread; never resend."""
    def __init__(self, operation: str, request_id: str, thread_id: str | None) -> None:
        self.operation, self.request_id, self.thread_id = operation, request_id, thread_id
        super().__init__("Native modifying outcome uncertain; reconcile the original request.")


def _text(value: Any, field: str, maximum: int = MAX_TEXT) -> str:
    if (type(value) is not str or not value.strip()
            or len(value.encode()) > maximum
            or any(ord(c) < 32 and c not in "\n\r\t" for c in value)
            or any(ord(c) == 127 for c in value) or _SECRET.search(value)):
        raise ValueError(f"Invalid or credential-like {field}")
    return value


def _id(value: Any, field: str) -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise ValueError(f"Exact {field} required")
    return value


def _int(value: Any, field: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"Invalid {field}")
    return value


def _json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode()


@dataclass(frozen=True, slots=True)
class Scope:
    """Observed connection identity, not OAuth credentials or authorization."""
    connection_id: str
    environment_id: str
    project_id: str
    capacity_provider_id: str = "capacity_fabric"

    def __post_init__(self) -> None:
        for name in ("connection_id", "environment_id", "project_id", "capacity_provider_id"):
            _id(getattr(self, name), name)
        # This client deliberately exposes no arbitrary provider/account override.
        if self.capacity_provider_id != "capacity_fabric":
            raise ValueError("Only the enrolled capacity_fabric instance is accepted")


@dataclass(frozen=True, slots=True)
class Thread:
    scope: Scope
    thread_id: str

    def __post_init__(self) -> None:
        if type(self.scope) is not Scope:
            raise ValueError("Observed native scope required")
        _id(self.thread_id, "thread_id")


@dataclass(frozen=True, slots=True)
class Run:
    thread: Thread
    run_id: str
    request_id: str
    delivery: str
    message_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.thread) is not Thread:
            raise ValueError("Original thread required")
        _id(self.run_id, "run_id"); _id(self.request_id, "request_id")
        if self.message_id is not None:
            _id(self.message_id, "message_id")
        if self.delivery not in {"launched", "queued", "started", "steered", "restarted"}:
            raise ValueError("Invalid native delivery")


@dataclass(frozen=True, slots=True)
class Cursor:
    thread: Thread
    position: int

    def __post_init__(self) -> None:
        if type(self.thread) is not Thread:
            raise ValueError("Original thread required")
        _int(self.position, "position", 0, 2**53 - 1)


@dataclass(frozen=True, slots=True)
class Result:
    run: Run
    status: str
    answer: str | None
    complete: bool
    pending_requests: int | None
    next_cursor: Cursor | None


class T3NativeClient:
    """One authorized native connection; capabilities are discovery, not grants.

    call_tool(name, arguments) returns an MCP CallToolResult. Native transport
    must enforce its own input/output/time limits and preserve original handles.
    schemas is the actual tools/list mapping of tool name to inputSchema.
    """
    def __init__(self, scope: Scope, call_tool: Callable, schemas: Mapping[str, Any]):
        if type(scope) is not Scope or not callable(call_tool) or not isinstance(schemas, Mapping):
            raise ValueError("Observed scope, authorized native caller and tool discovery required")
        self.scope, self.call_tool = scope, call_tool
        self.schemas = json.loads(_json(dict(schemas)))

    def capabilities(self) -> dict[str, bool]:
        names = self.schemas.keys()
        props = self.schemas.get("t3_thread_control", {}).get("properties", {})
        return {
            "read": "t3_thread_read" in names,
            "list": "t3_thread_list" in names,
            "launch": "t3_thread_launch" in names and "orchestrator_capabilities" in names,
            "message": "t3_thread_send" in names,
            "wait": "t3_thread_wait" in names,
            "stop": "t3_thread_interrupt" in names,
            "lifecycle_extension": all(k in props for k in ("action", "expectedUpdatedAt")),
        }

    def _target(self, thread: Thread) -> str:
        if type(thread) is not Thread or thread.scope != self.scope:
            raise Conflict("Thread belongs to a different environment, project or connection")
        return thread.thread_id

    async def _call(self, name: str, args: dict[str, Any], *, modifying: bool = False,
                    request_id: str = "read", thread_id: str | None = None) -> dict:
        schema = self.schemas.get(name)
        if type(schema) is not dict or type(schema.get("properties")) is not dict:
            raise Unavailable(f"Native tool not discovered: {name}")
        if not set(args) <= schema["properties"].keys():
            raise Unavailable(f"Installed {name} schema does not accept the requested operation")
        # Environment is pinned by connection + payload where native schema supports it.
        args = dict(args)
        if "environmentId" in schema["properties"]:
            args["environmentId"] = self.scope.environment_id
        if not set(schema.get("required", [])) <= args.keys():
            raise Unavailable(f"Installed {name} has additional required inputs")
        if len(_json(args)) > MAX_BYTES:
            raise ValueError("Native request exceeds bounded transport contract")
        try:
            value = self.call_tool(name, args)
            if inspect.isawaitable(value):
                value = await value
            if type(value) is not dict or len(_json(value)) > MAX_BYTES:
                raise ValueError("Unqualified native envelope")
            if value.get("isError") is True:
                error = value.get("structuredContent")
                code = error.get("code") if type(error) is dict else None
                if code in {"capability_denied", "provider_unavailable", "model_unavailable",
                            "invalid_input", "thread_not_found", "project_not_found",
                            "thread_conflict", "unsupported_operation", "parent_not_active"}:
                    raise Rejected(code)
                raise ValueError("Unqualified native error/effect")
            if value.get("isError") not in (None, False):
                raise ValueError("Invalid native error flag")
            body = value.get("structuredContent")
            if type(body) is not dict:
                raise ValueError("Native structured result missing")
            return body
        except Rejected:
            raise
        except (Exception, asyncio.CancelledError) as exc:
            if modifying:
                raise EffectUnknown(name, request_id, thread_id) from None
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise Unavailable("Native observation unavailable") from None

    async def capacity_models(self, search: str | None = None) -> tuple[str, ...]:
        args = {} if search is None else {"search": _text(search, "model search", 200)}
        value = await self._call("orchestrator_capabilities", args)
        rows = value.get("providers")
        if type(rows) is not list or len(rows) > 256:
            raise Unavailable("Native provider catalog malformed")
        found = [x for x in rows if type(x) is dict and
                 x.get("providerInstanceId") == self.scope.capacity_provider_id]
        if len(found) != 1:
            raise Unavailable("The exact enrolled Capacity provider is absent or ambiguous")
        provider = found[0]
        if provider.get("canRunChildTask") is not True or provider.get("constraints") != []:
            raise Rejected("provider_unavailable")
        models = provider.get("models")
        if type(models) is not list or len(models) > 1024:
            raise Unavailable("Native Capacity model catalog malformed")
        ids = []
        for model in models:
            if type(model) is not dict:
                raise Unavailable("Native Capacity model row malformed")
            try:
                ids.append(_id(model.get("id"), "model"))
            except ValueError:
                raise Unavailable("Native Capacity model identity malformed") from None
        if len(set(ids)) != len(ids):
            raise Unavailable("Native Capacity model catalog ambiguous")
        return tuple(ids)

    async def _model(self, model: str) -> dict[str, str]:
        _id(model, "model")
        if model not in await self.capacity_models(search=model):
            raise Rejected("model_unavailable")
        return {"instanceId": self.scope.capacity_provider_id, "model": model}

    async def list_threads(self, *, cursor: int = 0, limit: int = 20) -> dict:
        _int(cursor, "cursor", 0, 2**31 - 1); _int(limit, "limit", 1, 100)
        value = await self._call("t3_thread_list", {
            "projectId": self.scope.project_id, "cursor": cursor, "limit": limit,
            "includeSubagents": True})
        rows = value.get("threads")
        if type(rows) is not list or len(rows) > limit:
            raise Unavailable("Native thread page malformed")
        for row in rows:
            if type(row) is not dict or row.get("projectId") != self.scope.project_id:
                raise Conflict("Native list escaped the selected project")
            try:
                _id(row.get("threadId"), "thread_id")
            except ValueError:
                raise Unavailable("Native thread identity malformed") from None
        nxt = value.get("nextCursor")
        if nxt is not None and (type(nxt) is not int or nxt <= cursor):
            raise Unavailable("Native pagination made no progress")
        return value

    async def read(self, thread: Thread, *, cursor: Cursor | None = None,
                   view: str = "messages", limit: int = 20) -> dict:
        tid = self._target(thread); _int(limit, "limit", 1, 100)
        if view not in {"messages", "activity"}:
            raise ValueError("Unsupported native view")
        args: dict[str, Any] = {"threadId": tid, "view": view, "limit": limit,
                                "runLimit": 100, "maxCharsPerItem": 8192}
        if cursor is not None:
            if type(cursor) is not Cursor or cursor.thread != thread:
                raise Conflict("Cursor belongs to another thread/connection")
            args["afterPosition"] = cursor.position
        value = await self._call("t3_thread_read", args)
        self._qualify_read(thread, value, cursor, limit)
        return value

    def _qualify_read(self, thread: Thread, value: dict, cursor: Cursor | None,
                      limit: int) -> None:
        detail, items = value.get("thread"), value.get("items")
        if (type(detail) is not dict or detail.get("threadId") != thread.thread_id
                or detail.get("projectId") != self.scope.project_id):
            raise Conflict("Native observation changed thread/project identity")
        if (type(items) is not list or len(items) > limit or type(value.get("hasMore")) is not bool
                or type(value.get("recentRuns")) is not list):
            raise Unavailable("Incomplete native observation")
        positions = []
        for item in items:
            if (type(item) is not dict or type(item.get("position")) is not int
                    or item["position"] < 0 or type(item.get("textTruncated")) is not bool
                    or item.get("text") is not None and type(item["text"]) is not str):
                raise Unavailable("Malformed native timeline item")
            positions.append(item["position"])
        if positions != sorted(set(positions)):
            raise Unavailable("Native timeline is unordered or duplicated")
        if cursor is not None and positions and positions[0] <= cursor.position:
            raise Conflict("Native timeline repeated an already consumed position")
        nxt = value.get("nextPosition")
        if nxt is not None and (type(nxt) is not int or nxt < 0
                                or cursor is not None and nxt <= cursor.position):
            raise Unavailable("Native cursor did not advance")
        if value["hasMore"] and (nxt is None or not positions or nxt < positions[-1]):
            raise Unavailable("Native page has no recoverable continuation")

    async def read_full_item(self, thread: Thread, item: Mapping[str, Any],
                             *, max_chunks: int = 8) -> tuple[str | None, bool]:
        """Expand native truncated text by exact item/run and increasing offset."""
        tid = self._target(thread); _int(max_chunks, "max_chunks", 1, 16)
        if (not isinstance(item, Mapping) or type(item.get("text")) is not str
                or item.get("sourceThreadId") != tid
                or type(item.get("textTruncated")) is not bool):
            raise ValueError("Original exact native text item required")
        item_id = _id(item.get("itemId"), "item_id")
        run_id = item.get("runId")
        text = item["text"]
        if len(text.encode()) > MAX_TEXT:
            return None, False
        if not item["textTruncated"]:
            return text, True
        offset = item.get("nextTextOffset")
        if type(offset) is not int or offset <= 0:
            raise Unavailable("Truncated native text has no continuation offset")
        for _ in range(max_chunks):
            result = await self._call("t3_thread_read", {
                "threadId": tid, "itemId": item_id, "textOffset": offset,
                "maxCharsPerItem": 8192, "runLimit": 1})
            self._qualify_read(thread, result, None, 1)
            rows = result["items"]
            if len(rows) != 1:
                raise Conflict("Original native text item disappeared")
            chunk = rows[0]
            if (chunk.get("itemId") != item_id or chunk.get("runId") != run_id
                    or chunk.get("sourceThreadId") != tid or type(chunk.get("text")) is not str):
                raise Conflict("Native text expansion changed identity")
            text += chunk["text"]
            if len(text.encode()) > MAX_TEXT:
                return None, False
            if chunk["textTruncated"] is False:
                return text, True
            nxt = chunk.get("nextTextOffset")
            if type(nxt) is not int or nxt <= offset:
                raise Unavailable("Native text offset did not advance")
            offset = nxt
        return None, False

    async def launch(self, *, request_id: str, title: str, prompt: str,
                     model: str, base_sha: str | None = None,
                     writable: bool = False) -> Run:
        _id(request_id, "request_id"); _text(title, "title", 200); _text(prompt, "brief")
        if type(writable) is not bool or writable and base_sha is None:
            raise ValueError("Writing requires a native isolated worktree base")
        if base_sha is not None and (type(base_sha) is not str or not re.fullmatch(r"[0-9a-f]{40}", base_sha)):
            raise ValueError("An exact accepted base commit is required")
        selected = await self._model(model)
        args: dict[str, Any] = {"projectId": self.scope.project_id, "title": title,
                                "message": prompt, "modelSelection": selected}
        if base_sha is not None:
            args["workspaceStrategy"] = {"type": "worktree", "baseRef": base_sha}
        else:
            # Existing project identity is retained. Read-only is task scope, not
            # permission enforcement; the native caller ceiling still governs.
            args["workspaceStrategy"] = {"type": "root"}
        props = self.schemas.get("t3_thread_launch", {}).get("properties", {})
        if "clientRequestId" in props:
            args["clientRequestId"] = request_id
        value = await self._call("t3_thread_launch", args, modifying=True, request_id=request_id)
        try:
            if value.get("projectId") != self.scope.project_id:
                raise ValueError("Native launch project changed")
            return Run(Thread(self.scope, value["threadId"]), value["runId"], request_id, "launched")
        except Exception:
            raise EffectUnknown("t3_thread_launch", request_id, None) from None

    async def send(self, thread: Thread, *, request_id: str, message: str,
                   mode: str = "queue") -> Run:
        tid = self._target(thread); _id(request_id, "request_id"); _text(message, "message")
        if mode not in {"queue", "steer", "restart"}:
            raise ValueError("Use explicit queue, steer or restart; no ambiguous auto mode")
        observed = await self.read(thread, limit=1)
        current = observed["thread"]
        if current.get("providerInstanceId") != self.scope.capacity_provider_id:
            raise Rejected("provider_unavailable")
        await self._model(current.get("model"))
        if current.get("archived") is not False:
            raise Conflict("Archived or unknown archive state is not runnable")
        if mode in {"steer", "restart"} and not current.get("activeRunId"):
            raise Conflict("Steering/restart requires an observed active native run")
        args = {"threadId": tid, "message": message, "mode": mode}
        if "clientRequestId" in self.schemas.get("t3_thread_send", {}).get("properties", {}):
            args["clientRequestId"] = request_id
        value = await self._call("t3_thread_send", args, modifying=True,
                                 request_id=request_id, thread_id=tid)
        try:
            if value.get("threadId") != tid or value.get("delivery") not in {
                    "queue": {"queued", "started"}, "steer": {"steered"},
                    "restart": {"restarted"}}[mode]:
                raise ValueError("Native send effect differs from requested mode")
            return Run(thread, value["runId"], request_id, value["delivery"], value["messageId"])
        except Exception:
            raise EffectUnknown("t3_thread_send", request_id, tid) from None

    async def wait(self, run: Run, *, timeout_ms: int = 10_000,
                   include_children: bool = True) -> dict:
        if type(run) is not Run:
            raise ValueError("Original run required")
        tid = self._target(run.thread); _int(timeout_ms, "timeout", 1, 30_000)
        if type(include_children) is not bool:
            raise ValueError("Explicit child-settlement mode required")
        value = await self._call("t3_thread_wait", {"threadId": tid, "runId": run.run_id,
            "timeoutMs": timeout_ms, "untilDelegatedWorkSettled": include_children})
        if (value.get("threadId") != tid or value.get("runId") != run.run_id
                or type(value.get("timedOut")) is not bool or type(value.get("status")) is not str):
            raise Conflict("Native wait no longer identifies the original run")
        return value

    async def stop(self, thread: Thread, *, request_id: str, run_id: str | None = None,
                   stop_all: bool = False, reason: str = "User-requested stop") -> dict:
        tid = self._target(thread); _id(request_id, "request_id"); _text(reason, "reason", 2000)
        if type(stop_all) is not bool or not stop_all and run_id is None:
            raise ValueError("Select an exact run or explicitly stop the whole thread")
        if run_id is not None:
            _id(run_id, "run_id")
        if stop_all and run_id is not None:
            raise ValueError("Whole-thread Stop cannot masquerade as exact-run interruption")
        args = {"threadId": tid, "reason": reason, "stop": stop_all}
        if run_id is not None:
            args["runId"] = run_id
        if "clientRequestId" in self.schemas.get("t3_thread_interrupt", {}).get("properties", {}):
            args["clientRequestId"] = request_id
        # Stopping does not require working model capacity: never strand expensive execution.
        value = await self._call("t3_thread_interrupt", args, modifying=True,
                                 request_id=request_id, thread_id=tid)
        if value.get("threadId") != tid or value.get("status") not in TERMINAL | {
                "interrupt_requested", "no_active_run"}:
            raise EffectUnknown("t3_thread_interrupt", request_id, tid)
        if not stop_all and value.get("runId") not in (run_id, None):
            raise EffectUnknown("t3_thread_interrupt", request_id, tid)
        return value  # interrupt_requested is not a verified terminal stop.

    async def original_result(self, run: Run, *, cursor: Cursor | None = None,
                              max_pages: int = 5) -> Result:
        """Recover historical exact-run replies even after later turns start.

        Returns incomplete with a cursor rather than equating truncation, pending
        children, or a later run's successful answer with the requested outcome.
        """
        _int(max_pages, "max_pages", 1, 10)
        waited = await self.wait(run, timeout_ms=1, include_children=True)
        status = waited["status"]
        if waited["timedOut"] or status not in TERMINAL:
            return Result(run, status, None, False, None, cursor)
        result_run = waited.get("resultRun")
        rid = run.run_id
        if result_run is not None:
            if (type(result_run) is not dict or result_run.get("status") != status
                    or type(result_run.get("runId")) is not str):
                raise Conflict("Native final-result lineage is malformed")
            rid = _id(result_run["runId"], "native result run")
        found = None; pending = None; truncated = False
        for _ in range(max_pages):
            page = await self.read(run.thread, cursor=cursor, limit=100)
            pending = page["thread"].get("pendingRequestCount")
            if type(pending) is not int or pending < 0:
                raise Unavailable("Pending-request state unknown")
            for item in page["items"]:
                if (item.get("runId") == rid and item.get("type") == "assistant_message"
                        and item.get("sourceThreadId") == run.thread.thread_id):
                    if item["textTruncated"]:
                        full, recovered = await self.read_full_item(run.thread, item)
                        if recovered and full and full.strip():
                            found = full
                        else:
                            truncated = True
                    elif type(item.get("text")) is str and item["text"].strip():
                        found = item["text"]
            nxt = page.get("nextPosition")
            next_cursor = Cursor(run.thread, nxt) if nxt is not None else None
            if not page["hasMore"]:
                complete = status == "completed" and found is not None and not truncated
                return Result(run, status, found if complete else None,
                              complete, pending, next_cursor)
            cursor = next_cursor
        return Result(run, status, None, False, pending, cursor)
