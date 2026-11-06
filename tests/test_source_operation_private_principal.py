"""Private carrier qualification; no claim of a real socket peer or enrollment."""
import pytest
from dataclasses import FrozenInstanceError

from integrations.mastermind_workspace_app.contract import principal_frame
from integrations.mastermind_workspace_app.owner_context import workspace_principal_scope
from integrations.mastermind_workspace_app.source_operation_principal import (
    bind_private_source_principal, source_principal_frame, source_principal_scope)
from integrations.mastermind_workspace_app.source_operation_context import WorkspaceSourceOperationContextFactory
from integrations.mastermind_workspace_app.project_proposal_request import build_proposal_request
from tests.test_workspace_project_authoring_grant import project_bindings, verified
from tests.test_workspace_member_bindings import principal


def test_private_peer_carrier_matches_verified_frame_without_reconstructing_identity():
    policy, source = project_bindings()
    who = verified(policy, principal(source))
    frame = principal_frame(who)
    peer = [True]
    carried = bind_private_source_principal(frame, verified_expires_at=who.expires_at, peer_guard=lambda: peer[0])
    with pytest.raises(FrozenInstanceError):
        carried.expires_at += 1000
    frame["subject_digest"] = "foreign"
    assert source_principal_frame(carried) == principal_frame(who)
    assert source_principal_scope(carried) == workspace_principal_scope(who)
    with pytest.raises(ValueError):
        source_principal_scope(principal_frame(who))
    peer[0] = False
    with pytest.raises(PermissionError):
        source_principal_scope(carried)


def test_private_context_reloads_same_distinct_grant_and_original_token_deadline():
    policy, source = project_bindings()
    who = verified(policy, principal(source))
    clock = [who.expires_at - 1]
    carried = bind_private_source_principal(principal_frame(who), verified_expires_at=who.expires_at,
                                            peer_guard=lambda: True)
    factory = WorkspaceSourceOperationContextFactory(policy=policy, load_bindings=lambda: source, now=lambda: clock[0])
    permission = factory.bind(carried, action="publish_project_proposal", work_ref=None)
    assert permission.check() and permission.principal_scope == workspace_principal_scope(who)
    clock[0] = who.expires_at
    assert not permission.check()
    clock[0] -= 1
    source["profiles"]["member-0"]["project_authoring"] = None
    assert not permission.check()
    with pytest.raises(PermissionError):
        factory.bind(carried, action="ADOPT_PLAN", work_ref="WS:TEST")


@pytest.mark.parametrize("change", [
    {"verified_expires_at": True}, {"verified_expires_at": -1},
    {"peer_guard": lambda: False},
])
def test_private_carrier_rejects_invalid_deadline_or_absent_peer(change):
    policy, source = project_bindings()
    who = verified(policy, principal(source))
    with pytest.raises(ValueError):
        bind_private_source_principal(principal_frame(who), **({
            "verified_expires_at": who.expires_at, "peer_guard": lambda: True} | change))
