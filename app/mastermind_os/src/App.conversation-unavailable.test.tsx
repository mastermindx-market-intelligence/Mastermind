// @vitest-environment jsdom
import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { controlRoomFixture, missionFixture } from "./test-fixtures";
import type { WindowDocument } from "./workspace-contract";

// Pins the unavailable Conversation copy against the reported failure: an
// authenticated read with content permission true that still fails must
// advise source/service recovery and refresh — never sign in. Missing
// content access keeps the access-specific advice, and a missing read method
// keeps the no-connected-source copy. Refresh enablement stays driven by
// contentAvailable and SOURCE_READ_PENDING, and document rendering is intact.
const EN_RECOVERY =
  "The conversation source is unavailable. Refresh after the service or source becomes available.";
const ZH_RECOVERY = "对话来源暂不可用。服务或来源恢复后，请刷新。";
const SIGN_IN_ADVICE =
  "Sign in with permitted conversation access, then open this view again.";
const NO_SOURCE_ADVICE =
  "No conversation content is shown until a connected source is installed. Existing owner and effect boundaries remain unchanged.";

const readPrograms = async () => controlRoomFixture();

const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((yes) => {
    resolve = yes;
  });
  return { promise, resolve };
};

function windowDocument(): WindowDocument {
  const h = "a".repeat(64);
  return {
    schema: "mastermind.workspace.window_read_candidate.v1" as const,
    selection_ref: "managed-window:fixture",
    mode: "observed-turn-window" as const,
    view: {
      schema: "mastermind.workspace.visible_window_candidate.v1" as const,
      source_ref: "managed-window:fixture",
      scope: "one-managed-turn-window" as const,
      observed_at: "2026-09-21T07:00:00Z",
      epoch: h,
      terminal: false,
      coverage: "OBSERVED_WINDOW" as const,
      history: "NOT_PROVEN" as const,
      acceptance: "NOT_PROJECTED" as const,
      capabilities: {
        send: false as const,
        provider_control: false as const,
        history: false as const,
      },
      items: [
        {
          id: `visible:${h}`,
          source_sequence: 0,
          publication_sequence: 1,
          state: "completed" as const,
          kind: "visible-response" as const,
          text: "Permitted fixture response",
          representation: "VISIBLE_TEXT" as const,
          display_sha256: h,
        },
      ],
      gaps: [],
    },
  };
}

function installHost(options: {
  content: boolean;
  readCurrentWindow?: (request: {
    signal: AbortSignal;
  }) => Promise<WindowDocument>;
}) {
  const signIn = vi.fn(async () => {});
  window.MastermindMissionHost = {
    selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
    readPrograms,
    readMission: async () => missionFixture("WS:ALPHA", "JOB-A"),
    ...(options.readCurrentWindow
      ? { readCurrentWindow: options.readCurrentWindow }
      : {}),
    auth: {
      getState: () => ({
        status: "signed_in" as const,
        reason: null,
        acquisition: true,
        content: options.content,
      }),
      subscribe: () => () => {},
      signIn,
      signOut: async () => {},
    },
  };
  return { signIn };
}

beforeEach(() => {
  history.replaceState(null, "", "/?work_ref=WS%3AALPHA&root_job_id=JOB-A");
  delete (window as any).__TAURI_INTERNALS__;
  delete window.MastermindMissionHost;
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  delete window.MastermindMissionHost;
});

