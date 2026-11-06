from __future__ import annotations

import dataclasses

import pytest

from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from control_plane.executive_operator_supervisor import (
    ExecutiveOperatorSupervisor,
    ExecutiveOperatorSupervisorError,
)
from control_plane.executive_runtime import AttemptLease
from control_plane.model_router import ModelRouter, RoutingPolicyError
from test_executive_operator_supervisor import _PromptSource, _seed_dispatchable_operator_planner


LEGACY_ALIAS = "coo.operator.readonly"
CANDIDATE_ALIAS = "coo.operator.sol61.readonly"
LEGACY_PROFILE = "operator.appserver.readonly.docs-mcp.native-helper.v1"
CANDIDATE_PROFILE = "operator.appserver.readonly.docs-mcp.native-helper.sol61.v1"


def test_sol61_operator_candidate_is_additive_and_exact() -> None:
    registry = ExecutionCapabilityRegistry.load()
    router = ModelRouter.load()

    assert router.policy_version == "2026-10-14.attended-qualification"
    assert registry.policy_version == "2026-10-14.attended-qualification"
    assert registry.production_armed is False
    assert all(
        CANDIDATE_ALIAS not in tier.model_aliases
        for route in router.routes.values()
        for risk in ("routine", "elevated")
        for tier in route[risk]
    )

    legacy = router.model_aliases[LEGACY_ALIAS]
    candidate = router.model_aliases[CANDIDATE_ALIAS]

    assert legacy.model == "gpt-5.6-sol"
    assert legacy.execution_profile_id == LEGACY_PROFILE

    assert candidate.model == "gpt-6.1-sol"
    assert candidate.effort == "xhigh"
    assert candidate.execution_profile_id == CANDIDATE_PROFILE
    assert candidate.provider_alias == legacy.provider_alias == "codex"
    assert candidate.adapter_id == legacy.adapter_id
    assert candidate.capabilities == legacy.capabilities
    assert candidate.worker_eligible is True

    profile = registry.resolve(CANDIDATE_PROFILE)
    legacy_profile = registry.resolve(LEGACY_PROFILE)

    assert profile.enabled is True
    assert profile.execution_surface == "codex-app-server"
    assert profile.auth_realm == "dedicated-worker-account"
    assert profile.sandbox_policy == "read-only"
    assert profile.approval_policy == "never"
    assert profile.network_policy == "disabled"
    assert profile.write_capable is False
    assert profile.skills == ()
    assert profile.plugins == ()
    assert profile.mcp_servers == ("openai-developer-docs-v1",)
    assert profile.resource_grants == ()
    assert profile.native_helper is not None
    assert profile.native_helper.default_model == "gpt-6.1-sol"
    assert profile.native_helper.default_reasoning_effort == "xhigh"
    assert profile.native_helper.mechanism == "codex-multi-agent-v2-inherit-parent"
    assert profile.native_helper.inherit_parent_capabilities is True
    assert profile.native_helper.hide_spawn_agent_metadata is True
    assert profile.native_helper.max_concurrent_helpers == 1
    assert profile.native_helper.max_depth == 1
    assert profile.native_helper.max_runtime_seconds == 60

    assert legacy_profile.native_helper is not None
    assert legacy_profile.native_helper.default_model == "gpt-5.6-sol"

    for resolved, model in (
        (profile, "gpt-6.1-sol"),
        (legacy_profile, "gpt-5.6-sol"),
    ):
        overrides = resolved.app_server_config_overrides()
        assert [value for value in overrides if value.startswith("model=")] == [
            f'model="{model}"'
        ]
        assert [
            value for value in overrides
            if value.startswith("model_reasoning_effort=")
        ] == ['model_reasoning_effort="xhigh"']


def test_sol61_candidate_does_not_replace_current_coo_default() -> None:
    router = ModelRouter.load()

    assert router.model_aliases[LEGACY_ALIAS].model == "gpt-5.6-sol"
    assert router.model_aliases[CANDIDATE_ALIAS].model == "gpt-6.1-sol"
    assert router.resolve_model_alias(CANDIDATE_ALIAS).worker_eligible is True

    # This accepted frontier alias is separate from the explicitly selectable
    # candidate worker alias and must remain unavailable for a worker claim.
    existing = router.model_aliases["project.executive.sol61"]
    assert existing.model == "gpt-6.1-sol"
    assert existing.effort == "xhigh"
    assert existing.execution_profile_id == "operator.appserver.readonly.v1"
    assert existing.worker_eligible is False
    with pytest.raises(RoutingPolicyError, match="is not worker eligible"):
        router.resolve_model_alias("project.executive.sol61")


