// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import fixture from "./fixtures/capacity-fabric-owner-read.json";
import { CapacityFabricRead } from "./CapacityFabricRead";
import { capacitySummary, decodeCapacityFabric, type CapacityFabricRead as Read } from "./capacity-fabric";
import { bindMissionHost, createNativeClient, type AuthState, type MissionHost } from "../host";

const NOW = Date.parse(fixture.observed_at) + 10_000;
beforeEach(() => { vi.useFakeTimers({ toFake: ["Date"] }); vi.setSystemTime(NOW); });
afterEach(() => { cleanup(); vi.useRealTimers(); });
const body = () => structuredClone(fixture);
function observed(value = body()) {
  const read = decodeCapacityFabric(value);
  if (read.state !== "AVAILABLE") throw Error("The actual Python projection fixture must qualify");
  return read;
}
function owner() {
  let state: AuthState = { status: "signed_in", acquisition: true, content: false, reason: null };
  const listeners = new Set<() => void>();
  const read = vi.fn<(_request: { signal: AbortSignal }) => Promise<Read>>().mockResolvedValue(observed());
  const host = { auth: { getState: () => state, subscribe: (fn: () => void) => { listeners.add(fn); return () => listeners.delete(fn); } },
    invalidationGeneration: () => 1, readCapacityFabric: read } as unknown as MissionHost;
  return { host, read, revoke: () => { state = { ...state, status: "signed_out", acquisition: false }; for (const fn of listeners) fn(); } };
}
function refresh() { fireEvent.click(screen.getByRole("button", { name: "Read capacity" })); }

it("consumes the real public projection and keeps zero, missing windows, and consumer evidence distinct", () => {
  const read = observed();
  expect(read.document.resources[1].windows[2]).toMatchObject({ state: "EXHAUSTED", remaining_pct: 0 });
  expect(read.document.resources[2].windows.every(w => w.remaining_pct === null)).toBe(true);
  expect(read.document.consumers.every(c => c.runtime_state === "NOT_OBSERVED")).toBe(true);
  expect(capacitySummary(read.document)).toEqual({ constrained: 2, unknown: 1, qualifiedAllowances: 3 });
});

it.each(["authority", "private_path", "duplicate", "stale_window", "window_outlives_reset", "stale_consumer", "future_consumer", "spec_only_runtime", "unknown_zero", "boolean_count", "identity"])("refuses malformed or overstated %s evidence", fault => {
  const value: any = body();
  if (fault === "authority") value.admission_authorized = true;
  else if (fault === "private_path") value.projection_path = "/private/config";
  else if (fault === "duplicate") value.resources.push(value.resources[0]);
  else if (fault === "stale_window") value.resources[0].windows[0].observed_at = new Date(NOW - 590_000).toISOString();
  else if (fault === "window_outlives_reset") value.resources[0].windows[0].reset_at = new Date(NOW + 1_000).toISOString();
  else if (fault === "stale_consumer" || fault === "future_consumer") Object.assign(value.consumers[0], {
    runtime_state: "RESULT_PROVEN", evidence_ref: "fixture:receipt", observed_at: new Date(NOW + (fault === "stale_consumer" ? -900_000 : 1_000)).toISOString(),
  });
  else if (fault === "spec_only_runtime") Object.assign(value.consumers[2], {
    runtime_state: "RUNNING", evidence_ref: "fixture:receipt", observed_at: new Date(NOW - 30_000).toISOString(),
  });
  else if (fault === "unknown_zero") value.resources[2].windows[0].remaining_pct = 0;
  else if (fault === "boolean_count") value.resources[0].active = true;
  else value.resources[0].identity_qualified = false;
  expect(decodeCapacityFabric(value)).toEqual({ state: "UNAVAILABLE", reason: "INVALID_RESPONSE" });
});

it("detaches accepted evidence and withdraws it at expiry", () => {
  const value = body(), read = observed(value);
  value.resources[0].windows[0].remaining_pct = 99;
  expect(read.document.resources[0].windows[0].remaining_pct).toBe(70);
  expect(decodeCapacityFabric(fixture, Date.parse(fixture.expires_at))).toEqual({ state: "UNAVAILABLE", reason: "SOURCE_EXPIRED" });
});

it.each(["en", "zh-CN"] as const)("shows independent limits and filters only after an explicit %s read", async locale => {
  const env = owner(), zh = locale === "zh-CN";
  render(<CapacityFabricRead host={env.host} locale={locale} headingLevel={1}/>);
  expect(env.read).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: zh ? "读取容量" : "Read capacity" }));
  await screen.findByText("go:fixture-account");
  const monthly = screen.getByRole("meter", { name: zh ? "go:fixture-account 每月 剩余额度" : "go:fixture-account Monthly remaining" });
  expect(monthly.getAttribute("value")).toBe("0");
  expect(screen.getAllByText(zh ? "尚未观测实时连接" : "Live connection not observed")).toHaveLength(4);
  fireEvent.change(screen.getByRole("combobox", { name: zh ? "供应商" : "Provider", exact: true }), { target: { value: "go" } });
  expect(screen.queryByText("glm:fixture-account")).toBeNull();
  expect(screen.getByText("go:fixture-account")).toBeTruthy();
  expect(env.read).toHaveBeenCalledTimes(1);
  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
});

