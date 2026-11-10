// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { decodeLaunchBindingConfig } from "./launch-config";
import { readLaunchRequestPreview } from "./activation/LaunchRequestPreview";
import { createExecutiveLaunchBinding, resolveLaunchBinding, type LaunchEnrollmentConfig } from "./orchestration/executive-launch-command-port";
import { readCommandView } from "./orchestration/host-command-bindings";
import { OperationController, type OperationPointer, type PendingPointerStore } from "./orchestration/operation-controller";
import { intentIdForOperationKey } from "./orchestration/operation-key";
import { LaunchOrchestrator, type LaunchForm } from "./orchestration/ui/LaunchOrchestrator";

const EEC = "WS:EXECUTIVE-ECOSYSTEM-COMPLETION";
const CCR = "WS:CHAIRMAN-CONTROL-ROOM";
function manifest() {
  const common = { priority: 0, attemptLimit: 1,
    projects: [{ ref: "executive-infrastructure", label: "Infrastructure" }] };
  return { v: 2, defaultWorkstream: EEC, bindings: [
    { ...common, label: "Executive Ecosystem", workstream: EEC, profiles: [
      { ref: "research_only", label: "Research only" },
      { ref: "native_research_only", label: "Native research only" }] },
    { ...common, label: "Meta-CEO Office", workstream: CCR,
      profiles: [{ ref: "research_only", label: "Research only" }] },
  ] };
}
function config(): LaunchEnrollmentConfig {
  const value = decodeLaunchBindingConfig(JSON.stringify(manifest()));
  if (!value || !("bindings" in value)) throw new Error("Expected v2 enrollment");
  return value;
}
const goal: LaunchForm = { goal: "Read the completion frontier.",
  projectRef: "executive-infrastructure", profileRef: "research_only" };
function setup(value = config()) {
  const data = new Map<string, OperationPointer>();
  const store: PendingPointerStore = {
    read: scope => data.get(scope) ?? null,
    reserve: (scope, pointer) => {
      const retained = data.get(scope);
      if (retained) return { reserved: false, pointer: retained };
      data.set(scope, pointer); return { reserved: true };
    },
    clearIfEqual: (scope, pointer) => {
      const retained = data.get(scope);
      if (JSON.stringify(retained) !== JSON.stringify(pointer)) return false;
      return data.delete(scope);
    },
  };
  const callTool = vi.fn(async (..._args: unknown[]) => { throw new Error("lost response"); });
  const binding = createExecutiveLaunchBinding(value, { callTool }, {
    context: () => ({ principalScope: "scope-A", generation: "epoch-1" }),
    store, getSession: () => null, subscribe: () => () => {},
  });
  return { binding, store, callTool };
}
afterEach(cleanup);

describe("closed finite workstream enrollment", () => {
  it("freezes each binding while preserving exact default and per-entry optional presence", () => {
    const value = config();
    expect(value.defaultWorkstream).toBe(EEC);
    expect(value.bindings.map(binding => binding.workstream)).toEqual([EEC, CCR]);
    expect(Object.isFrozen(value.bindings[0].profiles[0])).toBe(true);
    expect(resolveLaunchBinding(value, CCR)?.attemptLimit).toBe(1);
    expect(resolveLaunchBinding(value, CCR)).not.toHaveProperty("validation");
    expect(resolveLaunchBinding(value, "WS:Unknown")).toBeNull();
    expect(resolveLaunchBinding(value, null as unknown as string)).toBeNull();
  });
  it.each(["default", "duplicate", "entry-version", "unknown", "bounded", "reverse", "native-only", "label", "template-cap"])(
    "refuses a broader or ambiguous catalog: %s", fault => {
      const value = manifest();
      if (fault === "default") value.defaultWorkstream = "WS:Missing";
      if (fault === "duplicate") value.bindings[1].workstream = EEC;
      if (fault === "entry-version") Object.assign(value.bindings[0], { v: 1 });
      if (fault === "unknown") Object.assign(value, { token: "unaccepted" });
      if (fault === "bounded") value.bindings[1].profiles[0].ref = "bounded_code_change";
      if (fault === "reverse") value.bindings[0].profiles.reverse();
      if (fault === "native-only") value.bindings[0].profiles.shift();
      if (fault === "label") value.bindings[0].label = "x".repeat(121);
      if (fault === "template-cap") {
        value.bindings = Array.from({ length: 9 }, (_, i) => ({
          ...structuredClone(value.bindings[0]), workstream: "WS:Entry" + i }));
        value.defaultWorkstream = "WS:Entry0";
      }
      expect(decodeLaunchBindingConfig(JSON.stringify(value))).toBeNull();
    });
  it.each([{ pytest_targets: [] }, { compileall_paths: [] }, { git_diff_check: false }])(
    "refuses nonempty inert validation in a v2 native pair: %j", validation => {
      const value = manifest();
      Object.assign(value.bindings[0], { validation });
      expect(decodeLaunchBindingConfig(JSON.stringify(value))).toBeNull();
      const { label: _label, ...leaf } = value.bindings[0];
      expect(decodeLaunchBindingConfig(JSON.stringify({ v: 1, ...leaf }))).not.toBeNull();
    });
  it("preserves exactly empty validation in a v2 native pair", () => {
    const value = manifest(); Object.assign(value.bindings[0], { validation: {} });
    const decoded = decodeLaunchBindingConfig(JSON.stringify(value)) as LaunchEnrollmentConfig;
    expect(decoded.bindings[0].validation).toEqual({});
  });
  it("keeps legacy payload and operation key identical when its workstream is explicit", () => {
    const row = config().bindings[0];
    const { label: _label, ...leaf } = row;
    const legacy = createExecutiveLaunchBinding(leaf, { callTool: vi.fn() }, {
      context: () => ({ principalScope: "scope-A", generation: "epoch-1" }),
      store: setup().store, getSession: () => null, subscribe: () => () => {},
    });
    expect(legacy.makeLaunchIntent(goal)).toEqual(legacy.makeLaunchIntent({ ...goal, workstreamRef: EEC }));
    expect(setup().binding.makeLaunchIntent(goal)).toEqual(legacy.makeLaunchIntent(goal));
  });
});

