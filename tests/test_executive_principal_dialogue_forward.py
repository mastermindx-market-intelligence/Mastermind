"""Forwarding of one authenticated principal ruling; source-only tests.

Real signed JWTs and the existing COO App fixtures only; no real network,
service, credentials or installed Runtime. Transport failure injection is a
local mock at the existing client seam. These tests run only against the exact
source tree that provides the imported modules; one case performs one local
disposable Unix-server round trip through the real CeoIngressClient.
"""
from __future__ import annotations

import asyncio
import dataclasses
import inspect
import json
import sys
from pathlib import Path

import pytest
from starlette.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).parent))
try:
    import test_executive_coo_principal_caller as caller_fixture
finally:
    sys.path.pop(0)

from integrations.company_dialogue_principal_app_contract import APP_REQUEST_SCHEMA
from integrations.company_dialogue_principal_host_contract import (
    MAX_RESPONSE_BYTES, encode_json_frame, validate_response,
)
from integrations.mastermind_company_mcp.principal_schemas import (
    PRINCIPAL_RESULT_SCHEMA, PRINCIPAL_SERVER_VERSION, principal_result_envelope,
    validate_principal_tool_arguments,
)
from integrations.mastermind_executive_app.coo import create_coo_app
from integrations.mastermind_executive_app.coo_binding import COO_SCOPES
from integrations.mastermind_executive_app.gateway import (
    TRANSPORT_NOT_SENT, TRANSPORT_SENT_OK, TRANSPORT_SENT_UNKNOWN, CeoIngressResponse,
)
from integrations.mastermind_executive_app.principal_dialogue import (
    FORWARD_TOOL, PrincipalDialogueForwardResult, forward_principal_ruling,
)

rsa_key = caller_fixture.rsa_key
fixture = caller_fixture.fixture

SURFACE = "coo-qualified-host"
RULING = {"authority_class": "WITHIN_COMMISSION", "selected_option": "opt-continue",
          "decision": "continue the already-bound worker within the current commission",
          "rationale": "current mission facts still support the worker request",
          "evidence_refs": ["https://github.com/example/repo/pull/1"]}

def obligation_id():
    """Disposable id in the canonical Wake grammar; not an enrolled obligation."""
    return "WAKE-" + "a" * 32


class Client:
    """Transport seam mock only; the real one-send law and vocabulary hold."""

    def __init__(self, response=None, exc=None, after_send=None):
        self.frames = []
        self.paths = []
        self.response = response
        self.exc = exc
        self.after_send = after_send

    async def send_frame(self, socket_path, frame):
        self.paths.append(socket_path)
        self.frames.append(json.loads(json.dumps(frame)))
        if self.after_send is not None:
            self.after_send()
        if self.exc is not None:
            raise self.exc
        return self.response


def sent_ok(envelope):
    return CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=True,
        result=json.loads(encode_json_frame(envelope, limit=MAX_RESPONSE_BYTES)))


def ruling_envelope():
    return principal_result_envelope(FORWARD_TOOL, data={"ruling": "recorded"})


def refused_json(result):
    assert isinstance(result, JSONResponse)
    assert result.status_code in (401, 403, 400)
    assert b"PRIVATE_CANARY" not in result.body
    assert b"/private/" not in result.body
    return result


def forward(app, token, *, work_ref="WS:ONE", oid=None, arguments=None, surface=SURFACE):
    return asyncio.run(forward_principal_ruling(app,
        caller_fixture.request(token), work_ref=work_ref,
        obligation_id=obligation_id() if oid is None else oid,
        arguments=dict(RULING) if arguments is None else arguments,
        reasoning_surface=surface))


def setup_principal(rsa_key, tmp_path):
    app, token, current, settings = caller_fixture.setup(rsa_key, tmp_path)
    # Recompose the real mission reducer with a Runtime-shaped JOB identity.
    # The older generic mission fixture uses JOB-1, outside the dialogue grammar.
    from tests import test_mission_workspace as mission
    wrapper = mission._v3_inputs()["fabric_view"]
    args = mission._current_args_for_wrapper(wrapper)
    args = json.loads(json.dumps(args).replace('"JOB-1"', '"JOB-001"'))
    responsibility = args["control_room"]["autonomy"]["responsibilities"][0]
    responsibility["accountable_seat"] = "coo"
    responsibility["owed_turn"]["seat"] = "coo"
    mission._refresh_observation_digests(args)
    current["mission"] = fixture.mandate_fixture.mw.compose_mission_workspace_v3(**args)
    return app, token, current, settings


