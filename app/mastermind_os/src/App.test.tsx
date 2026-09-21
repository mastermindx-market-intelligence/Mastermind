// @vitest-environment jsdom
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import {
  bothUnavailableMissionFixture,
  controlRoomFixture,
  missionFixture,
} from "./test-fixtures";

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
});
