import { describe, expect, it, vi } from "vitest";
import { bindMissionHost, createNativeClient, type RawClient } from "./host";
import currentMission from "./fixtures/mission-v2-current-128c46f6.json";

const signed = {
  status: "signed_in",
  reason: null,
  acquisition: true,
  content: true,
};
const deferred = () => {
  let resolve!: (value: unknown) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<unknown>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
};
const flush = async () => {
  for (let n = 0; n < 12; n++) await Promise.resolve();
};
type Read = (client: RawClient, signal: AbortSignal) => Promise<unknown>;
const reads: [string, Read][] = [
  ["read_programs", (c, signal) => c.readPrograms({ signal })],
  ["read_work", (c, signal) => c.readWork({ signal })],
  [
    "read_mission",
    (c, signal) =>
      c.readMission({ work_ref: "WS:ONE", root_job_id: "JOB-1", signal }),
  ],
  [
    "read_mission_v3",
    (c, signal) =>
      c.readMissionV3!({ workRef: "WS:ONE", rootJobId: "JOB-1", signal }),
  ],
  [
    "read_result",
    (c, signal) =>
      c.readResult!({
        workRef: "WS:ONE",
        rootJobId: "JOB-1",
        jobId: "JOB-2",
        attemptId: "ATT-11111111111111111111111111111111",
        resultEnvelopeDigest: "a".repeat(64),
        signal,
      }),
  ],
  ["read_current_window", (c, signal) => c.readCurrentWindow({ signal })],
];
async function setup(transport: (command: string) => Promise<unknown>) {
  const invoke = vi.fn((command: string) =>
    command === "auth_status" ? Promise.resolve(signed) : command === "executive_auth_status" ? Promise.resolve({ generation: 0, available: false }) : transport(command),
  );
  let notify = (_payload: unknown) => {};
  const client = await createNativeClient(
    invoke as never,
    async (_event, listener) => {
      notify = (payload) => listener({ payload });
      return () => {};
    },
  );
  return { client, invoke, notify };
}

describe("native read cancellation settlement", () => {
  it.each(reads)(
    "settles %s immediately even if the native read never returns",
    async (command, read) => {
      const hold = deferred();
      const { client, invoke } = await setup(() => hold.promise);
      const controller = new AbortController();
      let outcome = "PENDING";
      const done = read(client, controller.signal).then(
        () => {
          outcome = "RESOLVED";
        },
        (error: Error) => {
          outcome = error.message;
        },
      );
      controller.abort();
      await flush();
      try {
        expect(outcome).toBe("READ_CANCELLED");
        expect(invoke.mock.calls.map((call) => call[0])).toEqual([
          "executive_auth_status", "auth_status",
          command,
        ]);
      } finally {
        hold.resolve({});
        await done;
      }
    },
  );

  it.each(reads)(
    "does not invoke %s for an already-aborted request",
    async (_command, read) => {
      const { client, invoke } = await setup(async () => ({}));
      const controller = new AbortController();
      controller.abort();
      await expect(read(client, controller.signal)).rejects.toThrow(
        "READ_CANCELLED",
      );
      expect(invoke.mock.calls.map((call) => call[0])).toEqual(["executive_auth_status", "auth_status"]);
    },
  );

  it.each(["resolve", "reject", "abort"])(
    "removes the abort listener after %s",
    async (completion) => {
      const hold = deferred();
      const { client } = await setup(() => hold.promise);
      const controller = new AbortController();
      const added = vi.spyOn(controller.signal, "addEventListener");
      const removed = vi.spyOn(controller.signal, "removeEventListener");
      const done = client
        .readPrograms({ signal: controller.signal })
        .catch((error) => error);
      if (completion === "resolve") hold.resolve({});
      else if (completion === "reject") hold.reject(new Error("READ_FAILED"));
      else controller.abort();
      await flush();
      try {
        expect(added).toHaveBeenCalledTimes(1);
        expect(added.mock.calls[0][0]).toBe("abort");
        expect(removed).toHaveBeenCalledTimes(1);
        expect(removed.mock.calls[0][0]).toBe("abort");
        expect(removed.mock.calls[0][1]).toBe(added.mock.calls[0][1]);
      } finally {
        hold.resolve({});
        await done;
      }
    },
  );

  it("handles abort occurring inside invoke and consumes the late transport rejection", async () => {
    const hold = deferred();
    const controller = new AbortController();
    const { client, invoke } = await setup(() => {
      controller.abort();
      return hold.promise;
    });
    let outcome = "PENDING";
    let completions = 0;
    const done = client.readPrograms({ signal: controller.signal }).then(
      () => {
        outcome = "RESOLVED";
        completions++;
      },
      (error: Error) => {
        outcome = error.message;
        completions++;
      },
    );
    await flush();
    try {
      expect(outcome).toBe("READ_CANCELLED");
    } finally {
      hold.reject(new Error("LATE_NATIVE_FAILURE"));
      await done;
    }
    await flush();
    expect(completions).toBe(1);
    expect(invoke).toHaveBeenCalledTimes(3);
  });

  it("does not cancel or replay a sibling read", async () => {
    const first = deferred();
    const second = deferred();
    let calls = 0;
    const { client, invoke } = await setup(() =>
      ++calls === 1 ? first.promise : second.promise,
    );
    const one = new AbortController();
    const two = new AbortController();
    let firstState = "PENDING";
    let secondState = "PENDING";
    const a = client.readPrograms({ signal: one.signal }).then(
      () => {
        firstState = "RESOLVED";
      },
      (e: Error) => {
        firstState = e.message;
      },
    );
    const b = client.readPrograms({ signal: two.signal }).then(
      () => {
        secondState = "RESOLVED";
      },
      (e: Error) => {
        secondState = e.message;
      },
    );
    one.abort();
    await flush();
    try {
      expect(firstState).toBe("READ_CANCELLED");
      expect(secondState).toBe("PENDING");
      second.resolve({});
      await b;
      expect(secondState).toBe("RESOLVED");
      expect(invoke.mock.calls.map((call) => call[0])).toEqual([
        "executive_auth_status", "auth_status",
        "read_programs",
        "read_programs",
      ]);
    } finally {
      first.resolve({});
      second.resolve({});
      await Promise.all([a, b]);
    }
  });

  it("preserves an ordinary native failure and cleans up a synchronous invoke throw", async () => {
    const failure = new Error("READ_FAILED");
    const { client } = await setup(() => {
      throw failure;
    });
    const controller = new AbortController();
    const removed = vi.spyOn(controller.signal, "removeEventListener");
    await expect(
      client.readPrograms({ signal: controller.signal }),
    ).rejects.toBe(failure);
    expect(removed).toHaveBeenCalledTimes(1);
  });
});

