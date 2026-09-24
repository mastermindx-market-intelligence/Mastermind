from __future__ import annotations

import inspect

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


OBSERVED_AT_MS = 1_789_870_000_000
EXPIRES_AT_MS = 1_789_870_120_000
NOW_MS = 1_789_870_060_000
OBSERVER_DIGEST = "e" * 64
WORKER_ROUTE_DIGEST = "b" * 64
ACTION_SCOPE_REF = "web-message-scope-42"


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
    required_capabilities: frozenset[str] = frozenset(
        {"executive_submit", "studio_direct_write", "desktop_commander_write"}
    ),
    allowed_modes: frozenset[c1.PlacementMode] = frozenset(
        {
            c1.PlacementMode.EXISTING_SESSION_REUSE,
            c1.PlacementMode.NEW_SESSION_MATERIALIZATION,
        }
    ),
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
        required_capabilities=required_capabilities,
        quota_class=quota_class,
        provider="chatgpt-web",
        allowed_modes=allowed_modes,
    )
    candidate = c1.PlacementCandidateFact(
        worker_id=worker_id,
        provider="chatgpt-web",
        account_label="chatgpt3",
        quota_class=quota_class,
        capabilities=required_capabilities,
        observed_at_ms=OBSERVED_AT_MS,
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


def _principal_action_owner_facts(
    selection: c1.PlacementSelectionDecision,
    *,
    principal_required: frozenset[str] | None = None,
    action_partition_source: SourceRef | None = None,
    worker_route_source: SourceRef | None = None,
    worker_route_digest: str = WORKER_ROUTE_DIGEST,
) -> c1.PrincipalActionOwnerFacts:
    required = (
        principal_required
        if principal_required is not None
        else selection.demand.required_capabilities
    )
    return c1.PrincipalActionOwnerFacts(
        principal_required_capabilities=tuple(sorted(required)),
        action_partition_source=(
            action_partition_source
            or _source(SourceOwner.CAPACITY, "capacity-action-partition-current")
        ),
        worker_route_source=(
            worker_route_source
            or _source(SourceOwner.EXECUTIVE_OS, "executive-worker-route-current")
        ),
        worker_route_evidence_digest=worker_route_digest,
    )


def _principal_action_demand(
    selection: c1.PlacementSelectionDecision,
    *,
    principal_required: frozenset[str] | None = None,
    action_partition_source: SourceRef | None = None,
    worker_route_source: SourceRef | None = None,
    worker_route_digest: str = WORKER_ROUTE_DIGEST,
) -> c1.PrincipalActionDemandReceipt:
    return c1.build_principal_action_demand_receipt(
        decision=selection,
        owner_facts=_principal_action_owner_facts(
            selection,
            principal_required=principal_required,
            action_partition_source=action_partition_source,
            worker_route_source=worker_route_source,
            worker_route_digest=worker_route_digest,
        ),
    )


def _target_facts() -> dict[str, object]:
    return {
        "session_alias": "EXECUTIVE-CEO-CODEX-A",
        "target_seat": "fixture-seat-a",
        "reasoning_surface": "codex",
        "wake_transport": "codex-app-server",
        "allowed_transports": ["codex-app-server"],
        "workstream": "executive",
    }


def _descriptor(name: str, marker: str) -> wcap.EffectiveToolDescriptor:
    return wcap.EffectiveToolDescriptor(
        tool_name=name,
        invocation_schema_digest=marker * 64,
    )


def _contracts() -> tuple[wcap.CapabilityActionContract, ...]:
    specs: dict[str, tuple[wcap.EffectiveToolDescriptor, ...]] = {
        "desktop_commander_command": (
            _descriptor("mcp__Remote_Desktop_Commander__start_process", "1"),
        ),
        "desktop_commander_read": (
            _descriptor("mcp__Remote_Desktop_Commander__read_file", "2"),
        ),
        "desktop_commander_write": (
            _descriptor("mcp__Remote_Desktop_Commander__write_file", "3"),
            _descriptor("mcp__Remote_Desktop_Commander__edit_block", "4"),
        ),
        "executive_read": (
            _descriptor("mcp__Mastermind_Executive_v2__executive_state", "5"),
        ),
        "executive_submit": (
            _descriptor("mcp__Mastermind_Executive_v2__submit_ceo_intent", "6"),
        ),
        "github_read": (
            _descriptor("mcp__GitHub__fetch_file", "7"),
        ),
        "github_write": (
            _descriptor("mcp__GitHub__update_file", "8"),
            _descriptor("mcp__GitHub__create_pull_request", "9"),
        ),
        "studio_direct_command": (
            _descriptor("mcp__Studio_Direct___C2_Personal__start_process", "a"),
        ),
        "studio_direct_read": (
            _descriptor("mcp__Studio_Direct___C2_Personal__get_config", "b"),
        ),
        "studio_direct_write": (
            _descriptor("mcp__Studio_Direct___C2_Personal__write_file", "c"),
            _descriptor("mcp__Studio_Direct___C2_Personal__edit_block", "d"),
        ),
    }
    return tuple(
        wcap.CapabilityActionContract(
            capability=name,
            required_actions=specs[name],
        )
        for name in wcap.KNOWN_EFFECTIVE_CAPABILITIES
    )


def _all_actions(
    contracts: tuple[wcap.CapabilityActionContract, ...] | None = None,
) -> tuple[wcap.EffectiveToolDescriptor, ...]:
    bound = contracts or _contracts()
    return tuple(
        action
        for contract in bound
        for action in contract.required_actions
    )


def _serviceability_fact(
    action: wcap.EffectiveToolDescriptor,
    *,
    serviceable: bool = True,
    session_ref: str = "websol-c3-session-17",
    binding_ref: str = "runtimebinding-websol-c3-17",
    binding_generation: int = 7,
    action_scope_ref: str = ACTION_SCOPE_REF,
    action_surface_evidence_digest: str | None = None,
    observed_at_ms: int = OBSERVED_AT_MS,
    expires_at_ms: int = EXPIRES_AT_MS,
) -> wcap.ActionServiceabilityFact:
    return wcap.ActionServiceabilityFact(
        tool=action,
        session_ref=session_ref,
        binding_ref=binding_ref,
        binding_generation=binding_generation,
        action_scope_ref=action_scope_ref,
        action_surface_evidence_digest=(
            action_surface_evidence_digest
            or _action_surface(
                session_ref=session_ref,
                binding_ref=binding_ref,
                binding_generation=binding_generation,
                action_scope_ref=surface.action_scope_ref,
                action_surface_evidence_digest=surface.evidence_digest,
                observed_at_ms=observed_at_ms,
                expires_at_ms=expires_at_ms,
            ).evidence_digest
        ),
        observed_at_ms=observed_at_ms,
        expires_at_ms=expires_at_ms,
        serviceable=serviceable,
        evidence_digest="f" * 64,
    )


def _all_serviceable(
    contracts: tuple[wcap.CapabilityActionContract, ...] | None = None,
) -> tuple[wcap.ActionServiceabilityFact, ...]:
    return tuple(
        _serviceability_fact(action)
        for action in _all_actions(contracts)
    )


def _receipt(
    *,
    effective_tools: tuple[wcap.EffectiveToolDescriptor, ...] | None = None,
    contracts: tuple[wcap.CapabilityActionContract, ...] | None = None,
    serviceability: tuple[wcap.ActionServiceabilityFact, ...] | None = None,
    worker_id: str = "web-ceo-c3-astra",
    quota_class: str = "chatgpt-pro",
    session_ref: str = "websol-c3-session-17",
    binding_ref: str = "runtimebinding-websol-c3-17",
    binding_generation: int = 7,
    action_scope_ref: str = ACTION_SCOPE_REF,
    observed_at_ms: int = OBSERVED_AT_MS,
    expires_at_ms: int = EXPIRES_AT_MS,
    schema_complete: bool = True,
    action_surface: wcap.CurrentActionSurfaceFacts | None = None,
) -> wcap.WebCeoSessionCapabilityReceipt:
    bound_contracts = contracts or _contracts()
    bound_tools = effective_tools if effective_tools is not None else _all_actions(
        bound_contracts
    )
    surface = action_surface or _action_surface(
        session_ref=session_ref,
        binding_ref=binding_ref,
        binding_generation=binding_generation,
        action_scope_ref=action_scope_ref,
        observed_at_ms=observed_at_ms,
        expires_at_ms=expires_at_ms,
    )
    probes = (
        serviceability
        if serviceability is not None
        else tuple(
            _serviceability_fact(
                action,
                session_ref=session_ref,
                binding_ref=binding_ref,
                binding_generation=binding_generation,
                action_scope_ref=action_scope_ref,
                observed_at_ms=observed_at_ms,
                expires_at_ms=expires_at_ms,
            )
            for action in _all_actions(bound_contracts)
        )
    )
    return wcap.build_receipt_from_effective_tool_schema(
        effective_tools=bound_tools,
        capability_contracts=bound_contracts,
        schema_complete=schema_complete,
        observer_evidence_digest=OBSERVER_DIGEST,
        worker_id=worker_id,
        quota_class=quota_class,
        session_ref=session_ref,
        binding_ref=binding_ref,
        binding_generation=binding_generation,
        action_surface=surface,
        observed_at_ms=observed_at_ms,
        expires_at_ms=expires_at_ms,
        action_serviceability=probes,
    )


def _binding(
    *,
    worker_id: str = "web-ceo-c3-astra",
    quota_class: str = "chatgpt-pro",
    session_ref: str = "websol-c3-session-17",
    binding_ref: str = "runtimebinding-websol-c3-17",
    binding_generation: int = 7,
) -> wcap.CurrentSessionBindingFacts:
    return wcap.CurrentSessionBindingFacts(
        worker_id=worker_id,
        quota_class=quota_class,
        session_ref=session_ref,
        binding_ref=binding_ref,
        binding_generation=binding_generation,
    )


def _action_surface(
    *,
    session_ref: str = "websol-c3-session-17",
    binding_ref: str = "runtimebinding-websol-c3-17",
    binding_generation: int = 7,
    action_scope_ref: str = ACTION_SCOPE_REF,
    observed_at_ms: int = OBSERVED_AT_MS,
    expires_at_ms: int = EXPIRES_AT_MS,
    source: SourceRef | None = None,
) -> wcap.CurrentActionSurfaceFacts:
    return wcap.CurrentActionSurfaceFacts(
        session_ref=session_ref,
        binding_ref=binding_ref,
        binding_generation=binding_generation,
        action_scope_ref=action_scope_ref,
        observed_at_ms=observed_at_ms,
        expires_at_ms=expires_at_ms,
        source=(
            source
            or _source(
                SourceOwner.SURFACE_BINDINGS,
                "surface-bindings-web-message-scope-current",
            )
        ),
    )


def _assess(
    receipt: wcap.WebCeoSessionCapabilityReceipt,
    *,
    required: frozenset[str] = frozenset(
        {"executive_submit", "studio_direct_write", "desktop_commander_write"}
    ),
    binding_mode: wcap.ReceiverBindingMode = (
        wcap.ReceiverBindingMode.CAPACITY_SELECTABLE
    ),
    binding: wcap.CurrentSessionBindingFacts | None = None,
    action_surface: wcap.CurrentActionSurfaceFacts | None = None,
    expected_contract_digest: str | None = None,
    expected_observer_digest: str | None = None,
    expected_serviceability_digest: str | None = None,
    now_ms: int = NOW_MS,
    start_state: wcap.SessionStartState = wcap.SessionStartState.PRE_START,
    effect_state: EffectState = EffectState.NONE,
) -> wcap.WebCeoCapabilityPreflightDecision:
    current = binding or _binding()
    current_surface = action_surface or _action_surface(
        session_ref=current.session_ref,
        binding_ref=current.binding_ref,
        binding_generation=current.binding_generation,
    )
    return wcap.assess_web_ceo_session_capabilities(
        receipt=receipt,
        required_capabilities=required,
        receiver_binding_mode=binding_mode,
        expected_worker_id=current.worker_id,
        expected_quota_class=current.quota_class,
        expected_session_ref=current.session_ref,
        expected_binding_ref=current.binding_ref,
        expected_binding_generation=current.binding_generation,
        expected_action_scope_ref=current_surface.action_scope_ref,
        expected_action_surface_evidence_digest=current_surface.evidence_digest,
        expected_capability_contract_digest=(
            expected_contract_digest or receipt.capability_contract_digest
        ),
        expected_observer_evidence_digest=(
            expected_observer_digest or receipt.observer_evidence_digest
        ),
        expected_serviceability_evidence_digest=(
            expected_serviceability_digest
            or receipt.serviceability_evidence_digest
        ),
        now_ms=now_ms,
        start_state=start_state,
        effect_state=effect_state,
    )


def _guard(
    receipt: wcap.WebCeoSessionCapabilityReceipt,
    *,
    selection: c1.PlacementSelectionDecision | None = None,
    principal_action_demand: c1.PrincipalActionDemandReceipt | None = None,
    current_principal_action_facts: c1.PrincipalActionOwnerFacts | None = None,
    binding: wcap.CurrentSessionBindingFacts | None = None,
    action_surface: wcap.CurrentActionSurfaceFacts | None = None,
    expected_contract_digest: str | None = None,
    expected_observer_digest: str | None = None,
    expected_serviceability_digest: str | None = None,
    now_ms: int = NOW_MS,
    start_state: wcap.SessionStartState = wcap.SessionStartState.PRE_START,
    effect_state: EffectState = EffectState.NONE,
) -> c2.PlacementCommitmentPlan:
    bound_selection = selection or _selection()
    action_demand = principal_action_demand or _principal_action_demand(
        bound_selection
    )
    current_action_facts = (
        current_principal_action_facts
        or c1.PrincipalActionOwnerFacts(
            principal_required_capabilities=(
                action_demand.principal_required_capabilities
            ),
            action_partition_source=action_demand.action_partition_source,
            worker_route_source=action_demand.worker_route_source,
            worker_route_evidence_digest=(
                action_demand.worker_route_evidence_digest
            ),
        )
    )
    current_binding = binding or _binding()
    current_surface = action_surface or _action_surface(
        session_ref=current_binding.session_ref,
        binding_ref=current_binding.binding_ref,
        binding_generation=current_binding.binding_generation,
    )
    return wcap.build_guarded_commitment_plan_from_selection_decision(
        source_root_job_id="job-source-1",
        expected_source_root_revision=7,
        placement_selection=bound_selection,
        validated_target_facts=_target_facts(),
        capability_receipt=receipt,
        current_binding=current_binding,
        current_action_surface=current_surface,
        principal_action_demand=action_demand,
        current_principal_action_facts=current_action_facts,
        expected_capability_contract_digest=(
            expected_contract_digest or receipt.capability_contract_digest
        ),
        expected_observer_evidence_digest=(
            expected_observer_digest or receipt.observer_evidence_digest
        ),
        expected_serviceability_evidence_digest=(
            expected_serviceability_digest
            or receipt.serviceability_evidence_digest
        ),
        now_ms=now_ms,
        start_state=start_state,
        effect_state=effect_state,
    )


def _observations(
    receipt: wcap.WebCeoSessionCapabilityReceipt,
) -> dict[str, wcap.CapabilityObservation]:
    return {item.name: item for item in receipt.observations}


def test_v3_receipt_v2_preflight_schema_and_guard_signature_are_pinned() -> None:
    assert wcap.RECEIPT_SCHEMA.endswith(".v3")
    assert wcap.PREFLIGHT_SCHEMA.endswith(".v2")
    assert "capability_preflight" not in inspect.signature(
        wcap.build_guarded_commitment_plan_from_selection_decision
    ).parameters
    assert "capability_receipt" in inspect.signature(
        wcap.build_guarded_commitment_plan_from_selection_decision
    ).parameters
    guard_parameters = inspect.signature(
        wcap.build_guarded_commitment_plan_from_selection_decision
    ).parameters
    assert "current_binding" in guard_parameters
    assert "current_action_surface" in guard_parameters
    assert "principal_action_demand" in guard_parameters
    assert "current_principal_action_facts" in guard_parameters
    assert "expected_principal_action_demand_digest" not in guard_parameters
    assert "expected_worker_route_evidence_digest" not in guard_parameters
    assert "required_capabilities" not in guard_parameters
    assert "receiver_binding_mode" not in guard_parameters


def test_effect_guard_refuses_selection_without_web_action_demand() -> None:
    receipt = _receipt()
    selection = _selection(
        required_capabilities=frozenset({"strategic_reasoning"})
    )
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="PRINCIPAL_ACTION_DEMAND_OUTSIDE_CONTRACT",
    ):
        _guard(receipt, selection=selection)


