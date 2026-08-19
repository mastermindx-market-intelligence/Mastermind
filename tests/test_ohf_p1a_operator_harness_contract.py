"""OHF-P1A-R3 typed OperatorHarnessAdapter contract freeze."""
from __future__ import annotations

import dataclasses
import inspect
import re
from pathlib import Path
from typing import get_type_hints

import pytest

from control_plane.operator_harness_contract import (
    ACCOUNT_REALM_STATUS,
    ADAPTER_OBSERVED_IDS,
    ATTEMPT_BOUNDARY_MATRIX,
    AttemptBoundary,
    AttemptExecutionMode,
    AuthIdentityConfidence,
    AuthRealmFact,
    AuthRealmRequirement,
    CANONICAL_SESSION_FIELD,
    CARDINALITY,
    COMMAND_ID_RE,
    CRASH_WINDOW_MATRIX,
    CandidateResult,
    CapabilityClass,
    CapabilityIdentity,
    CapabilityManifest,
    EventCursor,
    EXECUTIVE_ALLOCATED_IDS,
    EXECUTIVE_OWNED_RECONCILE_FIELDS,
    FORBIDDEN_COMPARE_LAUNCH_PARAMETERS,
    FORBIDDEN_SESSION_SYNONYM,
    HarnessAdapterCapabilities,
    INVARIANT_ENFORCEMENT,
    LEGACY_SEALED_WORKER_ATTEMPT_FIELDS,
    LaunchDecision,
    LIVE_APP_SERVER_ADOPTION,
    METHOD_CONTRACTS,
    MethodClass,
    NativeHelperPolicy,
    OHF_FORBIDDEN_ATTEMPT_COLUMNS,
    OHF_PROPOSED_ATTEMPT_COLUMNS,
    OPERATOR_HARNESS_INTERFACE_VERSION,
    OPERATION_AGGREGATE_TYPE,
    OPERATION_COMMAND_ID_PREFIX,
    OPTIONAL_ADAPTER_PROTOCOLS,
    ObservedCapabilityIdentity,
    ObservedHarnessAttestation,
    ObservedTriState,
    OperationId,
    OperationIdempotencyClass,
    OperationReceiptKind,
    OperationResolution,
    OperatorHarnessAdapter,
    POST_RESTORE_ATTEMPT_STATUS,
    PREBIND_WRITER_FENCE_KEY,
    PROPOSED_SQL_INVARIANTS,
    ProcessGenerationRef,
    ProcessIdentityObservation,
    ProcessLiveness,
    ProviderWriterState,
    REATTEST_TRIGGERS,
    ReconcileObservation,
    RequestedExecutionProfile,
    SessionEpochRef,
    SessionEpochState,
    SessionStartObservation,
    StageConfigReceipt,
    SupportsApprovalResponse,
    SupportsCheckpoint,
    SupportsConfigStaging,
    SupportsNativeFork,
    SupportsProbe,
    SupportsSessionResume,
    SupportsSteering,
    TRANSACTION_GROUPS,
    TransactionGroup,
    TurnRef,
    TurnStartObservation,
    V1_QUALITY_TRADEOFF,
    WORKER_SLOT_AUTH_BINDING_PRODUCTION_INVARIANT,
    WRITER_REALM_KEY,
    WorkspaceIdentity,
    WriterFacts,
    abandon_epoch,
    adapter_method_returns_executive_id,
    classify_capability,
    compare_launch,
    compare_launch_parameter_names,
    derive_resume_safety,
    event_cursor_scoped_to,
    first_work_turn_allowed,
    may_abandon_epoch,
    may_bind_epoch_provider_session,
    may_bind_provider_session,
    may_hold_executive_writer,
    may_hold_prebind_epoch_writer,
    may_start_successor_rich_writer,
    native_helpers_allowed,
    operation_receipt_command_id,
    process_end_does_not_release_writer,
    restore_invalidation,
    rich_ohf_may_rewrite_legacy_attempt_field,
    resolve_operation_after_crash,
    writer_realm_key,
)


def _workspace() -> WorkspaceIdentity:
    return WorkspaceIdentity(
        workspace_path="/tmp/job-ws",
        base_sha="a" * 40,
        device=1,
        inode=2,
        uid=501,
        gid=20,
    )


