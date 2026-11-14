"""Scoped native + Runtime Session Bridge target discovery via existing owners.

No provider run or live Session Bridge installation. Uses actual Runtime/OHF
fixture facts and exact Session Bridge target projectors with hermetic native
manager and dialogue-return records.
"""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from control_plane.executive_delegation_identity import derive_delegation_identity
from control_plane.executive_runtime import JobStatus
from control_plane.fabric_coordination_policy import CoordinationIdentity
from integrations.fabric_coordination_targets import (
    ScopedSessionTargetResolver as Resolver, ScopedTargetUnavailable,
)
from integrations.session_bridge.claude_native import ClaudeNativeTargetProjector
from integrations.session_bridge.runtime_owner import RuntimeFabricTargetProjector
from tests.test_fabric_coordination_composite import NATIVE, SESSION, fixture
from tests.test_session_bridge_claude_native import session
from tests.test_workspace_agent_runtime_binding import (
    target as workspace_target, physical as workspace_physical,
    source as workspace_source,
)


def _worker_projector(observation, owner, *, rotate_generation=False):
    runtime = observation._runtime
    members = tuple(p for p in owner.snapshot.participants
                    if type(p.identity) is CoordinationIdentity)
    by_operation = {}
    by_job = {}
    for member in members:
        job = runtime.jobs.get_job(member.identity.job_id)
        delegation = derive_delegation_identity(job)
        by_operation[delegation.operation_key] = (member, job, delegation)
        by_job[job.job_id] = delegation.operation_key

    def target_reader(operation_key):
        member, job, delegation = by_operation[operation_key]
        facts = runtime.current_harness_binding_source(member.identity.attempt_id)
        return workspace_target(
            root_job_id=delegation.root_job_id, job_id=job.job_id,
            attempt_id=member.identity.attempt_id,
            worker_id=member.identity.worker_id,
            session_ref=delegation.session_ref,
            harness_session_epoch_id=facts.session_epoch_id,
            harness_generation_number=facts.generation_number + int(rotate_generation),
            harness_provider=facts.provider,
            harness_provider_session_id=f"fixture-{member.identity.worker_id}",
        )

    def physical_reader(operation_key, job_id, attempt_id):
        member, job, delegation = by_operation[operation_key]
        return workspace_physical(
            root_job_id=delegation.root_job_id, job_id=job_id,
            attempt_id=attempt_id, worker_id=member.identity.worker_id,
            operation_key=operation_key,
        )

    jobs = [SimpleNamespace(job_id=p.identity.job_id, status=JobStatus.RUNNING,
                            current_attempt_id=p.identity.attempt_id)
            for p in members]
    return RuntimeFabricTargetProjector(
        runtime, job_reader=lambda: list(jobs),
        identity_resolver=lambda j: SimpleNamespace(operation_key=by_job[j.job_id]),
        target_reader=target_reader,
        dialogue_source_reader=lambda root_job_id: workspace_source(),
        physical_source_reader=physical_reader,
    )


def _resolver(observation, owner, port, *, caller=None, worker_targets=None):
    return Resolver(
        owner=observation,
        worker_targets=worker_targets or _worker_projector(observation, owner),
        native_targets=ClaudeNativeTargetProjector(port),
        caller=caller or NATIVE,
        topic_ref="schema",
        now=lambda: observation._runtime.store.now_ms() // 1000,
    )


def test_native_coo_discovers_only_exact_direct_worker_and_never_its_sibling(
    tmp_path, monkeypatch,
):
    observation, owner, port = fixture(tmp_path, monkeypatch)
    target_reader = _resolver(observation, owner, port)
    items = target_reader.visible_targets()
    assert len(items) == 1
    value = items[0]
    assert value["kind"] == "fabric_attempt"
    assert value["role"] == "worker"
    assert value["relation"] == "direct_parent_child"
    assert value["addressable"] is True
    resolved = target_reader.resolve(value["target_ref"])
    assert resolved.recipient == owner.snapshot.participants[0].identity
    assert resolved.valid_until <= owner.snapshot.valid_until
    assert not port.send_calls and not port.reconcile_calls


def test_worker_discovers_exact_native_parent_and_group_peer(tmp_path, monkeypatch):
    observation, owner, port = fixture(tmp_path, monkeypatch)
    caller = owner.snapshot.participants[0].identity
    reader = _resolver(observation, owner, port, caller=caller)
    visible = reader.visible_targets()
    assert {p["kind"] for p in visible} == {"claude", "fabric_attempt"}
    native_ref = next(p["target_ref"] for p in visible if p["kind"] == "claude")
    resolved = reader.resolve(native_ref)
    assert resolved.recipient == NATIVE
    assert resolved.role.value == "coo"
    assert resolved.relation == "direct_parent_child"
    assert SESSION not in str(visible)
    assert NATIVE.principal_ref not in str(visible)
    assert not port.send_calls


def test_same_owner_projector_drift_is_refused_not_rerouted(tmp_path, monkeypatch):
    observation, owner, port = fixture(tmp_path, monkeypatch)
    reader = _resolver(observation, owner, port, worker_targets=_worker_projector(
        observation, owner, rotate_generation=True,
    ))
    with pytest.raises(ScopedTargetUnavailable, match="SCOPED_TARGET_UNAVAILABLE"):
        reader.visible_targets()
    assert not port.send_calls