it("labels a pool cap and missing occupancy without promoting queued work to reservations", async () => {
  const value: any = body();
  value.resources[0].configured_cap_basis = "POOL";
  value.resources[0].active = null;
  value.resources[0].queued = 7;
  const env = owner(); env.read.mockResolvedValue(observed(value));
  render(<CapacityFabricRead host={env.host}/>); refresh();
  const account = (await screen.findByText("glm:fixture-account")).closest("li")!;
  expect(within(account).getByText("Shared pool cap")).toBeTruthy();
  expect(within(account).getByText("Queued").textContent).toContain("7");
  expect(within(account).getByText("In use").textContent).toContain("Unknown");
  expect(within(account).queryByText("Reserved")).toBeNull();
});

it("clears accepted evidence and ignores a late response after sign-out", async () => {
  const env = owner();
  let finish!: (value: Read) => void;
  env.read.mockResolvedValueOnce(observed()).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  render(<CapacityFabricRead host={env.host}/>); refresh(); await screen.findByText("go:fixture-account");
  refresh(); act(env.revoke);
  await act(async () => finish(observed()));
  expect(screen.queryByText("go:fixture-account")).toBeNull();
  expect(screen.getByRole("button", { name: "Read capacity" }).hasAttribute("disabled")).toBe(true);
});

it("aborts an old owner and refuses its late material after host replacement", async () => {
  const old = owner(), current = owner();
  let finish!: (value: Read) => void, signal!: AbortSignal;
  old.read.mockImplementation(request => { signal = request.signal; return new Promise(resolve => { finish = resolve; }); });
  const { rerender } = render(<CapacityFabricRead host={old.host}/>); refresh();
  rerender(<CapacityFabricRead host={current.host}/>);
  expect(signal.aborted).toBe(true);
  await act(async () => finish(observed()));
  expect(screen.queryByText("go:fixture-account")).toBeNull();
  refresh(); await screen.findByText("go:fixture-account");
});

it("expires local evidence without background refresh", async () => {
  vi.useFakeTimers(); vi.setSystemTime(NOW);
  const env = owner(); render(<CapacityFabricRead host={env.host}/>);
  await act(async () => refresh());
  expect(screen.getByText("go:fixture-account")).toBeTruthy();
  await act(async () => vi.advanceTimersByTimeAsync(570_000));
  expect(screen.queryByText("go:fixture-account")).toBeNull();
  expect(screen.getByText("Readings need an update")).toBeTruthy();
  expect(env.read).toHaveBeenCalledTimes(1);
});

it("resets a removed provider filter when a fresh observation changes the account set", async () => {
  const env = owner();
  const next = body(); next.resources = next.resources.filter(row => row.provider === "glm");
  env.read.mockResolvedValueOnce(observed()).mockResolvedValueOnce(observed(next));
  render(<CapacityFabricRead host={env.host}/>); refresh(); await screen.findByText("go:fixture-account");
  fireEvent.change(screen.getByRole("combobox", { name: "Provider", exact: true }), { target: { value: "go" } });
  refresh(); await screen.findByText("glm:fixture-account");
  expect((screen.getByRole("combobox", { name: "Provider", exact: true }) as HTMLSelectElement).value).toBe("");
});

it("uses the fixed native command and rejects reader or auth replacement before release", async () => {
  let notify = (_: unknown) => {}, finish!: (value: unknown) => void;
  const signed = { status: "signed_in", reason: null, acquisition: true, content: false };
  const invoke = vi.fn(async (command: string) => {
    if (command === "auth_status") return signed;
    if (command === "executive_auth_status") return { generation: 0, available: false };
    if (command === "read_capacity_fabric") return new Promise(resolve => { finish = resolve; });
    throw Error("unexpected command");
  });
  const raw = await createNativeClient(invoke as never, async (_event, listener) => { notify = payload => listener({ payload }); return () => {}; });
  const host = bindMissionHost(raw);
  const first = host.readCapacityFabric!({ signal: new AbortController().signal });
  finish(fixture);
  expect((await first).state).toBe("AVAILABLE");
  expect(invoke.mock.calls.filter(([command]) => command === "read_capacity_fabric")).toEqual([["read_capacity_fabric", undefined]]);
  const pending = host.readCapacityFabric!({ signal: new AbortController().signal });
  notify({ ...signed, status: "signed_out", acquisition: false }); finish(fixture);
  await expect(pending).rejects.toThrow("READ_CANCELLED");
});
