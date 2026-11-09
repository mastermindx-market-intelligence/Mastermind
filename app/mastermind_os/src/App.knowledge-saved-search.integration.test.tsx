// @vitest-environment jsdom
/** Actual signed original-reference/reply owner + canonical project fixture.
 * Native invoke/auth is inert; real NativeClient/Host/App/session verifier/IDB. */
import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {IDBFactory} from 'fake-indexeddb';
import {App} from './App';
import {createNativeClient} from './host';
import type {MountedExecutiveSessionBinding} from './orchestration/os-executive-session-host';
import {composeMissionHost} from './compose-mission-host';
import {decodeLaunchBindingConfig} from './launch-config';
import source from './fixtures/knowledge-saved-search-source.json';
import library from './fixtures/project-knowledge-owner.json';
import historyOwner from './fixtures/project-conversation-history-owner.json';
let dispose=()=>{};
beforeEach(async()=>{
 history.replaceState(null,'','/os/');delete window.MastermindMissionHost;
 const {webcrypto}=await vi.importActual<{webcrypto:Crypto}>('node:crypto');vi.stubGlobal('crypto',webcrypto);
 vi.useFakeTimers({toFake:['Date']});vi.setSystemTime(new Date(source.clock_seconds*1000));
});
afterEach(()=>{cleanup();dispose();vi.useRealTimers();vi.restoreAllMocks();vi.unstubAllGlobals();delete window.MastermindMissionHost;});
type NativeSearchBoundary = {
 catalogue?: () => unknown;
 readFile?: (selection: Record<string,unknown>) => unknown;
 references?: (args: Record<string,unknown>) => unknown;
 reply?: (args: Record<string,unknown>) => unknown;
};
async function setup(holdOpen=false,boundary:NativeSearchBoundary={}){
 const listeners=new Map<string,Set<(event:{payload:unknown})=>void>>();
 let replies=0,finish!:(value:unknown)=>void;const pending=new Promise(resolve=>{finish=resolve;});
 const invoke=vi.fn(async(command:string,args?:Record<string,unknown>):Promise<unknown>=>{
  if(command==='auth_status')return{status:'signed_in',reason:null,acquisition:true,content:false};
  if(command==='executive_auth_status')return{generation:1,available:true};
  if(command==='executive_context')return structuredClone(source.executive_context);
  if(command==='read_programs')return structuredClone(source.programs);
  if(command==='read_project_knowledge_catalogue'&&boundary.catalogue){
   expect(args).toEqual({selection:{work_ref:source.work_ref}});
   return structuredClone(boundary.catalogue());
  }
  if(command==='read_project_knowledge_source'&&boundary.readFile)
   return structuredClone(boundary.readFile(args?.selection as Record<string,unknown>));
  if(command==='executive_project_history_context'){expect(args).toEqual({workRef:source.work_ref});return structuredClone(source.history_context);}
  if(command==='executive_project_session_references'){
   if(boundary.references)return structuredClone(boundary.references(args??{}));
   expect(args).toEqual({workRef:source.work_ref});return structuredClone(source.references);
  }
  if(command==='executive_session_reply'){
   if(boundary.reply)return structuredClone(boundary.reply(args??{}));
   expect(args).toEqual({operationKey:source.references.data.references[0].operation_key});
   return holdOpen&&++replies===2?pending:structuredClone(source.reply);
  }
  throw Error('No current target/send/provider or other capability supplied');
 });
 const client=await createNativeClient(invoke as never,async(name,listener)=>{
  const set=listeners.get(name)??new Set();set.add(listener);listeners.set(name,set);return()=>set.delete(listener);
 });
 const config=decodeLaunchBindingConfig(JSON.stringify({v:1,workstream:'WS:EXECUTIVE-ECOSYSTEM-COMPLETION',priority:0,attemptLimit:1,
  projects:[{ref:'executive-infrastructure',label:'Infrastructure'}],profiles:[{ref:'research_only',label:'Research'}]}))!;
 const composed=composeMissionHost(client,config,new IDBFactory(),'native');await composed.ready;await composed.sessionReady;
 window.MastermindMissionHost=composed.host;const view=render(<App/>);dispose=()=>{view.unmount();composed.dispose();};
 fireEvent.click(screen.getByRole('button',{name:'Projects'}));
 const title=source.programs.control_room.work.find(row=>row.work_ref===source.work_ref)!.agent_os.title;
 fireEvent.click(await screen.findByRole('button',{name:`Open project ${title}`}));
 fireEvent.click(screen.getByRole('button',{name:'Search'}));
 const calls=(command:string)=>invoke.mock.calls.filter(([name])=>name===command);
 return{view,host:composed.host,calls,finish,notify:(name:string,payload:unknown)=>listeners.get(name)?.forEach(fn=>fn({payload}))};
}
async function search(){
 fireEvent.click(await screen.findByRole('button',{name:'Read saved reply search source'}));
 await waitFor(()=>expect(screen.queryByRole('button',{name:'Reading…'})).toBeNull());
 fireEvent.click(screen.getByRole('button',{name:'Saved conversations'}));
 const input=screen.getByLabelText('Search this project');fireEvent.change(input,{target:{value:'bounded'}});fireEvent.submit(input.closest('form')!);
 return within(document.querySelector('.project-search') as HTMLElement).findByRole('button',{name:'Open'});
}
it('searches original saved replies without a current target, re-reads Open, and preserves query on Back/reopen',async()=>{
 const e=await setup(),legacy=e.host.sessionCommandBinding as MountedExecutiveSessionBinding;expect(legacy.port.context()).toBeNull();expect(legacy.port.projectHistory!.context()).toBeNull();expect(e.calls('executive_project_history_context')).toHaveLength(0);expect(e.calls('executive_project_session_references')).toHaveLength(0);
 fireEvent.click(await search());
 await waitFor(()=>expect(screen.getByRole('article').textContent).toContain(source.reply.data.text));
 expect(e.calls('executive_project_session_references')).toHaveLength(2);expect(e.calls('executive_session_reply')).toHaveLength(2);
 fireEvent.click(screen.getByRole('button',{name:'Back to search'}));expect(screen.getByLabelText('Search this project')).toHaveProperty('value','bounded');
 fireEvent.click(await within(document.querySelector('.project-search') as HTMLElement).findByRole('button',{name:'Open'}));
 await waitFor(()=>expect(screen.getByRole('article').textContent).toContain(source.reply.data.text));
 expect(e.calls('executive_project_history_context')).toHaveLength(1);
 expect(e.calls('executive_project_session_references')).toHaveLength(3);
 expect(e.calls('executive_session_context')).toHaveLength(0);expect(e.calls('executive_submit')).toHaveLength(0);
 expect(e.calls('executive_session_send')).toHaveLength(0);
 expect(await e.host.commandBinding!.store.read(source.history_context.data.principal_scope)).toBeNull();
});
it('withholds a genuine late saved reply after actual Executive READ withdrawal',async()=>{
 const e=await setup(true);fireEvent.click(await search());
 await waitFor(()=>expect(e.calls('executive_session_reply')).toHaveLength(2));
 act(()=>e.notify('mastermind-executive-auth-state',{generation:2,available:false}));
 await act(async()=>{e.finish(source.reply);});
 expect(document.querySelector('.knowledge-library-document')?.textContent??'').not.toContain(source.reply.data.text);
 expect(e.calls('executive_session_send')).toHaveLength(0);
});
it('refuses a detached saved-result Open after actual Host replacement',async()=>{
 const e=await setup();const open=await search(),count=e.calls('executive_project_session_references').length;
 window.MastermindMissionHost={...e.host};fireEvent.click(open);
 expect(e.calls('executive_project_session_references')).toHaveLength(count);
 expect(screen.queryByRole('button',{name:'Back to search'})).toBeNull();
});


