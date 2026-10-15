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
    path, _outer, _audit_dir = _config_file(tmp_path)
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
                # Actual ungranted read-side surface tool, not an unknown
                # Playwright tool; its optional filename can write artifacts.
                ("browser_take_screenshot", {
                    "browser_ref": "unsigned",
                    "filename": str(tmp_path / "ungranted-screenshot.png"),
                    "scale": "css",
                }),
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
            # This live fixture channel must reach the downstream owner port
            # and refuse the unsigned ref, not merely fail channel admission.
            assert _error_code(requested) == "BROWSER_REF_INVALID"

            # Read-only decoration is not an artifact grant. No source file or
            # Browser process may be produced by a forged read with filename.
            destination = tmp_path / "unauthorized-snapshot.md"
            refused_file = await _call(server, "browser_snapshot", {
                "browser_ref": "unsigned-not-an-admitted-resource",
                "filename": str(destination),
            })
            assert _error_code(refused_file) == "BROWSER_REF_INVALID"
            assert not destination.exists()
            assert not (tmp_path / "ungranted-screenshot.png").exists()
            # A tool not in the *source catalog* is separately out of surface,
            # not evidence of narrowing an available tool's rights.
            outside = await _call(server, "browser_evaluate", {
                "browser_ref": "unsigned", "function": "() => 1",
            })
            assert _error_code(outside) == "TOOL_NOT_AVAILABLE"
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
            # Unlike start_resource, snapshot IS a granted tool. The same
            # unsigned resource ref must now be refused at channel custody
            # after revocation, rather than even reaching its port decoder.
            revoked = await _call(server, "browser_snapshot", {
                "browser_ref": "unsigned-not-an-admitted-resource",
            })
            assert _error_code(revoked) == "CHANNEL_ADMISSION_REFUSED"
            assert list(Path(config.action.artifact_directory).iterdir()) == []
        finally:
            await runtime.aclose(timeout=5)

    asyncio.run(exercise())


def test_runtime_bound_attempt_still_refuses_snapshot_only_mutation(tmp_path, monkeypatch):
    """Existing SQLite Attempt/fence checks and exact tool grant compose.

    The source fixture uses fake process attestations and a test-local lease.
    No actual BrowserResourceRef or provider session is created; this is a
    stronger OWNER-INTEGRATION negative than a mere tools/list projection.
    """
    import os
    from tests import test_worker_browser_admission as owner_fixture

    original_grant = owner_fixture._grant
    monkeypatch.setattr(
        owner_fixture, "_grant",
        lambda config: original_grant(config, ("browser_snapshot",)),
    )
    (api, executive, lease, epoch, generation, profile, requested, config,
     run_root) = owner_fixture._setup(tmp_path)
    assert tuple(profile.mcp_server_grants[0].enabled_tools) == ("browser_snapshot",)
    assert requested.capabilities == profile.capability_manifest(
        harness_binary_digest=requested.harness_binary_digest,
    )

    async def exercise():
        runtime = await create_runtime_channel(config.action)
        try:
            admission = api.WorkerBrowserAdmission(
                executive.store, lease, epoch, generation, requested, profile,
                "worker-browser-isolated", runtime,
                run_root=run_root, expected_owner_uid=os.getuid(),
            )
            server = api.create_worker_browser_server(
                runtime, config.browser, admission,
            )
            assert [t.name for t in await _tools(server)] == ["browser_snapshot"]

            # The actual owner-bound transport refuses preparation and effects
            # even when the requesting worker has a live synthetic Attempt.
            for name, payload in (
                ("prepare_browser_resource", {
                    "project_ref": config.action.lease.project_ref,
                    "mode": "isolated",
                }),
                ("start_browser_resource", {"start_ref": "unsigned"}),
                ("run_browser_action", {
                    "browser_ref": "unsigned", "action_ref": "unsigned",
                }),
            ):
                result = await _call(server, name, payload)
                assert _error_code(result) == "TOOL_NOT_AVAILABLE", name

            invalid = await _call(server, "browser_snapshot", {
                "browser_ref": "unsigned-not-a-real-browser-resource",
            })
            assert invalid.isError is True
            assert _error_code(invalid) == "BROWSER_REF_INVALID"
            assert list(Path(config.action.artifact_directory).iterdir()) == []

            # Revoke the authoritative Job; a formerly selected read tool must
            # be denied at the trusted Runtime owner, before Browser actuation.
            executive.jobs.cancel_job(lease.attempt.job_id)
            revoked = await _call(server, "browser_snapshot", {
                "browser_ref": "unsigned-not-a-real-browser-resource",
            })
            assert _error_code(revoked) == "CHANNEL_ADMISSION_REFUSED"
            assert list(Path(config.action.artifact_directory).iterdir()) == []
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5)

    asyncio.run(exercise())
