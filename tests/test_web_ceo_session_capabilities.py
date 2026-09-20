from __future__ import annotations

import pytest

from control_plane import executive_placement_commitment as c2
from control_plane import executive_placement_selection as c1
from control_plane import web_ceo_session_capabilities as wcap
from control_plane.executive_steward import (
    CapacityState,
    EffectState,
    Freshness,
    ResponsibilityFact,
    Seat,
    SourceOwner,
    SourceRef,
)


def _source(owner: SourceOwner, ref: str) -> SourceRef:
    return SourceRef(
        owner=owner,
        ref=ref,
        observed_at="2026-09-20T00:00:00Z",
        freshness=Freshness.CURRENT,
    )


def _selection(
    *,
    worker_id: str = "web-ceo-c3-astra",
    quota_class: str = "chatgpt-pro",
) -> c1.PlacementSelectionDecision:
    responsibility = ResponsibilityFact(
        responsibility_ref="WS:WEB-CEO-CAPABILITY",
        title="Web CEO action-bearing placement",
        accountable_seat=Seat.CEO,
        state="waiting_capacity",
        root_job_id=None,
        source=_source(SourceOwner.AGENT_OS, "agentos-web-ceo-capability"),
    )
    demand = c1.PlacementDemand(
        required_capabilities=frozenset({"strategic_reasoning"}),
        quota_class=quota_class,
        provider="chatgpt-web",
        allowed_modes=frozenset({c1.PlacementMode.EXISTING_SESSION_REUSE}),
    )
    candidate = c1.PlacementCandidateFact(
        worker_id=worker_id,
        provider="chatgpt-web",
        account_label="chatgpt3",
        quota_class=quota_class,
        capabilities=frozenset({"strategic_reasoning"}),
        observed_at_ms=1_789_870_000_000,
        occupancy=c1.OccupancyState.FREE,
        occupancy_source=_source(SourceOwner.RUNTIME_BINDING, "binding-current"),
        capacity_state=CapacityState.AVAILABLE,
        capacity_source=_source(SourceOwner.CAPACITY, "capacity-current"),
        host_source_closure_proven=True,
        closure_source=_source(SourceOwner.CAPACITY, "closure-current"),
        effect_state=EffectState.NONE,
        mode=c1.PlacementMode.EXISTING_SESSION_REUSE,
        creation_surface_accessible=None,
        session_creation_allowed=None,
    )
    decision = c1.select_placement(
        responsibility=responsibility,
        demand=demand,
        candidates=(candidate,),
    )
    assert decision.state is c1.SelectionState.SELECTED
    return decision


def _target_facts() -> dict[str, object]:
    return {
        "session_alias": "EXECUTIVE-CEO-CODEX-A",
        "target_seat": "fixture-seat-a",
        "reasoning_surface": "codex",
        "wake_transport": "codex-app-server",
        "allowed_transports": ["codex-app-server"],
        "workstream": "executive",
    }


def _observation(
    name: str,
    state: wcap.CapabilityObservationState,
    proof: wcap.CapabilityProofClass,
) -> wcap.CapabilityObservation:
    return wcap.CapabilityObservation(name=name, state=state, proof_class=proof)


def _receipt(
    *observations: wcap.CapabilityObservation,
    worker_id: str = "web-ceo-c3-astra",
    quota_class: str = "chatgpt-pro",
    session_ref: str = "websol-c3-session-17",
    binding_ref: str = "runtimebinding-websol-c3-17",
    binding_generation: int = 7,
    observed_at_ms: int = 1_789_870_000_000,
    expires_at_ms: int = 1_789_870_120_000,
    schema_complete: bool = True,
) -> wcap.WebCeoSessionCapabilityReceipt:
    return wcap.WebCeoSessionCapabilityReceipt(
        worker_id=worker_id,
        quota_class=quota_class,
        session_ref=session_ref,
        binding_ref=binding_ref,
        binding_generation=binding_generation,
        observed_at_ms=observed_at_ms,
        expires_at_ms=expires_at_ms,
        schema_complete=schema_complete,
        tool_schema_digest="a" * 64,
        observations=tuple(observations),
    )


