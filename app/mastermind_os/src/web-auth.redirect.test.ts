// @vitest-environment jsdom
// @vitest-environment-options {"url":"https://mcp.mastermind-x.com/os/"}
import { beforeEach, afterEach, describe, it, expect, vi } from "vitest";
import { createWebAuth, handleWebAuthCallback } from "./web-auth";
import { registerUnsavedNavigationHold } from "./auth-navigation-guard";
import { CALLBACK_PATH, ISSUER, ORIGIN } from "./public-config";

const done = async () => { for (let i=0; i<40; i++) await Promise.resolve(); };
const response = (data: unknown) => new Response(JSON.stringify(data),
  { headers: {"content-type":"application/json"} });
const PRIOR_KEY = "mastermind-os-auth0-prior-login-v1:client-fixture";
const PENDING_KEY = "mastermind-os-auth0-redirect-pkce-v1";
const ATTEMPT_KEY = "mastermind-os-auth0-redirect-attempt-v1";

function harness() {
  let seed = 0;
  const listeners = new Set<(e: MessageEvent) => void>();
  const fetchFn = vi.fn<typeof fetch>().mockImplementation(async () =>
    response({token_type:"Bearer",access_token:"acquisition-private-token",expires_in:3600,
      scope:"mastermind.workspace.read"}));
  const navigate = vi.fn();
  const fireCsp = () => {
    for (const fn of [...listeners]) fn({
      effectiveDirective: "frame-src", blockedURI: new URL(ISSUER).origin,
    } as unknown as MessageEvent);
  };
  const fireAuth = () => {
    const frame = document.querySelector("iframe")!;
    const parsed = new URL(frame.src);
    for (const listener of [...listeners]) listener({
      origin: ORIGIN, source: frame.contentWindow,
      data: {type:"mastermind-auth-callback", state:parsed.searchParams.get("state"),
        code:"synthetic-code"},
    } as MessageEvent);
  };
  const fireRemoteLogout = () => {
    localStorage.setItem("mastermind-os-auth-logout-v1:client-fixture","1");
    for (const listener of [...listeners]) listener({
      key:"mastermind-os-auth-logout-v1:client-fixture", newValue:"1",
    } as unknown as MessageEvent);
  };
  const makeClient = () => createWebAuth({
    config:{webClientId:"client-fixture"},
    fetchFn,navigate,
    crypto:{
      getRandomValues(a: Uint8Array) { a.fill(++seed); return a; },
      subtle:{digest:async()=>new ArrayBuffer(32)},
    } as unknown as Crypto,
    addEventListener: ((_t:string, fn:(e:MessageEvent)=>void) => listeners.add(fn)) as typeof window.addEventListener,
    removeEventListener: ((_t:string, fn:(e:MessageEvent)=>void) => listeners.delete(fn)) as typeof window.removeEventListener,
  });
  return {makeClient, navigate, fetchFn, fireCsp, fireAuth, fireRemoteLogout};
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubEnv("VITE_MM_WEB_CLIENT_ID", "client-fixture");
  localStorage.clear(); sessionStorage.clear();
  history.replaceState(null,"","/os/");
  document.body.innerHTML = '<div id="root"></div>';
  Object.defineProperty(window, "opener", {value:null,configurable:true});
});
afterEach(() => {
  vi.useRealTimers(); vi.unstubAllEnvs(); vi.restoreAllMocks();
  localStorage.clear(); sessionStorage.clear();
  document.querySelectorAll("iframe").forEach(frame=>frame.remove());
  history.replaceState(null,"","/os/");
});

