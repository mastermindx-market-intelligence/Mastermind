// @vitest-environment jsdom
// @vitest-environment-options {"url":"https://mcp.mastermind-x.com/os/research/evidence/rvitem.v1.aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
import { afterEach, describe, expect, it, vi } from "vitest";
import { createWebAuth } from "./web-auth";
import { CALLBACK_URL, ORIGIN, RESEARCH_SCOPE, TRANSACTION_TTL_MS } from "./public-config";
import { evidenceUrl } from "./research/evidence-contract";
const id = `rvitem.v1.${"a".repeat(64)}`;
const audience = `${ORIGIN}/research/read`; // synthetic protocol input, not provider registration
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const flush = async () => { for (let i = 0; i < 30; i++) await Promise.resolve(); };
function setup(resource: string | null = audience, overrides: { scope?: string; expires?: number } = {}) {
  vi.useFakeTimers();
  const popup = { location: "", closed: false, close: vi.fn() };
  const listeners = new Set<(event: MessageEvent) => void>();
  const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => response({ token_type: "Bearer", access_token: "private-research-bearer", expires_in: overrides.expires ?? 3600, scope: overrides.scope ?? RESEARCH_SCOPE }));
  const open = vi.fn(() => popup);
  const client = createWebAuth({ config: { webClientId: "synthetic-existing-browser-client", researchResource: resource },
    openPopup: open, fetchFn: fetcher,
    crypto: { getRandomValues(value: Uint8Array) { value.fill(4); return value; }, subtle: { digest: () => Promise.resolve(new ArrayBuffer(32)) } } as unknown as Crypto,
    addEventListener: ((_type: string, fn: (event: MessageEvent) => void) => listeners.add(fn)) as unknown as typeof window.addEventListener,
    removeEventListener: ((_type: string, fn: (event: MessageEvent) => void) => listeners.delete(fn)) as unknown as typeof window.removeEventListener,
  });
  const callback = (origin = ORIGIN) => {
    for (const fn of [...listeners]) fn({ source: popup, origin, data: { type: "mastermind-auth-callback", state: new URL(popup.location).searchParams.get("state"), code: "synthetic-code" } } as unknown as MessageEvent);
  };
  const login = async () => { const pending = client.research!.signIn(); await flush(); callback(); await flush(); await pending; };
  return { client, fetcher, open, popup, callback, login };
}
afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); });
describe("existing private PKCE owner Research resource", () => {
  it("leaves unset Research inert with zero network and popup calls", async () => {
    const f = setup(null);
    await expect(f.client.research!.signIn()).rejects.toThrow("RESEARCH_UNAVAILABLE");
    await expect(f.client.research!.readEvidenceItem(id, new AbortController().signal)).rejects.toThrow("RESEARCH_UNAVAILABLE");
    expect(f.open).not.toHaveBeenCalled(); expect(f.fetcher).not.toHaveBeenCalled();
  });
  it("requests only the dedicated Research scope and preserves callback and origin", async () => {
    const f = setup(); await f.login();
    const url = new URL(f.popup.location);
    expect(url.searchParams.get("audience")).toBe(audience);
    expect(url.searchParams.get("scope")).toBe(RESEARCH_SCOPE);
    expect(url.searchParams.get("redirect_uri")).toBe(CALLBACK_URL);
    expect(f.fetcher).toHaveBeenCalledTimes(1);
    expect(f.client.getState().acquisition).toBe(false); expect(f.client.getState().content).toBe(false);
    expect(JSON.stringify(f.client.getState())).not.toContain("private-research-bearer");
  });
  it("requires an exact granted Research scope", async () => {
    const f = setup(audience, { scope: "mastermind.executive.read" });
    await expect(f.login()).rejects.toThrow("TOKEN_INVALID"); expect(f.client.research!.available()).toBe(false);
  });
  it("does not accept a callback from a different origin", async () => {
    const f = setup(); const pending = f.client.research!.signIn();
    const failure = expect(pending).rejects.toThrow("TRANSACTION_EXPIRED");
    await flush(); f.callback("https://www.mastermind-x.com"); await flush();
    expect(f.fetcher).not.toHaveBeenCalled(); await vi.advanceTimersByTimeAsync(TRANSACTION_TTL_MS); await failure;
  });
  it("validates item ID before sending a fixed private bearer read", async () => {
    const f = setup(); await f.login();
    expect(() => f.client.research!.readEvidenceItem(`${id}?token=x`, new AbortController().signal)).toThrow("EVIDENCE_ITEM_INVALID");
    expect(f.fetcher).toHaveBeenCalledTimes(1);
    f.fetcher.mockResolvedValueOnce(response({ fixture: "conditional-not-live" }));
    await f.client.research!.readEvidenceItem(id, new AbortController().signal);
    const [url, init] = f.fetcher.mock.calls.at(-1)!;
    expect(url).toBe(evidenceUrl(id)); expect(url).not.toContain("private-research-bearer");
    expect(init).toMatchObject({ method: "GET", credentials: "omit", redirect: "error", cache: "no-store", headers: { Accept: "application/json", Authorization: "Bearer private-research-bearer" } });
  });
  it("never reflects nonOK source response body", async () => {
    const f = setup(); await f.login(); f.fetcher.mockResolvedValueOnce(response({ private_title: "forbidden" }, 403));
    await expect(f.client.research!.readEvidenceItem(id, new AbortController().signal)).rejects.toThrow("READ_FAILED");
  });
  it.each(["signout", "expiry"])("aborts and refuses in-flight item on %s", async change => {
    const f = setup(audience, { expires: 2 }); await f.login();
    let resolve!: (response: Response) => void;
    f.fetcher.mockImplementationOnce(() => new Promise<Response>(yes => { resolve = yes; }));
    const pending = f.client.research!.readEvidenceItem(id, new AbortController().signal);
    const failure = expect(pending).rejects.toThrow("READ_CANCELLED");
    const signal = f.fetcher.mock.calls.at(-1)![1]!.signal!;
    if (change === "signout") await f.client.signOut(); else await vi.advanceTimersByTimeAsync(2000);
    expect(signal.aborted).toBe(true); expect(f.client.research!.available()).toBe(false);
    resolve(response({ private_text: "must not project" })); await failure;
  });
  it("bounds successful JSON before it can reach the component", async () => {
    const f = setup(); await f.login(); f.fetcher.mockResolvedValueOnce(response({ text: "x".repeat(17000) }));
    await expect(f.client.research!.readEvidenceItem(id, new AbortController().signal)).rejects.toThrow();
  });
});
