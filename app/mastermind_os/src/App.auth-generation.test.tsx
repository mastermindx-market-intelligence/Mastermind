// @vitest-environment jsdom
// Native events and source documents are injected fixtures, not live account reads.
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { flushSync } from "react-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { controlRoomFixture } from "./test-fixtures";
import { bindMissionHost, createNativeClient, type AuthState, type RawClient } from "./host";
import programsFixture from "./fixtures/programs-available-workspace-service.json";
import pairedFixture from "./fixtures/window-mission-association-producer.json";
import workFixture from "./fixtures/work-service-available.json";

const signed: AuthState = { status: "signed_in", reason: null, acquisition: true, content: true };
const deferred = () => {
  let resolve!: (value: unknown) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<unknown>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
const flush = async () => { for (let n = 0; n < 20; n++) await Promise.resolve(); };
function programs(title = "Previous scope program") {
  const envelope = structuredClone(programsFixture);
  const room = controlRoomFixture();
  const work = room.work[0], responsibility = room.autonomy.responsibilities[0];
  work.work_ref = "WS:FABRIC";
  work.agent_os.title = title;
  work.agent_os.workstream = "FABRIC";
  responsibility.responsibility_ref = "WS:FABRIC";
  responsibility.root_job_id = "JOB-001";
  responsibility.root_job_candidates = ["JOB-001"];
  responsibility.root_job_ambiguous = false;
  responsibility.runtime_root_state = "RESOLVED";
  room.work = [work];
  room.autonomy.responsibilities = [responsibility];
  return { ...envelope, control_room: room };
}
function mission(title = "Previous scope mission") {
  const doc = structuredClone(pairedFixture.mission);
  doc.program.title = title;
  return doc;
}
async function nativeFixture() {
  let notify!: (event: { payload: unknown }) => void;
  let hold = false;
  const pendingPrograms: ReturnType<typeof deferred>[] = [];
  const pendingMission = deferred(), pendingWindow = deferred();
  const invoke = vi.fn(async (command: string) => {
    if (command === "auth_status") return signed;
    if (command === "read_programs") {
      if (!hold) return programs();
      const pending = deferred();
      pendingPrograms.push(pending);
      return pending.promise;
    }
    if (command === "read_work") return structuredClone(workFixture);
    if (command === "read_mission_v3") return hold ? pendingMission.promise : mission();
    if (command === "read_current_window") return hold ? pendingWindow.promise : pairedFixture.window;
    throw new Error("unexpected fixture command: " + command);
  });
  const client = await createNativeClient(invoke as never, async (_name, listener) => {
    notify = listener;
    return () => {};
  });
  const host = bindMissionHost(client);
  return { client, host, invoke, notify, pendingPrograms,
    hold: () => { hold = true; },
    settle: () => {
      for (const pending of pendingPrograms) pending.resolve(programs("Current scope program"));
      pendingMission.resolve(mission("Current scope mission"));
      pendingWindow.resolve(pairedFixture.window);
    },
  };
}
beforeEach(async () => {
  history.replaceState(null, "", "/os/?work_ref=WS%3AFABRIC&root_job_id=JOB-001");
  delete (window as any).__TAURI_INTERNALS__;
  delete window.MastermindMissionHost;
  const { webcrypto } = await vi.importActual<{ webcrypto: Crypto }>("node:crypto");
  vi.stubGlobal("crypto", webcrypto);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); delete window.MastermindMissionHost; });

