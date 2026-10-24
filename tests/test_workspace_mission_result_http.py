"""Signed test HTTP and Unix export of one associated Mission/Result read.

The Executive MCP path fence is outside this slice's writable ceiling, so these
tests drive the workspace app and the existing Unix client directly. They do
not qualify installed namespace custody or an Auth0 registration.
"""
import asyncio
import hashlib
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode

import httpx
import pytest

from control_plane import executive_runtime as er
from control_plane import fabric_result_projection as frp
from control_plane.workspace_read_service import WorkspaceReadService
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from integrations.mastermind_workspace_app.contract import (
    BINDINGS_SCHEMA,
    MISSION_RESULT_FRAME_SCHEMA,
    MISSION_RESULT_OPERATION,
    canonical,
    principal_frame,
    workspace_authorizers,
)
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from tests.test_workspace_read_app import NOW, _authenticator, _workspace_token, rsa_key
from tests.test_workspace_read_socket import control, short_socket_root
from tests.test_workspace_result_service import result_owner

ROUTE = "/workspace/mission-result/current"
CAPTURE = os.environ.get("MISSION_RESULT_CAPTURE_DIR")


@asynccontextmanager
async def app_transport(owner, rsa_key, tmp_path, socket_root, *, after_control=None, after_app=None):
    auth = _authenticator(rsa_key)
    token = _workspace_token(rsa_key)
    principal = await auth.verify_authorization_header("Bearer " + token, now=NOW)
    slots = {"schema": BINDINGS_SCHEMA, "profiles": {
        "web": {"enabled": True, "binding": dict(principal_frame(principal), permission_digest="a" * 64)},
        "mac": {"enabled": False, "binding": None},
    }}
    app_auth, control_auth = workspace_authorizers(policy=auth.policy, load_bindings=lambda: slots)
    seen = {"factory": 0, "projected": []}

    def factory(actual):
        assert actual is owner["writer"]
        seen["factory"] += 1

        def project(snapshot, receipt):
            value = frp.project_fabric_role_result(snapshot, receipt)
            seen["projected"].append(value)
            if after_control:
                after_control(slots)
            return value

        return WorkspaceReadService(
            cache=owner["cache"], runtime=actual, authorize=control_auth,
            armed={}, runtime_identity={"db_present": True}, result_project=project,
            bounded_runtime=lambda candidate: owner["reader"] if candidate is owner["writer"] else pytest.fail("wrong owner"),
        )

    service = control(tmp_path, socket_root, factory)
    service._runtime_factory = lambda path: owner["writer"]
    await service.start()
    client = CeoIngressWorkspaceClient(service.ceo_ingress_socket_path)

    class AppClient:
        async def request(self, frame):
            response = await client.request(frame)
            if after_app:
                after_app(slots)
            return response

    workspace = create_workspace_app(WorkspaceAppConfig(
        authenticator=auth, now=lambda: NOW, authorize_principal=app_auth, client=AppClient(),
    ))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=workspace),
            base_url="https://mcp.mastermind-x.com",
        ) as http:
            yield http, token, slots, seen, client, principal, workspace
    finally:
        await service.close()


def _frame(owner, principal):
    return {
        "schema": MISSION_RESULT_FRAME_SCHEMA,
        "operation": MISSION_RESULT_OPERATION,
        "selection": dict(owner["selection"]),
        "principal": principal_frame(principal),
    }


