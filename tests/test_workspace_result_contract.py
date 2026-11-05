"""Frozen v2 frame validation, selector grammar, and operation-specific ceiling.

These tests are pure-contract checks — no auth, no Runtime, no fixture
ownership.  They pin the closed selection grammar for ``result`` and
``mission_v3`` operations, the v2 frame schema name, and the per-operation
response ceilings.
"""
from __future__ import annotations

import pytest

from integrations.mastermind_workspace_app import contract


def test_v2_frame_schema_constant_is_frozen():
    assert contract.FRAME_SCHEMA_V2 == "mastermind.executive_workspace_read.v2"


def test_result_constants_match_contract():
    assert contract.RESULT_BODY_SCHEMA == "mastermind.workspace_role_result.v1"
    assert contract.RESULT_OBSERVATION_SCHEMA == "mastermind.workspace_result_observation.v1"
    assert contract.PROJECTION_SCHEMA == "mastermind.fabric_role_result_view.v1"
    assert contract.MAX_RESULT_RESPONSE_BYTES == 16_384


def test_response_ceiling_for_returns_closed_values():
    assert contract.response_ceiling_for("result") == 16_384
    # Mission v3 retains the existing 2,000,000-byte Workspace response budget.
    assert contract.response_ceiling_for("mission_v3") == contract.MAX_RESPONSE_BYTES
    # Unknown / v1 operations fall back to the existing Mission ceiling; they
    # never widen into the result ceiling.
    assert contract.response_ceiling_for("programs") == contract.MAX_RESPONSE_BYTES
    assert contract.response_ceiling_for("mission") == contract.MAX_RESPONSE_BYTES


@pytest.mark.parametrize("field,value", [
    ("work_ref", "WS:A1"),
    ("work_ref", "WS:ABC.def-XYZ_42"),
    ("root_job_id", "JOB-1"),
    ("root_job_id", "JOB-999999999"),
    ("job_id", "JOB-7"),
    ("attempt_id", "ATT-" + "0" * 32),
    ("attempt_id", "ATT-" + "f" * 32),
    ("result_envelope_digest", "0" * 64),
    ("result_envelope_digest", "abcdef" + "0" * 58),
])
def test_v2_selection_accepts_closed_tokens(field, value):
    selection = {
        "work_ref": "WS:AA1", "root_job_id": "JOB-1", "job_id": "JOB-1",
        "attempt_id": "ATT-" + "0" * 32, "result_envelope_digest": "0" * 64,
    }
    selection[field] = value
    out = contract.v2_selection(selection, "result")
    assert out[field] == value


@pytest.mark.parametrize("field,bad", [
    ("work_ref", "ws:abc"),                  # lower-case prefix refused
    ("work_ref", "WS:"),                     # missing token
    ("work_ref", "WS:1toolong" * 5),         # exceeds 64 chars
    ("root_job_id", "JOB"),                  # missing numeric tail
    ("root_job_id", "JOB-1234567890"),       # exceeds 9 digits
    ("job_id", "job-1"),                     # lower-case prefix refused
    ("attempt_id", "ATT-" + "G" * 32),       # not lowercase hex
    ("attempt_id", "att-" + "0" * 32),       # lower-case prefix refused
    ("attempt_id", "ATT-" + "0" * 31),       # too short
    ("result_envelope_digest", "F" * 64),    # not lowercase hex
    ("result_envelope_digest", "0" * 63),    # too short
    ("result_envelope_digest", "0" * 65),    # too long
])
def test_v2_selection_refuses_malformed_tokens(field, bad):
    selection = {
        "work_ref": "WS:AA1", "root_job_id": "JOB-1", "job_id": "JOB-1",
        "attempt_id": "ATT-" + "0" * 32, "result_envelope_digest": "0" * 64,
    }
    selection[field] = bad
    with pytest.raises(ValueError, match="invalid_input"):
        contract.v2_selection(selection, "result")


