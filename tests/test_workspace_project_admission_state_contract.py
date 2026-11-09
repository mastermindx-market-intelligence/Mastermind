"""Real shared-owner state/capability contract checks; inert DTOs only."""
import inspect
import json
import re

import pytest
from common import executive_workspace_contract as _WORKSPACE
from common import workspace_project_admission_state_contract as contract
OWNER_SOURCE = "real"

WORK_REF = "WS:PROJADMISSION01"
ROOT_JOB_ID = "JOB-42"
SELECTION = {"work_ref": WORK_REF, "root_job_id": ROOT_JOB_ID}
TARGET_REF = "project_admission:" + "7c" * 32
REQUEST_DIGEST = "3f" * 32
EXPIRES_AT = 1893456000000


def _principal(**overrides):
    principal = {
        "policy_id": "policy-current",
        "issuer_digest": "aa" * 32,
        "subject_digest": "bb" * 32,
        "client_ref": "client-ref-1",
        "resource": _WORKSPACE.RESOURCE,
        "scopes": [_WORKSPACE.SCOPE],
    }
    principal.update(overrides)
    return principal


def _frame(**overrides):
    frame = {
        "schema": contract.FRAME_SCHEMA,
        "operation": contract.OPERATION,
        "selection": dict(SELECTION),
        "principal": _principal(),
        "admission_expires_at": EXPIRES_AT,
    }
    frame.update(overrides)
    return frame


def _receipt(**overrides):
    receipt = {
        "schema": contract.RECEIPT_SCHEMA,
        "work_ref": WORK_REF,
        "state": contract.STATE_PAUSED,
        "event_id": 41004,
        "command_id": "cmd-proj-admission-0001",
        "request_digest": REQUEST_DIGEST,
        "committed_at_ms": 1762100000000,
    }
    receipt.update(overrides)
    return receipt


def _capability(**overrides):
    capability = {
        "operation": contract.CAPABILITY_OPERATION,
        "target_ref": TARGET_REF,
        "can_pause": True,
    }
    capability.update(overrides)
    return capability


def _body(**overrides):
    body = {
        "schema": contract.BODY_SCHEMA,
        "selection": dict(SELECTION),
        "availability": contract.AVAILABILITY_AVAILABLE,
        "state": contract.STATE_NOT_SUSPENDED,
        "capability": _capability(),
        "current_receipt": None,
        "reason_codes": [],
    }
    body.update(overrides)
    return body


def _unavailable_body(**overrides):
    body = {
        "schema": contract.BODY_SCHEMA,
        "selection": dict(SELECTION),
        "availability": contract.AVAILABILITY_UNAVAILABLE,
        "state": None,
        "capability": None,
        "current_receipt": None,
        "reason_codes": ["ACCESS_DENIED"],
    }
    body.update(overrides)
    return body


def _bad_frame(frame):
    with pytest.raises(ValueError) as excinfo:
        contract.validate_frame(frame)
    assert str(excinfo.value) == "invalid_input"


_DEFAULT_EXPECTED = object()


def _bad_body(value, expected=_DEFAULT_EXPECTED):
    with pytest.raises(ValueError) as excinfo:
        contract.validate_body(
            value, SELECTION if expected is _DEFAULT_EXPECTED else expected)
    assert str(excinfo.value) == "source_unavailable"


# ---------------------------------------------------------------------------
# module surface
# ---------------------------------------------------------------------------


def test_module_constants_are_frozen():
    assert contract.FRAME_SCHEMA == "mastermind.workspace_project_admission_read.v1"
    assert contract.OPERATION == "project_admission_state"
    assert contract.BODY_SCHEMA == "mastermind.workspace_project_admission_state.v1"
    assert contract.MAX_REQUEST_BYTES == 16384
    assert contract.MAX_RESPONSE_BYTES == 32768
    assert contract.RECEIPT_SCHEMA == "mastermind.workstream_admission_suspension_receipt.v1"
    assert contract.CAPABILITY_OPERATION == "pause_workstream_admission"
    assert contract.TARGET_REF_PREFIX == "project_admission:"
    assert contract.AVAILABILITY_AVAILABLE == "AVAILABLE"
    assert contract.AVAILABILITY_UNAVAILABLE == "UNAVAILABLE"
    assert contract.STATE_NOT_SUSPENDED == "NOT_SUSPENDED"
    assert contract.STATE_PAUSED == "PAUSED"
    assert contract.UNAVAILABLE_REASON_CODES == frozenset({
        "INVALID_INPUT", "ACCESS_DENIED", "SOURCE_UNAVAILABLE",
        "SOURCE_CHANGED", "ROOT_MISMATCH", "OWNER_NOT_READY",
    })