/** Extend the incumbent raw Python fixture with distinct, bounded native entries.
 * The App, host owners, decoders and file-search producer remain unmocked. */
async function filePages(){
 const catalogue=structuredClone(library.catalogue);
 catalogue.selection.work_ref=source.work_ref;
 for(const record of catalogue.project.records){
  if(record.kind==='WORKSTREAM')record.path='agentos/workstreams/WS-'+source.work_ref.slice(3)+'.md';
  if(record.kind==='PROJECT_PREFERENCE')record.path='agentos/decisions/DEC-PROJECT-COMMUNICATION-PREFERENCE-'+source.work_ref.slice(3)+'.md';
 }
 const declared=library.catalogue.project.files.find(row=>row.origin.kind==='DECLARED_ARTIFACT')!;
 const uploaded=library.catalogue.project.files.find(row=>row.origin.kind==='PRINCIPAL_UPLOAD')!;
 const bodies:Record<string,(typeof library.sources)[keyof typeof library.sources]>={};
 catalogue.project.files=[];
 for(let index=0;index<8;index++){
  const original=index===4?uploaded:declared;
  const body=structuredClone(library.sources[original.source_ref as keyof typeof library.sources]);
  const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode('bounded-search-entry-'+index));
  const ref='project-file.v1.'+Array.from(new Uint8Array(digest),byte=>byte.toString(16).padStart(2,'0')).join('');
  const path='research/page-'+(index+1)+'.md',title='Page file '+(index+1);
  const row={...structuredClone(declared),source_ref:ref,path,display_name:title,
   revision:body.source.revision,content_sha256:body.document.content_sha256};
  body.selection={work_ref:source.work_ref,source_ref:ref};
  body.source.path=path;body.document.title=title;
  catalogue.project.files.push(row);bodies[ref]=body;
 }
 catalogue.project.coverage.files={state:'COMPLETE',declared:8,listed:8,omitted:0};
 return{catalogue,bodies,readFile:(selection:Record<string,unknown>)=>{
  const body=bodies[String(selection.source_ref)];
  expect(body).toBeDefined();
  expect(selection).toEqual({work_ref:source.work_ref,source_ref:body.selection.source_ref,
   expected_revision:body.source.revision});
  expect(body.source.commit).toBe(catalogue.source.commit);
  return body;
 }};
}
function submitQuery(query:string){
 const input=screen.getByLabelText('Search this project');
 fireEvent.change(input,{target:{value:query}});fireEvent.submit(input.closest('form')!);
 return within(document.querySelector('.project-search') as HTMLElement);
}
it('continues an empty first file page only on explicit Next through the actual App search producer',async()=>{
 const fixture=await filePages();
 const e=await setup(false,{catalogue:()=>fixture.catalogue,readFile:fixture.readFile});
 const searchView=submitQuery('中文');
 await waitFor(()=>expect(e.calls('read_project_knowledge_source')).toHaveLength(4));
 const next=await searchView.findByRole('button',{name:'Next page'});
 expect(next).toHaveProperty('disabled',false);
 expect(searchView.queryByRole('button',{name:'Open'})).toBeNull();
 expect(searchView.getByRole('status').textContent).toContain('scanned 4 · matched 0 · unavailable 0');
 expect(e.calls('read_project_knowledge_catalogue')).toHaveLength(1);
 expect(e.calls('read_project_knowledge_source').map(([,args])=>(args!.selection as Record<string,unknown>).source_ref))
  .toEqual(fixture.catalogue.project.files.slice(0,4).map(row=>row.source_ref));
 await act(async()=>{});
 expect(e.calls('read_project_knowledge_catalogue')).toHaveLength(1);
 expect(e.calls('read_project_knowledge_source')).toHaveLength(4);
 fireEvent.click(next);
 await searchView.findByText('Page file 5');
 expect(searchView.getAllByRole('button',{name:'Open'})).toHaveLength(1);
 expect(e.calls('read_project_knowledge_catalogue')).toHaveLength(2);
 expect(e.calls('read_project_knowledge_source').map(([,args])=>(args!.selection as Record<string,unknown>).source_ref))
  .toEqual(fixture.catalogue.project.files.map(row=>row.source_ref));
 expect(searchView.queryByRole('button',{name:'Next page'})).toBeNull();
 expect(e.calls('executive_submit')).toHaveLength(0);
 expect(e.calls('executive_session_send')).toHaveLength(0);
});


