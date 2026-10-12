"""Owner-injected Product MCP composition and same-grant result fence.

No product-user database, verifier, token exchange, listener, process, retry,
scheduler or browser is created.  The installing owner must provide a CURRENT
permission resolver, a bounded existing-owner read port and an admitted OAuth
resource policy. An OAuth claim by itself is never a product authorization.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
import re
from typing import Any

from integrations.business_mcp_auth.contracts import (
    AuthAuditSink, ResourcePolicy, validate_resource_policy,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from .app import (
    FinalAuthorization, ReadPort, create_authenticated_product_server,
)
from .contracts import ProductCaller, ProductRefused, SOURCES


CATALOG_SELECTION = ("catalog", "manifest", "catalog.static")


@dataclass(frozen=True)
class ProductReadBinding:
    """Projection of the incumbent product owner's exact, revocable grant.

    This is an immutable observation, NOT the grant's owner or a locally
    authoritative lease. Changes to owner generation, client, resource,
    product or remaining expiry must refuse release after the I/O await.
    """

    caller: ProductCaller
    product: str
    view: str
    source_id: str
    owner_ref: str
    grant_generation: str
    expires_at: int


BindingResolver = Callable[
    [ProductCaller, str, str], ProductReadBinding,
]


@dataclass(frozen=True)
class ProductDeploymentServices:
    """Borrowed host dependencies, never acquired implicitly by this adapter."""

    authenticator: JwtAuthenticator
    policy: ResourcePolicy
    now: Callable[[], int]
    audit_sink: AuthAuditSink
    read_port: ReadPort
    resolve_binding: BindingResolver
    allowed_hosts: tuple[str, ...]
    allowed_origins: tuple[str, ...] = ()


def _selected_source(request: Mapping[str, str]) -> tuple[str, str, str]:
    if not isinstance(request, Mapping):
        raise ProductRefused("PRODUCT_GRANT_CHANGED")
    if not request:
        return CATALOG_SELECTION
    if set(request) != {"product", "view"}:
        raise ProductRefused("PRODUCT_GRANT_CHANGED")
    product, view = request["product"], request["view"]
    if type(product) is not str or type(view) is not str or (product, view) not in SOURCES:
        raise ProductRefused("PRODUCT_GRANT_CHANGED")
    return product, view, SOURCES[(product, view)][0]


def _binding(
    resolver: BindingResolver,
    caller: ProductCaller,
    selection: tuple[str, str, str],
    now: Callable[[], int],
) -> ProductReadBinding:
    """Re-observe the real grant with the SAME caller and source selection."""
    try:
        timestamp = now()
        if type(timestamp) is not int or timestamp < 0:
            raise ProductRefused("PRODUCT_GRANT_CHANGED")
        if timestamp >= caller.expires_at:
            raise ProductRefused("PRODUCT_GRANT_CHANGED")
        product, view, source = selection
        result = resolver(caller, product, view)
        if type(result) is not ProductReadBinding:
            raise ProductRefused("PRODUCT_GRANT_CHANGED")
        if (type(result.caller) is not ProductCaller
            or result.caller != caller
            or result.product != product
            or result.view != view
            or result.source_id != source
            or type(result.expires_at) is not int
            or result.expires_at <= timestamp):
            raise ProductRefused("PRODUCT_GRANT_CHANGED")
        if (type(result.owner_ref) is not str
            or not 1 <= len(result.owner_ref) <= 128
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", result.owner_ref) is None
            or type(result.grant_generation) is not str
            or not 1 <= len(result.grant_generation) <= 128
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*",
                            result.grant_generation) is None):
            raise ProductRefused("PRODUCT_GRANT_CHANGED")
        # Product permission never lengthens the already verified JWT.
        return replace(result, expires_at=min(result.expires_at, caller.expires_at))
    except ProductRefused:
        raise
    except Exception:
        # No private product entitlement errors in a Web CEO result.
        raise ProductRefused("PRODUCT_GRANT_CHANGED") from None


def make_product_final_authorization(
    *, resolve_binding: BindingResolver, now: Callable[[], int],
) -> FinalAuthorization:
    """Require one current owner binding before and after awaited observation.

    The late recheck runs synchronously as the final authorization operation
    after JWT revalidation. A renewed/replaced/withdrawn owner grant is refused
    for the existing response, even when still permitted in a new request.
    """
    if not callable(resolve_binding) or not callable(now):
        raise ValueError("incumbent product grant resolver and clock required")

    def capture(caller: ProductCaller, request: Mapping[str, str]):
        if type(caller) is not ProductCaller:
            raise ProductRefused("PRODUCT_GRANT_CHANGED")
        selection = _selected_source(request)
        caller_snapshot = replace(caller)
        original = _binding(resolve_binding, caller_snapshot, selection, now)

        def revalidate() -> None:
            current = _binding(resolve_binding, caller_snapshot, selection, now)
            if current != original:
                raise ProductRefused("PRODUCT_GRANT_CHANGED")

        return revalidate

    return capture


def create_product_deployment(services: ProductDeploymentServices):
    """Construct inert authenticated MCP/ASGI composition, no listener start.

    This factory does not prove the injected resolver is product-authoritative,
    nor that a user/product/account/link/tunnel/deployment is installed. These
    are separate owner-side admission and real-path verification requirements.
    """
    if type(services) is not ProductDeploymentServices:
        raise ValueError("owner ProductDeploymentServices required")
    if (not isinstance(services.authenticator, JwtAuthenticator)
        or not callable(getattr(services.audit_sink, "emit", None))
        or not all(callable(fn) for fn in
                   (services.now, services.read_port, services.resolve_binding))):
        raise ValueError("borrowed service dependencies invalid")
    if (validate_resource_policy(services.policy) !=
        validate_resource_policy(services.authenticator.policy)):
        raise ValueError("authenticator policy identity mismatch")
    for names, required in ((services.allowed_hosts, True),
                            (services.allowed_origins, False)):
        if (type(names) is not tuple or
            (required and not names) or
            len(set(names)) != len(names) or
            any(type(value) is not str or not 1 <= len(value) <= 255
                or "*" in value or
                any(ord(ch) < 33 or ord(ch) == 127 for ch in value)
                for value in names)):
            raise ValueError("closed transport policy required")

    return create_authenticated_product_server(
        authenticator=services.authenticator,
        policy=services.policy,
        now=services.now,
        audit_sink=services.audit_sink,
        read_port=services.read_port,
        final_authorization=make_product_final_authorization(
            resolve_binding=services.resolve_binding, now=services.now),
        allowed_hosts=services.allowed_hosts,
        allowed_origins=services.allowed_origins,
    )
