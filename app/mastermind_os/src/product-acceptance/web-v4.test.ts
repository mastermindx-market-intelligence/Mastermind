// @vitest-environment jsdom
// @vitest-environment-options {"url":"https://mcp.mastermind-x.com/os/"}
import { afterEach, describe, expect, it, vi } from "vitest";
import { createWebAuth } from "../web-auth";
import { ORIGIN } from "../public-config";
import fixture from "../fixtures/mission-v4-owner-accepted.json";
const selected={workRef:fixture.product_acceptance.selection.work_ref,rootJobId:fixture.product_acceptance.selection.root_job_id,requestMessageKey:fixture.product_acceptance.selection.request_message_key};
const flush=async()=>{for(let n=0;n<30;n++)await Promise.resolve();};
const response=(value:unknown)=>new Response(JSON.stringify(value),{headers:{"content-type":"application/json"}});
function setup(attached=true){
 vi.useFakeTimers();let value:unknown={selector:selected,principalScope:"inert-fixture",ownerGeneration:1,selectionGeneration:1},count=0;
 const callbacks=new Set<(e:MessageEvent)=>void>(), observers=new Set<()=>void>();
 const owner={getSnapshot:()=>value,subscribe:(fn:()=>void)=>{observers.add(fn);return()=>{observers.delete(fn);};}};
 const popup={location:"",closed:false,close:vi.fn()};
 const fetcher=vi.fn<typeof fetch>(async()=>response({token_type:"Bearer",access_token:"inert-fixture-token",expires_in:3600,scope:new URL(popup.location).searchParams.get("scope")}));
 const client=createWebAuth({productAcceptanceOwner:attached?owner:undefined,config:{webClientId:"inert-public-client"},fetchFn:fetcher,openPopup:()=>popup,
  crypto:{getRandomValues(a:Uint8Array){a.fill(++count);return a;},subtle:{digest:async()=>new ArrayBuffer(32)}} as unknown as Crypto,
  addEventListener:((_t:string,f:(e:MessageEvent)=>void)=>callbacks.add(f)) as typeof window.addEventListener,
  removeEventListener:((_t:string,f:(e:MessageEvent)=>void)=>callbacks.delete(f)) as typeof window.removeEventListener});
 const callback=()=>{for(const fn of [...callbacks])fn({source:popup,origin:ORIGIN,data:{type:"mastermind-auth-callback",state:new URL(popup.location).searchParams.get("state"),code:"inert-code"}} as unknown as MessageEvent);};
 const login=async()=>{const pending=client.signIn();await flush();callback();await flush();callback();await pending;fetcher.mockClear();fetcher.mockResolvedValue(response(fixture));};
 return{client,owner,fetcher,login,set:(next:unknown)=>{value=next;for(const fn of [...observers])fn();}};
}
afterEach(()=>{vi.useRealTimers();vi.restoreAllMocks();});
describe("fixed authenticated browser v4 read",()=>{
 it("leaves the production default port absent",()=>{const e=setup(false);expect(e.client.readMissionV4).toBeUndefined();expect(e.client.productAcceptanceOwner).toBeUndefined();expect(e.fetcher).not.toHaveBeenCalled();});
 it("uses exactly the existing three-key GET with the private acquisition token",async()=>{const e=setup();await e.login();await e.client.readMissionV4!({...selected,signal:new AbortController().signal});expect(e.fetcher).toHaveBeenCalledTimes(1);const [url,options]=e.fetcher.mock.calls[0];const u=new URL(String(url));expect(u.origin).toBe(ORIGIN);expect(u.pathname).toBe("/workspace/mission/v4/current");expect([...u.searchParams]).toEqual([["work_ref",selected.workRef],["root_job_id",selected.rootJobId],["request_message_key",selected.requestMessageKey]]);expect(options?.method??"GET").toBe("GET");expect(options?.body).toBeUndefined();expect(JSON.stringify(e.client)).not.toContain("inert-fixture-token");});
 it.each(["null","foreign","malformed","extra"])("never calls HTTP for %s selector/owner",async defect=>{const e=setup();await e.login();if(defect==="null")e.set(null);if(defect==="foreign")e.set({selector:{...selected,rootJobId:"JOB-999"},principalScope:"inert",ownerGeneration:1,selectionGeneration:1});if(defect==="malformed")e.set({selector:selected});const request={...selected,signal:new AbortController().signal,...(defect==="extra"?{extra:1}:{})};await expect(e.client.readMissionV4!(request)).rejects.toThrow();expect(e.fetcher).not.toHaveBeenCalled();});
 it("does not read before sign-in",async()=>{const e=setup();await expect(e.client.readMissionV4!({...selected,signal:new AbortController().signal})).rejects.toThrow();expect(e.fetcher).not.toHaveBeenCalled();});
 it.each(["ownerABA","signOut","abort"])("withholds response after %s even if fetch ignores abort",async defect=>{const e=setup();await e.login();let settle!:(v:Response)=>void;const pending=new Promise<Response>(r=>settle=r);e.fetcher.mockImplementationOnce(()=>pending);const abort=new AbortController();const result=e.client.readMissionV4!({...selected,signal:abort.signal});const assertion=expect(result).rejects.toThrow();await flush();if(defect==="ownerABA"){e.set(null);e.set({selector:selected,principalScope:"inert-fixture",ownerGeneration:1,selectionGeneration:1});}if(defect==="signOut")await e.client.signOut();if(defect==="abort")abort.abort();settle(response(fixture));await assertion;});
});
