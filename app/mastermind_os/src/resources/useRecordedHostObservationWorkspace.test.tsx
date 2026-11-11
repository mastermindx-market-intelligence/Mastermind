// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import fixture from "./fixtures/recorded-host-observation-owner.json";
import { decodeHostObservationRead } from "./recorded-host-observation";
import { useRecordedHostObservationWorkspace, type RecordedHostWorkspaceProps } from "./useRecordedHostObservationWorkspace";
const available = () => decodeHostObservationRead(fixture, fixture.selection);
function props(): RecordedHostWorkspaceProps {
  return { selection: fixture.selection, authGeneration: 1, sourceGeneration: () => 1, canRead: () => true, readCurrent: vi.fn(async () => available()) };
}
it("does not read on mount; explicit read retains the exact owner result", async () => {
  const p = props(), view = renderHook(() => useRecordedHostObservationWorkspace(p));
  expect(p.readCurrent).not.toHaveBeenCalled();
  await act(() => view.result.current.read());
  expect(p.readCurrent).toHaveBeenCalledTimes(1); expect(view.result.current.state.state).toBe("AVAILABLE");
});
it.each(["auth", "source", "selection", "permission", "method"])("masks an accepted body immediately on %s departure and A-B-A", async fault => {
  const p = props(), view = renderHook(v => useRecordedHostObservationWorkspace(v), { initialProps: p });
  await act(() => view.result.current.read()); expect(view.result.current.state.state).toBe("AVAILABLE");
  const next = { ...p };
  if (fault === "auth") next.authGeneration++;
  if (fault === "source") next.sourceGeneration = () => 2;
  if (fault === "selection") next.selection = { ...fixture.selection, attempt_id: "ATT-" + "9".repeat(32) };
  if (fault === "permission") next.canRead = () => false;
  if (fault === "method") next.readCurrent = vi.fn(async () => available());
  view.rerender(next); expect(view.result.current.state.state).toBe("UNAVAILABLE");
  view.rerender(p); expect(view.result.current.state.state).toBe("UNAVAILABLE"); expect(p.readCurrent).toHaveBeenCalledTimes(1);
});
it("discards late result after selection change with zero replacement read", async () => {
  const p = props(); let finish!: (value: ReturnType<typeof available>) => void;
  p.readCurrent = vi.fn(() => new Promise<ReturnType<typeof available>>(resolve => { finish = resolve; }));
  const view = renderHook(v => useRecordedHostObservationWorkspace(v), { initialProps: p });
  let pending!: Promise<void>;
  act(() => { pending = view.result.current.read(); });
  view.rerender({ ...p, selection: null });
  await act(async () => { finish(available()); await pending; });
  expect(view.result.current.state.state).toBe("UNAVAILABLE"); expect(p.readCurrent).toHaveBeenCalledTimes(1);
});
it("rechecks actual permission on a captured click before any source call", async () => {
  let permitted = true; const p = { ...props(), canRead: () => permitted };
  const view = renderHook(() => useRecordedHostObservationWorkspace(p));
  const read = view.result.current.read; permitted = false; await act(() => read());
  expect(p.readCurrent).not.toHaveBeenCalled();
});