def test_effect_guard_derives_exact_session_mode_from_c1_demand() -> None:
    selection = _selection(
        required_capabilities=frozenset({"executive_submit"}),
        allowed_modes=frozenset({c1.PlacementMode.EXISTING_SESSION_REUSE}),
    )
    action_demand = _principal_action_demand(selection)
    current_action_facts = _principal_action_owner_facts(selection)
    required, mode = wcap._placement_action_requirements(
        selection,
        principal_action_demand=action_demand,
        current_principal_action_facts=current_action_facts,
    )
    assert required == frozenset({"executive_submit"})
    assert mode is wcap.ReceiverBindingMode.EXACT_SESSION_REQUIRED


def test_exact_fresh_action_capabilities_allow_guarded_commitment() -> None:
    receipt = _receipt()
    preflight = _assess(receipt)

    assert preflight.state is wcap.PreflightState.READY
    assert preflight.proven_capabilities == (
        "desktop_commander_write",
        "executive_submit",
        "studio_direct_write",
    )
    assert preflight.missing_capabilities == ()
    assert preflight.unknown_capabilities == ()

    plan = _guard(receipt)
    assert isinstance(plan, c2.PlacementCommitmentPlan)
    assert plan.selected_worker_id == "web-ceo-c3-astra"
    assert plan.selected_quota_class == "chatgpt-pro"