def _requested(**overrides: object) -> RequestedExecutionProfile:
    payload = dict(
        worker_id="worker-1",
        provider="codex",
        requested_model="gpt-5.6-sol",
        harness_kind="codex-app-server",
        harness_binary_digest="digest-v1",
        harness_version="0.147.0",
        workspace=_workspace(),
        sandbox_policy="read-only",
        approval_policy="never",
        network_policy="restricted",
        capabilities=CapabilityManifest(
            required=(
                CapabilityIdentity(name="ohf-probe", harness_binary_digest="digest-v1"),
            ),
            forbidden=("codex_apps",),
        ),
        native_helper_policy=NativeHelperPolicy.DISABLED,
        authority_policy_hash="auth-hash",
        write_capable=False,
    )
    payload.update(overrides)
    return RequestedExecutionProfile(**payload)  # type: ignore[arg-type]


def _observed(**overrides: object) -> ObservedHarnessAttestation:
    payload = dict(
        served_model="gpt-5.6-sol",
        harness_version="0.147.0",
        harness_binary_digest="digest-v1",
        capabilities=(
            ObservedCapabilityIdentity(kind="skill", name="ohf-probe"),
        ),
        effective_skills=("ohf-probe",),
        effective_mcp=(),
        effective_plugins_or_apps=(),
        sandbox_state="read-only",
        approval_state="never",
        network_state="restricted",
        effective_config_digest="cfg",
        auth=AuthRealmFact(
            worker_id="worker-1",
            provider="codex",
            identity_confidence=AuthIdentityConfidence.UNKNOWN,
        ),
        workspace=_workspace(),
        supports_subagent_capability_ceiling=ObservedTriState.UNKNOWN,
    )
    payload.update(overrides)
    return ObservedHarnessAttestation(**payload)  # type: ignore[arg-type]


def test_cardinality_and_identity_constants():
    assert CARDINALITY == "CARDINALITY_B"
    assert CANONICAL_SESSION_FIELD == "provider_session_id"
    assert FORBIDDEN_SESSION_SYNONYM == "native_session_id"
    assert WRITER_REALM_KEY == ("worker_id", "provider_session_id")
    assert PREBIND_WRITER_FENCE_KEY == ("session_epoch_id",)
    assert LIVE_APP_SERVER_ADOPTION == "NOT_SUPPORTED"
    assert V1_QUALITY_TRADEOFF == "V1_QUALITY_TRADEOFF_ACCEPTED"
    assert ACCOUNT_REALM_STATUS == "ACCOUNT_REALM_ATTESTATION_UNPROVEN"
    assert OPERATOR_HARNESS_INTERFACE_VERSION == "mastermind.operator_harness/v1"
    assert OPERATION_AGGREGATE_TYPE == "operator_operation"
    assert "silently rebound" in WORKER_SLOT_AUTH_BINDING_PRODUCTION_INVARIANT
    source = Path("control_plane/operator_harness_contract.py").read_text(encoding="utf-8")
    assert "native_session_id" in source
    assert "current-epoch projection" not in source
    assert "current-generation projection" not in source


def test_execution_mode_and_legacy_attempt_fields_are_sealed_worker_only():
    assert AttemptExecutionMode.SEALED_WORKER.value == "SEALED_WORKER"
    assert AttemptExecutionMode.OPERATOR_HARNESS.value == "OPERATOR_HARNESS"
    for field_name in LEGACY_SEALED_WORKER_ATTEMPT_FIELDS:
        assert rich_ohf_may_rewrite_legacy_attempt_field(field_name) is False
    assert "execution_mode" in OHF_PROPOSED_ATTEMPT_COLUMNS
    assert "current_session_epoch_id" in OHF_FORBIDDEN_ATTEMPT_COLUMNS
    assert "current_process_generation_id" in OHF_FORBIDDEN_ATTEMPT_COLUMNS


