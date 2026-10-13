// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ResearchEvidenceEntry } from "./ResearchEvidenceEntry";
import { createWebAuth, type WebAuthDeps, type WebPopup } from "../web-auth";
import { ORIGIN, RESEARCH_SCOPE } from "../public-config";
import { evidenceUrl, type ResearchEvidenceTransport } from "./evidence-contract";

const id = `rvitem.v1.${"a".repeat(64)}`;
const payload = { id, title: "Exact evidence", text: "Literal source 尾🙂", url: evidenceUrl(id),
  metadata: { coverage: "COMPLETE_BOUNDED_ITEM" } };
const clients: ReturnType<typeof createWebAuth>[] = [];
const response = (value: unknown) => new Response(JSON.stringify(value), { headers: { "content-type": "application/json" } });
const flush = async () => { for (let i = 0; i < 30; i++) await Promise.resolve(); };
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(yes => { resolve = yes; });
  return { promise, resolve };
}
function fixture(options: { firstDigest?: Promise<ArrayBuffer>; evidenceResponse?: Promise<Response> } = {}) {
  vi.useFakeTimers();
  const popups: (WebPopup & { location: string; closed: boolean })[] = [];
  const messages = new Set<(event: MessageEvent) => void>();
  let random = 0, digests = 0;
  const fetcher = vi.fn<typeof fetch>().mockImplementation(async (url) =>
    String(url).endsWith("/oauth/token")
      ? response({ token_type: "Bearer", access_token: "fixture-research-token", expires_in: 3600, scope: RESEARCH_SCOPE })
      : options.evidenceResponse ?? response(payload));
  const client = createWebAuth({
    config: { webClientId: "fixture-public-client", researchResource: "https://fixture.invalid/research" },
    crypto: { getRandomValues(array: Uint8Array) { array.fill(++random); return array; },
      subtle: { digest: () => ++digests === 1 && options.firstDigest ? options.firstDigest : Promise.resolve(new ArrayBuffer(32)) },
    } as unknown as Crypto,
    fetchFn: fetcher,
    openPopup: () => { const popup = { location: "", closed: false, close() { this.closed = true; } }; popups.push(popup); return popup; },
    addEventListener: ((_type: string, listener: (event: MessageEvent) => void) => { messages.add(listener); }) as unknown as WebAuthDeps["addEventListener"],
    removeEventListener: ((_type: string, listener: (event: MessageEvent) => void) => { messages.delete(listener); }) as unknown as WebAuthDeps["removeEventListener"],
  });
  clients.push(client);
  const callback = (failure?: string) => {
    const popup = popups[popups.length - 1];
    const state = new URL(popup.location).searchParams.get("state");
    for (const listener of [...messages]) listener({ source: popup, origin: ORIGIN,
      data: { type: "mastermind-auth-callback", state, ...(failure ? { failure } : { code: "fixture-one-time-code" }) },
    } as unknown as MessageEvent);
  };
  return { client, popups, fetcher, callback };
}
function view(f: ReturnType<typeof fixture>) {
  return <ResearchEvidenceEntry itemId={id} transport={f.client.research} signOut={f.client.signOut} />;
}
const signIn = () => screen.getByRole<HTMLButtonElement>("button", { name: "Sign in to Research" });
const status = () => screen.getByRole("status").textContent;
async function start() { await act(async () => { fireEvent.click(signIn()); await flush(); }); }
async function authorize(f: ReturnType<typeof fixture>) { await act(async () => { f.callback(); await flush(); }); }

