"""The snapshot-only worker tool cannot silently acquire a filename write.

A source-selected read tool is not an artifact-write authority. These checks
exercise the existing private Workbench MCP tunnel with synthetic caller scope,
not a real BrowserResourceRef, credential, Chrome or worker Job/Attempt.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from integrations.workbench_action_mcp.tunnel import create_runtime_channel
from integrations.workbench_browser_mcp.tunnel import (
    create_browser_tunnel_server, load_browser_tunnel_config,
)
from tests.test_workbench_browser_tunnel import _call, _config_file, _error_code
from tests.test_workbench_browser_worker_grant import _grant


def test_snapshot_only_worker_refuses_filename_before_browser_port(tmp_path):
    path, _, audit_dir = _config_file(tmp_path)
    config = load_browser_tunnel_config(str(path))

    async def exercise():
        runtime = await create_runtime_channel(config.action)
        try:
            granted = create_browser_tunnel_server(
                runtime, config.browser,
                mcp_grant=_grant(config, ("browser_snapshot",)),
            )
            forged_ref = "unsigned-not-an-admitted-browser-ref"
            read = await _call(granted, "browser_snapshot", {
                "browser_ref": forged_ref,
            })
            assert _error_code(read) == "BROWSER_REF_INVALID"

            filename = tmp_path / "unauthorized-worker-output.md"
            refused = await _call(granted, "browser_snapshot", {
                "browser_ref": forged_ref,
                "filename": str(filename),
            })
            assert _error_code(refused) == "BROWSER_ARTIFACT_NOT_GRANTED"
            evidence = [
                json.loads(line)
                for line in (audit_dir / "auth-audit.jsonl").read_text().splitlines()
            ]
            assert evidence[-1]["code"] == "request_refused"
            assert evidence[-1]["accepted"] is False
            assert evidence[-1]["tool"] == "browser_snapshot"
            assert not filename.exists()
            assert list(Path(config.action.artifact_directory).iterdir()) == []

            # The attended/unrestricted Workbench Browser port is a separate
            # original owner: this narrow worker-only fence changes no API.
            general = create_browser_tunnel_server(runtime, config.browser)
            unrestricted_invalid = await _call(general, "browser_snapshot", {
                "browser_ref": forged_ref, "filename": str(filename),
            })
            assert _error_code(unrestricted_invalid) == "BROWSER_REF_INVALID"
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5)

    asyncio.run(exercise())


def test_bound_worker_snapshot_artifact_refused_before_port_and_after_revoke(
    tmp_path, monkeypatch,
):
    """Existing SQLite Runtime receipt may admit a read, never a file write."""
    from tests import test_worker_browser_admission as owner_fixture

    original = owner_fixture._grant
    monkeypatch.setattr(
        owner_fixture, "_grant",
        lambda config: original(config, ("browser_snapshot",)),
    )
    (api, executive, lease, epoch, generation, profile, requested, config,
     run_root) = owner_fixture._setup(tmp_path)
    assert profile.mcp_server_grants[0].enabled_tools == ("browser_snapshot",)

    async def exercise():
        runtime = await create_runtime_channel(config.action)
        try:
            admission = api.WorkerBrowserAdmission(
                executive.store, lease, epoch, generation, requested, profile,
                "worker-browser-isolated", runtime, run_root=run_root,
                expected_owner_uid=os.getuid(),
            )
            server = api.create_worker_browser_server(
                runtime, config.browser, admission,
            )
            ref = "unsigned-not-an-admitted-browser-ref"
            no_file = await _call(server, "browser_snapshot", {
                "browser_ref": ref,
            })
            assert _error_code(no_file) == "BROWSER_REF_INVALID"
            filename = tmp_path / "worker-should-not-write.md"
            with_file = await _call(server, "browser_snapshot", {
                "browser_ref": ref, "filename": str(filename),
            })
            assert _error_code(with_file) == "BROWSER_ARTIFACT_NOT_GRANTED"
            assert not filename.exists()
            assert list(Path(config.action.artifact_directory).iterdir()) == []

            executive.jobs.cancel_job(lease.attempt.job_id)
            after_revoke = await _call(server, "browser_snapshot", {
                "browser_ref": ref, "filename": str(filename),
            })
            assert _error_code(after_revoke) == "CHANNEL_ADMISSION_REFUSED"
            assert list(Path(config.action.artifact_directory).iterdir()) == []
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5)

    asyncio.run(exercise())
