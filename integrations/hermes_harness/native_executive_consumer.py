"""Native Hermes consumer of the closed selected-child delegation path.

This module owns the *consumer* half of the native chain: the optional,
non-secret launch publication that a trusted host froze, the readiness and
enrollment proof that must hold before anything is registered, the one-RPC
transport over the already captured native MCP owner, and the fixed typed
owner-private slot that hands the immutable startup to the plugin loader.

It owns no principal, no session, no credential, no target registry, no
listener, no client, no token and no retry. The frozen child, the authenticated
Executive principal and the mission authority live in their incumbent owners
(the C29 selected-child contract, the capability/authentication owners and the
installed enrollment). This module only *proves* that the same frozen material
and the same authenticated connection are present, and then refuses when they
are not.

Three states stay distinct:

* A refusal decided before the transport is called is a proved no-effect.
* Anything after a possible send - a timeout, a lost response, a malformed or
  mismatched return - is uncertain: the original command identity is kept and
  the state is ``EFFECT_UNKNOWN`` (submit) or ``UNAVAILABLE`` (status).
* A material change after the registration - a different session, a different
  connection, a different target - is a refusal, never a silent retarget.

Nothing here reads a secret, opens a socket, writes an installed file, clears
``NATIVE_EXTENSION_NOT_INSTALLED`` or claims an enrollment. The default is
unbound: without a qualified publication and a proved live connection, no tool
is registered and the consumer stays unavailable.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import json
import re
import threading
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from integrations.hermes_delegate.policy import TOOL_NAME
from integrations.hermes_harness.native_tool_registration import (
    SELECTED_CHILD_SCHEMA,
    NativeDelegateBinding,
    NativeDelegateRegistration,
    NativeDelegateStartup,
    NativeToolRegistrationError,
)
from integrations.hermes_runtime.errors import RuntimeRefusal

__all__ = [
    "CONSUMER_MCP_SERVER",
    "CONSUMER_PLUGIN_NAME",
    "CONSUMER_PLUGIN_SOURCE",
    "CONSUMER_SCHEMA",
    "CONSUMER_SLOT_ATTRIBUTE",
    "ConsumerMcp",
    "ConsumerPlugin",
    "ConsumerPrincipal",
    "ConsumerSession",
    "ConsumerSlot",
    "ExecutiveConsumerPublication",
    "NativeConsumerCurrentness",
    "NativeExecutiveTransport",
    "install_consumer_slot",
    "publication_from_document",
    "read_consumer_slot",
    "schema_digest",
    "tools_schema_digest",
    "validate_consumer_publication",
]

# The optional installed publication. It is a *closed* document: exactly these
# keys, no credential, no bearer template, no client secret, no private path
# outside the role home and no caller-supplied authority boolean.
CONSUMER_SCHEMA = "mastermind.hermes_native_executive_consumer/v1"
CONTEXT_CONSUMER_SCHEMA = "mastermind.hermes_native_executive_consumer/v2"
CONTEXT_TOOLS_SCHEMA_DIGEST = "5fa24aa1d907d66d0ca0a56168617f955e09d063f532cf527fe0d7b923fb50af"
CURRENT_CONTEXT_CONSUMER_SCHEMA = "mastermind.hermes_native_executive_consumer/v3"
CURRENT_CONTEXT_TOOLS_SCHEMA_DIGEST = "41644c90bbd8b5927c5cc7f97f65fef144ba9f9ca6e0277d702d7a8a26fa0da0"
DISCOVERY_CONSUMER_SCHEMA = "mastermind.hermes_native_executive_consumer/v4"
DISCOVERY_TOOLS_SCHEMA_DIGEST = "94db08906bd04c78565f6172d7a657c13bbe608f3b14dba5649cbedb23deed42"
_WORKSPACE_RESOURCE = "https://mcp.mastermind-x.com/workspace/read"
_WORKSPACE_SCOPE = "mastermind.workspace.read"
_CURRENT_PRIMARY_RESOURCE = "https://mcp.mastermind-x.com/mcp"
_CURRENT_PRIMARY_URL = "https://mcp.mastermind-x.com/mcp/coo"
_CURRENT_PRIMARY_SCOPE = "mastermind.executive.coo.act mastermind.executive.read"

# The fixed typed owner-private slot on the ACTUAL per-profile PluginManager.
# It is a private attribute on an object the upstream owner created; this
# module never replaces the global ``_plugin_manager`` and never writes the
# tool registry directly.
CONSUMER_SLOT_ATTRIBUTE = "_mmx_native_executive_consumer"

# The plugin package that the native loader loads. It is a *non-bundled*
# ("user") directory plugin: it is never labelled "bundled" to buy trust.
CONSUMER_PLUGIN_NAME = "native_selected_child_plugin"
CONSUMER_PLUGIN_SOURCE = "user"

# The MCP server the Executive connection is published under. The raw COO
# tools of that server are never model-facing; only the C28 ``mmx_delegate``
# exposes delegation.
CONSUMER_MCP_SERVER = "mastermind_coo"

# The mandate read the consumer performs once, for the frozen work reference.
CONSUMER_MANDATE_TOOL = "executive_mandate"

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMAND_RE = re.compile(
    r"^coo-cycle:[^:\s]{1,128}:dispatch:[^:\s]{1,128}:attempt:[1-9][0-9]{0,9}$"
)
_WORK_REF_RE = re.compile(r"^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$")
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{1,255}$")
_CLIENT_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,255}$")
_SCOPE_RE = re.compile(r"^[a-z][a-z0-9._:-]{2,95}$")
_OAUTH_SCOPE_RE = re.compile(
    r"^[a-z][a-z0-9._:/-]{2,95}(?: [a-z][a-z0-9._:/-]{2,95})*$")

# A publication never carries bearer material. The check is on the *shape* of
# the closed document, not on a secret-scanner heuristic: only the exact keys
# below are accepted, so no secret can be smuggled through an extra member.
_PUBLICATION_KEYS = frozenset({
    "schema",
    "work_ref",
    "command",
    "job_id",
    "target_digest",
    "root_job_id",
    "mission_authority_ref",
    "authority_generation_digest",
    "capability_profile_digest",
    "principal_binding_digest",
    "principal",
    "mcp",
    "session",
    "plugin",
    "tools_schema_digest",
})
_PRINCIPAL_KEYS = frozenset({
    "policy_id", "issuer_digest", "subject_digest", "client_ref",
    "resource_ref", "scopes",
})
_MCP_KEYS = frozenset({
    "server", "url", "client_id", "scope", "server_name", "server_version",
})
_SESSION_KEYS = frozenset({"request_id", "principal_id", "role"})
_PLUGIN_KEYS = frozenset({"name", "source", "digest"})
_CHILD_KEYS = frozenset({"command", "job_id", "target_digest", "root_job_id"})
_CONTEXT_PUBLICATION_KEYS = (_PUBLICATION_KEYS - _CHILD_KEYS) | {
    "context", "selected_child", "permission_digest"}
_CONTEXT_KEYS = frozenset({"provider", "source_mode", "max_context_bytes", "freshness_seconds"})

_MAX_SCOPES = 16
_MAX_URL = 2048


def _text(value: Any, field: str, pattern: re.Pattern[str] = _REF_RE) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
    return value


def _digest(value: Any, field: str) -> str:
    if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
        raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")




def schema_digest(schema: Any) -> str:
    """Deterministic digest of one registered tool schema.

    The serving process and the supervisor compute it the same way, so the
    observed scoped entry can be compared with the released schema across the
    process boundary. It is an equality check, never an authority.
    """
    if not isinstance(schema, Mapping):
        raise RuntimeRefusal("NATIVE_CONSUMER_TOOLS_SCHEMA_INVALID")
    return hashlib.sha256(_canonical(dict(schema))).hexdigest()


def tools_schema_digest(tools: Any) -> str:
    """Use the capability owner's canonical observed MCP contract digest."""
    from control_plane.executive_agent_capabilities import observed_mcp_tool_schema_digest
    if not isinstance(tools, (list, tuple)):
        raise RuntimeRefusal("NATIVE_CONSUMER_TOOLS_SCHEMA_INVALID")
    rows = {}
    for tool in tools:
        if isinstance(tool, Mapping):
            row = dict(tool)
        elif callable(getattr(tool, "model_dump", None)):
            row = tool.model_dump(by_alias=True, exclude_none=True)
        else:
            row = {name: getattr(tool, name, None)
                   for name in ("name", "inputSchema", "outputSchema", "annotations")}
        name = row.get("name")
        if type(name) is not str or not name or name in rows:
            raise RuntimeRefusal("NATIVE_CONSUMER_TOOLS_SCHEMA_INVALID")
        for key in ("outputSchema", "annotations"):
            value = row.get(key)
            if callable(getattr(value, "model_dump", None)):
                row[key] = value.model_dump(by_alias=True, exclude_none=True)
        rows[name] = row
    result = observed_mcp_tool_schema_digest({"tools": rows})
    if result is None:
        raise RuntimeRefusal("NATIVE_CONSUMER_TOOLS_SCHEMA_INVALID")
    return result



