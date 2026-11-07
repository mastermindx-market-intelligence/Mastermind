/** Fixed project control API. Login/method presence never grants an action. */
import { decodeProjectAdmissionControl, validProjectAdmissionSelection, type ProjectAdmissionControl, type ProjectAdmissionSelection } from "./project-admission";
import type { AdmissionKind, PauseToken } from "./project-admission-command-port";
import type { AuthState } from "../host";
export type ProjectAdmissionMode="current"|"pause"|"resume"|"status";
export interface ProjectAdmissionReadRequest {selection:ProjectAdmissionSelection;signal:AbortSignal}
export interface ProjectAdmissionPauseRequest extends ProjectAdmissionReadRequest {command_id:string}
export interface ProjectAdmissionResumeRequest extends ProjectAdmissionPauseRequest {pause_token:PauseToken}
export interface ProjectAdmissionStatusRequest extends ProjectAdmissionPauseRequest {kind:AdmissionKind}
export interface ProjectAdmissionRawMethods {
 readProjectAdmissionControl(request:ProjectAdmissionReadRequest):Promise<unknown>;
 pauseProjectAdmission(request:ProjectAdmissionPauseRequest):Promise<unknown>;
 resumeProjectAdmission(request:ProjectAdmissionResumeRequest):Promise<unknown>;
 readProjectAdmissionOperation(request:ProjectAdmissionStatusRequest):Promise<unknown>;
}
export interface ProjectAdmissionHostMethods extends Omit<ProjectAdmissionRawMethods,"readProjectAdmissionControl"> {
 readProjectAdmissionControl(request:ProjectAdmissionReadRequest):Promise<ProjectAdmissionControl>;
}
export type ProjectAdmissionPublicRequest={selection:ProjectAdmissionSelection;command_id?:string;kind?:AdmissionKind;pause_token?:PauseToken};
function exact(value:unknown,keys:readonly string[]):value is Record<string,unknown>{
 if(typeof value!=="object" || value===null || Array.isArray(value))return false;
 const fields=Object.getOwnPropertyDescriptors(value);
 return Reflect.ownKeys(fields).length===keys.length && keys.every(key=>Object.hasOwn(fields,key)&&Object.hasOwn(fields[key],"value"));
}
export function projectAdmissionPublicRequest(mode:ProjectAdmissionMode,input:unknown):ProjectAdmissionPublicRequest|null{
 if(!["current","pause","resume","status"].includes(mode))return null;
 const keys=["selection","signal",...(mode==="current"?[]:["command_id"]),...(mode==="resume"?["pause_token"]:mode==="status"?["kind"]:[])];
 if(!exact(input,keys) || !validProjectAdmissionSelection(input.selection))return null;
 const selection={...input.selection};
 const kind=mode==="status"?input.kind:mode==="resume"?"project_resume":"project_pause";
 if(mode!=="current" && kind!=="project_pause" && kind!=="project_resume")return null;
 if(mode!=="current"){
  const prefix=kind==="project_resume"?"mmos-project-resume-":"mmos-project-pause-";
  if(typeof input.command_id!=="string" || new RegExp(`^${prefix}[0-9a-f]{40}$`).exec(input.command_id)?.[0]!==input.command_id)return null;
 }
 if(mode==="resume"){
  const token=input.pause_token;
  if(!exact(token,["event_id","receipt_digest"]) || typeof token.event_id!=="number" || !Number.isSafeInteger(token.event_id) || token.event_id<=0
   || typeof token.receipt_digest!=="string" || /^[0-9a-f]{64}$/.exec(token.receipt_digest)?.[0]!==token.receipt_digest)return null;
  return {selection,command_id:input.command_id as string,pause_token:{event_id:token.event_id,receipt_digest:token.receipt_digest}};
 }
 return {selection,...(mode!=="current"?{command_id:input.command_id as string}:{}),...(mode==="status"?{kind:kind as AdmissionKind}:{})};
}
const METHODS={current:"readProjectAdmissionControl",pause:"pauseProjectAdmission",resume:"resumeProjectAdmission",status:"readProjectAdmissionOperation"} as const;
type Client=Partial<ProjectAdmissionRawMethods>&{getState():AuthState;invalidationGeneration?():number};
/** Same host epoch + actual Acquisition client; original status does not read a gate. */
export function projectAdmissionHostMethods(client:Client,hostEpoch:()=>number):Partial<ProjectAdmissionHostMethods>{
 const generation=client.invalidationGeneration,getState=client.getState;
 if(typeof generation!=="function")return {};
 const result:Partial<ProjectAdmissionHostMethods>={};
 for(const mode of ["current","pause","resume","status"] as const){
  const name=METHODS[mode],method=client[name];if(typeof method!=="function")continue;
  const call=async(request:ProjectAdmissionReadRequest)=>{
   const payload=projectAdmissionPublicRequest(mode,request);if(!payload)throw new Error("PROJECT_ADMISSION_REQUEST_INVALID");
   const signal=request.signal,epoch=hostEpoch(),source=generation.call(client);
   const authorized=()=>{
    try {const auth=getState.call(client);return !signal.aborted && epoch===hostEpoch() && client.getState===getState
     && client.invalidationGeneration===generation && client[name]===method && source===generation.call(client)
     && Number.isSafeInteger(source) && source>=0 && auth.status==="signed_in" && auth.acquisition;}
    catch{return false;}
   };
   if(!authorized())throw new Error("PROJECT_ADMISSION_UNAUTHORIZED");
   const raw=await (method as (request:unknown)=>Promise<unknown>).call(client,{...payload,signal});
   if(!authorized())throw new Error("PROJECT_ADMISSION_AUTH_CHANGED");
   if(mode!=="current")return raw; // Sole finite port validates every action/status receipt before publication.
   const decoded=decodeProjectAdmissionControl(raw,payload.selection);if(!decoded)throw new Error("PROJECT_ADMISSION_RESPONSE_INVALID");
   return decoded;
  };
  Object.assign(result,{[name]:call});
 }
 return result;
}
export function projectAdmissionQuery(request:ProjectAdmissionPublicRequest):string{
 const values:Record<string,string>={work_ref:request.selection.work_ref};
 if(request.selection.root_job_id!==undefined)values.root_job_id=request.selection.root_job_id;
 if(request.command_id!==undefined)values.command_id=request.command_id;
 if(request.kind!==undefined)values.kind=request.kind;
 return new URLSearchParams(values).toString();
}
