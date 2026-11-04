// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { MissionHost, AuthState } from "../host";
import fixture from "./fixtures/resource-capacity-owner-read.json";
import { decodeResourceCapacityRead } from "./resource-capacity-read";
import { ResourceCapacityRead } from "./ResourceCapacityRead";
afterEach(cleanup);
function owner() {
  let state: AuthState = { status: "signed_in", acquisition: true, content: false, reason: null };
  let generation = 1;
  const listeners = new Set<(state: AuthState) => void>();
  const read = vi.fn(async (_request: unknown) => decodeResourceCapacityRead(fixture, fixture.selection));
  const host = { auth: { getState: () => state, subscribe: (fn: (state: AuthState) => void) => { listeners.add(fn); return () => { listeners.delete(fn); }; } },
    invalidationGeneration: () => generation, readResourceCapacity: read } as unknown as MissionHost;
  return { host, read, signOut: () => { generation++; state = { ...state, status: "signed_out", acquisition: false }; for (const fn of listeners) fn(state); } };
}
it("reads only after an explicit click with the exact selected work tuple", async () => {
  const env = owner();
  render(<ResourceCapacityRead host={env.host} selection={fixture.selection} />);
  expect(env.read).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Read original claim" }));
  await screen.findByText("Authenticated");
  expect(env.read).toHaveBeenCalledOnce();
  expect(env.read.mock.calls[0][0]).toEqual({ ...fixture.selection, signal: expect.any(AbortSignal) });
  expect(screen.getByText(/Current eligibility has not been evaluated/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: /place|reserve|start/i })).toBeNull();
});
it("never invents a root or source read when selection is absent", () => {
  const env = owner();
  render(<ResourceCapacityRead host={env.host} />);
  expect((screen.getByRole("button", { name: "Read original claim" }) as HTMLButtonElement).disabled).toBe(true);
  expect(env.read).not.toHaveBeenCalled();
  expect(screen.getByText(/Open a work item/)).toBeTruthy();
});
it("removes original receipt details immediately when the owner signs out", async () => {
  const env = owner();
  render(<ResourceCapacityRead host={env.host} selection={fixture.selection} />);
  fireEvent.click(screen.getByRole("button", { name: "Read original claim" }));
  await screen.findByText("Authenticated");
  act(() => env.signOut());
  expect(screen.queryByText("Authenticated")).toBeNull();
  expect((screen.getByRole("button", { name: "Read original claim" }) as HTMLButtonElement).disabled).toBe(true);
});
it("discards a pending original reply when the selected Attempt changes", async () => {
  const env = owner();
  let finish!: (v: ReturnType<typeof decodeResourceCapacityRead>) => void;
  env.read.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const { rerender } = render(<ResourceCapacityRead host={env.host} selection={fixture.selection} />);
  fireEvent.click(screen.getByRole("button", { name: "Read original claim" }));
  rerender(<ResourceCapacityRead host={env.host} selection={{ ...fixture.selection, attempt_id: "ATT-" + "9".repeat(32) }} />);
  await act(async () => finish(decodeResourceCapacityRead(fixture, fixture.selection)));
  await waitFor(() => expect(screen.queryByText("Authenticated")).toBeNull());
});
