import { execFileSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

export const RAKAZO_PIN = "c5e66e010ee3f3166d2ad216f928a75a0b9a2218";
export const RAKAZO_REPOSITORY = "https://github.com/elie222/rakazo.git";

const here = path.dirname(fileURLToPath(import.meta.url));
const COMMAND_TIMEOUT_MS = 180_000;
const ownedDirectories = new Set();
let cachedBaseEnv = null;

const ENTRY_FILES = [
  "packages/core/src/events.ts",
  "packages/db/src/computers.ts",
  "packages/adapters/src/computer-support.ts",
  "packages/core/src/cron.ts",
  "packages/core/src/action-approval.ts",
  "packages/core/src/approval-effect-key.ts",
  "packages/core/src/run-state.ts",
  "packages/core/src/inbound-routine.ts",
  "packages/core/src/user-error.ts",
];

export class QualificationError extends Error {
  constructor(message, code) {
    super(message);
    this.name = "QualificationError";
    this.code = code;
    this.imported = false;
  }
}

export function qualifyPinIdentity({ sha, licenseText, packageLicense }) {
  const failures = [];
  if (sha !== RAKAZO_PIN) failures.push(`commit ${sha} is not pin ${RAKAZO_PIN}`);
  if (packageLicense !== "Apache-2.0") {
    failures.push(`package license ${packageLicense} is not Apache-2.0`);
  }
  if (!String(licenseText).startsWith("Apache License\nVersion 2.0")) {
    failures.push("LICENSE text is not Apache License Version 2.0");
  }
  return { ok: failures.length === 0, failures };
}

function createOwnedAttempt() {
  const created = realpathSync(mkdtempSync(path.join(tmpdir(), "rakazo-qualification-")));
  ownedDirectories.add(created);
  return created;
}

export function removeOwnedDirectory(target) {
  let resolved = path.resolve(String(target));
  try {
    resolved = realpathSync(resolved);
  } catch {
    // A missing path is still unowned unless this process created it.
  }
  if (!ownedDirectories.has(resolved)) {
    throw new QualificationError(`unowned path: ${resolved}`, "UNOWNED_PATH");
  }
  rmSync(resolved, { recursive: true, force: true });
  ownedDirectories.delete(resolved);
  return resolved;
}

function baseExecutionEnv() {
  if (!cachedBaseEnv) {
    const home = createOwnedAttempt();
    const temp = createOwnedAttempt();
    const cache = path.join(home, "npm-cache");
    mkdirSync(cache, { recursive: true });
    const npmrc = path.join(home, ".npmrc");
    writeFileSync(npmrc, "");
    cachedBaseEnv = {
      PATH: process.env.PATH ?? "",
      HOME: home,
      TMPDIR: temp,
      LC_ALL: "C",
      GIT_TERMINAL_PROMPT: "0",
      GIT_CONFIG_NOSYSTEM: "1",
      GIT_CONFIG_GLOBAL: "/dev/null",
      GIT_CONFIG_SYSTEM: "/dev/null",
      GIT_NO_REPLACE_OBJECTS: "1",
      npm_config_userconfig: npmrc,
      npm_config_globalconfig: "/dev/null",
      npm_config_cache: cache,
      npm_config_ignore_scripts: "true",
      npm_config_audit: "false",
      npm_config_fund: "false",
      npm_config_update_notifier: "false",
    };
  }
  return { ...cachedBaseEnv };
}

// PATH is the only ambient value. Provider keys, proxies, NODE_OPTIONS, and
// user git/npm config stay out of acquisition and test execution.
export function buildExecutionEnv({ pinRoot, source } = {}) {
  const env = baseExecutionEnv();
  if (pinRoot) env.RAKAZO_PIN_ROOT = pinRoot;
  if (source) env.RAKAZO_SOURCE = source;
  return env;
}

function commandFailure(command, error) {
  const timedOut = Boolean(error.killed || error.signal);
  const detail = timedOut
    ? `timed out after ${COMMAND_TIMEOUT_MS}ms`
    : String(error.stderr ?? error.message ?? "").trim().slice(0, 400);
  return new QualificationError(`${command} failed: ${detail}`, "COMMAND_FAILED");
}

// Per-invocation only. These override repo-local config for this process and
// do not write the caller's git config. `git status` is not used: it runs
// clean filters even when fsmonitor is disabled. `hash-object --no-filters`
// compares worktree bytes as stored.
const validationGitArgs = [
  "-c", "core.fsmonitor=",
  "-c", "core.fsmonitorHookVersion=0",
  "-c", "core.hooksPath=/dev/null",
  "-c", "core.autocrlf=false",
  "-c", "core.safecrlf=false",
  "-c", "advice.detachedHead=false",
];

function gitSubcommand(args) {
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === "-c" || arg === "-C") {
      index += 1;
      continue;
    }
    if (!arg.startsWith("-")) return arg;
  }
  return "git";
}

