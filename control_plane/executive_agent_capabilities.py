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
from urllib.parse import urlsplit

from control_plane.operator_harness_contract import (
    CapabilityIdentity,
    CapabilityManifest,
    NativeHelperPolicy,
)


CAPABILITY_POLICY_SCHEMA = "mastermind.executive_agent_capabilities/v2"
DEFAULT_CAPABILITY_POLICY_PATH = (
    Path(__file__).resolve().parent.parent
    / "config"
    / "executive_agent_capabilities.json"
)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$")
_CONFIG_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_EXECUTION_SURFACES = frozenset({"codex-exec", "codex-app-server"})
_AUTH_REALMS = frozenset({"dedicated-worker-account"})
_SANDBOX_POLICIES = frozenset({"read-only", "workspace-write"})
_APPROVAL_POLICIES = frozenset({"never"})
_NETWORK_POLICIES = frozenset({"disabled"})
_MCP_TRANSPORTS = frozenset({"streamable-http"})
_MCP_AUTH_STATUSES = frozenset(
    {"unsupported", "notLoggedIn", "bearerToken", "oAuth"}
)
_MCP_APPROVAL_MODES = frozenset({"approve"})
_MCP_KEYS = frozenset(
    {
        "config_name",
        "transport",
        "url",
        "required",
        "auth_status",
        "server_identity",
        "server_version",
        "enabled_tools",
        "default_tools_approval_mode",
        "tool_schema_digest",
    }
)
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


def _config_name(value: Any, *, field: str) -> str:
    token = str(value or "").strip()
    if _CONFIG_NAME_RE.fullmatch(token) is None:
        raise CapabilityPolicyError(
            f"{field} must be a bounded App Server configuration name"
        )
    return token


def _digest_value(value: Any, *, field: str) -> str:
    token = str(value or "").strip().lower()
    if _DIGEST_RE.fullmatch(token) is None:
        raise CapabilityPolicyError(f"{field} must be a lowercase SHA-256 digest")
    return token


def _https_url(value: Any, *, field: str) -> str:
    token = str(value or "").strip()
    try:
        parsed = urlsplit(token)
        port = parsed.port
    except ValueError as exc:
        raise CapabilityPolicyError(f"{field} is not a valid HTTPS URL") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.query
        or port not in (None, 443)
    ):
        raise CapabilityPolicyError(
            f"{field} must be an HTTPS origin/path without credentials, query, or fragment"
        )
    return token


_BASE_APP_SERVER_OVERRIDES = (
    "mcp_servers={}",
    "plugins={}",
    "skills.config=[]",
    "agents.enabled=false",
    "features.apps=false",
    "features.plugins=false",
    "features.remote_plugin=false",
    "features.enable_mcp_apps=false",
    "features.auth_elicitation=false",
    "features.tool_call_mcp_elicitation=false",
    "features.mcp_2026_07_28=false",
    "features.multi_agent=false",
    "features.multi_agent_v2=false",
)


def _toml_string(value: str) -> str:
    """Encode one reviewed value for Codex's ``-c key=value`` TOML parser."""

    return json.dumps(value, ensure_ascii=True)


@dataclasses.dataclass(frozen=True)
class McpServerGrant:
    """One exact, secret-free MCP server/tool grant.

    The grant is configuration and attestation policy only. OAuth enrollment
    remains an action-time operation in the dedicated worker realm and no token
    value can appear here.
    """

    capability_id: str
    config_name: str
    transport: str
    url: str
    required: bool
    auth_status: str
    server_identity: str
    server_version: str
    enabled_tools: tuple[str, ...]
    default_tools_approval_mode: str
    tool_schema_digest: str
    grant_digest: str

    def config_projection(self) -> dict[str, object]:
        return {
            "default_tools_approval_mode": self.default_tools_approval_mode,
            "enabled": True,
            "enabled_tools": list(self.enabled_tools),
            "required": self.required,
            "url": self.url,
        }

    def config_overrides(self) -> tuple[str, ...]:
        prefix = f"mcp_servers.{self.config_name}"
        tools = json.dumps(list(self.enabled_tools), ensure_ascii=True, separators=(",", ":"))
        return (
            f"{prefix}.url={_toml_string(self.url)}",
            f"{prefix}.required={'true' if self.required else 'false'}",
            f"{prefix}.enabled=true",
            f"{prefix}.enabled_tools={tools}",
            (
                f"{prefix}.default_tools_approval_mode="
                f"{_toml_string(self.default_tools_approval_mode)}"
            ),
        )


