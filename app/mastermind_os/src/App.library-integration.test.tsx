// @vitest-environment jsdom
import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {App} from './App';
import {bindMissionHost,createNativeClient} from './host';
import type {SavedConversationSearchOwner} from './discovery/saved-conversations';
import {controlRoomFixture} from './test-fixtures';
import programs from './fixtures/programs-available-workspace-service.json';
import library from './fixtures/project-knowledge-owner.json';
const signed={status:'signed_in',reason:null,acquisition:true,content:false};
const uploaded=library.catalogue.project.files.find(row=>row.origin.kind==='PRINCIPAL_UPLOAD')!;
beforeEach(async()=>{history.replaceState(null,'','/os/');delete window.MastermindMissionHost;delete (window as any).__TAURI_INTERNALS__;
 const {webcrypto}=await vi.importActual<{webcrypto:Crypto}>('node:crypto');vi.stubGlobal('crypto',webcrypto);});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();delete window.MastermindMissionHost;});
async function setup(pendingSource=false, historyOwner?:SavedConversationSearchOwner){
 const room=controlRoomFixture(),row=structuredClone(room.work[0]);row.work_ref=library.work_ref;row.agent_os.workstream=library.work_ref.slice(3);
 row.agent_os.title='Qualified library project';row.executive.jobs=[];row.bindings=[];room.work=[row];room.autonomy.responsibilities=[];
 const collection={...structuredClone(programs),control_room:room};
 let notify!:(event:{payload:unknown})=>void,finish!:(value:unknown)=>void;
 const held=new Promise(resolve=>{finish=resolve;});
 const invoke=vi.fn(async(command:string,args?:any)=>{
  if(command==='auth_status')return signed;if(command==='executive_auth_status')return {generation:0,available:false};
  if(command==='read_programs')return structuredClone(collection);
  if(command==='read_project_knowledge_catalogue')return structuredClone(library.catalogue);
  if(command==='read_project_knowledge_memory')return structuredClone(library.memory);
  if(command==='read_project_knowledge_source')return pendingSource?held:structuredClone(library.sources[args.selection.source_ref as keyof typeof library.sources]);
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
 render(<App/>);fireEvent.click(screen.getByRole('button',{name:'Projects'}));
 fireEvent.click(await screen.findByRole('button',{name:'Open project Qualified library project'}));
 return {invoke,notify,finish};
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
 expect(screen.getAllByRole('heading',{level:1})).toHaveLength(1);
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
