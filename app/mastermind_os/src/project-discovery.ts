/** Closed request-local DATA reads. Syntax and hashes never confer authority. */
import { canonicalJson, sha256Hex } from './orchestration/operation-key';
import { validateProjectDataObservation, type CanonicalProjectDataObservation } from './knowledge/library/project-data-observation';

type JsonRecord = Record<string, any>;
type Selection = { work_ref: string; root_job_id: string } | null;
export interface ProjectDataOwnerObservation {
  schema:'mastermind.workspace_source_observation.v2'; state:'SAME'; selection:Selection;
  control_room:JsonRecord; runtime:JsonRecord; project_data:JsonRecord;
}
export interface CanonicalProgramProject {
  work_ref:string; control_room:JsonRecord; source_validity:JsonRecord;
  cache_currentness:JsonRecord; source_observation:ProjectDataOwnerObservation;
}
function fail():never { throw new Error('PROJECT_DATA_INVALID'); }
const rec = (x:unknown):x is JsonRecord => !!x && typeof x==='object' && !Array.isArray(x);
const exact = (x:unknown, keys:readonly string[]):x is JsonRecord => rec(x)
  && Object.keys(x).length===keys.length && keys.every(key=>Object.hasOwn(x,key));
const hash = (x:unknown,n=64):x is string => typeof x==='string' && new RegExp(`^[a-f0-9]{${n}}$`).test(x);
const integer = (x:unknown,min=0):x is number => Number.isSafeInteger(x) && Number(x)>=min;
const text = (x:unknown,max=256):x is string => typeof x==='string' && x.length>0 && x.length<=max && !/[\u0000-\u001f\u007f-\u009f]/.test(x);
const work = (x:unknown):x is string => typeof x==='string' && /^WS:[A-Z0-9]+(?:-[A-Z0-9]+)*$/.test(x) && x.length>=5 && x.length<=67;
const root = (x:unknown):x is string => typeof x==='string' && /^JOB-[0-9]+$/.test(x) && x.length<=128;
const same = (a:unknown,b:unknown) => canonicalJson(a)===canonicalJson(b);
const digest = (x:unknown) => sha256Hex(canonicalJson(x));
const CONTROL = ['instance_before','instance_after','publication_before','publication_after','document_digest','source_validity_digest','cache_currentness_digest'];
const RUNTIME = ['schema','state','source_identity','before','after','snapshot_digest'];
const BASIS = ['source','code_source','data_observation','creation_publication','source_generation','document_digest','source_validity_digest','cache_currentness_digest'];
const REFERENCE = ['repository','commit','path','content_sha256'];

/** Detach bounded ordinary JSON through value descriptors, never getter/toJSON. */
function detached(raw:unknown):any {
  const seen=new WeakSet<object>(); let nodes=0;
  function copy(x:any,depth:number):any {
    if(++nodes>200000||depth>32)fail();
    if(x===null||typeof x==='boolean')return x;
    if(typeof x==='number'){if(!Number.isFinite(x))fail();return x;}
    if(typeof x==='string'){
      if(x.length>2_000_000||/[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]/u.test(x))fail();
      return x;
    }
    if(typeof x!=='object'||seen.has(x))fail();seen.add(x);
    const array=Array.isArray(x),proto=Object.getPrototypeOf(x);
    if(array ? proto!==Array.prototype : proto!==Object.prototype&&proto!==null)fail();
    const keys=Reflect.ownKeys(x);if(keys.some(key=>typeof key!=='string'))fail();
    const out:any=array?[]:{};
    if(array){
      const length=Object.getOwnPropertyDescriptor(x,'length');
      if(!length||!('value' in length)||!integer(length.value)||length.value>200000||keys.length!==length.value+1)fail();
      for(let i=0;i<length.value;i++){
        const descriptor=Object.getOwnPropertyDescriptor(x,String(i));
        if(!descriptor||!('value' in descriptor)||!descriptor.enumerable)fail();
        out.push(copy(descriptor.value,depth+1));
      }
    }else{
      for(const key of keys as string[]){
        const descriptor=Object.getOwnPropertyDescriptor(x,key);
        if(!descriptor||!('value' in descriptor)||!descriptor.enumerable||key==='__proto__')fail();
        Object.defineProperty(out,key,{value:copy(descriptor.value,depth+1),enumerable:true,writable:false});
      }
    }
    return Object.freeze(out);
  }
  try{
    const value=copy(raw,0);
    if(new TextEncoder().encode(canonicalJson(value)).length>2_000_000)fail();
    return value;
  }catch{fail();}
}

