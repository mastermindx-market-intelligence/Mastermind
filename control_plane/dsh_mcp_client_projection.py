"""Inert DSH projection of existing Executive MCP policy; never launch admission.

The existing registry/digest owns policy. This projection neither adds DSH to
its execution surfaces nor transfers a Codex/Claude entitlement to DSH. A trusted
host must separately attest the actual DSH Attempt, artifact and resource realm.
No discovery, credential read, installation, process or provider call occurs here.
"""
from __future__ import annotations
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Mapping
from urllib.parse import urlsplit
from control_plane.executive_agent_capabilities import (
    ExecutionCapabilityProfile, observed_mcp_tool_schema_digest,
)


class DshMcpProjectionError(ValueError):
    """The existing grant cannot be represented without widening its rights."""


@dataclass(frozen=True)
class DshMcpToolProjection:
    _configuration_json: str
    production_armed: bool = field(default=False, init=False)

    def configuration(self) -> dict[str, Any]:
        return json.loads(self._configuration_json)


def _json_copy(value: Any) -> Any:
    def visit(item: Any, depth: int = 0) -> None:
        if depth > 40: raise DshMcpProjectionError('catalog nesting exceeds bound')
        kind = type(item)
        if kind is dict:
            if any(type(key) is not str for key in item):
                raise DshMcpProjectionError('catalog keys must be strings')
            for child in item.values(): visit(child, depth + 1)
        elif kind is list:
            for child in item: visit(child, depth + 1)
        elif kind is int and abs(item) > 9007199254740991:
            raise DshMcpProjectionError('catalog integer cannot cross the JS boundary exactly')
        elif kind is float and not math.isfinite(item):
            raise DshMcpProjectionError('catalog number must be finite')
        elif kind not in (str, int, float, bool, type(None)):
            raise DshMcpProjectionError('catalog is not plain JSON')
    visit(value)
    text = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
    if len(text) > 262144: raise DshMcpProjectionError('catalog exceeds byte bound')
    return json.loads(text)


def project_dsh_mcp_tools(profile: ExecutionCapabilityProfile, *, capability_id: str,
                          observed_tool_catalog: Mapping[str, Any]) -> DshMcpToolProjection:
    """Project one validated grant plus a complete owner-approved catalog.

    This does not authenticate a catalog or make a profile DSH-eligible. The
    runtime consumes this ONLY from its trusted host, never from model/YAML data.
    """
    if not isinstance(profile, ExecutionCapabilityProfile) or profile.enabled is not True:
        raise DshMcpProjectionError('enabled validated source profile required')
    grants = [g for g in profile.mcp_server_grants if g.capability_id == capability_id]
    if len(grants) != 1: raise DshMcpProjectionError('exact source grant required')
    grant = grants[0]
    if (grant.required is not True or grant.default_tools_approval_mode != 'approve'
            or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,31}', grant.config_name)):
        raise DshMcpProjectionError('grant startup or approval semantics are unsupported')
    enabled = grant.enabled_tools
    if (not isinstance(enabled, tuple) or not enabled or len(set(enabled)) != len(enabled)
            or any(not isinstance(n, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,127}', n) for n in enabled)):
        raise DshMcpProjectionError('nonempty exact tool names required')
    for value in [profile.profile_digest, grant.grant_digest, grant.tool_schema_digest]:
        if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
            raise DshMcpProjectionError('source digest missing')
    target: dict[str, Any] = {'serverName': grant.config_name, 'transport': grant.transport}
    if grant.transport == 'stdio':
        if (not isinstance(grant.command, str) or not PurePosixPath(grant.command).is_absolute()
                or grant.url is not None or not isinstance(grant.args, tuple)
                or any(not isinstance(arg, str) or '\0' in arg for arg in grant.args)):
            raise DshMcpProjectionError('exact absolute stdio target required')
        target.update(command=grant.command, args=list(grant.args))
    elif grant.transport == 'streamable-http':
        try: parsed = urlsplit(grant.url or '')
        except ValueError as exc: raise DshMcpProjectionError('invalid HTTP target') from exc
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or grant.command is not None or grant.args):
            raise DshMcpProjectionError('exact secret-free HTTPS target required')
        target['url'] = grant.url
    else: raise DshMcpProjectionError('unsupported MCP transport')
    catalog = _json_copy(observed_tool_catalog)
    if not isinstance(catalog, dict) or catalog.get('nextCursor') not in (None, ''):
        raise DshMcpProjectionError('complete tool catalog required')
    rows = catalog.get('tools')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 256:
        raise DshMcpProjectionError('tool catalog missing or oversized')
    by_name: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = row.get('name') if isinstance(row, dict) else None
        if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,127}', name)
                or name in by_name or not isinstance(row.get('inputSchema'), dict)):
            raise DshMcpProjectionError('catalog tool identity or schema invalid')
        for key in ['outputSchema', 'annotations', 'execution']:
            if row.get(key) is not None and not isinstance(row[key], dict):
                raise DshMcpProjectionError('catalog contract invalid')
        by_name[name] = row
    if not set(enabled) <= set(by_name): raise DshMcpProjectionError('granted tool missing')
    selected = {name: by_name[name] for name in sorted(enabled)}
    # Deliberately reuse the canonical Python owner; no JS digest clone.
    if observed_mcp_tool_schema_digest({'tools': selected}) != grant.tool_schema_digest:
        raise DshMcpProjectionError('granted tool schema drift')
    tools = [{'name': name, 'inputSchema': row['inputSchema'],
              'outputSchema': row.get('outputSchema'), 'annotations': row.get('annotations'),
              'execution': row.get('execution')} for name, row in selected.items()]
    value = {'schema': 'mastermind.dsh_mcp_tool_projection.v1', 'production_armed': False,
             'source': {'profile_id': profile.profile_id, 'profile_digest': profile.profile_digest,
                        'execution_surface': profile.execution_surface, 'auth_realm': profile.auth_realm,
                        'capability_id': grant.capability_id, 'grant_digest': grant.grant_digest,
                        'tool_schema_digest': grant.tool_schema_digest, 'auth_status': grant.auth_status},
             'target': target, 'serverInfo': {'name': grant.server_identity, 'version': grant.server_version},
             'required': True, 'approvalMode': 'approve', 'tools': tools}
    return DshMcpToolProjection(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                         ensure_ascii=True, allow_nan=False))