def test_context_rotation_does_not_consume_attempt():
    assert ATTEMPT_BOUNDARY_MATRIX["context_rotation"] is AttemptBoundary.SAME_ATTEMPT
    assert ATTEMPT_BOUNDARY_MATRIX["fresh_primary_session_same_placement"] is AttemptBoundary.SAME_ATTEMPT
    assert ATTEMPT_BOUNDARY_MATRIX["sigkill_abandon_s1_start_s2"] is AttemptBoundary.SAME_ATTEMPT
    assert ATTEMPT_BOUNDARY_MATRIX["phase_1f_aggregation_after_leader_release"] is AttemptBoundary.NEW_ATTEMPT
    assert ATTEMPT_BOUNDARY_MATRIX["harness_binary_digest_change"] is AttemptBoundary.NEW_ATTEMPT
    assert ATTEMPT_BOUNDARY_MATRIX["cross_attempt_session_reuse"] is AttemptBoundary.REFUSE
    assert ATTEMPT_BOUNDARY_MATRIX["served_model_mismatch"] is AttemptBoundary.REFUSE
    assert ATTEMPT_BOUNDARY_MATRIX["served_model_unknown"] is AttemptBoundary.REFUSE


def test_writer_realm_allows_opaque_id_collision_across_workers():
    a = writer_realm_key("W1", "abc")
    b = writer_realm_key("W2", "abc")
    assert a != b
    bindings = {a: "epoch-1"}
    assert may_bind_provider_session(
        worker_id="W2",
        provider_session_id="abc",
        existing_bindings=bindings,
        epoch_id="epoch-2",
    )
    assert not may_bind_provider_session(
        worker_id="W1",
        provider_session_id="abc",
        existing_bindings=bindings,
        epoch_id="epoch-other",
    )


def test_prebind_second_writer_on_same_epoch_refused():
    held = {"epoch-1": "gen-A"}
    assert may_hold_prebind_epoch_writer(
        session_epoch_id="epoch-1",
        generation_id="gen-A",
        held_by_epoch=held,
    )
    assert not may_hold_prebind_epoch_writer(
        session_epoch_id="epoch-1",
        generation_id="gen-B",
        held_by_epoch=held,
    )
    assert may_hold_prebind_epoch_writer(
        session_epoch_id="epoch-2",
        generation_id="gen-C",
        held_by_epoch=held,
    )


def test_duplicate_writer_same_realm_refused():
    held = {writer_realm_key("W1", "S1"): "gen-A"}
    assert may_hold_executive_writer(
        worker_id="W1",
        provider_session_id="S1",
        generation_id="gen-A",
        held_by=held,
    )
    assert not may_hold_executive_writer(
        worker_id="W1",
        provider_session_id="S1",
        generation_id="gen-B",
        held_by=held,
    )
    assert may_hold_executive_writer(
        worker_id="W1",
        provider_session_id="S2",
        generation_id="gen-C",
        held_by=held,
    )


def test_provider_session_bind_is_immutable():
    assert may_bind_epoch_provider_session(
        epoch_provider_session_id=None, observed_provider_session_id="S1"
    )
    assert may_bind_epoch_provider_session(
        epoch_provider_session_id="S1", observed_provider_session_id="S1"
    )
    assert not may_bind_epoch_provider_session(
        epoch_provider_session_id="S1", observed_provider_session_id="S2"
    )


def test_process_death_does_not_release_executive_or_provider_writer():
    facts = WriterFacts(
        process_liveness=ProcessLiveness.ALIVE,
        executive_writer_held=True,
        provider_writer_state=ProviderWriterState.UNKNOWN,
    )
    after = process_end_does_not_release_writer(1, facts)
    assert after.process_liveness is ProcessLiveness.PROVEN_DEAD
    assert after.executive_writer_held is True
    assert after.provider_writer_state is ProviderWriterState.UNKNOWN
    assert derive_resume_safety(
        epoch_state=SessionEpochState.CURRENT,
        executive_writer_held=after.executive_writer_held,
        process_liveness=after.process_liveness,
        provider_writer_state=after.provider_writer_state,
        expected_process=ProcessIdentityObservation(
            pid=1, pgid=1, process_start_identity="start", boot_id="boot"
        ),
        observed_process=ProcessIdentityObservation(
            pid=1, pgid=1, process_start_identity="start", boot_id="boot"
        ),
        requested=_requested(),
        observed=_observed(),
    ) is False


def test_abandonment_does_not_invent_provider_released():
    blocked = WriterFacts(
        process_liveness=ProcessLiveness.PROVEN_DEAD,
        executive_writer_held=True,
        provider_writer_state=ProviderWriterState.HELD,
    )
    abandoned = abandon_epoch(blocked)
    assert abandoned.executive_writer_held is False
    assert abandoned.provider_writer_state is ProviderWriterState.HELD
    assert may_abandon_epoch(process_liveness=ProcessLiveness.PROVEN_DEAD)
    assert not may_abandon_epoch(process_liveness=ProcessLiveness.UNKNOWN)


