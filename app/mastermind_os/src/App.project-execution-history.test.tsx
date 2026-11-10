// @vitest-environment jsdom
// Actual App, NativeClient, host decoders and Company views; only the native
// transport edge is inert. No installed execution or authenticated grant is claimed.
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { App } from './App';
import { bindMissionHost, createNativeClient } from './host';
import { controlRoomFixture } from './test-fixtures';
import { canonicalJson, sha256Hex } from './orchestration/operation-key';
import actual from './fixtures/project-execution-resource-owner.json';
import companyFixture from '../../../tests/fixtures/paperclip_connections.json';

const signed = {status:'signed_in',reason:null,acquisition:true,content:true};
const pair = {workRef:actual.selection.work_ref,rootJobId:actual.selection.root_job_id};
const digest = (value: unknown) => sha256Hex(canonicalJson(value));
beforeEach(() => {
  history.replaceState(null, '', '/os/');
  delete (window as any).__TAURI_INTERNALS__;
  delete window.MastermindMissionHost;
});
afterEach(() => {cleanup(); vi.restoreAllMocks(); delete window.MastermindMissionHost;});

// Explicit synthetic singleton variant of the original Python-produced read.
// All closed-wire digests are recomputed; it proves routing, not a new owner receipt.
function singleton(kind: 'execution' | 'planning') {
  const programs: any = structuredClone(actual.programs);
  const p = programs.canonical_projects[0], doc = p.control_room;
  const root = kind === 'execution' ? pair.rootJobId : 'JOB-001';
  Object.assign(doc.autonomy.responsibilities[0], {
    root_job_id:root,root_job_candidates:[root],root_job_ambiguous:false,runtime_root_state:'RESOLVED',
  });
  doc.work[0].executive.jobs = doc.work[0].executive.jobs.filter((row:any)=>row.job_id===root);
  p.source_validity.cards[0].root_job_id = root;
  p.source_observation.project_data.document_digest = digest(doc);
  p.source_observation.project_data.source_validity_digest = digest(p.source_validity);
  if (kind === 'execution') {
    p.root_history.roots = p.root_history.roots.filter((row:any)=>row.root_job_id===root);
    p.root_history.observation.snapshot_digest = digest({work_ref:p.work_ref,roots:p.root_history.roots});
  } else {
    programs.schema = 'mastermind.workspace_programs.v2';
    delete p.root_history;
  }
  return programs;
}
function deferred() {
  let resolve!: (value:unknown)=>void;
  const promise = new Promise<unknown>(done=>{resolve=done;});
  return {promise,resolve};
}
async function setup(initial:unknown=actual.programs) {
  const calls:Array<{command:string;args:unknown}>=[];
  const listeners=new Map<string,(event:{payload:unknown})=>void>();
  const reads={programs:async():Promise<unknown>=>structuredClone(initial),
    mission:async():Promise<unknown>=>structuredClone(actual.mission)};
  const company:any=structuredClone(companyFixture);
  company.projectBindings[0].workRef=pair.workRef;
  const invoke=async<T,>(command:string,args?:Record<string,unknown>):Promise<T>=>{
    calls.push({command,args});
    if(command==='auth_status'||command==='executive_auth_status')return structuredClone(signed) as T;
    if(command==='read_programs')return await reads.programs() as T;
    if(command==='read_mission_v3')return await reads.mission() as T;
    if(command==='read_company_workspace')return structuredClone(company) as T;
    throw Error('inert transport: '+command);
  };
  const client=await createNativeClient(invoke,async(name,listener)=>{
    listeners.set(name,listener);return()=>listeners.delete(name);
  });
  const bound=bindMissionHost(client);
  const generic=vi.fn(bound.readMissionV3!);
  const resource=vi.fn(bound.readProjectExecutionResource!);
  const host={...bound,readMissionV3:generic,readProjectExecutionResource:resource};
  window.MastermindMissionHost=host;
  return {calls,reads,company,host,generic,resource,
    notify:(payload:unknown)=>listeners.get('mastermind-auth-state')!({payload})};
}
function route(){return document.querySelector('.shell')?.getAttribute('data-active-route');}
function companyNav(){return within(document.getElementById('workspace-navigation')!).getByRole('navigation',{name:'Company navigation'});}
async function programs(user:ReturnType<typeof userEvent.setup>){
  await user.click(screen.getByRole('button',{name:'Programs workspace'}));
  await screen.findByRole('region',{name:'Choose work and review history'});
}
async function choose(user:ReturnType<typeof userEvent.setup>,root=pair.rootJobId){
  await user.click(within(screen.getByRole('region',{name:'Choose work and review history'})).getByRole('button',{name:root}));
}
function noCommand(calls:Array<{command:string}>){
  expect(calls.filter(({command})=>/^(launch|dispatch|create|submit|consume|ack|open_control|bind_control)/.test(command))).toEqual([]);
}

