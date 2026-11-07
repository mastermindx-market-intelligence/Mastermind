"""Claimed native remote transport uses original Runtime bindings; no provider I/O."""
from dataclasses import replace

import pytest

from control_plane import remote_attempt_transport as rt
from control_plane.native_conversation_result import DSH_NATIVE_RESULT_CONTRACT
from control_plane.operator_harness_contract import HarnessAdapterCapabilities, OperationId
from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
from test_dsh_native_runtime_result import _started_native, _turn
from test_dsh_native_runtime_resume import _release, _resume
from test_remote_attempt_transport import HOST_A, _host_binding, _join
from test_remote_operator_endpoint import case


def _remote(f, tmp_path, monkeypatch):
    flat = _host_binding(tmp_path, worker_id=f.dispatch.attempt.worker_id)
    requested = f.requested
    caps = HarnessAdapterCapabilities("1.0",
        ("describe_capabilities", "validate_requested_profile", "start_session", "begin_turn",
         "read_events", "interrupt_turn", "collect_candidate_result", "graceful_stop", "cancel", "reconcile"),
        ("resume_session",), True, False, False, False, False, False, False, True)
    # Exact interface version from the implementation, without constructing a process.
    from integrations.deepseek_harness.operator_adapter import NativeOperatorAdapter
    caps = replace(caps, interface_version=NativeOperatorAdapter.interface_version)
    host = rt.RemoteOperatorHostBinding(HOST_A, requested.worker_id, flat.transport, "c"*64,
        requested.provider, requested.harness_kind, requested.harness_binary_digest,
        requested.harness_version, requested.expected_config_digest, requested.workspace, caps)
    calls = []
    async def no_connection(client):
        calls.append(client.identity)
        raise AssertionError("native constructor must not issue network I/O")
    monkeypatch.setattr(RemoteWorkerBrokerClient, "_open_connection", no_connection)
    return host, calls


def _fresh(tmp_path, monkeypatch):
    workspace = tmp_path/"workspace"
    workspace.mkdir()
    f = _started_native(tmp_path, monkeypatch, claim_only=True,
                        capacity_join=_join(), worktree=workspace)
    host, calls = _remote(f, tmp_path, monkeypatch)
    return f, host, calls


def test_native_claim_selects_original_workspace_transport_and_result_contract(tmp_path, monkeypatch):
    f, host, calls = _fresh(tmp_path, monkeypatch)
    reads = []
    def source(h, w):
        reads.append((h, w))
        return host
    identity = rt.build_claimed_remote_workspace_identity_source(f.runtime, source)
    assert identity(f.dispatch.attempt, f.job) == f.requested.workspace
    adapter = rt.build_claimed_remote_operator_factory(f.runtime, source)(
        f.dispatch.attempt, f.requested, lambda _: "original native message", recovery=False)
    assert adapter.result_contract == DSH_NATIVE_RESULT_CONTRACT
    assert adapter.client.binding is host.transport
    assert adapter.client.identity["job_id"] == f.job.job_id
    assert adapter.client.identity["attempt_id"] == f.dispatch.attempt.attempt_id
    assert "ohf-start" in adapter.client.allowed_operations
    assert "ohf-resume" not in adapter.client.allowed_operations
    assert reads == [(HOST_A, f.dispatch.attempt.worker_id)]*2
    assert calls == []


@pytest.mark.parametrize("surface", ["workspace", "adapter"])
@pytest.mark.parametrize("change", ["child", "root", "claim"])
def test_native_binding_movement_during_host_lookup_refuses(tmp_path, monkeypatch, surface, change):
    f, host, calls = _fresh(tmp_path, monkeypatch)
    reads = []
    def source(*_):
        reads.append(True)
        if change == "claim":
            f.runtime.jobs.cancel_job(f.job.job_id)
        else:
            from control_plane.executive_runtime import _json_dumps
            job = f.runtime.jobs.get_job(f.job.job_id if change == "child" else f.root.job_id)
            changed = dict(job.constraints)
            changed["model" if change == "child" else "operator_model"] = "moved-model"
            with f.runtime.store.transaction() as connection:
                connection.execute("UPDATE jobs SET constraints_json=? WHERE job_id=?",
                                   (_json_dumps(changed), job.job_id))
        return host
    with pytest.raises(rt.RemoteAttemptTransportError):
        if surface == "workspace":
            rt.build_claimed_remote_workspace_identity_source(f.runtime, source)(f.dispatch.attempt, f.job)
        else:
            rt.build_claimed_remote_operator_factory(f.runtime, source)(
                f.dispatch.attempt, f.requested, lambda _: "", recovery=False)
    assert reads == [True] and calls == []


