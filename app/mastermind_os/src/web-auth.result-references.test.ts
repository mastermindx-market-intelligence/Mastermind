// @vitest-environment jsdom
// @vitest-environment-options {"url":"https://mcp.mastermind-x.com/os/"}
import { afterEach, describe, expect, it, vi } from "vitest";
import { createWebAuth } from "./web-auth";
import { ORIGIN } from "./public-config";

const jsonResponse = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
const deferred = () => {
  let resolve!: (value: Response) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<Response>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
};
const flush = async () => {
  for (let i = 0; i < 30; i++) await Promise.resolve();
};
const signal = () => new AbortController().signal;
const selection = { workRef: "WS:ONE", rootJobId: "JOB-7" };
const fixedUrl =
  `${ORIGIN}/workspace/result-references/current?work_ref=WS%3AONE&root_job_id=JOB-7`;
const referenceRoute = (url: string) =>
  url.startsWith(`${ORIGIN}/workspace/result-references/current`);

function setup() {
  vi.useFakeTimers();
  let count = 0;
  const popup = {
    location: "",
    closed: false,
    close: vi.fn(function () {
      popup.closed = true;
    }),
  };
  const messages = new Set<(e: MessageEvent) => void>();
  const fetcher = vi.fn<typeof fetch>().mockImplementation(async (input) => {
    const url = String(input);
    if (referenceRoute(url)) return jsonResponse({ unexpected: "read-without-handler" });
    return jsonResponse({
      token_type: "Bearer",
      access_token: "private-token",
      expires_in: 3600,
      scope: new URL(popup.location).searchParams.get("scope"),
    });
  });
  const client = createWebAuth({
    config: {
      executiveResource: null,
      webClientId: "fixture-public-client",
    },
    openPopup: () => popup,
    fetchFn: fetcher,
    crypto: {
      getRandomValues(array: Uint8Array) {
        array.fill(++count);
        return array;
      },
      subtle: { digest: () => Promise.resolve(new ArrayBuffer(32)) },
    } as unknown as Crypto,
    addEventListener: ((_type: string, fn: (e: MessageEvent) => void) =>
      messages.add(fn)) as unknown as typeof window.addEventListener,
    removeEventListener: ((_type: string, fn: (e: MessageEvent) => void) =>
      messages.delete(fn)) as unknown as typeof window.removeEventListener,
  });
  const callback = () => {
    const state = new URL(popup.location).searchParams.get("state");
    for (const listener of [...messages])
      listener({
        source: popup,
        origin: ORIGIN,
        data: {
          type: "mastermind-auth-callback",
          state,
          code: "code-opaque",
        },
      } as unknown as MessageEvent);
  };
  const login = async () => {
    const pending = client.signIn();
    await flush();
    callback();
    await flush();
    callback();
    await pending;
    fetcher.mockClear();
  };
  const reads = () => fetcher.mock.calls.filter(([input]) => referenceRoute(String(input)));
  return { client, fetcher, login, reads };
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  history.replaceState(null, "", "/os/");
});