function runGit(args, cwd, { input, allowStatus1 = false } = {}) {
  try {
    return execFileSync("git", [...validationGitArgs, ...args], {
      cwd,
      input,
      encoding: "utf8",
      timeout: COMMAND_TIMEOUT_MS,
      maxBuffer: 32 * 1024 * 1024,
      env: buildExecutionEnv(),
      stdio: ["pipe", "pipe", "pipe"],
    });
  } catch (error) {
    if (allowStatus1 && error.status === 1) return "";
    throw commandFailure(`git ${gitSubcommand(args)}`, error);
  }
}

function runNpm(args) {
  try {
    execFileSync("npm", args, {
      cwd: here,
      encoding: "utf8",
      timeout: COMMAND_TIMEOUT_MS,
      maxBuffer: 32 * 1024 * 1024,
      env: buildExecutionEnv(),
      stdio: ["pipe", "pipe", "pipe"],
    });
  } catch (error) {
    throw commandFailure(`npm ${args[0]}`, error);
  }
}

function canonical(target) {
  return realpathSync(path.resolve(target));
}

function readIdentity(root, sha) {
  const licenseText = readFileSync(path.join(root, "LICENSE"), "utf8");
  const packageLicense = JSON.parse(readFileSync(path.join(root, "package.json"), "utf8")).license;
  return qualifyPinIdentity({ sha, licenseText, packageLicense });
}

function nulRecords(text) {
  return text.split("\0").filter((record) => record.length > 0);
}

function hashWorktree(root, paths) {
  if (paths.some((filePath) => filePath.includes("\n"))) {
    throw new QualificationError("worktree drift: newline in tracked path", "SOURCE_DRIFT");
  }
  if (paths.length === 0) {
    throw new QualificationError("worktree drift: no tracked files", "SOURCE_DRIFT");
  }
  const output = runGit(["hash-object", "--no-filters", "--stdin-paths"], root, {
    input: `${paths.join("\n")}\n`,
  });
  const hashes = output.split("\n").filter((line) => line.length > 0);
  if (hashes.length !== paths.length) {
    throw new QualificationError("worktree drift: hash count mismatch", "SOURCE_DRIFT");
  }
  return hashes;
}