def test_principal_action_demand_wire_round_trip_is_closed() -> None:
    selection = _selection()
    action_demand = _principal_action_demand(
        selection,
        principal_required=frozenset(
            {"executive_submit", "studio_direct_write"}
        ),
    )
    rebuilt = c1.validate_principal_action_demand_receipt(
        action_demand.to_dict()
    )
    assert rebuilt == action_demand
    assert (
        rebuilt.selection_document_digest
        == c1.placement_selection_document_digest(selection)
    )


def test_principal_action_partition_digest_is_subset_bound() -> None:
    selection = _selection(
        required_capabilities=frozenset(
            {"executive_submit", "studio_direct_write"}
        )
    )
    canonical_facts = _principal_action_owner_facts(selection)
    canonical = c1.build_principal_action_demand_receipt(
        decision=selection,
        owner_facts=canonical_facts,
    )
    narrowed = _principal_action_owner_facts(
        selection,
        principal_required=frozenset({"executive_submit"}),
    )

    assert (
        narrowed.action_partition_evidence_digest
        != canonical.action_partition_evidence_digest
    )
    with pytest.raises(ValueError, match="action partition evidence digest mismatch"):
        c1.PrincipalActionDemandReceipt(
            selection_document_digest=canonical.selection_document_digest,
            principal_required_capabilities=narrowed.principal_required_capabilities,
            action_partition_source=canonical.action_partition_source,
            action_partition_evidence_digest=(
                canonical.action_partition_evidence_digest
            ),
            worker_route_source=canonical.worker_route_source,
            worker_route_evidence_digest=canonical.worker_route_evidence_digest,
        )


def test_principal_action_partition_requires_current_capacity_owner() -> None:
    selection = _selection()
    with pytest.raises(ValueError, match="action_partition_source owner must be capacity"):
        _principal_action_owner_facts(
            selection,
            action_partition_source=_source(
                SourceOwner.EXECUTIVE_OS,
                "executive-not-capacity-partition",
            ),
        )

    stale = SourceRef(
        owner=SourceOwner.CAPACITY,
        ref="capacity-action-partition-stale",
        observed_at="2026-09-19T00:00:00Z",
        freshness=Freshness.STALE,
    )
    with pytest.raises(ValueError, match="action_partition_source must be current"):
        _principal_action_owner_facts(
            selection,
            action_partition_source=stale,
        )


def test_worker_route_source_rollover_invalidates_principal_action_partition() -> None:
    selection = _selection(
        required_capabilities=frozenset({"executive_submit"})
    )
    action_demand = _principal_action_demand(selection)
    changed_route_facts = _principal_action_owner_facts(
        selection,
        worker_route_source=_source(
            SourceOwner.EXECUTIVE_OS,
            "executive-worker-route-generation-2",
        ),
    )

    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="PRINCIPAL_ACTION_DEMAND_RECONCILIATION_REQUIRED",
    ):
        _guard(
            _receipt(),
            selection=selection,
            principal_action_demand=action_demand,
            current_principal_action_facts=changed_route_facts,
        )


def test_worker_local_host_write_does_not_block_principal_submit_start() -> None:
    selection = _selection(
        required_capabilities=frozenset(
            {
                "executive_submit",
                "studio_direct_write",
                "desktop_commander_write",
            }
        )
    )
    action_demand = _principal_action_demand(
        selection,
        principal_required=frozenset({"executive_submit"}),
    )
    contracts = _contracts()
    exec_submit = next(
        item for item in contracts if item.capability == "executive_submit"
    )
    receipt = _receipt(
        contracts=contracts,
        schema_complete=True,
        effective_tools=exec_submit.required_actions,
        serviceability=tuple(
            _serviceability_fact(action)
            for action in exec_submit.required_actions
        ),
    )

    plan = _guard(
        receipt,
        selection=selection,
        principal_action_demand=action_demand,
    )
    assert isinstance(plan, c2.PlacementCommitmentPlan)


def test_principal_local_host_write_still_requires_exact_serviceability() -> None:
    selection = _selection(
        required_capabilities=frozenset(
            {"executive_submit", "studio_direct_write"}
        )
    )
    action_demand = _principal_action_demand(selection)
    contracts = _contracts()
    exec_submit = next(
        item for item in contracts if item.capability == "executive_submit"
    )
    receipt = _receipt(
        contracts=contracts,
        schema_complete=True,
        effective_tools=exec_submit.required_actions,
        serviceability=tuple(
            _serviceability_fact(action)
            for action in exec_submit.required_actions
        ),
    )

    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="CAPABILITY_PREFLIGHT_NOT_READY",
    ):
        _guard(
            receipt,
            selection=selection,
            principal_action_demand=action_demand,
        )