def test_old_native_ref_never_falls_back_to_new_generation(tmp_path, monkeypatch):
    observation, owner, port = fixture(tmp_path, monkeypatch)
    caller = owner.snapshot.participants[0].identity
    reader = _resolver(observation, owner, port, caller=caller)
    native_ref = next(t["target_ref"] for t in reader.visible_targets()
                      if t["kind"] == "claude")
    port.current[SESSION] = session(generation="gen-002")
    with pytest.raises(ScopedTargetUnavailable):
        reader.resolve(native_ref)
    assert not port.send_calls


def test_invented_or_nonexact_target_never_resolves(tmp_path, monkeypatch):
    observation, owner, port = fixture(tmp_path, monkeypatch)
    reader = _resolver(observation, owner, port)
    for reference in ("latest:claude", "claude:" + "0" * 64,
                      "fabric_attempt:" + "f" * 64, "worker-a"):
        with pytest.raises(ScopedTargetUnavailable):
            reader.resolve(reference)
    assert not port.send_calls


def test_stale_authenticated_caller_cannot_discover_foreign_peers(tmp_path, monkeypatch):
    observation, owner, port = fixture(tmp_path, monkeypatch)
    original = owner.snapshot.participants[0].identity
    forged = replace(original, binding_generation=original.binding_generation + 1)
    reader = _resolver(observation, owner, port, caller=forged)
    with pytest.raises(ScopedTargetUnavailable):
        reader.visible_targets()


def test_mid_read_membership_mutation_is_refused(tmp_path, monkeypatch):
    observation, owner, port = fixture(tmp_path, monkeypatch)
    reader = _resolver(observation, owner, port)
    original = observation.observe
    reads = [0]

    def mutate():
        result = original()
        reads[0] += 1
        if reads[0] == 1:
            people = owner.snapshot.participants
            owner.snapshot = replace(owner.snapshot, participants=(
                replace(people[0], coordination_group_ref="new-group"),
                *people[1:],
            ))
        return result

    monkeypatch.setattr(observation, "observe", mutate)
    with pytest.raises(ScopedTargetUnavailable):
        reader.visible_targets()
    assert reads[0] >= 2 and not port.send_calls


def test_no_public_command_sender_or_provider_session_parameters(tmp_path, monkeypatch):
    observation, owner, port = fixture(tmp_path, monkeypatch)
    reader = _resolver(observation, owner, port)
    result = reader.visible_targets()
    assert "send" not in vars(type(reader))
    assert "command" not in str(result).lower()
    assert "session_id" not in str(result).lower()
    assert "principal" not in str(result).lower()
    assert "worker_id" not in str(result).lower()


def test_foreign_management_session_never_becomes_discoverable(tmp_path, monkeypatch):
    from tests.test_session_bridge_claude_native import OTHER, Port
    observation, owner, _ = fixture(tmp_path, monkeypatch)
    port = Port([session(SESSION), session(OTHER, generation="gen-other",
                                       host_ref="ubuntu2")])
    # The composite source must use this *same* current management owner.
    from integrations.session_bridge.claude_native import ClaudeNativeTargetProjector
    observation._native_projector = ClaudeNativeTargetProjector(port)
    reader = _resolver(observation, owner, port,
                       caller=owner.snapshot.participants[0].identity)
    visible = reader.visible_targets()
    native_refs = [item for item in visible if item["kind"] == "claude"]
    assert len(native_refs) == 1
    hidden_ref = observation._native_projector._target(
        session(OTHER, generation="gen-other", host_ref="ubuntu2")).target_ref
    assert hidden_ref not in str(visible)
    with pytest.raises(ScopedTargetUnavailable):
        reader.resolve(hidden_ref)
    assert not port.send_calls


def test_stale_target_after_owner_refresh_refuses_instead_of_forwarding(
    tmp_path, monkeypatch,
):
    observation, owner, port = fixture(tmp_path, monkeypatch)
    reader = _resolver(observation, owner, port,
                       caller=owner.snapshot.participants[0].identity)
    native_ref = next(item["target_ref"] for item in reader.visible_targets()
                      if item["kind"] == "claude")
    original_resolve = reader._natives.resolve

    def rotating(target_ref):
        result = original_resolve(target_ref)
        port.current[SESSION] = session(generation="gen-after-read")
        return result

    monkeypatch.setattr(reader._natives, "resolve", rotating)
    with pytest.raises(ScopedTargetUnavailable):
        reader.resolve(native_ref)
    assert not port.send_calls and not port.reconcile_calls


def test_read_only_resolver_never_selects_expired_scope(tmp_path, monkeypatch):
    observation, owner, port = fixture(tmp_path, monkeypatch)
    reader = _resolver(observation, owner, port)
    reader._now = lambda: owner.snapshot.valid_until
    with pytest.raises(ScopedTargetUnavailable):
        reader.visible_targets()
    assert not port.send_calls


def test_physical_worker_target_rotation_during_discovery_refuses(
    tmp_path, monkeypatch,
):
    """The same worker identity must not inherit a changed dialogue carrier."""
    observation, owner, port = fixture(tmp_path, monkeypatch)
    reader = _resolver(observation, owner, port)
    original = reader._workers.list_targets
    calls = [0]

    def rotated_target():
        from dataclasses import replace as immutable_replace
        items = original()
        calls[0] += 1
        if calls[0] >= 2:
            return [immutable_replace(item, target_ref="fabric_attempt:" + "f" * 64)
                    for item in items]
        return items

    monkeypatch.setattr(reader._workers, "list_targets", rotated_target)
    with pytest.raises(ScopedTargetUnavailable):
        reader.visible_targets()
    assert calls[0] >= 2
    assert not port.send_calls and not port.reconcile_calls
