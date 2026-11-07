"""Positive and adversarial tests for the advisory coordination graph."""
from dataclasses import FrozenInstanceError, replace
import pytest
from control_plane.fabric_coordination_policy import (
    CoordinationGrant, CoordinationIdentity as Identity,
    CoordinationParticipant as Participant, CoordinationRefused,
    CoordinationRole as Role, CoordinationSnapshot as Snapshot,
    authorize_coordination,
)

NOW = 1000


def actor(n, role, **kwargs):
    values = dict(
        identity=Identity(f"JOB-{n}", f"ATT-{n}", f"worker-{n}", f"bind-{n}", 1),
        role=role, tenant_ref="tenant-a", portfolio_ref="portfolio-a",
        project_ref="project-a", program_ref=f"JOB-{n}/operation-{n}",
        workstream_ref="workstream-a", coordination_group_ref="group-a",
    )
    values.update(kwargs)
    return Participant(**values)


def snapshot(*actors, grants=()):
    return Snapshot("revision-1", NOW, NOW + 30, tuple(actors), grants)


def decide(a, b, *, grants=(), now=NOW, topic="topic-a", extra=()):
    return authorize_coordination(snapshot(a, b, *extra, grants=grants), a.identity, b.identity, topic_ref=topic, now=now)


@pytest.mark.parametrize("parent_role,child_role", [
    (Role.PROJECT_CEO, Role.COO), (Role.COO, Role.TASK_OPERATOR),
    (Role.TASK_OPERATOR, Role.WORKER), (Role.PROJECT_CEO, Role.WORKER),
    (Role.COO, Role.WORKER), (Role.PROJECT_CEO, Role.TASK_OPERATOR),
])
def test_parent_child_bidirectional_and_collapsed_layers(parent_role, child_role):
    parent = actor(1, parent_role)
    child = actor(2, child_role, parent_job_id=parent.identity.job_id)
    assert decide(parent, child).relation == "direct_parent_child"
    assert decide(child, parent).relation == "direct_parent_child"


@pytest.mark.parametrize("role,relation", [
    (Role.PROJECT_CEO, "portfolio_ceo_peer"), (Role.COO, "project_coo_peer"),
    (Role.TASK_OPERATOR, "workstream_operator_peer"), (Role.WORKER, "task_group_worker_peer"),
])
def test_permitted_peers_have_no_command_or_forward_authority(role, relation):
    result = decide(actor(1, role), actor(2, role))
    assert result.relation == relation
    assert result.operational_authority is False
    assert result.forwarding_allowed is False


def test_ceo_cross_project_within_portfolio():
    assert decide(actor(1, Role.PROJECT_CEO), actor(2, Role.PROJECT_CEO, project_ref="project-b")).relation == "portfolio_ceo_peer"


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("field", ["tenant_ref", "portfolio_ref"])
def test_tenant_and_portfolio_boundaries(role, field):
    with pytest.raises(CoordinationRefused):
        decide(actor(1, role), actor(2, role, **{field: "foreign"}))


@pytest.mark.parametrize("role", [Role.COO, Role.TASK_OPERATOR, Role.WORKER])
def test_same_rank_does_not_allow_cross_project(role):
    with pytest.raises(CoordinationRefused):
        decide(actor(1, role), actor(2, role, project_ref="project-b"))


@pytest.mark.parametrize("role", [Role.TASK_OPERATOR, Role.WORKER])
def test_workstream_isolation(role):
    with pytest.raises(CoordinationRefused):
        decide(actor(1, role), actor(2, role, workstream_ref="workstream-b"))


def test_workers_outside_group_are_not_peers():
    with pytest.raises(CoordinationRefused):
        decide(actor(1, Role.WORKER), actor(2, Role.WORKER, coordination_group_ref="group-b"))


@pytest.mark.parametrize("first,second", [(a,b) for a in Role for b in Role if a is not b])
def test_unrelated_different_ranks_cannot_command_or_contact(first, second):
    with pytest.raises(CoordinationRefused):
        decide(actor(1, first), actor(2, second))


def grant(a, b, **kwargs):
    values = dict(grant_ref="grant-a", first=a.identity, second=b.identity, topic_ref="topic-a", approved_project_refs=tuple(sorted({a.project_ref, b.project_ref})), not_before=NOW-1, valid_until=NOW+60)
    values.update(kwargs)
    return CoordinationGrant(**values)


@pytest.mark.parametrize("role", [Role.COO, Role.TASK_OPERATOR, Role.WORKER])
def test_bilateral_dependency_grant_for_exact_peers(role):
    a, b = actor(1, role), actor(2, role, project_ref="project-b")
    admitted = grant(a, b)
    assert decide(a, b, grants=(admitted,)).relation == "explicit_dependency_peer"
    assert decide(b, a, grants=(admitted,)).grant_ref == "grant-a"


