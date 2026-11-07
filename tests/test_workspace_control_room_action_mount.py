"""Four fixed actions through both actual Executive parent builders.

JWTs, audit sink and private client are isolated fixtures. No installed action.
"""
import pytest
from starlette.testclient import TestClient

from common import workspace_control_room_action_contract as wire
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.executive_mcp import server
from tests import test_workspace_read_app as workspace
from tests import test_workspace_control_room_action_http as action
from tests import test_executive_mcp_app_composition as executive
from tests.test_workspace_control_room_mount import _parent, profile

rsa_key = workspace.rsa_key
settings = executive.settings
short_socket_root = executive.short_socket_root
ORIGIN = "https://mcp.mastermind-x.com"


def mounted(settings, rsa_key, profile, *, operation="open", expected=None,
            selected=True, sink=None):
    grants = {name: action.Grant(name) for name in action.OPERATIONS}
    if not selected:
        grants[operation].active = False
    backend = workspace._FakeWorkspaceClient(envelope={
        "ok": True, "result": expected or action.result(operation)})
    leaf, _, _ = action.make(rsa_key, operation=operation, backend=backend, actions=grants)
    sink = sink or executive.Sink()
    policy = workspace._workspace_policy()
    verifier = MastermindTokenVerifier(
        authenticator=workspace._authenticator(rsa_key, policy=policy),
        policy=policy, now=lambda: workspace.NOW, audit_sink=sink,
    )
    app = _parent(settings, profile, sink=sink,
                  workspace_app=server.AuditedWorkspaceApp(leaf.app, verifier))
    return TestClient(app, base_url=ORIGIN), backend, sink


@pytest.mark.parametrize("operation", action.OPERATIONS)
def test_parent_preserves_one_exact_action_and_its_complete_result(
        settings, rsa_key, profile, operation):
    expected = {
        "open": action.result("open", disposition="NOT_DISPATCHED", status=409,
                              outcome={"ok": False, "failure_kind": "owed_source_changed"}),
        "bind": wire.unknown_result("bind"),
        "unbind": action.result("unbind", outcome={"ok": False, "detail": "not removed"}),
        "refresh-builds": action.result("refresh-builds", outcome={"ok": True}),
    }[operation]
    client, backend, sink = mounted(settings, rsa_key, profile, operation=operation,
                                    expected=expected)
    with client:
        response = client.post("/workspace/control-room/" + operation,
                               headers=action.headers(rsa_key), json=action.payload(operation))
    assert response.status_code == expected["status"] and response.json() == expected
    assert response.headers["Cache-Control"] == "no-store"
    assert len(backend.calls) == 1
    assert backend.calls[0]["schema"] == wire.FRAME_SCHEMA
    assert backend.calls[0]["operation"] == operation
    assert backend.calls[0]["payload"] == action.payload(operation)
    assert sink.events and sink.events[-1].accepted is True


@pytest.mark.parametrize("operation", action.OPERATIONS)
@pytest.mark.parametrize("fault", ["get", "head", "query", "alias", "slash", "scheme",
                                  "host", "duplicate_host", "origin", "duplicate_origin",
                                  "duplicate_authorization"])
def test_each_parent_action_retains_exact_public_framing(
        settings, rsa_key, profile, operation, fault):
    client, backend, _ = mounted(settings, rsa_key, profile, operation=operation)
    path, method, headers = "/workspace/control-room/" + operation, "POST", action.headers(rsa_key)
    expected = 404
    if fault in {"get", "head"}:
        method = fault.upper()
    elif fault == "query":
        path += "?principal=foreign"
    elif fault == "alias":
        path = "/workspace/control-room%2F" + operation
    elif fault == "slash":
        path += "/"
    elif fault == "scheme":
        path, expected = "http://mcp.mastermind-x.com" + path, 403
    elif fault == "host":
        headers["Host"], expected = "foreign.example.test", 403
    elif fault == "duplicate_host":
        headers = list(headers.items()) + [("Host", "mcp.mastermind-x.com")] * 2
        expected = 403
    elif fault == "origin":
        headers["Origin"], expected = "https://foreign.example.test", 403
    elif fault == "duplicate_origin":
        headers = list(headers.items()) + [("Origin", ORIGIN)] * 2
        expected = 403
    else:
        headers = list(headers.items()) + [("Authorization", headers["Authorization"])]
        expected = 401
    with client:
        response = client.request(method, path, headers=headers,
                                  json=action.payload(operation), follow_redirects=False)
    assert response.status_code == expected
    assert backend.calls == []


@pytest.mark.parametrize("fault", ["no_token", "foreign_subject", "wrong_scope",
                                  "selected_grant", "audit_failure"])
def test_parent_auth_or_grant_refusal_never_invokes_action(
        settings, rsa_key, profile, fault):
    sink = executive.Sink()
    if fault == "audit_failure":
        def refused(_event):
            raise OSError("fixture audit unavailable")
        sink.emit = refused
    client, backend, _ = mounted(settings, rsa_key, profile, sink=sink,
                                selected=fault != "selected_grant")
    overrides = {}
    if fault == "foreign_subject":
        overrides["sub"] = "unenrolled-fixture"
    elif fault == "wrong_scope":
        overrides["scope"] = "mastermind.executive.read"
    headers = {} if fault == "no_token" else {
        "Authorization": "Bearer " + workspace._workspace_token(rsa_key, **overrides),
    }
    with client:
        response = client.post("/workspace/control-room/open", headers=headers,
                               json=action.payload("open"))
    assert response.status_code in {401, 403}
    assert backend.calls == []


def test_absent_workspace_keeps_all_six_control_room_routes_unmounted(settings, profile):
    with TestClient(_parent(settings, profile), base_url=ORIGIN) as client:
        for operation in action.OPERATIONS:
            assert client.post("/workspace/control-room/" + operation,
                               json=action.payload(operation)).status_code == 404
        for operation in ("state", "discover"):
            assert client.get("/workspace/control-room/" + operation + "/current").status_code == 404
