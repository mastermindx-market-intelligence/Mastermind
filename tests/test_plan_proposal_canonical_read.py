"""Actual canonical compiler -> same Git publisher -> configured S5 READ.

Disposable bare Git upstream, inert PR and authorization callbacks. This proves
source behavior, not protected/live publication or an enrolled grant. Default
landing is simulated by a separate upstream actor, never by the publisher.
"""
from copy import deepcopy
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import zlib
import pytest
from control_plane import workspace_project_git_publisher as p
from control_plane.project_plan_proposal_git import BINDING_SCHEMA,ACTION,LOOKUP_SCHEMA
from control_plane.project_canonical_data import CanonicalDataUnavailable
from control_plane.executive_runtime import Runtime
from control_plane.workspace_source_operations import SourceOperationEvents
from tests.test_workspace_source_operations import REF
from control_plane.agentos_project_plan import read_from_macro_owner
from tests.test_agentos_plan_continuity_capture import repository
from tests.test_workspace_plan_adoption_git_publisher import old,env,isolated_git_env

def sha(raw):return hashlib.sha256(raw if type(raw) is bytes else raw.encode()).hexdigest()
def modules(repo):
 fixture=json.loads((Path(__file__).parent/'fixtures/agentos-plan-proposal-7c54.json').read_bytes())
 result={}
 for item in fixture['files']:
  raw=zlib.decompress(base64.b64decode(item['zlib_base64'],validate=True));assert sha(raw)==item['sha256']
  assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==item['blob']
  repo['write'](item['path'],raw)
  spec=importlib.util.spec_from_file_location('proposal_test_'+Path(item['path']).stem,repo['root']/item['path']);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);result[Path(item['path']).stem]=module
 return result
