"""Fail-closed installed composition for the provider-neutral ACP adapter.

This module joins already-reviewed owners. It does not register a route, create a
broker, select a provider/model/account, or grant lifecycle authority. The current
ACP adapter descriptor remains unarmed until a separately qualified installed
host packet and release wave explicitly change that gate.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
import re
import time
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

from control_plane.codex_worker import (
    _assert_binary_unchanged,
    _path_identity,
    render_worker_sandbox_permission_overrides,
)
from control_plane.executive_agent_capabilities import (
    ACP_EXECUTION_SURFACE,
    ACP_PROVIDER_FREE_AUTH_REALM,
    ExecutionCapabilityRegistry,
)
from control_plane.executive_worker_broker import BrokerPolicy
from control_plane.worker_execution_contract import (
    BinaryAttestation,
    LAUNCH_ATTESTATION_SCHEMA_VERSION,
    LaunchAttestation,
    WorkerLaunchSpec,
    WorkerProcessRef,
)
from integrations.acp_worker.adapter import AcpWorkerAdapter
from integrations.acp_worker.native import AcpNativeProcessOwner, AcpNativeProfile
from integrations.acp_worker.tool_admission import AcpNativeToolGate
from integrations.acp_worker.turn import AcpProfile

_AUTH_NONE = "none"
_ACP_PROFILE_ID = "worker.acp.providerfree.readonly.v1"
_ACP_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
_CREDENTIAL_ENV = re.compile(
    r"(?:^|_)(?:API_?KEY|AUTH|BEARER|COOKIE|CREDENTIAL|PASSWORD|SECRET|TOKEN)(?:_|$)",
    re.IGNORECASE,
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _require_credentialless_provider_home(path: Path) -> None:
    try:
        entries = tuple(Path(path).iterdir())
    except OSError as exc:
        raise ValueError("ACP credentialless provider home is unavailable") from exc
    if entries:
        raise ValueError("ACP credentialless provider home must be empty")


@dataclasses.dataclass(frozen=True)
class AcpSeatbeltConfinement:
    """One immutable outer launcher plus one separately attested ACP payload."""

    sandbox_binary: BinaryAttestation
    payload_binary: BinaryAttestation
    payload_argv: tuple[str, ...]
    tool_bootstrap_path: str

    def __post_init__(self) -> None:
        if not isinstance(self.sandbox_binary, BinaryAttestation):
            raise ValueError("ACP Seatbelt launcher attestation is required")
        if not isinstance(self.payload_binary, BinaryAttestation):
            raise ValueError("ACP payload binary attestation is required")
        argv = tuple(self.payload_argv)
        if (
            not argv
            or len(argv) > 128
            or argv[0] != self.payload_binary.real_path
            or any(
                not isinstance(value, str)
                or not value
                or "\x00" in value
                or "\n" in value
                or "\r" in value
                for value in argv
            )
            or sum(len(value.encode("utf-8")) + 1 for value in argv) > 128 * 1024
        ):
            raise ValueError("ACP payload argv is outside the reviewed boundary")
        bootstrap = self.tool_bootstrap_path
        if (
            not isinstance(bootstrap, str)
            or not Path(bootstrap).is_absolute()
            or bootstrap not in argv[1:]
        ):
            raise ValueError("ACP tool bootstrap is outside the payload argv")
        object.__setattr__(self, "payload_argv", argv)

    @property
    def digest(self) -> str:
        return hashlib.sha256(_canonical({
            "schema": "mastermind.acp_seatbelt_confinement.v1",
            "sandbox_binary": dataclasses.asdict(self.sandbox_binary),
            "payload_binary": dataclasses.asdict(self.payload_binary),
            "payload_argv": list(self.payload_argv),
            "tool_bootstrap_path": self.tool_bootstrap_path,
        })).hexdigest()

    def render(
        self,
        spec: WorkerLaunchSpec,
        workspace: Any,
        run_dir: Any,
        provider_home: Any,
    ) -> tuple[str, ...]:
        authorities = set(spec.authorities)
        if spec.authority is not None:
            authorities.add(str(spec.authority).strip().upper())
        if not authorities or not authorities.issubset({"READ", "RESEARCH"}):
            raise ValueError("ACP first Seatbelt profile is read-only")
        _assert_binary_unchanged(self.sandbox_binary)
        _assert_binary_unchanged(self.payload_binary)
        workspace_path = Path(workspace).resolve(strict=True)
        run_path = Path(run_dir).resolve(strict=True)
        if workspace_path != Path(spec.workspace_path).resolve(strict=True):
            raise ValueError("ACP Seatbelt workspace identity drifted")
        if run_path != Path(spec.run_dir).resolve(strict=True):
            raise ValueError("ACP Seatbelt run identity drifted")
        policy = tuple(render_worker_sandbox_permission_overrides(
            spec,
            workspace_path,
            run_path,
            Path(provider_home),
        ))
        return (
            self.sandbox_binary.real_path,
            "sandbox",
            "-P",
            "mastermind_exec_read",
            "-C",
            str(workspace_path),
            *policy,
            "--",
            *self.payload_argv,
        )


def _security_projection(packet: "AcpInstalledHostPacket") -> dict[str, Any]:
    policy = packet.policy
    native = packet.native_profile
    gate = packet.tool_gate
    return {
        "schema": "mastermind.acp_installed_host_packet.v1",
        "auth_mode": packet.auth_mode,
        "execution_profile": {
            "profile_id": packet.execution_profile_id,
            "profile_digest": packet.execution_profile_digest,
            "capability_policy_version": packet.capability_policy_version,
            "capability_policy_digest": packet.capability_policy_digest,
        },
        "confinement_sha256": (
            packet.confinement.digest if packet.confinement is not None else None
        ),
        "broker_policy": {
            "control_uid": policy.control_uid,
            "worker_uid": policy.worker_uid,
            "worker_gid": policy.worker_gid,
            "worker_user": policy.worker_user,
            "worker_id": policy.worker_id,
            "workspace_root": str(policy.workspace_root.resolve(strict=True)),
            "run_root": str(policy.run_root.resolve(strict=True)),
            "provider_home": str(policy.provider_home.resolve(strict=True)),
            "allowed_supplementary_gids": sorted(policy.allowed_supplementary_gids),
            "require_secret_canary": policy.require_secret_canary,
        },
        "protocol_profile": dataclasses.asdict(packet.protocol_profile),
        "native_profile": {
            "profile_id": native.profile_id,
            "binary": dataclasses.asdict(native.binary),
            "argv": list(native.argv),
            "stdout_limit_bytes": native.stdout_limit_bytes,
            "stderr_limit_bytes": native.stderr_limit_bytes,
            "private_startup": native.private_startup,
            "allowed_environment_keys": list(native.allowed_environment_keys or ()),
        },
        "environment": dict(packet.environment),
        "tool_gate": {
            "projection_sha256": gate.projection_sha256,
            "artifact_sha256": gate.artifact_sha256,
            "tools": [dataclasses.asdict(item) for item in gate.tools],
            "artifacts": [list(row) for row in gate.artifacts],
        },
    }




def complete_launch_attestation(
    packet: "AcpInstalledHostPacket",
    spec: WorkerLaunchSpec,
    ref: WorkerProcessRef,
    native_attestation: Mapping[str, Any],
) -> LaunchAttestation:
    """Promote exact ACP owner evidence into the existing Executive receipt."""

    if (
        not isinstance(packet, AcpInstalledHostPacket)
        or not isinstance(spec, WorkerLaunchSpec)
        or not isinstance(ref, WorkerProcessRef)
        or not isinstance(native_attestation, Mapping)
        or spec.worker_id != packet.policy.worker_id
        or ref.run_id != spec.run_id
        or ref.base_sha != spec.expected_base_sha
        or spec.expected_worker_uid != packet.policy.worker_uid
        or spec.expected_worker_gid != packet.policy.worker_gid
        or ref.effective_uid != packet.policy.worker_uid
        or ref.real_uid != packet.policy.worker_uid
        or ref.effective_gid != packet.policy.worker_gid
        or ref.real_gid != packet.policy.worker_gid
    ):
        raise ValueError("ACP native launch evidence does not match the installed host packet")
    expected_identity = {
        "pid": ref.pid,
        "pgid": ref.pgid,
        "session_id": ref.session_id,
        "start_identity": ref.process_start_identity,
        "boot_id": ref.boot_session_id,
        "effective_uid": ref.effective_uid,
        "effective_gid": ref.effective_gid,
    }
    if packet.confinement is None:
        raise ValueError("ACP native launch evidence is missing Seatbelt confinement")
    expected_environment = sorted(
        (*packet.environment.keys(), "HOME", "TMPDIR", "MMX_ACP_ATTEST_FD")
    )
    expected_argv = packet.confinement.render(
        spec,
        spec.workspace_path.resolve(strict=True),
        spec.run_dir.resolve(strict=True),
        packet.policy.provider_home,
    )
    argv_sha256 = hashlib.sha256(
        json.dumps(
            expected_argv,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    if (
        native_attestation.get("schema_version") != "mastermind.acp_native_launch/v1"
        or native_attestation.get("profile_id") != packet.native_profile.profile_id
        or native_attestation.get("binary_sha256") != packet.native_profile.binary.sha256
        or native_attestation.get("binary_version") != packet.native_profile.binary.version
        or native_attestation.get("argv_sha256") != argv_sha256
        or native_attestation.get("rendered_argv") != list(expected_argv)
        or native_attestation.get("environment_keys") != expected_environment
        or native_attestation.get("credential_values_persisted") is not False
        or native_attestation.get("process_identity") != expected_identity
    ):
        raise ValueError("ACP native launch evidence changed before Executive binding")
    return LaunchAttestation(
        schema_version=LAUNCH_ATTESTATION_SCHEMA_VERSION,
        created_at=ref.started_at,
        executable_path=packet.native_profile.binary.real_path,
        binary=packet.native_profile.binary,
        rendered_argv=expected_argv,
        environment_keys=tuple(expected_environment),
        permission_profile_sha256=packet.digest,
        prompt_sha256=hashlib.sha256(spec.prompt.encode("utf-8")).hexdigest(),
        expected_base_sha=spec.expected_base_sha,
        observed_base_sha=ref.base_sha,
        workspace_identity={
            **_path_identity(spec.workspace_path),
            "git_head": ref.base_sha,
        },
        worker_identity={
            "requested_user": spec.worker_user,
            "observed_user": packet.policy.worker_user,
            "expected_uid": spec.expected_worker_uid,
            "expected_gid": spec.expected_worker_gid,
            "effective_uid": ref.effective_uid,
            "effective_gid": ref.effective_gid,
            "real_uid": ref.real_uid,
            "real_gid": ref.real_gid,
        },
        provider_home_identity=_path_identity(packet.policy.provider_home),
        secret_canary_verdict=spec.secret_canary_verdict,
        launch_nonce=ref.launch_nonce,
        process_identity={
            **expected_identity,
            "real_uid": ref.real_uid,
            "real_gid": ref.real_gid,
        },
        isolation_manifest_sha256=spec.isolation_manifest_sha256,
    )


@dataclasses.dataclass(frozen=True)
class AcpInstalledHostPacket:
    """Trusted, secret-free construction facts for one installed ACP broker.

    BrokerPolicy remains the filesystem/principal owner. AcpNativeProfile owns
    executable/startup identity. AcpNativeToolGate owns the immutable governed
    tool closure. This object only proves those owners agree on one provider-free
    installation generation.
    """

    policy: BrokerPolicy
    protocol_profile: AcpProfile
    native_profile: AcpNativeProfile
    tool_gate: AcpNativeToolGate
    environment: Mapping[str, str]
    auth_mode: str = _AUTH_NONE
    confinement: AcpSeatbeltConfinement | None = None
    execution_profile_id: str = dataclasses.field(init=False)
    execution_profile_digest: str = dataclasses.field(init=False)
    capability_policy_version: str = dataclasses.field(init=False)
    capability_policy_digest: str = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.policy, BrokerPolicy):
            raise ValueError("ACP installed packet requires BrokerPolicy")
        if not isinstance(self.protocol_profile, AcpProfile):
            raise ValueError("ACP installed packet requires protocol profile")
        if not isinstance(self.native_profile, AcpNativeProfile):
            raise ValueError("ACP installed packet requires native profile")
        if not isinstance(self.tool_gate, AcpNativeToolGate):
            raise ValueError("ACP installed packet requires governed tool gate")
        if self.auth_mode != _AUTH_NONE or self.protocol_profile.auth_method is not None:
            raise ValueError("ACP first installed profile must be provider-free")
        if self.policy.require_secret_canary is not True:
            raise ValueError("ACP installed packet requires the existing secret canary")
        if self.policy.allowed_supplementary_gids:
            raise ValueError("ACP provider-free worker may not inherit supplementary groups")
        if not self.native_profile.private_startup:
            raise ValueError("ACP governed tools require private startup")
        if self.confinement is not None:
            if not isinstance(self.confinement, AcpSeatbeltConfinement):
                raise ValueError("ACP Seatbelt confinement is invalid")
            if self.native_profile.binary != self.confinement.sandbox_binary:
                raise ValueError("ACP native profile does not bind the Seatbelt launcher")
            if self.native_profile.argv != (
                self.confinement.sandbox_binary.real_path,
                "sandbox",
            ):
                raise ValueError("ACP native profile does not bind the Seatbelt subcommand")
            artifact_paths = {path for path, _digest in self.tool_gate.artifacts}
            if self.confinement.tool_bootstrap_path not in artifact_paths:
                raise ValueError("ACP confined payload bootstrap is outside the tool gate")
        allowed = tuple(self.native_profile.allowed_environment_keys or ())
        raw = self.environment
        if not isinstance(raw, Mapping):
            raise ValueError("ACP installed environment must be a mapping")
        env: dict[str, str] = {}
        for key, value in raw.items():
            if (
                not isinstance(key, str)
                or not isinstance(value, str)
                or not key
                or "\x00" in key
                or "\x00" in value
                or _CREDENTIAL_ENV.search(key) is not None
                or key in {"HOME", "TMPDIR"}
            ):
                raise ValueError("ACP installed environment contains credential or reserved state")
            env[key] = value
        if set(env) != set(allowed):
            raise ValueError("ACP installed environment differs from the native profile ceiling")
        object.__setattr__(self, "environment", MappingProxyType(dict(env)))
        # Identity originates solely in the canonical capability registry, never
        # in a Job, incoming ACP message or caller-controlled payload.
        registry = ExecutionCapabilityRegistry.load()
        profile = registry.resolve(_ACP_PROFILE_ID)
        if (
            profile.execution_surface != ACP_EXECUTION_SURFACE
            or profile.auth_realm != ACP_PROVIDER_FREE_AUTH_REALM
            or profile.write_capable
        ):
            raise ValueError("ACP installed execution profile is not read-only")
        for name, value in (
            ("execution_profile_id", profile.profile_id),
            ("execution_profile_digest", profile.profile_digest),
            ("capability_policy_version", registry.policy_version),
            ("capability_policy_digest", registry.policy_digest),
        ):
            object.__setattr__(self, name, value)

    def security_projection(self) -> dict[str, Any]:
        """Return a fresh canonical projection; never expose mutable owner state."""
        return _security_projection(self)

    def mcp_runtime_overlay(
        self, spec: WorkerLaunchSpec, *, now_ms: int
    ) -> Mapping[str, Any]:
        """Bind MCP *client* cwd/env to one read-only admitted Attempt.

        This is not a server command/argv, a grant issuer or child startup.
        Installed launch must separately consume this exact snapshot.
        """
        registry = ExecutionCapabilityRegistry.load()
        profile = registry.resolve(_ACP_PROFILE_ID)
        if (
            registry.policy_version != self.capability_policy_version
            or registry.policy_digest != self.capability_policy_digest
            or profile.profile_id != self.execution_profile_id
            or profile.profile_digest != self.execution_profile_digest
            or profile.execution_surface != ACP_EXECUTION_SURFACE
            or profile.auth_realm != ACP_PROVIDER_FREE_AUTH_REALM
            or profile.write_capable
        ):
            raise ValueError("ACP installed capability policy changed")
        if not isinstance(spec, WorkerLaunchSpec):
            raise ValueError("ACP runtime overlay requires WorkerLaunchSpec")
        authorities = set(spec.authorities)
        if spec.authority is not None:
            authorities.add(str(spec.authority).strip().upper())
        if (
            not authorities
            or not authorities.issubset({"READ", "RESEARCH"})
            or spec.worker_id != self.policy.worker_id
            or spec.expected_worker_uid != self.policy.worker_uid
            or spec.expected_worker_gid != self.policy.worker_gid
            or type(spec.expected_base_sha) is not str
            or _GIT_SHA.fullmatch(spec.expected_base_sha) is None
            or any(
                type(token) is not str or _ACP_TOKEN.fullmatch(token) is None
                for token in (spec.run_id, spec.job_id, spec.worker_id)
            )
            or type(now_ms) is not int
            or not 0 <= now_ms <= 8_640_000_000_000_000
            or isinstance(spec.timeout_seconds, bool)
            or not isinstance(spec.timeout_seconds, (int, float))
            or not math.isfinite(spec.timeout_seconds)
            or not 0 < spec.timeout_seconds <= 86_400
        ):
            raise ValueError("ACP runtime overlay has invalid admission or scope")
        try:
            workspace_root = self.policy.workspace_root.resolve(strict=True)
            run_root = self.policy.run_root.resolve(strict=True)
            workspace = Path(spec.workspace_path).resolve(strict=True)
            run_dir = Path(spec.run_dir).resolve(strict=True)
        except (OSError, ValueError, RuntimeError):
            raise ValueError("ACP runtime overlay cannot resolve admitted paths") from None
        if (
            workspace == workspace_root
            or not workspace.is_relative_to(workspace_root)
            or run_dir == run_root
            or not run_dir.is_relative_to(run_root)
        ):
            raise ValueError("ACP runtime overlay is outside the admitted roots")
        deadline = now_ms + int(spec.timeout_seconds * 1000)
        if deadline > 8_640_000_000_000_000:
            raise ValueError("ACP runtime overlay exceeds deadline ceiling")
        return MappingProxyType({
            "cwd": str(workspace),
            "env": MappingProxyType({
                "MMX_ACP_WORKSPACE_PATH": str(workspace),
                "MMX_ACP_WORKSPACE_BASE_SHA": spec.expected_base_sha,
                "MMX_ACP_RUN_ID": spec.run_id,
                "MMX_ACP_JOB_ID": spec.job_id,
                "MMX_ACP_WORKER_ID": spec.worker_id,
                "MMX_ACP_DEADLINE_MS": str(deadline),
            }),
        })

    @property
    def digest(self) -> str:
        return hashlib.sha256(_canonical(self.security_projection())).hexdigest()


class InstalledAcpWorkerAdapter(AcpWorkerAdapter):
    """Reviewed installed ACP implementation over the existing common adapter."""

    adapter_id = "acp"

    def __init__(self, packet: AcpInstalledHostPacket) -> None:
        if not isinstance(packet, AcpInstalledHostPacket):
            raise TypeError("installed ACP adapter requires AcpInstalledHostPacket")
        if packet.confinement is None:
            raise ValueError("ACP installed adapter requires Seatbelt confinement")
        if (
            os.geteuid() != packet.policy.worker_uid
            or os.getegid() != packet.policy.worker_gid
        ):
            raise ValueError("ACP installed factory is not running as its worker principal")
        _require_credentialless_provider_home(packet.policy.provider_home)
        packet.tool_gate.verify_artifacts()
        confinement = packet.confinement

        def render_launch_argv(spec, workspace, run_dir):
            _require_credentialless_provider_home(packet.policy.provider_home)
            # This callback runs inside the original native owner BEFORE
            # subprocess creation. Revalidate the exact Attempt and current
            # capability generation here; a packet from an older policy or a
            # widened Job must never reach even the fixed Seatbelt launcher.
            # This is preflight only: the eventual DSH MCP host must still
            # consume the sealed per-Attempt cwd/env before tool discovery.
            overlay = packet.mcp_runtime_overlay(
                spec, now_ms=int(time.time() * 1000)
            )
            if overlay["cwd"] != str(Path(workspace).resolve(strict=True)):
                raise ValueError("ACP runtime overlay changed before launch")
            return confinement.render(
                spec,
                workspace,
                run_dir,
                packet.policy.provider_home,
            )

        def render_attempt_overlay(spec, workspace, run_dir):
            _require_credentialless_provider_home(packet.policy.provider_home)
            overlay = packet.mcp_runtime_overlay(
                spec, now_ms=int(time.time() * 1000)
            )
            if overlay["cwd"] != str(Path(workspace).resolve(strict=True)):
                raise ValueError("ACP native Attempt workspace changed")
            if Path(run_dir).resolve(strict=True) != Path(spec.run_dir).resolve(strict=True):
                raise ValueError("ACP native Attempt run identity changed")
            return overlay

        owner = AcpNativeProcessOwner(
            packet.native_profile,
            environment_loader=lambda: dict(packet.environment),
            tool_gate=packet.tool_gate,
            launch_argv_builder=render_launch_argv,
            attempt_overlay_builder=render_attempt_overlay,
        )
        self._installed_packet = packet
        self._native_owner = owner
        super().__init__(
            packet.protocol_profile,
            inspector=owner.inspector,
            open_run=owner.open_run,
        )

    def launch_attestation(self, ref: WorkerProcessRef) -> LaunchAttestation:
        run = self._run_for(ref)
        return complete_launch_attestation(
            self._installed_packet,
            run.spec,
            ref,
            run.resources.launch_attestation,
        )

    @property
    def installed_host_digest(self) -> str:
        return self._installed_packet.digest


__all__ = [
    "AcpInstalledHostPacket",
    "AcpSeatbeltConfinement",
    "InstalledAcpWorkerAdapter",
    "complete_launch_attestation",
]
