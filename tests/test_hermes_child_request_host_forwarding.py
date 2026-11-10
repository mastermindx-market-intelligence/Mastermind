"""The WO-12 Hermes host lane: App-side child-request admission forwarding.

Covers the three layers the Hermes ``mastermind`` delegation backend rides:

1. ``CooApp.child_request_admit`` — the App-side forwarding of the private
   ``selected_child_admit`` frame (PR #2317 assigns this to WO-12): the
   frame's authority fields come from the App's own providers, the answer
   mapping is closed, and uncertainty keeps the original command.
2. ``build_hermes_host_mcp_app`` — the opt-in MCP producer over an existing
   COO App.  The model-facing ``mmx_delegate`` catalogue and its pinned
   digest are unchanged.
3. The full round-trip over the real stack: the real MCP edge (JSON-RPC
   over the streamable-HTTP manager), the real App, the real Unix ingress
   and the real Runtime — ADMITTED, REPLAY, precise conflict, precise WAIT.

All identities and sources are disposable dev/test fixtures (locally
generated RSA key, locally signed JWT) — the repo's own documented
dev/test issuance path; no production credentials are read or copied.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path

import httpx
import pytest
from starlette.requests import Request

from integrations.executive_mcp.coo import COO_TOOL_NAMES
from integrations.executive_mcp import hermes_host
from integrations.executive_mcp.hermes_host import (
    CHILD_REQUEST_ADMIT_INPUT_SCHEMA,
    CHILD_REQUEST_COMMAND_RE,
    HERMES_HOST_MCP_PATH,
    build_hermes_host_mcp_app,
    validate_child_request_admit_arguments,
)
from integrations.mastermind_executive_app import coo as coo_mod
from integrations.mastermind_executive_app.coo import create_coo_app
from tests import test_hermes_selected_child_ingress as ingress

rsa_key = ingress.rsa_key
WORK_REF = ingress.WORK_REF


def _command() -> str:
    return "child-request:" + "0" * 64


# ---------------------------------------------------------------------------
# 1. Closed shapes and byte-identical literals
# ---------------------------------------------------------------------------


def test_admission_schema_literals_are_byte_identical_to_the_core():
    from control_plane.executive_service import (
        CHILD_REQUEST_ADMISSION_SCHEMA as CORE_SCHEMA,
        CHILD_REQUEST_ADMISSION_STATES as CORE_STATES,
    )

    assert coo_mod.CHILD_REQUEST_ADMISSION_SCHEMA == CORE_SCHEMA
    assert coo_mod.CHILD_REQUEST_ADMISSION_STATES == CORE_STATES
    assert CORE_SCHEMA == "mastermind.child_request_admission/v1"


def test_host_tool_arguments_are_closed_and_precise():
    good = {"work_ref": WORK_REF, "command": _command()}
    assert validate_child_request_admit_arguments(good) == good
    for bad in (
        {"work_ref": WORK_REF, "command": "coo-cycle:r:dispatch:c:attempt:1"},
        {"work_ref": WORK_REF, "command": "child-request:zz"},
        {"work_ref": "WS:X", "command": _command()},
        {"work_ref": WORK_REF, "command": _command(), "envelope": {}},
        {"work_ref": WORK_REF},
        [good],
    ):
        with pytest.raises(ValueError):
            validate_child_request_admit_arguments(bad)
    assert CHILD_REQUEST_COMMAND_RE.fullmatch(_command())
    assert set(CHILD_REQUEST_ADMIT_INPUT_SCHEMA["properties"]) == {"work_ref", "command"}


def test_the_frozen_model_catalogue_is_unchanged():
    """The host lane adds NO model-facing tool; the pinned digest stands."""

    from integrations.executive_mcp.coo import (
        COO_TOOL_SCHEMA_DIGEST, coo_tool_schema_digest,
    )

    assert "child_request_admit" not in COO_TOOL_NAMES
    assert COO_TOOL_NAMES == ("executive_mandate", "executive_state",
                              "executive_inbox", "executive_fabric",
                              "submit_principal_intent", "principal_intent_status",
                              "mmx_delegate")
    assert coo_tool_schema_digest() == COO_TOOL_SCHEMA_DIGEST


@pytest.mark.parametrize("fault", ["foreign_schema", "bad_state", "wrong_command",
                                   "no_job_id", "wait_without_reason", "not_object",
                                   "bad_digest"])
def test_admission_projection_validator_is_closed(fault):
    base = {"schema": "mastermind.child_request_admission/v1", "state": "ADMITTED",
            "command_id": _command(), "job_id": "JOB-1", "request_digest": "a" * 64,
            "root_ref": "root", "logical_child_key": "key", "wait_reason": None,
            "wait_detail": {}}
    if fault == "foreign_schema":
        base["schema"] = "other/v1"
    elif fault == "bad_state":
        base["state"] = "MADE_UP"
    elif fault == "wrong_command":
        base["command_id"] = "child-request:" + "e" * 64
    elif fault == "no_job_id":
        base["job_id"] = ""
    elif fault == "wait_without_reason":
        base["state"] = "WAIT"
        base["job_id"] = None
        base["wait_reason"] = ""
    elif fault == "bad_digest":
        base["request_digest"] = "not-hex"
    with pytest.raises(ValueError):
        if fault == "not_object":
            coo_mod._child_request_admission_result(["x"], command_id=_command())
        else:
            coo_mod._child_request_admission_result(base, command_id=_command())


# ---------------------------------------------------------------------------
# 2. The App-side forwarding law over a fake transport
# ---------------------------------------------------------------------------


def _request_for(token: str) -> Request:
    return Request({"type": "http", "headers": [
        (b"authorization", ("Bearer " + token).encode())],
        "method": "POST", "path": "/", "query_string": b""})


def _forward(app, token: str, arguments: dict) -> dict:
    """Drive ``CooApp.child_request_admit`` directly (no HTTP hop)."""

    async def exercise():
        authenticated = await app.authorize_token(token)
        outcome = await app.child_request_admit(
            _request_for(token), authenticated, arguments)
        return json.loads(bytes(outcome.body))

    return asyncio.run(exercise())


def test_forwarding_requires_the_exact_frozen_target(rsa_key):
    settings, _current, token = ingress._app_settings(rsa_key, None)
    app = create_coo_app(settings, audit_sink=ingress.app_fixture.Sink())
    body = _forward(app, token, {"work_ref": WORK_REF, "command": _command()})
    assert body["ok"] is False
    assert body["error"]["kind"] == "refused"
    assert body["error"]["message"] == "EXECUTIVE_CHILD_REQUEST_TARGET_NOT_BOUND"


def test_forwarding_frame_carries_only_app_authority(rsa_key):
    """The private frame is built from the App's own providers only."""
    from integrations.mastermind_executive_app.gateway import CeoIngressResponse

    settings, _current, token = ingress._app_settings(rsa_key, ingress._target())
    app = create_coo_app(settings, audit_sink=ingress.app_fixture.Sink())
    frames = []

    async def send(path, frame):
        frames.append(frame)
        return CeoIngressResponse("sent_ok", ok=True, result={
            "schema": "mastermind.child_request_admission/v1", "state": "ADMITTED",
            "command_id": frame["request"]["command"], "job_id": "JOB-9",
            "request_digest": "a" * 64, "root_ref": "root",
            "logical_child_key": "key", "wait_reason": None, "wait_detail": {}})

    app._client.send_frame = send
    body = _forward(app, token, {"work_ref": WORK_REF, "command": _command()})
    assert body["ok"] is True, body
    assert body["result"]["state"] == "ADMITTED"
    assert body["result"]["job_id"] == "JOB-9"
    frame = frames[0]
    assert frame["schema"] == ingress.SELECTED_CHILD_FRAME_SCHEMA
    assert frame["request"] == {"action": "selected_child_admit",
                                "command": _command()}
    assert frame["target_digest"] == ingress._target().material_digest()
    assert set(frame["principal_context"]) == {
        "work_ref", "principal_binding_digest", "mission_authority_ref",
        "authority_generation_digest"}
    # The envelope never travels through the caller.
    assert "envelope" not in frame and "idempotency_key" not in frame


