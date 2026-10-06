from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from integrations.mastermind_browser_plugin.playwright_extension import (
    EXTENSION_ID,
    EXPECTED_MCP_VERSION,
    EXPECTED_TOOL_SCHEMA_DIGEST,
    ExtensionBrokerPlan,
    ExtensionModeError,
    attest_extension_catalog,
    build_extension_broker_plan,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "research" / "evidence" / "claude_browser_mcp_tools_0_0_79.json"


def plan(**changes):
    values = dict(
        node_executable="/opt/homebrew/bin/node",
        mcp_cli_path="/opt/mmx/runtime/node_modules/@playwright/mcp/cli.js",
        output_dir="/private/var/tmp/mastermind-browser-output",
        installed_mcp_version=EXPECTED_MCP_VERSION,
    )
    values.update(changes)
    return build_extension_broker_plan(**values)


def test_extension_plan_reuses_exact_reviewed_playwright_schema():
    value = plan()
    assert isinstance(value, ExtensionBrokerPlan)
    assert value.mcp_version == "0.0.79"
    assert value.expected_tool_schema_digest == EXPECTED_TOOL_SCHEMA_DIGEST
    assert value.extension_id == EXTENSION_ID
    assert value.requires_user_approval is True
    assert value.one_broker_connection_per_profile is True
    assert value.is_admission is False
    assert value.is_installation is False


def test_initial_extension_plan_is_manual_approval_and_contains_no_profile_token():
    value = plan()
    rendered = json.dumps(value.to_dict(), sort_keys=True)
    assert value.argv == (
        "/opt/mmx/runtime/node_modules/@playwright/mcp/cli.js",
        "--browser",
        "chrome",
        "--extension",
        "--output-dir",
        "/private/var/tmp/mastermind-browser-output",
    )
    for forbidden in (
        "PLAYWRIGHT_MCP_EXTENSION_TOKEN",
        "--profile-dir-name",
        "--cdp-endpoint",
        "--shared-browser-context",
        "--user-data-dir",
        "--secrets",
        "access_token",
        "client_secret",
        "cookie",
        "password",
    ):
        assert forbidden not in rendered


def test_extension_plan_has_no_model_selectable_profile_tab_or_caller_channel():
    names = set(ExtensionBrokerPlan.__dataclass_fields__)
    for forbidden in {
        "profile_ref",
        "tab_ref",
        "tab_id",
        "subject_digest",
        "client_ref",
        "actor",
        "extension_token",
        "oauth_token",
        "cookie",
    }:
        assert forbidden not in names


@pytest.mark.parametrize(
    "field,value",
    [
        ("node_executable", "node"),
        ("node_executable", "/tmp/../node"),
        ("mcp_cli_path", "/tmp/cli.js"),
        ("mcp_cli_path", "/tmp/node_modules/@playwright/mcp/other.js"),
        ("output_dir", "relative"),
        ("output_dir", "/tmp/../output"),
        ("installed_mcp_version", "0.0.80"),
        ("installed_mcp_version", True),
    ],
)
def test_extension_plan_refuses_unreviewed_runtime_or_paths(field, value):
    with pytest.raises(ExtensionModeError):
        plan(**{field: value})


def test_exact_pinned_fixture_catalog_attests():
    catalog = json.loads(FIXTURE.read_text(encoding="utf-8"))
    receipt = attest_extension_catalog(catalog)
    assert receipt.tool_schema_digest == EXPECTED_TOOL_SCHEMA_DIGEST
    assert set(receipt.allowed_tools) == {
        "browser_click",
        "browser_close",
        "browser_console_messages",
        "browser_fill_form",
        "browser_hover",
        "browser_navigate",
        "browser_network_requests",
        "browser_press_key",
        "browser_select_option",
        "browser_snapshot",
        "browser_tabs",
        "browser_take_screenshot",
        "browser_type",
        "browser_wait_for",
    }
    assert receipt.is_admission is False


def test_catalog_schema_drift_or_missing_tool_refuses():
    catalog = json.loads(FIXTURE.read_text(encoding="utf-8"))
    changed = copy.deepcopy(catalog)
    selected = next(tool for tool in changed["tools"] if tool["name"] == "browser_snapshot")
    selected["inputSchema"]["properties"]["injected"] = {"type": "string"}
    with pytest.raises(ExtensionModeError, match="schema"):
        attest_extension_catalog(changed)

    missing = copy.deepcopy(catalog)
    missing["tools"] = [
        tool for tool in missing["tools"] if tool["name"] != "browser_click"
    ]
    with pytest.raises(ExtensionModeError, match="catalog"):
        attest_extension_catalog(missing)


def test_extension_identity_is_the_official_playwright_web_store_extension():
    assert EXTENSION_ID == "mmlmfjhmonkocbjadbfplnigmagldckm"
