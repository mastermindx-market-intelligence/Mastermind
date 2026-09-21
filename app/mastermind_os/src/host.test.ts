import { describe, expect, it, vi } from "vitest";
import {
  bindMissionHost,
  createNativeClient,
  type RawClient,
  type AuthState,
} from "./host";
import current from "./fixtures/mission-v2-current-128c46f6.json";
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
  it("does not unwrap arbitrary Programs or content responses", async () => {
    const e = raw(),
      host = bindMissionHost(e.client),
      signal = new AbortController().signal;
    await expect(host.readPrograms!({ signal })).rejects.toThrow();
    await expect(host.readCurrentWindow!({ signal })).rejects.toThrow(
      "WINDOW_RESPONSE_INVALID",
    );
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
});
