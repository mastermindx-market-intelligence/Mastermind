// @vitest-environment jsdom
import {
  act,
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { navigateCompanyOperation } from "./test-operational-navigation";
import { bindMissionHost, type AuthState } from "./host";
import { createWebAuth } from "./web-auth";
import type {
  CommandIntent,
  EffectReceipt,
  FiniteCommandPort,
  OperationPointer,
  OwnerContext,
  PendingPointerStore,
} from "./orchestration/operation-controller";
import type { OrchestratorCommandBinding } from "./orchestration/host-command-bindings";
import { COMMAND_ROUTE_UNAVAILABLE } from "./orchestration/host-command-bindings";
import {
  bothUnavailableMissionFixture,
  controlRoomFixture,
  missionFixture,
} from "./test-fixtures";
import v3Current17 from "./fixtures/mission-v3-design-current-17-slots.json";
import v3Partial from "./fixtures/mission-v3-design-partial-truncated.json";
import v3Unavailable from "./fixtures/mission-v3-design-unavailable.json";
import resultAvailable from "./fixtures/result-design-available-at-16384-socket-bytes.json";
import resultUnavailableSource from "./fixtures/result-design-unavailable-source_changed.json";
import resultContentOverBudget from "./fixtures/result-design-content-over-budget-preserves-reject.json";
import workAvailable from "./fixtures/work-service-available.json";
import workUnavailable from "./fixtures/work-service-unavailable.json";

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
const readPrograms = async () => controlRoomFixture();
const programsFor = (workRef: string, rootJobId: string) => async () => {
  const document: any = controlRoomFixture(),
    work = document.work[0],
    responsibility = document.autonomy.responsibilities[0];
  work.work_ref = workRef;
  work.agent_os.workstream = workRef.slice(3);
  responsibility.responsibility_ref = workRef;
  responsibility.root_job_id = rootJobId;
  responsibility.root_job_candidates = [rootJobId];
  responsibility.root_job_ambiguous = false;
  responsibility.runtime_root_state = "RESOLVED";
  return document;
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
    const b = deferred<unknown>(), collectionB = deferred<unknown>(),
      read = vi.fn(({ workRef }: { workRef: string }) =>
        workRef === "WS:ALPHA"
          ? Promise.resolve(missionFixture("WS:ALPHA", "JOB-A"))
          : b.promise,
      );
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
      readPrograms: vi.fn().mockImplementationOnce(readPrograms).mockImplementation(() => collectionB.promise),
      readMission: read,
    };
    const user = userEvent.setup();
    render(<App />);
    await user.click(
      await screen.findByRole("button", { name: "Mission Workspace" }),
    );
    expect(await screen.findByText("JOB-A")).toBeTruthy();
    await navigateCompanyOperation(user, "Programs");
    await user.click(
      await screen.findByRole("button", { name: /Beta program/ }),
    );
    expect(screen.queryByText("JOB-A")).toBeNull();
    expect(screen.getByText(/PROGRAM_SELECTION_PENDING/)).toBeTruthy();
    expect(read).toHaveBeenCalledTimes(1);
    await act(async () => collectionB.resolve(await readPrograms()));
    expect(await screen.findByText(/SOURCE_READ_PENDING/)).toBeTruthy();
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
      readPrograms,
      readMission: read,
    };
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Open Programs" }));
    await user.click(
      await screen.findByRole("button", { name: /Beta program/ }),
    );
    expect(signals.get("WS:ALPHA")?.aborted).toBe(true);
    await act(async () => b.resolve(missionFixture("WS:BETA", "JOB-B")));
    expect(
      await screen.findByText("Exact project context · JOB-B"),
    ).toBeTruthy();
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
      readPrograms,
      readMission: () => Promise.reject(new Error("private detail")),
    };
    render(<App />);
    await userEvent.click(
      screen.getByRole("button", { name: "Mission Workspace" }),
    );
    expect(await screen.findByText(/SOURCE_UNAVAILABLE/)).toBeTruthy();
    expect(document.body.textContent).not.toContain("private detail");
  });
  it("keeps Conversation truthfully unavailable after Mission failure", async () => {
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
      readPrograms,
      readMission: () => Promise.reject(new Error("private detail")),
    };
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Mission Workspace" }));
    await screen.findByText(/SOURCE_UNAVAILABLE/);
    await user.click(screen.getByRole("button", { name: "Conversation" }));
    expect(
      screen.getByRole("heading", { name: "Conversation", level: 2 }),
    ).toBeTruthy();
    expect(
      screen.getByText("This app has no connected conversation source yet."),
    ).toBeTruthy();
    expect(
      screen.getByText("CONVERSATION_TRANSPORT_UNAVAILABLE").closest("details"),
    ).toBeTruthy();
    expect(document.body.textContent).not.toContain("private detail");
  });
  it("normalizes a synchronous Programs host failure", async () => {
    window.MastermindMissionHost = {
      readPrograms: () => {
        throw new Error("private detail");
      },
    };
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Open Programs" }));
    expect(await screen.findByText("SOURCE_UNAVAILABLE")).toBeTruthy();
    expect(document.body.textContent).not.toContain("private detail");
  });
  it("refuses an explicit partial URL instead of taking a host default", async () => {
    history.replaceState(null, "", "/?work_ref=WS%3AALPHA");
    const readMission = vi.fn();
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
      readPrograms,
      readMission,
    };
    render(<App />);
    await userEvent.click(
      screen.getByRole("button", { name: "Mission Workspace" }),
    );
    expect(await screen.findByText("EXACT_SELECTION_REQUIRED")).toBeTruthy();
    expect(readMission).not.toHaveBeenCalled();
  });
  it("normalizes a synchronous Mission host failure", async () => {
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
      readPrograms,
      readMission: () => {
        throw new Error("private detail");
      },
    };
    render(<App />);
    await userEvent.click(
      screen.getByRole("button", { name: "Mission Workspace" }),
    );
    expect(await screen.findByText("SOURCE_UNAVAILABLE")).toBeTruthy();
    expect(document.body.textContent).not.toContain("private detail");
  });
  it("distinguishes a valid empty Programs result from a failed read", async () => {
    const pending = deferred<unknown>();
    window.MastermindMissionHost = { readPrograms: () => pending.promise };
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Open Programs" }));
    expect(
      screen.getByText(/Reading the bounded Control Room projection/),
    ).toBeTruthy();
    const empty: any = controlRoomFixture();
    empty.work = [];
    empty.autonomy.responsibilities = [];
    await act(async () => pending.resolve(empty));
    expect(
      await screen.findByText(
        "No Programs were projected. This is not evidence of zero work.",
      ),
    ).toBeTruthy();
    expect(screen.queryByText("SOURCE_UNAVAILABLE")).toBeNull();
    cleanup();

    const failed = deferred<unknown>();
    window.MastermindMissionHost = { readPrograms: () => failed.promise };
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Open Programs" }));
    await act(async () => failed.reject(new Error("private detail")));
    expect(await screen.findByText("SOURCE_UNAVAILABLE")).toBeTruthy();
    expect(
      screen.queryByText(
        "No Programs were projected. This is not evidence of zero work.",
      ),
    ).toBeNull();
    expect(document.body.textContent).not.toContain("private detail");
  });
  it("refuses an ambiguous Programs root before reading Mission", async () => {
    const controlRoom: any = controlRoomFixture();
    controlRoom.autonomy.responsibilities.push(
      structuredClone(controlRoom.autonomy.responsibilities[0]),
    );
    const readMission = vi.fn();
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
      readPrograms: async () => controlRoom,
      readMission,
    };
    render(<App />);
    await userEvent.click(
      screen.getByRole("button", { name: "Mission Workspace" }),
    );
    expect(await screen.findByText("EXACT_SELECTION_UNRESOLVED")).toBeTruthy();
    expect(readMission).not.toHaveBeenCalled();
  });
  it("restores each exact Program/root pair through history and reload", async () => {
    const readMission = vi.fn(
      async ({ workRef, rootJobId }: { workRef: string; rootJobId: string }) =>
        missionFixture(workRef, rootJobId),
    );
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
      readPrograms,
      readMission,
    };
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Mission Workspace" }));
    expect(await screen.findByText("JOB-A")).toBeTruthy();
    await navigateCompanyOperation(user, "Programs");
    await user.click(
      await screen.findByRole("button", { name: /Beta program/ }),
    );
    expect(window.location.search).toBe(
      "?work_ref=WS%3ABETA&root_job_id=JOB-B",
    );
    expect(
      await screen.findByText("Exact project context · JOB-B"),
    ).toBeTruthy();

    window.history.back();
    await waitFor(() =>
      expect(window.location.search).toBe(
        "?work_ref=WS%3AALPHA&root_job_id=JOB-A",
      ),
    );
    expect(
      await screen.findByText("Exact project context · JOB-A"),
    ).toBeTruthy();
    window.history.forward();
    await waitFor(() =>
      expect(window.location.search).toBe(
        "?work_ref=WS%3ABETA&root_job_id=JOB-B",
      ),
    );
    expect(
      await screen.findByText("Exact project context · JOB-B"),
    ).toBeTruthy();

    cleanup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Mission Workspace" }));
    expect(await screen.findByText("JOB-B")).toBeTruthy();
  });
  it("persists a host-default pair before Program history and restores it", async () => {
    history.replaceState(null, "", "/");
    const readMission = vi.fn(
      async ({ workRef, rootJobId }: { workRef: string; rootJobId: string }) =>
        missionFixture(workRef, rootJobId),
    );
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
      readPrograms,
      readMission,
    };
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() =>
      expect(window.location.search).toBe(
        "?work_ref=WS%3AALPHA&root_job_id=JOB-A",
      ),
    );
    await navigateCompanyOperation(user, "Programs");
    await user.click(
      await screen.findByRole("button", { name: /Beta program/ }),
    );
    expect(window.location.search).toBe(
      "?work_ref=WS%3ABETA&root_job_id=JOB-B",
    );

    window.history.back();
    await waitFor(() =>
      expect(window.location.search).toBe(
        "?work_ref=WS%3AALPHA&root_job_id=JOB-A",
      ),
    );
    expect(await screen.findByText("Exact project context · JOB-A")).toBeTruthy();

    cleanup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Mission Workspace" }));
    expect(await screen.findByText("JOB-A")).toBeTruthy();
    expect(readMission).toHaveBeenCalled();
  });
  it("does not update after component detachment", async () => {
    const pending = deferred<unknown>();
    let readSignal: AbortSignal | undefined;
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
      readPrograms,
      readMission: ({ signal }) => {
        readSignal = signal;
        return pending.promise;
      },
    };
    const view = render(<App />);
    await waitFor(() => expect(readSignal).toBeDefined());
    view.unmount();
    expect(readSignal?.aborted).toBe(true);
    await act(async () => pending.resolve(missionFixture("WS:ALPHA", "JOB-A")));
    expect(document.body.textContent).toBe("");
  });
});

