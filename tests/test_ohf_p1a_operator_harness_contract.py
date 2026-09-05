"""OHF-P1A-R3.3 typed OperatorHarnessAdapter contract freeze."""
from __future__ import annotations

import dataclasses
import inspect
import re
import sqlite3
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
    COMMAND_ID_MAX_LEN,
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
    MAX_OPERATION_ID_LEN,
    METHOD_CONTRACTS,
    MethodClass,
    NativeHelperPolicy,
    OHF_FORBIDDEN_ATTEMPT_COLUMNS,
    OHF_PROPOSED_ATTEMPT_COLUMNS,
    OPERATOR_HARNESS_INTERFACE_VERSION,
    OPERATION_AGGREGATE_TYPE,
    OPERATION_COMMAND_ID_PREFIX,
    OPERATION_INTENT_TARGET_FIELDS,
    OPERATION_RECEIPT_COMMAND_SUFFIXES,
    OPTIONAL_ADAPTER_PROTOCOLS,
    ObservedCapabilityIdentity,
    ObservedHarnessAttestation,
    ObservedTriState,
    OperationId,
    OperationIdempotencyClass,
    OperationIntentReceipt,
    OperationIntentTarget,
    OperationKind,
    OperationReceiptKind,
    OperationResolution,
    OperatorHarnessAdapter,
    POST_RESTORE_ATTEMPT_STATUS,
    PREBIND_WRITER_FENCE_KEY,
    PROPOSED_SQL_INVARIANTS,
    ProcessGenerationRecord,
    ProcessGenerationRef,
    ProcessIdentityObservation,
    ProcessLiveness,
    ProviderSessionHandoff,
    ProviderWriterState,
    REATTEST_TRIGGERS,
    ReconcileObservation,
    RequestedExecutionProfile,
    ResumeBindRefusal,
    ResumeBindSnapshot,
    SameEpochRecoveryRefusal,
    SameEpochRecoveryReplay,
    SameEpochRecoverySnapshot,
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
    apply_resume_bind,
    apply_same_epoch_generation_recovery,
    classify_capability,
    classify_observed_capabilities,
    compare_launch,
    compare_launch_parameter_names,
    diagnose_resume_bind,
    diagnose_resume_intent_target,
    diagnose_same_epoch_generation_recovery,
    derive_resume_safety,
    event_cursor_scoped_to,
    first_work_turn_allowed,
    intent_receipt_for_operation,
    may_allocate_another_generation_after_tx10,
    may_abandon_epoch,
    may_bind_epoch_provider_session,
    may_bind_provider_session,
    may_bind_resume_result,
    may_hold_executive_writer,
    may_hold_prebind_epoch_writer,
    may_hold_postbind_realm_writer,
    may_recover_same_epoch_generation,
    may_start_successor_rich_writer,
    native_helpers_allowed,
    operation_id_permits_all_derived_receipts,
    operation_intent_target_from_event_payload,
    operation_receipt_command_id,
    process_end_does_not_release_writer,
    process_identity_is_complete,
    provider_session_handoff_for_resume,
    restore_invalidation,
    resume_session_handoff_is_lawful,
    rich_ohf_may_rewrite_legacy_attempt_field,
    resolve_operation_after_crash,
    same_epoch_recovery_replay_disposition,
    tx10_resume_intent_target,
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


def _epoch() -> SessionEpochRef:
    return SessionEpochRef(
        session_epoch_id="epoch-1",
        attempt_id="att-1",
        worker_id="W1",
        epoch_number=1,
    )


def _generation(generation_id: str, number: int) -> ProcessGenerationRef:
    return ProcessGenerationRef(
        process_generation_id=generation_id,
        session_epoch_id="epoch-1",
        generation_number=number,
        worker_id="W1",
    )


def _recovery_snapshot(
    *,
    liveness: ProcessLiveness = ProcessLiveness.PROVEN_DEAD,
    provider_writer: ProviderWriterState = ProviderWriterState.RELEASED,
    writer_held: bool = True,
    epoch_state: SessionEpochState = SessionEpochState.CURRENT,
) -> SameEpochRecoverySnapshot:
    return SameEpochRecoverySnapshot(
        epoch=_epoch(),
        epoch_state=epoch_state,
        provider_session_id="S1",
        generations=(
            ProcessGenerationRecord(
                ref=_generation("gen-1", 1),
                executive_writer_held=writer_held,
                process_liveness=liveness,
                provider_writer_state=provider_writer,
                provider_session_id="S1",
            ),
        ),
    )


def _process(
    *,
    pid: int | None = 4242,
    pgid: int | None = 4242,
    start: str | None = "start-g2",
    boot: str | None = "boot-1",
) -> ProcessIdentityObservation:
    return ProcessIdentityObservation(
        pid=pid,
        pgid=pgid,
        process_start_identity=start,
        boot_id=boot,
    )


def _handoff(session: str = "S1", worker: str = "W1") -> ProviderSessionHandoff:
    return ProviderSessionHandoff(provider_session_id=session, worker_id=worker)


def _observation(
    *,
    session: str | None = "S1",
    process: ProcessIdentityObservation | None = None,
) -> SessionStartObservation:
    return SessionStartObservation(
        provider_session_id=session,
        process=process if process is not None else _process(),
    )


def _recovered_tx10(
    command_id: str = "ohf-op:resume-s1-g2",
) -> tuple[SameEpochRecoverySnapshot, OperationId]:
    op = OperationId(command_id=command_id)
    recovered = apply_same_epoch_generation_recovery(
        _recovery_snapshot(),
        old_generation_id="gen-1",
        new_generation=_generation("gen-2", 2),
        operation_id=op,
        resume_safe=True,
    )
    return recovered, op


_UNSET = object()


