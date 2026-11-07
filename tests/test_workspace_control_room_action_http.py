"""Authenticated action admission and effect truth at the existing Workspace edge.

Only fixture JWTs and recording clients are used; no installed socket or effect.
"""
from __future__ import annotations

import asyncio
import hashlib
import json

import httpx
import pytest
from starlette.testclient import TestClient

from common import workspace_control_room_action_contract as wire
from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from tests import test_workspace_read_app as existing

rsa_key = existing.rsa_key
OPERATIONS = ("open", "bind", "unbind", "refresh-builds")
UNSET = object()


class Grant:
    def __init__(self, name="read"):
        self.name, self.active, self.generation = name, True, 0

    def __call__(self, principal):
        return self.active and type(principal) is VerifiedPrincipal

    def binding_digest(self, principal):
        if not self(principal):
            return None
        return hashlib.sha256(f"{self.name}:{self.generation}".encode()).hexdigest()


def payload(operation):
    return {
        "open": {"binding_id": "BIND-fixture", "owed_context": None},
        "bind": {"work_ref": "WS:fixture", "role": "ceo", "provider": "codex",
                 "locator": {"session_id": "fixture-session"}},
        "unbind": {"binding_id": "BIND-fixture"},
        "refresh-builds": {},
    }[operation]


def result(operation, *, disposition="OWNER_RETURNED", status=200, outcome=None):
    if disposition == "EFFECT_UNKNOWN":
        return wire.unknown_result(operation)
    return wire.action_result(operation, outcome or {"ok": True},
                              status=status, disposition=disposition)


def make(rsa_key, *, operation="open", backend=None, read=None, actions=UNSET,
         discovery=UNSET, now=None):
    backend = backend or existing._FakeWorkspaceClient(envelope={
        "ok": True, "result": result(operation)})
    read = read or Grant()
    if actions is UNSET:
        actions = {name: Grant(name) for name in OPERATIONS}
    if discovery is UNSET:
        discovery = Grant("discover")
    config = WorkspaceAppConfig(
        authenticator=existing._authenticator(rsa_key),
        now=now or (lambda: existing.NOW), authorize_principal=read,
        authorize_discovery=discovery, authorize_actions=actions, client=backend,
    )
    return TestClient(create_workspace_app(config)), backend, config


def headers(rsa_key):
    return {"Authorization": "Bearer " + existing._workspace_token(rsa_key),
            "Content-Type": "application/json"}


def send(client, rsa_key, operation="open", **kwargs):
    if "content" not in kwargs and "json" not in kwargs:
        kwargs["json"] = payload(operation)
    return client.post("/workspace/control-room/" + operation,
                       headers=headers(rsa_key), **kwargs)


@pytest.mark.parametrize("operation", OPERATIONS)
def test_action_is_a_fixed_default_denied_route_on_existing_read_app(rsa_key, operation):
    client, backend = existing._make_app(rsa_key, authorize=Grant())
    response = send(client, rsa_key, operation)
    assert response.status_code == 403
    assert response.json()["disposition"] == "NOT_DISPATCHED"
    assert backend.calls == []


@pytest.mark.parametrize("operation", OPERATIONS)
def test_signed_selected_action_has_one_host_derived_closed_frame(rsa_key, operation):
    client, backend, _ = make(rsa_key, operation=operation)
    response = send(client, rsa_key, operation)
    assert response.status_code == 200
    assert response.json() == result(operation)
    assert response.headers["Cache-Control"] == "no-store"
    assert len(backend.calls) == 1
    frame = wire.validate_frame(backend.calls[0])
    assert frame["operation"] == operation and frame["payload"] == payload(operation)
    assert frame["admission_expires_at"] == existing.NOW + 300
    assert frame["principal"]["scopes"] == [existing.SCOPE]
    assert "token" not in json.dumps(frame).lower()


@pytest.mark.parametrize("case", ["missing", "read_only", "selected_revoked",
                                  "read_revoked", "unstamped", "grant_exception"])
