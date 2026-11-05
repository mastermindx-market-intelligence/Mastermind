// @vitest-environment jsdom
import {act, cleanup, fireEvent, render, screen, waitFor} from "@testing-library/react";
import {afterEach, beforeEach, expect, it, vi} from "vitest";
import {App} from "./App";
import type {AuthState} from "./host";
import {createFixtureCommandBinding} from "./browser-proof-command-fixture";
import type {PendingPointerStore} from "./orchestration/operation-controller";
const readiness = vi.hoisted(() => ({version:"test-version",source_revision:"raw-source-revision",build_identity:"raw-build-identity",transport:"raw-transport",state:"raw-state",native_client_ref:"raw-client"}));
vi.mock("@tauri-apps/api/core",()=>({invoke:vi.fn(async()=>readiness)}));
beforeEach(()=>{localStorage.clear();delete window.MastermindMissionHost;delete (window as Window & {__TAURI_INTERNALS__?:unknown}).__TAURI_INTERNALS__;});
afterEach(()=>{cleanup();localStorage.clear();delete window.MastermindMissionHost;delete (window as Window & {__TAURI_INTERNALS__?:unknown}).__TAURI_INTERNALS__;});
it("shows plain Chinese unavailable work, selection and footer without changing raw diagnostics",()=>{
 render(<App locale="zh-CN" theme="light"/>);
 expect(screen.getByRole("heading",{name:"开始工作"})).toBeTruthy();
 expect(screen.getByRole("navigation",{name:"公司导航"})).toBeTruthy();
 expect(screen.getByRole("link",{name:"跳至工作区"})).toBeTruthy();
 expect(screen.getByText("暂时无法开始工作。")).toBeTruthy();
 expect(screen.queryByText("尚未选择工作项")).toBeNull();
 expect(document.querySelector("details.nav-advanced nav")?.getAttribute("aria-label")).toBe("工作导航");
 expect(document.querySelector<HTMLDetailsElement>("details.nav-advanced")?.open).toBe(false);
 expect(screen.getByText("状态与来源")).toBeTruthy();
 const summary=screen.getByText("技术详情");
 expect(summary.closest("details")?.open).toBe(false);
 expect(summary.closest("details")?.textContent).toContain("COMMAND_ROUTE_UNAVAILABLE");
 expect(screen.queryByText("Launch Orchestrator")).toBeNull();
 expect(screen.queryByText("No exact mission selected")).toBeNull();
});
it("localizes real signed-in status and leaves the sign-out callback intact",()=>{
 const signOut=vi.fn(async()=>{});
 window.MastermindMissionHost={auth:{getState:()=>({status:"signed_in",reason:null,acquisition:false,content:true}),subscribe:()=>()=>{},signIn:async()=>{},signOut}};
 render(<App locale="zh-CN"/>);
 expect(screen.getByText("已登录")).toBeTruthy();
 fireEvent.click(screen.getByRole("button",{name:"退出登录"}));
 expect(signOut).toHaveBeenCalledTimes(1);
});
it("localizes native build labels while keeping the exact receipt values in closed details",async()=>{
 Object.defineProperty(window,"__TAURI_INTERNALS__",{configurable:true,value:{}});
 render(<App locale="zh-CN"/>);
 const summary=await screen.findByText("构建详情");
 const details=summary.closest("details")!;
 expect(details.open).toBe(false);
 for(const label of ["版本","来源修订","构建标识","原生客户端引用","传输"]) expect(details.textContent).toContain(label);
 for(const value of Object.values(readiness)) expect(details.textContent).toContain(value);
});
it("changes language in the real ready composer without remounting or sending its unsent draft",async()=>{
 const store:PendingPointerStore={read:()=>null,reserve:()=>({reserved:true}),clearIfEqual:()=>true};
 const binding=createFixtureCommandBinding(store);
 const submit=vi.spyOn(binding.port,"submit");
 window.MastermindMissionHost={commandBinding:binding,auth:{getState:()=>({status:"signed_in",reason:null,acquisition:false,content:false}),subscribe:()=>()=>{},signIn:async()=>{},signOut:async()=>{}}};
 const view=render(<App locale="en"/>);
 const goal=screen.getByLabelText("Goal") as HTMLTextAreaElement;
 fireEvent.change(goal,{target:{value:"Keep this exact unsent goal"}});
 await waitFor(()=>expect(goal.value).toBe("Keep this exact unsent goal"));
 view.rerender(<App locale="zh-CN"/>);
 expect(screen.getByRole("heading",{name:"开始工作"})).toBeTruthy();
 expect(screen.getByLabelText("目标")).toBe(goal);
 expect(goal.value).toBe("Keep this exact unsent goal");
 expect(submit).not.toHaveBeenCalled();
});

it.each(["en", "zh-CN"] as const)("shows an explicit signed-out cue with the original sign-in action (%s)", locale => {
 const signIn=vi.fn(async()=>{});
 window.MastermindMissionHost={auth:{getState:()=>({status:"signed_out",reason:null,acquisition:false,content:false}),subscribe:()=>()=>{},signIn,signOut:vi.fn(async()=>{})}};
 render(<App locale={locale}/>);
 expect(screen.getByRole("heading",{name:locale==="zh-CN"?"欢迎回来。":"Welcome back."})).toBeTruthy();
 expect(screen.queryByText(locale==="zh-CN"?"暂时无法获取待决策事项。":"Decision information is unavailable right now.")).toBeNull();
 fireEvent.click(screen.getByRole("button",{name:locale==="zh-CN"?"登录":"Sign in"}));
 expect(signIn).toHaveBeenCalledTimes(1);
});

it("keeps the unsent Today goal protected before the explicit expired-auth cue",async()=>{
 let signedIn=true;
 let notify: (state: AuthState)=>void=()=>{};
 const store:PendingPointerStore={read:()=>null,reserve:()=>({reserved:true}),clearIfEqual:()=>true};
 const binding=createFixtureCommandBinding(store);
 const submit=vi.spyOn(binding.port,"submit");
 const signIn=vi.fn(async()=>{});
 window.MastermindMissionHost={commandBinding:binding,auth:{getState:()=>({status:signedIn?"signed_in":"signed_out",reason:signedIn?null:"TOKEN_EXPIRED",acquisition:signedIn,content:false}),subscribe:listener=>{notify=listener;return()=>{};},signIn,signOut:vi.fn(async()=>{})}};
 render(<App locale="en"/>);
 fireEvent.change(screen.getByLabelText("Goal"),{target:{value:"Literal unsent Today goal"}});
 await act(async()=>{signedIn=false;notify(window.MastermindMissionHost!.auth!.getState());});
 expect(screen.getByRole("heading",{name:"Welcome back."})).toBeTruthy();
 expect((screen.getByLabelText("Goal") as HTMLTextAreaElement).value).toBe("Literal unsent Today goal");
 expect(screen.getByLabelText("Goal").closest("section")?.textContent).toContain("expired");
 expect(screen.queryByText("Decision information is unavailable right now.")).toBeNull();
 expect(submit).not.toHaveBeenCalled();
});