describe("Executive OS convergence surfaces", () => {
  it("renders source-qualified Work without turning unknown ownership into zero", async () => {
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
      readPrograms,
      readWork: async () => workAvailable as never,
      readMission: async () => missionFixture("WS:ALPHA", "JOB-A"),
    };
    const user = userEvent.setup();
    render(<App />);

    await navigateCompanyOperation(user, "Work");
    expect(await screen.findByText("JOB-2")).toBeTruthy();
    expect(screen.getByText("CHECKPOINTED")).toBeTruthy();
    expect(screen.getByText("JOB-1")).toBeTruthy();
    expect(screen.getAllByText("UNKNOWN").length).toBeGreaterThan(0);
    expect(screen.getByText(/4 of 4 roots observed/i)).toBeTruthy();
    expect(screen.queryByText("WORK_QUEUE_SOURCE_NOT_CONNECTED")).toBeNull();
    expect(screen.queryByRole("button", { name: /Open Mission/i })).toBeNull();
  });

  it("renders typed Work unavailability as unavailable, not an empty all-clear", async () => {
    window.MastermindMissionHost = {
      readPrograms,
      readWork: async () => workUnavailable as never,
    };
    const user = userEvent.setup();
    render(<App />);

    await navigateCompanyOperation(user, "Work");
    expect(await screen.findByText("projection_refused")).toBeTruthy();
    expect(screen.getAllByText("UNAVAILABLE").length).toBeGreaterThan(0);
    expect(screen.getByText(/not evidence of zero work/i)).toBeTruthy();
  });

  it("keeps Fleet unavailable without its canonical feed", async () => {
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
      readPrograms,
      readMission: async () => missionFixture("WS:ALPHA", "JOB-A"),
    };
    const user = userEvent.setup();
    render(<App />);

    await navigateCompanyOperation(user, "Fleet & Capacity");
    expect(
      screen.getByRole("heading", { name: "Fleet & Capacity", level: 1 }),
    ).toBeTruthy();
    expect(screen.getByText("CAPACITY_SOURCE_NOT_CONNECTED")).toBeTruthy();
    expect(screen.queryByText("Missingness and source state")).toBeNull();
  });

  it("renders Activity from the admitted Mission without another source read", async () => {
    const readMission = vi.fn(async () => missionFixture("WS:ALPHA", "JOB-A"));
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
      readPrograms,
      readMission,
    };
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Mission Workspace" }));
    expect(await screen.findByText("JOB-A")).toBeTruthy();
    const readsBeforeActivity = readMission.mock.calls.length;

    await user.click(screen.getByRole("button", { name: "Activity" }));
    expect(
      screen.getByRole("heading", { name: "Activity", level: 1 }),
    ).toBeTruthy();
    expect(
      screen.getByRole("heading", { name: "Live work", level: 2 }),
    ).toBeTruthy();
    expect(screen.getByText("JOB-A-CHILD")).toBeTruthy();
    expect(readMission).toHaveBeenCalledTimes(readsBeforeActivity);
  });

  it("does not turn the absent Chairman-decision feed into an all-clear", () => {
    render(<App />);
    const attention = screen
      .getByRole("heading", {
        name: "Chairman attention is not established.",
        level: 2,
      })
      .closest("section");
    expect(attention).toBeTruthy();
    expect(
      within(attention!).getByText(
        "Missing attention data does not mean there are no decisions.",
        { exact: false },
      ),
    ).toBeTruthy();
    expect(within(attention!).queryByText("The owner has requested Chairman attention.")).toBeNull();
  });
});