@dataclass(frozen=True)
class ConsumerPrincipal:
    """The installed authenticated principal facts, compared at qualification.

    These are the facts the mandate projection reports for the authenticated
    principal. They are *read* from the mandate response and compared with
    this document; they are never manufactured here.
    """

    policy_id: str
    issuer_digest: str
    subject_digest: str
    client_ref: str
    resource_ref: str
    scopes: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.policy_id, "policy_id")
        for value in (self.issuer_digest, self.subject_digest, self.client_ref):
            _digest(value, "principal digest")
        _text(self.resource_ref, "resource_ref")
        if (not isinstance(self.scopes, tuple) or not self.scopes
                or len(self.scopes) > _MAX_SCOPES):
            raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
        if tuple(sorted(set(self.scopes))) != self.scopes:
            raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
        for scope in self.scopes:
            if type(scope) is not str or _SCOPE_RE.fullmatch(scope) is None:
                raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")

    def matches(self, observed: Any) -> bool:
        """Compare the observed mandate principal with the installed facts."""
        if not isinstance(observed, Mapping):
            return False
        return (
            observed.get("policy_id") == self.policy_id
            and observed.get("issuer_digest") == self.issuer_digest
            and observed.get("subject_digest") == self.subject_digest
            and observed.get("client_ref") == self.client_ref
            and observed.get("resource_ref") == self.resource_ref
            and list(observed.get("scopes") or ()) == list(self.scopes)
        )


def workspace_principal_frame(publication) -> dict:
    """Project already validated nonsecret facts for the existing wire owner."""
    principal = publication.workspace_principal
    if type(principal) is not ConsumerPrincipal:
        raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
    return {"policy_id": principal.policy_id, "issuer_digest": principal.issuer_digest,
            "subject_digest": principal.subject_digest, "client_ref": principal.client_ref,
            "resource": principal.resource_ref, "scopes": list(principal.scopes)}


def workspace_oauth_descriptor(principal_scope: str) -> dict:
    _digest(principal_scope, "workspace principal scope")
    return {"schema": "mastermind.hermes_workspace_oauth.v1", "resource": _WORKSPACE_RESOURCE,
            "identity_url": "https://mcp.mastermind-x.com/workspace/native-draft-identity/current",
            "scope": _WORKSPACE_SCOPE, "principal_scope": principal_scope}


@dataclass(frozen=True)
class ConsumerMcp:
    """The approved MCP/public client metadata of the Executive connection.

    ``client_id`` is the *public* OAuth client reference. It is not a secret:
    the bearer token and any client secret stay with the incumbent OAuth owner
    and its token storage.
    """

    server: str
    url: str
    client_id: str
    scope: str
    server_name: str
    server_version: str
    # Derived from a validated v3 principal. Never an independent public field.
    _workspace_principal_scope: str | None = None

    def __post_init__(self) -> None:
        _text(self.server, "server")
        if type(self.url) is not str or not 1 < len(self.url) <= _MAX_URL:
            raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
        from urllib.parse import urlsplit
        try:
            route = urlsplit(self.url)
            port = route.port
        except ValueError:
            raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID") from None
        if (not route.hostname or route.username is not None or route.password is not None
                or route.query or route.fragment or route.path not in {"/mcp", "/mcp/coo"}
                or (port is not None and not 1 <= port <= 65535)
                or not (route.scheme == "https"
                        or (route.scheme == "http" and route.hostname == "127.0.0.1"))):
            raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
        _text(self.client_id, "client_id", _CLIENT_REF_RE)
        if type(self.scope) is not str or _OAUTH_SCOPE_RE.fullmatch(self.scope) is None:
            raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
        _text(self.server_name, "server_name")
        _text(self.server_version, "server_version")
        if self._workspace_principal_scope is not None:
            _digest(self._workspace_principal_scope, "workspace principal scope")

    def matches_config(self, config: Any) -> bool:
        """Compare the live connection's own config with the approved facts."""
        if not isinstance(config, Mapping):
            return False
        oauth = config.get("oauth")
        if not isinstance(oauth, Mapping):
            return False
        if self._workspace_principal_scope is None:
            if "workspace" in oauth:
                return False
        elif (type(oauth) is not dict or set(oauth) != {"client_id", "scope", "workspace"}
                or oauth["workspace"] != workspace_oauth_descriptor(self._workspace_principal_scope)
                or config.get("transport") != "streamable-http"
                or config.get("strict_redirect_headers") is not True
                or config.get("ssl_verify", True) is not True or config.get("headers")
                or any(config.get(key) is not None for key in (
                    "server_json", "identity_header", "client_cert", "client_key"))):
            return False
        return (
            config.get("url") == self.url
            and str(config.get("auth") or "").lower() == "oauth"
            and oauth.get("client_id") == self.client_id
            and str(oauth.get("scope") or "") == self.scope
        )


@dataclass(frozen=True)
class ConsumerSession:
    """The installed enrollment identity of the native session.

    The instance, epoch, revision and generation are *not* here: they belong
    to the live process and are proved by the incumbent enrollment reader.
    """

    request_id: str
    principal_id: str
    role: str

    def __post_init__(self) -> None:
        _text(self.request_id, "request_id")
        _text(self.principal_id, "principal_id")
        _text(self.role, "role")


@dataclass(frozen=True)
class ConsumerPlugin:
    """The sealed plugin package the native loader must load."""

    name: str
    source: str
    digest: str

    def __post_init__(self) -> None:
        _text(self.name, "name")
        if self.source != CONSUMER_PLUGIN_SOURCE:
            # A bundled label would buy the upstream trust exemptions. The
            # consumer only ever loads a non-bundled, operator-installed plugin.
            raise RuntimeRefusal("NATIVE_CONSUMER_PLUGIN_SOURCE_INVALID")
        _digest(self.digest, "plugin digest")


@dataclass(frozen=True)
class ExecutiveConsumerPublication:
    """The optional, non-secret launch publication of one frozen child.

    Every field is supplied by a trusted host through the incumbent owners.
    Nothing here is derived from a role label, a model argument, an ambient
    environment lookup or a hand-authored command.
    """

    work_ref: str
    command: str
    job_id: str
    target_digest: str
    root_job_id: str
    mission_authority_ref: str
    authority_generation_digest: str
    capability_profile_digest: str
    principal_binding_digest: str
    principal: ConsumerPrincipal
    mcp: ConsumerMcp
    session: ConsumerSession
    plugin: ConsumerPlugin
    tools_schema_digest: str

    def __post_init__(self) -> None:
        if _WORK_REF_RE.fullmatch(self.work_ref or "") is None:
            raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
        if _COMMAND_RE.fullmatch(self.command or "") is None:
            raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
        _text(self.job_id, "job_id")
        _digest(self.target_digest, "target_digest")
        _text(self.root_job_id, "root_job_id")
        _text(self.mission_authority_ref, "mission_authority_ref")
        _digest(self.authority_generation_digest, "authority_generation_digest")
        _digest(self.capability_profile_digest, "capability_profile_digest")
        _digest(self.principal_binding_digest, "principal_binding_digest")
        _digest(self.tools_schema_digest, "tools_schema_digest")
        parts = self.command.split(":")
        if parts[3] != self.job_id:
            # The command's own Job segment must be the frozen Job, so the two
            # cannot describe different children.
            raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")



