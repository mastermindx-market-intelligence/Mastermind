import { beforeEach, describe, expect, it, vi } from "vitest";
import { bindMissionHost, createNativeClient, type RawClient } from "./host";
import {
  decodeResultReferencesEnvelope,
  type ResultReferencesDocument,
} from "./result-references";

// The closed result-references decoder is owned by its own module; this
// focused host test observes the exact body and selection the typed host
// hands to it without re-implementing that decoder here.
vi.mock("./result-references", () => ({
  decodeResultReferencesEnvelope: vi.fn(),
}));

const decode = vi.mocked(decodeResultReferencesEnvelope);

const signed = {
  status: "signed_in" as const,
  reason: null,
  acquisition: true,
  content: true,
};
const signedOut = {
  status: "signed_out" as const,
  reason: null,
  acquisition: false,
  content: false,
};
const selection = { workRef: "WS:ONE", rootJobId: "JOB-7" };
const unavailableBody = {
  schema: "mastermind.workspace_result_references.v1",
  selection: { work_ref: "WS:ONE", root_job_id: "JOB-7" },
  availability: "UNAVAILABLE",
  reason_codes: ["SOURCE_UNAVAILABLE"],
  index: null,
  source_observation: {
    schema: "mastermind.workspace_source_observation.v1",
    state: "UNKNOWN",
    selection: { work_ref: "WS:ONE", root_job_id: "JOB-7" },
    control_room: null,
    runtime: null,
  },
  catalogue: { generated_at: null, freshness: "UNKNOWN" },
};
const unavailableDocument = {
  ...unavailableBody,
  selection: { workRef: "WS:ONE", rootJobId: "JOB-7" },
} as unknown as ResultReferencesDocument;

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

