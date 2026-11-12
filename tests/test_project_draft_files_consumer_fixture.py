"""Opt-in whole same-run consumer operand; never live auth/provider evidence.

Workspace wire/principal, Root/PR and physical collection premises are inherited
from the complete File supplier. S19 uses actual signed HTTP/AF_UNIX admission.
No old no-file recording is imported or response rewritten.
"""
import asyncio,copy,hashlib,json,os,time
from pathlib import Path
import pytest
from tests.test_project_planning_files_join import file_joined,publish_file,owner,env,isolated_git_env,identity
from tests.test_mastermind_executive_app_asgi import rsa_key
from tests.test_workspace_project_git_publisher import rev_parse
from integrations.mastermind_workspace_app.contract import principal_frame


@pytest.mark.skipif(not os.environ.get('MM_PROJECT_FILE_CONSUMER_OUTPUT'),reason='opt-in whole source-issued File consumer recording')
def test_same_run_file_consumer_fixture(file_joined,monkeypatch,rsa_key):
 output=os.environ.get('MM_PROJECT_FILE_CONSUMER_OUTPUT')
 if not output:pytest.skip('opt-in whole source-issued File consumer recording')
 j=file_joined;factory=j['factory'];runtime=j['runtime'];args=j['args'];workspace=j['workspace']
 path=Path(output);samples=[]
 packet=dict(scope='DISPOSABLE_FILE_SOURCE_ISSUED_CONSUMER_FIXTURE',capture_state='PARTIAL_UNQUALIFIED',recorded_at_ms=int(time.time()*1000),samples=samples,
  limitations=['Synthetic enrollment/JWKS, Root seal, physical READ isolation and PR/default actor fixtures; no actual provider.',
  'Workspace raw owner/wire and context output uses verified in-process principal/peer premise, not signed Workspace HTTP.',
  'S19 admission/status/result use genuine signed HTTP/AF_UNIX over actual existing source owner/Runtime.',
  'Recorded expiry/clock, W/E scopes and raw responses remain unchanged. No old32e76 splice.'])
 def save():
  raw=json.dumps(packet,ensure_ascii=False,sort_keys=True,indent=2)+'\n';temp=path.with_suffix('.tmp');temp.write_text(raw);os.replace(temp,path)
 def record(edge,operation,request,response,**metadata):
  samples.append(dict(sequence=len(samples)+1,edge=edge,operation=operation,request=copy.deepcopy(request),response=copy.deepcopy(response),**metadata));save()
 contexts=j['installed']._permissions
 for action,work in [('publish_project_proposal',None),('add_project_file',args['work_ref'])]:
  value=contexts.bind(workspace,action=action,work_ref=work).public_context();record('ACTUAL_WORKSPACE_CONTEXT','context',value['selection'],value)
 record('ACTUAL_INSTALLED_WORKSPACE_OWNER','options',{'action':'publish_project_proposal'},j['options'])
 record('ACTUAL_INSTALLED_WORKSPACE_OWNER','prepare',dict(action='publish_project_proposal',request=j['request']),j['preview'])
 record('ACTUAL_INSTALLED_WORKSPACE_OWNER','submit',dict(j['preview']['selection'],preview_witness=j['preview']['preview_witness']),j['pending'])
 record('ACTUAL_DEFAULT_EVENT','reconcile',j['lookup'],j['status'])
 record('ACTUAL_INSTALLED_WORKSPACE_OWNER','read',j['lookup'],j['source_call']('read',j['lookup']))
 def catalogue():
  body,view,generation=j['data'].read_knowledge(principal_frame(workspace),operation='project_knowledge_catalogue',selection={'work_ref':args['work_ref']})
  record('ACTUAL_INSTALLED_CANONICAL_DATA','catalogue',{'work_ref':args['work_ref']},body,generation=generation)
  return body
 catalogue()
 actual=j['source_call'];prepared_files={}
 def source_call(operation,value):
  result=actual(operation,value);record('ACTUAL_INSTALLED_WORKSPACE_OWNER',operation,value,result)
  if operation=='prepare':
   body=value['request'];prepared_files[body['request_id']]=dict(action=value['action'],request_id=body['request_id'],work_ref=body['work_ref'],source_commit=body['source_commit'],base_revision=body['base_revision'],request_sha256=result['request_sha256'],expected_preference_revision=None)
  if operation=='submit':
   lookup=prepared_files[value['request_id']]
   record('ACTUAL_INSTALLED_WORKSPACE_OWNER','read',lookup,actual('read',lookup))
  return result
 j['source_call']=source_call
 file_request,file_status=publish_file(j)
 file_lookup=dict(action='add_project_file',request_id=file_request['request_id'],work_ref=file_request['work_ref'],source_commit=file_request['source_commit'],base_revision=file_request['base_revision'],request_sha256=file_status['request_sha256'],expected_preference_revision=None)
 record('ACTUAL_INSTALLED_WORKSPACE_OWNER','read',file_lookup,actual('read',file_lookup))
 after=catalogue();assert after['data_observation']['source_operation']['selection']['request_id']==file_request['request_id']
 args['grounding']['macro_sha']=rev_parse(j['integrator'],'HEAD');args['stage']='plan';args['private_request']=j['request']['goal'].encode('utf-8')
 from integrations.mastermind_executive_app.principal_namespace import principal_scope_from_identity
 who=args['principal'];scope=principal_scope_from_identity(issuer_digest=who.issuer_digest,subject_digest=who.subject_digest,client_ref=who.client_ref,resource=who.resource)
 material=dict(v=1,principalScope=scope,**{k:args[k] for k in ('work_ref','stage','project_source','publication','grounding')},private_request=args['private_request'].decode())
 args['operation_key']='mmos-project-planning-'+hashlib.sha256(json.dumps(material,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:40]
 from tests import test_project_planning_transport as transport
 monkeypatch.setattr(transport,'fixture',lambda *_:(factory,args,j['armed'],None))
 parts=transport.composition(j['tmp_path'],monkeypatch,rsa_key)
 async def action(client,headers,arguments,*tokens):
  context=await client.post('/os/executive/context',headers=[headers[0]],json={});assert context.status_code==200
  record('SIGNED_EXECUTIVE_HTTP','context',{},context.json(),status_code=context.status_code,route='/os/executive/context')
  packet['identities']=dict(workspace_scope=contexts.bind(workspace,action='add_project_file',work_ref=args['work_ref']).principal_scope,executive_context=context.json(),work_ref=args['work_ref'],creation_request_id=j['request']['request_id'],file_request_id=file_request['request_id'],planning_operation_key=args['operation_key'])
  packet['consumer_inputs']=dict(create_goal=j['request']['goal'],profile_id=j['request']['profile_id'],create_random_byte_hex='bb',file_random_byte_hex='cc',file=file_request['file'],planning_input=material,create_request=j['request'])
  assert scope==context.json()['principal_scope']!=packet['identities']['workspace_scope']
  for operation,value in [('submit',arguments),('status',{k:args[k] for k in ('operation_key','work_ref')})]:
   response=await client.post('/os/executive/project-planning/'+operation,headers=headers,json={'arguments':value})
   record('SIGNED_EXECUTIVE_HTTP',operation,{'arguments':value},response.json(),status_code=response.status_code,route='/os/executive/project-planning/'+operation)
   assert response.status_code==200,response.text
  assert len(runtime.jobs.list_jobs())==1 and runtime.attempts.list_attempts()==[]
  packet['assertions']=dict(jobs=1,attempts=0,planning_dispatched=False,current_file_commit=args['grounding']['macro_sha'],historical_create_commit=args['project_source']['commit'],executable_macro_commit=j['code'])
  assert packet['assertions']['current_file_commit']!=packet['assertions']['historical_create_commit']
  packet['capture_state']='COMPLETE';packet['recorded_at_ms']=int(time.time()*1000)
  raw=json.dumps(packet,ensure_ascii=False);assert all(token not in raw for token in tokens);save()
 asyncio.run(transport.exercise(parts,action))
