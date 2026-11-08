"""Real Runtime transactions using the unpatched canonical native policy.

Physical installation, account, process and provider observations remain inert.
The separate candidate stays disabled; this fixture does not prove installation.
"""
from dataclasses import replace
from types import SimpleNamespace
import hashlib
import os

import pytest

from control_plane import executive_runtime as rt
from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from control_plane.executive_orchestration_principal import OperatorPrincipalObservation
from control_plane.native_conversation_result import NativeConversationResultObservation
from control_plane.operator_harness_contract import (
    AuthRealmRequirement, CandidateResult, EventCursor, NativeHelperPolicy, NormalizedEvent,
    OperationId, ProcessIdentityObservation, RequestedExecutionProfile, TurnStartObservation,
    WorkspaceIdentity,
)
from integrations.deepseek_harness.native_protocol import NativeClaim, NativeResult, NativeTerminal
from test_dsh_native_runtime_binding import _root, PROFILE
from test_interactive_tx5_runtime import _attestation


def _started_native(tmp_path, monkeypatch, *, claim_only=False, capacity_join=None, worktree=None, unclaimed=False):
    registry = ExecutionCapabilityRegistry.load()
    declared = registry.resolve(PROFILE)
    manifest = declared.capability_manifest(harness_binary_digest="c"*64)
    runtime, root = _root(tmp_path, native_registry=registry, worktree=worktree)
    job = runtime.jobs.create_interactive_operator(root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-interactive:0")
    constraints = job.constraints
    metadata = {key: constraints[key] for key in (
        "routing_policy_version", "execution_profile_id", "execution_profile_digest",
        "capability_policy_version", "capability_policy_digest", "harness_binary_digest", "harness_version")}
    if capacity_join is not None:
        metadata["capacity_join"] = capacity_join
    runtime.workers.register_worker("native-fixture", provider="acp", account_label="fixture-only",
        worker_type="fixture", capabilities=["read"],
        quota_classes={"dsh-native": dict(provider="acp", model=constraints["model"], effort="default",
            cost_class="small", capabilities=["read"], metadata=metadata)})
    if unclaimed:
        return SimpleNamespace(runtime=runtime, root=root, job=job)
    dispatch = runtime.attempts.dispatch_cycle_job(job.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{job.job_id}:attempt:1", worker_id="native-fixture")
    lease = dict(fence_generation=dispatch.attempt.fence_generation, lease_token=dispatch.lease_token)
    requested = RequestedExecutionProfile(
        worker_id="native-fixture", provider="acp", requested_model=constraints["model"],
        harness_kind="dsh-native-web-acp", harness_binary_digest="c"*64, harness_version="native-test-only",
        workspace=WorkspaceIdentity(str(worktree) if worktree is not None else "/tmp/dsh-native-runtime-fixture",
                                    "a"*40, 1, 2, os.getuid(), os.getgid()),
        sandbox_policy="read-only", approval_policy="never", network_policy="disabled",
        capabilities=manifest, native_helper_policy=NativeHelperPolicy.DISABLED,
        authority_policy_hash=dispatch.attempt.authority_policy_hash,
        auth_realm_requirement=AuthRealmRequirement.SLOT_BOUND_V1,
        expected_config_digest=declared.expected_config_digest,
    )
    if claim_only:
        return SimpleNamespace(runtime=runtime, root=root, job=job, dispatch=dispatch, lease=lease,
                               requested=requested)
    harness = runtime.operator_harness
    harness.seal_operator_harness_attempt(dispatch.attempt.attempt_id, requested=requested, **lease)
    start = OperationId("ohf-op:native-runtime-start")
    epoch, generation = harness.reserve_start(dispatch.attempt.attempt_id, operation_id=start, **lease)
    process = ProcessIdentityObservation(2101, 2101, "native-runtime-test", "fixture-boot")
    session_id = "native-runtime-session"
    harness.bind_start_result(epoch=epoch, generation=generation, operation_id=start,
        provider_session_id=session_id, process=process, **lease)
    principal = OperatorPrincipalObservation(
        attempt_id=dispatch.attempt.attempt_id, worker_id="native-fixture",
        process_generation_id=generation.process_generation_id, provider_session_id=session_id,
        process_identity=dict(pid=process.pid, pgid=process.pgid,
            process_start_identity=process.process_start_identity, boot_id=process.boot_id),
        os_principal_name="native-test-only", os_principal_uid=9301,
        provider_home_identity=dict(path="/tmp/dsh-native-fixture-home", device=1, inode=2,
                                   uid=9301, gid=9301, mode=0o700),
        observed_at_ms=runtime.store.now_ms())
    observed = replace(_attestation(requested), effective_plugins_or_apps=("mastermind-company",))
    harness.seal_attestation(generation=generation, requested=requested, attestation=observed,
                            principal_observation=principal, **lease)
    return SimpleNamespace(runtime=runtime, root=root, job=job, dispatch=dispatch, lease=lease,
        requested=requested, epoch=epoch, generation=generation, session_id=session_id)


def _turn(f, ordinal=1, *, candidate=True, claim_changes=None):
    operation = OperationId(f"ohf-op:native-runtime-turn:{ordinal}")
    harness = f.runtime.operator_harness
    turn = harness.reserve_turn(epoch=f.epoch, generation=f.generation, operation_id=operation, **f.lease)
    claim = NativeClaim(operation.command_id, ordinal, f.session_id, f"message-{ordinal}", ordinal, ordinal*10)
    if claim_changes:
        claim = replace(claim, **claim_changes)
    harness.acknowledge_turn(turn=turn, operation_id=operation,
                            observation=TurnStartObservation(str(claim.native_turn), True), **f.lease)
    result = NativeResult("end_turn", NativeTerminal(operation.command_id, ordinal, claim,
        claim.through_seq+5, claim.native_turn+1, 2))
    observation = NativeConversationResultObservation.from_native(turn, f.session_id, result)
    if candidate:
        harness.record_candidate_evidence(turn=turn,
            candidate=CandidateResult(turn.attempt_id, turn.session_epoch_id, turn.process_generation_id,
                                      result.artifact_digest, "native fixture evidence"),
            events=(NormalizedEvent(turn.attempt_id, turn.session_epoch_id, turn.process_generation_id,
                                    turn.turn_id, "turn.completed", payload_redacted={"native_turn_count": 2}),),
            cursor=EventCursor(turn.attempt_id, turn.session_epoch_id, turn.process_generation_id,
                               local_sequence=ordinal, turn_id=turn.turn_id), **f.lease)
    return turn, observation


def test_native_turn_seal_replay_and_history_leave_original_writer_active(tmp_path, monkeypatch):
    f = _started_native(tmp_path, monkeypatch)
    harness = f.runtime.operator_harness
    turn, observation = _turn(f)
    ref = harness.seal_native_conversation_result(turn=turn, observation=observation, **f.lease)
    assert harness.seal_native_conversation_result(turn=turn, observation=observation, **f.lease) == ref
    payload = harness.native_conversation_result(attempt_id=turn.attempt_id, reference=ref)
    assert payload["observation"] == observation.to_wire()
    second, next_observation = _turn(f, 2)
    second_ref = harness.seal_native_conversation_result(turn=second, observation=next_observation, **f.lease)
    assert second_ref != ref
    assert harness.native_conversation_result(attempt_id=turn.attempt_id, reference=ref) == payload
    assert harness.current_writer_generation(f.epoch) == f.generation
    assert f.runtime.jobs.get_job(f.job.job_id).status is rt.JobStatus.RUNNING
    assert f.runtime.attempts.get_attempt(turn.attempt_id).status is rt.AttemptStatus.RUNNING
    with f.runtime.store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM events WHERE event_type='OHF_NATIVE_CONVERSATION_RESULT_SEALED'").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM events WHERE event_type='ORCHESTRATION_ROLE_RESULT_SEALED'").fetchone()[0] == 0
    with pytest.raises(rt.StateConflict):
        f.runtime.jobs.admit_cycle_plan(f.root.job_id,
            command_id=f"coo-cycle:{f.root.job_id}:admit-plan:{turn.attempt_id}")


@pytest.mark.parametrize("change", ["session", "operation", "first_turn", "digest", "foreign_turn", "missing_candidate"])
def test_native_result_must_join_original_candidate_and_acknowledged_turn(tmp_path, monkeypatch, change):
    f = _started_native(tmp_path, monkeypatch)
    turn, observation = _turn(f, candidate=change != "missing_candidate")
    if change != "missing_candidate":
        claim = observation.native_claim
        if change == "session":
            claim = replace(claim, session_id="foreign-session")
        elif change == "operation":
            claim = replace(claim, operation_id="ohf-op:foreign")
        elif change == "first_turn":
            claim = replace(claim, native_turn=0)
        terminal = replace(observation.native_terminal, claim=claim,
                           operation_id=claim.operation_id)
        result = NativeResult("refusal" if change == "digest" else "end_turn", terminal)
        observation = NativeConversationResultObservation.from_native(turn, claim.session_id, result)
        if change == "foreign_turn":
            observation = replace(observation, turn_id="foreign-turn")
    with pytest.raises((rt.StateConflict, ValueError)):
        f.runtime.operator_harness.seal_native_conversation_result(turn=turn, observation=observation, **f.lease)
    with f.runtime.store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM events WHERE event_type='OHF_NATIVE_CONVERSATION_RESULT_SEALED'").fetchone()[0] == 0


def test_native_result_replay_drift_and_foreign_reference_refuse(tmp_path, monkeypatch):
    f = _started_native(tmp_path, monkeypatch)
    turn, observation = _turn(f)
    harness = f.runtime.operator_harness
    ref = harness.seal_native_conversation_result(turn=turn, observation=observation, **f.lease)
    changed = NativeConversationResultObservation.from_native(turn, f.session_id,
        NativeResult("cancelled", observation.native_terminal))
    with pytest.raises(rt.StateConflict):
        harness.seal_native_conversation_result(turn=turn, observation=changed, **f.lease)
    for wrong in (replace(ref, event_id=ref.event_id+1), replace(ref, seal_digest="f"*64),
                  replace(ref, observation_digest="e"*64)):
        with pytest.raises(rt.StateConflict):
            harness.native_conversation_result(attempt_id=turn.attempt_id, reference=wrong)
    with pytest.raises(rt.StateConflict):
        harness.native_conversation_result(attempt_id="foreign-attempt", reference=ref)


def test_native_seal_requires_current_lease_but_historical_reference_does_not(tmp_path, monkeypatch):
    f = _started_native(tmp_path, monkeypatch)
    turn, observation = _turn(f)
    harness = f.runtime.operator_harness
    ref = harness.seal_native_conversation_result(turn=turn, observation=observation, **f.lease)
    with f.runtime.store.transaction() as connection:
        connection.execute("UPDATE attempts SET lease_expires_at_ms=? WHERE attempt_id=?",
                           (f.runtime.store.now_ms()-1, turn.attempt_id))
    with pytest.raises(rt.StateConflict):
        harness.seal_native_conversation_result(turn=turn, observation=observation, **f.lease)
    assert harness.native_conversation_result(attempt_id=turn.attempt_id, reference=ref)["turn"]["turn_id"] == turn.turn_id


class _NativeTurnAdapter:
    result_contract = "mastermind.dsh_native_conversation/v1"

    def __init__(self, f):
        self.f = f
        self.calls = 0

    def begin_turn(self, *, operation_id, turn, generation, launch):
        self.calls += 1
        assert generation == self.f.generation
        self.turn = turn
        claim = NativeClaim(operation_id.command_id, self.calls, self.f.session_id,
                            f"orchestrated-message-{self.calls}", self.calls, self.calls*10)
        self.result = NativeResult("end_turn", NativeTerminal(operation_id.command_id, self.calls,
                                  claim, claim.through_seq+5, claim.native_turn, 1))
        return TurnStartObservation(str(claim.native_turn), True)

    def read_events(self, cursor, *, timeout_seconds):
        turn = self.turn
        return ((NormalizedEvent(turn.attempt_id, turn.session_epoch_id, turn.process_generation_id,
                                 turn.turn_id, "turn.completed", payload_redacted={"native_turn_count": 1}),),
                replace(cursor, local_sequence=self.calls))

    def collect_candidate_result(self, turn):
        assert turn == self.turn
        return CandidateResult(turn.attempt_id, turn.session_epoch_id, turn.process_generation_id,
                               self.result.artifact_digest, "fixture native result")

    def observe_native_conversation_result(self, turn):
        return NativeConversationResultObservation.from_native(turn, self.f.session_id, self.result)


def _orchestrator(f):
    from control_plane.executive_operator_harness_port import ExecutiveOperatorHarnessPort
    from control_plane.operator_harness_orchestrator import OperatorHarnessOrchestrator, OperatorSessionReceipt
    from control_plane.operator_harness_contract import SessionStartObservation, compare_launch
    port = ExecutiveOperatorHarnessPort(f.runtime,
        rt.AttemptLease(attempt=f.dispatch.attempt, lease_token=f.dispatch.lease_token))
    adapter = _NativeTurnAdapter(f)
    observed = replace(_attestation(f.requested), effective_plugins_or_apps=("mastermind-company",))
    orchestrator = OperatorHarnessOrchestrator(port, adapter, attestation_reader=lambda _g: observed)
    session = OperatorSessionReceipt(f.epoch.attempt_id, f.epoch, f.generation,
        SessionStartObservation(f.session_id, ProcessIdentityObservation(2101, 2101,
                                 "native-runtime-test", "fixture-boot")),
        observed, compare_launch(f.requested, observed))
    return orchestrator, port, adapter, session


def test_original_port_and_orchestrator_seal_each_native_turn(tmp_path, monkeypatch):
    f = _started_native(tmp_path, monkeypatch)
    orchestrator, port, adapter, session = _orchestrator(f)
    def forbidden_plan_reader(*_args):
        raise AssertionError("native turn must never consume historical planner output")
    monkeypatch.setattr(port, "existing_interactive_plan_seal", forbidden_plan_reader)
    receipts = [orchestrator.run_turn(session, operation_id=OperationId(f"ohf-op:native-orchestrated:{n}"))
                for n in (1, 2)]
    assert adapter.calls == 2
    assert receipts[0].native_result != receipts[1].native_result
    for receipt in receipts:
        payload = f.runtime.operator_harness.native_conversation_result(
            attempt_id=f.epoch.attempt_id, reference=receipt.native_result)
        assert payload["turn"]["turn_id"] == receipt.turn.turn_id
        assert payload["observation"]["provider_native_turn_id"] == receipt.start.provider_native_turn_id
    assert f.runtime.operator_harness.current_writer_generation(f.epoch) == f.generation


@pytest.mark.parametrize("bad", ["wrong_contract", "missing_consumer", "role_callback"])
def test_native_consumer_refuses_before_provider_dispatch(tmp_path, monkeypatch, bad):
    from control_plane.operator_harness_orchestrator import OperatorHarnessOrchestrationError
    from control_plane.native_conversation_result import ROLE_RESULT_CONTRACT
    f = _started_native(tmp_path, monkeypatch)
    orchestrator, port, adapter, session = _orchestrator(f)
    kwargs = {}
    if bad == "wrong_contract":
        monkeypatch.setattr(port, "operator_result_contract", lambda _attempt: ROLE_RESULT_CONTRACT)
    elif bad == "missing_consumer":
        monkeypatch.setattr(port, "seal_operator_native_result", None)
    else:
        kwargs["_before_role_seal"] = lambda *_: None
    with pytest.raises(OperatorHarnessOrchestrationError):
        orchestrator.run_turn(session, operation_id=OperationId("ohf-op:native-refused"), **kwargs)
    assert adapter.calls == 0
    with f.runtime.store.read() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM events WHERE command_id='ohf-op:native-refused'").fetchone()[0] == 0


def _corrupt_fixture(runtime, table, sql, params):
    """Negative-control corruption; restore exact triggers before committing."""
    with runtime.store.transaction() as connection:
        triggers = connection.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name=?", (table,)).fetchall()
        for trigger in triggers:
            connection.execute('DROP TRIGGER "' + trigger["name"].replace('"', '""') + '"')
        connection.execute(sql, params)
        for trigger in triggers:
            connection.execute(trigger["sql"])


@pytest.mark.parametrize("kind", ["profile", "intent_job", "applied_job", "intent_quota", "applied_quota"])
def test_native_seal_rechecks_original_profile_and_receipt_ownership(tmp_path, monkeypatch, kind):
    import json
    from control_plane.operator_harness_contract import OperationReceiptKind, operation_receipt_command_id
    f = _started_native(tmp_path, monkeypatch)
    turn, observation = _turn(f)
    harness = f.runtime.operator_harness
    ref = harness.seal_native_conversation_result(turn=turn, observation=observation, **f.lease)
    if kind == "profile":
        with f.runtime.store.read() as connection:
            row = connection.execute("SELECT * FROM attempts WHERE attempt_id=?", (turn.attempt_id,)).fetchone()
        profile = json.loads(row["requested_execution_profile_json"])
        profile["workspace"]["base_sha"] = "b"*40
        encoded = rt._json_dumps(profile)
        _corrupt_fixture(f.runtime, "attempts",
            "UPDATE attempts SET requested_execution_profile_json=?,requested_execution_profile_digest=? WHERE attempt_id=?",
            (encoded, hashlib.sha256(encoded.encode()).hexdigest(), turn.attempt_id))
    else:
        field = "job_id" if kind.endswith("job") else "quota_class"
        command = observation.native_claim.operation_id
        if kind.startswith("applied"):
            command = operation_receipt_command_id(OperationId(command), OperationReceiptKind.APPLIED)
        _corrupt_fixture(f.runtime, "events",
            f"UPDATE events SET {field}=? WHERE command_id=?",
            (f.root.job_id if field == "job_id" else None, command))
    with pytest.raises(rt.StateConflict):
        harness.seal_native_conversation_result(turn=turn, observation=observation, **f.lease)
    with pytest.raises(rt.StateConflict):
        harness.native_conversation_result(attempt_id=turn.attempt_id, reference=ref)


def test_native_successor_requires_flushed_result_not_candidate_or_interrupt_only(tmp_path, monkeypatch):
    f = _started_native(tmp_path, monkeypatch)
    turn, observation = _turn(f)
    harness = f.runtime.operator_harness
    operation = OperationId("ohf-op:unsealed-native-successor")
    with pytest.raises(rt.StateConflict, match="flushed result seal"):
        harness.reserve_turn(epoch=f.epoch, generation=f.generation, operation_id=operation, **f.lease)
    assert f.runtime.store.find_event_by_command_id(operation.command_id) is None
    harness.seal_native_conversation_result(turn=turn, observation=observation, **f.lease)
    successor = harness.reserve_turn(epoch=f.epoch, generation=f.generation, operation_id=operation, **f.lease)
    assert successor.turn_id != turn.turn_id


def test_historical_native_result_survives_release_but_cannot_authorize_new_seal(tmp_path, monkeypatch):
    from control_plane.operator_harness_contract import ProcessLiveness, ProviderWriterState, ReconcileObservation
    f = _started_native(tmp_path, monkeypatch)
    turn, observation = _turn(f)
    harness = f.runtime.operator_harness
    ref = harness.seal_native_conversation_result(turn=turn, observation=observation, **f.lease)
    harness.record_reconcile_observation(generation=f.generation,
        observation=ReconcileObservation(ProcessLiveness.PROVEN_DEAD,
            ProcessIdentityObservation(2101, 2101, "native-runtime-test", "fixture-boot"),
            True, ProviderWriterState.RELEASED, f.session_id), **f.lease)
    assert harness.native_conversation_result(attempt_id=turn.attempt_id, reference=ref)["observation"] == observation.to_wire()
    with pytest.raises(rt.StateConflict):
        harness.seal_native_conversation_result(turn=turn, observation=observation, **f.lease)


def test_native_conversation_cannot_emit_a_planner_role_seal(tmp_path, monkeypatch):
    from test_interactive_tx5_runtime import _observation_for_plan
    f = _started_native(tmp_path, monkeypatch)
    turn, _ = _turn(f)
    role = _observation_for_plan(f.runtime, f.dispatch, f.epoch, f.generation, turn, {})
    with pytest.raises(rt.StateConflict, match="cannot seal a role result"):
        f.runtime.operator_harness.seal_orchestration_role_result(turn=turn, observation=role, **f.lease)


@pytest.mark.parametrize("changes", [{"through_seq": 15}, {"through_seq": 4}, {"native_turn": 1}, {"native_turn": 0}])
def test_native_successor_cannot_reuse_persisted_prefix_or_claimed_turn(tmp_path, monkeypatch, changes):
    f = _started_native(tmp_path, monkeypatch)
    harness = f.runtime.operator_harness
    turn, observation = _turn(f)
    first = harness.seal_native_conversation_result(turn=turn, observation=observation, **f.lease)
    successor, bad = _turn(f, 2, claim_changes=changes)
    with pytest.raises(rt.StateConflict, match="persisted prefix"):
        harness.seal_native_conversation_result(turn=successor, observation=bad, **f.lease)
    assert harness.native_conversation_result(attempt_id=turn.attempt_id, reference=first)["predecessor_result"] is None


def test_native_successor_preserves_gaps_and_uses_durable_claim_not_late_observed_turn(tmp_path, monkeypatch):
    f = _started_native(tmp_path, monkeypatch)
    harness = f.runtime.operator_harness
    first_turn, first = _turn(f)
    ref = harness.seal_native_conversation_result(turn=first_turn, observation=first, **f.lease)
    # Late observedLastTurn is not an independent durable last-turn watermark.
    second_turn, second = _turn(f, 2, claim_changes={"through_seq": 30, "native_turn": 2})
    assert second.native_claim.native_turn == first.native_terminal.observed_last_turn
    next_ref = harness.seal_native_conversation_result(turn=second_turn, observation=second, **f.lease)
    payload = harness.native_conversation_result(attempt_id=first_turn.attempt_id, reference=next_ref)
    assert payload["predecessor_result"] == ref.to_wire()


def test_native_stop_receipt_does_not_replace_original_begin_result_or_successor(tmp_path, monkeypatch):
    from control_plane.operator_harness_contract import OperationReceiptKind, operation_receipt_command_id
    f = _started_native(tmp_path, monkeypatch)
    orchestrator, port, adapter, session = _orchestrator(f)
    interrupts = []
    stop = OperationId("ohf-op:native-initial-stop")
    def interrupt(turn, *, operation_id):
        assert turn == adapter.turn and operation_id == stop
        interrupts.append((turn, operation_id))
        adapter.result = NativeResult("cancelled", adapter.result.terminal)
    monkeypatch.setattr(adapter, "interrupt_turn", interrupt, raising=False)
    first = orchestrator.run_turn(session, operation_id=OperationId("ohf-op:native-interrupted-begin"),
        _on_turn_applied=lambda turn: orchestrator.interrupt_turn(session, turn, operation_id=stop))
    assert interrupts == [(first.turn, stop)]
    payload = f.runtime.operator_harness.native_conversation_result(
        attempt_id=f.epoch.attempt_id, reference=first.native_result)
    assert payload["observation"]["stop_reason"] == "cancelled"
    assert payload["observation"]["native_claim"]["operationId"] == "ohf-op:native-interrupted-begin"
    assert f.runtime.events.get_event_by_command_id(
        operation_receipt_command_id(stop, OperationReceiptKind.APPLIED)) is not None
    second = orchestrator.run_turn(session, operation_id=OperationId("ohf-op:native-after-stop"))
    assert second.native_result != first.native_result and adapter.calls == 2
    assert f.runtime.operator_harness.native_conversation_result(
        attempt_id=f.epoch.attempt_id, reference=second.native_result)["predecessor_result"] == first.native_result.to_wire()


def test_active_observer_failure_preserves_acknowledged_effect_without_replay(tmp_path, monkeypatch):
    from control_plane.operator_harness_orchestrator import OperatorHarnessOrchestrationError
    from control_plane.operator_harness_contract import OperationReceiptKind, operation_receipt_command_id
    f = _started_native(tmp_path, monkeypatch)
    orchestrator, port, adapter, session = _orchestrator(f)
    operation = OperationId("ohf-op:failed-native-active-observation")
    with pytest.raises(OperatorHarnessOrchestrationError, match="acknowledged turn"):
        orchestrator.run_turn(session, operation_id=operation, _on_turn_applied=lambda _: True)
    assert adapter.calls == 1
    assert f.runtime.events.get_event_by_command_id(
        operation_receipt_command_id(operation, OperationReceiptKind.APPLIED)) is not None
    with pytest.raises(rt.StateConflict, match="not retryable"):
        orchestrator.run_turn(session, operation_id=operation)
    assert adapter.calls == 1
