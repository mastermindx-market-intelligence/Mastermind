import {describe,expect,it} from 'vitest';
import {bindMissionHost,createNativeClient} from './host';
import {programsFromControlRoom} from './mission';
import actual from './fixtures/project-discovery-current-data.json';
const signed={status:'signed_in',reason:null,acquisition:true,content:true};
const selected={workRef:actual.programs.canonical_projects[0].work_ref,rootJobId:actual.mission.mission.root_job_id!};

describe('actual Programs DATA DTO through incumbent NativeClient and MissionHost',()=>{
  it('acquires the fixed Programs source, selects the real N card, and rereads the actual root without a write',async()=>{
    const calls:Array<{command:string,args:unknown}>=[];
    const invoke=async<T,>(command:string,args?:unknown):Promise<T>=>{
      calls.push({command,args});
      if(command==='auth_status'||command==='executive_auth_status')return structuredClone(signed) as T;
      if(command==='read_programs')return structuredClone(actual.programs) as T;
      if(command==='read_mission_v3')return structuredClone(actual.mission) as T;
      throw Error('unexpected effect');
    };
    const client=await createNativeClient(invoke,async()=>()=>{}),host=bindMissionHost(client);
    const snapshot=await host.readProgramsObservation!({signal:new AbortController().signal});
    expect(snapshot.controlRoom).toEqual(actual.programs.control_room);
    const index=programsFromControlRoom(snapshot.programsInput??snapshot.controlRoom);
    expect(index.state).toBe('AVAILABLE');
    expect(index.programs.find(row=>row.workRef===selected.workRef)).toMatchObject({rootJobId:selected.rootJobId,rootState:'RESOLVED'});
    const mission=await host.readMissionV3!({...selected,signal:new AbortController().signal});
    expect(mission).toMatchObject({program:{work_ref:selected.workRef},mission:{root_job_id:selected.rootJobId}});
    expect(calls.filter(call=>call.command==='read_mission_v3')).toEqual([{command:'read_mission_v3',args:{selection:{work_ref:selected.workRef,root_job_id:selected.rootJobId}}}]);
    expect(calls.every(call=>['executive_auth_status','auth_status','read_programs','read_mission_v3'].includes(call.command))).toBe(true);
  });
  it('withholds the complete C/N result after native auth invalidation even when the late result is valid',async()=>{
    let notify!:(event:{payload:unknown})=>void,resolve!:(value:unknown)=>void;
    const invoke=async<T,>(command:string):Promise<T>=>{
      if(command==='auth_status'||command==='executive_auth_status')return structuredClone(signed) as T;
      return new Promise<unknown>(value=>{resolve=value;}) as Promise<T>;
    };
    const client=await createNativeClient(invoke,async(_event,listener)=>{notify=listener;return()=>{};});
    const read=bindMissionHost(client).readProgramsObservation!({signal:new AbortController().signal});
    notify({payload:{...signed,status:'signed_out',acquisition:false,content:false}});
    resolve(actual.programs);
    await expect(read).rejects.toThrow('READ_CANCELLED');
  });
});
