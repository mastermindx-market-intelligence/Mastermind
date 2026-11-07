import {afterEach,expect,it,vi} from 'vitest';
import {IDBFactory} from 'fake-indexeddb';
import {createNativeClient} from './host';
import {composeMissionHost} from './compose-mission-host';
import history from './fixtures/project-conversation-history-owner.json';
import fixture from './fixtures/project-conversation-catalogue-owner.json';
import fresh from './fixtures/project-fresh-conversation-owner.json';
const executionReference = {
  schema: 'mastermind.project_execution_reference.v1', work_ref: 'WS:PROJECT-ONE',
  root_job_id: 'JOB-123', root_event_id: 42, root_event_sha256: 'a'.repeat(64),
  project_execution_source_sha256: 'b'.repeat(64), principal_scope_sha256: 'c'.repeat(64),
};
const disposed:Array<()=>void>=[];afterEach(()=>disposed.splice(0).forEach(fn=>fn()));
async function setup(){
  const events=new Map<string,(event:{payload:unknown})=>void>();
  const invoke=vi.fn(async(command:string,args?:Record<string,unknown>)=>{
    if(command==='auth_status')return {status:'signed_in',reason:null,acquisition:true,content:false};
    if(command==='executive_auth_status')return {generation:1,available:true};
    if(command==='executive_project_history_context')return structuredClone(history.context);
    if(command==='executive_project_conversations_read'){
      if(args?.operation==='catalogue')return structuredClone(fixture.catalogue);
      if(args?.operation==='read')return structuredClone(fixture.read);
      if(args?.operation==='fresh_references')return structuredClone(fresh.catalogue);
      if(args?.operation==='fresh_read')return structuredClone(fresh.initial_read);
      if(args?.operation==='execution_references'||args?.operation==='execution_read')return {inertTransportResult:true};
    }
    throw Error('unlisted fixture boundary');
  });
  const raw=await createNativeClient(invoke as never,async(name,listener)=>{events.set(name,listener);return()=>{};});
  const composed=composeMissionHost(raw,null,new IDBFactory());disposed.push(composed.dispose);await composed.sessionReady;
  return {raw,host:composed.host,invoke,events};
}
it('joins actual NativeClient/Host/factory to exact catalogue and original window without constructor READ',async()=>{
  const e=await setup(),factory=e.host.session!.createProjectCatalogueReader!;
  const reader=factory({workRef:history.work_ref,currentWorkRef:()=>history.work_ref,selectionGeneration:()=>'one'});
  disposed.push(reader.dispose);
  expect(e.invoke.mock.calls.filter(([name])=>name==='executive_project_history_context')).toHaveLength(0);
  await reader.owner.refresh();const context=reader.owner.context();expect(context).not.toBeNull();
  const page=await reader.owner.catalogue({workRef:history.work_ref,signal:new AbortController().signal});
  expect(page.conversations).toHaveLength(fixture.catalogue.conversations.length);
  await expect(reader.owner.read(fixture.selection,new AbortController().signal)).resolves.toEqual(fixture.read);
  expect(e.invoke.mock.calls.filter(([name])=>name==='executive_project_conversations_read')).toEqual([
    ['executive_project_conversations_read',{operation:'catalogue',arguments:{work_ref:history.work_ref}}],
    ['executive_project_conversations_read',{operation:'read',arguments:fixture.selection}],
  ]);
});
it('forwards fresh reference READ as immutable reference, with no original-key conversion',async()=>{
  const e=await setup(),transport=e.raw.executiveSession!.projectConversations!,signal=new AbortController().signal;
  await transport.request('fresh_references',{work_ref:fresh.catalogue.work_ref},signal);
  await transport.request('fresh_read',fresh.initial_read.reference,signal);
  expect(e.invoke.mock.calls.filter(([name])=>name==='executive_project_conversations_read')).toEqual([
    ['executive_project_conversations_read',{operation:'fresh_references',arguments:{work_ref:fresh.catalogue.work_ref}}],
    ['executive_project_conversations_read',{operation:'fresh_read',arguments:fresh.initial_read.reference}],
  ]);
});
it('refuses accessors/foreign selectors before invocation and retires actual Executive epoch',async()=>{
  const e=await setup(),transport=e.raw.executiveSession!.projectConversations!,getter=vi.fn(()=>history.work_ref);
  for(const args of [{work_ref:history.work_ref,root_job_id:'JOB-1'},{work_ref:history.work_ref+'\n'},
    {work_ref:history.work_ref,cursor:'page\n'},Object.defineProperty({},'work_ref',{get:getter})])
    await expect(transport.request('catalogue',args,new AbortController().signal)).rejects.toThrow();
  expect(getter).not.toHaveBeenCalled();expect(e.invoke.mock.calls.filter(([name])=>name==='executive_project_conversations_read')).toHaveLength(0);
  const reader=e.host.session!.createProjectCatalogueReader!({workRef:history.work_ref,currentWorkRef:()=>history.work_ref,selectionGeneration:()=>'one'});
  disposed.push(reader.dispose);await reader.owner.refresh();expect(reader.owner.context()).not.toBeNull();
  e.events.get('mastermind-executive-auth-state')!({payload:{generation:2,available:false}});
  expect(reader.owner.context()).toBeNull();
  await expect(reader.owner.catalogue({workRef:history.work_ref,signal:new AbortController().signal})).rejects.toThrow();
  expect(e.invoke.mock.calls.filter(([name])=>name==='executive_project_conversations_read')).toHaveLength(0);
});

