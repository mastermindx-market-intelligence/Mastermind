"""Public Runtime two-Attempt continuation proof, with synthetic harness observations.

Requires the repaired #656 builder and #1289 PREPARE owner to be integrated.
This test creates only a private Runtime at pytest's tmp_path. It launches no
provider or worker process. The harness process/principal observations below are
explicit synthetic fixtures, processed by the real admission and lifecycle APIs.

No historical Attempt, epoch, generation, grant, lifecycle Event or continuation
receipt is inserted by test SQL. The test stops at PREPARE and asserts that no
continuation ACK was recorded. It does not prove native delivery or consumption.
"""
from __future__ import annotations

import os

import pytest

from control_plane.executive_operator_harness_port import ExecutiveOperatorHarnessPort
from control_plane.executive_orchestration_principal import OperatorPrincipalObservation
from control_plane.executive_runtime import AttemptLease, AttemptStatus, Runtime, StateConflict
from control_plane.operator_continuation_sources import (
    ContinuationExternalRefs,
    build_current_continuation_draft,
)
from control_plane.operator_harness_contract import (
    CheckpointObservation,
    OperationId,
    ProcessIdentityObservation,
    ProcessLiveness,
    ProviderWriterState,
    ReconcileObservation,
)
from test_runtime_binding_projection import _admitted_runtime, _attestation, _profile


RUNTIME_SOURCE_PIN = "9b7318baeb63399bd264bfb4fad2bd1617fff61c"


def _events(runtime, event_type):
    with runtime.store.read() as connection:
        return tuple(
            dict(row)
            for row in connection.execute(
                "SELECT * FROM events WHERE event_type=? ORDER BY event_id",
                (event_type,),
            )
        )


def _event_count(runtime):
    with runtime.store.read() as connection:
        return connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]


def _admit_successor(runtime, source):
    """Use real admission APIs with a second explicitly synthetic harness."""
    job = runtime.jobs.get_job(source.job_id)
    assert job is not None and job.current_attempt_id is None
    runtime.workers.register_worker(
        "worker-b",
        provider="openai-codex",
        account_label="account-b",
        worker_type="fixture",
        capabilities=["read"],
        quota_classes={
            "default": {
                "provider": "openai-codex",
                "capabilities": ["read"],
                "cost_class": "small",
            }
        },
    )
    dispatch = runtime.attempts.dispatch_cycle_job(
        job.job_id,
        command_id=f"coo-cycle:{job.root_job_id}:dispatch:{job.job_id}:attempt:2",
        worker_id="worker-b",
    )
    assert dispatch is not None and dispatch.lease_token is not None
    assert dispatch.attempt.attempt_number == source.attempt_number + 1

    profile = _profile(dispatch)
    harness = runtime.operator_harness
    sealed = harness.seal_operator_harness_attempt(
        dispatch.attempt.attempt_id,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=dispatch.lease_token,
        requested=profile,
    )
    operation = OperationId("ohf-op:continuation-successor-start")
    epoch, generation = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        operation_id=operation,
    )
    # These identities are synthetic input observations, never real host evidence.
    process = ProcessIdentityObservation(3002, 3002, "start-3002", "boot-fixture")
    session_id = "PROVIDER-SESSION-2"
    harness.bind_start_result(
        epoch=epoch,
        generation=generation,
        operation_id=operation,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        provider_session_id=session_id,
        process=process,
    )
    principal = OperatorPrincipalObservation(
        attempt_id=sealed.attempt_id,
        worker_id="worker-b",
        process_generation_id=generation.process_generation_id,
        provider_session_id=session_id,
        process_identity={
            "pid": process.pid,
            "pgid": process.pgid,
            "process_start_identity": process.process_start_identity,
            "boot_id": process.boot_id,
        },
        os_principal_name="fixture-principal",
        os_principal_uid=os.getuid(),
        provider_home_identity={
            "path": "/tmp/runtime-binding-projection-home-b",
            "device": 1,
            "inode": 3,
            "uid": os.getuid(),
            "gid": os.getgid(),
            "mode": 0o700,
        },
        observed_at_ms=runtime.store.now_ms(),
    )
    harness.seal_attestation(
        generation=generation,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        requested=profile,
        attestation=_attestation(profile),
        principal_observation=principal,
    )
    return dispatch


