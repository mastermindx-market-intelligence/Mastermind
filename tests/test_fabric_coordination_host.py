"""Authenticated source composition, no live provider or message effects."""
from dataclasses import replace

import pytest

from control_plane.fabric_coordination_policy import (
    CoordinationIdentity, CoordinationNativeIdentity, CoordinationParticipant,
    CoordinationRole,
)
from integrations.fabric_coordination_host import (
    AuthenticatedScopedTargetHost as Host, ScopedHostUnavailable,
)
from integrations.session_bridge.claude_native import ClaudeNativeTargetProjector
from tests.test_fabric_coordination_composite import NATIVE, fixture as mixed_fixture
from tests.test_fabric_coordination_single import (
    FIRST, SECOND, native_fixture, worker_fixture,
)
from tests.test_fabric_coordination_targets import _worker_projector
from tests.test_session_bridge_claude_native import Port, session, SESSION


def native_host():
    owner, port, _single, projector = native_fixture()
    caller = [FIRST]
    host = Host(
        membership_reader=lambda: owner[0],
        authenticated_caller_reader=lambda: caller[0],
        topic_ref="schema",
        now=lambda: owner[0].observed_at + 1,
        native_targets=projector,
        native_principal_reader=lambda sid, hostref:
            FIRST.principal_ref if (sid, hostref) == (FIRST.session_id, FIRST.host_ref)
            else SECOND.principal_ref if (sid, hostref) == (SECOND.session_id, SECOND.host_ref)
            else "missing",
    )
    return host, owner, port, caller


def worker_host(tmp_path, monkeypatch):
    seed, owner, _single, projector = worker_fixture(tmp_path, monkeypatch)
    caller = [owner.snapshot.participants[0].identity]
    host = Host(
        membership_reader=lambda: owner.snapshot,
        authenticated_caller_reader=lambda: caller[0],
        topic_ref="schema", now=lambda: seed.runtime.store.now_ms() // 1000,
        runtime=seed.runtime, worker_targets=projector,
    )
    return host, owner, caller, seed


def mixed_host(tmp_path, monkeypatch, *, omit_native=False):
    observation, owner, port = mixed_fixture(tmp_path, monkeypatch)
    caller = [NATIVE]
    options = dict(
        membership_reader=lambda: owner.snapshot,
        authenticated_caller_reader=lambda: caller[0],
        topic_ref="schema",
        now=lambda: observation._runtime.store.now_ms() // 1000,
        runtime=observation._runtime,
        worker_targets=_worker_projector(observation, owner),
    )
    if not omit_native:
        options["native_targets"] = observation._native_projector
        options["native_principal_reader"] = (
            lambda sid, hostref: NATIVE.principal_ref
            if (sid, hostref) == (NATIVE.session_id, NATIVE.host_ref)
            else "unknown"
        )
    return Host(**options), owner, port, caller


def test_native_only_ceo_peers_with_zero_runtime_jobs():
    host, owner, port, caller = native_host()
    visible = host.visible_targets()
    assert len(visible) == 1
    assert visible[0]["relation"] == "portfolio_ceo_peer"
    assert host.resolve(visible[0]["target_ref"]).recipient == SECOND
    assert not port.send_calls and not port.reconcile_calls


def test_native_host_reads_authenticated_caller_fresh_on_each_invocation():
    host, owner, port, caller = native_host()
    target = host.visible_targets()[0]["target_ref"]
    caller[0] = SECOND
    with pytest.raises(ScopedHostUnavailable, match="SCOPED_COORDINATION_HOST_UNAVAILABLE"):
        host.resolve(target)
    assert not port.send_calls


def test_worker_only_discovery_without_native_management(tmp_path, monkeypatch):
    host, owner, caller, _ = worker_host(tmp_path, monkeypatch)
    shown = host.visible_targets()
    assert len(shown) == 1
    assert shown[0]["kind"] == "fabric_attempt"
    assert shown[0]["relation"] == "task_group_worker_peer"
    assert host.resolve(shown[0]["target_ref"]).recipient == owner.snapshot.participants[1].identity


