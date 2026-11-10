import {expect,it,vi} from "vitest";
import {bindMissionHost,createNativeClient} from "./host";
import fixture from "./resources/fixtures/recorded-host-observation-owner.json";
async function setup(held=false){
 const events=new Map<string,(event:{payload:unknown})=>void>();let finish!:(value:unknown)=>void;
 const pending=new Promise(resolve=>{finish=resolve;});
 const invoke=vi.fn(async(name:string)=>name==="auth_status"?{status:"signed_in",reason:null,acquisition:true,content:false}:
  name==="executive_auth_status"?{generation:0,available:false}:name==="read_host_observation"?(held?pending:structuredClone(fixture)):
  Promise.reject(Error("Unlisted native fixture command")));
 const raw=await createNativeClient(invoke as never,async(name,listener)=>{events.set(name,listener);return()=>{};});
 return {raw,host:bindMissionHost(raw),invoke,events,finish};
}
it("joins recorded original-work observation through real native client and typed Host without automatic acquisition",async()=>{
 const e=await setup(),signal=new AbortController().signal;
 expect(e.invoke.mock.calls.filter(([name])=>name==="read_host_observation")).toHaveLength(0);
 const result=await e.host.readHostObservation!({selection:fixture.selection,signal});
 expect(result.state).toBe("AVAILABLE");if(result.state==="AVAILABLE")expect(result.document).toEqual(fixture.observation);
 expect(e.invoke.mock.calls.at(-1)).toEqual(["read_host_observation",{selection:fixture.selection}]);
 const getter=vi.fn(()=>fixture.selection);
 await expect(e.host.readHostObservation!(Object.defineProperty({signal},"selection",{get:getter,enumerable:true}) as never)).rejects.toThrow("HOST_OBSERVATION_REQUEST_INVALID");
 expect(getter).not.toHaveBeenCalled();
 expect(e.invoke.mock.calls.filter(([name])=>name==="read_host_observation")).toHaveLength(1);
});
it("withholds an in-flight recorded observation after actual native authentication loss without repeating it",async()=>{
 const e=await setup(true),signal=new AbortController().signal;
 const pending=e.host.readHostObservation!({selection:fixture.selection,signal}),rejected=expect(pending).rejects.toThrow();
 e.events.get("mastermind-auth-state")!({payload:{status:"signed_out",reason:null,acquisition:false,content:false}});
 e.finish(fixture);await rejected;
 expect(e.invoke.mock.calls.filter(([name])=>name==="read_host_observation")).toHaveLength(1);
});
