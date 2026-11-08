"""Profile qualification and transport proof; no installed authority or account."""
import dataclasses
import json
import os
from pathlib import Path
import shutil

import pytest

from control_plane.browser_resource_contract import (
    ALLOWED_BROWSER_TOOLS, APP_CONTROL_TOOLS, APP_CONTROL_TOOL_SCHEMA_DIGEST,
    WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST, browser_tools_for_digest, validate_app_control_origin,
)
from control_plane.executive_agent_capabilities import observed_mcp_tool_schema_digest
from integrations.workbench_action_mcp.service import parse_browser_service_config, ServiceConfigurationError
from integrations.workbench_browser_mcp.app import build_browser_tool_surface
from integrations.workbench_browser_mcp.contracts import BrowserRefCodec, BrowserContractError
from integrations.workbench_browser_mcp.relay import playwright_child_argv, McpStdioSession
from integrations.workbench_browser_mcp.resource_port import BrowserHostConfig, BrowserResourceRefused, validate_host_config

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "integrations/worker_browser_runtime"


def catalogue():
    native = json.loads((ROOT / "research/evidence/claude_browser_mcp_tools_0_0_79.json").read_text())["tools"]
    native = [row for row in native if row["name"] in ALLOWED_BROWSER_TOOLS]
    app = json.loads((ROOT / "app/mastermind_os/src/agent-control/tools.json").read_text())
    for row in app:
        row["annotations"] = {"readOnlyHint": row["annotations"]["readOnlyHint"]}
    return {"tools": native + app}


def test_profile_catalogue_digest_is_distinct_and_baseline_never_grows():
    rows = catalogue()["tools"]
    assert observed_mcp_tool_schema_digest({"tools": {row["name"]: row for row in rows}}) == APP_CONTROL_TOOL_SCHEMA_DIGEST
    assert observed_mcp_tool_schema_digest({"tools": {row["name"]: row for row in rows if row["name"] in ALLOWED_BROWSER_TOOLS}}) == WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST
    baseline = build_browser_tool_surface(catalogue())
    assert not any("mastermind_os_" in name for name in baseline.schemas)
    surface = build_browser_tool_surface(catalogue(), expected_tool_schema_digest=APP_CONTROL_TOOL_SCHEMA_DIGEST)
    assert {"mastermind_os_inspect", "mastermind_os_check", "prepare_mastermind_os_act", "prepare_mastermind_os_navigate"} <= surface.schemas.keys()
    assert "mastermind_os_act" not in surface.schemas
    assert "mastermind_os_navigate" not in surface.schemas
    assert not surface.validators["mastermind_os_check"].is_valid({"browser_ref": "a" * 32})
    assert surface.validators["mastermind_os_check"].is_valid({"browser_ref": "a" * 32, "route": "Projects"})
    for row in surface.tools:
        if row.name == "mastermind_os_inspect":
            assert row.annotations.idempotentHint is False
    changed = catalogue(); changed["tools"][-1]["inputSchema"]["minProperties"] = 0
    with pytest.raises(ValueError, match="schema drift"):
        build_browser_tool_surface(changed, expected_tool_schema_digest=APP_CONTROL_TOOL_SCHEMA_DIGEST)
    with pytest.raises(ValueError, match="not jointly qualified"):
        build_browser_tool_surface(catalogue(), expected_tool_schema_digest=APP_CONTROL_TOOL_SCHEMA_DIGEST, credentials_enabled=True)


def test_owner_selects_an_exact_origin_and_qualified_catalogue():
    source = {name: "/owned/" + name for name in ("source_root", "python_executable", "node_executable", "mcp_cli_path", "chrome_executable", "relay_root", "output_root", "home_dir", "tmp_dir", "tool_catalog_file")}
    source["startup_timeout_seconds"] = 10
    assert parse_browser_service_config(source).app_control_origin is None
    selected = {**source, "app_control": {"origin": "https://mcp.mastermind-x.com", "tool_schema_digest": APP_CONTROL_TOOL_SCHEMA_DIGEST}}
    config = parse_browser_service_config(selected)
    assert config.app_control_origin == "https://mcp.mastermind-x.com"
    assert config.app_control_tool_schema_digest == APP_CONTROL_TOOL_SCHEMA_DIGEST
    for bad in [{"origin": "https://mcp.mastermind-x.com", "tool_schema_digest": WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST}, {"origin": "http://remote.example", "tool_schema_digest": APP_CONTROL_TOOL_SCHEMA_DIGEST}, {"origin": "https://mcp.mastermind-x.com", "tool_schema_digest": APP_CONTROL_TOOL_SCHEMA_DIGEST, "script": "anything"}]:
        with pytest.raises(ServiceConfigurationError):
            parse_browser_service_config({**source, "app_control": bad})
    for invalid in ["https://example.com/", "https://user@example.com", "https://example.com?x=1", "https://example.com:443", "http://localhost:80", "https://example.com#x", "http://remote.example"]:
        with pytest.raises(ValueError): validate_app_control_origin(invalid)


