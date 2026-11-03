"""W3 normal composition: private Runtime, synthetic native observations only."""
from control_plane.runtime_binding_projection import project_runtime_binding
from control_plane.session_targets import load_session_targets
from tests.test_runtime_binding_projection import _admitted_runtime


def test_canonical_router_codex_provider_projects_without_new_admission(tmp_path):
    # Production ModelRouter uses canonical provider alias codex; the OHF
    # adapter separately names its native surface openai-codex.
    runtime, _, attempt, _, generation, _, _ = _admitted_runtime(tmp_path, provider="codex")
    target = load_session_targets().get("EXECUTIVE-COO-CODEX-A")
    binding = project_runtime_binding(runtime, attempt.attempt_id, target)
    assert binding.reasoning_surface == "codex"
    assert binding.binding_generation == generation.generation_number
    assert target.target_enabled is False


def test_private_completed_turn_callback_runs_before_existing_role_seal(tmp_path):
    import pytest
    from control_plane.executive_operator_harness_port import ExecutiveOperatorHarnessPort
    from control_plane.executive_runtime import AttemptLease, StateConflict
    from control_plane.operator_harness_contract import OperationId, SessionStartObservation, compare_launch
    from control_plane.operator_harness_orchestrator import OperatorHarnessOrchestrator, OperatorSessionReceipt
    from tests.test_runtime_binding_projection import _attestation
    from tests.test_executive_operator_supervisor import _ActiveAdapter

    runtime, dispatch, attempt, epoch, generation, process, profile = _admitted_runtime(tmp_path)
    port = ExecutiveOperatorHarnessPort(runtime, AttemptLease(attempt, dispatch.lease_token))
    adapter = _ActiveAdapter(runtime, lambda _: "output schema", cancel_during_collect=False)
    adapter.profile = profile
    adapter.process = process
    adapter.provider_session_id = "PROVIDER-SESSION-1"
    observed = _attestation(profile)
    session = OperatorSessionReceipt(attempt.attempt_id, epoch, generation,
        SessionStartObservation(adapter.provider_session_id, process), observed,
        compare_launch(profile, observed))
    orchestrator = OperatorHarnessOrchestrator(port, adapter,
        attestation_reader=lambda *_: observed)
    seen = []
    def consume(receipt, raw):
        assert raw.turn_id == receipt.turn.turn_id
        assert runtime.current_harness_binding_source(attempt.attempt_id).provider_session_id == adapter.provider_session_id
        seen.append(receipt.turn)
    receipt = orchestrator.run_turn(session,
        operation_id=OperationId("ohf-op:private-preseal-test"), _before_role_seal=consume)
    assert seen == [receipt.turn]
    assert adapter.begin_turn_calls == 1
    with pytest.raises(StateConflict, match="not a retained native writer"):
        runtime.current_harness_binding_source(attempt.attempt_id)


