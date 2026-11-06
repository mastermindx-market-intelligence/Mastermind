// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { SelectedSessionContinuation, type SelectedSessionContinuationProps } from "./SelectedSessionContinuation";

afterEach(cleanup);
const target = `fabric_attempt:${"b".repeat(64)}`;
function mount(extra: Partial<SelectedSessionContinuationProps> = {}) {
  const onContinue = vi.fn();
  const view = render(<SelectedSessionContinuation sessionKey={target} status={null}
    retainedPointer={null} reading={false} recovering={false} sending={false}
    onRecover={vi.fn()} onContinue={onContinue} {...extra} />);
  const instruction = screen.getByLabelText("What would you like done?") as HTMLTextAreaElement;
  const condition = screen.getByLabelText("How will we know it is done?") as HTMLTextAreaElement;
  fireEvent.change(instruction, { target: { value: "Read the exact source" } });
  fireEvent.change(condition, { target: { value: "Return verified evidence" } });
  return { ...view, onContinue, instruction, condition };
}

describe("DeepSeek composition guard through the governed session form", () => {
  it("sends explicit Ctrl+Enter through the existing form exactly once", () => {
    const { instruction, onContinue } = mount();
    fireEvent.keyDown(instruction, { key: "Enter", ctrlKey: true });
    fireEvent.keyDown(instruction, { key: "Enter", ctrlKey: true });
    fireEvent.submit(instruction.form!);
    expect(onContinue).toHaveBeenCalledTimes(1);
    expect(onContinue.mock.calls[0].slice(0, 2)).toEqual(["Read the exact source", "Return verified evidence"]);
  });

  it.each([
    { shiftKey: true }, { altKey: true }, { ctrlKey: true, metaKey: true },
    { ctrlKey: true, shiftKey: true }, { metaKey: true, shiftKey: true },
    { repeat: true }, { isComposing: true }, { keyCode: 229 },
  ])("never sends a modified/composing/repeated gesture %j", (flags) => {
    const { instruction, onContinue } = mount();
    expect(fireEvent.keyDown(instruction, { key: "Enter", ctrlKey: true, ...flags })).toBe(true);
    expect(onContinue).not.toHaveBeenCalled();
  });

  it("preserves plain Enter as a line break in the instruction field", () => {
    const { instruction, onContinue } = mount();
    expect(fireEvent.keyDown(instruction, { key: "Enter" })).toBe(true);
    expect(onContinue).not.toHaveBeenCalled();
  });

  it("keeps plain Enter as a line break in the completion field", () => {
    const { condition, onContinue } = mount();
    expect(fireEvent.keyDown(condition, { key: "Enter" })).toBe(true);
    expect(onContinue).not.toHaveBeenCalled();
  });

  it.each([{ ctrlKey: true }, { metaKey: true }])("supports an explicit modifier send in the completion field %j", (flags) => {
    const { condition, onContinue } = mount();
    fireEvent.keyDown(condition, { key: "Enter", ...flags });
    expect(onContinue).toHaveBeenCalledTimes(1);
  });

  it("does not submit the Safari-style Enter after compositionend", () => {
    const { instruction, onContinue } = mount();
    fireEvent.compositionStart(instruction);
    fireEvent.keyDown(instruction, { key: "Enter", ctrlKey: true });
    fireEvent.compositionEnd(instruction);
    fireEvent.keyDown(instruction, { key: "Enter", ctrlKey: true });
    expect(onContinue).not.toHaveBeenCalled();
    fireEvent.keyUp(instruction, { key: "Enter", ctrlKey: true });
    fireEvent.keyDown(instruction, { key: "Enter", ctrlKey: true });
    expect(onContinue).toHaveBeenCalledTimes(1);
  });

  it("clears an abandoned composition on window blur", () => {
    const { instruction, onContinue } = mount();
    fireEvent.compositionStart(instruction);
    fireEvent(window, new Event("blur"));
    fireEvent.keyDown(instruction, { key: "Enter", ctrlKey: true });
    expect(onContinue).toHaveBeenCalledTimes(1);
  });

  it.each([{ reading: true }, { recoveryRequired: true }, { sending: true }, { recovering: true }])(
    "cannot bypass the owner hold %j", (extra) => {
      const { instruction, onContinue } = mount(extra);
      fireEvent.keyDown(instruction, { key: "Enter", ctrlKey: true });
      expect(onContinue).not.toHaveBeenCalled();
    },
  );

  it("requires an explicit valid completion condition", () => {
    const { instruction, condition, onContinue } = mount();
    fireEvent.change(condition, { target: { value: " " } });
    fireEvent.keyDown(instruction, { key: "Enter", ctrlKey: true });
    expect(onContinue).not.toHaveBeenCalled();
  });

  it("removes every document composition listener on unmount", () => {
    const remove = vi.spyOn(document, "removeEventListener");
    const { unmount } = mount();
    unmount();
    for (const event of ["compositionstart", "compositionend", "keyup"]) {
      expect(remove.mock.calls.some(call => call[0] === event && call[2] === true)).toBe(true);
    }
    remove.mockRestore();
  });
});
