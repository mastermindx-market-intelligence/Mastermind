"""Worker-only and native-only peer discovery using incumbent owner records.

No synthetic fallback from mixed membership, no live provider call or worker
launch, no new message service. These tests prove a topology can be empty in
one modality without disabling already-admitted peers in the other.
"""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from control_plane.fabric_coordination_policy import (
    CoordinationNativeIdentity, CoordinationParticipant, CoordinationRole,
    CoordinationSnapshot,
)
from integrations.fabric_coordination_native import NativeCoordinationObservationSource
from integrations.fabric_coordination_single import (
    SingleDomainCoordinationObservationSource as Single,
    SingleDomainCoordinationUnavailable,
)
from integrations.fabric_coordination_targets import (
    ScopedSessionTargetResolver, ScopedTargetUnavailable,
)
from integrations.session_bridge.claude_native import ClaudeNativeTargetProjector
from tests.test_fabric_coordination_runtime import setup as runtime_setup
from tests.test_fabric_coordination_targets import _worker_projector
from tests.test_session_bridge_claude_native import (
    OTHER, SESSION, Port, session,
)

NOW = 1000
FIRST = CoordinationNativeIdentity(SESSION, "gen-001", "m2studio", "principal-one")
SECOND = CoordinationNativeIdentity(OTHER, "gen-002", "ubuntu1", "principal-two")


def native_fixture():
    members = (
        CoordinationParticipant(
            FIRST, CoordinationRole.PROJECT_CEO, "tenant", "portfolio",
            "project-a", "program-1",
        ),
        CoordinationParticipant(
            SECOND, CoordinationRole.PROJECT_CEO, "tenant", "portfolio",
            "project-b", "program-1",
        ),
    )
    owner = [CoordinationSnapshot("native-owner", NOW, NOW + 25, members)]
    port = Port([session(SESSION), session(OTHER, generation="gen-002", host_ref="ubuntu1")])
    projector = ClaudeNativeTargetProjector(port)
    principals = {
        (SESSION, "m2studio"): FIRST.principal_ref,
        (OTHER, "ubuntu1"): SECOND.principal_ref,
    }
    source = NativeCoordinationObservationSource(
        projector=projector, membership_reader=lambda: owner[0],
        principal_reader=lambda sid, host: principals.get((sid, host), "missing"),
        now=lambda: NOW + 1,
    )
    single = Single(
        membership_reader=lambda: owner[0], native_source=source,
        now=lambda: NOW + 1,
    )
    return owner, port, single, projector


def worker_fixture(tmp_path, monkeypatch):
    seed, _, _, owner, runtime_source = runtime_setup(tmp_path, monkeypatch)
    single = Single(membership_reader=lambda: owner.snapshot,
                    runtime_source=runtime_source, now=runtime_source.now)
    projector = _worker_projector(SimpleNamespace(_runtime=seed.runtime), owner)
    return seed, owner, single, projector


def worker_reader(owner, single, projector):
    return ScopedSessionTargetResolver(
        owner=single, worker_targets=projector,
        caller=owner.snapshot.participants[0].identity,
        topic_ref="schema", now=single._now,
    )


def native_reader(single, projector, *, caller=FIRST):
    return ScopedSessionTargetResolver(
        owner=single, native_targets=projector,
        caller=caller, topic_ref="schema", now=single._now,
    )


def test_worker_peers_are_visible_without_any_native_management_session(tmp_path, monkeypatch):
    _, owner, single, projector = worker_fixture(tmp_path, monkeypatch)
    observed = single.observe()
    assert observed.native_ids == ()
    assert len(observed.worker_peer_refs) == 2
    reader = worker_reader(owner, single, projector)
    targets = reader.visible_targets()
    assert len(targets) == 1
    assert targets[0]["kind"] == "fabric_attempt"
    assert targets[0]["relation"] == "task_group_worker_peer"
    exact = reader.resolve(targets[0]["target_ref"])
    assert exact.recipient == owner.snapshot.participants[1].identity
    assert exact.valid_until <= owner.snapshot.valid_until


def test_native_ceos_are_visible_without_running_executive_attempts():
    owner, port, single, projector = native_fixture()
    evidence = single.observe()
    assert evidence.worker_peer_refs == ()
    assert set(evidence.native_ids) == {FIRST, SECOND}
    reader = native_reader(single, projector)
    targets = reader.visible_targets()
    assert len(targets) == 1
    assert targets[0]["kind"] == "claude"
    assert targets[0]["relation"] == "portfolio_ceo_peer"
    assert targets[0]["role"] == "project_ceo"
    exact = reader.resolve(targets[0]["target_ref"])
    assert exact.recipient == SECOND
    assert not port.send_calls and not port.reconcile_calls


def test_worker_only_refuses_native_member_injected_after_scope_selection(tmp_path, monkeypatch):
    _, owner, single, _ = worker_fixture(tmp_path, monkeypatch)
    native = CoordinationParticipant(
        FIRST, CoordinationRole.PROJECT_CEO, "tenant", "portfolio",
        "project-a", "program-1",
    )
    owner.snapshot = replace(
        owner.snapshot, participants=(*owner.snapshot.participants, native))
    with pytest.raises(SingleDomainCoordinationUnavailable):
        single.observe()