def _resume_bind_snapshot(
    recovered: SameEpochRecoverySnapshot,
    operation_id: OperationId,
    *,
    applied: bool = False,
    process: ProcessIdentityObservation | None = None,
    intent_receipt: OperationIntentReceipt | None | object = _UNSET,
    bound_provider_session_id: str | None = None,
    writer_held: bool = True,
) -> ResumeBindSnapshot:
    g2 = next(
        row
        for row in recovered.generations
        if row.ref.process_generation_id == "gen-2"
    )
    if not writer_held:
        g2 = ProcessGenerationRecord(
            ref=g2.ref,
            executive_writer_held=False,
            process_liveness=g2.process_liveness,
            provider_writer_state=g2.provider_writer_state,
            provider_session_id=g2.provider_session_id,
        )
    bound = (
        recovered.provider_session_id
        if bound_provider_session_id is None
        else bound_provider_session_id
    )
    if intent_receipt is _UNSET:
        intent_receipt = intent_receipt_for_operation(
            recovered.intent_receipts, operation_id
        )
    return ResumeBindSnapshot(
        epoch=recovered.epoch,
        epoch_state=recovered.epoch_state,
        bound_provider_session_id=bound,
        generation=g2,
        operation_id=operation_id,
        intent_receipt=intent_receipt,
        applied=applied,
        process=process,
    )


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
    assert not native_helpers_allowed(
        write_capable=False,
        native_helper_policy=NativeHelperPolicy.PARENT_READ_ONLY_CEILING,
        supports_subagent_capability_ceiling=ObservedTriState.UNKNOWN,
    )
    assert native_helpers_allowed(
        write_capable=False,
        native_helper_policy=NativeHelperPolicy.PARENT_READ_ONLY_CEILING,
        supports_subagent_capability_ceiling=ObservedTriState.VERIFIED,
    )
    read_only_unknown = compare_launch(
        _requested(
            native_helper_policy=NativeHelperPolicy.PARENT_READ_ONLY_CEILING,
        ),
        _observed(),
    )
    assert (
        read_only_unknown.decision
        is LaunchDecision.REFUSE_HELPER_CEILING_MISSING
    )
    read_only_verified = compare_launch(
        _requested(
            native_helper_policy=NativeHelperPolicy.PARENT_READ_ONLY_CEILING,
        ),
        _observed(
            supports_subagent_capability_ceiling=ObservedTriState.VERIFIED,
        ),
    )
    assert read_only_verified.decision is LaunchDecision.ALLOW
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

    exact_mcp = CapabilityIdentity(
        kind="mcp_server",
        name="openaiDeveloperDocs",
        harness_binary_digest="digest-v1",
        tool_schema_digest="schema-v1",
        mcp_server_identity="openai-docs-mcp",
        mcp_server_version="1.0.0",
        mcp_auth_status="unsupported",
    )
    observed_mcp = ObservedCapabilityIdentity(
        kind="mcp_server",
        name="openaiDeveloperDocs",
        tool_schema_digest="schema-v1",
        mcp_server_identity="openai-docs-mcp",
        mcp_server_version="1.0.0",
        mcp_auth_status="unsupported",
    )
    exact_mcp_launch = compare_launch(
        _requested(
            capabilities=CapabilityManifest(required=(exact_mcp,)),
        ),
        _observed(
            capabilities=(observed_mcp,),
            effective_skills=(),
            effective_mcp=("openaiDeveloperDocs",),
        ),
    )
    assert exact_mcp_launch.decision is LaunchDecision.ALLOW
    wrong_auth = dataclasses.replace(observed_mcp, mcp_auth_status="oAuth")
    wrong_auth_launch = compare_launch(
        _requested(
            capabilities=CapabilityManifest(required=(exact_mcp,)),
        ),
        _observed(
            capabilities=(wrong_auth,),
            effective_skills=(),
            effective_mcp=("openaiDeveloperDocs",),
        ),
    )
    assert wrong_auth_launch.decision is LaunchDecision.REFUSE_MISSING_REQUIRED


def test_resource_capability_exact_digest_allows_and_missing_or_drift_refuses_before_tx5():
    requested_resource = CapabilityIdentity(
        kind="resource",
        name="worker-browser-b1-local",
        harness_binary_digest="digest-v1",
        resource_contract_digest="f" * 64,
    )
    exact = ObservedCapabilityIdentity(
        kind="resource",
        name="worker-browser-b1-local",
        resource_contract_digest="f" * 64,
    )
    requested = _requested(
        capabilities=CapabilityManifest(required=(requested_resource,))
    )

    allowed = compare_launch(
        requested,
        _observed(
            capabilities=(exact,),
            effective_skills=(),
            effective_mcp=(),
        ),
    )
    assert allowed.decision is LaunchDecision.ALLOW

    for observed in (
        (),
        (dataclasses.replace(exact, kind="skill"),),
        (dataclasses.replace(exact, resource_contract_digest="0" * 64),),
        (dataclasses.replace(exact, resource_contract_digest=None),),
    ):
        refused = compare_launch(
            requested,
            _observed(
                capabilities=observed,
                effective_skills=(),
                effective_mcp=(),
            ),
        )
        assert refused.decision is LaunchDecision.REFUSE_MISSING_REQUIRED


def _digest_required_profile(**overrides: object) -> RequestedExecutionProfile:
    """A requested profile whose one required capability carries a
    skill_content_digest, so a "wrong" observed row (same name, different
    digest) can be constructed distinctly from an "exact" one."""

    payload = dict(
        capabilities=CapabilityManifest(
            required=(
                CapabilityIdentity(
                    name="ohf-probe",
                    harness_binary_digest="digest-v1",
                    skill_content_digest="skill-digest-v1",
                ),
            ),
            forbidden=("codex_apps",),
        ),
    )
    payload.update(overrides)
    return _requested(**payload)


