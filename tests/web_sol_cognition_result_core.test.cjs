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
