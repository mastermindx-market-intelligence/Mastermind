"""Closed consumers of the actual original-input help read fixture.

The fixture was emitted by the real owner positive in
test_project_execution_help_read.py. It is data for decoder tests, never an
authorization input or a replacement for the original owner proof.
"""
import copy
import json
from pathlib import Path

import pytest

from common import coo_project_help_contract as wire


@pytest.fixture
def observed():
    return json.loads((Path(__file__).parent / "fixtures/project-execution-help-owner.json").read_bytes())


def validate(value, expected):
    return wire.validate_result(value, expected_context=expected["principal_context"],
        capability_profile_digest=expected["capability_profile_digest"],
        expected_workspace_principal=expected["workspace_principal"], expected_scope=expected["scope"])


def test_actual_execution_read_fixture_keeps_separate_source_and_input_identities(observed):
    value = validate(observed, observed)
    assert value == observed and value is not observed
    assert wire.decode(wire.encode(value)) == value
    assert value["schema"] == wire.EXECUTION_RESULT_SCHEMA
    assert value["observation"]["mission"]["mission_read_state"] == "PARTIAL"
    assert value["execution_authority"] is value["native_origin_attested"] is False
    original = value["original_execution"]
    assert original["execution_authorized"] is False
    assert original["original_source_plan"] == value["scope"]["source_plan"]
    assert original["current_adoption"]["project_plan_sha256"] == value["observation"]["project_plan_sha256"]
    assert wire.EXECUTION_RESULT_SCHEMA in wire.render(value)
    copied = copy.deepcopy(value)
    copied["original_execution"]["input_payload_sha256"] = "0" * 64
    # Structurally valid evidence remains a different read. Decoder acceptance
    # alone is deliberately not proof that this changed input exists.
    assert wire.read_identity(copied) != wire.read_identity(value)


@pytest.mark.parametrize("fault", ["missing_witness", "v1_with_witness", "wrong_root", "wrong_plan",
    "wrong_current_plan", "promoted_mission", "wrong_qualifier", "extra_private_bytes",
    "numeric_false", "true_authority"])
def test_execution_read_cannot_be_spliced_promoted_or_used_as_legacy(observed, fault):
    value = copy.deepcopy(observed)
    if fault == "missing_witness":
        del value["original_execution"]
    elif fault == "v1_with_witness":
        value["schema"] = wire.RESULT_SCHEMA
    elif fault == "wrong_root":
        value["original_execution"]["selection"]["root_job_id"] = "JOB-999999"
    elif fault == "wrong_plan":
        value["original_execution"]["original_source_plan"]["contract_sha256"] = "0" * 64
    elif fault == "wrong_current_plan":
        value["original_execution"]["current_adoption"]["project_plan_sha256"] = "0" * 64
    elif fault == "promoted_mission":
        value["observation"]["mission"]["mission_read_state"] = "CURRENT"
    elif fault == "wrong_qualifier":
        value["observation"]["mission"]["qualification"] = "CURRENT_DATA_CARD_WITH_UNOBSERVED_DISPATCH"
    elif fault == "extra_private_bytes":
        value["original_execution"]["private_request"] = "not public evidence"
    elif fault == "numeric_false":
        value["original_execution"]["execution_authorized"] = 0
    else:
        value["original_execution"]["execution_authorized"] = True
    with pytest.raises(ValueError):
        validate(value, observed)


def test_omitted_input_witness_keeps_the_existing_v1_constructor(observed):
    mission = copy.deepcopy(observed["observation"]["mission"])
    mission["qualification"] = "CURRENT_DATA_CARD_WITH_UNOBSERVED_DISPATCH"
    value = wire.result(principal_context=observed["principal_context"],
        capability_profile_digest=observed["capability_profile_digest"],
        workspace_principal=observed["workspace_principal"], selected_scope=observed["scope"],
        mission_identity=observed["observation"]["mission_owner_sha256"],
        plan_identity=observed["observation"]["project_plan_sha256"], mission_read=mission,
        targets=observed["targets"])
    assert value["schema"] == wire.RESULT_SCHEMA and "original_execution" not in value
    assert validate(value, observed) == value
    # This is a legacy constructor/decoder check only. It grants nothing to a
    # resource Mission, which the actual owner tests separately keep refused.
