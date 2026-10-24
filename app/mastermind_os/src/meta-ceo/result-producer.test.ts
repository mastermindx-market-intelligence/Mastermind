/**
 * Office Mission/Result producer → consumer qualification.
 *
 * Two mutually exclusive modes, selected only by the caller environment:
 *
 * 1. Fresh external gate — RESULT_PRODUCER_FIXTURE_DIR is present. The suite
 *    reads exactly that directory with the real Node filesystem and runs
 *    decodeResultBytes, decodeResultEnvelope, decodeMissionv3, and
 *    projectOffice on those bytes. A present-but-empty, missing, unreadable,
 *    or malformed explicit input fails this process. The committed export is
 *    never substituted for the supplied directory.
 * 2. Committed replay — the key is absent. The committed three-file export
 *    beside this test is the subject, labelled replay, with the same consumer
 *    and the acquisition sha256 pins.
 *
 * Root meta-ceo-open-harness-convergence-20261024-sol-001.
 * Parent meta-ceo-harness-implementation-20261024-web-001.
 * Child meta-ceo-harness-office-result-cursor-20261024-01.
 *
 * The Node filesystem module is really imported and really read. Nothing in
 * this file mocks or replaces it. This project ships no @types/node, so the
 * built-in specifier is declared once below, inside this test file only.
 */
import { beforeAll, describe, expect, it } from "vitest";

import { decodeMissionv3, type Missionv3Document } from "../mission";
import {
  RESULT_HTTP_BODY_BYTES,
  decodeResultBytes,
  decodeResultEnvelope,
  type ResultEnvelopeDigestShape,
  type ResultSelection,
} from "../result";
import {
  captureMissionOfficeRead,
  completeMissionOfficeRead,
} from "./mission-adapter";
import {
  projectOffice,
  type OfficeProjection,
  type ProjectionContext,
  type ReadSnapshot,
  type SourceClaim,
} from "./projection";

const FRESH_ENV_KEY = "RESULT_PRODUCER_FIXTURE_DIR";
const FILE_NAMES = [
  "actual-result.json",
  "actual-mission-v3.json",
  "fixture-provenance.json",
] as const;

const PINNED_SHA256 = {
  "actual-result.json":
    "fef28f4611e4d66b8db3f80c9dba8cb7b5247ce9071a2bc3e8aa0e5e16135f4a",
  "actual-mission-v3.json":
    "eec67d2d44fe03c5b060089a3046f6e77f7ec5d60ed30fda5843723b773ac529",
  "fixture-provenance.json":
    "f76459d06520b84bd46ee03eddcc8df9d2b96ec358db755b85bd5de738366d5f",
} as const;

/** Request-scoped identities from the unchanged export. They are not equated. */
const MISSION_RUNTIME_SOURCE_IDENTITY = "21e17d36420f8de07b9f72167c390119";
const RESULT_RUNTIME_SOURCE_IDENTITY = "371a2ea68a30441c37388d21b2513860";

/** Test-owned acquisition clock. It is not an owner timestamp. */
const LOCAL_ACQUIRED_AT = "2026-10-24T20:00:00Z";

type CallerEnv = { readonly [key: string]: string | undefined };
type FreshGate = { mode: "fresh"; path: string } | { mode: "replay" };
type ExportName = (typeof FILE_NAMES)[number];

interface ExportedSelection {
  work_ref: string;
  root_job_id: string;
  job_id: string;
  attempt_id: string;
  result_envelope_digest: string;
}

interface ConsumedExport {
  mode: "fresh" | "replay";
  directory: string;
  hashes: Record<ExportName, string>;
  selection: ExportedSelection;
  mission: Missionv3Document;
  result: ResultEnvelopeDigestShape;
  projection: OfficeProjection;
  missionSnapshot: ReadSnapshot<Missionv3Document>;
  resultSnapshot: ReadSnapshot<ResultEnvelopeDigestShape>;
  context: ProjectionContext;
}

