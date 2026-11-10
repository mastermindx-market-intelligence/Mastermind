"""Foreground handoffs to the incumbent T3 CLI, not a session/message runtime.

The caller supplies an authorized native executable and runner. T3 owns its
short-lived command credential, thread, provider, execution and durable history.
There is no credential loader, listener, persistence, retry, polling or scheduler.
A CLI failure after dispatch is uncertain until reconciled at the original T3.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

MAX_RESPONSE_BYTES = 262_144
MAX_MESSAGE_BYTES = 32_768
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/%+-]{0,511}\Z")
_REQUEST = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_SECRET = re.compile(r"\bsk-(?:admin-|proj-)?[A-Za-z0-9_-]{20,}|\bBearer\s+\S{16,}")


def _text(value: Any, field: str, limit: int = MAX_MESSAGE_BYTES) -> str:
    if (type(value) is not str or not value.strip()
            or len(value.encode("utf-8")) > limit
            or any(ord(c) < 32 and c not in "\n\r\t" for c in value)):
        raise ValueError(f"invalid {field}")
    if _SECRET.search(value):
        raise ValueError(f"credential-like content in {field}")
    return value


def _identity(value: Any, field: str) -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise ValueError(f"exact native {field} is required")
    return value


def _strings(values: Any, field: str, *, required: bool = True) -> tuple[str, ...]:
    if (type(values) is not tuple or len(values) > 16
            or (required and not values)):
        raise ValueError(f"bounded immutable {field} required")
    for value in values:
        _text(value, field, 2048)
    return values


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON field")
        out[key] = value
    return out


@dataclass(frozen=True, slots=True)
class HandoffBrief:
    """Task description only; never a permission, execution binding or budget."""
    request_id: str
    project_id: str
    objective: str
    source_ref: str
    acceptance_checks: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    non_goals: tuple[str, ...]
    allowed_write_paths: tuple[str, ...] = ()
    worktree_base: str | None = None

    def __post_init__(self) -> None:
        if type(self.request_id) is not str or _REQUEST.fullmatch(self.request_id) is None:
            raise ValueError("request_id must be a stable lowercase operation label")
        _identity(self.project_id, "project_id")
        _text(self.objective, "objective", 8192)
        _text(self.source_ref, "source_ref", 2048)
        url = urlparse(self.source_ref)
        parts = url.path.split("/")
        if (url.scheme != "https" or url.netloc != "github.com" or url.query or url.fragment
                or len(parts) < 6 or parts[3] != "blob" or _SHA.fullmatch(parts[4]) is None
                or "%" in url.path or any(ord(c) <= 32 or ord(c) == 127 for c in self.source_ref)
                or any(p in (".", "..", "") for p in parts[1:])):
            raise ValueError("source_ref must identify an exact committed GitHub brief")
        for name in ("acceptance_checks", "stop_conditions", "non_goals"):
            _strings(getattr(self, name), name)
        _strings(self.allowed_write_paths, "allowed_write_paths", required=False)
        for value in self.allowed_write_paths:
            p = PurePosixPath(value)
            if (p.is_absolute() or str(p) != value or "\\" in value
                    or any(x in ("..", ".git") for x in p.parts)
                    or ":" in value or any(x in value for x in "*?[]")
                    or any(ord(c) < 32 or ord(c) == 127 for c in value)
                    or value in (".", "")):
                raise ValueError("write scope requires exact relative file/directory paths")
        if self.allowed_write_paths and self.worktree_base is None:
            raise ValueError("code handoffs require an explicit isolated native worktree base")
        if self.worktree_base is not None and (
                type(self.worktree_base) is not str or _SHA.fullmatch(self.worktree_base) is None):
            raise ValueError("worktree_base must be an immutable accepted commit")
        if len(self.render().encode("utf-8")) > MAX_MESSAGE_BYTES:
            raise ValueError("handoff exceeds native prompt budget")

    def document(self) -> dict[str, Any]:
        return {"schema": "mastermind.t3_handoff_brief.v1",
                "request_id": self.request_id, "project_id": self.project_id,
                "objective": self.objective, "source_ref": self.source_ref,
                "acceptance_checks": list(self.acceptance_checks),
                "stop_conditions": list(self.stop_conditions), "non_goals": list(self.non_goals),
                "allowed_write_paths": list(self.allowed_write_paths),
                "worktree_base": self.worktree_base}

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(self.document(), sort_keys=True,
                              separators=(",", ":")).encode()).hexdigest()

    def render(self) -> str:
        return ("Bounded Web-to-T3 handoff. Preserve native project/provider defaults. "
                "This brief supplies task scope, not additional permission. "
                "Do not create replacement jobs, change credentials, or expand write scope.\n"
                + json.dumps(self.document(), ensure_ascii=True, indent=2)
                + "\nReturn to this exact thread with request_id, status, changed files, "
                  "actual checks/results, blockers and source/artifact references. "
                  "A reply is evidence, not acceptance. Stop at a stated boundary.\n")


@dataclass(frozen=True, slots=True)
class CliInvocation:
    argv: tuple[str, ...]
    stdin: str | None = None


@dataclass(frozen=True, slots=True)
class CliResult:
    returncode: int
    stdout: str
    stderr: str = ""  # Raw diagnostics never enter an exception or public proof.


@dataclass(frozen=True, slots=True)
class ThreadReceipt:
    request_id: str
    project_id: str
    thread_id: str
    run_id: str | None
    brief_sha256: str
    delivery: str | None = None

    def __post_init__(self) -> None:
        for field in ("project_id", "thread_id"):
            _identity(getattr(self, field), field)
        if self.run_id is not None:
            _identity(self.run_id, "run_id")
        if re.fullmatch(r"[0-9a-f]{64}", self.brief_sha256 or "") is None:
            raise ValueError("original brief fingerprint required")
        if _REQUEST.fullmatch(self.request_id or "") is None:
            raise ValueError("original request_id required")


class NativeUnavailable(RuntimeError):
    """No qualified native read result; not an empty successful projection."""


class NativeEffectUnknown(RuntimeError):
    """Retain original dispatch/host/process. Never retry or change carrier."""
    def __init__(self, request_id: str, *, thread_id: str | None = None) -> None:
        self.request_id, self.thread_id = request_id, thread_id
        super().__init__("Native modifying-call outcome is uncertain; reconcile the original "
                         "process/thread before any further mutation.")


class T3CliClient:
    """Stateless presentation client over the already installed native T3 CLI.

    The runner must preserve process handles on a lost/long-running call and
    must not perform implicit retries. This class neither launches subprocesses
    itself nor supplies/borrows credentials. The existing authorized host owns
    execution. Use the connected native MCP tools instead when available.
    """
    def __init__(self, executable: str, runner: Callable[[CliInvocation], Any]) -> None:
        if (type(executable) is not str or not executable.startswith("/")
                or "\x00" in executable or not callable(runner)):
            raise ValueError("resolved authorized native CLI and runner required")
        self.executable, self.runner = executable, runner

    async def _call(self, args: tuple[str, ...], *, stdin: str | None = None,
                    modifying: bool = False, request_id: str = "read",
                    thread_id: str | None = None) -> Any:
        try:
            # Native startup warnings can otherwise be written before --json
            # output. Ask the actual CLI for error-only logging; never strip or
            # guess a JSON object from a possibly ambiguous modifying reply.
            result = self.runner(CliInvocation(
                (self.executable, "thread", *args, "--log-level", "error"), stdin))
            if inspect.isawaitable(result):
                result = await result
            if (type(result) is not CliResult or type(result.returncode) is not int
                    or result.returncode != 0 or type(result.stdout) is not str
                    or len(result.stdout.encode("utf-8")) > MAX_RESPONSE_BYTES):
                raise ValueError("native command returned no qualified success")
            return json.loads(result.stdout, object_pairs_hook=_object_pairs,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
        except (Exception, asyncio.CancelledError) as error:
            if modifying:
                raise NativeEffectUnknown(request_id, thread_id=thread_id) from None
            if isinstance(error, asyncio.CancelledError):
                raise
            raise NativeUnavailable("native observation unavailable") from None

    async def list_threads(self, project_id: str) -> tuple[Mapping[str, Any], ...]:
        """Native CLI root inventory; its current implementation excludes subagents."""
        project = _identity(project_id, "project_id")
        value = await self._call(("list", "--project", project, "--json"))
        if (type(value) is not list or len(value) > 1000
                or any(type(x) is not dict or x.get("projectId") != project
                       or type(x.get("threadId")) is not str for x in value)):
            raise NativeUnavailable("native project projection changed")
        for row in value:
            try:
                _identity(row["threadId"], "thread_id")
            except ValueError:
                raise NativeUnavailable("native target identity malformed") from None
        return tuple(value)

    async def launch(self, brief: HandoffBrief) -> ThreadReceipt:
        if type(brief) is not HandoffBrief:
            raise ValueError("validated handoff brief required")
        args = ["start", "--title", "Web handoff " + brief.request_id, "--json"]
        if brief.worktree_base is not None:
            args.extend(("--worktree", brief.worktree_base, "--branch", "web/" + brief.request_id))
        args.extend((brief.project_id, "-"))
        value = await self._call(tuple(args), stdin=brief.render(), modifying=True,
                                 request_id=brief.request_id)
        try:
            if type(value) is not dict or value.get("projectId") != brief.project_id:
                raise ValueError("native launch project differs")
            return ThreadReceipt(brief.request_id, brief.project_id,
                                 value["threadId"], value["runId"], brief.fingerprint)
        except Exception:
            raise NativeEffectUnknown(brief.request_id) from None

    async def send(self, receipt: ThreadReceipt, message: str) -> ThreadReceipt:
        if type(receipt) is not ThreadReceipt:
            raise ValueError("original thread receipt required")
        text = _text(message, "follow-up message")
        value = await self._call(("send", "--json", receipt.thread_id, "-"),
                                 stdin=text, modifying=True, request_id=receipt.request_id,
                                 thread_id=receipt.thread_id)
        try:
            if (type(value) is not dict or value.get("threadId") != receipt.thread_id
                    or value.get("delivery") not in ("queued", "started")):
                raise ValueError("native follow-up identity/delivery differs")
            run = _identity(value["runId"], "run_id")
            if run == receipt.run_id:
                raise ValueError("queued follow-up did not identify a new run")
            return ThreadReceipt(receipt.request_id, receipt.project_id,
                                 receipt.thread_id, run, receipt.brief_sha256, value["delivery"])
        except Exception:
            raise NativeEffectUnknown(receipt.request_id, thread_id=receipt.thread_id) from None

    async def read(self, receipt: ThreadReceipt, *, messages: int = 20) -> Mapping[str, Any]:
        if type(receipt) is not ThreadReceipt or type(messages) is not int or not 1 <= messages <= 40:
            raise ValueError("original receipt and bounded message count required")
        value = await self._call(("show", receipt.thread_id, "--messages", str(messages), "--json"))
        if (type(value) is not dict or type(value.get("thread")) is not dict
                or type(value.get("messages")) is not list or len(value["messages"]) > messages
                or value["thread"].get("threadId") != receipt.thread_id
                or value["thread"].get("projectId") != receipt.project_id
                or any(type(m) is not dict or m.get("role") not in ("user", "assistant")
                       or type(m.get("text")) is not str for m in value["messages"])):
            raise NativeUnavailable("original native thread observation changed")
        return value  # Native status/metadata are retained, not upgraded to acceptance.

    @staticmethod
    def original_answer(receipt: ThreadReceipt, observation: Mapping[str, Any]) -> str | None:
        """Only a completed exact run can supply its answer; never another turn."""
        if type(receipt) is not ThreadReceipt or type(observation) is not dict:
            return None
        thread, messages = observation.get("thread"), observation.get("messages")
        if (type(thread) is not dict or type(messages) is not list
                or thread.get("threadId") != receipt.thread_id
                or thread.get("projectId") != receipt.project_id
                or receipt.run_id is None or thread.get("latestRunId") != receipt.run_id
                or thread.get("status") != "completed" or "activeRunId" not in thread
                or thread["activeRunId"] is not None
                or type(thread.get("pendingRequestCount")) is not int
                or thread["pendingRequestCount"] != 0):
            return None
        for item in reversed(messages):
            if (type(item) is dict and item.get("role") == "assistant"
                    and item.get("runId") == receipt.run_id and type(item.get("text")) is str
                    and item["text"].strip()):
                return item["text"]
        return None