@pytest.mark.parametrize("released_predecessor", [True, False])
def test_public_interrupted_read_only_journey_prepares_only_after_positive_release(
    tmp_path, released_predecessor
):
    runtime, dispatch, sealed, _epoch, generation, process, _profile_value = (
        _admitted_runtime(tmp_path)
    )
    source_id = dispatch.attempt.attempt_id
    source_port = ExecutiveOperatorHarnessPort(
        runtime, AttemptLease(dispatch.attempt, dispatch.lease_token)
    )
    checkpoint = {
        "summary": "The first bounded source phase is recorded.",
        "completed_steps": ["Read the pinned source."],
        "current_state": "Independent review remains.",
        "artifacts": [],
        "next_actions": ["Review the next bounded change."],
        "errors": [],
    }
    checkpoint_operation = OperationId("ohf-op:continuation-source-checkpoint")
    source_port.begin_operator_checkpoint(
        source_id, generation, checkpoint_operation
    )
    source_port.apply_operator_checkpoint(
        source_id,
        generation,
        checkpoint_operation,
        CheckpointObservation(checkpoint, provider_mutated_state=False),
    )

    if released_predecessor:
        stop_operation = OperationId("ohf-op:continuation-source-stop")
        source_port.begin_operator_generation_operation(
            source_id, generation, stop_operation, "graceful_stop"
        )
        source_port.graceful_stop_operator_generation(
            source_id,
            generation,
            stop_operation,
            ReconcileObservation(
                ProcessLiveness.PROVEN_DEAD,
                process,
                False,
                ProviderWriterState.RELEASED,
                "PROVIDER-SESSION-1",
            ),
        )

    # Simulate reconstruction of the owner after interruption in this private DB.
    # TX-9 invalidation is a real owner operation; it is not positive process death.
    runtime = Runtime.at(tmp_path)
    assert runtime.operator_harness.invalidate_after_restore() == 1
    source = runtime.attempts.get_attempt(source_id)
    assert source is not None and source.status is AttemptStatus.LOST
    assert source.attempt_number == 1 and source.checkpoint_sequence == 1
    assert source.checkpoint == checkpoint

    job = runtime.jobs.get_job(source.job_id)
    assert job is not None
    expectation = runtime.jobs.project_retry_safety(
        job.job_id, expected_attempt_id=source_id
    )
    assert expectation.requeue_kind == "TX9_DETACHED"
    decision = runtime.jobs.commit_coo_retry_decision(
        job.root_job_id, selected_job_id=job.job_id, expectation=expectation
    )
    assert decision.action == "REQUEUED"
    assert len(_events(runtime, "OHF_RESTORE_INVALIDATED")) == 1
    assert len(_events(runtime, "JOB_REQUEUED")) == 1

    target_dispatch = _admit_successor(runtime, source)
    target = runtime.attempts.get_attempt(target_dispatch.attempt.attempt_id)
    assert target is not None and target.status is AttemptStatus.RUNNING
    assert target.job_id == source.job_id and target.attempt_id != source.attempt_id
    assert target.worker_id == "worker-b" and source.worker_id == "worker-a"
    assert runtime.jobs.get_job(job.job_id).attempt_count == 2
    assert runtime.jobs.get_job(job.job_id).current_attempt_id == target.attempt_id

    refs = ContinuationExternalRefs(
        operation_key="portable-continuity-public-lifecycle-fixture",
        target_seat="coo",
        session_alias="COO-CODEX",
        source_authority_refs=("docs/sol_skills/INDEX.md",),
        agentos_refs=("WS:EXECUTIVE-CAPACITY-FABRIC",),
        github_state={
            "repository": "mastermindx-market-intelligence/Mastermind",
            "head_sha": RUNTIME_SOURCE_PIN,
        },
        slack_dialogue_ref=None,
        accepted_ruling_refs=(),
        source_revisions={"mastermind": RUNTIME_SOURCE_PIN},
    )
    before_draft = _event_count(runtime)
    draft = build_current_continuation_draft(
        runtime,
        source_attempt_id=source.attempt_id,
        target_attempt_id=target.attempt_id,
        refs=refs,
    )
    assert _event_count(runtime) == before_draft
    assert draft.to_dict()["checkpoint"] == source.checkpoint
    assert draft.next_action == checkpoint["next_actions"][0]
    assert draft.prior_attempt_receipt["status"] == "LOST"
    target_port = ExecutiveOperatorHarnessPort(
        runtime, AttemptLease(target_dispatch.attempt, target_dispatch.lease_token)
    )

    if released_predecessor:
        first = target_port.prepare_operator_continuation(target.attempt_id, draft)
        replay = target_port.prepare_operator_continuation(target.attempt_id, draft)
        assert replay.canonical_bytes() == first.canonical_bytes()
        assert first.source_attempt_id == source.attempt_id
        assert first.target_attempt_id == target.attempt_id
        assert len(_events(runtime, "OPERATOR_CONTINUATION_PREPARED")) == 1
    else:
        with pytest.raises(StateConflict, match="predecessor process/writer"):
            target_port.prepare_operator_continuation(target.attempt_id, draft)
        assert not _events(runtime, "OPERATOR_CONTINUATION_PREPARED")

    # Neither this lifecycle proof nor a valid capsule is evidence of consumption.
    assert not _events(runtime, "OPERATOR_CONTINUATION_ACKNOWLEDGED")
