/** Actual canonical/private/Event/temp-Git owner DTOs through fixed native
 * client/host and real controller/IndexedDB. Auth transport remains synthetic;
 * tests never grant, publish, create Jobs or invoke installed runtime effects. */
import {expect,it,vi} from 'vitest';
import {IDBFactory} from 'fake-indexeddb';
import {bindMissionHost,createNativeClient} from '../../host';
import {OperationController,type CommandIntent} from '../../orchestration/operation-controller';
import {createIndexedDbPendingPointerStore} from '../../orchestration/indexeddb-pending-pointer-store';
import {decodeProjectKnowledgePreview} from './project-knowledge-preview';
import {canonicalPublicRequest,publicRequestSha256,type ProjectFileAddRequest,type ProjectPreferenceSetRequest} from './project-knowledge-requests';
import {bindProjectKnowledgeCommandOwner,prepareProjectKnowledgeWrite,createProjectKnowledgeCommandPort,type PreparedProjectKnowledgeWrite} from './project-knowledge-port';
import fixture from '../../fixtures/knowledge-write-owner.json';
const signal=()=>new AbortController().signal;
type Request=ProjectFileAddRequest|ProjectPreferenceSetRequest;
async function setup(index=0){
 const journey=fixture.journeys[index]!,request=JSON.parse(canonicalPublicRequest(journey.request as Request)) as Request;
 let current=true,sourceCurrent=true,published=false;
 const invoke=vi.fn(async(command:string,_args?:Record<string,unknown>)=>{
  if(command==='auth_status')return {status:'signed_in',reason:null,acquisition:true,content:false};
  if(command==='executive_auth_status')return {generation:0,available:false};
  if(command==='source_operation_prepare')return journey.preview;
  if(command==='source_operation_submit')return journey.proposal_status;
  if(command==='source_operation_read'||command==='source_operation_reconcile')return published?journey.source_status:journey.proposal_status;
  throw Error('Unexpected native call');
 });
 const raw=await createNativeClient(invoke as never,async()=>()=>{}),host=bindMissionHost(raw),transport=host.sourceOperations!;
 const action=journey.preview.selection.action as 'add_project_file'|'set_project_communication_preference';
 const owner=bindProjectKnowledgeCommandOwner({workRef:request.work_ref,generation:'actual-host-epoch:0',contexts:{[action]:journey.context},
  isCurrent:()=>current,sourceIsCurrent:()=>sourceCurrent});
 let prepared:PreparedProjectKnowledgeWrite|null=null;
 const port=()=>createProjectKnowledgeCommandPort({workRef:request.work_ref,transport,owner,prepared:()=>prepared,
  isPreparedCurrent:anchor=>prepared===anchor&&current&&sourceCurrent});
 return {journey,request,owner,transport,invoke,port,prepare:async()=>prepared=await prepareProjectKnowledgeWrite({request,owner,transport,isCurrent:()=>current},signal()),
  losePrepared:()=>{prepared=null;sourceCurrent=false;},revoke:()=>{current=false;},publish:()=>{published=true;},prepared:()=>prepared};
}
it.each([0,1])('decodes exact real owner preview and canonical public SHA without action/schema invention %s',async index=>{
 const f=await setup(index),sha=await publicRequestSha256(f.request);
 expect(sha).toBe(f.journey.preview.request_sha256);
 expect(decodeProjectKnowledgePreview(f.journey.preview,f.request,sha)).toEqual(f.journey.preview);
 expect(decodeProjectKnowledgePreview({...f.journey.preview,selection:{...f.journey.preview.selection,action:'FILE_ADD'}},f.request,sha)).toBeNull();
});
it.each([0,1])('prepares before any durable pointer and submits only exact original witness once %s',async index=>{
 const f=await setup(index),factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory);
 const scope=f.journey.preview.owner_context.principal_scope;
 expect(await store.read(scope)).toBeNull();
 const prepared=await f.prepare();expect(await store.read(scope)).toBeNull();
 const port=f.port(),controller=new OperationController(port,store);
 const intent:CommandIntent={kind:'project_source_write',targetKey:prepared.targetKey,payload:{action:prepared.target.action,request:prepared.request}};
 const state=await controller.begin(intent);expect(state.status).toBe('unknown');
 expect(await store.read(scope)).toEqual({operationKey:f.request.request_id,kind:'project_source_write',targetKey:prepared.targetKey});
 const submitted=f.invoke.mock.calls.filter(([name])=>name==='source_operation_submit');expect(submitted).toHaveLength(1);
 expect(submitted[0]![1]).toEqual({request:{action:prepared.target.action,request_id:prepared.request.request_id,work_ref:prepared.request.work_ref,preview_witness:prepared.response.preview_witness}});
 expect(f.invoke.mock.calls.filter(([name])=>name==='source_operation_prepare')).toHaveLength(1);
 await controller.begin(intent);expect(f.invoke.mock.calls.filter(([name])=>name==='source_operation_submit')).toHaveLength(1);
 const saved=await store.read(scope);expect(JSON.stringify(saved)).not.toContain('content_utf8');expect(JSON.stringify(saved)).not.toContain('preview_witness');
});
it('reopens the same actual IndexedDB pointer after compiler/source context is unavailable and reconciles without preparing or resubmitting',async()=>{
 const f=await setup(),factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory),prepared=await f.prepare();
 const first=new OperationController(f.port(),store);
 await first.begin({kind:'project_source_write',targetKey:prepared.targetKey,payload:{action:prepared.target.action,request:prepared.request}});
 first.invalidate();f.losePrepared();
 const reopened=new OperationController(f.port(),createIndexedDbPendingPointerStore(factory));
 expect((await reopened.recover()).status).toBe('unknown');
 f.publish();expect((await reopened.recover({reconcileSource:true})).status).toBe('accepted');
 expect(await store.read(f.journey.preview.owner_context.principal_scope)).toBeNull();
 expect(f.invoke.mock.calls.filter(([name])=>name==='source_operation_prepare')).toHaveLength(1);
 expect(f.invoke.mock.calls.filter(([name])=>name==='source_operation_submit')).toHaveLength(1);
 expect(f.invoke.mock.calls.filter(([name])=>name==='source_operation_read')).toHaveLength(1);
 expect(f.invoke.mock.calls.filter(([name])=>name==='source_operation_reconcile')).toHaveLength(1);
});
it('refuses a changed same-original public payload before controller reservation',async()=>{
 const f=await setup(),prepared=await f.prepare(),port=f.port();
 const changed={...prepared.request,file:{...(prepared.request as ProjectFileAddRequest).file,content_utf8:'Changed'}};
 expect(()=>port.prepare({kind:'project_source_write',targetKey:prepared.targetKey,payload:{action:prepared.target.action,request:changed}})).toThrow();
 expect(f.invoke.mock.calls.filter(([name])=>name==='source_operation_submit')).toHaveLength(0);
});
it('refuses changed source expectations or wrong key prefixes on body-free recovery before I/O',async()=>{
 const f=await setup(),prepared=await f.prepare(),port=f.port();f.invoke.mockClear();
 await expect(port.readOperation({operationKey:'mmos-project-preference-set-'+'a'.repeat(40),kind:'project_source_write',targetKey:prepared.targetKey},signal())).rejects.toThrow();
 expect(f.invoke).not.toHaveBeenCalled();
});
it('drops a late prepare after source/auth owner revocation without creating a prepared original',async()=>{
 const f=await setup();let release!:(value:unknown)=>void;
 const transport={...f.transport,prepareSourceOperation:vi.fn(()=>new Promise(resolve=>{release=resolve;}))};
 const pending=prepareProjectKnowledgeWrite({request:f.request,owner:f.owner,transport,isCurrent:()=>true},signal());
 for(let turn=0;turn<20&&!release;turn++)await new Promise(resolve=>setTimeout(resolve,1));
 expect(release).toBeTypeOf('function');f.revoke();release(f.journey.preview);
 await expect(pending).rejects.toThrow('PROJECT_KNOWLEDGE_OPERATION_UNAVAILABLE');
 expect(f.prepared()).toBeNull();
});

it('a crash after server preparation but before publication reservation has no durable command to replay',async()=>{
 const f=await setup(),factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory);
 const prepared=await f.prepare();
 // Actual server fixture has retained private input/INTENT. The prepared
 // response and editor draft are local unsaved material, not a saved command.
 expect(prepared.response.preview_witness.original_input.input_ref).toMatch(/^terminal-input:/);
 expect(await store.read(f.journey.preview.owner_context.principal_scope)).toBeNull();
 f.losePrepared();
 const reopened=new OperationController(f.port(),createIndexedDbPendingPointerStore(factory));
 expect((await reopened.recover()).status).toBe('idle');
 expect(f.invoke.mock.calls.filter(([name])=>name==='source_operation_prepare')).toHaveLength(1);
 expect(f.invoke.mock.calls.filter(([name])=>name==='source_operation_submit'||name==='source_operation_read'||name==='source_operation_reconcile')).toHaveLength(0);
});
