import { expect, it, vi } from "vitest";
import { createFixtureCommandBinding } from "./browser-proof-command-fixture";
import { completeOrchestratorCommandBinding } from "./orchestration/host-command-bindings";
import type { PendingPointerStore } from "./orchestration/operation-controller";

it("exposes real composer shape but always refuses submit and recovery without transport", async () => {
  const store: PendingPointerStore = { read: vi.fn(() => null), reserve: vi.fn(() => ({reserved:true as const})), clearIfEqual: vi.fn(() => true) };
  const binding = createFixtureCommandBinding(store);
  expect(completeOrchestratorCommandBinding(binding)).toBe(binding);
  expect(binding.store).toBe(store);
  expect(binding.getView().profiles.map(p => p.ref)).toEqual(["governed_project", "native_research_only"]);
  const form = { goal:"A fixture goal", projectRef:"source-fixture-project", profileRef:"governed_project", frontierModelAlias:"fixture-ceo" };
  const intent = binding.makeLaunchIntent(form)!;
  const pointer = binding.port.prepare(intent);
  const signal = new AbortController().signal;
  expect(await binding.port.submit(pointer,intent,signal)).toEqual({...pointer,disposition:"refused"});
  expect(await binding.port.readOperation(pointer,signal)).toEqual({...pointer,disposition:"refused"});
  expect(binding.makeMessageIntent("session", "text")).toBeNull();
  expect(binding.makeStopIntent("session")).toBeNull();
  expect(store.reserve).not.toHaveBeenCalled();
});
