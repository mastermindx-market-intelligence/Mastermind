from __future__ import annotations

from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor
from control_plane.executive_runtime import AttemptLease
from control_plane.model_router import ModelRouter
from test_executive_operator_supervisor import _PromptSource, _seed_dispatchable_operator_planner


LEGACY_ALIAS = "coo.operator.readonly"
CANDIDATE_ALIAS = "coo.operator.sol61.readonly"
LEGACY_PROFILE = "operator.appserver.readonly.docs-mcp.native-helper.v1"
CANDIDATE_PROFILE = "operator.appserver.readonly.docs-mcp.native-helper.sol61.v1"


def test_sol61_operator_candidate_is_additive_and_exact() -> None:
    registry = ExecutionCapabilityRegistry.load()
    router = ModelRouter.load()

    assert router.policy_version == "2026-08-24.stage4"
    assert registry.policy_version == "2026-10-05.sol61-project-executive-candidate"
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
    assert profile.native_helper.max_concurrent_helpers == 1
    assert profile.native_helper.max_depth == 1
    assert profile.native_helper.max_runtime_seconds == 60

    assert legacy_profile.native_helper is not None
    assert legacy_profile.native_helper.default_model == "gpt-5.6-sol"

    candidate_overrides = profile.app_server_config_overrides()
    legacy_overrides = legacy_profile.app_server_config_overrides()
    assert 'model="gpt-6.1-sol"' in candidate_overrides
    assert 'model_reasoning_effort="xhigh"' in candidate_overrides
    assert 'model="gpt-5.6-sol"' in legacy_overrides
    assert 'model_reasoning_effort="xhigh"' in legacy_overrides
    assert candidate_overrides.count('model="gpt-6.1-sol"') == 1


def test_sol61_candidate_does_not_replace_current_coo_default() -> None:
    router = ModelRouter.load()

    assert router.model_aliases[LEGACY_ALIAS].model == "gpt-5.6-sol"
    assert router.model_aliases[CANDIDATE_ALIAS].model == "gpt-6.1-sol"

def test_sol61_candidate_reaches_supervisor_as_exact_claimed_model(tmp_path) -> None:
    runtime, root, planner = _seed_dispatchable_operator_planner(
        tmp_path, operator_alias=CANDIDATE_ALIAS
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

    requested = supervisor._requested_profile(planner, lease)

    assert requested.requested_model == "gpt-6.1-sol"
    assert requested.harness_kind == "codex-app-server"
    assert requested.sandbox_policy == "read-only"
    assert requested.approval_policy == "never"
    assert requested.network_policy == "disabled"
    assert requested.write_capable is False