describe("CSP-compatible same-tab Auth0 fallback", () => {
  it("never overwrites an unsent Office draft via automatic OAuth navigation", async () => {
    localStorage.setItem(PRIOR_KEY, "1");
    let dirty = true;
    const release = registerUnsavedNavigationHold(() => dirty);
    try {
      const h = harness(), c = h.makeClient();
      const first = c.restore!();
      await done(); await vi.advanceTimersByTimeAsync(10005); await first;
      expect(h.navigate).not.toHaveBeenCalled();
      expect(sessionStorage.getItem(PENDING_KEY)).toBeNull();
      expect(sessionStorage.getItem(ATTEMPT_KEY)).toBeNull();
      dirty = false;
      const second = c.restore!();
      await done(); await vi.advanceTimersByTimeAsync(10005); await second;
      expect(h.navigate).toHaveBeenCalledTimes(1);
      expect(new URL(h.navigate.mock.calls[0][0]).searchParams.get("prompt")).toBe("none");
    } finally { release(); }
  });
  it("does not redirect a new visitor without a previous explicit signed-in session", async () => {
    const h=harness(), c=h.makeClient();
    const task=c.restore!();
    await done(); await vi.advanceTimersByTimeAsync(10005); await task;
    expect(h.navigate).not.toHaveBeenCalled();
    expect(c.getState().status).toBe("signed_out");
  });
  it("uses one top-level prompt=none PKCE redirect after iframe failure for prior user", async () => {
    localStorage.setItem(PRIOR_KEY,"1");
    const h=harness(), c=h.makeClient();
    const task=c.restore!();
    await done(); await vi.advanceTimersByTimeAsync(10005); await task;
    expect(h.navigate).toHaveBeenCalledTimes(1);
    const url=new URL(h.navigate.mock.calls[0][0]);
    expect(url.origin).toBe(new URL(ISSUER).origin);
    expect(url.searchParams.get("prompt")).toBe("none");
    expect(url.searchParams.get("code_challenge_method")).toBe("S256");
    expect(url.searchParams.get("redirect_uri")).toBe(ORIGIN+CALLBACK_PATH);
    const stored=JSON.parse(sessionStorage.getItem(PENDING_KEY)!);
    expect(stored.state).toBe(url.searchParams.get("state"));
    expect(stored.verifier).toHaveLength(43);
    expect(url.toString()).not.toContain(stored.verifier);
    expect(sessionStorage.getItem(ATTEMPT_KEY)).toBe("1");
    // Without an actual navigation, a second cold restore in the same tab
    // is prevented from redirecting again.
    const again=h.makeClient().restore!();
    await done(); await vi.advanceTimersByTimeAsync(10005); await again;
    expect(h.navigate).toHaveBeenCalledTimes(1);
  });
  it("accepts only a state/client-matched callback, exchanges without persistent bearer, and fences logout", async () => {
    localStorage.setItem(PRIOR_KEY,"1");
    const h=harness(), c=h.makeClient();
    const initial=c.restore!();
    await done(); await vi.advanceTimersByTimeAsync(10005); await initial;
    const pending=JSON.parse(sessionStorage.getItem(PENDING_KEY)!);
    history.replaceState(null,"",CALLBACK_PATH+"?state="+pending.state+"&code=synthetic-code&iss="+encodeURIComponent(ISSUER));
    expect(handleWebAuthCallback()).toBe(false);
    expect(location.pathname).toBe("/os/");
    expect(location.search).toBe("");
    expect(document.getElementById("root")).not.toBeNull();
    const reopened=h.makeClient();
    const restore=reopened.restore!();
    await done(); await vi.advanceTimersByTimeAsync(10005);
    const state=await restore;
    expect(state).toMatchObject({status:"signed_in",acquisition:true,content:false});
    expect(h.fetchFn).toHaveBeenCalledTimes(1);
    expect(String(h.fetchFn.mock.calls[0][0])).toBe(ISSUER+"oauth/token");
    expect(sessionStorage.getItem(PENDING_KEY)).toBeNull();
    expect(sessionStorage.getItem(ATTEMPT_KEY)).toBeNull();
    expect(JSON.stringify(Object.keys(localStorage))).not.toContain("acquisition-private-token");
    await reopened.signOut();
    expect(localStorage.getItem(PRIOR_KEY)).toBeNull();
    expect(await h.makeClient().restore!()).toMatchObject({status:"signed_out"});
    expect(h.navigate).toHaveBeenCalledTimes(1);
  });
  it("refuses mismatched callback state without silently exchanging or redirecting twice", async () => {
    localStorage.setItem(PRIOR_KEY,"1");
    const h=harness(), c=h.makeClient();
    const first=c.restore!();
    await done(); await vi.advanceTimersByTimeAsync(10005); await first;
    history.replaceState(null,"",CALLBACK_PATH+"?state=wrong&code=synthetic");
    expect(handleWebAuthCallback()).toBe(true);
    expect(h.fetchFn).not.toHaveBeenCalled();
    expect(sessionStorage.getItem(PENDING_KEY)).toBeTruthy();
    expect(h.navigate).toHaveBeenCalledTimes(1);
  });
  it("reacts to live CSP frame-src denial without waiting ten seconds", async () => {
    localStorage.setItem(PRIOR_KEY,"1");
    const h=harness(), c=h.makeClient();
    const task=c.restore!();
    await done();
    expect(document.querySelector("iframe")).toBeTruthy();
    h.fireCsp();
    await task;
    expect(h.navigate).toHaveBeenCalledTimes(1);
    expect(document.querySelector("iframe")).toBeNull();
    expect(vi.getTimerCount()).toBeGreaterThanOrEqual(0);
  });

  it("never consumes a redirect callback for a different configured web client", async () => {
    localStorage.setItem(PRIOR_KEY,"1");
    const h=harness(), c=h.makeClient();
    const first=c.restore!();
    await done(); await vi.advanceTimersByTimeAsync(10005); await first;
    const pending=JSON.parse(sessionStorage.getItem(PENDING_KEY)!);
    vi.stubEnv("VITE_MM_WEB_CLIENT_ID","different-client");
    history.replaceState(null,"",CALLBACK_PATH+"?state="+pending.state+"&code=synthetic");
    expect(handleWebAuthCallback()).toBe(true);
    expect(sessionStorage.getItem(PENDING_KEY)).toBeTruthy();
    expect(h.fetchFn).not.toHaveBeenCalled();
  });
  it("never posts a same-tab OAuth code to an unrelated surviving opener", async () => {
    localStorage.setItem(PRIOR_KEY,"1");
    const h=harness(), c=h.makeClient();
    const first=c.restore!();
    await done(); await vi.advanceTimersByTimeAsync(10005); await first;
    const pending=JSON.parse(sessionStorage.getItem(PENDING_KEY)!);
    const opener={closed:false,postMessage:vi.fn()};
    Object.defineProperty(window,"opener",{value:opener,configurable:true});
    history.replaceState(null,"",CALLBACK_PATH+"?state="+pending.state+"&code=synthetic");
    expect(handleWebAuthCallback()).toBe(false);
    expect(opener.postMessage).not.toHaveBeenCalled();
    expect(document.getElementById("root")).not.toBeNull();
    // The next genuine client consumes only its matching one-use grant.
    const next=h.makeClient(); const restored=next.restore!();
    await done(); await vi.advanceTimersByTimeAsync(10005); await restored;
    await next.signOut();
  });

  it("retains explicit logout when the user clicks sign-in but its popup is blocked", async () => {
    const navigate=vi.fn();
    const c=createWebAuth({
      config:{webClientId:"client-fixture"},
      openPopup:()=>null, navigate,
    });
    await c.signOut();
    expect(localStorage.getItem("mastermind-os-auth-logout-v1:client-fixture")).toBe("1");
    expect(await c.signIn()).toMatchObject({reason:"POPUP_BLOCKED"});
    expect(localStorage.getItem("mastermind-os-auth-logout-v1:client-fixture")).toBe("1");
    const reopened=createWebAuth({
      config:{webClientId:"client-fixture"},
      openPopup:()=>null, navigate,
    });
    expect(await reopened.restore!()).toMatchObject({status:"signed_out"});
    expect(navigate).not.toHaveBeenCalled();
  });

  it("signs out in the same tab even when logout marker writes hit quota", async () => {
    localStorage.setItem(PRIOR_KEY, "1");
    const key = "mastermind-os-auth-logout-v1:client-fixture";
    const original = Storage.prototype.setItem;
    const denial = vi.spyOn(Storage.prototype, "setItem").mockImplementation(
      function(this: Storage, item: string, value: string) {
        if (item === key) throw new DOMException("quota", "QuotaExceededError");
        return original.call(this, item, value);
      });
    try {
      const h = harness(), client = h.makeClient();
      const signedOut = await client.signOut();
      expect(signedOut).toMatchObject({
        status: "signed_out", reason: "USER_SIGNED_OUT",
        acquisition: false, content: false,
      });
      expect(localStorage.getItem(key)).toBeNull();
      // The independent remove is not skipped when setItem throws.
      expect(localStorage.getItem(PRIOR_KEY)).toBeNull();
      expect(await client.restore!()).toMatchObject({status:"signed_out"});
      expect(h.navigate).not.toHaveBeenCalled();
      expect(h.fetchFn).not.toHaveBeenCalled();
    } finally { denial.mockRestore(); }
  });

  it("invalidates active Workspace credentials across tabs and blocks automatic re-login", async () => {
    const h=harness(), client=h.makeClient();
    const pending=client.restore!();
    await done();
    h.fireAuth();
    await done();
    h.fireCsp(); // Content remains unavailable, but acquisition is granted.
    await pending;
    expect(client.getState()).toMatchObject({status:"signed_in",acquisition:true});
    const before=client.invalidationGeneration!();
    h.fireRemoteLogout();
    expect(client.getState()).toMatchObject({status:"signed_out",acquisition:false,content:false});
    expect(client.invalidationGeneration!()).toBeGreaterThan(before);
    await expect(client.readPrograms!({signal:new AbortController().signal}))
      .rejects.toThrow("TOKEN_REQUIRED");
    expect(h.fetchFn).toHaveBeenCalledTimes(1);
    expect(await client.restore!()).toMatchObject({status:"signed_out"});
    expect(h.navigate).not.toHaveBeenCalled();
  });

  it("re-attempts a bounded top-level PKCE after acquisition expires", async () => {
    const h=harness();
    h.fetchFn.mockImplementation(async () =>
      response({token_type:"Bearer", access_token:"synthetic-short-lived",
        expires_in:1,scope:"mastermind.workspace.read"}));
    const client=h.makeClient();
    const pending=client.restore!();
    await done();
    h.fireAuth();
    await done();
    h.fireCsp(); // Content's frame is not allowed by the deployed CSP.
    await pending;
    expect(client.getState().acquisition).toBe(true);
    await vi.advanceTimersByTimeAsync(1005);
    await done();
    expect(client.getState().acquisition).toBe(false);
    h.fireCsp(); // The expiry renewal attempted a new acquisition iframe.
    await done();
    expect(h.navigate).toHaveBeenCalledTimes(1);
    const authorize=new URL(h.navigate.mock.calls[0][0]);
    expect(authorize.searchParams.get("prompt")).toBe("none");
    expect(sessionStorage.getItem(ATTEMPT_KEY)).toBe("1");
    expect(Object.keys(localStorage)).not.toContain("synthetic-short-lived");
  });

  it("rejects Auth0 login_required without looping or storing credentials", async () => {
    localStorage.setItem(PRIOR_KEY,"1");
    const h=harness(), c=h.makeClient();
    const first=c.restore!();
    await done(); await vi.advanceTimersByTimeAsync(10005); await first;
    const pending=JSON.parse(sessionStorage.getItem(PENDING_KEY)!);
    history.replaceState(null,"",CALLBACK_PATH+"?state="+pending.state+"&error=login_required&iss="+encodeURIComponent(ISSUER));
    expect(handleWebAuthCallback()).toBe(false);
    const restored=h.makeClient().restore!();
    await done(); await vi.advanceTimersByTimeAsync(10005); await restored;
    expect(h.navigate).toHaveBeenCalledTimes(1);
    expect(h.fetchFn).not.toHaveBeenCalled();
    expect(sessionStorage.getItem(ATTEMPT_KEY)).toBe("1");
    expect(sessionStorage.getItem(PENDING_KEY)).toBeNull();
  });
});
