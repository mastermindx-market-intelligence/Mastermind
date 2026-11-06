"""Existing Knowledge compiler/publisher -> same configured DATA reader.

Real disposable Git upstream/actual protected Macro parser and recipe bytes.
PR, grant and original-claim callbacks are inert seams; no live publication,
installed selection, worker, provider or credential is exercised.
"""
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from control_plane import workspace_project_git_publisher as p
from control_plane.project_canonical_data import CanonicalDataUnavailable,CanonicalProjectDataView
from control_plane.agentos_project_knowledge import read_project_knowledge_catalogue
from tests.test_workspace_plan_adoption_git_publisher import old,env,isolated_git_env
from tests.knowledge_recipe_test_support import load_recipes,canonical_workstream
from tests.test_project_plan_continuity import owner as actual_owner

@pytest.fixture
def ready(env,tmp_path,request):
 mode=getattr(request,'param','file')
 owner=actual_owner.__wrapped__(tmp_path/'owner');root=Path(owner.__file__).parents[1]
 ws=canonical_workstream().replace('ALPHA','DEMO');paths={'agentos/workstreams/WS-DEMO.md':ws,'scripts/agentos.py':(root/'scripts/agentos.py').read_text()}
 for path,raw in paths.items():
  target=env.seed/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(raw)
 old.git(env.seed,'add','.');old.git(env.seed,'commit','-m','Configured pinned Macro owner and project');old.git(env.seed,'push','origin','main');old.git(env.clone,'fetch','origin','main')
 base=old.rev_parse(env.seed,'HEAD');old.git(env.clone,'checkout','--detach',base)
 if mode=='file':
  request=old.make_file_add_request(base,base_revision=old.sha_hex(ws))
  recipe=load_recipes().build_project_file_add(request,actor_ref='workspace:'+old.scope_of(old.AUTHORIZED_PRINCIPAL),permission_binding_digest=old.knowledge_stamp_for(old.AUTHORIZED_PRINCIPAL,old.KNOWLEDGE_ACTION_FILE_ADD,old.WORK_REF),captured_commit=base,workstream_text=ws)
 else:
  request=old.make_preference_request(base,value='Literal 中文 memory\nsecond line',base_revision=old.sha_hex(ws),expected_preference_revision=None)
  recipe=load_recipes().build_project_preference_set(request,actor_ref='workspace:'+old.scope_of(old.AUTHORIZED_PRINCIPAL),permission_binding_digest=old.knowledge_stamp_for(old.AUTHORIZED_PRINCIPAL,old.KNOWLEDGE_ACTION_PREFERENCE,old.WORK_REF),captured_commit=base,workstream_text=ws,decision_text=None,decision_date='2026-11-04')
 events=old.KnowledgeOperationEvents();pr=old.InertPullRequestOwner(env.origin)
 state=SimpleNamespace(read=True,data=True,write=True,read_stamp='b'*64,data_stamp='c'*64)
 from control_plane.executive_runtime import Runtime
 from control_plane.workspace_source_operations import SourceOperationEvents
 runtime=Runtime.at(tmp_path/'publication-runtime');actual_events=SourceOperationEvents(runtime.store)
 actual_lookup={k:v for k,v in old.knowledge_lookup(request).items() if k in ('schema','action','request_id','work_ref')}
 actual_lookup['schema']='mastermind.workspace_source_operation_lookup.v1'
 actual_scope=old.scope_of(old.AUTHORIZED_PRINCIPAL)
 from control_plane.executive_supervisor import ExecutiveSupervisor
 from control_plane.project_source_original_input import ProjectSourceOriginalInput
 runs=tmp_path/'private-runs';runs.mkdir(mode=0o700)
 supervisor=ExecutiveSupervisor(runtime,object(),runs_root=runs,inspector=object(),process_controller=object())
 private=ProjectSourceOriginalInput(supervisor)
 frozen_payload=dict(schema='mastermind.project_source_original_input.v1',action=actual_lookup['action'],request=request,actor={'principal_id':'fixture'},initial_snapshot={'workstream_text':ws},source_binding={'recipe_source':'actual protected a8 fixture'})
 original_ref=private.prepare(actual_lookup,actual_scope,payload=frozen_payload,trusted_recipe_fingerprint=recipe['request_fingerprint']).to_dict()
 actual_events.prepare(actual_lookup,actual_scope,request_sha256=old.knowledge_lookup(request)['request_sha256'],recipe_fingerprint_sha256=recipe['request_fingerprint'],original_input=original_ref,permission_binding_digest=recipe['permission_binding_digest'],publication_binding=dict(expected_commit=base,branch=None,postimages=[{k:v for k,v in image.items() if k!='content_utf8'} for image in recipe['postimages']]),guard=lambda:True)
 actual_permit=actual_events.claim_phase(actual_lookup,actual_scope,permission_binding_digest=recipe['permission_binding_digest'],preview_witness=dict(original_input=original_ref,recipe_fingerprint_sha256=recipe['request_fingerprint']),guard=lambda:True)
 binding=p.PublisherBinding(worktree=str(env.clone),expected_origin=str(env.origin),default_branch='main',publisher_identity=old.PUBLISHER_IDENTITY)
 def load_original(principal,selected):
  original=actual_events.original(actual_lookup,actual_scope,guard=lambda:True)
  if original is None:return None
  assert private.read(actual_lookup,actual_scope,original_input=original['original_input'],trusted_recipe_fingerprint=original['recipe_fingerprint_sha256'],trusted_request_sha256=original['request_sha256'])==frozen_payload
  status=actual_events.read_status(actual_lookup,actual_scope,guard=lambda:True)
  publication=None
  if status['disposition']=='accepted':
   sources=status['receipt']['sources'];publication=dict(repository=p.REPOSITORY,commit=sources[0]['commit'],postimages=[dict(path=src['path'],content_sha256=src['content_sha256']) for src in sources])
  return dict(schema=p.KNOWLEDGE_OPERATION_SCHEMA,identity={**selected,'principal_scope':actual_scope},recipe_fingerprint_sha256=original['recipe_fingerprint_sha256'],permission_binding_digest=original['permission_binding_digest'],phase='SOURCE_PUBLISHED' if publication else 'CLAIMED',expected_commit=base,postimages=original['publication_binding']['postimages'],branch=None,publication=publication,proposal=None)
 publisher=p.FixedProjectGitPublisher(binding,old.AuthoredProposalCompiler(base),old.authorize,old.permission_stamp,old.qualify_publisher,pr,principal_scope=old.scope_of,
  authorize_knowledge=lambda principal,action,work:state.write and events.authorize_knowledge(principal,action,work),knowledge_permission_stamp=events.knowledge_permission_stamp,load_original_operation=load_original,validate_original_claim=lambda principal,selected,permit,metadata:actual_events.validate_permit(permit,actual_lookup,actual_scope,guard=lambda:True),
  canonical_data_macro_root=str(env.clone),canonical_data_code_commit=base,authorize_workspace_read=lambda _:state.read,workspace_read_permission_stamp=lambda _:state.read_stamp,authorize_latest_project_data=lambda _:state.data,latest_project_data_permission_stamp=lambda _:state.data_stamp,canonical_data_events=actual_events)
 def observe():return publisher.observe_canonical_project_data(old.AUTHORIZED_PRINCIPAL,work_ref=old.WORK_REF)
 def publish():return publisher.publish_knowledge(request,recipe,old.AUTHORIZED_PRINCIPAL,claim=actual_permit)
 def settle():
  current=publisher.reconcile_knowledge(old.knowledge_lookup(request),old.AUTHORIZED_PRINCIPAL)
  assert current['state']=='SOURCE_PUBLISHED',current
  sources=[dict(repository='macro',commit=current['source']['commit'],path=image['path'],content_sha256=image['content_sha256']) for image in current['source']['postimages']]
  return actual_events.retain_observation(actual_lookup,actual_scope,phase='PUBLICATION',sources=sources,proposal=None,qualify_observation=lambda payload:payload["sources"]==sources,guard=lambda:True)
 def land():
  result=publish();assert result['state']=='PROPOSAL_PUBLISHED',result
  old.git(env.seed,'fetch','origin',result['proposal']['head_branch']);old.git(env.seed,'merge','--ff-only','FETCH_HEAD');old.git(env.seed,'push','origin','main')
  settle()
  return result
 return SimpleNamespace(**locals())