describe("one port preserves exact selected work and original operation", () => {
  it("prepares the nondefault workstream and separates its key without borrowing sibling choices", () => {
    const { binding } = setup();
    const eec = binding.makeLaunchIntent({ ...goal, workstreamRef: EEC })!;
    const ccr = binding.makeLaunchIntent({ ...goal, workstreamRef: CCR })!;
    expect(eec.payload.operation_key).not.toBe(ccr.payload.operation_key);
    expect(ccr.targetKey).toBe(CCR);
    expect(binding.port.prepare(ccr).targetKey).toBe(CCR);
    expect(binding.makeLaunchIntent({ ...goal, workstreamRef: CCR, profileRef: "native_research_only" })).toBeNull();
    expect(binding.makeLaunchIntent({ ...goal, workstreamRef: "WS:Missing" })).toBeNull();
    expect(() => binding.port.prepare({ ...ccr, targetKey: EEC })).toThrow();
    expect(() => binding.port.prepare({ ...ccr, payload: { ...ccr.payload, workstream: EEC } })).toThrow();
  });
  it("does not borrow another binding's department or requested CEO", () => {
    const value = manifest();
    value.bindings[1].projects = [{ ref: "office-project", label: "Office" }];
    Object.assign(value.bindings[0], { frontierModels: [{ ref: "frontier.one", label: "One" }] });
    const selected = decodeLaunchBindingConfig(JSON.stringify(value)) as LaunchEnrollmentConfig;
    const { binding } = setup(selected);
    expect(binding.makeLaunchIntent({ ...goal, workstreamRef: CCR })).toBeNull();
    expect(binding.makeLaunchIntent({ ...goal, workstreamRef: CCR,
      projectRef: "office-project", frontierModelAlias: "frontier.one" })).toBeNull();
    expect(binding.makeLaunchIntent({ ...goal, workstreamRef: CCR, projectRef: "office-project" })?.targetKey).toBe(CCR);
  });
  it("previews the exact detached workstream and refuses accessors and foreign values", () => {
    const { binding } = setup();
    expect(readLaunchRequestPreview(binding, { ...goal, workstreamRef: CCR })).toMatchObject({
      state: "PREPARED", targetKey: CCR });
    const getter = vi.fn(() => CCR);
    const accessor = Object.defineProperty({ ...goal }, "workstreamRef", { get: getter });
    expect(readLaunchRequestPreview(binding, accessor)).toEqual({ state: "UNAVAILABLE" });
    expect(getter).not.toHaveBeenCalled();
    for (const value of ["WS:Missing", null, 12]) {
      expect(readLaunchRequestPreview(binding, { ...goal, workstreamRef: value } as LaunchForm))
        .toEqual({ state: "UNAVAILABLE" });
    }
  });
  it("retains one pending slot across workstream selection and reads the original pointer", async () => {
    const { binding, store, callTool } = setup();
    const controller = new OperationController(binding.port, store);
    const eec = binding.makeLaunchIntent({ ...goal, workstreamRef: EEC })!;
    const original = binding.port.prepare(eec);
    await controller.begin(eec);
    expect(await store.read("scope-A")).toEqual(original);
    await controller.begin(binding.makeLaunchIntent({ ...goal, workstreamRef: CCR })!);
    expect(callTool).toHaveBeenCalledTimes(1);
    expect(await store.read("scope-A")).toEqual(original);
    await controller.recover();
    expect(callTool.mock.calls[1][0]).toBe("ceo_intent_status");
    expect(callTool.mock.calls[1][1]).toEqual({ intent_id: intentIdForOperationKey(original.operationKey) });
    expect(await store.read("scope-A")).toEqual(original);
  });
  it("does not erase malformed catalog metadata into a usable default view", () => {
    const { binding } = setup();
    const view = binding.getView();
    expect(readCommandView(binding).workstreams?.map(entry => entry.ref)).toEqual([EEC, CCR]);
    for (const broken of [{ ...view, defaultWorkstream: "WS:Missing" },
      { ...view, workstreams: [] }, { ...view, workstreams: [view.workstreams![0], view.workstreams![0]] }]) {
      expect(readCommandView({ ...binding, getView: () => broken }).projects).toEqual([]);
    }
  });
});

