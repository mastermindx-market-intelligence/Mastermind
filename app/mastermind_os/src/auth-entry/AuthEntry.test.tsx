/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { AuthEntry } from "./AuthEntry";
import type {
  AuthEntryLocale,
  AuthEntryProps,
  AuthEntryState,
} from "./AuthEntry";

afterEach(cleanup);

function entryProps(overrides: Partial<AuthEntryProps> = {}): AuthEntryProps {
  return {
    state: "signed_out",
    locale: "en",
    theme: "dark",
    authenticationControl: <button>Sign in</button>,
    ...overrides,
  };
}

const EXPECTED = {
  en: {
    lock: "Private workspace",
    footer: "Mastermind OS",
    storyTitle: "Your company, in focus.",
    storySubtitle: "Decisions, projects and conversations.",
    assurance: "Your workspace stays private until you sign in.",
    browserNote: "Continue in your browser, then return here.",
    signed_out: {
      eyebrow: "Your private workspace",
      heading: "Welcome back.",
      body: "Sign in to your workspace.",
    },
    signing_in: {
      eyebrow: "Sign-in in progress",
      heading: "Finish signing in",
      body: "Complete sign-in in your browser. This window will update.",
      waitingLabel: "Waiting for browser",
      waitingDetail: "Return here after you finish.",
      cancelNote: "Cancel returns you to the sign-in screen.",
    },
    error: {
      heading: "Sign-in could not complete.",
    },
    unconfigured: {
      heading: "Sign-in is unavailable here.",
      body: "Sign-in is not configured for this app.",
    },
  },
  "zh-CN": {
    lock: "私密工作区",
    footer: "Mastermind OS",
    storyTitle: "让公司事务，清晰在握。",
    storySubtitle: "决策、项目与对话。",
    assurance: "登录前，工作区保持私密。",
    browserNote: "在浏览器中继续，完成后返回此处。",
    signed_out: {
      eyebrow: "您的私密工作区",
      heading: "欢迎回来。",
      body: "登录以访问工作区。",
    },
    signing_in: {
      eyebrow: "正在登录",
      heading: "完成登录",
      body: "请在浏览器中完成登录，此窗口将随之更新。",
      waitingLabel: "正在等待浏览器",
      waitingDetail: "完成后请返回此处。",
      cancelNote: "取消后将返回登录界面。",
    },
    error: {
      heading: "暂时无法完成登录。",
    },
    unconfigured: {
      heading: "此处暂时无法登录。",
      body: "此应用尚未配置登录。",
    },
  },
} as const;

const LOCALES: AuthEntryLocale[] = ["en", "zh-CN"];

function textOf(element: Element | null): string {
  return element?.textContent ?? "";
}