def test_authentication_and_two_permissions_precede_client(rsa_key, case):
    read, actions = Grant(), {name: Grant(name) for name in OPERATIONS}
    if case == "read_only":
        actions = None
    elif case == "selected_revoked":
        actions["open"].active = False
    elif case == "read_revoked":
        read.active = False
    elif case == "unstamped":
        actions["open"] = lambda _principal: True
    elif case == "grant_exception":
        def broken(_principal):
            raise OSError("private fixture path must not leak")
        actions["open"] = broken
    client, backend, _ = make(rsa_key, read=read, actions=actions)
    if case == "missing":
        response = client.post("/workspace/control-room/open", json=payload("open"))
    else:
        response = send(client, rsa_key)
    assert response.status_code in {401, 403}
    assert backend.calls == []
    assert "private fixture" not in response.text


@pytest.mark.parametrize("raw", [
    b'{"binding_id":"a","binding_id":"b"}',
    b'{"binding_id":"a","owed_context":{"x":1,"x":2}}',
    b'{"binding_id":"a","owed_context":NaN}',
    b'{"binding_id":"a","owed_context":"\\ud800"}',
    b'{"binding_id":"a","operation":"unbind"}',
    b'{"binding_id":"a","principal":{}}',
    b'{"binding_id":"a","admission_expires_at":9999999999}',
    b'{"binding_id":"a","before_effect":"callback"}',
    b'{"binding_id":"a"}\xff',
    b'[]', b'', b' ' * (wire.MAX_REQUEST_BYTES + 1) + b'{}',
])
def test_original_bounded_body_is_strict_before_dispatch(rsa_key, raw):
    client, backend, _ = make(rsa_key)
    response = send(client, rsa_key, content=raw)
    assert response.status_code == 400
    assert response.json()["disposition"] == "NOT_DISPATCHED"
    assert backend.calls == []


def test_whole_private_frame_budget_includes_server_principal_and_expiry(rsa_key):
    body = {"binding_id": "x" * (wire.MAX_REQUEST_BYTES - 40)}
    assert len(json.dumps(body).encode()) < wire.MAX_REQUEST_BYTES
    client, backend, _ = make(rsa_key)
    response = send(client, rsa_key, json=body)
    assert response.status_code == 400 and backend.calls == []


@pytest.mark.parametrize("case", ["query", "get", "head", "slash", "encoded",
                                  "content_type", "duplicate_content_type"])
def test_action_http_fences_refuse_before_dispatch(rsa_key, case):
    client, backend, _ = make(rsa_key)
    path, method, hdrs = "/workspace/control-room/open", "POST", headers(rsa_key)
    if case == "query":
        path += "?action=open"
    elif case in {"get", "head"}:
        method = case.upper()
    elif case == "slash":
        path += "/"
    elif case == "encoded":
        path = "/workspace/control-room%2Fopen"
    elif case == "content_type":
        hdrs["Content-Type"] = "text/plain"
    else:
        hdrs = list(hdrs.items()) + [("Content-Type", "application/json")]
    response = client.request(method, path, headers=hdrs,
                              content=json.dumps(payload("open")), follow_redirects=False)
    assert response.status_code in {400, 404, 405}
    if case in {"get", "head"}:
        assert response.headers["Allow"] == "POST"
    assert backend.calls == []


@pytest.mark.parametrize("change", ["expiry", "read_stamp", "action_stamp",
                                     "action_revoked", "client", "request", "callback"])
def test_stream_time_changes_are_rechecked_before_client(rsa_key, change):
    now, read, action = [existing.NOW], Grant(), Grant("open")
    actions = {name: Grant(name) for name in OPERATIONS}
    actions["open"] = action
    client, backend, config = make(rsa_key, read=read, actions=actions, now=lambda: now[0])
    replacement = existing._FakeWorkspaceClient()

    async def body():
        yield b'{"binding_id":'
        if change == "expiry":
            now[0] = existing.NOW + 300
        elif change == "read_stamp":
            read.generation += 1
        elif change == "action_stamp":
            action.generation += 1
        elif change == "action_revoked":
            action.active = False
        elif change == "client":
            object.__setattr__(config, "client", replacement)
        elif change == "request":
            backend.request = replacement.request
        else:
            object.__setattr__(config, "authorize_principal", Grant("replacement"))
        yield b'"BIND-fixture"}'

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app),
                                     base_url="https://fixture.test") as session:
            return await session.post("/workspace/control-room/open", headers=headers(rsa_key),
                                      content=body())
    response = asyncio.run(run())
    assert response.status_code in {403, 503}
    assert response.json()["disposition"] == "NOT_DISPATCHED"
    assert backend.calls == replacement.calls == []


