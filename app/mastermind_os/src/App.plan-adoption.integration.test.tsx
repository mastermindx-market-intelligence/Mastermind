// @vitest-environment jsdom
// Actual immutable 0eb03192 App mount: real NativeClient/Host, current catalogue,
// PlanPanel/inspection, ADOPT port, controller and IndexedDB. Only native invoke
// returns the committed disposable-Git owner's genuine safe fixture responses.
// No fake controller, live account/grant/Git publication or installed claim.
import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {IDBFactory} from 'fake-indexeddb';
import {App} from './App';
import {bindMissionHost,createNativeClient} from './host';
import {createIndexedDbPendingPointerStore} from './orchestration/indexeddb-pending-pointer-store';
import {controlRoomFixture} from './test-fixtures';
import programs from './fixtures/programs-available-workspace-service.json';
import actual from './fixtures/plan-adoption-installed-journey.json';

const scope=actual.context.owner_context.principal_scope;
const lookup={schema:'mastermind.workspace_source_operation_lookup.v1',...actual.preview.selection};
const original={kind:'project_adopt',operationKey:actual.request.request_id,targetKey:actual.request.work_ref};
beforeEach(async()=>{
 history.replaceState(null,'','/os/');delete window.MastermindMissionHost;
 delete (window as unknown as {__TAURI_INTERNALS__?:unknown}).__TAURI_INTERNALS__;
 const {webcrypto}=await vi.importActual<{webcrypto:Crypto}>('node:crypto');
 vi.stubGlobal('crypto',webcrypto);vi.stubGlobal('indexedDB',new IDBFactory());
 vi.spyOn(crypto,'getRandomValues').mockImplementation(value=>{(value as Uint8Array).fill(0x99);return value;});
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();delete window.MastermindMissionHost;});
async function setup({holdSubmit=false}={}){
 const room=controlRoomFixture();room.work=[room.work[0]];
 room.work[0].work_ref=actual.request.work_ref;
 room.work[0].agent_os.title='Adoption test project';room.autonomy.responsibilities=[];
 let notify!:(event:{payload:unknown})=>void;
 let finish!:(value:unknown)=>void;
 const delayed=new Promise(resolve=>{finish=resolve;});
 let phase:'candidate'|'ready'|'adoption'|'accepted'='candidate';
 const invoke=vi.fn(async(name:string,args?:unknown)=>{
  if(name==='auth_status')return {status:'signed_in',reason:null,acquisition:true,content:true};
  if(name==='executive_auth_status')return {generation:0,available:false};
  if(name==='read_programs')return {...structuredClone(programs),control_room:room};
  if(name==='read_project_plan'){
   expect(args).toEqual({selection:{work_ref:actual.request.work_ref}});
   return phase==='accepted'?actual.body:actual.initial_read;
  }
  if(name==='read_source_operation_context'){
   expect(args).toEqual({selection:{action:'ADOPT_PLAN',work_ref:actual.request.work_ref}});
   return actual.context;
  }
  if(name==='source_operation_prepare'){
   expect(args).toEqual({request:{action:'ADOPT_PLAN',request:actual.request}});return actual.preview;
  }
  if(name==='source_operation_submit'){
   expect(args).toEqual({request:{...actual.preview.selection,preview_witness:actual.preview.preview_witness}});
   return holdSubmit?delayed:actual.pending_candidate;
  }
  if(name==='source_operation_read'){
   expect(args).toEqual({request:lookup});
   return phase==='candidate'?actual.pending_candidate:phase==='ready'?actual.ready:phase==='adoption'?actual.pending_adoption:actual.status;
  }
  if(name==='source_operation_reconcile'){
   expect(args).toEqual({request:lookup});
   if(phase==='candidate'){phase='ready';return actual.ready;}
   if(phase==='adoption'){phase='accepted';return actual.status;}
   throw Error('Unexpected extra original reconciliation');
  }
  if(name==='source_operation_advance'){
   expect(args).toEqual({request:{schema:'mastermind.workspace_source_operation_advance.v1',...actual.preview.selection,...actual.ready.advance}});
   phase='adoption';return actual.pending_adoption;
  }
  throw Error('Unexpected fixture native command');
 });
 const raw=await createNativeClient(invoke as never,async(_name,listener)=>{notify=listener;return()=>{};});
 const host=bindMissionHost(raw);window.MastermindMissionHost=host;
 const store=createIndexedDbPendingPointerStore(globalThis.indexedDB);
 function mount(){return render(<App/>);}
 async function open(){
  fireEvent.click(screen.getByRole('button',{name:'Projects'}));
  fireEvent.click(await screen.findByRole('button',{name:'Open project Adoption test project'}));
  fireEvent.click(screen.getByRole('button',{name:'Project details'}));
  fireEvent.click(screen.getByRole("button",{name:"Plan",exact:true}));
  await screen.findByRole('region',{name:'Plan adoption review'});
 }
 const view=mount();await open();
 return {invoke,host,store,notify,finish,view,mount,open};
}
const calls=(e:Awaited<ReturnType<typeof setup>>,name:string)=>e.invoke.mock.calls.filter(([method])=>method===name);
async function prepare(){
 await waitFor(()=>expect((screen.getByRole('button',{name:'Review adoption'}) as HTMLButtonElement).disabled).toBe(false));
 fireEvent.click(screen.getByRole('button',{name:'Review adoption'}));
 await screen.findByRole('button',{name:'Adopt this plan'});
 await waitFor(()=>expect((screen.getByRole('button',{name:'Check original operation'}) as HTMLButtonElement).disabled).toBe(false));
}
async function adopt(){
 await prepare();fireEvent.click(screen.getByRole('button',{name:'Adopt this plan'}));
 await screen.findByText(/original adoption outcome is not known yet/);
}
it('actual App Details uses the same inspection through Review/Adopt/Check/Advance and explicit current Plan Compare',async()=>{
 const consoleErrors=vi.spyOn(console,'error'); // Observe; preserve normal reporting.
 const e=await setup();await prepare();
 const reads=calls(e,'read_project_plan').length;
 expect(reads).toBe(1);
 expect(calls(e,'source_operation_submit')).toHaveLength(0);
 expect(calls(e,'source_operation_reconcile')).toHaveLength(0);
 fireEvent.click(screen.getByRole('button',{name:'Adopt this plan'}));
 await screen.findByText(/original adoption outcome is not known yet/);
 expect(await e.store.read(scope)).toEqual(original);
 fireEvent.click(screen.getByRole('button',{name:'Check original operation'}));
 await screen.findByRole('button',{name:'Continue original adoption'});
 expect(screen.queryByText(/Publication of the original adoption is confirmed/)).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Continue original adoption'}));
 await screen.findByText(/original adoption outcome is not known yet/);
 fireEvent.click(screen.getByRole('button',{name:'Check original operation'}));
 await screen.findByText(/Publication of the original adoption is confirmed/);
 expect(calls(e,'source_operation_prepare')).toHaveLength(1);
 expect(calls(e,'source_operation_submit')).toHaveLength(1);
 expect(calls(e,'source_operation_advance')).toHaveLength(1);
 expect(calls(e,'source_operation_reconcile')).toHaveLength(2);
 expect(calls(e,'read_project_plan')).toHaveLength(reads);
 expect(await e.store.read(scope)).toBeNull();
 const plan=screen.getByRole('region',{name:'Project plan'});
 fireEvent.click(within(plan).getByRole('button',{name:'Refresh'}));
 await screen.findAllByText('DEC:PLAN-ADOPTION-'+'9'.repeat(40));
 expect(screen.getByText('Compared against the recorded predecessor plan.')).toBeTruthy();
 expect(calls(e,'read_project_plan')).toHaveLength(reads+1);
 expect(consoleErrors.mock.calls.filter(args=>args.some(value=>
  typeof value==='string'&&value.includes('same key')))).toHaveLength(0);
});
it('actual App reopen automatically reads only the original pointer and explicit Check reconciles without another submission',async()=>{
 const e=await setup();await adopt();
 expect(await e.store.read(scope)).toEqual(original);
 e.view.unmount();e.mount();await e.open();
 await waitFor(()=>expect(calls(e,'source_operation_read')).toHaveLength(1));
 expect(calls(e,'source_operation_submit')).toHaveLength(1);
 expect(calls(e,'source_operation_prepare')).toHaveLength(1);
 expect(calls(e,'source_operation_reconcile')).toHaveLength(0);
 fireEvent.click(screen.getByRole('button',{name:'Check original operation'}));
 await screen.findByRole('button',{name:'Continue original adoption'});
 expect(calls(e,'source_operation_reconcile')).toHaveLength(1);
 expect(await e.store.read(scope)).toEqual(original);
});
it('actual App caller refuses original recovery after global Host replacement without a render',async()=>{
 const e=await setup();await adopt();
 const before=calls(e,'source_operation_read').length;
 const check=screen.getByRole('button',{name:'Check original operation'});
 window.MastermindMissionHost={...e.host}; // same methods/epoch, different actual owner; no notify/render
 fireEvent.click(check);await act(async()=>{});
 expect(calls(e,'source_operation_read')).toHaveLength(before);
 expect(calls(e,'source_operation_reconcile')).toHaveLength(0);
 expect(await e.store.read(scope)).toEqual(original);
 window.MastermindMissionHost=e.host;
 fireEvent.click(screen.getByRole('button',{name:'Check original operation'}));
 await screen.findByRole('button',{name:'Continue original adoption'});
 expect(calls(e,'source_operation_submit')).toHaveLength(1);
 expect(calls(e,'source_operation_reconcile')).toHaveLength(1);
});
it('actual native auth loss withholds a late settled response and preserves the original App hint',async()=>{
 const e=await setup({holdSubmit:true});await prepare();
 fireEvent.click(screen.getByRole('button',{name:'Adopt this plan'}));
 await waitFor(()=>expect(calls(e,'source_operation_submit')).toHaveLength(1));
 expect(await e.store.read(scope)).toEqual(original);
 act(()=>e.notify({payload:{status:'signed_out',reason:'AUTHENTICATION_REQUIRED',acquisition:false,content:false}}));
 await act(async()=>e.finish(actual.status));
 expect(screen.queryByText(/Publication of the original adoption is confirmed/)).toBeNull();
 expect(await e.store.read(scope)).toEqual(original);
 expect(calls(e,'source_operation_reconcile')).toHaveLength(0);
 expect(calls(e,'source_operation_advance')).toHaveLength(0);
});
