"""SQLite integration coverage for the production-inert OHF P1B state plane."""

from __future__ import annotations

import sqlite3

import pytest

from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.operator_harness_contract import (
    AuthRealmRequirement,
    AuthRealmFact,
    CapabilityManifest,
    CandidateResult,
    EventCursor,
    NativeHelperPolicy,
    NormalizedEvent,
    ObservedHarnessAttestation,
    ObservedTriState,
    OperationId,
    OperationReceiptKind,
    ProcessIdentityObservation,
    ProcessLiveness,
    ProviderWriterState,
    ReconcileObservation,
    RequestedExecutionProfile,
    TurnRef,
    WorkspaceIdentity,
    operation_receipt_command_id,
)


def _lease(tmp_path):
    runtime = Runtime.at(tmp_path)
    runtime.workers.register_worker(
        "worker-01", provider="codex", account_label="one", worker_type="test"
    )
    job = runtime.jobs.create_job("OHF state-plane test")
    lease = runtime.attempts.claim_job(job.job_id)
    assert lease is not None
    return runtime, lease


def _profile(lease):
    return RequestedExecutionProfile(
        worker_id=lease.attempt.worker_id,
        provider="codex",
        requested_model="test-model",
        harness_kind="fake",
        harness_binary_digest="a" * 64,
        harness_version="1",
        workspace=WorkspaceIdentity("/tmp/work", "b" * 40, 1, 2, 3, 4),
        sandbox_policy="read-only",
        approval_policy="never",
        network_policy="disabled",
        capabilities=CapabilityManifest(),
        native_helper_policy=NativeHelperPolicy.DISABLED,
        authority_policy_hash=lease.attempt.authority_policy_hash,
        auth_realm_requirement=AuthRealmRequirement.SLOT_BOUND_V1,
    )


def _attestation(profile):
    return ObservedHarnessAttestation(
        served_model=profile.requested_model,
        harness_version=profile.harness_version,
        harness_binary_digest=profile.harness_binary_digest,
        capabilities=(),
        effective_skills=(),
        effective_mcp=(),
        effective_plugins_or_apps=(),
        sandbox_state=profile.sandbox_policy,
        approval_state=profile.approval_policy,
        network_state=profile.network_policy,
        effective_config_digest=None,
        auth=AuthRealmFact(worker_id=profile.worker_id, provider=profile.provider),
        workspace=profile.workspace,
        supports_subagent_capability_ceiling=ObservedTriState.UNKNOWN,
    )


def test_tx1_to_tx5_is_event_plane_only_and_never_uses_legacy_identity(tmp_path):
    runtime, lease = _lease(tmp_path)
    harness = runtime.operator_harness
    profile = _profile(lease)
    sealed = harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        requested=profile,
    )
    assert sealed.execution_mode == "OPERATOR_HARNESS"
    epoch, generation = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        operation_id=OperationId("ohf-op:start-1"),
    )
    harness.bind_start_result(
        epoch=epoch,
        generation=generation,
        operation_id=OperationId("ohf-op:start-1"),
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="S1",
        process=ProcessIdentityObservation(11, 11, "start", "boot"),
    )
    assert harness.seal_attestation(
        generation=generation,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        requested=profile,
        attestation=_attestation(profile),
    )
    turn = harness.reserve_turn(
        epoch=epoch,
        generation=generation,
        operation_id=OperationId("ohf-op:turn-1"),
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
    )
    harness.acknowledge_turn(
        turn=turn,
        operation_id=OperationId("ohf-op:turn-1"),
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
    )
    current = runtime.attempts.get_attempt(sealed.attempt_id)
    assert (
        current is not None
        and current.pid is None
        and current.provider_session_id is None
    )
    with pytest.raises(StateConflict, match="legacy Attempt identity"):
        runtime.attempts.record_process_exit(
            sealed.attempt_id,
            fence_generation=sealed.fence_generation,
            lease_token=lease.lease_token,
            exit_code=0,
            provider_session_id="must-refuse",
        )
    assert runtime.events.get_event_by_command_id("ohf-op:turn-1:applied") is not None


