/** Actual TS decoder against a real disposable Runtime/Workspace producer.
 * node --experimental-transform-types scripts/qualify_execution_return_read.mjs
 * The resolution hook supplies TS extensions only; no source is rewritten.
 */
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { registerHooks } from "node:module";
registerHooks({ resolve(specifier, context, nextResolve) {
  try { return nextResolve(specifier, context); }
  catch (error) {
    if (error.code === "ERR_MODULE_NOT_FOUND" && specifier.startsWith(".") && !/\.[a-z]+$/i.test(specifier))
      return nextResolve(specifier + ".ts", context);
    throw error;
  }
} });
const { decodeExecutionReturnRead } = await import("../app/mastermind_os/src/execution-return-read.ts");
const { mintSubmissionId } = await import("../app/mastermind_os/src/hermes-native/execution-return-contract.ts");
const fixture = JSON.parse(await readFile(new URL("../integrations/mmos/fixtures/execution_return_read_v1/retained.json", import.meta.url), "utf8"));
const wire = fixture.selection;
const selection = { workRef: wire.work_ref, rootJobId: wire.root_job_id, jobId: wire.job_id,
  attemptId: wire.attempt_id, resultEnvelopeDigest: wire.result_envelope_digest };
let assertions = 0;
function check(condition, message) { assert.ok(condition, message); assertions++; }
const valid = await decodeExecutionReturnRead(fixture, selection);
check(valid?.delivery_receipt?.state === "delivered", "original delivered receipt retained");
check(valid?.execution_return?.acceptance === "not_accepted", "delivery does not claim acceptance");
for (const mutate of [
  body => { body.extra = true; },
  body => { body.native_binding = { private: true }; },
  body => { body.selection.job_id = "JOB-999"; },
  body => { body.selection.result_envelope_digest = "f".repeat(64); },
  body => { body.source_observation.selection.attempt_id = "ATT-" + "e".repeat(32); },
  body => { body.source_observation.runtime.state = "UNKNOWN"; },
  body => { body.source_observation.runtime.after++; },
  body => { body.source_observation.control_room.publication_after++; },
  body => { body.execution_return.acceptance = "accepted"; },
  body => { body.execution_return.digest = "0".repeat(64); },
  body => { body.delivery_receipt.return_digest = "f".repeat(64); },
  body => { body.execution_return = null; },
  body => { body.reason_codes = ["SOURCE_UNAVAILABLE"]; },
  body => { body.execution_return.result.text = "界".repeat(40_000); },
]) {
  const changed = structuredClone(fixture); mutate(changed);
  check(await decodeExecutionReturnRead(changed, selection) === null, "malformed/foreign body refused");
}
const foreignReceipt = structuredClone(fixture);
foreignReceipt.delivery_receipt.conversation_id = "different-original-conversation";
foreignReceipt.delivery_receipt.submission_id = await mintSubmissionId(foreignReceipt.delivery_receipt.return_digest,
  foreignReceipt.delivery_receipt.conversation_id);
check(await decodeExecutionReturnRead(foreignReceipt, selection) === null, "same return ID cannot substitute conversation");
const unknown = structuredClone(fixture);
unknown.delivery_receipt.state = "unknown"; unknown.delivery_receipt.transport_ref = null;
check((await decodeExecutionReturnRead(unknown, selection))?.delivery_receipt?.state === "unknown", "unknown retained honestly");
const empty = { ...structuredClone(fixture), execution_return: null, delivery_receipt: null };
check((await decodeExecutionReturnRead(empty, selection))?.execution_return === null, "no return stays empty");
const unavailable = { ...empty, availability: "UNAVAILABLE", reason_codes: ["SOURCE_UNAVAILABLE"],
  source_observation: { schema: "mastermind.workspace_result_observation.v1", state: "UNKNOWN",
    selection: wire, control_room: null, runtime: null } };
check((await decodeExecutionReturnRead(unavailable, selection))?.availability === "UNAVAILABLE", "typed unavailable retained");
check(await decodeExecutionReturnRead({ ...unavailable, execution_return: fixture.execution_return }, selection) === null,
  "unavailable discards material");
console.log(JSON.stringify({ state: "PASS", assertions, consumer: "actual TypeScript decoder",
  producer: "disposable actual Runtime and Workspace owner", nativeEffects: "NOT_EXERCISED" }));
