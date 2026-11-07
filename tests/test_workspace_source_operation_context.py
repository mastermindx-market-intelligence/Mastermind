"""Actual sealed membership authorizers, no grant issuance or installed reads."""
import copy
import pytest

from integrations.mastermind_workspace_app.source_operation_context import WorkspaceSourceOperationPermission
from integrations.mastermind_workspace_app.owner_context import workspace_owner_context
from tests.test_workspace_project_authoring_grant import project_bindings, verified
from tests.test_workspace_member_bindings import principal


def bound(source_action="ADOPT_PLAN", field="plan_adoption"):
    policy, source = project_bindings()
    source["profiles"]["member-0"][field] = {"work_ref": "WS:TEST", "permission_digest": "f" * 64}
    who = verified(policy, principal(source))
    permission = WorkspaceSourceOperationPermission(policy=policy, load_bindings=lambda: source,
        principal=who, action=source_action, work_ref="WS:TEST")
    return source, who, permission


def test_real_owner_scope_and_inspection_do_not_need_macro_or_display_identity():
    _, who, permission = bound()
    assert permission.public_context() == {
        "schema": "mastermind.workspace_source_operation_context.v1",
        "selection": {"action": "ADOPT_PLAN", "work_ref": "WS:TEST"},
        "owner_context": workspace_owner_context(who), "can_inspect": True}
    assert permission.principal_scope == workspace_owner_context(who)["principal_scope"]
    assert permission.permission_binding_digest != permission.principal_scope


def test_revocation_or_binding_rotation_withdraws_original_context():
    source, _, permission = bound()
    source["profiles"]["member-0"]["plan_adoption"] = None
    assert not permission.check()
    with pytest.raises(PermissionError): permission.public_context()
    with pytest.raises(PermissionError): _ = permission.permission_binding_digest


@pytest.mark.parametrize("action", ["ADOPT_PLAN", "ACCEPT_DIRECTION", "add_project_file",
                                    "set_project_communication_preference"])
def test_create_or_read_grant_does_not_grant_other_source_action(action):
    policy, source = project_bindings()
    who = verified(policy, principal(source))
    with pytest.raises(PermissionError):
        WorkspaceSourceOperationPermission(policy=policy, load_bindings=lambda: source,
            principal=who, action=action, work_ref="WS:TEST")


@pytest.mark.parametrize("caller", [{}, {"signed_in": True}, {"principal_scope": "a" * 64}])
def test_unverified_public_identity_is_not_an_owner_context(caller):
    policy, source = project_bindings()
    with pytest.raises(ValueError):
        WorkspaceSourceOperationPermission(policy=policy, load_bindings=lambda: source,
            principal=caller, action="ADOPT_PLAN", work_ref="WS:TEST")


def test_same_current_grant_is_scoped_to_exact_work():
    source, who, _ = bound()
    policy, _ = project_bindings()
    with pytest.raises(PermissionError):
        WorkspaceSourceOperationPermission(policy=policy, load_bindings=lambda: source,
            principal=who, action="ADOPT_PLAN", work_ref="WS:OTHER")


def test_actual_token_expiry_withdraws_source_guard_before_further_effects():
    source, who, _ = bound()
    policy, _ = project_bindings()
    clock = [who.expires_at - 1]
    permission = WorkspaceSourceOperationPermission(policy=policy, load_bindings=lambda: source,
        principal=who, action="ADOPT_PLAN", work_ref="WS:TEST", now=lambda: clock[0])
    assert permission.check()
    clock[0] = who.expires_at
    assert not permission.check()
    with pytest.raises(PermissionError): permission.public_context()
