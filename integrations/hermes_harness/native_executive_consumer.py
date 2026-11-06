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
    "frozen_material_digest",
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


def frozen_material_digest(material: Mapping[str, Any]) -> str:
    """Deterministic equality digest over the frozen target material.

    This is an *equality* check over material equality, never an authority and
    never an operation identity. The callable that C29's target carries is not
    part of the material and cannot be digested.
    """
    if not isinstance(material, Mapping):
        raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
    return hashlib.sha256(_canonical(dict(material))).hexdigest()


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
    """Digest of one MCP server's complete discovered tool schema.

    The digest covers every discovered tool's name, description and input
    schema, sorted by name. It is compared against the frozen publication, so
    a server that grew, shrank or changed a tool can never be mistaken for the
    reviewed Executive ingress.
    """
    if tools is None or not isinstance(tools, (list, tuple)):
        raise RuntimeRefusal("NATIVE_CONSUMER_TOOLS_SCHEMA_INVALID")
    rows = []
    for tool in tools:
        name = getattr(tool, "name", None)
        if type(name) is not str or not name:
            raise RuntimeRefusal("NATIVE_CONSUMER_TOOLS_SCHEMA_INVALID")
        schema = getattr(tool, "inputSchema", None)
        if schema is None:
            schema = getattr(tool, "input_schema", None)
        description = getattr(tool, "description", None)
        rows.append({
            "name": name,
            "description": description if type(description) is str else "",
            "input_schema": schema if isinstance(schema, Mapping) else {},
        })
    if len(rows) != len({row["name"] for row in rows}):
        raise RuntimeRefusal("NATIVE_CONSUMER_TOOLS_SCHEMA_INVALID")
    rows.sort(key=lambda row: row["name"])
    return hashlib.sha256(_canonical(rows)).hexdigest()


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

    def __post_init__(self) -> None:
        _text(self.server, "server")
        if type(self.url) is not str or not 1 < len(self.url) <= _MAX_URL:
            raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
        if not self.url.startswith("https://") and not self.url.startswith("http://127.0.0.1"):
            # A native Executive ingress is loopback- or TLS-terminated. A
            # plaintext remote route is refused here rather than published.
            raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
        _text(self.client_id, "client_id", _CLIENT_REF_RE)
        if type(self.scope) is not str or _OAUTH_SCOPE_RE.fullmatch(self.scope) is None:
            raise RuntimeRefusal("NATIVE_CONSUMER_PUBLICATION_INVALID")
        _text(self.server_name, "server_name")
        _text(self.server_version, "server_version")

    def matches_config(self, config: Any) -> bool:
        """Compare the live connection's own config with the approved facts."""
        if not isinstance(config, Mapping):
            return False
        oauth = config.get("oauth")
        if not isinstance(oauth, Mapping):
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

    def frozen_material(self) -> dict[str, Any]:
        """The material the target digest is computed over.

        This is the *equality* material of the frozen child: the work
        reference, the command, the Job and the mission joins. The C30
        producer must publish exactly this material for the digests to match.
        """
        return {
            "work_ref": self.work_ref,
            "command": self.command,
            "job_id": self.job_id,
            "root_job_id": self.root_job_id,
            "mission_authority_ref": self.mission_authority_ref,
            "authority_generation_digest": self.authority_generation_digest,
            "capability_profile_digest": self.capability_profile_digest,
            "principal_binding_digest": self.principal_binding_digest,
        }


def validate_consumer_publication(value: Any) -> dict[str, Any]:
    """Validate one closed publication document and return its detached form.

    An absent member is ``None`` at the call site; a malformed member refuses
    here. No credential, bearer template, client secret, private path or
    authority boolean is accepted: the closed key set cannot carry one.
    """
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


def publication_from_document(document: Mapping[str, Any]) -> ExecutiveConsumerPublication:
    """Build the typed publication from a document.

    The document is validated first: a caller can never hand this function a
    shaped-but-unvalidated member.
    """
    return _typed_publication(validate_consumer_publication(document))


