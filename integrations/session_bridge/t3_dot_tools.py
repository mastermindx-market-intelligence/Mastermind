"""Dot-facing tools over the existing native T3 clients, not another agent runtime.

The authenticated host injects its incumbent fleet/access owner. Tool arguments
never select a credential, URL, executable, permission ceiling, or physical model
account. Native T3 remains the thread/run/queue owner. This module stores nothing,
starts no process, retries nothing, and never accepts a child's claimed success.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import re
from typing import Any, Protocol

from .t3_native_client import (
    Conflict, Cursor, EffectUnknown, LifecycleSnapshot, ResultProgress, Run,
    Scope, Thread, T3NativeClient, Unavailable, Rejected,
)
from .t3_project_team_inventory import read_native_inventory

MAX_BYTES = 256 * 1024
MAX_SNAPSHOT_TARGETS = 12
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,255}\Z")
_SECRET = re.compile(
    r"(?i)\b(?:bearer\s+|(?:api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"authorization|password|client[_-]?secret)\s*[=:]\s*)[^\s,;\"}]{8,}"
    r"|\b(?:sk-(?:proj-|admin-)?|xox[bpars]-)[A-Za-z0-9_-]{16,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
)
_PRIVATE_ITEMS = frozenset({"reasoning", "reasoning_delta", "thinking", "analysis", "private_reasoning"})


class FleetOwner(Protocol):
    """An installed access/connection owner, not a caller-supplied grant.

    authorize must check the current authenticated principal and exact scope on
    EACH call; a listed environment, a receipt, or a prompt is never a grant.
    client must return an already-authorized, exact native connection. Subsequent
    native calls retain T3's own access/permission/admission checks.
    """
    async def authorize(self, principal: Any, *, operation: str,
                        environment_id: str | None, project_id: str | None,
                        thread_id: str | None, arguments: dict) -> None: ...
    async def environments(self, principal: Any) -> dict: ...
    async def projects(self, principal: Any, environment_id: str, *, cursor: int, limit: int) -> dict: ...
    async def client(self, principal: Any, environment_id: str, project_id: str) -> T3NativeClient: ...


def _object(properties: dict, required: tuple[str, ...] = ()) -> dict:
    return {"type": "object", "properties": properties, "required": list(required),
            "additionalProperties": False}


def _string(maximum: int = 256, *, enum: tuple | None = None) -> dict:
    result = {"type": "string", "minLength": 1, "maxLength": maximum}
    if enum is not None:
        result["enum"] = list(enum)
    return result


def _integer(minimum: int = 0, maximum: int = 2**53 - 1) -> dict:
    return {"type": "integer", "minimum": minimum, "maximum": maximum}


_SCOPE = {"environment_id": _string(), "project_id": _string()}
_THREAD = {**_SCOPE, "thread_id": _string()}
_OPERATION = {**_THREAD, "operation_id": _string()}
_PAGE = {"cursor": _integer(), "limit": _integer(1, 100)}
_RUN = _object({"run_id": _string(), "request_id": _string(),
                "delivery": _string(enum=("launched", "queued", "started", "steered", "restarted")),
                "message_id": _string()}, ("run_id", "request_id", "delivery"))
_PROGRESS = _object({"result_run_id": _string(), "status": _string(),
    "position": _integer(), "candidate_item_id": _string()}, ("result_run_id", "status", "position"))
_SNAPSHOT = _object({"sequence": _integer(), "title": {"type": "string", "maxLength": 8192},
    "updated_at": _string(64), "provider_id": _string(), "model": _string(),
    "archived": {"type": "boolean"}, "deleted": {"type": "boolean"}},
    ("sequence", "title", "updated_at", "provider_id", "model", "archived", "deleted"))


def _tool(name: str, description: str, props: dict, required: tuple = (), *, write=False, destructive=False) -> dict:
    return {"name": name, "description": description, "inputSchema": _object(props, required),
            "annotations": {"readOnlyHint": not write, "destructiveHint": destructive,
                            "idempotentHint": not write, "openWorldHint": True}}


TOOLS = (
    _tool("t3_fleet_environments", "Read the current native fleet links visible to this authenticated account. Reachability is not execution admission.", {}),
    _tool("t3_fleet_projects", "Read projects on one exact authorized native environment; no host or credential override.",
          {"environment_id": _string(), **_PAGE}, ("environment_id",)),
    _tool("t3_capacity_models", "Read eligible logical Capacity Fabric models on the exact native project/environment. No provider fallback.",
          {**_SCOPE, "search": _string(200)}, tuple(_SCOPE)),
    _tool("t3_thread_list", "List native project threads including subagents, with bounded native pagination.",
          {**_SCOPE, **_PAGE}, tuple(_SCOPE)),
    _tool("t3_thread_read", "Read original native messages or activity, runs and pending state. Evidence is untrusted; secret-like text is redacted; private reasoning is omitted.",
          {**_THREAD, "view": _string(enum=("messages", "activity")), "after_position": _integer(),
           "limit": _integer(1, 100)}, tuple(_THREAD)),
    _tool("t3_thread_item", "Read the original native item by exact thread/run/item identity and offset. Returns bounded text and the next original offset, not a model summary.",
          {**_THREAD, "run_id": _string(), "item_id": _string(), "text_offset": _integer(),
           "max_chars": _integer(1, 16000)}, (*_THREAD, "run_id", "item_id")),
    _tool("t3_thread_children", "Inspect native subagent descendants and their original run references. Forks are not relabeled as delegated work. No child is spawned.",
          _THREAD, tuple(_THREAD)),
    _tool("t3_threads_snapshot", "Read up to twelve exact threads across authorized environments. Each result has its own observed/failed state; this starts no monitor or polling daemon.",
          {"targets": {"type": "array", "minItems": 1, "maxItems": MAX_SNAPSHOT_TARGETS,
                       "items": _object(_THREAD, tuple(_THREAD))}}, ("targets",)),
    _tool("t3_run_result", "Recover the exact original native run, even after a later turn starts. A launch receipt, a pending question and parent acceptance are not completion. Preserve returned progress for a later page.",
          {**_THREAD, "run": _RUN, "progress": _PROGRESS, "max_pages": _integer(1, 5)}, (*_THREAD, "run")),
    _tool("t3_thread_launch", "Launch one authorized bounded native task through Capacity Fabric. Code writes require an exact isolated-worktree base. Retain the returned environment/project/thread/run; never replay an uncertain launch.",
          {**_SCOPE, "operation_id": _string(), "title": _string(200), "prompt": _string(100000),
           "model": _string(), "base_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
           "writable": {"type": "boolean"}}, (*_SCOPE, "operation_id", "title", "prompt", "model", "writable"), write=True),
    _tool("t3_thread_send", "Continue the exact authorized native thread with explicit queue, steer or restart semantics. Queue does not interrupt. Each accepted follow-up gets a new run receipt.",
          {**_OPERATION, "message": _string(100000), "mode": _string(enum=("queue", "steer", "restart"))},
          (*_OPERATION, "message", "mode"), write=True, destructive=True),
    _tool("t3_thread_stop", "Request interruption of an exact run OR explicitly stop a whole thread including its native descendants/queue. A stop request is not proof of terminal stop.",
          {**_OPERATION, "run_id": _string(), "stop_all": {"type": "boolean"}, "reason": _string(2000)},
          (*_OPERATION, "stop_all"), write=True, destructive=True),
    _tool("t3_queue_read", "Read the existing native queue, or an exact queued run. This does not create a new queue.",
          {**_THREAD, **_PAGE, "queued_run_id": _string()}, tuple(_THREAD)),
    _tool("t3_queue_change", "Edit, cancel, reorder or promote one native queued run. Editing requires its observed full-text SHA-256. Preconditions are native/client checks, not a fabricated atomic CAS.",
          {**_OPERATION, "action": _string(enum=("edit", "cancel", "reorder", "promote_to_steer")),
           "queued_run_id": _string(), "text": _string(100000),
           "expected_text_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
           "before_run_id": _string(), "target_run_id": _string()},
          (*_OPERATION, "action", "queued_run_id"), write=True, destructive=True),
    _tool("t3_questions_read", "Read a thread's actual pending user-input questions. Permission approvals are never exposed or granted.",
          {**_THREAD, "question_id": _string()}, tuple(_THREAD)),
    _tool("t3_question_answer", "Answer an actual native user-input question within the assigned task. This cannot grant permission, credentials, new spending or a larger mission.",
          {**_OPERATION, "question_id": _string(), "answers": {"type": "object", "minProperties": 1,
           "maxProperties": 32, "additionalProperties": True}}, (*_OPERATION, "question_id", "answers"), write=True),
    _tool("t3_thread_configuration", "Inspect native model/permission metadata and the strict native revision guard when installed. Inspection grants no permission.", _THREAD, tuple(_THREAD)),
    _tool("t3_thread_set_model", "Select an approved logical Capacity model on an idle settled thread using the installed atomic native sequence guard. No generic provider/account or permission-mode changes.",
          {**_OPERATION, "snapshot": _SNAPSHOT, "model": _string()}, (*_OPERATION, "snapshot", "model"), write=True),
    _tool("t3_thread_archive", "Archive or restore one observed idle native thread. Does not delete files, worktrees or history. Requires the exact observed updated_at value.",
          {**_OPERATION, "expected_updated_at": _string(64), "archived": {"type": "boolean"}},
          (*_OPERATION, "expected_updated_at", "archived"), write=True, destructive=True),
    _tool("t3_thread_delete", "Explicitly tombstone one idle native thread using its atomic native sequence/title guard. Never deletes a project, worktree or file. Requires separate exact-target destructive authorization.",
          {**_OPERATION, "snapshot": _SNAPSHOT, "confirmed_title": {"type": "string", "maxLength": 8192},
           "confirm_delete": {"type": "boolean", "enum": [True]}},
          (*_OPERATION, "snapshot", "confirmed_title", "confirm_delete"), write=True, destructive=True),
)
_BY_NAME = {tool["name"]: tool for tool in TOOLS}


def _validate(value: Any, schema: dict, path: str = "arguments") -> None:
    """Closed small JSON contract used by this adapter (not general JSON Schema)."""
    kind = schema.get("type")
    if kind == "object":
        if type(value) is not dict:
            raise ValueError(f"{path}: object required")
        props = schema.get("properties", {})
        if not set(schema.get("required", ())) <= value.keys():
            raise ValueError(f"{path}: required field missing")
        if schema.get("additionalProperties") is False and not value.keys() <= props.keys():
            raise ValueError(f"{path}: unknown field")
        if not schema.get("minProperties", 0) <= len(value) <= schema.get("maxProperties", 100):
            raise ValueError(f"{path}: property count exceeded")
        for key, child in value.items():
            if type(key) is not str:
                raise ValueError(f"{path}: string property required")
            if key in props:
                _validate(child, props[key], path + "." + key)
    elif kind == "array":
        if type(value) is not list or not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 100):
            raise ValueError(f"{path}: bounded array required")
        for child in value:
            _validate(child, schema["items"], path + "[]")
    elif kind == "string":
        if type(value) is not str or not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 100000):
            raise ValueError(f"{path}: bounded text required")
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            raise ValueError(f"{path}: invalid text shape")
    elif kind == "integer":
        if type(value) is not int or not schema.get("minimum", 0) <= value <= schema.get("maximum", 2**53 - 1):
            raise ValueError(f"{path}: bounded integer required")
    elif kind == "boolean" and type(value) is not bool:
        raise ValueError(f"{path}: boolean required")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: unsupported selection")


def _encoded(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode()


def _plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {key: _plain(child) for key, child in dataclasses.asdict(value).items()}
    if isinstance(value, tuple):
        return [_plain(child) for child in value]
    if type(value) is list:
        return [_plain(child) for child in value]
    if type(value) is dict:
        return {key: _plain(child) for key, child in value.items()}
    return value


def _public(value: Any) -> tuple[Any, bool]:
    """Best-effort secret-pattern redaction; upstream scope remains the boundary."""
    changed = False
    def walk(item):
        nonlocal changed
        if type(item) is str:
            redacted = _SECRET.sub("[REDACTED]", item)
            changed = changed or redacted != item
            return redacted
        if type(item) is list:
            result = []
            for child in item:
                if type(child) is dict and child.get("type") in _PRIVATE_ITEMS:
                    changed = True
                    continue
                result.append(walk(child))
            return result
        if type(item) is dict:
            return {key: walk(child) for key, child in item.items()}
        return item
    result = walk(_plain(value))
    return result, changed


class T3DotTools:
    def __init__(self, owner: FleetOwner):
        if any(not callable(getattr(owner, name, None)) for name in
               ("authorize", "environments", "projects", "client")):
            raise TypeError("An installed fleet/access owner is required")
        self.owner = owner

    def catalog(self) -> list[dict]:
        return json.loads(_encoded(TOOLS))

    async def _authorize(self, principal, name, args):
        await self.owner.authorize(principal, operation=name,
            environment_id=args.get("environment_id"), project_id=args.get("project_id"),
            thread_id=args.get("thread_id"), arguments=args)

    async def _client(self, principal, args) -> T3NativeClient:
        client = await self.owner.client(principal, args["environment_id"], args["project_id"])
        if (type(client) is not T3NativeClient or client.scope.environment_id != args["environment_id"]
                or client.scope.project_id != args["project_id"]):
            raise Conflict("Owner returned another native environment/project")
        return client

    async def call(self, principal: Any, name: str, arguments: dict) -> dict:
        tool = _BY_NAME.get(name) if type(name) is str else None
        if tool is None:
            return self._failure("UNAVAILABLE", "TOOL_NOT_EXPOSED")
        write = not tool["annotations"]["readOnlyHint"]
        dispatched = False
        try:
            if len(_encoded(arguments)) > MAX_BYTES:
                raise ValueError("Input exceeds bounded contract")
            _validate(arguments, tool["inputSchema"])
            for field in ("environment_id", "project_id", "thread_id", "operation_id"):
                if field in arguments and not _ID.fullmatch(arguments[field]):
                    raise ValueError("Invalid native identity")
            await self._authorize(principal, name, arguments)
            # The native client owns the actual dispatch/effect classification.
            result = await self._dispatch(principal, name, dict(arguments))
            dispatched = write
            public, redacted = _public(result)
            # Recheck after observation: no read leaked after an observed revocation.
            await self._authorize(principal, name, arguments)
            response = {"schema": "mastermind.t3_dot_result.v1", "status": "OBSERVED",
                        "operation": name, "data": public, "redacted": redacted,
                        "parent_accepted": False, "retry_allowed": False}
            if len(_encoded(response)) > MAX_BYTES:
                if write:
                    raise EffectUnknown(name, arguments.get("operation_id", "unknown"), arguments.get("thread_id"))
                raise Unavailable("Result exceeds bounded contract; narrow the read")
            return response
        except EffectUnknown as exc:
            return self._failure("EFFECT_UNKNOWN", "ORIGINAL_NATIVE_EFFECT_UNCERTAIN",
                operation=name, environment_id=arguments.get("environment_id"),
                project_id=arguments.get("project_id"), thread_id=getattr(exc, "thread_id", None),
                operation_id=arguments.get("operation_id"))
        except Rejected as exc:
            if dispatched:
                return self._failure("EFFECT_UNKNOWN", "POST_EFFECT_ACCESS_CHANGED", operation=name,
                                     operation_id=arguments.get("operation_id"))
            return self._failure("REJECTED", exc.code if hasattr(exc, "code") else "NATIVE_REJECTED")
        except Conflict:
            return self._failure("EFFECT_UNKNOWN" if dispatched else "CONFLICT", "ORIGINAL_BINDING_CHANGED")
        except Unavailable:
            return self._failure("EFFECT_UNKNOWN" if dispatched else "UNAVAILABLE", "NATIVE_CAPABILITY_UNAVAILABLE")
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError, UnicodeError):
            return self._failure("EFFECT_UNKNOWN" if dispatched else "INVALID_ARGUMENT", "UNQUALIFIED_INPUT_OR_RESULT")
        except asyncio.CancelledError:
            raise
        except Exception:
            return self._failure("EFFECT_UNKNOWN" if write else "UNAVAILABLE", "OWNER_OR_TRANSPORT_UNAVAILABLE",
                                 operation=name, operation_id=arguments.get("operation_id") if type(arguments) is dict else None)

    @staticmethod
    def _failure(status, code, **refs):
        return {"schema": "mastermind.t3_dot_result.v1", "status": status, "code": code,
                "original": {key: value for key, value in refs.items() if value is not None},
                "retry_allowed": False, "parent_accepted": False}

    async def _dispatch(self, principal, name, args):
        if name == "t3_fleet_environments":
            return await self.owner.environments(principal)
        if name == "t3_fleet_projects":
            return await self.owner.projects(principal, args["environment_id"],
                cursor=args.get("cursor", 0), limit=args.get("limit", 20))
        if name == "t3_threads_snapshot":
            keys = [(row["environment_id"], row["project_id"], row["thread_id"]) for row in args["targets"]]
            if len(keys) != len(set(keys)):
                raise ValueError("Duplicate snapshot target")
            semaphore = asyncio.Semaphore(3)
            async def observe(row):
                async with semaphore:
                    value = await self.call(principal, "t3_thread_read", {**row, "limit": 1})
                    data = value.get("data")
                    return {"target": row, "status": value["status"], "code": value.get("code"),
                            "thread": data.get("thread") if type(data) is dict else None,
                            "next_position": data.get("nextPosition") if type(data) is dict else None}
            results = await asyncio.gather(*(observe(row) for row in args["targets"]))
            return {"threads": results, "complete": all(row["status"] == "OBSERVED" for row in results),
                    "atomic_snapshot": False, "monitor_started": False}
        client = await self._client(principal, args)
        if name == "t3_capacity_models":
            return {"models": await client.capacity_models(args.get("search")), "capabilities": client.capabilities()}
        if name == "t3_thread_list":
            return await client.list_threads(cursor=args.get("cursor", 0), limit=args.get("limit", 20))
        if name == "t3_thread_launch":
            return await client.launch(request_id=args["operation_id"], title=args["title"],
                prompt=args["prompt"], model=args["model"], base_sha=args.get("base_sha"), writable=args["writable"])
        thread = Thread(client.scope, args["thread_id"])
        if name == "t3_thread_read":
            cursor = Cursor(thread, args["after_position"]) if "after_position" in args else None
            return await client.read(thread, cursor=cursor, view=args.get("view", "messages"), limit=args.get("limit", 20))
        if name == "t3_thread_item":
            await client.read(thread, limit=1)
            body = await client._call("t3_thread_read", {"threadId": thread.thread_id,
                "itemId": args["item_id"], "textOffset": args.get("text_offset", 0),
                "maxCharsPerItem": args.get("max_chars", 8192), "runLimit": 1})
            client._qualify_read(thread, body, None, 1)
            rows = body["items"]
            item = rows[0] if len(rows) == 1 else None
            if (type(item) is not dict or item.get("itemId") != args["item_id"]
                    or item.get("sourceThreadId") != thread.thread_id or item.get("runId") != args["run_id"]):
                raise Conflict("Native item does not match original thread/run")
            if item.get("type") in _PRIVATE_ITEMS:
                raise Rejected("unsupported_operation")
            if item.get("textTruncated") is True and (
                    type(item.get("nextTextOffset")) is not int
                    or item["nextTextOffset"] <= args.get("text_offset", 0)):
                raise Conflict("Native text continuation did not advance")
            return body
        if name == "t3_thread_children":
            await client.read(thread, limit=1)
            inventory = await read_native_inventory(client._call,
                environment_id=client.scope.environment_id, project_id=client.scope.project_id)
            selected = inventory.descendants(thread.thread_id)
            return {"root_thread_id": thread.thread_id, "environment_id": client.scope.environment_id,
                    "project_id": client.scope.project_id, "observed_at": inventory.observed_at,
                    "threads": [row for row in inventory.threads if row.thread_id in selected],
                    "complete_paginated_read": True, "atomic_snapshot": False}
        if name == "t3_run_result":
            run = Run(thread, **args["run"])
            progress = None
            if "progress" in args:
                p = args["progress"]
                progress = ResultProgress(run, p["result_run_id"], p["status"],
                    Cursor(thread, p["position"]), p.get("candidate_item_id"))
            result = await client.original_result(run, progress=progress, max_pages=args.get("max_pages", 3))
            value = _plain(result)
            if result.progress is not None:
                p = result.progress
                value["progress"] = {"result_run_id": p.result_run_id, "status": p.status,
                    "position": p.cursor.position, **({"candidate_item_id": p.candidate_item_id} if p.candidate_item_id else {})}
            return value
        if name == "t3_thread_send":
            return await client.send(thread, request_id=args["operation_id"], message=args["message"], mode=args["mode"])
        if name == "t3_thread_stop":
            return await client.stop(thread, request_id=args["operation_id"], run_id=args.get("run_id"),
                stop_all=args["stop_all"], reason=args.get("reason", "Explicit authorized Dot stop"))
        if name == "t3_queue_read":
            if "queued_run_id" in args:
                value = await client.queue_read(thread, args["queued_run_id"])
                if value.get("truncated") is False and type(value.get("text")) is str:
                    value = {**value, "text_sha256": hashlib.sha256(value["text"].encode()).hexdigest()}
                return value
            return await client.queue_list(thread, cursor=args.get("cursor", 0), limit=args.get("limit", 20))
        if name == "t3_queue_change":
            names = ("action", "queued_run_id", "text", "expected_text_sha256", "before_run_id", "target_run_id")
            return await client.queue_change(thread, request_id=args["operation_id"],
                                             **{key: args[key] for key in names if key in args})
        if name == "t3_questions_read":
            if "question_id" in args:
                return await client.read_question(thread, args["question_id"])
            return {"question_ids": await client.pending_questions(thread), "permission_approvals": "NOT_EXPOSED"}
        if name == "t3_question_answer":
            return await client.answer_question(thread, request_id=args["question_id"],
                operation_id=args["operation_id"], answers=args["answers"])
        if name == "t3_thread_configuration":
            value = {"configuration": await client.configuration(thread), "capabilities": client.capabilities()}
            if client.capabilities()["lifecycle_extension"]:
                snapshot = dataclasses.asdict(await client.lifecycle_snapshot(thread))
                snapshot.pop("thread")
                value["snapshot"] = snapshot
            return value
        if name == "t3_thread_set_model":
            return await client.set_model_atomic(LifecycleSnapshot(thread, **args["snapshot"]),
                request_id=args["operation_id"], model=args["model"])
        if name == "t3_thread_delete":
            return await client.delete(LifecycleSnapshot(thread, **args["snapshot"]),
                request_id=args["operation_id"], confirmation_title=args["confirmed_title"],
                confirm_delete=args["confirm_delete"])
        if name == "t3_thread_archive":
            return await client.archive(thread, request_id=args["operation_id"],
                expected_updated_at=args["expected_updated_at"], archived=args["archived"])
        raise Unavailable("Tool not implemented")
