// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { RetainedActivityInspector } from "./RetainedActivityInspector";
import {
  decodeRetainedActivity, validActivitySelection, type ActivitySelection, type ActivityRead,
} from "./retained-activity";
import { bindMissionHost, createNativeClient } from "../host";

afterEach(() => cleanup());
const selected: ActivitySelection = {
  work_ref: "WS:ONE", root_job_id: "JOB-100", job_id: "JOB-101",
  attempt_id: "ATT-" + "a".repeat(32),
};
const sha = "d".repeat(64);
const raw = () => ({
  schema: "mastermind.workspace_retained_activity.v1",
  selection: { ...selected },
  availability: "AVAILABLE" as const, reason_codes: [] as string[],
  source_observation: {
    schema: "mastermind.workspace_retained_activity_observation.v1",
    state: "SAME", selection: { ...selected },
    control_room: {
      instance_before: "install-a", instance_after: "install-a",
      publication_before: 5, publication_after: 5,
      document_digest: sha, source_validity_digest: sha,
      cache_currentness_digest: sha,
    },
    runtime: {
      schema: "mastermind.runtime_read_observation.v1",
      state: "SAME", source_identity: "b".repeat(32), before: 5, after: 5,
    },
  },
  activity: {
    schema: "mastermind.operator_retained_activity_metadata.v1",
    selection: { ...selected }, availability: "RETAINED",
    source: { state: "SAME_AS_OF_READ", scope: "RETAINED_CANDIDATES_ONLY",
      source_truncated: false, live_worker_count: null, global_event_total: null },
    candidate_receipts_in_sample: 1, normalized_events_in_sample: 2,
    omitted_in_sample: 0,
    rows: [
      { candidate_event_id: 15, turn_id: "ohf-turn-1", ordinal_in_candidate: 0,
        category: "TOOL_ACTIVITY", candidate_recorded_at: "2026-10-18T08:00:00Z" },
      { candidate_event_id: 15, turn_id: "ohf-turn-1", ordinal_in_candidate: 1,
        category: "TURN_COMPLETED", candidate_recorded_at: "2026-10-18T08:00:00Z" },
    ],
  },
});
const unavailable = () => ({
  ...raw(), availability: "UNAVAILABLE" as const,
  reason_codes: ["SOURCE_UNAVAILABLE"],
  source_observation: {
    ...raw().source_observation, state: "UNKNOWN",
    control_room: null, runtime: null,
  },
  activity: null,
});

describe("retained operator activity strict privacy DTO", () => {
  it("decodes only existing original owner metadata, never claims execution or private reasoning", () => {
    const original = raw();
    const value = decodeRetainedActivity(original, selected);
    expect(value.availability).toBe("AVAILABLE");
    if (value.availability !== "AVAILABLE") return;
    expect(value.rows).toHaveLength(2);
    expect(value.rows[1].category).toBe("TURN_COMPLETED");
    expect(value.sourceState).toBe("SAME");
    expect(JSON.stringify(value)).not.toMatch(/private|tool_input|native_subordinate|lease_token/);
    value.rows[0].category = "ITEM_ACTIVITY";
    expect(original.activity.rows[0].category).toBe("TOOL_ACTIVITY");
  });
  it("never treats missing rows as a zero-worker or acceptance claim", () => {
    const value = raw();
    value.activity.rows = [];
    value.activity.normalized_events_in_sample = 0;
    value.activity.candidate_receipts_in_sample = 0;
    value.activity.availability = "NO_RETAINED_CANDIDATES";
    const decoded = decodeRetainedActivity(value, selected);
    expect(decoded.availability).toBe("AVAILABLE");
    if (decoded.availability !== "AVAILABLE") return;
    expect(decoded.rows).toEqual([]);
    expect("liveWorkers" in decoded).toBe(false);
  });
  it("closed unavailable reason never becomes a history claim", () => {
    const value = decodeRetainedActivity(unavailable(), selected);
    expect(value.availability).toBe("UNAVAILABLE");
    if (value.availability !== "UNAVAILABLE") return;
    expect(value.rows).toEqual([]);
    expect(value.reasons).toEqual(["SOURCE_UNAVAILABLE"]);
  });
  it.each([
    ["foreign root", v => { v.selection.root_job_id = "JOB-999"; }],
    ["unknown payload", v => { (v.activity.rows[0] as any).prompt = "private"; }],
    ["unknown response key", v => { (v as any).private = "hidden"; }],
    ["invented liveness", v => { (v.activity.source as any).live_worker_count = 0; }],
    ["unknown model category", v => { v.activity.rows[0].category = "raw_reasoning"; }],
    ["bad source", v => { v.source_observation.runtime.state = "UNKNOWN"; }],
    ["missing seal", v => { v.source_observation.runtime.source_identity = "foreign"; }],
    ["fake acceptance", v => { (v.activity as any).accepted = true; }],
    ["too many rows", v => { v.activity.rows = Array.from({ length: 33 }, () => v.activity.rows[0]); }],
  ] as Array<[string, (value: ReturnType<typeof raw>) => void]>)("refuses %s", (_reason, change) => {
    const value = raw();
    change(value);
    expect(() => decodeRetainedActivity(value, selected)).toThrow("RETAINED_ACTIVITY_INVALID");
  });
  it("validates the original four selectors including lower-hex Attempt and direct-child root", () => {
    expect(validActivitySelection(selected)).toBe(true);
    expect(validActivitySelection({ ...selected, attempt_id: "ATT-123" })).toBe(false);
    expect(validActivitySelection({ ...selected, job_id: selected.root_job_id })).toBe(false);
    expect(validActivitySelection({ ...selected, work_ref: "WS:wrong!" })).toBe(false);
  });
});