def test_actual_knowledge_pr_keeps_old_read_then_canonical_landing_selects_body(ready):
 f=ready;before=f.observe().read_knowledge_catalogue(work_ref=old.WORK_REF)
 assert before['availability']=='AVAILABLE',before
 before_refs={row['source_ref'] for row in before['project']['files']}
 published=f.publish();assert published['state']=='PROPOSAL_PUBLISHED',published
 assert f.observe().data_commit==f.base and f.observe().read_knowledge_catalogue(work_ref=old.WORK_REF)==before
 old.git(f.env.seed,'fetch','origin',published['proposal']['head_branch']);old.git(f.env.seed,'merge','--ff-only','FETCH_HEAD');old.git(f.env.seed,'push','origin','main')
 canonical=old.rev_parse(f.env.seed,'HEAD');reconciled=f.publisher.reconcile_knowledge(old.knowledge_lookup(f.request),old.AUTHORIZED_PRINCIPAL)
 assert reconciled['state']=='SOURCE_PUBLISHED' and reconciled['source']['commit']==canonical
 event=f.settle()
 assert read_project_knowledge_catalogue(macro_root=f.env.clone,expected_macro_sha=f.base,work_ref=old.WORK_REF)==before
 view=f.observe();catalogue=view.read_knowledge_catalogue(work_ref=old.WORK_REF);assert catalogue['availability']=='AVAILABLE',catalogue
 assert catalogue['source']['commit']==canonical and old.rev_parse(f.env.clone,'HEAD')==f.base
 image=next(i for i in f.recipe['postimages'] if i['path']!=old.CANONICAL_PATH)
 row=next(row for row in catalogue['project']['files'] if row['path']==image['path'])
 assert row['revision'] is not None,row
 source=view.read_knowledge_source(work_ref=old.WORK_REF,source_ref=row['source_ref'],expected_revision=row['revision'])
 assert source['availability']=='AVAILABLE',source
 image=next(i for i in f.recipe['postimages'] if i['path']!=old.CANONICAL_PATH)
 assert source['document']['content_utf8']==image['content_utf8'] and source['source']['content_sha256']==image['content_sha256']
 witness=view.witness();assert witness['canonical_data_commit']==canonical and witness['executable_macro_commit']==f.base
 assert witness['publication_time'] is None and witness['publication_recorded_at_ms']==event['recorded_at_ms']
 assert witness['source_operation']['event_id']==event['event_id'] and witness['source_operation']['receipt_sha256']==event['receipt_sha256']
 assert witness['canonical_observed_at_ms']>0 and f.pr.create_calls==1
 # Back/reopen means fresh current catalogue membership and exact blob selector.
 reopened=f.observe().read_knowledge_source(work_ref=old.WORK_REF,source_ref=row['source_ref'],expected_revision=row['revision'])
 assert reopened==source
 foreign=f.observe().read_knowledge_source(work_ref=old.WORK_REF,source_ref='project-file.v1.'+'f'*64,expected_revision=row['revision'])
 assert foreign['availability']=='UNAVAILABLE' and foreign['document'] is None
 output=os.environ.get('MM_CANONICAL_DATA_FIXTURE_OUTPUT')
 if output:
  Path(output).write_text(json.dumps(dict(scope='DISPOSABLE_SOURCE_ONLY_AUTH_PR_PROVIDER_SEAMS_INERT',initial_catalogue=before,prepared_request=f.request,prepared_recipe=f.recipe,proposal_published=published,source_observed_status=f.actual_events.read_status(f.actual_lookup,f.actual_scope,guard=lambda:True),catalogue=catalogue,source=source,memory=f.observe().read_knowledge_memory(work_ref=old.WORK_REF),data_observation=witness),indent=2,ensure_ascii=False)+'\n')