@dataclass(frozen=True)
class ConsumerContext:
    """Explicit delivery policy; source selection remains with Agent OS."""

    provider: str
    source_mode: str
    max_context_bytes: int
    freshness_seconds: float

    def __post_init__(self):
        from .agentos_memory_provider import (
            MAX_HOST_CONTEXT_BYTES, AgentOsRefusal, _freshness_seconds)
        if (type(self.provider) is not str or self.provider != "agentos"
                or type(self.source_mode) is not str
                or self.source_mode not in {"ADOPTED_SNAPSHOT", "CANONICAL_PROJECT_DATA"}
                or type(self.max_context_bytes) is not int
                or not 0 < self.max_context_bytes <= MAX_HOST_CONTEXT_BYTES):
            raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
        try:
            _freshness_seconds(self.freshness_seconds)
        except AgentOsRefusal:
            raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID") from None


@dataclass(frozen=True)
class ConsumerSelectedChild:
    command: str
    job_id: str
    target_digest: str
    root_job_id: str

    def __post_init__(self):
        if type(self.command) is not str or _COMMAND_RE.fullmatch(self.command) is None:
            raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
        _text(self.job_id, "job_id")
        _text(self.root_job_id, "root_job_id")
        _digest(self.target_digest, "target_digest")
        if self.command.split(":")[3] != self.job_id:
            raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")


@dataclass(frozen=True)
class ExecutiveContextConsumerPublication:
    """The same enrollment owner, with required context and an optional child.

    Context-only missions carry no fabricated Job, root or delegation proof.
    The v1 frozen-child type and its closed document remain unchanged.
    """

    work_ref: str
    mission_authority_ref: str
    authority_generation_digest: str
    capability_profile_digest: str
    principal_binding_digest: str
    permission_digest: str
    principal: ConsumerPrincipal
    mcp: ConsumerMcp
    session: ConsumerSession
    plugin: ConsumerPlugin
    tools_schema_digest: str
    context: ConsumerContext
    selected_child: ConsumerSelectedChild | None
    workspace_principal: ConsumerPrincipal | None = None
    discovery: bool = False

    def __post_init__(self):
        from common.workspace_project_plan_contract import validate_selection
        from integrations.executive_mcp.coo import (
            coo_context_tool_schema_digest, coo_current_context_tool_schema_digest, coo_discovery_tool_schema_digest)
        from integrations.mastermind_executive_app.coo_binding import _digest as binding_record_digest
        try:
            validate_selection({"work_ref": self.work_ref})
        except (TypeError, ValueError):
            raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID") from None
        _text(self.mission_authority_ref, "mission_authority_ref")
        for name in ("authority_generation_digest", "capability_profile_digest",
                     "principal_binding_digest", "permission_digest", "tools_schema_digest"):
            _digest(getattr(self, name), name)
        if (type(self.principal) is not ConsumerPrincipal
                or type(self.mcp) is not ConsumerMcp or type(self.session) is not ConsumerSession
                or type(self.plugin) is not ConsumerPlugin or type(self.context) is not ConsumerContext
                or (self.selected_child is not None and type(self.selected_child) is not ConsumerSelectedChild)):
            raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
        if type(self.discovery) is not bool or self.discovery and self.workspace_principal is None:
            raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
        if self.workspace_principal is None:
            if (self.context.source_mode != "ADOPTED_SNAPSHOT"
                    or self.tools_schema_digest != CONTEXT_TOOLS_SCHEMA_DIGEST
                    or coo_context_tool_schema_digest() != CONTEXT_TOOLS_SCHEMA_DIGEST
                    or self.mcp._workspace_principal_scope is not None):
                raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
        else:
            wp, principal = self.workspace_principal, self.principal
            expected_tools = DISCOVERY_TOOLS_SCHEMA_DIGEST if self.discovery else CURRENT_CONTEXT_TOOLS_SCHEMA_DIGEST
            observed_tools = coo_discovery_tool_schema_digest() if self.discovery else coo_current_context_tool_schema_digest()
            if (type(wp) is not ConsumerPrincipal or self.context.source_mode != "CANONICAL_PROJECT_DATA"
                    or self.tools_schema_digest != expected_tools or observed_tools != expected_tools
                    or wp.resource_ref != _WORKSPACE_RESOURCE or wp.scopes != (_WORKSPACE_SCOPE,)
                    or wp.policy_id == principal.policy_id
                    or any(getattr(wp, key) != getattr(principal, key)
                           for key in ("issuer_digest", "subject_digest", "client_ref"))
                    or principal.resource_ref != _CURRENT_PRIMARY_RESOURCE
                    or principal.scopes != tuple(_CURRENT_PRIMARY_SCOPE.split())
                    or self.mcp.server != CONSUMER_MCP_SERVER or self.mcp.url != _CURRENT_PRIMARY_URL
                    or self.mcp.scope != _CURRENT_PRIMARY_SCOPE
                    or self.mcp._workspace_principal_scope != hashlib.sha256(
                        _canonical(workspace_principal_frame(self))).hexdigest()):
                raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
        # The incumbent digest covers all seven enrolled-record fields,
        # including the enrollment owner's opaque permission receipt. The six
        # public principal facts alone cannot recreate this binding identity.
        principal = self.principal
        record = {"policy_id": principal.policy_id, "issuer_digest": principal.issuer_digest,
                  "subject_digest": principal.subject_digest, "client_ref": principal.client_ref,
                  "resource": principal.resource_ref, "scopes": list(principal.scopes),
                  "permission_digest": self.permission_digest}
        if binding_record_digest(record) != self.principal_binding_digest:
            raise RuntimeRefusal("NATIVE_CONSUMER_PRINCIPAL_BINDING_MISMATCH")


ConsumerPublication = ExecutiveConsumerPublication | ExecutiveContextConsumerPublication


def selected_child_publication(publication: ConsumerPublication) -> ExecutiveConsumerPublication | None:
    """Project only an explicitly selected child into the incumbent contract."""
    if type(publication) is ExecutiveConsumerPublication:
        return publication
    if type(publication) is not ExecutiveContextConsumerPublication:
        raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
    child = publication.selected_child
    if child is None:
        return None
    from dataclasses import fields
    return ExecutiveConsumerPublication(**{
        item.name: getattr(child, item.name) if item.name in _CHILD_KEYS
        else getattr(publication, item.name) for item in fields(ExecutiveConsumerPublication)})


def _validate_context_publication(value):
    current = type(value) is dict and value.get("schema") in {CURRENT_CONTEXT_CONSUMER_SCHEMA, DISCOVERY_CONSUMER_SCHEMA}
    keys = _CONTEXT_PUBLICATION_KEYS | {"workspace_principal"} if current else _CONTEXT_PUBLICATION_KEYS
    if (type(value) is not dict or set(value) != keys
            or value.get("schema") not in {CONTEXT_CONSUMER_SCHEMA, CURRENT_CONTEXT_CONSUMER_SCHEMA, DISCOVERY_CONSUMER_SCHEMA}):
        raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
    for name, keys in (("principal", _PRINCIPAL_KEYS), ("mcp", _MCP_KEYS),
                       ("session", _SESSION_KEYS), ("plugin", _PLUGIN_KEYS),
                       ("context", _CONTEXT_KEYS)):
        if type(value[name]) is not dict or set(value[name]) != keys:
            raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
    if type(value["principal"]["scopes"]) is not list:
        raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
    if current and (type(value["workspace_principal"]) is not dict
            or set(value["workspace_principal"]) != _PRINCIPAL_KEYS
            or type(value["workspace_principal"]["scopes"]) is not list):
        raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
    child = value["selected_child"]
    if child is not None and (type(child) is not dict or set(child) != _CHILD_KEYS):
        raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
    _typed_context_publication(value)
    try:
        return json.loads(_canonical(value))
    except (TypeError, ValueError, UnicodeError):
        raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID") from None


