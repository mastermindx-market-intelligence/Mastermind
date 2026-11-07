/** Original prepared Knowledge commands over the incumbent finite controller.
 * Server preparation precedes Review and durable controller reservation. Status
 * needs only the stored v5 safe tuple, current owner and actual fixed transport;
 * it never opens a private body, reads current Macro, prepares or submits again.
 */
import type {CommandIntent,EffectReceipt,FiniteCommandPort,OperationPointer,OwnerContext} from '../../orchestration/operation-controller';
import {parseProjectSourceWriteTarget,serializeProjectSourceWriteTarget,projectSourceWriteKeyMatches,type ProjectSourceWriteTarget} from '../../orchestration/project-source-write-target';
import type {SourceOperationTransport,KnowledgeSourceLookup} from '../../source-operations/transport';
import {canonicalPublicRequest,publicRequestSha256,type ProjectKnowledgeRequest,type ProjectKnowledgeSourceContext} from './project-knowledge-requests';
import {qualifyDiscoveryCorrectionSources,type ProjectDiscoveryCorrectionRequest} from './project-discovery-correction';
import {decodeProjectSourceOperationContext,decodeProjectSourceOperationStatus,type ProjectSourceAction,type ProjectSourceStatus} from './project-source-operation';
import {decodeProjectKnowledgePreview} from './project-knowledge-preview';

type Request=ProjectKnowledgeRequest;
type Preview=NonNullable<ReturnType<typeof decodeProjectKnowledgePreview>>;
export interface ProjectKnowledgeCommandOwner {
 context():OwnerContext|null;
 canInspect(action:ProjectSourceAction):boolean;
 canPrepare(action:ProjectSourceAction,source:ProjectKnowledgeSourceContext):boolean;
 canCorrect?(request:ProjectDiscoveryCorrectionRequest):boolean;
}
export interface PreparedProjectKnowledgeWrite {
 readonly request:Request;
 readonly ownerContext:OwnerContext;
 readonly response:Preview;
 readonly target:ProjectSourceWriteTarget;
 readonly targetKey:string;
}
const issued=new WeakSet<object>();
const actions=['add_project_file','set_project_communication_preference','correct_project_discovery'] as const;
function fail():never {throw new Error('PROJECT_KNOWLEDGE_OPERATION_UNAVAILABLE');}
const permits=(read:()=>boolean)=>{try{return read()===true;}catch{return false;}};
const actionOf=(request:Request):ProjectSourceAction=>request.schema==='mastermind.project_file_add_request.v1'?'add_project_file':request.schema==='mastermind.project_discovery_correct_request.v1'?'correct_project_discovery':'set_project_communication_preference';
const sourceOf=(request:Request)=>({workRef:request.work_ref,sourceCommit:request.source_commit,baseRevision:request.base_revision});
const canPrepareRequest=(owner:ProjectKnowledgeCommandOwner,request:Request)=>permits(()=>owner.canPrepare(actionOf(request),sourceOf(request)))
 &&(request.schema!=='mastermind.project_discovery_correct_request.v1'||permits(()=>owner.canCorrect?.(request)===true));
/** Inputs must be actual signed fixed context responses. Shape is not a grant;
 * isCurrent must retain actual host/auth/method identity for each response. */
