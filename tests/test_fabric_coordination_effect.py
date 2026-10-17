"""Owner-COMMIT admission hook: current identity + exact grant/target checks.

All exercised effects are hermetic consultations; no provider message, worker,
service, or production COMMIT is performed. These tests intentionally supply
current organizational and Session Bridge owners from the source fixtures.
"""
from dataclasses import replace

import pytest

from control_plane.fabric_coordination_policy import (
    CoordinationGrant, CoordinationRole,
)
from integrations.fabric_coordination_effect import (
    HierarchyEffectOwnerGuard, ScopedEffectRefused,
)
from tests.test_fabric_coordination_host import (
    native_host, worker_host, mixed_host,
)
from tests.test_fabric_coordination_single import FIRST, SECOND, NOW
from tests.test_session_bridge_claude_native import session


def guard_for(host, sender):
    targets = host.visible_targets()
    assert len(targets) == 1
    target = host.resolve(targets[0]["target_ref"])
    return HierarchyEffectOwnerGuard(
        host=host, original_sender=sender,
        original_target=target, original_topic_ref="schema",
    ), target


def test_native_ceo_original_edge_is_current_under_owner_fence():
    host, owner, port, caller = native_host()
    guard, target = guard_for(host, FIRST)
    assert target.recipient == SECOND
    assert target.grant_ref is None
    assert guard.verify_inside_owner_effect() is None
    assert not port.send_calls and not port.reconcile_calls


def test_worker_same_group_current_edge_under_owner_fence(tmp_path, monkeypatch):
    host, owner, caller, seed = worker_host(tmp_path, monkeypatch)
    guard, target = guard_for(host, caller[0])
    assert target.relation == "task_group_worker_peer"
    assert guard.verify_inside_owner_effect() is None
    assert seed.runtime.jobs.list_jobs()


def test_native_fence_refuses_post_selection_caller_rotation():
    host, owner, port, caller = native_host()
    guard, target = guard_for(host, FIRST)
    caller[0] = replace(FIRST, principal_ref="rotated-principal")
    with pytest.raises(ScopedEffectRefused, match="SCOPED_EFFECT_UNAVAILABLE"):
        guard.verify_inside_owner_effect()
    assert not port.send_calls


def test_native_fence_refuses_post_selection_recipient_generation_rotation():
    host, owner, port, caller = native_host()
    guard, target = guard_for(host, FIRST)
    port.current[SECOND.session_id] = session(
        SECOND.session_id, generation="gen-003", host_ref="ubuntu1",
    )
    with pytest.raises(ScopedEffectRefused):
        guard.verify_inside_owner_effect()
    assert not port.send_calls and not port.reconcile_calls


def test_native_fence_refuses_role_revocation_and_foreign_portfolio():
    host, owner, port, caller = native_host()
    guard, target = guard_for(host, FIRST)
    previous = owner[0]
    owner[0] = replace(previous, participants=(
        previous.participants[0],
        replace(previous.participants[1], portfolio_ref="foreign-portfolio"),
    ))
    with pytest.raises(ScopedEffectRefused):
        guard.verify_inside_owner_effect()
    assert not port.send_calls


def test_native_fence_refuses_scope_expiration():
    host, owner, port, caller = native_host()
    guard, target = guard_for(host, FIRST)
    host._now = lambda: owner[0].valid_until
    with pytest.raises(ScopedEffectRefused):
        guard.verify_inside_owner_effect()
    assert not port.send_calls


def test_no_implicit_grant_replacement_for_same_recipient_and_relation():
    host, owner, port, caller = native_host()
    initial = owner[0]
    a, b = initial.participants
    first = replace(a, role=CoordinationRole.COO)
    second = replace(b, role=CoordinationRole.COO)
    previous = CoordinationGrant(
        "grant-before", FIRST, SECOND, "schema",
        ("project-a", "project-b"), NOW, NOW + 25,
    )
    owner[0] = replace(initial, participants=(first, second), grants=(previous,))
    guard, target = guard_for(host, FIRST)
    assert target.relation == "explicit_dependency_peer"
    assert target.grant_ref == "grant-before"
    assert guard.verify_inside_owner_effect() is None

    # A newly approved dependency does not inherit the earlier accepted
    # intent's grant identity. A new request must be admitted instead.
    updated = replace(previous, grant_ref="grant-after")
    owner[0] = replace(owner[0], grants=(updated,))
    current = host.resolve(target.target_ref)
    assert current.recipient == target.recipient
    assert current.relation == target.relation
    assert current.grant_ref == "grant-after"
    with pytest.raises(ScopedEffectRefused):
        guard.verify_inside_owner_effect()
    assert not port.send_calls