@pytest.fixture
def ready(env,repository):
 repo=repository;loaded=modules(repo);compiler=loaded['agentos_plan_proposal_recipe'];decoder=loaded['agentos_plan_proposal'];owner=repo['owner']
 repo['ws']['artifacts']=[];repo['put_record']('agentos/workstreams/WS-PLAN-TEST.md',repo['ws']);repo['head']=repo['commit']()
 # Original configured root and publisher clone both remain on this code pin.
 old.git(env.seed,'fetch',str(repo['root']),repo['head']);old.git(env.seed,'merge','--allow-unrelated-histories','-m','Join exact canonical source fixture','FETCH_HEAD');old.git(env.seed,'push','origin','main');old.git(env.clone,'fetch','origin','main')
 base=old.rev_parse(env.seed,'HEAD');old.git(env.clone,'checkout','--detach',base)
 ws_path='agentos/workstreams/WS-PLAN-TEST.md';ws_raw=old.git(env.seed,'show',base+':'+ws_path).encode()
 def cap(path,raw,commit=base):return {'source':dict(repository=p.REPOSITORY,path=path,commit=commit,content_sha256=sha(raw)),'raw_bytes':raw}
 rid='mmos-project-plan-proposal-'+'8'*40;work='WS:PLAN-TEST';selected=dict(work_ref=work,job_id='JOB-001',attempt_id='ATT-'+'2'*32)
 request=dict(schema=compiler.REQUEST_SCHEMA,request_id=rid,work_ref=work,expected_commit=base,expected_adoption='DEC:PLAN-FIRST',base_source=repo['baseline']['source'],selection=selected,result_digest='3'*64)
 declaration=dict(schema=decoder.CANDIDATE_SCHEMA,work_ref=work,base_source=request['base_source'],base_adoption=request['expected_adoption'],plan=dict(objective='A proposal informed by returned evidence.',waves=[dict(id='W1',title='Compare',status='todo')],next_action='Review; do not auto-adopt.',body='Exact proposed body\n'),rationale='Bounded explicit returned evidence.',evidence=[])
 payload=dict(summary='Human result summary',current_state=json.dumps(declaration),completed_steps=[],next_actions=[])
 result=dict(schema=compiler.RESULT_SCHEMA,selection=selected,stage='plan',result_digest=request['result_digest'],payload=payload,payload_sha256=sha(compiler._canonical(payload)),planning_context_sha256='4'*64,planning_request_sha256='5'*64,planning_input_artifact_sha256='6'*64,principal_scope='7'*64,origin_root='original-root',budget_ref='original-budget',return_ref='original-parent')
 snapshot=dict(schema=compiler.SNAPSHOT_SCHEMA,repository=p.REPOSITORY,commit=base,workstream=cap(ws_path,ws_raw),decisions=[cap('agentos/decisions/DEC-PLAN-FIRST.md',old.git(env.seed,'show',base+':agentos/decisions/DEC-PLAN-FIRST.md').encode())],base=repo['baseline'],proposal_target=dict(path='research/project-plans/PLAN-PLAN-TEST-'+'8'*40+'.md',state='ABSENT'),evidence=[],source_binding={'fixture':'actual code pin'})
 recipe=compiler.compile_proposal_recipe(request,snapshot,result,{'principal_id':'fixture'},owner=owner,declaration_owner=decoder)
 lookup=dict(schema=LOOKUP_SCHEMA,action=ACTION,request_id=rid,work_ref=work);scope='9'*64;stamp='a'*64
 images=[dict(path=e['path'],content_sha256=e['content_sha256'],expected_preimage_sha256=e['expected_sha256']) for e in recipe['edits']]
 metadata=dict(schema=BINDING_SCHEMA,selection=lookup,principal_scope=scope,request_sha256=recipe['request_sha256'],recipe_fingerprint_sha256=recipe['recipe_fingerprint_sha256'],permission_binding_digest=stamp,phase='PUBLICATION',publication_binding=dict(expected_commit=base,postimages=images,branch=None))
 runtime=Runtime.at(env.tmp_path/'actual-source-events');events=SourceOperationEvents(runtime.store)
 events.prepare(lookup,scope,request_sha256=recipe['request_sha256'],recipe_fingerprint_sha256=recipe['recipe_fingerprint_sha256'],
  original_input=REF,permission_binding_digest=stamp,publication_binding=metadata['publication_binding'],guard=lambda:True)
 permit=events.claim_phase(lookup,scope,permission_binding_digest=stamp,
  preview_witness={'original_input':REF,'recipe_fingerprint_sha256':recipe['recipe_fingerprint_sha256']},guard=lambda:True)
 state=SimpleNamespace(publish=True,read=True,data=True,read_stamp='b'*64,data_stamp='c'*64,permit=permit,metadata=metadata)
 pr=old.InertPullRequestOwner(env.origin)
 binding=p.PublisherBinding(worktree=str(env.clone),expected_origin=str(env.origin),default_branch='main',publisher_identity=old.PUBLISHER_IDENTITY)
 publisher=p.FixedProjectGitPublisher(binding,lambda _:pytest.fail('no CREATE'),lambda _:False,lambda _:pytest.fail('no CREATE stamp'),old.qualify_publisher,pr,principal_scope=lambda _:scope,
  authorize_plan_proposal=lambda principal,work:state.publish,plan_proposal_permission_stamp=lambda principal,work:stamp,load_plan_proposal_operation=lambda *a:deepcopy(state.metadata),validate_plan_proposal_claim=lambda principal,selection,claim,metadata:events.validate_permit(claim,lookup,scope,guard=lambda:state.publish),
  canonical_data_macro_root=str(env.clone),canonical_data_code_commit=base,authorize_workspace_read=lambda _:state.read,workspace_read_permission_stamp=lambda _:state.read_stamp,authorize_latest_project_data=lambda _:state.data,latest_project_data_permission_stamp=lambda _:state.data_stamp,canonical_data_events=events)
 def publish():return publisher.publish_plan_proposal(request,recipe,old.AUTHORIZED_PRINCIPAL,claim=state.permit)
 def observe():return publisher.observe_canonical_project_data(old.AUTHORIZED_PRINCIPAL,work_ref=work)
 def land():
  published=publish();assert published['state']=='PROPOSAL_PUBLISHED',published
  old.git(env.seed,'fetch','origin',published['proposal']['head_branch']);old.git(env.seed,'merge','--ff-only','FETCH_HEAD');old.git(env.seed,'push','origin','main')
  observed=publisher.reconcile_plan_proposal(lookup,old.AUTHORIZED_PRINCIPAL)
  assert observed['state']=='SOURCE_PUBLISHED'
  sources=[dict(repository='macro',commit=observed['source']['commit'],**image) for image in observed['source']['postimages']]
  events.retain_observation(lookup,scope,phase='PUBLICATION',sources=sources,proposal=None,guard=lambda:state.publish,
   qualify_observation=lambda value:value['sources']==sources and observed['state']=='SOURCE_PUBLISHED')
  return published
 return SimpleNamespace(**locals())