def test_v3_writer_and_process_identity_constraints_are_enforced(tmp_path):
    runtime, lease = _lease(tmp_path)
    runtime.operator_harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        requested=_profile(lease),
    )
    epoch, generation = runtime.operator_harness.reserve_start(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        operation_id=OperationId("ohf-op:constraint-1"),
    )
    with pytest.raises(StateConflict, match="database invariant"):
        with runtime.store.transaction() as connection:
            connection.execute(
                """
                INSERT INTO process_generations(
                    process_generation_id,session_epoch_id,worker_id,
                    generation_number,pid,pgid,process_start_identity,boot_id,
                    started_at_ms,executive_writer_held,provider_writer_state,
                    created_at_ms
                ) VALUES('other',?,?,2,1,1,NULL,'boot',1,1,'UNKNOWN',1)
                """,
                (epoch.session_epoch_id, lease.attempt.worker_id),
            )
    assert generation.generation_number == 1


def test_tx9_invalidates_only_rich_live_authority_and_preserves_session_evidence(
    tmp_path,
):
    runtime, lease = _lease(tmp_path)
    harness = runtime.operator_harness
    sealed = harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        requested=_profile(lease),
    )
    epoch, generation = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        operation_id=OperationId("ohf-op:restore-start"),
    )
    harness.bind_start_result(
        epoch=epoch,
        generation=generation,
        operation_id=OperationId("ohf-op:restore-start"),
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="S1",
        process=ProcessIdentityObservation(21, 21, "start", "boot"),
    )
    assert harness.invalidate_after_restore() == 1
    with runtime.store.read() as connection:
        attempt = connection.execute(
            "SELECT status FROM attempts WHERE attempt_id=?", (sealed.attempt_id,)
        ).fetchone()
        epoch_row = connection.execute(
            "SELECT state,provider_session_id FROM harness_session_epochs WHERE session_epoch_id=?",
            (epoch.session_epoch_id,),
        ).fetchone()
        generation_row = connection.execute(
            "SELECT executive_writer_held,provider_session_id FROM process_generations WHERE process_generation_id=?",
            (generation.process_generation_id,),
        ).fetchone()
    assert attempt["status"] == "LOST"
    assert tuple(epoch_row) == ("ABANDONED", "S1")
    assert tuple(generation_row) == (0, "S1")
    assert (
        runtime.events.get_event_by_command_id(f"ohf-restore:{sealed.attempt_id}")
        is not None
    )


def test_tx10_tx11_resume_uses_typed_intent_and_matching_replay_is_noop(tmp_path):
    runtime, lease = _lease(tmp_path)
    harness = runtime.operator_harness
    sealed = harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        requested=_profile(lease),
    )
    epoch, g1 = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        operation_id=OperationId("ohf-op:resume-start"),
    )
    harness.bind_start_result(
        epoch=epoch,
        generation=g1,
        operation_id=OperationId("ohf-op:resume-start"),
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="S1",
        process=ProcessIdentityObservation(31, 31, "start-1", "boot"),
    )
    profile = _profile(lease)
    harness.seal_attestation(
        generation=g1,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        requested=profile,
        attestation=_attestation(profile),
    )
    harness.record_reconcile_observation(
        generation=g1,
        observation=ReconcileObservation(
            process_liveness=ProcessLiveness.PROVEN_DEAD,
            observed_process=ProcessIdentityObservation(31, 31, "start-1", "boot"),
            provider_session_reachable=True,
            provider_writer_state=ProviderWriterState.RELEASED,
            observed_provider_session_id="S1",
        ),
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
    )
    op = OperationId("ohf-op:resume-1")
    g2 = harness.reserve_same_epoch_resume(
        epoch=epoch,
        old_generation=g1,
        operation_id=op,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
    )
    assert (
        harness.reserve_same_epoch_resume(
            epoch=epoch,
            old_generation=g1,
            operation_id=op,
            fence_generation=sealed.fence_generation,
            lease_token=lease.lease_token,
        )
        == g2
    )
    assert (
        harness.bind_resume_result(
            epoch=epoch,
            generation=g2,
            operation_id=op,
            fence_generation=sealed.fence_generation,
            lease_token=lease.lease_token,
            provider_session_id="S1",
            process=ProcessIdentityObservation(32, 32, "start-2", "boot"),
        )
        == g2
    )
    assert (
        harness.bind_resume_result(
            epoch=epoch,
            generation=g2,
            operation_id=op,
            fence_generation=sealed.fence_generation,
            lease_token=lease.lease_token,
            provider_session_id="S1",
            process=ProcessIdentityObservation(32, 32, "start-2", "boot"),
        )
        == g2
    )
    with pytest.raises(StateConflict, match="already applied"):
        harness.bind_resume_result(
            epoch=epoch,
            generation=g2,
            operation_id=op,
            fence_generation=sealed.fence_generation,
            lease_token=lease.lease_token,
            provider_session_id="S1",
            process=ProcessIdentityObservation(33, 33, "changed", "boot"),
        )


