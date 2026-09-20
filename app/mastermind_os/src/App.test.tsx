// @vitest-environment jsdom
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { controlRoomFixture, missionFixture } from "./test-fixtures";

const invoke = vi.fn().mockResolvedValue({
  version: "0.1.0",
  source_revision: "a".repeat(40),
  build_identity: "test-build",
  transport: "UNCONFIGURED",
  state: "BUILT_NOT_PROVEN",
});
vi.mock("@tauri-apps/api/core", () => ({
  invoke: (...args: unknown[]) => invoke(...args),
}));
const deferred = <T,>() => {
  let resolve!: (value: T) => void, reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
};

beforeEach(() => {
  history.replaceState(null, "", "/?work_ref=WS%3AALPHA&root_job_id=JOB-A");
  delete (window as any).__TAURI_INTERNALS__;
  delete window.MastermindMissionHost;
  invoke.mockClear();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  delete window.MastermindMissionHost;
  delete (window as any).__TAURI_INTERNALS__;
});

describe("React read lifecycle fences", () => {
  it("hides displayed A synchronously while B is pending and after B rejects", async () => {
    const b = deferred<unknown>(),
      read = vi.fn(({ workRef }: { workRef: string }) =>
        workRef === "WS:ALPHA"
          ? Promise.resolve(missionFixture("WS:ALPHA", "JOB-A"))
          : b.promise,
      );
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
      controlRoom: controlRoomFixture(),
      readMission: read,
    };
    const user = userEvent.setup();
    render(<App />);
    await user.click(
      await screen.findByRole("button", { name: "Mission Workspace" }),
    );
    expect(await screen.findByText("JOB-A")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Programs" }));
    await user.click(screen.getByRole("button", { name: /Beta program/ }));
    expect(screen.queryByText("JOB-A")).toBeNull();
    expect(screen.getByText(/SOURCE_READ_PENDING/)).toBeTruthy();
    await act(async () => b.reject(new Error("disconnected")));
    expect(await screen.findByText(/SOURCE_UNAVAILABLE/)).toBeTruthy();
    expect(screen.queryByText("JOB-A")).toBeNull();
    expect(document.body.textContent).not.toContain("disconnected");
  });
  it("keeps B when an abort-ignoring A read resolves late", async () => {
    const a = deferred<unknown>(),
      b = deferred<unknown>(),
      signals = new Map<string, AbortSignal>(),
      read = vi.fn(
        ({ workRef, signal }: { workRef: string; signal: AbortSignal }) => {
          signals.set(workRef, signal);
          return workRef === "WS:ALPHA" ? a.promise : b.promise;
        },
      );
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
      controlRoom: controlRoomFixture(),
      readMission: read,
    };
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Open Programs" }));
    await user.click(screen.getByRole("button", { name: /Beta program/ }));
    expect(signals.get("WS:ALPHA")?.aborted).toBe(true);
    await act(async () => b.resolve(missionFixture("WS:BETA", "JOB-B")));
    expect(
      (await screen.findAllByRole("heading", { name: "Beta program" })).length,
    ).toBe(1);
    await act(async () => a.resolve(missionFixture("WS:ALPHA", "JOB-A")));
    await waitFor(() =>
      expect(
        screen.queryAllByRole("heading", { name: "Alpha program" }),
      ).toHaveLength(0),
    );
    expect(read).toHaveBeenCalledTimes(2);
  });
  it("renders a typed unavailable state after rejection", async () => {
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
      readMission: () => Promise.reject(new Error("private detail")),
    };
    render(<App />);
    await userEvent.click(
      screen.getByRole("button", { name: "Mission Workspace" }),
    );
    expect(await screen.findByText(/SOURCE_UNAVAILABLE/)).toBeTruthy();
    expect(document.body.textContent).not.toContain("private detail");
  });
  it("does not update after component detachment", async () => {
    const pending = deferred<unknown>();
    let readSignal: AbortSignal | undefined;
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
      readMission: ({ signal }) => {
        readSignal = signal;
        return pending.promise;
      },
    };
    const view = render(<App />);
    view.unmount();
    expect(readSignal?.aborted).toBe(true);
    await act(async () => pending.resolve(missionFixture("WS:ALPHA", "JOB-A")));
    expect(document.body.textContent).toBe("");
  });
});

