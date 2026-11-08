"""Exact following-cut route profiles; no live edge write or gateway probe."""
import copy
import pytest
from common import fresh_conversation_contract as fresh
from integrations.mastermind_executive_app.project_conversation_transport import ROUTES
from integrations.executive_mcp.server import _OS_FRESH_CONVERSATION_ROUTES, _OS_SESSION_EXECUTIVE_ROUTES
from ops.executive_os import os_public_edge as edge
from tests.test_os_public_edge import manifest
from tests import test_os_public_edge_transition as fixtures


def test_fixed_consumer_routes_reach_renderer_without_widening_incumbent_caps():
    assert set(edge.FRESH_CONVERSATION_POST_ROUTES) == set(fresh.ROUTES) == set(_OS_FRESH_CONVERSATION_ROUTES)
    assert set(edge.PROJECT_CONVERSATION_READ_POST_ROUTES) | {
        '/os/executive/session/project-executions', '/os/executive/session/project-execution-read',
    } == set(ROUTES) | {'/os/executive/session/history-context'}
    assert '/os/executive/session/history-context' in _OS_SESSION_EXECUTIVE_ROUTES
    assert edge.PRE_DIRECT_NATIVE_POST_ROUTES == edge.PRE_CONVERSATION_READ_POST_ROUTES + edge.PROJECT_CONVERSATION_READ_POST_ROUTES + edge.FRESH_CONVERSATION_POST_ROUTES + ('/os/executive/session/send',) + edge.PROJECT_EXECUTION_POST_ROUTES
    assert edge.PRE_COMPANY_PRIORITIES_POST_ROUTES == edge.PRE_DIRECT_NATIVE_POST_ROUTES + (
        "/os/executive/direct-native/result", "/os/executive/direct-native/consume",
        "/os/executive/direct-native/correction",
    )
    assert edge.POST_ROUTES == edge.PRE_COMPANY_PRIORITIES_POST_ROUTES + ("/os/executive/company-priorities",)
    assert (edge.GET_ROUTES, edge.PRE_COMPANY_PRIORITIES_POST_ROUTES) in edge.TRANSITION_ROUTE_PROFILES
    assert edge.GET_ROUTES == edge.PRE_CONVERSATION_READ_GET_ROUTES + ('/workspace/resources/host-observation/current', '/workspace/mission-result/current', '/workspace/native-draft-identity/current') + edge.BYOK_READ_ROUTES
    text = edge.render(manifest(), 49152)
    assert 'path ' + ' '.join(edge.POST_ROUTES) + '\n' in text
    assert 'path ' + ' '.join(edge.GET_ROUTES) + ' ' in text
    assert text.count('max_size 64KB') == 2 and text.count('max_size 98304') == 1
    assert '/os/executive/session/send' not in edge.PRE_NATIVE_SESSION_SEND_POST_ROUTES
    assert edge.PRE_BYOK_ROLES_POST_ROUTES == edge.PRE_NATIVE_SESSION_SEND_POST_ROUTES + ('/os/executive/session/send',)
    assert all('*' not in route for route in edge.GET_ROUTES + edge.POST_ROUTES)


