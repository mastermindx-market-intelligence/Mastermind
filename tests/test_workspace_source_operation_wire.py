"""Owned specification tests; refused worker artifacts are not used here."""
import copy
import json
import pytest

from common.workspace_source_operation_wire import validate_frame, decode_frame, FRAME_SCHEMA
from common.executive_workspace_contract import RESOURCE, SCOPE

PREFIX = {"publish_project_proposal": "mmos-project-create-",
          "publish_project_plan_proposal": "mmos-project-plan-proposal-", "ADOPT_PLAN": "mmos-project-adopt-",
          "ACCEPT_DIRECTION": "mmos-direction-accept-", "add_project_file": "mmos-project-file-add-",
          "set_project_communication_preference": "mmos-project-preference-set-"}


def lookup(action="publish_project_proposal"):
    value = {"action": action, "request_id": PREFIX[action] + "a" * 40, "work_ref": "WS:TEST"}
    if action in {"add_project_file", "set_project_communication_preference"}:
        value.update(source_commit="b" * 40, base_revision="c" * 64, request_sha256="d" * 64,
                     expected_preference_revision=None)
    else: value["schema"] = "mastermind.workspace_source_operation_lookup.v1"
    return value


def frame(operation="read", request=None):
    return {"schema": FRAME_SCHEMA, "operation": operation,
            "principal": {"policy_id": "workspace", "issuer_digest": "a" * 64, "subject_digest": "b" * 64,
                          "client_ref": "app", "resource": RESOURCE, "scopes": [SCOPE]},
            "verified_expires_at": 0, "request": lookup() if request is None else request}


@pytest.mark.parametrize("action", list(PREFIX))
@pytest.mark.parametrize("operation", ["prepare", "read", "reconcile", "submit"])
def test_closed_actual_action_families_and_detachment(action, operation):
    selected = lookup(action)
    if operation == "prepare":
        body = {"schema": "adapter-owned", "request_id": selected["request_id"], "goal": "Literal中文\nGoal"}
        if action != "publish_project_proposal": body["work_ref"] = selected["work_ref"]
        request = {"action": action, "request": body}
    elif operation == "submit":
        request = {k: selected[k] for k in ("action", "request_id", "work_ref")}
        request["preview_witness"] = {"recipe_fingerprint_sha256": "e" * 64, "original_input": {
            "schema": "mastermind.terminal_original_input_reference.v1", "input_ref": "terminal-input:" + "f" * 64,
            "artifact_sha256": "1" * 64, "payload_sha256": "2" * 64}}
    else: request = selected
    original = frame(operation, request)
    value = validate_frame(original)
    assert value == original and value is not original and value["principal"] is not original["principal"]
    # Expiry0 is a carried value, never authority or a wire-level clock decision.
    raw = json.dumps(original, ensure_ascii=False).encode()
    assert decode_frame(raw) == original and decode_frame(raw + b"\n") == original


def test_advance_is_exact_adopt_original_witness():
    value = frame("advance", lookup("ADOPT_PLAN") | {
        "schema": "mastermind.workspace_source_operation_advance.v1", "phase_receipt_digest": "3" * 64})
    assert validate_frame(value) == value
    value["request"]["action"] = "publish_project_proposal"
    with pytest.raises(ValueError, match="^invalid_source_operation_frame$"): validate_frame(value)


@pytest.mark.parametrize("change", [
    {"verified_expires_at": True}, {"verified_expires_at": -1}, {"operation": []},
    {"principal": {"signed_in": True}}, {"request": lookup() | {"raw_body": "private"}},
])
def test_private_carrier_rejects_invalid_or_extra_scope_fields(change):
    with pytest.raises(ValueError, match="^invalid_source_operation_frame$"): validate_frame(frame() | change)


@pytest.mark.parametrize("action", ["add_project_file", "set_project_communication_preference"])
def test_knowledge_status_requires_full_original_bodyfree_tuple(action):
    value = lookup(action); del value["request_sha256"]
    with pytest.raises(ValueError): validate_frame(frame(request=value))
    value = lookup(action); value["request_id"] = PREFIX["publish_project_proposal"] + "a" * 40
    with pytest.raises(ValueError): validate_frame(frame(request=value))


@pytest.mark.parametrize("key", ["principal", "verified_expires_at", "operation"])
def test_prepare_cannot_inject_private_carrier_authority(key):
    request = {"action": "publish_project_proposal", "request": {"request_id": PREFIX["publish_project_proposal"] + "a" * 40, key: "fake"}}
    with pytest.raises(ValueError): validate_frame(frame("prepare", request))


def test_duplicate_json_keys_nonfinite_surrogates_and_byte_budget_refuse():
    raw = json.dumps(frame()).encode()
    with pytest.raises(ValueError): decode_frame(raw.replace(b'"verified_expires_at": 0', b'"verified_expires_at": 0, "verified_expires_at": 1'))
    with pytest.raises(ValueError): decode_frame(raw.replace(b'"verified_expires_at": 0', b'"verified_expires_at": NaN'))
    request = {"action": "publish_project_proposal", "request": {"request_id": PREFIX["publish_project_proposal"] + "a" * 40, "goal": "中" * 40000}}
    with pytest.raises(ValueError): validate_frame(frame("prepare", request))
    request["request"]["goal"] = "\ud800"
    with pytest.raises(ValueError): validate_frame(frame("prepare", request))


def test_deep_and_hostile_values_fail_without_coercion():
    touched = []
    class Hostile(dict):
        def items(self): touched.append(True); raise RuntimeError()
    with pytest.raises(ValueError): validate_frame(Hostile())
    assert touched == []
    value = []
    for _ in range(40): value = [value]
    request = {"action": "publish_project_proposal", "request": {"request_id": PREFIX["publish_project_proposal"] + "a" * 40, "deep": value}}
    with pytest.raises(ValueError): validate_frame(frame("prepare", request))


def test_only_closed_bounded_file_prepare_uses_larger_request_envelope():
    from common.workspace_source_operation_wire import operation_request_limit
    body={'schema':'mastermind.project_file_add_request.v1','request_id':PREFIX['add_project_file']+'a'*40,
        'work_ref':'WS:TEST','source_commit':'b'*40,'base_revision':'c'*64,
        'file':{'display_name':'"'*124+'.txt','media_type':'text/plain','content_utf8':'\t'*32768}}
    request={'action':'add_project_file','request':body}
    assert operation_request_limit('prepare',request)==98304
    assert validate_frame(frame('prepare',request))['request']==request
    for changed in [request|{'action':'ADOPT_PLAN'},
                    request|{'request':body|{'extra':'not file authority'}},
                    request|{'request':body|{'file':body['file']|{'content_utf8':'\t'*32769}}}]:
        assert operation_request_limit('prepare',changed)==32768
        with pytest.raises(ValueError):validate_frame(frame('prepare',changed))


def test_other_prepare_stays_at_32k_even_inside_larger_private_carrier():
    request={'action':'publish_project_proposal','request':{'request_id':PREFIX['publish_project_proposal']+'a'*40,
        'goal':'x'*32768}}
    assert len(json.dumps(frame('prepare',request)).encode())<98304
    with pytest.raises(ValueError):validate_frame(frame('prepare',request))
