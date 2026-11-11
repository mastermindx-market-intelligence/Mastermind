/**
 * Focused cross-language producer → consumer glue test.
 *
 * Two mutually exclusive modes, selected only by the caller environment:
 *
 * 1. Fresh external gate — WINDOW_MISSION_FIXTURE_PATH is present in the
 *    caller environment. The suite then reads exactly that absolute file with
 *    the real Node filesystem, runs the production decoders
 *    (decodeMissionv3, decodeWindow) and observedMissionAssociation on it
 *    using the selection carried inside the file, and reports what it
 *    consumed on stdout so the calling process can verify real consumption.
 *    A present-but-empty, missing, unreadable, malformed or non-conforming
 *    explicit input fails this process; the committed export is never
 *    substituted for the supplied file.
 * 2. Committed replay — the key is absent (an ordinary `vitest run`). The
 *    committed producer export is decoded as regression coverage, together
 *    with test-local negatives for the production rejection paths and for
 *    the mode contract itself.
 *
 * The Node filesystem module is really imported and really read; nothing in
 * this file mocks or replaces it. Because this project ships no @types/node,
 * the built-in specifier is declared once below, inside this test file only.
 */
import { describe, expect, it } from "vitest";

import { decodeMissionv3 } from "./mission";
import { decodeWindow, observedMissionAssociation } from "./workspace-contract";
import committedFixtureJson from "./fixtures/window-mission-association-producer.json";

// ---------------------------------------------------------------------------
// Caller contract
// ---------------------------------------------------------------------------

const FRESH_ENV_KEY = "WINDOW_MISSION_FIXTURE_PATH";

/** The producer DTO shape shared by the fresh file and the committed export. */
interface ProducerDocument {
  mission: unknown;
  window: unknown;
  selection: { work_ref: string; root_job_id: string };
}

/** Structural view of the caller environment (no @types/node in this project). */
type CallerEnv = { readonly [key: string]: string | undefined };

const callerEnv = (globalThis as { process?: { env?: CallerEnv } }).process
  ?.env;

type FreshGate = { mode: "fresh"; path: string } | { mode: "replay" };

/**
 * A present key means fresh mode, even for an unusable value: an explicitly
 * supplied empty path must fail the process instead of silently degrading to
 * the committed export. Only a genuinely absent key is replay mode. The
 * caller environment is read once and never mutated or overridden.
 */
function resolveFreshGate(env: CallerEnv | undefined): FreshGate {
  if (!env || env[FRESH_ENV_KEY] === undefined) return { mode: "replay" };
  const path = env[FRESH_ENV_KEY];
  if (!path.trim()) {
    throw new Error(
      `${FRESH_ENV_KEY} is set but empty: an explicit fresh path must name a real file, not fall back to the committed export`,
    );
  }
  return { mode: "fresh", path };
}

const GATE = resolveFreshGate(callerEnv);

// ---------------------------------------------------------------------------
// Real filesystem access
// ---------------------------------------------------------------------------

interface NodeFsPromises {
  readFile(path: string, encoding: "utf8"): Promise<string>;
}

async function realFs(): Promise<NodeFsPromises> {
  // Localized test-only declaration: this project ships no @types/node, so
  // the Node built-in specifier has no static type here. The real module is
  // loaded and used; no mock or replacement of it exists in this file.
  // @ts-expect-error node:fs/promises is resolved by the vitest worker.
  return (await import("node:fs/promises")) as NodeFsPromises;
}

async function readExternalRaw(path: string): Promise<string> {
  // Propagates ENOENT/EACCES: an unreadable explicit input fails the process
  // instead of degrading to any other source.
  return (await realFs()).readFile(path, "utf8");
}

