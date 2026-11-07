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


test("mode effort action candidate API is available", () => {
  assert.equal(typeof core?.prepareModeEffortActionCandidate, "function");
});

function actionRequest(overrides = {}) {
  return {
    schema: "mastermind.web_sol_mode_effort_action_request/v1",
    runtime_binding_id: `bind-wsx-${"d".repeat(48)}`,
    runtime_binding_generation: 9,
    runtime_binding_fingerprint: "e".repeat(64),
    document_epoch: "f".repeat(32),
    operation_key: "frontier-mode-extra-high-001",
    nonce: "mode-nonce-1234567890",
    issued_at_ms: 1000,
    expires_at_ms: 31000,
    requested_family: "SOL",
    requested_effort: "EXTRA_HIGH",
    ...overrides,
  };
}

if (core) {
  test("prepares one exact-bound Pro to Extra High action candidate without authority", () => {
    const plan = core.planModeTransition(request("SOL", "EXTRA_HIGH"), observed({effort: "PRO"}));
    const result = core.prepareModeEffortActionCandidate(actionRequest(), plan, 1300);
    assert.equal(result.status, "MODE_ACTION_READY");
    assert.equal(result.action, "SET_REASONING_EFFORT");
    assert.equal(result.target.runtime_binding_generation, 9);
    assert.equal(result.target.document_epoch, "f".repeat(32));
    assert.equal(result.operation_key, "frontier-mode-extra-high-001");
    assert.equal(result.nonce, "mode-nonce-1234567890");
    assert.equal(result.requested_family, "SOL");
    assert.equal(result.requested_effort, "EXTRA_HIGH");
    assert.equal(result.selector_state_digest, "a".repeat(64));
    assert.equal(result.target_slider_value, 3);
    assert.equal(result.policy_admission_required, false);
    assert.equal(result.action_authorized, false);
    assert.equal(result.browser_mutation_performed, false);
    assert.equal(result.post_action_readback_required, true);
    assert.equal(result.capability_reprobe_required, true);
    assert.equal(result.exact_owner_admission_required, true);
    assert.equal(result.served_model, null);
    assert.ok(Object.isFrozen(result));
    assert.ok(Object.isFrozen(result.target));
  });

  test("Pro action candidate keeps policy admission external", () => {
    const plan = core.planModeTransition(
      request("SOL", "PRO"),
      observed({effort: "EXTRA_HIGH"}),
    );
    const result = core.prepareModeEffortActionCandidate(
      actionRequest({requested_effort: "PRO"}),
      plan,
      1300,
    );
    assert.equal(result.status, "MODE_ACTION_READY");
    assert.equal(result.target_slider_value, 4);
    assert.equal(result.policy_admission_required, true);
    assert.equal(result.action_authorized, false);
  });

  test("already-selected mode yields no-change and no action", () => {
    const plan = core.planModeTransition(
      request("SOL", "EXTRA_HIGH"),
      observed({effort: "EXTRA_HIGH"}),
    );
    const result = core.prepareModeEffortActionCandidate(actionRequest(), plan, 1300);
    assert.equal(result.status, "MODE_ACTION_NO_CHANGE");
    assert.equal(result.action, null);
    assert.equal(result.target_slider_value, null);
    assert.equal(result.browser_mutation_performed, false);
  });

  for (const [name, overrides] of [
    ["expired", {expires_at_ms: 1200}],
    ["future", {issued_at_ms: 1400, expires_at_ms: 30000}],
    ["overlong", {expires_at_ms: 31001}],
  ]) {
    test(`action candidate refuses ${name} time window`, () => {
      const plan = core.planModeTransition(request(), observed());
      const result = core.prepareModeEffortActionCandidate(actionRequest(overrides), plan, 1300);
      assert.equal(result.status, "MODE_ACTION_WINDOW_INVALID");
      assert.equal(result.action_authorized, false);
    });
  }

  for (const [field, value] of [
    ["runtime_binding_id", `bind-wsx-${"1".repeat(47)}`],
    ["runtime_binding_generation", 0],
    ["runtime_binding_fingerprint", "x".repeat(64)],
    ["document_epoch", "a".repeat(31)],
    ["operation_key", "bad operation"],
    ["nonce", "short"],
  ]) {
    test(`action candidate refuses invalid exact identity/control field ${field}`, () => {
      const plan = core.planModeTransition(request(), observed());
      const result = core.prepareModeEffortActionCandidate(
        actionRequest({[field]: value}),
        plan,
        1300,
      );
      assert.equal(result.status, "MODE_ACTION_INVALID");
    });
  }

  test("action candidate request is closed to unknown fields", () => {
    const req = actionRequest();
    req.command = "CLICK";
    const plan = core.planModeTransition(request(), observed());
    const result = core.prepareModeEffortActionCandidate(req, plan, 1300);
    assert.equal(result.status, "MODE_ACTION_INVALID");
    assert.ok(!JSON.stringify(result).includes("CLICK"));
  });

  for (const [name, mutate] of [
    ["upstream authority", p => { p.action_authorized = true; }],
    ["upstream browser effect", p => { p.browser_mutation_performed = true; }],
    ["missing readback", p => { p.readback_required = false; }],
    ["missing reprobe", p => { p.capability_reprobe_required = false; }],
    ["selector digest", p => { p.selector_state_digest = "bad"; }],
    ["target value", p => { p.target_slider_value = 9; }],
    ["requested effort mismatch", p => { p.requested_effort = "PRO"; }],
  ]) {
    test(`action candidate refuses transition-plan tamper: ${name}`, () => {
      const plan = {...core.planModeTransition(request(), observed())};
      mutate(plan);
      const result = core.prepareModeEffortActionCandidate(actionRequest(), plan, 1300);
      assert.equal(result.status, "MODE_ACTION_TRANSITION_INVALID");
      assert.equal(result.action_authorized, false);
    });
  }

  test("non-ready transition remains non-actionable", () => {
    const plan = core.planModeTransition(
      request("LATEST", "EXTRA_HIGH"),
      observed({family: "SOL"}),
    );
    const result = core.prepareModeEffortActionCandidate(
      actionRequest({requested_family: "LATEST"}),
      plan,
      1300,
    );
    assert.equal(result.status, "MODE_ACTION_TRANSITION_NOT_READY");
    assert.equal(result.action, null);
  });

  test("candidate builder never mutates action request or transition plan", () => {
    const req = actionRequest();
    const plan = core.planModeTransition(request(), observed());
    const beforeReq = JSON.stringify(req);
    const beforePlan = JSON.stringify(plan);
    core.prepareModeEffortActionCandidate(req, plan, 1300);
    assert.equal(JSON.stringify(req), beforeReq);
    assert.equal(JSON.stringify(plan), beforePlan);
  });
}
