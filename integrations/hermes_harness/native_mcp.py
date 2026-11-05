"""Compose a *disabled* native Hermes MCP config from the reviewed Steward donor.

This is an installer input, not authorization or a Steward connection.
The live server can be enabled only by a future receiving-owner authenticated
release; ordinary Hermes installs must not connect, post or dispatch.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

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