export function assertImmutableSource(root) {
  const resolved = path.resolve(String(root ?? ""));
  let toplevel = "";
  try {
    toplevel = runGit(["rev-parse", "--show-toplevel"], resolved).trim();
  } catch (error) {
    if (error instanceof QualificationError) {
      throw new QualificationError(`not a canonical git root: ${resolved}`, "ROOT_MISMATCH");
    }
    throw error;
  }
  let canonicalRoot = resolved;
  let canonicalTop = toplevel;
  try {
    canonicalRoot = canonical(resolved);
    canonicalTop = canonical(toplevel);
  } catch (error) {
    if (error instanceof QualificationError) throw error;
    throw new QualificationError(`not a canonical git root: ${resolved}`, "ROOT_MISMATCH");
  }
  if (canonicalTop !== canonicalRoot) {
    throw new QualificationError(`canonical root ${canonicalTop} is not ${canonicalRoot}`, "ROOT_MISMATCH");
  }

  const sha = runGit(["rev-parse", "HEAD"], resolved).trim();
  if (sha !== RAKAZO_PIN) {
    throw new QualificationError(`commit ${sha} is not pin ${RAKAZO_PIN}`, "PIN_MISMATCH");
  }
  const identity = readIdentity(resolved, sha);
  if (!identity.ok) {
    throw new QualificationError(identity.failures.join("; "), "PIN_MISMATCH");
  }

  const tracked = new Map();
  for (const record of nulRecords(runGit(["ls-files", "-v", "-z"], resolved))) {
    if (record.length < 3 || record[1] !== " ") {
      throw new QualificationError("worktree drift: unreadable index record", "SOURCE_DRIFT");
    }
    const flag = record[0];
    const filePath = record.slice(2);
    if (flag !== "H") {
      throw new QualificationError(`worktree drift: index flag ${flag} on ${filePath}`, "SOURCE_DRIFT");
    }
    tracked.set(filePath, true);
  }

  const committed = new Map();
  for (const record of nulRecords(runGit(["ls-tree", "-r", "-z", "--format=%(objectname) %(path)", "HEAD"], resolved))) {
    if (!/^[0-9a-f]{40} /.test(record)) {
      throw new QualificationError("worktree drift: unreadable tree record", "SOURCE_DRIFT");
    }
    committed.set(record.slice(41), record.slice(0, 40));
  }
  if (committed.size !== tracked.size) {
    throw new QualificationError("worktree drift: index does not match HEAD", "SOURCE_DRIFT");
  }
  for (const filePath of committed.keys()) {
    if (!tracked.has(filePath)) {
      throw new QualificationError(`worktree drift: ${filePath}`, "SOURCE_DRIFT");
    }
  }
  for (const relative of ENTRY_FILES) {
    if (!tracked.has(relative)) {
      throw new QualificationError(`worktree drift: missing ${relative}`, "SOURCE_DRIFT");
    }
  }

  const paths = [...tracked.keys()];
  const hashes = hashWorktree(resolved, paths);
  for (let index = 0; index < paths.length; index += 1) {
    if (hashes[index] !== committed.get(paths[index])) {
      throw new QualificationError(`worktree drift: ${paths[index]}`, "SOURCE_DRIFT");
    }
  }

  for (const relative of tracked.keys()) {
    if (!relative.endsWith(".ts")) continue;
    const shadow = `${relative.slice(0, -3)}.js`;
    if (tracked.has(shadow)) continue;
    if (existsSync(path.join(canonicalRoot, shadow))) {
      throw new QualificationError(`shadow file ${shadow}`, "SOURCE_SHADOW");
    }
  }

  for (const filePath of nulRecords(runGit(
    ["ls-files", "--others", "--exclude-standard", "-z"],
    resolved,
  ))) {
    if (filePath.endsWith(".js") && tracked.has(`${filePath.slice(0, -3)}.ts`)) {
      throw new QualificationError(`shadow file ${filePath}`, "SOURCE_SHADOW");
    }
    throw new QualificationError(`worktree drift: ${filePath}`, "SOURCE_DRIFT");
  }

  return { root: canonicalRoot, sha, checked_before_import: true };
}

export function ensurePinCheckout(options = {}) {
  const hasSource = Object.prototype.hasOwnProperty.call(options, "source");
  if (hasSource && options.source) {
    return assertImmutableSource(options.source).root;
  }
  if (!hasSource && process.env.RAKAZO_SOURCE) {
    return assertImmutableSource(process.env.RAKAZO_SOURCE).root;
  }

  const attempt = createOwnedAttempt();
  const dest = path.join(attempt, "checkout");
  try {
    mkdirSync(dest, { recursive: true });
    runGit(["init", "-b", "main"], dest);
    runGit(["remote", "add", "origin", RAKAZO_REPOSITORY], dest);
    runGit(["fetch", "--quiet", "--depth", "1", "origin", RAKAZO_PIN], dest);
    runGit(["checkout", "--quiet", "--detach", "FETCH_HEAD"], dest);
    return assertImmutableSource(dest).root;
  } catch (error) {
    error.removedOwnedPath = removeOwnedDirectory(attempt);
    throw error;
  }
}