def test_profile_origin_and_digest_must_be_paired_in_host_configuration(tmp_path):
    os.chmod(tmp_path, 0o700)
    config = BrowserHostConfig(source_root=tmp_path, python_executable="/owned/python", node_executable="/owned/node",
        mcp_cli_path=str(tmp_path / "integrations/worker_browser_runtime/node_modules/@playwright/mcp/cli.js"), chrome_executable="/owned/chrome", relay_root=tmp_path,
        output_root=tmp_path, home_dir="/owned/home", tmp_dir="/owned/tmp")
    with pytest.raises(BrowserResourceRefused, match="APP_CONTROL_PROFILE_NOT_QUALIFIED"):
        validate_host_config(dataclasses.replace(config, app_control_origin="https://mcp.mastermind-x.com"))
    with pytest.raises(BrowserResourceRefused, match="APP_CONTROL_ORIGIN_REQUIRED"):
        validate_host_config(dataclasses.replace(config, expected_tool_schema_digest=APP_CONTROL_TOOL_SCHEMA_DIGEST))
    validate_host_config(dataclasses.replace(config, app_control_origin="https://mcp.mastermind-x.com", expected_tool_schema_digest=APP_CONTROL_TOOL_SCHEMA_DIGEST))


def test_opted_in_child_is_fixed_and_preserves_original_browser_lease_options():
    args = dict(node_executable="/owned/node", mcp_cli_path="/owned/runtime/node_modules/@playwright/mcp/cli.js", chrome_executable="/owned/chrome", output_dir="/owned/output", mode="isolated", profile_dir=None)
    baseline = playwright_child_argv(**args)
    assert baseline[1] == args["mcp_cli_path"]
    selected = playwright_child_argv(**args, app_control_origin="https://mcp.mastermind-x.com")
    assert selected[1] == "/owned/runtime/app-control/child.cjs"
    assert selected[2:-2] == baseline[2:]
    assert selected[-2:] == ("--app-origin", "https://mcp.mastermind-x.com")
    assert BrowserRefCodec(b"k" * 32).allowed_tools == ALLOWED_BROWSER_TOOLS
    assert BrowserRefCodec(b"k" * 32, allowed_tools=browser_tools_for_digest(APP_CONTROL_TOOL_SCHEMA_DIGEST)).allowed_tools == ALLOWED_BROWSER_TOOLS | APP_CONTROL_TOOLS


@pytest.mark.skipif(not (RUNTIME / "app-control/node_modules/@modelcontextprotocol/sdk/package.json").is_file() or shutil.which("node") is None,
                    reason="Install the pinned browser runtime for actual stdio catalogue qualification")
def test_actual_stdio_child_qualifies_its_catalogue_without_launching_browser(tmp_path):
    argv = playwright_child_argv(node_executable=shutil.which("node"), mcp_cli_path=str(RUNTIME / "node_modules/@playwright/mcp/cli.js"),
        chrome_executable="/unavailable/source-proof-chrome", output_dir=str(tmp_path), mode="isolated", profile_dir=None,
        app_control_origin="https://mcp.mastermind-x.com")
    session = McpStdioSession(argv=argv, env={"PATH": os.environ["PATH"], "HOME": str(tmp_path)},
        allowed_tools=browser_tools_for_digest(APP_CONTROL_TOOL_SCHEMA_DIGEST), expected_tool_schema_digest=APP_CONTROL_TOOL_SCHEMA_DIGEST)
    try:
        assert session.start().tool_schema_digest == APP_CONTROL_TOOL_SCHEMA_DIGEST
        assert session.call("mastermind_os_inspect", {})["structuredContent"]["code"] == "BROWSER_RESOURCE_UNAVAILABLE"
    finally:
        session.close()
