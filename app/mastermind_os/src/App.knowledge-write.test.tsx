// @vitest-environment jsdom
/** One real signed HTTP/CF1/Runtime/temp-Git producer journey. Native auth,
 * Programs orientation, credentials and PR APIs are explicit inert seams;
 * this is source composition evidence, never installed/publication proof. */
import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {IDBFactory} from 'fake-indexeddb';
import {App} from './App';
import {bindMissionHost,createNativeClient} from './host';
import {createIndexedDbPendingPointerStore} from './orchestration/indexeddb-pending-pointer-store';
import {controlRoomFixture} from './test-fixtures';
import programs from './fixtures/programs-available-workspace-service.json';
import rawJourney from './fixtures/knowledge-signed-canonical-journey.json';
import firstUseJourney from './fixtures/knowledge-first-use-signed-journey.json';
import {validate_catalogue,validate_memory,validate_source} from './knowledge/library/knowledge-library-contract';

beforeEach(async()=>{
 history.replaceState(null,'','/os/');delete window.MastermindMissionHost;delete (window as any).__TAURI_INTERNALS__;
 const {webcrypto}=await vi.importActual<{webcrypto:Crypto}>('node:crypto');vi.stubGlobal('crypto',webcrypto);
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();delete window.MastermindMissionHost;});
describe.each([{name:'existing signed source publication',data:rawJourney},{name:'first unrelated canonical DATA',data:firstUseJourney}])('$name',({data})=>{
const journey=data as typeof rawJourney & {context?:unknown;second_context?:unknown;second_source?:typeof rawJourney.source};
async function setup(){
 let stage:'before'|'proposal'|'N'|'second-proposal'|'N2'='before';
 const room=controlRoomFixture(),row=structuredClone(room.work[0]);
 row.work_ref=journey.request.work_ref;row.agent_os.workstream=journey.request.work_ref.slice(3);
 row.agent_os.title='Canonical knowledge project';row.executive.jobs=[];row.bindings=[];room.work=[row];room.autonomy.responsibilities=[];
 const collection={...structuredClone(programs),control_room:room};
 let notify!:(event:{payload:unknown})=>void;
 const invoke=vi.fn(async(command:string,args?:any)=>{
  if(command==='auth_status')return {status:'signed_in',reason:null,acquisition:true,content:false};
  if(command==='executive_auth_status')return {generation:0,available:false};
  if(command==='read_programs')return structuredClone(collection);
  if(command==='read_project_knowledge_catalogue')return structuredClone(stage==='before'?journey.before:stage==='proposal'?journey.pr_only_catalogue:stage==='N2'?journey.reopened:journey.after);
  if(command==='read_source_operation_context'){
   if(!journey.context)throw Error('Actual signed context fixture not yet supplied');
   const context=(stage==='N'||stage==='second-proposal'||stage==='N2'?journey.second_context??journey.context:journey.context) as {selection?:{action?:unknown;work_ref?:unknown}};
   if(context.selection?.action!==args.selection.action||context.selection?.work_ref!==args.selection.work_ref)throw Error('This distinct action context is not in the fixture');
   return structuredClone(context);
  }
  if(command==='source_operation_prepare'){
   const second=args.request.request.request_id===journey.second_request.request_id;
   expect(args.request).toEqual({action:'add_project_file',request:second?journey.second_request:journey.request});
   return structuredClone(second?journey.second_preview:journey.preview);
  }
  if(command==='source_operation_submit'){
   const second=args.request.request_id===journey.second_request.request_id;stage=second?'second-proposal':'proposal';
   expect(args.request.preview_witness).toEqual((second?journey.second_preview:journey.preview).preview_witness);
   return structuredClone(second?journey.second_proposal_status:journey.proposal_status);
  }
  if(command==='source_operation_read'||command==='source_operation_reconcile'){
   const second=args.request.request_id===journey.second_request.request_id;
   return structuredClone(second?(stage==='N2'?journey.second_accepted_status:journey.second_proposal_status):(stage==='N'||stage==='N2'?journey.accepted_status:journey.proposal_status));
  }
  if(command==='read_project_knowledge_source'){
   const body=stage==='N2'?journey.second_source:journey.source;
   if(!body||body.selection.source_ref!==args.selection.source_ref||body.source!.revision!==args.selection.expected_revision)throw Error('This source response is not in the coherent fixture');
   return structuredClone(body);
  }
  throw Error('Unexpected fixed fixture command');
 });
 const raw=await createNativeClient(invoke as never,async(_name,listener)=>{notify=listener;return()=>{};});
 const host=bindMissionHost(raw),store=createIndexedDbPendingPointerStore(new IDBFactory());
 delete host.readProjectArchive;delete host.readProjectArchivePage;
 const forbidden=vi.fn(()=>{throw Error('No Executive fixture authority');});
 host.commandBinding={store,port:{context:()=>null,prepare:forbidden,submit:forbidden,readOperation:forbidden},
  getView:()=>({projects:[],profiles:[],session:null}),subscribe:()=>()=>{},makeLaunchIntent:forbidden,makeMessageIntent:forbidden,makeStopIntent:forbidden};
 window.MastermindMissionHost=host;const mounted=render(<App/>);
 async function openLibrary(){fireEvent.click(screen.getByRole('button',{name:'Projects'}));
  fireEvent.click(await screen.findByRole('button',{name:'Open project Canonical knowledge project'}));fireEvent.click(screen.getByRole('button',{name:'Knowledge'}));}
 await openLibrary();
 return {invoke,store,mounted,openLibrary,notify,land:()=>{stage=stage==='second-proposal'?'N2':'N';}};
}
async function prepareFile(second=false){
 const request=second?journey.second_request:journey.request;
 vi.spyOn(globalThis.crypto,'getRandomValues').mockImplementation(array=>{(array as Uint8Array).fill(second?0xbb:0xaa);return array;});
 const add=await screen.findByRole('button',{name:'Add files'});await waitFor(()=>expect((add as HTMLButtonElement).disabled).toBe(false));fireEvent.click(add);
 const bytes=new TextEncoder().encode(request.file.content_utf8),file=new File([bytes],request.file.display_name,{type:request.file.media_type});
 Object.defineProperty(file,'arrayBuffer',{value:async()=>bytes.buffer});
 fireEvent.change(screen.getByLabelText('Choose a file'),{target:{files:[file]}});fireEvent.click(screen.getByRole('button',{name:'Add file'}));
 return screen.findByRole('button',{name:'Publish changes'});
}
it('joins the actual original C→N publication to Library, Search, Back and App reopen without a Runtime root',async()=>{
 const e=await setup(),publish=await prepareFile();
 const scope=journey.preview.owner_context.principal_scope;
 expect(await e.store.read(scope)).toBeNull();expect(e.invoke.mock.calls.filter(([name])=>name==='source_operation_submit')).toHaveLength(0);
 fireEvent.click(publish);await screen.findByText('The project source has not confirmed this save. Check the original publication; do not submit it again.');
 expect(screen.queryByRole('heading',{level:3,name:journey.request.file.display_name})).toBeNull();
 e.land();fireEvent.click(screen.getByRole('button',{name:'Check publication status'}));await screen.findByText('Saved to the project source.');
 await waitFor(async()=>expect(await e.store.read(scope)).toBeNull());
 const row=(await screen.findByRole('heading',{level:3,name:journey.request.file.display_name})).closest('.knowledge-library-row')!;
 fireEvent.click(within(row as HTMLElement).getByRole('button',{name:'Open'}));
 await waitFor(()=>expect(screen.getByRole('article').textContent).toContain(journey.request.file.content_utf8.trim()));
 fireEvent.click(screen.getByRole('button',{name:'Back'}));fireEvent.click(screen.getByRole('button',{name:'Close editor'}));
 fireEvent.click(screen.getByRole('button',{name:'Search'}));const query=await screen.findByLabelText('Search this project');
 fireEvent.change(query,{target:{value:'literal'}});fireEvent.submit(query.closest('form')!);
 fireEvent.click(await screen.findByRole('button',{name:'Open'}));await screen.findByRole('button',{name:'Back'});
 await waitFor(()=>expect(screen.getByRole('article').textContent).toContain(journey.request.file.content_utf8.trim()));
 fireEvent.click(screen.getByRole('button',{name:'Back'}));expect((screen.getByLabelText('Search this project') as HTMLInputElement).value).toBe('literal');
 fireEvent.click(await screen.findByRole('button',{name:'Open'}));await screen.findByRole('article');
 e.mounted.unmount();render(<App/>);await e.openLibrary();await screen.findByRole('heading',{level:3,name:journey.request.file.display_name});
 expect(e.invoke.mock.calls.filter(([name])=>name==='source_operation_prepare')).toHaveLength(1);
 expect(e.invoke.mock.calls.filter(([name])=>name==='source_operation_submit')).toHaveLength(1);
 expect(e.invoke.mock.calls.filter(([name])=>name==='source_operation_reconcile')).toHaveLength(1);
 expect(e.invoke.mock.calls.filter(([name])=>/read_mission|launch|session_message/.test(name))).toHaveLength(0);
});
it('withdraws an actual prepared original on auth change and rejects its detached Publish button',async()=>{
 const e=await setup(),stale=await prepareFile();
 await act(async()=>e.notify({payload:{status:'signed_out',reason:null,acquisition:false,content:false}}));
 expect(screen.queryByRole('button',{name:'Publish changes'})).toBeNull();fireEvent.click(stale);
 expect(e.invoke.mock.calls.filter(([name])=>name==='source_operation_submit')).toHaveLength(0);
 expect(await e.store.read(journey.preview.owner_context.principal_scope)).toBeNull();
});

it('prepares the next genuine edit from N, then searches and opens its actual N2 source',async()=>{
 const e=await setup();fireEvent.click(await prepareFile());
 await screen.findByText('The project source has not confirmed this save. Check the original publication; do not submit it again.');
 e.land();fireEvent.click(screen.getByRole('button',{name:'Check publication status'}));await screen.findByText('Saved to the project source.');
 await screen.findByRole('heading',{level:3,name:journey.request.file.display_name});fireEvent.click(screen.getByRole('button',{name:'Close editor'}));
 fireEvent.click(await prepareFile(true));
 await screen.findByText('The project source has not confirmed this save. Check the original publication; do not submit it again.');
 e.land();fireEvent.click(screen.getByRole('button',{name:'Check publication status'}));await screen.findByText('Saved to the project source.');
 await screen.findByRole('heading',{level:3,name:journey.second_request.file.display_name});fireEvent.click(screen.getByRole('button',{name:'Close editor'}));
 fireEvent.click(screen.getByRole('button',{name:'Search'}));const input=await screen.findByLabelText('Search this project');
 fireEvent.change(input,{target:{value:'Second'}});fireEvent.submit(input.closest('form')!);
 fireEvent.click(await screen.findByRole('button',{name:'Open'}));await screen.findByRole('button',{name:'Back'});
 await waitFor(()=>expect(screen.getByRole('article').textContent).toContain(journey.second_request.file.content_utf8));
 fireEvent.click(screen.getByRole('button',{name:'Back'}));expect((screen.getByLabelText('Search this project') as HTMLInputElement).value).toBe('Second');
 expect(e.invoke.mock.calls.filter(([name])=>name==='source_operation_prepare')).toHaveLength(2);
 expect(e.invoke.mock.calls.filter(([name])=>name==='source_operation_submit')).toHaveLength(2);
 expect(e.invoke.mock.calls.filter(([name])=>name==='source_operation_reconcile')).toHaveLength(2);
 expect(journey.before.code_context.executable_macro_commit).toBe(journey.reopened.code_context.executable_macro_commit);
 expect(journey.second_request.source_commit).toBe(journey.after.source!.commit);
});

});