def test_draft_pr_keeps_configured_reader_then_qualified_default_selection_compares(ready):
 f=ready;old_view=f.observe();before=old_view.read_plan(work_ref=f.work);assert before['continuity']['proposals']['items']==[]
 published=f.publish();assert published['state']=='PROPOSAL_PUBLISHED',published
 assert f.observe().data_commit==f.base and f.observe().read_plan(work_ref=f.work)==before
 assert old.rev_parse(f.env.clone,'HEAD')==f.base
 branch=published['proposal']['head_branch'];old.git(f.env.seed,'fetch','origin',branch);old.git(f.env.seed,'merge','--ff-only','FETCH_HEAD');old.git(f.env.seed,'push','origin','main')
 canonical=old.rev_parse(f.env.seed,'HEAD')
 observed=f.publisher.reconcile_plan_proposal(f.lookup,old.AUTHORIZED_PRINCIPAL);assert observed['state']=='SOURCE_PUBLISHED'
 sources=[dict(repository='macro',commit=observed['source']['commit'],**image) for image in observed['source']['postimages']]
 f.events.retain_observation(f.lookup,f.scope,phase='PUBLICATION',sources=sources,proposal=None,guard=lambda:f.state.publish,
  qualify_observation=lambda value:value['sources']==sources)
 # Canonical landing does not mutate the configured revision-bound READ.
 fixed=read_from_macro_owner(macro_root=f.env.clone,expected_macro_sha=f.base,work_ref=f.work,include_continuity=True)
 assert fixed==before and old.rev_parse(f.env.clone,'HEAD')==f.base
 with pytest.raises(CanonicalDataUnavailable):old_view.check()
 view=f.observe();body=view.read_plan(work_ref=f.work);witness=view.witness()
 assert view.data_commit==canonical and view.code_commit==f.base and witness['canonical_data_commit']!=witness['executable_macro_commit']
 assert witness['publication_time'] is None and type(witness['publication_recorded_at_ms']) is int
 assert witness['source_operation']['selection']=={k:f.lookup[k] for k in ('action','request_id','work_ref')}
 assert body['source']['commit']==canonical and body['plan']['objective']==f.repo['ws']['objective']
 assert body['continuity']['adoption']['decision_ref']=='DEC:PLAN-FIRST'
 item=next(i for i in body['continuity']['proposals']['items'] if i['proposal_source']['path']==f.recipe['proposal_path'])
 assert item['state']=='RECORDED_PROPOSAL' and item['comparison']['state']=='AVAILABLE'
 assert item['comparison']['base_text'].encode()==f.repo['baseline_bytes'] and item['candidate_sha256']==f.recipe['candidate_sha256']
 assert f.recipe['proposal_path'] in item['comparison']['candidate_text']
 assert old.rev_parse(f.env.clone,'HEAD')==f.base and f.pr.create_calls==1
@pytest.mark.parametrize('permission',['read','data'])
def test_either_permission_missing_cannot_select_future_data(ready,permission):
 f=ready;f.land();setattr(f.state,permission,False)
 with pytest.raises(CanonicalDataUnavailable):f.observe()
@pytest.mark.parametrize('change',['read_stamp','data_stamp'])
def test_changed_permission_stamp_invalidates_existing_view(ready,change):
 f=ready;view=f.observe();setattr(f.state,change,'f'*64)
 with pytest.raises(CanonicalDataUnavailable):view.check()
@pytest.mark.parametrize('path',['scripts/agentos.py','config/mastermind_programs.yml','agentos/schema/new-schema.yml'])
def test_fixed_executed_reader_closure_change_refuses_without_executing_new_code(ready,path):
 f=ready;target=f.env.seed/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text('raise AssertionError("must never execute")\n');old.git(f.env.seed,'add',path);old.git(f.env.seed,'commit','-m','Unqualified source change');old.git(f.env.seed,'push','origin','main')
 with pytest.raises(CanonicalDataUnavailable):f.observe()
