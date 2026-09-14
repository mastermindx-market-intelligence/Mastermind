from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import threading

import pytest

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from integrations.business_mcp_auth.contracts import (
    CHANNEL_AUDIT_SCHEMA,
    ChannelAuditEvent,
    load_resource_policy,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.workbench_action_mcp.contracts import ActionCaller, ActionTokenCodec
from integrations.workbench_action_mcp.patch_port import create_text_patch_port
import integrations.workbench_action_mcp.runtime as runtime_module
from integrations.workbench_action_mcp.runtime import (
    FixedTunnelChannel,
    StableWorkbenchActionLease,
    WorkbenchActionRuntime,
    channel_binding_ref,
    channel_client_ref,
    channel_subject_digest,
)
from integrations.workbench_read_mcp.runtime import (
    RuntimeCloseIncomplete,
    RuntimeCloseUncertain,
    RuntimeConfigurationError,
)


class _Keys:
    def __init__(self) -> None:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        self.jwk.update(kid="fixture", alg="RS256", use="sig")

    async def key_for(self, kid):
        if kid != "fixture":
            raise ValueError("unknown key")
        return self.jwk


def _policy(subject: str):
    return load_resource_policy(
        {
            "schema": "mastermind.business_mcp_auth_policy.v1",
            "policy_id": "fixture.workbench.action.runtime",
            "resource": "https://workbench-action.example/mcp",
            "resource_metadata_url": "https://workbench-action.example/.well-known/oauth-protected-resource/mcp",
            "issuer": "https://identity.workbench-action.example",
            "authorization_servers": ["https://identity.workbench-action.example"],
            "jwks_uri": "https://identity.workbench-action.example/jwks",
            "required_scopes": ["workbench.action"],
            "allowed_subject_digests": [subject],
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 0,
            "max_token_lifetime_seconds": 3600,
            "jwks_cache_ttl_seconds": 60,
            "unknown_kid_refresh_cooldown_seconds": 1,
            "fetch_failure_backoff_seconds": 1,
        }
    )


def _lease(subject: str, client: str, resource: str, now_ms: int) -> StableWorkbenchActionLease:
    return StableWorkbenchActionLease(
        expected_subject_digest=subject,
        expected_client_ref=client,
        resource=resource,
        required_scopes=("workbench.action",),
        project_ref="project:" + "1" * 64,
        context_ref="context:" + "2" * 64,
        responsibility_ref="responsibility:" + "3" * 64,
        operation_ref="operation:" + "4" * 64,
        owner_ref="owner:" + "5" * 64,
        generation="generation:" + "6" * 64,
        allowed_paths=("sample.py",),
        committed_head="7" * 40,
        lease_expires_at_ms=now_ms + 300_000,
    )


def _open_directories(tmp_path: Path) -> tuple[Path, Path, Path, int, int, int]:
    project = tmp_path / "project"
    audit = tmp_path / "audit"
    artifacts = tmp_path / "artifacts"
    project.mkdir(mode=0o700)
    audit.mkdir(mode=0o700)
    artifacts.mkdir(mode=0o700)
    return (
        project,
        audit,
        artifacts,
        os.open(project, os.O_RDONLY | os.O_DIRECTORY),
        os.open(audit, os.O_RDONLY | os.O_DIRECTORY),
        os.open(artifacts, os.O_RDONLY | os.O_DIRECTORY),
    )


def test_runtime_executes_patch_through_shared_bounded_executor(tmp_path: Path) -> None:
    project, _audit, _artifacts, project_fd, audit_fd, artifact_fd = _open_directories(
        tmp_path
    )
    target = project / "sample.py"
    original = b"value = 1\n"
    target.write_bytes(original)

    now_seconds = 1_800_000_000
    now_ms = now_seconds * 1000
    subject = "a" * 64
    client = "b" * 64
    policy = _policy(subject)
    auth = JwtAuthenticator(policy=policy, jwks_cache=_Keys())
    lease = _lease(subject, client, policy.resource, now_ms)
    token_key = b"z" * 32
    runtime = None
    try:
        runtime = WorkbenchActionRuntime.open(
            authenticator=auth,
            policy=policy,
            now=lambda: now_seconds,
            clock_ms=lambda: now_ms,
            project_directory_fd=project_fd,
            audit_directory_fd=audit_fd,
            host_artifact_fd=artifact_fd,
            host_id="c" * 64,
            lease=lease,
            action_token_key=token_key,
            allowed_hosts=("127.0.0.1:9443",),
            max_concurrency=1,
            io_timeout_seconds=5.0,
            action_ttl_ms=60_000,
        )
        caller = ActionCaller(
            subject_digest=subject,
            client_ref=client,
            resource=policy.resource,
            scopes=("workbench.action",),
            expires_at=now_seconds + 600,
        )
        binding = runtime.resolve_binding(caller, lease.project_ref)
        assert binding is not None
        assert binding.scope.root_device == os.fstat(project_fd).st_dev
        assert runtime.services.artifact_store is runtime.artifact_store
        assert runtime.services.host_binding is runtime.host_binding
        assert runtime.host_binding.host_id == "c" * 64
        assert runtime.host_binding.boot_session_id

        prepare, commit, reconcile = create_text_patch_port(
            resolve_binding=runtime.resolve_binding,
            clock_ms=lambda: now_ms,
            run_io=runtime.run_io,
            token_codec=ActionTokenCodec(token_key),
            artifact_store=runtime.artifact_store,
            host=runtime.host_binding,
            action_ttl_ms=60_000,
        )

        async def exercise() -> None:
            prepared = await prepare(
                caller,
                {
                    "project_ref": lease.project_ref,
                    "relative_path": "sample.py",
                    "mode": "REPLACE",
                    "expected_sha256": hashlib.sha256(original).hexdigest(),
                    "old_text": "value = 1",
                    "new_text": "value = 2",
                },
            )
            result = await commit(caller, prepared["action_ref"])
            assert result["effect_state"] == "APPLIED"
            observed = await reconcile(caller, prepared["action_ref"])
            assert observed["effect_state"] == "APPLIED"
            await runtime.aclose(timeout=5.0)

        asyncio.run(exercise())
        assert target.read_text() == "value = 2\n"
        assert runtime.resolve_binding(caller, lease.project_ref) is None
        os.fstat(project_fd)
        os.fstat(audit_fd)
        os.fstat(artifact_fd)
    finally:
        if runtime is not None:
            try:
                asyncio.run(runtime.aclose(timeout=1.0))
            except Exception:
                pass
        os.close(project_fd)
        os.close(audit_fd)
        os.close(artifact_fd)


def test_channel_audit_remains_owned_after_source_drift_and_drains_before_close(
    tmp_path: Path,
) -> None:
    channel = FixedTunnelChannel("tunnel-a", "org-a", "workspace-a")
    now_ms = 1_800_000_000_000
    project, audit, _artifacts, project_fd, audit_fd, artifact_fd = _open_directories(
        tmp_path
    )
    lease = _lease(
        channel_subject_digest(channel),
        channel_client_ref(channel),
        "https://workbench-action.example/mcp",
        now_ms,
    )
    runtime = WorkbenchActionRuntime.open_channel(
        channel=channel,
        clock_ms=lambda: now_ms,
        project_directory_fd=project_fd,
        audit_directory_fd=audit_fd,
        host_artifact_fd=artifact_fd,
        host_id="d" * 64,
        audit_policy_id="workbench-action-channel-test",
        lease=lease,
        action_token_key=b"x" * 32,
        max_concurrency=1,
    )
    entered = threading.Event()
    release = threading.Event()
    real_emit = runtime._audit_sink.emit

    def blocked_emit(event: ChannelAuditEvent) -> None:
        entered.set()
        if not release.wait(5):
            raise AssertionError("audit worker was not released")
        real_emit(event)

    runtime._audit_sink.emit = blocked_emit
    os.chmod(project, 0o720)
    assert runtime.resolve_binding(runtime.channel_services.caller, lease.project_ref) is None
    os.chmod(project, 0o700)
    event = ChannelAuditEvent(
        schema=CHANNEL_AUDIT_SCHEMA,
        policy_id=runtime.channel_services.audit_policy_id,
        code="channel_refused",
        accepted=False,
        channel_ref=channel_binding_ref(channel),
        tool="prepare_text_patch",
        action_digest=None,
    )

    async def exercise() -> None:
        pending = asyncio.create_task(runtime.emit_channel_audit(event))
        assert await asyncio.to_thread(entered.wait, 1)
        with pytest.raises(RuntimeCloseIncomplete):
            await runtime.aclose(timeout=0.01)
        os.fstat(runtime.root_fd)
        os.fstat(runtime.artifact_store.dir_fd)
        release.set()
        await pending
        await runtime.aclose(timeout=1)

    try:
        asyncio.run(exercise())
        rows = [json.loads(line) for line in (audit / "auth-audit.jsonl").read_text().splitlines()]
        assert [row["code"] for row in rows] == ["channel_refused"]
    finally:
        for descriptor in (project_fd, audit_fd, artifact_fd):
            os.close(descriptor)


def test_channel_audit_rejects_foreign_binding_and_arbitrary_callback(tmp_path: Path) -> None:
    channel = FixedTunnelChannel("tunnel-a", "org-a", "workspace-a")
    now_ms = 1_800_000_000_000
    _project, _audit, _artifacts, project_fd, audit_fd, artifact_fd = _open_directories(
        tmp_path
    )
    lease = _lease(
        channel_subject_digest(channel),
        channel_client_ref(channel),
        "https://workbench-action.example/mcp",
        now_ms,
    )
    runtime = WorkbenchActionRuntime.open_channel(
        channel=channel,
        clock_ms=lambda: now_ms,
        project_directory_fd=project_fd,
        audit_directory_fd=audit_fd,
        host_artifact_fd=artifact_fd,
        host_id="d" * 64,
        audit_policy_id="workbench-action-channel-test",
        lease=lease,
        action_token_key=b"x" * 32,
    )
    foreign = ChannelAuditEvent(
        schema=CHANNEL_AUDIT_SCHEMA,
        policy_id=runtime.channel_services.audit_policy_id,
        code="channel_refused",
        accepted=False,
        channel_ref="f" * 64,
        tool="prepare_text_patch",
        action_digest=None,
    )

    async def exercise() -> None:
        with pytest.raises(TypeError):
            await runtime.emit_channel_audit(lambda: None)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            await runtime.emit_channel_audit(foreign)
        await runtime.aclose(timeout=1)

    try:
        asyncio.run(exercise())
    finally:
        for descriptor in (project_fd, audit_fd, artifact_fd):
            os.close(descriptor)


def test_artifact_cleanup_uncertainty_is_sticky_across_repeated_close(tmp_path: Path) -> None:
    now_seconds = 1_800_000_000
    subject = "a" * 64
    policy = _policy(subject)
    _project, _audit, _artifacts, project_fd, audit_fd, artifact_fd = _open_directories(
        tmp_path
    )
    runtime = WorkbenchActionRuntime.open(
        authenticator=JwtAuthenticator(policy=policy, jwks_cache=_Keys()),
        policy=policy,
        now=lambda: now_seconds,
        clock_ms=lambda: now_seconds * 1000,
        project_directory_fd=project_fd,
        audit_directory_fd=audit_fd,
        host_artifact_fd=artifact_fd,
        host_id="e" * 64,
        lease=_lease(subject, "b" * 64, policy.resource, now_seconds * 1000),
        action_token_key=b"z" * 32,
        allowed_hosts=("127.0.0.1:9443",),
    )
    runtime.artifact_store.mark_cleanup_uncertain("test_injected")

    async def exercise() -> None:
        with pytest.raises(RuntimeCloseUncertain) as first:
            await runtime.aclose(timeout=1)
        with pytest.raises(RuntimeCloseUncertain) as repeated:
            await runtime.aclose(timeout=1)
        assert repeated.value is first.value

    try:
        asyncio.run(exercise())
    finally:
        for descriptor in (project_fd, audit_fd, artifact_fd):
            os.close(descriptor)


def test_darwin_boot_fallback_is_refused_before_descriptor_adoption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now_seconds = 1_800_000_000
    subject = "a" * 64
    policy = _policy(subject)
    _project, _audit, _artifacts, project_fd, audit_fd, artifact_fd = _open_directories(
        tmp_path
    )

    class FallbackInspector:
        def boot_session_id(self) -> str:
            return "adapter-123"

    monkeypatch.setattr(runtime_module, "ProcessInspector", FallbackInspector)
    monkeypatch.setattr(runtime_module.platform, "system", lambda: "Darwin")
    try:
        with pytest.raises(RuntimeConfigurationError):
            WorkbenchActionRuntime.open(
                authenticator=JwtAuthenticator(policy=policy, jwks_cache=_Keys()),
                policy=policy,
                now=lambda: now_seconds,
                clock_ms=lambda: now_seconds * 1000,
                project_directory_fd=project_fd,
                audit_directory_fd=audit_fd,
                host_artifact_fd=artifact_fd,
                host_id="e" * 64,
                lease=_lease(subject, "b" * 64, policy.resource, now_seconds * 1000),
                action_token_key=b"z" * 32,
                allowed_hosts=("127.0.0.1:9443",),
            )
        os.fstat(project_fd)
        os.fstat(audit_fd)
        os.fstat(artifact_fd)
    finally:
        for descriptor in (project_fd, audit_fd, artifact_fd):
            os.close(descriptor)


def test_construction_failure_attempts_project_audit_and_artifact_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now_seconds = 1_800_000_000
    subject = "a" * 64
    policy = _policy(subject)
    _project, _audit, _artifacts, project_fd, audit_fd, artifact_fd = _open_directories(
        tmp_path
    )
    real_open_owned_root = runtime_module._open_owned_root
    real_close = os.close
    owned_descriptors: list[int] = []
    attempted_closes: list[int] = []
    audit_close_attempted = False

    def record_owned_root(host_fd: int):
        result = real_open_owned_root(host_fd)
        owned_descriptors.append(result[0])
        return result

    def fail_project_close(descriptor: int) -> None:
        attempted_closes.append(descriptor)
        if owned_descriptors and descriptor == owned_descriptors[0]:
            raise OSError("injected project close failure")
        real_close(descriptor)

    real_audit_close = runtime_module.DurableAuthAuditSink.close

    def record_audit_close(sink) -> None:
        nonlocal audit_close_attempted
        audit_close_attempted = True
        real_audit_close(sink)

    monkeypatch.setattr(runtime_module, "_open_owned_root", record_owned_root)
    def fail_wiring(_services: object) -> None:
        raise RuntimeError("wire failed")

    monkeypatch.setattr(runtime_module, "create_deployment", fail_wiring)
    monkeypatch.setattr(runtime_module.DurableAuthAuditSink, "close", record_audit_close)
    monkeypatch.setattr(runtime_module.os, "close", fail_project_close)
    try:
        with pytest.raises(RuntimeCloseUncertain) as failure:
            WorkbenchActionRuntime.open(
                authenticator=JwtAuthenticator(policy=policy, jwks_cache=_Keys()),
                policy=policy,
                now=lambda: now_seconds,
                clock_ms=lambda: now_seconds * 1000,
                project_directory_fd=project_fd,
                audit_directory_fd=audit_fd,
                host_artifact_fd=artifact_fd,
                host_id="e" * 64,
                lease=_lease(subject, "b" * 64, policy.resource, now_seconds * 1000),
                action_token_key=b"z" * 32,
                allowed_hosts=("127.0.0.1:9443",),
            )
        assert isinstance(failure.value.primary_error, RuntimeError)
        assert audit_close_attempted
        assert len(owned_descriptors) == 2
        assert all(descriptor in attempted_closes for descriptor in owned_descriptors)
    finally:
        monkeypatch.setattr(runtime_module.os, "close", real_close)
        for descriptor in (*owned_descriptors, project_fd, audit_fd, artifact_fd):
            try:
                real_close(descriptor)
            except OSError:
                pass
