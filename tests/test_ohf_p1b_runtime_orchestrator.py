"""Real Executive Event/SQLite integration for the unarmed OHF orchestrator."""

from __future__ import annotations

import inspect
from dataclasses import replace
from pathlib import Path

import pytest

from control_plane.executive_operator_harness_port import (
    ExecutiveOperatorHarnessPort,
)
from control_plane.executive_runtime import (
    AttemptStatus,
    JobStatus,
    Runtime,
    StateConflict,
)
from control_plane.operator_harness_contract import (
    ACCOUNT_REALM_STATUS,
    AuthRealmFact,
    CandidateResult,
    CapabilityManifest,
    EventCursor,
    LaunchDecision,
    NativeHelperPolicy,
    NormalizedEvent,
    ObservedHarnessAttestation,
    ObservedTriState,
    OperationId,
    OperationReceiptKind,
    ProcessGenerationRef,
    ProcessIdentityObservation,
    ProcessLiveness,
    ProfileValidation,
    ProviderSessionHandoff,
    ProviderWriterState,
    ReconcileObservation,
    RequestedExecutionProfile,
    SessionStartObservation,
    TurnStartObservation,
    WorkspaceIdentity,
    operation_receipt_command_id,
)
from control_plane.operator_harness_orchestrator import (
    OperatorEffectUnknown,
    OperatorHarnessOrchestrator,
    OperatorOperationApplied,
    OperatorStartRefused,
)


def _op(suffix: str) -> OperationId:
    return OperationId(f"ohf-op:{suffix}")


class _Clock:
    def __init__(self) -> None:
        self.value = 1_900_000_000_000

    def __call__(self) -> int:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += seconds * 1000


def _runtime_lease(tmp_path):
    runtime = Runtime.at(tmp_path)
    runtime.workers.register_worker(
        "worker-01", provider="openai-codex", account_label="one", worker_type="test"
    )
    job = runtime.jobs.create_job("OHF real-port integration")
    lease = runtime.attempts.claim_job(job.job_id)
    assert lease is not None
    return runtime, job, lease


@pytest.mark.parametrize("shape", ["sealed", "active", "abandoned"])
def test_expired_ohf_takeover_preserves_authority_and_recovers_lawful_shapes(
    tmp_path, shape
) -> None:
    clock = _Clock()
    runtime = Runtime.at(tmp_path, clock=clock, lease_seconds=2)
    runtime.workers.register_worker(
        "worker-01", provider="openai-codex", account_label="one", worker_type="test"
    )
    job = runtime.jobs.create_job("takeover")
    old = runtime.attempts.claim_job(job.job_id)
    assert old is not None
    profile = _profile(old)
    runtime.operator_harness.seal_operator_harness_attempt(
        old.attempt.attempt_id,
        fence_generation=old.attempt.fence_generation,
        lease_token=old.lease_token,
        requested=profile,
    )
    epoch = generation = None
    if shape != "sealed":
        epoch, generation = runtime.operator_harness.reserve_start(
            old.attempt.attempt_id,
            fence_generation=old.attempt.fence_generation,
            lease_token=old.lease_token,
            operation_id=_op(f"takeover-{shape}"),
        )
        runtime.operator_harness.bind_start_result(
            epoch=epoch,
            generation=generation,
            operation_id=_op(f"takeover-{shape}"),
            fence_generation=old.attempt.fence_generation,
            lease_token=old.lease_token,
            provider_session_id="S1",
            process=ProcessIdentityObservation(901, 901, "start-901", "boot"),
        )
        if shape == "abandoned":
            dead = ReconcileObservation(
                ProcessLiveness.PROVEN_DEAD,
                ProcessIdentityObservation(901, 901, "start-901", "boot"),
                True,
                ProviderWriterState.RELEASED,
                "S1",
            )
            runtime.operator_harness.record_hard_process_death(
                generation=generation,
                observation=dead,
                fence_generation=old.attempt.fence_generation,
                lease_token=old.lease_token,
            )
            runtime.operator_harness.abandon_epoch(
                epoch=epoch,
                fence_generation=old.attempt.fence_generation,
                lease_token=old.lease_token,
            )
    clock.advance(3)
    runtime.attempts.reconcile_expired()
    current = runtime.attempts.get_attempt(old.attempt.attempt_id)
    assert current is not None and current.status in {
        AttemptStatus.CLAIMED,
        AttemptStatus.RUNNING,
    }
    assert runtime.jobs.get_job(job.job_id).status in {
        JobStatus.RUNNING,
        JobStatus.CHECKPOINTED,
    }
    with pytest.raises(StateConflict):
        runtime.attempts.heartbeat_attempt(
            old.attempt.attempt_id,
            fence_generation=old.attempt.fence_generation,
            lease_token=old.lease_token,
        )
    replacement = runtime.attempts.takeover_expired_operator_harness(
        old.attempt.attempt_id,
        expected_fence_generation=old.attempt.fence_generation,
        lease_owner="recovery",
        lease_seconds=30,
    )
    assert replacement.attempt.fence_generation == old.attempt.fence_generation + 1
    port = ExecutiveOperatorHarnessPort(runtime, replacement)
    if shape == "sealed":
        port.begin_operator_session(
            replacement.attempt.attempt_id, _op("takeover-sealed-e1")
        )
    elif shape == "active":
        assert generation is not None and epoch is not None
        dead = ReconcileObservation(
            ProcessLiveness.PROVEN_DEAD,
            ProcessIdentityObservation(901, 901, "start-901", "boot"),
            True,
            ProviderWriterState.UNKNOWN,
            "S1",
        )
        runtime.operator_harness.record_hard_process_death(
            generation=generation,
            observation=dead,
            fence_generation=replacement.attempt.fence_generation,
            lease_token=replacement.lease_token,
        )
        runtime.operator_harness.abandon_epoch(
            epoch=epoch,
            fence_generation=replacement.attempt.fence_generation,
            lease_token=replacement.lease_token,
        )
    else:
        epoch2, _ = port.begin_operator_session(
            replacement.attempt.attempt_id, _op("takeover-abandoned-e2")
        )
        assert epoch2.epoch_number == 2


