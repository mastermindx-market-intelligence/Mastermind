from __future__ import annotations

import inspect

import pytest

from control_plane.session_targets import (
    RuntimeBinding,
    SessionTarget,
    SessionTargetRegistry,
)


_ROOT_JOB_ID = "JOB-001"
_TARGET_ALIAS = "EXECUTIVE-CEO-A"
_SISTER_ALIAS = "EXECUTIVE-CEO-B"


def _target(alias: str) -> SessionTarget:
    return SessionTarget(
        session_alias=alias,
        target_seat="ceo",
        reasoning_surface="codex",
        wake_transport="codex-app-server",
        allowed_transports=("codex-app-server",),
        workstream=None,
        target_enabled=False,
    )


def _registry(*, bind_root: bool = True) -> SessionTargetRegistry:
    chairman = SessionTarget(
        session_alias="EXECUTIVE-CHAIRMAN-A",
        target_seat="chairman",
        reasoning_surface="human",
        wake_transport="human",
        allowed_transports=("human",),
        workstream=None,
        target_enabled=False,
    )
    coo = SessionTarget(
        session_alias="EXECUTIVE-COO-A",
        target_seat="coo",
        reasoning_surface="workspace-agent",
        wake_transport="chatgpt-gui",
        allowed_transports=("chatgpt-gui",),
        workstream=None,
        target_enabled=False,
    )
    target = _target(_TARGET_ALIAS)
    sister = _target(_SISTER_ALIAS)
    return SessionTargetRegistry(
        schema="mastermind.wake_session_targets.v2",
        lifecycle_authority="executive_os",
        production_armed=False,
        policy_version="test-sol-action-target-v1",
        default_alias_by_seat={
            "chairman": chairman.session_alias,
            "ceo": sister.session_alias,
            "coo": coo.session_alias,
        },
        workstream_alias_by_seat={},
        root_job_bindings=(
            {_ROOT_JOB_ID: {"ceo": target.session_alias}} if bind_root else {}
        ),
        targets={
            chairman.session_alias: chairman,
            coo.session_alias: coo,
            target.session_alias: target,
            sister.session_alias: sister,
        },
    )


def _binding(
    alias: str = _TARGET_ALIAS,
    *,
    binding_id: str = "bind-sol-a-000001",
    generation: int = 7,
    surface: str | None = "codex",
    account_label: str = "shared-sol-principal",
) -> RuntimeBinding:
    return RuntimeBinding(
        session_alias=alias,
        binding_id=binding_id,
        binding_generation=generation,
        native_handle=f"native-{alias.lower()}",
        account_label=account_label,
        reasoning_surface=surface,
    )


def test_exact_root_target_and_runtime_binding_resolve_action_authority():
    from control_plane.sol_action_target import (
        ActionTargetReason,
        ActionTargetState,
        RuntimeBindingSnapshot,
        require_sol_action_authority,
        resolve_sol_action_target,
    )

    target_binding = _binding()
    result = resolve_sol_action_target(
        root_job_id=_ROOT_JOB_ID,
        registry=_registry(),
        binding_snapshot=RuntimeBindingSnapshot.current(
            (target_binding, _binding(_SISTER_ALIAS, binding_id="bind-sol-b-000001"))
        ),
        actor_binding=target_binding,
    )

    assert result.state is ActionTargetState.RESOLVED
    assert result.reason is ActionTargetReason.EXACT_RUNTIME_BINDING
    assert result.root_job_id == _ROOT_JOB_ID
    assert result.target_seat == "ceo"
    assert result.session_alias == _TARGET_ALIAS
    assert result.binding_id == "bind-sol-a-000001"
    assert result.binding_generation == 7
    assert result.reasoning_surface == "codex"
    assert result.action_authoritative is True
    assert result.observer_only is False
    assert len(result.evidence_digest) == 64
    assert require_sol_action_authority(result) is result


