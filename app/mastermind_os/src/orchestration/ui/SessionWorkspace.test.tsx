// @vitest-environment jsdom
import { useState } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SessionWorkspace, type SessionCompletion } from "./SessionWorkspace";

const makeProps = (overrides = {}) =>
  ({
    sessionKey: "session-1",
    title: "Test Session",
    messages: [
      { id: "msg-1", role: "user" as const, text: "Hello" },
      { id: "msg-2", role: "assistant" as const, text: "Hi there" },
    ],
    observedAt: "2026-09-26T10:00:00Z",
    connection: "connected" as const,
    coverage: "Complete",
    turnBusy: false,
    sending: false,
    onSend: vi.fn(),
    onStop: undefined,
    ...overrides,
  });

const sendButton = () => screen.getByRole("button", { name: "Send" }) as HTMLButtonElement;
const pendingSendButton = () =>
  screen.getByRole("button", { name: "Sending…" }) as HTMLButtonElement;
const messageBox = () => screen.getByLabelText("Message") as HTMLTextAreaElement;
const sendForm = () => messageBox().closest("form") as HTMLFormElement;

beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(() => {
  cleanup();
});

describe("SessionWorkspace", () => {
  describe("rendering", () => {
    it("renders title and connection status", () => {
      render(<SessionWorkspace {...makeProps()} />);
      expect(screen.getByText("Test Session")).toBeTruthy();
      expect(screen.getByText(/Connected/)).toBeTruthy();
    });

    it("renders messages with correct roles", () => {
      render(<SessionWorkspace {...makeProps()} />);
      expect(screen.getByText("Hello")).toBeTruthy();
      expect(screen.getByText("Hi there")).toBeTruthy();
      expect(screen.getByText("User")).toBeTruthy();
      expect(screen.getByText("Assistant")).toBeTruthy();
    });

    it("renders activity role correctly", () => {
      render(
        <SessionWorkspace
          {...makeProps({
            messages: [{ id: "act-1", role: "activity", text: "System started" }],
          })}
        />,
      );
      expect(screen.getByText("System started")).toBeTruthy();
      expect(screen.getByText("Activity")).toBeTruthy();
    });

    it("renders observedAt as a time element and keeps it separate from coverage", () => {
      render(<SessionWorkspace {...makeProps()} />);
      const time = screen.getByText("2026-09-26T10:00:00Z").closest("time");
      expect(time?.getAttribute("dateTime")).toBe("2026-09-26T10:00:00Z");
      expect(screen.getByText(/Complete/)).toBeTruthy();
    });

    it("omits the observed timestamp when observedAt is null", () => {
      render(<SessionWorkspace {...makeProps({ observedAt: null })} />);
      expect(screen.queryByText(/Observed at/)).toBeNull();
      expect(screen.getByText(/Complete/)).toBeTruthy();
    });

    it("renders unavailable state with reason", () => {
      render(
        <SessionWorkspace {...makeProps({ unavailableReason: "Session unavailable" })} />,
      );
      expect(screen.getByText("Session unavailable")).toBeTruthy();
      expect(screen.queryByLabelText("Message")).toBeNull();
      expect(screen.queryByRole("button", { name: "Send" })).toBeNull();
    });

    it("renders empty messages state", () => {
      render(<SessionWorkspace {...makeProps({ messages: [] })} />);
      expect(screen.getByText("No messages in this session.")).toBeTruthy();
    });

    it("renders error with role=alert and tabIndex=-1", () => {
      render(<SessionWorkspace {...makeProps({ error: "Send failed" })} />);
      const alert = screen.getByRole("alert");
      expect(alert.textContent).toBe("Send failed");
      expect(alert.getAttribute("tabIndex")).toBe("-1");
    });

    it("renders disconnected notice when connection is disconnected", () => {
      render(<SessionWorkspace {...makeProps({ connection: "disconnected" })} />);
      const notices = screen.queryAllByText(
        "Session is disconnected. Messages cannot be sent until the connection is restored.",
      );
      expect(notices.length).toBeGreaterThan(0);
    });

    it("renders unknown connection status", () => {
      render(<SessionWorkspace {...makeProps({ connection: "unknown" })} />);
      expect(screen.getByText(/Connection unknown/i)).toBeTruthy();
    });
  });

  describe("send conditions", () => {
    it("enables send when connected, not busy, not sending, and has text", () => {
      render(<SessionWorkspace {...makeProps()} />);
      fireEvent.change(messageBox(), { target: { value: "Hello" } });
      expect(sendButton().disabled).toBe(false);
    });

    it("disables send when connection is disconnected", () => {
      render(<SessionWorkspace {...makeProps({ connection: "disconnected" })} />);
      expect(sendButton().disabled).toBe(true);
    });

    it("disables send when turnBusy is true", () => {
      render(<SessionWorkspace {...makeProps({ turnBusy: true })} />);
      expect(sendButton().disabled).toBe(true);
    });

    it("disables send when sending is true", () => {
      render(<SessionWorkspace {...makeProps({ sending: true })} />);
      expect((screen.getByRole("button", { name: "Sending…" }) as HTMLButtonElement).disabled).toBe(true);
    });

    it("disables send when textarea is empty", () => {
      render(<SessionWorkspace {...makeProps()} />);
      expect(sendButton().disabled).toBe(true);
    });

    it("disables send for whitespace-only text and the handler refuses it", () => {
      const onSend = vi.fn();
      render(<SessionWorkspace {...makeProps({ onSend })} />);
      fireEvent.change(messageBox(), { target: { value: "  \n\t " } });
      expect(sendButton().disabled).toBe(true);
      fireEvent.submit(sendForm());
      expect(onSend).not.toHaveBeenCalled();
    });

    it("disables send when the message exceeds the UTF-8 ceiling", () => {
      render(<SessionWorkspace {...makeProps()} />);
      fireEvent.change(messageBox(), { target: { value: "a".repeat(16385) } });
      expect(sendButton().disabled).toBe(true);
    });

    it("disables the send textarea when connection is disconnected", () => {
      render(<SessionWorkspace {...makeProps({ connection: "disconnected" })} />);
      expect(messageBox().disabled).toBe(true);
    });

    it("disables the send textarea when turnBusy is true", () => {
      render(<SessionWorkspace {...makeProps({ turnBusy: true })} />);
      expect(messageBox().disabled).toBe(true);
    });

    it("disables the send textarea when sending is true", () => {
      render(<SessionWorkspace {...makeProps({ sending: true })} />);
      expect(messageBox().disabled).toBe(true);
    });
  });

  describe("stop button", () => {
    it("renders stop button when stopLabel is provided", () => {
      render(<SessionWorkspace {...makeProps({ stopLabel: "Interrupt turn" as const })} />);
      expect(screen.getByRole("button", { name: "Interrupt turn" })).toBeTruthy();
    });

    it("does not render stop button when stopLabel is undefined", () => {
      render(<SessionWorkspace {...makeProps({ onStop: undefined })} />);
      expect(screen.queryByRole("button", { name: "Interrupt turn" })).toBeNull();
    });

    it("does not render a stop button without an explicit label", () => {
      render(<SessionWorkspace {...makeProps({ onStop: vi.fn() })} />);
      expect(screen.queryByRole("button", { name: "Request stop" })).toBeNull();
    });

    it("disables stop button when stopping is true", () => {
      render(
        <SessionWorkspace
          {...makeProps({
            stopLabel: "Request stop" as const,
            stopping: true,
            onStop: vi.fn(),
          })}
        />,
      );
      const btn = screen.getByRole("button", { name: "Stopping…" }) as HTMLButtonElement;
      expect(btn.disabled).toBe(true);
    });

    it("calls onStop when stop button is clicked", async () => {
      const user = userEvent.setup();
      const onStop = vi.fn();
      render(
        <SessionWorkspace {...makeProps({ stopLabel: "Interrupt turn" as const, onStop })} />,
      );
      await user.click(screen.getByRole("button", { name: "Interrupt turn" }));
      expect(onStop).toHaveBeenCalledTimes(1);
      expect(typeof onStop.mock.calls[0][0]).toBe("function");
    });
  });

  describe("UTF-8 length validation", () => {
    it("shows error when text exceeds 16384 bytes", () => {
      render(<SessionWorkspace {...makeProps()} />);
      fireEvent.change(messageBox(), { target: { value: "a".repeat(16385) } });
      expect(screen.getByText(/bytes/)).toBeTruthy();
      expect(sendButton().disabled).toBe(true);
    });

    it("does not show error at exactly 16384 bytes", () => {
      render(<SessionWorkspace {...makeProps()} />);
      fireEvent.change(messageBox(), { target: { value: "a".repeat(16384) } });
      expect(screen.queryByText(/bytes/)).toBeNull();
      expect(sendButton().disabled).toBe(false);
    });

    it("counts multi-byte UTF-8 characters against the byte ceiling", () => {
      render(<SessionWorkspace {...makeProps()} />);
      // é is two bytes: 8193 chars = 16386 bytes
      fireEvent.change(messageBox(), { target: { value: "é".repeat(8193) } });
      expect(screen.getByText(/bytes/)).toBeTruthy();
      expect(sendButton().disabled).toBe(true);
    });
  });

  describe("draft preservation", () => {
    it("preserves draft text on error", () => {
      render(<SessionWorkspace {...makeProps({ error: "Send failed" })} />);
      fireEvent.change(messageBox(), { target: { value: "My draft message" } });
      expect(messageBox().value).toBe("My draft message");
    });

    it("keeps the draft until the owner reports a completed send", async () => {
      const user = userEvent.setup();
      const onSend = vi.fn();
      render(<SessionWorkspace {...makeProps({ onSend })} />);
      fireEvent.change(messageBox(), { target: { value: "My message" } });

      await user.click(sendButton());
      expect(onSend).toHaveBeenCalledTimes(1);
      // Firing onSend alone must not drop the text: no completion yet.
      expect(messageBox().value).toBe("My message");

      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 0));
      });
      expect(messageBox().value).toBe("My message");
    });

    it("clears the draft after an accepted completion", async () => {
      const user = userEvent.setup();
      let held: SessionCompletion | undefined;
      const onSend = vi.fn((_text: string, onComplete: SessionCompletion) => {
        held = onComplete;
      });
      render(<SessionWorkspace {...makeProps({ onSend })} />);
      fireEvent.change(messageBox(), { target: { value: "My message" } });

      await user.click(sendButton());
      expect(onSend).toHaveBeenCalledTimes(1);
      await act(async () => {
        held?.({ status: "accepted" });
      });
      expect(onSend).toHaveBeenCalledTimes(1);
      expect(messageBox().value).toBe("");
      expect(sendButton().disabled).toBe(true);
    });

    it("preserves the draft when the send ends in a refusal shown as an error", async () => {
      const user = userEvent.setup();
      let held: SessionCompletion | undefined;
      const onSend = vi.fn((_text: string, onComplete: SessionCompletion) => {
        held = onComplete;
      });
      const { rerender } = render(<SessionWorkspace {...makeProps({ onSend })} />);
      fireEvent.change(messageBox(), { target: { value: "Do not lose me" } });

      await user.click(sendButton());
      await act(async () => {
        held?.({ status: "refused" });
      });
      rerender(
        <SessionWorkspace {...makeProps({ onSend, error: "Send failed" })} />,
      );

      expect(onSend).toHaveBeenCalledTimes(1);
      expect(messageBox().value).toBe("Do not lose me");
      expect(screen.getByRole("alert").textContent).toBe("Send failed");

      // The refusal released the guard, so the same text can be retried.
      await user.click(sendButton());
      expect(onSend).toHaveBeenCalledTimes(2);
      expect(onSend.mock.calls[1][0]).toBe("Do not lose me");
    });

    it("a changed error string alone never unlocks the send guard", async () => {
      const user = userEvent.setup();
      let held: SessionCompletion | undefined;
      const onSend = vi.fn((_text: string, onComplete: SessionCompletion) => {
        held = onComplete;
      });
      const { rerender } = render(<SessionWorkspace {...makeProps({ onSend })} />);
      fireEvent.change(messageBox(), { target: { value: "Retry me" } });

      await user.click(sendButton());
      expect(onSend).toHaveBeenCalledTimes(1);

      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 0));
      });
      // Uncorrelated error text is display-only: no retry authority.
      rerender(<SessionWorkspace {...makeProps({ onSend, error: "Rejected" })} />);
      fireEvent.submit(sendForm());
      expect(onSend).toHaveBeenCalledTimes(1);
      expect(pendingSendButton().disabled).toBe(true);

      await act(async () => {
        held?.({ status: "refused" });
      });
      await user.click(sendButton());
      expect(onSend).toHaveBeenCalledTimes(2);
      expect(onSend.mock.calls[1][0]).toBe("Retry me");
    });
  });

  describe("identity switch", () => {
    it("clears draft when sessionKey changes", () => {
      const { rerender } = render(<SessionWorkspace {...makeProps()} />);
      fireEvent.change(messageBox(), { target: { value: "My message" } });
      expect(messageBox().value).toBe("My message");

      rerender(<SessionWorkspace {...makeProps({ sessionKey: "session-2" })} />);
      expect(messageBox().value).toBe("");
    });

    it("clears error when sessionKey changes", () => {
      const { rerender } = render(
        <SessionWorkspace {...makeProps({ error: "Previous error" })} />,
      );
      expect(screen.getByRole("alert")).toBeTruthy();

      rerender(<SessionWorkspace {...makeProps({ sessionKey: "session-2" })} />);
      expect(screen.queryByRole("alert")).toBeNull();
    });

    it("clears messages when sessionKey changes", () => {
      const { rerender } = render(<SessionWorkspace {...makeProps()} />);
      expect(screen.getByText("Hello")).toBeTruthy();

      rerender(
        <SessionWorkspace {...makeProps({ sessionKey: "session-2", messages: [] })} />,
      );
      expect(screen.queryByText("Hello")).toBeNull();
      expect(screen.queryByText("Hi there")).toBeNull();
    });

    it("clears the send latch on session change without re-sending the old text", async () => {
      const user = userEvent.setup();
      const onSend = vi.fn();
      const { rerender } = render(<SessionWorkspace {...makeProps({ onSend })} />);
      fireEvent.change(messageBox(), { target: { value: "First" } });
      await user.click(sendButton());
      expect(onSend).toHaveBeenCalledTimes(1);

      // No completion, then a new session identity.
      rerender(<SessionWorkspace {...makeProps({ onSend, sessionKey: "session-2" })} />);
      expect(messageBox().value).toBe("");

      fireEvent.change(messageBox(), { target: { value: "Second" } });
      await user.click(sendButton());
      expect(onSend).toHaveBeenCalledTimes(2);
      expect(onSend.mock.calls[1][0]).toBe("Second");
    });
  });

  describe("duplicate send prevention", () => {
    it("calls onSend only once across event ticks, then again after the explicit completion", async () => {
      const user = userEvent.setup();
      let held: SessionCompletion | undefined;
      const onSend = vi.fn((_text: string, onComplete: SessionCompletion) => {
        held = onComplete;
      });
      render(<SessionWorkspace {...makeProps({ onSend })} />);
      fireEvent.change(messageBox(), { target: { value: "Hello" } });

      await user.click(sendButton());
      // A direct form submit probes the handler-level latch while the control
      // is visibly pending ("Sending…", disabled).
      fireEvent.submit(sendForm());
      expect(onSend).toHaveBeenCalledTimes(1);
      expect(onSend.mock.calls[0][0]).toBe("Hello");

      // Ticks pass with no completion: still exactly one send.
      await act(async () => {
        await Promise.resolve();
        await new Promise((resolve) => setTimeout(resolve, 0));
      });
      fireEvent.submit(sendForm());
      expect(onSend).toHaveBeenCalledTimes(1);

      // The correlated completion is what re-arms the control.
      await act(async () => {
        held?.({ status: "refused" });
      });
      fireEvent.change(messageBox(), { target: { value: "Second" } });
      await user.click(sendButton());
      expect(onSend).toHaveBeenCalledTimes(2);
      expect(onSend.mock.calls[1][0]).toBe("Second");
    });
  });

  describe("onSend payload", () => {
    it("passes text and a completion handle to onSend", async () => {
      const user = userEvent.setup();
      const onSend = vi.fn();
      render(<SessionWorkspace {...makeProps({ onSend })} />);
      fireEvent.change(messageBox(), { target: { value: "Hello world" } });

      await user.click(sendButton());
      expect(onSend).toHaveBeenCalledTimes(1);
      expect(onSend.mock.calls[0][0]).toBe("Hello world");
      expect(typeof onSend.mock.calls[0][1]).toBe("function");
    });

    it("sends after a completed cycle for freshly typed text", async () => {
      const user = userEvent.setup();
      let held: SessionCompletion | undefined;
      const onSend = vi.fn((_text: string, onComplete: SessionCompletion) => {
        held = onComplete;
      });
      render(<SessionWorkspace {...makeProps({ onSend })} />);
      fireEvent.change(messageBox(), { target: { value: "Hello" } });
      await user.click(sendButton());
      await act(async () => {
        held?.({ status: "accepted" });
      });

      fireEvent.change(messageBox(), { target: { value: "Again" } });
      await user.click(sendButton());
      expect(onSend).toHaveBeenCalledTimes(2);
      expect(onSend.mock.calls[1][0]).toBe("Again");
    });
  });

  describe("busy turn display", () => {
    it("shows disabled textarea when turnBusy is true", () => {
      render(<SessionWorkspace {...makeProps({ turnBusy: true })} />);
      expect(messageBox().disabled).toBe(true);
    });

    it("shows disabled textarea when sending is true", () => {
      render(<SessionWorkspace {...makeProps({ sending: true })} />);
      expect(messageBox().disabled).toBe(true);
    });

    it("textarea placeholder reflects busy state", () => {
      render(<SessionWorkspace {...makeProps({ turnBusy: true })} />);
      expect(messageBox().placeholder).toBe("Wait for the current turn to complete.");
    });

    it("textarea placeholder reflects sending state", () => {
      render(<SessionWorkspace {...makeProps({ sending: true })} />);
      expect(messageBox().placeholder).toBe("Wait for the current turn to complete.");
    });

    it("textarea placeholder reflects disconnected state", () => {
      render(<SessionWorkspace {...makeProps({ connection: "disconnected" })} />);
      expect(messageBox().placeholder).toBe("Connect to send messages.");
    });
  });

  describe("message rendering safety", () => {
    it("renders malicious text as plain text", () => {
      render(
        <SessionWorkspace
          {...makeProps({
            messages: [
              { id: "bad-1", role: "user" as const, text: "<img src=x onerror=alert(1)>" },
            ],
          })}
        />,
      );
      expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeTruthy();
      expect(document.querySelector("img")).toBeNull();
    });

    it("renders script injection attempt as text", () => {
      render(
        <SessionWorkspace
          {...makeProps({
            messages: [
              { id: "bad-2", role: "assistant" as const, text: "<script>alert(1)</script>Hello" },
            ],
          })}
        />,
      );
      expect(screen.getByText("<script>alert(1)</script>Hello")).toBeTruthy();
      expect(document.querySelector("script")).toBeNull();
    });

    it("uses stable message keys", () => {
      render(
        <SessionWorkspace
          {...makeProps({
            messages: [
              { id: "msg-1", role: "user", text: "First" },
              { id: "msg-2", role: "assistant", text: "Second" },
              { id: "msg-3", role: "activity", text: "Third" },
            ],
          })}
        />,
      );
      expect(screen.getAllByRole("listitem")).toHaveLength(3);
    });
  });

  describe("coverage display", () => {
    it("displays coverage value", () => {
      render(<SessionWorkspace {...makeProps({ coverage: "Partial coverage" })} />);
      expect(screen.getByText(/Partial coverage/)).toBeTruthy();
    });

    it("keeps the draft when only coverage or observedAt change", () => {
      const { rerender } = render(<SessionWorkspace {...makeProps()} />);
      fireEvent.change(messageBox(), { target: { value: "Still here" } });

      rerender(
        <SessionWorkspace
          {...makeProps({ coverage: "Partial coverage", observedAt: "2026-09-26T11:00:00Z" })}
        />,
      );
      expect(messageBox().value).toBe("Still here");
      expect(screen.getByText(/Partial coverage/)).toBeTruthy();
      expect(screen.getByText("2026-09-26T11:00:00Z")).toBeTruthy();
    });
  });

  describe("stopLabel variants", () => {
    it("renders 'Request stop' when that label is passed", () => {
      render(
        <SessionWorkspace {...makeProps({ stopLabel: "Request stop" as const, onStop: vi.fn() })} />,
      );
      expect(screen.getByRole("button", { name: "Request stop" })).toBeTruthy();
    });

    it("renders 'Interrupt turn' when that label is passed", () => {
      render(
        <SessionWorkspace
          {...makeProps({ stopLabel: "Interrupt turn" as const, onStop: vi.fn() })}
        />,
      );
      expect(screen.getByRole("button", { name: "Interrupt turn" })).toBeTruthy();
    });
  });
});