def _profile(lease) -> RequestedExecutionProfile:
    return RequestedExecutionProfile(
        worker_id=lease.attempt.worker_id,
        provider="openai-codex",
        requested_model="gpt-5.6-sol",
        harness_kind="fake-app-server",
        harness_binary_digest="a" * 64,
        harness_version="fake/1",
        workspace=WorkspaceIdentity("/work", "b" * 40, 1, 2, 3, 4),
        sandbox_policy="read-only",
        approval_policy="never",
        network_policy="restricted",
        capabilities=CapabilityManifest(),
        native_helper_policy=NativeHelperPolicy.DISABLED,
        authority_policy_hash=lease.attempt.authority_policy_hash,
    )


def _attestation(profile: RequestedExecutionProfile) -> ObservedHarnessAttestation:
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
        effective_config_digest="d" * 64,
        auth=AuthRealmFact(
            worker_id=profile.worker_id,
            provider=profile.provider,
            attestation_status=ACCOUNT_REALM_STATUS,
        ),
        workspace=profile.workspace,
        supports_subagent_capability_ceiling=ObservedTriState.FALSE,
    )


class FakeAdapter:
    interface_version = "mastermind.operator_harness/v1"

    def __init__(self, profile: RequestedExecutionProfile) -> None:
        self.profile = profile
        self.attestations: dict[str, ObservedHarnessAttestation] = {}
        self.calls: list[str] = []
        self.fail_start = False
        self.session_id = "S1"
        self.process_number = 100
        self.reconcile_observation: ReconcileObservation | None = None
        self.stop_observation: ReconcileObservation | None = None

    def validate_requested_profile(self, requested):
        self.calls.append("validate")
        return ProfileValidation(
            requested=requested, accepted=requested == self.profile
        )

    def start_session(self, *, generation, **kwargs):
        self.calls.append("start_session")
        if self.fail_start:
            raise RuntimeError("Bearer sk-release-secret API_KEY=must-not-persist")
        self.attestations[generation.process_generation_id] = _attestation(self.profile)
        return SessionStartObservation(
            provider_session_id=self.session_id,
            process=ProcessIdentityObservation(
                self.process_number,
                self.process_number,
                f"start-{self.process_number}",
                "boot",
            ),
        )

    def observed_attestation(self, generation):
        return self.attestations[generation.process_generation_id]

    def begin_turn(self, *, turn, **kwargs):
        self.calls.append("begin_turn")
        return TurnStartObservation(
            provider_native_turn_id=f"native-{turn.turn_id}", acknowledged=True
        )

    def read_events(self, cursor, *, timeout_seconds=30.0):
        self.calls.append("read_events")
        event = NormalizedEvent(
            attempt_id=cursor.attempt_id,
            session_epoch_id=cursor.session_epoch_id,
            process_generation_id=cursor.process_generation_id,
            turn_id=cursor.turn_id,
            kind="turn/completed",
        )
        return (event,), replace(cursor, local_sequence=cursor.local_sequence + 1)

    def collect_candidate_result(self, turn):
        self.calls.append("collect_candidate_result")
        return CandidateResult(
            attempt_id=turn.attempt_id,
            session_epoch_id=turn.session_epoch_id,
            process_generation_id=turn.process_generation_id,
            artifact_digest="e" * 64,
            summary="provider candidate only",
        )

    def graceful_stop(self, generation, *, operation_id):
        self.calls.append("graceful_stop")
        if self.stop_observation is not None:
            return self.stop_observation
        return self._dead(generation, ProviderWriterState.RELEASED)

    def cancel(self, generation, *, reason, operation_id):
        self.calls.append("cancel")
        return self._dead(generation, ProviderWriterState.UNKNOWN)

    def reconcile(self, generation):
        self.calls.append("reconcile")
        if self.reconcile_observation is not None:
            return self.reconcile_observation
        return self._dead(generation, ProviderWriterState.RELEASED)

    def resume_session(self, *, generation, provider_session, **kwargs):
        self.calls.append("resume_session")
        self.process_number += 1
        self.session_id = provider_session.provider_session_id
        self.attestations[generation.process_generation_id] = _attestation(self.profile)
        return SessionStartObservation(
            provider_session_id=self.session_id,
            process=ProcessIdentityObservation(
                self.process_number,
                self.process_number,
                f"start-{self.process_number}",
                "boot",
            ),
        )

    def _dead(self, generation, writer):
        number = 100 if generation.generation_number == 1 else self.process_number
        return ReconcileObservation(
            process_liveness=ProcessLiveness.PROVEN_DEAD,
            observed_process=ProcessIdentityObservation(
                number, number, f"start-{number}", "boot"
            ),
            provider_session_reachable=True,
            provider_writer_state=writer,
            observed_provider_session_id=self.session_id,
            observed_config_digest="d" * 64,
        )

    def interrupt_turn(self, turn, *, operation_id):  # pragma: no cover
        raise NotImplementedError

    def describe_capabilities(self):  # pragma: no cover
        raise NotImplementedError