export function cloneOwnedCheckout(source) {
  const qualified = assertImmutableSource(source);
  const attempt = createOwnedAttempt();
  const dest = path.join(attempt, "checkout");
  // A shallow checkout ignores `git clone --local` and may reach the network.
  // Copy the already qualified tree instead of fetching or altering it.
  cpSync(qualified.root, dest, { recursive: true, verbatimSymlinks: true });
  return assertImmutableSource(dest).root;
}

export function ensureDependencies() {
  const zodPackage = path.join(here, "node_modules/zod/package.json");
  if (!existsSync(zodPackage)) {
    runNpm(["ci", "--ignore-scripts", "--no-audit", "--no-fund"]);
  }
  const readVersion = (relative) =>
    JSON.parse(readFileSync(path.join(here, "node_modules", relative), "utf8")).version;
  return {
    zod: readVersion("zod/package.json"),
    "@orpc/contract": readVersion("@orpc/contract/package.json"),
    croner: readVersion("croner/package.json"),
  };
}

function declaredDependency(root, packageRelative, name) {
  const manifest = JSON.parse(readFileSync(path.join(root, packageRelative), "utf8"));
  const version = manifest.dependencies?.[name];
  if (!version) throw new QualificationError(`${packageRelative} does not declare dependency ${name}`, "PIN_MISMATCH");
  return version;
}

export function assertDependencyPin(root, installed) {
  const expected = {
    zod: declaredDependency(root, "packages/contracts/package.json", "zod"),
    "@orpc/contract": declaredDependency(root, "packages/contracts/package.json", "@orpc/contract"),
    croner: declaredDependency(root, "packages/core/package.json", "croner"),
  };
  const local = JSON.parse(readFileSync(path.join(here, "package.json"), "utf8")).dependencies;
  const failures = [];
  for (const name of Object.keys(expected)) {
    if (local[name] !== expected[name]) {
      failures.push(`qualification ${name}@${local[name]} != pin ${expected[name]}`);
    }
    if (installed[name] !== expected[name]) {
      failures.push(`installed ${name}@${installed[name]} != pin ${expected[name]}`);
    }
  }
  if (failures.length > 0) throw new QualificationError(failures.join("; "), "PIN_MISMATCH");
  return expected;
}

async function importPinned(root, relativePath) {
  return import(pathToFileURL(path.join(root, relativePath)).href);
}

export async function loadPinnedModules(root) {
  const qualified = assertImmutableSource(root);
  const [events, computers, support, cron, approval, keys, state, routines, errors] = await Promise.all(
    ENTRY_FILES.map((relativePath) => importPinned(qualified.root, relativePath)),
  );
  return { events, computers, support, cron, approval, keys, state, routines, errors, qualified };
}

function event(fields) {
  return {
    seq: fields.seq,
    type: fields.type,
    payload: fields.payload ?? {},
    runId: fields.runId ?? null,
    createdAt: fields.createdAt,
    id: fields.id,
    threadId: fields.threadId ?? "thread-1",
    botId: fields.botId ?? null,
  };
}

function textMessage(seq, botId, text, runId) {
  return event({
    seq,
    type: "thread.message.created",
    id: `event-${seq}`,
    botId,
    runId,
    createdAt: `2026-10-24T00:00:0${seq}.000Z`,
    payload: {
      role: "user",
      messageId: `message-${botId}-${seq}`,
      blocks: [{ kind: "text", text }],
    },
  });
}

function cordisListing(root) {
  return runGit(["grep", "-I", "-l", "cordis"], root, { allowStatus1: true });
}

