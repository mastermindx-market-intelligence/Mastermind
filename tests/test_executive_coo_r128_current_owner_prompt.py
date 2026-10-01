"""Real public owner/Runtime composition; the SDK RPC transport is hermetic."""
import dataclasses
import json

import pytest

from control_plane.executive_operator_supervisor import (
    ExecutiveOperatorSupervisor, ExecutiveOperatorSupervisorError,
)
from control_plane.executive_runtime import AttemptLease, AttemptStatus, StateConflict
from control_plane.operator_harness_contract import (
    EventCursor, HarnessAdapterCapabilities, ProcessGenerationRef, TurnRef,
)
from control_plane.operator_harness_wire import to_wire
from control_plane.operator_harness_orchestrator import OperatorEffectUnknown
from control_plane.remote_operator_harness_adapter import (
    RemoteOperatorHarnessAdapter, _REQUIRED_REMOTE_OPERATIONS,
)
from tests.test_executive_coo_r119_later_turn import _inventory
from tests.test_executive_coo_r124_domain_turn import (
    _real_consumption_context, _append_negative_event,
)
from tests.test_executive_coo_r125_domain_seal import ObservedConsumptionAdapter


def _context(tmp_path, monkeypatch):
    rt, root, domain, attempt, session, _, _, lease, _, digest = _real_consumption_context(tmp_path, monkeypatch)
    projection = rt.jobs.project_cycle_domain_consumption(root.job_id, domain_attempt_id=attempt)
    body = dict(schema_version="mastermind.executive_coo_domain_consumption/v1",
        root_job_id=root.job_id, domain_job_id=domain.job_id, domain_attempt_id=attempt,
        consumption_projection_digest=digest, consumed_result="已消化完整工作與獨立審查 · full reviewed outcome")
    transport = ObservedConsumptionAdapter(session.observation.provider_session_id, body)

    class Client:
        def __init__(self): self.calls = []
        def request_sync(self, operation, payload, **kwargs):
            self.calls.append((operation, payload))
            if operation == "ohf-begin-turn":
                assert payload['launch'] == to_wire(session.launch)
                started = transport.begin_turn(operation_id=payload['operation_id'],
                    turn=TurnRef(**payload['turn']), generation=ProcessGenerationRef(**payload['generation']),
                    launch=session.launch)
                return {'observation': to_wire(started)}
            if operation == "ohf-collect-turn":
                turn = TurnRef(**payload['turn'])
                events, cursor = transport.read_events(EventCursor(**payload['cursor']))
                candidate = transport.collect_candidate_result(turn)
                return dict(events=to_wire(events), cursor=to_wire(cursor),
                    candidate=to_wire(candidate), raw_role_result=to_wire(transport.observe_raw_role_result(turn)))
            raise AssertionError('forbidden RPC: ' + operation)

    client = Client()
    capabilities = HarnessAdapterCapabilities(
        interface_version='mastermind.operator_harness/v1', supported_required_operations=_REQUIRED_REMOTE_OPERATIONS,
        supported_optional_operations=(), supports_native_resume=False, supports_native_fork=False,
        supports_steering=False, supports_approval_response=False, supports_checkpoint=False,
        supports_config_staging=False, supports_subagent_capability_ceiling=False,
        supports_structured_events=True)
    factories = []
    adapters = []
    def factory(current, requested, loader, *, recovery):
        factories.append((current, requested, recovery))
        assert current.attempt_id == attempt and requested == session.launch.requested and recovery
        adapter = RemoteOperatorHarnessAdapter(client, turn_input_loader=loader, capabilities=capabilities)
        # Restore only the actual attestation captured from the public initial G1.
        # This cache is transport data, never a new admission or positive authority.
        adapter._start_receipts[session.generation.process_generation_id] = {'attestation': session.observed}
        adapters.append(adapter)
        return adapter
    sup = ExecutiveOperatorSupervisor(rt, claimed_adapter_factory=factory,
        prompt_source=object(), instance_id=lease.attempt.lease_owner)
    return rt, root, domain, session, lease, projection, body, sup, client, transport, factories, adapters


