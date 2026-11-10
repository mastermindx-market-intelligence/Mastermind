// @vitest-environment jsdom
// @vitest-environment-options {"url":"https://mcp.mastermind-x.com/os/"}
/** Actual App/NativeClient/composeMissionHost/production IDB store. Only the
 * native invoke/auth boundary is inert. C and N bodies come from ONE genuine
 * canonical publication/Runtime/installed-child run; no row or root is made. */
import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {IDBFactory} from 'fake-indexeddb';
import {App} from './App';
import {createNativeClient} from './host';
import {composeMissionHost} from './compose-mission-host';
import {decodeLaunchBindingConfig} from './launch-config';
import actual from './fixtures/project-discovery-app-source.json';
const workRef=actual.programs.canonical_projects[0].work_ref;
const rootJobId=actual.mission.mission.root_job_id!;
const executiveScope='c'.repeat(64); // Synthetic Executive owner; never the Workspace source scope.
let dispose=()=>{};
afterEach(()=>{cleanup();dispose();delete window.MastermindMissionHost;history.replaceState(null,'','/os/');vi.restoreAllMocks();});
function deferred(){let resolve!:(value:unknown)=>void;const promise=new Promise(value=>{resolve=value;});return{promise,resolve};}
async function setup(){
 history.replaceState(null,'','/os/');delete window.MastermindMissionHost;
 const listeners=new Map<string,Set<(event:{payload:unknown})=>void>>();
 const state={stage:'C' as 'C'|'N',hold:null as ReturnType<typeof deferred>|null};
 const signed={status:'signed_in',reason:null,acquisition:true,content:true};
 const invoke=vi.fn(async(command:string,args?:Record<string,unknown>):Promise<unknown>=>{
  if(command==='auth_status')return signed;
  if(command==='executive_auth_status')return{generation:1,available:true};
  if(command==='executive_context')return{schema:'mastermind.os.executive.owner_context.v1',principal_scope:executiveScope,
   verified_expiry:Math.floor(Date.now()/1000)+600,profile:{name:'web_ceo_v3',server_version:'1.5.0'}};
  if(command==='read_programs'){
   if(state.hold)return state.hold.promise;
   if(state.stage==='N')return structuredClone(actual.programs);
   return structuredClone(actual.programs_before);
  }
  if(command==='read_mission_v3')return structuredClone(actual.mission);
  if(command==='read_project_plan')return structuredClone(actual.selected_plan);
  throw Error('unavailable inert READ; effects are not supplied');
 });
 const client=await createNativeClient(invoke as never,async(name,listener)=>{
  const set=listeners.get(name)??new Set();set.add(listener);listeners.set(name,set);return()=>set.delete(listener);
 });
 const config=decodeLaunchBindingConfig(JSON.stringify({v:1,workstream:'WS:EXECUTIVE-ECOSYSTEM-COMPLETION',priority:0,attemptLimit:1,
  projects:[{ref:'executive-infrastructure',label:'Infrastructure'}],profiles:[{ref:'research_only',label:'Research'}]}))!;
 const composed=composeMissionHost(client,config,new IDBFactory(),'native');await composed.ready;
 window.MastermindMissionHost=composed.host;
 const view=render(<App/>);dispose=()=>{view.unmount();composed.dispose();};
 const calls=(command:string)=>invoke.mock.calls.filter(([name])=>name===command);
 return{state,client,host:composed.host,view,calls,invoke,notify:(name:string,payload:unknown)=>{for(const listener of listeners.get(name)??[])listener({payload});}};
}
function newCard(){const browser=document.querySelector('.project-archive-browser');return browser?within(browser as HTMLElement).queryByText(workRef)?.closest('tr')??null:null;}
async function projects(){fireEvent.click(screen.getByRole('button',{name:'Projects'}));await screen.findByText(actual.programs.control_room.work[0].work_ref);}

