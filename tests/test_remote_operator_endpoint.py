"""Claim-to-endpoint composition, with no credentials or provider execution."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from control_plane import remote_attempt_transport as rt
from control_plane.executive_runtime import Runtime
from control_plane.operator_harness_contract import (
    CapabilityManifest, NativeHelperPolicy, OperationId, RequestedExecutionProfile,
    WorkspaceIdentity,
)
from control_plane.remote_codex_operator_adapter import codex_remote_capabilities
from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
from test_remote_attempt_transport import HOST_A, HOST_B, WORKER, QUOTA, _host_binding, _join


@pytest.fixture
def case(tmp_path, monkeypatch, request):
    provider = getattr(request, "param", "codex")
    runtime = Runtime.at(tmp_path / 'runtime')
    runtime.workers.register_worker(WORKER, provider=provider, account_label='fixture',
        worker_type='fixture', capabilities=['research'], quota_classes={QUOTA: {
            'capabilities': ['research'], 'metadata': {'capacity_join': _join()}}})
    job = runtime.jobs.create_job('exact operator endpoint', requested_authorities=['READ'],
        constraints={'eligible_quota_classes': [QUOTA]}, attempt_limit=1)
    lease = runtime.attempts.claim_job(job.job_id, worker_id=WORKER, quota_class=QUOTA,
        lease_owner='endpoint-fixture')
    workspace = tmp_path / 'workspace'; workspace.mkdir(); info = workspace.stat()
    requested = RequestedExecutionProfile(WORKER, 'claude' if provider == 'claude' else 'openai-codex', 'fixture-exact-model',
        'claude-agent-sdk' if provider == 'claude' else 'codex-app-server', 'a' * 64, '0.147.0',
        WorkspaceIdentity(str(workspace), 'b' * 40, info.st_dev, info.st_ino, info.st_uid, info.st_gid),
        'read-only', 'never', 'disabled', CapabilityManifest(),
        NativeHelperPolicy.DISABLED, lease.attempt.authority_policy_hash,
        expected_config_digest='e' * 64)
    flat = _host_binding(tmp_path)
    calls = []
    async def no_connection(client):
        calls.append(client.identity)
        raise AssertionError('No network is allowed in resolution tests')
    monkeypatch.setattr(RemoteWorkerBrokerClient, '_open_connection', no_connection)
    return runtime, job, lease, requested, flat, calls


def binding(case, **changes):
    runtime, job, lease, requested, flat, calls = case
    values = dict(host_ref=flat.host_ref, worker_id=flat.worker_id,
        transport=flat.transport, worker_source_config_digest='c' * 64,
        provider=requested.provider, harness_kind=requested.harness_kind,
        harness_binary_digest=requested.harness_binary_digest,
        harness_version=requested.harness_version,
        expected_config_digest=requested.expected_config_digest,
        workspace=requested.workspace, capabilities=codex_remote_capabilities())
    if requested.provider == "claude":
        values["capabilities"] = dataclasses.replace(values["capabilities"],
            supports_native_resume=False, supported_optional_operations=())
    values.update(changes)
    return rt.RemoteOperatorHostBinding(**values)


def test_runtime_allocated_generation_is_bound_before_remote_start(case):
    runtime, job, lease, requested, flat, calls = case
    adapter = rt.build_claimed_remote_operator_factory(
        runtime, lambda h, w: binding(case)
    )(lease.attempt, requested, lambda t: 'bounded', recovery=False)
    sealed = runtime.operator_harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        requested=requested,
    )
    operation = OperationId(f'ohf-op:start:{sealed.attempt_id}')
    epoch, generation = runtime.operator_harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        operation_id=operation,
    )
    # The fixture's network trap proves validation reached the transport only
    # after the Runtime-issued pair was accepted.  Before the repair this call
    # refuses earlier with payload_identity_override instead.
    with pytest.raises(AssertionError, match='No network is allowed'):
        adapter.start_session(
            operation_id=operation,
            requested=requested,
            epoch=epoch,
            generation=generation,
        )
    assert adapter.client.bound_payload_identity == {
        'session_epoch_id': epoch.session_epoch_id,
        'process_generation_id': generation.process_generation_id,
    }
    assert calls == [adapter.client.identity]


def test_selected_endpoint_uses_existing_transport_and_no_network(case):
    runtime, job, lease, requested, flat, calls = case
    reads = []
    def source(host, worker):
        reads.append((host, worker)); return binding(case)
    factory = rt.build_claimed_remote_operator_factory(runtime, source)
    adapter = factory(lease.attempt, requested, lambda turn: 'bounded', recovery=False)
    assert adapter.client.identity == dict(host_ref=HOST_A, job_id=job.job_id,
        attempt_id=lease.attempt.attempt_id, worker_id=WORKER, operation_id=lease.attempt.attempt_id)
    assert adapter.client.binding is flat.transport
    assert 'ohf-start' in adapter.client.allowed_operations
    assert 'start' not in adapter.client.allowed_operations
    assert 'ohf-resume' not in adapter.client.allowed_operations
    assert reads == [(HOST_A, WORKER)] and calls == []


@pytest.mark.parametrize('field,value', [
    ('host_ref', HOST_B), ('worker_id', 'another-worker'),
    ('worker_source_config_digest', 'f' * 64), ('provider', 'claude'),
    ('harness_kind', 'claude-agent-sdk'), ('harness_binary_digest', 'f' * 64),
    ('harness_version', 'different'), ('expected_config_digest', 'f' * 64),
])
def test_stale_or_wrong_host_binding_refuses_before_transport(case, field, value):
    runtime, job, lease, requested, flat, calls = case
    with pytest.raises(rt.RemoteAttemptTransportError):
        factory = rt.build_claimed_remote_operator_factory(runtime,
            lambda h, w: binding(case, **{field: value}))
        factory(lease.attempt, requested, lambda t: '', recovery=False)
    assert calls == []


def test_binding_source_cannot_repoint_a_claim_during_resolution(case):
    runtime, job, lease, requested, flat, calls = case
    def moved(host, worker):
        runtime.jobs.cancel_job(job.job_id)
        return binding(case)
    factory = rt.build_claimed_remote_operator_factory(runtime, moved)
    with pytest.raises(rt.RemoteAttemptTransportError):
        factory(lease.attempt, requested, lambda t: '', recovery=False)
    assert calls == []


def test_binding_error_is_sanitized_and_never_falls_back(case):
    runtime, job, lease, requested, flat, calls = case
    reads = []
    def broken(host, worker):
        reads.append(worker)
        raise ValueError('private credential-path diagnostic')
    factory = rt.build_claimed_remote_operator_factory(runtime, broken)
    with pytest.raises(rt.RemoteAttemptTransportError) as error:
        factory(lease.attempt, requested, lambda t: '', recovery=False)
    assert error.value.code == 'HOST_BINDING_UNAVAILABLE'
    assert 'private' not in str(error.value) and reads == [WORKER] and calls == []


@pytest.mark.parametrize('field,value', [('worker_id', 'wrong-worker'),
    ('authority_policy_hash', 'f' * 64), ('fence_generation', 999)])
def test_caller_cannot_substitute_claim_identity(case, field, value):
    runtime, job, lease, requested, flat, calls = case
    reads = []
    factory = rt.build_claimed_remote_operator_factory(runtime,
        lambda h, w: reads.append(w) or binding(case))
    with pytest.raises(rt.RemoteAttemptTransportError):
        factory(dataclasses.replace(lease.attempt, **{field: value}), requested,
            lambda t: '', recovery=False)
    assert reads == [] and calls == []


@pytest.mark.parametrize('recovery', [None, 0, 1, 'false'])
def test_recovery_mode_is_not_coerced(case, recovery):
    runtime, job, lease, requested, flat, calls = case
    factory = rt.build_claimed_remote_operator_factory(runtime, lambda h, w: binding(case))
    with pytest.raises(rt.RemoteAttemptTransportError):
        factory(lease.attempt, requested, lambda t: '', recovery=recovery)
    assert calls == []


@pytest.mark.parametrize('case', ['codex', 'claude'], indirect=True)
def test_recovery_uses_persisted_generation_and_never_allows_start(case):
    runtime, job, lease, requested, flat, calls = case
    sealed = runtime.operator_harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        requested=requested,
    )
    start = OperationId(f'ohf-op:start:{sealed.attempt_id}')
    epoch, generation = runtime.operator_harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=lease.lease_token,
        operation_id=start,
    )
    factory = rt.build_claimed_remote_operator_factory(
        runtime, lambda h, w: binding(case)
    )
    adapter = factory(sealed, requested, lambda t: '', recovery=True)
    expected = {
        'session_epoch_id': epoch.session_epoch_id,
        'process_generation_id': generation.process_generation_id,
    }
    assert adapter.client.bound_payload_identity == expected
    assert 'ohf-start' not in adapter.client.allowed_operations
    assert 'ohf-validate' not in adapter.client.allowed_operations
    assert ('ohf-resume' in adapter.client.allowed_operations) == (
        requested.provider == 'openai-codex'
    )
    assert adapter.client.identity['attempt_id'] == lease.attempt.attempt_id
    from control_plane.remote_worker_transport import TransportError
    with pytest.raises(TransportError):
        adapter.client.request_sync('ohf-start', {})
    with pytest.raises(AssertionError, match='No network is allowed'):
        adapter.reconcile(generation)
    assert calls == [adapter.client.identity]
    calls.clear()
    with pytest.raises(rt.RemoteAttemptTransportError):
        factory(
            sealed,
            dataclasses.replace(requested, requested_model='replacement'),
            lambda t: '',
            recovery=True,
        )
    runtime.jobs.cancel_job(job.job_id)
    cancelled = runtime.attempts.get_attempt(sealed.attempt_id)
    recovery = factory(cancelled, requested, lambda t: '', recovery=True)
    assert recovery.client.bound_payload_identity == expected
    assert 'ohf-cancel' in recovery.client.allowed_operations
    with pytest.raises(AssertionError, match='No network is allowed'):
        recovery.cancel(
            generation,
            reason='fixture cancellation',
            operation_id=OperationId(f'ohf-op:recover-cancel:{sealed.attempt_id}'),
        )
    assert calls == [recovery.client.identity]


@pytest.mark.parametrize('case', ['codex'], indirect=True)
def test_recovery_resume_rotates_to_new_generation_scoped_client(case):
    runtime, job, lease, requested, flat, calls = case
    requested = dataclasses.replace(requested, expected_config_digest='d' * 64)
    from control_plane.executive_operator_harness_port import ExecutiveOperatorHarnessPort
    from control_plane.operator_harness_contract import ProviderSessionHandoff
    from control_plane.operator_harness_orchestrator import (
        OperatorEffectUnknown,
        OperatorHarnessOrchestrator,
    )
    from test_ohf_p1b_runtime_orchestrator import FakeAdapter

    seed = FakeAdapter(requested)
    port = ExecutiveOperatorHarnessPort(runtime, lease)
    seed_orchestrator = OperatorHarnessOrchestrator(
        port,
        seed,
        attestation_reader=lambda item, generation: item.observed_attestation(
            generation
        ),
    )
    session = seed_orchestrator.start_attempt(
        attempt_id=lease.attempt.attempt_id,
        requested=requested,
        operation_id=OperationId(f'ohf-op:start:{lease.attempt.attempt_id}'),
    )
    seed_orchestrator.reconcile(session)

    current = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    factory = rt.build_claimed_remote_operator_factory(
        runtime,
        lambda h, w: binding(
            case, expected_config_digest=requested.expected_config_digest
        ),
    )
    adapter = factory(current, requested, lambda t: '', recovery=True)
    g1_client = adapter.client
    g1_identity = dict(g1_client.bound_payload_identity)
    assert g1_identity == {
        'session_epoch_id': session.epoch.session_epoch_id,
        'process_generation_id': session.generation.process_generation_id,
    }

    resumed = OperatorHarnessOrchestrator(
        port,
        adapter,
        attestation_reader=lambda item, generation: item.observed_attestation(
            generation
        ),
    )
    operation = OperationId(f'ohf-op:resume:{lease.attempt.attempt_id}')
    with pytest.raises(OperatorEffectUnknown, match='resume_session'):
        resumed.resume(
            session,
            operation_id=operation,
            handoff=ProviderSessionHandoff('S1', WORKER),
        )

    g2 = runtime.operator_harness.current_writer_generation(session.epoch)
    assert g2.generation_number == 2
    assert adapter.client is not g1_client
    assert g1_client.bound_payload_identity == g1_identity
    assert adapter.client.bound_payload_identity == {
        'session_epoch_id': session.epoch.session_epoch_id,
        'process_generation_id': g2.process_generation_id,
    }
    assert calls == [adapter.client.identity]


@pytest.mark.parametrize('case', ['codex', 'claude'], indirect=True)
def test_both_provider_realms_keep_exact_identity_without_account_name_inference(case):
    runtime, job, lease, requested, flat, calls = case
    # WORKER deliberately looks Codex-specific even for the Claude fixture.
    adapter = rt.build_claimed_remote_operator_factory(runtime, lambda h, w: binding(case))(
        lease.attempt, requested, lambda t: '', recovery=False)
    assert adapter.client.identity['worker_id'] == WORKER
    assert adapter.describe_capabilities().supports_native_resume == (requested.provider == 'openai-codex')
    assert calls == []


def test_remote_binding_constructor_is_not_an_account_or_profile_fallback(case):
    runtime, job, lease, requested, flat, calls = case
    with pytest.raises(rt.RemoteAttemptTransportError):
        rt.build_claimed_remote_operator_factory(runtime, lambda h, w: None)(
            lease.attempt, requested, lambda t: '', recovery=False)
    with pytest.raises(rt.RemoteAttemptTransportError):
        binding(case, provider='claude', harness_kind='claude-agent-sdk')
    assert calls == []


def test_sealed_attempt_cannot_reacquire_fresh_start_capability(case):
    runtime, job, lease, requested, flat, calls = case
    sealed = runtime.operator_harness.seal_operator_harness_attempt(lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token,
        requested=requested)
    reads = []
    factory = rt.build_claimed_remote_operator_factory(runtime,
        lambda h, w: reads.append(w) or binding(case))
    with pytest.raises(rt.RemoteAttemptTransportError, match='CLAIM_NOT_LAUNCHABLE'):
        factory(sealed, requested, lambda t: '', recovery=False)
    assert reads == [] and calls == []


def test_heartbeat_does_not_invalidate_an_unchanged_endpoint(case):
    runtime, job, lease, requested, flat, calls = case
    def source(host, worker):
        runtime.attempts.heartbeat_attempt(lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token)
        return binding(case)
    adapter = rt.build_claimed_remote_operator_factory(runtime, source)(
        lease.attempt, requested, lambda t: '', recovery=False)
    assert adapter.client.identity['worker_id'] == WORKER and calls == []


@pytest.mark.parametrize('field,value', [('supports_native_fork', True),
    ('supports_native_resume', 'true'), ('supports_structured_events', False)])
def test_unqualified_capability_claim_never_constructs_transport(case, field, value):
    runtime, job, lease, requested, flat, calls = case
    capabilities = dataclasses.replace(codex_remote_capabilities(), **{field: value})
    with pytest.raises(rt.RemoteAttemptTransportError):
        factory = rt.build_claimed_remote_operator_factory(runtime,
            lambda h, w: binding(case, capabilities=capabilities))
        factory(lease.attempt, requested, lambda t: '', recovery=False)
    assert calls == []
