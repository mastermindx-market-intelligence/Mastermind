from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from control_plane.claude_native_helper_projection import (
    ClaudeNativeHelperDefinition,
    ClaudeNativeHelperProjectionError,
    project_claude_native_helpers,
)
from control_plane.executive_agent_capabilities import (
    ExecutionCapabilityRegistry,
    observed_mcp_tool_schema_digest,
)
from control_plane.operator_harness_contract import ObservedTriState


@pytest.fixture
def profile():
    registry = ExecutionCapabilityRegistry.load(
        Path(
            "scripts/ohf/fixtures/"
            "executive_agent_capabilities_v4_mastermind_operator.json"
        ),
        source_root=Path.cwd(),
    )
    return registry.resolve(
        "operator.appserver.readonly.docs-mcp.native-helper.v1"
    )


def _roster():
    return (
        ClaudeNativeHelperDefinition(
            agent_id="code-reader",
            description=(
                "Inspect implementation evidence when code-reading is the "
                "smallest sufficient same-session task."
            ),
            prompt="Read only. Return bounded evidence, findings, and risks.",
            max_turns=8,
        ),
        ClaudeNativeHelperDefinition(
            agent_id="research-scout",
            description=(
                "Gather bounded source facts already exposed to this session "
                "when independent company custody is not required."
            ),
            prompt="Read only. Return source-bound facts and unresolved gaps.",
            max_turns=10,
        ),
    )


def _catalog_pair(profile):
    grants = []
    catalogs = {}
    for grant in profile.mcp_server_grants:
        rows = [
            {
                "name": name,
                "inputSchema": {"type": "object", "properties": {}},
            }
            for name in (*grant.enabled_tools, "ungranted_fixture_tool")
        ]
        selected = {
            row["name"]: row
            for row in rows
            if row["name"] in grant.enabled_tools
        }
        grants.append(
            dataclasses.replace(
                grant,
                tool_schema_digest=observed_mcp_tool_schema_digest(
                    {"tools": selected}
                ),
            )
        )
        catalogs[grant.config_name] = {"tools": rows}
    return (
        dataclasses.replace(profile, mcp_server_grants=tuple(grants)),
        catalogs,
    )


def test_empty_mcp_roster_compiles_cardless_read_only_agents(profile):
    source = dataclasses.replace(profile, mcp_server_grants=())
    projection = project_claude_native_helpers(
        source,
        helpers=_roster(),
        permission_mode="bypassPermissions",
        supports_subagent_capability_ceiling=ObservedTriState.VERIFIED,
    )
    args = projection.cli_arguments()
    assert args[:4] == (
        "--permission-mode",
        "bypassPermissions",
        "--allowedTools",
        "Agent",
    )
    assert args[-2] == "--agents"
    assert projection.environment() == {
        "CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS": "1",
        "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS": str(
            source.native_helper.max_concurrent_helpers
        ),
        "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": str(
            source.native_helper.max_depth
        ),
        "CLAUDE_CODE_SUBAGENT_MODEL_FORCE": "1",
    }
    agents = projection.agents()
    assert tuple(agents) == ("code-reader", "research-scout")
    for definition in agents.values():
        assert definition["model"] == "inherit"
        assert definition["permissionMode"] == "bypassPermissions"
        assert definition["background"] is False
        assert definition["omitClaudeMd"] is True
        assert set(definition["tools"]) == {"Glob", "Grep", "Read"}
        assert {
            "Agent",
            "Bash",
            "Edit",
            "Write",
            "WebFetch",
            "WebSearch",
        } <= set(definition["disallowedTools"])
        assert definition["mcpServers"] == []


def test_exact_mcp_grants_are_visible_and_ungranted_tools_are_denied(profile):
    source, catalogs = _catalog_pair(profile)
    projection = project_claude_native_helpers(
        source,
        helpers=_roster(),
        permission_mode="dontAsk",
        supports_subagent_capability_ceiling=ObservedTriState.VERIFIED,
        observed_tool_catalogs=catalogs,
    )
    expected = tuple(
        sorted(
            f"mcp__{grant.config_name}__{tool}"
            for grant in source.mcp_server_grants
            for tool in grant.enabled_tools
        )
    )
    expected_denied = tuple(
        sorted(
            f"mcp__{grant.config_name}__ungranted_fixture_tool"
            for grant in source.mcp_server_grants
        )
    )
    assert projection.auto_approved_tools == expected
    assert set(expected_denied) <= set(projection.denied_tools)
    for definition in projection.agents().values():
        assert set(expected) <= set(definition["tools"])
        assert set(expected_denied) <= set(definition["disallowedTools"])
        assert definition["mcpServers"]