describe("native and interaction contracts", () => {
  it("keeps exactly five Company destinations and contextual operational routes", async () => {
    render(<App />);
    const company = screen.getByRole("navigation", { name: "Company navigation" });
    expect(within(company).getAllByRole("button").map(button => button.textContent?.trim().replace(/^[^A-Za-z]+/, ""))).toEqual([
      "Today", "Projects", "Inbox", "Conversations", "Knowledge",
    ]);
    const operations = screen.getByRole("navigation", { name: "Company operations" });
    expect(within(operations).getByRole("button", { name: "Work" })).toBeTruthy();
    expect(within(operations).getByRole("button", { name: "Open Programs" })).toBeTruthy();
    await userEvent.setup().click(within(operations).getByRole("button", { name: "Fleet & Capacity" }));
    expect(screen.getByRole("heading", { name: "Fleet & Capacity", level: 1 })).toBeTruthy();
    expect(screen.queryByRole("navigation", { name: "Company operations" })).toBeNull();
  });
  it("skip to workspace retains Today and the original URL while focusing main", async () => {
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
      readPrograms,
      readMission: async () => missionFixture("WS:ALPHA", "JOB-A"),
    };
    const user = userEvent.setup();
    render(<App />);
    expect(screen.getByRole("heading", { name: "Today", level: 1 })).toBeTruthy();
    const originalUrl = location.href;
    await user.click(screen.getByRole("link", { name: "Skip to workspace" }));
    expect(document.activeElement).toBe(screen.getByRole("main"));
    expect(location.href).toBe(originalUrl);
    expect(screen.getByRole("heading", { name: "Today", level: 1 })).toBeTruthy();
  });
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
    expect(invoke).toHaveBeenCalledTimes(1);
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
    await act(async () => {
      history.replaceState(null, "", "/?work_ref=WS%3AALPHA&root_job_id=JOB-A");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(
      await screen.findByText("NATIVE_TRANSPORT_UNCONFIGURED"),
    ).toBeTruthy();
    expect(invoke).toHaveBeenCalledTimes(1);
  });
  it("renders configured native readiness only through an opaque client reference", async () => {
    const nativeClientRef = `native-client:v1:${"b".repeat(64)}`;
    invoke.mockResolvedValueOnce({
      version: "0.1.0",
      source_revision: "a".repeat(40),
      build_identity: "configured-test-build",
      transport: "CONFIGURED",
      state: "BUILT_NOT_PROVEN",
      native_client_ref: nativeClientRef,
    });
    (window as any).__TAURI_INTERNALS__ = {};
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
    };
    render(<App />);
    await waitFor(() => expect(invoke).toHaveBeenCalledWith("readiness"));
    expect(screen.getByText(/CONFIGURED \/ BUILT_NOT_PROVEN/)).toBeTruthy();
    expect(screen.getByText("Native client reference")).toBeTruthy();
    expect(screen.getByText(nativeClientRef)).toBeTruthy();
    expect(document.body.textContent).not.toContain("tpc_");
  });
  it("distinguishes an absent Programs source from a malformed source", async () => {
    render(<App />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Open Programs" }));
    expect(
      screen.getByRole("heading", { name: "Programs", level: 1 }),
    ).toBeTruthy();
    expect(
      await screen.findByText("QUALIFIED_PROGRAM_READ_UNAVAILABLE"),
    ).toBeTruthy();
    cleanup();

    window.MastermindMissionHost = {
      readPrograms: async () => ({ invalid: true }),
    };
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Open Programs" }));
    expect(await screen.findByText("SCHEMA_INVALID")).toBeTruthy();
  });
  it("graph and list share identities and restore keyboard focus", async () => {
    history.replaceState(
      null,
      "",
      "/?work_ref=WS%3AALPHA&root_job_id=JOB-ROOT",
    );
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-ROOT" },
      readPrograms: programsFor("WS:ALPHA", "JOB-ROOT"),
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
    history.replaceState(
      null,
      "",
      "/?work_ref=WS%3AALPHA&root_job_id=JOB-ROOT",
    );
    const fixture: any = missionFixture();
    fixture.execution.artifacts = ["<img src=x onerror=alert(1)>"];
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-ROOT" },
      readPrograms: programsFor("WS:ALPHA", "JOB-ROOT"),
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
  it("renders a null projection clock as unavailable", async () => {
    history.replaceState(null, "", "/?work_ref=WS%3AB5&root_job_id=JOB-B5");
    window.MastermindMissionHost = {
      selection: { workRef: "WS:B5", rootJobId: "JOB-B5" },
      readPrograms: programsFor("WS:B5", "JOB-B5"),
      readMission: async () => bothUnavailableMissionFixture(),
    };
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Evidence" }));
    const label = await screen.findByText("Projection created"),
      value = label.nextElementSibling;
    expect(value?.textContent).toBe("Unavailable");
    expect(value?.querySelector("time")).toBeNull();
  });
  it("labels partial missions without a current qualification claim", async () => {
    history.replaceState(
      null,
      "",
      "/?work_ref=WS%3AALPHA&root_job_id=JOB-ROOT",
    );
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-ROOT" },
      readPrograms: programsFor("WS:ALPHA", "JOB-ROOT"),
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
    history.replaceState(
      null,
      "",
      "/?work_ref=WS%3AALPHA&root_job_id=JOB-ROOT",
    );
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
      readPrograms: programsFor("WS:ALPHA", "JOB-ROOT"),
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

describe("installed authentication and permitted content", () => {
  it("calls sign-in directly from the header gesture and names missing public configuration", async () => {
    const signIn = vi.fn(async () => {});
    window.MastermindMissionHost = {
      auth: {
        getState: () => ({
          status: "signed_out",
          reason: null,
          acquisition: false,
          content: false,
        }),
        subscribe: () => () => {},
        signIn,
        signOut: async () => {},
      },
    };
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(signIn).toHaveBeenCalledTimes(1);
    cleanup();
    window.MastermindMissionHost.auth!.getState = () => ({
      status: "unconfigured",
      reason: "CLIENT_NOT_REGISTERED",
      acquisition: false,
      content: false,
    });
    render(<App />);
    expect(screen.getByText("Sign-in setup pending")).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: "Sign in" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });
  it("renders the global current window only as unbound from the selected Mission", async () => {
    const h = "b".repeat(64);
    window.MastermindMissionHost = {
      readPrograms,
      readMission: async () => missionFixture("WS:ALPHA", "JOB-A"),
      readCurrentWindow: async () => ({
        schema: "mastermind.workspace.window_read_candidate.v1" as const,
        selection_ref: "managed-window:unbound-fixture",
        mode: "observed-turn-window" as const,
        view: {
          schema: "mastermind.workspace.visible_window_candidate.v1" as const,
          source_ref: "managed-window:unbound-fixture",
          scope: "one-managed-turn-window" as const,
          observed_at: "2026-09-21T08:00:00Z",
          epoch: h,
          terminal: false,
          coverage: "OBSERVED_WINDOW" as const,
          history: "NOT_PROVEN" as const,
          acceptance: "NOT_PROJECTED" as const,
          capabilities: {
            send: false as const,
            provider_control: false as const,
            history: false as const,
          },
          items: [
            {
              id: `visible:${h}`,
              source_sequence: 0,
              publication_sequence: 1,
              state: "completed" as const,
              kind: "visible-response" as const,
              text: "Unbound permitted response",
              representation: "VISIBLE_TEXT" as const,
              display_sha256: h,
            },
          ],
          gaps: [],
        },
      }),
      auth: {
        getState: () => ({
          status: "signed_in",
          reason: null,
          acquisition: true,
          content: true,
        }),
        subscribe: () => () => {},
        signIn: async () => {},
        signOut: async () => {},
      },
    };
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Mission Workspace" }));
    await screen.findByText("JOB-A");
    await user.click(screen.getByRole("button", { name: "Conversation" }));

    expect(
      await screen.findByRole("heading", {
        name: "Unbound current window",
        level: 2,
      }),
    ).toBeTruthy();
    expect(screen.getByText("NOT_LINKED_TO_SELECTED_MISSION")).toBeTruthy();
    expect(
      screen.getByText(
        "No relationship is proven between this current window and WS:ALPHA / JOB-A.",
      ),
    ).toBeTruthy();
    expect(screen.getByText("Unbound permitted response")).toBeTruthy();
    const banner = within(screen.getByRole("banner"));
    expect(banner.queryByText("CURRENT")).toBeNull();
    expect(banner.queryByText("PARTIAL")).toBeNull();
    expect(banner.queryByText(/This mission projection is/)).toBeNull();
    expect(screen.getByRole("status").textContent).toContain(
      "not linked to the selected Mission",
    );
    expect(
      screen.queryByRole("heading", { name: "Missingness and source state" }),
    ).toBeNull();
  });

  it("consumes the fixed content callback and clears visible text on sign-out", async () => {
    let listener!: (state: import("./host").AuthState) => void;
    const h = "a".repeat(64),
      readCurrentWindow = vi.fn(async () => ({
        schema: "mastermind.workspace.window_read_candidate.v1" as const,
        selection_ref: "managed-window:fixture",
        mode: "observed-turn-window" as const,
        view: {
          schema: "mastermind.workspace.visible_window_candidate.v1" as const,
          source_ref: "managed-window:fixture",
          scope: "one-managed-turn-window" as const,
          observed_at: "2026-09-21T07:00:00Z",
          epoch: h,
          terminal: false,
          coverage: "OBSERVED_WINDOW" as const,
          history: "NOT_PROVEN" as const,
          acceptance: "NOT_PROJECTED" as const,
          capabilities: {
            send: false as const,
            provider_control: false as const,
            history: false as const,
          },
          items: [
            {
              id: `visible:${h}`,
              source_sequence: 0,
              publication_sequence: 1,
              state: "completed" as const,
              kind: "visible-response" as const,
              text: "Permitted fixture response",
              representation: "VISIBLE_TEXT" as const,
              display_sha256: h,
            },
          ],
          gaps: [],
        },
      }));
    window.MastermindMissionHost = {
      readPrograms,
      readMission: async () => missionFixture("WS:ALPHA", "JOB-A"),
      readCurrentWindow,
      auth: {
        getState: () => ({
          status: "signed_in",
          reason: null,
          acquisition: true,
          content: true,
        }),
        subscribe(fn) {
          listener = fn;
          return () => {};
        },
        signIn: async () => {},
        signOut: async () => {
          listener({
            status: "signed_out",
            reason: null,
            acquisition: false,
            content: false,
          });
        },
      },
    };
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Conversation" }));
    expect(await screen.findByText("Permitted fixture response")).toBeTruthy();
    expect(readCurrentWindow).toHaveBeenCalledWith({
      signal: expect.any(AbortSignal),
    });
    await user.click(screen.getByRole("button", { name: "Sign out" }));
    expect(screen.queryByText("Permitted fixture response")).toBeNull();
  });

  it("associates a v2 window with a qualifying current plan child and stays unbound for v1", async () => {
    const att = "ATT-" + "ab".repeat(16);
    const h = "c".repeat(64);
    const mission: any = structuredClone(v3Current17);
    mission.children = {
      ...mission.children,
      state: "AVAILABLE",
      coverage: "COMPLETE",
      items: [
        {
          job_id: "JOB-101",
          status: "RUNNING",
          parent_job_id: "JOB-100",
          depth: 1,
          orchestration_role: "plan",
          plan_step_id: null,
          attempt_count: 1,
          attempt_limit: 2,
          current_attempt_id: att,
          latest_attempt: {
            attempt_id: att,
            attempt_number: 1,
            status: "RUNNING",
            started_at: "2026-09-20T00:00:00Z",
            finished_at: null,
            exit_code: null,
            has_result: false,
            error_present: false,
            error_class: null,
          },
          worker_id: null,
        },
      ],
      total_count: 1,
      overflow_count: 0,
      unjoined_job_count: 0,
      unjoined_job_ids: [],
    };
    history.replaceState(null, "", "/?work_ref=WS%3AB5&root_job_id=JOB-100");
    window.MastermindMissionHost = {
      readPrograms: programsFor("WS:B5", "JOB-100"),
      readMission: async () => missionFixture("WS:B5", "JOB-100"),
      readMissionV3: async () => mission,
      readCurrentWindow: async () => ({
        schema: "mastermind.workspace.window_read_candidate.v2" as const,
        selection_ref: "managed-window:observed",
        mode: "observed-turn-window" as const,
        observation_binding: { job_id: "JOB-101", attempt_id: att },
        view: {
          schema: "mastermind.workspace.visible_window_candidate.v1" as const,
          source_ref: "managed-window:observed",
          scope: "one-managed-turn-window" as const,
          observed_at: "2026-09-21T08:00:00Z",
          epoch: h,
          terminal: false,
          coverage: "OBSERVED_WINDOW" as const,
          history: "NOT_PROVEN" as const,
          acceptance: "NOT_PROJECTED" as const,
          capabilities: {
            send: false as const,
            provider_control: false as const,
            history: false as const,
          },
          items: [
            {
              id: `visible:${h}`,
              source_sequence: 0,
              publication_sequence: 1,
              state: "completed" as const,
              kind: "visible-response" as const,
              text: "Observed permitted response",
              representation: "VISIBLE_TEXT" as const,
              display_sha256: h,
            },
          ],
          gaps: [],
        },
      }),
      auth: {
        getState: () => ({
          status: "signed_in",
          reason: null,
          acquisition: true,
          content: true,
        }),
        subscribe: () => () => {},
        signIn: async () => {},
        signOut: async () => {},
      },
    };
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Conversation" }));
    expect(
      await screen.findByRole("heading", {
        name: "Observed window for this Mission",
        level: 2,
      }),
    ).toBeTruthy();
    expect(screen.getByText(/JOB-101/)).toBeTruthy();
    expect(screen.getByText(new RegExp(att))).toBeTruthy();
    expect(screen.getByText(/Window observed at/)).toBeTruthy();
    expect(screen.getByText(/Mission document generated at/)).toBeTruthy();
    expect(screen.queryByText("NOT_LINKED_TO_SELECTED_MISSION")).toBeNull();
    expect(screen.getByText("Observed permitted response")).toBeTruthy();
    expect(screen.queryByText(/same principal/i)).toBeNull();
    expect(screen.queryByText(/atomic/i)).toBeNull();
  });

  it("does not combine a mission from before logout with a later window", async () => {
    const att = "ATT-" + "ab".repeat(16);
    const h = "d".repeat(64);
    const missionHold = deferred<unknown>();
    const windowHold = deferred<unknown>();
    let listener!: (state: AuthState) => void;
    history.replaceState(null, "", "/?work_ref=WS%3AB5&root_job_id=JOB-100");
    window.MastermindMissionHost = {
      readPrograms: programsFor("WS:B5", "JOB-100"),
      readMission: async () => missionFixture("WS:B5", "JOB-100"),
      readMissionV3: () => missionHold.promise,
      readCurrentWindow: () => windowHold.promise as Promise<any>,
      auth: {
        getState: () => ({
          status: "signed_in",
          reason: null,
          acquisition: true,
          content: true,
        }),
        subscribe(fn) {
          listener = fn;
          return () => {};
        },
        signIn: async () => {},
        signOut: async () => {},
      },
    };
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Conversation" }));
    listener({
      status: "signed_out",
      reason: null,
      acquisition: false,
      content: false,
    });
    await act(async () => {
      missionHold.resolve(structuredClone(v3Current17));
      windowHold.resolve({
        schema: "mastermind.workspace.window_read_candidate.v2",
        selection_ref: "managed-window:late",
        mode: "observed-turn-window",
        observation_binding: { job_id: "JOB-101", attempt_id: att },
        view: {
          schema: "mastermind.workspace.visible_window_candidate.v1",
          source_ref: "managed-window:late",
          scope: "one-managed-turn-window",
          observed_at: "2026-09-21T08:00:00Z",
          epoch: h,
          terminal: false,
          coverage: "OBSERVED_WINDOW",
          history: "NOT_PROVEN",
          acceptance: "NOT_PROJECTED",
          capabilities: {
            send: false,
            provider_control: false,
            history: false,
          },
          items: [
            {
              id: `visible:${h}`,
              source_sequence: 0,
              publication_sequence: 1,
              state: "completed",
              kind: "visible-response",
              text: "Late window after logout",
              representation: "VISIBLE_TEXT",
              display_sha256: h,
            },
          ],
          gaps: [],
        },
      });
    });
    expect(screen.queryByText("Late window after logout")).toBeNull();
    expect(
      screen.queryByRole("heading", {
        name: "Observed window for this Mission",
      }),
    ).toBeNull();
  });

  it("offers explicit refresh from unavailable without autopoll", async () => {
    const readCurrentWindow = vi.fn(async () => {
      throw new Error("WINDOW_UNAVAILABLE");
    });
    const readMissionV3 = vi.fn(async () => structuredClone(v3Current17));
    window.MastermindMissionHost = {
      readPrograms,
      readMission: async () => missionFixture("WS:ALPHA", "JOB-A"),
      readMissionV3,
      readCurrentWindow,
      auth: {
        getState: () => ({
          status: "signed_in",
          reason: null,
          acquisition: true,
          content: true,
        }),
        subscribe: () => () => {},
        signIn: async () => {},
        signOut: async () => {},
      },
    };
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Conversation" }));
    const refresh = await screen.findByRole("button", { name: /Refresh/ });
    expect((refresh as HTMLButtonElement).disabled).toBe(false);
    const missionCalls = readMissionV3.mock.calls.length;
    const windowCalls = readCurrentWindow.mock.calls.length;
    expect(windowCalls).toBeGreaterThan(0);
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 30));
    });
    expect(readMissionV3.mock.calls.length).toBe(missionCalls);
    expect(readCurrentWindow.mock.calls.length).toBe(windowCalls);
    await user.click(refresh);
    expect(readCurrentWindow.mock.calls.length).toBeGreaterThan(windowCalls);
  });

  it("does not associate a window read after selection changed during the mission await", async () => {
    const att = "ATT-" + "ab".repeat(16);
    const h = "e".repeat(64);
    const missionHold = deferred<unknown>();
    const windowHold = deferred<unknown>();
    history.replaceState(null, "", "/?work_ref=WS%3AB5&root_job_id=JOB-100");
    window.MastermindMissionHost = {
      readPrograms: programsFor("WS:B5", "JOB-100"),
      readMission: async ({ workRef, rootJobId }) =>
        missionFixture(workRef, rootJobId),
      readMissionV3: () => missionHold.promise,
      readCurrentWindow: () => windowHold.promise as Promise<any>,
      auth: {
        getState: () => ({
          status: "signed_in",
          reason: null,
          acquisition: true,
          content: true,
        }),
        subscribe: () => () => {},
        signIn: async () => {},
        signOut: async () => {},
      },
    };
    const user = userEvent.setup();
    render(<App />);
    await navigateCompanyOperation(user, "Programs");
    await user.click(screen.getByRole("button", { name: "Conversation" }));
    await navigateCompanyOperation(user, "Programs");
    const beta = await screen.findByRole("button", { name: /Beta program/ });
    await user.click(beta);
    await act(async () => {
      missionHold.resolve(structuredClone(v3Current17));
      windowHold.resolve({
        schema: "mastermind.workspace.window_read_candidate.v2",
        selection_ref: "managed-window:stale-pair",
        mode: "observed-turn-window",
        observation_binding: { job_id: "JOB-101", attempt_id: att },
        view: {
          schema: "mastermind.workspace.visible_window_candidate.v1",
          source_ref: "managed-window:stale-pair",
          scope: "one-managed-turn-window",
          observed_at: "2026-09-21T08:00:00Z",
          epoch: h,
          terminal: false,
          coverage: "OBSERVED_WINDOW",
          history: "NOT_PROVEN",
          acceptance: "NOT_PROJECTED",
          capabilities: {
            send: false,
            provider_control: false,
            history: false,
          },
          items: [
            {
              id: `visible:${h}`,
              source_sequence: 0,
              publication_sequence: 1,
              state: "completed",
              kind: "visible-response",
              text: "Stale pair window",
              representation: "VISIBLE_TEXT",
              display_sha256: h,
            },
          ],
          gaps: [],
        },
      });
    });
    expect(screen.queryByText("Stale pair window")).toBeNull();
    expect(
      screen.queryByRole("heading", {
        name: "Observed window for this Mission",
      }),
    ).toBeNull();
  });
});

describe("route focus handoff", () => {
  it("moves keyboard focus from a removed Open Programs action to the route heading", async () => {
    const user = userEvent.setup();
    render(<App />);
    expect(document.activeElement).toBe(document.body);
    screen.getByRole("button", { name: "Open Programs" }).focus();
    await user.keyboard("{Enter}");
    expect(document.activeElement).toBe(
      screen.getByRole("heading", { name: "Programs", level: 1 }),
    );
  });

  it("retains persistent navigation focus and exposes the current route", async () => {
    const user = userEvent.setup();
    render(<App />);
    const programs = screen.getByRole("button", { name: "Projects" });
    programs.focus();
    await user.keyboard("{Enter}");
    expect(document.activeElement).toBe(programs);
    expect(programs.getAttribute("aria-current")).toBe("page");
    await user.keyboard("{Enter}");
    expect(document.activeElement).toBe(programs);
  });

  it("hands program selection to the Projects heading without stealing focus when data resolves", async () => {
    const pending = deferred<unknown>();
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
      readPrograms,
      readMission: ({ workRef }) =>
        workRef === "WS:BETA"
          ? pending.promise
          : Promise.resolve(missionFixture("WS:ALPHA", "JOB-A")),
    };
    const user = userEvent.setup();
    render(<App />);
    screen.getByRole("button", { name: "Open Programs" }).focus();
    await user.keyboard("{Enter}");
    (await screen.findByRole("button", { name: /Beta program/ })).focus();
    await user.keyboard("{Enter}");
    expect(document.activeElement).toBe(
      screen.getByRole("heading", { name: "Projects", level: 1 }),
    );
    const connections = screen.getByRole("button", { name: "Connections" });
    connections.focus();
    await act(async () => pending.resolve(missionFixture("WS:BETA", "JOB-B")));
    expect(document.activeElement).toBe(connections);
  });

  it("does not focus a heading on initial render or a late Programs read", async () => {
    const pending = deferred<unknown>();
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
      readPrograms: () => pending.promise,
      readMission: async () => missionFixture("WS:ALPHA", "JOB-A"),
    };
    render(<App />);
    expect(document.activeElement).toBe(document.body);
    const action = screen.getByRole("button", { name: "Open Programs" });
    action.focus();
    await act(async () => pending.resolve(controlRoomFixture()));
    expect(document.activeElement).toBe(action);
  });
});

