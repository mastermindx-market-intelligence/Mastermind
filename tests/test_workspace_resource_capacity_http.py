"""Signed fixed HTTP boundary and original selected-work source; no live account."""
import asyncio
import copy
import pytest
from common import workspace_resource_capacity_contract as wire
from integrations.mastermind_workspace_app.app import _capacity_envelope_response
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from tests.test_workspace_resource_capacity_read import owner, run
from tests.test_workspace_read_app import _make_app, _workspace_token, _FakeWorkspaceClient, rsa_key

ROUTE = "/workspace/resources/capacity/current"


def test_signed_fixed_http_route_keeps_allowlisted_retained_body_and_no_store(owner, rsa_key):
    envelope = run(owner)
    app, client = _make_app(rsa_key, client=_FakeWorkspaceClient(envelope=envelope))
    response = app.get(ROUTE, params=owner["selected"], headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 200, response.text
    assert response.json() == envelope["result"]
    assert response.headers["cache-control"] == "no-store"
    assert len(client.calls) == 1
    assert client.calls[0]["schema"] == wire.FRAME_SCHEMA
    assert client.calls[0]["operation"] == wire.OPERATION
    assert client.calls[0]["selection"] == owner["selected"]


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer garbled"}])
def test_unsigned_or_malformed_authorization_never_calls_source(owner, rsa_key, headers):
    app, client = _make_app(rsa_key, client=_FakeWorkspaceClient(envelope=run(owner)))
    assert app.get(ROUTE, params=owner["selected"], headers=headers).status_code in (401, 403)
    assert client.calls == []


@pytest.mark.parametrize("extra", [{"host_ref": "host-" + "a" * 64}, {"clock": "now"}, {"attempt_id": "../private"}])
def test_http_does_not_accept_host_clock_or_path_selectors(owner, rsa_key, extra):
    app, client = _make_app(rsa_key, client=_FakeWorkspaceClient(envelope=run(owner)))
    response = app.get(ROUTE, params={**owner["selected"], **extra}, headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 400
    assert client.calls == []


@pytest.mark.parametrize("mutation", ["account", "eligibility", "receipt", "oversize"])
def test_edge_rejects_unreviewed_fields_new_grants_or_false_receipts(owner, mutation):
    envelope = copy.deepcopy(run(owner))
    body = envelope["result"]
    if mutation == "account": body["provider_capacity"]["account"] = "PRIVATE-SECRET"
    elif mutation == "eligibility": body["provider_capacity"]["can_place_work"] = True
    elif mutation == "receipt": body["source_observation"]["runtime"]["after"] += 1
    else: body["provider_capacity"]["quota_horizons"] = ["PRIVATE-SECRET" * 2000]
    response = _capacity_envelope_response(envelope)
    assert response.status_code == 503
    assert b"PRIVATE-SECRET" not in response.body


@pytest.mark.parametrize("method,path", [("POST", ROUTE), ("HEAD", ROUTE), ("GET", "/workspace/resources/%63apacity/current")])
def test_aliases_and_non_get_methods_are_fenced_before_auth_or_source(owner, rsa_key, method, path):
    app, client = _make_app(rsa_key, client=_FakeWorkspaceClient(envelope=run(owner)))
    response = app.request(method, path, params=owner["selected"])
    assert response.status_code in (400, 404, 405)
    assert client.calls == []


def test_wrong_capacity_frame_refuses_before_socket_open(owner, monkeypatch):
    called = []
    async def forbidden(*args, **kwargs):
        called.append(True)
        raise AssertionError("invalid frame opened socket")
    monkeypatch.setattr(asyncio, "open_unix_connection", forbidden)
    frame = {**owner["request"], "selection": {**owner["selected"], "host_ref": "supplied"}}
    with pytest.raises(ValueError):
        asyncio.run(CeoIngressWorkspaceClient("/not-opened.sock").request(frame))
    assert called == []


@pytest.mark.parametrize("case", ["available", "coo_revoked", "workspace_revoked", "wrong_attempt"])
def test_actual_signed_http_socket_original_coo_and_runtime_chain(owner, tmp_path, monkeypatch, rsa_key, short_socket_root, case):
    from dataclasses import replace
    from integrations.mastermind_workspace_app.contract import principal_frame
    from integrations.mastermind_executive_app.coo_binding import _digest
    from tests import test_workspace_admitted_plan_read as transport_suite
    from tests.test_workspace_read_app import _authenticator, NOW
    from control_plane.coo_principal_host import CooHostProvider
    from control_plane.workspace_read_service import WorkspaceReadService
    from control_plane import workspace_resource_capacity_read as source
    auth = _authenticator(rsa_key)
    verified = asyncio.run(auth.verify_authorization_header("Bearer " + _workspace_token(rsa_key), now=NOW))
    viewer = principal_frame(verified)
    mutable = owner["mutable"]
    mutable["policy"]["issuer"] = auth.policy.issuer
    mutable["policy"]["authorization_servers"] = [auth.policy.issuer]
    mutable["policy"]["jwks_uri"] = auth.policy.issuer + "/.well-known/jwks.json"
    mutable["policy"]["allowed_subject_digests"] = [viewer["subject_digest"]]
    enrolled = mutable["binding"]["binding"]
    for field in ("issuer_digest", "subject_digest", "client_ref"): enrolled[field] = viewer[field]
    mutable["missions"][0]["principal_binding_digest"] = _digest(enrolled)
    def service(actual, authorize):
        assert actual is owner
        return WorkspaceReadService(cache=owner["cache"], runtime=owner["writer"], authorize=authorize,
            armed={}, runtime_identity={"db_present": True}, bounded_runtime=lambda actual: owner["reader"] if actual is owner["writer"] else pytest.fail("wrong Runtime"))
    monkeypatch.setattr(transport_suite, "service", service)
    original_control = transport_suite.control
    def control(path, socket_root, factory):
        result = original_control(path, socket_root, factory)
        result._ceo_ingress_app_binding = replace(result._ceo_ingress_app_binding,
            principal_facts_factory=lambda runtime: CooHostProvider(owner["coo"].source, factory(runtime)),
            principal_admission_armed=True, principal_admission_guard=lambda _: None)
        return result
    monkeypatch.setattr(transport_suite, "control", control)
    if case == "coo_revoked":
        original = source.read_capacity
        def revoke(*args):
            response = original(*args); mutable["missions"][0]["enabled"] = False
            return response
        monkeypatch.setattr(source, "read_capacity", revoke)
    def after_app(slots, _clock):
        slots["profiles"]["web"]["enabled"] = False
    async def exchange():
        async with transport_suite.transport(owner, rsa_key, tmp_path, short_socket_root,
            after_app=after_app if case == "workspace_revoked" else None) as (http, token, slots, seen, client, principal, mounted):
            selected = dict(owner["selected"])
            if case == "wrong_attempt": selected["attempt_id"] = "ATT-" + "9" * 32
            response = await http.get(ROUTE, params=selected, headers={"Authorization": "Bearer " + token})
            if case in {"coo_revoked", "workspace_revoked"}:
                assert response.status_code == 403, response.text
                assert "provider_capacity" not in response.text
            elif case == "wrong_attempt":
                assert response.json()["availability"] == "UNAVAILABLE", response.text
                assert response.json()["provider_capacity"] is None
            else:
                assert response.status_code == 200, response.text
                assert response.json()["availability"] == "AVAILABLE"
                assert response.json()["provider_capacity"]["observation_kind"] == "RETAINED_CLAIM"
                assert response.json()["provider_capacity"]["can_place_work"] is False
                assert response.json()["source_observation"]["state"] == "SAME"
                assert "no-store" in response.headers["cache-control"]
    asyncio.run(exchange())