interface NodeFs {
  readFile(path: string): Promise<Uint8Array>;
  writeFile(path: string, data: Uint8Array | string): Promise<void>;
  mkdir(path: string, options: { recursive: true }): Promise<void>;
  mkdtemp(prefix: string): Promise<string>;
}

const callerEnv = (globalThis as { process?: { env?: CallerEnv } }).process
  ?.env;

function resolveFreshGate(env: CallerEnv | undefined): FreshGate {
  if (!env || env[FRESH_ENV_KEY] === undefined) return { mode: "replay" };
  const path = env[FRESH_ENV_KEY];
  if (!path.trim()) {
    throw new Error(
      `${FRESH_ENV_KEY} is set but empty: an explicit fresh directory must name a real export, not fall back to the committed export`,
    );
  }
  return { mode: "fresh", path };
}

const GATE = resolveFreshGate(callerEnv);
const COMMITTED_DIR = new URL("./fixtures/result-producer/", import.meta.url)
  .pathname;

async function realFs(): Promise<NodeFs> {
  // @ts-expect-error node:fs/promises is resolved by the vitest worker.
  return (await import("node:fs/promises")) as NodeFs;
}

function joinPath(dir: string, name: string): string {
  return `${dir.replace(/\/+$/, "")}/${name}`;
}

async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  const digest = await crypto.subtle.digest("SHA-256", copy);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function parseJson(name: string, bytes: Uint8Array): unknown {
  let text: string;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    throw new Error(`${name} is not valid UTF-8`);
  }
  try {
    return JSON.parse(text) as unknown;
  } catch (error) {
    const detail = error instanceof Error ? error.message : "parse failed";
    throw new Error(`${name} is not JSON: ${detail}`);
  }
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function exportedSelection(provenance: unknown): ExportedSelection {
  if (!record(provenance)) {
    throw new Error("fixture-provenance.json is not a JSON object");
  }
  const selection = provenance.selection;
  if (!record(selection)) {
    throw new Error(
      "fixture-provenance.json selection is missing the exported five-key tuple",
    );
  }
  const keys = [
    "work_ref",
    "root_job_id",
    "job_id",
    "attempt_id",
    "result_envelope_digest",
  ] as const;
  const out = {} as ExportedSelection;
  for (const key of keys) {
    const value = selection[key];
    if (typeof value !== "string" || value.length === 0) {
      throw new Error(
        `fixture-provenance.json selection.${key} is missing; refusing to invent a tuple`,
      );
    }
    out[key] = value;
  }
  return out;
}

function resultSelection(selection: ExportedSelection): ResultSelection {
  return {
    workRef: selection.work_ref,
    rootJobId: selection.root_job_id,
    jobId: selection.job_id,
    attemptId: selection.attempt_id,
    resultEnvelopeDigest: selection.result_envelope_digest,
  };
}

function sameSelection(
  wire: ResultEnvelopeDigestShape["selection"],
  selection: ExportedSelection,
): boolean {
  return (
    wire.work_ref === selection.work_ref &&
    wire.root_job_id === selection.root_job_id &&
    wire.job_id === selection.job_id &&
    wire.attempt_id === selection.attempt_id &&
    wire.result_envelope_digest === selection.result_envelope_digest
  );
}

/**
 * Presentation identity of the result's own decoded observation.
 * It is not an owner revision and it is not copied from the Mission.
 */
