"""Native hierarchy policy: pure owner-supplied facts, no live session enrollment.

These tests intentionally never create a provider session or use model-supplied
roles. Native CEO/COO identity and Runtime workers share the *policy*, not the
authenticated discovery, commit ownership, or transport implementation.
"""
from dataclasses import replace

import pytest

from control_plane.fabric_coordination_policy import (
    CoordinationActorIdentity, CoordinationDecision, CoordinationGrant,
    CoordinationIdentity, CoordinationNativeIdentity, CoordinationParticipant,
    CoordinationRefused, CoordinationRole, CoordinationSnapshot,
    authorize_coordination,
)

T = 1000
CEO_A = CoordinationNativeIdentity(
    "11111111-2222-4333-8444-555555555555", "gen-a", "m2studio",
    "principal-owner-a",
)
CEO_B = CoordinationNativeIdentity(
    "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee", "gen-b", "ubuntu1",
    "principal-owner-b",
)
COO_A = CoordinationNativeIdentity(
    "aaaaaaaa-2222-4333-8444-555555555555", "gen-a", "ubuntu1",
    "principal-coo-a",
)
COO_B = CoordinationNativeIdentity(
    "bbbbbbbb-2222-4333-8444-555555555555", "gen-b", "ubuntu2",
    "principal-coo-b",
)
WORKER = CoordinationIdentity("JOB-101", "ATT-101", "worker-a", "bind-a", 1)


def p(identity, role, *, project="project-a", portfolio="portfolio-a",
      tenant="tenant-a", parent_identity=None, parent_job_id=None,
      workstream=None, group=None):
    return CoordinationParticipant(
        identity, role, tenant, portfolio, project, "program-1",
        parent_job_id, workstream, group, True, parent_identity,
    )


def s(*people, grants=()):
    return CoordinationSnapshot("owner-1", T, T + 25, tuple(people), grants)


def decision(snapshot, src, dst, *, topic="schema", when=T + 1):
    return authorize_coordination(
        snapshot, src.identity, dst.identity, topic_ref=topic, now=when,
    )


def deny(snapshot, src, dst, *, topic="schema", when=T + 1):
    with pytest.raises(CoordinationRefused):
        decision(snapshot, src, dst, topic=topic, when=when)


def test_native_ceo_peer_across_projects_in_one_portfolio_both_directions():
    a = p(CEO_A, CoordinationRole.PROJECT_CEO)
    b = p(CEO_B, CoordinationRole.PROJECT_CEO, project="project-b")
    snap = s(a, b)
    for x, y in ((a, b), (b, a)):
        allowed = decision(snap, x, y)
        assert allowed.relation == "portfolio_ceo_peer"
        assert allowed.operational_authority is False
        assert allowed.forwarding_allowed is False


def test_native_coo_peer_same_project_but_not_foreign_project():
    a = p(COO_A, CoordinationRole.COO)
    b = p(COO_B, CoordinationRole.COO)
    assert decision(s(a, b), a, b).relation == "project_coo_peer"
    foreign = replace(b, project_ref="project-b")
    deny(s(a, foreign), a, foreign)


def test_native_ceo_to_native_coo_exact_parent_bidirectional():
    ceo = p(CEO_A, CoordinationRole.PROJECT_CEO)
    coo = p(COO_A, CoordinationRole.COO, parent_identity=CEO_A)
    snap = s(ceo, coo)
    for src, target in ((ceo, coo), (coo, ceo)):
        assert decision(snap, src, target).relation == "direct_parent_child"


def test_native_coo_to_worker_exact_parent_without_invented_runtime_job():
    coo = p(COO_A, CoordinationRole.COO)
    worker = p(WORKER, CoordinationRole.WORKER, workstream="ws",
               group="group", parent_identity=COO_A)
    snap = s(coo, worker)
    assert decision(snap, coo, worker).relation == "direct_parent_child"
    assert decision(snap, worker, coo).relation == "direct_parent_child"


def test_mixed_rank_without_exact_parent_remains_denied():
    coo = p(COO_A, CoordinationRole.COO)
    worker = p(WORKER, CoordinationRole.WORKER, workstream="ws", group="g")
    deny(s(coo, worker), worker, coo)
    deny(s(coo, worker), coo, worker)


def test_unlisted_parent_not_equivalent_to_live_authenticated_peer():
    coo = p(COO_A, CoordinationRole.COO)
    worker = p(WORKER, CoordinationRole.WORKER, workstream="ws",
               group="g", parent_identity=COO_A)
    # The projection omits the COO: a claimed parent relationship cannot
    # materialize a discoverable participant.
    snap = s(worker)
    with pytest.raises(CoordinationRefused):
        authorize_coordination(snap, worker.identity, coo.identity,
                               topic_ref="schema", now=T + 1)