def _typed_publication(document: Mapping[str, Any]) -> ExecutiveConsumerPublication:
    """Build the typed publication from an already validated document."""
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
    """The fixed typed owner-private slot on one per-profile PluginManager.

    The held native startup owns the slot. The plugin loader reads it through
    the typed accessors below. The slot carries the *one* immutable startup
    and, after a proved registration, the *one* registration receipt. A second
    different registration is refused: the original context and lease stay.
    """

    __slots__ = ("owner", "profile_id", "source", "plugin_id", "publication", "startup",
                 "_registration", "_lock")

    def __init__(self, *, owner: str, profile_id: str, source: str, plugin_id: str,
                 publication: "ExecutiveConsumerPublication",
                 startup: NativeDelegateStartup) -> None:
        if (type(owner) is not str or not owner
                or type(profile_id) is not str or not profile_id
                or type(source) is not str or not source
                or type(plugin_id) is not str or not plugin_id):
            raise RuntimeRefusal("NATIVE_CONSUMER_SLOT_INVALID")
        if not isinstance(publication, ExecutiveConsumerPublication):
            raise RuntimeRefusal("NATIVE_CONSUMER_SLOT_INVALID")
        if not isinstance(startup, NativeDelegateStartup):
            raise RuntimeRefusal("NATIVE_CONSUMER_SLOT_INVALID")
        if startup.binding is None:
            raise RuntimeRefusal("NATIVE_CONSUMER_SLOT_UNBOUND")
        self.owner = owner
        self.profile_id = profile_id
        self.source = source
        self.plugin_id = plugin_id
        self.publication = publication
        self.startup = startup
        self._registration: NativeDelegateRegistration | None = None
        self._lock = threading.Lock()

    def publish_registration(self, registration: NativeDelegateRegistration) -> None:
        """Record the one registration this slot may ever own."""
        if not isinstance(registration, NativeDelegateRegistration):
            raise RuntimeRefusal("NATIVE_CONSUMER_REGISTRATION_INVALID")
        with self._lock:
            current = self._registration
            if current is None:
                self._registration = registration
                return
            if (current.name != registration.name or current.scope != registration.scope
                    or current.handler is not registration.handler
                    or current.check_fn is not registration.check_fn):
                # A second, different registration never replaces the first.
                raise RuntimeRefusal("NATIVE_CONSUMER_REGISTRATION_CONFLICT")

    @property
    def registration(self) -> NativeDelegateRegistration | None:
        with self._lock:
            return self._registration

    def identities_match(self, *, owner: str, source: str, plugin_id: str) -> bool:
        return (self.owner == owner and self.source == source
                and self.plugin_id == plugin_id)


def install_consumer_slot(manager: Any, slot: ConsumerSlot) -> ConsumerSlot:
    """Install the slot on the ACTUAL per-profile PluginManager.

    The manager is the object the upstream owner created for this profile. A
    manager that already carries a *different* slot is refused: a reconnect,
    a settings change or another profile must never retarget a live
    registration.
    """
    if manager is None or not hasattr(manager, "scope_key"):
        raise RuntimeRefusal("NATIVE_CONSUMER_MANAGER_INVALID")
    if not isinstance(slot, ConsumerSlot):
        raise RuntimeRefusal("NATIVE_CONSUMER_SLOT_INVALID")
    existing = getattr(manager, CONSUMER_SLOT_ATTRIBUTE, None)
    if existing is not None:
        if not isinstance(existing, ConsumerSlot) or not existing.identities_match(
                owner=slot.owner, source=slot.source, plugin_id=slot.plugin_id):
            raise RuntimeRefusal("NATIVE_CONSUMER_SLOT_CONFLICT")
        return existing
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
    if not slot.identities_match(owner=owner, source=source, plugin_id=plugin_id):
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
            if self._guard is not None and self._guard() is not True:
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
    """One ``tools/call`` on one captured native MCP owner.

    The caller owns no connection. It uses the *captured* ``MCPServerTask`` and
    its live ``ClientSession``, on the MCP owner's own loop, under the
    incumbent RPC lock and inflight bookkeeping. It never opens a session,
    discovers a server, reconnects, replays, cancels or handles a token.

    A lost response, a timeout or a transport error is *uncertain*: the caller
    raises and never retries, cancels or re-keys the request.
    """

    __slots__ = ("_server", "_session", "_loop", "_timeout")

    def __init__(self, *, server: Any, session: Any, loop: Any, timeout: float = 30.0) -> None:
        self._server = server
        self._session = session
        self._loop = loop
        self._timeout = float(timeout)

    @property
    def server(self) -> Any:
        return self._server

    @property
    def session(self) -> Any:
        return self._session

    @property
    def loop(self) -> Any:
        return self._loop

    def call(self, tool_name: str, arguments: Mapping[str, Any]) -> Any:
        """Send exactly one request and return the raw MCP result."""
        server = self._server
        session = self._session
        loop = self._loop
        if server is None or session is None or loop is None:
            raise _ConsumerUncertain("native mcp owner is unavailable")
        if getattr(server, "session", None) is not session:
            # The captured session was replaced (a reconnect). Never call the
            # replacement: the binding owns the session it was qualified on.
            raise _ConsumerUncertain("native mcp session changed")
        payload = dict(arguments)

        async def _call() -> Any:
            lock = getattr(server, "_rpc_lock", None)
            inflight = getattr(server, "_inflight_tasks", None)
            task = asyncio.current_task()
            if lock is None:
                raise RuntimeError("native mcp owner has no rpc lock")
            async with lock:
                if inflight is not None and task is not None:
                    inflight.add(task)
                try:
                    return await session.call_tool(tool_name, arguments=payload)
                finally:
                    if inflight is not None and task is not None:
                        inflight.discard(task)

        try:
            future = asyncio.run_coroutine_threadsafe(_call(), loop)
        except Exception as exc:
            raise _ConsumerUncertain("native rpc scheduling failed") from exc
        try:
            return future.result(timeout=self._timeout)
        except concurrent.futures.TimeoutError as exc:
            # The send may already have happened. Do not cancel, retry or
            # re-key it: the original command stays uncertain.
            future.add_done_callback(_consume_future_result)
            raise _ConsumerUncertain("native rpc timed out") from exc
        except Exception as exc:
            raise _ConsumerUncertain("native rpc failed") from exc


