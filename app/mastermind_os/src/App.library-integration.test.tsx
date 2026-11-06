// @vitest-environment jsdom
import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {App} from './App';
import {bindMissionHost,createNativeClient} from './host';
import type {SavedConversationSearchOwner} from './discovery/saved-conversations';
import {controlRoomFixture} from './test-fixtures';
import programs from './fixtures/programs-available-workspace-service.json';
import library from './fixtures/project-knowledge-owner.json';
import paired from './fixtures/window-mission-association-producer.json';
import publicationOwner from './fixtures/knowledge-write-owner.json';
import {IDBFactory} from 'fake-indexeddb';
import {createIndexedDbPendingPointerStore} from './orchestration/indexeddb-pending-pointer-store';
import {decodeWindow,observedMissionAssociation} from './workspace-contract';
import {decodeMissionv3} from './mission';
const signed={status:'signed_in',reason:null,acquisition:true,content:false};
const uploaded=library.catalogue.project.files.find(row=>row.origin.kind==='PRINCIPAL_UPLOAD')!;
beforeEach(async()=>{history.replaceState(null,'','/os/');delete window.MastermindMissionHost;delete (window as any).__TAURI_INTERNALS__;
 const {webcrypto}=await vi.importActual<{webcrypto:Crypto}>('node:crypto');vi.stubGlobal('crypto',webcrypto);});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();delete window.MastermindMissionHost;});
