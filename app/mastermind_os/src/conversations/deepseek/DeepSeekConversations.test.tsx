// @vitest-environment jsdom
import {act,cleanup,fireEvent,render,screen} from "@testing-library/react";
import {afterEach,expect,it,vi} from "vitest";
import {DeepSeekConversations} from "./DeepSeekConversations";
import {COMPANY_SCHEMA, DONOR_SHA} from "../../../../../integrations/deepseek_harness/company_plugin/src/protocol";
import type {ConversationListModel} from "../conversation-list-contract";
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers(); });
const model:ConversationListModel={schema:"mastermind.conversations_list_projection.v1",authGeneration:1,
 recentState:"UNAVAILABLE",projectsState:"CURRENT",recent:[],projects:[],sources:[],historyCoverage:"NOT_ENUMERATED"};
const props={model,signedIn:true,authGeneration:1,onOpenProject:()=>false,children:<p>Existing project conversations</p>};
const config={url:"https://chat.mastermind-x.com/",origin:"https://chat.mastermind-x.com"};
it("preserves the existing journey when the native application is not installed",()=>{
 const next=vi.fn();render(<DeepSeekConversations {...props} config={null} onNewConversation={next}/>);
 expect(screen.getByText("Existing project conversations")).toBeTruthy();
 expect(document.querySelector("iframe")).toBeNull();
 fireEvent.click(screen.getByRole("tab",{name:"Chat"}));
 expect(screen.getByRole("heading",{name:"The chat connection is not installed"})).toBeTruthy();
 fireEvent.click(screen.getByRole("button",{name:"New project conversation"}));expect(next).toHaveBeenCalledOnce();
});
it("mounts the complete application without passing tokens or project IDs in the URL",()=>{
 render(<DeepSeekConversations {...props} config={config}/>);
 const frame=screen.getByTitle("Mastermind chat");
 expect(frame.getAttribute("src")).toBe(config.url);
 expect(frame.getAttribute("sandbox")).not.toContain("allow-top-navigation");
 expect(frame.getAttribute("sandbox")).toContain("allow-popups-to-escape-sandbox");
 expect(frame.getAttribute("allow")).toContain("clipboard-write");
 expect(frame.getAttribute("referrerpolicy")).toBe("no-referrer");
 fireEvent.click(screen.getByRole("tab",{name:"Project conversations"}));
 expect(screen.getByTitle("Mastermind chat")).toBe(frame);
});
it("removes the child on sign-out and remounts on a new authentication generation",()=>{
 const app=render(<DeepSeekConversations {...props} config={config}/>);
 const original=screen.getByTitle("Mastermind chat");
 app.rerender(<DeepSeekConversations {...props} authGeneration={2} config={config}/>);
 expect(screen.getByTitle("Mastermind chat")).not.toBe(original);
 app.rerender(<DeepSeekConversations {...props} authGeneration={3} signedIn={false} config={config}/>);
 expect(document.querySelector("iframe")).toBeNull();
 expect(screen.getByRole("heading",{name:"Sign in to continue chatting"})).toBeTruthy();
});
it("shows the same usable states in Chinese",()=>{
 render(<DeepSeekConversations {...props} config={null} locale="zh-CN"/>);
 fireEvent.click(screen.getByRole("tab",{name:"聊天"}));
 expect(screen.getByRole("heading",{name:"聊天连接尚未安装"})).toBeTruthy();
});

