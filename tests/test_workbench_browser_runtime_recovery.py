"""Retained Workbench runtime, real artifact store and Unix peer recovery path."""
from __future__ import annotations

import asyncio
import dataclasses
import os
import socket
import tempfile
import threading
from pathlib import Path

import pytest

from control_plane.browser_resource_contract import WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST
from control_plane.codex_worker import ProcessInspector
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.workbench_action_mcp.action_artifacts import (
    ACTION_PURPOSE_BROWSER_RESOURCE,
    ActionArtifactIdentity,
    acquire_store_writer,
    claim_action,
    finalize_action,
    write_action_process,
)
from integrations.workbench_action_mcp.contracts import ActionCaller
from integrations.workbench_action_mcp.runtime import WorkbenchActionRuntime
from integrations.workbench_browser_mcp.browser_port import BrowserPortRefused
from integrations.workbench_browser_mcp.contracts import BrowserResourceRef
from integrations.workbench_browser_mcp.deployment import create_browser_deployment
from integrations.workbench_browser_mcp.relay import (
    BrowserRelayError,
    BrowserRelayServer,
    McpSessionReceipt,
    McpStdioSession,
    relay_request,
)
from integrations.workbench_read_mcp.runtime import RuntimeClosed
from tests.test_workbench_browser_deployment import _fixture as browser_fixture
from tests.workbench_action_mcp.test_runtime import (
    _Keys,
    _lease,
    _open_directories,
    _policy,
)


