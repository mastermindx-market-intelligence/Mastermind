// @vitest-environment jsdom
import {act,cleanup,fireEvent,render,screen,waitFor,within} from "@testing-library/react";
import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {App} from "./App";
import userEvent from "@testing-library/user-event";
import {createNativeClient} from "./host";
import {composeMissionHost} from "./compose-mission-host";
vi.mock("@tauri-apps/api/core",()=>({invoke:vi.fn(async()=>{throw new Error("INERT_READINESS_UNAVAILABLE");})}));
const partial={status:"error",reason:"AUTH_TRANSACTION_EXPIRED",acquisition:true,content:false};
const yes={schema:"mastermind.native_authorization_continuation.v1",state:"ELIGIBLE",resource:"CONTENT",reason:"CONTENT_PENDING_TIMEOUT"};
const no={...yes,state:"INELIGIBLE",resource:null,reason:"NOT_ELIGIBLE"};
let dispose=()=>{};
beforeEach(()=>{history.replaceState(null,"","/os/");localStorage.clear();delete window.MastermindMissionHost;Object.defineProperty(window,"__TAURI_INTERNALS__",{configurable:true,value:{}});});
afterEach(()=>{cleanup();dispose();dispose=()=>{};delete window.MastermindMissionHost;delete (window as unknown as Record<string,unknown>).__TAURI_INTERNALS__;vi.restoreAllMocks();});
async function mount(locale:"en"|"zh-CN"="en",eligible=true) {
 let capability=eligible?yes:no,finish!:(value:unknown)=>void,reject!:(value:unknown)=>void;
 const invoke=vi.fn(async(command:string):Promise<unknown>=>{
  if(command==="auth_status")return partial;
  if(command==="executive_auth_status")return {generation:1,available:false};
  if(command==="read_authorization_continuation")return capability;
  if(command==="continue_authorization")return new Promise((resolve,no)=>{finish=resolve;reject=no;});
  if(command==="read_programs"||command==="read_work")throw new Error("SOURCE_UNAVAILABLE");
  throw new Error("UNEXPECTED_NATIVE_COMMAND");
 });
 const events=new Map<string,(event:{payload:unknown})=>void>();
 const client=await createNativeClient(invoke as never,async(name,handler)=>{events.set(name,handler);return()=>{events.delete(name);};});const composition=composeMissionHost(client,null,undefined,"native");dispose=composition.dispose;
 window.MastermindMissionHost=composition.host;const view=render(<App locale={locale}/>);
 return {invoke,client,expire:()=>events.get("mastermind-auth-state")!({payload:{status:"error",reason:"NATIVE_TOKEN_EXPIRED",acquisition:false,content:false}}),host:composition.host,footer:view.container.querySelector(".nav-account")!,
  finish:()=>finish({...partial,status:"signing_in",reason:null}),refuse:()=>{capability=no;reject(new Error("AUTHORIZATION_IDENTITY_CHANGED"));},
  unknown:()=>reject(new Error("AUTH_CONTINUATION_EXCHANGE_UNCONFIRMED"))};
}
it.each(["en","zh-CN"] as const)("opens Content continuation once only after explicit gesture and returns keyboard focus: %s",async locale=>{
 const f=await mount(locale);const button=await screen.findByRole("button",{name:locale==="en"?"Continue authorization":"继续授权"});
 expect(f.invoke.mock.calls.some(([n])=>n==="continue_authorization")).toBe(false);button.focus();
 await userEvent.setup().keyboard("{Enter}");fireEvent.click(button);
 await waitFor(()=>expect(f.invoke.mock.calls.filter(([n])=>n==="continue_authorization")).toHaveLength(1));
 expect((button as HTMLButtonElement).disabled).toBe(true);
 await act(async()=>{f.finish();});
 const status=within(f.footer as HTMLElement).getByRole("status");expect(status.textContent).toContain(locale==="en"?"Authorization request opened":"授权请求已打开");
 await waitFor(()=>expect(document.activeElement).toBe(status));expect(f.client.getState().acquisition).toBe(true);expect(f.client.getState().content).toBe(false);
 expect(f.invoke.mock.calls.some(([n])=>n==="sign_in"||n==="sign_out"||n==="executive_submit")).toBe(false);
});
it("does not offer a guessed action for ineligible or old native metadata",async()=>{
 const f=await mount("en",false);await waitFor(()=>expect(f.invoke.mock.calls.some(([n])=>n==="read_authorization_continuation")).toBe(true));
 expect(screen.queryByRole("button",{name:"Continue authorization"})).toBeNull();expect(f.invoke.mock.calls.some(([n])=>n==="continue_authorization")).toBe(false);
});
it("refuses no-render Host generation replacement at the enabled gesture",async()=>{
 const f=await mount();const button=await screen.findByRole("button",{name:"Continue authorization"});f.host.invalidationGeneration=()=>999;
 fireEvent.click(button);expect(f.invoke.mock.calls.some(([n])=>n==="continue_authorization")).toBe(false);
 expect(within(f.footer as HTMLElement).getByRole("status").textContent).toContain("not sent");
});
it("preserves Acquisition on native refusal and never replays after re-reading ineligible status",async()=>{
 const f=await mount();fireEvent.click(await screen.findByRole("button",{name:"Continue authorization"}));await waitFor(()=>expect(f.invoke.mock.calls.some(([n])=>n==="continue_authorization")).toBe(true));
 await act(async()=>{f.refuse();});await waitFor(()=>expect(screen.queryByRole("button",{name:"Continue authorization"})).toBeNull());
 expect(f.footer.textContent).toContain("Additional authorization is unavailable here");expect(f.client.getState()).toEqual(partial);
 expect(f.invoke.mock.calls.filter(([n])=>n==="continue_authorization")).toHaveLength(1);
});

