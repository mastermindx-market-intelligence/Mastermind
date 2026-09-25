"""Compile a closed Claude Code native-helper roster from reviewed capability facts.

This module is a provider-syntax projection, not an admission or routing owner.
It creates no Job/Attempt, provider/account/model/host choice, retry state, or
credential state. A caller must already own the parent Attempt and must still
prove a Claude-specific execution binding before using the projection in
production. The production_armed flag is therefore permanently false.

V1 helpers are deliberately read-only, same-Attempt subordinates. Work that
needs writes, independent review, durable continuation, another worker, or
separate effect custody belongs in an Executive child Job instead.
"""
from __future__ import annotations

import dataclasses
import json
import re
from typing import Any, Mapping, Sequence

from control_plane.claude_mcp_client_projection import (
    ClaudeMcpProjectionError,
    project_claude_mcp_client,
)
from control_plane.executive_agent_capabilities import ExecutionCapabilityProfile
from control_plane.operator_harness_contract import (
    NativeHelperPolicy,
    ObservedTriState,
    native_helpers_allowed,
)

_AGENT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_MAX_AGENTS = 16
_MAX_DESCRIPTION_BYTES = 2048
_MAX_PROMPT_BYTES = 16384
_MAX_TURNS = 32
_READ_ONLY_BUILTINS = frozenset({"Read", "Glob", "Grep"})
_ALWAYS_DENIED = (
    "Agent",
    "Bash",
    "Edit",
    "Write",
    "NotebookEdit",
    "Skill",
    "Task",
    "WebFetch",
    "WebSearch",
)
_PERMISSION_MODES = frozenset({"dontAsk", "bypassPermissions"})


class ClaudeNativeHelperProjectionError(ValueError):
    """The requested native-helper projection would widen the parent ceiling."""


@dataclasses.dataclass(frozen=True)
class ClaudeNativeHelperDefinition:
    """One source-reviewed role Claude may choose from by description."""

    agent_id: str
    description: str
    prompt: str
    max_turns: int = 12


@dataclasses.dataclass(frozen=True)
class ClaudeNativeHelperProjection:
    source_profile_id: str
    source_profile_digest: str
    source_native_helper_grant_digest: str
    source_native_helper_mechanism: str
    source_mcp_grant_digests: tuple[str, ...]
    source_mcp_tool_schema_digests: tuple[str, ...]
    permission_mode: str
    agent_ids: tuple[str, ...]
    enabled_tools: tuple[str, ...]
    auto_approved_tools: tuple[str, ...]
    denied_tools: tuple[str, ...]
    _agents_json: str
    _max_concurrent_helpers: int
    _max_depth: int
    production_armed: bool = dataclasses.field(default=False, init=False)

    def agents(self) -> dict[str, Any]:
        return json.loads(self._agents_json)

    def cli_arguments(self) -> tuple[str, ...]:
        """Session-scoped roster plus no-card admission of the Agent tool."""

        allowed = ("Agent", *self.auto_approved_tools)
        return (
            "--permission-mode",
            self.permission_mode,
            "--allowedTools",
            *allowed,
            "--agents",
            self._agents_json,
        )

    def environment(self) -> dict[str, str]:
        """Provider-native width/depth controls translated from the source grant."""

        return {
            "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS": str(
                self._max_concurrent_helpers
            ),
            "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": str(self._max_depth),
        }


def _bounded_text(value: Any, *, field: str, max_bytes: int) -> str:
    if not isinstance(value, str):
        raise ClaudeNativeHelperProjectionError(f"{field} must be text")
    token = value.strip()
    if not token or len(token.encode("utf-8")) > max_bytes or "\x00" in token:
        raise ClaudeNativeHelperProjectionError(f"{field} is empty or oversized")
    return token