def _typed_context_publication(document):
    common = {name: document[name] for name in (
        "work_ref", "mission_authority_ref", "authority_generation_digest",
        "capability_profile_digest", "principal_binding_digest", "permission_digest", "tools_schema_digest")}
    principal = dict(document["principal"])
    principal["scopes"] = tuple(principal["scopes"])
    workspace = None
    mcp = dict(document["mcp"])
    if document["schema"] in {CURRENT_CONTEXT_CONSUMER_SCHEMA, DISCOVERY_CONSUMER_SCHEMA}:
        raw_workspace = dict(document["workspace_principal"])
        raw_workspace["scopes"] = tuple(raw_workspace["scopes"])
        workspace = ConsumerPrincipal(**raw_workspace)
        frame = dict(raw_workspace, resource=raw_workspace["resource_ref"], scopes=list(workspace.scopes))
        frame.pop("resource_ref")
        mcp["_workspace_principal_scope"] = hashlib.sha256(_canonical(frame)).hexdigest()
    return ExecutiveContextConsumerPublication(
        **common, principal=ConsumerPrincipal(**principal), mcp=ConsumerMcp(**mcp), workspace_principal=workspace,
        discovery=document["schema"] == DISCOVERY_CONSUMER_SCHEMA,
        session=ConsumerSession(**document["session"]), plugin=ConsumerPlugin(**document["plugin"]),
        context=ConsumerContext(**document["context"]), selected_child=(None
            if document["selected_child"] is None else ConsumerSelectedChild(**document["selected_child"])))


def validate_consumer_publication(value: Any) -> dict[str, Any]:
    """Validate one closed publication document and return its detached form.

    An absent member is ``None`` at the call site; a malformed member refuses
    here. No credential, bearer template, client secret, private path or
    authority boolean is accepted: the closed key set cannot carry one.
    """
    if type(value) is dict and value.get("schema") in {CONTEXT_CONSUMER_SCHEMA, CURRENT_CONTEXT_CONSUMER_SCHEMA, DISCOVERY_CONSUMER_SCHEMA}:
        return _validate_context_publication(value)
    if type(value) is not dict or set(value) != _PUBLICATION_KEYS:
        raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
    if value["schema"] != CONSUMER_SCHEMA:
        raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
    principal = value["principal"]
    if type(principal) is not dict or set(principal) != _PRINCIPAL_KEYS:
        raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
    mcp = value["mcp"]
    if type(mcp) is not dict or set(mcp) != _MCP_KEYS:
        raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
    session = value["session"]
    if type(session) is not dict or set(session) != _SESSION_KEYS:
        raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
    plugin = value["plugin"]
    if type(plugin) is not dict or set(plugin) != _PLUGIN_KEYS:
        raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
    scopes = principal["scopes"]
    if type(scopes) is not list:
        raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
    document = {
        "schema": CONSUMER_SCHEMA,
        "work_ref": value["work_ref"],
        "command": value["command"],
        "job_id": value["job_id"],
        "target_digest": value["target_digest"],
        "root_job_id": value["root_job_id"],
        "mission_authority_ref": value["mission_authority_ref"],
        "authority_generation_digest": value["authority_generation_digest"],
        "capability_profile_digest": value["capability_profile_digest"],
        "principal_binding_digest": value["principal_binding_digest"],
        "principal": {
            "policy_id": principal["policy_id"],
            "issuer_digest": principal["issuer_digest"],
            "subject_digest": principal["subject_digest"],
            "client_ref": principal["client_ref"],
            "resource_ref": principal["resource_ref"],
            "scopes": list(scopes),
        },
        "mcp": {
            "server": mcp["server"],
            "url": mcp["url"],
            "client_id": mcp["client_id"],
            "scope": mcp["scope"],
            "server_name": mcp["server_name"],
            "server_version": mcp["server_version"],
        },
        "session": {
            "request_id": session["request_id"],
            "principal_id": session["principal_id"],
            "role": session["role"],
        },
        "plugin": {
            "name": plugin["name"],
            "source": plugin["source"],
            "digest": plugin["digest"],
        },
        "tools_schema_digest": value["tools_schema_digest"],
    }
    # Constructing the typed objects re-validates every member.
    _typed_publication(document)
    return document


def publication_from_document(document: Mapping[str, Any]) -> ConsumerPublication:
    """Build the typed publication from a document.

    The document is validated first: a caller can never hand this function a
    shaped-but-unvalidated member.
    """
    return _typed_publication(validate_consumer_publication(document))


def _typed_publication(document: Mapping[str, Any]) -> ConsumerPublication:
    """Build the typed publication from an already validated document."""
    if document["schema"] in {CONTEXT_CONSUMER_SCHEMA, CURRENT_CONTEXT_CONSUMER_SCHEMA, DISCOVERY_CONSUMER_SCHEMA}:
        return _typed_context_publication(document)
    principal = document["principal"]
    mcp = document["mcp"]
    session = document["session"]
    plugin = document["plugin"]
    return ExecutiveConsumerPublication(
        work_ref=document["work_ref"],
        command=document["command"],
        job_id=document["job_id"],
        target_digest=document["target_digest"],
        root_job_id=document["root_job_id"],
        mission_authority_ref=document["mission_authority_ref"],
        authority_generation_digest=document["authority_generation_digest"],
        capability_profile_digest=document["capability_profile_digest"],
        principal_binding_digest=document["principal_binding_digest"],
        principal=ConsumerPrincipal(
            policy_id=principal["policy_id"],
            issuer_digest=principal["issuer_digest"],
            subject_digest=principal["subject_digest"],
            client_ref=principal["client_ref"],
            resource_ref=principal["resource_ref"],
            scopes=tuple(principal["scopes"]),
        ),
        mcp=ConsumerMcp(
            server=mcp["server"],
            url=mcp["url"],
            client_id=mcp["client_id"],
            scope=mcp["scope"],
            server_name=mcp["server_name"],
            server_version=mcp["server_version"],
        ),
        session=ConsumerSession(
            request_id=session["request_id"],
            principal_id=session["principal_id"],
            role=session["role"],
        ),
        plugin=ConsumerPlugin(
            name=plugin["name"], source=plugin["source"], digest=plugin["digest"],
        ),
        tools_schema_digest=document["tools_schema_digest"],
    )