class NativeExecutiveTransport:
    """One RPC per action on the captured native MCP owner.

    The transport owns no connection. It uses the *captured* ``MCPServerTask``
    and its live ``ClientSession``, on the MCP owner's own loop, under the
    incumbent RPC lock and inflight bookkeeping. It never opens a session,
    discovers a server, reconnects, replays, cancels or handles a token.

    A pre-send refusal returns the canonical ``REFUSED`` envelope. Anything
    after a possible send raises, and the C28 adapter turns that into the
    original command's ``EFFECT_UNKNOWN`` (submit) or ``UNAVAILABLE`` (status).
    """

    def __init__(self, *, publication: ExecutiveConsumerPublication, server: Any,
                 session: Any, loop: Any, timeout: float = 30.0,
                 currentness: Callable[[], bool] | None = None,
                 trust_gate: Callable[[], str | None] | None = None) -> None:
        self._publication = publication
        self._caller = _NativeMcpCaller(server=server, session=session, loop=loop,
                                        timeout=timeout)
        self._currentness = currentness
        self._trust_gate = trust_gate

    @property
    def publication(self) -> ExecutiveConsumerPublication:
        return self._publication

    # -- the two closed entries the C28 adapter uses -------------------

    def submit_selected_child(self, command_id: str) -> Mapping[str, Any]:
        return self._call("selected_child_submit", command_id)

    def selected_child_status(self, command_id: str) -> Mapping[str, Any]:
        return self._call("selected_child_status", command_id)

    # -- the one RPC ---------------------------------------------------

    def _call(self, action: str, command_id: str) -> Mapping[str, Any]:
        publication = self._publication
        try:
            if command_id != publication.command:
                raise _ConsumerRefused("NATIVE_COMMAND_MISMATCH")
            if self._currentness is not None and self._currentness() is not True:
                raise _ConsumerRefused("NATIVE_BINDING_STALE")
            if self._trust_gate is not None:
                refusal = self._trust_gate()
                if refusal is not None:
                    # A proved pre-send refusal: the incumbent trust gate
                    # refused before any transport work, so nothing was sent.
                    raise _ConsumerRefused("NATIVE_MCP_TRUST_REFUSED")
        except _ConsumerRefused as exc:
            # A proved no-effect: the transport was never called. The C28
            # adapter accepts the canonical REFUSED envelope unchanged.
            return _refusal_envelope(exc.reason, publication)
        payload = {"action": action, "command": publication.command}
        try:
            raw = self._caller.call(TOOL_NAME, payload)
        except _ConsumerUncertain:
            raise
        except Exception:
            raise _ConsumerUncertain("native rpc failed")
        envelope = self._unwrap(raw)
        if envelope is None:
            raise _ConsumerUncertain("native rpc returned an unusable envelope")
        return envelope

    def _unwrap(self, raw: Any) -> Mapping[str, Any] | None:
        """Unwrap the real structured content of one MCP tool result.

        ``isError=False`` or a success-looking string is not proof. The
        envelope must carry the canonical schema, the original command and Job,
        and the frozen target digest.
        """
        if raw is None:
            return None
        is_error = getattr(raw, "isError", None)
        if is_error is None and isinstance(raw, Mapping):
            is_error = raw.get("isError")
        if is_error is True:
            # The protocol-level error flag is never proof of an effect.
            return None
        content = getattr(raw, "structuredContent", None)
        if content is None:
            content = getattr(raw, "structured_content", None)
        body: Any = content
        if body is None:
            text = getattr(raw, "content", None)
            if text is None:
                text = raw
            if isinstance(text, (list, tuple)):
                pieces = []
                for item in text:
                    value = getattr(item, "text", None)
                    if value is None and isinstance(item, Mapping):
                        value = item.get("text")
                    if isinstance(value, str):
                        pieces.append(value)
                text = "".join(pieces)
            if isinstance(text, str):
                try:
                    body = json.loads(text)
                except (TypeError, ValueError):
                    return None
            else:
                body = text
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except (TypeError, ValueError):
                return None
        if not isinstance(body, Mapping):
            return None
        # The App wraps the tool result in its own envelope. Accept either the
        # bare selected-child envelope or the wrapped one, but only when the
        # wrapped payload proves the same original command.
        if body.get("schema") != SELECTED_CHILD_SCHEMA and isinstance(body.get("data"), Mapping):
            body = body["data"]
        if body.get("schema") != SELECTED_CHILD_SCHEMA:
            return None
        publication = self._publication
        if body.get("command_id") != publication.command:
            return None
        if body.get("job_id") != publication.job_id:
            return None
        digest = body.get("target_digest")
        if digest != publication.target_digest:
            # The C29/C30 join adds ``target_digest`` to the authenticated
            # response. A response without it, or with another value, is not
            # the frozen target and can never be projected to the model.
            return None
        return dict(body)


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


