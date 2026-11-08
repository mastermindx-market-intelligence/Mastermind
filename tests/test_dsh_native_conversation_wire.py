"""Closed v2 syntax; owner admission and physical effects are separate proofs."""
import copy
import hashlib
import json

import pytest
from common import fresh_conversation_contract as wire

BASE = {"work_ref": "WS:ONE", "operation_key": "native-one"}
DIGEST = "a" * 64

def principal(resource="executive"):
    return dict(policy_id="policy", issuer="https://issuer.example",
        issuer_digest="b"*64, resource=resource, subject_digest="c"*64,
        client_ref="client", scopes=["read"], issued_at=1, expires_at=2, jti_digest=None)

def request(operation):
    value = dict(BASE)
    if operation in {"preview", "create", "turn", "turn_preview"}: value["message"] = "  exact text\n"
    if operation in {"consume", "consume_status", "turn", "turn_preview"}: value["initial_digest"] = DIGEST
    if operation.startswith("turn"): value["turn_key"] = "t1"
    if operation.startswith("resume"): value["resume_key"] = "r1"
    if operation.startswith("stop"): value["stop_key"] = "s1"
    if operation in {"create", "turn", "resume"}: value["preview_digest"] = DIGEST
    if operation in {"resume", "resume_preview"}: value["expected_result_digest"] = DIGEST
    if operation == "stop": value.update(turn_id="TURN:1", binding_digest=DIGEST)
    return value

def frame(operation):
    return dict(schema=wire.NATIVE_SCHEMA, operation=operation,
        principal=principal(), workspace_principal=principal("workspace")
            if operation in wire.NATIVE_DUAL_RESOURCE else None, arguments=request(operation))

@pytest.mark.parametrize("message", ["x"*131072, "中"*43690, "  native\r\n\ttext  ", "\U0001f642"*32768])
def test_native_message_preserves_exact_utf8_and_original_objective_identity(message):
    value = {**BASE, "message": message}
    assert wire.validate_request(value, operation="preview", schema=wire.NATIVE_SCHEMA)["message"] == message
    material = json.loads(wire.native_objective(message))
    raw = message.encode()
    assert material == dict(mode="fresh_native_conversation", result_contract=wire.NATIVE_RESULT_CONTRACT,
        message_sha256=hashlib.sha256(raw).hexdigest(), message_utf8_bytes=len(raw))
    assert len(wire.native_objective(message)) < 4000
    if message.strip() != message:
        assert wire.native_objective(message) != wire.native_objective(message.strip())

@pytest.mark.parametrize("message", ["x"*131073, "中"*43691, "\U0001f642"*32769, "\ud800", "x\x00", "\x7f", "\x85", " \t\n"])
def test_native_message_refuses_invalid_or_over_budget_input(message):
    with pytest.raises((ValueError, UnicodeError)):
        wire.validate_request({**BASE, "message": message}, operation="preview", schema=wire.NATIVE_SCHEMA)

def test_v1_message_limit_and_optional_send_preview_remain_unchanged():
    with pytest.raises(ValueError):
        wire.validate_request({**BASE, "message": "x"*701}, operation="preview")
    legacy = request("turn")
    legacy.pop("preview_digest")
    assert wire.validate_request(legacy, operation="turn") == legacy
    with pytest.raises(ValueError):
        wire.validate_request(legacy, operation="turn", schema=wire.NATIVE_SCHEMA)

@pytest.mark.parametrize("operation", [op for op in wire.NATIVE_ROUTES.values() if op != "stop"])
def test_native_closed_fields_and_resource_principals(operation):
    value = frame(operation)
    assert wire.validate_private_frame(value) == value
    for field in ("provider", "model", "execution_profile", "native_session_id", "worker_id", "authorization_generation"):
        changed = copy.deepcopy(value)
        changed["arguments"][field] = "untrusted"
        with pytest.raises(ValueError):
            wire.validate_private_frame(changed)
    changed = copy.deepcopy(value)
    if operation in wire.NATIVE_DUAL_RESOURCE:
        changed["workspace_principal"] = None
    else:
        changed["workspace_principal"] = principal("workspace")
    with pytest.raises((ValueError, TypeError)):
        wire.validate_private_frame(changed)