function resultPresentationClaim(
  result: ResultEnvelopeDigestShape,
  localAcquiredAt: string,
): SourceClaim {
  const observation = result.source_observation;
  const control = observation.control_room;
  const runtime = observation.runtime;
  const validTime =
    /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(localAcquiredAt) &&
    Number.isFinite(Date.parse(localAcquiredAt));
  const qualified =
    result.availability === "AVAILABLE" &&
    observation.state === "SAME" &&
    control !== null &&
    control.document_digest !== null &&
    control.instance_before !== null &&
    control.instance_after !== null &&
    control.publication_before !== null &&
    control.publication_after !== null &&
    runtime !== null &&
    runtime.state === "SAME" &&
    runtime.source_identity !== null &&
    runtime.before !== null &&
    runtime.after !== null &&
    validTime;
  const revision = qualified
    ? `result-source-observation:v1:${JSON.stringify([
        observation.schema,
        observation.selection,
        control.instance_before,
        control.instance_after,
        control.publication_before,
        control.publication_after,
        control.document_digest,
        control.source_validity_digest,
        control.cache_currentness_digest,
        runtime.schema,
        runtime.state,
        runtime.source_identity,
        runtime.before,
        runtime.after,
      ])}`
    : null;
  return {
    owner: "EXECUTIVE_OS",
    ref: qualified ? control.document_digest : null,
    ref_kind: "CONTROL_ROOM_DOCUMENT_DIGEST",
    revision,
    observed_at: validTime ? localAcquiredAt : null,
    observed_at_kind: "LOCAL_ACQUISITION",
    state: qualified ? "CURRENT" : "UNKNOWN",
    coverage: result.availability === "AVAILABLE" ? "COMPLETE" : "INCOMPLETE",
  };
}

async function readExportBytes(
  directory: string,
): Promise<Record<ExportName, Uint8Array>> {
  if (!directory.trim()) {
    throw new Error(
      "fixture directory is empty; refusing to substitute the committed export",
    );
  }
  const fs = await realFs();
  const out = {} as Record<ExportName, Uint8Array>;
  for (const name of FILE_NAMES) {
    const path = joinPath(directory, name);
    const bytes = new Uint8Array(await fs.readFile(path));
    if (bytes.byteLength === 0) {
      throw new Error(
        `${path} is empty; refusing to substitute the committed export`,
      );
    }
    out[name] = bytes;
  }
  return out;
}

async function consumeExport(
  directory: string,
  mode: "fresh" | "replay",
): Promise<ConsumedExport> {
  const bytes = await readExportBytes(directory);
  const hashes = {
    "actual-result.json": await sha256Hex(bytes["actual-result.json"]),
    "actual-mission-v3.json": await sha256Hex(bytes["actual-mission-v3.json"]),
    "fixture-provenance.json": await sha256Hex(
      bytes["fixture-provenance.json"],
    ),
  };
  const selection = exportedSelection(
    parseJson("fixture-provenance.json", bytes["fixture-provenance.json"]),
  );
  const expected = resultSelection(selection);
  const resultValue = parseJson(
    "actual-result.json",
    bytes["actual-result.json"],
  );
  const fromBytes = decodeResultBytes(
    bytes["actual-result.json"],
    RESULT_HTTP_BODY_BYTES,
    expected,
  );
  const fromEnvelope = decodeResultEnvelope(resultValue, expected);
  if (!fromBytes || !fromEnvelope) {
    throw new Error(
      `result decoders rejected the supplied bytes (decodeResultBytes=${fromBytes ? "accepted" : "rejected"}, decodeResultEnvelope=${fromEnvelope ? "accepted" : "rejected"})`,
    );
  }
  expect(fromBytes).toEqual(fromEnvelope);
  if (!sameSelection(fromBytes.selection, selection)) {
    throw new Error(
      "decoded result selection differs from fixture-provenance.json; refusing to choose one",
    );
  }
  const mission = decodeMissionv3(parseJson("actual-mission-v3.json", bytes["actual-mission-v3.json"]), {
    workRef: selection.work_ref,
    rootJobId: selection.root_job_id,
  });
  if (!mission) {
    throw new Error(
      "decodeMissionv3 rejected the supplied mission bytes for the exported selection",
    );
  }

  const base: ProjectionContext = {
    authGeneration: 1,
    selection: { workRef: selection.work_ref, rootJobId: selection.root_job_id },
    sessionRef: null,
    bindingGeneration: null,
    revisions: {
      mission: null,
      programs: null,
      result: null,
      conversation: null,
    },
  };
  const pending = captureMissionOfficeRead(base);
  const missionRead = completeMissionOfficeRead(
    pending,
    base,
    mission,
    LOCAL_ACQUIRED_AT,
  );
  const observedMission = missionRead.kind === "observed" ? missionRead.snapshot.value : null;
  if (missionRead.kind !== "observed" || observedMission?.schema !== "mastermind.mission_workspace.v3") {
    const reason = missionRead.kind === "discarded" ? missionRead.reason : "MISSION_VALUE_ABSENT";
    throw new Error(`mission presentation adapter discarded the export: ${reason}`);
  }
  const resultClaim = resultPresentationClaim(fromBytes, LOCAL_ACQUIRED_AT);
  const context = structuredClone(missionRead.context);
  context.revisions.result = resultClaim.revision;
  const missionSnapshot: ReadSnapshot<Missionv3Document> = {
    context: missionRead.snapshot.context,
    source: missionRead.snapshot.source,
    value: observedMission,
  };
  const resultSnapshot: ReadSnapshot<ResultEnvelopeDigestShape> = {
    context: structuredClone(context),
    source: resultClaim,
    value: structuredClone(fromBytes),
  };
  const projection = projectOffice(
    {
      mission: missionSnapshot,
      programs: null,
      result: resultSnapshot,
      conversation: null,
    },
    context,
  );
  return {
    mode,
    directory,
    hashes,
    selection,
    mission,
    result: fromBytes,
    projection,
    missionSnapshot,
    resultSnapshot,
    context,
  };
}