def test_tx8_abandoned_epoch_allocates_exact_next_epoch_without_writer_steal(tmp_path):
    runtime, lease = _lease(tmp_path)
    harness = runtime.operator_harness
    profile = _profile(lease)
    sealed = harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        requested=profile,
    )
    e1, g1 = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        operation_id=OperationId("ohf-op:e1"),
    )
    harness.bind_start_result(
        epoch=e1,
        generation=g1,
        operation_id=OperationId("ohf-op:e1"),
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="S1",
        process=ProcessIdentityObservation(41, 41, "start-1", "boot"),
    )
    harness.record_hard_process_death(
        generation=g1,
        observation=ReconcileObservation(
            ProcessLiveness.PROVEN_DEAD,
            ProcessIdentityObservation(41, 41, "start-1", "boot"),
            True,
            ProviderWriterState.UNKNOWN,
            "S1",
        ),
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
    )
    harness.abandon_epoch(
        epoch=e1,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
    )

    e2, g2 = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        operation_id=OperationId("ohf-op:e2"),
    )
    assert e2.epoch_number == 2 and g2.generation_number == 1
    with runtime.store.read() as connection:
        assert (
            connection.execute(
                "SELECT SUM(executive_writer_held) FROM process_generations WHERE session_epoch_id=?",
                (e1.session_epoch_id,),
            ).fetchone()[0]
            == 0
        )


def test_applied_and_effect_unknown_are_mutually_exclusive(tmp_path):
    runtime, lease = _lease(tmp_path)
    harness = runtime.operator_harness
    profile = _profile(lease)
    sealed = harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        requested=profile,
    )
    op = OperationId("ohf-op:terminal-exclusive")
    epoch, generation = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        operation_id=op,
    )
    with pytest.raises(StateConflict, match="database invariant"):
        with runtime.store.transaction() as connection:
            connection.execute(
                """
                INSERT INTO process_generations(
                  process_generation_id,session_epoch_id,worker_id,
                  provider_session_id,generation_number,started_at_ms,
                  executive_writer_held,provider_writer_state,created_at_ms
                ) VALUES('inverse-session',?,?,'S1',2,1,0,'UNKNOWN',1)
                """,
                (epoch.session_epoch_id, lease.attempt.worker_id),
            )
    with pytest.raises(StateConflict, match="database invariant"):
        with runtime.store.transaction() as connection:
            connection.execute(
                """
                UPDATE process_generations SET provider_session_id='S1'
                WHERE process_generation_id=?
                """,
                (generation.process_generation_id,),
            )
    harness.bind_start_result(
        epoch=epoch,
        generation=generation,
        operation_id=op,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="S1",
        process=ProcessIdentityObservation(51, 51, "start", "boot"),
    )
    assert (
        harness.record_effect_unknown(
            attempt_id=sealed.attempt_id,
            operation_id=op,
            fence_generation=sealed.fence_generation,
            lease_token=lease.lease_token,
            phase="post_apply",
            detail="safe-code",
        )
        is False
    )
    assert (
        runtime.events.get_event_by_command_id(
            operation_receipt_command_id(op, OperationReceiptKind.EFFECT_UNKNOWN)
        )
        is None
    )