async function setup(pendingSource=false, historyOwner?:SavedConversationSearchOwner, destination=false, publication=false){
 const room=controlRoomFixture(),row=structuredClone(room.work[0]);row.work_ref=library.work_ref;row.agent_os.workstream=library.work_ref.slice(3);
 row.agent_os.title='Qualified library project';
 const destinationPair=JSON.parse(JSON.stringify(paired).replaceAll(paired.selection.work_ref,library.work_ref)) as typeof paired;
 if(!destination){row.executive.jobs=[];row.bindings=[];room.autonomy.responsibilities=[];}
 else {
   const responsibility=structuredClone(room.autonomy.responsibilities[0]);
   Object.assign(responsibility,{responsibility_ref:library.work_ref,root_job_id:paired.selection.root_job_id,
    root_job_candidates:[paired.selection.root_job_id],root_job_ambiguous:false,runtime_root_state:'RESOLVED'});
   room.autonomy.responsibilities=[responsibility];
   history.replaceState(null,'',`/os/?work_ref=${library.work_ref}&root_job_id=${paired.selection.root_job_id}`);
   // Controlled destination uses the producer's complete tuple, rebound to the
   // actual file source work; real decoders must qualify it before App sees it.
   const selection={workRef:library.work_ref,rootJobId:paired.selection.root_job_id};
   expect(observedMissionAssociation(await decodeWindow(destinationPair.window),decodeMissionv3(destinationPair.mission,selection),selection)).not.toBeNull();
 }
 room.work=[row];
 const collection={...structuredClone(programs),control_room:room};
 const journey=publicationOwner.journeys[0]!;let sourceObserved=false;
 let notify!:(event:{payload:unknown})=>void,finish!:(value:unknown)=>void;
 const held=new Promise(resolve=>{finish=resolve;});
 const invoke=vi.fn(async(command:string,args?:any)=>{
  if(command==='auth_status')return {...signed,content:destination};if(command==='executive_auth_status')return {generation:0,available:false};
  if(command==='read_programs')return structuredClone(collection);
  if(command==='read_mission_v3')return structuredClone(destinationPair.mission);
  if(command==='read_current_window')return structuredClone(destinationPair.window);
  if(command==='read_project_knowledge_catalogue')return structuredClone(publication?(sourceObserved?journey.after_catalogue:journey.before_catalogue):library.catalogue);
  if(command==='read_project_knowledge_memory')return structuredClone(publication?journey.after_memory:library.memory);
  if(command==='read_project_knowledge_source')return pendingSource?held:structuredClone(publication?journey.sources[args.selection.source_ref as keyof typeof journey.sources]:library.sources[args.selection.source_ref as keyof typeof library.sources]);
  if(publication && command==='read_source_operation_context'){if(args.selection.action!==journey.context.selection.action)throw Error('Distinct context unavailable');return structuredClone(journey.context);}
  if(publication && command==='source_operation_prepare'){expect(args.request).toEqual({action:journey.context.selection.action,request:journey.request});return structuredClone(journey.preview);}
  if(publication && command==='source_operation_submit')return structuredClone(journey.proposal_status);
  if(publication && (command==='source_operation_read'||command==='source_operation_reconcile'))return structuredClone(sourceObserved?journey.source_status:journey.proposal_status);
  throw new Error('Unexpected fixed fixture command');
 });
 const raw=await createNativeClient(invoke as never,async(_name,listener)=>{notify=listener;return()=>{};});
 const host=bindMissionHost(raw);delete host.readProjectArchive;delete host.readProjectArchivePage;if(historyOwner){
  // Explicit synthetic Session owner. It is separate from Workspace READ and
  // never advertises a current target or any successful mutation.
  const noEffect=vi.fn(()=>{throw new Error('No fixture command authority');});
  host.sessionCommandBinding={port:{context:historyOwner.context,projectHistory:historyOwner,
    currentTargetRef:()=>null,prepare:noEffect,submit:noEffect,readOperation:noEffect},
    store:{read:()=>null,reserve:noEffect,clearIfEqual:noEffect},getView:()=>null,subscribe:()=>()=>{},
    makeLaunchIntent:noEffect,makeMessageIntent:noEffect,makeStopIntent:noEffect,makeSessionMessageIntent:noEffect} as never;
 }
 window.MastermindMissionHost=host;
 const store=publication?createIndexedDbPendingPointerStore(new IDBFactory()):undefined;
 if(store){
  // Real durable owner slot, with no Executive launch/message authority.
  const forbidden=vi.fn(()=>{throw Error('No Executive fixture command');});
  host.commandBinding={store,port:{context:()=>null,prepare:forbidden,submit:forbidden,readOperation:forbidden},
   getView:()=>({projects:[],profiles:[],session:null}),subscribe:()=>()=>{},
   makeLaunchIntent:forbidden,makeMessageIntent:forbidden,makeStopIntent:forbidden};
 }
 const mounted=render(<App/>);
 if(!destination){fireEvent.click(screen.getByRole('button',{name:'Projects'}));
 fireEvent.click(await screen.findByRole('button',{name:'Open project Qualified library project'}));}
 return {invoke,notify,finish,host,destinationPair,store,mounted,land:()=>{sourceObserved=true;}};
}
it('opens actual rootless project Library source through fixed native reads without creating Mission or draft authority',async()=>{
 const e=await setup();fireEvent.click(screen.getByRole('button',{name:'Knowledge'}));
 await screen.findByRole('heading',{level:1,name:library.catalogue.project.title});
 const card=screen.getByText('Uploaded file').closest('.knowledge-library-row')!;
 fireEvent.click(within(card as HTMLElement).getByRole('button',{name:'Open'}));
 await screen.findByText('中文 body line.');
 expect(screen.getAllByRole('heading',{level:1})).toHaveLength(1);
 expect(e.invoke.mock.calls.filter(([name])=>name==='read_project_knowledge_source')).toEqual([['read_project_knowledge_source',{selection:{work_ref:library.work_ref,source_ref:uploaded.source_ref,expected_revision:uploaded.revision}}]]);
 expect(e.invoke.mock.calls.filter(([name])=>/mission|prepare|submit|launch|create|adopt|pause|resume|append/.test(name))).toHaveLength(0);
 expect(screen.queryByRole('button',{name:/Add to draft|Send|Save file|Edit preference/})).toBeNull();
});
it('joins explicit project file Search Open to exact Library reread and preserves the mounted query on Back',async()=>{
 const e=await setup();fireEvent.click(screen.getByRole('button',{name:'Search'}));
 const input=await screen.findByLabelText('Search this project');fireEvent.change(input,{target:{value:'中文'}});
 fireEvent.submit(input.closest('form')!);
 const open=await screen.findAllByRole('button',{name:'Open'});fireEvent.click(open[0]);
 await screen.findByRole('button',{name:'Back'});
 await waitFor(()=>expect(screen.getAllByRole('heading',{level:1})).toHaveLength(1));
 fireEvent.click(screen.getByRole('button',{name:'Back'}));
 expect((screen.getByLabelText('Search this project') as HTMLInputElement).value).toBe('中文');
 expect(e.invoke.mock.calls.some(([name])=>name==='read_project_knowledge_source')).toBe(true);
 expect(e.invoke.mock.calls.filter(([name])=>/mission|prepare|submit|launch|create|adopt|pause|resume/.test(name))).toHaveLength(0);
});
it('withdraws an actual Library source body on auth change and refuses late completion without a second source read',async()=>{
 const e=await setup(true);fireEvent.click(screen.getByRole('button',{name:'Knowledge'}));
 await screen.findByRole('heading',{level:1,name:library.catalogue.project.title});
 const card=screen.getByText('Uploaded file').closest('.knowledge-library-row')!;fireEvent.click(within(card as HTMLElement).getByRole('button',{name:'Open'}));
 await waitFor(()=>expect(e.invoke.mock.calls.filter(([name])=>name==='read_project_knowledge_source')).toHaveLength(1));
 act(()=>e.notify({payload:{status:'signed_out',reason:'AUTHENTICATION_REQUIRED',acquisition:false,content:false}}));
 await act(async()=>e.finish(structuredClone(library.sources[uploaded.source_ref as keyof typeof library.sources])));
 expect(screen.queryByText('中文 body line.')).toBeNull();
 expect(e.invoke.mock.calls.filter(([name])=>name==='read_project_knowledge_source')).toHaveLength(1);
});

