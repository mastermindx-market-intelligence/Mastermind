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
from tests.test_workbench_browser_tunnel import _call, _error_code


def test_snapshot_only_private_channel_stays_dormant_until_exact_receipt(tmp_path, monkeypatch):
    """The broker may prepare a channel before it persists a launch receipt.

    The channel must not gain Browser authority from its own construction;
    only the original Runtime owner plus the exact durable receipt may allow
    calls, and later Job cancellation must immediately revoke them.
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
            payload = {"browser_ref": "unsigned-not-an-admitted-browser-ref"}
            before = await _call(server, "browser_snapshot", payload)
            assert _error_code(before) == "CHANNEL_ADMISSION_REFUSED"
            assert list(Path(config.action.artifact_directory).iterdir()) == []

            # Simulate only the broker's exact authenticated receipt persistence,
            # not another lease, session, provider launch or Browser resource.
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