def test_mixed_known_and_unclassified_principal_action_cannot_ready() -> None:
    selection = _selection(
        required_capabilities=frozenset(
            {"executive_submit", "future_web_action"}
        )
    )
    action_demand = _principal_action_demand(selection)
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="PRINCIPAL_ACTION_DEMAND_OUTSIDE_CONTRACT",
    ):
        _guard(
            _receipt(),
            selection=selection,
            principal_action_demand=action_demand,
        )


def test_principal_action_subset_is_bound_and_cannot_be_caller_narrowed() -> None:
    selection = _selection(
        required_capabilities=frozenset(
            {"executive_submit", "studio_direct_write"}
        )
    )
    canonical_facts = _principal_action_owner_facts(selection)
    canonical = c1.build_principal_action_demand_receipt(
        decision=selection,
        owner_facts=canonical_facts,
    )
    narrowed = _principal_action_demand(
        selection,
        principal_required=frozenset({"executive_submit"}),
    )
    assert narrowed.evidence_digest != canonical.evidence_digest
    assert (
        narrowed.action_partition_evidence_digest
        != canonical.action_partition_evidence_digest
    )

    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="PRINCIPAL_ACTION_DEMAND_RECONCILIATION_REQUIRED",
    ):
        _guard(
            _receipt(),
            selection=selection,
            principal_action_demand=narrowed,
            current_principal_action_facts=canonical_facts,
        )


def test_worker_route_change_invalidates_principal_action_partition() -> None:
    selection = _selection(
        required_capabilities=frozenset({"executive_submit"})
    )
    action_demand = _principal_action_demand(selection)
    changed_route_facts = _principal_action_owner_facts(
        selection,
        worker_route_digest="c" * 64,
    )

    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="PRINCIPAL_ACTION_DEMAND_RECONCILIATION_REQUIRED",
    ):
        _guard(
            _receipt(),
            selection=selection,
            principal_action_demand=action_demand,
            current_principal_action_facts=changed_route_facts,
        )


def test_action_demand_for_different_selection_is_refused() -> None:
    original = _selection(
        required_capabilities=frozenset({"executive_submit"})
    )
    changed = _selection(
        required_capabilities=frozenset(
            {"executive_submit", "studio_direct_write"}
        )
    )
    action_demand = _principal_action_demand(original)

    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="PRINCIPAL_ACTION_DEMAND_RECONCILIATION_REQUIRED",
    ):
        _guard(
            _receipt(),
            selection=changed,
            principal_action_demand=action_demand,
        )


def test_github_read_only_astra_is_prestart_rebindable() -> None:
    contracts = _contracts()
    github_read = next(
        c for c in contracts if c.capability == "github_read"
    )
    receipt = _receipt(
        contracts=contracts,
        effective_tools=github_read.required_actions,
        serviceability=tuple(
            _serviceability_fact(action)
            for action in github_read.required_actions
        ),
    )

    states = _observations(receipt)
    assert states["github_read"].state is wcap.CapabilityObservationState.PRESENT
    assert states["executive_submit"].state is wcap.CapabilityObservationState.ABSENT
    assert (
        states["studio_direct_write"].state
        is wcap.CapabilityObservationState.ABSENT
    )
    assert (
        states["desktop_commander_write"].state
        is wcap.CapabilityObservationState.ABSENT
    )

    preflight = _assess(receipt)
    assert preflight.state is wcap.PreflightState.PRESTART_REBIND_REQUIRED
    assert preflight.rebind_allowed is True
    assert preflight.exclusion == {
        "worker_id": "web-ceo-c3-astra",
        "quota_class": "chatgpt-pro",
        "reason": "effective_capability_missing",
    }
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="CAPABILITY_PREFLIGHT_NOT_READY",
    ):
        _guard(receipt)


def test_exact_session_required_missing_action_never_rebinds() -> None:
    contracts = _contracts()
    github_read = next(
        c for c in contracts if c.capability == "github_read"
    )
    receipt = _receipt(
        contracts=contracts,
        effective_tools=github_read.required_actions,
        serviceability=tuple(
            _serviceability_fact(action)
            for action in github_read.required_actions
        ),
    )

    preflight = _assess(
        receipt,
        required=frozenset({"executive_submit"}),
        binding_mode=wcap.ReceiverBindingMode.EXACT_SESSION_REQUIRED,
    )
    assert preflight.state is wcap.PreflightState.EXACT_SESSION_BLOCKED
    assert preflight.rebind_allowed is False
    assert preflight.exclusion is None


def test_visible_but_unprobed_action_remains_unknown() -> None:
    receipt = _receipt(serviceability=())
    preflight = _assess(receipt, required=frozenset({"executive_submit"}))

    assert preflight.state is wcap.PreflightState.CAPABILITY_PROOF_REQUIRED
    assert preflight.unknown_capabilities == ("executive_submit",)
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="CAPABILITY_PREFLIGHT_NOT_READY",
    ):
        _guard(
            receipt,
            selection=_selection(
                required_capabilities=frozenset({"executive_submit"})
            ),
        )


def test_failed_serviceability_probe_remains_unknown_not_absent() -> None:
    contracts = _contracts()
    exec_submit = next(
        c for c in contracts if c.capability == "executive_submit"
    )
    failed_name = exec_submit.required_actions[0].tool_name
    probes = tuple(
        _serviceability_fact(
            action,
            serviceable=action.tool_name != failed_name,
        )
        for action in _all_actions(contracts)
    )
    receipt = _receipt(contracts=contracts, serviceability=probes)

    observation = _observations(receipt)["executive_submit"]
    assert observation.state is wcap.CapabilityObservationState.UNKNOWN
    assert observation.proof_class is wcap.CapabilityProofClass.NO_EFFECT_PROBE
    assert (
        _assess(receipt, required=frozenset({"executive_submit"})).state
        is wcap.PreflightState.CAPABILITY_PROOF_REQUIRED
    )


def test_incomplete_surface_omission_stays_unknown_and_never_rebinds() -> None:
    contracts = _contracts()
    github_read = next(
        c for c in contracts if c.capability == "github_read"
    )
    receipt = _receipt(
        contracts=contracts,
        schema_complete=False,
        effective_tools=github_read.required_actions,
        serviceability=tuple(
            _serviceability_fact(action)
            for action in github_read.required_actions
        ),
    )

    observation = _observations(receipt)["executive_submit"]
    assert observation.state is wcap.CapabilityObservationState.UNKNOWN
    assert observation.proof_class is wcap.CapabilityProofClass.EFFECTIVE_SCHEMA

    preflight = _assess(
        receipt,
        required=frozenset({"executive_submit"}),
    )
    assert preflight.state is wcap.PreflightState.CAPABILITY_PROOF_REQUIRED
    assert preflight.rebind_allowed is False
    assert preflight.missing_capabilities == ()
    assert preflight.unknown_capabilities == ("executive_submit",)