def capture_native_mcp_owner(publication: ExecutiveConsumerPublication):
    """Capture the genuine SAME-profile MCP owner of the Executive server.

    The capture proves four things before anything is registered: the
    connection is the live one of this profile, the handshake advertised the
    reviewed server identity, the complete discovered tool schema is the
    reviewed C29 schema, and the connection was opened with the approved
    route, OAuth client and scope.

    A cached, configured or merely-connected boolean is never accepted.
    """
    from tools import mcp_tool as core
    from tools.mcp_tool_loop import _running_loop
    from tools.mcp_tool_scope import _resolve_server_key

    server_name = publication.mcp.server
    try:
        key = _resolve_server_key(server_name)
        with core._lock:
            server = core._servers.get(key)
    except Exception:
        raise RuntimeRefusal("NATIVE_CONSUMER_MCP_SERVER_UNAVAILABLE") from None
    if server is None:
        raise RuntimeRefusal("NATIVE_CONSUMER_MCP_SERVER_UNAVAILABLE")
    session = getattr(server, "session", None)
    if session is None:
        raise RuntimeRefusal("NATIVE_CONSUMER_MCP_SESSION_UNAVAILABLE")
    loop = _running_loop()
    if loop is None:
        raise RuntimeRefusal("NATIVE_CONSUMER_MCP_LOOP_UNAVAILABLE")
    initialize = getattr(server, "initialize_result", None)
    info = getattr(initialize, "serverInfo", None)
    if (getattr(info, "name", None) != publication.mcp.server_name
            or getattr(info, "version", None) != publication.mcp.server_version):
        raise RuntimeRefusal("NATIVE_CONSUMER_MCP_IDENTITY_MISMATCH")
    try:
        observed = tools_schema_digest(getattr(server, "_tools", ()))
    except RuntimeRefusal:
        raise
    if observed != publication.tools_schema_digest:
        raise RuntimeRefusal("NATIVE_CONSUMER_TOOLS_SCHEMA_MISMATCH")
    if not publication.mcp.matches_config(getattr(server, "_config", None)):
        raise RuntimeRefusal("NATIVE_CONSUMER_MCP_CONFIG_MISMATCH")
    return server, session, loop


