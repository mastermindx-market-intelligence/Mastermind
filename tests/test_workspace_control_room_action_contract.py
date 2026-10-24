"""Closed action transport facts; no socket, grant or operation is created."""
import copy

import pytest

from common import workspace_control_room_action_contract as actions
from common.executive_workspace_contract import MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, canonical
from tests.test_workspace_member_bindings import fixture, principal


def payload(operation):
    return {
        "open": {"binding_id": "11111111-1111-4111-8111-111111111111"},
        "bind": {"work_ref": "WS:FIXTURE", "role": "worker", "provider": "cursor_agent",
                 "locator": {"chat_id": "fixture-only", "workspace_dir": None}},
        "unbind": {"binding_id": "11111111-1111-4111-8111-111111111111"},
        "refresh-builds": {},
    }[operation]


def frame(operation="open"):
    _, members = fixture(1)
    return {"schema": actions.FRAME_SCHEMA, "operation": operation,
            "principal": principal(members), "admission_expires_at": 2000000000,
            "payload": payload(operation)}


@pytest.mark.parametrize("operation", ["open", "bind", "unbind", "refresh-builds"])
def test_action_frame_is_closed_bounded_and_detached(operation):
    value = frame(operation)
    before = copy.deepcopy(value)
    parsed = actions.validate_frame(value)
    assert parsed == before and parsed is not value
    value["principal"]["subject_digest"] = "f" * 64
    value["payload"].clear()
    assert parsed == before
    assert len(canonical(parsed)) + 1 <= MAX_REQUEST_BYTES


@pytest.mark.parametrize("mutation", [
    "schema", "operation", "top_level_key", "path", "argv", "owner", "grant",
    "role", "wrong_resource", "wrong_scope", "extra_scope", "missing_principal_key",
])
def test_action_frame_cannot_carry_alternative_authority_or_execution_inputs(mutation):
    value = frame()
    if mutation == "schema": value["schema"] = "mastermind.workspace_control_room_read.v1"
    elif mutation == "operation": value["operation"] = "discover"
    elif mutation in {"top_level_key", "path", "argv", "owner", "grant"}: value[mutation] = "fixture"
    elif mutation == "role": value["principal"]["role"] = "admin"
    elif mutation == "wrong_resource": value["principal"]["resource"] = "https://other.example.test"
    elif mutation == "wrong_scope": value["principal"]["scopes"] = ["mastermind.executive.intent.submit"]
    elif mutation == "extra_scope": value["principal"]["scopes"].append("mastermind.executive.intent.submit")
    elif mutation == "missing_principal_key": del value["principal"]["client_ref"]
    with pytest.raises(ValueError, match="invalid_input"):
        actions.validate_frame(value)


@pytest.mark.parametrize("expiry", [None, True, 0, -1, 1.5, "2000000000"])
def test_admission_expiry_is_a_positive_host_derived_integer(expiry):
    value = frame()
    value["admission_expires_at"] = expiry
    with pytest.raises(ValueError, match="invalid_input"):
        actions.validate_frame(value)


@pytest.mark.parametrize("operation,value", [
    ("open", {}),
    ("open", {"binding_id": ""}),
    ("open", {"binding_id": "fixture", "target_surface": "other"}),
    ("open", {"binding_id": "fixture", "command": "not-a-selector"}),
    ("bind", {"work_ref": "WS:X", "role": "worker", "provider": "cursor_agent", "locator": []}),
    ("bind", dict(payload("bind"), seat_ref=True)),
    ("unbind", {"binding_id": "fixture", "owed_context": None}),
    ("refresh-builds", {"macro_root": "/fixture"}),
    ("refresh-builds", None),
])
def test_action_payload_has_only_the_original_closed_primitive_inputs(operation, value):
    request = frame(operation)
    request["payload"] = value
    with pytest.raises(ValueError, match="invalid_input"):
        actions.validate_frame(request)


def test_explicit_owed_context_is_preserved_for_the_original_owner_to_refuse():
    request = frame()
    request["payload"]["owed_context"] = None
    parsed = actions.validate_frame(request)
    assert "owed_context" in parsed["payload"] and parsed["payload"]["owed_context"] is None


def test_request_byte_budget_counts_utf8_and_the_final_newline():
    request = frame("bind")
    request["payload"]["locator"]["chat_id"] = "界" * MAX_REQUEST_BYTES
    with pytest.raises(ValueError, match="invalid_input"):
        actions.validate_frame(request)


@pytest.mark.parametrize("operation", ["open", "bind", "unbind", "refresh-builds"])
def test_unknown_result_is_explicit_bounded_and_never_retry_advice(operation):
    result = actions.unknown_result(operation)
    assert result["schema"] == actions.RESULT_SCHEMA
    assert result["operation"] == operation
    assert result["status"] == 503 and result["disposition"] == "EFFECT_UNKNOWN"
    assert result["outcome"]["retryable"] is False
    assert result["outcome"]["next_action"] == "read_current_state"
    assert actions.validate_result(result, operation=operation) == result
    assert len(canonical({"ok": True, "result": result})) + 1 <= MAX_RESPONSE_BYTES


def test_owner_returned_does_not_infer_success_or_no_effect():
    outcome = {"ok": False, "detail": "accepted input retained; publication unavailable"}
    result = actions.action_result(
        "refresh-builds", outcome, status=200, disposition="OWNER_RETURNED",
    )
    assert result["outcome"] == outcome and result["disposition"] == "OWNER_RETURNED"
    outcome["detail"] = "caller mutation"
    assert result["outcome"]["detail"] == "accepted input retained; publication unavailable"


@pytest.mark.parametrize("mutation", ["operation", "status", "disposition", "extra", "unknown_detail"])
def test_private_action_result_has_no_cross_operation_or_false_refusal_rewrite(mutation):
    result = actions.unknown_result("open")
    if mutation == "operation": result["operation"] = "unbind"
    if mutation == "status": result["status"] = 200
    if mutation == "disposition": result["disposition"] = "NOT_DISPATCHED"
    if mutation == "extra": result["internal_path"] = "/fixture/private"
    if mutation == "unknown_detail": result["outcome"]["detail"] = "/fixture/private"
    with pytest.raises(ValueError, match="source_unavailable"):
        actions.validate_result(result, operation="open")


def test_actual_owner_precondition_refusal_preserves_status_and_outcome():
    outcome = {"ok": False, "failure_kind": "source_precondition_failed",
               "next_action": "read_current_state"}
    result = actions.action_result("open", outcome, status=409, disposition="NOT_DISPATCHED")
    assert result["outcome"] == outcome and result["status"] == 409


def test_over_budget_owner_result_refuses_instead_of_truncating_or_claiming_no_effect():
    with pytest.raises(ValueError, match="source_unavailable"):
        actions.action_result(
            "open", {"ok": True, "detail": "x" * MAX_RESPONSE_BYTES},
            status=200, disposition="OWNER_RETURNED",
        )