def test_incomplete_surface_exact_positive_facts_can_prove_exact_action() -> None:
    contracts = _contracts()
    exec_submit = next(
        c for c in contracts if c.capability == "executive_submit"
    )
    receipt = _receipt(
        contracts=contracts,
        schema_complete=False,
        effective_tools=(),
        serviceability=tuple(
            _serviceability_fact(action)
            for action in exec_submit.required_actions
        ),
    )

    observation = _observations(receipt)["executive_submit"]
    assert observation.state is wcap.CapabilityObservationState.PRESENT
    assert observation.proof_class is wcap.CapabilityProofClass.NO_EFFECT_PROBE
    assert (
        _assess(receipt, required=frozenset({"executive_submit"})).state
        is wcap.PreflightState.READY
    )


def test_incomplete_surface_failed_probe_stays_unknown() -> None:
    contracts = _contracts()
    exec_submit = next(
        c for c in contracts if c.capability == "executive_submit"
    )
    facts = tuple(
        _serviceability_fact(
            action,
            serviceable=index != 0,
        )
        for index, action in enumerate(exec_submit.required_actions)
    )
    receipt = _receipt(
        contracts=contracts,
        schema_complete=False,
        effective_tools=(),
        serviceability=facts,
    )

    observation = _observations(receipt)["executive_submit"]
    assert observation.state is wcap.CapabilityObservationState.UNKNOWN
    assert observation.proof_class is wcap.CapabilityProofClass.NO_EFFECT_PROBE
    assert (
        _assess(receipt, required=frozenset({"executive_submit"})).state
        is wcap.PreflightState.CAPABILITY_PROOF_REQUIRED
    )


def test_complete_surface_absence_conflicting_positive_fact_refuses() -> None:
    contracts = _contracts()
    exec_submit = next(
        c for c in contracts if c.capability == "executive_submit"
    )
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="COMPLETE_SCHEMA_CONTRADICTS_POSITIVE_SERVICEABILITY",
    ):
        _receipt(
            contracts=contracts,
            schema_complete=True,
            effective_tools=(),
            serviceability=tuple(
                _serviceability_fact(action)
                for action in exec_submit.required_actions
            ),
        )


def test_tool_schema_digest_binds_completeness_fact() -> None:
    contracts = _contracts()
    github_read = next(
        c for c in contracts if c.capability == "github_read"
    )
    tools = github_read.required_actions
    serviceability = tuple(
        _serviceability_fact(action)
        for action in github_read.required_actions
    )
    complete = _receipt(
        contracts=contracts,
        schema_complete=True,
        effective_tools=tools,
        serviceability=serviceability,
    )
    incomplete = _receipt(
        contracts=contracts,
        schema_complete=False,
        effective_tools=tools,
        serviceability=serviceability,
    )
    assert complete.tool_schema_digest != incomplete.tool_schema_digest


def test_effect_unknown_freezes_prestart_failover() -> None:
    contracts = _contracts()
    github_read = next(
        c for c in contracts if c.capability == "github_read"
    )
    receipt = _receipt(
        contracts=contracts,
        effective_tools=github_read.required_actions,
        serviceability=tuple(
            _serviceability_fact(action)
            for action in github_read.required_actions
        ),
    )
    preflight = _assess(
        receipt,
        required=frozenset({"executive_submit"}),
        effect_state=EffectState.EFFECT_UNKNOWN,
    )
    assert preflight.state is wcap.PreflightState.EFFECT_UNKNOWN
    assert preflight.rebind_allowed is False


def test_started_session_with_lost_action_is_sticky_degraded() -> None:
    contracts = _contracts()
    github_read = next(
        c for c in contracts if c.capability == "github_read"
    )
    receipt = _receipt(
        contracts=contracts,
        effective_tools=github_read.required_actions,
        serviceability=tuple(
            _serviceability_fact(action)
            for action in github_read.required_actions
        ),
    )
    preflight = _assess(
        receipt,
        required=frozenset({"executive_submit"}),
        start_state=wcap.SessionStartState.STARTED,
    )
    assert preflight.state is wcap.PreflightState.STICKY_DEGRADED
    assert preflight.rebind_allowed is False


def test_started_healthy_session_is_started_sticky_not_ready_for_new_commit() -> None:
    receipt = _receipt()
    preflight = _assess(
        receipt,
        required=frozenset({"executive_submit"}),
        start_state=wcap.SessionStartState.STARTED,
    )
    assert preflight.state is wcap.PreflightState.STARTED_STICKY


def test_stale_capability_receipt_fails_closed() -> None:
    receipt = _receipt(expires_at_ms=OBSERVED_AT_MS + 30_000)
    preflight = _assess(
        receipt,
        required=frozenset({"executive_submit"}),
        now_ms=OBSERVED_AT_MS + 60_000,
    )
    assert preflight.state is wcap.PreflightState.STALE_EVIDENCE


@pytest.mark.parametrize(
    "binding",
    [
        _binding(session_ref="websol-c3-session-18"),
        _binding(binding_ref="runtimebinding-websol-c3-18"),
        _binding(binding_generation=8),
        _binding(worker_id="web-ceo-c4-sol"),
        _binding(quota_class="chatgpt-business"),
    ],
)
def test_action_time_binding_rollover_requires_reconciliation(
    binding: wcap.CurrentSessionBindingFacts,
) -> None:
    receipt = _receipt()
    preflight = _assess(
        receipt,
        required=frozenset({"executive_submit"}),
        binding=binding,
    )
    assert preflight.state is wcap.PreflightState.RECONCILIATION_REQUIRED


@pytest.mark.parametrize(
    "binding",
    [
        _binding(session_ref="websol-c3-session-18"),
        _binding(binding_ref="runtimebinding-websol-c3-18"),
        _binding(binding_generation=8),
    ],
)
def test_guard_rereads_binding_and_catches_rollover(
    binding: wcap.CurrentSessionBindingFacts,
) -> None:
    receipt = _receipt()
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="CAPABILITY_PREFLIGHT_NOT_READY",
    ):
        _guard(
            receipt,
            selection=_selection(
                required_capabilities=frozenset({"executive_submit"})
            ),
            binding=binding,
        )


def test_guard_rejects_selection_current_binding_mismatch_before_c2() -> None:
    receipt = _receipt()
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="CAPABILITY_PREFLIGHT_SELECTION_MISMATCH",
    ):
        _guard(
            receipt,
            selection=_selection(worker_id="web-ceo-c4-sol"),
        )


def test_contract_digest_drift_requires_reconciliation() -> None:
    receipt = _receipt()
    preflight = _assess(
        receipt,
        required=frozenset({"executive_submit"}),
        expected_contract_digest="f" * 64,
    )
    assert preflight.state is wcap.PreflightState.RECONCILIATION_REQUIRED
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="CAPABILITY_PREFLIGHT_NOT_READY",
    ):
        _guard(
            receipt,
            selection=_selection(
                required_capabilities=frozenset({"executive_submit"})
            ),
            expected_contract_digest="f" * 64,
        )


def test_observer_evidence_rollover_requires_reconciliation() -> None:
    receipt = _receipt()
    preflight = _assess(
        receipt,
        required=frozenset({"executive_submit"}),
        expected_observer_digest="f" * 64,
    )
    assert preflight.state is wcap.PreflightState.RECONCILIATION_REQUIRED
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="CAPABILITY_PREFLIGHT_NOT_READY",
    ):
        _guard(
            receipt,
            selection=_selection(
                required_capabilities=frozenset({"executive_submit"})
            ),
            expected_observer_digest="f" * 64,
        )


