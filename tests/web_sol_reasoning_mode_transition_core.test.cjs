"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const corePath = path.join(
  __dirname,
  "../integrations/chairman_surfaces/web_sol_extension/reasoning_mode_transition_core.js",
);
let core;
if (fs.existsSync(corePath)) core = require(corePath);

test("mode transition core is available", () => {
  assert.equal(typeof core?.planModeTransition, "function");
});

function observed({
  family = "SOL",
  effort = "PRO",
  min = 0,
  max = 4,
  value = effort === "PRO" ? 4 : effort === "EXTRA_HIGH" ? 3 : effort === "HIGH" ? 2 : effort === "MEDIUM" ? 1 : 0,
  enabled = true,
  status = "MODE_PICKER_OBSERVED",
  digest = "a".repeat(64),
} = {}) {
  return {
    schema: "mastermind.web_sol_mode_picker_observation/v1",
    status,
    selected_family: family,
    selected_effort: effort,
    family_selection_count: 1,
    effort_control_count: 1,
    controls_enabled: enabled,
    slider: {min, max, value},
    selector_state_digest: digest,
    served_model: null,
    action_authorized: false,
  };
}

function unavailable(status = "MODE_PICKER_UNAVAILABLE") {
  return {
    schema: "mastermind.web_sol_mode_picker_observation/v1",
    status,
    selected_family: null,
    selected_effort: null,
    family_selection_count: 0,
    effort_control_count: 0,
    controls_enabled: false,
    slider: null,
    selector_state_digest: null,
    served_model: null,
    action_authorized: false,
  };
}

function request(family = "SOL", effort = "EXTRA_HIGH") {
  return {requested_family: family, requested_effort: effort};
}

