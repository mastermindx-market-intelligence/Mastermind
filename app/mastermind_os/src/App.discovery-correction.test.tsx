// @vitest-environment jsdom
/** Actual correction owner/temp-Git records and receipts through the full App.
 * Native auth, Programs orientation and initial installed CODE are explicit
 * fixture seams. The refreshed catalogue is a genuine read-only legacy frame;
 * this test does not claim a live current-DATA compiler or installed account. */
import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {IDBFactory} from 'fake-indexeddb';
import {App} from './App';
import {bindMissionHost,createNativeClient} from './host';
import {createIndexedDbPendingPointerStore} from './orchestration/indexeddb-pending-pointer-store';
import {controlRoomFixture} from './test-fixtures';
import programs from './fixtures/programs-available-workspace-service.json';
import journey from './fixtures/discovery-correction-owner.json';
beforeEach(async()=>{
 history.replaceState(null,'','/os/');delete window.MastermindMissionHost;delete (window as any).__TAURI_INTERNALS__;
 const {webcrypto}=await vi.importActual<{webcrypto:Crypto}>('node:crypto');vi.stubGlobal('crypto',webcrypto);
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();delete window.MastermindMissionHost;});
async function setup(){
 let stage:'before'|'proposal'|'landed'='before',lostPrepare=false;
 const room=controlRoomFixture(),row=structuredClone(room.work[0]);
 row.work_ref=journey.request.work_ref;row.agent_os.workstream=journey.request.work_ref.slice(3);
 row.agent_os.title='Discovery project';row.executive.jobs=[];row.bindings=[];room.work=[row];room.autonomy.responsibilities=[];
 const collection={...structuredClone(programs),control_room:room};let notify!:(event:{payload:unknown})=>void;
 const code={schema:'mastermind.project_knowledge_code_context.v1',work_ref:journey.request.work_ref,
  executable_macro_commit:journey.request.source_commit,reader_source_commit:'9'.repeat(40)};
 const invoke=vi.fn(async(command:string,args?:any)=>{
  if(command==='auth_status')return {status:'signed_in',reason:null,acquisition:true,content:false};
  if(command==='executive_auth_status')return {generation:0,available:false};
  if(command==='read_programs')return structuredClone(collection);
  if(command==='read_project_knowledge_catalogue')return structuredClone(stage==='landed'?journey.after_catalogue:{...journey.before_catalogue,code_context:code});
  if(command==='read_source_operation_context'){
   if(args.selection.action!=='correct_project_discovery')throw Error('Distinct action unavailable');return structuredClone(journey.context);
  }
  if(command==='read_project_knowledge_source'){
   const sources:Record<string,unknown>=stage==='landed'?journey.after_sources:journey.before_sources;
   const source=sources[args.selection.source_ref];if(!source)throw Error('Unknown source');
   return structuredClone(stage==='landed'?source:{...(source as object),code_context:code});
  }
  if(command==='source_operation_prepare'){
   expect(args.request).toEqual({action:'correct_project_discovery',request:journey.request});
   if(lostPrepare)throw Error('Fixture response lost after durable prepare');return structuredClone(journey.preview);
  }
  if(command==='source_operation_submit'){stage='proposal';return structuredClone(journey.proposal_status);}
  if(command==='source_operation_read'){expect(args.request).toEqual(journey.lookup);return structuredClone(journey.prepared_status);}
  if(command==='source_operation_reconcile'){expect(args.request).toEqual(journey.lookup);return structuredClone(stage==='landed'?journey.source_status:journey.proposal_status);}
  throw Error('Unexpected fixture command');
 });
 const raw=await createNativeClient(invoke as never,async(_name,listener)=>{notify=listener;return()=>{};});
 const host=bindMissionHost(raw),store=createIndexedDbPendingPointerStore(new IDBFactory());
 delete host.readProjectArchive;delete host.readProjectArchivePage;
 const forbidden=vi.fn(()=>{throw Error('No Executive mutation authority in UI fixture');});
 host.commandBinding={store,port:{context:()=>null,prepare:forbidden,submit:forbidden,readOperation:forbidden},
  getView:()=>({projects:[],profiles:[],session:null}),subscribe:()=>()=>{},makeLaunchIntent:forbidden,makeMessageIntent:forbidden,makeStopIntent:forbidden};
 window.MastermindMissionHost=host;const mounted=render(<App/>);
 fireEvent.click(screen.getByRole('button',{name:'Projects'}));
 fireEvent.click(await screen.findByRole('button',{name:'Open project Discovery project'}));fireEvent.click(screen.getByRole('button',{name:'Knowledge'}));
 await screen.findByRole('heading',{name:journey.before_catalogue.project.title});
 async function open(){
  fireEvent.click(screen.getByRole('button',{name:'Browse all records'}));
  const finding=await screen.findByText('The original measured result.');
  fireEvent.click(within(finding.closest('.knowledge-library-row') as HTMLElement).getByRole('button',{name:'Open'}));
  fireEvent.click(await screen.findByRole('button',{name:'Correct discovery'}));
 }
 return {invoke,store,mounted,notify,open,land:()=>{stage='landed';},losePrepare:()=>{lostPrepare=true;}};
}
async function fillAndReview(){
 const r=journey.request,values:[string,string][]=[['Why this correction?',r.correction_reason],['Corrected finding',r.replacement.claim],
  ['What would disprove it?',r.replacement.falsifier],['What changes?',r.replacement.so_what],['How was it checked?',r.replacement.verified_by],
  ['Supporting references',r.replacement.evidence.join('\n')],['Evidence and limitations',r.replacement.body_utf8],
  ['Discovery type',r.replacement.kind],['Confidence',r.replacement.confidence],['Evidence date',r.replacement.verified_at]];
 for(const [label,value]of values)fireEvent.change(screen.getByLabelText(label),{target:{value}});
 fireEvent.click(screen.getByRole('button',{name:'Review correction'}));
}
it('opens exact source, reviews explicit evidence, publishes once and refreshes retained history',async()=>{
 const e=await setup();vi.spyOn(globalThis.crypto,'getRandomValues').mockImplementation(array=>{(array as Uint8Array).fill(0xaa);return array;});
 await e.open();expect((screen.getByLabelText('Confidence') as HTMLSelectElement).value).toBe('');
 expect((screen.getByLabelText('Evidence date') as HTMLInputElement).value).toBe('');
 await fillAndReview();const publish=await screen.findByRole('button',{name:'Publish changes'});
 expect(await e.store.read(journey.context.owner_context.principal_scope)).toBeNull();
 const review=screen.getByRole('region',{name:'Review prepared changes'});
 expect(review.textContent).toContain(journey.request.replacement.falsifier);expect(review.textContent).toContain('Probable');
 fireEvent.click(publish);await screen.findByText('The project source has not confirmed this save. Check the original publication; do not submit it again.');
 fireEvent.click(publish);expect(e.invoke.mock.calls.filter(([name])=>name==='source_operation_submit')).toHaveLength(1);
 e.land();fireEvent.click(screen.getByRole('button',{name:'Check publication status'}));await screen.findByText('Saved to the project source.');
 fireEvent.click(await screen.findByRole('button',{name:'Browse all records'}));
 await screen.findByText('The corrected measured result.');
 expect(await e.store.read(journey.context.owner_context.principal_scope)).toBeNull();
 expect(e.invoke.mock.calls.filter(([name])=>name==='source_operation_prepare')).toHaveLength(1);
 expect(e.invoke.mock.calls.filter(([name])=>name==='source_operation_reconcile')).toHaveLength(1);
});
it('reads a lost preparation by its exact original lookup without a submission pointer',async()=>{
 const e=await setup();vi.spyOn(globalThis.crypto,'getRandomValues').mockImplementation(array=>{(array as Uint8Array).fill(0xaa);return array;});
 e.losePrepare();await e.open();await fillAndReview();await screen.findByText('This correction could not be prepared. Check the original operation.');
 fireEvent.click(screen.getByRole('button',{name:'Check original operation'}));await screen.findByText('The original operation was read. No change was resubmitted.');
 expect(e.invoke.mock.calls.filter(([name])=>name==='source_operation_read')).toHaveLength(1);
 expect(e.invoke.mock.calls.filter(([name])=>name==='source_operation_submit'||name==='source_operation_reconcile')).toHaveLength(0);
 expect(await e.store.read(journey.context.owner_context.principal_scope)).toBeNull();
});
it('withdraws a prepared correction when the authenticated owner changes',async()=>{
 const e=await setup();vi.spyOn(globalThis.crypto,'getRandomValues').mockImplementation(array=>{(array as Uint8Array).fill(0xaa);return array;});
 await e.open();await fillAndReview();const retained=await screen.findByRole('button',{name:'Publish changes'});
 await act(async()=>e.notify({payload:{status:'signed_out',reason:null,acquisition:false,content:false}}));
 expect(screen.queryByRole('button',{name:'Publish changes'})).toBeNull();fireEvent.click(retained);
 expect(e.invoke.mock.calls.filter(([name])=>name==='source_operation_submit')).toHaveLength(0);
});