def test_restore_preserves_historical_released_evidence():
    facts = WriterFacts(
        process_liveness=ProcessLiveness.ALIVE,
        executive_writer_held=True,
        provider_writer_state=ProviderWriterState.HELD,
    )
    invalidated = restore_invalidation(facts)
    assert invalidated.clear_executive_writer is True
    assert invalidated.abandon_epoch is True
    assert invalidated.historical_provider_writer_state is ProviderWriterState.HELD
    assert invalidated.historical_process_liveness is ProcessLiveness.ALIVE
    assert invalidated.attempt_status == POST_RESTORE_ATTEMPT_STATUS == "LOST"
    released = WriterFacts(
        process_liveness=ProcessLiveness.PROVEN_DEAD,
        executive_writer_held=True,
        provider_writer_state=ProviderWriterState.RELEASED,
    )
    restored_released = restore_invalidation(released)
    assert restored_released.historical_provider_writer_state is ProviderWriterState.RELEASED


def test_live_stdio_adoption_never_resume_safe():
    expected = ProcessIdentityObservation(
        pid=8, pgid=8, process_start_identity="start", boot_id="boot"
    )
    assert derive_resume_safety(
        epoch_state=SessionEpochState.CURRENT,
        executive_writer_held=True,
        process_liveness=ProcessLiveness.ALIVE,
        provider_writer_state=ProviderWriterState.HELD,
        expected_process=expected,
        observed_process=expected,
        requested=_requested(),
        observed=_observed(),
        live_transport_adoptable=True,
    ) is False


def test_launch_gate_and_served_model_mismatch():
    requested = _requested(write_capable=True)
    allow = compare_launch(requested, _observed())
    assert allow.decision is LaunchDecision.ALLOW
    assert first_work_turn_allowed(allow.decision)
    mismatch = compare_launch(requested, _observed(served_model="other-model"))
    assert mismatch.decision is LaunchDecision.REFUSE_SERVED_MODEL_MISMATCH
    assert not first_work_turn_allowed(mismatch.decision)
    unknown = compare_launch(requested, _observed(served_model=None))
    assert unknown.decision is LaunchDecision.REFUSE_SERVED_MODEL_UNKNOWN
    unclassified = compare_launch(
        requested,
        _observed(
            capabilities=(
                ObservedCapabilityIdentity(kind="skill", name="ohf-probe"),
                ObservedCapabilityIdentity(kind="plugin", name="github:create-pr"),
            ),
            effective_plugins_or_apps=("github:create-pr",),
        ),
    )
    assert unclassified.decision is LaunchDecision.REFUSE_UNCLASSIFIED
    assert "github:create-pr" in unclassified.unclassified


def test_lab_unclassified_requires_explicit_requested_policy():
    observed = _observed(
        capabilities=(
            ObservedCapabilityIdentity(kind="skill", name="ohf-probe"),
            ObservedCapabilityIdentity(kind="plugin", name="openai-templates:x"),
        ),
        effective_plugins_or_apps=("openai-templates:x",),
    )
    without_policy = compare_launch(_requested(write_capable=False), observed)
    assert without_policy.decision is LaunchDecision.REFUSE_UNCLASSIFIED
    with_policy = compare_launch(
        _requested(
            write_capable=False,
            capabilities=CapabilityManifest(
                required=(
                    CapabilityIdentity(name="ohf-probe", harness_binary_digest="digest-v1"),
                ),
                forbidden=("codex_apps",),
                unclassified_policy="lab_allow_unclassified_readonly",
            ),
        ),
        observed,
    )
    assert with_policy.decision is LaunchDecision.ALLOW


def test_compare_launch_has_no_caller_verdict_escape_hatch():
    names = set(compare_launch_parameter_names())
    assert names == {"requested", "observed"}
    assert names.isdisjoint(FORBIDDEN_COMPARE_LAUNCH_PARAMETERS)
    signature = str(inspect.signature(compare_launch))
    for banned in FORBIDDEN_COMPARE_LAUNCH_PARAMETERS:
        assert banned not in inspect.signature(compare_launch).parameters
        assert f"{banned}=" not in signature


