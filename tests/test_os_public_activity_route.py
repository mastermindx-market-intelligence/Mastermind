"""The existing public OS edge must explicitly publish the authorized activity GET.

Never add an unauthenticated alias, POST permission or another proxy owner.
"""
from pathlib import Path

from ops.executive_os.os_public_edge import GET_ROUTES, POST_ROUTES, _TEMPLATE

ROOT = Path(__file__).resolve().parents[1]
ACTIVITY_ROUTE = "/workspace/operator/activity/current"


def test_exact_activity_get_route_only_in_public_os_edge_and_stage_receipt():
    assert GET_ROUTES.count(ACTIVITY_ROUTE) == 1
    assert ACTIVITY_ROUTE not in POST_ROUTES
    template = _TEMPLATE.read_text(encoding="utf-8")
    assert template.count(ACTIVITY_ROUTE) == 1
    get_block = template.split("@get {", 1)[1].split("handle @get", 1)[0]
    assert get_block.count(ACTIVITY_ROUTE) == 1
    assert "method GET" in get_block
    post_block = template.split("@post {", 1)[1].split("handle @post", 1)[0]
    assert ACTIVITY_ROUTE not in post_block


def test_original_workspace_app_get_route_and_outer_fence_are_consistent():
    path = ROOT / "integrations/mastermind_workspace_app/app.py"
    source = path.read_text(encoding="utf-8")
    assert '_ACTIVITY_ROUTE = "/workspace/operator/activity/current"' in source
    assert 'Route(_ACTIVITY_ROUTE, activity_endpoint, methods=["GET"])' in source
    fence = source.split("class _RawPathFence:", 1)[1].split(
        "    def __init__(self, app: Any) -> None:", 1
    )[0]
    assert fence.count("_ACTIVITY_ROUTE,") == 1
    assert '"GET"' in fence


def test_original_executive_path_fence_lists_activity_get_without_post():
    source = (ROOT / "integrations/executive_mcp/server.py").read_text(
        encoding="utf-8"
    )
    assert source.count('"/workspace/operator/activity/current"') == 3
    assert '"POST" "workspace/operator/activity/current"' not in source
