"""Inert source-contract checks: no production collector or runtime is opened."""
import copy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from common import executive_workspace_contract as workspace
from common import workspace_autonomy_read_contract as wire
from control_plane.executive_autonomy import StatusEvidence
from control_plane.executive_coo_policy import CooCyclePolicy
from control_plane.workspace_autonomy_read import (
    compose_autonomy_policy_read, project_host_autonomy_status,
)
from ops.executive_os.autonomy_control import ProductionStatusHost, StatusSnapshot

SELECTED = {"work_ref": "WS:ONE", "root_job_id": "JOB-1"}
NOW = datetime(2026, 11, 3, 12, tzinfo=UTC)


def plan_body():
    policy = CooCyclePolicy.load()
    observation = {"schema": workspace.PLAN_OBSERVATION_SCHEMA,
        "selection": dict(SELECTED), "state": "SAME",
        "runtime": {"schema": "mastermind.runtime_read_observation.v1", "state": "SAME",
                    "source_identity": "a" * 32, "before": 5, "after": 5},
        "control_room": {"instance_before": "owner1", "instance_after": "owner1",
            "publication_before": 7, "publication_after": 7,
            "document_digest": "a" * 64, "source_validity_digest": "b" * 64,
            "cache_currentness_digest": "c" * 64}}
    return {"schema": workspace.PLAN_BODY_SCHEMA, "selection": dict(SELECTED),
        "availability": "AVAILABLE", "reason_codes": [], "source_observation": observation,
        "plan": {"schema": "mastermind.admitted_execution_plan_view.v1",
            "root_job_id": "JOB-1", "plan_attempt_id": "ATT-one", "policy_sha": policy.policy_sha256,
            "plan_digest": "d" * 64, "reservation_digest": "e" * 64,
            "plan_schema_version": "mastermind.execution_plan/v1",
            "admission_schema_version": "mastermind.coo_plan_admission/v1",
            "admission_state": "ADMITTED", "steps": []}}, policy


def frame():
    principal = {key: "fixture" for key in workspace.PRINCIPAL_KEYS}
    principal.update(resource=workspace.RESOURCE, scopes=[workspace.SCOPE])
    return {"schema": wire.FRAME_SCHEMA, "operation": "autonomy",
            "selection": dict(SELECTED), "principal": principal}


def snapshot(**changes):
    evidence = StatusEvidence(transaction_present=False, control_armed=True, worker_armed=True,
        receipt_state="ARMED", receipt_matches=True, config_drift=False, identity_reconciled=True,
        service_state="READY", readiness_expires_at=NOW + timedelta(hours=1))
    return StatusSnapshot(expected_sha="a" * 40, installed_sha="a" * 40,
        control_config_sha256="b" * 64, worker_config_sha256="c" * 64,
        evidence=replace(evidence, **changes))


def test_frame_reuses_the_exact_incumbent_principal_and_selection():
    value = frame()
    assert wire.validate_frame(value) is value
    assert value["schema"] == wire.FRAME_SCHEMA
    for mutate in (
        lambda f: f["principal"].update(scopes=[workspace.SCOPE, "mastermind.executive.intent.submit"]),
        lambda f: f["principal"].update(resource="foreign"),
        lambda f: f.update(operation="pause"),
        lambda f: f["selection"].update(root_job_id="latest"),
        lambda f: f.update(path="/private/held"),
    ):
        changed = copy.deepcopy(value)
        mutate(changed)
        with pytest.raises(ValueError):
            wire.validate_frame(changed)


def test_real_policy_projection_retains_root_digest_source_and_no_grant():
    body, policy = plan_body()
    result = compose_autonomy_policy_read(body, policy)
    assert result["policy"]["scope"] == "ADMITTED_ROOT"
    assert result["policy"]["limits"] == policy.to_dict()
    assert result["policy"]["source_sha256"] == policy.source_sha256
    assert result["source_observation"] == body["source_observation"]
    assert set(result["policy"]) == {"scope", "policy_sha", "source_sha256", "plan_digest",
                                     "reservation_digest", "limits"}
    body["source_observation"]["runtime"]["after"] = 99
    assert result["source_observation"]["runtime"]["after"] == 5


