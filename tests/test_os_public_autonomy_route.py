from ops.executive_os.os_public_edge import (
    GET_ROUTES, PRE_AUTONOMY_GET_ROUTES, PRE_PROJECT_SESSION_GET_ROUTES, POST_ROUTES, PRE_PROJECT_ADMISSION_POST_ROUTES, TRANSITION_ROUTE_PROFILES, _TEMPLATE,
)


def test_autonomy_is_one_fixed_get_with_the_exact_journal_predecessor():
    route = "/workspace/autonomy/current"
    assert GET_ROUTES.count(route) == 1
    assert set(PRE_PROJECT_SESSION_GET_ROUTES) - set(PRE_AUTONOMY_GET_ROUTES) == {route}
    assert route not in POST_ROUTES
    assert (PRE_AUTONOMY_GET_ROUTES, PRE_PROJECT_ADMISSION_POST_ROUTES) in TRANSITION_ROUTE_PROFILES
    assert _TEMPLATE.read_text().count(route) == 1