@pytest.mark.parametrize("operation", ["create", "turn", "resume"])
def test_native_modifying_preview_is_required(operation):
    value = request(operation)
    value.pop("preview_digest")
    with pytest.raises(ValueError):
        wire.validate_native_request(value, operation=operation)

def test_native_wire_version_cannot_be_smuggled_through_v1():
    value = frame("resume")
    value["schema"] = wire.SCHEMA
    with pytest.raises(ValueError):
        wire.validate_private_frame(value)
    with pytest.raises(ValueError):
        wire.validate_request(request("preview"), operation="preview", schema="mastermind.executive.fresh_conversation.v3")
    assert not set(wire.ROUTES) & set(wire.NATIVE_ROUTES)
    assert "/os/executive/conversation/v2/%73top" not in wire.NATIVE_ROUTES

def test_native_frame_budget_includes_both_principals_and_encoded_message():
    value = frame("create")
    value["arguments"]["message"] = '"' * wire.NATIVE_MESSAGE_BYTES
    for p in (value["principal"], value["workspace_principal"]):
        for field in wire.PRINCIPAL_FIELDS - {"scopes", "issued_at", "expires_at", "jti_digest"}:
            p[field] = "\x00" * 2048
        p["scopes"] = [("\x00"*90 + str(i)) for i in range(16)]
    accepted = wire.validate_private_frame(value)
    actual = wire._bounded_json(accepted, wire.NATIVE_MAX_REQUEST_BYTES, newline=True)
    assert actual.endswith(b"\n") and len(actual) <= wire.NATIVE_MAX_REQUEST_BYTES
    assert len(actual) > 65536
    value["arguments"]["message"] += "x"
    with pytest.raises(ValueError):
        wire.validate_private_frame(value)

def test_native_original_reference_is_shared_but_does_not_select_a_new_root():
    reference = dict(schema="mastermind.fresh_conversation_reference.v1",
        work_ref="WS:ONE", root_job_id="JOB:1", root_event_id=1,
        root_event_sha256=DIGEST, principal_scope_sha256="b"*64)
    value = {"work_ref": "WS:ONE", "reference": reference}
    assert wire.validate_native_request(value, operation="read") == value
    with pytest.raises(ValueError):
        wire.validate_native_request({**value, "operation_key": "second"}, operation="read")
    with pytest.raises(ValueError):
        wire.validate_native_request({**value, "message": "x"}, operation="preview")
    with pytest.raises(ValueError):
        wire.validate_native_request({**value, "work_ref": "WS:OTHER"}, operation="read")

def absent():
    return dict(schema=wire.NATIVE_DATA_SCHEMA, work_ref="WS:ONE", operation_key="native-one", reference=None,
        state="ABSENT", effect="NONE", parent_consumed=False, preview=None, locator=None,
        session=None, active_turn=None, result=None, head_result=None, can_send=False, can_resume=False, can_stop=False)

def response(data, operation="status"):
    return dict(schema=wire.NATIVE_RESULT_SCHEMA, operation=operation, ok=True, data=data, error=None)

def test_native_absent_response_cannot_claim_controls_or_change_contract():
    value = response(absent())
    assert wire.validate_native_response(value, BASE, operation="status") == value
    for field in ("can_send", "can_stop", "can_resume", "parent_consumed"):
        changed = copy.deepcopy(value)
        changed["data"][field] = True
        with pytest.raises(ValueError):
            wire.validate_native_response(changed, BASE, operation="status")
    for changed in ({**value, "schema": wire.RESULT_SCHEMA},
                    {**value, "operation": "read"},
                    {**value, "ok": 1},
                    {**value, "extra": True}):
        with pytest.raises(ValueError):
            wire.validate_native_response(changed, BASE, operation="status")