def _orchestrator(runtime, lease, adapter):
    port = ExecutiveOperatorHarnessPort(runtime, lease)
    return port, OperatorHarnessOrchestrator(
        port,
        adapter,
        attestation_reader=lambda item, generation: item.observed_attestation(
            generation
        ),
    )


class _FailAfterBindPort(ExecutiveOperatorHarnessPort):
    def bind_operator_session(self, attempt_id, operation_id, observation):
        super().bind_operator_session(attempt_id, operation_id, observation)
        raise RuntimeError("injected crash after durable TX-3")


def _event_types(runtime: Runtime) -> list[str]:
    with runtime.store.read() as connection:
        return [
            str(row["event_type"])
            for row in connection.execute(
                "SELECT event_type FROM events ORDER BY event_id"
            )
        ]


def test_real_runtime_end_to_end_orders_events_and_keeps_candidate_non_authoritative(
    tmp_path,
) -> None:
    runtime, job, lease = _runtime_lease(tmp_path)
    profile = _profile(lease)
    adapter = FakeAdapter(profile)
    _, orchestrator = _orchestrator(runtime, lease, adapter)

    session = orchestrator.start_attempt(
        attempt_id=lease.attempt.attempt_id,
        requested=profile,
        operation_id=_op("e2e-start"),
    )
    turn = orchestrator.run_turn(session, operation_id=_op("e2e-turn"))
    stopped = orchestrator.graceful_stop(session, operation_id=_op("e2e-stop"))

    assert session.launch.decision is LaunchDecision.ALLOW
    assert turn.candidate.complete_job_permitted is False
    assert stopped.provider_writer_state is ProviderWriterState.RELEASED
    event_types = _event_types(runtime)
    ordered = [
        "OHF_PROFILE_SEALED",
        "OPERATOR_OPERATION_INTENT",
        "OPERATOR_OPERATION_APPLIED",
        "OHF_ATTESTATION_OBSERVED",
        "OHF_LAUNCH_DECISION",
        "OPERATOR_OPERATION_INTENT",
        "OPERATOR_OPERATION_APPLIED",
        "OHF_CANDIDATE_RESULT_RECORDED",
        "OPERATOR_OPERATION_INTENT",
        "OPERATOR_OPERATION_APPLIED",
    ]
    cursor = 0
    for event_type in event_types:
        if cursor < len(ordered) and event_type == ordered[cursor]:
            cursor += 1
    assert cursor == len(ordered)

    candidate_event = runtime.events.get_event_by_command_id(
        f"ohf-candidate:{turn.turn.turn_id}"
    )
    assert candidate_event is not None
    assert candidate_event.payload["candidate"]["complete_job_permitted"] is False
    turn_applied = runtime.events.get_event_by_command_id(
        operation_receipt_command_id(_op("e2e-turn"), OperationReceiptKind.APPLIED)
    )
    assert turn_applied is not None
    assert turn_applied.payload["provider_native_turn_id"].startswith("native-")
    attempt = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    current_job = runtime.jobs.get_job(job.job_id)
    assert attempt is not None and attempt.status is AttemptStatus.RUNNING
    assert current_job is not None and current_job.status is JobStatus.RUNNING
    with runtime.store.read() as connection:
        generation = connection.execute(
            """
            SELECT ended_at_ms,executive_writer_held,provider_writer_state
            FROM process_generations WHERE process_generation_id=?
            """,
            (session.generation.process_generation_id,),
        ).fetchone()
    assert tuple(generation) == (generation["ended_at_ms"], 0, "RELEASED")
    assert generation["ended_at_ms"] is not None


