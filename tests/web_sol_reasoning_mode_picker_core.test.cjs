"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const corePath = path.join(
  __dirname,
  "../integrations/chairman_surfaces/web_sol_extension/reasoning_mode_picker_core.js",
);
let core;
if (fs.existsSync(corePath)) core = require(corePath);

test("mode picker core is available", () => {
  assert.equal(typeof core?.observeOpenModePicker, "function");
});

class FakeElement {
  constructor({attrs = {}, text = "", selectors = {}, closest = {}, visible = true, hidden = false} = {}) {
    this._attrs = {...attrs};
    this.textContent = text;
    this._selectors = selectors;
    this._closest = closest;
    this._visible = visible;
    this.hidden = hidden;
  }
  getAttribute(name) {
    return Object.prototype.hasOwnProperty.call(this._attrs, name) ? this._attrs[name] : null;
  }
  hasAttribute(name) {
    return Object.prototype.hasOwnProperty.call(this._attrs, name);
  }
  querySelectorAll(selector) {
    return this._selectors[selector] ? [...this._selectors[selector]] : [];
  }
  closest(selector) {
    return this._closest[selector] ?? null;
  }
  getClientRects() {
    return this._visible ? [{x: 0, y: 0, width: 1, height: 1}] : [];
  }
}

class FakeDocument {
  constructor({containers = [], ids = {}} = {}) {
    this._containers = containers;
    this._ids = ids;
  }
  querySelectorAll(selector) {
    if (selector === "[data-model-reasoning-effort-slider], [data-model-picker-power-slider]") {
      return [...this._containers];
    }
    return [];
  }
  getElementById(id) {
    return this._ids[id] ?? null;
  }
}

function pickerFixture({
  family = "SOL",
  effort = "EXTRA_HIGH",
  sliderMin = 0,
  sliderMax = 4,
  sliderValue = effort === "PRO" ? 4 : effort === "EXTRA_HIGH" ? 3 : effort === "HIGH" ? 2 : effort === "MEDIUM" ? 1 : 0,
  enabled = true,
  visible = true,
  extraContainers = [],
  descriptionText = null,
  checkedRadios = null,
} = {}) {
  const labelByEffort = {
    INSTANT: "Instant",
    MEDIUM: "Medium",
    HIGH: "High",
    EXTRA_HIGH: "Extra High",
    PRO: "Pro",
  };
  const familyText = family === "SOL" ? "GPT-5.6 Sol" : "Latest";
  const desc = new FakeElement({text: descriptionText ?? `${familyText} ${labelByEffort[effort] ?? effort}`});
  const modeItem = new FakeElement({attrs: {"aria-describedby": "mode-desc"}});
  const slider = new FakeElement({
    attrs: {
      role: "slider",
      "aria-valuemin": String(sliderMin),
      "aria-valuemax": String(sliderMax),
      "aria-valuenow": String(sliderValue),
      "aria-disabled": enabled ? "false" : "true",
    },
    closest: {"[role='menuitem']": modeItem},
  });
  const radios = checkedRadios ?? [
    new FakeElement({attrs: {role: "menuitemradio", "aria-checked": family === "SOL" ? "true" : "false"}, text: "GPT-5.6 Sol"}),
    new FakeElement({attrs: {role: "menuitemradio", "aria-checked": family === "LATEST" ? "true" : "false"}, text: "Latest"}),
  ];
  const picker = new FakeElement({selectors: {"[role='menuitemradio']": radios}});
  const container = new FakeElement({
    attrs: {"data-model-picker-power-slider": ""},
    selectors: {"[role='slider']": [slider]},
    closest: {
      "[data-testid='composer-intelligence-picker-content'], [role='menu'], [role='group']": picker,
    },
    visible,
  });
  return {
    document: new FakeDocument({containers: [container, ...extraContainers], ids: {"mode-desc": desc}}),
    container,
    picker,
    slider,
    desc,
  };
}

