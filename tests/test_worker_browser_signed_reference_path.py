"""Source-only signed BrowserRef must also have a durable resource-start claim.

A valid HMAC and SQLite Worker Attempt/materialization receipt alone must
not authorize Browser read without the original BrowserResourcePort start
claim. Process inspection and relay are test doubles; this is not Chrome.
"""
from __future__ import annotations

import asyncio
import dataclasses
import os
from pathlib import Path

from control_plane.codex_worker import ProcessIdentity
from integrations.workbench_action_mcp.tunnel import create_runtime_channel
from integrations.workbench_browser_mcp import tunnel as browser_tunnel
from integrations.workbench_browser_mcp.contracts import (
    BrowserRefCodec, BrowserResourceRef,
)
from integrations.workbench_browser_mcp.relay import (
    RELAY_RESPONSE_SCHEMA,
)
from tests import test_worker_browser_admission as owner_fixture
from tests.test_workbench_browser_tunnel import _call, _error_code, _tools


def test_signed_ref_without_resource_start_claim_is_denied_even_with_live_attempt(
    tmp_path, monkeypatch,
):
    original_grant = owner_fixture._grant
    monkeypatch.setattr(
        owner_fixture, "_grant",
        lambda config: original_grant(config, ("browser_snapshot",)),
    )
    (api, executive, lease, epoch, generation, profile, requested, config,
     run_root) = owner_fixture._setup(tmp_path)
    seen = []
    real_factory = browser_tunnel.create_browser_ports

    class Inspector:
        def inspect(self, pid: int):
            assert pid == 4321
            return ProcessIdentity(
                start_identity="fixture-relay-start", pgid=4321, session_id=4321,
                effective_uid=os.geteuid(), effective_gid=os.getegid(),
                real_uid=os.getuid(), real_gid=os.getgid(),
            )

    def fake_relay(_socket, request, *, timeout):
        seen.append((request["tool"], request["resource_id"], dict(request["arguments"])))
        return {
            "schema": RELAY_RESPONSE_SCHEMA,
            "request_id": request["request_id"],
            "resource_id": request["resource_id"],
            "ok": True,
            "result": {
                "content": [{"type": "text", "text": "SIGNED-FIXTURE-INLINE-DOM"}],
                "isError": False,
            },
        }

    def instrumented_factory(**kwargs):
        ports = real_factory(**kwargs)
        monkeypatch.setattr(ports.action_port, "_inspector", Inspector())
        monkeypatch.setattr(ports.action_port, "_relay_requester", fake_relay)
        return ports

    monkeypatch.setattr(browser_tunnel, "create_browser_ports", instrumented_factory)

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
            assert [row.name for row in await _tools(server)] == ["browser_snapshot"]
            services = runtime.channel_services
            binding = runtime.resolve_binding(services.caller, services.project_ref)
            assert binding is not None
            scope = binding.scope
            now = services.clock_ms()
            fixture_ref = BrowserResourceRef(
                schema="mastermind.workbench_browser_ref.v1",
                start_action_id="c" * 32,
                subject_digest=services.caller.subject_digest,
                client_ref=services.caller.client_ref,
                resource=services.caller.resource,
                project_ref=binding.project_ref,
                context_ref=scope.context_ref,
                responsibility_ref=scope.responsibility_ref,
                operation_ref=scope.operation_ref,
                owner_ref=scope.owner_ref,
                generation=scope.generation,
                host_id=services.host_binding.host_id,
                boot_session_id=services.host_binding.boot_session_id,
                relay_pid=4321,
                relay_start_identity="fixture-relay-start",
                relay_pgid=4321,
                relay_session_id=4321,
                mode="isolated",
                profile_ref=None,
                tool_schema_digest="d" * 64,
                issued_at_ms=now - 1000,
                expires_at_ms=now + 15000,
            )
            token = BrowserRefCodec(
                services.action_token_key,
            ).encode_resource(fixture_ref)
            inline = await _call(server, "browser_snapshot", {"browser_ref": token})
            assert _error_code(inline) == "BROWSER_RECOVERY_BINDING_CHANGED"
            assert seen == [], "a valid HMAC alone must not dispatch Browser work"

            # A validly signed token must still be bound to this exact live
            # Runtime generation and host, never merely to the HMAC key.
            for mismatch in (
                {"generation": "generation:another-attempt"},
                {"host_id": "f" * 64},
            ):
                altered = BrowserRefCodec(services.action_token_key).encode_resource(
                    dataclasses.replace(fixture_ref, **mismatch),
                )
                refused = await _call(server, "browser_snapshot", {
                    "browser_ref": altered,
                })
                assert _error_code(refused) == "BROWSER_BINDING_CHANGED"
                assert seen == []

            denied_filename = await _call(server, "browser_snapshot", {
                "browser_ref": token, "filename": str(tmp_path / "denied.md"),
            })
            assert _error_code(denied_filename) == "BROWSER_ARTIFACT_NOT_GRANTED"
            assert seen == []
            mutation = await _call(server, "start_browser_resource", {
                "start_ref": "invalid",
            })
            assert _error_code(mutation) == "TOOL_NOT_AVAILABLE"
            assert seen == []

            executive.jobs.cancel_job(lease.attempt.job_id)
            revoked = await _call(server, "browser_snapshot", {
                "browser_ref": token,
            })
            assert _error_code(revoked) == "CHANNEL_ADMISSION_REFUSED"
            assert seen == []
            assert not (tmp_path / "denied.md").exists()
            assert list(Path(config.browser.output_root).iterdir()) == []
            assert list(Path(config.action.artifact_directory).iterdir()) == []
        finally:
            runtime.revoke()
            await runtime.aclose(timeout=5)

    asyncio.run(exercise())