def test_public_surface_is_pure_validator():
    public = {name for name, value in vars(contract).items()
              if not name.startswith("_") and callable(value)}
    assert public == {"selection", "validate_frame", "validate_body"}
    source = inspect.getsource(contract)
    for pattern in (r"\bimport\s+(?:time|datetime)\b", r"\bfrom\s+(?:time|datetime)\b",
                    r"time\.time\s*\(", r"datetime\.", r"utcnow", r"\bnow\s*\("):
        assert re.search(pattern, source) is None


def test_module_binds_installed_owner():
    assert contract._workspace is _WORKSPACE


def test_owner_provenance_is_recorded():
    assert OWNER_SOURCE == "real"


# ---------------------------------------------------------------------------
# selection wrapper
# ---------------------------------------------------------------------------


def test_selection_positive_returns_detached_copy():
    served = contract.selection(dict(SELECTION))
    assert served == SELECTION
    served["work_ref"] = "WS:MUTATED000"
    assert SELECTION["work_ref"] == "WS:PROJADMISSION01"


@pytest.mark.parametrize("value", [
    None, 7, True, ["WS:PROJADMISSION01"],
    {}, {"work_ref": WORK_REF},
    {"work_ref": WORK_REF, "root_job_id": ROOT_JOB_ID, "extra": 1},
    {"work_ref": "ws:projadmission01", "root_job_id": ROOT_JOB_ID},
    {"work_ref": "WORK:PROJADMISSION01", "root_job_id": ROOT_JOB_ID},
    {"work_ref": "WS:", "root_job_id": ROOT_JOB_ID},
    {"work_ref": "WS:A B", "root_job_id": ROOT_JOB_ID},
    {"work_ref": WORK_REF + "\n", "root_job_id": ROOT_JOB_ID},
    {"work_ref": WORK_REF, "root_job_id": "job-42"},
    {"work_ref": WORK_REF, "root_job_id": "JOB-"},
    {"work_ref": WORK_REF, "root_job_id": "JOB-1234567890"},
    {"work_ref": WORK_REF, "root_job_id": "JOB-42\n"},
    {"work_ref": WORK_REF, "root_job_id": 42},
])
def test_selection_rejects_malformed_pairs(value):
    with pytest.raises(ValueError) as excinfo:
        contract.selection(value)
    assert str(excinfo.value) == "invalid_input"


def test_selection_accepts_grammar_boundaries():
    assert contract.selection({"work_ref": "WS:AB", "root_job_id": "JOB-0"}) == {
        "work_ref": "WS:AB", "root_job_id": "JOB-0"}
    long_ref = "WS:" + "A" * 64
    assert contract.selection({"work_ref": long_ref, "root_job_id": "JOB-999999999"})["work_ref"] == long_ref


# ---------------------------------------------------------------------------
# request frame
# ---------------------------------------------------------------------------


def test_frame_positive_returns_detached_json_copy():
    frame = _frame()
    served = contract.validate_frame(frame)
    assert served == frame
    assert served is not frame
    assert served["selection"] is not frame["selection"]
    assert served["principal"] is not frame["principal"]
    served["selection"]["work_ref"] = "WS:MUTATED000"
    served["admission_expires_at"] = -1
    assert frame["selection"]["work_ref"] == "WS:PROJADMISSION01"
    assert frame["admission_expires_at"] == EXPIRES_AT
    assert contract.validate_frame(frame) == frame


def test_frame_accepts_any_valid_selection():
    other = {"work_ref": "WS:OTHERONE1", "root_job_id": "JOB-7"}
    served = contract.validate_frame(_frame(selection=other))
    assert served["selection"] == other