// Synthetic contract-only fixtures; actual producer joining is a separate gate.
function resultHost(result: unknown = resultAvailable) {
  const mission = structuredClone(v3Current17);
  const selected = resultAvailable.selection;
  mission.program.work_ref = selected.work_ref;
  // Keep every existing selection join consistent in this synthetic document.
  const renamed = JSON.parse(
    JSON.stringify(mission)
      .replaceAll("WS:B5", selected.work_ref)
      .replaceAll("JOB-100", selected.root_job_id),
  );
  renamed.result_refs.refs = [
    {
      root_job_id: selected.root_job_id,
      job_id: selected.job_id,
      attempt_id: selected.attempt_id,
      result_envelope_digest: selected.result_envelope_digest,
      orchestration_role: "review",
      validation: "UNVALIDATED",
    },
  ];
  renamed.result_refs.absent_job_ids = [];
  renamed.result_refs.omitted_job_ids = [];
  const signed: AuthState = {
    status: "signed_in",
    reason: null,
    acquisition: true,
    content: false,
  };
  let listener = (_state: AuthState) => {};
  const legacy = vi.fn(async () => {
    throw new Error("legacy route must not be read");
  });
  const detail = vi.fn(async () => result);
  window.MastermindMissionHost = {
    readPrograms: programsFor(selected.work_ref, selected.root_job_id),
    readMission: legacy,
    readMissionV3: vi.fn(async () => renamed),
    readResult: detail,
    auth: {
      getState: () => signed,
      subscribe: (fn) => {
        listener = fn;
        return () => {};
      },
      signIn: async () => {},
      signOut: async () => {},
    },
  };
  history.replaceState(null, "", "/?work_ref=WS%3ADESIGN&root_job_id=JOB-001");
  return {
    legacy,
    detail,
    mission: renamed,
    notify: (state: AuthState) => listener(state),
  };
}
async function openResult() {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Mission Workspace" }));
  const summary = await screen.findByText("1 result refs");
  await user.click(within(summary.closest("section")!).getByRole("button"));
  return user;
}
describe("result card and same-observation Mission lifecycle", () => {
  it("uses one live v3 acquisition without a v2 prerequisite or eager detail read", async () => {
    const h = resultHost();
    render(<App />);
    await waitFor(() =>
      expect(window.MastermindMissionHost!.readMissionV3).toHaveBeenCalledTimes(
        1,
      ),
    );
    expect(h.detail).not.toHaveBeenCalled();
    await openResult();
    expect(h.legacy).not.toHaveBeenCalled();
    expect(window.MastermindMissionHost!.readMissionV3).toHaveBeenCalledTimes(
      1,
    );
    expect(h.detail).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Result detail")).toBeTruthy();
  });
  it("does not fall back to legacy data after v3 refusal", async () => {
    const h = resultHost();
    window.MastermindMissionHost!.readMissionV3 = async () => {
      throw new Error("refused");
    };
    render(<App />);
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "Mission Workspace" }));
    expect(await screen.findByText("SOURCE_UNAVAILABLE")).toBeTruthy();
    expect(h.legacy).not.toHaveBeenCalled();
    expect(h.detail).not.toHaveBeenCalled();
  });
  it("renders permitted findings and exact envelope/review target identities as inert detail", async () => {
    resultHost();
    render(<App />);
    await openResult();
    const card = (await screen.findByText("Result detail")).closest("section")!;
    await waitFor(() =>
      expect(card.textContent).toContain("DESIGN_ONLY_FINDING"),
    );
    expect(card.textContent).toContain(
      resultAvailable.selection.result_envelope_digest,
    );
    expect(card.textContent).toContain(
      resultAvailable.result.review.reviewed_job_id,
    );
    expect(card.textContent).toContain(
      resultAvailable.result.review.reviewed_attempt_id,
    );
    expect(card.textContent).toContain(
      resultAvailable.result.review.reviewed_result_digest,
    );
    expect(card.textContent).toContain("evidence_digests");
    expect(card.querySelector("a")).toBeNull();
  });
  it("preserves a typed SOURCE_CHANGED response with no fabricated content", async () => {
    const value = structuredClone(resultUnavailableSource);
    value.selection = structuredClone(resultAvailable.selection);
    value.source_observation.selection = structuredClone(
      resultAvailable.selection,
    );
    resultHost(value);
    render(<App />);
    await openResult();
    expect(
      (await screen.findAllByText(/SOURCE_CHANGED/)).length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText("Structured role result")).toBeNull();
  });
  it("keeps oversize content unavailable while preserving reject and counts", async () => {
    const value = structuredClone(resultContentOverBudget);
    value.selection = structuredClone(resultAvailable.selection);
    value.source_observation.selection = structuredClone(
      resultAvailable.selection,
    );
    value.result.selection = {
      ...value.result.selection,
      result_envelope_digest: resultAvailable.selection.result_envelope_digest,
    };
    resultHost(value);
    render(<App />);
    await openResult();
    expect(await screen.findByText(/Content omitted by owner/)).toBeTruthy();
    expect(screen.getByText(/verdict: reject/)).toBeTruthy();
    expect(screen.queryByText("Structured role result")).toBeNull();
  });
  it("ignores an abort-ignoring detail reply after changing the selected Mission", async () => {
    const pending = deferred<unknown>();
    resultHost();
    window.MastermindMissionHost!.readResult = () => pending.promise;
    render(<App />);
    await openResult();
    await act(async () => {
      history.replaceState(null, "", "/?work_ref=WS%3AOTHER&root_job_id=JOB-2");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    await act(async () => pending.resolve(resultAvailable));
    expect(screen.queryByText("Structured role result")).toBeNull();
    expect(screen.queryByText("Result detail")).toBeNull();
  });
});

describe("result permission and detached-read fences", () => {
  it("does not restore detail from a late reply after logout", async () => {
    const pending = deferred<unknown>();
    const h = resultHost();
    window.MastermindMissionHost!.readResult = () => pending.promise;
    render(<App />);
    await openResult();
    act(() =>
      h.notify({
        status: "signed_out",
        reason: null,
        acquisition: false,
        content: false,
      }),
    );
    await act(async () => pending.resolve(resultAvailable));
    expect(screen.queryByText("Result detail")).toBeNull();
    expect(screen.queryByText("Structured role result")).toBeNull();
  });
  it("aborts pending detail when the component unmounts", async () => {
    const pending = deferred<unknown>();
    resultHost();
    let signal: AbortSignal | undefined;
    window.MastermindMissionHost!.readResult = (request) => {
      signal = request.signal;
      return pending.promise;
    };
    const page = render(<App />);
    await openResult();
    page.unmount();
    expect(signal?.aborted).toBe(true);
    await act(async () => pending.resolve(resultAvailable));
    expect(screen.queryByText("Result detail")).toBeNull();
  });
});

describe("actual unconfigured web owner lifecycle", () => {
  it("does not turn a token refusal notification into repeated Program reads", async () => {
    history.replaceState(null, "", "/os/");
    const client = createWebAuth({ config: { webClientId: undefined } });
    const actualRead = client.readPrograms;
    let calls = 0;
    client.readPrograms = async (args) => {
      // Bound the unchanged failure so an actual feedback loop cannot hang CI.
      if (++calls > 4) throw new Error("TEST_FEEDBACK_LOOP_BOUND");
      return actualRead(args);
    };
    window.MastermindMissionHost = bindMissionHost(client);
    render(<App />);
    await act(async () => {
      for (let i = 0; i < 16; i++) await Promise.resolve();
    });
    expect(calls).toBe(0);
    expect(
      screen.getByRole("button", { name: "Sign in" }).hasAttribute("disabled"),
    ).toBe(true);
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "Open Programs" }));
    expect(document.activeElement).toBe(
      screen.getByRole("heading", { name: "Programs", level: 1 }),
    );
    expect(calls).toBe(0);
  });
});

function memoryStore(): PendingPointerStore {
  const data = new Map<string, OperationPointer>();
  return {
    read: (scope) => data.get(scope) ?? null,
    reserve: (scope, pointer) => {
        const existing = data.get(scope);
        if (existing) return { reserved: false, pointer: existing };
        data.set(scope, pointer);
        return { reserved: true };
      },
    clearIfEqual: (scope, pointer) => {
      const current = data.get(scope);
      if (
        current &&
        current.operationKey === pointer.operationKey &&
        current.kind === pointer.kind &&
        current.targetKey === pointer.targetKey
      ) {
          data.delete(scope);
          return true;
        }
        return false;
    },
  };
}

