"""Hermes-native, session-bound ingress to the *existing* Fabric authority.

No scheduler, ledger, credentials, executable paths, provider calls, or worker
lifecycle reside here. Installation requires a trusted, authenticated native
session grant and an injected existing Fabric port. Default is unbound.
"""
from __future__ import annotations

import hashlib
import inspect
import os
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

TOOL = "mmx_fabric_worker"
TOOLSET = "mmx_fabric"
SCHEMA = "mastermind.hermes_fabric_native.v1"
TASK_CLASSES = frozenset({"mechanical", "fix_build", "review", "census", "audit"})
COMPLEXITIES = frozenset({
    "C0_MECHANICAL", "C1_ROUTINE_BOUNDED",
    "C2_COMPLEX_BOUNDED", "C3_FRONTIER_JUDGMENT",
})
KEY = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
OPERATIONS = frozenset({"preview", "submit", "status", "result"})
# The model never receives a root/parent/caller authority field.
TOOL_SCHEMA = {
    "name": TOOL,
    "description": (
        "Observe or request one independently admitted Fabric child for this "
        "authenticated Hermes session. Fabric owns all provider, host, "
        "account, budget, worker and result decisions. Never retry an "
        "uncertain submission. A preview is not an admission."
    ),
    "parameters": {
        "type": "object", "additionalProperties": False,
        "required": ["action", "task_key"],
        "properties": {
            "action": {"type": "string", "enum": sorted(OPERATIONS)},
            "task_key": {"type": "string", "pattern": KEY.pattern},
            "task_class": {"type": "string", "enum": sorted(TASK_CLASSES)},
            "task_complexity": {"type": "string", "enum": sorted(COMPLEXITIES)},
            "work_packet": {"type": "string", "maxLength": 16000},
            "escalation_reason": {"type": "string", "maxLength": 500},
        },
    },
}


class FabricNativeRefusal(RuntimeError):
    """A named fail-closed refusal, not permission to change a carrier."""


@dataclass(frozen=True)
class SessionGrant:
    """Issued by the actual authenticated Hermes/Executive host, never a model."""
    profile_id: str
    session_id: str
    root_id: str
    parent_id: str
    # Distinct bound native session generation; changes invalidate this grant.
    generation: str

    def __post_init__(self) -> None:
        for value in (self.root_id, self.parent_id):
            if type(value) is not str or IDENTITY.fullmatch(value) is None:
                raise FabricNativeRefusal("GRANT_IDENTITY_INVALID")
        for value in (self.profile_id, self.session_id, self.generation):
            if type(value) is not str or not 0 < len(value) <= 256:
                raise FabricNativeRefusal("GRANT_LINEAGE_INVALID")


@runtime_checkable
class FabricOwnerPort(Protocol):
    """Existing authenticated owner; status must prove exact root/parent.

    'NOT_FOUND' is allowed only after a definitive original-owner absence
    observation. An incomplete observation is UNAVAILABLE, not NOT_FOUND.
    submit() must retain the original carrier/ID under incumbent admission
    and return state, never silently fall back to another provider.
    """
    def preview(self, grant: SessionGrant, run_id: str,
                task_class: str, complexity: str, reason: str) -> Mapping[str, Any]: ...
    def status(self, grant: SessionGrant, run_id: str) -> Mapping[str, Any]: ...
    def submit(self, grant: SessionGrant, run_id: str, task_class: str,
               complexity: str, packet: str, reason: str) -> Mapping[str, Any]: ...
    def result(self, grant: SessionGrant, run_id: str) -> Mapping[str, Any]: ...


def run_id_for(grant: SessionGrant, task_key: str) -> str:
    """Stable original-run identity across an authorized session reconnect.

    Generation is a currentness fence, not part of the logical job key:
    a refreshed native owner cannot accidentally mint a replacement worker.
    """
    if type(task_key) is not str or KEY.fullmatch(task_key) is None:
        raise FabricNativeRefusal("TASK_KEY_INVALID")
    data = json.dumps([grant.profile_id, grant.session_id,
                       task_key], separators=(",", ":")).encode("utf-8")
    return "hermes-native-" + hashlib.sha256(data).hexdigest()[:40]


def _project(grant: SessionGrant | None, run_id: str | None,
             state: str, reason: str | None = None,
             **extra: Any) -> str:
    body: dict[str, Any] = {
        "schema": SCHEMA, "state": state, "reason": reason,
        "run_id": run_id, "root_id": grant.root_id if grant else None,
        "parent_id": grant.parent_id if grant else None,
    }
    body.update(extra)
    return json.dumps(body, sort_keys=True, separators=(",", ":"))