@pytest.mark.parametrize("value", [None, 7, True, "frame", [], {}])
def test_frame_rejects_non_dict(value):
    _bad_frame(value)


@pytest.mark.parametrize("overrides", [
    {"schema": "mastermind.executive_workspace_read.v3"},
    {"schema": None},
    {"operation": "admitted_plan"},
    {"operation": "project_admission"},
    {"operation": None},
    {"schema": contract.FRAME_SCHEMA.upper()},
])
def test_frame_rejects_schema_and_operation_drift(overrides):
    _bad_frame(_frame(**overrides))


@pytest.mark.parametrize("key", ["schema", "operation", "selection", "principal",
                                 "admission_expires_at"])
def test_frame_rejects_missing_keys(key):
    frame = _frame()
    del frame[key]
    _bad_frame(frame)


@pytest.mark.parametrize("extra", [
    {"extra": 1}, {"actor": "claude"}, {"plan": {}},
    {"result": {"ok": True}},
])
def test_frame_rejects_unknown_keys(extra):
    frame = _frame()
    frame.update(extra)
    _bad_frame(frame)


def test_frame_rejects_extra_principal_actor():
    principal = _principal()
    principal["actor"] = "claude"
    _bad_frame(_frame(principal=principal))


@pytest.mark.parametrize("key", ["policy_id", "issuer_digest", "subject_digest",
                                 "client_ref", "resource", "scopes"])
def test_frame_rejects_missing_principal_keys(key):
    principal = _principal()
    del principal[key]
    _bad_frame(_frame(principal=principal))


@pytest.mark.parametrize("principal", [
    _principal(resource="https://mcp.mastermind-x.com/workspace/write"),
    _principal(scopes=[]),
    _principal(scopes=["mastermind.workspace.read", "extra.scope"]),
    _principal(scopes="mastermind.workspace.read"),
    _principal(policy_id=""),
    _principal(policy_id="x" * 257),
    _principal(policy_id=7),
    _principal(issuer_digest=None),
    _principal(client_ref=True),
])
def test_frame_owner_rejection_maps_to_fixed_invalid_input(principal):
    _bad_frame(_frame(principal=principal))


@pytest.mark.parametrize("selection", [
    {}, {"work_ref": WORK_REF}, {"work_ref": WORK_REF, "root_job_id": ROOT_JOB_ID, "job_id": "JOB-42"},
    {"work_ref": "ws:projadmission01", "root_job_id": ROOT_JOB_ID},
    {"work_ref": "WS:PROJADMISSION01 ", "root_job_id": ROOT_JOB_ID},
    {"work_ref": WORK_REF, "root_job_id": None},
    {"work_ref": None, "root_job_id": ROOT_JOB_ID},
    None, 7,
])
def test_frame_rejects_malformed_selection(selection):
    _bad_frame(_frame(selection=selection))


@pytest.mark.parametrize("expires_at", [
    True, False, 0, -1, 1.5, "5", None, EXPIRES_AT + 0.0,
])
def test_frame_rejects_non_positive_bool_or_non_int_expiry(expires_at):
    _bad_frame(_frame(admission_expires_at=expires_at))


def test_frame_rejects_request_over_byte_cap():
    _bad_frame(_frame(admission_expires_at=10 ** 20000))


# ---------------------------------------------------------------------------
# AVAILABLE bodies
# ---------------------------------------------------------------------------


def test_available_not_suspended_positive():
    body = _body()
    payload = contract.validate_body(body, SELECTION)
    assert isinstance(payload, bytes)
    assert payload.endswith(b"\n")
    assert payload.count(b"\n") == 1
    assert len(payload) + 0 <= contract.MAX_RESPONSE_BYTES
    decoded = json.loads(payload.decode("utf-8"))
    assert decoded == {"ok": True, "result": body}


def test_available_paused_positive():
    body = _body(state=contract.STATE_PAUSED,
                 capability=_capability(can_pause=False),
                 current_receipt=_receipt())
    payload = contract.validate_body(body, SELECTION)
    assert json.loads(payload.decode("utf-8")) == {"ok": True, "result": body}


