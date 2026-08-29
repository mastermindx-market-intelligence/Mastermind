"""Contract tests for the storeless MAS-237 RuntimeBinding projection."""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from control_plane.ceo_intent import INTENT_SCHEMA_V2, submit_intent
from control_plane.executive_orchestration_principal import OperatorPrincipalObservation
import control_plane.executive_runtime as executive_runtime
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
    TurnStartObservation,
    WorkspaceIdentity,
)
from control_plane.runtime_binding_projection import project_runtime_binding
from control_plane.session_targets import SessionTarget


def _target(*, seat: str = "coo", surface: str = "codex") -> SessionTarget:
    return SessionTarget(
        session_alias="COO-CODEX",
        target_seat=seat,
        reasoning_surface=surface,
        wake_transport="grok-computer",
        allowed_transports=("grok-computer",),
        workstream=None,
        target_enabled=False,
    )


def _intent() -> dict[str, object]:
    return {
        "schema": INTENT_SCHEMA_V2,
        "intent_id": "CEO-PROJECTION-001",
        "actor": "ceo-sol",
        "objective": "Exercise the inert RuntimeBinding projection.",
        "department": "executive-infrastructure",
        "priority": 9,
        "grounding": {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40},
        "execution_contract": {"requested_authorities": ["READ"], "attempt_limit": 2},
        "intent_kind": "executive_coo_cycle",
        "business_impact": "material",
    }


def _profile(dispatch) -> RequestedExecutionProfile:
    attempt = dispatch.attempt
    return RequestedExecutionProfile(
        worker_id=str(attempt.worker_id),
        provider="openai-codex",
        requested_model="fixture-model",
        harness_kind="fixture",
        harness_binary_digest="a" * 64,
        harness_version="1",
        workspace=WorkspaceIdentity(
            "/tmp/runtime-binding-projection", "b" * 40, 1, 2, os.getuid(), os.getgid()
        ),
        sandbox_policy="read-only",
        approval_policy="never",
        network_policy="disabled",
        capabilities=CapabilityManifest(),
        native_helper_policy=NativeHelperPolicy.DISABLED,
        authority_policy_hash=str(attempt.authority_policy_hash),
        auth_realm_requirement=AuthRealmRequirement.SLOT_BOUND_V1,
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
        effective_config_digest=None,
        auth=AuthRealmFact(worker_id=profile.worker_id, provider=profile.provider),
        workspace=profile.workspace,
        supports_subagent_capability_ceiling=ObservedTriState.UNKNOWN,
    )


