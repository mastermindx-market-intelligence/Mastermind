"""Two explicitly enrolled v4 tools on the original native PluginContext.

ConsumerSlot retains registration, the original in-flight call and recovery
lookup. Native registry leases own unload; SDK lock/tasks own transport;
Workspace Events own durable effects. This adapter creates none of those owners.
"""
from __future__ import annotations

import copy
import concurrent.futures
import json
from dataclasses import dataclass
from typing import Any, Callable

from common import coo_agentos_context_contract as context_wire
from common import coo_discovery_contract as wire
from integrations.executive_mcp.coo import COO_DISCOVERY_TOOL_SPECS
from .native_agentos_context import decode_native_tool_result, expected_context, MAX_MCP_RESULT_BYTES
from .native_executive_consumer import (
    CONSUMER_PLUGIN_NAME, CONSUMER_SLOT_ATTRIBUTE, ConsumerSlot,
    ExecutiveContextConsumerPublication, _NativeMcpCaller, _ConsumerNotDispatched, read_mandate,
    workspace_principal_frame, schema_digest)
from .native_tool_registration import (
    NativeToolRegistrationError, _registry, _ctx_scope, _ctx_profile_name,
    _loading_mode_refusal, _bound_session_key)

TOOLSET = "mmx_discovery"


def schemas():
    return {spec.name: {"name": spec.name, "description": spec.description,
                       "parameters": copy.deepcopy(spec.input_schema)}
            for spec in COO_DISCOVERY_TOOL_SPECS if spec.name in wire.TOOLS}


@dataclass(frozen=True)
class NativeDiscoveryBinding:
    slot: ConsumerSlot
    publication: ExecutiveContextConsumerPublication
    caller: _NativeMcpCaller
    profile_id: str
    session_id: str
    session_key: str | None
    currentness: Callable[[], bool]
    trust_gate: Callable[..., str | None]

    def __post_init__(self):
        if (type(self.slot) is not ConsumerSlot or type(self.publication) is not ExecutiveContextConsumerPublication
                or not self.publication.discovery or self.slot.publication is not self.publication
                or type(self.caller) is not _NativeMcpCaller or not callable(self.currentness)
                or not callable(self.trust_gate) or type(self.profile_id) is not str or not self.profile_id
                or type(self.session_id) is not str or not self.session_id
                or (self.session_key is not None and (type(self.session_key) is not str or not self.session_key))):
            raise NativeToolRegistrationError("NATIVE_DISCOVERY_BINDING_INVALID")


@dataclass(frozen=True)
class DiscoveryToolRegistration:
    name: str
    handler: Any
    check_fn: Any
    handle: Any
    entry: Any
    schema_sha256: str


@dataclass(frozen=True)
class NativeDiscoveryRegistration:
    context: Any
    registry: Any
    binding: NativeDiscoveryBinding
    scope: str
    tools: tuple[DiscoveryToolRegistration, ...]


def qualify_binding(*, slot, server, session, loop, profile_id, session_id, session_key,
                    currentness, trust_gate, timeout):
    publication = slot.publication
    caller = _NativeMcpCaller(server=server, session=session, loop=loop,
        currentness=currentness, wait_for_lock=False, timeout=timeout)
    binding = NativeDiscoveryBinding(slot, publication, caller, profile_id, session_id,
                                    session_key, currentness, trust_gate)
    mandate = read_mandate(caller, publication)
    principal, mission, capability = (mandate.get(key) for key in ("principal", "mission", "capability"))
    if (type(principal) is not dict or not publication.principal.matches(principal)
            or principal.get("principal_binding_digest") != publication.principal_binding_digest
            or type(mission) is not dict or any(mission.get(key) != getattr(publication, key)
                for key in ("work_ref", "mission_authority_ref", "authority_generation_digest"))
            or type(capability) is not dict or capability.get("capability_profile_digest") != publication.capability_profile_digest
            or type(capability.get("principal_actions")) is not list
            or not {context_wire.CURRENT_ACTION, wire.READ_ACTION, wire.CORRECTION_ACTION}.issubset(capability["principal_actions"])
            or currentness() is not True):
        raise NativeToolRegistrationError("NATIVE_DISCOVERY_MANDATE_MISMATCH")
    return binding