@pytest.mark.parametrize('fixed,posts', [
    (edge.PRE_PLAN_PROPOSAL_GET_ROUTES, edge.PRE_PLAN_PROPOSAL_POST_ROUTES),
    (edge.PRE_CONVERSATION_READ_GET_ROUTES, edge.PRE_CONVERSATION_READ_POST_ROUTES),
    (edge.MISSION_RESULT_GET_ROUTES, edge.PRE_MISSION_RESULT_POST_ROUTES),
    (edge.PRE_FOLLOWING_MISSION_RESULT_GET_ROUTES, edge.PRE_FOLLOWING_MISSION_RESULT_POST_ROUTES),
    (edge.PRE_NATIVE_DRAFT_GET_ROUTES, edge.PRE_NATIVE_DRAFT_POST_ROUTES),
    (edge.PRE_BYOK_ROLES_GET_ROUTES, edge.PRE_BYOK_ROLES_POST_ROUTES),
    (edge.PRE_PROJECT_EXECUTION_GET_ROUTES, edge.PRE_PROJECT_EXECUTION_POST_ROUTES),
    (edge.PROJECT_EXECUTION_PRE_MERGE_GET_ROUTES, edge.PROJECT_EXECUTION_PRE_MERGE_POST_ROUTES),
    (edge.PRE_NATIVE_SESSION_SEND_GET_ROUTES, edge.PRE_NATIVE_SESSION_SEND_POST_ROUTES),
    (edge.GET_ROUTES, edge.POST_ROUTES),
])
def test_whole_predecessor_and_current_profiles_transition_without_mutating_input(fixed, posts):
    live = fixtures.fullconfig()
    fixtures.get_paths_of(live)[:] = sorted(set(fixed) | set(edge.asset_routes(fixtures.OLD)))
    fixtures.post_paths_of(live)[:] = list(posts)
    # Every one of these profiles already owns source-operation/operation,
    # and therefore retains its dedicated, separately bounded POST branch.
    fixtures.expect_source_upgrade(fixtures.inner_of(live))
    before = copy.deepcopy(live)
    planned, prepared, final = fixtures.transition_values(live)
    assert live == before
    assert planned['post_routes'] == list(edge.POST_ROUTES)
    assert fixtures.post_paths_of(prepared) == fixtures.post_paths_of(final) == list(edge.POST_ROUTES)


@pytest.mark.parametrize('fault', ['hybrid_get', 'hybrid_post', 'extra', 'missing', 'wildcard'])
def test_partial_or_mixed_following_route_profiles_refuse(fault):
    live = fixtures.fullconfig()
    fixtures.get_paths_of(live)[:] = sorted(set(edge.GET_ROUTES) | set(edge.asset_routes(fixtures.OLD)))
    fixtures.post_paths_of(live)[:] = list(edge.POST_ROUTES)
    fixtures.expect_source_upgrade(fixtures.inner_of(live))
    if fault == 'hybrid_get':
        fixtures.get_paths_of(live).remove('/workspace/resources/host-observation/current')
    elif fault == 'hybrid_post':
        fixtures.post_paths_of(live)[:] = list(edge.PRE_CONVERSATION_READ_POST_ROUTES)
    elif fault == 'extra':
        fixtures.post_paths_of(live).append('/os/executive/conversation/delete')
    elif fault == 'missing':
        fixtures.post_paths_of(live).remove('/os/executive/conversation/consume/status')
    else:
        fixtures.post_paths_of(live).append('/os/executive/conversation/*')
    with pytest.raises(ValueError):
        fixtures.transition_values(live)


def test_mission_result_firstcut_and_following_profiles_are_exact():
    assert '/workspace/mission-result/current' in edge.GET_ROUTES
    assert edge.MISSION_RESULT_GET_ROUTES == edge.PRE_MISSION_RESULT_GET_ROUTES + ('/workspace/mission-result/current',)
    assert (edge.MISSION_RESULT_GET_ROUTES, edge.PRE_MISSION_RESULT_POST_ROUTES) in edge.TRANSITION_ROUTE_PROFILES
    assert (edge.PRE_FOLLOWING_MISSION_RESULT_GET_ROUTES, edge.PRE_FOLLOWING_MISSION_RESULT_POST_ROUTES) in edge.TRANSITION_ROUTE_PROFILES
    assert (edge.PRE_NATIVE_DRAFT_GET_ROUTES, edge.PRE_NATIVE_DRAFT_POST_ROUTES) in edge.TRANSITION_ROUTE_PROFILES
    assert edge.PRE_NATIVE_DRAFT_GET_ROUTES == edge.PRE_FOLLOWING_MISSION_RESULT_GET_ROUTES + ('/workspace/mission-result/current',)
    assert edge.PRE_NATIVE_DRAFT_POST_ROUTES == edge.PRE_FOLLOWING_MISSION_RESULT_POST_ROUTES
    assert edge.GET_ROUTES == edge.PRE_FOLLOWING_MISSION_RESULT_GET_ROUTES + ('/workspace/mission-result/current', '/workspace/native-draft-identity/current') + edge.BYOK_READ_ROUTES
    assert edge.PRE_NATIVE_SESSION_SEND_POST_ROUTES == edge.PRE_FOLLOWING_MISSION_RESULT_POST_ROUTES