@pytest.mark.parametrize("change", [
    {"revoked": True}, {"not_before": NOW+1}, {"valid_until": NOW},
    {"topic_ref": "other"}, {"approved_project_refs": ("project-a",)},
])
def test_grant_revocation_expiry_topic_and_bilateral_approval(change):
    a, b = actor(1, Role.WORKER), actor(2, Role.WORKER, project_ref="project-b")
    with pytest.raises(CoordinationRefused):
        decide(a, b, grants=(grant(a, b, **change),))


def test_grant_cannot_survive_new_binding_generation():
    a, b = actor(1, Role.WORKER), actor(2, Role.WORKER, project_ref="project-b")
    admitted = grant(a, b)
    new_b = replace(b, identity=replace(b.identity, binding_generation=2))
    with pytest.raises(CoordinationRefused):
        decide(a, new_b, grants=(admitted,))


@pytest.mark.parametrize("field", ["tenant_ref", "portfolio_ref"])
def test_grant_never_overrides_tenant_or_portfolio(field):
    a, b = actor(1, Role.WORKER), actor(2, Role.WORKER, **{field: "foreign"})
    with pytest.raises(CoordinationRefused):
        decide(a, b, grants=(grant(a, b),))


def test_grant_does_not_create_cross_rank_authority():
    a, b = actor(1, Role.WORKER), actor(2, Role.PROJECT_CEO)
    with pytest.raises(CoordinationRefused):
        decide(a, b, grants=(grant(a, b),))


@pytest.mark.parametrize("now", [NOW-1, NOW+30, NOW+31])
def test_stale_and_future_observations_fail_closed(now):
    with pytest.raises(CoordinationRefused):
        decide(actor(1, Role.WORKER), actor(2, Role.WORKER), now=now)


@pytest.mark.parametrize("which", [0, 1])
def test_terminal_participant_refused(which):
    pair = [actor(1, Role.WORKER), actor(2, Role.WORKER)]
    pair[which] = replace(pair[which], active=False)
    with pytest.raises(CoordinationRefused):
        decide(*pair)


def test_old_attempt_cannot_impersonate_current_attempt():
    a, b = actor(1, Role.WORKER), actor(2, Role.WORKER)
    with pytest.raises(CoordinationRefused):
        authorize_coordination(snapshot(a,b), replace(a.identity, attempt_id="ATT-old"), b.identity, topic_ref="topic-a", now=NOW)


def test_no_self_send():
    a = actor(1, Role.WORKER)
    with pytest.raises(CoordinationRefused):
        authorize_coordination(snapshot(a), a.identity, a.identity, topic_ref="topic-a", now=NOW)


@pytest.mark.parametrize("value", [True, 0, -1, "1", 1.0])
def test_binding_generation_must_be_positive_integer(value):
    with pytest.raises(CoordinationRefused):
        Identity("JOB-1", "ATT-1", "worker-1", "bind-1", value)


def test_roles_are_not_freeform_prompt_strings():
    with pytest.raises(CoordinationRefused):
        actor(1, "project_ceo")


@pytest.mark.parametrize("field,value", [("workstream_ref", None), ("coordination_group_ref", None)])
def test_worker_scope_cannot_be_omitted(field, value):
    with pytest.raises(CoordinationRefused):
        actor(1, Role.WORKER, **{field: value})


def test_ambiguous_identity_snapshot_rejected():
    a = actor(1, Role.WORKER)
    with pytest.raises(CoordinationRefused):
        snapshot(a, a)


def test_duplicate_binding_rejected_even_with_different_job():
    a, b = actor(1, Role.WORKER), actor(2, Role.WORKER)
    with pytest.raises(CoordinationRefused):
        snapshot(a, replace(b, identity=replace(b.identity, binding_id=a.identity.binding_id)))


def test_duplicate_grant_reference_rejected():
    a, b = actor(1, Role.WORKER), actor(2, Role.WORKER)
    g = grant(a, b)
    with pytest.raises(CoordinationRefused):
        snapshot(a,b,grants=(g,g))


@pytest.mark.parametrize("change", [{"project_ref":"foreign"}, {"workstream_ref":"foreign"}, {"tenant_ref":"foreign"}, {"portfolio_ref":"foreign"}])
def test_parent_link_cannot_bypass_scope(change):
    parent, child = actor(1, Role.TASK_OPERATOR), actor(2, Role.WORKER, parent_job_id="JOB-1", **change)
    with pytest.raises(CoordinationRefused):
        snapshot(parent, child)


def test_cycle_or_reverse_rank_parent_rejected():
    with pytest.raises(CoordinationRefused):
        snapshot(actor(1,Role.COO,parent_job_id="JOB-2"), actor(2,Role.WORKER,parent_job_id="JOB-1"))


def test_snapshot_is_bounded_and_immutable():
    a = actor(1,Role.WORKER)
    with pytest.raises(CoordinationRefused):
        Snapshot("rev", NOW, NOW+31, (a,))
    with pytest.raises(CoordinationRefused):
        Snapshot("rev", NOW, NOW+30, [a])
    with pytest.raises(FrozenInstanceError):
        a.role = Role.PROJECT_CEO


