"""Production native-session composition for the attended Fabric worker tool.

Hermes owns the active parent, durable turn lease, transcript and tool dispatch.
Fabric owns request admission, routing, execution and retained results. This
module joins those existing owners; it does not create a worker or claim ledger.
It is mounted by the normal PluginManager, independently of the primary model.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .facade_port import FabricFacadePort
from .hermes_mcp_client import bind_native_mcp_client
from .native_evidence import (
    ENROLLMENT_SCHEMA, ORIGIN_KIND, PLUGIN_ID, evidence_for, native_root,
    qualify_native_intent, read_enrollment,
)
from .native import (
    FabricNativeRefusal, FabricPreDispatchRefusal, SessionGrant, TOOL,
    _project, register_native_tool, run_id_for,
)

CAPACITY_SERVER = "mastermind-fabric-capacity"
_LOCAL_SURFACES = frozenset({"cli", "tui", "desktop"})


@dataclass
class _Invocation:
    """Only the current native callback; never a task/lifecycle registry."""
    grant: SessionGrant
    parent: Any
    db: Any
    holder: str
    turn_id: str
    tool_call_id: str
    arguments: dict[str, Any]
    submitted: bool = False


class NativeSessionBinding:
    """Host-produced grants from the actual native parent and its durable lease.

    The native profile gates registration, and the existing execution facade
    attests that enrollment before the first operation. Root/parent use its stable namespace and
    the native original conversation, never an Executive Job. Delegated and
    unattended callers are refused; their existing admission path is separate.
    """

    def __init__(self, ctx: Any) -> None:
        from hermes_cli.plugins import PluginContext

        if type(ctx) is not PluginContext or ctx.plugin_id != PLUGIN_ID:
            raise FabricNativeRefusal("HERMES_NATIVE_CONTEXT_UNAVAILABLE")
        self.ctx = ctx
        self.closed = False
        self.enrollment: Mapping[str, Any] | None = None
        self._server_attested = False
        self._active: contextvars.ContextVar[_Invocation | None] = contextvars.ContextVar(
            "hermes_attended_fabric_invocation", default=None)

    def enroll(self, capabilities: Mapping[str, Any]) -> None:
        from types import MappingProxyType
        contract = capabilities.get("hermes_native_origin")
        if (not isinstance(contract, Mapping) or contract.get("schema") != ENROLLMENT_SCHEMA
                or contract.get("enabled") is not True or contract.get("kind") != ORIGIN_KIND
                or contract.get("profile_id") != self.ctx.profile_name
                or type(contract.get("namespace")) is not str
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", contract["namespace"]) is None
                or contract.get("native_session_owner") != "Hermes SessionDB"
                or contract.get("request_admission_owner") != "fabric_task.request"
                or contract.get("root_policy") != "native_conversation_namespace_v1"
                or type(contract.get("source_revision")) is not str
                or re.fullmatch(r"[0-9a-f]{40}", contract["source_revision"]) is None
                or type(contract.get("package_sha256")) is not str
                or re.fullmatch(r"[0-9a-f]{64}", contract["package_sha256"]) is None
                or type(contract.get("generation")) is not str
                or re.fullmatch(r"[0-9a-f]{64}", contract["generation"]) is None):
            raise FabricNativeRefusal("HERMES_NATIVE_ORIGIN_NOT_ENROLLED")
        self.enrollment = MappingProxyType(dict(contract))

    def call(self, client: Any, action: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        active = self._active.get()
        if active is None or not self.current(active.grant) or self.enrollment is None:
            raise FabricNativeRefusal("NATIVE_ATTENDED_TURN_NOT_CURRENT")
        if not self._server_attested:
            # Native plugin discovery precedes MCP startup. Attest through the
            # existing client only inside a persisted, current invocation.
            remote = client("fabric_capabilities", {}).get("hermes_native_origin")
            if remote != self.enrollment or not self.current(active.grant):
                raise FabricNativeRefusal("HERMES_NATIVE_ORIGIN_NOT_ENROLLED")
            self._server_attested = True
        return client(action, {**arguments, "native_origin": evidence_for(active, self.enrollment)})

    def close(self) -> None:
        # Unload revokes this binding; it does not cancel a Fabric worker.
        self.closed = True

    def _manual_routes(self) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
        raw = self.ctx.get_config("manual_routes", [])
        if type(raw) is not list or len(raw) > 64:
            raise FabricNativeRefusal("NATIVE_MANUAL_ROUTES_INVALID")
        pairs = []
        for item in raw:
            if (type(item) is not dict or set(item) != {"pool", "model"}
                    or type(item["pool"]) is not str or type(item["model"]) is not str):
                raise FabricNativeRefusal("NATIVE_MANUAL_ROUTES_INVALID")
            pairs.append((item["pool"], item["model"]))
        return tuple(sorted({p for p, _ in pairs})), tuple(sorted(set(pairs)))

    def _capture(self, session_id: str, turn_id: str, tool_call_id: str,
                 arguments: Mapping[str, Any]) -> _Invocation:
        from agent.subagent_lifecycle import get_active_subagent_parent
        from hermes_constants import get_hermes_home, hermes_home_key
        from hermes_state import SessionDB
        from run_agent import AIAgent

        parent = get_active_subagent_parent()
        db = getattr(parent, "_session_db", None)
        scope = getattr(self.ctx._manager, "scope_key", None)
        holder = getattr(parent, "_active_session_turn_lease_holder", None)
        if (self.closed or self.enrollment is None
                or type(parent) is not AIAgent or type(db) is not SessionDB
                or self.ctx.session_surface() not in _LOCAL_SURFACES
                or getattr(parent, "_delegate_depth", 0) != 0
                or getattr(parent, "_turn_origin", None)
                or getattr(parent, "_persist_disabled", False)
                or getattr(parent, "_interrupt_requested", False)
                or not session_id or parent.session_id != session_id
                or not turn_id or getattr(parent, "_current_turn_id", None) != turn_id
                or type(holder) is not str or not holder
                or type(tool_call_id) is not str or not tool_call_id
                or scope != hermes_home_key(get_hermes_home())
                or Path(db.db_path).resolve().parent != Path(scope).resolve()):
            raise FabricNativeRefusal("NATIVE_ATTENDED_TURN_NOT_CURRENT")

        # Native compression lineage excludes forks, resets and delegated children.
        # Use the same original conversation key as native turn serialization.
        origin = db._session_turn_lease_key(session_id)
        lineage = db._resume_lineage_ids(session_id)
        row = db.get_session(session_id)
        expiry = db.session_turn_lease_expires_at(session_id, holder)
        if (not lineage or lineage[0] != origin or lineage[-1] != session_id
                or len(lineage) >= 100 or row is None
                or type(row.get("runtime_generation")) is not int
                or type(expiry) not in (int, float) or expiry <= time.time()):
            raise FabricNativeRefusal("NATIVE_DURABLE_TURN_NOT_CURRENT")
        pools, models = self._manual_routes()
        generation = hashlib.sha256(json.dumps(
            [scope, holder, turn_id, row["runtime_generation"]],
            separators=(",", ":")).encode()).hexdigest()
        root = native_root(self.enrollment, origin)
        grant = SessionGrant(
            profile_id=self.ctx.profile_name, session_id=session_id,
            root_id=root, parent_id=root, generation=generation,
            manual_pools=pools, manual_models=models, origin_session_id=origin)
        if not qualify_native_intent(db, grant, tool_call_id, arguments, original_submit=False):
            raise FabricNativeRefusal("NATIVE_DURABLE_INTENT_NOT_CURRENT")
        return _Invocation(grant, parent, db, holder, turn_id, tool_call_id,
                           json.loads(json.dumps(dict(arguments))))

    def current(self, grant: SessionGrant) -> bool:
        active = self._active.get()
        if active is None or active.grant is not grant:
            return False
        try:
            now = self._capture(grant.session_id, active.turn_id,
                                active.tool_call_id, active.arguments)
            return (now.parent is active.parent and now.db is active.db
                    and now.holder == active.holder and now.grant == grant)
        except Exception:
            return False

    def authorize_session(self, session_id: str) -> SessionGrant:
        active = self._active.get()
        if (active is None or active.grant.session_id != session_id
                or not self.current(active.grant)):
            raise FabricNativeRefusal("NATIVE_ATTENDED_TURN_NOT_CURRENT")
        return active.grant

    def middleware(self, *, tool_name: str, args: Any, next_call: Any,
                   session_id: str = "", turn_id: str = "",
                   tool_call_id: str = "", **_: Any) -> Any:
        if tool_name != TOOL:
            return next_call(args)
        # Native execution middleware is single-use and wraps the real dispatch
        # after request rewriting. Catch setup failure: Hermes otherwise skips
        # a failing middleware, which must never weaken this tool's authority.
        try:
            if not isinstance(args, Mapping):
                raise FabricNativeRefusal("ARGUMENTS_NOT_OBJECT")
            active = self._capture(session_id, turn_id, tool_call_id, args)
        except FabricNativeRefusal as exc:
            return _project(None, None, "REFUSED", str(exc))
        except Exception:
            return _project(None, None, "UNAVAILABLE", "NATIVE_BINDING_UNAVAILABLE")
        token = self._active.set(active)
        try:
            return next_call(args)
        finally:
            self._active.reset(token)

    def _durable_original_intent(self, active: _Invocation, run_id: str) -> bool:
        args = active.arguments
        return (args.get("action") == "submit"
                and run_id_for(active.grant, args.get("task_key")) == run_id
                and qualify_native_intent(active.db, active.grant, active.tool_call_id,
                                          args, original_submit=True))

    def authorize_new_run(self, grant: SessionGrant, run_id: str) -> bool:
        active = self._active.get()
        if active is None or active.submitted or not self.current(grant):
            return False
        if not self._durable_original_intent(active, run_id) or not self.current(grant):
            return False
        # Only the current native single-use invocation. The durable original
        # intent above and Fabric's O_EXCL retained request are the real owners.
        active.submitted = True
        return True

    def verify_submission(self, grant: SessionGrant, run_id: str, task_class: str,
                          complexity: str, packet: str, reason: str,
                          pool: str | None, model: str | None) -> None:
        active = self._active.get()
        if active is None or not self.current(grant):
            raise FabricPreDispatchRefusal("NATIVE_ATTENDED_TURN_NOT_CURRENT")
        args = active.arguments
        if (args.get("action") != "submit"
                or run_id_for(grant, args.get("task_key")) != run_id
                or args.get("task_class") != task_class
                or args.get("task_complexity") != complexity
                or args.get("work_packet") != packet
                or args.get("escalation_reason", "") != reason
                or args.get("pool") != pool or args.get("model") != model):
            raise FabricPreDispatchRefusal("NATIVE_DURABLE_ARGUMENTS_CHANGED")

    def preview(self, grant: SessionGrant, run_id: str, task_class: str,
                complexity: str, reason: str) -> Mapping[str, Any]:
        if (not self.current(grant)
                or CAPACITY_SERVER not in self.ctx._mcp_allowlist(self.ctx.plugin_id)):
            raise FabricNativeRefusal("HERMES_CAPACITY_PREVIEW_NOT_ENROLLED")
        reply = self.ctx.call_mcp(CAPACITY_SERVER, "fabric_route_preview",
                                 {"task_class": task_class, "complexity": complexity}, timeout=20)
        document = reply.get("structuredContent") or reply.get("result")
        if type(document) is str and len(document) <= 65536:
            try:
                document = json.loads(document)
            except (TypeError, ValueError):
                raise FabricNativeRefusal("FABRIC_PREVIEW_NOT_PROVEN") from None
        if (reply.get("ok") is not True or reply.get("truncated") is True
                or not isinstance(document, Mapping)
                or document.get("proof") != "PREVIEW_ONLY_NO_RESERVATION_OR_DISPATCH"
                or document.get("reserved") is not False or not self.current(grant)):
            raise FabricNativeRefusal("FABRIC_PREVIEW_NOT_PROVEN")
        return {**document, "owner_state": document.get("state"), "state": "PREVIEW_ONLY"}


class _NativeFacadePort(FabricFacadePort):
    def __init__(self, binding: NativeSessionBinding, call_tool: Any) -> None:
        self.binding = binding
        super().__init__(call_tool, authorize_new_run=binding.authorize_new_run,
                         preview_route=binding.preview)

    def submit(self, grant: SessionGrant, run_id: str, task_class: str,
               complexity: str, packet: str, reason: str, *,
               pool: str | None = None, model: str | None = None) -> Mapping[str, Any]:
        self.binding.verify_submission(grant, run_id, task_class, complexity,
                                       packet, reason, pool, model)
        return super().submit(grant, run_id, task_class, complexity, packet,
                              reason, pool=pool, model=model)


def register(ctx: Any) -> None:
    """Actual native plugin entry point; enrollment remains an installed owner."""
    from hermes_constants import get_hermes_home

    binding = NativeSessionBinding(ctx)
    # Native profile policy gates publication without requiring MCP startup.
    # The first current invocation attests this exact contract remotely; the
    # server independently rechecks native evidence on every operation.
    client = bind_native_mcp_client(ctx)
    try:
        contract = read_enrollment(get_hermes_home())
    except Exception:
        raise FabricNativeRefusal("HERMES_NATIVE_ORIGIN_NOT_ENROLLED") from None
    binding.enroll({"hermes_native_origin": contract})
    port = _NativeFacadePort(binding, lambda action, args: binding.call(client, action, args))
    middleware = ctx.register_middleware("tool_execution", binding.middleware)
    tool_lease = None
    try:
        tool_lease = register_native_tool(
            ctx, authorize_session=binding.authorize_session,
            port=port, currentness_guard=binding.current)
        ctx.on_unload(binding.close)
    except Exception:
        binding.close()
        try:
            if tool_lease is not None:
                tool_lease.dispose()
        finally:
            middleware.dispose()
        raise
