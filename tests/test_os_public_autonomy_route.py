from ops.executive_os.os_public_edge import (
    GET_ROUTES, PRE_AUTONOMY_GET_ROUTES, POST_ROUTES, TRANSITION_ROUTE_PROFILES, _TEMPLATE,
)


def test_autonomy_is_one_fixed_get_with_the_exact_journal_predecessor():
    route = "/workspace/autonomy/current"
    assert GET_ROUTES.count(route) == 1
    assert set(GET_ROUTES) - set(PRE_AUTONOMY_GET_ROUTES) == {route, "/workspace/resources/capacity/current", "/workspace/project-direction/current", "/workspace/project-session/current"}
    assert route not in POST_ROUTES
    assert (PRE_AUTONOMY_GET_ROUTES, POST_ROUTES) in TRANSITION_ROUTE_PROFILES
    assert _TEMPLATE.read_text().count(route) == 1
