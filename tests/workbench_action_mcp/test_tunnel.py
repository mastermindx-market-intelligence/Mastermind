from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import mcp.types as mcp_types
import pytest

import integrations.workbench_action_mcp.tunnel as tunnel_module
from integrations.workbench_action_mcp.runtime import (
    FixedTunnelChannel,
    StableWorkbenchActionLease,
    WorkbenchActionRuntime,
    channel_binding_ref,
    channel_client_ref,
    channel_subject_digest,
)
from integrations.workbench_action_mcp.tunnel import (
    TUNNEL_SCHEMA,
    TunnelConfigurationError,
    create_runtime_channel,
    create_tunnel_action_server,
    load_tunnel_config,
    parse_tunnel_config,
)
from integrations.workbench_read_mcp.runtime import (
    RuntimeCloseIncomplete,
    RuntimeConfigurationError,
)

CHANNEL = FixedTunnelChannel(
    tunnel_id="c1-personal-tunnel",
    organization_id="org-example-01",
    workspace_id="ws-disposable-01",
)
OTHER_CHANNEL = FixedTunnelChannel(
    tunnel_id="c1-personal-tunnel",
    organization_id="org-example-01",
    workspace_id="ws-other-account-02",
)
KEY_A = "9" * 64
KEY_B = "8" * 64


def _lease(channel: FixedTunnelChannel, now_ms: int) -> StableWorkbenchActionLease:
    return StableWorkbenchActionLease(
        expected_subject_digest=channel_subject_digest(channel),
        expected_client_ref=channel_client_ref(channel),
        resource="https://workbench-action.example/mcp",
        required_scopes=("workbench.action",),
        project_ref="project:" + "1" * 64,
        context_ref="context:" + "2" * 64,
        responsibility_ref="responsibility:" + "3" * 64,
        operation_ref="operation:" + "4" * 64,
        owner_ref="owner:" + "5" * 64,
        generation="generation:" + "6" * 64,
        allowed_paths=("sample.py",),
        committed_head=None,
        lease_expires_at_ms=now_ms + 300_000,
    )


def _document(
    tmp_path: Path,
    *,
    channel: FixedTunnelChannel = CHANNEL,
    key_hex: str = KEY_A,
    tag: str = "a",
) -> tuple[dict[str, object], Path, Path, str]:
    project = tmp_path / f"project-{tag}"
    audit = tmp_path / f"audit-{tag}"
    artifact = tmp_path / f"artifact-{tag}"
    artifact.mkdir(mode=0o700)
    project.mkdir(mode=0o700)
    audit.mkdir(mode=0o700)
    key_file = tmp_path / f"action-key-{tag}.hex"
    key_file.write_text(key_hex + "\n")
    os.chmod(key_file, 0o600)
    python_executable = os.path.realpath(sys.executable)
    recipe_root = (
        Path(__file__).resolve().parents[2]
        / "integrations"
        / "workbench_action_mcp"
        / "recipes"
    )
    now_ms = int(time.time() * 1000)
    lease = _lease(channel, now_ms)
    document: dict[str, object] = {
        "schema": TUNNEL_SCHEMA,
        "tunnel_id": channel.tunnel_id,
        "organization_id": channel.organization_id,
        "workspace_id": channel.workspace_id,
        "audit_policy_id": f"workbench-action-tunnel-{tag}",
        "project_root": str(project),
        "audit_directory": str(audit),
        "artifact_directory": str(artifact),
        "host_id": "a" * 64,
        "action_key_file": str(key_file),
        "python_executable": python_executable,
        "python_sha256": hashlib.sha256(
            Path(python_executable).read_bytes()
        ).hexdigest(),
        "recipe_root": str(recipe_root),
        "process_deadline_seconds": 5.0,
        "max_concurrency": 1,
        "io_timeout_seconds": 5.0,
        "close_timeout_seconds": 5.0,
        "action_ttl_ms": 60_000,
        "lease": {
            "expected_subject_digest": lease.expected_subject_digest,
            "expected_client_ref": lease.expected_client_ref,
            "resource": lease.resource,
            "required_scopes": ["workbench.action"],
            "project_ref": lease.project_ref,
            "context_ref": lease.context_ref,
            "responsibility_ref": lease.responsibility_ref,
            "operation_ref": lease.operation_ref,
            "owner_ref": lease.owner_ref,
            "generation": lease.generation,
            "allowed_paths": list(lease.allowed_paths),
            "committed_head": None,
            "lease_expires_at_ms": lease.lease_expires_at_ms,
        },
    }
    return document, project, audit, key_hex