def test_native_generation_or_principal_rotation_refuses_old_identity():
    coo = p(COO_A, CoordinationRole.COO)
    snap = s(coo)
    for identity in (replace(COO_A, generation="gen-2"),
                     replace(COO_A, principal_ref="principal-other"),
                     replace(COO_A, host_ref="other-host")):
        with pytest.raises(CoordinationRefused):
            snap.participant(identity, now=T + 1)


@pytest.mark.parametrize("value", [
    {"session_id": "LATEST"},
    {"session_id": "AAAAAAAA-2222-4333-8444-555555555555"},
    {"generation": ""},
    {"host_ref": "host with whitespace"},
    {"principal_ref": ""},
])
def test_native_identity_is_closed_and_exact(value):
    base = dict(session_id=COO_A.session_id, generation=COO_A.generation,
                host_ref=COO_A.host_ref, principal_ref=COO_A.principal_ref)
    with pytest.raises(CoordinationRefused):
        CoordinationNativeIdentity(**dict(base, **value))


@pytest.mark.parametrize("role", [CoordinationRole.WORKER,
                                 CoordinationRole.TASK_OPERATOR])
def test_native_session_cannot_self_admit_as_worker_or_operator(role):
    with pytest.raises(CoordinationRefused):
        p(COO_A, role, workstream="ws", group="g")


def test_native_session_cannot_claim_runtime_job_parent():
    with pytest.raises(CoordinationRefused):
        p(COO_A, CoordinationRole.COO, parent_job_id="JOB-101")


def test_duplicate_native_session_even_across_generation_or_principal_refused():
    a = p(COO_A, CoordinationRole.COO)
    for rotated in (replace(COO_A, generation="gen-2"),
                    replace(COO_A, host_ref="other-host"),
                    replace(COO_A, principal_ref="another")):
        with pytest.raises(CoordinationRefused, match="AMBIGUOUS_OWNER_FACTS"):
            s(a, replace(a, identity=rotated))


def test_duplicate_runtime_worker_jobs_still_refused():
    worker = p(WORKER, CoordinationRole.WORKER, workstream="ws", group="g")
    with pytest.raises(CoordinationRefused, match="AMBIGUOUS_OWNER_FACTS"):
        s(worker, replace(worker, identity=replace(WORKER, binding_id="bind-b")))


@pytest.mark.parametrize("mutation", [
    {"project_ref": "project-b"},
    {"portfolio_ref": "portfolio-b"},
    {"tenant_ref": "tenant-b"},
    {"role": CoordinationRole.PROJECT_CEO},
])
def test_native_parent_inconsistent_with_scoped_owner_facts_refused(mutation):
    ceo = p(CEO_A, CoordinationRole.PROJECT_CEO)
    coo = p(COO_A, CoordinationRole.COO, parent_identity=CEO_A)
    with pytest.raises(CoordinationRefused, match="INVALID_PARENT_RELATION"):
        s(ceo, replace(coo, **mutation))


def test_native_peer_grant_exact_topic_and_expiry():
    a = p(COO_A, CoordinationRole.COO)
    b = p(COO_B, CoordinationRole.COO, project="project-b")
    grant = CoordinationGrant("grant-1", a.identity, b.identity, "schema",
                              ("project-a", "project-b"), T, T + 10)
    snap = s(a, b, grants=(grant,))
    assert decision(snap, a, b, when=T + 9).relation == "explicit_dependency_peer"
    deny(snap, a, b, topic="other")
    deny(snap, a, b, when=T + 10)
    deny(s(a, b, grants=(replace(grant, revoked=True),)), a, b)


def test_cross_portfolio_or_tenant_never_enabled_by_grant():
    a = p(COO_A, CoordinationRole.COO)
    for b in (p(COO_B, CoordinationRole.COO, project="project-b", portfolio="other"),
              p(COO_B, CoordinationRole.COO, project="project-b", tenant="other")):
        grant = CoordinationGrant("grant-1", a.identity, b.identity, "schema",
                                  ("project-a", "project-b"), T, T + 10)
        deny(s(a, b, grants=(grant,)), a, b)


def test_wrong_native_principal_does_not_reuse_old_dependency_grant():
    a = p(COO_A, CoordinationRole.COO)
    b = p(COO_B, CoordinationRole.COO, project="project-b")
    grant = CoordinationGrant("grant-1", a.identity, b.identity, "schema",
                              ("project-a", "project-b"), T, T + 10)
    rotated = replace(a, identity=replace(a.identity, principal_ref="other"))
    deny(s(rotated, b, grants=(grant,)), rotated, b)


def test_type_alias_and_fail_closed_non_actor():
    assert CoordinationNativeIdentity in CoordinationActorIdentity.__args__
    ceo = p(CEO_A, CoordinationRole.PROJECT_CEO)
    snap = s(ceo)
    for wrong in (object(), "session-id", {"role": "ceo"}):
        with pytest.raises(CoordinationRefused):
            authorize_coordination(snap, wrong, ceo.identity,
                                   topic_ref="schema", now=T + 1)
