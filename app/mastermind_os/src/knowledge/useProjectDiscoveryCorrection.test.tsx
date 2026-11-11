// @vitest-environment jsdom
import {act,cleanup,renderHook,waitFor} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {IDBFactory} from 'fake-indexeddb';
import fixture from '../fixtures/discovery-correction-owner.json';
import fileFixture from '../fixtures/knowledge-write-owner.json';
import {createIndexedDbPendingPointerStore} from '../orchestration/indexeddb-pending-pointer-store';
import {useProjectKnowledgeWorkspace,type ProjectKnowledgeWorkspaceProps} from './useProjectKnowledgeWorkspace';
import {validateDiscoveryCorrectionRequest,validateDiscoveryCorrectionLookup} from './library/project-discovery-correction';
import {validate_source,type ProjectDiscoverySource} from './library/knowledge-library-contract';
import type {SourceOperationTransport} from '../source-operations/transport';
afterEach(cleanup);
function setup(){
 const request=validateDiscoveryCorrectionRequest(fixture.request),lookup=validateDiscoveryCorrectionLookup(fixture.lookup);
 const body=validate_source(fixture.original_source,request.work_ref,fixture.original_source.selection.source_ref);
 const snapshot={workRef:request.work_ref,sourceCommit:request.source_commit,baseRevision:request.base_revision};
 const source:ProjectDiscoverySource=Object.freeze({workRef:request.work_ref,sourceRef:fixture.original_source.selection.source_ref,
  title:body.document!.title,mediaType:body.document!.mediaType,contentUtf8:body.document!.contentUtf8,
  contentSha256:body.document!.contentSha256,source:body.source!,sourceContext:snapshot,discoveryRef:request.discovery_ref});
 let current=true,sourceCurrent=true,correctionGranted=true,published=false;
 const transport:SourceOperationTransport={prepareSourceOperation:vi.fn(async()=>fixture.preview),
  submitSourceOperation:vi.fn(async()=>fixture.proposal_status),readSourceOperation:vi.fn(async()=>fixture.prepared_status),
  reconcileSourceOperation:vi.fn(async()=>published?fixture.source_status:fixture.proposal_status),
  advanceSourceOperation:vi.fn(async()=>{throw Error('Unexpected advance');})};
 const store=createIndexedDbPendingPointerStore(new IDBFactory());
 const props:ProjectKnowledgeWorkspaceProps={workRef:request.work_ref,authGeneration:1,hostGeneration:1,
  canRead:()=>current,store,transport,onSourceObserved:vi.fn(),readContext:vi.fn(async selected=>{
   if(selected.action==='correct_project_discovery'&&correctionGranted)return fixture.context;
   if(selected.action==='add_project_file')return {...fileFixture.journeys[0]!.context,owner_context:fixture.context.owner_context};
   throw Error('Distinct action not available');
  })};
 const owner={current:(value:typeof snapshot)=>{if(!sourceCurrent||JSON.stringify(value)!==JSON.stringify(snapshot))throw Error('SOURCE_CHANGED');return snapshot;},
  codeContext:()=>({schema:'mastermind.project_knowledge_code_context.v1' as const,work_ref:request.work_ref,
   executable_macro_commit:request.source_commit,reader_source_commit:'9'.repeat(40)}),
  discoveryCurrent:(value:ProjectDiscoverySource)=>sourceCurrent&&value===source};
 const mounted=renderHook((value:ProjectKnowledgeWorkspaceProps)=>useProjectKnowledgeWorkspace(value),{initialProps:props});
 return {request,lookup,source,snapshot,transport,store,props,owner,...mounted,
  ready:async()=>{act(()=>mounted.result.current.registerSourceOwner(owner));await act(async()=>{await mounted.result.current.readActions({...snapshot,signal:new AbortController().signal});});},
  revokeCorrection:()=>{correctionGranted=false;},loseSource:()=>{sourceCurrent=false;},publish:()=>{published=true;},revoke:()=>{current=false;}};
}
it('requires the actual issued full discovery object, then preserves original recovery after source loss',async()=>{
 const f=setup();await f.ready();
 await act(async()=>{await f.result.current.prepareCorrection(f.request,{...f.source});});
 expect(f.transport.prepareSourceOperation).not.toHaveBeenCalled();
 await act(async()=>{await f.result.current.prepareCorrection(f.request,f.source);});expect(f.result.current.phase).toBe('prepared');
 await act(async()=>{await f.result.current.publish();});expect(f.result.current.phase).toBe('proposal-published');
 f.loseSource();f.publish();await act(async()=>{await f.result.current.checkOriginal();});
 expect(f.result.current.phase).toBe('source-published');expect(f.props.onSourceObserved).toHaveBeenCalledTimes(1);
 expect(f.transport.submitSourceOperation).toHaveBeenCalledTimes(1);expect(f.transport.prepareSourceOperation).toHaveBeenCalledTimes(1);
});
it('drops a late prepare when its original opened discovery is withdrawn',async()=>{
 const f=setup();await f.ready();let release!:(value:unknown)=>void;
 vi.mocked(f.transport.prepareSourceOperation).mockImplementation(()=>new Promise(resolve=>{release=resolve;}));
 let pending!:Promise<void>;
 await act(async()=>{pending=f.result.current.prepareCorrection(f.request,f.source);});
 await waitFor(()=>expect(release).toBeTypeOf('function'));f.loseSource();
 await act(async()=>{release(fixture.preview);await pending;});
 expect(f.result.current.prepared).toBeNull();expect(f.transport.submitSourceOperation).not.toHaveBeenCalled();
 expect(await f.store.read(fixture.context.owner_context.principal_scope)).toBeNull();
});
it('inspects a lost prepare with exact eight-field identity and no source, pointer or preparation',async()=>{
 const f=setup();f.loseSource();
 await act(async()=>{expect((await f.result.current.inspectOriginal(f.lookup)).selection.request_id).toBe(f.request.request_id);});
 expect(f.transport.readSourceOperation).toHaveBeenCalledExactlyOnceWith(f.lookup,expect.any(AbortSignal));
 expect(f.transport.prepareSourceOperation).not.toHaveBeenCalled();expect(f.transport.submitSourceOperation).not.toHaveBeenCalled();
 expect(await f.store.read(fixture.context.owner_context.principal_scope)).toBeNull();
});
it('does not use remaining file access to accept a late correction inspection after its context ticket changes',async()=>{
 const f=setup();await f.ready();let release!:(value:unknown)=>void;
 vi.mocked(f.transport.readSourceOperation).mockImplementation(()=>new Promise(resolve=>{release=resolve;}));
 let pending!:Promise<unknown>;
 await act(async()=>{pending=f.result.current.inspectOriginal(f.lookup);});
 expect(release).toBeTypeOf('function');f.revokeCorrection();
 await act(async()=>{await f.result.current.readActions({...f.snapshot,signal:new AbortController().signal});});
 const refused=expect(pending).rejects.toThrow('SOURCE_CHANGED');
 await act(async()=>{release(fixture.prepared_status);await refused;});expect(f.result.current.status).toBeNull();
});
it('refuses a valid-looking inspection receipt whose predecessor belongs to another discovery',async()=>{
 const f=setup(),wrong=structuredClone(fixture.source_status);
 wrong.receipt.sources.find(value=>value.path==='agentos/discoveries/DSC-ORIGINAL-FINDING.md')!.path='agentos/discoveries/DSC-FOREIGN-FINDING.md';
 vi.mocked(f.transport.readSourceOperation).mockResolvedValue(wrong);
 await act(async()=>{await expect(f.result.current.inspectOriginal(f.lookup)).rejects.toThrow();});
 expect(f.result.current.status).toBeNull();expect(f.props.onSourceObserved).not.toHaveBeenCalled();
});
it('does not overwrite a different pending operation with a correction',async()=>{
 const f=setup();await f.ready();const original={kind:'project_pause' as const,targetKey:'WS:ALPHA',operationKey:'mmos-project-pause-'+'b'.repeat(40)};
 const scope=fixture.context.owner_context.principal_scope;await f.store.reserve(scope,original);
 await act(async()=>{await f.result.current.prepareCorrection(f.request,f.source);});
 expect(f.result.current.phase).toBe('publication-held');expect(await f.store.read(scope)).toEqual(original);
 expect(f.transport.prepareSourceOperation).not.toHaveBeenCalled();
});