def test_exactly_one_comparator_exact_and_wrong_duplicate_is_not_satisfied():
    """RED (CAP-S1 P6-7): classify_observed_capabilities() must require
    EXACTLY ONE observed row for a required name.  Pre-fix,
    `any(_identity_proven(...) for item in observed_caps)` lets the correct
    row satisfy the rule even though a second, wrong-identity row sharing the
    same name is also present -- the exact defect Sol's seam map names."""
    requested = _digest_required_profile(write_capable=True)
    exact_row = ObservedCapabilityIdentity(
        kind="skill", name="ohf-probe", skill_content_digest="skill-digest-v1"
    )
    wrong_row = ObservedCapabilityIdentity(
        kind="skill", name="ohf-probe", skill_content_digest="wrong-digest"
    )
    observed = _observed(
        capabilities=(exact_row, wrong_row),
        effective_skills=("ohf-probe",),
        effective_mcp=(),
    )
    missing, forbidden_present, unclassified, unknown_precision = classify_observed_capabilities(
        requested, observed
    )
    assert missing == ("ohf-probe",)
    assert "ohf-probe" in unknown_precision
    comparison = compare_launch(requested, observed)
    assert comparison.decision is LaunchDecision.REFUSE_MISSING_REQUIRED
    assert "missing_required" in comparison.mismatch_reasons


def test_exactly_one_comparator_two_identical_proven_rows_is_not_satisfied():
    """RED (CAP-S1 P6-7): two IDENTICAL proven rows for the same required
    name are still not "exactly one" -- duplication itself is the defect,
    independent of whether the duplicate content agrees."""
    requested = _digest_required_profile(write_capable=True)
    exact_row = ObservedCapabilityIdentity(
        kind="skill", name="ohf-probe", skill_content_digest="skill-digest-v1"
    )
    observed = _observed(
        capabilities=(exact_row, dataclasses.replace(exact_row)),
        effective_skills=("ohf-probe",),
        effective_mcp=(),
    )
    missing, _forbidden, _unclassified, unknown_precision = classify_observed_capabilities(
        requested, observed
    )
    assert missing == ("ohf-probe",)
    assert "ohf-probe" in unknown_precision
    comparison = compare_launch(requested, observed)
    assert comparison.decision is LaunchDecision.REFUSE_MISSING_REQUIRED
    assert "missing_required" in comparison.mismatch_reasons


def test_exactly_one_comparator_two_wrong_duplicates_stays_missing():
    """Regression: two duplicate rows that are BOTH wrong were already
    refused pre-fix; assert the refusal is unchanged and now also carries
    unknown_precision."""
    requested = _digest_required_profile(write_capable=True)
    wrong_a = ObservedCapabilityIdentity(
        kind="skill", name="ohf-probe", skill_content_digest="wrong-a"
    )
    wrong_b = ObservedCapabilityIdentity(
        kind="skill", name="ohf-probe", skill_content_digest="wrong-b"
    )
    observed = _observed(
        capabilities=(wrong_a, wrong_b),
        effective_skills=("ohf-probe",),
        effective_mcp=(),
    )
    missing, _forbidden, _unclassified, unknown_precision = classify_observed_capabilities(
        requested, observed
    )
    assert missing == ("ohf-probe",)
    assert "ohf-probe" in unknown_precision
    comparison = compare_launch(requested, observed)
    assert comparison.decision is LaunchDecision.REFUSE_MISSING_REQUIRED
    assert "missing_required" in comparison.mismatch_reasons


def test_exactly_one_comparator_lone_exact_row_is_satisfied():
    """Regression: the ordinary lone-exact-row case must stay ALLOW."""
    requested = _digest_required_profile(write_capable=True)
    exact_row = ObservedCapabilityIdentity(
        kind="skill", name="ohf-probe", skill_content_digest="skill-digest-v1"
    )
    observed = _observed(
        capabilities=(exact_row,),
        effective_skills=("ohf-probe",),
        effective_mcp=(),
    )
    missing, _forbidden, _unclassified, unknown_precision = classify_observed_capabilities(
        requested, observed
    )
    assert missing == ()
    assert "ohf-probe" not in unknown_precision
    comparison = compare_launch(requested, observed)
    assert comparison.decision is LaunchDecision.ALLOW


def test_exactly_one_comparator_lone_wrong_row_stays_missing():
    """Regression: a lone but wrong-identity row was already refused
    pre-fix; assert it is unchanged."""
    requested = _digest_required_profile(write_capable=True)
    wrong_row = ObservedCapabilityIdentity(
        kind="skill", name="ohf-probe", skill_content_digest="wrong-digest"
    )
    observed = _observed(
        capabilities=(wrong_row,),
        effective_skills=("ohf-probe",),
        effective_mcp=(),
    )
    missing, _forbidden, _unclassified, unknown_precision = classify_observed_capabilities(
        requested, observed
    )
    assert missing == ("ohf-probe",)
    assert "ohf-probe" in unknown_precision
    comparison = compare_launch(requested, observed)
    assert comparison.decision is LaunchDecision.REFUSE_MISSING_REQUIRED


def test_required_capability_present_only_in_a_summary_set_never_satisfies():
    """A required name observed ONLY via a `named` summary set
    (effective_skills/effective_mcp/effective_plugins_or_apps), with zero
    typed observation rows, must never satisfy a digest-bearing requirement
    -- len(same_name_rows) == 0 is "missing", never "proven by summary"."""
    requested = _digest_required_profile(write_capable=True)
    observed = _observed(
        capabilities=(),
        effective_skills=("ohf-probe",),
        effective_mcp=(),
    )
    missing, _forbidden, _unclassified, unknown_precision = classify_observed_capabilities(
        requested, observed
    )
    assert missing == ("ohf-probe",)
    assert "ohf-probe" in unknown_precision
    comparison = compare_launch(requested, observed)
    assert comparison.decision is LaunchDecision.REFUSE_MISSING_REQUIRED


def test_kind_mismatch_on_the_lone_observed_row_is_not_proven():
    """Regression via _identity_proven's own kind check: a lone row sharing
    the required name but a different `kind` is not proven, so it must stay
    missing (exactly-one-row is necessary but not sufficient)."""
    requested = _requested(write_capable=True)  # default required rule kind="skill"
    wrong_kind_row = ObservedCapabilityIdentity(kind="mcp_server", name="ohf-probe")
    observed = _observed(
        capabilities=(wrong_kind_row,),
        effective_skills=("ohf-probe",),
        effective_mcp=(),
    )
    missing, _forbidden, _unclassified, unknown_precision = classify_observed_capabilities(
        requested, observed
    )
    assert missing == ("ohf-probe",)
    assert "ohf-probe" in unknown_precision
    comparison = compare_launch(requested, observed)
    assert comparison.decision is LaunchDecision.REFUSE_MISSING_REQUIRED


