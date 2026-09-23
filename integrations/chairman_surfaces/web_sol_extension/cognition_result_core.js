"use strict";

(() => {
  const RESULT_SCHEMA = "mastermind.executive_orchestration_result/v1";
  const MAX_CANONICAL_RESULT_BYTES = 49152;
  const ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
  const DIGEST_RE = /^[0-9a-f]{64}$/;
  const AUTHORITY_RE = /^[A-Z][A-Z0-9_]{1,31}$/;
  const ROLES = new Set(["plan", "work", "review", "repair", "aggregation"]);
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
  const REPAIR_KEYS = new Set([
    ...WORK_KEYS, "supersedes_job_id", "rejected_review_job_id", "rejected_review_result_digest",
  ]);
  const REVIEW_KEYS = new Set([
    "schema_version", ...LINEAGE_KEYS, "reviewed_job_id", "reviewed_attempt_id",
    "reviewed_result_digest", "repair_round", "verdict", "evidence_digests", "findings",
  ]);
  const FINDING_KEYS = new Set(["code", "severity", "message", "evidence_digests"]);
  const PLAN_KEYS = new Set(["schema_version", "root_job_id", "plan_attempt_id", "steps"]);
  const PLAN_STEP_V1_KEYS = new Set([
    "ordinal", "step_id", "objective", "business_impact", "review_required",
    "requested_authorities", "allowed_write_paths", "validation_ids", "attempt_limit", "cost_class",
  ]);
  const PLAN_STEP_V2_KEYS = new Set([...PLAN_STEP_V1_KEYS, "placement"]);
  const PLACEMENT_KEYS = new Set(["provider_realm", "quota_class"]);
  const AGGREGATION_KEYS = new Set([
    "schema_version", "root_job_id", "handoff_digest", "policy_sha", "plan_attempt_id",
    "plan_digest", "revisions", "aggregate_summary", "evidence_digests",
  ]);
  const REVISION_KEYS = new Set([
    "ordinal", "plan_step_id", "current_job_id", "current_attempt_id", "current_result_digest",
    "repair_round", "review_required", "qualifying_review_job_id", "qualifying_review_attempt_id",
    "qualifying_review_result_digest",
  ]);

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

  function validText(value, maximum = 8192, nonempty = false) {
    return typeof value === "string" && !value.includes("\0") && value.length <= maximum &&
      (!nonempty || (value.length > 0 && value.trim() === value));
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

  function validWorkResult(value, expected, repair) {
    const keys = repair ? REPAIR_KEYS : WORK_KEYS;
    const schema = repair ? "mastermind.repair_result/v1" : "mastermind.work_result/v1";
    if (!exactKeys(value, keys) || value.schema_version !== schema || !validLineage(value, expected) ||
        !Number.isInteger(value.repair_round) || value.repair_round < (repair ? 1 : 0) ||
        value.repair_round > (repair ? 2 : 0) || !validArtifacts(value.artifacts) ||
        !validEvidence(value.evidence_digests)) return false;
    if (!repair) return true;
    return validId(value.supersedes_job_id) && validId(value.rejected_review_job_id) &&
      validDigest(value.rejected_review_result_digest);
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

  function validPlanResult(value, expected) {
    if (!exactKeys(value, PLAN_KEYS) || !["mastermind.execution_plan/v1", "mastermind.execution_plan/v2"].includes(value.schema_version) ||
        value.root_job_id !== expected.root_job_id || value.plan_attempt_id !== expected.run_id) return false;
    const v2 = value.schema_version === "mastermind.execution_plan/v2";
    return validArray(value.steps, 8, (step, index) => {
      const keys = v2 ? PLAN_STEP_V2_KEYS : PLAN_STEP_V1_KEYS;
      if (!exactKeys(step, keys) || step.ordinal !== index || !validId(step.step_id) ||
          !validText(step.objective, 8192, true) || !["routine", "material", "critical"].includes(step.business_impact) ||
          typeof step.review_required !== "boolean" ||
          !validStringArray(step.requested_authorities, 16, (item) => typeof item === "string" && AUTHORITY_RE.test(item)) ||
          !validStringArray(step.allowed_write_paths, 32, (item) => validText(item, 1024, true)) ||
          !validStringArray(step.validation_ids, 64, validDigest) ||
          !Number.isInteger(step.attempt_limit) || step.attempt_limit < 1 || step.attempt_limit > 2 ||
          !["default", "small"].includes(step.cost_class)) return false;
      return !v2 || (exactKeys(step.placement, PLACEMENT_KEYS) &&
        validText(step.placement.provider_realm, 128, true) && validText(step.placement.quota_class, 128, true));
    }, 1);
  }

  function validAggregationResult(value, expected) {
    if (!exactKeys(value, AGGREGATION_KEYS) || value.schema_version !== "mastermind.aggregation_result/v1" ||
        value.root_job_id !== expected.job_id || !validDigest(value.handoff_digest) ||
        !validDigest(value.policy_sha) || !validId(value.plan_attempt_id) || !validDigest(value.plan_digest) ||
        !validText(value.aggregate_summary) || !validEvidence(value.evidence_digests)) return false;
    return validArray(value.revisions, 8, (item, index) => {
      if (!exactKeys(item, REVISION_KEYS) || item.ordinal !== index || !validId(item.plan_step_id) ||
          !validId(item.current_job_id) || !validId(item.current_attempt_id) || !validDigest(item.current_result_digest) ||
          !Number.isInteger(item.repair_round) || item.repair_round < 0 || item.repair_round > 2 ||
          typeof item.review_required !== "boolean") return false;
      const reviewIds = [item.qualifying_review_job_id, item.qualifying_review_attempt_id];
      const nullableIds = reviewIds.every((entry) => entry === null || validId(entry));
      const nullableDigest = item.qualifying_review_result_digest === null || validDigest(item.qualifying_review_result_digest);
      if (!nullableIds || !nullableDigest) return false;
      const allPresent = reviewIds.every((entry) => entry !== null) && item.qualifying_review_result_digest !== null;
      const allAbsent = reviewIds.every((entry) => entry === null) && item.qualifying_review_result_digest === null;
      return item.review_required ? allPresent : allAbsent;
    }, 1);
  }

  function validRoleResult(value, expected) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return false;
    if (expected.role === "plan") return validPlanResult(value, expected);
    if (expected.role === "work") return validWorkResult(value, expected, false);
    if (expected.role === "review") return validReviewResult(value, expected);
    if (expected.role === "repair") return validWorkResult(value, expected, true);
    return validAggregationResult(value, expected);
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
        !validStringArray(value.errors, 16) || !validRoleResult(value.role_result, expected)) {
      return closed("RESULT_REFUSED");
    }
    return closed("RESULT_READY", text, bytes.byteLength);
  }

  globalThis.MMXWebSolCognitionResult = Object.freeze({
    MAX_CANONICAL_RESULT_BYTES,
    reduceCanonicalResultText,
  });
})();