if (core) {
  test("observes one open Sol Extra High picker without granting action authority", async () => {
    const {document} = pickerFixture();
    const result = await core.observeOpenModePicker(document);
    assert.equal(result.status, "MODE_PICKER_OBSERVED");
    assert.equal(result.selected_family, "SOL");
    assert.equal(result.selected_effort, "EXTRA_HIGH");
    assert.equal(result.family_selection_count, 1);
    assert.equal(result.effort_control_count, 1);
    assert.equal(result.controls_enabled, true);
    assert.deepEqual(result.slider, {min: 0, max: 4, value: 3});
    assert.match(result.selector_state_digest, /^[0-9a-f]{64}$/);
    assert.equal(result.action_authorized, false);
    assert.equal(result.served_model, null);
    assert.ok(Object.isFrozen(result));
    assert.ok(Object.isFrozen(result.slider));
  });

  test("observes Latest Pro only when description and slider index agree", async () => {
    const {document} = pickerFixture({family: "LATEST", effort: "PRO"});
    const result = await core.observeOpenModePicker(document);
    assert.equal(result.status, "MODE_PICKER_OBSERVED");
    assert.equal(result.selected_family, "LATEST");
    assert.equal(result.selected_effort, "PRO");
    assert.deepEqual(result.slider, {min: 0, max: 4, value: 4});
  });

  test("no visible picker is unavailable", async () => {
    const result = await core.observeOpenModePicker(new FakeDocument());
    assert.equal(result.status, "MODE_PICKER_UNAVAILABLE");
    assert.equal(result.selector_state_digest, null);
  });

  test("a hidden stale picker is ignored when one visible picker remains", async () => {
    const hidden = pickerFixture({visible: false}).container;
    const {document} = pickerFixture({extraContainers: [hidden]});
    const result = await core.observeOpenModePicker(document);
    assert.equal(result.status, "MODE_PICKER_OBSERVED");
    assert.equal(result.effort_control_count, 1);
  });

  test("two visible slider containers fail ambiguous", async () => {
    const second = pickerFixture().container;
    const {document} = pickerFixture({extraContainers: [second]});
    const result = await core.observeOpenModePicker(document);
    assert.equal(result.status, "MODE_PICKER_AMBIGUOUS");
  });

  test("two checked family rows fail ambiguous", async () => {
    const radios = [
      new FakeElement({attrs: {role: "menuitemradio", "aria-checked": "true"}, text: "GPT-5.6 Sol"}),
      new FakeElement({attrs: {role: "menuitemradio", "aria-checked": "true"}, text: "Latest"}),
    ];
    const {document} = pickerFixture({checkedRadios: radios});
    const result = await core.observeOpenModePicker(document);
    assert.equal(result.status, "MODE_PICKER_AMBIGUOUS");
  });

  test("one unrecognized checked family fails unsupported without echoing its label", async () => {
    const secretLabel = "Some Future Model private-label";
    const radios = [
      new FakeElement({attrs: {role: "menuitemradio", "aria-checked": "true"}, text: secretLabel}),
    ];
    const {document} = pickerFixture({checkedRadios: radios});
    const result = await core.observeOpenModePicker(document);
    assert.equal(result.status, "MODE_PICKER_UNSUPPORTED");
    assert.ok(!JSON.stringify(result).includes(secretLabel));
  });

  test("disabled selector is observed but never action-authorized", async () => {
    const {document} = pickerFixture({enabled: false});
    const result = await core.observeOpenModePicker(document);
    assert.equal(result.status, "MODE_PICKER_OBSERVED");
    assert.equal(result.controls_enabled, false);
    assert.equal(result.action_authorized, false);
  });

  for (const [name, opts] of [
    ["non-integer minimum", {sliderMin: "x"}],
    ["value below range", {sliderValue: -1}],
    ["value above range", {sliderValue: 5}],
    ["more than five positions", {sliderMax: 5}],
  ]) {
    test(`invalid ARIA range fails closed: ${name}`, async () => {
      const {document} = pickerFixture(opts);
      const result = await core.observeOpenModePicker(document);
      assert.equal(result.status, "MODE_PICKER_INVALID");
    });
  }

  test("effort label and slider position disagreement fails invalid", async () => {
    const {document} = pickerFixture({effort: "HIGH", sliderValue: 3});
    const result = await core.observeOpenModePicker(document);
    assert.equal(result.status, "MODE_PICKER_INVALID");
  });

  test("unsupported effort description fails closed without guessing", async () => {
    const raw = "GPT-5.6 Sol Hyper Think";
    const {document} = pickerFixture({descriptionText: raw});
    const result = await core.observeOpenModePicker(document);
    assert.equal(result.status, "MODE_PICKER_UNSUPPORTED");
    assert.ok(!JSON.stringify(result).includes(raw));
  });

  test("missing description reference fails invalid", async () => {
    const f = pickerFixture();
    f.slider._closest["[role='menuitem']"]._attrs["aria-describedby"] = "missing";
    const result = await core.observeOpenModePicker(f.document);
    assert.equal(result.status, "MODE_PICKER_INVALID");
  });

  test("duplicate description ids fail invalid", async () => {
    const f = pickerFixture();
    f.slider._closest["[role='menuitem']"]._attrs["aria-describedby"] = "mode-desc mode-desc";
    const result = await core.observeOpenModePicker(f.document);
    assert.equal(result.status, "MODE_PICKER_INVALID");
  });

  test("normalized selector digest is deterministic", async () => {
    const one = await core.observeOpenModePicker(pickerFixture().document);
    const two = await core.observeOpenModePicker(pickerFixture().document);
    assert.equal(one.selector_state_digest, two.selector_state_digest);
  });

  test("observer source contains no browser mutation or transport primitive", () => {
    const source = fs.readFileSync(corePath, "utf8");
    assert.doesNotMatch(source, /\.click\s*\(/);
    assert.doesNotMatch(source, /dispatchEvent\s*\(/);
    assert.doesNotMatch(source, /\.focus\s*\(/);
    assert.doesNotMatch(source, /\b(?:KeyboardEvent|MouseEvent|PointerEvent)\b/);
    assert.doesNotMatch(source, /\b(?:fetch|XMLHttpRequest|setTimeout|setInterval)\s*\(/);
    assert.doesNotMatch(source, /\b(?:localStorage|sessionStorage)\b/);
  });
}