it("holds an unconfirmed command outcome without a second handoff even if metadata is stale",async()=>{
 const f=await mount();fireEvent.click(await screen.findByRole("button",{name:"Continue authorization"}));await waitFor(()=>expect(f.invoke.mock.calls.some(([n])=>n==="continue_authorization")).toBe(true));
 await act(async()=>{f.unknown();});await waitFor(()=>expect(f.footer.textContent).toContain("Authorization outcome is unconfirmed"));
 expect(screen.queryByRole("button",{name:"Continue authorization"})).toBeNull();expect(f.invoke.mock.calls.filter(([n])=>n==="continue_authorization")).toHaveLength(1);
});

it("withdraws the affordance after actual native Acquisition expiry without reattributing an old eligible response",async()=>{
 const f=await mount();await screen.findByRole("button",{name:"Continue authorization"});
 await act(async()=>{f.expire();});await waitFor(()=>expect(screen.queryByRole("button",{name:"Continue authorization"})).toBeNull());
 expect(f.client.getState().acquisition).toBe(false);expect(screen.queryByText("Account connected")).toBeNull();
 expect(f.invoke.mock.calls.some(([n])=>n==="continue_authorization")).toBe(false);
});
it("keeps continuation gesture-only through existing navigation and return",async()=>{
 const f=await mount();await screen.findByRole("button",{name:"Continue authorization"});
 fireEvent.click(screen.getByRole("button",{name:"Projects"}));fireEvent.click(screen.getByRole("button",{name:"Today"}));
 expect(screen.getByRole("button",{name:"Continue authorization"})).toBeTruthy();expect(f.invoke.mock.calls.some(([n])=>n==="continue_authorization")).toBe(false);
 expect(f.client.getState()).toEqual(partial);
});

it("refuses no-render replacement of the actual Host at the enabled gesture",async()=>{
 const f=await mount();const button=await screen.findByRole("button",{name:"Continue authorization"});window.MastermindMissionHost={...f.host};
 fireEvent.click(button);expect(f.invoke.mock.calls.some(([n])=>n==="continue_authorization")).toBe(false);expect(screen.queryByRole("button",{name:"Continue authorization"})).toBeNull();
});

it("does not steal focus from another user gesture while the browser handoff settles",async()=>{
 const f=await mount();fireEvent.click(await screen.findByRole("button",{name:"Continue authorization"}));await waitFor(()=>expect(f.invoke.mock.calls.some(([n])=>n==="continue_authorization")).toBe(true));
 const projects=screen.getByRole("button",{name:"Projects"});projects.focus();fireEvent.click(projects);
 await act(async()=>{f.finish();});expect(document.activeElement).toBe(projects);
});
it("refuses a no-render auth-reader substitution before any native handoff",async()=>{
 const f=await mount();const button=await screen.findByRole("button",{name:"Continue authorization"});f.host.auth!.getState=()=>{throw new Error("foreign owner");};
 fireEvent.click(button);expect(f.invoke.mock.calls.some(([n])=>n==="continue_authorization")).toBe(false);
});
