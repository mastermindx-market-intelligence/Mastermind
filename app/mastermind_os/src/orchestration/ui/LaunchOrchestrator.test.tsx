// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LaunchOrchestrator } from "./LaunchOrchestrator";

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
      expect(onSubmit).toHaveBeenCalledWith({
        goal: "Valid goal",
        projectRef: "proj-alpha",
        profileRef: "prof-1",
      });
    });

    it("keeps the latch across event ticks until the owner reports progress", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
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
      await user.click(launchButton());
      expect(onSubmit).toHaveBeenCalledTimes(1);

      // Owner progress: a submitting true -> false cycle releases the latch.
      rerender(<LaunchOrchestrator {...makeProps({ onSubmit, submitting: true })} />);
      rerender(<LaunchOrchestrator {...makeProps({ onSubmit, submitting: false })} />);

      fireEvent.change(textarea, { target: { value: "Valid goal again" } });
      await user.click(launchButton());
      expect(onSubmit).toHaveBeenCalledTimes(2);
    });

    it("releases the latch on a changed error signal and preserves the draft", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      const { rerender } = render(<LaunchOrchestrator {...makeProps({ onSubmit })} />);
      const textarea = screen.getByLabelText("Goal") as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: "Retry goal" } });

      await user.click(launchButton());
      expect(onSubmit).toHaveBeenCalledTimes(1);

      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 0));
      });
      await user.click(launchButton());
      expect(onSubmit).toHaveBeenCalledTimes(1);

      rerender(<LaunchOrchestrator {...makeProps({ onSubmit, error: "Launch refused" })} />);
      expect((screen.getByLabelText("Goal") as HTMLTextAreaElement).value).toBe("Retry goal");

      await user.click(launchButton());
      expect(onSubmit).toHaveBeenCalledTimes(2);
      expect(onSubmit).toHaveBeenLastCalledWith({
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
      expect(onSubmit).toHaveBeenCalledWith({
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
    it("passes correct LaunchForm to onSubmit", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      render(<LaunchOrchestrator {...makeProps({ onSubmit })} />);
      fireEvent.change(screen.getByLabelText("Goal"), { target: { value: "My goal" } });

      await user.selectOptions(screen.getByLabelText("Project"), "proj-gamma");
      await user.selectOptions(screen.getByLabelText("Profile"), "prof-2");
      await user.click(launchButton());

      expect(onSubmit).toHaveBeenCalledWith({
        goal: "My goal",
        projectRef: "proj-gamma",
        profileRef: "prof-2",
      });
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
      expect(onSubmit).toHaveBeenCalledWith({
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