export function bindProjectKnowledgeCommandOwner(input:{workRef:string;generation:string;
 contexts:Partial<Record<ProjectSourceAction,unknown>>;isCurrent:(action:ProjectSourceAction)=>boolean;
 sourceIsCurrent:(source:ProjectKnowledgeSourceContext)=>boolean;
 discoveryIsCurrent?:(request:ProjectDiscoveryCorrectionRequest)=>boolean;}):ProjectKnowledgeCommandOwner {
 const contexts=new Map<ProjectSourceAction,ReturnType<typeof decodeProjectSourceOperationContext>>();
 for(const action of actions){
  const raw=input.contexts[action];if(raw===undefined)continue;
  const context=decodeProjectSourceOperationContext(raw,{action,workRef:input.workRef});
  if(context.selection.action!==action||context.selection.work_ref!==input.workRef)fail();
  contexts.set(action,context);
 }
 const scopes=new Set([...contexts.values()].map(value=>value.owner_context.principal_scope));
 if(scopes.size!==1||!input.generation||input.generation.length>512)fail();
 const principalScope=[...scopes][0]!;
 const current=(action:ProjectSourceAction)=>contexts.has(action)&&permits(()=>input.isCurrent(action));
 return Object.freeze({
  context:()=>actions.some(current)?{principalScope,generation:input.generation}:null,
  canInspect:current,
  canPrepare:(action:ProjectSourceAction,source:ProjectKnowledgeSourceContext)=>current(action)&&source.workRef===input.workRef&&permits(()=>input.sourceIsCurrent(source)),
  canCorrect:(request:ProjectDiscoveryCorrectionRequest)=>current('correct_project_discovery')&&request.work_ref===input.workRef&&permits(()=>input.discoveryIsCurrent?.(request)===true),
 });
}
function context(owner:ProjectKnowledgeCommandOwner,action:ProjectSourceAction,signal?:AbortSignal):OwnerContext {
 if(signal?.aborted||!permits(()=>owner.canInspect(action)))fail();
 const value=owner.context();
 if(!value||value.principalScope.length!==64||!/^[0-9a-f]{64}$/.test(value.principalScope)||!value.generation)fail();
 return Object.freeze({principalScope:value.principalScope,generation:value.generation});
}
function fence(owner:ProjectKnowledgeCommandOwner,action:ProjectSourceAction,before:OwnerContext,signal?:AbortSignal){
 const now=context(owner,action,signal);
 if(now.principalScope!==before.principalScope||now.generation!==before.generation)fail();
}
/** Actual prepare only; no pointer reservation, publication or request-ID mint. */
export async function prepareProjectKnowledgeWrite(input:{request:Request;transport:SourceOperationTransport;
 owner:ProjectKnowledgeCommandOwner;isCurrent:()=>boolean},signal:AbortSignal):Promise<PreparedProjectKnowledgeWrite>{
 const request=JSON.parse(canonicalPublicRequest(input.request)) as Request,action=actionOf(request);
 const before=context(input.owner,action,signal);
 if(!permits(input.isCurrent)||!canPrepareRequest(input.owner,request))fail();
 const requestSha=await publicRequestSha256(request);
 fence(input.owner,action,before,signal);
 if(!permits(input.isCurrent))fail();
 const raw=await input.transport.prepareSourceOperation({action,request},signal);
 fence(input.owner,action,before,signal);
 if(!permits(input.isCurrent)||!canPrepareRequest(input.owner,request))fail();
 const response=decodeProjectKnowledgePreview(raw,request,requestSha);
 if(!response||response.owner_context.principal_scope!==before.principalScope||response.recipe_fingerprint_sha256===requestSha)fail();
 const common={work_ref:request.work_ref,source_commit:request.source_commit,base_revision:request.base_revision,request_sha256:requestSha};
 const target:ProjectSourceWriteTarget=Object.freeze(request.schema==='mastermind.project_discovery_correct_request.v1'
  ?{...common,action:'correct_project_discovery',discovery_ref:request.discovery_ref,expected_discovery_revision:request.expected_discovery_revision}
  :{...common,action:request.schema==='mastermind.project_file_add_request.v1'?'add_project_file':'set_project_communication_preference',
    expected_preference_revision:'expected_preference_revision' in request?request.expected_preference_revision:null});
 const targetKey=serializeProjectSourceWriteTarget(target);if(!targetKey)fail();
 const prepared=Object.freeze({request:deepFreeze(request),ownerContext:before,response,target,targetKey});
 issued.add(prepared);return prepared;
}
function deepFreeze<T>(value:T):T {if(value&&typeof value==='object'){Object.values(value).forEach(deepFreeze);Object.freeze(value);}return value;}
export function createProjectKnowledgeCommandPort(input:{workRef:string;transport:SourceOperationTransport;
 owner:ProjectKnowledgeCommandOwner;prepared:()=>PreparedProjectKnowledgeWrite|null;
 isPreparedCurrent:(prepared:PreparedProjectKnowledgeWrite)=>boolean;
 onStatus?:(status:ProjectSourceStatus)=>void;}):FiniteCommandPort {
 function lookup(pointer:OperationPointer):KnowledgeSourceLookup {
  const target=pointer.targetKey?parseProjectSourceWriteTarget(pointer.targetKey):null;
  if(pointer.kind!=='project_source_write'||!target||target.work_ref!==input.workRef||!projectSourceWriteKeyMatches(pointer.operationKey,target))fail();
  return {...target,request_id:pointer.operationKey};
 }
 function preparedFor(intent:CommandIntent):PreparedProjectKnowledgeWrite {
  const prepared=input.prepared();
  if(!prepared||!issued.has(prepared)||!permits(()=>input.isPreparedCurrent(prepared))||
   intent.kind!=='project_source_write'||intent.targetKey!==prepared.targetKey)fail();
  const proto=Object.getPrototypeOf(intent.payload);if(proto!==Object.prototype&&proto!==null)fail();
  const descriptors=Object.getOwnPropertyDescriptors(intent.payload);
  if(Reflect.ownKeys(descriptors).length!==2||!descriptors.action||!descriptors.request||
    !descriptors.action.enumerable||!descriptors.request.enumerable||!('value' in descriptors.action)||!('value' in descriptors.request)||
    descriptors.action.value!==prepared.target.action||canonicalPublicRequest(descriptors.request.value)!==canonicalPublicRequest(prepared.request))fail();
  fence(input.owner,prepared.target.action,prepared.ownerContext);
  if(!canPrepareRequest(input.owner,prepared.request))fail();
  return prepared;
 }
 async function observe(pointer:OperationPointer,signal:AbortSignal,call:(selected:KnowledgeSourceLookup)=>Promise<unknown>,anchor?:PreparedProjectKnowledgeWrite):Promise<EffectReceipt>{
  const selected=lookup(pointer),before=context(input.owner,selected.action,signal);
  const status=decodeProjectSourceOperationStatus(await call(selected),{action:selected.action,workRef:selected.work_ref,requestId:selected.request_id,requestSha256:selected.request_sha256,principalScope:before.principalScope});
  fence(input.owner,selected.action,before,signal);
  if(status.selection.action!==selected.action||status.selection.request_id!==selected.request_id||
    status.selection.work_ref!==selected.work_ref||status.owner_context.principal_scope!==before.principalScope||
    (status.receipt!==null&&status.request_sha256!==selected.request_sha256)||
    (anchor&&status.receipt!==null&&status.recipe_fingerprint_sha256!==anchor.response.recipe_fingerprint_sha256))fail();
  if(selected.action==='correct_project_discovery'&&status.receipt?.kind==='SOURCE_OBSERVED'){
   qualifyDiscoveryCorrectionSources(selected,before.principalScope,status.receipt.sources,anchor?.response.preview.postimages);
  }
  input.onStatus?.(status);
  return {operationKey:pointer.operationKey,kind:'project_source_write',targetKey:pointer.targetKey,disposition:status.disposition};
 }
 return {
  context:()=>{try{return input.owner.context();}catch{return null;}},
  prepare(intent){const prepared=preparedFor(intent);return {operationKey:prepared.request.request_id,kind:'project_source_write',targetKey:prepared.targetKey};},
  async submit(pointer,intent,signal){
   const prepared=preparedFor(intent),selected=lookup(pointer);
   if(selected.request_id!==prepared.request.request_id||pointer.targetKey!==prepared.targetKey)fail();
   return observe(pointer,signal,()=>input.transport.submitSourceOperation({action:selected.action,request_id:selected.request_id,
    work_ref:selected.work_ref,preview_witness:prepared.response.preview_witness},signal),prepared);
  },
  readOperation:(pointer,signal)=>observe(pointer,signal,selected=>input.transport.readSourceOperation(selected,signal)),
  reconcileOperation:(pointer,signal)=>observe(pointer,signal,selected=>input.transport.reconcileSourceOperation(selected,signal)),
 };
}