class ConsumerSlot:
    """The original manager's sole qualification/registration outcome owner."""

    __slots__ = ("owner", "profile_id", "source", "plugin_id", "publication", "startup",
                 "_registration", "_lock", "manager", "scope", "package_path",
                 "package_check", "qualification_task", "qualification_worker", "qualification_key",
                 "qualification_outcome", "load_attempted", "loader_entered",
                 "loader_result", "loader_record", "load_outcome", "registration_context",
                 "registration_binding", "registration_error", "registration_attempted",
                 "memory_factory", "context_registration", "import_current",
                 "discovery_binding", "discovery_context", "discovery_attempted", "discovery_handles",
                 "discovery_registration", "discovery_error", "discovery_call", "discovery_last_call",
                 "discovery_last_result", "discovery_uncertain", "discovery_uncertain_call")

    def __init__(self, *, owner: str, profile_id: str, source: str, plugin_id: str,
                 publication: ConsumerPublication,
                 startup: NativeDelegateStartup | None = None) -> None:
        if any(type(value) is not str or not value
               for value in (owner, profile_id, source, plugin_id)):
            raise RuntimeRefusal("NATIVE_CONSUMER_SLOT_INVALID")
        if type(publication) not in (ExecutiveConsumerPublication, ExecutiveContextConsumerPublication):
            raise RuntimeRefusal("NATIVE_CONSUMER_SLOT_INVALID")
        if startup is not None and not isinstance(startup, NativeDelegateStartup):
            raise RuntimeRefusal("NATIVE_CONSUMER_SLOT_INVALID")
        self.owner, self.profile_id, self.source, self.plugin_id = owner, profile_id, source, plugin_id
        self.publication = publication
        has_child = selected_child_publication(publication) is not None
        if not has_child and startup is not None:
            raise RuntimeRefusal("NATIVE_CONSUMER_SLOT_INVALID")
        self.startup = startup if startup is not None else NativeDelegateStartup() if has_child else None
        self._registration = None
        self._lock = threading.RLock()
        self.manager = self.scope = self.package_path = self.package_check = None
        self.qualification_task = self.qualification_worker = self.qualification_key = None
        self.qualification_outcome = "UNBOUND"
        self.load_attempted = self.loader_entered = self.registration_attempted = False
        self.loader_result = self.loader_record = self.registration_context = self.registration_binding = None
        self.registration_error = None
        self.load_outcome = "NOT_ATTEMPTED"
        self.memory_factory = self.context_registration = None
        self.import_current = None
        self.discovery_binding = self.discovery_context = self.discovery_registration = None
        self.discovery_error = self.discovery_call = self.discovery_last_call = None
        self.discovery_last_result = self.discovery_uncertain = None
        self.discovery_uncertain_call = None
        self.discovery_attempted = False
        self.discovery_handles = []

    @property
    def delegate_binding(self):
        return None if self.startup is None else self.startup.binding

    def identities_match(self, *, owner: str, source: str, plugin_id: str,
                         profile_id: str | None = None,
                         publication: ExecutiveConsumerPublication | None = None) -> bool:
        return (self.owner == owner and self.source == source and self.plugin_id == plugin_id
                and (profile_id is None or self.profile_id == profile_id)
                and (publication is None or self.publication == publication))

    def bind_startup(self, startup: NativeDelegateStartup) -> None:
        if (not isinstance(startup, NativeDelegateStartup) or startup.binding is None
                or selected_child_publication(self.publication) is None):
            raise RuntimeRefusal("NATIVE_CONSUMER_SLOT_UNBOUND")
        with self._lock:
            if self.load_attempted or self.registration_attempted:
                raise RuntimeRefusal("NATIVE_CONSUMER_ORIGINAL_LOAD_RETAINED")
            if self.delegate_binding is not None and self.delegate_binding is not startup.binding:
                raise RuntimeRefusal("NATIVE_CONSUMER_SLOT_CONFLICT")
            self.startup = startup

    def begin_registration(self, ctx: Any) -> None:
        with self._lock:
            if (self.registration_attempted or self.delegate_binding is None
                    or getattr(ctx, "_manager", None) is not self.manager):
                raise NativeToolRegistrationError("NATIVE_CONSUMER_ORIGINAL_REGISTRATION_RETAINED")
            if not callable(self.package_check) or self.package_check() is not True:
                raise NativeToolRegistrationError("NATIVE_CONSUMER_PLUGIN_UNQUALIFIED")
            # Retain the original owners BEFORE C28 may mutate the native registry.
            self.registration_context = ctx
            self.registration_binding = self.delegate_binding
            self.registration_attempted = True
            self.load_outcome = "REGISTRATION_PENDING"

    def retain_registration_error(self, error: Exception) -> None:
        with self._lock:
            self.registration_error = error
            self.load_outcome = (
                "EFFECT_UNKNOWN" if getattr(error, "code", "") in {
                    "NATIVE_TOOL_REGISTRATION_EFFECT_UNKNOWN", "NATIVE_TOOL_ROLLBACK_EFFECT_UNKNOWN"}
                or not isinstance(error, NativeToolRegistrationError) else "REFUSED")

    def publish_registration(self, registration: NativeDelegateRegistration) -> None:
        if not isinstance(registration, NativeDelegateRegistration):
            raise RuntimeRefusal("NATIVE_CONSUMER_REGISTRATION_INVALID")
        with self._lock:
            binding = self.delegate_binding
            if (binding is None or registration.profile_id != binding.profile_id
                    or registration.session_id != binding.session_id
                    or registration.command != binding.command or registration.job_id != binding.job_id
                    or registration.scope != self.scope):
                raise RuntimeRefusal("NATIVE_CONSUMER_REGISTRATION_CONFLICT")
            current = self._registration
            if current is not None and current is not registration:
                raise RuntimeRefusal("NATIVE_CONSUMER_REGISTRATION_CONFLICT")
            self._registration = registration

    @property
    def registration(self) -> NativeDelegateRegistration | None:
        with self._lock:
            return self._registration



def install_consumer_slot(manager: Any, slot: ConsumerSlot) -> ConsumerSlot:
    """Return the actual original slot; never retarget an existing binding."""
    scope = getattr(manager, "scope_key", None)
    if type(scope) is not str or not scope or not isinstance(slot, ConsumerSlot):
        raise RuntimeRefusal("NATIVE_CONSUMER_MANAGER_INVALID")
    existing = getattr(manager, CONSUMER_SLOT_ATTRIBUTE, None)
    if existing is not None:
        if (not isinstance(existing, ConsumerSlot)
                or not existing.identities_match(
                    owner=slot.owner, source=slot.source, plugin_id=slot.plugin_id,
                    profile_id=slot.profile_id, publication=slot.publication)
                or existing.manager is not manager or existing.scope != scope
                or (slot.delegate_binding is not None
                    and existing.delegate_binding is not slot.delegate_binding)):
            raise RuntimeRefusal("NATIVE_CONSUMER_SLOT_CONFLICT")
        return existing
    if slot.manager is not None and (slot.manager is not manager or slot.scope != scope):
        raise RuntimeRefusal("NATIVE_CONSUMER_SLOT_CONFLICT")
    slot.manager, slot.scope = manager, scope
    setattr(manager, CONSUMER_SLOT_ATTRIBUTE, slot)
    return slot



def read_consumer_slot(ctx: Any, *, owner: str, source: str,
                       plugin_id: str) -> ConsumerSlot:
    """Read the slot through the actual plugin context, with identity checks.

    The context must be the real upstream ``PluginContext`` for the profile
    that owns the slot, and its manifest must be the expected non-bundled
    plugin. The profile is cross-checked: the slot records the profile the
    held native startup qualified, and the context reports the profile the
    upstream owner resolved for this load. Anything else refuses; an ordinary
    unbound discovery exposes no tool at all.
    """
    manager = getattr(ctx, "_manager", None)
    if manager is None or not hasattr(manager, "scope_key"):
        raise NativeToolRegistrationError("NATIVE_PLUGIN_CONTEXT_INVALID")
    slot = getattr(manager, CONSUMER_SLOT_ATTRIBUTE, None)
    if not isinstance(slot, ConsumerSlot):
        raise NativeToolRegistrationError("NATIVE_CONSUMER_SLOT_UNBOUND")
    if (not slot.identities_match(owner=owner, source=source, plugin_id=plugin_id)
            or slot.manager is not manager or slot.scope != manager.scope_key):
        raise NativeToolRegistrationError("NATIVE_CONSUMER_SLOT_FOREIGN")
    manifest = getattr(ctx, "manifest", None)
    if manifest is None:
        raise NativeToolRegistrationError("NATIVE_PLUGIN_CONTEXT_INVALID")
    if getattr(manifest, "source", None) != slot.source:
        raise NativeToolRegistrationError("NATIVE_CONSUMER_PLUGIN_SOURCE_MISMATCH")
    name = getattr(manifest, "name", None)
    if name != slot.plugin_id:
        raise NativeToolRegistrationError("NATIVE_CONSUMER_PLUGIN_ID_MISMATCH")
    reported = getattr(ctx, "profile_name", None)
    if type(reported) is not str or reported != slot.profile_id:
        raise NativeToolRegistrationError("NATIVE_PROFILE_MISMATCH")
    if (slot.package_path is None
            or str(getattr(manifest, "path", "")) != slot.package_path):
        raise NativeToolRegistrationError("NATIVE_CONSUMER_PLUGIN_PACKAGE_MISMATCH")
    return slot


