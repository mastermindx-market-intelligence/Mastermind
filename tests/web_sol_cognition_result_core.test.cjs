"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const source = fs.readFileSync(
  path.join(__dirname, "..", "integrations", "chairman_surfaces", "web_sol_extension", "cognition_result_core.js"),
  "utf8",
);
const context = vm.createContext({TextEncoder});
vm.runInContext(source, context);
const core = context.MMXWebSolCognitionResult;

const expected = Object.freeze({
  job_id: "JOB-200",
  run_id: "ATT-200",
  worker_id: "web-sol-pro-3",
  role: "work",
  root_job_id: "JOB-ROOT",
});

function envelope(overrides = {}) {
  return {
    current_state: "Research synthesis is complete; implementation remains external.",
    errors: [],
    job_id: expected.job_id,
    next_actions: ["Route the accepted repair to a write-capable worker."],
    role: expected.role,
    role_result: {
      artifacts: [],
      evidence_digests: ["a".repeat(64)],
      plan_attempt_id: "ATT-PLAN",
      plan_digest: "b".repeat(64),
      plan_step_id: "research-1",
      repair_round: 0,
      root_job_id: expected.root_job_id,
      schema_version: "mastermind.work_result/v1",
    },
    run_id: expected.run_id,
    schema_version: "mastermind.executive_orchestration_result/v1",
    status: "COMPLETED",
    summary: "Read-only Pro research identified the bounded repair and evidence.",
    validations: [],
    worker_id: expected.worker_id,
    ...overrides,
  };
}

