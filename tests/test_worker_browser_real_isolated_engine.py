"""Opt-in physical Chromium/Playwright snapshot through original BrowserResourcePort.

This owns a disposable headless browser with synthetic HTML, NOT a private
Chrome tab, a browser-profile grant or an Executive/provider model turn. Reuse
original signed ResourcePort, leased Runtime, worker admission and cleanup.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import pytest

from control_plane.browser_resource_contract import WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST
from integrations.workbench_action_mcp.tunnel import create_runtime_channel
from integrations.workbench_browser_mcp import tunnel as browser_tunnel
from integrations.workbench_browser_mcp.contracts import BrowserRefCodec
from tests import test_worker_browser_admission as owner_fixture
from tests.test_workbench_browser_resource_port import _fake_relay
from tests.test_workbench_browser_tunnel import _call, _error_code


@pytest.mark.skipif(
    os.environ.get("MASTERMIND_REAL_ISOLATED_BROWSER_RESOURCE_TEST") != "1",
    reason="requires explicit M2 isolated Chromium and Playwright engine opt-in",
)
def test_real_playwright_dom_snapshot_through_signed_worker_browser_resource(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    original_grant = owner_fixture._grant
    monkeypatch.setattr(
        owner_fixture, "_grant",
        lambda config: original_grant(config, ("browser_snapshot",)),
    )
    (api, executive, lease, epoch, generation, profile, requested, config,
     run_root) = owner_fixture._setup(tmp_path)

    # Pin a separate Python interpreter that actually has Playwright; don't
    # change the original Workbench relay launcher or borrow Chrome user data.
    engine_python = shutil.which("python3")
    if engine_python is None:
        pytest.skip("isolated Python engine unavailable")
    info = subprocess.run(
        [engine_python, "-c",
         "import playwright, pathlib, json;print(json.dumps(list(playwright.__path__)))"],
        capture_output=True, text=True, timeout=5,
    )
    if info.returncode:
        pytest.skip("explicit isolated Playwright Python package unavailable")
    import json
    package_dir = Path(json.loads(info.stdout)[0]).resolve(strict=True)
    package_parent = package_dir.parent
    browser_cache = Path.home() / "Library/Caches/ms-playwright"
    if not browser_cache.is_dir():
        pytest.skip("headless test engine cache absent; no browser download")
    assert (package_dir / "sync_api").is_dir()
    assert not (tmp_path / "ChromeProfile").exists()

    # Preserve the exact original Browser ResourcePort UNIX relay contract,
    # replacing only the fake tool result with real DOM/ARIA computation.
    script = _fake_relay(tmp_path)
    source = script.read_text(encoding="utf-8")
    source = source.replace(
        '"tool_schema_digest":"d"*64,',
        f'"tool_schema_digest":"{WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST}",',
    )
    target = '            c.sendall(json.dumps(out,separators=(",",":")).encode()+b"\\n")'
    assert source.count(target) == 1
    insert = '''            if req.get("kind") == "tool":
                if req.get("tool") not in (None,"browser_snapshot"):
                    raise RuntimeError("unqualified browser action in isolated proof")
                from playwright.sync_api import sync_playwright
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    try:
                        context = browser.new_context(
                            accept_downloads=False, service_workers="block")
                        try:
                            page = context.new_page()
                            # No URL, Chrome private profile, credential,
                            # private tab, disk artifact or external network.
                            page.set_content(
                                "<!doctype html><title>Fabric Test</title>"
                                "<main><h1>FABRIC_REAL_ISOLATED_BROWSER_DOM</h1>"
                                "<p>Authorized synthetic source-only page</p></main>")
                            aria = page.locator("main").aria_snapshot()
                            assert "FABRIC_REAL_ISOLATED_BROWSER_DOM" in aria
                            out["result"] = {
                                "content":[{"type":"text", "text":aria}],
                                "isError":False}
                        finally:
                            context.close()
                    finally:
                        browser.close()
'''
    source = source.replace(target, insert + target)
    # M2's approved Py3.14/user-installed Playwright package and browser
    # *binary cache* are test inputs, not Chrome's personal profile/session.
    source = 'import sys,os\nsys.path.insert(0,' + repr(str(package_parent)) + ')\n' + (
        'os.environ["PLAYWRIGHT_BROWSERS_PATH"]=' + repr(str(browser_cache)) + '\n'
    ) + source
    script.write_text(source, encoding="utf-8")
    os.chmod(script, 0o600)

    relay_root = Path(tempfile.mkdtemp(prefix="mmx-physical-browser-", dir="/tmp"))
    os.chmod(relay_root, 0o700)
    captured = []
    real_factory = browser_tunnel.create_browser_ports

    def relay_builder(*, config, prepared, barrier_fd, socket_path, output_dir, profile_dir):
        assert profile_dir is None, "never connect a private Chrome profile"
        return (
            os.path.realpath(engine_python), str(script),
            "--barrier-fd", str(barrier_fd), "--socket-path", str(socket_path),
            "--resource-id", prepared.action_id,
        )

    def instrumented_factory(**kwargs):
        kwargs["host_config"] = dataclasses.replace(
            kwargs["host_config"], relay_root=relay_root,
        )
        ports = real_factory(**kwargs, relay_command_builder=relay_builder)
        captured.append(ports)
        return ports

    monkeypatch.setattr(browser_tunnel, "create_browser_ports", instrumented_factory)

    async def exercise():
        runtime = await create_runtime_channel(config.action)
        ref = None
        try:
            admission = api.WorkerBrowserAdmission(
                executive.store, lease, epoch, generation, requested, profile,
                "worker-browser-isolated", runtime, run_root=run_root,
                expected_owner_uid=os.getuid(),
            )
            worker = api.create_worker_browser_server(
                runtime, config.browser, admission,
            )
            assert len(captured) == 1
            resource = captured[0].resource_port
            caller = runtime.channel_services.caller
            pending = resource.prepare_resource(
                caller, project_ref=runtime.channel_services.project_ref,
                mode="isolated",
            )
            started = resource.start_resource(caller, pending)
            assert started["effect_state"] == "APPLIED"
            assert started["reconciled"] is False
            ref = started["browser_ref"]
            codec = BrowserRefCodec(runtime.channel_services.action_token_key)
            verified = codec.decode_resource(
                ref, now_ms=runtime.channel_services.clock_ms(),
            )
            assert verified.relay_pid > 0
            assert verified.profile_ref is None
            assert verified.mode == "isolated"
            assert verified.tool_schema_digest == WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST
            assert resource.start_resource(caller, pending)["reconciled"] is True

            result = await _call(worker, "browser_snapshot", {"browser_ref": ref})
            assert result.isError is False
            snapshot = result.content[0].text
            assert "FABRIC_REAL_ISOLATED_BROWSER_DOM" in snapshot
            assert "heading" in snapshot
            # Browser read-only grant never supplies artifact-writing authority.
            filename = await _call(worker, "browser_snapshot", {
                "browser_ref": ref, "filename": "forbidden.md",
            })
            assert _error_code(filename) == "BROWSER_ARTIFACT_NOT_GRANTED"
            assert not (tmp_path / "forbidden.md").exists()
            assert not list(Path(config.action.artifact_directory).glob("*.md"))
            executive.jobs.cancel_job(lease.attempt.job_id)
            revoked = await _call(worker, "browser_snapshot", {"browser_ref": ref})
            assert _error_code(revoked) == "CHANNEL_ADMISSION_REFUSED"
            return snapshot
        finally:
            if ref is not None and captured:
                result = captured[0].resource_port.cleanup_resource(
                    ref, owner_state="released", effect_state="APPLIED",
                )
                assert result["released"] is True
            runtime.revoke()
            await runtime.aclose(timeout=5)

    try:
        actual_snapshot = asyncio.run(exercise())
        snapshot_bytes = actual_snapshot.encode("utf-8")
        actual_sha = hashlib.sha256(snapshot_bytes).hexdigest()
        assert len(actual_sha) == 64 and len(snapshot_bytes) > 0
        print(
            "FABRIC_PHYSICAL_BROWSER_PROOF_V1 "
            + json.dumps(
                {
                    "schema": "mastermind.fabric_isolated_browser_source_proof.v1",
                    "snapshot_sha256": actual_sha,
                    "snapshot_bytes": len(snapshot_bytes),
                    "snapshot_marker": "FABRIC_REAL_ISOLATED_BROWSER_DOM",
                    "engine": "headless-playwright-chromium",
                    "runtime": "test-local-sqlite-worker-attempt",
                    "external_browser_resource": False,
                },
                sort_keys=True,
            )
        )
    finally:
        shutil.rmtree(relay_root, ignore_errors=True)
