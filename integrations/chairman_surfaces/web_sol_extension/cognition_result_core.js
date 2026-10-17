"use strict";

(() => {
  const RESULT_SCHEMA = "mastermind.executive_orchestration_result/v1";
  const MAX_CANONICAL_RESULT_BYTES = 24 * 1024;
  const ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
  const DIGEST_RE = /^[0-9a-f]{64}$/;
  const EMAIL_RE = /\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b/;
  const MASTERMIND_ENV_RE = /\bMASTERMIND_[A-Z_]+\b/;
  const JWT_RE = /(^|[^0-9A-Za-z])eyJ[0-9A-Za-z+\/=_-]{4,}\.[0-9A-Za-z+\/=_-]{4,}(?:\.[0-9A-Za-z+\/=_-]*)?/;
  const PREFIXED_SECRET_RE = /(^|[^0-9A-Za-z])(?:sb_secret_|sb_publishable_|sbp_|sk-ant-|sk-|github_pat_|ghp_|gho_|ghs_)[0-9A-Za-z+\/=_-]{8,}/;
  const SECRET_MARKERS = ["PASSWORD", "TOKEN", "SECRET", "KEY", "PASS"];
  const ROLES = new Set(["work", "review"]);
  const EXPECTED_KEYS = new Set([
    "job_id", "run_id", "worker_id", "role", "root_job_id",
  ]);
  const ENVELOPE_KEYS = new Set([
    "schema_version", "job_id", "run_id", "worker_id", "role", "status",
    "role_result", "summary", "current_state", "next_actions", "errors",
    "validations",
  ]);
  const LINEAGE_KEYS = ["root_job_id", "plan_attempt_id", "plan_digest", "plan_step_id"];
  const ARTIFACT_KEYS = new Set(["path", "digest"]);
  const WORK_KEYS = new Set([
    "schema_version", ...LINEAGE_KEYS, "repair_round", "artifacts", "evidence_digests",
  ]);
  const REVIEW_KEYS = new Set([
    "schema_version", ...LINEAGE_KEYS, "reviewed_job_id", "reviewed_attempt_id",
    "reviewed_result_digest", "repair_round", "verdict", "evidence_digests", "findings",
  ]);
  const FINDING_KEYS = new Set(["code", "severity", "message", "evidence_digests"]);

  function exactKeys(value, expected) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return false;
    const keys = Object.keys(value);
    return keys.length === expected.size && keys.every((key) => expected.has(key));
  }

  function validId(value) {
    return typeof value === "string" && ID_RE.test(value);
  }

  function validDigest(value) {
    return typeof value === "string" && DIGEST_RE.test(value);
  }

  function isWellFormedUnicode(value) {
    for (let index = 0; index < value.length; index += 1) {
      const code = value.charCodeAt(index);
      if (code >= 0xd800 && code <= 0xdbff) {
        if (index + 1 >= value.length) return false;
        const next = value.charCodeAt(index + 1);
        if (next < 0xdc00 || next > 0xdfff) return false;
        index += 1;
      } else if (code >= 0xdc00 && code <= 0xdfff) {
        return false;
      }
    }
    return true;
  }

  function validText(value, maximum = 8192, nonempty = false) {
    return typeof value === "string" && isWellFormedUnicode(value) &&
      !value.includes("\0") && value.length <= maximum &&
      (!nonempty || (value.length > 0 && value.trim() === value));
  }

  function stringHasBrowserRedactionTrigger(value) {
    if (JWT_RE.test(value) || PREFIXED_SECRET_RE.test(value) ||
        EMAIL_RE.test(value) || MASTERMIND_ENV_RE.test(value)) return true;
    const upper = value.toUpperCase();
    const marked = SECRET_MARKERS.some((marker) => upper.includes(marker));
    return marked && (value.includes("=") || value.startsWith("sk-") || upper.includes("TOKEN"));
  }

  function containsBrowserRedactionTrigger(value) {
    if (typeof value === "string") return stringHasBrowserRedactionTrigger(value);
    if (Array.isArray(value)) return value.some((item) => containsBrowserRedactionTrigger(item));
    if (!value || typeof value !== "object") return false;
    return Object.entries(value).some(([key, item]) =>
      stringHasBrowserRedactionTrigger(key) || containsBrowserRedactionTrigger(item));
  }

  function validArray(value, maximum, validator, minimum = 0) {
    return Array.isArray(value) && value.length >= minimum && value.length <= maximum &&
      value.every((item, index) => validator(item, index));
  }

  function validStringArray(value, maximum = 64, validator = (item) => validText(item)) {
    return validArray(value, maximum, validator) && new Set(value).size === value.length;
  }

  function validExpected(expected) {
    return exactKeys(expected, EXPECTED_KEYS) &&
      validId(expected.job_id) && validId(expected.run_id) &&
      validId(expected.worker_id) && validId(expected.root_job_id) &&
      typeof expected.role === "string" && ROLES.has(expected.role);
  }

  function validLineage(value, expected) {
    return value.root_job_id === expected.root_job_id &&
      validId(value.plan_attempt_id) && validDigest(value.plan_digest) && validId(value.plan_step_id);
  }

  function validArtifacts(value) {
    return validArray(value, 64, (item) => exactKeys(item, ARTIFACT_KEYS) &&
      validText(item.path, 1024, true) && validDigest(item.digest));
  }

  function validEvidence(value) {
    return validStringArray(value, 64, validDigest);
  }

  function validWorkResult(value, expected) {
    return exactKeys(value, WORK_KEYS) &&
      value.schema_version === "mastermind.work_result/v1" &&
      validLineage(value, expected) &&
      Number.isInteger(value.repair_round) &&
      value.repair_round === 0 &&
      validArtifacts(value.artifacts) &&
      validEvidence(value.evidence_digests);
  }

  function validReviewResult(value, expected) {
    if (!exactKeys(value, REVIEW_KEYS) || value.schema_version !== "mastermind.review_result/v1" ||
        !validLineage(value, expected) || !validId(value.reviewed_job_id) ||
        !validId(value.reviewed_attempt_id) || !validDigest(value.reviewed_result_digest) ||
        !Number.isInteger(value.repair_round) || value.repair_round < 0 || value.repair_round > 2 ||
        !["approve", "reject"].includes(value.verdict) || !validEvidence(value.evidence_digests)) return false;
    return validArray(value.findings, 64, (item) => exactKeys(item, FINDING_KEYS) &&
      validId(item.code) && ["info", "warning", "blocking"].includes(item.severity) &&
      validText(item.message) && validEvidence(item.evidence_digests));
  }

  function validRoleResult(value, expected) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return false;
    if (expected.role === "work") return validWorkResult(value, expected);
    if (expected.role === "review") return validReviewResult(value, expected);
    return false;
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
        value.validations.length !== 0 || !validText(value.summary) ||
        !validText(value.current_state) || !validStringArray(value.next_actions, 16) ||
        !validStringArray(value.errors, 16) || !validRoleResult(value.role_result, expected) ||
        containsBrowserRedactionTrigger(value)) {
      return closed("RESULT_REFUSED");
    }
    return closed("RESULT_READY", text, bytes.byteLength);
  }

  globalThis.MMXWebSolCognitionResult = Object.freeze({
    MAX_CANONICAL_RESULT_BYTES,
    reduceCanonicalResultText,
  });
})();
