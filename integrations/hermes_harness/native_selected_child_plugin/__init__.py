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
    """Register the one selected-child tool through the upstream owner.

    The loader calls this with the plugin context only. Every input comes
    from the owner-private slot the held native startup installed, and every
    refusal leaves no tool registered.
    """
    owner = current_runtime_owner()
    if not owner:
        # The held native startup did not bind this process's owner identity.
        raise NativeToolRegistrationError("NATIVE_CONSUMER_OWNER_UNAVAILABLE")
    slot = read_consumer_slot(ctx, owner=owner, source=CONSUMER_PLUGIN_SOURCE,
                               plugin_id=CONSUMER_PLUGIN_NAME)
    _assert_mcp_allowed(ctx, slot)
    registration = register_native_delegate_tools(ctx, slot.startup)
    # The one registration this slot may own. A second, different one is
    # refused; the original context and lease stay with the upstream owner.
    slot.publish_registration(registration)
    return registration
