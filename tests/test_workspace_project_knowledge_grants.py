"""File and communication edits have independent exact-project grants."""
import pytest
from integrations.mastermind_workspace_app.project_authoring_grant import (
    ADD_PROJECT_FILE_ACTION, SET_PROJECT_PREFERENCE_ACTION, workspace_project_authorizers,
    validate_project_bindings, _ACTION_FIELDS)
from tests.test_workspace_project_suspend_grant import fixture
from tests.test_workspace_member_bindings import principal


def gate(policy, source, action, work='WS:SYNTHETIC-PROJECT'):
    return workspace_project_authorizers(policy=policy, load_bindings=lambda: source, action=action, work_ref=work)[1]


@pytest.mark.parametrize('action,field', [(ADD_PROJECT_FILE_ACTION,'project_file_add'),
                                         (SET_PROJECT_PREFERENCE_ACTION,'project_preference_set')])
def test_knowledge_action_requires_distinct_exact_project_receipt(action,field):
    policy, source=fixture(); who=principal(source)
    assert not gate(policy,source,action)(who)
    source['profiles']['member-0'][field]={'work_ref':'WS:SYNTHETIC-PROJECT','permission_digest':'4'*64}
    assert gate(policy,source,action)(who)
    assert not gate(policy,source,action,'WS:OTHER-PROJECT')(who)
    assert not gate(policy,source,action)(principal(source,'member-1'))
    source['profiles']['member-0'][field]=None
    assert not gate(policy,source,action)(who)


@pytest.mark.parametrize('other', list(_ACTION_FIELDS.values()))
def test_no_action_receipt_can_be_reused_to_add_file(other):
    if other=='project_file_add': return
    policy,source=fixture();slot=source['profiles']['member-0']
    slot['project_file_add']={'work_ref':'WS:SYNTHETIC-PROJECT','permission_digest':'4'*64}
    slot[other]='4'*64 if other=='project_authoring' else {'work_ref':'WS:SYNTHETIC-PROJECT','permission_digest':'4'*64}
    with pytest.raises(ValueError): validate_project_bindings(source,policy)


def test_read_receipt_and_file_grant_do_not_grant_communication_edit():
    policy, source=fixture();who=principal(source)
    source['profiles']['member-0']['project_file_add']={'work_ref':'WS:SYNTHETIC-PROJECT','permission_digest':'4'*64}
    assert not gate(policy,source,SET_PROJECT_PREFERENCE_ACTION)(who)
    with pytest.raises(ValueError):
        workspace_project_authorizers(policy=policy,load_bindings=lambda:source,action=SET_PROJECT_PREFERENCE_ACTION)
