"use strict";

(() => {
  const RESULT_SCHEMA = "mastermind.executive_orchestration_result/v1";
  const MAX_CANONICAL_RESULT_BYTES = 49152;
  const ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
  const ROLES = new Set(["plan", "work", "review", "repair", "aggregation"]);
  const EXPECTED_KEYS = new Set([
    "job_id", "run_id", "worker_id", "role", "root_job_id",
  ]);
  const ENVELOPE_KEYS = new Set([
    "schema_version", "job_id", "run_id", "worker_id", "role", "status",
    "role_result", "summary", "current_state", "next_actions", "errors",
    "validations",
  ]);

  function exactKeys(value, expected) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return false;
    const keys = Object.keys(value);
    return keys.length === expected.size && keys.every((key) => expected.has(key));
  }

  function validId(value) {
    return typeof value === "string" && ID_RE.test(value);
  }

  function validExpected(expected) {
    return exactKeys(expected, EXPECTED_KEYS) &&
      validId(expected.job_id) && validId(expected.run_id) &&
      validId(expected.worker_id) && validId(expected.root_job_id) &&
      typeof expected.role === "string" && ROLES.has(expected.role);
  }

  function canonicalJson(value) {
    if (value === null) return "null";
    if (typeof value === "string") return JSON.stringify(value);
    if (typeof value === "boolean") return value ? "true" : "false";
    if (typeof value === "number") {
      if (!Number.isFinite(value) || !Number.isInteger(value)) return null;
      return String(value);
    }
    if (Array.isArray(value)) {
      const parts = [];
      for (const item of value) {
        const encoded = canonicalJson(item);
        if (encoded === null) return null;
        parts.push(encoded);
      }
      return `[${parts.join(",")}]`;
    }
    if (!value || typeof value !== "object") return null;
    const parts = [];
    for (const key of Object.keys(value).sort()) {
      const encoded = canonicalJson(value[key]);
      if (encoded === null) return null;
      parts.push(`${JSON.stringify(key)}:${encoded}`);
    }
    return `{${parts.join(",")}}`;
  }

  function closed(status, canonicalResultJson = null, byteLength = 0) {
    return Object.freeze({
      status,
      canonical_result_json: canonicalResultJson,
      canonical_result_byte_length: byteLength,
    });
  }

  function reduceCanonicalResultText(text, expected) {
    if (!validExpected(expected) || typeof text !== "string" || text.length === 0 ||
        text.startsWith("\ufeff")) return closed("RESULT_REFUSED");
    let bytes;
    try {
      bytes = new TextEncoder().encode(text);
    } catch (_error) {
      return closed("RESULT_REFUSED");
    }
    if (bytes.byteLength > MAX_CANONICAL_RESULT_BYTES) {
      return closed("RESULT_TOO_LARGE");
    }
    let value;
    try {
      value = JSON.parse(text);
    } catch (_error) {
      return closed("RESULT_REFUSED");
    }
    const canonical = canonicalJson(value);
    if (canonical === null || canonical !== text) return closed("RESULT_REFUSED");
    if (!exactKeys(value, ENVELOPE_KEYS) || value.schema_version !== RESULT_SCHEMA ||
        value.job_id !== expected.job_id || value.run_id !== expected.run_id ||
        value.worker_id !== expected.worker_id || value.role !== expected.role ||
        value.status !== "COMPLETED" || !Array.isArray(value.validations) ||
        value.validations.length !== 0 || !value.role_result ||
        typeof value.role_result !== "object" || Array.isArray(value.role_result) ||
        value.role_result.root_job_id !== expected.root_job_id) {
      return closed("RESULT_REFUSED");
    }
    return closed("RESULT_READY", text, bytes.byteLength);
  }

  globalThis.MMXWebSolCognitionResult = Object.freeze({
    MAX_CANONICAL_RESULT_BYTES,
    reduceCanonicalResultText,
  });
})();