def test_harness_workspace_sandbox_approval_config_are_derived():
    requested = _requested(expected_config_digest="cfg")
    assert compare_launch(
        requested, _observed(harness_binary_digest="other")
    ).decision is LaunchDecision.REFUSE_HARNESS_BINARY_MISMATCH
    assert compare_launch(
        requested, _observed(harness_binary_digest=None)
    ).decision is LaunchDecision.REFUSE_UNATTESTABLE
    other_ws = WorkspaceIdentity(
        workspace_path="/tmp/other",
        base_sha="b" * 40,
        device=1,
        inode=9,
        uid=501,
        gid=20,
    )
    assert compare_launch(
        requested, _observed(workspace=other_ws)
    ).decision is LaunchDecision.REFUSE_WORKSPACE_MISMATCH
    assert compare_launch(
        requested, _observed(sandbox_state="full")
    ).decision is LaunchDecision.REFUSE_SANDBOX_MISMATCH
    assert compare_launch(
        requested, _observed(approval_state="unless-trusted")
    ).decision is LaunchDecision.REFUSE_APPROVAL_MISMATCH
    assert compare_launch(
        requested, _observed(effective_config_digest="drifted")
    ).decision is LaunchDecision.REFUSE_CONFIG_DRIFT


def test_auth_requirement_is_explicit_and_has_no_default_true():
    requested = _requested(
        auth_realm_requirement=AuthRealmRequirement.VERIFIED_PROVIDER_ACCOUNT,
        expected_provider_account_id="acct-1",
    )
    unknown_account = compare_launch(requested, _observed())
    assert unknown_account.decision is LaunchDecision.REFUSE_AUTH_REALM_MISMATCH
    matched = compare_launch(
        requested,
        _observed(
            auth=AuthRealmFact(
                worker_id="worker-1",
                provider="codex",
                nonsecret_provider_account_id="acct-1",
                identity_confidence=AuthIdentityConfidence.PROVIDER_REPORTED,
            )
        ),
    )
    assert matched.decision is LaunchDecision.ALLOW
    slot_bound = compare_launch(_requested(), _observed())
    assert slot_bound.decision is LaunchDecision.ALLOW


def test_capability_classes_and_helpers():
    assert classify_capability(
        "ohf-probe", required=["ohf-probe"], allowed_ambient=[], forbidden=[]
    ) is CapabilityClass.REQUIRED
    assert classify_capability(
        "mystery", required=["ohf-probe"], allowed_ambient=[], forbidden=[]
    ) is CapabilityClass.UNCLASSIFIED
    assert native_helpers_allowed(
        write_capable=False,
        native_helper_policy=NativeHelperPolicy.PARENT_READ_ONLY_CEILING,
        supports_subagent_capability_ceiling=ObservedTriState.UNKNOWN,
    )
    assert not native_helpers_allowed(
        write_capable=True,
        native_helper_policy=NativeHelperPolicy.REQUIRES_SUBAGENT_CAPABILITY_CEILING,
        supports_subagent_capability_ceiling=ObservedTriState.UNKNOWN,
    )
    write_wrong_policy = compare_launch(
        _requested(
            write_capable=True,
            native_helper_policy=NativeHelperPolicy.PARENT_READ_ONLY_CEILING,
        ),
        _observed(),
    )
    assert write_wrong_policy.decision is LaunchDecision.REFUSE_HELPER_CEILING_MISSING
    forbidden = compare_launch(
        _requested(write_capable=True),
        _observed(
            capabilities=(
                ObservedCapabilityIdentity(kind="skill", name="ohf-probe"),
                ObservedCapabilityIdentity(kind="app", name="codex_apps"),
            ),
            effective_plugins_or_apps=("codex_apps",),
        ),
    )
    assert forbidden.decision is LaunchDecision.REFUSE_FORBIDDEN
    missing = compare_launch(
        _requested(write_capable=True),
        _observed(capabilities=(), effective_skills=(), effective_mcp=()),
    )
    assert missing.decision is LaunchDecision.REFUSE_MISSING_REQUIRED
    digest_required = compare_launch(
        _requested(
            capabilities=CapabilityManifest(
                required=(
                    CapabilityIdentity(
                        name="ohf-probe",
                        harness_binary_digest="digest-v1",
                        skill_content_digest="skill-digest",
                    ),
                )
            )
        ),
        _observed(),
    )
    assert digest_required.decision is LaunchDecision.REFUSE_MISSING_REQUIRED


