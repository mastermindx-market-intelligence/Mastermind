"""Plan adoption is an independent same-project grant, never source creation."""
import pytest

from integrations.mastermind_workspace_app.project_authoring_grant import (
    PLAN_ADOPT_ACTION, PROJECT_SUSPEND_ACTION, validate_project_bindings, workspace_project_authorizers,
)
from integrations.mastermind_workspace_app.contract import permission_stamp
from tests.test_workspace_member_bindings import principal
from tests.test_workspace_project_suspend_grant import fixture, SUSPEND
from tests.test_workspace_project_authoring_grant import GRANT


def gate(policy, source, action=PLAN_ADOPT_ACTION, work_ref="WS:SYNTHETIC-PROJECT"):
    return workspace_project_authorizers(policy=policy, load_bindings=lambda: source,
        action=action, work_ref=work_ref)[1]


def test_creation_and_suspension_never_implicitly_adopt_a_plan():
    policy, source = fixture()
    who = principal(source)
    author = workspace_project_authorizers(policy=policy, load_bindings=lambda: source)[1]
    assert author(who) is True and gate(policy, source, PROJECT_SUSPEND_ACTION)(who) is True
    assert gate(policy, source)(who) is False
    source["profiles"]["member-0"]["plan_adoption"] = {"work_ref": "WS:SYNTHETIC-PROJECT", "permission_digest": "8" * 64}
    assert gate(policy, source)(who) is True
    assert gate(policy, source, work_ref="WS:OTHER-PROJECT")(who) is False
    assert gate(policy, source)(principal(source, "member-1")) is False
    source["profiles"]["member-0"]["project_authoring"] = None
    assert gate(policy, source)(who) is True and author(who) is False


def test_adoption_rotation_and_revocation_do_not_change_suspension():
    policy, source = fixture()
    who = principal(source)
    source["profiles"]["member-0"]["plan_adoption"] = {"work_ref": "WS:SYNTHETIC-PROJECT", "permission_digest": "8" * 64}
    adopted, paused = gate(policy, source), gate(policy, source, PROJECT_SUSPEND_ACTION)
    old_adopt, old_pause = permission_stamp(adopted, who), permission_stamp(paused, who)
    assert old_adopt != old_pause
    source["profiles"]["member-0"]["plan_adoption"]["permission_digest"] = "9" * 64
    assert permission_stamp(adopted, who) != old_adopt and permission_stamp(paused, who) == old_pause
    source["profiles"]["member-0"]["plan_adoption"] = None
    assert adopted(who) is False and permission_stamp(paused, who) == old_pause


@pytest.mark.parametrize("digest", [GRANT, SUSPEND["permission_digest"], "F" * 64])
def test_reused_or_malformed_adoption_receipts_are_not_authority(digest):
    policy, source = fixture()
    source["profiles"]["member-0"]["plan_adoption"] = {"work_ref": "WS:SYNTHETIC-PROJECT", "permission_digest": digest}
    with pytest.raises(ValueError): validate_project_bindings(source, policy)


def test_adoption_requires_an_explicit_project_scope():
    policy, source = fixture()
    with pytest.raises(ValueError):
        workspace_project_authorizers(policy=policy, load_bindings=lambda: source, action=PLAN_ADOPT_ACTION)
