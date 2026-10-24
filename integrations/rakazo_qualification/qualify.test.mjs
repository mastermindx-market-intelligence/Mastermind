import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { appendFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { before, test } from "node:test";
import {
  RAKAZO_PIN,
  buildExecutionEnv,
  cloneOwnedCheckout,
  ensurePinCheckout,
  observePinnedRakazo,
  qualifyPinIdentity,
  removeOwnedDirectory,
} from "./qualify.mjs";

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
  assert.equal(report.source_gate.checked_before_import, true);
  assert.equal(report.source_gate.sha, RAKAZO_PIN);
  assert.deepEqual(report.dependencies, {
    zod: "4.6.7",
    "@orpc/contract": "1.15.7",
    croner: "10.0.1",
  });
  assert.equal(report.integration_burden.adopted_as_company_authority.length, 0);
});

test("tampered donor source is rejected before import", async () => {
  const copy = cloneOwnedCheckout(report.checkout_root);
  appendFileSync(
    path.join(copy, "packages/core/src/events.ts"),
    '\nthrow new Error("IMPORTED_TAMPERED_SOURCE");\n',
  );
  await assert.rejects(
    () => observePinnedRakazo(copy),
    (error) => {
      assert.equal(error.code, "SOURCE_DRIFT");
      assert.equal(error.imported, false);
      assert.equal(String(error.message).includes("IMPORTED_TAMPERED_SOURCE"), false);
      assert.match(error.message, /worktree drift/);
      return true;
    },
  );
});

test("an untracked sibling shadow is rejected before import", async () => {
  const copy = cloneOwnedCheckout(report.checkout_root);
  writeFileSync(
    path.join(copy, "packages/core/src/events.js"),
    'throw new Error("IMPORTED_SHADOW");\n',
  );
  await assert.rejects(
    () => observePinnedRakazo(copy),
    (error) => {
      assert.equal(error.code, "SOURCE_SHADOW");
      assert.equal(error.imported, false);
      assert.equal(String(error.message).includes("IMPORTED_SHADOW"), false);
      assert.match(error.message, /shadow file/);
      return true;
    },
  );
});

test("an unowned sentinel path survives a rejected lookup", () => {
  const foreign = path.join(tmpdir(), `rakazo-qualification-foreign-${process.pid}`);
  mkdirSync(foreign, { recursive: true });
  writeFileSync(path.join(foreign, "SENTINEL"), "keep");

  const predictable = path.join(tmpdir(), `rakazo-pin-${RAKAZO_PIN}`);
  mkdirSync(predictable, { recursive: true });
  writeFileSync(path.join(predictable, "SENTINEL"), "keep");
  const sibling = `${predictable}-sentinel`;
  mkdirSync(sibling, { recursive: true });
  writeFileSync(path.join(sibling, "SENTINEL"), "keep");

  assert.throws(
    () => ensurePinCheckout({ source: foreign }),
    (error) => {
      assert.equal(error.code, "ROOT_MISMATCH");
      assert.equal(error.imported, false);
      assert.equal(error.removedOwnedPath, undefined);
      return true;
    },
  );
  assert.throws(
    () => ensurePinCheckout({ source: path.join(report.checkout_root, "packages") }),
    (error) => {
      assert.equal(error.code, "ROOT_MISMATCH");
      assert.equal(error.imported, false);
      return true;
    },
  );
  assert.throws(() => removeOwnedDirectory(foreign), /unowned/);
  assert.throws(() => removeOwnedDirectory(predictable), /unowned/);
  assert.throws(() => removeOwnedDirectory(sibling), /unowned/);
  assert.throws(() => removeOwnedDirectory(report.checkout_root), /unowned/);

  assert.equal(readFileSync(path.join(foreign, "SENTINEL"), "utf8"), "keep");
  assert.equal(readFileSync(path.join(predictable, "SENTINEL"), "utf8"), "keep");
  assert.equal(readFileSync(path.join(sibling, "SENTINEL"), "utf8"), "keep");
  assert.equal(
    readFileSync(path.join(report.checkout_root, "packages/core/src/events.ts"), "utf8").includes(
      "IMPORTED_TAMPERED_SOURCE",
    ),
    false,
  );
});

