// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { bindMissionHost, createNativeClient } from './host';
import { programsFromControlRoom } from './mission';
import { RetainedRootChoice, type RetainedRootChoiceProps } from './RetainedRootChoice';
import { canonicalJson, sha256Hex } from './orchestration/operation-key';
import actual from './fixtures/project-execution-resource-owner.json';

afterEach(cleanup);
const signed={status:'signed_in',reason:null,acquisition:true,content:true};
const selected={workRef:actual.selection.work_ref,rootJobId:actual.selection.root_job_id};
const clone=()=>structuredClone(actual) as any;

/** The native invocation edge is inert. Both existing NativeClient/MissionHost
 * adapters and the actual Python-produced response/decoder path run unchanged. */
async function source(reply:()=>Promise<unknown>=async()=>structuredClone(actual.mission)) {
  const calls:Array<{command:string;args:unknown}>=[];
  const listeners=new Map<string,(event:{payload:unknown})=>void>();
  const invoke=async<T,>(command:string,args?:Record<string,unknown>):Promise<T>=>{
    calls.push({command,args});
    if(command==='auth_status'||command==='executive_auth_status')return structuredClone(signed) as T;
    if(command==='read_programs')return structuredClone(actual.programs) as T;
    if(command==='read_mission_v3')return await reply() as T;
    throw Error('unexpected native effect: '+command);
  };
  const client=await createNativeClient(invoke,async(name,listener)=>{listeners.set(name,listener);return()=>listeners.delete(name);});
  const host=bindMissionHost(client);
  const readCard=async()=>{
    const observation=await host.readProgramsObservation!({signal:new AbortController().signal});
    const projection=programsFromControlRoom(observation.programsInput);
    expect(projection.state).toBe('AVAILABLE');
    return projection.programs.find(card=>card.workRef===selected.workRef)!;
  };
  const card=await readCard(),generation=host.invalidationGeneration!();
  return {client,host,card,calls,readCard,generation,
    notify:(payload:unknown)=>listeners.get('mastermind-auth-state')!({payload}),
    current:()=>host.invalidationGeneration!()===generation,
  };
}
type Source=Awaited<ReturnType<typeof source>>;
function props(f:Source,overrides:Partial<RetainedRootChoiceProps>={}):RetainedRootChoiceProps {
  return {workRef:f.card.workRef,rootCandidates:f.card.rootCandidates,rootState:f.card.rootState,
    selectedRootJobId:selected.rootJobId,locale:'en',onChooseRoot:vi.fn(),rootHistory:f.card.rootHistory,
    resourceInspection:{read:f.host.readProjectExecutionResource!,generation:f.generation,current:f.current},...overrides};
}
function deferred(){let resolve!:(value:unknown)=>void;const promise=new Promise<unknown>(done=>{resolve=done;});return {promise,resolve};}
function resourceCalls(f:Source){return f.calls.filter(call=>call.command==='read_mission_v3');}

