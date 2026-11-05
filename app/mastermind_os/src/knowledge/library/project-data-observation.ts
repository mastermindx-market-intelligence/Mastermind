/** Closed owner-observed CODE/DATA provenance. No permission, currentness,
 * clock acquisition, network, source selection or operation effect lives here. */
export type SourceObservedAction='add_project_file'|'set_project_communication_preference'|'publish_project_proposal'|'publish_project_plan_proposal'|'ADOPT_PLAN';
export interface CanonicalProjectDataObservation{
 readonly schema:'mastermind.canonical_project_data_observation.v1';
 readonly repository:'mastermindx-market-intelligence/macro'; readonly default_ref:string;
 readonly executable_macro_commit:string;readonly canonical_data_commit:string;
 readonly canonical_commit_at:string;readonly canonical_observed_at_ms:number;
 readonly publication_recorded_at_ms:number|null;readonly publication_time:null;
 readonly source_operation:null|Readonly<{selection:Readonly<{action:SourceObservedAction;request_id:string;work_ref:string}>;
  principal_scope:string;request_sha256:string;recipe_fingerprint_sha256:string;event_id:number;receipt_sha256:string;recorded_at_ms:number;
  sources:readonly Readonly<{repository:'macro';commit:string;path:string;content_sha256:string}>[]}>;
 readonly reader_closure_sha256:string;readonly code_config_relation:'IDENTICAL_READER_CLOSURE';readonly authority:'OBSERVATION_ONLY';
 readonly data_continuity?:ProjectDataContinuity;
}
/** Closed continuity frame for selected DATA unchanged across a CODE-only move:
 * the same work, principal, reader closure and both exact commits, emitted
 * beside its observation. No authority, publication or Event is inferred here. */
export interface ProjectDataContinuity{
 readonly schema:'mastermind.project_data_continuity.v1';readonly kind:'UNCHANGED_SELECTED_PROJECT_DATA';
 readonly work_ref:string;readonly principal_scope:string;
 readonly executable_macro_commit:string;readonly canonical_data_commit:string;
 readonly reader_closure_sha256:string;readonly selected_data_closure_sha256:string;
 readonly ancestry:'CODE_ANCESTOR_OF_DATA';
}
function invalid():never{throw new Error('INVALID_CANONICAL_DATA_OBSERVATION');}
function record(value:unknown,keys:readonly string[],optional:readonly string[]=[]):Record<string,unknown>{
 if(!value||typeof value!=='object'||Array.isArray(value))invalid();
 const proto=Object.getPrototypeOf(value);if(proto!==Object.prototype&&proto!==null)invalid();
 const own=Reflect.ownKeys(value);
 if(own.length<keys.length||own.length>keys.length+optional.length||own.some(key=>typeof key!=='string'||(!keys.includes(key)&&!optional.includes(key))))invalid();
 const out:Record<string,unknown>={};
 for(const key of keys){const d=Object.getOwnPropertyDescriptor(value,key);if(!d||!d.enumerable||!('value' in d))invalid();out[key]=d.value;}
 for(const key of optional){if(!own.includes(key))continue;const d=Object.getOwnPropertyDescriptor(value,key);if(!d||!d.enumerable||!('value' in d))invalid();out[key]=d.value;}
 return out;
}
function hex(value:unknown,length:number):string{if(typeof value!=='string'||value.length!==length||!/^[0-9a-f]+$/.test(value))invalid();return value;}
function integer(value:unknown,min=0):number{if(typeof value!=='number'||!Number.isSafeInteger(value)||value<min)invalid();return value;}
function path(value:unknown,max:number):string{
 if(typeof value!=='string'||value.length>max||/^[A-Za-z0-9][A-Za-z0-9._/-]*$/.exec(value)?.[0]!==value||value.split('/').some(part=>!part||part==='.'||part==='..'))invalid();return value;
}
function stamp(value:unknown):string{
 if(typeof value!=='string'||value.length>64)invalid();
 const m=/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|([+-])(\d{2}):(\d{2}))$/.exec(value);
 if(!m||+m[2]!<1||+m[2]!>12||+m[3]!<1||+m[3]!>31||+m[4]!>23||+m[5]!>59||+m[6]!>59||+(m[8]??0)>23||+(m[9]??0)>59||!Number.isFinite(Date.parse(value)))invalid();
 const date=new Date(0);date.setUTCFullYear(+m[1]!,+m[2]!-1,+m[3]!);
 if(date.getUTCMonth()!==+m[2]!-1||date.getUTCDate()!==+m[3]!)invalid();return value;
}
function freeze<T>(value:T):T{if(value&&typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value);}return value;}
/** Closed continuity qualification: exact fixed fields, valid WS work, 64-hex
 * principal and closures, and C/N/reader_closure joins to its own observation
 * with C!=N. Never inferred from the DATA, build SHA, clock or authority. */
