"""Read-only worker tools cannot silently acquire artifact-write authority.

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

            # This ungranted private STDIO tunnel is not the authenticated
            # attended HTTP endpoint. Its original permissive port remains.
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


def test_multi_read_tool_worker_grant_cannot_write_artifacts(tmp_path):
    """Every private worker read grant needs separate output-file authority.

    Screenshot uses a default output filename even when none is supplied.
    This source-only fixture checks dispatch policy, not a real browser session.
    """
    path, _, _ = _config_file(tmp_path)
    config = load_browser_tunnel_config(str(path))

    async def exercise():
        runtime = await create_runtime_channel(config.action)
        try:
            names = (
                "browser_snapshot",
                "browser_take_screenshot",
                "browser_console_messages",
                "browser_network_requests",
            )
            server = create_browser_tunnel_server(
                runtime, config.browser, mcp_grant=_grant(config, names),
            )
            invalid_ref = "unsigned-not-an-admitted-browser-ref"
            for name, payload in (
                ("browser_snapshot", {
                    "browser_ref": invalid_ref,
                    "filename": str(tmp_path / "page.md"),
                }),
                ("browser_take_screenshot", {
                    "browser_ref": invalid_ref,
                    "scale": "css",
                }),
                ("browser_console_messages", {
                    "browser_ref": invalid_ref,
                    "level": "info",
                    "filename": str(tmp_path / "console.txt"),
                }),
                ("browser_network_requests", {
                    "browser_ref": invalid_ref,
                    "static": False,
                    "filename": str(tmp_path / "network.txt"),
                }),
            ):
                result = await _call(server, name, payload)
                assert _error_code(result) == "BROWSER_ARTIFACT_NOT_GRANTED", name

            without_filename = await _call(server, "browser_snapshot", {
                "browser_ref": invalid_ref,
            })
            assert _error_code(without_filename) == "BROWSER_REF_INVALID"
            assert not list(tmp_path.glob("*.txt"))
            assert not list(tmp_path.glob("*.md"))
            assert list(Path(config.browser.output_root).iterdir()) == []
            assert list(Path(config.action.artifact_directory).iterdir()) == []
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5)

    asyncio.run(exercise())


def test_private_worker_artifact_refusal_precedes_observable_port_dispatch(
    tmp_path, monkeypatch,
):
    """An inline read reaches a controlled spy; file-output reads do not.

    This spy deliberately replaces only BrowserActionPort.call_read_tool.
    It is NOT a real BrowserRef, Playwright relay, Chrome process or Worker
    signing receipt; it distinguishes MCP dispatch from an invalid-ref refusal.
    """
    from integrations.workbench_browser_mcp import tunnel as tunnel_module

    path, _, audit_dir = _config_file(tmp_path)
    config = load_browser_tunnel_config(str(path))
    calls = []
    real_factory = tunnel_module.create_browser_ports

    def instrumented_factory(**kwargs):
        ports = real_factory(**kwargs)

        def spy_read(caller, browser_ref, name, arguments):
            calls.append((browser_ref, name, dict(arguments)))
            return {
                "content": [{"type": "text", "text": "controlled inline snapshot"}],
                "isError": False,
            }

        monkeypatch.setattr(ports.action_port, "call_read_tool", spy_read)
        return ports

    monkeypatch.setattr(tunnel_module, "create_browser_ports", instrumented_factory)

    async def exercise():
        runtime = await create_runtime_channel(config.action)
        try:
            names = (
                "browser_snapshot", "browser_take_screenshot",
                "browser_console_messages", "browser_network_requests",
            )
            server = create_browser_tunnel_server(
                runtime, config.browser, mcp_grant=_grant(config, names),
            )
            opaque = "deliberately-unsigned-ref-for-spy"
            allowed = await _call(server, "browser_snapshot", {"browser_ref": opaque})
            assert allowed.isError is False
            assert allowed.content[0].text == "controlled inline snapshot"
            assert calls == [(opaque, "browser_snapshot", {})]

            for name, args in (
                ("browser_snapshot", {"filename": "snapshot.md"}),
                ("browser_take_screenshot", {"scale": "css"}),
                ("browser_console_messages", {
                    "level": "info", "filename": "console.txt",
                }),
                ("browser_network_requests", {
                    "static": False, "filename": "requests.txt",
                }),
            ):
                denied = await _call(
                    server, name, {"browser_ref": opaque, **args},
                )
                assert _error_code(denied) == "BROWSER_ARTIFACT_NOT_GRANTED"
                assert calls == [(opaque, "browser_snapshot", {})]

            records = [
                json.loads(line)
                for line in (audit_dir / "auth-audit.jsonl").read_text().splitlines()
            ]
            assert [row["code"] for row in records] == (
                ["accepted"] + ["request_refused"] * 4
            )
            assert [row["accepted"] for row in records] == (
                [True] + [False] * 4
            )
            runtime.revoke()
            after_revoke = await _call(
                server, "browser_snapshot", {"browser_ref": opaque},
            )
            assert _error_code(after_revoke) == "CHANNEL_ADMISSION_REFUSED"
            assert calls == [(opaque, "browser_snapshot", {})]
            assert list(Path(config.browser.output_root).iterdir()) == []
            assert list(Path(config.action.artifact_directory).iterdir()) == []
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5)

    asyncio.run(exercise())