@pytest.mark.parametrize('field',['read','data'])
def test_both_current_grants_required(ready,field):
 f=ready;f.land();setattr(f.state,field,False)
 with pytest.raises(CanonicalDataUnavailable):f.observe()
@pytest.mark.parametrize('field',['read_stamp','data_stamp'])
def test_either_changed_grant_invalidates_captured_view(ready,field):
 f=ready;view=f.observe();setattr(f.state,field,'f'*64)
 with pytest.raises(CanonicalDataUnavailable):view.check()
@pytest.mark.parametrize('path',['scripts/agentos.py','config/mastermind_programs.yml','agentos/schema/workstream.schema.yml','scripts/agentos_project_plan_contract.py'])
def test_non_data_or_code_change_never_becomes_executable(ready,path):
 f=ready;f.land();target=f.env.seed/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text('raise AssertionError("unreviewed")\n');old.git(f.env.seed,'add',path);old.git(f.env.seed,'commit','-m','Unqualified source mutation');old.git(f.env.seed,'push','origin','main')
 with pytest.raises(CanonicalDataUnavailable):f.observe()
def test_changed_default_masks_old_view_and_new_code_is_never_loaded(ready,monkeypatch):
 f=ready;view=f.observe();f.land()
 with pytest.raises(CanonicalDataUnavailable):view.check()
 from control_plane import ceo_boot_packet
 calls=[];original=ceo_boot_packet.bounded_subprocess_runner
 def observe(argv,**kw):calls.append(argv);return original(argv,**kw)
 monkeypatch.setattr(ceo_boot_packet,'bounded_subprocess_runner',observe)
 f.observe().read_knowledge_catalogue(work_ref=old.WORK_REF)
 assert any(f.base+':scripts/agentos.py' in argv for argv in calls)
 assert all(not arg.endswith(':scripts/agentos.py') or arg.startswith(f.base+':') for argv in calls for arg in argv if type(arg) is str)
