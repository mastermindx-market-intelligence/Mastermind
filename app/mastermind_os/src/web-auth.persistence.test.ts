// @vitest-environment jsdom
// @vitest-environment-options {"url":"https://mcp.mastermind-x.com/os/"}
import { describe, expect, it, vi, afterEach } from "vitest";
import { createWebAuth } from "./web-auth";
import { ORIGIN, ISSUER } from "./public-config";

const response = (data: unknown) => new Response(JSON.stringify(data),
  { headers: { "content-type": "application/json" } });
const flush = async () => { for (let i = 0; i < 30; i++) await Promise.resolve(); };
afterEach(() => {
  vi.useRealTimers();
  document.querySelectorAll("iframe").forEach(e => e.remove());
  localStorage.clear(); sessionStorage.clear();
});
describe("silent Auth0 PKCE restoration", () => {
  function make() {
    vi.useFakeTimers();
    let i = 0;
    const messages = new Set<(event: MessageEvent) => void>();
    const fetchFn = vi.fn<typeof fetch>().mockImplementation(async () =>
      response({ token_type: "Bearer", access_token: "private-silent-token",
        expires_in: 3600, scope: "mastermind.workspace.read" }));
    const client = createWebAuth({
      config: { webClientId: "client-fixture" },
      fetchFn, crypto: {
        getRandomValues(a: Uint8Array) { a.fill(++i); return a; },
        subtle: { digest: async () => new ArrayBuffer(32) },
      } as unknown as Crypto,
      addEventListener: ((_t: string, f: (event: MessageEvent) => void) => { messages.add(f); }) as typeof window.addEventListener,
      removeEventListener: ((_t: string, f: (event: MessageEvent) => void) => { messages.delete(f); }) as typeof window.removeEventListener,
    });
    const callback = (extra: Record<string, unknown> = {}, correct = true) => {
      const frame = document.querySelector("iframe")!;
      const url = new URL(frame.src);
      for (const listener of messages) {
        listener({ source: correct ? frame.contentWindow : window, origin: ORIGIN,
          data: { type: "mastermind-auth-callback",
            state: url.searchParams.get("state"), code: "test-code", ...extra } } as MessageEvent);
      }
    };
    return { client, fetchFn, callback };
  }
  it("restores two separate audiences without popup or token storage", async () => {
    const {client, fetchFn, callback} = make();
    const promise = client.restore!();
    await flush();
    let frame = document.querySelector("iframe")!;
    expect(new URL(frame.src).origin).toBe(new URL(ISSUER).origin);
    expect(new URL(frame.src).searchParams.get("prompt")).toBe("none");
    callback();
    await flush();
    frame = document.querySelector("iframe")!;
    expect(new URL(frame.src).searchParams.get("audience")).toContain("/window/current");
    fetchFn.mockImplementation(async () => response({
      token_type: "Bearer", access_token: "content-token", expires_in: 3600,
      scope: "mastermind.workspace.content.read" }));
    callback();
    expect(await promise).toMatchObject({ status: "signed_in", acquisition: true, content: true });
    expect(fetchFn).toHaveBeenCalledTimes(2);
    expect(document.querySelector("iframe")).toBeNull();
    expect(localStorage.getItem("mastermind-os-auth0-prior-login-v1:client-fixture")).toBe("1");
    expect(JSON.stringify(Object.keys(localStorage))).not.toContain("private-silent-token");
  });
  it("rejects forged frame sources without a token exchange", async () => {
    const {client, fetchFn, callback} = make();
    const pending = client.restore!();
    await flush();
    callback({}, false);
    await flush();
    expect(fetchFn).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(10001);
    expect(await pending).toMatchObject({status:"signed_out"});
  });
  it("keeps a late silent exchange from restoring a signed-out session", async () => {
    const {client, fetchFn, callback} = make();
    let release!: (value: Response) => void;
    fetchFn.mockImplementation(() => new Promise(resolve => { release = resolve; }));
    const pending = client.restore!();
    await flush();
    callback();
    await flush();
    await client.signOut();
    release(response({token_type:"Bearer",access_token:"late",expires_in:3600,scope:"mastermind.workspace.read"}));
    await pending;
    expect(client.getState().status).toBe("signed_out");
  });
});
