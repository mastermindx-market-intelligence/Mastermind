/** Disposable component proof for an exact frozen or current port/controller. */
import assert from "node:assert/strict";
import readline from "node:readline";
import { pathToFileURL } from "node:url";

const [portFile, controllerFile, scenario, storeContract = "legacy"] = process.argv.slice(2);
assert(["legacy", "atomic"].includes(storeContract));
const { ExecutiveLaunchCommandPort } = await import(pathToFileURL(portFile));
const { OperationController } = await import(pathToFileURL(controllerFile));
const input = readline.createInterface({ input: process.stdin });
const waiting = new Map();
let statusEnvelope;
input.on("line", line => {
  const message = JSON.parse(line);
  const resolve = waiting.get(message.id);
  assert(resolve, "reply must match an outstanding exact call");
  waiting.delete(message.id);
  if (message.envelope.tool === "ceo_intent_status") {
    statusEnvelope = structuredClone(message.envelope);
  }
  resolve(message.envelope);
});
let sequence = 0;
const calls = [];
const client = {
  callTool(name, args) {
    const id = ++sequence;
    calls.push({ name, args });
    process.stdout.write(JSON.stringify({ type: "call", id, name, args }) + "\n");
    return new Promise(resolve => waiting.set(id, resolve));
  },
};
const ctx = { principalScope: "fixture-principal", generation: "fixture-generation-1" };
const config = {
  workstream: "WS:ORIGINAL-LAUNCH", priority: 5,
  projects: [{ ref: "executive-infrastructure", label: "Executive infrastructure" }],
  profiles: [{ ref: "research_only", label: "Research only" }],
};
const form = { goal: "Read the disposable fixture and return evidence.",
  projectRef: "executive-infrastructure", profileRef: "research_only" };
function pointerStore(initial) {
  const hints = new Map(initial ? [[ctx.principalScope, structuredClone(initial)]] : []);
  const store = {
    read(scope) { return hints.get(scope) ?? null; },
  };
  if (storeContract === "atomic") Object.assign(store, {
    reserve(scope, pointer) {
      const prior = hints.get(scope);
      if (prior) return { reserved: false, pointer: structuredClone(prior) };
      hints.set(scope, structuredClone(pointer));
      return { reserved: true };
    },
    clearIfEqual(scope, pointer) {
      assert.deepEqual(hints.get(scope), pointer);
      hints.delete(scope);
      return true;
    },
  });
  else Object.assign(store, {
    write(scope, pointer) { hints.set(scope, structuredClone(pointer)); },
    clear(scope, pointer) {
      assert.deepEqual(hints.get(scope), pointer);
      hints.delete(scope);
    },
  });
  return { hints, store };
}
const { hints, store } = pointerStore();
const port = new ExecutiveLaunchCommandPort(config, client, () => ctx);
const intent = port.makeLaunchIntent(form);
assert(intent);
const originalPointer = port.prepare(intent);
const controller = new OperationController(port, store);
const initial = await controller.begin(intent);
let final = initial;
let pendingBegin;
if (scenario === "lost-reply") {
  assert.equal(initial.status, "unknown");
  assert.deepEqual(hints.get(ctx.principalScope), originalPointer);
  const reopenedPort = new ExecutiveLaunchCommandPort(
    { ...config, workstream: "WS:CHANGED-UI" }, client, () => ctx);
  const reopened = new OperationController(reopenedPort, store);
  pendingBegin = await reopened.begin(reopenedPort.makeLaunchIntent(form));
  assert.equal(pendingBegin.status, "checking");
  assert.equal(pendingBegin.reason, "PENDING_POINTER");
  assert.equal(calls.length, 1, "pending operation must block a second submit");
  final = await reopened.recover();
  assert.equal(calls.filter(call => call.name === "ceo_intent_status").length, 1);
} else {
  assert.equal(initial.status, "accepted");
}
if (final.status === "accepted") {
  assert.equal(final.missionSelection.workRef, config.workstream);
  assert.match(final.missionSelection.rootJobId, /^JOB-/);
  assert.equal(hints.size, 0);
} else {
  // Preserve observed incompatibility as a failed qualification in the JSON report.
  assert.equal(scenario, "lost-reply");
  assert.equal(final.status, "unknown", JSON.stringify(final));
  assert.deepEqual(hints.get(ctx.principalScope), originalPointer);
}
assert.equal(calls.filter(call => call.name === "submit_ceo_intent").length, 1);

