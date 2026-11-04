// @vitest-environment jsdom
import {act,cleanup,renderHook} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {IDBFactory} from 'fake-indexeddb';
import fixture from '../fixtures/knowledge-write-owner.json';
import {createIndexedDbPendingPointerStore} from '../orchestration/indexeddb-pending-pointer-store';
import type {SourceOperationTransport} from '../source-operations/transport';
import {useProjectKnowledgeWorkspace,type ProjectKnowledgeWorkspaceProps} from './useProjectKnowledgeWorkspace';
import type {ProjectFileAddRequest} from './library/project-knowledge-requests';
afterEach(cleanup);
function setup() {
  const journey=fixture.journeys[0]!,request=journey.request as ProjectFileAddRequest;
  let current=true,published=false,source=true;
  const transport:SourceOperationTransport={prepareSourceOperation:vi.fn(async()=>journey.preview),
    submitSourceOperation:vi.fn(async()=>journey.proposal_status),
    readSourceOperation:vi.fn(async()=>published?journey.source_status:journey.proposal_status),
    reconcileSourceOperation:vi.fn(async()=>published?journey.source_status:journey.proposal_status),
    advanceSourceOperation:vi.fn(async()=>{throw Error('Unexpected advance');})};
  const store=createIndexedDbPendingPointerStore(new IDBFactory());
  const props:ProjectKnowledgeWorkspaceProps={workRef:request.work_ref,authGeneration:1,hostGeneration:1,
    canRead:()=>current,store,transport,onSourceObserved:vi.fn(),
    readContext:vi.fn(async selected=>{if(selected.action!==journey.context.selection.action)throw Error('Distinct permission unavailable');return journey.context;})};
  const snapshot={workRef:request.work_ref,sourceCommit:request.source_commit,baseRevision:request.base_revision};
  const owner={current:(value:typeof snapshot)=>{if(!source||JSON.stringify(value)!==JSON.stringify(snapshot))throw Error('SOURCE_CHANGED');return {...snapshot};}};
  const mounted=renderHook((value:ProjectKnowledgeWorkspaceProps)=>useProjectKnowledgeWorkspace(value),{initialProps:props});
  async function ready(){act(()=>mounted.result.current.registerSourceOwner(owner));
    await act(async()=>{await mounted.result.current.readActions({...snapshot,signal:new AbortController().signal});});}
  return {journey,request,props,transport,store,owner,snapshot,...mounted,ready,
    publish:()=>{published=true;},loseSource:()=>{source=false;},revoke:()=>{current=false;}};
}
it('does no mount I/O; preparation leaves IndexedDB empty until explicit publication',async()=>{
  const f=setup();expect(f.props.readContext).not.toHaveBeenCalled();expect(f.transport.prepareSourceOperation).not.toHaveBeenCalled();
  await f.ready();await act(async()=>{await f.result.current.prepare(f.request);});
  expect(f.result.current.phase).toBe('prepared');expect(await f.store.read(f.journey.context.owner_context.principal_scope)).toBeNull();
  expect(f.transport.submitSourceOperation).not.toHaveBeenCalled();
  await act(async()=>{await f.result.current.publish();});
  expect(f.result.current.phase).toBe('proposal-published');expect(f.transport.submitSourceOperation).toHaveBeenCalledTimes(1);
  expect(await f.store.read(f.journey.context.owner_context.principal_scope)).toMatchObject({operationKey:f.request.request_id,kind:'project_source_write'});
});
it('failed preparation keeps the original empty store and never claims publication UNKNOWN',async()=>{
  const f=setup();await f.ready();vi.mocked(f.transport.prepareSourceOperation).mockRejectedValue(Error('private failure'));
  await act(async()=>{await f.result.current.prepare(f.request);});
  expect(f.result.current.phase).toBe('prepare-unavailable');expect(f.result.current.prepared).toBeNull();
  expect(await f.store.read(f.journey.context.owner_context.principal_scope)).toBeNull();expect(f.transport.submitSourceOperation).not.toHaveBeenCalled();
});
it('same-coordinate Library replacement cannot reuse an old prepared witness',async()=>{
  const f=setup();await f.ready();await act(async()=>{await f.result.current.prepare(f.request);});
  act(()=>f.result.current.registerSourceOwner({...f.owner}));
  await act(async()=>{await f.result.current.publish();});
  expect(f.transport.submitSourceOperation).not.toHaveBeenCalled();expect(await f.store.read(f.journey.context.owner_context.principal_scope)).toBeNull();
});
it('withdraws the exact durable store immediately and recovers its original after restoration and source loss',async()=>{
  const f=setup();await f.ready();await act(async()=>{await f.result.current.prepare(f.request);await f.result.current.publish();});
  const pointer=await f.store.read(f.journey.context.owner_context.principal_scope);expect(pointer).not.toBeNull();
  f.rerender({...f.props,store:undefined});expect(f.result.current.controller).toBeUndefined();
  await act(async()=>{await f.result.current.checkOriginal();});expect(f.transport.reconcileSourceOperation).not.toHaveBeenCalled();
  f.loseSource();f.publish();f.rerender(f.props);
  await act(async()=>{await f.result.current.checkOriginal();});
  expect(f.transport.prepareSourceOperation).toHaveBeenCalledTimes(1);expect(f.transport.submitSourceOperation).toHaveBeenCalledTimes(1);
  expect(f.transport.reconcileSourceOperation).toHaveBeenCalledTimes(1);expect(f.result.current.phase).toBe('source-published');
  expect(f.props.onSourceObserved).toHaveBeenCalledTimes(1);expect(await f.store.read(f.journey.context.owner_context.principal_scope)).toBeNull();
});
it('stale handlers cannot prepare, submit or reconcile after unnotified owner withdrawal',async()=>{
  const f=setup();await f.ready();await act(async()=>{await f.result.current.prepare(f.request);});f.revoke();
  await act(async()=>{await f.result.current.publish();await f.result.current.checkOriginal();});
  expect(f.transport.submitSourceOperation).not.toHaveBeenCalled();expect(f.transport.reconcileSourceOperation).not.toHaveBeenCalled();
  expect(await f.store.read(f.journey.context.owner_context.principal_scope)).toBeNull();
});

