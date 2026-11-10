"""Signed HTTP -> actual Workspace owner -> actual bounded Runtime return read."""
import copy

import pytest

from common import workspace_execution_return_contract as wire
from tests.test_workspace_execution_return_read import result_owner, retain, authorize, call
from tests.test_workspace_result_service import service
from tests.test_workspace_read_app import _make_app, _workspace_token, _FakeWorkspaceClient, rsa_key


class ActualOwnerClient:
    def __init__(self, owner):
        self.owner = service(owner, authorize=authorize)
        self.calls = []

    async def request(self, frame):
        self.calls.append(frame)
        return await self.owner.handle_frame(frame)


def test_signed_fixed_route_reaches_actual_runtime_without_effects(result_owner, rsa_key):
    o = result_owner
    _, _, _, record, receipt = retain(o)
    client = ActualOwnerClient(o)
    app, _ = _make_app(rsa_key, client=client, authorize=authorize)
    before = o["writer"].store.list_events()
    response = app.get(wire.PATH, params=o["selection"],
                       headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["execution_return"] == record and body["delivery_receipt"] == receipt
    assert len(client.calls) == 1
    assert client.calls[0]["schema"] == wire.FRAME_SCHEMA
    assert client.calls[0]["selection"] == o["selection"]
    assert o["writer"].store.list_events() == before


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer invalid"}])
def test_no_authentication_never_reaches_the_runtime(result_owner, rsa_key, headers):
    client = ActualOwnerClient(result_owner)
    app, _ = _make_app(rsa_key, client=client, authorize=authorize)
    response = app.get(wire.PATH, params=result_owner["selection"], headers=headers)
    assert response.status_code in (401, 403)
    assert client.calls == []


@pytest.mark.parametrize("alteration", ["missing", "extra", "duplicate", "path", "post", "body"])
def test_exact_read_boundary_refuses_before_owner(result_owner, rsa_key, alteration):
    client = ActualOwnerClient(result_owner)
    app, _ = _make_app(rsa_key, client=client, authorize=authorize)
    selected = dict(result_owner["selection"])
    method, path, content = "GET", wire.PATH, b""
    if alteration == "missing": selected.pop("result_envelope_digest")
    if alteration == "extra": selected["target"] = "another-conversation"
    if alteration == "duplicate": selected = list(selected.items()) + [("job_id", selected["job_id"])]
    if alteration == "path": path += "/"
    if alteration == "post": method = "POST"
    if alteration == "body": content = b"{}"
    response = app.request(method, path, params=selected, content=content,
                           headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code in (400, 404, 405)
    assert client.calls == []


@pytest.mark.parametrize("alteration", ["extra", "selection", "observation", "receipt"])
def test_edge_rejects_unqualified_backend_material(result_owner, rsa_key, alteration):
    retain(result_owner)
    envelope = copy.deepcopy(call(result_owner))
    body = envelope["result"]
    if alteration == "extra": body["native_binding"] = {"private": True}
    if alteration == "selection": body["selection"]["job_id"] = "JOB-999"
    if alteration == "observation": body["source_observation"]["runtime"]["state"] = "UNKNOWN"
    if alteration == "receipt": body["delivery_receipt"]["return_digest"] = "f" * 64
    app, _ = _make_app(rsa_key, client=_FakeWorkspaceClient(envelope=envelope), authorize=authorize)
    response = app.get(wire.PATH, params=result_owner["selection"],
                       headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "source_unavailable"
    assert "native_binding" not in response.text


def test_typed_unavailable_uses_own_schema_and_no_material(result_owner, rsa_key):
    envelope = wire.unavailable(result_owner["selection"], "SOURCE_UNAVAILABLE")
    app, _ = _make_app(rsa_key, client=_FakeWorkspaceClient(envelope=envelope), authorize=authorize)
    response = app.get(wire.PATH, params=result_owner["selection"],
                       headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 503
    assert response.json() == envelope["result"]
    assert response.headers["cache-control"] == "no-store"
