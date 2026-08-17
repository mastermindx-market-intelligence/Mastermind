"""OHF-P1A-R2 typed OperatorHarnessAdapter contract freeze."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from control_plane.operator_harness_contract import (
    ACCOUNT_REALM_STATUS,
    ATTEMPT_BOUNDARY_MATRIX,
    AttemptBoundary,
    AuthIdentityConfidence,
    AuthRealmFact,
    CANONICAL_SESSION_FIELD,
    CARDINALITY,
    CandidateResult,
    CapabilityClass,
    CapabilityIdentity,
    CapabilityManifest,
    EventCursor,
    FORBIDDEN_SESSION_SYNONYM,
    LIVE_APP_SERVER_ADOPTION,
    LaunchDecision,
    METHOD_CONTRACTS,
    MethodClass,
    NativeHelperPolicy,
    OPERATOR_HARNESS_INTERFACE_VERSION,
    ObservedHarnessAttestation,
    POST_RESTORE_ATTEMPT_STATUS,
    ProcessLiveness,
    ProviderWriterState,
    REATTEST_TRIGGERS,
    ReconcileReport,
    RequestedExecutionProfile,
    SessionEpochState,
    StageConfigReceipt,
    V1_QUALITY_TRADEOFF,
    WRITER_REALM_KEY,
    WorkspaceIdentity,
    WriterFacts,
    abandon_epoch,
    classify_capability,
    compare_launch,
    derive_resume_safety,
    first_work_turn_allowed,
    may_bind_provider_session,
    may_hold_executive_writer,
    native_helpers_allowed,
    process_end_does_not_release_writer,
    restore_invalidation,
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
        effective_skills=("ohf-probe",),
        effective_mcp=("ohf_probe",),
        effective_plugins_or_apps=(),
        sandbox_state="read-only",
        approval_state="never",
        effective_config_digest="cfg",
        auth=AuthRealmFact(
            worker_id="worker-1",
            provider="codex",
            identity_confidence=AuthIdentityConfidence.UNKNOWN,
        ),
        workspace=_workspace(),
    )
    payload.update(overrides)
    return ObservedHarnessAttestation(**payload)  # type: ignore[arg-type]


def test_cardinality_and_identity_constants():
    assert CARDINALITY == "CARDINALITY_B"
    assert CANONICAL_SESSION_FIELD == "provider_session_id"
    assert FORBIDDEN_SESSION_SYNONYM == "native_session_id"
    assert WRITER_REALM_KEY == ("worker_id", "provider_session_id")
    assert LIVE_APP_SERVER_ADOPTION == "NOT_SUPPORTED"
    assert V1_QUALITY_TRADEOFF == "V1_QUALITY_TRADEOFF_ACCEPTED"
    assert ACCOUNT_REALM_STATUS == "ACCOUNT_REALM_ATTESTATION_UNPROVEN"
    assert OPERATOR_HARNESS_INTERFACE_VERSION == "mastermind.operator_harness/v1"
    source = Path("control_plane/operator_harness_contract.py").read_text(encoding="utf-8")
    assert "native_session_id" in source
    assert source.count("FORBIDDEN_SESSION_SYNONYM") >= 1


def test_context_rotation_does_not_consume_attempt():
    assert ATTEMPT_BOUNDARY_MATRIX["context_rotation"] is AttemptBoundary.SAME_ATTEMPT
    assert ATTEMPT_BOUNDARY_MATRIX["fresh_primary_session_same_placement"] is AttemptBoundary.SAME_ATTEMPT
    assert ATTEMPT_BOUNDARY_MATRIX["sigkill_abandon_s1_start_s2"] is AttemptBoundary.SAME_ATTEMPT
    assert ATTEMPT_BOUNDARY_MATRIX["phase_1f_aggregation_after_leader_release"] is AttemptBoundary.NEW_ATTEMPT
    assert ATTEMPT_BOUNDARY_MATRIX["harness_binary_digest_change"] is AttemptBoundary.NEW_ATTEMPT
    assert ATTEMPT_BOUNDARY_MATRIX["cross_attempt_session_reuse"] is AttemptBoundary.REFUSE
    assert ATTEMPT_BOUNDARY_MATRIX["served_model_mismatch"] is AttemptBoundary.REFUSE


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
        facts=after,
        process_identity_match=True,
        workspace_match=True,
        profile_match=True,
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
    assert derive_resume_safety(
        epoch_state=SessionEpochState.ABANDONED,
        facts=abandoned,
        process_identity_match=True,
        workspace_match=True,
        profile_match=True,
    ) is False


def test_restore_invalidates_writer_and_uses_lost():
    facts = WriterFacts(
        process_liveness=ProcessLiveness.ALIVE,
        executive_writer_held=True,
        provider_writer_state=ProviderWriterState.HELD,
    )
    invalidated, status = restore_invalidation(facts)
    assert invalidated.executive_writer_held is False
    assert invalidated.process_liveness is ProcessLiveness.UNKNOWN
    assert invalidated.provider_writer_state is ProviderWriterState.HELD
    assert status == POST_RESTORE_ATTEMPT_STATUS == "LOST"
    released = WriterFacts(
        process_liveness=ProcessLiveness.PROVEN_DEAD,
        executive_writer_held=True,
        provider_writer_state=ProviderWriterState.RELEASED,
    )
    restored_released, _ = restore_invalidation(released)
    assert restored_released.provider_writer_state is ProviderWriterState.UNKNOWN


def test_live_stdio_adoption_never_resume_safe():
    facts = WriterFacts(
        process_liveness=ProcessLiveness.ALIVE,
        executive_writer_held=True,
        provider_writer_state=ProviderWriterState.HELD,
    )
    assert derive_resume_safety(
        epoch_state=SessionEpochState.CURRENT,
        facts=facts,
        process_identity_match=True,
        workspace_match=True,
        profile_match=True,
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
    unclassified = compare_launch(
        requested,
        _observed(),
        unclassified=("github:create-pr",),
    )
    assert unclassified.decision is LaunchDecision.REFUSE_UNCLASSIFIED


def test_lab_unclassified_requires_explicit_policy():
    requested = _requested(write_capable=False)
    without_policy = compare_launch(
        requested,
        _observed(),
        unclassified=("openai-templates:x",),
    )
    assert without_policy.decision is LaunchDecision.REFUSE_UNCLASSIFIED
    with_policy = compare_launch(
        requested,
        _observed(),
        unclassified=("openai-templates:x",),
        lab_unclassified_policy=True,
    )
    assert with_policy.decision is LaunchDecision.ALLOW


def test_capability_classes_and_helpers():
    assert classify_capability(
        "ohf-probe", required=["ohf-probe"], allowed_ambient=[], forbidden=[]
    ) is CapabilityClass.REQUIRED
    assert classify_capability(
        "mystery", required=["ohf-probe"], allowed_ambient=[], forbidden=[]
    ) is CapabilityClass.UNCLASSIFIED
    assert native_helpers_allowed(
        write_capable=False, supports_subagent_capability_ceiling=False
    )
    assert not native_helpers_allowed(
        write_capable=True, supports_subagent_capability_ceiling=False
    )
    assert native_helpers_allowed(
        write_capable=True, supports_subagent_capability_ceiling=True
    )
    write_wrong_policy = compare_launch(
        _requested(
            write_capable=True,
            native_helper_policy=NativeHelperPolicy.PARENT_READ_ONLY_CEILING,
        ),
        _observed(),
    )
    assert write_wrong_policy.decision is LaunchDecision.REFUSE_HELPER_CEILING_MISSING


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


def test_reconcile_cannot_decide_lifecycle():
    with pytest.raises(ValueError):
        ReconcileReport(
            process_liveness=ProcessLiveness.PROVEN_DEAD,
            process_identity_match=False,
            provider_session_reachable=None,
            provider_writer_state=ProviderWriterState.UNKNOWN,
            executive_writer_held=True,
            workspace_identity_match=True,
            profile_or_config_drift=False,
            resume_safe=False,
            may_kill=True,
        )


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
        assert spec.idempotent is True
    assert METHOD_CONTRACTS["resume_session"].classification is MethodClass.COMMON_OPTIONAL
    assert METHOD_CONTRACTS["fork_session"].classification is MethodClass.COMMON_OPTIONAL


def test_event_cursor_and_reattest_triggers():
    cursor = EventCursor(attempt_id="att-1", last_sequence=3)
    assert dataclasses.is_dataclass(cursor)
    assert "new_process_generation" in REATTEST_TRIGGERS
    assert "harness_config_reload" in REATTEST_TRIGGERS
    assert "authoritative_workspace_identity_change" in REATTEST_TRIGGERS
    assert "every_turn" not in REATTEST_TRIGGERS


def test_scenario_a_graceful_restart_same_epoch():
    assert ATTEMPT_BOUNDARY_MATRIX["graceful_process_replacement"] is AttemptBoundary.SAME_ATTEMPT
    released = WriterFacts(
        process_liveness=ProcessLiveness.PROVEN_DEAD,
        executive_writer_held=False,
        provider_writer_state=ProviderWriterState.RELEASED,
    )
    # New generation may attach to S1 after confirmed release.
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