def test_native_creator_cannot_receive_legacy_result_codec(tmp_path, monkeypatch):
    f, host, calls = _fresh(tmp_path, monkeypatch)
    reads = []
    wrong = replace(f.requested, provider="openai-codex", harness_kind="codex-app-server")
    with pytest.raises(rt.RemoteAttemptTransportError) as error:
        rt.build_claimed_remote_operator_factory(f.runtime, lambda *args: reads.append(args) or host)(
            f.dispatch.attempt, wrong, lambda _: "", recovery=False)
    assert error.value.code == "CLAIM_MISMATCH"
    assert reads == [] and calls == []


def test_native_profile_cannot_promote_unbound_legacy_job(case):
    runtime, job, lease, requested, flat, calls = case
    requested = replace(requested, provider="acp", harness_kind="dsh-native-web-acp")
    reads = []
    with pytest.raises(rt.RemoteAttemptTransportError) as error:
        rt.build_claimed_remote_operator_factory(runtime, lambda *args: reads.append(args))(
            lease.attempt, requested, lambda _: "", recovery=False)
    assert error.value.code == "CLAIM_MISMATCH"
    assert reads == [] and calls == []


@pytest.mark.parametrize("surface", ["workspace", "adapter"])
def test_native_creator_refuses_legacy_host_tuple(tmp_path, monkeypatch, surface):
    f, host, calls = _fresh(tmp_path, monkeypatch)
    wrong = replace(host, provider="openai-codex", harness_kind="codex-app-server")
    with pytest.raises(rt.RemoteAttemptTransportError) as error:
        if surface == "workspace":
            rt.build_claimed_remote_workspace_identity_source(f.runtime, lambda *args: wrong)(
                f.dispatch.attempt, f.job)
        else:
            rt.build_claimed_remote_operator_factory(f.runtime, lambda *args: wrong)(
                f.dispatch.attempt, f.requested, lambda _: "", recovery=False)
    assert error.value.code == "HOST_BINDING_MISMATCH"
    assert calls == []


@pytest.mark.parametrize("resumed", [False, True])
def test_native_recovery_binds_actual_runtime_g1_or_g2_without_start(tmp_path, monkeypatch, resumed):
    workspace = tmp_path/"workspace"
    workspace.mkdir()
    f = _started_native(tmp_path, monkeypatch, capacity_join=_join(), worktree=workspace)
    turn, observation = _turn(f)
    ref = f.runtime.operator_harness.seal_native_conversation_result(
        turn=turn, observation=observation, **f.lease)
    if resumed:
        _release(f)
        f = _resume(f)
    host, calls = _remote(f, tmp_path, monkeypatch)
    current = f.runtime.attempts.get_attempt(f.epoch.attempt_id)
    adapter = rt.build_claimed_remote_operator_factory(f.runtime, lambda *args: host)(
        current, f.requested, lambda _: "", recovery=True)
    assert adapter.result_contract == DSH_NATIVE_RESULT_CONTRACT
    assert adapter.client.bound_payload_identity == dict(
        session_epoch_id=f.epoch.session_epoch_id,
        process_generation_id=f.generation.process_generation_id)
    assert f.generation.generation_number == (2 if resumed else 1)
    assert "ohf-start" not in adapter.client.allowed_operations
    assert "ohf-validate" not in adapter.client.allowed_operations
    assert "ohf-resume" in adapter.client.allowed_operations
    assert f.runtime.operator_harness.native_conversation_result(
        attempt_id=turn.attempt_id, reference=ref)["turn"]["turn_id"] == turn.turn_id
    assert calls == []


