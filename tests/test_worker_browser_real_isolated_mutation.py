"""Opt-in actual isolated Chromium click through original signed Worker Browser.

The page is entirely synthetic. A disposable Python relay launches Playwright
headless Chromium on first tool request; no user session, profile or URL.
Real ResourcePort/APPLIED claim, WorkerAdmission and ActionPort are exercised,
but the SQLite Attempt and Browser grant are test-only, not production.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
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
    os.environ.get("MASTERMIND_REAL_ISOLATED_BROWSER_MUTATION_TEST") != "1",
    reason="requires explicit M2 disposable Playwright Chromium mutation opt-in",
)
def test_real_chromium_click_from_original_worker_claim(tmp_path, monkeypatch):
    engine_python = shutil.which("python3")
    if engine_python is None:
        pytest.skip("isolated Python unavailable")
    probe = subprocess.run(
        [engine_python, "-c", "import playwright,json;print(json.dumps(list(playwright.__path__)))"],
        capture_output=True, text=True, timeout=5,
    )
    if probe.returncode:
        pytest.skip("Playwright engine package absent; no download")
    package_dir = Path(json.loads(probe.stdout)[0]).resolve(strict=True)
    cache = Path.home() / "Library/Caches/ms-playwright"
    if not cache.is_dir():
        pytest.skip("physical engine cache absent; no download")

    original_grant = owner_fixture._grant
    tools = ("browser_snapshot", "prepare_browser_click", "run_browser_action")
    monkeypatch.setattr(owner_fixture, "_grant",
                        lambda config: original_grant(config, tools))
    (api, executive, lease, epoch, generation, profile, requested, config,
     run_root) = owner_fixture._setup(tmp_path)

    script = _fake_relay(tmp_path)
    text = script.read_text(encoding="utf-8")
    old_digest = '"tool_schema_digest":"d"*64,'
    old_tools = '"allowed_tools":["browser_snapshot"],'
    assert text.count(old_digest) == text.count(old_tools) == 1
    text = text.replace(
        old_digest, f'"tool_schema_digest":"{WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST}",'
    ).replace(old_tools, '"allowed_tools":["browser_snapshot","browser_click"],')
    target = '            c.sendall(json.dumps(out,separators=(",",":")).encode()+b"\\n")'
    assert text.count(target) == 1
    # Lazy initialize a separate Chromium process inside the resource-owned
    # relay. Keep one page across snapshot, click, and subsequent snapshot.
    initialized = '''pw=browser=context=page=None
'''
    assert text.count("try:\n    while not stop:") == 1
    text = text.replace("try:\n    while not stop:", initialized + "try:\n    while not stop:")
    operation = '''            if req.get("kind") == "tool":
                if req.get("tool") not in ("browser_snapshot", "browser_click"):
                    raise RuntimeError("unapproved tool in physical fixture")
                if page is None:
                    from playwright.sync_api import sync_playwright
                    pw = sync_playwright().start()
                    browser = pw.chromium.launch(headless=True)
                    context = browser.new_context(
                        accept_downloads=False, service_workers="block")
                    context.route("**/*", lambda route: route.abort())
                    page = context.new_page()
                    page.set_content(
                        '<!doctype html><title>Fabric Action</title>'
                        '<main><h1 id="state">FABRIC_BUTTON_READY</h1>'
                        '<button type="button" onclick="document.getElementById(\\'state\\').textContent=\\'FABRIC_BUTTON_CLICKED\\'">Toggle</button></main>'
                    )
                if req["tool"] == "browser_click":
                    if req["arguments"] != {"target":"Toggle"}:
                        raise RuntimeError("unexpected target or arguments")
                    page.get_by_role("button", name="Toggle").click()
                snapshot = page.locator("main").aria_snapshot()
                out["result"] = {
                    "content":[{"type":"text","text":snapshot}], "isError":False,
                }
'''
    text = text.replace(target, operation + target)
    finish = "finally:\n    s.close()\n"
    assert text.count(finish) == 1
    text = text.replace(finish, """finally:
    s.close()
    if context is not None: context.close()
    if browser is not None: browser.close()
    if pw is not None: pw.stop()