function parseExternalDocument(raw: string): ProducerDocument {
  const parsed = JSON.parse(raw) as unknown;
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("producer document is not a JSON object");
  }
  const candidate = parsed as Record<string, unknown>;
  const selection = candidate.selection;
  if (
    candidate.mission === undefined ||
    candidate.window === undefined ||
    typeof selection !== "object" ||
    selection === null ||
    typeof (selection as Record<string, unknown>).work_ref !== "string" ||
    typeof (selection as Record<string, unknown>).root_job_id !== "string"
  ) {
    throw new Error(
      "producer document does not carry mission, window and selection",
    );
  }
  const known = selection as { work_ref: string; root_job_id: string };
  return {
    mission: candidate.mission,
    window: candidate.window,
    selection: {
      work_ref: known.work_ref,
      root_job_id: known.root_job_id,
    },
  };
}

async function loadExternalDocument(path: string): Promise<ProducerDocument> {
  return parseExternalDocument(await readExternalRaw(path));
}

// ---------------------------------------------------------------------------
// Shared positive: the production decoders run on a producer DTO using that
// DTO's own selection, mapped to the established camelCase consumer API.
// ---------------------------------------------------------------------------

async function assertProducerAssociation(
  document: ProducerDocument,
): Promise<{
  missionSchema: string;
  windowSchema: string;
  workRef: string;
  rootJobId: string;
  jobId: string;
  attemptId: string;
}> {
  const selection = {
    workRef: document.selection.work_ref,
    rootJobId: document.selection.root_job_id,
  };
  const mission = decodeMissionv3(document.mission, selection);
  if (!mission) {
    throw new Error(
      `decodeMissionv3 rejected the producer mission for ${selection.workRef}/${selection.rootJobId}`,
    );
  }
  const window = await decodeWindow(document.window);
  if (!window) throw new Error("decodeWindow rejected the producer window");
  if (window.schema !== "mastermind.workspace.window_read_candidate.v2") {
    throw new Error("producer window is not a v2 observation window");
  }
  const association = observedMissionAssociation(window, mission, selection);
  if (!association) {
    throw new Error("observedMissionAssociation rejected the observed pair");
  }
  expect(association.state).toBe("OBSERVED_MISSION_ASSOCIATION");
  expect(association.job_id).toBe(window.observation_binding.job_id);
  expect(association.attempt_id).toBe(window.observation_binding.attempt_id);
  return {
    missionSchema: mission.schema,
    windowSchema: window.schema,
    workRef: selection.workRef,
    rootJobId: selection.rootJobId,
    jobId: association.job_id,
    attemptId: association.attempt_id,
  };
}

// ---------------------------------------------------------------------------
// Real-consumption receipt for the calling process
// ---------------------------------------------------------------------------

async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(text),
  );
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function emitConsumptionReport(report: Record<string, unknown>): void {
  const stdout = (
    globalThis as { process?: { stdout?: { write(chunk: string): void } } }
  ).process?.stdout;
  if (!stdout) {
    throw new Error("no process stdout to report fresh consumption on");
  }
  stdout.write(`FRESH_CONSUMED ${JSON.stringify(report)}\n`);
}

// ---------------------------------------------------------------------------
// Suites
// ---------------------------------------------------------------------------

