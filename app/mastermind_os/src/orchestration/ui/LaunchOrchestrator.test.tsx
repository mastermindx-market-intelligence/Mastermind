// @vitest-environment jsdom
import { useState } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  LaunchOrchestrator,
  type LaunchCompletion,
  type LaunchForm,
} from "./LaunchOrchestrator";

const makeProps = (overrides = {}) => ({
  projects: [
    { ref: "proj-alpha", label: "Alpha Project" },
    { ref: "proj-beta", label: "Beta Project", unavailableReason: "Beta is read-only" },
    { ref: "proj-gamma", label: "Gamma Project" },
  ],
  profiles: [
    { ref: "prof-1", label: "Profile One" },
    { ref: "prof-2", label: "Profile Two" },
    { ref: "prof-3", label: "Profile Three", unavailableReason: "Profile Three requires admin" },
  ],
  submitting: false,
  onSubmit: vi.fn(),
  onCancel: vi.fn(),
  ...overrides,
});

const launchButton = () => screen.getByRole("button", { name: "Launch" }) as HTMLButtonElement;
const pendingLaunchButton = () =>
  screen.getByRole("button", { name: "Launching…" }) as HTMLButtonElement;
const goalForm = () => screen.getByLabelText("Goal").closest("form") as HTMLFormElement;

beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(() => {
  cleanup();
});