it('a new signed context ticket retires a prepared witness without changing source coordinates',async()=>{
  const f=setup();await f.ready();await act(async()=>{await f.result.current.prepare(f.request);});
  await act(async()=>{await f.result.current.readActions({...f.snapshot,signal:new AbortController().signal});});
  await act(async()=>{await f.result.current.publish();});
  expect(f.transport.submitSourceOperation).not.toHaveBeenCalled();
  expect(await f.store.read(f.journey.context.owner_context.principal_scope)).toBeNull();
});

it('withdraws a detached publication callback when the actual host generation changes',async()=>{
  const f=setup();await f.ready();await act(async()=>{await f.result.current.prepare(f.request);});
  const oldPublish=f.result.current.publish;
  f.rerender({...f.props,hostGeneration:2});await f.ready();
  await act(async()=>{await f.result.current.prepare(f.request);});
  await act(async()=>{await oldPublish();});expect(f.transport.submitSourceOperation).not.toHaveBeenCalled();
  await act(async()=>{await f.result.current.publish();});expect(f.transport.submitSourceOperation).toHaveBeenCalledTimes(1);
});

it('preserves another pending kind and does not compile or publish a replacement',async()=>{
  const f=setup();await f.ready();const original={kind:'project_pause' as const,targetKey:'WS:ALPHA',operationKey:'mmos-project-pause-'+'a'.repeat(40)};
  const scope=f.journey.context.owner_context.principal_scope;await f.store.reserve(scope,original);
  await act(async()=>{await f.result.current.prepare(f.request);});
  expect(f.result.current.phase).toBe('publication-held');expect(await f.store.read(scope)).toEqual(original);
  expect(f.transport.prepareSourceOperation).not.toHaveBeenCalled();expect(f.transport.submitSourceOperation).not.toHaveBeenCalled();
});
