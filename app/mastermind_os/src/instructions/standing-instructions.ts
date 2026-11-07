/** Canonical content only. Revisions/source hashes are syntax checked here;
 * their recomputation and currentness belong to the authenticated Python owner.
 * Authored text never establishes instruction state, permission or execution. */
export interface StandingInstructionSelection {readonly work_ref:string}
export interface InstructionSource {readonly repository:'mastermindx-market-intelligence/macro';readonly commit:string;readonly path:string;readonly content_sha256:string}
export interface StandingInstruction {readonly instruction_ref:string;readonly text:string;readonly revision:string}
export type InstructionReadReason='ACCESS_DENIED'|'SOURCE_UNAVAILABLE'|'SOURCE_CHANGED'|'OWNER_NOT_READY'|'RECORD_NOT_FOUND'|'RECORD_INVALID'|'CONTENT_OVER_BUDGET';
type ContentFacts=(
 {readonly availability:'AVAILABLE';readonly source:InstructionSource;readonly declaration:'NOT_DECLARED'|'SUPPLIED';readonly instructions:readonly StandingInstruction[];readonly reason_codes:readonly []}|
 {readonly availability:'UNAVAILABLE';readonly source:null;readonly declaration:null;readonly instructions:null;readonly reason_codes:readonly [InstructionReadReason]});
export type StandingInstructionsRead=({readonly schema:'mastermind.workspace_project_instructions.v1';readonly selection:StandingInstructionSelection}&ContentFacts)|({readonly schema:'mastermind.workspace_project_instructions.v2';readonly selection:StandingInstructionSelection;readonly recovery_identity:Readonly<{principal_scope:string}>|null}&ContentFacts);
const SCHEMA='mastermind.workspace_project_instructions.v1',PUBLIC_SCHEMA='mastermind.workspace_project_instructions.v2';
const REASONS=new Set<unknown>(['ACCESS_DENIED','SOURCE_UNAVAILABLE','SOURCE_CHANGED','OWNER_NOT_READY','RECORD_NOT_FOUND','RECORD_INVALID','CONTENT_OVER_BUDGET']);
const match=(pattern:RegExp,value:unknown):value is string=>typeof value==='string'&&pattern.exec(value)?.[0]===value;
function key(value:unknown,prefix:string):value is string{return typeof value==='string'&&value.startsWith(prefix)&&value.length>=prefix.length+2&&value.length<=prefix.length+64&&match(/^[A-Z0-9]+(?:-[A-Z0-9]+)*$/,value.slice(prefix.length));}
function utf16(value:string):boolean{for(let i=0;i<value.length;i++){const c=value.charCodeAt(i);if(c>=0xd800&&c<=0xdbff){const next=value.charCodeAt(++i);if(!(next>=0xdc00&&next<=0xdfff))return false;}else if(c>=0xdc00&&c<=0xdfff)return false;}return true;}
function record(value:unknown,keys:readonly string[]):value is Record<string,unknown>{return value!==null&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).length===keys.length&&keys.every(k=>Object.hasOwn(value,k));}
/** A bounded parsed-JSON copy rejects accessors/symbols/toJSON before any read. */
function parsed(value:unknown,seen:Set<object>,depth=0,budget={bytes:0}):unknown{
 if(value===null||typeof value==='boolean')return value;
 if(typeof value==='string'){if(value.length>8192||!utf16(value))throw Error();budget.bytes+=new TextEncoder().encode(value).length;if(budget.bytes>32768)throw Error();return value;}
 if(typeof value!=='object'||depth>6||seen.has(value)||seen.size>=128)throw Error();
 seen.add(value);
 const prototype=Object.getPrototypeOf(value),fields=Object.getOwnPropertyDescriptors(value),keys=Reflect.ownKeys(fields);
 if(Array.isArray(value)){
  const length=fields.length?.value;
  if(prototype!==Array.prototype||typeof length!=='number'||!Number.isSafeInteger(length)||length<0||length>16||keys.length!==length+1)throw Error();
  const result:unknown[]=[];
  for(let i=0;i<length;i++){const d=fields[String(i)];if(!d||!Object.hasOwn(d,'value')||!d.enumerable)throw Error();result.push(parsed(d.value,seen,depth+1,budget));}
  return result;
 }
 if(prototype!==Object.prototype&&prototype!==null||keys.length>8)throw Error();
 const result:Record<string,unknown>=Object.create(null);
 for(const k of keys){if(typeof k!=='string'||k.length>64)throw Error();const d=fields[k];if(!Object.hasOwn(d,'value')||!d.enumerable)throw Error();result[k]=parsed(d.value,seen,depth+1,budget);}
 return result;
}
export function validStandingInstructionSelection(value:unknown):value is StandingInstructionSelection{
 try{const safe=parsed(value,new Set());return record(safe,['work_ref'])&&key(safe.work_ref,'WS:');}catch{return false;}
}
function source(value:unknown,work:string):value is InstructionSource{return record(value,['repository','commit','path','content_sha256'])&&value.repository==='mastermindx-market-intelligence/macro'&&match(/^[0-9a-f]{40}$/,value.commit)&&value.path===`agentos/workstreams/WS-${work.slice(3)}.md`&&match(/^[0-9a-f]{64}$/,value.content_sha256);}
// Python str.strip's whitespace set, including NEL but excluding BOM.
const BLANK=/^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]*$/u;
export function decodeStandingInstructions(value:unknown,expected:StandingInstructionSelection):StandingInstructionsRead|null{
 try{
  const selected=parsed(expected,new Set());if(!record(selected,['work_ref'])||!key(selected.work_ref,'WS:'))return null;
  const body=parsed(value,new Set());
  const owned=record(body,['schema','selection','availability','source','declaration','instructions','reason_codes','recovery_identity']);
  if(!(owned||record(body,['schema','selection','availability','source','declaration','instructions','reason_codes']))||body.schema!==(owned?PUBLIC_SCHEMA:SCHEMA)||!record(body.selection,['work_ref'])||body.selection.work_ref!==selected.work_ref)return null;
  if(body.availability==='AVAILABLE'){
   if(!source(body.source,selected.work_ref)||!['NOT_DECLARED','SUPPLIED'].includes(body.declaration as string)||!Array.isArray(body.instructions)||!Array.isArray(body.reason_codes)||body.reason_codes.length!==0||body.declaration==='NOT_DECLARED'&&body.instructions.length!==0)return null;
   const refs=new Set<string>();
   for(const row of body.instructions){
    if(!record(row,['instruction_ref','text','revision'])||!key(row.instruction_ref,'INS:')||refs.has(row.instruction_ref)||typeof row.text!=='string'||BLANK.test(row.text)||Array.from(row.text).length>4096||/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/u.test(row.text)||!match(/^[0-9a-f]{64}$/,row.revision))return null;
    refs.add(row.instruction_ref);
   }
  }else if(body.availability==='UNAVAILABLE'){
   if(body.source!==null||body.declaration!==null||body.instructions!==null||!Array.isArray(body.reason_codes)||body.reason_codes.length!==1||!REASONS.has(body.reason_codes[0]))return null;
  }else return null;
  if(owned){
   if(body.availability==='AVAILABLE'){if(!record(body.recovery_identity,['principal_scope'])||!match(/^[0-9a-f]{64}$/,body.recovery_identity.principal_scope))return null;}
   else if(body.recovery_identity!==null)return null;
  }
  if(new TextEncoder().encode(JSON.stringify({ok:true,result:body})+'\n').length>32768)return null;
  return JSON.parse(JSON.stringify(body)) as StandingInstructionsRead;
 }catch{return null;}
}