def test_complete_schema_receipt_requires_full_closed_vocabulary() -> None:
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="COMPLETE_SCHEMA_OBSERVATIONS_INCOMPLETE",
    ):
        wcap.WebCeoSessionCapabilityReceipt(
            worker_id="web-ceo-c3-astra",
            quota_class="chatgpt-pro",
            session_ref="websol-c3-session-17",
            binding_ref="runtimebinding-websol-c3-17",
            binding_generation=7,
            action_scope_ref=ACTION_SCOPE_REF,
            observed_at_ms=OBSERVED_AT_MS,
            expires_at_ms=EXPIRES_AT_MS,
            schema_complete=True,
            tool_schema_digest="a" * 64,
            capability_contract_digest="b" * 64,
            observer_evidence_digest="c" * 64,
            action_surface_evidence_digest="e" * 64,
            serviceability_evidence_digest="d" * 64,
            observations=(
                wcap.CapabilityObservation(
                    name="executive_submit",
                    state=wcap.CapabilityObservationState.UNKNOWN,
                    proof_class=wcap.CapabilityProofClass.EFFECTIVE_SCHEMA,
                ),
            ),
        )


def test_incomplete_schema_cannot_claim_absence() -> None:
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="ABSENCE_REQUIRES_COMPLETE_SCHEMA",
    ):
        wcap.WebCeoSessionCapabilityReceipt(
            worker_id="web-ceo-c3-astra",
            quota_class="chatgpt-pro",
            session_ref="websol-c3-session-17",
            binding_ref="runtimebinding-websol-c3-17",
            binding_generation=7,
            action_scope_ref=ACTION_SCOPE_REF,
            observed_at_ms=OBSERVED_AT_MS,
            expires_at_ms=EXPIRES_AT_MS,
            schema_complete=False,
            tool_schema_digest="a" * 64,
            capability_contract_digest="b" * 64,
            observer_evidence_digest="c" * 64,
            action_surface_evidence_digest="e" * 64,
            serviceability_evidence_digest="d" * 64,
            observations=(
                wcap.CapabilityObservation(
                    name="executive_submit",
                    state=wcap.CapabilityObservationState.ABSENT,
                    proof_class=wcap.CapabilityProofClass.EFFECTIVE_SCHEMA,
                ),
            ),
        )


def test_foreign_capability_is_rejected_in_observation() -> None:
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="CAPABILITY_OUTSIDE_CLOSED_SET",
    ):
        wcap.CapabilityObservation(
            name="invented_super_write",
            state=wcap.CapabilityObservationState.UNKNOWN,
            proof_class=wcap.CapabilityProofClass.EFFECTIVE_SCHEMA,
        )


def test_foreign_required_capability_is_rejected() -> None:
    receipt = _receipt()
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="CAPABILITY_OUTSIDE_CLOSED_SET",
    ):
        _assess(
            receipt,
            required=frozenset({"invented_super_write"}),
        )


def test_hand_built_ready_with_empty_proven_partition_is_refused() -> None:
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="PREFLIGHT_PARTITION_INVALID|READY_PREFLIGHT_INVALID",
    ):
        wcap.WebCeoCapabilityPreflightDecision(
            state=wcap.PreflightState.READY,
            receiver_binding_mode=wcap.ReceiverBindingMode.CAPACITY_SELECTABLE,
            worker_id="web-ceo-c3-astra",
            quota_class="chatgpt-pro",
            session_ref="websol-c3-session-17",
            binding_ref="runtimebinding-websol-c3-17",
            binding_generation=7,
            action_scope_ref=ACTION_SCOPE_REF,
            capability_contract_digest="b" * 64,
            required_capabilities=("executive_submit",),
            proven_capabilities=(),
            missing_capabilities=(),
            unknown_capabilities=(),
            evidence_digest="c" * 64,
            rebind_allowed=False,
            exclusion=None,
        )


def test_decision_partition_must_be_disjoint_and_complete() -> None:
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="PREFLIGHT_PARTITION_INVALID",
    ):
        wcap.WebCeoCapabilityPreflightDecision(
            state=wcap.PreflightState.RECONCILIATION_REQUIRED,
            receiver_binding_mode=wcap.ReceiverBindingMode.CAPACITY_SELECTABLE,
            worker_id="web-ceo-c3-astra",
            quota_class="chatgpt-pro",
            session_ref="websol-c3-session-17",
            binding_ref="runtimebinding-websol-c3-17",
            binding_generation=7,
            action_scope_ref=ACTION_SCOPE_REF,
            capability_contract_digest="b" * 64,
            required_capabilities=("executive_submit",),
            proven_capabilities=("executive_submit",),
            missing_capabilities=("executive_submit",),
            unknown_capabilities=(),
            evidence_digest="c" * 64,
            rebind_allowed=False,
            exclusion=None,
        )


def test_one_exposed_action_cannot_prove_unexposed_sibling_action() -> None:
    contracts = _contracts()
    github_write = next(
        c for c in contracts if c.capability == "github_write"
    )
    one_action = (github_write.required_actions[0],)

    receipt = _receipt(
        contracts=contracts,
        effective_tools=one_action,
        serviceability=(),
    )
    assert (
        _observations(receipt)["github_write"].state
        is wcap.CapabilityObservationState.ABSENT
    )

    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="SERVICEABILITY_FACT_WITHOUT_SURFACE",
    ):
        _receipt(
            contracts=contracts,
            effective_tools=one_action,
            serviceability=(
                _serviceability_fact(github_write.required_actions[0]),
            ),
        )


def test_every_required_action_needs_its_own_serviceability_proof() -> None:
    contracts = _contracts()
    github_write = next(
        c for c in contracts if c.capability == "github_write"
    )
    probes = (
        _serviceability_fact(github_write.required_actions[0]),
    )
    receipt = _receipt(
        contracts=contracts,
        effective_tools=_all_actions(contracts),
        serviceability=probes,
    )
    observation = _observations(receipt)["github_write"]
    assert observation.state is wcap.CapabilityObservationState.UNKNOWN
    assert (
        _assess(receipt, required=frozenset({"github_write"})).state
        is wcap.PreflightState.CAPABILITY_PROOF_REQUIRED
    )


def test_same_action_name_with_changed_invocation_schema_is_unknown() -> None:
    contracts = _contracts()
    exec_submit = next(
        c for c in contracts if c.capability == "executive_submit"
    )
    expected = exec_submit.required_actions[0]
    changed = wcap.EffectiveToolDescriptor(
        tool_name=expected.tool_name,
        invocation_schema_digest="f" * 64,
    )
    tools = tuple(
        changed if item.tool_name == expected.tool_name else item
        for item in _all_actions(contracts)
    )
    probes = tuple(
        fact
        for fact in _all_serviceable(contracts)
        if fact.tool.tool_name != expected.tool_name
    )
    receipt = _receipt(
        contracts=contracts,
        effective_tools=tools,
        serviceability=probes,
    )
    observation = _observations(receipt)["executive_submit"]
    assert observation.state is wcap.CapabilityObservationState.UNKNOWN
    assert (
        _assess(
            receipt,
            required=frozenset({"executive_submit"}),
        ).state
        is wcap.PreflightState.CAPABILITY_PROOF_REQUIRED
    )


def test_schema_drift_rejects_false_positive_serviceability() -> None:
    contracts = _contracts()
    exec_submit = next(
        c for c in contracts if c.capability == "executive_submit"
    )
    expected = exec_submit.required_actions[0]
    changed = wcap.EffectiveToolDescriptor(
        tool_name=expected.tool_name,
        invocation_schema_digest="f" * 64,
    )
    tools = tuple(
        changed if item.tool_name == expected.tool_name else item
        for item in _all_actions(contracts)
    )
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="SERVICEABILITY_FACT_WITH_SCHEMA_DRIFT",
    ):
        _receipt(
            contracts=contracts,
            effective_tools=tools,
            serviceability=(_serviceability_fact(expected),),
        )


