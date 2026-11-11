import type {MissionHost} from '../host';
import type {OwnerContext} from '../orchestration/operation-controller';
import {completeExecutiveSessionBinding,readSessionOwnerContext} from '../orchestration/os-executive-session-host';
/** Existing authenticated E READ owner; no target or SEND capability is
 * inferred. Private own-text/original observation may outlive Workspace
 * expiry, while all actual actions retain their independent resource gates. */
export function createSessionExecutiveOwnerGetter(input:{host:MissionHost|null;native:boolean;authRevision:number;currentAuthRevision:()=>number}):()=>OwnerContext|null{
  const {host,native,authRevision,currentAuthRevision}=input;
  const binding=completeExecutiveSessionBinding(host?.sessionCommandBinding),context=binding?.port.context;
  const auth=host?.auth,state=auth?.getState,source=host?.invalidationGeneration;
  let generation:number|null=null;try{const value=source?.call(host);if(typeof value==='number'&&Number.isSafeInteger(value)&&value>=0)generation=value;}catch{/* closed */}
  const current=()=>{
    if(!host||!binding||!context||!auth||!state||generation===null||window.MastermindMissionHost!==host||
      currentAuthRevision()!==authRevision||host.auth!==auth||auth.getState!==state||host.invalidationGeneration!==source||
      source?.call(host)!==generation||host.sessionCommandBinding!==binding||binding.port.context!==context)return false;
    const value=state.call(auth);
    return value.status==='signed_in'||native&&value.status==='signed_out'&&value.reason!=='USER_SIGNED_OUT';
  };
  return ()=>{try{if(!current())return null;const owner=readSessionOwnerContext(binding!);return owner&&current()?owner:null;}catch{return null;}};
}