def test_auth_realm_fact_rejects_credential_shaped_fields():
    with pytest.raises(ValueError):
        AuthRealmFact(worker_id="w", provider="codex", plan_type="refresh-token-xyz")
    fact = AuthRealmFact(worker_id="w", provider="codex")
    assert fact.attestation_status == ACCOUNT_REALM_STATUS
    assert fact.identity_confidence is AuthIdentityConfidence.UNKNOWN


def test_candidate_result_cannot_complete_job():
    with pytest.raises(ValueError):
        CandidateResult(
            attempt_id="a",
            session_epoch_id="e",
            process_generation_id="g",
            artifact_digest=None,
            summary="done",
            complete_job_permitted=True,
        )


def test_reconcile_observation_cannot_assert_executive_facts():
    names = {item.name for item in dataclasses.fields(ReconcileObservation)}
    assert names.isdisjoint(EXECUTIVE_OWNED_RECONCILE_FIELDS)
    report = ReconcileObservation(
        process_liveness=ProcessLiveness.PROVEN_DEAD,
        observed_process=ProcessIdentityObservation(),
        provider_session_reachable=None,
        provider_writer_state=ProviderWriterState.UNKNOWN,
    )
    assert not hasattr(report, "resume_safe")
    assert not hasattr(report, "executive_writer_held")


def test_stage_config_side_effect_law():
    with pytest.raises(ValueError):
        StageConfigReceipt(
            attempt_id="a",
            staging_directory="/tmp/stage",
            files_written=("config.toml",),
            wrote_credentials=True,
        )


def test_prepare_rejected_and_required_methods_are_typed():
    assert METHOD_CONTRACTS["prepare"].classification is MethodClass.REJECTED
    assert METHOD_CONTRACTS["complete_job"].classification is MethodClass.REJECTED
    assert METHOD_CONTRACTS["signal_process"].classification is MethodClass.SUPERVISOR_RUNTIME
    required = {
        name
        for name, spec in METHOD_CONTRACTS.items()
        if spec.classification is MethodClass.COMMON_REQUIRED
    }
    assert required == {
        "describe_capabilities",
        "validate_requested_profile",
        "start_session",
        "begin_turn",
        "read_events",
        "interrupt_turn",
        "collect_candidate_result",
        "graceful_stop",
        "cancel",
        "reconcile",
    }
    for spec in METHOD_CONTRACTS.values():
        assert spec.forbidden_side_effects or spec.classification in {
            MethodClass.REJECTED,
            MethodClass.SUPERVISOR_RUNTIME,
        }
        if spec.requires_operation_id:
            assert spec.idempotency is not OperationIdempotencyClass.PURE_IDEMPOTENT
        else:
            assert spec.idempotency is OperationIdempotencyClass.PURE_IDEMPOTENT or spec.classification in {
                MethodClass.REJECTED,
                MethodClass.SUPERVISOR_RUNTIME,
            }


def test_state_changing_methods_require_operation_id():
    for name in (
        "start_session",
        "resume_session",
        "begin_turn",
        "interrupt_turn",
        "cancel",
        "send_input",
        "respond_to_approval",
        "fork_session",
        "stage_operator_config",
        "checkpoint",
        "graceful_stop",
        "probe",
    ):
        spec = METHOD_CONTRACTS[name]
        assert spec.requires_operation_id is True
        assert spec.idempotency is OperationIdempotencyClass.NON_REPLAYABLE_ON_UNKNOWN_EFFECT
    for name in (
        "describe_capabilities",
        "validate_requested_profile",
        "read_events",
        "collect_candidate_result",
        "reconcile",
    ):
        assert METHOD_CONTRACTS[name].requires_operation_id is False
        assert METHOD_CONTRACTS[name].idempotency is OperationIdempotencyClass.PURE_IDEMPOTENT


