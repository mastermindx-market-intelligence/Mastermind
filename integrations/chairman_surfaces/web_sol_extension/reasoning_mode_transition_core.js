"use strict";

(() => {
  const SCHEMA = "mastermind.web_sol_mode_transition_plan/v1";
  const ACTION_REQUEST_SCHEMA = "mastermind.web_sol_mode_effort_action_request/v1";
  const ACTION_CANDIDATE_SCHEMA = "mastermind.web_sol_mode_effort_action_candidate/v1";
  const PICKER_SCHEMA = "mastermind.web_sol_mode_picker_observation/v1";
  const DIGEST_RE = /^[0-9a-f]{64}$/;
  const BINDING_RE = /^bind-wsx-[0-9a-f]{48}$/;
  const DOCUMENT_EPOCH_RE = /^[0-9a-f]{32}$/;
  const CONTROL_TOKEN_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{2,255}$/;
  const NONCE_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$/;
  const MAX_ACTION_WINDOW_MS = 30000;
  const REQUEST_KEYS = new Set(["requested_family", "requested_effort"]);
  const ACTION_REQUEST_KEYS = new Set([
    "schema", "runtime_binding_id", "runtime_binding_generation",
    "runtime_binding_fingerprint", "document_epoch", "operation_key", "nonce",
    "issued_at_ms", "expires_at_ms", "requested_family", "requested_effort",
  ]);
  const TRANSITION_PLAN_KEYS = new Set([
    "schema", "status", "current_family", "current_effort", "requested_family",
    "requested_effort", "selector_state_digest", "transition_kind",
    "target_slider_value", "policy_admission_required", "action_authorized",
    "browser_mutation_performed", "readback_required",
    "capability_reprobe_required", "served_model",
  ]);
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

  const TRANSITION_STATUSES = new Set([
    "MODE_TRANSITION_INVALID",
    "MODE_TRANSITION_UNAVAILABLE",
    "MODE_FAMILY_CHANGE_UNSUPPORTED",
    "MODE_TRANSITION_DISABLED",
    "MODE_TRANSITION_NO_CHANGE",
    "MODE_TARGET_UNAVAILABLE",
    "MODE_TRANSITION_READY",
  ]);

  function validActionIdentityRequest(value) {
    return value &&
      value.schema === ACTION_REQUEST_SCHEMA &&
      typeof value.runtime_binding_id === "string" &&
      BINDING_RE.test(value.runtime_binding_id) &&
      safeInteger(value.runtime_binding_generation) &&
      value.runtime_binding_generation > 0 &&
      typeof value.runtime_binding_fingerprint === "string" &&
      DIGEST_RE.test(value.runtime_binding_fingerprint) &&
      typeof value.document_epoch === "string" &&
      DOCUMENT_EPOCH_RE.test(value.document_epoch) &&
      typeof value.operation_key === "string" &&
      CONTROL_TOKEN_RE.test(value.operation_key) &&
      typeof value.nonce === "string" &&
      NONCE_RE.test(value.nonce) &&
      FAMILIES.has(value.requested_family) &&
      TARGET_EFFORTS.has(value.requested_effort);
  }

  function validActionWindow(value, nowMs) {
    return safeInteger(nowMs) && nowMs > 0 &&
      safeInteger(value.issued_at_ms) && value.issued_at_ms > 0 &&
      safeInteger(value.expires_at_ms) &&
      value.expires_at_ms > value.issued_at_ms &&
      value.expires_at_ms - value.issued_at_ms <= MAX_ACTION_WINDOW_MS &&
      value.issued_at_ms <= nowMs && nowMs < value.expires_at_ms;
  }

  function normalizeTransitionPlan(raw) {
    const value = snapshot(raw, TRANSITION_PLAN_KEYS);
    if (!value || value.schema !== SCHEMA || !TRANSITION_STATUSES.has(value.status) ||
        value.action_authorized !== false ||
        value.browser_mutation_performed !== false ||
        value.readback_required !== true ||
        value.capability_reprobe_required !== true ||
        value.served_model !== null) {
      return null;
    }

    if (value.status !== "MODE_TRANSITION_READY" &&
        value.status !== "MODE_TRANSITION_NO_CHANGE") {
      return value;
    }

    if (!FAMILIES.has(value.current_family) ||
        !FAMILIES.has(value.requested_family) ||
        value.current_family !== value.requested_family ||
        !OBSERVED_EFFORTS.has(value.current_effort) ||
        !TARGET_EFFORTS.has(value.requested_effort) ||
        typeof value.selector_state_digest !== "string" ||
        !DIGEST_RE.test(value.selector_state_digest) ||
        typeof value.policy_admission_required !== "boolean" ||
        value.policy_admission_required !== (value.requested_effort === "PRO")) {
      return null;
    }

    if (value.status === "MODE_TRANSITION_NO_CHANGE") {
      if (value.current_effort !== value.requested_effort ||
          value.transition_kind !== "NONE" ||
          value.target_slider_value !== null) {
        return null;
      }
      return value;
    }

    if (value.current_effort === value.requested_effort ||
        value.transition_kind !== "SET_EFFORT_VALUE" ||
        !safeInteger(value.target_slider_value) ||
        value.target_slider_value < 0 || value.target_slider_value > 8) {
      return null;
    }
    return value;
  }

  function renderActionCandidate(status, request = null, plan = null) {
    const bound = request !== null &&
      (status === "MODE_ACTION_READY" || status === "MODE_ACTION_NO_CHANGE");
    const ready = status === "MODE_ACTION_READY";
    const target = bound ? Object.freeze({
      runtime_binding_id: request.runtime_binding_id,
      runtime_binding_generation: request.runtime_binding_generation,
      runtime_binding_fingerprint: request.runtime_binding_fingerprint,
      document_epoch: request.document_epoch,
    }) : null;
    return Object.freeze({
      schema: ACTION_CANDIDATE_SCHEMA,
      status,
      action: ready ? "SET_REASONING_EFFORT" : null,
      target,
      operation_key: bound ? request.operation_key : null,
      nonce: bound ? request.nonce : null,
      issued_at_ms: bound ? request.issued_at_ms : null,
      expires_at_ms: bound ? request.expires_at_ms : null,
      requested_family: bound ? request.requested_family : null,
      requested_effort: bound ? request.requested_effort : null,
      selector_state_digest: bound ? plan.selector_state_digest : null,
      target_slider_value: ready ? plan.target_slider_value : null,
      policy_admission_required: bound ? plan.policy_admission_required : null,
      action_authorized: false,
      browser_mutation_performed: false,
      post_action_readback_required: true,
      capability_reprobe_required: true,
      exact_owner_admission_required: true,
      served_model: null,
    });
  }

  function prepareModeEffortActionCandidate(rawRequest, rawTransitionPlan, nowMs) {
    const request = snapshot(rawRequest, ACTION_REQUEST_KEYS);
    if (!validActionIdentityRequest(request)) {
      return renderActionCandidate("MODE_ACTION_INVALID");
    }
    if (!validActionWindow(request, nowMs)) {
      return renderActionCandidate("MODE_ACTION_WINDOW_INVALID");
    }

    const plan = normalizeTransitionPlan(rawTransitionPlan);
    if (!plan) {
      return renderActionCandidate("MODE_ACTION_TRANSITION_INVALID");
    }
    if (plan.status !== "MODE_TRANSITION_READY" &&
        plan.status !== "MODE_TRANSITION_NO_CHANGE") {
      return renderActionCandidate("MODE_ACTION_TRANSITION_NOT_READY");
    }
    if (plan.requested_family !== request.requested_family ||
        plan.requested_effort !== request.requested_effort) {
      return renderActionCandidate("MODE_ACTION_TRANSITION_INVALID");
    }
    if (plan.status === "MODE_TRANSITION_NO_CHANGE") {
      return renderActionCandidate("MODE_ACTION_NO_CHANGE", request, plan);
    }
    return renderActionCandidate("MODE_ACTION_READY", request, plan);
  }

  const api = Object.freeze({
    SCHEMA,
    ACTION_CANDIDATE_SCHEMA,
    MAX_ACTION_WINDOW_MS,
    planModeTransition,
    prepareModeEffortActionCandidate,
  });
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else globalThis.MMXWebSolModeTransitionCore = api;
})();
