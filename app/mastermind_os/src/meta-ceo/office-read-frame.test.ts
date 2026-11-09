// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import type { MissionHost, AuthState } from "../host";
import { captureOfficeReadFrame } from "./office-read-frame";
afterEach(() => {
  delete window.MastermindMissionHost;
  vi.restoreAllMocks();
});
function frame(source: "readWork" | "readProjectJournal" = "readWork") {
  let epoch = 1,
    revision = 0,
    auth: AuthState = {
      status: "signed_in",
      acquisition: true,
      content: false,
      reason: null,
    };
  const reader = vi.fn(async () => {
    throw Error("not invoked");
  });
  const host: MissionHost = {
    auth: {
      getState: () => auth,
      subscribe: () => () => {},
      signIn: async () => {},
      signOut: async () => {},
    },
    invalidationGeneration: () => epoch,
    [source]: reader,
  };
  window.MastermindMissionHost = host;
  const f = captureOfficeReadFrame(host, 0, () => revision, source);
  return {
    host,
    reader,
    f,
    epoch: () => epoch++,
    revision: () => revision++,
    auth: (v: AuthState) => {
      auth = v;
    },
  };
}
it.each(["readWork", "readProjectJournal"] as const)(
  "qualifies only the actual current %s frame without reading or requiring CONTENT",
  (source) => {
    const x = frame(source);
    expect(x.f.current()).toBe(true);
    expect(x.reader).not.toHaveBeenCalled();
    expect(Object.isFrozen(x.f)).toBe(true);
  },
);
it.each([
  "host",
  "source-method",
  "auth-method",
  "epoch",
  "revision",
  "revoked",
  "throw",
] as const)("no-render %s departure fails closed", (damage) => {
  const x = frame();
  if (damage === "host") window.MastermindMissionHost = { ...x.host };
  if (damage === "source-method") x.host.readWork = vi.fn();
  if (damage === "auth-method")
    x.host.auth!.getState = () => ({
      status: "signed_in",
      acquisition: true,
      content: false,
      reason: null,
    });
  if (damage === "epoch") x.epoch();
  if (damage === "revision") x.revision();
  if (damage === "revoked")
    x.auth({
      status: "signed_in",
      acquisition: false,
      content: false,
      reason: null,
    });
  if (damage === "throw")
    x.host.auth!.getState = () => {
      throw Error("private");
    };
  expect(x.f.current()).toBe(false);
  expect(x.reader).not.toHaveBeenCalled();
});
