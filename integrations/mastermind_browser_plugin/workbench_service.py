"""Compose the high-level Browser service over one existing Workbench deployment.

This module is deliberately transport-free. It derives one domain-separated
Browser reference-signing key from the already-owned Workbench action key and
projects the existing stable Workbench lease into the fixed broker caller used
for low-level resource/effect ownership. External Browser callers remain
separate and are bound by the caller_binding injected by the web/native ingress.

No listener, browser, tunnel, registry, scheduler, retry queue, credential, OAuth
resource, or runtime is created here.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from typing import Any, Callable

from integrations.workbench_action_mcp.contracts import ActionCaller

from .catalog import SCHEMA_DIGEST
from .composition import BrowserOwnerComposition
from .owner_adapter import BrowserCallerBinding
from .server import create_http_app
from .workbench_composition import compose_browser_owner_from_workbench

_BROWSER_SIGNING_PURPOSE = b"mastermind.browser-fabric.outer-ref-key.v1\0"


def derive_browser_signing_key(action_token_key: bytes) -> bytes:
    """Derive a Browser-only HMAC key without provisioning another secret."""
    if type(action_token_key) is not bytes or len(action_token_key) < 32:
        raise TypeError("existing Workbench action key is required")
    return hmac.new(
        action_token_key,
        _BROWSER_SIGNING_PURPOSE,
        hashlib.sha256,
    ).digest()


def browser_broker_caller_from_lease(lease: Any) -> ActionCaller:
    """Project the existing stable Workbench lease into its exact broker caller.

    Structural validation keeps this transport-free module independent of the
    runtime/MCP SDK import edge. The service passes its already-validated stable
    lease object; this function neither validates project authority nor mints it.
    """
    required = (
        "expected_subject_digest",
        "expected_client_ref",
        "resource",
        "required_scopes",
        "lease_expires_at_ms",
    )
    if any(not hasattr(lease, field) for field in required):
        raise TypeError("stable Workbench lease is required")
    if (
        type(lease.expected_subject_digest) is not str
        or len(lease.expected_subject_digest) != 64
        or type(lease.expected_client_ref) is not str
        or not lease.expected_client_ref
        or type(lease.resource) is not str
        or not lease.resource
        or type(lease.required_scopes) is not tuple
        or not lease.required_scopes
        or any(type(scope) is not str or not scope for scope in lease.required_scopes)
        or type(lease.lease_expires_at_ms) is not int
        or isinstance(lease.lease_expires_at_ms, bool)
        or lease.lease_expires_at_ms <= 0
    ):
        raise TypeError("stable Workbench lease identity is invalid")
    expires_at = lease.lease_expires_at_ms // 1000
    if expires_at <= 0:
        raise TypeError("stable Workbench lease expiry is invalid")
    return ActionCaller(
        subject_digest=lease.expected_subject_digest,
        client_ref=lease.expected_client_ref,
        resource=lease.resource,
        scopes=lease.required_scopes,
        expires_at=expires_at,
    )


def browser_caller_binding_from_action_caller(
    caller: ActionCaller,
) -> BrowserCallerBinding:
    """Project one already-authenticated outer caller into Browser ref identity."""
    if type(caller) is not ActionCaller:
        raise TypeError("authenticated ActionCaller is required")
    return BrowserCallerBinding(
        subject_digest=caller.subject_digest,
        client_ref=caller.client_ref,
        resource=caller.resource,
    )


@dataclass(frozen=True, slots=True)
class WorkbenchBrowserFabricHttpApp:
    """One unstarted HTTP app plus the owner composition it serves."""

    fabric: "WorkbenchBrowserFabricComposition"
    app: Any

    @property
    def owner(self):
        return self.fabric.owner

    @property
    def composition(self):
        return self.fabric.composition


@dataclass(frozen=True, slots=True)
class WorkbenchBrowserFabricComposition:
    """Transport-free seven-tool Browser composition over one Workbench owner."""

    composition: BrowserOwnerComposition
    broker_caller: ActionCaller

    def __post_init__(self) -> None:
        if type(self.composition) is not BrowserOwnerComposition:
            raise TypeError("Browser owner composition is required")
        if type(self.broker_caller) is not ActionCaller:
            raise TypeError("exact Workbench broker caller is required")

    @property
    def owner(self):
        return self.composition.owner

    @property
    def codec(self):
        return self.composition.codec


def compose_workbench_browser_fabric(
    *,
    deployment: Any,
    action_token_key: bytes,
    clock_ms: Callable[[], int],
    caller_binding: Callable[[Any], BrowserCallerBinding],
    broker_caller: ActionCaller,
    expected_catalog_schema_digest: str = SCHEMA_DIGEST,
    expected_backend_schema_digest: str,
) -> WorkbenchBrowserFabricComposition:
    """Join the seven-tool Browser owner to one already-created Workbench deployment."""
    if not callable(clock_ms) or not callable(caller_binding):
        raise TypeError("Browser fabric callbacks are required")
    if type(broker_caller) is not ActionCaller:
        raise TypeError("exact Workbench broker caller is required")
    signing_key = derive_browser_signing_key(action_token_key)
    composition = compose_browser_owner_from_workbench(
        deployment=deployment,
        signing_key=signing_key,
        clock_ms=clock_ms,
        caller_binding=caller_binding,
        broker_caller=broker_caller,
        expected_catalog_schema_digest=expected_catalog_schema_digest,
        expected_backend_schema_digest=expected_backend_schema_digest,
    )
    return WorkbenchBrowserFabricComposition(
        composition=composition,
        broker_caller=broker_caller,
    )


def create_workbench_browser_fabric_http_app(
    *,
    deployment: Any,
    action_token_key: bytes,
    clock_ms: Callable[[], int],
    caller_binding: Callable[[Any], BrowserCallerBinding],
    broker_caller: ActionCaller,
    authenticate: Callable,
    auth_challenge: str,
    allowed_hosts: list[str] | tuple[str, ...],
    allowed_origins: tuple[str, ...] = (),
    expected_catalog_schema_digest: str = SCHEMA_DIGEST,
    expected_backend_schema_digest: str,
) -> WorkbenchBrowserFabricHttpApp:
    """Return an unstarted Browser MCP HTTP app over the same Workbench owner."""
    fabric = compose_workbench_browser_fabric(
        deployment=deployment,
        action_token_key=action_token_key,
        clock_ms=clock_ms,
        caller_binding=caller_binding,
        broker_caller=broker_caller,
        expected_catalog_schema_digest=expected_catalog_schema_digest,
        expected_backend_schema_digest=expected_backend_schema_digest,
    )
    app = create_http_app(
        owner=fabric.owner,
        authenticate=authenticate,
        auth_challenge=auth_challenge,
        allowed_hosts=list(allowed_hosts),
        allowed_origins=allowed_origins,
    )
    return WorkbenchBrowserFabricHttpApp(fabric=fabric, app=app)


__all__ = [
    "WorkbenchBrowserFabricComposition",
    "WorkbenchBrowserFabricHttpApp",
    "browser_broker_caller_from_lease",
    "browser_caller_binding_from_action_caller",
    "compose_workbench_browser_fabric",
    "create_workbench_browser_fabric_http_app",
    "derive_browser_signing_key",
]