function reference(value:unknown,repository:string):JsonRecord {
  if(!exact(value,REFERENCE)||value.repository!==repository||!hash(value.commit,40)||!hash(value.content_sha256)
    ||typeof value.path!=='string'||value.path.length>512||!/^agentos\/|^scripts\//.test(value.path)
    ||value.path.split('/').some((part:string)=>!part||part==='.'||part==='..'))fail();
  return value;
}
function control(value:unknown):JsonRecord {
  if(!exact(value,CONTROL)||!text(value.instance_before)||value.instance_before!==value.instance_after
    ||!integer(value.publication_before,1)||value.publication_before!==value.publication_after
    ||!hash(value.document_digest)||!hash(value.source_validity_digest)||!hash(value.cache_currentness_digest))fail();
  return value;
}
function runtime(value:unknown):JsonRecord {
  if(!exact(value,RUNTIME)||value.schema!=='mastermind.runtime_read_observation.v1'||value.state!=='SAME'
    ||!text(value.source_identity)||!integer(value.before)||value.before!==value.after||!hash(value.snapshot_digest))fail();
  return value;
}
function decodeOwner(value:any,selection:Selection):ProjectDataOwnerObservation {
  if(!exact(value,['schema','state','selection','control_room','runtime','project_data'])
    ||value.schema!=='mastermind.workspace_source_observation.v2'||value.state!=='SAME'
    ||!same(value.selection,selection))fail();
  if(selection!==null&&(!exact(value.selection,['work_ref','root_job_id'])||!work(selection.work_ref)||!root(selection.root_job_id)))fail();
  control(value.control_room);runtime(value.runtime);
  const p=value.project_data;if(!exact(p,BASIS)||!hash(p.source_generation)
    ||!hash(p.document_digest)||!hash(p.source_validity_digest)||!hash(p.cache_currentness_digest))fail();
  const source=reference(p.source,'mastermindx-market-intelligence/macro');
  const match=/^agentos\/workstreams\/WS-([A-Z0-9]+(?:-[A-Z0-9]+)*)\.md$/.exec(source.path);
  const ref=match?'WS:'+match[1]:null;if(!work(ref)||(selection!==null&&selection.work_ref!==ref))fail();
  const code=reference(p.code_source,source.repository);
  if(code.path!=='scripts/agentos.py')fail();
  const witness:CanonicalProjectDataObservation=validateProjectDataObservation(p.data_observation,
    {workRef:ref,canonicalDataCommit:source.commit,executableMacroCommit:code.commit});
  const creation=p.creation_publication;
  if(!exact(creation,['selection','principal_scope','request_sha256','recipe_fingerprint_sha256','event_id','receipt_sha256','recorded_at_ms','sources'])
    ||!exact(creation.selection,['action','request_id','work_ref'])||creation.selection.action!=='publish_project_proposal'
    ||creation.selection.work_ref!==ref||typeof creation.selection.request_id!=='string'||!/^mmos-project-create-[a-f0-9]{40}$/.test(creation.selection.request_id)
    ||!['principal_scope','request_sha256','recipe_fingerprint_sha256','receipt_sha256'].every(key=>hash(creation[key]))
    ||!integer(creation.event_id,1)||!integer(creation.recorded_at_ms,1)||!Array.isArray(creation.sources)||creation.sources.length!==1)fail();
  const original=reference(creation.sources[0],'macro');if(original.path!==source.path)fail();
  if(witness.source_operation&&(witness.source_operation.principal_scope!==creation.principal_scope||witness.source_operation.selection.work_ref!==ref))fail();
  return value as ProjectDataOwnerObservation;
}
export function decodeProjectDataOwnerObservation(raw:unknown,selection:Selection):ProjectDataOwnerObservation|null {
  try{return decodeOwner(detached(raw),selection);}catch{return null;}
}