afterEach(async () => {
  cleanup();
  for (const client of clients.splice(0)) await client.signOut();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("Research evidence sign-in presentation over the actual private auth owner", () => {
  it("keeps one pending popup through generation notifications and repeated button activation", async () => {
    const f = fixture(); render(view(f));
    await act(async () => { fireEvent.click(signIn()); fireEvent.click(signIn()); await flush(); });
    expect(status()).toBe("Loading authorized evidence…");
    expect(signIn().disabled).toBe(true);
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Sign out" }).disabled).toBe(false);
    await act(async () => { fireEvent.click(signIn()); await flush(); });
    expect(f.popups).toHaveLength(1);
    expect(f.popups[0].closed).toBe(false);
    expect(f.fetcher).not.toHaveBeenCalled();
  });

  it("keeps explicit sign-out after the canceled pending sign-in rejects", async () => {
    const f = fixture(); render(view(f)); await start();
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Sign out" })); await flush(); });
    expect(status()).toBe("Sign in to read this evidence item.");
    expect(signIn().disabled).toBe(false);
    expect(f.popups[0].closed).toBe(true);
    expect(document.querySelector("pre")).toBeNull();
    expect(f.client.research!.available()).toBe(false);
    expect(f.fetcher).not.toHaveBeenCalled();
    await start();
    expect(f.popups).toHaveLength(2);
    expect(status()).toBe("Loading authorized evidence…");
  });

  it("reports a genuine current sign-in failure and permits explicit retry to the exact item", async () => {
    const f = fixture(); render(view(f)); await start();
    await act(async () => { f.callback("AUTHORIZATION_DENIED"); await flush(); });
    expect(status()).toBe("This evidence item is unavailable.");
    expect(signIn().disabled).toBe(false);
    expect(f.fetcher).not.toHaveBeenCalled();
    await start(); await authorize(f);
    expect(status()).toBe("This citation contains one complete item from the source.");
    expect(document.querySelector("pre")?.textContent).toBe(payload.text);
    expect(f.fetcher.mock.calls.map(call => String(call[0]))).toEqual([
      "https://dev-eo0jf8us5mup7wd5.us.auth0.com/oauth/token", evidenceUrl(id),
    ]);
  });

  it("ignores an old sign-in rejection after sign-out and a successful newer sign-in", async () => {
    const digest = deferred<ArrayBuffer>(), f = fixture({ firstDigest: digest.promise });
    render(view(f)); await start();
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Sign out" })); await flush(); });
    await start(); await authorize(f);
    expect(document.querySelector("pre")?.textContent).toBe(payload.text);
    await act(async () => { digest.resolve(new ArrayBuffer(32)); await flush(); });
    expect(status()).toBe("This citation contains one complete item from the source.");
    expect(document.querySelector("pre")?.textContent).toBe(payload.text);
    expect(f.fetcher).toHaveBeenCalledTimes(2);
  });

  it("does not let a replaced transport's pending completion change the current item view", async () => {
    const old = fixture(), current = fixture(); const r = render(view(old)); await start();
    r.rerender(view(current)); await start(); await authorize(current);
    await act(async () => { await old.client.signOut(); await flush(); });
    expect(status()).toBe("This citation contains one complete item from the source.");
    expect(document.querySelector("pre")?.textContent).toBe(payload.text);
    expect(old.fetcher).not.toHaveBeenCalled();
    expect(current.fetcher).toHaveBeenCalledTimes(2);
  });

  it("does not let an unmounted sign-in rejection change a newly mounted view", async () => {
    const old = fixture(), current = fixture(); const r = render(view(old)); await start();
    r.unmount(); render(view(current)); await start();
    await act(async () => { await old.client.signOut(); await flush(); });
    expect(status()).toBe("Loading authorized evidence…");
    expect(signIn().disabled).toBe(true);
    expect(current.popups).toHaveLength(1);
    expect(current.popups[0].closed).toBe(false);
  });

  it("withdraws evidence on generation change and rejects a late evidence response after sign-out", async () => {
    const pending = deferred<Response>(), f = fixture({ evidenceResponse: pending.promise });
    render(view(f)); await start(); await authorize(f);
    expect(f.fetcher).toHaveBeenCalledTimes(2);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Sign out" })); await flush(); });
    await act(async () => { pending.resolve(response(payload)); await flush(); });
    expect(status()).toBe("Sign in to read this evidence item.");
    expect(document.querySelector("pre")).toBeNull();
    expect(f.client.research!.available()).toBe(false);
  });

  it("clears already displayed evidence after an external auth-generation change", async () => {
    const f = fixture(); render(view(f)); await start(); await authorize(f);
    expect(document.querySelector("pre")?.textContent).toBe(payload.text);
    await act(async () => { await f.client.signOut(); await flush(); });
    expect(status()).toBe("Sign in to read this evidence item.");
    expect(document.querySelector("pre")).toBeNull();
  });

  it("discards a pending presentation attempt when the selected item changes", async () => {
    const f = fixture(), nextId = `rvitem.v1.${"b".repeat(64)}`;
    const r = render(view(f)); await start();
    r.rerender(<ResearchEvidenceEntry itemId={nextId} transport={f.client.research} signOut={f.client.signOut} />);
    await act(async () => { await f.client.signOut(); await flush(); });
    expect(status()).toBe("Sign in to read this evidence item.");
    expect(signIn().disabled).toBe(false);
    expect(document.querySelector("pre")).toBeNull();
    expect(f.fetcher).not.toHaveBeenCalled();
  });

  it("keeps pending page lifecycle transitions privacy-cleared without opening another popup", async () => {
    const f = fixture(); render(view(f)); await start();
    act(() => window.dispatchEvent(new Event("pagehide")));
    expect(document.querySelector("pre")).toBeNull();
    await act(async () => { fireEvent.click(signIn()); await flush(); });
    expect(f.popups).toHaveLength(1);
    await act(async () => { window.dispatchEvent(new Event("pageshow")); await flush(); });
    expect(status()).toBe("Loading authorized evidence…");
    expect(signIn().disabled).toBe(true);
    await authorize(f);
    expect(document.querySelector("pre")?.textContent).toBe(payload.text);
  });

  it("ignores an obsolete fulfilled renderer contract promise without granting data or hiding a current failure", async () => {
    const first = deferred<unknown>(), second = deferred<unknown>();
    let generation = 0;
    const listeners = new Set<() => void>();
    const notify = () => { generation++; for (const listener of listeners) listener(); };
    const read = vi.fn(async () => payload);
    const port: ResearchEvidenceTransport = {
      authGeneration: () => generation, available: () => false,
      subscribe: listener => { listeners.add(listener); return () => { listeners.delete(listener); }; },
      signIn: vi.fn().mockImplementationOnce(() => { notify(); return first.promise; })
        .mockImplementationOnce(() => { notify(); return second.promise; }),
      readEvidenceItem: read,
    };
    render(<ResearchEvidenceEntry itemId={id} transport={port} signOut={async () => { notify(); }} />);
    await start();
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Sign out" })); await flush(); });
    await start();
    await act(async () => { first.resolve(undefined); await flush(); });
    expect(status()).toBe("Loading authorized evidence…");
    expect(signIn().disabled).toBe(true);
    // A current promise that completes without a capability is still a visible failure.
    await act(async () => { second.resolve(undefined); await flush(); });
    expect(status()).toBe("This evidence item is unavailable.");
    expect(signIn().disabled).toBe(false);
    expect(read).not.toHaveBeenCalled();
    expect(document.querySelector("pre")).toBeNull();
  });
});
