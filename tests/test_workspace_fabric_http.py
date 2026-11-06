"""Signed browser GET framing and actual private App-peer dispatch."""
import asyncio
import copy
import dataclasses
import json

import pytest

from common import executive_workspace_fabric_contract as wire
from common import executive_workspace_contract as workspace
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from tests.test_workspace_read_app import _make_app, _workspace_token, _FakeWorkspaceClient, rsa_key, NOW
from tests.test_workspace_fabric_read import status, owner, paid, selection
from tests.test_workspace_read_socket import control, short_socket_root

CATALOG = "/workspace/fabric/catalog/current"
STATUS = "/workspace/fabric/status/current"
SELECTED = {"root_id": "JOB-1", "run_id": "ATT-" + "a" * 32}


def permissions():
    values = [True, "f" * 64]
    def authorize(principal):
        return values[0]
    authorize.binding_digest = lambda principal: values[1]
    return authorize, values


def catalog():
    return {"schema": wire.CATALOG_SCHEMA, "availability": "PARTIAL",
        "observed_at": "2026-11-03T00:00:00Z",
        "source": {"owner": "ATTENDED_FABRIC", "observation_kind": "CONTROLLER_STATUS_SNAPSHOT",
            "revision": "a" * 64, "scope": "EXACT_RUN_SET", "atomic": False, "time_basis": "LOCAL_READ"},
        "coverage": {"returned_count": 1, "candidate_count": None, "omitted_count": None,
            "scan_complete": False, "status_complete": True},
        "items": [{"run_id": SELECTED["run_id"], "controller_modified_at": None,
            "status": status(SELECTED["run_id"], SELECTED["root_id"]), "reason_code": None}],
        "reason_codes": ["ROWS_OMITTED"]}