""")
    text = (
        "import sys,os\nsys.path.insert(0,"+repr(str(package_dir.parent))+")\n"
        'os.environ["PLAYWRIGHT_BROWSERS_PATH"]='+repr(str(cache))+"\n"+text
    )
    script.write_text(text, encoding="utf-8")
    os.chmod(script, 0o600)

    relay_root = Path(tempfile.mkdtemp(prefix="mmx-physical-click-", dir="/tmp"))
    os.chmod(relay_root, 0o700)
    observed = []
    source_factory = browser_tunnel.create_browser_ports

    def builder(*, config, prepared, barrier_fd, socket_path, output_dir, profile_dir):
        assert profile_dir is None
        return (
            os.path.realpath(engine_python), str(script), "--barrier-fd",
            str(barrier_fd), "--socket-path", str(socket_path),
            "--resource-id", prepared.action_id,
        )

    def instrumented_factory(**kwargs):
        kwargs["host_config"] = dataclasses.replace(
            kwargs["host_config"], relay_root=relay_root,
        )
        ports = source_factory(**kwargs, relay_command_builder=builder)
        observed.append(ports)
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
            server = api.create_worker_browser_server(runtime, config.browser, admission)
            resource = observed[0].resource_port
            caller = runtime.channel_services.caller
            prepared = resource.prepare_resource(
                caller, project_ref=runtime.channel_services.project_ref,
                mode="isolated",
            )
            start = resource.start_resource(caller, prepared)
            assert start["effect_state"] == "APPLIED"
            ref = start["browser_ref"]
            assert resource.start_resource(caller, prepared)["reconciled"] is True
            verified = BrowserRefCodec(
                runtime.channel_services.action_token_key,
            ).decode_resource(ref, now_ms=runtime.channel_services.clock_ms())
            assert verified.mode == "isolated" and verified.profile_ref is None
            assert verified.tool_schema_digest == WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST

            before = await _call(server, "browser_snapshot", {"browser_ref": ref})
            assert before.isError is False
            before_dom = before.content[0].text
            assert "FABRIC_BUTTON_READY" in before_dom
            assert "FABRIC_BUTTON_CLICKED" not in before_dom

            pending = await _call(server, "prepare_browser_click", {
                "browser_ref": ref, "target": "Toggle",
            })
            assert pending.structuredContent["status"] == "PREPARED"
            action_ref = pending.structuredContent["action_ref"]
            outcome = await _call(server, "run_browser_action", {
                "browser_ref": ref, "action_ref": action_ref,
            })
            assert outcome.structuredContent["effect_state"] == "APPLIED"
            assert outcome.structuredContent["reconciled"] is False
            replay = await _call(server, "run_browser_action", {
                "browser_ref": ref, "action_ref": action_ref,
            })
            assert replay.structuredContent["effect_state"] == "APPLIED"
            assert replay.structuredContent["reconciled"] is True

            after = await _call(server, "browser_snapshot", {"browser_ref": ref})
            assert after.isError is False
            after_dom = after.content[0].text
            assert "FABRIC_BUTTON_CLICKED" in after_dom
            assert before_dom != after_dom

            invalid = BrowserRefCodec(
                runtime.channel_services.action_token_key,
            ).encode_resource(dataclasses.replace(verified, start_action_id="f"*32))
            refused = await _call(server, "prepare_browser_click", {
                "browser_ref": invalid, "target": "Toggle",
            })
            assert _error_code(refused) == "BROWSER_RECOVERY_BINDING_CHANGED"
            filename = await _call(server, "browser_snapshot", {
                "browser_ref": ref, "filename": "not-authorized.md",
            })
            assert _error_code(filename) == "BROWSER_ARTIFACT_NOT_GRANTED"
            assert not (tmp_path / "not-authorized.md").exists()
            assert not list(Path(config.action.artifact_directory).glob("*.md"))
            ungranted = await _call(server, "prepare_browser_fill_form", {
                "browser_ref": ref, "fields": [],
            })
            assert _error_code(ungranted) == "TOOL_NOT_AVAILABLE"
            executive.jobs.cancel_job(lease.attempt.job_id)
            revoked = await _call(server, "run_browser_action", {
                "browser_ref": ref, "action_ref": action_ref,
            })
            assert _error_code(revoked) == "CHANNEL_ADMISSION_REFUSED"
            revoked_read = await _call(server, "browser_snapshot", {"browser_ref": ref})
            assert _error_code(revoked_read) == "CHANNEL_ADMISSION_REFUSED"
            return before_dom, after_dom
        finally:
            if ref is not None and observed:
                recorded = BrowserRefCodec(
                    runtime.channel_services.action_token_key,
                ).decode_resource(ref, now_ms=runtime.channel_services.clock_ms())
                socket_path = relay_root / f"{recorded.start_action_id}.sock"
                cleanup = observed[0].resource_port.cleanup_resource(
                    ref, owner_state="released", effect_state="APPLIED",
                )
                assert cleanup["released"] is True
                assert not socket_path.exists()
            runtime.revoke()
            await runtime.aclose(timeout=5)

    try:
        before_dom, after_dom = asyncio.run(exercise())
        print("FABRIC_PHYSICAL_BROWSER_CLICK_PROOF_V1 "+json.dumps({
            "schema":"mastermind.fabric_physical_browser_click_source_proof.v1",
            "before_bytes":len(before_dom.encode()), "after_bytes":len(after_dom.encode()),
            "before_sha256":hashlib.sha256(before_dom.encode()).hexdigest(),
            "after_sha256":hashlib.sha256(after_dom.encode()).hexdigest(),
            "engine":"isolated-headless-playwright-chromium",
            "controller_admission":"test-local-sqlite-fixture",
        },sort_keys=True))
    finally:
        shutil.rmtree(relay_root, ignore_errors=True)
