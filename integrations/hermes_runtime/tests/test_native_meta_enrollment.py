"""Explicit Meta enrollment on the same bounded native and release owners.

Native state/ticket APIs reuse the existing SQLite owner double. No installed
role, provider, service activation or new Office participant is claimed.
"""
import asyncio
from copy import deepcopy
import json

import pytest

from integrations.hermes_runtime import native_session_control as control
from integrations.hermes_runtime.constants import conversation_contract
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.system_service import render_role_units_from_installation
from integrations.hermes_runtime.tests.test_native_session_enrollment import native, SHA, REQUEST
from integrations.hermes_harness.tests.test_native_executive_consumer import (
    _installation, publication_document,
)
from ops.executive_os import release_manifest as release

META = conversation_contract("mmmeta")
SECRETARY = conversation_contract("mmsecretary")


def installation(role, consumer=True):
    publication = publication_document() if consumer else None
    value = _installation(consumer=publication, role=role)
    row = next(item for item in value["roles"] if item["role"] == role)
    row["native_gateway"]["session_enrollment"]["schema"] = conversation_contract(role).enrollment_schema
    if publication is not None:
        row["native_gateway"]["executive_consumer"]["session"].update(
            role=role, principal_id=f"uid:{row['uid']}")
    return value


def test_secretary_contract_keeps_all_existing_wire_values():
    assert SECRETARY.native_verb == control.VERB
    assert SECRETARY.native_schema == control.SCHEMA
    assert SECRETARY.enrollment_schema == control.ENROLLMENT_SCHEMA
    assert SECRETARY.enrollment_result_schema == control.ENROLLMENT_RESULT_SCHEMA
    assert META.role == "mmmeta" and META.kind == "hermes_meta"
    assert META.native_verb != SECRETARY.native_verb
    assert META.enrollment_result_schema != SECRETARY.enrollment_result_schema


@pytest.mark.parametrize("value", ["", "secretary", "meta", None, True, [], {}])
def test_role_contract_is_closed(value):
    with pytest.raises(RuntimeRefusal):
        conversation_contract(value)


@pytest.mark.parametrize("role", ["mmsecretary", "mmmeta"])
@pytest.mark.parametrize("consumer", [False, True])
def test_role_recipe_matches_runtime_contract_and_preserves_other_unit(role, consumer):
    document = installation(role, consumer)
    checked = release.validate_hermes_runtime_installation(document)
    units = render_role_units_from_installation(checked, release_commit=SHA)
    bare = deepcopy(document)
    row = next(item for item in bare["roles"] if item["role"] == role)
    row.pop("native_gateway")
    unchanged = render_role_units_from_installation(bare, release_commit=SHA)
    other = "mmmeta" if role == "mmsecretary" else "mmsecretary"
    assert units[other] == unchanged[other]
    command = "enroll-meta-session" if role == "mmmeta" else "enroll-secretary-session"
    assert units[role].count("ExecReload=") == 1
    assert f"hermes-runtime {command} --profile" in units[role]
    assert "hermes-runtime canary --profile" not in units[role]
    assert checked == document


@pytest.mark.parametrize("change", ["enrollment_schema", "consumer_role", "request_id"])
def test_meta_recipe_refuses_cross_role_or_foreign_request(change):
    document = installation("mmmeta")
    native_recipe = document["roles"][0]["native_gateway"]
    if change == "enrollment_schema":
        native_recipe["session_enrollment"]["schema"] = SECRETARY.enrollment_schema
    else:
        native_recipe["executive_consumer"]["session"][
            "role" if change == "consumer_role" else "request_id"] = (
                "mmsecretary" if change == "consumer_role" else "foreign-request")
    with pytest.raises(release.ReleaseManifestError):
        release.validate_hermes_runtime_installation(document)