describe("workstream selection uses the existing mounted launch form", () => {
  it("preserves the goal, resets sibling choices, and sends the visible workstream in preview and launch", async () => {
    const { binding } = setup();
    const view = readCommandView(binding);
    const preview = vi.fn((form: LaunchForm) => readLaunchRequestPreview(binding, form));
    const submit = vi.fn();
    const user = userEvent.setup();
    render(<LaunchOrchestrator {...view} submitting={false} onSubmit={submit}
      onCancel={() => {}} previewRequest={preview} />);
    await user.type(screen.getByLabelText("Goal"), goal.goal);
    await user.selectOptions(screen.getByLabelText("Profile"), "native_research_only");
    await user.selectOptions(screen.getByLabelText("Workstream"), CCR);
    expect((screen.getByLabelText("Goal") as HTMLTextAreaElement).value).toBe(goal.goal);
    expect((screen.getByLabelText("Profile") as HTMLSelectElement).value).toBe("research_only");
    expect(screen.queryByRole("option", { name: "Native research only" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Preview requested scope" }));
    expect(preview.mock.calls[0][0].workstreamRef).toBe(CCR);
    await user.click(screen.getByRole("button", { name: /^Launch$/ }));
    expect(submit.mock.calls[0][0]).toEqual({ ...goal, workstreamRef: CCR });
    expect((screen.getByLabelText("Workstream") as HTMLSelectElement).disabled).toBe(true);
  });
  it("keeps an unavailable retained workstream and draft instead of silently selecting the default", () => {
    const view = readCommandView(setup().binding);
    render(<LaunchOrchestrator {...view} workstreamRef="WS:Removed" initialDraft={goal.goal}
      submitting={false} onSubmit={vi.fn()} onCancel={() => {}} />);
    expect((screen.getByLabelText("Goal") as HTMLTextAreaElement).value).toBe(goal.goal);
    expect((screen.getByRole("button", { name: /^Launch$/ }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByLabelText("Workstream") as HTMLSelectElement).value).toBe("WS:Removed");
  });
  it("keeps an Office target fixed while its existing form remains mounted", () => {
    const view = readCommandView(setup().binding);
    const changed = vi.fn();
    const rendered = render(<LaunchOrchestrator {...view} workstreamRef={CCR} lockWorkstream
      initialDraft={goal.goal} submitting={false} onSubmit={vi.fn()} onCancel={() => {}}
      onWorkstreamChange={changed} />);
    const goalElement = screen.getByLabelText("Goal");
    rendered.rerender(<LaunchOrchestrator {...view} workstreamRef={CCR} lockWorkstream
      initialDraft="must not replace" submitting={false} onSubmit={vi.fn()} onCancel={() => {}}
      onWorkstreamChange={changed} />);
    expect(screen.getByLabelText("Goal")).toBe(goalElement);
    expect((goalElement as HTMLTextAreaElement).value).toBe(goal.goal);
    expect((screen.getByLabelText("Workstream") as HTMLSelectElement).disabled).toBe(true);
    expect(changed).not.toHaveBeenCalled();
  });
});

it("keeps the canonical 4096-byte v2 budget independent of the sixteen-template limit", () => {
  const entry = { label: "A", workstream: "WS:W0", priority: 0,
    projects: [{ ref: "aa", label: "A" }], profiles: [{ ref: "research_only", label: "R" }] };
  const value = { v: 2, defaultWorkstream: "WS:W0", bindings:
    Array.from({ length: 16 }, (_, i) => ({ ...structuredClone(entry), workstream: "WS:W" + i })) };
  expect(decodeLaunchBindingConfig(JSON.stringify(value))).not.toBeNull();
  for (const binding of value.bindings) binding.label = "x".repeat(120);
  expect(decodeLaunchBindingConfig(JSON.stringify(value))).toBeNull();
});