def _assess(
    receipt: wcap.WebCeoSessionCapabilityReceipt,
    *,
    required: frozenset[str] = frozenset(
        {"executive_submit", "studio_direct_write", "desktop_commander_write"}
    ),
    worker_id: str = "web-ceo-c3-astra",
    quota_class: str = "chatgpt-pro",
    session_ref: str = "websol-c3-session-17",
    binding_ref: str = "runtimebinding-websol-c3-17",
    binding_generation: int = 7,
    now_ms: int = 1_789_870_060_000,
    start_state: wcap.SessionStartState = wcap.SessionStartState.PRE_START,
    effect_state: EffectState = EffectState.NONE,
) -> wcap.WebCeoCapabilityPreflightDecision:
    return wcap.assess_web_ceo_session_capabilities(
        receipt=receipt,
        required_capabilities=required,
        expected_worker_id=worker_id,
        expected_quota_class=quota_class,
        expected_session_ref=session_ref,
        expected_binding_ref=binding_ref,
        expected_binding_generation=binding_generation,
        now_ms=now_ms,
        start_state=start_state,
        effect_state=effect_state,
    )


def test_exact_fresh_action_capabilities_allow_guarded_commitment() -> None:
    receipt = _receipt(
        _observation(
            "executive_submit",
            wcap.CapabilityObservationState.PRESENT,
            wcap.CapabilityProofClass.EFFECTIVE_SCHEMA,
        ),
        _observation(
            "studio_direct_write",
            wcap.CapabilityObservationState.PRESENT,
            wcap.CapabilityProofClass.EFFECTIVE_SCHEMA,
        ),
        _observation(
            "desktop_commander_write",
            wcap.CapabilityObservationState.PRESENT,
            wcap.CapabilityProofClass.EFFECTIVE_SCHEMA,
        ),
        _observation(
            "github_read",
            wcap.CapabilityObservationState.PRESENT,
            wcap.CapabilityProofClass.NO_EFFECT_PROBE,
        ),
    )
    preflight = _assess(receipt)

    assert preflight.state is wcap.PreflightState.READY
    assert preflight.rebind_allowed is False
    assert preflight.missing_capabilities == ()
    assert preflight.unknown_capabilities == ()
    assert preflight.proven_capabilities == (
        "desktop_commander_write",
        "executive_submit",
        "studio_direct_write",
    )

    plan = wcap.build_guarded_commitment_plan_from_selection_decision(
        source_root_job_id="job-source-1",
        expected_source_root_revision=7,
        placement_selection=_selection(),
        validated_target_facts=_target_facts(),
        capability_preflight=preflight,
    )
    assert isinstance(plan, c2.PlacementCommitmentPlan)
    assert plan.selected_worker_id == "web-ceo-c3-astra"
    assert plan.selected_quota_class == "chatgpt-pro"


def test_blind_astra_is_prestart_rebindable_and_cannot_commit() -> None:
    receipt = _receipt(
        _observation(
            "github_read",
            wcap.CapabilityObservationState.PRESENT,
            wcap.CapabilityProofClass.NO_EFFECT_PROBE,
        ),
        _observation(
            "executive_submit",
            wcap.CapabilityObservationState.ABSENT,
            wcap.CapabilityProofClass.EFFECTIVE_SCHEMA,
        ),
        _observation(
            "studio_direct_write",
            wcap.CapabilityObservationState.ABSENT,
            wcap.CapabilityProofClass.EFFECTIVE_SCHEMA,
        ),
        _observation(
            "desktop_commander_write",
            wcap.CapabilityObservationState.ABSENT,
            wcap.CapabilityProofClass.EFFECTIVE_SCHEMA,
        ),
    )
    preflight = _assess(receipt)

    assert preflight.state is wcap.PreflightState.PRESTART_REBIND_REQUIRED
    assert preflight.rebind_allowed is True
    assert preflight.missing_capabilities == (
        "desktop_commander_write",
        "executive_submit",
        "studio_direct_write",
    )
    assert preflight.exclusion == {
        "worker_id": "web-ceo-c3-astra",
        "quota_class": "chatgpt-pro",
        "reason": "effective_capability_missing",
    }
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="CAPABILITY_PREFLIGHT_NOT_READY",
    ):
        wcap.build_guarded_commitment_plan_from_selection_decision(
            source_root_job_id="job-source-1",
            expected_source_root_revision=7,
            placement_selection=_selection(),
            validated_target_facts=_target_facts(),
            capability_preflight=preflight,
        )


