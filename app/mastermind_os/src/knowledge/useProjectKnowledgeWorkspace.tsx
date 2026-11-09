import {useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState} from 'react';
import {OperationController, type PendingPointerStore} from '../orchestration/operation-controller';
import type {SourceOperationTransport,KnowledgeSourceLookup} from '../source-operations/transport';
import type {SourceOperationContextSelection} from '../source-operations/context';
import {bindProjectKnowledgeCommandOwner, createProjectKnowledgeCommandPort,
  prepareProjectKnowledgeWrite, type PreparedProjectKnowledgeWrite} from './library/project-knowledge-port';
import type {ProjectKnowledgeRequest,ProjectDiscoveryCorrectionRequest,ProjectKnowledgeSourceContext} from './library/project-knowledge-requests';
import {decodeProjectSourceOperationStatus, type ProjectSourceAction, type ProjectSourceStatus} from './library/project-source-operation';
import type {KnowledgeLibrarySourceOwner,ProjectDiscoverySource} from './library/knowledge-library-contract';
import {sameKnowledgeCodeContext,type ProjectKnowledgeCodeContext} from './library/project-data-observation';
import type {KnowledgeEditPhase} from './library/ProjectKnowledgeEditor';
import {qualifyDiscoveryCorrectionSources} from './library/project-discovery-correction';

const actions = ['add_project_file','set_project_communication_preference','correct_project_discovery'] as const;
type Request = ProjectKnowledgeRequest;
export interface ProjectKnowledgeWorkspaceProps {
  workRef: string | null;
  authGeneration: number;
  hostGeneration: number | null;
  /** Rechecks the actual installed host, auth, methods and host generation. */
  canRead: () => boolean;
  readContext?: (request: SourceOperationContextSelection & {signal: AbortSignal}) => Promise<unknown>;
  transport?: SourceOperationTransport;
  /** Only the actual incumbent commandBinding.store. */
  store?: PendingPointerStore;
  onSourceObserved?: () => void;
}

/** App-lifetime Knowledge composition. There is no mount read, replacement
 * store, automatic mutation or automatic reconciliation. Preparation remains
 * unsaved local material until the explicit publication gesture reserves the
 * original v5 pointer. The Library owns the current CODE/DATA source witness. */