def registration_current(binding):
    try:
        slot = binding.slot
        registration = slot.discovery_registration
        loaded = getattr(slot.manager, "_plugins", {}).get(CONSUMER_PLUGIN_NAME)
        if (slot.discovery_binding is not binding or slot.publication is not binding.publication
                or slot.discovery_error is not None or slot.registration_error is not None
                or type(registration) is not NativeDiscoveryRegistration or registration.binding is not binding
                or getattr(slot.manager, CONSUMER_SLOT_ATTRIBUTE, None) is not slot
                or slot.manager.scope_key != slot.scope or registration.scope != slot.scope
                or registration.context is not slot.discovery_context
                or getattr(registration.context, "_manager", None) is not slot.manager
                or loaded is None or loaded is not slot.loader_record
                or getattr(loaded, "manifest", None) is not getattr(registration.context, "manifest", None)
                or getattr(loaded, "enabled", None) is not True or getattr(loaded, "error", None) is not None
                or slot.load_outcome not in {"REGISTERED", "CONTEXT_REGISTERED"}
                or not callable(slot.import_current) or slot.import_current() is not True
                or not callable(slot.package_check) or slot.package_check() is not True
                or binding.currentness() is not True or _registry() is not registration.registry
                or tuple(item.name for item in registration.tools) != wire.TOOLS):
            return False
        for item in registration.tools:
            entry = registration.registry.snapshot_registration(item.name, scope=registration.scope)
            if (entry is not item.entry or entry.handler is not item.handler
                    or entry.check_fn is not item.check_fn or entry.toolset != TOOLSET
                    or schema_digest(entry.schema) != item.schema_sha256):
                return False
        return True
    except Exception:
        return False


def _lineage(binding, session_id, task_id):
    # Only the enrolled parent can use these mission tools. A child dispatcher
    # task is never silently promoted to the parent's governed write surface.
    return (type(session_id) is str and session_id == binding.session_id and task_id is None
            and (binding.session_key is None or _bound_session_key() == binding.session_key))


def _recovered(pending, tool, value, result):
    if (pending is None or wire.lookup(tool, value) != pending["lookup"] or result["state"] != "OBSERVED"
            or tool != wire.CORRECTION_TOOL or value["operation"] not in {"read", "reconcile"}):
        return False
    status = result["data"]
    if status["disposition"] == "refused" and status["reason"] == "NOT_DISPATCHED":
        return True
    receipt = status["receipt"]
    return receipt is not None and (receipt["kind"] in {"PROPOSAL_OBSERVED", "SOURCE_OBSERVED"}
        or pending["operation"] == "prepare" and receipt["kind"] == "INTENT")


def _refund_no_send(call):
    if call.get("refund_attempted"):
        return
    call["refund_attempted"] = True
    for charge in call["booked"]:
        try:
            charge.refund()
        except Exception:
            call["refund_unknown"] = True


def _settle_original_future(slot):
    """Observe only the retained SDK future; never retry, cancel or reconnect.

    A timeout remains unknown until the original caller positively returns a
    pre-send refusal, or the canonical Workspace owner reconciles an effect.
    A completed SDK success is not interpreted here as publication proof.
    """
    call = slot.discovery_call
    if call is None or call.get("refund_unknown"):
        return
    future = call.get("original_future")
    if type(future) is not concurrent.futures.Future or not future.done() or future.cancelled():
        return
    if isinstance(future.exception(), _ConsumerNotDispatched):
        _refund_no_send(call)
        if slot.discovery_uncertain_call is call:
            slot.discovery_uncertain = slot.discovery_uncertain_call = None
    if not call.get("refund_unknown"):
        slot.discovery_call = None


