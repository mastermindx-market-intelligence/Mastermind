"""Browser snapshot-only worker channel: dispatch fences, not catalog-only claims.

The *existing* Workbench Browser private stdio transport must refuse every
resource-start and modifying action when its synthetic grant selects only
``browser_snapshot``. This test is unarmed: no real BrowserResourceRef, Chrome
process, principal admission, production credential, extension or Browser host.
A snapshot's optional ``filename`` remains a potential artifact write and is
not represented as effect-free merely because readOnlyHint is true.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from integrations.workbench_action_mcp.tunnel import create_runtime_channel
from integrations.workbench_browser_mcp.tunnel import (
    create_browser_tunnel_server, load_browser_tunnel_config,
)
from tests.test_workbench_browser_tunnel import (
    _call, _config_file, _error_code, _tools,
)
from tests.test_workbench_browser_worker_grant import _grant


def test_snapshot_only_worker_transport_refuses_other_tools_and_unsigned_resource(tmp_path):
    path, _document, _audit_dir = _config_file(tmp_path)
    config = load_browser_tunnel_config(str(path))

    async def exercise():
        runtime = await create_runtime_channel(config.action)
        try:
            # The fixture grant is not source-signed/Runtime-admitted. What we
            # test is the original worker transport's exact dispatch boundary.
            grant = _grant(config, ("browser_snapshot",))
            assert grant.auth_status == "unsupported"
            assert grant.enabled_tools == ("browser_snapshot",)
            server = create_browser_tunnel_server(
                runtime, config.browser, mcp_grant=grant,
            )
            assert [row.name for row in await _tools(server)] == ["browser_snapshot"]

            forbidden = (
                ("prepare_browser_resource", {
                    "project_ref": config.action.lease.project_ref,
                    "mode": "isolated",
                }),
                ("start_browser_resource", {"start_ref": "unsigned"}),
                ("run_browser_action", {
                    "browser_ref": "unsigned", "action_ref": "unsigned",
                }),
                ("prepare_browser_click", {
                    "browser_ref": "unsigned", "target": "button",
                }),
                ("browser_evaluate", {"browser_ref": "unsigned", "function": "() => 1"}),
            )
            for name, payload in forbidden:
                refused = await _call(server, name, payload)
                assert _error_code(refused) == "TOOL_NOT_AVAILABLE", name

            # A catalog grant is not a Browser resource grant: no handler may
            # materialize a resource from a worker-supplied opaque string.
            requested = await _call(server, "browser_snapshot", {
                "browser_ref": "unsigned-not-an-admitted-resource",
            })
            assert requested.isError is True
            assert _error_code(requested) in {
                "BROWSER_REF_INVALID", "BROWSER_BINDING_CHANGED",
                "CHANNEL_ADMISSION_REFUSED",
            }

            # Read-only decoration is not an artifact grant. No source file or
            # Browser process may be produced by a forged read with filename.
            destination = tmp_path / "unauthorized-snapshot.md"
            refused_file = await _call(server, "browser_snapshot", {
                "browser_ref": "unsigned-not-an-admitted-resource",
                "filename": str(destination),
            })
            assert refused_file.isError is True
            assert not destination.exists()
            assert list(Path(config.action.artifact_directory).iterdir()) == []
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5)

    asyncio.run(exercise())


def test_snapshot_only_grant_does_not_silently_authorize_resource_start(tmp_path):
    path, _, _ = _config_file(tmp_path)
    config = load_browser_tunnel_config(str(path))

    async def exercise():
        runtime = await create_runtime_channel(config.action)
        try:
            server = create_browser_tunnel_server(
                runtime, config.browser,
                mcp_grant=_grant(config, ("browser_snapshot",)),
            )
            runtime.revoke()
            result = await _call(server, "start_browser_resource", {
                "start_ref": "unsigned",
            })
            assert _error_code(result) == "TOOL_NOT_AVAILABLE"
            assert list(Path(config.action.artifact_directory).iterdir()) == []
        finally:
            await runtime.aclose(timeout=5)

    asyncio.run(exercise())
