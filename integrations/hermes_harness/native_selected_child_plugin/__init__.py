"""The non-bundled native plugin that exposes the closed selected-child tool.

The upstream loader calls ``register(ctx)`` with exactly one argument: the
plugin context. It injects no binding, no target, no transport and no
authority. This package therefore takes the startup from the fixed typed
owner-private slot on the ACTUAL per-profile PluginManager that the held
native startup installed, and it refuses when that slot is absent, foreign or
bound to another profile.

An ordinary unbound discovery registers nothing. The model never sees a
delegation tool that is not backed by a qualified, current binding, and the
raw Executive MCP tools of that server are never model-facing: only the C28
``mmx_delegate`` exposes delegation.

The package is installed as a *user* (non-bundled) directory plugin. It never
claims the bundled source, never replaces the global plugin manager and never
writes the tool registry directly: the actual registration, the profile scope
and the unload lease all stay with the upstream owner.
"""
from __future__ import annotations

from typing import Any

from integrations.hermes_harness.native_executive_consumer import (
    CONSUMER_PLUGIN_NAME,
    CONSUMER_PLUGIN_SOURCE,
    ConsumerSlot,
    ExecutiveContextConsumerPublication,
    selected_child_publication,
    read_consumer_slot,
)
from integrations.hermes_harness.native_tool_registration import (
    NativeToolRegistrationError,
    register_native_delegate_tools,
)
from integrations.hermes_runtime.native_session_control import current_runtime_owner

__all__ = ["register"]


def _assert_mcp_allowed(ctx: Any, slot: ConsumerSlot) -> None:
    """Require the incumbent per-server MCP allowlist to name the server.

    The upstream plugin MCP grant is default-deny and per server. A plugin
    that may not call the Executive server never registers the delegation
    tool, so the grant is checked by the same owner that reads it.
    """
    server = slot.publication.mcp.server
    allowlist = ctx._mcp_allowlist(ctx.plugin_id)
    if server not in allowlist:
        raise NativeToolRegistrationError("NATIVE_CONSUMER_MCP_NOT_ALLOWED")


def register(ctx: Any):
    """Retain original registration owners before C28 can have an effect."""
    # General PluginContext.register_memory_provider is intentionally inert.
    # Only the real native memory collector can receive the actual provider.
    if type(ctx).__module__ == "plugins.memory" and type(ctx).__name__ == "_ProviderCollector":
        from plugins.memory import _ProviderCollector
        if type(ctx) is not _ProviderCollector:
            raise NativeToolRegistrationError("NATIVE_PLUGIN_CONTEXT_INVALID")
        from integrations.hermes_runtime.native_agentos_memory import register_memory_provider
        return register_memory_provider(ctx)
    owner = current_runtime_owner()
    if not owner:
        raise NativeToolRegistrationError("NATIVE_CONSUMER_OWNER_UNAVAILABLE")
    slot = read_consumer_slot(ctx, owner=owner, source=CONSUMER_PLUGIN_SOURCE,
                              plugin_id=CONSUMER_PLUGIN_NAME)
    _assert_mcp_allowed(ctx, slot)
    if type(slot.publication) is ExecutiveContextConsumerPublication:
        from integrations.hermes_runtime.native_agentos_memory import NativeAgentOsMemoryFactory
        if (type(slot.memory_factory) is not NativeAgentOsMemoryFactory
                or not slot.memory_factory.loader_ready() or slot.context_registration is not None):
            raise NativeToolRegistrationError("NATIVE_AGENTOS_FACTORY_UNAVAILABLE")
        slot.context_registration = ctx
        if slot.publication.discovery:
            from integrations.hermes_harness.native_discovery_tools import register_discovery_tools
            try:
                register_discovery_tools(ctx, slot)
            except Exception as error:
                slot.retain_registration_error(error)
                raise
        if selected_child_publication(slot.publication) is None:
            return None
    slot.begin_registration(ctx)
    try:
        registration = register_native_delegate_tools(ctx, slot.startup)
        slot.publish_registration(registration)
        return registration
    except Exception as error:
        # The native loader may catch the exception. This original private slot
        # keeps its exact context/binding/handle and uncertainty for reconciliation.
        slot.retain_registration_error(error)
        raise