describe("native and interaction contracts", () => {
  it("native mode invokes readiness only and never fetches", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockRejectedValue(new Error("must not run"));
    (window as any).__TAURI_INTERNALS__ = {};
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
    };
    render(<App />);
    await waitFor(() => expect(invoke).toHaveBeenCalledWith("readiness"));
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(
      screen.getByRole("heading", { name: "Today", level: 1 }),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Workspace connection unavailable. Current work was not read.",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/UNCONFIGURED \/ BUILT_NOT_PROVEN/)).toBeTruthy();
    expect(screen.getByText("a".repeat(40))).toBeTruthy();
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "Mission Workspace" }));
    expect(
      screen.getByText(
        "The workspace is not connected. Mission content will appear when an approved source is available.",
      ),
    ).toBeTruthy();
    expect(screen.queryByText(/cannot pass as a producer document/)).toBeNull();
    expect(screen.getByText("Technical details")).toBeTruthy();
  });
  it("distinguishes an absent Programs source from a malformed source", async () => {
    render(<App />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Open Programs" }));
    expect(
      screen.getByRole("heading", { name: "Programs", level: 1 }),
    ).toBeTruthy();
    expect(screen.getByText(/approved source is available/)).toBeTruthy();
    cleanup();

    window.MastermindMissionHost = { controlRoom: { invalid: true } };
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Open Programs" }));
    expect(
      screen.getByText(/did not match the required contract/),
    ).toBeTruthy();
  });
  it("graph and list share identities and restore keyboard focus", async () => {
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-ROOT" },
      readMission: async () => missionFixture(),
    };
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() =>
      expect(screen.getByText(/Source and observation clocks/)).toBeTruthy(),
    );
    await user.click(screen.getByRole("button", { name: "Connections" }));
    const graphRelation = screen.getByRole("button", {
      name: /JOB-ROOTcontainsJOB-ROOT-CHILD/,
    });
    await user.click(graphRelation);
    expect(document.activeElement).toBe(graphRelation);
    await user.click(screen.getByRole("button", { name: "List" }));
    const listRelation = screen.getByRole("button", {
      name: /JOB-ROOTcontainsJOB-ROOT-CHILD/,
    });
    expect(document.activeElement).toBe(listRelation);
    expect(
      screen.getByText("Selected relationship: JOB-ROOT->JOB-ROOT-CHILD"),
    ).toBeTruthy();
  });
  it("renders hostile text inert and displays actual artifacts", async () => {
    const fixture: any = missionFixture();
    fixture.execution.artifacts = ["<img src=x onerror=alert(1)>"];
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-ROOT" },
      readMission: async () => fixture,
    };
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() =>
      expect(screen.getByText(/Source and observation clocks/)).toBeTruthy(),
    );
    await user.click(screen.getByRole("button", { name: "Evidence" }));
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeTruthy();
    expect(document.querySelector("img")).toBeNull();
    expect(
      screen.getAllByText(/EXECUTIVE_OS · job:JOB-ROOT · status/).length,
    ).toBeGreaterThan(0);
  });
  it("labels partial missions without a current qualification claim", async () => {
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-ROOT" },
      readMission: async () => missionFixture(),
    };
    render(<App />);
    expect(
      await screen.findByText(/source qualification is not current/),
    ).toBeTruthy();
    expect(document.body.textContent).not.toContain(
      "exact source-qualified mission",
    );
  });
  it("renders unjoined counts and identities as separate bounded facts", async () => {
    const fixture: any = missionFixture();
    fixture.children.state = "PARTIAL";
    fixture.children.coverage = "INCOMPLETE";
    fixture.children.reason_codes = ["UNJOINED_JOBS_PRESENT"];
    fixture.children.total_count = null;
    fixture.children.overflow_count = null;
    fixture.children.unjoined_job_count = null;
    fixture.children.unjoined_job_ids = ["JOB-UNJOINED"];
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-ROOT" },
      readMission: async () => fixture,
    };
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Mission Workspace" }));
    await waitFor(() => expect(screen.getByText("Count unknown")).toBeTruthy());
    expect(screen.getByText("JOB-UNJOINED")).toBeTruthy();
    expect(screen.getByText(/Known-subset evidence/)).toBeTruthy();
  });
});