def test_same_current_owner_sends_complete_reviewed_bodies_in_actual_sdk_rpc_and_seals(tmp_path, monkeypatch):
    rt, root, domain, session, lease, projection, body, sup, client, transport, factories, _ = _context(tmp_path, monkeypatch)
    initial = rt.events.get_event_by_command_id('orchestration-result-seal:' + session.attempt_id)
    before = _inventory(rt)
    sealed = sup.continue_domain_consumption(lease)
    sent = [payload for name, payload in client.calls if name == 'ohf-begin-turn']
    assert len(sent) == len(transport.begin_turn_calls) == 1
    prompt = sent[0]['prompt']
    projection_text, schema_text = prompt.split('CANONICAL_REVIEWED_RESULTS_JSON:\n')[1].split('\nOUTPUT_SCHEMA_JSON:\n')
    assert json.loads(projection_text) == projection
    assert projection['revisions'] and projection['revision_results']
    schema = json.loads(schema_text)
    assert schema['properties']['domain_attempt_id']['const'] == session.attempt_id
    assert schema['properties']['consumption_projection_digest']['const'] == projection['consumption_projection_digest']
    assert set(schema['properties']) == set(body) and schema['additionalProperties'] is False
    assert lease.lease_token not in prompt and 'evidence data' in prompt
    assert sealed['consumption_result'] == body
    assert rt.events.get_event_by_command_id(initial.command_id) == initial
    assert rt.attempts.get_attempt(session.attempt_id).status is AttemptStatus.CHECKPOINTED
    assert rt.jobs.get_job(domain.job_id).current_attempt_id == session.attempt_id
    after = _inventory(rt)
    for table in ('jobs', 'harness_session_epochs', 'process_generations'):
        if table in before: assert after[table] == before[table], table
    with rt.store.read() as c:
        assert c.execute("SELECT COUNT(*) FROM coo_provider_charges WHERE root_job_id=? AND effect_class='FINAL'", (root.job_id,)).fetchone()[0] == 1
    assert len(factories) == 1 and factories[0][2] is True
    with pytest.raises(ExecutiveOperatorSupervisorError, match='INTENT cardinality'):
        sup.continue_domain_consumption(lease)
    assert _inventory(rt) == after and len(sent) == len(transport.begin_turn_calls) == 1
    assert len([name for name, _ in client.calls if name == 'ohf-begin-turn']) == 1


@pytest.mark.parametrize('bad', ['owner', 'worker', 'fence', 'token', 'job', 'profile_digest', 'grant_digest', 'principal_digest', 'status', 'untyped_lease',
    'profile_data', 'grant_data', 'placement_data', 'principal_data', 'float_fence', 'execution_mode'])
def test_foreign_owner_or_lease_refuses_before_factory_provider_or_credit(tmp_path, monkeypatch, bad):
    rt, _, _, _, lease, _, _, sup, client, _, factories, _ = _context(tmp_path, monkeypatch)
    if bad == 'owner': sup.instance_id = 'foreign-owner'
    if bad == 'token': lease = AttemptLease(lease.attempt, 'foreign-token')
    fields = {'worker':'worker_id', 'fence':'fence_generation', 'job':'job_id',
        'profile_digest':'requested_execution_profile_digest', 'grant_digest':'effective_grant_digest',
        'principal_digest':'execution_principal_snapshot_digest', 'status':'status'}
    if bad in fields:
        value = lease.attempt.fence_generation + 1 if bad == 'fence' else AttemptStatus.RUNNING if bad == 'status' else 'foreign'
        lease = AttemptLease(dataclasses.replace(lease.attempt, **{fields[bad]:value}), lease.lease_token)
    if bad == 'untyped_lease': lease = dataclasses.asdict(lease)
    metadata = {'profile_data':'requested_execution_profile', 'grant_data':'effective_grant',
        'placement_data':'placement_snapshot', 'principal_data':'execution_principal_snapshot',
        'execution_mode':'execution_mode', 'float_fence':'fence_generation'}
    if bad in metadata:
        value = float(lease.attempt.fence_generation) if bad == 'float_fence' else 'foreign' if bad == 'execution_mode' else {'foreign':'caller metadata'}
        lease = AttemptLease(dataclasses.replace(lease.attempt, **{metadata[bad]:value}), lease.lease_token)
    before = _inventory(rt)
    with pytest.raises((ExecutiveOperatorSupervisorError, StateConflict)): sup.continue_domain_consumption(lease)
    assert _inventory(rt) == before and not client.calls and not factories


@pytest.mark.parametrize('timeout', [True, False, 0, -1, float('inf'), float('nan'), 301, '30', None])
def test_invalid_timeout_never_reserves_final(tmp_path, monkeypatch, timeout):
    rt, _, _, _, lease, _, _, sup, client, _, factories, _ = _context(tmp_path, monkeypatch)
    before = _inventory(rt)
    with pytest.raises(ExecutiveOperatorSupervisorError): sup.continue_domain_consumption(lease, timeout_seconds=timeout)
    assert _inventory(rt) == before and not client.calls and not factories


