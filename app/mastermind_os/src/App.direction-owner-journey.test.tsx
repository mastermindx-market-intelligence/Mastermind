// @vitest-environment jsdom
/** ONE actual signed HTTP/temporary Unix/installed canonical owner sequence.
 * Native auth/invoke only are inert; no projected rows or owner clocks edited. */
import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {IDBFactory} from 'fake-indexeddb';
import {App} from './App';
import {createNativeClient} from './host';
import {composeMissionHost} from './compose-mission-host';
import {decodeLaunchBindingConfig} from './launch-config';
import source from './fixtures/direction-app-source.json';
let dispose=()=>{};
beforeEach(async()=>{history.replaceState(null,'','/os/');delete window.MastermindMissionHost;
 const {webcrypto}=await vi.importActual<{webcrypto:Crypto}>('node:crypto');vi.stubGlobal('crypto',webcrypto);});
afterEach(()=>{cleanup();dispose();vi.restoreAllMocks();vi.unstubAllGlobals();delete window.MastermindMissionHost;});
async function setup({hold=false,foreign=false}={}){
 let finish!:(value:unknown)=>void;const pending=new Promise(resolve=>{finish=resolve;});
 const events=new Map<string,Set<(event:{payload:unknown})=>void>>();
 const invoke=vi.fn(async(command:string,args?:any):Promise<unknown>=>{
  if(command==='auth_status')return{status:'signed_in',reason:null,acquisition:true,content:false};
  if(command==='executive_auth_status')return{generation:0,available:false};
  if(command==='read_programs')return structuredClone(source.programs);
  if(command==='read_project_direction'){
   expect(args).toEqual({selection:{work_ref:source.work_ref}});
   return hold?pending:structuredClone(foreign?source.foreign:source.direction);
  }
  throw Error('No Runtime target, provider or write capability supplied');
 });
 const client=await createNativeClient(invoke as never,async(name,listener)=>{const set=events.get(name)??new Set();set.add(listener);events.set(name,set);return()=>set.delete(listener);});
 const config=decodeLaunchBindingConfig(JSON.stringify({v:1,workstream:'WS:EXECUTIVE-ECOSYSTEM-COMPLETION',priority:0,attemptLimit:1,
  projects:[{ref:'executive-infrastructure',label:'Infrastructure'}],profiles:[{ref:'research_only',label:'Research'}]}))!;
 const composed=composeMissionHost(client,config,new IDBFactory(),'native');await composed.ready;await composed.sessionReady;
 window.MastermindMissionHost=composed.host;const view=render(<App/>);dispose=()=>{view.unmount();composed.dispose();};
 const open=async()=>{fireEvent.click(screen.getByRole('button',{name:'Projects'}));
  const title=source.programs.control_room.work.find(row=>row.work_ref===source.work_ref)!.agent_os.title;
  fireEvent.click(await screen.findByRole('button',{name:`Open project ${title}`}));
  fireEvent.click(screen.getByRole('button',{name:'Project details'}));
  expect(screen.getByRole('heading',{name:'Project overview'})).toBeTruthy();
  expect(screen.queryByRole('button',{name:'Read instructions'})).toBeNull();
  expect(screen.queryByRole('button',{name:'Check pause status'})).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:"Direction",exact:true}));
 };
 await open();return{open,finish,host:composed.host,calls:(name:string)=>invoke.mock.calls.filter(([command])=>command===name),
  notify:(name:string,payload:unknown)=>events.get(name)?.forEach(fn=>fn({payload})),invoke};
}
const read=()=>fireEvent.click(screen.getByRole('button',{name:'Read Direction'}));
it('reads canonical accepted Direction/history with exact source revision, returns to Projects and rereads on reopen',async()=>{
 const e=await setup();expect(e.calls('read_project_direction')).toHaveLength(0);read();
 const current=await screen.findByRole('article',{name:'Current accepted Direction'});
 expect(current.textContent).toContain(source.direction.direction.current.answer);
 expect(current.textContent).toContain(source.direction.direction.current.rationale);
 const previous=source.direction.direction.history.revisions[0];
 fireEvent.click(screen.getByRole('button',{name:new RegExp(previous.answer)}));
 const selected=screen.getByRole('article',{name:'Previous Direction, read only'});
 expect(selected.textContent).toContain(previous.rationale);
 fireEvent.click(within(selected).getByText('Revision and source details'));
 expect(selected.textContent).toContain(previous.source.commit);expect(selected.textContent).toContain(previous.source.content_sha256);
 expect(selected.textContent).toContain(previous.decided_at);
 expect(screen.getByRole('article',{name:'Current accepted Direction'}).textContent).toContain(source.direction.direction.current.answer);
 fireEvent.click(screen.getByRole('button',{name:'View current Direction'}));
 expect(screen.getByRole('article',{name:'Selected current Direction, read only'}).textContent).toContain(source.direction.direction.current.answer);
 fireEvent.click(screen.getByRole('button',{name:'← Back to project details'}));
 expect(screen.getByRole('heading',{name:'Project overview'})).toBeTruthy();
 expect(document.activeElement).toBe(screen.getByRole('button',{name:'Direction',exact:true}));
 expect(screen.queryByRole('article',{name:'Current accepted Direction'})).toBeNull();
 expect(e.calls('read_project_direction')).toHaveLength(1);
 fireEvent.click(screen.getByRole('button',{name:'Direction',exact:true}));
 expect(screen.getByRole('article',{name:'Current accepted Direction'})).toBeTruthy();
 expect(e.calls('read_project_direction')).toHaveLength(1);
 await e.open();expect(screen.queryByRole('article',{name:'Current accepted Direction'})).toBeNull();
 expect(e.calls('read_project_direction')).toHaveLength(1);read();await screen.findByRole('article',{name:'Current accepted Direction'});
 expect(e.calls('read_project_direction')).toHaveLength(2);
 expect(e.invoke.mock.calls.filter(([name])=>/submit|prepare|pause|resume|consume|send|mission|current_window/.test(name))).toHaveLength(0);
});
it('withholds late canonical Direction after actual Workspace auth withdrawal',async()=>{
 const e=await setup({hold:true});read();await waitFor(()=>expect(e.calls('read_project_direction')).toHaveLength(1));
 act(()=>e.notify('mastermind-auth-state',{status:'signed_out',reason:null,acquisition:false,content:false}));
 await act(async()=>e.finish(source.direction));
 expect(document.body.textContent).not.toContain(source.direction.direction.current.answer);
});
it('withholds late canonical Direction after selected source catalogue refresh',async()=>{
 const e=await setup({hold:true});read();await waitFor(()=>expect(e.calls('read_project_direction')).toHaveLength(1));
 fireEvent.click(screen.getByRole('button',{name:'Refresh Projects'}));await act(async()=>e.finish(source.direction));
 expect(screen.queryByRole('article',{name:'Current accepted Direction'})).toBeNull();
});
it('refuses the actual foreign-project owner response without showing accepted content',async()=>{
 const e=await setup({foreign:true});read();await screen.findByText('Direction could not be read. Read again to retry.');
 expect(screen.queryByRole('article',{name:'Current accepted Direction'})).toBeNull();
 expect(document.body.textContent).not.toContain(source.direction.direction.current.answer);
 expect(e.calls('read_project_direction')).toHaveLength(1);
});
it('withholds a pending canonical Direction when its actual Host is replaced',async()=>{
 const e=await setup({hold:true});read();await waitFor(()=>expect(e.calls('read_project_direction')).toHaveLength(1));
 window.MastermindMissionHost={...e.host};fireEvent.click(screen.getByRole('button',{name:'Today'}));
 await act(async()=>e.finish(source.direction));expect(document.body.textContent).not.toContain(source.direction.direction.current.answer);
});
