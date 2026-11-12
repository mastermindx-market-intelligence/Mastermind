// @vitest-environment jsdom
// Actual App/controller/store with explicit inert command/auth/read transports.
// No real admission, provider, service, activation or lifecycle is exercised.
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { controlRoomFixture, missionFixture } from "./test-fixtures";
import { navigateCompanyOperation } from "./test-operational-navigation";
import type { OrchestratorCommandBinding } from "./orchestration/host-command-bindings";
import type {
  OperationPointer,
  PendingPointerStore,
  FiniteCommandPort,
  OwnerContext,
} from "./orchestration/operation-controller";
import type { AuthState } from "./host";
vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn().mockResolvedValue({ state: "BUILT_NOT_PROVEN" }),
}));
function fixture(unknown = false) {
  let owner: OwnerContext | null = {
    principalScope: "owner-a",
    generation: "g1",
  };
  let auth: AuthState = {
      status: "signed_in",
      acquisition: true,
      content: true,
      reason: null,
    },
    saved: OperationPointer | null = null;
  const original: OperationPointer = {
    operationKey: "activation-original-1",
    kind: "launch",
    targetKey: "opaque-launch-not-root",
  };
  const store: PendingPointerStore = {
    read: vi.fn(() => saved),
    reserve: vi.fn((_s, p) => {
      if (saved) return { reserved: false as const, pointer: saved };
      saved = p;
      return { reserved: true as const };
    }),
    clearIfEqual: vi.fn((_s, p) => {
      if (saved?.operationKey !== p.operationKey) return false;
      saved = null;
      return true;
    }),
  };
  const receipt = () => ({
    ...original,
    disposition: unknown ? ("unknown" as const) : ("accepted" as const),
    ...(unknown
      ? {}
      : { missionSelection: { workRef: "WS:LAUNCH", rootJobId: "JOB-L" } }),
  });
  const port: FiniteCommandPort = {
    context: () => owner,
    prepare: vi.fn(() => original),
    submit: vi.fn(async () => receipt()),
    readOperation: vi.fn(async () => receipt()),
  };
  const binding: OrchestratorCommandBinding = {
    port,
    store,
    getView: () => ({
      projects: [{ ref: "proj-a", label: "Project A" }],
      profiles: [{ ref: "prof-a", label: "Profile A" }],
      session: null,
    }),
    subscribe: () => () => {},
    makeLaunchIntent: (form) => ({
      kind: "launch",
      targetKey: original.targetKey,
      payload: { ...form },
    }),
    makeMessageIntent: () => null,
    makeStopIntent: () => null,
  };
  window.MastermindMissionHost = {
    selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
    invalidationGeneration: () => 1,
    commandBinding: binding,
    readPrograms: async () => controlRoomFixture(),
    readMission: async ({ workRef, rootJobId }) =>
      missionFixture(workRef, rootJobId),
    auth: {
      getState: () => auth,
      subscribe: () => () => {},
      signIn: async () => {},
      signOut: async () => {},
    },
  };
  return {
    port,
    store,
    original,
    saved: () => saved,
    owner: (v: OwnerContext | null) => {
      owner = v;
    },
    auth: (v: AuthState) => {
      auth = v;
    },
  };
}
beforeEach(() => {
  history.replaceState(null, "", "/?work_ref=WS%3AALPHA&root_job_id=JOB-A");
  delete window.MastermindMissionHost;
});
afterEach(() => {
  cleanup();
  delete window.MastermindMissionHost;
  vi.restoreAllMocks();
});
async function launch() {
  const user = userEvent.setup();
  render(<App />);
  await navigateCompanyOperation(user, "Work");
  await user.type(screen.getByLabelText("Goal"), "Carry the original request");
  await user.click(screen.getByRole("button", { name: "Launch" }));
  return user;
}
async function estate(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Session Estate" }));
  return screen.findByRole("region", { name: "Activation receipts" });
}
it("actual accepted launch→receipt→Work→Back preserves original identity and distinguishes absent owner facts", async () => {
  const f = fixture();
  const user = await launch();
  await waitFor(() =>
    expect(window.location.search).toContain("root_job_id=JOB-L"),
  );
  const view = await estate(user);
  expect(within(view).getByText("activation-original-1")).toBeTruthy();
  expect(within(view).getAllByText("Not reported by this source")).toHaveLength(
    5,
  );
  await user.click(within(view).getByRole("button", { name: "Open Work" }));
  expect(screen.getByRole("heading", { name: "Work", level: 1 })).toBeTruthy();
  await user.click(
    screen.getByRole("button", { name: "Back to activation receipts" }),
  );
  const returned = screen.getByRole("region", { name: "Activation receipts" });
  expect(within(returned).getByText("opaque-launch-not-root")).toBeTruthy();
  await user.click(
    within(returned).getByRole("button", { name: "Open Sessions" }),
  );
  expect(document.activeElement?.id).toBe("activation-session-owner");
  expect(f.port.prepare).toHaveBeenCalledTimes(1);
  expect(f.port.submit).toHaveBeenCalledTimes(1);
  expect(f.port.readOperation).not.toHaveBeenCalled();
  expect(f.saved()).toBeNull();
});
it("unknown receipt reads only the exact original operation and preserves its durable hint", async () => {
  const f = fixture(true);
  const user = await launch();
  await screen.findByRole("button", { name: "Check status" });
  const view = await estate(user);
  expect(within(view).queryByRole("button", { name: "Open Work" })).toBeNull();
  await user.click(
    within(view).getByRole("button", { name: "Read original status" }),
  );
  await waitFor(() => expect(f.port.readOperation).toHaveBeenCalledTimes(1));
  expect(f.port.readOperation).toHaveBeenCalledWith(
    f.original,
    expect.any(AbortSignal),
  );
  expect(f.saved()).toEqual(f.original);
  expect(f.port.prepare).toHaveBeenCalledTimes(1);
  expect(f.port.submit).toHaveBeenCalledTimes(1);
});
it.each(["host", "revoked", "principal", "generation"] as const)(
  "no-render %s withdrawal refuses receipt recovery without clearing or replacement",
  async (kind) => {
    const f = fixture(true);
    const user = await launch();
    await screen.findByRole("button", { name: "Check status" });
    const view = await estate(user);
    const button = within(view).getByRole("button", {
      name: "Read original status",
    });
    if (kind === "host")
      window.MastermindMissionHost = { ...window.MastermindMissionHost! };
    if (kind === "revoked")
      f.auth({
        status: "signed_in",
        reason: null,
        acquisition: false,
        content: true,
      });
    if (kind === "principal")
      f.owner({ principalScope: "owner-b", generation: "g1" });
    if (kind === "generation")
      f.owner({ principalScope: "owner-a", generation: "g2" });
    fireEvent.click(button);
    await act(async () => {});
    expect(f.port.readOperation).not.toHaveBeenCalled();
    expect(f.store.clearIfEqual).not.toHaveBeenCalled();
    expect(f.saved()).toEqual(f.original);
    expect(f.port.submit).toHaveBeenCalledTimes(1);
  },
);

it("an accepted receipt cannot be reused after another selection and return", async () => {
  const f = fixture();
  const user = await launch();
  await waitFor(() => expect(window.location.search).toContain("JOB-L"));
  await estate(user);
  expect(screen.getByText("activation-original-1")).toBeTruthy();
  await navigateCompanyOperation(user, "Programs");
  await user.click(
    await screen.findByRole("button", { name: /Alpha program/ }),
  );
  await estate(user);
  expect(
    screen.getByText("Original request identity unavailable."),
  ).toBeTruthy();
  expect(screen.queryByText("activation-original-1")).toBeNull();
  expect(f.port.submit).toHaveBeenCalledTimes(1);
});