describe("native auth generation reaches the actual workspace", () => {
  it("advances the typed host generation even when the public auth state is identical", async () => {
    const e = await nativeFixture();
    const before = e.host.invalidationGeneration!();
    const state = e.client.getState();
    e.notify({ payload: { ...signed } });
    expect(e.client.getState()).toEqual(state);
    expect(e.host.invalidationGeneration!()).toBeGreaterThan(before);
    expect(Object.keys(e.client.getState()).sort()).toEqual(["acquisition", "content", "reason", "status"]);
  });
  it("does not advance generation or notify for a malformed native event", async () => {
    const e = await nativeFixture();
    const listener = vi.fn();
    e.host.auth!.subscribe(listener);
    const before = e.host.invalidationGeneration!();
    e.notify({ payload: { ...signed, principal: "caller-must-not-invent" } });
    expect(listener).not.toHaveBeenCalled();
    expect(e.host.invalidationGeneration!()).toBe(before);
  });
  it.each([
    ["Mission Workspace", "Previous scope mission"],
    ["Programs", "Previous scope program"],
    ["Conversation", "plan child visible"],
  ])("clears rendered %s on an identical-state native boundary before replacement reads finish", async (route, privateText) => {
    const e = await nativeFixture();
    window.MastermindMissionHost = e.host;
    render(<App />);
    await userEvent.setup().click(screen.getByRole("button", { name: route }));
    await waitFor(() => expect(document.body.textContent).toContain(privateText));
    const reads = e.invoke.mock.calls.filter(([name]) => name === "read_programs").length;
    e.hold();
    try {
      await act(async () => { e.notify({ payload: { ...signed } }); await flush(); });
      expect(document.body.textContent).not.toContain(privateText);
      expect(e.invoke.mock.calls.filter(([name]) => name === "read_programs")).toHaveLength(reads + 1);
    } finally { await act(async () => { e.settle(); await flush(); }); }
  });
  it("clears rendered Work in the auth-notification commit before passive reacquisition", async () => {
    const e = await nativeFixture();
    window.MastermindMissionHost = e.host;
    render(<App />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Work" }));
    await waitFor(() => expect(document.body.textContent).toContain("JOB-2"));
    e.hold();
    try {
      flushSync(() => { e.notify({ payload: { ...signed } }); });
      expect(document.body.textContent).not.toContain("JOB-2");
    } finally {
      await act(async () => { e.settle(); await flush(); });
    }
  });

  it.each(["resolve", "reject"] as const)("cancels the superseded typed read and refuses its late %s across an identical-state auth boundary", async (lateOutcome) => {
    const e = await nativeFixture();
    window.MastermindMissionHost = e.host;
    render(<App />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Programs" }));
    await waitFor(() => expect(document.body.textContent).toContain("Previous scope program"));
    e.hold();
    let oldOutcome = "PENDING";
    const oldRead = e.host.readPrograms!({ signal: new AbortController().signal }).then(
      () => { oldOutcome = "RESOLVED"; },
      (error: Error) => { oldOutcome = error.message; },
    );
    try {
      await waitFor(() => expect(e.pendingPrograms).toHaveLength(1));
      const before = e.host.invalidationGeneration!();
      await act(async () => { e.notify({ payload: { ...signed } }); await flush(); });
      expect(e.host.invalidationGeneration!()).toBeGreaterThan(before);
      expect(oldOutcome).toBe("READ_CANCELLED");
      expect(document.body.textContent).not.toContain("Previous scope program");
      expect(e.pendingPrograms).toHaveLength(2);
      await act(async () => {
        if (lateOutcome === "resolve") e.pendingPrograms[0]!.resolve(programs("Late old private program"));
        else e.pendingPrograms[0]!.reject(new Error("LATE_OLD_READ_FAILURE"));
        await flush();
      });
      expect(document.body.textContent).not.toContain("Late old private program");
      expect(document.body.textContent).not.toContain("Previous scope program");
      expect(oldOutcome).toBe("READ_CANCELLED");
      await act(async () => {
        e.pendingPrograms[1]!.resolve(programs("Fresh replacement program"));
        await flush();
      });
      await waitFor(() => expect(document.body.textContent).toContain("Fresh replacement program"));
      expect(document.body.textContent).not.toContain("Late old private program");
      await oldRead;
    } finally { await act(async () => { e.settle(); await flush(); }); }
  });
  it("deduplicates an unchanged legacy client notification without inventing a generation", () => {
    let notify!: (state: AuthState) => void;
    const client: RawClient = {
      getState: () => signed, subscribe: (listener) => { notify = listener; return () => {}; },
      signIn: async () => {}, signOut: async () => {},
      readPrograms: async () => programs(), readWork: async () => structuredClone(workFixture),
      readMission: async () => ({}), readCurrentWindow: async () => ({}),
    };
    const host = bindMissionHost(client);
    const before = host.invalidationGeneration!();
    notify({ ...signed });
    expect(host.invalidationGeneration!()).toBe(before);
    notify({ ...signed, content: false });
    expect(host.invalidationGeneration!()).toBeGreaterThan(before);
  });
});
