/**
 * Associated Mission/Result producer → consumer qualification.
 *
 * Two mutually exclusive modes, selected only by the caller environment:
 *
 * 1. Fresh external gate — MISSION_RESULT_FIXTURE_DIR is present. The suite
 *    reads exactly that directory with the real Node filesystem. A
 *    present-but-empty, missing, unreadable, or malformed explicit input
 *    fails this process. The committed export is never substituted.
 * 2. Committed replay — the key is absent. Sha256 and runtime source-identity
 *    pins apply only in this mode.
 *
 * actual-pair.json is the whole HTTP response body. Nested mission and
 * role_result are fields of that body. A reserialized nested Result is not
 * recorded as those HTTP bytes.
 *
 * Root meta-ceo-open-harness-convergence-20261024-sol-001.
 * Parent meta-ceo-harness-implementation-20261024-web-001.
 * Child meta-ceo-harness-office-join-cursor-20261024-01.
 * Brief 317eae34ecfda3fa4ef65fd80d1700e06bd5264f.
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

const FRESH_ENV_KEY = "MISSION_RESULT_FIXTURE_DIR";
const FILE_NAMES = ["actual-pair.json", "fixture-provenance.json"] as const;
const PINNED_SHA256 = {
  "actual-pair.json":
    "027faefc46fb4def6f304330f20799ed886c42d72a8aa88ddbd95b7885c91dda",
  "fixture-provenance.json":
    "69464454738e15a2b058395d7690fd7bea1c9db539aa1a1d2add546fd96e9719",
} as const;
const REPLAY_RUNTIME_SOURCE_IDENTITY = "d870e55698a78c2749750632bcf1b395";
const ATTEMPT_OWNED_NEGATIVE_ROOT =
  /^\/tmp\/mission-result-producer-negative-[A-Za-z0-9]{6,}$/;
const LOCAL_ACQUIRED_AT = "2026-10-24T21:40:00Z";

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
  httpBytes: number;
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
  rm(path: string, options: { recursive: true; force: true }): Promise<void>;
}

const callerEnv = (globalThis as { process?: { env?: CallerEnv } }).process?.env;

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
const COMMITTED_DIR = new URL(
  "./fixtures/mission-result-producer/",
  import.meta.url,
).pathname;

async function realFs(): Promise<NodeFs> {
  // @ts-expect-error node:fs/promises is resolved by the vitest worker.
  return (await import("node:fs/promises")) as NodeFs;
}

function joinPath(dir: string, name: string): string {
  return `${dir.replace(/\/+$/, "")}/${name}`;
}

async function removeAttemptOwnedRoot(fs: NodeFs, root: string): Promise<void> {
  if (!ATTEMPT_OWNED_NEGATIVE_ROOT.test(root)) {
    throw new Error(`refusing to remove a path outside this attempt: ${root}`);
  }
  await fs.rm(root, { recursive: true, force: true });
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

function exportedSelection(value: unknown, label: string): ExportedSelection {
  if (!record(value)) throw new Error(`${label} selection is not an object`);
  const keys = [
    "work_ref",
    "root_job_id",
    "job_id",
    "attempt_id",
    "result_envelope_digest",
  ] as const;
  const out = {} as ExportedSelection;
  for (const key of keys) {
    const item = value[key];
    if (typeof item !== "string" || item.length === 0) {
      throw new Error(`${label} selection.${key} is missing; refusing to invent a tuple`);
    }
    out[key] = item;
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

async function readExportBytes(directory: string): Promise<Record<ExportName, Uint8Array>> {
  if (!directory.trim()) {
    throw new Error("fixture directory is empty; refusing to substitute the committed export");
  }
  const fs = await realFs();
  const out = {} as Record<ExportName, Uint8Array>;
  for (const name of FILE_NAMES) {
    const path = joinPath(directory, name);
    const bytes = new Uint8Array(await fs.readFile(path));
    if (bytes.byteLength === 0) {
      throw new Error(`${path} is empty; refusing to substitute the committed export`);
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
    "actual-pair.json": await sha256Hex(bytes["actual-pair.json"]),
    "fixture-provenance.json": await sha256Hex(bytes["fixture-provenance.json"]),
  };
  const provenance = parseJson(
    "fixture-provenance.json",
    bytes["fixture-provenance.json"],
  );
  if (!record(provenance)) throw new Error("fixture-provenance.json is not a JSON object");
  if (provenance.http_body_sha256 !== hashes["actual-pair.json"]) {
    throw new Error("provenance http_body_sha256 does not match this directory's actual-pair.json");
  }
  if (provenance.http_body_bytes !== bytes["actual-pair.json"].byteLength) {
    throw new Error("provenance http_body_bytes does not match this directory's actual-pair.json");
  }
  const selection = exportedSelection(provenance.selection, "fixture-provenance.json");
  const compound = parseJson("actual-pair.json", bytes["actual-pair.json"]);
  if (!record(compound) || compound.schema !== "mastermind.workspace_mission_result.v1") {
    throw new Error("actual-pair.json is not the compound Mission/Result body");
  }
  const bodySelection = exportedSelection(compound.selection, "actual-pair.json");
  if (JSON.stringify(bodySelection) !== JSON.stringify(selection)) {
    throw new Error("compound selection differs from fixture-provenance.json; refusing to choose one");
  }
  const expected = resultSelection(selection);
  const nestedText = JSON.stringify(compound.role_result);
  const nestedBytes = new TextEncoder().encode(nestedText);
  const nestedHash = await sha256Hex(nestedBytes);
  if (nestedHash === hashes["actual-pair.json"]) {
    throw new Error("reserialized nested role_result was labeled as the whole HTTP body");
  }
  const fromBytes = decodeResultBytes(nestedBytes, RESULT_HTTP_BODY_BYTES, expected);
  const fromEnvelope = decodeResultEnvelope(compound.role_result, expected);
  if (!fromBytes || !fromEnvelope) {
    throw new Error(
      `result decoders rejected the nested role_result (decodeResultBytes=${fromBytes ? "accepted" : "rejected"}, decodeResultEnvelope=${fromEnvelope ? "accepted" : "rejected"})`,
    );
  }
  expect(fromBytes).toEqual(fromEnvelope);
  if (!sameSelection(fromBytes.selection, selection)) {
    throw new Error("decoded result selection differs from the exported tuple");
  }
  const mission = decodeMissionv3(compound.mission, {
    workRef: selection.work_ref,
    rootJobId: selection.root_job_id,
  });
  if (!mission) {
    throw new Error("decodeMissionv3 rejected the nested mission for the exported selection");
  }
  const identity = fromBytes.source_observation.runtime?.source_identity;
  if (
    !identity ||
    mission.result_refs.generation.source_identity !== identity ||
    mission.source.owner_observation?.runtime?.source_identity !== identity ||
    provenance.role_result_runtime_source_identity !== identity ||
    provenance.mission_runtime_source_identity !== identity
  ) {
    throw new Error("consumed runtime source identity is not one shared observation");
  }

  const base: ProjectionContext = {
    authGeneration: 1,
    selection: { workRef: selection.work_ref, rootJobId: selection.root_job_id },
    sessionRef: null,
    bindingGeneration: null,
    revisions: { mission: null, programs: null, result: null, conversation: null },
  };
  const pending = captureMissionOfficeRead(base);
  const missionRead = completeMissionOfficeRead(pending, base, mission, LOCAL_ACQUIRED_AT);
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
    { mission: missionSnapshot, programs: null, result: resultSnapshot, conversation: null },
    context,
  );
  return {
    mode,
    directory,
    hashes,
    httpBytes: bytes["actual-pair.json"].byteLength,
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
  mutate: (mission: Missionv3Document, result: ResultEnvelopeDigestShape) => void,
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

function expectAssociated(consumed: ConsumedExport): void {
  const identity = consumed.result.source_observation.runtime?.source_identity;
  expect(consumed.result.schema).toBe("mastermind.workspace_role_result.v1");
  expect(consumed.result.availability).toBe("AVAILABLE");
  expect(consumed.mission.schema).toBe("mastermind.mission_workspace.v3");
  expect(consumed.mission.read_state.state).toBe("CURRENT");
  expect(consumed.mission.result_refs.generation.source_identity).toBe(identity);
  expect(consumed.projection.result.value).not.toBeNull();
  expect(consumed.projection.result.reason).toBeNull();
  expect(consumed.projection.result.source.state).toBe("CURRENT");
  expect(consumed.projection.result.value?.result?.review?.verdict).toBe("reject");
  expect(consumed.projection.result.value?.result?.execution_status).toBe("COMPLETED");
  expect(consumed.projection.result.value?.result?.acceptance).toBe("NOT_PROJECTED");
  expect(consumed.projection.receipts.review).toBe("NOT_YET");
  expect(consumed.projection.receipts.return).toBe("RETURNED");
  expect(consumed.projection.receipts.acceptance).toBe("NOT_PROJECTED");
  expect(consumed.projection.receipts.review).not.toBe("reject");
  expect(consumed.mission.execution.state).toBe("NOT_STARTED");
  expect(consumed.context.sessionRef).toBeNull();
  expect(consumed.context.bindingGeneration).toBeNull();
}

function contentFallback(consumed: ConsumedExport): ResultEnvelopeDigestShape {
  const fallback = structuredClone(consumed.result);
  const view = fallback.result;
  if (!view) throw new Error("exported result has no role view");
  fallback.availability = "CONTENT_OVER_BUDGET";
  fallback.reason_codes = ["CONTENT_OVER_BUDGET"];
  view.availability = "CONTENT_OVER_BUDGET";
  view.content = null;
  view.content_complete = false;
  view.omitted = ["role_result", "summary", "next_actions"];
  const decoded = decodeResultEnvelope(fallback, resultSelection(consumed.selection));
  if (!decoded?.result) throw new Error("decodeResultEnvelope rejected the content-fallback shape");
  return decoded;
}

function expectContentFallback(consumed: ConsumedExport): void {
  const decoded = contentFallback(consumed);
  const projected = projectOffice(
    {
      mission: consumed.missionSnapshot,
      programs: null,
      result: {
        context: consumed.resultSnapshot.context,
        source: consumed.resultSnapshot.source,
        value: decoded,
      },
      conversation: null,
    },
    consumed.context,
  );
  expect(projected.result.value).not.toBeNull();
  expect(projected.result.reason).toBe("CONTENT_OVER_BUDGET");
  expect(projected.result.source.coverage).toBe("INCOMPLETE");
  expect(projected.result.value?.availability).toBe("CONTENT_OVER_BUDGET");
  expect(projected.result.value?.result?.review?.verdict).toBe("reject");
  expect(projected.result.value?.result?.content).toBeNull();
  expect(projected.receipts.review).toBe("NOT_YET");
  expect(projected.receipts.acceptance).toBe("NOT_PROJECTED");
}

function expectRefusals(consumed: ConsumedExport): void {
  const digest = projectMutated(consumed, (_mission, result) => {
    result.selection.result_envelope_digest = "f".repeat(64);
  });
  expect(digest.result.source.state).toBe("UNASSOCIATED");
  expect(digest.result.reason).toBe("RESULT_TUPLE_NOT_ASSOCIATED");
  expect(digest.result.value).toBeNull();

  const controlRoom = projectMutated(consumed, (_mission, result) => {
    const room = result.source_observation.control_room;
    if (!room || room.publication_after === null) {
      throw new Error("control-room challenge is missing a decoded observation");
    }
    room.publication_after += 1;
  });
  expect(controlRoom.result.source.state).toBe("UNKNOWN");
  expect(controlRoom.result.reason).toBe("RESULT_OBSERVATION_UNQUALIFIED");
  expect(controlRoom.result.value).toBeNull();

  const identity = projectMutated(consumed, (_mission, result) => {
    const runtime = result.source_observation.runtime;
    if (!runtime) throw new Error("runtime challenge is missing a decoded generation");
    runtime.source_identity = "a".repeat(32);
  });
  expect(identity.result.source.state).toBe("UNKNOWN");
  expect(identity.result.reason).toBe("RESULT_OBSERVATION_UNQUALIFIED");

  const noncurrent = projectMutated(consumed, (mission) => {
    mission.read_state = { ...mission.read_state, state: "PARTIAL" };
    mission.result_refs = {
      ...mission.result_refs,
      availability: "UNAVAILABLE",
      refs: [],
      absent_job_ids: [],
      omitted_job_ids: [],
    };
  });
  expect(noncurrent.result.source.state).toBe("UNASSOCIATED");
  expect(noncurrent.result.reason).toBe("RESULT_TUPLE_NOT_ASSOCIATED");
  expect(noncurrent.result.value).toBeNull();
  expect(consumed.projection.result.value).not.toBeNull();
  expect(consumed.projection.result.reason).toBeNull();
}

function consumptionReport(consumed: ConsumedExport): Record<string, unknown> {
  const identity = consumed.result.source_observation.runtime?.source_identity ?? null;
  return {
    root: "meta-ceo-open-harness-convergence-20261024-sol-001",
    parent: "meta-ceo-harness-implementation-20261024-web-001",
    child: "meta-ceo-harness-office-join-cursor-20261024-01",
    brief_sha: "317eae34ecfda3fa4ef65fd80d1700e06bd5264f",
    mode: consumed.mode,
    directory: consumed.directory,
    sha256: consumed.hashes,
    http_body_bytes: consumed.httpBytes,
    selection: consumed.selection,
    mission_runtime_source_identity: identity,
    role_result_runtime_source_identity: identity,
    runtime_before: consumed.result.source_observation.runtime?.before ?? null,
    runtime_after: consumed.result.source_observation.runtime?.after ?? null,
    projected_result_state: consumed.projection.result.source.state,
    projected_result_reason: consumed.projection.result.reason,
    result_review_verdict: consumed.result.result?.review?.verdict ?? null,
    result_execution_status: consumed.result.result?.execution_status ?? null,
    result_acceptance: consumed.result.result?.acceptance ?? null,
    mission_review_verdict: consumed.mission.review.verdict,
    mission_transport: consumed.mission.transport.dispatch_state,
    mission_acceptance: consumed.mission.acceptance.state,
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
  it("decodes the compound HTTP body and associates the nested pair", () => {
    expectAssociated(get());
  });
  it("keeps a nested content fallback associated with incomplete coverage", () => {
    expectContentFallback(get());
  });
  it("refuses a noncurrent mission, a crossed tuple, and a changed observation", () => {
    expectRefusals(get());
  });
}

describe("mission-result producer consumer", () => {
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
      it("reports identities and hashes from the consumed directory", () => {
        const report = consumptionReport(consumed);
        expect(report.mode).toBe("fresh");
        expect(report.sha256).toEqual(consumed.hashes);
        expect(report.mission_runtime_source_identity).toBe(
          report.role_result_runtime_source_identity,
        );
        expect(report.projected_result_state).toBe("CURRENT");
        expect(report.projected_result_reason).toBeNull();
        emitConsumptionReport(report);
      });
    },
  );

  describe.skipIf(GATE.mode === "fresh")("committed producer export replay", () => {
    let consumed: ConsumedExport;
    beforeAll(async () => {
      consumed = await consumeExport(COMMITTED_DIR, "replay");
    });

    it("pins the committed HTTP bytes and the shared runtime identity", () => {
      expect(consumed.mode).toBe("replay");
      expect(consumed.hashes).toEqual(PINNED_SHA256);
      expect(consumed.httpBytes).toBe(10024);
      expect(consumed.result.source_observation.runtime?.source_identity).toBe(
        REPLAY_RUNTIME_SOURCE_IDENTITY,
      );
      expect(consumed.mission.result_refs.generation.source_identity).toBe(
        REPLAY_RUNTIME_SOURCE_IDENTITY,
      );
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

    it("rejects empty or malformed explicit input and deletes only the attempt directory", async () => {
      const fs = await realFs();
      const sentinel = `/tmp/mission-result-producer-sentinel-${Date.now().toString(36)}`;
      await fs.writeFile(sentinel, "keep");
      let root: string | undefined;
      try {
        root = await fs.mkdtemp("/tmp/mission-result-producer-negative-");
        const emptyDir = joinPath(root, "empty");
        const badDir = joinPath(root, "bad");
        await fs.mkdir(emptyDir, { recursive: true });
        await fs.mkdir(badDir, { recursive: true });
        await fs.writeFile(joinPath(emptyDir, "actual-pair.json"), new Uint8Array());
        for (const name of FILE_NAMES) {
          await fs.writeFile(joinPath(badDir, name), "{");
        }
        const mismatchDir = joinPath(root, "mismatch");
        await fs.mkdir(mismatchDir, { recursive: true });
        const committed = await readExportBytes(COMMITTED_DIR);
        await fs.writeFile(joinPath(mismatchDir, "actual-pair.json"), committed["actual-pair.json"]);
        await fs.writeFile(
          joinPath(mismatchDir, "fixture-provenance.json"),
          JSON.stringify({ http_body_sha256: "ab".repeat(32), http_body_bytes: 1, selection: {} }),
        );
        await expect(readExportBytes(emptyDir)).rejects.toThrow(/empty/);
        await expect(consumeExport(badDir, "fresh")).rejects.toThrow(/not JSON/);
        await expect(consumeExport(mismatchDir, "fresh")).rejects.toThrow(/does not match/);
        await expect(consumeExport(joinPath(root, "missing"), "fresh")).rejects.toThrow();
      } finally {
        if (root !== undefined) await removeAttemptOwnedRoot(fs, root);
      }
      if (root === undefined) throw new Error("attempt-owned root was not created");
      await expect(fs.readFile(joinPath(root, "empty/actual-pair.json"))).rejects.toThrow();
      const kept = new TextDecoder().decode(await fs.readFile(sentinel));
      expect(kept).toBe("keep");
      await fs.rm(sentinel, { recursive: true, force: true });
      const committedAfter = await readExportBytes(COMMITTED_DIR);
      expect(await sha256Hex(committedAfter["actual-pair.json"])).toBe(
        PINNED_SHA256["actual-pair.json"],
      );
    });

    it("refuses to remove a caller-provided or shared directory", async () => {
      const fs = await realFs();
      await expect(removeAttemptOwnedRoot(fs, COMMITTED_DIR)).rejects.toThrow(/refusing/);
      await expect(removeAttemptOwnedRoot(fs, "/tmp")).rejects.toThrow(/refusing/);
      await expect(
        removeAttemptOwnedRoot(fs, "/tmp/mission-result-producer-negative-"),
      ).rejects.toThrow(/refusing/);
      const committed = await readExportBytes(COMMITTED_DIR);
      expect(await sha256Hex(committed["actual-pair.json"])).toBe(
        PINNED_SHA256["actual-pair.json"],
      );
    });
  });
});