_FEATURE_PROJECTION_KEYS = (
    "apps",
    "auth_elicitation",
    "enable_mcp_apps",
    "mcp_2026_07_28",
    "multi_agent",
    "multi_agent_v2",
    "plugins",
    "remote_plugin",
    "tool_call_mcp_elicitation",
)


def app_server_security_config_projection(
    config: Mapping[str, Any] | None,
) -> dict[str, object]:
    """Project only the fields that can widen this G3 process.

    Credential values, account metadata and unrelated UI settings are never
    copied into the projection. Malformed shapes remain distinguishable from
    the expected closed shape and therefore produce a different digest.
    """

    root = config if isinstance(config, Mapping) else {}
    agents = root.get("agents")
    features = root.get("features")
    skills = root.get("skills")
    plugins = root.get("plugins")
    raw_servers = root.get("mcp_servers") or root.get("mcpServers")
    projected_servers: dict[str, object] = {}
    if isinstance(raw_servers, Mapping):
        for raw_name, raw_value in sorted(raw_servers.items(), key=lambda row: str(row[0])):
            name = str(raw_name)
            if not isinstance(raw_value, Mapping):
                projected_servers[name] = {"invalid": True}
                continue
            tools = raw_value.get("enabled_tools")
            projected_servers[name] = {
                "default_tools_approval_mode": raw_value.get(
                    "default_tools_approval_mode"
                ),
                "enabled": raw_value.get("enabled"),
                "enabled_tools": (
                    sorted(str(item) for item in tools)
                    if isinstance(tools, list)
                    else None
                ),
                "required": raw_value.get("required"),
                "url": raw_value.get("url"),
            }
    elif raw_servers is not None:
        projected_servers["__invalid__"] = {"invalid": True}

    if isinstance(plugins, Mapping):
        plugin_projection: object = {
            str(name): True for name in sorted(plugins, key=str)
        }
    else:
        plugin_projection = {"__invalid__": True}

    skill_config = skills.get("config") if isinstance(skills, Mapping) else None
    return {
        "agents": {
            "enabled": agents.get("enabled") if isinstance(agents, Mapping) else None
        },
        "features": {
            key: features.get(key) if isinstance(features, Mapping) else None
            for key in _FEATURE_PROJECTION_KEYS
        },
        "mcp_servers": projected_servers,
        "plugins": plugin_projection,
        "skills": {
            "config": list(skill_config) if isinstance(skill_config, list) else None
        },
    }


def app_server_security_config_digest(config: Mapping[str, Any] | None) -> str:
    return _digest(app_server_security_config_projection(config))


