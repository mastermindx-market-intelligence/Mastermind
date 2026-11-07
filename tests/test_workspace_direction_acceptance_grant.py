"""Direction acceptance is explicit and independent of the other project actions."""
import pytest
from integrations.mastermind_workspace_app.project_authoring_grant import (
    ACCEPT_DIRECTION_ACTION, PLAN_ADOPT_ACTION, validate_project_bindings, workspace_project_authorizers,
)
from integrations.mastermind_workspace_app.contract import permission_stamp
from tests.test_workspace_project_suspend_grant import fixture, SUSPEND
from tests.test_workspace_project_authoring_grant import GRANT
from tests.test_workspace_member_bindings import principal


def gate(policy, source, action=ACCEPT_DIRECTION_ACTION, work_ref="WS:SYNTHETIC-PROJECT"):
    return workspace_project_authorizers(policy=policy, load_bindings=lambda: source, action=action, work_ref=work_ref)[1]


def test_direction_requires_its_own_exact_project_receipt():
    policy, source = fixture()
    who = principal(source)
    source["profiles"]["member-0"]["plan_adoption"] = {"work_ref": "WS:SYNTHETIC-PROJECT", "permission_digest": "8" * 64}
    assert gate(policy, source)(who) is False
    source["profiles"]["member-0"]["direction_acceptance"] = {"work_ref": "WS:SYNTHETIC-PROJECT", "permission_digest": "5" * 64}
    assert gate(policy, source)(who) is True and gate(policy, source, work_ref="WS:OTHER-PROJECT")(who) is False
    assert gate(policy, source)(principal(source, "member-1")) is False
    adopt_stamp = permission_stamp(gate(policy, source, PLAN_ADOPT_ACTION), who)
    source["profiles"]["member-0"]["direction_acceptance"] = None
    assert gate(policy, source)(who) is False and permission_stamp(gate(policy, source, PLAN_ADOPT_ACTION), who) == adopt_stamp


@pytest.mark.parametrize("digest", [GRANT, SUSPEND["permission_digest"], "8" * 64])
def test_other_action_receipts_cannot_accept_direction(digest):
    policy, source = fixture()
    source["profiles"]["member-0"]["plan_adoption"] = {"work_ref": "WS:SYNTHETIC-PROJECT", "permission_digest": "8" * 64}
    source["profiles"]["member-0"]["direction_acceptance"] = {"work_ref": "WS:SYNTHETIC-PROJECT", "permission_digest": digest}
    with pytest.raises(ValueError): validate_project_bindings(source, policy)


def test_direction_action_without_scope_is_not_a_permission():
    policy, source = fixture()
    with pytest.raises(ValueError):
        workspace_project_authorizers(policy=policy, load_bindings=lambda: source, action=ACCEPT_DIRECTION_ACTION)