it('refuses a changed catalogue commit before any next-page file body is read',async()=>{
 const fixture=await filePages();
 const e=await setup(false,{catalogue:()=>fixture.catalogue,readFile:fixture.readFile});
 const searchView=submitQuery('中文');
 const next=await searchView.findByRole('button',{name:'Next page'});
 expect(e.calls('read_project_knowledge_source')).toHaveLength(4);
 fixture.catalogue.source.commit='f'.repeat(40);
 fireEvent.click(next);
 await searchView.findByText('The source changed since this view loaded. Refresh to try again.',{exact:false});
 expect(e.calls('read_project_knowledge_catalogue')).toHaveLength(2);
 expect(e.calls('read_project_knowledge_source')).toHaveLength(4);
 expect(searchView.queryByRole('button',{name:'Open'})).toBeNull();
 await act(async()=>{});
 expect(e.calls('read_project_knowledge_catalogue')).toHaveLength(2);
 expect(e.calls('read_project_knowledge_source')).toHaveLength(4);
});

function savedPages(){
 // Reuse the two existing original-reference/reply fixture pairs unchanged.
 // Only the bounded page envelope supplies the inert opaque continuation.
 const cursor='cursor-2',second=structuredClone(historyOwner.page);
 const first={...structuredClone(source.references),data:{...structuredClone(source.references.data),
  status:'PARTIAL',next_cursor:cursor,high_water:second.data.high_water}};
 const boundary:NativeSearchBoundary={
  references:args=>{
   if(args.cursor===undefined){expect(args).toEqual({workRef:source.work_ref});return first;}
   expect(args).toEqual({workRef:source.work_ref,cursor});return second;
  },
  reply:args=>{
   if(args.operationKey===source.reply.operation_key){
    expect(args).toEqual({operationKey:source.reply.operation_key});return source.reply;
   }
   expect(args).toEqual({operationKey:historyOwner.answer.operation_key});return historyOwner.answer;
  },
 };
 return{boundary,first,second,cursor};
}
async function submitSavedQuery(query:string){
 fireEvent.click(await screen.findByRole('button',{name:'Read saved reply search source'}));
 await waitFor(()=>expect(screen.queryByRole('button',{name:'Reading…'})).toBeNull());
 fireEvent.click(screen.getByRole('button',{name:'Saved conversations'}));
 return submitQuery(query);
}
it('continues an empty saved-reply search page only after explicit Next with its original cursor and high-water mark',async()=>{
 const fixture=savedPages(),e=await setup(false,fixture.boundary);
 const searchView=await submitSavedQuery('durable');
 const next=await searchView.findByRole('button',{name:'Next page'});
 expect(next).toHaveProperty('disabled',false);
 expect(searchView.queryByRole('button',{name:'Open'})).toBeNull();
 expect(searchView.getByRole('status').textContent).toContain('scanned 1 · matched 0 · unavailable 0');
 expect(e.calls('executive_project_session_references')).toEqual([
  ['executive_project_session_references',{workRef:source.work_ref}],
 ]);
 expect(e.calls('executive_session_reply')).toEqual([
  ['executive_session_reply',{operationKey:source.reply.operation_key}],
 ]);
 await act(async()=>{});
 expect(e.calls('executive_project_session_references')).toHaveLength(1);
 expect(e.calls('executive_session_reply')).toHaveLength(1);
 fireEvent.click(next);
 await searchView.findByText(historyOwner.answer.data.text);
 expect(searchView.getAllByRole('button',{name:'Open'})).toHaveLength(1);
 expect(e.calls('executive_project_session_references')).toEqual([
  ['executive_project_session_references',{workRef:source.work_ref}],
  ['executive_project_session_references',{workRef:source.work_ref,cursor:fixture.cursor}],
 ]);
 expect(e.calls('executive_session_reply')).toEqual([
  ['executive_session_reply',{operationKey:source.reply.operation_key}],
  ['executive_session_reply',{operationKey:historyOwner.answer.operation_key}],
 ]);
 expect(searchView.queryByRole('button',{name:'Next page'})).toBeNull();
 expect(e.calls('executive_session_context')).toHaveLength(0);
 expect(e.calls('executive_submit')).toHaveLength(0);
 expect(e.calls('executive_session_send')).toHaveLength(0);
});
it('refuses a changed saved-page high-water mark before opening another original reply',async()=>{
 const fixture=savedPages(),e=await setup(false,fixture.boundary);
 const searchView=await submitSavedQuery('durable');
 const next=await searchView.findByRole('button',{name:'Next page'});
 expect(e.calls('executive_session_reply')).toHaveLength(1);
 fixture.second.data.high_water++;
 fireEvent.click(next);
 await searchView.findByText('The source changed since this view loaded. Refresh to try again.',{exact:false});
 expect(e.calls('executive_project_session_references')).toHaveLength(2);
 expect(e.calls('executive_session_reply')).toHaveLength(1);
 expect(searchView.queryByRole('button',{name:'Open'})).toBeNull();
 await act(async()=>{});
 expect(e.calls('executive_project_session_references')).toHaveLength(2);
 expect(e.calls('executive_session_reply')).toHaveLength(1);
});
