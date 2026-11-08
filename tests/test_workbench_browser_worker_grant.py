"""The worker transport must enforce grants, not just advertise a smaller list."""
from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path

import pytest

from control_plane.executive_agent_capabilities import (
    McpServerGrant, observed_mcp_tool_schema_digest,
)
from integrations.workbench_action_mcp.tunnel import create_runtime_channel
from integrations.workbench_browser_mcp.app import build_browser_tool_surface
from integrations.workbench_browser_mcp.tunnel import (
    create_browser_tunnel_server, load_browser_tunnel_config,
)
from tests.test_workbench_browser_tunnel import _call, _config_file, _error_code, _tools


def _grant(config, names=("prepare_browser_resource",)):
    catalog = json.loads(Path(config.browser.tool_catalog_file).read_text())
    tools = {t.name: t.model_dump(mode="json")
             for t in build_browser_tool_surface(catalog).tools if t.name in names}
    return McpServerGrant(
        capability_id="worker-browser-isolated", config_name="worker_browser",
        transport="stdio", url=None, command="/reviewed/browser-owner",
        args=(), required=True, auth_status="unsupported",
        server_identity="Mastermind Workbench Browser Tunnel", server_version="0.1.0",
        enabled_tools=names, default_tools_approval_mode="approve",
        tool_schema_digest=observed_mcp_tool_schema_digest({"tools": tools}),
        grant_digest="a" * 64,
    )


def test_worker_catalog_and_dispatch_both_enforce_exact_grant(tmp_path):
    path, _, _ = _config_file(tmp_path)
    config = load_browser_tunnel_config(str(path))

    async def exercise():
        runtime = await create_runtime_channel(config.action)
        try:
            server = create_browser_tunnel_server(
                runtime, config.browser, mcp_grant=_grant(config))
            assert [t.name for t in await _tools(server)] == ["prepare_browser_resource"]
            refused = await _call(server, "start_browser_resource", {"start_ref": "opaque"})
            assert _error_code(refused) == "TOOL_NOT_AVAILABLE"
            prepared = await _call(server, "prepare_browser_resource", {
                "project_ref": config.action.lease.project_ref, "mode": "isolated"})
            assert prepared.structuredContent["status"] == "PREPARED"
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5)
    asyncio.run(exercise())


@pytest.mark.parametrize("changes", [
    {"tool_schema_digest": "0" * 64},
    {"enabled_tools": ("browser_evaluate",)},
    {"enabled_tools": ()},
    {"enabled_tools": ("prepare_browser_resource", "prepare_browser_resource")},
    {"transport": "streamable-http", "url": "https://example.invalid/browser"},
    {"server_identity": "other-server"},
    {"server_version": "unreviewed"},
])
def test_invalid_worker_grant_refuses_before_runtime_use(tmp_path, changes):
    path, _, _ = _config_file(tmp_path)
    config = load_browser_tunnel_config(str(path))

    async def exercise():
        runtime = await create_runtime_channel(config.action)
        try:
            with pytest.raises(ValueError, match="BROWSER_WORKER_GRANT_REFUSED"):
                create_browser_tunnel_server(runtime, config.browser,
                    mcp_grant=dataclasses.replace(_grant(config), **changes))
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5)
    asyncio.run(exercise())


def test_worker_binding_revocation_reaches_the_resource_port(tmp_path):
    path, _, _ = _config_file(tmp_path)
    config = load_browser_tunnel_config(str(path))

    async def exercise():
        runtime = await create_runtime_channel(config.action)
        active = True
        def owner_binding(caller, project):
            return runtime.resolve_binding(caller, project) if active else None
        try:
            server = create_browser_tunnel_server(runtime, config.browser,
                mcp_grant=_grant(config), resolve_binding=owner_binding)
            active = False
            result = await _call(server, "prepare_browser_resource", {
                "project_ref": config.action.lease.project_ref, "mode": "isolated"})
            assert _error_code(result) == "CHANNEL_ADMISSION_REFUSED"
            assert list(Path(config.action.artifact_directory).iterdir()) == []
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5)
    asyncio.run(exercise())


def test_generic_run_cannot_launder_a_tool_outside_the_grant(tmp_path):
    from integrations.workbench_browser_mcp.contracts import BrowserRefCodec
    from tests.test_workbench_browser_contracts import _action
    path, _, audit = _config_file(tmp_path)
    config = load_browser_tunnel_config(str(path))
    async def exercise():
        runtime = await create_runtime_channel(config.action)
        try:
            server = create_browser_tunnel_server(runtime, config.browser,
                mcp_grant=_grant(config, ("run_browser_action",)))
            services = runtime.channel_services
            now = services.clock_ms()
            token = BrowserRefCodec(services.action_token_key).encode_action(
                _action("signed-browser-resource", issued_at_ms=now, expires_at_ms=now+1000))
            result = await _call(server, "run_browser_action", {"action_ref": token, "browser_ref": "signed-browser-resource"})
            assert _error_code(result) == "BROWSER_TOOL_NOT_GRANTED"
            assert list(Path(config.action.artifact_directory).iterdir()) == []
            assert '"code":"request_refused"' in "".join(p.read_text() for p in Path(audit).rglob("*.jsonl")).replace(" ", "")
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5)
    asyncio.run(exercise())


def test_revocation_after_queueing_is_checked_by_resource_port(tmp_path, monkeypatch):
    path, _, _ = _config_file(tmp_path)
    config = load_browser_tunnel_config(str(path))
    async def exercise():
        runtime = await create_runtime_channel(config.action)
        active = True
        def binding(caller, project):
            return runtime.resolve_binding(caller, project) if active else None
        original = runtime.run_io
        async def delayed(operation):
            nonlocal active
            active = False
            return await original(operation)
        try:
            server = create_browser_tunnel_server(runtime, config.browser,
                mcp_grant=_grant(config), resolve_binding=binding)
            monkeypatch.setattr(runtime, "run_io", delayed)
            result = await _call(server, "prepare_browser_resource", {
                "project_ref": config.action.lease.project_ref, "mode": "isolated"})
            assert result.isError
            assert list(Path(config.action.artifact_directory).iterdir()) == []
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5)
    asyncio.run(exercise())