def observed_mcp_tool_schema_digest(row: Mapping[str, Any]) -> str | None:
    """Digest the effective allow-listed tool contracts, excluding prose.

    Descriptions and titles can change without changing authority. Tool names,
    input/output schemas and security annotations cannot.
    """

    tools = row.get("tools")
    if not isinstance(tools, Mapping):
        return None
    normalized: list[dict[str, object]] = []
    for raw_name, raw_tool in sorted(tools.items(), key=lambda item: str(item[0])):
        if not isinstance(raw_tool, Mapping):
            return None
        name = str(raw_tool.get("name") or raw_name).strip()
        input_schema = raw_tool.get("inputSchema")
        if not name or not isinstance(input_schema, Mapping):
            return None
        output_schema = raw_tool.get("outputSchema")
        annotations = raw_tool.get("annotations")
        if annotations is not None and not isinstance(annotations, Mapping):
            return None
        if output_schema is not None and not isinstance(output_schema, Mapping):
            return None
        normalized.append(
            {
                "annotations": dict(annotations) if isinstance(annotations, Mapping) else None,
                "input_schema": dict(input_schema),
                "name": name,
                "output_schema": (
                    dict(output_schema) if isinstance(output_schema, Mapping) else None
                ),
            }
        )
    return _digest(normalized)


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
    mcp_server_grants: tuple[McpServerGrant, ...]
    plugins: tuple[str, ...]
    forbidden: tuple[str, ...]
    profile_digest: str

    @property
    def required_capability_names(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                (
                    *self.skills,
                    *(grant.config_name for grant in self.mcp_server_grants),
                    *self.plugins,
                )
            )
        )

    @property
    def mcp_servers(self) -> tuple[str, ...]:
        """Policy IDs, retained as the route/profile identity surface."""

        return tuple(grant.capability_id for grant in self.mcp_server_grants)

    def app_server_config_projection(self) -> dict[str, object]:
        """Security-relevant config expected back from ``config/read``."""

        return {
            "agents": {"enabled": False},
            "features": {
                "apps": False,
                "auth_elicitation": False,
                "enable_mcp_apps": False,
                "mcp_2026_07_28": False,
                "multi_agent": False,
                "multi_agent_v2": False,
                "plugins": False,
                "remote_plugin": False,
                "tool_call_mcp_elicitation": False,
            },
            "mcp_servers": {
                grant.config_name: grant.config_projection()
                for grant in self.mcp_server_grants
            },
            "plugins": {},
            # App Server currently omits an explicitly empty ``skills.config``
            # from config/read. The override still clears configured skills;
            # effective discovery is independently attested by skills/list.
            "skills": {"config": None},
        }

    @property
    def expected_config_digest(self) -> str:
        return _digest(self.app_server_config_projection())

    def app_server_config_overrides(self) -> tuple[str, ...]:
        if self.execution_surface != "codex-app-server":
            raise CapabilityPolicyError(
                f"profile {self.profile_id!r} is not an App Server profile"
            )
        values = list(_BASE_APP_SERVER_OVERRIDES)
        for grant in self.mcp_server_grants:
            values.extend(grant.config_overrides())
        return tuple(values)

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
        for name in self.skills:
            required.append(
                CapabilityIdentity(
                    name=name,
                    kind="skill",
                    harness_binary_digest=binary_digest,
                )
            )
        for grant in self.mcp_server_grants:
            required.append(
                CapabilityIdentity(
                    name=grant.config_name,
                    kind="mcp_server",
                    harness_binary_digest=binary_digest,
                    tool_schema_digest=grant.tool_schema_digest,
                    mcp_server_identity=grant.server_identity,
                    mcp_server_version=grant.server_version,
                    mcp_auth_status=grant.auth_status,
                )
            )
        for name in self.plugins:
            required.append(
                CapabilityIdentity(
                    name=name,
                    kind="plugin",
                    harness_binary_digest=binary_digest,
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
    mcp_servers: Mapping[str, McpServerGrant]
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
            "mcp_servers",
            "plugins",
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
        plugins_raw = raw.get("plugins")
        if plugins_raw != {}:
            raise CapabilityPolicyError(
                "G3 plugin grants remain unavailable until exact installed-bundle "
                "attestation exists; plugins must be empty"
            )
        mcp_raw = raw.get("mcp_servers")
        if not isinstance(mcp_raw, dict) or len(mcp_raw) > 32:
            raise CapabilityPolicyError("capability policy MCP registry is invalid")
        mcp_registry: dict[str, McpServerGrant] = {}
        config_names: set[str] = set()
        for raw_id, value in mcp_raw.items():
            capability_id = _identifier(raw_id, field="mcp_server capability_id")
            if not isinstance(value, dict) or set(value) != _MCP_KEYS:
                raise CapabilityPolicyError(
                    f"MCP grant {capability_id!r} fields drifted"
                )
            config_name = _config_name(
                value.get("config_name"),
                field=f"mcp_servers.{capability_id}.config_name",
            )
            if config_name in config_names:
                raise CapabilityPolicyError(
                    f"MCP config name {config_name!r} is not unique"
                )
            config_names.add(config_name)
            transport = _closed_choice(
                value.get("transport"),
                field=f"mcp_servers.{capability_id}.transport",
                choices=_MCP_TRANSPORTS,
            )
            url = _https_url(
                value.get("url"), field=f"mcp_servers.{capability_id}.url"
            )
            if value.get("required") is not True:
                raise CapabilityPolicyError(
                    f"MCP grant {capability_id!r} must fail startup closed"
                )
            auth_status = str(value.get("auth_status") or "").strip()
            if auth_status not in _MCP_AUTH_STATUSES:
                raise CapabilityPolicyError(
                    f"MCP grant {capability_id!r} auth_status is unsupported"
                )
            server_identity = _identifier(
                value.get("server_identity"),
                field=f"mcp_servers.{capability_id}.server_identity",
            )
            server_version = _identifier(
                value.get("server_version"),
                field=f"mcp_servers.{capability_id}.server_version",
            )
            enabled_tools = _identities(
                value.get("enabled_tools"),
                field=f"mcp_servers.{capability_id}.enabled_tools",
            )
            if not enabled_tools:
                raise CapabilityPolicyError(
                    f"MCP grant {capability_id!r} requires a non-empty tool allow-list"
                )
            approval_mode = str(
                value.get("default_tools_approval_mode") or ""
            ).strip()
            if approval_mode not in _MCP_APPROVAL_MODES:
                raise CapabilityPolicyError(
                    f"MCP grant {capability_id!r} approval mode is unsupported"
                )
            tool_schema_digest = _digest_value(
                value.get("tool_schema_digest"),
                field=f"mcp_servers.{capability_id}.tool_schema_digest",
            )
            normalized_grant = {
                "capability_id": capability_id,
                "config_name": config_name,
                "transport": transport,
                "url": url,
                "required": True,
                "auth_status": auth_status,
                "server_identity": server_identity,
                "server_version": server_version,
                "enabled_tools": list(enabled_tools),
                "default_tools_approval_mode": approval_mode,
                "tool_schema_digest": tool_schema_digest,
            }
            mcp_registry[capability_id] = McpServerGrant(
                capability_id=capability_id,
                config_name=config_name,
                transport=transport,
                url=url,
                required=True,
                auth_status=auth_status,
                server_identity=server_identity,
                server_version=server_version,
                enabled_tools=enabled_tools,
                default_tools_approval_mode=approval_mode,
                tool_schema_digest=tool_schema_digest,
                grant_digest=_digest(normalized_grant),
            )
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
            mcp_server_ids = _identities(
                value.get("mcp_servers"), field=f"profiles.{profile_id}.mcp_servers"
            )
            plugins = _identities(
                value.get("plugins"), field=f"profiles.{profile_id}.plugins"
            )
            forbidden = _identities(
                value.get("forbidden"), field=f"profiles.{profile_id}.forbidden"
            )
            unknown_mcp = sorted(set(mcp_server_ids) - set(mcp_registry))
            if unknown_mcp:
                raise CapabilityPolicyError(
                    f"profile {profile_id!r} references unknown MCP grants: "
                    + ", ".join(unknown_mcp)
                )
            if plugins:
                raise CapabilityPolicyError(
                    f"profile {profile_id!r} cannot grant plugins before "
                    "installed-bundle attestation"
                )
            resolved_mcp = tuple(
                mcp_registry[item] for item in mcp_server_ids
            )
            required = set(
                (
                    *skills,
                    *(grant.config_name for grant in resolved_mcp),
                    *plugins,
                )
            )
            collision = sorted(required & set(forbidden))
            if collision:
                raise CapabilityPolicyError(
                    f"profile {profile_id!r} both requires and forbids: {', '.join(collision)}"
                )
            if execution_surface == "codex-exec" and (mcp_server_ids or plugins):
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
                "mcp_servers": [
                    {
                        "capability_id": grant.capability_id,
                        "grant_digest": grant.grant_digest,
                    }
                    for grant in resolved_mcp
                ],
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
                mcp_server_grants=resolved_mcp,
                plugins=plugins,
                forbidden=forbidden,
                profile_digest=_digest(normalized),
            )
        normalized_policy = {
            "schema_version": CAPABILITY_POLICY_SCHEMA,
            "policy_version": policy_version,
            "lifecycle_authority": "executive_os",
            "production_armed": False,
            "mcp_servers": {
                capability_id: grant.grant_digest
                for capability_id, grant in sorted(mcp_registry.items())
            },
            "plugins": {},
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
            mcp_servers=mcp_registry,
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
    "McpServerGrant",
    "app_server_security_config_digest",
    "app_server_security_config_projection",
    "observed_mcp_tool_schema_digest",
]
