"""Fixed authenticated metadata read, including the actual HTTP/Unix path."""
import asyncio
import copy
import dataclasses

import httpx
import pytest

from common import workspace_byok_read_contract as wire
from control_plane.workspace_read_service import WorkspaceReadService
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.executive_mcp.server import AuditedWorkspaceApp, _mounted_lifespan, build_executive_mcp_app
from integrations.mastermind_executive_app.app import AppSettings
from integrations.mastermind_executive_app.gateway import AppPolicies
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from integrations.mastermind_workspace_app.contract import BINDINGS_SCHEMA, principal_frame, workspace_authorizers
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from tests.test_mastermind_executive_app_asgi import _FakeJwksCache, _read_policy, _submit_policy
from tests.test_workspace_read_app import (
    NOW, _authenticator, _workspace_token, rsa_key, _make_app, _FakeWorkspaceClient,
)
from tests.test_workspace_read_service import frame as incumbent_frame
from tests.test_workspace_read_socket import control, short_socket_root

ROUTE = "/workspace/byok/roles/current"


def observed():
    return {"schema": wire.BODY_SCHEMA, "state": "OBSERVED", "reason_code": "OBSERVED",
            "roles": [
                {"role": "mmmeta", "state": "CONFIGURATION_OBSERVED",
                 "requested_provider": "zai", "requested_model": "glm-5.3"},
                {"role": "mmsecretary", "state": "ABSENT",
                 "requested_provider": None, "requested_model": None}],
            "source_observation": {"host_binding_sha256": "a" * 64,
                "host_boot_id": "01234567-0123-4567-89ab-0123456789ab",
                "implementation_sha": "b" * 40, "metadata_sha256": "c" * 64,
                "observed_at_ms": NOW * 1000}, "proof": wire.proof()}


def frame():
    return {"schema": wire.FRAME_SCHEMA, "operation": wire.OPERATION,
            "principal": incumbent_frame()["principal"]}


class Permit:
    allowed = True
    stamp = "d" * 64
    def __call__(self, _): return self.allowed
    def binding_digest(self, _): return self.stamp


class NoSourceWork:
    def __getattr__(self, _): pytest.fail("unrelated Runtime/cache acquisition")


def provider(reader=None, permit=None):
    return WorkspaceReadService(cache=NoSourceWork(), runtime=NoSourceWork(),
        authorize=permit or Permit(), armed={}, runtime_identity={}, byok_roles_reader=reader)


def test_unbound_is_not_role_absence_and_performs_no_source_work():
    result = asyncio.run(provider().handle_frame(frame()))
    assert result == {"ok": True, "result": wire.unavailable("SOURCE_UNBOUND")}


@pytest.mark.parametrize("defect", ["extra", "role_swap", "duplicate_role", "connected",
    "proof_true", "proof_integer", "private_path", "absent_model", "stale", "future", "oversized", "crash"])
def test_closed_metadata_and_original_timestamp_fail_without_partial_disclosure(defect, monkeypatch):
    monkeypatch.setattr("control_plane.workspace_read_service.time.time", lambda: NOW)
    body = observed()
    if defect == "extra": body["raw_secret"] = "must-not-escape"
    elif defect == "role_swap": body["roles"].reverse()
    elif defect == "duplicate_role": body["roles"][1]["role"] = "mmmeta"
    elif defect == "connected": body["roles"][0]["state"] = "CONNECTED"
    elif defect == "proof_true": body["proof"]["provider_called"] = True
    elif defect == "proof_integer": body["proof"]["credentials_read"] = 0
    elif defect == "private_path": body["source_observation"]["path"] = "/private/role"
    elif defect == "absent_model": body["roles"][1]["requested_model"] = "candidate"
    elif defect == "stale": body["source_observation"]["observed_at_ms"] -= 30_001
    elif defect == "future": body["source_observation"]["observed_at_ms"] += 5_001
    elif defect == "oversized": body["roles"][0]["requested_model"] = "x" * 9000
    calls = []
    async def read():
        calls.append(True)
        if defect == "crash": raise RuntimeError("must-not-escape")
        return body
    result = asyncio.run(provider(read).handle_frame(frame()))
    assert result == {"ok": True, "result": wire.unavailable(
        "SOURCE_STALE" if defect in {"stale", "future"} else "SOURCE_UNAVAILABLE")}
    assert calls == [True]
    assert "must-not-escape" not in repr(result)


