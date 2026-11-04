"""Versioned native planning contracts must preserve the closed V1 default."""
from __future__ import annotations

import hashlib
import json

import pytest
from jsonschema import Draft7Validator, Draft202012Validator

from control_plane.executive_orchestration_result import (
    PLAN_SCHEMA_V1,
    PLAN_SCHEMA_V3,
    PLAN_SCHEMA_V4,
    PLAN_SCHEMA_V5,
    OrchestrationResultError,
    RESULT_SCHEMA,
    GOLDEN_ROLE_SCHEMA_DIGESTS,
    orchestration_result_schema,
    role_schema_digest,
)
from control_plane.claude_operator_helper_protocol import (
    EXECUTIVE_PLAN_CONTRACT,
    native_plan_contract,
    native_plan_schema,
)


def _envelope(version: str, *, placement: bool = True) -> dict:
    steps = []
    for ordinal, provider in enumerate(("codex", "anthropic")):
        step = {
            "ordinal": ordinal,
            "step_id": f"step-{ordinal}",
            "objective": f"Independently research {provider} evidence",
            "business_impact": "routine" if ordinal == 0 else "material",
            "review_required": ordinal == 1,
            "requested_authorities": ["READ"],
            "allowed_write_paths": [],
            "validation_ids": [],
            "attempt_limit": 1,
            "cost_class": "small",
        }
        if version in (PLAN_SCHEMA_V3, PLAN_SCHEMA_V4):
            step["prerequisite_step_ids"] = []
        if placement:
            step["placement"] = {
                "provider_realm": provider,
                "quota_class": f"{provider}-research",
            }
        steps.append(step)
    return {
        "schema_version": RESULT_SCHEMA,
        "job_id": "JOB-100",
        "run_id": "ATT-100",
        "worker_id": "planner-1",
        "role": "plan",
        "status": "COMPLETED",
        "role_result": {
            "schema_version": version,
            "root_job_id": "JOB-0",
            "plan_attempt_id": "ATT-100",
            "steps": steps,
        },
        "summary": "Independent work steps ready",
        "current_state": "Read-only work",
        "next_actions": [],
        "errors": [],
        "validations": [],
    }


def test_v1_schema_and_native_digest_are_unchanged():
    assert role_schema_digest("plan") == GOLDEN_ROLE_SCHEMA_DIGESTS["plan"]
    assert role_schema_digest("plan") == "8413f6b0777e2adceff2a9fd262760bf1d01c5cc92314e6abb5f8dc1079bbbe4"
    assert orchestration_result_schema("plan") == orchestration_result_schema(
        "plan", plan_schema_version=PLAN_SCHEMA_V1
    )
    assert native_plan_schema() == native_plan_schema(EXECUTIVE_PLAN_CONTRACT)
    assert native_plan_contract() == native_plan_contract(EXECUTIVE_PLAN_CONTRACT)
    assert native_plan_contract()["name"] == "executive-plan-v1"


