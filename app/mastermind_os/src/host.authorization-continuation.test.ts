import {expect,it,vi} from "vitest";
import {createNativeClient,bindMissionHost} from "./host";
const state={status:"error",reason:"AUTH_TRANSACTION_EXPIRED",acquisition:true,content:false};
const yes={schema:"mastermind.native_authorization_continuation.v1",state:"ELIGIBLE",resource:"CONTENT",reason:"CONTENT_PENDING_TIMEOUT"};
async function fixture(read:()=>Promise<unknown>=async()=>yes, command:()=>Promise<unknown>=async()=>({...state,status:"signing_in",reason:null})) {
 const continueCommand=command;
 const calls=vi.fn(async (command:string,args?:unknown) => {
  if(command==="auth_status")return state;
  if(command==="executive_auth_status")return {generation:1,available:false};
  if(command==="read_authorization_continuation")return read();
  if(command==="continue_authorization")return continueCommand();
  throw new Error("UNEXPECTED_COMMAND");
 });
 const events=new Map<string,(event:{payload:unknown})=>void>();
 const client=await createNativeClient(calls as never,async(name,handler)=>{events.set(name,handler);return()=>{};});return {client,calls,host:bindMissionHost(client),emit:(payload:unknown)=>events.get("mastermind-auth-state")!({payload})};
}
it("uses only fixed zero-input metadata/command and requires freshly qualified same-source eligibility",async()=>{
 const f=await fixture(), o=f.host.authorizationContinuation!;
 await expect(o.continue()).rejects.toThrow("AUTH_CONTINUATION_INELIGIBLE");
 expect(await o.read({signal:new AbortController().signal})).toEqual(yes);
 await o.continue();expect(f.client.getState()).toEqual({...state,status:"signing_in",reason:null});
 expect(f.calls.mock.calls.filter(([name])=>name==="continue_authorization")).toEqual([["continue_authorization"]]);
 expect(f.calls.mock.calls.find(([name])=>name==="read_authorization_continuation")).toEqual(["read_authorization_continuation",undefined]);
 await expect(o.continue()).rejects.toThrow();expect(f.calls.mock.calls.filter(([name])=>name==="continue_authorization")).toHaveLength(1);
});
it("rejects malformed capability and same-owner method substitution before invoking any command",async()=>{
 const bad=await fixture(async()=>({...yes,allow:true}));await expect(bad.host.authorizationContinuation!.read({signal:new AbortController().signal})).rejects.toThrow("RESPONSE_INVALID");
 const f=await fixture(),o=f.host.authorizationContinuation!;await o.read({signal:new AbortController().signal});
 f.client.continueAuthorization=vi.fn();await expect(o.continue()).rejects.toThrow();expect(f.client.continueAuthorization).not.toHaveBeenCalled();
});
it("discards a late capability after source-generation replacement",async()=>{
 let finish!:(value:unknown)=>void;const f=await fixture(()=>new Promise(resolve=>{finish=resolve;}));
 const pending=f.host.authorizationContinuation!.read({signal:new AbortController().signal});
 f.client.invalidationGeneration=()=>99;finish(yes);await expect(pending).rejects.toThrow("AUTHENTICATION_CHANGED");
 await expect(f.host.authorizationContinuation!.continue()).rejects.toThrow();expect(f.calls.mock.calls.some(([n])=>n==="continue_authorization")).toBe(false);
});

it("never restores a revoked Acquisition from a late command result or duplicates an unresolved handoff",async()=>{
 let finish!:(value:unknown)=>void;const f=await fixture(async()=>yes,()=>new Promise(resolve=>{finish=resolve;}));const o=f.host.authorizationContinuation!;
 await o.read({signal:new AbortController().signal});const pending=o.continue();
 await expect(f.client.continueAuthorization!()).rejects.toThrow("AUTH_CONTINUATION_INELIGIBLE");
 f.emit({status:"error",reason:"NATIVE_TOKEN_EXPIRED",acquisition:false,content:false});finish({...state,status:"signing_in",reason:null});await pending;
 expect(f.client.getState().acquisition).toBe(false);expect(f.calls.mock.calls.filter(([n])=>n==="continue_authorization")).toHaveLength(1);
});
it("cancels metadata locally and refuses a later continuation without claiming the native read was cancelled",async()=>{
 let finish!:(value:unknown)=>void;const f=await fixture(()=>new Promise(resolve=>{finish=resolve;}));const abort=new AbortController();
 const pending=f.host.authorizationContinuation!.read({signal:abort.signal});abort.abort();await expect(pending).rejects.toThrow();finish(yes);
 await expect(f.host.authorizationContinuation!.continue()).rejects.toThrow();expect(f.calls.mock.calls.some(([n])=>n==="continue_authorization")).toBe(false);
});

it("leaves old or unsupported clients without a continuation facet",async()=>{
 const f=await fixture();delete f.client.readAuthorizationContinuation;const host=bindMissionHost(f.client);expect(Object.hasOwn(host,"authorizationContinuation")).toBe(false);
 expect(f.calls.mock.calls.some(([n])=>n==="read_authorization_continuation"||n==="continue_authorization")).toBe(false);
});