def test_cli_payload_is_canonical_and_has_no_worker_or_placement_selector(profile):
    source = dataclasses.replace(profile, mcp_server_grants=())
    projection = project_claude_native_helpers(
        source,
        helpers=_roster(),
        permission_mode="dontAsk",
        supports_subagent_capability_ceiling=ObservedTriState.VERIFIED,
    )
    payload = projection.cli_arguments()[-1]
    assert payload == json.dumps(
        json.loads(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    for forbidden in (
        "worker_id",
        "provider_realm",
        "provider_account",
        "quota_class",
        "host_id",
        "model_router",
    ):
        assert forbidden not in payload


def test_projection_retains_source_identity_and_stays_production_inert(profile):
    source = dataclasses.replace(profile, mcp_server_grants=())
    projection = project_claude_native_helpers(
        source,
        helpers=_roster(),
        permission_mode="bypassPermissions",
        supports_subagent_capability_ceiling=ObservedTriState.VERIFIED,
    )
    assert projection.source_profile_id == source.profile_id
    assert projection.source_profile_digest == source.profile_digest
    assert (
        projection.source_native_helper_grant_digest
        == source.native_helper.grant_digest
    )
    assert (
        projection.source_native_helper_mechanism
        == source.native_helper.mechanism
    )
    assert projection.production_armed is False
    with pytest.raises((TypeError, ValueError), match="init=False"):
        dataclasses.replace(projection, production_armed=True)


def test_write_capable_native_helper_refuses_to_executive_child_boundary(profile):
    source = dataclasses.replace(
        profile,
        write_capable=True,
        mcp_server_grants=(),
    )
    with pytest.raises(
        ClaudeNativeHelperProjectionError,
        match="Executive child Job",
    ):
        project_claude_native_helpers(
            source,
            helpers=_roster(),
            permission_mode="bypassPermissions",
            supports_subagent_capability_ceiling=ObservedTriState.VERIFIED,
        supports_subagent_capability_ceiling=ObservedTriState.VERIFIED,
        )


def test_missing_native_helper_grant_refuses(profile):
    source = dataclasses.replace(
        profile,
        native_helper=None,
        mcp_server_grants=(),
    )
    with pytest.raises(
        ClaudeNativeHelperProjectionError,
        match="no native helper grant",
    ):
        project_claude_native_helpers(
            source,
            helpers=_roster(),
            permission_mode="bypassPermissions",
            supports_subagent_capability_ceiling=ObservedTriState.VERIFIED,
        supports_subagent_capability_ceiling=ObservedTriState.VERIFIED,
        )


def test_unverified_subagent_ceiling_refuses(profile):
    source = dataclasses.replace(profile, mcp_server_grants=())
    with pytest.raises(
        ClaudeNativeHelperProjectionError,
        match="not admitted",
    ):
        project_claude_native_helpers(
            source,
            helpers=_roster(),
            permission_mode="bypassPermissions",
            supports_subagent_capability_ceiling=ObservedTriState.UNKNOWN,
        )


def test_interactive_permission_mode_refuses(profile):
    source = dataclasses.replace(profile, mcp_server_grants=())
    with pytest.raises(
        ClaudeNativeHelperProjectionError,
        match="not unattended",
    ):
        project_claude_native_helpers(
            source,
            helpers=_roster(),
            permission_mode="default",
            supports_subagent_capability_ceiling=ObservedTriState.VERIFIED,
        )


def test_duplicate_or_nondeterministic_roster_refuses(profile):
    source = dataclasses.replace(profile, mcp_server_grants=())
    first, second = _roster()
    with pytest.raises(
        ClaudeNativeHelperProjectionError,
        match="canonically sorted",
    ):
        project_claude_native_helpers(
            source,
            helpers=(second, first),
            permission_mode="bypassPermissions",
            supports_subagent_capability_ceiling=ObservedTriState.VERIFIED,
        supports_subagent_capability_ceiling=ObservedTriState.VERIFIED,
        )
    with pytest.raises(
        ClaudeNativeHelperProjectionError,
        match="duplicated",
    ):
        project_claude_native_helpers(
            source,
            helpers=(first, first),
            permission_mode="bypassPermissions",
            supports_subagent_capability_ceiling=ObservedTriState.VERIFIED,
        supports_subagent_capability_ceiling=ObservedTriState.VERIFIED,
        )


def test_mcp_profile_requires_complete_observed_catalog(profile):
    with pytest.raises(
        ClaudeNativeHelperProjectionError,
        match="MCP projection is not closed",
    ):
        project_claude_native_helpers(
            profile,
            helpers=_roster(),
            permission_mode="bypassPermissions",
            supports_subagent_capability_ceiling=ObservedTriState.VERIFIED,
        supports_subagent_capability_ceiling=ObservedTriState.VERIFIED,
        )
