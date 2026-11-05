"""Inert production composition for the authenticated public Product MCP profile.

All services come from existing Business OAuth/audit/runtime owners. This module
creates no listener, service, credential, user mapping, queue, session or retry
plane. The default HTTP observation transport contains only fixed public
Macro/Terminal endpoints and opens no connection until a tool is invoked.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

from integrations.business_mcp_auth.contracts import (
    AuthAuditSink, ResourcePolicy, validate_resource_policy,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator

from .app import create_product_server, product_http_app
from .contracts import utc_now
from .reader import ProductReader
from .schemas import SCOPE
from .transport import PublicTransport


@dataclass(frozen=True)
class ProductRuntimeServices:
    """Borrowed, owner-qualified bindings; never raw config or environment lookup."""

    authenticator: JwtAuthenticator
    policy: ResourcePolicy
    now: Callable[[], int]
    utc_now: Callable[[], datetime]
    audit_sink: AuthAuditSink
    allowed_hosts: tuple[str, ...]
    allowed_origins: tuple[str, ...] = ()


def _validate_transport_addresses(
    hosts: object, origins: object,
) -> None:
    for addresses, required in ((hosts, True), (origins, False)):
        if (type(addresses) is not tuple or (required and not addresses)
                or any(type(address) is not str or not address
                       or len(address) > 253 or "*" in address
                       or any(ord(c) <= 32 or ord(c) == 127 for c in address)
                       for address in addresses)):
            raise ValueError("TRANSPORT_POLICY_INVALID")
    # The Browser and OAuth owners choose actual authorities. Here we merely
    # refuse wildcards/URLs-with-path as trusted Origin values. Do not infer a
    # loopback or production origin from the environment.
    for address in origins:
        try:
            parsed = urlsplit(address)
            if (parsed.scheme not in ("https", "http")
                    or not parsed.netloc or not parsed.hostname
                    or (parsed.scheme == "http"
                        and parsed.hostname not in ("127.0.0.1", "::1", "localhost"))
                    or parsed.username is not None or parsed.password is not None
                    or parsed.path or parsed.query or parsed.fragment
                    or address != f"{parsed.scheme}://{parsed.netloc}"
                    or (parsed.port is not None and not 1 <= parsed.port <= 65535)):
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError("TRANSPORT_POLICY_INVALID") from None
    for address in hosts:
        # The underlying SDK still applies its admitted Host-origin checks.
        # Reject any URL, whitespace, userinfo or path at the source boundary.
        if any(x in address for x in ("@", "/", "\\", "?", "#", "%")):
            raise ValueError("TRANSPORT_POLICY_INVALID")
        try:
            parsed = urlsplit("//" + address)
            if (not parsed.netloc or not parsed.hostname or parsed.path
                    or parsed.query or parsed.fragment
                    or parsed.username is not None or parsed.password is not None
                    or (parsed.port is not None and not 1 <= parsed.port <= 65535)):
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError("TRANSPORT_POLICY_INVALID") from None


def create_deployment(services: ProductRuntimeServices):
    """Build a bounded ASGI app under the *existing* host's lifecycle.

    A product MCP OAuth principal is intentionally NOT treated as an existing
    product-site session. The only tools in this version read explicitly public
    source data. New private observations require application-owner binding.
    """
    if not isinstance(services, ProductRuntimeServices):
        raise ValueError("RUNTIME_SERVICES_REQUIRED")
    if (not isinstance(services.authenticator, JwtAuthenticator)
            or not callable(getattr(services.audit_sink, "emit", None))
            or not callable(services.now) or not callable(services.utc_now)):
        raise ValueError("RUNTIME_SERVICES_INVALID")
    try:
        issued_at = services.now()
        observed_at = services.utc_now()
        if type(issued_at) is not int or issued_at < 0:
            raise ValueError
        utc_now(observed_at)
    except Exception:
        raise ValueError("RUNTIME_SERVICES_INVALID") from None
    selected = validate_resource_policy(services.policy)
    if selected != validate_resource_policy(services.authenticator.policy):
        raise ValueError("AUTH_POLICY_BINDING_MISMATCH")
    if selected.required_scopes != (SCOPE,):
        raise ValueError("PRODUCT_SCOPE_REQUIRED")
    _validate_transport_addresses(services.allowed_hosts, services.allowed_origins)
    reader = ProductReader(transport=PublicTransport(), now=services.utc_now)
    server = create_product_server(
        authenticator=services.authenticator,
        policy=selected,
        now=services.now,
        audit_sink=services.audit_sink,
        reader=reader,
        allowed_hosts=services.allowed_hosts,
        allowed_origins=services.allowed_origins,
    )
    return product_http_app(server)


__all__ = ["ProductRuntimeServices", "create_deployment"]
