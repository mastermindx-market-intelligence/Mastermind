"""Signed Workspace edge/transport proof for the original retained activity view.

HTTP fixture mirrors the genuine control-service output but does not
claim a customer's dual enrollment or installed machine source.
"""
from __future__ import annotations

import asyncio
import copy
import json

import pytest

from common import executive_workspace_activity_contract as activity
from common import executive_workspace_contract as wire
from integrations.mastermind_workspace_app.app import _activity_envelope_response
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from tests.test_workspace_retained_activity_read import owner_fixture, _run
from tests.test_workspace_read_socket import short_socket_root
from tests.test_workspace_read_app import (
    _make_app, _workspace_token, _FakeWorkspaceClient, rsa_key,
)

ROUTE = "/workspace/operator/activity/current"

@pytest.fixture
def owner(tmp_path, monkeypatch):
    with owner_fixture(tmp_path, monkeypatch) as actual:
        yield actual


def test_signed_http_request_keeps_original_activity_and_no_store(owner, rsa_key):
    original = _run(owner)
    assert original["result"]["availability"] == "AVAILABLE"
    fake = _FakeWorkspaceClient(envelope=original)
    app, recorded = _make_app(rsa_key, client=fake)
    response = app.get(
        ROUTE, params=owner["selected"],
        headers={"Authorization": "Bearer " + _workspace_token(rsa_key)},
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == original["result"]
    assert len(recorded.calls) == 1
    wire_frame = recorded.calls[0]
    assert wire_frame["schema"] == activity.FRAME_SCHEMA
    assert wire_frame["operation"] == activity.OPERATION
    assert wire_frame["selection"] == owner["selected"]
    assert wire_frame["principal"]["resource"] == wire.RESOURCE
    assert wire_frame["principal"]["scopes"] == [wire.SCOPE]
    assert activity.validate_result(response.json(), owner["selected"]) == response.json()


@pytest.mark.parametrize("bad", [
    {}, {"Authorization": "Bearer garbled"},
])
def test_unauthenticated_http_never_calls_original_reader(owner, rsa_key, bad):
    fake = _FakeWorkspaceClient(envelope=_run(owner))
    app, recorded = _make_app(rsa_key, client=fake)
    response = app.get(ROUTE, params=owner["selected"], headers=bad)
    assert response.status_code in (401, 403)
    assert recorded.calls == []


@pytest.mark.parametrize("query", [
    {"work_ref": "WS:ONE"},
    {"work_ref": "WS:ONE", "root_job_id": "JOB-1", "job_id": "JOB-2",
     "attempt_id": "ATT-" + "a" * 32, "raw": "secret"},
    {"work_ref": "../private", "root_job_id": "JOB-1", "job_id": "JOB-2",
     "attempt_id": "ATT-" + "a" * 32},
])
def test_bad_http_selectors_refuse_before_control_source(owner, rsa_key, query):
    fake = _FakeWorkspaceClient(envelope=_run(owner))
    app, recorded = _make_app(rsa_key, client=fake)
    response = app.get(
        ROUTE, params=query,
        headers={"Authorization": "Bearer " + _workspace_token(rsa_key)},
    )
    assert response.status_code == 400
    assert recorded.calls == []


@pytest.mark.parametrize("mutation", [
    "raw_provider_payload", "extra_body", "other_selection", "fake_live_workers",
    "missing_receipt", "fake_acceptance", "unknown_category",
])
def test_edge_closed_decoder_never_copies_unknown_source_fields(owner, mutation):
    data = copy.deepcopy(_run(owner))
    body = data["result"]
    if mutation == "raw_provider_payload":
        body["activity"]["rows"][0]["provider_payload"] = {"secret": "PRIVATE"}
    elif mutation == "extra_body":
        body["private_runtime"] = "/home/private"
    elif mutation == "other_selection":
        body["selection"]["root_job_id"] = "JOB-987"
    elif mutation == "fake_live_workers":
        body["activity"]["source"]["live_worker_count"] = 1
    elif mutation == "missing_receipt":
        body["source_observation"]["runtime"]["source_identity"] = None
    elif mutation == "fake_acceptance":
        body["activity"]["accepted"] = True
    else:
        body["activity"]["rows"][0]["category"] = "RAW_PROVIDER_REASONING"
    response = _activity_envelope_response(data)
    assert response.status_code == 503
    assert b"PRIVATE" not in response.body
    assert b"RAW_PROVIDER_REASONING" not in response.body
    assert b"/home/private" not in response.body


def test_public_unavailable_response_retains_no_attempt_event_data(owner):
    data = activity.unavailable(owner["selected"], "SOURCE_UNAVAILABLE")
    response = _activity_envelope_response(data)
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert json.loads(response.body)["activity"] is None
    assert "worker" not in response.body.decode().lower()


def test_client_rejects_wrong_frame_before_socket_and_caps_read(monkeypatch, owner):
    called = []
    async def forbidden(*args, **kwargs):
        called.append(kwargs["limit"])
        raise OSError("original transport unavailable")
    monkeypatch.setattr(asyncio, "open_unix_connection", forbidden)
    client = CeoIngressWorkspaceClient("/tmp/mmos-activity-do-not-open.sock")
    frame = dict(owner["request"])
    frame["operation"] = "mission_v3"
    with pytest.raises(ValueError):
        asyncio.run(client.request(frame))
    assert called == []
    with pytest.raises(ValueError):
        asyncio.run(client.request(owner["request"]))
    assert called == [activity.MAX_RESPONSE_BYTES]


def test_no_other_wire_protocol_inherits_sensitive_activity(owner):
    for schema in (wire.FRAME_SCHEMA, wire.FRAME_SCHEMA_V2, wire.FRAME_SCHEMA_V3):
        frame = {**owner["request"], "schema": schema}
        assert asyncio.run(owner["service"].handle_frame(frame)) == wire.error("invalid_input", 400)



@pytest.mark.parametrize("case", [
    "positive", "other_attempt", "workspace_revoked", "coo_revoked",
])
def test_actual_signed_http_unix_socket_coo_and_runtime_end_to_end(
    tmp_path, monkeypatch, rsa_key, short_socket_root, case,
):
    """Both different OAuth policies independently enrolled; actual signed
    JWT -> mounted HTTP -> existing Unix socket -> original COO + Runtime.
    Local synthetic source only. No production credential or native Fabic run.
    """
    from tests import test_workspace_admitted_plan_read as plan_suite
    from tests.test_workspace_read_app import _authenticator, _workspace_token, NOW
    from integrations.mastermind_workspace_app.contract import principal_frame
    from integrations.mastermind_executive_app.coo_binding import _digest
    from control_plane.workspace_read_service import WorkspaceReadService

    with owner_fixture(tmp_path, monkeypatch) as owner:
        auth = _authenticator(rsa_key)
        token = _workspace_token(rsa_key)
        verified = asyncio.run(
            auth.verify_authorization_header("Bearer " + token, now=NOW),
        )
        viewer = principal_frame(verified)
        coo = owner["mutable"]
        # Independent original COO policy accepts the *same underlying issuer,
        # subject and client* with its own policy ID, resource and scopes.
        policy = coo["policy"]
        policy["issuer"] = auth.policy.issuer
        policy["authorization_servers"] = [auth.policy.issuer]
        policy["jwks_uri"] = auth.policy.issuer + "/.well-known/jwks.json"
        policy["allowed_subject_digests"] = [viewer["subject_digest"]]
        enrolled = coo["binding"]["binding"]
        for name in ("issuer_digest", "subject_digest", "client_ref"):
            enrolled[name] = viewer[name]
        coo["missions"][0]["principal_binding_digest"] = _digest(enrolled)
        assert coo["policy"]["policy_id"] != viewer["policy_id"]
        assert coo["policy"]["resource"] != viewer["resource"]
        assert coo["binding"]["binding"]["scopes"] != viewer["scopes"]
        assert owner["coo"].source.for_workspace_read_principal(
            viewer, owner["selected"]["work_ref"],
        )[0]["enabled"] is True

        def original_service(subject, authorize):
            assert subject is owner
            service = WorkspaceReadService(
                cache=owner["cache"], runtime=owner["writer"],
                authorize=authorize, armed={}, runtime_identity={"db_present": True},
                bounded_runtime=lambda actual: owner["reader"]
                    if actual is owner["writer"] else pytest.fail("wrong Runtime"),
            )
            if case == "coo_revoked":
                original = service._read_retained_activity
                def revoke_during_original_source(frame):
                    result = original(frame)
                    coo["missions"][0]["enabled"] = False
                    return result
                service._read_retained_activity = revoke_during_original_source
            return service
        monkeypatch.setattr(plan_suite, "service", original_service)
        from dataclasses import replace as replace_installed_binding
        from control_plane.coo_principal_host import CooHostProvider
        original_control = plan_suite.control
        def genuine_coo_host(tmp, socket_root, workspace_factory):
            svc = original_control(tmp, socket_root, workspace_factory)
            original_binding = svc._ceo_ingress_app_binding
            svc._ceo_ingress_app_binding = replace_installed_binding(
                original_binding,
                principal_facts_factory=lambda runtime: CooHostProvider(
                    owner["coo"].source, workspace_factory(runtime),
                ),
                principal_admission_armed=True,
                principal_admission_guard=lambda _envelope: None,
            )
            return svc
        monkeypatch.setattr(plan_suite, "control", genuine_coo_host)

        def after_app(slots, _clock):
            if case == "workspace_revoked":
                slots["profiles"]["web"]["enabled"] = False

        async def run():
            async with plan_suite.transport(
                owner, rsa_key, tmp_path, short_socket_root,
                after_app=after_app if case == "workspace_revoked" else None,
            ) as (http, enrolled_token, slots, seen, client, principal, _mounted):
                assert principal_frame(principal) == viewer
                selection = dict(owner["selected"])
                if case == "other_attempt":
                    selection["attempt_id"] = "ATT-" + "9" * 32
                response = await http.get(
                    ROUTE, params=selection,
                    headers={"Authorization": "Bearer " + enrolled_token},
                )
                if case.endswith("revoked"):
                    assert response.status_code == 403
                    assert response.json()["error"]["code"] == "access_denied"
                    assert "candidate_event_id" not in response.text
                else:
                    assert response.status_code in (200, 503)
                    view = response.json()
                    if case == "positive":
                        assert response.status_code == 200, response.text
                        assert view["availability"] == "AVAILABLE"
                        assert view["activity"]["rows"][0]["category"] == "TURN_COMPLETED"
                        assert view["source_observation"]["state"] == "SAME"
                    else:
                        assert response.status_code == 503
                        assert view["availability"] == "UNAVAILABLE"
                        assert view["activity"] is None
                    assert response.headers["cache-control"] == "no-store"
                assert seen["factory"] >= 1
        asyncio.run(run())


def test_installed_socket_missing_original_coo_fails_before_any_runtime_reader(
    owner, tmp_path, short_socket_root,
):
    from tests.test_workspace_read_socket import control
    from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
    def forbidden_factory(_runtime):
        pytest.fail("unentitled Workspace source must never be opened")
    async def run():
        service = control(tmp_path, short_socket_root, forbidden_factory)
        await service.start()
        try:
            client = CeoIngressWorkspaceClient(service.ceo_ingress_socket_path)
            result = await client.request(owner["request"])
            assert result == wire.error("access_denied", 403)
        finally:
            await service.close()
    asyncio.run(run())


@pytest.mark.parametrize("method", ["HEAD", "POST", "OPTIONS", "DELETE"])
@pytest.mark.parametrize("signed", [True, False])
def test_non_get_activity_is_refused_by_original_raw_path_fence_before_auth_or_source(
    owner, rsa_key, method, signed,
):
    fake = _FakeWorkspaceClient(envelope=_run(owner))
    app, recorded = _make_app(rsa_key, client=fake)
    headers = ({"Authorization": "Bearer " + _workspace_token(rsa_key)}
               if signed else {})
    response = app.request(method, ROUTE, params=owner["selected"], headers=headers)
    assert response.status_code == 405
    assert response.headers["cache-control"] == "no-store"
    assert recorded.calls == []


def test_encoded_activity_route_rejected_before_auth_or_runtime(owner, rsa_key):
    fake = _FakeWorkspaceClient(envelope=_run(owner))
    app, recorded = _make_app(rsa_key, client=fake)
    response = app.get(
        "/workspace/operator%2factivity/current",
        params=owner["selected"],
        headers={"Authorization": "Bearer " + _workspace_token(rsa_key)},
    )
    assert response.status_code == 400
    assert recorded.calls == []
