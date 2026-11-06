"""One fixed compound GET; complete source-enabled predecessor stays valid."""
import copy
import pytest
from ops.executive_os import os_public_edge as edge
from tests import test_os_public_edge_transition as fixture

@pytest.mark.parametrize('fixed_get,fixed_post', [
    (edge.PRE_MISSION_RESULT_GET_ROUTES, edge.PRE_MISSION_RESULT_POST_ROUTES),
    (edge.MISSION_RESULT_GET_ROUTES, edge.PRE_MISSION_RESULT_POST_ROUTES),
    (edge.GET_ROUTES, edge.POST_ROUTES),
])
def test_whole_compound_get_profile_and_predecessor_preserve_caps_and_other_sites(fixed_get,fixed_post):
    # The mission-result addition is READ-only in both retained generations.
    # Later closed source features legitimately extend the current full profile.
    assert edge.MISSION_RESULT_GET_ROUTES==edge.PRE_MISSION_RESULT_GET_ROUTES+('/workspace/mission-result/current',)
    assert edge.PRE_NATIVE_DRAFT_GET_ROUTES==edge.PRE_FOLLOWING_MISSION_RESULT_GET_ROUTES+('/workspace/mission-result/current',)
    assert edge.PRE_NATIVE_DRAFT_POST_ROUTES==edge.PRE_FOLLOWING_MISSION_RESULT_POST_ROUTES
    live=fixture.fullconfig()
    fixture.get_paths_of(live)[:]=sorted(set(fixed_get)|set(edge.asset_routes(fixture.OLD)))
    fixture.post_paths_of(live)[:]=list(fixed_post)
    fixture.expect_source_upgrade(fixture.inner_of(live))
    before=copy.deepcopy(live)
    planned,prepared,final=fixture.transition_values(live)
    assert live==before
    assert planned['get_routes']['fixed']==list(edge.GET_ROUTES)
    assert fixture.post_paths_of(prepared)==fixture.post_paths_of(final)==list(edge.POST_ROUTES)
    assert prepared['apps']['http']['servers']['srv0']['routes'][1:]==before['apps']['http']['servers']['srv0']['routes'][1:]
    assert fixture.inner_of(final)[1]['handle'][0]['max_size']==64000
    assert fixture.inner_of(final)[2]['handle'][0]['max_size']==98304

@pytest.mark.parametrize('damage',['missing_prior','extra','wildcard'])
def test_compound_get_cannot_mask_partial_or_widened_profile(damage):
    live=fixture.fullconfig()
    fixture.get_paths_of(live)[:]=sorted(set(edge.GET_ROUTES)|set(edge.asset_routes(fixture.OLD)))
    fixture.post_paths_of(live)[:]=list(edge.POST_ROUTES)
    fixture.expect_source_upgrade(fixture.inner_of(live))
    if damage=='missing_prior':fixture.get_paths_of(live).remove('/workspace/project-access/current')
    else:fixture.get_paths_of(live).append('/workspace/mission-result/*' if damage=='wildcard' else '/workspace/mission-result/other')
    with pytest.raises(ValueError):fixture.transition_values(live)