@pytest.mark.parametrize("route,operation,params", [(CATALOG, wire.CATALOG_OPERATION, None), (STATUS, wire.STATUS_OPERATION, SELECTED)])
def test_signed_fixed_get_returns_only_bounded_metadata(rsa_key, route, operation, params):
    authorize, _ = permissions()
    result = catalog() if params is None else status(**{"run": params["run_id"], "root": params["root_id"]})
    if params is not None:
        result.update(result="PRIVATE", session_home_reference={"home_path": "/private"})
    app, calls = _make_app(rsa_key, authorize=authorize, client=_FakeWorkspaceClient(envelope={"ok": True, "result": result}))
    response = app.get(route, params=params, headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert "PRIVATE" not in response.text and "/private" not in response.text
    sent = calls.calls[0]
    assert sent["schema"] == wire.FRAME_SCHEMA and sent["operation"] == operation
    assert sent["selection"] == params
    assert sent["principal"]["resource"] == workspace.RESOURCE
    wire.validate_frame(sent)


@pytest.mark.parametrize("route", [CATALOG, STATUS])
@pytest.mark.parametrize("case", ["anonymous", "bad_token", "disabled", "no_witness"])
def test_authentication_and_live_membership_refuse_before_private_read(rsa_key, route, case):
    authorize, values = permissions()
    headers = {"Authorization": "Bearer " + _workspace_token(rsa_key)}
    if case == "anonymous": headers = {}
    elif case == "bad_token": headers["Authorization"] = "Bearer malformed"
    elif case == "disabled": values[0] = False
    else: values[1] = None
    app, calls = _make_app(rsa_key, authorize=authorize)
    response = app.get(route, params=SELECTED if route == STATUS else None, headers=headers)
    assert response.status_code in (401, 403)
    assert calls.calls == []


@pytest.mark.parametrize("route,query", [
    (CATALOG, "root_id=JOB-1"), (CATALOG, "root=/private"), (STATUS, ""),
    (STATUS, "root_id=JOB-1"), (STATUS, "root_id=JOB-1&run_id=../private"),
    (STATUS, "root_id=JOB-1&run_id=ATT-" + "a" * 32 + "&root_id=JOB-2"),
    (STATUS, "root_id=JOB-1&run_id=ATT-" + "a" * 32 + "&source=M2"),
])
def test_no_arbitrary_selector_root_source_or_duplicate_query(rsa_key, route, query):
    authorize, _ = permissions()
    app, calls = _make_app(rsa_key, authorize=authorize)
    response = app.get(route + ("?" + query if query else ""), headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 400
    assert calls.calls == []


@pytest.mark.parametrize("route", [CATALOG, STATUS])
@pytest.mark.parametrize("method", ["POST", "HEAD", "PUT", "DELETE"])
def test_fixed_read_routes_never_accept_mutating_or_head_alias(rsa_key, route, method):
    app, calls = _make_app(rsa_key)
    response = app.request(method, route)
    assert response.status_code == 405
    assert calls.calls == []


@pytest.mark.parametrize("case", ["revoked", "permission_rotation", "expired"])
def test_release_rechecks_hide_successful_late_response(rsa_key, case):
    authorize, values = permissions()
    clock = [NOW]
    def after(frame):
        if case == "revoked": values[0] = False
        elif case == "permission_rotation": values[1] = "e" * 64
        else: clock[0] = NOW + 301
    app, calls = _make_app(rsa_key, authorize=authorize, now=lambda: clock[0],
        client=_FakeWorkspaceClient(envelope={"ok": True, "result": catalog()}, on_call=after))
    response = app.get(CATALOG, headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 403 and len(calls.calls) == 1
    assert "items" not in response.text


@pytest.mark.parametrize("case", ["wrong_run", "wrong_root", "fabricated_acceptance", "unknown_state", "oversized", "catalog_raw"])
def test_invalid_or_raw_metadata_is_closed_at_http(rsa_key, case):
    authorize, _ = permissions()
    value = status(SELECTED["run_id"], SELECTED["root_id"])
    route, params = STATUS, SELECTED
    if case == "wrong_run": value["run_id"] = "another-run"
    elif case == "wrong_root": value["root_id"] = "other-root"
    elif case == "fabricated_acceptance": value.update(accepted=True, acceptance_state="ACCEPTED")
    elif case == "unknown_state": value["state"] = "SUCCESS_WITHOUT_PROOF"
    elif case == "oversized": value["acceptance_reason"] = "x" * 20_000
    else:
        value, route, params = catalog(), CATALOG, None
        value["items"][0]["status"]["result"] = "PRIVATE"
    app, _ = _make_app(rsa_key, authorize=authorize, client=_FakeWorkspaceClient(envelope={"ok": True, "result": value}))
    response = app.get(route, params=params, headers={"Authorization": "Bearer " + _workspace_token(rsa_key)})
    assert response.status_code == 503
    assert "PRIVATE" not in response.text


@pytest.mark.parametrize("case", ["allowed", "not_armed", "no_paid_owner", "late_owner_change", "foreign_peer"])
def test_actual_app_peer_service_dispatches_only_original_coo_and_paid_source(owner, tmp_path, short_socket_root, case):
    import os
    from control_plane.coo_principal_host import CooHostProvider
    async def execute():
        def factory(runtime):
            return owner["service"]
        app_uid = os.geteuid() + 2000 if case == "foreign_peer" else None
        svc = control(tmp_path / "service", short_socket_root, factory, app_uid=app_uid)
        await svc.start()
        try:
            svc._ceo_ingress_app_binding = dataclasses.replace(svc._ceo_ingress_app_binding,
                principal_facts_factory=lambda runtime: CooHostProvider(owner["coo"].source, factory(runtime)),
                principal_admission_armed=case != "not_armed", principal_admission_guard=lambda envelope: None)
            svc._paid_worker_binding_source = None if case == "no_paid_owner" else owner["source"]
            if case == "late_owner_change":
                owner["effects"].append(lambda: setattr(svc, "_ceo_ingress_app_binding",
                    dataclasses.replace(svc._ceo_ingress_app_binding)))
            client = CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path)
            if case == "foreign_peer":
                with pytest.raises(ValueError):
                    await client.request(owner["request"])
                assert owner["calls"] == []
                return
            response = await client.request(owner["request"])
            if case == "allowed":
                assert response["ok"] is True, response
                wire.validate_catalog(response["result"])
                assert len(owner["calls"]) == 1
            else:
                assert response == workspace.error("access_denied", 403), response
                assert len(owner["calls"]) == (1 if case == "late_owner_change" else 0)
        finally:
            # This is a disposable test-only source injection, not service
            # startup qualification or a test of the installed host lifecycle.
            svc._paid_worker_binding_source = None
            await svc.close()
    asyncio.run(execute())