function canonical(value) {
  if (value === null) return "null";
  if (typeof value === "string") return JSON.stringify(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return String(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
}

function test(name, fn) {
  try {
    fn();
    process.stdout.write(`ok - ${name}\n`);
  } catch (error) {
    process.stderr.write(`not ok - ${name}\n${error.stack}\n`);
    process.exitCode = 1;
  }
}

test("accepts one exact canonical existing Executive result envelope", () => {
  const text = canonical(envelope());
  const result = core.reduceCanonicalResultText(text, expected);
  assert.equal(result.status, "RESULT_READY");
  assert.equal(result.canonical_result_json, text);
  assert.equal(result.canonical_result_byte_length, Buffer.byteLength(text, "utf8"));
});

test("refuses prose around an otherwise valid result", () => {
  const result = core.reduceCanonicalResultText(`done\n${canonical(envelope())}`, expected);
  assert.equal(result.status, "RESULT_REFUSED");
  assert.equal(result.canonical_result_json, null);
});

test("refuses fenced output instead of scraping a block from transcript text", () => {
  const result = core.reduceCanonicalResultText(`\`\`\`json\n${canonical(envelope())}\n\`\`\``, expected);
  assert.equal(result.status, "RESULT_REFUSED");
});

test("refuses noncanonical spacing and key order", () => {
  const result = core.reduceCanonicalResultText(JSON.stringify(envelope(), null, 2), expected);
  assert.equal(result.status, "RESULT_REFUSED");
});

test("refuses duplicate JSON keys because canonical bytes no longer match", () => {
  const text = canonical(envelope());
  const duplicate = text.replace('"job_id":"JOB-200"', '"job_id":"JOB-200","job_id":"JOB-200"');
  const result = core.reduceCanonicalResultText(duplicate, expected);
  assert.equal(result.status, "RESULT_REFUSED");
});

test("refuses outer identity drift", () => {
  const result = core.reduceCanonicalResultText(canonical(envelope({worker_id: "wrong-worker"})), expected);
  assert.equal(result.status, "RESULT_REFUSED");
});

test("refuses root identity drift inside role result", () => {
  const value = envelope();
  value.role_result = {...value.role_result, root_job_id: "JOB-OTHER"};
  const result = core.reduceCanonicalResultText(canonical(value), expected);
  assert.equal(result.status, "RESULT_REFUSED");
});

test("refuses unknown outer fields", () => {
  const result = core.reduceCanonicalResultText(canonical(envelope({transcript: "no"})), expected);
  assert.equal(result.status, "RESULT_REFUSED");
});

test("refuses over-budget canonical result without returning the content", () => {
  const value = envelope();
  value.next_actions = Array.from({length: 16}, (_, index) => `${index}:` + "x".repeat(4000));
  const text = canonical(value);
  assert.ok(Buffer.byteLength(text, "utf8") > core.MAX_CANONICAL_RESULT_BYTES);
  const result = core.reduceCanonicalResultText(text, expected);
  assert.equal(result.status, "RESULT_TOO_LARGE");
  assert.equal(result.canonical_result_json, null);
  assert.equal(result.canonical_result_byte_length, 0);
});


test("refuses unknown nested role-result fields before any content crosses the browser boundary", () => {
  const value = envelope();
  value.role_result = {...value.role_result, transcript: "private transcript"};
  const result = core.reduceCanonicalResultText(canonical(value), expected);
  assert.equal(result.status, "RESULT_REFUSED");
  assert.equal(result.canonical_result_json, null);
});

test("refuses unknown nested artifact fields before export", () => {
  const value = envelope();
  value.role_result = {
    ...value.role_result,
    artifacts: [{path: "artifact.txt", digest: "c".repeat(64), transcript: "private"}],
  };
  const result = core.reduceCanonicalResultText(canonical(value), expected);
  assert.equal(result.status, "RESULT_REFUSED");
  assert.equal(result.canonical_result_json, null);
});

test("refuses non-string next-action payloads before export", () => {
  const value = envelope();
  value.next_actions = [{transcript: "private"}];
  const result = core.reduceCanonicalResultText(canonical(value), expected);
  assert.equal(result.status, "RESULT_REFUSED");
  assert.equal(result.canonical_result_json, null);
});


test("accepts the closed existing Executive shape for every orchestration role family", () => {
  const digestA = "a".repeat(64);
  const digestB = "b".repeat(64);
  const cases = [
    {
      role: "plan",
      role_result: {
        schema_version: "mastermind.execution_plan/v1",
        root_job_id: "JOB-ROOT",
        plan_attempt_id: "ATT-ROLE",
        steps: [{
          ordinal: 0,
          step_id: "step-1",
          objective: "Perform bounded research.",
          business_impact: "routine",
          review_required: false,
          requested_authorities: ["READ_ONLY"],
          allowed_write_paths: [],
          validation_ids: [],
          attempt_limit: 1,
          cost_class: "default",
        }],
      },
    },
    {
      role: "plan",
      role_result: {
        schema_version: "mastermind.execution_plan/v2",
        root_job_id: "JOB-ROOT",
        plan_attempt_id: "ATT-ROLE",
        steps: [{
          ordinal: 0,
          step_id: "step-1",
          objective: "Perform bounded research.",
          business_impact: "routine",
          review_required: false,
          requested_authorities: ["READ_ONLY"],
          allowed_write_paths: [],
          validation_ids: [],
          attempt_limit: 1,
          cost_class: "default",
          placement: {provider_realm: "realm-1", quota_class: "default"},
        }],
      },
    },
    {
      role: "review",
      role_result: {
        schema_version: "mastermind.review_result/v1",
        root_job_id: "JOB-ROOT",
        plan_attempt_id: "ATT-PLAN",
        plan_digest: digestA,
        plan_step_id: "step-1",
        reviewed_job_id: "JOB-WORK",
        reviewed_attempt_id: "ATT-WORK",
        reviewed_result_digest: digestB,
        repair_round: 0,
        verdict: "approve",
        evidence_digests: [],
        findings: [],
      },
    },
    {
      role: "repair",
      role_result: {
        schema_version: "mastermind.repair_result/v1",
        root_job_id: "JOB-ROOT",
        plan_attempt_id: "ATT-PLAN",
        plan_digest: digestA,
        plan_step_id: "step-1",
        repair_round: 1,
        supersedes_job_id: "JOB-WORK",
        rejected_review_job_id: "JOB-REVIEW",
        rejected_review_result_digest: digestB,
        artifacts: [],
        evidence_digests: [],
      },
    },
    {
      role: "aggregation",
      job_id: "JOB-ROOT",
      role_result: {
        schema_version: "mastermind.aggregation_result/v1",
        root_job_id: "JOB-ROOT",
        handoff_digest: digestA,
        policy_sha: digestB,
        plan_attempt_id: "ATT-PLAN",
        plan_digest: digestA,
        revisions: [{
          ordinal: 0,
          plan_step_id: "step-1",
          current_job_id: "JOB-WORK",
          current_attempt_id: "ATT-WORK",
          current_result_digest: digestB,
          repair_round: 0,
          review_required: false,
          qualifying_review_job_id: null,
          qualifying_review_attempt_id: null,
          qualifying_review_result_digest: null,
        }],
        aggregate_summary: "Accepted work is ready for parent consumption.",
        evidence_digests: [],
      },
    },
  ];

  for (const item of cases) {
    const roleExpected = {
      job_id: item.job_id || "JOB-ROLE",
      run_id: "ATT-ROLE",
      worker_id: "worker-role",
      role: item.role,
      root_job_id: "JOB-ROOT",
    };
    const value = {
      schema_version: "mastermind.executive_orchestration_result/v1",
      job_id: roleExpected.job_id,
      run_id: roleExpected.run_id,
      worker_id: roleExpected.worker_id,
      role: item.role,
      status: "COMPLETED",
      role_result: item.role_result,
      summary: "bounded",
      current_state: "complete",
      next_actions: [],
      errors: [],
      validations: [],
    };
    const result = core.reduceCanonicalResultText(canonical(value), roleExpected);
    assert.equal(result.status, "RESULT_READY", item.role_result.schema_version);
  }
});


test("refuses credential-prefixed content before browser export", () => {
  const value = envelope({summary: "credential sk-ant-abcdefghij"});
  const result = core.reduceCanonicalResultText(canonical(value), expected);
  assert.equal(result.status, "RESULT_REFUSED");
  assert.equal(result.canonical_result_json, null);
});

test("refuses JWT-shaped content before browser export", () => {
  const value = envelope({
    current_state: "jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.signature",
  });
  const result = core.reduceCanonicalResultText(canonical(value), expected);
  assert.equal(result.status, "RESULT_REFUSED");
});

test("refuses email-shaped content before browser export", () => {
  const value = envelope({next_actions: ["Contact operator@example.com"]});
  const result = core.reduceCanonicalResultText(canonical(value), expected);
  assert.equal(result.status, "RESULT_REFUSED");
});

test("refuses Mastermind environment or secret-marker material before browser export", () => {
  for (const text of [
    "MASTERMIND_AUTH_TOKEN is configured",
    "TOKEN=plainvalue",
    "PASSWORD=plainvalue",
  ]) {
    const value = envelope({current_state: text});
    const result = core.reduceCanonicalResultText(canonical(value), expected);
    assert.equal(result.status, "RESULT_REFUSED", text);
  }
});


test("reserves worst-case string-framing headroom under the incumbent 64 KiB native frame", () => {
  const nativeFrameBytes = 64 * 1024;
  const reservedFramingBytes = 16 * 1024;
  assert.equal(core.MAX_CANONICAL_RESULT_BYTES, 24 * 1024);
  assert.ok((2 * core.MAX_CANONICAL_RESULT_BYTES) + reservedFramingBytes <= nativeFrameBytes);
});


test("refuses lone UTF-16 surrogate text that native UTF-8 canonicalization cannot accept", () => {
  const value = envelope({summary: "\ud800"});
  const result = core.reduceCanonicalResultText(canonical(value), expected);
  assert.equal(result.status, "RESULT_REFUSED");
});

test("preserves valid non-BMP Unicode text", () => {
  const value = envelope({summary: "bounded research 😀"});
  const text = canonical(value);
  const result = core.reduceCanonicalResultText(text, expected);
  assert.equal(result.status, "RESULT_READY");
  assert.equal(result.canonical_result_json, text);
});