def test_unissued_literal_or_foreign_revision_cannot_replace_data_owner(ready):
 f=ready;forged=CanonicalProjectDataView(object(),f.publisher._canonical_data,object(),f.base,f.base,f.env.clone,f.env.clone,{})
 with pytest.raises(CanonicalDataUnavailable):forged.check()
 f.land();view=f.observe();row=view.read_knowledge_catalogue(work_ref=old.WORK_REF)['project']['files'][0]
 response=view.read_knowledge_source(work_ref=old.WORK_REF,source_ref=row['source_ref'],expected_revision='f'*40)
 assert response['availability']=='UNAVAILABLE' and response['document'] is None


def test_dirty_configured_code_root_is_not_an_immutable_code_pin(ready):
 f=ready;(f.env.clone/'scripts/agentos.py').write_text('raise AssertionError("dirty source")\n')
 with pytest.raises(CanonicalDataUnavailable):f.observe()


def test_fixed_origin_requalification_refuses_another_repository(ready,tmp_path):
 f=ready;view=f.observe();old.git(f.env.clone,'remote','set-url','origin',str(tmp_path/'foreign.git'))
 with pytest.raises(CanonicalDataUnavailable):view.check()


def test_ambient_git_cannot_hide_dirty_configured_root(ready,tmp_path,monkeypatch):
 f=ready;alternate=tmp_path/'same-commit-clean';old.git(tmp_path,'clone',str(f.env.origin),str(alternate))
 assert old.rev_parse(alternate,'HEAD')==f.base
 (f.env.clone/'scripts/agentos.py').write_text('raise AssertionError("actual dirty configured root")\n')
 monkeypatch.setenv('GIT_DIR',str(alternate/'.git'));monkeypatch.setenv('GIT_WORK_TREE',str(alternate))
 monkeypatch.setenv('GIT_COMMON_DIR',str(alternate/'.git'));monkeypatch.setenv('GIT_CONFIG_COUNT','1')
 monkeypatch.setenv('GIT_CONFIG_KEY_0','core.worktree');monkeypatch.setenv('GIT_CONFIG_VALUE_0',str(alternate))
 with pytest.raises(CanonicalDataUnavailable):f.observe()