def setup_client(rsa_key, tmp_path, **client_kwargs):
    app, token, current, settings = setup_principal(rsa_key, tmp_path)
    client = Client(**client_kwargs)
    app._client = client
    return app, token, current, client


def expected_caller(app, token):
    derived = asyncio.run(app.resolve_principal_dialogue_caller(
        caller_fixture.request(token), work_ref="WS:ONE", reasoning_surface=SURFACE))
    value = dataclasses.asdict(derived)
    value["new_effect_gate"] = derived.new_effect_gate.value
    return value


def test_current_valid_caller_is_forwarded_and_decoded(rsa_key, tmp_path):
    app, token, _, client = setup_client(rsa_key, tmp_path, response=sent_ok(ruling_envelope()))
    oid = obligation_id()
    result = asyncio.run(forward_principal_ruling(app, caller_fixture.request(token),
        work_ref="WS:ONE", obligation_id=oid, arguments=dict(RULING), reasoning_surface=SURFACE))
    assert type(result) is PrincipalDialogueForwardResult
    assert result.obligation_id == oid
    assert result.transport == TRANSPORT_SENT_OK
    assert result.result["schema"] == PRINCIPAL_RESULT_SCHEMA
    assert result.result["ok"] is True
    assert result.result["server_version"] == PRINCIPAL_SERVER_VERSION
    assert result.result["data"] == {"ruling": "recorded"}
    assert len(client.frames) == 1
    frame = client.frames[0]
    assert frame["schema"] == APP_REQUEST_SCHEMA
    assert frame["tool"] == "ruling"
    assert frame["obligation_id"] == oid
    assert frame["caller"] == expected_caller(app, token)
    assert frame["arguments"] == RULING
    assert result.result == validate_response(
        encode_json_frame(result.result, limit=MAX_RESPONSE_BYTES), tool="ruling")


@pytest.mark.parametrize("fault", ["scope", "subject", "expired", "signature",
                                   "grant", "owed", "accountable", "binding"])
def test_token_role_or_binding_failure_sends_nothing(rsa_key, tmp_path, fault):
    app, token, current, client = setup_client(rsa_key, tmp_path)
    if fault == "scope":
        token = fixture.fixture._token(rsa_key, scope="mastermind.executive.read")
    elif fault == "subject":
        token = fixture.fixture._token(rsa_key, **{"scope": " ".join(COO_SCOPES), "sub": "another-subject"})
    elif fault == "expired":
        token = fixture.fixture._token(rsa_key, **{"scope": " ".join(COO_SCOPES),
            "iat": fixture.fixture.NOW - 600, "nbf": fixture.fixture.NOW - 600, "exp": fixture.fixture.NOW - 60})
    elif fault == "signature":
        parts = token.split(".")
        parts[2] = ("A" if parts[2][0] != "A" else "B") + parts[2][1:]
        token = ".".join(parts)
    elif fault == "grant":
        current["authority"] = dataclasses.replace(current["authority"],
            principal_actions=("bounded_intent",))
    elif fault == "owed":
        current["mission"]["principal"]["owed_turn"]["seat"] = "worker"
    elif fault == "accountable":
        current["mission"]["principal"]["accountable_seat"] = "ceo"
    else:
        current["binding"]["enabled"] = False
    refused_json(forward(app, token))
    assert client.frames == []


@pytest.mark.parametrize("fault", ["oid_space", "oid_empty", "missing_rationale",
                                   "extra_key", "bad_class", "bad_option", "not_dict"])
def test_invalid_obligation_or_arguments_send_nothing(rsa_key, tmp_path, fault):
    app, token, _, client = setup_client(rsa_key, tmp_path)
    oid = obligation_id()
    if fault == "oid_space":
        oid = "not an obligation id"
    elif fault == "oid_empty":
        oid = ""
    elif fault == "missing_rationale":
        arguments = {key: value for key, value in RULING.items() if key != "rationale"}
    elif fault == "extra_key":
        arguments = {**RULING, "thread": "T123"}
    elif fault == "bad_class":
        arguments = {**RULING, "authority_class": "ABSOLUTE"}
    elif fault == "bad_option":
        arguments = {**RULING, "selected_option": "approve"}
    else:
        arguments = list(RULING)
    kwargs = {} if fault.startswith("oid") else {"arguments": arguments}
    refused_json(forward(app, token, oid=oid, **kwargs))
    assert client.frames == []


