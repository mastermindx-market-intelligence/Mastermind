import type { AuthState } from "./host";

const copy = {
  en: {
    sessionExpired: "Your app access has expired.",
    someAccessExpired: "Some app access has expired.",
    transactionTimeout: "The authorization attempt timed out before it completed.",
    authorizationRefused: "Authorization was not granted.",
    label: "Account connected",
    pending: "Additional authorization is still pending.",
    timeout: "Additional authorization timed out. Your account remains connected.",
    expired: "Additional access expired. Your account remains connected.",
    refused: "Additional authorization was not granted. Your account remains connected.",
    unavailable: "Authorization is incomplete. Your account remains connected.",
  },
  "zh-CN": {
    sessionExpired: "应用访问权限已过期。",
    someAccessExpired: "部分应用访问权限已过期。",
    transactionTimeout: "本次授权尚未完成便已超时。",
    authorizationRefused: "授权未获批准。",
    label: "账户已连接",
    pending: "后续授权仍在进行中。",
    timeout: "后续授权已超时；您的账户仍保持连接。",
    expired: "部分访问权限已过期；您的账户仍保持连接。",
    refused: "后续授权未获批准；您的账户仍保持连接。",
    unavailable: "授权尚未完成；您的账户仍保持连接。",
  },
} as const;

/** The flags identify incomplete access, not which resource caused a general error. */
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

/** Exact public native causes only. A general refusal does not identify the
 * resource; Executive-specific text remains with its existing local observation. */
export function nativeAuthFeedback(state: AuthState, locale: "en" | "zh-CN"): string | null {
  const text = copy[locale];
  switch (state.reason) {
    case "NATIVE_TOKEN_EXPIRED":
      return state.acquisition || state.content ? text.someAccessExpired : text.sessionExpired;
    case "AUTH_TRANSACTION_EXPIRED": return text.transactionTimeout;
    case "AUTHORIZATION_REFUSED": return text.authorizationRefused;
    default: return null;
  }
}
