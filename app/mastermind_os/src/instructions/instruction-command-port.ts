/** Original instruction pause through the incumbent finite controller. */
import type {FiniteCommandPort,OwnerContext,CommandIntent,OperationPointer,EffectReceipt} from "../orchestration/operation-controller";
import {parseInstructionAdmissionTarget,serializeInstructionAdmissionTarget} from "../orchestration/instruction-admission-target";
import {decodeInstructionAdmissionControl,decodeInstructionAdmissionResult,type InstructionAdmissionSelection} from "./instruction-admission";
import type {InstructionPauseRequest,InstructionStatusRequest} from "./instruction-host";
export interface InstructionAdmissionSnapshot {
 selection:InstructionAdmissionSelection|null;data:unknown;dataGeneration:string|null;generation:string|null;canRead:boolean;
}
export interface InstructionAdmissionTransport {
 pause(request:InstructionPauseRequest):Promise<unknown>;
 status(request:InstructionStatusRequest):Promise<unknown>;
}
function exact(value:unknown,keys:readonly string[]):value is Record<string,unknown>{
 if(typeof value!=="object"||value===null||Array.isArray(value)||![Object.prototype,null].includes(Object.getPrototypeOf(value)))return false;
 const fields=Object.getOwnPropertyDescriptors(value);
 return Reflect.ownKeys(fields).length===keys.length&&keys.every(k=>Object.hasOwn(fields,k)&&fields[k].enumerable&&Object.hasOwn(fields[k],"value"));
}
function same(a:unknown,b:InstructionAdmissionSelection):boolean{return serializeInstructionAdmissionTarget(a as InstructionAdmissionSelection)===serializeInstructionAdmissionTarget(b);}
function pointerMatches(pointer:OperationPointer,selection:InstructionAdmissionSelection):boolean {
 return pointer.kind==="instruction_pause"&&/^mmos-instruction-pause-[0-9a-f]{40}$/.exec(pointer.operationKey)?.[0]===pointer.operationKey
  &&pointer.targetKey===serializeInstructionAdmissionTarget(selection)&&parseInstructionAdmissionTarget(pointer.targetKey)!==null;
}
export function instructionEffectReceipt(value:unknown,pointer:OperationPointer,selection:InstructionAdmissionSelection,status=false):EffectReceipt {
 if(!pointerMatches(pointer,selection))return {...pointer,disposition:"unknown"};
 const body=decodeInstructionAdmissionResult(value,{...selection,command_id:pointer.operationKey},status?"status":"pause");
 if(!body)return {...pointer,disposition:"unknown"};
 if(status)return {...pointer,disposition:"state" in body&&body.state==="OBSERVED"?"accepted":"unknown"};
 return {...pointer,disposition:"disposition" in body&&body.disposition==="COMMITTED"?"accepted":"disposition" in body&&body.disposition==="NOT_DISPATCHED"?"refused":"unknown"};
}
export function createInstructionAdmissionCommandPort(getCurrent:()=>InstructionAdmissionSnapshot,transport:InstructionAdmissionTransport):FiniteCommandPort {
 let retained:{context:OwnerContext;selection:InstructionAdmissionSelection}|null=null;
 let departed:string|null=null;
 function context():OwnerContext|null {
  const snapshot=getCurrent();
  if(!snapshot.canRead||!snapshot.selection||serializeInstructionAdmissionTarget(snapshot.selection)===null||!snapshot.generation){retained=null;return null;}
  if(retained&&(retained.context.generation!==snapshot.generation||!same(snapshot.selection,retained.selection)))retained=null;
  if(departed===snapshot.generation)return null;
  const body=snapshot.dataGeneration===snapshot.generation?decodeInstructionAdmissionControl(snapshot.data,snapshot.selection):null;
  if(body?.owner_context){
   const owner={principalScope:body.owner_context.principal_scope,generation:snapshot.generation};
   if(retained&&retained.context.principalScope!==owner.principalScope){departed=snapshot.generation;retained=null;return null;}
   retained={context:owner,selection:{...snapshot.selection}};
  }
  return retained?{...retained.context}:null;
 }
 function permitted(intent:CommandIntent){
  const snapshot=getCurrent();
  if(!snapshot.canRead||!snapshot.selection||!snapshot.generation||snapshot.dataGeneration!==snapshot.generation)return null;
  const data=decodeInstructionAdmissionControl(snapshot.data,snapshot.selection);
  if(data?.availability!=="AVAILABLE"||data.state!=="NOT_SUSPENDED"||!data.permission.pause||intent.kind!=="instruction_pause"
   ||intent.targetKey!==serializeInstructionAdmissionTarget(snapshot.selection)||!exact(intent.payload,["selection","expected_revision","expected_source"])
   ||!same(intent.payload.selection,snapshot.selection)||intent.payload.expected_revision!==data.instruction_revision
   ||!exact(intent.payload.expected_source,["repository","commit","path","content_sha256"]))return null;
  const source=intent.payload.expected_source;
  if(source.repository!==data.source.repository||source.commit!==data.source.commit||source.path!==data.source.path||source.content_sha256!==data.source.content_sha256)return null;
  return {selection:{...snapshot.selection},data};
 }
 return {
  context,
  prepare(intent){
   if(!context()||!permitted(intent))throw Error("INSTRUCTION_PAUSE_UNAVAILABLE");
   const bytes=new Uint8Array(20);globalThis.crypto.getRandomValues(bytes);
   return {kind:"instruction_pause",targetKey:intent.targetKey,operationKey:"mmos-instruction-pause-"+Array.from(bytes,x=>x.toString(16).padStart(2,"0")).join("")};
  },
  async submit(pointer,intent,signal){
   const value=permitted(intent),before=context();
   if(!value||!before||!pointerMatches(pointer,value.selection)||pointer.targetKey!==intent.targetKey||signal.aborted)return {...pointer,disposition:"refused"};
   try{
    const result=await transport.pause({selection:value.selection,command_id:pointer.operationKey,expected_revision:value.data.instruction_revision,expected_source:value.data.source,signal});
    const after=context();
    if(signal.aborted||!after||after.principalScope!==before.principalScope||after.generation!==before.generation||!same(getCurrent().selection,value.selection))return {...pointer,disposition:"unknown"};
    return instructionEffectReceipt(result,pointer,value.selection);
   }catch{return {...pointer,disposition:"unknown"};}
  },
  async readOperation(pointer,signal){
   const before=context(),selected=getCurrent().selection;
   if(!before||!selected||!pointerMatches(pointer,selected)||signal.aborted)return {...pointer,disposition:"unknown"};
   const selection={...selected};
   try{
    const result=await transport.status({selection,command_id:pointer.operationKey,signal}),after=context();
    if(signal.aborted||!after||after.principalScope!==before.principalScope||after.generation!==before.generation||!same(getCurrent().selection,selection))return {...pointer,disposition:"unknown"};
    return instructionEffectReceipt(result,pointer,selection,true);
   }catch{return {...pointer,disposition:"unknown"};}
  },
 };
}
