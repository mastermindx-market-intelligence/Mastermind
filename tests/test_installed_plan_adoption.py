"""Actual fixed compiler/nominal DATA/private/Event/Git ADOPT composition.

Disposable upstream and inert PR/credential/seal fixtures only. No installed
permission, publication, service, provider or product acceptance is claimed.
"""
from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import os
import json
import pytest

from tests.test_project_plan_adoption_source_owner import joined, advance_request
from tests.test_agentos_plan_continuity_capture import repository
from tests.test_workspace_plan_adoption_git_publisher import isolated_git_env, old
from tests.test_installed_source_git_identity import identity as identity_fixture
from integrations.executive_mcp.installed import InstalledBootPacketCollector
from integrations.mastermind_workspace_app.canonical_project_data import InstalledCanonicalProjectData
from integrations.mastermind_workspace_app.installed_plan_adoption import build_plan_adoption_owner
from integrations.mastermind_workspace_app.project_authoring_grant import SCHEMA_V5
from control_plane.workspace_project_git_publisher import PublisherBinding


def sha(raw): return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def installed(joined, tmp_path, monkeypatch):
    f = joined
    # The installed reader child already carries PYTHONDONTWRITEBYTECODE=1.
    # This in-process real-reader seam must preserve that same physical law.
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    proposal_path='research/project-plans/PLAN-PLAN-TEST-'+'8'*40+'.md'
    f.repo['ws']['artifacts']=['macro:'+proposal_path]
    f.repo['put_record']('agentos/workstreams/WS-PLAN-TEST.md',f.repo['ws'])
    f.repo['git']('rm','planning/proposal.md')
    candidate_record = deepcopy(f.repo['ws'])
    candidate_record['next_action'] = 'Compare the exact planning waves.'
    candidate_record['waves'] = [{'id':'W1','title':'Qualified planning wave','status':'todo'}]
    candidate = f.repo['owner']._yaml_frontmatter(candidate_record).encode()
    f.repo['write'](proposal_path, f.repo['owner']._yaml_frontmatter(
        dict(f.repo['header'],candidate_sha256=sha(candidate))).encode() + candidate)
    code = f.repo['commit'](); f.repo['git']('push','origin','main')
    request = dict(f.request,expected_commit=code,candidate_sha256=sha(candidate),
        proposal_source=dict(f.request['proposal_source'],path=proposal_path,commit=code,
            content_sha256=sha(f.repo['git']('show',code+':'+proposal_path))))
    code_root = tmp_path/'immutable-code'
    old.git(tmp_path,'clone',str(f.origin),str(code_root))
    source = tmp_path/'mastermind-source';source.mkdir();(source/'README.md').write_text('Synthetic sealed source\n')
    old.git(source,'init','-q');old.git(source,'add','.');old.git(source,'commit','-m','Synthetic source seal')
    source_sha=old.rev_parse(source,'HEAD')
    collector=InstalledBootPacketCollector(source_root=source,macro_root=code_root,
        code_root=Path(__file__).parents[1],python_executable=Path(sys.executable),expected_source_sha=source_sha)
    from integrations.executive_mcp import installed as module
    def synthetic_root_seal(env,*,deadline=None,snapshot_capture=None):
        observed=module._clean_git_snapshot(code_root,runner=collector._runner,env=env,
            label='Macro source',content_scope='macro_brief',include_seal=True,deadline=deadline,
            snapshot_capture=snapshot_capture,_allow_synthetic_fixture=True)
        return source_sha,observed[0],'synthetic-test-root-seal',observed[1]
    monkeypatch.setattr(collector,'_snapshot_pair',synthetic_root_seal)
    directory=tmp_path/'identity';directory.mkdir()
    identity=identity_fixture.__wrapped__(directory,monkeypatch)[0]
    identity.binding=PublisherBinding(worktree=str(f.clone),expected_origin=str(f.origin),
        default_branch='main',publisher_identity='synthetic-qualified-identity')
    monkeypatch.setattr(identity,'qualify',lambda binding:binding==identity.binding)
    monkeypatch.setattr(identity,'find',f.pr.find);monkeypatch.setattr(identity,'create',f.pr.create)
    f.bindings['schema']=SCHEMA_V5
    for slot in f.bindings['profiles'].values():
        slot['project_plan_proposal_publish']=None;slot['project_canonical_data_read']=None
    f.bindings['profiles']['member-0']['project_canonical_data_read']='6'*64
    data=InstalledCanonicalProjectData(collector=collector,policy=f.policy,load_bindings=lambda:f.bindings,
        git_identity=identity,events=f.events,runtime_guard=lambda:True)
    owner=build_plan_adoption_owner(collector=collector,data=data,events=f.events,private_inputs=f.private,
        contexts=f.permissions,git_identity=identity)
    return type('Fixture',(),dict(f=f,request=request,source=owner,data=data,collector=collector,
        code=code,candidate=candidate,record=candidate_record,identity=identity))()