def test_meta_create_and_lost_reply_recover_original_native_session(native):
    native.state.lost = True
    async def execute():
        first = await control._enrollment_operation(
            native.runner, native.home, native.params, native.principal, role="mmmeta")
        assert first["schema"] == META.enrollment_result_schema
        assert first["status"] == "ENROLLED"
        second = await control._enrollment_operation(
            native.runner, native.home, native.params, native.principal, role="mmmeta")
        assert second == first
    asyncio.run(execute())
    assert len(native.state.calls) == 1
    observed = control.read_enrolled_session(
        native.runner, native.home, SHA, REQUEST, native.principal, role="mmmeta")
    assert observed["status"] == "ENROLLED"
    assert observed["target"]["principal_id"] == native.principal
    assert observed["route"] == native.route


def test_meta_enrollment_receipt_cannot_be_validated_as_secretary(native):
    native.commit()
    value = control._inspect_enrollment(
        native.runner, native.home, SHA, REQUEST, native.principal, role="mmmeta")
    assert control.validate_enrollment_result(value, role="mmmeta") == value
    with pytest.raises(RuntimeRefusal, match="NATIVE_ENROLLMENT_RESULT_INVALID"):
        control.validate_enrollment_result(value)
    wrong = dict(value, schema=SECRETARY.enrollment_result_schema)
    with pytest.raises(RuntimeRefusal):
        control.validate_enrollment_result(wrong, role="mmmeta")


def test_private_owner_installs_only_meta_verb_and_preserves_its_effect(native):
    async def execute():
        control.install_private_control(
            native.runner, native.home, "mmmeta", implementation_sha=SHA,
            session_enrollment={"schema": META.enrollment_schema, "request_id": REQUEST})
        handlers = native.runner.session_control_server.private_handlers
        assert set(handlers) == {META.native_verb}
        handler = handlers[META.native_verb]
        before = await asyncio.to_thread(handler, {
            "operation": "inspect_enrollment", "profile_id": str(native.home),
            "implementation_sha": SHA, "request_id": REQUEST}, native.principal)
        assert before["status"] == "ABSENT" and before["schema"] == META.enrollment_result_schema
        value = await asyncio.to_thread(handler, native.params, native.principal)
        assert value["status"] == "ENROLLED" and value["schema"] == META.enrollment_result_schema
        with pytest.raises(RuntimeRefusal, match="NATIVE_SECRETARY_CONTROL_ALREADY_INSTALLED"):
            control.install_private_control(native.runner, native.home, "mmsecretary")
    asyncio.run(execute())
    assert len(native.state.calls) == 1


def test_private_meta_capability_cannot_be_secretary_capability(native):
    async def execute():
        with pytest.raises(RuntimeRefusal, match="NATIVE_ENROLLMENT_CAPABILITY_INVALID"):
            control.install_private_control(
                native.runner, native.home, "mmmeta", implementation_sha=SHA,
                session_enrollment={"schema": SECRETARY.enrollment_schema, "request_id": REQUEST})
        assert not native.runner.session_control_server.private_handlers
    asyncio.run(execute())
    assert not native.state.calls


def test_meta_client_refuses_foreign_result_contract_before_socket(native):
    client = control.NativeSecretaryClient(native.home, role="mmmeta")
    with pytest.raises(RuntimeRefusal, match="NATIVE_CONVERSATION_SCHEMA_INVALID"):
        client._call({"operation": "observe"}, result_schema=control.SCHEMA)
    with pytest.raises(RuntimeRefusal, match="NATIVE_CONVERSATION_SCHEMA_INVALID"):
        client._call({"operation": "inspect_enrollment"}, result_schema=control.ENROLLMENT_RESULT_SCHEMA)


def test_opaque_bootstrap_does_not_qualify_a_malformed_consumer():
    value = installation("mmmeta")
    value["roles"][0]["native_gateway"]["executive_consumer"] = {"not": "a publication"}
    staged = release.validate_hermes_runtime_installation(value, _defer_consumer=True)
    assert staged == value
    with pytest.raises(release.ReleaseManifestError, match="executive consumer is invalid"):
        release.validate_hermes_runtime_installation(staged)
    staged["roles"][0]["native_gateway"]["executive_consumer"]["not"] = "changed"
    assert value["roles"][0]["native_gateway"]["executive_consumer"]["not"] == "a publication"