def handler_for(binding, tool):
    def handle(arguments, *, session_id=None, task_id=None):
        try:
            value = wire.arguments(tool, arguments)
        except Exception:
            # No recovery identity can be invented for an invalid request.
            return json.dumps({"error": "NATIVE_DISCOVERY_INVALID_INPUT"})
        selected, mutation = wire.lookup(tool, value), wire.mutating(tool, value)
        def outcome(state, reason):
            return wire.result(tool, value, state=state, reason=reason)
        def current():
            return _lineage(binding, session_id, task_id) and registration_current(binding)
        slot, invoked, booked = binding.slot, False, []
        original_future = None
        if selected["work_ref"] != binding.publication.work_ref or not current():
            return context_wire.encode(outcome("NOT_DISPATCHED", "AUTHORITY_UNAVAILABLE"), limit=wire.MAX_RESULT_BYTES).decode()
        call = {"tool": tool, "operation": wire.operation(tool, value), "lookup": selected, "booked": booked}
        with slot._lock:
            _settle_original_future(slot)
            pending = slot.discovery_uncertain
            if (slot.discovery_call is not None or pending is not None and mutation and
                    not (tool == wire.CORRECTION_TOOL and value["operation"] == "reconcile" and selected == pending["lookup"])):
                return context_wire.encode(outcome("NOT_DISPATCHED", "ORIGINAL_OPERATION_UNRESOLVED"), limit=wire.MAX_RESULT_BYTES).decode()
            slot.discovery_call = call
        try:
            # The incumbent trust/spend owner receives the actual remote name
            # and complete validated arguments, exactly once for this call.
            if binding.trust_gate(tool, booked, value) is not None or not current():
                result = outcome("NOT_DISPATCHED", "AUTHORITY_UNAVAILABLE")
            else:
                invoked = True
                raw = binding.caller.call(tool, value, currentness=current)
                body = decode_native_tool_result(raw, limit=MAX_MCP_RESULT_BYTES)
                result = wire.validate_result(body, tool=tool, value=value,
                    expected_context=expected_context(binding.publication),
                    capability_profile_digest=binding.publication.capability_profile_digest,
                    workspace_principal=workspace_principal_frame(binding.publication))
                if not current():
                    raise ValueError("original_native_owner_changed")
        except _ConsumerNotDispatched:
            invoked = False
            result = outcome("NOT_DISPATCHED", "AUTHORITY_UNAVAILABLE")
        except Exception as error:
            future = getattr(error, "original_future", None)
            if type(future) is concurrent.futures.Future:
                original_future = future
            result = (outcome("EFFECT_UNKNOWN", "ORIGINAL_OUTCOME_UNKNOWN") if invoked and mutation
                else outcome("UNAVAILABLE", "SOURCE_UNAVAILABLE") if invoked
                else outcome("NOT_DISPATCHED", "AUTHORITY_UNAVAILABLE"))
        finally:
            if not invoked:
                _refund_no_send(call)
        with slot._lock:
            # Publish the future and its observer outcome atomically. A concurrent
            # readback must not settle it before this original call's uncertainty
            # is retained, or admit a replacement while finalization is pending.
            if original_future is not None:
                call["original_future"] = original_future
            slot.discovery_last_result = result
            slot.discovery_last_call = call
            unresolved = result["state"] == "EFFECT_UNKNOWN"
            if mutation and result["state"] == "OBSERVED" and value["operation"] != "prepare":
                status = result["data"]
                unresolved = status["disposition"] == "unknown" and (
                    status["receipt"] is None or status["receipt"]["kind"] in {"INTENT", "PHASE_ATTEMPTED"})
            if mutation and unresolved:
                # Preserve the earliest original uncertainty, including when a
                # reconciliation of that same identity is itself interrupted.
                if slot.discovery_uncertain is None:
                    slot.discovery_uncertain = {"operation": wire.operation(tool, value), "lookup": selected}
                    slot.discovery_uncertain_call = call
            elif _recovered(slot.discovery_uncertain, tool, value, result):
                slot.discovery_uncertain = slot.discovery_uncertain_call = None
            if (slot.discovery_call is call and not call.get("refund_unknown")
                    and "original_future" not in call):
                slot.discovery_call = None
        return context_wire.encode(result, limit=wire.MAX_RESULT_BYTES).decode()
    handle.__name__ = tool
    handle.__qualname__ = tool
    return handle