def test_native_g2_does_not_relax_original_g3_allocation_fence(tmp_path, monkeypatch):
    workspace = tmp_path/"workspace"
    workspace.mkdir()
    f = _started_native(tmp_path, monkeypatch, capacity_join=_join(), worktree=workspace)
    turn, observation = _turn(f)
    f.runtime.operator_harness.seal_native_conversation_result(turn=turn, observation=observation, **f.lease)
    _release(f)
    f = _resume(f)
    from control_plane.executive_runtime import StateConflict
    with pytest.raises(StateConflict):
        f.runtime.operator_harness.reserve_same_epoch_resume(
            epoch=f.epoch, old_generation=f.generation,
            operation_id=OperationId("ohf-op:forbidden-third-native-generation"), **f.lease)


@pytest.mark.parametrize("change", ["model", "binary", "version", "path", "base"])
def test_native_request_cannot_substitute_bound_execution_facts(tmp_path, monkeypatch, change):
    f, host, calls = _fresh(tmp_path, monkeypatch)
    requested = f.requested
    if change == "model":
        requested = replace(requested, requested_model="different-model")
    elif change == "binary":
        requested = replace(requested, harness_binary_digest="f"*64)
    elif change == "version":
        requested = replace(requested, harness_version="different-version")
    else:
        workspace = replace(requested.workspace, **({"workspace_path": "/another/worktree"}
                             if change == "path" else {"base_sha": "b"*40}))
        requested = replace(requested, workspace=workspace)
    reads = []
    # A host/request pair agreeing with each other still cannot replace Runtime.
    host = replace(host, **{key: getattr(requested, key) for key in (
        "harness_binary_digest", "harness_version", "workspace")})
    with pytest.raises(rt.RemoteAttemptTransportError) as error:
        rt.build_claimed_remote_operator_factory(f.runtime, lambda *args: reads.append(args) or host)(
            f.dispatch.attempt, requested, lambda _: "", recovery=False)
    assert error.value.code == "CLAIM_MISMATCH"
    assert reads == [] and calls == []


def test_native_fresh_quota_movement_during_host_read_refuses(tmp_path, monkeypatch):
    f, host, calls = _fresh(tmp_path, monkeypatch)
    def moved(*_):
        with f.runtime.store.transaction() as connection:
            connection.execute("UPDATE worker_quota_classes SET model=? WHERE worker_id=? AND quota_class=?",
                               ("withdrawn-model", f.dispatch.attempt.worker_id, f.dispatch.attempt.quota_class))
        return host
    with pytest.raises(rt.RemoteAttemptTransportError) as error:
        rt.build_claimed_remote_operator_factory(f.runtime, moved)(
            f.dispatch.attempt, f.requested, lambda _: "", recovery=False)
    assert error.value.code == "STATE_MOVED"
    assert calls == []


def test_native_containment_constructor_keeps_original_identity_after_quota_model_withdrawal(tmp_path, monkeypatch):
    workspace = tmp_path/"workspace"
    workspace.mkdir()
    f = _started_native(tmp_path, monkeypatch, capacity_join=_join(), worktree=workspace)
    host, calls = _remote(f, tmp_path, monkeypatch)
    with f.runtime.store.transaction() as connection:
        connection.execute("UPDATE worker_quota_classes SET model=? WHERE worker_id=? AND quota_class=?",
                           ("withdrawn-model", f.dispatch.attempt.worker_id, f.dispatch.attempt.quota_class))
    current = f.runtime.attempts.get_attempt(f.epoch.attempt_id)
    adapter = rt.build_claimed_remote_operator_factory(f.runtime, lambda *_: host)(
        current, f.requested, lambda _: "", recovery=True)
    assert adapter.result_contract == DSH_NATIVE_RESULT_CONTRACT
    assert "ohf-start" not in adapter.client.allowed_operations
    assert adapter.client.bound_payload_identity["process_generation_id"] == f.generation.process_generation_id
    assert calls == []
