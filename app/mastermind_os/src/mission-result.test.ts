import { beforeAll, describe, expect, it } from "vitest";
import {
  COMPOUND_REFUSAL_REASONS,
  MISSION_RESULT_HTTP_BODY_BYTES,
  MISSION_RESULT_SCHEMA,
  decodeMissionResult,
  decodeMissionResultBytes,
  type MissionResultDocument,
} from "./mission-result";
import { normalizeResultSelection, type ResultSelection } from "./result";

const PINNED_SHA256 = "9ca1a0a5522ce549950d5ea542ad6acd7345e298119dbebe2625676dce67a9f2";
const PINNED_BYTES = 10024;

let httpBytes: Uint8Array;
let selection: ResultSelection;

async function sha256(bytes: Uint8Array): Promise<string> {
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  const digest = await crypto.subtle.digest("SHA-256", copy);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

beforeAll(async () => {
  // @ts-expect-error node:fs/promises is resolved by the vitest worker.
  const fs = (await import("node:fs/promises")) as { readFile(path: URL): Promise<Uint8Array> };
  httpBytes = new Uint8Array(await fs.readFile(new URL(
    "./meta-ceo/fixtures/mission-result-producer/actual-pair.json",
    import.meta.url,
  )));
  const body = JSON.parse(new TextDecoder().decode(httpBytes)) as { selection: Record<string, string> };
  const normalized = normalizeResultSelection({
    workRef: body.selection.work_ref,
    rootJobId: body.selection.root_job_id,
    jobId: body.selection.job_id,
    attemptId: body.selection.attempt_id,
    resultEnvelopeDigest: body.selection.result_envelope_digest,
  });
  if (!normalized) throw new Error("committed compound selection is not the five-field selector");
  selection = normalized;
});

function available(): MissionResultDocument {
  const decoded = decodeMissionResultBytes(httpBytes, selection);
  if (!decoded.ok || decoded.document.availability !== "AVAILABLE")
    throw new Error("unchanged producer bytes did not decode as an available pair");
  return decoded.document;
}

describe("closed compound Mission/Result body", () => {
  it("decodes the unchanged producer bytes without treating a reserialized nested result as the HTTP body", async () => {
    expect(httpBytes.byteLength).toBe(PINNED_BYTES);
    expect(await sha256(httpBytes)).toBe(PINNED_SHA256);
    const decoded = decodeMissionResultBytes(httpBytes, selection);
    expect(decoded.ok).toBe(true);
    if (!decoded.ok || decoded.document.availability !== "AVAILABLE") return;
    expect(decoded.document.schema).toBe(MISSION_RESULT_SCHEMA);
    expect(decoded.document.reasonCodes).toEqual([]);
    expect(decoded.document.mission.schema).toBe("mastermind.mission_workspace.v3");
    expect(decoded.document.mission.read_state.state).toBe("CURRENT");
    expect(decoded.document.roleResult.schema).toBe("mastermind.workspace_role_result.v1");
    expect(decoded.document.roleResult.availability).toBe("AVAILABLE");
    expect(decoded.document.roleResult.result?.review?.verdict).toBe("reject");
    expect(decoded.document.roleResult.result?.acceptance).toBe("NOT_PROJECTED");
    expect(decoded.document.roleResult.result?.execution_status).toBe("COMPLETED");
    const nested = JSON.stringify(decoded.document.roleResult);
    expect(new TextEncoder().encode(nested).byteLength).not.toBe(httpBytes.byteLength);
  });

  it("refuses an open shape, a crossed tuple, and a half-present pair", () => {
    const body = JSON.parse(new TextDecoder().decode(httpBytes)) as Record<string, unknown>;
    expect(decodeMissionResult({ ...body, extra: true }, selection)).toEqual({ ok: false, reason: "INVALID" });
    expect(decodeMissionResult({ ...body, schema: "mastermind.workspace_role_result.v1" }, selection))
      .toEqual({ ok: false, reason: "INVALID" });
    const crossed = structuredClone(body) as { selection: { work_ref: string } };
    crossed.selection.work_ref = "WS:OTHER";
    expect(decodeMissionResult(crossed, selection)).toEqual({ ok: false, reason: "INVALID" });
    expect(decodeMissionResult({ ...body, mission: null }, selection)).toEqual({ ok: false, reason: "INVALID" });
    expect(decodeMissionResult({ ...body, role_result: null }, selection)).toEqual({ ok: false, reason: "INVALID" });
    expect(decodeMissionResult({ ...body, availability: "CONTENT_OVER_BUDGET" }, selection))
      .toEqual({ ok: false, reason: "INVALID" });
  });

  it("accepts a closed unavailable body and refuses reasons that would invent a nested result", () => {
    const wire = {
      work_ref: selection.workRef,
      root_job_id: selection.rootJobId,
      job_id: selection.jobId,
      attempt_id: selection.attemptId,
      result_envelope_digest: selection.resultEnvelopeDigest,
    };
    const unavailable = {
      schema: MISSION_RESULT_SCHEMA,
      selection: wire,
      availability: "UNAVAILABLE",
      reason_codes: ["SOURCE_CHANGED", "OVER_BUDGET"],
      mission: null,
      role_result: null,
    };
    const decoded = decodeMissionResult(unavailable, selection);
    expect(decoded.ok).toBe(true);
    if (!decoded.ok || decoded.document.availability !== "UNAVAILABLE") return;
    expect(decoded.document.mission).toBeNull();
    expect(decoded.document.roleResult).toBeNull();
    expect(decoded.document.reasonCodes).toEqual(["SOURCE_CHANGED", "OVER_BUDGET"]);
    expect(decodeMissionResult({ ...unavailable, reason_codes: [] }, selection)).toEqual({ ok: false, reason: "INVALID" });
    expect(decodeMissionResult({ ...unavailable, reason_codes: ["SOURCE_CHANGED", "SOURCE_CHANGED"] }, selection))
      .toEqual({ ok: false, reason: "INVALID" });
    expect(decodeMissionResult({ ...unavailable, reason_codes: ["CONTENT_OVER_BUDGET"] }, selection))
      .toEqual({ ok: false, reason: "INVALID" });
    expect(decodeMissionResult({ ...unavailable, role_result: { schema: "mastermind.workspace_role_result.v1" } }, selection))
      .toEqual({ ok: false, reason: "INVALID" });
    expect(COMPOUND_REFUSAL_REASONS).not.toContain("CONTENT_OVER_BUDGET");
  });

  it("keeps a synthetic nested CONTENT_OVER_BUDGET inside an available compound", () => {
    const body = structuredClone(JSON.parse(new TextDecoder().decode(httpBytes))) as {
      role_result: { availability: string; reason_codes: string[]; result: { availability: string; content: unknown; content_complete: boolean; omitted: string[] } };
    };
    body.role_result.availability = "CONTENT_OVER_BUDGET";
    body.role_result.reason_codes = ["CONTENT_OVER_BUDGET"];
    body.role_result.result.availability = "CONTENT_OVER_BUDGET";
    body.role_result.result.content = null;
    body.role_result.result.content_complete = false;
    body.role_result.result.omitted = ["role_result", "summary", "next_actions"];
    const decoded = decodeMissionResult(body, selection);
    expect(decoded.ok).toBe(true);
    if (!decoded.ok || decoded.document.availability !== "AVAILABLE") return;
    expect(decoded.document.roleResult.availability).toBe("CONTENT_OVER_BUDGET");
    expect(decoded.document.roleResult.result?.content).toBeNull();
    expect(decoded.document.mission.read_state.state).toBe("CURRENT");
  });

  it("does not let reserialization replace received-byte accounting or the outer envelope cap", () => {
    const document = available();
    expect(document.availability).toBe("AVAILABLE");
    const tiny = JSON.stringify({
      schema: MISSION_RESULT_SCHEMA,
      selection: {
        work_ref: selection.workRef,
        root_job_id: selection.rootJobId,
        job_id: selection.jobId,
        attempt_id: selection.attemptId,
        result_envelope_digest: selection.resultEnvelopeDigest,
      },
      availability: "UNAVAILABLE",
      reason_codes: ["RESPONSE_OVER_BUDGET"],
      mission: null,
      role_result: null,
    });
    expect(decodeMissionResult(JSON.parse(tiny), selection).ok).toBe(true);
    const padded = new Uint8Array(MISSION_RESULT_HTTP_BODY_BYTES + 1);
    padded.set(new TextEncoder().encode(tiny));
    padded.fill(0x20, tiny.length);
    expect(decodeMissionResultBytes(padded, selection)).toEqual({ ok: false, reason: "RECEIVED_OVER_BUDGET" });
    const huge = { pad: "y".repeat(MISSION_RESULT_HTTP_BODY_BYTES) };
    expect(decodeMissionResult(huge, selection)).toEqual({ ok: false, reason: "RESPONSE_OVER_BUDGET" });
  });

  it("refuses a synthetic nested result that exceeds its own 16384-byte envelope without keeping the mission", () => {
    const body = structuredClone(JSON.parse(new TextDecoder().decode(httpBytes))) as {
      role_result: { result: { content: { summary: string } } };
    };
    body.role_result.result.content.summary = "z".repeat(20_000);
    const decoded = decodeMissionResult(body, selection);
    expect(decoded.ok).toBe(false);
    if (!decoded.ok) expect(decoded.reason).toBe("INVALID");
  });
});