def test_exactly_one_comparator_is_order_invariant():
    """Shuffling observed row order must never change any of the four
    returned tuples -- the comparator counts rows by name, not position."""
    requested = _digest_required_profile(write_capable=True)
    exact_row = ObservedCapabilityIdentity(
        kind="skill", name="ohf-probe", skill_content_digest="skill-digest-v1"
    )
    wrong_row = ObservedCapabilityIdentity(
        kind="skill", name="ohf-probe", skill_content_digest="wrong-digest"
    )
    forward = _observed(
        capabilities=(exact_row, wrong_row),
        effective_skills=("ohf-probe",),
        effective_mcp=(),
    )
    backward = _observed(
        capabilities=(wrong_row, exact_row),
        effective_skills=("ohf-probe",),
        effective_mcp=(),
    )
    forward_result = classify_observed_capabilities(requested, forward)
    backward_result = classify_observed_capabilities(requested, backward)
    assert forward_result == backward_result
    assert forward_result[0] == ("ohf-probe",)


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
    assert resume["provider_session"] is ProviderSessionHandoff
    assert resume["epoch"] is SessionEpochRef
    assert resume["generation"] is ProcessGenerationRef
    assert resume["return"] is SessionStartObservation
    start_params = inspect.signature(OperatorHarnessAdapter.start_session).parameters
    assert "provider_session" not in start_params
    assert "provider_session_id" not in start_params
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
        "after_tx10_before_resume_call",
        "during_resume_session",
        "resume_returned_before_applied",
        "after_tx11_applied",
        "observed_session_mismatch_refuses_tx11",
        "incomplete_process_identity_refuses_tx11",
        "intent_target_mismatch_refuses_tx11",
        "duplicate_tx11_matching_observation",
        "duplicate_tx10_while_successor_holds",
        "hard_dead_g1_provider_held_or_unknown",
        "unknown_process_blocks_tx10",
    }
    assert required_windows <= set(CRASH_WINDOW_MATRIX)
    for row in CRASH_WINDOW_MATRIX.values():
        assert row["safe_automatic_retry"] != "retry"
        assert "writer_held" in row
    assert "prebind_epoch_writer" in PROPOSED_SQL_INVARIANTS
    assert "WHERE executive_writer_held = 1" in PROPOSED_SQL_INVARIANTS["prebind_epoch_writer"]
    assert "provider_session_id IS NOT NULL" in PROPOSED_SQL_INVARIANTS["postbind_realm_writer"]
    assert set(INVARIANT_ENFORCEMENT)
    assert TransactionGroup.TX10_SAME_EPOCH_GENERATION_RECOVERY in TRANSACTION_GROUPS
    tx10 = TRANSACTION_GROUPS[TransactionGroup.TX10_SAME_EPOCH_GENERATION_RECOVERY]
    assert "No new SessionEpoch" in tx10
    assert "No new Attempt" in tx10
    assert "resume_session" in tx10
    assert "ProviderSessionHandoff" in tx10
    assert "TX-11" in tx10
    assert TransactionGroup.TX11_BIND_RESUME_RESULT in TRANSACTION_GROUPS
    tx11 = TRANSACTION_GROUPS[TransactionGroup.TX11_BIND_RESUME_RESULT]
    assert "already-bound S1" in tx11
    assert "Must not mutate" in tx11
    assert "TX-3 only" in tx11
    assert "OperationIntentTarget" in tx10
    assert "INTENT_TARGET_MISMATCH" in tx11
    assert INVARIANT_ENFORCEMENT["same_epoch_generation_recovery"].value == "BEGIN_IMMEDIATE"
    assert INVARIANT_ENFORCEMENT["resume_provider_session_handoff"].value == "PURE_COMPARATOR"
    assert INVARIANT_ENFORCEMENT["resume_bind_process_identity"].value == "BEGIN_IMMEDIATE"
    assert INVARIANT_ENFORCEMENT["operation_intent_target"].value == "BEGIN_IMMEDIATE"
    assert INVARIANT_ENFORCEMENT["process_identity_positive_nonblank"].value == "SQL_TRIGGER"
    assert "pid > 0" in PROPOSED_SQL_INVARIANTS["process_identity_pid_positive"]
    assert "pgid > 0" in PROPOSED_SQL_INVARIANTS["process_identity_pgid_positive"]
    assert "length(trim(process_start_identity))" in PROPOSED_SQL_INVARIANTS[
        "process_identity_recorded_together"
    ]


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
    assert COMMAND_ID_MAX_LEN == 128
    assert MAX_OPERATION_ID_LEN == COMMAND_ID_MAX_LEN - len(":effect-unknown")
    assert "effect-unknown" in OPERATION_RECEIPT_COMMAND_SUFFIXES


def test_operation_id_receipt_closure_at_max_and_one_beyond():
    prefix = OPERATION_COMMAND_ID_PREFIX
    max_id = prefix + "a" * (MAX_OPERATION_ID_LEN - len(prefix))
    assert len(max_id) == MAX_OPERATION_ID_LEN
    assert operation_id_permits_all_derived_receipts(max_id)
    op = OperationId(command_id=max_id)
    for kind in (
        OperationReceiptKind.INTENT,
        OperationReceiptKind.APPLIED,
        OperationReceiptKind.REFUSED,
        OperationReceiptKind.EFFECT_UNKNOWN,
        OperationReceiptKind.RECONCILED,
    ):
        derived = operation_receipt_command_id(op, kind)
        assert COMMAND_ID_RE.fullmatch(derived)
        assert len(derived) <= COMMAND_ID_MAX_LEN
    beyond = max_id + "a"
    assert len(beyond) == MAX_OPERATION_ID_LEN + 1
    assert COMMAND_ID_RE.fullmatch(beyond)
    assert not operation_id_permits_all_derived_receipts(beyond)
    with pytest.raises(ValueError, match="derived receipt"):
        OperationId(command_id=beyond)
    too_long_for_regex = "o" + "a" * COMMAND_ID_MAX_LEN
    assert len(too_long_for_regex) == COMMAND_ID_MAX_LEN + 1
    assert COMMAND_ID_RE.fullmatch(too_long_for_regex) is None