export function useProjectKnowledgeWorkspace(props: ProjectKnowledgeWorkspaceProps) {
  const identities = useRef({read:props.readContext, transport:props.transport, store:props.store, epoch:0});
  if (identities.current.read !== props.readContext || identities.current.transport !== props.transport || identities.current.store !== props.store)
    identities.current = {read:props.readContext, transport:props.transport, store:props.store, epoch:identities.current.epoch+1};
  const alive=useRef(true);
  const scope = JSON.stringify([props.workRef,props.authGeneration,props.hostGeneration,identities.current.epoch]);
  const live = useRef({props,scope}); live.current = {props,scope};
  const sourceOwner = useRef<{scope:string;value:KnowledgeLibrarySourceOwner}|null>(null);
  const contexts = useRef<{scope:string; values:Partial<Record<ProjectSourceAction,unknown>>}|null>(null);
  const prepared = useRef<{scope:string; value:PreparedProjectKnowledgeWrite;sourceOwner:KnowledgeLibrarySourceOwner;contextTicket:object;codeContext:ProjectKnowledgeCodeContext;discovery:ProjectDiscoverySource|null}|null>(null);
  const correctionSource=useRef<ProjectDiscoverySource|null>(null);
  const pendingPrepare = useRef<AbortController|null>(null);
  // A rendered Review gesture is single-use even after durable settlement.
  // This never replaces/clears the controller pointer or asserts an outcome.
  const usedReviewGestures=useRef(new WeakSet<PreparedProjectKnowledgeWrite>());
  const phaseRef = useRef<{scope:string;value:KnowledgeEditPhase}>({scope,value:'idle'});
  const [, repaint] = useState(0);
  const setPhase = (value:KnowledgeEditPhase) => {phaseRef.current={scope:live.current.scope,value};repaint(n=>n+1);};
  function current(started=scope) {
    const now=live.current;
    try {return alive.current && now.scope===started && now.props.workRef!==null && now.props.hostGeneration!==null && now.props.canRead()===true;}
    catch {return false;}
  }
  const codeContext = (snapshot:ProjectKnowledgeSourceContext) => {
    if (!current() || sourceOwner.current?.scope!==scope) return null;
    try {const value=sourceOwner.current.value.codeContext?.();return value?.work_ref===snapshot.workRef?value:null;}
    catch {return null;}
  };
  const sourceCurrent = (snapshot:ProjectKnowledgeSourceContext) => {
    if (!current() || snapshot.workRef!==live.current.props.workRef || sourceOwner.current?.scope!==scope || !codeContext(snapshot)) return false;
    try {const value=sourceOwner.current.value.current({workRef:snapshot.workRef,sourceCommit:snapshot.sourceCommit,baseRevision:snapshot.baseRevision});return value.workRef===snapshot.workRef && value.sourceCommit===snapshot.sourceCommit && value.baseRevision===snapshot.baseRevision;}
    catch {return false;}
  };
  function currentDiscovery(source:ProjectDiscoverySource) {
    try{return current()&&sourceOwner.current?.scope===scope&&sourceCurrent(source.sourceContext)
      &&sourceOwner.current.value.discoveryCurrent?.(source)===true;}catch{return false;}
  }
  function correctionMatches(request:Request,source:ProjectDiscoverySource|null) {
    return request.schema!=='mastermind.project_discovery_correct_request.v1'||!!source&&currentDiscovery(source)
      &&request.discovery_ref===source.discoveryRef&&request.expected_discovery_revision===source.contentSha256
      &&request.work_ref===source.workRef&&request.source_commit===source.source.commit
      &&request.base_revision===source.sourceContext.baseRevision;
  }
  function owner() {
    if (!current() || contexts.current?.scope!==scope || !props.workRef) return null;
    const ticket=contexts.current;
    try {return bindProjectKnowledgeCommandOwner({workRef:props.workRef,generation:scope,
      contexts:ticket.values,isCurrent:()=>current() && contexts.current===ticket,
      sourceIsCurrent:sourceCurrent,discoveryIsCurrent:request=>correctionMatches(request,correctionSource.current)});} catch {return null;}
  }
  const currentOwner = owner();
  const slot = useRef<{scope:string;store:PendingPointerStore;transport:SourceOperationTransport;controller:OperationController}|null>(null);
  if (props.workRef && props.store && props.transport &&
      (slot.current?.scope!==scope || slot.current.store!==props.store || slot.current.transport!==props.transport)) {
    const delegate = {
      context:()=>owner()?.context()??null,
      canInspect:(action:ProjectSourceAction)=>owner()?.canInspect(action)===true,
      canPrepare:(action:ProjectSourceAction,source:ProjectKnowledgeSourceContext)=>owner()?.canPrepare(action,source)===true,
      canCorrect:(request:ProjectDiscoveryCorrectionRequest)=>owner()?.canCorrect?.(request)===true,
    };
    const port=createProjectKnowledgeCommandPort({workRef:props.workRef,transport:props.transport,owner:delegate,
      prepared:()=>prepared.current?.scope===scope?prepared.current.value:null,
      isPreparedCurrent:anchor=>current() && prepared.current?.value===anchor && sourceOwner.current?.value===prepared.current.sourceOwner && contexts.current===prepared.current.contextTicket && sameKnowledgeCodeContext(prepared.current.codeContext,codeContext({workRef:anchor.request.work_ref,sourceCommit:anchor.request.source_commit,baseRevision:anchor.request.base_revision})??undefined) && sourceCurrent({workRef:anchor.request.work_ref,sourceCommit:anchor.request.source_commit,baseRevision:anchor.request.base_revision}) && prepared.current.discovery===correctionSource.current && correctionMatches(anchor.request,prepared.current.discovery),
      onStatus:status=>{
        if (!current()) return;
        lastStatus.current={scope,value:status};
        if (status.receipt?.kind==='SOURCE_OBSERVED' && status.disposition==='accepted') {
          setPhase('source-published');
          if (observed.current!==status.receipt.receipt_sha256) {
            observed.current=status.receipt.receipt_sha256;live.current.props.onSourceObserved?.();
          }
        } else if (status.disposition==='refused') setPhase('refused');
        else setPhase(status.receipt?.kind==='PROPOSAL_OBSERVED'?'proposal-published':'unknown');
      }});
    slot.current={scope,store:props.store,transport:props.transport,controller:new OperationController(port,props.store)};
  }
  const lastStatus=useRef<{scope:string;value:ProjectSourceStatus}|null>(null), observed=useRef<string|null>(null);
  const controller=props.store && props.transport && slot.current?.scope===scope && slot.current.store===props.store && slot.current.transport===props.transport?slot.current.controller:undefined;
  const committed=useRef({scope,controller});
  useLayoutEffect(()=>{
    if (committed.current.scope!==scope || committed.current.controller!==controller) {
      committed.current.controller?.invalidate(); pendingPrepare.current?.abort();
      prepared.current=null; contexts.current=null; correctionSource.current=null;
      committed.current={scope,controller}; repaint(n=>n+1);
    }
  },[scope,controller]);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;pendingPrepare.current?.abort();committed.current.controller?.invalidate();};},[]);
  const registerSourceOwner=useCallback((value:KnowledgeLibrarySourceOwner|null)=>{sourceOwner.current=value?{scope:live.current.scope,value}:null;},[]);

  async function readContexts(signal:AbortSignal) {
    const started=scope, read=props.readContext, workRef=props.workRef;
    if (!read || !workRef || !current() || signal.aborted) throw Error('PROJECT_KNOWLEDGE_UNAVAILABLE');
    const values:Partial<Record<ProjectSourceAction,unknown>>={};
    await Promise.all(actions.map(async action=>{
      try {const value=await read({action,workRef,signal});
        if (current(started) && !signal.aborted) values[action]=value;
      } catch { /* Missing distinct action context remains unavailable. */ }
    }));
    if (!current(started) || signal.aborted) throw Error('SOURCE_CHANGED');
    contexts.current={scope:started,values};
  }
  async function readActions(snapshot:ProjectKnowledgeSourceContext & {signal:AbortSignal}) {
    const started=scope, originalSource=sourceOwner.current;
    if (!current() || !sourceCurrent(snapshot)) throw Error('SOURCE_CHANGED');
    await readContexts(snapshot.signal);
    if (!current(started) || snapshot.signal.aborted || sourceOwner.current!==originalSource || !sourceCurrent(snapshot)) throw Error('SOURCE_CHANGED');
    const qualified=owner(); repaint(n=>n+1);
    return {schema:'mastermind.project_knowledge_actions.v2',selection:{work_ref:snapshot.workRef},
      source_commit:snapshot.sourceCommit,base_revision:snapshot.baseRevision,actions:{
        add_files:props.store && props.transport && qualified?.canInspect('add_project_file')?'AVAILABLE':'UNAVAILABLE',
        edit_preference:props.store && props.transport && qualified?.canInspect('set_project_communication_preference')?'AVAILABLE':'UNAVAILABLE',
        correct_discovery:props.store && props.transport && qualified?.canInspect('correct_project_discovery')?'AVAILABLE':'UNAVAILABLE'}};
  }
  function startDraft() {
    if (!current() || !controller || ["submitting","checking","unknown"].includes(controller.getState().status)) return false;
    pendingPrepare.current?.abort(); prepared.current=null;correctionSource.current=null;setPhase('idle');return true;
  }
  async function prepare(request:Request,discovery:ProjectDiscoverySource|null=null) {
    const selected=owner(), transport=props.transport, started=scope, originalSource=sourceOwner.current, originalContexts=contexts.current, originalCode=codeContext({workRef:request.work_ref,sourceCommit:request.source_commit,baseRevision:request.base_revision});
    if (!current()) return;
    if (!selected || !transport || !controller || !originalSource || !originalContexts || !originalCode) {setPhase('prepare-unavailable');return;}
    if (['submitting','checking','unknown'].includes(controller.getState().status)) return;
    prepared.current=null;pendingPrepare.current?.abort();correctionSource.current=null;
    if(!correctionMatches(request,discovery)){setPhase('prepare-unavailable');return;}
    correctionSource.current=discovery;
    const pending=new AbortController();pendingPrepare.current=pending;
    try {
      const principal=selected.context();if(!principal)throw Error('PROJECT_KNOWLEDGE_UNAVAILABLE');
      const original=await props.store!.read(principal.principalScope,pending.signal);
      if(pending.signal.aborted || !current(started) || contexts.current!==originalContexts || sourceOwner.current!==originalSource)return;
      if(original){setPhase('publication-held');return;}
      const value=await prepareProjectKnowledgeWrite({request,transport,owner:selected,isCurrent:()=>current(started) && sourceOwner.current===originalSource && contexts.current===originalContexts && correctionSource.current===discovery && correctionMatches(request,discovery) && sameKnowledgeCodeContext(originalCode,codeContext({workRef:request.work_ref,sourceCommit:request.source_commit,baseRevision:request.base_revision})??undefined)},pending.signal);
      if (pending.signal.aborted || !current(started) || sourceOwner.current!==originalSource) return;
      if(correctionSource.current!==discovery||!correctionMatches(request,discovery))return;
      prepared.current={scope:started,value,sourceOwner:originalSource.value,contextTicket:originalContexts,codeContext:originalCode,discovery};setPhase('prepared');
    } catch {if (!pending.signal.aborted && current(started)) setPhase('prepare-unavailable');}
  }
  function canPublish() {
    const anchor=prepared.current;
    return !!anchor && !usedReviewGestures.current.has(anchor.value) && anchor.scope===scope && current() && sourceOwner.current?.value===anchor.sourceOwner && contexts.current===anchor.contextTicket && anchor.discovery===correctionSource.current && correctionMatches(anchor.value.request,anchor.discovery) && sameKnowledgeCodeContext(anchor.codeContext,codeContext({workRef:anchor.value.request.work_ref,sourceCommit:anchor.value.request.source_commit,baseRevision:anchor.value.request.base_revision})??undefined) && sourceCurrent({workRef:anchor.value.request.work_ref,sourceCommit:anchor.value.request.source_commit,baseRevision:anchor.value.request.base_revision});
  }
  async function publish(expected:PreparedProjectKnowledgeWrite) {
    const anchor=prepared.current;
    if (!current() || !controller || anchor?.scope!==scope || anchor.value!==expected) return;
    if (usedReviewGestures.current.has(expected)) return;
    if (!canPublish()) {setPhase('stale');return;}
    usedReviewGestures.current.add(expected);
    setPhase('pending');
    const result=await controller.begin({kind:'project_source_write',targetKey:anchor.value.targetKey,
      payload:{action:anchor.value.target.action,request:anchor.value.request}});
    if (current() && phaseRef.current.value==='pending') setPhase(result.status==='unknown' && result.pointer.kind!=='project_source_write'?'publication-held':result.status==='refused'?'refused':result.status==='accepted'?'source-published':'unknown');
  }
  async function checkOriginal() {
    if (!current() || !controller) return;
    if (!owner()?.context()) {
      try {await readContexts(new AbortController().signal);} catch {return;}
    }
    if (!current() || !owner()?.context()) return;
    const result=await controller.recover({reconcileSource:true});
    if(current()){if(result.status==='unknown' && result.pointer.kind!=='project_source_write')setPhase('publication-held');else repaint(n=>n+1);}
  }
  // Read only the exact original safe lookup. A lost prepare does not own a
  // durable submit pointer yet; inspection never prepares, reserves or sends it.
  async function inspectOriginal(lookup:KnowledgeSourceLookup) {
    const started=scope, signal=new AbortController().signal;
    if (!current() || lookup.work_ref!==props.workRef || !['add_project_file','correct_project_discovery'].includes(lookup.action)) throw Error('SOURCE_CHANGED');
    await readContexts(signal);
    const ticket=contexts.current, selected=owner(), before=selected?.context(), transport=props.transport;
    if (!before || !transport || !selected?.canInspect(lookup.action)) throw Error('PROJECT_KNOWLEDGE_UNAVAILABLE');
    const value=decodeProjectSourceOperationStatus(await transport.readSourceOperation(lookup,signal),{
      action:lookup.action,workRef:lookup.work_ref,requestId:lookup.request_id,
      requestSha256:lookup.request_sha256,principalScope:before.principalScope});
    const after=owner()?.context();
    if (!current(started) || contexts.current!==ticket || !selected.canInspect(lookup.action)
      || !after || after.principalScope!==before.principalScope || after.generation!==before.generation) throw Error('SOURCE_CHANGED');
    if(lookup.action==='correct_project_discovery'&&value.receipt?.kind==='SOURCE_OBSERVED')
      qualifyDiscoveryCorrectionSources(lookup,before.principalScope,value.receipt.sources);
    lastStatus.current={scope:started,value};repaint(n=>n+1);
    return value;
  }
  const renderedPrepared=prepared.current?.scope===scope?prepared.current.value:null;
  const methods=useRef({readActions,prepare,publish,checkOriginal,startDraft,inspectOriginal,currentDiscovery,
    currentSource:(snapshot:ProjectKnowledgeSourceContext)=>{if(!sourceCurrent(snapshot))throw Error('SOURCE_CHANGED');return {...snapshot};}});
  methods.current={readActions,prepare,publish,checkOriginal,startDraft,inspectOriginal,currentDiscovery,
    currentSource:(snapshot:ProjectKnowledgeSourceContext)=>{if(!sourceCurrent(snapshot))throw Error('SOURCE_CHANGED');return {...snapshot};}};
  // The editor captures callback identity at open. Locale, phase and unrelated
  // source updates must not replace those callbacks or discard the typed draft.
  const stable=useMemo(()=>({
    readActions:(...args:Parameters<typeof readActions>)=>live.current.scope===scope?methods.current.readActions(...args):Promise.reject(Error('SOURCE_CHANGED')),
    startDraft:()=>live.current.scope===scope && methods.current.startDraft(),
    inspectOriginal:(lookup:KnowledgeSourceLookup)=>live.current.scope===scope?methods.current.inspectOriginal(lookup):Promise.reject(Error('SOURCE_CHANGED')),
    prepare:(request:Request)=>live.current.scope===scope?methods.current.prepare(request):Promise.resolve(),
    prepareCorrection:(request:ProjectDiscoveryCorrectionRequest,source:ProjectDiscoverySource)=>live.current.scope===scope?methods.current.prepare(request,source):Promise.resolve(),
    currentDiscovery:(source:ProjectDiscoverySource)=>live.current.scope===scope&&methods.current.currentDiscovery(source),
    checkOriginal:()=>live.current.scope===scope?methods.current.checkOriginal():Promise.resolve(),
    currentSource:(snapshot:ProjectKnowledgeSourceContext)=>{if(live.current.scope!==scope)throw Error('SOURCE_CHANGED');return methods.current.currentSource(snapshot);},
  }),[scope]);
  // Bind the destructive gesture to the exact Review rendered to the user.
  // A callback retained from A can never submit a later prepared original B.
  const publishRendered=useMemo(()=>()=>live.current.scope===scope && renderedPrepared
    ? methods.current.publish(renderedPrepared):Promise.resolve(),[scope,renderedPrepared]);
  return {scope,registerSourceOwner,...stable,publish:publishRendered,canPublish:canPublish(),
    phase:phaseRef.current.scope===scope?phaseRef.current.value:'idle' as KnowledgeEditPhase,
    prepared:prepared.current?.scope===scope?prepared.current.value:null,
    status:lastStatus.current?.scope===scope?lastStatus.current.value:null,
    controller:currentOwner?controller:undefined};
}