def _admitted_runtime(tmp_path):
    runtime = Runtime.at(tmp_path)
    runtime.workers.register_worker(
        "worker-a",
        provider="openai-codex",
        account_label="account-a",
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
    receipt = submit_intent(runtime, _intent())
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    planner = runtime.jobs.create_cycle_planner(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0",
    )
    dispatch = runtime.attempts.dispatch_cycle_job(
        planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        worker_id="worker-a",
    )
    assert dispatch is not None and dispatch.lease_token is not None
    profile = _profile(dispatch)
    harness = runtime.operator_harness
    sealed = harness.seal_operator_harness_attempt(
        dispatch.attempt.attempt_id,
        fence_generation=dispatch.attempt.fence_generation,
        lease_token=dispatch.lease_token,
        requested=profile,
    )
    operation = OperationId("ohf-op:projection-start")
    epoch, generation = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        operation_id=operation,
    )
    process = ProcessIdentityObservation(3001, 3001, "start-3001", "boot-fixture")
    harness.bind_start_result(
        epoch=epoch,
        generation=generation,
        operation_id=operation,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        provider_session_id="PROVIDER-SESSION-1",
        process=process,
    )
    principal = OperatorPrincipalObservation(
        attempt_id=sealed.attempt_id,
        worker_id="worker-a",
        process_generation_id=generation.process_generation_id,
        provider_session_id="PROVIDER-SESSION-1",
        process_identity={
            "pid": process.pid,
            "pgid": process.pgid,
            "process_start_identity": process.process_start_identity,
            "boot_id": process.boot_id,
        },
        os_principal_name="fixture-principal",
        os_principal_uid=os.getuid(),
        provider_home_identity={
            "path": "/tmp/runtime-binding-projection-home",
            "device": 1,
            "inode": 2,
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
    return runtime, dispatch, sealed, epoch, generation, process, profile


def _expected_binding_id(attempt_id: str, epoch_id: str) -> str:
    return "bind-" + hashlib.sha256(f"{attempt_id}:{epoch_id}".encode("utf-8")).hexdigest()[:40]


def _sqlite_snapshot(runtime: Runtime):
    with runtime.store.read() as connection:
        tables = tuple(
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        )
        schema = tuple(
            tuple(row)
            for row in connection.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
            )
        )
        contents = tuple(
            (
                table,
                tuple(tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")),
            )
            for table in tables
        )
    return schema, contents


def test_projects_exact_current_admitted_ohf_binding_without_a_write(tmp_path):
    runtime, dispatch, sealed, epoch, generation, _process, _profile_value = _admitted_runtime(tmp_path)
    before = _sqlite_snapshot(runtime)

    binding = project_runtime_binding(runtime, sealed.attempt_id, _target())

    assert binding.session_alias == "COO-CODEX"
    assert binding.binding_id == _expected_binding_id(sealed.attempt_id, epoch.session_epoch_id)
    assert binding.binding_generation == generation.generation_number
    assert binding.native_handle == "PROVIDER-SESSION-1"
    assert binding.account_label == "account-a"
    assert binding.reasoning_surface == "codex"
    assert _sqlite_snapshot(runtime) == before
    assert dispatch.attempt.attempt_id == sealed.attempt_id


def test_public_projection_uses_one_supplied_snapshot_connection(tmp_path, monkeypatch):
    runtime, _dispatch, sealed, _epoch, _generation, _process, _profile_value = _admitted_runtime(tmp_path)
    with runtime.store.read() as connection:
        expected = project_runtime_binding(
            runtime, sealed.attempt_id, _target(), connection=connection
        )
        monkeypatch.setattr(
            runtime.store,
            "read",
            lambda: pytest.fail("provided connection must not open a second read"),
        )
        actual = project_runtime_binding(
            runtime, sealed.attempt_id, _target(), connection=connection
        )
    assert actual == expected


def test_public_projection_keeps_one_snapshot_when_generation_changes_after_read(tmp_path):
    runtime, _dispatch, sealed, _epoch, generation, _process, _profile_value = _admitted_runtime(tmp_path)
    with runtime.store.read() as connection:
        before = project_runtime_binding(runtime, sealed.attempt_id, _target(), connection=connection)
        with runtime.store.transaction() as writer:
            # Test-only corruption: a normal runtime transition cannot alter a
            # generation number in place, but the projection seam must still
            # retain the supplied reader's snapshot when another connection
            # commits a newer state.
            writer.execute("DROP TRIGGER process_generation_projection_update")
            writer.execute(
                "UPDATE process_generations SET generation_number=2 WHERE process_generation_id=?",
                (generation.process_generation_id,),
            )
        still_before = project_runtime_binding(
            runtime, sealed.attempt_id, _target(), connection=connection
        )
    after = project_runtime_binding(runtime, sealed.attempt_id, _target())
    assert before.binding_generation == still_before.binding_generation == 1
    assert after.binding_generation == 2


def test_same_epoch_generation_replacement_keeps_id_and_advances_generation(tmp_path):
    runtime, dispatch, sealed, epoch, g1, process, profile = _admitted_runtime(tmp_path)
    before = project_runtime_binding(runtime, sealed.attempt_id, _target())
    harness = runtime.operator_harness
    turn_operation = OperationId("ohf-op:projection-g1-turn")
    turn = harness.reserve_turn(
        epoch=epoch,
        generation=g1,
        operation_id=turn_operation,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    harness.acknowledge_turn(
        turn=turn,
        operation_id=turn_operation,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        observation=TurnStartObservation("NATIVE-PROJECTION-G1", True),
    )
    harness.record_reconcile_observation(
        generation=g1,
        observation=ReconcileObservation(
            ProcessLiveness.PROVEN_DEAD,
            process,
            True,
            ProviderWriterState.RELEASED,
            "PROVIDER-SESSION-1",
        ),
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    resume = OperationId("ohf-op:projection-resume")
    g2 = harness.reserve_same_epoch_resume(
        epoch=epoch,
        old_generation=g1,
        operation_id=resume,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    process2 = ProcessIdentityObservation(3002, 3002, "start-3002", "boot-fixture")
    harness.bind_resume_result(
        epoch=epoch,
        generation=g2,
        operation_id=resume,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        provider_session_id="PROVIDER-SESSION-1",
        process=process2,
    )
    principal = runtime.operator_harness.admitted_principal_observation(g1)
    assert principal is not None
    harness.seal_attestation(
        generation=g2,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        requested=profile,
        attestation=_attestation(profile),
        principal_observation=OperatorPrincipalObservation.from_dict(
            {
                **principal.to_dict(),
                "process_generation_id": g2.process_generation_id,
                "process_identity": {
                    "pid": process2.pid,
                    "pgid": process2.pgid,
                    "process_start_identity": process2.process_start_identity,
                    "boot_id": process2.boot_id,
                },
            }
        ),
    )
    after = project_runtime_binding(runtime, sealed.attempt_id, _target())
    assert after.binding_id == before.binding_id
    assert after.binding_generation == g2.generation_number == 2


def test_new_attempt_and_epoch_identity_change_binding_id(tmp_path):
    first = _admitted_runtime(tmp_path / "first")
    second = _admitted_runtime(tmp_path / "second")
    first_binding = project_runtime_binding(first[0], first[2].attempt_id, _target())
    second_binding = project_runtime_binding(second[0], second[2].attempt_id, _target())
    assert first_binding.binding_id != second_binding.binding_id


def test_orchestration_attempt_refuses_a_second_epoch_after_abandonment(tmp_path):
    runtime, dispatch, sealed, first_epoch, first_generation, first_process, _profile_value = _admitted_runtime(tmp_path)
    harness = runtime.operator_harness
    harness.record_hard_process_death(
        generation=first_generation,
        observation=ReconcileObservation(
            ProcessLiveness.PROVEN_DEAD,
            first_process,
            True,
            ProviderWriterState.UNKNOWN,
            "PROVIDER-SESSION-1",
        ),
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    harness.abandon_epoch(
        epoch=first_epoch,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    # The existing OHF law permits only one epoch for an orchestration Attempt,
    # so no production-valid same-Attempt new epoch fixture can be constructed.
    # This refusal is the boundary that prevents a fabricated identity case.
    with pytest.raises(StateConflict, match="only one session epoch per Attempt"):
        harness.reserve_start(
            sealed.attempt_id,
            fence_generation=sealed.fence_generation,
            lease_token=dispatch.lease_token,
            operation_id=OperationId("ohf-op:projection-new-epoch"),
        )


@pytest.mark.parametrize(
    "target",
    [_target(seat="ceo"), _target(surface="chatgpt-sol")],
    ids=["owner-seat-mismatch", "logical-surface-mismatch"],
)
def test_projection_refuses_target_that_does_not_match_current_binding(tmp_path, target):
    runtime, _dispatch, sealed, _epoch, _generation, _process, _profile_value = _admitted_runtime(tmp_path)
    with pytest.raises(StateConflict):
        project_runtime_binding(runtime, sealed.attempt_id, target)


def test_projection_refuses_missing_writer_session_or_current_epoch(tmp_path):
    runtime, _dispatch, sealed, epoch, generation, _process, _profile_value = _admitted_runtime(tmp_path)
    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE process_generations SET executive_writer_held=0 WHERE process_generation_id=?",
            (generation.process_generation_id,),
        )
    with pytest.raises(StateConflict):
        project_runtime_binding(runtime, sealed.attempt_id, _target())

    runtime, _dispatch, sealed, epoch, generation, _process, _profile_value = _admitted_runtime(tmp_path / "stale")
    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE harness_session_epochs SET state='TERMINAL' WHERE session_epoch_id=?",
            (epoch.session_epoch_id,),
        )
    with pytest.raises(StateConflict):
        project_runtime_binding(runtime, sealed.attempt_id, _target())


def test_projection_refuses_provider_session_drift_and_unknown_provider(tmp_path):
    runtime, _dispatch, sealed, _epoch, generation, _process, _profile_value = _admitted_runtime(tmp_path)
    with runtime.store.transaction() as connection:
        connection.execute("DROP TRIGGER process_generation_projection_update")
        connection.execute(
            "UPDATE process_generations SET provider_session_id='DRIFTED-SESSION' WHERE process_generation_id=?",
            (generation.process_generation_id,),
        )
    with pytest.raises(StateConflict):
        project_runtime_binding(runtime, sealed.attempt_id, _target())

    runtime, _dispatch, sealed, _epoch, _generation, _process, _profile_value = _admitted_runtime(tmp_path / "unknown")
    with runtime.store.transaction() as connection:
        connection.execute("DROP TRIGGER workers_identity_immutable")
        connection.execute("UPDATE workers SET provider='openai' WHERE worker_id='worker-a'")
    with pytest.raises(StateConflict):
        project_runtime_binding(runtime, sealed.attempt_id, _target())


def test_projection_refuses_non_ohf_attempt_and_wrong_source_admission(tmp_path):
    runtime = Runtime.at(tmp_path)
    runtime.workers.register_worker(
        "worker-a", provider="openai-codex", account_label="account-a", worker_type="fixture"
    )
    job = runtime.jobs.create_job("legacy attempt")
    lease = runtime.attempts.claim_job(job.job_id)
    assert lease is not None
    with pytest.raises(StateConflict):
        project_runtime_binding(runtime, lease.attempt.attempt_id, _target())

    runtime, _dispatch, sealed, _epoch, generation, _process, _profile_value = _admitted_runtime(tmp_path / "wrong-source")
    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE process_generations SET observed_attestation_digest=NULL WHERE process_generation_id=?",
            (generation.process_generation_id,),
        )
    with pytest.raises(StateConflict):
        project_runtime_binding(runtime, sealed.attempt_id, _target())


@pytest.mark.parametrize(
    "kind",
    ["expired", "null-token", "claimed", "job-state", "released", "wrong-holder", "fence"],
)
def test_projection_refuses_incoherent_current_lease_and_quota(tmp_path, kind):
    runtime, _dispatch, sealed, _epoch, _generation, _process, _profile_value = _admitted_runtime(tmp_path)
    if kind == "wrong-holder":
        connection = runtime.store._open()
        try:
            connection.execute("PRAGMA foreign_keys=OFF")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE worker_quota_classes SET held_attempt_id='ATT-WRONG' "
                "WHERE worker_id='worker-a' AND quota_class='default'"
            )
            connection.commit()
        finally:
            connection.close()
        with pytest.raises(StateConflict):
            project_runtime_binding(runtime, sealed.attempt_id, _target())
        return
    with runtime.store.transaction() as connection:
        if kind == "expired":
            connection.execute(
                "UPDATE attempts SET lease_expires_at_ms=0 WHERE attempt_id=?",
                (sealed.attempt_id,),
            )
        elif kind == "null-token":
            connection.execute("PRAGMA ignore_check_constraints=ON")
            connection.execute(
                "UPDATE attempts SET lease_token=NULL WHERE attempt_id=?",
                (sealed.attempt_id,),
            )
        elif kind == "claimed":
            connection.execute(
                "UPDATE attempts SET status='CLAIMED' WHERE attempt_id=?",
                (sealed.attempt_id,),
            )
        elif kind == "job-state":
            connection.execute(
                "UPDATE jobs SET status='CHECKPOINTED' WHERE current_attempt_id=?",
                (sealed.attempt_id,),
            )
        elif kind == "released":
            connection.execute(
                "UPDATE worker_quota_classes SET status='DRAINING',held_attempt_id=NULL "
                "WHERE worker_id='worker-a' AND quota_class='default'"
            )
        elif kind == "fence":
            connection.execute(
                "UPDATE worker_quota_classes SET fence_counter=fence_counter+1 "
                "WHERE worker_id='worker-a' AND quota_class='default'"
            )
    with pytest.raises(StateConflict):
        project_runtime_binding(runtime, sealed.attempt_id, _target())


def test_projection_refuses_current_job_pointer_drift(tmp_path):
    runtime, _dispatch, sealed, _epoch, _generation, _process, _profile_value = _admitted_runtime(tmp_path)
    connection = runtime.store._open()
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "UPDATE jobs SET current_attempt_id='ATT-WRONG' WHERE current_attempt_id=?",
            (sealed.attempt_id,),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(StateConflict):
        project_runtime_binding(runtime, sealed.attempt_id, _target())


@pytest.mark.parametrize("event_type", ["ORCHESTRATION_WORK_ADMITTED", "OHF_LAUNCH_DECISION"])
def test_projection_refuses_duplicate_current_admission_or_decision(tmp_path, event_type):
    runtime, _dispatch, sealed, _epoch, generation, _process, _profile_value = _admitted_runtime(tmp_path)
    with runtime.store.transaction() as connection:
        if event_type == "ORCHESTRATION_WORK_ADMITTED":
            connection.execute("DROP INDEX events_one_work_admission_per_generation")
        row = connection.execute(
            "SELECT * FROM events WHERE aggregate_type='process_generation' "
            "AND aggregate_id=? AND event_type=?",
            (generation.process_generation_id, event_type),
        ).fetchone()
        assert row is not None
        runtime.store.append_event(
            connection,
            aggregate_type=str(row["aggregate_type"]),
            aggregate_id=str(row["aggregate_id"]),
            event_type=event_type,
            command_id=f"projection-duplicate:{event_type}:{generation.process_generation_id}",
            actor=str(row["actor"]),
            job_id=str(row["job_id"]),
            attempt_id=str(row["attempt_id"]),
            worker_id=str(row["worker_id"]),
            quota_class=str(row["quota_class"]),
            payload=json.loads(str(row["payload_json"])),
            timestamp_ms=int(row["created_at_ms"]),
        )
    with pytest.raises(StateConflict):
        project_runtime_binding(runtime, sealed.attempt_id, _target())


def test_projection_refuses_stale_writer_with_newer_writerless_generation(tmp_path):
    runtime, _dispatch, sealed, epoch, generation, _process, _profile_value = _admitted_runtime(tmp_path)
    with runtime.store.transaction() as connection:
        connection.execute(
            """INSERT INTO process_generations(
                 process_generation_id,session_epoch_id,worker_id,provider_session_id,
                 generation_number,started_at_ms,executive_writer_held,
                 provider_writer_state,created_at_ms
               ) VALUES(?,?,?,?,2,1,0,'UNKNOWN',1)""",
            (
                "projection-writerless-g2",
                epoch.session_epoch_id,
                "worker-a",
                "PROVIDER-SESSION-1",
            ),
        )
    with pytest.raises(StateConflict):
        project_runtime_binding(runtime, sealed.attempt_id, _target())


def test_projection_does_not_read_live_policy_and_refuses_corrupt_persisted_digest(tmp_path, monkeypatch):
    runtime, _dispatch, sealed, _epoch, _generation, _process, _profile_value = _admitted_runtime(tmp_path)
    monkeypatch.setattr(
        executive_runtime.CooCyclePolicy,
        "load",
        lambda: pytest.fail("projection must not load mutable CooCyclePolicy"),
    )
    assert project_runtime_binding(runtime, sealed.attempt_id, _target()).reasoning_surface == "codex"

    monkeypatch.undo()
    with runtime.store.transaction() as connection:
        connection.execute("DROP TRIGGER events_are_immutable_update")
        event = connection.execute(
            "SELECT event_id,payload_json FROM events WHERE event_type='ORCHESTRATION_WORK_ADMITTED' "
            "AND attempt_id=?",
            (sealed.attempt_id,),
        ).fetchone()
        assert event is not None
        payload = json.loads(str(event["payload_json"]))
        payload["policy_sha"] = "not-a-digest"
        connection.execute(
            "UPDATE events SET payload_json=? WHERE event_id=?",
            (json.dumps(payload, sort_keys=True, separators=(",", ":")), event["event_id"]),
        )
    with pytest.raises(StateConflict):
        project_runtime_binding(runtime, sealed.attempt_id, _target())
