/** Actual whole canonical source fixture; inert native/auth only. No write ports. */
import {createNativeClient} from '../host';
import {composeMissionHost} from '../compose-mission-host';
import {decodeLaunchBindingConfig} from '../launch-config';
import whole from '../fixtures/tools-whole-owner.json';
export const toolsWorkRef=whole.selection.work_ref;
export const toolsTitle=whole.programs.result.control_room.work.find(row=>row.work_ref===toolsWorkRef)!.agent_os.title;
export async function createToolsAppFixture(database:IDBFactory){
 const calls:{command:string;args:unknown}[]=[],events=new Map<string,Set<(e:{payload:unknown})=>void>>();
 const invoke=async(command:string,args?:unknown):Promise<unknown>=>{
  calls.push({command,args});
  if(command==='auth_status')return{status:'signed_in',reason:null,acquisition:true,content:false};
  if(command==='executive_auth_status')return{generation:0,available:false};
  if(command==='terminal_session_status')return{state:'SIGNED_OUT',generation:0,available:false,reason:'FIXTURE_NOT_CONNECTED',principal_scope:null,session_scope:null};
  if(command==='read_programs')return structuredClone(whole.programs.result);
  if(command==='read_mission_v3')return structuredClone(whole.mission.result);
  throw Error('Unowned fixture capability');
 };
 const client=await createNativeClient(invoke as never,async(name,fn)=>{const set=events.get(name)??new Set();set.add(fn);events.set(name,set);return()=>set.delete(fn);});
 const config=decodeLaunchBindingConfig(JSON.stringify({v:1,workstream:'WS:EXECUTIVE-ECOSYSTEM-COMPLETION',priority:0,attemptLimit:1,
  projects:[{ref:'executive-infrastructure',label:'Infrastructure'}],profiles:[{ref:'research_only',label:'Research'}]}))!;
 const composed=composeMissionHost(client,config,database,'native');await composed.ready;await composed.sessionReady;
 return{...composed,calls,notify:(name:string,payload:unknown)=>events.get(name)?.forEach(fn=>fn({payload}))};
}