describe("web retained-result reference read", () => {
  it("issues the fixed GET route with the acquisition READ bearer and exact two-field query", async () => {
    const e = setup();
    await e.login();
    const body = {
      schema: "mastermind.workspace_result_references.v1",
      selection: { work_ref: "WS:ONE", root_job_id: "JOB-7" },
      availability: "AVAILABLE",
      reason_codes: [],
      index: { schema: "mastermind.fabric_result_reference_index.v1" },
      source_observation: { schema: "mastermind.workspace_source_observation.v1" },
      catalogue: { generated_at: "2026-10-31T00:00:00Z", freshness: "STALE" },
    };
    e.fetcher.mockImplementation(async (input) =>
      referenceRoute(String(input)) ? jsonResponse(body) : jsonResponse({}),
    );
    await expect(
      e.client.readResultReferences!({ ...selection, signal: signal() }),
    ).resolves.toEqual(body);
    expect(e.reads()).toHaveLength(1);
    const [url, init] = e.reads()[0] as [string, RequestInit];
    expect(url).toBe(fixedUrl);
    expect(init.method).toBe("GET");
    expect(init.credentials).toBe("omit");
    expect(init.cache).toBe("no-store");
    expect((init.headers as Record<string, string>).Accept).toBe("application/json");
    expect((init.headers as Record<string, string>).Authorization).toBe(
      "Bearer private-token",
    );
  });

  it("never adds a selector, cursor or arbitrary URL beyond the two root fields", async () => {
    const e = setup();
    await e.login();
    e.fetcher.mockImplementation(async (input) =>
      referenceRoute(String(input))
        ? jsonResponse({ schema: "mastermind.workspace_result_references.v1" })
        : jsonResponse({}),
    );
    const request = {
      ...selection,
      jobId: "JOB-9",
      attemptId: "ATT-11111111111111111111111111111111",
      resultEnvelopeDigest: "a".repeat(64),
    } as typeof selection;
    await e.client.readResultReferences!({ ...request, signal: signal() });
    const [url] = e.reads()[0] as [string, RequestInit];
    expect(url).toBe(fixedUrl);
    expect(new URL(url).searchParams.size).toBe(2);
  });

  it("rejects an invalid selection before any request", async () => {
    const e = setup();
    await e.login();
    await expect(
      e.client.readResultReferences!({
        workRef: "WS:lower",
        rootJobId: "JOB-7",
        signal: signal(),
      }),
    ).rejects.toThrow("SELECTION_INVALID");
    await expect(
      e.client.readResultReferences!({
        workRef: "WS:ONE",
        rootJobId: "JOB-nope",
        signal: signal(),
      }),
    ).rejects.toThrow("SELECTION_INVALID");
    expect(e.reads()).toHaveLength(0);
  });

  it("requires the acquisition token before any request", async () => {
    const e = setup();
    await expect(
      e.client.readResultReferences!({ ...selection, signal: signal() }),
    ).rejects.toThrow("TOKEN_REQUIRED");
    expect(e.reads()).toHaveLength(0);
  });

  it("keeps the typed 503 unavailable body for this route's closed schema", async () => {
    for (const [body, outcome] of [
      [
        {
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
        },
        "kept",
      ],
      [
        {
          schema: "mastermind.workspace_role_result.v1",
          availability: "UNAVAILABLE",
        },
        "RESPONSE_INVALID",
      ],
      [
        {
          schema: "mastermind.workspace_result_references.v1",
          availability: "AVAILABLE",
        },
        "RESPONSE_INVALID",
      ],
    ] as const) {
      const e = setup();
      await e.login();
      e.fetcher.mockImplementation(async (input) =>
        referenceRoute(String(input)) ? jsonResponse(body, 503) : jsonResponse({}),
      );
      const pending = e.client.readResultReferences!({ ...selection, signal: signal() });
      if (outcome === "kept") await expect(pending).resolves.toEqual(body);
      else await expect(pending).rejects.toThrow(outcome);
    }
  });

  it("fails closed on 403 and 404 like the retained Result route", async () => {
    for (const status of [403, 404]) {
      const e = setup();
      await e.login();
      e.fetcher.mockImplementation(async (input) =>
        referenceRoute(String(input)) ? jsonResponse({ denied: true }, status) : jsonResponse({}),
      );
      await expect(
        e.client.readResultReferences!({ ...selection, signal: signal() }),
      ).rejects.toThrow("READ_FAILED");
    }
  });

  it("enforces the exact 16KiB body cap", async () => {
    const e = setup();
    await e.login();
    const oversized = {
      schema: "mastermind.workspace_result_references.v1",
      index: { padding: "x".repeat(17_000) },
    };
    e.fetcher.mockImplementation(async (input) =>
      referenceRoute(String(input)) ? jsonResponse(oversized) : jsonResponse({}),
    );
    await expect(
      e.client.readResultReferences!({ ...selection, signal: signal() }),
    ).rejects.toThrow("RESPONSE_TOO_LARGE");
  });

  it("refuses a late response after caller abort even when the fetch fixture ignores cancellation", async () => {
    const e = setup();
    await e.login();
    const hold = deferred();
    e.fetcher.mockImplementation(async (input) =>
      referenceRoute(String(input)) ? hold.promise : jsonResponse({}),
    );
    const controller = new AbortController();
    let outcome = "PENDING";
    const done = e.client
      .readResultReferences!({ ...selection, signal: controller.signal })
      .then(
        () => {
          outcome = "RESOLVED";
        },
        (error: Error) => {
          outcome = error.message;
        },
      );
    await flush();
    controller.abort();
    await flush();
    expect(outcome).toBe("PENDING");
    hold.resolve(jsonResponse({ late: true }));
    await done;
    expect(outcome).toBe("READ_CANCELLED");
  });

  it("settles READ_CANCELLED when sign-out advances the auth generation mid-read", async () => {
    const e = setup();
    await e.login();
    const hold = deferred();
    e.fetcher.mockImplementation(async (input) =>
      referenceRoute(String(input)) ? hold.promise : jsonResponse({}),
    );
    let outcome = "PENDING";
    const done = e.client
      .readResultReferences!({ ...selection, signal: signal() })
      .then(
        () => {
          outcome = "RESOLVED";
        },
        (error: Error) => {
          outcome = error.message;
        },
      );
    await flush();
    await e.client.signOut();
    hold.resolve(jsonResponse({ late: true }));
    await done;
    expect(outcome).toBe("READ_CANCELLED");
  });
});
