"""One secret-free fixed GET; complete incumbent profiles and bounds retained."""
import copy
import pytest
from ops.executive_os import os_public_edge as edge
from ops.executive_os.os_public_edge_transition import prepare_config, final_config
from tests.test_os_public_edge import manifest
from tests.test_project_controls_edge_join import predecessor, method_routes, add_expected_native_branch
from tests.test_os_public_edge_transition import NATIVE_PATHS

ROUTE = '/workspace/byok/roles/current'

def test_byok_read_has_one_exact_get_and_no_post_or_source_branch():
    assert edge.PRE_MODEL_CONFIGURATION_GET_ROUTES == edge.PRE_BYOK_ROLES_GET_ROUTES + (ROUTE,)
    assert edge.GET_ROUTES == edge.PRE_MODEL_CONFIGURATION_GET_ROUTES + ("/workspace/resources/models/current",)
    assert edge.PRE_PROJECT_EXECUTION_POST_ROUTES == edge.PRE_BYOK_ROLES_POST_ROUTES
    assert edge.PRE_DIRECT_NATIVE_POST_ROUTES == edge.PRE_PROJECT_EXECUTION_POST_ROUTES + edge.PROJECT_EXECUTION_POST_ROUTES
    assert edge.PRE_COMPANY_PRIORITIES_POST_ROUTES == edge.PRE_DIRECT_NATIVE_POST_ROUTES + (
        "/os/executive/direct-native/result", "/os/executive/direct-native/consume",
        "/os/executive/direct-native/correction",
    )
    assert edge.POST_ROUTES == edge.PRE_COMPANY_PRIORITIES_POST_ROUTES + ("/os/executive/company-priorities",)
    assert (edge.PRE_MODEL_CONFIGURATION_GET_ROUTES, edge.PRE_COMPANY_PRIORITIES_POST_ROUTES) in edge.TRANSITION_ROUTE_PROFILES
    assert ROUTE not in edge.POST_ROUTES + edge.SOURCE_POST_ROUTES
    assert (edge.PRE_BYOK_ROLES_GET_ROUTES, edge.PRE_BYOK_ROLES_POST_ROUTES) in edge.TRANSITION_ROUTE_PROFILES
    assert len(edge.TRANSITION_ROUTE_PROFILES) == 34
    text = edge.render(manifest(),49152)
    get = text.split('    @get {',1)[1].split('    }',1)[0]
    assert 'method GET' in get and get.count(ROUTE) == 1
    assert text.count(ROUTE) == 1
    assert text.count('max_size 64KB') == 2 and text.count('max_size 98304') == 1
    assert text.count('reverse_proxy 127.0.0.1:49152') == 6
    assert text.count("max_size 524288") == 1
    assert all(text.split().count(path) == 1 for path in NATIVE_PATHS)
    assert text.count("    @nativepost {") == 1
    assert text.count("    handle @nativepost {") == 1
    native = text.split("    @nativepost {", 1)[1].split("    }", 1)[0]
    assert native.split() == ["method", "POST", "path", *NATIVE_PATHS]

@pytest.mark.parametrize('maker',[prepare_config, final_config])
def test_byok_get_transition_retains_complete_predecessor_and_other_sites(maker):
    live = predecessor(); routes = method_routes(live)
    routes[0]['match'][0]['path'] = sorted(set(edge.PRE_BYOK_ROLES_GET_ROUTES)|set(edge.asset_routes(manifest())))
    routes[1]['match'][0]['path'] = list(edge.PRE_BYOK_ROLES_POST_ROUTES)
    before = copy.deepcopy(live)
    expected = copy.deepcopy(live)
    method_routes(expected)[0]['match'][0]['path'] = sorted(set(edge.GET_ROUTES)|set(edge.asset_routes(manifest())))
    method_routes(expected)[1]['match'][0]['path'] = list(edge.POST_ROUTES)
    for route in method_routes(expected)[3:5]:
        route["match"][0]["path"] = (
            list(edge.COMPLETE_MCP_METADATA_ROUTES)
            if route["match"][0]["method"] == ["GET"]
            else list(edge.COMPLETE_MCP_ROUTES))
    add_expected_native_branch(expected)
    result = maker(fullconfig=live,current_manifest=manifest(),candidate_manifest=manifest(),relay_port=49152)
    assert result == expected and live == before
    for bad in (ROUTE+'/',ROUTE+'-other','/workspace/byok/*'):
        malformed=copy.deepcopy(live);method_routes(malformed)[0]['match'][0]['path'].append(bad)
        with pytest.raises(ValueError):
            maker(fullconfig=malformed,current_manifest=manifest(),candidate_manifest=manifest(),relay_port=49152)