def test_hard_dead_released_same_epoch_g2_is_lawful():
    snapshot = _recovery_snapshot()
    g2 = _generation("gen-2", 2)
    op = OperationId(command_id="ohf-op:resume-s1-g2")
    assert may_recover_same_epoch_generation(
        snapshot,
        old_generation_id="gen-1",
        new_generation=g2,
        operation_id=op,
        resume_safe=True,
    )
    recovered = apply_same_epoch_generation_recovery(
        snapshot,
        old_generation_id="gen-1",
        new_generation=g2,
        operation_id=op,
        resume_safe=True,
    )
    assert recovered.epoch.session_epoch_id == snapshot.epoch.session_epoch_id
    assert recovered.epoch.attempt_id == snapshot.epoch.attempt_id
    assert recovered.epoch.epoch_number == snapshot.epoch.epoch_number
    assert recovered.creates_new_epoch is False
    assert recovered.consumes_attempt is False
    assert recovered.provider_session_id == "S1"
    by_id = {row.ref.process_generation_id: row for row in recovered.generations}
    assert by_id["gen-1"].executive_writer_held is False
    assert by_id["gen-1"].provider_writer_state is ProviderWriterState.RELEASED
    assert by_id["gen-2"].executive_writer_held is True
    assert by_id["gen-2"].ref.generation_number == 2
    assert by_id["gen-2"].provider_session_id == "S1"
    assert op.command_id in recovered.reserved_operation_ids
    receipt = intent_receipt_for_operation(recovered.intent_receipts, op)
    assert receipt is not None
    assert receipt.event_type == OperationReceiptKind.INTENT.value
    assert receipt.command_id == op.command_id
    assert receipt.aggregate_id == op.command_id
    assert receipt.target == tx10_resume_intent_target(
        epoch=recovered.epoch,
        generation=g2,
        provider_session_id="S1",
    )
    assert operation_intent_target_from_event_payload(
        receipt.target.to_event_payload()
    ) == receipt.target
    assert ATTEMPT_BOUNDARY_MATRIX["safe_crash_recovery"] is AttemptBoundary.SAME_ATTEMPT


def test_hard_dead_held_or_unknown_provider_writer_refuses_g2():
    g2 = _generation("gen-2", 2)
    op = OperationId(command_id="ohf-op:resume-blocked")
    for writer in (ProviderWriterState.HELD, ProviderWriterState.UNKNOWN):
        snapshot = _recovery_snapshot(provider_writer=writer)
        assert (
            diagnose_same_epoch_generation_recovery(
                snapshot,
                old_generation_id="gen-1",
                new_generation=g2,
                operation_id=op,
                resume_safe=True,
            )
            is SameEpochRecoveryRefusal.PROVIDER_WRITER_NOT_RELEASED
        )
        with pytest.raises(ValueError, match="PROVIDER_WRITER_NOT_RELEASED"):
            apply_same_epoch_generation_recovery(
                snapshot,
                old_generation_id="gen-1",
                new_generation=g2,
                operation_id=op,
                resume_safe=True,
            )


def test_unknown_process_refuses_same_epoch_g2():
    snapshot = _recovery_snapshot(liveness=ProcessLiveness.UNKNOWN)
    g2 = _generation("gen-2", 2)
    op = OperationId(command_id="ohf-op:resume-unknown-process")
    assert (
        diagnose_same_epoch_generation_recovery(
            snapshot,
            old_generation_id="gen-1",
            new_generation=g2,
            operation_id=op,
            resume_safe=True,
        )
        is SameEpochRecoveryRefusal.PROCESS_LIVENESS_UNKNOWN
    )


def test_duplicate_same_epoch_recovery_hits_writer_and_operation_id():
    snapshot = _recovery_snapshot()
    g2 = _generation("gen-2", 2)
    op = OperationId(command_id="ohf-op:resume-once")
    recovered = apply_same_epoch_generation_recovery(
        snapshot,
        old_generation_id="gen-1",
        new_generation=g2,
        operation_id=op,
        resume_safe=True,
    )
    held_epoch = {
        row.ref.session_epoch_id: row.ref.process_generation_id
        for row in recovered.generations
        if row.executive_writer_held
    }
    assert not may_hold_prebind_epoch_writer(
        session_epoch_id="epoch-1",
        generation_id="gen-3",
        held_by_epoch=held_epoch,
    )
    held_realm = {
        writer_realm_key("W1", "S1"): row.ref.process_generation_id
        for row in recovered.generations
        if row.executive_writer_held
    }
    assert not may_hold_postbind_realm_writer(
        worker_id="W1",
        provider_session_id="S1",
        generation_id="gen-3",
        held_by=held_realm,
    )
    assert (
        diagnose_same_epoch_generation_recovery(
            recovered,
            old_generation_id="gen-1",
            new_generation=_generation("gen-3", 3),
            operation_id=op,
            resume_safe=True,
        )
        is SameEpochRecoveryRefusal.OLD_WRITER_NOT_HELD
    )
    assert (
        diagnose_same_epoch_generation_recovery(
            recovered,
            old_generation_id="gen-1",
            new_generation=_generation("gen-3", 3),
            operation_id=OperationId(command_id="ohf-op:resume-twice"),
            resume_safe=True,
        )
        is SameEpochRecoveryRefusal.OLD_WRITER_NOT_HELD
    )
    # Same OperationId is reserved even if a caller names a different old generation.
    g2_as_old = SameEpochRecoverySnapshot(
        epoch=recovered.epoch,
        epoch_state=recovered.epoch_state,
        provider_session_id=recovered.provider_session_id,
        generations=tuple(
            ProcessGenerationRecord(
                ref=row.ref,
                executive_writer_held=row.executive_writer_held,
                process_liveness=(
                    ProcessLiveness.PROVEN_DEAD
                    if row.ref.process_generation_id == "gen-2"
                    else row.process_liveness
                ),
                provider_writer_state=(
                    ProviderWriterState.RELEASED
                    if row.ref.process_generation_id == "gen-2"
                    else row.provider_writer_state
                ),
                provider_session_id=row.provider_session_id,
            )
            for row in recovered.generations
        ),
        reserved_operation_ids=recovered.reserved_operation_ids,
    )
    assert (
        diagnose_same_epoch_generation_recovery(
            g2_as_old,
            old_generation_id="gen-2",
            new_generation=_generation("gen-3", 3),
            operation_id=op,
            resume_safe=True,
        )
        is SameEpochRecoveryRefusal.OPERATION_ID_DUPLICATE
    )