def test_native_response_budget_counts_complete_encoded_private_wrapper():
    value = absent()
    value.update(state="PREVIEW_READY", preview=dict(digest=DIGEST, profile_digest=DIGEST, source_digest=DIGEST,
        grounding={"opaque": '"' * 17000}, attempt_limit=1, worker_account="REGISTERED_NOT_SESSION_ATTESTED"))
    with pytest.raises(ValueError, match="byte limit"):
        wire.validate_native_response(response(value, "preview"), request("preview"), operation="preview")

def test_native_owner_types_stop_and_exact_result_reference():
    # Runs with the actual repository types; never substitute a shape-only
    # mock for original identifier/receipt semantics.
    from control_plane.native_conversation_result import NativeConversationResultRef
    value = frame("stop")
    assert wire.validate_private_frame(value) == value
    reference = NativeConversationResultRef("ohf-native-result:TURN:1", 7, DIGEST, "b"*64)
    result = dict(contract=wire.NATIVE_RESULT_CONTRACT, digest=DIGEST, reference=reference.to_wire())
    assert wire.validate_native_result(result) == result
    for changed in ({**result, "digest": "c"*64}, {**result, "envelope": {}},
                    {**result, "reference": {**reference.to_wire(), "event_id": True}}):
        with pytest.raises(ValueError):
            wire.validate_native_result(changed)


def _reference():
    return dict(schema="mastermind.fresh_conversation_reference.v1", work_ref="WS:ONE", root_job_id="JOB:1",
        root_event_id=1, root_event_sha256=DIGEST, principal_scope_sha256="b"*64)

@pytest.mark.parametrize("event_id", [True, 1.0])
def test_native_response_revalidates_reference_scalar_types(event_id):
    original = _reference()
    selected = dict(work_ref="WS:ONE", reference=original)
    data = {**absent(), "operation_key": None, "reference": {**original, "root_event_id": event_id}}
    with pytest.raises(ValueError):
        wire.validate_native_response(response(data), selected, operation="status")

def test_native_reference_locator_cannot_change_original_root():
    selected = dict(work_ref="WS:ONE", reference=_reference())
    data = {**absent(), "operation_key": None, "reference": selected["reference"], "state": "ADMITTED",
        "locator": dict(work_ref="WS:ONE", root_job_id="JOB:OTHER", job_id=None, attempt_id=None)}
    with pytest.raises(ValueError, match="another original root"):
        wire.validate_native_response(response(data), selected, operation="status")

def test_native_ready_projection_requires_real_child_and_idle_session():
    preview = dict(schema=wire.NATIVE_TURN_PREVIEW_SCHEMA, work_ref="WS:ONE", operation_key="native-one",
        reference=None, turn_key="t1", state="TURN_READY", effect="NONE", parent_consumed=False, can_send=True,
        locator=dict(work_ref="WS:ONE", root_job_id="JOB:1", job_id=None, attempt_id=None),
        initial_consumption=dict(state="CONSUMED", event_id=1, event_sha256=DIGEST, initial_digest=DIGEST),
        preview_digest=DIGEST)
    with pytest.raises(ValueError, match="child and Attempt"):
        wire.validate_native_response(response(preview, "turn_preview"), request("turn_preview"), operation="turn_preview")
    preview = dict(schema=wire.NATIVE_CONTROL_DATA_SCHEMA, work_ref="WS:ONE", operation_key="native-one", reference=None,
        kind="resume", control_key="r1", state="RESUME_READY", effect="NONE", locator=None, session=None,
        active_turn=None, operation_id=None, receipt=None, head_result=None, preview_digest=DIGEST, parent_consumed=False,
        target=dict(expected_result_digest=DIGEST, binding_digest=DIGEST))
    with pytest.raises(ValueError, match="original idle session"):
        wire.validate_native_response(response(preview, "resume_preview"), request("resume_preview"), operation="resume_preview")

@pytest.mark.parametrize("state", ["CREATED", "IDLE"])
def test_native_settled_state_cannot_omit_original_session_and_result(state):
    with pytest.raises(ValueError, match="result anchors"):
        wire.validate_native_response(response({**absent(), "state": state}), BASE, operation="status")