@pytest.mark.parametrize("change", ["permission", "stamp", "authorizer", "reader", "runtime"])
def test_changed_permission_or_source_discards_one_original_read(change, monkeypatch):
    monkeypatch.setattr("control_plane.workspace_read_service.time.time", lambda: NOW)
    permit = Permit()
    async def read():
        if change == "permission": permit.allowed = False
        elif change == "stamp": permit.stamp = "e" * 64
        elif change == "authorizer": owner.authorize = Permit()
        elif change == "reader": owner._byok_roles_reader = lambda: None
        elif change == "runtime": owner.runtime = object()
        return observed()
    owner = provider(read, permit)
    result = asyncio.run(owner.handle_frame(frame()))
    if change in {"reader", "runtime"}:
        assert result == {"ok": True, "result": wire.unavailable("SOURCE_CHANGED")}
    else:
        assert result["ok"] is False and result["status"] == 403


def test_unstamped_authorizer_cannot_read():
    owner = provider()
    owner.authorize = lambda _: True
    assert asyncio.run(owner.handle_frame(frame()))["status"] == 403


def test_synchronous_source_is_refused_without_invocation():
    def read(): pytest.fail("synchronous source invoked")
    with pytest.raises(ValueError, match="asynchronous"):
        provider(read)


def test_replaced_synchronous_source_is_not_invoked():
    owner = provider()
    def read(): pytest.fail("replacement synchronous source invoked")
    owner._byok_roles_reader = read
    assert asyncio.run(owner.handle_frame(frame())) == {"ok": True, "result": wire.unavailable()}


def test_valid_pair_is_called_once_and_detached(monkeypatch):
    monkeypatch.setattr("control_plane.workspace_read_service.time.time", lambda: NOW)
    original = observed(); calls = []
    async def read(): calls.append(True); return original
    result = asyncio.run(provider(read).handle_frame(frame()))
    assert calls == [True] and result["result"] == original
    original["roles"][0]["requested_model"] = "changed"
    assert result["result"]["roles"][0]["requested_model"] == "glm-5.3"


@pytest.mark.parametrize("defect", ["extra", "selection", "scope", "operation"])
def test_closed_frame_refuses_before_source(defect):
    request = frame()
    if defect == "extra": request["host"] = "ubuntu1"
    elif defect == "selection": request["selection"] = {"role": "mmmeta"}
    elif defect == "scope": request["principal"]["scopes"] = ["mastermind.executive.submit"]
    else: request["operation"] = "enroll"
    async def read(): pytest.fail("source reached")
    assert asyncio.run(provider(read).handle_frame(request))["status"] == 400