describe('new canonical N project in the real mounted App',()=>{
 it('explicitly reloads C→N, opens the actual root, shows Project details, and returns to the same new row',async()=>{
  const e=await setup();await projects();expect(newCard()).toBeNull();
  e.state.stage='N';fireEvent.click(screen.getByRole('button',{name:'Refresh Projects'}));
  await waitFor(()=>expect(newCard()).not.toBeNull());
  fireEvent.click(within(newCard() as HTMLElement).getByRole('button',{name:/Open project/}));
  await waitFor(()=>expect(e.calls('read_mission_v3')).toHaveLength(1));
  expect(e.calls('read_mission_v3')[0][1]).toEqual({selection:{work_ref:workRef,root_job_id:rootJobId}});
  expect(new URLSearchParams(location.search).get('work_ref')).toBe(workRef);
  expect(new URLSearchParams(location.search).get('root_job_id')).toBe(rootJobId);
  const details=await screen.findByRole('button',{name:'Project details'});fireEvent.click(details);
  const panel=await screen.findByRole('region',{name:'Project details'});
  fireEvent.click(within(panel).getByRole('button',{name:'Plan'}));
  const planOwner=within(screen.getByRole('region',{name:'Inspect Plan'}));
  const objective=await planOwner.findByText((_text,node)=>node?.classList.contains('mm-project-plan__objective')===true && node.textContent===actual.selected_plan.plan.objective);
  expect(objective.textContent).toBe(actual.selected_plan.plan.objective);
  expect(e.calls('read_project_plan').at(-1)?.[1]).toEqual({selection:{work_ref:workRef}});
  fireEvent.click(screen.getByRole('button',{name:'Projects'}));await waitFor(()=>expect(newCard()).not.toBeNull());
  expect(await e.host.commandBinding!.store.read(executiveScope)).toBeNull();
  expect(e.invoke.mock.calls.filter(([name])=>/submit|source_operation_prepare|source_operation_reconcile|executive_fresh_conversation/.test(name))).toHaveLength(0);
 });
 it('does not publish a valid late N list after native auth withdrawal',async()=>{
  const e=await setup();await projects();e.state.hold=deferred();
  fireEvent.click(screen.getByRole('button',{name:'Refresh Projects'}));
  await act(async()=>{e.notify('mastermind-auth-state',{status:'signed_out',reason:null,acquisition:false,content:false});});
  await act(async()=>{e.state.hold!.resolve(actual.programs);});
  expect(newCard()).toBeNull();expect(e.calls('read_mission_v3')).toHaveLength(0);
 });
 it('refuses a visible N row after actual Host replacement without a notification',async()=>{
  const e=await setup();await projects();e.state.stage='N';fireEvent.click(screen.getByRole('button',{name:'Refresh Projects'}));
  await waitFor(()=>expect(newCard()).not.toBeNull());
  const detached=within(newCard() as HTMLElement).getByRole('button',{name:/Open project/});
  window.MastermindMissionHost={...e.host};
  fireEvent.click(detached);
  expect(e.calls('read_mission_v3')).toHaveLength(0);
  expect(new URLSearchParams(location.search).get('work_ref')).toBeNull();
 });
 it('withholds a changed-source N response instead of selecting its otherwise genuine root',async()=>{
  const e=await setup();await projects();e.state.hold=deferred();
  fireEvent.click(screen.getByRole('button',{name:'Refresh Projects'}));
  const changed=structuredClone(actual.programs);
  changed.canonical_projects[0].source_observation.project_data.data_observation.canonical_data_commit='f'.repeat(40);
  await act(async()=>{e.state.hold!.resolve(changed);});
  await waitFor(()=>expect(screen.getByRole('button',{name:'Refresh Projects'}).getAttribute('disabled')).toBeNull());
  expect(newCard()).toBeNull();expect(e.calls('read_mission_v3')).toHaveLength(0);
 });
 it('offers the acquired N project in New conversation without inventing a saved-conversation locator or creating anything',async()=>{
  const e=await setup();await projects();e.state.stage='N';fireEvent.click(screen.getByRole('button',{name:'Refresh Projects'}));
  await waitFor(()=>expect(newCard()).not.toBeNull());
  fireEvent.click(within(document.querySelector('#workspace-navigation') as HTMLElement).getByRole('button',{name:'New conversation'}));
  const chooser=await screen.findByRole('combobox',{name:'Project'});
  await waitFor(()=>expect((chooser as HTMLSelectElement).disabled).toBe(false));
  expect(within(chooser).getAllByRole('option').some(row=>(row as HTMLOptionElement).value===workRef)).toBe(true);
  fireEvent.change(chooser,{target:{value:workRef}});
  expect(chooser).toHaveProperty('value',workRef);
  expect(e.calls('executive_fresh_conversation')).toHaveLength(0);
  expect(await e.host.commandBinding!.store.read(executiveScope)).toBeNull();
 });

});