const defaultSession = {
  sessionKey: "sess-1",
  title: "Session One",
  messages: [] as { id: string; role: "user" | "assistant" | "activity"; text: string }[],
  observedAt: null as string | null,
  connection: "connected" as const,
  coverage: "COMPLETE",
  turnBusy: false,
  stopLabel: "Request stop" as const,
  selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
};

function makeCommandBinding(overrides: {
  ctx?: OwnerContext | null;
  view?: OrchestratorCommandBinding["getView"] extends () => infer V
    ? V
    : never;
  store?: PendingPointerStore;
  submit?: FiniteCommandPort["submit"];
  readOperation?: FiniteCommandPort["readOperation"];
  makeLaunchIntent?: OrchestratorCommandBinding["makeLaunchIntent"];
  makeMessageIntent?: OrchestratorCommandBinding["makeMessageIntent"];
  makeStopIntent?: OrchestratorCommandBinding["makeStopIntent"];
} = {}) {
  let ctx: OwnerContext | null =
    overrides.ctx === undefined
      ? { principalScope: "owner-a", generation: "gen-1" }
      : overrides.ctx;
  let view = overrides.view ?? {
    projects: [{ ref: "proj-a", label: "Project A" }],
    profiles: [{ ref: "prof-a", label: "Profile A" }],
    session: defaultSession,
  };
  const listeners = new Set<() => void>();
  let seq = 0;
  const prepare = vi.fn((intent: CommandIntent): OperationPointer => ({
    operationKey: `op-${++seq}`,
    kind: intent.kind,
    targetKey: intent.targetKey,
  }));
  const submit =
    overrides.submit ??
    vi.fn(async (pointer: OperationPointer, intent: CommandIntent): Promise<EffectReceipt> => ({
      operationKey: pointer.operationKey,
      kind: pointer.kind,
      targetKey: pointer.targetKey,
      disposition: "accepted",
      ...(intent.kind === "launch"
        ? { missionSelection: { workRef: "WS:LAUNCH", rootJobId: "JOB-L" } }
        : {}),
    }));
  const readOperation =
    overrides.readOperation ??
    vi.fn(async (pointer: OperationPointer): Promise<EffectReceipt> => ({
      operationKey: pointer.operationKey,
      kind: pointer.kind,
      targetKey: pointer.targetKey,
      disposition: "accepted",
      ...(pointer.kind === "launch"
        ? { missionSelection: { workRef: "WS:LAUNCH", rootJobId: "JOB-L" } }
        : {}),
    }));
  const port: FiniteCommandPort = {
    context: () => ctx,
    prepare,
    submit,
    readOperation,
  };
  const binding: OrchestratorCommandBinding = {
    port,
    store: overrides.store ?? memoryStore(),
    getView: () => view,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    makeLaunchIntent:
      overrides.makeLaunchIntent ??
      ((form) => ({
        kind: "launch",
        targetKey: "opaque-launch",
        payload: { ...form },
      })),
    makeMessageIntent:
      overrides.makeMessageIntent ??
      ((sessionKey, text) => ({
        kind: "message",
        targetKey: "opaque-session",
        payload: { sessionKey, text },
      })),
    makeStopIntent:
      overrides.makeStopIntent ??
      ((sessionKey) => ({
        kind: "stop",
        targetKey: "opaque-session",
        payload: { sessionKey },
      })),
  };
  return {
    binding,
    prepare,
    submit,
    readOperation,
    setCtx: (next: OwnerContext | null) => {
      ctx = next;
    },
    setView: (next: typeof view) => {
      view = next;
      for (const listener of listeners) listener();
    },
  };
}

function installCommandHost(
  binding: OrchestratorCommandBinding | undefined,
  auth: AuthState = {
    status: "signed_in",
    reason: null,
    acquisition: true,
    content: true,
  },
) {
  let current = auth;
  let listener = (_state: AuthState) => {};
  window.MastermindMissionHost = {
    selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
    readPrograms,
    readMission: async ({ workRef, rootJobId }) =>
      missionFixture(workRef, rootJobId),
    ...(binding ? { commandBinding: binding } : {}),
    auth: {
      getState: () => current,
      subscribe: (fn) => {
        listener = fn;
        return () => {};
      },
      signIn: async () => {},
      signOut: async () => {},
    },
  };
  return {
    notify: (state: AuthState) => {
      current = state;
      listener(state);
    },
    setAuth: (state: AuthState) => {
      current = state;
    },
  };
}

async function launchFromWork(user: ReturnType<typeof userEvent.setup>) {
  await navigateCompanyOperation(user, "Work");
  await user.type(
    screen.getByLabelText("Goal"),
    "Ship the orchestrator",
  );
  await user.click(screen.getByRole("button", { name: "Launch" }));
}