def test_v2_selection_refuses_extra_or_missing_field_for_result():
    base = {
        "work_ref": "WS:AA1", "root_job_id": "JOB-1", "job_id": "JOB-1",
        "attempt_id": "ATT-" + "0" * 32, "result_envelope_digest": "0" * 64,
    }
    with pytest.raises(ValueError, match="invalid_input"):
        contract.v2_selection({**base, "extra": "x"}, "result")
    broken = {k: v for k, v in base.items() if k != "job_id"}
    with pytest.raises(ValueError, match="invalid_input"):
        contract.v2_selection(broken, "result")


def test_v2_selection_refuses_mission_v3_extra_field():
    base = {"work_ref": "WS:AA1", "root_job_id": "JOB-1"}
    with pytest.raises(ValueError, match="invalid_input"):
        contract.v2_selection({**base, "job_id": "JOB-2"}, "mission_v3")


def test_v2_selection_unknown_operation_refuses():
    with pytest.raises(ValueError, match="invalid_input"):
        contract.v2_selection({"work_ref": "WS:AA1", "root_job_id": "JOB-1"}, "programs")


def test_validate_v2_frame_accepts_well_formed_result_frame():
    principal = {"policy_id": "p", "issuer_digest": "0" * 64, "subject_digest": "1" * 64,
                 "client_ref": "fixture-web", "resource": contract.RESOURCE,
                 "scopes": [contract.SCOPE]}
    frame = contract.validate_v2_frame({
        "schema": contract.FRAME_SCHEMA_V2,
        "operation": "result",
        "selection": {
            "work_ref": "WS:AA1", "root_job_id": "JOB-1", "job_id": "JOB-1",
            "attempt_id": "ATT-" + "0" * 32, "result_envelope_digest": "0" * 64,
        },
        "principal": principal,
    })
    assert frame["schema"] == contract.FRAME_SCHEMA_V2


def test_validate_v2_frame_refuses_v1_schema():
    principal = {"policy_id": "p", "issuer_digest": "0" * 64, "subject_digest": "1" * 64,
                 "client_ref": "fixture-web", "resource": contract.RESOURCE,
                 "scopes": [contract.SCOPE]}
    with pytest.raises(ValueError, match="invalid_input"):
        contract.validate_v2_frame({
            "schema": contract.FRAME_SCHEMA,  # v1 — refused on the v2 path
            "operation": "result",
            "selection": {"work_ref": "WS:AA1", "root_job_id": "JOB-1"},
            "principal": principal,
        })


def test_validate_v2_frame_refuses_wrong_principal_resource():
    principal = {"policy_id": "p", "issuer_digest": "0" * 64, "subject_digest": "1" * 64,
                 "client_ref": "fixture-web", "resource": "https://other/workspace",
                 "scopes": [contract.SCOPE]}
    with pytest.raises(ValueError, match="invalid_input"):
        contract.validate_v2_frame({
            "schema": contract.FRAME_SCHEMA_V2,
            "operation": "mission_v3",
            "selection": {"work_ref": "WS:AA1", "root_job_id": "JOB-1"},
            "principal": principal,
        })


def test_validate_v2_frame_refuses_extra_principal_field():
    principal = {"policy_id": "p", "issuer_digest": "0" * 64, "subject_digest": "1" * 64,
                 "client_ref": "fixture-web", "resource": contract.RESOURCE,
                 "scopes": [contract.SCOPE], "extra": "x"}
    with pytest.raises(ValueError, match="invalid_input"):
        contract.validate_v2_frame({
            "schema": contract.FRAME_SCHEMA_V2,
            "operation": "mission_v3",
            "selection": {"work_ref": "WS:AA1", "root_job_id": "JOB-1"},
            "principal": principal,
        })

@pytest.mark.parametrize('size',[16383,16384,16385])
def test_socket_boundary_counts_whole_envelope_and_newline(size):
    envelope={'ok':True,'result':{'text':'漢'}}
    envelope['result']['text'] += 'x'*(size-len(contract.canonical(envelope))-1)
    assert len(contract.canonical(envelope))+1 == size
    if size <=16384:
        assert len(contract.bounded_canonical(envelope,limit=16383))+1 == size
    else:
        with pytest.raises(ValueError):contract.bounded_canonical(envelope,limit=16383)
