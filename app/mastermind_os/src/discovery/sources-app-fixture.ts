/** Whole canonical installed-source sequence reused without row/body changes.
 * Native/auth is inert; actual NativeClient, host and IndexedDB composition. */
import {createNativeClient} from '../host';
import {composeMissionHost} from '../compose-mission-host';
import {decodeLaunchBindingConfig} from '../launch-config';
import source from '../fixtures/knowledge-memory-source.json';
export const sourcesWorkRef=source.request.work_ref;
export const sourcesTitle=source.programs.control_room.work.find(row=>row.work_ref===sourcesWorkRef)!.agent_os.title;
export async function createSourcesAppFixture(database:IDBFactory){
 const calls:{command:string;args:unknown}[]=[],events=new Map<string,Set<(event:{payload:unknown})=>void>>();
 const invoke=async(command:string,args?:Record<string,unknown>):Promise<unknown>=>{
  calls.push({command,args});
  if(command==='auth_status')return{status:'signed_in',reason:null,acquisition:true,content:false};
  if(command==='executive_auth_status')return{generation:0,available:false};
  if(command==='terminal_session_status')return{state:'SIGNED_OUT',generation:0,available:false,reason:'FIXTURE_NOT_CONNECTED',principal_scope:null,session_scope:null};
  if(command==='read_programs')return structuredClone(source.programs);
  if(command==='read_project_knowledge_catalogue')return structuredClone(source.before);
  if(command==='read_project_knowledge_memory')return structuredClone(source.memory_before);
  if(command==='read_project_knowledge_source'){
   const selection=args?.selection as Record<string,unknown>;
   const body=[source.source_before,source.file_before].find(item=>item.selection.source_ref===selection.source_ref&&item.source.revision===selection.expected_revision);
   if(selection.work_ref!==sourcesWorkRef||!body)throw Error('Source selector not in the actual original catalogue');
   return structuredClone(body);
  }
  throw Error('No other source or command capability supplied');
 };
 const client=await createNativeClient(invoke as never,async(name,fn)=>{const set=events.get(name)??new Set();set.add(fn);events.set(name,set);return()=>set.delete(fn);});
 const config=decodeLaunchBindingConfig(JSON.stringify({v:1,workstream:'WS:EXECUTIVE-ECOSYSTEM-COMPLETION',priority:0,attemptLimit:1,
  projects:[{ref:'executive-infrastructure',label:'Infrastructure'}],profiles:[{ref:'research_only',label:'Research'}]}))!;
 const composed=composeMissionHost(client,config,database,'native');await composed.ready;await composed.sessionReady;
 return{...composed,calls,notify:(name:string,payload:unknown)=>events.get(name)?.forEach(fn=>fn({payload}))};
}
