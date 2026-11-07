"""Control Room reads through the complete installed-parent composition.

Signed JWTs, JWKS and the recording private client are fixtures. No installed
socket, identity provider, desktop action or Control/Worker service is used.
"""
import dataclasses
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from common.workspace_control_room_read_contract import FRAME_SCHEMA
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.executive_mcp import server
from tests import test_executive_mcp_app_composition as executive
from tests import test_workspace_read_app as workspace
from tests.test_workspace_control_room_read_edge import permitted

rsa_key = workspace.rsa_key
settings = executive.settings
short_socket_root = executive.short_socket_root

ORIGIN = "https://mcp.mastermind-x.com"
STATE = "/workspace/control-room/state/current"
DISCOVER = "/workspace/control-room/discover/current"


@pytest.fixture(params=["executive", "web_ceo_v3"])
def profile(request):
    return request.param


def _parent(settings, profile, *, workspace_app=None, sink=None):
    sink = sink or executive.Sink()
    if profile == "executive":
        return server.build_executive_mcp_app(
            settings, audit_sink=sink, workspace_app=workspace_app,
        )

    async def unrelated_owner(*args, **kwargs):
        raise AssertionError("a Workspace READ must not enter another owner")

    return server.build_web_ceo_v3_mcp_app(
        dataclasses.replace(settings, read_from_ceo_ingress=True),
        audit_sink=sink,
        mdm_reader=SimpleNamespace(
            list_macos_devices=unrelated_owner, device=unrelated_owner,
        ),
        session_target_projector=unrelated_owner,
        session_reply_handler=unrelated_owner,
        session_summon_handler=unrelated_owner,
        workspace_app=workspace_app,
    )


def _mounted(settings, rsa_key, profile, *, envelope=None, authorize=None, sink=None):
    backend = workspace._FakeWorkspaceClient(envelope=envelope)
    leaf, _ = workspace._make_app(
        rsa_key, client=backend,
        authorize=permitted() if authorize is None else authorize,
        authorize_discovery=permitted(),
    )
    sink = sink or executive.Sink()
    policy = workspace._workspace_policy()
    verifier = MastermindTokenVerifier(
        authenticator=workspace._authenticator(rsa_key, policy=policy),
        policy=policy, now=lambda: workspace.NOW, audit_sink=sink,
    )
    app = _parent(
        settings, profile, sink=sink,
        workspace_app=server.AuditedWorkspaceApp(leaf.app, verifier),
    )
    return TestClient(app, base_url=ORIGIN), backend, sink


@pytest.mark.parametrize("operation", ["state", "discover"])
def test_signed_read_traverses_parent_audit_and_leaf(settings, rsa_key, profile, operation):
    payload = {"control_room": {"schema": "mastermind.chairman_control_room.v1"},
               "composed_at": "2026-10-17T00:00:00Z"}
    client, backend, sink = _mounted(
        settings, rsa_key, profile, envelope={"ok": True, "result": payload},
    )
    with client:
        response = client.get(f"/workspace/control-room/{operation}/current", headers={
            "Authorization": "Bearer " + workspace._workspace_token(rsa_key),
        })
    assert response.status_code == 200
    assert response.json() == payload
    assert response.headers["Cache-Control"] == "no-store"
    assert len(backend.calls) == 1
    assert backend.calls[0]["schema"] == FRAME_SCHEMA
    assert backend.calls[0]["operation"] == operation
    assert backend.calls[0]["principal"]["scopes"] == ["mastermind.workspace.read"]
    assert sink.events and sink.events[-1].accepted is True


def test_parent_preserves_discovery_owner_refusal(settings, rsa_key, profile):
    client, backend, _ = _mounted(settings, rsa_key, profile, envelope={
        "ok": False, "status": 403,
        "error": {"code": "access_denied", "message": "control room unavailable"},
    })
    with client:
        response = client.get(DISCOVER, headers={
            "Authorization": "Bearer " + workspace._workspace_token(rsa_key),
        })
    assert response.status_code == 403
    assert len(backend.calls) == 1 and backend.calls[0]["operation"] == "discover"
    assert "candidate" not in response.text


@pytest.mark.parametrize("refusal", ["no_token", "foreign_subject", "wrong_scope",
                                    "revoked_member", "audit_failure"])
def test_parent_auth_refusals_never_acquire_private_source(settings, rsa_key, profile, refusal):
    sink = executive.Sink()
    if refusal == "audit_failure":
        def unavailable(_event):
            raise OSError("fixture audit unavailable")
        sink.emit = unavailable
    client, backend, _ = _mounted(
        settings, rsa_key, profile, sink=sink,
        authorize=(lambda _p: False) if refusal == "revoked_member" else None,
    )
    overrides = {}
    if refusal == "foreign_subject":
        overrides["sub"] = "different-unenrolled-fixture-subject"
    elif refusal == "wrong_scope":
        overrides["scope"] = "mastermind.executive.read"
    headers = {} if refusal == "no_token" else {
        "Authorization": "Bearer " + workspace._workspace_token(rsa_key, **overrides),
    }
    with client:
        response = client.get(STATE, headers=headers)
    assert response.status_code in {401, 403}
    assert backend.calls == []


@pytest.mark.parametrize("case", ["query", "post", "head", "alias", "slash",
                                  "host", "origin", "duplicate_authorization"])
def test_parent_framing_refuses_before_private_source(settings, rsa_key, profile, case):
    client, backend, _ = _mounted(settings, rsa_key, profile)
    bearer = "Bearer " + workspace._workspace_token(rsa_key)
    headers = {"Authorization": bearer}
    path, method, expected = STATE, "GET", {404}
    if case == "query":
        path += "?x=1"
    elif case in {"post", "head"}:
        method = case.upper()
    elif case == "alias":
        path = "/workspace/control-room%2Fstate/current"
    elif case == "slash":
        path += "/"
    elif case == "host":
        headers["Host"], expected = "foreign.example.test", {403}
    elif case == "origin":
        headers["Origin"], expected = "https://foreign.example.test", {403}
    else:
        headers = [("Authorization", bearer), ("Authorization", bearer)]
        expected = {400, 401}
    with client:
        response = client.request(method, path, headers=headers, follow_redirects=False)
    assert response.status_code in expected
    assert backend.calls == []


def test_absent_workspace_keeps_both_reads_unmounted(settings, profile):
    with TestClient(_parent(settings, profile), base_url=ORIGIN) as client:
        assert client.get(STATE).status_code == 404
        assert client.get(DISCOVER).status_code == 404
