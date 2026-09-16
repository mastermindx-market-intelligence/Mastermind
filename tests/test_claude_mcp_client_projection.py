from __future__ import annotations

import dataclasses
import importlib
import importlib.util
import json
from pathlib import Path

import pytest

from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from control_plane.operator_harness_contract import NativeHelperPolicy

MODULE = "control_plane.claude_mcp_client_projection"


def test_client_projection_exists():
    assert importlib.util.find_spec(MODULE) is not None, "Claude MCP client projection is missing"


@pytest.fixture
def api():
    if importlib.util.find_spec(MODULE) is None:
        pytest.skip("implementation intentionally absent for RED")
    return importlib.import_module(MODULE)


@pytest.fixture
def profile():
    registry = ExecutionCapabilityRegistry.load(
        Path("scripts/ohf/fixtures/executive_agent_capabilities_v4_mastermind_operator.json"),
        source_root=Path.cwd(),
    )
    return registry.resolve("operator.browser.local-review.v1")


def browser_only(profile):
    return dataclasses.replace(profile, mcp_server_grants=tuple(
        g for g in profile.mcp_server_grants if g.transport == "stdio"))


def test_cli_preserves_all_grants_and_exact_bootstrap(api, profile):
    projection = api.project_claude_mcp_client(profile, surface="cli")
    config = projection.configuration()["mcpServers"]
    assert set(config) == {g.config_name for g in profile.mcp_server_grants}
    for g in profile.mcp_server_grants:
        if g.transport == "stdio":
            assert config[g.config_name] == {"type": "stdio", "command": g.command, "args": list(g.args)}
        else:
            assert config[g.config_name] == {"type": "http", "url": g.url}
    args = projection.cli_arguments()
    assert args[:2] == ("--strict-mcp-config", "--mcp-config")
    assert json.loads(args[2]) == projection.configuration()
    assert "--chrome" not in args and "--dangerously-skip-permissions" not in args


def test_exact_tools_and_source_identity(api, profile):
    p = api.project_claude_mcp_client(profile, surface="cli")
    expected = tuple(sorted(f"mcp__{g.config_name}__{t}" for g in profile.mcp_server_grants for t in g.enabled_tools))
    assert p.enabled_tools == expected
    assert p.auto_approved_tools == expected
    assert all("*" not in x for x in p.enabled_tools)
    assert p.source_profile_digest == profile.profile_digest
    assert p.source_grant_digests == tuple(sorted(g.grant_digest for g in profile.mcp_server_grants))
    assert p.source_tool_schema_digests == tuple(sorted(g.tool_schema_digest for g in profile.mcp_server_grants))
    assert p.production_armed is False


def test_sdk_keys_and_precise_permissions(api, profile):
    p = api.project_claude_mcp_client(profile, surface="agent-sdk")
    c = p.configuration()
    assert set(c) == {"mcp_servers", "allowed_tools", "strict_mcp_config"}
    assert c["allowed_tools"] == list(p.auto_approved_tools)
    assert set(c["mcp_servers"]) == {g.config_name for g in profile.mcp_server_grants}


def test_desktop_local_stdio_shape(api, profile):
    p = api.project_claude_mcp_client(browser_only(profile), surface="desktop-local")
    entry = next(iter(p.configuration()["mcpServers"].values()))
    assert set(entry) == {"command", "args"}
    assert "env" not in entry


def test_desktop_refuses_remote_not_silently_drops_required_grant(api, profile):
    with pytest.raises(api.ClaudeMcpProjectionError, match="local bridge"):
        api.project_claude_mcp_client(profile, surface="desktop-local")


@pytest.mark.parametrize("surface", ["plugin-subagent", "remote-connector", "unknown", "", None])
def test_unsupported_surface_refused(api, profile, surface):
    with pytest.raises(api.ClaudeMcpProjectionError):
        api.project_claude_mcp_client(profile, surface=surface)


def test_inline_helper_disabled_refused(api, profile):
    with pytest.raises(api.ClaudeMcpProjectionError, match="helper"):
        api.project_claude_mcp_client(profile, surface="inline-subagent")


def test_inline_uses_definitions_not_shared_parent_references(api, profile):
    profile, catalogs = catalog_pair(profile)
    p = api.project_claude_mcp_client(profile, surface="inline-subagent", observed_tool_catalogs=catalogs)
    c = p.configuration()
    assert all(isinstance(x, dict) for x in c["mcpServers"])
    assert c["tools"] == list(p.enabled_tools)
    assert "permissionMode" not in c


def test_disabled_profile_refused(api, profile):
    with pytest.raises(api.ClaudeMcpProjectionError):
        api.project_claude_mcp_client(dataclasses.replace(profile, enabled=False), surface="cli")