@pytest.mark.parametrize("fault", ["lost", "malformed_result", "ok_missing",
                                   "wrong_type", "exception", "bad_inner_error"])
def test_one_send_and_unknown_on_lost_or_malformed_responses(rsa_key, tmp_path, fault):
    if fault == "lost":
        response = CeoIngressResponse(transport=TRANSPORT_SENT_UNKNOWN)
    elif fault == "malformed_result":
        response = CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=True,
                                      result={"unexpected": "shape"})
    elif fault == "ok_missing":
        response = CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=None,
                                      result=ruling_envelope())
    elif fault == "wrong_type":
        response = {"transport": TRANSPORT_SENT_OK, "ok": True}
    elif fault == "exception":
        response = None
    else:
        response = CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=True, result={
            "schema": PRINCIPAL_RESULT_SCHEMA, "tool": "ruling", "ok": False,
            "server_version": PRINCIPAL_SERVER_VERSION,
            "data": None, "error": {"code": "NOT_A_CODE", "message": "x"}})
    app, token, _, client = setup_client(rsa_key, tmp_path,
                                         response=response,
                                         exc=RuntimeError("PRIVATE_CANARY /private/socket") if fault == "exception" else None)
    oid = obligation_id()
    result = forward(app, token, oid=oid)
    assert type(result) is PrincipalDialogueForwardResult
    assert result.obligation_id == oid
    assert result.transport == TRANSPORT_SENT_UNKNOWN
    assert result.result is None
    assert len(client.frames) == 1
    assert b"PRIVATE_CANARY" not in json.dumps(result.result or {}).encode()


def test_post_send_binding_revocation_withholds_result(rsa_key, tmp_path):
    app, token, current, _ = setup_principal(rsa_key, tmp_path)
    state = {}
    def after_send():
        current["binding"]["enabled"] = False
        state["revoked"] = True
    client = Client(response=sent_ok(ruling_envelope()), after_send=after_send)
    app._client = client
    result = forward(app, token)
    assert state.get("revoked") is True
    assert len(client.frames) == 1
    assert result.transport == TRANSPORT_SENT_UNKNOWN
    assert result.result is None
    assert result.obligation_id == obligation_id()


def test_binding_change_after_caller_derivation_refuses_before_send(rsa_key, tmp_path, monkeypatch):
    app, token, current, client = setup_client(rsa_key, tmp_path)
    original = app.resolve_principal_dialogue_caller
    async def derive_then_revoke(*args, **kwargs):
        caller = await original(*args, **kwargs)
        current["binding"]["enabled"] = False
        return caller
    monkeypatch.setattr(app, "resolve_principal_dialogue_caller", derive_then_revoke)
    refused_json(forward(app, token))
    assert client.frames == []


def test_post_send_mission_closure_preserves_valid_response(rsa_key, tmp_path):
    app, token, current, _ = setup_principal(rsa_key, tmp_path)
    def after_send():
        # The ruling legitimately advances the mission; authentication is unchanged.
        current["mission"]["read_state"]["state"] = "HISTORICAL"
        current["mission"]["principal"]["owed_turn"]["seat"] = "worker"
    client = Client(response=sent_ok(ruling_envelope()), after_send=after_send)
    app._client = client
    result = forward(app, token)
    assert len(client.frames) == 1
    assert result.transport == TRANSPORT_SENT_OK
    assert result.result is not None and result.result["ok"] is True


def test_client_not_sent_classified_as_not_sent_with_no_result(rsa_key, tmp_path):
    app, token, _, client = setup_client(rsa_key, tmp_path, response=CeoIngressResponse(
        transport=TRANSPORT_NOT_SENT, ok=None, result=None, error=None, detail="connect refused"))
    oid = obligation_id()
    result = forward(app, token, oid=oid)
    assert type(result) is PrincipalDialogueForwardResult
    assert result.transport == TRANSPORT_NOT_SENT
    assert result.result is None
    assert result.obligation_id == oid
    assert len(client.frames) == 1