def test_unknown_required_capability_requires_more_proof_not_rebind() -> None:
    receipt = _receipt(
        _observation(
            "executive_submit",
            wcap.CapabilityObservationState.PRESENT,
            wcap.CapabilityProofClass.EFFECTIVE_SCHEMA,
        ),
        _observation(
            "studio_direct_write",
            wcap.CapabilityObservationState.UNKNOWN,
            wcap.CapabilityProofClass.NO_EFFECT_PROBE,
        ),
        schema_complete=False,
    )
    preflight = _assess(
        receipt,
        required=frozenset({"executive_submit", "studio_direct_write"}),
    )
    assert preflight.state is wcap.PreflightState.CAPABILITY_PROOF_REQUIRED
    assert preflight.rebind_allowed is False
    assert preflight.unknown_capabilities == ("studio_direct_write",)


def test_absence_requires_complete_effective_schema_evidence() -> None:
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="ABSENCE_REQUIRES_COMPLETE_SCHEMA",
    ):
        _receipt(
            _observation(
                "executive_submit",
                wcap.CapabilityObservationState.ABSENT,
                wcap.CapabilityProofClass.EFFECTIVE_SCHEMA,
            ),
            schema_complete=False,
        )

    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="ABSENCE_REQUIRES_SCHEMA_PROOF",
    ):
        _receipt(
            _observation(
                "executive_submit",
                wcap.CapabilityObservationState.ABSENT,
                wcap.CapabilityProofClass.NO_EFFECT_PROBE,
            )
        )


def test_stale_capability_evidence_never_commits_or_rebinds() -> None:
    receipt = _receipt(
        _observation(
            "executive_submit",
            wcap.CapabilityObservationState.PRESENT,
            wcap.CapabilityProofClass.EFFECTIVE_SCHEMA,
        ),
        expires_at_ms=1_789_870_030_000,
    )
    preflight = _assess(
        receipt,
        required=frozenset({"executive_submit"}),
        now_ms=1_789_870_060_000,
    )
    assert preflight.state is wcap.PreflightState.STALE_EVIDENCE
    assert preflight.rebind_allowed is False


@pytest.mark.parametrize(
    ("change", "value"),
    [
        ("worker_id", "web-ceo-c1-sol"),
        ("quota_class", "chatgpt-business"),
        ("session_ref", "websol-c1-session-2"),
        ("binding_ref", "runtimebinding-websol-c1-2"),
        ("binding_generation", 8),
    ],
)
def test_exact_identity_or_binding_mismatch_requires_reconciliation(
    change: str, value: object
) -> None:
    receipt = _receipt(
        _observation(
            "executive_submit",
            wcap.CapabilityObservationState.PRESENT,
            wcap.CapabilityProofClass.EFFECTIVE_SCHEMA,
        )
    )
    kwargs = {change: value}
    preflight = _assess(
        receipt,
        required=frozenset({"executive_submit"}),
        **kwargs,
    )
    assert preflight.state is wcap.PreflightState.RECONCILIATION_REQUIRED
    assert preflight.rebind_allowed is False


def test_effect_unknown_freezes_capability_failover() -> None:
    receipt = _receipt(
        _observation(
            "executive_submit",
            wcap.CapabilityObservationState.ABSENT,
            wcap.CapabilityProofClass.EFFECTIVE_SCHEMA,
        )
    )
    preflight = _assess(
        receipt,
        required=frozenset({"executive_submit"}),
        effect_state=EffectState.EFFECT_UNKNOWN,
    )
    assert preflight.state is wcap.PreflightState.EFFECT_UNKNOWN
    assert preflight.rebind_allowed is False