@pytest.mark.parametrize("change", ["expiry", "read_revoked", "action_revoked"])
def test_complete_owner_result_survives_post_dispatch_admission_change(rsa_key, change):
    now, read, action = [existing.NOW], Grant(), Grant("open")
    actions = {name: Grant(name) for name in OPERATIONS}
    actions["open"] = action
    outcome = {"ok": True, "detail": "opened", "verification_update": "unconfirmed"}
    expected = result("open", outcome=outcome)
    def during(_frame):
        if change == "expiry":
            now[0] = existing.NOW + 1000
        elif change == "read_revoked":
            read.active = False
        else:
            action.active = False
    backend = existing._FakeWorkspaceClient(envelope={"ok": True, "result": expected},
                                           on_call=during)
    client, _, _ = make(rsa_key, backend=backend, read=read, actions=actions, now=lambda: now[0])
    response = send(client, rsa_key)
    assert response.status_code == 200 and response.json() == expected
    assert len(backend.calls) == 1


@pytest.mark.parametrize("disposition,status,outcome", [
    ("NOT_DISPATCHED", 409, {"ok": False, "failure_kind": "owed_source_changed"}),
    ("NOT_DISPATCHED", 403, {"ok": False, "failure_kind": "access_denied"}),
    ("OWNER_RETURNED", 200, {"ok": False, "failure_kind": "effect_unknown"}),
    ("OWNER_RETURNED", 200, {"ok": False, "detail": "publication failed"}),
    ("EFFECT_UNKNOWN", 503, None),
])
def test_public_action_result_preserves_owner_disposition_and_status(
        rsa_key, disposition, status, outcome):
    expected = result("open", disposition=disposition, status=status, outcome=outcome)
    backend = existing._FakeWorkspaceClient(envelope={"ok": True, "result": expected})
    client, _, _ = make(rsa_key, backend=backend)
    response = send(client, rsa_key)
    assert response.status_code == status
    assert response.json() == expected
    assert len(backend.calls) == 1


@pytest.mark.parametrize("case", ["raise", "cancel", "wrong_operation", "extra",
                                  "bare_error", "oversized"])
def test_unknown_after_client_invocation_never_becomes_zero_effect_or_retry(rsa_key, case):
    envelope, error = {"ok": True, "result": result("open")}, None
    if case == "raise":
        error = OSError("secret fixture detail")
    elif case == "cancel":
        error = asyncio.CancelledError()
    elif case == "wrong_operation":
        envelope["result"] = result("unbind")
    elif case == "extra":
        envelope["unexpected"] = True
    elif case == "bare_error":
        envelope = {"ok": False, "status": 503, "error": {"code": "internal_error"}}
    else:
        envelope["result"]["outcome"]["text"] = "x" * wire.MAX_RESPONSE_BYTES
    backend = existing._FakeWorkspaceClient(envelope=envelope, raise_on_call=error)
    client, _, _ = make(rsa_key, backend=backend)
    response = send(client, rsa_key)
    assert response.status_code == 503
    assert response.json() == wire.unknown_result("open")
    assert len(backend.calls) == 1
    assert "secret fixture" not in response.text


def test_repeated_http_cancellation_retains_the_single_original_client(rsa_key):
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        class Client:
            calls = 0
            async def request(self, frame):
                self.calls += 1
                entered.set()
                await release.wait()
                return {"ok": True, "result": result("open")}
        backend = Client()
        client, _, _ = make(rsa_key, backend=backend)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app),
                                     base_url="https://fixture.test") as session:
            task = asyncio.create_task(session.post(
                "/workspace/control-room/open", headers=headers(rsa_key), json=payload("open")))
            await asyncio.wait_for(entered.wait(), 1)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done() and backend.calls == 1
            release.set()
            response = await asyncio.wait_for(task, 1)
            assert response.json() == result("open")
            assert backend.calls == 1
    asyncio.run(run())


