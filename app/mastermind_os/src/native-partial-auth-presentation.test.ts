import { expect, it } from "vitest";
import type { AuthState } from "./host";
import { nativePartialAuthPresentation } from "./native-partial-auth-presentation";

const observed: AuthState = {
  status: "error", reason: "AUTH_TRANSACTION_EXPIRED", acquisition: true, content: false,
};

it.each(["en", "zh-CN"] as const)("distinguishes terminal timeout from ongoing authorization: %s", locale => {
  const timeout = nativePartialAuthPresentation(observed, locale)!;
  const pending = nativePartialAuthPresentation({ ...observed, status: "signing_in", reason: null }, locale)!;
  expect(timeout.label).toBe(locale === "en" ? "Account connected" : "账户已连接");
  expect(timeout.description).toContain(locale === "en" ? "Additional authorization timed out." : "后续授权已超时");
  expect(pending.description).toBe(locale === "en" ? "Additional authorization is still pending." : "后续授权仍在进行中。");
  expect(timeout.description).not.toContain(locale === "en" ? "pending" : "进行中");
  expect(timeout.description).not.toContain(locale === "en" ? "try again" : "重试");
  expect(observed).toEqual({ status: "error", reason: "AUTH_TRANSACTION_EXPIRED", acquisition: true, content: false });
});

it("keeps refusal, expired access and unknown causes separate without echoing raw reasons", () => {
  expect(nativePartialAuthPresentation({ ...observed, reason: "AUTHORIZATION_REFUSED" }, "en")?.description)
    .toContain("Additional authorization was not granted.");
  expect(nativePartialAuthPresentation({ ...observed, reason: "NATIVE_TOKEN_EXPIRED" }, "en")?.description)
    .toContain("Additional access expired.");
  for (const reason of ["NOT_ESTABLISHED", "UNRECOGNIZED_TIMEOUT_PRIVATE", null]) {
    const value = nativePartialAuthPresentation({ ...observed, reason }, "en")!;
    expect(value.description).toBe("Authorization is incomplete. Your account remains connected.");
    expect(value.description).not.toContain("timed out");
  }
});

it("does not attribute a general owner failure to Content or claim Workspace availability", () => {
  for (const reason of ["AUTH_TRANSACTION_EXPIRED", "AUTHORIZATION_REFUSED", "NATIVE_TOKEN_EXPIRED"]) {
    const value = nativePartialAuthPresentation({ ...observed, reason }, "en")!;
    expect(value.description).toContain("Your account remains connected.");
    expect(value.description).not.toMatch(/Content|Workspace/);
  }
});

it.each([
  { ...observed, acquisition: false },
  { ...observed, content: true },
  { ...observed, status: "signed_out" as const },
  { ...observed, status: "unconfigured" as const },
  { ...observed, status: "signed_in" as const, reason: null },
])("leaves the other existing state presentation untouched: %j", state => {
  expect(nativePartialAuthPresentation(state, "en")).toBeNull();
  expect(nativePartialAuthPresentation(state, "zh-CN")).toBeNull();
});
