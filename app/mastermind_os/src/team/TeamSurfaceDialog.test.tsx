// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TeamSurfaceDialog } from "./TeamSurfaceDialog";
afterEach(cleanup);

describe("TeamSurfaceDialog — keyboard contract for the Team surfaces", () => {
  it("closes on Escape", () => {
    const onClose = vi.fn();
    render(
      <TeamSurfaceDialog title="New teammate" closeLabel="Close" onClose={onClose}>
        <p>Body</p>
      </TeamSurfaceDialog>,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("exposes the dialog semantics and a labelled close button", () => {
    const onClose = vi.fn();
    render(
      <TeamSurfaceDialog title="New group" closeLabel="Close surface" onClose={onClose}>
        <p>Body</p>
      </TeamSurfaceDialog>,
    );
    const dialog = screen.getByRole("dialog", { name: "New group" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Close surface" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("moves focus into the dialog on open and back to the trigger on close", () => {
    function Harness() {
      const [open, setOpen] = React.useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>
            Open surface
          </button>
          {open ? (
            <TeamSurfaceDialog
              title="New teammate"
              closeLabel="Close"
              onClose={() => setOpen(false)}
            >
              <button type="button">Inside</button>
            </TeamSurfaceDialog>
          ) : null}
        </>
      );
    }
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: "Open surface" });
    trigger.focus(); // keyboard open: focus sits on the trigger
    fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog");
    expect(document.activeElement).toBe(dialog); // focus moved in
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull(); // closed
    expect(document.activeElement).toBe(trigger); // and returned to the trigger
  });

  it("traps Tab inside the dialog and wraps at both ends", () => {
    render(
      <TeamSurfaceDialog title="Surface" closeLabel="Close" onClose={() => {}}>
        <button type="button">First</button>
        <button type="button">Last</button>
      </TeamSurfaceDialog>,
    );
    const dialog = screen.getByRole("dialog");
    // Focus order: the ✕ close button leads, then the dialog's own controls.
    const close = screen.getByRole("button", { name: "Close" });
    const first = screen.getByRole("button", { name: "First" });
    const last = screen.getByRole("button", { name: "Last" });
    // From the dialog root, Tab enters the first focusable control.
    fireEvent.keyDown(dialog, { key: "Tab" });
    expect(document.activeElement).toBe(close);
    // From the last control, Tab wraps around — focus never escapes.
    last.focus();
    fireEvent.keyDown(dialog, { key: "Tab" });
    expect(document.activeElement).toBe(close);
    // From the leading close button, Shift+Tab wraps to the last control.
    close.focus();
    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(last);
    // Interior Tab passes through untouched — the browser owns that move
    // (jsdom's keyDown alone does not advance focus, by design).
    first.focus();
    fireEvent.keyDown(dialog, { key: "Tab" });
    expect(document.activeElement).toBe(first); // no hijack, no escape
  });
});
