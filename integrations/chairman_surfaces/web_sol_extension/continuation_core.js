"use strict";

(() => {
  const ACTION_SCHEMA = "mastermind.web_sol_surface_action.v1";
  const DIRECTIVE_DIGEST = "cde0de54629786dcd6c0ee3b169558cf050de48b828a4da15cbd2d881c66afd9";
  const MESSAGE_KIND = "MMX_WEB_SOL_SUBMIT_CONTINUATION";
  const RESULT_SCHEMA = "mastermind.web_sol_continuation_submit_result.v1";
  const MAX_EFFECTS = 256;
  const START_OBSERVATION_ATTEMPTS = 10;
  const START_OBSERVATION_INTERVAL_MS = 200;
  const CORRELATION_KEYS = Object.freeze([
    "turn_id", "directive_digest", "session_alias", "runtime_binding_id",
    "runtime_binding_generation", "runtime_binding_fingerprint",
  ]);
  const REQUEST_KEYS = new Set([
    "schema", "binding_id", "conversation_fingerprint", "binding_fingerprint",
    "action", "operation_key", "issued_at", "expires_at", "nonce",
    ...CORRELATION_KEYS,
  ]);
  const RESULT_KEYS = new Set([
    "schema", "conversation_fingerprint", "effect", ...CORRELATION_KEYS,
  ]);
  const effects = [];

  function exactKeys(value, expected) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return false;
    const keys = Object.keys(value);
    return keys.length === expected.size && keys.every((key) => expected.has(key));
  }

  function isHex64(value) {
    return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
  }

  function validRequest(request) {
    if (!exactKeys(request, REQUEST_KEYS) || request.schema !== ACTION_SCHEMA) return false;
    if (request.action !== "SUBMIT_CONTINUATION") return false;
    if (!isHex64(request.conversation_fingerprint) || !isHex64(request.binding_fingerprint)) return false;
    if (typeof request.binding_id !== "string" ||
        !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(request.binding_id)) return false;
    if (typeof request.operation_key !== "string" || !request.operation_key ||
        request.operation_key.length > 256 || /\s/.test(request.operation_key)) return false;
    if (typeof request.nonce !== "string" || request.nonce.length < 16 ||
        request.nonce.length > 128 || /\s/.test(request.nonce)) return false;
    if (typeof request.turn_id !== "string" ||
        !/^[A-Za-z0-9][A-Za-z0-9._:/-]{2,255}$/.test(request.turn_id)) return false;
    if (typeof request.session_alias !== "string" ||
        !/^[A-Za-z0-9][A-Za-z0-9._:/-]{2,255}$/.test(request.session_alias)) return false;
    if (typeof request.runtime_binding_id !== "string" ||
        !/^bind-wsx-[0-9a-f]{48}$/.test(request.runtime_binding_id)) return false;
    if (!Number.isSafeInteger(request.runtime_binding_generation) ||
        request.runtime_binding_generation < 1) return false;
    return request.directive_digest === DIRECTIVE_DIGEST &&
      isHex64(request.runtime_binding_fingerprint) &&
      typeof request.issued_at === "string" && typeof request.expires_at === "string";
  }

  function validResult(value, request) {
    return exactKeys(value, RESULT_KEYS) && value.schema === RESULT_SCHEMA &&
      value.conversation_fingerprint === request.conversation_fingerprint &&
      value.turn_id === request.turn_id && value.directive_digest === request.directive_digest &&
      value.session_alias === request.session_alias &&
      value.runtime_binding_id === request.runtime_binding_id &&
      value.runtime_binding_generation === request.runtime_binding_generation &&
      value.runtime_binding_fingerprint === request.runtime_binding_fingerprint &&
      ["NOT_SUBMITTED", "SUBMIT_TRIGGERED", "SUBMIT_EFFECT_UNKNOWN"].includes(value.effect);
  }

  function result(status, observation) {
    return {status, observation};
  }

  async function handle(request, ops) {
    if (!validRequest(request) || !ops) {
      return result("CONTINUATION_SUBMIT_EFFECT_UNKNOWN", ops?.unknownObservation?.());
    }
    if (effects.some((row) => row.nonce === request.nonce || row.turn_id === request.turn_id) ||
        effects.length >= MAX_EFFECTS) {
      return result("CONTINUATION_NOT_SUBMITTED", ops.unknownObservation());
    }
    const resolved = ops.resolveExactTarget(request.conversation_fingerprint);
    if (resolved.status) return result("CONTINUATION_NOT_SUBMITTED", ops.unknownObservation());
    const before = await ops.freshProbe(resolved.tabId, request.conversation_fingerprint);
    if (!before || before.conversation_fingerprint !== request.conversation_fingerprint ||
        !before.observation.target_present || !before.observation.exact_conversation_loaded ||
        before.observation.auth_required === true || before.observation.composer_available !== true ||
        before.observation.generation_state !== "idle") {
      return result("CONTINUATION_NOT_SUBMITTED", before ? before.observation : ops.unknownObservation());
    }
    const current = ops.resolveExactTarget(request.conversation_fingerprint);
    if (current.status || current.tabId !== resolved.tabId || ops.requestWindowStatus(request)) {
      return result("CONTINUATION_NOT_SUBMITTED", before.observation);
    }

    effects.push({nonce: request.nonce, turn_id: request.turn_id});
    let submission;
    try {
      submission = await ops.sendMessage(resolved.tabId, {
        kind: MESSAGE_KIND,
        expected_conversation_fingerprint: request.conversation_fingerprint,
        turn_id: request.turn_id,
        directive_digest: request.directive_digest,
        session_alias: request.session_alias,
        runtime_binding_id: request.runtime_binding_id,
        runtime_binding_generation: request.runtime_binding_generation,
        runtime_binding_fingerprint: request.runtime_binding_fingerprint,
      });
    } catch (_error) {
      return result("CONTINUATION_SUBMIT_EFFECT_UNKNOWN", before.observation);
    }
    if (!validResult(submission, request)) {
      return result("CONTINUATION_SUBMIT_EFFECT_UNKNOWN", before.observation);
    }
    if (submission.effect === "NOT_SUBMITTED") {
      return result("CONTINUATION_NOT_SUBMITTED", before.observation);
    }
    if (submission.effect === "SUBMIT_EFFECT_UNKNOWN") {
      return result("CONTINUATION_SUBMIT_EFFECT_UNKNOWN", before.observation);
    }
    let after = null;
    for (let attempt = 0; attempt < START_OBSERVATION_ATTEMPTS; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, START_OBSERVATION_INTERVAL_MS));
      after = await ops.freshProbe(resolved.tabId, request.conversation_fingerprint);
      if (after && after.conversation_fingerprint === request.conversation_fingerprint &&
          after.observation.target_present && after.observation.exact_conversation_loaded &&
          after.observation.auth_required !== true && after.observation.generation_state === "active") {
        return result("CONTINUATION_STARTED", after.observation);
      }
      if (ops.requestWindowStatus(request)) break;
    }
    return result(
      "CONTINUATION_SUBMIT_EFFECT_UNKNOWN",
      after ? after.observation : before.observation,
    );
  }

  globalThis.MMXWebSolContinuation = Object.freeze({validRequest, handle, correlationKeys: CORRELATION_KEYS});
})();