const guardResults = [];
const positiveVersionControls = [];
if (statusEnvelope && final.status === "accepted") {
  {
    const altered = structuredClone(statusEnvelope);
    altered.server_version = "1.5.0";
    let reads = 0;
    const positiveClient = { async callTool(tool, args) {
      assert.equal(tool, "ceo_intent_status", "positive version control cannot submit");
      assert.deepEqual(args, calls.find(call => call.name === tool).args);
      reads += 1;
      return altered;
    } };
    const pending = pointerStore(originalPointer);
    const positivePort = new ExecutiveLaunchCommandPort(
      { ...config, workstream: "WS:CHANGED-UI" }, positiveClient, () => ctx);
    const positiveController = new OperationController(positivePort, pending.store);
    const blocked = await positiveController.begin(positivePort.makeLaunchIntent(form));
    assert.equal(blocked.reason, "PENDING_POINTER");
    assert.equal(reads, 0);
    const result = await positiveController.recover();
    assert.equal(result.status, "accepted", "qualified 1.5.0 recovery must remain accepted");
    assert.equal(result.missionSelection.workRef, config.workstream);
    assert.equal(pending.hints.size, 0);
    assert.equal(reads, 1);
    positiveVersionControls.push({
      name: "qualified-version:1.5.0",
      status: result.status,
      pending_pointer_cleared: true,
    });
  }
  const mutations = [
    ...["1.3.0", "1.3.1", "1.6.0", "2.0.0", null, 1.4, {}].map(version => [
      "unsupported-version:" + JSON.stringify(version),
      value => { value.server_version = version; },
    ]),
    ["foreign-tool", value => { value.tool = "executive_job"; }],
    ["wrong-mode", value => { value.mode = "write"; }],
    ["extra-envelope-field", value => { value.extra = true; }],
    ["foreign-intent", value => { value.data.intent_id = "auto-" + "0".repeat(32); }],
    ["malformed-degraded", value => { value.degraded = [1]; }],
    ["future-receipt-schema", value => { value.data.schema = "mastermind.ceo_intent_receipt.v3"; }],
  ];
  for (const [name, mutate] of mutations) {
    const altered = structuredClone(statusEnvelope);
    mutate(altered);
    let reads = 0;
    const guardClient = { async callTool(tool, args) {
      assert.equal(tool, "ceo_intent_status", "negative control cannot submit");
      assert.deepEqual(args, calls.find(call => call.name === tool).args);
      reads += 1;
      return altered;
    } };
    const pending = pointerStore(originalPointer);
    const guardPort = new ExecutiveLaunchCommandPort(
      { ...config, workstream: "WS:CHANGED-UI" }, guardClient, () => ctx);
    const guardController = new OperationController(guardPort, pending.store);
    const blocked = await guardController.begin(guardPort.makeLaunchIntent(form));
    assert.equal(blocked.reason, "PENDING_POINTER");
    assert.equal(reads, 0);
    const result = await guardController.recover();
    assert.equal(result.status, "unknown", name);
    assert.deepEqual(pending.hints.get(ctx.principalScope), originalPointer, name);
    assert.equal(reads, 1);
    guardResults.push({ name, status: result.status, pending_pointer_retained: true });
  }
}
process.stdout.write(JSON.stringify({
  type: "result", scenario, initial_state: initial.status,
  blocked_duplicate_begin: pendingBegin?.reason ?? null,
  final_state: final.status, reason: final.reason,
  mission_selection: final.missionSelection ?? null,
  submit_calls: 1, status_calls: calls.filter(call => call.name === "ceo_intent_status").length,
  pending_hints: hints.size,
  compatibility_passed: final.status === "accepted",
  positive_version_controls: positiveVersionControls,
  negative_controls: guardResults,
}) + "\n");
input.close();