def test_native_only_refuses_runtime_member_injected_after_scope_selection():
    owner, port, single, _ = native_fixture()
    from control_plane.fabric_coordination_policy import CoordinationIdentity
    worker = CoordinationParticipant(
        CoordinationIdentity("JOB-1", "ATT-1", "worker", "bind-1", 1),
        CoordinationRole.WORKER, "tenant", "portfolio", "project-a",
        "program-1", workstream_ref="ws", coordination_group_ref="g",
    )
    owner[0] = replace(owner[0], participants=(*owner[0].participants, worker))
    with pytest.raises(SingleDomainCoordinationUnavailable):
        single.observe()
    assert not port.send_calls


def test_native_grant_revocation_during_read_refuses_and_does_not_reuse_old_peer():
    owner, port, single, projector = native_fixture()
    initial = single._membership
    calls = [0]

    def revoked_scope():
        value = initial()
        calls[0] += 1
        if calls[0] == 2:
            owner[0] = replace(value, participants=(
                value.participants[0],
                replace(value.participants[1], active=False),
            ))
        return value

    single._membership = revoked_scope
    with pytest.raises(ScopedTargetUnavailable):
        native_reader(single, projector).visible_targets()
    assert not port.send_calls


def test_worker_runtime_generation_drift_refuses(tmp_path, monkeypatch):
    _, owner, single, _ = worker_fixture(tmp_path, monkeypatch)
    members = owner.snapshot.participants
    owner.snapshot = replace(owner.snapshot, participants=(
        members[0],
        replace(members[1], identity=replace(
            members[1].identity,
            binding_generation=members[1].identity.binding_generation + 1,
        )),
    ))
    with pytest.raises(SingleDomainCoordinationUnavailable):
        single.observe()


def test_native_session_rotated_between_attestations_refuses():
    owner, port, single, projector = native_fixture()
    original = single._native.observe
    reads = [0]

    def rotated():
        result = original()
        reads[0] += 1
        if reads[0] == 1:
            port.current[OTHER] = session(
                OTHER, generation="gen-003", host_ref="ubuntu1",
            )
        return result

    single._native.observe = rotated
    with pytest.raises(SingleDomainCoordinationUnavailable):
        single.observe()
    # The second native observation refuses before returning a receipt.
    assert reads[0] >= 1 and not port.send_calls


def test_native_peer_target_is_not_retargeted_after_session_rotation():
    _, port, single, projector = native_fixture()
    reader = native_reader(single, projector)
    target = reader.visible_targets()[0]["target_ref"]
    port.current[OTHER] = session(OTHER, generation="gen-003", host_ref="ubuntu1")
    with pytest.raises(ScopedTargetUnavailable):
        reader.resolve(target)
    assert not port.send_calls


def test_missing_native_projector_not_allowed_for_mixed_owner(tmp_path, monkeypatch):
    from tests.test_fabric_coordination_composite import fixture
    mixed, owner, port = fixture(tmp_path, monkeypatch)
    with pytest.raises(TypeError):
        ScopedSessionTargetResolver(
            owner=mixed, worker_targets=_worker_projector(mixed, owner),
            caller=owner.snapshot.participants[0].identity,
            topic_ref="schema", now=lambda:NOW,
        )


def test_single_owner_type_pairing_rejects_opposite_projector(tmp_path, monkeypatch):
    _, owner, single, projector = worker_fixture(tmp_path, monkeypatch)
    port = Port()
    with pytest.raises(TypeError):
        ScopedSessionTargetResolver(
            owner=single, native_targets=ClaudeNativeTargetProjector(port),
            caller=owner.snapshot.participants[0].identity,
            topic_ref="schema", now=single._now,
        )


def test_absent_or_both_sources_refused_at_construction(tmp_path, monkeypatch):
    _, owner, single, _ = worker_fixture(tmp_path, monkeypatch)
    with pytest.raises(TypeError):
        Single(membership_reader=lambda: owner.snapshot, now=single._now)
    with pytest.raises(TypeError):
        Single(
            membership_reader=lambda: owner.snapshot, now=single._now,
            runtime_source=single._runtime,
            native_source=native_fixture()[2]._native,
        )


def test_expired_single_domain_scope_refused():
    owner, port, single, projector = native_fixture()
    single._now = lambda: owner[0].valid_until
    with pytest.raises(SingleDomainCoordinationUnavailable):
        single.observe()
    assert not port.send_calls


def test_single_domain_never_exports_sender_authority_or_transport():
    _, port, single, projector = native_fixture()
    observation = single.observe()
    reader = native_reader(single, projector)
    public = reader.visible_targets()
    assert "send" not in vars(type(single))
    assert "send" not in vars(type(reader))
    assert "requester" not in str(observation)
    assert FIRST.principal_ref not in str(public)
    assert SECOND.session_id not in str(public)
    assert not port.send_calls


def test_native_membership_digest_refuses_same_revision_with_wrong_project_roles():
    """Attestation identities alone must not endorse a divergent owner scope."""
    owner, port, single, projector = native_fixture()
    original = owner[0]
    # Caller-facing host observation is different from the manager-attested
    # owner source, even though session UUIDs and revision label still match.
    def divergent():
        return replace(original, participants=(
            original.participants[0],
            replace(original.participants[1], project_ref="misassigned-project"),
        ))

    single._membership = divergent
    with pytest.raises(SingleDomainCoordinationUnavailable):
        single.observe()
    assert not port.send_calls and not port.reconcile_calls