@pytest.mark.parametrize("name", ["a__b", "a*", "-server", "token=secret", "a b"])
def test_ambiguous_server_name_refused(api, profile, name):
    g = dataclasses.replace(profile.mcp_server_grants[0], config_name=name)
    with pytest.raises(api.ClaudeMcpProjectionError):
        api.project_claude_mcp_client(dataclasses.replace(profile, mcp_server_grants=(g,)), surface="cli")


def test_duplicate_server_names_refused(api, profile):
    a, b = profile.mcp_server_grants
    b = dataclasses.replace(b, config_name=a.config_name)
    with pytest.raises(api.ClaudeMcpProjectionError):
        api.project_claude_mcp_client(dataclasses.replace(profile, mcp_server_grants=(a,b)), surface="cli")


@pytest.mark.parametrize("transport", ["sse", "ws", "shell", "http", "unknown"])
def test_unreviewed_transport_refused(api, profile, transport):
    g = dataclasses.replace(profile.mcp_server_grants[0], transport=transport)
    with pytest.raises(api.ClaudeMcpProjectionError):
        api.project_claude_mcp_client(dataclasses.replace(profile, mcp_server_grants=(g,)), surface="cli")


def test_mutating_return_does_not_mutate_projection_or_grant(api, profile):
    p = api.project_claude_mcp_client(profile, surface="cli")
    first = p.configuration()
    first["mcpServers"].clear()
    assert p.configuration()["mcpServers"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.surface = "other"


def test_non_cli_does_not_emit_cli_arguments(api, profile):
    p = api.project_claude_mcp_client(profile, surface="agent-sdk")
    with pytest.raises(api.ClaudeMcpProjectionError):
        p.cli_arguments()


def test_unknown_approval_mode_refused(api, profile):
    g = dataclasses.replace(profile.mcp_server_grants[0], default_tools_approval_mode="bypass")
    with pytest.raises(api.ClaudeMcpProjectionError):
        api.project_claude_mcp_client(dataclasses.replace(profile, mcp_server_grants=(g,)), surface="cli")


def test_empty_profile_is_explicitly_empty(api, profile):
    p = api.project_claude_mcp_client(dataclasses.replace(profile, mcp_server_grants=()), surface="cli")
    assert p.configuration() == {"mcpServers": {}}
    assert p.auto_approved_tools == ()
    assert p.cli_arguments() == ("--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}')


def test_projection_cannot_be_relabelled_as_production_armed(api, profile):
    projection = api.project_claude_mcp_client(profile, surface="cli")
    with pytest.raises((TypeError, ValueError), match="init=False"):
        dataclasses.replace(projection, production_armed=True)


def test_prompt_tools_remain_available_but_not_auto_approved(api, profile):
    grant = dataclasses.replace(profile.mcp_server_grants[0], default_tools_approval_mode="prompt")
    candidate = dataclasses.replace(profile, mcp_server_grants=(grant,))
    projection = api.project_claude_mcp_client(candidate, surface="agent-sdk")
    assert projection.enabled_tools
    assert projection.auto_approved_tools == ()
    assert projection.configuration()["allowed_tools"] == []


def test_sdk_ignores_ambient_mcp_servers(api, profile):
    projection = api.project_claude_mcp_client(profile, surface="agent-sdk")
    config = projection.configuration()
    assert config.get("strict_mcp_config") is True


def test_sdk_strict_mode_also_applies_to_empty_grants(api, profile):
    empty = dataclasses.replace(profile, mcp_server_grants=())
    config = api.project_claude_mcp_client(empty, surface="agent-sdk").configuration()
    assert config["mcp_servers"] == {}
    assert config.get("strict_mcp_config") is True


def catalog_pair(profile):
    from control_plane.executive_agent_capabilities import observed_mcp_tool_schema_digest
    grants, catalogs = [], {}
    for grant in profile.mcp_server_grants:
        rows = [{"name": name, "inputSchema": {"type": "object", "properties": {}}}
                for name in (*grant.enabled_tools, "ungranted_fixture_tool")]
        selected = {row["name"]: row for row in rows if row["name"] in grant.enabled_tools}
        grants.append(dataclasses.replace(grant, tool_schema_digest=observed_mcp_tool_schema_digest({"tools": selected})))
        catalogs[grant.config_name] = {"tools": rows}
    return dataclasses.replace(profile, mcp_server_grants=tuple(grants),
                               native_helper_policy=NativeHelperPolicy.PARENT_READ_ONLY_CEILING), catalogs


def test_inline_requires_a_complete_observed_catalog(api, profile):
    profile = dataclasses.replace(profile, native_helper_policy=NativeHelperPolicy.PARENT_READ_ONLY_CEILING)
    with pytest.raises(api.ClaudeMcpProjectionError, match="catalog"):
        api.project_claude_mcp_client(profile, surface="inline-subagent")


def test_inline_compiles_exact_ungranted_tool_denials(api, profile):
    profile, catalogs = catalog_pair(profile)
    p = api.project_claude_mcp_client(profile, surface="inline-subagent", observed_tool_catalogs=catalogs)
    expected = sorted(f"mcp__{g.config_name}__ungranted_fixture_tool" for g in profile.mcp_server_grants)
    assert p.configuration()["disallowedTools"] == expected
    assert list(p.denied_tools) == expected
    assert len(p.source_tool_catalog_digests) == len(profile.mcp_server_grants)
    assert not set(p.enabled_tools) & set(p.denied_tools)


@pytest.mark.parametrize("damage", ["schema", "pagination", "duplicate", "missing", "extra-server", "missing-server", "name-alias"])
def test_catalog_drift_and_incomplete_inventory_fail_closed(api, profile, damage):
    profile, catalogs = catalog_pair(profile)
    name = profile.mcp_server_grants[0].config_name
    rows = catalogs[name]["tools"]
    if damage == "schema": rows[0]["inputSchema"] = {"type": "string"}
    elif damage == "pagination": catalogs[name]["nextCursor"] = "another-page"
    elif damage == "duplicate": rows.append(dict(rows[0]))
    elif damage == "missing": rows.pop(0)
    elif damage == "extra-server": catalogs["unexpected"] = {"tools": rows}
    elif damage == "missing-server": del catalogs[name]
    elif damage == "name-alias": rows[0]["name"] = "alias__unsafe"
    with pytest.raises(api.ClaudeMcpProjectionError):
        api.project_claude_mcp_client(profile, surface="inline-subagent", observed_tool_catalogs=catalogs)


def test_cli_and_sdk_use_catalog_denials_without_new_permissions(api, profile):
    profile, catalogs = catalog_pair(profile)
    cli = api.project_claude_mcp_client(profile, surface="cli", observed_tool_catalogs=catalogs)
    assert "--disallowedTools" in cli.cli_arguments()
    for name in cli.denied_tools: assert name in cli.cli_arguments()
    sdk = api.project_claude_mcp_client(profile, surface="agent-sdk", observed_tool_catalogs=catalogs)
    assert sdk.configuration()["disallowed_tools"] == list(sdk.denied_tools)
    assert sdk.configuration()["strict_mcp_config"] is True


def twin_catalog_fixture(profile):
    import copy
    profile, catalogs = catalog_pair(profile)
    first = profile.mcp_server_grants[0]
    second = dataclasses.replace(first, config_name="catalogTwin")
    left = copy.deepcopy(catalogs[first.config_name])
    right = copy.deepcopy(left)
    left["tools"][-1]["inputSchema"] = {"type": "string"}
    right["tools"][-1]["inputSchema"] = {"type": "integer"}
    return dataclasses.replace(profile, mcp_server_grants=(first, second)), {
        first.config_name: left, second.config_name: right,
    }


def test_catalog_identity_changes_when_server_catalogs_are_swapped(api, profile):
    profile, catalogs = twin_catalog_fixture(profile)
    first, second = (g.config_name for g in profile.mcp_server_grants)
    before = api.project_claude_mcp_client(profile, surface="inline-subagent", observed_tool_catalogs=catalogs)
    swapped = {first: catalogs[second], second: catalogs[first]}
    after = api.project_claude_mcp_client(profile, surface="inline-subagent", observed_tool_catalogs=swapped)
    assert before.configuration() == after.configuration()
    assert before.denied_tools == after.denied_tools
    assert before.source_tool_catalog_digests != after.source_tool_catalog_digests


@pytest.mark.parametrize("surface", ["cli", "agent-sdk", "inline-subagent"])
def test_catalog_fingerprints_retain_server_names(api, profile, surface):
    from control_plane.executive_agent_capabilities import observed_mcp_tool_schema_digest
    profile, catalogs = twin_catalog_fixture(profile)
    projection = api.project_claude_mcp_client(profile, surface=surface, observed_tool_catalogs=catalogs)
    expected = tuple(sorted((name, observed_mcp_tool_schema_digest({
        "tools": {row["name"]: row for row in catalog["tools"]},
    })) for name, catalog in catalogs.items()))
    assert projection.source_tool_catalog_digests == expected


def test_catalog_identity_ignores_input_order_not_server_assignment(api, profile):
    profile, catalogs = twin_catalog_fixture(profile)
    before = api.project_claude_mcp_client(profile, surface="inline-subagent", observed_tool_catalogs=catalogs)
    reordered = {name: {"tools": list(reversed(catalog["tools"]))}
                 for name, catalog in reversed(tuple(catalogs.items()))}
    reverse_profile = dataclasses.replace(profile, mcp_server_grants=tuple(reversed(profile.mcp_server_grants)))
    after = api.project_claude_mcp_client(reverse_profile, surface="inline-subagent", observed_tool_catalogs=reordered)
    assert before == after