if (core) {
  test("plans Pro to Extra High as one same-family semantic slider transition", () => {
    const result = core.planModeTransition(request("SOL", "EXTRA_HIGH"), observed());
    assert.equal(result.status, "MODE_TRANSITION_READY");
    assert.equal(result.transition_kind, "SET_EFFORT_VALUE");
    assert.equal(result.current_family, "SOL");
    assert.equal(result.current_effort, "PRO");
    assert.equal(result.requested_family, "SOL");
    assert.equal(result.requested_effort, "EXTRA_HIGH");
    assert.equal(result.target_slider_value, 3);
    assert.equal(result.selector_state_digest, "a".repeat(64));
    assert.equal(result.policy_admission_required, false);
    assert.equal(result.action_authorized, false);
    assert.equal(result.browser_mutation_performed, false);
    assert.equal(result.readback_required, true);
    assert.equal(result.capability_reprobe_required, true);
    assert.equal(result.served_model, null);
    assert.ok(Object.isFrozen(result));
  });

  test("plans same-family Extra High to Pro while leaving admission to its owner", () => {
    const result = core.planModeTransition(
      request("LATEST", "PRO"),
      observed({family: "LATEST", effort: "EXTRA_HIGH"}),
    );
    assert.equal(result.status, "MODE_TRANSITION_READY");
    assert.equal(result.target_slider_value, 4);
    assert.equal(result.policy_admission_required, true);
    assert.equal(result.action_authorized, false);
  });

  test("already-selected effort is a no-change plan rather than a mutation", () => {
    const result = core.planModeTransition(
      request("SOL", "EXTRA_HIGH"),
      observed({effort: "EXTRA_HIGH"}),
    );
    assert.equal(result.status, "MODE_TRANSITION_NO_CHANGE");
    assert.equal(result.transition_kind, "NONE");
    assert.equal(result.target_slider_value, null);
    assert.equal(result.browser_mutation_performed, false);
  });

  test("family change is explicitly unsupported", () => {
    const result = core.planModeTransition(request("LATEST", "EXTRA_HIGH"), observed({family: "SOL"}));
    assert.equal(result.status, "MODE_FAMILY_CHANGE_UNSUPPORTED");
    assert.equal(result.transition_kind, "NONE");
    assert.equal(result.target_slider_value, null);
    assert.equal(result.action_authorized, false);
  });

  test("disabled observed controls block the transition", () => {
    const result = core.planModeTransition(request(), observed({enabled: false}));
    assert.equal(result.status, "MODE_TRANSITION_DISABLED");
    assert.equal(result.transition_kind, "NONE");
  });

  for (const status of [
    "MODE_PICKER_UNAVAILABLE",
    "MODE_PICKER_AMBIGUOUS",
    "MODE_PICKER_INVALID",
    "MODE_PICKER_UNSUPPORTED",
    "MODE_PICKER_EVIDENCE_UNVERIFIED",
  ]) {
    test(`non-observed picker status ${status} stays unavailable`, () => {
      const result = core.planModeTransition(request(), unavailable(status));
      assert.equal(result.status, "MODE_TRANSITION_UNAVAILABLE");
      assert.equal(result.action_authorized, false);
    });
  }

  test("requested effort outside the observed slider range is unavailable", () => {
    const result = core.planModeTransition(
      request("SOL", "PRO"),
      observed({effort: "HIGH", max: 3, value: 2}),
    );
    assert.equal(result.status, "MODE_TARGET_UNAVAILABLE");
    assert.equal(result.target_slider_value, null);
  });

  test("only Extra High and Pro are admitted as first-canary targets", () => {
    const result = core.planModeTransition(
      {requested_family: "SOL", requested_effort: "HIGH"},
      observed(),
    );
    assert.equal(result.status, "MODE_TRANSITION_INVALID");
  });

  test("picker effort and slider position must agree before planning", () => {
    const result = core.planModeTransition(
      request(),
      observed({effort: "PRO", value: 3}),
    );
    assert.equal(result.status, "MODE_TRANSITION_INVALID");
  });

  for (const [name, mutate] of [
    ["extra request field", (r, _o) => { r.command = "CLICK"; }],
    ["extra observation field", (_r, o) => { o.raw_dom = "private"; }],
    ["extra slider field", (_r, o) => { o.slider.selector = "[role=slider]"; }],
    ["malformed digest", (_r, o) => { o.selector_state_digest = "bad"; }],
    ["upstream action authority", (_r, o) => { o.action_authorized = true; }],
    ["served-model injection", (_r, o) => { o.served_model = "gpt-secret"; }],
    ["wrong family count", (_r, o) => { o.family_selection_count = 2; }],
    ["wrong effort count", (_r, o) => { o.effort_control_count = 2; }],
  ]) {
    test(`closed-shape or authority violation fails invalid: ${name}`, () => {
      const r = request();
      const o = observed();
      mutate(r, o);
      const result = core.planModeTransition(r, o);
      assert.equal(result.status, "MODE_TRANSITION_INVALID");
      assert.equal(result.action_authorized, false);
      assert.ok(!JSON.stringify(result).includes("private"));
      assert.ok(!JSON.stringify(result).includes("gpt-secret"));
    });
  }

  test("planner never mutates its request or observation", () => {
    const r = request();
    const o = observed();
    const beforeR = JSON.stringify(r);
    const beforeO = JSON.stringify(o);
    core.planModeTransition(r, o);
    assert.equal(JSON.stringify(r), beforeR);
    assert.equal(JSON.stringify(o), beforeO);
  });

  test("planner source contains no browser mutation, transport, retry, or persistence primitive", () => {
    const source = fs.readFileSync(corePath, "utf8");
    assert.doesNotMatch(source, /\.click\s*\(/);
    assert.doesNotMatch(source, /\.focus\s*\(/);
    assert.doesNotMatch(source, /dispatchEvent\s*\(/);
    assert.doesNotMatch(source, /\b(?:KeyboardEvent|MouseEvent|PointerEvent)\b/);
    assert.doesNotMatch(source, /\b(?:fetch|XMLHttpRequest|setTimeout|setInterval)\s*\(/);
    assert.doesNotMatch(source, /\b(?:chrome|document|window|localStorage|sessionStorage)\s*\./);
    assert.doesNotMatch(source, /\b(?:retry|resend|sendMessage|executeScript)\b/i);
  });
}
