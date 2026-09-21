// @vitest-environment jsdom
// @vitest-environment-options {"url":"https://mcp.mastermind-x.com/os/"}
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createWebAuth,
  handleWebAuthCallback,
  type WebPopup,
} from "./web-auth";
import {
  ISSUER,
  ORIGIN,
  ACQUISITION_AUDIENCE,
  CONTENT_AUDIENCE,
  ACQUISITION_SCOPE,
  CONTENT_SCOPE,
  TRANSACTION_TTL_MS,
  READ_TIMEOUT_MS,
  TOKEN_TIMEOUT_MS,
} from "./public-config";
const response = (data: unknown) =>
  new Response(JSON.stringify(data), {
    headers: { "content-type": "application/json" },
  });
const deferred = <T>() => {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((yes) => (resolve = yes));
  return { promise, resolve };
};
const flush = async () => {
  for (let i = 0; i < 30; i++) await Promise.resolve();
};
function setup(
  options: {
    blocked?: boolean;
    digest?: Promise<ArrayBuffer>;
    configured?: boolean;
  } = {},
) {
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
  const fetcher = vi
    .fn<typeof fetch>()
    .mockImplementation(async () =>
      response({
        token_type: "Bearer",
        access_token: "private-token",
        expires_in: 3600,
      }),
    );
  const open = vi.fn(() => (options.blocked ? null : popup));
  const client = createWebAuth({
    config: {
      webClientId:
        options.configured === false ? null : "fixture-public-client",
    },
    openPopup: open,
    fetchFn: fetcher,
    crypto: {
      getRandomValues(array: Uint8Array) {
        array.fill(++count);
        return array;
      },
      subtle: {
        digest: () => options.digest ?? Promise.resolve(new ArrayBuffer(32)),
      },
    } as unknown as Crypto,
    addEventListener: ((_type: string, fn: (e: MessageEvent) => void) =>
      messages.add(fn)) as unknown as typeof window.addEventListener,
    removeEventListener: ((_type: string, fn: (e: MessageEvent) => void) =>
      messages.delete(fn)) as unknown as typeof window.removeEventListener,
  });
  const callback = (
    override: Record<string, unknown> = {},
    source: unknown = popup,
    origin = ORIGIN,
  ) => {
    const state = new URL(popup.location).searchParams.get("state");
    for (const listener of [...messages])
      listener({
        source,
        origin,
        data: {
          type: "mastermind-auth-callback",
          state,
          code: "code-opaque",
          ...override,
        },
      } as MessageEvent);
  };
  const login = async () => {
    const pending = client.signIn();
    await flush();
    callback();
    await flush();
    callback();
    await pending;
  };
  return { client, popup, messages, fetcher, open, callback, login };
}
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  history.replaceState(null, "", "/os/");
  Object.defineProperty(window, "opener", { value: null, configurable: true });
});
describe("browser public PKCE", () => {
  it("keeps missing public client IDs explicit without opening or requesting", async () => {
    const e = setup({ configured: false });
    expect(await e.client.signIn()).toMatchObject({ status: "unconfigured" });
    expect(e.open).not.toHaveBeenCalled();
    expect(e.fetcher).not.toHaveBeenCalled();
  });
  it("opens one popup synchronously and uses two distinct custom-only S256 transactions", async () => {
    const e = setup();
    const pending = e.client.signIn();
    expect(e.open).toHaveBeenCalledExactlyOnceWith(
      "about:blank",
      "_blank",
      expect.any(String),
    );
    await flush();
    const a = new URL(e.popup.location);
    expect(a.origin).toBe(new URL(ISSUER).origin);
    expect(a.searchParams.get("audience")).toBe(ACQUISITION_AUDIENCE);
    expect(a.searchParams.get("scope")).toBe(ACQUISITION_SCOPE);
    expect(a.searchParams.get("code_challenge_method")).toBe("S256");
    e.callback();
    await flush();
    const b = new URL(e.popup.location);
    expect(b.searchParams.get("audience")).toBe(CONTENT_AUDIENCE);
    expect(b.searchParams.get("scope")).toBe(CONTENT_SCOPE);
    expect(b.searchParams.get("state")).not.toBe(a.searchParams.get("state"));
    e.callback();
    await pending;
    expect(e.open).toHaveBeenCalledTimes(1);
    expect(e.client.getState()).toMatchObject({
      status: "signed_in",
      acquisition: true,
      content: true,
    });
    expect(e.popup.close).toHaveBeenCalledTimes(1);
    const body = new URLSearchParams(String(e.fetcher.mock.calls[0][1]?.body));
    expect(body.get("code_verifier")).toHaveLength(43);
    expect(body.has("client_secret")).toBe(false);
    expect(JSON.stringify(e.client)).not.toContain("private-token");
  });
  it.each(["source", "origin", "state"])(
    "ignores unrelated %s callbacks without consuming a legitimate transaction",
    async (field) => {
      const e = setup();
      const pending = e.client.signIn();
      await flush();
      e.callback(
        field === "state" ? { state: "wrong" } : {},
        field === "source" ? {} : e.popup,
        field === "origin" ? "https://example.invalid" : ORIGIN,
      );
      await flush();
      expect(e.fetcher).not.toHaveBeenCalled();
      e.callback();
      await flush();
      e.callback();
      await pending;
      expect(e.client.getState().content).toBe(true);
    },
  );
  it("consumes a code before exchange so duplicate callbacks cannot replay it", async () => {
    const e = setup();
    const pending = e.client.signIn();
    await flush();
    e.callback();
    e.callback();
    await flush();
    expect(e.fetcher).toHaveBeenCalledTimes(1);
    e.callback();
    await pending;
    expect(e.fetcher).toHaveBeenCalledTimes(2);
  });
  it("does not resume a PKCE challenge after logout", async () => {
    const digest = deferred<ArrayBuffer>();
    const e = setup({ digest: digest.promise });
    const pending = e.client.signIn();
    await e.client.signOut();
    digest.resolve(new ArrayBuffer(32));
    await pending;
    expect(e.popup.location).toBe("");
    expect(e.fetcher).not.toHaveBeenCalled();
    expect(e.client.getState().status).toBe("signed_out");
  });
  it("does not resurrect tokens after logout during exchange", async () => {
    const e = setup();
    const result = deferred<Response>();
    e.fetcher.mockReturnValueOnce(result.promise);
    const pending = e.client.signIn();
    await flush();
    e.callback();
    await flush();
    await e.client.signOut();
    result.resolve(
      response({
        token_type: "Bearer",
        access_token: "late",
        expires_in: 3600,
      }),
    );
    await pending;
    await flush();
    expect(e.client.getState().acquisition).toBe(false);
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });
  it("reports popup blocking and closing explicitly", async () => {
    const blocked = setup({ blocked: true });
    await blocked.client.signIn();
    expect(blocked.client.getState().reason).toBe("POPUP_BLOCKED");
    const e = setup();
    const pending = e.client.signIn();
    await flush();
    e.popup.closed = true;
    await vi.advanceTimersByTimeAsync(250);
    await pending;
    expect(e.client.getState().reason).toBe("POPUP_CLOSED");
  });
  it("expires one-use authorization state", async () => {
    const e = setup();
    const pending = e.client.signIn();
    await flush();
    await vi.advanceTimersByTimeAsync(TRANSACTION_TTL_MS);
    await pending;
    expect(e.client.getState().reason).toBe("TRANSACTION_EXPIRED");
    expect(e.messages.size).toBe(0);
  });
  it("keeps acquisition usable when content is refused", async () => {
    const e = setup();
    const pending = e.client.signIn();
    await flush();
    e.callback();
    await flush();
    e.callback({ code: undefined, failure: "AUTHORIZATION_DENIED" });
    await pending;
    expect(e.client.getState()).toMatchObject({
      status: "error",
      acquisition: true,
      content: false,
      reason: "AUTHORIZATION_DENIED",
    });
  });
  it.each([
    { token_type: "opaque" },
    { scope: "openid mastermind.workspace.read" },
    { expires_in: 0 },
    { expires_in: "3600" },
  ])("refuses an invalid token result %j", async (change) => {
    const e = setup();
    e.fetcher.mockResolvedValueOnce(
      response({
        token_type: "Bearer",
        access_token: "opaque-token",
        expires_in: 3600,
        ...change,
      }),
    );
    const pending = e.client.signIn();
    await flush();
    e.callback();
    await pending;
    expect(e.client.getState()).toMatchObject({
      status: "error",
      acquisition: false,
      content: false,
    });
  });
  it("refuses oversized token bodies", async () => {
    const e = setup();
    e.fetcher.mockResolvedValueOnce(response({ padding: "x".repeat(32769) }));
    const pending = e.client.signIn();
    await flush();
    e.callback();
    await pending;
    expect(e.client.getState().reason).toBe("RESPONSE_TOO_LARGE");
  });
  it("times out token exchange", async () => {
    const e = setup();
    e.fetcher.mockImplementationOnce(
      (_url, init) =>
        new Promise((_yes, no) =>
          init!.signal!.addEventListener("abort", () =>
            no(new Error("aborted")),
          ),
        ),
    );
    const pending = e.client.signIn();
    await flush();
    e.callback();
    await vi.advanceTimersByTimeAsync(TOKEN_TIMEOUT_MS);
    await pending;
    expect(e.client.getState().reason).toBe("TOKEN_TIMEOUT");
  });
});
describe("fixed browser reads", () => {
  it("maps only the exact mission pair and separate audience resources", async () => {
    const e = setup();
    await e.login();
    e.fetcher.mockImplementation(async () => response({ ok: true }));
    const signal = new AbortController().signal;
    await e.client.readPrograms({ signal });
    await e.client.readMission({
      work_ref: "WS:ONE",
      root_job_id: "JOB-1",
      signal,
    });
    await e.client.readCurrentWindow({ signal });
    const urls = e.fetcher.mock.calls.slice(2).map((c) => String(c[0]));
    expect(urls).toEqual([
      `${ORIGIN}/workspace/programs/current`,
      `${ORIGIN}/workspace/mission/current?work_ref=WS%3AONE&root_job_id=JOB-1`,
      `${ORIGIN}/workspace/window/current`,
    ]);
    await expect(
      e.client.readMission({ work_ref: "bad", root_job_id: "JOB-1", signal }),
    ).rejects.toThrow("SELECTION_INVALID");
  });
  it("permits >64KiB public JSON while enforcing the 2M byte cap", async () => {
    const e = setup();
    await e.login();
    e.fetcher.mockResolvedValueOnce(response({ body: "x".repeat(70000) }));
    await expect(
      e.client.readPrograms({ signal: new AbortController().signal }),
    ).resolves.toMatchObject({ body: expect.any(String) });
    e.fetcher.mockResolvedValueOnce(response({ body: "x".repeat(2_000_000) }));
    await expect(
      e.client.readPrograms({ signal: new AbortController().signal }),
    ).rejects.toThrow("RESPONSE_TOO_LARGE");
  });
  it("checks logout and abort again after a transport ignores cancellation", async () => {
    const e = setup();
    await e.login();
    const d = deferred<Response>();
    e.fetcher.mockReturnValueOnce(d.promise);
    const pending = e.client.readPrograms({
      signal: new AbortController().signal,
    });
    await e.client.signOut();
    d.resolve(response({ stale: true }));
    await expect(pending).rejects.toThrow("READ_CANCELLED");
  });
  it("does not release an expired token read", async () => {
    const e = setup();
    await e.login();
    vi.advanceTimersByTime(3600001);
    expect(e.client.getState().acquisition).toBe(false);
    await expect(
      e.client.readPrograms({ signal: new AbortController().signal }),
    ).rejects.toThrow("TOKEN_REQUIRED");
  });
  it("honors the read timeout", async () => {
    const e = setup();
    await e.login();
    const d = deferred<Response>();
    e.fetcher.mockReturnValueOnce(d.promise);
    const pending = e.client.readPrograms({
      signal: new AbortController().signal,
    });
    vi.advanceTimersByTime(READ_TIMEOUT_MS);
    d.resolve(response({ late: true }));
    await expect(pending).rejects.toThrow("READ_CANCELLED");
  });
});
describe("callback cleanup and handoff", () => {
  it("cleans the URL before code and state reach the exact-origin opener", () => {
    const post = vi.fn(() => expect(location.search + location.hash).toBe(""));
    Object.defineProperty(window, "opener", {
      value: { postMessage: post },
      configurable: true,
    });
    history.replaceState(
      null,
      "",
      "/os/auth/callback?state=one&code=two&iss=" + encodeURIComponent(ISSUER),
    );
    expect(handleWebAuthCallback()).toBe(true);
    expect(post).toHaveBeenCalledWith(
      { type: "mastermind-auth-callback", state: "one", code: "two" },
      ORIGIN,
    );
  });
  it.each([
    "state=one&code=two&code=three",
    "state=one&code=two&extra=x",
    "state=one&code=two&error=denied",
    "state=one&code=two&iss=bad",
    "state=one&code=two#secret",
  ])("refuses malformed callback %s after cleaning", (query) => {
    const post = vi.fn();
    Object.defineProperty(window, "opener", {
      value: { postMessage: post },
      configurable: true,
    });
    history.replaceState(null, "", "/os/auth/callback?" + query);
    handleWebAuthCallback();
    expect(location.search + location.hash).toBe("");
    expect(post.mock.calls[0][0]).toMatchObject({
      failure: "CALLBACK_INVALID",
    });
    expect(post.mock.calls[0][0]).not.toHaveProperty("code");
  });
  it("fails closed if URL cleanup fails and refuses callback path aliases", () => {
    history.replaceState(null, "", "/os/auth/callback?state=one&code=two");
    const post = vi.fn();
    Object.defineProperty(window, "opener", {
      value: { postMessage: post },
      configurable: true,
    });
    vi.spyOn(history, "replaceState").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(handleWebAuthCallback()).toBe(true);
    expect(post).not.toHaveBeenCalled();
    vi.restoreAllMocks();
    history.replaceState(null, "", "/os/auth/callback/");
    expect(handleWebAuthCallback()).toBe(false);
  });
});