def register_discovery_tools(ctx, slot):
    binding = slot.discovery_binding
    if (type(binding) is not NativeDiscoveryBinding or not callable(getattr(ctx, "register_tool", None))
            or _loading_mode_refusal(ctx) is not None or _ctx_profile_name(ctx) != binding.profile_id
            or _ctx_scope(ctx) != slot.scope or getattr(ctx, "_manager", None) is not slot.manager):
        raise NativeToolRegistrationError("NATIVE_DISCOVERY_BINDING_INVALID")
    from registration_lifecycle import replacement_coordinator
    registry, source_schemas = _registry(), schemas()
    with replacement_coordinator.transaction(), slot._lock:
        if slot.discovery_attempted or slot.discovery_registration is not None:
            raise NativeToolRegistrationError("NATIVE_CONSUMER_ORIGINAL_REGISTRATION_RETAINED")
        if slot.package_check() is not True or binding.currentness() is not True:
            raise NativeToolRegistrationError("NATIVE_CONSUMER_PLUGIN_UNQUALIFIED")
        for name in wire.TOOLS:
            if (registry.snapshot_registration(name, scope=slot.scope) is not None
                    or registry.get_entry(name, scope=slot.scope) is not None):
                raise NativeToolRegistrationError("NATIVE_TOOL_COLLISION")
        slot.discovery_context, slot.discovery_attempted = ctx, True
        records = []
        try:
            for name in wire.TOOLS:
                handler = handler_for(binding, name)
                check_fn = lambda: registration_current(binding)
                schema = source_schemas[name]
                try:
                    handle = ctx.register_tool(name=name, toolset=TOOLSET, schema=schema, handler=handler,
                        check_fn=check_fn, is_async=False, description=schema["description"], emoji="mmx")
                except Exception as exc:
                    raise NativeToolRegistrationError("NATIVE_TOOL_REGISTRATION_EFFECT_UNKNOWN",
                        context=ctx, binding=binding, scope=slot.scope, tool_name=name) from exc
                if handle is None:
                    raise NativeToolRegistrationError("NATIVE_TOOL_REGISTRATION_EFFECT_UNKNOWN",
                        context=ctx, binding=binding, scope=slot.scope, tool_name=name)
                slot.discovery_handles.append((name, handle))
                entry = registry.snapshot_registration(name, scope=slot.scope)
                if (entry is None or entry.handler is not handler or entry.check_fn is not check_fn
                        or entry.toolset != TOOLSET or entry.schema != schema):
                    raise NativeToolRegistrationError("NATIVE_TOOL_READBACK_MISMATCH")
                records.append(DiscoveryToolRegistration(name, handler, check_fn, handle, entry, schema_digest(schema)))
            slot.discovery_registration = NativeDiscoveryRegistration(ctx, registry, binding, slot.scope, tuple(records))
            return slot.discovery_registration
        except Exception as error:
            # Dispose only actual leases returned to this original context.
            # An unreturned lease remains uncertain, even if prior leases clean up.
            for name, handle in reversed(slot.discovery_handles):
                try:
                    handle.dispose()
                except Exception as cleanup:
                    error = NativeToolRegistrationError("NATIVE_TOOL_ROLLBACK_EFFECT_UNKNOWN",
                        context=ctx, binding=binding, scope=slot.scope, handle=handle, tool_name=name)
                    error.__cause__ = cleanup
                    break
            slot.discovery_error = error
            slot.retain_registration_error(error)
            raise error


def readback(slot):
    binding = slot.discovery_binding
    if type(binding) is not NativeDiscoveryBinding or not registration_current(binding):
        raise NativeToolRegistrationError("NATIVE_DISCOVERY_REGISTRATION_UNAVAILABLE")
    with slot._lock:
        _settle_original_future(slot)
        return {"catalogue": wire.CATALOGUE, "registered": True,
                "tools": [{"name": item.name, "schema_sha256": item.schema_sha256}
                          for item in slot.discovery_registration.tools],
                "reservation_unresolved": bool(slot.discovery_call is not None and slot.discovery_call.get("refund_unknown")),
                "uncertain_original": copy.deepcopy(slot.discovery_uncertain)}