describe("App command composition", () => {
  it("dispatches nothing for absent, incomplete, or unauthenticated bindings", async () => {
    const incomplete = makeCommandBinding();
    const user = userEvent.setup();

    installCommandHost(undefined);
    render(<App />);
    await navigateCompanyOperation(user, "Work");
    expect(screen.getByText(COMMAND_ROUTE_UNAVAILABLE)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Launch" })).toBeNull();
    cleanup();

    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
      readPrograms,
      readMission: async () => missionFixture("WS:ALPHA", "JOB-A"),
      commandBinding: {
        port: incomplete.binding.port,
        store: incomplete.binding.store,
        getView: incomplete.binding.getView,
        subscribe: incomplete.binding.subscribe,
        makeLaunchIntent: incomplete.binding.makeLaunchIntent,
        makeMessageIntent: incomplete.binding.makeMessageIntent,
      } as OrchestratorCommandBinding,
      auth: {
        getState: () => ({
          status: "signed_in",
          reason: null,
          acquisition: true,
          content: true,
        }),
        subscribe: () => () => {},
        signIn: async () => {},
        signOut: async () => {},
      },
    };
    render(<App />);
    await navigateCompanyOperation(user, "Work");
    expect(screen.getByText(COMMAND_ROUTE_UNAVAILABLE)).toBeTruthy();
    expect(incomplete.prepare).not.toHaveBeenCalled();
    expect(incomplete.submit).not.toHaveBeenCalled();
    cleanup();

    const signedOut = makeCommandBinding();
    installCommandHost(signedOut.binding, {
      status: "signed_out",
      reason: null,
      acquisition: false,
      content: false,
    });
    render(<App />);
    await navigateCompanyOperation(user, "Work");
    expect(screen.getByText(COMMAND_ROUTE_UNAVAILABLE)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Launch" })).toBeNull();
    expect(signedOut.prepare).not.toHaveBeenCalled();
    expect(signedOut.submit).not.toHaveBeenCalled();
  });

  it("selects the exact returned mission after an accepted launch", async () => {
    const { binding, prepare, submit } = makeCommandBinding();
    installCommandHost(binding);
    const user = userEvent.setup();
    render(<App />);
    await launchFromWork(user);
    await waitFor(() =>
      expect(window.location.search).toContain("work_ref=WS%3ALAUNCH"),
    );
    expect(window.location.search).toContain("root_job_id=JOB-L");
    expect(
      screen.getByRole("heading", { name: "Projects", level: 1 }),
    ).toBeTruthy();
    expect(
      screen.getByRole("tab", { name: "Overview" }).getAttribute("aria-selected"),
    ).toBe("true");
    expect(prepare).toHaveBeenCalledTimes(1);
    expect(submit).toHaveBeenCalledTimes(1);
    expect(prepare.mock.calls[0][0].kind).toBe("launch");
    expect(prepare.mock.calls[0][0].targetKey).toBe("opaque-launch");
  });

  it("does not prepare or submit twice for double launch, send, or stop", async () => {
    const launchHold = deferred<EffectReceipt>();
    const { binding, prepare, submit } = makeCommandBinding({
      submit: vi.fn(() => launchHold.promise),
    });
    installCommandHost(binding);
    const user = userEvent.setup();
    render(<App />);
    await navigateCompanyOperation(user, "Work");
    await user.type(screen.getByLabelText("Goal"), "Ship the orchestrator");
    const launch = screen.getByRole("button", { name: "Launch" });
    await user.click(launch);
    await user.click(launch);
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
    expect(prepare).toHaveBeenCalledTimes(1);

    cleanup();
    history.replaceState(null, "", "/?work_ref=WS%3AALPHA&root_job_id=JOB-A");
    const sendHold = deferred<EffectReceipt>();
    const second = makeCommandBinding({
      submit: vi.fn(() => sendHold.promise),
    });
    installCommandHost(second.binding);
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Conversation" }));
    await user.type(screen.getByLabelText("Message"), "Hello orchestrator");
    const send = screen.getByRole("button", { name: "Send" });
    await user.click(send);
    await user.click(send);
    await waitFor(() => expect(second.submit).toHaveBeenCalledTimes(1));
    expect(second.prepare).toHaveBeenCalledTimes(1);
    expect(second.prepare.mock.calls[0][0].kind).toBe("message");

    cleanup();
    history.replaceState(null, "", "/?work_ref=WS%3AALPHA&root_job_id=JOB-A");
    const stopHold = deferred<EffectReceipt>();
    const third = makeCommandBinding({
      submit: vi.fn(() => stopHold.promise),
    });
    installCommandHost(third.binding);
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Conversation" }));
    const stop = screen.getByRole("button", { name: "Request stop" });
    await user.click(stop);
    await user.click(stop);
    await waitFor(() => expect(third.submit).toHaveBeenCalledTimes(1));
    expect(third.prepare).toHaveBeenCalledTimes(1);
    expect(third.prepare.mock.calls[0][0].kind).toBe("stop");
  });

  it("recovers a lost launch with readOperation only", async () => {
    const submit = vi.fn(async () => {
      throw new Error("transport lost secret");
    });
    const { binding, prepare, readOperation } = makeCommandBinding({ submit });
    installCommandHost(binding);
    const user = userEvent.setup();
    render(<App />);
    await launchFromWork(user);
    expect(await screen.findByRole("button", { name: "Check status" })).toBeTruthy();
    expect(document.body.textContent).not.toContain("transport lost secret");
    await user.click(screen.getByRole("button", { name: "Check status" }));
    await waitFor(() => expect(readOperation).toHaveBeenCalledTimes(1));
    expect(prepare).toHaveBeenCalledTimes(1);
    expect(submit).toHaveBeenCalledTimes(1);
  });

  it("does not let an A-B-A late receipt set the new selection", async () => {
    const pending = deferred<EffectReceipt>();
    const submit = vi.fn((_pointer: OperationPointer, _intent: CommandIntent) => pending.promise);
    const made = makeCommandBinding({ submit });
    const host = installCommandHost(made.binding);
    const user = userEvent.setup();
    render(<App />);
    await launchFromWork(user);
    expect(made.prepare).toHaveBeenCalledTimes(1);
    act(() =>
      host.notify({
        status: "signed_out",
        reason: null,
        acquisition: false,
        content: false,
      }),
    );
    made.setCtx({ principalScope: "owner-b", generation: "gen-2" });
    host.setAuth({
      status: "signed_in",
      reason: null,
      acquisition: true,
      content: true,
    });
    act(() =>
      host.notify({
        status: "signed_in",
        reason: null,
        acquisition: true,
        content: true,
      }),
    );
    made.setCtx({ principalScope: "owner-a", generation: "gen-3" });
    host.setAuth({
      status: "signed_in",
      reason: null,
      acquisition: true,
      content: true,
    });
    act(() =>
      host.notify({
        status: "signed_in",
        reason: null,
        acquisition: true,
        content: true,
      }),
    );
    await act(async () =>
      pending.resolve({
        operationKey: "op-1",
        kind: "launch",
        targetKey: "opaque-launch",
        disposition: "accepted",
        missionSelection: { workRef: "WS:LAUNCH", rootJobId: "JOB-L" },
      }),
    );
    expect(window.location.search).toContain("work_ref=WS%3AALPHA");
    expect(window.location.search).not.toContain("WS%3ALAUNCH");
    expect(made.submit).toHaveBeenCalledTimes(1);
  });

  it("suppresses a stale launch result after a mission switch", async () => {
    const pending = deferred<EffectReceipt>();
    const submit = vi.fn((_pointer: OperationPointer, _intent: CommandIntent) => pending.promise);
    const made = makeCommandBinding({ submit });
    installCommandHost(made.binding);
    const user = userEvent.setup();
    render(<App />);
    await launchFromWork(user);
    await navigateCompanyOperation(user, "Programs");
    await user.click(await screen.findByRole("button", { name: /Beta program/ }));
    await act(async () =>
      pending.resolve({
        operationKey: "op-1",
        kind: "launch",
        targetKey: "opaque-launch",
        disposition: "accepted",
        missionSelection: { workRef: "WS:LAUNCH", rootJobId: "JOB-L" },
      }),
    );
    expect(window.location.search).toContain("work_ref=WS%3ABETA");
    expect(window.location.search).not.toContain("WS%3ALAUNCH");
    expect(made.submit).toHaveBeenCalledTimes(1);
  });

  it("does not send when the session view root does not match the selection", async () => {
    const made = makeCommandBinding({
      view: {
        projects: [{ ref: "proj-a", label: "Project A" }],
        profiles: [{ ref: "prof-a", label: "Profile A" }],
        session: {
          ...defaultSession,
          selection: { workRef: "WS:OTHER", rootJobId: "JOB-Z" },
        },
      },
    });
    installCommandHost(made.binding);
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Conversation" }));
    expect(screen.getByText(COMMAND_ROUTE_UNAVAILABLE)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Send" })).toBeNull();
    expect(made.prepare).not.toHaveBeenCalled();
    expect(made.submit).not.toHaveBeenCalled();
  });

  it("still passes all five result selector fields with a command binding installed", async () => {
    const h = resultHost();
    const made = makeCommandBinding();
    window.MastermindMissionHost!.commandBinding = made.binding;
    render(<App />);
    await openResult();
    expect(h.detail).toHaveBeenCalledTimes(1);
    expect(h.detail).toHaveBeenCalledWith(
      expect.objectContaining({
        workRef: "WS:DESIGN",
        rootJobId: "JOB-001",
        jobId: "JOB-004",
        attemptId: "ATT-44444444444444444444444444444444",
        resultEnvelopeDigest:
          "390cfeea0f8476caa22dd263a243acf66216ea14d560ad6c908f668f59052a3a",
      }),
    );
    expect(made.prepare).not.toHaveBeenCalled();
  });
});

describe("host-composition repair regressions (R2)", () => {
  it("F1: a pre-existing pending pointer is recoverable through Check status without any new submit", async () => {
    const seeded: OperationPointer = {
      operationKey: "op-seeded",
      kind: "launch",
      targetKey: "opaque-launch",
    };
    const data = new Map<string, OperationPointer>([
      ["owner-a", seeded],
    ]);
    const store: PendingPointerStore = {
      read: (scope) => data.get(scope) ?? null,
      reserve: (scope, pointer) => {
        const existing = data.get(scope);
        if (existing) return { reserved: false, pointer: existing };
        data.set(scope, pointer);
        return { reserved: true };
      },
      clearIfEqual: (scope, pointer) => {
        const current = data.get(scope);
        if (
          current &&
          current.operationKey === pointer.operationKey &&
          current.kind === pointer.kind &&
          current.targetKey === pointer.targetKey
        ) {
          data.delete(scope);
          return true;
        }
        return false;
      },
    };
    const readOperation = vi
      .fn(async (_pointer: OperationPointer): Promise<EffectReceipt> => {
        throw new Error("unreachable without a seeded receipt");
      })
      .mockResolvedValueOnce({
        operationKey: "op-seeded",
        kind: "launch",
        targetKey: "opaque-launch",
        disposition: "unknown",
      })
      .mockResolvedValueOnce({
        operationKey: "op-seeded",
        kind: "launch",
        targetKey: "opaque-launch",
        disposition: "refused",
      });
    const made = makeCommandBinding({ store, readOperation });
    installCommandHost(made.binding);
    const user = userEvent.setup();
    render(<App />);
    await launchFromWork(user);
    // begin() refuses to submit over the unresolved seeded pointer, and the
    // static PENDING_POINTER hold keeps recovery reachable (not disabled).
    await waitFor(() =>
      expect(
        screen
          .getByRole("button", { name: "Check status" })
          .hasAttribute("disabled"),
      ).toBe(false),
    );
    expect(made.prepare).not.toHaveBeenCalled();
    expect(made.submit).not.toHaveBeenCalled();

    // First recovery is uncertain: read-only, exact pointer, still held.
    await user.click(screen.getByRole("button", { name: "Check status" }));
    await waitFor(() => expect(readOperation).toHaveBeenCalledTimes(1));
    expect(readOperation.mock.calls[0][0]).toEqual(seeded);
    expect(made.prepare).not.toHaveBeenCalled();
    expect(made.submit).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(
        screen
          .getByRole("button", { name: "Check status" })
          .hasAttribute("disabled"),
      ).toBe(false),
    );
    expect(store.read("owner-a")).toEqual(seeded);

    // Terminal refusal correlates completion: pointer cleared, guard released,
    // draft preserved, no navigation.
    await user.click(screen.getByRole("button", { name: "Check status" }));
    await waitFor(() => expect(made.readOperation).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Launch" })).toBeTruthy(),
    );
    expect(store.read("owner-a")).toBeNull();
    expect(
      (screen.getByLabelText("Goal") as HTMLTextAreaElement).value,
    ).toBe("Ship the orchestrator");
    expect(window.location.search).toContain("work_ref=WS%3AALPHA");
    expect(made.prepare).not.toHaveBeenCalled();
    expect(made.submit).not.toHaveBeenCalled();
  });

  it("F1: a validated terminal recovery of a seeded launch pointer navigates and clears the hint", async () => {
    const seeded: OperationPointer = {
      operationKey: "op-nav",
      kind: "launch",
      targetKey: "opaque-launch",
    };
    const data = new Map<string, OperationPointer>([["owner-a", seeded]]);
    const store: PendingPointerStore = {
      read: (scope) => data.get(scope) ?? null,
      reserve: (scope, pointer) => {
        const existing = data.get(scope);
        if (existing) return { reserved: false, pointer: existing };
        data.set(scope, pointer);
        return { reserved: true };
      },
      clearIfEqual: (scope, pointer) => {
        const current = data.get(scope);
        if (!current || current.operationKey !== pointer.operationKey || current.kind !== pointer.kind || current.targetKey !== pointer.targetKey) return false;
        data.delete(scope);
        return true;
      },
    };
    const readOperation = vi.fn(
      async (_pointer: OperationPointer): Promise<EffectReceipt> => ({
        operationKey: "op-nav",
        kind: "launch",
        targetKey: "opaque-launch",
        disposition: "accepted",
        missionSelection: { workRef: "WS:LAUNCH", rootJobId: "JOB-L" },
      }),
    );
    const made = makeCommandBinding({ store, readOperation });
    installCommandHost(made.binding);
    const user = userEvent.setup();
    render(<App />);
    await launchFromWork(user);
    await waitFor(() =>
      expect(
        screen
          .getByRole("button", { name: "Check status" })
          .hasAttribute("disabled"),
      ).toBe(false),
    );
    await user.click(screen.getByRole("button", { name: "Check status" }));
    await waitFor(() =>
      expect(window.location.search).toContain("work_ref=WS%3ALAUNCH"),
    );
    expect(window.location.search).toContain("root_job_id=JOB-L");
    expect(store.read("owner-a")).toBeNull();
    expect(made.prepare).not.toHaveBeenCalled();
    expect(made.submit).not.toHaveBeenCalled();
    expect(made.readOperation).toHaveBeenCalledTimes(1);
  });

  it("F3: Conversation shows the fixed command-route unavailable code when the binding is absent", async () => {
    installCommandHost(undefined);
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Conversation" }));
    expect(screen.getByText("Session Workspace")).toBeTruthy();
    expect(screen.getByText(COMMAND_ROUTE_UNAVAILABLE)).toBeTruthy();
    // No fabricated session, connection, or dispatch surface.
    expect(screen.queryByRole("button", { name: "Send" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Request stop" })).toBeNull();
    expect(screen.queryByText("Connected")).toBeNull();
    // The read-only conversation reader card remains intact.
    expect(
      screen.getByText("This app has no connected conversation source yet."),
    ).toBeTruthy();
  });

  it("F4: a stop requested while a send is held is refused once and never wedges", async () => {
    const hold = deferred<EffectReceipt>();
    const made = makeCommandBinding({
      submit: vi.fn(() => hold.promise),
    });
    installCommandHost(made.binding);
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Conversation" }));
    await user.type(screen.getByLabelText("Message"), "Hello orchestrator");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(made.submit).toHaveBeenCalledTimes(1));
    expect(made.prepare).toHaveBeenCalledTimes(1);
    expect(made.prepare.mock.calls[0][0].kind).toBe("message");

    // Cross-action click while the send is unresolved.
    await user.click(screen.getByRole("button", { name: "Request stop" }));
    expect(made.prepare).toHaveBeenCalledTimes(1);
    expect(made.submit).toHaveBeenCalledTimes(1);
    // The new callback is refused exactly once: its own guard releases.
    expect(screen.getByRole("button", { name: "Request stop" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Stopping…" })).toBeNull();
    // The original send stays visibly held.
    expect(screen.getByRole("button", { name: "Sending…" })).toBeTruthy();

    // The original receipt settles only on the original guard; the stop
    // control is usable again, not stuck at "Stopping…".
    await act(async () =>
      hold.resolve({
        operationKey: "op-1",
        kind: "message",
        targetKey: "opaque-session",
        disposition: "accepted",
      }),
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Send" })).toBeTruthy(),
    );
    expect(screen.getByRole("button", { name: "Request stop" })).toBeTruthy();
    expect(
      (screen.getByLabelText("Message") as HTMLTextAreaElement).value,
    ).toBe("");
    expect(made.prepare).toHaveBeenCalledTimes(1);
    expect(made.submit).toHaveBeenCalledTimes(1);
  });

  it("F4: a launch requested while another launch is held is refused once without touching the original", async () => {
    const hold = deferred<EffectReceipt>();
    const made = makeCommandBinding({
      submit: vi.fn(() => hold.promise),
    });
    installCommandHost(made.binding);
    const user = userEvent.setup();
    render(<App />);
    await navigateCompanyOperation(user, "Work");
    await user.type(screen.getByLabelText("Goal"), "First launch");
    await user.click(screen.getByRole("button", { name: "Launch" }));
    await waitFor(() => expect(made.submit).toHaveBeenCalledTimes(1));

    // A second dispatch from a remounted leaf (mission switch and back).
    await navigateCompanyOperation(user, "Programs");
    await user.click(await screen.findByRole("button", { name: /Beta program/ }));
    await navigateCompanyOperation(user, "Work");
    await user.type(screen.getByLabelText("Goal"), "Second launch");
    await user.click(screen.getByRole("button", { name: "Launch" }));
    expect(made.prepare).toHaveBeenCalledTimes(1);
    expect(made.submit).toHaveBeenCalledTimes(1);
    // Refused once at click time: the second form is usable, draft preserved.
    expect(screen.getByRole("button", { name: "Launch" })).toBeTruthy();
    expect(
      (screen.getByLabelText("Goal") as HTMLTextAreaElement).value,
    ).toBe("Second launch");
    expect(screen.getByRole("button", { name: "Check status" })).toBeTruthy();

    // The original launch is still the only pending operation; its receipt
    // settles on its own guard and pointer only.
    await act(async () =>
      hold.resolve({
        operationKey: "op-1",
        kind: "launch",
        targetKey: "opaque-launch",
        disposition: "accepted",
        missionSelection: { workRef: "WS:LAUNCH", rootJobId: "JOB-L" },
      }),
    );
    // The mission switch superseded the original selection, so even a valid
    // terminal receipt must not navigate to the launch target here.
    await waitFor(() => {
      expect(window.location.search).toContain("work_ref=WS%3ABETA");
      expect(window.location.search).not.toContain("WS%3ALAUNCH");
    });
    expect(made.prepare).toHaveBeenCalledTimes(1);
    expect(made.submit).toHaveBeenCalledTimes(1);
  });

  it("F2: replacing the binding object supersedes an in-flight receipt even under the same owner epoch", async () => {
    const hold = deferred<EffectReceipt>();
    const old = makeCommandBinding({ submit: vi.fn(() => hold.promise) });
    installCommandHost(old.binding);
    const replacement = makeCommandBinding();
    const user = userEvent.setup();
    render(<App />);
    await launchFromWork(user);
    await waitFor(() => expect(old.submit).toHaveBeenCalledTimes(1));
    // Same principalScope and generation, new binding object, no rerender yet.
    window.MastermindMissionHost!.commandBinding = replacement.binding;
    await act(async () =>
      hold.resolve({
        operationKey: "op-1",
        kind: "launch",
        targetKey: "opaque-launch",
        disposition: "accepted",
        missionSelection: { workRef: "WS:LAUNCH", rootJobId: "JOB-L" },
      }),
    );
    // The old receipt is stale: no navigation, callback completed refused
    // exactly once, draft preserved, replacement dispatches nothing.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Launch" })).toBeTruthy(),
    );
    expect(window.location.search).toContain("work_ref=WS%3AALPHA");
    expect(window.location.search).not.toContain("WS%3ALAUNCH");
    expect(replacement.prepare).not.toHaveBeenCalled();
    expect(replacement.submit).not.toHaveBeenCalled();
    expect(
      (screen.getByLabelText("Goal") as HTMLTextAreaElement).value,
    ).toBe("Ship the orchestrator");
    // The replacement route owns the next dispatch through its own controller.
    await user.click(screen.getByRole("button", { name: "Launch" }));
    await waitFor(() => expect(replacement.submit).toHaveBeenCalledTimes(1));
    expect(replacement.prepare).toHaveBeenCalledTimes(1);
    expect(old.submit).toHaveBeenCalledTimes(1);
  });

  it("F2: a receipt after the rerender observed the replacement is refused and the uncertain pointer is kept", async () => {
    const hold = deferred<EffectReceipt>();
    // One shared store: the pointer written by the old binding must survive
    // a stale settlement and remain recoverable under the replacement.
    const data = new Map<string, OperationPointer>();
    const store: PendingPointerStore = {
      read: (scope) => data.get(scope) ?? null,
      reserve: (scope, pointer) => {
        const existing = data.get(scope);
        if (existing) return { reserved: false, pointer: existing };
        data.set(scope, pointer);
        return { reserved: true };
      },
      clearIfEqual: (scope, pointer) => {
        const current = data.get(scope);
        if (
          current &&
          current.operationKey === pointer.operationKey &&
          current.kind === pointer.kind &&
          current.targetKey === pointer.targetKey
        ) {
          data.delete(scope);
          return true;
        }
        return false;
      },
    };
    const replacementRead = vi.fn(
      async (_pointer: OperationPointer): Promise<EffectReceipt> => ({
        operationKey: "op-1",
        kind: "launch",
        targetKey: "opaque-launch",
        disposition: "refused",
      }),
    );
    const old = makeCommandBinding({
      store,
      submit: vi.fn(() => hold.promise),
    });
    installCommandHost(old.binding);
    const replacement = makeCommandBinding({
      store,
      readOperation: replacementRead,
    });
    const user = userEvent.setup();
    render(<App />);
    await launchFromWork(user);
    await waitFor(() => expect(old.submit).toHaveBeenCalledTimes(1));
    const written = store.read("owner-a");
    expect(written).toEqual({
      operationKey: "op-1",
      kind: "launch",
      targetKey: "opaque-launch",
    });
    // Swap the binding and force the composition to observe it.
    window.MastermindMissionHost!.commandBinding = replacement.binding;
    old.setView({
      projects: [{ ref: "proj-a", label: "Project A churned" }],
      profiles: [{ ref: "prof-a", label: "Profile A" }],
      session: defaultSession,
    });
    // The old receipt resolves as UNCERTAIN after the replacement committed.
    await act(async () =>
      hold.resolve({
        operationKey: "op-1",
        kind: "launch",
        targetKey: "opaque-launch",
        disposition: "unknown",
      }),
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Launch" })).toBeTruthy(),
    );
    expect(window.location.search).toContain("work_ref=WS%3AALPHA");
    // The original uncertain pointer was not cleared by the stale admission.
    expect(store.read("owner-a")).toEqual(written);

    // A retry under the replacement sees the preserved pointer and recovers
    // read-only: zero new prepare/submit anywhere.
    await user.click(screen.getByRole("button", { name: "Launch" }));
    await waitFor(() =>
      expect(
        screen
          .getByRole("button", { name: "Check status" })
          .hasAttribute("disabled"),
      ).toBe(false),
    );
    await user.click(screen.getByRole("button", { name: "Check status" }));
    await waitFor(() => expect(replacementRead).toHaveBeenCalledTimes(1));
    expect(replacementRead.mock.calls[0][0]).toEqual(written);
    expect(replacement.prepare).not.toHaveBeenCalled();
    expect(replacement.submit).not.toHaveBeenCalled();
    expect(old.prepare).toHaveBeenCalledTimes(1);
    expect(old.submit).toHaveBeenCalledTimes(1);
    // Terminal refusal through the live route clears exactly that pointer.
    await waitFor(() => expect(store.read("owner-a")).toBeNull());
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Launch" })).toBeTruthy(),
    );
  });

  it("F2: subscription churn on the same binding keeps one controller and never re-dispatches", async () => {
    const hold = deferred<EffectReceipt>();
    const made = makeCommandBinding({ submit: vi.fn(() => hold.promise) });
    installCommandHost(made.binding);
    const user = userEvent.setup();
    render(<App />);
    await launchFromWork(user);
    await waitFor(() => expect(made.submit).toHaveBeenCalledTimes(1));
    made.setView({
      projects: [
        { ref: "proj-a", label: "Project A renamed" },
        { ref: "proj-b", label: "Project B" },
      ],
      profiles: [{ ref: "prof-a", label: "Profile A" }],
      session: defaultSession,
    });
    made.setView({
      projects: [{ ref: "proj-a", label: "Project A" }],
      profiles: [{ ref: "prof-a", label: "Profile A" }],
      session: defaultSession,
    });
    await act(async () =>
      hold.resolve({
        operationKey: "op-1",
        kind: "launch",
        targetKey: "opaque-launch",
        disposition: "accepted",
        missionSelection: { workRef: "WS:LAUNCH", rootJobId: "JOB-L" },
      }),
    );
    await waitFor(() =>
      expect(window.location.search).toContain("work_ref=WS%3ALAUNCH"),
    );
    expect(made.prepare).toHaveBeenCalledTimes(1);
    expect(made.submit).toHaveBeenCalledTimes(1);
  });
});


describe("host-composition repair regressions (R4)", () => {
  it("F5: Check status after a pre-render binding replacement recovers through nothing and keeps the original uncertainty", async () => {
    const seeded: OperationPointer = {
      operationKey: "op-seeded",
      kind: "launch",
      targetKey: "opaque-launch",
    };
    const data1 = new Map<string, OperationPointer>([["owner-a", seeded]]);
    const store1: PendingPointerStore = {
      read: (scope) => data1.get(scope) ?? null,
      reserve: (scope, pointer) => {
        const existing = data1.get(scope);
        if (existing) return { reserved: false, pointer: existing };
        data1.set(scope, pointer);
        return { reserved: true };
      },
      clearIfEqual: (scope, pointer) => {
        const current = data1.get(scope);
        if (
          current &&
          current.operationKey === pointer.operationKey &&
          current.kind === pointer.kind &&
          current.targetKey === pointer.targetKey
        ) {
          data1.delete(scope);
          return true;
        }
        return false;
      },
    };
    const data2 = new Map<string, OperationPointer>();
    const store2: PendingPointerStore = {
      read: (scope) => data2.get(scope) ?? null,
      reserve: (scope, pointer) => {
        const existing = data2.get(scope);
        if (existing) return { reserved: false, pointer: existing };
        data2.set(scope, pointer);
        return { reserved: true };
      },
      clearIfEqual: (scope, pointer) => {
        const current = data2.get(scope);
        if (
          current &&
          current.operationKey === pointer.operationKey &&
          current.kind === pointer.kind &&
          current.targetKey === pointer.targetKey
        ) {
          data2.delete(scope);
          return true;
        }
        return false;
      },
    };
    const oldRead = vi.fn(
      async (_pointer: OperationPointer): Promise<EffectReceipt> => ({
        operationKey: "op-seeded",
        kind: "launch",
        targetKey: "opaque-launch",
        disposition: "accepted",
        missionSelection: { workRef: "WS:OLDROUTE", rootJobId: "JOB-OLD" },
      }),
    );
    const replacementRead = vi.fn(
      async (pointer: OperationPointer): Promise<EffectReceipt> => ({
        operationKey: pointer.operationKey,
        kind: pointer.kind,
        targetKey: pointer.targetKey,
        disposition: "refused",
      }),
    );
    const old = makeCommandBinding({ store: store1, readOperation: oldRead });
    installCommandHost(old.binding);
    const replacement = makeCommandBinding({
      store: store2,
      readOperation: replacementRead,
    });
    const user = userEvent.setup();
    render(<App />);
    await launchFromWork(user);
    // Static PENDING_POINTER hold: recovery reachable, zero dispatch.
    await waitFor(() =>
      expect(
        screen
          .getByRole("button", { name: "Check status" })
          .hasAttribute("disabled"),
      ).toBe(false),
    );
    expect(old.prepare).not.toHaveBeenCalled();
    expect(old.submit).not.toHaveBeenCalled();
    // Replace the binding object with the SAME owner scope/generation and
    // no rerender, then ask for a status check through the live binding.
    window.MastermindMissionHost!.commandBinding = replacement.binding;
    await user.click(screen.getByRole("button", { name: "Check status" }));
    await act(async () => {
      for (let i = 0; i < 8; i++) await Promise.resolve();
    });
    // The live binding owns the check: the superseded slot's controller,
    // port, and store are untouched — no old readOperation, no status
    // publication from the old route, no navigation, no uncertainty clear.
    expect(oldRead).not.toHaveBeenCalled();
    expect(replacementRead).not.toHaveBeenCalled();
    expect(window.location.search).toContain("work_ref=WS%3AALPHA");
    expect(window.location.search).not.toContain("WS%3AOLDROUTE");
    expect(store1.read("owner-a")).toEqual(seeded);
    // The hold is not wedged: the control stays enabled.
    expect(
      screen
        .getByRole("button", { name: "Check status" })
        .hasAttribute("disabled"),
    ).toBe(false);

    // Once the composition observes the replacement (a rerender swaps the
    // slot), Check status recovers through the LIVE binding's controller.
    // The seeded pointer lives only in the old store, so the live recover
    // is read-only and reaches no old-port call; the uncertainty survives.
    await user.click(screen.getByRole("button", { name: "Today" }));
    await navigateCompanyOperation(user, "Work");
    await user.click(screen.getByRole("button", { name: "Check status" }));
    await act(async () => {
      for (let i = 0; i < 8; i++) await Promise.resolve();
    });
    expect(oldRead).not.toHaveBeenCalled();
    expect(replacementRead).not.toHaveBeenCalled();
    expect(window.location.search).toContain("work_ref=WS%3AALPHA");
    expect(store1.read("owner-a")).toEqual(seeded);
    // Re-entry: the in-flight flag reset and the control is usable again.
    expect(
      screen
        .getByRole("button", { name: "Check status" })
        .hasAttribute("disabled"),
    ).toBe(false);
    expect(replacement.prepare).not.toHaveBeenCalled();
    expect(replacement.submit).not.toHaveBeenCalled();
  });

  it("F5: Check status during a pre-render replacement with an in-flight submit neither joins nor re-reads the old route", async () => {
    const hold = deferred<EffectReceipt>();
    const old = makeCommandBinding({ submit: vi.fn(() => hold.promise) });
    installCommandHost(old.binding);
    const replacement = makeCommandBinding();
    const user = userEvent.setup();
    render(<App />);
    await launchFromWork(user);
    await waitFor(() => expect(old.submit).toHaveBeenCalledTimes(1));
    // Check status is rendered while the submit is unresolved.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Check status" })).toBeTruthy(),
    );
    // Pre-render replacement, then a status check through the live binding.
    window.MastermindMissionHost!.commandBinding = replacement.binding;
    await user.click(screen.getByRole("button", { name: "Check status" }));
    await act(async () =>
      hold.resolve({
        operationKey: "op-1",
        kind: "launch",
        targetKey: "opaque-launch",
        disposition: "accepted",
        missionSelection: { workRef: "WS:STALE", rootJobId: "JOB-STALE" },
      }),
    );
    await act(async () => {
      for (let i = 0; i < 8; i++) await Promise.resolve();
    });
    // The old submit's own receipt settles only its own pending: no fresh
    // readOperation through the old port, no navigation under the live
    // binding, the callback refused exactly once with the draft preserved.
    expect(old.readOperation).not.toHaveBeenCalled();
    expect(replacement.readOperation).not.toHaveBeenCalled();
    expect(replacement.submit).not.toHaveBeenCalled();
    expect(window.location.search).toContain("work_ref=WS%3AALPHA");
    expect(window.location.search).not.toContain("WS%3ASTALE");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Launch" })).toBeTruthy(),
    );
    expect(
      (screen.getByLabelText("Goal") as HTMLTextAreaElement).value,
    ).toBe("Ship the orchestrator");
    // The exact terminal receipt cleared the OLD store's own pointer.
    expect(old.binding.store.read("owner-a")).toBeNull();
    expect(replacement.prepare).not.toHaveBeenCalled();
  });

  it("F6: an old-route settlement after an auth clear plus replacement never releases the newer pending; its own accepted receipt navigates", async () => {
    const hold1 = deferred<EffectReceipt>();
    const hold2 = deferred<EffectReceipt>();
    const old = makeCommandBinding({ submit: vi.fn(() => hold1.promise) });
    const host = installCommandHost(old.binding);
    const replacement = makeCommandBinding({
      submit: vi.fn(() => hold2.promise),
    });
    const user = userEvent.setup();
    render(<App />);
    await launchFromWork(user);
    await waitFor(() => expect(old.submit).toHaveBeenCalledTimes(1));
    // Auth clears the original pending (refused once) without resolving it.
    host.notify({
      status: "signed_out",
      reason: null,
      acquisition: false,
      content: false,
    });
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Launch" })).toBeNull(),
    );
    // The owner replaces the route object while signed out; the store is
    // distinct, so the new route starts with no pending pointer.
    window.MastermindMissionHost!.commandBinding = replacement.binding;
    host.notify({
      status: "signed_in",
      reason: null,
      acquisition: true,
      content: true,
    });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Launch" })).toBeTruthy(),
    );
    // Retry: a real dispatch under the replacement binding.
    await user.type(screen.getByLabelText("Goal"), "Retry under replacement");
    await user.click(screen.getByRole("button", { name: "Launch" }));
    await waitFor(() => expect(replacement.submit).toHaveBeenCalledTimes(1));
    expect(old.submit).toHaveBeenCalledTimes(1);
    expect((await replacement.binding.store.read("owner-a"))?.operationKey).toBe(
      "op-1",
    );
    // The OLD route's receipt arrives while the newer launch is in flight:
    // it must not navigate and must not complete or refuse the newer
    // callback — the newer guard belongs to its own route's receipt.
    await act(async () =>
      hold1.resolve({
        operationKey: "op-1",
        kind: "launch",
        targetKey: "opaque-launch",
        disposition: "accepted",
        missionSelection: { workRef: "WS:STALE", rootJobId: "JOB-STALE" },
      }),
    );
    await act(async () => {
      for (let i = 0; i < 8; i++) await Promise.resolve();
    });
    expect(window.location.search).not.toContain("WS%3ASTALE");
    expect(screen.getByRole("button", { name: "Launching…" })).toBeTruthy();
    expect((await replacement.binding.store.read("owner-a"))?.operationKey).toBe(
      "op-1",
    );
    // The newer launch's own ACCEPTED receipt settles its own pending,
    // navigates on the live route, and clears exactly its own pointer.
    await act(async () =>
      hold2.resolve({
        operationKey: "op-1",
        kind: "launch",
        targetKey: "opaque-launch",
        disposition: "accepted",
        missionSelection: { workRef: "WS:FRESH2", rootJobId: "JOB-FRESH2" },
      }),
    );
    await waitFor(() =>
      expect(window.location.search).toContain("work_ref=WS%3AFRESH2"),
    );
    expect(window.location.search).not.toContain("WS%3ASTALE");
    await waitFor(() =>
      expect(replacement.binding.store.read("owner-a")).toBeNull(),
    );
    expect(old.readOperation).not.toHaveBeenCalled();
    expect(replacement.readOperation).not.toHaveBeenCalled();
  });
});

