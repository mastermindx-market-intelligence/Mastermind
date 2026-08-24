"""Secret-free execution-capability grants for Executive worker placement.

The registry answers which *named, immutable execution surface* a routed Job
requires.  It owns no Job, Attempt, Worker, session, credential, process, MCP
server, plugin, or queue.  Executive Runtime remains the sole lifecycle owner.

The resulting profile and policy digests travel through Job constraints,
worker-capacity metadata, and the atomic ``JOB_CLAIMED`` receipt.  A configured
MCP server/plugin/skill therefore cannot become ambient authority merely because
it exists in a provider home: it must belong to the exact reviewed profile that
both the Job and claimed capacity name.  The operator-harness attestation layer
remains responsible for proving the provider process actually matches the grant.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from control_plane.operator_harness_contract import (
    CapabilityIdentity,
    CapabilityManifest,
    NativeHelperPolicy,
)


CAPABILITY_POLICY_SCHEMA = "mastermind.executive_agent_capabilities/v1"
DEFAULT_CAPABILITY_POLICY_PATH = (
    Path(__file__).resolve().parent.parent
    / "config"
    / "executive_agent_capabilities.json"
)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$")
_EXECUTION_SURFACES = frozenset({"codex-exec", "codex-app-server"})
_AUTH_REALMS = frozenset({"dedicated-worker-account"})
_SANDBOX_POLICIES = frozenset({"read-only", "workspace-write"})
_APPROVAL_POLICIES = frozenset({"never"})
_NETWORK_POLICIES = frozenset({"disabled"})
_PROFILE_KEYS = frozenset(
    {
        "enabled",
        "execution_surface",
        "auth_realm",
        "sandbox_policy",
        "approval_policy",
        "network_policy",
        "write_capable",
        "native_helper_policy",
        "skills",
        "mcp_servers",
        "plugins",
        "forbidden",
    }
)


class CapabilityPolicyError(RuntimeError):
    """The reviewed execution-capability policy is malformed or unsafe."""


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _identifier(value: Any, *, field: str) -> str:
    token = str(value or "").strip().lower()
    if _ID_RE.fullmatch(token) is None:
        raise CapabilityPolicyError(f"{field} must be a bounded lowercase identifier")
    return token


def _closed_choice(value: Any, *, field: str, choices: frozenset[str]) -> str:
    token = str(value or "").strip().lower()
    if token not in choices:
        raise CapabilityPolicyError(
            f"{field} must be one of {', '.join(sorted(choices))}"
        )
    return token


def _identities(value: Any, *, field: str, maximum: int = 32) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise CapabilityPolicyError(f"{field} must be a list with at most {maximum} items")
    result: list[str] = []
    for raw in value:
        item = _identifier(raw, field=field)
        if item in result:
            raise CapabilityPolicyError(f"{field} contains duplicate identity {item!r}")
        result.append(item)
    return tuple(sorted(result))


@dataclasses.dataclass(frozen=True)
class ExecutionCapabilityProfile:
    profile_id: str
    enabled: bool
    execution_surface: str
    auth_realm: str
    sandbox_policy: str
    approval_policy: str
    network_policy: str
    write_capable: bool
    native_helper_policy: NativeHelperPolicy
    skills: tuple[str, ...]
    mcp_servers: tuple[str, ...]
    plugins: tuple[str, ...]
    forbidden: tuple[str, ...]
    profile_digest: str

    @property
    def required_capability_names(self) -> tuple[str, ...]:
        return tuple(sorted((*self.skills, *self.mcp_servers, *self.plugins)))

    def capability_manifest(self, *, harness_binary_digest: str) -> CapabilityManifest:
        """Compile the profile into the existing OHF requested manifest.

        ``harness_binary_digest`` is supplied only at Attempt profile-seal time;
        the Git policy never pins a mutable host binary.  Capability kind is
        preserved so an MCP server cannot satisfy a plugin or skill grant merely
        by reusing its name.
        """

        binary_digest = str(harness_binary_digest or "").strip().lower()
        if re.fullmatch(r"[0-9a-f]{64}", binary_digest) is None:
            raise CapabilityPolicyError(
                "harness_binary_digest must be a lowercase SHA-256 digest"
            )
        required: list[CapabilityIdentity] = []
        for kind, names in (
            ("skill", self.skills),
            ("mcp_server", self.mcp_servers),
            ("plugin", self.plugins),
        ):
            for name in names:
                required.append(
                    CapabilityIdentity(
                        name=name,
                        kind=kind,
                        harness_binary_digest=binary_digest,
                        mcp_server_identity=(name if kind == "mcp_server" else None),
                    )
                )
        return CapabilityManifest(
            required=tuple(required),
            allowed_ambient=(),
            forbidden=self.forbidden,
            unclassified_policy="fail_closed_on_write",
        )


@dataclasses.dataclass(frozen=True)
class ExecutionCapabilityRegistry:
    policy_version: str
    lifecycle_authority: str
    production_armed: bool
    profiles: Mapping[str, ExecutionCapabilityProfile]
    policy_digest: str
    source_path: Path

    @classmethod
    def load(cls, path: str | Path | None = None) -> "ExecutionCapabilityRegistry":
        source = Path(path or DEFAULT_CAPABILITY_POLICY_PATH).expanduser().resolve(
            strict=True
        )
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CapabilityPolicyError(
                f"capability policy is unreadable: {type(exc).__name__}"
            ) from exc
        if not isinstance(raw, dict) or set(raw) != {
            "schema_version",
            "policy_version",
            "lifecycle_authority",
            "production_armed",
            "profiles",
        }:
            raise CapabilityPolicyError("capability policy root fields drifted")
        if raw.get("schema_version") != CAPABILITY_POLICY_SCHEMA:
            raise CapabilityPolicyError("capability policy schema_version is unsupported")
        if raw.get("lifecycle_authority") != "executive_os":
            raise CapabilityPolicyError(
                "capability policy must preserve Executive OS lifecycle authority"
            )
        if raw.get("production_armed") is not False:
            raise CapabilityPolicyError(
                "G0 capability policy must remain production_armed=false"
            )
        policy_version = _identifier(raw.get("policy_version"), field="policy_version")
        profiles_raw = raw.get("profiles")
        if not isinstance(profiles_raw, dict) or not profiles_raw or len(profiles_raw) > 32:
            raise CapabilityPolicyError("capability policy requires 1-32 profiles")
        profiles: dict[str, ExecutionCapabilityProfile] = {}
        for raw_id, value in profiles_raw.items():
            profile_id = _identifier(raw_id, field="profile_id")
            if not isinstance(value, dict) or set(value) != _PROFILE_KEYS:
                raise CapabilityPolicyError(
                    f"capability profile {profile_id!r} fields drifted"
                )
            enabled = value.get("enabled") is True
            if not isinstance(value.get("enabled"), bool):
                raise CapabilityPolicyError(f"profile {profile_id!r} enabled must be boolean")
            execution_surface = _closed_choice(
                value.get("execution_surface"),
                field=f"profiles.{profile_id}.execution_surface",
                choices=_EXECUTION_SURFACES,
            )
            auth_realm = _closed_choice(
                value.get("auth_realm"),
                field=f"profiles.{profile_id}.auth_realm",
                choices=_AUTH_REALMS,
            )
            sandbox_policy = _closed_choice(
                value.get("sandbox_policy"),
                field=f"profiles.{profile_id}.sandbox_policy",
                choices=_SANDBOX_POLICIES,
            )
            approval_policy = _closed_choice(
                value.get("approval_policy"),
                field=f"profiles.{profile_id}.approval_policy",
                choices=_APPROVAL_POLICIES,
            )
            network_policy = _closed_choice(
                value.get("network_policy"),
                field=f"profiles.{profile_id}.network_policy",
                choices=_NETWORK_POLICIES,
            )
            if not isinstance(value.get("write_capable"), bool):
                raise CapabilityPolicyError(
                    f"profile {profile_id!r} write_capable must be boolean"
                )
            write_capable = value["write_capable"]
            try:
                native_helper_policy = NativeHelperPolicy(
                    str(value.get("native_helper_policy") or "").strip().upper()
                )
            except ValueError as exc:
                raise CapabilityPolicyError(
                    f"profile {profile_id!r} native_helper_policy is unsupported"
                ) from exc
            skills = _identities(value.get("skills"), field=f"profiles.{profile_id}.skills")
            mcp_servers = _identities(
                value.get("mcp_servers"), field=f"profiles.{profile_id}.mcp_servers"
            )
            plugins = _identities(
                value.get("plugins"), field=f"profiles.{profile_id}.plugins"
            )
            forbidden = _identities(
                value.get("forbidden"), field=f"profiles.{profile_id}.forbidden"
            )
            required = set((*skills, *mcp_servers, *plugins))
            collision = sorted(required & set(forbidden))
            if collision:
                raise CapabilityPolicyError(
                    f"profile {profile_id!r} both requires and forbids: {', '.join(collision)}"
                )
            if execution_surface == "codex-exec" and (mcp_servers or plugins):
                raise CapabilityPolicyError(
                    f"profile {profile_id!r} cannot grant MCP/plugins to sealed codex-exec"
                )
            if write_capable and sandbox_policy != "workspace-write":
                raise CapabilityPolicyError(
                    f"profile {profile_id!r} write capability requires workspace-write"
                )
            if not write_capable and sandbox_policy != "read-only":
                raise CapabilityPolicyError(
                    f"profile {profile_id!r} read-only capability requires read-only sandbox"
                )
            if native_helper_policy is not NativeHelperPolicy.DISABLED:
                raise CapabilityPolicyError(
                    f"profile {profile_id!r} cannot enable native helpers before a proven ceiling"
                )
            normalized = {
                "profile_id": profile_id,
                "enabled": enabled,
                "execution_surface": execution_surface,
                "auth_realm": auth_realm,
                "sandbox_policy": sandbox_policy,
                "approval_policy": approval_policy,
                "network_policy": network_policy,
                "write_capable": write_capable,
                "native_helper_policy": native_helper_policy.value,
                "skills": list(skills),
                "mcp_servers": list(mcp_servers),
                "plugins": list(plugins),
                "forbidden": list(forbidden),
            }
            profiles[profile_id] = ExecutionCapabilityProfile(
                profile_id=profile_id,
                enabled=enabled,
                execution_surface=execution_surface,
                auth_realm=auth_realm,
                sandbox_policy=sandbox_policy,
                approval_policy=approval_policy,
                network_policy=network_policy,
                write_capable=write_capable,
                native_helper_policy=native_helper_policy,
                skills=skills,
                mcp_servers=mcp_servers,
                plugins=plugins,
                forbidden=forbidden,
                profile_digest=_digest(normalized),
            )
        normalized_policy = {
            "schema_version": CAPABILITY_POLICY_SCHEMA,
            "policy_version": policy_version,
            "lifecycle_authority": "executive_os",
            "production_armed": False,
            "profiles": {
                profile_id: {
                    "profile_digest": profile.profile_digest,
                    "enabled": profile.enabled,
                }
                for profile_id, profile in sorted(profiles.items())
            },
        }
        return cls(
            policy_version=policy_version,
            lifecycle_authority="executive_os",
            production_armed=False,
            profiles=profiles,
            policy_digest=_digest(normalized_policy),
            source_path=source,
        )

    def resolve(self, profile_id: str) -> ExecutionCapabilityProfile:
        token = _identifier(profile_id, field="profile_id")
        try:
            profile = self.profiles[token]
        except KeyError as exc:
            raise CapabilityPolicyError(f"unknown execution capability profile {token!r}") from exc
        if not profile.enabled:
            raise CapabilityPolicyError(f"execution capability profile {token!r} is disabled")
        return profile


__all__ = [
    "CAPABILITY_POLICY_SCHEMA",
    "DEFAULT_CAPABILITY_POLICY_PATH",
    "CapabilityPolicyError",
    "ExecutionCapabilityProfile",
    "ExecutionCapabilityRegistry",
]
