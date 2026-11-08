import { expect, it } from "vitest";
import type { AuthState } from "./host";
import { nativePartialAuthPresentation } from "./native-partial-auth-presentation";

const observed: AuthState = {
  status: "error", reason: "AUTH_TRANSACTION_EXPIRED", acquisition: true, content: false,
};

it.each(["en", "zh-CN"] as const)("distinguishes terminal Content timeout from ongoing authorization: %s", locale => {
  const timeout = nativePartialAuthPresentation(observed, locale)!;
  const pending = nativePartialAuthPresentation({ ...observed, status: "signing_in", reason: null }, locale)!;
  expect(timeout.label).toBe(locale === "en" ? "Workspace signed in" : "工作区已登录");
  expect(timeout.description).toContain(locale === "en" ? "Content authorization timed out." : "内容访问授权已超时");
  expect(pending.description).toBe(locale === "en" ? "Content authorization is still pending." : "内容访问授权仍在进行中。");
  expect(timeout.description).not.toContain(locale === "en" ? "pending" : "进行中");
  expect(timeout.description).not.toContain(locale === "en" ? "try again" : "重试");
  expect(observed).toEqual({ status: "error", reason: "AUTH_TRANSACTION_EXPIRED", acquisition: true, content: false });
});

it("keeps refusal, expired access and unknown causes separate without echoing raw reasons", () => {
  expect(nativePartialAuthPresentation({ ...observed, reason: "AUTHORIZATION_REFUSED" }, "en")?.description)
    .toContain("Content authorization was not granted.");
  expect(nativePartialAuthPresentation({ ...observed, reason: "NATIVE_TOKEN_EXPIRED" }, "en")?.description)
    .toContain("Content access expired.");
  for (const reason of ["NOT_ESTABLISHED", "UNRECOGNIZED_TIMEOUT_PRIVATE", null]) {
    const value = nativePartialAuthPresentation({ ...observed, reason }, "en")!;
    expect(value.description).toBe("Content access is unavailable. Workspace access remains signed in.");
    expect(value.description).not.toContain("timed out");
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