@pytest.mark.parametrize('flag',['timed_out','limit_exceeded','invalid_utf8'])
def test_configured_head_requires_all_bounded_read_flags(ready,monkeypatch,flag):
 f=ready
 from control_plane import ceo_boot_packet
 monkeypatch.setattr(ceo_boot_packet,'bounded_subprocess_runner',lambda *a,**kw:dict(code=0,stdout=f.base+'\n',**{flag:True}))
 with pytest.raises(CanonicalDataUnavailable):f.publisher._canonical_data._configured()


@pytest.mark.parametrize('path',['docs/unrelated.md','tests/test_unrelated.py','site/unrelated.html'])
def test_unrelated_canonical_movement_keeps_pinned_reader_and_actual_publication(ready,path):
 f=ready;f.land();target=f.env.seed/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text('Unrelated canonical movement\n');old.git(f.env.seed,'add',path);old.git(f.env.seed,'commit','-m','Unrelated repository update');old.git(f.env.seed,'push','origin','main')
 view=f.observe();assert view.code_commit==f.base and view.data_commit==old.rev_parse(f.env.seed,'HEAD')
 assert view.read_knowledge_catalogue(work_ref=old.WORK_REF)['availability']=='AVAILABLE'
 assert view.witness()['source_operation']['selection']['request_id']==f.request['request_id']

def test_default_landing_without_real_source_observed_event_does_not_enable_data(ready):
 f=ready;published=f.publish();old.git(f.env.seed,'fetch','origin',published['proposal']['head_branch']);old.git(f.env.seed,'merge','--ff-only','FETCH_HEAD');old.git(f.env.seed,'push','origin','main')
 with pytest.raises(CanonicalDataUnavailable):f.observe()
 f.settle();assert f.observe().data_commit!=f.base

def test_ambient_git_redirects_cannot_change_knowledge_or_plan_reader(ready,tmp_path,monkeypatch):
 f=ready;f.land();view=f.observe();catalogue=view.read_knowledge_catalogue(work_ref=old.WORK_REF)
 image=next(i for i in f.recipe['postimages'] if i['path']!=old.CANONICAL_PATH)
 row=next(row for row in catalogue['project']['files'] if row['path']==image['path'])
 alternate=tmp_path/'old-data';old.git(tmp_path,'init',str(alternate));old.git(alternate,'fetch','--depth=1',str(f.env.clone),f.base);old.git(alternate,'checkout','--detach','FETCH_HEAD')
 monkeypatch.setenv('GIT_DIR',str(alternate/'.git'));monkeypatch.setenv('GIT_WORK_TREE',str(alternate))
 monkeypatch.setenv('GIT_COMMON_DIR',str(alternate/'.git'))
 source=view.read_knowledge_source(work_ref=old.WORK_REF,source_ref=row['source_ref'],expected_revision=row['revision'])
 assert source['availability']=='AVAILABLE' and source['document']['content_utf8']==image['content_utf8']
 plan=f.observe().read_plan(work_ref=old.WORK_REF)
 assert plan['availability']=='AVAILABLE' and plan['source']['commit']==view.data_commit

def test_publication_receipt_dict_and_foreign_scope_are_not_read_authority(ready):
 from control_plane.canonical_data_publication import capture_source_publication,CanonicalPublicationUnavailable
 f=ready;f.land()
 status=f.actual_events.read_status(f.actual_lookup,f.actual_scope,guard=lambda:True)
 with pytest.raises(CanonicalPublicationUnavailable):capture_source_publication(status,f.actual_lookup,f.actual_scope,guard=lambda:True)
 proof=capture_source_publication(f.actual_events,f.actual_lookup,f.actual_scope,guard=lambda:True)
 with pytest.raises(CanonicalPublicationUnavailable):proof.check('f'*64)
 with pytest.raises(CanonicalPublicationUnavailable):capture_source_publication(f.actual_events,f.actual_lookup,f.actual_scope,guard=lambda:False)


