"""H5 configured-model READ through the original signed HTTP and Unix owners.

All principals, sockets and Runtime owners are disposable fixtures. The real
ModelRouter reads repository policy; no credential, provider, or live pool is used.
"""
import asyncio
import copy
from dataclasses import replace

import pytest

from common import executive_workspace_contract as original_wire
from common import workspace_model_configuration_contract as wire
from control_plane import model_router_configuration as configuration
from control_plane import workspace_model_configuration_read as source
from integrations.mastermind_workspace_app.contract import principal_frame
from tests import test_workspace_admitted_plan_read as transport_suite
from tests.test_workspace_admitted_plan_read import plan_owner
from tests.test_workspace_read_app import (
    _workspace_token, rsa_key,
)
from tests.test_workspace_read_socket import short_socket_root

ROUTE = "/workspace/resources/models/current"


def _frame(principal):
    return {
        "schema": wire.FRAME_SCHEMA,
        "operation": wire.OPERATION,
        "selection": None,
        "principal": principal_frame(principal),
    }


def test_signed_http_socket_and_actual_router_keep_configuration_separate_from_admission(
        plan_owner, rsa_key, tmp_path, short_socket_root):
    expected = configuration.load_configuration()
    wire.validate_configuration(expected)

    async def run():
        async with transport_suite.transport(
                plan_owner, rsa_key, tmp_path, short_socket_root) as (
                    http, token, slots, seen, client, principal, mounted):
            before = plan_owner["namespace"].entries
            response = await http.get(ROUTE, headers={"Authorization": "Bearer " + token})
            assert response.status_code == 200, response.text
            body = response.json()
            assert wire.validate_result(body) is body
            assert body["configuration"] == expected
            assert body["availability"] == "AVAILABLE"
            assert body["configuration"]["physical_account_pools"] == "NOT_JOINED"
            assert body["configuration"]["live_capacity"] == "NOT_OBSERVED"
            assert body["configuration"]["admission_authorized"] is False
            assert body["configuration"]["credential_resolution_performed"] is False
            assert body["configuration"]["providers"] and body["configuration"]["models"]
            assert response.headers["cache-control"] == "no-store"
            direct = await client.request(_frame(principal))
            assert direct["ok"] is True
            assert direct["result"]["configuration"] == expected
            assert len(original_wire.canonical(direct)) + 1 <= wire.MAX_RESPONSE_BYTES
            assert seen["factory"] == 2
            assert plan_owner["namespace"].entries == before

    asyncio.run(run())


@pytest.mark.parametrize("case", ["missing", "foreign_scope"])
def test_unqualified_http_principal_never_reaches_original_source_factory(
        plan_owner, rsa_key, tmp_path, short_socket_root, case):
    async def run():
        async with transport_suite.transport(
                plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, slots, seen, *_):
            headers = {} if case == "missing" else {
                "Authorization": "Bearer " + _workspace_token(
                    rsa_key, scope="mastermind.executive.read")}
            response = await http.get(ROUTE, headers=headers)
            assert response.status_code in (401, 403)
            assert seen["factory"] == 0
    asyncio.run(run())


@pytest.mark.parametrize("case", ["query", "body", "post", "encoded_route"])
def test_fixed_read_has_no_caller_selected_source_or_write_shape(
        plan_owner, rsa_key, tmp_path, short_socket_root, case):
    async def run():
        async with transport_suite.transport(
                plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, slots, seen, *_):
            kwargs = {"headers": {"Authorization": "Bearer " + token}}
            method, path = "GET", ROUTE
            if case == "query":
                kwargs["params"] = {"policy": "/private/unqualified.json"}
            elif case == "body":
                kwargs["content"] = b'{"policy":"caller-selected"}'
            elif case == "post":
                method = "POST"
            else:
                path = "/workspace/resources/%6dodels/current"
            response = await http.request(method, path, **kwargs)
            assert response.status_code in (400, 404, 405)
            assert seen["factory"] == 0
    asyncio.run(run())


@pytest.mark.parametrize("case", ["disabled", "permission_changed", "expired"])
def test_http_release_rechecks_original_permission_and_expiry(
        plan_owner, rsa_key, tmp_path, short_socket_root, case):
    def after(slots, clock):
        if case == "disabled":
            slots["profiles"]["web"]["enabled"] = False
        elif case == "permission_changed":
            slots["profiles"]["web"]["binding"]["permission_digest"] = "b" * 64
        else:
            clock[0] += 86400

    async def run():
        async with transport_suite.transport(
                plan_owner, rsa_key, tmp_path, short_socket_root,
                after_app=after) as (http, token, *_):
            response = await http.get(ROUTE, headers={"Authorization": "Bearer " + token})
            assert response.status_code == 403
            assert "configuration" not in response.text
    asyncio.run(run())