def test_wire_bytes_are_canonical_from_owner():
    body = _body()
    expected = _WORKSPACE.canonical({"ok": True, "result": body}) + b"\n"
    assert contract.validate_body(body, SELECTION) == expected


def test_receipt_accepts_closed_field_boundaries():
    receipt = _receipt(event_id=1, committed_at_ms=0,
                       command_id="a" * 128, request_digest="0" * 64)
    body = _body(state=contract.STATE_PAUSED,
                 capability=_capability(can_pause=False), current_receipt=receipt)
    assert contract.validate_body(body, SELECTION)


@pytest.mark.parametrize("value", [None, 7, True, "body", [], {"ok": True}])
def test_body_rejects_non_dict_or_envelope_shaped_value(value):
    _bad_body(value)


@pytest.mark.parametrize("key", ["schema", "selection", "availability", "state",
                                 "capability", "current_receipt", "reason_codes"])
def test_body_rejects_missing_keys(key):
    body = _body()
    del body[key]
    _bad_body(body)


@pytest.mark.parametrize("extra", [
    {"ok": True}, {"result": 1}, {"plan": None}, {"source_observation": {}},
    {"actor": "claude"},
])
def test_body_rejects_unknown_keys(extra):
    body = _body()
    body.update(extra)
    _bad_body(body)


@pytest.mark.parametrize("schema", [
    "mastermind.workspace_admitted_execution_plan.v1",
    "mastermind.workstream_admission_suspension_receipt.v1",
    None, contract.BODY_SCHEMA.upper(),
])
def test_body_rejects_schema_drift(schema):
    _bad_body(_body(schema=schema))


@pytest.mark.parametrize("overrides", [
    {"selection": {"work_ref": "WS:OTHERONE1", "root_job_id": ROOT_JOB_ID}},
    {"selection": {"work_ref": WORK_REF, "root_job_id": "JOB-43"}},
    {"selection": {"work_ref": "WS:OTHERONE1", "root_job_id": "JOB-43"}},
    {"selection": {"work_ref": "ws:projadmission01", "root_job_id": ROOT_JOB_ID}},
    {"selection": {"work_ref": WORK_REF}},
    {"selection": None},
])
def test_body_rejects_foreign_or_malformed_selection(overrides):
    _bad_body(_body(**overrides))


@pytest.mark.parametrize("expected", [
    None, 7, {}, {"work_ref": WORK_REF},
    {"work_ref": "WS:OTHERONE1", "root_job_id": ROOT_JOB_ID},
    {"work_ref": WORK_REF, "root_job_id": "JOB-43"},
])
def test_body_rejects_mismatched_or_malformed_expected(expected):
    _bad_body(_body(), expected)


@pytest.mark.parametrize("availability", [
    "available", "unavailable", "UNAVAILABLE ", "READY", "", None, True, 1,
])
def test_body_rejects_availability_drift(availability):
    _bad_body(_body(availability=availability))


@pytest.mark.parametrize("reason_codes", [
    ["INVALID_INPUT"], ["ACCESS_DENIED"], "ACCESS_DENIED", None, {}, (),
])
def test_available_rejects_nonempty_or_non_list_reason_codes(reason_codes):
    _bad_body(_body(reason_codes=reason_codes))


@pytest.mark.parametrize("state", [
    None, "RUNNING", "READY", "AUTONOMOUS", "not_suspended", "PAUSED ", "", True, False, 1,
])
def test_available_rejects_state_drift(state):
    _bad_body(_body(state=state))


@pytest.mark.parametrize("capability", [
    None, 7, "capability", True,
    {},
    {"operation": contract.CAPABILITY_OPERATION, "target_ref": TARGET_REF},
    {"operation": contract.CAPABILITY_OPERATION, "can_pause": True},
    {"target_ref": TARGET_REF, "can_pause": True},
    dict(_capability(), actor="claude"),
    dict(_capability(), operation="resume_workstream_admission"),
    dict(_capability(), operation=None),
])
def test_available_rejects_capability_shape_drift(capability):
    _bad_body(_body(capability=capability))