def test_native_owner_types_control_target_is_historical_and_locator_remains_exact():
    from control_plane.native_conversation_result import NativeConversationResultRef
    from control_plane.operator_harness_contract import OperationId, OperationReceiptKind, operation_receipt_command_id
    request_value = request("stop")
    operation = OperationId("ohf-op:stop:native-wire")
    value = dict(schema=wire.NATIVE_CONTROL_DATA_SCHEMA, work_ref="WS:ONE", operation_key="native-one", reference=None,
        kind="stop", control_key="s1", state="APPLIED", effect="COMMITTED",
        locator=dict(work_ref="WS:ONE", root_job_id="JOB:1", job_id="JOB:2", attempt_id="ATT:1"),
        session=dict(attempt_id="ATT:1", session_epoch_id="EPOCH:1", process_generation_id="GEN:1",
                     provider_session_id="SESSION:1", binding_digest="c"*64),
        active_turn=dict(turn_id="TURN:2", begin_operation_id="ohf-op:turn:2"),
        operation_id=operation.command_id,
        receipt=dict(kind=OperationReceiptKind.APPLIED.value,
            command_id=operation_receipt_command_id(operation, OperationReceiptKind.APPLIED),
            event_id=5, event_sha256=DIGEST),
        head_result=None, preview_digest=None, parent_consumed=False,
        target=dict(turn_id=request_value["turn_id"], binding_digest=request_value["binding_digest"]))
    # Current status may advance. The original control owner must independently
    # join this historical target and receipt to the exact control-request Event.
    assert wire.validate_native_response(response(value, "stop"), request_value, operation="stop")
    absent_control = copy.deepcopy(value)
    absent_control.update(state="ABSENT", effect="NONE")
    with pytest.raises(ValueError, match="absent native control"):
        wire.validate_native_response(response(absent_control, "stop_status"), request("stop_status"), operation="stop_status")
    wrong = copy.deepcopy(value); wrong["session"]["attempt_id"]="ATT:OTHER"
    with pytest.raises(ValueError, match="session locator"):
        wire.validate_native_response(response(wrong, "stop"), request_value, operation="stop")
    wrong = copy.deepcopy(value); wrong["target"]["turn_id"]="TURN:OTHER"
    with pytest.raises(ValueError, match="original request"):
        wire.validate_native_response(response(wrong, "stop"), request_value, operation="stop")
    ref = NativeConversationResultRef("ohf-native-result:TURN:1", 2, "e"*64, "f"*64)
    preview = {**value, "kind":"resume", "control_key":"r1", "state":"RESUME_READY", "effect":"NONE",
        "active_turn":None, "operation_id":None, "receipt":None, "preview_digest":DIGEST,
        "head_result":dict(contract=wire.NATIVE_RESULT_CONTRACT,digest=ref.seal_digest,reference=ref.to_wire()),
        "target":dict(expected_result_digest=DIGEST,binding_digest=DIGEST)}
    with pytest.raises(ValueError, match="resume head differs"):
        wire.validate_native_response(response(preview, "resume_preview"), request("resume_preview"), operation="resume_preview")


def test_native_resume_preview_binds_the_current_idle_writer():
    from control_plane.native_conversation_result import NativeConversationResultRef
    ref = NativeConversationResultRef("ohf-native-result:TURN:1", 2, DIGEST, "f"*64)
    data = dict(schema=wire.NATIVE_CONTROL_DATA_SCHEMA, work_ref="WS:ONE", operation_key="native-one",
        reference=None, kind="resume", control_key="r1", state="RESUME_READY", effect="NONE",
        locator=dict(work_ref="WS:ONE", root_job_id="JOB:1", job_id="JOB:2", attempt_id="ATT:1"),
        session=dict(attempt_id="ATT:1", session_epoch_id="EPOCH:1", process_generation_id="GEN:1",
            provider_session_id="SESSION:1", binding_digest="c"*64), active_turn=None, operation_id=None,
        receipt=None, head_result=dict(contract=wire.NATIVE_RESULT_CONTRACT, digest=ref.seal_digest,
            reference=ref.to_wire()), preview_digest=DIGEST, parent_consumed=False,
        target=dict(expected_result_digest=DIGEST, binding_digest="c"*64))
    selected = request("resume_preview")
    assert wire.validate_native_response(response(data, "resume_preview"), selected, operation="resume_preview")
    reserved = {**data, "operation_id": "ohf-op:original-resume"}
    with pytest.raises(ValueError, match="preview cannot carry an operation"):
        wire.validate_native_response(response(reserved, "resume_preview"), selected, operation="resume_preview")
    changed = copy.deepcopy(data)
    changed["target"]["binding_digest"] = "d"*64
    with pytest.raises(ValueError, match="resume target binding"):
        wire.validate_native_response(response(changed, "resume_preview"), selected, operation="resume_preview")