def test_real_installed_prepare_publish_reconcile_advance_and_nominal_read(installed):
    j=installed;f=j.f
    initial_read=j.data.view(f.who,work_ref=f.work).read_plan(work_ref=f.work)
    preview=j.source.prepare(j.request,f.who)
    assert set(preview['preview']['changed_frontmatter_fields']) <= {'waves','next_action'}
    assert preview['preview']['record_body_changed'] is False
    pending=j.source.submit(lookup=f.lookup,preview_witness=preview['preview_witness'],principal=f.who)
    assert pending['receipt']['kind']=='PROPOSAL_OBSERVED'
    pending_candidate=deepcopy(pending)
    f.merge(pending)
    ready=j.source.reconcile(f.lookup,f.who)
    assert ready['reason']=='READY_FOR_ADVANCE'
    # Candidate publication has no effect on current accepted content.
    before=j.data.view(f.who,work_ref=f.work)
    assert before.read_plan(work_ref=f.work)['continuity']['adoption']['decision_ref']=='DEC:PLAN-FIRST'
    pending=j.source.advance(advance_request(f,ready),f.who)
    assert pending['phase']=='ADOPTION' and pending['disposition']=='unknown'
    pending_adoption=deepcopy(pending)
    f.merge(pending)
    accepted=j.source.reconcile(f.lookup,f.who)
    assert accepted['disposition']=='accepted' and accepted['receipt']['kind']=='SOURCE_OBSERVED'
    view=j.data.view(f.who,work_ref=f.work);body=view.read_plan(work_ref=f.work)
    assert view.code_commit==j.code and view.data_commit!=j.code
    assert view.witness()['source_operation']['selection']['action']=='ADOPT_PLAN'
    assert body['plan']['objective']==f.repo['ws']['objective']
    assert body['plan']['waves'][0]['title']=='Qualified planning wave'
    adopted=body['continuity']['adoption']
    assert adopted['state']=='AVAILABLE' and adopted['adoption']['predecessor']=='DEC:PLAN-FIRST'
    item=body['continuity']['proposals']['items'][0]
    assert item['adoption_relation']=='CURRENT_DECISION_REFERENCES_PROPOSAL'
    assert item['comparison']['candidate_text'].encode()==j.candidate
    assert f.pr.create_calls==2 and f.runtime.jobs.list_jobs()==[]
    destination=os.environ.get('MM_ADOPT_READ_FIXTURE')
    if destination:
        Path(destination).write_text(json.dumps(dict(body=body,witness=view.witness(),status=accepted,initial_read=initial_read,request=j.request,preview=preview,context=f.permissions.bind(f.who,action='ADOPT_PLAN',work_ref=f.work).public_context(),pending_candidate=pending_candidate,ready=ready,pending_adoption=pending_adoption),ensure_ascii=False,sort_keys=True))