class NativeConsumerCurrentness:
    """The synchronous proof that one binding is still the current one.

    It re-proves the live native facts that the binding was built from: the
    enrolled session identity, the captured MCP owner and the installed
    publication. It returns the literal ``True`` only when every one of them
    still holds, and ``False`` for anything else - including an exception.
    """

    __slots__ = ("_publication", "_session_id", "_instance_id", "_authority_epoch",
                 "_server", "_session", "_guard")

    def __init__(self, *, publication: ExecutiveConsumerPublication, session_id: str,
                 instance_id: str, authority_epoch: int, server: Any, session: Any,
                 guard: Callable[[], bool] | None = None) -> None:
        self._publication = publication
        self._session_id = session_id
        self._instance_id = instance_id
        self._authority_epoch = authority_epoch
        self._server = server
        self._session = session
        self._guard = guard

    def __call__(self) -> bool:
        try:
            if self._guard is None or self._guard() is not True:
                return False
            server = self._server
            if server is None or getattr(server, "session", None) is not self._session:
                return False
            if getattr(server, "session", None) is None:
                return False
            return True
        except Exception:
            return False

    @property
    def publication(self) -> ExecutiveConsumerPublication:
        return self._publication

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def instance_id(self) -> str:
        return self._instance_id

    @property
    def authority_epoch(self) -> int:
        return self._authority_epoch


class _ConsumerRefused(Exception):
    """A proved pre-send refusal: the transport was never called."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _ConsumerUncertain(Exception):
    """A possible send whose effect is unknown."""

    def __init__(self, message, *, original_future=None):
        super().__init__(message)
        self.original_future = original_future


class _ConsumerNotDispatched(_ConsumerUncertain):
    """The original caller proved refusal before session.call_tool entry."""


def _refusal_envelope(reason: str, publication: ExecutiveConsumerPublication) -> dict[str, Any]:
    """The canonical no-effect envelope the C28 adapter accepts."""
    return {
        "schema": SELECTED_CHILD_SCHEMA,
        "state": "REFUSED",
        "reason": reason,
        "command_id": publication.command,
        "job_id": publication.job_id,
        "attempt_id": None,
        "attempt_status": None,
        "job_status": None,
        "live_submit": False,
    }


class _NativeMcpCaller:
    """One RPC on the captured native loop, with checks at its actual send edge."""

    __slots__ = ("_server", "_session", "_loop", "_timeout", "_currentness", "_wait_for_lock")

    def __init__(self, *, server: Any, session: Any, loop: Any, timeout: float = 30.0,
                 currentness: Callable[[], bool] | None = None, wait_for_lock: bool = True) -> None:
        self._server, self._session, self._loop = server, session, loop
        self._timeout, self._currentness = float(timeout), currentness
        self._wait_for_lock = wait_for_lock

    @property
    def server(self): return self._server

    @property
    def session(self): return self._session

    @property
    def loop(self): return self._loop

    def _check(self):
        if (self._server is None or self._session is None or self._loop is None
                or getattr(self._server, "session", None) is not self._session
                or (self._currentness is not None and self._currentness() is not True)):
            raise _ConsumerUncertain("original native MCP binding is unavailable")

    def call(self, tool_name: str, arguments: Mapping[str, Any], *,
             currentness: Callable[[], bool] | None = None) -> Any:
        def check():
            self._check()
            if currentness is not None and currentness() is not True:
                raise _ConsumerUncertain("original native call binding is unavailable")
        try:
            check()
        except Exception as exc:
            raise _ConsumerNotDispatched("original native call refused before scheduling") from exc
        try:
            if asyncio.get_running_loop() is self._loop:
                raise _ConsumerNotDispatched("synchronous RPC cannot block its owner loop")
        except RuntimeError:
            pass
        server, session, loop = self._server, self._session, self._loop
        payload = dict(arguments)

        async def exchange():
            lock = getattr(server, "_rpc_lock", None)
            inflight = getattr(server, "_inflight_tasks", None)
            task = asyncio.current_task()
            if lock is None:
                raise _ConsumerNotDispatched("native RPC lock is unavailable")
            # Context reads do not queue behind a still-owned SDK request after
            # its observer timed out. Check on the original loop, without any
            # await before acquisition; the incumbent lock/inflight set remain
            # the sole custody mechanism. Legacy callers keep their behavior.
            if not self._wait_for_lock:
                from collections import deque
                waiters = getattr(lock, "_waiters", False)
                # asyncio.Lock fairness can suspend an unlocked acquire while
                # an older waiter is waking. Qualify that incumbent shape too.
                if (type(lock) is not asyncio.Lock or type(inflight) is not set
                        or type(waiters) not in (type(None), deque)
                        or lock.locked() or waiters or inflight):
                    raise _ConsumerNotDispatched("original native RPC is still in flight")
            async with lock:
                # The connection/authority may change while waiting for this lock.
                try:
                    check()
                except Exception as exc:
                    raise _ConsumerNotDispatched("original native call refused at send edge") from exc
                if inflight is not None and task is not None:
                    inflight.add(task)
                try:
                    try:
                        result = await session.call_tool(tool_name, arguments=payload)
                        check()
                        return result
                    except _ConsumerNotDispatched as exc:
                        # Only this caller's pre-entry checks can prove no send.
                        # A session/late guard exception cannot borrow that fact.
                        raise _ConsumerUncertain("native RPC failed after send entry") from exc
                finally:
                    if inflight is not None and task is not None:
                        inflight.discard(task)

        coroutine = exchange()
        try:
            future = asyncio.run_coroutine_threadsafe(coroutine, loop)
        except Exception as exc:
            coroutine.close()
            raise _ConsumerUncertain("native RPC scheduling failed") from exc
        try:
            return future.result(timeout=self._timeout)
        except concurrent.futures.TimeoutError as exc:
            future.add_done_callback(_consume_future_result)
            raise _ConsumerUncertain("native RPC timed out; original request retained", original_future=future) from exc
        except _ConsumerNotDispatched:
            raise
        except Exception as exc:
            raise _ConsumerUncertain("native RPC failed") from exc



class NativeExecutiveTransport:
    """One original RPC; late uncertainty preserves C28 command identity."""

    def __init__(self, *, publication: ExecutiveConsumerPublication, server: Any,
                 session: Any, loop: Any, timeout: float = 30.0,
                 currentness: Callable[[], bool] | None = None,
                 trust_gate: Callable[[], str | None] | None = None) -> None:
        self._publication = publication
        self._caller = _NativeMcpCaller(
            server=server, session=session, loop=loop, timeout=timeout, currentness=currentness)
        self._currentness, self._trust_gate = currentness, trust_gate

    @property
    def publication(self): return self._publication

    def submit_selected_child(self, command_id): return self._call("selected_child_submit", command_id)

    def selected_child_status(self, command_id): return self._call("selected_child_status", command_id)

    def _call(self, action, command_id):
        publication = self._publication
        try:
            if command_id != publication.command:
                raise _ConsumerRefused("NATIVE_COMMAND_MISMATCH")
            if self._currentness is not None and self._currentness() is not True:
                raise _ConsumerRefused("NATIVE_BINDING_STALE")
            if self._trust_gate is not None and self._trust_gate() is not None:
                raise _ConsumerRefused("NATIVE_MCP_TRUST_REFUSED")
        except _ConsumerRefused as exc:
            return _refusal_envelope(exc.reason, publication)
        try:
            raw = self._caller.call(TOOL_NAME, {"action": action, "command": publication.command})
            envelope = self._unwrap(raw, action=action)
            if envelope is None or (self._currentness is not None and self._currentness() is not True):
                raise _ConsumerUncertain("native result or original binding is unavailable")
            return envelope
        except _ConsumerUncertain:
            raise
        except Exception as exc:
            raise _ConsumerUncertain("native RPC outcome unavailable") from exc

    def _unwrap(self, raw: Any, *, action: str) -> Mapping[str, Any] | None:
        from integrations.hermes_delegate.executive import (
            validate_selected_child_ingress_envelope, validate_selected_child_local_envelope)
        body = _native_result_body(raw)
        if type(body) is not dict:
            return None
        if body.get("schema") != SELECTED_CHILD_SCHEMA and type(body.get("data")) is dict:
            body = body["data"]
        publication = self._publication
        try:
            if "target_digest" in body:
                return validate_selected_child_ingress_envelope(
                    body, command_id=publication.command, job_id=publication.job_id,
                    target_digest=publication.target_digest)
            return validate_selected_child_local_envelope(
                body, command_id=publication.command, action=action)
        except (ValueError, TypeError, KeyError):
            return None


def _native_result_body(raw):
    if raw is None:
        return None
    if not isinstance(raw, Mapping) and callable(getattr(raw, "model_dump", None)):
        # Both reviewed SDK generations serialize the same wire aliases.
        # In particular, SDK 2.3's is_error must not bypass the error check.
        raw = raw.model_dump(by_alias=True)
        if type(raw) is not dict:
            return None
    def member(name, fallback=None):
        return raw.get(name, fallback) if isinstance(raw, Mapping) else getattr(raw, name, fallback)
    if member("isError") is True or member("is_error") is True:
        return None
    if member("resultType", member("result_type", "complete")) != "complete":
        return None
    body = member("structuredContent", member("structured_content"))
    if body is None:
        body = member("content", raw)
        if isinstance(body, (list, tuple)):
            pieces = [item.get("text") if isinstance(item, Mapping) else getattr(item, "text", None)
                      for item in body]
            if len(pieces) != 1 or type(pieces[0]) is not str:
                return None
            body = pieces[0]
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except (ValueError, TypeError):
            return None
    return body if type(body) is dict else None



def _consume_future_result(future: Any) -> None:
    """Observe a finished future's outcome so the loop stays quiet."""
    try:
        future.exception()
    except (asyncio.CancelledError, Exception):
        pass


