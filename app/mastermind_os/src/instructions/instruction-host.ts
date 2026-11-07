/** Fixed content and instruction control methods; method presence grants nothing. */
import type {AuthState} from "../host";
import {serializeInstructionAdmissionTarget} from "../orchestration/instruction-admission-target";
import {decodeStandingInstructions,validStandingInstructionSelection,type StandingInstructionsRead,type StandingInstructionSelection,type InstructionSource} from "./standing-instructions";
import {decodeInstructionAdmissionControl,decodeInstructionAdmissionResult,type InstructionAdmissionSelection} from "./instruction-admission";
export type InstructionMode="content"|"current"|"pause"|"status";
export interface InstructionContentRequest {selection:StandingInstructionSelection;signal:AbortSignal}
export interface InstructionControlRequest {selection:InstructionAdmissionSelection;signal:AbortSignal}
export interface InstructionStatusRequest extends InstructionControlRequest {command_id:string}
export interface InstructionPauseRequest extends InstructionStatusRequest {expected_revision:string;expected_source:InstructionSource}
export interface InstructionRawMethods {
 readProjectInstructions(request:InstructionContentRequest):Promise<unknown>;
 readInstructionAdmissionControl(request:InstructionControlRequest):Promise<unknown>;
 pauseInstructionAdmission(request:InstructionPauseRequest):Promise<unknown>;
 readInstructionAdmissionOperation(request:InstructionStatusRequest):Promise<unknown>;
}
export type InstructionControlRead=NonNullable<ReturnType<typeof decodeInstructionAdmissionControl>>;
export interface InstructionHostMethods extends Omit<InstructionRawMethods,"readProjectInstructions"|"readInstructionAdmissionControl"> {
 readProjectInstructions(request:InstructionContentRequest):Promise<StandingInstructionsRead>;
 readInstructionAdmissionControl(request:InstructionControlRequest):Promise<InstructionControlRead>;
}
export type InstructionPublicRequest={selection:StandingInstructionSelection|InstructionAdmissionSelection;command_id?:string;expected_revision?:string;expected_source?:InstructionSource};
function exact(value:unknown,keys:readonly string[]):value is Record<string,unknown>{
 if(typeof value!=="object"||value===null||Array.isArray(value)||![Object.prototype,null].includes(Object.getPrototypeOf(value)))return false;
 const fields=Object.getOwnPropertyDescriptors(value);
 return Reflect.ownKeys(fields).length===keys.length&&keys.every(k=>Object.hasOwn(fields,k)&&fields[k].enumerable&&Object.hasOwn(fields[k],"value"));
}
const hex=(value:unknown,size:number):value is string=>typeof value==="string"&&new RegExp(`^[0-9a-f]{${size}}$`).exec(value)?.[0]===value;
export function instructionPublicRequest(mode:InstructionMode,input:unknown):InstructionPublicRequest|null{
 try{
  if(!["content","current","pause","status"].includes(mode))return null;
  const command=mode==="pause"||mode==="status";
  if(!exact(input,["selection","signal",...(command?["command_id"]:[]),...(mode==="pause"?["expected_revision","expected_source"]:[])]))return null;
  if(mode==="content"?!validStandingInstructionSelection(input.selection):serializeInstructionAdmissionTarget(input.selection as InstructionAdmissionSelection)===null)return null;
  const selection={...input.selection as InstructionAdmissionSelection};
  if(command&&(typeof input.command_id!=="string"||/^mmos-instruction-pause-[0-9a-f]{40}$/.exec(input.command_id)?.[0]!==input.command_id))return null;
  if(mode==="pause"){
   const source=input.expected_source;
   if(!hex(input.expected_revision,64)||!exact(source,["repository","commit","path","content_sha256"])
    ||source.repository!=="mastermindx-market-intelligence/macro"||!hex(source.commit,40)||!hex(source.content_sha256,64)
    ||source.path!==`agentos/workstreams/WS-${selection.work_ref.slice(3)}.md`)return null;
   return {selection,command_id:input.command_id as string,expected_revision:input.expected_revision,expected_source:{...source} as unknown as InstructionSource};
  }
  return {selection,...(command?{command_id:input.command_id as string}:{})};
 }catch{return null;}
}
export function instructionQuery(payload:InstructionPublicRequest):string{
 const values:Record<string,string>={work_ref:payload.selection.work_ref};
 if("instruction_ref" in payload.selection)values.instruction_ref=payload.selection.instruction_ref;
 if(payload.command_id!==undefined)values.command_id=payload.command_id;
 return new URLSearchParams(values).toString();
}
const METHODS={content:"readProjectInstructions",current:"readInstructionAdmissionControl",pause:"pauseInstructionAdmission",status:"readInstructionAdmissionOperation"} as const;
type Client=Partial<InstructionRawMethods>&{getState():AuthState;invalidationGeneration?():number};
export function instructionHostMethods(client:Client,hostEpoch:()=>number):Partial<InstructionHostMethods>{
 const getState=client.getState,generation=client.invalidationGeneration;
 if(typeof generation!=="function")return {};
 const result:Partial<InstructionHostMethods>={};
 for(const mode of ["content","current","pause","status"] as const){
  const name=METHODS[mode],method=client[name];if(typeof method!=="function")continue;
  const call=async(request:InstructionContentRequest|InstructionControlRequest)=>{
   const payload=instructionPublicRequest(mode,request);if(!payload)throw Error("INSTRUCTION_REQUEST_INVALID");
   const signal=request.signal,epoch=hostEpoch(),ticket=generation.call(client);
   const qualified=()=>{
    try{const auth=getState.call(client);return !signal.aborted&&epoch===hostEpoch()&&client.getState===getState&&client.invalidationGeneration===generation
     &&client[name]===method&&ticket===generation.call(client)&&Number.isSafeInteger(ticket)&&ticket>=0&&auth.status==="signed_in"&&auth.acquisition;}catch{return false;}
   };
   if(!qualified())throw Error("INSTRUCTION_UNAUTHORIZED");
   const raw=await (method as (request:unknown)=>Promise<unknown>).call(client,{...payload,signal});
   if(!qualified())throw Error("INSTRUCTION_AUTH_CHANGED");
   const selected=payload.selection as InstructionAdmissionSelection;
   const body=mode==="content"?decodeStandingInstructions(raw,payload.selection):mode==="current"?decodeInstructionAdmissionControl(raw,selected):decodeInstructionAdmissionResult(raw,{...selected,command_id:payload.command_id!},mode);
   if(!body)throw Error("INSTRUCTION_RESPONSE_INVALID");
   return body;
  };
  Object.assign(result,{[name]:call});
 }
 return result;
}