class RecoverySession(McpStdioSession):
    def __init__(self):
        super().__init__(
            argv=("/usr/bin/true",), env={},
            allowed_tools=frozenset({"browser_click", "browser_snapshot"}),
            expected_tool_schema_digest=WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST,
        )
        self.calls = []

    def start(self):
        self._receipt = McpSessionReceipt(
            child_pid=os.getpid(),
            tool_schema_digest=WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST,
            allowed_tools=("browser_click", "browser_snapshot"),
        )
        return self._receipt

    def call(self, tool, arguments):
        self.calls.append(tool)
        if tool == "browser_click":
            raise BrowserRelayError("synthetic click ACK lost")
        assert tool == "browser_snapshot"
        return {"content": [{"type": "text", "text": "same carrier"}], "isError": False}

    def close(self):
        self._receipt = None


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="Unix sockets required")
@pytest.mark.parametrize("terminal", ["root_changed", "explicit_revoke"])
def test_original_runtime_recovers_read_only_after_effect_unknown_and_lease_expiry(
    tmp_path: Path, terminal: str
):
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    project, _audit, _artifacts, project_fd, audit_fd, artifact_fd = _open_directories(
        runtime_root
    )
    fixture_root = tmp_path / "browser-fixture"
    fixture_root.mkdir()
    fake_fd, _fake_services, host_config, catalog, _fake_caller, _calls = browser_fixture(
        fixture_root
    )
    os.close(fake_fd)
    base_ms = 1_800_000_000_000
    clock = {"ms": base_ms + 100}
    subject, client = "a" * 64, "b" * 64
    policy = _policy(subject)
    auth = JwtAuthenticator(policy=policy, jwks_cache=_Keys())
    lease = _lease(subject, client, policy.resource, base_ms)
    caller = ActionCaller(
        subject_digest=subject, client_ref=client, resource=policy.resource,
        scopes=("workbench.action",), expires_at=base_ms // 1000 + 600,
    )
    runtime = None
    relay = None
    thread = None
    try:
        with tempfile.TemporaryDirectory(prefix="br-", dir="/tmp") as short_root:
            relay_root = Path(short_root)
            runtime = WorkbenchActionRuntime.open(
                authenticator=auth, policy=policy,
                now=lambda: clock["ms"] // 1000,
                clock_ms=lambda: clock["ms"],
                project_directory_fd=project_fd,
                audit_directory_fd=audit_fd,
                host_artifact_fd=artifact_fd,
                host_id="c" * 64,
                lease=lease, action_token_key=b"z" * 32,
                allowed_hosts=("127.0.0.1:9443",),
            )
            observed = ProcessInspector().inspect(os.getpid())
            deployment = create_browser_deployment(
                services=runtime.services,
                host_config=dataclasses.replace(host_config, relay_root=relay_root),
                tool_catalog=catalog,
                profile_resolver=lambda _ref: None,
                inspector=ProcessInspector(),
            )
            binding = runtime.resolve_binding(caller, lease.project_ref)
            assert binding is not None
            resource = BrowserResourceRef(
                schema="mastermind.workbench_browser_ref.v1",
                start_action_id="d" * 32,
                subject_digest=subject, client_ref=client, resource=policy.resource,
                project_ref=lease.project_ref,
                context_ref=lease.context_ref,
                responsibility_ref=lease.responsibility_ref,
                operation_ref=lease.operation_ref,
                owner_ref=lease.owner_ref,
                generation=lease.generation,
                host_id=runtime.host_binding.host_id,
                boot_session_id=runtime.host_binding.boot_session_id,
                relay_pid=os.getpid(),
                relay_start_identity=observed.start_identity,
                relay_pgid=observed.pgid,
                relay_session_id=observed.session_id,
                mode="isolated", profile_ref=None,
                tool_schema_digest=WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST,
                issued_at_ms=base_ms + 50,
                expires_at_ms=lease.lease_expires_at_ms,
            )
            browser_ref = deployment.action_port.codec.encode_resource(resource)
            identity = ActionArtifactIdentity(
                action_id=resource.start_action_id,
                purpose=ACTION_PURPOSE_BROWSER_RESOURCE,
                subject_digest=subject, client_ref=client, resource=policy.resource,
                project_ref=lease.project_ref,
                context_ref=lease.context_ref,
                responsibility_ref=lease.responsibility_ref,
                operation_ref=lease.operation_ref,
                owner_ref=lease.owner_ref,
                generation=lease.generation,
                root_device=binding.scope.root_device,
                root_inode=binding.scope.root_inode,
                store_device=runtime.artifact_store.device,
                store_inode=runtime.artifact_store.inode,
                host_id=resource.host_id,
                boot_session_id=resource.boot_session_id,
                relative_path=f"browser:{resource.start_action_id}",
                source_identity=resource.tool_schema_digest,
            )
            with acquire_store_writer(runtime.artifact_store):
                assert claim_action(
                    runtime.artifact_store, identity, claimed_at_ms=base_ms + 10
                ).created
                write_action_process(
                    runtime.artifact_store, identity,
                    pid=resource.relay_pid,
                    process_start_identity=resource.relay_start_identity,
                    pgid=resource.relay_pgid,
                    session_id=resource.relay_session_id,
                    host_id=resource.host_id,
                    boot_session_id=resource.boot_session_id,
                    recorded_at_ms=base_ms + 20,
                )
                finalize_action(
                    runtime.artifact_store, identity,
                    effect_state="APPLIED",
                    observed_sha256=resource.tool_schema_digest,
                    completed_at_ms=base_ms + 30,
                    durability="durable", details={"relay": "ready"},
                )
            session = RecoverySession()
            relay = BrowserRelayServer(
                resource_id=resource.start_action_id,
                socket_path=relay_root / f"{resource.start_action_id}.sock",
                session=session, owner_pid=os.getpid(), parent_pid=os.getppid(),
                expires_at_ms=lease.lease_expires_at_ms,
                clock_ms=lambda: clock["ms"],
            )
            thread = threading.Thread(target=relay.serve_forever, daemon=True)
            thread.start()
            relay.wait_ready(timeout=3)

            async def exercise():
                action_ref = await deployment.prepare_action(
                    caller, browser_ref, "browser_click", {"target": "button"}
                )
                result = await deployment.run_action(caller, browser_ref, action_ref)
                assert result["effect_state"] == "EFFECT_UNKNOWN"
                clock["ms"] = lease.lease_expires_at_ms
                assert runtime.resolve_binding(caller, lease.project_ref) is None
                with pytest.raises(RuntimeClosed):
                    await runtime.run_io(lambda: "mutating ordinary operation")
                with pytest.raises(RuntimeClosed):
                    await deployment.prepare_action(
                        caller, browser_ref, "browser_click", {"target": "button"}
                    )
                with pytest.raises(RuntimeClosed):
                    await deployment.run_action(caller, browser_ref, action_ref)
                with pytest.raises(RuntimeClosed):
                    await runtime.run_recovery_io("browser_click", lambda: None)
                snapshot = await deployment.read_tool(caller, browser_ref, "browser_snapshot", {})
                assert snapshot["content"][0]["text"] == "same carrier"
                assert session.calls == ["browser_click", "browser_snapshot"]
                with pytest.raises(BrowserPortRefused, match="BROWSER_BINDING_CHANGED"):
                    await deployment.read_tool(
                        dataclasses.replace(caller, client_ref="different"),
                        browser_ref, "browser_snapshot", {},
                    )
                with pytest.raises(BrowserPortRefused, match="BROWSER_BINDING_CHANGED"):
                    await deployment.read_tool(
                        dataclasses.replace(caller, expires_at=base_ms // 1000 + 299),
                        browser_ref, "browser_snapshot", {},
                    )
                original_resolver = deployment.action_port._resolve_recovery_binding
                assert original_resolver is not None

                def changed_root(actual, project_ref):
                    retained = original_resolver(actual, project_ref)
                    assert retained is not None
                    return dataclasses.replace(
                        retained,
                        scope=dataclasses.replace(
                            retained.scope, root_inode=retained.scope.root_inode + 1
                        ),
                    )

                deployment.action_port._resolve_recovery_binding = changed_root
                with pytest.raises(BrowserPortRefused, match="BROWSER_RECOVERY_BINDING_CHANGED"):
                    await deployment.read_tool(caller, browser_ref, "browser_snapshot", {})
                deployment.action_port._resolve_recovery_binding = original_resolver
                previous_inspector = deployment.action_port._inspector
                deployment.action_port._inspector = type(
                    "ChangedInspector", (),
                    {"inspect": lambda _self, _pid: dataclasses.replace(
                        observed, start_identity="changed"
                    )},
                )()
                with pytest.raises(BrowserPortRefused, match="PROCESS_IDENTITY_CHANGED"):
                    await deployment.read_tool(caller, browser_ref, "browser_snapshot", {})
                deployment.action_port._inspector = previous_inspector
                if terminal == "root_changed":
                    os.chmod(project, 0o755)
                else:
                    runtime.revoke()
                with pytest.raises(RuntimeClosed):
                    await deployment.read_tool(caller, browser_ref, "browser_snapshot", {})
                if terminal == "root_changed":
                    os.chmod(project, 0o700)

            asyncio.run(exercise())
            assert session.calls == ["browser_click", "browser_snapshot"]
    finally:
        if relay is not None:
            relay.stop()
        if thread is not None:
            thread.join(timeout=3)
        if runtime is not None:
            try:
                asyncio.run(runtime.aclose(timeout=5))
            except RuntimeClosed:
                pass
        for fd in (project_fd, audit_fd, artifact_fd):
            os.close(fd)