def test_original_socket_rechecks_permission_after_actual_configuration_read(
        plan_owner, rsa_key, tmp_path, short_socket_root, monkeypatch):
    original = source.read_model_configuration
    slots_ref = []

    def revoke():
        response = original()
        assert response["result"]["availability"] == "AVAILABLE"
        slots_ref[0]["profiles"]["web"]["enabled"] = False
        return response

    monkeypatch.setattr(source, "read_model_configuration", revoke)

    async def run():
        async with transport_suite.transport(
                plan_owner, rsa_key, tmp_path, short_socket_root) as (
                    http, token, slots, seen, client, principal, mounted):
            slots_ref.append(slots)
            response = await client.request(_frame(principal))
            assert response == original_wire.error("access_denied", 403)
            assert seen["factory"] == 1
    asyncio.run(run())


def test_executive_binding_replacement_withholds_observed_configuration(
        plan_owner, rsa_key, tmp_path, short_socket_root, monkeypatch):
    controls = []
    original_control = transport_suite.control
    original_read = source.read_model_configuration

    def control(*args, **kwargs):
        actual = original_control(*args, **kwargs)
        controls.append(actual)
        return actual

    def changed():
        response = original_read()
        assert response["result"]["availability"] == "AVAILABLE"
        actual = controls[0]
        actual._ceo_ingress_app_binding = replace(actual._ceo_ingress_app_binding)
        return response

    monkeypatch.setattr(transport_suite, "control", control)
    monkeypatch.setattr(source, "read_model_configuration", changed)

    async def run():
        async with transport_suite.transport(
                plan_owner, rsa_key, tmp_path, short_socket_root) as (
                    http, token, slots, seen, client, principal, mounted):
            response = await client.request(_frame(principal))
            assert response == original_wire.error("access_denied", 403)
    asyncio.run(run())


@pytest.mark.parametrize("field,value", [
    ("physical_account_pools", {"account": "PRIVATE-UNQUALIFIED"}),
    ("live_capacity", "READY"),
    ("admission_authorized", True),
])
def test_http_wire_refuses_unqualified_physical_or_admission_claims(
        plan_owner, rsa_key, tmp_path, short_socket_root, monkeypatch, field, value):
    envelope = copy.deepcopy(source.read_model_configuration())
    assert envelope["result"]["availability"] == "AVAILABLE"
    envelope["result"]["configuration"][field] = value
    monkeypatch.setattr(source, "read_model_configuration", lambda: envelope)

    async def run():
        async with transport_suite.transport(
                plan_owner, rsa_key, tmp_path, short_socket_root) as (
                    http, token, slots, seen, *_):
            response = await http.get(ROUTE, headers={"Authorization": "Bearer " + token})
            assert response.status_code == 503
            assert "PRIVATE-UNQUALIFIED" not in response.text
            assert seen["factory"] == 1
    asyncio.run(run())


@pytest.mark.parametrize("raw,code", [
    ('{"policy_version":"first","policy_version":"second"}', "DUPLICATE_CONFIGURATION_KEY"),
    ('{"value":NaN}', "NONFINITE_CONFIGURATION_VALUE"),
])
def test_configuration_reader_refuses_ambiguous_or_nonfinite_source(tmp_path, raw, code):
    path = tmp_path / "policy.json"
    path.write_text(raw)
    with pytest.raises(configuration.ConfigurationError, match=code):
        configuration.read_configuration_source(path)


def test_atomic_source_replacement_during_read_refuses_old_observation(tmp_path, monkeypatch):
    path = tmp_path / "policy.json"
    path.write_text('{"policy_version":"same-public-value"}')
    original = configuration.os.read
    replaced = []

    def read(fd, size):
        raw = original(fd, size)
        if raw and not replaced:
            changed = tmp_path / "new-policy.json"
            changed.write_bytes(path.read_bytes())
            changed.replace(path)
            replaced.append(True)
        return raw

    monkeypatch.setattr(configuration.os, "read", read)
    with pytest.raises(configuration.ConfigurationError, match="CONFIGURATION_CHANGED_DURING_READ"):
        configuration.read_configuration_source(path)
    assert replaced == [True]
