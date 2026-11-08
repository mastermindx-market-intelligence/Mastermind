import type { AuthState } from "./host";

const copy = {
  en: {
    label: "Workspace signed in",
    pending: "Content authorization is still pending.",
    timeout: "Content authorization timed out. Workspace access remains signed in.",
    expired: "Content access expired. Workspace access remains signed in.",
    refused: "Content authorization was not granted. Workspace access remains signed in.",
    unavailable: "Content access is unavailable. Workspace access remains signed in.",
  },
  "zh-CN": {
    label: "工作区已登录",
    pending: "内容访问授权仍在进行中。",
    timeout: "内容访问授权已超时；工作区登录仍然有效。",
    expired: "内容访问权限已过期；工作区登录仍然有效。",
    refused: "内容访问未获授权；工作区登录仍然有效。",
    unavailable: "内容访问暂不可用；工作区登录仍然有效。",
  },
} as const;

/** Presentation of the existing native flags only; confers no access or action. */
export function nativePartialAuthPresentation(
  state: AuthState,
  locale: "en" | "zh-CN",
): { label: string; description: string } | null {
  if (state.acquisition !== true || state.content !== false ||
      (state.status !== "signing_in" && state.status !== "error")) return null;
  const text = copy[locale];
  const description = state.status === "signing_in" ? text.pending
    : state.reason === "AUTH_TRANSACTION_EXPIRED" ? text.timeout
      : state.reason === "NATIVE_TOKEN_EXPIRED" ? text.expired
        : state.reason === "AUTHORIZATION_REFUSED" ? text.refused
          : text.unavailable;
  return { label: text.label, description };
}