def test_sister_sol_with_same_account_family_remains_observer_only():
    from control_plane.sol_action_target import (
        ActionTargetReason,
        ActionTargetState,
        RuntimeBindingSnapshot,
        SolActionAuthorityError,
        require_sol_action_authority,
        resolve_sol_action_target,
    )

    target_binding = _binding()
    sister_binding = _binding(
        _SISTER_ALIAS,
        binding_id="bind-sol-b-000001",
        account_label=target_binding.account_label or "",
    )
    result = resolve_sol_action_target(
        root_job_id=_ROOT_JOB_ID,
        registry=_registry(),
        binding_snapshot=RuntimeBindingSnapshot.current(
            (target_binding, sister_binding)
        ),
        actor_binding=sister_binding,
    )

    assert result.state is ActionTargetState.RESOLVED
    assert result.reason is ActionTargetReason.ACTOR_OBSERVER_ONLY
    assert result.session_alias == _TARGET_ALIAS
    assert result.action_authoritative is False
    assert result.observer_only is True
    with pytest.raises(SolActionAuthorityError) as exc_info:
        require_sol_action_authority(result)
    assert exc_info.value.resolution is result


@pytest.mark.parametrize("root_job_id", ["", "not-a-job", " JOB-001 "])
def test_malformed_root_identity_is_unknown_without_default_fallback(root_job_id: str):
    from control_plane.sol_action_target import (
        ActionTargetReason,
        ActionTargetState,
        RuntimeBindingSnapshot,
        resolve_sol_action_target,
    )

    sister_binding = _binding(_SISTER_ALIAS, binding_id="bind-sol-b-000001")
    result = resolve_sol_action_target(
        root_job_id=root_job_id,
        registry=_registry(),
        binding_snapshot=RuntimeBindingSnapshot.current((sister_binding,)),
        actor_binding=sister_binding,
    )

    assert result.state is ActionTargetState.UNKNOWN
    assert result.reason is ActionTargetReason.ROOT_JOB_ID_MALFORMED
    assert result.session_alias is None
    assert result.action_authoritative is False


def test_unbound_root_is_unknown_even_when_seat_default_matches_actor():
    from control_plane.sol_action_target import (
        ActionTargetReason,
        ActionTargetState,
        RuntimeBindingSnapshot,
        resolve_sol_action_target,
    )

    sister_binding = _binding(_SISTER_ALIAS, binding_id="bind-sol-b-000001")
    result = resolve_sol_action_target(
        root_job_id=_ROOT_JOB_ID,
        registry=_registry(bind_root=False),
        binding_snapshot=RuntimeBindingSnapshot.current((sister_binding,)),
        actor_binding=sister_binding,
    )

    assert result.state is ActionTargetState.UNKNOWN
    assert result.reason is ActionTargetReason.ROOT_TARGET_MISSING
    assert result.session_alias is None
    assert result.action_authoritative is False


def test_missing_exact_target_is_unavailable_and_does_not_promote_sister():
    from control_plane.sol_action_target import (
        ActionTargetReason,
        ActionTargetState,
        RuntimeBindingSnapshot,
        resolve_sol_action_target,
    )

    sister_binding = _binding(_SISTER_ALIAS, binding_id="bind-sol-b-000001")
    result = resolve_sol_action_target(
        root_job_id=_ROOT_JOB_ID,
        registry=_registry(),
        binding_snapshot=RuntimeBindingSnapshot.current((sister_binding,)),
        actor_binding=sister_binding,
    )

    assert result.state is ActionTargetState.UNAVAILABLE
    assert result.reason is ActionTargetReason.TARGET_RUNTIME_UNAVAILABLE
    assert result.session_alias == _TARGET_ALIAS
    assert result.binding_id is None
    assert result.action_authoritative is False
    assert result.observer_only is True


def test_unknown_binding_source_fails_closed_even_for_matching_actor():
    from control_plane.sol_action_target import (
        ActionTargetReason,
        ActionTargetState,
        RuntimeBindingSnapshot,
        resolve_sol_action_target,
    )

    result = resolve_sol_action_target(
        root_job_id=_ROOT_JOB_ID,
        registry=_registry(),
        binding_snapshot=RuntimeBindingSnapshot.unknown(),
        actor_binding=_binding(),
    )

    assert result.state is ActionTargetState.UNKNOWN
    assert result.reason is ActionTargetReason.BINDING_EVIDENCE_UNKNOWN
    assert result.session_alias == _TARGET_ALIAS
    assert result.action_authoritative is False


