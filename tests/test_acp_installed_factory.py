from __future__ import annotations

import hashlib
import importlib
import os
from pathlib import Path

import pytest

from control_plane.executive_worker_broker import BrokerPolicy
from control_plane.worker_adapter import (
    adapter_descriptor,
    bind_reviewed_adapter,
    construct_reviewed_adapter,
)
from control_plane.worker_execution_contract import (
    BinaryAttestation,
    LAUNCH_ATTESTATION_SCHEMA_VERSION,
    LaunchAttestation,
    WorkerLaunchSpec,
    WorkerProcessRef,
)
from integrations.acp_worker.adapter import AcpWorkerAdapter
from integrations.acp_worker.native import AcpNativeProfile
from integrations.acp_worker.tool_admission import AcpNativeToolGate, AcpObservedTool
from integrations.acp_worker.turn import AcpProfile


def _installed():
    try:
        return importlib.import_module("integrations.acp_worker.installed")
    except ModuleNotFoundError:
        pytest.fail("installed ACP factory is missing")


def _binary(path: Path) -> BinaryAttestation:
    info = path.stat()
    return BinaryAttestation(
        path=str(path),
        real_path=str(path.resolve(strict=True)),
        version="fixture-1",
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        team_identifier=None,
        size=info.st_size,
        device=info.st_dev,
        inode=info.st_ino,
        mode=info.st_mode & 0o7777,
        uid=info.st_uid,
        gid=info.st_gid,
        mtime_ns=info.st_mtime_ns,
    )


def _packet(tmp_path: Path, *, environment=None, private_startup=True):
    installed = _installed()
    workspace = tmp_path / "workspaces"
    run_root = tmp_path / "runs"
    provider_home = tmp_path / "provider-home"
    for path in (workspace, run_root, provider_home):
        path.mkdir(mode=0o700)
        path.chmod(0o700)
    bootstrap = tmp_path / "governed-acp.mjs"
    bootstrap.write_text("console.log('fixture')\n", encoding="utf-8")
    digest = hashlib.sha256(bootstrap.read_bytes()).hexdigest()
    binary = _binary(Path(os.environ.get("PYTHON", os.sys.executable)).resolve(strict=True))
    native_profile = AcpNativeProfile(
        "deepseek-governed-acp",
        binary,
        (binary.real_path, str(bootstrap)),
        private_startup=private_startup,
        allowed_environment_keys=("PATH", "MMX_DSH_PROFILE_ROOT") if private_startup else None,
    )
    gate = AcpNativeToolGate(
        "a" * 64,
        digest,
        (AcpObservedTool("mcp__granted__read_file", "b" * 64),),
        ((str(bootstrap), digest),),
    )
    policy = BrokerPolicy(
        control_uid=450 if os.geteuid() != 450 else 449,
        worker_uid=os.geteuid(),
        worker_gid=os.getegid(),
        worker_user="fixture-acp-worker",
        worker_id="acp-fixture",
        workspace_root=workspace,
        run_root=run_root,
        provider_home=provider_home,
        allowed_supplementary_gids=frozenset(),
        require_secret_canary=True,
    )
    values = environment if environment is not None else {
        "PATH": "/usr/bin:/bin",
        "MMX_DSH_PROFILE_ROOT": str(tmp_path / "supply"),
    }
    return installed.AcpInstalledHostPacket(
        policy=policy,
        protocol_profile=AcpProfile(
            "deepseek-harness-acp",
            "0.2.0-rc.1",
            model_option_provider="fixture",
        ),
        native_profile=native_profile,
        tool_gate=gate,
        environment=values,
        auth_mode="none",
    )


def test_acp_descriptor_has_reviewed_class_but_remains_unarmed(tmp_path):
    _installed()
    descriptor = adapter_descriptor("acp")
    assert descriptor.implemented is False
    assert descriptor.implementation == (
        "integrations.acp_worker.installed.InstalledAcpWorkerAdapter"
    )


def test_reviewed_factory_constructs_existing_acp_adapter_without_open_run_injection(tmp_path):
    installed = _installed()
    packet = _packet(tmp_path)
    adapter = construct_reviewed_adapter("acp", packet)
    assert type(adapter) is installed.InstalledAcpWorkerAdapter
    assert isinstance(adapter, AcpWorkerAdapter)
    assert adapter.adapter_id == "acp"
    assert bind_reviewed_adapter(adapter, "acp").adapter_id == "acp"
    assert adapter.installed_host_digest == packet.digest
    with pytest.raises(TypeError):
        construct_reviewed_adapter("acp", packet, open_run=lambda _spec: None)


def test_provider_free_packet_refuses_credential_bearing_home(tmp_path):
    installed = _installed()
    packet = _packet(tmp_path)
    (packet.policy.provider_home / "auth.json").write_text("secret", encoding="utf-8")
    with pytest.raises(ValueError, match="credentialless provider home"):
        installed.InstalledAcpWorkerAdapter(packet)


@pytest.mark.parametrize(
    "environment",
    [
        {"PATH": "/usr/bin:/bin", "OPENAI_API_KEY": "secret"},
        {"PATH": "/usr/bin:/bin", "AUTH_TOKEN": "secret"},
        {"PATH": "/usr/bin:/bin", "HOME": "/tmp/ambient"},
        {"PATH": "/usr/bin:/bin"},
    ],
)
def test_packet_refuses_credential_or_environment_ceiling_drift(tmp_path, environment):
    installed = _installed()
    with pytest.raises(ValueError, match="environment"):
        _packet(tmp_path, environment=environment)


def test_packet_requires_private_startup_for_governed_tools(tmp_path):
    _installed()
    with pytest.raises(ValueError, match="private startup"):
        _packet(tmp_path, private_startup=False)