def test_operation_id_maps_to_existing_command_id_law():
    import control_plane.executive_runtime as runtime

    assert COMMAND_ID_RE.pattern == runtime._COMMAND_ID_RE.pattern
    op = OperationId(command_id="ohf-op:start-1")
    assert COMMAND_ID_RE.fullmatch(op.command_id)
    assert operation_receipt_command_id(op, OperationReceiptKind.INTENT) == op.command_id
    applied = operation_receipt_command_id(op, OperationReceiptKind.APPLIED)
    assert applied == "ohf-op:start-1:applied"
    assert COMMAND_ID_RE.fullmatch(applied)
    with pytest.raises(ValueError):
        OperationId(command_id="not-a-legal-prefix")


def test_intent_without_applied_is_non_replayable_unless_call_never_started():
    assert resolve_operation_after_crash(
        intent_committed=True,
        terminal_receipt=None,
        external_call_proven_not_started=False,
    ) is OperationResolution.EFFECT_UNKNOWN
    assert resolve_operation_after_crash(
        intent_committed=True,
        terminal_receipt=None,
        external_call_proven_not_started=True,
    ) is OperationResolution.MAY_RETRY_SAME_OPERATION_ID
    assert not may_start_successor_rich_writer(
        process_liveness=ProcessLiveness.UNKNOWN,
        process_proven_absent=False,
        external_effect_unknown=True,
    )
    assert may_start_successor_rich_writer(
        process_liveness=ProcessLiveness.PROVEN_DEAD,
        process_proven_absent=True,
        external_effect_unknown=True,
    )


def test_executive_id_ownership_is_on_the_protocol():
    start = inspect.signature(OperatorHarnessAdapter.start_session)
    assert "epoch" in start.parameters
    assert "generation" in start.parameters
    start_hints = get_type_hints(OperatorHarnessAdapter.start_session)
    assert start_hints["epoch"] is SessionEpochRef
    assert start_hints["generation"] is ProcessGenerationRef
    assert start_hints["return"] is SessionStartObservation
    begin = get_type_hints(OperatorHarnessAdapter.begin_turn)
    assert begin["turn"] is TurnRef
    assert begin["return"] is TurnStartObservation
    for method in (
        "start_session",
        "begin_turn",
        "graceful_stop",
        "cancel",
        "reconcile",
        "collect_candidate_result",
    ):
        assert adapter_method_returns_executive_id(method) is False
    assert "session_epoch_id" in EXECUTIVE_ALLOCATED_IDS
    assert "provider_session_id" in ADAPTER_OBSERVED_IDS
    epoch = SessionEpochRef(
        session_epoch_id="e1",
        attempt_id="a1",
        worker_id="w1",
        epoch_number=1,
    )
    assert not hasattr(epoch, "provider_session_id")
    generation = ProcessGenerationRef(
        process_generation_id="g1",
        session_epoch_id="e1",
        generation_number=1,
        worker_id="w1",
    )
    assert not hasattr(generation, "pid")


def test_optional_protocols_require_operation_id():
    assert OPTIONAL_ADAPTER_PROTOCOLS == {
        "probe": SupportsProbe,
        "stage_operator_config": SupportsConfigStaging,
        "resume_session": SupportsSessionResume,
        "send_input": SupportsSteering,
        "respond_to_approval": SupportsApprovalResponse,
        "fork_session": SupportsNativeFork,
        "checkpoint": SupportsCheckpoint,
    }
    for protocol in OPTIONAL_ADAPTER_PROTOCOLS.values():
        methods = [
            name
            for name, value in vars(protocol).items()
            if callable(value) and not name.startswith("_")
        ]
        assert methods
        for name in methods:
            params = inspect.signature(getattr(protocol, name)).parameters
            assert "operation_id" in params or "request" in params
    resume = get_type_hints(SupportsSessionResume.resume_session)
    assert resume["operation_id"] is OperationId
    assert resume["return"] is SessionStartObservation
    describe = get_type_hints(OperatorHarnessAdapter.describe_capabilities)
    assert describe["return"] is HarnessAdapterCapabilities


def test_event_cursor_is_generation_scoped():
    cursor = EventCursor(
        attempt_id="att-1",
        session_epoch_id="e1",
        process_generation_id="g1",
        local_sequence=3,
    )
    assert event_cursor_scoped_to(cursor, "g1")
    assert not event_cursor_scoped_to(cursor, "g2")
    assert "new_process_generation" in REATTEST_TRIGGERS
    assert "harness_config_reload" in REATTEST_TRIGGERS
    assert "authoritative_workspace_identity_change" in REATTEST_TRIGGERS
    assert "every_turn" not in REATTEST_TRIGGERS