it('opens a saved Search reply only through its independently supplied Session owner and preserves query on Back',async()=>{
 const hex=(c:string)=>c.repeat(64),text='Original saved reply 中文 body';
 const reference={read_ref:'session-reply-'+hex('a'),operation_key:'session-continue-'+hex('b'),request_ref:'original-request',request_event_id:41,request_revision:hex('c'),requested_at:'2026-11-03T10:20:30.000Z',work_ref:library.work_ref,root_job_id:'JOB-123',target_ref:'fabric_attempt:'+hex('d'),reference_only:true};
 const readReferences=vi.fn(async()=>({schema:'mastermind.os.executive.session_result.v1',operation:'references',ok:true,effect:'NONE',operation_key:null,error:null,data:{schema:'mastermind.session_reply_references.v1',status:'COMPLETE',references:[reference],next_cursor:null,high_water:100}}));
 const readAnswer=vi.fn(async()=>({receipt:{operationKey:reference.operation_key,targetKey:reference.target_ref,kind:'message',disposition:'accepted'},answer:{readRef:reference.read_ref,text,nextStep:null,parentConsumed:false}}));
 const owner={context:()=>({principalScope:'explicit-session-fixture',generation:'session-owner-1'}),authGeneration:()=>7,readReferences,readAnswer} as unknown as SavedConversationSearchOwner;
 const e=await setup(false,owner);fireEvent.click(screen.getByRole('button',{name:'Search'}));
 fireEvent.click(screen.getByRole('button',{name:'Saved conversations'}));
 const input=screen.getByLabelText('Search this project');fireEvent.change(input,{target:{value:'中文'}});fireEvent.submit(input.closest('form')!);
 fireEvent.click(await screen.findByRole('button',{name:'Open'}));
 const heading=await screen.findByRole('heading',{level:1,name:'Saved reply'});
 await within(heading.closest('article')!).findByText(text);
 expect(readReferences).toHaveBeenCalledTimes(2);expect(readAnswer).toHaveBeenCalledTimes(2);
 expect(screen.getAllByRole('heading',{level:1})).toHaveLength(1);
 expect(e.invoke.mock.calls.filter(([name])=>name==='read_project_knowledge_source')).toHaveLength(0);
 fireEvent.click(screen.getByRole('button',{name:'Back to search'}));
 expect((screen.getByLabelText('Search this project') as HTMLInputElement).value).toBe('中文');
});