def test_revoked_exact_dependency_grant_refuses_effect():
    host, owner, port, caller = native_host()
    a, b = owner[0].participants
    first = replace(a, role=CoordinationRole.COO)
    second = replace(b, role=CoordinationRole.COO)
    grant = CoordinationGrant(
        "grant-original", FIRST, SECOND, "schema",
        ("project-a", "project-b"), NOW, NOW + 25,
    )
    owner[0] = replace(owner[0], participants=(first, second), grants=(grant,))
    guard, target = guard_for(host, FIRST)
    owner[0] = replace(owner[0], grants=(replace(grant, revoked=True),))
    with pytest.raises(ScopedEffectRefused):
        guard.verify_inside_owner_effect()
    assert not port.send_calls


def test_fresh_scope_renewal_allows_unchanged_original_edge():
    host, owner, port, caller = native_host()
    guard, target = guard_for(host, FIRST)
    # The 30-second membership observation may refresh while a bounded task
    # runs. Fresh current authorization, not the old expiring snapshot, wins.
    owner[0] = replace(owner[0], valid_until=owner[0].valid_until + 1)
    assert host.resolve(target.target_ref).valid_until > target.valid_until
    assert guard.verify_inside_owner_effect() is None
    assert not port.send_calls


def test_dependency_grant_payload_change_under_same_ref_refuses_old_intent():
    host, owner, port, caller = native_host()
    a, b = owner[0].participants
    old = CoordinationGrant(
        "grant-stable", FIRST, SECOND, "schema",
        ("project-a", "project-b"), NOW, NOW + 25,
    )
    owner[0] = replace(owner[0], participants=(
        replace(a, role=CoordinationRole.COO),
        replace(b, role=CoordinationRole.COO),
    ), grants=(old,))
    guard, target = guard_for(host, FIRST)
    assert target.grant_ref == "grant-stable"
    assert target.grant_digest
    assert guard.verify_inside_owner_effect() is None
    # A revision owner could attempt to reuse its old grant ID while changing
    # its validity terms. Do not let it inherit an already-accepted request.
    owner[0] = replace(owner[0], grants=(replace(old, valid_until=NOW + 26),))
    fresh = host.resolve(target.target_ref)
    assert fresh.grant_ref == target.grant_ref
    assert fresh.grant_digest != target.grant_digest
    with pytest.raises(ScopedEffectRefused):
        guard.verify_inside_owner_effect()
    assert not port.send_calls


def test_mixed_native_to_worker_current_edge(tmp_path, monkeypatch):
    host, owner, port, caller = mixed_host(tmp_path, monkeypatch)
    guard, target = guard_for(host, caller[0])
    assert target.relation == "direct_parent_child"
    assert guard.verify_inside_owner_effect() is None
    assert not port.send_calls


def test_public_arguments_never_set_an_effect_sender():
    host, owner, port, caller = native_host()
    guard, target = guard_for(host, FIRST)
    with pytest.raises(TypeError):
        guard.verify_inside_owner_effect(sender=SECOND)
    assert not hasattr(guard, "send")
    assert not hasattr(guard, "commit")
    assert not hasattr(guard, "wake")
    assert not port.send_calls


def test_forged_original_consultation_fails_constructor():
    host, owner, port, caller = native_host()
    _guard, target = guard_for(host, FIRST)
    with pytest.raises(TypeError):
        HierarchyEffectOwnerGuard(
            host=host, original_sender=SECOND,
            original_target=target, original_topic_ref="schema",
        )
    with pytest.raises(TypeError):
        HierarchyEffectOwnerGuard(
            host=host, original_sender=FIRST,
            original_target=target, original_topic_ref="wrong-topic",
        )
    assert not port.send_calls


@pytest.mark.parametrize("mutation", [
    "joint_tenant_portfolio_move",
    "single_ceo_project_reassignment",
    "joint_program_reassignment",
])
def test_accepted_consultation_cannot_follow_organizational_reassignment(mutation):
    """C3 review: same principals/relation must not carry an old grant of context."""
    host, owner, port, caller = native_host()
    guard, original = guard_for(host, FIRST)
    assert guard.verify_inside_owner_effect() is None
    first, second = owner[0].participants
    if mutation == "joint_tenant_portfolio_move":
        changed = (
            replace(first, tenant_ref="new-tenant", portfolio_ref="new-portfolio"),
            replace(second, tenant_ref="new-tenant", portfolio_ref="new-portfolio"),
        )
    elif mutation == "single_ceo_project_reassignment":
        changed = (first, replace(second, project_ref="new-project"))
    else:
        changed = (
            replace(first, program_ref="new-program"),
            replace(second, program_ref="new-program"),
        )
    owner[0] = replace(owner[0], participants=changed)
    # A new consultation could be approved under the current scope, but an
    # already accepted request must not follow this organizational transfer.
    refreshed = host.resolve(original.target_ref)
    assert refreshed.recipient == original.recipient
    assert refreshed.relation == original.relation
    with pytest.raises(ScopedEffectRefused):
        guard.verify_inside_owner_effect()
    assert not port.send_calls and not port.reconcile_calls
