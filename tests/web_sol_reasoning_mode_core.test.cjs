"use strict";
const assert = require("node:assert/strict");
const { createHash } = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const corePath = path.join(__dirname, "../integrations/chairman_surfaces/web_sol_extension/reasoning_mode_core.js");
let core;
if (fs.existsSync(corePath)) core = require(corePath);

test("mode core is available", () => {
  assert.equal(typeof core?.qualifyModeReadback, "function");
});

function digest(sample) {
  const keys = Object.keys(sample).filter(key => key !== "selector_evidence_digest").sort();
  return createHash("sha256").update(JSON.stringify(sample, keys)).digest("hex");
}
function sign(sample) {
  sample.selector_evidence_digest = digest(sample);
  return sample;
}
function fixture() {
  const target = {
    runtime_binding_id: `bind-wsx-${"a".repeat(48)}`,
    runtime_binding_generation: 7,
    runtime_binding_fingerprint: "b".repeat(64),
    document_epoch: "c".repeat(32),
  };
  const request = {
    ...target, requested_family: "LATEST", requested_effort: "EXTRA_HIGH",
    not_before_ms: 1000, expires_at_ms: 31000,
  };
  const observations = [1100, 1200].map(observed_at_ms => sign({
    ...target, observed_at_ms, selected_family: "LATEST", selected_effort: "EXTRA_HIGH",
    family_selection_count: 1, effort_control_count: 1, controls_enabled: true,
    page_ready: true, composer_ready: true, generation_state: "IDLE",
    auth_state: "AUTHENTICATED",
  }));
  return { request, observations, nowMs: 1300 };
}
async function run(change = () => {}) {
  const f = fixture();
  change(f);
  return core.qualifyModeReadback(f.request, f.observations, f.nowMs);
}
function changeSample(field, value) {
  return f => { f.observations[1][field] = value; sign(f.observations[1]); };
}

