"""Auth + HTTP-framing matrix for the v2 result/mission_v3 routes.

Hermetic tests: every ``client.request`` is replaced by a fake recording the
exact frame it would have been sent.  No socket is ever opened.  Each test
wires its own fake so timing-sensitive cases can revoke/expire mid-call.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any

import pytest
from starlette.testclient import TestClient

from integrations.mastermind_workspace_app import contract
from integrations.mastermind_workspace_app.app import (
    WorkspaceAppConfig,
    create_workspace_app,
)
from tests.test_workspace_read_app import (
    _FakeWorkspaceClient, _authenticator, _make_app, _workspace_token, NOW, RESOURCE, SCOPE,
    rsa_key,
)


def test_result_route_registered_with_strict_methods(rsa_key):
    test_client, _ = _make_app(rsa_key)
    # Non-GET methods must be refused by the route table — 405 Method Not Allowed
    # is the strict-by-construction reply for a route that exists for GET only.
    response = test_client.post("/workspace/result/current", headers={"Authorization": "Bearer x"})
    assert response.status_code == 405  # POST route not registered
    response = test_client.head("/workspace/result/current")
    assert response.status_code == 405  # HEAD not registered on v2


def test_result_route_refuses_missing_query(rsa_key):
    test_client, fake = _make_app(rsa_key)
    response = test_client.get("/workspace/result/current",
                                headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 400
    assert fake.calls == []


def test_result_route_refuses_v1_two_field_query(rsa_key):
    test_client, fake = _make_app(rsa_key)
    params = {"work_ref": "WS:AA1", "root_job_id": "JOB-1"}
    response = test_client.get("/workspace/result/current", params=params,
                                headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 400
    assert fake.calls == []


def test_result_route_refuses_unknown_query_key(rsa_key):
    test_client, fake = _make_app(rsa_key)
    params = {
        "work_ref": "WS:AA1", "root_job_id": "JOB-1", "job_id": "JOB-1",
        "attempt_id": "ATT-" + "0" * 32, "result_envelope_digest": "0" * 64,
        "extra": "x",
    }
    response = test_client.get("/workspace/result/current", params=params,
                                headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 400
    assert fake.calls == []


def test_result_route_refuses_duplicate_query_key(rsa_key):
    test_client, fake = _make_app(rsa_key)
    response = test_client.get(
        "/workspace/result/current?work_ref=WS:AA1&root_job_id=JOB-1&job_id=JOB-1&attempt_id=ATT-" + "0" * 32 + "&result_envelope_digest=" + "0" * 64 + "&work_ref=WS:AA2",
        headers={"Authorization": "Bearer " + _workspace_token(rsa_key)},
    )
    assert response.status_code == 400
    assert fake.calls == []


def test_result_route_refuses_semicolon_or_fragment(rsa_key):
    test_client, _ = _make_app(rsa_key)
    response = test_client.get(
        "/workspace/result/current?work_ref=WS:AA1;root_job_id=JOB-1",
        headers={"Authorization": "Bearer " + _workspace_token(rsa_key)},
    )
    assert response.status_code == 400
    response = test_client.get(
        "/workspace/result/current?work_ref=WS:AA1&root_job_id=JOB-1#frag",
        headers={"Authorization": "Bearer " + _workspace_token(rsa_key)},
    )
    assert response.status_code == 400


def test_result_route_refuses_plus_space_substitution(rsa_key):
    test_client, fake = _make_app(rsa_key)
    response = test_client.get(
        "/workspace/result/current?work_ref=WS:+AA1&root_job_id=JOB-1&job_id=JOB-1&attempt_id=ATT-" + "0" * 32 + "&result_envelope_digest=" + "0" * 64,
        headers={"Authorization": "Bearer " + _workspace_token(rsa_key)},
    )
    assert response.status_code == 400
    assert fake.calls == []


def test_result_route_refuses_malformed_selector_token(rsa_key):
    test_client, fake = _make_app(rsa_key)
    response = test_client.get(
        "/workspace/result/current?work_ref=WS:bad!token&root_job_id=JOB-1&job_id=JOB-1&attempt_id=ATT-" + "0" * 32 + "&result_envelope_digest=" + "0" * 64,
        headers={"Authorization": "Bearer " + _workspace_token(rsa_key)},
    )
    assert response.status_code == 400
    assert fake.calls == []


def test_result_route_dispatches_v2_frame_with_exact_selection(rsa_key):
    envelope = {"ok": True, "result": {"schema": contract.RESULT_BODY_SCHEMA,
                                       "availability": "UNAVAILABLE",
                                       "reason_codes": ["SOURCE_UNAVAILABLE"],
                                       "selection": {"work_ref": "WS:AA1", "root_job_id": "JOB-1",
                                                      "job_id": "JOB-1", "attempt_id": "ATT-" + "0" * 32,
                                                      "result_envelope_digest": "0" * 64},
                                       "source_observation": None, "result": None}}
    client = _FakeWorkspaceClient(envelope=envelope)
    test_client, fake = _make_app(rsa_key, client=client)
    response = test_client.get(
        "/workspace/result/current?work_ref=WS:AA1&root_job_id=JOB-1&job_id=JOB-1&attempt_id=ATT-" + "0" * 32 + "&result_envelope_digest=" + "0" * 64,
        headers={"Authorization": "Bearer " + _workspace_token(rsa_key)},
    )
    assert response.status_code == 503  # UNAVAILABLE maps to 503
    assert fake.calls, "client must have been reached"
    frame = fake.calls[0]
    assert frame["schema"] == contract.FRAME_SCHEMA_V2
    assert frame["operation"] == "result"
    assert set(frame["selection"]) == {"work_ref", "root_job_id", "job_id", "attempt_id", "result_envelope_digest"}


def test_mission_v3_route_dispatches_v2_frame(rsa_key):
    envelope = {"ok": True, "result": {"schema": "mastermind.mission_workspace.v3",
                                       "availability": "UNAVAILABLE",
                                       "reason_codes": ["SOURCE_UNAVAILABLE"]}}
    client = _FakeWorkspaceClient(envelope=envelope)
    test_client, fake = _make_app(rsa_key, client=client)
    response = test_client.get(
        "/workspace/mission/v3/current?work_ref=WS:AA1&root_job_id=JOB-1",
        headers={"Authorization": "Bearer " + _workspace_token(rsa_key)},
    )
    assert response.status_code == 503
    assert fake.calls, "client must have been reached"
    frame = fake.calls[0]
    assert frame["schema"] == contract.FRAME_SCHEMA_V2
    assert frame["operation"] == "mission_v3"
    assert set(frame["selection"]) == {"work_ref", "root_job_id"}


def test_v1_routes_remain_unchanged(rsa_key):
    """v1 mission and programs routes must continue to use the v1 frame."""
    envelope = {"ok": True, "result": {"schema": contract.PROGRAMS_SCHEMA,
                                       "availability": "AVAILABLE",
                                       "control_room": {"x": 1},
                                       "source_observation": {"state": "SAME"},
                                       "reason_codes": []}}
    client = _FakeWorkspaceClient(envelope=envelope)
    test_client, fake = _make_app(rsa_key, client=client)
    response = test_client.get("/workspace/programs/current",
                                headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 200
    assert fake.calls[0]["schema"] == contract.FRAME_SCHEMA
    assert fake.calls[0]["operation"] == "programs"


def test_permission_revoke_after_dispatch_returns_403(rsa_key):
    envelope = {"ok": True, "result": {"schema": contract.RESULT_BODY_SCHEMA,
                                       "availability": "UNAVAILABLE",
                                       "reason_codes": ["SOURCE_UNAVAILABLE"],
                                       "selection": {"work_ref": "WS:AA1", "root_job_id": "JOB-1",
                                                      "job_id": "JOB-1", "attempt_id": "ATT-" + "0" * 32,
                                                      "result_envelope_digest": "0" * 64},
                                       "source_observation": None, "result": None}}
    client = _FakeWorkspaceClient(envelope=envelope)
    authorized = [True]
    test_client, fake = _make_app(
        rsa_key, client=client,
        authorize=lambda _p: authorized[0],
    )
    # Authorize is consulted twice: once before dispatch, once after.  Revoke
    # between those calls so the post-read recheck returns False.
    def on_call(_frame):
        authorized[0] = False
    client._on_call = on_call
    response = test_client.get(
        "/workspace/result/current?work_ref=WS:AA1&root_job_id=JOB-1&job_id=JOB-1&attempt_id=ATT-" + "0" * 32 + "&result_envelope_digest=" + "0" * 64,
        headers={"Authorization": "Bearer " + _workspace_token(rsa_key)},
    )
    assert response.status_code == 403
    assert response.headers["Cache-Control"] == "no-store"


def test_permission_stamp_loss_after_dispatch_returns_403(rsa_key):
    envelope = {"ok": True, "result": {"schema": contract.RESULT_BODY_SCHEMA,
                                       "availability": "UNAVAILABLE",
                                       "reason_codes": ["SOURCE_UNAVAILABLE"],
                                       "selection": {"work_ref": "WS:AA1", "root_job_id": "JOB-1",
                                                      "job_id": "JOB-1", "attempt_id": "ATT-" + "0" * 32,
                                                      "result_envelope_digest": "0" * 64},
                                       "source_observation": None, "result": None}}
    client = _FakeWorkspaceClient(envelope=envelope)
    stamps = ["a" * 64, "b" * 64]
    authorize = lambda _p: True

    def binding_digest(_p):
        return stamps.pop(0)
    authorize.binding_digest = binding_digest
    test_client, fake = _make_app(rsa_key, client=client, authorize=authorize)
    response = test_client.get(
        "/workspace/result/current?work_ref=WS:AA1&root_job_id=JOB-1&job_id=JOB-1&attempt_id=ATT-" + "0" * 32 + "&result_envelope_digest=" + "0" * 64,
        headers={"Authorization": "Bearer " + _workspace_token(rsa_key)},
    )
    assert response.status_code == 403


def test_unicode_overhead_still_fits_result_budget(rsa_key):
    """The v2 envelope response never widens the result body beyond 16384."""
    payload = {"schema": contract.RESULT_BODY_SCHEMA,
               "selection": {"work_ref": "WS:AA1", "root_job_id": "JOB-1", "job_id": "JOB-1",
                              "attempt_id": "ATT-" + "0" * 32, "result_envelope_digest": "0" * 64},
               "availability": "AVAILABLE",
               "reason_codes": [],
               "source_observation": {"schema": contract.RESULT_OBSERVATION_SCHEMA,
                                       "state": "SAME",
                                       "selection": {"work_ref": "WS:AA1", "root_job_id": "JOB-1",
                                                      "job_id": "JOB-1", "attempt_id": "ATT-" + "0" * 32,
                                                      "result_envelope_digest": "0" * 64},
                                       "control_room": {"instance_before": "x", "instance_after": "x",
                                                         "publication_before": 1, "publication_after": 1,
                                                         "document_digest": "0" * 64,
                                                         "source_validity_digest": "0" * 64,
                                                         "cache_currentness_digest": "0" * 64},
                                       "runtime": {"schema": "mastermind.runtime_read_observation.v1",
                                                   "state": "SAME", "source_identity": "0" * 32,
                                                   "before": 1, "after": 1}},
               "result": {"schema": contract.PROJECTION_SCHEMA,
                          "selection": {"root_job_id": "JOB-1", "job_id": "JOB-1",
                                          "attempt_id": "ATT-" + "0" * 32,
                                          "result_envelope_digest": "0" * 64},
                          "role": "work", "execution_status": "COMPLETED",
                          "acceptance": "NOT_PROJECTED", "role_result_digest": "0" * 64,
                          "generation": {"schema": "mastermind.runtime_read_observation.v1",
                                          "state": "SAME", "source_identity": "0" * 32,
                                          "before": 1, "after": 1},
                          "availability": "AVAILABLE", "content_complete": True, "review": None,
                          "counts": {"findings": None, "next_actions": 0},
                          "content": {"role_result": {"comment": "你好" * 200},
                                       "summary": {"comment": "🌍"}, "next_actions": []},
                          "omitted": []}}
    client = _FakeWorkspaceClient(envelope={"ok": True, "result": payload})
    test_client, _ = _make_app(rsa_key, client=client)
    response = test_client.get(
        "/workspace/result/current?work_ref=WS:AA1&root_job_id=JOB-1&job_id=JOB-1&attempt_id=ATT-" + "0" * 32 + "&result_envelope_digest=" + "0" * 64,
        headers={"Authorization": "Bearer " + _workspace_token(rsa_key)},
    )
    assert response.status_code in (200, 503), response.text
    assert len(response.content) <= contract.MAX_RESULT_RESPONSE_BYTES

@pytest.mark.parametrize('size', [16383, 16384, 16385])
@pytest.mark.parametrize('unicode', [False, True])
def test_http_body_has_independent_exact_utf8_ceiling(rsa_key, size, unicode):
    # Deliberately transport-only data; this test isolates the HTTP encoder cap.
    body = {'availability': 'AVAILABLE', 'padding': '漢' if unicode else ''}
    body['padding'] += 'x' * (size - len(contract.canonical(body)))
    assert len(contract.canonical(body)) == size
    client, _ = _make_app(rsa_key, client=_FakeWorkspaceClient(envelope={'ok': True, 'result': body}))
    query = {'work_ref':'WS:ONE', 'root_job_id':'JOB-1', 'job_id':'JOB-1',
             'attempt_id':'ATT-'+'a'*32, 'result_envelope_digest':'b'*64}
    response = client.get('/workspace/result/current', params=query,
                          headers={'Authorization':'Bearer '+_workspace_token(rsa_key)})
    if size <= 16384:
        assert response.status_code == 200 and response.content == contract.canonical(body)
    else:
        assert response.status_code == 503 and 'padding' not in response.text


@pytest.mark.parametrize('stage', ['before', 'after'])
def test_result_missing_configured_permission_stamp_fails_closed(rsa_key, stage):
    fake = _FakeWorkspaceClient(envelope={'ok': True, 'result': {'content': 'must not release'}})
    authorize = lambda principal: True
    authorize.binding_digest = lambda principal: None if stage == 'before' or fake.calls else 'a'*64
    app = create_workspace_app(WorkspaceAppConfig(authenticator=_authenticator(rsa_key),
        now=lambda:NOW, authorize_principal=authorize, client=fake))
    with TestClient(app) as client:
        response = client.get('/workspace/result/current', params={'work_ref':'WS:ONE','root_job_id':'JOB-1','job_id':'JOB-1','attempt_id':'ATT-'+'a'*32,'result_envelope_digest':'b'*64},headers={'Authorization':'Bearer '+_workspace_token(rsa_key)})
    assert response.status_code == 403 and 'must not release' not in response.text
    assert len(fake.calls) == (stage == 'after')


@pytest.mark.parametrize('operation', ['result', 'mission_v3'])
@pytest.mark.parametrize('code', [[], {}])
def test_unhashable_failure_code_is_closed_without_content(rsa_key, operation, code):
    envelope={'ok':False,'status':503,'error':{'code':code,'message':'PRIVATE_SENTINEL'}}
    client,_=_make_app(rsa_key,client=_FakeWorkspaceClient(envelope=envelope))
    selection={'work_ref':'WS:ONE','root_job_id':'JOB-1'}
    path='/workspace/mission/v3/current'
    if operation=='result':
        path='/workspace/result/current'
        selection.update(job_id='JOB-1',attempt_id='ATT-'+'a'*32,result_envelope_digest='b'*64)
    response=client.get(path,params=selection,headers={'Authorization':'Bearer '+_workspace_token(rsa_key)})
    assert response.status_code==503 and response.headers['cache-control']=='no-store'
    assert 'PRIVATE_SENTINEL' not in response.text
    assert response.json()['error']['code']=='internal_error'