describe('reached Programs history → explicit resource inspection',()=>{
  it('renders original roles, waits for both explicit choices, and reads only the fixed original pair',async()=>{
    const f=await source(),choose=vi.fn(),base=props(f,{selectedRootJobId:null,onChooseRoot:choose});
    const view=render(<RetainedRootChoice {...base}/>);
    expect(screen.getByText('Planning · Queued')).toBeTruthy();
    expect(screen.getByText('Execution · Queued')).toBeTruthy();
    expect(resourceCalls(f)).toHaveLength(0);
    fireEvent.click(screen.getByRole('button',{name:selected.rootJobId}));
    expect(choose).toHaveBeenCalledWith(selected);expect(resourceCalls(f)).toHaveLength(0);
    view.rerender(<RetainedRootChoice {...base} selectedRootJobId={selected.rootJobId}/>);
    const button=screen.getByRole('button',{name:'Inspect execution'});button.focus();expect(document.activeElement).toBe(button);
    fireEvent.click(button);fireEvent.click(button);
    const section=screen.getByRole('region',{name:'Execution details'});
    await within(section).findByText('Durable');
    expect(within(section).getByText('Queued')).toBeTruthy();
    expect(within(section).getByText('The original work input is unavailable in this read.')).toBeTruthy();
    expect(within(section).getByText('The currently adopted plan has not been read.')).toBeTruthy();
    expect(resourceCalls(f)).toEqual([{command:'read_mission_v3',args:{selection:actual.selection}}]);
    expect(f.calls.every(call=>['auth_status','executive_auth_status','read_programs','read_mission_v3'].includes(call.command))).toBe(true);
    expect(choose).toHaveBeenCalledTimes(1);
  });
  it('preserves legacy omission and shows unavailable when the typed port is absent',async()=>{
    const f=await source();
    const view=render(<RetainedRootChoice {...props(f,{rootHistory:undefined,resourceInspection:undefined})}/>);
    expect(screen.queryByRole('region',{name:'Execution details'})).toBeNull();
    expect(resourceCalls(f)).toHaveLength(0);
    view.rerender(<RetainedRootChoice {...props(f,{resourceInspection:undefined})}/>);
    expect(screen.getByText('Execution details are unavailable from this connection.')).toBeTruthy();
    expect(screen.queryByRole('button',{name:'Inspect execution'})).toBeNull();
    expect(resourceCalls(f)).toHaveLength(0);
  });
  it.each(['missing','foreign-root','unproved-authority','changed-owner'])('withholds %s response from the rendered consumer',async fault=>{
    const value=clone().mission,owner=value.source.owner_observation;
    if(fault==='missing')delete owner.resource;
    if(fault==='foreign-root')owner.resource.selection.root_job_id='JOB-999';
    if(fault==='unproved-authority')owner.resource.execution_authorized=true;
    if(fault==='changed-owner')owner.control_room.publication_after++;
    const f=await source(async()=>value);render(<RetainedRootChoice {...props(f)}/>);
    fireEvent.click(screen.getByRole('button',{name:'Inspect execution'}));
    await screen.findByText('Execution details are unavailable from this connection.');
    expect(screen.queryByText('Durable')).toBeNull();expect(resourceCalls(f)).toHaveLength(1);
  });
  it.each(['membership','original-event','execution-context'])('requires Programs refresh when original %s changes',async fault=>{
    const value=clone().mission,r=value.source.owner_observation.resource,h=r.history;
    if(fault==='membership'){const row=structuredClone(h.roots[0]);row.root_job_id='JOB-003';h.roots.push(row);}
    if(fault==='original-event')h.roots[1].creation_event_sha256='e'.repeat(64);
    if(fault==='execution-context'){h.roots[1].execution.context_sha256='e'.repeat(64);r.original_execution.context_sha256='e'.repeat(64);}
    h.observation.snapshot_digest=sha256Hex(canonicalJson({work_ref:h.work_ref,roots:h.roots}));
    const f=await source(async()=>value);render(<RetainedRootChoice {...props(f)}/>);
    fireEvent.click(screen.getByRole('button',{name:'Inspect execution'}));
    await screen.findByText('The project history or connection changed. Refresh Programs before inspecting this execution.');
    expect(screen.queryByText('Durable')).toBeNull();expect(resourceCalls(f)).toHaveLength(1);
  });
  it('allows independently observed progress without relabeling the Programs history',async()=>{
    const value=clone().mission,h=value.source.owner_observation.resource.history;
    h.roots[1].status='RUNNING';h.observation.before=h.observation.after=20;
    h.observation.source_identity='later-observation';
    h.observation.snapshot_digest=sha256Hex(canonicalJson({work_ref:h.work_ref,roots:h.roots}));
    value.mission.status='RUNNING';value.execution.state='IN_PROGRESS';
    const f=await source(async()=>value);render(<RetainedRootChoice {...props(f)}/>);
    fireEvent.click(screen.getByRole('button',{name:'Inspect execution'}));
    await within(screen.getByRole('region',{name:'Execution details'})).findByText('Running');
    expect(screen.getByText('Execution · Queued')).toBeTruthy();
    expect(screen.getByText('Status comes from this execution read; the project history observation is retained separately.')).toBeTruthy();
  });
  it('clears and aborts an identical-candidate Programs refresh and a root A-B-A change',async()=>{
    const pending=deferred(),f=await source(()=>pending.promise),read=vi.fn(f.host.readProjectExecutionResource!);
    const base=props(f,{resourceInspection:{read,generation:1,current:f.current}});
    const view=render(<RetainedRootChoice {...base}/>);
    fireEvent.click(screen.getByRole('button',{name:'Inspect execution'}));
    const signal=read.mock.calls[0][0].signal;
    const fresh=await f.readCard();
    view.rerender(<RetainedRootChoice {...base} rootHistory={fresh.rootHistory} selectedRootJobId="JOB-001"/>);
    expect(signal.aborted).toBe(true);
    view.rerender(<RetainedRootChoice {...base} rootHistory={fresh.rootHistory}/>);
    await act(async()=>{pending.resolve(actual.mission);await pending.promise;});
    expect(screen.queryByText('Durable')).toBeNull();expect(resourceCalls(f)).toHaveLength(1);
    expect(screen.getByRole('button',{name:'Inspect execution'})).toBeTruthy();
  });
  it('aborts an old host read and does not fetch automatically from its replacement',async()=>{
    const pending=deferred(),old=await source(()=>pending.promise),next=await source();
    const read=vi.fn(old.host.readProjectExecutionResource!);
    const view=render(<RetainedRootChoice {...props(old,{resourceInspection:{read,generation:1,current:old.current}})}/>);
    fireEvent.click(screen.getByRole('button',{name:'Inspect execution'}));
    view.rerender(<RetainedRootChoice {...props(next,{resourceInspection:{read:next.host.readProjectExecutionResource!,generation:2,current:next.current}})}/>);
    expect(read.mock.calls[0][0].signal.aborted).toBe(true);
    await act(async()=>{pending.resolve(actual.mission);await pending.promise;});
    expect(screen.queryByText('Durable')).toBeNull();expect(resourceCalls(next)).toHaveLength(0);
  });
  it('withholds a read after source currentness is lost',async()=>{
    let available=true;const pending=deferred(),f=await source(()=>pending.promise);
    render(<RetainedRootChoice {...props(f,{resourceInspection:{read:f.host.readProjectExecutionResource!,generation:1,current:()=>available}})}/>);
    fireEvent.click(screen.getByRole('button',{name:'Inspect execution'}));available=false;
    await act(async()=>{pending.resolve(actual.mission);await pending.promise;});
    await screen.findByText('The project history or connection changed. Refresh Programs before inspecting this execution.');
    expect(screen.queryByText('Durable')).toBeNull();expect(resourceCalls(f)).toHaveLength(1);
  });
  it('renders the supported Chinese scope and unavailable input without changing identifiers',async()=>{
    const f=await source();render(<RetainedRootChoice {...props(f,{locale:'zh-CN'})}/>);
    fireEvent.click(screen.getByRole('button',{name:'查看执行'}));
    await screen.findByText('持续执行');expect(screen.getByText('尚未读取当前采用的计划。')).toBeTruthy();
    expect(screen.getByRole('button',{name:selected.rootJobId})).toBeTruthy();
  });
});