def _assert_pair(body, selection):
    assert body["schema"] == "mastermind.workspace_mission_result.v1"
    assert body["availability"] == "AVAILABLE"
    assert body["reason_codes"] == []
    mission, role = body["mission"], body["role_result"]
    assert mission["schema"] == "mastermind.mission_workspace.v3"
    assert mission["read_state"]["state"] == "CURRENT"
    assert role["schema"] == "mastermind.workspace_role_result.v1"
    assert role["availability"] == "AVAILABLE"
    identity = role["source_observation"]["runtime"]["source_identity"]
    assert mission["source"]["owner_observation"]["runtime"]["source_identity"] == identity
    assert mission["result_refs"]["generation"]["source_identity"] == identity
    assert mission["result_refs"]["generation"]["before"] == role["source_observation"]["runtime"]["before"]
    assert mission["result_refs"]["generation"]["after"] == role["source_observation"]["runtime"]["after"]
    assert any(
        ref["root_job_id"] == selection["root_job_id"]
        and ref["job_id"] == selection["job_id"]
        and ref["attempt_id"] == selection["attempt_id"]
        and ref["result_envelope_digest"] == selection["result_envelope_digest"]
        for ref in mission["result_refs"]["refs"]
    )
    assert role["result"]["review"]["verdict"] == "reject"
    assert role["result"]["execution_status"] == "COMPLETED"
    assert role["result"]["acceptance"] == "NOT_PROJECTED"
    assert mission["acceptance"]["state"] == "NOT_PROJECTED"
    assert role["source_observation"]["control_room"] == mission["source"]["owner_observation"]["control_room"]


def test_signed_export_is_the_associated_compound_body(
    result_owner, rsa_key, tmp_path, short_socket_root, monkeypatch,
):
    owner = result_owner
    for registry, method in (
        (owner["reader"].jobs, "list_jobs"),
        (owner["reader"].attempts, "list_attempts"),
        (owner["reader"].events, "list_events"),
    ):
        monkeypatch.setattr(registry, method, lambda *args, **kwargs: pytest.fail("unbounded acquisition"))

    async def run():
        async with app_transport(owner, rsa_key, tmp_path, short_socket_root) as (
            http, token, _slots, seen, client, principal, _workspace,
        ):
            headers = {"Authorization": "Bearer " + token}
            traces = []
            original = er.sqlite3.connect

            def connect(*args, **kwargs):
                connection = original(*args, **kwargs)
                connection.set_trace_callback(traces.append)
                return connection

            monkeypatch.setattr(er.sqlite3, "connect", connect)
            before = owner["namespace"].entries
            response = await http.get(ROUTE, params=owner["selection"], headers=headers)
            assert response.status_code == 200, response.text
            assert response.headers["cache-control"] == "no-store"
            body = response.json()
            _assert_pair(body, owner["selection"])
            statements = [sql.strip().upper() for sql in traces]
            assert statements.count("PRAGMA DATA_VERSION") == 2
            assert not any(sql.startswith(("INSERT", "UPDATE", "DELETE")) for sql in statements)
            assert len(statements) <= er.BOUNDED_ROLE_RESULT_MAX_STATEMENTS
            assert owner["namespace"].entries == before + 1 == owner["namespace"].exits
            assert response.content == canonical(body)
            assert len(canonical({"ok": True, "result": body["role_result"]})) + 1 <= 16384
            assert len(canonical({"ok": True, "result": body})) + 1 <= 2_000_000
            socket = await client.request(_frame(owner, principal))
            assert socket["ok"] is True
            _assert_pair(socket["result"], owner["selection"])
            assert (
                socket["result"]["role_result"]["source_observation"]["runtime"]["source_identity"]
                != body["role_result"]["source_observation"]["runtime"]["source_identity"]
            )
            second = await http.get(ROUTE, params=owner["selection"], headers=headers)
            assert second.status_code == 200
            assert (
                second.json()["role_result"]["source_observation"]["runtime"]["source_identity"]
                != body["role_result"]["source_observation"]["runtime"]["source_identity"]
            )
            assert seen["factory"] >= 1
            if CAPTURE:
                destination = Path(CAPTURE)
                destination.mkdir(parents=True, exist_ok=True)
                (destination / "actual-pair.json").write_bytes(response.content)
                runtime = body["role_result"]["source_observation"]["runtime"]
                provenance = {
                    "proof_ceiling": "SOURCE_ASSOCIATED_READ_QUALIFIED",
                    "brief_sha": "317eae34ecfda3fa4ef65fd80d1700e06bd5264f",
                    "route": ROUTE,
                    "http_body_sha256": hashlib.sha256(response.content).hexdigest(),
                    "http_body_bytes": len(response.content),
                    "selection": body["selection"],
                    "mission_schema": body["mission"]["schema"],
                    "role_result_schema": body["role_result"]["schema"],
                    "mission_read_state": body["mission"]["read_state"]["state"],
                    "role_result_availability": body["role_result"]["availability"],
                    "mission_runtime_source_identity": body["mission"]["source"]["owner_observation"]["runtime"]["source_identity"],
                    "role_result_runtime_source_identity": runtime["source_identity"],
                    "runtime_before": runtime["before"],
                    "runtime_after": runtime["after"],
                    "control_room": body["role_result"]["source_observation"]["control_room"],
                    "review_verdict": body["role_result"]["result"]["review"]["verdict"],
                    "execution_status": body["role_result"]["result"]["execution_status"],
                    "acceptance": body["role_result"]["result"]["acceptance"],
                    "mission_acceptance": body["mission"]["acceptance"]["state"],
                    "note": (
                        "http_body_sha256 is the whole HTTP response body. "
                        "Nested mission and role_result are fields of that body, "
                        "not separate raw HTTP responses."
                    ),
                }
                (destination / "fixture-provenance.json").write_text(
                    json.dumps(provenance, indent=2, sort_keys=True) + "\n",
                )

    asyncio.run(run())


