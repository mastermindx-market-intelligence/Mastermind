// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ResearchEvidence } from "./ResearchEvidence";
import { evidenceUrl, type ResearchEvidenceTransport } from "./evidence-contract";
const id = `rvitem.v1.${"a".repeat(64)}`;
const text = "  Literal source\f尾🙂e\u0301\n<img src=x onerror=alert(1)>";
const payload = { id, title: "Bounded evidence <script>secret</script>", text, url: evidenceUrl(id), metadata: { coverage: "COMPLETE_BOUNDED_ITEM" } };
function fixture(initial = true) {
  let available = initial, generation = 0;
  const listeners = new Set<() => void>();
  const read = vi.fn(async (_id: string, _signal: AbortSignal): Promise<unknown> => payload);
  const notify = () => { for (const fn of listeners) fn(); };
  const port: ResearchEvidenceTransport = { available: () => available, authGeneration: () => generation,
    subscribe: fn => { listeners.add(fn); return () => { listeners.delete(fn); }; },
    signIn: vi.fn(async () => { generation++; available = true; notify(); }), readEvidenceItem: read };
  const signOut = vi.fn(async () => { generation++; available = false; notify(); });
  return { port, read, signOut, notify, revoke: () => { generation++; available = false; notify(); }, listeners };
}
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
describe("conditional literal item view with no private body cache", () => {
  it("keeps an anonymous shell empty until Research sign-in, without workspace calls", async () => {
    const f = fixture(false); render(<ResearchEvidence itemId={id} transport={f.port} signOut={f.signOut} />);
    expect(f.read).not.toHaveBeenCalled(); expect(screen.queryByText(payload.title)).toBeNull();
    await act(async () => { fireEvent.click(screen.getByText("Sign in to Research")); });
    expect(await screen.findByText(payload.title)).toBeTruthy(); expect(f.read).toHaveBeenCalledTimes(1);
  });
  it("renders complete literal text without HTML interpretation or trimming", async () => {
    const f = fixture(); const { container } = render(<ResearchEvidence itemId={id} transport={f.port} signOut={f.signOut} />);
    await screen.findByText(payload.title);
    expect(container.querySelector("pre")?.textContent).toBe(text);
    expect(container.querySelector("img")).toBeNull(); expect(container.querySelector("script")).toBeNull();
  });
  it("withdraws displayed private text when the auth epoch is revoked", async () => {
    const f = fixture(); const { container } = render(<ResearchEvidence itemId={id} transport={f.port} signOut={f.signOut} />);
    await screen.findByText(payload.title); act(() => f.revoke());
    expect(container.querySelector("pre")).toBeNull(); expect(screen.queryByText(payload.title)).toBeNull();
  });
  it("blocks a late result after sign-out even if the external signout fails", async () => {
    const f = fixture(); let resolve!: (value: unknown) => void;
    f.read.mockImplementationOnce(() => new Promise(yes => { resolve = yes; }));
    const signOut = vi.fn(async () => { throw new Error("provider unavailable"); });
    const { container } = render(<ResearchEvidence itemId={id} transport={f.port} signOut={signOut} />);
    await act(async () => { fireEvent.click(screen.getByText("Sign out")); });
    await act(async () => { resolve(payload); });
    expect(container.querySelector("pre")).toBeNull(); expect(screen.queryByText(payload.title)).toBeNull();
  });
  it("clears hidden/history snapshots and performs a fresh read on pageshow", async () => {
    const f = fixture(); const { container } = render(<ResearchEvidence itemId={id} transport={f.port} signOut={f.signOut} />);
    await screen.findByText(payload.title); act(() => window.dispatchEvent(new Event("pagehide")));
    expect(container.querySelector("pre")).toBeNull();
    await act(async () => { window.dispatchEvent(new Event("pageshow")); });
    expect(f.read).toHaveBeenCalledTimes(2); expect(container.querySelector("pre")?.textContent).toBe(text);
  });
  it("clears on visibility hidden and refuses hidden in-flight projection", async () => {
    const f = fixture(); const { container } = render(<ResearchEvidence itemId={id} transport={f.port} signOut={f.signOut} />);
    await screen.findByText(payload.title);
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    expect(container.querySelector("pre")).toBeNull();
  });
  it("refuses mismatched or oversized data rather than showing a partial item", async () => {
    const f = fixture(); f.read.mockResolvedValueOnce({ ...payload, text: "中".repeat(334) });
    const { container } = render(<ResearchEvidence itemId={id} transport={f.port} signOut={f.signOut} />);
    expect(await screen.findByText("This evidence item is unavailable.")).toBeTruthy(); expect(container.querySelector("pre")).toBeNull();
  });
  it("retries the same item through an existing valid Research token without another sign-in", async () => {
    const f = fixture(); f.read.mockRejectedValueOnce(new Error("READ_FAILED"));
    render(<ResearchEvidence itemId={id} transport={f.port} signOut={f.signOut} />);
    await screen.findByText("This evidence item is unavailable.");
    await act(async () => { fireEvent.click(screen.getByText("Retry evidence")); });
    expect(await screen.findByText(payload.title)).toBeTruthy();
    expect(f.read).toHaveBeenCalledTimes(2); expect(f.port.signIn).not.toHaveBeenCalled();
  });
  it("refuses null/invalid selection before reading and supports existing theme/locale props", () => {
    const f = fixture(); const { container } = render(<ResearchEvidence itemId={null} transport={f.port} signOut={f.signOut} locale="zh-CN" theme="light" />);
    expect(f.read).not.toHaveBeenCalled(); expect(screen.getByText("来源片段")).toBeTruthy();
    expect(container.querySelector(".shell")?.getAttribute("data-theme")).toBe("light");
  });
  it("unsubscribes and aborts when the component unmounts", () => {
    const f = fixture(); f.read.mockImplementationOnce(() => new Promise(() => {}));
    const { unmount } = render(<ResearchEvidence itemId={id} transport={f.port} signOut={f.signOut} />);
    const signal = f.read.mock.calls[0][1]; unmount();
    expect(signal.aborted).toBe(true); expect(f.listeners.size).toBe(0);
  });
});