it('reaches original execution details from actual Programs without replacing Mission selection',async()=>{
  const f=await setup(),user=userEvent.setup();render(<App/>);await programs(user);
  const locationBefore=location.search;
  expect(screen.getByText('Planning · Queued')).toBeTruthy();
  expect(screen.getByText('Execution · Queued')).toBeTruthy();
  await choose(user);expect(f.resource).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button',{name:'Inspect execution'}));
  await within(screen.getByRole('region',{name:'Execution details'})).findByText('Durable');
  expect(f.resource).toHaveBeenCalledTimes(1);expect(f.resource.mock.calls[0][0]).toMatchObject(pair);
  expect(location.search).toBe(locationBefore);expect(f.generic).not.toHaveBeenCalled();noCommand(f.calls);
});

it('cancels a root A-B-A read without restoring its old details or entering Mission',async()=>{
  const f=await setup(),pending=deferred(),user=userEvent.setup();f.reads.mission=()=>pending.promise;
  render(<App/>);await programs(user);await choose(user);
  await user.click(screen.getByRole('button',{name:'Inspect execution'}));
  await waitFor(()=>expect(f.resource).toHaveBeenCalledTimes(1));
  const signal=f.resource.mock.calls[0][0].signal;
  await choose(user,'JOB-001');expect(signal.aborted).toBe(true);await choose(user);
  await act(async()=>{pending.resolve(actual.mission);await pending.promise;});
  expect(screen.queryByText('Durable')).toBeNull();expect(f.resource).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('button',{name:'Inspect execution'})).toBeTruthy();expect(f.generic).not.toHaveBeenCalled();
});

it('clears and aborts the resource on an identical-candidate Programs refresh',async()=>{
  const f=await setup(),pending=deferred(),user=userEvent.setup();f.reads.mission=()=>pending.promise;
  render(<App/>);await programs(user);await choose(user);
  await user.click(screen.getByRole('button',{name:'Inspect execution'}));
  await waitFor(()=>expect(f.resource).toHaveBeenCalledTimes(1));
  const signal=f.resource.mock.calls[0][0].signal;
  await user.click(screen.getByRole('button',{name:'Refresh Projects'}));
  await waitFor(()=>expect(signal.aborted).toBe(true));
  await act(async()=>{pending.resolve(actual.mission);await pending.promise;});
  expect(screen.queryByRole('region',{name:'Execution details'})).toBeNull();
  expect(f.resource).toHaveBeenCalledTimes(1);expect(f.generic).not.toHaveBeenCalled();
});

it.each(['revoked','same-public-state'])('clears original resource ownership on %s auth invalidation',async kind=>{
  const f=await setup(),pending=deferred(),user=userEvent.setup();f.reads.mission=()=>pending.promise;
  render(<App/>);await programs(user);await choose(user);
  await user.click(screen.getByRole('button',{name:'Inspect execution'}));
  await waitFor(()=>expect(f.resource).toHaveBeenCalledTimes(1));
  const signal=f.resource.mock.calls[0][0].signal;
  act(()=>f.notify(kind==='revoked'?{status:'signed_out',reason:null,acquisition:false,content:false}:signed));
  await waitFor(()=>expect(signal.aborted).toBe(true));
  await act(async()=>{pending.resolve(actual.mission);await pending.promise;});
  expect(screen.queryByText('Durable')).toBeNull();expect(f.resource).toHaveBeenCalledTimes(1);expect(f.generic).not.toHaveBeenCalled();
});

it('opens a sole original execution from Programs through the same read-only choice',async()=>{
  const f=await setup(singleton('execution')),user=userEvent.setup();render(<App/>);await programs(user);
  const locationBefore=location.search;
  await user.click(screen.getByRole('button',{name:/Mastermind OS delivery.*Execution JOB-002/}));
  expect(route()).toBe('Programs');expect(screen.getByRole('button',{name:'Inspect execution'})).toBeTruthy();
  expect(f.resource).not.toHaveBeenCalled();expect(f.generic).not.toHaveBeenCalled();expect(location.search).toBe(locationBefore);
});