def test_installed_basic_adoption_refuses_current_objective_body_and_foreign_actor(installed):
    j=installed;f=j.f
    snapshot=j.source._capture(j.request,f.who,'CANDIDATE')
    actor=j.source._actor(f.who,j.request,snapshot)
    prepared=j.source._adapter.prepare(request=j.request,initial_snapshot=snapshot,actor=actor)
    recipe=j.source._adapter.candidate_recipe(prepared)
    assert j.source._qualify_recipe(f.who,prepared,recipe,'CANDIDATE')
    foreign=deepcopy(actor);foreign['principal_id']='f'*64
    altered=j.source._adapter.prepare(request=j.request,initial_snapshot=snapshot,actor=foreign)
    assert not j.source._qualify_recipe(f.who,altered,j.source._adapter.candidate_recipe(altered),'CANDIDATE')
    for field,value in [('objective','Changed project scope'),('owner','foreign-owner'),(None,'Changed body')]:
        record=dict(j.record)
        if field is not None:record[field]=value
        raw=f.repo['owner']._yaml_frontmatter(record).encode()+(b'Changed body\n' if field is None else b'')
        changed=deepcopy(snapshot)
        header=dict(f.repo['header'],candidate_sha256=sha(raw))
        proposal=f.repo['owner']._yaml_frontmatter(header).encode()+raw
        changed['snapshot']['proposal']['raw_bytes']=proposal
        changed['snapshot']['proposal']['source']['content_sha256']=sha(proposal)
        changed['snapshot']['candidate_target']['path']=j.request['proposal_source']['path'][:-3]+'.candidate-'+sha(raw)[:20]+'.md'
        request=dict(j.request,candidate_sha256=sha(raw),proposal_source=deepcopy(changed['snapshot']['proposal']['source']))
        p=j.source._adapter.prepare(request=request,initial_snapshot=changed,actor=actor)
        assert not j.source._qualify_recipe(f.who,p,j.source._adapter.candidate_recipe(p),'CANDIDATE')
    assert f.runtime.store.list_events()==[] and f.pr.create_calls==0


def test_initial_current_data_may_advance_without_executing_data_code(installed):
    j=installed;f=j.f
    f.repo['write']('docs/unrelated.md',b'Unrelated current DATA\n')
    current=f.repo['commit']();f.repo['git']('push','origin','main')
    request=dict(j.request,expected_commit=current,proposal_source=dict(j.request['proposal_source'],commit=current))
    preview=j.source.prepare(request,f.who)
    permission=f.permissions.bind(f.who,action='ADOPT_PLAN',work_ref=f.work)
    original=f.private.lookup_original(f.lookup,permission.principal_scope,guard=permission.check)
    payload=original['private_payload']
    assert payload['source_binding']['compiler']['commit']==j.code
    assert payload['initial_snapshot']['snapshot']['commit']==current
    assert payload['initial_snapshot']['canonical_data']['executable_macro_commit']==j.code
    assert payload['initial_snapshot']['canonical_data']['canonical_data_commit']==current
    assert preview['preview']['expected_commit']==current and current!=j.code
    assert f.pr.create_calls==0 and f.runtime.jobs.list_jobs()==[]


@pytest.mark.parametrize('fault',['current_ws','adopt_grant'])
def test_ready_original_is_retained_when_current_source_or_adopt_permission_changes(installed,fault):
    j=installed;f=j.f
    preview=j.source.prepare(j.request,f.who)
    pending=j.source.submit(lookup=f.lookup,preview_witness=preview['preview_witness'],principal=f.who)
    f.merge(pending);ready=j.source.reconcile(f.lookup,f.who)
    assert ready['reason']=='READY_FOR_ADVANCE'
    before=len(f.runtime.store.list_events())
    if fault=='current_ws':
        record=dict(f.repo['ws'],next_action='Independent current owner change')
        f.repo['put_record']('agentos/workstreams/WS-PLAN-TEST.md',record)
        f.repo['commit']();f.repo['git']('push','origin','main')
    else:f.bindings['profiles']['member-0']['plan_adoption']=None
    with pytest.raises((ValueError,PermissionError)):
        j.source.advance(advance_request(f,ready),f.who)
    assert len(f.runtime.store.list_events())==before and f.pr.create_calls==1
    assert f.events.read_status(f.lookup,ready['owner_context']['principal_scope'],guard=lambda:True)==ready