def test_candidate_requires_exact_tx5_intent_and_applied_provenance(tmp_path):
    runtime, lease = _lease(tmp_path)
    harness = runtime.operator_harness
    profile = _profile(lease)
    sealed = harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        requested=profile,
    )
    start = OperationId("ohf-op:candidate-start")
    epoch, generation = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        operation_id=start,
    )
    harness.bind_start_result(
        epoch=epoch,
        generation=generation,
        operation_id=start,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="S1",
        process=ProcessIdentityObservation(61, 61, "start", "boot"),
    )
    harness.seal_attestation(
        generation=generation,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        requested=profile,
        attestation=_attestation(profile),
    )
    op = OperationId("ohf-op:candidate-turn")
    turn = harness.reserve_turn(
        epoch=epoch,
        generation=generation,
        operation_id=op,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
    )
    candidate = CandidateResult(
        turn.attempt_id,
        turn.session_epoch_id,
        turn.process_generation_id,
        "f" * 64,
        "Bearer sk-provider-secret user@example.com",
    )
    cursor = EventCursor(
        turn.attempt_id,
        turn.session_epoch_id,
        turn.process_generation_id,
        turn_id=turn.turn_id,
    )
    with pytest.raises(StateConflict, match="TX-5 APPLIED"):
        harness.record_candidate_evidence(
            turn=turn,
            candidate=candidate,
            events=(),
            cursor=cursor,
            fence_generation=sealed.fence_generation,
            lease_token=lease.lease_token,
        )
    forged = TurnRef(
        "forged-turn",
        turn.session_epoch_id,
        turn.process_generation_id,
        turn.attempt_id,
    )
    with pytest.raises(StateConflict, match="TX-5 INTENT"):
        harness.record_candidate_evidence(
            turn=forged,
            candidate=candidate,
            events=(),
            cursor=EventCursor(
                turn.attempt_id,
                turn.session_epoch_id,
                turn.process_generation_id,
                turn_id="forged-turn",
            ),
            fence_generation=sealed.fence_generation,
            lease_token=lease.lease_token,
        )
    harness.acknowledge_turn(
        turn=turn,
        operation_id=op,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
    )
    malicious_event = NormalizedEvent(
        turn.attempt_id,
        turn.session_epoch_id,
        turn.process_generation_id,
        turn.turn_id,
        "provider",
        provider_event_id="sk-event-secret",
        payload_redacted={"API_KEY": "must-not-persist"},
    )
    harness.record_candidate_evidence(
        turn=turn,
        candidate=candidate,
        events=(malicious_event,),
        cursor=cursor,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
    )
    with runtime.store.read() as connection:
        persisted = connection.execute(
            "SELECT payload_json FROM events WHERE command_id=?",
            (f"ohf-candidate:{turn.turn_id}",),
        ).fetchone()[0]
    assert "sk-provider-secret" not in persisted
    assert "user@example.com" not in persisted
    assert "must-not-persist" not in persisted