def test_mixed_scope_uses_both_existing_identity_owners(tmp_path, monkeypatch):
    host, owner, port, caller = mixed_host(tmp_path, monkeypatch)
    shown = host.visible_targets()
    assert len(shown) == 1
    assert shown[0]["kind"] == "fabric_attempt"
    assert shown[0]["relation"] == "direct_parent_child"
    assert not port.send_calls


def test_mixed_scope_missing_native_owner_never_downgrades(tmp_path, monkeypatch):
    with pytest.raises(TypeError, match="missing or unexpected"):
        mixed_host(tmp_path, monkeypatch, omit_native=True)


def test_worker_scope_becoming_mixed_must_be_reselected(tmp_path, monkeypatch):
    host, owner, caller, seed = worker_host(tmp_path, monkeypatch)
    native = CoordinationParticipant(
        FIRST, CoordinationRole.PROJECT_CEO, "tenant", "portfolio",
        "project", "program-1",
    )
    owner.snapshot = replace(
        owner.snapshot, participants=(*owner.snapshot.participants, native),
    )
    with pytest.raises(ScopedHostUnavailable):
        host.visible_targets()


def test_native_scope_becoming_worker_mixed_must_be_reselected():
    host, owner, port, caller = native_host()
    worker = CoordinationParticipant(
        CoordinationIdentity("JOB-1", "ATT-1", "worker", "bind-1", 1),
        CoordinationRole.WORKER, "tenant", "portfolio", "project",
        "program", workstream_ref="ws", coordination_group_ref="group",
    )
    owner[0] = replace(owner[0], participants=(*owner[0].participants, worker))
    with pytest.raises(ScopedHostUnavailable):
        host.visible_targets()
    assert not port.send_calls


def test_host_does_not_accept_unverified_role_in_public_arguments():
    host, owner, port, caller = native_host()
    with pytest.raises(TypeError):
        host.visible_targets(caller=SECOND)
    for value in (None, 1, {"caller": FIRST}, "latest:claude"):
        with pytest.raises(ScopedHostUnavailable):
            host.resolve(value)
    assert not port.send_calls


def test_host_refuses_rotated_native_identity_even_when_scope_is_same():
    host, owner, port, caller = native_host()
    ref = host.visible_targets()[0]["target_ref"]
    port.current[SECOND.session_id] = session(
        SECOND.session_id, generation="gen-009", host_ref="ubuntu1",
    )
    with pytest.raises(ScopedHostUnavailable):
        host.resolve(ref)
    assert not port.send_calls


def test_host_refuses_stale_current_authenticated_principal():
    host, owner, port, caller = native_host()
    caller[0] = replace(FIRST, principal_ref="new-principal")
    with pytest.raises(ScopedHostUnavailable):
        host.visible_targets()
    assert not port.send_calls


def test_worker_only_host_rejects_unneeded_native_projector(tmp_path, monkeypatch):
    seed, owner, _single, projector = worker_fixture(tmp_path, monkeypatch)
    with pytest.raises(TypeError):
        Host(
            membership_reader=lambda: owner.snapshot,
            authenticated_caller_reader=lambda: owner.snapshot.participants[0].identity,
            topic_ref="schema",
            now=lambda: seed.runtime.store.now_ms() // 1000,
            runtime=seed.runtime, worker_targets=projector,
            native_targets=ClaudeNativeTargetProjector(Port()),
        )


def test_native_only_host_rejects_runtime_injection(tmp_path, monkeypatch):
    seed, _owner, _single, _projector = worker_fixture(tmp_path, monkeypatch)
    native_owner, _port, _source, native_projector = native_fixture()
    with pytest.raises(TypeError):
        Host(
            membership_reader=lambda: native_owner[0],
            authenticated_caller_reader=lambda: FIRST,
            topic_ref="schema", now=lambda: native_owner[0].observed_at + 1,
            runtime=seed.runtime, native_targets=native_projector,
            native_principal_reader=lambda *_: "principal-one",
        )