@pytest.mark.parametrize(
    "version,contract",
    [(PLAN_SCHEMA_V3, "executive-plan-v3"), (PLAN_SCHEMA_V4, "executive-plan-v4")],
)
def test_versioned_provider_schema_accepts_real_independent_steps(version, contract):
    envelope = _envelope(version)
    public = orchestration_result_schema(
        "plan",
        plan_schema_version=version,
        job_id="JOB-100",
        run_id="ATT-100",
        worker_id="planner-1",
        root_job_id="JOB-0",
    )
    Draft202012Validator.check_schema(public)
    Draft202012Validator(public).validate(envelope)
    assert public["properties"]["role_result"]["properties"]["schema_version"] == {"const": version}
    assert public["properties"]["role_result"]["properties"]["steps"]["items"]["required"].count("prerequisite_step_ids") == 1
    native = native_plan_schema(contract)
    Draft7Validator.check_schema(native)
    Draft7Validator(native).validate(envelope)
    assert native_plan_contract(contract)["name"] == contract
    assert native_plan_contract(contract)["schema_digest"] == hashlib.sha256(
        json.dumps(native, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    assert not Draft7Validator(native).is_valid(_envelope(PLAN_SCHEMA_V1))


def test_v3_explicit_placement_required_and_v4_auto_placement_allowed():
    v3 = native_plan_schema("executive-plan-v3")
    assert not Draft7Validator(v3).is_valid(_envelope(PLAN_SCHEMA_V3, placement=False))
    v4 = native_plan_schema("executive-plan-v4")
    Draft7Validator(v4).validate(_envelope(PLAN_SCHEMA_V4, placement=False))
    assert not Draft7Validator(v3).is_valid(_envelope(PLAN_SCHEMA_V4))


@pytest.mark.parametrize("value", [None, "", "executive-plan-v2", "executor-plan-v3", "executive-plan-v6", True])
def test_unknown_native_contract_fails_closed(value):
    with pytest.raises((ValueError, OrchestrationResultError)):
        native_plan_schema(value)
    with pytest.raises((ValueError, OrchestrationResultError)):
        native_plan_contract(value)


@pytest.mark.parametrize("version", ["", "v3", "mastermind.execution_plan/v2", True, None])
def test_unsupported_explicit_export_version_fails_closed(version):
    with pytest.raises((OrchestrationResultError, ValueError)):
        orchestration_result_schema("plan", plan_schema_version=version)

from control_plane.executive_supervisor import worker_result_schema
from control_plane.executive_operator_supervisor import (
    ExecutiveOperatorSupervisor,
    ExecutiveOperatorSupervisorError,
)
from control_plane.executive_runtime import Runtime


@pytest.mark.parametrize(
    "version",
    [PLAN_SCHEMA_V3, PLAN_SCHEMA_V4],
)
def test_supervisor_export_matches_selected_native_producer(version):
    envelope = _envelope(version, placement=(version == PLAN_SCHEMA_V3))
    selected = worker_result_schema(
        job_id="JOB-100", run_id="ATT-100", worker_id="planner-1",
        effective_grant_digest="a" * 64,
        orchestration_role="plan", root_job_id="JOB-0",
        plan_schema_version=version,
    )
    Draft202012Validator(selected).validate(envelope)
    assert selected["properties"]["role_result"]["properties"]["schema_version"] == {"const": version}
    assert not Draft202012Validator(selected).is_valid(_envelope(PLAN_SCHEMA_V1))


@pytest.mark.parametrize(
    "version",
    [PLAN_SCHEMA_V1, PLAN_SCHEMA_V3, PLAN_SCHEMA_V4, PLAN_SCHEMA_V5],
)
def test_supervisor_requires_claimed_adapter_factory_for_opt_in(tmp_path, version):
    # Any explicit native version, including V1, is an opt-in that must arrive
    # through a claim-aware factory. Factory presence alone never opts in.
    runtime = Runtime.at(tmp_path)
    with pytest.raises(ExecutiveOperatorSupervisorError, match="claim"):
        ExecutiveOperatorSupervisor(
            runtime, adapter_factory=lambda loader: object(),
            prompt_source=object(),
            plan_schema_version=version,
        )


@pytest.mark.parametrize("version", ["", "v3", "mastermind.execution_plan/v2", True])
def test_supervisor_refuses_unqualified_plan_version(tmp_path, version):
    runtime = Runtime.at(tmp_path)
    with pytest.raises((ExecutiveOperatorSupervisorError, ValueError)):
        ExecutiveOperatorSupervisor(
            runtime, claimed_adapter_factory=lambda *a, **kw: object(),
            prompt_source=object(),
            plan_schema_version=version,
        )


def test_supervisor_omitted_and_explicit_none_are_the_same_legacy_opt_out(tmp_path):
    # ``None`` is legacy omission, never a versioned producer. It reaches the
    # supervisor identically whether the keyword is absent or explicitly None.
    omitted = ExecutiveOperatorSupervisor(
        Runtime.at(tmp_path / "omitted"),
        claimed_adapter_factory=lambda *a, **kw: object(),
        prompt_source=object(),
    )
    explicit = ExecutiveOperatorSupervisor(
        Runtime.at(tmp_path / "explicit"),
        claimed_adapter_factory=lambda *a, **kw: object(),
        prompt_source=object(),
        plan_schema_version=None,
    )
    assert omitted.plan_schema_version == PLAN_SCHEMA_V1
    assert explicit.plan_schema_version == PLAN_SCHEMA_V1
    # A claim-aware factory is present in both, yet no native producer is bound.
    assert omitted._claimed_adapter_factory is not None
    assert explicit._claimed_adapter_factory is not None
    assert omitted.fresh_planner_schema_version is None
    assert explicit.fresh_planner_schema_version is None


@pytest.mark.parametrize("version", [PLAN_SCHEMA_V1, PLAN_SCHEMA_V3, PLAN_SCHEMA_V4, PLAN_SCHEMA_V5])
def test_supervisor_explicit_native_version_is_preferred_for_fresh_planners(tmp_path, version):
    # Explicit opt-in survives the composition; omission never becomes native
    # merely because a claim-aware factory was supplied.
    opted_in = ExecutiveOperatorSupervisor(
        Runtime.at(tmp_path / "in"), claimed_adapter_factory=lambda *a, **kw: object(),
        prompt_source=object(), plan_schema_version=version,
    )
    assert opted_in.plan_schema_version == version
    assert opted_in.fresh_planner_schema_version == version
    legacy = ExecutiveOperatorSupervisor(
        Runtime.at(tmp_path / "out"), claimed_adapter_factory=lambda *a, **kw: object(),
        prompt_source=object(),
    )
    assert legacy.fresh_planner_schema_version is None

def test_trusted_control_composition_selects_v3_only_with_claimed_adapter(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace
    from scripts import executive_os_phase1c as cli
    from control_plane import executive_worker_broker as broker
    from test_ceo_submit_armed_composition import _raw, _write

    raw = cli.load_control_config(_write(tmp_path, _raw(tmp_path)))
    bindings = {}
    monkeypatch.setattr(broker, "WorkerBrokerClient", lambda *a, **kw: object())
    monkeypatch.setattr(cli, "activate_launchd_socket", lambda name: object())

    def capture(config, **kw):
        bindings.update(kw)
        return SimpleNamespace(config=config)

    monkeypatch.setattr(cli, "ExecutiveControlService", capture)
    service = cli._service_from_config(
        raw,
        claimed_operator_adapter_factory=lambda *a, **kw: object(),
        plan_schema_version=PLAN_SCHEMA_V3,
    )
    operator = bindings["operator_supervisor_factory"](
        Runtime.at(tmp_path / "runtime"), object()
    )
    assert operator.plan_schema_version == PLAN_SCHEMA_V3
    assert operator.fresh_planner_schema_version == PLAN_SCHEMA_V3
    assert service.config.ceo_submit_armed is False


@pytest.mark.parametrize(
    "version",
    [PLAN_SCHEMA_V1, PLAN_SCHEMA_V3, PLAN_SCHEMA_V4, PLAN_SCHEMA_V5],
)
def test_trusted_control_refuses_unbound_versioned_producer_before_socket(
    monkeypatch, version
):
    # The trusted Control entrypoint refuses every explicit version without an
    # explicitly supplied claim-bound adapter, including native V1.
    from scripts import executive_os_phase1c as cli
    from control_plane import executive_worker_broker as broker

    def forbidden(*args, **kwargs):
        pytest.fail("unbound plan selection reached the broker/socket")

    monkeypatch.setattr(broker, "WorkerBrokerClient", forbidden)
    monkeypatch.setattr(cli, "activate_launchd_socket", forbidden)
    with pytest.raises(cli.ServiceError, match="claim-bound"):
        cli._service_from_config({}, plan_schema_version=version)


@pytest.mark.parametrize("version", ["", "v3", True])
def test_trusted_control_refuses_unsupported_plan_version_before_socket(
    monkeypatch, version
):
    from scripts import executive_os_phase1c as cli
    from control_plane import executive_worker_broker as broker

    def forbidden(*args, **kwargs):
        pytest.fail("unqualified plan contract reached broker/socket")

    monkeypatch.setattr(broker, "WorkerBrokerClient", forbidden)
    monkeypatch.setattr(cli, "activate_launchd_socket", forbidden)
    with pytest.raises(cli.ServiceError, match="plan schema"):
        cli._service_from_config({}, plan_schema_version=version)

@pytest.mark.parametrize(
    "selected,reported",
    [
        (PLAN_SCHEMA_V3, "executive-plan-v1"),
        (PLAN_SCHEMA_V3, "executive-plan-v4"),
        (PLAN_SCHEMA_V4, "executive-plan-v3"),
        (PLAN_SCHEMA_V4, None),
    ],
)
def test_current_runtime_attempt_refuses_claimed_adapter_contract_mismatch(
    tmp_path, selected, reported,
):
    from types import SimpleNamespace
    from control_plane.executive_runtime import AttemptLease, OrchestrationDispatchOutcome
    from test_executive_operator_supervisor import _seed_dispatchable_operator_planner

    runtime, root, planner = _seed_dispatchable_operator_planner(
        tmp_path, plan_schema_version=selected,
    )
    dispatched = runtime.attempts.dispatch_cycle_job(
        planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        worker_id="worker-a",
    )
    assert isinstance(dispatched, OrchestrationDispatchOutcome)
    assert dispatched.lease_token is not None
    lease = AttemptLease(dispatched.attempt, dispatched.lease_token)
    factory_calls = []

    def claimed_factory(current, profile, loader, *, recovery):
        factory_calls.append((current.attempt_id, recovery))
        return SimpleNamespace(plan_contract=reported)

    supervisor = ExecutiveOperatorSupervisor(
        runtime, claimed_adapter_factory=claimed_factory,
        prompt_source=object(), plan_schema_version=selected,
    )
    profile = supervisor._requested_profile(planner, lease)
    with pytest.raises(ExecutiveOperatorSupervisorError, match="contract"):
        supervisor._adapter_for_attempt(
            lease, profile, lambda _turn: "inert", recovery=False,
        )
    assert factory_calls == [(dispatched.attempt.attempt_id, False)]
    assert runtime.attempts.get_attempt(dispatched.attempt.attempt_id).status.name == "CLAIMED"


def test_v5_native_producer_binds_immediate_coordinator():
    envelope = _envelope(PLAN_SCHEMA_V4, placement=False)
    body = envelope["role_result"]
    body["schema_version"] = PLAN_SCHEMA_V5
    body["coordinator_job_id"] = "JOB-009"
    for step in body["steps"]:
        step["delegation"] = None
    Draft7Validator(native_plan_schema("executive-plan-v5")).validate(envelope)
    bound = worker_result_schema(
        job_id="JOB-100", run_id="ATT-100", worker_id="planner-1",
        effective_grant_digest="a" * 64, orchestration_role="plan",
        root_job_id="JOB-0", plan_schema_version=PLAN_SCHEMA_V5,
        coordinator_job_id="JOB-009",
    )
    Draft202012Validator(bound).validate(envelope)
    body["coordinator_job_id"] = "JOB-010"
    assert not Draft202012Validator(bound).is_valid(envelope)
    assert role_schema_digest("plan") == GOLDEN_ROLE_SCHEMA_DIGESTS["plan"]
