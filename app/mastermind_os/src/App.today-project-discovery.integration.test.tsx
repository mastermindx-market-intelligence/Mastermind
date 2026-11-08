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
function todayRow(){const region=screen.queryByRole('region',{name:'Your projects',exact:true});return region?within(region).queryByText((_text,node)=>node?.classList.contains('today-faint')===true && node.textContent?.startsWith(workRef)===true)?.closest('li')??null:null;}
async function acquiredToday(){const e=await setup();await projects();e.state.stage='N';fireEvent.click(screen.getByRole('button',{name:'Refresh Projects'}));await waitFor(()=>expect(newCard()).not.toBeNull());fireEvent.click(screen.getByRole('button',{name:'Today',exact:true}));await waitFor(()=>expect(todayRow()).not.toBeNull());return e;}
function newCard(){const browser=document.querySelector('.project-archive-browser');return browser?within(browser as HTMLElement).queryByText(workRef)?.closest('li')??null:null;}
async function projects(){fireEvent.click(screen.getByRole('button',{name:'Projects'}));await screen.findByText(actual.programs.control_room.work[0].work_ref);}

describe('Today uses the same qualified current project catalogue',()=>{
 it('shows the genuinely acquired new-N project after an explicit catalogue reload',async()=>{
  const e=await setup();await projects();expect(newCard()).toBeNull();
  e.state.stage='N';fireEvent.click(screen.getByRole('button',{name:'Refresh Projects'}));
  await waitFor(()=>expect(newCard()).not.toBeNull());
  const readsAtReload=e.calls('read_programs').length;
  fireEvent.click(screen.getByRole('button',{name:'Today',exact:true}));
  expect(e.calls('read_programs')).toHaveLength(readsAtReload);
  const today=await screen.findByRole('region',{name:'Your projects',exact:true});
  const row=within(today).queryByText((_text,node)=>node?.classList.contains('today-faint')===true && node.textContent?.startsWith(workRef)===true);
  expect(row).not.toBeNull();
  expect(within(row!.closest('li')!).getByRole('button',{name:/Open project/})).toBeTruthy();
  const readsBefore=e.calls('read_programs').length;
  fireEvent.click(within(row!.closest('li')!).getByRole('button',{name:/Open project/}));
  await waitFor(()=>expect(e.calls('read_mission_v3')).toHaveLength(1));
  expect(e.calls('read_mission_v3')[0][1]).toEqual({selection:{work_ref:workRef,root_job_id:rootJobId}});
  fireEvent.click(await screen.findByRole('button',{name:'Project details'}));
  const panel=await screen.findByRole('region',{name:'Project details'});
  fireEvent.click(within(panel).getByRole('button',{name:'Plan',exact:true}));
  const planOwner=within(screen.getByRole('region',{name:'Inspect Plan',exact:true}));
  expect((await planOwner.findByText((_text,node)=>node?.classList.contains('mm-project-plan__objective')===true && node.textContent===actual.selected_plan.plan.objective)).textContent).toBe(actual.selected_plan.plan.objective);
  fireEvent.click(screen.getByRole('button',{name:'Today',exact:true}));
  await waitFor(()=>expect(todayRow()).not.toBeNull());
  expect(e.calls('read_programs').length).toBeGreaterThanOrEqual(readsBefore);
  expect(await e.host.commandBinding!.store.read(executiveScope)).toBeNull();
  expect(e.invoke.mock.calls.filter(([name])=>/submit|source_operation_prepare|source_operation_reconcile|executive_fresh_conversation/.test(name))).toHaveLength(0);
 });
 it('opens the genuine rootless configured project as catalogue details without creating a Mission',async()=>{
  const e=await setup();await projects();
  const configuredWork=actual.programs_before.control_room.work[0].work_ref;
  fireEvent.click(screen.getByRole('button',{name:'Today',exact:true}));
  const region=await screen.findByRole('region',{name:'Your projects'});
  const row=within(region).getByText((_text,node)=>node?.classList.contains('today-faint')===true && node.textContent?.startsWith(configuredWork)===true).closest('li')!;
  fireEvent.click(within(row).getByRole('button',{name:/Open project/}));
  expect(e.calls('read_mission_v3')).toHaveLength(0);
  expect(new URLSearchParams(location.search).get('root_job_id')).toBeNull();
  fireEvent.click(await screen.findByRole('button',{name:'Project details'}));
  expect(await screen.findByRole('region',{name:'Project details'})).toBeTruthy();
  expect(await e.host.commandBinding!.store.read(executiveScope)).toBeNull();
 });
 it('refuses the acquired Today action after Host replacement without notification',async()=>{
  const e=await acquiredToday();const button=within(todayRow()!).getByRole('button',{name:/Open project/});
  window.MastermindMissionHost={...e.host};fireEvent.click(button);
  expect(e.calls('read_mission_v3')).toHaveLength(0);
  expect(new URLSearchParams(location.search).get('root_job_id')).toBeNull();
 });
 it('withdraws Today rows after actual auth withdrawal and refuses the detached action',async()=>{
  const e=await acquiredToday();const button=within(todayRow()!).getByRole('button',{name:/Open project/});
  await act(async()=>e.notify('mastermind-auth-state',{status:'signed_out',reason:null,acquisition:false,content:false}));
  fireEvent.click(button);expect(todayRow()).toBeNull();expect(e.calls('read_mission_v3')).toHaveLength(0);
 });
 it('withholds a late valid N catalogue after auth withdrawal rather than falling back to Office C',async()=>{
  const e=await setup();await projects();e.state.hold=deferred();fireEvent.click(screen.getByRole('button',{name:'Refresh Projects'}));
  await act(async()=>e.notify('mastermind-auth-state',{status:'signed_out',reason:null,acquisition:false,content:false}));
  await act(async()=>e.state.hold!.resolve(actual.programs));
  expect(todayRow()).toBeNull();expect(e.calls('read_mission_v3')).toHaveLength(0);
 });
 it('withholds a changed-source catalogue from Today instead of using its genuine root',async()=>{
  const e=await setup();await projects();e.state.hold=deferred();fireEvent.click(screen.getByRole('button',{name:'Refresh Projects'}));
  const changed=structuredClone(actual.programs);changed.canonical_projects[0].source_observation.project_data.data_observation.canonical_data_commit='f'.repeat(40);
  await act(async()=>e.state.hold!.resolve(changed));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Refresh Projects'}).hasAttribute('disabled')).toBe(false));
  fireEvent.click(screen.getByRole('button',{name:'Today',exact:true}));expect(todayRow()).toBeNull();expect(e.calls('read_mission_v3')).toHaveLength(0);
 });
});
