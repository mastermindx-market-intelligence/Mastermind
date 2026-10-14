import pytest

from integrations.mastermind_browser_plugin.tunnel_binding import (
    BrowserTunnelBindingError,
    PROFILE_NAME,
    build_browser_tunnel_binding,
)

BROWSER = "tunnel_browser_0123456789abcdef"
STUDIO = "tunnel_studio_abcdef0123456789"
UPSTREAM = "https://browser-gateway.tailabc.ts.net/browser-fabric"


def test_browser_tunnel_is_distinct_but_reuses_tunnel_runtime():
    row = build_browser_tunnel_binding(
        browser_tunnel_ref=BROWSER,
        studio_tunnel_ref=STUDIO,
        internal_upstream_url=UPSTREAM,
    )
    assert PROFILE_NAME == "mastermind-browser"
    assert row.browser_tunnel_ref == BROWSER
    assert row.studio_tunnel_ref == STUDIO
    assert row.internal_upstream_url == UPSTREAM
    assert row.requires_separate_tunnel is True
    assert row.reuses_tunnel_client_runtime is True
    assert row.is_registration is False
    assert row.is_auth_linking is False


def test_same_tunnel_ref_is_refused_to_preserve_catalog_and_outage_isolation():
    with pytest.raises(BrowserTunnelBindingError):
        build_browser_tunnel_binding(
            browser_tunnel_ref=STUDIO,
            studio_tunnel_ref=STUDIO,
            internal_upstream_url=UPSTREAM,
        )


@pytest.mark.parametrize(
    "value",
    [
        "",
        "x",
        "tunnel id",
        "tunnel/id",
        "tunnel@example.com",
        "x" * 129,
        42,
        True,
        None,
    ],
)
def test_tunnel_refs_are_opaque_secret_safe_identifiers(value):
    with pytest.raises(BrowserTunnelBindingError):
        build_browser_tunnel_binding(
            browser_tunnel_ref=value,
            studio_tunnel_ref=STUDIO,
            internal_upstream_url=UPSTREAM,
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://browser-gateway.tailabc.ts.net/browser-fabric",
        "https://browser-gateway.example.com/browser-fabric",
        "https://browser-gateway.tailabc.ts.net/studio-fabric",
        "https://browser-gateway.tailabc.ts.net/browser-fabric?x=1",
        "https://browser-gateway.tailabc.ts.net/browser-fabric#x",
        "https://user:pass@browser-gateway.tailabc.ts.net/browser-fabric",
        "https://browser-gateway.tailabc.ts.net:444/browser-fabric",
        "",
        None,
    ],
)
def test_internal_upstream_is_exact_private_browser_route(url):
    with pytest.raises(BrowserTunnelBindingError):
        build_browser_tunnel_binding(
            browser_tunnel_ref=BROWSER,
            studio_tunnel_ref=STUDIO,
            internal_upstream_url=url,
        )


def test_binding_exposes_no_api_key_auth0_or_workspace_credential_fields():
    row = build_browser_tunnel_binding(
        browser_tunnel_ref=BROWSER,
        studio_tunnel_ref=STUDIO,
        internal_upstream_url=UPSTREAM,
    )
    value = row.to_dict()
    assert value["authority"] == {
        "tunnel_binding_is_authority": False,
        "may_create_tunnel": False,
        "may_link_auth0": False,
        "may_select_browser": False,
        "may_mint_browser_grant": False,
    }
    rendered = repr(value)
    for forbidden in ("api_key", "client_secret", "access_token", "refresh_token"):
        assert forbidden not in rendered
