"""Contract tests for the storeless MAS-237 RuntimeBinding projection."""
from __future__ import annotations

import hashlib
import os

import pytest

from control_plane.ceo_intent import INTENT_SCHEMA_V2, submit_intent
from control_plane.executive_orchestration_principal import OperatorPrincipalObservation
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
from control_plane.runtime_binding_projection import (
    active_operator_binding_facts,
    project_runtime_binding,
)
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


def test_projects_exact_current_admitted_ohf_binding_without_a_write(tmp_path):
    runtime, dispatch, sealed, epoch, generation, _process, _profile_value = _admitted_runtime(tmp_path)
    with runtime.store.read() as connection:
        events_before = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    binding = project_runtime_binding(runtime, sealed.attempt_id, _target())

    assert binding.session_alias == "COO-CODEX"
    assert binding.binding_id == _expected_binding_id(sealed.attempt_id, epoch.session_epoch_id)
    assert binding.binding_generation == generation.generation_number
    assert binding.native_handle == "PROVIDER-SESSION-1"
    assert binding.account_label == "account-a"
    assert binding.reasoning_surface == "codex"
    with runtime.store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == events_before
    assert dispatch.attempt.attempt_id == sealed.attempt_id


def test_projection_is_deterministic_and_uses_one_supplied_snapshot_connection(tmp_path, monkeypatch):
    runtime, _dispatch, sealed, _epoch, _generation, _process, _profile_value = _admitted_runtime(tmp_path)
    with runtime.store.read() as connection:
        expected = active_operator_binding_facts(runtime, sealed.attempt_id, _target(), connection=connection)
        monkeypatch.setattr(
            runtime.store,
            "read",
            lambda: pytest.fail("provided connection must not open a second read"),
        )
        actual = active_operator_binding_facts(runtime, sealed.attempt_id, _target(), connection=connection)
    assert actual == expected
    assert actual.provider == "openai-codex"


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
        connection.execute("UPDATE workers SET provider='future-provider' WHERE worker_id='worker-a'")
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