def test_real_runtime_refuses_before_provider_when_intent_cannot_commit(
    tmp_path,
) -> None:
    runtime, _, lease = _runtime_lease(tmp_path)
    profile = _profile(lease)
    adapter = FakeAdapter(profile)
    port, orchestrator = _orchestrator(runtime, lease, adapter)
    port.seal_operator_attempt(lease.attempt.attempt_id, profile)
    port.begin_operator_session(lease.attempt.attempt_id, _op("preexisting"))

    with pytest.raises(StateConflict):
        orchestrator.start_attempt(
            attempt_id=lease.attempt.attempt_id,
            requested=profile,
            operation_id=_op("must-refuse"),
        )

    assert "start_session" not in adapter.calls


def test_real_runtime_effect_unknown_is_durable_and_blocks_restart_replay(
    tmp_path,
) -> None:
    runtime, _, lease = _runtime_lease(tmp_path)
    profile = _profile(lease)
    adapter = FakeAdapter(profile)
    adapter.fail_start = True
    _, orchestrator = _orchestrator(runtime, lease, adapter)
    operation = _op("unknown-start")

    with pytest.raises(OperatorEffectUnknown):
        orchestrator.start_attempt(
            attempt_id=lease.attempt.attempt_id,
            requested=profile,
            operation_id=operation,
        )
    effect = runtime.events.get_event_by_command_id(
        operation_receipt_command_id(operation, OperationReceiptKind.EFFECT_UNKNOWN)
    )
    assert effect is not None
    assert effect.payload["phase"] == "start_session"
    assert "must-not-persist" not in str(effect.payload)
    assert "sk-release-secret" not in str(effect.payload)

    _, restarted = _orchestrator(runtime, lease, adapter)
    with pytest.raises(StateConflict):
        restarted.start_attempt(
            attempt_id=lease.attempt.attempt_id,
            requested=profile,
            operation_id=operation,
        )
    assert adapter.calls.count("start_session") == 1


@pytest.mark.parametrize("operation", ["start", "turn"])
def test_same_operation_retries_only_before_durable_provider_dispatch(
    tmp_path, operation
) -> None:
    runtime, _, lease = _runtime_lease(tmp_path)
    profile = _profile(lease)
    adapter = FakeAdapter(profile)
    port, orchestrator = _orchestrator(runtime, lease, adapter)
    start_op = _op(f"dispatch-{operation}-start")
    if operation == "start":
        port.seal_operator_attempt(lease.attempt.attempt_id, profile)
        epoch, _ = port.begin_operator_session(lease.attempt.attempt_id, start_op)
        receipt = orchestrator.start_attempt(
            attempt_id=lease.attempt.attempt_id,
            requested=profile,
            operation_id=start_op,
        )
        assert receipt.epoch == epoch
        runtime, _, lease = _runtime_lease(tmp_path / "post-marker")
        profile = _profile(lease)
        adapter = FakeAdapter(profile)
        port, orchestrator = _orchestrator(runtime, lease, adapter)
        port.seal_operator_attempt(lease.attempt.attempt_id, profile)
        target_op = _op("dispatch-start-post")
        port.begin_operator_session(lease.attempt.attempt_id, target_op)
        assert port.commit_operator_provider_dispatch(
            lease.attempt.attempt_id, target_op, "start_session"
        )
        calls = adapter.calls.count("start_session")
        with pytest.raises(OperatorEffectUnknown):
            orchestrator.start_attempt(
                attempt_id=lease.attempt.attempt_id,
                requested=profile,
                operation_id=target_op,
            )
        assert adapter.calls.count("start_session") == calls
    else:
        session = orchestrator.start_attempt(
            attempt_id=lease.attempt.attempt_id,
            requested=profile,
            operation_id=start_op,
        )
        pre = _op("dispatch-turn-pre")
        allocated = port.begin_operator_turn(
            lease.attempt.attempt_id, session.generation, pre
        )
        result = orchestrator.run_turn(session, operation_id=pre)
        assert result.turn == allocated
        post = _op("dispatch-turn-post")
        port.begin_operator_turn(lease.attempt.attempt_id, session.generation, post)
        assert port.commit_operator_provider_dispatch(
            lease.attempt.attempt_id, post, "begin_turn"
        )
        calls = adapter.calls.count("begin_turn")
        with pytest.raises(OperatorEffectUnknown):
            orchestrator.run_turn(session, operation_id=post)
        assert adapter.calls.count("begin_turn") == calls
    unknown = runtime.events.get_event_by_command_id(
        operation_receipt_command_id(
            target_op if operation == "start" else post,
            OperationReceiptKind.EFFECT_UNKNOWN,
        )
    )
    assert unknown is not None