describe("native generation cancellation", () => {
  it.each(["auth-event", "same-state-event", "sign-out", "sign-in"])(
    "settles pending reads before a native reply after %s",
    async (kind) => {
      const hold = deferred();
      const { client, notify } = await setup(() => hold.promise);
      let outcome = "PENDING";
      const done = client
        .readPrograms({ signal: new AbortController().signal })
        .then(
          () => {
            outcome = "RESOLVED";
          },
          (error: Error) => {
            outcome = error.message;
          },
        );
      let control: Promise<unknown> = Promise.resolve();
      if (kind === "sign-out") control = client.signOut();
      else if (kind === "sign-in") control = client.signIn();
      else if (kind === "same-state-event") notify({ ...signed });
      else
        notify({
          status: "signed_out",
          reason: null,
          acquisition: false,
          content: false,
        });
      await flush();
      try {
        expect(outcome).toBe("READ_CANCELLED");
      } finally {
        hold.resolve(signed);
        await Promise.all([done, control]);
      }
    },
  );

  it("preserves the refusal of malformed auth events without cancelling valid reads", async () => {
    const hold = deferred();
    const { client, notify } = await setup(() => hold.promise);
    let outcome = "PENDING";
    const done = client
      .readPrograms({ signal: new AbortController().signal })
      .then(
        () => {
          outcome = "RESOLVED";
        },
        (error: Error) => {
          outcome = error.message;
        },
      );
    notify({ status: "signed_out" });
    await flush();
    expect(outcome).toBe("PENDING");
    expect(client.getState()).toEqual(signed);
    hold.resolve({});
    await done;
    expect(outcome).toBe("RESOLVED");
  });

  it("composes native cancellation with a fresh exact Mission read through the real typed host", async () => {
    const first = deferred();
    let reads = 0;
    const { client, invoke } = await setup(() =>
      ++reads === 1 ? first.promise : Promise.resolve(currentMission),
    );
    const host = bindMissionHost(client);
    const controller = new AbortController();
    let oldState = "PENDING";
    const old = host.readMission!({
      workRef: "WS:ONE",
      rootJobId: "JOB-1",
      signal: controller.signal,
    }).then(
      () => {
        oldState = "RESOLVED";
      },
      (error: Error) => {
        oldState = error.message;
      },
    );
    controller.abort();
    await flush();
    try {
      expect(oldState).toBe("READ_CANCELLED");
      const fresh = await host.readMission!({
        workRef: "WS:ONE",
        rootJobId: "JOB-1",
        signal: new AbortController().signal,
      });
      expect(fresh).toMatchObject({
        schema: "mastermind.mission_workspace.v2",
        read_state: { state: "CURRENT" },
      });
      expect(invoke.mock.calls.map((call) => call[0])).toEqual([
        "executive_auth_status", "auth_status",
        "read_mission",
        "read_mission",
      ]);
    } finally {
      first.reject(new Error("LATE_OLD_READ"));
      await old;
    }
  });
});

describe("native auth event wins over delayed control reply", () => {
  it.each(["sign-in", "sign-out"])(
    "keeps the newer native auth state when %s returns late",
    async (kind) => {
      const hold = deferred();
      const { client, notify } = await setup(() => hold.promise);
      const signedOut = {
        status: "signed_out",
        reason: null,
        acquisition: false,
        content: false,
      };
      const pending = kind === "sign-in" ? client.signIn() : client.signOut();
      const newer = kind === "sign-in" ? signedOut : signed;
      notify(newer);
      const observed = client.getState();
      hold.resolve(kind === "sign-in" ? signed : signedOut);
      await pending;
      expect(client.getState()).toEqual(observed);
      expect(client.getState()).toEqual(newer);
    },
  );

  it.each(["sign-in", "sign-out"])(
    "still consumes the current %s reply after a malformed native event",
    async (kind) => {
      const hold = deferred();
      const { client, notify } = await setup(() => hold.promise);
      const signedOut = {
        status: "signed_out",
        reason: null,
        acquisition: false,
        content: false,
      };
      const pending = kind === "sign-in" ? client.signIn() : client.signOut();
      notify({ status: "invalid" });
      const expected = kind === "sign-in" ? signed : signedOut;
      hold.resolve(expected);
      await pending;
      expect(client.getState()).toEqual(expected);
    },
  );
});