def test_prefix_spoof_namespace_does_not_match_exact_action_contract() -> None:
    contracts = _contracts()
    github_read = next(c for c in contracts if c.capability == "github_read")
    expected = github_read.required_actions[0]
    spoof = wcap.EffectiveToolDescriptor(
        tool_name="mcp__GitHub_Evil__fetch_file",
        invocation_schema_digest=expected.invocation_schema_digest,
    )
    receipt = _receipt(
        contracts=contracts,
        effective_tools=(spoof,),
        serviceability=(),
    )
    assert (
        _observations(receipt)["github_read"].state
        is wcap.CapabilityObservationState.ABSENT
    )


def test_serviceability_fact_outside_contract_is_refused() -> None:
    evil = _descriptor("mcp__GitHub_Evil__update_file", "e")
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="SERVICEABILITY_FACT_OUTSIDE_CONTRACT",
    ):
        _receipt(
            serviceability=(_serviceability_fact(evil),),
        )


def test_serviceability_fact_binding_mismatch_is_refused() -> None:
    action = _all_actions()[0]
    fact = _serviceability_fact(
        action,
        binding_generation=8,
    )
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="SERVICEABILITY_FACT_BINDING_MISMATCH",
    ):
        _receipt(serviceability=(fact,))


def test_serviceability_fact_must_cover_receipt_ttl() -> None:
    action = _all_actions()[0]
    fact = _serviceability_fact(
        action,
        expires_at_ms=OBSERVED_AT_MS + 30_000,
    )
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="SERVICEABILITY_FACT_NOT_CURRENT_FOR_RECEIPT",
    ):
        _receipt(serviceability=(fact,))


def test_serviceability_fact_schema_mismatch_is_refused() -> None:
    action = _all_actions()[0]
    changed = wcap.EffectiveToolDescriptor(
        tool_name=action.tool_name,
        invocation_schema_digest="0" * 64,
    )
    fact = _serviceability_fact(changed)
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="SERVICEABILITY_FACT_SCHEMA_MISMATCH",
    ):
        _receipt(serviceability=(fact,))


def test_serviceability_owner_digest_rollover_requires_reconciliation() -> None:
    receipt = _receipt()
    preflight = _assess(
        receipt,
        required=frozenset({"executive_submit"}),
        expected_serviceability_digest="0" * 64,
    )
    assert preflight.state is wcap.PreflightState.RECONCILIATION_REQUIRED
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="CAPABILITY_PREFLIGHT_NOT_READY",
    ):
        _guard(
            receipt,
            selection=_selection(
                required_capabilities=frozenset({"executive_submit"})
            ),
            expected_serviceability_digest="0" * 64,
        )


def test_serviceability_evidence_digest_binds_exact_fact_result() -> None:
    contracts = _contracts()
    action = _all_actions(contracts)[0]
    healthy = _receipt(contracts=contracts)
    changed_facts = tuple(
        _serviceability_fact(
            item,
            serviceable=item.tool_name != action.tool_name,
        )
        for item in _all_actions(contracts)
    )
    degraded = _receipt(
        contracts=contracts,
        serviceability=changed_facts,
    )
    assert (
        healthy.serviceability_evidence_digest
        != degraded.serviceability_evidence_digest
    )


def test_capability_contracts_must_cover_entire_closed_vocabulary() -> None:
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="CAPABILITY_ACTION_CONTRACTS_INCOMPLETE",
    ):
        wcap.build_receipt_from_effective_tool_schema(
            effective_tools=(),
            capability_contracts=_contracts()[:-1],
            schema_complete=True,
            observer_evidence_digest=OBSERVER_DIGEST,
            worker_id="web-ceo-c3-astra",
            quota_class="chatgpt-pro",
            session_ref="websol-c3-session-17",
            binding_ref="runtimebinding-websol-c3-17",
            binding_generation=7,
            action_surface=_action_surface(),
            observed_at_ms=OBSERVED_AT_MS,
            expires_at_ms=EXPIRES_AT_MS,
            action_serviceability=(),
        )


def test_tool_schema_digest_binds_invocation_schema_digest() -> None:
    contracts = _contracts()
    receipt_a = _receipt(contracts=contracts)
    action = _all_actions(contracts)[0]
    changed = wcap.EffectiveToolDescriptor(
        tool_name=action.tool_name,
        invocation_schema_digest="f" * 64,
    )
    tools = tuple(
        changed if item.tool_name == action.tool_name else item
        for item in _all_actions(contracts)
    )
    probes = tuple(
        fact
        for fact in _all_serviceable(contracts)
        if fact.tool.tool_name != action.tool_name
    )
    receipt_b = _receipt(
        contracts=contracts,
        effective_tools=tools,
        serviceability=probes,
    )
    assert receipt_a.tool_schema_digest != receipt_b.tool_schema_digest


def test_receipt_wire_round_trip_is_closed_and_deterministic() -> None:
    receipt = _receipt()
    rebuilt = wcap.validate_session_capability_receipt(receipt.to_dict())
    assert rebuilt == receipt
    assert rebuilt.evidence_digest == receipt.evidence_digest

    forged = dict(receipt.to_dict())
    forged["authority"] = "chairman"
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="CAPABILITY_RECEIPT_SHAPE_INVALID",
    ):
        wcap.validate_session_capability_receipt(forged)


def test_receipt_wire_digest_detects_mutation() -> None:
    receipt = _receipt()
    forged = receipt.to_dict()
    forged["binding_generation"] = 8
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="CAPABILITY_RECEIPT_DIGEST_MISMATCH",
    ):
        wcap.validate_session_capability_receipt(forged)


def test_guarded_c2_plan_does_not_persist_private_session_or_tool_coordinates() -> None:
    receipt = _receipt()
    plan = _guard(receipt)
    wire = plan.to_dict()
    rendered = str(wire)

    assert "websol-c3-session-17" not in rendered
    assert "runtimebinding-websol-c3-17" not in rendered
    assert ACTION_SCOPE_REF not in rendered
    assert "action_scope_ref" not in wire
    assert receipt.tool_schema_digest not in rendered
    assert receipt.observer_evidence_digest not in rendered
    assert receipt.capability_contract_digest not in rendered
    assert "provider_session_id" not in wire
    assert "binding_ref" not in wire


def test_preflight_projection_carries_binding_mode_but_never_grants_authority() -> None:
    receipt = _receipt()
    projection = _assess(
        receipt,
        required=frozenset({"executive_submit"}),
        binding_mode=wcap.ReceiverBindingMode.EXACT_SESSION_REQUIRED,
    ).to_dict()

    assert projection["schema_version"] == wcap.PREFLIGHT_SCHEMA
    assert projection["state"] == "ready"
    assert projection["receiver_binding_mode"] == "exact_session_required"
    assert projection["selection_is_commitment"] is False
    assert "authority" not in projection
    assert "provider_session_id" not in projection


def test_prestart_applied_effect_requires_reconciliation() -> None:
    receipt = _receipt()
    preflight = _assess(
        receipt,
        required=frozenset({"executive_submit"}),
        effect_state=EffectState.APPLIED,
    )
    assert preflight.state is wcap.PreflightState.RECONCILIATION_REQUIRED


