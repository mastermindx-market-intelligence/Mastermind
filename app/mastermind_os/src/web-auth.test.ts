import freshRecoveryOwner from "./conversations/new-conversation/fixtures/fresh-conversation-recovery-owner.json";
import projectConversationLegacy from "./fixtures/project-conversation-catalogue-owner.json";
import projectConversationFresh from "./fixtures/project-fresh-conversation-owner.json";
// @vitest-environment jsdom
// @vitest-environment-options {"url":"https://mcp.mastermind-x.com/os/"}
import { planObservationFixture } from "./planning/plan-observation.fixture";
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
  MAX_RESPONSE_BYTES,
} from "./public-config";
import workUnavailable from "./fixtures/work-service-unavailable.json";
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

describe("fixed BYOK role metadata transport", () => {
  it("uses the existing acquisition token with the fixed path and private no-store transport", async () => {
    const e = setup(); await e.login(); e.fetcher.mockClear();
    e.fetcher.mockResolvedValueOnce(response({ state: "SOURCE_UNBOUND" }));
    expect(await e.client.readByokRoles!({ signal: new AbortController().signal })).toEqual({ state: "SOURCE_UNBOUND" });
    expect(e.fetcher).toHaveBeenCalledExactlyOnceWith(ORIGIN + "/workspace/byok/roles/current",
      expect.objectContaining({ method: "GET", redirect: "error", credentials: "omit", cache: "no-store",
        headers: expect.objectContaining({ Authorization: "Bearer private-token" }) }));
  });
  it("enforces its smaller closed byte ceiling", async () => {
    const e = setup(); await e.login(); e.fetcher.mockClear();
    e.fetcher.mockResolvedValueOnce(response({ payload: "x".repeat(8192) }));
    await expect(e.client.readByokRoles!({ signal: new AbortController().signal })).rejects.toThrow();
    expect(e.fetcher).toHaveBeenCalledOnce();
  });
});
function setup(
  options: {
    blocked?: boolean;
    digest?: Promise<ArrayBuffer>;
    configured?: boolean;
    executiveResource?: string;
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
  const fetcher = vi.fn<typeof fetch>().mockImplementation(async () =>
    response({
      token_type: "Bearer",
      access_token: "private-token",
      expires_in: 3600,
      scope: new URL(popup.location).searchParams.get("scope"),
    }),
  );
  const open = vi.fn(() => (options.blocked ? null : popup));
  const client = createWebAuth({
    config: {
      executiveResource: options.executiveResource ?? null,
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
    // This harness counts only transient PKCE callback listeners. Persistent
    // cross-tab storage observers have a separate dedicated test fixture.
    addEventListener: ((type: string, fn: (e: MessageEvent) => void) => {
      if (type === "message") messages.add(fn);
    }) as unknown as typeof window.addEventListener,
    removeEventListener: ((type: string, fn: (e: MessageEvent) => void) => {
      if (type === "message") messages.delete(fn);
    }) as unknown as typeof window.removeEventListener,
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
    if (options.executiveResource) { await flush(); callback(); }
    await pending;
  };
  return { client, popup, messages, fetcher, open, callback, login };
}
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  localStorage.clear(); sessionStorage.clear();
  history.replaceState(null, "", "/os/");
  Object.defineProperty(window, "opener", { value: null, configurable: true });
});
describe("long-lived interactive browser sign-in", () => {
  const fireSilentCode = (listeners: Set<(e: MessageEvent) => void>) => {
    const frame = document.querySelector("iframe");
    expect(frame).not.toBeNull();
    const state = new URL(frame!.src).searchParams.get("state");
    for (const listener of [...listeners]) listener({
      source: frame!.contentWindow,
      origin: ORIGIN,
      data: { type: "mastermind-auth-callback", state, code: "silent-code" },
    } as MessageEvent);
  };

  it("renews a five-minute interactive grant ahead of expiry without another sign-in or stored token", async () => {
    const e = setup();
    let issued = 0;
    e.fetcher.mockImplementation(async () => response({
      token_type: "Bearer", access_token: `private-rotated-${++issued}`,
      expires_in: 300,
    }));
    await e.login();
    expect(e.client.getState()).toMatchObject({ status: "signed_in", acquisition: true, content: true });
    expect(e.open).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(240_000);
    await flush();
    expect(new URL(document.querySelector("iframe")!.src).searchParams.get("prompt")).toBe("none");
    fireSilentCode(e.messages);
    await flush();
    fireSilentCode(e.messages);
    await flush();
    expect(issued).toBe(4); // original two scopes, renewed two scopes
    expect(e.open).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(60_001); // old tokens are now expired
    expect(e.client.getState()).toMatchObject({ status: "signed_in", acquisition: true, content: true });
    expect(localStorage.getItem("mastermind-os-auth0-prior-login-v1:fixture-public-client")).toBe("1");
    expect(JSON.stringify(Object.values(localStorage))).not.toContain("private-rotated");
    expect(JSON.stringify(Object.values(sessionStorage))).not.toContain("private-rotated");
  });

  it("does not silently reauthenticate after an explicit logout interrupts renewal", async () => {
    const e = setup();
    e.fetcher.mockImplementation(async () => response({
      token_type: "Bearer", access_token: "short-lived-private",
      expires_in: 300,
    }));
    await e.login();
    await vi.advanceTimersByTimeAsync(240_000);
    await flush();
    expect(document.querySelector("iframe")).not.toBeNull();
    await e.client.signOut();
    fireSilentCode(e.messages);
    await flush();
    await vi.advanceTimersByTimeAsync(60_001);
    expect(e.client.getState()).toMatchObject({ status: "signed_out", reason: "USER_SIGNED_OUT" });
    expect(e.open).toHaveBeenCalledTimes(1);
    expect(document.querySelector("iframe")).toBeNull();
  });
});

describe("fixed project planning two-resource requests",()=>{
  const resource="https://fixture-resource.mastermind-x.com/executive";
  const args={operation_key:"original-planning",work_ref:"WS:EXAMPLE"};
  it("sends two private resource bearers only to the fixed same-origin route",async()=>{
    const e=setup({executiveResource:resource});await e.login();e.fetcher.mockReset();
    e.fetcher.mockImplementation(async()=>response({schema:"mastermind.project_initial_planning.private_result.v1",operation:"status",ok:true,data:{},error:null}));
    await e.client.executive!.projectPlanning!.request("status",args,new AbortController().signal);
    expect(e.fetcher).toHaveBeenCalledTimes(1);
    const [url,options]=e.fetcher.mock.calls[0]!;
    expect(url).toBe(`${ORIGIN}/os/executive/project-planning/status`);
    expect(options).toMatchObject({method:"POST",redirect:"error",credentials:"omit",cache:"no-store",
      headers:{Authorization:"Bearer private-token","X-Mastermind-Workspace-Authorization":"Bearer private-token"},body:JSON.stringify({arguments:args})});
    e.fetcher.mockClear();await e.client.executive!.context(new AbortController().signal);
    expect(e.fetcher.mock.calls[0]![1]!.headers).not.toHaveProperty("X-Mastermind-Workspace-Authorization");
  });
  it("rejects arbitrary routes and additional authority fields before fetch",async()=>{
    const e=setup({executiveResource:resource});await e.login();e.fetcher.mockReset();
    expect(()=>e.client.executive!.projectPlanning!.request("../submit" as never,args,new AbortController().signal)).toThrow("PROJECT_PLANNING_INPUT_INVALID");
    expect(()=>e.client.executive!.projectPlanning!.request("status",{...args,job_id:"JOB-invented"},new AbortController().signal)).toThrow("PROJECT_PLANNING_INPUT_INVALID");
    expect(e.fetcher).not.toHaveBeenCalled();
  });
  it("drops a pending planning response when either resource is signed out",async()=>{
    const e=setup({executiveResource:resource});await e.login();const held=deferred<Response>();e.fetcher.mockReset();e.fetcher.mockReturnValue(held.promise);
    const pending=e.client.executive!.projectPlanning!.request("status",args,new AbortController().signal);
    const rejection=expect(pending).rejects.toThrow();await e.client.signOut();held.resolve(response({ok:true}));await rejection;
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });
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
  it("broadcasts logout across tabs even when the storage marker hits quota", async () => {
    class TestChannel {
      static peers = new Set<TestChannel>();
      onmessage: ((event: MessageEvent) => void) | null = null;
      constructor(readonly name: string) { TestChannel.peers.add(this); }
      postMessage(value: unknown) {
        for (const peer of TestChannel.peers) {
          if (peer !== this && peer.name === this.name) {
            peer.onmessage?.({ data: value } as MessageEvent);
          }
        }
      }
      close() { TestChannel.peers.delete(this); }
    }
    vi.stubGlobal("BroadcastChannel", TestChannel);
    try {
      const peer = setup();
      await peer.login();
      expect(peer.client.getState().acquisition).toBe(true);
      const sender = setup();
      const oldSet = Storage.prototype.setItem;
      const quota = vi.spyOn(Storage.prototype, "setItem").mockImplementation(function(this: Storage, key, value) {
        if (key.startsWith("mastermind-os-auth-logout-v1:")) {
          throw new DOMException("Storage quota exhausted", "QuotaExceededError");
        }
        oldSet.call(this, key, value);
      });
      try { await sender.client.signOut(); }
      finally { quota.mockRestore(); }
      expect(localStorage.getItem("mastermind-os-auth-logout-v1:fixture-public-client")).toBeNull();
      expect(peer.client.getState()).toMatchObject({
        status: "signed_out", reason: "USER_SIGNED_OUT", acquisition: false, content: false,
      });
      await expect(peer.client.readPrograms({signal:new AbortController().signal}))
        .rejects.toThrow("TOKEN_REQUIRED");
    } finally { vi.unstubAllGlobals(); }
  });
  it("clears an explicit logout marker only after a new successful interactive login", async () => {
    const e=setup();
    await e.login();
    await e.client.signOut();
    expect(localStorage.getItem("mastermind-os-auth-logout-v1:fixture-public-client")).toBe("1");
    e.popup.closed=false;
    await e.login();
    expect(e.client.getState()).toMatchObject({status:"signed_in",acquisition:true});
    expect(localStorage.getItem("mastermind-os-auth-logout-v1:fixture-public-client")).toBeNull();
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
    await e.client.readWork({ signal });
    await e.client.readMission({
      work_ref: "WS:ONE",
      root_job_id: "JOB-1",
      signal,
    });
    await e.client.readCurrentWindow({ signal });
    const urls = e.fetcher.mock.calls.slice(2).map((c) => String(c[0]));
    expect(urls).toEqual([
      `${ORIGIN}/workspace/programs/current`,
      `${ORIGIN}/workspace/work/current`,
      `${ORIGIN}/workspace/mission/current?work_ref=WS%3AONE&root_job_id=JOB-1`,
      `${ORIGIN}/workspace/window/current`,
    ]);
    await expect(
      e.client.readMission({ work_ref: "bad", root_job_id: "JOB-1", signal }),
    ).rejects.toThrow("SELECTION_INVALID");
  });
  it("preserves the fixed Work typed-503 document for the closed decoder", async () => {
    const e = setup();
    await e.login();
    e.fetcher.mockResolvedValueOnce(
      new Response(JSON.stringify(workUnavailable), {
        status: 503,
        headers: { "content-type": "application/json" },
      }),
    );
    await expect(
      e.client.readWork({ signal: new AbortController().signal }),
    ).resolves.toEqual(workUnavailable);
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

// Fixed structured-result transport uses the existing acquisition token only.
import { bindMissionHost } from "./host";
import resultUnavailable from "./fixtures/result-design-unavailable-source_changed.json";
import { normalizeResultSelection } from "./result";
const resultRequest = () => ({
  workRef: resultUnavailable.selection.work_ref,
  rootJobId: resultUnavailable.selection.root_job_id,
  jobId: resultUnavailable.selection.job_id,
  attemptId: resultUnavailable.selection.attempt_id,
  resultEnvelopeDigest: resultUnavailable.selection.result_envelope_digest,
  signal: new AbortController().signal,
});
describe("fixed structured-result browser transport", () => {
  it("preserves validated typed503 on only the fixed result path", async () => {
    const e = setup();
    await e.login();
    e.fetcher.mockResolvedValueOnce(
      new Response(JSON.stringify(resultUnavailable), {
        status: 503,
        headers: { "content-type": "application/json" },
      }),
    );
    const host = bindMissionHost(e.client);
    expect(await host.readResult!(resultRequest())).toEqual(resultUnavailable);
    const [url, options] = e.fetcher.mock.calls.at(-1)!;
    expect(new URL(String(url)).pathname).toBe("/workspace/result/current");
    expect([...new URL(String(url)).searchParams.keys()]).toEqual([
      "work_ref",
      "root_job_id",
      "job_id",
      "attempt_id",
      "result_envelope_digest",
    ]);
    expect(options?.redirect).toBe("error");
    expect(options?.credentials).toBe("omit");
  });
  it.each([401, 403, 500])(
    "does not admit a result body from status %s",
    async (status) => {
      const e = setup();
      await e.login();
      e.fetcher.mockResolvedValueOnce(
        new Response(JSON.stringify(resultUnavailable), {
          status,
          headers: { "content-type": "application/json" },
        }),
      );
      await expect(
        bindMissionHost(e.client).readResult!(resultRequest()),
      ).rejects.toThrow();
    },
  );
  it("refuses malformed typed503 and oversize bytes before display", async () => {
    const e = setup();
    await e.login();
    const host = bindMissionHost(e.client);
    e.fetcher.mockResolvedValueOnce(
      new Response(JSON.stringify({ ...resultUnavailable, unexpected: true }), {
        status: 503,
        headers: { "content-type": "application/json" },
      }),
    );
    await expect(host.readResult!(resultRequest())).rejects.toThrow(
      "RESULT_RESPONSE_INVALID",
    );
    e.fetcher.mockResolvedValueOnce(
      new Response(" ".repeat(16385), {
        status: 503,
        headers: { "content-type": "application/json" },
      }),
    );
    await expect(host.readResult!(resultRequest())).rejects.toThrow();
  });
  it("rejects noncanonical new Mission selectors before HTTP", async () => {
    const e = setup();
    await e.login();
    e.fetcher.mockClear();
    await expect(
      e.client.readMissionV3!({
        workRef: "WS:AB",
        rootJobId: "JOB-x",
        signal: new AbortController().signal,
      }),
    ).rejects.toThrow("SELECTION_INVALID");
    expect(e.fetcher).not.toHaveBeenCalled();
  });
});

describe("fixed compound Mission/Result browser transport", () => {
  const wire = resultUnavailable.selection;
  const selected = normalizeResultSelection({
    workRef: wire.work_ref,
    rootJobId: wire.root_job_id,
    jobId: wire.job_id,
    attemptId: wire.attempt_id,
    resultEnvelopeDigest: wire.result_envelope_digest,
  })!;
  const compoundRequest = () => ({ ...selected, signal: new AbortController().signal });
  const unavailableBody = {
    schema: "mastermind.workspace_mission_result.v1",
    selection: wire,
    availability: "UNAVAILABLE",
    reason_codes: ["SOURCE_UNAVAILABLE"],
    mission: null,
    role_result: null,
  };
  async function producerBytes() {
    const cwd = (globalThis as { process?: { cwd?: () => string } }).process?.cwd?.();
    if (!cwd) throw new Error("producer fixture path requires the vitest worker cwd");
    // @ts-expect-error node:fs/promises is resolved by the vitest worker.
    const fs = (await import("node:fs/promises")) as { readFile(path: string): Promise<Uint8Array> };
    return new Uint8Array(await fs.readFile(
      `${cwd}/src/meta-ceo/fixtures/mission-result-producer/actual-pair.json`,
    ));
  }

  it("uses one fixed acquisition GET and the unchanged producer bytes", async () => {
    const e = setup();
    await e.login();
    const bytes = await producerBytes();
    const producer = JSON.parse(new TextDecoder().decode(bytes)) as { selection: typeof wire };
    const producerSelection = normalizeResultSelection({
      workRef: producer.selection.work_ref,
      rootJobId: producer.selection.root_job_id,
      jobId: producer.selection.job_id,
      attemptId: producer.selection.attempt_id,
      resultEnvelopeDigest: producer.selection.result_envelope_digest,
    })!;
    e.fetcher.mockResolvedValueOnce(new Response(bytes, { headers: { "content-type": "application/json" } }));
    const host = bindMissionHost(e.client);
    const decoded = await host.readMissionResult!({ ...producerSelection, signal: new AbortController().signal });
    expect(decoded.availability).toBe("AVAILABLE");
    const [url, options] = e.fetcher.mock.calls.at(-1)!;
    const parsed = new URL(String(url));
    expect(parsed.origin).toBe(ORIGIN);
    expect(parsed.pathname).toBe("/workspace/mission-result/current");
    expect([...parsed.searchParams.keys()]).toEqual([
      "work_ref", "root_job_id", "job_id", "attempt_id", "result_envelope_digest",
    ]);
    expect(parsed.searchParams.get("result_envelope_digest")).toBe(producerSelection.resultEnvelopeDigest);
    expect(options).toMatchObject({ method: "GET", redirect: "error", credentials: "omit", cache: "no-store" });
    expect(options?.body).toBeUndefined();
    expect(new Headers(options?.headers).get("authorization")).toMatch(/^Bearer /);
    expect(JSON.stringify(e.client)).not.toContain("private-token");
  });

  it("preserves a typed 503 compound refusal and refuses auth denial without a nested result", async () => {
    const e = setup();
    await e.login();
    const host = bindMissionHost(e.client);
    e.fetcher.mockResolvedValueOnce(new Response(JSON.stringify(unavailableBody), {
      status: 503, headers: { "content-type": "application/json" },
    }));
    const decoded = await host.readMissionResult!(compoundRequest());
    expect(decoded).toMatchObject({ availability: "UNAVAILABLE", mission: null, roleResult: null });
    e.fetcher.mockResolvedValueOnce(new Response(JSON.stringify(unavailableBody), {
      status: 401, headers: { "content-type": "application/json" },
    }));
    await expect(host.readMissionResult!(compoundRequest())).rejects.toThrow();
    e.fetcher.mockResolvedValueOnce(new Response(JSON.stringify({ ...unavailableBody, extra: true }), {
      status: 503, headers: { "content-type": "application/json" },
    }));
    await expect(host.readMissionResult!(compoundRequest())).rejects.toThrow("MISSION_RESULT_RESPONSE_INVALID");
  });

  it("refuses an oversized declared body and a surplus selector before a second read", async () => {
    const e = setup();
    await e.login();
    const host = bindMissionHost(e.client);
    e.fetcher.mockClear();
    e.fetcher.mockResolvedValueOnce(new Response("{}", {
      status: 200,
      headers: { "content-type": "application/json", "content-length": String(MAX_RESPONSE_BYTES + 1) },
    }));
    await expect(host.readMissionResult!(compoundRequest())).rejects.toThrow("RESPONSE_TOO_LARGE");
    expect(e.fetcher).toHaveBeenCalledTimes(1);
    await expect(e.client.readMissionResult!({ ...compoundRequest(), extra: true } as never)).rejects.toThrow("SELECTION_INVALID");
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });

  it("withholds a late body after sign-out even if the transport ignores abort", async () => {
    const e = setup();
    await e.login();
    let release!: (value: Response) => void;
    e.fetcher.mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));
    const host = bindMissionHost(e.client);
    const pending = host.readMissionResult!(compoundRequest());
    const assertion = expect(pending).rejects.toThrow();
    await flush();
    await e.client.signOut();
    release(new Response(JSON.stringify(unavailableBody), { headers: { "content-type": "application/json" } }));
    await assertion;
  });
});

describe("optional Executive authentication in the existing web owner", () => {
  const resource = "https://fixture-resource.mastermind-x.com/executive";
  const scopes = "mastermind.executive.read mastermind.executive.intent.submit";
  it("keeps one research submission live beyond the read deadline for its finite owner", async () => {
    const e = setup({ executiveResource: resource });
    await e.login();
    const held = deferred<Response>();
    e.fetcher.mockReset();
    e.fetcher.mockReturnValue(held.promise);
    const pending = e.client.executive!.submit({ execution_profile: "research_only",
      operation_key: "same-foreground-operation" }, new AbortController().signal);
    const settled = vi.fn();
    void pending.then(settled, settled);
    await vi.advanceTimersByTimeAsync(READ_TIMEOUT_MS + 1);
    expect(settled).not.toHaveBeenCalled();
    expect(e.fetcher).toHaveBeenCalledTimes(1);
    expect(e.fetcher.mock.calls[0]![1]!.signal!.aborted).toBe(false);
    const accepted = { ok: true, status: "accepted", request_ref: "same" };
    held.resolve(response(accepted));
    await expect(pending).resolves.toEqual(accepted);
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });
  it.each(["native_research_only", "bounded_code_change"])(
    "keeps the incumbent %s deadline and never retries", async (execution_profile) => {
      const e = setup({ executiveResource: resource });
      await e.login();
      e.fetcher.mockReset();
      e.fetcher.mockReturnValue(new Promise(() => {}));
      const pending = e.client.executive!.submit({ execution_profile }, new AbortController().signal);
      const refused = expect(pending).rejects.toThrow("EXECUTIVE_REQUEST_CANCELLED");
      await vi.advanceTimersByTimeAsync(READ_TIMEOUT_MS);
      await refused;
      expect(e.fetcher).toHaveBeenCalledTimes(1);
    });
  it("ends a stalled research submission at its one total deadline", async () => {
    const e = setup({ executiveResource: resource });
    await e.login();
    e.fetcher.mockReset();
    e.fetcher.mockReturnValue(new Promise(() => {}));
    const pending = e.client.executive!.submit({ execution_profile: "research_only" }, new AbortController().signal);
    const refused = expect(pending).rejects.toThrow("EXECUTIVE_REQUEST_CANCELLED");
    await vi.advanceTimersByTimeAsync(430_000);
    await refused;
    expect(e.fetcher).toHaveBeenCalledTimes(1);
    expect(e.fetcher.mock.calls[0]![1]!.signal!.aborted).toBe(true);
  });
  it("closes the actual research fetch when its auth generation changes", async () => {
    const e = setup({ executiveResource: resource });
    await e.login();
    e.fetcher.mockReset();
    e.fetcher.mockReturnValue(new Promise(() => {}));
    const pending = e.client.executive!.submit({ execution_profile: "research_only" }, new AbortController().signal);
    const refused = expect(pending).rejects.toThrow("EXECUTIVE_REQUEST_CANCELLED");
    e.client.signOut();
    await refused;
    expect(e.fetcher.mock.calls[0]![1]!.signal!.aborted).toBe(true);
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });
  it("uses a distinct third PKCE transaction with the same client and callback", async () => {
    const e = setup({ executiveResource: resource }), pending = e.client.signIn();
    await flush(); const first = new URL(e.popup.location);
    e.callback(); await flush(); const second = new URL(e.popup.location);
    e.callback(); await flush(); const third = new URL(e.popup.location);
    expect(third.searchParams.get("audience")).toBe(resource);
    expect(third.searchParams.get("scope")).toBe(scopes);
    expect(third.searchParams.get("client_id")).toBe(first.searchParams.get("client_id"));
    expect(third.searchParams.get("redirect_uri")).toBe(first.searchParams.get("redirect_uri"));
    expect(new Set([first, second, third].map((u) => u.searchParams.get("state"))).size).toBe(3);
    e.callback(); await pending;
    expect(e.client.executive!.available()).toBe(true);
    expect(e.client.getState()).toEqual({ status: "signed_in", reason: null, acquisition: true, content: true });
    expect(JSON.stringify(e.client)).not.toContain("private-token");
  });
  it("keeps workspace access usable when optional Executive authorization is refused", async () => {
    const e = setup({ executiveResource: resource }), pending = e.client.signIn();
    await flush(); e.callback(); await flush(); e.callback(); await flush();
    e.callback({ code: undefined, error: "access_denied" }); await pending;
    expect(e.client.getState()).toMatchObject({ status: "signed_in", acquisition: true, content: true });
    expect(e.client.executive!.available()).toBe(false);
  });
  it.each([scopes.split(" ").reverse().join(" "), "mastermind.executive.read", "mastermind.executive.intent.submit", scopes + " admin", scopes + " mastermind.executive.read"])(
    "accepts only the full or READ-only Executive scope set", async (returnedScope) => {
      const e = setup({ executiveResource: resource });
      e.fetcher.mockImplementation(async () => response({ token_type: "Bearer", access_token: "private-token", expires_in: 3600,
        scope: new URL(e.popup.location).searchParams.get("audience") === resource
          ? returnedScope : new URL(e.popup.location).searchParams.get("scope") }));
      await e.login();
      expect(e.client.executive!.available()).toBe(returnedScope === scopes.split(" ").reverse().join(" ") || returnedScope === "mastermind.executive.read");
    });
  it("keeps READ-only Executive grants usable for observation but refuses SEND before fetch", async () => {
    const e = setup({ executiveResource: resource });
    e.fetcher.mockImplementation(async () => response({
      token_type: "Bearer", access_token: "private-token", expires_in: 3600,
      scope: new URL(e.popup.location).searchParams.get("audience") === resource
        ? "mastermind.executive.read"
        : new URL(e.popup.location).searchParams.get("scope"),
    }));
    await e.login();
    expect(e.client.executive!.available()).toBe(true);
    expect(e.client.executiveSession!.available()).toBe(true);
    e.fetcher.mockClear();
    const signal = new AbortController().signal;
    await expect(e.client.executive!.submit({ operation_key: "readonly-denied" }, signal))
      .rejects.toThrow("EXECUTIVE_SEND_SCOPE_REQUIRED");
    await expect(e.client.executiveSession!.send({
      target_ref: "fabric_attempt:" + "a".repeat(64),
      instruction: "continue", stop_condition: "finish",
      operation_key: "session-continue-" + "b".repeat(64),
    }, signal)).rejects.toThrow("EXECUTIVE_SEND_SCOPE_REQUIRED");
    expect(e.fetcher).not.toHaveBeenCalled();
    e.fetcher.mockImplementation(async () => response({ ok: true }));
    await e.client.executive!.context(signal);
    await e.client.executive!.status({ intent_id: "read-only-status" }, signal);
    await e.client.executiveSession!.reply({ operation_key: "read-only-result" }, signal);
    expect(e.fetcher.mock.calls.map(([url]) => url)).toEqual([
      ORIGIN + "/os/executive/context", ORIGIN + "/os/executive/status",
      ORIGIN + "/os/executive/session/reply",
    ]);
  });
  it("retains SEND only when the exact combined Executive scopes are granted, regardless of ordering", async () => {
    const e = setup({ executiveResource: resource });
    e.fetcher.mockImplementation(async () => response({
      token_type: "Bearer", access_token: "private-token", expires_in: 3600,
      scope: new URL(e.popup.location).searchParams.get("audience") === resource
        ? scopes.split(" ").reverse().join(" ")
        : new URL(e.popup.location).searchParams.get("scope"),
    }));
    await e.login();
    e.fetcher.mockClear();
    e.fetcher.mockImplementation(async () => response({ ok: true }));
    const signal = new AbortController().signal;
    await e.client.executive!.submit({ operation_key: "combined-grant" }, signal);
    await e.client.executiveSession!.send({
      target_ref: "fabric_attempt:" + "a".repeat(64),
      instruction: "continue", stop_condition: "finish",
      operation_key: "session-continue-" + "b".repeat(64),
    }, signal);
    expect(e.fetcher.mock.calls.map(([url]) => url)).toEqual([
      ORIGIN + "/os/executive/submit", ORIGIN + "/os/executive/session/send",
    ]);
  });
  it("exposes only three fixed authenticated POST routes with exact bodies", async () => {
    const e = setup({ executiveResource: resource }); await e.login();
    e.fetcher.mockClear(); e.fetcher.mockResolvedValue(response({ ok: true }));
    const signal = new AbortController().signal;
    await e.client.executive!.context(signal);
    e.fetcher.mockResolvedValue(response({ ok: false }));
    await e.client.executive!.submit({ operation_key: "original" }, signal);
    e.fetcher.mockResolvedValue(response({ ok: false }));
    await e.client.executive!.status({ intent_id: "original-intent" }, signal);
    expect(e.fetcher.mock.calls.map(([url]) => url)).toEqual(["context", "submit", "status"].map((path) => ORIGIN + "/os/executive/" + path));
    expect(e.fetcher.mock.calls.map(([, init]) => JSON.parse(String(init?.body)))).toEqual([
      {}, { arguments: { operation_key: "original" } }, { arguments: { intent_id: "original-intent" } },
    ]);
    for (const [, init] of e.fetcher.mock.calls) expect(init).toMatchObject({
      method: "POST", redirect: "error", credentials: "omit", cache: "no-store",
      headers: { Authorization: "Bearer private-token", "Content-Type": "application/json" },
    });
  });
  it("bounds request and actual response bytes without submitting twice", async () => {
    const e = setup({ executiveResource: resource }); await e.login(); e.fetcher.mockClear();
    await expect(e.client.executive!.submit({ extra: "x".repeat(65_536) }, new AbortController().signal)).rejects.toThrow("EXECUTIVE_INPUT_TOO_LARGE");
    expect(e.fetcher).not.toHaveBeenCalled();
    e.fetcher.mockResolvedValue(response({ data: "x".repeat(262_144) }));
    await expect(e.client.executive!.context(new AbortController().signal)).rejects.toThrow();
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });
  it.each(["submit", "status"] as const)("invalidates a stalled %s reply immediately on sign-out", async (route) => {
    const e = setup({ executiveResource: resource }); await e.login();
    const late = deferred<Response>(); e.fetcher.mockReturnValue(late.promise);
    const generation = e.client.executive!.authGeneration();
    const result = route === "submit"
      ? e.client.executive!.submit({ operation_key: "original" }, new AbortController().signal)
      : e.client.executive!.status({ intent_id: "original" }, new AbortController().signal);
    const rejected = expect(result).rejects.toThrow("EXECUTIVE_REQUEST_CANCELLED");
    await e.client.signOut(); await rejected;
    expect(e.client.executive!.authGeneration()).toBeGreaterThan(generation);
    expect(e.client.executive!.available()).toBe(false);
    late.resolve(response({ ok: true, status: "accepted" })); await flush();
    expect(e.fetcher.mock.calls.filter(([url]) => String(url).endsWith("/" + route))).toHaveLength(1);
  });
  it("expires Executive capability even while the display's workspace access remains valid", async () => {
    const e = setup({ executiveResource: resource });
    e.fetcher.mockImplementation(async () => response({ token_type: "Bearer", access_token: "private-token",
      scope: new URL(e.popup.location).searchParams.get("scope"),
      expires_in: new URL(e.popup.location).searchParams.get("audience") === resource ? 1 : 3600 }));
    await e.login(); const generation = e.client.executive!.authGeneration(), listener = vi.fn();
    e.client.executive!.subscribe(listener);
    await vi.advanceTimersByTimeAsync(1001);
    expect(e.client.executive!.available()).toBe(false);
    expect(e.client.executive!.authGeneration()).toBeGreaterThan(generation);
    expect(listener).toHaveBeenCalled();
    expect(e.client.getState().status).toBe("signed_in");
  });
});

describe("authenticated admitted-plan Web host transport", () => {
  const selection = { work_ref: "WS:PLAN-VISIBILITY", root_job_id: "JOB-123" };
  const request = () => ({ ...selection, signal: new AbortController().signal });
  const observation = (state: "SAME" | "UNKNOWN") => state === "SAME"
    ? planObservationFixture(selection)
    : { ...planObservationFixture(selection), state, control_room: null, runtime: null };
  const unavailablePlan = () => ({
    schema: "mastermind.workspace_admitted_execution_plan.v1",
    selection: { ...selection }, availability: "UNAVAILABLE",
    reason_codes: ["ADMISSION_NOT_ESTABLISHED"],
    source_observation: observation("UNKNOWN"), plan: null,
  });
  const availablePlan = () => ({
    schema: "mastermind.workspace_admitted_execution_plan.v1",
    selection: { ...selection }, availability: "AVAILABLE",
    reason_codes: [], source_observation: observation("SAME"),
    plan: { schema: "mastermind.admitted_execution_plan_view.v1",
      root_job_id: selection.root_job_id, plan_attempt_id: "ATT-123",
      plan_schema_version: "mastermind.execution_plan/v3",
      admission_schema_version: "mastermind.coo_plan_admission/v2",
      policy_sha: "a".repeat(64), plan_digest: "b".repeat(64),
      reservation_digest: "c".repeat(64), admission_state: "ADMITTED",
      steps: [{ ordinal: 0, step_id: "step-0",
        objective: "Validate the authenticated original plan",
        business_impact: "material", review_required: true, prerequisite_step_ids: [] }],
    },
  });
  it("mounts only the existing generation-fenced owner port, with no unsigned acquisition", async () => {
    const e = setup();
    const host = bindMissionHost(e.client);
    expect(typeof e.client.invalidationGeneration).toBe("function");
    expect(typeof host.readAdmittedPlan).toBe("function");
    await expect(host.readAdmittedPlan!(request())).rejects.toThrow("PLAN_READ_UNAUTHORIZED");
    expect(e.fetcher).not.toHaveBeenCalled();
    await e.login();
    e.fetcher.mockClear();
    e.fetcher.mockResolvedValueOnce(response(availablePlan()));
    const result = await host.readAdmittedPlan!(request());
    expect(result.availability).toBe("AVAILABLE");
    if (result.availability !== "AVAILABLE") throw Error("expected admitted plan");
    expect(result.plan.steps[0].objective).toBe("Validate the authenticated original plan");
    expect(e.fetcher).toHaveBeenCalledTimes(1);
    const [url, options] = e.fetcher.mock.calls[0];
    expect(new URL(String(url)).pathname).toBe("/workspace/plan/current");
    expect(Object.fromEntries(new URL(String(url)).searchParams)).toEqual(selection);
    expect(options).toMatchObject({
      method: "GET", redirect: "error", credentials: "omit", cache: "no-store",
      headers: { Authorization: "Bearer private-token" },
    });
  });
  it("preserves 503 as a typed unavailable plan without treating admission as execution", async () => {
    const e = setup(); await e.login(); e.fetcher.mockClear();
    e.fetcher.mockResolvedValueOnce(new Response(JSON.stringify(unavailablePlan()), {
      status: 503, headers: { "content-type": "application/json" },
    }));
    const observed = await bindMissionHost(e.client).readAdmittedPlan!(request());
    expect(observed).toMatchObject({ availability: "UNAVAILABLE", observation: "UNKNOWN",
      plan: null, reason_codes: ["ADMISSION_NOT_ESTABLISHED"] });
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });
  it("fences a late plan reply after sign-out using the original OAuth generation", async () => {
    const e = setup(); await e.login(); e.fetcher.mockClear();
    const host = bindMissionHost(e.client);
    const late = deferred<Response>();
    e.fetcher.mockReturnValueOnce(late.promise);
    const before = host.invalidationGeneration!();
    const result = host.readAdmittedPlan!(request());
    const denied = expect(result).rejects.toThrow();
    await host.auth!.signOut();
    late.resolve(response(availablePlan()));
    await denied;
    expect(host.invalidationGeneration!()).toBeGreaterThan(before);
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });
});


import {
  ControlRoomActionTransportError, CONTROL_ROOM_UNKNOWN_OUTCOME,
  type ControlRoomOperation,
} from "./control-room-actions";

describe("fixed acquisition Control Room action transport", () => {
  const terminal = (
    operation: ControlRoomOperation = "open",
    disposition = "OWNER_RETURNED",
    outcome: Record<string, unknown> = { ok: false, detail: "original owner refused" },
  ) => ({
    schema: "mastermind.workspace_control_room_action_result.v1",
    operation, status: disposition === "OWNER_RETURNED" ? 200 : disposition === "NOT_DISPATCHED" ? 409 : 503,
    disposition, outcome,
  });
  const actionResponse = (value = terminal(), status = value.status) =>
    new Response(JSON.stringify(value), { status, headers: { "content-type": "application/json" } });
  const invoke = (
    client: ReturnType<typeof createWebAuth>, operation: ControlRoomOperation = "open",
    signal = new AbortController().signal,
    payload: Record<string, unknown> = { binding_id: "original-binding" },
  ) => {
    switch (operation) {
      case "open": return client.openControlRoomSurface!({ payload, signal });
      case "bind": return client.bindControlRoomSurface!({ payload, signal });
      case "unbind": return client.unbindControlRoomSurface!({ payload, signal });
      case "refresh-builds": return client.refreshControlRoomBuilds!({ signal });
    }
  };
  const login = async (expires = 3600) => {
    const e = setup({ executiveResource: "https://fixture-resource.mastermind-x.com/executive" });
    e.fetcher.mockImplementation(async () => {
      const url = new URL(e.popup.location);
      return response({
        token_type: "Bearer", access_token: url.searchParams.get("audience") === ACQUISITION_AUDIENCE
          ? "fixture-acquisition-token" : "fixture-other-token",
        expires_in: expires, scope: url.searchParams.get("scope"),
      });
    });
    await e.login();
    e.fetcher.mockReset();
    e.fetcher.mockResolvedValue(actionResponse());
    return e;
  };
  const uncertain = (operation = "open") => ({ operation, disposition: "EFFECT_UNKNOWN" });

  it.each([
    ["open", { binding_id: "original-binding", target_surface: "desktop", owed_context: null }],
    ["bind", { work_ref: "WS:A", role: "ceo", provider: "codex", locator: { session_id: "explicit" } }],
    ["unbind", { binding_id: "original-binding" }],
    ["refresh-builds", {}],
  ] as const)("sends exactly one fixed %s call with the acquisition bearer", async (operation, payload) => {
    const e = await login();
    const expected = terminal(operation);
    e.fetcher.mockResolvedValueOnce(actionResponse(expected));
    expect(await invoke(e.client, operation, undefined, payload)).toEqual(expected);
    expect(e.fetcher).toHaveBeenCalledTimes(1);
    const [url, init] = e.fetcher.mock.calls[0]!;
    expect(url).toBe(ORIGIN + "/workspace/control-room/" + operation);
    expect(init).toMatchObject({
      method: "POST", redirect: "error", credentials: "omit", cache: "no-store",
      headers: { Accept: "application/json", "Content-Type": "application/json",
        Authorization: "Bearer fixture-acquisition-token" },
    });
    expect(JSON.parse(String(init?.body))).toEqual(payload);
    expect(new TextEncoder().encode(String(init?.body)).length).toBeLessThanOrEqual(8192);
  });

  it("keeps Discovery as the separate fixed authenticated READ", async () => {
    const e = await login();
    e.fetcher.mockResolvedValueOnce(response({ observed: true }));
    expect(await e.client.readControlRoomDiscovery!({ signal: new AbortController().signal })).toEqual({ observed: true });
    expect(e.fetcher).toHaveBeenCalledExactlyOnceWith(
      ORIGIN + "/workspace/control-room/discover/current",
      expect.objectContaining({ method: "GET", headers: expect.objectContaining({ Authorization: "Bearer fixture-acquisition-token" }) }),
    );
  });

  it.each(["signed_out", "unconfigured", "aborted", "invalid", "oversized", "expired"] as const)(
    "proves no outgoing action for %s preflight", async (why) => {
      const e = why === "unconfigured" ? setup({ configured: false }) : await login();
      if (why === "signed_out") await e.client.signOut();
      if (why === "expired") await vi.advanceTimersByTimeAsync(3_600_001);
      e.fetcher.mockClear();
      const controller = new AbortController();
      if (why === "aborted") controller.abort();
      const payload = why === "invalid" ? { wrong: "field" } : why === "oversized"
        ? { binding_id: "x".repeat(8192) } : { binding_id: "original-binding" };
      await expect(invoke(e.client, "open", controller.signal, payload)).rejects.toMatchObject({
        operation: "open", disposition: "NOT_DISPATCHED",
      });
      expect(e.fetcher).not.toHaveBeenCalled();
    },
  );

  it("rejects auth movement while inspecting a detached request before fetch", async () => {
    const e = await login();
    const payload = new Proxy({ binding_id: "original-binding" }, {
      ownKeys(target) { void e.client.signOut(); return Reflect.ownKeys(target); },
    });
    await expect(invoke(e.client, "open", undefined, payload)).rejects.toMatchObject({
      operation: "open", disposition: "NOT_DISPATCHED",
    });
    expect(e.fetcher).not.toHaveBeenCalled();
  });

  it.each([
    new Error("fetch failed"),
    new ControlRoomActionTransportError("open", "NOT_DISPATCHED"),
    new ControlRoomActionTransportError("bind", "NOT_DISPATCHED"),
  ])("classifies a synchronous fetch exception from its own dispatch fact", async (error) => {
    const e = await login();
    e.fetcher.mockImplementationOnce(() => { throw error; });
    await expect(invoke(e.client)).rejects.toMatchObject(uncertain());
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });

  it("classifies rejected fetch without trusting a foreign transport error", async () => {
    const e = await login();
    e.fetcher.mockRejectedValueOnce(new ControlRoomActionTransportError("unbind", "NOT_DISPATCHED"));
    await expect(invoke(e.client)).rejects.toMatchObject(uncertain());
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });

  it.each(["logout", "expiry"] as const)("retains the qualified owner result after %s", async (why) => {
    const e = await login(why === "expiry" ? 2 : 3600);
    const late = deferred<Response>(); e.fetcher.mockReturnValueOnce(late.promise);
    const pending = invoke(e.client);
    await flush();
    if (why === "logout") await e.client.signOut();
    else await vi.advanceTimersByTimeAsync(2001);
    const expected = terminal();
    late.resolve(actionResponse(expected));
    expect(await pending).toEqual(expected);
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });

  it("allows Refresh builds beyond the incumbent READ timeout without a retry", async () => {
    const e = await login(), late = deferred<Response>();
    e.fetcher.mockReturnValueOnce(late.promise);
    const pending = invoke(e.client, "refresh-builds");
    await vi.advanceTimersByTimeAsync(READ_TIMEOUT_MS + 1);
    const expected = terminal("refresh-builds");
    late.resolve(actionResponse(expected));
    expect(await pending).toEqual(expected);
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });

  it("settles at the single total deadline even when fetch ignores abort", async () => {
    const e = await login(), late = deferred<Response>();
    e.fetcher.mockReturnValueOnce(late.promise);
    const pending = invoke(e.client).catch(error => error);
    await vi.advanceTimersByTimeAsync(489_999);
    let settled = false; void pending.then(() => { settled = true; }); await flush();
    expect(settled).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    expect(await pending).toMatchObject(uncertain());
    const cancel = vi.fn(async () => {});
    late.resolve({ body: { cancel }, headers: new Headers(), status: 200 } as unknown as Response);
    await flush();
    expect(cancel).toHaveBeenCalledTimes(1);
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });

  it("does not restart its deadline at headers and never awaits stalled cleanup", async () => {
    const e = await login(), late = deferred<Response>();
    e.fetcher.mockReturnValueOnce(late.promise);
    const pending = invoke(e.client).catch(error => error);
    await vi.advanceTimersByTimeAsync(300_000);
    const reader = {
      read: vi.fn(() => new Promise<ReadableStreamReadResult<Uint8Array>>(() => {})),
      cancel: vi.fn(() => new Promise<void>(() => {})), releaseLock: vi.fn(),
    };
    late.resolve({ status: 200, headers: new Headers({ "content-type": "application/json" }),
      body: { getReader: () => reader } } as unknown as Response);
    await flush();
    await vi.advanceTimersByTimeAsync(190_000);
    expect(await pending).toMatchObject(uncertain());
    expect(reader.cancel).toHaveBeenCalledTimes(1);
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });

  it("returns uncertainty promptly on caller abort with an uncooperative fetch", async () => {
    const e = await login(), controller = new AbortController(), late = deferred<Response>();
    e.fetcher.mockReturnValueOnce(late.promise);
    const pending = invoke(e.client, "open", controller.signal).catch(error => error);
    controller.abort();
    expect(await pending).toMatchObject(uncertain());
    late.resolve(actionResponse()); await flush();
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });

  it("keeps a qualified result when cleanup triggers abort and throws", async () => {
    const e = await login(), controller = new AbortController(), expected = terminal();
    const bytes = new TextEncoder().encode(JSON.stringify(expected));
    const reader = {
      read: vi.fn().mockResolvedValueOnce({ done: false, value: bytes }).mockResolvedValueOnce({ done: true }),
      cancel: vi.fn(() => { throw new Error("cleanup"); }),
      releaseLock: vi.fn(() => { controller.abort(); throw new Error("release"); }),
    };
    e.fetcher.mockResolvedValueOnce({ status: 200, headers: new Headers({ "content-type": "application/json" }),
      body: { getReader: () => reader } } as unknown as Response);
    expect(await invoke(e.client, "open", controller.signal)).toEqual(expected);
  });

  it("owns copies of chunks before a source reader reuses its buffer", async () => {
    const e = await login(), expected = terminal();
    const bytes = new TextEncoder().encode(JSON.stringify(expected));
    const first = bytes.slice(0, 20), second = bytes.slice(20);
    const reader = {
      read: vi.fn().mockResolvedValueOnce({ done: false, value: first })
        .mockImplementationOnce(async () => { first.fill(0); return { done: false, value: second }; })
        .mockResolvedValueOnce({ done: true }),
      cancel: vi.fn(async () => {}), releaseLock: vi.fn(),
    };
    e.fetcher.mockResolvedValueOnce({ status: 200, headers: new Headers({ "content-type": "application/json" }),
      body: { getReader: () => reader } } as unknown as Response);
    expect(await invoke(e.client)).toEqual(expected);
  });

  it.each(["NOT_DISPATCHED", "EFFECT_UNKNOWN"])("retains a qualified non-2xx %s envelope", async disposition => {
    const e = await login();
    const expected = terminal("open", disposition,
      disposition === "EFFECT_UNKNOWN" ? CONTROL_ROOM_UNKNOWN_OUTCOME : { ok: false, failure_kind: "stale_context" });
    e.fetcher.mockResolvedValueOnce(actionResponse(expected));
    expect(await invoke(e.client)).toEqual(expected);
  });

  it.each(["wide", "spoofed", "data-view"])("refuses a non-byte %s stream without normalization", async kind => {
    const e = await login();
    const bytes = new TextEncoder().encode(JSON.stringify(terminal()));
    const wide = new Uint16Array(bytes);
    if (kind === "spoofed") Object.defineProperty(wide, Symbol.toStringTag, { value: "Uint8Array" });
    const value = kind === "data-view" ? new DataView(bytes.buffer) : wide;
    const reader = {
      read: vi.fn().mockResolvedValueOnce({ done: false, value }).mockResolvedValueOnce({ done: true }),
      cancel: vi.fn(async () => {}), releaseLock: vi.fn(),
    };
    e.fetcher.mockResolvedValueOnce({ status: 200, headers: new Headers({ "content-type": "application/json" }),
      body: { getReader: () => reader } } as unknown as Response);
    await expect(invoke(e.client)).rejects.toMatchObject(uncertain());
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });

  it("counts synchronous preflight against its original deadline before dispatch", async () => {
    const e = await login();
    let expired = false;
    const payload = new Proxy({ binding_id: "original-binding" }, {
      ownKeys(target) {
        if (!expired) { expired = true; vi.advanceTimersByTime(490_001); }
        return Reflect.ownKeys(target);
      },
    });
    await expect(invoke(e.client, "open", undefined, payload)).rejects.toMatchObject({
      operation: "open", disposition: "NOT_DISPATCHED",
    });
    expect(e.fetcher).not.toHaveBeenCalled();
  });

  it("retains a canonical unknown outcome regardless of JSON member order", async () => {
    const e = await login();
    const outcome = Object.fromEntries(Object.entries(CONTROL_ROOM_UNKNOWN_OUTCOME).sort(([a], [b]) => a.localeCompare(b)));
    const expected = terminal("open", "EFFECT_UNKNOWN", outcome);
    e.fetcher.mockResolvedValueOnce(actionResponse(expected));
    expect(await invoke(e.client)).toEqual(expected);
  });

  it.each([
    "wrong_operation", "status_mismatch", "duplicate_keys", "escaped_duplicate",
    "invalid_utf8", "html", "bare_auth_refusal", "length_not_decimal", "length_over_cap", "actual_over_cap",
  ] as const)("withholds an unqualified %s response after the sole fetch", async why => {
    const e = await login();
    let raw: string | Uint8Array = JSON.stringify(terminal());
    let status = 200;
    const headers: Record<string, string> = { "content-type": "application/json" };
    if (why === "wrong_operation") raw = JSON.stringify(terminal("bind"));
    if (why === "status_mismatch") status = 409;
    if (why === "duplicate_keys") raw = raw.replace('"operation":"open"', '"operation":"bind","operation":"open"');
    if (why === "escaped_duplicate") raw = raw.replace('"operation":"open"', '"oper\\u0061tion":"bind","operation":"open"');
    if (why === "invalid_utf8") raw = new Uint8Array([0xc3, 0x28]);
    if (why === "html") { raw = "<html>refused</html>"; headers["content-type"] = "text/html"; }
    if (why === "bare_auth_refusal") { raw = '{"detail":"not authorized"}'; status = 403; }
    if (why === "length_not_decimal") headers["content-length"] = "1e3";
    if (why === "length_over_cap") headers["content-length"] = "2000001";
    if (why === "actual_over_cap") raw = " ".repeat(2_000_001);
    e.fetcher.mockResolvedValueOnce(new Response(raw as BodyInit, { status, headers }));
    await expect(invoke(e.client)).rejects.toMatchObject(uncertain());
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });
});

describe("authenticated per-user Fabric browser reads", () => {
  const selection = { rootId: "ROOT:paid-fixture", runId: "ATT-1" };
  const status = () => ({
    schema: "mastermind.fabric_task_status.v1",
    run_id: selection.runId, root_id: selection.rootId, parent_run_id: null,
    state: "TERMINAL", rc: 0, signal: "ok",
    result_available: true, result_bytes: 41, accepted: false,
    accepted_by: "none", acceptance_state: "NOT_ACCEPTED",
    acceptance_reason: "not_accepted",
  });
  const catalog = () => ({
    schema: "mastermind.attended_fabric_catalog.v1", availability: "PARTIAL",
    observed_at: "2026-11-03T00:00:00Z",
    source: {
      owner: "ATTENDED_FABRIC", observation_kind: "CONTROLLER_STATUS_SNAPSHOT",
      revision: "b".repeat(64), scope: "EXACT_RUN_SET", atomic: false,
      time_basis: "LOCAL_READ",
    },
    coverage: {
      returned_count: 1, candidate_count: 2, omitted_count: 1,
      scan_complete: true, status_complete: true,
    },
    items: [{ run_id: selection.runId, controller_modified_at: null,
      status: status(), reason_code: null }],
    reason_codes: ["ROWS_OMITTED"],
  });
  const request = (client: ReturnType<typeof setup>["client"], kind: "catalog" | "status",
    signal = new AbortController().signal) => {
    const host = bindMissionHost(client);
    return kind === "catalog"
      ? host.readAttendedFabricCatalog!({ signal })
      : host.readAttendedFabric!({ ...selection, signal });
  };

  it("mounts both fixed reads and refuses a signed-out caller before HTTP", async () => {
    const e = setup(), host = bindMissionHost(e.client);
    expect(typeof host.readAttendedFabricCatalog).toBe("function");
    expect(typeof host.readAttendedFabric).toBe("function");
    await expect(request(e.client, "catalog")).rejects.toThrow("FABRIC_READ_UNAUTHORIZED");
    await expect(request(e.client, "status")).rejects.toThrow("FABRIC_READ_UNAUTHORIZED");
    expect(e.fetcher).not.toHaveBeenCalled();
  });

  it("uses the acquisition bearer on exact metadata-only GET routes", async () => {
    const e = setup();
    await e.login();
    e.fetcher.mockClear();
    e.fetcher.mockResolvedValueOnce(response(catalog()));
    expect(await request(e.client, "catalog")).toEqual(catalog());
    e.fetcher.mockResolvedValueOnce(response(status()));
    expect(await request(e.client, "status")).toEqual(status());
    expect(e.fetcher).toHaveBeenCalledTimes(2);
    const [catalogUrl, catalogOptions] = e.fetcher.mock.calls[0];
    expect(String(catalogUrl)).toBe(`${ORIGIN}/workspace/fabric/catalog/current`);
    const [statusUrl, statusOptions] = e.fetcher.mock.calls[1];
    expect(new URL(String(statusUrl)).origin).toBe(ORIGIN);
    expect(new URL(String(statusUrl)).pathname).toBe("/workspace/fabric/status/current");
    expect([...new URL(String(statusUrl)).searchParams]).toEqual([
      ["root_id", selection.rootId], ["run_id", selection.runId],
    ]);
    for (const options of [catalogOptions, statusOptions]) {
      expect(options).toMatchObject({
        method: "GET", credentials: "omit", redirect: "error", cache: "no-store",
        headers: { Accept: "application/json", Authorization: "Bearer private-token" },
      });
      expect(options).not.toHaveProperty("body");
    }
  });

  it.each(["", "../foreign", "https://example.invalid/run", "run&root_id=foreign", "x".repeat(129)])(
    "refuses invalid exact-run selectors %s before HTTP", async (invalid) => {
      const e = setup();
      await e.login();
      e.fetcher.mockClear();
      for (const selected of [
        { rootId: invalid, runId: selection.runId },
        { rootId: selection.rootId, runId: invalid },
      ]) {
        await expect(e.client.readAttendedFabric!({ ...selected,
          signal: new AbortController().signal })).rejects.toThrow("FABRIC_SELECTION_INVALID");
      }
      expect(e.fetcher).not.toHaveBeenCalled();
    },
  );

  it.each(["catalog", "status"] as const)(
    "rejects unauthorized or unavailable %s payloads", async (kind) => {
      const e = setup();
      await e.login();
      for (const code of [401, 403, 503]) {
        e.fetcher.mockResolvedValueOnce(new Response(JSON.stringify(kind === "catalog" ? catalog() : status()), {
          status: code, headers: { "content-type": "application/json" },
        }));
        await expect(request(e.client, kind)).rejects.toThrow("READ_FAILED");
      }
    },
  );

  it.each(["catalog", "status"] as const)(
    "withholds an in-flight %s after sign-out without repeating the read", async (kind) => {
      const e = setup();
      await e.login();
      e.fetcher.mockClear();
      const d = deferred<Response>();
      e.fetcher.mockReturnValueOnce(d.promise);
      const pending = request(e.client, kind);
      await e.client.signOut();
      d.resolve(response(kind === "catalog" ? catalog() : status()));
      await expect(pending).rejects.toThrow("READ_CANCELLED");
      expect(e.fetcher).toHaveBeenCalledTimes(1);
    },
  );

  it.each(["catalog", "status"] as const)(
    "cancels %s and withholds a late server response", async (kind) => {
      const e = setup();
      await e.login();
      e.fetcher.mockClear();
      const d = deferred<Response>(), controller = new AbortController();
      e.fetcher.mockReturnValueOnce(d.promise);
      const pending = request(e.client, kind, controller.signal);
      controller.abort();
      expect(e.fetcher.mock.calls[0][1]?.signal?.aborted).toBe(true);
      d.resolve(response(kind === "catalog" ? catalog() : status()));
      await expect(pending).rejects.toThrow("READ_CANCELLED");
      expect(e.fetcher).toHaveBeenCalledTimes(1);
    },
  );

  it("keeps machine-wide catalogs outside the authenticated user's run set", async () => {
    const e = setup();
    await e.login();
    const wide = catalog();
    wide.source.scope = "MACHINE_OWNER";
    e.fetcher.mockResolvedValueOnce(response(wide));
    await expect(request(e.client, "catalog")).rejects.toThrow("FABRIC_CATALOG_SCOPE_REFUSED");
  });

  it.each([["catalog", 65_536], ["status", 16_384]] as const)(
    "bounds the %s response before handing it to the host decoder", async (kind, cap) => {
      const e = setup();
      await e.login();
      e.fetcher.mockResolvedValueOnce(response({
        ...(kind === "catalog" ? catalog() : status()), padding: "x".repeat(cap),
      }));
      await expect(request(e.client, kind)).rejects.toThrow();
    },
  );
});

describe("fixed H2 direct-native authenticated routes",()=>{
  const resource="https://fixture-resource.mastermind-x.com/executive";
  const selection={work_ref:"WS:H2-FIXTURE",job_id:"JOB-123",attempt_id:null};
  const unavailable={schema:"mastermind.direct_native_result_response.v1",selection,availability:"UNAVAILABLE",reason_codes:["NOT_TERMINAL"],result:null,consumption:null};
  it("refuses READ-only direct-native Event ACK before network while allowing result reads", async () => {
    const e = setup({ executiveResource: resource });
    e.fetcher.mockImplementation(async () => response({
      token_type: "Bearer", access_token: "private-token", expires_in: 3600,
      scope: new URL(e.popup.location).searchParams.get("audience") === resource
        ? "mastermind.executive.read"
        : new URL(e.popup.location).searchParams.get("scope"),
    }));
    await e.login();
    expect(e.client.executive!.available()).toBe(true);
    e.fetcher.mockClear();
    e.fetcher.mockResolvedValue(response(unavailable));
    const signal = new AbortController().signal;
    await e.client.executive!.directNative!.read(selection, signal);
    expect(e.fetcher).toHaveBeenCalledTimes(1);
    await expect(e.client.executive!.directNative!.consume({
      ...selection, attempt_id: "ATT-456", result_digest: "d".repeat(64),
      operation_key: "mmos-readonly-ack-denied",
    }, signal)).rejects.toThrow("EXECUTIVE_SEND_SCOPE_REQUIRED");
    await expect(e.client.executive!.directNative!.correction!({
      ...selection,attempt_id:'ATT-456',fence_generation:7,operation_key:'original-correction',operation:'request',
    },signal)).rejects.toThrow('EXECUTIVE_SEND_SCOPE_REQUIRED');
    expect(e.fetcher.mock.calls.map(([url]) => url)).toEqual([
      ORIGIN + "/os/executive/direct-native/result",
    ]);
  });
  it("uses the existing executive bearer and exact direct bodies without automatic consumption",async()=>{
    const e=setup({executiveResource:resource});await e.login();e.fetcher.mockClear();
    e.fetcher.mockImplementation(async()=>response(unavailable));
    const signal=new AbortController().signal;
    await e.client.executive!.directNative!.read(selection,signal);
    expect(e.fetcher).toHaveBeenCalledTimes(1);
    const consumed={...selection,attempt_id:"ATT-456",result_digest:"d".repeat(64),operation_key:"mmos-consume-fixture"};
    await e.client.executive!.directNative!.consume(consumed,signal);
    expect(e.fetcher.mock.calls.map(([url])=>url)).toEqual([ORIGIN+'/os/executive/direct-native/result',ORIGIN+'/os/executive/direct-native/consume']);
    expect(e.fetcher.mock.calls.map(([,init])=>JSON.parse(String(init?.body)))).toEqual([selection,consumed]);
    for(const [,init] of e.fetcher.mock.calls)expect(init).toMatchObject({method:"POST",redirect:"error",credentials:"omit",cache:"no-store",headers:{Authorization:"Bearer private-token"}});
  });
  it("preserves typed unavailable on503 and rejects duplicate fields before display",async()=>{
    const e=setup({executiveResource:resource});await e.login();e.fetcher.mockClear();
    e.fetcher.mockResolvedValueOnce(new Response(JSON.stringify(unavailable),{status:503,headers:{'content-type':'application/json'}}));
    expect(await e.client.executive!.directNative!.read(selection,new AbortController().signal)).toMatchObject(unavailable);
    e.fetcher.mockResolvedValueOnce(new Response('{"schema":"a","schema":"b"}',{headers:{'content-type':'application/json'}}));
    await expect(e.client.executive!.directNative!.read(selection,new AbortController().signal)).rejects.toThrow('RESPONSE_INVALID_JSON');
    expect(e.fetcher).toHaveBeenCalledTimes(2);
  });
  it("rejects HTTP 400 on the existing direct-native route even with a typed unavailable body", async () => {
    const e = setup({executiveResource: resource});
    await e.login(); e.fetcher.mockClear();
    e.fetcher.mockResolvedValueOnce(new Response(JSON.stringify(unavailable), {
      status: 400, headers: {"content-type": "application/json"},
    }));
    await expect(e.client.executive!.directNative!.read(selection, new AbortController().signal))
      .rejects.toThrow("EXECUTIVE_REQUEST_FAILED");
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });
  it("rejects malformed digest/selection before fetch and fences a late reply after signout",async()=>{
    const e=setup({executiveResource:resource});await e.login();e.fetcher.mockClear();
    await expect(e.client.executive!.directNative!.consume({...selection,attempt_id:'ATT-456',result_digest:'x'+'d'.repeat(64),operation_key:'original'},new AbortController().signal)).rejects.toThrow('DIRECT_SELECTION_INVALID');
    expect(e.fetcher).not.toHaveBeenCalled();
    const pendingResponse=deferred<Response>();e.fetcher.mockReturnValueOnce(pendingResponse.promise);
    const pending=e.client.executive!.directNative!.read(selection,new AbortController().signal);
    const rejected=expect(pending).rejects.toThrow();await e.client.signOut();pendingResponse.resolve(response(unavailable));await rejected;
  });
});

import projectPlanFixture from "./fixtures/project-plan-canonical-owner.json";
describe("canonical project-plan fixed Web READ", () => {
  const selection = { work_ref: "WS:ONE" };
  const request = () => ({ ...selection, signal: new AbortController().signal });
  it("joins the actual Python-owner fixture through the same acquired identity without a Job", async () => {
    const e = setup();
    const host = bindMissionHost(e.client);
    await expect(host.readProjectPlan!(request())).rejects.toThrow("PROJECT_PLAN_READ_UNAUTHORIZED");
    expect(e.fetcher).not.toHaveBeenCalled();
    await e.login(); e.fetcher.mockClear();
    e.fetcher.mockResolvedValueOnce(response(projectPlanFixture));
    const value = await host.readProjectPlan!(request());
    expect(value.availability).toBe("AVAILABLE");
    if (value.availability !== "AVAILABLE") throw Error("expected actual plan content");
    expect(value.plan.objective).toBe("Deliver the real owner content.");
    const [url, options] = e.fetcher.mock.calls[0];
    expect(new URL(String(url)).pathname).toBe("/workspace/project-plan/current");
    expect(Object.fromEntries(new URL(String(url)).searchParams)).toEqual(selection);
    expect(options).toMatchObject({ method: "GET", credentials: "omit", redirect: "error", cache: "no-store" });
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });
  it("retains typed unavailable and treats an old backend404 as a failed read", async () => {
    const e = setup(); await e.login(); e.fetcher.mockClear();
    const body = { ...projectPlanFixture, availability: "UNAVAILABLE", source: null, plan: null, reason_codes: ["SOURCE_UNAVAILABLE"] };
    e.fetcher.mockResolvedValueOnce(new Response(JSON.stringify(body), { status: 503, headers: { "content-type": "application/json" } }));
    await expect(bindMissionHost(e.client).readProjectPlan!(request())).resolves.toMatchObject({ availability: "UNAVAILABLE", plan: null });
    e.fetcher.mockResolvedValueOnce(new Response("missing", { status: 404 }));
    await expect(bindMissionHost(e.client).readProjectPlan!(request())).rejects.toThrow();
    expect(e.fetcher).toHaveBeenCalledTimes(2);
  });
  it("discards the actual body on identity revocation and never retries", async () => {
    const e = setup(); await e.login(); e.fetcher.mockClear();
    const late = deferred<Response>(); e.fetcher.mockReturnValueOnce(late.promise);
    const host = bindMissionHost(e.client);
    const pending = host.readProjectPlan!(request());
    const rejected = expect(pending).rejects.toThrow();
    await host.auth!.signOut(); late.resolve(response(projectPlanFixture));
    await rejected;
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });
  it("rejects wrong selection and oversized JSON before display", async () => {
    const e = setup(); await e.login(); e.fetcher.mockClear();
    e.fetcher.mockResolvedValueOnce(response({ ...projectPlanFixture, selection: { work_ref: "WS:OTHER" } }));
    await expect(bindMissionHost(e.client).readProjectPlan!(request())).rejects.toThrow("PROJECT_PLAN_INVALID");
    e.fetcher.mockResolvedValueOnce(response({ ...projectPlanFixture, padding: "漢".repeat(50_000) }));
    await expect(bindMissionHost(e.client).readProjectPlan!(request())).rejects.toThrow();
  });
});

import projectJournalFixture from "./fixtures/project-journal-canonical-owner.json";
describe("canonical project-journal fixed Web READ", () => {
  const selection = { work_ref: "WS:ONE" };
  const request = () => ({ ...selection, signal: new AbortController().signal });
  it("joins the actual Python-owner fixture through the same acquired identity without a Job", async () => {
    const e = setup();
    const host = bindMissionHost(e.client);
    await expect(host.readProjectJournal!(request())).rejects.toThrow("PROJECT_JOURNAL_READ_UNAUTHORIZED");
    expect(e.fetcher).not.toHaveBeenCalled();
    await e.login(); e.fetcher.mockClear();
    e.fetcher.mockResolvedValueOnce(response(projectJournalFixture));
    const value = await host.readProjectJournal!(request());
    expect(value.availability).toBe("AVAILABLE");
    if (value.availability !== "AVAILABLE") throw Error("expected actual plan content");
    expect(value.journal?.entries[0].title).toBe("The original implementation returned.");
    const [url, options] = e.fetcher.mock.calls[0];
    expect(new URL(String(url)).pathname).toBe("/workspace/project-journal/current");
    expect(Object.fromEntries(new URL(String(url)).searchParams)).toEqual(selection);
    expect(options).toMatchObject({ method: "GET", credentials: "omit", redirect: "error", cache: "no-store" });
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });
  it("retains typed unavailable and treats an old backend404 as a failed read", async () => {
    const e = setup(); await e.login(); e.fetcher.mockClear();
    const body = { ...projectJournalFixture, availability: "UNAVAILABLE", source: null, journal: null, reason_codes: ["SOURCE_UNAVAILABLE"] };
    e.fetcher.mockResolvedValueOnce(new Response(JSON.stringify(body), { status: 503, headers: { "content-type": "application/json" } }));
    await expect(bindMissionHost(e.client).readProjectJournal!(request())).resolves.toMatchObject({ availability: "UNAVAILABLE", journal: null });
    e.fetcher.mockResolvedValueOnce(new Response("missing", { status: 404 }));
    await expect(bindMissionHost(e.client).readProjectJournal!(request())).rejects.toThrow();
    expect(e.fetcher).toHaveBeenCalledTimes(2);
  });
  it("discards the actual body on identity revocation and never retries", async () => {
    const e = setup(); await e.login(); e.fetcher.mockClear();
    const late = deferred<Response>(); e.fetcher.mockReturnValueOnce(late.promise);
    const host = bindMissionHost(e.client);
    const pending = host.readProjectJournal!(request());
    const rejected = expect(pending).rejects.toThrow();
    await host.auth!.signOut(); late.resolve(response(projectJournalFixture));
    await rejected;
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });
  it("rejects wrong selection and oversized JSON before display", async () => {
    const e = setup(); await e.login(); e.fetcher.mockClear();
    e.fetcher.mockResolvedValueOnce(response({ ...projectJournalFixture, selection: { work_ref: "WS:OTHER" } }));
    await expect(bindMissionHost(e.client).readProjectJournal!(request())).rejects.toMatchObject({ name: "PROJECT_JOURNAL_INVALID" });
    e.fetcher.mockResolvedValueOnce(response({ ...projectJournalFixture, padding: "漢".repeat(50_000) }));
    await expect(bindMissionHost(e.client).readProjectJournal!(request())).rejects.toThrow();
  });
});

import autonomyFixture from "./supervision/autonomy-policy.producer-fixture.json";
describe("selected-root autonomy fixed Web READ", () => {
 const selection = autonomyFixture.selection;
 const request = () => ({...selection,signal:new AbortController().signal});
 it("requires current Acquisition auth and uses only the fixed exact selected-root GET", async () => {
  const e=setup(),host=bindMissionHost(e.client);
  await expect(host.readAutonomyPolicy!(request())).rejects.toThrow("AUTONOMY_READ_UNAUTHORIZED");
  expect(e.fetcher).not.toHaveBeenCalled();
  await e.login();e.fetcher.mockClear();e.fetcher.mockResolvedValueOnce(response(autonomyFixture));
  expect(await host.readAutonomyPolicy!(request())).toEqual(autonomyFixture);
  const [url,options]=e.fetcher.mock.calls[0];
  expect(new URL(String(url)).origin).toBe(ORIGIN);
  expect(new URL(String(url)).pathname).toBe("/workspace/autonomy/current");
  expect(Object.fromEntries(new URL(String(url)).searchParams)).toEqual(selection);
  expect(options).toMatchObject({method:"GET",credentials:"omit",redirect:"error",cache:"no-store"});
  expect(e.fetcher).toHaveBeenCalledTimes(1);
 });
 it("retains only closed typed503 unavailable and fails old404", async () => {
  const e=setup();await e.login();e.fetcher.mockClear();const host=bindMissionHost(e.client);
  const body={...autonomyFixture,availability:"UNAVAILABLE",policy:null,source_observation:null,reason_codes:["SOURCE_UNAVAILABLE"]};
  e.fetcher.mockResolvedValueOnce(new Response(JSON.stringify(body),{status:503,headers:{"content-type":"application/json"}}));
  await expect(host.readAutonomyPolicy!(request())).resolves.toMatchObject(body);
  e.fetcher.mockResolvedValueOnce(new Response("missing",{status:404}));
  await expect(host.readAutonomyPolicy!(request())).rejects.toThrow();
 });
 it("withholds late private data after signout without retry", async () => {
  const e=setup();await e.login();e.fetcher.mockClear();const host=bindMissionHost(e.client);
  const late=deferred<Response>();e.fetcher.mockReturnValueOnce(late.promise);
  const pending=host.readAutonomyPolicy!(request()),rejected=expect(pending).rejects.toThrow();
  await host.auth!.signOut();late.resolve(response(autonomyFixture));await rejected;
  expect(e.fetcher).toHaveBeenCalledTimes(1);
 });
 it("rejects foreign-root, unknown fields, malformed selectors and over-cap UTF8 before display", async () => {
  const e=setup();await e.login();e.fetcher.mockClear();const host=bindMissionHost(e.client);
  await expect(host.readAutonomyPolicy!({...request(),work_ref:"WS:ONE\n"})).rejects.toThrow("AUTONOMY_SELECTION_INVALID");
  expect(e.fetcher).not.toHaveBeenCalled();
  for(const body of [
   {...autonomyFixture,selection:{...selection,root_job_id:"JOB-2"}},
   {...autonomyFixture,granted:true},
   {...autonomyFixture,padding:"漢".repeat(12_000)},
  ]) {e.fetcher.mockResolvedValueOnce(response(body));await expect(host.readAutonomyPolicy!(request())).rejects.toThrow();}
  expect(e.fetcher).toHaveBeenCalledTimes(3);
 });
});

import resourceCapacityFixture from "./resources/fixtures/resource-capacity-owner-read.json";
describe("selected-work resource capacity fixed Web READ", () => {
 const selection = resourceCapacityFixture.selection;
 const request = () => ({ ...selection, signal: new AbortController().signal });
 it("requires Acquisition and reads only the exact fixed four-field GET", async () => {
  const e=setup(), host=bindMissionHost(e.client);
  await expect(host.readResourceCapacity!(request())).rejects.toThrow("RESOURCE_CAPACITY_UNAUTHORIZED");
  expect(e.fetcher).not.toHaveBeenCalled();
  await e.login(); e.fetcher.mockClear(); e.fetcher.mockResolvedValueOnce(response(resourceCapacityFixture));
  expect((await host.readResourceCapacity!(request())).state).toBe("AVAILABLE");
  const [url,options]=e.fetcher.mock.calls[0];
  expect(new URL(String(url)).origin).toBe(ORIGIN);
  expect(new URL(String(url)).pathname).toBe("/workspace/resources/capacity/current");
  expect(Object.fromEntries(new URL(String(url)).searchParams)).toEqual(selection);
  expect(options).toMatchObject({method:"GET",credentials:"omit",redirect:"error",cache:"no-store"});
  expect(e.fetcher).toHaveBeenCalledTimes(1);
 });
 it("keeps only typed unavailable503 and refuses older404 without a fallback", async () => {
  const e=setup(); await e.login();e.fetcher.mockClear(); const host=bindMissionHost(e.client);
  const body={...resourceCapacityFixture,availability:"UNAVAILABLE",provider_capacity:null,source_observation:null,reason_codes:["SOURCE_UNAVAILABLE"]};
  e.fetcher.mockResolvedValueOnce(new Response(JSON.stringify(body),{status:503,headers:{"content-type":"application/json"}}));
  await expect(host.readResourceCapacity!(request())).resolves.toEqual({state:"UNAVAILABLE"});
  e.fetcher.mockResolvedValueOnce(new Response("missing",{status:404}));
  await expect(host.readResourceCapacity!(request())).rejects.toThrow();
  expect(e.fetcher).toHaveBeenCalledTimes(2);
 });
 it("discards a late body after signout without retry", async () => {
  const e=setup();await e.login();e.fetcher.mockClear();const host=bindMissionHost(e.client);
  const late=deferred<Response>();e.fetcher.mockReturnValueOnce(late.promise);
  const pending=host.readResourceCapacity!(request()),rejected=expect(pending).rejects.toThrow();
  await host.auth!.signOut();late.resolve(response(resourceCapacityFixture));await rejected;
  expect(e.fetcher).toHaveBeenCalledTimes(1);
 });
 it("refuses host selectors, foreign Attempt, raw extras and over16KiB bodies", async () => {
  const e=setup();await e.login();e.fetcher.mockClear();const host=bindMissionHost(e.client);
  await expect(host.readResourceCapacity!({...request(),host_ref:"supplied"} as never)).rejects.toThrow("RESOURCE_CAPACITY_SELECTION_INVALID");
  expect(e.fetcher).not.toHaveBeenCalled();
  e.fetcher.mockResolvedValueOnce(response({...resourceCapacityFixture,selection:{...selection,attempt_id:"ATT-"+"9".repeat(32)}}));
  await expect(host.readResourceCapacity!(request())).rejects.toThrow("RESOURCE_CAPACITY_INVALID");
  e.fetcher.mockResolvedValueOnce(response({...resourceCapacityFixture,padding:"漢".repeat(6000)}));
  await expect(host.readResourceCapacity!(request())).rejects.toThrow();
 });
});

import planV2Fixture from "./fixtures/project-plan-v2-owner.json";
it("joins actual Python v2 continuity through the existing authenticated fixed Web read", async () => {
  const e = setup(); await e.login(); e.fetcher.mockClear();
  const selection = { work_ref: "WS:PLAN-TEST" };
  e.fetcher.mockResolvedValueOnce(response(planV2Fixture.cases.available_pending));
  const value = await bindMissionHost(e.client).readProjectPlan!({ ...selection, signal: new AbortController().signal });
  expect(value).toEqual(planV2Fixture.cases.available_pending);
  const [url, options] = e.fetcher.mock.calls[0];
  expect(new URL(String(url)).pathname).toBe("/workspace/project-plan/current");
  expect(Object.fromEntries(new URL(String(url)).searchParams)).toEqual(selection);
  expect(options).toMatchObject({ method: "GET", credentials: "omit", redirect: "error", cache: "no-store" });
  expect(e.fetcher).toHaveBeenCalledTimes(1);
});

import projectSessionFixture from "./fixtures/project-session-association-producer.json";
describe("project-session fixed Web READ", () => {
  const request = () => ({ workRef: projectSessionFixture.selection.work_ref, rootJobId: projectSessionFixture.selection.root_job_id, signal: new AbortController().signal });
  it("uses actual paired owner body and one fixed acquisition route", async () => {
    const e = setup(); const host = bindMissionHost(e.client);
    await expect(host.readProjectSessionAssociation!(request())).rejects.toThrow("PROJECT_SESSION_READ_UNAUTHORIZED");
    expect(e.fetcher).not.toHaveBeenCalled();
    await e.login(); e.fetcher.mockClear(); e.fetcher.mockResolvedValueOnce(response(projectSessionFixture));
    await expect(host.readProjectSessionAssociation!(request())).resolves.toEqual(projectSessionFixture);
    const [url, options] = e.fetcher.mock.calls[0];
    expect(new URL(String(url)).pathname).toBe("/workspace/project-session/current");
    expect(Object.fromEntries(new URL(String(url)).searchParams)).toEqual(projectSessionFixture.selection);
    expect(options).toMatchObject({ method: "GET", credentials: "omit", redirect: "error", cache: "no-store" });
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });
  it("withholds late owner body after sign-out and never retries", async () => {
    const e = setup(); await e.login(); e.fetcher.mockClear();
    const late = deferred<Response>(); e.fetcher.mockReturnValueOnce(late.promise);
    const host = bindMissionHost(e.client); const pending = host.readProjectSessionAssociation!(request());
    const rejected = expect(pending).rejects.toThrow();
    await host.auth!.signOut(); late.resolve(response(projectSessionFixture)); await rejected;
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });
});

import acceptedDirectionFixture from "./direction/fixtures/accepted-direction-owner.json";
describe("canonical accepted Direction fixed Web READ", () => {
  const selected = acceptedDirectionFixture.selection;
  const request = () => ({ ...selected, signal: new AbortController().signal });
  it("uses the existing Acquisition identity for one fixed rootless GET", async () => {
    const e = setup(); const host = bindMissionHost(e.client);
    await expect(host.readProjectDirection!(request())).rejects.toThrow("DIRECTION_READ_UNAUTHORIZED");
    expect(e.fetcher).not.toHaveBeenCalled();
    await e.login(); e.fetcher.mockClear();
    e.fetcher.mockResolvedValueOnce(response(acceptedDirectionFixture));
    expect((await host.readProjectDirection!(request())).availability).toBe("AVAILABLE");
    const [url, options] = e.fetcher.mock.calls[0];
    expect(new URL(String(url)).pathname).toBe("/workspace/project-direction/current");
    expect(Object.fromEntries(new URL(String(url)).searchParams)).toEqual(selected);
    expect(options).toMatchObject({ method: "GET", credentials: "omit", redirect: "error", cache: "no-store" });
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });
  it("retains typed absence and rejects an unsupported old backend response", async () => {
    const e = setup(); await e.login(); e.fetcher.mockClear();
    const absent = { ...acceptedDirectionFixture, availability: "UNAVAILABLE", source: null, direction: null, reason_codes: ["NOT_DECLARED"] };
    e.fetcher.mockResolvedValueOnce(new Response(JSON.stringify(absent), { status: 503, headers: { "content-type": "application/json" } }));
    await expect(bindMissionHost(e.client).readProjectDirection!(request())).resolves.toMatchObject({ availability: "UNAVAILABLE", direction: null });
    e.fetcher.mockResolvedValueOnce(new Response("not installed", { status: 404 }));
    await expect(bindMissionHost(e.client).readProjectDirection!(request())).rejects.toThrow();
    expect(e.fetcher).toHaveBeenCalledTimes(2);
  });
  it("discards a reply after identity loss without a second request", async () => {
    const e = setup(); await e.login(); e.fetcher.mockClear();
    const late = deferred<Response>(); e.fetcher.mockReturnValueOnce(late.promise);
    const host = bindMissionHost(e.client); const pending = host.readProjectDirection!(request());
    const rejected = expect(pending).rejects.toThrow();
    await host.auth!.signOut(); late.resolve(response(acceptedDirectionFixture)); await rejected;
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });
  it("rejects caller selectors, source substitution and oversized raw responses", async () => {
    const e = setup(); await e.login(); e.fetcher.mockClear(); const host = bindMissionHost(e.client);
    await expect(host.readProjectDirection!({ ...request(), commit: "a".repeat(40) } as never)).rejects.toThrow("DIRECTION_SELECTION_INVALID");
    expect(e.fetcher).not.toHaveBeenCalled();
    e.fetcher.mockResolvedValueOnce(response({ ...acceptedDirectionFixture, selection: { work_ref: "WS:OTHER" } }));
    await expect(host.readProjectDirection!(request())).rejects.toThrow("DIRECTION_INVALID");
    e.fetcher.mockResolvedValueOnce(response({ padding: "x".repeat(65_537) }));
    await expect(host.readProjectDirection!(request())).rejects.toThrow();
  });
});

import admissionFixture from './admission/fixtures/project-admission-owner.json';
import instructionFixture from './instructions/fixtures/instruction-owner.json';
describe('fixed authenticated instruction Web transport',()=>{
 const selection={work_ref:'WS:ONE',instruction_ref:'INS:DAILY-ONE'},command_id=instructionFixture.status.selection.command_id;
 const request=()=>({selection,command_id,expected_revision:instructionFixture.current.instruction_revision,expected_source:{...instructionFixture.current.source,repository:'mastermindx-market-intelligence/macro' as const},signal:new AbortController().signal});
 it('joins owner content/current/status GETs and one explicit fixed-origin instruction pause',async()=>{
  const e=setup();await e.login();e.fetcher.mockClear();const host=bindMissionHost(e.client),signal=request().signal;
  e.fetcher.mockResolvedValueOnce(response(instructionFixture.project_only_empty));await expect(host.readProjectInstructions!({selection:{work_ref:'WS:ONE'},signal})).resolves.toEqual(instructionFixture.project_only_empty);
  e.fetcher.mockResolvedValueOnce(response(instructionFixture.current));await expect(host.readInstructionAdmissionControl!({selection,signal})).resolves.toEqual(instructionFixture.current);
  e.fetcher.mockResolvedValueOnce(response(instructionFixture.unknown));await host.pauseInstructionAdmission!(request());
  e.fetcher.mockResolvedValueOnce(response(instructionFixture.status));await host.readInstructionAdmissionOperation!({selection,command_id,signal});
  expect(e.fetcher.mock.calls.map(([url,options])=>[new URL(String(url)).origin,new URL(String(url)).pathname,options?.method])).toEqual([[ORIGIN,'/workspace/project-instructions/current','GET'],[ORIGIN,'/workspace/instruction-admission/current','GET'],[ORIGIN,'/workspace/instruction-admission/pause','POST'],[ORIGIN,'/workspace/instruction-admission/operation','GET']]);
  const post=e.fetcher.mock.calls[2][1];expect(post).toMatchObject({redirect:'error',credentials:'omit',cache:'no-store'});
  expect(JSON.parse(String(post?.body))).toEqual({selection,command_id,expected_revision:instructionFixture.current.instruction_revision,expected_source:instructionFixture.current.source});
  expect(Object.fromEntries(new URL(String(e.fetcher.mock.calls[3][0])).searchParams)).toEqual({...selection,command_id});
 });
 it('refuses missing authentication and caller authority before sending',async()=>{
  const e=setup(),host=bindMissionHost(e.client);await expect(host.pauseInstructionAdmission!(request())).rejects.toThrow();expect(e.fetcher).not.toHaveBeenCalled();
  await e.login();e.fetcher.mockClear();await expect(host.pauseInstructionAdmission!({...request(),principal:'forged'} as never)).rejects.toThrow();expect(e.fetcher).not.toHaveBeenCalled();
 });
 it('withholds a late mutation result on auth departure without resending',async()=>{
  const e=setup();await e.login();e.fetcher.mockClear();const host=bindMissionHost(e.client),late=deferred<Response>();e.fetcher.mockReturnValueOnce(late.promise);
  const pending=host.pauseInstructionAdmission!(request()),rejected=expect(pending).rejects.toThrow();await host.auth!.signOut();late.resolve(response(instructionFixture.unknown));await rejected;expect(e.fetcher).toHaveBeenCalledTimes(1);
 });
 it('keeps the same original request through bounded response and timeout failures',async()=>{
  const e=setup();await e.login();e.fetcher.mockClear();const host=bindMissionHost(e.client);
  e.fetcher.mockResolvedValueOnce(response({padding:'x'.repeat(32769)}));await expect(host.pauseInstructionAdmission!(request())).rejects.toThrow();expect(e.fetcher).toHaveBeenCalledTimes(1);
  e.fetcher.mockImplementationOnce(()=>new Promise(()=>{}));const pending=host.pauseInstructionAdmission!(request()),rejected=expect(pending).rejects.toThrow();await vi.advanceTimersByTimeAsync(60_001);await rejected;expect(e.fetcher).toHaveBeenCalledTimes(2);
  for(const [,options] of e.fetcher.mock.calls)expect(JSON.parse(String(options?.body)).command_id).toBe(command_id);
 });
});
describe('fixed authenticated project admission Web transport',()=>{
 const selection=admissionFixture.open.selection;
 const command_id='mmos-project-pause-'+'a'.repeat(40);
 const request=()=>({selection,signal:new AbortController().signal});
 it('joins closed current and original status GETs plus one explicit Pause POST on fixed acquisition origin',async()=>{
  const e=setup();await e.login();e.fetcher.mockClear();const host=bindMissionHost(e.client);
  e.fetcher.mockResolvedValueOnce(response(admissionFixture.open));
  await expect(host.readProjectAdmissionControl!(request())).resolves.toEqual(admissionFixture.open);
  e.fetcher.mockResolvedValueOnce(response(admissionFixture.pause_result));
  await host.pauseProjectAdmission!({...request(),command_id});
  e.fetcher.mockResolvedValueOnce(response(admissionFixture.pause_result));
  await host.readProjectAdmissionOperation!({...request(),command_id,kind:'project_pause'});
  expect(e.fetcher.mock.calls.map(([url,options])=>[new URL(String(url)).origin,new URL(String(url)).pathname,options?.method])).toEqual([
   [ORIGIN,'/workspace/project-admission/current','GET'],[ORIGIN,'/workspace/project-admission/pause','POST'],[ORIGIN,'/workspace/project-admission/operation','GET']
  ]);
  const post=e.fetcher.mock.calls[1][1];expect(post).toMatchObject({redirect:'error',credentials:'omit',cache:'no-store'});
  expect(JSON.parse(String(post?.body))).toEqual({selection,command_id});
  expect(Object.fromEntries(new URL(String(e.fetcher.mock.calls[2][0])).searchParams)).toEqual({...selection,command_id,kind:'project_pause'});
 });
 it('never dispatches without login or when request contains caller authority/private fields',async()=>{
  const e=setup(),host=bindMissionHost(e.client);
  await expect(host.pauseProjectAdmission!({...request(),command_id})).rejects.toThrow();expect(e.fetcher).not.toHaveBeenCalled();
  await e.login();e.fetcher.mockClear();
  await expect(host.pauseProjectAdmission!({...request(),command_id,principal:'caller'} as never)).rejects.toThrow();expect(e.fetcher).not.toHaveBeenCalled();
 });
 it('withholds late mutation result after auth departure and never resends',async()=>{
  const e=setup();await e.login();e.fetcher.mockClear();const host=bindMissionHost(e.client),late=deferred<Response>();
  e.fetcher.mockReturnValueOnce(late.promise);
  const pending=host.pauseProjectAdmission!({...request(),command_id}),rejected=expect(pending).rejects.toThrow();
  await host.auth!.signOut();late.resolve(response(admissionFixture.pause_result));await rejected;expect(e.fetcher).toHaveBeenCalledTimes(1);
 });
 it('bounds streamed action responses and closes a timed-out original without a replacement',async()=>{
  const e=setup();await e.login();e.fetcher.mockClear();const host=bindMissionHost(e.client);
  e.fetcher.mockResolvedValueOnce(response({padding:'x'.repeat(32769)}));
  await expect(host.pauseProjectAdmission!({...request(),command_id})).rejects.toThrow();expect(e.fetcher).toHaveBeenCalledTimes(1);
  e.fetcher.mockImplementationOnce(()=>new Promise(()=>{}));
  const pending=host.pauseProjectAdmission!({...request(),command_id}),rejected=expect(pending).rejects.toThrow();
  await vi.advanceTimersByTimeAsync(60_001);await rejected;expect(e.fetcher).toHaveBeenCalledTimes(2);
 });
});

import projectArchiveFixture from "./projects/archive/fixtures/project-archive-owner.json";
describe("canonical archive fixed Web READ", () => {
  const request = () => ({ signal: new AbortController().signal });
  it("uses one fixed rootless Acquisition GET and actual native helper body", async () => {
    const e = setup(); const host = bindMissionHost(e.client);
    await expect(host.readProjectArchive!(request())).rejects.toThrow("PROJECT_ARCHIVE_READ_UNAUTHORIZED");
    expect(e.fetcher).not.toHaveBeenCalled();
    await e.login(); e.fetcher.mockClear(); e.fetcher.mockResolvedValueOnce(response(projectArchiveFixture));
    await expect(host.readProjectArchive!(request())).resolves.toEqual(projectArchiveFixture);
    const [url, options] = e.fetcher.mock.calls[0];
    expect(new URL(String(url)).pathname).toBe("/workspace/projects/archive/current");
    expect(new URL(String(url)).search).toBe("");
    expect(options).toMatchObject({ method: "GET", credentials: "omit", redirect: "error", cache: "no-store" });
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });
  it("preserves unavailable sample without inventing empty archives", async () => {
    const e = setup(); await e.login(); e.fetcher.mockClear();
    const absent = { schema: "mastermind.workspace_project_archive.v1", availability: "UNAVAILABLE", catalogue: null, sample: null, reason_codes: ["SOURCE_UNAVAILABLE"] };
    e.fetcher.mockResolvedValueOnce(new Response(JSON.stringify(absent), { status: 503, headers: { "content-type": "application/json" } }));
    await expect(bindMissionHost(e.client).readProjectArchive!(request())).resolves.toMatchObject({ availability: "UNAVAILABLE", sample: null });
    e.fetcher.mockResolvedValueOnce(new Response("not installed", { status: 404 }));
    await expect(bindMissionHost(e.client).readProjectArchive!(request())).rejects.toThrow();
  });
  it("withholds late archive content after identity loss without a retry", async () => {
    const e = setup(); await e.login(); e.fetcher.mockClear();
    const late = deferred<Response>(); e.fetcher.mockReturnValueOnce(late.promise);
    const host = bindMissionHost(e.client); const pending = host.readProjectArchive!(request());
    const rejected = expect(pending).rejects.toThrow();
    await host.auth!.signOut(); late.resolve(response(projectArchiveFixture)); await rejected;
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });
  it("refuses caller members and oversized raw bodies", async () => {
    const e = setup(); await e.login(); e.fetcher.mockClear(); const host = bindMissionHost(e.client);
    await expect(host.readProjectArchive!({ ...request(), work_refs: ["WS:FOREIGN"] } as never)).rejects.toThrow("PROJECT_ARCHIVE_REQUEST_INVALID");
    expect(e.fetcher).not.toHaveBeenCalled();
    e.fetcher.mockResolvedValueOnce(response({ padding: "x".repeat(262_145) }));
    await expect(host.readProjectArchive!(request())).rejects.toThrow();
  });
});


describe("canonical archive continuation Web READ", () => {
  const cursor = { after_work_ref: projectArchiveFixture.catalogue.work_refs[0]!, catalogue_digest: projectArchiveFixture.catalogue.document_digest };
  const request = () => ({ ...cursor, signal: new AbortController().signal });
  it("uses only the same fixed GET with the member anchor and catalogue digest", async () => {
    const e = setup(); await e.login(); e.fetcher.mockClear();
    const page = structuredClone(projectArchiveFixture); page.catalogue.work_refs = [projectArchiveFixture.catalogue.work_refs[1]!]; page.sample.items = [];
    page.sample.coverage.supplied_count = 1; page.sample.coverage.observed_count = 1;
    e.fetcher.mockResolvedValueOnce(response(page));
    await expect(bindMissionHost(e.client).readProjectArchivePage!(request())).resolves.toEqual(page);
    const [url, options] = e.fetcher.mock.calls[0];
    expect(new URL(String(url)).pathname).toBe("/workspace/projects/archive/current");
    expect(Object.fromEntries(new URL(String(url)).searchParams)).toEqual(cursor);
    expect(options).toMatchObject({ method: "GET", credentials: "omit", redirect: "error", cache: "no-store" });
  });
  it("rejects private selectors and changed catalogue replies without a retry", async () => {
    const e = setup(); await e.login(); e.fetcher.mockClear(); const host = bindMissionHost(e.client);
    await expect(host.readProjectArchivePage!({ ...request(), work_refs: ["WS:FOREIGN"] } as never)).rejects.toThrow("PROJECT_ARCHIVE_REQUEST_INVALID");
    expect(e.fetcher).not.toHaveBeenCalled();
    const changed = structuredClone(projectArchiveFixture); changed.catalogue.document_digest = "f".repeat(64);
    e.fetcher.mockResolvedValueOnce(response(changed));
    await expect(host.readProjectArchivePage!(request())).rejects.toThrow("PROJECT_ARCHIVE_PAGE_CHANGED");
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });
});
import projectAccessFixture from './access/fixtures/current-grants.json';
import projectAccessV5Fixture from './access/fixtures/v5-current-grants.json';
describe('fixed current project access Web read',()=>{
 const request=()=>({selection:{work_ref:'WS:ONE'},signal:new AbortController().signal});
 it('uses only fixed Acquisition GET and preserves the bounded unavailable body',async()=>{
  const e=setup();await e.login();e.fetcher.mockClear();const host=bindMissionHost(e.client);
  e.fetcher.mockResolvedValueOnce(response(projectAccessFixture));
  await expect(host.readProjectAccess!(request())).resolves.toEqual(projectAccessFixture);
  const [url,options]=e.fetcher.mock.calls[0];
  expect(new URL(String(url)).origin).toBe(ORIGIN);expect(new URL(String(url)).pathname).toBe('/workspace/project-access/current');
  expect(Object.fromEntries(new URL(String(url)).searchParams)).toEqual({work_ref:'WS:ONE'});
  expect(options).toMatchObject({method:'GET',redirect:'error',credentials:'omit',cache:'no-store'});
  e.fetcher.mockResolvedValueOnce(response(projectAccessV5Fixture));await expect(host.readProjectAccess!(request())).resolves.toEqual(projectAccessV5Fixture);
  const unavailable={schema:projectAccessFixture.schema,selection:projectAccessFixture.selection,availability:'UNAVAILABLE',source:null,membership:null,declaration:null,grants:null,reason_codes:['SOURCE_UNAVAILABLE']};
  e.fetcher.mockResolvedValueOnce(new Response(JSON.stringify(unavailable),{status:503,headers:{'Content-Type':'application/json'}}));
  await expect(host.readProjectAccess!(request())).resolves.toEqual(unavailable);
 });
 it('refuses login absence, extra selector and oversized grant bodies without a second request',async()=>{
  const e=setup(),host=bindMissionHost(e.client);await expect(host.readProjectAccess!(request())).rejects.toThrow();expect(e.fetcher).not.toHaveBeenCalled();
  await e.login();e.fetcher.mockClear();await expect(host.readProjectAccess!({...request(),principal:'forged'} as never)).rejects.toThrow();expect(e.fetcher).not.toHaveBeenCalled();
  e.fetcher.mockResolvedValueOnce(response({padding:'x'.repeat(16385)}));await expect(host.readProjectAccess!(request())).rejects.toThrow();expect(e.fetcher).toHaveBeenCalledTimes(1);
 });
 it('withholds late access facts after sign-out with no retry',async()=>{
  const e=setup();await e.login();e.fetcher.mockClear();const host=bindMissionHost(e.client),late=deferred<Response>();e.fetcher.mockReturnValueOnce(late.promise);
  const pending=host.readProjectAccess!(request()),rejected=expect(pending).rejects.toThrow();await host.auth!.signOut();late.resolve(response(projectAccessFixture));await rejected;
  expect(e.fetcher).toHaveBeenCalledTimes(1);
 });
});

describe("project history fixed READ",()=>{
  const historyResource="https://mcp.mastermind-x.com/os/executive";
  const executionReference = {
    schema:"mastermind.project_execution_reference.v1",work_ref:"WS:PROJECT-ONE",root_job_id:"JOB-123",root_event_id:42,
    root_event_sha256:"a".repeat(64),project_execution_source_sha256:"b".repeat(64),principal_scope_sha256:"c".repeat(64),
  };
  async function readOnlyHistory(){
    const e=setup({executiveResource:historyResource});
    e.fetcher.mockImplementation(async()=>response({token_type:"Bearer",access_token:"private-token",expires_in:3600,
      scope:new URL(e.popup.location).searchParams.get("audience")===historyResource
        ?"mastermind.executive.read":new URL(e.popup.location).searchParams.get("scope")}));
    await e.login();e.fetcher.mockClear();return e;
  }
  it("sends six literal conversation READs with exact arguments and READ-only authority",async()=>{
    const e=await readOnlyHistory(),signal=new AbortController().signal;
    e.fetcher.mockImplementation(async()=>response({inertTransportResult:true}));
    const transport=e.client.executiveSession!.projectConversations!;
    const cases=[
      ["catalogue","conversations",{work_ref:projectConversationLegacy.catalogue.work_ref}],
      ["read","conversation-read",projectConversationLegacy.selection],
      ["fresh_references","fresh-conversations",{work_ref:projectConversationFresh.catalogue.work_ref}],
      ["fresh_read","fresh-conversation-read",projectConversationFresh.initial_read.reference],
      ["execution_references","project-executions",{work_ref:executionReference.work_ref}],
      ["execution_read","project-execution-read",executionReference],
    ] as const;
    for(const [operation,path,args] of cases){
      await transport.request(operation,args,signal);
      const [url,request]=e.fetcher.mock.calls.at(-1)!;
      expect(url).toBe(ORIGIN+"/os/executive/session/"+path);
      expect(JSON.parse(request!.body as string)).toEqual({arguments:args});
      expect(new Headers(request!.headers).has("x-mastermind-workspace-authorization")).toBe(false);
    }
    expect(e.fetcher).toHaveBeenCalledTimes(6);
  });
  it("refuses foreign project execution selectors before a network request or accessor evaluation",async()=>{
    const e=setup({executiveResource:historyResource}),signal=new AbortController().signal;
    const transport=e.client.executiveSession!.projectConversations!,getter=vi.fn(()=>executionReference.work_ref);
    for(const value of [Object.defineProperty({...executionReference},"work_ref",{get:getter}),
      {...executionReference,root_job_id:"JOB-invented"},{...executionReference,root_event_id:true},
      {...executionReference,principal_scope_sha256:"short"},{...executionReference,operation_key:"forged"}]) {
      await expect(transport.request("execution_read",value,signal)).rejects.toThrow("PROJECT_CONVERSATION_SELECTION_INVALID");
    }
    await expect(transport.request("execution_references",{work_ref:"WS:project.a_1"},signal)).rejects.toThrow();
    await expect(transport.request("execution_references",{work_ref:executionReference.work_ref,cursor:null},signal)).rejects.toThrow();
    expect(getter).not.toHaveBeenCalled();expect(e.fetcher).not.toHaveBeenCalled();
  });
  it.each(["execution_references","execution_read"] as const)("discards delayed %s after the existing Executive auth generation ends",async operation=>{
    const e=await readOnlyHistory(),held=deferred<Response>();e.fetcher.mockReturnValue(held.promise);
    const args=operation==="execution_read"?executionReference:{work_ref:executionReference.work_ref};
    const pending=e.client.executiveSession!.projectConversations!.request(operation,args,new AbortController().signal);
    const rejected=expect(pending).rejects.toThrow("EXECUTIVE_REQUEST_CANCELLED");
    await e.client.signOut();held.resolve(response({inertTransportResult:true}));await rejected;
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });
  it("sends only the direct work selection with READ-only Executive authority and never widens SEND",async()=>{
    const e=await readOnlyHistory(),signal=new AbortController().signal;
    e.fetcher.mockImplementation(async()=>response({ok:true}));
    await e.client.executiveSession!.historyContext!({workRef:"WS:Original.Project"},signal);
    expect(e.fetcher).toHaveBeenCalledTimes(1);
    const [url,request]=e.fetcher.mock.calls[0];
    expect(url).toBe(ORIGIN+"/os/executive/session/history-context");
    expect(JSON.parse(request!.body as string)).toEqual({selection:{work_ref:"WS:Original.Project"}});
    const headers=new Headers(request!.headers);
    expect(headers.has("x-mastermind-workspace-authorization")).toBe(false);
    await expect(e.client.executiveSession!.send({operation_key:"inert-original",target_ref:"fabric_attempt:"+"a".repeat(64),instruction:"inert message",stop_condition:"finish"},signal)).rejects.toThrow("EXECUTIVE_SEND_SCOPE_REQUIRED");
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });
  it("rejects root/additional/accessor selectors before OAuth or fetch",async()=>{
    const e=setup({executiveResource:historyResource}),signal=new AbortController().signal;
    const getter=vi.fn(()=>"WS:Original.Project");
    for(const selection of [{workRef:"WS:Original.Project",rootJobId:"JOB-1"},
      Object.defineProperty({},"workRef",{get:getter}),{workRef:"WS:Original.Project\n"}]){
      await expect(e.client.executiveSession!.historyContext!(selection as {workRef:string},signal)).rejects.toThrow("SESSION_HISTORY_SELECTION_INVALID");
    }
    expect(getter).not.toHaveBeenCalled();expect(e.fetcher).not.toHaveBeenCalled();
  });
  it("refuses the original READ reply after actual auth generation withdrawal",async()=>{
    const e=await readOnlyHistory(),held=deferred<Response>();e.fetcher.mockImplementation(()=>held.promise);
    const pending=e.client.executiveSession!.historyContext!({workRef:"WS:Original.Project"},new AbortController().signal);
    const refused=expect(pending).rejects.toThrow();await flush();
    await e.client.signOut();held.resolve(response({ok:true}));await refused;
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });
});

describe("fresh conversation fixed transport",()=>{
 const resource="https://mcp.mastermind-x.com/os/executive";
 const preview={work_ref:"WS:Original.Project",operation_key:"mmos-conversation-create-"+"a".repeat(40),message:"Original user message."};
 it("uses dual resource headers only on preview/create and exact original Executive recovery bodies",async()=>{
  const e=setup({executiveResource:resource});await e.login();e.fetcher.mockClear();
  e.fetcher.mockImplementation(async()=>response({ok:false,error:{code:"inert"}}));
  const signal=new AbortController().signal;
  for(const operation of ["preview","create","status","read"] as const){
   const request=operation==="preview"?preview:operation==="create"?{...preview,preview_digest:"b".repeat(64)}:
    {work_ref:preview.work_ref,operation_key:preview.operation_key};
   await e.client.executive!.freshConversation!.request(operation,request,signal);
   const [url,options]=e.fetcher.mock.calls.at(-1)!;
   expect(url).toBe(ORIGIN+"/os/executive/conversation/"+operation);
   expect(JSON.parse(options!.body as string)).toEqual({arguments:request});
   expect(new Headers(options!.headers).has("x-mastermind-workspace-authorization")).toBe(operation==="preview"||operation==="create");
  }
  expect(e.fetcher).toHaveBeenCalledTimes(4);
 });
 it("carries all six attended leaves on exact paths with source-owned dual-resource separation",async()=>{
  const e=setup({executiveResource:resource});await e.login();e.fetcher.mockClear();
  e.fetcher.mockImplementation(async()=>response({inertTransportResult:true}));
  const signal=new AbortController().signal,{preview_digest,...preflight}=freshRecoveryOwner.turn_request;
  const selected={work_ref:preflight.work_ref,reference:preflight.reference,turn_key:preflight.turn_key};
  for(const [operation,path,request,dual] of [
    ["consume","consume",freshRecoveryOwner.consume_request,true],
    ["consume_status","consume/status",freshRecoveryOwner.consume_request,false],
    ["turn_preview","turn/preview",preflight,true],
    ["turn","turn",freshRecoveryOwner.turn_request,true],
    ["turn_status","turn/status",selected,false],
    ["turn_read","turn/read",selected,false],
  ] as const){
   await e.client.executive!.freshConversation!.request(operation,request,signal);
   const [url,options]=e.fetcher.mock.calls.at(-1)!;
   expect(url).toBe(ORIGIN+"/os/executive/conversation/"+path);
   expect(JSON.parse(options!.body as string)).toEqual({arguments:request});
   expect(new Headers(options!.headers).has("x-mastermind-workspace-authorization")).toBe(dual);
  }
  expect(e.fetcher).toHaveBeenCalledTimes(6);
 });
 it("does not relabel a READ-only Executive token as original submit-policy recovery",async()=>{
  const e=setup({executiveResource:resource});
  e.fetcher.mockImplementation(async()=>response({token_type:"Bearer",access_token:"private-token",expires_in:3600,
   scope:new URL(e.popup.location).searchParams.get("audience")===resource?"mastermind.executive.read":new URL(e.popup.location).searchParams.get("scope")}));
  await e.login();e.fetcher.mockClear();
  await expect(e.client.executive!.freshConversation!.request("status",{work_ref:preview.work_ref,operation_key:preview.operation_key},new AbortController().signal)).rejects.toThrow("EXECUTIVE_SEND_SCOPE_REQUIRED");
  expect(e.fetcher).not.toHaveBeenCalled();
 });
 it("closes unknown/request fields before transport and withholds a late reply after actual sign-out",async()=>{
  const e=setup({executiveResource:resource}),signal=new AbortController().signal;
  expect(()=>e.client.executive!.freshConversation!.request("preview",{...preview,root_job_id:"JOB-foreign"},signal)).toThrow("FRESH_CONVERSATION_REQUEST_INVALID");
  expect(e.fetcher).not.toHaveBeenCalled();await e.login();e.fetcher.mockClear();
  const held=deferred<Response>();e.fetcher.mockImplementation(()=>held.promise);
  const pending=e.client.executive!.freshConversation!.request("preview",preview,signal),refused=expect(pending).rejects.toThrow();
  await flush();await e.client.signOut();held.resolve(response({ok:true}));await refused;
  expect(e.fetcher).toHaveBeenCalledTimes(1);
 });
});

describe("fixed project execution two-resource requests", () => {
  const resource = "https://fixture-resource.mastermind-x.com/executive";
  const statusArgs = {operation_key: "mmos-project-execute-" + "a".repeat(40), work_ref: "WS:EXAMPLE"};
  const context = {record_source: {repository: "mastermindx-market-intelligence/macro", commit: "b".repeat(40),
    path: "agentos/workstreams/WS-EXAMPLE.md", content_sha256: "c".repeat(64)}, adoption: null, adoption_decision_source: null};
  const requests = {
    preview: {...statusArgs, operation_key: "mmos-project-preview-" + "d".repeat(40), expected_context: context},
    submit: {...statusArgs, expected_context: context, context_sha256: "e".repeat(64),
      execution_binding_sha256: "f".repeat(64), execution_profile: "research_only",
      objective: "Finish the project", handoff_text: "Original private handoff", continuation_mode: "DURABLE"},
    status: statusArgs,
  };
  const envelope = (operation: string, code: string | null = null) => ({
    schema: "mastermind.project_execution_private_result.v1", operation, ok: code === null,
    data: code === null ? {state: "ACCEPTED", operation_key: statusArgs.operation_key} : null,
    error: code === null ? null : {code, message: "Fixed refusal"},
  });
  it.each(["preview", "submit", "status"] as const)("sends exact %s arguments with both private grants to the fixed route", async operation => {
    const e = setup({executiveResource: resource});
    e.fetcher.mockImplementation(async () => {
      const url = new URL(e.popup.location), audience = url.searchParams.get("audience");
      return response({token_type: "Bearer", access_token: audience === resource ? "private-executive" : "private-workspace",
        expires_in: 3600, scope: url.searchParams.get("scope")});
    });
    await e.login();
    e.fetcher.mockReset();
    e.fetcher.mockResolvedValue(response(envelope(operation)));
    await e.client.executive!.projectExecution!.request(operation, requests[operation], new AbortController().signal);
    expect(e.fetcher).toHaveBeenCalledTimes(1);
    const [url, options] = e.fetcher.mock.calls[0]!;
    expect(url).toBe(ORIGIN + "/os/executive/project-execution/" + operation);
    expect(options).toMatchObject({method: "POST", redirect: "error", credentials: "omit", cache: "no-store",
      headers: {Authorization: "Bearer private-executive", "X-Mastermind-Workspace-Authorization": "Bearer private-workspace"},
      body: JSON.stringify({arguments: requests[operation]})});
    expect(JSON.stringify(e.client)).not.toContain("private-executive");
  });
  it.each(["preview", "submit", "status"] as const)("requires submit authority for the original %s owner before fetch", async operation => {
    const e = setup({executiveResource: resource});
    e.fetcher.mockImplementation(async () => response({token_type: "Bearer", access_token: "private-token", expires_in: 3600,
      scope: new URL(e.popup.location).searchParams.get("audience") === resource
        ? "mastermind.executive.read" : new URL(e.popup.location).searchParams.get("scope")}));
    await e.login();
    e.fetcher.mockClear();
    await expect(e.client.executive!.projectExecution!.request(operation, requests[operation], new AbortController().signal))
      .rejects.toThrow("EXECUTIVE_SEND_SCOPE_REQUIRED");
    expect(e.fetcher).not.toHaveBeenCalled();
  });
  it("rejects unknown route and extra authority fields before fetch", async () => {
    const e = setup({executiveResource: resource});
    await e.login(); e.fetcher.mockClear();
    expect(() => e.client.executive!.projectExecution!.request("../submit" as never, statusArgs, new AbortController().signal))
      .toThrow("PROJECT_EXECUTION_INPUT_INVALID");
    expect(() => e.client.executive!.projectExecution!.request("status", {...statusArgs, principal_scope: "f".repeat(64)}, new AbortController().signal))
      .toThrow("PROJECT_EXECUTION_INPUT_INVALID");
    expect(e.fetcher).not.toHaveBeenCalled();
  });
  it.each([["invalid_request", 400], ["context_changed", 403], ["operation_conflict", 409], ["source_unavailable", 503], ["effect_unknown", 202]] as const)
    ("preserves typed %s without retrying or replacing the original request", async (code, httpStatus) => {
      const e = setup({executiveResource: resource});
      await e.login(); e.fetcher.mockReset();
      const body = envelope("submit", code);
      e.fetcher.mockResolvedValue(new Response(JSON.stringify(body), {status: httpStatus, headers: {"content-type": "application/json"}}));
      await expect(e.client.executive!.projectExecution!.request("submit", requests.submit, new AbortController().signal)).resolves.toEqual(body);
      expect(e.fetcher).toHaveBeenCalledTimes(1);
    });
  it("rejects mismatched error envelopes without exposing a private response", async () => {
    const e = setup({executiveResource: resource});
    await e.login(); e.fetcher.mockReset();
    e.fetcher.mockResolvedValue(new Response(JSON.stringify(envelope("status", "refused")), {status: 403, headers: {"content-type": "application/json"}}));
    await expect(e.client.executive!.projectExecution!.request("submit", requests.submit, new AbortController().signal))
      .rejects.toThrow("PROJECT_EXECUTION_RESPONSE_INVALID");
    expect(e.fetcher).toHaveBeenCalledTimes(1);
  });
  it("drops a delayed execution response on sign-out and does not resubmit after sign-in", async () => {
    const e = setup({executiveResource: resource});
    await e.login(); e.fetcher.mockReset();
    const held = deferred<Response>();
    e.fetcher.mockReturnValue(held.promise);
    const request = e.client.executive!.projectExecution!.request("submit", requests.submit, new AbortController().signal);
    const rejected = expect(request).rejects.toThrow("EXECUTIVE_REQUEST_CANCELLED");
    await e.client.signOut();
    held.resolve(response(envelope("submit")));
    await rejected;
    expect(e.fetcher).toHaveBeenCalledTimes(1);
    e.fetcher.mockImplementation(async () => response({token_type: "Bearer", access_token: "replacement-private",
      expires_in: 3600, scope: new URL(e.popup.location).searchParams.get("scope")}));
    await e.login();
    expect(e.fetcher.mock.calls.filter(([url]) => String(url).includes("/project-execution/"))).toHaveLength(1);
  });
  it("settles on the shorter Workspace expiry even while Executive remains authorized", async () => {
    const e = setup({executiveResource: resource});
    e.fetcher.mockImplementation(async () => response({token_type: "Bearer", access_token: "private-token",
      expires_in: new URL(e.popup.location).searchParams.get("audience") === ACQUISITION_AUDIENCE ? 120 : 3600,
      scope: new URL(e.popup.location).searchParams.get("scope")}));
    await e.login(); e.fetcher.mockReset();
    e.fetcher.mockReturnValue(new Promise(() => {}));
    const request = e.client.executive!.projectExecution!.request("submit", requests.submit, new AbortController().signal);
    const rejected = expect(request).rejects.toThrow("EXECUTIVE_REQUEST_CANCELLED");
    await vi.advanceTimersByTimeAsync(120_000);
    await rejected;
    expect(e.fetcher).toHaveBeenCalledTimes(1);
    expect(e.fetcher.mock.calls[0]![1]!.signal!.aborted).toBe(true);
  });
});

// New read reuses the independent Executive READ owner, never Workspace/SEND.
describe("authored company priorities fixed read",()=>{
 it("uses the fixed empty JSON route with READ-only Executive scope",async()=>{
  const resource="https://executive.example.invalid/mcp",e=setup({executiveResource:resource});
  e.fetcher.mockImplementation(async()=>response({token_type:"Bearer",access_token:"private-token",expires_in:3600,scope:new URL(e.popup.location).searchParams.get("audience")===resource?"mastermind.executive.read":new URL(e.popup.location).searchParams.get("scope")}));
  await e.login();e.fetcher.mockReset();e.fetcher.mockResolvedValueOnce(response({schema:"inert-wire-only"}));
  await e.client.executive!.companyPriorities!(new AbortController().signal);
  expect(e.fetcher).toHaveBeenCalledExactlyOnceWith(ORIGIN+"/os/executive/company-priorities",expect.objectContaining({method:"POST",body:"{}",credentials:"omit",redirect:"error",cache:"no-store",headers:{Accept:"application/json","Content-Type":"application/json",Authorization:"Bearer private-token"}}));
 });
 it("discards the delayed READ after the current Executive grant ends",async()=>{
  const e=setup({executiveResource:"https://executive.example.invalid/mcp"});await e.login();e.fetcher.mockReset();const held=deferred<Response>();e.fetcher.mockReturnValueOnce(held.promise);const read=e.client.executive!.companyPriorities!(new AbortController().signal);const refused=expect(read).rejects.toThrow();await e.client.signOut();held.resolve(response({must_not_escape:true}));await refused;
 });
});