@pytest.mark.parametrize("case", ["absent", "revoked", "changed_stamp", "late_expiry"])
def test_discovery_requires_its_own_current_grant_until_read_release(rsa_key, case):
    now, discovery = [existing.NOW], Grant("discover")
    expected = {"candidates": ["fixture"]}
    def during(_frame):
        if case == "revoked":
            discovery.active = False
        elif case == "changed_stamp":
            discovery.generation += 1
    backend = existing._FakeWorkspaceClient(envelope={"ok": True, "result": expected},
                                           on_call=during)
    if case == "late_expiry":
        count = [0]
        class SlowGrant(Grant):
            def __call__(self, principal):
                count[0] += 1
                if count[0] >= 3:
                    now[0] = existing.NOW + 300
                return super().__call__(principal)
        discovery = SlowGrant("discover")
    client, _, _ = make(rsa_key, backend=backend,
                       discovery=None if case == "absent" else discovery, now=lambda: now[0])
    response = client.get("/workspace/control-room/discover/current", headers=headers(rsa_key))
    assert response.status_code == 403 and "candidates" not in response.text
    assert len(backend.calls) == (0 if case == "absent" else 1)


def test_discovery_selected_grant_and_state_membership_remain_distinct(rsa_key):
    client, backend, _ = make(rsa_key, discovery=Grant("discover"))
    assert client.get("/workspace/control-room/discover/current", headers=headers(rsa_key)).status_code == 200
    assert backend.calls[0]["operation"] == "discover"
    client, backend, _ = make(rsa_key, discovery=None, actions=None)
    assert client.get("/workspace/control-room/state/current", headers=headers(rsa_key)).status_code == 200
    assert backend.calls[0]["operation"] == "state"


@pytest.mark.parametrize("value", [{}, {"open": lambda _p: True},
                                   {name: None for name in OPERATIONS}])
def test_partial_or_non_callable_action_configuration_is_refused(rsa_key, value):
    with pytest.raises(ValueError):
        make(rsa_key, actions=value)


def test_caller_mapping_mutation_cannot_replace_selected_action(rsa_key):
    actions = {name: Grant(name) for name in OPERATIONS}
    client, backend, config = make(rsa_key, actions=actions)
    actions["open"] = lambda _p: False
    with pytest.raises(TypeError):
        config.authorize_actions["open"] = lambda _p: False
    assert send(client, rsa_key).status_code == 200
    assert len(backend.calls) == 1


def test_final_action_permission_can_expire_before_client_admission(rsa_key):
    now, calls = [existing.NOW], [0]
    class SlowGrant(Grant):
        def __call__(self, principal):
            calls[0] += 1
            if calls[0] >= 3:
                now[0] = existing.NOW + 300
            return super().__call__(principal)
    actions = {name: Grant(name) for name in OPERATIONS}
    actions["open"] = SlowGrant("open")
    client, backend, _ = make(rsa_key, actions=actions, now=lambda: now[0])
    response = send(client, rsa_key)
    assert response.status_code == 403
    assert response.json()["disposition"] == "NOT_DISPATCHED"
    assert backend.calls == []


@pytest.mark.parametrize("grant_available", [False, True])
def test_stream_stops_before_unauthorized_body_or_over_budget_remainder(rsa_key, grant_available):
    client, backend, _ = make(rsa_key, actions=UNSET if grant_available else None)
    consumed = []
    async def body():
        consumed.append("first")
        yield b" " * (wire.MAX_REQUEST_BYTES + 1)
        consumed.append("remainder")
        yield b"{}"
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app),
                                     base_url="https://fixture.test") as session:
            return await session.post("/workspace/control-room/open", headers=headers(rsa_key),
                                      content=body())
    response = asyncio.run(run())
    assert response.status_code == (400 if grant_available else 403)
    assert consumed == (["first"] if grant_available else [])
    assert backend.calls == []