def test_started_session_with_lost_tool_is_sticky_degraded_not_rebound() -> None:
    receipt = _receipt(
        _observation(
            "executive_submit",
            wcap.CapabilityObservationState.ABSENT,
            wcap.CapabilityProofClass.EFFECTIVE_SCHEMA,
        )
    )
    preflight = _assess(
        receipt,
        required=frozenset({"executive_submit"}),
        start_state=wcap.SessionStartState.STARTED,
    )
    assert preflight.state is wcap.PreflightState.STICKY_DEGRADED
    assert preflight.rebind_allowed is False
    assert preflight.missing_capabilities == ("executive_submit",)


def test_prestart_applied_effect_is_reconciliation_required() -> None:
    receipt = _receipt(
        _observation(
            "executive_submit",
            wcap.CapabilityObservationState.PRESENT,
            wcap.CapabilityProofClass.EFFECTIVE_SCHEMA,
        )
    )
    preflight = _assess(
        receipt,
        required=frozenset({"executive_submit"}),
        effect_state=EffectState.APPLIED,
    )
    assert preflight.state is wcap.PreflightState.RECONCILIATION_REQUIRED
    assert preflight.rebind_allowed is False


def test_receipt_wire_round_trip_is_closed_and_deterministic() -> None:
    receipt = _receipt(
        _observation(
            "studio_direct_write",
            wcap.CapabilityObservationState.PRESENT,
            wcap.CapabilityProofClass.EFFECTIVE_SCHEMA,
        ),
        _observation(
            "executive_submit",
            wcap.CapabilityObservationState.PRESENT,
            wcap.CapabilityProofClass.NO_EFFECT_PROBE,
        ),
    )
    wire = receipt.to_dict()
    rebuilt = wcap.validate_session_capability_receipt(wire)
    assert rebuilt == receipt
    assert rebuilt.evidence_digest == receipt.evidence_digest

    forged = dict(wire)
    forged["authority"] = "chairman"
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="CAPABILITY_RECEIPT_SHAPE_INVALID",
    ):
        wcap.validate_session_capability_receipt(forged)


def test_guard_rejects_preflight_for_different_selected_candidate() -> None:
    receipt = _receipt(
        _observation(
            "executive_submit",
            wcap.CapabilityObservationState.PRESENT,
            wcap.CapabilityProofClass.EFFECTIVE_SCHEMA,
        )
    )
    preflight = _assess(
        receipt,
        required=frozenset({"executive_submit"}),
    )
    assert preflight.state is wcap.PreflightState.READY

    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="CAPABILITY_PREFLIGHT_SELECTION_MISMATCH",
    ):
        wcap.build_guarded_commitment_plan_from_selection_decision(
            source_root_job_id="job-source-1",
            expected_source_root_revision=7,
            placement_selection=_selection(worker_id="web-ceo-c4-sol"),
            validated_target_facts=_target_facts(),
            capability_preflight=preflight,
        )


def test_decision_projection_is_machine_readable_and_never_grants_authority() -> None:
    receipt = _receipt(
        _observation(
            "executive_submit",
            wcap.CapabilityObservationState.ABSENT,
            wcap.CapabilityProofClass.EFFECTIVE_SCHEMA,
        )
    )
    projection = _assess(
        receipt,
        required=frozenset({"executive_submit"}),
    ).to_dict()

    assert projection["schema_version"] == wcap.PREFLIGHT_SCHEMA
    assert projection["state"] == "prestart_rebind_required"
    assert projection["rebind_allowed"] is True
    assert projection["selection_is_commitment"] is False
    assert "authority" not in projection
    assert "provider_session_id" not in projection