def test_transaction_groups_and_crash_windows_are_frozen():
    assert set(TRANSACTION_GROUPS) == set(TransactionGroup)
    required_windows = {
        "after_tx2_before_adapter_call",
        "during_process_launch",
        "provider_created_s1_before_response",
        "after_s1_response_before_tx3",
        "after_tx3_before_attestation",
        "after_attestation_before_turn",
        "provider_accepted_turn_before_applied",
        "graceful_stop_succeeded_before_tx6",
        "sigkill_before_tx7",
        "tx8_committed_e2_not_created",
        "restore_completed_before_tx9",
        "controller_dies_during_tx9",
    }
    assert required_windows <= set(CRASH_WINDOW_MATRIX)
    for row in CRASH_WINDOW_MATRIX.values():
        assert row["safe_automatic_retry"] != "retry"
        assert "writer_held" in row
    assert "prebind_epoch_writer" in PROPOSED_SQL_INVARIANTS
    assert "WHERE executive_writer_held = 1" in PROPOSED_SQL_INVARIANTS["prebind_epoch_writer"]
    assert "provider_session_id IS NOT NULL" in PROPOSED_SQL_INVARIANTS["postbind_realm_writer"]
    assert set(INVARIANT_ENFORCEMENT)


def test_scenario_a_graceful_restart_same_epoch():
    assert ATTEMPT_BOUNDARY_MATRIX["graceful_process_replacement"] is AttemptBoundary.SAME_ATTEMPT
    released = WriterFacts(
        process_liveness=ProcessLiveness.PROVEN_DEAD,
        executive_writer_held=False,
        provider_writer_state=ProviderWriterState.RELEASED,
    )
    assert may_hold_executive_writer(
        worker_id="W1",
        provider_session_id="S1",
        generation_id="gen-2",
        held_by={},
    )
    assert released.provider_writer_state is ProviderWriterState.RELEASED


def test_scenario_c_sigkill_keeps_fence():
    after_kill = process_end_does_not_release_writer(
        99,
        WriterFacts(
            process_liveness=ProcessLiveness.ALIVE,
            executive_writer_held=True,
            provider_writer_state=ProviderWriterState.UNKNOWN,
        ),
    )
    held = {writer_realm_key("W1", "S1"): "gen-1"}
    assert not may_hold_executive_writer(
        worker_id="W1",
        provider_session_id="S1",
        generation_id="gen-2",
        held_by=held,
    )
    assert after_kill.executive_writer_held is True
    assert not may_hold_prebind_epoch_writer(
        session_epoch_id="epoch-1",
        generation_id="gen-2",
        held_by_epoch={"epoch-1": "gen-1"},
    )


def test_scenario_d_fresh_s2_after_abandon_s1():
    held = {writer_realm_key("W1", "S1"): "gen-1"}
    abandoned = abandon_epoch(
        WriterFacts(
            process_liveness=ProcessLiveness.PROVEN_DEAD,
            executive_writer_held=True,
            provider_writer_state=ProviderWriterState.HELD,
        )
    )
    if not abandoned.executive_writer_held:
        held.pop(writer_realm_key("W1", "S1"), None)
    assert may_hold_executive_writer(
        worker_id="W1",
        provider_session_id="S2",
        generation_id="gen-3",
        held_by=held,
    )
    bindings = {writer_realm_key("W1", "S1"): "epoch-1"}
    assert not may_bind_provider_session(
        worker_id="W1",
        provider_session_id="S1",
        existing_bindings=bindings,
        epoch_id="epoch-2",
    )
    assert may_bind_provider_session(
        worker_id="W1",
        provider_session_id="S2",
        existing_bindings=bindings,
        epoch_id="epoch-2",
    )


def test_command_id_regex_is_the_runtime_law():
    assert COMMAND_ID_RE.fullmatch("ohf-op:abc")
    assert COMMAND_ID_RE.fullmatch("ohf-op:abc:effect-unknown")
    assert not COMMAND_ID_RE.fullmatch("")
    assert OPERATION_COMMAND_ID_PREFIX.startswith("ohf-op")
    # Keep the unused import of `re` honest against a local copy of the law.
    assert re.compile(COMMAND_ID_RE.pattern).pattern == COMMAND_ID_RE.pattern
