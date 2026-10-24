import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

export const RAKAZO_PIN = "c5e66e010ee3f3166d2ad216f928a75a0b9a2218";
export const RAKAZO_REPOSITORY = "https://github.com/elie222/rakazo.git";

const here = path.dirname(fileURLToPath(import.meta.url));

const REAL_SOURCE = {
  computerScopeKey: "team:${input.spaceId}:${input.userId}",
  resolveActionApproval: "resolveActionApprovalDetail",
  projectMessages: "thread.message.created",
  nextRoutineRunDate: "nextCronDate",
};

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

function git(args, cwd) {
  return execFileSync("git", args, {
    cwd,
    encoding: "utf8",
    env: { ...process.env, GIT_TERMINAL_PROMPT: "0" },
  }).trim();
}

function readIdentity(root, sha) {
  const licenseText = readFileSync(path.join(root, "LICENSE"), "utf8");
  const packageLicense = JSON.parse(readFileSync(path.join(root, "package.json"), "utf8")).license;
  return qualifyPinIdentity({ sha, licenseText, packageLicense });
}

export function ensurePinCheckout() {
  const requested = process.env.RAKAZO_SOURCE;
  if (requested) {
    const sha = git(["rev-parse", "HEAD"], requested);
    const identity = readIdentity(requested, sha);
    if (!identity.ok) {
      throw new Error(`RAKAZO_SOURCE refused: ${identity.failures.join("; ")}`);
    }
    return requested;
  }

  const dest = path.join(tmpdir(), `rakazo-pin-${RAKAZO_PIN}`);
  let sha = "";
  if (existsSync(path.join(dest, ".git"))) {
    try {
      sha = git(["rev-parse", "HEAD"], dest);
    } catch {
      sha = "";
    }
  }
  if (sha !== RAKAZO_PIN) {
    rmSync(dest, { recursive: true, force: true });
    mkdirSync(dest, { recursive: true });
    git(["init", "-b", "main"], dest);
    git(["remote", "add", "origin", RAKAZO_REPOSITORY], dest);
    git(["fetch", "--quiet", "--depth", "1", "origin", RAKAZO_PIN], dest);
    git(["checkout", "--quiet", "--detach", "FETCH_HEAD"], dest);
    sha = git(["rev-parse", "HEAD"], dest);
  }
  const identity = readIdentity(dest, sha);
  if (!identity.ok) {
    throw new Error(`pinned checkout refused: ${identity.failures.join("; ")}`);
  }
  return dest;
}

export function ensureDependencies() {
  const zodPackage = path.join(here, "node_modules/zod/package.json");
  if (!existsSync(zodPackage)) {
    execFileSync("npm", ["ci", "--ignore-scripts", "--no-audit", "--no-fund"], {
      cwd: here,
      encoding: "utf8",
      env: { ...process.env, GIT_TERMINAL_PROMPT: "0" },
    });
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
  if (!version) throw new Error(`${packageRelative} does not declare dependency ${name}`);
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
  if (failures.length > 0) throw new Error(failures.join("; "));
  return expected;
}

async function importPinned(root, relativePath) {
  process.env.RAKAZO_PIN_ROOT = root;
  return import(pathToFileURL(path.join(root, relativePath)).href);
}

export async function loadPinnedModules(root) {
  const [events, computers, support, cron, approval, keys, state, routines, errors] =
    await Promise.all([
      importPinned(root, "packages/core/src/events.ts"),
      importPinned(root, "packages/db/src/computers.ts"),
      importPinned(root, "packages/adapters/src/computer-support.ts"),
      importPinned(root, "packages/core/src/cron.ts"),
      importPinned(root, "packages/core/src/action-approval.ts"),
      importPinned(root, "packages/core/src/approval-effect-key.ts"),
      importPinned(root, "packages/core/src/run-state.ts"),
      importPinned(root, "packages/core/src/inbound-routine.ts"),
      importPinned(root, "packages/core/src/user-error.ts"),
    ]);
  const loaded = { events, computers, support, cron, approval, keys, state, routines, errors };
  for (const [name, marker] of Object.entries(REAL_SOURCE)) {
    const owner =
      name === "computerScopeKey"
        ? computers
        : name === "resolveActionApproval"
          ? approval
          : name === "projectMessages"
            ? events
            : cron;
    const source = owner[name].toString();
    if (!source.includes(marker)) {
      throw new Error(`loaded ${name} is not the pinned Rakazo function`);
    }
  }
  return loaded;
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
  try {
    return git(["grep", "-I", "-l", "cordis"], root);
  } catch (error) {
    if (error.status === 1) return "";
    throw error;
  }
}

export async function observePinnedRakazo(root = ensurePinCheckout()) {
  const installed = ensureDependencies();
  const dependencies = assertDependencyPin(root, installed);
  const modules = await loadPinnedModules(root);
  const sha = git(["rev-parse", "HEAD"], root);
  const identity = readIdentity(root, sha);
  if (!identity.ok) throw new Error(identity.failures.join("; "));

  const { events, computers, support, cron, approval, keys, state, routines, errors } = modules;
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

  const journeys = readFileSync(path.join(root, "packages/testkit/src/journeys.test.ts"), "utf8");
  const productJourneyGated = journeys.includes(
    "const describeJourneys = hasDb ? describe : describe.skip",
  );
  const cordis = cordisListing(root);

  return {
    pin: sha,
    repository: RAKAZO_REPOSITORY,
    license: "Apache-2.0",
    dependencies,
    real_function_markers: REAL_SOURCE,
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
      effect_approval: {
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
      disconnect_recovery: {
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
      streaming: {
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
      cancellation_without_replay: {
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
      restart_persistence: {
        failed_to_queued: state.canTransition("failed", "queued"),
        completed_to_queued: state.canTransition("completed", "queued"),
        workspace_path: [
          support.resolveBotWorkspacePath("dedicated", "bot-a", "notes/result.txt"),
          support.resolveBotWorkspacePath("dedicated", "bot-a", "notes/result.txt"),
        ],
      },
    },
    unsupported: [
      {
        id: "cordis_plugin_load",
        observed: cordis.length === 0 ? "absent" : "present",
        reason:
          "Pinned Rakazo has no Cordis plugin host. MCP contract modules are not loaded or executed as a plugin runtime in this slice.",
      },
      {
        id: "postgres_graphile_product_journey",
        observed: productJourneyGated ? "database-gated" : "ungated",
        reason:
          "packages/testkit/src/journeys.test.ts runs only when VERIFY_DATABASE=1 and DATABASE_URL are set. This qualification does not start Postgres, Graphile Worker, Docker, or the donor API, and does not adopt them as company authority.",
      },
      {
        id: "authenticated_signed_in_ui",
        observed: "not-run",
        reason: "No account, browser session, credential, or production service is started.",
      },
    ],
    integration_burden: {
      summary:
        "The pinned product journey needs Postgres, the API, a sandbox provider, and Graphile Worker. Those stay outside Mastermind authority. This slice observes the pinned pure modules with mock messages and no model call.",
      adopted_as_company_authority: [],
      load_boundary_stubs: [
        "packages/db/src/client.js",
        "packages/db/src/row-security.js",
      ],
      missing_proof: [
        "authenticated signed-in UI",
        "database-backed product journeys",
        "Cordis plugin load",
        "live model provider",
        "24-hour and seven-day observation",
      ],
    },
  };
}