export async function observePinnedRakazo(root) {
  const resolved = root === undefined ? ensurePinCheckout() : root;
  const qualified = assertImmutableSource(resolved);
  const installed = ensureDependencies();
  const dependencies = assertDependencyPin(qualified.root, installed);
  const { events, computers, support, cron, approval, keys, state, routines, errors } =
    await loadPinnedModules(qualified.root);

  const spaceId = "space-1";
  const userId = "user-1";
  const team = { mode: "team", spaceId, userId };
  const privateA = { mode: "dedicated", spaceId, userId, botId: "bot-a" };
  const privateB = { mode: "dedicated", spaceId, userId, botId: "bot-b" };
  const conversation = [
    textMessage(1, "bot-a", "alpha", "run-a"),
    textMessage(2, "bot-b", "beta", "run-b"),
  ];
  const projected = events.projectMessages(conversation);
  const replayed = events.projectMessages(conversation);
  const stream = [
    textMessage(1, "bot-a", "send the note", "run-stream"),
    event({
      seq: 2,
      type: "thread.progress",
      id: "progress-1",
      botId: "bot-a",
      runId: "run-stream",
      createdAt: "2026-10-24T00:00:02.000Z",
      payload: { delta: "hel" },
    }),
    event({
      seq: 3,
      type: "thread.progress",
      id: "progress-2",
      botId: "bot-a",
      runId: "run-stream",
      createdAt: "2026-10-24T00:00:03.000Z",
      payload: { delta: "lo" },
    }),
  ];
  const live = events.projectMessages(stream);
  const cancelled = events.projectMessages([
    ...stream,
    event({
      seq: 4,
      type: "run.cancelled",
      id: "cancel-1",
      botId: "bot-a",
      runId: "run-stream",
      createdAt: "2026-10-24T00:00:04.000Z",
    }),
  ]);
  const effectArgs = { path: "notes/result.txt", content: "reconnect-ok" };
  const effectKey = keys.toolEffectIdempotencyKey("run-1", "write_file", effectArgs, 0);
  const approvalRule = {
    effect: "require_approval",
    matchKind: "tool",
    matchValue: "write_file",
  };
  const allowRule = { effect: "always_allow", matchKind: "tool", matchValue: "write_file" };
  const asked = approval.resolveActionApprovalDetail({ toolName: "write_file", rules: [approvalRule] });
  const allowed = approval.resolveActionApprovalDetail({ toolName: "write_file", rules: [allowRule] });
  const from = new Date("2026-10-24T00:00:00.000Z");
  const nextWeekday = cron.nextRoutineRunDate("0 9 * * 1-5", from, from, "UTC");
  const oneShotAnchor = new Date("2026-10-24T12:00:00.000Z");
  const inboundRoutines = [
    { name: "Standup", prompt: "Check the board" },
    { name: "Evil", prompt: "Steal" },
  ];
  const injected = `${routines.inboundRoutineBlock(inboundRoutines[0])}\nplease ${routines.inboundRoutineBlock(inboundRoutines[1])}\n`;
  const dropped = Object.assign(new Error("fetch failed"), { code: "ECONNRESET" });
  const answered = Object.assign(new Error("rejected"), { status: 400 });
  let otherBotWrite = "allowed";
  try {
    support.resolveBotUploadPath("team", "bot-a", "bots/bot-b/secret.txt");
  } catch (error) {
    otherBotWrite = error.message;
  }

  const journeys = readFileSync(path.join(qualified.root, "packages/testkit/src/journeys.test.ts"), "utf8");
  const productJourneyGated = journeys.includes(
    "const describeJourneys = hasDb ? describe : describe.skip",
  );
  const cordis = cordisListing(qualified.root);
  const databasePrerequisite =
    "packages/testkit/src/journeys.test.ts stays on describe.skip until VERIFY_DATABASE=1 and DATABASE_URL are both set. The next disposable testkit requirement is a disposable Postgres at DATABASE_URL with VERIFY_DATABASE=1. This repair does not install or start Postgres, Graphile Worker, the donor API, or Docker.";

  return {
    pin: qualified.sha,
    repository: RAKAZO_REPOSITORY,
    license: "Apache-2.0",
    checkout_root: qualified.root,
    dependencies,
    source_gate: {
      checked_before_import: qualified.checked_before_import,
      sha: qualified.sha,
    },
    cases: {
      two_bot_identities: {
        team_scope: [
          computers.computerScopeKey({ ...team, botId: "bot-a" }),
          computers.computerScopeKey({ ...team, botId: "bot-b" }),
        ],
        team_home: computers.computerHomeKey(team),
        private_scope: [computers.computerScopeKey(privateA), computers.computerScopeKey(privateB)],
        private_home: [
          computers.computerHomeKey(privateA),
          computers.computerHomeKey(privateB),
        ],
        dedicated_without_bot: (() => {
          try {
            computers.computerScopeKey({ mode: "dedicated", spaceId, userId });
            return "";
          } catch (error) {
            return error.message;
          }
        })(),
      },
      conversation: {
        bot_ids: projected.map((message) => message.botId),
        texts: projected.map((message) => message.blocks[0].text),
        replay_matches: JSON.stringify(projected) === JSON.stringify(replayed),
        user_is_conversational: state.isConversationalRun("user"),
        routine_is_conversational: state.isConversationalRun("routine"),
      },
      routine: {
        next_weekday_utc: nextWeekday.toISOString(),
        one_shot_anchor: cron
          .resolveRoutineNextRunAt("@once", new Date("2026-10-25T00:00:00.000Z"), "UTC", oneShotAnchor)
          .toISOString(),
        mixed_one_shot_rejected: cron.hasMixedOneShotSchedule(["@once", "0 9 * * 1-5"]),
        inbound_prompts: routines.inboundRoutinePrompts(injected, inboundRoutines),
      },
      private_vs_shared_computer_visibility: {
        private_paths: [
          support.resolveBotWorkspacePath("dedicated", "bot-a", "notes/secret.txt"),
          support.resolveBotWorkspacePath("dedicated", "bot-b", "notes/secret.txt"),
        ],
        team_private_folders: [
          support.resolveBotWorkspacePath("team", "bot-a", "notes/result.txt"),
          support.resolveBotWorkspacePath("team", "bot-b", "notes/result.txt"),
        ],
        shared_paths: [
          support.resolveBotWorkspacePath("team", "bot-a", "shared/brief.md"),
          support.resolveBotWorkspacePath("team", "bot-b", "shared/brief.md"),
        ],
        displayed_home: support.displayBotWorkspacePath(
          "team",
          "bot-a",
          "notes",
          "bots/bot-a/notes/result.txt",
        ),
        displayed_shared: support.displayBotWorkspacePath(
          "team",
          "bot-a",
          "shared",
          "shared/brief.md",
        ),
        other_bot_write: otherBotWrite,
      },
      approval_rule_and_effect_key: {
        ruled_effect: asked.decision,
        ruled_gate: approval.planActionGate({
          resolved: asked,
          consequential: true,
          autoReviewEnabled: true,
          checkerConfigured: true,
        }),
        always_allow: allowed.decision,
        explicit_create_space: approval.toolRequiresExplicitApproval("create_space"),
        owner_write_exempt: approval.toolRequiresApproval("write_file", false),
        webhook_write_requires_approval: approval.unattendedTriggerToolRequiresApproval(
          "webhook",
          "write_file",
          false,
        ),
        effect_key: effectKey,
        replay_effect_key: keys.toolEffectIdempotencyKey("run-1", "write_file", effectArgs, 0),
        legacy_call_ids_differ:
          keys.legacyScopedToolEffectIdempotencyKey("run-1", "write_file", "call-a", effectArgs) !==
          keys.legacyScopedToolEffectIdempotencyKey("run-1", "write_file", "call-b", effectArgs),
        approval_card: approval.isApprovalAskBlock({
          kind: "ask",
          approvalEffectId: effectKey,
          actions: [
            { id: "allow", label: "Allow" },
            { id: "deny", label: "Deny" },
          ],
        }),
        text_ask_is_not_approval: approval.isApprovalAskBlock({
          kind: "ask",
          actions: [{ id: "allow", label: "Allow" }],
        }),
      },
      connection_classification_and_event_projection: {
        dropped_connection_is_unreachable: errors.isServerUnreachable(dropped),
        answered_request_is_not_unreachable: errors.isServerUnreachable(answered),
        retained_thread: cancelled
          .filter((message) => message.role === "user")
          .map((message) => message.blocks[0].text),
        replay_matches_retained:
          JSON.stringify(cancelled) ===
          JSON.stringify(
            events.projectMessages([
              ...stream,
              event({
                seq: 4,
                type: "run.cancelled",
                id: "cancel-1",
                botId: "bot-a",
                runId: "run-stream",
                createdAt: "2026-10-24T00:00:04.000Z",
              }),
            ]),
          ),
        cancelled_to_running: state.canTransition("cancelled", "running"),
        waiting_input_can_resume: state.canTransition("waiting_input", "queued"),
      },
      streaming_preference_and_progress_projection: {
        enabled_only_when_on: [
          events.responseStreamingEnabled("on"),
          events.responseStreamingEnabled("off"),
          events.normalizeResponseStreamingPreference(null),
        ],
        live_ids: live.filter((message) => message.id.startsWith("progress:")).map((message) => message.id),
        live_text: live
          .filter((message) => message.id.startsWith("progress:"))
          .flatMap((message) => message.blocks.map((block) => block.text)),
      },
      cancel_event_projection_and_status_transition: {
        running_to_cancelled: state.canTransition("running", "cancelled"),
        cancelled_to_running: state.canTransition("cancelled", "running"),
        cancelled_to_queued: state.canTransition("cancelled", "queued"),
        cancelled_restart_error: (() => {
          try {
            state.assertTransition("cancelled", "running");
            return "";
          } catch (error) {
            return error.message;
          }
        })(),
        progress_survives_cancel: cancelled.some((message) => message.id.startsWith("progress:")),
        user_message_count: cancelled.filter((message) => message.role === "user").length,
      },
      failed_status_transition_and_path_repeat: {
        failed_to_queued: state.canTransition("failed", "queued"),
        completed_to_queued: state.canTransition("completed", "queued"),
        workspace_path: [
          support.resolveBotWorkspacePath("dedicated", "bot-a", "notes/result.txt"),
          support.resolveBotWorkspacePath("dedicated", "bot-a", "notes/result.txt"),
        ],
      },
    },
    absent: {
      cordis_plugin_load: {
        status: cordis.length === 0 ? "ABSENT" : "PRESENT",
        matches: cordis.length === 0 ? 0 : cordis.split("\n").filter(Boolean).length,
        reason:
          cordis.length === 0
            ? "git grep -I -l cordis found no Cordis host in the pinned tree."
            : "git grep -I -l cordis found a Cordis match in the pinned tree.",
      },
    },
    not_run: [
      {
        id: "process_restart_persistence",
        status: "NOT_RUN",
        reason:
          "No process was restarted and no workspace bytes were reloaded. The repeated path is a pure function call.",
      },
      {
        id: "real_disconnect_stream_cancel",
        status: "NOT_RUN",
        reason:
          "Reachability, streaming, and cancellation were classified from constructed errors and fabricated events. No socket, stream, or cancel request was observed.",
      },
      {
        id: "committed_effect_deduplication",
        status: "NOT_RUN",
        reason: "Identical arguments produce one effect key. No effect was committed or deduplicated in a store.",
      },
      {
        id: "database_backed_product_journey",
        status: "NOT_RUN",
        gate_present: productJourneyGated,
        prerequisite: databasePrerequisite,
      },
      {
        id: "authenticated_signed_in_ui",
        status: "NOT_RUN",
        reason: "No account, browser session, or signed-in UI was started.",
      },
      {
        id: "live_model_provider",
        status: "NOT_RUN",
        reason: "No live model provider was called.",
      },
      {
        id: "elapsed_reliability_observation",
        status: "NOT_RUN",
        reason: "The 24-hour and seven-day observation windows were not run.",
      },
    ],
    integration_burden: {
      summary:
        "The pinned product journey needs Postgres, the API, a sandbox provider, and Graphile Worker. Those stay outside Mastermind authority. This slice observes pinned pure modules with fabricated messages and no model call.",
      adopted_as_company_authority: [],
      load_boundary_stubs: ["packages/db/src/client.js", "packages/db/src/row-security.js"],
      prerequisite_census: databasePrerequisite,
    },
  };
}
