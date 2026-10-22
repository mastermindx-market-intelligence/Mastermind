// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { AuthState, MissionHost } from "./host";
import { decodeProgramsObservation, type ProgramsObservation } from "./programs-observation";
import { controlRoomFixture, missionFixture } from "./test-fixtures";
import programsAvailable from "./fixtures/programs-available-workspace-service.json";
import programsUnavailable from "./fixtures/programs-unavailable-workspace-service.json";
import { decodeWorkDocument } from "./work";
import workAvailable from "./fixtures/work-service-available.json";

// Actual App component proof with existing host boundaries. jsdom does not prove
// browser keyboard default activation, Tab navigation or native blur behavior.
(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let container: HTMLDivElement;
let root: Root | null = null;
const qualified = () => decodeProgramsObservation({ ...structuredClone(programsAvailable), control_room: controlRoomFixture() });
const refused = () => decodeProgramsObservation(structuredClone(programsUnavailable));
function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function findButton(name: string) {
  return [...container.querySelectorAll<HTMLButtonElement>("button")]
    .find(element => (element.getAttribute("aria-label") || element.textContent?.trim()) === name);
}
function button(name: string) { const element = findButton(name); expect(element, `button ${name}`).toBeTruthy(); return element!; }
async function click(name: string) { await act(async () => { button(name).click(); }); }
async function mount() { root = createRoot(container); await act(async () => { root!.render(<App />); }); }
async function projects() { await mount(); await click("Projects"); }
function pending(control: HTMLButtonElement) {
  expect(control.disabled).toBe(false);
  expect(control.hasAttribute("disabled")).toBe(false);
  expect(control.getAttribute("aria-disabled")).toBe("true");
  expect(control.tabIndex).toBe(0);
}
function ready(control: HTMLButtonElement) {
  expect(control.disabled).toBe(false); expect(control.getAttribute("aria-disabled")).toBe("false");
}
function sourceHost(readProgramsObservation: MissionHost["readProgramsObservation"]) {
  const readWork = vi.fn(async () => decodeWorkDocument(workAvailable)!);
  const readMission = vi.fn(async ({ workRef, rootJobId }: { workRef: string; rootJobId: string }) => missionFixture(workRef, rootJobId));
  const readPrograms = vi.fn(async () => controlRoomFixture());
  window.MastermindMissionHost = { readProgramsObservation, readPrograms, readWork, readMission };
  return { readWork, readMission, readPrograms };
}
function authHost() {
  let state: AuthState = { status: "signed_in", reason: null, acquisition: true, content: false };
  let generation = 0, notify!: (state: AuthState) => void;
  const auth = { getState: () => state, subscribe: (listener: (state: AuthState) => void) => { notify = listener; return () => {}; },
    signIn: vi.fn(async () => {}), signOut: vi.fn(async () => {}) };
  Object.assign(window.MastermindMissionHost!, { auth, invalidationGeneration: () => generation });
  return { auth, change: async (acquisition: boolean) => {
    await act(async () => { generation++; state = { status: acquisition ? "signed_in" : "signed_out", reason: null, acquisition, content: false }; notify(state); });
  } };
}
beforeEach(() => {
  history.replaceState(null, "", "/os/"); delete window.MastermindMissionHost;
  delete (window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;
  container = document.createElement("div"); document.body.append(container);
});
afterEach(async () => {
  if (root) await act(async () => { root!.unmount(); });
  root = null; container.remove(); delete window.MastermindMissionHost; vi.restoreAllMocks();
});

describe("Programs collection manual recovery", () => {
  it.each(["rejection", "typed unavailable", "malformed"] as const)("recovers a startup %s without remount or unrelated reads", async failure => {
    const read = vi.fn().mockImplementationOnce(async () => {
      if (failure === "rejection") throw new Error("transient");
      return failure === "typed unavailable" ? refused() : { ...qualified(), controlRoom: {} };
    }).mockImplementation(async () => qualified());
    const { readWork, readMission, readPrograms } = sourceHost(read);
    await projects(); expect(findButton("Open project Beta program")).toBeUndefined();
    const before = location.href;
    await click("Refresh Projects");
    expect(findButton("Open project Beta program")).toBeTruthy();
    expect(read).toHaveBeenCalledTimes(2); expect(readPrograms).not.toHaveBeenCalled();
    expect(readWork).toHaveBeenCalledTimes(1); expect(readMission).not.toHaveBeenCalled();
    expect(location.href).toBe(before);
  });

  it("keeps initial pending focusable and refuses duplicate activation", async () => {
    const wait = deferred<ProgramsObservation>(); const read = vi.fn(() => wait.promise); sourceHost(read);
    await projects(); const control = button("Refresh Projects"); pending(control);
    await act(async () => { control.click(); control.click(); }); expect(read).toHaveBeenCalledTimes(1);
    await act(async () => { wait.resolve(qualified()); }); ready(control);
    expect(button("Refresh Projects")).toBe(control);
  });

  it.each(["success", "rejection", "typed unavailable", "malformed"] as const)("keeps one focusable guarded control until retry %s", async settlement => {
    const wait = deferred<ProgramsObservation>();
    const read = vi.fn().mockRejectedValueOnce(new Error("first")).mockReturnValueOnce(wait.promise).mockImplementation(async () => qualified());
    const { readWork, readMission } = sourceHost(read); await projects();
    const control = button("Refresh Projects"); control.focus();
    await act(async () => { control.click(); control.click(); control.click(); }); pending(control);
    await act(async () => { control.click(); control.click(); }); expect(read).toHaveBeenCalledTimes(2);
    await act(async () => {
      if (settlement === "rejection") wait.reject(new Error("again"));
      else wait.resolve(settlement === "success" ? qualified() : settlement === "typed unavailable" ? refused() : { ...qualified(), controlRoom: {} });
    });
    ready(control); expect(button("Refresh Projects")).toBe(control); expect(document.activeElement).toBe(control);
    expect(readWork).toHaveBeenCalledTimes(1); expect(readMission).not.toHaveBeenCalled();
    if (settlement !== "success") { expect(findButton("Open project Beta program")).toBeUndefined(); await click("Refresh Projects"); expect(read).toHaveBeenCalledTimes(3); }
    expect(findButton("Open project Beta program")).toBeTruthy();
  });

  it("recovers a deep-linked exact Mission only after its fresh collection qualifies", async () => {
    history.replaceState(null, "", "/os/?work_ref=WS%3ABETA&root_job_id=JOB-B");
    const wait = deferred<ProgramsObservation>(); const read = vi.fn().mockRejectedValueOnce(new Error("first")).mockReturnValueOnce(wait.promise);
    const { readMission, readWork } = sourceHost(read); await projects(); const before = location.href;
    await click("Refresh Projects"); expect(readMission).not.toHaveBeenCalled(); expect(location.href).toBe(before);
    await act(async () => { wait.resolve(qualified()); });
    expect(readMission).toHaveBeenCalledTimes(1); expect(readMission.mock.calls[0][0]).toMatchObject({ workRef: "WS:BETA", rootJobId: "JOB-B" });
    expect(readWork).toHaveBeenCalledTimes(1); expect(location.href).toBe(before);
  });

  it("recovers a selection-time failure in place while preserving exact project and tab", async () => {
    const read = vi.fn().mockResolvedValueOnce(qualified()).mockRejectedValueOnce(new Error("selection read")).mockResolvedValue(qualified());
    const { readMission, readWork } = sourceHost(read); await projects(); await click("Open project Beta program");
    expect(container.textContent).toContain("PROGRAM_SOURCE_UNAVAILABLE"); expect(readMission).not.toHaveBeenCalled();
    const before = location.href; await click("Refresh Projects");
    expect(read).toHaveBeenCalledTimes(3); expect(readMission).toHaveBeenCalledTimes(1);
    expect(readMission.mock.calls[0][0]).toMatchObject({ workRef: "WS:BETA", rootJobId: "JOB-B" });
    expect(container.querySelector('[role="tab"][aria-selected="true"]')?.textContent).toBe("Overview");
    expect(location.href).toBe(before); expect(readWork).toHaveBeenCalledTimes(1);
  });

  it("does not admit an unresolved deep-link pair after successful collection recovery", async () => {
    history.replaceState(null, "", "/os/?work_ref=WS%3ABETA&root_job_id=JOB-WRONG");
    const read = vi.fn().mockRejectedValueOnce(new Error("first")).mockResolvedValue(qualified());
    const { readMission } = sourceHost(read); await projects(); const before = location.href; await click("Refresh Projects");
    expect(readMission).not.toHaveBeenCalled(); expect(location.href).toBe(before);
    await act(async () => { window.dispatchEvent(new PopStateEvent("popstate")); });
    expect(container.textContent).toContain("EXACT_SELECTION_UNRESOLVED");
    expect(readMission).not.toHaveBeenCalled();
  });

  it("reuses the legacy reader without qualifying bare data as Projects owner receipt", async () => {
    const readPrograms = vi.fn().mockRejectedValueOnce(new Error("first")).mockResolvedValue(controlRoomFixture());
    const readMission = vi.fn(); window.MastermindMissionHost = { readPrograms, readMission };
    await mount(); await click("Open Programs"); await click("Refresh Projects");
    expect(readPrograms).toHaveBeenCalledTimes(2); expect(container.textContent).toContain("Beta program");
    await click("Projects"); expect(findButton("Open project Beta program")).toBeUndefined(); expect(readMission).not.toHaveBeenCalled();
  });

  it("shares the same pending read across Projects and legacy Programs navigation", async () => {
    const wait = deferred<ProgramsObservation>(); const read = vi.fn().mockRejectedValueOnce(new Error("first")).mockReturnValueOnce(wait.promise);
    sourceHost(read); await projects(); await click("Refresh Projects"); await click("Today"); await click("Open Programs");
    pending(button("Refresh Projects")); await click("Refresh Projects"); expect(read).toHaveBeenCalledTimes(2);
    await act(async () => { wait.resolve(qualified()); }); ready(button("Refresh Projects"));
    expect(container.textContent).toContain("Beta program"); await click("Projects"); expect(findButton("Open project Beta program")).toBeTruthy();
  });

  it("keeps missing readers and denied acquisition natively disabled", async () => {
    window.MastermindMissionHost = {}; await projects(); let control = button("Refresh Projects");
    expect(control.disabled).toBe(true); expect(control.getAttribute("aria-disabled")).toBe("true");
    await act(async () => { root!.unmount(); }); root = null;
    const read = vi.fn(async () => qualified()); sourceHost(read); const auth = authHost();
    // Start admitted, then revoke to exercise notification and loader fences.
    await projects(); await auth.change(false); control = button("Refresh Projects");
    expect(control.disabled).toBe(true); await click("Refresh Projects"); expect(read).toHaveBeenCalledTimes(1);
    expect(auth.auth.signIn).not.toHaveBeenCalled(); expect(auth.auth.signOut).not.toHaveBeenCalled();
  });

  it.each(["signed_out", "signed_in"] as const)("never starts a read when %s acquisition is denied initially", async status => {
    const read = vi.fn(async () => qualified()); sourceHost(read);
    const state: AuthState = { status, reason: null, acquisition: false, content: false };
    window.MastermindMissionHost!.auth = { getState: () => state, subscribe: () => () => {}, signIn: vi.fn(async () => {}), signOut: vi.fn(async () => {}) };
    await projects(); expect(button("Refresh Projects").disabled).toBe(true);
    await click("Refresh Projects"); expect(read).not.toHaveBeenCalled();
  });

  it.each(["success", "rejection"] as const)("aborts on unmount and tolerates late retry %s", async settlement => {
    const wait = deferred<ProgramsObservation>(); const read = vi.fn().mockRejectedValueOnce(new Error("first")).mockReturnValueOnce(wait.promise);
    const { readMission } = sourceHost(read); await projects(); await click("Refresh Projects");
    const signal = read.mock.calls[1][0].signal as AbortSignal;
    await act(async () => { root!.unmount(); }); root = null; expect(signal.aborted).toBe(true);
    await act(async () => { if (settlement === "success") wait.resolve(qualified()); else wait.reject(new Error("detached")); });
    expect(container.textContent).toBe(""); expect(read).toHaveBeenCalledTimes(2); expect(readMission).not.toHaveBeenCalled();
  });

  it.each(["success", "rejection"] as const)("ignores late retry %s after sign-out", async settlement => {
    const wait = deferred<ProgramsObservation>(); const read = vi.fn().mockRejectedValueOnce(new Error("first")).mockReturnValueOnce(wait.promise);
    const { readMission } = sourceHost(read); const auth = authHost(); await projects(); await click("Refresh Projects");
    const signal = read.mock.calls[1][0].signal as AbortSignal; await auth.change(false); expect(signal.aborted).toBe(true);
    await act(async () => { if (settlement === "success") wait.resolve(qualified()); else wait.reject(new Error("old principal")); });
    expect(button("Refresh Projects").disabled).toBe(true); expect(findButton("Open project Beta program")).toBeUndefined();
    expect(read).toHaveBeenCalledTimes(2); expect(readMission).not.toHaveBeenCalled();
  });

  it.each(["success", "rejection"] as const)("does not replace a newer same-shaped auth generation with late %s", async settlement => {
    const wait = deferred<ProgramsObservation>(); const fresh = qualified();
    (fresh.controlRoom as ReturnType<typeof controlRoomFixture>).work[1].agent_os.title = "New principal Beta";
    const read = vi.fn().mockRejectedValueOnce(new Error("first")).mockReturnValueOnce(wait.promise).mockResolvedValueOnce(fresh);
    sourceHost(read); const auth = authHost(); await projects(); await click("Refresh Projects");
    const signal = read.mock.calls[1][0].signal as AbortSignal; await auth.change(true); expect(signal.aborted).toBe(true);
    expect(findButton("Open project New principal Beta")).toBeTruthy();
    await act(async () => { if (settlement === "success") wait.resolve(qualified()); else wait.reject(new Error("old generation")); });
    expect(findButton("Open project New principal Beta")).toBeTruthy(); expect(findButton("Open project Beta program")).toBeUndefined();
    expect(read).toHaveBeenCalledTimes(3);
  });

  it.each(["success", "rejection"] as const)("ignores late retry %s after selection changes", async settlement => {
    history.replaceState(null, "", "/os/?work_ref=WS%3AALPHA&root_job_id=JOB-A");
    const old = deferred<ProgramsObservation>(); const next = deferred<ProgramsObservation>();
    const read = vi.fn().mockRejectedValueOnce(new Error("first")).mockReturnValueOnce(old.promise).mockReturnValueOnce(next.promise);
    const { readMission, readWork } = sourceHost(read); await projects(); await click("Refresh Projects");
    const signal = read.mock.calls[1][0].signal as AbortSignal;
    await act(async () => { history.pushState(null, "", "/os/?work_ref=WS%3ABETA&root_job_id=JOB-B"); window.dispatchEvent(new PopStateEvent("popstate")); });
    expect(signal.aborted).toBe(true); pending(button("Refresh Projects"));
    await act(async () => { if (settlement === "success") old.resolve(qualified()); else old.reject(new Error("old selection")); });
    expect(readMission).not.toHaveBeenCalled(); pending(button("Refresh Projects"));
    await act(async () => { next.resolve(qualified()); });
    expect(readMission).toHaveBeenCalledTimes(1); expect(readMission.mock.calls[0][0]).toMatchObject({ workRef: "WS:BETA", rootJobId: "JOB-B" });
    expect(readWork).toHaveBeenCalledTimes(1); expect(location.search).toBe("?work_ref=WS%3ABETA&root_job_id=JOB-B");
  });

  it.each(["success", "rejection"] as const)("does not steal focus or navigate after retry %s on another route", async settlement => {
    const wait = deferred<ProgramsObservation>(); const read = vi.fn().mockRejectedValueOnce(new Error("first")).mockReturnValueOnce(wait.promise);
    sourceHost(read); await projects(); button("Refresh Projects").focus(); await click("Refresh Projects");
    const target = button("Today"); target.focus(); await click("Today"); const before = location.href;
    await act(async () => { if (settlement === "success") wait.resolve(qualified()); else wait.reject(new Error("again")); });
    expect(document.activeElement).toBe(target); expect(location.href).toBe(before); expect(findButton("Refresh Projects")).toBeUndefined();
  });

  it("preserves an unsent Office draft and reuses current same-project Mission reopening", async () => {
    const read = vi.fn(async () => qualified()); const { readMission, readWork } = sourceHost(read);
    readMission.mockRejectedValueOnce(new Error("mission-only"));
    await projects(); await click("Open project Beta program"); expect(container.textContent).toContain("SOURCE_UNAVAILABLE");
    await click("Today"); const draft = container.querySelector<HTMLTextAreaElement>("#office-direction")!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(draft, "Keep my unsent direction");
      draft.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await click("Projects"); await click("Refresh Projects");
    // Re-entering AVAILABLE re-admits the selected Mission through its existing effect.
    expect(readMission).toHaveBeenCalledTimes(2); expect(readWork).toHaveBeenCalledTimes(1);
    await click("Today"); expect(container.querySelector<HTMLTextAreaElement>("#office-direction")!.value).toBe("Keep my unsent direction");
    await click("Projects"); const reads = read.mock.calls.length; await click("Open project Beta program");
    expect(read).toHaveBeenCalledTimes(reads); expect(readMission).toHaveBeenCalledTimes(3);
  });
});
