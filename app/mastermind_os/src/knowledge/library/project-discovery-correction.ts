/** Closed correction values and deterministic paths. No permission, original
 * identity minting, transport, persistence, clock or publication lives here. */
import {canonicalJson, sha256Hex} from '../../orchestration/operation-key';

export const DISCOVERY_CORRECTION_ACTION = 'correct_project_discovery';
export const DISCOVERY_CORRECTION_SCHEMA = 'mastermind.project_discovery_correct_request.v1';
export const DISCOVERY_CORRECTION_PREFIX = 'mmos-project-discovery-correct-';
export const DISCOVERY_KINDS = ['architecture','data','landmine','dead_code','constraint','runtime'] as const;
export interface DiscoveryReplacement {
  claim:string; falsifier:string; so_what:string;
  kind:(typeof DISCOVERY_KINDS)[number]; confidence:'verified'|'probable'|'suspected';
  verified_at:string; verified_by:string; expires:string|null; body_utf8:string; evidence:string[];
}
export interface ProjectDiscoveryCorrectionRequest {
  schema:typeof DISCOVERY_CORRECTION_SCHEMA; request_id:string; work_ref:string;
  source_commit:string; base_revision:string; discovery_ref:string;
  expected_discovery_revision:string; correction_reason:string; replacement:DiscoveryReplacement;
}
export interface DiscoveryCorrectionTarget {
  action:typeof DISCOVERY_CORRECTION_ACTION; work_ref:string; source_commit:string;
  base_revision:string; request_sha256:string; discovery_ref:string; expected_discovery_revision:string;
}
export type DiscoveryCorrectionLookup = DiscoveryCorrectionTarget & {request_id:string};
export interface DiscoveryCorrectionPreviewChange {
  kind:'DISCOVERY_CORRECTION'; discovery_ref:string; replacement_ref:string;
  correction_reason:string; replacement:DiscoveryReplacement;
}
export const DISCOVERY_CORRECTION_TARGET_KEYS = ['action','base_revision','discovery_ref',
  'expected_discovery_revision','request_sha256','source_commit','work_ref'] as const;
const requestKeys=['schema','request_id','work_ref','source_commit','base_revision','discovery_ref',
  'expected_discovery_revision','correction_reason','replacement'];
