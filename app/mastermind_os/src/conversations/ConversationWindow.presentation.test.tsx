// @vitest-environment jsdom
import {cleanup,fireEvent,render,screen} from "@testing-library/react";
import {afterEach,expect,it,vi} from "vitest";
import {ConversationWindow} from "./ConversationWindow";
import {decodeMissionv3} from "../mission";
import {decodeWindow} from "../workspace-contract";
import {projectOffice,type OfficeInput,type ProjectionContext,type SourceState} from "../meta-ceo/projection";
import fixture from "../fixtures/window-mission-association-producer.json";
afterEach(cleanup);
async function input() {
  const context: ProjectionContext = { authGeneration: 3,
    selection: { workRef: fixture.selection.work_ref, rootJobId: fixture.selection.root_job_id },
    sessionRef: null, bindingGeneration: null,
    revisions: { mission: "m1", programs: null, result: null, conversation: "w1" } };
  const source = { owner: "EXECUTIVE_OS", ref: "private:mission", revision: "m1", observed_at: "2026-10-04T08:00:00Z", state: "CURRENT" as const, coverage: "COMPLETE" };
  const reads: OfficeInput = { programs: null, result: null,
    mission: { context, source, value: decodeMissionv3(structuredClone(fixture.mission), context.selection!) },
    conversation: { context, source: { ...source, owner: "CURRENT_WINDOW", ref: "private:window", revision: "w1", coverage: "OBSERVED_WINDOW" }, value: await decodeWindow(structuredClone(fixture.window)) } };
  return { reads, context, projection: projectOffice(reads, context) };
}

it("keeps exact replies first and raw scope in a closed accessible disclosure",async()=>{
 const {projection}=await input();const view=render(<ConversationWindow projection={projection} headingLevel={1} draft={"Exact draft\n原文"} onDraftChange={vi.fn()}/>);
 expect(screen.getByRole("heading",{level:1,name:"One"})).toBeTruthy();
 expect(screen.getByText(projection.conversation.value!.view.items.find(item=>item.text)!.text!)).toBeTruthy();
 const state=screen.getByText("CURRENT");expect(state.closest("details")?.open).toBe(false);
 expect(screen.getByText("Replies from the selected work. This view may not include the full conversation.")).toBeTruthy();
 expect(view.container.querySelector('.conversation-mark')).toBeNull();
 expect((screen.getByRole("textbox",{name:"Unsent draft"}) as HTMLTextAreaElement).value).toBe("Exact draft\n原文");
});
it.each<SourceState>(["UNAVAILABLE","WITHHELD","UNASSOCIATED"])("keeps %s distinct from empty replies and withholds source identity",async state=>{
 const {reads,context}=await input();reads.conversation!.source.state=state;
 render(<ConversationWindow projection={projectOffice(reads,context)} draft="" onDraftChange={vi.fn()}/>);
 expect(screen.getByRole("status").textContent).not.toMatch(/No replies|No visible/);
 expect(screen.queryByText(reads.conversation!.value!.view.items[0].text!)).toBeNull();
 expect(document.body.textContent).not.toContain("private:window");
 expect(screen.getByRole("button",{name:"Context"})).toHaveProperty("disabled",true);
});
it("uses plain earlier-view copy without promoting it to current history",async()=>{
 const {reads,context}=await input();reads.conversation!.source.state="STALE";
 render(<ConversationWindow projection={projectOffice(reads,context)} draft="" onDraftChange={vi.fn()}/>);
 expect(screen.getByText("Showing an earlier view. Newer replies may be missing.")).toBeTruthy();
 expect(screen.getByText("STALE").closest("details")?.open).toBe(false);
});
it("keeps context provenance opt-in and returns focus on Escape",async()=>{
 const {projection}=await input();render(<ConversationWindow projection={projection} draft="Exact draft" onDraftChange={vi.fn()}/>);
 const trigger=screen.getByRole("button",{name:"Context"});fireEvent.click(trigger);
 const panel=screen.getByRole("region",{name:"Conversation context"});expect(document.activeElement).toBe(panel);
 expect(screen.getByText("m1").closest("details")?.open).toBe(false);
 fireEvent.keyDown(panel,{key:"Escape"});expect(document.activeElement).toBe(trigger);
});
it("keeps the actual notes element and user text through locale updates",async()=>{
 const {projection}=await input();const view=render(<ConversationWindow projection={projection} draft="Original notes 原文" notesPresentation="collapsed" onDraftChange={vi.fn()}/>);
 fireEvent.click(screen.getByRole("button",{name:"Unsent notes"}));const notes=screen.getByRole("textbox",{name:"Unsent notes"});notes.focus();
 view.rerender(<ConversationWindow projection={projection} locale="zh-CN" draft="Original notes 原文" notesPresentation="collapsed" onDraftChange={vi.fn()}/>);
 expect(screen.getByRole("textbox",{name:"未发送的笔记"})).toBe(notes);expect(document.activeElement).toBe(notes);
 expect(notes).toHaveProperty("value","Original notes 原文");expect(screen.getByText("这些笔记不会发送。")).toBeTruthy();
});
it("keeps unknown outcome visible and its code closed without offering replay",async()=>{
 const {reads,context}=await input();reads.mission!.value!.transport.dispatch_state="EFFECT_UNKNOWN";
 render(<ConversationWindow projection={projectOffice(reads,context)} draft="" onDraftChange={vi.fn()}/>);
 expect(screen.getByRole("alert").textContent).toContain("Don’t send it again");
 for(const code of screen.getAllByText("EFFECT_UNKNOWN"))expect(code.closest("details")?.open).toBe(false);
 expect(screen.queryByRole("button",{name:/resend|retry|stop|send again/i})).toBeNull();
});
