"""Configuration-only Claude projections of existing Executive MCP grants.

This module does not admit a provider, launch a process, allocate a browser,
read credentials, grant helper authority or change an execution surface.
An adapter must still prove the full requested/observed profile, transport,
server-side tool guard and Attempt-bound resource environment. In particular,
CLI allowedTools means auto-approval, not a security boundary or tool filter.
Never install this output over ambient Desktop/Claude settings automatically.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from control_plane.executive_agent_capabilities import (
    ExecutionCapabilityProfile, observed_mcp_tool_schema_digest,
)
from control_plane.operator_harness_contract import NativeHelperPolicy

_SURFACES = frozenset({"cli", "agent-sdk", "desktop-local", "inline-subagent"})
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,127}")
_TOOL = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,127}")


class ClaudeMcpProjectionError(ValueError):
    """A grant cannot be represented faithfully on the selected client."""


@dataclass(frozen=True)
class ClaudeMcpClientProjection:
    surface: str
    source_profile_id: str
    source_profile_digest: str
    source_grant_digests: tuple[str, ...]
    source_tool_schema_digests: tuple[str, ...]
    enabled_tools: tuple[str, ...]
    auto_approved_tools: tuple[str, ...]
    denied_tools: tuple[str, ...]
    source_tool_catalog_digests: tuple[tuple[str, str], ...]  # (config_name, schema digest)
    _configuration_json: str
    production_armed: bool = field(default=False, init=False)

    def configuration(self) -> dict[str, Any]:
        """Return an independent client-shaped copy, not mutable grant state."""
        return json.loads(self._configuration_json)

    def cli_arguments(self) -> tuple[str, ...]:
        """An argv fragment; no shell interpolation or permission-mode override.

        Existing denies remain authoritative. This fragment must not be used to
        remove mcp__* from the sealed subscription-worker profile. The adapter
        must reconcile its complete CLI/settings and enforce its server guard.
        """
        if self.surface != "cli":
            raise ClaudeMcpProjectionError("CLI arguments require the cli surface")
        result = ("--strict-mcp-config", "--mcp-config", self._configuration_json)
        if self.auto_approved_tools:
            result += ("--allowedTools", *self.auto_approved_tools)
        if self.denied_tools:
            result += ("--disallowedTools", *self.denied_tools)
        return result


def _catalog_denials(profile, catalogs):
    """Translate complete owner-supplied tools/list observations; no probing or I/O.

    Bind allowed schemas using the existing attestation digest. Also retain the
    full catalog digest so a caller can recheck it after connection/reconnection.
    The existing runtime owner still has to enforce the grant server-side;
    configuration and a caller-supplied catalog are not launch authorization.
    """
    if catalogs is None:
        return (), ()
    names = {grant.config_name for grant in profile.mcp_server_grants}
    if not isinstance(catalogs, Mapping) or set(catalogs) != names:
        raise ClaudeMcpProjectionError("observed catalog server identities differ")
    denied, digests = [], []
    for grant in profile.mcp_server_grants:
        catalog = catalogs[grant.config_name]
        if not isinstance(catalog, Mapping) or catalog.get("nextCursor") not in (None, ""):
            raise ClaudeMcpProjectionError("observed catalog is incomplete or paginated")
        rows = catalog.get("tools")
        if not isinstance(rows, list) or not 1 <= len(rows) <= 256:
            raise ClaudeMcpProjectionError("observed catalog tools are missing or oversized")
        tools = {}
        for row in rows:
            if not isinstance(row, Mapping):
                raise ClaudeMcpProjectionError("observed catalog tool is invalid")
            name = row.get("name")
            if (not isinstance(name, str) or not _TOOL.fullmatch(name)
                    or "__" in name or name in tools):
                raise ClaudeMcpProjectionError("observed catalog tool name is invalid or duplicated")
            tools[name] = row
        allowed = set(grant.enabled_tools)
        if not allowed <= set(tools):
            raise ClaudeMcpProjectionError("observed catalog lacks a granted tool")
        try:
            full_digest = observed_mcp_tool_schema_digest({"tools": tools})
            grant_digest = observed_mcp_tool_schema_digest(
                {"tools": {name: tools[name] for name in allowed}})
        except (TypeError, ValueError) as exc:
            raise ClaudeMcpProjectionError("observed catalog schema cannot be normalized") from exc
        if full_digest is None or grant_digest != grant.tool_schema_digest:
            raise ClaudeMcpProjectionError("observed catalog tool schema drift")
        digests.append((grant.config_name, full_digest))
        denied.extend(f"mcp__{grant.config_name}__{name}" for name in set(tools) - allowed)
    return tuple(sorted(denied)), tuple(sorted(digests))


def project_claude_mcp_client(
    profile: ExecutionCapabilityProfile, *, surface: str,
    observed_tool_catalogs: Mapping[str, Mapping[str, Any]] | None = None,
) -> ClaudeMcpClientProjection:
    """Project a trusted, already-validated capability profile without arming it.

    A configuration candidate is not an assertion that a Codex-only profile is
    admitted on Claude. Native helper enablement is a necessary, not sufficient,
    condition: a child also needs its own admitted browser resource generation.
    """
    if not isinstance(surface, str) or surface not in _SURFACES:
        raise ClaudeMcpProjectionError("unsupported Claude client surface")
    if not isinstance(profile, ExecutionCapabilityProfile) or not profile.enabled:
        raise ClaudeMcpProjectionError("an enabled validated profile is required")
    if surface == "inline-subagent" and profile.native_helper_policy == NativeHelperPolicy.DISABLED:
        raise ClaudeMcpProjectionError("profile forbids native helper admission")
    servers: dict[str, dict[str, Any]] = {}
    enabled: set[str] = set()
    approved: set[str] = set()
    for grant in profile.mcp_server_grants:
        name = grant.config_name
        if not isinstance(name, str) or not _NAME.fullmatch(name) or "__" in name or name in servers:
            raise ClaudeMcpProjectionError("invalid, ambiguous or duplicate MCP server name")
        if grant.default_tools_approval_mode not in {"approve", "prompt"}:
            raise ClaudeMcpProjectionError("unsupported tool approval semantics")
        if grant.transport == "stdio":
            if not isinstance(grant.command, str) or not grant.command or grant.url is not None:
                raise ClaudeMcpProjectionError("invalid stdio grant")
            if not isinstance(grant.args, tuple) or any(not isinstance(a, str) for a in grant.args):
                raise ClaudeMcpProjectionError("invalid stdio arguments")
            entry: dict[str, Any] = {"command": grant.command, "args": list(grant.args)}
            if surface != "desktop-local":
                entry["type"] = "stdio"
        elif grant.transport == "streamable-http":
            if surface == "desktop-local":
                raise ClaudeMcpProjectionError("Desktop HTTP requires an admitted local bridge or remote connector")
            if not isinstance(grant.url, str) or not grant.url.startswith("https://") or grant.command is not None or grant.args:
                raise ClaudeMcpProjectionError("invalid HTTP grant")
            entry = {"type": "http", "url": grant.url}
        else:
            raise ClaudeMcpProjectionError("unsupported MCP transport")
        servers[name] = entry
        for tool in grant.enabled_tools:
            if not isinstance(tool, str) or not _TOOL.fullmatch(tool):
                raise ClaudeMcpProjectionError("invalid or wildcard MCP tool name")
            full = f"mcp__{name}__{tool}"
            if full in enabled:
                raise ClaudeMcpProjectionError("duplicate MCP tool grant")
            enabled.add(full)
            if grant.default_tools_approval_mode == "approve":
                approved.add(full)
    if surface == "inline-subagent" and observed_tool_catalogs is None:
        raise ClaudeMcpProjectionError("inline MCP requires a complete observed tool catalog")
    denied, catalog_digests = _catalog_denials(profile, observed_tool_catalogs)
    servers = dict(sorted(servers.items()))
    tools, auto = tuple(sorted(enabled)), tuple(sorted(approved))
    if surface == "agent-sdk":
        configuration: dict[str, Any] = {"mcp_servers": servers, "allowed_tools": list(auto), "strict_mcp_config": True}
        if observed_tool_catalogs is not None:
            configuration["disallowed_tools"] = list(denied)
    elif surface == "inline-subagent":
        # Inline definitions create connections; strings reuse the parent.
        # A new connection alone does not prove independent browser ownership.
        configuration = {"mcpServers": [{name: config} for name, config in servers.items()],
                         "tools": list(tools), "disallowedTools": list(denied)}
    else:
        configuration = {"mcpServers": servers}
    return ClaudeMcpClientProjection(
        surface=surface,
        source_profile_id=profile.profile_id,
        source_profile_digest=profile.profile_digest,
        source_grant_digests=tuple(sorted(g.grant_digest for g in profile.mcp_server_grants)),
        source_tool_schema_digests=tuple(sorted(g.tool_schema_digest for g in profile.mcp_server_grants)),
        enabled_tools=tools,
        auto_approved_tools=auto,
        denied_tools=denied,
        source_tool_catalog_digests=catalog_digests,
        _configuration_json=json.dumps(configuration, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
    )
