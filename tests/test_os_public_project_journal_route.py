"""Additive Journal route only, preserving exact predecessor upgrade."""
from ops.executive_os.os_public_edge import GET_ROUTES, PRE_AUTONOMY_GET_ROUTES, PRE_PROJECT_JOURNAL_GET_ROUTES, POST_ROUTES, PRE_PROJECT_ADMISSION_POST_ROUTES, TRANSITION_ROUTE_PROFILES, _TEMPLATE

def test_fixed_journal_route_and_predecessor_profile():
    route='/workspace/project-journal/current'
    assert GET_ROUTES.count(route)==1
    assert set(PRE_AUTONOMY_GET_ROUTES)-set(PRE_PROJECT_JOURNAL_GET_ROUTES)=={route}
    assert (PRE_PROJECT_JOURNAL_GET_ROUTES,PRE_PROJECT_ADMISSION_POST_ROUTES) in TRANSITION_ROUTE_PROFILES
    assert _TEMPLATE.read_text().count(route)==1
