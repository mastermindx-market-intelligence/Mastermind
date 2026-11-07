// @vitest-environment jsdom
import {act,cleanup,renderHook} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {IDBFactory} from 'fake-indexeddb';
import fixture from '../fixtures/knowledge-write-owner.json';
import {createIndexedDbPendingPointerStore} from '../orchestration/indexeddb-pending-pointer-store';
import type {SourceOperationTransport} from '../source-operations/transport';
import {useProjectKnowledgeWorkspace,type ProjectKnowledgeWorkspaceProps} from './useProjectKnowledgeWorkspace';
import {publicRequestSha256,type ProjectFileAddRequest} from './library/project-knowledge-requests';
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
  const owner={codeContext:()=>source?({schema:'mastermind.project_knowledge_code_context.v1' as const,work_ref:request.work_ref,executable_macro_commit:request.source_commit,reader_source_commit:'07e317ef5b6e0107fcfca9228f179c7d269bb234'}):null,current:(value:typeof snapshot)=>{if(!source||JSON.stringify(value)!==JSON.stringify(snapshot))throw Error('SOURCE_CHANGED');return {...snapshot};}};
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
  const f=setup();await f.ready();await act(async()=>{await f.result.current.prepare(f.request);});await act(async()=>{await f.result.current.publish();});
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

it('binds a retained same-scope Review callback to A and only the rendered B callback may submit B',async()=>{
  const f=setup();await f.ready();await act(async()=>{await f.result.current.prepare(f.request);});
  const oldPublish=f.result.current.publish;act(()=>{expect(f.result.current.startDraft()).toBe(true);});
  const replacement=structuredClone(f.request);replacement.request_id='mmos-project-file-add-'+'b'.repeat(40);
  const next=structuredClone(f.journey.preview);next.selection.request_id=replacement.request_id;
  next.request_sha256=await publicRequestSha256(replacement);
  vi.mocked(f.transport.prepareSourceOperation).mockResolvedValue(next);
  const nextStatus=structuredClone(f.journey.proposal_status);nextStatus.selection.request_id=replacement.request_id;nextStatus.request_sha256=next.request_sha256;
  vi.mocked(f.transport.submitSourceOperation).mockResolvedValue(nextStatus);
  await act(async()=>{await f.result.current.prepare(replacement);});
  expect(f.result.current.prepared?.request.request_id).toBe(replacement.request_id);
  await act(async()=>{await oldPublish();});expect(f.transport.submitSourceOperation).not.toHaveBeenCalled();
  expect(await f.store.read(f.journey.context.owner_context.principal_scope)).toBeNull();
  await act(async()=>{await f.result.current.publish();});
  expect(f.transport.submitSourceOperation).toHaveBeenCalledTimes(1);
  expect(vi.mocked(f.transport.submitSourceOperation).mock.calls[0]![0]).toMatchObject({request_id:replacement.request_id});
});

it('legacy Library bodies remain read-only without an independent CODE owner',async()=>{
  const f=setup();act(()=>f.result.current.registerSourceOwner({current:f.owner.current}));
  await expect(f.result.current.readActions({...f.snapshot,signal:new AbortController().signal})).rejects.toThrow('SOURCE_CHANGED');
  await act(async()=>{await f.result.current.prepare(f.request);});
  expect(f.transport.prepareSourceOperation).not.toHaveBeenCalled();expect(f.transport.submitSourceOperation).not.toHaveBeenCalled();
  expect(await f.store.read(f.journey.context.owner_context.principal_scope)).toBeNull();
});

it('consumes the rendered publication gesture once even when an immediate terminal receipt clears its pointer',async()=>{
  const f=setup();await f.ready();vi.mocked(f.transport.submitSourceOperation).mockResolvedValue(f.journey.source_status);
  await act(async()=>{await f.result.current.prepare(f.request);});const retained=f.result.current.publish;
  await act(async()=>{await retained();});expect(f.result.current.phase).toBe('source-published');
  expect(await f.store.read(f.journey.context.owner_context.principal_scope)).toBeNull();
  await act(async()=>{await retained();});expect(f.transport.submitSourceOperation).toHaveBeenCalledTimes(1);
});

it('retires retained original-status callbacks on unmount without erasing the durable pointer',async()=>{
  const f=setup();await f.ready();await act(async()=>{await f.result.current.prepare(f.request);});
  await act(async()=>{await f.result.current.publish();});const check=f.result.current.checkOriginal;
  const scope=f.journey.context.owner_context.principal_scope,original=await f.store.read(scope);f.unmount();
  await check();expect(f.transport.reconcileSourceOperation).not.toHaveBeenCalled();expect(await f.store.read(scope)).toEqual(original);
});

it('inspects the exact lost-prepare original without source, prepare, reserve, submit or replay',async()=>{
 const f=setup();
 const request=f.request,lookup={action:'add_project_file' as const,request_id:request.request_id,work_ref:request.work_ref,source_commit:request.source_commit,base_revision:request.base_revision,request_sha256:await publicRequestSha256(request),expected_preference_revision:null};
 await act(async()=>{const status=await f.result.current.inspectOriginal(lookup);expect(status.selection.request_id).toBe(request.request_id);});
 expect(f.transport.readSourceOperation).toHaveBeenCalledExactlyOnceWith(lookup,expect.any(AbortSignal));
 expect(f.transport.prepareSourceOperation).not.toHaveBeenCalled();expect(f.transport.submitSourceOperation).not.toHaveBeenCalled();
 expect(await f.store.read(f.journey.context.owner_context.principal_scope)).toBeNull();
 f.revoke();await expect(f.result.current.inspectOriginal(lookup)).rejects.toThrow();
 expect(f.transport.readSourceOperation).toHaveBeenCalledTimes(1);
});
