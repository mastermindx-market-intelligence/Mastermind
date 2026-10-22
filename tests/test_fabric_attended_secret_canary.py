"""Hash/status receipt validation only; these fixtures are not live canaries."""
import copy
import dataclasses
from pathlib import Path

import pytest

from control_plane.codex_worker import (
    LaunchValidationError, validate_secret_canary_verdict,
    validate_attended_claude_secret_canary,
)
from control_plane.worker_execution_contract import WorkerLaunchSpec


def inputs():
    spec = WorkerLaunchSpec(
        run_id="attempt-1", job_id="job-1", worker_id="worker-1",
        workspace_path=Path("/srv/assignments/job-1"),
        run_dir=Path("/srv/runs/attempt-1"), prompt="Read the assigned source.",
        result_schema_path=Path("/srv/runs/attempt-1/schema.json"),
        authorities=("READ",), require_secret_canary=True,
    )
    args = dict(spec=spec, execution_profile_id="fabric.attended.claude.bounded.v1",
                harness_binding_id="minimax-token-plan.claude-code-anthropic",
                physical_binding_sha256="a" * 64, provider_home="/srv/realm/minimax")
    realm = {k: v for k, v in args.items() if k != "spec"}
    realm.update(run_id=spec.run_id, job_id=spec.job_id, worker_id=spec.worker_id)
    value = dict(schema_version="mastermind.executive_secret_canary/v2", passed=True,
                 checks={k: "DENIED" for k in (
                     "control_service_environment", "administrative_checkout",
                     "executive_database", "other_worker_home", "forbidden_production_path")},
                 receipt_sha256="b" * 64, control_environment_probe_sha256="c" * 64,
                 observed_at="2026-10-12T00:00:00Z",
                 worker_auth_exception="ASSIGNED_CLAUDE_PROVIDER_REALM_ONLY",
                 realm_binding=realm)
    return value, args


def test_attended_receipt_preserves_real_exception_without_claiming_codex_home():
    value, args = inputs()
    assert validate_attended_claude_secret_canary(value, **args) == value
    with pytest.raises(LaunchValidationError):
        validate_secret_canary_verdict(value, require_passed=True)
    legacy = copy.deepcopy(value)
    legacy.pop("realm_binding")
    legacy.update(schema_version="mastermind.executive_secret_canary/v1",
                  worker_auth_exception="DEDICATED_CODEX_HOME_ONLY")
    assert validate_secret_canary_verdict(legacy, require_passed=True) == legacy
    with pytest.raises(LaunchValidationError):
        validate_attended_claude_secret_canary(legacy, **args)


@pytest.mark.parametrize("field", [
    "run_id", "job_id", "worker_id", "provider_home", "physical_binding_sha256",
    "harness_binding_id", "execution_profile_id",
])
def test_canary_from_other_assignment_or_realm_refuses(field):
    value, args = inputs()
    value["realm_binding"][field] = "other"
    with pytest.raises(LaunchValidationError, match="another assigned realm"):
        validate_attended_claude_secret_canary(value, **args)


@pytest.mark.parametrize("check", [
    "control_service_environment", "administrative_checkout", "executive_database",
    "other_worker_home", "forbidden_production_path",
])
def test_assigned_provider_exception_never_exempts_an_unrelated_secret(check):
    value, args = inputs()
    value["checks"][check] = "ALLOWED"
    with pytest.raises(LaunchValidationError, match="must be DENIED"):
        validate_attended_claude_secret_canary(value, **args)


@pytest.mark.parametrize("change", [
    {"execution_profile_id": "autonomous"},
    {"harness_binding_id": "glm-coding-plan.claude-code-anthropic"},
    {"provider_home": "/srv/../other"},
    {"provider_home": "relative/home"},
    {"physical_binding_sha256": "bad"},
])
def test_other_or_malformed_composition_does_not_widen_exception(change):
    value, args = inputs()
    args.update(change)
    with pytest.raises(LaunchValidationError):
        validate_attended_claude_secret_canary(value, **args)


def test_missing_canary_bypass_extra_secret_and_failed_receipt_refuse():
    value, args = inputs()
    for damaged in (None, {**value, "passed": False}, {**value, "secret": "fixture"},
                    {**value, "worker_auth_exception": "DEDICATED_CODEX_HOME_ONLY"}):
        with pytest.raises(LaunchValidationError):
            validate_attended_claude_secret_canary(damaged, **args)
    args["spec"] = dataclasses.replace(args["spec"], require_secret_canary=False)
    with pytest.raises(LaunchValidationError):
        validate_attended_claude_secret_canary(value, **args)
