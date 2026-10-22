// @vitest-environment jsdom
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { controlRoomFixture, missionFixture } from "./test-fixtures";
import type { OrchestratorCommandBinding } from "./orchestration/host-command-bindings";
import type { CommandIntent, EffectReceipt, OperationPointer } from "./orchestration/operation-controller";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn().mockResolvedValue({ version: "0.1.0", source_revision: "a".repeat(40),
    build_identity: "test-build", transport: "UNCONFIGURED", state: "BUILT_NOT_PROVEN" }),
}));

const privateReason = "private-producer-detail-not-for-display";
const draft = "Keep this unsent conversation draft";

function installFixture(options: { lost?: boolean; accepted?: boolean; error?: string } = {}) {
  let pending: OperationPointer | null = null;
  const receipt = (pointer: OperationPointer): EffectReceipt => ({ ...pointer,
    disposition: options.accepted ? "accepted" : "refused", reason: privateReason });
  const prepare = vi.fn((intent: CommandIntent): OperationPointer => ({ operationKey: "feedback-op-1",
    kind: intent.kind, targetKey: intent.targetKey }));
  const submit = vi.fn(async (pointer: OperationPointer) => {
    if (options.lost) throw new Error("private-transport-loss");
    return receipt(pointer);
  });
  const readOperation = vi.fn(async (pointer: OperationPointer) => receipt(pointer));
  const binding: OrchestratorCommandBinding = {
    port: { context: () => ({ principalScope: "owner-a", generation: "gen-1" }),
      prepare, submit, readOperation },
    store: {
      read: () => pending,
      reserve: (_scope, pointer) => {
        if (pending) return { reserved: false, pointer: pending };
        pending = pointer; return { reserved: true };
      },
      clearIfEqual: (_scope, pointer) => {
        if (!pending || pending.operationKey !== pointer.operationKey ||
          pending.kind !== pointer.kind || pending.targetKey !== pointer.targetKey) return false;
        pending = null; return true;
      },
    },
    getView: () => ({ projects: [{ ref: "proj-a", label: "Project A" }],
      profiles: [{ ref: "prof-a", label: "Profile A" }],
      session: { sessionKey: "sess-1", title: "Session One", messages: [], observedAt: null,
        connection: "connected", coverage: "COMPLETE", turnBusy: false, stopLabel: "Request stop",
        selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" }, ...(options.error ? { error: options.error } : {}) } }),
    subscribe: () => () => {},
    makeLaunchIntent: form => ({ kind: "launch", targetKey: "opaque-launch", payload: { ...form } }),
    makeMessageIntent: (sessionKey, text) => ({ kind: "message", targetKey: "opaque-session", payload: { sessionKey, text } }),
    makeStopIntent: sessionKey => ({ kind: "stop", targetKey: "opaque-session", payload: { sessionKey } }),
  };
  window.MastermindMissionHost = {
    selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" }, readPrograms: async () => controlRoomFixture(),
    readMission: async ({ workRef, rootJobId }) => missionFixture(workRef, rootJobId), commandBinding: binding,
    auth: { getState: () => ({ status: "signed_in", reason: null, acquisition: true, content: true }),
      subscribe: () => () => {}, signIn: async () => {}, signOut: async () => {} },
  };
  return { binding, prepare, submit, readOperation };
}

beforeEach(() => {
  history.replaceState(null, "", "/?work_ref=WS%3AALPHA&root_job_id=JOB-A");
  delete (window as any).__TAURI_INTERNALS__;
  delete window.MastermindMissionHost;
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); delete window.MastermindMissionHost; });

async function openConversation(user: ReturnType<typeof userEvent.setup>) {
  render(<App />);
  await user.click(screen.getByRole("button", { name: "Conversation" }));
  const heading = await screen.findByRole("heading", { name: "Session One" });
  return within(heading.closest("section")!);
}

describe("Conversation owner feedback composition", () => {
  it.each(["message", "stop", "lost-message"] as const)(
    "shows a scoped safe alert after %s refusal without replay or draft loss", async mode => {
      const made = installFixture({ lost: mode === "lost-message" });
      const user = userEvent.setup(), panel = await openConversation(user);
      await user.type(panel.getByLabelText("Message"), draft);
      const location = window.location.href;
      const action = mode === "stop" ? "Request stop" : "Send";
      await user.click(panel.getByRole("button", { name: action }));
      await waitFor(() => expect(made.submit).toHaveBeenCalledTimes(1));
      if (mode === "lost-message") {
        const pointer = made.binding.store.read("owner-a");
        expect(pointer).toMatchObject({ operationKey: "feedback-op-1", kind: "message", targetKey: "opaque-session" });
        await user.click(await screen.findByRole("button", { name: "Check status" }));
        await waitFor(() => expect(made.readOperation).toHaveBeenCalledTimes(1));
        expect(made.readOperation).toHaveBeenCalledWith(pointer, expect.any(AbortSignal));
      } else expect(made.readOperation).not.toHaveBeenCalled();
      await waitFor(() => expect(panel.getByRole("button", { name: action }).hasAttribute("disabled")).toBe(false));
      expect(made.binding.store.read("owner-a")).toBeNull();
      expect(made.prepare).toHaveBeenCalledTimes(1);
      expect(made.submit).toHaveBeenCalledTimes(1);
      expect((panel.getByLabelText("Message") as HTMLTextAreaElement).value).toBe(draft);
      expect(window.location.href).toBe(location);
      expect(document.body.textContent).not.toContain(privateReason);
      expect(document.body.textContent).not.toContain("private-transport-loss");
      expect(screen.queryByRole("button", { name: "Check status" })).toBeNull();
      const alert = panel.getByRole("alert");
      expect(alert.textContent?.trim().length).toBeGreaterThan(0);
    },
  );

  it("forwards qualified owner feedback into the selected session alert without submitting", async () => {
    const error = "The selected session owner is unavailable.";
    const made = installFixture({ error }), user = userEvent.setup(), panel = await openConversation(user);
    expect(made.prepare).not.toHaveBeenCalled(); expect(made.submit).not.toHaveBeenCalled();
    expect(made.readOperation).not.toHaveBeenCalled();
    expect(panel.getByRole("alert").textContent).toContain(error);
  });

  it("does not invent a refusal alert after an accepted send", async () => {
    const made = installFixture({ accepted: true }), user = userEvent.setup(), panel = await openConversation(user);
    await user.type(panel.getByLabelText("Message"), draft);
    await user.click(panel.getByRole("button", { name: "Send" }));
    await waitFor(() => expect((panel.getByLabelText("Message") as HTMLTextAreaElement).value).toBe(""));
    expect(made.prepare).toHaveBeenCalledTimes(1); expect(made.submit).toHaveBeenCalledTimes(1);
    expect(made.readOperation).not.toHaveBeenCalled(); expect(panel.queryByRole("alert")).toBeNull();
  });
});