function validateDataContinuity(raw:unknown,code:string,data:string,reader:string,workRef:string|undefined):ProjectDataContinuity{
 const value=record(raw,['schema','kind','work_ref','principal_scope','executable_macro_commit','canonical_data_commit','reader_closure_sha256','selected_data_closure_sha256','ancestry']);
 if(value.schema!=='mastermind.project_data_continuity.v1'||value.kind!=='UNCHANGED_SELECTED_PROJECT_DATA'||value.ancestry!=='CODE_ANCESTOR_OF_DATA')invalid();
 if(typeof value.work_ref!=='string'||/^WS:[A-Z0-9]+(?:-[A-Z0-9]+)*$/.exec(value.work_ref)?.[0]!==value.work_ref||value.work_ref.length<5||value.work_ref.length>67||(workRef!==undefined&&value.work_ref!==workRef))invalid();
 const innerCode=hex(value.executable_macro_commit,40),innerData=hex(value.canonical_data_commit,40);
 if(innerCode!==code||innerData!==data||innerCode===innerData)invalid();
 if(hex(value.reader_closure_sha256,64)!==reader)invalid();
 return freeze({schema:'mastermind.project_data_continuity.v1',kind:'UNCHANGED_SELECTED_PROJECT_DATA',work_ref:value.work_ref,
  principal_scope:hex(value.principal_scope,64),executable_macro_commit:innerCode,canonical_data_commit:innerData,
  reader_closure_sha256:reader,selected_data_closure_sha256:hex(value.selected_data_closure_sha256,64),ancestry:'CODE_ANCESTOR_OF_DATA'});
}
/** expectedExecutable is an actual pinned App/owner CODE coordinate, never a
 * value inferred from this observation. Omission performs shape qualification
 * only (e.g. fixed host parsing); consumers must separately bind CODE scope. */