def test_raw_sql_cannot_mutate_ohf_identity_or_bound_session_projection(tmp_path):
    runtime, lease = _lease(tmp_path)
    harness = runtime.operator_harness
    sealed = harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        requested=_profile(lease),
    )
    op = OperationId("ohf-op:immutable")
    epoch, generation = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        operation_id=op,
    )
    harness.bind_start_result(
        epoch=epoch,
        generation=generation,
        operation_id=op,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="S1",
        process=ProcessIdentityObservation(71, 71, "start", "boot"),
    )
    with pytest.raises(StateConflict, match="database invariant"):
        with runtime.store.transaction() as connection:
            connection.execute(
                """
                INSERT INTO process_generations(
                  process_generation_id,session_epoch_id,worker_id,
                  provider_session_id,generation_number,started_at_ms,
                  executive_writer_held,provider_writer_state,created_at_ms
                ) VALUES('missing-session',?,?,NULL,2,1,0,'UNKNOWN',1)
                """,
                (epoch.session_epoch_id, lease.attempt.worker_id),
            )
    mutations = [
        (
            "UPDATE harness_session_epochs SET attempt_id='forged' WHERE session_epoch_id=?",
            epoch.session_epoch_id,
        ),
        (
            "UPDATE harness_session_epochs SET worker_id='forged' WHERE session_epoch_id=?",
            epoch.session_epoch_id,
        ),
        (
            "UPDATE harness_session_epochs SET epoch_number=9 WHERE session_epoch_id=?",
            epoch.session_epoch_id,
        ),
        (
            "UPDATE process_generations SET session_epoch_id='forged' WHERE process_generation_id=?",
            generation.process_generation_id,
        ),
        (
            "UPDATE process_generations SET provider_session_id=NULL WHERE process_generation_id=?",
            generation.process_generation_id,
        ),
        (
            "UPDATE process_generations SET provider_session_id='S2' WHERE process_generation_id=?",
            generation.process_generation_id,
        ),
    ]
    for sql, target in mutations:
        with pytest.raises(StateConflict, match="database invariant"):
            with runtime.store.transaction() as connection:
                connection.execute(sql, (target,))
    with runtime.store.read() as connection:
        assert (
            connection.execute(
                """
            SELECT e.provider_session_id,g.provider_session_id
            FROM harness_session_epochs e
            JOIN process_generations g
              ON g.session_epoch_id=e.session_epoch_id
            WHERE g.process_generation_id=?
            """,
                (generation.process_generation_id,),
            ).fetchone()[:]
            == ("S1", "S1")
        )


@pytest.mark.parametrize("same_worker", [True, False])
def test_other_attempt_lease_cannot_target_durable_refs(tmp_path, same_worker):
    runtime = Runtime.at(tmp_path)
    if same_worker:
        runtime.workers.register_worker(
            "shared",
            provider="codex",
            account_label="one",
            worker_type="test",
            quota_classes=("qa", "qb"),
        )
        workers = ("shared", "shared")
    else:
        runtime.workers.register_worker(
            "worker-a",
            provider="codex",
            account_label="one",
            worker_type="test",
            quota_classes=("qa",),
        )
        runtime.workers.register_worker(
            "worker-b",
            provider="codex",
            account_label="two",
            worker_type="test",
            quota_classes=("qb",),
        )
        workers = ("worker-a", "worker-b")
    leases = []
    for index, quota in enumerate(("qa", "qb")):
        job = runtime.jobs.create_job(
            f"job-{quota}", constraints={"eligible_quota_classes": [quota]}
        )
        lease = runtime.attempts.claim_job(
            job.job_id, worker_id=workers[index], quota_class=quota
        )
        assert lease is not None
        profile = _profile(lease)
        runtime.operator_harness.seal_operator_harness_attempt(
            lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
            requested=profile,
        )
        op = OperationId(f"ohf-op:{quota}-start")
        epoch, generation = runtime.operator_harness.reserve_start(
            lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
            operation_id=op,
        )
        runtime.operator_harness.bind_start_result(
            epoch=epoch,
            generation=generation,
            operation_id=op,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
            provider_session_id=f"S-{quota}",
            process=ProcessIdentityObservation(
                801 if quota == "qa" else 802,
                801 if quota == "qa" else 802,
                f"start-{quota}",
                "boot",
            ),
        )
        runtime.operator_harness.seal_attestation(
            generation=generation,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
            requested=profile,
            attestation=_attestation(profile),
        )
        leases.append((lease, epoch, generation))
    lease_a, epoch_a, _ = leases[0]
    lease_b, epoch_b, generation_b = leases[1]
    forged_epoch = type(epoch_a)(
        epoch_b.session_epoch_id,
        epoch_a.attempt_id,
        epoch_a.worker_id,
        epoch_b.epoch_number,
    )
    with pytest.raises(StateConflict, match="owned|exact"):
        runtime.operator_harness.reserve_turn(
            epoch=forged_epoch,
            generation=generation_b,
            operation_id=OperationId("ohf-op:cross-turn"),
            fence_generation=lease_a.attempt.fence_generation,
            lease_token=lease_a.lease_token,
        )
    with pytest.raises(StateConflict, match="owned"):
        runtime.operator_harness.reserve_same_epoch_resume(
            epoch=forged_epoch,
            old_generation=generation_b,
            operation_id=OperationId("ohf-op:cross-resume"),
            fence_generation=lease_a.attempt.fence_generation,
            lease_token=lease_a.lease_token,
        )

    turn_op = OperationId("ohf-op:target-turn")
    turn_b = runtime.operator_harness.reserve_turn(
        epoch=epoch_b,
        generation=generation_b,
        operation_id=turn_op,
        fence_generation=lease_b.attempt.fence_generation,
        lease_token=lease_b.lease_token,
    )
    forged_turn = TurnRef(
        turn_b.turn_id,
        turn_b.session_epoch_id,
        turn_b.process_generation_id,
        lease_a.attempt.attempt_id,
    )
    with pytest.raises(StateConflict, match="TX-5 target mismatch"):
        runtime.operator_harness.acknowledge_turn(
            turn=forged_turn,
            operation_id=turn_op,
            fence_generation=lease_a.attempt.fence_generation,
            lease_token=lease_a.lease_token,
        )
    forged_candidate = CandidateResult(
        forged_turn.attempt_id,
        forged_turn.session_epoch_id,
        forged_turn.process_generation_id,
        "f" * 64,
        "candidate",
    )
    forged_cursor = EventCursor(
        forged_turn.attempt_id,
        forged_turn.session_epoch_id,
        forged_turn.process_generation_id,
        turn_id=forged_turn.turn_id,
    )
    with pytest.raises(StateConflict, match="TX-5 INTENT"):
        runtime.operator_harness.record_candidate_evidence(
            turn=forged_turn,
            candidate=forged_candidate,
            events=(),
            cursor=forged_cursor,
            fence_generation=lease_a.attempt.fence_generation,
            lease_token=lease_a.lease_token,
        )
    assert (
        runtime.events.get_event_by_command_id(
            operation_receipt_command_id(turn_op, OperationReceiptKind.APPLIED)
        )
        is None
    )
    assert (
        runtime.events.get_event_by_command_id(f"ohf-candidate:{turn_b.turn_id}")
        is None
    )