def test_current_write_grant_is_not_required_to_read_retained_publication(ready):
 f=ready;f.land();f.state.write=False
 assert f.observe().read_knowledge_catalogue(work_ref=old.WORK_REF)['availability']=='AVAILABLE'

@pytest.mark.parametrize('ready',['preference'],indirect=True)
def test_actual_memory_write_retains_event_and_reopens_exact_literal(ready):
 f=ready;old_memory=f.observe().read_knowledge_memory(work_ref=old.WORK_REF)
 f.land();view=f.observe();memory=view.read_knowledge_memory(work_ref=old.WORK_REF)
 assert memory['availability']=='AVAILABLE',memory
 assert memory['memory']['value']=='Literal 中文 memory\nsecond line'
 catalogue=f.observe().read_knowledge_catalogue(work_ref=old.WORK_REF)
 ref=catalogue['project']['memory']['source_ref'];revision=catalogue['project']['memory']['revision']
 opened=f.observe().read_knowledge_source(work_ref=old.WORK_REF,source_ref=ref,expected_revision=revision)
 assert opened['availability']=='AVAILABLE' and 'Literal 中文 memory' in opened['document']['content_utf8']
 output=os.environ.get('MM_CANONICAL_DATA_FIXTURE_OUTPUT')
 if output:
  file=Path(output);sequence=json.loads(file.read_text()) if file.exists() else {}
  sequence['memory_edit']=dict(initial_memory=old_memory,prepared_request=f.request,prepared_recipe=f.recipe,source_observed_status=f.actual_events.read_status(f.actual_lookup,f.actual_scope,guard=lambda:True),catalogue=catalogue,memory=memory,source=opened,data_observation=f.observe().witness())
  file.write_text(json.dumps(sequence,indent=2,ensure_ascii=False)+'\n')

def test_fixed_child_capture_separates_actual_code_root_from_shallow_data_root(ready,tmp_path):
 from control_plane.agentos_project_knowledge import read_project_knowledge_source
 f=ready;f.land();data_root=tmp_path/'data-only'
 old.git(tmp_path,'clone','--depth=1','--no-local',str(f.env.origin),str(data_root))
 data_commit=old.rev_parse(data_root,'HEAD');assert data_commit!=f.base
 # The shallow DATA database cannot provide the old executable commit; a
 # capture silently loading C from DATA therefore cannot pass this join.
 import subprocess
 assert subprocess.run(['git','-C',str(data_root),'cat-file','-e',f.base],capture_output=True).returncode!=0
 catalogue=read_project_knowledge_catalogue(macro_root=data_root,expected_macro_sha=data_commit,work_ref=old.WORK_REF,code_root=f.env.clone,code_commit=f.base)
 assert catalogue['availability']=='AVAILABLE',catalogue
 image=next(i for i in f.recipe['postimages'] if i['path']!=old.CANONICAL_PATH)
 row=next(row for row in catalogue['project']['files'] if row['path']==image['path'])
 source=read_project_knowledge_source(macro_root=data_root,expected_macro_sha=data_commit,work_ref=old.WORK_REF,source_ref=row['source_ref'],expected_revision=row['revision'],code_root=f.env.clone,code_commit=f.base)
 assert source['availability']=='AVAILABLE' and source['document']['content_utf8']==image['content_utf8']
 refused=read_project_knowledge_catalogue(macro_root=data_root,expected_macro_sha=data_commit,work_ref=old.WORK_REF,code_root=f.env.clone,code_commit='f'*40)
 assert refused['availability']=='UNAVAILABLE'


def test_retained_publication_view_is_bound_to_its_selected_work(ready):
 f=ready;f.land();view=f.observe()
 with pytest.raises(CanonicalDataUnavailable):view.read_knowledge_catalogue(work_ref='WS:FOREIGN')
 with pytest.raises(CanonicalDataUnavailable):f.publisher.observe_canonical_project_data(old.AUTHORIZED_PRINCIPAL,work_ref='WS:FOREIGN')
