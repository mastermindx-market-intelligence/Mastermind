import type { ReactNode } from "react";
import "./auth-entry.css";

export type AuthEntryState =
  "signed_out" | "signing_in" | "error" | "unconfigured";
export type AuthEntryLocale = "en" | "zh-CN";
export type AuthEntryTheme = "dark" | "light";

export interface AuthEntryProps {
  /** Entry lifecycle owned by the parent authentication flow. */
  state: AuthEntryState;
  locale: AuthEntryLocale;
  theme: AuthEntryTheme;
  /**
   * The caller's real control: the sign-in button, the cancel sign-in
   * button, or the disabled control for an unconfigured host. Rendered
   * exactly as supplied — this component never manufactures a second
   * button, callback or controller.
   */
  authenticationControl: ReactNode;
  /** Supplied user-facing feedback from the existing authentication owner. */
  feedback?: ReactNode;
  /** Guarded recovery content (unsent draft / original operation) shown visibly below the panel. */
  protectedWork?: ReactNode;
  /** Existing preference control node, rendered inside the panel. */
  preferencesControl?: ReactNode;
  /** Bundled Paper sculpture asset path supplied by the parent. Decorative only. */
  illustrationSrc?: string;
}

type StateCopy = {
  eyebrow: string;
  heading: string;
  body?: string;
  waitingLabel?: string;
  waitingDetail?: string;
  note?: string;
};

type LocaleCopy = {
  brand: string;
  lock: string;
  storyEyebrow: string;
  storyTitle: string;
  storySubtitle: string;
  assurance: string;
  footer: string;
  states: Record<AuthEntryState, StateCopy>;
};

const COPY: Record<AuthEntryLocale, LocaleCopy> = {
  en: {
    brand: "mastermind",
    lock: "Private workspace",
    storyEyebrow: "Space to think. Clarity to act.",
    storyTitle: "Your company, in focus.",
    storySubtitle: "Decisions, projects and conversations.",
    assurance: "Your workspace stays private until you sign in.",
    footer: "Mastermind OS",
    states: {
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
        note: "Cancel returns you to the sign-in screen.",
      },
      error: {
        eyebrow: "Your private workspace",
        heading: "Sign-in could not complete.",
      },
      unconfigured: {
        eyebrow: "Your private workspace",
        heading: "Sign-in is unavailable here.",
        body: "Sign-in is not configured for this app.",
      },
    },
  },
  "zh-CN": {
    brand: "mastermind",
    lock: "私密工作区",
    storyEyebrow: "从容思考，清晰行动。",
    storyTitle: "让公司事务，清晰在握。",
    storySubtitle: "决策、项目与对话。",
    assurance: "登录前，工作区保持私密。",
    footer: "Mastermind OS",
    states: {
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
        note: "取消后将返回登录界面。",
      },
      error: {
        eyebrow: "您的私密工作区",
        heading: "暂时无法完成登录。",
      },
      unconfigured: {
        eyebrow: "您的私密工作区",
        heading: "此处暂时无法登录。",
        body: "此应用尚未配置登录。",
      },
    },
  },
};

function StarMark({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.2"
      aria-hidden="true"
      focusable="false"
    >
      <rect x="1" y="1" width="22" height="22" rx="6" />
      <path d="m12 5 2 5 5 2-5 2-2 5-2-5-5-2 5-2z" />
    </svg>
  );
}

function LockMark({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 16 16"
      fill="currentColor"
      aria-hidden="true"
      focusable="false"
    >
      <path
        fillRule="evenodd"
        d="M8 1.5A3 3 0 0 0 5 4.5V6h-.5A1.5 1.5 0 0 0 3 7.5v5A1.5 1.5 0 0 0 4.5 14h7a1.5 1.5 0 0 0 1.5-1.5v-5A1.5 1.5 0 0 0 11.5 6H11V4.5a3 3 0 0 0-3-3zm-1.5 3V6h3V4.5a1.5 1.5 0 0 0-3 0zM4.5 7.5h7v5h-7v-5z"
      />
    </svg>
  );
}

/**
 * Private-entry presentation surface. Pure controlled rendering: no state,
 * no effects, no timers, no automatic focus, no auto-submit and no side
 * effects of any kind. Every action arrives as a supplied ReactNode.
 */
export function AuthEntry({
  state,
  locale,
  theme,
  authenticationControl,
  feedback,
  protectedWork,
  preferencesControl,
  illustrationSrc,
}: AuthEntryProps) {
  const copy = COPY[locale];
  const panel = copy.states[state];
  const rootClassName = [
    "auth-entry",
    `auth-entry--${theme}`,
    `auth-entry--${state}`,
    locale === "zh-CN" ? "auth-entry--zh" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={rootClassName} lang={locale} data-theme={theme}>
      <header className="auth-entry__masthead">
        <span className="auth-entry__brand">
          <StarMark className="auth-entry__brand-mark" />
          {copy.brand}
        </span>
        <span className="auth-entry__lock">
          <LockMark className="auth-entry__lock-mark" />
          {copy.lock}
        </span>
      </header>

      <main className="auth-entry__main">
        <div className="auth-entry__grid">
          <section className="auth-entry__story">
            <div className="auth-entry__story-copy">
              <p className="auth-entry__story-eyebrow">{copy.storyEyebrow}</p>
              <h1 className="auth-entry__title">
                {locale === "en" ? (
                  <>
                    Your company, <br />
                    in focus.
                  </>
                ) : (
                  <>
                    让公司事务，
                    <br />
                    清晰在握。
                  </>
                )}
              </h1>
              <p className="auth-entry__subtitle">{copy.storySubtitle}</p>
            </div>
            {illustrationSrc ? (
              <figure className="auth-entry__figure">
                <img className="auth-entry__art" src={illustrationSrc} alt="" />
              </figure>
            ) : null}
          </section>

          <div className="auth-entry__entry">
            <section className="auth-entry__panel">
              <p className="auth-entry__eyebrow">{panel.eyebrow}</p>
              <h2 className="auth-entry__panel-heading">{panel.heading}</h2>
              {panel.body && (
                <p className="auth-entry__panel-body">{panel.body}</p>
              )}
              {feedback && (
                <div className="auth-entry__feedback">{feedback}</div>
              )}
              {panel.waitingLabel ? (
                <p className="auth-entry__waiting">
                  <span className="auth-entry__waiting-label">
                    {panel.waitingLabel}
                  </span>
                  <span className="auth-entry__waiting-detail">
                    {panel.waitingDetail}
                  </span>
                </p>
              ) : null}

              {protectedWork && (
                <div className="auth-entry__recovery-notice" role="status">
                  <p>
                    {locale === "en"
                      ? "Review unfinished work below before signing in."
                      : "登录前，请先查看下方未完成的工作。"}
                  </p>
                  <a
                    className="auth-entry__protected-link"
                    href="#auth-entry-protected"
                  >
                    {locale === "en"
                      ? "Review unfinished work"
                      : "查看未完成的工作"}
                  </a>
                </div>
              )}
              <div className="auth-entry__control">{authenticationControl}</div>

              {preferencesControl ? (
                <div className="auth-entry__preferences">
                  {preferencesControl}
                </div>
              ) : null}

            </section>
            <p className="auth-entry__assurance">
              {panel.note || copy.assurance}
            </p>
          </div>
        </div>

        {protectedWork ? (
          <section
            className="auth-entry__protected"
            id="auth-entry-protected"
            tabIndex={-1}
          >
            {protectedWork}
          </section>
        ) : null}
      </main>

      <footer className="auth-entry__footer">{copy.footer}</footer>
    </div>
  );
}

export default AuthEntry;
