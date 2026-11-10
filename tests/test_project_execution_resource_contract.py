"""Closed syntax tests using output captured from the actual owner proof.

The fixture is read evidence, never a source of runtime authority. The reached
owner test separately proves its original DATA/admission/Runtime producers.
"""
import copy
import json
from pathlib import Path

import pytest

from common.project_execution_resource_contract import validate_history, validate_resource


def _fixture():
    return json.loads((Path(__file__).parent / "fixtures/project-execution-resource-owner.json").read_text())


def test_real_owner_fixture_retains_full_history_and_explicit_scope():
    value = _fixture()
    resource = value["mission"]["source"]["owner_observation"]["resource"]
    assert validate_resource(resource, **value["selection"]) is resource
    history = next(item["root_history"] for item in value["programs"]["canonical_projects"]
        if item["work_ref"] == value["selection"]["work_ref"])
    assert validate_history(history, work_ref=history["work_ref"]) is history
    assert history["roots"] == resource["history"]["roots"]


@pytest.mark.parametrize("fault", ["boolean_after", "unsafe_integer", "identity_control", "identity_oversize",
    "unknown_kind", "unknown_status", "duplicate_root", "unbound_snapshot"])
def test_history_closed_shape_refuses_mixed_or_malformed_read_evidence(fault):
    value = _fixture()["mission"]["source"]["owner_observation"]["resource"]["history"]
    observation = value["observation"]
    if fault == "boolean_after":
        observation.update(before=1, after=True)
    elif fault == "unsafe_integer":
        observation.update(before=2**53, after=2**53)
    elif fault == "identity_control":
        observation["source_identity"] = "actual\nsource"
    elif fault == "identity_oversize":
        observation["source_identity"] = "a" * 257
    elif fault == "unknown_kind":
        value["roots"][0]["kind"] = "INFERRED_FROM_TITLE"
    elif fault == "unknown_status":
        value["roots"][0]["status"] = []
    elif fault == "duplicate_root":
        value["roots"].append(copy.deepcopy(value["roots"][0]))
    else:
        observation["snapshot_digest"] = "0" * 64
    with pytest.raises(ValueError):
        validate_history(value, work_ref=value["work_ref"])


@pytest.mark.parametrize("fault", ["planning_as_execution", "spliced_identity", "input_claim", "adoption_claim", "execution_claim"])
def test_resource_does_not_turn_history_or_unread_sources_into_execution_authority(fault):
    value = _fixture()
    resource = value["mission"]["source"]["owner_observation"]["resource"]
    if fault == "planning_as_execution":
        resource["selection"]["root_job_id"] = resource["history"]["roots"][0]["root_job_id"]
        value["selection"] = copy.deepcopy(resource["selection"])
    elif fault == "spliced_identity":
        resource["original_execution"]["source_sha256"] = "0" * 64
    elif fault == "input_claim":
        resource["original_input"] = {"state": "AVAILABLE", "reason": None}
    elif fault == "adoption_claim":
        resource["current_adoption"] = {"state": "MATCHES_ORIGINAL", "reason": None}
    else:
        resource["execution_authorized"] = True
    with pytest.raises(ValueError):
        validate_resource(resource, **value["selection"])


@pytest.mark.parametrize("invalid", [0, 0.0, None, "false", []])
def test_resource_authority_flag_requires_the_actual_false_boolean(invalid):
    value = _fixture()
    resource = value["mission"]["source"]["owner_observation"]["resource"]
    resource["execution_authorized"] = invalid
    with pytest.raises(ValueError):
        validate_resource(resource, **value["selection"])