def _consumer_manifest(manager: Any) -> Any:
    """The exact manifest the upstream manager gated and loaded."""
    plugins = getattr(manager, "_plugins", None)
    if not isinstance(plugins, dict):
        raise RuntimeRefusal("NATIVE_CONSUMER_PLUGIN_NOT_DISCOVERED")
    loaded = plugins.get(CONSUMER_PLUGIN_NAME)
    manifest = getattr(loaded, "manifest", None)
    if manifest is None:
        raise RuntimeRefusal("NATIVE_CONSUMER_PLUGIN_NOT_DISCOVERED")
    if getattr(manifest, "source", None) != CONSUMER_PLUGIN_SOURCE:
        raise RuntimeRefusal("NATIVE_CONSUMER_PLUGIN_SOURCE_MISMATCH")
    return manifest


def install_native_consumer(
    *,
    manager: Any,
    publication: ExecutiveConsumerPublication,
    owner: str,
    profile_id: str,
    session_id: str,
    instance_id: str,
    authority_epoch: int,
    route: str | None,
    server: Any,
    session: Any,
    loop: Any,
    timeout: float = 30.0,
    trust_gate: Callable[[], str | None] | None = None,
    session_guard: Callable[[], bool] | None = None,
) -> ConsumerSlot:
    """Qualify the connection, install the slot and load the one plugin.

    The order is fixed: the connection is qualified first, the immutable
    startup is installed on the actual per-profile manager, and only then is
    the plugin loaded through the upstream loader, with the upstream manifest
    and configuration gates, the load deadline, the registration ledger and
    the unload lease.
    """
    manifest = _consumer_manifest(manager)
    installed = getattr(manifest, "path", None)
    if not installed:
        raise RuntimeRefusal("NATIVE_CONSUMER_PLUGIN_PACKAGE_INVALID")
    if plugin_package_digest(installed) != publication.plugin.digest:
        raise RuntimeRefusal("NATIVE_CONSUMER_PLUGIN_PACKAGE_MISMATCH")
    caller = _NativeMcpCaller(server=server, session=session, loop=loop, timeout=timeout)
    binding = qualify_executive_consumer(
        publication=publication, caller=caller, profile_id=profile_id,
        session_id=session_id, instance_id=instance_id, authority_epoch=authority_epoch,
        session_key=route, task_id=None, timeout=timeout, trust_gate=trust_gate,
        currentness=session_guard)
    slot = ConsumerSlot(owner=owner, profile_id=profile_id, source=CONSUMER_PLUGIN_SOURCE,
                        plugin_id=CONSUMER_PLUGIN_NAME, publication=publication,
                        startup=NativeDelegateStartup(binding=binding))
    install_consumer_slot(manager, slot)
    manager._load_plugin(manifest)
    return slot


def _mandate_schema() -> str:
    """The incumbent mandate projection's schema identity."""
    from control_plane.coo_principal_mandate import SCHEMA
    return SCHEMA


def _unwrap_mandate(raw: Any) -> Mapping[str, Any] | None:
    """Unwrap the authenticated mandate document from one tool result.

    The App wraps the projection in its own result envelope. Both shapes are
    accepted, but only when the payload carries the incumbent mandate schema.
    """
    if raw is None:
        return None
    is_error = getattr(raw, "isError", None)
    if is_error is None and isinstance(raw, Mapping):
        is_error = raw.get("isError")
    if is_error is True:
        return None
    content = getattr(raw, "structuredContent", None)
    if content is None:
        content = getattr(raw, "structured_content", None)
    body: Any = content
    if body is None:
        text = getattr(raw, "content", None)
        if text is None:
            text = raw
        if isinstance(text, (list, tuple)):
            pieces = []
            for item in text:
                value = getattr(item, "text", None)
                if value is None and isinstance(item, Mapping):
                    value = item.get("text")
                if isinstance(value, str):
                    pieces.append(value)
            text = "".join(pieces)
        if isinstance(text, str):
            try:
                body = json.loads(text)
            except (TypeError, ValueError):
                return None
        else:
            body = text
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except (TypeError, ValueError):
            return None
    if not isinstance(body, Mapping):
        return None
    schema = _mandate_schema()
    if body.get("schema") == schema:
        return body
    data = body.get("data")
    if isinstance(data, Mapping) and data.get("schema") == schema:
        return data
    return None


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