@pytest.mark.parametrize("reader_failure", ["mismatch", "exception"])
def test_attestation_failure_returns_handle_for_durable_cleanup_and_terminalization(
    tmp_path, reader_failure
) -> None:
    runtime, job, lease = _runtime_lease(tmp_path)
    profile = _profile(lease)
    adapter = FakeAdapter(profile)
    port = ExecutiveOperatorHarnessPort(runtime, lease)

    def read_attestation(item, generation):
        if reader_failure == "exception":
            raise RuntimeError("attestation reader failed")
        return replace(item.observed_attestation(generation), served_model="wrong")

    orchestrator = OperatorHarnessOrchestrator(
        port,
        adapter,
        attestation_reader=read_attestation,
    )
    with pytest.raises(OperatorStartRefused) as caught:
        orchestrator.start_attempt(
            attempt_id=lease.attempt.attempt_id,
            requested=profile,
            operation_id=_op("refused-cleanup-start"),
        )
    handle = caught.value.handle
    observed = orchestrator.graceful_stop(
        handle, operation_id=_op("refused-cleanup-stop")
    )
    assert observed.process_liveness is ProcessLiveness.PROVEN_DEAD
    runtime.operator_harness.abandon_epoch(
        epoch=handle.epoch,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    runtime.attempts.fail_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        payload={"summary": "attestation refused"},
    )
    assert runtime.jobs.get_job(job.job_id).status is JobStatus.FAILED
    with runtime.store.read() as connection:
        assert (
            connection.execute(
                "SELECT executive_writer_held FROM process_generations WHERE process_generation_id=?",
                (handle.generation.process_generation_id,),
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT held_attempt_id FROM worker_quota_classes WHERE worker_id=? AND quota_class=?",
                (lease.attempt.worker_id, lease.attempt.quota_class),
            ).fetchone()[0]
            is None
        )


def test_crash_after_provider_and_tx3_is_effect_unknown_without_second_call(
    tmp_path,
) -> None:
    runtime, _, lease = _runtime_lease(tmp_path)
    profile = _profile(lease)
    adapter = FakeAdapter(profile)
    port = _FailAfterBindPort(runtime, lease)
    orchestrator = OperatorHarnessOrchestrator(
        port,
        adapter,
        attestation_reader=lambda item, generation: item.observed_attestation(
            generation
        ),
    )
    operation = _op("post-bind-crash")

    with pytest.raises(OperatorOperationApplied):
        orchestrator.start_attempt(
            attempt_id=lease.attempt.attempt_id,
            requested=profile,
            operation_id=operation,
        )
    assert (
        runtime.events.get_event_by_command_id(
            operation_receipt_command_id(operation, OperationReceiptKind.APPLIED)
        )
        is not None
    )
    assert (
        runtime.events.get_event_by_command_id(
            operation_receipt_command_id(operation, OperationReceiptKind.EFFECT_UNKNOWN)
        )
        is None
    )

    _, restarted = _orchestrator(runtime, lease, adapter)
    with pytest.raises(StateConflict):
        restarted.start_attempt(
            attempt_id=lease.attempt.attempt_id,
            requested=profile,
            operation_id=operation,
        )
    assert adapter.calls.count("start_session") == 1