const replacementKeys=['claim','falsifier','so_what','kind','confidence','verified_at','verified_by','expires','body_utf8','evidence'];
const bytes=(value:string)=>new TextEncoder().encode(value).length;
function invalid():never {throw Error('INVALID_PROJECT_DISCOVERY_CORRECTION');}
function object(value:unknown,keys:readonly string[]):Record<string,unknown> {
  if(!value||typeof value!=='object'||Array.isArray(value)||![Object.prototype,null].includes(Object.getPrototypeOf(value)))invalid();
  const fields=Object.getOwnPropertyDescriptors(value), own=Reflect.ownKeys(fields);
  if(own.length!==keys.length||own.some(key=>typeof key!=='string'||!keys.includes(key)))invalid();
  return Object.fromEntries(keys.map(key=>{const d=fields[key];if(!d?.enumerable||!Object.hasOwn(d,'value'))invalid();return [key,d.value];}));
}
function hex(value:unknown,size:number):string {
  if(typeof value!=='string'||value.length!==size||!/^[0-9a-f]+$/.test(value))invalid();return value;
}
export function validDiscoveryReference(value:unknown,prefix='DSC:'):value is string {
  return typeof value==='string'&&value.startsWith(prefix)&&value.length>=prefix.length+2&&value.length<=prefix.length+64
    &&/^[A-Z0-9]+(?:-[A-Z0-9]+)*$/.exec(value.slice(prefix.length))?.[0]===value.slice(prefix.length);
}
function text(value:unknown,limit:number,empty=false):string {
  if(typeof value!=='string'||bytes(value)>limit||(!value.trim()&&!(empty&&value==='')))invalid();
  for(const c of value){const n=c.codePointAt(0)!;if((n<32&&!['\n','\r','\t'].includes(c))||(n>=127&&n<=159)||(n>=0xd800&&n<=0xdfff))invalid();}
  return value;
}
function date(value:unknown):string {
  if(typeof value!=='string'||/^\d{4}-\d{2}-\d{2}$/.exec(value)?.[0]!==value)invalid();
  const [year,month,day]=value.split('-').map(Number);
  const days=[31,year!%4===0&&(year!%100!==0||year!%400===0)?29:28,31,30,31,30,31,31,30,31,30,31];
  if(year!<1||month!<1||month!>12||day!<1||day!>days[month!-1]!)invalid();return value;
}
function identity(v:Record<string,unknown>) {
  if(typeof v.request_id!=='string'||new RegExp('^'+DISCOVERY_CORRECTION_PREFIX+'[0-9a-f]{40}$').exec(v.request_id)?.[0]!==v.request_id
    ||!validDiscoveryReference(v.work_ref,'WS:')||!validDiscoveryReference(v.discovery_ref))invalid();
  hex(v.source_commit,40);hex(v.base_revision,64);hex(v.expected_discovery_revision,64);
}
function freeze<T>(value:T):T {if(value&&typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value);}return value;}
/** Returns a detached, deeply frozen request; never rewrites literal evidence. */
export function validateDiscoveryCorrectionRequest(raw:unknown):ProjectDiscoveryCorrectionRequest {
  const value=object(raw,requestKeys);if(value.schema!==DISCOVERY_CORRECTION_SCHEMA)invalid();identity(value);
  value.correction_reason=text(value.correction_reason,2048);
  const replacement=object(value.replacement,replacementKeys);
  for(const field of ['claim','falsifier','so_what','verified_by'])replacement[field]=text(replacement[field],2048);
  const verified=date(replacement.verified_at);replacement.verified_at=verified;
  if(replacement.expires!==null){const expiry=date(replacement.expires);replacement.expires=expiry;if(expiry<verified)invalid();}
  replacement.body_utf8=text(replacement.body_utf8,8192,true);
  if(!(DISCOVERY_KINDS as readonly unknown[]).includes(replacement.kind)||!['verified','probable','suspected'].includes(replacement.confidence as string))invalid();
  const evidence=replacement.evidence;
  if(!Array.isArray(evidence)||Object.getPrototypeOf(evidence)!==Array.prototype||evidence.length<1||evidence.length>8)invalid();
  const fields=Object.getOwnPropertyDescriptors(evidence);
  if(Reflect.ownKeys(fields).length!==evidence.length+1)invalid();
  replacement.evidence=Array.from({length:evidence.length},(_,i)=>{const d=fields[String(i)];if(!d?.enumerable||!Object.hasOwn(d,'value'))invalid();return text(d.value,1024);});
  if(new Set(replacement.evidence as string[]).size!==evidence.length||bytes(canonicalJson(replacement))>16384)invalid();
  value.replacement=replacement;if(bytes(canonicalJson(value))>24576)invalid();
  return freeze(value as unknown as ProjectDiscoveryCorrectionRequest);
}
export function validateDiscoveryCorrectionTarget(raw:unknown):DiscoveryCorrectionTarget {
  const value=object(raw,DISCOVERY_CORRECTION_TARGET_KEYS);
  if(value.action!==DISCOVERY_CORRECTION_ACTION||!validDiscoveryReference(value.work_ref,'WS:')||!validDiscoveryReference(value.discovery_ref))invalid();
  hex(value.source_commit,40);hex(value.base_revision,64);hex(value.request_sha256,64);hex(value.expected_discovery_revision,64);
  return freeze(value as unknown as DiscoveryCorrectionTarget);
}
export function validateDiscoveryCorrectionLookup(raw:unknown):DiscoveryCorrectionLookup {
  const value=object(raw,[...DISCOVERY_CORRECTION_TARGET_KEYS,'request_id']);identity(value);
  const {request_id,...target}=value;
  return freeze({...validateDiscoveryCorrectionTarget(target),request_id:request_id as string});
}
export function discoveryReplacementRef(value:{request_id:string;work_ref:string},principalScope:string):string {
  hex(principalScope,64);
  return 'DSC:PROJECT-CORRECTION-'+sha256Hex(canonicalJson({principal_scope:principalScope,request_id:value.request_id,work_ref:value.work_ref})).slice(0,40).toUpperCase();
}
export function discoveryCorrectionPreimages(request:Pick<ProjectDiscoveryCorrectionRequest,'request_id'|'work_ref'|'discovery_ref'|'base_revision'|'expected_discovery_revision'>,principalScope:string):Record<string,string|null> {
  const replacement=discoveryReplacementRef(request,principalScope);if(replacement===request.discovery_ref)invalid();
  return {['agentos/discoveries/DSC-'+request.discovery_ref.slice(4)+'.md']:request.expected_discovery_revision,
    ['agentos/discoveries/DSC-'+replacement.slice(4)+'.md']:null,
    ['agentos/workstreams/WS-'+request.work_ref.slice(3)+'.md']:request.base_revision};
}
/** Qualify the original atomic source set before any observer reports acceptance.
 * Recovery uses only the original lookup; an available prepared Review adds its
 * exact postimage hashes without becoming a recovery prerequisite. */
export function qualifyDiscoveryCorrectionSources(lookup:DiscoveryCorrectionLookup,principalScope:string,
  sources:readonly {repository:string;path:string;commit:string;content_sha256:string}[],
  images?:readonly {path:string;content_sha256:string}[]):void {
  const expected=discoveryCorrectionPreimages(lookup,principalScope);
  if(sources.length!==3||new Set(sources.map(source=>source.path)).size!==3
    ||new Set(sources.map(source=>source.commit)).size!==1
    ||sources.some(source=>source.repository!=='macro'||!Object.hasOwn(expected,source.path)))invalid();
  if(images){const hashes=new Map(images.map(image=>[image.path,image.content_sha256]));
    if(hashes.size!==3||sources.some(source=>hashes.get(source.path)!==source.content_sha256))invalid();}
}
