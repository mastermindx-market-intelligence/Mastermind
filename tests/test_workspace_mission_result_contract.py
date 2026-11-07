"""Closed compound Mission/Result grammar. Frozen v1/v2/v3 operations stay closed."""
import pytest

from common.executive_workspace_contract import (
    FRAME_SCHEMA_V2,
    MAX_RESPONSE_BYTES,
    MAX_RESULT_RESPONSE_BYTES,
    RESOURCE,
    RESULT_BODY_SCHEMA,
    SCOPE,
    validate_v2_frame,
)
from common.executive_workspace_mission_result_contract import (
    BODY_SCHEMA,
    COMPOUND_REFUSAL_REASONS,
    FRAME_SCHEMA,
    MAX_COMPOUND_RESPONSE_BYTES,
    MAX_NESTED_RESULT_RESPONSE_BYTES,
    MISSION_SCHEMA,
    OPERATION,
    compound_envelope_fits,
    nested_result_envelope_fits,
    selection,
    unavailable_body,
    validate_body,
    validate_frame,
)
from integrations.mastermind_workspace_app import contract as app_contract

SELECTION = {
    "work_ref": "WS:ONE",
    "root_job_id": "JOB-001",
    "job_id": "JOB-002",
    "attempt_id": "ATT-" + "ab" * 16,
    "result_envelope_digest": "cd" * 32,
}


def _principal():
    return {
        "policy_id": "workspace-test",
        "issuer_digest": "a" * 64,
        "subject_digest": "b" * 64,
        "client_ref": "fixture-web",
        "resource": RESOURCE,
        "scopes": [SCOPE],
    }


def _frame(**overrides):
    value = {
        "schema": FRAME_SCHEMA,
        "operation": OPERATION,
        "selection": dict(SELECTION),
        "principal": _principal(),
    }
    value.update(overrides)
    return value


def _available_body():
    return {
        "schema": BODY_SCHEMA,
        "selection": dict(SELECTION),
        "availability": "AVAILABLE",
        "reason_codes": [],
        "mission": {"schema": MISSION_SCHEMA},
        "role_result": {"schema": RESULT_BODY_SCHEMA},
    }


def test_frame_reuses_the_five_field_result_selector():
    frame = validate_frame(_frame())
    assert frame["schema"] == "mastermind.executive_workspace_mission_result_read.v1"
    assert frame["operation"] == "mission_result"
    assert set(frame) == {"schema", "operation", "selection", "principal"}
    assert selection(frame["selection"]) == {
        "attempt_id": SELECTION["attempt_id"],
        "job_id": SELECTION["job_id"],
        "result_envelope_digest": SELECTION["result_envelope_digest"],
        "root_job_id": SELECTION["root_job_id"],
        "work_ref": SELECTION["work_ref"],
    }
    assert app_contract.MISSION_RESULT_FRAME_SCHEMA == FRAME_SCHEMA
    assert app_contract.MISSION_RESULT_BODY_SCHEMA == BODY_SCHEMA
    assert app_contract.MAX_NESTED_RESULT_RESPONSE_BYTES == MAX_RESULT_RESPONSE_BYTES == 16384
    assert app_contract.MAX_COMPOUND_RESPONSE_BYTES == MAX_RESPONSE_BYTES == 2_000_000


def test_v2_grammar_rejects_the_compound_operation():
    foreign = _frame(schema=FRAME_SCHEMA_V2, operation="mission_result")
    with pytest.raises(ValueError):
        validate_v2_frame(foreign)
    with pytest.raises(ValueError):
        validate_frame(_frame(operation="result"))
    with pytest.raises(ValueError):
        validate_frame(_frame(schema=FRAME_SCHEMA_V2))
    two_field = {key: SELECTION[key] for key in ("work_ref", "root_job_id")}
    with pytest.raises(ValueError):
        selection(two_field)
    extra = _frame()
    extra["note"] = "extra"
    with pytest.raises(ValueError):
        validate_frame(extra)


def test_available_body_requires_both_documents_and_empty_reasons():
    body = validate_body(_available_body())
    assert body["availability"] == "AVAILABLE"
    assert body["reason_codes"] == []
    half = _available_body()
    half["mission"] = None
    with pytest.raises(ValueError):
        validate_body(half)
    labeled = _available_body()
    labeled["reason_codes"] = ["SOURCE_UNAVAILABLE"]
    with pytest.raises(ValueError):
        validate_body(labeled)
    bare = _available_body()
    bare["role_result"] = {"schema": "mastermind.fabric_role_result_view.v1"}
    with pytest.raises(ValueError):
        validate_body(bare)


@pytest.mark.parametrize("reason", sorted(COMPOUND_REFUSAL_REASONS))
def test_unavailable_discards_both_documents(reason):
    body = validate_body(unavailable_body(SELECTION, reason))
    assert body["availability"] == "UNAVAILABLE"
    assert body["reason_codes"] == [reason]
    assert body["mission"] is None and body["role_result"] is None
    leaked = unavailable_body(SELECTION, reason)
    leaked["role_result"] = {"schema": RESULT_BODY_SCHEMA}
    with pytest.raises(ValueError):
        validate_body(leaked)


def test_compound_reasons_reject_content_omission_and_duplicates():
    with pytest.raises(ValueError):
        unavailable_body(SELECTION, "CONTENT_OVER_BUDGET")
    with pytest.raises(ValueError):
        unavailable_body(SELECTION, ["SOURCE_UNAVAILABLE", "SOURCE_UNAVAILABLE"])
    with pytest.raises(ValueError):
        unavailable_body(SELECTION, [])


def test_nested_result_ceiling_is_independent_of_the_compound_ceiling():
    oversized = {"schema": RESULT_BODY_SCHEMA, "pad": "漢" * 6000}
    assert nested_result_envelope_fits(oversized) is False
    compound = {
        "schema": BODY_SCHEMA,
        "selection": dict(SELECTION),
        "availability": "UNAVAILABLE",
        "reason_codes": ["RESPONSE_OVER_BUDGET"],
        "mission": None,
        "role_result": oversized,
    }
    assert compound_envelope_fits(compound) is True
    assert len("漢" * 6000) * 3 < MAX_COMPOUND_RESPONSE_BYTES
    too_wide = {"pad": "x" * (MAX_COMPOUND_RESPONSE_BYTES + 8)}
    assert compound_envelope_fits(too_wide) is False
    assert nested_result_envelope_fits({"schema": RESULT_BODY_SCHEMA, "pad": "ok"}) is True
