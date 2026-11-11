"""Two exact observational GET routes, no wildcard, POST or service effect."""
from pathlib import Path
from ops.executive_os.os_public_edge import GET_ROUTES, POST_ROUTES, PRE_PROJECT_ADMISSION_GET_ROUTES, PRE_PROJECT_ADMISSION_POST_ROUTES, PRE_DIRECTION_GET_ROUTES, TRANSITION_ROUTE_PROFILES, _TEMPLATE

ROUTES = {"/workspace/project-direction/current", "/workspace/resources/capacity/current"}


def test_exact_two_route_delta_retains_the_actual_predecessor_profile():
    assert set(PRE_PROJECT_ADMISSION_GET_ROUTES) - set(PRE_DIRECTION_GET_ROUTES) == ROUTES
    assert (PRE_DIRECTION_GET_ROUTES, PRE_PROJECT_ADMISSION_POST_ROUTES) in TRANSITION_ROUTE_PROFILES
    assert all(GET_ROUTES.count(path) == 1 and path not in POST_ROUTES for path in ROUTES)
    assert not any("*" in path for path in GET_ROUTES)


def test_template_exposes_only_fixed_gets_and_gateway_mounts_direction_explicitly():
    text = _TEMPLATE.read_text()
    get = text.split("@get {", 1)[1].split("handle @get", 1)[0]
    post = text.split("@post {", 1)[1].split("handle @post", 1)[0]
    assert "method GET" in get
    for path in ROUTES:
        assert get.count(path) == 1 and path not in post
    source = (Path(__file__).resolve().parents[1] / "integrations/executive_mcp/server.py").read_text()
    assert source.count('"/workspace/project-direction/current"') == 3
