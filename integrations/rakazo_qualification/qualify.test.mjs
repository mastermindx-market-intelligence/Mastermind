import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { before, test } from "node:test";
import { observePinnedRakazo, qualifyPinIdentity, RAKAZO_PIN } from "./qualify.mjs";

let report;

before(async () => {
  report = await observePinnedRakazo();
});

test("pinned Apache-2.0 source is the only admitted Rakazo identity", () => {
  const refused = qualifyPinIdentity({
    sha: "0".repeat(40),
    licenseText: "MIT\n",
    packageLicense: "MIT",
  });
  assert.equal(refused.ok, false);
  assert.ok(refused.failures.some((failure) => failure.includes(RAKAZO_PIN)));
  assert.ok(refused.failures.some((failure) => failure.includes("Apache-2.0")));
  assert.ok(refused.failures.some((failure) => failure.includes("LICENSE text")));

  assert.equal(report.pin, RAKAZO_PIN);
  console.log(`rakazo pin ${report.pin}`);
  assert.equal(report.repository, "https://github.com/elie222/rakazo.git");
  assert.equal(report.license, "Apache-2.0");
  assert.deepEqual(report.dependencies, {
    zod: "4.6.7",
    "@orpc/contract": "1.15.7",
    croner: "10.0.1",
  });
  assert.equal(report.integration_burden.adopted_as_company_authority.length, 0);
});

test("two bot identities stay distinct on private computers and share one team computer", () => {
  const observed = report.cases.two_bot_identities;
  assert.deepEqual(observed.team_scope, ["team:space-1:user-1", "team:space-1:user-1"]);
  const digest = createHash("sha256").update("space-1:user-1").digest("hex").slice(0, 32);
  assert.equal(observed.team_home, `team-${digest}`);
  assert.deepEqual(observed.private_scope, ["bot:bot-a", "bot:bot-b"]);
  assert.deepEqual(observed.private_home, ["bot-a", "bot-b"]);
  assert.equal(observed.dedicated_without_bot, "Dedicated computers require a bot id");
});

test("conversation keeps each bot's history and does not treat a routine as the conversation", () => {
  const observed = report.cases.conversation;
  assert.deepEqual(observed.bot_ids, ["bot-a", "bot-b"]);
  assert.deepEqual(observed.texts, ["alpha", "beta"]);
  assert.equal(observed.replay_matches, true);
  assert.equal(observed.user_is_conversational, true);
  assert.equal(observed.routine_is_conversational, false);
});

test("routine schedule and inbound prompt stay owner-authored", () => {
  const observed = report.cases.routine;
  assert.equal(observed.next_weekday_utc, "2026-10-26T09:00:00.000Z");
  assert.equal(observed.one_shot_anchor, "2026-10-24T12:00:00.000Z");
  assert.equal(observed.mixed_one_shot_rejected, true);
  assert.deepEqual(observed.inbound_prompts, ["Check the board"]);
});

test("private computers hide paths that a shared computer exposes only through shared/", () => {
  const observed = report.cases.private_vs_shared_computer_visibility;
  assert.deepEqual(observed.private_paths, ["notes/secret.txt", "notes/secret.txt"]);
  assert.deepEqual(observed.team_private_folders, [
    "bots/bot-a/notes/result.txt",
    "bots/bot-b/notes/result.txt",
  ]);
  assert.deepEqual(observed.shared_paths, ["shared/brief.md", "shared/brief.md"]);
  assert.equal(observed.displayed_home, "notes/result.txt");
  assert.equal(observed.displayed_shared, "shared/brief.md");
  assert.match(observed.other_bot_write, /escapes the bot workspace/);
});

test("effect approval pauses a ruled side effect and keeps one effect identity across replay", () => {
  const observed = report.cases.effect_approval;
  assert.equal(observed.ruled_effect, "ask");
  assert.equal(observed.ruled_gate, "ask");
  assert.equal(observed.always_allow, "allow");
  assert.equal(observed.explicit_create_space, true);
  assert.equal(observed.owner_write_exempt, false);
  assert.equal(observed.webhook_write_requires_approval, true);
  assert.equal(observed.effect_key, observed.replay_effect_key);
  assert.match(observed.effect_key, /^run-1:write_file:[a-f0-9]{64}$/);
  assert.equal(observed.legacy_call_ids_differ, true);
  assert.equal(observed.approval_card, true);
  assert.equal(observed.text_ask_is_not_approval, false);
});

test("disconnect recovery rebuilds the retained thread and does not replay a cancelled run", () => {
  const observed = report.cases.disconnect_recovery;
  assert.equal(observed.dropped_connection_is_unreachable, true);
  assert.equal(observed.answered_request_is_not_unreachable, false);
  assert.deepEqual(observed.retained_thread, ["send the note"]);
  assert.equal(observed.replay_matches_retained, true);
  assert.equal(observed.cancelled_to_running, false);
  assert.equal(observed.waiting_input_can_resume, true);
});

test("streaming folds one live reply and cancellation drops it without replay", () => {
  const streaming = report.cases.streaming;
  assert.deepEqual(streaming.enabled_only_when_on, [true, false, "off"]);
  assert.deepEqual(streaming.live_ids, ["progress:run-stream"]);
  assert.deepEqual(streaming.live_text, ["hello"]);

  const cancelled = report.cases.cancellation_without_replay;
  assert.equal(cancelled.running_to_cancelled, true);
  assert.equal(cancelled.cancelled_to_running, false);
  assert.equal(cancelled.cancelled_to_queued, false);
  assert.equal(cancelled.cancelled_restart_error, "Illegal run transition cancelled -> running");
  assert.equal(cancelled.progress_survives_cancel, false);
  assert.equal(cancelled.user_message_count, 1);
});

test("restart keeps a failed run and the same workspace path", () => {
  const observed = report.cases.restart_persistence;
  assert.equal(observed.failed_to_queued, true);
  assert.equal(observed.completed_to_queued, false);
  assert.deepEqual(observed.workspace_path, ["notes/result.txt", "notes/result.txt"]);
});

test("unsupported capabilities stay explicit", () => {
  const unsupported = Object.fromEntries(report.unsupported.map((item) => [item.id, item]));
  assert.equal(unsupported.cordis_plugin_load.observed, "absent");
  assert.equal(unsupported.postgres_graphile_product_journey.observed, "database-gated");
  assert.equal(unsupported.authenticated_signed_in_ui.observed, "not-run");
  assert.deepEqual(report.integration_burden.missing_proof, [
    "authenticated signed-in UI",
    "database-backed product journeys",
    "Cordis plugin load",
    "live model provider",
    "24-hour and seven-day observation",
  ]);
  assert.deepEqual(report.integration_burden.load_boundary_stubs, [
    "packages/db/src/client.js",
    "packages/db/src/row-security.js",
  ]);
});