def test_stop_application_requires_dead_and_released_after_committed_intent(
    tmp_path,
) -> None:
    runtime, _, lease = _runtime_lease(tmp_path)
    profile = _profile(lease)
    adapter = FakeAdapter(profile)
    _, orchestrator = _orchestrator(runtime, lease, adapter)
    session = orchestrator.start_attempt(
        attempt_id=lease.attempt.attempt_id,
        requested=profile,
        operation_id=_op("bad-stop-start"),
    )
    adapter.stop_observation = ReconcileObservation(
        process_liveness=ProcessLiveness.ALIVE,
        observed_process=session.observation.process,
        provider_session_reachable=True,
        provider_writer_state=ProviderWriterState.RELEASED,
        observed_provider_session_id="S1",
    )
    operation = _op("bad-stop")

    with pytest.raises(OperatorEffectUnknown):
        orchestrator.graceful_stop(session, operation_id=operation)

    intent = runtime.events.get_event_by_command_id(operation.command_id)
    effect = runtime.events.get_event_by_command_id(
        operation_receipt_command_id(operation, OperationReceiptKind.EFFECT_UNKNOWN)
    )
    assert intent is not None
    assert intent.payload["schema_version"].endswith("/v1")
    assert effect is not None
    with runtime.store.read() as connection:
        generation = connection.execute(
            """
            SELECT ended_at_ms,executive_writer_held
            FROM process_generations WHERE process_generation_id=?
            """,
            (session.generation.process_generation_id,),
        ).fetchone()
    assert tuple(generation) == (None, 1)