def test_tx10_intent_crash_has_deterministic_replay_disposition():
    safe = same_epoch_recovery_replay_disposition(
        intent_committed=True,
        terminal_receipt=None,
        external_call_proven_not_started=True,
    )
    unknown = same_epoch_recovery_replay_disposition(
        intent_committed=True,
        terminal_receipt=None,
        external_call_proven_not_started=False,
    )
    assert safe is SameEpochRecoveryReplay.RETRY_SAME_OPERATION_ON_ALLOCATED_GENERATION
    assert unknown is SameEpochRecoveryReplay.EFFECT_UNKNOWN_HOLD_GENERATION
    assert may_allocate_another_generation_after_tx10(intent_committed=True) is False
    assert may_allocate_another_generation_after_tx10(intent_committed=False) is False
    recovered = apply_same_epoch_generation_recovery(
        _recovery_snapshot(),
        old_generation_id="gen-1",
        new_generation=_generation("gen-2", 2),
        operation_id=OperationId(command_id="ohf-op:resume-crash"),
        resume_safe=True,
    )
    g2 = next(row for row in recovered.generations if row.ref.process_generation_id == "gen-2")
    assert g2.executive_writer_held is True
    assert g2.process_liveness is ProcessLiveness.UNKNOWN
    assert not may_start_successor_rich_writer(
        process_liveness=g2.process_liveness,
        process_proven_absent=False,
        external_effect_unknown=True,
    )


def test_resume_session_requires_bound_provider_session_handoff():
    recovered, _op = _recovered_tx10()
    handoff = provider_session_handoff_for_resume(
        epoch=recovered.epoch,
        bound_provider_session_id=recovered.provider_session_id,
    )
    assert handoff.provider_session_id == "S1"
    assert handoff.worker_id == "W1"
    assert resume_session_handoff_is_lawful(
        handoff,
        epoch=recovered.epoch,
        bound_provider_session_id="S1",
    )
    assert not resume_session_handoff_is_lawful(
        _handoff("S2"),
        epoch=recovered.epoch,
        bound_provider_session_id="S1",
    )
    assert not resume_session_handoff_is_lawful(
        _handoff("S1", worker="W2"),
        epoch=recovered.epoch,
        bound_provider_session_id="S1",
    )
    with pytest.raises(ValueError, match="already-bound"):
        provider_session_handoff_for_resume(
            epoch=recovered.epoch,
            bound_provider_session_id="",
        )
    with pytest.raises(ValueError, match="provider_session_id is required"):
        ProviderSessionHandoff(provider_session_id="", worker_id="W1")
    resume_contract = METHOD_CONTRACTS["resume_session"]
    assert "allocate provider_session_id" in resume_contract.forbidden_side_effects
    assert "create a new provider session" in resume_contract.forbidden_side_effects
    assert "rebind epoch.provider_session_id" in resume_contract.forbidden_side_effects
    assert "ProviderSessionHandoff" in resume_contract.notes
    assert "TX-11" in resume_contract.notes


def test_tx11_records_process_identity_and_applied_without_rebinding_s1():
    recovered, op = _recovered_tx10()
    snapshot = _resume_bind_snapshot(recovered, op)
    observation = _observation()
    handoff = _handoff()
    assert may_bind_resume_result(
        snapshot, observation=observation, handoff=handoff
    )
    bound = apply_resume_bind(
        snapshot, observation=observation, handoff=handoff
    )
    assert bound.applied is True
    receipt = bound.intent_receipt
    assert receipt is not None
    assert receipt.operation_id.command_id == op.command_id
    assert receipt.target.operation_kind is OperationKind.RESUME_SESSION
    assert receipt.target.attempt_id == recovered.epoch.attempt_id
    assert receipt.target.session_epoch_id == recovered.epoch.session_epoch_id
    assert receipt.target.process_generation_id == "gen-2"
    assert receipt.target.worker_id == "W1"
    assert receipt.target.provider_session_id == "S1"
    assert receipt.aggregate_type == OPERATION_AGGREGATE_TYPE
    assert tuple(receipt.target.to_event_payload()) == OPERATION_INTENT_TARGET_FIELDS
    assert bound.bound_provider_session_id == "S1"
    assert bound.epoch.session_epoch_id == recovered.epoch.session_epoch_id
    assert bound.epoch.attempt_id == recovered.epoch.attempt_id
    assert bound.creates_new_epoch is False
    assert bound.consumes_attempt is False
    assert bound.epoch_provider_session_mutated is False
    assert bound.generation.provider_session_id == "S1"
    assert bound.generation.executive_writer_held is True
    assert bound.generation.process_liveness is ProcessLiveness.ALIVE
    assert bound.generation.provider_writer_state is ProviderWriterState.HELD
    assert bound.process == _process()
    assert process_identity_is_complete(bound.process)
    applied = operation_receipt_command_id(op, OperationReceiptKind.APPLIED)
    assert applied == "ohf-op:resume-s1-g2:applied"
    assert same_epoch_recovery_replay_disposition(
        intent_committed=True,
        terminal_receipt=OperationReceiptKind.APPLIED,
        external_call_proven_not_started=False,
    ) is SameEpochRecoveryReplay.APPLIED
    assert "new_process_generation" in REATTEST_TRIGGERS