test("unrelated environment variables do not leak into execution", () => {
  const canary = path.join(tmpdir(), `rakazo-qualification-canary-${process.pid}.cjs`);
  writeFileSync(canary, "console.error('CANARY_LOADED');\n");
  const keys = [
    "NODE_OPTIONS",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "OPENAI_API_KEY",
    "RAKAZO_QUALIFICATION_CANARY",
    "GIT_CONFIG_GLOBAL",
    "npm_config_userconfig",
    "npm_config_registry",
  ];
  const previous = new Map(keys.map((key) => [key, process.env[key]]));
  try {
    process.env.NODE_OPTIONS = `--require ${canary}`;
    process.env.HTTPS_PROXY = "http://127.0.0.1:9";
    process.env.HTTP_PROXY = "http://127.0.0.1:9";
    process.env.ALL_PROXY = "http://127.0.0.1:9";
    process.env.http_proxy = "http://127.0.0.1:9";
    process.env.https_proxy = "http://127.0.0.1:9";
    process.env.OPENAI_API_KEY = "sk-canary-not-a-credential";
    process.env.RAKAZO_QUALIFICATION_CANARY = "leak-me";
    process.env.GIT_CONFIG_GLOBAL = path.join(tmpdir(), "not-the-owned-gitconfig");
    process.env.npm_config_userconfig = path.join(tmpdir(), "not-the-owned-npmrc");
    process.env.npm_config_registry = "http://127.0.0.1:9/registry";

    const env = buildExecutionEnv({ pinRoot: report.checkout_root });
    assert.equal(env.RAKAZO_PIN_ROOT, report.checkout_root);
    assert.equal(env.PATH, process.env.PATH);
    assert.notEqual(env.HOME, process.env.HOME);
    assert.equal(env.GIT_CONFIG_GLOBAL, "/dev/null");
    assert.equal(env.NODE_OPTIONS, undefined);
    assert.equal(env.HTTPS_PROXY, undefined);
    assert.equal(env.HTTP_PROXY, undefined);
    assert.equal(env.ALL_PROXY, undefined);
    assert.equal(env.http_proxy, undefined);
    assert.equal(env.https_proxy, undefined);
    assert.equal(env.OPENAI_API_KEY, undefined);
    assert.equal(env.RAKAZO_QUALIFICATION_CANARY, undefined);
    assert.equal(env.npm_config_registry, undefined);
    assert.notEqual(env.npm_config_userconfig, process.env.npm_config_userconfig);

    const probe = spawnSync(
      process.execPath,
      [
        "-e",
        "process.stdout.write(JSON.stringify({NODE_OPTIONS:process.env.NODE_OPTIONS??null,HTTPS_PROXY:process.env.HTTPS_PROXY??null,HTTP_PROXY:process.env.HTTP_PROXY??null,ALL_PROXY:process.env.ALL_PROXY??null,OPENAI_API_KEY:process.env.OPENAI_API_KEY??null,RAKAZO_QUALIFICATION_CANARY:process.env.RAKAZO_QUALIFICATION_CANARY??null,npm_config_registry:process.env.npm_config_registry??null}))",
      ],
      { env, encoding: "utf8" },
    );
    assert.equal(probe.status, 0, probe.stderr);
    assert.equal(String(probe.stderr).includes("CANARY_LOADED"), false);
    assert.deepEqual(JSON.parse(probe.stdout), {
      NODE_OPTIONS: null,
      HTTPS_PROXY: null,
      HTTP_PROXY: null,
      ALL_PROXY: null,
      OPENAI_API_KEY: null,
      RAKAZO_QUALIFICATION_CANARY: null,
      npm_config_registry: null,
    });
  } finally {
    for (const [key, value] of previous) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
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

test("approval rules resolve ask or allow and identical arguments keep one effect key", () => {
  const observed = report.cases.approval_rule_and_effect_key;
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

test("connection failures classify reachability and a fabricated event log projects the same messages", () => {
  const observed = report.cases.connection_classification_and_event_projection;
  assert.equal(observed.dropped_connection_is_unreachable, true);
  assert.equal(observed.answered_request_is_not_unreachable, false);
  assert.deepEqual(observed.retained_thread, ["send the note"]);
  assert.equal(observed.replay_matches_retained, true);
  assert.equal(observed.cancelled_to_running, false);
  assert.equal(observed.waiting_input_can_resume, true);
});

test("streaming preference and fabricated progress deltas fold into one projection", () => {
  const streaming = report.cases.streaming_preference_and_progress_projection;
  assert.deepEqual(streaming.enabled_only_when_on, [true, false, "off"]);
  assert.deepEqual(streaming.live_ids, ["progress:run-stream"]);
  assert.deepEqual(streaming.live_text, ["hello"]);
});

test("a fabricated cancel event clears that progress projection and forbids cancelled to running", () => {
  const cancelled = report.cases.cancel_event_projection_and_status_transition;
  assert.equal(cancelled.running_to_cancelled, true);
  assert.equal(cancelled.cancelled_to_running, false);
  assert.equal(cancelled.cancelled_to_queued, false);
  assert.equal(cancelled.cancelled_restart_error, "Illegal run transition cancelled -> running");
  assert.equal(cancelled.progress_survives_cancel, false);
  assert.equal(cancelled.user_message_count, 1);
});

test("a failed status may return to queued and the workspace path function repeats", () => {
  const observed = report.cases.failed_status_transition_and_path_repeat;
  assert.equal(observed.failed_to_queued, true);
  assert.equal(observed.completed_to_queued, false);
  assert.deepEqual(observed.workspace_path, ["notes/result.txt", "notes/result.txt"]);
});

test("Cordis absence is distinct from NOT_RUN process, disconnect, and database proofs", () => {
  assert.equal(report.absent.cordis_plugin_load.status, "ABSENT");
  assert.equal(report.absent.cordis_plugin_load.matches, 0);
  const notRun = Object.fromEntries(report.not_run.map((item) => [item.id, item]));
  for (const id of [
    "process_restart_persistence",
    "real_disconnect_stream_cancel",
    "committed_effect_deduplication",
    "database_backed_product_journey",
    "authenticated_signed_in_ui",
    "live_model_provider",
    "elapsed_reliability_observation",
  ]) {
    assert.equal(notRun[id].status, "NOT_RUN", id);
  }
  assert.equal(notRun.cordis_plugin_load, undefined);
  assert.equal(notRun.database_backed_product_journey.gate_present, true);
  assert.match(notRun.database_backed_product_journey.prerequisite, /journeys\.test\.ts/);
  assert.match(notRun.database_backed_product_journey.prerequisite, /VERIFY_DATABASE=1/);
  assert.match(notRun.database_backed_product_journey.prerequisite, /DATABASE_URL/);
  assert.match(notRun.database_backed_product_journey.prerequisite, /does not install or start/);
  console.log("NOT_RUN");
});
