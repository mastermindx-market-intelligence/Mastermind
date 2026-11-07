"""Join Hermes's EXISTING MCP client to the enrolled Fabric-only facade.

This does not configure a server, open a socket, read credentials, create
an admission principal, or install a plugin. Hermes PluginContext.call_mcp
enforces a profile/plugin-specific MCP allowlist. The host must independently
bind the original session grant and original-effect admission authority.
"""
from __future__ import annotations

import inspect
import json
import re
from collections.abc import Mapping
from typing import Any, Callable

from .native import FabricNativeRefusal

EXECUTION_SERVER = "mastermind-fabric-exec"
FABRIC_SCHEMA = "mastermind.fabric_mcp.v1"
NATIVE_ACTIONS = frozenset({"fabric_capabilities", "fabric_status", "fabric_request", "fabric_result"})
_MAX_RETURN_CHARS = 65536
_ERROR = "HERMES_FABRIC_MCP_UNAVAILABLE"


def bind_native_mcp_client(ctx: Any) -> Callable[[str, Mapping[str, Any]], Mapping[str, Any]]:
    """Return one owner-backed synchronous client, default-deny without enrollment.

    The existing read-only `mastermind-fabric-capacity` MCP is intentionally
    not a substitute. Native MCP server naming and plugin allowlist policy
    belong to the installed Hermes profile, not to this module or an LLM.
    """
    client = getattr(ctx, "call_mcp", None)
    allowlist_reader = getattr(ctx, "_mcp_allowlist", None)
    plugin_id = getattr(ctx, "plugin_id", None)
    if (not callable(client) or inspect.iscoroutinefunction(client)
            or not callable(allowlist_reader)
            or type(plugin_id) is not str or not plugin_id):
        raise FabricNativeRefusal("HERMES_NATIVE_MCP_OWNER_UNAVAILABLE")
    try:
        allowlist = allowlist_reader(plugin_id)
    except Exception:
        raise FabricNativeRefusal("HERMES_NATIVE_MCP_ENROLLMENT_UNKNOWN") from None
    if (type(allowlist) is not list
            or EXECUTION_SERVER not in allowlist):
        raise FabricNativeRefusal("HERMES_FABRIC_EXECUTION_NOT_ENROLLED")

    def call_tool(action: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        if action not in NATIVE_ACTIONS or not isinstance(arguments, Mapping):
            raise FabricNativeRefusal("HERMES_FABRIC_ACTION_NOT_ALLOWED")
        # On every call, Hermes itself rechecks current profile-scoped MCP
        # consent; this preliminary read additionally fences stale bindings.
        try:
            current = allowlist_reader(plugin_id)
            if type(current) is not list or EXECUTION_SERVER not in current:
                raise FabricNativeRefusal("HERMES_FABRIC_EXECUTION_NOT_ENROLLED")
        except FabricNativeRefusal:
            raise
        except Exception:
            raise FabricNativeRefusal("HERMES_NATIVE_MCP_ENROLLMENT_UNKNOWN") from None
        try:
            reply = client(EXECUTION_SERVER, action, dict(arguments), timeout=30)
            if inspect.isawaitable(reply):
                raise FabricNativeRefusal(_ERROR)
        except Exception:
            raise FabricNativeRefusal(_ERROR) from None
        if not isinstance(reply, Mapping) or reply.get("truncated") is True:
            raise FabricNativeRefusal("HERMES_FABRIC_MCP_RESPONSE_INVALID")
        if reply.get("ok") is not True:
            raise FabricNativeRefusal("HERMES_FABRIC_MCP_RESPONSE_REFUSED")
        # Native Hermes removes duplicate structuredContent when its JSON is
        # already in a text block. Decode that one exact result string from
        # this enrolled client, then apply the same canonical schema checks.
        # Never scrape logs, nested responses or another server's text.
        document = reply.get("structuredContent")
        if document is None:
            document = reply.get("result")
            if type(document) is str and len(document) <= _MAX_RETURN_CHARS:
                try:
                    document = json.loads(document)
                except (TypeError, ValueError):
                    raise FabricNativeRefusal("HERMES_FABRIC_MCP_SCHEMA_INVALID") from None
        if (not isinstance(document, Mapping)
                or document.get("schema") != FABRIC_SCHEMA
                or document.get("action") != (
                    "capabilities" if action == "fabric_capabilities" else action)):
            raise FabricNativeRefusal("HERMES_FABRIC_MCP_SCHEMA_INVALID")
        # The native client's admission check precedes transport. Consent may
        # change while that call runs, so it must also govern response release.
        after_error = None
        try:
            current = allowlist_reader(plugin_id)
            if type(current) is not list or EXECUTION_SERVER not in current:
                after_error = "HERMES_FABRIC_EXECUTION_NOT_ENROLLED"
        except Exception:
            after_error = "HERMES_NATIVE_MCP_ENROLLMENT_UNKNOWN"
        if after_error:
            if action != "fabric_request" or document.get("error") is not None:
                raise FabricNativeRefusal(after_error)
            # Preserve only the recorded submit control receipt for the typed
            # port to authenticate against its original run/root/parent. An
            # incomplete receipt still becomes EFFECT_UNKNOWN there; it is
            # never labelled NOT_APPLIED. No returned result/diagnostic passes.
            receipt = {key: document[key] for key in (
                "schema", "action", "run_id", "root_id", "parent_id",
                "delivery", "controller_pid", "worker_start_proven",
            ) if key in document}
            receipt["response_withheld"] = True
            return receipt
        # The incumbent typed port performs full run/root/parent/response
        # attestation; no field transformation or invented witness here.
        return dict(document)

    return call_tool