def project_claude_native_helpers(
    profile: ExecutionCapabilityProfile,
    *,
    helpers: Sequence[ClaudeNativeHelperDefinition],
    permission_mode: str,
    observed_tool_catalogs: Mapping[str, Mapping[str, Any]] | None = None,
) -> ClaudeNativeHelperProjection:
    """Project an exact read-only helper roster; never infer broader authority."""

    if not isinstance(profile, ExecutionCapabilityProfile) or not profile.enabled:
        raise ClaudeNativeHelperProjectionError(
            "an enabled capability profile is required"
        )
    if permission_mode not in _PERMISSION_MODES:
        raise ClaudeNativeHelperProjectionError(
            "parent permission mode is not unattended"
        )
    grant = profile.native_helper
    if grant is None:
        raise ClaudeNativeHelperProjectionError("profile has no native helper grant")
    if profile.write_capable:
        raise ClaudeNativeHelperProjectionError(
            "v1 Claude native helpers are read-only; write work must use an "
            "Executive child Job"
        )
    if (
        profile.native_helper_policy
        is not NativeHelperPolicy.PARENT_READ_ONLY_CEILING
    ):
        raise ClaudeNativeHelperProjectionError(
            "profile does not admit read-only native helpers"
        )
    if not native_helpers_allowed(
        write_capable=False,
        native_helper_policy=profile.native_helper_policy,
        supports_subagent_capability_ceiling=ObservedTriState.VERIFIED,
    ):
        raise ClaudeNativeHelperProjectionError(
            "native helper capability ceiling is not admitted"
        )
    if not grant.inherit_parent_capabilities or not grant.hide_spawn_agent_metadata:
        raise ClaudeNativeHelperProjectionError(
            "native helper grant is not shrink-only"
        )
    if (
        type(grant.max_concurrent_helpers) is not int
        or grant.max_concurrent_helpers < 1
    ):
        raise ClaudeNativeHelperProjectionError(
            "native helper concurrency ceiling is invalid"
        )
    if type(grant.max_depth) is not int or grant.max_depth != 1:
        raise ClaudeNativeHelperProjectionError(
            "Claude v1 requires native helper depth exactly one"
        )
    if (
        type(grant.max_runtime_seconds) is not int
        or grant.max_runtime_seconds < 1
    ):
        raise ClaudeNativeHelperProjectionError(
            "native helper runtime ceiling is invalid"
        )

    definitions = tuple(helpers)
    if not definitions or len(definitions) > _MAX_AGENTS:
        raise ClaudeNativeHelperProjectionError(
            "native helper roster cardinality is invalid"
        )
    if any(
        not isinstance(item, ClaudeNativeHelperDefinition) for item in definitions
    ):
        raise ClaudeNativeHelperProjectionError("helper definition type is invalid")
    ids = tuple(item.agent_id for item in definitions)
    if len(set(ids)) != len(ids):
        raise ClaudeNativeHelperProjectionError("native helper ids are duplicated")
    if tuple(sorted(ids)) != ids:
        raise ClaudeNativeHelperProjectionError(
            "native helper roster must be canonically sorted"
        )

    catalogs = observed_tool_catalogs
    if catalogs is None and not profile.mcp_server_grants:
        catalogs = {}
    try:
        mcp = project_claude_mcp_client(
            profile,
            surface="inline-subagent",
            observed_tool_catalogs=catalogs,
        )
    except (ClaudeMcpProjectionError, ValueError, TypeError) as exc:
        raise ClaudeNativeHelperProjectionError(
            "inline helper MCP projection is not closed"
        ) from exc

    child_mcp = mcp.configuration()
    mcp_tools = tuple(sorted(mcp.enabled_tools))
    denied = tuple(sorted(set(_ALWAYS_DENIED) | set(mcp.denied_tools)))
    tools = tuple(sorted(_READ_ONLY_BUILTINS | set(mcp_tools)))

    agents: dict[str, dict[str, Any]] = {}
    for item in definitions:
        if _AGENT_ID_RE.fullmatch(item.agent_id) is None:
            raise ClaudeNativeHelperProjectionError("native helper id is invalid")
        description = _bounded_text(
            item.description,
            field="native helper description",
            max_bytes=_MAX_DESCRIPTION_BYTES,
        )
        prompt = _bounded_text(
            item.prompt,
            field="native helper prompt",
            max_bytes=_MAX_PROMPT_BYTES,
        )
        if (
            type(item.max_turns) is not int
            or not 1 <= item.max_turns <= _MAX_TURNS
        ):
            raise ClaudeNativeHelperProjectionError(
                "native helper max_turns is invalid"
            )
        agents[item.agent_id] = {
            "description": description,
            "prompt": prompt,
            "model": "inherit",
            "maxTurns": item.max_turns,
            "tools": list(tools),
            "disallowedTools": list(denied),
            "mcpServers": child_mcp.get("mcpServers", []),
        }

    payload = json.dumps(
        agents,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return ClaudeNativeHelperProjection(
        source_profile_id=profile.profile_id,
        source_profile_digest=profile.profile_digest,
        source_native_helper_grant_digest=grant.grant_digest,
        source_native_helper_mechanism=grant.mechanism,
        source_mcp_grant_digests=tuple(
            sorted(item.grant_digest for item in profile.mcp_server_grants)
        ),
        source_mcp_tool_schema_digests=tuple(
            sorted(item.tool_schema_digest for item in profile.mcp_server_grants)
        ),
        permission_mode=permission_mode,
        agent_ids=ids,
        enabled_tools=tools,
        auto_approved_tools=tuple(sorted(mcp.auto_approved_tools)),
        denied_tools=denied,
        _agents_json=payload,
        _max_concurrent_helpers=grant.max_concurrent_helpers,
        _max_depth=grant.max_depth,
    )


__all__ = [
    "ClaudeNativeHelperDefinition",
    "ClaudeNativeHelperProjection",
    "ClaudeNativeHelperProjectionError",
    "project_claude_native_helpers",
]