@pytest.mark.parametrize('path',['config/new-config.yml','agentos/schemas/new-schema.yml','unexpected.md'])
def test_unrelated_default_movement_requires_actual_unchanged_selected_data_and_pinned_reader(ready,path,monkeypatch):
 # Accepted4e0 continuity law permits unrelated canonical movement only when
 # the actual selected reader inputs remain equal at C and N. These files
 # are outside the fixed executable closure; they never become CODE.
 f=ready;before=f.observe().read_plan(work_ref=f.work)
 target=f.env.seed/path;target.parent.mkdir(parents=True,exist_ok=True)
 target.write_text('raise AssertionError("must never execute")\n')
 old.git(f.env.seed,'add',path);old.git(f.env.seed,'commit','-m','Unrelated canonical movement');old.git(f.env.seed,'push','origin','main')
 canonical=old.rev_parse(f.env.seed,'HEAD');calls=[]
 from control_plane import agentos_project_plan
 actual=agentos_project_plan.bounded_subprocess_runner
 def observe(argv,**kw):calls.append(argv);return actual(argv,**kw)
 monkeypatch.setattr(agentos_project_plan,'bounded_subprocess_runner',observe)
 view=f.observe();body=view.read_plan(work_ref=f.work);witness=view.witness()
 assert view.code_commit==f.base and view.data_commit==canonical!=f.base
 assert body['plan']==before['plan']
 # Reader-generated source labels identify N; immutable historical source
 # labels stay exact. Compare every other continuity value and source byte
 # digest, never erase original baseline identity or publication facts.
 def configured_labels(value):
  if type(value) is list:return [configured_labels(item) for item in value]
  if type(value) is dict:
   if set(value)=={'repository','commit','path','content_sha256'} and value['commit']==canonical:
    return {**value,'commit':f.base}
   return {key:configured_labels(item) for key,item in value.items()}
  return value
 assert configured_labels(body['continuity'])==before['continuity']
 assert witness['source_operation'] is None and witness['publication_recorded_at_ms'] is None
 assert witness['data_continuity']['executable_macro_commit']==f.base
 assert witness['data_continuity']['canonical_data_commit']==canonical
 assert body['source']['commit']==canonical and body['source']['content_sha256']==before['source']['content_sha256']
 assert calls and any(f.base+':scripts/agentos.py' in argv for argv in calls)
 for argv in calls:
  assert not any(type(arg) is str and arg.endswith(':'+path) for arg in argv)
  for arg in argv:
   if type(arg) is str and arg.endswith((':scripts/agentos.py',':scripts/agentos_project_plan_contract.py')):assert arg.startswith(f.base+':')

def test_changed_recipe_or_foreign_permit_does_not_publish(ready):
 f=ready;before=old.snapshot(f.env.clone);changed=deepcopy(f.recipe);changed['edits'][0]['content_utf8']+='changed'
 assert f.publisher.publish_plan_proposal(f.request,changed,old.AUTHORIZED_PRINCIPAL,claim=f.state.permit)['state']=='CONFLICT'
 assert f.publisher.publish_plan_proposal(f.request,f.recipe,old.AUTHORIZED_PRINCIPAL,claim=object())['state']=='NOT_DISPATCHED'
 assert old.snapshot(f.env.clone)==before and f.pr.create_calls==0

def test_issued_basis_qualifies_full_dec_set_and_uses_actual_snapshot(ready):
 from control_plane.project_plan_canonical_basis import capture_current_plan_basis,PlanBasisUnavailable
 f=ready;view=f.observe();basis=capture_current_plan_basis(view,work_ref=f.work);material=basis.material()
 assert material['base_adoption']=='DEC:PLAN-FIRST' and material['base_source']==f.repo['baseline']['source']
 assert material['source']['commit']==f.base and material['executable_macro_commit']==f.base
 snapshot=basis.proposal_snapshot(request_id=f.request['request_id'])
 assert snapshot['workstream']['source']['commit']==f.base and len(snapshot['decisions'])==1
 assert snapshot['base']==f.repo['baseline'] and snapshot['proposal_target']==f.snapshot['proposal_target']
 material['base_adoption']=None;assert basis.material()['base_adoption']=='DEC:PLAN-FIRST'
 with pytest.raises(PlanBasisUnavailable):basis.qualify_creation_source({'repository':'macro','commit':f.base,'path':f.ws_path,'content_sha256':sha(f.ws_raw),'request_sha256':'f'*64})
 f.state.data=False
 with pytest.raises(PlanBasisUnavailable):basis.check()

def test_reader_never_loads_helper_from_observed_data_commit(ready,monkeypatch):
 f=ready;f.land();calls=[]
 from control_plane import agentos_project_plan
 original=agentos_project_plan.bounded_subprocess_runner
 def observe(argv,**kw):calls.append(argv);return original(argv,**kw)
 monkeypatch.setattr(agentos_project_plan,'bounded_subprocess_runner',observe)
 view=f.observe();view.read_plan(work_ref=f.work)
 for argv in calls:
  for arg in argv:
   if type(arg) is str and arg.endswith((':scripts/agentos.py',':scripts/agentos_project_plan_contract.py')):
    assert arg.startswith(f.base+':')
 assert any(f.base+':scripts/agentos.py' in argv for argv in calls)

def test_literal_data_view_and_unissued_basis_never_substitute_for_owner(ready):
 from control_plane.project_canonical_data import CanonicalProjectDataView
 from control_plane.project_plan_canonical_basis import capture_current_plan_basis,PlanBasisUnavailable
 f=ready
 with pytest.raises(PlanBasisUnavailable):capture_current_plan_basis({'data_commit':f.base},work_ref=f.work)
 forged=CanonicalProjectDataView(object(),f.publisher._canonical_data,object(),f.base,f.base,f.env.clone,f.env.clone,{})
 with pytest.raises(CanonicalDataUnavailable):forged.check()