@pytest.mark.parametrize("target_ref", [
    "", "admission:" + "7c" * 32, "project_admission",
    "project_admission:" + "7C" * 32,
    "project_admission:" + "7c" * 31,
    "project_admission:" + "7c" * 33,
    "project_admission:" + "g" * 32,
    "project_admission:" + "7c" * 32 + "\n",
    " project_admission:" + "7c" * 32,
    "project_admission:" + "7c" * 32 + " ",
    None, 7, True,
    "project_admission:" + REQUEST_DIGEST + "7c",
])
def test_available_rejects_malformed_target_ref(target_ref):
    _bad_body(_body(capability=_capability(target_ref=target_ref)))


@pytest.mark.parametrize("can_pause", [1, 0, "true", "false", None, 1.0])
def test_available_rejects_non_bool_can_pause(can_pause):
    _bad_body(_body(capability=_capability(can_pause=can_pause)))


def test_available_rejects_can_pause_polarity_drift():
    _bad_body(_body(state=contract.STATE_NOT_SUSPENDED,
                    capability=_capability(can_pause=False)))
    _bad_body(_body(state=contract.STATE_PAUSED,
                    capability=_capability(can_pause=True),
                    current_receipt=_receipt()))


@pytest.mark.parametrize("receipt", [
    {}, False, 0, "receipt", _receipt(),
])
def test_not_suspended_requires_no_receipt(receipt):
    _bad_body(_body(state=contract.STATE_NOT_SUSPENDED, current_receipt=receipt))


def test_paused_requires_receipt():
    _bad_body(_body(state=contract.STATE_PAUSED,
                    capability=_capability(can_pause=False),
                    current_receipt=None))


# ---------------------------------------------------------------------------
# suspension receipt
# ---------------------------------------------------------------------------


def _paused(**receipt_overrides):
    return _body(state=contract.STATE_PAUSED,
                 capability=_capability(can_pause=False),
                 current_receipt=_receipt(**receipt_overrides))


def _paused_with_receipt(receipt):
    return _body(state=contract.STATE_PAUSED,
                 capability=_capability(can_pause=False),
                 current_receipt=receipt)


@pytest.mark.parametrize("receipt", [
    "receipt", 7, True, [], None,
    {"schema": contract.RECEIPT_SCHEMA},
])
def test_receipt_rejects_non_dict_or_incomplete_shape(receipt):
    _bad_body(_paused_with_receipt(receipt))


@pytest.mark.parametrize("schema", [
    "mastermind.workstream_admission_suspension_receipt.v0",
    "mastermind.workspace_project_admission_state.v1",
    None, contract.RECEIPT_SCHEMA.upper(),
])
def test_receipt_rejects_schema_drift(schema):
    _bad_body(_paused(schema=schema))


@pytest.mark.parametrize("state", [
    "NOT_SUSPENDED", "paused", "PAUSED ", "", None, True, 1,
])
def test_receipt_rejects_state_drift(state):
    _bad_body(_paused(state=state))


@pytest.mark.parametrize("work_ref", [
    "WS:OTHERONE1", "ws:projadmission01", "WS:PROJADMISSION02",
    "", None, 7,
])
def test_receipt_rejects_foreign_work_ref(work_ref):
    _bad_body(_paused(work_ref=work_ref))


@pytest.mark.parametrize("event_id", [0, -1, -41004, True, False, 1.0, "5", None])
def test_receipt_rejects_event_id_drift(event_id):
    _bad_body(_paused(event_id=event_id))


@pytest.mark.parametrize("command_id", [
    "", ".abc", ":abc", "-abc", "a" * 129,
    "has space", "line1\nline2", "bad!char", "cmd#1", "cmd\\id",
    "trailing\n", None, 5, True,
    "cmd-proj-admission-0001\nx",
])
def test_receipt_rejects_command_id_drift(command_id):
    _bad_body(_paused(command_id=command_id))


@pytest.mark.parametrize("request_digest", [
    "", "3F" * 32, "3f" * 31, "3f" * 33, "g" * 64, "3f" * 32 + "\n",
    " 3f" * 1, None, 7, True, REQUEST_DIGEST.upper(),
])
def test_receipt_rejects_request_digest_drift(request_digest):
    _bad_body(_paused(request_digest=request_digest))


