from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys

import mcp.types as mcp_types

from integrations.workbench_action_mcp.tunnel import create_runtime_channel
from integrations.workbench_browser_mcp.app import build_browser_tool_surface
from integrations.workbench_browser_mcp.tunnel import (
    BROWSER_TUNNEL_SCHEMA,
    BrowserTunnelConfigurationError,
    create_browser_tunnel_server,
    load_browser_tunnel_config,
)
from tests.workbench_action_mcp.test_tunnel import _document


def _private(path: Path) -> str:
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return str(path)


def _browser_block(tmp_path: Path) -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    return {
        "source_root": str(root),
        "python_executable": sys.executable,
        "node_executable": "/opt/homebrew/bin/node",
        "mcp_cli_path": "/tmp/mcp/node_modules/@playwright/mcp/cli.js",
        "chrome_executable": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "relay_root": _private(tmp_path / "relay"),
        "output_root": _private(tmp_path / "output"),
        "home_dir": _private(tmp_path / "home"),
        "tmp_dir": _private(tmp_path / "tmp"),
        "tool_catalog_file": str(
            root
            / "research"
            / "evidence"
            / "claude_browser_mcp_tools_0_0_79.json"
        ),
        "startup_timeout_seconds": 5.0,
    }


def _config_file(tmp_path: Path):
    action_doc, _project, audit, _key = _document(tmp_path, tag="browser")
    action_path = tmp_path / "action-tunnel.json"
    action_path.write_text(json.dumps(action_doc), encoding="ascii")
    os.chmod(action_path, 0o600)
    outer = {
        "schema": BROWSER_TUNNEL_SCHEMA,
        "action_tunnel_config": str(action_path),
        "browser": _browser_block(tmp_path),
    }
    path = tmp_path / "browser-tunnel.json"
    path.write_text(json.dumps(outer), encoding="ascii")
    os.chmod(path, 0o600)
    return path, outer, audit


async def _tools(server):
    handler = server.request_handlers[mcp_types.ListToolsRequest]
    response = await handler(None)
    return response.root.tools


async def _call(server, name: str, arguments: dict | None):
    handler = server.request_handlers[mcp_types.CallToolRequest]
    response = await handler(
        mcp_types.CallToolRequest(
            params=mcp_types.CallToolRequestParams(
                name=name,
                arguments=arguments,
            )
        )
    )
    return response.root


def _error_code(result) -> str:
    assert result.isError is True
    return json.loads(result.content[0].text)["code"]


def test_browser_tunnel_config_composes_existing_action_tunnel(tmp_path: Path):
    path, outer, _audit = _config_file(tmp_path)
    selected = load_browser_tunnel_config(str(path))
    assert selected.schema == BROWSER_TUNNEL_SCHEMA
    assert selected.action_config_path == outer["action_tunnel_config"]
    assert selected.action.lease == load_browser_tunnel_config(str(path)).action.lease
    assert selected.browser.tool_catalog_file.endswith(
        "claude_browser_mcp_tools_0_0_79.json"
    )


def test_browser_tunnel_config_refuses_extra_authority_field(tmp_path: Path):
    path, outer, _audit = _config_file(tmp_path)
    outer["host_override"] = "mini2"
    path.write_text(json.dumps(outer), encoding="ascii")
    os.chmod(path, 0o600)
    try:
        load_browser_tunnel_config(str(path))
    except BrowserTunnelConfigurationError:
        pass
    else:
        raise AssertionError("browser tunnel accepted caller-selected host override")


def test_browser_tunnel_tool_surface_is_identical_to_web_surface(tmp_path: Path):
    path, _outer, _audit = _config_file(tmp_path)
    selected = load_browser_tunnel_config(str(path))

    async def exercise():
        runtime = await create_runtime_channel(selected.action)
        try:
            server = create_browser_tunnel_server(runtime, selected.browser)
            observed = await _tools(server)
            catalog = json.loads(
                Path(selected.browser.tool_catalog_file).read_text(encoding="utf-8")
            )
            expected = build_browser_tool_surface(catalog).tools
            assert [tool.model_dump(mode="json") for tool in observed] == [
                tool.model_dump(mode="json") for tool in expected
            ]
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5.0)

    asyncio.run(exercise())


def test_revoked_channel_refuses_before_browser_port_dispatch(tmp_path: Path):
    path, _outer, audit = _config_file(tmp_path)
    selected = load_browser_tunnel_config(str(path))

    async def exercise():
        runtime = await create_runtime_channel(selected.action)
        server = create_browser_tunnel_server(runtime, selected.browser)
        runtime.revoke()
        result = await _call(
            server,
            "prepare_browser_resource",
            {
                "project_ref": selected.action.lease.project_ref,
                "mode": "isolated",
            },
        )
        assert _error_code(result) == "CHANNEL_ADMISSION_REFUSED"
        await runtime.aclose(timeout=5.0)

    asyncio.run(exercise())
    rows = [
        json.loads(line)
        for line in (audit / "auth-audit.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[-1]["accepted"] is False
    assert rows[-1]["code"] == "channel_refused"


def test_prepare_resource_uses_fixed_channel_project_and_starts_no_process(tmp_path: Path):
    path, _outer, audit = _config_file(tmp_path)
    selected = load_browser_tunnel_config(str(path))

    async def exercise():
        runtime = await create_runtime_channel(selected.action)
        try:
            server = create_browser_tunnel_server(runtime, selected.browser)
            result = await _call(
                server,
                "prepare_browser_resource",
                {
                    "project_ref": selected.action.lease.project_ref,
                    "mode": "isolated",
                },
            )
            assert result.isError is False
            payload = result.structuredContent
            assert payload["status"] == "PREPARED"
            assert isinstance(payload["start_ref"], str)
            assert list(Path(selected.action.artifact_directory).iterdir()) == []
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5.0)

    asyncio.run(exercise())
    rows = [
        json.loads(line)
        for line in (audit / "auth-audit.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[-1]["accepted"] is True
    assert rows[-1]["tool"] == "prepare_browser_resource"


def test_native_stdio_child_lists_exact_browser_surface(tmp_path: Path):
    from tests.test_mcp_stdio_boundary import child, initialize

    path, _outer, _audit = _config_file(tmp_path)
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "mastermind_workbench_browser_stdio.py"
    )
    catalog = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "research"
            / "evidence"
            / "claude_browser_mcp_tools_0_0_79.json"
        ).read_text(encoding="utf-8")
    )
    expected = {
        tool.name for tool in build_browser_tool_surface(catalog).tools
    }
    with child([sys.executable, str(script), "--config", str(path)]) as process:
        initialize(process)
        process.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        observed = {
            tool["name"] for tool in process.receive()["result"]["tools"]
        }
        assert observed == expected
        process.assert_exit(0)


def test_browser_stdio_describe_is_dependency_free_and_inert():
    import subprocess

    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "mastermind_workbench_browser_stdio.py"
    )
    completed = subprocess.run(
        [sys.executable, "-I", str(script), "--describe"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert completed.returncode == 0
    value = json.loads(completed.stdout)
    assert value["mode"] == "fixed-channel-stdio"
    assert value["installed"] is False
    assert value["persistent_profiles"] is False
