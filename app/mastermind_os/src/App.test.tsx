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
import { bindMissionHost, type AuthState } from "./host";
import { createWebAuth } from "./web-auth";
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
    const b = deferred<unknown>(),
      read = vi.fn(({ workRef }: { workRef: string }) =>
        workRef === "WS:ALPHA"
          ? Promise.resolve(missionFixture("WS:ALPHA", "JOB-A"))
          : b.promise,
      );
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
      readPrograms,
      readMission: read,
    };
    const user = userEvent.setup();
    render(<App />);
    await user.click(
      await screen.findByRole("button", { name: "Mission Workspace" }),
    );
    expect(await screen.findByText("JOB-A")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Programs" }));
    await user.click(
      await screen.findByRole("button", { name: /Beta program/ }),
    );
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
    await user.click(screen.getByRole("button", { name: "Programs" }));
    await user.click(
      await screen.findByRole("button", { name: /Beta program/ }),
    );
    expect(window.location.search).toBe(
      "?work_ref=WS%3ABETA&root_job_id=JOB-B",
    );
    expect(await screen.findByText("JOB-B")).toBeTruthy();

    window.history.back();
    await waitFor(() =>
      expect(window.location.search).toBe(
        "?work_ref=WS%3AALPHA&root_job_id=JOB-A",
      ),
    );
    expect(await screen.findByText("JOB-A")).toBeTruthy();
    window.history.forward();
    await waitFor(() =>
      expect(window.location.search).toBe(
        "?work_ref=WS%3ABETA&root_job_id=JOB-B",
      ),
    );
    expect(await screen.findByText("JOB-B")).toBeTruthy();

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
    await user.click(screen.getByRole("button", { name: "Programs" }));
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
    expect(await screen.findByText("JOB-A")).toBeTruthy();

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
  it("keeps global Work and Fleet unavailable without their canonical feeds", async () => {
    window.MastermindMissionHost = {
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
      readPrograms,
      readMission: async () => missionFixture("WS:ALPHA", "JOB-A"),
    };
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Work" }));
    expect(
      screen.getByRole("heading", { name: "Work", level: 1 }),
    ).toBeTruthy();
    expect(screen.getByText("WORK_QUEUE_SOURCE_NOT_CONNECTED")).toBeTruthy();
    expect(screen.queryByText("Missingness and source state")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Fleet & Capacity" }));
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
        name: "Chairman attention",
        level: 2,
      })
      .closest("section");
    expect(attention).toBeTruthy();
    expect(
      within(attention!).getByText(
        "Absence here is not evidence that zero decisions exist.",
        { exact: false },
      ),
    ).toBeTruthy();
    expect(within(attention!).getByText("NOT PROJECTED")).toBeTruthy();
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
    await user.click(screen.getByRole("button", { name: "Programs" }));
    await user.click(screen.getByRole("button", { name: "Conversation" }));
    await user.click(screen.getByRole("button", { name: "Programs" }));
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
    const programs = screen.getByRole("button", { name: "Programs" });
    programs.focus();
    await user.keyboard("{Enter}");
    expect(document.activeElement).toBe(programs);
    expect(programs.getAttribute("aria-current")).toBe("page");
    await user.keyboard("{Enter}");
    expect(document.activeElement).toBe(programs);
  });

  it("hands program selection to the Mission heading without stealing focus when data resolves", async () => {
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
      screen.getByRole("heading", { name: "Mission Workspace", level: 1 }),
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
