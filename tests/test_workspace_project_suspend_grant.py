"""Only an explicit same-project receipt grants admission suspension."""
import copy

import pytest

from integrations.mastermind_workspace_app.project_authoring_grant import (
    PROJECT_SUSPEND_ACTION, validate_project_bindings, workspace_project_authorizers, legacy_workspace_document,
)
from integrations.mastermind_workspace_app.contract import permission_stamp
from tests.test_workspace_member_bindings import principal
from tests.test_workspace_project_authoring_grant import project_bindings, GRANT

SUSPEND = {"work_ref": "WS:SYNTHETIC-PROJECT", "permission_digest": "6" * 64}


def fixture():
    policy, source = project_bindings()
    source["profiles"]["member-0"]["project_admission_suspend"] = dict(SUSPEND)
    return policy, source


def gates(policy, source, work_ref="WS:SYNTHETIC-PROJECT"):
    return workspace_project_authorizers(policy=policy, load_bindings=lambda: source,
        action=PROJECT_SUSPEND_ACTION, work_ref=work_ref)[1]


def test_project_scope_and_source_authority_remain_independent():
    policy, source = fixture()
    first, second = principal(source), principal(source, "member-1")
    selected, foreign = gates(policy, source), gates(policy, source, "WS:OTHER-PROJECT")
    assert selected(first) is True and selected(second) is False and foreign(first) is False
    author = workspace_project_authorizers(policy=policy, load_bindings=lambda: source)[1]
    assert author(first) is True
    author_stamp = permission_stamp(author, first)
    suspend_stamp = permission_stamp(selected, first)
    source["profiles"]["member-0"]["project_admission_suspend"]["permission_digest"] = "7" * 64
    assert permission_stamp(selected, first) != suspend_stamp
    assert permission_stamp(author, first) == author_stamp
    source["profiles"]["member-0"]["project_admission_suspend"] = None
    assert selected(first) is False and author(first) is True


def test_author_and_read_grants_do_not_authorize_pause():
    policy, source = project_bindings()
    assert gates(policy, source)(principal(source)) is False
    source["profiles"]["member-0"]["project_authoring"] = None
    source["profiles"]["member-0"]["project_admission_suspend"] = dict(SUSPEND)
    assert gates(policy, source)(principal(source)) is True
    assert workspace_project_authorizers(policy=policy, load_bindings=lambda: source)[1](principal(source)) is False


@pytest.mark.parametrize("grant", [
    "6" * 64, {}, {"permission_digest": "6" * 64},
    {**SUSPEND, "root_job_id": "JOB-001"}, {**SUSPEND, "work_ref": "WS:BAD\n"},
    {**SUSPEND, "permission_digest": GRANT}, {**SUSPEND, "permission_digest": "F" * 64},
])
def test_malformed_or_reused_pause_grants_fail_closed(grant):
    policy, source = fixture()
    source["profiles"]["member-0"]["project_admission_suspend"] = grant
    with pytest.raises(ValueError):
        validate_project_bindings(source, policy)


def test_scope_retarget_and_disabled_member_revoke_immediately_and_returned_grant_is_detached():
    policy, source = fixture()
    who = principal(source)
    authorize = gates(policy, source)
    detached = validate_project_bindings(source, policy)
    detached["profiles"]["member-0"]["project_admission_suspend"]["work_ref"] = "WS:OTHER-PROJECT"
    assert authorize(who) is True
    source["profiles"]["member-0"]["project_admission_suspend"]["work_ref"] = "WS:OTHER-PROJECT"
    assert authorize(who) is False
    source["profiles"]["member-0"]["project_admission_suspend"] = None
    source["profiles"]["member-0"]["project_authoring"] = None
    source["profiles"]["member-0"]["control_room_actions"] = {k: None for k in source["profiles"]["member-0"]["control_room_actions"]}
    source["profiles"]["member-0"]["enabled"] = False
    assert authorize(who) is False


def test_missing_scope_or_unknown_action_is_not_a_grant():
    policy, source = fixture()
    for kwargs in ({"action": PROJECT_SUSPEND_ACTION}, {"action": "resume_project"},
                   {"action": "publish_project_proposal", "work_ref": "WS:SYNTHETIC-PROJECT"}):
        with pytest.raises(ValueError):
            workspace_project_authorizers(policy=policy, load_bindings=lambda: source, **kwargs)


def test_explicit_legacy_composition_preserves_actual_read_and_action_stamps():
    from integrations.mastermind_workspace_app.contract import workspace_authorizers, workspace_control_room_authorizers
    from tests.test_workspace_control_room_action_grants import compile_source
    policy, _, _, legacy = compile_source()
    _, source = fixture()
    who = principal(source)
    _, before_read = workspace_authorizers(policy=policy, load_bindings=lambda: legacy)
    _, after_read = workspace_authorizers(policy=policy, load_bindings=lambda: legacy_workspace_document(source, policy))
    assert permission_stamp(before_read, who) == permission_stamp(after_read, who)
    _, before_action = workspace_control_room_authorizers(policy=policy, load_bindings=lambda: legacy, action="open")
    _, after_action = workspace_control_room_authorizers(policy=policy,
        load_bindings=lambda: legacy_workspace_document(source, policy), action="open")
    assert permission_stamp(before_action, who) == permission_stamp(after_action, who)
    source["profiles"]["member-0"]["project_admission_suspend"] = None
    assert permission_stamp(before_read, who) == permission_stamp(after_read, who)
