// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";
import actualFeed from "./inbox/fixtures/terminal-sharing-request-feed.json";
import { bindMissionHost, createNativeClient } from "./host";

beforeEach(() => {
  history.replaceState(null, "", "/os/");
  delete window.MastermindMissionHost;
});
afterEach(() => { cleanup(); delete window.MastermindMissionHost; vi.restoreAllMocks(); });

async function mount(terminalState: "UNCONFIGURED" | "SIGNED_OUT") {
  const initial = { state: terminalState, generation: 0, reason: null, available: false,
    principal_scope: null, session_scope: null };
  const invoke = vi.fn(async (command: string) => {
    if (command === "auth_status") return {status:"signed_in", reason:null, acquisition:true, content:true};
    if (command === "executive_auth_status") return {generation:0,available:false};
    if (command === "terminal_session_status") return initial;
    if (command === "terminal_sign_in") return {...initial,state:"SIGNING_IN",generation:1};
    if (command === "terminal_disconnect") return {...initial,state:"SIGNED_OUT",generation:2,reason:"SIGNED_OUT_LOCAL"};
    throw new Error("synthetic unavailable source");
  });
  const client = await createNativeClient(invoke as never, async () => () => {});
  window.MastermindMissionHost = bindMissionHost(client);
  render(<App />);
  fireEvent.click(screen.getAllByRole("button", {name:"Inbox"})[0]);
  await screen.findByRole("region", {name:"Terminal brief requests"});
  expect(document.querySelector('.workspace-header-quiet')).toBeTruthy();
  expect(screen.getByText("Workspace source", {exact:true})).toBeTruthy();
  expect(screen.queryByText("Source status", {exact:true})).toBeNull();
  expect(document.querySelector('main > .notice')).toBeNull();
  return {invoke, client};
}

it("mounts the real Inbox seam without borrowing signed-in workspace grants or inventing requests", async () => {
  const {invoke,client} = await mount("UNCONFIGURED");
  expect(client.getState()).toMatchObject({status:"signed_in",acquisition:true,content:true});
  expect(screen.queryByRole("button", {name:"Connect Terminal"})).toBeNull();
  expect(screen.queryByRole("button", {name:"Continue in Terminal"})).toBeNull();
  expect(invoke.mock.calls.filter(([name]) => name === "read_terminal_sharing_requests"
    || name === "terminal_sign_in" || name === "open_terminal_sharing_request")).toHaveLength(0);
  expect(document.body.textContent).not.toContain("6 members");
  expect(document.body.textContent).not.toContain("Version 3");
});

it("requires an explicit separate Terminal connection and leaves the workspace auth owner unchanged", async () => {
  const {invoke,client} = await mount("SIGNED_OUT");
  expect(invoke.mock.calls.filter(([name]) => name === "terminal_sign_in")).toHaveLength(0);
  fireEvent.click(await screen.findByRole("button", {name:"Connect Terminal"}));
  await waitFor(() => expect(invoke.mock.calls.filter(([name]) => name === "terminal_sign_in")).toHaveLength(1));
  expect(invoke.mock.calls.filter(([name]) => name === "sign_in" || name === "sign_out"
    || name === "read_terminal_sharing_requests" || name === "open_terminal_sharing_request")).toHaveLength(0);
  expect(client.getState()).toMatchObject({status:"signed_in",acquisition:true,content:true});
});

it("joins the actual SQL-issued request through the native host, Inbox and exact review tuple, then withdraws on Terminal logout", async () => {
  const events=new Map<string,(event:{payload:unknown})=>void>();
  const signed={state:"SIGNED_IN",generation:2,reason:null,available:true,...actualFeed.viewer};
  const invoke=vi.fn(async(command:string,args?:Record<string,unknown>)=>{
    if(command==="auth_status")return {status:"signed_in",reason:null,acquisition:true,content:true};
    if(command==="executive_auth_status")return {generation:0,available:false};
    if(command==="terminal_session_status")return signed;
    if(command==="read_terminal_sharing_requests")return structuredClone(actualFeed);
    if(command==="open_terminal_sharing_request") {
      const selected=args?.selection as Record<string,unknown>;
      return {schema:"mastermind.terminal_sharing_handoff.v1",request_ref:selected.request_ref,
        revision:1,delivery_id:selected.delivery_id,outcome:"HANDOFF_REQUESTED"};
    }
    throw new Error("synthetic unavailable workspace source");
  });
  const client=await createNativeClient(invoke as never,async(name,handler)=>{events.set(name,handler);return()=>{events.delete(name);};});
  window.MastermindMissionHost=bindMissionHost(client);render(<App/>);
  expect(invoke.mock.calls.filter(([name])=>name.startsWith("terminal_"))).toHaveLength(0);
  fireEvent.click(screen.getAllByRole("button",{name:"Inbox"})[0]);
  await screen.findByText(actualFeed.requests[0].delivery.title);
  expect(screen.getByText("3 members")).toBeTruthy();
  expect(screen.queryByText("Version 1")).toBeNull();
  fireEvent.click(screen.getByRole("button",{name:"Continue in Terminal"}));
  await screen.findByText("Continue in Terminal to review this request.");
  const request=actualFeed.requests[0];
  expect(invoke.mock.calls.filter(([name])=>name==="open_terminal_sharing_request")).toEqual([
    ["open_terminal_sharing_request",{selection:{request_ref:request.request_ref,revision:1,
      delivery_id:request.delivery.delivery_id,content_sha256:request.delivery.content_sha256}}]
  ]);
  expect(screen.getByText(request.delivery.title)).toBeTruthy();
  expect(screen.queryByText("Shared",{exact:true})).toBeNull();
  await act(async()=>{events.get("terminal-session-changed")?.({payload:{state:"SIGNED_OUT",generation:3,
    reason:"SIGNED_OUT_LOCAL",available:false,principal_scope:null,session_scope:null}});});
  expect(screen.queryByText(request.delivery.title)).toBeNull();
  expect(client.getState()).toMatchObject({status:"signed_in",acquisition:true,content:true});
  expect(invoke.mock.calls.filter(([name])=>name==="sign_in"||name==="executive_submit"||name==="terminal_sign_in")).toHaveLength(0);
});