export function validateProjectDataObservation(raw:unknown,expected:{workRef?:string;canonicalDataCommit?:string;executableMacroCommit?:string}={}):CanonicalProjectDataObservation{
 try{
  const value=record(raw,['schema','repository','default_ref','executable_macro_commit','canonical_data_commit','canonical_commit_at','canonical_observed_at_ms','publication_recorded_at_ms','publication_time','source_operation','reader_closure_sha256','code_config_relation','authority'],['data_continuity']);
  if(value.schema!=='mastermind.canonical_project_data_observation.v1'||value.repository!=='mastermindx-market-intelligence/macro'||value.publication_time!==null||value.code_config_relation!=='IDENTICAL_READER_CLOSURE'||value.authority!=='OBSERVATION_ONLY')invalid();
  const code=hex(value.executable_macro_commit,40),data=hex(value.canonical_data_commit,40),reader=hex(value.reader_closure_sha256,64);
  if((expected.executableMacroCommit!==undefined&&code!==expected.executableMacroCommit)||(expected.canonicalDataCommit!==undefined&&data!==expected.canonicalDataCommit))invalid();
  const observed=integer(value.canonical_observed_at_ms,1),publication=value.publication_recorded_at_ms===null?null:integer(value.publication_recorded_at_ms);
  let operation:CanonicalProjectDataObservation['source_operation']=null;
  let continuity:ProjectDataContinuity|undefined;
  if(value.source_operation===null){
   if(publication!==null)invalid();
   if(!Object.hasOwn(value,'data_continuity')){if(code!==data)invalid();}
   else{if(code===data)invalid();continuity=validateDataContinuity(value.data_continuity,code,data,reader,expected.workRef);}
  }
  else{
   if(Object.hasOwn(value,'data_continuity'))invalid();
   const op=record(value.source_operation,['selection','principal_scope','request_sha256','recipe_fingerprint_sha256','event_id','receipt_sha256','recorded_at_ms','sources']);
   const selected=record(op.selection,['action','request_id','work_ref']);
   const prefix=selected.action==='add_project_file'?'mmos-project-file-add-':selected.action==='set_project_communication_preference'?'mmos-project-preference-set-':selected.action==='publish_project_proposal'?'mmos-project-create-':selected.action==='publish_project_plan_proposal'?'mmos-project-plan-proposal-':selected.action==='ADOPT_PLAN'?'mmos-project-adopt-':invalid();
   if(typeof selected.request_id!=='string'||!selected.request_id.startsWith(prefix)||!/^[0-9a-f]{40}$/.test(selected.request_id.slice(prefix.length))||selected.request_id.length!==prefix.length+40||typeof selected.work_ref!=='string'||/^WS:[A-Z0-9]+(?:-[A-Z0-9]+)*$/.exec(selected.work_ref)?.[0]!==selected.work_ref||selected.work_ref.length<5||selected.work_ref.length>67||(expected.workRef!==undefined&&selected.work_ref!==expected.workRef))invalid();
   if(!Array.isArray(op.sources)||Object.getPrototypeOf(op.sources)!==Array.prototype)invalid();
   const listed=(op.sources as unknown[]).length;
   const count=selected.action==='publish_project_proposal'?1:selected.action==='ADOPT_PLAN'?(listed===2||listed===3?listed:invalid()):2;
   if(listed!==count||Reflect.ownKeys(op.sources).length!==count+1)invalid();
   const sources=[];
   for(let i=0;i<count;i++){
    const descriptor=Object.getOwnPropertyDescriptor(op.sources,String(i));if(!descriptor||!descriptor.enumerable||!('value' in descriptor))invalid();
    const source=record(descriptor.value,['repository','commit','path','content_sha256']);if(source.repository!=='macro')invalid();
    sources.push({repository:'macro' as const,commit:hex(source.commit,40),path:path(source.path,512),content_sha256:hex(source.content_sha256,64)});
   }
   if(new Set(sources.map(entry=>entry.path)).size!==count||new Set(sources.map(entry=>entry.commit)).size!==1)invalid();
   // Exact per-action source-path grammar. Source commits are never joined to
   // the DATA commit, and a candidate/READY/receipt artifact is never accepted
   // as adoption: DEC-PLAN-ADOPTION-<TAILUPPER>.md must itself be present.
   const work=selected.work_ref.slice(3),tail=selected.request_id.slice(prefix.length);
   if(selected.action==='publish_project_proposal'||selected.action==='publish_project_plan_proposal'){
    const expectedPaths=new Set(['agentos/workstreams/WS-'+work+'.md']);
    if(count===2)expectedPaths.add('research/project-plans/PLAN-'+work+'-'+tail+'.md');
    if(sources.some(entry=>!expectedPaths.has(entry.path)))invalid();
   }
   else if(selected.action==='ADOPT_PLAN'){
    const ws='agentos/workstreams/WS-'+work+'.md',decision='agentos/decisions/DEC-PLAN-ADOPTION-'+tail.toUpperCase()+'.md';
    const paths=new Set(sources.map(entry=>entry.path));
    if(!paths.has(ws)||!paths.has(decision))invalid();
    for(const entry of sources){
     if(entry.path===ws||entry.path===decision)continue;
     const key=/^agentos\/decisions\/DEC-([A-Z0-9]+(?:-[A-Z0-9]+)*)\.md$/.exec(entry.path)?.[1];
     if(key===undefined||key.length<2||key.length>128)invalid();
    }
   }
   const recorded=integer(op.recorded_at_ms);if(publication!==recorded)invalid();
   operation={selection:{action:selected.action as SourceObservedAction,request_id:selected.request_id,work_ref:selected.work_ref},
    principal_scope:hex(op.principal_scope,64),request_sha256:hex(op.request_sha256,64),recipe_fingerprint_sha256:hex(op.recipe_fingerprint_sha256,64),
    event_id:integer(op.event_id,1),receipt_sha256:hex(op.receipt_sha256,64),recorded_at_ms:recorded,sources};
  }
  const observation:CanonicalProjectDataObservation={schema:'mastermind.canonical_project_data_observation.v1',repository:'mastermindx-market-intelligence/macro',default_ref:path(value.default_ref,200),
   executable_macro_commit:code,canonical_data_commit:data,canonical_commit_at:stamp(value.canonical_commit_at),canonical_observed_at_ms:observed,
   publication_recorded_at_ms:publication,publication_time:null,source_operation:operation,reader_closure_sha256:reader,
   code_config_relation:'IDENTICAL_READER_CLOSURE',authority:'OBSERVATION_ONLY'};
  return freeze(continuity?{...observation,data_continuity:continuity}:observation);
 }catch{invalid();}
}

