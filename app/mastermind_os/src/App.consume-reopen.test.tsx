// @vitest-environment jsdom
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { directConsumeIdentity } from "./direct-native-result";
import type { AuthState } from "./host";
import { controlRoomFixture, missionFixture } from "./test-fixtures";
import { navigateCompanyOperation } from "./test-operational-navigation";
import type { OrchestratorCommandBinding } from "./orchestration/host-command-bindings";
import type { EffectReceipt, OperationPointer, OwnerContext, PendingPointerStore } from "./orchestration/operation-controller";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn().mockResolvedValue({ version: "0.1.0", source_revision: "a".repeat(40), build_identity: "test", transport: "UNCONFIGURED", state: "BUILT_NOT_PROVEN" }) }));
const original: OperationPointer = { operationKey: "retained-original-operation", kind: "launch", targetKey: "opaque-original-target" };
const signedIn: AuthState = { status: "signed_in", reason: null, acquisition: true, content: true };
const signedOut: AuthState = { status: "signed_out", reason: null, acquisition: false, content: false };
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(yes => { resolve = yes; });
  return { promise, resolve };
};
function fixture(pointer: OperationPointer | null = original, emptyCatalog = false) {
  let ctx: OwnerContext | null = { principalScope: "a".repeat(64), generation: "gen-1" };
  let auth = signedIn;
  let authListener = (_state: AuthState) => {};
  const data = new Map<string, OperationPointer>(pointer ? [["a".repeat(64), pointer]] : []);
  const store: PendingPointerStore = {
    read: scope => data.get(scope) ?? null,
    reserve: (scope, value) => {
      const saved = data.get(scope);
      if (saved) return { reserved: false, pointer: saved };
      data.set(scope, value);
      return { reserved: true };
    },
    clearIfEqual: vi.fn((scope, value) => {
      const saved = data.get(scope);
      if (!saved || saved.operationKey !== value.operationKey || saved.kind !== value.kind || saved.targetKey !== value.targetKey) return false;
      data.delete(scope);
      return true;
    }),
  };
  const prepare = vi.fn((intent): OperationPointer => ({ operationKey: "new-operation", kind: intent.kind, targetKey: intent.targetKey }));
  const publication = vi.fn();
  const submit = vi.fn(async (value): Promise<EffectReceipt> => {
    publication(value);
    return { ...value, disposition: "accepted", missionSelection: { workRef: "WS:NEW", rootJobId: "JOB-NEW" } };
  });
  const readOperation = vi.fn(async (value: OperationPointer): Promise<EffectReceipt> => ({ ...value, disposition: "accepted", ...(value.kind === "launch" ? { missionSelection: { workRef: "WS:ORIGINAL", rootJobId: "JOB-ORIGINAL" } } : {}) }));
  const binding: OrchestratorCommandBinding = {
    port: { context: () => ctx, prepare, submit, readOperation }, store,
    getView: () => ({ projects: emptyCatalog ? [] : [{ ref: "project", label: "Project" }], profiles: emptyCatalog ? [] : [{ ref: "profile", label: "Profile" }], session: null }),
    subscribe: () => () => {},
    makeLaunchIntent: form => ({ kind: "launch", targetKey: "new-target", payload: { ...form } }),
    makeMessageIntent: () => null, makeStopIntent: () => null,
  };
  window.MastermindMissionHost = {
    commandBinding: binding, readPrograms: async () => controlRoomFixture(),
    readMission: async ({ workRef, rootJobId }) => missionFixture(workRef, rootJobId),
    auth: { getState: () => auth, subscribe: fn => { authListener = fn; return () => {}; }, signIn: async () => {}, signOut: async () => {} },
  };
  return { binding, store, data, prepare, submit, publication, readOperation,
    setCtx: (value: OwnerContext | null) => { ctx = value; },
    notify: (value: AuthState) => { auth = value; authListener(value); },
  };
}
beforeEach(() => { history.replaceState(null, "", "/os/"); delete window.MastermindMissionHost; });
afterEach(() => { cleanup(); delete window.MastermindMissionHost; vi.restoreAllMocks(); });

// Canonical private pointer constructor; effect ports are explicit spies.
// This tests presentation/recovery routing only, never actual Runtime acceptance.
const consumedPointer = () => directConsumeIdentity("a".repeat(64), {
  work_ref: "WS:ORIGINAL", job_id: "JOB-123", attempt_id: "ATT-456",
}, "d".repeat(64));

it("truthfully presents an existing consume pointer and only reads its original status", async () => {
  const pointer = consumedPointer();
  const made = fixture(pointer); render(<App />);
  expect(await screen.findByText(pointer.operationKey)).toBeTruthy();
  expect(screen.getByText(/Original consume reference/)).toBeTruthy();
  expect(screen.queryByText("MALFORMED_POINTER")).toBeNull();
  expect(made.readOperation).not.toHaveBeenCalled();
  await userEvent.setup().click(screen.getByRole("button", { name: "Check status" }));
  await waitFor(() => expect(made.readOperation).toHaveBeenCalledWith(pointer, expect.any(AbortSignal)));
  expect(made.prepare).not.toHaveBeenCalled();
  expect(made.submit).not.toHaveBeenCalled();
  expect(made.publication).not.toHaveBeenCalled();
});

it.each(["target", "key", "kind", "extra"])("keeps malformed consume pointer %s unrecognized", async fault => {
  const pointer: any = consumedPointer();
  if (fault === "target") pointer.targetKey = "{}";
  if (fault === "key") pointer.operationKey = "mmos-consume-" + "z".repeat(40);
  if (fault === "kind") pointer.kind = "unknown";
  if (fault === "extra") pointer.extra = true;
  const made = fixture(pointer); render(<App />);
  expect(await screen.findByText("MALFORMED_POINTER")).toBeTruthy();
  expect(screen.queryByText(pointer.operationKey)).toBeNull();
  expect(made.readOperation).not.toHaveBeenCalled();
  expect(made.prepare).not.toHaveBeenCalled();
  expect(made.submit).not.toHaveBeenCalled();
});