def publication_server_name(publication: ExecutiveConsumerPublication) -> str:
    """The MCP server name the publication binds the connection to."""
    return publication.mcp.server


def plugin_package_digest(root: Any) -> str:
    """Digest of one installed plugin package: its manifest and module bytes.

    The package is sealed: the installer publishes this digest over the
    release source, and the consumer recomputes it over the installed bytes
    before the loader imports anything. A symlinked or missing member refuses.
    """
    from pathlib import Path

    base = Path(root)
    files: dict[str, str] = {}
    for name in ("plugin.yaml", "__init__.py"):
        path = base / name
        try:
            if path.is_symlink() or not path.is_file():
                raise RuntimeRefusal("NATIVE_CONSUMER_PLUGIN_PACKAGE_INVALID")
            data = path.read_bytes()
        except OSError:
            raise RuntimeRefusal("NATIVE_CONSUMER_PLUGIN_PACKAGE_INVALID") from None
        files[name] = hashlib.sha256(data).hexdigest()
    return hashlib.sha256(_canonical(files)).hexdigest()



def held_plugin_package_digest(owner: Any) -> str:
    """Read the fixed package through the existing held release capability."""
    relative = "integrations/hermes_harness/" + CONSUMER_PLUGIN_NAME
    owner.directory(relative)
    files = {name: hashlib.sha256(owner.source(relative + "/" + name)).hexdigest()
             for name in ("plugin.yaml", "__init__.py")}
    owner.check()
    return hashlib.sha256(_canonical(files)).hexdigest()


def capture_native_mcp_owner(publication: ExecutiveConsumerPublication, *, include_guard=False):
    """Capture one exact scoped owner and a non-retargeting currentness check."""
    from tools import mcp_tool as core
    from tools.mcp_tool_loop import _running_loop
    from tools.mcp_tool_scope import _resolve_server_key
    try:
        key = _resolve_server_key(publication.mcp.server)
        with core._lock:
            server = core._servers.get(key)
        session = getattr(server, "session", None)
        loop = _running_loop()
    except Exception:
        raise RuntimeRefusal("NATIVE_CONSUMER_MCP_SERVER_UNAVAILABLE") from None

    def current():
        try:
            with core._lock:
                same_owner = core._servers.get(key) is server
            initialized = getattr(server, "initialize_result", None)
            if callable(getattr(initialized, "model_dump", None)):
                value = initialized.model_dump(by_alias=True, exclude_none=True)
                info = value.get("serverInfo") if type(value) is dict else None
                name = info.get("name") if type(info) is dict else None
                version = info.get("version") if type(info) is dict else None
            else:
                info = getattr(initialized, "serverInfo", None)
                name, version = getattr(info, "name", None), getattr(info, "version", None)
            return (server is not None and session is not None and loop is not None
                    and same_owner and _running_loop() is loop
                    and getattr(server, "session", None) is session
                    and name == publication.mcp.server_name
                    and version == publication.mcp.server_version
                    and tools_schema_digest(getattr(server, "_tools", ())) == publication.tools_schema_digest
                    and publication.mcp.matches_config(getattr(server, "_config", None)))
        except Exception:
            return False
    if not current():
        raise RuntimeRefusal("NATIVE_CONSUMER_MCP_CONTRACT_UNAVAILABLE")
    return (server, session, loop, current) if include_guard else (server, session, loop)





def install_native_consumer(
    *, manager: Any, publication: ConsumerPublication, owner: str,
    profile_id: str, session_id: str, instance_id: str, authority_epoch: int,
    route: str | None, server: Any, session: Any, loop: Any, timeout: float = 30.0,
    trust_gate: Callable[[], str | None] | None = None,
    session_guard: Callable[[], bool] | None = None,
    manifest: Any = None, package_check: Callable[[], bool] | None = None,
) -> ConsumerSlot:
    """Retain the original slot before qualification and native registration."""
    slot = install_consumer_slot(manager, ConsumerSlot(
        owner=owner, profile_id=profile_id, source=CONSUMER_PLUGIN_SOURCE,
        plugin_id=CONSUMER_PLUGIN_NAME, publication=publication))
    if slot.load_attempted:
        # Success and uncertainty both retain this exact original registration.
        return slot
    if (manifest is None or not callable(package_check) or package_check() is not True
            or getattr(manifest, "source", None) != CONSUMER_PLUGIN_SOURCE
            or getattr(manifest, "name", None) != CONSUMER_PLUGIN_NAME
            or not callable(session_guard) or session_guard() is not True):
        raise RuntimeRefusal("NATIVE_CONSUMER_STARTUP_UNQUALIFIED")
    package_path = str(getattr(manifest, "path", ""))
    if not package_path or (slot.package_path is not None and slot.package_path != package_path):
        raise RuntimeRefusal("NATIVE_CONSUMER_PLUGIN_PACKAGE_MISMATCH")
    slot.package_path, slot.package_check = package_path, package_check
    context_required = type(publication) is ExecutiveContextConsumerPublication
    if context_required:
        from integrations.hermes_runtime.native_agentos_memory import NativeAgentOsMemoryFactory
        if (type(slot.memory_factory) is not NativeAgentOsMemoryFactory
                or not slot.memory_factory.loader_ready()):
            raise RuntimeRefusal("NATIVE_AGENTOS_FACTORY_UNAVAILABLE")
    child = selected_child_publication(publication)
    discovery_required = context_required and publication.discovery
    if discovery_required:
        from .native_discovery_tools import qualify_binding
        if slot.discovery_binding is not None:
            raise RuntimeRefusal("NATIVE_CONSUMER_ORIGINAL_LOAD_RETAINED")
        slot.discovery_binding = qualify_binding(slot=slot, server=server, session=session, loop=loop,
            profile_id=profile_id, session_id=session_id, session_key=route,
            currentness=session_guard, trust_gate=trust_gate, timeout=timeout)
    if child is not None:
        caller = _NativeMcpCaller(server=server, session=session, loop=loop,
                                 timeout=timeout, currentness=session_guard)
        binding = qualify_executive_consumer(
            publication=child, caller=caller, profile_id=profile_id, session_id=session_id,
            instance_id=instance_id, authority_epoch=authority_epoch, session_key=route,
            task_id=None, timeout=timeout, trust_gate=trust_gate, currentness=session_guard)
        slot.bind_startup(NativeDelegateStartup(binding=binding))
    if package_check() is not True or session_guard() is not True:
        raise RuntimeRefusal("NATIVE_CONSUMER_STARTUP_CHANGED")
    with slot._lock:
        if slot.load_attempted:
            return slot
        slot.load_attempted = True
        slot.load_outcome = "LOAD_PENDING"
    try:
        slot.loader_result = manager._load_plugin(manifest)
    except Exception as error:
        slot.retain_registration_error(error)
        raise
    loaded = getattr(manager, "_plugins", {}).get(CONSUMER_PLUGIN_NAME)
    if ((child is not None and slot.registration is None)
            or (context_required and slot.context_registration is None)
            or (discovery_required and (slot.discovery_registration is None or slot.discovery_error is not None))
            or slot.registration_error is not None
            or loaded is None or getattr(loaded, "enabled", None) is not True
            or getattr(loaded, "error", None) is not None
            or getattr(loaded, "manifest", None) is not manifest):
        if slot.load_outcome not in {"EFFECT_UNKNOWN", "REFUSED"}:
            slot.load_outcome = "EFFECT_UNKNOWN" if slot.registration_attempted or slot.discovery_attempted else "REFUSED"
        return slot
    if package_check() is not True or session_guard() is not True:
        slot.load_outcome = "CURRENTNESS_UNAVAILABLE"
        return slot
    slot.loader_record = loaded
    slot.load_outcome = "REGISTERED" if child is not None else "CONTEXT_REGISTERED"
    if discovery_required:
        from .native_discovery_tools import registration_current
        if not registration_current(slot.discovery_binding):
            slot.load_outcome = "CURRENTNESS_UNAVAILABLE"
    return slot



