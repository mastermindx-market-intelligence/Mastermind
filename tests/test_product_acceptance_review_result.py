"""Opt-in provider proof output preserves the ordinary review schema."""

import copy
import pytest
from jsonschema import Draft202012Validator

from control_plane.executive_orchestration_result import (
    OrchestrationResultError,
    _validate_review,
    orchestration_result_schema,
    product_acceptance_review_result_schema,
    role_schema_digest,
)
from tests.test_product_acceptance_review_proof import proof


def body():
    return {
        "schema_version": "mastermind.review_result/v2",
        "root_job_id": "JOB-root",
        "plan_attempt_id": "ATT-plan",
        "plan_digest": "1" * 64,
        "plan_step_id": "step-1",
        "reviewed_job_id": "JOB-subject",
        "reviewed_attempt_id": "ATT-subject",
        "reviewed_result_digest": "2" * 64,
        "repair_round": 0,
        "verdict": "approve",
        "evidence_digests": [],
        "findings": [],
        "product_acceptance_proof": proof(),
    }


def schema():
    return product_acceptance_review_result_schema(
        job_id="JOB-review",
        run_id="ATT-review",
        worker_id="worker-review",
        root_job_id="JOB-root",
        expected_basis_digest="a" * 64,
        expected_criterion_digests=("b" * 64,),
        expected_obligation_digests=("d" * 64, "e" * 64),
    )


def test_default_review_provider_schema_is_byte_compatible():
    assert (
        role_schema_digest("review")
        == "a0e853358f325d95b9d94c61161c40e7e7bae67e44679614b5ebea229b3d102c"
    )
    ordinary = orchestration_result_schema("review")["properties"]["role_result"]
    assert ordinary["properties"]["schema_version"] == {
        "const": "mastermind.review_result/v1"
    }
    assert "product_acceptance_proof" not in ordinary["properties"]


def test_opt_in_actual_provider_schema_binds_every_proof_identity():
    selected = schema()["properties"]["role_result"]
    Draft202012Validator.check_schema(selected)
    assert Draft202012Validator(selected).is_valid(body())
    for change in [
        "wrong_basis",
        "missing_obligation",
        "wrong_obligation",
        "extra_verdict",
    ]:
        value = body()
        if change == "wrong_basis":
            value["product_acceptance_proof"]["acceptance_basis_digest"] = "9" * 64
        elif change == "missing_obligation":
            value["product_acceptance_proof"]["obligations"].pop()
        elif change == "wrong_obligation":
            value["product_acceptance_proof"]["obligations"][0]["obligation_digest"] = (
                "9" * 64
            )
        else:
            value["product_acceptance_proof"]["accepted"] = True
        assert not Draft202012Validator(selected).is_valid(value), change


def test_canonical_v2_review_retains_unproven_product_data_without_accepting():
    value = body()
    value["product_acceptance_proof"]["obligations"][1]["state"] = "UNPROVEN"
    assert _validate_review(value, outer_errors=[]) == value
    assert "accepted" not in _validate_review(value, outer_errors=[])


def test_generic_v1_cannot_smuggle_the_new_proof_facet():
    value = body()
    value["schema_version"] = "mastermind.review_result/v1"
    with pytest.raises(OrchestrationResultError):
        _validate_review(value, outer_errors=[])


def test_v2_is_not_canonical_without_its_closed_proof():
    value = body()
    del value["product_acceptance_proof"]
    with pytest.raises(OrchestrationResultError):
        _validate_review(value, outer_errors=[])


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_criterion_digests", ()),
        ("expected_obligation_digests", ("d" * 64,) * 65),
    ],
)
def test_provider_schema_refuses_unsupported_bounded_identity_counts(field, value):
    args = dict(
        job_id="JOB-review",
        run_id="ATT-review",
        worker_id="worker-review",
        root_job_id="JOB-root",
        expected_basis_digest="a" * 64,
        expected_criterion_digests=("b" * 64,),
        expected_obligation_digests=("d" * 64,),
    )
    args[field] = value
    with pytest.raises(OrchestrationResultError):
        product_acceptance_review_result_schema(**args)