def test_factory_failure_retains_exact_admitted_final_and_never_retries(tmp_path, monkeypatch):
    rt, root, _, _, lease, _, _, sup, client, _, _, _ = _context(tmp_path, monkeypatch)
    def refused(*args, **kwargs): raise RuntimeError('incumbent provider binding unavailable')
    sup._claimed_adapter_factory = refused
    with pytest.raises(ExecutiveOperatorSupervisorError, match='construction refused'): sup.continue_domain_consumption(lease)
    held = _inventory(rt)
    with rt.store.read() as c:
        assert c.execute("SELECT COUNT(*) FROM coo_provider_charges WHERE root_job_id=? AND effect_class='FINAL'", (root.job_id,)).fetchone()[0] == 1
    with pytest.raises(ExecutiveOperatorSupervisorError, match='INTENT cardinality'): sup.continue_domain_consumption(lease)
    assert _inventory(rt) == held and not client.calls


@pytest.mark.parametrize('bad', ['foreign_turn', 'changed_projection', 'wrong_attestation', 'missing_attestation', 'untyped_attestation'])
def test_loader_and_retained_g1_failures_never_send_provider_rpc(tmp_path, monkeypatch, bad):
    rt, _, _, session, lease, _, _, sup, client, _, _, _ = _context(tmp_path, monkeypatch)
    actual = sup._claimed_adapter_factory
    def hostile(current, requested, loader, *, recovery):
        adapter = actual(current, requested, loader, recovery=recovery)
        if bad == 'foreign_turn':
            original = adapter.turn_input_loader
            adapter.turn_input_loader = lambda turn: original(dataclasses.replace(turn, turn_id='foreign-turn'))
        if bad == 'changed_projection':
            original = rt.jobs.project_cycle_domain_consumption
            def changed(*a, **kw):
                value = original(*a, **kw); return {**value, 'unexpected_body':'not the admitted projection'}
            monkeypatch.setattr(rt.jobs, 'project_cycle_domain_consumption', changed)
        if bad == 'wrong_attestation':
            adapter._start_receipts[session.generation.process_generation_id]['attestation'] = dataclasses.replace(session.observed, served_model='foreign')
        if bad == 'missing_attestation': adapter._start_receipts.clear()
        if bad == 'untyped_attestation': adapter._start_receipts[session.generation.process_generation_id]['attestation'] = dataclasses.asdict(session.observed)
        return adapter
    sup._claimed_adapter_factory = hostile
    with pytest.raises((ExecutiveOperatorSupervisorError, OperatorEffectUnknown)):
        sup.continue_domain_consumption(lease)
    assert not client.calls
    assert rt.attempts.get_attempt(session.attempt_id).status is AttemptStatus.CHECKPOINTED


def test_complete_prompt_exceeding_broker_limit_refuses_before_final(tmp_path, monkeypatch):
    rt, _, _, _, lease, _, _, sup, client, _, factories, _ = _context(tmp_path, monkeypatch)
    # Explicit negative transport-budget test; positive authority stays real Runtime.
    import control_plane.executive_operator_supervisor as module
    monkeypatch.setattr(module, '_MAX_OPERATOR_PROMPT_BYTES', 64)
    before = _inventory(rt)
    with pytest.raises(ExecutiveOperatorSupervisorError, match='broker limit'): sup.continue_domain_consumption(lease)
    assert _inventory(rt) == before and not client.calls and not factories


def test_unknown_initial_receipt_refuses_without_provider_or_new_credit(tmp_path, monkeypatch):
    rt, _, _, session, lease, _, _, sup, client, _, factories, _ = _context(tmp_path, monkeypatch)
    source = rt.events.get_event_by_command_id('ohf-op:turn:' + session.attempt_id)
    _append_negative_event(rt, source, command=source.command_id + ':negative-unknown',
        event_type='OPERATOR_OPERATION_EFFECT_UNKNOWN', payload={'operation_kind':'begin_turn','detail':'negative ambiguity'})
    before = _inventory(rt)
    with pytest.raises((ExecutiveOperatorSupervisorError, StateConflict)): sup.continue_domain_consumption(lease)
    assert _inventory(rt) == before and not client.calls and not factories
