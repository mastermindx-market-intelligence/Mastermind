"""Signed ResourcePort start → snapshot-only Worker admission over a fake relay.

This is a source-owned local process integration test; the relay is a tiny
fixture Python UNIX-socket child, NOT Playwright/Chrome or a real browser.
It proves original resource-start artifacts are compatible with the same
WorkerBrowserAdmission + BrowserActionPort. No production grants installed.
"""
from __future__ import annotations

import asyncio
import dataclasses
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

from control_plane.browser_resource_contract import WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST
from integrations.workbench_action_mcp.tunnel import create_runtime_channel
from integrations.workbench_browser_mcp import tunnel as browser_tunnel
from integrations.workbench_browser_mcp.contracts import BrowserRefCodec
from tests import test_worker_browser_admission as owner_fixture
from tests.test_workbench_browser_resource_port import _fake_relay
from tests.test_workbench_browser_tunnel import _call, _error_code


@pytest.mark.parametrize("mutation_tools", [False, True])
def test_original_browser_resource_start_receipt_serves_worker_read_and_revoke(
    tmp_path, monkeypatch, mutation_tools,
):
    original_grant = owner_fixture._grant
    names = (("browser_snapshot", "prepare_browser_click", "run_browser_action")
             if mutation_tools else ("browser_snapshot",))
    monkeypatch.setattr(
        owner_fixture, "_grant",
        lambda config: original_grant(config, names),
    )
    (api, executive, lease, epoch, generation, profile, requested, config,
     run_root) = owner_fixture._setup(tmp_path)

    # Reuse the established owner fixture's Python relay contract, with only
    # the non-browser inline read response added to the test process.
    script = _fake_relay(tmp_path)
    body = script.read_text(encoding="utf-8")
    needle = '            c.sendall(json.dumps(out,separators=(",",":")).encode()+b"\\n")'
    assert body.count(needle) == 1
    assert body.count('"tool_schema_digest":"d"*64,') == 1
    body = body.replace(
        '"tool_schema_digest":"d"*64,',
        f'"tool_schema_digest":"{WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST}",',
    )
    if mutation_tools:
        assert body.count('"allowed_tools":["browser_snapshot"],') == 1
        body = body.replace(
            '"allowed_tools":["browser_snapshot"],',
            '"allowed_tools":["browser_snapshot","browser_click"],',
        )
    body = body.replace(needle, '''            if req.get("kind") == "tool":
                out["result"] = {
                    "content": [{"type": "text", "text": "RESOURCE-START-FIXTURE"}],
                    "isError": False,
                }
''' + needle)
    script.write_text(body, encoding="utf-8")
    os.chmod(script, 0o600)

    captured = []
    relay_root = Path(tempfile.mkdtemp(prefix="mmx-worker-signed-port-", dir="/tmp"))
    os.chmod(relay_root, 0o700)
    real_factory = browser_tunnel.create_browser_ports

    def relay_builder(*, config, prepared, barrier_fd, socket_path, output_dir, profile_dir):
        assert profile_dir is None
        return (
            os.path.realpath(sys.executable), str(script),
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
            start_ref = resource.prepare_resource(
                caller,
                project_ref=runtime.channel_services.project_ref,
                mode="isolated",
            )
            started = resource.start_resource(caller, start_ref)
            assert started["effect_state"] == "APPLIED"
            assert started["reconciled"] is False
            ref = started["browser_ref"]
            replayed = resource.start_resource(caller, start_ref)
            assert replayed["effect_state"] == "APPLIED"
            assert replayed["reconciled"] is True
            assert replayed["browser_ref"] == ref
            signed = BrowserRefCodec(runtime.channel_services.action_token_key)
            observed = signed.decode_resource(ref, now_ms=runtime.channel_services.clock_ms())
            assert observed.relay_pid > 0
            assert observed.mode == "isolated"
            assert observed.profile_ref is None
            assert observed.tool_schema_digest == WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST
            payload, hmac_signature = ref.split(".")
            flipped = ("A" if hmac_signature[0] != "A" else "B") + hmac_signature[1:]
            tampered = await _call(
                worker, "browser_snapshot", {"browser_ref": payload + "." + flipped},
            )
            assert _error_code(tampered) == "BROWSER_REF_INVALID"

            snapshot = await _call(worker, "browser_snapshot", {"browser_ref": ref})
            assert snapshot.isError is False
            assert snapshot.content[0].text == "RESOURCE-START-FIXTURE"

            # Re-signing the same observed process under a different resource
            # start ID must not borrow the real resource's durable APPLIED claim.
            unclaimed = signed.encode_resource(
                dataclasses.replace(observed, start_action_id="f" * 32),
            )
            refused_unclaimed = await _call(
                worker, "browser_snapshot", {"browser_ref": unclaimed},
            )
            assert _error_code(refused_unclaimed) == "BROWSER_RECOVERY_BINDING_CHANGED"

            if mutation_tools:
                valid_prepare = await _call(worker, "prepare_browser_click", {
                    "browser_ref": ref, "target": "fixture-target",
                })
                assert valid_prepare.structuredContent["status"] == "PREPARED"
                action_ref = valid_prepare.structuredContent["action_ref"]
                first_action = await _call(worker, "run_browser_action", {
                    "browser_ref": ref, "action_ref": action_ref,
                })
                assert first_action.structuredContent["effect_state"] == "APPLIED"
                assert first_action.structuredContent["reconciled"] is False
                replay_action = await _call(worker, "run_browser_action", {
                    "browser_ref": ref, "action_ref": action_ref,
                })
                assert replay_action.structuredContent["effect_state"] == "APPLIED"
                assert replay_action.structuredContent["reconciled"] is True
                # A signed ref with real process identity but no original
                # ResourcePort APPLIED start claim must never mint an action.
                bad_prepare = await _call(worker, "prepare_browser_click", {
                    "browser_ref": unclaimed, "target": "fixture-target",
                })
                assert _error_code(bad_prepare) == "BROWSER_RECOVERY_BINDING_CHANGED"

            filename = await _call(worker, "browser_snapshot", {
                "browser_ref": ref, "filename": "not-authorized.md",
            })
            assert _error_code(filename) == "BROWSER_ARTIFACT_NOT_GRANTED"

            executive.jobs.cancel_job(lease.attempt.job_id)
            denied = await _call(worker, "browser_snapshot", {"browser_ref": ref})
            assert _error_code(denied) == "CHANNEL_ADMISSION_REFUSED"
            if mutation_tools:
                revoked_action = await _call(worker, "run_browser_action", {
                    "browser_ref": ref, "action_ref": action_ref,
                })
                assert _error_code(revoked_action) == "CHANNEL_ADMISSION_REFUSED"
            assert not (tmp_path / "not-authorized.md").exists()
            assert list(Path(config.action.artifact_directory).glob("*.md")) == []
        finally:
            if ref is not None and captured:
                result = captured[0].resource_port.cleanup_resource(
                    ref, owner_state="released", effect_state="APPLIED",
                )
                assert result["released"] is True
            runtime.revoke()
            await runtime.aclose(timeout=5)

    try:
        asyncio.run(exercise())
    finally:
        shutil.rmtree(relay_root, ignore_errors=True)


@pytest.mark.parametrize("flag,resolver", [
    (True, None),
    ("true", lambda *_args: None),
    (1, lambda *_args: None),
])
def test_private_fresh_resource_claim_requires_exact_flag_and_resolver(
    flag, resolver,
):
    """A truthy or resolverless security selection cannot silently downgrade."""
    from integrations.workbench_browser_mcp.deployment import create_browser_ports

    with pytest.raises(ValueError, match="BROWSER_FRESH_RESOURCE_CLAIM_INVALID"):
        create_browser_ports(
            resolve_binding=lambda *_args: None,
            resolve_recovery_binding=resolver,
            require_resource_claim_for_fresh=flag,
            clock_ms=lambda: 0,
            action_token_key=b"k" * 32,
            artifact_store=object(),
            host_binding=object(),
            action_ttl_ms=3000,
            host_config=object(),
            profile_resolver=lambda _ref: None,
        )
