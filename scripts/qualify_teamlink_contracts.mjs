/** Actual TypeScript consumer qualification, using the shared Python vectors.
 * Run: node scripts/qualify_teamlink_contracts.mjs
 * No installed transport, credentials, dispatch or consumption is exercised.
 */
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  TeamLinkContractError, isExpired, isPingPongEcho, mayForward,
  mintMessageId, parseTeamLinkMessage, verifyDuplicate,
} from "../app/mastermind_os/src/hermes-native/teamlink-contract.ts";

const cases = JSON.parse(await readFile(new URL("../tests/fixtures/teamlink_envelopes.json", import.meta.url), "utf8"));
let checks = 0;
function check(run) { run(); checks += 1; }
function changed(message, path, value) {
  const result = structuredClone(message), keys = path.split(".");
  let target = result;
  for (const key of keys.slice(0, -1)) target = target[key];
  target[keys.at(-1)] = value;
  return result;
}

for (const detail of ["", "recipient"]) {
  const error = new TeamLinkContractError("INVALID", detail);
  check(() => assert.deepEqual([error.code, error.detail, error.message],
    ["INVALID", detail, detail ? "INVALID: recipient" : "INVALID"]));
}

for (const item of cases.immutableChanges) {
  check(() => assert.equal(verifyDuplicate(cases.message, changed(cases.message, item.path, item.value)), "refused_content_changed", item.path));
}
const repeat = structuredClone(cases.message);
delete repeat.reply_to;
delete repeat.from.thread_ref;
repeat.correlation = Object.fromEntries(Object.entries(repeat.correlation).reverse().filter(([, value]) => value !== null));
check(() => assert.equal(verifyDuplicate(cases.message, repeat), "same_message"));
const observed = { ...structuredClone(cases.message), hop_count: 2, delivery_state: "replied" };
check(() => assert.equal(verifyDuplicate(observed, cases.message), "same_message"));
check(() => assert.deepEqual([observed.hop_count, observed.delivery_state], [2, "replied"]));
check(() => assert.deepEqual(mayForward(observed, new Date("2099-11-09T00:00:00Z")), [false, "hop_breach"]));
const malformed = structuredClone(cases.message);
delete malformed.to;
check(() => assert.throws(() => verifyDuplicate(cases.message, malformed), TeamLinkContractError));
const expired = changed(cases.message, "expires_at", "2000-01-01T00:00:00Z");
check(() => assert.deepEqual(mayForward(expired), [false, "expired"]));
check(() => assert.deepEqual(mayForward(expired, new Date(expired.expires_at)), [false, "expired"]));
for (const clock of [new Date(NaN), "now", 0, false, null]) {
  check(() => assert.equal(isExpired(cases.message, clock), true));
  check(() => assert.deepEqual(mayForward(cases.message, clock), [false, "expired"]));
}
for (const expiry of cases.invalidDates) {
  const message = changed(cases.message, "expires_at", expiry);
  check(() => assert.throws(() => parseTeamLinkMessage(message), TeamLinkContractError));
  check(() => assert.equal(isExpired(message, new Date("2000-01-01T00:00:00Z")), true));
}
const echo = structuredClone(cases.message);
[echo.from, echo.to] = [echo.to, echo.from];
echo.message_id = "tlm-" + "f".repeat(32);
echo.hop_count = 1;
echo.delivery_state = "picked_up";
check(() => assert.equal(isPingPongEcho(cases.message, echo), true));
for (const [path, value] of [["operation_key", "other-operation"], ["from.side", "hermes_profile"],
  ["from.thread_ref", "another-thread"], ["to.id", "another-agent"],
  ["body", "A new question"], ["correlation.root_run_ref", "other-root"]]) {
  check(() => assert.equal(isPingPongEcho(cases.message, changed(echo, path, value)), false, path));
}
// Existing v1 mint is deliberately unchanged; original Unicode identities survive.
assert.equal(await mintMessageId("coo-bot", "roundtrip-a3", "状态 status ping 中文", []),
  "tlm-64a95e24a3ae74fba98f72b2f2aa1352");
assert.equal(await mintMessageId("engineering", "wo19-teamlink-check-1",
  "Run the WO-19 dry-run and report the unattributed count.",
  ["DEC:COMMERCIAL-DATA-RIGHTS-CHAIRMAN-ATTESTATION-20261023", "sha256:" + "ab".repeat(32)]),
  "tlm-0b0e68856ac4439993fac4b6e166b593");
checks += 2;
console.log(JSON.stringify({ state: "PASS", checks, consumer: "actual TypeScript module", transport: "NOT_EXERCISED" }));
