import { describe, expect, it, vi } from "vitest";
import { bindMissionHost, type AuthState, type RawClient } from "../host";
import { composeMissionHost } from "../compose-mission-host";
import fixture from "../fixtures/mission-v4-owner-accepted.json";
import { guardAcceptanceRead, missionV4Selection, ownerObservation } from "./owner-observation";
const selected = { workRef: fixture.product_acceptance.selection.work_ref, rootJobId: fixture.product_acceptance.selection.root_job_id, requestMessageKey: fixture.product_acceptance.selection.request_message_key };
const snapshot = () => ({ selector: {...selected}, principalScope: "fixture-owner", ownerGeneration: 1, selectionGeneration: 1 });
function setup() {
  let value: unknown = snapshot(), generation=1;
  let state: AuthState = {status:"signed_in", acquisition:true, content:true, reason:null};
  const listeners=new Set<()=>void>(), authListeners=new Set<(s:AuthState)=>void>();
  const owner={getSnapshot:()=>value, subscribe:(fn:()=>void)=>{listeners.add(fn);return()=>{listeners.delete(fn);};}};
  const read=vi.fn(async()=>structuredClone(fixture));
  const client:RawClient={productAcceptanceOwner:owner,readMissionV4:read,getState:()=>state,invalidationGeneration:()=>generation,
    subscribe:fn=>{authListeners.add(fn);return()=>{authListeners.delete(fn);};},signIn:async()=>{},signOut:async()=>{},
    readPrograms:async()=>null,readWork:async()=>null,readMission:async()=>null,readCurrentWindow:async()=>null};
  return {client,owner,read,host:bindMissionHost(client),set:(next:unknown,notify=true)=>{value=next;if(notify)for(const f of [...listeners])f();},
    auth:(next:AuthState,notify=true)=>{state=next;generation++;if(notify)for(const f of [...authListeners])f(state);},listenerCount:()=>listeners.size};
}
const request=()=>({...selected,signal:new AbortController().signal});
const deferred=()=>{let resolve!:(v:typeof fixture)=>void;const promise=new Promise<typeof fixture>(r=>resolve=r);return{promise,resolve};};
describe("owner-bound v4 host read",()=>{
 it("keeps default raw client uncomposed through the existing composition",()=>{const e=setup();Object.assign(e.client,{productAcceptanceOwner:undefined});const c=composeMissionHost(e.client);expect(c.host.readMissionV4).toBeUndefined();expect(c.host.productAcceptanceOwner).toBeUndefined();c.dispose();});
 it("passes the same real attachment through existing composition",()=>{const e=setup();const c=composeMissionHost(e.client);expect(c.host.productAcceptanceOwner).toBe(e.owner);c.dispose();});
 it("decodes the existing exact parent-consumed receipt",async()=>{const e=setup();expect(await e.host.readMissionV4!(request())).toEqual(fixture);expect(e.read).toHaveBeenCalledTimes(1);expect(e.listenerCount()).toBe(0);});
 it.each([null,{}, {...snapshot(),extra:1}, {...snapshot(),ownerGeneration:-1}, {...snapshot(),principalScope:""}, {...snapshot(),selector:{...selected,requestMessageKey:"bad"}}, {...snapshot(),selector:{...selected,workRef:"WS:FOREIGN"}}])("refuses missing/foreign/malformed owner before the underlying read: %j",async value=>{const e=setup();e.set(value);await expect(e.host.readMissionV4!(request())).rejects.toThrow();expect(e.read).not.toHaveBeenCalled();});
 it("rejects surplus selector fields",async()=>{const e=setup();await expect(e.host.readMissionV4!({...request(),extra:1} as never)).rejects.toThrow("SELECTION_INVALID");expect(e.read).not.toHaveBeenCalled();});
 it.each(["ownerGeneration","selectionGeneration","principalScope","notificationABA","silentMutation","ownerReplacement","authABA","silentAuthGeneration","abort"])("discards old result after %s",async kind=>{
  const e=setup(),p=deferred(),abort=new AbortController();e.read.mockImplementationOnce(()=>p.promise);
  const result=e.host.readMissionV4!({...selected,signal:abort.signal});
  if(kind==="notificationABA"){e.set(null);e.set(snapshot());}
  else if(kind==="ownerReplacement"){Object.assign(e.client,{productAcceptanceOwner:{...e.owner}});}
  else if(kind==="authABA"){e.auth({status:"signed_out",acquisition:false,content:false,reason:null});e.auth({status:"signed_in",acquisition:true,content:true,reason:null});}
  else if(kind==="silentAuthGeneration")e.auth({status:"signed_in",acquisition:true,content:true,reason:null},false);
  else if(kind==="abort")abort.abort();
  else if(kind==="silentMutation")e.set({...snapshot(),ownerGeneration:2},false);
  else e.set({...snapshot(),[kind]:kind==="principalScope"?"different-owner":2});
  p.resolve(structuredClone(fixture));await expect(result).rejects.toThrow("READ_CANCELLED");expect(e.listenerCount()).toBe(0);
 });
 it("withholds a forged accepted receipt even through a typed raw client",async()=>{const e=setup();const f=structuredClone(fixture);f.product_acceptance.receipt.parent_result_envelope_digest="f".repeat(64);e.read.mockResolvedValueOnce(f);await expect(e.host.readMissionV4!(request())).rejects.toThrow("MISSION_V4_RESPONSE_INVALID");});
 it("does not infer a selection or treat an unavailable parent as accepted",async()=>{const e=setup();const f:any=structuredClone(fixture);f.product_acceptance={...f.product_acceptance,state:"UNAVAILABLE",receipt:null,reason_codes:["PARENT_CONSUMPTION_UNPROVEN"]};e.read.mockResolvedValueOnce(f);expect((await e.host.readMissionV4!(request()) as any).product_acceptance.state).toBe("UNAVAILABLE");});
 it("handles throwing snapshot getters without acquisition",()=>{const owner={getSnapshot(){throw Error("missing");},subscribe:()=>()=>{}};expect(ownerObservation(owner)).toBeNull();expect(()=>guardAcceptanceRead(owner,selected,()=>true)).toThrow();});
 it("requires a closed exact three-key selector",()=>{expect(missionV4Selection({...selected,signal:{}})).toBeNull();expect(missionV4Selection(selected)).toEqual(selected);});
});