def test_tx11_refuses_observed_session_mismatch_and_does_not_rebind():
    recovered, op = _recovered_tx10("ohf-op:resume-mismatch")
    snapshot = _resume_bind_snapshot(recovered, op)
    handoff = _handoff()
    for observed in ("S2", None, ""):
        observation = _observation(session=observed)
        assert (
            diagnose_resume_bind(
                snapshot, observation=observation, handoff=handoff
            )
            is ResumeBindRefusal.PROVIDER_SESSION_MISMATCH
        )
        with pytest.raises(ValueError, match="PROVIDER_SESSION_MISMATCH"):
            apply_resume_bind(snapshot, observation=observation, handoff=handoff)
    assert snapshot.bound_provider_session_id == "S1"
    assert snapshot.applied is False
    assert snapshot.epoch_provider_session_mutated is False
    assert not may_bind_epoch_provider_session(
        epoch_provider_session_id="S1",
        observed_provider_session_id="S2",
    )


def test_tx11_refuses_unbound_epoch_that_belongs_to_tx3():
    recovered, op = _recovered_tx10("ohf-op:resume-unbound")
    snapshot = _resume_bind_snapshot(
        recovered, op, bound_provider_session_id=""
    )
    assert (
        diagnose_resume_bind(
            snapshot, observation=_observation(), handoff=_handoff()
        )
        is ResumeBindRefusal.EPOCH_SESSION_UNBOUND
    )
    assert may_bind_epoch_provider_session(
        epoch_provider_session_id=None,
        observed_provider_session_id="S1",
    )


def test_tx11_refuses_incomplete_process_identity():
    recovered, op = _recovered_tx10("ohf-op:resume-incomplete")
    snapshot = _resume_bind_snapshot(recovered, op)
    incomplete_cases = (
        _process(pid=None),
        _process(pgid=None),
        _process(pid=0),
        _process(pgid=0),
        _process(pid=-1),
        _process(pgid=-8),
        _process(start=""),
        _process(boot=""),
        _process(start="   "),
        _process(boot="\t"),
        _process(start=None),
        _process(boot=None),
    )
    for process in incomplete_cases:
        observation = _observation(process=process)
        assert not process_identity_is_complete(observation.process)
        assert (
            diagnose_resume_bind(
                snapshot, observation=observation, handoff=_handoff()
            )
            is ResumeBindRefusal.PROCESS_IDENTITY_INCOMPLETE
        )
    assert process_identity_is_complete(_process(pid=1, pgid=1))


def test_tx11_refuses_wrong_handoff_and_missing_intent():
    recovered, op = _recovered_tx10("ohf-op:resume-handoff")
    snapshot = _resume_bind_snapshot(recovered, op)
    assert (
        diagnose_resume_bind(
            snapshot, observation=_observation(), handoff=_handoff("S2")
        )
        is ResumeBindRefusal.HANDOFF_MISMATCH
    )
    no_intent = _resume_bind_snapshot(recovered, op, intent_receipt=None)
    assert (
        diagnose_resume_bind(
            no_intent, observation=_observation(), handoff=_handoff()
        )
        is ResumeBindRefusal.INTENT_MISSING
    )
    no_writer = _resume_bind_snapshot(recovered, op, writer_held=False)
    assert (
        diagnose_resume_bind(
            no_writer, observation=_observation(), handoff=_handoff()
        )
        is ResumeBindRefusal.GENERATION_NOT_WRITER
    )


def test_resume_returned_before_tx11_is_effect_unknown_and_holds_g2():
    recovered, op = _recovered_tx10("ohf-op:resume-before-tx11")
    snapshot = _resume_bind_snapshot(recovered, op)
    assert snapshot.applied is False
    assert snapshot.generation.process_liveness is ProcessLiveness.UNKNOWN
    unknown = same_epoch_recovery_replay_disposition(
        intent_committed=True,
        terminal_receipt=None,
        external_call_proven_not_started=False,
    )
    assert unknown is SameEpochRecoveryReplay.EFFECT_UNKNOWN_HOLD_GENERATION
    assert may_allocate_another_generation_after_tx10(intent_committed=True) is False
    window = CRASH_WINDOW_MATRIX["resume_returned_before_applied"]
    assert "TX-11" in window["required_reconciliation"]
    assert window["safe_automatic_retry"] == "no"
    assert not may_start_successor_rich_writer(
        process_liveness=snapshot.generation.process_liveness,
        process_proven_absent=False,
        external_effect_unknown=True,
    )
    assert op.command_id in recovered.reserved_operation_ids


def test_duplicate_tx11_matching_observation_is_noop():
    recovered, op = _recovered_tx10("ohf-op:resume-applied-once")
    first = apply_resume_bind(
        _resume_bind_snapshot(recovered, op),
        observation=_observation(),
        handoff=_handoff(),
    )
    replay = apply_resume_bind(
        first, observation=_observation(), handoff=_handoff()
    )
    assert replay is first or (
        replay.applied is True
        and replay.process == first.process
        and replay.bound_provider_session_id == "S1"
        and replay.epoch_provider_session_mutated is False
    )
    conflict = _observation(process=_process(pid=9999))
    assert (
        diagnose_resume_bind(first, observation=conflict, handoff=_handoff())
        is ResumeBindRefusal.ALREADY_APPLIED_CONFLICT
    )
    with pytest.raises(ValueError, match="ALREADY_APPLIED_CONFLICT"):
        apply_resume_bind(first, observation=conflict, handoff=_handoff())


def _wrong_intent_receipt(
    recovered: SameEpochRecoverySnapshot,
    operation_id: OperationId,
    **overrides: object,
) -> OperationIntentReceipt:
    lawful = intent_receipt_for_operation(recovered.intent_receipts, operation_id)
    assert lawful is not None
    payload = dict(lawful.target.to_event_payload())
    payload.update({key: value for key, value in overrides.items()})
    if "operation_kind" in overrides and isinstance(overrides["operation_kind"], OperationKind):
        payload["operation_kind"] = overrides["operation_kind"].value
    target = operation_intent_target_from_event_payload(payload)
    return OperationIntentReceipt(operation_id=operation_id, target=target)


