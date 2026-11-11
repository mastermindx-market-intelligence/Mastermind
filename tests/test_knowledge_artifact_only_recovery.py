"""Actual private artifact-only interruption; no invented Event/no-effect proof."""
import copy
import pytest
from tests.test_knowledge_source_service import owner, env, isolated_git_env, selection
from tests.test_workspace_project_git_publisher import git
from control_plane.workspace_source_operations import SourceOperationConflict


@pytest.mark.parametrize('changed',['none','payload','stamp'])
def test_prepare_recovers_exact_preintent_actor_date_and_basis(owner,monkeypatch,changed):
    o=owner; service=o['service']; real_prepare=o['events'].prepare
    def interrupted(*args,**kwargs):raise RuntimeError('inert crash before INTENT')
    monkeypatch.setattr(o['events'],'prepare',interrupted)
    with pytest.raises(RuntimeError):service.prepare(o['request'],o['who'])
    assert o['runtime'].store.list_events()==[] and o['pr'].create_calls==0
    monkeypatch.setattr(o['events'],'prepare',real_prepare)
    service._date=lambda:pytest.fail('recovery regenerated original date')
    request=copy.deepcopy(o['request'])
    if changed=='payload':request['file']['content_utf8']='different'
    elif changed=='stamp':o['bindings']['profiles']['member-0']['project_file_add']['permission_digest']='8'*64
    if changed!='none':
        with pytest.raises((SourceOperationConflict,PermissionError)):service.prepare(request,o['who'])
        assert o['runtime'].store.list_events()==[] and o['pr'].create_calls==0
        return
    (o['env'].clone/'unrelated.md').write_text('Later canonical context\n')
    git(o['env'].clone,'add','unrelated.md');git(o['env'].clone,'commit','-m','Advance unrelated source')
    preview=service.prepare(request,o['who'])
    assert preview['preview']['source_commit']==request['source_commit']
    assert o['calls']==['prepare','restore']
    assert [e.payload['kind'] for e in o['runtime'].store.list_events()]==['INTENT']
    again=service.prepare(request,o['who'])
    assert again==preview and len(o['runtime'].store.list_events())==1
    assert o['pr'].create_calls==0 and o['runtime'].jobs.list_jobs()==[]
