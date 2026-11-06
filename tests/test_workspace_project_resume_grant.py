"""Pause does not authorize Resume; both retain their exact selected WS."""
import pytest
from integrations.mastermind_workspace_app.project_authoring_grant import (
    PROJECT_RESUME_ACTION, PROJECT_SUSPEND_ACTION, validate_project_bindings, workspace_project_authorizers,
)
from integrations.mastermind_workspace_app.contract import permission_stamp
from tests.test_workspace_project_suspend_grant import fixture, SUSPEND
from tests.test_workspace_project_authoring_grant import GRANT
from tests.test_workspace_member_bindings import principal


def gate(policy, source, action=PROJECT_RESUME_ACTION, work_ref="WS:SYNTHETIC-PROJECT"):
    return workspace_project_authorizers(policy=policy, load_bindings=lambda: source, action=action, work_ref=work_ref)[1]


def test_pause_alone_never_resumes_admission_and_resume_stays_project_scoped():
    policy, source = fixture()
    who = principal(source)
    paused = gate(policy, source, PROJECT_SUSPEND_ACTION)
    assert paused(who) is True and gate(policy, source)(who) is False
    source["profiles"]["member-0"]["project_admission_resume"] = {"work_ref": "WS:SYNTHETIC-PROJECT", "permission_digest": "4" * 64}
    assert gate(policy, source)(who) is True and gate(policy, source, work_ref="WS:OTHER-PROJECT")(who) is False
    before = permission_stamp(paused, who)
    source["profiles"]["member-0"]["project_admission_resume"] = None
    assert gate(policy, source)(who) is False and permission_stamp(paused, who) == before


@pytest.mark.parametrize("digest", [GRANT, SUSPEND["permission_digest"]])
def test_other_project_action_receipts_do_not_resume_admission(digest):
    policy, source = fixture()
    source["profiles"]["member-0"]["project_admission_resume"] = {"work_ref": "WS:SYNTHETIC-PROJECT", "permission_digest": digest}
    with pytest.raises(ValueError): validate_project_bindings(source, policy)


def test_resume_requires_an_explicit_scope():
    policy, source = fixture()
    with pytest.raises(ValueError):
        workspace_project_authorizers(policy=policy, load_bindings=lambda: source, action=PROJECT_RESUME_ACTION)
