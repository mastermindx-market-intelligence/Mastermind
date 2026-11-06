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
let dispose=()=>{};
beforeEach(async()=>{
 history.replaceState(null,'','/os/');delete window.MastermindMissionHost;
 const {webcrypto}=await vi.importActual<{webcrypto:Crypto}>('node:crypto');vi.stubGlobal('crypto',webcrypto);
 vi.useFakeTimers({toFake:['Date']});vi.setSystemTime(new Date(source.clock_seconds*1000));
});
afterEach(()=>{cleanup();dispose();vi.useRealTimers();vi.restoreAllMocks();vi.unstubAllGlobals();delete window.MastermindMissionHost;});
async function setup(holdOpen=false){
 const listeners=new Map<string,Set<(event:{payload:unknown})=>void>>();
 let replies=0,finish!:(value:unknown)=>void;const pending=new Promise(resolve=>{finish=resolve;});
 const invoke=vi.fn(async(command:string,args?:Record<string,unknown>):Promise<unknown>=>{
  if(command==='auth_status')return{status:'signed_in',reason:null,acquisition:true,content:false};
  if(command==='executive_auth_status')return{generation:1,available:true};
  if(command==='executive_context')return structuredClone(source.executive_context);
  if(command==='read_programs')return structuredClone(source.programs);
  if(command==='executive_project_history_context'){expect(args).toEqual({workRef:source.work_ref});return structuredClone(source.history_context);}
  if(command==='executive_project_session_references'){expect(args).toEqual({workRef:source.work_ref});return structuredClone(source.references);}
  if(command==='executive_session_reply'){
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