def _claimed_profile(tmp_path, model_alias):
    runtime, root, planner = _seed_dispatchable_operator_planner(
        tmp_path.resolve(), operator_model_alias=model_alias
    )
    dispatch = runtime.attempts.dispatch_cycle_job(
        planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        lease_owner="sol61-candidate-test",
    )
    assert dispatch.lease_token is not None
    lease = AttemptLease(dispatch.attempt, dispatch.lease_token)
    supervisor = ExecutiveOperatorSupervisor(
        runtime,
        claimed_adapter_factory=lambda *args, **kwargs: None,
        prompt_source=_PromptSource(),
    )
    return runtime, planner, lease, supervisor


def _assert_requested_read_only(requested, model):
    assert requested.requested_model == model
    assert requested.harness_kind == "codex-app-server"
    assert requested.sandbox_policy == "read-only"
    assert requested.approval_policy == "never"
    assert requested.network_policy == "disabled"
    assert requested.write_capable is False


def test_sol61_candidate_reaches_supervisor_as_exact_claimed_model(tmp_path) -> None:
    _, planner, lease, supervisor = _claimed_profile(tmp_path, CANDIDATE_ALIAS)

    _assert_requested_read_only(
        supervisor._requested_profile(planner, lease), "gpt-6.1-sol"
    )


def test_legacy_helper_reaches_supervisor_as_exact_claimed_model(tmp_path) -> None:
    _, planner, lease, supervisor = _claimed_profile(tmp_path, LEGACY_ALIAS)

    _assert_requested_read_only(
        supervisor._requested_profile(planner, lease), "gpt-5.6-sol"
    )


def _assert_matching_job_and_quota_cannot_override_helper(
    tmp_path, monkeypatch, model_alias, *, model, effort
):
    runtime, planner, lease, supervisor = _claimed_profile(tmp_path, model_alias)
    sealed_model = ModelRouter.load().model_aliases[model_alias].model
    _assert_requested_read_only(
        supervisor._requested_profile(planner, lease), sealed_model
    )
    quota = runtime.workers.get_quota_class(
        lease.attempt.worker_id, lease.attempt.quota_class
    )
    assert quota is not None

    # Keep every policy/profile/harness/authority binding valid. Mutating both
    # sides together deliberately passes the older Job-versus-quota check.
    changed_quota = dataclasses.replace(quota, model=model, effort=effort)
    changed_job = dataclasses.replace(
        planner, constraints={**planner.constraints, "model": model, "effort": effort}
    )

    def read_claimed_quota(worker_id, quota_class):
        assert (worker_id, quota_class) == (
            lease.attempt.worker_id, lease.attempt.quota_class
        )
        return changed_quota

    monkeypatch.setattr(runtime.workers, "get_quota_class", read_claimed_quota)
    with pytest.raises(
        ExecutiveOperatorSupervisorError,
        match="not one reviewed rich read-only lane",
    ):
        supervisor._requested_profile(changed_job, lease)


def test_legacy_helper_refuses_coordinated_model_drift(tmp_path, monkeypatch) -> None:
    _assert_matching_job_and_quota_cannot_override_helper(
        tmp_path, monkeypatch, LEGACY_ALIAS, model="gpt-6.1-sol", effort="xhigh"
    )


def test_legacy_helper_refuses_coordinated_effort_drift(tmp_path, monkeypatch) -> None:
    _assert_matching_job_and_quota_cannot_override_helper(
        tmp_path, monkeypatch, LEGACY_ALIAS, model="gpt-5.6-sol", effort="high"
    )


def test_sol61_helper_refuses_coordinated_model_drift(tmp_path, monkeypatch) -> None:
    _assert_matching_job_and_quota_cannot_override_helper(
        tmp_path, monkeypatch, CANDIDATE_ALIAS, model="gpt-5.6-sol", effort="xhigh"
    )


def test_sol61_helper_refuses_coordinated_effort_drift(tmp_path, monkeypatch) -> None:
    _assert_matching_job_and_quota_cannot_override_helper(
        tmp_path, monkeypatch, CANDIDATE_ALIAS, model="gpt-6.1-sol", effort="high"
    )