// ---------------------------------------------------------------------------
// Host completion contract — real wrapping hosts, not prop-driven harnesses.
// ---------------------------------------------------------------------------

describe("SessionWorkspace host completion contract", () => {
  const base = {
    sessionKey: "s1",
    title: "T",
    messages: [] as const,
    observedAt: null,
    connection: "connected" as const,
    coverage: "Complete",
    turnBusy: false,
  };

  it("synchronous acceptance clears the draft and re-arms after fresh input", async () => {
    const sent: string[] = [];
    function Host() {
      return (
        <SessionWorkspace
          {...base}
          sending={false}
          onSend={(text, onComplete) => {
            sent.push(text);
            onComplete({ status: "accepted" });
          }}
        />
      );
    }
    render(<Host />);
    fireEvent.change(messageBox(), { target: { value: "first" } });
    await act(async () => {
      sendButton().click();
    });
    expect(sent).toEqual(["first"]);
    expect(messageBox().value).toBe("");
    fireEvent.change(messageBox(), { target: { value: "second" } });
    await act(async () => {
      sendButton().click();
    });
    expect(sent).toEqual(["first", "second"]);
  });

  it("synchronous refusal resolves visibly, preserves the draft, and authorizes retry", async () => {
    const sent: string[] = [];
    function Host() {
      return (
        <SessionWorkspace
          {...base}
          sending={false}
          onSend={(text, onComplete) => {
            sent.push(text);
            onComplete({ status: "refused" });
          }}
        />
      );
    }
    render(<Host />);
    fireEvent.change(messageBox(), { target: { value: "keep me" } });
    await act(async () => {
      sendButton().click();
    });
    expect(sent).toEqual(["keep me"]);
    expect(sendButton().textContent).toBe("Send");
    expect(messageBox().value).toBe("keep me");
    await act(async () => {
      sendButton().click();
    });
    expect(sent).toEqual(["keep me", "keep me"]);
  });

  it("an already-resolved promise with batched host state resolves and re-arms", async () => {
    let calls = 0;
    function Host() {
      const [sending, setSending] = useState(false);
      return (
        <SessionWorkspace
          {...base}
          sending={sending}
          onSend={(_text, onComplete) => {
            calls += 1;
            // React batches both updates away: pending is never observed.
            setSending(true);
            setSending(false);
            Promise.resolve().then(() => onComplete({ status: "accepted" }));
          }}
        />
      );
    }
    render(<Host />);
    fireEvent.change(messageBox(), { target: { value: "batched" } });
    await act(async () => {
      sendButton().click();
    });
    expect(calls).toBe(1);
    // The microtask completion flushed inside act: draft cleared, reusable.
    expect(messageBox().value).toBe("");
    fireEvent.change(messageBox(), { target: { value: "again" } });
    await act(async () => {
      sendButton().click();
    });
    expect(calls).toBe(2);
  });

  it("ordinary async pending disables the action immediately and resolves on completion", async () => {
    let settle: SessionCompletion | undefined;
    function Host() {
      return (
        <SessionWorkspace
          {...base}
          sending={false}
          onSend={(_text, onComplete) => {
            settle = onComplete;
          }}
        />
      );
    }
    render(<Host />);
    fireEvent.change(messageBox(), { target: { value: "async" } });
    await act(async () => {
      sendButton().click();
    });
    expect(pendingSendButton().disabled).toBe(true);
    expect(messageBox().disabled).toBe(true);
    await act(async () => {
      settle?.({ status: "refused" });
    });
    expect(sendButton().textContent).toBe("Send");
    expect(messageBox().value).toBe("async");
  });

  it("a void onSend that never completes stays visibly blocked and never authorizes retry", async () => {
    const onSend = vi.fn();
    function Host() {
      return (
        <SessionWorkspace
          {...base}
          sending={false}
          onSend={onSend}
        />
      );
    }
    render(<Host />);
    fireEvent.change(messageBox(), { target: { value: "hello" } });
    await act(async () => {
      sendButton().click();
    });
    expect(onSend).toHaveBeenCalledTimes(1);
    expect(pendingSendButton().disabled).toBe(true);
    await act(async () => {
      fireEvent.submit(sendForm());
    });
    expect(onSend).toHaveBeenCalledTimes(1);
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(screen.getByRole("button", { name: "Sending…" })).toBeTruthy();
    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it("a thrown onSend stays visibly blocked without authorizing retry", async () => {
    const attempts: string[] = [];
    function Host() {
      return (
        <SessionWorkspace
          {...base}
          sending={false}
          onSend={(text) => {
            attempts.push(text);
            throw new Error("host exploded");
          }}
        />
      );
    }
    render(<Host />);
    fireEvent.change(messageBox(), { target: { value: "boom" } });
    await act(async () => {
      sendButton().click();
    });
    expect(attempts).toEqual(["boom"]);
    expect(pendingSendButton().disabled).toBe(true);
    await act(async () => {
      fireEvent.submit(sendForm());
    });
    expect(attempts).toEqual(["boom"]);
    expect(screen.getByRole("button", { name: "Sending…" })).toBeTruthy();
  });

  it("an uncorrelated error-string change is display-only and never unlocks the guard", async () => {
    let calls = 0;
    function Host() {
      const [error, setError] = useState<string | undefined>(undefined);
      return (
        <SessionWorkspace
          {...base}
          sending={false}
          error={error}
          onSend={(_text, _onComplete) => {
            calls += 1;
            setError(`refused-${calls}`);
          }}
        />
      );
    }
    render(<Host />);
    fireEvent.change(messageBox(), { target: { value: "err" } });
    await act(async () => {
      sendButton().click();
    });
    expect(calls).toBe(1);
    expect(screen.getByRole("alert").textContent).toBe("refused-1");
    await act(async () => {
      fireEvent.submit(sendForm());
    });
    expect(calls).toBe(1);
    expect(pendingSendButton().disabled).toBe(true);
  });

  it("send success clears only the submitted draft; text edited during flight is preserved", async () => {
    let held: SessionCompletion | undefined;
    function Host() {
      return (
        <SessionWorkspace
          {...base}
          sending={false}
          onSend={(_text, onComplete) => {
            held = onComplete;
          }}
        />
      );
    }
    render(<Host />);
    fireEvent.change(messageBox(), { target: { value: "submitted" } });
    await act(async () => {
      sendButton().click();
    });
    expect(messageBox().disabled).toBe(true);
    // The user force-edits the box while the send is still in flight.
    fireEvent.change(messageBox(), { target: { value: "edited meanwhile" } });
    await act(async () => {
      held?.({ status: "accepted" });
    });
    // Only the submitted text may be cleared; the newer edit survives.
    expect(messageBox().value).toBe("edited meanwhile");
    await act(async () => {
      sendButton().click();
    });
    expect(screen.getByRole("button", { name: "Sending…" })).toBeTruthy();
  });

  it("a late completion from session A cannot resolve or clear session B", async () => {
    let held: SessionCompletion | undefined;
    const sent: { session: string; text: string }[] = [];
    function Host({ sessionKey }: { sessionKey: string }) {
      return (
        <SessionWorkspace
          {...base}
          sessionKey={sessionKey}
          sending={false}
          onSend={(text, onComplete) => {
            sent.push({ session: sessionKey, text });
            held = onComplete;
          }}
        />
      );
    }
    const { rerender } = render(<Host sessionKey="s1" />);
    fireEvent.change(messageBox(), { target: { value: "From A" } });
    await act(async () => {
      sendButton().click();
    });
    expect(sent).toEqual([{ session: "s1", text: "From A" }]);

    // Switch identity to session B and type a fresh draft.
    rerender(<Host sessionKey="s2" />);
    expect(messageBox().value).toBe("");
    fireEvent.change(messageBox(), { target: { value: "From B" } });

    // Session A's completion arrives late: it must be a no-op for B.
    await act(async () => {
      held?.({ status: "accepted" });
    });
    expect(messageBox().value).toBe("From B");
    expect(sendButton().textContent).toBe("Send");

    await act(async () => {
      sendButton().click();
    });
    expect(sent).toEqual([
      { session: "s1", text: "From A" },
      { session: "s2", text: "From B" },
    ]);
  });

  it("a stored completion handle reconciles the same pending send across rerenders", async () => {
    let held: SessionCompletion | undefined;
    const onSend = vi.fn((_text: string, onComplete: SessionCompletion) => {
      held = onComplete;
    });
    const { rerender } = render(
      <SessionWorkspace {...base} sending={false} onSend={onSend} />,
    );
    fireEvent.change(messageBox(), { target: { value: "reconcile me" } });
    await act(async () => {
      sendButton().click();
    });
    expect(onSend).toHaveBeenCalledTimes(1);

    // Unrelated rerenders do not remount the component or drop the pending
    // action; the owner still holds the correlated handle.
    rerender(
      <SessionWorkspace
        {...base}
        sending={false}
        error="unrelated display text"
        onSend={onSend}
      />,
    );
    expect(screen.getByRole("button", { name: "Sending…" })).toBeTruthy();

    // The owner resolves the same pending action out-of-band, no remount.
    await act(async () => {
      held?.({ status: "refused" });
    });
    expect(messageBox().value).toBe("reconcile me");
    expect(sendButton().textContent).toBe("Send");
  });

  it("stop duplicate guard is visible while the host never reports, then re-arms on completion", async () => {
    let held: SessionCompletion | undefined;
    const onStop = vi.fn((onComplete: SessionCompletion) => {
      held = onComplete;
    });
    function Host() {
      return (
        <SessionWorkspace
          {...base}
          sending={false}
          onSend={() => undefined}
          stopLabel="Interrupt turn"
          onStop={onStop}
        />
      );
    }
    render(<Host />);
    const stopBtn = screen.getByRole("button", { name: "Interrupt turn" }) as HTMLButtonElement;
    await act(async () => {
      stopBtn.click();
    });
    expect(onStop).toHaveBeenCalledTimes(1);
    // The guard is visible even though the host never set `stopping`.
    const pendingStop = screen.getByRole("button", { name: "Stopping…" }) as HTMLButtonElement;
    expect(pendingStop.disabled).toBe(true);
    await act(async () => {
      fireEvent.click(pendingStop);
    });
    expect(onStop).toHaveBeenCalledTimes(1);

    await act(async () => {
      held?.({ status: "accepted" });
    });
    expect(screen.getByRole("button", { name: "Interrupt turn" })).toBeTruthy();
    await act(async () => {
      (screen.getByRole("button", { name: "Interrupt turn" }) as HTMLButtonElement).click();
    });
    expect(onStop).toHaveBeenCalledTimes(2);
  });
});