it('opens the actual Team project connection into sole-execution history',async()=>{
  const f=await setup(singleton('execution')),user=userEvent.setup();render(<App/>);
  await user.click(within(companyNav()).getByRole('button',{name:'Team'}));
  const company=await screen.findByRole('region',{name:'Always-on company'});
  const open=await within(company).findByRole('button',{name:'Open project'});
  await user.click(open);
  await waitFor(()=>expect(route()).toBe('Programs'));
  expect(screen.getByRole('button',{name:'Inspect execution'})).toBeTruthy();
  expect(location.search).toBe('');expect(f.generic).not.toHaveBeenCalled();noCommand(f.calls);
});

it('keeps original planning Mission navigation from the Team project connection',async()=>{
  // Navigation/call proof only: the inert execution reply is deliberately not
  // a successful planning Mission. Existing legacy host positives run separately.
  const f=await setup(singleton('planning')),user=userEvent.setup();render(<App/>);
  await user.click(within(companyNav()).getByRole('button',{name:'Team'}));
  await user.click(await within(await screen.findByRole('region',{name:'Always-on company'})).findByRole('button',{name:'Open project'}));
  await waitFor(()=>expect(route()).toBe('Projects'));
  expect(new URLSearchParams(location.search).get('root_job_id')).toBe('JOB-001');
  await waitFor(()=>expect(f.generic).toHaveBeenCalled());
  expect(f.resource).not.toHaveBeenCalled();noCommand(f.calls);
});

it('retains Paperclip context when its linked project is outside the current catalogue',async()=>{
  const f=await setup(singleton('execution')),user=userEvent.setup();f.company.projectBindings[0].workRef='WS:OTHER-PROJECT';
  render(<App/>);await user.click(within(companyNav()).getByRole('button',{name:'Team'}));
  await user.click(await within(await screen.findByRole('region',{name:'Always-on company'})).findByRole('button',{name:'Open project'}));
  expect(route()).toBe('Team');expect(await screen.findByText(/original OS project is not in the current permitted catalogue/)).toBeTruthy();
  expect(location.search).toBe('');expect(f.resource).not.toHaveBeenCalled();expect(f.generic).not.toHaveBeenCalled();noCommand(f.calls);
});

it('preserves retained-history selection on the supported readPrograms-only host',async()=>{
  const room:any=controlRoomFixture(),work=room.work[0].work_ref;
  Object.assign(room.autonomy.responsibilities[0],{responsibility_ref:work,
    root_job_id:null,root_job_candidates:['JOB-001','JOB-002'],root_job_ambiguous:true,runtime_root_state:'CONFLICT'});
  const generic=vi.fn(async()=>{throw Error('no Mission read is expected');});
  const signedIn={status:'signed_in' as const,reason:null,acquisition:true,content:false};
  window.MastermindMissionHost={readPrograms:async()=>room,readMissionV3:generic,invalidationGeneration:()=>1,
    auth:{getState:()=>signedIn,subscribe:()=>()=>{},signIn:async()=>{},signOut:async()=>{}}};
  const user=userEvent.setup();render(<App/>);await programs(user);await choose(user,'JOB-001');
  expect(within(screen.getByRole('region',{name:'Choose work and review history'}))
    .getByRole('button',{name:'JOB-001'}).getAttribute('aria-pressed')).toBe('true');
  expect(screen.queryByRole('region',{name:'Execution details'})).toBeNull();
  expect(location.search).toBe('');expect(generic).not.toHaveBeenCalled();
});

it('keeps an existing Mission selection while inspecting independent execution history',async()=>{
  history.replaceState(null,'','/os/?work_ref=WS%3AOTHER-PROJECT&root_job_id=JOB-999');
  const f=await setup(),user=userEvent.setup();render(<App/>);await programs(user);
  const locationBefore=location.search,genericReads=f.generic.mock.calls.length;
  await choose(user);await user.click(screen.getByRole('button',{name:'Inspect execution'}));
  await within(screen.getByRole('region',{name:'Execution details'})).findByText('Durable');
  expect(location.search).toBe(locationBefore);expect(f.generic).toHaveBeenCalledTimes(genericReads);
  expect(f.resource).toHaveBeenCalledTimes(1);noCommand(f.calls);
});
