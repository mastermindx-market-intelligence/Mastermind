// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { MountedExecutiveSessionBinding } from "../orchestration/os-executive-session-host";
import { qualifyExecutiveOfficeSession } from "./session-context";
import { useOfficeProjection } from "./useOfficeProjection";

const selection = { workRef: "WS:ALPHA", rootJobId: "JOB-1" };
const target = `fabric_attempt:${"a".repeat(64)}`;
const principal = "p".repeat(64);
const generation = "epoch:alpha";

function binding(
  changes: Record<string, unknown> = {},
): MountedExecutiveSessionBinding {
  const observed = {
    targetRef: target,
    selection,
    principalScope: principal,
    generation,
    ...(changes.observation as Record<string, unknown> | undefined),
  };
  return {
    port: {
      context: changes.owner === null ? () => null :
        () => ({ principalScope: principal, generation,
          ...(changes.owner as Record<string, unknown> | undefined) }),
      currentTargetRef: () => changes.currentTarget === undefined ? target : changes.currentTarget,
      currentObservation: changes.missing === true ? undefined :
        changes.throwing === true ? () => { throw Error("closed source"); } :
        () => observed,
    },
  } as unknown as MountedExecutiveSessionBinding;
}

describe("exact Executive native-session to Office context", () => {
  it("binds one owner-verified selection and target without inventing a session", () => {
    const result = qualifyExecutiveOfficeSession(true, selection, binding());
    expect(result.sessionRef).toBe(target);
    expect(result.bindingGeneration).toBe(
      JSON.stringify(["executive-native-session", principal, generation]),
    );
    expect(result).not.toHaveProperty("dispatch");
    expect(result).not.toHaveProperty("authority");
  });

  it("refuses absent authentication, selection and missing/legacy host observation", () => {
    expect(qualifyExecutiveOfficeSession(false, selection, binding())).toEqual({
      sessionRef: null, bindingGeneration: null,
    });
    expect(qualifyExecutiveOfficeSession(true, null, binding()).sessionRef).toBeNull();
    expect(qualifyExecutiveOfficeSession(true, selection, null).sessionRef).toBeNull();
    expect(qualifyExecutiveOfficeSession(true, selection, binding({ missing: true })).sessionRef).toBeNull();
  });

  it.each([
    { observation: { selection: { workRef: "WS:OTHER", rootJobId: "JOB-1" } } },
    { observation: { selection: { workRef: "WS:ALPHA", rootJobId: "JOB-2" } } },
    { observation: { selection: { workRef: "WS:ALPHA", rootJobId: "JOB-1", extra: "not owner" } } },
    { observation: { targetRef: "fab-other:some-session" } },
    { currentTarget: `fabric_attempt:${"b".repeat(64)}` },
    { observation: { principalScope: "someone-else" } },
    { owner: { principalScope: "other-signed-in-user" } },
    { owner: { generation: "stale" } },
    { observation: { generation: "old-epoch" } },
    { owner: null },
    { throwing: true },
  ])("does not infer identity through mismatched/ambiguous owner evidence: %j", (changes) => {
    expect(qualifyExecutiveOfficeSession(true, selection, binding(changes)).sessionRef).toBeNull();
  });

  it("rejects an invalid target even if both getters agree", () => {
    const hostile = "fabric_attempt:" + "A".repeat(64);
    expect(qualifyExecutiveOfficeSession(true, selection, binding({
      currentTarget: hostile, observation: { targetRef: hostile },
    })).sessionRef).toBeNull();
  });

  it("Office drafts stay associated with their original native target and owner epoch", () => {
    const selected = selection;
    const first = qualifyExecutiveOfficeSession(true, selected, binding());
    const second = qualifyExecutiveOfficeSession(true, selected, binding({
      observation: { targetRef: `fabric_attempt:${"b".repeat(64)}` },
      currentTarget: `fabric_attempt:${"b".repeat(64)}`,
    }));
    const { result, rerender } = renderHook(
      ({ context }) => useOfficeProjection(7, selected, context),
      { initialProps: { context: first } },
    );
    act(() => { result.current.changeDraft("Original CEO direction"); });
    expect(result.current.draft.text).toBe("Original CEO direction");
    rerender({ context: second });
    expect(result.current.draft.text).toBe("");
    act(() => { result.current.changeDraft("Other direction"); });
    expect(result.current.draft.text).toBe("Other direction");
    rerender({ context: first });
    expect(result.current.draft.text).toBe("Original CEO direction");
    rerender({ context: { sessionRef: null, bindingGeneration: null } });
    expect(result.current.draft.text).toBe("");
  });

  it("a forged title or Slack thread is not even part of the observation interface", () => {
    const forged = {
      observation: { sessionKey: "executive-office", thread_ts: "99999.9",
        model: "grok", title: "CEO is running" },
    };
    expect(qualifyExecutiveOfficeSession(true, selection, binding(forged)).sessionRef).toBeNull();
  });
});