describe('actual NativeClient/MissionHost resource owner boundaries',()=>{
  it('refuses pre-dispatch when the captured original reader is replaced',async()=>{
    const f=await source(),replacement=vi.fn(async()=>actual.mission);
    f.client.readMissionV3=replacement;
    await expect(f.host.readProjectExecutionResource!({...selected,signal:new AbortController().signal})).rejects.toThrow('READ_CANCELLED');
    expect(replacement).not.toHaveBeenCalled();expect(resourceCalls(f)).toHaveLength(0);
  });
  it.each(['revoked','A-B-A','same-public-state'])('joins original native cancellation after %s auth change without another read',async change=>{
    const pending=deferred(),f=await source(()=>pending.promise);
    const operation=f.host.readProjectExecutionResource!({...selected,signal:new AbortController().signal});
    const refusal=expect(operation).rejects.toThrow('READ_CANCELLED');
    f.notify(change==='same-public-state'?signed:{...signed,status:'signed_out',acquisition:false,content:false});
    if(change==='A-B-A')f.notify(signed);
    await refusal;pending.resolve(actual.mission);await pending.promise;
    expect(resourceCalls(f)).toHaveLength(1);
  });
  it('refuses replacement generation owner after the original transport returns',async()=>{
    const pending=deferred(),f=await source(()=>pending.promise);
    const operation=f.host.readProjectExecutionResource!({...selected,signal:new AbortController().signal});
    const original=f.client.invalidationGeneration!;f.client.invalidationGeneration=()=>original();
    pending.resolve(actual.mission);
    await expect(operation).rejects.toThrow('READ_CANCELLED');expect(resourceCalls(f)).toHaveLength(1);
  });
  it('does not expose the resource port without the original client generation owner',async()=>{
    const f=await source();delete f.client.invalidationGeneration;
    expect(bindMissionHost(f.client).readProjectExecutionResource).toBeUndefined();
    expect(resourceCalls(f)).toHaveLength(0);
  });
});