describe("Conversation unavailable source copy", () => {
  it("advises source recovery and refresh, never sign in, after a permitted read fails", async () => {
    const readCurrentWindow = vi.fn(() =>
      Promise.reject(new Error("private window read failure")),
    );
    const { signIn } = installHost({ content: true, readCurrentWindow });
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Conversation" }));
    expect(await screen.findByText(EN_RECOVERY)).toBeTruthy();
    expect(
      screen.getByRole("heading", { name: "Conversation", level: 2 }),
    ).toBeTruthy();
    expect(readCurrentWindow).toHaveBeenCalledTimes(1);
    expect(readCurrentWindow).toHaveBeenCalledWith({
      signal: expect.any(AbortSignal),
    });
    expect(screen.queryByText(SIGN_IN_ADVICE)).toBeNull();
    expect(signIn).not.toHaveBeenCalled();
    expect(
      screen.getByText("CONVERSATION_TRANSPORT_UNAVAILABLE").closest("details"),
    ).toBeTruthy();
    expect(
      document.body.textContent,
    ).not.toContain("private window read failure");
    expect(
      (screen.getByRole("button", { name: "Refresh window" }) as HTMLButtonElement)
        .disabled,
    ).toBe(false);
  });

  it("keeps access-specific advice and reads nothing without content permission", async () => {
    const readCurrentWindow = vi.fn();
    const { signIn } = installHost({ content: false, readCurrentWindow });
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Conversation" }));
    expect(await screen.findByText(SIGN_IN_ADVICE)).toBeTruthy();
    expect(
      screen.getByText(
        "The current permitted conversation window is unavailable.",
      ),
    ).toBeTruthy();
    expect(readCurrentWindow).not.toHaveBeenCalled();
    expect(signIn).not.toHaveBeenCalled();
    expect(screen.queryByText(EN_RECOVERY)).toBeNull();
    expect(
      (screen.getByRole("button", { name: "Refresh window" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });

  it("keeps the no-connected-source copy when no read method is installed", async () => {
    const { signIn } = installHost({ content: true });
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Conversation" }));
    expect(
      await screen.findByText(
        "This app has no connected conversation source yet.",
      ),
    ).toBeTruthy();
    expect(screen.getByText(NO_SOURCE_ADVICE)).toBeTruthy();
    expect(screen.queryByText(EN_RECOVERY)).toBeNull();
    expect(screen.queryByText(SIGN_IN_ADVICE)).toBeNull();
    expect(signIn).not.toHaveBeenCalled();
    expect(
      (screen.getByRole("button", { name: "Refresh window" }) as HTMLButtonElement)
        .disabled,
    ).toBe(false);
  });

  it("keeps SOURCE_READ_PENDING and document rendering across a manual refresh", async () => {
    const second = deferred<WindowDocument>();
    const flights: Array<() => Promise<WindowDocument>> = [
      () => Promise.reject(new Error("private window read failure")),
      () => second.promise,
    ];
    const readCurrentWindow = vi.fn(() => flights.shift()!());
    installHost({ content: true, readCurrentWindow });
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Conversation" }));
    expect(await screen.findByText(EN_RECOVERY)).toBeTruthy();
    await user.click(
      screen.getByRole("button", { name: "Refresh window" }),
    );
    expect(await within(screen.getByRole("heading", { name: "Conversation", level: 2 }).closest("section")!).findByText("SOURCE READ PENDING")).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: "Refresh window" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    await act(async () => {
      second.resolve(windowDocument());
    });
    expect(
      await screen.findByRole("heading", {
        name: "Unbound current window",
        level: 2,
      }),
    ).toBeTruthy();
    expect(screen.getByText("Permitted fixture response")).toBeTruthy();
    expect(screen.queryByText(EN_RECOVERY)).toBeNull();
    expect(
      (screen.getByRole("button", { name: "Refresh window" }) as HTMLButtonElement)
        .disabled,
    ).toBe(false);
    expect(readCurrentWindow).toHaveBeenCalledTimes(2);
  });

  it.each([
    { locale: "en", theme: "dark", copy: EN_RECOVERY, other: ZH_RECOVERY },
    { locale: "zh-CN", theme: "dark", copy: ZH_RECOVERY, other: EN_RECOVERY },
    { locale: "en", theme: "light", copy: EN_RECOVERY, other: ZH_RECOVERY },
    { locale: "zh-CN", theme: "light", copy: ZH_RECOVERY, other: EN_RECOVERY },
  ] as const)(
    "renders the recovery copy for locale $locale and theme $theme",
    async ({ locale, theme, copy, other }) => {
      const readCurrentWindow = vi.fn(() =>
        Promise.reject(new Error("private window read failure")),
      );
      const { signIn } = installHost({ content: true, readCurrentWindow });
      const user = userEvent.setup();
      render(<App locale={locale} theme={theme} />);
      expect(document.querySelector(".shell")?.getAttribute("lang")).toBe(
        locale,
      );
      expect(document.querySelector(".shell")?.getAttribute("data-theme")).toBe(
        theme,
      );
      await user.click(screen.getByRole("button", { name: "Conversation" }));
      expect(await screen.findByText(copy)).toBeTruthy();
      expect(screen.queryByText(other)).toBeNull();
      expect(screen.queryByText(SIGN_IN_ADVICE)).toBeNull();
      expect(signIn).not.toHaveBeenCalled();
    },
  );
});
