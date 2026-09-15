"""SQLite integration coverage for the production-inert OHF P1B state plane."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import replace

import pytest

from control_plane.executive_runtime import (
    OrchestrationDispatchOutcome,
    Runtime,
    RuntimeStore,
    StateConflict,
    _json_dumps,
    _json_loads,
)
from control_plane.operator_harness_contract import (
    AuthRealmFact,
    AuthRealmRequirement,
    CapabilityManifest,
    CandidateResult,
    CheckpointObservation,
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
    TurnStartObservation,
    WorkspaceIdentity,
    operation_receipt_command_id,
)
from control_plane.ceo_intent import INTENT_SCHEMA_V2, submit_intent
from control_plane.executive_orchestration_principal import (
    OperatorPrincipalObservation,
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


def _started(tmp_path):
    runtime, lease = _lease(tmp_path)
    harness = runtime.operator_harness
    profile = _profile(lease)
    sealed = harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        requested=profile,
    )
    operation = OperationId("ohf-op:checkpoint-fixture-start")
    epoch, generation = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        operation_id=operation,
    )
    harness.bind_start_result(
        epoch=epoch,
        generation=generation,
        operation_id=operation,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="S1",
        process=ProcessIdentityObservation(101, 101, "start", "boot"),
    )
    return runtime, lease, epoch, generation


def _checkpoint(candidate):
    return CheckpointObservation(
        {"summary": "checkpoint", "current_state": candidate}
    )


def _commit(runtime, lease, generation, suffix, candidate="first"):
    harness = runtime.operator_harness
    operation = OperationId(f"ohf-op:{suffix}")
    harness.reserve_checkpoint_operation(
        generation=generation,
        operation_id=operation,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    return harness.apply_checkpoint_operation(
        generation=generation,
        operation_id=operation,
        observation=_checkpoint(candidate),
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )


def _raw_generation(generation, *, number=None, worker=None):
    return replace(
        generation,
        generation_number=generation.generation_number
        if number is None
        else number,
        worker_id=generation.worker_id if worker is None else worker,
    )


def test_cctx0_checkpoint_generation_ownership_is_exact(tmp_path):
    runtime, lease, _epoch, generation = _started(tmp_path)
    harness = runtime.operator_harness
    wrong_number = _raw_generation(generation, number=2)
    wrong_worker = _raw_generation(generation, worker="intruder")
    for bad in (wrong_number, wrong_worker):
        with pytest.raises(
            StateConflict,
            match=r"^OHF epoch/generation refs are not exactly owned by the lease$",
        ):
            harness.reserve_checkpoint_operation(
                generation=bad,
                operation_id=OperationId(
                    f"ohf-op:reserve-{bad.generation_number}-{bad.worker_id}"
                ),
                fence_generation=lease.attempt.fence_generation,
                lease_token=lease.lease_token,
            )
    for bad in (wrong_number, wrong_worker):
        operation = OperationId(
            f"ohf-op:apply-{bad.generation_number}-{bad.worker_id}"
        )
        with pytest.raises(
            StateConflict,
            match=r"^OHF epoch/generation refs are not exactly owned by the lease$",
        ):
            harness.apply_checkpoint_operation(
                generation=bad,
                operation_id=operation,
                observation=_checkpoint("bad"),
                fence_generation=lease.attempt.fence_generation,
                lease_token=lease.lease_token,
            )
    writer_operation = OperationId("ohf-op:checkpoint-writer-held")
    harness.reserve_checkpoint_operation(
        generation=generation,
        operation_id=writer_operation,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE process_generations SET executive_writer_held=0 WHERE process_generation_id=?",
            (generation.process_generation_id,),
        )
    for call in (
        lambda: harness.reserve_checkpoint_operation(
            generation=generation,
            operation_id=OperationId("ohf-op:checkpoint-writer-reserve"),
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        ),
        lambda: harness.apply_checkpoint_operation(
            generation=generation,
            operation_id=writer_operation,
            observation=_checkpoint("writer"),
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        ),
    ):
        with pytest.raises(StateConflict, match="OHF epoch/generation refs"):
            call()
    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE process_generations SET executive_writer_held=1 WHERE process_generation_id=?",
            (generation.process_generation_id,),
        )
    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE harness_session_epochs SET state='TERMINAL' WHERE session_epoch_id=?",
            (generation.session_epoch_id,),
        )
    for call in (
        lambda: harness.reserve_checkpoint_operation(
            generation=generation,
            operation_id=OperationId("ohf-op:cctx-terminal-reserve"),
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        ),
        lambda: harness.apply_checkpoint_operation(
            generation=generation,
            operation_id=writer_operation,
            observation=_checkpoint("terminal"),
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        ),
    ):
        with pytest.raises(StateConflict, match="OHF epoch/generation refs"):
            call()
    for fence, token in (
        (lease.attempt.fence_generation + 1, lease.lease_token),
        (lease.attempt.fence_generation, "wrong-token"),
    ):
        with pytest.raises(StateConflict):
            harness.reserve_checkpoint_operation(
                generation=generation,
                operation_id=OperationId(
                    f"ohf-op:fence-{fence}-{bool(token == 'wrong-token')}"
                ),
                fence_generation=fence,
                lease_token=token,
            )


def test_cctx0_checkpoint_sequence_is_monotonic_and_intents_are_stale_closed(tmp_path):
    runtime, lease, _epoch, generation = _started(tmp_path)
    harness = runtime.operator_harness
    first = _commit(runtime, lease, generation, "checkpoint-1", "candidate-1")
    assert first.checkpoint["current_state"] == "candidate-1"
    stale = OperationId("ohf-op:checkpoint-stale")
    harness.reserve_checkpoint_operation(
        generation=generation,
        operation_id=stale,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    second = _commit(runtime, lease, generation, "checkpoint-2", "candidate-2")
    assert second.checkpoint["current_state"] == "candidate-2"
    with pytest.raises(StateConflict, match="does not match INTENT"):
        harness.apply_checkpoint_operation(
            generation=generation,
            operation_id=stale,
            observation=_checkpoint("late"),
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        )
    attempt = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    assert attempt is not None
    assert attempt.checkpoint_sequence == 2
    with runtime.store.read() as connection:
        stored_attempt = connection.execute(
            "SELECT checkpoint_json FROM attempts WHERE attempt_id=?",
            (lease.attempt.attempt_id,),
        ).fetchone()
    assert stored_attempt is not None
    assert stored_attempt["checkpoint_json"] == _json_dumps(second.checkpoint)
    events = runtime.events.list_events(job_id=str(lease.attempt.job_id))
    payloads = [
        event.payload["checkpoint_sequence"]
        for event in events
        if event.event_type == "JOB_CHECKPOINTED"
    ]
    assert payloads == [1, 2]


def test_cctx0_checkpoint_operation_replay_is_idempotent(tmp_path):
    runtime, lease, _epoch, generation = _started(tmp_path)
    harness = runtime.operator_harness
    operation = OperationId("ohf-op:checkpoint-replay")
    harness.reserve_checkpoint_operation(
        generation=generation,
        operation_id=operation,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    observation = _checkpoint("replay")
    first = harness.apply_checkpoint_operation(
        generation=generation,
        operation_id=operation,
        observation=observation,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    second = harness.apply_checkpoint_operation(
        generation=generation,
        operation_id=operation,
        observation=observation,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    assert second == first
    with pytest.raises(StateConflict, match="checkpoint operation INTENT preconditions failed"):
        harness.reserve_checkpoint_operation(
            generation=generation,
            operation_id=operation,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        )
    with pytest.raises(StateConflict, match="does not match INTENT"):
        harness.apply_checkpoint_operation(
            generation=generation,
            operation_id=OperationId("ohf-op:checkpoint-no-intent"),
            observation=observation,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        )
    with runtime.store.read() as connection:
