"use strict";

// Production-inert evidence reducer for the existing Web-Sol observation owner.
// It neither authenticates a producer nor grants admission. No stored identity,
// browser actuation, provider call, clock, retry or capability registry lives here.
(() => {
  const SCHEMA = "mastermind.web_sol_mode_readback/v1";
  const MAX_EVIDENCE_LIFETIME_MS = 30000;
  const DIGEST_RE = /^[0-9a-f]{64}$/;
  const BINDING_RE = /^bind-wsx-[0-9a-f]{48}$/;
  const DOCUMENT_EPOCH_RE = /^[0-9a-f]{32}$/;
  const TARGET_KEYS = [
    "runtime_binding_id", "runtime_binding_generation",
    "runtime_binding_fingerprint", "document_epoch",
  ];
  const REQUEST_KEYS = new Set([
    ...TARGET_KEYS, "requested_family", "requested_effort", "not_before_ms", "expires_at_ms",
  ]);
  const OBSERVATION_KEYS = new Set([
    ...TARGET_KEYS, "observed_at_ms", "selected_family", "selected_effort",
    "family_selection_count", "effort_control_count", "controls_enabled",
    "page_ready", "composer_ready", "generation_state", "auth_state", "selector_evidence_digest",
  ]);
  const FAMILIES = new Set(["SOL", "LATEST"]);
  const EFFORTS = new Set(["EXTRA_HIGH", "PRO"]);
  const OBSERVED_FAMILIES = new Set([...FAMILIES, "UNKNOWN"]);
  const OBSERVED_EFFORTS = new Set([...EFFORTS, "OTHER", "UNKNOWN"]);
  const GENERATION_STATES = new Set(["IDLE", "ACTIVE", "UNKNOWN"]);
  const AUTH_STATES = new Set(["AUTHENTICATED", "AUTH_REQUIRED", "UNKNOWN"]);

  // Accept JSON-derived own data properties only. Copy before any await so that
  // a caller cannot change the input between integrity verification and use.
  function snapshot(value, keys) {
    try {
      if (!value || typeof value !== "object" || Array.isArray(value)) return null;
      const prototype = Object.getPrototypeOf(value);
      if (prototype !== null && Object.getPrototypeOf(prototype) !== null) return null;
      const names = Reflect.ownKeys(value);
      if (names.length !== keys.size || !names.every(key => typeof key === "string" && keys.has(key))) return null;
      const descriptors = Object.getOwnPropertyDescriptors(value);
      const result = Object.create(null);
      for (const key of names) {
        const descriptor = descriptors[key];
        if (!descriptor || !Object.hasOwn(descriptor, "value") || !descriptor.enumerable) return null;
        result[key] = descriptor.value;
      }
      return Object.freeze(result);
    } catch (_error) {
      return null;
    }
  }

  function snapshotObservations(value) {
    try {
      if (!Array.isArray(value)) return null;
      const names = Reflect.ownKeys(value);
      if (names.length !== 3 || !names.every(key => key === "0" || key === "1" || key === "length")) return null;
      const descriptors = Object.getOwnPropertyDescriptors(value);
      if (descriptors.length?.value !== 2) return null;
      const pair = [];
      for (const index of ["0", "1"]) {
        const descriptor = descriptors[index];
        if (!descriptor || !Object.hasOwn(descriptor, "value") || !descriptor.enumerable) return null;
        pair.push(snapshot(descriptor.value, OBSERVATION_KEYS));
      }
      return Object.freeze(pair);
    } catch (_error) {
      return null;
    }
  }

  function matches(pattern, value) {
    return typeof value === "string" && pattern.test(value);
  }
  function positiveInteger(value) {
    return Number.isSafeInteger(value) && value > 0;
  }
  function count(value) {
    return Number.isSafeInteger(value) && value >= 0 && value <= 8;
  }
  function validTarget(value) {
    return matches(BINDING_RE, value.runtime_binding_id) &&
      positiveInteger(value.runtime_binding_generation) &&
      matches(DIGEST_RE, value.runtime_binding_fingerprint) &&
      matches(DOCUMENT_EPOCH_RE, value.document_epoch);
  }
  function validRequest(value) {
    return value && validTarget(value) && FAMILIES.has(value.requested_family) &&
      EFFORTS.has(value.requested_effort) && positiveInteger(value.not_before_ms) &&
      positiveInteger(value.expires_at_ms) && value.expires_at_ms > value.not_before_ms &&
      value.expires_at_ms - value.not_before_ms <= MAX_EVIDENCE_LIFETIME_MS;
  }
  function validObservation(value) {
    return value && validTarget(value) && positiveInteger(value.observed_at_ms) &&
      OBSERVED_FAMILIES.has(value.selected_family) && OBSERVED_EFFORTS.has(value.selected_effort) &&
      count(value.family_selection_count) && count(value.effort_control_count) &&
      typeof value.controls_enabled === "boolean" && typeof value.page_ready === "boolean" &&
      typeof value.composer_ready === "boolean" && GENERATION_STATES.has(value.generation_state) &&
      AUTH_STATES.has(value.auth_state) && matches(DIGEST_RE, value.selector_evidence_digest);
  }

  async function observationDigest(value) {
    try {
      if (typeof globalThis.crypto?.subtle?.digest !== "function" || typeof TextEncoder !== "function") return null;
      const keys = Object.keys(value).filter(key => key !== "selector_evidence_digest").sort();
      const bytes = new TextEncoder().encode(JSON.stringify(value, keys));
      const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
      return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
    } catch (_error) {
      return null;
    }
  }

  function result(status, request = null, observations = null) {
    const matched = status === "MODE_READBACK_MATCH";
    const target = matched
      ? Object.freeze(Object.fromEntries(TARGET_KEYS.map(key => [key, request[key]]))) : null;
    return Object.freeze({
      schema: SCHEMA, status, target,
      observed_at_ms: matched ? observations[1].observed_at_ms : null,
      expires_at_ms: matched ? request.expires_at_ms : null,
      selected_model: matched ? observations[1].selected_family : null,
      selected_effort: matched ? observations[1].selected_effort : null,
      served_model: null,
      model_evidence: Object.freeze(matched ? observations.map(value => value.selector_evidence_digest) : []),
      action_authorized: false,
      capability_reprobe_required: true,
    });
  }

  /**
   * Qualify two authenticated-owner observations after an exact mode barrier.
   * MODE_READBACK_MATCH attests only consistency/integrity of supplied evidence.
   * Producer authentication, effect reconciliation and action admission remain
   * mandatory outside this helper, as does a current post-mode capability probe.
   */
  async function qualifyModeReadback(rawRequest, rawObservations, nowMs) {
    const request = snapshot(rawRequest, REQUEST_KEYS);
    const observations = snapshotObservations(rawObservations);
    if (!validRequest(request) || !positiveInteger(nowMs) ||
        !observations || !observations.every(validObservation)) {
      return result("MODE_OBSERVATION_INVALID");
    }
    if (!observations.every(value => TARGET_KEYS.every(key => value[key] === request[key]))) {
      return result("MODE_IDENTITY_MISMATCH");
    }
    if (nowMs > request.expires_at_ms || observations[0].observed_at_ms <= request.not_before_ms ||
        observations[1].observed_at_ms <= observations[0].observed_at_ms ||
        observations.some(value => value.observed_at_ms > nowMs)) {
      return result("MODE_EVIDENCE_STALE");
    }
    for (const observation of observations) {
      if (await observationDigest(observation) !== observation.selector_evidence_digest) {
        return result("MODE_EVIDENCE_UNVERIFIED");
      }
    }
    if (!observations.every(value => value.page_ready && value.composer_ready &&
        value.generation_state === "IDLE" && value.auth_state === "AUTHENTICATED")) {
      return result("MODE_SURFACE_BLOCKED");
    }
    if (!observations.every(value => value.controls_enabled &&
        value.family_selection_count === 1 && value.effort_control_count === 1)) {
      return result("MODE_SELECTOR_UNAVAILABLE");
    }
    if (!observations.every(value => value.selected_family === request.requested_family &&
        value.selected_effort === request.requested_effort)) {
      return result("MODE_READBACK_MISMATCH");
    }
    return result("MODE_READBACK_MATCH", request, observations);
  }

  const api = Object.freeze({ SCHEMA, MAX_EVIDENCE_LIFETIME_MS, qualifyModeReadback });
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else globalThis.MMXWebSolModeReadbackCore = api;
})();