def test_current_authenticated_principal_must_remain_a_registered_actor():
    host, owner, port, caller = native_host()
    caller[0] = "COO"  # provider label is not an authenticated member
    with pytest.raises(ScopedHostUnavailable):
        host.visible_targets()
    assert not port.send_calls


def test_expired_membership_refuses_before_target_selection():
    host, owner, port, caller = native_host()
    host._now = lambda: owner[0].valid_until
    with pytest.raises(ScopedHostUnavailable):
        host.visible_targets()
    assert not port.send_calls


def test_host_does_not_expose_send_or_worker_lifecycle():
    host, owner, port, caller = native_host()
    assert not hasattr(host, "send")
    assert not hasattr(host, "launch")
    assert not hasattr(host, "register_worker")
    visible = host.visible_targets()
    assert FIRST.session_id not in str(visible)
    assert SECOND.principal_ref not in str(visible)
    assert not port.send_calls


def test_authenticated_principal_rotation_during_target_discovery_refuses():
    host, owner, port, caller = native_host()
    original = host._owner.observe
    reads = [0]

    def rotate_after_second_observation():
        result = original()
        reads[0] += 1
        if reads[0] == 2:
            caller[0] = replace(FIRST, principal_ref="no-longer-valid")
        return result

    host._owner.observe = rotate_after_second_observation
    with pytest.raises(ScopedHostUnavailable):
        host.visible_targets()
    assert reads[0] == 2
    assert not port.send_calls


def test_authenticated_principal_rotation_during_exact_resolution_refuses():
    host, owner, port, caller = native_host()
    ref = host.visible_targets()[0]["target_ref"]
    original = host._owner.observe
    reads = [0]

    def rotate_after_final_observation():
        result = original()
        reads[0] += 1
        if reads[0] >= 4:
            caller[0] = replace(FIRST, principal_ref="rotated-principal")
        return result

    host._owner.observe = rotate_after_final_observation
    with pytest.raises(ScopedHostUnavailable):
        host.resolve(ref)
    assert reads[0] >= 4
    assert not port.send_calls


def test_async_caller_source_cannot_be_misbound_to_sync_host():
    owner, port, _single, projector = native_fixture()

    async def verified_actor():
        return FIRST

    with pytest.raises(TypeError, match="synchronous"):
        Host(
            membership_reader=lambda: owner[0],
            authenticated_caller_reader=verified_actor,
            topic_ref="schema", now=lambda: owner[0].observed_at + 1,
            native_targets=projector,
            native_principal_reader=lambda *_: FIRST.principal_ref,
        )
    assert not port.send_calls


def test_scope_revocation_after_target_projection_cannot_leak_peer():
    """Old caller-only last-read check missed a revoked recipient portfolio."""
    host, owner, port, caller = native_host()
    original = host._authenticated_caller
    reads = [0]

    def revoke_after_projection():
        reads[0] += 1
        if reads[0] == 2:
            current = owner[0]
            owner[0] = replace(current, participants=(
                current.participants[0],
                replace(current.participants[1], portfolio_ref="foreign"),
            ))
        return original()

    host._authenticated_caller = revoke_after_projection
    with pytest.raises(ScopedHostUnavailable):
        host.visible_targets()
    assert reads[0] >= 2
    assert not port.send_calls and not port.reconcile_calls


def test_scope_dependency_grant_revoke_after_resolve_never_exposes_target():
    """Host must reauthorize the recipient even after resolved exact ref."""
    from control_plane.fabric_coordination_policy import CoordinationGrant
    from tests.test_fabric_coordination_single import FIRST, SECOND, NOW

    host, owner, port, caller = native_host()
    a, b = owner[0].participants
    grant = CoordinationGrant(
        "final-read-grant", FIRST, SECOND, "schema",
        ("project-a", "project-b"), NOW, NOW + 25,
    )
    owner[0] = replace(owner[0], participants=(
        replace(a, role=CoordinationRole.COO),
        replace(b, role=CoordinationRole.COO),
    ), grants=(grant,))
    reference = host.visible_targets()[0]["target_ref"]
    original = host._authenticated_caller
    reads = [0]

    def revoke_after_projection():
        reads[0] += 1
        if reads[0] == 2:
            owner[0] = replace(owner[0], grants=(
                replace(grant, revoked=True),
            ))
        return original()

    host._authenticated_caller = revoke_after_projection
    with pytest.raises(ScopedHostUnavailable):
        host.resolve(reference)
    assert reads[0] >= 2
    assert not port.send_calls and not port.reconcile_calls


