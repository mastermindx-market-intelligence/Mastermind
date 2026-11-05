"""The new canonical record read is one exact GET, never an execution route."""
from pathlib import Path

from ops.executive_os.os_public_edge import GET_ROUTES, PRE_PROJECT_PLAN_GET_ROUTES, POST_ROUTES, PRE_PROJECT_ADMISSION_POST_ROUTES, TRANSITION_ROUTE_PROFILES, _TEMPLATE

ROUTE = "/workspace/project-plan/current"


def test_new_read_is_fixed_get_and_old_publication_remains_an_exact_predecessor():
    assert GET_ROUTES.count(ROUTE) == 1
    assert ROUTE not in POST_ROUTES
    assert (PRE_PROJECT_PLAN_GET_ROUTES, PRE_PROJECT_ADMISSION_POST_ROUTES) in TRANSITION_ROUTE_PROFILES
    assert set(GET_ROUTES) - set(PRE_PROJECT_PLAN_GET_ROUTES) == {
        ROUTE, "/workspace/project-journal/current", "/workspace/autonomy/current",
        "/workspace/resources/capacity/current", "/workspace/project-direction/current", "/workspace/project-session/current", "/workspace/project-admission/current", "/workspace/project-admission/operation", "/workspace/projects/archive/current", "/workspace/project-knowledge/current", "/workspace/project-memory/current", "/workspace/project-source/current", "/workspace/source-operation/context", "/workspace/source-operation/operation", '/workspace/project-instructions/current', '/workspace/instruction-admission/current', '/workspace/instruction-admission/operation', '/workspace/project-access/current', '/workspace/mission-result/current'}
    template = _TEMPLATE.read_text()
    get_block = template.split("@get {", 1)[1].split("handle @get", 1)[0]
    post_block = template.split("@post {", 1)[1].split("handle @post", 1)[0]
    assert get_block.count(ROUTE) == 1 and ROUTE not in post_block
    assert "method GET" in get_block


def test_public_gateway_and_workspace_owner_mount_exact_route_without_generic_path():
    root = Path(__file__).resolve().parents[1]
    gateway = (root / "integrations/executive_mcp/server.py").read_text()
    assert gateway.count('"' + ROUTE + '"') == 3
    owner = (root / "integrations/mastermind_workspace_app/app.py").read_text()
    assert 'Route(_PROJECT_PLAN_ROUTE, project_plan_endpoint, methods=["GET"])' in owner