def test_other_attempt_lease_cannot_poison_provider_dispatch(tmp_path):
    runtime = Runtime.at(tmp_path)
    leases = []
    for worker in ("worker-a", "worker-b"):
        runtime.workers.register_worker(
            worker,
            provider="codex",
            account_label=worker,
            worker_type="test",
        )
        job = runtime.jobs.create_job(f"dispatch-{worker}")
        lease = runtime.attempts.claim_job(job.job_id, worker_id=worker)
        assert lease is not None
        runtime.operator_harness.seal_operator_harness_attempt(
            lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
            requested=_profile(lease),
        )
        leases.append(lease)

    lease_a, lease_b = leases
    operation = OperationId("ohf-op:dispatch-owner-a")
    runtime.operator_harness.reserve_start(
        lease_a.attempt.attempt_id,
        fence_generation=lease_a.attempt.fence_generation,
        lease_token=lease_a.lease_token,
        operation_id=operation,
    )
    with pytest.raises(StateConflict, match="matching operation INTENT"):
        runtime.operator_harness.commit_provider_dispatch(
            attempt_id=lease_b.attempt.attempt_id,
            operation_id=operation,
            operation_kind="start_session",
            fence_generation=lease_b.attempt.fence_generation,
            lease_token=lease_b.lease_token,
        )
    assert (
        runtime.events.get_event_by_command_id(f"{operation.command_id}:dispatch")
        is None
    )
    assert runtime.operator_harness.commit_provider_dispatch(
        attempt_id=lease_a.attempt.attempt_id,
        operation_id=operation,
        operation_kind="start_session",
        fence_generation=lease_a.attempt.fence_generation,
        lease_token=lease_a.lease_token,
    )