def test_deny_and_malformed_digest_stop_before_runtime(
    result_owner, rsa_key, tmp_path, short_socket_root,
):
    owner = result_owner

    async def run():
        async with app_transport(owner, rsa_key, tmp_path, short_socket_root) as (
            http, token, slots, seen, _client, _principal, workspace,
        ):
            owner["cache"].snapshot = lambda: pytest.fail("cache before permission")
            before = owner["namespace"].entries
            for bad in (
                None,
                _workspace_token(rsa_key, client_id="foreign"),
                _workspace_token(rsa_key, scope="mastermind.executive.read"),
                _workspace_token(rsa_key, sub="foreign"),
                _workspace_token(rsa_key, resource="https://wrong.example.test"),
            ):
                headers = {} if bad is None else {"Authorization": "Bearer " + bad}
                response = await http.get(ROUTE, params=owner["selection"], headers=headers)
                assert response.status_code in (401, 403), response.text
                assert seen["factory"] == 0
                assert owner["namespace"].entries == before
            slots["profiles"]["web"]["enabled"] = False
            disabled = await http.get(
                ROUTE, params=owner["selection"], headers={"Authorization": "Bearer " + token},
            )
            assert disabled.status_code == 403
            assert seen["factory"] == 0
            slots["profiles"]["web"]["enabled"] = True
            bad_selection = dict(owner["selection"], result_envelope_digest="not-a-digest")
            malformed = await http.get(
                ROUTE, params=bad_selection, headers={"Authorization": "Bearer " + token},
            )
            assert malformed.status_code == 400, malformed.text
            assert seen["factory"] == 0
            assert owner["namespace"].entries == before
            sent = []

            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(event):
                sent.append(event)

            query = urlencode(owner["selection"]).encode() + b"&extra=x"
            await workspace({
                "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                "scheme": "https", "method": "GET", "path": ROUTE,
                "raw_path": ROUTE.encode(), "root_path": "", "query_string": query,
                "headers": [
                    (b"host", b"mcp.mastermind-x.com"),
                    (b"authorization", ("Bearer " + token).encode()),
                ],
                "client": ("127.0.0.1", 1), "server": ("mcp.mastermind-x.com", 443),
            }, receive, send)
            assert next(event["status"] for event in sent if event["type"] == "http.response.start") == 400
            assert seen["factory"] == 0

    asyncio.run(run())


@pytest.mark.parametrize("gate", ["control", "app"])
def test_permission_reload_hides_the_pair(
    result_owner, rsa_key, tmp_path, short_socket_root, gate,
):
    def mutate(slots):
        slots["profiles"]["web"]["enabled"] = False

    async def run():
        async with app_transport(
            result_owner, rsa_key, tmp_path, short_socket_root, **{"after_" + gate: mutate},
        ) as (http, token, _slots, seen, *_rest):
            response = await http.get(
                ROUTE, params=result_owner["selection"],
                headers={"Authorization": "Bearer " + token},
            )
            assert response.status_code == 403, response.text
            assert seen["projected"]
            assert "role_result" not in response.text
            assert "reject" not in response.text

    asyncio.run(run())
