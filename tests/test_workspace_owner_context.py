"""Scope comes from the existing authenticated Workspace identity only."""
import hashlib

import pytest

from common.executive_workspace_contract import canonical
from integrations.mastermind_workspace_app.owner_context import workspace_owner_context, workspace_principal_scope
from integrations.mastermind_workspace_app.contract import principal_frame
from tests.test_workspace_project_authoring_grant import project_bindings, verified
from tests.test_workspace_member_bindings import principal


def test_exact_verified_workspace_frame_is_shared_operation_scope():
    policy, bindings = project_bindings()
    who = verified(policy, principal(bindings))
    expected = hashlib.sha256(canonical(principal_frame(who))).hexdigest()
    assert workspace_owner_context(who) == {"principal_scope": expected}
    assert workspace_principal_scope(who) == expected
    detached = workspace_owner_context(who)
    detached["principal_scope"] = "changed"
    assert workspace_principal_scope(who) == expected


def test_distinct_workspace_members_do_not_share_unresolved_operation_scope():
    policy, bindings = project_bindings()
    first = verified(policy, principal(bindings))
    other = verified(policy, principal(bindings, "member-1"))
    assert workspace_principal_scope(first) != workspace_principal_scope(other)


@pytest.mark.parametrize("value", [{}, {"principal_scope": "a" * 64}, {"signed_in": True}, None])
def test_public_auth_or_caller_assertion_is_not_verified_workspace_context(value):
    with pytest.raises(ValueError, match="access_denied"):
        workspace_owner_context(value)