def test_inactive_old_attempt_cannot_block_unique_current_generation():
    """Runtime may retain completed Attempts after a Job's active rebinding."""
    past = replace(actor(1, Role.WORKER), active=False)
    current = replace(
        actor(1, Role.WORKER),
        identity=Identity("JOB-1", "ATT-new", "worker-new", "bind-new", 2),
    )
    peer = actor(2, Role.WORKER)
    scope = snapshot(past, current, peer)
    assert authorize_coordination(
        scope, current.identity, peer.identity, topic_ref="topic-a", now=NOW,
    ).relation == "task_group_worker_peer"
    with pytest.raises(CoordinationRefused):
        authorize_coordination(
            scope, past.identity, peer.identity, topic_ref="topic-a", now=NOW,
        )


def test_inactive_old_binding_epoch_does_not_block_unique_current_generation():
    old = replace(actor(1, Role.WORKER), active=False)
    fresh = replace(
        actor(1, Role.WORKER),
        identity=replace(old.identity, binding_generation=2),
    )
    peer = actor(2, Role.WORKER)
    scope = snapshot(old, fresh, peer)
    assert authorize_coordination(
        scope, fresh.identity, peer.identity, topic_ref="topic-a", now=NOW,
    ).relation == "task_group_worker_peer"
    with pytest.raises(CoordinationRefused):
        authorize_coordination(
            scope, old.identity, peer.identity, topic_ref="topic-a", now=NOW,
        )


def test_native_managed_session_old_inactive_generation_not_a_second_live_session():
    from control_plane.fabric_coordination_policy import CoordinationNativeIdentity
    old = CoordinationNativeIdentity(
        "f71c3451-edd7-4e88-93d8-1fe483eac293", "gen-001",
        "ubuntu1", "principal-old",
    )
    new = replace(old, generation="gen-002", principal_ref="principal-current")
    peer = CoordinationNativeIdentity(
        "11111111-2222-4333-8444-555555555555", "gen-001",
        "ubuntu2", "principal-peer",
    )
    def native(identity, active=True):
        return Participant(
            identity, Role.COO, "tenant", "portfolio", "project",
            "program", active=active,
        )
    scope = snapshot(native(old, active=False), native(new), native(peer))
    assert authorize_coordination(
        scope, new, peer, topic_ref="topic-a", now=NOW,
    ).relation == "project_coo_peer"
    with pytest.raises(CoordinationRefused):
        authorize_coordination(
            scope, old, peer, topic_ref="topic-a", now=NOW,
        )
    with pytest.raises(CoordinationRefused):
        snapshot(native(old), native(new), native(peer))


def test_two_active_epochs_for_one_runtime_job_remain_ambiguous():
    old = actor(1, Role.WORKER)
    newer = replace(
        old, identity=Identity("JOB-1", "ATT-new", "worker-new", "bind-new", 2),
    )
    with pytest.raises(CoordinationRefused):
        snapshot(old, newer)


def test_current_parent_edge_ignores_old_inactive_parent_attempt():
    retired = replace(actor(1, Role.PROJECT_CEO), active=False)
    current = replace(
        actor(1, Role.PROJECT_CEO),
        identity=Identity("JOB-1", "ATT-new", "worker-new", "bind-new", 2),
    )
    child = actor(2, Role.WORKER, parent_job_id="JOB-1")
    scope = snapshot(current, retired, child)
    assert authorize_coordination(
        scope, current.identity, child.identity, topic_ref="topic-a", now=NOW,
    ).relation == "direct_parent_child"
    with pytest.raises(CoordinationRefused):
        authorize_coordination(
            scope, retired.identity, child.identity, topic_ref="topic-a", now=NOW,
        )


def test_stale_explicit_parent_pin_must_not_fallback_to_current_job_owner():
    historical = actor(1, Role.PROJECT_CEO)
    current = replace(
        historical,
        identity=Identity("JOB-1", "ATT-new", "worker-new", "bind-new", 2),
    )
    child = actor(
        2, Role.WORKER, parent_job_id=current.identity.job_id,
        parent_identity=historical.identity,
    )
    with pytest.raises(CoordinationRefused):
        snapshot(current, child)


def test_matching_explicit_and_legacy_parent_still_permitted():
    parent = actor(1, Role.PROJECT_CEO)
    child = actor(
        2, Role.WORKER, parent_job_id=parent.identity.job_id,
        parent_identity=parent.identity,
    )
    snap = snapshot(parent, child)
    assert authorize_coordination(
        snap, child.identity, parent.identity,
        topic_ref="topic-a", now=NOW,
    ).relation == "direct_parent_child"
    assert authorize_coordination(
        snap, parent.identity, child.identity,
        topic_ref="topic-a", now=NOW,
    ).relation == "direct_parent_child"


def test_legacy_job_only_parent_remains_explicit_compatibility_mode():
    parent = actor(1, Role.PROJECT_CEO)
    child = actor(2, Role.WORKER, parent_job_id=parent.identity.job_id)
    snap = snapshot(parent, child)
    assert authorize_coordination(
        snap, child.identity, parent.identity,
        topic_ref="topic-a", now=NOW,
    ).relation == "direct_parent_child"