@pytest.mark.parametrize("answer", ["conflict", "not_frozen", "not_sent", "raise", "garbage"])
def test_forwarding_maps_every_owner_answer_honestly(rsa_key, answer):
    from integrations.mastermind_executive_app.gateway import CeoIngressResponse

    settings, _current, token = ingress._app_settings(rsa_key, ingress._target())
    app = create_coo_app(settings, audit_sink=ingress.app_fixture.Sink())

    async def send(path, frame):
        if answer == "conflict":
            return CeoIngressResponse("sent_ok", ok=False,
                                      error={"code": "conflict", "message": "drift"})
        if answer == "not_frozen":
            return CeoIngressResponse("sent_ok", ok=False,
                                      error={"code": "invalid_input", "message": "no"})
        if answer == "not_sent":
            return CeoIngressResponse("not_sent")
        if answer == "raise":
            raise RuntimeError("PRIVATE_POST_SEND_FAILURE")
        return CeoIngressResponse("sent_ok", ok=True, result={"unexpected": True})

    app._client.send_frame = send
    body = _forward(app, token, {"work_ref": WORK_REF, "command": _command()})
    assert body["ok"] is False, body
    kind = body["error"]["kind"]
    message = body["error"]["message"]
    if answer == "conflict":
        assert kind == "conflict" and "digest" in message
    elif answer == "not_frozen":
        assert kind == "refused" and "NOT_FROZEN" in message
    elif answer == "not_sent":
        assert kind == "refused" and "NOT_SENT" in message
    else:
        # A possible admission stays unknown; the original command is kept.
        assert kind == "unknown" and "EFFECT_UNKNOWN" in message


# ---------------------------------------------------------------------------
# 3. The real round-trip: MCP edge + App + Unix ingress + Runtime
# ---------------------------------------------------------------------------