const projectModel = (authGeneration = 1, locatorGeneration = authGeneration): ConversationListModel => ({
 ...model, authGeneration, projects: [{
  key: "project-chat", title: "Private project", nextAction: null,
  locator: {kind: "project", workRef: "WS:CHAT", sourceRef: "agentos:catalogue",
   sourceRevision: "a".repeat(40), authGeneration: locatorGeneration},
 }],
});
function mountedBridge(frame: HTMLIFrameElement) {
 const target = frame.contentWindow!;
 const posted = vi.spyOn(target, "postMessage");
 fireEvent.load(frame);
 const nonce = () => posted.mock.calls.filter(([message]) => message.type === "connect").at(-1)![0].nonce;
 const receive = (message: Record<string, unknown>, source: Window = target, origin = config.origin) =>
  fireEvent(window, new MessageEvent("message", {source, origin,
   data: {schema: COMPANY_SCHEMA, nonce: nonce(), ...message}}));
 const ready = () => receive({type: "ready", donor: DONOR_SHA});
 const view = () => posted.mock.calls.filter(([message]) => message.type === "context").at(-1)![0].view;
 ready();
 return {target, posted, nonce, receive, ready, view};
}
it("withholds a former authentication generation before the mounted child receives project data", () => {
 const open = vi.fn(() => true);
 render(<DeepSeekConversations {...props} model={projectModel(1)} authGeneration={2}
  selectedProject="WS:CHAT" onOpenProject={open} config={config}/>);
 const child = mountedBridge(screen.getByTitle("Mastermind chat") as HTMLIFrameElement);
 expect(child.view()).toMatchObject({state: "UNAVAILABLE", projects: [], selectedProject: null});
 child.receive({type: "open_project", generation: child.view().generation, workRef: "WS:CHAT"});
 expect(open).not.toHaveBeenCalled();
});
it("withholds a retired project locator even inside a current-generation model", () => {
 const open = vi.fn(() => true);
 render(<DeepSeekConversations {...props} model={projectModel(2, 1)} authGeneration={2}
  selectedProject="WS:CHAT" onOpenProject={open} config={config}/>);
 const child = mountedBridge(screen.getByTitle("Mastermind chat") as HTMLIFrameElement);
 expect(child.view()).toMatchObject({state: "CURRENT", projects: [], selectedProject: null});
 child.receive({type: "open_project", generation: child.view().generation, workRef: "WS:CHAT"});
 expect(open).not.toHaveBeenCalled();
});
it("routes only the current listed project through the mounted company's exact owner locator", () => {
 const current = projectModel(), open = vi.fn(() => true);
 render(<DeepSeekConversations {...props} model={current} selectedProject="WS:CHAT" onOpenProject={open} config={config}/>);
 const child = mountedBridge(screen.getByTitle("Mastermind chat") as HTMLIFrameElement);
 const navigation = {type: "open_project", generation: child.view().generation, workRef: "WS:CHAT"};
 child.receive(navigation, window);
 child.receive(navigation, child.target, "https://foreign.example");
 child.receive({...navigation, workRef: "WS:OTHER"});
 expect(open).not.toHaveBeenCalled();
 child.receive(navigation);
 expect(open).toHaveBeenCalledExactlyOnceWith(current.projects[0].locator);
 expect(child.posted.mock.calls.at(-1)![0]).toMatchObject({type: "navigation_result", workRef: "WS:CHAT", ok: true});
});
it("revokes the original mounted document and rejects its late navigation across auth replacement and logout", () => {
 const open = vi.fn(() => true);
 const app = render(<DeepSeekConversations {...props} model={projectModel()} onOpenProject={open} config={config}/>);
 const originalFrame = screen.getByTitle("Mastermind chat") as HTMLIFrameElement;
 const original = mountedBridge(originalFrame);
 const navigation = {type: "open_project", generation: original.view().generation, workRef: "WS:CHAT"};
 app.rerender(<DeepSeekConversations {...props} model={projectModel(2)} authGeneration={2} onOpenProject={open} config={config}/>);
 expect(original.posted.mock.calls.at(-1)![0].view).toMatchObject({state: "SIGNED_OUT", projects: [], selectedProject: null});
 original.receive(navigation);
 expect(open).not.toHaveBeenCalled();
 const replacementFrame = screen.getByTitle("Mastermind chat") as HTMLIFrameElement;
 expect(replacementFrame).not.toBe(originalFrame);
 const replacement = mountedBridge(replacementFrame);
 replacement.receive({...navigation, generation: replacement.view().generation});
 expect(open).toHaveBeenCalledOnce();
 app.rerender(<DeepSeekConversations {...props} model={projectModel(2)} authGeneration={3}
  signedIn={false} onOpenProject={open} config={config}/>);
 expect(replacement.posted.mock.calls.at(-1)![0].view).toMatchObject({state: "SIGNED_OUT", projects: []});
 replacement.receive({...navigation, generation: replacement.view().generation});
 expect(open).toHaveBeenCalledOnce();
 expect(document.querySelector("iframe")).toBeNull();
});
it("keeps the native document alive while keyboard users move between chat and projects", () => {
 render(<DeepSeekConversations {...props} config={config}/>);
 const frame = screen.getByTitle("Mastermind chat");
 const chat = screen.getByRole("tab", {name: "Chat"});
 const projects = screen.getByRole("tab", {name: "Project conversations"});
 chat.focus();
 for (const [key, selected] of [["ArrowRight", projects], ["Home", chat], ["End", projects], ["ArrowLeft", chat]] as const) {
  fireEvent.keyDown(document.activeElement!, {key});
  expect(selected.getAttribute("aria-selected")).toBe("true");
  expect(selected.getAttribute("tabindex")).toBe("0");
  expect(document.activeElement).toBe(selected);
  expect(screen.getByTitle("Mastermind chat")).toBe(frame);
 }
});
it("keeps an unacknowledged connection visible and retires its old handshake without recreating or navigating the native session", () => {
 vi.useFakeTimers();
 const open = vi.fn(() => true);
 render(<DeepSeekConversations {...props} model={projectModel()} onOpenProject={open} config={config}/>);
 const frame = screen.getByTitle("Mastermind chat") as HTMLIFrameElement;
 const child = mountedBridge(frame);
 const oldNonce = child.nonce(), oldGeneration = child.view().generation;
 act(() => { vi.advanceTimersByTime(12000); });
 expect(screen.getByRole("status").textContent).toContain("The chat connection is not ready");
 expect(screen.getByRole("link", {name: "Open chat application"}).getAttribute("href")).toBe(config.url);
 expect(screen.getByTitle("Mastermind chat")).toBe(frame);
 fireEvent.load(frame);
 expect(child.nonce()).not.toBe(oldNonce);
 child.receive({type: "ready", donor: DONOR_SHA, nonce: oldNonce});
 child.receive({type: "open_project", generation: oldGeneration, workRef: "WS:CHAT", nonce: oldNonce});
 expect(open).not.toHaveBeenCalled();
 child.ready();
 child.receive({type: "ack", generation: child.view().generation});
 expect(screen.queryByRole("status")).toBeNull();
 expect(open).not.toHaveBeenCalled();
 expect(child.posted.mock.calls.every(([message]) =>
  ["connect", "context"].includes(message.type))).toBe(true);
});