describe("explicit retained activity component", () => {
  const read = () => vi.fn(async () => decodeRetainedActivity(raw(), selected));
  it("reads nothing until selected original Attempt button is clicked", async () => {
    const source = read();
    render(<RetainedActivityInspector selection={selected} read={source}
      sourceGeneration={() => 9} canRead={() => true} />);
    expect(source).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Inspect retained activity" }));
    expect(await screen.findAllByText(/candidate recorded:/)).toHaveLength(2);
    expect(screen.getByText(/not live tool streaming or private model reasoning/)).toBeTruthy();
    expect(source).toHaveBeenCalledTimes(1);
    expect(source).toHaveBeenCalledWith(expect.objectContaining(selected));
  });
  it("cannot read without the original source or verified viewer permission", () => {
    const source = read();
    render(<RetainedActivityInspector selection={selected} read={source}
      sourceGeneration={() => 1} canRead={() => false} />);
    expect(screen.getByRole("button", { name: "Inspect retained activity" })).toHaveProperty("disabled", true);
    expect(source).not.toHaveBeenCalled();
  });
  it("drops already displayed private rows on viewer revocation, generation or Attempt switch", async () => {
    const source = vi.fn(async () => decodeRetainedActivity(raw(), selected));
    let enrolled = true, generation = 41;
    const canRead = () => enrolled;
    const sourceGeneration = () => generation;
    const { rerender } = render(<RetainedActivityInspector
      selection={selected} read={source} sourceGeneration={sourceGeneration} canRead={canRead} />);
    fireEvent.click(screen.getByRole("button", { name: "Inspect retained activity" }));
    expect(await screen.findAllByText(/candidate recorded:/)).toHaveLength(2);

    enrolled = false;
    rerender(<RetainedActivityInspector
      selection={selected} read={source} sourceGeneration={sourceGeneration} canRead={canRead} />);
    expect(screen.queryByText(/candidate recorded:/)).toBeNull();
    expect(screen.getByRole("button", { name: "Inspect retained activity" })).toHaveProperty("disabled", true);

    enrolled = true;
    rerender(<RetainedActivityInspector
      selection={selected} read={source} sourceGeneration={sourceGeneration} canRead={canRead} />);
    // Revocation is sticky even if the original source fails to rotate generation.
    expect(screen.queryByText(/candidate recorded:/)).toBeNull();
    generation++;
    rerender(<RetainedActivityInspector
      selection={selected} read={source} sourceGeneration={sourceGeneration} canRead={canRead} />);
    expect(screen.queryByText(/candidate recorded:/)).toBeNull();

    rerender(<RetainedActivityInspector
      selection={{ ...selected, attempt_id: "ATT-" + "f".repeat(32) }}
      read={source} sourceGeneration={sourceGeneration} canRead={canRead} />);
    expect(screen.queryByText(/candidate recorded:/)).toBeNull();
    expect(source).toHaveBeenCalledTimes(1);
  });
  it("revocation drops delayed metadata before display", async () => {
    let release!: (result: ActivityRead) => void;
    const source = vi.fn(() => new Promise<ActivityRead>(resolve => { release = resolve; }));
    let generation = 6;
    const { rerender } = render(<RetainedActivityInspector selection={selected} read={source}
      sourceGeneration={() => generation} canRead={() => true} />);
    fireEvent.click(screen.getByRole("button", { name: "Inspect retained activity" }));
    generation = 7;
    release(decodeRetainedActivity(raw(), selected));
    await waitFor(() => expect(screen.queryByText(/candidate recorded:/)).toBeNull());
    rerender(<RetainedActivityInspector selection={{ ...selected, attempt_id: "ATT-" + "f".repeat(32) }}
      read={source} sourceGeneration={() => generation} canRead={() => true} />);
    expect(screen.queryByText(/candidate recorded:/)).toBeNull();
  });
  it("correctly renders unavailable and does not synthesize idle workers", async () => {
    const source = vi.fn(async () => decodeRetainedActivity(unavailable(), selected));
    render(<RetainedActivityInspector selection={selected} read={source}
      sourceGeneration={() => 1} canRead={() => true} />);
    fireEvent.click(screen.getByRole("button", { name: "Inspect retained activity" }));
    expect(await screen.findByText(/No authorized activity available/)).toBeTruthy();
    expect(screen.queryByText(/candidate recorded:/)).toBeNull();
  });
});

