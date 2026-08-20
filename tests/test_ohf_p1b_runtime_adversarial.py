"""Adversarial P1B runtime state-plane tests; no provider or adapter is used."""

from __future__ import annotations

import hashlib
import sqlite3

import pytest

from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.operator_harness_contract import (
    AuthRealmFact,
    AuthRealmRequirement,
    CapabilityManifest,
    NativeHelperPolicy,
    ObservedHarnessAttestation,
    ObservedTriState,
    OperationId,
    ProcessIdentityObservation,
    ProcessLiveness,
    ProviderWriterState,
    ReconcileObservation,
    RequestedExecutionProfile,
    WorkspaceIdentity,
)


def _runtime(tmp_path):
    runtime = Runtime.at(tmp_path)
    runtime.workers.register_worker(
        "worker-01", provider="codex", account_label="one", worker_type="test"
    )
    job = runtime.jobs.create_job("adversarial OHF test")
    lease = runtime.attempts.claim_job(job.job_id)
    assert lease is not None
    return runtime, lease


def _profile(lease):
    return RequestedExecutionProfile(
        worker_id=lease.attempt.worker_id,
        provider="codex",
        requested_model="m",
        harness_kind="fake",
        harness_binary_digest="a" * 64,
        harness_version="1",
        workspace=WorkspaceIdentity("/tmp/w", "b" * 40, 1, 2, 3, 4),
        sandbox_policy="read-only",
        approval_policy="never",
        network_policy="disabled",
        capabilities=CapabilityManifest(),
        native_helper_policy=NativeHelperPolicy.DISABLED,
        authority_policy_hash=lease.attempt.authority_policy_hash,
        auth_realm_requirement=AuthRealmRequirement.SLOT_BOUND_V1,
    )


def _allow(profile):
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


def _started(tmp_path, *, attest=True):
    runtime, lease = _runtime(tmp_path)
    profile = _profile(lease)
    harness = runtime.operator_harness
    sealed = harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        requested=profile,
    )
    epoch, generation = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        operation_id=OperationId("ohf-op:start-adversarial"),
    )
    harness.bind_start_result(
        epoch=epoch,
        generation=generation,
        operation_id=OperationId("ohf-op:start-adversarial"),
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="S1",
        process=ProcessIdentityObservation(101, 101, "start", "boot"),
    )
    if attest:
        harness.seal_attestation(
            generation=generation,
            fence_generation=sealed.fence_generation,
            lease_token=lease.lease_token,
            requested=profile,
            attestation=_allow(profile),
        )
    return runtime, lease, profile, epoch, generation


def test_tx5_blocks_pre_attestation_and_refused_launch(tmp_path):
    runtime, lease, profile, epoch, generation = _started(tmp_path, attest=False)
    with pytest.raises(StateConflict, match="ALLOW"):
        runtime.operator_harness.reserve_turn(
            epoch=epoch,
            generation=generation,
            operation_id=OperationId("ohf-op:pre-attestation"),
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        )
    refused = _allow(profile)
    refused = refused.__class__(**{**refused.__dict__, "served_model": "wrong"})
    runtime.operator_harness.seal_attestation(
        generation=generation,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        requested=profile,
        attestation=refused,
    )
    with pytest.raises(StateConflict, match="ALLOW"):
        runtime.operator_harness.reserve_turn(
            epoch=epoch,
            generation=generation,
            operation_id=OperationId("ohf-op:refused-turn"),
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        )