function validity(project:CanonicalProgramProject):void {
  const {source_validity:v,cache_currentness:c,control_room:doc,source_observation:o}=project;
  if(!exact(v,['schema','profile','source_generation','cards'])||v.schema!=='mastermind.project_data_source_validity.v1'
    ||v.profile!=='workspace_project_data_read.v1'||v.source_generation!==o.project_data.source_generation
    ||!exact(c,['state','source_generation'])||c.state!=='fresh'||c.source_generation!==v.source_generation
    ||!Array.isArray(v.cards)||v.cards.length>1||!rec(doc.autonomy)||!Array.isArray(doc.autonomy.responsibilities)
    ||doc.autonomy.responsibilities.length!==v.cards.length)fail();
  for(const receipt of v.cards){
    if(!exact(receipt,['responsibility_ref','root_job_id','components'])||receipt.responsibility_ref!==project.work_ref
      ||!(receipt.root_job_id===null||root(receipt.root_job_id))||!rec(receipt.components))fail();
    const row=doc.autonomy.responsibilities.find((item:any)=>item.responsibility_ref===project.work_ref);
    if(!row||row.root_job_id!==receipt.root_job_id||!rec(row.validity))fail();
    if(!same(Object.keys(receipt.components).sort(),Object.keys(row.validity).sort()))fail();
    for(const name of Object.keys(receipt.components)){
      if(!['card','decision_current','dispatch','owed_open_age'].includes(name))fail();
      const component=receipt.components[name],meta=row.validity[name];
      if(!exact(component,['proof_ref','qualified_at','remaining_ms','state'])||!rec(meta)
        ||meta.schema!=='mastermind.autonomy_validity.v1'||meta.policy!=='mapper-inclusive-48h-future-1h.v1'
        ||!hash(component.proof_ref)||component.proof_ref!==meta.proof_ref||component.qualified_at!==meta.qualified_at
        ||component.qualified_at!==doc.generated_at)fail();
      if(meta.valid_for_ms===null){if(component.remaining_ms!==null||component.state!=='unqualified')fail();}
      else if(!integer(meta.valid_for_ms)||!integer(component.remaining_ms,1)||component.remaining_ms>Math.min(meta.valid_for_ms,15000)||component.state!=='current')fail();
    }
  }
}

export function decodeCanonicalProgramsProjects(raw:unknown,baseObservation:unknown,baseControlRoom:unknown):readonly CanonicalProgramProject[] {
  try{
    const values=detached(raw),base=detached(baseControlRoom),observation=detached(baseObservation);
    if(!Array.isArray(values)||values.length>8||!rec(base)||!rec(base.sources)||!hash(base.sources.macro_sha,40)
      ||!Array.isArray(base.work)||!rec(observation)||observation.schema!=='mastermind.workspace_source_observation.v1'
      ||observation.state!=='SAME'||observation.selection!==null||observation.runtime!==null)fail();
    control(observation.control_room);
    const seen=new Set(base.work.map((row:any)=>row.work_ref));
    for(const value of values){
      if(!exact(value,['work_ref','control_room','source_validity','cache_currentness','source_observation'])||!work(value.work_ref)||seen.has(value.work_ref))fail();
      seen.add(value.work_ref);const o=decodeOwner(value.source_observation,null),p=o.project_data;
      if(!same(o.control_room,observation.control_room)||p.code_source.commit!==base.sources.macro_sha
        ||p.creation_publication.selection.work_ref!==value.work_ref)fail();
      const doc=value.control_room;
      if(!rec(doc)||doc.schema!=='mastermind.chairman_control_room.v1'||typeof doc.generated_at!=='string'
        ||!Number.isFinite(Date.parse(doc.generated_at))||!rec(doc.autonomy)||doc.autonomy.generated_at!==doc.generated_at
        ||!Array.isArray(doc.work)||doc.work.length!==1||doc.work[0].work_ref!==value.work_ref
        ||Math.abs(Date.parse(doc.generated_at)-p.data_observation.canonical_observed_at_ms)>=1000
        ||p.document_digest!==digest(doc)||p.source_validity_digest!==digest(value.source_validity)
        ||p.cache_currentness_digest!==digest(value.cache_currentness))fail();
      validity(value as CanonicalProgramProject);
    }
    return values as readonly CanonicalProgramProject[];
  }catch{fail();}
}