def test_worker_only_still_operates_with_dormant_native_roster_record(tmp_path, monkeypatch):
    """A revoked/inactive CEO cannot force worker peer discovery to need Claude."""
    from tests.test_fabric_coordination_single import worker_fixture
    seed, owner, _single, projector = worker_fixture(tmp_path, monkeypatch)
    dormant = CoordinationParticipant(
        FIRST, CoordinationRole.PROJECT_CEO, "tenant", "portfolio",
        "retired-project", "retired-program", active=False,
    )
    owner.snapshot = replace(
        owner.snapshot,
        participants=(*owner.snapshot.participants, dormant),
    )
    caller = owner.snapshot.participants[0].identity
    host = Host(
        membership_reader=lambda: owner.snapshot,
        authenticated_caller_reader=lambda: caller,
        topic_ref="schema",
        now=lambda: seed.runtime.store.now_ms() // 1000,
        runtime=seed.runtime, worker_targets=projector,
    )
    visible = host.visible_targets()
    assert len(visible) == 1
    assert visible[0]["kind"] == "fabric_attempt"
    assert host.resolve(visible[0]["target_ref"]).recipient == owner.snapshot.participants[1].identity
    assert "retired-project" not in str(visible)
    assert host._owner.observe().snapshot.participants[-1] == dormant


def test_native_only_still_operates_with_dormant_worker_without_runtime():
    """No synthetic Executive Attempt is needed for a retired worker record."""
    owner, port, _single, projector = native_fixture()
    dormant = CoordinationParticipant(
        CoordinationIdentity("JOB-retired", "ATT-retired", "worker-retired",
                             "binding-retired", 1),
        CoordinationRole.WORKER,
        "tenant", "portfolio", "project-b", "program-1",
        workstream_ref="retired-stream", coordination_group_ref="retired-group",
        active=False,
    )
    owner[0] = replace(
        owner[0], participants=(*owner[0].participants, dormant),
    )
    host = Host(
        membership_reader=lambda: owner[0],
        authenticated_caller_reader=lambda: FIRST,
        topic_ref="schema", now=lambda: owner[0].observed_at + 1,
        native_targets=projector,
        native_principal_reader=lambda sid, hostref:
            FIRST.principal_ref if (sid, hostref) == (FIRST.session_id, FIRST.host_ref)
            else SECOND.principal_ref if (sid, hostref) == (SECOND.session_id, SECOND.host_ref)
            else "missing",
    )
    visible = host.visible_targets()
    assert len(visible) == 1
    assert visible[0]["kind"] == "claude"
    assert host.resolve(visible[0]["target_ref"]).recipient == SECOND
    assert host._owner.observe().snapshot.participants[-1] == dormant
    assert not port.send_calls and not port.reconcile_calls


def test_dormant_other_domain_reactivation_during_target_read_refuses():
    owner, port, _single, projector = native_fixture()
    dormant = CoordinationParticipant(
        CoordinationIdentity("JOB-retired", "ATT-retired", "worker-retired",
                             "binding-retired", 1),
        CoordinationRole.WORKER,
        "tenant", "portfolio", "project-b", "program-1",
        workstream_ref="retired-stream", coordination_group_ref="retired-group",
        active=False,
    )
    owner[0] = replace(owner[0], participants=(*owner[0].participants, dormant))
    principal = {
        (FIRST.session_id, FIRST.host_ref): FIRST.principal_ref,
        (SECOND.session_id, SECOND.host_ref): SECOND.principal_ref,
    }
    host = Host(
        membership_reader=lambda: owner[0],
        authenticated_caller_reader=lambda: FIRST,
        topic_ref="schema", now=lambda: owner[0].observed_at + 1,
        native_targets=projector,
        native_principal_reader=lambda sid, hostref: principal.get((sid, hostref), "missing"),
    )
    original = host._authenticated_caller
    calls = [0]

    def reactivate_after_discovery():
        calls[0] += 1
        if calls[0] == 2:
            current = owner[0]
            owner[0] = replace(current, participants=(
                *current.participants[:-1],
                replace(current.participants[-1], active=True),
            ))
        return original()

    host._authenticated_caller = reactivate_after_discovery
    with pytest.raises(ScopedHostUnavailable):
        host.visible_targets()
    assert calls[0] >= 2
    assert not port.send_calls and not port.reconcile_calls