def _attest_reply(raw: Any, grant: SessionGrant, run_id: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise FabricNativeRefusal("FABRIC_OWNER_RESPONSE_INVALID")
    if raw.get("run_id") != run_id or raw.get("root_id") != grant.root_id:
        raise FabricNativeRefusal("FABRIC_OWNER_IDENTITY_MISMATCH")
    # An absent parent is NOT proof of the original parent.
    if raw.get("parent_id") != grant.parent_id:
        raise FabricNativeRefusal("FABRIC_OWNER_PARENT_MISMATCH")
    state = raw.get("state")
    if type(state) is not str or not 0 < len(state) <= 64:
        raise FabricNativeRefusal("FABRIC_OWNER_STATE_INVALID")
    digest = raw.get("result_digest")
    if digest is not None and (type(digest) is not str or
                               re.fullmatch(r"[0-9a-f]{64}", digest) is None):
        raise FabricNativeRefusal("FABRIC_OWNER_RESULT_DIGEST_INVALID")
    projected = {"state": state,
                 "reason": str(raw.get("reason"))[:120] if raw.get("reason") else None,
                 "result_digest": digest,
                 "worker_started": raw.get("worker_started") is True}
    body = raw.get("result_text")
    if body is not None:
        if (state != "TERMINAL" or type(body) is not str or digest is None
                or len(body.encode("utf-8")) > 8192
                or hashlib.sha256(body.encode("utf-8")).hexdigest() != digest):
            raise FabricNativeRefusal("FABRIC_OWNER_RESULT_INVALID")
        projected["result_text"] = body
    return projected


def native_handler(
    *, profile_id: str, authorize_session: Callable[[str], SessionGrant],
    port: FabricOwnerPort, currentness_guard: Callable[[SessionGrant], bool],
) -> Callable[..., str]:
    """One native handler. Only Hermes supplies session_id outside JSON input."""
    if not profile_id or not callable(authorize_session) or not callable(currentness_guard):
        raise FabricNativeRefusal("NATIVE_HOST_BINDING_INVALID")
    if not isinstance(port, FabricOwnerPort):
        raise FabricNativeRefusal("FABRIC_OWNER_PORT_UNBOUND")

    def handle(arguments: Any, *, session_id: Any = None,
               task_id: Any = None) -> str:
        if type(session_id) is not str or not session_id:
            return _project(None, None, "REFUSED", "NATIVE_SESSION_MISSING")
        if not isinstance(arguments, Mapping):
            return _project(None, None, "REFUSED", "ARGUMENTS_NOT_OBJECT")
        if set(arguments) - set(TOOL_SCHEMA["parameters"]["properties"]):
            return _project(None, None, "REFUSED", "UNKNOWN_FIELD")
        action, key = arguments.get("action"), arguments.get("task_key")
        if type(action) is not str or action not in OPERATIONS:
            return _project(None, None, "REFUSED", "ACTION_INVALID")
        if type(key) is not str or KEY.fullmatch(key) is None:
            return _project(None, None, "REFUSED", "TASK_KEY_INVALID")
        try:
            grant = authorize_session(session_id)
            if (not isinstance(grant, SessionGrant)
                    or grant.profile_id != profile_id
                    or grant.session_id != session_id
                    or currentness_guard(grant) is not True):
                raise FabricNativeRefusal("NATIVE_SESSION_NOT_AUTHORIZED")
            run_id = run_id_for(grant, key)
        except Exception:
            return _project(None, None, "REFUSED", "NATIVE_SESSION_NOT_AUTHORIZED")

        if action in {"status", "result"}:
            try:
                raw = (port.status(grant, run_id) if action == "status"
                       else port.result(grant, run_id))
                return _project(grant, run_id, **_attest_reply(raw, grant, run_id))
            except Exception:
                return _project(grant, run_id, "UNAVAILABLE",
                                "FABRIC_ORIGINAL_OBSERVATION_UNAVAILABLE")

        task_class = arguments.get("task_class")
        complexity = arguments.get("task_complexity")
        reason = arguments.get("escalation_reason", "")
        if (type(task_class) is not str or task_class not in TASK_CLASSES
                or type(complexity) is not str or complexity not in COMPLEXITIES
                or type(reason) is not str or len(reason) > 500):
            return _project(grant, run_id, "REFUSED", "TASK_QUALIFICATION_INVALID")
        if complexity == "C3_FRONTIER_JUDGMENT" and not reason.strip():
            return _project(grant, run_id, "REFUSED", "ESCALATION_REASON_REQUIRED")
        if action == "preview":
            try:
                raw = port.preview(grant, run_id, task_class, complexity, reason)
                return _project(grant, run_id, **_attest_reply(raw, grant, run_id))
            except Exception:
                return _project(grant, run_id, "UNAVAILABLE",
                                "FABRIC_PREVIEW_UNAVAILABLE")

        packet = arguments.get("work_packet")
        if (type(packet) is not str or not packet.strip()
                or "\x00" in packet or len(packet) > 16000
                or len(packet.encode("utf-8")) > 32768):
            return _project(grant, run_id, "REFUSED", "PACKET_INVALID")
        try:
            observed = _attest_reply(port.status(grant, run_id), grant, run_id)
        except Exception:
            return _project(grant, run_id, "UNAVAILABLE",
                            "FABRIC_ORIGINAL_OBSERVATION_UNAVAILABLE")
        if observed["state"] != "NOT_FOUND":
            return _project(grant, run_id, **observed)
        # Recheck native authority immediately before the only possible write.
        try:
            if currentness_guard(grant) is not True:
                raise FabricNativeRefusal("NATIVE_SESSION_REVOKED")
        except Exception:
            return _project(grant, run_id, "REFUSED", "NATIVE_SESSION_REVOKED")
        try:
            raw = port.submit(grant, run_id, task_class, complexity, packet, reason)
        except Exception:
            # The incumbent port may have sent the request. Never auto-retry.
            return _project(grant, run_id, "EFFECT_UNKNOWN",
                            "FABRIC_SUBMIT_ORIGINAL_EFFECT_UNKNOWN")
        try:
            return _project(grant, run_id, **_attest_reply(raw, grant, run_id))
        except Exception:
            return _project(grant, run_id, "EFFECT_UNKNOWN",
                            "FABRIC_SUBMIT_ORIGINAL_EFFECT_UNKNOWN")

    return handle


def register_native_tool(ctx: Any, *, authorize_session: Callable[[str], SessionGrant],
                         port: FabricOwnerPort,
                         currentness_guard: Callable[[SessionGrant], bool]) -> Any:
    """Use the actual upstream native owner; no process-global unbound default."""
    if getattr(ctx, "profile_name", None) is None or not callable(
            getattr(ctx, "register_tool", None)):
        raise FabricNativeRefusal("HERMES_NATIVE_CONTEXT_UNAVAILABLE")
    handler = native_handler(profile_id=ctx.profile_name,
                             authorize_session=authorize_session, port=port,
                             currentness_guard=currentness_guard)
    # Native Hermes owns the registry, collision fence and registration lease.
    # Do not overwrite a prior installation or create a parallel registry.
    try:
        from hermes_cli.plugin_isolation import (
            HOST_PROCESS_ENV, ISOLATION_HOST, isolation_mode,
        )
        from registration_lifecycle import replacement_coordinator
        from tools.registry import registry
    except ImportError:
        raise FabricNativeRefusal("HERMES_NATIVE_OWNER_UNAVAILABLE") from None
    if os.environ.get(HOST_PROCESS_ENV) == "1":
        raise FabricNativeRefusal("HERMES_PLUGIN_HOST_PROCESS_REFUSED")
    try:
        if isolation_mode() == ISOLATION_HOST and (
            getattr(getattr(ctx, "manifest", None), "source", "") != "bundled"
        ):
            raise FabricNativeRefusal("HERMES_PLUGIN_ISOLATION_REFUSED")
    except FabricNativeRefusal:
        raise
    except Exception:
        raise FabricNativeRefusal("HERMES_PLUGIN_ISOLATION_UNKNOWN") from None
    scope = getattr(getattr(ctx, "_manager", None), "scope_key", None)
    if type(scope) is not str or not scope:
        raise FabricNativeRefusal("HERMES_NATIVE_SCOPE_UNAVAILABLE")
    check_fn = lambda: True   # Each call checks current native session grant.
    with replacement_coordinator.transaction():
        if (registry.snapshot_registration(TOOL, scope=scope) is not None
                or registry.get_entry(TOOL, scope=scope) is not None):
            raise FabricNativeRefusal("HERMES_NATIVE_TOOL_COLLISION")
        try:
            handle = ctx.register_tool(
                name=TOOL, toolset=TOOLSET, schema=TOOL_SCHEMA,
                handler=handler, check_fn=check_fn, is_async=False,
                description=TOOL_SCHEMA["description"], emoji="cpu")
        except Exception:
            # This may have written the native entry before a transport loss.
            raise FabricNativeRefusal("HERMES_REGISTRATION_EFFECT_UNKNOWN") from None
        if handle is None:
            raise FabricNativeRefusal("HERMES_REGISTRATION_RECEIPT_UNAVAILABLE")
        try:
            entry = registry.snapshot_registration(TOOL, scope=scope)
            if (entry is None or entry.handler is not handler
                    or entry.schema != TOOL_SCHEMA or entry.toolset != TOOLSET
                    or entry.check_fn is not check_fn):
                raise FabricNativeRefusal("HERMES_REGISTRATION_READBACK_MISMATCH")
        except Exception as exc:
            try:
                handle.dispose()   # Only this exact native lease; no broad unregister.
            except Exception:
                raise FabricNativeRefusal("HERMES_REGISTRATION_ROLLBACK_UNKNOWN") from None
            if isinstance(exc, FabricNativeRefusal):
                raise
            raise FabricNativeRefusal("HERMES_REGISTRATION_READBACK_UNAVAILABLE") from None
        return handle