@pytest.mark.parametrize("mutate", [
    lambda b: b["plan"].update(root_job_id="JOB-2"),
    lambda b: b["plan"].update(policy_sha="f" * 64),
    lambda b: b["plan"].update(admission_state="QUEUED"),
    lambda b: b.update(availability="UNAVAILABLE"),
    lambda b: b["source_observation"]["runtime"].update(after=6),
    lambda b: b["source_observation"]["control_room"].update(publication_after=8),
    lambda b: b["source_observation"].update(state="UNKNOWN"),
    lambda b: b["plan"].update(plan_schema_version="mastermind.execution_plan/v99"),
    lambda b: b["plan"].update(admission_schema_version="mastermind.coo_plan_admission/v2"),
])
def test_foreign_or_unclosed_source_is_not_a_policy_read(mutate):
    body, policy = plan_body()
    mutate(body)
    with pytest.raises(ValueError, match="AUTONOMY_SOURCE_INVALID"):
        compose_autonomy_policy_read(body, policy)


def test_policy_object_does_not_bypass_its_digest_or_type():
    body, policy = plan_body()
    for altered in (replace(policy, max_depth=policy.max_depth + 1),
                    replace(policy, max_depth=True),
                    replace(policy, source_sha256="not-a-digest"), object()):
        with pytest.raises(ValueError, match="AUTONOMY_SOURCE_INVALID"):
            compose_autonomy_policy_read(body, altered)


def test_response_over_budget_is_not_silently_truncated():
    body, policy = plan_body()
    body["source_observation"]["control_room"].update(instance_before="x" * 32768,
                                                      instance_after="x" * 32768)
    with pytest.raises(ValueError, match="AUTONOMY_SOURCE_INVALID"):
        compose_autonomy_policy_read(body, policy)


@pytest.mark.parametrize("changes,status", [
    ({}, "ARMED_READY"),
    ({"transaction_present": True, "config_drift": True}, "TRANSACTION_INCOMPLETE"),
    ({"config_drift": True, "identity_reconciled": False}, "CONFIG_DRIFT"),
    ({"identity_reconciled": False}, "EFFECT_UNKNOWN"),
    ({"readiness_expires_at": NOW - timedelta(seconds=1)}, "READINESS_EXPIRED"),
    ({"service_state": "DEGRADED"}, "ARMED_DEGRADED"),
    ({"control_armed": False, "worker_armed": False, "receipt_state": "DISARMED"}, "UNARMED"),
])
def test_host_status_keeps_original_unsafe_precedence_without_collecting(changes, status):
    with patch.object(ProductionStatusHost, "collect_status", side_effect=AssertionError("held host")):
        result = project_host_autonomy_status(snapshot(**changes), expected_sha="a" * 40, observed_at=NOW)
    assert result["scope"] == "HOST"
    assert result["status"]["status"] == status
    assert "project_paused" not in result
    assert result["observed_at"] == NOW.isoformat()


def test_host_snapshot_requires_explicit_clock_identity_and_safe_fields():
    cases = [
        (snapshot(), "b" * 40, NOW),
        (snapshot(), "a" * 40, NOW.replace(tzinfo=None)),
        (replace(snapshot(), refusal_code="private raw details\npassword"), "a" * 40, NOW),
        (snapshot(control_armed=1), "a" * 40, NOW),
        (snapshot(readiness_expires_at=NOW.replace(tzinfo=None)), "a" * 40, NOW),
    ]
    for current, expected, now in cases:
        with pytest.raises(ValueError, match="AUTONOMY_SOURCE_INVALID"):
            project_host_autonomy_status(current, expected_sha=expected, observed_at=now)


def test_unavailable_is_explicit_and_has_no_policy_or_observation():
    value = wire.unavailable(SELECTED, "POLICY_MISMATCH")["result"]
    assert value["availability"] == "UNAVAILABLE"
    assert value["policy"] is None and value["source_observation"] is None
    with pytest.raises(ValueError):
        wire.unavailable(SELECTED, "READY")


@pytest.mark.parametrize("plan_version,admission_version,policy_version,count", [
    (5, 2, 2, 0), (4, 3, 1, 0),
    (5, 3, 1, 0), (4, 2, 2, 0),
    (5, 3, 2, 17), (4, 2, 1, 9),
])
def test_policy_view_keeps_exact_version_policy_pair_and_step_bound(
        plan_version, admission_version, policy_version, count):
    body, _ = plan_body()
    policy = CooCyclePolicy.load(version=policy_version)
    body["plan"].update(
        plan_schema_version=f"mastermind.execution_plan/v{plan_version}",
        admission_schema_version=f"mastermind.coo_plan_admission/v{admission_version}",
        policy_sha=policy.policy_sha256, steps=[{} for _ in range(count)])
    with pytest.raises(ValueError, match="AUTONOMY_SOURCE_INVALID"):
        compose_autonomy_policy_read(body, policy)