if (core) {
  test("two qualified Extra High observations never authorize an action", async () => {
    const f = fixture();
    const result = await core.qualifyModeReadback(f.request, f.observations, f.nowMs);
    assert.equal(result.status, "MODE_READBACK_MATCH");
    assert.equal(result.selected_model, "LATEST");
    assert.equal(result.selected_effort, "EXTRA_HIGH");
    assert.equal(result.served_model, null);
    assert.equal(result.action_authorized, false);
    assert.equal(result.capability_reprobe_required, true);
    assert.equal(result.target.runtime_binding_generation, 7);
    assert.deepEqual(result.model_evidence, f.observations.map(s => s.selector_evidence_digest));
    assert.ok(Object.isFrozen(result) && Object.isFrozen(result.target) && Object.isFrozen(result.model_evidence));
  });
  test("Pro selector evidence is not served-model or routing-policy admission", async () => {
    const result = await run(f => {
      f.request.requested_effort = "PRO";
      f.observations.forEach(s => { s.selected_effort = "PRO"; sign(s); });
    });
    assert.equal(result.status, "MODE_READBACK_MATCH");
    assert.equal(result.served_model, null);
    assert.equal(result.action_authorized, false);
  });
  for (const [field, value] of [
    ["runtime_binding_id", `bind-wsx-${"d".repeat(48)}`],
    ["runtime_binding_generation", 8],
    ["runtime_binding_fingerprint", "d".repeat(64)],
    ["document_epoch", "d".repeat(32)],
  ]) {
    test(`refuses stale/wrong ${field}, including A-B-A document replacement`, async () => {
      assert.equal((await run(changeSample(field, value))).status, "MODE_IDENTITY_MISMATCH");
    });
  }
  for (const [field, value] of [
    ["selected_family", "SOL"], ["selected_family", "UNKNOWN"],
    ["selected_effort", "PRO"], ["selected_effort", "OTHER"], ["selected_effort", "UNKNOWN"],
  ]) {
    test(`does not infer requested mode from ${field}=${value}`, async () => {
      assert.equal((await run(changeSample(field, value))).status, "MODE_READBACK_MISMATCH");
    });
  }
  for (const [field, value] of [
    ["family_selection_count", 0], ["family_selection_count", 2],
    ["effort_control_count", 0], ["effort_control_count", 2], ["controls_enabled", false],
  ]) {
    test(`refuses unavailable/ambiguous selector ${field}=${value}`, async () => {
      assert.equal((await run(changeSample(field, value))).status, "MODE_SELECTOR_UNAVAILABLE");
    });
  }
  for (const [field, value] of [
    ["page_ready", false], ["composer_ready", false], ["generation_state", "ACTIVE"],
    ["generation_state", "UNKNOWN"], ["auth_state", "AUTH_REQUIRED"], ["auth_state", "UNKNOWN"],
  ]) {
    test(`refuses unqualified surface ${field}=${value}`, async () => {
      assert.equal((await run(changeSample(field, value))).status, "MODE_SURFACE_BLOCKED");
    });
  }
  for (const [name, change] of [
    ["expired request", f => { f.nowMs = 31001; }],
    ["future observation", changeSample("observed_at_ms", 1400)],
    ["pre-mode evidence", f => { f.request.not_before_ms = 1150; }],
    ["same observation replay", f => { f.observations[1] = { ...f.observations[0] }; }],
    ["observation order reversal", f => { f.observations.reverse(); }],
    ["mode barrier equality", f => { f.observations[0].observed_at_ms = 1000; sign(f.observations[0]); }],
  ]) {
    test(`fails closed on ${name}`, async () => {
      assert.equal((await run(change)).status, "MODE_EVIDENCE_STALE");
    });
  }
  test("rejects digest tampering rather than treating a digest as proof", async () => {
    assert.equal((await run(f => { f.observations[1].selector_evidence_digest = "0".repeat(64); })).status,
      "MODE_EVIDENCE_UNVERIFIED");
  });
  for (const [name, change] of [
    ["boolean generation", f => { f.request.runtime_binding_generation = true; }],
    ["unbounded lifetime", f => { f.request.expires_at_ms = 31001; }],
    ["NaN clock", f => { f.nowMs = NaN; }],
    ["unknown requested mode", f => { f.request.requested_effort = "AUTO"; }],
    ["third observation", f => { f.observations.push({ ...f.observations[1] }); }],
    ["missing observation", f => { f.observations.pop(); }],
    ["missing evidence field", f => { delete f.observations[0].selector_evidence_digest; }],
    ["wrong boolean shape", changeSample("controls_enabled", 1)],
    ["fractional selector count", changeSample("effort_control_count", 1.5)],
    ["public command injection", f => { f.request.SEND_TEXT = "private prompt must not echo"; }],
    ["effect-clearance injection", f => { f.request.effect_unknown = false; }],
    ["raw DOM injection", f => { f.observations[1].raw_dom = "private DOM must not echo"; }],
  ]) {
    test(`rejects closed-shape violation: ${name}`, async () => {
      const result = await run(change);
      assert.equal(result.status, "MODE_OBSERVATION_INVALID");
      assert.equal(result.action_authorized, false);
      assert.equal(result.target, null);
      assert.ok(!JSON.stringify(result).includes("private"));
    });
  }
  test("accessor input is rejected without invoking it", async () => {
    let calls = 0;
    const result = await run(f => {
      Object.defineProperty(f.observations[0], "selected_effort", {
        enumerable: true, get() { calls++; return "EXTRA_HIGH"; },
      });
    });
    assert.equal(result.status, "MODE_OBSERVATION_INVALID");
    assert.equal(calls, 0);
  });
  test("snapshots inputs before asynchronous digest work", async () => {
    const f = fixture();
    const pending = core.qualifyModeReadback(f.request, f.observations, f.nowMs);
    f.request.requested_effort = "PRO";
    f.observations[1].selected_effort = "PRO";
    const result = await pending;
    assert.equal(result.status, "MODE_READBACK_MATCH");
    assert.equal(result.selected_effort, "EXTRA_HIGH");
  });
  test("missing digest service fails closed and needs no browser globals", async () => {
    const context = { module: { exports: {} }, TextEncoder, crypto: undefined };
    vm.runInNewContext(fs.readFileSync(corePath, "utf8"), context);
    const f = fixture();
    const result = await context.module.exports.qualifyModeReadback(f.request, f.observations, f.nowMs);
    assert.equal(result.status, "MODE_EVIDENCE_UNVERIFIED");
    assert.equal(result.action_authorized, false);
  });
  for (const field of ["runtime_binding_id", "runtime_binding_fingerprint", "document_epoch"]) {
    test(`rejects trailing-newline normalization in ${field}`, async () => {
      const result = await run(f => {
        f.request[field] += "\n";
        f.observations.forEach(s => { s[field] += "\n"; sign(s); });
      });
      assert.equal(result.status, "MODE_OBSERVATION_INVALID");
    });
  }
  test("observation array extra keys are not silently discarded", async () => {
    const result = await run(f => { f.observations.command = "SEND_TEXT"; });
    assert.equal(result.status, "MODE_OBSERVATION_INVALID");
  });
  test("observation array accessor is never invoked", async () => {
    let calls = 0;
    const result = await run(f => {
      const first = f.observations[0];
      Object.defineProperty(f.observations, "0", {
        enumerable: true, get() { calls++; return first; },
      });
    });
    assert.equal(result.status, "MODE_OBSERVATION_INVALID");
    assert.equal(calls, 0);
  });
  test("repeat/reconnect evaluation is stateless and never sends or grants permission", async () => {
    const first = await run();
    const second = await run();
    assert.deepEqual(second, first);
    const source = fs.readFileSync(corePath, "utf8");
    assert.doesNotMatch(source, /\b(fetch|setTimeout|setInterval|XMLHttpRequest)\s*\(/);
    assert.doesNotMatch(source, /\b(document|window|chrome|localStorage|sessionStorage)\s*\./);
    assert.equal(second.action_authorized, false);
  });
}
