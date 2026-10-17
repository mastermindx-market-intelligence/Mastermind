// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SessionWorkspace, type SessionWorkspaceProps } from "./SessionWorkspace";

afterEach(cleanup);
function setup(overrides: Partial<SessionWorkspaceProps> = {}) {
  const onSend = vi.fn<SessionWorkspaceProps["onSend"]>();
  const props: SessionWorkspaceProps = { sessionKey: "exact-session", title: "Session", messages: [],
    observedAt: null, connection: "connected", coverage: "Qualified test", turnBusy: false,
    sending: false, onSend, ...overrides };
  render(<SessionWorkspace {...props} />);
  const box = screen.getByRole("textbox", {name: "Message"}) as HTMLTextAreaElement;
  fireEvent.change(box, {target: {value: "Keep this exact message"}});
  return {box, onSend};
}

describe("SessionWorkspace keyboard contract", () => {
  it("ready Enter uses the existing submit path exactly once and holds the pending guard", () => {
    const {box, onSend} = setup();
    fireEvent.keyDown(box, {key: "Enter", code: "Enter"});
    fireEvent.keyDown(box, {key: "Enter", code: "Enter"});
    expect(onSend).toHaveBeenCalledTimes(1);
    expect(onSend.mock.calls[0][0]).toBe("Keep this exact message");
    expect(box.value).toBe("Keep this exact message");
    expect(screen.getByRole("button", {name: "Sending…"})).toBeTruthy();
  });
  it("Shift+Enter keeps a newline and does not send", async () => {
    const user = userEvent.setup(); const {box,onSend}=setup();
    await user.click(box); await user.keyboard("{End}{Shift>}{Enter}{/Shift}");
    expect(box.value).toBe("Keep this exact message\n"); expect(onSend).not.toHaveBeenCalled();
  });
  it.each([{isComposing:true},{keyCode:229}])("IME confirmation never submits: %j", extra => {
    const {box,onSend}=setup();
    const event=new KeyboardEvent("keydown",{key:"Enter",bubbles:true,cancelable:true,...extra});
    fireEvent(box,event);
    expect(onSend).not.toHaveBeenCalled(); expect(event.defaultPrevented).toBe(false);
  });
  it("a held Enter never sends the next draft after synchronous acceptance", () => {
    const onSend=vi.fn<SessionWorkspaceProps["onSend"]>((_text,complete)=>complete({status:"accepted"}));
    const {box}=setup({onSend});
    fireEvent.keyDown(box,{key:"Enter"});
    expect(onSend).toHaveBeenCalledTimes(1); expect(box.value).toBe("");
    fireEvent.change(box,{target:{value:"Later draft"}});
    fireEvent.keyDown(box,{key:"Enter",repeat:true});
    expect(onSend).toHaveBeenCalledTimes(1); expect(box.value).toBe("Later draft");
  });
  it.each(["ctrlKey","metaKey","altKey"])("does not introduce %s+Enter dispatch", modifier=>{
    const {box,onSend}=setup(); fireEvent.keyDown(box,{key:"Enter",[modifier]:true});
    expect(onSend).not.toHaveBeenCalled();
  });
  it.each([{connection:"disconnected" as const},{turnBusy:true},{sending:true}])("does not submit an unavailable composer: %j", overrides=>{
    const {box,onSend}=setup(overrides); fireEvent.keyDown(box,{key:"Enter"});
    expect(onSend).not.toHaveBeenCalled();
  });
  it.each(["   ","字".repeat(5462)])("blank or oversized messages remain unsent", text=>{
    const {box,onSend}=setup();fireEvent.change(box,{target:{value:text}});fireEvent.keyDown(box,{key:"Enter"});
    expect(onSend).not.toHaveBeenCalled();
  });
  it("preserves explicit Send for pointer/mobile users",()=>{
    const {onSend}=setup();fireEvent.click(screen.getByRole("button",{name:"Send"}));
    expect(onSend).toHaveBeenCalledTimes(1);
  });
});