describe("Pro/native command recovery integration", () => {
  it("Check status recovers a synchronous transport failure without resubmitting or reloading", async () => {
    const made = makeCommandBinding({
      submit: vi.fn(() => { throw new Error("transport setup failed synchronously"); }),
    });
    installCommandHost(made.binding);
    const user = userEvent.setup();
    render(<App />);
    await launchFromWork(user);
    await waitFor(() => expect(screen.getByRole("button", { name: "Check status" }).hasAttribute("disabled")).toBe(false));
    expect((await made.binding.store.read("owner-a"))?.operationKey).toBe("op-1");
    await user.click(screen.getByRole("button", { name: "Check status" }));
    await waitFor(() => expect(made.readOperation).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(window.location.search).toContain("work_ref=WS%3ALAUNCH"));
    expect(window.location.search).toContain("root_job_id=JOB-L");
    expect(made.prepare).toHaveBeenCalledTimes(1);
    expect(made.submit).toHaveBeenCalledTimes(1);
    expect(made.readOperation).toHaveBeenCalledWith(expect.objectContaining({ operationKey: "op-1", kind: "launch", targetKey: "opaque-launch" }), expect.any(AbortSignal));
    expect(made.binding.store.read("owner-a")).toBeNull();
  });
});

describe("Pro/native Conversation recovery", () => {
  it("recovers an uncertain message by exact readback, clearing only its draft", async () => {
    const made = makeCommandBinding({ submit: vi.fn(() => { throw new Error("synchronous message transport loss"); }) });
    installCommandHost(made.binding);
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Conversation" }));
    await user.type(screen.getByLabelText("Message"), "Preserve accepted scope A and report the native result.");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Check status" }).hasAttribute("disabled")).toBe(false));
    expect((screen.getByLabelText("Message") as HTMLTextAreaElement).value).toBe("Preserve accepted scope A and report the native result.");
    expect(made.binding.store.read("owner-a")).toMatchObject({ operationKey: "op-1", kind: "message", targetKey: "opaque-session" });
    expect(screen.getByRole("button", { name: "Sending…" }).hasAttribute("disabled")).toBe(true);
    await user.click(screen.getByRole("button", { name: "Check status" }));
    await waitFor(() => expect(made.readOperation).toHaveBeenCalledTimes(1));
    await waitFor(() => expect((screen.getByLabelText("Message") as HTMLTextAreaElement).value).toBe(""));
    expect(made.prepare).toHaveBeenCalledTimes(1);
    expect(made.submit).toHaveBeenCalledTimes(1);
    expect(made.readOperation).toHaveBeenCalledWith(expect.objectContaining({ operationKey: "op-1", kind: "message", targetKey: "opaque-session" }), expect.any(AbortSignal));
    expect(made.binding.store.read("owner-a")).toBeNull();
    expect(window.location.search).not.toContain("JOB-L");
  });

  it("keeps message recovery usable after its first read throws synchronously", async () => {
    const readOperation = vi.fn().mockImplementationOnce(() => { throw new Error("synchronous read failure"); }).mockImplementation(async (pointer: OperationPointer): Promise<EffectReceipt> => ({ ...pointer, disposition: "accepted" }));
    const made = makeCommandBinding({ submit: vi.fn(async () => { throw new Error("lost acknowledgement"); }), readOperation });
    installCommandHost(made.binding);
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Conversation" }));
    await user.type(screen.getByLabelText("Message"), "Continue the already accepted implementation.");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Check status" }).hasAttribute("disabled")).toBe(false));
    await user.click(screen.getByRole("button", { name: "Check status" }));
    await waitFor(() => expect(readOperation).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByRole("button", { name: "Check status" }).hasAttribute("disabled")).toBe(false));
    expect((await made.binding.store.read("owner-a"))?.operationKey).toBe("op-1");
    await user.click(screen.getByRole("button", { name: "Check status" }));
    await waitFor(() => expect(readOperation).toHaveBeenCalledTimes(2));
    expect(made.submit).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(made.binding.store.read("owner-a")).toBeNull());
  });
});