def test_all_inactive_members_are_not_a_discoverable_domain():
    owner, port, _single, projector = native_fixture()
    owner[0] = replace(owner[0], participants=tuple(
        replace(item, active=False) for item in owner[0].participants
    ))
    with pytest.raises(ScopedHostUnavailable):
        Host(
            membership_reader=lambda: owner[0],
            authenticated_caller_reader=lambda: FIRST,
            topic_ref="schema", now=lambda: owner[0].observed_at + 1,
            native_targets=projector,
            native_principal_reader=lambda *_: FIRST.principal_ref,
        )
    assert not port.send_calls


def test_historical_native_generation_remains_audit_only_not_addressable():
    """A single live native UUID is valid alongside its inactive old generation."""
    host, owner, port, caller = native_host()
    earlier = replace(
        owner[0].participants[0],
        identity=replace(FIRST, generation="gen-before", principal_ref="prior-principal"),
        active=False,
    )
    owner[0] = replace(
        owner[0], participants=(*owner[0].participants, earlier),
    )
    visible = host.visible_targets()
    assert len(visible) == 1
    assert visible[0]["kind"] == "claude"
    assert host.resolve(visible[0]["target_ref"]).recipient == SECOND
    assert host._owner.observe().snapshot.participants[-1] == earlier
    assert earlier.identity.session_id not in str(visible)
    assert not port.send_calls and not port.reconcile_calls


def test_historical_worker_attempt_remains_audit_only_not_addressable(
    tmp_path, monkeypatch,
):
    """A retained old binding for the same Job never overrides current Runtime."""
    host, owner, caller, seed = worker_host(tmp_path, monkeypatch)
    past = replace(
        owner.snapshot.participants[0],
        identity=replace(
            owner.snapshot.participants[0].identity,
            attempt_id="ATT-previous",
            binding_id="binding-previous",
        ),
        active=False,
    )
    owner.snapshot = replace(
        owner.snapshot, participants=(*owner.snapshot.participants, past),
    )
    visible = host.visible_targets()
    assert len(visible) == 1
    assert visible[0]["kind"] == "fabric_attempt"
    selected = host.resolve(visible[0]["target_ref"])
    assert selected.recipient == owner.snapshot.participants[1].identity
    assert host._owner.observe().snapshot.participants[-1] == past
    assert past.identity.attempt_id not in str(visible)


@pytest.mark.parametrize("mutation", [
    "joint_tenant_portfolio_move", "ceo_project_reassignment",
])
def test_host_final_scope_fence_detects_still_permitted_edge_context_change(
    mutation,
):
    """C3 review: same policy relation cannot return old peer after reassignment."""
    host, owner, port, caller = native_host()
    original = host._authenticated_caller
    calls = [0]

    def move_after_target_projection():
        calls[0] += 1
        if calls[0] == 2:
            original_scope = owner[0]
            first, second = original_scope.participants
            if mutation == "joint_tenant_portfolio_move":
                members = (
                    replace(first, tenant_ref="relocated-tenant",
                            portfolio_ref="relocated-portfolio"),
                    replace(second, tenant_ref="relocated-tenant",
                            portfolio_ref="relocated-portfolio"),
                )
            else:
                members = (first, replace(second, project_ref="moved-project"))
            owner[0] = replace(original_scope, participants=members)
        return original()

    host._authenticated_caller = move_after_target_projection
    with pytest.raises(ScopedHostUnavailable):
        host.visible_targets()
    assert calls[0] >= 2
    assert not port.send_calls and not port.reconcile_calls
