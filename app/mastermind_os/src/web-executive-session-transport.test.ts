// @vitest-environment jsdom
// @vitest-environment-options {"url":"https://mcp.mastermind-x.com/os/"}
// Focused coverage for the fixed selected-session transport inside the
// existing private web auth owner. No backend, token or route is real here.
import { afterEach, describe, expect, it, vi } from "vitest";
import { createWebAuth } from "./web-auth";
import { ORIGIN } from "./public-config";

const RESOURCE = "https://fixture-resource.mastermind-x.com/executive";
const response = (data: unknown) =>
  new Response(JSON.stringify(data), {
    headers: { "content-type": "application/json" },
  });
const flush = async () => {
  for (let i = 0; i < 30; i++) await Promise.resolve();
};

function setup(options: { configured?: boolean } = {}) {
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
  const fetcher = vi.fn<typeof fetch>().mockImplementation(async () =>
    response({
      token_type: "Bearer",
      access_token: "private-token",
      expires_in: 3600,
      scope: new URL(popup.location).searchParams.get("scope"),
    }),
  );
  const client = createWebAuth({
    config: {
      executiveResource: options.configured === false ? null : RESOURCE,
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
        data: { type: "mastermind-auth-callback", state, code: "code-opaque" },
      } as unknown as MessageEvent);
  };
  const login = async () => {
    const pending = client.signIn();
    await flush();
    callback();
    await flush();
    callback();
    await flush();
    callback();
    await pending;
  };
  return { client, fetcher, login };
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

const SELECTION = { workRef: "WS:ONE", rootJobId: "JOB-1" };
const SEND_ARGS = {
  target_ref: `fabric_attempt:${"a".repeat(64)}`,
  instruction: "Continue the slice",
  stop_condition: "CI green",
  operation_key: `session-continue-${"b".repeat(64)}`,
};

describe("fixed selected-session transport", () => {
  it("sends only the four fixed session POST routes with exact argument shapes", async () => {
    const e = setup();
    await e.login();
    expect(e.client.executiveSession!.available()).toBe(true);
    e.fetcher.mockClear();
    e.fetcher.mockImplementation(async () => response({ ok: true }));
    const signal = new AbortController().signal;
    await e.client.executiveSession!.context(SELECTION, signal);
    await e.client.executiveSession!.send(SEND_ARGS, signal);
    await e.client.executiveSession!.reply({ operation_key: SEND_ARGS.operation_key }, signal);
    const args = {work_ref:"WS:ONE",root_job_id:"JOB-1",page_size:16,
      cursor:"YWJjZA=="};
    await e.client.executiveSession!.references!(args, signal);
    expect(e.fetcher.mock.calls.map(([url]) => url)).toEqual(
      ["context", "send", "reply", "references"].map((route) => `${ORIGIN}/os/executive/session/${route}`),
    );
    expect(e.fetcher.mock.calls.map(([, init]) => JSON.parse(String(init?.body)))).toEqual([
      { selection: { work_ref: "WS:ONE", root_job_id: "JOB-1" } },
      { arguments: SEND_ARGS },
      { arguments: { operation_key: SEND_ARGS.operation_key } },
      { arguments: {work_ref:"WS:ONE",root_job_id:"JOB-1",page_size:16,
        cursor:"YWJjZA==" } },
    ]);
    for (const [, init] of e.fetcher.mock.calls)
      expect(init).toMatchObject({
        method: "POST",
        redirect: "error",
        credentials: "omit",
        cache: "no-store",
        headers: {
          Authorization: "Bearer private-token",
          "Content-Type": "application/json",
        },
      });
  });

  it("sends no session request without Executive configuration or a valid Executive token", async () => {
    const unconfigured = setup({ configured: false });
    expect(unconfigured.client.executiveSession!.available()).toBe(false);
    await expect(
      unconfigured.client.executiveSession!.context(SELECTION, new AbortController().signal),
    ).rejects.toThrow("EXECUTIVE_AUTH_REQUIRED");
    expect(unconfigured.fetcher).not.toHaveBeenCalled();
    // Signed out with configuration present: still no request.
    const signedOut = setup();
    expect(signedOut.client.executiveSession!.available()).toBe(false);
    await expect(
      signedOut.client.executiveSession!.context(SELECTION, new AbortController().signal),
    ).rejects.toThrow("EXECUTIVE_AUTH_REQUIRED");
    expect(signedOut.fetcher).not.toHaveBeenCalled();
  });

  it("refuses a non-canonical selection before any request", async () => {
    const e = setup();
    await e.login();
    e.fetcher.mockClear();
    await expect(
      e.client.executiveSession!.context(
        { workRef: "bad", rootJobId: "JOB-1" },
        new AbortController().signal,
      ),
    ).rejects.toThrow("SELECTION_INVALID");
    expect(e.fetcher).not.toHaveBeenCalled();
  });

  it("aborts an in-flight session request on sign-out and advances the auth generation", async () => {
    const e = setup();
    await e.login();
    let release: (value: Response) => void = () => {};
    e.fetcher.mockReturnValueOnce(
      new Promise<Response>((resolve) => {
        release = resolve;
      }),
    );
    const generation = e.client.executiveSession!.authGeneration();
    const pending = e.client.executiveSession!.context(
      SELECTION,
      new AbortController().signal,
    );
    const rejected = expect(pending).rejects.toThrow("EXECUTIVE_REQUEST_CANCELLED");
    await e.client.signOut();
    await rejected;
    expect(e.client.executiveSession!.authGeneration()).toBeGreaterThan(generation);
    expect(e.client.executiveSession!.available()).toBe(false);
    release(response({ ok: true }));
    await flush();
    // Exactly the one request; no retry, no late second send.
    expect(e.fetcher.mock.calls.filter(([url]) => String(url).endsWith("/session/context"))).toHaveLength(1);
  });

  it("bounds the session response body", async () => {
    const e = setup();
    await e.login();
    e.fetcher.mockClear();
    e.fetcher.mockResolvedValueOnce(response({ data: "x".repeat(262_144) }));
    await expect(
      e.client.executiveSession!.context(SELECTION, new AbortController().signal),
    ).rejects.toThrow();
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });
});
