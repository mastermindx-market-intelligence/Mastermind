"""Native-parent composition over T3's existing child and communication owners.

No agent runner, wake loop, task store, provider switch or permission authority.
The injected native connection authenticates its own parent. Source objects and
client-side checks are task constraints, not an atomic admission/security fence.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Mapping

from .t3_mission_brief import MissionBrief, _text
from .t3_native_client import Conflict, EffectUnknown, Rejected, Run, T3NativeClient, Thread, Unavailable, _id

ROLES = frozenset({"implementation", "research", "review", "design", "test", "general"})
KINDS = frozenset({"question", "progress", "blocker", "result", "correction", "direction"})
STATUSES = frozenset({"queued", "running", "waiting", "completed", "failed", "cancelled", "interrupted"})
TERMINAL = STATUSES - {"queued", "running", "waiting"}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _paths(paths: tuple[str, ...], parents: tuple[str, ...]) -> None:
    if type(paths) is not tuple or len(paths) > 32 or len(set(paths)) != len(paths):
        raise ValueError("Bounded unique immutable write paths required")
    for value in paths:
        if type(value) is not str:
            raise ValueError("Exact relative write path required")
        path = PurePosixPath(value)
        if (path.is_absolute() or str(path) != value or value in {"", "."}
                or any(part in {"..", ".git"} for part in path.parts)
                or any(c in value for c in "\\:*?[]%") or any(ord(c) <= 32 for c in value)):
            raise ValueError("Exact relative write path required")
        if not any(value == parent or value.startswith(parent + "/") for parent in parents):
            raise ValueError("Child write scope exceeds the parent mission")


@dataclass(frozen=True, slots=True)
class ChildBrief:
    mission: MissionBrief
    child_key: str
    objective: str
    phase_ids: tuple[str, ...]
    acceptance: tuple[str, ...]
    allowed_write_paths: tuple[str, ...] = ()
    role: str = "research"

    def __post_init__(self) -> None:
        if type(self.mission) is not MissionBrief:
            raise ValueError("Complete original mission required")
        _id(self.child_key, "child key")
        _text(self.objective, "child objective", 4096)
        if self.role not in ROLES:
            raise ValueError("Unsupported native child role")
        if (type(self.phase_ids) is not tuple or not self.phase_ids or len(self.phase_ids) > 32
                or len(set(self.phase_ids)) != len(self.phase_ids)
                or not set(self.phase_ids) <= {p.phase_id for p in self.mission.phases}):
            raise ValueError("Child phases must belong to the original mission")
        if type(self.acceptance) is not tuple or not 1 <= len(self.acceptance) <= 16:
            raise ValueError("Bounded child acceptance required")
        for check in self.acceptance:
            _text(check, "child acceptance", 2048)
        _paths(self.allowed_write_paths, self.mission.allowed_write_paths)
        if len(self.render().encode()) > 65536:
            raise ValueError("Child brief exceeds delivery budget; do not truncate scope")

    @property
    def isolation(self) -> str:
        return "worktree" if self.allowed_write_paths else "shared"

    def document(self) -> dict:
        return {"schema": "mastermind.t3_child_brief.v1", "child_key": self.child_key,
                "parent_mission": self.mission.document(), "parent_sha256": self.mission.fingerprint,
                "objective": self.objective, "phase_ids": list(self.phase_ids),
                "acceptance": list(self.acceptance), "allowed_write_paths": list(self.allowed_write_paths),
                "role": self.role, "isolation": self.isolation,
                "scope_is_permission_enforcement": False}

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(_json(self.document()).encode()).hexdigest()

    def render(self) -> str:
        return ("Bounded child commission; source context is not an authority grant.\n"
                + _json(self.document())
                + "\nThe native child has no automatic parent history. Recover the linked source and notes. "
                  "Preserve every parent DONE_WHEN while working only on your assigned phases and paths. "
                  "For no-write scope do not edit files; native permission mode may be broader and is not changed here. "
                  "Use the already-admitted paid Fabric for bounded implementation labor; native children are "
                  "for coordination or reasoning under the existing envelope. Do not create grandchildren by default. "
                  "Return child_key, original task/thread/run, source revision, checks, evidence, remaining criteria "
                  "and unknown effects. Questions and blockers are not completion. A result is not parent acceptance. "
                  "Do not overwrite siblings, change credentials, retry an uncertain effect or expand budget.\n")


def check_parallel_write_scopes(briefs: tuple[ChildBrief, ...]) -> dict:
    """Advisory conflict preflight, not a worker queue or runtime reservation."""
    if type(briefs) is not tuple or len(briefs) > 16 or any(type(x) is not ChildBrief for x in briefs):
        raise ValueError("Bounded child brief set required")
    if len({x.child_key for x in briefs}) != len(briefs):
        raise ValueError("Child identities must be unique")
    collisions = []
    for index, left in enumerate(briefs):
        for right in briefs[index + 1:]:
            overlap = [(a, b) for a in left.allowed_write_paths for b in right.allowed_write_paths
                       if a == b or a.startswith(b + "/") or b.startswith(a + "/")]
            if overlap:
                collisions.append({"children": [left.child_key, right.child_key], "overlapping_paths": overlap})
    return {"write_collisions": collisions, "can_integrate_without_path_coordination": not collisions,
            "execution_authority": False, "reservation_created": False}


def model_options(catalog: Mapping[str, Any], provider_id: str, model: str,
                  requested: Mapping[str, str | bool]) -> list[dict]:
    """Validate explicit reasoning/options against the exact native model row.

    Do not infer 'max', translate a model alias, or treat a prompt as an effort
    setting. Omitted options inherit natively; an explicit empty mapping clears.
    """
    if type(catalog) is not dict or type(requested) is not dict or len(requested) > 16:
        raise ValueError("Native catalog and bounded explicit options required")
    providers = catalog.get("providers")
    if type(providers) is not list or len(providers) > 256:
        raise Unavailable("Native provider catalog malformed")
    rows = [p for p in providers if type(p) is dict and p.get("providerInstanceId") == provider_id]
    if len(rows) != 1 or rows[0].get("canRunChildTask") is not True or rows[0].get("constraints") != []:
        raise Rejected("provider_unavailable")
    models = rows[0].get("models")
    if type(models) is not list or len(models) > 1024:
        raise Unavailable("Native model catalog malformed")
    matches = [r for r in models if type(r) is dict and r.get("id") == model]
    if len(matches) != 1:
        raise Rejected("model_unavailable")
    options = matches[0].get("options", [])
    if type(options) is not list or len(options) > 64:
        raise Unavailable("Native option catalog malformed")
    by_id = {}
    for option in options:
        if (type(option) is not dict or type(option.get("id")) is not str
                or option["id"] in by_id or type(option.get("values")) is not list
                or len(option["values"]) > 64
                or any(type(x) not in {str, bool} for x in option["values"])):
            raise Unavailable("Native option catalog malformed")
        by_id[option["id"]] = option["values"]
    result = []
    for key, value in requested.items():
        if (type(key) is not str or type(value) not in {str, bool} or key not in by_id
                or not any(type(value) is type(v) and value == v for v in by_id[key])):
            raise Rejected("model_option_unavailable")
        result.append({"id": key, "value": value})
    return sorted(result, key=lambda x: x["id"])


@dataclass(frozen=True, slots=True)
class ChildReceipt:
    parent: Thread
    child: Run
    task_id: str
    child_key: str
    brief_sha256: str
    mission_sha256: str
    selected_model: str
    initial_native_status: str

    def __post_init__(self) -> None:
        _id(self.selected_model, "selected model")
        if self.initial_native_status not in STATUSES:
            raise ValueError("Original native status required")
        if (type(self.parent) is not Thread or type(self.child) is not Run
                or self.parent.scope != self.child.thread.scope
                or self.parent.thread_id == self.child.thread.thread_id):
            raise ValueError("Exact native parent and distinct same-scope child required")
        _id(self.task_id, "task id"); _id(self.child_key, "child key")
        for digest in (self.brief_sha256, self.mission_sha256):
            if type(digest) is not str or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("Original brief fingerprint required")


@dataclass(frozen=True, slots=True)
class Communication:
    kind: str
    body: str
    mission_sha256: str
    source_ref: str

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError("Explicit communication kind required")
        _text(self.body, "communication", 16384); _text(self.source_ref, "source", 2048)
        if (type(self.mission_sha256) is not str or len(self.mission_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.mission_sha256)):
            raise ValueError("Original mission fingerprint required")

    def render(self) -> str:
        return ("Task communication; retain the existing mission, native authority and original effects.\n"
                + _json({"kind": self.kind, "body": self.body, "mission_sha256": self.mission_sha256,
                         "source_ref": self.source_ref, "authority_granted": False}))


class NativeParent:
    """Only an already-authenticated native parent can use child-only tools.

    The server's parentThreadId, not a requested id or environment variable,
    must match. Outside-agent connections normally return null and refuse here.
    """
    def __init__(self, client: T3NativeClient, parent: Thread):
        if not isinstance(client, T3NativeClient) or type(parent) is not Thread or client.scope != parent.scope:
            raise ValueError("Exact existing native connection and parent required")
        self.client, self.parent = client, parent

    async def _catalog(self, model: str | None = None) -> dict:
        body = await self.client._call("orchestrator_capabilities", {} if model is None else {"search": model})
        if (body.get("parentThreadId") != self.parent.thread_id
                or body.get("inheritedProviderInstanceId") != self.client.scope.capacity_provider_id):
            raise Rejected("native_parent_not_bound")
        if type(body.get("features")) is not dict or body["features"].get("appOwnedSubagents") is not True:
            raise Unavailable("Native child capability unavailable")
        return body

    def _receipt(self, receipt: ChildReceipt) -> None:
        if type(receipt) is not ChildReceipt or receipt.parent != self.parent:
            raise Conflict("Original receipt belongs to another parent/connection")

    async def delegate(self, brief: ChildBrief, *, request_id: str, model: str,
                       options: dict[str, str | bool] | None = None) -> ChildReceipt:
        if type(brief) is not ChildBrief:
            raise ValueError("Validated complete child brief required")
        _id(request_id, "request id"); _id(model, "model")
        if options is not None and type(options) is not dict:
            raise ValueError("Explicit native options must be an object")
        catalog = await self._catalog(model)
        selected = model_options(catalog, self.client.scope.capacity_provider_id, model, {} if options is None else options)
        target = {"providerInstanceId": self.client.scope.capacity_provider_id, "model": model}
        if options is not None:
            target["options"] = selected
        args = {"task": brief.render(), "target": target, "title": brief.child_key,
                "role": brief.role, "isolation": brief.isolation, "mode": "async"}
        if "clientRequestId" in self.client.schemas.get("delegate_task", {}).get("properties", {}):
            args["clientRequestId"] = request_id
        body = await self.client._call("delegate_task", args, modifying=True,
                                       request_id=request_id, thread_id=self.parent.thread_id)
        try:
            if (body.get("providerInstanceId") != self.client.scope.capacity_provider_id
                    or body.get("model") != model or body.get("status") not in STATUSES
                    or body.get("remoteChild") is not None):
                raise ValueError("Native child binding differs")
            child = Run(Thread(self.client.scope, body["childThreadId"]), body["childRunId"], request_id, "launched")
            return ChildReceipt(self.parent, child, body["taskId"], brief.child_key,
                                brief.fingerprint, brief.mission.fingerprint, model, body["status"])
        except Exception:
            raise EffectUnknown("delegate_task", request_id, self.parent.thread_id) from None

    async def consume_return(self, receipt: ChildReceipt, *, completion_run_id: str) -> dict:
        """Consume after a native completion wake, not a polling loop.

        task_status marks delivery in T3, so a lost response is a modifying
        unknown effect. A finished turn with live children is not task success.
        """
        self._receipt(receipt); _id(completion_run_id, "native completion run")
        if completion_run_id != receipt.child.run_id:
            raise Conflict("Completion belongs to another original child run")
        await self._catalog()
        body = await self.client._call("task_status", {"taskId": receipt.task_id}, modifying=True,
                                       request_id=receipt.child.request_id, thread_id=self.parent.thread_id)
        if (body.get("taskId") != receipt.task_id or body.get("childThreadId") != receipt.child.thread.thread_id
                or body.get("childRunId") != completion_run_id or body.get("remoteChild") is not None
                or body.get("providerInstanceId") != self.client.scope.capacity_provider_id
                or body.get("model") != receipt.selected_model):
            raise EffectUnknown("task_status", receipt.child.request_id, self.parent.thread_id)
        if (body.get("status") not in STATUSES or type(body.get("hasPendingChildRuns")) is not bool
                or type(body.get("hasPendingQuestion")) is not bool or "pendingApproval" not in body):
            raise EffectUnknown("task_status", receipt.child.request_id, self.parent.thread_id)
        ready = (body["status"] == "completed" and body.get("workState") == "result_available"
                 and body["hasPendingChildRuns"] is False and body["hasPendingQuestion"] is False
                 and body["pendingApproval"] is None and body.get("latestTerminalRunId") == completion_run_id
                 and body.get("latestTerminalStatus") == "completed"
                 and (type(body.get("summary")) is str and bool(body["summary"].strip())
                      or type(body.get("resultContextTransferId")) is str and bool(body["resultContextTransferId"])))
        return {"native": body, "result_ready_for_parent_review": ready, "accepted": False,
                "original_mission_sha256": receipt.mission_sha256,
                "next_action": "VERIFY_ORIGINAL_ACCEPTANCE" if ready else "RECONCILE_NATIVE_CHILD_STATE"}

    async def communicate(self, receipt: ChildReceipt, message: Communication, *, request_id: str,
                          mode: str = "queue") -> Run:
        self._receipt(receipt)
        if type(message) is not Communication or message.mission_sha256 != receipt.mission_sha256:
            raise Conflict("Message changed the parent mission binding")
        if mode not in {"queue", "steer"}:
            raise ValueError("Use native stop/cancel separately; no implicit restart")
        await self._catalog()
        return await self.client.send(receipt.child.thread, request_id=request_id,
                                      message=message.render(), mode=mode)

    async def cancel(self, receipt: ChildReceipt, *, request_id: str, reason: str) -> dict:
        self._receipt(receipt); _id(request_id, "request id"); _text(reason, "cancel reason", 2000)
        # Cancellation remains useful when inference is unavailable. Native
        # task_cancel enforces the original authenticated parent relationship.
        args = {"taskId": receipt.task_id, "reason": reason}
        if "clientRequestId" in self.client.schemas.get("task_cancel", {}).get("properties", {}):
            args["clientRequestId"] = request_id
        body = await self.client._call("task_cancel", args, modifying=True,
                                       request_id=request_id, thread_id=self.parent.thread_id)
        if body.get("taskId") != receipt.task_id or body.get("status") not in TERMINAL | {"cancel_requested"}:
            raise EffectUnknown("task_cancel", request_id, self.parent.thread_id)
        return {"native": body, "terminal_observed": body["status"] in TERMINAL, "accepted": False}


async def set_reasoning(client: T3NativeClient, thread: Thread, *, request_id: str,
                        option_id: str, value: str | bool, expected_updated_at: str) -> dict:
    """Set one advertised option on an idle thread without changing its model.

    Native configure remains the owner. This check-then-dispatch is not an atomic
    server CAS and cannot override concurrent native edits or permission modes.
    """
    import asyncio
    tid = client._target(thread); _id(request_id, "request id"); _id(option_id, "option id")
    if type(value) not in {str, bool}:
        raise ValueError("Native reasoning options are exact strings or booleans")
    await client._idle_snapshot(thread, expected_updated_at)
    before = await client.configuration(thread)
    selected = before["modelSelection"]
    if selected["instanceId"] != client.scope.capacity_provider_id:
        raise Rejected("provider_unavailable")
    current = selected.get("options", [])
    if (type(current) is not list or len(current) > 16
            or any(type(item) is not dict or set(item) != {"id", "value"}
                   or type(item["id"]) is not str or type(item["value"]) not in {str, bool} for item in current)
            or len({item["id"] for item in current}) != len(current)):
        raise Unavailable("Native current options malformed")
    options = {item["id"]: item["value"] for item in current}
    options[option_id] = value
    catalog = await client._call("orchestrator_capabilities", {"search": selected["model"]})
    checked = model_options(catalog, client.scope.capacity_provider_id, selected["model"], options)
    if options == {item["id"]: item["value"] for item in current}:
        return {"state": "UNCHANGED", "observed": before, "configuration_written": False,
                "native_atomic_precondition": False}
    target = {"instanceId": selected["instanceId"], "model": selected["model"], "options": checked}
    receipt = await client._call("t3_thread_configure", {"threadId": tid, "modelSelection": target},
                                 modifying=True, request_id=request_id, thread_id=tid)
    client._sequence(receipt, "t3_thread_configure", request_id, tid)
    try:
        after = await client.configuration(thread)
        actual = after["modelSelection"]
        observed_options = actual.get("options", [])
        if (actual.get("instanceId") != target["instanceId"] or actual.get("model") != target["model"]
                or type(observed_options) is not list or len(observed_options) != len(checked)
                or sorted(observed_options, key=lambda x: x["id"]) != checked
                or any(after[key] != before[key] for key in ("runtimeMode", "interactionMode"))):
            raise Conflict("Native reasoning/model/mode readback differs")
    except (Exception, asyncio.CancelledError):
        raise EffectUnknown("t3_thread_configure", request_id, tid, receipt) from None
    return {"receipt": receipt, "observed": after, "configuration_written": True,
            "model_changed": False, "native_atomic_precondition": False,
            "reasoning_quality_or_provider_obedience": "UNPROVEN"}