describe("LaunchOrchestrator", () => {
  describe("rendering", () => {
    it("renders project and profile selects with all choices", () => {
      render(<LaunchOrchestrator {...makeProps()} />);
      const projectSelect = screen.getByLabelText("Project") as HTMLSelectElement;
      const profileSelect = screen.getByLabelText("Profile") as HTMLSelectElement;
      expect(projectSelect.options).toHaveLength(3);
      expect(profileSelect.options).toHaveLength(3);
    });

    it("shows unavailableReason on disabled options", () => {
      render(<LaunchOrchestrator {...makeProps()} />);
      const options = (screen.getByLabelText("Project") as HTMLSelectElement).querySelectorAll("option");
      const betaOption = Array.from(options).find((o) => o.value === "proj-beta");
      expect(betaOption?.text).toContain("Beta is read-only");
      expect(betaOption?.disabled).toBe(true);
    });

    it("renders unavailable state with reason when unavailableReason is set", () => {
      render(<LaunchOrchestrator {...makeProps({ unavailableReason: "No projects available" })} />);
      expect(screen.getByText("No projects available")).toBeTruthy();
      expect(screen.queryByLabelText("Goal")).toBeNull();
      expect(screen.queryByRole("button", { name: "Launch" })).toBeNull();
    });

    it("renders error with role=alert and tabIndex=-1", () => {
      render(<LaunchOrchestrator {...makeProps({ error: "Something went wrong" })} />);
      const errorEl = screen.getByRole("alert");
      expect(errorEl.textContent).toBe("Something went wrong");
      expect(errorEl.getAttribute("tabIndex")).toBe("-1");
    });

    it("renders cancel button", () => {
      render(<LaunchOrchestrator {...makeProps()} />);
      expect(screen.getByRole("button", { name: "Cancel" })).toBeTruthy();
    });
  });

  describe("default selections", () => {
    it("selects first eligible project and profile by default", () => {
      render(<LaunchOrchestrator {...makeProps()} />);
      expect((screen.getByLabelText("Project") as HTMLSelectElement).value).toBe("proj-alpha");
      expect((screen.getByLabelText("Profile") as HTMLSelectElement).value).toBe("prof-1");
    });

    it("skips unavailable items when selecting defaults", () => {
      render(<LaunchOrchestrator {...makeProps({
        projects: [
          { ref: "p1", label: "P1", unavailableReason: "gone" },
          { ref: "p2", label: "P2" },
        ],
        profiles: [
          { ref: "f1", label: "F1", unavailableReason: "gone" },
          { ref: "f2", label: "F2" },
        ],
      })} />);
      expect((screen.getByLabelText("Project") as HTMLSelectElement).value).toBe("p2");
      expect((screen.getByLabelText("Profile") as HTMLSelectElement).value).toBe("f2");
    });

    it("falls back to first item when all items are unavailable and stays blocked", () => {
      render(<LaunchOrchestrator {...makeProps({
        projects: [
          { ref: "p1", label: "P1", unavailableReason: "gone" },
          { ref: "p2", label: "P2", unavailableReason: "also gone" },
        ],
      })} />);
      const projectSelect = screen.getByLabelText("Project") as HTMLSelectElement;
      expect(projectSelect.value).toBe("p1");
      expect(projectSelect.options[0].disabled).toBe(true);
      expect(launchButton().disabled).toBe(true);
    });
  });

  describe("form validation", () => {
    it("blocks submit when goal is empty", () => {
      render(<LaunchOrchestrator {...makeProps()} />);
      expect(launchButton().disabled).toBe(true);
    });

    it("blocks submit when goal is only whitespace", () => {
      render(<LaunchOrchestrator {...makeProps()} />);
      const textarea = screen.getByLabelText("Goal") as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: "   " } });
      expect(launchButton().disabled).toBe(true);
      fireEvent.submit(textarea.closest("form") as HTMLFormElement);
      expect(screen.getByLabelText("Project")).toBeTruthy();
    });

    it("blocks submit when selected project is unavailable", () => {
      render(<LaunchOrchestrator {...makeProps()} />);
      const projectSelect = screen.getByLabelText("Project") as HTMLSelectElement;
      act(() => {
        projectSelect.value = "proj-beta";
      });
      projectSelect.dispatchEvent(new Event("change", { bubbles: true }));
      expect(launchButton().disabled).toBe(true);
      expect(screen.getByText("Beta is read-only")).toBeTruthy();
    });

    it("blocks submit when selected profile is unavailable", () => {
      render(<LaunchOrchestrator {...makeProps()} />);
      const profileSelect = screen.getByLabelText("Profile") as HTMLSelectElement;
      act(() => {
        profileSelect.value = "prof-3";
      });
      profileSelect.dispatchEvent(new Event("change", { bubbles: true }));
      expect(launchButton().disabled).toBe(true);
      expect(screen.getByText("Profile Three requires admin")).toBeTruthy();
    });

    it("blocks submit when the selected project ref is no longer offered", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      const { rerender } = render(<LaunchOrchestrator {...makeProps({ onSubmit })} />);
      fireEvent.change(screen.getByLabelText("Goal"), { target: { value: "Valid goal" } });
      await user.selectOptions(screen.getByLabelText("Project"), "proj-gamma");
      expect(launchButton().disabled).toBe(false);

      // A later render drops that choice: the selection is now stale.
      rerender(<LaunchOrchestrator
        {...makeProps({
          onSubmit,
          projects: [
            { ref: "proj-alpha", label: "Alpha Project" },
            { ref: "proj-beta", label: "Beta Project", unavailableReason: "Beta is read-only" },
          ],
        })}
      />);
      expect(launchButton().disabled).toBe(true);
      fireEvent.submit(screen.getByLabelText("Goal").closest("form") as HTMLFormElement);
      expect(onSubmit).not.toHaveBeenCalled();
    });

    it("blocks submit when submitting is true", () => {
      render(<LaunchOrchestrator {...makeProps({ submitting: true })} />);
      const btn = screen.getByRole("button", { name: "Launching…" }) as HTMLButtonElement;
      expect(btn.disabled).toBe(true);
    });

    it("shows byte length error when goal exceeds 16384 bytes", () => {
      render(<LaunchOrchestrator {...makeProps()} />);
      const textarea = screen.getByLabelText("Goal") as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: "a".repeat(16385) } });
      expect(screen.getByText(/bytes/)).toBeTruthy();
      expect(launchButton().disabled).toBe(true);
    });

    it("allows submit when goal is exactly at the ASCII byte limit", () => {
      render(<LaunchOrchestrator {...makeProps()} />);
      const textarea = screen.getByLabelText("Goal") as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: "a".repeat(16384) } });
      expect(screen.queryByText(/bytes/)).toBeNull();
      expect(launchButton().disabled).toBe(false);
    });

    it("counts multi-byte UTF-8 characters against the byte ceiling", () => {
      render(<LaunchOrchestrator {...makeProps()} />);
      const textarea = screen.getByLabelText("Goal") as HTMLTextAreaElement;
      // é is two bytes: 8192 chars = 16384 bytes, exactly at the ceiling
      fireEvent.change(textarea, { target: { value: "é".repeat(8192) } });
      expect(screen.queryByText(/bytes/)).toBeNull();
      expect(launchButton().disabled).toBe(false);

      fireEvent.change(textarea, { target: { value: "é".repeat(8193) } });
      expect(screen.getByText(/bytes/)).toBeTruthy();
      expect(launchButton().disabled).toBe(true);
    });
  });

  describe("draft preservation", () => {
    it("preserves the draft goal when the owner reports an error", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      const { rerender } = render(<LaunchOrchestrator {...makeProps({ onSubmit })} />);
      const textarea = screen.getByLabelText("Goal") as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: "My draft goal" } });
      await user.click(launchButton());
      expect(onSubmit).toHaveBeenCalledTimes(1);

      rerender(<LaunchOrchestrator {...makeProps({ onSubmit, error: "Network error" })} />);
      expect((screen.getByLabelText("Goal") as HTMLTextAreaElement).value).toBe("My draft goal");
    });

    it("preserves draft goal on rerender without error", () => {
      const { rerender } = render(<LaunchOrchestrator {...makeProps()} />);
      const textarea = screen.getByLabelText("Goal") as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: "My draft goal" } });
      rerender(<LaunchOrchestrator {...makeProps()} />);
      expect(textarea.value).toBe("My draft goal");
    });

    it("disables the goal field while submitting", () => {
      render(<LaunchOrchestrator {...makeProps({ submitting: true })} />);
      expect((screen.getByLabelText("Goal") as HTMLTextAreaElement).disabled).toBe(true);
    });

    it("disables both selects while submitting", () => {
      render(<LaunchOrchestrator {...makeProps({ submitting: true })} />);
      expect((screen.getByLabelText("Project") as HTMLSelectElement).disabled).toBe(true);
      expect((screen.getByLabelText("Profile") as HTMLSelectElement).disabled).toBe(true);
    });
  });

  describe("duplicate submit prevention", () => {
    it("calls onSubmit only once even with rapid clicks", () => {
      const onSubmit = vi.fn();
      render(<LaunchOrchestrator {...makeProps({ onSubmit })} />);
      fireEvent.change(screen.getByLabelText("Goal"), { target: { value: "Valid goal" } });

      const submitBtn = launchButton();
      act(() => { submitBtn.click(); });
      act(() => { submitBtn.click(); });
      act(() => { submitBtn.click(); });

      expect(onSubmit).toHaveBeenCalledTimes(1);
      expect(onSubmit.mock.calls[0][0]).toEqual({
        goal: "Valid goal",
        projectRef: "proj-alpha",
        profileRef: "prof-1",
      });
    });

    it("keeps the latch across event ticks and host busy edges until the explicit completion", async () => {
      const user = userEvent.setup();
      let held: LaunchCompletion | undefined;
      const onSubmit = vi.fn((_intent: LaunchForm, onComplete: LaunchCompletion) => {
        held = onComplete;
      });
      const { rerender } = render(<LaunchOrchestrator {...makeProps({ onSubmit })} />);
      const textarea = screen.getByLabelText("Goal") as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: "Valid goal" } });

      await user.click(launchButton());
      expect(onSubmit).toHaveBeenCalledTimes(1);

      // Several event ticks pass with no owner signal at all.
      await act(async () => {
        await Promise.resolve();
        await new Promise((resolve) => setTimeout(resolve, 0));
      });
      fireEvent.submit(goalForm());
      expect(onSubmit).toHaveBeenCalledTimes(1);

      // Host pending edges alone no longer release the guard: the component's
      // own in-flight state keeps the control visibly blocked.
      rerender(<LaunchOrchestrator {...makeProps({ onSubmit, submitting: true })} />);
      rerender(<LaunchOrchestrator {...makeProps({ onSubmit, submitting: false })} />);
      expect(pendingLaunchButton().disabled).toBe(true);
      fireEvent.submit(goalForm());
      expect(onSubmit).toHaveBeenCalledTimes(1);

      // The correlated completion is what re-arms the control.
      await act(async () => {
        held?.({ status: "refused" });
      });
      await user.click(launchButton());
      expect(onSubmit).toHaveBeenCalledTimes(2);
      expect(onSubmit.mock.calls[1][0]).toEqual({
        goal: "Valid goal",
        projectRef: "proj-alpha",
        profileRef: "prof-1",
      });
    });

    it("a refused completion releases the latch and preserves the draft; a changed error string alone does not", async () => {
      const user = userEvent.setup();
      let held: LaunchCompletion | undefined;
      const onSubmit = vi.fn((_intent: LaunchForm, onComplete: LaunchCompletion) => {
        held = onComplete;
      });
      const { rerender } = render(<LaunchOrchestrator {...makeProps({ onSubmit })} />);
      const textarea = screen.getByLabelText("Goal") as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: "Retry goal" } });

      await user.click(launchButton());
      expect(onSubmit).toHaveBeenCalledTimes(1);

      // An uncorrelated error-string change is display-only: no retry authority.
      rerender(<LaunchOrchestrator {...makeProps({ onSubmit, error: "Launch refused" })} />);
      expect((screen.getByLabelText("Goal") as HTMLTextAreaElement).value).toBe("Retry goal");
      fireEvent.submit(goalForm());
      expect(onSubmit).toHaveBeenCalledTimes(1);

      await act(async () => {
        held?.({ status: "refused" });
      });
      await user.click(launchButton());
      expect(onSubmit).toHaveBeenCalledTimes(2);
      expect(onSubmit.mock.calls[1][0]).toEqual({
        goal: "Retry goal",
        projectRef: "proj-alpha",
        profileRef: "prof-1",
      });
    });

    it("allows subsequent submit after submitting clears", () => {
      const onSubmit = vi.fn();
      const { rerender } = render(
        <LaunchOrchestrator {...makeProps({ onSubmit, submitting: true })} />,
      );
      rerender(<LaunchOrchestrator {...makeProps({ onSubmit, submitting: false })} />);
      fireEvent.change(screen.getByLabelText("Goal"), { target: { value: "New goal" } });
      act(() => { launchButton().click(); });
      expect(onSubmit).toHaveBeenCalledTimes(1);
    });
  });

  describe("keyboard submission", () => {
    it("submits form when submit button is clicked with valid goal", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      render(<LaunchOrchestrator {...makeProps({ onSubmit })} />);
      fireEvent.change(screen.getByLabelText("Goal"), { target: { value: "Goal via keyboard" } });

      await user.click(launchButton());

      expect(onSubmit).toHaveBeenCalledTimes(1);
      expect(onSubmit.mock.calls[0][0]).toEqual({
        goal: "Goal via keyboard",
        projectRef: "proj-alpha",
        profileRef: "prof-1",
      });
    });

    it("does not submit when textarea is empty", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      render(<LaunchOrchestrator {...makeProps({ onSubmit })} />);
      await user.click(launchButton());
      expect(onSubmit).not.toHaveBeenCalled();
    });

    it("does not submit a whitespace-only goal from the form handler", () => {
      const onSubmit = vi.fn();
      render(<LaunchOrchestrator {...makeProps({ onSubmit })} />);
      const textarea = screen.getByLabelText("Goal") as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: " \n\t " } });
      fireEvent.submit(textarea.closest("form") as HTMLFormElement);
      expect(onSubmit).not.toHaveBeenCalled();
    });
  });

  describe("onSubmit payload", () => {
    it("passes correct LaunchForm plus a completion handle to onSubmit", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      render(<LaunchOrchestrator {...makeProps({ onSubmit })} />);
      fireEvent.change(screen.getByLabelText("Goal"), { target: { value: "My goal" } });

      await user.selectOptions(screen.getByLabelText("Project"), "proj-gamma");
      await user.selectOptions(screen.getByLabelText("Profile"), "prof-2");
      await user.click(launchButton());

      expect(onSubmit).toHaveBeenCalledTimes(1);
      expect(onSubmit.mock.calls[0][0]).toEqual({
        goal: "My goal",
        projectRef: "proj-gamma",
        profileRef: "prof-2",
      });
      expect(typeof onSubmit.mock.calls[0][1]).toBe("function");
    });

    it("passes opaque refs unchanged without interpretation", async () => {
      const onSubmit = vi.fn();
      render(<LaunchOrchestrator {...makeProps({
        projects: [{ ref: "ws:special/ref", label: "Special" }],
        profiles: [{ ref: "profile:with:colons", label: "Colon Profile" }],
        onSubmit,
      })} />);
      fireEvent.change(screen.getByLabelText("Goal"), { target: { value: "Opaque" } });
      await userEvent.setup().click(launchButton());
      expect(onSubmit.mock.calls[0][0]).toEqual({
        goal: "Opaque",
        projectRef: "ws:special/ref",
        profileRef: "profile:with:colons",
      });
    });
  });

  describe("onCancel", () => {
    it("calls onCancel when Cancel button is clicked", async () => {
      const user = userEvent.setup();
      const onCancel = vi.fn();
      render(<LaunchOrchestrator {...makeProps({ onCancel })} />);
      await user.click(screen.getByRole("button", { name: "Cancel" }));
      expect(onCancel).toHaveBeenCalledTimes(1);
    });

    it("cancel button is disabled when submitting", () => {
      render(<LaunchOrchestrator {...makeProps({ submitting: true, onCancel: vi.fn() })} />);
      expect((screen.getByRole("button", { name: "Cancel" }) as HTMLButtonElement).disabled).toBe(true);
    });
  });

  describe("selection refs", () => {
    it("renders unusual ref strings without interpretation", () => {
      render(<LaunchOrchestrator {...makeProps({
        projects: [{ ref: "REF-123", label: "Project" }],
        profiles: [{ ref: "PROF-456", label: "Profile" }],
      })} />);
      expect(screen.getByLabelText("Project")).toBeTruthy();
      expect(screen.getByLabelText("Profile")).toBeTruthy();
      expect((screen.getByLabelText("Project") as HTMLSelectElement).value).toBe("REF-123");
    });
  });

  describe("malicious text inertness", () => {
    it("renders malicious goal text as plain text, not HTML", () => {
      render(<LaunchOrchestrator {...makeProps()} />);
      const textarea = screen.getByLabelText("Goal") as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: "<img src=x onerror=alert(1)>" } });
      expect((screen.getByLabelText("Goal") as HTMLTextAreaElement).value).toBe(
        "<img src=x onerror=alert(1)>",
      );
      expect(document.querySelector("img")).toBeNull();
    });
  });
});

