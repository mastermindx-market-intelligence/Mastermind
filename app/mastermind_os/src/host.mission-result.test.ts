import { beforeAll, describe, expect, it, vi, type Mock } from "vitest";
import { bindMissionHost, createNativeClient, type AuthState, type RawClient } from "./host";
import { decodeMissionResultBytes, type MissionResultDocument } from "./mission-result";
import { normalizeResultSelection, type ResultSelection } from "./result";

const signed: AuthState = { status: "signed_in", reason: null, acquisition: true, content: true };
let pairBody: unknown;
let selection: ResultSelection;

beforeAll(async () => {
  // @ts-expect-error node:fs/promises is resolved by the vitest worker.
  const fs = (await import("node:fs/promises")) as { readFile(path: URL): Promise<Uint8Array> };
  const bytes = new Uint8Array(await fs.readFile(new URL(
    "./meta-ceo/fixtures/mission-result-producer/actual-pair.json",
    import.meta.url,
  )));
  pairBody = JSON.parse(new TextDecoder().decode(bytes));
  const wire = (pairBody as { selection: Record<string, string> }).selection;
  const normalized = normalizeResultSelection({
    workRef: wire.work_ref,
    rootJobId: wire.root_job_id,
    jobId: wire.job_id,
    attemptId: wire.attempt_id,
    resultEnvelopeDigest: wire.result_envelope_digest,
  });
  if (!normalized) throw new Error("producer selection is not normalizable");
  selection = normalized;
  const decoded = decodeMissionResultBytes(bytes, selection);
  if (!decoded.ok) throw new Error("producer bytes failed before the host test");
});

function request(signal = new AbortController().signal) {
  return { ...selection, signal };
}

function client(options: { generation?: () => number; read?: RawClient["readMissionResult"] } = {}) {
  let state = signed;
  const listeners = new Set<(next: AuthState) => void>();
  let generation = 1;
  const read = (options.read ?? vi.fn(async () => structuredClone(pairBody))) as Mock;
  const raw: RawClient = {
    getState: () => state,
    invalidationGeneration: options.generation ?? (() => generation),
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    signIn: async () => {},
    signOut: async () => {},
    readPrograms: async () => ({}),
    readWork: async () => ({}),
    readMission: async () => ({}),
    readCurrentWindow: async () => ({}),
    readMissionResult: read,
  };
  return {
    raw,
    read,
    listeners,
    setState(next: AuthState) {
      state = next;
      for (const listener of listeners) listener(next);
    },
    bumpGeneration() {
      generation += 1;
      for (const listener of listeners) listener(state);
    },
  };
}

describe("optional compound Mission/Result host read", () => {
  it("mounts the typed read only when the raw method and invalidation generation both exist", () => {
    const mounted = client();
    expect(bindMissionHost(mounted.raw).readMissionResult).toEqual(expect.any(Function));
    const noGeneration: RawClient = { ...mounted.raw, invalidationGeneration: undefined };
    expect(bindMissionHost(noGeneration).readMissionResult).toBeUndefined();
    const noMethod: RawClient = { ...mounted.raw, readMissionResult: undefined };
    expect(bindMissionHost(noMethod).readMissionResult).toBeUndefined();
  });

  it("does not register a native compound command", async () => {
    const commands: string[] = [];
    const native = await createNativeClient((async (command: string) => {
      commands.push(command);
      if (command === "auth_status")
        return { status: "signed_out", reason: null, acquisition: false, content: false };
      throw new Error(`unexpected command ${command}`);
    }) as never, async () => () => {});
    expect(native.readMissionResult).toBeUndefined();
    expect(bindMissionHost(native).readMissionResult).toBeUndefined();
    expect(commands).not.toContain("read_mission_result");
  });

  it("decodes the unchanged producer body and normalizes the selector apart from AbortSignal", async () => {
    const e = client();
    const host = bindMissionHost(e.raw);
    const decoded = await host.readMissionResult!(request());
    expect(decoded.availability).toBe("AVAILABLE");
    if (decoded.availability !== "AVAILABLE") return;
    expect(decoded.roleResult.result?.review?.verdict).toBe("reject");
    expect(e.read).toHaveBeenCalledTimes(1);
    const passed = e.read.mock.calls[0][0] as ResultSelection & { signal?: AbortSignal };
    expect(passed.signal).toEqual(expect.any(AbortSignal));
    expect(Object.keys(passed).filter((key) => key !== "signal").sort()).toEqual([
      "attemptId", "jobId", "resultEnvelopeDigest", "rootJobId", "workRef",
    ]);
    await expect(host.readMissionResult!({ ...request(), extra: true } as never)).rejects.toThrow("SELECTION_INVALID");
    expect(e.read).toHaveBeenCalledTimes(1);
  });

  it("makes no raw call while signed out", async () => {
    const e = client();
    e.setState({ status: "signed_out", reason: null, acquisition: false, content: false });
    await expect(bindMissionHost(e.raw).readMissionResult!(request())).rejects.toThrow("READ_CANCELLED");
    expect(e.read).not.toHaveBeenCalled();
  });

  it("withholds the body when the displayed auth state stays the same and the generation changes", async () => {
    let release!: (value: unknown) => void;
    const e = client({ read: vi.fn(() => new Promise((resolve) => { release = resolve; })) });
    const host = bindMissionHost(e.raw);
    const pending = host.readMissionResult!(request());
    const assertion = expect(pending).rejects.toThrow("READ_CANCELLED");
    e.bumpGeneration();
    expect(e.raw.getState()).toEqual(signed);
    release(structuredClone(pairBody));
    await assertion;
  });

  it.each(["abort", "methodReplacement"])("withholds an abort-ignoring read after %s", async (event) => {
    let release!: (value: unknown) => void;
    const e = client({ read: vi.fn(() => new Promise((resolve) => { release = resolve; })) });
    const host = bindMissionHost(e.raw);
    const abort = new AbortController();
    const pending = host.readMissionResult!({ ...selection, signal: abort.signal });
    const assertion = expect(pending).rejects.toThrow("READ_CANCELLED");
    if (event === "abort") abort.abort();
    if (event === "methodReplacement") e.raw.readMissionResult = async () => structuredClone(pairBody);
    release(structuredClone(pairBody));
    await assertion;
  });

  it("does not turn an invalid compound body into a nested result document", async () => {
    const e = client({ read: vi.fn(async () => ({ ...structuredClone(pairBody) as object, extra: true })) });
    await expect(bindMissionHost(e.raw).readMissionResult!(request())).rejects.toThrow("MISSION_RESULT_RESPONSE_INVALID");
    const unavailable = client({
      read: vi.fn(async () => ({
        schema: "mastermind.workspace_mission_result.v1",
        selection: (pairBody as { selection: unknown }).selection,
        availability: "UNAVAILABLE",
        reason_codes: ["SOURCE_UNAVAILABLE"],
        mission: null,
        role_result: null,
      })),
    });
    const decoded: MissionResultDocument = await bindMissionHost(unavailable.raw).readMissionResult!(request());
    expect(decoded.availability).toBe("UNAVAILABLE");
    expect(decoded.roleResult).toBeNull();
    expect(decoded.mission).toBeNull();
  });
});