async def _host_mcp_call(client, token, arguments):
    """One real signed MCP tool call over the host-lane route."""

    headers = {"authorization": "Bearer " + token,
               "accept": "application/json, text/event-stream",
               "mcp-protocol-version": "2025-06-18"}
    response = await client.post(HERMES_HOST_MCP_PATH, headers=headers, json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "child_request_admit", "arguments": arguments}})
    assert response.status_code == 200, response.text
    body = response.json()
    assert "error" not in body, body
    reply = body["result"]
    payload = json.loads(reply["content"][0]["text"])
    assert reply["isError"] is (payload.get("ok") is not True)
    return payload


def test_real_mcp_round_trip_admitted_replay_conflict_and_wait(
        tmp_path, rsa_key, monkeypatch):
    """The proof shape of the Hermes lane, at composition level.

    The real MCP edge (streamable-HTTP manager), the real App-side
    forwarding, the real Unix ingress and the real Runtime: one frozen
    envelope is ADMITTED once, replayed to the SAME Job, a drifted digest
    is a precise conflict, and a full queue is a precise WAIT.
    """
    monkeypatch.setenv("MMOS_CHILD_ROOT_READY_LIMIT", "1")

    async def exercise():
        import tempfile
        with tempfile.TemporaryDirectory(prefix="mmx-hermes-host-", dir="/tmp") as directory:
            socket_root = Path(directory)
            async with ingress._control(tmp_path, socket_root,
                                        name="hermes-host-forwarding") as host:
                service = host.service
                settings, token = await ingress._installed_app(
                    host, rsa_key, socket_path=host.socket)
                core = create_coo_app(settings, audit_sink=ingress.app_fixture.Sink())
                app = build_hermes_host_mcp_app(core)
                assert type(app) is hermes_host.HermesHostMcpBoundary
                command, envelope = ingress._admission_material(
                    host.root.job_id, host.root.job_id, "hermes-host-key-0001")
                service._ceo_ingress_app_binding = dataclasses.replace(
                    service._ceo_ingress_app_binding,
                    child_request_material={command: envelope})

                async with app._app.router.lifespan_context(app._app):
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app),
                        base_url="http://127.0.0.1") as client:
                        admitted = await _host_mcp_call(client, token, {
                            "work_ref": WORK_REF, "command": command})
                        assert admitted["ok"] is True, admitted
                        assert admitted["result"]["state"] == "ADMITTED", admitted
                        job_id = admitted["result"]["job_id"]
                        assert admitted["result"]["command_id"] == command

                        replay = await _host_mcp_call(client, token, {
                            "work_ref": WORK_REF, "command": command})
                        assert replay["ok"] is True, replay
                        assert replay["result"]["state"] == "REPLAY", replay
                        assert replay["result"]["job_id"] == job_id

                        unfrozen = await _host_mcp_call(client, token, {
                            "work_ref": WORK_REF,
                            "command": "child-request:" + "e" * 64})
                        assert unfrozen["ok"] is False, unfrozen
                        assert unfrozen["error"]["kind"] == "refused", unfrozen
                        assert "NOT_FROZEN" in unfrozen["error"]["message"]

                        # The host re-freezes the SAME command with a
                        # different goal digest: a precise conflict.
                        _, drifted = ingress._admission_material(
                            host.root.job_id, host.root.job_id,
                            "hermes-host-key-0001", brief_digest="c" * 64)
                        service._ceo_ingress_app_binding = dataclasses.replace(
                            service._ceo_ingress_app_binding,
                            child_request_material={command: drifted})
                        conflict = await _host_mcp_call(client, token, {
                            "work_ref": WORK_REF, "command": command})
                        assert conflict["ok"] is False, conflict
                        assert conflict["error"]["kind"] == "conflict", conflict

                        # The per-root cap (configured at one) sends a second
                        # logical child back with a precise wait reason.
                        second_command, second = ingress._admission_material(
                            host.root.job_id, host.root.job_id,
                            "hermes-host-key-0002")
                        service._ceo_ingress_app_binding = dataclasses.replace(
                            service._ceo_ingress_app_binding,
                            child_request_material={command: drifted,
                                                    second_command: second})
                        wait = await _host_mcp_call(client, token, {
                            "work_ref": WORK_REF, "command": second_command})
                        assert wait["ok"] is True, wait
                        assert wait["result"]["state"] == "WAIT", wait
                        assert wait["result"]["wait_reason"] == \
                            "CHILD_QUEUE_ROOT_READY_FULL"

                        with service.runtime.store.read() as connection:
                            count = int(connection.execute(
                                "SELECT COUNT(*) FROM events e JOIN jobs j"
                                " ON j.job_id=e.job_id"
                                " WHERE e.event_type='JOB_CREATED'"
                                " AND json_extract(e.payload_json,"
                                " '$.provenance.child_request.schema')"
                                " = 'ChildExecutionRequest.v1'"
                            ).fetchone()[0])
                        assert count == 1
                        assert service.runtime.jobs.get_job(job_id).attempt_count == 0
                        host.finish_gate.set()
                        await asyncio.sleep(0.05)

    asyncio.run(exercise())
