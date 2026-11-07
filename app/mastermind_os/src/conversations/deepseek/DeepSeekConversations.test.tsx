// @vitest-environment jsdom
import {cleanup,fireEvent,render,screen} from "@testing-library/react";
import {afterEach,expect,it,vi} from "vitest";
import {DeepSeekConversations} from "./DeepSeekConversations";
import type {ConversationListModel} from "../conversation-list-contract";
afterEach(cleanup);
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
