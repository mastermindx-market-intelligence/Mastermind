"""Browser worker channel admission before, during and after an owned launch.

These are fixture-only original Runtime/Browser owner gates, not a live worker,
real BrowserResourceRef, Chrome startup or independent permission grant.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from integrations.workbench_action_mcp.tunnel import create_runtime_channel
from tests import test_worker_browser_admission as owner_fixture
from tests.test_worker_browser_admission import _materialize
from tests.test_workbench_browser_tunnel import _call, _error_code, _tools


def test_snapshot_only_private_channel_stays_dormant_until_exact_receipt(tmp_path, monkeypatch):
    """A fixture-bound channel refuses before receipt, admits, then revokes.

    This does not invoke the real broker resource factory or provider start.
    The fixture uses a real SQLite Runtime and the production receipt writer
    and reader with synthetic process identities. After persistence the
    admitted call reaches the Browser port; its unsigned BrowserRef is refused.
    No real Browser resource is started or granted by this test.
    """
    original_grant = owner_fixture._grant
    monkeypatch.setattr(
        owner_fixture, "_grant",
        lambda config: original_grant(config, ("browser_snapshot",)),
    )
    (api, executive, lease, epoch, generation, profile, requested, config,
     _fixture_root) = owner_fixture._setup(tmp_path)
    assert profile.mcp_server_grants[0].enabled_tools == ("browser_snapshot",)

    # The independent test root intentionally starts without a materialization
    # receipt even though the fixture's original root has a valid one.
    pending_root = tmp_path / "awaiting-authorized-materialization"
    pending_root.mkdir(mode=0o700)
    assert list(pending_root.iterdir()) == []

    async def exercise():
        runtime = await create_runtime_channel(config.action)
        try:
            admission = api.WorkerBrowserAdmission(
                executive.store, lease, epoch, generation, requested, profile,
                "worker-browser-isolated", runtime, run_root=pending_root,
                expected_owner_uid=os.getuid(),
            )
            server = api.create_worker_browser_server(
                runtime, config.browser, admission,
            )
            assert [t.name for t in await _tools(server)] == ["browser_snapshot"]
            ungranted = await _call(server, "prepare_browser_resource", {
                "project_ref": config.action.lease.project_ref,
                "mode": "isolated",
            })
            assert _error_code(ungranted) == "TOOL_NOT_AVAILABLE"
            payload = {"browser_ref": "unsigned-not-an-admitted-browser-ref"}
            before = await _call(server, "browser_snapshot", payload)
            assert _error_code(before) == "CHANNEL_ADMISSION_REFUSED"
            assert list(Path(config.action.artifact_directory).iterdir()) == []

            # Mirror the broker receipt field set with synthetic test identities.
            # This is not a live broker, provider or Browser resource launch.
            _materialize(pending_root, executive, epoch, generation, requested)
            admitted = await _call(server, "browser_snapshot", payload)
            # The granted call reaches the original Browser port, which then
            # correctly refuses our deliberately unsigned resource reference.
            assert _error_code(admitted) == "BROWSER_REF_INVALID"
            assert list(Path(config.action.artifact_directory).iterdir()) == []

            executive.jobs.cancel_job(lease.attempt.job_id)
            revoked = await _call(server, "browser_snapshot", payload)
            assert _error_code(revoked) == "CHANNEL_ADMISSION_REFUSED"
            assert list(Path(config.action.artifact_directory).iterdir()) == []
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5)

    asyncio.run(exercise())