@pytest.mark.parametrize("committed_at_ms", [-1, True, False, 1.5, "0", None])
def test_receipt_rejects_committed_at_ms_drift(committed_at_ms):
    _bad_body(_paused(committed_at_ms=committed_at_ms))


@pytest.mark.parametrize("extra", [{"actor": "claude"}, {"event_id_dup": 1}])
def test_receipt_rejects_unknown_keys(extra):
    receipt = _receipt()
    receipt.update(extra)
    _bad_body(_paused_with_receipt(receipt))


@pytest.mark.parametrize("key", ["schema", "work_ref", "state", "event_id",
                                 "command_id", "request_digest", "committed_at_ms"])
def test_receipt_rejects_missing_keys(key):
    receipt = _receipt()
    del receipt[key]
    _bad_body(_paused_with_receipt(receipt))


# ---------------------------------------------------------------------------
# UNAVAILABLE bodies
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("reason", [
    "INVALID_INPUT", "ACCESS_DENIED", "SOURCE_UNAVAILABLE",
    "SOURCE_CHANGED", "ROOT_MISMATCH", "OWNER_NOT_READY",
])
def test_unavailable_positive_each_reason(reason):
    body = _unavailable_body(reason_codes=[reason])
    payload = contract.validate_body(body, SELECTION)
    assert json.loads(payload.decode("utf-8")) == {"ok": True, "result": body}


def test_unavailable_positive_multiple_reasons():
    body = _unavailable_body(reason_codes=["ROOT_MISMATCH", "SOURCE_CHANGED"])
    assert contract.validate_body(body, SELECTION)


@pytest.mark.parametrize("state", [
    "NOT_SUSPENDED", "PAUSED", "RUNNING", False, "", 0,
])
def test_unavailable_rejects_false_state(state):
    _bad_body(_unavailable_body(state=state))


@pytest.mark.parametrize("capability", [
    _capability(), _capability(can_pause=False), True, 0, {},
])
def test_unavailable_rejects_false_capability(capability):
    _bad_body(_unavailable_body(capability=capability))


@pytest.mark.parametrize("receipt", [
    _receipt(), {}, "", False, 0,
])
def test_unavailable_rejects_false_receipt(receipt):
    _bad_body(_unavailable_body(current_receipt=receipt))


@pytest.mark.parametrize("reason_codes", [
    [], None, "ACCESS_DENIED", {}, ("ACCESS_DENIED",), 7,
    ["UNKNOWN_CODE"], ["access_denied"], ["ACCESS_DENIED "],
    [None], [1], [True], ["ACCESS_DENIED", "NOPE"], [["ACCESS_DENIED"]],
])
def test_unavailable_rejects_reason_code_drift(reason_codes):
    _bad_body(_unavailable_body(reason_codes=reason_codes))


# ---------------------------------------------------------------------------
# wire envelope, byte cap, detachment
# ---------------------------------------------------------------------------


def test_body_rejects_response_over_byte_cap():
    _bad_body(_unavailable_body(reason_codes=["ACCESS_DENIED"] * 2500))


def test_body_does_not_mutate_input():
    body = _body()
    snapshot = json.loads(json.dumps(body))
    contract.validate_body(body, SELECTION)
    assert body == snapshot


def test_wire_bytes_detached_from_later_input_mutation():
    body = _body()
    payload = contract.validate_body(body, SELECTION)
    body["state"] = "RUNNING"
    body["capability"]["can_pause"] = False
    body["reason_codes"].append("ACCESS_DENIED")
    decoded = json.loads(payload.decode("utf-8"))
    assert decoded["result"]["state"] == contract.STATE_NOT_SUSPENDED
    assert decoded["result"]["capability"]["can_pause"] is True
    assert decoded["result"]["reason_codes"] == []
    assert contract.validate_body(_body(), SELECTION) == payload


def test_frame_wire_cap_constant_matches_body_response_cap_semantics():
    assert contract.MAX_REQUEST_BYTES == 16384
    assert contract.MAX_RESPONSE_BYTES == 32768
    body = _body()
    payload = contract.validate_body(body, SELECTION)
    assert len(payload) + 1 <= contract.MAX_RESPONSE_BYTES
    assert payload == contract.validate_body(_body(), SELECTION)
