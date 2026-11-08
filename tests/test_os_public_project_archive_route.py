"""Archive browse exposes one explicit GET and retains its exact predecessor."""
from pathlib import Path
from ops.executive_os.os_public_edge import GET_ROUTES, POST_ROUTES, PRE_ARCHIVE_GET_ROUTES, PRE_INSTRUCTION_ADMISSION_POST_ROUTES, TRANSITION_ROUTE_PROFILES, _TEMPLATE

ROUTE = "/workspace/projects/archive/current"

def test_archive_is_a_single_fixed_get_with_exact_predecessor():
    later = {"/workspace/project-knowledge/current", "/workspace/project-memory/current",
             "/workspace/project-source/current", "/workspace/source-operation/context",
             "/workspace/source-operation/operation", '/workspace/project-instructions/current', '/workspace/instruction-admission/current', '/workspace/instruction-admission/operation', '/workspace/project-access/current', '/workspace/source-operation/options', '/workspace/resources/host-observation/current', '/workspace/mission-result/current', '/workspace/native-draft-identity/current', '/workspace/byok/roles/current', '/workspace/resources/models/current'}
    assert set(GET_ROUTES) - set(PRE_ARCHIVE_GET_ROUTES) == {ROUTE, *later}
    assert GET_ROUTES.count(ROUTE) == 1 and ROUTE not in POST_ROUTES
    assert (PRE_ARCHIVE_GET_ROUTES, PRE_INSTRUCTION_ADMISSION_POST_ROUTES) in TRANSITION_ROUTE_PROFILES
    assert not any("*" in path for path in GET_ROUTES)
    source = (Path(__file__).parents[1] / "integrations/executive_mcp/server.py").read_text()
    assert source.count('"' + ROUTE + '"') == 3

def test_template_keeps_archive_in_get_only():
    text = _TEMPLATE.read_text()
    get = text.split("@get {", 1)[1].split("handle @get", 1)[0]
    post = text.split("@post {", 1)[1].split("handle @post", 1)[0]
    assert "method GET" in get and get.count(ROUTE) == 1 and ROUTE not in post