def test_complete_schema_observation_names_are_exact_closed_set() -> None:
    receipt = _receipt()
    assert tuple(item.name for item in receipt.observations) == tuple(
        sorted(wcap.KNOWN_EFFECTIVE_CAPABILITIES)
    )


def test_observer_evidence_digest_is_bound_into_receipt_digest() -> None:
    receipt = _receipt()
    changed = wcap.WebCeoSessionCapabilityReceipt(
        worker_id=receipt.worker_id,
        quota_class=receipt.quota_class,
        session_ref=receipt.session_ref,
        binding_ref=receipt.binding_ref,
        binding_generation=receipt.binding_generation,
        action_scope_ref=receipt.action_scope_ref,
        observed_at_ms=receipt.observed_at_ms,
        expires_at_ms=receipt.expires_at_ms,
        schema_complete=receipt.schema_complete,
        tool_schema_digest=receipt.tool_schema_digest,
        capability_contract_digest=receipt.capability_contract_digest,
        observer_evidence_digest="f" * 64,
        action_surface_evidence_digest=receipt.action_surface_evidence_digest,
        serviceability_evidence_digest=receipt.serviceability_evidence_digest,
        observations=receipt.observations,
    )
    assert changed.evidence_digest != receipt.evidence_digest


def test_serviceability_fact_from_different_action_scope_refuses_receipt() -> None:
    contracts = _contracts()
    probes = tuple(
        _serviceability_fact(
            action,
            action_scope_ref=(
                "web-message-scope-previous"
                if index == 0
                else ACTION_SCOPE_REF
            ),
        )
        for index, action in enumerate(_all_actions(contracts))
    )
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="SERVICEABILITY_FACT_BINDING_MISMATCH",
    ):
        _receipt(contracts=contracts, serviceability=probes)


def test_same_session_binding_but_changed_action_scope_requires_reconciliation() -> None:
    receipt = _receipt()
    preflight = _assess(
        receipt,
        required=frozenset({"executive_submit"}),
        action_surface=_action_surface(
            action_scope_ref="web-message-scope-43"
        ),
    )
    assert preflight.state is wcap.PreflightState.RECONCILIATION_REQUIRED
    assert preflight.rebind_allowed is False


def test_action_surface_binding_must_match_current_runtime_binding() -> None:
    receipt = _receipt()
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="ACTION_SURFACE_BINDING_MISMATCH",
    ):
        _guard(
            receipt,
            action_surface=_action_surface(binding_generation=8),
        )


def test_guard_refuses_action_scope_rollover_before_c2(monkeypatch) -> None:
    receipt = _receipt()
    called = {"count": 0}

    def _unexpected_c2(**kwargs):
        called["count"] += 1
        raise AssertionError("unguarded C2 call")

    monkeypatch.setattr(
        c2,
        "build_commitment_plan_from_selection_decision",
        _unexpected_c2,
    )
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="CAPABILITY_PREFLIGHT_NOT_READY",
    ):
        _guard(
            receipt,
            selection=_selection(
                required_capabilities=frozenset({"executive_submit"})
            ),
            action_surface=_action_surface(
                action_scope_ref="web-message-scope-43"
            ),
        )
    assert called["count"] == 0


def test_action_surface_requires_surface_bindings_owner() -> None:
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="ACTION_SURFACE_OWNER_INVALID",
    ):
        _action_surface(
            source=_source(SourceOwner.CAPACITY, "forged-capacity-surface"),
        )


def test_action_surface_requires_current_owner_source() -> None:
    stale = SourceRef(
        owner=SourceOwner.SURFACE_BINDINGS,
        ref="surface-bindings-stale",
        observed_at="2026-09-19T00:00:00Z",
        freshness=Freshness.STALE,
    )
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="ACTION_SURFACE_SOURCE_NOT_CURRENT",
    ):
        _action_surface(source=stale)


def test_same_scope_but_changed_surface_evidence_cannot_reach_c2(monkeypatch) -> None:
    receipt = _receipt()
    changed_surface = _action_surface(
        source=_source(
            SourceOwner.SURFACE_BINDINGS,
            "surface-bindings-web-message-scope-generation-2",
        )
    )
    assert changed_surface.action_scope_ref == receipt.action_scope_ref
    assert (
        changed_surface.evidence_digest
        != receipt.action_surface_evidence_digest
    )
    called = {"count": 0}

    def _unexpected_c2(**kwargs):
        called["count"] += 1
        raise AssertionError("unguarded C2 call")

    monkeypatch.setattr(
        c2,
        "build_commitment_plan_from_selection_decision",
        _unexpected_c2,
    )
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="CAPABILITY_PREFLIGHT_NOT_READY",
    ):
        _guard(
            receipt,
            selection=_selection(
                required_capabilities=frozenset({"executive_submit"})
            ),
            action_surface=changed_surface,
        )
    assert called["count"] == 0


def test_expired_action_surface_refuses_before_c2(monkeypatch) -> None:
    receipt = _receipt()
    expired = _action_surface(
        observed_at_ms=NOW_MS - 10_000,
        expires_at_ms=NOW_MS - 1,
    )
    called = {"count": 0}

    def _unexpected_c2(**kwargs):
        called["count"] += 1
        raise AssertionError("unguarded C2 call")

    monkeypatch.setattr(
        c2,
        "build_commitment_plan_from_selection_decision",
        _unexpected_c2,
    )
    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="ACTION_SURFACE_NOT_CURRENT",
    ):
        _guard(
            receipt,
            selection=_selection(
                required_capabilities=frozenset({"executive_submit"})
            ),
            action_surface=expired,
        )
    assert called["count"] == 0


def test_receipt_digest_binds_owner_issued_action_surface_evidence() -> None:
    first_surface = _action_surface()
    second_surface = _action_surface(
        source=_source(
            SourceOwner.SURFACE_BINDINGS,
            "surface-bindings-web-message-scope-generation-2",
        )
    )
    first = _receipt(action_surface=first_surface)
    second = _receipt(action_surface=second_surface)

    assert first.action_scope_ref == second.action_scope_ref
    assert first.action_surface_evidence_digest != second.action_surface_evidence_digest
    assert first.evidence_digest != second.evidence_digest


def test_current_owner_surface_allows_existing_guard_and_stays_private() -> None:
    surface = _action_surface()
    receipt = _receipt(action_surface=surface)
    plan = _guard(receipt, action_surface=surface)
    rendered = str(plan.to_dict())

    assert isinstance(plan, c2.PlacementCommitmentPlan)
    assert surface.action_scope_ref not in rendered
    assert surface.evidence_digest not in rendered
    assert surface.source.ref not in rendered


def test_serviceability_from_prior_same_scope_surface_evidence_refuses_receipt() -> None:
    contracts = _contracts()
    prior_surface = _action_surface()
    current_surface = _action_surface(
        source=_source(
            SourceOwner.SURFACE_BINDINGS,
            "surface-bindings-web-message-scope-generation-2",
        )
    )
    assert prior_surface.action_scope_ref == current_surface.action_scope_ref
    assert prior_surface.evidence_digest != current_surface.evidence_digest

    stale_probes = tuple(
        _serviceability_fact(
            action,
            action_scope_ref=prior_surface.action_scope_ref,
            action_surface_evidence_digest=prior_surface.evidence_digest,
        )
        for action in _all_actions(contracts)
    )

    with pytest.raises(
        wcap.WebCeoSessionCapabilityError,
        match="SERVICEABILITY_FACT_SURFACE_EVIDENCE_MISMATCH",
    ):
        _receipt(
            contracts=contracts,
            action_surface=current_surface,
            serviceability=stale_probes,
        )
