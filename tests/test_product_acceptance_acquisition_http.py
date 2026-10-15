"""Explicit acquisition mode; real JWT, hermetic installed-owner responses."""
import copy

import pytest

from common import product_acceptance_acquisition_contract as acquisition
from common import product_acceptance_read_contract as original
from tests.test_product_acceptance_app_read import body, selection, headers
from tests.test_workspace_read_app import _FakeWorkspaceClient, _make_app, rsa_key
from tests.test_workspace_read_service import frame

ROUTE = "/workspace/mission/v4/current"


def params():
    return {**{k: selection()[k] for k in ("work_ref", "root_job_id")},
            "read_mode": "original_owner"}


def test_explicit_acquisition_uses_distinct_two_key_frame(rsa_key):
    fake = _FakeWorkspaceClient(envelope={"ok": True, "result": body()})
    client, _ = _make_app(rsa_key, client=fake)
    response = client.get(ROUTE, params=params(), headers=headers(rsa_key))
    assert response.status_code == 200, response.text
    assert response.json() == body()
    assert response.headers["Cache-Control"] == "no-store"
    assert len(fake.calls) == 1
    sent = fake.calls[0]
    assert sent["operation"] == acquisition.OPERATION
    assert sent["selection"] == {k: selection()[k] for k in ("work_ref", "root_job_id")}
    acquisition.validate_frame(sent)
    with pytest.raises(ValueError): original.validate_frame(sent)


@pytest.mark.parametrize("defect", ["no_mode_no_key", "unknown_mode", "duplicate_mode", "mixed_key",
    "obligation", "encoded_mode_key", "encoded_work_key", "empty_mode", "extra_key", "duplicate_work"])
def test_invalid_or_ambiguous_mode_never_reaches_owner(rsa_key, defect):
    client, fake = _make_app(rsa_key)
    query = params()
    if defect == "no_mode_no_key": del query["read_mode"]
    if defect == "unknown_mode": query["read_mode"] = "newest"
    if defect == "empty_mode": query["read_mode"] = ""
    if defect == "mixed_key": query["request_message_key"] = selection()["request_message_key"]
    if defect == "obligation": query["obligation_id"] = "WAK-client-selected"
    if defect == "extra_key": query["authority"] = "accepted"
    if defect == "duplicate_mode": query = list(query.items()) + [("read_mode", "original_owner")]
    if defect == "duplicate_work": query = list(query.items()) + [("work_ref", query["work_ref"])]
    if defect in ("encoded_mode_key", "encoded_work_key"):
        key = "read_mode" if defect == "encoded_mode_key" else "work_ref"
        encoded = "read%5Fmode" if defect == "encoded_mode_key" else "work%5Fref"
        raw = "&".join((encoded if k == key else k) + "=" + v for k, v in query.items())
        response = client.get(ROUTE + "?" + raw, headers=headers(rsa_key))
    else:
        response = client.get(ROUTE, params=query, headers=headers(rsa_key))
    assert response.status_code == 400, response.text
    assert not fake.calls


def test_body_and_unauthenticated_acquisition_are_refused(rsa_key):
    client, fake = _make_app(rsa_key)
    assert client.get(ROUTE, params=params()).status_code == 401
    assert client.request("GET", ROUTE, params=params(), headers=headers(rsa_key), content=b"x").status_code == 400
    assert not fake.calls


@pytest.mark.parametrize("defect", ["work", "root", "missing_key", "malformed_key", "partial", "receipt_extra"])
def test_foreign_or_unqualified_owner_response_is_closed(rsa_key, defect):
    value = body()
    selected = value["product_acceptance"]["selection"]
    if defect == "work": selected["work_ref"] = "WS:FOREIGN"
    if defect == "root": selected["root_job_id"] = "JOB-999"
    if defect == "missing_key": del selected["request_message_key"]
    if defect == "malformed_key": selected["request_message_key"] = "guessed"
    if defect == "partial": value["mission"]["read_state"]["state"] = "PARTIAL"
    if defect == "receipt_extra": value["product_acceptance"]["receipt"]["private"] = "hidden"
    client, _ = _make_app(rsa_key, client=_FakeWorkspaceClient(envelope={"ok": True, "result": value}))
    response = client.get(ROUTE, params=params(), headers=headers(rsa_key))
    assert response.status_code == 503
    assert "qualified_ruling_digest" not in response.text


def test_permission_rotation_withholds_acquired_body(rsa_key):
    epoch = [0]
    authorize = lambda _: True
    authorize.binding_digest = lambda _: str(epoch[0]) * 64
    fake = _FakeWorkspaceClient(envelope={"ok": True, "result": body()},
        on_call=lambda _: epoch.__setitem__(0, 2))
    client, _ = _make_app(rsa_key, client=fake, authorize=authorize)
    response = client.get(ROUTE, params=params(), headers=headers(rsa_key))
    assert response.status_code == 403 and "qualified_ruling_digest" not in response.text


def test_acquisition_contract_detaches_only_existing_mission_frame():
    value = {**frame(), "schema": acquisition.FRAME_SCHEMA, "operation": acquisition.OPERATION}
    mission = acquisition.mission_frame(value)
    assert mission["schema"] == "mastermind.executive_workspace_read.v2"
    assert mission["operation"] == "mission_v3"
    assert mission["selection"] == value["selection"]
    mission["principal"]["scopes"].append("foreign")
    assert mission["principal"] != value["principal"]


@pytest.mark.parametrize("defect", ["operation", "schema", "extra", "key", "principal", "scope", "selection_type"])
def test_wire_mode_never_widens_old_grammars(defect):
    value = copy.deepcopy({**frame(), "schema": acquisition.FRAME_SCHEMA, "operation": acquisition.OPERATION})
    if defect == "operation": value["operation"] = original.OPERATION
    if defect == "schema": value["schema"] = "mastermind.executive_workspace_read.v2"
    if defect == "extra": value["owner_target"] = {}
    if defect == "key": value["selection"]["request_message_key"] = selection()["request_message_key"]
    if defect == "principal": value["principal"]["obligation_id"] = "guessed"
    if defect == "scope": value["principal"]["scopes"] += ["submit"]
    if defect == "selection_type": value["selection"] = []
    with pytest.raises(ValueError): acquisition.validate_frame(value)