@pytest.mark.parametrize("method,suffix,body,expected", [
    ("GET", "?host=ubuntu1", None, 400), ("GET", "", b"{}", 400),
    ("POST", "", None, 405), ("HEAD", "", None, 405),
])
def test_http_input_refusals_precede_client(rsa_key, method, suffix, body, expected):
    app, client = _make_app(rsa_key, authorize=Permit())
    with app:
        result = app.request(method, ROUTE + suffix, content=body,
            headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert result.status_code == expected and not client.calls


def test_http_rechecks_permission_and_expiry(rsa_key):
    permit = Permit()
    client = _FakeWorkspaceClient(envelope={"ok": True, "result": observed()},
        on_call=lambda _: setattr(permit, "allowed", False))
    app, client = _make_app(rsa_key, client=client, authorize=permit)
    with app:
        result = app.get(ROUTE, headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert result.status_code == 403 and len(client.calls) == 1


@pytest.mark.parametrize("defect", [None, "binding", "factory", "runtime", "principal", "factory_retired"])
def test_signed_mounted_http_to_original_control_socket(tmp_path, short_socket_root, rsa_key, monkeypatch, defect):
    monkeypatch.setattr("control_plane.workspace_read_service.time.time", lambda: NOW)
    async def run():
        auth = _authenticator(rsa_key); token = _workspace_token(rsa_key)
        principal = await auth.verify_authorization_header("Bearer " + token, now=NOW)
        slots = {"schema": BINDINGS_SCHEMA, "profiles": {
            "web": {"enabled": True, "binding": dict(principal_frame(principal), permission_digest="a" * 64)},
            "mac": {"enabled": False, "binding": None}}}
        app_auth, control_auth = workspace_authorizers(policy=auth.policy, load_bindings=lambda: slots)
        calls = []
        async def read():
            calls.append(True)
            if defect == "binding":
                svc._ceo_ingress_app_binding = dataclasses.replace(original_binding)
            elif defect == "factory":
                object.__setattr__(original_binding, "workspace_read_provider_factory", lambda _: None)
            elif defect == "runtime": svc.runtime = object()
            elif defect == "principal": slots["profiles"]["web"]["enabled"] = False
            return observed()
        def factory(actual):
            value = WorkspaceReadService(cache=NoSourceWork(), runtime=actual, authorize=control_auth,
                armed={}, runtime_identity={}, byok_roles_reader=read)
            if defect == "factory_retired":
                object.__setattr__(original_binding, "workspace_read_provider_factory", lambda _: None)
            return value
        svc = control(tmp_path, short_socket_root, factory)
        await svc.start()
        original_binding, original_runtime = svc._ceo_ingress_app_binding, svc.runtime
        client = CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path)
        workspace = create_workspace_app(WorkspaceAppConfig(authenticator=auth, now=lambda: NOW,
            authorize_principal=app_auth, client=client))
        class Sink:
            def emit(self, _): pass
        sink = Sink()
        verifier = MastermindTokenVerifier(authenticator=auth, policy=auth.policy, now=lambda: NOW, audit_sink=sink)
        mounted = build_executive_mcp_app(AppSettings(
            policies=AppPolicies(read=_read_policy(), submit=_submit_policy()),
            mastermind_root=tmp_path, macro_root_flag=None, environ={},
            ceo_ingress_socket_path=svc.ceo_ingress_socket_path,
            read_from_ceo_ingress=True, jwks_cache=_FakeJwksCache(rsa_key), clock=lambda: NOW),
            audit_sink=sink, workspace_app=AuditedWorkspaceApp(workspace, verifier))
        try:
            async with _mounted_lifespan(mounted):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mounted),
                        base_url="https://mcp.mastermind-x.com") as http:
                    result = await http.get(ROUTE, headers={"Authorization": "Bearer " + token})
                    assert result.headers["cache-control"] == "no-store"
                    if defect is None: assert result.status_code == 200 and result.json() == observed()
                    else: assert result.status_code == (403 if defect == "principal" else 503)
                    assert calls == ([] if defect == "factory_retired" else [True])
        finally:
            svc.runtime = original_runtime
            svc._ceo_ingress_app_binding = original_binding
            object.__setattr__(original_binding, "workspace_read_provider_factory", factory)
            await svc.close()
    asyncio.run(run())


def test_non_app_peer_cannot_observe_roles(tmp_path, short_socket_root):
    import os
    async def run():
        def factory(_): pytest.fail("non-App source call")
        svc = control(tmp_path, short_socket_root, factory, app_uid=os.geteuid() + 2000)
        await svc.start()
        try:
            with pytest.raises(ValueError):
                await CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path).request(frame())
        finally: await svc.close()
    asyncio.run(run())