function projectMutated(
  consumed: ConsumedExport,
  mutate: (
    mission: Missionv3Document,
    result: ResultEnvelopeDigestShape,
  ) => void,
): OfficeProjection {
  const mission = structuredClone(consumed.mission);
  const result = structuredClone(consumed.result);
  mutate(mission, result);
  return projectOffice(
    {
      mission: {
        context: consumed.missionSnapshot.context,
        source: consumed.missionSnapshot.source,
        value: mission,
      },
      programs: null,
      result: {
        context: consumed.resultSnapshot.context,
        source: consumed.resultSnapshot.source,
        value: result,
      },
      conversation: null,
    },
    consumed.context,
  );
}

function expectDecoded(consumed: ConsumedExport): void {
  expect(consumed.result.schema).toBe("mastermind.workspace_role_result.v1");
  expect(consumed.result.availability).toBe("AVAILABLE");
  expect(consumed.mission.schema).toBe("mastermind.mission_workspace.v3");
  expect(consumed.mission.read_state.state).toBe("CURRENT");
  expect(consumed.mission.program.work_ref).toBe(consumed.selection.work_ref);
  expect(consumed.mission.mission.root_job_id).toBe(consumed.selection.root_job_id);
  expect(
    consumed.mission.result_refs.refs.some(
      (ref) =>
        ref.root_job_id === consumed.selection.root_job_id &&
        ref.job_id === consumed.selection.job_id &&
        ref.attempt_id === consumed.selection.attempt_id &&
        ref.result_envelope_digest === consumed.selection.result_envelope_digest,
    ),
  ).toBe(true);
}

function expectWithheld(consumed: ConsumedExport): void {
  const missionRoom = consumed.mission.source.owner_observation?.control_room;
  const resultRoom = consumed.result.source_observation.control_room;
  const missionIdentity =
    consumed.mission.result_refs.generation.source_identity;
  const resultIdentity =
    consumed.result.source_observation.runtime?.source_identity;
  expect(missionRoom).toEqual(resultRoom);
  expect(missionRoom).not.toBe(resultRoom);
  expect(missionIdentity).toBe(MISSION_RUNTIME_SOURCE_IDENTITY);
  expect(resultIdentity).toBe(RESULT_RUNTIME_SOURCE_IDENTITY);
  expect(missionIdentity).not.toBe(resultIdentity);
  expect(consumed.projection.mission.source.state).toBe("CURRENT");
  expect(consumed.projection.result.source.state).toBe("UNKNOWN");
  expect(consumed.projection.result.reason).toBe(
    "RESULT_OBSERVATION_UNQUALIFIED",
  );
  expect(consumed.projection.result.value).toBeNull();
  expect(consumed.projection.programs.source.state).toBe("UNAVAILABLE");
  expect(consumed.projection.conversation.source.state).toBe("UNAVAILABLE");
  expect(consumed.projection.companyTotal).toBeNull();
  expect(consumed.projection.work).toEqual({
    state: "UNAVAILABLE",
    reason: "WORK_PENDING_CUSTODY",
  });
}

