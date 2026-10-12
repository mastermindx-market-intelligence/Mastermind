"""Product MCP owner-grant composition gates, without owner implementation.

No product credentials, listeners, real users or external product traffic.
"""
from __future__ import annotations

from dataclasses import replace
import pytest

from integrations.product_access_mcp.contracts import ProductCaller, ProductRefused, READ_SCOPE
from integrations.product_access_mcp.deployment import (
    ProductReadBinding, ProductDeploymentServices,
    make_product_final_authorization, create_product_deployment,
    CATALOG_SELECTION,
)

CALLER = ProductCaller(
    subject_digest="a" * 64, client_ref="b" * 64,
    resource="https://product.example.test/mcp",
    scopes=(READ_SCOPE,), expires_at=2000,
)
RISK = {"product": "terminal", "view": "market_risk"}
MACRO = {"product": "macro", "view": "status"}


def binding(caller=CALLER, *, product="terminal", view="market_risk",
            source_id="terminal.public_risk_projection", expires_at=1950,
            owner_ref="product-owner", grant_generation="v1"):
    return ProductReadBinding(
        caller=caller, product=product, view=view,
        source_id=source_id, expires_at=expires_at,
        owner_ref=owner_ref, grant_generation=grant_generation,
    )


def test_grant_bound_to_same_caller_source_and_generation():
    now = [1800]
    calls = []
    def owner(caller, product, view):
        calls.append((caller, product, view))
        return binding(caller)
    check = make_product_final_authorization(
        resolve_binding=owner, now=lambda: now[0],
    )(CALLER, RISK)
    assert check() is None
    assert calls == [(CALLER, "terminal", "market_risk")] * 2


def test_product_manifest_still_requires_owner_grant():
    calls = []
    def owner(caller, product, view):
        calls.append((product, view))
        return binding(caller, product="catalog", view="manifest", source_id="catalog.static")
    fence = make_product_final_authorization(
        resolve_binding=owner, now=lambda: 1800,
    )(CALLER, {})
    fence()
    assert calls == [("catalog", "manifest"), ("catalog", "manifest")]
    assert CATALOG_SELECTION == ("catalog", "manifest", "catalog.static")


@pytest.mark.parametrize("mutator", [
    lambda x: replace(x, grant_generation="v2"),
    lambda x: replace(x, owner_ref="another-owner"),
    lambda x: replace(x, source_id="macro.public_status"),
    lambda x: replace(x, expires_at=1900),
    lambda x: replace(x, caller=replace(CALLER, client_ref="c" * 64)),
])
def test_owner_grant_replacement_after_observation_is_refused(mutator):
    change = [False]
    def owner(caller, product, view):
        old = binding(caller)
        return mutator(old) if change[0] else old
    fence = make_product_final_authorization(
        resolve_binding=owner, now=lambda: 1800,
    )(CALLER, RISK)
    change[0] = True
    with pytest.raises(ProductRefused) as exc:
        fence()
    assert exc.value.code == "PRODUCT_GRANT_CHANGED"


def test_owner_revocation_after_observation_is_refused():
    grant = [binding()]
    def owner(caller, product, view):
        if not grant:
            raise PermissionError("private actor revoked")
        return grant[0]
    fence = make_product_final_authorization(
        resolve_binding=owner, now=lambda: 1800,
    )(CALLER, RISK)
    grant.clear()
    with pytest.raises(ProductRefused) as exc:
        fence()
    assert exc.value.code == "PRODUCT_GRANT_CHANGED"
    assert "private" not in str(exc.value)


@pytest.mark.parametrize("expires", [1800, 1750])
def test_grant_deadline_is_enforced(expires):
    with pytest.raises(ProductRefused):
        make_product_final_authorization(
            resolve_binding=lambda caller, p, v: binding(caller, expires_at=expires),
            now=lambda: 1800,
        )(CALLER, RISK)


def test_jwt_expiry_revokes_outstanding_grant():
    now = [1800]
    fence = make_product_final_authorization(
        resolve_binding=lambda caller, p, v: binding(caller, expires_at=3000),
        now=lambda: now[0],
    )(CALLER, RISK)
    now[0] = CALLER.expires_at
    with pytest.raises(ProductRefused):
        fence()


@pytest.mark.parametrize("bad", [
    None, object(), "yes", {}, lambda: None,
])
def test_wrong_owner_return_refused(bad):
    with pytest.raises(ProductRefused):
        make_product_final_authorization(
            resolve_binding=lambda c, p, v: bad,
            now=lambda: 1800,
        )(CALLER, RISK)


@pytest.mark.parametrize("bad", [
    {"product": "terminal", "view": "status"},
    {"product": "macro", "view": "market_risk"},
    {"product": "terminal", "view": "market_risk", "token": "x"},
    {"product": True, "view": "market_risk"},
])
def test_invalid_selected_product_cannot_reach_grant_resolver(bad):
    calls = []
    def resolver(c, p, v):
        calls.append(1)
        return binding(c)
    with pytest.raises(ProductRefused):
        make_product_final_authorization(
            resolve_binding=resolver, now=lambda: 1800,
        )(CALLER, bad)
    assert calls == []


def test_owner_must_grant_requested_source_not_sibling():
    with pytest.raises(ProductRefused):
        make_product_final_authorization(
            resolve_binding=lambda caller, p, v: binding(caller),
            now=lambda: 1800,
        )(CALLER, MACRO)


def test_late_grant_clock_regression_fails_closed():
    clock = [1800]
    def owner(c,p,v):
        return binding(c, expires_at=1900)
    fence = make_product_final_authorization(
        resolve_binding=owner, now=lambda: clock[0],
    )(CALLER, RISK)
    clock[0] = 1901
    with pytest.raises(ProductRefused):
        fence()


def test_missing_resolver_and_clock_do_not_create_default_grant():
    with pytest.raises(ValueError):
        make_product_final_authorization(resolve_binding=None, now=lambda: 1800)
    with pytest.raises(ValueError):
        make_product_final_authorization(
            resolve_binding=lambda c, p, v: binding(c), now=None)
    with pytest.raises(ValueError):
        create_product_deployment(None)


def test_owner_generation_must_be_opaque_bounded_value():
    for bad in ("", "line\nbreak", " " * 4, "0"*129, "Bearer secret"):
        with pytest.raises(ProductRefused):
            make_product_final_authorization(
                resolve_binding=lambda c, p, v: binding(
                    c, grant_generation=bad),
                now=lambda: 1800,
            )(CALLER, RISK)
