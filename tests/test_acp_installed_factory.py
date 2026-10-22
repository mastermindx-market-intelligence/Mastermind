from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
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


def _confined_packet(tmp_path: Path):
    installed = _installed()
    base = _packet(tmp_path)
    sandbox = tmp_path / "codex-sandbox"
    sandbox.write_bytes(b"sandbox")
    sandbox.chmod(0o500)
    sandbox_binary = _binary(sandbox)
    confinement = installed.AcpSeatbeltConfinement(
        sandbox_binary=sandbox_binary,
        payload_binary=base.native_profile.binary,
        payload_argv=base.native_profile.argv,
        tool_bootstrap_path=base.native_profile.argv[1],
    )
    native_profile = AcpNativeProfile(
        base.native_profile.profile_id,
        sandbox_binary,
        (sandbox_binary.real_path, "sandbox"),
        private_startup=True,
        allowed_environment_keys=base.native_profile.allowed_environment_keys,
    )
    return installed.AcpInstalledHostPacket(
        policy=base.policy,
        protocol_profile=base.protocol_profile,
        native_profile=native_profile,
        tool_gate=base.tool_gate,
        environment=base.environment,
        auth_mode=base.auth_mode,
        confinement=confinement,
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
    packet = _confined_packet(tmp_path)
    adapter = construct_reviewed_adapter("acp", packet)
    assert type(adapter) is installed.InstalledAcpWorkerAdapter
    assert isinstance(adapter, AcpWorkerAdapter)
    assert adapter.adapter_id == "acp"
    assert bind_reviewed_adapter(adapter, "acp").adapter_id == "acp"
    assert adapter.installed_host_digest == packet.digest
    with pytest.raises(TypeError):
        construct_reviewed_adapter("acp", packet, open_run=lambda _spec: None)


def test_installed_adapter_refuses_missing_seatbelt_confinement(tmp_path):
    installed = _installed()
    with pytest.raises(ValueError, match="Seatbelt confinement"):
        installed.InstalledAcpWorkerAdapter(_packet(tmp_path))


def test_packet_refuses_confinement_bootstrap_outside_tool_gate(tmp_path):
    installed = _installed()
    base = _packet(tmp_path)
    sandbox = tmp_path / "codex-sandbox-unbound"
    sandbox.write_bytes(b"sandbox")
    sandbox.chmod(0o500)
    sandbox_binary = _binary(sandbox)
    confinement = installed.AcpSeatbeltConfinement(
        sandbox_binary=sandbox_binary,
        payload_binary=base.native_profile.binary,
        payload_argv=(base.native_profile.binary.real_path, "/tmp/not-admitted.mjs"),
        tool_bootstrap_path="/tmp/not-admitted.mjs",
    )
    native_profile = AcpNativeProfile(
        base.native_profile.profile_id,
        sandbox_binary,
        (sandbox_binary.real_path, "sandbox"),
        private_startup=True,
        allowed_environment_keys=base.native_profile.allowed_environment_keys,
    )
    with pytest.raises(ValueError, match="bootstrap"):
        installed.AcpInstalledHostPacket(
            policy=base.policy,
            protocol_profile=base.protocol_profile,
            native_profile=native_profile,
            tool_gate=base.tool_gate,
            environment=base.environment,
            auth_mode=base.auth_mode,
            confinement=confinement,
        )


def test_provider_free_packet_refuses_credential_bearing_home(tmp_path):
    installed = _installed()
    packet = _confined_packet(tmp_path)
    (packet.policy.provider_home / "auth.json").write_text("secret", encoding="utf-8")
    with pytest.raises(ValueError, match="credentialless provider home"):
        installed.InstalledAcpWorkerAdapter(packet)


def test_provider_home_drift_refuses_again_at_launch_boundary(tmp_path):
    installed = _installed()
    packet = _confined_packet(tmp_path)
    adapter = installed.InstalledAcpWorkerAdapter(packet)
    spec = _confined_spec(packet, tmp_path)
    (packet.policy.provider_home / "late-auth.json").write_text("secret", encoding="utf-8")
    with pytest.raises(ValueError, match="credentialless provider home"):
        adapter._native_owner._launch_argv(
            spec,
            spec.workspace_path.resolve(strict=True),
            spec.run_dir.resolve(strict=True),
        )


def test_native_launch_preflight_consumes_current_attempt_binding(tmp_path, monkeypatch):
    import integrations.acp_worker.installed as installed

    packet = _confined_packet(tmp_path)
    spec = _confined_spec(packet, tmp_path)
    adapter = installed.InstalledAcpWorkerAdapter(packet)
    workspace = spec.workspace_path.resolve(strict=True)
    run_dir = spec.run_dir.resolve(strict=True)
    expected = packet.confinement.render(
        spec, workspace, run_dir, packet.policy.provider_home
    )
    assert adapter._native_owner._launch_argv(spec, workspace, run_dir) == expected
    for changed in (
        dataclasses.replace(spec, authorities=("READ", "WRITE_BRANCH")),
        dataclasses.replace(spec, worker_id="other-worker"),
    ):
        with pytest.raises(ValueError, match="ACP runtime overlay"):
            adapter._native_owner._launch_argv(changed, workspace, run_dir)

    original_load = installed.ExecutionCapabilityRegistry.load
    class Drifted:
        policy_version = "drifted"
        policy_digest = "f" * 64
        profiles = original_load().profiles
        def resolve(self, profile_id):
            return self.profiles[profile_id]

    monkeypatch.setattr(
        installed.ExecutionCapabilityRegistry, "load",
        classmethod(lambda cls, *args, **kwargs: Drifted()),
    )
    with pytest.raises(ValueError, match="ACP installed capability policy changed"):
        adapter._native_owner._launch_argv(spec, workspace, run_dir)


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
    packet = _confined_packet(tmp_path)
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
        confinement=packet.confinement,
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
    profile = registry.resolve("worker.acp.providerfree.readonly.v1")
    assert profile.execution_surface == "acp-agent"
    assert profile.write_capable is False
    assert adapter_descriptor("acp").implemented is False


def _launch_evidence(packet, tmp_path):
    spec = _confined_spec(packet, tmp_path)
    ref = WorkerProcessRef(
        run_id=spec.run_id, pid=1234, pgid=1234, process_start_identity="1.000001",
        boot_session_id="boot-1", launch_nonce="f" * 32, provider_session_id=None,
        stdout_path=str(spec.run_dir / "stdout"), stderr_path=str(spec.run_dir / "stderr"),
        result_path=str(spec.run_dir / "result"), started_at="2026-10-03T12:00:00+00:00",
        binary=packet.native_profile.binary, base_sha=spec.expected_base_sha,
        session_id=1234, effective_uid=packet.policy.worker_uid,
        effective_gid=packet.policy.worker_gid, real_uid=packet.policy.worker_uid,
        real_gid=packet.policy.worker_gid,
    )
    import json
    assert packet.confinement is not None
    rendered = packet.confinement.render(
        spec,
        spec.workspace_path.resolve(strict=True),
        spec.run_dir.resolve(strict=True),
        packet.policy.provider_home,
    )
    native = {
        "schema_version": "mastermind.acp_native_launch/v1",
        "profile_id": packet.native_profile.profile_id,
        "binary_sha256": packet.native_profile.binary.sha256,
        "binary_version": packet.native_profile.binary.version,
        "argv_sha256": hashlib.sha256(
            json.dumps(rendered, separators=(",", ":"), ensure_ascii=True).encode()
        ).hexdigest(),
        "rendered_argv": list(rendered),
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
    packet = _confined_packet(tmp_path)
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
    assert tuple(attestation.rendered_argv) == tuple(native["rendered_argv"])


def test_complete_acp_attestation_refuses_native_profile_or_process_drift(tmp_path):
    installed = _installed()
    packet = _confined_packet(tmp_path)
    spec, ref, native = _launch_evidence(packet, tmp_path)
    altered_argv = list(native["rendered_argv"])
    altered_argv[-1] = "/tmp/not-admitted.mjs"
    altered_hash = hashlib.sha256(
        json.dumps(tuple(altered_argv), separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    for changed in (
        {**native, "profile_id": "other"},
        {**native, "process_identity": {**native["process_identity"], "pid": 9999}},
        {**native, "environment_keys": ["PATH"]},
        {**native, "rendered_argv": altered_argv, "argv_sha256": altered_hash},
    ):
        with pytest.raises(ValueError, match="native launch evidence"):
            installed.complete_launch_attestation(packet, spec, ref, changed)


def _confined_spec(packet, tmp_path):
    from control_plane.executive_supervisor import ExecutiveSupervisor

    workspace = packet.policy.workspace_root / "confined-job"
    run_dir = packet.policy.run_root / "confined-run"
    workspace.mkdir()
    run_dir.mkdir()
    schema = run_dir / "result.schema.json"
    schema.write_text('{"type":"object"}', encoding="utf-8")
    denied, manifest, manifest_sha = ExecutiveSupervisor._isolation_manifest(
        (packet.policy.workspace_root, packet.policy.run_root),
        workspace=workspace,
        run_dir=run_dir,
    )
    return WorkerLaunchSpec(
        "RUN-C", "JOB-C", packet.policy.worker_id, workspace, run_dir,
        "confined provider-free proof", schema,
        authorities=("READ", "RESEARCH"), model="fixture-model",
        expected_base_sha="d" * 40,
        expected_worker_uid=packet.policy.worker_uid,
        expected_worker_gid=packet.policy.worker_gid,
        isolation_roots=(packet.policy.workspace_root, packet.policy.run_root),
        isolation_denied_paths=denied,
        isolation_manifest=manifest,
        isolation_manifest_sha256=manifest_sha,
        forbidden_paths=(tmp_path / "controller.sqlite3",),
        secret_canary_verdict={"passed": True, "receipt_sha256": "e" * 64},
        require_secret_canary=True,
    )


def test_seatbelt_confinement_renders_existing_readonly_policy_around_fixed_payload(tmp_path):
    installed = _installed()
    packet = _packet(tmp_path)
    sandbox = tmp_path / "codex-sandbox"
    sandbox.write_bytes(b"sandbox")
    sandbox.chmod(0o500)
    confinement = installed.AcpSeatbeltConfinement(
        sandbox_binary=_binary(sandbox),
        payload_binary=packet.native_profile.binary,
        payload_argv=packet.native_profile.argv,
        tool_bootstrap_path=packet.native_profile.argv[1],
    )
    spec = _confined_spec(packet, tmp_path)
    rendered = confinement.render(
        spec,
        spec.workspace_path.resolve(),
        spec.run_dir.resolve(),
        packet.policy.provider_home,
    )
    from control_plane.codex_worker import render_worker_sandbox_permission_overrides

    expected_policy = tuple(render_worker_sandbox_permission_overrides(
        spec,
        spec.workspace_path.resolve(),
        spec.run_dir.resolve(),
        packet.policy.provider_home.resolve(),
    ))
    assert rendered[:6] == (
        confinement.sandbox_binary.real_path,
        "sandbox",
        "-P",
        "mastermind_exec_read",
        "-C",
        str(spec.workspace_path.resolve()),
    )
    assert rendered[6:6 + len(expected_policy)] == expected_policy
    assert rendered[6 + len(expected_policy)] == "--"
    assert rendered[-len(confinement.payload_argv):] == confinement.payload_argv
    assert any("network.enabled=false" in item for item in rendered)


def test_seatbelt_confinement_refuses_write_authority_and_payload_drift(tmp_path):
    installed = _installed()
    packet = _packet(tmp_path)
    sandbox = tmp_path / "codex-sandbox"
    sandbox.write_bytes(b"sandbox")
    sandbox.chmod(0o500)
    confinement = installed.AcpSeatbeltConfinement(
        sandbox_binary=_binary(sandbox),
        payload_binary=packet.native_profile.binary,
        payload_argv=packet.native_profile.argv,
        tool_bootstrap_path=packet.native_profile.argv[1],
    )
    spec = _confined_spec(packet, tmp_path)
    write_spec = dataclasses.replace(spec, authorities=("READ", "WRITE_BRANCH"))
    with pytest.raises(ValueError, match="read-only"):
        confinement.render(
            write_spec,
            write_spec.workspace_path.resolve(),
            write_spec.run_dir.resolve(),
            packet.policy.provider_home,
        )
    changed_payload = installed.AcpSeatbeltConfinement(
        sandbox_binary=confinement.sandbox_binary,
        payload_binary=confinement.payload_binary,
        payload_argv=(confinement.payload_binary.real_path, "/tmp/not-admitted.mjs"),
        tool_bootstrap_path="/tmp/not-admitted.mjs",
    )
    assert changed_payload.digest != confinement.digest


def test_packet_binds_current_acp_policy_generation_without_caller_strings(tmp_path):
    packet = _confined_packet(tmp_path)
    from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry

    registry = ExecutionCapabilityRegistry.load()
    profile = registry.resolve("worker.acp.providerfree.readonly.v1")
    assert packet.execution_profile_id == profile.profile_id
    assert packet.execution_profile_digest == profile.profile_digest
    assert packet.capability_policy_version == registry.policy_version
    assert packet.capability_policy_digest == registry.policy_digest
    projection = installed_projection = packet.security_projection()
    assert projection["execution_profile"] == {
        "profile_id": profile.profile_id,
        "profile_digest": profile.profile_digest,
        "capability_policy_version": registry.policy_version,
        "capability_policy_digest": registry.policy_digest,
    }
    assert packet.digest == hashlib.sha256(
        json.dumps(
            installed_projection,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def test_runtime_overlay_binds_exact_attempt_workspace_without_static_grant_drift(tmp_path):
    packet = _confined_packet(tmp_path)
    spec = _confined_spec(packet, tmp_path)
    overlay = packet.mcp_runtime_overlay(spec, now_ms=1_800_000_000_000)
    assert overlay["cwd"] == str(spec.workspace_path.resolve(strict=True))
    assert overlay["env"] == {
        "MMX_ACP_WORKSPACE_PATH": str(spec.workspace_path.resolve(strict=True)),
        "MMX_ACP_WORKSPACE_BASE_SHA": spec.expected_base_sha,
        "MMX_ACP_RUN_ID": spec.run_id,
        "MMX_ACP_JOB_ID": spec.job_id,
        "MMX_ACP_WORKER_ID": spec.worker_id,
        "MMX_ACP_DEADLINE_MS": str(
            1_800_000_000_000 + int(spec.timeout_seconds * 1000)
        ),
    }
    assert "command" not in overlay
    assert "args" not in overlay
    assert "serverName" not in overlay


def test_runtime_overlay_reaches_existing_workspace_read_gateway(tmp_path):
    """Owner-owned Attempt fields drive the real read/search gateway, not Jobs."""
    from integrations.acp_worker.workspace_read_mcp import WorkspaceReadGateway

    packet = _confined_packet(tmp_path)
    spec = _confined_spec(packet, tmp_path)
    (spec.workspace_path / "memo.txt").write_text(
        "bounded workspace contents\nalpha needle\n", encoding="utf-8"
    )
    overlay = packet.mcp_runtime_overlay(spec, now_ms=1_800_000_000_000)
    with pytest.raises(TypeError):
        overlay["cwd"] = "/tmp/foreign"
    with pytest.raises(TypeError):
        overlay["env"]["MMX_ACP_WORKER_ID"] = "foreign"
    assert set(overlay) == {"cwd", "env"}
    gateway = WorkspaceReadGateway.from_environment(overlay["env"])
    try:
        observed = gateway.call("read_file", {"relative_path": "memo.txt"})
        assert observed["ok"] is True
        assert observed["data"]["run_id"] == spec.run_id
        assert observed["data"]["job_id"] == spec.job_id
        assert observed["data"]["worker_id"] == spec.worker_id
        assert "alpha needle" in observed["data"]["content"]
        matched = gateway.call(
            "search_text", {"relative_path": "memo.txt", "query": "needle"}
        )
        assert matched["ok"] is True
        assert len(matched["data"]["matches"]) == 1
        refused = gateway.call("read_file", {"relative_path": "../outside"})
        assert refused["ok"] is False
    finally:
        gateway.close()


def test_attempt_overlay_drives_real_mcp_stdio_process(tmp_path):
    """Provider-free SDK subprocess consumes the trusted per-Attempt overlay."""
    import asyncio
    import importlib.util
    import sys
    import time

    if importlib.util.find_spec("mcp") is None:
        pytest.skip("pinned official MCP SDK absent; stdio proof not executed")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    packet = _confined_packet(tmp_path)
    spec = _confined_spec(packet, tmp_path)
    (spec.workspace_path / "memo.txt").write_text(
        "read from admitted attempt\nunique-needle\n", encoding="utf-8"
    )
    overlay = packet.mcp_runtime_overlay(
        spec, now_ms=int(time.time() * 1000)
    )
    launcher = Path(__file__).resolve().parents[1] / "scripts/acp_workspace_read_mcp.py"

    async def scenario():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-B", str(launcher)],
            cwd=overlay["cwd"],
            env={**dict(overlay["env"]), "PATH": "/usr/bin:/bin"},
        )
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                await client.initialize()
                tools = await client.list_tools()
                assert [tool.name for tool in tools.tools] == [
                    "read_file", "search_text"
                ]
                read = await client.call_tool(
                    "read_file", {"relative_path": "memo.txt"}
                )
                assert read.isError is False
                result = json.loads(read.content[0].text)
                assert result["data"]["run_id"] == spec.run_id
                assert result["data"]["job_id"] == spec.job_id
                assert result["data"]["worker_id"] == spec.worker_id
                assert "unique-needle" in result["data"]["content"]
                search = await client.call_tool(
                    "search_text",
                    {"relative_path": "memo.txt", "query": "unique-needle"},
                )
                assert search.isError is False
                assert len(
                    json.loads(search.content[0].text)["data"]["matches"]
                ) == 1
                denied = await client.call_tool(
                    "read_file", {"relative_path": "../not-allowed"}
                )
                assert denied.isError is True

    asyncio.run(scenario())


def test_runtime_overlay_refuses_expired_or_foreign_attempt_identity(tmp_path):
    packet = _confined_packet(tmp_path)
    spec = _confined_spec(packet, tmp_path)
    for changed in (
        dataclasses.replace(spec, job_id="other\njob"),
        dataclasses.replace(spec, worker_id="foreign"),
        dataclasses.replace(spec, timeout_seconds=float("inf")),
        dataclasses.replace(spec, expected_worker_gid=spec.expected_worker_gid + 1),
        dataclasses.replace(spec, authorities=("READ", "DELETE_FILE")),
    ):
        with pytest.raises(ValueError, match="ACP runtime overlay"):
            packet.mcp_runtime_overlay(changed, now_ms=1_800_000_000_000)
    with pytest.raises(ValueError, match="ACP runtime overlay"):
        packet.mcp_runtime_overlay(spec, now_ms=8_640_000_000_000_000)


def test_runtime_overlay_refuses_write_or_scope_drift(tmp_path):
    packet = _confined_packet(tmp_path)
    spec = _confined_spec(packet, tmp_path)
    import dataclasses

    for changed in (
        dataclasses.replace(spec, authorities=("READ", "WRITE_BRANCH")),
        dataclasses.replace(spec, worker_id="different-worker"),
        dataclasses.replace(spec, expected_base_sha=None),
    ):
        with pytest.raises(ValueError, match="ACP runtime overlay"):
            packet.mcp_runtime_overlay(changed, now_ms=1_800_000_000_000)

    outside = tmp_path / "outside-workspace"
    outside.mkdir(mode=0o700)
    with pytest.raises(ValueError, match="ACP runtime overlay"):
        packet.mcp_runtime_overlay(
            dataclasses.replace(spec, workspace_path=outside),
            now_ms=1_800_000_000_000,
        )


def test_runtime_overlay_refuses_policy_drift(tmp_path, monkeypatch):
    packet = _confined_packet(tmp_path)
    spec = _confined_spec(packet, tmp_path)
    import integrations.acp_worker.installed as installed

    original = installed.ExecutionCapabilityRegistry.load

    class Drifted:
        policy_version = "drifted-policy"
        policy_digest = "f" * 64
        profiles = original().profiles
        def resolve(self, profile_id):
            return self.profiles[profile_id]

    monkeypatch.setattr(
        installed.ExecutionCapabilityRegistry,
        "load",
        classmethod(lambda cls, *args, **kwargs: Drifted()),
    )
    with pytest.raises(ValueError, match="ACP installed capability policy changed"):
        packet.mcp_runtime_overlay(spec, now_ms=1_800_000_000_000)
