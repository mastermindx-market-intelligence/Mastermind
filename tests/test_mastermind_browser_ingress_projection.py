import pytest

from integrations.mastermind_browser_plugin.ingress import (
    BrowserIngressError,
    build_browser_ingress_plan,
)


PUBLIC='https://browser-mcp.mastermind.example/mcp'
INTERNAL='https://m2-browser.tail123.ts.net/browser-fabric'


def test_browser_ingress_is_separate_public_plugin_but_same_owner_path():
    plan=build_browser_ingress_plan(
        public_resource_url=PUBLIC,
        internal_upstream_url=INTERNAL,
    )
    assert plan.public_resource_url==PUBLIC
    assert plan.internal_upstream_url==INTERNAL
    assert plan.public_path=='/mcp'
    assert plan.internal_path=='/browser-fabric'
    assert plan.web_lane=='oauth_https'
    assert plan.native_lane=='supervisor_private_stdio'
    assert plan.same_browser_owner_required is True
    assert plan.requires_dedicated_public_binding is True
    assert plan.is_admission is False


@pytest.mark.parametrize('url',[
    'http://browser.example/mcp',
    'https://browser.example/browser',
    'https://user:pass@browser.example/mcp',
    'https://browser.example:8443/mcp',
    'https://browser.example/mcp?x=1',
    'https://browser.example/mcp#frag',
    'https:///mcp',
])
def test_public_plugin_resource_is_exact_https_mcp_url(url):
    with pytest.raises(BrowserIngressError):
        build_browser_ingress_plan(public_resource_url=url,internal_upstream_url=INTERNAL)


@pytest.mark.parametrize('url',[
    'http://m2.tail123.ts.net/browser-fabric',
    'https://m2.tail123.ts.net/mcp',
    'https://m2.example.com/browser-fabric',
    'https://user@m2.tail123.ts.net/browser-fabric',
    'https://m2.tail123.ts.net:8443/browser-fabric',
    'https://m2.tail123.ts.net/browser-fabric?x=1',
    'https://m2.tail123.ts.net/browser-fabric#frag',
])
def test_internal_browser_route_is_exact_tailnet_service(url):
    with pytest.raises(BrowserIngressError):
        build_browser_ingress_plan(public_resource_url=PUBLIC,internal_upstream_url=url)


def test_projection_has_no_host_account_or_credential_selector():
    plan=build_browser_ingress_plan(public_resource_url=PUBLIC,internal_upstream_url=INTERNAL)
    assert set(plan.to_dict())=={
        'schema','public_resource_url','internal_upstream_url','public_path',
        'internal_path','web_lane','native_lane','same_browser_owner_required',
        'requires_dedicated_public_binding','is_admission',
    }
    rendered=str(plan.to_dict()).lower()
    for forbidden in ('credential','account_label','host_ref','worker_id','attempt_id','token'):
        assert forbidden not in rendered


def test_current_v1_never_claims_one_tunnel_multiplexing_is_proven():
    plan=build_browser_ingress_plan(public_resource_url=PUBLIC,internal_upstream_url=INTERNAL)
    assert plan.requires_dedicated_public_binding is True
