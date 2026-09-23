import { describe, expect, it, vi } from "vitest";
import {
  bindMissionHost,
  createNativeClient,
  type RawClient,
  type AuthState,
} from "./host";
import current from "./fixtures/mission-v2-current-128c46f6.json";
import v3Current17 from "./fixtures/mission-v3-design-current-17-slots.json";
import resultAvailable from "./fixtures/result-design-available-at-16384-socket-bytes.json";
const signed: AuthState = {
  status: "signed_in",
  reason: null,
  acquisition: true,
  content: true,
};
const out: AuthState = {
  status: "signed_out",
  reason: null,
  acquisition: false,
  content: false,
};
const deferred = <T>() => {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((yes) => (resolve = yes));
  return { promise, resolve };
};
function raw() {
  let listener = (s: AuthState) => {};
  const client: RawClient = {
    getState: () => signed,
    subscribe(fn) {
      listener = fn;
      return () => {};
    },
    signIn: vi.fn(async () => {}),
    signOut: vi.fn(async () => {}),
    readPrograms: vi.fn(async () => ({})),
    readMission: vi.fn(async () => current),
    readMissionV3: vi.fn(async () => v3Current17),
    readResult: vi.fn(async () => resultAvailable),
    readCurrentWindow: vi.fn(async () => ({})),
  };
  return { client, notify: (s: AuthState) => listener(s) };
}
describe("installed typed host", () => {
  it("consumes actual Mission v2 and maps the exact selected pair", async () => {
    const e = raw(),
      host = bindMissionHost(e.client);
    const signal = new AbortController().signal;
    expect(
      (
        (await host.readMission!({
          workRef: "WS:ONE",
          rootJobId: "JOB-1",
          signal,
        })) as typeof current
      ).read_state.state,
    ).toBe("CURRENT");
    expect(e.client.readMission).toHaveBeenCalledWith({
      work_ref: "WS:ONE",
      root_job_id: "JOB-1",
      signal,
    });
    await expect(
      host.readMission!({ workRef: "WS:OTHER", rootJobId: "JOB-1", signal }),
    ).rejects.toThrow("MISSION_RESPONSE_INVALID");
  });
  it("consumes the fixed readMissionV3 envelope from the index schema", async () => {
    const e = raw(),
      host = bindMissionHost(e.client);
    const signal = new AbortController().signal;
    const decoded = await host.readMissionV3!({
      workRef: "WS:B5",
      rootJobId: "JOB-100",
      signal,
    });
    expect(decoded).toMatchObject({
      schema: "mastermind.mission_workspace.v3",
    });
    expect(decoded).toMatchObject({
      result_refs: { refs: expect.any(Array), availability: "AVAILABLE" },
    });
    expect(e.client.readMissionV3).toHaveBeenCalledWith({
      workRef: "WS:B5",
      rootJobId: "JOB-100",
      signal,
    });
  });
  it("consumes the fixed readResult envelope and preserves source failure without mislabeling cancellation", async () => {
    const e = raw(),
      host = bindMissionHost(e.client);
    const signal = new AbortController().signal;
    const ready = await host.readResult!({
      workRef: "WS:DESIGN",
      rootJobId: "JOB-001",
      jobId: "JOB-004",
      attemptId: "ATT-44444444444444444444444444444444",
      resultEnvelopeDigest:
        "390cfeea0f8476caa22dd263a243acf66216ea14d560ad6c908f668f59052a3a",
      signal,
    });
    expect(ready).toMatchObject({ availability: "AVAILABLE" });
    e.client.readResult = vi.fn(async () => {
      throw new Error("READ_FAILED");
    });
    const err = await host.readResult!({
      workRef: "WS:DESIGN",
      rootJobId: "JOB-001",
      jobId: "JOB-004",
      attemptId: "ATT-44444444444444444444444444444444",
      resultEnvelopeDigest:
        "390cfeea0f8476caa22dd263a243acf66216ea14d560ad6c908f668f59052a3a",
      signal,
    }).catch((e: Error) => e);
    expect(err).toBeInstanceOf(Error);
    expect((err as Error).message).toBe("READ_FAILED");
  });
  it("does not unwrap arbitrary Programs or content responses", async () => {
    const e = raw(),
      host = bindMissionHost(e.client),
      signal = new AbortController().signal;
    await expect(host.readPrograms!({ signal })).rejects.toThrow();
    await expect(host.readCurrentWindow!({ signal })).rejects.toThrow(
      "WINDOW_RESPONSE_INVALID",
    );
  });
  it("exposes one invalidation generation that spans sequential mission and window reads", async () => {
    const e = raw(),
      host = bindMissionHost(e.client);
    expect(host.invalidationGeneration?.()).toBe(0);
    const first = host.invalidationGeneration?.();
    e.notify(out);
    const afterAuth = host.invalidationGeneration?.();
    expect(afterAuth).toBeGreaterThan(first ?? -1);
    const missionHold = deferred<unknown>();
    const windowHold = deferred<unknown>();
    e.client.readMissionV3 = () => missionHold.promise;
    e.client.readCurrentWindow = () => windowHold.promise;
    const started = host.invalidationGeneration?.() ?? 0;
    const mission = host.readMissionV3!({
      workRef: "WS:B5",
      rootJobId: "JOB-100",
      signal: new AbortController().signal,
    });
    e.notify(signed);
    missionHold.resolve(v3Current17);
    await expect(mission).rejects.toThrow("READ_CANCELLED");
    expect(host.invalidationGeneration?.()).not.toBe(started);
    const windowStarted = host.invalidationGeneration?.() ?? 0;
    const windowRead = host.readCurrentWindow!({
      signal: new AbortController().signal,
    });
    windowHold.resolve({
      schema: "mastermind.workspace.window_read_candidate.v1",
    });
    await expect(windowRead).rejects.toThrow("WINDOW_RESPONSE_INVALID");
    expect(windowStarted).not.toBe(started);
  });
  it.each(["logout", "auth", "abort"])(
    "fences an abort-ignoring late response after %s",
    async (kind) => {
      const e = raw(),
        pending = deferred<unknown>();
      e.client.readMission = () => pending.promise;
      const host = bindMissionHost(e.client),
        controller = new AbortController();
      const read = host.readMission!({
        workRef: "WS:ONE",
        rootJobId: "JOB-1",
        signal: controller.signal,
      });
      if (kind === "logout") await host.auth!.signOut();
      else if (kind === "auth") e.notify(out);
      else controller.abort();
      pending.resolve(current);
      await expect(read).rejects.toThrow("READ_CANCELLED");
    },
  );
});
describe("native fixed command adapter", () => {
  it("has only fixed commands and drops stale sign-in command replies", async () => {
    const pending = deferred<unknown>();
    const invoke = vi.fn(async (command: string) =>
      command === "sign_in"
        ? pending.promise
        : command === "sign_out"
          ? out
          : signed,
    );
    const client = await createNativeClient(
      invoke as never,
      async () => () => {},
    );
    const signin = client.signIn();
    await client.signOut();
    pending.resolve(signed);
    await signin;
    expect(client.getState()).toEqual(out);
    expect(invoke.mock.calls.map((c) => c[0])).toEqual([
      "auth_status",
      "sign_in",
      "sign_out",
    ]);
  });
  it("denies a late native read after an authentication event and validates the event shape", async () => {
    const pending = deferred<unknown>();
    let listener!: (e: { payload: unknown }) => void;
    const invoke = vi.fn(async (command: string) =>
      command === "auth_status" ? signed : pending.promise,
    );
    const client = await createNativeClient(
      invoke as never,
      async (_event, fn) => {
        listener = fn;
        return () => {};
      },
    );
    const read = client.readMission({
      work_ref: "WS:ONE",
      root_job_id: "JOB-1",
      signal: new AbortController().signal,
    });
    expect(invoke).toHaveBeenLastCalledWith("read_mission", {
      selection: { work_ref: "WS:ONE", root_job_id: "JOB-1" },
    });
    listener({ payload: out });
    pending.resolve(current);
    await expect(read).rejects.toThrow("READ_CANCELLED");
    listener({ payload: { ...signed, token: "forbidden" } });
    expect(client.getState()).toEqual(out);
  });
  it("routes the fixed native readMissionV3/readResult commands and refuses arbitrary URL selectors", async () => {
    let listener!: (e: { payload: unknown }) => void;
    let lastMissionV3: unknown, lastResult: unknown;
    const invoke = vi.fn(async (command: string, args: unknown) => {
      if (command === "auth_status") return signed;
      if (command === "read_mission_v3") {
        lastMissionV3 = args;
        return v3Current17;
      }
      if (command === "read_result") {
        lastResult = args;
        return resultAvailable;
      }
      return {};
    });
    const client = await createNativeClient(
      invoke as never,
      async (_event, fn) => {
        listener = fn;
        return () => {};
      },
    );
    const v3 = await client.readMissionV3!({
      workRef: "WS:B5",
      rootJobId: "JOB-100",
      signal: new AbortController().signal,
    });
    expect(v3).toMatchObject({ schema: "mastermind.mission_workspace.v3" });
    expect(invoke).toHaveBeenCalledWith("read_mission_v3", {
      selection: { work_ref: "WS:B5", root_job_id: "JOB-100" },
    });
    const res = await client.readResult!({
      workRef: "WS:DESIGN",
      rootJobId: "JOB-001",
      jobId: "JOB-004",
      attemptId: "ATT-44444444444444444444444444444444",
      resultEnvelopeDigest:
        "390cfeea0f8476caa22dd263a243acf66216ea14d560ad6c908f668f59052a3a",
      signal: new AbortController().signal,
    });
    expect(res).toMatchObject({ availability: "AVAILABLE" });
    expect(invoke).toHaveBeenCalledWith("read_result", {
      selection: resultAvailable.selection,
    });
    // Only fixed paths and selection-key selectors are accepted
    expect(lastMissionV3).toEqual({
      selection: { work_ref: "WS:B5", root_job_id: "JOB-100" },
    });
    expect((lastResult as { selection: object }).selection).toEqual({
      work_ref: "WS:DESIGN",
      root_job_id: "JOB-001",
      job_id: "JOB-004",
      attempt_id: "ATT-44444444444444444444444444444444",
      result_envelope_digest:
        "390cfeea0f8476caa22dd263a243acf66216ea14d560ad6c908f668f59052a3a",
    });
    await expect(
      client.readMissionV3!({
        workRef: "WS:B5",
        rootJobId: "https://other",
        signal: new AbortController().signal,
      }),
    ).rejects.toThrow("SELECTION_INVALID");
    expect(listener).toBeTypeOf("function");
  });
});