def test_no_caller_identity_is_acceptable_from_arguments_or_request_data():
    parameters = inspect.signature(forward_principal_ruling).parameters
    assert set(parameters) == {"app", "request", "work_ref", "obligation_id",
                               "arguments", "reasoning_surface"}
    assert not {"caller", "context", "peer", "guard", "principal", "stamp",
                "binding", "mission"} & set(parameters)


def test_forwarded_caller_is_always_the_real_derivation_not_a_fabrication(rsa_key, tmp_path):
    app, token, current, client = setup_client(rsa_key, tmp_path, response=sent_ok(ruling_envelope()))
    fabricated = dict(expected_caller(app, token))
    fabricated["root_job_id"] = "JOB-999"
    fabricated["reasoning_surface"] = "attacker-surface"
    forward(app, token)
    frame = client.frames[0]
    assert frame["caller"] != fabricated
    assert frame["caller"] == expected_caller(app, token)
    assert frame["caller"]["admission_context"]["work_ref"] == "WS:ONE"


def test_inner_refusal_is_sanitized_through_the_principal_error_envelope(rsa_key, tmp_path):
    inner = {"schema": PRINCIPAL_RESULT_SCHEMA, "tool": "ruling", "ok": False,
             "server_version": PRINCIPAL_SERVER_VERSION, "data": None,
             "error": {"code": "DIALOGUE_REFUSED",
                       "message": "refused xoxb-1234567890abcdef1234 secret",
                       "detail_code": "AUTHORITY_CLASS_CLOSED"}}
    app, token, _, client = setup_client(rsa_key, tmp_path,
                                         response=CeoIngressResponse(
                                             transport=TRANSPORT_SENT_OK, ok=True, result=inner))
    result = forward(app, token)
    assert result.transport == TRANSPORT_SENT_OK
    error = result.result["error"]
    assert error["code"] == "DIALOGUE_REFUSED"
    assert error["message"] == "DIALOGUE_REFUSED"
    assert "xoxb" not in error["message"]
    assert error["detail_code"] == "AUTHORITY_CLASS_CLOSED"


async def _round_trip(app, token, sock, envelope):
    replies = []

    async def handler(reader, writer):
        data = await reader.readline()
        if not data.endswith(b"\n"):
            data += await reader.read()
        frame = json.loads(data)
        replies.append(frame)
        writer.write(encode_json_frame({"ok": True, "result": envelope},
                                        limit=MAX_RESPONSE_BYTES))
        await writer.drain()
        writer.close()

    server = await asyncio.start_unix_server(handler, path=str(sock))
    try:
        return await forward_principal_ruling(app, caller_fixture.request(token),
            work_ref="WS:ONE", obligation_id=obligation_id(), arguments=dict(RULING),
            reasoning_surface=SURFACE)
    finally:
        server.close()
        await server.wait_closed()


def test_local_disposable_unix_server_round_trip_through_real_client(rsa_key, tmp_path):
    app, token, _, settings = setup_principal(rsa_key, tmp_path)
    # A short path: unix socket names are bounded well below pytest's tmp depth.
    sock = tmp_path / "app.sock"
    round_settings = dataclasses.replace(settings,
        executive=dataclasses.replace(settings.executive, ceo_ingress_socket_path=sock))
    app = create_coo_app(round_settings, audit_sink=fixture.Sink())
    try:
        result = asyncio.run(asyncio.wait_for(
            _round_trip(app, token, sock, ruling_envelope()), timeout=10))
    finally:
        sock.unlink(missing_ok=True)
    assert isinstance(result, PrincipalDialogueForwardResult)
    assert result.transport == TRANSPORT_SENT_OK
    assert result.result is not None and result.result["ok"] is True
    assert result.result["data"] == {"ruling": "recorded"}


def test_source_only_module_adds_no_installed_surface():
    import integrations.mastermind_executive_app.principal_dialogue as module
    public = {name for name in vars(module) if not name.startswith("_")}
    assert {"forward_principal_ruling", "PrincipalDialogueForwardResult",
            "FORWARD_TOOL"} <= public
    assert not any("route" in name.lower() or "listen" in name.lower() for name in public)