# This fixture uses real admission, claim, checkpoint, positive process release,
# restore invalidation and COO retry APIs. Native observations alone are fake.
def _successor(tmp_path, monkeypatch, *, commission_content=b'# W3 commission\n\nContinue the original bounded work.\n'):
    import copy
    from control_plane import codex_operator_adapter as codex
    from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor
    from control_plane.executive_supervisor import ExecutiveSupervisor
    from control_plane.executive_runtime import AttemptLease
    from control_plane.operator_harness_contract import CheckpointObservation, OperationId
    from tests import test_executive_operator_supervisor as fixture
    original_submit = fixture.submit_intent
    def submit(runtime, intent, **kwargs):
        intent = copy.deepcopy(intent)
        intent['intent_id'] = 'w3-original-operation-fixture'
        binding = copy.deepcopy(kwargs['execution_binding'])
        binding['operator_harness_version'] = codex.CONSUMPTION_EVIDENCE_PINNED_HARNESS_VERSION
        binding['operator_harness_binary_digest'] = codex.CONSUMPTION_EVIDENCE_PINNED_BINARY_DIGEST
        kwargs['execution_binding'] = binding
        return original_submit(runtime, intent, **kwargs)
    monkeypatch.setattr(fixture, 'submit_intent', submit)
    from control_plane.executive_runtime import WorkerRegistry
    original_register = WorkerRegistry.register_worker
    def register(registry, worker_id, **kwargs):
        kwargs = copy.deepcopy(kwargs)
        for q in (kwargs.get('quota_classes') or {}).values():
            if isinstance(q, dict) and 'metadata' in q:
                q['metadata'].update(harness_version=codex.CONSUMPTION_EVIDENCE_PINNED_HARNESS_VERSION,
                    harness_binary_digest=codex.CONSUMPTION_EVIDENCE_PINNED_BINARY_DIGEST)
        return original_register(registry, worker_id, **kwargs)
    monkeypatch.setattr(WorkerRegistry, 'register_worker', register)
    clock = fixture._Clock()
    runtime, root, planner = fixture._seed_dispatchable_operator_planner(tmp_path,
        commission_content=commission_content, clock=clock)
    worker = runtime.workers.get_worker('worker-a')
    quota = runtime.workers.get_quota_class('worker-a', 'codex-coo-operator')
    metadata = copy.deepcopy(quota.metadata)
    metadata.update(harness_version=codex.CONSUMPTION_EVIDENCE_PINNED_HARNESS_VERSION,
        harness_binary_digest=codex.CONSUMPTION_EVIDENCE_PINNED_BINARY_DIGEST)
    quota_dict = dict(provider=quota.provider, model=quota.model, effort=quota.effort,
        cost_class=quota.cost_class, capabilities=quota.capabilities, metadata=metadata)
    dispatch = runtime.attempts.dispatch_cycle_job(planner.job_id,
        command_id=f'coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1', worker_id='worker-a')
    lease = AttemptLease(dispatch.attempt, dispatch.lease_token)
    sup = ExecutiveOperatorSupervisor(runtime, adapter_factory=lambda _: None,
        prompt_source=ExecutiveSupervisor(runtime, object(), inspector=object(), process_controller=object()))
    adapter = fixture._ActiveAdapter(runtime, lambda _: 'output schema', cancel_during_collect=False)
    orch = sup._orchestrator(lease, adapter)
    session = orch.start_attempt(attempt_id=lease.attempt.attempt_id,
        requested=sup._requested_profile(planner, lease), operation_id=OperationId('ohf-op:source-start'))
    checkpoint = {'summary': 'Original source work saved.', 'completed_steps': ['read'],
        'current_state': 'Next useful source check remains.', 'artifacts': [],
        'next_actions': ['Complete the bounded next source check.'], 'errors': []}
    op = OperationId('ohf-op:source-checkpoint')
    orch.runtime.begin_operator_checkpoint(lease.attempt.attempt_id, session.generation, op)
    orch.runtime.apply_operator_checkpoint(lease.attempt.attempt_id, session.generation, op,
        CheckpointObservation(checkpoint, provider_mutated_state=False))
    orch.graceful_stop(session, operation_id=OperationId('ohf-op:source-stop'))
    runtime.operator_harness.invalidate_after_restore()
    source = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    expectation = runtime.jobs.project_retry_safety(planner.job_id, expected_attempt_id=source.attempt_id)
    runtime.jobs.commit_coo_retry_decision(root.job_id, selected_job_id=planner.job_id, expectation=expectation)
    runtime.workers.register_worker('worker-b', provider=worker.provider,
        account_label='other-account@company', worker_type='fixture', capabilities=worker.capabilities,
        quota_classes={'codex-coo-operator': quota_dict})
    target = runtime.attempts.dispatch_cycle_job(planner.job_id,
        command_id=f'coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:2', worker_id='worker-b')
    assert target is not None and target.lease_token
    return runtime, runtime.jobs.get_job(planner.job_id), AttemptLease(target.attempt, target.lease_token), source


def _normal_supervisor(runtime, *, alter=None, normal_factory=None):
    import dataclasses
    import hashlib
    from control_plane import codex_operator_adapter as codex
    from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor
    from control_plane.executive_supervisor import ExecutiveSupervisor
    from tests.test_executive_operator_supervisor import _ActiveAdapter
    made = []
    class Native(_ActiveAdapter):
        def read_events(self, cursor, *, timeout_seconds):
            events, next_cursor = super().read_events(cursor, timeout_seconds=timeout_seconds)
            return tuple(dataclasses.replace(e, kind='turn/completed',
                provider_event_id=self.native_turn_id) for e in events), next_cursor
        def collect_retained_plain_text_evidence(self, turn):
            value = self.prompts[-1].encode('utf-8')
            proof = codex.RetainedPlainInputEvidence(turn.attempt_id, turn.session_epoch_id,
                turn.process_generation_id, turn.turn_id, self.provider_session_id,
                self.native_turn_id, hashlib.sha256(value).hexdigest(), len(value),
                codex.CONSUMPTION_EVIDENCE_SHAPE, codex.CONSUMPTION_EVIDENCE_PINNED_HARNESS_VERSION,
                codex.CONSUMPTION_EVIDENCE_PINNED_BINARY_DIGEST, codex.CONSUMPTION_EVIDENCE_SCOPE)
            return proof if alter is None else alter(proof)
    def factory(attempt, requested, loader, *, recovery):
        assert recovery is False
        adapter = Native(runtime, loader, cancel_during_collect=False)
        made.append(adapter)
        return adapter
    prompt_source = ExecutiveSupervisor(runtime, object(), inspector=object(), process_controller=object())
    if normal_factory is not None:
        from tests.test_claimed_operator_control_composition import capture
        path, monkeypatch = normal_factory
        path.mkdir()
        _, supervisor, _ = capture(path, monkeypatch, runtime=runtime,
            prompt_source=prompt_source, claimed_operator_adapter_factory=factory)
        return supervisor, made
    return ExecutiveOperatorSupervisor(runtime, claimed_adapter_factory=factory,
        prompt_source=prompt_source), made