def test_tx6_compatibility_api_requires_proven_dead_before_release(tmp_path) -> None:
    runtime, _, lease = _runtime_lease(tmp_path)
    profile = _profile(lease)
    adapter = FakeAdapter(profile)
    _, orchestrator = _orchestrator(runtime, lease, adapter)
    session = orchestrator.start_attempt(
        attempt_id=lease.attempt.attempt_id,
        requested=profile,
        operation_id=_op("tx6-start"),
    )

    with pytest.raises(StateConflict, match="PROVEN_DEAD"):
        runtime.operator_harness.record_graceful_stop(
            generation=session.generation,
            observation=ReconcileObservation(
                ProcessLiveness.ALIVE,
                ProcessIdentityObservation(100, 100, "start-100", "boot"),
                True,
                ProviderWriterState.RELEASED,
                "S1",
            ),
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        )
    forged_generation = ProcessGenerationRef(
        session.generation.process_generation_id,
        "wrong-epoch",
        session.generation.generation_number,
        session.generation.worker_id,
    )
    with pytest.raises(StateConflict, match="exactly owned"):
        runtime.operator_harness.record_hard_process_death(
            generation=forged_generation,
            observation=ReconcileObservation(
                ProcessLiveness.PROVEN_DEAD,
                session.observation.process,
                True,
                ProviderWriterState.UNKNOWN,
                "S1",
            ),
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        )
    with pytest.raises(StateConflict, match="process identity mismatch"):
        runtime.operator_harness.record_graceful_stop(
            generation=session.generation,
            observation=ReconcileObservation(
                ProcessLiveness.PROVEN_DEAD,
                ProcessIdentityObservation(999, 999, "wrong", "boot"),
                True,
                ProviderWriterState.RELEASED,
                "S1",
            ),
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        )
    runtime.operator_harness.record_graceful_stop(
        generation=session.generation,
        observation=ReconcileObservation(
            ProcessLiveness.PROVEN_DEAD,
            ProcessIdentityObservation(100, 100, "start-100", "boot"),
            True,
            ProviderWriterState.RELEASED,
            "S1",
        ),
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    with runtime.store.read() as connection:
        held = connection.execute(
            """
            SELECT executive_writer_held FROM process_generations
            WHERE process_generation_id=?
            """,
            (session.generation.process_generation_id,),
        ).fetchone()[0]
    assert held == 0


def test_cancel_records_death_but_keeps_writer_without_explicit_release(
    tmp_path,
) -> None:
    runtime, _, lease = _runtime_lease(tmp_path)
    profile = _profile(lease)
    adapter = FakeAdapter(profile)
    _, orchestrator = _orchestrator(runtime, lease, adapter)
    session = orchestrator.start_attempt(
        attempt_id=lease.attempt.attempt_id,
        requested=profile,
        operation_id=_op("cancel-start"),
    )

    observation = orchestrator.cancel(
        session, operation_id=_op("cancel"), reason="test"
    )
    assert observation.provider_writer_state is ProviderWriterState.UNKNOWN
    with runtime.store.read() as connection:
        generation = connection.execute(
            """
            SELECT ended_at_ms,executive_writer_held,provider_writer_state
            FROM process_generations WHERE process_generation_id=?
            """,
            (session.generation.process_generation_id,),
        ).fetchone()
    assert generation["ended_at_ms"] is not None
    assert tuple(generation)[1:] == (1, "UNKNOWN")


def test_legacy_terminal_rate_limit_and_cancel_cannot_bypass_live_ohf_writer(
    tmp_path,
) -> None:
    runtime, job, lease = _runtime_lease(tmp_path)
    profile = _profile(lease)
    adapter = FakeAdapter(profile)
    _, orchestrator = _orchestrator(runtime, lease, adapter)
    orchestrator.start_attempt(
        attempt_id=lease.attempt.attempt_id,
        requested=profile,
        operation_id=_op("legacy-guard-start"),
    )
    mutations = (
        lambda: runtime.attempts.complete_attempt(
            lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
            payload={"summary": "forged"},
        ),
        lambda: runtime.attempts.fail_attempt(
            lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
            payload={"summary": "forged"},
        ),
        lambda: runtime.attempts.rate_limit_attempt(
            lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        ),
    )
    for mutation in mutations:
        with pytest.raises(StateConflict, match="shutdown/abandon"):
            mutation()
    runtime.jobs.cancel_job(job.job_id)
    with pytest.raises(StateConflict, match="shutdown/abandon"):
        runtime.attempts.acknowledge_cancel(
            lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        )
    with runtime.store.read() as connection:
        assert (
            connection.execute(
                "SELECT held_attempt_id FROM worker_quota_classes WHERE worker_id=? AND quota_class=?",
                (lease.attempt.worker_id, lease.attempt.quota_class),
            ).fetchone()[0]
            == lease.attempt.attempt_id
        )
        assert (
            connection.execute(
                "SELECT SUM(executive_writer_held) FROM process_generations WHERE session_epoch_id IN (SELECT session_epoch_id FROM harness_session_epochs WHERE attempt_id=?)",
                (lease.attempt.attempt_id,),
            ).fetchone()[0]
            == 1
        )


def test_resume_safety_is_derived_from_durable_reconcile_and_never_allocates_g3(
    tmp_path,
) -> None:
    runtime, _, lease = _runtime_lease(tmp_path)
    profile = _profile(lease)
    adapter = FakeAdapter(profile)
    port, orchestrator = _orchestrator(runtime, lease, adapter)
    session = orchestrator.start_attempt(
        attempt_id=lease.attempt.attempt_id,
        requested=profile,
        operation_id=_op("resume-start"),
    )

    with pytest.raises(StateConflict, match="derived recovery"):
        port.begin_operator_resume(
            lease.attempt.attempt_id, session.epoch, _op("unsafe-resume")
        )
    assert "resume_session" not in adapter.calls

    adapter.reconcile_observation = adapter._dead(
        session.generation, ProviderWriterState.UNKNOWN
    )
    orchestrator.reconcile(session)
    with pytest.raises(StateConflict, match="derived recovery"):
        port.begin_operator_resume(
            lease.attempt.attempt_id,
            session.epoch,
            _op("unsafe-writer-unknown"),
        )
    assert "resume_session" not in adapter.calls

    adapter.reconcile_observation = None
    observed = orchestrator.reconcile(session)
    assert observed.process_liveness is ProcessLiveness.PROVEN_DEAD
    reconcile_events = [
        event_type
        for event_type in _event_types(runtime)
        if event_type == "OHF_RECONCILE_OBSERVED"
    ]
    assert reconcile_events == [
        "OHF_RECONCILE_OBSERVED",
        "OHF_RECONCILE_OBSERVED",
    ]
    safe_op = _op("safe-resume")
    allocated_g2 = port.begin_operator_resume(
        lease.attempt.attempt_id, session.epoch, safe_op
    )
    assert (
        port.begin_operator_resume(lease.attempt.attempt_id, session.epoch, safe_op)
        == allocated_g2
    )
    resumed = orchestrator.resume(
        session,
        operation_id=safe_op,
        handoff=ProviderSessionHandoff("S1", "worker-01"),
    )
    assert resumed.generation.generation_number == 2
    assert resumed.generation == allocated_g2
    assert resumed.observation.provider_session_id == "S1"

    resume_calls = adapter.calls.count("resume_session")
    with pytest.raises(StateConflict):
        orchestrator.resume(
            resumed,
            operation_id=_op("must-not-create-g3"),
            handoff=ProviderSessionHandoff("S1", "worker-01"),
        )
    assert adapter.calls.count("resume_session") == resume_calls
    with runtime.store.read() as connection:
        generations = connection.execute(
            """
            SELECT generation_number FROM process_generations
            WHERE session_epoch_id=? ORDER BY generation_number
            """,
            (session.epoch.session_epoch_id,),
        ).fetchall()
    assert [row["generation_number"] for row in generations] == [1, 2]
    assert (
        "resume_safe"
        not in inspect.signature(
            runtime.operator_harness.reserve_same_epoch_resume
        ).parameters
    )


def test_resume_restart_after_dispatch_is_effect_unknown_without_provider_replay(
    tmp_path,
) -> None:
    runtime, _, lease = _runtime_lease(tmp_path)
    profile = _profile(lease)
    adapter = FakeAdapter(profile)
    port, orchestrator = _orchestrator(runtime, lease, adapter)
    session = orchestrator.start_attempt(
        attempt_id=lease.attempt.attempt_id,
        requested=profile,
        operation_id=_op("resume-dispatch-start"),
    )
    orchestrator.reconcile(session)
    operation = _op("resume-dispatch-restart")
    generation = port.begin_operator_resume(
        lease.attempt.attempt_id, session.epoch, operation
    )
    assert generation.generation_number == 2
    assert port.commit_operator_provider_dispatch(
        lease.attempt.attempt_id, operation, "resume_session"
    )
    resume_calls = adapter.calls.count("resume_session")

    _, restarted = _orchestrator(runtime, lease, adapter)
    with pytest.raises(OperatorEffectUnknown, match="dispatch"):
        restarted.resume(
            session,
            operation_id=operation,
            handoff=ProviderSessionHandoff("S1", "worker-01"),
        )

    assert adapter.calls.count("resume_session") == resume_calls
    assert (
        runtime.events.get_event_by_command_id(
            operation_receipt_command_id(operation, OperationReceiptKind.EFFECT_UNKNOWN)
        )
        is not None
    )
    with runtime.store.read() as connection:
        rows = connection.execute(
            """
            SELECT generation_number,pid,executive_writer_held
            FROM process_generations WHERE session_epoch_id=?
            ORDER BY generation_number
            """,
            (session.epoch.session_epoch_id,),
        ).fetchall()
    assert [tuple(row) for row in rows] == [(1, 100, 0), (2, None, 1)]


def test_resume_refuses_released_without_matching_allow_attestation(tmp_path) -> None:
    runtime, _, lease = _runtime_lease(tmp_path)
    profile = _profile(lease)
    port = ExecutiveOperatorHarnessPort(runtime, lease)
    port.seal_operator_attempt(lease.attempt.attempt_id, profile)
    epoch, generation = port.begin_operator_session(
        lease.attempt.attempt_id, _op("unsafe-start")
    )
    runtime.operator_harness.bind_start_result(
        epoch=epoch,
        generation=generation,
        operation_id=_op("unsafe-start"),
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="S1",
        process=ProcessIdentityObservation(100, 100, "start-100", "boot"),
    )
    runtime.operator_harness.record_reconcile_observation(
        generation=generation,
        observation=ReconcileObservation(
            process_liveness=ProcessLiveness.PROVEN_DEAD,
            observed_process=ProcessIdentityObservation(100, 100, "start-100", "boot"),
            provider_session_reachable=True,
            provider_writer_state=ProviderWriterState.RELEASED,
            observed_provider_session_id="S1",
        ),
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )

    with pytest.raises(StateConflict, match="derived recovery"):
        port.begin_operator_resume(
            lease.attempt.attempt_id, epoch, _op("unsafe-no-attestation")
        )
    with runtime.store.read() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM process_generations WHERE session_epoch_id=?",
            (epoch.session_epoch_id,),
        ).fetchone()[0]
    assert count == 1


def test_real_port_is_constructor_only_and_unregistered(tmp_path) -> None:
    runtime, _, lease = _runtime_lease(tmp_path)
    with runtime.store.read() as connection:
        before = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    ExecutiveOperatorHarnessPort(runtime, lease)
    with runtime.store.read() as connection:
        after = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert after == before

    root = Path(__file__).resolve().parents[1]
    for production_file in (
        root / "config/executive_worker_routes.json",
        root / "control_plane/executive_service.py",
        root / "control_plane/executive_supervisor.py",
        root / "control_plane/executive_worker_broker.py",
        root / "control_plane/flags.py",
    ):
        source = production_file.read_text(encoding="utf-8")
        assert "ExecutiveOperatorHarnessPort" not in source
        assert "executive_operator_harness_port" not in source
