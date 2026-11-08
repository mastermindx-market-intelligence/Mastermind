"""The authenticated model READ composes with the exact native edge predecessor."""
import copy
import hashlib
import json

import pytest

from ops.executive_os import os_public_edge as edge
from ops.executive_os.os_public_edge_transition import final_config, prepare_config
from tests import test_os_public_edge_transition as fixtures

ROUTE = "/workspace/resources/models/current"


def test_one_model_get_preserves_every_predecessor_and_method_boundary():
    # Exact 33-profile prefix at e754aee1132b1304786fb6b0d09989535062e116.
    assert hashlib.sha256(json.dumps(
        edge.TRANSITION_ROUTE_PROFILES[:-1], separators=(",", ":")
    ).encode()).hexdigest() == "a7c14bba481a30a963ea4e1bdbd82870cab1352bc254b36e277ac0ee43c272e6"
    assert len(edge.TRANSITION_ROUTE_PROFILES) == 34
    assert edge.GET_ROUTES == edge.PRE_MODEL_CONFIGURATION_GET_ROUTES + (ROUTE,)
    assert edge.POST_ROUTES == edge.PRE_MODEL_CONFIGURATION_POST_ROUTES
    assert edge.TRANSITION_ROUTE_PROFILES[-1] == (edge.GET_ROUTES, edge.POST_ROUTES)
    assert ROUTE not in (
        edge.POST_ROUTES + edge.SOURCE_POST_ROUTES
        + edge.NATIVE_CONVERSATION_POST_ROUTES + edge.COMPLETE_MCP_ROUTES
        + edge.COMPLETE_MCP_METADATA_ROUTES
    )
    assert edge.GET_ROUTES.count(ROUTE) == 1
    assert edge.render(fixtures.OLD, 49152).count(ROUTE) == 1


@pytest.mark.parametrize("fault", ["missing", "duplicate", "wildcard", "reordered"])
def test_model_get_template_must_match_exact_ordered_profile(tmp_path, monkeypatch, fault):
    source = edge._TEMPLATE.read_text()
    if fault == "missing":
        candidate = source.replace(" " + ROUTE, "", 1)
    elif fault == "duplicate":
        candidate = source.replace(ROUTE, ROUTE + " " + ROUTE, 1)
    elif fault == "wildcard":
        candidate = source.replace(ROUTE, ROUTE + "/*", 1)
    else:
        candidate = source.replace("/workspace/byok/roles/current " + ROUTE,
                                   ROUTE + " /workspace/byok/roles/current", 1)
    assert candidate != source
    path = tmp_path / "edge.template"
    path.write_text(candidate)
    monkeypatch.setattr(edge, "_TEMPLATE", path)
    with pytest.raises(ValueError):
        edge.render(fixtures.OLD, 49152)


@pytest.mark.parametrize("with_mcp", [False, True])
@pytest.mark.parametrize("predecessor", [False, True])
@pytest.mark.parametrize("maker", [prepare_config, final_config])
def test_pre_model_and_current_native_profiles_preserve_whole_configuration(with_mcp, predecessor, maker):
    live = fixtures.native_current_config(with_mcp)
    if predecessor:
        fixtures.get_paths_of(live)[:] = sorted(
            set(edge.PRE_MODEL_CONFIGURATION_GET_ROUTES) | set(edge.asset_routes(fixtures.OLD)))
    before = copy.deepcopy(live)
    result = maker(fullconfig=live, current_manifest=fixtures.OLD,
                   candidate_manifest=fixtures.NEW, relay_port=49152)
    expected = copy.deepcopy(before)
    assets = set(edge.asset_routes(fixtures.NEW))
    if maker is prepare_config:
        assets.update(edge.asset_routes(fixtures.OLD))
    fixtures.get_paths_of(expected)[:] = sorted(set(edge.GET_ROUTES) | assets)
    assert result == expected
    assert live == before
    branches = fixtures.inner_of(result)
    assert branches[-2] == fixtures.inner_of(before)[-2]
    assert branches[-2]["handle"][0] == {"handler": "request_body", "max_size": 524288}
    assert sum(branch.get("match", [{}])[0].get("path") == list(fixtures.NATIVE_PATHS)
               for branch in branches) == 1


@pytest.mark.parametrize("with_mcp", [False, True])
def test_model_get_cannot_mix_with_pre_company_priorities_posts(with_mcp):
    live = fixtures.native_current_config(with_mcp)
    fixtures.post_paths_of(live)[:] = list(edge.PRE_COMPANY_PRIORITIES_POST_ROUTES)
    before = copy.deepcopy(live)
    fixtures.assert_native_refused(live)
    assert live == before
