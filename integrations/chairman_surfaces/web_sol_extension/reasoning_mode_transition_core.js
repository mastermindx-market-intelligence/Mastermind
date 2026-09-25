"use strict";

(() => {
  const SCHEMA = "mastermind.web_sol_mode_transition_plan/v1";
  const PICKER_SCHEMA = "mastermind.web_sol_mode_picker_observation/v1";
  const DIGEST_RE = /^[0-9a-f]{64}$/;
  const REQUEST_KEYS = new Set(["requested_family", "requested_effort"]);
  const OBSERVATION_KEYS = new Set([
    "schema", "status", "selected_family", "selected_effort",
    "family_selection_count", "effort_control_count", "controls_enabled",
    "slider", "selector_state_digest", "served_model", "action_authorized",
  ]);
  const SLIDER_KEYS = new Set(["min", "max", "value"]);
  const FAMILIES = new Set(["SOL", "LATEST"]);
  const TARGET_EFFORTS = new Set(["EXTRA_HIGH", "PRO"]);
  const OBSERVED_EFFORTS = new Set(["INSTANT", "MEDIUM", "HIGH", "EXTRA_HIGH", "PRO"]);
  const PICKER_STATUSES = new Set([
    "MODE_PICKER_OBSERVED",
    "MODE_PICKER_UNAVAILABLE",
    "MODE_PICKER_AMBIGUOUS",
    "MODE_PICKER_INVALID",
    "MODE_PICKER_UNSUPPORTED",
    "MODE_PICKER_EVIDENCE_UNVERIFIED",
  ]);
  const EFFORT_INDEX = Object.freeze({
    INSTANT: 0,
    MEDIUM: 1,
    HIGH: 2,
    EXTRA_HIGH: 3,
    PRO: 4,
  });

  function snapshot(value, keys) {
    try {
      if (!value || typeof value !== "object" || Array.isArray(value)) return null;
      const prototype = Object.getPrototypeOf(value);
      if (prototype !== null && Object.getPrototypeOf(prototype) !== null) return null;
      const names = Reflect.ownKeys(value);
      if (names.length !== keys.size ||
          !names.every(key => typeof key === "string" && keys.has(key))) return null;
      const descriptors = Object.getOwnPropertyDescriptors(value);
      const out = Object.create(null);
      for (const key of names) {
        const descriptor = descriptors[key];
        if (!descriptor || !Object.hasOwn(descriptor, "value") || !descriptor.enumerable) return null;
        out[key] = descriptor.value;
      }
      return Object.freeze(out);
    } catch (_error) {
      return null;
    }
  }

  function safeInteger(value) {
    return Number.isSafeInteger(value);
  }

  function count(value) {
    return safeInteger(value) && value >= 0 && value <= 8;
  }

  function snapshotSlider(value) {
    const slider = snapshot(value, SLIDER_KEYS);
    if (!slider || !safeInteger(slider.min) || !safeInteger(slider.max) || !safeInteger(slider.value)) {
      return null;
    }
    const optionCount = slider.max - slider.min + 1;
    if (optionCount < 1 || optionCount > 5 || slider.value < slider.min || slider.value > slider.max) {
      return null;
    }
    return slider;
  }

  function validRequest(value) {
    return value && FAMILIES.has(value.requested_family) && TARGET_EFFORTS.has(value.requested_effort);
  }

  function normalizeObservation(raw) {
    const value = snapshot(raw, OBSERVATION_KEYS);
    if (!value || value.schema !== PICKER_SCHEMA || !PICKER_STATUSES.has(value.status) ||
        !count(value.family_selection_count) || !count(value.effort_control_count) ||
        typeof value.controls_enabled !== "boolean" ||
        value.served_model !== null || value.action_authorized !== false) {
      return null;
    }

    if (value.status !== "MODE_PICKER_OBSERVED") {
      if (value.selected_family !== null || value.selected_effort !== null ||
          value.slider !== null || value.selector_state_digest !== null) {
        return null;
      }
      return Object.freeze({...value, slider: null});
    }

    if (!FAMILIES.has(value.selected_family) || !OBSERVED_EFFORTS.has(value.selected_effort) ||
        value.family_selection_count !== 1 || value.effort_control_count !== 1 ||
        typeof value.selector_state_digest !== "string" ||
        !DIGEST_RE.test(value.selector_state_digest)) {
      return null;
    }
    const slider = snapshotSlider(value.slider);
    if (!slider) return null;
    const expectedCurrent = slider.min + EFFORT_INDEX[value.selected_effort];
    if (expectedCurrent > slider.max || slider.value !== expectedCurrent) return null;
    return Object.freeze({...value, slider});
  }

  function render(status, request = null, observation = null, transitionKind = "NONE", targetValue = null) {
    const current = observation?.status === "MODE_PICKER_OBSERVED" ? observation : null;
    return Object.freeze({
      schema: SCHEMA,
      status,
      current_family: current?.selected_family ?? null,
      current_effort: current?.selected_effort ?? null,
      requested_family: request?.requested_family ?? null,
      requested_effort: request?.requested_effort ?? null,
      selector_state_digest: current?.selector_state_digest ?? null,
      transition_kind: transitionKind,
      target_slider_value: targetValue,
      policy_admission_required: request ? request.requested_effort === "PRO" : null,
      action_authorized: false,
      browser_mutation_performed: false,
      readback_required: true,
      capability_reprobe_required: true,
      served_model: null,
    });
  }

  function planModeTransition(rawRequest, rawObservation) {
    const request = snapshot(rawRequest, REQUEST_KEYS);
    const observation = normalizeObservation(rawObservation);
    if (!validRequest(request) || !observation) {
      return render("MODE_TRANSITION_INVALID");
    }
    if (observation.status !== "MODE_PICKER_OBSERVED") {
      return render("MODE_TRANSITION_UNAVAILABLE", request);
    }
    if (observation.selected_family !== request.requested_family) {
      return render("MODE_FAMILY_CHANGE_UNSUPPORTED", request, observation);
    }
    if (!observation.controls_enabled) {
      return render("MODE_TRANSITION_DISABLED", request, observation);
    }
    if (observation.selected_effort === request.requested_effort) {
      return render("MODE_TRANSITION_NO_CHANGE", request, observation);
    }
    const targetValue = observation.slider.min + EFFORT_INDEX[request.requested_effort];
    if (targetValue > observation.slider.max) {
      return render("MODE_TARGET_UNAVAILABLE", request, observation);
    }
    return render("MODE_TRANSITION_READY", request, observation, "SET_EFFORT_VALUE", targetValue);
  }

  const api = Object.freeze({SCHEMA, planModeTransition});
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else globalThis.MMXWebSolModeTransitionCore = api;
})();