describe("mission-window-producer consumer glue", () => {
  describe.skipIf(GATE.mode !== "fresh")(
    "fresh external producer gate",
    { timeout: 120_000 },
    () => {
      it("consumes exactly the externally supplied producer DTO", async () => {
        if (GATE.mode !== "fresh") throw new Error("fresh gate required");
        const raw = await readExternalRaw(GATE.path);
        const document = parseExternalDocument(raw);
        const found = await assertProducerAssociation(document);
        emitConsumptionReport({
          path: GATE.path,
          sha256: await sha256Hex(raw),
          selection: {
            work_ref: document.selection.work_ref,
            root_job_id: document.selection.root_job_id,
          },
          association: { job_id: found.jobId, attempt_id: found.attemptId },
          mission_schema: found.missionSchema,
          window_schema: found.windowSchema,
        });
      });
    },
  );

  describe.skipIf(GATE.mode === "fresh")(
    "committed producer export replay",
    () => {
      const COMMITTED = committedFixtureJson as ProducerDocument;

      const committedSelection = () => ({
        workRef: COMMITTED.selection.work_ref,
        rootJobId: COMMITTED.selection.root_job_id,
      });

      it("decodes mission v3 from the static producer export", () => {
        const mission = decodeMissionv3(
          COMMITTED.mission,
          committedSelection(),
        );
        expect(mission).not.toBeNull();
        expect(mission?.schema).toBe("mastermind.mission_workspace.v3");
      });

      it("decodes the companion window from the static producer export", async () => {
        const decoded = await decodeWindow(COMMITTED.window);
        expect(decoded).not.toBeNull();
        expect(decoded?.schema).toBe(
          "mastermind.workspace.window_read_candidate.v2",
        );
      });

      it("associates mission + window from the static producer export", async () => {
        await assertProducerAssociation(COMMITTED);
      });

      it("keeps the mode contract: absent key replays, empty key fails", () => {
        expect(resolveFreshGate(undefined)).toEqual({ mode: "replay" });
        expect(resolveFreshGate({})).toEqual({ mode: "replay" });
        expect(resolveFreshGate({ OTHER_KEY: "value" })).toEqual({
          mode: "replay",
        });
        expect(
          resolveFreshGate({ [FRESH_ENV_KEY]: "supplied/other.json" }),
        ).toEqual({ mode: "fresh", path: "supplied/other.json" });
        expect(() => resolveFreshGate({ [FRESH_ENV_KEY]: "" })).toThrow(
          /empty/,
        );
        expect(() => resolveFreshGate({ [FRESH_ENV_KEY]: "   " })).toThrow(
          /empty/,
        );
      });

      it("rejects an absent fresh file instead of degrading", async () => {
        const absent = new URL(
          "./absent-fresh-fixture-do-not-create.json",
          import.meta.url,
        ).pathname;
        await expect(loadExternalDocument(absent)).rejects.toThrow();
      });

      it("rejects a malformed fresh payload instead of degrading", () => {
        expect(() => parseExternalDocument("")).toThrow();
        expect(() => parseExternalDocument("{ this is not json")).toThrow();
        expect(() => parseExternalDocument(JSON.stringify([]))).toThrow();
        expect(() =>
          parseExternalDocument(JSON.stringify({ mission: {} })),
        ).toThrow();
      });

      it("rejects a nonconforming mission schema", () => {
        const forged = {
          ...(COMMITTED.mission as Record<string, unknown>),
          schema: "mastermind.mission_workspace.v2",
        };
        expect(decodeMissionv3(forged, committedSelection())).toBeNull();
      });

      it("rejects a forged owner observation receipt", () => {
        const mission = COMMITTED.mission as Record<string, unknown>;
        const source = mission.source as Record<string, unknown>;
        const observation = source.owner_observation as Record<
          string,
          unknown
        >;
        const forged = {
          ...mission,
          source: {
            ...source,
            owner_observation: {
              ...observation,
              selection: {
                work_ref: COMMITTED.selection.work_ref,
                root_job_id: "JOB-999999999",
              },
            },
          },
        };
        expect(decodeMissionv3(forged, committedSelection())).toBeNull();
      });

      it("rejects a replaced observation binding attempt", async () => {
        const selection = committedSelection();
        const mission = decodeMissionv3(COMMITTED.mission, selection);
        expect(mission).not.toBeNull();
        const rawWindow = COMMITTED.window as Record<string, unknown>;
        const binding = rawWindow.observation_binding as Record<
          string,
          unknown
        >;
        const replaced = {
          ...rawWindow,
          observation_binding: {
            job_id: binding.job_id,
            attempt_id: `ATT-${"b".repeat(32)}`,
          },
        };
        const decoded = await decodeWindow(replaced);
        expect(decoded).not.toBeNull();
        expect(observedMissionAssociation(decoded, mission, selection)).toBe(
          null,
        );
      });
    },
  );
});