it('forwards project execution READ through the incumbent NativeClient without a new command or send grant', async()=>{
  const e=await setup(),transport=e.raw.executiveSession!.projectConversations!,signal=new AbortController().signal;
  await transport.request('execution_references',{work_ref:executionReference.work_ref},signal);
  await transport.request('execution_read',executionReference,signal);
  expect(e.invoke.mock.calls.filter(([name])=>name==='executive_project_conversations_read')).toEqual([
    ['executive_project_conversations_read',{operation:'execution_references',arguments:{work_ref:executionReference.work_ref}}],
    ['executive_project_conversations_read',{operation:'execution_read',arguments:executionReference}],
  ]);
  expect(e.invoke.mock.calls.some(([name])=>name==='executive_submit'||name==='executive_session_send')).toBe(false);
});
it('rejects foreign execution references and does not evaluate accessor selectors', async()=>{
  const e=await setup(),transport=e.raw.executiveSession!.projectConversations!,signal=new AbortController().signal;
  const getter=vi.fn(()=>executionReference.work_ref);
  const accessor=Object.defineProperty({...executionReference},'work_ref',{get:getter});
  for(const args of [accessor,{...executionReference,operation_key:'forged'},
    {...executionReference,work_ref:'WS:project.a_1'},{...executionReference,root_event_id:Number.MAX_SAFE_INTEGER+1},
    {...executionReference,project_execution_source_sha256:'short'}]) {
    await expect(transport.request('execution_read',args,signal)).rejects.toThrow('PROJECT_CONVERSATION_SELECTION_INVALID');
  }
  await expect(transport.request('execution_references',{work_ref:executionReference.work_ref,cursor:null},signal)).rejects.toThrow();
  expect(getter).not.toHaveBeenCalled();
  expect(e.invoke.mock.calls.filter(([name])=>name==='executive_project_conversations_read')).toHaveLength(0);
});
it('settles a pending project execution READ on the current auth generation boundary without retry', async()=>{
  const e=await setup(),transport=e.raw.executiveSession!.projectConversations!;
  let release!:(value:unknown)=>void;
  e.invoke.mockReturnValueOnce(new Promise(resolve=>{release=resolve;}) as never);
  const pending=transport.request('execution_read',executionReference,new AbortController().signal);
  const rejected=expect(pending).rejects.toThrow('EXECUTIVE_AUTH_CHANGED');
  e.events.get('mastermind-executive-auth-state')!({payload:{generation:2,available:false}});
  await rejected;release({inertTransportResult:true});await Promise.resolve();
  expect(e.invoke.mock.calls.filter(([name])=>name==='executive_project_conversations_read')).toHaveLength(1);
});
