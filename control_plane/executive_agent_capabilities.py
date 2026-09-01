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


CAPABILITY_POLICY_SCHEMA = "mastermind.executive_agent_capabilities/v3"
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
_NETWORK_POLICIES = frozenset({"disabled", "loopback-browser-only"})
_MCP_TRANSPORTS = frozenset({"stdio", "streamable-http"})
_MCP_AUTH_STATUSES = frozenset(
    {"unsupported", "notLoggedIn", "bearerToken", "oAuth"}
)
_MCP_APPROVAL_MODES = frozenset({"approve"})
_NATIVE_HELPER_MECHANISMS = frozenset({"codex-multi-agent-v2-inherit-parent"})
_REASONING_EFFORTS = frozenset(
    {"low", "medium", "high", "xhigh", "max", "ultra"}
)
_MCP_COMMON_KEYS = frozenset(
    {
        "config_name",
        "transport",
        "required",
        "auth_status",
        "server_identity",
        "server_version",
        "enabled_tools",
        "default_tools_approval_mode",
        "tool_schema_digest",
    }
)
_MCP_HTTP_KEYS = _MCP_COMMON_KEYS | {"url"}
_MCP_STDIO_KEYS = _MCP_COMMON_KEYS | {"args", "command"}
WORKER_BROWSER_MCP_COMMAND = "/usr/bin/python3"
WORKER_BROWSER_MCP_BOOTSTRAP = r'''import hashlib,json,os,stat
K=("MASTERMIND_BROWSER_ARTIFACT_DIR","MASTERMIND_BROWSER_FIXTURE_A_URL","MASTERMIND_BROWSER_FIXTURE_B_URL","MASTERMIND_BROWSER_FIXTURE_NONCE","MASTERMIND_BROWSER_ORIGIN","MASTERMIND_BROWSER_PROXY_URL","MASTERMIND_BROWSER_RUNTIME_MANIFEST_PATH","MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256","MASTERMIND_BROWSER_RUNTIME_ROOT","MASTERMIND_BROWSER_WORKSPACE_PATH","PLAYWRIGHT_BROWSERS_PATH")
F="MASTERMIND_BROWSER_RUNTIME_CONTAINER_FD"
N="worker-browser-b1-install-manifest.json"
d=-1; D=-1
try:
 e={k:os.environ[k] for k in K}
 r=e["MASTERMIND_BROWSER_RUNTIME_ROOT"]
 m=e["MASTERMIND_BROWSER_RUNTIME_MANIFEST_PATH"]
 if not os.path.isabs(r) or os.path.basename(r)!="runtime" or m!=os.path.join(r,N): raise ValueError()
 c=os.path.dirname(r)
 q=getattr(os,"O_NOFOLLOW",0); z=getattr(os,"O_DIRECTORY",0)
 if not q or not z: raise OSError()
 d=os.open(c,os.O_RDONLY|q|z); i=os.fstat(d)
 x=os.open("runtime/"+N,os.O_RDONLY|q,dir_fd=d)
 try:
  a=os.fstat(x)
  if not stat.S_ISREG(a.st_mode) or a.st_nlink!=1 or a.st_uid!=os.geteuid() or stat.S_IMODE(a.st_mode)!=0o400 or not 0<a.st_size<=4194304: raise OSError()
  b=b""
  while len(b)<=4194304:
   h=os.read(x,65536)
   if not h: break
   b+=h
  j=os.fstat(x)
 finally: os.close(x)
 if len(b)>4194304 or (a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns)!=(j.st_dev,j.st_ino,j.st_size,j.st_mtime_ns) or hashlib.sha256(b).hexdigest()!=e["MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256"]: raise ValueError()
 v=json.loads(b.decode("utf-8")); w=v["runtime_container"]
 if b!=json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()+b"\n" or set(w)!={"device","gid","inode","mode","uid"} or any(type(w[k]) is not int for k in w) or w!={"device":i.st_dev,"gid":i.st_gid,"inode":i.st_ino,"mode":stat.S_IMODE(i.st_mode),"uid":i.st_uid} or i.st_uid!=os.geteuid() or stat.S_IMODE(i.st_mode)!=0o500: raise ValueError()
 D=os.dup(d)
 for C in ("runtime","bin"):
  Y=os.open(C,os.O_RDONLY|q|z,dir_fd=D); os.close(D); D=Y; U=os.fstat(D)
  if not stat.S_ISDIR(U.st_mode) or U.st_uid!=os.geteuid() or stat.S_IMODE(U.st_mode)!=0o500: raise OSError()
 l=v["launcher"]; y=os.open("worker-browser-b1-launcher",os.O_RDONLY|q,dir_fd=D)
 try:
  s=os.fstat(y); g=hashlib.sha256(); n=0
  while n<=4194304:
   h=os.read(y,65536)
   if not h: break
   n+=len(h); g.update(h)
  t=os.fstat(y); k=os.stat("worker-browser-b1-launcher",dir_fd=D,follow_symlinks=False)
 finally: os.close(y)
 P=lambda o:(o.st_dev,o.st_ino,o.st_mode,o.st_nlink,o.st_uid,o.st_gid,o.st_size,o.st_mtime_ns,o.st_ctime_ns)
 if set(l)!={"gid","mode","path","sha256","uid"} or l["path"]!=os.path.join(r,"bin","worker-browser-b1-launcher") or not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or s.st_uid!=os.geteuid() or stat.S_IMODE(s.st_mode)!=0o500 or n!=s.st_size or n>4194304 or P(s)!=P(t) or P(s)!=P(k) or l!={"gid":s.st_gid,"mode":0o500,"path":l["path"],"sha256":g.hexdigest(),"uid":s.st_uid}: raise ValueError()
 os.close(D); D=-1
 os.set_inheritable(d,True); e[F]=str(d); os.fchdir(d)
 os.execve("runtime/bin/worker-browser-b1-launcher",["runtime/bin/worker-browser-b1-launcher"],e)
except (KeyError,OSError,TypeError,UnicodeError,ValueError):
 if D>=0:
  try: os.close(D)
  except OSError: pass
 if d>=0:
  try: os.close(d)
  except OSError: pass
 raise SystemExit("runtime container bootstrap refused")
'''
WORKER_BROWSER_MCP_ARGS = ("-I", "-S", "-c", WORKER_BROWSER_MCP_BOOTSTRAP)
_RESOURCE_KEYS = frozenset(
    {
        "artifact_root",
        "browser",
        "browser_revision",
        "kind",
        "manifest_digest",
        "manifest_path",
        "runtime_root",
        "runtime_manifest_digest",
        "runtime_manifest_path",
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
        "native_helper",
        "skills",
        "mcp_servers",
        "resources",
        "plugins",
        "forbidden",
    }
)
_NATIVE_HELPER_KEYS = frozenset(
    {
        "mechanism",
        "default_model",
        "default_reasoning_effort",
        "inherit_parent_capabilities",
        "hide_spawn_agent_metadata",
        "max_concurrent_helpers",
        "max_depth",
        "max_runtime_seconds",
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
    token = str(value or "").strip()
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
    url: str | None
    command: str | None
    args: tuple[str, ...]
    required: bool
    auth_status: str
    server_identity: str
    server_version: str
    enabled_tools: tuple[str, ...]
    default_tools_approval_mode: str
    tool_schema_digest: str
    grant_digest: str

    def config_projection(self) -> dict[str, object]:
        projection: dict[str, object] = {
            "default_tools_approval_mode": self.default_tools_approval_mode,
            "enabled": True,
            "enabled_tools": list(self.enabled_tools),
            "required": self.required,
        }
        if self.transport == "streamable-http":
            projection["url"] = self.url
        else:
            projection["command"] = self.command
            projection["args"] = list(self.args)
        return projection

    def config_overrides(self) -> tuple[str, ...]:
        prefix = f"mcp_servers.{self.config_name}"
        tools = json.dumps(list(self.enabled_tools), ensure_ascii=True, separators=(",", ":"))
        values = [
            f"{prefix}.required={'true' if self.required else 'false'}",
            f"{prefix}.enabled=true",
            f"{prefix}.enabled_tools={tools}",
            (
                f"{prefix}.default_tools_approval_mode="
                f"{_toml_string(self.default_tools_approval_mode)}"
            ),
        ]
        if self.transport == "streamable-http":
            assert self.url is not None
            values.insert(0, f"{prefix}.url={_toml_string(self.url)}")
        else:
            assert self.command is not None
            values.insert(0, f"{prefix}.command={_toml_string(self.command)}")
            args = json.dumps(list(self.args), ensure_ascii=True, separators=(",", ":"))
            values.insert(1, f"{prefix}.args={args}")
        return tuple(values)


@dataclasses.dataclass(frozen=True)
class ResourceGrant:
    """One immutable Attempt-subordinate resource grant in the existing registry."""

    resource_id: str
    kind: str
    manifest_path: str
    manifest_digest: str
    runtime_root: str
    runtime_manifest_digest: str
    runtime_manifest_path: str
    artifact_root: str
    browser: str
    browser_revision: str
    grant_digest: str


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

_AGENT_SECURITY_KEYS = (
    "default_subagent_model",
    "default_subagent_reasoning_effort",
    "enabled",
    "interrupt_message",
    "job_max_runtime_seconds",
    "max_concurrent_threads_per_session",
    "max_depth",
)


def app_server_security_config_projection(
    config: Mapping[str, Any] | None,
) -> dict[str, object]:
    """Project only the fields that can widen this G4 process.
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
            projection: dict[str, object] = {
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
            }
            if raw_value.get("command") is not None or raw_value.get("args") is not None:
                args = raw_value.get("args")
                projection["command"] = raw_value.get("command")
                projection["args"] = list(args) if isinstance(args, list) else None
            else:
                projection["url"] = raw_value.get("url")
            projected_servers[name] = projection
    elif raw_servers is not None:
        projected_servers["__invalid__"] = {"invalid": True}

    if isinstance(plugins, Mapping):
        plugin_projection: object = {
            str(name): True for name in sorted(plugins, key=str)
        }
    else:
        plugin_projection = {"__invalid__": True}

    skill_config = skills.get("config") if isinstance(skills, Mapping) else None
    if isinstance(agents, Mapping) and agents.get("enabled") is True:
        agent_projection: dict[str, object] = {
            key: agents.get(key) for key in _AGENT_SECURITY_KEYS
        }
        for key, value in sorted(agents.items(), key=lambda item: str(item[0])):
            name = str(key)
            if name not in agent_projection:
                agent_projection[name] = (
                    dict(value) if isinstance(value, Mapping) else value
                )
    else:
        agent_projection = {
            "enabled": agents.get("enabled") if isinstance(agents, Mapping) else None
        }

    return {
        "agents": agent_projection,
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
    native_helper: "NativeHelperGrant | None"
    skills: tuple[str, ...]
    mcp_server_grants: tuple[McpServerGrant, ...]
    resource_grants: tuple[ResourceGrant, ...]
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
                    *(grant.resource_id for grant in self.resource_grants),
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

        agents: dict[str, object]
        multi_agent: object = False
        multi_agent_v2: object = False
        if self.native_helper is None:
            agents = {"enabled": False}
        else:
            helper = self.native_helper
            agents = {
                "default_subagent_model": helper.default_model,
                "default_subagent_reasoning_effort": (
                    helper.default_reasoning_effort
                ),
                "enabled": True,
                "interrupt_message": None,
                "job_max_runtime_seconds": helper.max_runtime_seconds,
                "max_concurrent_threads_per_session": (
                    helper.max_concurrent_helpers
                ),
                "max_depth": helper.max_depth,
            }
            multi_agent_v2 = {
                "enabled": True,
                "hide_spawn_agent_metadata": helper.hide_spawn_agent_metadata,
                # V2 counts the root; the public agents setting above counts
                # only spawned helpers.  Pin both interpretations.
                "max_concurrent_threads_per_session": (
                    helper.max_concurrent_helpers + 1
                ),
                "non_code_mode_only": False,
            }
        return {
            "agents": agents,
            "features": {
                "apps": False,
                "auth_elicitation": False,
                "enable_mcp_apps": False,
                "mcp_2026_07_28": False,
                "multi_agent": multi_agent,
                "multi_agent_v2": multi_agent_v2,
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
        if self.native_helper is not None:
            helper = self.native_helper
            values = [
                value
                for value in values
                if value
                not in {
                    "agents.enabled=false",
                    "features.multi_agent=false",
                    "features.multi_agent_v2=false",
                }
            ]
            values.extend(
                (
                    "features.multi_agent=false",
                    (
                        "features.multi_agent_v2={enabled=true,"
                        "hide_spawn_agent_metadata=true,"
                        "max_concurrent_threads_per_session="
                        f"{helper.max_concurrent_helpers + 1},"
                        "non_code_mode_only=false}"
                    ),
                    "agents.enabled=true",
                    (
                        "agents.max_concurrent_threads_per_session="
                        f"{helper.max_concurrent_helpers}"
                    ),
                    f"agents.max_depth={helper.max_depth}",
                    (
                        "agents.job_max_runtime_seconds="
                        f"{helper.max_runtime_seconds}"
                    ),
                    (
                        "agents.default_subagent_model="
                        f"{_toml_string(helper.default_model)}"
                    ),
                    (
                        "agents.default_subagent_reasoning_effort="
                        f"{_toml_string(helper.default_reasoning_effort)}"
                    ),
                )
            )
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
        for grant in self.resource_grants:
            required.append(
                CapabilityIdentity(
                    name=grant.resource_id,
                    kind="resource",
                    harness_binary_digest=binary_digest,
                    resource_contract_digest=grant.grant_digest,
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
class NativeHelperGrant:
    """Machine-enforced, shrink-only native helper limits for one profile."""

    mechanism: str
    default_model: str
    default_reasoning_effort: str
    inherit_parent_capabilities: bool
    hide_spawn_agent_metadata: bool
    max_concurrent_helpers: int
    max_depth: int
    max_runtime_seconds: int
    grant_digest: str


@dataclasses.dataclass(frozen=True)
class ExecutionCapabilityRegistry:
    policy_version: str
    lifecycle_authority: str
    production_armed: bool
    mcp_servers: Mapping[str, McpServerGrant]
    resources: Mapping[str, ResourceGrant]
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
            "resources",
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
                "capability policy must remain production_armed=false"
            )
        policy_version = _identifier(raw.get("policy_version"), field="policy_version")
        plugins_raw = raw.get("plugins")
        if plugins_raw != {}:
            raise CapabilityPolicyError(
                "plugin grants remain unavailable until exact installed-bundle "
                "attestation exists; plugins must be empty"
            )
        mcp_raw = raw.get("mcp_servers")
        if not isinstance(mcp_raw, dict) or len(mcp_raw) > 32:
            raise CapabilityPolicyError("capability policy MCP registry is invalid")
        mcp_registry: dict[str, McpServerGrant] = {}
        config_names: set[str] = set()
        for raw_id, value in mcp_raw.items():
            capability_id = _identifier(raw_id, field="mcp_server capability_id")
            if not isinstance(value, dict):
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
            expected_mcp_keys = (
                _MCP_HTTP_KEYS if transport == "streamable-http" else _MCP_STDIO_KEYS
            )
            if set(value) != expected_mcp_keys:
                raise CapabilityPolicyError(
                    f"MCP grant {capability_id!r} fields drifted"
                )
            url: str | None = None
            command: str | None = None
            args: tuple[str, ...] = ()
            if transport == "streamable-http":
                url = _https_url(
                    value.get("url"), field=f"mcp_servers.{capability_id}.url"
                )
            else:
                command_value = str(value.get("command") or "").strip()
                if (
                    capability_id != "playwright-worker-browser-b1"
                    or command_value != WORKER_BROWSER_MCP_COMMAND
                ):
                    raise CapabilityPolicyError(
                        f"MCP grant {capability_id!r} stdio command is not reviewed"
                    )
                raw_args = value.get("args")
                if (
                    raw_args != list(WORKER_BROWSER_MCP_ARGS)
                    or len(
                        json.dumps(
                            raw_args,
                            ensure_ascii=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    )
                    > 4096
                ):
                    raise CapabilityPolicyError(
                        f"MCP grant {capability_id!r} stdio args are not reviewed"
                    )
                command = command_value
                args = tuple(raw_args)
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
                "command": command,
                "args": list(args),
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
                command=command,
                args=args,
                required=True,
                auth_status=auth_status,
                server_identity=server_identity,
                server_version=server_version,
                enabled_tools=enabled_tools,
                default_tools_approval_mode=approval_mode,
                tool_schema_digest=tool_schema_digest,
                grant_digest=_digest(normalized_grant),
            )
        resources_raw = raw.get("resources")
        if not isinstance(resources_raw, dict) or len(resources_raw) > 16:
            raise CapabilityPolicyError("capability policy resource registry is invalid")
        resource_registry: dict[str, ResourceGrant] = {}
        for raw_id, value in resources_raw.items():
            resource_id = _identifier(raw_id, field="resource_id")
            if not isinstance(value, dict) or set(value) != _RESOURCE_KEYS:
                raise CapabilityPolicyError(
                    f"resource grant {resource_id!r} fields drifted"
                )
            if value.get("kind") != "browser-devserver":
                raise CapabilityPolicyError(
                    f"resource grant {resource_id!r} kind is unsupported"
                )
            if value.get("manifest_path") != "config/worker_browser_b1_control_room_devserver.json":
                raise CapabilityPolicyError(
                    f"resource grant {resource_id!r} manifest path is not reviewed"
                )
            manifest_digest = _digest_value(
                value.get("manifest_digest"),
                field=f"resources.{resource_id}.manifest_digest",
            )
            runtime_root = str(value.get("runtime_root") or "")
            runtime_manifest_digest = _digest_value(
                value.get("runtime_manifest_digest"),
                field=f"resources.{resource_id}.runtime_manifest_digest",
            )
            runtime_manifest_path = str(value.get("runtime_manifest_path") or "")
            artifact_root = str(value.get("artifact_root") or "")
            if runtime_root != "/Volumes/Mastermind/worker-browser-b1/runtime":
                raise CapabilityPolicyError(
                    f"resource grant {resource_id!r} runtime root is not reviewed"
                )
            if artifact_root != "/Volumes/Mastermind/worker-browser-b1/artifacts":
                raise CapabilityPolicyError(
                    f"resource grant {resource_id!r} artifact root is not reviewed"
                )
            if runtime_manifest_path != (
                "/Volumes/Mastermind/worker-browser-b1/runtime/"
                "worker-browser-b1-install-manifest.json"
            ):
                raise CapabilityPolicyError(
                    f"resource grant {resource_id!r} runtime manifest is not reviewed"
                )
            if value.get("browser") != "chromium" or value.get("browser_revision") != "1237":
                raise CapabilityPolicyError(
                    f"resource grant {resource_id!r} browser pin is unsupported"
                )
            normalized_resource = {
                "resource_id": resource_id,
                "kind": "browser-devserver",
                "manifest_path": value["manifest_path"],
                "manifest_digest": manifest_digest,
                "runtime_root": runtime_root,
                "runtime_manifest_digest": runtime_manifest_digest,
                "runtime_manifest_path": runtime_manifest_path,
                "artifact_root": artifact_root,
                "browser": "chromium",
                "browser_revision": "1237",
            }
            resource_registry[resource_id] = ResourceGrant(
                resource_id=resource_id,
                kind="browser-devserver",
                manifest_path=str(value["manifest_path"]),
                manifest_digest=manifest_digest,
                runtime_root=runtime_root,
                runtime_manifest_digest=runtime_manifest_digest,
                runtime_manifest_path=runtime_manifest_path,
                artifact_root=artifact_root,
                browser="chromium",
                browser_revision="1237",
                grant_digest=_digest(normalized_resource),
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
            native_helper_raw = value.get("native_helper")
            native_helper: NativeHelperGrant | None = None
            if native_helper_raw is not None:
                if (
                    not isinstance(native_helper_raw, dict)
                    or set(native_helper_raw) != _NATIVE_HELPER_KEYS
                ):
                    raise CapabilityPolicyError(
                        f"profile {profile_id!r} native_helper fields drifted"
                    )
                mechanism = _closed_choice(
                    native_helper_raw.get("mechanism"),
                    field=f"profiles.{profile_id}.native_helper.mechanism",
                    choices=_NATIVE_HELPER_MECHANISMS,
                )
                default_model = str(
                    native_helper_raw.get("default_model") or ""
                ).strip()
                if _ID_RE.fullmatch(default_model) is None:
                    raise CapabilityPolicyError(
                        f"profile {profile_id!r} native helper model is invalid"
                    )
                default_effort = _closed_choice(
                    native_helper_raw.get("default_reasoning_effort"),
                    field=(
                        f"profiles.{profile_id}.native_helper."
                        "default_reasoning_effort"
                    ),
                    choices=_REASONING_EFFORTS,
                )
                if native_helper_raw.get("inherit_parent_capabilities") is not True:
                    raise CapabilityPolicyError(
                        f"profile {profile_id!r} native helper must inherit the "
                        "parent capability ceiling"
                    )
                if native_helper_raw.get("hide_spawn_agent_metadata") is not True:
                    raise CapabilityPolicyError(
                        f"profile {profile_id!r} native helper must hide per-spawn "
                        "role/model/effort overrides"
                    )
                max_helpers = native_helper_raw.get("max_concurrent_helpers")
                max_depth = native_helper_raw.get("max_depth")
                max_runtime = native_helper_raw.get("max_runtime_seconds")
                if type(max_helpers) is not int or max_helpers != 1:
                    raise CapabilityPolicyError(
                        f"profile {profile_id!r} native helper ceiling must be one"
                    )
                if type(max_depth) is not int or max_depth != 1:
                    raise CapabilityPolicyError(
                        f"profile {profile_id!r} native helper depth must be one"
                    )
                if (
                    type(max_runtime) is not int
                    or max_runtime < 30
                    or max_runtime > 300
                ):
                    raise CapabilityPolicyError(
                        f"profile {profile_id!r} native helper runtime is unbounded"
                    )
                native_helper_normalized = {
                    "mechanism": mechanism,
                    "default_model": default_model,
                    "default_reasoning_effort": default_effort,
                    "inherit_parent_capabilities": True,
                    "hide_spawn_agent_metadata": True,
                    "max_concurrent_helpers": max_helpers,
                    "max_depth": max_depth,
                    "max_runtime_seconds": max_runtime,
                }
                native_helper = NativeHelperGrant(
                    mechanism=mechanism,
                    default_model=default_model,
                    default_reasoning_effort=default_effort,
                    inherit_parent_capabilities=True,
                    hide_spawn_agent_metadata=True,
                    max_concurrent_helpers=max_helpers,
                    max_depth=max_depth,
                    max_runtime_seconds=max_runtime,
                    grant_digest=_digest(native_helper_normalized),
                )
            skills = _identities(value.get("skills"), field=f"profiles.{profile_id}.skills")
            mcp_server_ids = _identities(
                value.get("mcp_servers"), field=f"profiles.{profile_id}.mcp_servers"
            )
            resource_ids = _identities(
                value.get("resources"), field=f"profiles.{profile_id}.resources"
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
            unknown_resources = sorted(set(resource_ids) - set(resource_registry))
            if unknown_resources:
                raise CapabilityPolicyError(
                    f"profile {profile_id!r} references unknown resources: "
                    + ", ".join(unknown_resources)
                )
            if plugins:
                raise CapabilityPolicyError(
                    f"profile {profile_id!r} cannot grant plugins before "
                    "installed-bundle attestation"
                )
            resolved_mcp = tuple(
                mcp_registry[item] for item in mcp_server_ids
            )
            resolved_resources = tuple(
                resource_registry[item] for item in resource_ids
            )
            required = set(
                (
                    *skills,
                    *(grant.config_name for grant in resolved_mcp),
                    *(grant.resource_id for grant in resolved_resources),
                    *plugins,
                )
            )
            collision = sorted(required & set(forbidden))
            if collision:
                raise CapabilityPolicyError(
                    f"profile {profile_id!r} both requires and forbids: {', '.join(collision)}"
                )
            if execution_surface == "codex-exec" and (
                mcp_server_ids or resource_ids or plugins
            ):
                raise CapabilityPolicyError(
                    f"profile {profile_id!r} cannot grant MCP/plugins or resources "
                    "to sealed codex-exec"
                )
            is_browser_profile = profile_id == "operator.browser.local-review.v1"
            if is_browser_profile:
                if (
                    mcp_server_ids
                    != (
                        "openai-developer-docs-v1",
                        "playwright-worker-browser-b1",
                    )
                    or resource_ids != ("worker-browser-b1-local",)
                    or network_policy != "loopback-browser-only"
                    or execution_surface != "codex-app-server"
                    or native_helper_policy is not NativeHelperPolicy.DISABLED
                ):
                    raise CapabilityPolicyError(
                        "browser profile must preserve the exact reviewed rich-operator "
                        "MCP/resource/network ceiling"
                    )
            elif resource_ids or network_policy == "loopback-browser-only":
                raise CapabilityPolicyError(
                    f"profile {profile_id!r} cannot inherit browser resource authority"
                )
            if write_capable and sandbox_policy != "workspace-write":
                raise CapabilityPolicyError(
                    f"profile {profile_id!r} write capability requires workspace-write"
                )
            if not write_capable and sandbox_policy != "read-only":
                raise CapabilityPolicyError(
                    f"profile {profile_id!r} read-only capability requires read-only sandbox"
                )
            if (
                native_helper_policy is NativeHelperPolicy.DISABLED
                and native_helper is not None
            ):
                raise CapabilityPolicyError(
                    f"profile {profile_id!r} has a native helper grant while helpers are disabled"
                )
            if (
                native_helper_policy
                is NativeHelperPolicy.PARENT_READ_ONLY_CEILING
                and native_helper is None
            ):
                raise CapabilityPolicyError(
                    f"profile {profile_id!r} enables native helpers without an exact ceiling"
                )
            if (
                native_helper_policy
                is NativeHelperPolicy.REQUIRES_SUBAGENT_CAPABILITY_CEILING
                or (native_helper is not None and write_capable)
            ):
                raise CapabilityPolicyError(
                    f"profile {profile_id!r} write-capable native helpers remain unavailable"
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
                "native_helper_grant_digest": (
                    native_helper.grant_digest if native_helper is not None else None
                ),
                "skills": list(skills),
                "mcp_servers": [
                    {
                        "capability_id": grant.capability_id,
                        "grant_digest": grant.grant_digest,
                    }
                    for grant in resolved_mcp
                ],
                "resources": [
                    {
                        "resource_id": grant.resource_id,
                        "grant_digest": grant.grant_digest,
                    }
                    for grant in resolved_resources
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
                native_helper=native_helper,
                skills=skills,
                mcp_server_grants=resolved_mcp,
                resource_grants=resolved_resources,
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
            "resources": {
                resource_id: grant.grant_digest
                for resource_id, grant in sorted(resource_registry.items())
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
            resources=resource_registry,
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
    "NativeHelperGrant",
    "ResourceGrant",
    "app_server_security_config_digest",
    "app_server_security_config_projection",
    "observed_mcp_tool_schema_digest",
]
