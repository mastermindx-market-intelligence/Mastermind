// @vitest-environment jsdom
import {afterEach,expect,it,vi} from "vitest";
import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {useEffect,useState} from "react";
import {bindMissionHost,createNativeClient,type AuthState,type MissionHost,type RawClient} from "./host";
import {NativePrimaryAccountControl} from "./NativePrimaryAccountControl";
import fixture from "./fixtures/native-session-send-producer.json";
const out:AuthState={status:"signed_out",reason:null,acquisition:false,content:false};
const pending:AuthState={...out,status:"signing_in"};
const signed:AuthState={...out,status:"signed_in",acquisition:true,content:true};
afterEach(()=>{cleanup();delete window.MastermindMissionHost;});
async function setup(action:()=>Promise<unknown>=async()=>pending){
 const events=new Map<string,(e:{payload:unknown})=>void>();
 const invoke=vi.fn(async(command:string)=>{
  if(command==="executive_auth_status")return {generation:1,available:false};
  if(command==="auth_status"||command==="sign_out")return out;
  if(command==="sign_in_primary")return action();throw Error("UNEXPECTED_NATIVE_COMMAND");
 });
 const raw=await createNativeClient(invoke as never,async(name,fn)=>{events.set(name,fn as never);return()=>{};});
 const host=bindMissionHost(raw);window.MastermindMissionHost=host;return {raw,host,invoke,events};
}
function Surface({host,before}:{host:MissionHost;before?:()=>void}){
 const [state,setState]=useState(host.auth!.getState());useEffect(()=>host.auth!.subscribe(setState),[host]);
 return <NativePrimaryAccountControl host={host} state={state} locale="en" beforeSignIn={before}/>;
}
it("explicit gesture invokes only zero-input primary through actual NativeClient/Host/control",async()=>{
 const x=await setup(),before=vi.fn();render(<Surface host={x.host} before={before}/>);
 expect(x.invoke.mock.calls.filter(c=>c[0].startsWith("sign_in"))).toHaveLength(0);
 expect(screen.getByText("Account access only. Work needs separate authorization.")).toBeTruthy();
 fireEvent.click(screen.getByRole("button"));await waitFor(()=>expect(before).toHaveBeenCalledTimes(1));
 await waitFor(()=>expect(x.invoke.mock.calls.filter(c=>c[0]==="sign_in_primary")).toEqual([["sign_in_primary"]]));
 expect(x.invoke.mock.calls.filter(c=>c[0]==="sign_in")).toHaveLength(0);
});
it("missing primary facet never falls back to generic full Sign in",async()=>{
 const x=await setup();delete x.raw.signInPrimary;const host=bindMissionHost(x.raw);window.MastermindMissionHost=host;
 render(<Surface host={host}/>);const button=screen.getByRole("button") as HTMLButtonElement;
 expect(button.disabled).toBe(true);fireEvent.click(button);expect(screen.getByText("Account sign-in is unavailable here.")).toBeTruthy();
 expect(x.invoke.mock.calls.filter(c=>c[0].startsWith("sign_in"))).toHaveLength(0);
});
it.each(["host","owner","method","auth","epoch"] as const)("no-render %s withdrawal refuses stale gesture",async kind=>{
 const x=await setup();render(<Surface host={x.host}/>);
 if(kind==="host")window.MastermindMissionHost={...x.host};
 else if(kind==="owner")(x.host as {primaryAccount?:unknown}).primaryAccount={signIn:vi.fn()};
 else if(kind==="method")x.host.primaryAccount!.signIn=vi.fn();
 else if(kind==="auth")x.host.auth!.getState=()=>out;
 else (x.host as {invalidationGeneration?:()=>number}).invalidationGeneration=()=>99;
 fireEvent.click(screen.getByRole("button"));expect(x.invoke.mock.calls.filter(c=>c[0].startsWith("sign_in"))).toHaveLength(0);
});
it("duplicate gestures retain one original handoff",async()=>{
 let finish!:(v:unknown)=>void;const held=new Promise(r=>{finish=r;});const x=await setup(()=>held);render(<Surface host={x.host}/>);
 fireEvent.click(screen.getByRole("button"));fireEvent.click(screen.getByRole("button"));
 await waitFor(()=>expect(x.invoke.mock.calls.filter(c=>c[0]==="sign_in_primary")).toHaveLength(1));
 await expect(x.raw.signInPrimary!()).rejects.toThrow("PRIMARY_AUTH_PENDING");finish(pending);
});
it("lost handoff remains unconfirmed without owner/raw retry",async()=>{
 const x=await setup(async()=>{throw Error("inert lost reply");});render(<Surface host={x.host}/>);fireEvent.click(screen.getByRole("button"));
 await screen.findByText(/handoff is unconfirmed/);expect((screen.getByRole("button") as HTMLButtonElement).disabled).toBe(true);
 await expect(x.host.primaryAccount!.signIn()).rejects.toThrow("PRIMARY_AUTH_UNAVAILABLE");
 await expect(x.raw.signInPrimary!()).rejects.toThrow("PRIMARY_AUTH_PENDING");
 expect(x.invoke.mock.calls.filter(c=>c[0]==="sign_in_primary")).toHaveLength(1);
});
it("late primary reply after native auth withdrawal cannot replace current state",async()=>{
 let finish!:(v:unknown)=>void;const held=new Promise(r=>{finish=r;});const x=await setup(()=>held);
 const original=x.raw.signInPrimary!();x.events.get("mastermind-auth-state")!({payload:{...out,reason:"USER_SIGNED_OUT"}});
 finish(pending);await original;expect(x.raw.getState()).toEqual({...out,reason:"USER_SIGNED_OUT"});
});
it("primary entry withdraws old Executive transport before dispatch without an event",async()=>{
 let raw!:RawClient;let check:Promise<unknown>|undefined;
 const invoke=vi.fn(async(command:string)=>{
  if(command==="executive_auth_status")return {generation:1,available:true};if(command==="auth_status")return signed;
  if(command==="sign_in_primary"){
   check=raw.executiveSession!.send!(fixture.arguments,new AbortController().signal).then(()=>"unexpected",e=>(e as Error).message);
   return pending;
  }throw Error("UNEXPECTED_NATIVE_COMMAND");
 });
 raw=await createNativeClient(invoke as never,async()=>()=>{});await raw.signInPrimary!();
 expect(await check).toBe("EXECUTIVE_UNAVAILABLE");expect(invoke.mock.calls.filter(c=>c[0]==="executive_session_send")).toHaveLength(0);
});