@pytest.mark.parametrize("operation", ["turn", "turn_status", "turn_read"])
def test_native_turn_response_cannot_borrow_consumption_state_or_send_projection(operation):
    value = dict(schema=wire.NATIVE_TURN_DATA_SCHEMA, **BASE, reference=None, turn_key="t1",
        state="CONSUMED", effect="NONE", parent_consumed=False, can_send=True,
        locator=dict(work_ref="WS:ONE", root_job_id="JOB:1", job_id="JOB:2", attempt_id="ATT:1"),
        initial_consumption=dict(state="CONSUMED", event_id=1, event_sha256=DIGEST, initial_digest=DIGEST),
        result=None)
    with pytest.raises(ValueError, match="state differs from operation"):
        wire.validate_native_response(response(value, operation), request(operation), operation=operation)


def test_native_consumption_recovery_cannot_grant_new_send():
    value = dict(schema=wire.NATIVE_TURN_DATA_SCHEMA, **BASE, reference=None, turn_key=None,
        state="CONSUMED", effect="NONE", parent_consumed=False, can_send=True,
        locator=dict(work_ref="WS:ONE", root_job_id="JOB:1", job_id="JOB:2", attempt_id="ATT:1"),
        initial_consumption=dict(state="CONSUMED", event_id=1, event_sha256=DIGEST, initial_digest=DIGEST),
        result=None)
    assert wire.validate_native_response(response(value, "consume"), request("consume"), operation="consume")
    with pytest.raises(ValueError, match="another Send"):
        wire.validate_native_response(response(value, "consume_status"), request("consume_status"), operation="consume_status")


@pytest.mark.parametrize("field", ["operation_id", "receipt", "session", "active_turn", "target", "head_result", "preview_digest"])
def test_native_absent_control_cannot_smuggle_attached_evidence(field):
    value = dict(schema=wire.NATIVE_CONTROL_DATA_SCHEMA, **BASE, reference=None,
        kind="stop", control_key="s1", state="ABSENT", effect="NONE",
        locator=dict(work_ref="WS:ONE", root_job_id="JOB:1", job_id="JOB:2", attempt_id="ATT:1"),
        session=None, active_turn=None, operation_id=None, receipt=None, head_result=None,
        preview_digest=None, parent_consumed=False, target=None)
    assert wire.validate_native_response(response(value, "stop_status"), request("stop_status"), operation="stop_status")
    value[field] = "foreign-attached-evidence"
    with pytest.raises(ValueError, match="absent native control"):
        wire.validate_native_response(response(value, "stop_status"), request("stop_status"), operation="stop_status")

@pytest.mark.parametrize("operation", ["recover", "turn_recover"])
def test_signed_original_recovery_responses_cannot_claim_a_new_provider_effect(operation):
    from pathlib import Path
    fixture = json.loads((Path(__file__).parents[1] /
        "app/mastermind_os/src/fixtures/native-fresh-recovery-owner.json").read_text())
    sample = next(value for value in fixture["samples"] if value["operation"] == operation)
    assert wire.validate_native_response(sample["response"], sample["arguments"], operation=operation)
    changed = copy.deepcopy(sample["response"])
    changed["data"]["effect"] = "COMMITTED"
    with pytest.raises(ValueError, match="new effect"):
        wire.validate_native_response(changed, sample["arguments"], operation=operation)
