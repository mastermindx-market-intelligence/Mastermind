import type {SessionSendArguments} from './executive-session-command-port';
/** Data closure only. Actual current target, identity, send scope and epoch
 * remain the incumbent Session/Executive owners' responsibility. */
export function sessionSendArguments(raw:unknown):SessionSendArguments|null{
 try{
  if(!raw||typeof raw!=='object'||Array.isArray(raw))return null;
  const v=raw as Record<string,unknown>;
  if(Object.keys(v).sort().join(',')!=='instruction,operation_key,stop_condition,target_ref')return null;
  const exact=(s:unknown,re:RegExp)=>typeof s==='string'&&re.exec(s)?.[0]===s;
  if(!exact(v.target_ref,/^(?:fabric_attempt|hermes_secretary|hermes_meta):[0-9a-f]{64}$/)||!exact(v.operation_key,/^session-continue-[0-9a-f]{64}$/))return null;
  for(const text of [v.instruction,v.stop_condition])if(typeof text!=='string'||!text.trim()||Array.from(text).length>700)return null;
  return {target_ref:v.target_ref as string,operation_key:v.operation_key as string,instruction:v.instruction as string,stop_condition:v.stop_condition as string};
 }catch{return null;}
}
