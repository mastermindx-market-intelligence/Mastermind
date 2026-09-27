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
    CapabilityPolicyError,
    ExecutionCapabilityRegistry,
    observed_mcp_tool_schema_digest,
)
from control_plane.operator_harness_contract import ObservedTriState


@pytest.fixture
def profile():
    registry = ExecutionCapabilityRegistry.load(
        Path(
            "tests/fixtures/"
            "executive_agent_capabilities_claude_native_helper_v3.json"
        ),
        source_root=Path.cwd(),
    )
    return registry.resolve("operator.claude.readonly.native-helper.v1")


def test_profile_is_claude_specific(profile):
    assert profile.execution_surface == "claude-code"
    assert profile.native_helper is not None
    assert profile.native_helper.mechanism == "claude-code-agent-inherit-parent"
    assert profile.native_helper.default_model == "inherit-parent"
    assert profile.native_helper.default_reasoning_effort == "inherit"


def test_codex_native_helper_grant_is_refused():
    registry = ExecutionCapabilityRegistry.load(
        Path("config/executive_agent_capabilities.json"),
        source_root=Path.cwd(),
    )
    codex_profile = registry.resolve(
        "operator.appserver.readonly.docs-mcp.native-helper.v1"
    )
    with pytest.raises(
        ClaudeNativeHelperProjectionError,
        match="claude-code execution profile",
    ):
        project_claude_native_helpers(
            codex_profile,
            helpers=_roster(),
            permission_mode="dontAsk",
            execution_mode="noninteractive",
            supports_subagent_capability_ceiling=ObservedTriState.VERIFIED,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("execution_surface", "codex-app-server", "requires claude-code execution surface"),
        ("default_model", "sonnet", "inherit the admitted parent model"),
        (
            "default_reasoning_effort",
            "medium",
            "inherit the admitted parent reasoning effort",
        ),
    ),
)
def test_registry_refuses_drifted_claude_helper_identity(
    tmp_path, field, value, message
):
    source = Path(
        "tests/fixtures/executive_agent_capabilities_claude_native_helper_v3.json"
    )
    raw = json.loads(source.read_text(encoding="utf-8"))
    profile = raw["profiles"]["operator.claude.readonly.native-helper.v1"]
    if field == "execution_surface":
        profile[field] = value
    else:
        profile["native_helper"][field] = value
    candidate = tmp_path / "capabilities.json"
    candidate.write_text(
        json.dumps(raw, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    with pytest.raises(CapabilityPolicyError, match=message):
        ExecutionCapabilityRegistry.load(candidate, source_root=Path.cwd())


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
        execution_mode="noninteractive",
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
    denied_index = args.index("--disallowedTools")
    assert set(args[denied_index + 1 : -2]) >= {
        "SendMessage",
        "ListAgents",
        "TaskCreate",
        "TaskUpdate",
    }
    assert projection.execution_mode == "noninteractive"
    assert projection.runtime_ceiling_seconds == source.native_helper.max_runtime_seconds
    assert projection.external_runtime_enforcement_required is True
    assert projection.environment() == {
        "CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS": "1",
        "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",
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
        execution_mode="noninteractive",
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
        execution_mode="noninteractive",
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
        execution_mode="noninteractive",
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
            execution_mode="noninteractive",
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
            execution_mode="noninteractive",
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
            execution_mode="noninteractive",
            supports_subagent_capability_ceiling=ObservedTriState.UNKNOWN,
        )


def test_interactive_parent_session_refuses(profile):
    source = dataclasses.replace(profile, mcp_server_grants=())
    with pytest.raises(
        ClaudeNativeHelperProjectionError,
        match="noninteractive parent session",
    ):
        project_claude_native_helpers(
            source,
            helpers=_roster(),
            permission_mode="bypassPermissions",
            execution_mode="interactive",
            supports_subagent_capability_ceiling=ObservedTriState.VERIFIED,
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
            execution_mode="noninteractive",
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
            execution_mode="noninteractive",
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
            execution_mode="noninteractive",
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
            execution_mode="noninteractive",
            supports_subagent_capability_ceiling=ObservedTriState.VERIFIED,
        )