def test_normal_supervisor_delivers_exact_capsule_and_closed_ack(tmp_path, monkeypatch):
    import json
    runtime, job, lease, source = _successor(tmp_path, monkeypatch)
    supervisor, made = _normal_supervisor(runtime, normal_factory=(tmp_path / "control", monkeypatch))
    result = supervisor._run_claimed(job, lease)
    assert result.attempt.status.value == 'COMPLETED'
    assert len(made) == 1 and made[0].begin_turn_calls == 1
    prepared = runtime.events.get_event_by_command_id(f'operator-continuation:prepare:{lease.attempt.attempt_id}')
    ack = runtime.events.get_event_by_command_id(f'operator-continuation:ack:{lease.attempt.attempt_id}')
    assert prepared and ack
    assert prepared.payload['capsule']['operation_key'] == 'w3-original-operation-fixture'
    assert prepared.payload['capsule']['source_attempt_id'] == source.attempt_id
    canonical = json.dumps(prepared.payload['capsule'], sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    assert made[0].prompts[0].count(canonical) == 1
    assert ack.payload['ack']['capsule_id'] == prepared.payload['capsule_id']


def _has_ack(runtime, lease):
    return runtime.events.get_event_by_command_id(f'operator-continuation:ack:{lease.attempt.attempt_id}')


import pytest
import dataclasses


def test_initialized_contract_mismatch_refuses_before_continuation_prepare(
    tmp_path, monkeypatch,
):
    from control_plane import operator_continuation_delivery as delivery
    from control_plane.executive_operator_supervisor import (
        ExecutiveOperatorSupervisorError,
    )
    from tests.test_executive_operator_supervisor import _ActiveAdapter

    runtime, job, lease, _ = _successor(tmp_path, monkeypatch)
    supervisor, made = _normal_supervisor(runtime)
    attestations = []
    original_attestation = _ActiveAdapter.observed_attestation

    def mismatched_attestation(adapter, generation):
        observed = original_attestation(adapter, generation)
        attestations.append(adapter)
        adapter.plan_contract = "executive-plan-v3"
        return observed

    prepare_calls = []
    original_prepare = delivery._ContinuationDelivery.prepare

    def observe_prepare(continuation, session):
        prepare_calls.append(session)
        return original_prepare(continuation, session)

    monkeypatch.setattr(
        _ActiveAdapter, "observed_attestation", mismatched_attestation,
    )
    monkeypatch.setattr(
        delivery._ContinuationDelivery, "prepare", observe_prepare,
    )
    with pytest.raises(
        ExecutiveOperatorSupervisorError,
        match="legacy adapter plan contract",
    ):
        supervisor._run_claimed(job, lease)

    assert len(made) == 1
    assert made[0] in attestations
    assert prepare_calls == []
    assert runtime.events.get_event_by_command_id(
        f"operator-continuation:prepare:{lease.attempt.attempt_id}"
    ) is None
    assert not _has_ack(runtime, lease)
    assert made[0].begin_turn_calls == made[0].read_calls == 0
    assert made[0].stop_calls == 1
    assert runtime.attempts.get_attempt(
        lease.attempt.attempt_id
    ).status.value != "COMPLETED"


@pytest.mark.parametrize('field,value', [
    ('retained_input_digest', 'f'*64), ('retained_input_byte_length', 1),
    ('turn_id', 'ohf-turn:foreign'), ('session_epoch_id', 'ohf-epoch:foreign'),
    ('process_generation_id', 'ohf-gen:foreign'), ('attempt_id', 'ATT-'+'f'*32),
    ('provider_session_id', 'FOREIGN'), ('provider_native_turn_id', 'FOREIGN'),
    ('harness_version', '0.166.0'), ('harness_binary_digest', 'a'*64),
    ('input_shape', 'skill'), ('scope', 'model used it'),
])
def test_normal_path_refuses_spliced_input_before_ack(tmp_path, monkeypatch, field, value):
    runtime, job, lease, _ = _successor(tmp_path, monkeypatch)
    supervisor, made = _normal_supervisor(runtime,
        alter=lambda proof: dataclasses.replace(proof, **{field: value}))
    with pytest.raises(Exception, match='role result could not be sealed'):
        supervisor._run_claimed(job, lease)
    assert not _has_ack(runtime, lease)
    assert made[0].begin_turn_calls == 1
    assert runtime.attempts.get_attempt(lease.attempt.attempt_id).status.value != 'COMPLETED'


@pytest.mark.parametrize('commit_first', [True, False])
def test_lost_ack_response_reconciles_same_event_without_retry(tmp_path, monkeypatch, commit_first):
    from control_plane.executive_operator_harness_port import ExecutiveOperatorHarnessPort
    runtime, job, lease, _ = _successor(tmp_path, monkeypatch)
    original = ExecutiveOperatorHarnessPort.acknowledge_operator_continuation
    calls = []
    def lost(port, attempt_id, ack):
        calls.append(ack)
        if commit_first:
            original(port, attempt_id, ack)
        raise ConnectionError('ACK response lost')
    monkeypatch.setattr(ExecutiveOperatorHarnessPort, 'acknowledge_operator_continuation', lost)
    supervisor, made = _normal_supervisor(runtime)
    if commit_first:
        assert supervisor._run_claimed(job, lease).attempt.status.value == 'COMPLETED'
        assert _has_ack(runtime, lease)
    else:
        with pytest.raises(Exception, match='role result could not be sealed'):
            supervisor._run_claimed(job, lease)
        assert not _has_ack(runtime, lease)
    assert len(calls) == 1 and made[0].begin_turn_calls == 1
    # Expired/restarted recovery never replays the callback or native turn.
    supervisor._recover_one(lease.attempt.attempt_id)
    assert len(calls) == 1 and len(made) == 1 and made[0].begin_turn_calls == 1


def test_ack_then_role_seal_failure_does_not_complete_job(tmp_path, monkeypatch):
    from control_plane.executive_operator_harness_port import ExecutiveOperatorHarnessPort
    runtime, job, lease, _ = _successor(tmp_path, monkeypatch)
    def fail(*_args):
        raise RuntimeError('role seal failed after ACK')
    monkeypatch.setattr(ExecutiveOperatorHarnessPort, 'seal_operator_role_result', fail)
    supervisor, made = _normal_supervisor(runtime)
    with pytest.raises(Exception, match='role result could not be sealed'):
        supervisor._run_claimed(job, lease)
    assert _has_ack(runtime, lease)
    assert runtime.attempts.get_attempt(lease.attempt.attempt_id).status.value != 'COMPLETED'
    supervisor._recover_one(lease.attempt.attempt_id)
    assert len(made) == 1 and made[0].begin_turn_calls == 1


def test_binding_changes_during_input_read_refuses_ack(tmp_path, monkeypatch):
    runtime, job, lease, _ = _successor(tmp_path, monkeypatch)
    def cancel(proof):
        runtime.jobs.cancel_job(job.job_id)
        return proof
    supervisor, made = _normal_supervisor(runtime, alter=cancel)
    with pytest.raises(Exception, match='role result could not be sealed'):
        supervisor._run_claimed(job, lease)
    assert not _has_ack(runtime, lease)
    assert made[0].begin_turn_calls == 1


def test_prepared_capsule_is_not_resubmitted_or_completed_by_restart(tmp_path, monkeypatch):
    from control_plane.operator_continuation_delivery import _ContinuationDelivery
    runtime, job, lease, _ = _successor(tmp_path, monkeypatch)
    prepare = _ContinuationDelivery.prepare
    def crash(delivery, session):
        prepare(delivery, session)
        raise RuntimeError('trusted transient render lost before dispatch')
    monkeypatch.setattr(_ContinuationDelivery, 'prepare', crash)
    supervisor, made = _normal_supervisor(runtime)
    with pytest.raises(RuntimeError, match='transient render lost'):
        supervisor._run_claimed(job, lease)
    assert runtime.events.get_event_by_command_id(f'operator-continuation:prepare:{lease.attempt.attempt_id}')
    assert made[0].begin_turn_calls == 0
    supervisor._recover_one(lease.attempt.attempt_id)
    assert len(made) == 1 and made[0].begin_turn_calls == 0
    assert not _has_ack(runtime, lease)


def test_known_resource_shape_refuses_before_provider_and_prepare(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
    runtime, job, lease, _ = _successor(tmp_path, monkeypatch)
    supervisor, made = _normal_supervisor(runtime)
    original = ExecutionCapabilityRegistry.resolve
    def resolve(registry, name):
        profile = original(registry, name)
        # Keep real constructor validation intact, then change the source-owned
        # declaration seen at the continuation preflight seam.
        if name == job.constraints['execution_profile_id']:
            return dataclasses.replace(profile, resource_grants=(SimpleNamespace(resource_id='unsupported'),))
        return profile
    requested = supervisor._requested_profile(job, lease)
    monkeypatch.setattr(supervisor, '_requested_profile', lambda *_: requested)
    monkeypatch.setattr(ExecutionCapabilityRegistry, 'resolve', resolve)
    with pytest.raises(Exception, match='UNSUPPORTED before PREPARE'):
        supervisor._run_claimed(job, lease)
    assert made == [] and not _has_ack(runtime, lease)
    assert not runtime.events.get_event_by_command_id(f'operator-continuation:prepare:{lease.attempt.attempt_id}')


@pytest.mark.parametrize('damage', ['completion-kind', 'completion-native-id', 'candidate-artifact'])
def test_native_completion_and_candidate_are_capsule_validator_inputs(tmp_path, monkeypatch, damage):
    from control_plane.operator_continuation_delivery import _ContinuationDelivery
    runtime, job, lease, _ = _successor(tmp_path, monkeypatch)
    original = _ContinuationDelivery.consume_before_seal
    def damaged(delivery, receipt, raw, adapter, session):
        if damage == 'candidate-artifact':
            raw = dataclasses.replace(raw, provider_turn_artifact_digest='f'*64)
        else:
            event = receipt.events[0]
            event = dataclasses.replace(event, **({'kind': 'turn.completed'} if damage == 'completion-kind'
                else {'provider_event_id': 'FOREIGN'}))
            receipt = dataclasses.replace(receipt, events=(event,))
        return original(delivery, receipt, raw, adapter, session)
    monkeypatch.setattr(_ContinuationDelivery, 'consume_before_seal', damaged)
    supervisor, made = _normal_supervisor(runtime)
    with pytest.raises(Exception, match='role result could not be sealed'):
        supervisor._run_claimed(job, lease)
    assert not _has_ack(runtime, lease) and made[0].begin_turn_calls == 1


def test_target_source_changes_during_input_read_refuses_ack(tmp_path, monkeypatch):
    from control_plane import operator_continuation_delivery as composition
    runtime, job, lease, _ = _successor(tmp_path, monkeypatch)
    original = composition._target
    def changed(proof):
        monkeypatch.setattr(composition, '_target', lambda: dataclasses.replace(original(), workstream='foreign'))
        return proof
    supervisor, made = _normal_supervisor(runtime, alter=changed)
    with pytest.raises(Exception, match='role result could not be sealed'):
        supervisor._run_claimed(job, lease)
    assert not _has_ack(runtime, lease)


def test_second_same_operation_call_cannot_dispatch_again(tmp_path, monkeypatch):
    runtime, job, lease, _ = _successor(tmp_path, monkeypatch)
    supervisor, made = _normal_supervisor(runtime)
    supervisor._run_claimed(job, lease)
    with pytest.raises(Exception):
        supervisor._run_claimed(job, lease)
    assert len(made) == 1 and made[0].begin_turn_calls == 1
    assert _has_ack(runtime, lease)


def test_source_free_legacy_successor_does_not_gain_capsule_or_ack(tmp_path, monkeypatch):
    from control_plane.executive_runtime import StateConflict
    runtime, job, lease, _ = _successor(tmp_path, monkeypatch, commission_content=None)
    supervisor, made = _normal_supervisor(runtime)
    with pytest.raises(StateConflict, match='cross-realm continuation requires an immutable commission'):
        supervisor._run_claimed(job, lease)
    assert made == []
    assert runtime.events.get_event_by_command_id(
        f'operator-continuation:prepare:{lease.attempt.attempt_id}') is None
    assert not _has_ack(runtime, lease)