def test_packet_requires_current_dedicated_worker_principal(tmp_path, monkeypatch):
    installed = _installed()
    packet = _packet(tmp_path)
    monkeypatch.setattr(installed.os, "geteuid", lambda: packet.policy.worker_uid + 100)
    with pytest.raises(ValueError, match="worker principal"):
        installed.InstalledAcpWorkerAdapter(packet)


def test_packet_digest_changes_with_host_security_identity(tmp_path):
    installed = _installed()
    packet = _packet(tmp_path)
    changed = installed.AcpInstalledHostPacket(
        policy=packet.policy,
        protocol_profile=packet.protocol_profile,
        native_profile=packet.native_profile,
        tool_gate=packet.tool_gate,
        environment={**dict(packet.environment), "PATH": "/bin:/usr/bin"},
        auth_mode=packet.auth_mode,
    )
    assert changed.digest != packet.digest


def test_acp_agent_surface_is_named_but_not_sealed_or_routable():
    from control_plane.executive_agent_capabilities import (
        ExecutionCapabilityRegistry,
        adapter_supports_execution_surface,
        is_sealed_worker_execution_surface,
    )

    registry = ExecutionCapabilityRegistry.load()
    assert adapter_supports_execution_surface("acp", "acp-agent")
    assert not is_sealed_worker_execution_surface("acp-agent")
    assert all(
        profile.execution_surface != "acp-agent"
        for profile in registry.profiles.values()
    )
    assert adapter_descriptor("acp").implemented is False


def _launch_evidence(packet, tmp_path):
    workspace = packet.policy.workspace_root / "job"
    run_dir = packet.policy.run_root / "run"
    workspace.mkdir()
    run_dir.mkdir()
    schema = run_dir / "result.schema.json"
    schema.write_text('{"type":"object"}', encoding="utf-8")
    isolation = "c" * 64
    spec = WorkerLaunchSpec(
        "RUN-1", "JOB-1", packet.policy.worker_id, workspace, run_dir,
        "harmless provider-free proof", schema, authorities=("READ", "RESEARCH"),
        model="fixture-model", expected_base_sha="d" * 40,
        expected_worker_uid=packet.policy.worker_uid,
        expected_worker_gid=packet.policy.worker_gid,
        isolation_manifest_sha256=isolation,
        secret_canary_verdict={"passed": True, "receipt_sha256": "e" * 64},
        require_secret_canary=True,
    )
    ref = WorkerProcessRef(
        run_id=spec.run_id, pid=1234, pgid=1234, process_start_identity="1.000001",
        boot_session_id="boot-1", launch_nonce="f" * 32, provider_session_id=None,
        stdout_path=str(run_dir / "stdout"), stderr_path=str(run_dir / "stderr"),
        result_path=str(run_dir / "result"), started_at="2026-10-03T12:00:00+00:00",
        binary=packet.native_profile.binary, base_sha=spec.expected_base_sha,
        session_id=1234, effective_uid=packet.policy.worker_uid,
        effective_gid=packet.policy.worker_gid, real_uid=packet.policy.worker_uid,
        real_gid=packet.policy.worker_gid,
    )
    import json
    native = {
        "schema_version": "mastermind.acp_native_launch/v1",
        "profile_id": packet.native_profile.profile_id,
        "binary_sha256": packet.native_profile.binary.sha256,
        "binary_version": packet.native_profile.binary.version,
        "argv_sha256": hashlib.sha256(
            json.dumps(packet.native_profile.argv, separators=(",", ":"), ensure_ascii=True).encode()
        ).hexdigest(),
        "environment_keys": sorted((*packet.environment, "HOME", "TMPDIR", "MMX_ACP_ATTEST_FD")),
        "credential_values_persisted": False,
        "process_identity": {
            "pid": ref.pid, "pgid": ref.pgid, "session_id": ref.session_id,
            "start_identity": ref.process_start_identity, "boot_id": ref.boot_session_id,
            "effective_uid": ref.effective_uid, "effective_gid": ref.effective_gid,
        },
    }
    return spec, ref, native


def test_complete_acp_attestation_uses_existing_executive_schema(tmp_path):
    installed = _installed()
    packet = _packet(tmp_path)
    spec, ref, native = _launch_evidence(packet, tmp_path)
    attestation = installed.complete_launch_attestation(packet, spec, ref, native)
    assert isinstance(attestation, LaunchAttestation)
    assert attestation.schema_version == LAUNCH_ATTESTATION_SCHEMA_VERSION
    assert attestation.isolation_manifest_sha256 == spec.isolation_manifest_sha256
    assert attestation.permission_profile_sha256 == packet.digest
    assert attestation.prompt_sha256 == hashlib.sha256(spec.prompt.encode()).hexdigest()
    assert attestation.worker_identity["effective_uid"] == packet.policy.worker_uid
    assert attestation.provider_home_identity["path"] == str(packet.policy.provider_home.resolve())
    assert attestation.secret_canary_verdict == spec.secret_canary_verdict
    assert attestation.process_identity["start_identity"] == ref.process_start_identity


def test_complete_acp_attestation_refuses_native_profile_or_process_drift(tmp_path):
    installed = _installed()
    packet = _packet(tmp_path)
    spec, ref, native = _launch_evidence(packet, tmp_path)
    for changed in (
        {**native, "profile_id": "other"},
        {**native, "process_identity": {**native["process_identity"], "pid": 9999}},
        {**native, "environment_keys": ["PATH"]},
    ):
        with pytest.raises(ValueError, match="native launch evidence"):
            installed.complete_launch_attestation(packet, spec, ref, changed)