function expectDistinctStates(consumed: ConsumedExport): void {
  const role = consumed.result.result;
  expect(role?.review?.verdict).toBe("reject");
  expect(role?.execution_status).toBe("COMPLETED");
  expect(role?.acceptance).toBe("NOT_PROJECTED");
  expect(role?.review?.reviewed_result_digest).not.toBe(
    consumed.selection.result_envelope_digest,
  );
  expect(consumed.mission.review.verdict).toBe("NOT_YET");
  expect(consumed.mission.execution.state).toBe("NOT_STARTED");
  expect(consumed.mission.transport.dispatch_state).toBe("RETURNED");
  expect(consumed.mission.acceptance.state).toBe("NOT_PROJECTED");
  expect(consumed.projection.receipts.review).toBe("NOT_YET");
  expect(consumed.projection.receipts.return).toBe("RETURNED");
  expect(consumed.projection.receipts.acceptance).toBe("NOT_PROJECTED");
  expect(consumed.projection.receipts.review).not.toBe(role?.review?.verdict);
}

function expectPresentation(consumed: ConsumedExport): void {
  expect(consumed.context.sessionRef).toBeNull();
  expect(consumed.context.bindingGeneration).toBeNull();
  expect(consumed.context.authGeneration).toBe(1);
  expect(consumed.projection.context.sessionRef).toBeNull();
  expect(consumed.projection.context.bindingGeneration).toBeNull();
  expect(consumed.missionSnapshot.source.observed_at).toBe(LOCAL_ACQUIRED_AT);
  expect(consumed.missionSnapshot.source.observed_at_kind).toBe(
    "LOCAL_ACQUISITION",
  );
  expect(consumed.missionSnapshot.source.ref_kind).toBe(
    "CONTROL_ROOM_DOCUMENT_DIGEST",
  );
  expect(consumed.resultSnapshot.source.observed_at).toBe(LOCAL_ACQUIRED_AT);
  expect(consumed.resultSnapshot.source.observed_at_kind).toBe(
    "LOCAL_ACQUISITION",
  );
  expect(consumed.resultSnapshot.source.revision?.startsWith(
    "result-source-observation:v1:",
  )).toBe(true);
  expect(consumed.missionSnapshot.source.revision?.startsWith(
    "mission-owner-observation:v1:",
  )).toBe(true);
  expect(consumed.missionSnapshot.source.revision).not.toBe(
    consumed.resultSnapshot.source.revision,
  );
}

function expectChallenges(consumed: ConsumedExport): void {
  const digest = projectMutated(consumed, (_mission, result) => {
    result.selection.result_envelope_digest = "f".repeat(64);
  });
  expect(digest.result.source.state).toBe("UNASSOCIATED");
  expect(digest.result.reason).toBe("RESULT_TUPLE_NOT_ASSOCIATED");
  expect(digest.result.value).toBeNull();

  const tuple = projectMutated(consumed, (_mission, result) => {
    result.selection.job_id = "JOB-999999999";
  });
  expect(tuple.result.source.state).toBe("UNASSOCIATED");
  expect(tuple.result.reason).toBe("RESULT_TUPLE_NOT_ASSOCIATED");

  // Challenge copies only. The exported observations stay distinct, and the
  // projected result remains UNKNOWN. Aligning one runtime field here isolates
  // the challenged clause; it is not a current join of the producer pair.
  const controlRoom = projectMutated(consumed, (mission, result) => {
    const runtime = result.source_observation.runtime;
    const room = result.source_observation.control_room;
    const missionIdentity = mission.result_refs.generation.source_identity;
    if (!runtime || !room || room.publication_after === null || !missionIdentity) {
      throw new Error("control-room challenge is missing a decoded observation");
    }
    runtime.source_identity = missionIdentity;
    room.publication_after += 1;
  });
  expect(controlRoom.result.source.state).toBe("UNKNOWN");
  expect(controlRoom.result.reason).toBe("RESULT_OBSERVATION_UNQUALIFIED");
  expect(controlRoom.result.value).toBeNull();

  const generation = projectMutated(consumed, (mission, result) => {
    const runtime = result.source_observation.runtime;
    const missionIdentity = mission.result_refs.generation.source_identity;
    if (!runtime || runtime.before === null || !missionIdentity) {
      throw new Error("runtime challenge is missing a decoded generation");
    }
    runtime.source_identity = missionIdentity;
    runtime.before += 1;
  });
  expect(generation.result.source.state).toBe("UNKNOWN");
  expect(generation.result.reason).toBe("RESULT_OBSERVATION_UNQUALIFIED");
  expect(generation.result.value).toBeNull();

  expect(consumed.result.source_observation.runtime?.source_identity).toBe(
    RESULT_RUNTIME_SOURCE_IDENTITY,
  );
  expect(consumed.mission.result_refs.generation.source_identity).toBe(
    MISSION_RUNTIME_SOURCE_IDENTITY,
  );
}

