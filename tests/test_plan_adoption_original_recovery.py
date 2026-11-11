"""Same-ID private-before-INTENT crash recovery, no second operation/material."""
from copy import deepcopy
import pytest
from tests.test_project_plan_adoption_source_owner import joined
from tests.test_agentos_plan_continuity_capture import repository
from tests.test_workspace_plan_adoption_git_publisher import isolated_git_env


def orphan(f,monkeypatch):
    real=f.events.prepare
    def crash(*args,**kwargs):raise RuntimeError('synthetic crash after private artifact')
    monkeypatch.setattr(f.events,'prepare',crash)
    with pytest.raises(RuntimeError):f.source.prepare(f.request,f.who)
    monkeypatch.setattr(f.events,'prepare',real)
    assert f.runtime.store.list_events()==[]
    return f.private.lookup_original(f.lookup,f.permissions.bind(f.who,action='ADOPT_PLAN',work_ref=f.work).principal_scope,guard=lambda:True)


def test_exact_private_orphan_restores_original_actor_day_and_basis_without_source_recapture(joined,monkeypatch):
    f=joined;retained=orphan(f,monkeypatch)
    assert retained is not None and f.state.actor_calls==1 and f.state.captures==1
    f.state.unavailable=True
    preview=f.service().prepare(f.request,f.who)
    assert preview['preview_witness']['original_input']==retained['original_input']
    assert preview['recipe_fingerprint_sha256']==retained['recipe_fingerprint_sha256']
    assert f.state.actor_calls==1 and f.state.captures==1
    assert [e.payload['kind'] for e in f.runtime.store.list_events()]==['INTENT']
    assert f.pr.create_calls==0 and f.runtime.jobs.list_jobs()==[]


@pytest.mark.parametrize('fault',['request','stamp','grant'])
def test_private_orphan_changed_original_or_permission_refuses_without_new_effect(joined,monkeypatch,fault):
    f=joined;orphan(f,monkeypatch);request=deepcopy(f.request)
    if fault=='request':request['candidate_sha256']='a'*64
    if fault=='stamp':f.bindings['profiles']['member-0']['plan_adoption']['permission_digest']='7'*64
    if fault=='grant':f.bindings['profiles']['member-0']['plan_adoption']=None
    with pytest.raises((ValueError,PermissionError)):f.service().prepare(request,f.who)
    assert f.runtime.store.list_events()==[] and f.pr.create_calls==0
    assert f.state.actor_calls==1 and f.state.captures==1
