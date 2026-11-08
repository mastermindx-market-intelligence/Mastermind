"""Compose a *disabled* native Hermes MCP config from the reviewed Steward donor.

This is an installer input, not authorization or a Steward connection.
The live server can be enabled only by a future receiving-owner authenticated
release; ordinary Hermes installs must not connect, post or dispatch.

The same module also owns the *qualified optional* consumer config: the exact
MCP/OAuth entry of the Executive connection, and the plugin grant that lets
the non-bundled consumer plugin call that one server. That config is rendered
only for a qualified optional input. The default stays disarmed, and neither
the bearer token nor any client secret is ever written here: the bearer stays
with the incumbent OAuth owner and its token storage.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.hermes_config import render_hermes_config
from integrations.hermes_steward.client import ALLOWED_TOOLS
from integrations.hermes_steward import config_guard

_SOURCE = Path(__file__).resolve().parents[1] / "hermes_steward" / "hermes.mcp.yaml"
_SERVER = "mastermind_steward"
_URL_ENV = "${MASTERMIND_STEWARD_MCP_URL}"
_AUTH_ENV = "Bearer ${MASTERMIND_STEWARD_ACCESS_TOKEN}"


def render_disarmed_native_config(profile: object) -> str:
    """Include exact Steward native MCP config with enabled=false.

    Fail closed if the existing WP3 source has drifted or supplies any extra
    server/tool. The result is actual Hermes config.yaml bytes; it is never
    evidence that a server connected or that a model can call tools.
    """
    if _SOURCE.is_symlink() or not _SOURCE.is_file():
        raise RuntimeRefusal("NATIVE_MCP_SOURCE_UNAVAILABLE")
    try:
        source_bytes = _SOURCE.read_bytes()
        if len(source_bytes) > 64 * 1024:
            raise RuntimeRefusal("NATIVE_MCP_SOURCE_TOO_LARGE")
        verdict = config_guard.inspect_file(_SOURCE)
        source = config_guard._load_unique_yaml(source_bytes)
    except RuntimeRefusal:
        raise
    except (OSError, ValueError, RuntimeError):
        raise RuntimeRefusal("NATIVE_MCP_SOURCE_INVALID") from None
    if verdict.get("status") != "PASS_OFFLINE_STEWARD_READ_CONFIG":
        raise RuntimeRefusal("NATIVE_MCP_SOURCE_UNQUALIFIED")
    if not isinstance(source, dict) or not isinstance(source.get("mcp_servers"), dict):
        raise RuntimeRefusal("NATIVE_MCP_SOURCE_UNQUALIFIED")
    servers = source["mcp_servers"]
    if set(servers) != {_SERVER} or not isinstance(servers[_SERVER], dict):
        raise RuntimeRefusal("NATIVE_MCP_SOURCE_UNQUALIFIED")
    server = deepcopy(servers[_SERVER])
    if (
        server.get("enabled") is not True
        or server.get("url") != _URL_ENV
        or server.get("headers") != {"Authorization": _AUTH_ENV}
        or server.get("tools") != {
            "include": list(ALLOWED_TOOLS),
            "resources": False,
            "prompts": False,
        }
        or set(server) != {"url", "headers", "enabled", "timeout", "tools"}
        or server.get("timeout") != 30
    ):
        raise RuntimeRefusal("NATIVE_MCP_SOURCE_UNQUALIFIED")
    server["enabled"] = False

    # PyYAML is only needed during real installer invocation, never by the
    # Secretary's shadow scanner import path.
    import yaml

    fragment = yaml.safe_dump(
        {"mcp_servers": {_SERVER: server}},
        sort_keys=False,
        allow_unicode=False,
    )
    result = render_hermes_config(profile) + fragment
    if len(result.encode("utf-8")) > 64 * 1024:
        raise RuntimeRefusal("NATIVE_MCP_RESULT_TOO_LARGE")
    try:
        rebuilt = config_guard._load_unique_yaml(result.encode("utf-8"))
    except ValueError:
        raise RuntimeRefusal("NATIVE_MCP_RESULT_INVALID") from None
    if rebuilt.get("mcp_servers") != {_SERVER: server}:
        raise RuntimeRefusal("NATIVE_MCP_RESULT_INVALID")
    return result


# The bounded connect timeout of the qualified Executive entry. It is the same
# bound the reviewed Steward donor uses.
_CONSUMER_TIMEOUT = 30


def render_consumer_mcp_server(publication: Any) -> dict[str, Any]:
    """The exact MCP/OAuth entry of the qualified Executive connection.

    The raw Executive tools of that server are never model-facing: the
    ``include`` filter is empty, so the upstream filter registers nothing for
    this server and only the C28 ``mmx_delegate`` exposes delegation.

    There is no bearer template, no token copy and no client secret here. The
    OAuth entry carries the *public* client reference and the scope; the
    bearer stays with the incumbent OAuth owner and its token storage.
    """
    from integrations.hermes_harness.native_executive_consumer import (
        CONSUMER_MCP_SERVER,
    )

    mcp = publication.mcp
    if mcp.server != CONSUMER_MCP_SERVER:
        raise RuntimeRefusal("NATIVE_CONSUMER_MCP_SERVER_INVALID")
    server = {
        "url": mcp.url,
        "enabled": True,
        "auth": "oauth",
        "timeout": _CONSUMER_TIMEOUT,
        "oauth": {
            "client_id": mcp.client_id,
            "scope": mcp.scope,
        },
        "tools": {
            "include": [],
            "resources": False,
            "prompts": False,
        },
    }
    if mcp._workspace_principal_scope is not None:
        from integrations.hermes_harness.native_executive_consumer import workspace_oauth_descriptor
        server["oauth"]["workspace"] = workspace_oauth_descriptor(mcp._workspace_principal_scope)
        server.update(transport="streamable-http", strict_redirect_headers=True)
    return server


def render_consumer_plugin_config(publication: Any) -> dict[str, Any]:
    """The plugin grant of the qualified consumer.

    The upstream plugin loader is opt-in: a *user* plugin loads only when the
    operator lists it in ``plugins.enabled``. The per-server MCP grant is
    default-deny, so the Executive server is named explicitly. Nothing else
    is granted.
    """
    from integrations.hermes_harness.native_executive_consumer import (
        CONSUMER_PLUGIN_NAME,
    )

    return {
        "enabled": [CONSUMER_PLUGIN_NAME],
        "entries": {
            CONSUMER_PLUGIN_NAME: {
                "mcp_allowlist": [publication.mcp.server],
            },
        },
    }