/** Independently emitted by the sealed reader's CODE snapshot, never inferred
 * from DATA, build SHA, a timestamp or the observation's own code claim. */
export interface ProjectKnowledgeCodeContext {
 readonly schema:'mastermind.project_knowledge_code_context.v1';readonly work_ref:string;
 readonly executable_macro_commit:string;readonly reader_source_commit:string;
}
export interface ProjectKnowledgeReadMetadata {
 readonly codeContext?:ProjectKnowledgeCodeContext;
 readonly dataObservation?:CanonicalProjectDataObservation;
}
export function validateProjectKnowledgeCodeContext(raw:unknown,workRef:string):ProjectKnowledgeCodeContext{
 const value=record(raw,['schema','work_ref','executable_macro_commit','reader_source_commit']);
 if(value.schema!=='mastermind.project_knowledge_code_context.v1'||value.work_ref!==workRef)invalid();
 return freeze({schema:'mastermind.project_knowledge_code_context.v1',work_ref:workRef,
  executable_macro_commit:hex(value.executable_macro_commit,40),reader_source_commit:hex(value.reader_source_commit,40)});
}
/** Only these two named optional fields are allowed; legacy no-context bodies
 * remain parseable, while DATA capability needs actual independent CODE. */
export function knowledgeReadKeys(raw:object,base:readonly string[]):string[]{
 return [...base,...['code_context','data_observation'].filter(key=>Object.hasOwn(raw,key))];
}
export function validateKnowledgeReadMetadata(raw:Record<string,unknown>,workRef:string):ProjectKnowledgeReadMetadata{
 const code=Object.getOwnPropertyDescriptor(raw,'code_context'),data=Object.getOwnPropertyDescriptor(raw,'data_observation');
 if(!code&&!data)return Object.freeze({});
 if(!code||!code.enumerable||!('value' in code)||(data&&(!data.enumerable||!('value' in data))))invalid();
 const codeContext=validateProjectKnowledgeCodeContext(code.value,workRef);
 let commit:string|undefined;
 const sourceField=Object.getOwnPropertyDescriptor(raw,'source');
 if(!sourceField||!('value' in sourceField))invalid();
 if(sourceField.value!==null){
  if(!sourceField.value||typeof sourceField.value!=='object')invalid();
  const descriptor=Object.getOwnPropertyDescriptor(sourceField.value,'commit');
  if(!descriptor||!('value' in descriptor))invalid();commit=hex(descriptor.value,40);
 }
 if(data){
  const dataObservation=validateProjectDataObservation(data.value,{workRef,canonicalDataCommit:commit,executableMacroCommit:codeContext.executable_macro_commit});
  return freeze({codeContext,dataObservation});
 }
 if(commit!==undefined&&commit!==codeContext.executable_macro_commit)invalid();
 return freeze({codeContext});
}
export function sameKnowledgeCodeContext(left:ProjectKnowledgeCodeContext|undefined,right:ProjectKnowledgeCodeContext|undefined):boolean{
 return left===undefined?right===undefined:!!right&&left.work_ref===right.work_ref&&left.executable_macro_commit===right.executable_macro_commit&&left.reader_source_commit===right.reader_source_commit;
}
