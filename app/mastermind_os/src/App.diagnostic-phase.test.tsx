// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { AuthState, MissionHost } from "./host";
import { decodeProgramsObservation, type ProgramsObservation } from "./programs-observation";
import { controlRoomFixture, missionFixture } from "./test-fixtures";
import programsAvailable from "./fixtures/programs-available-workspace-service.json";
import { decodeWorkDocument } from "./work";
import workAvailable from "./fixtures/work-service-available.json";

// Programs read-phase regression through the real App: the diagnostic side
// state must track the existing single-scheduled read without adding reads,
// subscriptions or refreshes, and a stale reply must never overwrite it.
(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let container: HTMLDivElement;
let root: Root | null = null;
const qualified = () => decodeProgramsObservation({ ...structuredClone(programsAvailable), control_room: controlRoomFixture() });
function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function diagnosticValue(term: string): string | null {
  // The diagnostic fields live inside the existing fallback Technical details
  // disclosures; their content stays in the DOM while the disclosure is closed.
  for (const dt of Array.from(container.querySelectorAll("dt"))) {
    if (dt.textContent === term) return dt.nextElementSibling?.textContent ?? null;
  }
  return null;
}
function openDiagnosticDetails(): HTMLDetailsElement | null {
  const summary = [...container.querySelectorAll("details summary")]
    .find((element) => element.textContent === "Technical details" &&
      element.closest("details")?.querySelector("dl"));
  return summary ? (summary.closest("details") as HTMLDetailsElement) : null;
}
async function mount() { root = createRoot(container); await act(async () => { root!.render(<App />); }); }
function sourceHost(readProgramsObservation: MissionHost["readProgramsObservation"]) {
  const readWork = vi.fn(async () => decodeWorkDocument(workAvailable)!);
  const readMission = vi.fn(async ({ workRef, rootJobId }: { workRef: string; rootJobId: string }) => missionFixture(workRef, rootJobId));
  const readPrograms = vi.fn(async () => controlRoomFixture());
  window.MastermindMissionHost = { readProgramsObservation, readPrograms, readWork, readMission };
  return { readWork, readMission, readPrograms };
}
const diagnostics = vi.fn(() => ({
  hostKind: "unknown",
  launchConfigured: null,
  frontendResourceConfigured: null,
  nativeResourceConfigured: null,
  acquisitionAvailable: true,
  contentAvailable: false,
  executiveAvailable: null,
  executiveContextPhase: "not_requested",
}));
function authHost(acquisition: boolean) {
  let state: AuthState = {
    status: acquisition ? "signed_in" : "signed_out",
    reason: null, acquisition, content: false,
  };
  let generation = 0;
  let notify: (state: AuthState) => void = () => {};
  const auth = {
    getState: () => state,
    subscribe: (listener: (state: AuthState) => void) => { notify = listener; return () => {}; },
    signIn: vi.fn(async () => {}), signOut: vi.fn(async () => {}),
  };
  Object.assign(window.MastermindMissionHost!, {
    auth, diagnostics, invalidationGeneration: () => generation,
  });
  return { auth, change: async (next: boolean) => {
    await act(async () => {
      generation++;
      state = { status: next ? "signed_in" : "signed_out", reason: null, acquisition: next, content: false };
      notify(state);
    });
  } };
}
beforeEach(() => {
  history.replaceState(null, "", "/os/"); delete window.MastermindMissionHost;
  delete (window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;
  diagnostics.mockClear();
  container = document.createElement("div"); document.body.append(container);
});
afterEach(async () => {
  if (root) await act(async () => { root!.unmount(); });
  root = null; container.remove(); delete window.MastermindMissionHost; vi.restoreAllMocks();
});

describe("Programs read diagnostics", () => {
  it("tracks the one scheduled read from pending to ready without extra reads, and opening the disclosure takes a fresh snapshot only", async () => {
    const wait = deferred<ProgramsObservation>();
    const read = vi.fn(() => wait.promise);
    const { readPrograms } = sourceHost(read);
    authHost(true);
    await mount();
    expect(read).toHaveBeenCalledTimes(1);
    expect(diagnosticValue("Projects read phase")).toBe("pending");
    const callsBefore = diagnostics.mock.calls.length;
    const details = openDiagnosticDetails();
    expect(details).toBeTruthy();
    await act(async () => { details!.querySelector("summary")!.click(); });
    expect(details!.open).toBe(true);
    // The disclosure tick re-renders for a fresh snapshot only: no new read.
    expect(diagnostics.mock.calls.length).toBeGreaterThan(callsBefore);
    expect(read).toHaveBeenCalledTimes(1);
    await act(async () => { wait.resolve(qualified()); });
    expect(diagnosticValue("Projects read phase")).toBe("ready");
    expect(diagnosticValue("Projects read reason")).toBe("NONE");
    expect(read).toHaveBeenCalledTimes(1);
    expect(readPrograms).not.toHaveBeenCalled();
  });

  it("shows private entry and schedules no read when acquisition is denied", async () => {
    const read = vi.fn(async () => qualified());
    sourceHost(read);
    authHost(false);
    await mount();
    expect(read).not.toHaveBeenCalled();
    // The accepted private-entry composition replaces the workspace shell, so
    // the read-phase disclosure is not mounted for a denied acquisition.
    expect(container.textContent).toContain("Sign in to your workspace.");
    expect(diagnosticValue("Projects read phase")).toBeNull();
  });

  it("reports not_requested when the host exposes no Programs reader", async () => {
    window.MastermindMissionHost = {};
    authHost(true);
    await mount();
    expect(diagnosticValue("Projects read phase")).toBe("not_requested");
  });

  it.each([
    ["AUTHENTICATION_REQUIRED", "auth_unavailable"],
    ["SOURCE_UNAVAILABLE", "transport_failure"],
    ["ACCESS_REFUSED", "transport_failure"],
    ["SELECTION_UNAVAILABLE", "transport_failure"],
    ["RESPONSE_INVALID", "invalid_response"],
    ["RESPONSE_BOUND", "invalid_response"],
    ["PROGRAM_RESPONSE_INVALID", "invalid_response"],
    ["PROGRAM_OBSERVATION_INVALID", "invalid_response"],
    ["AUTHENTICATION_CHANGED", "unknown"],
    ["READ_CANCELLED", "unknown"],
    ["private detail: principal acct-991", "unknown"],
  ] as Array<[string, string]>)("maps a failed read carrying %s to %s", async (message, expected) => {
    const read = vi.fn(async () => { throw new Error(message); });
    sourceHost(read);
    authHost(true);
    await mount();
    expect(read).toHaveBeenCalledTimes(1);
    expect(diagnosticValue("Projects read phase")).toBe(expected);
    expect(diagnosticValue("Projects read reason")).toBe(message.startsWith("private detail") ? "UNKNOWN" : message);
    expect(container.textContent).not.toContain("acct-991");
  });

  it("hands the shell to private entry on auth invalidation and ignores a stale reply", async () => {
    const wait = deferred<ProgramsObservation>();
    const read = vi.fn().mockReturnValueOnce(wait.promise).mockResolvedValue(qualified());
    sourceHost(read);
    const auth = authHost(true);
    await mount();
    expect(read).toHaveBeenCalledTimes(1);
    expect(diagnosticValue("Projects read phase")).toBe("pending");
    await auth.change(false);
    expect(read).toHaveBeenCalledTimes(1);
    // Sign-out replaces the shell with private entry; the phase disclosure
    // unmounts and the in-flight reply must never reschedule a read.
    expect(container.textContent).toContain("Sign in to your workspace.");
    expect(diagnosticValue("Projects read phase")).toBeNull();
    await act(async () => { wait.resolve(qualified()); });
    expect(container.textContent).toContain("Sign in to your workspace.");
    expect(diagnosticValue("Projects read phase")).toBeNull();
    expect(read).toHaveBeenCalledTimes(1);
  });
});