describe("AuthEntry", () => {
  it("renders the exact signed_out content in both locales with exactly one h1", () => {
    for (const locale of LOCALES) {
      const expected = EXPECTED[locale];
      const { container, unmount } = render(
        <AuthEntry {...entryProps({ locale })} />,
      );

      const h1s = container.querySelectorAll("h1");
      expect(h1s).toHaveLength(1);
      expect(textOf(h1s[0])).toBe(expected.storyTitle);

      expect(textOf(screen.getByText(expected.signed_out.eyebrow))).toBe(
        expected.signed_out.eyebrow,
      );
      expect(textOf(screen.getByRole("heading", { level: 2 }))).toBe(
        expected.signed_out.heading,
      );
      expect(screen.getByText(expected.signed_out.body)).toBeTruthy();
      expect(screen.getByText(expected.storySubtitle)).toBeTruthy();
      expect(screen.getByText(expected.assurance)).toBeTruthy();
      expect(screen.getByText(expected.browserNote)).toBeTruthy();
      expect(screen.getByText(expected.lock)).toBeTruthy();
      expect(screen.getByText(expected.footer)).toBeTruthy();

      unmount();
    }
  });

  it("renders the exact signing_in content in both locales", () => {
    for (const locale of LOCALES) {
      const expected = EXPECTED[locale];
      render(
        <AuthEntry
          {...entryProps({
            state: "signing_in",
            locale,
            authenticationControl: <button>Cancel sign-in</button>,
          })}
        />,
      );

      expect(screen.getByText(expected.signing_in.eyebrow)).toBeTruthy();
      expect(textOf(screen.getByRole("heading", { level: 2 }))).toBe(
        expected.signing_in.heading,
      );
      expect(screen.getByText(expected.signing_in.body)).toBeTruthy();
      expect(screen.getByText(expected.signing_in.waitingLabel)).toBeTruthy();
      expect(screen.getByText(expected.signing_in.waitingDetail)).toBeTruthy();
      expect(screen.getByText(expected.signing_in.cancelNote)).toBeTruthy();

      cleanup();
    }
  });

  it("signed_out invokes only the caller control on click and never on mount or state transition", () => {
    const onSignIn = vi.fn();
    const { rerender } = render(
      <AuthEntry
        {...entryProps({
          authenticationControl: <button onClick={onSignIn}>Sign in</button>,
        })}
      />,
    );

    expect(onSignIn).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(onSignIn).toHaveBeenCalledTimes(1);

    rerender(
      <AuthEntry
        {...entryProps({
          state: "signing_in",
          authenticationControl: (
            <button onClick={onSignIn}>Cancel sign-in</button>
          ),
        })}
      />,
    );
    expect(onSignIn).toHaveBeenCalledTimes(1);

    rerender(
      <AuthEntry
        {...entryProps({
          authenticationControl: <button onClick={onSignIn}>Sign in</button>,
        })}
      />,
    );
    expect(onSignIn).toHaveBeenCalledTimes(1);
  });

  it("signing_in uses the supplied cancel control and manufactures no second sign-in button", () => {
    const { container } = render(
      <AuthEntry
        {...entryProps({
          state: "signing_in",
          authenticationControl: <button>Cancel sign-in</button>,
        })}
      />,
    );

    const buttons = container.querySelectorAll("button");
    expect(buttons).toHaveLength(1);
    expect(textOf(buttons[0])).toBe("Cancel sign-in");
    expect(screen.queryByText("Sign in")).toBeNull();
    expect(screen.queryByText(EXPECTED.en.browserNote)).toBeNull();
  });

  it("signing_in renders no spinner animation or elapsed-time claim", () => {
    const { container } = render(
      <AuthEntry
        {...entryProps({
          state: "signing_in",
          authenticationControl: <button>Cancel sign-in</button>,
        })}
      />,
    );
    expect(container.querySelector('[class*="spinner"]')).toBeNull();
    expect(container.querySelectorAll('svg[class*="spin"]')).toHaveLength(0);
    expect(container.textContent).not.toMatch(
      /elapsed|seconds? (?:elapsed|passed)/i,
    );
  });

  it("error shows the supplied feedback, the browser note, and never claims workspace readiness", () => {
    const { container } = render(
      <AuthEntry
        {...entryProps({
          state: "error",
          feedback: <p>Session expired. Please sign in again.</p>,
          authenticationControl: <button>Try again</button>,
        })}
      />,
    );

    expect(textOf(screen.getByRole("heading", { level: 2 }))).toBe(
      EXPECTED.en.error.heading,
    );
    expect(
      screen.getByText("Session expired. Please sign in again."),
    ).toBeTruthy();
    expect(screen.getByText(EXPECTED.en.browserNote)).toBeTruthy();
    expect(screen.queryByText(EXPECTED.en.signed_out.heading)).toBeNull();
    expect(container.textContent).not.toMatch(/\bready\b/i);
  });

  it("error renders no invented raw reason when no feedback is supplied", () => {
    const { container } = render(
      <AuthEntry
        {...entryProps({
          state: "error",
          authenticationControl: <button>Try again</button>,
        })}
      />,
    );
    expect(textOf(screen.getByRole("heading", { level: 2 }))).toBe(
      EXPECTED.en.error.heading,
    );
    expect(container.querySelector(".auth-entry__feedback")).toBeNull();
  });

  it("unconfigured shows the unavailable content and never claims workspace readiness", () => {
    const { container } = render(
      <AuthEntry
        {...entryProps({
          state: "unconfigured",
          authenticationControl: <button disabled>Sign in</button>,
        })}
      />,
    );

    expect(textOf(screen.getByRole("heading", { level: 2 }))).toBe(
      EXPECTED.en.unconfigured.heading,
    );
    expect(screen.getByText(EXPECTED.en.unconfigured.body)).toBeTruthy();
    expect(container.textContent).not.toMatch(/\bready\b/i);
    expect(screen.queryByText(EXPECTED.en.signed_out.heading)).toBeNull();

    const button = screen.getByRole("button") as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });

  it("keeps the exact protectedWork textarea present with its value through state and locale rerenders", () => {
    const protectedWork = (
      <textarea
        aria-label="Unsent draft"
        defaultValue="Draft: revisit the AU01 checklist"
      />
    );
    const { rerender, container } = render(
      <AuthEntry {...entryProps({ protectedWork })} />,
    );

    const textarea = screen.getByLabelText(
      "Unsent draft",
    ) as HTMLTextAreaElement;
    expect(textarea.value).toBe("Draft: revisit the AU01 checklist");
    expect(textarea.closest("details")).toBeNull();
    expect(textarea.closest("[hidden]")).toBeNull();

    rerender(
      <AuthEntry
        {...entryProps({
          state: "signing_in" as AuthEntryState,
          locale: "zh-CN",
          authenticationControl: <button>Cancel sign-in</button>,
          protectedWork,
        })}
      />,
    );

    const still = screen.getByLabelText("Unsent draft") as HTMLTextAreaElement;
    expect(container.contains(still)).toBe(true);
    expect(still.value).toBe("Draft: revisit the AU01 checklist");
    expect(still.closest("details")).toBeNull();
    expect(container.querySelector("details[open]")).toBeNull();
  });

  it("renders no illustration element when none is supplied", () => {
    const { container } = render(<AuthEntry {...entryProps()} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("figure")).toBeNull();
  });

  it("renders the supplied bundled sculpture as a decorative image with empty alt", () => {
    const { container } = render(
      <AuthEntry
        {...entryProps({ illustrationSrc: "/assets/auth-sculpture.png" })}
      />,
    );
    const img = container.querySelector("img");
    expect(img).toBeTruthy();
    expect(img?.getAttribute("src")).toBe("/assets/auth-sculpture.png");
    expect(img?.getAttribute("alt")).toBe("");
  });

  it("never renders a design-preview label in the production footer or anywhere else", () => {
    const { container } = render(
      <AuthEntry
        {...entryProps({
          preferencesControl: <label>Use system theme</label>,
          protectedWork: <p>Unsent draft</p>,
        })}
      />,
    );
    expect(container.textContent).not.toMatch(/Design preview/i);
    expect(container.querySelector("footer")?.textContent).toBe(
      "Mastermind OS",
    );
  });

  it("renders the light theme with the same content and supplied disabled control", () => {
    for (const locale of LOCALES) {
      const expected = EXPECTED[locale];
      const { container, unmount } = render(
        <AuthEntry
          {...entryProps({
            state: "unconfigured",
            locale,
            theme: "light",
            authenticationControl: (
              <button disabled>{locale === "en" ? "Sign in" : "登录"}</button>
            ),
          })}
        />,
      );

      const root = container.firstElementChild as HTMLElement;
      expect(root.className).toContain("auth-entry--light");
      expect(textOf(screen.getByRole("heading", { level: 2 }))).toBe(
        expected.unconfigured.heading,
      );
      expect(screen.getByText(expected.unconfigured.body)).toBeTruthy();
      const button = screen.getByRole("button") as HTMLButtonElement;
      expect(button.disabled).toBe(true);
      unmount();
    }
  });
  it("keeps owner supplied signed-out popup feedback visible without inventing a second action", () => {
    render(
      <AuthEntry
        {...entryProps({
          feedback: <p role="alert">Allow the sign-in popup and try again.</p>,
        })}
      />,
    );
    expect(screen.getByRole("alert").textContent).toBe(
      "Allow the sign-in popup and try again.",
    );
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });
  it("points to guarded unfinished work before the supplied sign-in action", () => {
    const { container } = render(
      <AuthEntry
        {...entryProps({
          protectedWork: (
            <textarea
              aria-label="Guarded local draft"
              defaultValue="Exact user text"
            />
          ),
        })}
      />,
    );
    const link = screen.getByRole("link", { name: "Review unfinished work" });
    const button = screen.getByRole("button", { name: "Sign in" });
    expect(
      Boolean(
        link.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING,
      ),
    ).toBe(true);
    expect(link.getAttribute("href")).toBe("#auth-entry-protected");
    expect(
      container.querySelector("#auth-entry-protected textarea"),
    ).toBeTruthy();
  });
});