def test_effective_tool_schema_producer_maps_real_tool_families() -> None:
    receipt = wcap.build_receipt_from_effective_tool_schema(
        tool_names=(
            "mcp__GitHub__fetch_file",
            "mcp__GitHub__update_file",
            "mcp__Mastermind_Executive_v2__executive_state",
            "mcp__Mastermind_Executive_v2__submit_ceo_intent",
            "mcp__Studio_Direct___C2_Personal__get_config",
            "mcp__Studio_Direct___C2_Personal__write_file",
            "mcp__Studio_Direct___C2_Personal__start_process",
            "mcp__Remote_Desktop_Commander__read_file",
            "mcp__Remote_Desktop_Commander__write_file",
            "mcp__Remote_Desktop_Commander__start_process",
        ),
        worker_id="web-ceo-c3-astra",
        quota_class="chatgpt-pro",
        session_ref="websol-c3-session-17",
        binding_ref="runtimebinding-websol-c3-17",
        binding_generation=7,
        observed_at_ms=1_789_870_000_000,
        expires_at_ms=1_789_870_120_000,
    )
    states = {item.name: item.state for item in receipt.observations}
    assert states["github_read"] is wcap.CapabilityObservationState.PRESENT
    assert states["github_write"] is wcap.CapabilityObservationState.PRESENT
    assert states["executive_read"] is wcap.CapabilityObservationState.PRESENT
    assert states["executive_submit"] is wcap.CapabilityObservationState.PRESENT
    assert states["studio_direct_read"] is wcap.CapabilityObservationState.PRESENT
    assert states["studio_direct_write"] is wcap.CapabilityObservationState.PRESENT
    assert states["studio_direct_command"] is wcap.CapabilityObservationState.PRESENT
    assert states["desktop_commander_read"] is wcap.CapabilityObservationState.PRESENT
    assert states["desktop_commander_write"] is wcap.CapabilityObservationState.PRESENT
    assert states["desktop_commander_command"] is wcap.CapabilityObservationState.PRESENT
    assert all(
        item.proof_class is wcap.CapabilityProofClass.EFFECTIVE_SCHEMA
        for item in receipt.observations
    )


def test_effective_tool_schema_producer_turns_github_read_only_astra_into_rebind() -> None:
    receipt = wcap.build_receipt_from_effective_tool_schema(
        tool_names=(
            "mcp__GitHub__fetch",
            "mcp__GitHub__fetch_file",
            "mcp__GitHub__search",
        ),
        worker_id="web-ceo-c3-astra",
        quota_class="chatgpt-pro",
        session_ref="websol-c3-session-17",
        binding_ref="runtimebinding-websol-c3-17",
        binding_generation=7,
        observed_at_ms=1_789_870_000_000,
        expires_at_ms=1_789_870_120_000,
    )
    states = {item.name: item.state for item in receipt.observations}
    assert states["github_read"] is wcap.CapabilityObservationState.PRESENT
    assert states["github_write"] is wcap.CapabilityObservationState.ABSENT
    assert states["executive_submit"] is wcap.CapabilityObservationState.ABSENT
    assert states["studio_direct_write"] is wcap.CapabilityObservationState.ABSENT
    assert states["desktop_commander_write"] is wcap.CapabilityObservationState.ABSENT

    preflight = _assess(receipt)
    assert preflight.state is wcap.PreflightState.PRESTART_REBIND_REQUIRED
    assert preflight.rebind_allowed is True


def test_effective_tool_schema_receipt_does_not_persist_raw_tool_names() -> None:
    raw_tools = (
        "mcp__GitHub__fetch_file",
        "mcp__Mastermind_Executive__submit_ceo_intent",
    )
    receipt = wcap.build_receipt_from_effective_tool_schema(
        tool_names=raw_tools,
        worker_id="web-ceo-c3-astra",
        quota_class="chatgpt-pro",
        session_ref="websol-c3-session-17",
        binding_ref="runtimebinding-websol-c3-17",
        binding_generation=7,
        observed_at_ms=1_789_870_000_000,
        expires_at_ms=1_789_870_120_000,
    )
    rendered = str(receipt.to_dict())
    for name in raw_tools:
        assert name not in rendered
    assert receipt.tool_schema_digest != "a" * 64


def test_effective_tool_schema_rejects_duplicate_tool_names() -> None:
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="DUPLICATE_EFFECTIVE_TOOL_NAME",
    ):
        wcap.build_receipt_from_effective_tool_schema(
            tool_names=("mcp__GitHub__fetch", "mcp__GitHub__fetch"),
            worker_id="web-ceo-c3-astra",
            quota_class="chatgpt-pro",
            session_ref="websol-c3-session-17",
            binding_ref="runtimebinding-websol-c3-17",
            binding_generation=7,
            observed_at_ms=1_789_870_000_000,
            expires_at_ms=1_789_870_120_000,
        )