// ---------------------------------------------------------------------------
// Host completion contract — real wrapping hosts, not prop-driven harnesses.
// ---------------------------------------------------------------------------

describe("LaunchOrchestrator host completion contract", () => {
  const catalog = {
    projects: [{ ref: "p1", label: "P1" }],
    profiles: [{ ref: "f1", label: "F1" }],
  };
  const noop = () => undefined;
  const goalBox = () => screen.getByLabelText("Goal") as HTMLTextAreaElement;
  const fillGoal = (value: string) => fireEvent.change(goalBox(), { target: { value } });

  it("synchronous refusal resolves visibly, keeps the draft, and authorizes retry", async () => {
    const intents: LaunchForm[] = [];
    function Host() {
      return (
        <LaunchOrchestrator
          {...catalog}
          submitting={false}
          onCancel={noop}
          onSubmit={(intent, onComplete) => {
            intents.push(intent);
            onComplete({ status: "refused" });
          }}
        />
      );
    }
    render(<Host />);
    fillGoal("Sync refused");
    await act(async () => {
      launchButton().click();
    });
    expect(intents).toHaveLength(1);
    // Resolved within the same event: not stuck pending, draft intact.
    expect(launchButton().textContent).toBe("Launch");
    expect(launchButton().disabled).toBe(false);
    expect(goalBox().value).toBe("Sync refused");
    await act(async () => {
      launchButton().click();
    });
    expect(intents).toHaveLength(2);
  });

  it("synchronous acceptance clears the goal so a still-mounted parent cannot relaunch", async () => {
    const intents: LaunchForm[] = [];
    function Host() {
      return (
        <LaunchOrchestrator
          {...catalog}
          submitting={false}
          onCancel={noop}
          onSubmit={(intent, onComplete) => {
            intents.push(intent);
            onComplete({ status: "accepted" });
          }}
        />
      );
    }
    render(<Host />);
    fillGoal("Launch once");
    await act(async () => {
      launchButton().click();
    });
    expect(intents).toHaveLength(1);
    expect(goalBox().value).toBe("");
    // Blank goal blocks any accidental second launch of the same intent.
    expect(launchButton().disabled).toBe(true);
    await act(async () => {
      fireEvent.submit(goalForm());
    });
    expect(intents).toHaveLength(1);
  });

  it("an already-resolved promise with batched host state resolves and re-arms", async () => {
    let calls = 0;
    function Host() {
      const [submitting, setSubmitting] = useState(false);
      return (
        <LaunchOrchestrator
          {...catalog}
          submitting={submitting}
          onCancel={noop}
          onSubmit={(_intent, onComplete) => {
            calls += 1;
            // React batches both updates away: pending is never observed.
            setSubmitting(true);
            setSubmitting(false);
            Promise.resolve().then(() => onComplete({ status: "refused" }));
          }}
        />
      );
    }
    render(<Host />);
    fillGoal("Batched");
    await act(async () => {
      launchButton().click();
    });
    expect(calls).toBe(1);
    // The microtask completion flushed inside act: reusable, not stuck.
    expect(launchButton().textContent).toBe("Launch");
    fillGoal("Batched again");
    await act(async () => {
      launchButton().click();
    });
    expect(calls).toBe(2);
  });

  it("ordinary async pending disables the action immediately and resolves on completion", async () => {
    let settle: LaunchCompletion | undefined;
    function Host() {
      return (
        <LaunchOrchestrator
          {...catalog}
          submitting={false}
          onCancel={noop}
          onSubmit={(_intent, onComplete) => {
            settle = onComplete;
          }}
        />
      );
    }
    render(<Host />);
    fillGoal("Async goal");
    await act(async () => {
      launchButton().click();
    });
    // Pending is visible immediately after the dispatch.
    expect(pendingLaunchButton().disabled).toBe(true);
    expect(goalBox().disabled).toBe(true);
    await act(async () => {
      settle?.({ status: "refused" });
    });
    expect(launchButton().textContent).toBe("Launch");
    expect(goalBox().value).toBe("Async goal");
    await act(async () => {
      launchButton().click();
    });
    expect(screen.getByRole("button", { name: "Launching…" })).toBeTruthy();
  });

  it("a void host that never completes stays visibly blocked and never authorizes retry", async () => {
    const onSubmit = vi.fn();
    function Host() {
      return (
        <LaunchOrchestrator
          {...catalog}
          submitting={false}
          onCancel={noop}
          onSubmit={onSubmit}
        />
      );
    }
    render(<Host />);
    fillGoal("Void");
    await act(async () => {
      launchButton().click();
    });
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(pendingLaunchButton().disabled).toBe(true);
    // A direct form submit probes the handler-level latch, bypassing the
    // disabled button.
    await act(async () => {
      fireEvent.submit(goalForm());
    });
    expect(onSubmit).toHaveBeenCalledTimes(1);
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(screen.getByRole("button", { name: "Launching…" })).toBeTruthy();
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("a thrown host callback stays visibly blocked without authorizing retry", async () => {
    const attempts: string[] = [];
    function Host() {
      return (
        <LaunchOrchestrator
          {...catalog}
          submitting={false}
          onCancel={noop}
          onSubmit={(intent) => {
            attempts.push(intent.goal);
            throw new Error("host exploded");
          }}
        />
      );
    }
    render(<Host />);
    fillGoal("Boom");
    await act(async () => {
      launchButton().click();
    });
    expect(attempts).toHaveLength(1);
    expect(pendingLaunchButton().disabled).toBe(true);
    await act(async () => {
      fireEvent.submit(goalForm());
    });
    expect(attempts).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Launching…" })).toBeTruthy();
  });

  it("an uncorrelated error-string change is display-only and never unlocks the guard", async () => {
    let calls = 0;
    function Host() {
      const [error, setError] = useState<string | undefined>(undefined);
      return (
        <LaunchOrchestrator
          {...catalog}
          submitting={false}
          error={error}
          onCancel={noop}
          onSubmit={(_intent, onComplete) => {
            calls += 1;
            setError(`refused-${calls}`);
          }}
        />
      );
    }
    render(<Host />);
    fillGoal("Err");
    await act(async () => {
      launchButton().click();
    });
    expect(calls).toBe(1);
    expect(screen.getByRole("alert").textContent).toBe("refused-1");
    // Distinct error strings keep arriving, but none of them is authority.
    await act(async () => {
      fireEvent.submit(goalForm());
    });
    expect(calls).toBe(1);
    expect(pendingLaunchButton().disabled).toBe(true);
  });

  it("a stored completion handle reconciles the same pending launch across rerenders", async () => {
    let held: LaunchCompletion | undefined;
    const onSubmit = vi.fn((_intent: LaunchForm, onComplete: LaunchCompletion) => {
      held = onComplete;
    });
    const { rerender } = render(
      <LaunchOrchestrator {...catalog} submitting={false} onCancel={noop} onSubmit={onSubmit} />,
    );
    fillGoal("Reconcile");
    await act(async () => {
      launchButton().click();
    });
    expect(onSubmit).toHaveBeenCalledTimes(1);

    // Unrelated rerenders do not remount the component or drop the pending
    // action; the owner still holds the correlated handle.
    rerender(
      <LaunchOrchestrator
        {...catalog}
        submitting={false}
        error="unrelated display text"
        onCancel={noop}
        onSubmit={onSubmit}
      />,
    );
    expect(screen.getByRole("button", { name: "Launching…" })).toBeTruthy();

    // The owner resolves the same pending action out-of-band, no remount.
    await act(async () => {
      held?.({ status: "accepted" });
    });
    expect(goalBox().value).toBe("");
    expect(launchButton().textContent).toBe("Launch");
  });

  const invalidLaunchOutcomes: Array<{
    name: string;
    invoke: (complete: (outcome?: unknown) => void) => void;
  }> = [
    { name: "missing argument", invoke: (complete) => complete() },
    { name: "null", invoke: (complete) => complete(null) },
    { name: "array", invoke: (complete) => complete(["accepted"]) },
    { name: "unknown status", invoke: (complete) => complete({ status: "nope" }) },
    { name: "nonstring status", invoke: (complete) => complete({ status: 1 }) },
    {
      name: "throwing getter",
      invoke: (complete) =>
        complete({
          get status() {
            throw new Error("status getter exploded");
          },
        }),
    },
    {
      name: "proxy value",
      invoke: (complete) =>
        complete(
          new Proxy({ status: "accepted" as const }, {
            get() {
              return "nope";
            },
          }),
        ),
    },
  ];

  it.each(invalidLaunchOutcomes)(
    "invalid launch $name stays pending, does not throw, then valid refused reconciles without duplicate dispatch",
    async ({ invoke }) => {
      let held: LaunchCompletion | undefined;
      const onSubmit = vi.fn((_intent: LaunchForm, onComplete: LaunchCompletion) => {
        held = onComplete;
      });
      function Host() {
        return (
          <LaunchOrchestrator
            {...catalog}
            submitting={false}
            onCancel={noop}
            onSubmit={onSubmit}
          />
        );
      }
      render(<Host />);
      fillGoal("Invalid then valid");
      await act(async () => {
        launchButton().click();
      });
      expect(onSubmit).toHaveBeenCalledTimes(1);
      expect(pendingLaunchButton().disabled).toBe(true);

      await act(async () => {
        invoke(held as (outcome?: unknown) => void);
      });
      expect(pendingLaunchButton().disabled).toBe(true);
      expect(goalBox().value).toBe("Invalid then valid");
      await act(async () => {
        fireEvent.submit(goalForm());
      });
      expect(onSubmit).toHaveBeenCalledTimes(1);

      await act(async () => {
        held?.({ status: "refused" });
      });
      expect(launchButton().textContent).toBe("Launch");
      expect(goalBox().value).toBe("Invalid then valid");
      await act(async () => {
        launchButton().click();
      });
      expect(onSubmit).toHaveBeenCalledTimes(2);
    },
  );
});

// ---------------------------------------------------------------------------
// Stale-selection retention and explicit reselection
// ---------------------------------------------------------------------------

describe("LaunchOrchestrator stale selection retention", () => {
  it("retains a stale project ref as a disabled previous-selection option with explanation until explicit reselection", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    const { rerender } = render(
      <LaunchOrchestrator {...makeProps({ onSubmit })} />,
    );
    fireEvent.change(screen.getByLabelText("Goal"), {
      target: { value: "Stale project goal" },
    });
    await user.selectOptions(screen.getByLabelText("Project"), "proj-gamma");
    await user.selectOptions(screen.getByLabelText("Profile"), "prof-2");
    expect(launchButton().disabled).toBe(false);

    // Drop the chosen project, leaving exactly one eligible option behind.
    rerender(
      <LaunchOrchestrator
        {...makeProps({
          onSubmit,
          projects: [
            { ref: "proj-alpha", label: "Alpha Project" },
            {
              ref: "proj-beta",
              label: "Beta Project",
              unavailableReason: "Beta is read-only",
            },
          ],
        })}
      />,
    );

    const projectSelect = screen.getByLabelText("Project") as HTMLSelectElement;
    // Stale ref remains the displayed value rather than collapsing to a default.
    expect(projectSelect.value).toBe("proj-gamma");
    const staleOption = Array.from(projectSelect.options).find(
      (o) => o.value === "proj-gamma",
    );
    expect(staleOption).toBeTruthy();
    expect(staleOption?.disabled).toBe(true);
    // Accessible explanation text and the aria-describedby link back to it.
    expect(screen.getByText(/^Your previous project/i)).toBeTruthy();
    const describedById = projectSelect.getAttribute("aria-describedby");
    expect(describedById).toBeTruthy();
    expect(
      document.getElementById(describedById as string)?.textContent,
    ).toMatch(/previous project/i);
    // Goal draft survives the catalog churn untouched.
    expect((screen.getByLabelText("Goal") as HTMLTextAreaElement).value).toBe(
      "Stale project goal",
    );
    // Forced submit is refused while the selection is stale; no dispatch.
    expect(launchButton().disabled).toBe(true);
    fireEvent.submit(goalForm());
    expect(onSubmit).not.toHaveBeenCalled();

    // Explicit eligible reselection clears staleness and re-arms a single dispatch.
    await user.selectOptions(projectSelect, "proj-alpha");
    expect(launchButton().disabled).toBe(false);
    await user.click(launchButton());
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit.mock.calls[0][0]).toEqual({
      goal: "Stale project goal",
      projectRef: "proj-alpha",
      profileRef: "prof-2",
    });
  });

  it("retains a stale profile ref as a disabled previous-selection option with explanation until explicit reselection", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    const { rerender } = render(
      <LaunchOrchestrator {...makeProps({ onSubmit })} />,
    );
    fireEvent.change(screen.getByLabelText("Goal"), {
      target: { value: "Stale profile goal" },
    });
    await user.selectOptions(screen.getByLabelText("Project"), "proj-alpha");
    await user.selectOptions(screen.getByLabelText("Profile"), "prof-2");
    expect(launchButton().disabled).toBe(false);

    rerender(
      <LaunchOrchestrator
        {...makeProps({
          onSubmit,
          profiles: [
            { ref: "prof-1", label: "Profile One" },
            {
              ref: "prof-3",
              label: "Profile Three",
              unavailableReason: "Profile Three requires admin",
            },
          ],
        })}
      />,
    );

    const profileSelect = screen.getByLabelText("Profile") as HTMLSelectElement;
    expect(profileSelect.value).toBe("prof-2");
    const staleOption = Array.from(profileSelect.options).find(
      (o) => o.value === "prof-2",
    );
    expect(staleOption).toBeTruthy();
    expect(staleOption?.disabled).toBe(true);
    expect(screen.getByText(/^Your previous profile/i)).toBeTruthy();
    const describedById = profileSelect.getAttribute("aria-describedby");
    expect(describedById).toBeTruthy();
    expect(
      document.getElementById(describedById as string)?.textContent,
    ).toMatch(/previous profile/i);
    expect((screen.getByLabelText("Goal") as HTMLTextAreaElement).value).toBe(
      "Stale profile goal",
    );
    expect(launchButton().disabled).toBe(true);
    fireEvent.submit(goalForm());
    expect(onSubmit).not.toHaveBeenCalled();

    await user.selectOptions(profileSelect, "prof-1");
    expect(launchButton().disabled).toBe(false);
    await user.click(launchButton());
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit.mock.calls[0][0]).toEqual({
      goal: "Stale profile goal",
      projectRef: "proj-alpha",
      profileRef: "prof-1",
    });
  });

  it("retains both stale project and profile with explanation, blocking submit until explicit dual reselect", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    const twoEach = (override: Record<string, unknown> = {}) => ({
      ...makeProps({
        projects: [
          { ref: "proj-alpha", label: "Alpha Project" },
          { ref: "proj-gamma", label: "Gamma Project" },
        ],
        profiles: [
          { ref: "prof-1", label: "Profile One" },
          { ref: "prof-2", label: "Profile Two" },
        ],
      }),
      onSubmit,
      ...override,
    });

    const { rerender } = render(<LaunchOrchestrator {...twoEach()} />);
    fireEvent.change(screen.getByLabelText("Goal"), {
      target: { value: "Both stale" },
    });
    await user.selectOptions(screen.getByLabelText("Project"), "proj-gamma");
    await user.selectOptions(screen.getByLabelText("Profile"), "prof-2");
    expect(launchButton().disabled).toBe(false);

    rerender(
      <LaunchOrchestrator
        {...twoEach({
          onSubmit,
          projects: [{ ref: "proj-alpha", label: "Alpha Project" }],
          profiles: [{ ref: "prof-1", label: "Profile One" }],
        })}
      />,
    );

    const projectSelect = screen.getByLabelText("Project") as HTMLSelectElement;
    const profileSelect = screen.getByLabelText("Profile") as HTMLSelectElement;
    expect(projectSelect.value).toBe("proj-gamma");
    expect(profileSelect.value).toBe("prof-2");
    expect(screen.getByText(/^Your previous project/i)).toBeTruthy();
    expect(screen.getByText(/^Your previous profile/i)).toBeTruthy();
    expect((screen.getByLabelText("Goal") as HTMLTextAreaElement).value).toBe(
      "Both stale",
    );
    expect(launchButton().disabled).toBe(true);
    fireEvent.submit(goalForm());
    expect(onSubmit).not.toHaveBeenCalled();

    // Resolving only the stale project keeps the form blocked on the profile.
    await user.selectOptions(projectSelect, "proj-alpha");
    expect(launchButton().disabled).toBe(true);
    await user.selectOptions(profileSelect, "prof-1");
    expect(launchButton().disabled).toBe(false);
    await user.click(launchButton());
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit.mock.calls[0][0]).toEqual({
      goal: "Both stale",
      projectRef: "proj-alpha",
      profileRef: "prof-1",
    });
  });

  it.each(["Project", "Profile"] as const)("describes an empty %s list without inventing a previous choice", (field) => {
    const onSubmit = vi.fn();
    render(<LaunchOrchestrator {...makeProps({ onSubmit,
      ...(field === "Project" ? { projects: [] } : { profiles: [] }),
    })} />);
    fireEvent.change(screen.getByLabelText("Goal"), { target: { value: "Retain an unstarted goal" } });
    const select = screen.getByLabelText(field) as HTMLSelectElement;
    expect(select.options).toHaveLength(1);
    expect(select.options[0].value).toBe("");
    expect(select.options[0].disabled).toBe(true);
    expect(select.value).toBe("");
    const description = document.getElementById(select.getAttribute("aria-describedby")!);
    expect(description?.textContent).toBe(`No ${field.toLowerCase()}s are currently available.`);
    expect(description?.textContent).not.toMatch(/previous/i);
    expect(select.getAttribute("aria-invalid")).toBe("true");
    expect(launchButton().disabled).toBe(true);
    fireEvent.submit(goalForm());
    expect(onSubmit).not.toHaveBeenCalled();
    expect((screen.getByLabelText("Goal") as HTMLTextAreaElement).value).toBe("Retain an unstarted goal");
  });

  it("preserves a never-selected fresh form default when the choice set grows", () => {
    const { rerender } = render(<LaunchOrchestrator {...makeProps()} />);
    expect((screen.getByLabelText("Project") as HTMLSelectElement).value).toBe(
      "proj-alpha",
    );
    rerender(
      <LaunchOrchestrator
        {...makeProps({
          projects: [
            { ref: "proj-alpha", label: "Alpha Project" },
            { ref: "proj-delta", label: "Delta Project" },
            {
              ref: "proj-beta",
              label: "Beta Project",
              unavailableReason: "Beta is read-only",
            },
            { ref: "proj-gamma", label: "Gamma Project" },
          ],
        })}
      />,
    );
    expect((screen.getByLabelText("Project") as HTMLSelectElement).value).toBe(
      "proj-alpha",
    );
  });

  it("keeps the pending latch when the chosen option is dropped mid-pending; no second dispatch", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    function Host() {
      const [projects, setProjects] = useState([
        { ref: "proj-alpha", label: "Alpha Project" },
        { ref: "proj-gamma", label: "Gamma Project" },
      ]);
      const [profiles] = useState([
        { ref: "prof-1", label: "Profile One" },
        { ref: "prof-2", label: "Profile Two" },
      ]);
      return (
        <LaunchOrchestrator
          projects={projects}
          profiles={profiles}
          submitting={false}
          onSubmit={(intent) => {
            onSubmit(intent);
            // Owner churns the catalog while the launch never completes.
            if (intent.projectRef === "proj-gamma") {
              setProjects([{ ref: "proj-alpha", label: "Alpha Project" }]);
            }
          }}
          onCancel={vi.fn()}
        />
      );
    }
    render(<Host />);
    fireEvent.change(screen.getByLabelText("Goal"), {
      target: { value: "Churn goal" },
    });
    await user.selectOptions(screen.getByLabelText("Project"), "proj-gamma");
    await user.selectOptions(screen.getByLabelText("Profile"), "prof-2");
    expect(launchButton().disabled).toBe(false);
    await user.click(launchButton());
    expect(onSubmit).toHaveBeenCalledTimes(1);
    // Options churned mid-pending; the latch keeps the form visibly blocked.
    expect(pendingLaunchButton().disabled).toBe(true);
    fireEvent.submit(goalForm());
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(pendingLaunchButton().disabled).toBe(true);
    expect(
      (screen.getByLabelText("Project") as HTMLSelectElement).value,
    ).toBe("proj-gamma");
  });
});