it('qualifies the actual first-N read frames without inventing an operation or publication clock',()=>{
 const f=firstUseJourney,work=f.request.work_ref;
 const catalogue=validate_catalogue(f.before,work),memory=validate_memory(f.before_memory,work);
 const source=validate_source(f.before_source,work,f.before_source.selection.source_ref);
 expect(f.initial.source.commit).not.toBe(f.unrelated_commit);
 expect(f.before.source.commit).toBe(f.unrelated_commit);
 expect(f.request.source_commit).toBe(f.unrelated_commit);
 expect(f.preview.preview.source_commit).toBe(f.unrelated_commit);
 for(const body of [catalogue,memory,source]){
  const observation=body.dataObservation!;
  expect(observation.executable_macro_commit).toBe(f.initial.source.commit);
  expect(observation.canonical_data_commit).toBe(f.unrelated_commit);
  expect(observation.source_operation).toBeNull();
  expect(observation.publication_recorded_at_ms).toBeNull();
  expect(observation.publication_time).toBeNull();
  expect(observation.data_continuity!.work_ref).toBe(work);
  expect(observation.data_continuity!.principal_scope).toBe(f.context.owner_context.principal_scope);
  expect(Object.isFrozen(observation.data_continuity)).toBe(true);
 }
 expect(memory.availability).toBe('EMPTY');
 expect(f.after.data_observation.source_operation.event_id).toBe(f.accepted_status.receipt.event_id);
 expect(f.reopened.data_observation.source_operation.event_id).toBe(f.second_accepted_status.receipt.event_id);
 expect(f.accepted_status.receipt.event_id).not.toBe(f.second_accepted_status.receipt.event_id);
 expect(f.second_request.source_commit).toBe(f.after.source.commit);
 expect(f.reopened.code_context).toEqual(f.before.code_context);
 expect(f.second_source.source.commit).toBe(f.reopened.source.commit);
});