describe("same MissionHost source generation, no parallel bearer custody", () => {
  it("returns no port if the original raw client did not mount the activity reader", () => {
    const stub: any = {
      getState: () => ({status:"signed_in",acquisition:true,content:false,reason:null}),
      invalidationGeneration: () => 7, subscribe: () => () => {},
      signIn: async () => {}, signOut: async () => {},
      readPrograms: async () => null, readWork: async () => null,
      readMission: async () => null, readCurrentWindow: async () => null,
    };
    expect(bindMissionHost(stub).readRetainedActivity).toBeUndefined();
  });
  it("stale generation invalidation rejects the original pending response", async () => {
    let sourceEpoch = 8, release!: (v: unknown) => void;
    const stub: any = {
      getState: () => ({status:"signed_in",acquisition:true,content:false,reason:null}),
      invalidationGeneration: () => sourceEpoch,
      subscribe: () => () => {}, signIn: async () => {}, signOut: async () => {},
      readPrograms: async () => null, readWork: async () => null,
      readMission: async () => null, readCurrentWindow: async () => null,
      readRetainedActivity: () => new Promise(resolve => { release = resolve; }),
    };
    const host = bindMissionHost(stub);
    const pending = host.readRetainedActivity!({ ...selected, signal: new AbortController().signal });
    sourceEpoch++;
    release(raw());
    await expect(pending).rejects.toThrow("READ_CANCELLED");
  });
});

describe("native Tauri retained-activity Workspace source", () => {
  const signedIn = { status: "signed_in", reason: null, acquisition: true, content: false };
  const signedOut = { status: "signed_out", reason: null, acquisition: false, content: false };
  it("invokes precisely one original four-selector reader and decodes a closed DTO", async () => {
    const calls: Array<{ command: string; args: unknown }> = [];
    let readCalls = 0;
    const invoke = <T,>(command: string, args?: Record<string, unknown>): Promise<T> => {
      calls.push({ command, args });
      if (command === "executive_auth_status") return Promise.resolve({ generation: 0, available: false } as T);
      if (command === "auth_status") return Promise.resolve(signedIn as T);
      if (command === "read_retained_activity") { readCalls++; return Promise.resolve(raw() as T); }
      return Promise.reject(new Error("UNEXPECTED_NATIVE_COMMAND"));
    };
    const client = await createNativeClient(invoke, async () => () => {});
    const host = bindMissionHost(client);
    const decoded = await host.readRetainedActivity!({
      ...selected, signal: new AbortController().signal,
    });
    expect(calls.at(-1)).toEqual({
      command: "read_retained_activity", args: { selection: selected },
    });
    expect(readCalls).toBe(1);
    expect(decoded.availability).toBe("AVAILABLE");
    if (decoded.availability === "AVAILABLE") {
      expect(decoded.rows[0].category).toBe("TOOL_ACTIVITY");
      expect(Object.keys(decoded.rows[0])).toEqual([
        "candidate_event_id", "turn_id", "ordinal_in_candidate", "category",
        "candidate_recorded_at",
      ]);
    }
    await expect(host.readRetainedActivity!({
      ...selected, attempt_id: "ATT-FOREIGN",
      signal: new AbortController().signal,
    })).rejects.toThrow("ACTIVITY_SELECTION_INVALID");
    expect(readCalls).toBe(1);
  });

  it("drops late Tauri data across the original logged-out generation", async () => {
    const calls: string[] = [];
    let authListener!: (message: { payload: unknown }) => void;
    let release!: (body: unknown) => void;
    const invoke = <T,>(command: string): Promise<T> => {
      calls.push(command);
      if (command === "executive_auth_status") return Promise.resolve({ generation: 0, available: false } as T);
      if (command === "auth_status") return Promise.resolve(signedIn as T);
      if (command === "read_retained_activity") return new Promise<T>(resolve => {
        release = body => resolve(body as T);
      });
      return Promise.reject(new Error("UNEXPECTED_NATIVE_COMMAND"));
    };
    const client = await createNativeClient(invoke, async (event, listener) => {
      if (event === "mastermind-auth-state") authListener = listener;
      return () => {};
    });
    const host = bindMissionHost(client);
    const signal = new AbortController().signal;
    const pending = host.readRetainedActivity!({ ...selected, signal });
    expect(calls.at(-1)).toBe("read_retained_activity");
    authListener({ payload: signedOut });
    release(raw());
    await expect(pending).rejects.toThrow("READ_CANCELLED");
    expect(host.auth?.getState().status).toBe("signed_out");
  });
});