async function setup(
  transport: (command: string, args?: Record<string, unknown>) => Promise<unknown>,
) {
  const invoke = vi.fn((command: string, _args?: Record<string, unknown>) =>
    command === "auth_status"
      ? Promise.resolve(signed)
      : command === "executive_auth_status"
        ? Promise.resolve({ generation: 0, available: false })
        : transport(command),
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

const minimalClient = (overrides: Partial<RawClient> = {}): RawClient => ({
  getState: () => ({ ...signed }),
  subscribe: () => () => {},
  signIn: async () => ({}),
  signOut: async () => ({}),
  readPrograms: async () => ({}),
  readWork: async () => ({}),
  readMission: async () => ({}),
  readCurrentWindow: async () => ({}),
  ...overrides,
});

const read = (client: RawClient, signal = new AbortController().signal) =>
  bindMissionHost(client).readResultReferences!({ ...selection, signal });

beforeEach(() => {
  decode.mockReset();
});

describe("typed retained-result reference host port", () => {
  it("issues the fixed two-field native route and fully decodes the body", async () => {
    const body = { ...unavailableBody };
    const document = unavailableDocument;
    decode.mockReturnValue(document);
    const { client, invoke } = await setup(() => Promise.resolve(body));
    await expect(read(client)).resolves.toBe(document);
    expect(invoke.mock.calls.map((call) => call[0])).toEqual([
      "executive_auth_status",
      "auth_status",
      "read_result_references",
    ]);
    // The fixed request carries exactly the two root selection keys; no job,
    // attempt, digest or caller-supplied URL ever reaches the native command.
    expect(invoke.mock.calls[2][1]).toEqual({
      selection: { work_ref: "WS:ONE", root_job_id: "JOB-7" },
    });
    expect(decode).toHaveBeenCalledTimes(1);
    expect(decode.mock.calls[0][0]).toEqual(body);
    expect(decode.mock.calls[0][1]).toEqual(selection);
  });

  it("drops an extra caller selector before the fixed read", async () => {
    decode.mockReturnValue(unavailableDocument);
    const { client, invoke } = await setup(() => Promise.resolve(unavailableBody));
    const request = {
      ...selection,
      jobId: "JOB-9",
      attemptId: "ATT-11111111111111111111111111111111",
      resultEnvelopeDigest: "a".repeat(64),
    } as typeof selection;
    await expect(
      bindMissionHost(client).readResultReferences!({ ...request, signal: new AbortController().signal }),
    ).resolves.toBe(unavailableDocument);
    expect(invoke.mock.calls[2][1]).toEqual({
      selection: { work_ref: "WS:ONE", root_job_id: "JOB-7" },
    });
  });

  it("rejects an invalid selection before any native command or decode", async () => {
    const { client, invoke } = await setup(() => Promise.resolve(unavailableBody));
    const host = bindMissionHost(client);
    await expect(
      host.readResultReferences!({
        workRef: "WS:lower",
        rootJobId: "JOB-7",
        signal: new AbortController().signal,
      }),
    ).rejects.toThrow("SELECTION_INVALID");
    await expect(
      host.readResultReferences!({
        workRef: "WS:ONE",
        rootJobId: "JOB-x",
        signal: new AbortController().signal,
      }),
    ).rejects.toThrow("SELECTION_INVALID");
    expect(invoke.mock.calls.map((call) => call[0])).toEqual([
      "executive_auth_status",
      "auth_status",
    ]);
    expect(decode).not.toHaveBeenCalled();
  });

  it("keeps the typed unavailable body a decoded document, not an error", async () => {
    decode.mockReturnValue(unavailableDocument);
    const { client } = await setup(() => Promise.resolve(unavailableBody));
    // The typed allowed 503 body for this route is returned exactly as the
    // decoder produced it; the host never converts UNAVAILABLE into a throw.
    await expect(read(client)).resolves.toBe(unavailableDocument);
  });

  it("reports the missing typed port without a native command", async () => {
    const client = minimalClient();
    await expect(read(client)).rejects.toThrow("RESULT_REFERENCES_UNAVAILABLE");
    expect(decode).not.toHaveBeenCalled();
  });

  it("rejects a null decode as an invalid response", async () => {
    decode.mockReturnValue(null);
    const { client } = await setup(() => Promise.resolve({ schema: "other" }));
    await expect(read(client)).rejects.toThrow("RESULT_REFERENCES_RESPONSE_INVALID");
  });

  it("settles an in-flight read on abort and never decodes the late body", async () => {
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
      expect(decode).not.toHaveBeenCalled();
      hold.resolve(unavailableBody);
      await done;
      expect(decode).not.toHaveBeenCalled();
      expect(invoke.mock.calls.map((call) => call[0])).toEqual([
        "executive_auth_status",
        "auth_status",
        "read_result_references",
      ]);
    } finally {
      hold.resolve(unavailableBody);
      await done;
    }
  });

  it("settles an in-flight read when the auth generation advances", async () => {
    const hold = deferred();
    const { client, notify } = await setup(() => hold.promise);
    let outcome = "PENDING";
    const done = read(client).then(
      () => {
        outcome = "RESOLVED";
      },
      (error: Error) => {
        outcome = error.message;
      },
    );
    await flush();
    notify({ ...signedOut });
    await flush();
    try {
      expect(outcome).toBe("READ_CANCELLED");
      expect(decode).not.toHaveBeenCalled();
    } finally {
      hold.resolve(unavailableBody);
      await done;
    }
  });

  it("never repopulates an aborted root from its late response", async () => {
    const first = deferred();
    let calls = 0;
    const { client, invoke } = await setup(() =>
      ++calls === 1 ? first.promise : Promise.resolve(unavailableBody),
    );
    decode.mockReturnValue(unavailableDocument);
    const controller = new AbortController();
    let firstOutcome = "PENDING";
    const stale = read(client, controller.signal).then(
      () => {
        firstOutcome = "RESOLVED";
      },
      (error: Error) => {
        firstOutcome = error.message;
      },
    );
    controller.abort();
    await flush();
    const fresh = await read(client);
    expect(fresh).toBe(unavailableDocument);
    expect(decode).toHaveBeenCalledTimes(1);
    expect(firstOutcome).toBe("READ_CANCELLED");
    expect(invoke.mock.calls.map((call) => call[0])).toEqual([
      "executive_auth_status",
      "auth_status",
      "read_result_references",
      "read_result_references",
    ]);
    first.resolve(unavailableBody);
    await stale;
    expect(decode).toHaveBeenCalledTimes(1);
  });
});
