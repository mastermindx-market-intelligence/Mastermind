// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { AuthState } from "./host";
import { decodeWorkDocument, type WorkDocument } from "./work";
import { decodeProgramsObservation } from "./programs-observation";
import { controlRoomFixture, missionFixture } from "./test-fixtures";
import programsAvailable from "./fixtures/programs-available-workspace-service.json";
import workAvailable from "./fixtures/work-service-available.json";
import workUnavailable from "./fixtures/work-service-unavailable.json";

// These component tests enforce focusable DOM semantics and guarded activation.
// jsdom does not reproduce Chrome's blur on native disabled, keyboard default
// activation, or Tab navigation. Real-browser focus qualification is separate.
(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
  .IS_REACT_ACT_ENVIRONMENT = true;
let container: HTMLDivElement;
let root: Root | null = null;
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function button(label: string) {
  const match = [...container.querySelectorAll<HTMLButtonElement>("button")]
    .find((element) => (element.getAttribute("aria-label") || element.textContent?.trim()) === label);
  expect(match, `button ${label}`).toBeTruthy();
  return match!;
}
async function click(label: string) {
  await act(async () => { button(label).click(); });
}
async function mountWork() {
  root = createRoot(container);
  await act(async () => { root!.render(<App />); });
  await click("Work");
}
function expectPending(control: HTMLButtonElement) {
  // This is the discriminator that the old jsdom focus assertion lacked.
  expect(control.disabled).toBe(false);
  expect(control.hasAttribute("disabled")).toBe(false);
  expect(control.getAttribute("aria-disabled")).toBe("true");
  expect(control.tabIndex).toBe(0);
  expect(container.textContent).toContain("Reading the bounded Work projection…");
}
beforeEach(() => {
  history.replaceState(null, "", "/os/");
  delete window.MastermindMissionHost;
  delete (window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;
  container = document.createElement("div"); document.body.append(container);
});
afterEach(async () => {
  if (root) await act(async () => { root!.unmount(); });
  root = null; container.remove(); delete window.MastermindMissionHost; vi.restoreAllMocks();
});

describe("Work refresh pending-control semantics", () => {
  it("keeps the initial pending read focusable and rejects repeated DOM activation", async () => {
    const initial = deferred<WorkDocument>();
    const readWork = vi.fn(() => initial.promise);
    window.MastermindMissionHost = { readPrograms: async () => controlRoomFixture(), readWork };
    await mountWork();
    const control = button("Refresh Work");
    expectPending(control);
    await act(async () => { control.click(); control.click(); });
    expect(readWork).toHaveBeenCalledTimes(1);
    await act(async () => { initial.resolve(decodeWorkDocument(workAvailable)!); });
    expect(control.getAttribute("aria-disabled")).toBe("false");
  });

  it.each(["success", "refusal", "rejection", "malformed"] as const)(
    "keeps the same focusable control guarded until %s settlement", async (settlement) => {
      const retry = deferred<unknown>();
      const readWork = vi.fn().mockRejectedValueOnce(new Error("temporary"))
        .mockReturnValueOnce(retry.promise).mockResolvedValue(structuredClone(workAvailable));
      const readPrograms = vi.fn(async () => controlRoomFixture());
      window.MastermindMissionHost = { readPrograms, readWork };
      await mountWork();
      const control = button("Refresh Work"); control.focus();
      // Same-turn activations as well as later events must remain one read.
      await act(async () => { control.click(); control.click(); control.click(); });
      expectPending(control);
      await act(async () => { control.click(); control.click(); });
      expect(readWork).toHaveBeenCalledTimes(2);
      expect(readPrograms).toHaveBeenCalledTimes(1);
      await act(async () => {
        if (settlement === "rejection") retry.reject(new Error("temporary again"));
        else retry.resolve(settlement === "success" ? structuredClone(workAvailable)
          : settlement === "refusal" ? structuredClone(workUnavailable) : {});
      });
      expect(button("Refresh Work")).toBe(control);
      expect(control.disabled).toBe(false);
      expect(control.getAttribute("aria-disabled")).toBe("false");
      expect(document.activeElement).toBe(control);
      expect(container.textContent).toContain(settlement === "success" ? "JOB-2"
        : settlement === "refusal" ? "projection_refused" : "SOURCE_UNAVAILABLE");
      expect(readWork).toHaveBeenCalledTimes(2);
      if (settlement !== "success") {
        await click("Refresh Work");
        expect(readWork).toHaveBeenCalledTimes(3);
        expect(container.textContent).toContain("JOB-2");
      }
    },
  );

  it.each(["success", "rejection"] as const)(
    "does not reclaim focus after the user selects another control before %s", async (settlement) => {
      const retry = deferred<unknown>();
      window.MastermindMissionHost = {
        readPrograms: async () => controlRoomFixture(),
        readWork: vi.fn().mockRejectedValueOnce(new Error("temporary")).mockReturnValueOnce(retry.promise),
      };
      await mountWork();
      button("Refresh Work").focus(); await click("Refresh Work");
      const target = button("Projects"); target.focus();
      await act(async () => {
        if (settlement === "success") retry.resolve(structuredClone(workAvailable));
        else retry.reject(new Error("temporary again"));
      });
      expect(document.activeElement).toBe(target);
    },
  );

  it.each(["success", "rejection"] as const)(
    "does not reclaim focus after navigation unmounts the control before %s", async (settlement) => {
      const retry = deferred<unknown>();
      const readPrograms = vi.fn(async () => controlRoomFixture());
      const readWork = vi.fn().mockRejectedValueOnce(new Error("temporary")).mockReturnValueOnce(retry.promise);
      window.MastermindMissionHost = { readPrograms, readWork };
      await mountWork();
      const control = button("Refresh Work"); control.focus(); await click("Refresh Work");
      const target = button("Today"); target.focus(); await click("Today");
      expect(control.isConnected).toBe(false);
      const locationAfterNavigation = location.href;
      await act(async () => {
        if (settlement === "success") retry.resolve(structuredClone(workAvailable));
        else retry.reject(new Error("temporary again"));
      });
      expect(document.activeElement).toBe(target);
      expect(location.href).toBe(locationAfterNavigation);
      expect(readWork).toHaveBeenCalledTimes(2);
      expect(readPrograms).toHaveBeenCalledTimes(1);
    },
  );

  it("keeps a missing Work reader natively disabled", async () => {
    window.MastermindMissionHost = { readPrograms: async () => controlRoomFixture() };
    await mountWork();
    const control = button("Refresh Work");
    expect(control.disabled).toBe(true);
    expect(control.getAttribute("aria-disabled")).toBe("true");
    await act(async () => { control.click(); });
    expect(container.textContent).toContain("QUALIFIED_WORK_READ_UNAVAILABLE");
  });

  it.each(["success", "rejection"] as const)(
    "keeps sign-out disabled and ignores late %s from the aborted retry", async (settlement) => {
      const retry = deferred<unknown>();
      let state: AuthState = { status: "signed_in", reason: null, acquisition: true, content: false };
      let notify!: (state: AuthState) => void;
      const readWork = vi.fn().mockRejectedValueOnce(new Error("temporary")).mockReturnValueOnce(retry.promise);
      window.MastermindMissionHost = {
        readPrograms: async () => controlRoomFixture(), readWork,
        auth: { getState: () => state, subscribe: listener => { notify = listener; return () => {}; },
          signIn: async () => {}, signOut: async () => {} },
      };
      await mountWork(); await click("Refresh Work");
      const signal = readWork.mock.calls[1][0].signal as AbortSignal;
      await act(async () => {
        state = { status: "signed_out", reason: null, acquisition: false, content: false }; notify(state);
      });
      expect(signal.aborted).toBe(true);
      const control = button("Refresh Work");
      expect(control.disabled).toBe(true);
      expect(control.getAttribute("aria-disabled")).toBe("true");
      await act(async () => {
        control.click();
        if (settlement === "success") retry.resolve(structuredClone(workAvailable));
        else retry.reject(new Error("old epoch"));
      });
      expect(readWork).toHaveBeenCalledTimes(2);
      expect(container.textContent).not.toContain("JOB-2");
      expect(container.textContent).toContain("AUTHENTICATION_REQUIRED");
    },
  );

  it("preserves project selection, root filter and unrelated read counts through pending", async () => {
    const retry = deferred<unknown>();
    const readWork = vi.fn().mockRejectedValueOnce(new Error("temporary")).mockReturnValueOnce(retry.promise);
    const readProgramsObservation = vi.fn(async () => decodeProgramsObservation({
      ...structuredClone(programsAvailable),
      control_room: JSON.parse(JSON.stringify(controlRoomFixture()).replaceAll("JOB-A", "JOB-2")),
    }));
    const readMission = vi.fn(async ({ workRef, rootJobId }: { workRef: string; rootJobId: string }) => missionFixture(workRef, rootJobId));
    window.MastermindMissionHost = { readProgramsObservation, readMission, readWork };
    await mountWork(); await click("Projects"); await click("Open project Alpha program"); await click("Work");
    const url = location.href;
    const programCalls = readProgramsObservation.mock.calls.length, missionCalls = readMission.mock.calls.length;
    const control = button("Refresh Work"); control.focus(); await click("Refresh Work");
    expectPending(control); await click("Refresh Work");
    await act(async () => { retry.resolve(structuredClone(workAvailable)); });
    expect(button("Refresh Work")).toBe(control);
    expect(location.href).toBe(url);
    expect(container.querySelector('[role="tab"][aria-selected="true"]')?.textContent).toBe("Work");
    expect(container.textContent).toContain("Exact project root JOB-2; other roots remain outside this project view.");
    expect(container.textContent).toContain("CHECKPOINTED");
    expect(container.textContent).not.toContain("JOB-1");
    expect(readWork).toHaveBeenCalledTimes(2);
    expect(readProgramsObservation).toHaveBeenCalledTimes(programCalls);
    expect(readMission).toHaveBeenCalledTimes(missionCalls);
  });
});
