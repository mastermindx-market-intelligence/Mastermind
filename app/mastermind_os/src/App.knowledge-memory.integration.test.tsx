// @vitest-environment jsdom
/** ONE signed installed compiler/HTTP/Unix/Runtime/tempGit source sequence.
 * Only native invoke/auth is inert. Canonical Programs/Memory/files/receipts
 * are unchanged; current catalogue supplies every source selector. */
import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {IDBFactory} from 'fake-indexeddb';
import {App} from './App';
import {createNativeClient} from './host';
import {composeMissionHost} from './compose-mission-host';
import {decodeLaunchBindingConfig} from './launch-config';
import source from './fixtures/knowledge-memory-source.json';
let dispose=()=>{};
beforeEach(async()=>{history.replaceState(null,'','/os/');delete window.MastermindMissionHost;
 const {webcrypto}=await vi.importActual<{webcrypto:Crypto}>('node:crypto');vi.stubGlobal('crypto',webcrypto);});
afterEach(()=>{cleanup();dispose();vi.restoreAllMocks();vi.unstubAllGlobals();delete window.MastermindMissionHost;});
async function setup({lost=false,holdSource=false}={}){
 let stage:'before'|'proposal'|'after'='before',finish!:(body:unknown)=>void;
 const waiting=new Promise(resolve=>{finish=resolve;});
 const events=new Map<string,Set<(event:{payload:unknown})=>void>>();
 const lookup={...source.preview.selection,source_commit:source.request.source_commit,base_revision:source.request.base_revision,
  request_sha256:source.preview.request_sha256,expected_preference_revision:source.request.expected_preference_revision};
 const invoke=vi.fn(async(command:string,args?:any):Promise<unknown>=>{
  if(command==='auth_status')return{status:'signed_in',reason:null,acquisition:true,content:false};
  if(command==='executive_auth_status')return{generation:0,available:false};
  if(command==='read_programs')return structuredClone(source.programs);
  if(command==='read_project_knowledge_catalogue')return structuredClone(stage==='after'?source.after:stage==='proposal'?source.pr_only_catalogue:source.before);
  if(command==='read_project_knowledge_memory')return structuredClone(stage==='after'?source.memory_after:source.memory_before);
  if(command==='read_source_operation_context'){
   expect(args.selection.work_ref).toBe(source.request.work_ref);
   return structuredClone(args.selection.action==='add_project_file'?source.file_context:source.context);
  }
  if(command==='source_operation_prepare'){
   expect(args.request).toEqual({action:'set_project_communication_preference',request:source.request});return structuredClone(source.preview);
  }
  if(command==='source_operation_submit'){
   expect(args.request).toEqual({...source.preview.selection,preview_witness:source.preview.preview_witness});stage='proposal';
   if(lost)throw Error('lost response after original source operation');return structuredClone(source.proposal_status);
  }
  if(command==='source_operation_read'||command==='source_operation_reconcile'){
   expect(args.request).toEqual(lookup);return structuredClone(stage==='after'?source.accepted_status:source.proposal_status);
  }
  if(command==='read_project_knowledge_source'){
   const options=stage==='after'?[source.source_after,source.file_after]:[source.source_before,source.file_before];
   const body=options.find(item=>item.selection.source_ref===args.selection.source_ref&&item.source.revision===args.selection.expected_revision);
   if(!body)throw Error('Source selector is not in the current actual fixture');
   return holdSource?waiting:structuredClone(body);
  }
  throw Error('No current-session/provider or other capability supplied');
 });
 const client=await createNativeClient(invoke as never,async(name,listener)=>{const set=events.get(name)??new Set();set.add(listener);events.set(name,set);return()=>set.delete(listener);});
 const config=decodeLaunchBindingConfig(JSON.stringify({v:1,workstream:'WS:EXECUTIVE-ECOSYSTEM-COMPLETION',priority:0,attemptLimit:1,
  projects:[{ref:'executive-infrastructure',label:'Infrastructure'}],profiles:[{ref:'research_only',label:'Research'}]}))!;
 const composed=composeMissionHost(client,config,new IDBFactory(),'native');await composed.ready;await composed.sessionReady;
 window.MastermindMissionHost=composed.host;const mount=()=>render(<App/>);const view=mount();dispose=()=>{view.unmount();composed.dispose();};
 const calls=(name:string)=>invoke.mock.calls.filter(([command])=>command===name);
 const open=async()=>{fireEvent.click(screen.getByRole('button',{name:'Projects'}));
  const title=source.programs.control_room.work.find(row=>row.work_ref===source.request.work_ref)!.agent_os.title;
  fireEvent.click(await screen.findByRole('button',{name:`Open project ${title}`}));fireEvent.click(screen.getByRole('button',{name:'Knowledge'}));
  await screen.findByRole('tab',{name:'Memory'});
 };
 await open();return{view,mount,open,calls,host:composed.host,finish,land:()=>{stage='after';},
  notify:(name:string,payload:unknown)=>events.get(name)?.forEach(fn=>fn({payload}))};
}
async function edit(){
 fireEvent.click(screen.getByRole('tab',{name:'Memory'}));
 const original=await screen.findByText((_text,node)=>node?.classList.contains('knowledge-library-memory-value')===true&&node.textContent===source.memory_before.memory.value);expect(original.textContent).toBe(source.memory_before.memory.value);
 vi.spyOn(crypto,'getRandomValues').mockImplementation(array=>{(array as Uint8Array).fill(0xbb);return array;});
 const button=await screen.findByRole('button',{name:'Edit'});await waitFor(()=>expect(button).toHaveProperty('disabled',false));fireEvent.click(button);
 const value=screen.getByRole('textbox',{name:'Communication preference'});expect(value).toHaveProperty('value',source.memory_before.memory.value);
 fireEvent.change(value,{target:{value:source.request.value}});fireEvent.click(screen.getByRole('button',{name:'Save preference'}));
 return screen.findByRole('button',{name:'Publish changes'});
}
it('edits actual populated Memory using its canonical content CAS, publishes once, and reopens exact text plus scoped file Search',async()=>{
 const e=await setup();const publish=await edit(),scope=source.preview.owner_context.principal_scope;
 expect(await e.host.commandBinding!.store.read(scope)).toBeNull();expect(e.calls('source_operation_submit')).toHaveLength(0);
 fireEvent.click(publish);await screen.findByText('The project source has not confirmed this save. Check the original publication; do not submit it again.');
 e.land();fireEvent.click(screen.getByRole('button',{name:'Check publication status'}));await screen.findByText('Saved to the project source.');
 await waitFor(async()=>expect(await e.host.commandBinding!.store.read(scope)).toBeNull());
 fireEvent.click(screen.getByRole('button',{name:'Close editor'}));fireEvent.click(await screen.findByRole('tab',{name:'Memory'}));
 const text=await screen.findByText((_text,node)=>node?.classList.contains('knowledge-library-memory-value')===true&&node.textContent===source.request.value);expect(text.textContent).toBe(source.request.value);
 fireEvent.click(screen.getByRole('button',{name:'Back to files'}));
 const row=(await screen.findByRole('heading',{level:3,name:source.file_request.file.display_name})).closest('.knowledge-library-row')!;
 fireEvent.click(within(row as HTMLElement).getByRole('button',{name:'Open'}));await waitFor(()=>expect(screen.getByRole('article').textContent).toContain(source.file_request.file.content_utf8.trim()));
 fireEvent.click(screen.getByRole('button',{name:'Back'}));fireEvent.click(screen.getByRole('button',{name:'Search'}));
 const input=await screen.findByLabelText('Search this project');fireEvent.change(input,{target:{value:'literal'}});fireEvent.submit(input.closest('form')!);
 fireEvent.click(await screen.findByRole('button',{name:'Open'}));await waitFor(()=>expect(screen.getByRole('article').textContent).toContain(source.file_request.file.content_utf8.trim()));
 fireEvent.click(screen.getByRole('button',{name:'Back'}));expect(screen.getByLabelText('Search this project')).toHaveProperty('value','literal');
 e.view.unmount();e.mount();await e.open();fireEvent.click(screen.getByRole('tab',{name:'Memory'}));
 await screen.findByText((_text,node)=>node?.classList.contains('knowledge-library-memory-value')===true&&node.textContent===source.request.value);
 expect(e.calls('source_operation_prepare')).toHaveLength(1);expect(e.calls('source_operation_submit')).toHaveLength(1);expect(e.calls('source_operation_reconcile')).toHaveLength(1);
 expect(e.calls('read_mission_v3')).toHaveLength(0);
});
it('retains a lost Memory publication across App reopen and reconciles only the same original lookup',async()=>{
 const e=await setup({lost:true});fireEvent.click(await edit());
 await screen.findByText('The project source has not confirmed this save. Check the original publication; do not submit it again.');
 const scope=source.preview.owner_context.principal_scope,pointer=await e.host.commandBinding!.store.read(scope);expect(pointer?.kind).toBe('project_source_write');
 e.view.unmount();e.mount();await e.open();expect(e.calls('source_operation_reconcile')).toHaveLength(0);
 e.land();fireEvent.click(screen.getByRole('button',{name:'Check publication status'}));await screen.findByText('Saved to the project source.');
 expect(e.calls('source_operation_prepare')).toHaveLength(1);expect(e.calls('source_operation_submit')).toHaveLength(1);expect(e.calls('source_operation_reconcile')).toHaveLength(1);
 expect(await e.host.commandBinding!.store.read(scope)).toBeNull();
});
it('rejects a detached actual prepared Memory Publish after native auth withdrawal',async()=>{
 const e=await setup(),publish=await edit();
 act(()=>e.notify('mastermind-auth-state',{status:'signed_out',reason:null,acquisition:false,content:false}));
 fireEvent.click(publish);expect(e.calls('source_operation_submit')).toHaveLength(0);
 expect(await e.host.commandBinding!.store.read(source.preview.owner_context.principal_scope)).toBeNull();
});
it('withholds a genuine scoped file body after actual source read auth withdrawal',async()=>{
 const e=await setup({holdSource:true});
 const row=(await screen.findByRole('heading',{level:3,name:source.file_request.file.display_name})).closest('.knowledge-library-row')!;
 fireEvent.click(within(row as HTMLElement).getByRole('button',{name:'Open'}));await waitFor(()=>expect(e.calls('read_project_knowledge_source')).toHaveLength(1));
 act(()=>e.notify('mastermind-auth-state',{status:'signed_out',reason:null,acquisition:false,content:false}));
 await act(async()=>{e.finish(source.file_before);});
 expect(document.querySelector('.knowledge-library-document')?.textContent??'').not.toContain(source.file_request.file.content_utf8.trim());
 expect(e.calls('source_operation_submit')).toHaveLength(0);
});