function consumptionReport(consumed: ConsumedExport): Record<string, unknown> {
  return {
    root: "meta-ceo-open-harness-convergence-20261024-sol-001",
    parent: "meta-ceo-harness-implementation-20261024-web-001",
    child: "meta-ceo-harness-office-result-cursor-20261024-01",
    mode: consumed.mode,
    directory: consumed.directory,
    sha256: consumed.hashes,
    selection: consumed.selection,
    decoders: {
      decodeResultBytes: "accepted",
      decodeResultEnvelope: "accepted",
      decodeMissionv3: "accepted",
    },
    control_room_equal: true,
    mission_runtime_source_identity: MISSION_RUNTIME_SOURCE_IDENTITY,
    result_runtime_source_identity: RESULT_RUNTIME_SOURCE_IDENTITY,
    projected_mission_state: consumed.projection.mission.source.state,
    projected_result_state: consumed.projection.result.source.state,
    projected_result_reason: consumed.projection.result.reason,
    result_review_verdict: consumed.result.result?.review?.verdict ?? null,
    result_execution_status: consumed.result.result?.execution_status ?? null,
    result_acceptance: consumed.result.result?.acceptance ?? null,
    mission_review_verdict: consumed.mission.review.verdict,
    mission_transport: consumed.mission.transport.dispatch_state,
    mission_acceptance: consumed.mission.acceptance.state,
    session_ref: consumed.context.sessionRef,
    binding_generation: consumed.context.bindingGeneration,
    observed_at_kind: "LOCAL_ACQUISITION",
  };
}

function emitConsumptionReport(report: Record<string, unknown>): void {
  const stdout = (
    globalThis as { process?: { stdout?: { write(chunk: string): void } } }
  ).process?.stdout;
  if (!stdout) throw new Error("no process stdout to report fresh consumption on");
  stdout.write(`FRESH_CONSUMED ${JSON.stringify(report)}\n`);
}

function registerConsumer(get: () => ConsumedExport): void {
  it("decodes the export with the real result and mission decoders", () => {
    expectDecoded(get());
  });

  it("withholds the result when the runtime source identities differ", () => {
    expectWithheld(get());
  });

  it("keeps review rejection, completion, transport, and acceptance distinct", () => {
    expectDistinctStates(get());
  });

  it("labels a test-owned local acquisition and leaves session and binding unknown", () => {
    expectPresentation(get());
  });

  it("withholds supplied tuple, Control Room generation, and Runtime generation mismatches", () => {
    expectChallenges(get());
  });
}

