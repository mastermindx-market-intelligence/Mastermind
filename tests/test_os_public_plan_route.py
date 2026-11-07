"""One existing public edge owner must publish the authenticated plan read in both layers."""
from pathlib import Path

from ops.executive_os.os_public_edge import GET_ROUTES, _TEMPLATE

PLAN_ROUTE = "/workspace/plan/current"


def test_plan_route_present_in_actual_caddy_proxy_and_receipt_allowlist():
    assert GET_ROUTES.count(PLAN_ROUTE) == 1
    text = _TEMPLATE.read_text(encoding="utf-8")
    get_block = text.split("@get {", 1)[1].split("handle @get", 1)[0]
    assert get_block.count(PLAN_ROUTE) == 1
    assert "method GET" in get_block
    assert "method POST" not in get_block
    post_block = text.split("@post {", 1)[1].split("handle @post", 1)[0]
    assert PLAN_ROUTE not in post_block


def test_plan_existing_server_is_get_only_with_same_exact_route():
    source = (Path(__file__).resolve().parents[1] /
              "integrations/mastermind_workspace_app/app.py").read_text(encoding="utf-8")
    assert '_PLAN_ROUTE = "/workspace/plan/current"' in source
    assert 'Route(_PLAN_ROUTE, plan_endpoint, methods=["GET"])' in source
