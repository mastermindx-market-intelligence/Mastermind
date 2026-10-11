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
import os
import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from control_plane.codex_worker import _path_identity
from control_plane.executive_worker_broker import BrokerPolicy
from control_plane.worker_execution_contract import (
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


def _security_projection(packet: "AcpInstalledHostPacket") -> dict[str, Any]:
    policy = packet.policy
    native = packet.native_profile
    gate = packet.tool_gate
    return {
        "schema": "mastermind.acp_installed_host_packet.v1",
        "auth_mode": packet.auth_mode,
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
    expected_environment = sorted(
        (*packet.environment.keys(), "HOME", "TMPDIR", "MMX_ACP_ATTEST_FD")
    )
    argv_sha256 = hashlib.sha256(
        json.dumps(
            packet.native_profile.argv,
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
        rendered_argv=packet.native_profile.argv,
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

    @property
    def digest(self) -> str:
        return hashlib.sha256(_canonical(_security_projection(self))).hexdigest()


class InstalledAcpWorkerAdapter(AcpWorkerAdapter):
    """Reviewed installed ACP implementation over the existing common adapter."""

    adapter_id = "acp"

    def __init__(self, packet: AcpInstalledHostPacket) -> None:
        if not isinstance(packet, AcpInstalledHostPacket):
            raise TypeError("installed ACP adapter requires AcpInstalledHostPacket")
        if (
            os.geteuid() != packet.policy.worker_uid
            or os.getegid() != packet.policy.worker_gid
        ):
            raise ValueError("ACP installed factory is not running as its worker principal")
        try:
            entries = tuple(packet.policy.provider_home.iterdir())
        except OSError as exc:
            raise ValueError("ACP credentialless provider home is unavailable") from exc
        if entries:
            raise ValueError("ACP credentialless provider home must be empty")
        packet.tool_gate.verify_artifacts()
        owner = AcpNativeProcessOwner(
            packet.native_profile,
            environment_loader=lambda: dict(packet.environment),
            tool_gate=packet.tool_gate,
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
    "InstalledAcpWorkerAdapter",
    "complete_launch_attestation",
]