describe("result-producer consumer", () => {
  describe.skipIf(GATE.mode !== "fresh")(
    "fresh external producer gate",
    { timeout: 120_000 },
    () => {
      let consumed: ConsumedExport;
      beforeAll(async () => {
        if (GATE.mode !== "fresh") throw new Error("fresh gate required");
        consumed = await consumeExport(GATE.path, "fresh");
      });

      registerConsumer(() => consumed);

      it("reports the consumed byte hashes on stdout", () => {
        const report = consumptionReport(consumed);
        expect(report.mode).toBe("fresh");
        expect(report.directory).toBe(GATE.mode === "fresh" ? GATE.path : "");
        emitConsumptionReport(report);
      });
    },
  );

  describe.skipIf(GATE.mode === "fresh")("committed producer export replay", () => {
    let consumed: ConsumedExport;
    beforeAll(async () => {
      consumed = await consumeExport(COMMITTED_DIR, "replay");
    });

    it("pins the acquisition sha256 of each unchanged export file", () => {
      expect(consumed.mode).toBe("replay");
      expect(consumed.hashes).toEqual(PINNED_SHA256);
    });

    registerConsumer(() => consumed);

    it("keeps the mode contract: an absent key replays and an empty key fails", () => {
      expect(resolveFreshGate(undefined)).toEqual({ mode: "replay" });
      expect(resolveFreshGate({})).toEqual({ mode: "replay" });
      expect(resolveFreshGate({ OTHER_KEY: "value" })).toEqual({ mode: "replay" });
      expect(resolveFreshGate({ [FRESH_ENV_KEY]: "/tmp/supplied-export" })).toEqual({
        mode: "fresh",
        path: "/tmp/supplied-export",
      });
      expect(() => resolveFreshGate({ [FRESH_ENV_KEY]: "" })).toThrow(/empty/);
      expect(() => resolveFreshGate({ [FRESH_ENV_KEY]: "   " })).toThrow(/empty/);
    });

    it("rejects an absent fresh directory instead of reading the committed export", async () => {
      const absent = joinPath(COMMITTED_DIR, "missing-fresh-export-do-not-create");
      await expect(readExportBytes(absent)).rejects.toThrow();
    });

    it("rejects an empty, unreadable, or malformed explicit file", async () => {
      const fs = await realFs();
      const root = await fs.mkdtemp("/tmp/result-producer-negative-");
      const emptyDir = joinPath(root, "empty");
      const badDir = joinPath(root, "bad");
      const dirFile = joinPath(root, "dir-as-file");
      const selectionDir = joinPath(root, "missing-selection");
      await fs.mkdir(emptyDir, { recursive: true });
      await fs.mkdir(badDir, { recursive: true });
      await fs.mkdir(dirFile, { recursive: true });
      await fs.mkdir(selectionDir, { recursive: true });
      await fs.writeFile(joinPath(emptyDir, "actual-result.json"), new Uint8Array());
      await fs.mkdir(joinPath(dirFile, "actual-result.json"), { recursive: true });
      const committed = await readExportBytes(COMMITTED_DIR);
      for (const name of FILE_NAMES) {
        const payload = name === "actual-result.json" ? "{" : committed[name];
        await fs.writeFile(joinPath(badDir, name), payload);
        const selectionPayload = name === "fixture-provenance.json" ? "{}" : committed[name];
        await fs.writeFile(joinPath(selectionDir, name), selectionPayload);
      }
      await expect(readExportBytes(emptyDir)).rejects.toThrow(/empty/);
      await expect(readExportBytes(dirFile)).rejects.toThrow();
      await expect(consumeExport(badDir, "fresh")).rejects.toThrow(/not JSON/);
      await expect(consumeExport(selectionDir, "fresh")).rejects.toThrow(/selection/);
    });

    it("rejects provenance that does not carry the exported selection", () => {
      expect(() => exportedSelection(null)).toThrow(/JSON object/);
      expect(() => exportedSelection({})).toThrow(/selection/);
      expect(() => exportedSelection({ selection: { work_ref: "WS:ONE" } })).toThrow(
        /root_job_id/,
      );
      expect(() => parseJson("actual-result.json", new Uint8Array())).toThrow();
      expect(() =>
        parseJson("actual-result.json", new TextEncoder().encode("{")),
      ).toThrow(/not JSON/);
      expect(() =>
        exportedSelection(
          parseJson("fixture-provenance.json", new TextEncoder().encode("[]")),
        ),
      ).toThrow(/JSON object/);
    });
  });
});