def test_tx11_refuses_intent_target_mismatch_before_applied():
    recovered, op_a = _recovered_tx10("ohf-op:resume-target-a")
    lawful = _resume_bind_snapshot(recovered, op_a)
    observation = _observation()
    handoff = _handoff()
    assert diagnose_resume_bind(
        lawful, observation=observation, handoff=handoff
    ) is None

    g3_receipt = _wrong_intent_receipt(
        recovered, op_a, process_generation_id="gen-3"
    )
    g2 = next(
        row
        for row in recovered.generations
        if row.ref.process_generation_id == "gen-2"
    )
    assert (
        diagnose_resume_intent_target(
            g3_receipt,
            operation_id=op_a,
            epoch=recovered.epoch,
            generation=g2,
            bound_provider_session_id="S1",
        )
        is ResumeBindRefusal.INTENT_TARGET_MISMATCH
    )
    assert (
        diagnose_resume_bind(
            _resume_bind_snapshot(recovered, op_a, intent_receipt=g3_receipt),
            observation=observation,
            handoff=handoff,
        )
        is ResumeBindRefusal.INTENT_TARGET_MISMATCH
    )

    other_epoch = _wrong_intent_receipt(
        recovered, op_a, session_epoch_id="epoch-other"
    )
    assert (
        diagnose_resume_bind(
            _resume_bind_snapshot(recovered, op_a, intent_receipt=other_epoch),
            observation=observation,
            handoff=handoff,
        )
        is ResumeBindRefusal.INTENT_TARGET_MISMATCH
    )

    other_session = _wrong_intent_receipt(
        recovered, op_a, provider_session_id="S2"
    )
    assert (
        diagnose_resume_bind(
            _resume_bind_snapshot(recovered, op_a, intent_receipt=other_session),
            observation=observation,
            handoff=handoff,
        )
        is ResumeBindRefusal.INTENT_TARGET_MISMATCH
    )

    start_kind = _wrong_intent_receipt(
        recovered, op_a, operation_kind=OperationKind.START_SESSION
    )
    assert (
        diagnose_resume_bind(
            _resume_bind_snapshot(recovered, op_a, intent_receipt=start_kind),
            observation=observation,
            handoff=handoff,
        )
        is ResumeBindRefusal.INTENT_TARGET_MISMATCH
    )

    other_attempt = _wrong_intent_receipt(
        recovered, op_a, attempt_id="att-other"
    )
    assert (
        diagnose_resume_bind(
            _resume_bind_snapshot(recovered, op_a, intent_receipt=other_attempt),
            observation=observation,
            handoff=handoff,
        )
        is ResumeBindRefusal.INTENT_TARGET_MISMATCH
    )

    op_b = OperationId(command_id="ohf-op:resume-target-b")
    borrowed_a = intent_receipt_for_operation(recovered.intent_receipts, op_a)
    assert (
        diagnose_resume_bind(
            _resume_bind_snapshot(recovered, op_b, intent_receipt=borrowed_a),
            observation=observation,
            handoff=handoff,
        )
        is ResumeBindRefusal.INTENT_TARGET_MISMATCH
    )
    with pytest.raises(ValueError, match="INTENT_TARGET_MISMATCH"):
        apply_resume_bind(
            _resume_bind_snapshot(recovered, op_a, intent_receipt=g3_receipt),
            observation=observation,
            handoff=handoff,
        )
    window = CRASH_WINDOW_MATRIX["intent_target_mismatch_refuses_tx11"]
    assert "INTENT_TARGET_MISMATCH" in window["required_reconciliation"]


def test_process_generations_identity_checks_match_executive_law():
    schema_doc = Path(
        "research/EXECUTIVE_OS_OHF_P1A_DURABLE_IDENTITY_AND_SCHEMA_2026-08-16.md"
    ).read_text(encoding="utf-8")
    for fragment in (
        PROPOSED_SQL_INVARIANTS["process_identity_pid_positive"],
        PROPOSED_SQL_INVARIANTS["process_identity_pgid_positive"],
        "length(trim(process_start_identity)) > 0",
        "length(trim(boot_id)) > 0",
    ):
        assert fragment in schema_doc
    connection = sqlite3.connect(":memory:")
    connection.execute(
        """
        CREATE TABLE process_generations (
          process_generation_id TEXT PRIMARY KEY,
          pid INTEGER,
          pgid INTEGER,
          process_start_identity TEXT,
          boot_id TEXT,
          CHECK (pid IS NULL OR pid > 0),
          CHECK (pgid IS NULL OR pgid > 0),
          CHECK (
            (pid IS NULL AND pgid IS NULL AND process_start_identity IS NULL
             AND boot_id IS NULL)
            OR
            (pid IS NOT NULL AND pgid IS NOT NULL
             AND length(trim(process_start_identity)) > 0
             AND length(trim(boot_id)) > 0)
          )
        )
        """
    )
    connection.execute(
        "INSERT INTO process_generations VALUES ('g-null', NULL, NULL, NULL, NULL)"
    )
    connection.execute(
        "INSERT INTO process_generations VALUES ('g-ok', 1, 1, 'start', 'boot')"
    )
    bad_rows = (
        ("g-pid0", 0, 1, "start", "boot"),
        ("g-pid-neg", -1, 1, "start", "boot"),
        ("g-pgid0", 1, 0, "start", "boot"),
        ("g-pgid-neg", 1, -2, "start", "boot"),
        ("g-empty-start", 1, 1, "", "boot"),
        ("g-empty-boot", 1, 1, "start", ""),
        ("g-ws-start", 1, 1, "   ", "boot"),
        ("g-ws-boot", 1, 1, "start", "   "),
    )
    for row in bad_rows:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO process_generations VALUES (?, ?, ?, ?, ?)",
                row,
            )
    connection.close()
