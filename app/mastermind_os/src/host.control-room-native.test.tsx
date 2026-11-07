// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import { createNativeClient, bindMissionHost, type AuthState } from "./host";
import fixture from "./fixtures/native-wire/control-room-state-source.json";
const signed: AuthState = {status:"signed_in",reason:null,acquisition:true,content:false};
const source = () => structuredClone(fixture.samples[0].response.body);
function deferred<T>() {
  let resolve!: (value:T)=>void;
  const promise = new Promise<T>(yes=>{resolve=yes;});
  return {promise,resolve};
}
async function harness(state:AuthState=signed, read:()=>Promise<unknown>=async()=>source()) {
  const listeners=new Map<string,(event:{payload:unknown})=>void>();
  const invoke=vi.fn(async(command:string,..._args:unknown[])=>{
    if(command==="auth_status") return state;
    if(command==="executive_auth_status") return {available:false,generation:0};
    if(command==="read_control_room_state") return read();
    throw Error("UNCOMMISSIONED_FIXTURE_COMMAND");
  });
  const client=await createNativeClient(invoke as never,async(event,listener)=>{
    listeners.set(event,listener);return()=>{listeners.delete(event);};
  });
  return {client,host:bindMissionHost(client),invoke,
    auth:(next:AuthState)=>listeners.get("mastermind-auth-state")!({payload:next}),
    calls:()=>invoke.mock.calls.filter(([command])=>command==="read_control_room_state")};
}
describe("fixed native Control Room inventory read",()=>{
  it("makes the real native facet available and decodes the source-issued same-cache response",async()=>{
    const h=await harness();
    expect(h.client.readControlRoomState).toBeTypeOf("function");
    const result=await h.host.readControlRoomState!({signal:new AbortController().signal});
    expect(result.state).toBe("AVAILABLE");
    expect(result.navigation.state).toBe("AVAILABLE");
    if(result.navigation.state!=="AVAILABLE") throw Error("NAVIGATION_UNAVAILABLE");
    expect(result.navigation.capabilities.codex?.state).toBe("NOT_INSTALLED");
    expect(result.navigation.capabilities.aionui?.state).toBe("UNSUPPORTED");
    expect(h.calls()).toEqual([["read_control_room_state",undefined]]);
    expect(h.invoke.mock.calls.some(([name])=>/discover|bind|open_control|capacity|host_observation/.test(name))).toBe(false);
  });
  it.each([
    {...signed,status:"signed_out",acquisition:false} as AuthState,
    {...signed,acquisition:false},
  ])("withholds the fixed command without current native acquisition",async state=>{
    const h=await harness(state);
    await expect(h.host.readControlRoomState!({signal:new AbortController().signal})).rejects.toThrow("CONTROL_ROOM_READ_UNAUTHORIZED");
    expect(h.calls()).toHaveLength(0);
  });
  it("aborted input never dispatches",async()=>{
    const h=await harness(),control=new AbortController();control.abort();
    await expect(h.host.readControlRoomState!({signal:control.signal})).rejects.toThrow("READ_CANCELLED");
    expect(h.calls()).toHaveLength(0);
  });
  it.each(["abort","same-label-auth"])("withholds late source after %s without resubmitting",async kind=>{
    const pending=deferred<unknown>(),h=await harness(signed,()=>pending.promise),control=new AbortController();
    const result=h.host.readControlRoomState!({signal:control.signal});
    const refused=expect(result).rejects.toThrow("READ_CANCELLED");
    if(kind==="abort")control.abort();else h.auth({...signed});
    pending.resolve(source());await refused;
    expect(h.calls()).toHaveLength(1);
  });
  it("refuses a foreign body through the existing closed decoder",async()=>{
    const h=await harness(signed,async()=>({...source(),host_ref:"foreign"}));
    await expect(h.host.readControlRoomState!({signal:new AbortController().signal})).rejects.toThrow("CONTROL_ROOM_RESPONSE_INVALID");
    expect(h.calls()).toHaveLength(1);
  });
  it.each(["ACCESS_REFUSED","SOURCE_UNAVAILABLE"])("propagates native %s without fallback/action",async reason=>{
    const h=await harness(signed,async()=>{throw Error(reason);});
    await expect(h.host.readControlRoomState!({signal:new AbortController().signal})).rejects.toThrow(reason);
    expect(h.calls()).toHaveLength(1);
    expect(h.invoke.mock.calls.map(([name])=>name).filter(name=>name!=="auth_status"&&name!=="executive_auth_status")).toEqual(["read_control_room_state"]);
  });
});