def _mandate_schema() -> str:
    """The incumbent mandate projection's schema identity."""
    from control_plane.coo_principal_mandate import SCHEMA
    return SCHEMA


def _unwrap_mandate(raw: Any) -> Mapping[str, Any] | None:
    body = _native_result_body(raw)
    if type(body) is not dict:
        return None
    schema = _mandate_schema()
    if body.get("schema") == schema:
        return body
    data = body.get("data")
    return data if type(data) is dict and data.get("schema") == schema else None



def read_mandate(caller: _NativeMcpCaller, publication: ExecutiveConsumerPublication,
                 ) -> Mapping[str, Any]:
    """Read the authenticated Executive mandate for the frozen work reference.

    This is the incumbent ``executive_mandate`` read. It is performed once,
    on the same captured owner, with the same closed request the model could
    never make.
    """
    raw = caller.call(CONSUMER_MANDATE_TOOL, {"work_ref": publication.work_ref})
    mandate = _unwrap_mandate(raw)
    if mandate is None:
        raise RuntimeRefusal("NATIVE_CONSUMER_MANDATE_UNAVAILABLE")
    return mandate


def compare_mandate(mandate: Mapping[str, Any],
                    publication: ExecutiveConsumerPublication) -> None:
    """Compare the authenticated mandate with the explicit installed enrollment.

    Every join is compared: the principal policy, issuer, subject, client,
    resource and scopes, the principal binding digest, the mission work
    reference, root, authority reference and authority generation, and the
    capability profile digest. A difference refuses the registration; it is
    never repaired, inferred or re-bound.
    """
    principal = mandate.get("principal")
    mission = mandate.get("mission")
    capability = mandate.get("capability")
    if not isinstance(principal, Mapping) or not isinstance(mission, Mapping) \
            or not isinstance(capability, Mapping):
        raise RuntimeRefusal("NATIVE_CONSUMER_MANDATE_MISMATCH")
    if not publication.principal.matches(principal):
        raise RuntimeRefusal("NATIVE_CONSUMER_PRINCIPAL_MISMATCH")
    if principal.get("principal_binding_digest") != publication.principal_binding_digest:
        raise RuntimeRefusal("NATIVE_CONSUMER_PRINCIPAL_BINDING_MISMATCH")
    if mission.get("work_ref") != publication.work_ref:
        raise RuntimeRefusal("NATIVE_CONSUMER_WORK_REF_MISMATCH")
    if mission.get("root_job_id") != publication.root_job_id:
        raise RuntimeRefusal("NATIVE_CONSUMER_ROOT_MISMATCH")
    if mission.get("mission_authority_ref") != publication.mission_authority_ref:
        raise RuntimeRefusal("NATIVE_CONSUMER_AUTHORITY_MISMATCH")
    if mission.get("authority_generation_digest") != publication.authority_generation_digest:
        raise RuntimeRefusal("NATIVE_CONSUMER_AUTHORITY_GENERATION_MISMATCH")
    if capability.get("capability_profile_digest") != publication.capability_profile_digest:
        raise RuntimeRefusal("NATIVE_CONSUMER_CAPABILITY_MISMATCH")


def qualify_executive_consumer(
    *,
    publication: ExecutiveConsumerPublication,
    caller: _NativeMcpCaller,
    profile_id: str,
    session_id: str,
    instance_id: str,
    authority_epoch: int,
    session_key: str | None = None,
    task_id: str | None = None,
    timeout: float = 30.0,
    trust_gate: Callable[[], str | None] | None = None,
    currentness: Callable[[], bool] | None = None,
) -> NativeDelegateBinding:
    """Prove the ready process, the frozen target and the authenticated connection.

    The order is fixed and every step is proved before the next one starts:

    1. the authenticated Executive mandate for the frozen work reference is
       read once and compared with the explicit installed enrollment;
    2. one harmless ``selected_child_status`` for the frozen command proves
       the canonical command, the canonical Job and the frozen target digest;
    3. only then is the immutable binding built.

    A new-effect closure does not disable this: the qualified status read and
    the authorized original replay stay available. Fresh admission belongs to
    the incumbent C17 closure, not to this consumer.
    """
    if type(session_id) is not str or not session_id:
        raise RuntimeRefusal("NATIVE_CONSUMER_SESSION_INVALID")
    if type(instance_id) is not str or not instance_id:
        raise RuntimeRefusal("NATIVE_CONSUMER_SESSION_INVALID")
    if type(authority_epoch) is not int or authority_epoch < 1:
        raise RuntimeRefusal("NATIVE_CONSUMER_SESSION_INVALID")

    mandate = read_mandate(caller, publication)
    compare_mandate(mandate, publication)

    guard = NativeConsumerCurrentness(
        publication=publication, session_id=session_id, instance_id=instance_id,
        authority_epoch=authority_epoch, server=caller.server, session=caller.session,
        guard=currentness)
    # The qualification read is the operator's own read of its own
    # connection; it is not a model dispatch and does not pass the
    # model-facing trust gate.
    qualification = NativeExecutiveTransport(
        publication=publication, server=caller.server, session=caller.session,
        loop=caller.loop, timeout=timeout, currentness=guard)
    # One harmless read of the frozen command. It proves the canonical
    # command, the canonical Job and the frozen target digest.
    envelope = qualification.selected_child_status(publication.command)
    if envelope.get("state") == "REFUSED":
        raise RuntimeRefusal("NATIVE_CONSUMER_STATUS_REFUSED")
    if envelope.get("command_id") != publication.command:
        raise RuntimeRefusal("NATIVE_CONSUMER_COMMAND_MISMATCH")
    if envelope.get("job_id") != publication.job_id:
        raise RuntimeRefusal("NATIVE_CONSUMER_JOB_MISMATCH")
    if envelope.get("target_digest") != publication.target_digest:
        raise RuntimeRefusal("NATIVE_CONSUMER_TARGET_DIGEST_MISMATCH")

    if guard() is not True:
        raise RuntimeRefusal("NATIVE_CONSUMER_STARTUP_CHANGED")
    binding = NativeDelegateBinding(
        transport=NativeExecutiveTransport(
            publication=publication, server=caller.server, session=caller.session,
            loop=caller.loop, timeout=timeout, currentness=guard, trust_gate=trust_gate),
        currentness_guard=guard,
        profile_id=profile_id,
        session_id=session_id,
        command=publication.command,
        job_id=publication.job_id,
        session_key=session_key,
        task_id=task_id,
    )
    return binding
