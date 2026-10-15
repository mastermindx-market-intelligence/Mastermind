"""Legacy planner contracts stay frozen when hierarchy V5 is opted in."""
import copy

import pytest
from jsonschema import Draft202012Validator

from control_plane.claude_operator_helper_protocol import native_plan_contract
from control_plane.executive_orchestration_result import (
    PLAN_SCHEMA_V1, PLAN_SCHEMA_V3, PLAN_SCHEMA_V4, PLAN_SCHEMA_V5,
    OrchestrationResultError, _validate_plan, canonical_digest,
    orchestration_result_schema, role_schema_digest,
)


def body(version=PLAN_SCHEMA_V1):
    return orchestration_result_schema("plan", plan_schema_version=version)["properties"]["role_result"]


def plan(version, count=1):
    steps = []
    for i in range(count):
        step = dict(ordinal=i, step_id=f"STEP-{i}", objective="Read admitted input",
                    business_impact="routine", review_required=False,
                    requested_authorities=["READ"], allowed_write_paths=[],
                    validation_ids=[], attempt_limit=1, cost_class="small")
        if version != PLAN_SCHEMA_V1:
            step["prerequisite_step_ids"] = []
        if version == PLAN_SCHEMA_V3:
            step["placement"] = dict(provider_realm="codex", quota_class="default")
        if version == PLAN_SCHEMA_V5:
            step["delegation"] = None
        steps.append(step)
    result = dict(schema_version=version, root_job_id="ROOT", plan_attempt_id="ATT-1", steps=steps)
    if version == PLAN_SCHEMA_V5:
        result["coordinator_job_id"] = "COORD"
    return result


def typed(value):
    return _validate_plan(value, outer=dict(run_id="ATT-1", expected_root_job_id="ROOT"))


def test_default_v1_schema_and_native_handshake_are_unchanged():
    assert role_schema_digest("plan") == "8413f6b0777e2adceff2a9fd262760bf1d01c5cc92314e6abb5f8dc1079bbbe4"
    assert native_plan_contract() == {
        "name": "executive-plan-v1",
        "schema_digest": "4818e6ad3e14595c8259d0aae289eac793a995f66be5756c5657ac045868e17e",
    }
    assert orchestration_result_schema("plan") == orchestration_result_schema("plan", plan_schema_version=PLAN_SCHEMA_V1)


@pytest.mark.parametrize("version,digest", [
    (PLAN_SCHEMA_V3, "5fc2b4d8a4c52ab281ca8cc07b57cd18e05dc77794bc527eddf1e8a6f6578549"),
    (PLAN_SCHEMA_V4, "56c859db0beaa0df9791163c94cb4cd2bfa28b92b28d2dfe7264c7b22c726e3a"),
])
def test_v3_v4_schema_matches_exact_1315_producer(version, digest):
    # Frozen source comparison: PR1315 c4f2dbda56c8, not a changed golden.
    assert canonical_digest(orchestration_result_schema("plan", plan_schema_version=version)) == digest


@pytest.mark.parametrize("version", [PLAN_SCHEMA_V1, PLAN_SCHEMA_V3, PLAN_SCHEMA_V4])
def test_legacy_producer_refuses_v5_fields_and_ninth_step(version):
    schema = body(version)
    validator = Draft202012Validator(schema)
    value = plan(version)
    validator.validate(value)
    assert typed(value) == value
    assert schema["properties"]["steps"]["maxItems"] == 8
    assert "coordinator_job_id" not in schema["properties"]
    for change in ("coordinator", "delegation", "ninth"):
        bad = copy.deepcopy(value)
        if change == "coordinator": bad["coordinator_job_id"] = "COORD"
        elif change == "delegation": bad["steps"][0]["delegation"] = None
        else: bad = plan(version, 9)
        assert list(validator.iter_errors(bad))
        with pytest.raises(OrchestrationResultError): typed(bad)


def test_explicit_v5_producer_matches_typed_nested_contract():
    value = plan(PLAN_SCHEMA_V5, 16)
    value["steps"][0]["delegation"] = dict(descendant_limit=8, max_depth=3)
    validator = Draft202012Validator(body(PLAN_SCHEMA_V5))
    validator.validate(value)
    assert typed(value) == value
    assert role_schema_digest("plan", plan_schema_version=PLAN_SCHEMA_V5) == canonical_digest(
        orchestration_result_schema("plan", plan_schema_version=PLAN_SCHEMA_V5))
    assert role_schema_digest("plan", plan_schema_version=PLAN_SCHEMA_V5) != role_schema_digest("plan")
    for change in ("missing_parent", "missing_delegation", "review_coordinator", "extra_grant", "seventeenth"):
        bad = copy.deepcopy(value)
        if change == "missing_parent": del bad["coordinator_job_id"]
        elif change == "missing_delegation": del bad["steps"][0]["delegation"]
        elif change == "review_coordinator": bad["steps"][0]["review_required"] = True
        elif change == "extra_grant": bad["steps"][0]["delegation"]["new_root"] = True
        else: bad = plan(PLAN_SCHEMA_V5, 17)
        assert list(validator.iter_errors(bad))
        with pytest.raises(OrchestrationResultError): typed(bad)


@pytest.mark.parametrize("version", [None, True, [], "mastermind.execution_plan/v2", "mastermind.execution_plan/v6"])
def test_unknown_producer_version_refuses_without_fallback(version):
    with pytest.raises(OrchestrationResultError):
        orchestration_result_schema("plan", plan_schema_version=version)


def test_version_selector_cannot_change_another_role_or_bound_root():
    with pytest.raises(OrchestrationResultError):
        orchestration_result_schema("work", plan_schema_version=PLAN_SCHEMA_V5)
    schema = orchestration_result_schema("plan", plan_schema_version=PLAN_SCHEMA_V5, root_job_id="ROOT")
    validator = Draft202012Validator(schema["properties"]["role_result"])
    validator.validate(plan(PLAN_SCHEMA_V5))
    bad = plan(PLAN_SCHEMA_V5)
    bad["root_job_id"] = "OTHER"
    assert list(validator.iter_errors(bad))