@pytest.mark.parametrize(
    "state", [ProviderWriterState.HELD, ProviderWriterState.UNKNOWN]
)
def test_tx6_never_releases_writer_without_provider_released(tmp_path, state):
    runtime, lease, _profile_value, _epoch, generation = _started(tmp_path)
    with pytest.raises(StateConflict, match="RELEASED"):
        runtime.operator_harness.record_graceful_stop(
            generation=generation,
            observation=ReconcileObservation(
                ProcessLiveness.PROVEN_DEAD,
                ProcessIdentityObservation(101, 101, "start", "boot"),
                True,
                state,
                "S1",
            ),
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        )
    runtime.operator_harness.record_hard_process_death(
        generation=generation,
        observation=ReconcileObservation(
            ProcessLiveness.PROVEN_DEAD,
            ProcessIdentityObservation(101, 101, "start", "boot"),
            True,
            state,
            "S1",
        ),
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    with runtime.store.read() as connection:
        assert (
            connection.execute(
                "SELECT executive_writer_held FROM process_generations WHERE process_generation_id=?",
                (generation.process_generation_id,),
            ).fetchone()[0]
            == 1
        )


def test_tx8_refuses_alive_then_abandons_dead_without_rewriting_provider_evidence(
    tmp_path,
):
    runtime, lease, _profile_value, epoch, generation = _started(tmp_path)
    with pytest.raises(StateConflict, match="PROVEN_DEAD"):
        runtime.operator_harness.abandon_epoch(
            epoch=epoch,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        )
    runtime.operator_harness.record_hard_process_death(
        generation=generation,
        observation=ReconcileObservation(
            ProcessLiveness.PROVEN_DEAD,
            ProcessIdentityObservation(101, 101, "start", "boot"),
            True,
            ProviderWriterState.UNKNOWN,
            "S1",
        ),
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    runtime.operator_harness.abandon_epoch(
        epoch=epoch,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    with runtime.store.read() as connection:
        assert tuple(
            connection.execute(
                "SELECT state,provider_session_id FROM harness_session_epochs WHERE session_epoch_id=?",
                (epoch.session_epoch_id,),
            ).fetchone()
        ) == ("ABANDONED", "S1")
        assert (
            connection.execute(
                "SELECT executive_writer_held FROM process_generations WHERE process_generation_id=?",
                (generation.process_generation_id,),
            ).fetchone()[0]
            == 0
        )


def test_sql_guards_partial_identity_projections_legacy_fields_and_mode_race(tmp_path):
    runtime, lease = _runtime(tmp_path)
    # The legacy winner selects SEALED_WORKER atomically; TX-1 cannot overwrite it.
    runtime.attempts.record_process(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="legacy",
    )
    with pytest.raises(StateConflict):
        runtime.operator_harness.seal_operator_harness_attempt(
            lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
            requested=_profile(lease),
        )
    with runtime.store.transaction() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE attempts SET execution_mode='OPERATOR_HARNESS' WHERE attempt_id=?",
                (lease.attempt.attempt_id,),
            )
    runtime2, lease2 = _runtime(tmp_path / "rich")
    profile = _profile(lease2)
    runtime2.operator_harness.seal_operator_harness_attempt(
        lease2.attempt.attempt_id,
        fence_generation=lease2.attempt.fence_generation,
        lease_token=lease2.lease_token,
        requested=profile,
    )
    epoch, _generation = runtime2.operator_harness.reserve_start(
        lease2.attempt.attempt_id,
        fence_generation=lease2.attempt.fence_generation,
        lease_token=lease2.lease_token,
        operation_id=OperationId("ohf-op:raw-attack"),
    )
    with runtime2.store.transaction() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO process_generations(
                    process_generation_id,session_epoch_id,worker_id,
                    generation_number,pid,pgid,process_start_identity,boot_id,
                    started_at_ms,executive_writer_held,provider_writer_state,
                    created_at_ms
                ) VALUES('partial',?,?,2,1,1,NULL,'boot',1,1,'UNKNOWN',1)
                """,
                (epoch.session_epoch_id, lease2.attempt.worker_id),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO harness_session_epochs(
                    session_epoch_id,attempt_id,worker_id,epoch_number,state,
                    created_at_ms
                ) VALUES('bad-worker',?,?,2,'TERMINAL',1)
                """,
                (lease2.attempt.attempt_id, "other"),
            )


def test_ohf_mode_requires_profile_and_tx1_receipt(tmp_path):
    runtime, lease = _runtime(tmp_path)
    with pytest.raises(StateConflict, match="database invariant"):
        with runtime.store.transaction() as connection:
            connection.execute(
                "UPDATE attempts SET execution_mode='OPERATOR_HARNESS' WHERE attempt_id=?",
                (lease.attempt.attempt_id,),
            )
    current = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    assert current is not None
    assert current.execution_mode is None
    assert current.requested_execution_profile is None

    raw_profile = "{}"
    raw_digest = hashlib.sha256(raw_profile.encode("utf-8")).hexdigest()
    with runtime.store.transaction() as connection:
        connection.execute(
            """
            UPDATE attempts
            SET execution_mode='OPERATOR_HARNESS',
                requested_execution_profile_json=?,
                requested_execution_profile_digest=?
            WHERE attempt_id=?
            """,
            (raw_profile, raw_digest, lease.attempt.attempt_id),
        )
    with pytest.raises(StateConflict, match="committed TX-1 profile seal"):
        runtime.operator_harness.reserve_start(
            lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
            operation_id=OperationId("ohf-op:no-tx1"),
        )
    with runtime.store.read() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM harness_session_epochs WHERE attempt_id=?",
                (lease.attempt.attempt_id,),
            ).fetchone()[0]
            == 0
        )