async def _call(server, name: str, arguments: dict | None):
    handler = server.request_handlers[mcp_types.CallToolRequest]
    response = await handler(
        mcp_types.CallToolRequest(
            params=mcp_types.CallToolRequestParams(name=name, arguments=arguments)
        )
    )
    return response.root


async def _tools(server):
    handler = server.request_handlers[mcp_types.ListToolsRequest]
    response = await handler(None)
    return response.root.tools


def _error_code(result) -> str:
    assert result.isError is True
    assert len(result.content) == 1
    return json.loads(result.content[0].text)["code"]


def _audit_lines(audit: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (audit / "auth-audit.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def test_fixed_channel_prepares_commits_and_reconciles(tmp_path: Path) -> None:
    document, project, audit, _ = _document(tmp_path)
    config = parse_tunnel_config(document)
    receipts: list[dict] = []
    target = project / "sample.py"
    original = b"value = 1\n"
    target.write_bytes(original)

    async def exercise() -> str:
        runtime = await create_runtime_channel(config, call_receipt_sink=receipts.append)
        try:
            server = create_tunnel_action_server(runtime)
            tools = await _tools(server)
            assert {tool.name for tool in tools} == {
                "workspace_manifest",
                "read_project_file",
                "preview_text_replace",
                "prepare_text_patch",
                "commit_text_patch",
                "reconcile_text_patch",
                "prepare_project_command",
                "run_project_command",
                "read_action_result",
                "reconcile_action",
            }
            commit_tool = next(t for t in tools if t.name == "commit_text_patch")
            assert commit_tool.annotations.readOnlyHint is False
            assert commit_tool.annotations.destructiveHint is True

            prepared = await _call(
                server,
                "prepare_text_patch",
                {
                    "project_ref": config.lease.project_ref,
                    "relative_path": "sample.py",
                    "mode": "REPLACE",
                    "expected_sha256": hashlib.sha256(original).hexdigest(),
                    "old_text": "value = 1",
                    "new_text": "value = 2",
                },
            )
            assert prepared.isError is False
            assert prepared.structuredContent["status"] == "PREPARED"
            action_ref = prepared.structuredContent["action_ref"]

            committed = await _call(server, "commit_text_patch", {"action_ref": action_ref})
            assert committed.isError is False
            assert committed.structuredContent["effect_state"] == "APPLIED"

            observed = await _call(server, "reconcile_text_patch", {"action_ref": action_ref})
            assert observed.structuredContent["effect_state"] == "APPLIED"
            return action_ref
        finally:
            await runtime.aclose(timeout=5.0)

    action_ref = asyncio.run(exercise())
    assert target.read_text(encoding="utf-8") == "value = 2\n"

    events = _audit_lines(audit)
    assert [event["tool"] for event in events] == [
        "prepare_text_patch",
        "commit_text_patch",
        "reconcile_text_patch",
    ]
    assert all(event["code"] == "accepted" and event["accepted"] is True for event in events)
    assert all(event["channel_ref"] == channel_binding_ref(CHANNEL) for event in events)
    assert events[0]["action_digest"] is None
    assert events[1]["action_digest"] == hashlib.sha256(action_ref.encode("utf-8")).hexdigest()

    assert receipts
    assert all(
        receipt["authority_kind"] == "secure_mcp_tunnel_channel"
        and receipt["channel_ref"] == channel_binding_ref(CHANNEL)
        for receipt in receipts
    )


def test_open_channel_exposes_channel_services_without_oauth_surface(tmp_path: Path) -> None:
    project = tmp_path / "project"
    audit = tmp_path / "audit"
    project.mkdir(mode=0o700)
    audit.mkdir(mode=0o700)
    now_ms = int(time.time() * 1000)
    lease = _lease(CHANNEL, now_ms)
    project_fd = os.open(project, os.O_RDONLY | os.O_DIRECTORY)
    audit_fd = os.open(audit, os.O_RDONLY | os.O_DIRECTORY)
    artifact = tmp_path / "artifacts"
    artifact.mkdir(mode=0o700)
    artifact_fd = os.open(artifact, os.O_RDONLY | os.O_DIRECTORY)
    runtime = None
    try:
        runtime = WorkbenchActionRuntime.open_channel(
            channel=CHANNEL,
            clock_ms=lambda: int(time.time() * 1000),
            project_directory_fd=project_fd,
            audit_directory_fd=audit_fd,
            host_artifact_fd=artifact_fd,
            host_id="a" * 64,
            audit_policy_id="workbench-action-tunnel-fixture",
            lease=lease,
            action_token_key=bytes.fromhex(KEY_A),
            max_concurrency=1,
            io_timeout_seconds=5.0,
            action_ttl_ms=60_000,
        )
        services = runtime.channel_services
        assert services.channel == CHANNEL
        assert services.channel_ref == channel_binding_ref(CHANNEL)
        assert services.caller.subject_digest == channel_subject_digest(CHANNEL)
        assert services.caller.client_ref == channel_client_ref(CHANNEL)
        assert services.project_ref == lease.project_ref
        binding = runtime.resolve_binding(services.caller, lease.project_ref)
        assert binding is not None and binding.scope.allowed_paths == ("sample.py",)
        assert not hasattr(runtime, "services")
        assert not hasattr(runtime, "server")
        runtime.revoke()
        assert runtime.resolve_binding(services.caller, lease.project_ref) is None
    finally:
        if runtime is not None:
            try:
                asyncio.run(runtime.aclose(timeout=1.0))
            except Exception:
                pass
        os.close(project_fd)
        os.close(audit_fd)
        os.close(artifact_fd)


def test_open_channel_refuses_channel_not_matching_host_lease(tmp_path: Path) -> None:
    project = tmp_path / "project"
    audit = tmp_path / "audit"
    project.mkdir(mode=0o700)
    audit.mkdir(mode=0o700)
    lease = _lease(CHANNEL, int(time.time() * 1000))
    project_fd = os.open(project, os.O_RDONLY | os.O_DIRECTORY)
    audit_fd = os.open(audit, os.O_RDONLY | os.O_DIRECTORY)
    artifact = tmp_path / "artifacts"
    artifact.mkdir(mode=0o700)
    artifact_fd = os.open(artifact, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(RuntimeConfigurationError):
            WorkbenchActionRuntime.open_channel(
                channel=OTHER_CHANNEL,
                clock_ms=lambda: int(time.time() * 1000),
                project_directory_fd=project_fd,
                audit_directory_fd=audit_fd,
                host_artifact_fd=artifact_fd,
                host_id="a" * 64,
                audit_policy_id="workbench-action-tunnel-fixture",
                lease=lease,
                action_token_key=bytes.fromhex(KEY_A),
            )
    finally:
        os.close(project_fd)
        os.close(audit_fd)
        os.close(artifact_fd)


def test_expired_lease_refuses_open_and_live_admission(tmp_path: Path) -> None:
    project = tmp_path / "project"
    audit = tmp_path / "audit"
    project.mkdir(mode=0o700)
    audit.mkdir(mode=0o700)
    now_ms = int(time.time() * 1000)
    project_fd = os.open(project, os.O_RDONLY | os.O_DIRECTORY)
    audit_fd = os.open(audit, os.O_RDONLY | os.O_DIRECTORY)
    artifact = tmp_path / "artifacts"
    artifact.mkdir(mode=0o700)
    artifact_fd = os.open(artifact, os.O_RDONLY | os.O_DIRECTORY)
    runtime = None
    try:
        with pytest.raises(RuntimeConfigurationError):
            WorkbenchActionRuntime.open_channel(
                channel=CHANNEL,
                clock_ms=lambda: now_ms + 300_001,
                project_directory_fd=project_fd,
                audit_directory_fd=audit_fd,
                host_artifact_fd=artifact_fd,
                host_id="a" * 64,
                audit_policy_id="workbench-action-tunnel-fixture",
                lease=_lease(CHANNEL, now_ms),
                action_token_key=bytes.fromhex(KEY_A),
            )

        clock = {"ms": now_ms}
        runtime = WorkbenchActionRuntime.open_channel(
            channel=CHANNEL,
            clock_ms=lambda: clock["ms"],
            project_directory_fd=project_fd,
            audit_directory_fd=audit_fd,
            host_artifact_fd=artifact_fd,
            host_id="a" * 64,
            audit_policy_id="workbench-action-tunnel-fixture",
            lease=_lease(CHANNEL, now_ms),
            action_token_key=bytes.fromhex(KEY_A),
            max_concurrency=1,
            io_timeout_seconds=5.0,
            action_ttl_ms=60_000,
        )
        config_document, _, _, _ = _document(tmp_path, tag="command-binding")
        tunnel_module._bind_command_host(runtime, parse_tunnel_config(config_document))
        server = create_tunnel_action_server(runtime)

        async def exercise() -> None:
            fine = await _call(
                server,
                "prepare_text_patch",
                {
                    "project_ref": runtime.channel_services.project_ref,
                    "relative_path": "sample.py",
                    "mode": "CREATE",
                    "new_text": "hello\n",
                },
            )
            assert fine.isError is False
            clock["ms"] = runtime._lease.stable.lease_expires_at_ms
            stale = await _call(
                server,
                "prepare_text_patch",
                {
                    "project_ref": runtime.channel_services.project_ref,
                    "relative_path": "sample.py",
                    "mode": "CREATE",
                    "new_text": "again\n",
                },
            )
            assert _error_code(stale) == "CHANNEL_ADMISSION_REFUSED"

        asyncio.run(exercise())
        # Preparation is read-only: the admitted CREATE never wrote, and the
        # refused one never may.
        assert not (project / "sample.py").exists()
        events = _audit_lines(audit)
        # The narrow observation-only audit method survives effect revocation.
        assert [event["code"] for event in events] == ["accepted", "channel_refused"]
    finally:
        if runtime is not None:
            try:
                asyncio.run(runtime.aclose(timeout=1.0))
            except Exception:
                pass
        os.close(project_fd)
        os.close(audit_fd)
        os.close(artifact_fd)


def test_foreign_project_and_foreign_root_refuse(tmp_path: Path) -> None:
    document, project, audit, _ = _document(tmp_path)
    config = parse_tunnel_config(document)
    other_document, other_project, _, _ = _document(
        tmp_path, channel=CHANNEL, key_hex=KEY_A, tag="b"
    )
    other_config = parse_tunnel_config(other_document)

    async def exercise() -> None:
        runtime = await create_runtime_channel(config)
        try:
            server = create_tunnel_action_server(runtime)
            refused = await _call(
                server,
                "prepare_text_patch",
                {
                    "project_ref": "project:" + "9" * 64,
                    "relative_path": "sample.py",
                    "mode": "CREATE",
                    "new_text": "x\n",
                },
            )
            assert _error_code(refused) == "ACTION_BINDING_CHANGED"
        finally:
            await runtime.aclose(timeout=5.0)

        # A runtime opened on a different project root must refuse the action
        # prepared against the first root, even with the same channel and key.
        first = await create_runtime_channel(config)
        try:
            server = create_tunnel_action_server(first)
            prepared = await _call(
                server,
                "prepare_text_patch",
                {
                    "project_ref": config.lease.project_ref,
                    "relative_path": "sample.py",
                    "mode": "CREATE",
                    "new_text": "owned\n",
                },
            )
            action_ref = prepared.structuredContent["action_ref"]
        finally:
            await first.aclose(timeout=5.0)

        second = await create_runtime_channel(other_config)
        try:
            assert other_config.lease.project_ref == config.lease.project_ref
            server = create_tunnel_action_server(second)
            moved = await _call(server, "commit_text_patch", {"action_ref": action_ref})
            assert _error_code(moved) == "ACTION_BINDING_CHANGED"
            assert not (other_project / "sample.py").exists()
        finally:
            await second.aclose(timeout=5.0)
        assert not (project / "sample.py").exists()

    asyncio.run(exercise())


def test_foreign_account_key_cannot_decode_or_apply(tmp_path: Path) -> None:
    document_a, project_a, _, _ = _document(tmp_path, tag="a")
    document_b, project_b, _, _ = _document(
        tmp_path, channel=OTHER_CHANNEL, key_hex=KEY_B, tag="b"
    )
    config_a = parse_tunnel_config(document_a)
    config_b = parse_tunnel_config(document_b)

    async def exercise() -> None:
        first = await create_runtime_channel(config_a)
        try:
            server = create_tunnel_action_server(first)
            prepared = await _call(
                server,
                "prepare_text_patch",
                {
                    "project_ref": config_a.lease.project_ref,
                    "relative_path": "sample.py",
                    "mode": "CREATE",
                    "new_text": "account-a\n",
                },
            )
            assert prepared.isError is False
            return prepared.structuredContent["action_ref"]
        finally:
            await first.aclose(timeout=5.0)

    action_ref = asyncio.run(exercise())

    async def replay() -> None:
        second = await create_runtime_channel(config_b)
        try:
            server = create_tunnel_action_server(second)
            refused = await _call(server, "commit_text_patch", {"action_ref": action_ref})
            assert _error_code(refused) == "ACTION_INVALID"
            assert not (project_b / "sample.py").exists()
        finally:
            await second.aclose(timeout=5.0)

    asyncio.run(replay())
    assert not (project_a / "sample.py").exists()


def test_same_key_restart_reconciles_applied_patch_without_another_write(
    tmp_path: Path,
) -> None:
    document, project, audit, _ = _document(tmp_path)
    config = parse_tunnel_config(document)
    target = project / "sample.py"

    async def prepare_and_commit() -> str:
        runtime = await create_runtime_channel(config)
        try:
            server = create_tunnel_action_server(runtime)
            prepared = await _call(
                server,
                "prepare_text_patch",
                {
                    "project_ref": config.lease.project_ref,
                    "relative_path": "sample.py",
                    "mode": "CREATE",
                    "new_text": "stable\n",
                },
            )
            action_ref = prepared.structuredContent["action_ref"]
            committed = await _call(server, "commit_text_patch", {"action_ref": action_ref})
            assert committed.structuredContent["effect_state"] == "APPLIED"
            return action_ref
        finally:
            await runtime.aclose(timeout=5.0)

    async def reconcile_and_replay(action_ref: str) -> None:
        runtime = await create_runtime_channel(config)
        try:
            server = create_tunnel_action_server(runtime)
            observed = await _call(server, "reconcile_text_patch", {"action_ref": action_ref})
            assert observed.isError is False
            assert observed.structuredContent["effect_state"] == "APPLIED"
            replayed = await _call(server, "commit_text_patch", {"action_ref": action_ref})
            assert replayed.structuredContent["effect_state"] == "APPLIED"
        finally:
            await runtime.aclose(timeout=5.0)

    action_ref = asyncio.run(prepare_and_commit())
    before = target.stat()
    asyncio.run(reconcile_and_replay(action_ref))
    after = target.stat()
    assert target.read_text(encoding="utf-8") == "stable\n"
    assert (before.st_ino, before.st_mtime_ns, before.st_size) == (
        after.st_ino,
        after.st_mtime_ns,
        after.st_size,
    )


def test_dispatch_errors_are_sanitized_without_reflected_values(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    document, project, _, _ = _document(tmp_path)
    config = parse_tunnel_config(document)
    sentinel = "SECRET_ACTION_TOKEN/" + ("Q" * 4096) + "/bin/sh -c boom"

    async def exercise() -> None:
        runtime = await create_runtime_channel(config)
        try:
            server = create_tunnel_action_server(runtime)
            caplog.set_level(logging.DEBUG)
            unknown = await _call(server, sentinel, {"argv": ["/bin/sh"]})
            assert _error_code(unknown) == "TOOL_NOT_AVAILABLE"
            assert unknown.isError is True
            assert unknown.content[0].text == '{"code":"TOOL_NOT_AVAILABLE"}'
            assert sentinel not in unknown.content[0].text
            assert sentinel not in caplog.text
            captured = capsys.readouterr()
            assert sentinel not in captured.out
            assert sentinel not in captured.err
            for record in caplog.records:
                assert sentinel not in record.getMessage()
                if record.args:
                    assert sentinel not in str(record.args)

            injected = {
                "project_ref": config.lease.project_ref,
                "relative_path": "sample.py",
                "mode": "CREATE",
                "new_text": "x\n",
                "secret_reflected_value": "/bin/sh -c boom",
            }
            refused = await _call(server, "prepare_text_patch", injected)
            assert _error_code(refused) == "INVALID_REQUEST"
            text = refused.content[0].text
            assert "secret_reflected_value" not in text
            assert "/bin/sh -c boom" not in text

            oversize = await _call(
                server,
                "prepare_text_patch",
                {
                    "project_ref": config.lease.project_ref,
                    "relative_path": "sample.py",
                    "mode": "CREATE",
                    "new_text": "y" * (16384 + 1),
                },
            )
            assert _error_code(oversize) == "INVALID_REQUEST"

            missing = await _call(
                server,
                "commit_text_patch",
                {"action_ref": None},
            )
            assert _error_code(missing) == "INVALID_REQUEST"
        finally:
            await runtime.aclose(timeout=5.0)

    asyncio.run(exercise())
    assert not (project / "sample.py").exists()
    # Schema refusals of recognized tools are durably audited; the unknown
    # tool name is not a channel admission and is not audited.
    events = _audit_lines(tmp_path / "audit-a")
    assert [event["code"] for event in events] == [
        "request_refused",
        "request_refused",
        "request_refused",
    ]


def test_poisoned_audit_blocks_every_effect(tmp_path: Path) -> None:
    document, project, audit, _ = _document(tmp_path)
    config = parse_tunnel_config(document)

    async def exercise() -> None:
        runtime = await create_runtime_channel(config)
        try:
            server = create_tunnel_action_server(runtime)
            fine = await _call(
                server,
                "prepare_text_patch",
                {
                    "project_ref": config.lease.project_ref,
                    "relative_path": "sample.py",
                    "mode": "CREATE",
                    "new_text": "before-poison\n",
                },
            )
            assert fine.isError is False
            action_ref = fine.structuredContent["action_ref"]

            named = audit / "auth-audit.jsonl"
            orphan = audit / "orphaned.jsonl"
            named.rename(orphan)
            named.write_text("replacement\n", encoding="utf-8")
            named.chmod(0o600)

            blocked = await _call(
                server,
                "commit_text_patch",
                {"action_ref": action_ref},
            )
            assert _error_code(blocked) == "CHANNEL_AUDIT_UNAVAILABLE"
            assert not (project / "sample.py").exists()
        finally:
            try:
                await runtime.aclose(timeout=5.0)
            except Exception:
                runtime.revoke()
                try:
                    os.close(runtime.root_fd)
                except OSError:
                    pass

    asyncio.run(exercise())
    assert (audit / "orphaned.jsonl").exists()


def test_blocked_physical_audit_is_owned_and_event_loop_stays_responsive(
    tmp_path: Path,
) -> None:
    # Explicit physical-entry gate: emit is stalled on a threading.Event inside
    # the runtime-owned executor.  The event loop stays responsive, no effect
    # is dispatched before durable audit completion, close is incomplete until
    # release, and the stalled write is drained afterward.
    document, project, _, _ = _document(tmp_path)
    document["close_timeout_seconds"] = 0.1
    config = parse_tunnel_config(document)
    entered = threading.Event()
    release = threading.Event()

    def failsafe() -> None:
        time.sleep(8)
        release.set()

    threading.Thread(target=failsafe, daemon=True).start()

    async def exercise() -> None:
        runtime = await create_runtime_channel(config)
        real_emit = runtime.channel_services.audit_sink.emit

        def stalled(event):
            entered.set()
            if not release.wait(timeout=10):
                raise RuntimeError("stalled emit was not released")
            return real_emit(event)

        runtime.channel_services.audit_sink.emit = stalled
        try:
            server = create_tunnel_action_server(runtime)
            task = asyncio.create_task(
                _call(
                    server,
                    "prepare_text_patch",
                    {
                        "project_ref": config.lease.project_ref,
                        "relative_path": "sample.py",
                        "mode": "CREATE",
                        "new_text": "blocked-audit\n",
                    },
                )
            )
            deadline = time.monotonic() + 5
            while not entered.is_set() and time.monotonic() < deadline:
                await asyncio.sleep(0.01)
            assert entered.is_set()
            await asyncio.wait_for(asyncio.sleep(0.05), timeout=0.5)
            assert not (project / "sample.py").exists()
            with pytest.raises(RuntimeCloseIncomplete):
                await runtime.aclose(timeout=0.1)
            assert not task.done()
            release.set()
            await asyncio.wait_for(task, timeout=5)
            assert not (project / "sample.py").exists()
            await runtime.aclose(timeout=5.0)
        finally:
            release.set()
            runtime.revoke()
            try:
                await runtime.aclose(timeout=5.0)
            except Exception:
                pass

    asyncio.run(exercise())
    assert not (project / "sample.py").exists()


def test_close_drain_is_incomplete_while_physical_operation_active(tmp_path: Path) -> None:
    document, _, _, _ = _document(tmp_path)
    document["close_timeout_seconds"] = 0.1
    config = parse_tunnel_config(document)

    async def exercise() -> None:
        runtime = await create_runtime_channel(config)
        try:
            def slow() -> dict:
                time.sleep(0.6)
                return {"drained": True}

            task = asyncio.create_task(runtime.run_io(slow))
            await asyncio.sleep(0.05)
            with pytest.raises(RuntimeCloseIncomplete):
                await runtime.aclose(timeout=0.1)
            assert await task == {"drained": True}
            await runtime.aclose(timeout=5.0)
        except BaseException:
            runtime.revoke()
            try:
                await runtime.aclose(timeout=5.0)
            except Exception:
                pass
            raise

    asyncio.run(exercise())


def test_tunnel_config_rejects_malformed_identity_and_extra_keys(tmp_path: Path) -> None:
    document, _, _, _ = _document(tmp_path)
    extra = dict(document)
    extra["shell"] = "/bin/zsh"
    with pytest.raises(TunnelConfigurationError) as caught:
        parse_tunnel_config(extra)
    assert caught.value.code == "TUNNEL_CONFIGURATION_REFUSED"

    relative = dict(document)
    relative["project_root"] = "project-a"
    with pytest.raises(TunnelConfigurationError):
        parse_tunnel_config(relative)

    wrong_scope = json.loads(json.dumps(document))
    wrong_scope["lease"]["required_scopes"] = ["workbench.read"]
    with pytest.raises(TunnelConfigurationError):
        parse_tunnel_config(wrong_scope)

    empty_tunnel = dict(document)
    empty_tunnel["tunnel_id"] = ""
    with pytest.raises(TunnelConfigurationError):
        parse_tunnel_config(empty_tunnel)


def test_secure_config_and_key_acquisition_identity(tmp_path: Path) -> None:
    from integrations.workbench_action_mcp.tunnel import (
        _open_safe_directory,
        _secure_action_key,
    )

    document, _, audit, _ = _document(tmp_path)
    config_file = tmp_path / "tunnel.json"
    config_file.write_text(json.dumps(document))
    os.chmod(config_file, 0o600)
    loaded = load_tunnel_config(str(config_file))
    assert loaded.channel == CHANNEL
    assert loaded.schema == TUNNEL_SCHEMA

    duplicate = tmp_path / "duplicate.json"
    raw = json.dumps(document)
    duplicate.write_text(raw[:-1] + ',"schema": "' + TUNNEL_SCHEMA + '"}')
    os.chmod(duplicate, 0o600)
    with pytest.raises(TunnelConfigurationError):
        load_tunnel_config(str(duplicate))

    linked = tmp_path / "linked.json"
    os.link(config_file, linked)
    with pytest.raises(TunnelConfigurationError):
        load_tunnel_config(str(linked))

    symlink = tmp_path / "symlink.json"
    symlink.symlink_to(config_file)
    with pytest.raises(TunnelConfigurationError):
        load_tunnel_config(str(symlink))

    group_writable = tmp_path / "group.json"
    group_writable.write_text(json.dumps(document))
    os.chmod(group_writable, 0o620)
    with pytest.raises(TunnelConfigurationError):
        load_tunnel_config(str(group_writable))

    key_file = Path(str(document["action_key_file"]))
    os.chmod(key_file, 0o644)
    with pytest.raises(TunnelConfigurationError):
        _secure_action_key(str(key_file))
    os.chmod(key_file, 0o600)

    short_key = tmp_path / "short.hex"
    short_key.write_text("9" * 32 + "\n")
    os.chmod(short_key, 0o600)
    with pytest.raises(TunnelConfigurationError):
        _secure_action_key(str(short_key))

    audit.chmod(0o770)
    with pytest.raises(TunnelConfigurationError):
        _open_safe_directory(str(audit))
    audit.chmod(0o700)


def test_wrong_channel_configuration_refuses_composition(tmp_path: Path) -> None:
    document, _, _, _ = _document(tmp_path)
    swapped = dict(document)
    swapped["workspace_id"] = OTHER_CHANNEL.workspace_id
    config = parse_tunnel_config(swapped)

    async def attempt() -> None:
        await create_runtime_channel(config)

    with pytest.raises(TunnelConfigurationError) as caught:
        asyncio.run(attempt())
    assert caught.value.code == "TUNNEL_CONFIGURATION_REFUSED"


def test_launcher_describe_is_dependency_free_and_truthful() -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "mastermind_workbench_action_stdio.py"
    completed = subprocess.run(
        [sys.executable, "-S", str(script), "--describe"],
        cwd="/",
        env={"PATH": os.environ.get("PATH", "")},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=5,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    observed = json.loads(completed.stdout)
    assert observed == {
        "capability": "BUILT_NOT_PROVEN",
        "mode": "fixed-channel-stdio",
        "authority_kind": "secure_mcp_tunnel_channel",
        "config_schema": "mastermind.workbench_action_tunnel.v1",
        "installed": False,
        "scope": "workbench.action",
        "tools": [
            "workspace_manifest",
            "read_project_file",
            "preview_text_replace",
            "prepare_text_patch",
            "commit_text_patch",
            "reconcile_text_patch",
            "prepare_project_command",
            "run_project_command",
            "read_action_result",
            "reconcile_action",
        ],
    }