def test_multiple_bindings_for_exact_alias_are_conflict_not_newest_wins():
    from control_plane.sol_action_target import (
        ActionTargetReason,
        ActionTargetState,
        RuntimeBindingSnapshot,
        resolve_sol_action_target,
    )

    older = _binding(binding_id="bind-sol-a-000001", generation=7)
    newer = _binding(binding_id="bind-sol-a-000002", generation=8)
    result = resolve_sol_action_target(
        root_job_id=_ROOT_JOB_ID,
        registry=_registry(),
        binding_snapshot=RuntimeBindingSnapshot.current((newer, older)),
        actor_binding=newer,
    )

    assert result.state is ActionTargetState.CONFLICT
    assert result.reason is ActionTargetReason.RUNTIME_BINDING_CONFLICT
    assert result.binding_id is None
    assert result.action_authoritative is False


def test_binding_surface_mismatch_is_conflict():
    from control_plane.sol_action_target import (
        ActionTargetReason,
        ActionTargetState,
        RuntimeBindingSnapshot,
        resolve_sol_action_target,
    )

    mismatched = _binding(surface="chatgpt-sol")
    result = resolve_sol_action_target(
        root_job_id=_ROOT_JOB_ID,
        registry=_registry(),
        binding_snapshot=RuntimeBindingSnapshot.current((mismatched,)),
        actor_binding=mismatched,
    )

    assert result.state is ActionTargetState.CONFLICT
    assert result.reason is ActionTargetReason.RUNTIME_BINDING_SURFACE_CONFLICT
    assert result.action_authoritative is False


@pytest.mark.parametrize(
    "actor",
    [
        _binding(binding_id="bind-sol-a-stale1", generation=7),
        _binding(binding_id="bind-sol-a-000001", generation=6),
        _binding(
            _SISTER_ALIAS,
            binding_id="bind-sol-a-000001",
            generation=7,
        ),
    ],
)
def test_stale_or_wrong_actor_binding_cannot_act(actor: RuntimeBinding):
    from control_plane.sol_action_target import (
        ActionTargetReason,
        ActionTargetState,
        RuntimeBindingSnapshot,
        SolActionAuthorityError,
        require_sol_action_authority,
        resolve_sol_action_target,
    )

    current = _binding()
    result = resolve_sol_action_target(
        root_job_id=_ROOT_JOB_ID,
        registry=_registry(),
        binding_snapshot=RuntimeBindingSnapshot.current((current,)),
        actor_binding=actor,
    )

    assert result.state is ActionTargetState.RESOLVED
    assert result.reason is ActionTargetReason.ACTOR_OBSERVER_ONLY
    assert result.action_authoritative is False
    with pytest.raises(SolActionAuthorityError):
        require_sol_action_authority(result)


def test_resolution_is_deterministic_and_has_no_untrusted_election_inputs():
    from control_plane.sol_action_target import (
        RuntimeBindingSnapshot,
        resolve_sol_action_target,
    )

    signature = inspect.signature(resolve_sol_action_target)
    assert list(signature.parameters) == [
        "root_job_id",
        "registry",
        "binding_snapshot",
        "actor_binding",
    ]
    assert all(
        name not in signature.parameters
        for name in (
            "slack_principal",
            "provider_family",
            "model_claim",
            "healthy_tab",
            "observed_at",
            "newest_timestamp",
            "claimed_session_alias",
        )
    )

    current = _binding()
    first = resolve_sol_action_target(
        root_job_id=_ROOT_JOB_ID,
        registry=_registry(),
        binding_snapshot=RuntimeBindingSnapshot.current((current,)),
        actor_binding=current,
    )
    second = resolve_sol_action_target(
        root_job_id=_ROOT_JOB_ID,
        registry=_registry(),
        binding_snapshot=RuntimeBindingSnapshot.current((current,)),
        actor_binding=current,
    )
    assert first == second
    assert first.evidence_digest == second.evidence_digest