async function openFileWithGenuineDraft(){
 const e=await setup(false,undefined,true);
 fireEvent.click(screen.getByRole('button',{name:'Conversations'}));
 fireEvent.click(await screen.findByRole('button',{name:/^Open conversation:/}));
 await screen.findByText(e.destinationPair.window.view.items.find(item=>item.text)!.text!);
 fireEvent.click(screen.getByRole('button',{name:'Unsent notes'}));
 fireEvent.change(screen.getByRole('textbox',{name:'Unsent notes'}),{target:{value:'Original current App draft'}});
 fireEvent.click(screen.getByRole('button',{name:'Knowledge'}));
 await screen.findByRole('heading',{level:1,name:library.catalogue.project.title});
 fireEvent.click(within(screen.getByText('Uploaded file').closest('.knowledge-library-row')! as HTMLElement).getByRole('button',{name:'Open'}));
 await screen.findByRole('button',{name:'Add excerpt to draft'});
 return e;
}
it('appends and undoes an actual Library source in the genuine mounted unsent draft without a file root or send',async()=>{
 const e=await openFileWithGenuineDraft();
 fireEvent.click(screen.getByRole('button',{name:'Add excerpt to draft'}));
 expect(await screen.findByText('Excerpt added to the draft. Not sent.')).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'Remove added excerpt'}));
 fireEvent.click(screen.getByRole('button',{name:'Conversations'}));
 fireEvent.click(await screen.findByRole('button',{name:/^Open conversation:/}));
 fireEvent.click(screen.getByRole('button',{name:'Unsent notes'}));
 expect(screen.getByRole('textbox',{name:'Unsent notes'})).toHaveProperty('value','Original current App draft');
 expect(e.invoke.mock.calls.some(([name])=>/submit|prepare|send|create|source_operation/.test(name))).toBe(false);
});
it('returns to original notes only after the explicit guarded source gesture',async()=>{
 const e=await openFileWithGenuineDraft();
 fireEvent.click(screen.getByRole('button',{name:'Add excerpt to draft'}));
 fireEvent.click(within(screen.getByRole('heading',{level:1}).closest('article')!).getByRole('button',{name:'Back'}));
 fireEvent.click(within(screen.getByText('Uploaded file').closest('.knowledge-library-row')! as HTMLElement).getByRole('button',{name:'Open'}));
 fireEvent.click(await screen.findByRole('button',{name:'Open original conversation'}));
 const notes=await screen.findByRole('button',{name:'Unsent notes'});
 expect(document.activeElement).toBe(notes);
 expect(e.invoke.mock.calls.some(([name])=>/submit|prepare|send|create|source_operation/.test(name))).toBe(false);
});
it.each(['content','generation'] as const)('refuses a stale original return after no-render %s loss',async(kind)=>{
 const e=await openFileWithGenuineDraft();
 fireEvent.click(screen.getByRole('button',{name:'Add excerpt to draft'}));
 fireEvent.click(within(screen.getByRole('heading',{level:1}).closest('article')!).getByRole('button',{name:'Back'}));
 fireEvent.click(within(screen.getByText('Uploaded file').closest('.knowledge-library-row')! as HTMLElement).getByRole('button',{name:'Open'}));
 const control=await screen.findByRole('button',{name:'Open original conversation'});
 if(kind==='content')vi.spyOn(e.host.auth!,'getState').mockReturnValue({...signed,content:false} as never);
 else vi.spyOn(e.host,'invalidationGeneration').mockReturnValue(e.host.invalidationGeneration!()+1);
 fireEvent.click(control);
 expect(screen.queryByRole('button',{name:'Unsent notes'})).toBeNull();
 expect(e.invoke.mock.calls.some(([name])=>/submit|prepare|send|create|source_operation/.test(name))).toBe(false);
});
it('refuses a stale Library append when actual Content permission disappears without a React notification',async()=>{
 const e=await openFileWithGenuineDraft(),oldAdd=screen.getByRole('button',{name:'Add excerpt to draft'});
 const currentAuth = vi.spyOn(e.host.auth!,'getState').mockReturnValue({...signed,content:false} as never);
 fireEvent.click(oldAdd);
 expect(screen.queryByText('Excerpt added to the draft. Not sent.')).toBeNull();
 // Reacquire the real read capability before inspecting the retained draft.
 currentAuth.mockRestore();
 fireEvent.click(screen.getByRole('button',{name:'Conversations'}));
 fireEvent.click(await screen.findByRole('button',{name:/^Open conversation:/}));
 fireEvent.click(screen.getByRole('button',{name:'Unsent notes'}));
 expect(screen.getByRole('textbox',{name:'Unsent notes'})).toHaveProperty('value','Original current App draft');
 expect(e.invoke.mock.calls.some(([name])=>/submit|prepare|send|create|source_operation/.test(name))).toBe(false);
});

it('keeps a legacy Library read-only even with fixed command methods and the actual durable store',async()=>{
 const e=await setup(false,undefined,false,true),journey=publicationOwner.journeys[0]!;
 fireEvent.click(screen.getByRole('button',{name:'Knowledge'}));
 await screen.findByRole('heading',{level:1,name:journey.before_catalogue.project.title});
 await act(async()=>{});
 const add=screen.getByRole('button',{name:'Add files'});expect((add as HTMLButtonElement).disabled).toBe(true);fireEvent.click(add);
 expect(screen.queryByLabelText('Choose a file')).toBeNull();
 expect(e.invoke.mock.calls.filter(([name])=>name==='read_source_operation_context')).toHaveLength(0);
 expect(e.invoke.mock.calls.filter(([name])=>name==='source_operation_prepare'||name==='source_operation_submit')).toHaveLength(0);
 expect(await e.store!.read(journey.context.owner_context.principal_scope)).toBeNull();
});
